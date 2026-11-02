# Source scope and historical-target eligibility

Public handoff, 2026-11-02 (Asia/Taipei). Development remains **paused after checkpoint 045**. These rules preserve the current CPS scope; this document does not admit new evidence, reopen a closed trial, or authorize execution. Read [the guideline](GUIDELINE_V4.md), [RQA policy](RQA.md), and the [current handoff](../handoff/CURRENT_STATUS.md) together.

## Generation inputs

Generate 未填 only from the exact approved original contract, demonstrably incorporated original schedules, and verified project identification. A filename, directory, matching total or similar description does not establish contract incorporation or revision identity. Pin the original bytes, SHA-256, revision, selected sheets/pages and adoption evidence. An unverified quotation remains unverified; specifically, quotation adoption for case `1120301` has not been established.

The generator must not obtain values from historical 未填, 已填/OK, company selection habits, catalogues, purchase/production records, later internal 電機圖, or 板金/鈑金 drawings. Historical embedded “original material” sheets are historical target evidence, not a replacement for the original contract. Keep evaluation materials, private expectations and respondent answers out of generation and tuning inputs.

Work on original files is read-only. Do not execute macros, refresh external links, edit source cells or recalculate source contracts. Record literal and visible values separately, including merged-cell anchors and covered cells, formula/cache/error states, true blanks, formatted blanks and explicit empty strings. A cached number is not proof that the underlying formula is valid. Missing source values remain unknown; errors do not become zero or ordinary blank values.

Missing referenced schedules, conflicting revisions and unusable key cells block the affected output. A labelled partial research draft may preserve usable evidence, but partial delivery is not a complete pass. Do not silently replace an unreadable contract with a budget, quotation or analysis sheet.

## Client drawings: investigation only

The current inspection clarification allows separately examining **original client-supplied control/electrical drawings**. The electrical-drawing exclusion refers to later internal 電機圖. The 板金/鈑金 and later manufacturing-document restrictions remain.

Before that inspection, establish provider, original file/attachment, exact byte version and availability before 未填 creation. A matching filename, email date or local modification time is not proof of byte identity, actual availability to the creator, reading or adoption. Record uncertainty explicitly.

This is an investigation permission. It does not add drawings to the frozen contract-only generator, alter historical scores, or rehabilitate an excluded target. Do not use later drawings to fill missing contract dimensions.

## Supply-list semantics

未填 supplies drafters with a material/supply list in the format they will modify into 已填. Whole-project negotiated prices, tax and total-price reconciliation are not material rows and must not be allocated into an item contract unit price.

Material responsibility must retain both conditions of the recorded rule: **no enclosure and no estimate**. Missing price alone is insufficient. Customer supply, “not included in the estimate,” self-transport, service work and absence of company responsibility are different facts. Preserve those distinctions and unresolved scope. Do not delete an item merely because it has no price, or set a price to zero because it is customer-supplied.

Preserve explicit item units, quantities, per-panel bases, total quantities, analysis bases and one-time fees separately. Do not multiply every analysis quantity by a panel count. Contract groups, physical enclosures, individual panels and material rows are different levels.

## Exclude misnamed later-stage targets

Any selected 未填 target with `+` or full-width `＋` in actual **panel/enclosure dimensions** is excluded as a misnamed later-stage target. Exclude the entire selected case from valid training, tuning and scoring; do not remove only the difficult dimension or row.

Inspect panel-specification cells and enclosure material names/specifications/continuations, including merged visible values and their context. The rule covers added height, combined widths and other additive dimension expressions. It does not depend on a particular number or suffix.

Model/accessory/configuration plus signs, such as `FL+LS` or `3P+N`, do not by themselves trigger this exclusion. A plus sign in a filename is insufficient, and `±` is not the same symbol. Ambiguous field roles require review rather than automatic exclusion or approval.

The seven selected cases already excluded in full are:

`1110106`, `1110201`, `1110909`, `1111101`, `1121102`, `1130309`, `1130906`.

