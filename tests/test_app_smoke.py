from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import fraud_detection

APP = Path(__file__).resolve().parent.parent / "app.py"
PAGES = ["Overview", "Claims Explorer", "Network Analysis", "Fraud Indicators & Exceptions",
         "Investigation Workspace", "Evaluation"]


@pytest.fixture
def seeded_db(db):
    rules = fraud_detection.load_rules()
    run_id, at, indicators = fraud_detection.run_detection(db.read_tables(), rules)
    fraud_detection.save_run(run_id, at, rules, indicators)
    return db


def test_every_page_renders_without_exceptions(seeded_db):
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception
    for page in PAGES:
        at.session_state["page"] = page
        at.run()
        assert not at.exception, page