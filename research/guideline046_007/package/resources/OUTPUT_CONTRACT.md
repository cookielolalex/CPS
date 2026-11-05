# Output contract (candidate 046g, draft)

Return one JSON file conforming to `SEMANTIC_RESPONSE.schema.json` (`cps.semantic-source-refs.v2`) and to every rule in `SOURCE_REFERENCE_CONTRACT.md`. The response states your semantic decisions and points at exact inventory cells and context facts. The adapter later copies the source text and builds the writer carrier. It cannot fix or complete your response.

046f reproduces the historical 未填 creator's majority practice (FIELD_ROLES R47b–R58, owner decisions O10–O20). Where R47b–R59 and an older sentence of this package disagree, R47b–R59 govern. 046g adds scoped packets for large 材料清單 workbooks (FIELD_ROLES R59; interface point 4a); on a packet without `context:scope` nothing changes.

## What you receive

- `SOURCE_INVENTORY.json`: the complete typed positional inventory of the bound source: the company material list (材料清單) when the job has one, otherwise the contract (R47b). The other document is not supplied, and no field may cite or copy from it. The inventory is authoritative for characters, types and addresses. Compute `inventory_sha256` as the SHA-256 of this file's exact bytes.
- `view_NN.png`: reconstructed inspection images of the same saved cells. They help you see the layout. They do not add characters, and their line wrapping is artificial.
- `context_facts` in the inventory:
  - job inputs (R48): `context:case_identity` (internal case id), `context:customer_name` (customer full name) and `context:project_name` (project short name);
  - company resources (R58): `context:company_name`, `context:glossary` (generic prefix words, category words, the generic enclosure word and device abbreviations) and, on a contract job only, `context:brand_table` (brand and model by device type and rating band). A 材料清單 packet has no brand table (O17): I and J then come only from its cells.

  The resources are owner-reviewed private company data, supplied with each packet and pinned by SHA-256. Use them only as R52, R55 and R56 say. The values in this package's examples are invented.
  - on a scoped packet only (R59): `context:scope`, JSON text naming every sheet of the workbook with its role, dimensions, content-cell count, `in_scope` flag and reason, the bill sheet, its header row and the R49 end row. The inventory then holds only the in-scope sheets. Read it before the cells. It is not field evidence.

## How to build the response

1. **Read everything.** Read the whole inventory and all views (on a scoped packet: every in-scope sheet; the scoped-out sheets are not supplied and are not missing, R59). Identify sheet roles, the detailed bill sheet that carries the sender's prices, its column header and column roles, every logical item and continuation, sections, totals, analysis blocks and every nonitem region.
2. **Find the quoted range (R49).** It runs from the first item line under the column header down to the end row: the row whose unit-price or amount column holds 合計 or 總計. A 合計 written in the description column is a block total, not the end, and a total labelled for a block (小計, 甲站合計) does not end the range. Repeated site sections and goods/labour subsections inside the range are all in it. Summary sheets never yield rows. When every bill line has no price and no status, rows come from the analysis sheet (R51). On a scoped packet the bill sheet and end row are those of `context:scope` (R59 item 2).
3. **Decide the rows (R50, R51).** Inside the range, in source order, write one `demand` item for each:
   - priced line (its unit-price or amount cell holds a number above zero);
   - not-estimated line: its unit-price or amount cell contains 不含估價; cite that cell. A 以下不含估價 heading is not inherited;
   - unnumbered fee line of the sender before the end row (freight, drawing, design or management fee). Fee lines are rows only when priced or not estimated.

   Analysis components become the rows instead of their parent when the parent bill line has no price and no status and its block lies inside the quoted range, or when every bill line has no price and no status (R51). Write them as `demand` items, block by block in analysis order. A no-price, no-status line whose block lies outside the range is `excluded_supply`, and its block is `analysis_unlinked`. When the parent is priced or not estimated, its components are never rows: they stay `analysis_component` items with a component link (R21, R25), or `analysis_unlinked` cells (R46). On a scoped packet a block of a priced or not-estimated parent gives no `analysis_component` items or links; its cells are `analysis_unlinked` with the R59 reason.

   Never split or merge lines, and never add rows. A remark saying a line is not included or not used does not remove it. Supply and separate-contract markers (業主供料, 甲供, 業主自備, 業主自理, 另案, 另案發包, supplied by others) do not decide inclusion and are never copied into a field. Provisionally (O10), a panel line marked owner-supplied is omitted with the lines inside it (its numbered descendants or its R33 heading scope) only when no line inside it has a price inside the quoted range.
