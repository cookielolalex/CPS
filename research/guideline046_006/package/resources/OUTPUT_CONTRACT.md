# Output contract (candidate 046f, draft)

Return one JSON file conforming to `SEMANTIC_RESPONSE.schema.json` (`cps.semantic-source-refs.v2`) and to every rule in `SOURCE_REFERENCE_CONTRACT.md`. The response states your semantic decisions and points at exact inventory cells and context facts. The adapter later copies the source text and builds the writer carrier. It cannot fix or complete your response.

046f reproduces the historical 未填 creator's majority practice (FIELD_ROLES R48–R58). Where R48–R58 and an older sentence of this package disagree, R48–R58 govern.

## What you receive

- `SOURCE_INVENTORY.json`: the complete typed positional inventory. It is authoritative for characters, types and addresses. Compute `inventory_sha256` as the SHA-256 of this file's exact bytes.
- `view_NN.png`: reconstructed inspection images of the same saved cells. They help you see the layout. They do not add characters, and their line wrapping is artificial.
- `context_facts` in the inventory:
  - job inputs (R48): `context:case_identity` (internal case id), `context:customer_name` (customer full name) and `context:project_name` (project short name);
  - company resources (R58): `context:company_name`, `context:glossary` (generic prefix words, the generic enclosure word and device abbreviations) and `context:brand_table` (brand and model by device type and rating band).

  The resources are owner-reviewed private company data, supplied with each packet and pinned by SHA-256. Use them only as R52, R55 and R56 say. The values in this package's examples are invented.

## How to build the response

1. **Read everything.** Read the whole inventory and all views. Identify sheet roles, the detailed bill sheet that carries the sender's prices, its column header and column roles, every logical item and continuation, sections, totals, analysis blocks and every nonitem region.
2. **Find the quoted range (R49).** It runs from the first item line under the column header down to the end row: the row whose unit-price or amount column holds 合計 or 總計. A 合計 written in the description column is a block total, not the end. Repeated site sections and goods/labour subsections inside the range are all in it. Summary sheets never yield rows. When every bill line is unpriced, rows come from the analysis sheet (R51).
3. **Decide the rows (R50, R51).** Inside the range, in source order, write one `demand` item for each:
   - priced line (its unit-price or amount cell holds a number above zero);
   - not-estimated line (its amount cell holds the literal 不含估價);
   - zero-state line (a cached 0 amount with no unit price);
   - unnumbered fee line of the sender before the end row (freight, drawing, design or management fee).

   Analysis components become the rows instead of their parent when the parent bill line has no price and no status and its block lies in range, or when every bill line is unpriced (R51). Write them as `demand` items, block by block in analysis order. When the parent is priced or not estimated, its components are never rows: they stay `analysis_component` items with a component link (R21, R25), or `analysis_unlinked` cells (R46).

   Never split or merge lines, and never add rows. A remark saying a line is not included or not used does not remove it. Supply and separate-contract markers (業主供料, 甲供, 業主自備, 業主自理, 另案, 另案發包, supplied by others) do not decide inclusion and are never copied into a field. Provisionally (O10), a panel line marked owner-supplied is omitted with its contents only when no line inside it has a price inside the quoted range.
4. **Classify every other content cell (census, R11, R50, R51).** Assign exactly one primary `source_roles` entry to every content cell, and none to empty cells.

   | Cells | Role | Reason (begin with) |
   |---|---|---|
   | A row's own description, unit, quantity, unit-price, amount and remark cells | `demand_content` (for R51 component rows, `demand_content` or `analysis_content`; R51 does not say which, and the route accepts both) | what the cells are |
   | Item numbers | `item_identifier` | |
   | An in-range line with no price and no status | `excluded_supply` (every cell, including its item number and continuation rows) | "no enclosure and no estimate: not in the quoted supply (R45)", then the condition: price cells empty, or the text they hold |
   | An item-like line after the end row | `excluded_supply` | "outside the quoted range (R49)" |
   | An owner-supplied panel line omitted under O10, and its contents (including a not-estimated or zero-state line inside it) | `excluded_supply` (R50 states no census role for an O10 omission; this is the role for lines that are not 未填 rows; open question 4 below) | name the marker and "owner-supplied panel with no priced line inside the quoted range (R50, provisional O10)" |
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
   | A, B | Only on an enclosure row (R56): A = the enclosure noun from the line, or from its section heading when the line names only a generic box; B = `<w>W*<h>H*<d>D` from dimensions stated in the contract (mm), else null. Null on every other row. |
   | C, D | R52, after dropping the generic leading prefix word named in the glossary. Equipment line: C = the glossary abbreviation, else the head noun; D = the rest. Material, bulk, service, labour and fee lines: C null, D = the description (category chain kept). Single segment: an equipment noun goes to C with D null, anything else to D with C null. Enclosure row: C = the glossary's generic enclosure word; D = the remaining material, finish or type text (R56). Breaker-type lines: D joins the rating tokens with single spaces and drops wrapping brackets (R53). Every other D keeps its punctuation verbatim. Continuation rows join the description with no separator. Remarks, code columns and price text never enter C or D. |
   | E, F | The line's own unit and quantity cells, verbatim (R57). |
   | G, H | Null (R57). |
   | I, J | Not-estimated line: I = J = 不含估價, citing the amount cell. Priced equipment line: a brand or model stated in the line's own cells, else the brand table by device type and rating band; a device or rating the table does not cover leaves I and J null with a reason. Enclosure row: I null, J = the company name. Material, service, fee and zero-state lines: null (R55, R56). |
   | K, O, P | Null (R48). |
   | L, M, N | Copied exactly from `context:case_identity`, `context:customer_name` and `context:project_name`, citing only that context ref, on every row (R48). Never infer M or N from a letterhead (R6). |
   | Q | Priced line: its unit price as a number, cited from its unit-price cell, never the amount. Null on not-estimated and zero-state lines (R54). |

   **Citations (R58).** A field derived through a company resource cites the source cell it was derived from together with the context ref: C from the glossary cites the description cell and `context:glossary`; I and J from the brand table cite the description cell and `context:brand_table`; J on an enclosure row cites the line's description cell and `context:company_name`. L, M and N cite only their job-input context refs. The transformation says how the value was obtained from the cited text; the role basis says why that text has this field role. Keep values exactly as the policy and source support them; never adjust a value to pass a check.
