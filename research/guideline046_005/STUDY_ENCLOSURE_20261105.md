# Enclosure A/B creator-practice study for 046g (public-safe)

Date 2026-11-05. Evaluation role, exposed tuning cases only. No reserved case, qualification candidate, or `qual_screen/files` file was opened. This report gives counts and generic findings. Every example is invented (甲-1 控制盤, 乙 PANEL, 丙站). Per-row evidence, hashes and scripts are in the private JSON beside this file.

## Scope

- **Targets.** The 37 `eval_targets` cases were read with the `compare_target049` loader. **32 use the current template** (I/J = 型號/廠牌 in canonical order, unit price in Q). 5 older-template cases are excluded.
- **Sources (材料清單).** 15 of the 32 current-template cases have a bound material list in the named locations: 4 dev cases (the fifth dev case uses the older template) and 11 family-screen cases. The 5 large-structure cases are not in `eval_targets`, and neither are 5 of the family-screen cases, so those 10 were not used. None of the other current-template cases has a contract inventory in the private bundle, so the remaining **17 cases are target-only**. For them the study can count rows and describe the form of A, but cannot say where A came from.
- **Definitions.**
  - An *enclosure row* is a target row for a priced line (or a line with a status) that supplies an enclosure body: a panel, control box, meter box, instrument box, sub-distribution box, isolation box or grounding test box.
  - Junction and pull boxes (接線箱, 拉線箱, 接線盒), existing-panel work, enclosure parts (door, base plate) and service lines (assembly, lifting, testing, bases) are not enclosure rows.
  - Target rows were aligned with source lines by an order-preserving match on text, unit, quantity and unit price. Every enclosure pairing was then checked by hand.
- **Comparison.** Values are compared in the evaluator's normalized mode (NFKC, whitespace collapsed).

## Q1. Which rows carry A/B

**Pooled.** 135 enclosure rows across the 32 cases; 103 carry A. 351 rows carry A in total, so 248 A-bearing rows are not enclosure rows.

Case-level pattern (32 cases):

| Pattern | Cases | Years |
|---|---:|---|
| A/B only on enclosure rows | 21 | 113: 7, 114: 12 of 12, 115: 2 |
| A/B of the panel group on **every** row of the group | 3 | 115 only (3 of the 5 year-115 cases) |
| No A/B at all | 3 | 113 |
| A on the first row of each group, which is a pole or switch line, not the enclosure | 2 | 113 |
| A on the first row of each site section: the site name, on the first box only | 2 | 113 |
| A on the first row of each section, mostly the enclosure | 1 | 113 |

- **Enclosure rows per case:** 1–10 (1 row: 3 cases; 2: 7; 3: 6; 4: 4; 5: 4; 6: 3; 7: 1; 9: 1; 10: 3).
- **Several enclosures in one job are normal.** Each enclosure gets its own A/B row, for example one meter box plus one main panel per site section.
- **One target lists 7 named panel rows.** Only the first carries a quantity (7) and the price, so a 7-panel line appears to be split into named rows. This case is target-only; its source was not seen.
- **Heading rows.** One 113 file copies panel-heading lines as rows, but leaves A blank on them. No file puts A on a heading row in place of the enclosure row.
- **A without B, and B without A.** In 114–115 files A and B always come together. A without B appears only in 113 files that follow an older convention. B without A appears in two 113 files: in one, B holds an enclosure-type word; in the other, B holds material names because the columns were shifted (18 rows).

| Case | Source here | Pattern | Enclosure rows | with A | Other rows with A |
|---|---|---|---:|---:|---:|
| 1130304 | yes | enclosure rows (+ column-shifted rows using B) | 3 | 3 | 0 |
| 1130402 | no | enclosure rows | 2 | 2 | 0 |
| 1130503 | no | none | 3 | 0 | 0 |
| 1130504 | no | section first row, site name | 10 | 4 | 0 |
| 1130505 | no | section first row, site name | 5 | 2 | 0 |
| 1130605 | no | none | 4 | 0 | 0 |
| 1130803 | yes | none | 1 | 0 | 0 |
| 1130807 | no | group first row | 5 | 0 | 5 |
| 1130810 | no | group first row | 4 | 0 | 3 |
| 1130907 | yes | enclosure rows | 3 | 3 | 0 |
| 1131006 | yes | section first row | 10 | 6 | 1 |
| 1131008 | no | enclosure rows (site name) | 3 | 1 | 0 |
| 1131109 | yes | enclosure rows | 2 | 2 | 0 |
| 1131202 | yes | enclosure rows | 6 | 6 | 0 |
| 1131204 | yes | enclosure rows | 9 | 9 | 0 |
| 1140104 | no | enclosure rows (+ parts, one removal row) | 2 | 2 | 3 |
| 1140205 | no | enclosure rows | 10 | 10 | 0 |
| 1140207 | yes | enclosure rows | 2 | 2 | 0 |
| 1140307 | no | enclosure rows | 5 | 5 | 0 |
| 1140312 | yes | enclosure rows | 6 | 6 | 0 |
| 1140506 | yes | enclosure rows | 1 | 1 | 0 |
| 1140507 | no | enclosure rows | 1 | 1 | 0 |
| 1140508 | no | enclosure rows | 2 | 2 | 0 |
| 1140805 | no | enclosure rows | 3 | 3 | 0 |
| 1140807 | yes | enclosure rows | 3 | 3 | 0 |
| 1141001 | yes | enclosure rows | 6 | 6 | 0 |
| 1141002 | yes | enclosure rows | 4 | 4 | 0 |
| 1150101 | no | enclosure rows | 7 | 7 | 0 |
| 1150301 | no | group, all rows | 2 | 2 | 80 |
| 1150507 | yes | group, all rows | 4 | 4 | 86 |
| 1150509 | no | group, all rows | 2 | 2 | 70 |
| 1150601 | yes | enclosure rows | 5 | 5 | 0 |

