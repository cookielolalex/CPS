# Candidate 046c: development batch 1 (three tuning cases), 2026-11-03

**Outcome: both readers cleared the governing numeric gate on all three cases, with every manual obligation met and 0 critical errors. No case is recorded as passed.** Saved 17-column workbook QA, visual QA and saved-assembly repeatability were not attempted. No admitted export runtime is available here. These are tuning cases: the results are development evidence for 046d and earn no eligibility credit. The checks were source-only, and no historical target was read.

## Setup
- **Candidate:** 046c, unchanged (manifest `4d8602db…`).
- **Evaluator:** frozen `compare_source047.py` (`d0959cb2…`).
- **Evaluator-side decisions:** recorded before generation in [DECISIONS_BATCH1.md](../../research/guideline046_003/DECISIONS_BATCH1.md), together with the pinned [evaluator addendum](../../research/guideline046_003/harness/EVALUATOR_ADDENDUM_BATCH1.md):
  - the design-plus-management-fee line is excluded from scoring and governed by a manual obligation (backlog Q2);
  - the panel-group A exclusion applies only to held-out 1150107.
- **Rolling-validation case 1150107:** taken out of the generator runs before generation, so it is not consumed by tuning. Its source-only expectations are frozen and kept.
- **Expectations, per case:**
  - authored in one evaluator context;
  - independently reviewed in a second;
  - fixes applied;
  - re-verified FREEZE_OK, with the R13 gate passing.
- **Admissions:** one per case, frozen before generation: [b1a](../../research/guideline046_003/records/ADMISSION_046c_b1a.json), [b1b](../../research/guideline046_003/records/ADMISSION_046c_b1b.json), [b1c](../../research/guideline046_003/records/ADMISSION_046c_b1c.json).
- **Run order and bounds:** reader A was generated, frozen and assembled before reader B started. The wall-clock bound per reader was declared beforehand.
- **Model:** `claude-opus-5-5` was observed on every message.
- **Evaluation:** one separate evaluation-role context per case.

## Scores

Core is shown as governing declared-alternatives, with canonical in brackets.

| Case (scored rows) | Reader | Core | Supported | Raw nonnull | Census | Obligations | Critical | Time / bound |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1141002 (150 + 1 excluded) | A | 550/550 (548) | 700/700 | 648/648 | 173/173 | 16/16 | 0 | 709 / 3000 s |
| | B | 550/550 (548) | 700/700 | 648/648 | 173/173 | 16/16 | 0 | 644 / 3000 s |
| 1130803 (63 + 1 excluded) | A | 239/239 (236) | 302/302 | 297/297 | 97/97 | 15/15 | 0 | 670 / 1500 s |
| | B | 239/239 (235) | 302/302 | 297/297 | 97/97 | 15/15 | 0 | 609 / 1500 s |
| 1140506 (95 + 1 excluded) | A | 353/354 (339) | 448/449 | 507/507 | 275/275 | 16/16 | 0 | 880 / 2400 s |
| | B | 354/354 (338) | 449/449 | 507/507 | 275/275 | 16/16 | 0 | 930 / 2400 s |

Further results, the same in every run:
- 0 pairing incidents, 0 role defects and 0 unsupported populated positions.
- Exactly one extra generated row, which is the excluded line, accepted under its manual obligation.
- The comparator's `complete_row_roles` reads false mechanically because of that single row.

Canonical core is below 99% on 1130803 and 1140506. In each case the gap comes from placements that 046c leaves undecided and that were declared before generation as complete alternatives:
- type words after a delimiter;
- mixed inclusion clauses;
- protocol and acronym tokens;
- bare exclusion remarks.

**Run isolation:**
- The supplementary full-command check found 0 outside paths in all 6 transcripts.
- The pinned audit tool flagged 3 runs falsely, because it truncates commands at 600 characters before extracting paths. The fix is in the 046d harness.
- One reader reported listing its own run folder; it opened none of the files there.

## Generic error classes, routed to 046d
- **R14 misapplied (generator error, 1 row, 1 core field, 1140506 A):** a bracketed attribute at the start of a longer moved run was split off as its own span.
- **Bare exclusion or not-used remarks naming no object** (1130803, 3 rows per reader; declared alternative).
- **A method-change remark with a site-condition justification** (1130803 B, 1 row; declared alternative).
- **A status word inside a bracketed inclusion clause** classified with the whole clause, without naming its class (1141002, 2 rows; borderline obligation).
- **Disagreement on holding:** whether a lump-sum demand that points to an unavailable drawing must be held (1140506: A held it, B did not).
- **Null reasons naming a source column by a document role the source does not state** (1130803 A; wording only).
- Backlog questions Q1, Q2, Q4, Q5, Q7, Q10 and Q13 came up as expected. The 046d draft decides them in R26–R38.

## What this does and does not show
- Under 046c, with policy-undecided placements declared in advance, two independent readers reached at least 99% source-core correctness on three development cases of 64–151 rows. That excludes analysis components; the one component case, 1141210, failed reader A because of a package-example defect that 046d fixes.
- It is **not** historical reconstruction accuracy.
- It is **not** an eligibility result.
- It is **not** deployment evidence: the export, saved-workbook and visual QA gates are unattempted, and no reserved or qualification case has been run.
