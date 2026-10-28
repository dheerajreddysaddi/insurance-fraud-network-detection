"""Evaluation: compare detector output with the isolated answer key."""
import pandas as pd
import streamlit as st

from src import evaluation


def _f(x):
    return "n/a" if x is None else f"{x:.3f}"


def _matrix(m):
    return pd.DataFrame({"Flagged": [m["tp"], m["fp"]], "Not flagged": [m["fn"], m["tn"]]},
                        index=["Actually in a planted network", "Actually normal"])


def render(ctx):
    st.header("Evaluation")
    if ctx["analysis"] is None:
        st.info("Run detection first.")
        return
    st.warning("These numbers compare the rules with SYNTHETIC labels made by the same generator the rules were "
               "designed against. They show whether the rules do what they claim. They do not show real-world "
               "fraud-detection performance.")
    try:
        gt = evaluation.load_ground_truth()
    except FileNotFoundError:
        st.info("The ground-truth files are not available in this environment (data/ground_truth/). "
                "Generate data with scripts/generate_data.py, or see DEPLOYMENT.md for the hosted setup.")
        return
    a, tables = ctx["analysis"], ctx["tables"]
    if set(gt["claim_labels"]["claim_id"]) != set(tables["claims"]["claim_id"]):
        st.error("The ground-truth files do not match the claims in this database (different seed or scale). "
                 "Regenerate both together with scripts/generate_data.py.")
        return

    res = evaluation.evaluate_all(a["claim_scores"], a["networks"], a["indicators"], gt)
    st.caption(f"Sample: {res['n_claims']:,} claims, {res['n_suspicious_claims']} of them in planted networks "
               f"(unit = claim); {res['networks']['planted']} planted networks (unit = network). "
               "There is no train/test split because the rules are not trained.")

    st.subheader("Claim level")
    rows = []
    for label, key in (("Rules only", "claims_rules_only"), ("Rules + network", "claims_rules_plus_network")):
        m = res[key]
        rows.append({"Method": label, "TP": m["tp"], "FP": m["fp"], "FN": m["fn"], "TN": m["tn"],
                     "Precision": _f(m["precision"]), "Recall": _f(m["recall"]), "F1": _f(m["f1"]),
                     "FPR": _f(m["fpr"]), "FNR": _f(m["fnr"])})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    c1, c2 = st.columns(2)
    c1.markdown("Confusion matrix: rules only")
    c1.dataframe(_matrix(res["claims_rules_only"]))
    c2.markdown("Confusion matrix: rules + network")
    c2.dataframe(_matrix(res["claims_rules_plus_network"]))

    st.subheader("Network level")
    n = res["networks"]
    st.dataframe(pd.DataFrame([{
        "Planted": n["planted"], "Recovered": n["recovered"], "Flagged": n["flagged_detected"],
        "True": n["true_positive_networks"], "False": n["false_positive_networks"],
        "Precision": _f(n["precision"]), "Recall": _f(n["recall"]), "F1": _f(n["f1"]),
        **{k: _f(v) for k, v in n["precision_at_k"].items()}}]), hide_index=True, use_container_width=True)
    st.markdown("**Per planted network**")
    st.dataframe(res["per_network"], hide_index=True, use_container_width=True)

    st.markdown("**Flagged networks that are mostly NOT planted (false positives)**")
    members = gt["network_members"]
    planted = set(members.loc[members["entity_type"] == "CLAIMANT", "entity_id"])
    nets = a["networks"].copy()
    nets["planted_share"] = nets["claimant_ids"].apply(lambda ids: sum(i in planted for i in ids) / len(ids))
    fp = nets[nets["flagged"] & (nets["planted_share"] < 0.5)]
    if fp.empty:
        st.caption("None.")
    else:
        st.dataframe(fp[["rank", "network_id", "network_score", "n_claimants", "indicator_types",
                         "planted_share", "explanation"]], hide_index=True, use_container_width=True)
        st.caption("Inspect these on the Network Analysis page to see which weak signals linked unrelated claimants.")

    st.subheader("Injected exceptions")
    ex = res["exceptions"].copy()
    for col in ("recall", "precision"):
        ex[col] = ex[col].apply(_f)
    st.dataframe(ex, hide_index=True, use_container_width=True)
    b = res["benign"]
    st.caption(f"Benign households: {b['household_claims']} claims; {b['flagged_by_rules']} flagged by rules alone, "
               f"{b['flagged_final']} after network analysis.")

    with st.expander("Metric definitions and limits"):
        st.markdown("""
- **Claim level:** TP = a claim in a planted network that was flagged. FP = a normal claim that was flagged.
  FN = a planted claim not flagged. TN = a normal claim not flagged.
- **Precision** = TP / (TP + FP). **Recall** = TP / (TP + FN). **F1** = harmonic mean of precision and recall.
- **FPR** = FP / (FP + TN). **FNR** = FN / (FN + TP).
- **Network level:** a flagged detected network counts as true if at least half of its claimants come from one planted
  network. A planted network is recovered if a flagged network contains at least half of its claimants.
- **P@K** = share of the K highest-ranked detected networks that are true.
- **Limits:** thresholds were chosen by the author with knowledge of the generator, so results are optimistic.
  Re-run with another seed (`--seed 777`) with unchanged rules for a fairer check. Synthetic labels show injected
  patterns, not proven fraud.
""")