## Q2. What she writes in A (15 source cases, 65 enclosure rows)

| A class | Rows |
|---|---:|
| Section-heading text: item label removed, plus a leading category segment (低壓配電盤，) or a trailing 設備 | 24 |
| Analysis-block title's trailing panel tag (R51 component rows) | 2 |
| The line's own enclosure noun phrase, qualifiers kept, no tag in the line | 18 |
| The line's noun with the line's own tag kept, including a tag the line gives in a later segment | 4 |
| The line's tag noun plus station numbers from the line's remark cell | 3 |
| Place name from a work/site heading + a generic 配電盤 | 5 |
| A tag or qualifier that the bound source does not contain | 2 |
| The line's leading category word instead of its noun | 1 |
| Blank | 5 |
| Column-shifted row | 1 |

**The trigger is a panel-naming heading.** A heading names a panel when its text, after the label and category are removed, contains 盤, 箱, 櫃, PANEL or PNL (`[2] 甲-1 PANEL`, `<3> 丁2盤設備`).

- **The first enclosure line under such a heading (28 rows):** A is the heading's name on 26. On 1 she kept the line noun with its tag; 1 is blank.
- **No such heading (work, site or cost heading, 37 rows):** A comes from the line on 24 (18 noun, 3 noun with tag, 3 tag with remark numbers). The rest: 5 site name + 配電盤, 2 not in the source, 4 blank, 1 category word, 1 shifted row.

**Tags are always kept.** On all 30 rows where the line or its panel heading carries a tag, A keeps the tag (30/30). Current R56's "without a tag" example (CP-1 控制盤 → 控制盤) is the opposite of her practice. The 17 target-only cases agree: of 43 non-blank A values, 26 contain a tag (tag + PANEL/PNL/盤 18, tag alone 4, noun + tag 4). The others are site/group names (10), generic nouns (4) and qualified nouns (3).

**Qualifiers are kept, and the generic word is not substituted.** Invented examples: 雙層式電表箱 stays whole and is not reduced to 電表箱. A type parenthesis stays (控制箱(屋外型)). A material or dimension parenthesis is dropped (液位儀表箱(SUS304) → 液位儀表箱; 甲盤(W:700，H:1800，D:500) → 甲盤). When the line names two boxes, the last one is used (2 of 2).

**Exceptions that no source rule reaches:**
- In one case family, the main panel under a site heading gets the place name + 配電盤, while the meter box in the same section does not (5 rows, 2 cases).
- Station numbers from the remark cell (3 rows, 1 case).
- Tags that come from outside the bound source (2 rows).

## Q3. B

- **Where the dimensions come from (65 rows):**
  - 28: W/H/D-labelled dimensions written inside the line's description cell (`W:800，H:2000，D:600`, `(W)600(H)1500(D)400`). All 28 agree with her numbers.
  - 23: filled by her, but the numbers appear nowhere in the bound workbook (no cell or row holds all three). These are unreachable.
  - 13: B blank. Of these, 10 are in one 113 file that writes the dimensions in D instead, 2 have dimensions only in the remark cell, and 1 has none.
  - 1: column-shifted row.
- **No B came from a heading or from the remark cell.**
- **Format on all enclosure rows (32 cases).** 81 are `<w>W*<h>H*<d>D`. The rest: 2 with a trailing uncertainty note "(…)", 3 with letters missing (typos, 1 case), 1 written `W<w>*H<h>*D<d>`, 4 holding non-dimension text, and 44 blank (all in 113 files).
- **Never a unit, never a thickness on an enclosure row.** Only two part rows (a base plate and a door), which are not enclosure rows, carry `…*2.0t(mm)`.
- **Year trend.** In 114–115 files every enclosure row carries B, even when the source gives no dimensions.

## Q4. Enclosure lines without A

32 of 135 enclosure rows have A blank. 30 of them are in 113 files that use another A convention:
- no A at all: 8;
- A on the group's first row instead: 9;
- site name on the first box only: 9;
- A on the section's first row: 4.

Under the enclosure-row convention (21 cases, 85 enclosure rows), only 2 are blank: both isolation boxes, in one 113 file. That file also writes the dimensions in D.

