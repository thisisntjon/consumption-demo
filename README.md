# Consumption Engine: public research record

The Consumption Engine turns a large, growing, mixed-quality pile of documents into current, checkable knowledge that AI agents can use without a human reviewing every file. This repository holds the parts of that work that anyone can inspect and rerun. The engine itself is private.

Project page: <https://simoneresearch.com/product/consumption-engine/>

## Latest: decision ledger, September 27, 2026

[`ledger/`](ledger/) publishes 34 preregistered decisions from one working day: each states its question, check and pass bar before the check ran, then records the outcome. 11 were confirmed, 14 refuted, 5 inconclusive and 4 were still open at export.

```text
python ledger/verify_ledger.py
```

Read [`ledger/README.md`](ledger/README.md) for what the day shows and the limits on reading it.

## Current public fixture

The canonical runnable fixture is [`ce-stranger-replay-v1`](https://github.com/thisisntjon/ce-stranger-replay-v1/tree/9f201735313a420c3abe15a4c736864469a7a597), tag `v1.0.0-fixture`. Use it for the website replay and for source review.

## Historical fixture (superseded September 24, 2026)

The rest of this repository is an earlier public, synthetic vertical-slice fixture, retained unchanged for historical reproducibility. It is small and self-contained so a stranger can inspect the recorded behavior without access to a private workstation or network service.

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

The comparison is a bounded author-run demonstration on the same fixture. It does not claim scientific truth, general superiority, or human acceptance. The fixture is synthetic and manually annotated. It demonstrates reproducible behavior and evidence lineage. It does not certify the truth of the fictional policy, automatic claim extraction, production readiness, or a physical clean-machine restore. See [`examples/public_demo/README.md`](examples/public_demo/README.md) for the full scenario.
