"""Regenerate the dataset twice in SEPARATE processes with the same seed and compare file checksums."""
import argparse
import hashlib
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def digest_tree(root: Path, prefix: str) -> dict:
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            out[f"{prefix}/{path.relative_to(root).as_posix()}"] = (hashlib.sha256(data).hexdigest(), data.count(b"\n"))
    return out


def run_once(scale: str, seed: int, base: Path) -> dict:
    out, gt = base / "generated", base / "ground_truth"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_data.py"), "--scale", scale, "--seed", str(seed),
                    "--out-dir", str(out), "--gt-dir", str(gt)],
                   check=True, stdout=subprocess.DEVNULL, cwd=ROOT)
    return {**digest_tree(out, "generated"), **digest_tree(gt, "ground_truth")}


def main() -> None:
    ap = argparse.ArgumentParser(description="Check that the same seed gives byte-identical output.")
    ap.add_argument("--scale", default="full", choices=["starter", "full"])
    ap.add_argument("--seed", type=int, default=20261022)
    ap.add_argument("--report", type=Path, default=ROOT / "docs" / "reproducibility_report.md")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        first, second = run_once(args.scale, args.seed, Path(a)), run_once(args.scale, args.seed, Path(b))

    rows, ok = [], True
    for name in sorted(first):
        same = first[name] == second.get(name)
        ok &= same
        rows.append(f"| {name} | {first[name][1]} | {first[name][0][:16]} | {second.get(name, ('missing',))[0][:16]} "
                    f"| {'yes' if same else 'NO'} |")
    ok &= set(first) == set(second)
    text = (f"# Reproducibility report\n\n- Scale: {args.scale}\n- Seed: {args.seed}\n"
            f"- Checked at (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
            "(report metadata only; it is not part of the generated data)\n"
            f"- Result: **{'IDENTICAL' if ok else 'MISMATCH'}** ({len(first)} files, two separate runs)\n\n"
            "| File | Lines | SHA-256 run 1 (first 16) | SHA-256 run 2 (first 16) | Same |\n|---|---:|---|---|---|\n"
            + "\n".join(rows) + "\n")
    args.report.parent.mkdir(exist_ok=True)
    args.report.write_text(text, encoding="utf-8")
    print(text)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()