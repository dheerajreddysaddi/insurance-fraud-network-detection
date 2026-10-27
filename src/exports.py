"""File exports. Deterministic: fixed column order, LF line endings, no timestamps."""
from __future__ import annotations

import csv
from pathlib import Path

from src.database import TABLE_COLUMNS


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