Other observations:
- Price does not decide the blank: all 32 blank rows are priced.
- An unpriced line with no status is not a row at all. This happens, for example, with the bill-level panel line whose analysis components are the rows.
- The one not-estimated enclosure row seen (a control box) has A blank, as R56 says.
- Junction/pull boxes never carry A (3 rows).
- One not-estimated removal line for an existing panel does carry the panel name in A (1 row).

## Q5. Device rows inside an enclosure group

- **Group-wide cases.** In the 3 year-115 group-wide cases, every row of the group carries the group's A and B: 236 rows, with the same values as the group's enclosure row. These are devices, not-estimated lines, labour and fees.
- **Group-first-row cases.** In the 3 group-first-row cases, the group name sits on the group's first item row (9 rows).
- **Everywhere else.** In the other 26 cases no device row carries A.
- **No source signal.** One of the group-wide cases has the same section structure as a 114 sibling that is enclosure-only.

## Proposed replacement R56 A/B sentence (046g draft)

> **A and B (enclosure row only).**
>
> **A, panel section.** When the line is the first enclosure line under a section heading or analysis block that names a panel, A is that name. Write the heading text without its item label, without a leading category segment (低壓配電盤，) and without a trailing 設備:
> - `[2] 甲-1 PANEL` → 甲-1 PANEL
> - `[1] 低壓配電盤，乙 PANEL (丙站)` → 乙 PANEL (丙站)
> - `<3> 丁2盤設備` → 丁2盤
> - block title `工作項目：低壓配電盤，一般屋外型，戊 PNL` → 戊 PNL
>
> A heading names a panel when, after these removals, it contains 盤, 箱, 櫃, PANEL or PNL. Work, site and cost headings (`<2-1> 甲站機電工程`, `<A> 設備費(項目)`) do not.
>
> **A, otherwise.** A is the line's own enclosure noun phrase. Drop the prefix 產品 and a leading category segment, including one joined by a hyphen (低壓配電盤-丁盤). Take the first segment that names a box and cut it after its last enclosure word. Keep the qualifiers and the tag, never reducing to a generic word:
> - 雙層式電表箱 SUS304 … → 雙層式電表箱
> - (庚型電表箱，30A以上) → 庚型電表箱
> - 甲-1 控制盤 → 甲-1 控制盤
>
> Keep a type parenthesis (控制箱(屋外型)). Drop a dimension or material parenthesis (液位儀表箱(SUS304) → 液位儀表箱).
>
> A bare panel tag that the line gives in a later segment goes before the noun (分電箱，鋼板，己 PNL → 己 PNL分電箱). When the line names two boxes, use the last (甲端子箱(含銅排)，乙測試箱(含配件) → 乙測試箱).
>
> **B.** B is `<w>W*<h>H*<d>D`, in whole millimetres with no unit and no thickness. Take it from W/H/D-labelled dimensions in the line's description cell (`W:800，H:2000，D:600` → 800W*2000H*600D; `(W)600(H)1500(D)400`; `-W300×H300×D150mm`). Dimensions only in a remark or code cell, or absent, leave B null with a reason.
>
> **Scope.** A grounding test box, instrument box, isolation box or sub-distribution box is an enclosure. A junction or pull box, an existing panel, an enclosure part or a not-estimated enclosure is not.

## Simulated agreement on the 15 source cases (65 enclosure rows)

| | A rows reproduced | B rows reproduced |
|---|---:|---:|
| **Proposed** | **47 / 65** | 28 / 65 |
| Proposed without the last-box clause | 45 / 65 | 28 / 65 |
| Current R56, literal deterministic reading | 15 / 65 | 26 / 65 |
| 4 dev cases, proposed | 6 / 12 | 3 / 12 |
| 4 dev cases, actual frozen 046f readers | 1 / 12 | 3 / 12 |

- **Counting.** A row counts as reproduced when the normalized value equals hers, including blank = blank.
- **Current-rule B.** The current reading reads dimensions from the remark cell too, which costs it the 2 remark-only rows.
- **Years.** Proposed A is 23/34 on 113 cases and 22/31 on 114–115 cases. Current R56 is 3/34 and 12/31.

**Remaining A misses (18):**
- 5 blank in older-convention files;
- 5 site name + 配電盤;
- 3 remark station numbers;
- 2 tags not in the source;
- 1 kept line noun under a block tag;
- 1 category word;
- 1 column-shifted row.

**Remaining B misses (37):**
- 23 unreachable;
- 10 dimensions she wrote in D;
- 3 typos;
- 1 shifted row.

The B rule matches every reachable, correctly typed B.

**Not covered by any enclosure-row rule.** In the 3 group-wide cases, the A/B she writes on every row of the group adds 140–172 positions per case that the proposed rule misses (172 in the one source case, 1150507). This is a case-level choice with no signal in the source, so it needs an owner decision: enclosure row only, which is her majority practice (21 of 32 cases, 12 of 12 in 114), or group-wide, which 3 of 5 year-115 cases use.
