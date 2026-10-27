import pytest

from src import fraud_detection
from src.investigations import (InvestigationError, add_note, change_status, get_investigation,
                                list_investigations, open_investigation)


def first_claim(db):
    return db.read_tables(["claims"])["claims"]["claim_id"].iloc[0]


def test_open_creates_event_and_blocks_duplicate_subject(db):
    claim = first_claim(db)
    inv_id = open_investigation("CLAIM", claim, "HIGH", "analyst1", note="flagged by rules")
    assert inv_id == "INVG-2026-000001"
    detail = get_investigation(inv_id)
    assert detail["summary"]["current_status"] == "OPEN"
    assert list(detail["events"]["event_type"]) == ["OPENED"]
    with pytest.raises(InvestigationError):
        open_investigation("CLAIM", claim, "HIGH", "analyst2")


def test_full_lifecycle_keeps_append_only_history(db):
    inv_id = open_investigation("CLAIM", first_claim(db), "MEDIUM", "a1")
    change_status(inv_id, "IN_REVIEW", "a1", "started")
    add_note(inv_id, "a1", "called the provider")
    change_status(inv_id, "ESCALATED", "a1", "needs senior review")
    change_status(inv_id, "CLOSED_ACTION_TAKEN", "boss", "claim denied")
    ev = get_investigation(inv_id)["events"]
    assert list(ev["event_type"]) == ["OPENED", "STATUS_CHANGE", "NOTE", "STATUS_CHANGE", "DECISION"]
    assert get_investigation(inv_id)["summary"]["current_status"] == ev["to_status"].dropna().iloc[-1]


def test_invalid_transition_rejected_and_nothing_recorded(db):
    inv_id = open_investigation("CLAIM", first_claim(db), "LOW", "a1")
    with pytest.raises(InvestigationError):
        change_status(inv_id, "CLOSED_ACTION_TAKEN", "a1", "skipping review")
    assert len(get_investigation(inv_id)["events"]) == 1


def test_closing_requires_note_and_closed_is_terminal(db):
    inv_id = open_investigation("CLAIM", first_claim(db), "LOW", "a1")
    change_status(inv_id, "IN_REVIEW", "a1")
    with pytest.raises(InvestigationError):
        change_status(inv_id, "CLOSED_NO_ACTION", "a1", "  ")
    change_status(inv_id, "CLOSED_NO_ACTION", "a1", "benign household")
    with pytest.raises(InvestigationError):
        change_status(inv_id, "IN_REVIEW", "a1", "reopen")


def test_stale_view_is_rejected(db):
    inv_id = open_investigation("CLAIM", first_claim(db), "LOW", "a1")
    change_status(inv_id, "IN_REVIEW", "a1")
    with pytest.raises(InvestigationError):
        change_status(inv_id, "ESCALATED", "a2", "x", expected_status="OPEN")


def test_survives_restart_and_source_reload_cannot_erase_it(db, starter_ds):
    inv_id = open_investigation("CLAIM", first_claim(db), "HIGH", "a1")
    db.reset_engine()                                   # simulates restarting the app
    assert inv_id in set(list_investigations()["investigation_id"])
    with pytest.raises(db.DatabaseError):
        db.load_dataset(starter_ds.tables, replace=True)


def test_indicators_are_linked_through_bridge_table(db, starter_tables):
    rules = fraud_detection.load_rules()
    tables = db.read_tables()
    run_id, at, inds = fraud_detection.run_detection(tables, rules)
    fraud_detection.save_run(run_id, at, rules, inds)
    _, loaded = fraud_detection.indicators_from_db()
    assert len(loaded) == len(inds)
    pick = next(i for i in loaded if i["indicator_type"] == "UNUSUAL_TIMING")
    inv_id = open_investigation("CLAIM", pick["claim_id"], "HIGH", "a1", [pick["indicator_id"]])
    assert list(get_investigation(inv_id)["indicators"]["indicator_id"]) == [pick["indicator_id"]]