4. **Classify every other content cell (census, R11, R50, R51).** Assign exactly one primary `source_roles` entry to every content cell, and none to empty cells.

   | Cells | Role | Reason (begin with) |
   |---|---|---|
   | A row's own description, unit, quantity, unit-price, amount and remark cells | `demand_content` (for R51 component rows, `demand_content` or `analysis_content`; R51 does not say which, and the route accepts both) | what the cells are |
   | Item numbers | `item_identifier` | |
   | An in-range line with no price and no status | `excluded_supply` (every cell, including its item number and continuation rows) | "no enclosure and no estimate: not in the quoted supply (R45)", then the condition: price cells empty, or the text they hold |
   | An item-like line after the end row | `excluded_supply` | "outside the quoted range (R49)" |
   | On a scoped packet: every content cell on a bill-sheet row after the end row | `excluded_supply` | "outside the quoted range (R49, R59)" |
   | An owner-supplied panel line omitted under O10, and the lines inside it (including a not-estimated line inside it) | `excluded_supply` (R50) | name the marker and "owner-supplied panel with no priced line inside the quoted range (R50, provisional O10)" |
   | A no-price, no-status line whose analysis block lies outside the quoted range; its block | `excluded_supply` (the line); `analysis_unlinked` (the block, R46) | per R45 (the line); per R46 (the block) |
   | The parent line of components listed as rows | `section` | "parent of analysis components listed as rows (R51)" |
   | Headings, section titles | `section` | |
   | Block totals, subtotals, the end row, tax, negotiation, amount-in-words | `financial_summary` | |
   | Validity, delivery, payment, freight and other commercial notes | `commercial_note` | |
   | Pointers to documents not in the packet | `document_reference` | |
   | Title, column headers, page headers | `header` | |
   | Signature lines, page footers | `footer` | |
   | Anything you cannot resolve | `unresolved` | name the possible roles, or say why none fits |

   Every `demand_content`/`analysis_content` cell must be cited by its item. No item may cite an `excluded_supply` or `analysis_unlinked` cell. A single role entry can list many refs that share one reason.
