# Candidate 046b source-only trials — 2026-11-03

**Outcome: neither case passed. CPS is not deployment-ready.**

- 1140908 regressed against 045 on the 045-comparable canonical core score.
- On 1141208, both readers cleared the governing numeric gate, but both failed the source-case gate on one mandatory obligation.
- Saved-workbook QA, visual QA and assembly repeatability were not attempted, because no admitted export runtime exists here.
- There is no eligible-pair credit. 0 historical pairs passed, and all 38 reserved projects stay closed.

## What ran

| Item | Record |
|---|---|
| Candidate | 046b, `research/guideline046_002/package/` (manifest sha256 `7748be1d…59f4`). 046a is unchanged. |
| Reviews | [046a review](../../research/guideline046_002/REVIEW_046a.md), [046b review and confirmation](../../research/guideline046_002/REVIEW_046b.md) (APPROVE_FOR_BOUNDED_SOURCE_TRIAL), [dated decisions](../../research/guideline046_002/DECISIONS_046b.md) |
| Route | `tools/cps046b_route.py` v2 plus the archived original `writer004.mjs` `validateCarrier`, with only the `@oai/artifact-tool` import stubbed. Route tests: 113/113, using invented fixtures and a 98-case parity fuzz against the real writer. |
| Admission | [ADMISSION_046b.json](../../research/guideline046_002/records/ADMISSION_046b.json): 24 pinned files, frozen before generation. |
| Generators | Four fresh Claude Code subagent contexts (1140908 A/B, then 1141208 A/B). One prompt each, no follow-ups and no retries. Requested model: inherited, with no effort override. **Observed model: `claude-opus-5-5`** on every message. The proposed sol6.1/xhigh could not be selected, so the runs are not like-for-like with 045. |
| Inputs | Exact 046b package plus the case packet (v2 inventory and views) only. Transcript audits found 0 file reads outside each run directory; 12 calls in the 1141208 runs only changed directory to `/tmp`. Isolation was instruction-based, not OS-level. |
| Carriers | All 4 responses passed the package checker, converted, and passed the unchanged writer validation. |
| Evaluators | A separate evaluation-role context per case, using `compare_source046.py`, which wraps the frozen 043 `evaluate()` (hash-pinned). The manual semantic review is private. |

## 1140908 (exposed regression; frozen 043 expectations; canonical core governs)

| Measure | A | B | 045 A / B |
|---|---:|---:|---:|
| Core, canonical (= declared alternatives) | **141/176 (80.11%)** | **140/176 (79.55%)** | 155 / 147 |
| Supported | 188/223 | 187/223 | |
| All positions | 764/799 | 716/799 | |
| Whole rows | 28/47 | 0/47 | |
| Raw literal (nonnull) | 282/282 (184/184) | 282/282 (184/184) | |
| Nonitem census locators | 95/95 | 95/95 | |
| Pairing incidents, extra rows, role defects | 0, 0, 0 | 0, 0, 0 | |
| Unresolved critical errors | 0 | 0 | |
| Mandatory obligations | 10/12 | 9/12 | |
| 99% gate | fail | fail | fail |

Error classes (generic):

- Both readers placed a rental/basis qualifier in C instead of D on 13 rows, which is 26 core fields each.
- A material prefix that belongs in C was moved to D: 2 rows in A, 1 row in B.
- An acronym was moved from D into C: 2 rows, B only.
- A new-quantity qualifier was left in C: 1 row each.
- The wrong D clause joiner was used: 2 rows each.
- A pointer to an unavailable standard was put in D: 1 row, A only.
- B filled the using-customer field (N) from the letterhead on all 47 rows, a non-core position. The evaluator counted this as noncritical. If customer-role inference is treated as critical, B has 47 critical positions.

**Regression:** A −14 and B −7 core fields against 045. Under the programme rule, the full audit 048 is brought forward.

## 1141208 (next real source case; expectations authored and frozen this session; gate read in declared-alternatives mode)

