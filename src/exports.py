"""File exports. Deterministic: fixed column order, LF line endings, no timestamps."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateTable

from src import database
from src.database import LOAD_ORDER, TABLE_COLUMNS


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow(["" if row.get(c) is None else row[c] for c in columns])


def write_tables_csv(tables: dict[str, list[dict]], out_dir: Path) -> None:
    for name, rows in tables.items():
        write_csv(out_dir / f"{name}.csv", TABLE_COLUMNS[name], rows)


def write_ground_truth(ground_truth: dict[str, tuple[list[str], list[dict]]], out_dir: Path) -> None:
    for name, (columns, rows) in ground_truth.items():
        write_csv(out_dir / f"{name}.csv", columns, rows)


def write_tables_json(tables: dict[str, list[dict]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        ordered = [{c: r.get(c) for c in TABLE_COLUMNS[name]} for r in rows]
        text = json.dumps(ordered, indent=1, ensure_ascii=False) + "\n"
        (out_dir / f"{name}.json").write_bytes(text.encode("utf-8"))   # bytes: no newline translation on Windows


def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def write_sql_seed(tables: dict[str, list[dict]], path: Path) -> None:
    """A self-contained SQLite script: schema (CREATE TABLE) + INSERTs in foreign-key order."""
    lines = ["-- Synthetic insurance-fraud data. Generated locally; contains no real personal data.",
             "PRAGMA foreign_keys=ON;"]
    for table in database.metadata.sorted_tables:
        lines.append(str(CreateTable(table).compile(dialect=sqlite.dialect())).strip() + ";")
    lines.append("BEGIN;")
    for name in LOAD_ORDER:
        cols = TABLE_COLUMNS[name]
        for row in tables[name]:
            values = ", ".join(sql_literal(row.get(c)) for c in cols)
            lines.append(f"INSERT INTO {name} ({', '.join(cols)}) VALUES ({values});")
    lines.append("COMMIT;")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))