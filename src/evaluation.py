"""Compare detector output with the answer-key files. Used AFTER detection; never feeds the detector."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

from src import config

GT_NAMES = ["networks", "network_members", "anomalies", "benign_groups", "claim_labels"]


def load_ground_truth(gt_dir=None) -> dict:
    gt_dir = Path(gt_dir or config.GROUND_TRUTH_DIR)
    missing = [n for n in GT_NAMES if not (gt_dir / f"{n}.csv").exists()]
    if missing:
        raise FileNotFoundError(f"Ground-truth files missing in {gt_dir}: {missing}. Run scripts/generate_data.py first.")
    return {n: pd.read_csv(gt_dir / f"{n}.csv", keep_default_na=False) for n in GT_NAMES}


def gt_from_generated(ground_truth) -> dict:
    """Convert the generator's in-memory ground truth to DataFrames (used by tests)."""
    return {name: pd.DataFrame(rows, columns=cols) for name, (cols, rows) in ground_truth.items()}


def expected_exceptions(gt) -> dict:
    out = defaultdict(set)
    for r in gt["anomalies"].itertuples():
        eid = "|".join(sorted(r.entity_id.split("|"))) if r.issue_type == "PLANTED_EDGE_NOT_IN_OBSERVED_EDGES" else r.entity_id
        out[r.issue_type].add(eid)
    return dict(out)


def _div(a, b):
    return a / b if b else None


def prf(tp, fp, fn) -> dict:
    precision, recall = _div(tp, tp + fp), _div(tp, tp + fn)
    if precision is None or recall is None:
        f1 = None
    else:
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def metrics(tp, fp, fn, tn) -> dict:
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, **prf(tp, fp, fn),
            "fpr": _div(fp, fp + tn), "fnr": _div(fn, fn + tp)}


def evaluate_claims(claim_scores, labels, flag_col) -> dict:
    m = claim_scores.merge(labels[["claim_id", "is_suspicious_network"]], on="claim_id", how="inner")
    y, p = m["is_suspicious_network"].astype(int) == 1, m[flag_col].astype(bool)
    return {"n": int(len(m)), **metrics(int((y & p).sum()), int((~y & p).sum()), int((y & ~p).sum()), int((~y & ~p).sum()))}


def evaluate_networks(networks, gt) -> tuple[dict, pd.DataFrame]:
    members = gt["network_members"]
    planted = {nid: set(g["entity_id"]) for nid, g in members[members["entity_type"] == "CLAIMANT"].groupby("network_id")}
    pattern_of = dict(zip(gt["networks"]["network_id"], gt["networks"]["pattern"]))
    det = networks.to_dict("records") if len(networks) else []
    per = []
    for nid, pm in sorted(planted.items()):
        best = None
        for d in det:                                   # det is in rank order, so ties keep the better rank
            overlap = len(pm & set(d["claimant_ids"]))
            if overlap and (best is None or overlap > best[0]):
                best = (overlap, d)
        if best:
            overlap, d = best
            per.append({"planted_network": nid, "pattern": pattern_of.get(nid, ""), "planted_claimants": len(pm),
                        "detected_network": d["network_id"], "detected_rank": int(d["rank"]),
                        "detected_flagged": bool(d["flagged"]), "claimants_found": overlap,
                        "recall": overlap / len(pm), "purity": overlap / len(d["claimant_ids"]),
                        "recovered": bool(d["flagged"]) and overlap / len(pm) >= 0.5})
        else:
            per.append({"planted_network": nid, "pattern": pattern_of.get(nid, ""), "planted_claimants": len(pm),
                        "detected_network": "", "detected_rank": None, "detected_flagged": False,
                        "claimants_found": 0, "recall": 0.0, "purity": None, "recovered": False})

    def relevant(d):   # a detected network is 'real' if at least half its claimants come from one planted network
        return any(len(pm & set(d["claimant_ids"])) / len(d["claimant_ids"]) >= 0.5 for pm in planted.values())

    flagged = [d for d in det if d["flagged"]]
    tp = sum(1 for d in flagged if relevant(d))
    fp = len(flagged) - tp
    recovered = sum(1 for r in per if r["recovered"])
    flags = [relevant(d) for d in det]
    p_at_k = {}
    for k in sorted({len(planted), 5, 10}):
        kk = min(k, len(det))
        p_at_k[f"P@{k}"] = sum(flags[:kk]) / kk if kk else None
    summary = {"planted": len(planted), "recovered": recovered, "detected_total": len(det),
               "flagged_detected": len(flagged), "true_positive_networks": tp, "false_positive_networks": fp,
               **prf(tp, fp, len(planted) - recovered), "precision_at_k": p_at_k}
    return summary, pd.DataFrame(per)


