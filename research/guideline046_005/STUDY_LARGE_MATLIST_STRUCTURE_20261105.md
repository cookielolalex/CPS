# Material-list (材料清單) structure study for 046f scoping (public-safe)

Date 2026-11-04. Source role only. I read one 材料-titled file per case, from the project folder, and its v2 inventory. I read no 未填, 已填/OK, generator output or contract file. This report gives counts, generic sheet roles and header-vocabulary words only. Exposed tuning cases only: 1131112, 1131207, 1140304, 1140607, 1140808.

Method: each file was downloaded through the Drive connector and its bytes checked against the Drive size. The three `.xls` files were converted with headless LibreOffice. Each file then went through `build_inventory_xlsx_v2.py` with auto views and every sheet in scope. Counting used the route's `has_content` definition. "Priced" means a number above zero in the unit-price or amount column. "Not estimated" means one of those cells contains 不含估價. "Item-like" means the description cell is non-empty and the row has a quantity or a unit other than 全. The hashes are listed in the private file.

## Files

Each case has exactly one 材料-titled file (one at the project-folder level, none in the production-documents subfolder), and that file is the 材料清單. Every sheet in every file is visible, so there are no hidden sheets. Every file follows the public-works tender template:

- **1131112, 1131207, 1140304 and 1140808.** The sender's quotation fills the template's detail sheet, whose title row has been changed to 材料清單. The summary, analysis and resource sheets are still there, with no prices in them. They look like copies of the contract's sheets, but I did not compare them with the contract.
- **1140607.** The sender edited the contract's detail sheet in place, so its title row still has the template's own title. The sender inserted the 合計 end row in the middle of the sheet, followed by a negotiated-price row and a signature row. Below those, the contract's remaining sections are still on the same sheet.

## Per case

Cells means content cells. "lit/cf" is literal and cached-formula content. "Header" is the row that holds the header vocabulary, with ×n giving how many times it occurs on the sheet. "End" is the first cell in the unit-price or amount column that holds 合計 or 總計.

### 1131112 — all sheets 7,629

| # | Role | Dim | Cells (lit/cf) | Merges | Header | End |
|---|---|---|---:|---:|---|---|
| 1 | summary | 38×7 | 23 (23/0) | 38 | r8 ×1: 項次, 工作項目, 金額(元), 備註 | none (總價 in description column) |
| 2 | bill/detail | 112×9 | 543 (519/24) | 9 | r8 ×1: 項次, 項目及說明, 單位, 數量, 單價, 複價, 廠牌, 型號, 備註 | r100, 單價 column |
| 3 | unit-price analysis | 4704×7 | 7,063 (7,063/0) | 2,192 | r9 ×190: 工料名稱, 單位, 數量, 單價, 複價, 編碼(備註) | none |

- **Bill range:** rows 14–100.
  - 78 item-like lines: 23 priced (21 numbered, 2 unnumbered), 55 not estimated, 0 unpriced with no status.
  - 4 block 小計 rows, all in the description column.
- **Analysis:** 189 blocks with 1,075 components, plus 1 empty template frame. Block references are local integers. 0 blocks link to a bill line by code or name.

### 1131207 — all sheets 4,604

| # | Role | Dim | Cells (lit/cf) | Merges | Header | End |
|---|---|---|---:|---:|---|---|
| 1 | summary | 38×7 | 23 (23/0) | 38 | r8 ×1: 項次, 工作項目, 金額(元), 備註 | none |
| 2 | bill/detail | 88×9 | 452 (424/28) | 9 | r8 ×1: as 1131112 (備註 written 編碼(備註)) | r78, 單價 column |
| 3 | unit-price analysis | 2688×7 | 4,129 (4,129/0) | 1,328 | r9 ×118 | none |

- **Bill range:** rows 11–78. 67 item-like lines: 27 priced (25 numbered, 2 unnumbered), 40 not estimated, 0 unpriced with no status.
- **Analysis:** 114 blocks with 614 components, plus 4 empty frames. Block references are integers. 0 blocks link to a bill line.

### 1140304 — all sheets 2,459

| # | Role | Dim | Cells (lit/cf) | Merges | Header | End |
|---|---|---|---:|---:|---|---|
| 1 | summary | 38×7 | 22 (22/0) | 38 | r8 ×1 | none |
| 2 | bill/detail | 109×9 | 524 (484/40) | 8 | r8 ×1: as 1131112 | r96, 單價 column |
| 3 | unit-price analysis | 672×7 | 992 (992/0) | 352 | r9 ×32 | none |
| 4 | resource statistics | 311×10 | 921 (921/0) | 48 | r9 ×8 (page repeats): 工項代碼, 工項名稱, 單位, 工程用量, 單價, 複價, 人工, 機具, 材料, 雜項 | none |

