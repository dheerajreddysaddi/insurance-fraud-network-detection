"""Data validation on DataFrames (from the database or from CSV): keys, enums, dates, lifecycle, money."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import pandas as pd

from src import database
from src.constants import ENUMS
from src.fraud_detection import shared_groups
from src.investigations import ALLOWED_TRANSITIONS

ENUM_COLUMNS = [
    ("policies", "policy_type", "policy_type"), ("policies", "status", "policy_status"),
    ("providers", "provider_type", "provider_type"), ("providers", "status", "provider_status"),
    ("incidents", "incident_type", "incident_type"), ("claims", "status", "claim_status"),
    ("claim_status_events", "from_status", "claim_status"), ("claim_status_events", "to_status", "claim_status"),
    ("payments", "payment_method", "payment_method"),
    ("relationship_edges", "edge_type", "edge_type"), ("relationship_edges", "src_type", "edge_entity"),
    ("relationship_edges", "dst_type", "edge_entity"),
    ("fraud_indicators", "severity", "severity"), ("investigations", "current_status", "investigation_status"),
    ("investigations", "priority", "severity"), ("investigation_events", "event_type", "investigation_event_type"),
]
DATE_COLUMNS = {
    "claimants": ["date_of_birth", "registered_date"], "providers": ["registered_date"],
    "policies": ["start_date", "end_date"], "incidents": ["incident_date"],
    "claims": ["claim_date", "decision_date"], "claim_status_events": ["event_date"],
    "invoices": ["invoice_date", "service_date"], "payments": ["payment_date"],
    "relationship_edges": ["effective_from"], "quarantine_records": ["quarantined_date"],
}
CLAIM_TRANSITIONS = {(None, "SUBMITTED"), ("SUBMITTED", "UNDER_REVIEW"), ("UNDER_REVIEW", "APPROVED"),
                     ("UNDER_REVIEW", "REJECTED"), ("APPROVED", "PARTIALLY_PAID"), ("APPROVED", "PAID"),
                     ("PARTIALLY_PAID", "PAID")}
ENTITY_LOOKUP = {"CLAIMANT": ("claimants", "claimant_id"), "PROVIDER": ("providers", "provider_id"),
                 "POLICY": ("policies", "policy_id"), "CLAIM": ("claims", "claim_id")}


def read_csv_tables(csv_dir) -> dict:
    tables = {}
    for name in database.LOAD_ORDER:
        df = pd.read_csv(Path(csv_dir) / f"{name}.csv", dtype=str, keep_default_na=False)
        df = df.where(df != "", None)
        for col in df.columns:
            if col.endswith("_cents"):
                df[col] = pd.to_numeric(df[col])
        tables[name] = df
    return tables


def _d(series):
    return pd.to_datetime(series, errors="coerce")


def run_validation(tables, expected=None, seed=None) -> dict:
    """expected: {issue_type: set(entity ids)} of PLANTED exceptions. Matching violations are reported as
    'expected', everything else as 'unexpected' (a real problem)."""
    expected = expected or {}
    checks = []

    def record(name, ids, expected_key=None):
        ids = [str(i) for i in ids]
        allowed = expected.get(expected_key, set()) if expected_key else set()
        n_exp = sum(1 for i in ids if i in allowed)
        checks.append({"check": name, "violations": len(ids), "expected": n_exp,
                       "unexpected": len(ids) - n_exp, "examples": ids[:5]})

    def has(*names):
        return all(n in tables and len(tables[n]) > 0 for n in names)

    # primary keys, foreign keys
    for table in database.metadata.sorted_tables:
        df = tables.get(table.name)
        if df is None:
            continue
        pk = [c.name for c in table.primary_key.columns]
        dup = df[df.duplicated(subset=pk, keep=False)] if len(df) else df
        record(f"pk:{table.name}", ["|".join(map(str, r)) for r in dup[pk].drop_duplicates().itertuples(index=False)])
    for table in database.metadata.sorted_tables:
        child = tables.get(table.name)
        if child is None or child.empty:
            continue
        for fk in table.foreign_keys:
            parent = tables.get(fk.column.table.name)
            if parent is None:
                continue
            values = child[fk.parent.name].dropna()
            record(f"fk:{table.name}.{fk.parent.name}", values[~values.isin(set(parent[fk.column.name]))].unique())

    # relationship-edge integrity (polymorphic endpoints cannot be database foreign keys)
    if has("relationship_edges"):
        e = tables["relationship_edges"]
        known = {k: (set(tables[t][c]) if t in tables else set()) for k, (t, c) in ENTITY_LOOKUP.items()}
        record("edges:unknown_endpoint", [r.edge_id for r in e.itertuples()
                                          if r.src_id not in known[r.src_type] or r.dst_id not in known[r.dst_type]])
        record("edges:self_loop", e.loc[e["src_id"] == e["dst_id"], "edge_id"])

    # enums and date formats
    for table, col, key in ENUM_COLUMNS:
        df = tables.get(table)
        if df is None or df.empty:
            continue
        vals = df[col].dropna()
        record(f"enum:{table}.{col}", vals[~vals.isin(ENUMS[key])])
    for table, cols in DATE_COLUMNS.items():
        df = tables.get(table)
        if df is None or df.empty:
            continue
        for col in cols:
            s = df[col].dropna()
            record(f"date_format:{table}.{col}", s[pd.to_datetime(s, format="%Y-%m-%d", errors="coerce").isna()])

    # date ordering and lifecycle
    if has("policies"):
        p = tables["policies"]
        record("order:policy_end_before_start", p.loc[_d(p["end_date"]) < _d(p["start_date"]), "policy_id"])
    if has("claims", "incidents", "policies"):
        c = (tables["claims"].merge(tables["incidents"][["incident_id", "incident_date"]], on="incident_id", how="left")
             .merge(tables["policies"][["policy_id", "start_date", "end_date", "status", "claimant_id"]]
                    .rename(columns={"status": "policy_status", "claimant_id": "policy_claimant"}),
                    on="policy_id", how="left"))
        record("order:incident_outside_policy_period", c.loc[
            (_d(c["incident_date"]) < _d(c["start_date"])) | (_d(c["incident_date"]) > _d(c["end_date"])), "claim_id"])
        record("order:claim_before_incident", c.loc[_d(c["claim_date"]) < _d(c["incident_date"]), "claim_id"])
        record("order:decision_before_claim", c.loc[_d(c["decision_date"]) < _d(c["claim_date"]), "claim_id"])
        record("lifecycle:claim_on_cancelled_policy", c.loc[c["policy_status"] == "CANCELLED", "claim_id"])
        record("lifecycle:claimant_differs_from_policy_holder",
               c.loc[c["policy_claimant"].notna() & (c["claimant_id"] != c["policy_claimant"]), "claim_id"])
    if has("invoices", "claims", "incidents"):
        inv = (tables["invoices"].merge(tables["claims"][["claim_id", "incident_id"]], on="claim_id", how="left")
               .merge(tables["incidents"][["incident_id", "incident_date"]], on="incident_id", how="left"))
        record("order:invoice_before_service", inv.loc[_d(inv["invoice_date"]) < _d(inv["service_date"]), "invoice_id"])
        record("order:service_before_incident", inv.loc[_d(inv["service_date"]) < _d(inv["incident_date"]), "invoice_id"])
    if has("payments", "invoices", "claims"):
        pay = (tables["payments"]
               .merge(tables["invoices"][["invoice_id", "invoice_date", "claim_id"]].rename(columns={"claim_id": "invoice_claim"}),
                      on="invoice_id", how="left")
               .merge(tables["claims"][["claim_id", "decision_date"]], on="claim_id", how="left"))
        record("order:payment_before_invoice", pay.loc[_d(pay["payment_date"]) < _d(pay["invoice_date"]), "payment_id"])
        record("order:payment_before_decision", pay.loc[_d(pay["payment_date"]) < _d(pay["decision_date"]), "payment_id"])
        record("lifecycle:payment_invoice_claim_mismatch",
               pay.loc[pay["invoice_claim"].notna() & (pay["invoice_claim"] != pay["claim_id"]), "payment_id"])
    if has("claim_status_events", "claims"):
        ev = tables["claim_status_events"].sort_values("event_id")
        bad_transition, last_status = [], {}
        for claim_id, g in ev.groupby("claim_id", sort=False):
            prev = None
            for fr, to in zip(g["from_status"], g["to_status"]):
                fr = None if pd.isna(fr) else fr
                if fr != prev or (prev, to) not in CLAIM_TRANSITIONS:
                    bad_transition.append(claim_id)
                    break
                prev = to
            last_status[claim_id] = prev
        record("lifecycle:claim_transitions", bad_transition)
        cl = tables["claims"]
        record("lifecycle:claim_status_vs_latest_event",
               cl.loc[cl["claim_id"].map(last_status) != cl["status"], "claim_id"])

    # financial reconciliation
    if has("claims"):
        cl = tables["claims"].copy()
        if has("invoices"):
            inv_total = tables["invoices"].groupby("claim_id")["amount_cents"].sum()
            record("finance:invoice_total_vs_claimed",
                   cl.loc[cl["claim_id"].map(inv_total).fillna(0) != cl["claimed_cents"], "claim_id"])
        paid = (tables["payments"].groupby("claim_id")["amount_cents"].sum()
                if "payments" in tables and len(tables["payments"]) else pd.Series(dtype=float))
        cl["paid"] = cl["claim_id"].map(paid).fillna(0)
        approved, s = cl["approved_cents"], cl["status"]
        record("finance:payment_exceeds_approved", cl.loc[approved.notna() & (cl["paid"] > approved), "claim_id"],
               "PAYMENT_EXCEEDS_APPROVED")
        record("finance:payment_without_approval", cl.loc[(cl["paid"] > 0) & (approved.isna() | (approved == 0)), "claim_id"])
        record("finance:approved_exceeds_claimed", cl.loc[approved > cl["claimed_cents"], "claim_id"])
        ap = approved.fillna(0)
        bad = (((s == "REJECTED") | (s == "APPROVED") | s.isin(["SUBMITTED", "UNDER_REVIEW"])) & (cl["paid"] > 0)) | \
              ((s == "PAID") & (cl["paid"] < ap)) | ((s == "PARTIALLY_PAID") & ((cl["paid"] <= 0) | (cl["paid"] >= ap)))
        record("lifecycle:claim_status_vs_payments", cl.loc[bad, "claim_id"])
    if has("invoices", "claims"):
        inv = tables["invoices"].merge(tables["claims"][["claim_id", "claimant_id"]], on="claim_id", how="left")
        dup = inv[inv.duplicated("fingerprint", keep=False)]
        n = dup.groupby("fingerprint")["claimant_id"].transform("nunique") if len(dup) else pd.Series(dtype=int)
        record("finance:duplicate_invoice_across_claimants", dup.loc[n > 1, "invoice_id"] if len(dup) else [],
               "DUPLICATE_INVOICE_ACROSS_CLAIMANTS")

    # quarantine layer and unrecorded relationships
    if has("quarantine_records"):
        q = tables["quarantine_records"]
        policies_known = set(tables["policies"]["policy_id"]) if "policies" in tables else set()
        record("quarantine:policy_actually_exists",
               [r.entity_id for r in q.itertuples() if r.issue_type == "CLAIM_NONEXISTENT_POLICY"
                and json.loads(r.raw_payload)["policy_id"] in policies_known])
        record("quarantine:claim_nonexistent_policy",
               q.loc[q["issue_type"] == "CLAIM_NONEXISTENT_POLICY", "entity_id"], "CLAIM_NONEXISTENT_POLICY")
    if has("claimants", "relationship_edges"):
        e = tables["relationship_edges"]
        recorded = {(t, frozenset((a, b))) for t, a, b in zip(e["edge_type"], e["src_id"], e["dst_id"])}
        missing = []
        for field, etype in (("phone", "SHARES_PHONE"), ("email", "SHARES_EMAIL"), ("address", "SHARES_ADDRESS")):
            for ids in shared_groups(tables["claimants"], field).values():
                missing += [f"{a}|{b}" for a, b in combinations(ids, 2) if (etype, frozenset((a, b))) not in recorded]
        record("edges:attribute_pair_missing", missing, "PLANTED_EDGE_NOT_IN_OBSERVED_EDGES")

    # indicators and investigations (only present after detection / use)
    if has("fraud_indicators"):
        known = set()
        for name, col in (("claimants", "claimant_id"), ("claims", "claim_id"), ("providers", "provider_id"),
                          ("invoices", "invoice_id"), ("policies", "policy_id")):
            if name in tables:
                known |= set(tables[name][col])
        if "quarantine_records" in tables:
            known |= set(tables["quarantine_records"]["entity_id"])
        bad = []
        for r in tables["fraud_indicators"].itertuples():
            try:
                related = json.loads(r.related_entities)
                json.loads(r.evidence)
            except (TypeError, ValueError):
                bad.append(r.indicator_id)
                continue
            if any(x not in known for x in related):
                bad.append(r.indicator_id)
        record("indicators:bad_reference", bad)
    if has("investigations", "investigation_events"):
        groups = {k: g for k, g in tables["investigation_events"].sort_values("event_id").groupby("investigation_id")}
        bad = []
        for inv in tables["investigations"].itertuples():
            state, ok = None, True
            for r in groups.get(inv.investigation_id, pd.DataFrame(columns=["event_type"])).itertuples():
                if r.event_type == "OPENED":
                    ok &= state is None and r.to_status == "OPEN"
                    state = r.to_status
                elif r.event_type in ("STATUS_CHANGE", "DECISION"):
                    ok &= state is not None and r.from_status == state and r.to_status in ALLOWED_TRANSITIONS[state]
                    state = r.to_status
            if not ok or state != inv.current_status:
                bad.append(inv.investigation_id)
        record("investigations:lifecycle", bad)

    info = {}
    if "claimants" in tables and len(tables["claimants"]):
        info["benign_shared_address_groups"] = len(shared_groups(tables["claimants"], "address"))
    return {"validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "seed": seed,
            "row_counts": {n: int(len(df)) for n, df in tables.items()}, "checks": checks,
            "unexpected_failures": sum(c["unexpected"] for c in checks),
            "expected_exceptions": {c["check"]: c["expected"] for c in checks if c["expected"]}, "info": info}


def format_markdown(report) -> str:
    lines = ["# Validation summary", "",
             f"- Validated at (UTC): {report['validated_at']}", f"- Generation seed: {report['seed']}",
             f"- **Unexpected failures: {report['unexpected_failures']}**",
             f"- Benign shared-address groups (informational, never a violation): "
             f"{report['info'].get('benign_shared_address_groups', 'n/a')}", "",
             "## Row counts", "", "| Table | Rows |", "|---|---:|"]
    lines += [f"| {n} | {c} |" for n, c in report["row_counts"].items()]
    lines += ["", "## Checks", "",
              "Expected = planted anomalies found as intended. Unexpected = a real problem.", "",
              "| Check | Violations | Expected (planted) | Unexpected |", "|---|---:|---:|---:|"]
    lines += [f"| {c['check']} | {c['violations']} | {c['expected']} | {c['unexpected']} |" for c in report["checks"]]
    return "\n".join(lines) + "\n"