# Proposed evaluator v4: compare_target050 (A/B scored per panel), 2026-11-05

**Status: proposed under owner decision O35 ("Score A/B per panel"). Not frozen, not governing.** It needs an independent review, then a freeze by SHA before any qualification output is evaluated. Until then the frozen v3, `compare_target049.py` (`b600c046…`), stays as it is.

## Problem

The historical creator puts a panel's A/B (盤體名稱 and 盤體規格) in one of two places:
- on the enclosure row only, in most files;
- on every row of the panel's group, in the files from March–May 115.

v3 scores A/B per row. So one panel name counts once, or 70–90 times, depending only on which of her two habits the target follows.

The effect was measured in an evaluation-role study of the three exposed window files (`research/guideline046_005/DECISIONS_OWNER_O23_O25.md`, O32–O35). With a group-wide rule added to CPS, the best possible scores on two of those files were still 0.84 and 0.67, below the O31 floor of 0.90. One panel name that is wrong, or that does not appear in the source, was multiplied across the panel's rows.

The evaluator already treats K–O as job-level for exactly this reason: she writes them on every row in later files and on the first row only in older ones.

## Change

A and B leave the per-row positions. For each case:

1. Take the set of distinct non-null normalized A values on all target rows, and the same set on all CPS rows.
2. Count A as `counted = max(|target set|, |CPS set|)` and `matched = |intersection|`.
3. Score B the same way, separately.

As a result:
- one wrong panel name counts once, as it did on a single row in v3;
- a missing or extra panel name or size counts once per distinct value.

Everything else is v3: row alignment, gap fill, the other fields, job-level K–O, normalization, the description score, and the schema of the outputs. The output adds `v3_per_row_AB`, the v3 score on the same pairs, as a diagnostic.

CPS keeps writing A/B on the enclosure row only (O30), its current practice. The date-window rule (O32) is withdrawn.

## Effect on the frozen 046f development outputs (reader A, diagnostic)

| Case | v3 | v4 |
|---|---:|---:|
| 1130803 | 0.985 | 0.985 |
| 1140506 | 0.962 | 0.962 |
| 1131202 | 0.966 | 0.968 |
| 1141002 | 0.959 | 0.962 |
| 1130204 (old template, excluded) | 0.585 | 0.586 |

On these enclosure-only targets, v4 is equal to v3 or slightly higher. It is higher where several enclosure rows share one name. No CPS output exists yet for the three window files.

## Tests

`tests/test_compare_target050.py` uses invented fixtures and passes 21/21. Among other things, it checks that:
- a group-wide target and an enclosure-only target with the same panel score the same;
- a wrong name counts once;
- a missing or an extra panel counts once;
- a shared size counts once;
- the per-field sums equal matched and counted, as the aggregator's consistency check requires;
- without A/B, v4 equals v3.

## What the review must weigh

- **Effect on the bar.** Is this a faithful implementation of O35, or does it lower the bar? A/B weight falls a great deal in group-wide files and hardly at all in enclosure-only ones.
- **Unscored placement.** Set-based scoring ignores which rows carry the name. CPS could write a right name on the wrong row and lose nothing. Is that acceptable for panel-level identifiers?
- **max-based counting.** Check it against the alternatives: the union, or one-to-one panel matching.
- **Aggregator interaction.** The O31 gate script pins v3 and needs a pins-only v2.
