"""Investigation workflow. Append-only history; every change is one transaction."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import and_, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from src import database
from src.constants import ENUMS, YEAR
from src.database import (claims, fraud_indicators, get_engine, investigation_events,
                          investigation_indicators, investigations)

ALLOWED_TRANSITIONS = {
    "OPEN": {"IN_REVIEW", "CLOSED_NO_ACTION"},
    "IN_REVIEW": {"ESCALATED", "CLOSED_NO_ACTION", "CLOSED_ACTION_TAKEN"},
    "ESCALATED": {"IN_REVIEW", "CLOSED_NO_ACTION", "CLOSED_ACTION_TAKEN"},
    "CLOSED_NO_ACTION": set(),          # closed states are terminal
    "CLOSED_ACTION_TAKEN": set(),
}


class InvestigationError(ValueError):
    """A rule was broken (bad transition, duplicate subject, stale view). Message is safe to show the user."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require(value, label):
    if not value or not str(value).strip():
        raise InvestigationError(f"{label} is required.")


def _next_id(conn) -> str:
    last = conn.execute(select(func.max(investigations.c.investigation_id))).scalar()
    n = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"INVG-{YEAR}-{n:06d}"


def find_by_subject(subject_type, subject_id):
    with get_engine().connect() as conn:
        return conn.execute(select(investigations.c.investigation_id).where(and_(
            investigations.c.subject_type == subject_type, investigations.c.subject_id == subject_id))).scalar()


def open_investigation(subject_type, subject_id, priority, opened_by, indicator_ids=(), note=None) -> str:
    if subject_type not in ENUMS["subject_type"]:
        raise InvestigationError(f"subject_type must be one of {ENUMS['subject_type']}.")
    if priority not in ENUMS["severity"]:
        raise InvestigationError(f"priority must be one of {ENUMS['severity']}.")
    _require(subject_id, "subject_id")
    _require(opened_by, "reviewer name")
    indicator_ids = sorted(set(indicator_ids))
    for attempt in range(5):                       # retry only if two users grab the same new id
        try:
            with get_engine().begin() as conn:
                existing = conn.execute(select(investigations.c.investigation_id).where(and_(
                    investigations.c.subject_type == subject_type,
                    investigations.c.subject_id == subject_id))).scalar()
                if existing:
                    raise InvestigationError(f"{subject_type} {subject_id} already has investigation {existing}.")
                if subject_type == "CLAIM" and conn.execute(
                        select(claims.c.claim_id).where(claims.c.claim_id == subject_id)).first() is None:
                    raise InvestigationError(f"Claim {subject_id} does not exist.")
                if indicator_ids:
                    found = conn.execute(select(func.count()).select_from(fraud_indicators).where(
                        fraud_indicators.c.indicator_id.in_(indicator_ids))).scalar_one()
                    if found != len(indicator_ids):
                        raise InvestigationError("One or more indicator ids do not exist.")
                new_id, now = _next_id(conn), _now()
                conn.execute(insert(investigations).values(
                    investigation_id=new_id, subject_type=subject_type, subject_id=subject_id, priority=priority,
                    opened_by=opened_by.strip(), opened_at=now, current_status="OPEN"))
                if indicator_ids:
                    conn.execute(insert(investigation_indicators),
                                 [{"investigation_id": new_id, "indicator_id": i} for i in indicator_ids])
                conn.execute(insert(investigation_events).values(
                    investigation_id=new_id, event_type="OPENED", from_status=None, to_status="OPEN",
                    note=(note or "").strip() or None, actor=opened_by.strip(), event_time=now))
            return new_id
        except IntegrityError:
            if attempt == 4:
                raise InvestigationError("Could not create the investigation because of a concurrent change. Try again.")
    raise AssertionError("unreachable")


def change_status(investigation_id, new_status, actor, note="", expected_status=None) -> None:
    _require(actor, "reviewer name")
    if new_status not in ENUMS["investigation_status"]:
        raise InvestigationError(f"Unknown status {new_status}.")
    closing = new_status.startswith("CLOSED")
    if closing and not (note or "").strip():
        raise InvestigationError("A note explaining the decision is required when closing an investigation.")
    with get_engine().begin() as conn:
        row = conn.execute(select(investigations.c.current_status).where(
            investigations.c.investigation_id == investigation_id).with_for_update()).first()
        if row is None:
            raise InvestigationError(f"Investigation {investigation_id} does not exist.")
        current = row[0]
        if expected_status is not None and expected_status != current:
            raise InvestigationError(f"Status is now {current}; someone else changed it. Refresh and try again.")
        if new_status not in ALLOWED_TRANSITIONS[current]:
            allowed = ", ".join(sorted(ALLOWED_TRANSITIONS[current])) or "none (closed)"
            raise InvestigationError(f"Cannot move from {current} to {new_status}. Allowed: {allowed}.")
        result = conn.execute(update(investigations).where(and_(
            investigations.c.investigation_id == investigation_id,
            investigations.c.current_status == current)).values(current_status=new_status))
        if result.rowcount != 1:
            raise InvestigationError("The investigation was changed at the same time. Refresh and try again.")
        conn.execute(insert(investigation_events).values(
            investigation_id=investigation_id, event_type="DECISION" if closing else "STATUS_CHANGE",
            from_status=current, to_status=new_status, note=(note or "").strip() or None,
            actor=actor.strip(), event_time=_now()))


def add_note(investigation_id, actor, note) -> None:
    _require(actor, "reviewer name")
    _require(note, "note")
    with get_engine().begin() as conn:
        if conn.execute(select(investigations.c.investigation_id).where(
                investigations.c.investigation_id == investigation_id)).first() is None:
            raise InvestigationError(f"Investigation {investigation_id} does not exist.")
        conn.execute(insert(investigation_events).values(
            investigation_id=investigation_id, event_type="NOTE", from_status=None, to_status=None,
            note=note.strip(), actor=actor.strip(), event_time=_now()))


def list_investigations() -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(select(investigations).order_by(
            investigations.c.opened_at.desc(), investigations.c.investigation_id.desc()), conn)


def get_investigation(investigation_id) -> dict:
    """{'summary': dict, 'indicators': DataFrame, 'events': DataFrame}"""
    with get_engine().connect() as conn:
        summary = pd.read_sql(select(investigations).where(
            investigations.c.investigation_id == investigation_id), conn)
        if summary.empty:
            raise InvestigationError(f"Investigation {investigation_id} does not exist.")
        inds = pd.read_sql(
            select(fraud_indicators).join(investigation_indicators,
                                          fraud_indicators.c.indicator_id == investigation_indicators.c.indicator_id)
            .where(investigation_indicators.c.investigation_id == investigation_id)
            .order_by(fraud_indicators.c.indicator_id), conn)
        events = pd.read_sql(select(investigation_events).where(
            investigation_events.c.investigation_id == investigation_id)
            .order_by(investigation_events.c.event_id), conn)
    return {"summary": summary.iloc[0].to_dict(), "indicators": inds, "events": events}