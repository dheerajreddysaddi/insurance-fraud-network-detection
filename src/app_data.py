"""Cached data access for the dashboard. Reads the database only; never reads the answer key."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import func, select

from src import database, fraud_detection, network_analysis, validators

SOURCE_TABLES = ["claimants", "providers", "policies", "incidents", "claims", "claim_status_events",
                 "invoices", "payments", "relationship_edges", "quarantine_records"]
INDICATOR_COLUMNS = ["indicator_id", "type", "category", "severity", "score", "entity_id", "claim_id",
                     "explanation"]


def source_version() -> str:
    """Cheap fingerprint of the source tables; changes when data is regenerated so caches refresh."""
    tables = database.metadata.tables
    with database.get_engine().connect() as conn:
        counts = [conn.execute(select(func.count()).select_from(tables[n])).scalar_one()
                  for n in ("claims", "invoices", "payments", "relationship_edges")]
    return "-".join(map(str, counts))


@st.cache_data(show_spinner="Loading data from the database...")
def load_source_tables(version: str) -> dict:
    return database.read_tables(SOURCE_TABLES)


def latest_run():
    runs = database.detection_runs
    with database.get_engine().connect() as conn:
        row = conn.execute(select(runs).order_by(runs.c.started_at.desc(), runs.c.run_id.desc())
                           .limit(1)).mappings().first()
    return dict(row) if row else None


@st.cache_data(show_spinner="Analysing indicators and networks...")
def load_analysis(run_id: str, version: str) -> dict:
    tables = load_source_tables(version)
    rules = fraud_detection.load_rules()
    _, indicators = fraud_detection.indicators_from_db(run_id)
    result = network_analysis.analyze(tables, indicators, rules)
    owner = dict(zip(tables["claims"]["claim_id"], tables["claims"]["claimant_id"]))
    return {"rules": rules, "indicators": indicators, "owner": owner, **result}


@st.cache_data(show_spinner="Running validation checks...")
def load_validation(version: str) -> dict:
    return validators.run_validation(load_source_tables(version), None, None)


def run_detection_and_save() -> str:
    """Runs detection on fresh database tables and stores it as a NEW run (older runs are kept)."""
    tables = database.read_tables(SOURCE_TABLES)
    rules = fraud_detection.load_rules()
    run_id, detected_at, indicators = fraud_detection.run_detection(tables, rules)
    fraud_detection.save_run(run_id, detected_at, rules, indicators)
    st.cache_data.clear()
    return run_id


# ------------------------------------------------------------ indicator helpers
def category_map(rules: dict) -> dict:
    return {t: v["category"] for t, v in rules["indicators"].items()}


def indicators_frame(indicators: list, rules: dict) -> pd.DataFrame:
    cat = category_map(rules)
    rows = [{"indicator_id": i["indicator_id"], "type": i["indicator_type"], "category": cat[i["indicator_type"]],
             "severity": i["severity"], "score": i["score"], "entity_id": i["entity_id"],
             "claim_id": i["claim_id"] or "", "explanation": i["explanation"]} for i in indicators]
    return pd.DataFrame(rows, columns=INDICATOR_COLUMNS)


def indicators_for_claim(indicators: list, claim_id: str, claimant_id: str) -> list:
    """Indicators that mention this claim or its claimant (claimant-level ones apply to all their claims)."""
    out = []
    for i in indicators:
        related = i["related_entities"]
        if (i["claim_id"] == claim_id or claim_id in related or claimant_id in related
                or i["entity_id"] in (claim_id, claimant_id)):
            out.append(i)
    return out


def indicators_for_network(indicators: list, rules: dict, owner: dict, claimant_ids) -> list:
    cat = category_map(rules)
    members = set(claimant_ids)
    return [i for i in indicators if cat[i["indicator_type"]] == "SUSPICIOUS"
            and network_analysis.indicator_claimants(i, owner) & members]