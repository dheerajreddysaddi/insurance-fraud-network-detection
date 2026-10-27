"""Schema + engine. One code path for SQLite (local) and PostgreSQL (hosted)."""
from __future__ import annotations

from sqlalchemy import (CheckConstraint, Column, ForeignKey, Integer, MetaData, String,
                        Table, Text, UniqueConstraint, PrimaryKeyConstraint, create_engine,
                        delete, event, func, select, text)
from sqlalchemy.exc import SQLAlchemyError

from src import config
from src.constants import ENUMS

metadata = MetaData()


class DatabaseError(RuntimeError):
    """Raised with an actionable message instead of silently switching databases."""


def _enum_check(table: str, column: str, key: str) -> CheckConstraint:
    values = ", ".join(f"'{v}'" for v in ENUMS[key])
    return CheckConstraint(f"{column} IN ({values})", name=f"ck_{table}_{column}")


# ---------------------------------------------------------------- source tables
claimants = Table(
    "claimants", metadata,
    Column("claimant_id", String(20), primary_key=True),
    Column("first_name", String(60), nullable=False),
    Column("last_name", String(60), nullable=False),
    Column("date_of_birth", String(10), nullable=False),
    Column("phone", String(30), nullable=False),
    Column("email", String(120), nullable=False),
    Column("address_line", String(120), nullable=False),
    Column("city", String(60), nullable=False),
    Column("postal_code", String(10), nullable=False),
    Column("registered_date", String(10), nullable=False),
)

providers = Table(
    "providers", metadata,
    Column("provider_id", String(12), primary_key=True),
    Column("provider_name", String(120), nullable=False),
    Column("provider_type", String(20), nullable=False),
    Column("phone", String(30), nullable=False),
    Column("email", String(120), nullable=False),
    Column("address_line", String(120), nullable=False),
    Column("city", String(60), nullable=False),
    Column("registered_date", String(10), nullable=False),
    Column("status", String(10), nullable=False),
    _enum_check("providers", "provider_type", "provider_type"),
    _enum_check("providers", "status", "provider_status"),
)

policies = Table(
    "policies", metadata,
    Column("policy_id", String(20), primary_key=True),
    Column("claimant_id", String(20), ForeignKey("claimants.claimant_id"), nullable=False, index=True),
    Column("policy_type", String(10), nullable=False),
    Column("start_date", String(10), nullable=False),
    Column("end_date", String(10), nullable=False),
    Column("premium_cents", Integer, nullable=False),
    Column("coverage_limit_cents", Integer, nullable=False),
    Column("status", String(10), nullable=False),
    CheckConstraint("end_date >= start_date", name="ck_policies_dates"),
    CheckConstraint("premium_cents > 0 AND coverage_limit_cents > 0", name="ck_policies_amounts"),
    _enum_check("policies", "policy_type", "policy_type"),
    _enum_check("policies", "status", "policy_status"),
)

incidents = Table(
    "incidents", metadata,
    Column("incident_id", String(20), primary_key=True),
    Column("incident_date", String(10), nullable=False),
    Column("location", String(80), nullable=False),
    Column("incident_type", String(30), nullable=False),
    Column("narrative", Text, nullable=False),
    _enum_check("incidents", "incident_type", "incident_type"),
)

claims = Table(
    "claims", metadata,
    Column("claim_id", String(24), primary_key=True),
    Column("claimant_id", String(20), ForeignKey("claimants.claimant_id"), nullable=False, index=True),
    Column("policy_id", String(20), ForeignKey("policies.policy_id"), nullable=False, index=True),
    Column("incident_id", String(20), ForeignKey("incidents.incident_id"), nullable=False, index=True),
    Column("claim_date", String(10), nullable=False),
    Column("claimed_cents", Integer, nullable=False),
    Column("approved_cents", Integer),
    Column("decision_date", String(10)),
    Column("status", String(20), nullable=False),
    CheckConstraint("claimed_cents > 0", name="ck_claims_claimed"),
    CheckConstraint("approved_cents IS NULL OR approved_cents >= 0", name="ck_claims_approved"),
    _enum_check("claims", "status", "claim_status"),
)

