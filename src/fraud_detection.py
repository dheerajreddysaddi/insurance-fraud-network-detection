"""Rule-based fraud indicators.

Input: dict of pandas DataFrames (the database tables). Output: list of indicator dicts.
Reads ONLY source tables, never the answer-key files, so labels cannot leak into detection.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations

import pandas as pd
import yaml
from sqlalchemy import insert, select

from src import config, database

RULES_PATH = config.CONFIG_DIR / "detection_rules.yaml"


def load_rules(path=RULES_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def rules_hash(rules: dict) -> str:
    return hashlib.sha1(json.dumps(rules, sort_keys=True).encode()).hexdigest()[:16]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", text.lower())).strip()


def money(cents) -> str:
    return f"INR {int(cents) / 100:,.2f}"


def shared_groups(claimants: pd.DataFrame, field: str) -> dict:
    """value -> sorted claimant ids, only for values shared by 2+ claimants. field: phone|email|address."""
    if field == "address":
        keys = claimants["address_line"] + "|" + claimants["city"] + "|" + claimants["postal_code"]
    else:
        keys = claimants[field]
    groups = defaultdict(list)
    for key, cid in zip(keys, claimants["claimant_id"]):
        groups[key].append(cid)
    return {k: sorted(v) for k, v in groups.items() if len(v) > 1}


class IndicatorFactory:
    """Builds indicator dicts with a deterministic id, severity band and the rule description."""

    def __init__(self, run_id: str, detected_at: str, rules: dict):
        self.run_id, self.detected_at, self.rules = run_id, detected_at, rules

    def __call__(self, itype, entity_type, entity_id, related, evidence, explanation, score, claim_id=None):
        bands = self.rules["scoring"]["severity_bands"]
        severity = "HIGH" if score >= bands["HIGH"] else "MEDIUM" if score >= bands["MEDIUM"] else "LOW"
        related = [str(r) for r in related]
        key = "|".join([self.run_id, itype, entity_id, *sorted(related)])
        return {
            "indicator_id": "IND-" + hashlib.sha1(key.encode()).hexdigest()[:12],
            "run_id": self.run_id, "indicator_type": itype, "severity": severity, "score": int(score),
            "entity_type": entity_type, "entity_id": entity_id, "claim_id": claim_id,
            "related_entities": related, "evidence": evidence,
            "rule_description": self.rules["indicators"][itype]["description"],
            "explanation": explanation, "detected_at": self.detected_at,
        }


# --------------------------------------------------------------------- detectors
def detect_shared_contacts(tables, rules, make):
    claimants = tables["claimants"]
    cfg = rules["indicators"]
    addr = dict(zip(claimants["claimant_id"],
                    claimants["address_line"] + "|" + claimants["city"] + "|" + claimants["postal_code"]))
    phone_of = dict(zip(claimants["claimant_id"], claimants["phone"]))
    out = []
    # shared address = household: recorded with score 0 so the treatment is visible
    for address, ids in sorted(shared_groups(claimants, "address").items()):
        shares_phone = len({phone_of[i] for i in ids}) == 1
        extra = " They also share a phone number, which is normal inside one household." if shares_phone else ""
        out.append(make(
            "BENIGN_SHARED_ADDRESS", "CLAIMANT", ids[0], ids,
            {"address": address, "claimants": ids, "also_share_phone": shares_phone},
            f"{len(ids)} claimants live at the same address ({address}).{extra} "
            "A common address alone is not evidence of fraud, so no risk score was added.", score=0))
    # shared phone/email counts only when the claimants live at DIFFERENT addresses
    for field, itype in (("phone", "SHARED_PHONE"), ("email", "SHARED_EMAIL")):
        c = cfg[itype]
        for value, ids in sorted(shared_groups(claimants, field).items()):
            addresses = sorted({addr[i] for i in ids})
            if len(addresses) == 1:
                continue
            score = min(c["max_score"], c["base_score"] + c["per_extra_member"] * (len(ids) - 2))
            out.append(make(
                itype, "CLAIMANT", ids[0], ids,
                {"value": value, "claimants": ids, "distinct_addresses": len(addresses)},
                f"{len(ids)} claimants ({', '.join(ids)}) share the {field} {value} but live at "
                f"{len(addresses)} different addresses, so this is not a household.", score=score))
    return out


def detect_missing_edges(tables, rules, make):
    """Phone/email sharing that exists in the data but has no recorded relationship edge."""
    edges = tables["relationship_edges"]
    recorded = {(t, frozenset((s, d))) for t, s, d in zip(edges["edge_type"], edges["src_id"], edges["dst_id"])}
    out = []
    for field, etype in (("phone", "SHARES_PHONE"), ("email", "SHARES_EMAIL")):
        for value, ids in sorted(shared_groups(tables["claimants"], field).items()):
            for a, b in combinations(ids, 2):
                if (etype, frozenset((a, b))) not in recorded:
                    out.append(make(
                        "MISSING_RELATIONSHIP_EDGE", "CLAIMANT", a, [a, b],
                        {"shared_field": field, "value": value, "expected_edge_type": etype},
                        f"{a} and {b} share the {field} {value}, but no {etype} edge is recorded. "
                        "The relationship was inferred from the claimant records.",
                        score=rules["indicators"]["MISSING_RELATIONSHIP_EDGE"]["base_score"]))
    return out


def detect_similar_narratives(tables, rules, make):
    cfg = rules["indicators"]["SIMILAR_NARRATIVE"]
    thr = rules["detection"]["narrative"]["similarity_threshold"]
    df = (tables["claims"][["claim_id", "claimant_id", "incident_id"]]
          .merge(tables["incidents"][["incident_id", "incident_type", "incident_date", "narrative"]], on="incident_id")
          .sort_values("claim_id").reset_index(drop=True))
    tokens = [frozenset(normalize_text(t).split()) for t in df["narrative"]]
    sizes = [len(t) for t in tokens]
    claim, claimant = list(df["claim_id"]), list(df["claimant_id"])
    by_type = defaultdict(list)
    for idx, itype in enumerate(df["incident_type"]):
        by_type[itype].append(idx)

    parent, pairs = {}, []

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for idxs in by_type.values():                       # blocking: only compare same incident type
        for pos, i in enumerate(idxs):
            ti, li, ci = tokens[i], sizes[i], claimant[i]
            for j in idxs[pos + 1:]:
                lj = sizes[j]
                if claimant[j] == ci or min(li, lj) < thr * max(li, lj):
                    continue
                inter = len(ti & tokens[j])
                sim = inter / (li + lj - inter)
                if sim >= thr:
                    pairs.append((claim[i], claim[j], sim))
                    parent.setdefault(claim[i], claim[i])
                    parent.setdefault(claim[j], claim[j])
                    parent[find(claim[i])] = find(claim[j])

    clusters, min_sim = defaultdict(set), {}
    for c in parent:
        clusters[find(c)].add(c)
    for a, b, s in pairs:
        root = find(a)
        min_sim[root] = min(min_sim.get(root, 1.0), s)

    owner = dict(zip(claim, claimant))
    date_of = dict(zip(claim, df["incident_date"]))
    text_of = dict(zip(claim, df["narrative"]))
    out = []
    for root in sorted(clusters, key=lambda r: min(clusters[r])):
        claim_ids = sorted(clusters[root])
        claimants_in = sorted({owner[c] for c in claim_ids})
        if len(claimants_in) < 2:
            continue
        dates = sorted(date_of[c] for c in claim_ids)
        score = min(cfg["max_score"], cfg["base_score"] + cfg["per_claim"] * len(claim_ids))
        out.append(make(
            "SIMILAR_NARRATIVE", "CLAIM", claim_ids[0], claim_ids + claimants_in,
            {"claims": claim_ids, "claimants": claimants_in, "min_similarity": round(min_sim[root], 3),
             "incident_date_range": [dates[0], dates[-1]], "example_narrative": text_of[claim_ids[0]][:160]},
            f"{len(claim_ids)} claims from {len(claimants_in)} different claimants have near-identical incident "
            f"narratives (similarity >= {min_sim[root]:.2f}); incident dates span {dates[0]} to {dates[-1]}.",
            score=score))
    return out


def detect_duplicate_invoices(tables, rules, make):
    inv = tables["invoices"].merge(tables["claims"][["claim_id", "claimant_id"]], on="claim_id")
    score = rules["indicators"]["DUPLICATE_INVOICE_ACROSS_CLAIMANTS"]["base_score"]
    seen, out = set(), []
    for key_cols in (["fingerprint"], ["provider_id", "provider_invoice_ref"]):
        cand = inv[inv.duplicated(key_cols, keep=False)]
        for _, g in cand.groupby(key_cols):
            if g["claimant_id"].nunique() < 2 or g["claim_id"].nunique() < 2:
                continue
            ids = frozenset(g["invoice_id"])
            if ids in seen:
                continue
            seen.add(ids)
            g = g.sort_values("invoice_id")
            inv_ids, claim_ids = list(g["invoice_id"]), sorted(g["claim_id"].unique())
            claimants_in, providers = sorted(g["claimant_id"].unique()), sorted(g["provider_id"].unique())
            out.append(make(
                "DUPLICATE_INVOICE_ACROSS_CLAIMANTS", "INVOICE", inv_ids[0],
                inv_ids + claim_ids + claimants_in + providers,
                {"matched_on": key_cols, "invoices": inv_ids, "claims": claim_ids, "claimants": claimants_in,
                 "provider": providers[0], "amount_cents": int(g["amount_cents"].iloc[0]),
                 "service_date": str(g["service_date"].iloc[0])},
                f"{len(inv_ids)} invoices ({', '.join(inv_ids)}) from {providers[0]} match on "
                f"{' + '.join(key_cols)} (amount {money(g['amount_cents'].iloc[0])}) but belong to claims of "
                f"{len(claimants_in)} different claimants ({', '.join(claimants_in)}).", score=score))
    return out


def detect_payment_exceeds(tables, rules, make):
    paid = tables["payments"].groupby("claim_id")["amount_cents"].sum()
    score = rules["indicators"]["PAYMENT_EXCEEDS_APPROVED"]["base_score"]
    out = []
    for claim_id, approved in sorted(zip(tables["claims"]["claim_id"], tables["claims"]["approved_cents"]),
                                     key=lambda x: x[0]):
        if pd.isna(approved):
            continue
        total, approved = int(paid.get(claim_id, 0)), int(approved)
        if total > approved:
            out.append(make(
                "PAYMENT_EXCEEDS_APPROVED", "CLAIM", claim_id, [claim_id],
                {"approved_cents": approved, "total_paid_cents": total, "excess_cents": total - approved},
                f"Claim {claim_id}: payments total {money(total)} but only {money(approved)} was approved "
                f"(excess {money(total - approved)}).", score=score, claim_id=claim_id))
    return out


def detect_unusual_timing(tables, rules, make):
    cfg = rules["detection"]["timing"]
    score = rules["indicators"]["UNUSUAL_TIMING"]["base_score"]
    claims = tables["claims"]
    df = (claims.merge(tables["incidents"][["incident_id", "incident_date"]], on="incident_id")
          .merge(tables["policies"][["policy_id", "start_date"]], on="policy_id"))
    for col in ("claim_date", "incident_date", "start_date"):
        df[col] = pd.to_datetime(df[col])
    df["days_to_incident"] = (df["incident_date"] - df["start_date"]).dt.days
    df["filing_delay"] = (df["claim_date"] - df["incident_date"]).dt.days

    pay = (tables["payments"].merge(tables["invoices"][["invoice_id", "invoice_date"]], on="invoice_id")
           .merge(claims[["claim_id", "decision_date"]], on="claim_id"))
    for col in ("payment_date", "invoice_date", "decision_date"):
        pay[col] = pd.to_datetime(pay[col])
    pay["lag"] = (pay["payment_date"] - pay[["invoice_date", "decision_date"]].max(axis=1)).dt.days
    df["min_pay_lag"] = df["claim_id"].map(pay.groupby("claim_id")["lag"].min())

    out = []
    for row in df.sort_values("claim_id").itertuples(index=False):
        signals = []
        if 0 <= row.days_to_incident <= cfg["policy_start_to_incident_days"]:
            signals.append(f"incident {int(row.days_to_incident)} days after policy start")
        if row.filing_delay <= cfg["filing_delay_days"]:
            signals.append(f"claim filed {int(row.filing_delay)} day(s) after the incident")
        if pd.notna(row.min_pay_lag) and row.min_pay_lag <= cfg["payment_lag_days"]:
            signals.append(f"payment {int(row.min_pay_lag)} day(s) after approval/invoice")
        if len(signals) >= cfg["min_signals"]:
            out.append(make(
                "UNUSUAL_TIMING", "CLAIM", row.claim_id, [row.claim_id],
                {"signals": signals, "days_policy_start_to_incident": int(row.days_to_incident),
                 "filing_delay_days": int(row.filing_delay),
                 "min_payment_lag_days": None if pd.isna(row.min_pay_lag) else int(row.min_pay_lag)},
                f"Claim {row.claim_id} shows {len(signals)} timing signals: " + "; ".join(signals) + ".",
                score=score, claim_id=row.claim_id))
    return out


def detect_repeat_claimant_provider(tables, rules, make):
    window = rules["detection"]["repeat_provider"]["window_days"]
    score = rules["indicators"]["REPEAT_CLAIMANT_PROVIDER"]["base_score"]
    inv = tables["invoices"][["claim_id", "provider_id"]].drop_duplicates()
    df = (inv.merge(tables["claims"][["claim_id", "claimant_id", "incident_id"]], on="claim_id")
          .merge(tables["incidents"][["incident_id", "incident_date"]], on="incident_id"))
    df["incident_date"] = pd.to_datetime(df["incident_date"])
    df = df[df.duplicated(["claimant_id", "provider_id"], keep=False)]
    out = []
    for (claimant, provider), g in df.groupby(["claimant_id", "provider_id"]):
        g = g.sort_values(["incident_date", "claim_id"])
        ids, dates = list(g["claim_id"]), list(g["incident_date"])
        chain = set()
        for k in range(1, len(ids)):
            if (dates[k] - dates[k - 1]).days <= window:
                chain.update((ids[k - 1], ids[k]))
        if chain:
            chain = sorted(chain)
            out.append(make(
                "REPEAT_CLAIMANT_PROVIDER", "CLAIMANT", claimant, [claimant, provider] + chain,
                {"provider": provider, "claims": chain, "window_days": window},
                f"{claimant} has {len(chain)} claims with {provider} within {window} days of each other. "
                "Repeat visits can be genuine, so this is only a weak signal.", score=score))
    return out


def detect_data_integrity(tables, rules, make):
    score = rules["indicators"]["DATA_INTEGRITY_VIOLATION"]["base_score"]
    q = tables["quarantine_records"]
    return [make("DATA_INTEGRITY_VIOLATION", "CLAIM", r.entity_id, [r.entity_id],
                 {"issue_type": r.issue_type, "reason": r.reason, "quarantine_id": r.quarantine_id},
                 f"{r.entity_id} was quarantined at import: {r.reason}. It is not part of the claims table.",
                 score=score)
            for r in q.sort_values("quarantine_id").itertuples(index=False)]


DETECTORS = (detect_shared_contacts, detect_missing_edges, detect_similar_narratives, detect_duplicate_invoices,
             detect_payment_exceeds, detect_unusual_timing, detect_repeat_claimant_provider, detect_data_integrity)


def run_detection(tables, rules=None, run_id=None, detected_at=None):
    """Returns (run_id, detected_at, indicators)."""
    rules = rules or load_rules()
    now = datetime.now(timezone.utc)
    run_id = run_id or "RUN-" + now.strftime("%Y%m%dT%H%M%S%f")
    detected_at = detected_at or now.isoformat(timespec="seconds")
    make = IndicatorFactory(run_id, detected_at, rules)
    indicators = []
    for detector in DETECTORS:
        indicators.extend(detector(tables, rules, make))
    ids = [i["indicator_id"] for i in indicators]
    assert len(ids) == len(set(ids)), "indicator ids must be unique"
    return run_id, detected_at, indicators


# ---------------------------------------------------------------- persistence
def _json_default(obj):
    return obj.item() if hasattr(obj, "item") else str(obj)


def save_run(run_id, started_at, rules, indicators) -> None:
    rows = []
    for ind in indicators:
        row = dict(ind)
        row["related_entities"] = json.dumps(ind["related_entities"])
        row["evidence"] = json.dumps(ind["evidence"], sort_keys=True, default=_json_default)
        rows.append(row)
    with database.get_engine().begin() as conn:
        conn.execute(insert(database.detection_runs).values(
            run_id=run_id, started_at=started_at, rules_hash=rules_hash(rules), indicator_count=len(rows)))
        for i in range(0, len(rows), 500):
            conn.execute(insert(database.fraud_indicators), rows[i:i + 500])


def latest_run_id():
    runs = database.detection_runs
    with database.get_engine().connect() as conn:
        return conn.execute(select(runs.c.run_id).order_by(runs.c.started_at.desc(), runs.c.run_id.desc())
                            .limit(1)).scalar()


def indicators_from_db(run_id=None):
    """Returns (run_id, indicators) with JSON columns parsed. Defaults to the latest run."""
    run_id = run_id or latest_run_id()
    if run_id is None:
        return None, []
    fi = database.fraud_indicators
    with database.get_engine().connect() as conn:
        df = pd.read_sql(select(fi).where(fi.c.run_id == run_id).order_by(fi.c.indicator_id), conn)
    df = df.astype(object).where(df.notna(), None)
    rows = df.to_dict("records")
    for r in rows:
        r["related_entities"] = json.loads(r["related_entities"])
        r["evidence"] = json.loads(r["evidence"])
    return run_id, rows