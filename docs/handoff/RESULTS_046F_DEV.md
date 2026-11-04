# Candidate 046f development trial: historical match (2026-11-04)

**Five non-reserved tuning cases, readers A and B each.** These cases were already exposed in the creator-practice studies, so the trial earns no eligibility credit. Visual QA was not run, and the portable writer is not admitted.

## Setup

- **Candidate:** 046f, frozen (manifest `5f5502a7…`). The independent review approved it after two rounds; see `research/guideline046_006/REVIEW_046f.md`.
- **Admission:** `research/guideline046_006/ADMISSION_046f_dev_a.json`.
- **Inputs:** each packet is bound to the case's company 材料清單 (owner decision O17), with no brand table, plus the job inputs for L/M/N (O13). A leave-one-out draft glossary was used, not yet owner-approved.
- **Run order:** reader A was frozen and assembled before reader B started.
- **Model:** `claude-opus-5-5` was observed on every run.
- **Timing:** 587–818 s per run, all within bounds.
- **Evaluator:** `compare_target048.py` v2 (O19). The governing score covers rows plus every non-description field. C/D is reported as one description position against a target of 0.75.
- **Assembly:** route v4.2, then portable writer v2.2. Saved-cell QA passed on 10/10 runs with 0 mismatches.

## Results (identical for readers A and B)

| Case | Governing score | Row recall / precision | C/D description | Critical errors |
|---|---:|---:|---:|---:|
| 1130803 | **0.985** | 1.000 / 1.000 | 0.703 | 0 |
| 1140506 | **0.962** | 0.979 / 0.979 | 0.711 | 0 |
| 1131202 | 0.942 | 0.974 / 0.983 | 0.613 | 0 |
| 1141002 | 0.928 | 0.974 / 0.974 | 0.806 | 0 |
| 1130204 | 0.585 | 1.000 / 1.000 | 0.228 | 0 |

**Pooled:** 0.883 governing, a cross-case diagnostic rather than a reliability rate. Two of five cases are at ≥0.95, and four of five at ≥0.90.

For comparison, the frozen 046b/046c outputs scored 0.22–0.33 on these cases under the earlier metric (v1.1), before the recalibration.

**1130204** has an older template target. It puts the unit price in G and the status in H instead of Q and I/J. CPS's Q equals her G on 30 of 30 rows, and its status matches her H on 62 of 62. That accounts for 154 of its unmatched positions.

## Generic miss classes (per reader, 252 unmatched governing positions in total)

| Class | Positions |
|---|---:|
| Older-template column convention | 154 |
| Rows not aligning because C/D forms diverge: missing glossary category words, compound abbreviations not in the glossary | 56 |
| Enclosure A naming (panel tags, qualified names) | 10 |
| Enclosure B dimensions not stated in the bound source | 7 |
| Targets leaving the job-level L/M/N blank | 6 |
| Zero-state lines kept by the creator | 4 |
| Smaller creator variations | 15 |

No unmatched position comes from CPS breaking a rule.

## Next

- Glossary category words and R52 matching after a qualifier.
- A decision on enclosure tags in A.
- How older-template targets are handled in qualification.
- Qualification on unexposed cases, including 10 reserved, after the writer is admitted and visual QA has run.