- **Bill range:** rows 10–96. 83 item-like lines: 36 priced (34 numbered, 2 unnumbered), 47 not estimated, 0 unpriced with no status. Two panel sections follow each other with no heading between them, and numbering restarts at 1 after two formula-zero rows.
- **Analysis:** 31 blocks with 128 components, plus 1 empty frame. 0 blocks link to a bill line.

### 1140607 — all sheets 3,968

| # | Role | Dim | Cells (lit/cf/other) | Merges | Header | End |
|---|---|---|---:|---:|---|---|
| 1 | summary | 38×26 | 46 (46/0) | 38 | r8 ×1 | none (合計 and 總價(總計) in description column) |
| 2 | bill/detail | 288×9 | 999 (806/192/1 missing cache) | 21 | r8 ×1: 項次, 項目及說明, 單位, 數量, 單價, 複價, 編碼(備註). **The brand and model columns have no header label**, although they hold 29 cells in range. | r146, 單價 column |
| 3 | unit-price analysis | 199×7 | 368 (308/60) | 68 | r9 ×8 | none |
| 4 | resource statistics | 209×23 | 2,555 (1,058/1,495/2 missing cache) | 4 | r9 ×1 | none |

- **Bill range:** rows 14–146.
  - 61 item-like lines: 23 priced (21 numbered, 2 unnumbered), 38 not estimated, 0 unpriced with no status.
  - 4 block 小計 rows in the description column.
  - 58 of the 61 lines carry a pay-item code in the remarks column.
- **Analysis:** 8 blocks with 37 components. Block references are outline paths. All 8 blocks link to in-range bill lines, and code, exact name and outline path all agree on each link. 1 parent line is priced and 7 are not estimated.

### 1140808 — all sheets 5,286

| # | Role | Dim | Cells (lit/cf) | Merges | Header | End |
|---|---|---|---:|---:|---|---|
| 1 | bill/detail | 134×9 | 637 (566/71) | 7 | r8 ×1: as 1131112 | r129, 單價 column |
| 2 | unit-price analysis | 1831×7 | 4,649 (3,846/803) | 756 | r9 ×94 | none |

There is no summary sheet.

- **Bill range:** rows 13–129.
  - 77 item-like lines: 27 priced (26 numbered, 1 unnumbered), 50 not estimated, 0 unpriced with no status.
  - 1 section 小計 row in the description column, followed by an unnumbered priced fee line.
  - 76 of the 77 lines carry a pay-item code in the remarks column.
  - Continuation rows carry formula zeros.
- **Analysis:** 94 blocks with 488 components. Block references are outline paths, and every path belongs to other sections of the contract, not to the bill's section. 0 blocks link to a bill line by code, name or path.
- **Owner-fixed prices:** 21 components in 8 of the blocks have numeric unit prices, each with an owner-fixed-price remark. This is the only sheet outside the five bill sheets that holds nonzero prices.

## Summary table

| Case | Bill | Summary | Analysis | Resource | Bill determinable | R51 lines |
|---|---:|---:|---:|---:|---|---:|
| 1131112 | 543 | 23 | 7,063 | — | Y | 0 |
| 1131207 | 452 | 23 | 4,129 | — | Y | 0 |
| 1140304 | 524 | 22 | 992 | 921 | Y | 0 |
| 1140607 | 999 | 46 | 368 | 2,555 | Y | 0 |
| 1140808 | 637 | — | 4,649 | — | Y | 0 |

## Q1. One bill sheet per case?

Yes. In every case exactly one sheet is the R49 bill sheet, and I am highly confident of it. That sheet is the only one that has all three signals:

- a single, non-repeated header row containing 項次, a name word, 單位, 數量, 單價 and 複價;
- priced lines below that header;
- a cell in the unit-price column holding 合計 (cell text exactly 合計 in all five).

**Proposed deterministic rule BILL1.** Consider every sheet, hidden ones included. Normalise each cell's text by removing all whitespace, including U+3000. A sheet is a candidate when all of these hold:

- (a) exactly one row has header cells matching all of: 項次; a name word (項目及說明, 名稱, 品名 or 材料名稱); 單位; 數量; 單價; and 複價 or 金額. No other row on the sheet has the same header set.
- (b) below that row, a cell in the 單價 or 複價 column has normalised text exactly 合計 or 總計. The first such cell is the R49 end row.
- (c) at least one cell in the 單價 or 複價 column, between the header and the end row, holds a number above zero.

With exactly one candidate, that sheet is the bill sheet. With zero or more than one, the case is held for the scope reader or the owner.

