# Evaluation and deployment bar

Read [Current status](CURRENT_STATUS.md) first. Development remains paused; this document explains the completed evidence and the unchanged evaluation contract.

## Keep four questions separate

1. **Source fidelity and interpretation:** Did generation preserve and interpret the allowed contract correctly?
2. **Historical target eligibility:** Is the selected historical 未填 genuinely an initial-stage target, and is it compatible with the exact contract revision used?
3. **Generated versus historical performance:** Does the generated output meet the defined comparison against an independently eligible historical target?
4. **Artifact mechanics:** Did the saved workbook preserve the accepted carrier, remain readable, and repeat correctly when assembled again?

A pass in one category does not prove another. Checkpoint 045 answered the first and fourth questions on case 1140908. It did not establish historical eligibility or produce a new historical-pair performance pass.

## Fixed deployment requirements

Do not reduce thresholds, change the denominator after seeing outputs, drop difficult layouts, or retrospectively add favorable alternatives to obtain a pass.

- At least **30 independently eligible, revision-compatible project pairs**, including **10 reserved** pairs.
- At least **99% source-core correctness** for each case, each applicable detail/component stratum, each claimed layout, and overall. Score both original readers separately; averaging them does not pass a failed reader.
- Complete required raw representations, source provenance, nonitem coverage, and manual obligations.
- **Zero unresolved critical errors**.
- Two original readers passing correctness and required saved/visual checks, plus assembly repeatability.
- Saved-workbook and visual QA covering the agreed **17-column main worksheet**.

The current counts are 1 independently eligible exposed development pair, 0 eligible reserved pairs, and 0 performance-passed historical pairs. The current bar is not met. Candidate inventory counts are not qualification counts.

All **38 reserved answers must remain closed** until the final candidate, evaluator, complete source expectations, input manifests **and all 38 generated outputs** have been frozen. Generation and historical-answer evaluation stay in separate roles. Do not feed historical material values, answer-derived corrections, private evaluator files, or post-output hints into generation.

## Checkpoint 045: exact scope and measurements

Case 1140908 contained 47 source demands and no source components. The fixed obligations were 176 canonical core fields, 223 supported fields, 799 positions, 576 expected-null positions, 282 raw fields (184 nonnull), 95 required nonitem entries, and 12 mandatory manual obligations. One complete alternative was declared before generation. No component percentage or component-layout credit is available from a zero-component case.

| Fixed measure | A | B |
| --- | ---: | ---: |
| Canonical core / applicable detail / case layout | 155/176 (88.068182%) | 147/176 (83.522727%) |
| Supported fields | 202/223 | 194/223 |
| All positions | 778/799 | 760/799 |
| Whole rows | 27/47 | 9/47 |
| Material-name field C | 46/47 | 46/47 |
| Supported specification field D | 15/35 | 7/35 |
| Unit field E | 47/47 | 47/47 |
| Quantity field F | 47/47 | 47/47 |
| Exact raw representation | 197/282 | 197/282 |
| Nonnull raw representation | 115/184 | 115/184 |
| Required nonitem literal and locator coverage | 51/95 | 51/95 |
| Required supported-field source traceability | 223/223 | 223/223 |
| Expected-null positions retained | 576/576 | 566/576 |
| Unsupported populated positions | 0 | 10 |
| Manual obligations passed / reviewed | 9/12 | 9/12 |

At 99%, a denominator of 176 requires **175 correct core fields**. Neither reader passed. The normalized representation and single predeclared complete alternative yielded the same core scores. Repeated selected identity fields and null agreement do not increase core credit. Source-derived item rates were unsupported in this case, so their denominator was zero; no price-accuracy percentage is claimed.

All 47 demands corresponded exactly once, with correct row roles and no missing, extra, or ambiguous demand rows. All 12 manual obligations were reviewed for each reader: 9 passed, 3 noncritical mandatory obligations failed, and none were deferred. The review found 0 critical factual errors. Full semantic provenance still failed because traceable source text was assigned to incorrect fields.

### What the failures mean

Each reader had 69 numeric-string spelling mismatches and 16 explicit-empty-string versus canonical-null mismatches. Underlying source values remained recoverable. These are exact representation failures, not evidence that quantities or prices changed.

The 44 entries absent from the required nonitem collection survived as item anchors. They were in the wrong coverage container; the source facts did not disappear. Anchor use does not waive a separately required census entry.

Other failures concern derived-field allocation, C/D boundaries, and unsupported-field assignment. Reading B placed source-derived commercial/administrative content in 10 unsupported positions. Traceability alone does not make such placement correct. The 045 prompt did not explicitly state all frozen raw serialization conventions. The next version may clarify the policy prospectively; this does not invalidate or retroactively pass 045.

### Independence and repeatability limits

The original readings used identical frozen source/protocol bytes in separate sequential invocations. Reading B received no Reading A feedback. Both outcomes were frozen before explicit evaluation access. The comparer ran exactly once on each untouched accepted carrier. There was no repair, retry, third model call, new alternative, gold edit, or denominator change.

Reader agreement was 165/176 core positions, 778/799 total positions, 26/47 whole rows, and 282/282 raw strings. This is diagnostic agreement, **not correctness**: both readers agreed on raw strings that failed the same representation contract. Correctness repeatability failed.

Model stages took 235,669 ms and 269,477 ms. No tool event was observed in the recorded streams. These observations do not certify OS isolation, backend model/effort, provider cancellation, or stochastic independence. Reported input-token usage differed despite identical supplied bytes; no cause was established.

## Saved workbook and visual evidence

Saved-cell checks passed 9,549 positions for original A, 9,269 for original B, and 9,549 for one separately marked exact-A assembly repeat: **28,367 positions** across three workbooks. All four sheets were checked and contained zero formulas. The repeat preserved the carrier bytes and complete saved matrices; ZIP-byte identity was not a requirement.

The independent visual reviewer inspected **42 saved-reopened images**, 14 for each original/repeat workbook. All 17 main columns and all 47 detail rows were readable. Component/link sheets were header-only. Review sheets were sampled at 36 rows per workbook; dense JSON wrapped and split identifiers. This is not a full provenance-display or component-data-layout certification. Native Excel validation was not performed.

These mechanics passed but do not reverse the failed source case.

## Historical comparisons and audit interpretation

Checkpoint 041, on a **different case** (1141210), scored 117/123 = 95.121951% for each reader and also failed the source-case gate. Its applicable detail result was 63/69 and component result 54/54. Keep this result as historical evidence; the 041-to-045 score difference is not a causal improvement/regression estimate for a single code change.

Across the 036–045 series, the full audit reported 11 actual model attempts, 10 normal completions, and 8 accepted original workbooks across 16 planned slots and three measured source cases. Cases and configurations differ. These totals are descriptive execution history, not a reliability rate, eight qualified projects, or deployment evidence.

The full audit at 045 approved the exact plan and reporting with zero mandatory amendments. The next full audit is 048, earlier after a critical finding or regression. Hash checks, native guard checks, synthetic fixtures, and repeated verification counts support integrity only; never count them as independent accuracy observations.

Local evidence locations are listed in [Current status](CURRENT_STATUS.md#local-evidence-map). Detailed private semantic ledgers and material values are intentionally absent from the public handoff.
