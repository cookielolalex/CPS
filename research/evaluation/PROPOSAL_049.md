# Proposed evaluator v3: compare_target049 (gap fill), 2026-11-04, revised 2026-11-05

**Status: revised after review round 1 (APPROVE_AFTER_LISTED_FIXES). Not frozen and not governing.** Under owner decision O23 ("Adopt v3 if review OK"), it governs qualification only after the reviewer approves the revision and v3 is frozen by SHA. The frozen v2 (`compare_target048.py`) stays unchanged and governs every result recorded so far. O24: the description target of 0.75 is reported only and does not gate.

## Round-1 review and revision

The first proposal filled a gap whenever E and F were equal. The adversarial review built invented cases where that paired different lines that happen to share a unit and quantity, causing false passes:
- a different fee line, 式/1, rose from 0.906 to 0.984;
- a different 不含估價 line rose from 0.879 to 1.000;
- a different device, 只/2, rose from 0.853 to 0.952.

In 600-trial simulations it produced 17–37 false passes, against 0–4 under v2.

The review also corrected the framing. The O19 record had accepted that C/D quality affects row alignment indirectly, so v3 is a change to the recorded metric (now approved under O23), not a fix to v2.

Revisions:
- **B1 (fill key):** a filled pair needs equal E and F plus the line's identity outside C/D. That means equal non-null Q, or equal non-null I other than 不含估價. The fill uses an order-preserving maximum matching inside each gap, not equal-count positional pairing.
- **S1:** the docstring now discloses that the description rate, row recall and row precision rise with filled pairs.
- **S2:** filled pairs are flagged in `pairs`, and the v2 description rate is reported.
- **S3:** tests 4 and 8 changed on purpose, and the reviewer's fixtures C0–C11 were added. Tests now pass 36/36.

Every adversarial fixture now scores what the reviewer's line-identity oracle allows, or lower. The exception is C8a: garbage C/D with every other field right scores 1.000 with a description rate of 0.0. The governing score allows this by design (O19, O24), and `description_cd` reports it.

## Problem

Owner decision O19 excludes C/D wording from the governing score. In v2, though, two rows pair only when their similarity is at least 0.5. Similarity is 0.7 × C+D wording, plus 0.15 × equal E, plus 0.15 × equal F.

Suppose CPS and the creator wrote the same source line at the same position, agreeing on E, F, Q, I and J, but the creator's wording shares no characters with CPS's (for example a 2-character abbreviation against a 19-character description). The pair scores 0.30, so v2 leaves both rows unpaired. Each row then counts all its non-null scored positions as misses. C/D wording thus decides those positions. The O19 record accepted this as an indirect effect of alignment, so narrowing it is a metric change (O23), not a correction of v2.

A private diagnostic on the frozen 046f development outputs found 7 such pairs, all at matching positions with equal E and F. They are 4 in 1141002, 2 in 1131202 and 1 in 1140506. In most of them Q, I and J also agree.

## Change (as first proposed; superseded by B1 above)

Keep the v2 alignment unchanged, then fill gaps:
- Take the v2 pairs as anchors, plus a virtual start and a virtual end.
- Look at each gap between two consecutive anchors. If it holds the same number k ≥ 1 of unpaired target rows and unpaired CPS rows, pair them in order.
- Fill only when each of the k positional pairs has equal normalized E and equal normalized F, and E or F is non-null on each.
- If the counts differ, or any one pair fails the test, the whole gap stays unpaired.

Filled pairs are scored exactly like v2 pairs, on every position including the description position, so a filled pair whose Q differs still counts a miss. The output lists the filled pairs (`gap_filled_pairs`) and reports the v2 alignment and its score as a diagnostic (`v2_alignment`). Nothing else changes: fields, normalization, job-level K–O, the description score and the 0.95 reading.

Tests: `tests/test_compare_target049.py`, invented fixtures, 17/17 pass.

## Effect on the frozen 046f development outputs (post hoc, diagnostic only)

| Case | v2 | v3 as first proposed | Revised v3 (B1) | Gap-filled pairs (revised) |
|---|---:|---:|---:|---:|
| 1130803 | 0.985 | 0.985 | 0.985 | 0 |
| 1140506 | 0.962 | 0.982 | 0.962 | 0 |
| 1131202 | 0.942 | 0.966 | 0.966 | 2 |
| 1141002 | 0.928 | 0.984 | 0.959 | 2 |
| 1130204 (old template, excluded by O21) | 0.585 | 0.585 | 0.585 | 0 |

Two of the four current-template development cases cross 0.95 only under v3 (1131202 and 1141002). v3 was designed after those v2 results were known.

Readers A and B are identical in both versions.

These v3 figures were computed after v3 was designed on these same cases, so they are not evidence that the metric is sound or that CPS reaches the bar. Only a frozen v3 applied to qualification outputs can show that.

## Risks the review must weigh

1. **False pairings.** Equal E/F at the same position inside an equal-count gap might pair different lines, for example when the creator replaced one line with another that has the same unit and quantity. Such a pair is still scored field by field, so it earns credit only where the fields agree.
2. **Lowering the bar.** A filled pair recovers non-description positions that v2 counted as misses. That is what O19 asks for. But the owner set the 95% bar knowing v2's numbers, and v3 raises scores. So v3 needs the owner's approval as a metric change, not only a review.
3. **Interaction with row recall and precision.** These are diagnostics, not governing. They rise with filled pairs.