Result: BILL1 finds exactly one candidate in 5 of 5 cases, always the bill sheet. Weaker variants fail:

- **"Title row says 材料清單"** finds nothing in 1140607.
- **"Header has 廠牌 and 型號"** finds nothing in 1140607.
- **"Only sheet with nonzero prices"** finds 2 sheets in 1140808, because of the owner-fixed analysis prices.
- **"Sheet name contains 詳細"** works on all five, but it depends on template naming.

Signal (a) alone, or (b) alone, also isolates the bill sheet in all five cases.

**Where BILL1 would fail:**

- the header split over two rows or merged under a parent heading (for example 金額 over 單價/複價);
- vocabulary variants: 品名, 規格, a unit-suffixed 單價(元), or 小計 used as an amount header;
- several bill-like sheets: per-site sheets, a change or addition sheet, or the contract's original detail sheet left next to the sender's copy (the in-place pattern of 1140607 makes this plausible);
- a total with no label in the price columns, or a total written in the description column. The R49 fallback, which ends the range at the last item line before the signature, then needs a relaxed rule;
- a block total written in a price column (甲站合計), which is why the text must be exactly 合計 or 總計;
- a one-block analysis sheet whose header row also carries 項次, which the repeated-header test cannot catch;
- contract-only jobs, which have no sender prices and give zero candidates. Under R47b that is correct.

## Q2. Content cells

| Case | Bill only | Bill + summary | All sheets |
|---|---:|---:|---:|
| 1131112 | 543 | 566 | 7,629 |
| 1131207 | 452 | 475 | 4,604 |
| 1140304 | 524 | 546 | 2,459 |
| 1140607 | 999 | 1,045 | 3,968 |
| 1140808 | 637 | 637 (no summary) | 5,286 |

How the bill sheet's cells split, as before the first item line / in range / after the end row:

| Case | Before | In range | After |
|---|---:|---:|---:|
| 1131112 | 28 | 510 | 5 |
| 1131207 | 22 | 428 | 2 |
| 1140304 | 21 | 499 | 4 |
| 1140607 | 29 | 572 | 398 |
| 1140808 | 28 | 601 | 8 |

## Q3. Does R51 trigger?

No, in none of the five. Every in-range item-like line is either priced or not estimated, so 0 lines are unpriced with no status, and the all-unpriced fallback never applies. Every analysis block sits on a separate sheet, outside the bill-sheet range.

Only 1140607 has analysis blocks linked to in-range lines: 8 blocks, whose parents are 1 priced line and 7 not-estimated lines. Under R51's last sentence those components are never rows. They would be `analysis_component` items (R21/R25), but only if the analysis sheet is in scope.

## Q4. Content after the end row on the bill sheet

| Case | Rows | Cells | What they are |
|---|---:|---:|---|
| 1131112 | 3 | 5 | negotiated-price row, signature, template footer |
| 1131207 | 2 | 2 | signature, footer |
| 1140304 | 2 | 4 | negotiated price, signature |
| 1140607 | 122 | 398 | negotiated price and signature, then the contract's remaining sections |
| 1140808 | 5 | 8 | negotiated price, signature, formula-zero rows |

The 1140607 remainder contains:

- 31 item-like rows: 22 priced at owner-fixed unit prices and 9 with zero amounts;
- 10 total or subtotal rows in the description column, including a 合計 and a 總價(總計).

Under R49 all of it is out of range (`excluded_supply`). A priced-line test that ignored the range would wrongly add 22 rows.

## Q5. Proposed scope stage

This sits between source preparation and generation. It is a source role, and its output is frozen before any generation.

1. **Full inventory first.** Build the v2 inventory with every sheet in scope, then freeze and hash it.

2. **Deterministic scope tool.** The tool proposes each sheet's role and `in_scope` flag:
   - The **bill sheet** is the single BILL1 candidate, and it is always in scope. Zero or several candidates means hold.
   - An **analysis sheet** is in scope only in these cases:
     - (i) every in-range bill line is unpriced with no status (the R51 fallback); or
     - (ii) some in-range bill line that is unpriced with no status has a block linked by code, name or outline path; or
     - (iii) as an owner option, at least one block links to any in-range line, because of the R21/R25 `analysis_component` obligation. 1140607 meets (iii); the other four do not.
   - **Summary, resource-statistics and other sheets** are out of scope. None of them yields rows (R49; guideline §3).
   - The tool **flags** every hidden sheet, every "other" sheet, every second near-candidate, and every out-of-scope sheet with nonzero price cells or 不含估價. 1140808's analysis sheet is flagged by the last test, because of its owner-fixed prices.

3. **Separate scope reader.** A fresh context receives only the scope digest and the package's R47b and R49–R51. For each sheet it returns the role, the `in_scope` flag and a reason. It also names the bill sheet and the end row, and gives a reason for each flag.

