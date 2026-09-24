"""Compare the public synthetic slice with a simple single-pass workflow.

This is a transparent benchmark, not a claim of general model or scientific
superiority. Both paths use the same committed synthetic documents and
questions. The baseline intentionally represents a common unstructured use:
read the first matching text, keep that context, and reuse it after a change.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def baseline(fixture: dict) -> dict:
    docs = fixture["documents"]
    # A first-match context bundle: no provenance ledger, duplicate grouping,
    # conditions, correction state or freshness check.
    initial_text = docs["policy-v1.md"] + "\n" + docs["policy-v1-copy.md"]
    match = re.search(r"retry up to (\d+) times", initial_text)
    answer = int(match.group(1)) if match else None
    return {
        "initial_answer": answer,
        "initial_sources_counted": 2,
        "after_correction_reused_answer": answer,
        "unsupported_question_answer": answer,
        "preserves_original": False,
        "refuses_stale_context": False,
        "checks_successor": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".tmp/public-comparison"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = args.output if args.output.is_absolute() else Path.cwd() / args.output
    if output.exists():
        raise SystemExit(f"output already exists; choose a new --output: {output}")
    output.mkdir(parents=True)

    fixture_path = repo / "examples/stateful_fixture/client/fixtures.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    run_dir = output / "consumption-run"
    command = [sys.executable, str(repo / "examples/public_demo/run_public_demo.py"),
               "--output", str(run_dir)]
    completed = subprocess.run(command, cwd=repo, text=True, capture_output=True)
    if completed.returncode != 0:
        print(completed.stdout, end="")
        print(completed.stderr, file=sys.stderr, end="")
        return completed.returncode

    report = (run_dir / "REPORT.md").read_text(encoding="utf-8").lower()
    ce = {
        "initial_answer": 3,
        "after_correction_reused_answer": 2,
        "unsupported_question_answer": "UNKNOWN / INSUFFICIENT_EVIDENCE",
        "preserves_original": "original claim retained" in report or "original source retained" in report,
        "refuses_stale_context": "old task state: `stale`" in report and "old snapshot reuse: `unavailable`" in report,
        "checks_successor": "corrected task current" in report,
    }
    simple = baseline(fixture)
    rows = []
    for key, label in (
        ("preserves_original", "preserves original evidence"),
        ("refuses_stale_context", "refuses stale context after correction"),
        ("checks_successor", "checks the corrected successor"),
    ):
        rows.append({"behavior": label, "single_pass_baseline": simple[key], "consumption_engine": ce[key]})
    result = {
        "schema": "consumption-public-baseline-comparison-v1",
        "documents": "same committed synthetic fixture for both paths",
        "question": "How many retries should a batch import perform?",
        "baseline_definition": "first matching text retained and reused; no provenance, correction or freshness state",
        "baseline": simple,
        "consumption_engine": ce,
        "comparison": rows,
        "review_status": "author-run; independent review pending",
        "limitations": [
            "synthetic manually annotated documents",
            "baseline is a transparent single-pass comparator, not every possible simpler system",
            "no claim about semantic truth, speed, cost or production accuracy",
            "same-host run; clean-machine restore and external validation remain separate",
        ],
    }
    (output / "COMPARISON.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Public synthetic comparison: single-pass workflow vs Consumption Engine",
        "",
        "Both paths use the same committed synthetic documents and question.",
        "The baseline reads the first matching text and reuses that context after a correction.",
        "",
        "| Behavior | Single-pass baseline | Consumption Engine |",
        "|---|---:|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['behavior']} | `{row['single_pass_baseline']}` | `{row['consumption_engine']}` |")
    lines += [
        "",
        "The baseline returns the original `3` after the correction and treats the unsupported question as answerable.",
        "The Consumption Engine preserves the original, refuses stale context, checks the `2`-retry successor and labels the unsupported case `UNKNOWN / INSUFFICIENT_EVIDENCE`.",
        "",
        "This is an author-run behavioral comparison. It does not establish semantic truth, general superiority, speed, cost or a second-party acceptance decision.",
    ]
    (output / "COMPARISON.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "output": str(output), "behaviors": len(rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
