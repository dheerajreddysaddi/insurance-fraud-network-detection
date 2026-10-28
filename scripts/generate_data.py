"""Generate a dataset, write CSV + ground-truth files, and load it into the configured database."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, database, exports  # noqa: E402
from src.constants import DEFAULT_SEED  # noqa: E402
from src.data_generator import SCALES, generate  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic insurance-fraud data.")
    ap.add_argument("--scale", choices=list(SCALES), default="starter")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--replace", action="store_true", help="rebuild source tables if data already exists")
    ap.add_argument("--wipe-investigations", action="store_true",
                    help="ALSO erase investigations (required if any exist)")
    ap.add_argument("--skip-db", action="store_true", help="only write CSV/ground-truth files")
    ap.add_argument("--csv-dir", type=Path, default=config.GENERATED_DIR)
    args = ap.parse_args()

    ds = generate(args.scale, args.seed)
    exports.write_tables_csv(ds.tables, args.csv_dir)
    exports.write_ground_truth(ds.ground_truth, config.GROUND_TRUTH_DIR)
    print(f"Generated scale={args.scale} seed={args.seed}")
    for name, rows in ds.tables.items():
        print(f"  {name:<22}{len(rows):>7}")

    if not args.skip_db:
        import time
        t0 = time.time()


        def lap(msg):
            print(f"  [{time.time() - t0:6.1f}s] {msg}", flush=True)
        database.check_connection()
        lap("connected")
        database.create_schema()
        lap("schema ready")
        database.load_dataset(ds.tables, replace=args.replace, wipe_investigations=args.wipe_investigations,progress=True)
        lap("all tables loaded")
        print("Loaded into database.")


if __name__ == "__main__":
    main()