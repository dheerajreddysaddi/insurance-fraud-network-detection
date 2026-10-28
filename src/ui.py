"""Shared UI helpers: styling, sign-in, formatting, row selection, investigation launcher."""
from __future__ import annotations

import hmac
import os

import pandas as pd
import streamlit as st

from src import database, investigations

ACCENT = "#1F5FAD"
PRIORITIES = ["HIGH", "MEDIUM", "LOW"]


def inject_css() -> None:
    st.markdown("""<style>
    .block-container {padding-top: 1.5rem; max-width: 1250px;}
    [data-testid="stMetricValue"] {font-size: 1.5rem;}
    h1, h2, h3 {font-weight: 600;}
    </style>""", unsafe_allow_html=True)


def money(cents) -> str:
    return "-" if cents is None or pd.isna(cents) else f"INR {int(cents) / 100:,.0f}"


def kv_table(items: dict) -> None:
    st.table(pd.DataFrame({"Field": list(items), "Value": [str(v) for v in items.values()]}).set_index("Field"))


def table_with_selection(df: pd.DataFrame, key: str, column_config=None):
    """Interactive table; returns the selected row (a Series) or None."""
    df = df.reset_index(drop=True)
    event = st.dataframe(df, use_container_width=True, hide_index=True, on_select="rerun",
                         selection_mode="single-row", key=key, column_config=column_config)
    rows = event.selection.rows
    return df.iloc[rows[0]] if rows and rows[0] < len(df) else None


def no_detection() -> None:
    st.info("No detection run exists yet. Sign in and press 'Run detection now' in the sidebar, "
            "or run `python scripts/run_detection.py`.")


# ------------------------------------------------------------------ flash message
def flash(message: str, kind: str = "success") -> None:
    st.session_state["_flash"] = (kind, message)


def show_flash() -> None:
    item = st.session_state.pop("_flash", None)
    if item:
        getattr(st, item[0])(item[1])


# ---------------------------------------------------------------------- sign-in
def _configured_passcode() -> str:
    env_value = os.environ.get("APP_PASSCODE", "").strip()
    if env_value:                       # local .env or a hosting environment variable
        return env_value
    try:
        return str(st.secrets.get("APP_PASSCODE", "")).strip()
    except Exception:                   # no secrets file present
        return ""


def reviewer():
    return st.session_state.get("reviewer")


def sidebar_login(dialect: str) -> None:
    with st.sidebar:
        st.markdown("**Reviewer sign-in**")
        if reviewer():
            st.caption(f"Signed in as {reviewer()}")
            if st.button("Sign out"):
                st.session_state.pop("reviewer", None)
                st.rerun()
            return
        passcode = _configured_passcode()
        if not passcode and dialect != "sqlite":
            st.warning("Read-only: no APP_PASSCODE is configured for this deployment.")
            return
        name = st.text_input("Your name", key="login_name", max_chars=60)
        code = st.text_input("Passcode", type="password", key="login_code") if passcode else ""
        if st.button("Sign in"):
            if not name.strip():
                st.error("Enter your name.")
            elif passcode and not hmac.compare_digest(code.encode(), passcode.encode()):
                st.error("Wrong passcode.")
            else:
                st.session_state["reviewer"] = name.strip()
                st.rerun()


# ------------------------------------------------------------ open investigation
def investigation_launcher(subject_type: str, subject_id: str, default_priority: str,
                           indicator_ids: list, key: str) -> None:
    st.subheader("Investigation")
    existing = investigations.find_by_subject(subject_type, subject_id)
    if existing:
        st.info(f"Investigation **{existing}** already exists for this {subject_type.lower()}. "
                "Open it in the Investigation Workspace.")
        return
    who = reviewer()
    if not who:
        st.caption("Sign in from the sidebar to open an investigation.")
        return
    index = PRIORITIES.index(default_priority) if default_priority in PRIORITIES else 2
    priority = st.selectbox("Priority", PRIORITIES, index=index, key=f"{key}_prio")
    note = st.text_area("Opening note (optional)", key=f"{key}_note")
    st.caption(f"{len(indicator_ids)} indicator(s) will be linked as evidence.")
    if st.button("Open investigation", key=f"{key}_btn"):
        try:
            new_id = investigations.open_investigation(subject_type, subject_id, priority, who, indicator_ids, note)
        except investigations.InvestigationError as exc:
            st.error(str(exc))
        else:
            st.success(f"Opened {new_id}. Continue in the Investigation Workspace.")