4. **Agreement check.** The tool and the reader must agree on:
   - the bill-sheet index;
   - the end row;
   - every `in_scope` flag.

   If they agree, the decision is frozen. If they disagree, the case is held for the owner. There is no tie-break run.

   I recommend using both. The rule is cheap and auditable; the reader catches layout variants the rule misses. Choosing the bill sheet is the most consequential source decision under R49.

5. **Scoped inventory.** It is a projection of the full inventory:
   - `sheets[]` is unchanged except for the `in_scope` flags;
   - cells and views of out-of-scope sheets are removed;
   - all other cell records are byte-identical;
   - a `context:scope` fact is added.

   The route's census invariant (rows × columns of the in-scope sheets equals the number of cells) still holds. Pin both hashes in the job configuration.

**Digest contents.** For each sheet:

- index, name, visibility, dimensions, content cells (literal, cached and other), merges and formula records;
- the title rows above the first header row;
- the first header row in full; any repeats as a count and their row numbers;
- the first 5 content rows below the header;
- each row holding 合計 or 總計 in a price column, with 2 rows of context either side (at most 3 such rows);
- the first 3 other total-label rows;
- the first 2 block headings (工作項目) and the total number of block headings;
- the last 3 content rows;
- computed counts: nonzero price cells; 不含估價 cells; for each candidate, in-range priced, not-estimated and unpriced lines; block-link counts.

Measured digest size: 1131112 116 cells, 1131207 128, 1140304 173, 1140607 283, 1140808 117. Wide resource sheets dominate the larger digests; capping each row at its first 10 columns would keep every case under about 200.

**Scoped sizes.**
- Bill sheet only: 543, 452, 524, 999 and 637 cells.
- With option (iii), 1140607 becomes 999 + 368 = 1,367 cells.
- Every scoped size is far below the admitted writer's 5,000-entry `nonitems` cap.

**Telling the generator.** Add a `context:scope` fact with, for each sheet:
- index, name, role, visibility, dimensions, content-cell count and `in_scope` flag;
- a reason: for example "summary: never yields rows (R49)", "analysis: no block linked to an in-range bill line; R51 not triggered", or "resource statistics: source check only".

The fact also records the rule version, the digest hash and the agreement result.

The guideline also needs one sentence. Out-of-scope sheets are not missing or unreadable sources, so they are not grounds for a §1 hold. They have no census, and no field may cite or reconstruct them. `context:scope` is never a field proof; the route already nulls a field proven only by context, other than L, M and N.

**What could go wrong, and how it would be caught:**

| Risk | Detection |
|---|---|
| Wrong or second bill sheet | Zero or several BILL1 candidates, or tool–reader disagreement, means hold. An audit recomputes BILL1 on the frozen full inventory. After the freeze, the evaluator classifies unmatched historical rows whose source lies on a scoped-out sheet as scope loss. |
| A row-bearing sheet scoped out (missed R51) | The tool computes the R51 conditions on the full inventory before scoping, and the audit re-derives them. The route cannot see scoped-out cells, so this check must live in the scope tool and its audit. |
| Linked analysis components dropped (1140607) | `context:scope` records the linked-block count for each out-of-scope sheet. The route warns when that count is above 0. This needs an owner decision on option (iii). |
| Priced content outside scope | The flag requires a reason. The 1140808 owner-fixed component prices are the expected example. |
| Generator holds because sheets are "missing" | The guideline sentence and `context:scope` prevent it. A held status that cites such a sheet is visible to the evaluator. |
| Generator cites a scoped-out cell | The existing `UNKNOWN_CELL_REF` check rejects it. |
| Rows taken from after the end row on an in-scope bill sheet (1140607: 398 cells, 22 priced lines) | Proposed route check: a demand item citing a bill-sheet cell below the `context:scope` end row is warned or invalid. The evaluator would also see extra rows. |
| Scoped inventory is not a faithful projection | A verifier compares the scoped inventory with the full one record by record, and checks both hashes. |

Scope is per sheet, because the route requires a whole-sheet census. Out-of-range rows on the bill sheet therefore stay in the census as `excluded_supply`. Sub-sheet scoping would need a route change, and I do not recommend it.

## Limitations

- **Five tuning cases only.** I did not test the rule on other layouts.
- **Item-like and link detection are heuristics.** The link counts use code, exact-name and name-prefix matching. In 1140607 a looser name test gave 9 hits against 8 confirmed links.
- **Converted files.** The `.xls` inventories describe LibreOffice conversions, not the original bytes.
- **Provenance not checked.** Adoption of the 材料清單 and its version were not checked.
