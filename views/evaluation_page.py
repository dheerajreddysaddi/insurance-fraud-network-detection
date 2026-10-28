"""Evaluation: compare detector output with the isolated answer key."""
import pandas as pd
import streamlit as st

from src import evaluation, ui

PATTERN = {"contact_ring": "Shared contact details", "narrative_ring": "Repeated incident story",
           "provider_collusion": "Provider collusion"}
ISSUE = {"PAYMENT_EXCEEDS_APPROVED": "Paid more than approved",
         "CLAIM_NONEXISTENT_POLICY": "Claim on a nonexistent policy",
         "DUPLICATE_INVOICE_ACROSS_CLAIMANTS": "Same invoice on different claimants",
         "PLANTED_EDGE_NOT_IN_OBSERVED_EDGES": "Relationship missing from records",
         "BENIGN_SHARED_ADDRESS": "Shared-address household (must not count as evidence)"}


def _f(x):
    return "n/a" if x is None else f"{x:.3f}"


def _matrix(m):
    return pd.DataFrame({"Flagged": [m["tp"], m["fp"]], "Not flagged": [m["fn"], m["tn"]]},
                        index=["Actually in a planted network", "Actually normal"])


def render(ctx):
    ui.page_header("Evaluation", "How well the rules match the known, planted patterns in the synthetic data.")
    if ctx["analysis"] is None:
        st.info("Run detection first.")
        return
    st.warning("These numbers compare the rules with SYNTHETIC labels made by the same generator the rules were "
               "designed against. They show whether the rules do what they claim, not real-world performance.")
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
    n, m = res["networks"], res["claims_rules_plus_network"]
    k = st.columns(4)
    ui.kpi(k[0], "Planted networks found", f"{n['recovered']} of {n['planted']}", "recovered by the rules", "ok")
    ui.kpi(k[1], "Networks flagged", n["flagged_detected"], f"{n['false_positive_networks']} were not planted", "medium")
    ui.kpi(k[2], "Planted claims caught", f"{m['tp']} of {m['tp'] + m['fn']}", "rules + network", "ok")
    ui.kpi(k[3], "Normal claims also flagged", m["fp"], f"of {m['fp'] + m['tn']:,} normal claims", "high")
    ui.callout(f"<b>In plain words.</b> The rules found {n['recovered']} of {n['planted']} planted networks, but also "
               f"flagged {n['false_positive_networks']} networks that were not planted. Sample: {res['n_claims']:,} claims "
               f"({res['n_suspicious_claims']} planted). Nothing is trained, so there is no train/test split.")

    t1, t2, t3, t4, t5 = st.tabs(["Claim level", "Network level", "False alarms", "Injected exceptions", "Definitions"])
    with t1:
        rows = []
        for label, key in (("Rules only", "claims_rules_only"), ("Rules + network", "claims_rules_plus_network")):
            x = res[key]
            rows.append({"Method": label, "TP": x["tp"], "FP": x["fp"], "FN": x["fn"], "TN": x["tn"],
                         "Precision": _f(x["precision"]), "Recall": _f(x["recall"]), "F1": _f(x["f1"]),
                         "FPR": _f(x["fpr"]), "FNR": _f(x["fnr"])})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        c1, c2 = st.columns(2)
        c1.markdown("**Rules only**")
        c1.dataframe(_matrix(res["claims_rules_only"]))
        c2.markdown("**Rules + network**")
        c2.dataframe(_matrix(res["claims_rules_plus_network"]))
    with t2:
        st.dataframe(pd.DataFrame([{
            "Planted": n["planted"], "Recovered": n["recovered"], "Flagged": n["flagged_detected"],
            "True": n["true_positive_networks"], "False": n["false_positive_networks"],
            "Precision": _f(n["precision"]), "Recall": _f(n["recall"]), "F1": _f(n["f1"]),
            **{k_: _f(v) for k_, v in n["precision_at_k"].items()}}]), hide_index=True, use_container_width=True)
        pn = res["per_network"]
        st.dataframe(pd.DataFrame({
            "Planted network": pn["planted_network"], "Pattern": pn["pattern"].map(lambda p: PATTERN.get(p, p)),
            "People planted": pn["planted_claimants"], "People found": pn["claimants_found"],
            "Found": (pn["recall"] * 100).round(0).astype(int).astype(str) + "%",
            "Detected as": pn["detected_network"],
            "Rank": pd.to_numeric(pn["detected_rank"], errors="coerce").astype("Int64"),
            "Flagged": pn["detected_flagged"].map({True: "Yes", False: "No"}),
            "Recovered": pn["recovered"].map({True: "Yes", False: "No"})}),
            hide_index=True, use_container_width=True)
    with t3:
        members = gt["network_members"]
        planted = set(members.loc[members["entity_type"] == "CLAIMANT", "entity_id"])
        nets = a["networks"].copy()
        nets["planted_share"] = nets["claimant_ids"].apply(lambda ids: sum(i in planted for i in ids) / len(ids))
        fp = nets[nets["flagged"] & (nets["planted_share"] < 0.5)]
        if fp.empty:
            st.success("No flagged network is mostly unplanted.")
        else:
            common = set.intersection(*[set(s.split(",")) for s in fp["indicator_types"]])
            if common:
                ui.callout(f"<b>Pattern.</b> All {len(fp)} of these networks were flagged on the same signs: "
                           + ", ".join(sorted(ui.friendly(t).lower() for t in common)) + ".")
            st.dataframe(pd.DataFrame({
                "Rank": fp["rank"], "Network": fp["network_id"], "Score": fp["network_score"],
                "Claimants": fp["n_claimants"], "Claims": fp["n_claims"],
                "Warning signs": fp["indicator_types"].map(ui.friendly_list),
                "From planted networks": (fp["planted_share"] * 100).round(0).astype(int).astype(str) + "%"}),
                hide_index=True, use_container_width=True)
            st.caption("Open these on the Network Analysis page to see which weak signs linked unrelated claimants.")
    with t4:
        ex = res["exceptions"]
        st.dataframe(pd.DataFrame({
            "Injected issue": ex["issue_type"].map(ISSUE), "Planted": ex["planted"], "Detected": ex["detected"],
            "Matched": ex["matched"], "Recall": ex["recall"].map(_f), "Precision": ex["precision"].map(_f)}),
            hide_index=True, use_container_width=True)
        b = res["benign"]
        st.caption(f"Households sharing an address: {b['household_claims']} claims; {b['flagged_by_rules']} flagged by "
                   f"rules alone, {b['flagged_final']} after network analysis.")
    with t5:
        st.markdown("""
- **Claim level:** TP = a planted claim that was flagged. FP = a normal claim that was flagged. FN = a planted claim not flagged. TN = a normal claim not flagged.
- **Precision** = TP / (TP + FP). **Recall** = TP / (TP + FN). **F1** = harmonic mean of the two.
- **FPR** = FP / (FP + TN). **FNR** = FN / (FN + TP).
- **Network level:** a flagged network counts as true if at least half its claimants come from one planted network. A planted network is recovered if a flagged network contains at least half of its claimants.
- **P@K** = share of the K highest-ranked networks that are true.
- **Limits:** thresholds were chosen with knowledge of the generator, so results are optimistic. Re-run with another seed (`--seed 777`) and unchanged rules for a fairer check.
""")