5. **Fill the 17 values (R48, R52–R57)** and give each column either a non-null proof (`refs`, `transformation`, `role_basis`) or a specific null `reason`.

   | Field | Rule |
   |---|---|
   | A, B | Only on an enclosure row (R56, O30): a priced line supplying an enclosure, a 盤, 箱 or 櫃 housing devices (for example a control, meter, instrument, isolation, sub-distribution, test or terminal box; the list is not exhaustive; not 接線盒, 接線箱, 拉線箱, 既設盤, enclosure parts or services). A = the panel name of the section heading or block title that names a panel (R56: without the item or block label, a leading category segment such as 低壓配電盤，, and trailing 設備, 工程, 製作, 更新 or an enclosure count; it must end with its one box noun, optionally followed by a tag or one bracket), on the first enclosure row under it that is not a meter, terminal, test, isolation or instrument box (else the first), unless the name has no tag and the row's own box noun has one; otherwise the line's own enclosure noun phrase with qualifiers and tag (甲-1 控制盤; 控制盤 CP-1; 分電箱，鋼板，己 PNL → 己 PNL分電箱; two boxes → the last, a 附…/含… box is not a second box). B = `<w>W*<h>H*<d>D` in mm (no unit means mm), in W, H, D order, from W/H/D- or 寬/高/深-labelled dimensions in the line's own description only; remark-only, partial, other-unit or absent dimensions leave B null with a reason. Component rows take only their block's title (R51, R56). A not-estimated enclosure is an ordinary row. Null on every other row, including the devices of a panel. |
   | C, D | R52. Segments are separated by ，,、；; only; a separate specification cell joins with '，', continuation rows with no separator. Drop the glossary's generic prefix word and the leading category chain (segments ending in 類, or glossary category words, dropped only while a later noun segment remains). Then, in this order: glossary (the noun segment begins with a glossary device: C = its abbreviation, D = the rest or null); acronym (equipment line with a digit-free Latin acronym fused to or bracketed after the noun: C = the acronym alone, O20; material, light-source, current and protocol tokens stay in D); single segment (C null, D = the text); head noun (equipment line: C = the noun segment cut before its first digit or bracket, D = the rest); other (C null, D = the description without the prefix and the chain). Equipment families are exhaustive (switches, breakers, contactors, relays, timers, meters, instruments, surge protectors and arresters, pumps, motors, fans, lamps, sockets, transformers, starters) and every glossary device is equipment. Only the prefix, the chain, C's text, markers, references and cost codes leave the description; the rest stays verbatim except R53 (rating tokens joined with one space on every line type). Enclosure row: C = the glossary's generic enclosure word; D = the description without the prefix, every leading category segment, the text A took from the line and the dimensions (R56). Remarks, code columns and price text never enter C or D. Acronym step: D = the rest after the noun and its acronym, or null (自動切換開關(ATS) 3P160A → C ATS, D 3P160A). A noun segment whose first token contains a digit (AC220V 指示燈) is handled as a description starting with a digit: C null, D = the text. |
   | E, F | The line's own unit and quantity cells, verbatim (R57). |
   | G, H | Null (R57). |
   | I, J | Not-estimated line: I = J = 不含估價, citing the unit-price or amount cell that contains it. Any priced line: a brand or model stated in the line's own cells (including the source's brand/model columns). With a 材料清單, I and J come only from its cells. Otherwise, only when the bound source is the contract, on a priced equipment line: the brand table by device type and rating band; a breaker whose rating no entry covers takes J = the table's breaker brand (O18), I null; a line stating only a brand or only a model takes the missing value only when the entry's brand matches; anything else not covered → null with a reason. Enclosure row: I null, J = the brand cell if stated, else the company name (R55, R56). |
   | K, O, P | Null (R48). |
   | L, M, N | Copied exactly from `context:case_identity`, `context:customer_name` and `context:project_name`, each citing only its own context ref, on every item, rows and analysis components alike (R48). Never infer M or N from a letterhead (R6). |
   | Q | Priced line: its unit price as a number, cited from its unit-price cell, never the amount. Null on not-estimated lines (R54). |

   **Citations (R58).** A field derived through a company resource cites the source cell it was derived from together with the context ref: C from the glossary cites the description cell and `context:glossary`; I and J from the brand table (contract jobs only) cite the description cell and `context:brand_table`; J on an enclosure row cites the line's description cell and `context:company_name`. L, M and N cite only their job-input context refs. The transformation says how the value was obtained from the cited text; the role basis says why that text has this field role. Keep values exactly as the policy and source support them; never adjust a value to pass a check.
6. **Fill `raw_refs`** per `SOURCE_REFERENCE_CONTRACT.md` §3: description and remarks streams in row-major order, and at most one cell each for unit, quantity, unit price and amount. Never list an empty cell, and give a specific reason for every empty selection. Set `anchor_refs` to the item's identity cell(s) on its first row, normally the item number; an unnumbered fee line or component row uses the first cell of its description.
7. **Keep the earlier mechanics.** Source reading, raw and provenance mechanics, census roles (R11, R29, R45, R46), holds (R42), document references (R5: never in C or D) and cost-line codes (R23) still apply where R47b–R59 do not address them. Make every null reason true of the whole source (R9). Record total/subtotal discrepancies in `limitations` without repairing them (R10).
8. **Set statuses.** Item `status` is `research_draft` or `held`; `held` needs review reasons. Top-level `status` is `research_draft`, `partial` (some scope is unresolved or held) or `held`. Record every unresolved obligation in `limitations` or review reasons.