| Measure | A | B |
|---|---:|---:|
| Core, declared alternatives (governing) | **107/107** | **107/107** |
| Core, canonical | 107/107 | 105/107 (one declared alternative used) |
| Supported, all positions, whole rows (declared) | 137/137, 510/510, 30/30 | 137/137, 510/510, 30/30 |
| Raw literal (nonnull) | 180/180 (136/136) | 180/180 (136/136) |
| Nonitem census located / exact values | 68/68 / 68/68 | 68/68 / 68/68 |
| Pairing incidents, extra rows, role defects | 0, 0, 0 | 0, 0, 0 |
| Unresolved critical errors | 0 | 0 |
| Mandatory obligations | 9/10 (8/10 if read strictly) | 9/10 |
| Governing numeric gate | pass | pass |
| Source-case gate | **fail** | **fail** |

Both readers failed obligation S05. On 4 rows they kept a protocol or physical-medium designation in C without recording its protocol role in the proof, which FIELD_ROLES requires. Separately, reader A gave 2 census cells a role label that differs from the expectations.

Cautions:

- This is one source-only case with 30 rows and 107 core fields; at 99%, one wrong core field is tolerated.
- The expectations were authored by one evaluator context and verified by a second, both before generation, under the same frozen policy the generators used.
- No historical target exists for 1141208, so this result says nothing about historical reconstruction accuracy.
- Two-reader agreement (105/107 core) is diagnostic only.

## Not attempted, and why

- Workbook export, saved 17-column QA, visual QA and saved-assembly repeatability. They need `@oai/artifact-tool` and the Windows source helper. They can run later on the frozen carriers without any repair.
- Historical-target evaluation, which is outside source-only scope.
- Any retry or repair of the scored outputs.

Private evidence is in the separately delivered `CPS_046b_results_20261103_PRIVATE.zip` (sha256 `d6dad4f7…df74`). It holds the packets, expectations, frozen responses, carriers, ledgers, comparisons, manual reviews and transcripts. None of that material is on GitHub.

## Addendum, 2026-11-03: audit 048 corrections (no rescoring)

The full [audit 048](../evidence/AUDIT_048.md) was brought forward by the regression. It reproduced every score above exactly. It also records the following process facts, which this report originally omitted or overstated:

- **P-1 (high).** The independent reviews of 046b were **interface and mechanics reviews only**. PLAN71 required an independent *semantic* review of the field-role rules (C/D boundaries, document references, commercial versus specification text) before admission, and that review did not take place. "APPROVE_FOR_BOUNDED_SOURCE_TRIAL" above means interface approval, not semantic approval. The 1140908 regression sits mainly in that unreviewed text:
  - package-text changes account for A −12 and B −2 of the change against 045;
  - runtime or reader variance on unchanged text accounts for A −2 and B −5;
  - most misses rest on evaluator conventions that the 046b text omits, contradicts or leaves unclear.
- **P-2.** `harness/audit_transcript.py` was changed after admission, to stop misreading relative paths. That was before the 1141208 transcript audits, and the change was not disclosed. Outcomes are unaffected.
- **P-3.** The two 046b policy declarations (P1/P2) came from questions asked by the 1141208 expectation author. They entered the generator package before any 1141208 reading.
- **P-4.** The 1141208 section above says FIELD_ROLES requires role recording on 4 rows. Generator-visible text covers 2 of them. The other 2 depend on the evaluation-side class extension E3.
- **P-5.** PLAN71's prospective timing, fixed model bound and A-before-B assembly were not applied, and this was not declared. A and B ran at the same time; concurrent runs exclude feedback between readers. Wall-clock durations: 1140908 A 611 s, B 587 s; 1141208 A 295 s, B 317 s.
- **P-6 to P-8.**
  - AGENTS.md was injected into every generator context and was not pinned.
  - The rise in raw and census scores is a property of the deterministic adapter, not of reading accuracy.
  - The evaluator brief template was not pinned.

Next steps are revised in [RESUME_047.md](RESUME_047.md): a semantic review gate, a policy–expectation consistency gate (R13), and owner decisions on supply-basis qualifier placement and on customer-role inference.
