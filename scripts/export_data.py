"""Generate a dataset and write CSV + JSON + SQL seed + ground truth, WITHOUT touching any database."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, exports  # noqa: E402
from src.constants import DEFAULT_SEED  # noqa: E402
from src.data_generator import SCALES, generate  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Export synthetic data as CSV, JSON and SQL.")
    ap.add_argument("--scale", choices=list(SCALES), default="full")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out-dir", type=Path, default=config.GENERATED_DIR)
    ap.add_argument("--gt-dir", type=Path, default=config.GROUND_TRUTH_DIR,
                    help="ground-truth files go here; they must match the data in your database")
    args = ap.parse_args()

    ds = generate(args.scale, args.seed)
    exports.write_tables_csv(ds.tables, args.out_dir)
    exports.write_tables_json(ds.tables, args.out_dir / "json")
    exports.write_sql_seed(ds.tables, args.out_dir / "seed.sql")
    exports.write_ground_truth(ds.ground_truth, args.gt_dir)
    print(f"Exported scale={args.scale} seed={args.seed} to {args.out_dir} (ground truth: {args.gt_dir})")


if __name__ == "__main__":
    main()