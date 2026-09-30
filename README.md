# Consumption Engine: public research record

Consumption Engine is a local research prototype for preserving evidence, preparing task context and reusing checked procedures. The product runtime is private. This repository publishes selected research records and a historical synthetic fixture.

## Latest local update: September 30, 2026

Working ingestion and evidence delivery extend the demonstrated manual procedure reuse below; **end-to-end efficiency remains unproven**. Read the [dated intake, PDF reading, answer and maintenance update](https://simoneresearch.com/evidence/consumption-ingestion-2026-09-30/).

- Selected PDF intake: **256 documents, 899 MB decimal, 7,555 pages**, initial **101.8 seconds**; unchanged replay **6.1 seconds**, 256 cache hits, zero reparses. Mechanical qualification; engineering, preparation and review excluded.
- Six pages from two papers: creator order passed **16/17** valid prose checks versus coordinate sorting **1/17**. One invalid frozen criterion is disclosed and originals retained. Optional source-checked page access was accepted; one complete response took **0.315 seconds / 1,873 tokens**. Footnotes, captions, tables, equations and diagrams remain limited; default indexing unchanged.
- **36 answer responses**: lexical **7/12** grounded answers versus RRF **6/12**, plus unsupported refusal checks. Lexical retained; no universal superiority or total-cost claim.
- Explicit caller-selected complete text ranges deliver source-bound passages without copied briefs; changed sources refuse and explicit refresh produces a checked successor. The later revision records **258 passing tests plus recovery**, not general agent efficacy.
- Frozen maintenance proposals: **0/3 accepted in each condition**; prepared used **23,638 versus 13,012 tokens (+81.7%)**. Three later assisted corrections were separately accepted; failed scores remain unchanged.

These aggregates were inspected in retained local output/review records, not externally reproduced. No private papers, runtime or raw data are released here. MiniCheck remains advisory: its limited audit found three false acceptances among 72 negatives with shared-source/data-overlap caveats; simulated reviewer savings are not operational evidence.

## Earlier procedure result: September 30, 2026

CE-EXEC-01 accepted **four generated procedures** across ordinary and prepared conditions. **Two retained procedures were manually selected and reused successfully on six new-input batches**, with **zero dispatch model calls** and **two changed-source refusals**. Zero dispatch calls excludes procedure generation, preparation and review. Prepared generation used **21,103 reported model tokens**, ordinary **11,151**; end-to-end savings were not demonstrated.

The subsequent CE-REUSE-02 study is independently accepted and closed as a negative result for autonomous reuse and efficiency. All four attempts completed; each condition accepted one of two activities. No agent selected `run_skill` or made a retrieval call. Skill availability used 11,818 reported tokens versus ordinary 11,317. Citations alone do not demonstrate evidence consumption.

## Run or inspect

- [Product and capability boundaries](https://simoneresearch.com/product/consumption-engine/)
- [Dated evaluation conditions and source version](https://simoneresearch.com/evidence/consumption-results-2026-09-30/)
- [Runnable public synthetic fixture](https://github.com/thisisntjon/ce-stranger-replay-v1/tree/8374bb6ee93edef37f57f284532d9487d5fd2e2d), released as `v1.0.0-fixture`
- [September 27 decision ledger](https://github.com/thisisntjon/consumption-demo/tree/7df8429ba8de11ae3bf571cc9ee6bab03386b1ae/ledger)

## Evidence and limits

The September 30 aggregates come from independently inspected retained local output/check records and recorded nonauthor acceptance. Private receipts, source data and runtime are not published here, so these outcomes are **not publicly reproducible**. Two known public course policies, finite inputs, manual preparation and unmeasured engineering/review/energy costs limit the results. Source bindings establish byte identity, not semantic truth or reviewer authentication. The Library and CE are complementary projects; these results do not establish complete integration, general autonomy or overall economics.

The public ledger verifies process records and file integrity, not its cited private outcome receipts. Its 49/50 claim-support result was graded by Claude-based agents on the same team, not independently reproduced externally. It publishes 34 decisions: 11 confirmed, 14 refuted, five inconclusive and four open at export.

To check the immutable ledger snapshot:

```text
git clone https://github.com/thisisntjon/consumption-demo.git
cd consumption-demo
git checkout 7df8429ba8de11ae3bf571cc9ee6bab03386b1ae
python ledger/verify_ledger.py
```

The earlier website link pinned `9f201735313a420c3abe15a4c736864469a7a597`; that is a historical snapshot, not the released fixture tag target.

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
