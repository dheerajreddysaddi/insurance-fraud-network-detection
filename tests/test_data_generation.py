import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from src import database
from src.data_generator import SCALES, generate


@pytest.fixture(scope="module")
def ds():
    return generate("starter")


def test_volumes_match_scale(ds):
    cfg = SCALES["starter"]
    assert len(ds.tables["claims"]) == cfg["claims"]
    assert len(ds.tables["claimants"]) == cfg["claimants"]
    assert len(ds.tables["providers"]) == cfg["providers"]
    assert len(ds.tables["relationship_edges"]) == cfg["edges"]


def test_same_seed_is_reproducible():
    a, b = generate("starter", 123), generate("starter", 123)
    assert a.tables == b.tables and a.ground_truth == b.ground_truth


def test_different_seed_differs():
    assert generate("starter", 1).tables["claimants"] != generate("starter", 2).tables["claimants"]


def test_primary_keys_unique(ds):
    keys = {"claimants": "claimant_id", "claims": "claim_id", "policies": "policy_id",
            "invoices": "invoice_id", "payments": "payment_id", "providers": "provider_id"}
    for table, key in keys.items():
        ids = [r[key] for r in ds.tables[table]]
        assert len(ids) == len(set(ids)), table


def test_nonexistent_policy_claims_are_quarantined_not_inserted(ds):
    policy_ids = {p["policy_id"] for p in ds.tables["policies"]}
    assert all(c["policy_id"] in policy_ids for c in ds.tables["claims"])
    assert len(ds.tables["quarantine_records"]) == SCALES["starter"]["quarantined_claims"]


def test_invoices_reconcile_to_claimed_amount(ds):
    totals = {}
    for inv in ds.tables["invoices"]:
        totals[inv["claim_id"]] = totals.get(inv["claim_id"], 0) + inv["amount_cents"]
    assert all(totals[c["claim_id"]] == c["claimed_cents"] for c in ds.tables["claims"])


def test_ground_truth_has_all_required_anomaly_types(ds):
    cols, rows = ds.ground_truth["anomalies"]
    types = {r["issue_type"] for r in rows}
    assert {"CLAIM_NONEXISTENT_POLICY", "PAYMENT_EXCEEDS_APPROVED", "DUPLICATE_INVOICE_ACROSS_CLAIMANTS",
            "PLANTED_EDGE_NOT_IN_OBSERVED_EDGES", "BENIGN_SHARED_ADDRESS"} <= types


def test_database_load_and_foreign_keys_enforced(tmp_path, monkeypatch, ds):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "t.db").as_posix())
    database.reset_engine()
    database.create_schema()
    database.load_dataset(ds.tables)
    assert database.table_counts()["claims"] == len(ds.tables["claims"])
    with pytest.raises(IntegrityError):
        with database.get_engine().begin() as conn:
            conn.execute(insert(database.claims).values(
                claim_id="CLAIM-2026-999999", claimant_id="CLM-2026-000001", policy_id="POL-2026-NOPE",
                incident_id="INC-2026-000001", claim_date="2026-01-01", claimed_cents=100, status="SUBMITTED"))
    with pytest.raises(database.DatabaseError):          # loading twice must not silently overwrite
        database.load_dataset(ds.tables)
    database.reset_engine()