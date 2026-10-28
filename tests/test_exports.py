import json
import sqlite3

from src import exports
from src.database import TABLE_COLUMNS


def test_json_export_round_trips(tmp_path, starter_ds):
    exports.write_tables_json(starter_ds.tables, tmp_path)
    for name in ("claims", "payments", "quarantine_records"):
        loaded = json.loads((tmp_path / f"{name}.json").read_text(encoding="utf-8"))
        expected = [{c: r.get(c) for c in TABLE_COLUMNS[name]} for r in starter_ds.tables[name]]
        assert loaded == expected


def test_sql_seed_loads_into_sqlite_with_valid_foreign_keys(tmp_path, starter_ds):
    path = tmp_path / "seed.sql"
    exports.write_sql_seed(starter_ds.tables, path)
    con = sqlite3.connect(":memory:")
    con.executescript(path.read_text(encoding="utf-8"))
    for name in ("claims", "invoices", "payments", "relationship_edges"):
        count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        assert count == len(starter_ds.tables[name]), name
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def test_exports_are_byte_identical_for_same_data(tmp_path, starter_ds):
    for folder in ("a", "b"):
        exports.write_sql_seed(starter_ds.tables, tmp_path / folder / "seed.sql")
        exports.write_tables_csv(starter_ds.tables, tmp_path / folder)
    assert (tmp_path / "a" / "seed.sql").read_bytes() == (tmp_path / "b" / "seed.sql").read_bytes()
    assert (tmp_path / "a" / "claims.csv").read_bytes() == (tmp_path / "b" / "claims.csv").read_bytes()