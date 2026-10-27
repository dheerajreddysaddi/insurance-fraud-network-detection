import pytest

from src import evaluation


def test_metrics_known_values():
    m = evaluation.metrics(tp=8, fp=2, fn=2, tn=88)
    assert m["precision"] == pytest.approx(0.8) and m["recall"] == pytest.approx(0.8)
    assert m["f1"] == pytest.approx(0.8)
    assert m["fpr"] == pytest.approx(2 / 90) and m["fnr"] == pytest.approx(0.2)


def test_zero_division_returns_none_not_crash():
    m = evaluation.metrics(0, 0, 0, 10)
    assert m["precision"] is None and m["recall"] is None and m["f1"] is None
    assert evaluation.metrics(0, 3, 4, 10)["f1"] == 0.0


@pytest.fixture(scope="module")
def result(detection, starter_ds):
    gt = evaluation.gt_from_generated(starter_ds.ground_truth)
    return evaluation.evaluate_all(detection["claim_scores"], detection["networks"], detection["indicators"], gt)


def test_confusion_matrix_covers_every_claim(result, starter_ds):
    for key in ("claims_rules_only", "claims_rules_plus_network"):
        m = result[key]
        assert m["tp"] + m["fp"] + m["fn"] + m["tn"] == len(starter_ds.tables["claims"])
        assert m["tp"] + m["fn"] == result["n_suspicious_claims"]


def test_network_analysis_does_not_reduce_recall(result):
    assert result["claims_rules_plus_network"]["recall"] >= result["claims_rules_only"]["recall"]


def test_planted_networks_are_recovered_and_rank_highly(result):
    n = result["networks"]
    assert n["recovered"] >= 2 and n["recovered"] / n["planted"] >= 0.66
    assert n["precision_at_k"][f"P@{n['planted']}"] >= 0.66


def test_injected_exceptions_are_detected(result):
    ex = result["exceptions"].set_index("issue_type")
    for issue in ("PAYMENT_EXCEEDS_APPROVED", "CLAIM_NONEXISTENT_POLICY",
                  "DUPLICATE_INVOICE_ACROSS_CLAIMANTS", "PLANTED_EDGE_NOT_IN_OBSERVED_EDGES"):
        assert ex.loc[issue, "recall"] == 1.0, issue
    assert ex.loc["BENIGN_SHARED_ADDRESS", "recall"] == 1.0