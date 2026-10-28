"""Shared UI helpers: styling, plain-English labels, sign-in, row selection, investigation launcher."""
from __future__ import annotations

import hmac
import html
import os

import pandas as pd
import streamlit as st

from src import investigations

ACCENT = "#1F5FAD"
PRIORITIES = ["HIGH", "MEDIUM", "LOW"]

TONES = {  # tone -> (text colour, background)
    "high": ("#9B1C1C", "#FDECEC"), "medium": ("#8A5300", "#FFF4E0"), "low": ("#4B5563", "#F1F3F5"),
    "ok": ("#1E6B3A", "#E8F5EC"), "info": (ACCENT, "#E8F0FB"),
}
RISK_LABEL = {"HIGH": "High risk", "MEDIUM": "Flagged", "LOW": "Low risk", "NONE": "No warning signs"}
RISK_TONE = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low", "NONE": "ok"}
STATUS_TONE = {"OPEN": "info", "IN_REVIEW": "medium", "ESCALATED": "high",
               "CLOSED_NO_ACTION": "ok", "CLOSED_ACTION_TAKEN": "low"}
FRIENDLY = {
    "SHARED_PHONE": "Shared phone number", "SHARED_EMAIL": "Shared email address",
    "SIMILAR_NARRATIVE": "Near-identical incident story", "DUPLICATE_INVOICE_ACROSS_CLAIMANTS": "Same invoice on different claimants",
    "UNUSUAL_TIMING": "Unusual timing", "REPEAT_CLAIMANT_PROVIDER": "Repeat visits to one provider",
    "PAYMENT_EXCEEDS_APPROVED": "Paid more than approved", "DATA_INTEGRITY_VIOLATION": "Record failed import checks",
    "MISSING_RELATIONSHIP_EDGE": "Relationship missing from records", "BENIGN_SHARED_ADDRESS": "Shared address (household)",
}


def friendly(code: str) -> str:
    return FRIENDLY.get(code, code.replace("_", " ").capitalize())


def friendly_list(csv: str) -> str:
    return ", ".join(friendly(t) for t in str(csv).split(",") if t) or "-"


def inject_css() -> None:
    st.markdown("""<style>
    #MainMenu, footer {visibility: hidden;}
    .block-container {padding-top: 1.4rem; max-width: 1180px;}
    html, body, [class*="css"] {font-family: "Inter", "Segoe UI", system-ui, sans-serif;}
    h1 {font-size: 1.6rem; font-weight: 650; margin-bottom: .1rem;}
    h2 {font-size: 1.2rem; font-weight: 600;} h3 {font-size: 1.05rem; font-weight: 600;}
    [data-testid="stSidebar"] {background: #F6F8FB; border-right: 1px solid #E5E7EB;}
    [data-testid="stSidebar"] .stButton > button {text-align: left; justify-content: flex-start; border-radius: 8px;
        padding: .45rem .8rem; font-weight: 500;}
    [data-testid="stSidebar"] .stButton > button[kind="secondary"] {border-color: transparent; background: transparent;}
    .brand {display: flex; gap: .6rem; align-items: center; margin: .2rem 0 1rem;}
    .brand-mark {width: 2rem; height: 2rem; border-radius: 8px; background: #1F5FAD; color: #fff; font-weight: 700;
        display: flex; align-items: center; justify-content: center; font-size: .8rem;}
    .brand-name {font-weight: 650; font-size: 1rem; line-height: 1.1;} .brand-sub {font-size: .75rem; color: #6B7280;}
    .page-sub {color: #4B5563; font-size: .95rem; margin: 0 0 1rem;}
    .callout {border-left: 4px solid #1F5FAD; background: #F3F6FB; padding: .7rem 1rem; border-radius: 6px; margin: .5rem 0 1rem; font-size: .92rem;}
    .badge {display: inline-block; padding: .1rem .6rem; border-radius: 999px; font-size: .78rem; font-weight: 600; vertical-align: middle;}
    .chip {display: inline-block; padding: .12rem .55rem; margin: .15rem .3rem .15rem 0; border-radius: 6px;
        background: #EEF2F7; color: #374151; font-size: .78rem;}
    .rank {font-size: 1.15rem; font-weight: 650; color: #1F5FAD;}
    .q-title {font-weight: 600; font-size: .98rem;}
    .q-score {font-size: 1.3rem; font-weight: 650; text-align: right;}
    .kpi, [data-testid="stMetric"] {border: 1px solid #E5E7EB; border-radius: 10px; padding: .75rem .95rem; background: #fff;}
    .kpi .l, [data-testid="stMetricLabel"] p {font-size: .76rem; color: #6B7280; text-transform: uppercase; letter-spacing: .04em;}
    .kpi .v {font-size: 1.65rem; font-weight: 650; line-height: 1.25;}
    .kpi .n {font-size: .8rem; color: #6B7280;}
    [data-testid="stMetricValue"] {font-size: 1.4rem;}
    </style>""", unsafe_allow_html=True)



