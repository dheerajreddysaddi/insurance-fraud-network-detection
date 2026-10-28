"""Overview: KPIs, a few charts, and the data-quality summary."""
import pandas as pd
import plotly.express as px
import streamlit as st

from src import app_data, investigations, ui

CATEGORY_COLORS = {"SUSPICIOUS": ui.ACCENT, "EXCEPTION": "#D68910", "BENIGN": "#9CA3AF"}
PRIORITY_COLORS = {"HIGH": "#C0392B", "MEDIUM": "#D68910", "LOW": "#9CA3AF"}


def _style(fig, height=300):
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=10, b=0), template="simple_white", legend_title_text="")
    return fig


def render(ctx):
    if ctx["analysis"] is None:
        ui.no_detection()
        return
    tables, a, run = ctx["tables"], ctx["analysis"], ctx["run"]
    cs, nets = a["claim_scores"], a["networks"]
    ind = app_data.indicators_frame(a["indicators"], a["rules"])
    inv = investigations.list_investigations()
    open_n = int((~inv["current_status"].str.startswith("CLOSED")).sum()) if len(inv) else 0
    flagged_nets = int(nets["flagged"].sum()) if len(nets) else 0

    st.header("Overview")
    st.caption(f"Detection run {run['run_id']} - {run['indicator_count']} indicators - rules hash {run['rules_hash']}")
    r1 = st.columns(4)
    r1[0].metric("Claims", f"{len(tables['claims']):,}")
    r1[1].metric("Claimants", f"{len(tables['claimants']):,}")
    r1[2].metric("Providers", f"{len(tables['providers']):,}")
    r1[3].metric("Open investigations", open_n)
    r2 = st.columns(4)
    r2[0].metric("Flagged claims", int(cs["flagged"].sum()),
                 help="Rule score above the threshold, or the claimant belongs to a flagged network.")
    r2[1].metric("Flagged networks", flagged_nets,
                 help="Connected groups with enough score and at least two different indicator types.")
    r2[2].metric("Data & financial exceptions", int((ind["category"] == "EXCEPTION").sum()),
                 help="Quarantined records, overpayments and relationships missing from the edge table.")
    r2[3].metric("Benign shared addresses", int((ind["category"] == "BENIGN").sum()),
                 help="Households sharing an address. Recorded with score 0.")

    left, right = st.columns(2)
    with left:
        st.subheader("Which signals fire most?")
        counts = ind.groupby(["type", "category"]).size().reset_index(name="count").sort_values("count")
        fig = px.bar(counts, x="count", y="type", color="category", orientation="h",
                     color_discrete_map=CATEGORY_COLORS)
        st.plotly_chart(_style(fig), use_container_width=True)
    with right:
        st.subheader("Which networks should be reviewed first?")
        flagged = nets[nets["flagged"]] if len(nets) else nets
        if len(flagged) == 0:
            st.info("No network reached the flagging threshold.")
        else:
            fig = px.bar(flagged.sort_values("network_score"), x="network_score", y="network_id", color="priority",
                         orientation="h", color_discrete_map=PRIORITY_COLORS, hover_data=["n_claimants", "n_claims"])
            st.plotly_chart(_style(fig), use_container_width=True)

    st.subheader("When were flagged claims filed?")
    m = cs.merge(tables["claims"][["claim_id", "claim_date"]], on="claim_id")
    m["month"] = m["claim_date"].str[:7]
    by_month = m.groupby("month").agg(flagged_claims=("flagged", "sum")).reset_index()
    st.plotly_chart(_style(px.bar(by_month, x="month", y="flagged_claims", color_discrete_sequence=[ui.ACCENT]), 260),
                    use_container_width=True)

    st.subheader("Investigations by status")
    if len(inv):
        st.dataframe(inv["current_status"].value_counts().rename_axis("status").reset_index(name="count"),
                     hide_index=True)
    else:
        st.caption("No investigations yet. Open one from the Claims Explorer or Network Analysis page.")

    with st.expander("Data-quality summary (automated validation)"):
        rep = app_data.load_validation(ctx["src_version"])
        checks = pd.DataFrame(rep["checks"])
        failing = checks[checks["violations"] > 0][["check", "violations"]]
        st.write(f"{len(checks) - len(failing)} of {len(checks)} checks passed with zero violations.")
        if len(failing):
            st.caption("Checks with violations. Overpayments, duplicate invoices, quarantined claims and unrecorded "
                       "edges are deliberate exceptions in this synthetic dataset; they are also reported on the "
                       "Fraud Indicators & Exceptions page.")
            st.dataframe(failing, hide_index=True)
        st.dataframe(pd.DataFrame(list(rep["row_counts"].items()), columns=["table", "rows"]), hide_index=True)