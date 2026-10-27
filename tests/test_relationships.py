import pandas as pd
import pytest

from src import evaluation
from src.validators import run_validation


@pytest.fixture(scope="module")
def expected(starter_ds):
    return evaluation.expected_exceptions(evaluation.gt_from_generated(starter_ds.ground_truth))


def check(report, name):
    return next(c for c in report["checks"] if c["check"] == name)


def test_clean_data_has_no_unexpected_failures(starter_tables, expected):
    report = run_validation(starter_tables, expected, seed=20261022)
    bad = [c for c in report["checks"] if c["unexpected"]]
    assert bad == [], bad


def test_planted_anomalies_reported_as_expected(starter_tables, expected):
    exp = run_validation(starter_tables, expected)["expected_exceptions"]
    for name in ("finance:payment_exceeds_approved", "finance:duplicate_invoice_across_claimants",
                 "edges:attribute_pair_missing", "quarantine:claim_nonexistent_policy"):
        assert exp.get(name, 0) > 0, name


def test_without_answer_key_planted_anomalies_show_as_unexpected(starter_tables):
    assert run_validation(starter_tables, None)["unexpected_failures"] > 0


def _copy(tables, name):
    t = dict(tables)
    t[name] = tables[name].copy()
    return t, t[name]


def test_detects_foreign_key_violation(starter_tables, expected):
    t, claims = _copy(starter_tables, "claims")
    claims.loc[0, "policy_id"] = "POL-2026-NOPE"
    assert check(run_validation(t, expected), "fk:claims.policy_id")["unexpected"] == 1


def test_detects_duplicate_primary_key(starter_tables, expected):
    t, claims = _copy(starter_tables, "claims")
    t["claims"] = pd.concat([claims, claims.iloc[[0]]], ignore_index=True)
    assert check(run_validation(t, expected), "pk:claims")["unexpected"] == 1


def test_detects_invalid_enum(starter_tables, expected):
    t, claims = _copy(starter_tables, "claims")
    claims.loc[0, "status"] = "BOGUS"
    assert check(run_validation(t, expected), "enum:claims.status")["unexpected"] == 1


def test_detects_payment_before_invoice(starter_tables, expected):
    t, pay = _copy(starter_tables, "payments")
    pay.loc[0, "payment_date"] = "1999-01-01"
    assert check(run_validation(t, expected), "order:payment_before_invoice")["unexpected"] >= 1


def test_detects_invoice_total_mismatch(starter_tables, expected):
    t, inv = _copy(starter_tables, "invoices")
    inv.loc[0, "amount_cents"] += 100
    assert check(run_validation(t, expected), "finance:invoice_total_vs_claimed")["unexpected"] == 1