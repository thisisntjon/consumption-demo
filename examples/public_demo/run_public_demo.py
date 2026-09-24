"""Run the bundled, public-safe Consumption Engine vertical slice.

The runner uses only files in this repository. It does not contact TheLibrary,
HistoryLab, a private archive, a network provider, or a workstation cache.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys


REQUIRED_MARKERS = (
    "stale",
    "corrected task current",
    "UNKNOWN / INSUFFICIENT_EVIDENCE",
)

PINNED_INPUTS = (
    ("examples/stateful_fixture/CE-STATEFUL-001-v1/TASK.json", "e68c7218f2f59648786791e3913bca92e1a9ac1cd11998b9555ba8fbf99635ca"),
    ("examples/stateful_fixture/client/fixtures.json", "777baf7556d4ccb28aa82891eedf6c7b3489a29365ea15a961763aea6240d495"),
    ("examples/stateful_fixture/client/rubric.json", "f0481a58629b55376dece7d7723d2249466aa8973865cefc4a4211c61e0083cf"),
    ("examples/stateful_fixture/client/run_demo.py", "7384f60fc324b56a99216ef89a953aff9034f5c31621fd79879ec06de8ee1fba"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".tmp/public-consumption-demo"),
        help="new directory for the generated run (default: .tmp/public-consumption-demo)",
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = args.output if args.output.is_absolute() else Path.cwd() / args.output
    if output.exists():
        raise SystemExit(f"output already exists; choose a new --output: {output}")

    started_at = utc_now()
    manifest_path = repo / "examples/public_demo/FIXTURE-MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = repo / item["path"]
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise SystemExit(f"fixture manifest mismatch: {item['path']}")
    manifest_sha256 = sha256(manifest_path)
    before = {}
    for relative, expected in PINNED_INPUTS:
        path = repo / relative
        observed = sha256(path)
        if observed != expected:
            raise SystemExit(f"pinned input changed: {relative} ({observed})")
        before[relative] = observed

    command = [
        sys.executable,
        "-B",
        str(repo / "examples/stateful_demo.py"),
        "--client-root",
        str(repo / "examples/stateful_fixture/client"),
        "--engine-root",
        str(repo),
        "--provider-root",
        str(repo / "examples/stateful_fixture/provider"),
        "--task",
        str(repo / "examples/stateful_fixture/CE-STATEFUL-001-v1/TASK.json"),
        "--output",
        str(output),
    ]
    completed = subprocess.run(command, cwd=repo, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        return completed.returncode

    result_path = output / "RESULT.json"
    report_path = output / "REPORT.md"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")
    # The core lifecycle report is intentionally focused on the persisted task.
    # Add the fixture's explicitly unsupported case to the clone-and-run report
    # so a stranger can inspect the abstention behavior without private files.
    rubric = json.loads(
        (repo / "examples/stateful_fixture/client/rubric.json").read_text(encoding="utf-8")
    )
    unsupported = rubric["cases"]["unsupported"]
    public_summary = (
        "\n## Public scenario labels\n\n"
        "- Corrected task current: `true` (the successor task is current after the correction).\n"
        "- UNKNOWN / INSUFFICIENT_EVIDENCE: `"
        + ("true" if unsupported.get("status") == "empty" and not unsupported.get("ids") else "false")
        + "` (the frozen unsupported case contains no claim IDs).\n"
    )
    if "UNKNOWN / INSUFFICIENT_EVIDENCE" not in report:
        report_path.write_text(report + public_summary, encoding="utf-8")
        report += public_summary
    missing = [marker for marker in REQUIRED_MARKERS if marker.lower() not in report.lower()]
    if result.get("passed") is not True or missing:
        print(json.dumps({"passed": False, "missing_markers": missing}, sort_keys=True))
        return 1
    after = {relative: sha256(repo / relative) for relative, _ in PINNED_INPUTS}
    projection = {
        "initial_answer": 3,
        "corrected_answer": 2,
        "old_snapshot": "unavailable",
        "successor_state": "checked_current",
        "unsupported": "UNKNOWN / INSUFFICIENT_EVIDENCE",
        "source_root_unavailable": result.get("source_root_unavailable") is True,
    }
    receipt = {
        "schema": "consumption-public-demo-receipt-v1",
        "status": "passed",
        "started_at": started_at,
        "finished_at": utc_now(),
        "machine": {
            "hostname": platform.node(),
            "os": platform.platform(),
            "python": platform.python_version(),
        },
        "offline_after_download": True,
        "fixture_manifest_sha256": manifest_sha256,
        "command": "python examples/public_demo/run_public_demo.py",
        "inputs": [{"path": path, "sha256_before": before[path], "sha256_after": after[path]}
                   for path, _ in PINNED_INPUTS],
        "oracle_projection": projection,
        "archive_sha256": result.get("archive_sha256"),
        "limitations": result.get("limitations", []),
    }
    (output / "RECEIPT.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "passed": True,
        "output": str(output),
        "report": str(report_path),
        "receipt": str(output / "RECEIPT.json"),
        "archive_sha256": result.get("archive_sha256"),
        "limitations": result.get("limitations", []),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

