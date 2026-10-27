from pathlib import Path

import pandas as pd

from src import fraud_detection
from src.fraud_detection import IndicatorFactory, detect_payment_exceeds, detect_similar_narratives

SRC = Path(__file__).resolve().parent.parent / "src"


def _make(rules):
    return IndicatorFactory("RUN-T", "2026-01-01T00:00:00+00:00", rules)


def test_all_expected_indicator_types_present(detection):
    types = {i["indicator_type"] for i in detection["indicators"]}
    assert {"SHARED_PHONE", "SHARED_EMAIL", "SIMILAR_NARRATIVE", "DUPLICATE_INVOICE_ACROSS_CLAIMANTS",
            "PAYMENT_EXCEEDS_APPROVED", "DATA_INTEGRITY_VIOLATION", "MISSING_RELATIONSHIP_EDGE",
            "BENIGN_SHARED_ADDRESS", "UNUSUAL_TIMING"} <= types


def test_indicator_fields_valid_and_ids_unique(detection):
    ids = [i["indicator_id"] for i in detection["indicators"]]
    assert len(ids) == len(set(ids))
    for i in detection["indicators"]:
        assert i["severity"] in ("LOW", "MEDIUM", "HIGH") and i["score"] >= 0
        assert i["explanation"] and i["rule_description"] and i["related_entities"]


def test_benign_households_get_score_zero_and_no_contact_indicator(detection, starter_ds):
    benign = {r["claimant_id"] for r in starter_ds.ground_truth["benign_groups"][1]}
    assert all(i["score"] == 0 for i in detection["indicators"] if i["indicator_type"] == "BENIGN_SHARED_ADDRESS")
    for i in detection["indicators"]:
        if i["indicator_type"] in ("SHARED_PHONE", "SHARED_EMAIL"):
            assert not benign & set(i["related_entities"])


def test_detection_is_deterministic(starter_tables, detection):
    _, _, again = fraud_detection.run_detection(
        starter_tables, detection["rules"], run_id="RUN-TEST", detected_at="2026-01-01T00:00:00+00:00")
    assert again == detection["indicators"]


def test_detector_source_never_touches_answer_key():
    for name in ("fraud_detection.py", "network_analysis.py"):
        text = (SRC / name).read_text(encoding="utf-8")
        for forbidden in ("ground_truth", "claim_labels", "is_suspicious"):
            assert forbidden not in text, (name, forbidden)


def test_payment_exactly_at_approved_is_not_flagged_but_one_rupee_over_is():
    rules = fraud_detection.load_rules()
    claims = pd.DataFrame({"claim_id": ["CLAIM-1", "CLAIM-2"], "approved_cents": [10000, 10000]})
    pay = pd.DataFrame({"claim_id": ["CLAIM-1", "CLAIM-2"], "amount_cents": [10000, 10100]})
    out = detect_payment_exceeds({"claims": claims, "payments": pay}, rules, _make(rules))
    assert [i["entity_id"] for i in out] == ["CLAIM-2"]


def test_identical_narratives_flagged_only_across_different_claimants():
    rules = fraud_detection.load_rules()
    text = "Policyholder reported a vehicle collision at Adyar near the railway station in clear conditions"
    incidents = pd.DataFrame({"incident_id": ["I1", "I2", "I3"], "incident_type": ["COLLISION"] * 3,
                              "incident_date": ["2026-01-01"] * 3, "narrative": [text, text, "Totally different story about hail"]})
    same = pd.DataFrame({"claim_id": ["C1", "C2", "C3"], "claimant_id": ["A", "A", "B"], "incident_id": ["I1", "I2", "I3"]})
    assert detect_similar_narratives({"claims": same, "incidents": incidents}, rules, _make(rules)) == []
    diff = same.assign(claimant_id=["A", "B", "C"])
    out = detect_similar_narratives({"claims": diff, "incidents": incidents}, rules, _make(rules))
    assert len(out) == 1 and set(out[0]["evidence"]["claims"]) == {"C1", "C2"}


def test_flagged_networks_meet_documented_thresholds(detection):
    nets, rules = detection["networks"], detection["rules"]["networks"]
    flagged = nets[nets["flagged"]]
    assert len(flagged) >= 1
    assert (flagged["network_score"] >= rules["network_flag_threshold"]).all()
    assert (flagged["n_claimants"] >= 2).all()
    cs = detection["claim_scores"]
    members = set().union(*flagged["claim_ids"])
    assert cs[cs["claim_id"].isin(members)]["flagged"].all()