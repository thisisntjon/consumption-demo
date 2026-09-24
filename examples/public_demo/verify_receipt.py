"""Verify a public-demo receipt against the committed oracle file."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--oracles", type=Path, default=Path(__file__).with_name("ORACLES.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    oracles = json.loads(args.oracles.read_text(encoding="utf-8"))
    expected_inputs = oracles["pinned_inputs"]
    observed_inputs = {item["path"]: item for item in receipt.get("inputs", [])}
    checks = {
        "receipt_passed": receipt.get("status") == "passed",
        "manifest_pin_matches": receipt.get("fixture_manifest_sha256") == oracles["fixture_manifest_sha256"],
        "input_set_matches": set(observed_inputs) == set(expected_inputs),
        "input_hashes_match": all(
            observed_inputs.get(path, {}).get("sha256_before") == expected
            and observed_inputs.get(path, {}).get("sha256_after") == expected
            for path, expected in expected_inputs.items()
        ),
        "oracle_projection_matches": receipt.get("oracle_projection") == oracles["expected_projection"],
        "offline_declared": receipt.get("offline_after_download") is True,
    }
    decision = {
        "schema": "consumption-public-demo-oracle-decision-v1",
        "decision": "accepted_automated_oracle" if all(checks.values()) else "rejected",
        "actor": "automated-public-oracle-verifier",
        "verifier_runtime": {"python": platform.python_version(), "os": platform.platform()},
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "receipt_sha256": digest(args.receipt),
        "oracles_sha256": digest(args.oracles),
        "checks": checks,
        "scope": "exact receipt/oracle identity and declared behavioral projection only",
        "not_proven": ["scientific truth", "semantic entailment", "human acceptance", "production readiness"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(decision, sort_keys=True))
    return 0 if decision["decision"] == "accepted_automated_oracle" else 1


if __name__ == "__main__":
    raise SystemExit(main())
