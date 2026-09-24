# Public-safe Consumption Engine demo

This is the clone-and-run entrypoint for the first Consumption Engine vertical
slice. It uses only the synthetic, manually annotated fixture committed in this
repository. It does not need a private archive, TheLibrary, HistoryLab, a
network connection, or workstation caches.

From a fresh clone with Python 3.11 or newer:

```powershell
python examples/public_demo/run_public_demo.py --output .tmp/public-demo-run
```

The run creates a new directory containing:

- `REPORT.md`: the inspectable question, evidence path, correction, stale
  refusal, checked successor, unknown case and restore boundary;
- `RESULT.json`: machine-readable outcome and limitations; and
- `RECEIPT.json`: local machine identity, runtime, before/after input pins and
  stable oracle projection; and
- `completed-work.zip`: the sealed synthetic state used by the local restore
  check.

`FIXTURE-MANIFEST.json` publishes byte counts and hashes for all 12 committed
fixture files; its SHA-256 is pinned in `ORACLES.json`. The runner verifies the
manifest before starting. `ORACLES.json` also publishes the expected status
projection.

The first clean external CI receipt is preserved as
`CI-RECEIPT-36061873661.json` (SHA-256
`234b679d13ee90f2a172ed407abca1d9f24c2ba71b1f39d3a8122843f27c8250`) with its
matched comparison record beside it. The originating GitHub artifact is
`consumption-public-receipts-36061873661`.

CI also runs `verify_receipt.py` against `ORACLES.json`. Its automated decision
checks the exact input pins and stable status projection. That decision is a
machine-level integrity/oracle check, not a human semantic review or truth
certification.

An independent reviewer can use [INDEPENDENT-REVIEW.md](INDEPENDENT-REVIEW.md)
to run the package twice and return a bound decision without private fleet
access.
Run the command twice in separate output directories and compare the
`oracle_projection` objects in the two receipts; they should match.

The expected run exits successfully and includes these behaviors:

1. the original `3`-retry claim is preserved;
2. an exact mirror is not counted as independent corroboration;
3. a correction changes the supported successor to `2` retries;
4. the old task is refused as stale;
5. an unsupported question remains `UNKNOWN / INSUFFICIENT_EVIDENCE`; and
6. the exported state is checked without the original source folder.

This proves a reproducible local synthetic workflow. It does not claim
scientific truth, automatic claim extraction, independent acceptance, or a
physical clean-machine restore. Those are separate qualification steps.

## Matched baseline comparison

To inspect the current bounded comparison against a simple single-pass workflow
using the same documents:

```powershell
python examples/public_demo/compare_baseline.py --output .tmp/public-comparison
```

The comparison makes the baseline definition explicit and records the result in
`COMPARISON.md` and `COMPARISON.json`. It is an author-run behavioral result;
independent review and broader measurements of time, cost and correctness are
still required before claiming general superiority.
