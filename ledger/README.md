# Decision ledger: September 27, 2026

This folder publishes one day of the Consumption Engine team's working decision ledger. Each row is a preregistered decision: the question, the evidence it rested on, the change to try, the check to run, and the bar the result had to clear, all written before the check ran. The outcome and verdict were appended afterwards. Failed bars are recorded as `refuted`, not reworded.

The team is a small group of AI agents directed by Jonathan Simone, running on free local compute. Node names in the ledger (`skynet`, `roach`, `skynet-gpu`) are machines and agent identities, not people.

## Check it

```text
python ledger/verify_ledger.py
```

Python 3.11 or newer, standard library only, no network. Expected output:

```text
PASS: 34 decisions; confirmed 11, refuted 14, inconclusive 5, open 4; ledger sha256 0427d8af...
```

The script checks that ids are consecutive, that every row states a question, a check and a bar, that every resolved row has an outcome recorded no earlier than the row was stated, that open rows carry no outcome, and that the tally, file hash and `SUMMARY.md` match. Change one status in `DECISIONS.jsonl` and it fails.

## What the day shows

- **Most bars failed.** 14 of 30 resolved decisions were refuted and 5 could not be judged as written. 11 were confirmed.
- **Failures changed the plan.** D-002 looked like a gain (7 to 12 of 15 paraphrased questions answered) until a leak check found test files in the search corpus. With them excluded the gain was 0 of 15. D-004 and D-010 then made the index leak-free by construction.
- **A distilled checker did not transfer.** D-008: a small CPU classifier trained on 2,000 synthetic errors learned the synthetic edits (training loss about 0.02) but still accepted 27 of 31 real bad rows against a bar of 9. The real errors are over-reach, which the synthetic edits did not model.
- **A generated onboarding file beat hand-written docs on a sealed bank.** D-019: a fresh agent given only the generated curriculum answered 14 of 15 current-state questions with 0 stale answers; a fresh agent given the existing docs answered 6 of 15 with 4 stale.
- **A local source locator passed on its fifth attempt.** D-025 to D-030: an on-disk store finds the source file of 83.2% (practice) and 85.0% (confirm) of verifier passages at 4.4 ms p95, against a bar of 80% and 50 ms.
- **First real-corpus consumption cleared its first sample gate.** D-029: 49 of 50 randomly sampled claims extracted by a local model from a real project were supported by their cited source lines (bar 45).

## Read the results with these limits

- **Timestamps are self-recorded** by the agents. The first third-party timestamp is this repository's public commit. `source_row_sha256` binds each row to its private original for a later audit.
- **Grading is mostly by Claude-based agents on the same team.** Where a grader was not an author of the graded work, the row says so. That is separation of roles, not independent reproduction.
- **Repeated attempts.** T1 (D-025 to D-030) and the swarm extraction gates (D-031, D-033, D-034) passed only after changes between attempts (T1 on attempt five, the swarm gate on attempt three). The rate bars were never lowered; T1 added a planted-file clause from D-026 on. Each attempt and its failure is in the ledger. D-034 discloses that its grader knew the earlier failure modes.
- **Receipts are private.** Rows cite receipt files in the team's private workspace. They are named so the chain can be audited on request; they are not published here.
- **This is one day of process evidence.** It does not show that the Consumption Engine outperforms other systems. The flywheel test that decides that (an agent printed from the inventory against an agent given the raw project, on sealed questions) had not passed when this was exported.

## Files

| File | What it is |
|---|---|
| `DECISIONS.jsonl` | 34 rows, one JSON object per line |
| `SUMMARY.md` | Generated table of every decision |
| `MANIFEST.json` | Export rules, source hash, tally, file hashes |
| `verify_ledger.py` | The checker above |
