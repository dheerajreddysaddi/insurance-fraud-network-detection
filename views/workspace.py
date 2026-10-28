"""Investigation Workspace: open, review, change status, add notes. History is append-only."""
import streamlit as st

from src import app_data, investigations, ui
from src.constants import ENUMS
from src.investigations import ALLOWED_TRANSITIONS, InvestigationError


def _indicator_ids(ctx, subject_type, subject_id):
    a = ctx["analysis"]
    if a is None:
        return []
    if subject_type == "CLAIM":
        claims = ctx["tables"]["claims"]
        match = claims[claims["claim_id"] == subject_id]
        if match.empty:
            raise InvestigationError(f"Claim {subject_id} does not exist.")
        found = app_data.indicators_for_claim(a["indicators"], subject_id, match.iloc[0]["claimant_id"])
    else:
        nets = a["networks"]
        match = nets[nets["network_id"] == subject_id] if len(nets) else nets
        if len(match) == 0:
            raise InvestigationError(f"Network {subject_id} is not in the latest detection run.")
        found = app_data.indicators_for_network(a["indicators"], a["rules"], a["owner"], match.iloc[0]["claimant_ids"])
    return [i["indicator_id"] for i in found]


def _open_form(ctx):
    with st.expander("Open a new investigation"):
        stype = st.radio("Subject", ["CLAIM", "NETWORK"], horizontal=True)
        sid = st.text_input("Claim ID or network ID", placeholder="CLAIM-2026-000123 or SUSNET-CLM-2026-000130")
        prio = st.selectbox("Priority", ui.PRIORITIES, index=1, key="new_prio")
        note = st.text_area("Opening note (optional)", key="new_note")
        if st.button("Open investigation", key="new_btn"):
            who = ui.reviewer()
            if not who:
                st.warning("Sign in from the sidebar first.")
                return
            try:
                new_id = investigations.open_investigation(stype, sid.strip(), prio, who,
                                                           _indicator_ids(ctx, stype, sid.strip()), note)
            except InvestigationError as exc:
                st.error(str(exc))
            else:
                ui.flash(f"Opened {new_id}.")
                st.rerun()


def _actions(inv_id, current):
    who = ui.reviewer()
    if not who:
        st.info("Sign in from the sidebar to change status or add notes.")
        return
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Change status**")
        allowed = sorted(ALLOWED_TRANSITIONS[current])
        if not allowed:
            st.caption("This investigation is closed. Closed states are final, but you can still add notes.")
        else:
            with st.form(f"status_{inv_id}_{current}"):
                new_status = st.selectbox("New status", allowed)
                note = st.text_area("Note (required when closing)")
                if st.form_submit_button("Save status change"):
                    try:
                        investigations.change_status(inv_id, new_status, who, note, expected_status=current)
                    except InvestigationError as exc:
                        st.error(str(exc))
                    else:
                        ui.flash(f"{inv_id} moved to {new_status}.")
                        st.rerun()
            st.caption("Closing records a review outcome. It is not a confirmed fraud label.")
    with c2:
        st.markdown("**Add a note**")
        with st.form(f"note_{inv_id}", clear_on_submit=True):
            text = st.text_area("Note")
            if st.form_submit_button("Add note"):
                try:
                    investigations.add_note(inv_id, who, text)
                except InvestigationError as exc:
                    st.error(str(exc))
                else:
                    ui.flash("Note added.")
                    st.rerun()


def render(ctx):
    st.header("Investigation Workspace")
    st.caption("Statuses record the reviewer's workflow decision. They are not confirmed fraud labels. "
               "Changes made by other reviewers appear when you refresh or interact with the page.")
    inv = investigations.list_investigations()
    counts = {s: int((inv["current_status"] == s).sum()) if len(inv) else 0 for s in ENUMS["investigation_status"]}
    st.caption("  |  ".join(f"{s}: {n}" for s, n in counts.items()))
    _open_form(ctx)
    if inv.empty:
        st.info("No investigations yet. Open one above, or from the Claims Explorer or Network Analysis page.")
        return
    wanted = st.multiselect("Filter by status", ENUMS["investigation_status"])
    shown = inv[inv["current_status"].isin(wanted)] if wanted else inv
    row = ui.table_with_selection(shown[["investigation_id", "subject_type", "subject_id", "priority",
                                         "current_status", "opened_by", "opened_at"]], "inv_table")
    if row is None:
        st.caption("Select an investigation to see its evidence and history.")
        return
    inv_id = row["investigation_id"]
    detail = investigations.get_investigation(inv_id)
    s = detail["summary"]
    st.divider()
    st.subheader(f"{inv_id} - {s['current_status']}")
    st.write(f"Subject: **{s['subject_type']} {s['subject_id']}** - priority {s['priority']} - "
             f"opened by {s['opened_by']} at {s['opened_at']}")
    st.markdown("**Evidence linked when it was opened**")
    if detail["indicators"].empty:
        st.caption("No indicators were linked.")
    for r in detail["indicators"].itertuples():
        st.markdown(f"- **{r.indicator_type}** ({r.severity}, score {r.score}): {r.explanation}")
    st.markdown("**History (append-only)**")
    st.dataframe(detail["events"][["event_time", "event_type", "from_status", "to_status", "actor", "note"]],
                 hide_index=True, use_container_width=True)
    _actions(inv_id, s["current_status"])