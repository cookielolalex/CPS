# Enclosure A/B replay of the revised R56 rule (046g review round 1), public-safe

Date 2026-11-05. Evaluation role, exposed tuning cases only. Same 15 cases, same bound sources and targets, same 65 enclosure rows as the earlier enclosure study (all source and target sha256 pins re-verified). No reserved case, qualification candidate, `qual_screen/files` or `qual_sources` file was opened. This file gives counts and row ids only; per-row values, evidence and scripts are in `REPLAY_PRIVATE.json` and `scripts/` beside it. Examples below are invented.

## What was implemented

A deterministic function (`scripts/rule046g_r1.py`) implementing the review's rule texts B1, Q1, Q3, S2, S3, S5, S6, S7, S8, S9 and S10, with S4 (component rows take only their block title) and Q2 (innermost heading that names a panel) applied. Self-check on the invented examples quoted in the review: 52/52 pass.

Reading choices the review text leaves open (each was also run as a variant, table below):
- **S5 category segment.** Primary: a leading category word that itself names a box is dropped only when a later segment is the box segment ("each segment before the box segment"). Variant: dropped whenever a later segment remains (R52).
- **S2 tag.** Primary: any Latin/digit code or 甲… placeholder, except materials, floors, ratings, IP/RS/AC/DC codes and a grade letter written before 級 (a class-C box). Variants: the grade letter counts; letter-only codes do not.
- **Scope.** R33 scope from the label-format outline; a subtotal row that names an open heading closes it.
- **Q3 subsidiary test** on the row's own box noun (after the last-box clause).

## Agreement with the creator (65 enclosure rows, normalized mode, blank = blank counts as agreement)

| | A, all 65 | A, heading-derived (28) | A, line-derived (37) | B, all 65 |
|---|---:|---:|---:|---:|
| Earlier study rule | 47/65 | 26/28 | 21/37 | 28/65 |
| **Revised rule (primary reading)** | 45/65 | 26/28 | 19/37 | 28/65 |
| Variant: category word dropped whenever a later segment remains (R52 reading of S5) | 46/65 | 26/28 | 20/37 | 28/65 |
| Variant: grade letter (class-C box) counts as a tag | 45/65 | 26/28 | 19/37 | 28/65 |
| Variant: letter-only codes are not tags | 44/65 | 26/28 | 18/37 | 28/65 |
| Variant: both tag readings above | 40/65 | 22/28 | 18/37 | 28/65 |
| Variant: study category set instead of glossary chain words | 45/65 | 26/28 | 19/37 | 28/65 |
| Variant: nearest heading only (study scoping) | 45/65 | 26/28 | 19/37 | 28/65 |
| With S11 (strict numbering) | 45/65 | 26/28 | 19/37 | 28/65 |
| With S11 (outline numbering) | 45/65 | 26/28 | 19/37 | 28/65 |

- The subsets are the earlier study's split: 28 first enclosure rows under a panel-naming heading or block title, 37 others. Under the revised B1 test the heading-derived set is the same 28 rows (25 section headings, 3 block titles), so the revised rule's own split gives the same counts.
- **A: 47/65 → 45/65.** Heading-derived unchanged at 26/28; line-derived 21/37 → 19/37.
- **B: 28/65 → 28/65,** the same 28 rows with identical values. S9 changes no value here: every reachable B is already W/H/D-labelled in W, H, D order, in mm or unitless, with one complete set.

## Rows whose outcome changed (primary reading, against the earlier rule)

| Row | Field | Change | Class |
|---|---|---|---|
| 1131202 T2 (S2r9) | A | match->miss | B1 follower list |
| 1130304 T2 (S2r10) | A | match->miss | B1 follower list |

- **Why (both rows).** The line's only enclosure word outside its leading category segment is directly followed by 體 (invented: 低壓配電盤，丙型箱體，鋼板). Under B1's closed follower list that names no box, so the category word is the only box noun left and A becomes it; under the R52 variant A is null. She wrote the 箱體 noun phrase on both rows. The earlier simulation counted 箱體 as an enclosure word, although 046g's own Terms already said it names none.
- **Value changed, outcome unchanged:** 1131006 T201 (S2r218) A (same B1 cause; she left A blank, so both the old and the new value miss). Under the R52 variant this row turns into a match (null = blank), giving 46/65.
- **No other row changed.** Q1, Q3, S2, S3, S5, S6, S7 and S8 reproduce the earlier values on every other row.
- **Suggested B1 refinement (replay-only, not a review item).** A longer noun ending in the glossary's enclosure word (乙型箱體) would name a box ending at 體, while the bare word 箱體 stays a category segment. That gives A 47/65, heading-derived 26/28, line-derived 21/37 and B 28/65. It restores both changed rows and keeps the B1 fixes for 盤體, 盤內 and 箱座.
- **Tag sensitivity (letter-only codes not tags):** also loses 1131202 T80 (S2r140).
- **Tag sensitivity (both tag readings):** also loses 1131202 T80 (S2r140), 1131109 T9 (S1r18), 1131204 T2 (S1r9), 1131204 T17 (S1r25), 1131204 T32 (S1r41).
  The fully literal wording (every Latin/digit code is a tag, the grade letter included) gives the primary result. The losses appear only when a reader takes "a designation of one panel" to exclude letter-only type codes. That costs 1 line row: its moved bare tag reads as a second box. If the reader also counts the grade letter of a class-C box as a tag, 4 heading rows also go to their line noun through the S2 exception. S2 would be firmer if it said whether letter-only codes and grade letters (甲級, C級) are tags.

