"""Validate the database (default) or the exported CSV files and write a validation summary."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, database, evaluation, validators  # noqa: E402
from src.constants import DEFAULT_SEED  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate generated data.")
    ap.add_argument("--source", choices=["db", "csv"], default="db")
    ap.add_argument("--csv-dir", type=Path, default=config.GENERATED_DIR)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="seed to print in the summary")
    args = ap.parse_args()

    if args.source == "db":
        database.check_connection()
        tables = database.read_tables()
    else:
        tables = validators.read_csv_tables(args.csv_dir)
    expected = None
    try:
        expected = evaluation.expected_exceptions(evaluation.load_ground_truth())
    except FileNotFoundError:
        print("WARNING: ground-truth files not found; planted anomalies will show as UNEXPECTED.")

    report = validators.run_validation(tables, expected, args.seed)
    md = validators.format_markdown(report)
    (config.ROOT_DIR / "docs").mkdir(exist_ok=True)
    (config.ROOT_DIR / "docs" / "validation_summary.md").write_text(md, encoding="utf-8")
    config.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    (config.GENERATED_DIR / "validation_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(md)
    sys.exit(1 if report["unexpected_failures"] else 0)


if __name__ == "__main__":
    main()