# Proposed evaluator v3: compare_target049 (gap fill), 2026-11-04

**Status: proposed. Not frozen and not governing.** It needs an independent review and the owner's approval. The frozen v2 (`compare_target048.py`) stays unchanged and governs every result recorded so far.

## Problem

Owner decision O19 excludes C/D wording from the governing score. In v2, though, two rows pair only when their similarity is at least 0.5. Similarity is 0.7 × C+D wording, plus 0.15 × equal E, plus 0.15 × equal F.

Suppose CPS and the creator wrote the same source line at the same position, agreeing on E, F, Q, I and J, but the creator's wording shares no characters with CPS's (for example a 2-character abbreviation against a 19-character description). The pair scores 0.30, so v2 leaves both rows unpaired. Each row then counts all its non-null scored positions as misses. C/D wording thus decides those positions, contrary to O19.

A private diagnostic on the frozen 046f development outputs found 7 such pairs, all at matching positions with equal E and F. They are 4 in 1141002, 2 in 1131202 and 1 in 1140506. In most of them Q, I and J also agree.

## Change

Keep the v2 alignment unchanged, then fill gaps:
- Take the v2 pairs as anchors, plus a virtual start and a virtual end.
- Look at each gap between two consecutive anchors. If it holds the same number k ≥ 1 of unpaired target rows and unpaired CPS rows, pair them in order.
- Fill only when each of the k positional pairs has equal normalized E and equal normalized F, and E or F is non-null on each.
- If the counts differ, or any one pair fails the test, the whole gap stays unpaired.

Filled pairs are scored exactly like v2 pairs, on every position including the description position, so a filled pair whose Q differs still counts a miss. The output lists the filled pairs (`gap_filled_pairs`) and reports the v2 alignment and its score as a diagnostic (`v2_alignment`). Nothing else changes: fields, normalization, job-level K–O, the description score and the 0.95 reading.

Tests: `tests/test_compare_target049.py`, invented fixtures, 17/17 pass.

## Effect on the frozen 046f development outputs (post hoc, diagnostic only)

| Case | v2 | v3 | Gap-filled pairs |
|---|---:|---:|---:|
| 1130803 | 0.985 | 0.985 | 0 |
| 1140506 | 0.962 | 0.982 | 1 |
| 1131202 | 0.942 | 0.966 | 2 |
| 1141002 | 0.928 | 0.984 | 4 |
| 1130204 (old template, excluded by O21) | 0.585 | 0.585 | 0 |

Readers A and B are identical in both versions.

These v3 figures were computed after v3 was designed on these same cases, so they are not evidence that the metric is sound or that CPS reaches the bar. Only a frozen v3 applied to qualification outputs can show that.

## Risks the review must weigh

1. **False pairings.** Equal E/F at the same position inside an equal-count gap might pair different lines, for example when the creator replaced one line with another that has the same unit and quantity. Such a pair is still scored field by field, so it earns credit only where the fields agree.
2. **Lowering the bar.** A filled pair recovers non-description positions that v2 counted as misses. That is what O19 asks for. But the owner set the 95% bar knowing v2's numbers, and v3 raises scores. So v3 needs the owner's approval as a metric change, not only a review.
3. **Interaction with row recall and precision.** These are diagnostics, not governing. They rise with filled pairs.
