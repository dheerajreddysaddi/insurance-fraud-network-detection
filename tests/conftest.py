import pandas as pd
import pytest

from src import database, fraud_detection, network_analysis
from src.data_generator import generate


@pytest.fixture(scope="session")
def starter_ds():
    return generate("starter")


@pytest.fixture(scope="session")
def starter_tables(starter_ds):
    return {name: pd.DataFrame(rows, columns=database.TABLE_COLUMNS[name]) for name, rows in starter_ds.tables.items()}


@pytest.fixture(scope="session")
def detection(starter_tables):
    rules = fraud_detection.load_rules()
    _, _, indicators = fraud_detection.run_detection(
        starter_tables, rules, run_id="RUN-TEST", detected_at="2026-01-01T00:00:00+00:00")
    return {"rules": rules, "indicators": indicators, **network_analysis.analyze(starter_tables, indicators, rules)}


@pytest.fixture
def db(tmp_path, monkeypatch, starter_ds):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "t.db").as_posix())
    database.reset_engine()
    database.create_schema()
    database.load_dataset(starter_ds.tables)
    yield database
    database.reset_engine()