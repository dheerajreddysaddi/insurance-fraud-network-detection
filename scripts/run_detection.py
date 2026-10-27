"""Run detection on the database, save indicators, rank networks, and (optionally) evaluate."""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import database, evaluation, fraud_detection, network_analysis  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Run fraud detection.")
    ap.add_argument("--no-eval", action="store_true", help="skip comparison with the answer key")
    ap.add_argument("--gt-dir", type=Path, default=None)
    args = ap.parse_args()

    database.check_connection()
    tables = database.read_tables()
    if tables["claims"].empty:
        sys.exit("No data found. Run: python scripts/generate_data.py --scale full --replace")

    rules = fraud_detection.load_rules()
    run_id, detected_at, indicators = fraud_detection.run_detection(tables, rules)   # answer key NOT loaded yet
    fraud_detection.save_run(run_id, detected_at, rules, indicators)
    result = network_analysis.analyze(tables, indicators, rules)

    print(f"Run {run_id}: {len(indicators)} indicators saved (rules hash {fraud_detection.rules_hash(rules)})")
    for itype, n in sorted(Counter(i["indicator_type"] for i in indicators).items()):
        print(f"  {itype:<38}{n:>6}")
    cs, nets = result["claim_scores"], result["networks"]
    print(f"\nFlagged claims: {int(cs['flagged'].sum())} of {len(cs)} "
          f"(rules alone: {int(cs['rule_flagged'].sum())})")
    print(f"Networks: {len(nets)} connected groups, {int(nets['flagged'].sum()) if len(nets) else 0} flagged")
    for r in nets[nets["flagged"]].head(5).itertuples():
        print(f"\n#{r.rank} {r.network_id} score={r.network_score} priority={r.priority}\n   {r.explanation}")

    if not args.no_eval:
        try:
            gt = evaluation.load_ground_truth(args.gt_dir)
        except FileNotFoundError as exc:
            print(f"\nSkipping evaluation: {exc}")
            return
        print("\n" + evaluation.format_report(
            evaluation.evaluate_all(cs, nets, indicators, gt)))


if __name__ == "__main__":
    main()