def evaluate_exceptions(indicators, gt) -> pd.DataFrame:
    def ids_of(itype):
        return [i for i in indicators if i["indicator_type"] == itype]

    detected = {
        "PAYMENT_EXCEEDS_APPROVED": {i["entity_id"] for i in ids_of("PAYMENT_EXCEEDS_APPROVED")},
        "CLAIM_NONEXISTENT_POLICY": {i["entity_id"] for i in ids_of("DATA_INTEGRITY_VIOLATION")
                                     if i["evidence"].get("issue_type") == "CLAIM_NONEXISTENT_POLICY"},
        "DUPLICATE_INVOICE_ACROSS_CLAIMANTS": {r for i in ids_of("DUPLICATE_INVOICE_ACROSS_CLAIMANTS")
                                               for r in i["related_entities"] if r.startswith("INV-PRV-")},
        "PLANTED_EDGE_NOT_IN_OBSERVED_EDGES": {"|".join(sorted(i["related_entities"]))
                                               for i in ids_of("MISSING_RELATIONSHIP_EDGE")},
        "BENIGN_SHARED_ADDRESS": {r for i in ids_of("BENIGN_SHARED_ADDRESS") for r in i["related_entities"]},
    }
    truth = expected_exceptions(gt)
    truth["BENIGN_SHARED_ADDRESS"] = set(gt["benign_groups"]["claimant_id"])   # all household members
    rows = []
    for issue, det in detected.items():
        t = truth.get(issue, set())
        hit = len(t & det)
        rows.append({"issue_type": issue, "planted": len(t), "detected": len(det), "matched": hit,
                     "recall": _div(hit, len(t)), "precision": _div(hit, len(det))})
    return pd.DataFrame(rows)


def evaluate_all(claim_scores, networks, indicators, gt) -> dict:
    labels = gt["claim_labels"]
    net_summary, per_network = evaluate_networks(networks, gt)
    benign_members = set(gt["benign_groups"]["claimant_id"])
    bc = claim_scores[claim_scores["claimant_id"].isin(benign_members)]
    return {"n_claims": int(len(labels)), "n_suspicious_claims": int((labels["is_suspicious_network"] == 1).sum()),
            "claims_rules_only": evaluate_claims(claim_scores, labels, "rule_flagged"),
            "claims_rules_plus_network": evaluate_claims(claim_scores, labels, "flagged"),
            "networks": net_summary, "per_network": per_network,
            "exceptions": evaluate_exceptions(indicators, gt),
            "benign": {"household_claims": int(len(bc)), "flagged_by_rules": int(bc["rule_flagged"].sum()),
                       "flagged_final": int(bc["flagged"].sum())}}


def _fmt(x):
    return "n/a" if x is None else f"{x:.3f}"


def format_report(res) -> str:
    lines = [f"Evaluation sample: {res['n_claims']} claims, {res['n_suspicious_claims']} in planted networks (unit = claim)."]
    for key, title in (("claims_rules_only", "Claim flags: rules only"),
                       ("claims_rules_plus_network", "Claim flags: rules + network")):
        m = res[key]
        lines += [f"\n{title}", f"  TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']}",
                  f"  precision={_fmt(m['precision'])} recall={_fmt(m['recall'])} F1={_fmt(m['f1'])} "
                  f"FPR={_fmt(m['fpr'])} FNR={_fmt(m['fnr'])}"]
    n = res["networks"]
    lines += ["\nNetworks", f"  planted={n['planted']} recovered={n['recovered']} flagged={n['flagged_detected']} "
              f"(true={n['true_positive_networks']}, false={n['false_positive_networks']})",
              f"  precision={_fmt(n['precision'])} recall={_fmt(n['recall'])} F1={_fmt(n['f1'])} "
              + " ".join(f"{k}={_fmt(v)}" for k, v in n["precision_at_k"].items()),
              "\nPer planted network", res["per_network"].to_string(index=False),
              "\nInjected exceptions", res["exceptions"].to_string(index=False),
              f"\nBenign households: {res['benign']}"]
    return "\n".join(lines)