Use IDs such as `R001…` for rows in source order and `C001…` for `analysis_component` items in analysis order. Do not form groups for contractual sections: no row except the enclosure row carries A or B (R56).

## Interface points (route v4.3)

Route v4.1 resolved two of the interface questions recorded for 046f and kept one mechanism; route v4.2 keeps them and adds the policy checks in point 4; route v4.3 (candidate 046g) keeps all of them and adds the scope checks in point 4a. Follow them; do not change a value to avoid a warning.

1. **A null C may be `research_draft`** (FIELD_ROLES R57). Give C a specific null reason as for any null field. `check` warns `R57_NULL_C_RESEARCH_DRAFT`; the export then needs the portable writer's mode v2 (writer004 itself requires `held` for a null C).
2. **A non-null A or B requires a group** whose `name` equals A and whose `specification` equals B (route `UNGROUPED_AB_MUST_BE_BLANK`, `A_MUST_EQUAL_GROUP_NAME`, `B_MUST_EQUAL_GROUP_SPECIFICATION`; writer004 `UNGROUPED_AB_MUST_BE_BLANK`). R56 keeps this as the mechanism: the enclosure row's A and B are carried by a one-row group (`relationship: physical_enclosure`) whose only member is that row. The route accepts a group with exactly one member.
3. **Q does not require verified adoption** (R54, O16). With unverified or partial adoption, a non-null Q gives the warning `O16_Q_UNVERIFIED_ADOPTION`, not a violation.
4. **Policy checks on a job packet** (route v4.2; R48, R56, R58). On an inventory that carries the job-input facts (every 046f packet), `check` rejects as `invalid`: a null L, M or N on any item (`R48_JOB_INPUT_REQUIRED`); an L, M or N whose refs are not exactly its own context ref (`R48_JOB_INPUT_REF`) or whose value differs from that fact (`R48_JOB_INPUT_VALUE_MISMATCH`); a non-null K, O or P (`R48_FIELD_MUST_BE_NULL`); a group whose relationship is not `physical_enclosure` (`R56_GROUP_RELATIONSHIP`) or that does not have exactly one member (`R56_GROUP_ONE_MEMBER_REQUIRED`). On every inventory, a J that cites `context:company_name` must equal it (`R56_J_COMPANY_NAME_MISMATCH`). The report field `policy_checks` says whether the job-packet checks were applied.
4a. **Scoped packets** (route v4.3; R59). On an inventory that carries `context:scope`, `check` and `check-inventory` reject as `invalid` a fact that is malformed (`R59_SCOPE_FACT_INVALID`) or disagrees with the inventory's sheets, flags, content-cell counts, cells or views (`R59_SCOPE_FACT_MISMATCH`), an item, group or link that cites a bill-sheet cell on a row below the fact's `end_row` (`R59_ROW_BELOW_END_ROW`), and a response that cites `context:scope` in any reference list (`R59_SCOPE_FACT_CITED`, `check` only). They warn `R59_LINKED_ANALYSIS_OUT_OF_SCOPE` when the fact records linked analysis blocks on an out-of-scope sheet. The report field `scope` reads `applied` on a scoped packet and `not_applied` otherwise; without the fact every check is that of v4.2.

One policy question stays open for the owner (FIELD_ROLES R50, note for the owner): 5. the O10 boundary in `SYNTHETIC_ALLOCATION_CASES.json` A12. R50 makes the unpriced owner-supplied panel line `excluded_supply` when a line inside it is priced; the O10 record ("the panel group stays and its lines are rows") can be read as keeping it as a row. Under O11, R50 also supersedes O7/R45's inclusion of in-panel lines without a price. Follow R50; evaluators declare both readings before scoring. (R50 now states the census role of an O10 omission, `excluded_supply`, which closes the earlier question 4.)

