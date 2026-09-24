# Independent review checklist

This checklist is for a reviewer who did not author the package. It uses only a
fresh clone and the committed synthetic fixture.

## Run

From the repository root, with Python 3.11 or newer:

```text
python examples/public_demo/run_public_demo.py --output .tmp/review-run-a
python examples/public_demo/run_public_demo.py --output .tmp/review-run-b
python examples/public_demo/verify_receipt.py .tmp/review-run-a/RECEIPT.json --output .tmp/review-run-a/ORACLE-DECISION.json
python examples/public_demo/verify_receipt.py .tmp/review-run-b/RECEIPT.json --output .tmp/review-run-b/ORACLE-DECISION.json
```

Compare the two `oracle_projection` objects. They must match. Confirm both
oracle decisions are `accepted_automated_oracle`.

## Acceptance criteria

Accept the package only if all of these are true:

1. The fixture manifest and all before/after input hashes match `ORACLES.json`.
2. The initial answer is 3 retries and the corrected answer is 2 retries.
3. The old snapshot is `unavailable` after correction.
4. The successor state is `checked_current`.
5. The unsupported question is `UNKNOWN / INSUFFICIENT_EVIDENCE`.
6. The source root is unavailable during restore verification.
7. Both runs produce the same oracle projection.
8. No private path, network share, live provider or workstation cache is needed.

Return a review decision that names the reviewer and session, binds the exact
receipt and oracle hashes, and states the scope. Do not upgrade the result to
scientific truth, production readiness or general efficacy.
