"""Overview: what needs a reviewer's attention first."""
import pandas as pd
import plotly.express as px
import streamlit as st

from src import app_data, investigations, ui

QUEUE_ORDER = ["DUPLICATE_INVOICE_ACROSS_CLAIMANTS", "SHARED_PHONE", "SHARED_EMAIL", "SIMILAR_NARRATIVE",
               "UNUSUAL_TIMING", "REPEAT_CLAIMANT_PROVIDER"]


def _open_network(network_id: str) -> None:        # button callback: jump to the Network Analysis page
    st.session_state["page"] = "Network Analysis"
    st.session_state["network_choice"] = network_id


def _queue_card(r) -> None:
    signs = [t for t in QUEUE_ORDER if t in r.indicator_types.split(",")]
    chips = "".join(ui.chip(ui.friendly(t)) for t in signs[:4])
    if len(signs) > 4:
        chips += ui.chip(f"+{len(signs) - 4} more")
    with st.container(border=True):
        c = st.columns([0.6, 5.2, 1.1, 1.3], vertical_alignment="center")
        c[0].markdown(f"<div class='rank'>#{r.rank}</div>", unsafe_allow_html=True)
        c[1].markdown(f"<div class='q-title'>{ui.plural(r.n_claimants, 'claimant')} linked through "
                      f"{ui.plural(r.n_providers, 'provider')}, {ui.plural(r.n_claims, 'claim')}</div>{chips}",
                      unsafe_allow_html=True)
        c[2].markdown(f"<div style='text-align:center'>{ui.badge(r.priority.title(), ui.RISK_TONE[r.priority])}"
                      f"<div class='q-score' style='text-align:center'>{r.network_score}</div></div>",
                      unsafe_allow_html=True)
        c[3].button("Review", key=f"rev_{r.network_id}", on_click=_open_network, args=(r.network_id,),
                    use_container_width=True)


def render(ctx):
    ui.page_header("Overview", "What needs a reviewer's attention first.")
    if ctx["analysis"] is None:
        ui.no_detection()
        return
    tables, a, run = ctx["tables"], ctx["analysis"], ctx["run"]
    cs, nets = a["claim_scores"], a["networks"]
    ind = app_data.indicators_frame(a["indicators"], a["rules"])
    inv = investigations.list_investigations()
    open_n = int((~inv["current_status"].str.startswith("CLOSED")).sum()) if len(inv) else 0
    flagged_nets = nets[nets["flagged"]] if len(nets) else nets
    high_n = int((flagged_nets["priority"] == "HIGH").sum()) if len(flagged_nets) else 0
    n_claims, n_flag = len(tables["claims"]), int(cs["flagged"].sum())

    k = st.columns(4)
    ui.kpi(k[0], "Claims reviewed", f"{n_claims:,}",
           f"{len(tables['claimants']):,} claimants, {len(tables['providers']):,} providers")
    ui.kpi(k[1], "Claims flagged", f"{n_flag:,}", f"{n_flag / n_claims:.1%} of all claims", "medium")
    ui.kpi(k[2], "Suspicious networks", len(flagged_nets), f"{high_n} high priority", "high" if high_n else "info")
    ui.kpi(k[3], "Open investigations", open_n, "being reviewed now")
    ui.callout("<b>How to read this.</b> A flag means the records show warning signs worth a closer look. "
               "It does not mean fraud has been proven.")

    st.subheader("Networks to review first")
    if len(flagged_nets) == 0:
        st.info("No network reached the flagging threshold.")
    else:
        show_all = st.checkbox(f"Show all {len(flagged_nets)} flagged networks")
        for r in flagged_nets.head(len(flagged_nets) if show_all else min(5, len(flagged_nets))).itertuples():
            _queue_card(r)

    st.subheader("Data checks (kept separate from fraud scores)")
    cnt = lambda t: int((ind["type"] == t).sum())  # noqa: E731
    e = st.columns(4)
    ui.kpi(e[0], "Overpaid claims", cnt("PAYMENT_EXCEEDS_APPROVED"), "paid more than approved", "medium")
    ui.kpi(e[1], "Quarantined records", cnt("DATA_INTEGRITY_VIOLATION"), "failed import checks", "medium")
    ui.kpi(e[2], "Unrecorded relationships", cnt("MISSING_RELATIONSHIP_EDGE"), "in the data, not in records", "medium")
    ui.kpi(e[3], "Shared-address households", cnt("BENIGN_SHARED_ADDRESS"), "not treated as evidence", "low")

    st.subheader("Which warning signs were found?")
    left, right = st.columns([3, 2])
    base = {t: v["base_score"] for t, v in a["rules"]["indicators"].items()}
    cut = a["rules"]["scoring"]["severity_bands"]["MEDIUM"]
    susp = ind[ind["category"] == "SUSPICIOUS"]
    counts = susp.groupby("type").size().reset_index(name="Times detected")
    counts["Warning sign"] = counts["type"].map(ui.friendly)
    counts["Strength"] = counts["type"].map(lambda t: "Stronger signs" if base[t] >= cut else "Weak signs")
    fig = px.bar(counts.sort_values("Times detected"), x="Times detected", y="Warning sign", color="Strength",
                 orientation="h", color_discrete_map={"Stronger signs": ui.ACCENT, "Weak signs": "#B8C0CC"})
    fig.update_layout(height=290, margin=dict(l=0, r=0, t=10, b=0), template="simple_white", yaxis_title="",
                      legend=dict(orientation="h", y=-0.25, title_text=""))
    left.plotly_chart(fig, use_container_width=True)
    with right:
        ui.callout("<b>Reading the chart.</b> Most detections are weak signs such as repeat visits and timing. "
                   "They are common in genuine claims, so they matter mainly when several appear together or "
                   f"alongside a stronger sign. 'Weak' means a rule score under {cut}.")

    with st.expander("Data-quality summary (automated validation)"):
        rep = app_data.load_validation(ctx["src_version"])
        checks = pd.DataFrame(rep["checks"])
        failing = checks[checks["violations"] > 0][["check", "violations"]]
        st.write(f"{len(checks) - len(failing)} of {len(checks)} checks passed with zero violations.")
        if len(failing):
            st.caption("Checks with violations. Overpayments, duplicate invoices, quarantined claims and unrecorded "
                       "relationships are deliberate exceptions in this synthetic dataset.")
            st.dataframe(failing, hide_index=True)
        st.dataframe(pd.DataFrame(list(rep["row_counts"].items()), columns=["Table", "Rows"]), hide_index=True)
    st.caption(f"Detection run {run['run_id']} - {run['indicator_count']} indicators - rules version {run['rules_hash']}")