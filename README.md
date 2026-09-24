# Consumption Engine: public fixture

This repository contains the public, synthetic vertical-slice fixture for the Consumption Engine. It is deliberately small and self-contained so a stranger can inspect the complete behavior without access to a private workstation, TheLibrary, HistoryLab, or a network service.

## Run it

Requires Python 3.11 or newer.

```text
python examples/public_demo/run_public_demo.py --output .tmp/public-demo-run
python examples/public_demo/verify_receipt.py .tmp/public-demo-run/RECEIPT.json --output .tmp/public-demo-run/ORACLE-DECISION.json
```

Run the first command twice with different output directories. The generated report shows the original answer, duplicate handling, correction, stale-context refusal, checked successor, explicit insufficient-evidence result, and offline restore check. `ORACLE-DECISION.json` verifies the declared fixture projection and byte pins.

For the matched baseline comparison:

```text
python examples/public_demo/compare_baseline.py --output .tmp/public-comparison
```

The comparison is a bounded author-run demonstration on the same fixture. It does not claim scientific truth, general superiority, or human acceptance.

## Scope

The fixture is synthetic and manually annotated. It demonstrates reproducible behavior and evidence lineage. It does not certify the truth of the fictional policy, automatic claim extraction, production readiness, or a physical clean-machine restore.

See [`examples/public_demo/README.md`](examples/public_demo/README.md) for the full scenario and review steps.