def page_header(title: str, subtitle: str, steps=None) -> None:   # steps accepted but no longer shown
    st.markdown(f"<h1>{html.escape(title)}</h1><p class='page-sub'>{html.escape(subtitle)}</p>", unsafe_allow_html=True)


def chip(text: str) -> str:
    return f"<span class='chip'>{html.escape(text)}</span>"


def plural(n, word: str) -> str:
    return f"{int(n)} {word}" + ("" if int(n) == 1 else "s")


def brand() -> None:
    st.markdown("<div class='brand'><div class='brand-mark'>FN</div><div><div class='brand-name'>Fraud Network Review</div>"
                "<div class='brand-sub'>Investigation support</div></div></div>", unsafe_allow_html=True)


def _go(page: str) -> None:
    st.session_state["page"] = page


def nav(pages: list) -> None:
    current = st.session_state.get("page", pages[0])
    for p in pages:
        st.button(p, key=f"nav_{p}", type="primary" if p == current else "secondary",
                  use_container_width=True, on_click=_go, args=(p,))



def kpi(col, label: str, value, note: str = "", tone: str = "info") -> None:
    color = TONES[tone][0]
    col.markdown(f"<div class='kpi'><div class='l'>{html.escape(label)}</div>"
                 f"<div class='v' style='color:{color}'>{html.escape(str(value))}</div>"
                 f"<div class='n'>{html.escape(note)}</div></div>", unsafe_allow_html=True)


def badge(text: str, tone: str) -> str:
    fg, bg = TONES[tone]
    return f"<span class='badge' style='color:{fg};background:{bg}'>{html.escape(text)}</span>"


def callout(body_html: str) -> None:
    """body_html must already be escaped by the caller."""
    st.markdown(f"<div class='callout'>{body_html}</div>", unsafe_allow_html=True)


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
    if env_value:
        return env_value
    try:
        return str(st.secrets.get("APP_PASSCODE", "")).strip()
    except Exception:           # no secrets file present
        return ""


def reviewer():
    return st.session_state.get("reviewer")


def sidebar_login(dialect: str) -> None:
    """Renders inside whatever container the caller opened (an expander in app.py)."""
    if reviewer():
        st.caption(f"Signed in as {reviewer()}")
        if st.button("Sign out"):
            st.session_state.pop("reviewer", None)
            st.rerun()
        return
    st.caption("Needed only to open or update investigations. Browsing is open.")
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
        st.caption("Sign in from the sidebar to open an investigation for this item.")
        return
    index = PRIORITIES.index(default_priority) if default_priority in PRIORITIES else 2
    priority = st.selectbox("Priority", PRIORITIES, index=index, key=f"{key}_prio")
    note = st.text_area("Opening note (optional)", key=f"{key}_note")
    st.caption(f"{len(indicator_ids)} warning sign(s) will be linked as evidence.")
    if st.button("Open investigation", key=f"{key}_btn"):
        try:
            new_id = investigations.open_investigation(subject_type, subject_id, priority, who, indicator_ids, note)
        except investigations.InvestigationError as exc:
            st.error(str(exc))
        else:
            st.success(f"Opened {new_id}. Continue in the Investigation Workspace.")