## Heading test (B1, Q1) on all headings of the enclosure rows' sheets

- 125 headings and block titles: 28 name a panel under both tests, 2 under the old test only (both in one case, with no enclosure row in their scope), 0 under the revised test only.
- 6 headings end in 工程/製作/更新 or an enclosure count; 0 of them name a panel after stripping. So Q1's work-word stripping is not exercised by these 15 sources: no 盤工程-type heading exists. The 2 heading-subset misses are a block-title row where she kept the 箱體 word after the tag and a blank in an older-convention file.

## S11: unpriced, no-status line followed by numbered descendants

- **Strict reading (3 → 3.1, 3-1):** 0 such lines in the 15 sources. No source numbers a child with its parent's number as prefix. The only hyphenated labels are 5 site headings in 2 cases (N-1, N-2 …) whose parent number N has no line.
- **Outline reading** (a line with a unit or quantity, followed by lines with a deeper label format): 23 lines in 2 cases. None names a panel under B1. Among their descendants there are 0 enclosure rows and 0 target rows: the descendants are unpriced, or sit on an all-unpriced bill whose rows are analysis components.
- **Agreement with and without S11:** A 45/65 and B 28/65 both ways, under either reading. S11 does not change any row because no row is affected.
- **Nearest analogue (R51 parents).** 9 enclosure component rows have an unpriced, no-status parent bill line (9 of 9). Her A equals that parent's text read as a heading on 0. It equals the block title's last-segment name on 2. S4 already governs these rows.
- **Recommendation: do not adopt S11 in 046g.** These sources give no evidence for it (0 instances under the strict reading, 0 affected rows under the broad one), and the nearest analogue goes the other way (0 of 9). Record it as an open question for a source that has such a line, and keep the R33 heading definition.

## Q3: panel-heading scopes with two or more enclosure rows

- 28 panel-naming headings or block titles hold enclosure rows. Each governs exactly one (innermost heading): **0 scopes govern two or more**, so the subsidiary-box selection never decides a row here and the replay is the same under any Q3 choice.
- 1 scope holds 3 enclosure rows by raw nesting (1150507 heading S1r55). The source's label formats put two later panel headings inside it, and each of those governs its own row. Her A: the heading's own name on its first row, whose own box noun is not a subsidiary box; each inner heading's name on the other two. This is consistent with Q3 and with the innermost-heading reading.
- Context: 10 scopes whose heading names no panel hold two or more enclosure rows. In 5 of them (site headings, 2 cases), a meter box comes first and keeps its own noun, and the main panel after it gets the site name + 配電盤. That is the direction Q3 encodes, but Q3 does not reach these rows, because the heading names no panel.

## S10: non-exhaustive enclosure list

- Census of priced lines whose head segment (after the prefix and the R52 chain) names a box under B1: 100 lines. 57 are among the 65, 43 are assembly, wiring, busbar, transport or device lines under a panel category word, and 0 other. **S10 adds no enclosure row.** No line in these sources names a terminal box alone.
- 8 of the 65 are not found by a head-segment test:
  - 3 lines whose only enclosure word outside the category is followed by 體. Under B1 these lines name no box at all.
  - 5 lines whose head is a category word missing from the glossary draft (lightning, grounding or level-meter families).
  - A reader applying B1 literally could leave the 3 lines out of the enclosure rows. R56's "houses devices" definition keeps them, but the text does not say so.

## Limits

- This is a fit on the same cases the rule was written from, not a prediction. Denominators are the 65 rows of 15 cases. The 17 target-only and 5 old-template cases are not covered.
- All 18 earlier A misses are still misses: site name + 配電盤 (5), older-convention blanks (5), remark station numbers (3), tags not in the source (2), a kept line noun under a block tag (1), a category word (1) and a column-shifted row (1). The 2 rows above are new misses. On B, the 37 misses are unchanged: 23 unreachable, 10 written in D, 3 typos, 1 shifted row.
