# Consumption Engine: historical fixture

> **Superseded notice · September 24, 2026**
>
> This repository is retained for historical reproducibility. The canonical public fixture is [`ce-stranger-replay-v1`](https://github.com/thisisntjon/ce-stranger-replay-v1/tree/9f201735313a420c3abe15a4c736864469a7a597). Use that package for the current website replay and current source review. This repository's files and recorded results remain unchanged.

This repository contains an earlier public, synthetic vertical-slice fixture for the Consumption Engine. It is deliberately small and self-contained so a stranger can inspect the recorded behavior without access to a private workstation, TheLibrary, HistoryLab, or a network service.

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