claim_status_events = Table(
    "claim_status_events", metadata,
    Column("event_id", String(12), primary_key=True),
    Column("claim_id", String(24), ForeignKey("claims.claim_id"), nullable=False, index=True),
    Column("from_status", String(20)),
    Column("to_status", String(20), nullable=False),
    Column("event_date", String(10), nullable=False),
    _enum_check("claim_status_events", "to_status", "claim_status"),
)

invoices = Table(
    "invoices", metadata,
    Column("invoice_id", String(30), primary_key=True),
    Column("claim_id", String(24), ForeignKey("claims.claim_id"), nullable=False, index=True),
    Column("provider_id", String(12), ForeignKey("providers.provider_id"), nullable=False, index=True),
    Column("provider_invoice_ref", String(20), nullable=False),
    Column("invoice_date", String(10), nullable=False),
    Column("service_date", String(10), nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("description", String(120), nullable=False),
    Column("fingerprint", String(16), nullable=False, index=True),  # derived: hash of key fields
    CheckConstraint("amount_cents > 0", name="ck_invoices_amount"),
)

payments = Table(
    "payments", metadata,
    Column("payment_id", String(20), primary_key=True),
    Column("claim_id", String(24), ForeignKey("claims.claim_id"), nullable=False, index=True),
    Column("invoice_id", String(30), ForeignKey("invoices.invoice_id"), nullable=False, index=True),
    Column("payment_date", String(10), nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("payment_method", String(20), nullable=False),
    CheckConstraint("amount_cents > 0", name="ck_payments_amount"),
    _enum_check("payments", "payment_method", "payment_method"),
)

# src_id/dst_id are polymorphic (claimant, provider, ...), so they are validated in code, not by FK.
relationship_edges = Table(
    "relationship_edges", metadata,
    Column("edge_id", String(12), primary_key=True),
    Column("edge_type", String(20), nullable=False),
    Column("src_type", String(10), nullable=False),
    Column("src_id", String(30), nullable=False, index=True),
    Column("dst_type", String(10), nullable=False),
    Column("dst_id", String(30), nullable=False, index=True),
    Column("evidence", Text, nullable=False),
    Column("effective_from", String(10), nullable=False),
    Column("source", String(10), nullable=False),
    UniqueConstraint("edge_type", "src_id", "dst_id", name="uq_edges_triple"),
    _enum_check("relationship_edges", "edge_type", "edge_type"),
    _enum_check("relationship_edges", "src_type", "edge_entity"),
    _enum_check("relationship_edges", "dst_type", "edge_entity"),
)

# Import-validation layer: records that violate a foreign key live here, not in the real tables.
quarantine_records = Table(
    "quarantine_records", metadata,
    Column("quarantine_id", String(12), primary_key=True),
    Column("entity_type", String(20), nullable=False),
    Column("entity_id", String(30), nullable=False),
    Column("issue_type", String(60), nullable=False),
    Column("raw_payload", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("quarantined_date", String(10), nullable=False),
)

# ------------------------------------------------- detection + investigation tables
detection_runs = Table(
    "detection_runs", metadata,
    Column("run_id", String(30), primary_key=True),
    Column("started_at", String(30), nullable=False),
    Column("rules_hash", String(16), nullable=False),
    Column("indicator_count", Integer, nullable=False),
)

fraud_indicators = Table(
    "fraud_indicators", metadata,
    Column("indicator_id", String(16), primary_key=True),
    Column("run_id", String(30), ForeignKey("detection_runs.run_id"), nullable=False, index=True),
    Column("indicator_type", String(40), nullable=False),
    Column("severity", String(10), nullable=False),
    Column("score", Integer, nullable=False),
    Column("entity_type", String(20), nullable=False),
    Column("entity_id", String(30), nullable=False, index=True),
    Column("claim_id", String(24), ForeignKey("claims.claim_id"), index=True),  # nullable
    Column("related_entities", Text, nullable=False),   # JSON list
    Column("evidence", Text, nullable=False),            # JSON object
    Column("rule_description", Text, nullable=False),
    Column("explanation", Text, nullable=False),
    Column("detected_at", String(30), nullable=False),
    _enum_check("fraud_indicators", "severity", "severity"),
)

investigations = Table(
    "investigations", metadata,
    Column("investigation_id", String(20), primary_key=True),
    Column("subject_type", String(10), nullable=False),
    Column("subject_id", String(40), nullable=False),
    Column("priority", String(10), nullable=False),
    Column("opened_by", String(60), nullable=False),
    Column("opened_at", String(30), nullable=False),
    Column("current_status", String(20), nullable=False),
    UniqueConstraint("subject_type", "subject_id", name="uq_investigation_subject"),
    _enum_check("investigations", "subject_type", "subject_type"),
    _enum_check("investigations", "priority", "severity"),
    _enum_check("investigations", "current_status", "investigation_status"),
)

investigation_indicators = Table(  # bridge table (N:M)
    "investigation_indicators", metadata,
    Column("investigation_id", String(20), ForeignKey("investigations.investigation_id"), nullable=False),
    Column("indicator_id", String(16), ForeignKey("fraud_indicators.indicator_id"), nullable=False),
    PrimaryKeyConstraint("investigation_id", "indicator_id"),
)

investigation_events = Table(  # append-only: the app only ever INSERTs here
    "investigation_events", metadata,
    Column("event_id", Integer, primary_key=True, autoincrement=True),
    Column("investigation_id", String(20), ForeignKey("investigations.investigation_id"),
           nullable=False, index=True),
    Column("event_type", String(20), nullable=False),
    Column("from_status", String(20)),
    Column("to_status", String(20)),
    Column("note", Text),
    Column("actor", String(60), nullable=False),
    Column("event_time", String(30), nullable=False),
    _enum_check("investigation_events", "event_type", "investigation_event_type"),
)

LOAD_ORDER = ["claimants", "providers", "policies", "incidents", "claims",
              "claim_status_events", "invoices", "payments", "relationship_edges",
              "quarantine_records"]
WORKFLOW_DELETE_ORDER = ["investigation_events", "investigation_indicators", "investigations",
                         "fraud_indicators", "detection_runs"]
TABLE_COLUMNS = {t.name: [c.name for c in t.columns] for t in metadata.sorted_tables}

# ---------------------------------------------------------------------- engine
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = config.get_database_url()
        kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
        engine = create_engine(url, pool_pre_ping=True, **kwargs)
        if engine.dialect.name == "sqlite":
            @event.listens_for(engine, "connect")
            def _enable_foreign_keys(dbapi_conn, _record):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()
        _engine = engine
    return _engine


def reset_engine() -> None:
    """Used by tests to point at a different database."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def check_connection() -> None:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise DatabaseError(
            f"Could not connect to the {get_engine().dialect.name} database "
            f"({type(exc).__name__}). Check DATABASE_URL in .env or the hosting secrets. "
            "The app will NOT fall back to another database automatically."
        ) from exc


def create_schema() -> None:
    metadata.create_all(get_engine())


def table_counts() -> dict[str, int]:
    with get_engine().connect() as conn:
        return {t.name: conn.execute(select(func.count()).select_from(t)).scalar_one()
                for t in metadata.sorted_tables}


def load_dataset(tables: dict[str, list[dict]], replace: bool = False,
                 wipe_investigations: bool = False) -> None:
    """Insert a generated dataset in ONE transaction. Never overwrites silently."""
    with get_engine().begin() as conn:
        n_claims = conn.execute(select(func.count()).select_from(claims)).scalar_one()
        n_invg = conn.execute(select(func.count()).select_from(investigations)).scalar_one()
        if n_claims and not replace:
            raise DatabaseError("The database already contains data. Re-run with --replace to rebuild it.")
        if n_invg and not wipe_investigations:
            raise DatabaseError(
                f"{n_invg} investigation(s) exist. Rebuilding source data would orphan them. "
                "Re-run with --replace --wipe-investigations only if you really want to erase them.")
        if n_claims or n_invg:
            for name in WORKFLOW_DELETE_ORDER + list(reversed(LOAD_ORDER)):
                conn.execute(delete(metadata.tables[name]))
        for name in LOAD_ORDER:
            rows = tables[name]
            for i in range(0, len(rows), 1000):
                conn.execute(metadata.tables[name].insert(), rows[i:i + 1000])