## Self-check before returning

Run the package checker on your file. It reads only the two files you name:

```bash
python3 -I tools/cps046b_route.py check --inventory SOURCE_INVENTORY.json --response response.json
```

- `invalid` violations are structural defects, such as an unknown or wrong-case reference, a missing proof, a wrong type, a mismatched unit or quantity, a missing role, a duplicate role, or a content cell that no item uses. Correct the response from the source, not by deleting meaning.
- `field_must_be_null` violations mean the cited source cannot be carried for that field. Examples: a quantity written as text with a unit or with full-width digits, a date-typed or error cell, or a field other than L, M and N proven only by context (for example I or C citing only `context:brand_table` or `context:glossary`: cite the source cell too). Set that field null, or that raw selection empty, with a specific reason. The source cell stays in the census.
- `unrepresentable_hold` violations mean a true answer cannot be carried by the admitted writer. Examples: a value that begins with `-`, `=`, `+` or `@`, or a held component link. Do not change a true value to make one disappear. Keep it, explain it in `limitations`, and return the response. The export is then held, and that outcome is recorded honestly.
- `invalid` also covers the route v4.2 policy checks (interface point 4): correct L, M, N, K, O, P, the group or the J from the job inputs and the resources, never by inventing a value. It also covers the route v4.3 scope checks (interface point 4a): an `R59_ROW_BELOW_END_ROW` item is out of the quoted range, so classify its cells `excluded_supply` and drop the citation; an `R59_SCOPE_FACT_CITED` citation is removed (the fact is never evidence); an `R59_SCOPE_FACT_INVALID` or `R59_SCOPE_FACT_MISMATCH` violation is a packet defect to report, not something the response can repair.
- The warnings `O13_SELECTION_EVIDENCE_M_N` (M and N cite job inputs), `R57_NULL_C_RESEARCH_DRAFT` (a null C on a `research_draft` row) and `O16_Q_UNVERIFIED_ADOPTION` (Q under unverified adoption) are expected under R48, R57 and R54. The first two tell the orchestrator to export with the portable writer's mode v2. None is a violation. On a scoped packet `R59_LINKED_ANALYSIS_OUT_OF_SCOPE` is expected when the fact records linked blocks on a scoped-out sheet (R59 item 6); it needs no change to the response.
- A passing check proves structure only. It is not semantic approval.

## Prohibited

- Translating, normalizing spelling, or inventing a name, abbreviation, model or brand. An abbreviation comes only from the glossary, a brand or model only from the line's own cells or, on a contract job without a 材料清單, the brand table.
- Copying a supply or separate-contract marker, a remark, a code or price text into C or D.
- Filling G, H, K, O or P, copying F into P, or putting the amount in Q.
- Inferring M or N from a letterhead, addressee line or signature (R6); they come only from the job inputs.
- Multiplying analysis bases, merging separate items, splitting a line, adding rows or dropping a row that R50/R51 make.
- Reading anything except the supplied packet and this package, and using historical worksheets, prior outputs, the job's other source document or evaluator material.

## After return (not the generator's job)

The orchestrator freezes the response bytes, then runs `convert` to produce the carrier and census ledger. A carrier with M/N selection evidence or a null C on a `research_draft` row is not accepted by the unchanged writer004 gate; the portable writer's mode v2 (`research/export/README.md`) validates it with writer004 on a documented placeholder copy plus the sha256-pinned route v4.2 port (route v4.3 keeps that port byte-identical, so it validates v4.3 carriers unchanged). Evaluation happens in a separate role. Workbook export, saved-cell QA and visual QA need an admitted export runtime. Where none is available, they are recorded as unattempted.
