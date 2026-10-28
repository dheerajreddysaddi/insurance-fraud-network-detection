"""Fraud Indicators & Exceptions: suspicious activity, data/financial exceptions, benign sharing."""
import streamlit as st

from src import app_data, ui

COLUMNS = ["indicator_id", "type", "severity", "score", "entity_id", "claim_id", "explanation"]


def _panel(df, by_id, key):
    if df.empty:
        st.info("No indicators in this category.")
        return
    c1, c2, c3 = st.columns([2, 2, 3])
    types = c1.multiselect("Type", sorted(df["type"].unique()), key=f"{key}_t")
    sev = c2.multiselect("Severity", ["HIGH", "MEDIUM", "LOW"], key=f"{key}_s")
    q = c3.text_input("Search entity ID or explanation", key=f"{key}_q")
    f = df
    if types:
        f = f[f["type"].isin(types)]
    if sev:
        f = f[f["severity"].isin(sev)]
    if q.strip():
        ql = q.strip().lower()
        f = f[f["entity_id"].str.lower().str.contains(ql, regex=False)
              | f["explanation"].str.lower().str.contains(ql, regex=False)]
    f = f.sort_values(["score", "indicator_id"], ascending=[False, True])
    st.caption(f"{len(f)} of {len(df)} indicators. Select a row for the rule and evidence.")
    row = ui.table_with_selection(f[COLUMNS], f"{key}_tbl")
    if row is None:
        return
    ind = by_id[row["indicator_id"]]
    st.markdown(f"**{ind['indicator_type']}** - severity {ind['severity']} - score {ind['score']}")
    st.write(ind["explanation"])
    st.markdown("**Rule:** " + ind["rule_description"])
    st.markdown("**Evidence**")
    st.json(ind["evidence"])
    st.markdown("**Related entities:** " + ", ".join(ind["related_entities"]))
    st.caption(f"Detected {ind['detected_at']} - run {ind['run_id']}")


def render(ctx):
    if ctx["analysis"] is None:
        ui.no_detection()
        return
    tables, a = ctx["tables"], ctx["analysis"]
    df = app_data.indicators_frame(a["indicators"], a["rules"])
    by_id = {i["indicator_id"]: i for i in a["indicators"]}
    st.header("Fraud Indicators & Exceptions")
    t1, t2, t3 = st.tabs(["Suspicious activity", "Data & financial exceptions", "Benign shared attributes"])
    with t1:
        st.caption("Rule hits that add to fraud-risk scores. A high score means review is recommended, not that fraud is proven.")
        _panel(df[df["category"] == "SUSPICIOUS"], by_id, "susp")
    with t2:
        st.caption("Integrity and financial problems. They are reported separately and are NOT added to fraud-risk scores.")
        _panel(df[df["category"] == "EXCEPTION"], by_id, "exc")
        st.subheader("Quarantined records (failed import validation)")
        st.dataframe(tables["quarantine_records"][["quarantine_id", "entity_id", "issue_type", "reason", "raw_payload"]],
                     hide_index=True, use_container_width=True)
    with t3:
        st.caption("Claimants sharing an address look like households. A common address alone is never treated as "
                   "evidence: these indicators have score 0 and create no link in the network graph.")
        benign = df[df["category"] == "BENIGN"]
        members = {m for i in a["indicators"] if i["indicator_type"] == "BENIGN_SHARED_ADDRESS"
                   for m in i["related_entities"]}
        hh = a["claim_scores"][a["claim_scores"]["claimant_id"].isin(members)]
        c = st.columns(3)
        c[0].metric("Shared-address groups", len(benign))
        c[1].metric("Claimants in them", len(members))
        c[2].metric("Their claims flagged anyway", int(hh["flagged"].sum()))
        flagged_hh = hh[hh["flagged"]]
        if len(flagged_hh):
            st.caption("These claims were flagged because of other indicators or network membership, never the address:")
            st.dataframe(flagged_hh[["claim_id", "claimant_id", "risk_score", "indicator_types", "network_id"]],
                         hide_index=True)
        _panel(benign, by_id, "ben")