Case `1130906` also has user-relayed expert confirmation that the target belongs to a later OK/drafting stage. Its WT-A5 comparison is closed as invalid. Earlier WT-A4/WT-A5 answers and comparisons are retained only as history; they cannot support valid scoring or tuning. Separate client-drawing inspection does not readmit the case. Do not automatically replace an excluded file with another revision.

Record every exclusion with file path, SHA-256, sheet/cell, original evidence, enclosure context and policy revision. Preserve original filenames, bytes, previous scores and denominators. Expert confirmation for one case is not expert confirmation for all seven.

## Screening is only one eligibility check

The installed screening route is `cps.ps1 screen-targets`, documented in the exported implementation notes. A successful process exit means a report was produced, not that a target was admitted. Inspect the per-file result:

| Status | Meaning |
|---|---|
| `EXCLUDE_PANEL_DIMENSION_PLUS` | The target is excluded; remove the whole selected benchmark case. |
| `NO_PANEL_DIMENSION_PLUS_DETECTED` | This identifiable scope did not trigger the plus rule; no complete gold-eligibility claim follows. |
| `REVIEW_REQUIRED` / `UNSCANNED_*` | Eligibility remains incomplete. |
| `SKIPPED_KNOWN_LATER_STAGE_OR_TEMP` | Known later-stage/temporary file is not read or admitted as a candidate. |

The installed screener's documented limits include unsupported legacy XLS targets, unrecognized headers, ambiguous plus signs, unusable formula caches, source changes and bounded scan limits. Its old limits must not be silently presented as support in another implementation. A changed source hash invalidates earlier screening. Do not infer whole-archive absence from a bounded no-match.

No-plus screening does not establish initial workflow stage, exact contract revision, pre-creation source use, source completeness, answer correctness or project-family independence. Those are separate eligibility obligations. A name containing 未填 is not sufficient.

## Separate data populations and exposure

The old pool has 23 remaining candidates after exclusions. Its retained historical holdouts were exposed and cannot become fresh blind tests again. The later inventory contains 153 development candidates in 139 assigned families (118 tuning and 35 rolling) and 38 reserved cases in 35 assigned families. These are inventory counts, not qualified cases or performance passes.

At pause: one independently eligible **exposed development pair**, zero eligible reserved pairs, and zero performance-passed historical pairs. Source-only correctness and historical-pair eligibility must be reported separately. Filename grouping does not prove substantive family independence. Once a case informs tuning, later results on it are regression evidence, not fresh blind validation.

All **38 reserved answers remain closed** until the final candidate, evaluator, complete source expectations, input manifests **and all 38 generated outputs** are frozen. Evaluation-only target screening must not supply generation values or leak reserved answers. Do not lower thresholds or shrink difficult source scopes to obtain a pass.

## Local evidence to consult after an explicit resume

The public repository omits private source contracts, target workbooks, mailbox contents and cell-level answers. `{WORKSPACE}` is the original workspace root; `{RUN}` is its contract-to-未填 run root; `{REFINEMENT}` is `{RUN}/cps_refinement_001`.

| Purpose | Local record |
|---|---|
| Frozen baseline guideline and current inspection overlay | `{WORKSPACE}/CPS/GUIDELINE_V4.md`, `SOURCE_POLICY.md` |
| File/hash-specific target-screening rules and registry | `{WORKSPACE}/CPS/TARGET_ELIGIBILITY.md`, `TARGET_SCREENING_REGISTRY.json` |
| Current legacy pool and exclusions | `{WORKSPACE}/CPS/ACTIVE_POOL.json`; `{RUN}/cps_pool_revision_003/POOL_EXCLUSIONS.json` |
| Development split membership | `{REFINEMENT}/inputs/generation_tuning.json`, `generation_rolling_validation.json` |
| Exact eligible pair disposition | `{RUN}/rqa034_response_001/ELIGIBILITY_UPDATE.json` |
| Pause and latest plan | `{REFINEMENT}/STATE.json`, `pause_after045_001/RECORD.json`, `PLAN_v71.md` |

Read target-bearing records only in the appropriate evaluation role and at the permitted stage. The local records retain the exact original evidence; the public policy digest is not a substitute for source-version or target-eligibility verification.