6. **Fill `raw_refs`** per `SOURCE_REFERENCE_CONTRACT.md` §3: description and remarks streams in row-major order, and at most one cell each for unit, quantity, unit price and amount. Never list an empty cell, and give a specific reason for every empty selection. Set `anchor_refs` to the item's identity cell(s) on its first row, normally the item number; an unnumbered fee line or component row uses the first cell of its description.
7. **Keep the earlier mechanics.** Source reading, raw and provenance mechanics, census roles (R11, R29, R45, R46), holds (R42), document references (R5: never in C or D) and cost-line codes (R23) still apply where R48–R58 do not address them. Make every null reason true of the whole source (R9). Record total/subtotal discrepancies in `limitations` without repairing them (R10).
8. **Set statuses.** Item `status` is `research_draft` or `held`; `held` needs review reasons. Top-level `status` is `research_draft`, `partial` (some scope is unresolved or held) or `held`. Record every unresolved obligation in `limitations` or review reasons.

Use IDs such as `R001…` for rows in source order and `C001…` for `analysis_component` items in analysis order. Do not form groups for contractual sections: no row except the enclosure row carries A or B (R56).

## Open interface questions (route v4 unchanged on these points)

R48–R58 change field roles; route v4 changed only the context-only proof rule for L, M and N (O13). Three route and writer constraints still bind every response and are recorded for the package author's decision. Until then, follow them and state them in `limitations`; do not change a value to avoid them.

1. **A null C requires `status: "held"`** (route `NULL_C_REQUIRES_HELD`, writer004 `UNRESOLVED_ITEM_MUST_BE_HELD`). Under R52, material, bulk, service, labour and fee rows have C null, so they are held with a review reason saying they are held only for this reason.
2. **A non-null A or B requires a group** whose `name` equals A and whose `specification` equals B (route `UNGROUPED_AB_MUST_BE_BLANK`, `A_MUST_EQUAL_GROUP_NAME`, `B_MUST_EQUAL_GROUP_SPECIFICATION`; writer004 `UNGROUPED_AB_MUST_BE_BLANK`). R56 forms no response groups. The example carries the enclosure row's A and B through a one-row group (`relationship: physical_enclosure`) whose only member is that row, and names the question in the group's limitations.
3. **Q requires verified source adoption** (route `Q_REQUIRES_VERIFIED_ADOPTION`), although R54 replaces the adoption hold. With unverified or partial adoption, a non-null Q is an `invalid` violation.

One policy question is also open and recorded for the package author: 4. R50 names no census role or reason for lines omitted under the provisional O10 rule; the table above uses `excluded_supply`, and A11/A12 in `SYNTHETIC_ALLOCATION_CASES.json` show the literal R50 reading.

## Self-check before returning

Run the package checker on your file. It reads only the two files you name:

```bash
python3 -I tools/cps046b_route.py check --inventory SOURCE_INVENTORY.json --response response.json
```

- `invalid` violations are structural defects, such as an unknown or wrong-case reference, a missing proof, a wrong type, a mismatched unit or quantity, a missing role, a duplicate role, or a content cell that no item uses. Correct the response from the source, not by deleting meaning.
- `field_must_be_null` violations mean the cited source cannot be carried for that field. Examples: a quantity written as text with a unit or with full-width digits, a date-typed or error cell, or a field other than L, M and N proven only by context (for example I or C citing only `context:brand_table` or `context:glossary`: cite the source cell too). Set that field null, or that raw selection empty, with a specific reason. The source cell stays in the census.
- `unrepresentable_hold` violations mean a true answer cannot be carried by the admitted writer. Examples: a value that begins with `-`, `=`, `+` or `@`, or a held component link. Do not change a true value to make one disappear. Keep it, explain it in `limitations`, and return the response. The export is then held, and that outcome is recorded honestly.
- The warning `O13_SELECTION_EVIDENCE_M_N` is expected whenever M and N cite job inputs. It tells the orchestrator to export with the portable writer's mode v2. It is not a violation.
- A passing check proves structure only. It is not semantic approval.

## Prohibited

- Translating, normalizing spelling, or inventing a name, abbreviation, model or brand. An abbreviation comes only from the glossary, a brand or model only from the line's own cells or the brand table.
- Copying a supply or separate-contract marker, a remark, a code or price text into C or D.
- Filling G, H, K, O or P, copying F into P, or putting the amount in Q.
- Inferring M or N from a letterhead, addressee line or signature (R6); they come only from the job inputs.
- Multiplying analysis bases, merging separate items, splitting a line, adding rows or dropping a row that R50/R51 make.
- Reading anything except the supplied packet and this package, and using historical worksheets, prior outputs or evaluator material.

## After return (not the generator's job)

The orchestrator freezes the response bytes, then runs `convert` to produce the carrier and census ledger. A carrier with M/N selection evidence is not accepted by the unchanged writer004 gate; the portable writer's mode v2 (`research/export/README.md`) validates it with writer004 on a documented placeholder copy plus the route v4 port. Evaluation happens in a separate role. Workbook export, saved-cell QA and visual QA need an admitted export runtime. Where none is available, they are recorded as unattempted.
