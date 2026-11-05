# Source-reference and coverage contract v2 (candidate 046g, route v4.3)

Status: candidate interface for independent review and bounded source trials. It is not deployment approval. `tools/cps046b_route.py` (route v4.3, `cps046g-route.v4.3`) mechanically enforces every rule below that can be checked from references and inventory data alone. Route v4 differs from route v3 (046e) in one rule: L, M and N may be proven by job-input context facts alone (owner decision O13, FIELD_ROLES R48); see §3 Proofs and §5. Route v4.1 changes two more checks into warnings: a null C may have status `research_draft` (FIELD_ROLES R57), and a non-null Q no longer requires verified adoption (R54, O16); see §3. Route v4.2 adds `invalid` policy checks from inventory data on a 046f job packet (R48, R56, R58; §3 "Policy checks"); its writer port and relaxations are those of v4.1. Route v4.3 (candidate 046g) adds scope checks that apply only to a scoped packet, an inventory carrying `context:scope` (FIELD_ROLES R59; §1b, §3 "Scope checks"); without that fact it behaves as v4.2, and its writer port is byte-identical to v4.2's. Semantic choices, such as which cells are descriptive or which role a cell has, stay with the AI and an independent semantic review. Where this text and the tool disagree, the response is held and the disagreement is a defect to report. Do not adapt the response to whichever one is more lenient.

The AI decides item identity, field roles, values and references. The route only validates and copies. It never selects a reference, edits a value, shortens a name, infers a brand, repairs a response or reads evaluator material.

## 1. Immutable inventory (`SOURCE_INVENTORY.schema.json`, `cps.source-inventory.cells.v2`)

A source preparer builds one inventory per pinned cached workbook (`cached_xls` or `cached_xlsx`). It holds:

- `case_id` and `family_id`.
- `source`: format, bytes, sha256, adoption status and basis, reader limits, and `carrier_source` (the exact `{kind,path,sha256,views}` object the existing writer requires; the path is original provenance, not a location to open).
- `sheets`: every sheet, including empty and hidden ones, with index, visibility, dimensions, merges, formula-record count and `in_scope`.
- `views`: reconstructed inspection images, each pinned by hash.
- `cells`: **every** physical position of every in-scope sheet.
- `context_facts`: separately authorized facts (§1a).
- `limitations`.

The response binds to the inventory by the SHA-256 of its file bytes.

### 1a. Context facts (046f)

Each context fact is `{ref, namespace, value, basis, authority_pins}`; `value` is a string, number or null, and `authority_pins` pins the private file it came from by SHA-256. The packet preparer adds them from a private per-job configuration (`harness/README.md`). A 046f packet carries:

| Ref | Namespace | Value | Used by |
|---|---|---|---|
| `context:case_identity` | `cps.internal_case_id` | internal case id (job input) | L (R48) |
| `context:customer_name` | `cps.job_input.customer_full_name` | customer full name (job input) | M (R48) |
| `context:project_name` | `cps.job_input.project_short_name` | project short name (job input) | N (R48) |
| `context:company_name` | `cps.company_resource.company_name` | the company name | J on the enclosure row (R56, R58) |
| `context:glossary` | `cps.company_resource.glossary` | JSON text `cps.company-glossary.v1`: `generic_prefix_words`, `enclosure_word`, `category_words` (the category words R52 drops as chain), `abbreviations[{device, abbreviation}]` | C (R52, R56, R58) |
| `context:brand_table` | `cps.company_resource.brand_table` | JSON text `cps.company-brand-table.v1`: `entries[{device, rating_band, brand, model}]`. **Contract packets only**: a 材料清單 packet has no brand table (O17; `harness/make_job_config.py` omits it) | I and J on priced equipment lines of a contract job (R55, R58) |

The company resources are owner-reviewed private company data. They never enter the public repository; the examples in this package use invented values. The route checks that a cited context ref exists in the inventory (`UNKNOWN_CONTEXT_REF`; on a 材料清單 packet this rejects any citation of `context:brand_table`). It does not read or interpret the glossary or the brand table. It compares only the plain job-input and company-name values: on a 046f job packet, L, M and N must equal their facts, and on every inventory a J that cites `context:company_name` must equal it (§3 "Policy checks").

An inventory is a **046f job packet** when it carries `context:customer_name` or `context:project_name`. A job packet must carry all three job-input facts (`R48_JOB_INPUT_FACT_MISSING`) as nonblank strings (`R48_JOB_INPUT_FACT_VALUE`). `check`, `convert` and `check-inventory` report `policy_checks: applied` for a job packet and `not_applied_no_job_input_facts` otherwise; `check-inventory` also warns `NOT_A_046F_JOB_PACKET`. Every packet made by `make_job_config.py` is a job packet; inventories without job inputs are pre-046f mechanics fixtures.

Cell reference IDs are `cell:S<sheet index>!<A1 address>`, for example `cell:S1!B12`. Matching is exact and case-sensitive. A reference is valid only if that exact ID exists in the inventory. Equal text in two cells does not make their references interchangeable. Context IDs are `context:<name>`.

Each cell records `saved_type` (`empty|blank|text|number|date|boolean|error`) and `state` (`literal|cached_formula|true_blank|explicit_empty|covered|error|missing_cache|unresolved`). It also records the original `saved_value`, `formula_record_present`, `formula` (null where the reader cannot decompile it), `native_literal` (null where the format stores only binary64), `merge_anchor_ref`, `conflicts`, the views containing it, `canonical_raw`, `usable_for_raw` and `raw_limit_reason`.

**Content cell:** `literal`/`cached_formula` with a saved value that is not null and not `""`, plus `error`, `missing_cache`, `unresolved`, and `covered` with a recorded conflict. **Empty cell:** `true_blank`, `explicit_empty`, and `covered` without a conflict.

### 1b. Scoped packets (046g, FIELD_ROLES R59)

When the full inventory of a workbook has more than 2,500 literal or cached-formula content cells, the source preparer runs the scope stage (`harness/README.md`) and the packet is a **scoped packet**: a projection of the full inventory that keeps only the in-scope sheets' cells and views (the kept views renumbered 1..n), sets each sheet's `in_scope` flag, and appends the context fact `context:scope` (namespace `cps.source_prep.scope`). Its value is JSON text, schema `cps.scope-fact.v1`, with exactly the keys `schema`, `rule` (`R59`), `bill_rule` (`BILL1.v1`), `threshold` (`content_cells_literal_or_cached`, `limit` 2500), `bill_sheet_index`, `bill_header_row`, `end_row`, `sheets` (for every sheet: `index`, `name`, `role`, `visibility`, `rows`, `columns`, `content_cells`, `in_scope`, `reason`, `linked_analysis_blocks`), `digest_sha256`, `full_inventory_sha256`, `decision_sha256` and `agreement` (`tool_and_reader_agreed`). `authority_pins` pin the frozen scope decision, the full inventory and the scope digest. The fact is never field evidence. Scoped-out sheets keep their `sheets` record (with `in_scope` false) but have no cells or views; they are not missing sources (R59).

## 2. Canonical raw text (profile `cached-cell-raw-scalar-text.v2`)

- R1 Text: the exact saved Unicode string. No trimming, normalization or parsing; the text `001.00` stays `001.00`.
- R2 Finite number or numeric formula cache: `Decimal(repr(float(v)))` written in fixed notation, then trailing fractional zeros and any trailing `.` removed, with `-0` written as `0`. No grouping and no exponent. Examples: `12.0`→`12`, `0.1+0.2`→`0.30000000000000004`, `1e-05`→`0.00001`.
- R3 True blank, explicit empty string or covered position: `canonical_raw` is null, so the cell contributes no text.
- R4 Date, boolean, error and missing-cache cells, and text containing C0 controls other than TAB/LF/CR: `usable_for_raw=false` with a reason. They stay literal in the inventory and census, but cannot be copied into raw or proof text. A field that needs one must be held.

The inventory and census keep the original type and value. `canonical_raw` serves only raw and proof copying.

## 3. Response (`SEMANTIC_RESPONSE.schema.json`, `cps.semantic-source-refs.v2`)

Top level: `schema`, `case_id`, `family_id`, `inventory_sha256`, `status` (`research_draft|partial|held`), `groups`, `items`, `component_links`, `source_roles`, `limitations`.

**Items.** Each item has `id` (`^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$`, unique across groups and items), `role` (`demand|analysis_component`), `group_id` (a group ID or null), `status` (`research_draft|held`), `values`, `proofs`, `raw_refs`, `anchor_refs` and `review_reasons`. `values` holds exactly 17 values in A–Q order. An `analysis_component` has `group_id`, A and B null (FIELD_ROLES R25; `COMPONENT_GROUP_FORBIDDEN`).

- Types: F, P and Q are finite numbers with absolute value at most 2^53−1, or null. G and H are always null. Every other position is a string or null. A string must be nonblank after JavaScript `trim`, at most 30,000 UTF-16 units, with no C0 control except TAB/LF/CR and no lone surrogate. A numeric-looking specification such as `110` is written as the string `"110"`.
- A null C may have status `research_draft` or `held` (route v4.1, FIELD_ROLES R57; `check` warns `R57_NULL_C_RESEARCH_DRAFT` for `research_draft`). Its null proof still needs a specific reason. `held` requires at least one review reason.

**Proofs.** `proofs` maps every letter A–Q to exactly one of:

- `{"reason": "..."}` when the value is null; the reason must be specific.
- `{"refs": [...], "transformation": "...", "role_basis": "..."}` when the value is not null.

Proof rules:

- Every proof cell must have a non-null `canonical_raw`, so a proof can never cite an empty or unusable cell.
- All proof cells of one field are on one sheet.
- F, P and Q are each proven by exactly one cell, whose canonical text parses (writer `numericRaw`) to the value. Only ASCII digits, an optional sign, optional `,` thousands grouping and one decimal point are accepted.
- If the source cell for F, P or Q is not such a plain numeric literal (for example `2台`, full-width digits, or a date-typed cell), the field is **null** with a specific reason. Its raw text is still kept.
- F's proof cell must be the item's raw `quantity` cell.
- A field proven only by `context:` references is allowed for L, M and N alone (job inputs, R48). Any other field proven only by context must be null with a reason (`CONTEXT_ONLY_PROOF_UNREPRESENTABLE`, category `field_must_be_null`). A field derived through a company resource cites its source cell together with the context ref (R58), for example `["cell:S1!B5", "context:glossary"]`; such a proof is cell evidence, and its context refs are packed into the transformation.

**Raw references.** `raw_refs` has the six raw fields `description, unit, quantity, unit_price, amount, remarks`. Each is `{"refs":[...], "reason_if_empty": string|null}`. A non-empty list requires `reason_if_empty:null`, and an empty list requires a specific reason.

- `unit`, `quantity`, `unit_price` and `amount` hold at most one cell each: the item's own cell in that role (FIELD_ROLES R22).
- `description` lists the logical item's descriptive text cells in row-major order (top to bottom, then left to right). These are its name/description column and any separate specification or description column, including proven continuation rows. Exclude the item-number cell and the unit, quantity, price, amount and remarks cells. The checker enforces row-major order and these exclusions.
- `remarks` lists the item's remarks-column cells in row-major order.
- Every listed cell must have non-null `canonical_raw`; empty cells are never listed. The copied raw text is the canonical texts joined with U+000A.
- A content cell that cannot be carried (date, boolean, error, or control characters) is never listed. A raw role that would need such a cell has an empty selection and a specific reason. The cell stays in the census.
- A description cell or anchor cell belongs to exactly one item. Sharing one across items is an item-boundary error.
- Consistency: a non-null E equals the copied raw unit exactly. A non-null F equals `numericRaw(raw quantity)`. A non-null Q equals `numericRaw(raw unit_price)`. Under route v4.1 it no longer requires inventory `adoption_status: "verified"` (R54, O16): with `partial` or `unverified` adoption, `check` warns `O16_Q_UNVERIFIED_ADOPTION`.

**Anchors and location.** `anchor_refs` (at least one) are the cells that carry the item's identity on its first physical row, normally its item-number cell.

- When an item has no item-number cell, its first description cell is the anchor.
- When one cell holds both the item number and the description text, classify it as `demand_content` (or `analysis_content`), cite it in the description, and use it as the anchor.
- A cell used as one item's anchor or description cell cannot be another item's anchor or description cell.
- At most 2000 demand items and 2000 analysis components are allowed.
- Anchors are all on one row, and that row is the first row of the item's cells.
- The item's carrier location is the ordered union of its anchor and raw-field cells. All of these cells must be on one sheet and inside the inventory views.

**Groups.** A group is `{id, name|null, specification|null, relationship, anchor_refs, name_refs, specification_refs, quantity_basis, limitations}`.

- `relationship` is one of `contractual_group|physical_enclosure|contractual_and_physical|unresolved`.
- A non-null name or specification needs its proof references. A null name needs at least one limitation.
- A non-null A or B needs a non-null `group_id`. A must equal that group's `name` exactly, and B must equal its `specification` exactly. (046f: R56 forms no contractual groups, so the enclosure row's A and B are carried by a one-row group; on a job packet route v4.2 requires every group to be `physical_enclosure` with exactly one member; see "Policy checks".)
- A contractual grouping alone does not prove physical ownership or enclosure count.

**Component links.** Every `analysis_component` item has exactly one link, and a demand item has none. A link is `{component_id, parent_id, status, basis_quantity, basis_raw_ref, basis_unit_ref, refs, reason}`.

- `supported` (basis cells per FIELD_ROLES R21: the component row's own quantity and unit cells): the parent is a demand item other than itself, `basis_quantity` is greater than 0, `basis_raw_ref` is one cell whose canonical text parses to `basis_quantity`, and `basis_unit_ref` is one nonblank, non-formula-like cell of saved type `text`. All basis cells are on one sheet. Never multiply by the parent quantity.
- `held`: the admitted writer cannot carry a held or unlinked component, so the **whole export is held**. The response and census are still retained. Never delete a component or invent a link to avoid this. An analysis block whose referenced item is not a demand item of this response is not a component at all (FIELD_ROLES R46): its cells take the census role `analysis_unlinked`.

**Policy checks (route v4.2; FIELD_ROLES R48, R56, R58).** All are `invalid`. On a 046f job packet (§1a):

- every item, demand row or `analysis_component`, has non-null L, M and N (`R48_JOB_INPUT_REQUIRED`); each is proven by exactly its own context ref and nothing else, L `["context:case_identity"]`, M `["context:customer_name"]`, N `["context:project_name"]` (`R48_JOB_INPUT_REF`); and each equals that fact's value (`R48_JOB_INPUT_VALUE_MISMATCH`);
- K, O and P are null on every item (`R48_FIELD_MUST_BE_NULL`);
- every group has `relationship: physical_enclosure` (`R56_GROUP_RELATIONSHIP`) and exactly one member item (`R56_GROUP_ONE_MEMBER_REQUIRED`).

On every inventory, a non-null J whose proof cites `context:company_name` equals that fact's value (`R56_J_COMPANY_NAME_MISMATCH`). The route does not decide whether a row is an enclosure; that stays semantic.

**Scope checks (route v4.3; FIELD_ROLES R59).** Only on a scoped packet (§1b); `check`, `convert` and `check-inventory` report `scope: applied` there and `scope: not_applied` otherwise.

- `R59_SCOPE_FACT_INVALID` (invalid): the fact's value is not strict JSON text with exactly the keys of §1b, a rule version, the agreement or the threshold (more than 2,500) is wrong, a hash is not 64 hex digits, or a sheet entry has the wrong keys or types.
- `R59_SCOPE_FACT_MISMATCH` (invalid): the fact and the inventory disagree. The sheet lists must match in order on `index`, `name`, `visibility`, `rows`, `columns` and `in_scope`; exactly one sheet has role `bill`, it is in scope and it is `bill_sheet_index`; in-scope roles are `bill` or `analysis`, out-of-scope roles `summary`, `analysis`, `resource_statistics` or `other`; each in-scope sheet's `content_cells` equals its content cells in the inventory; no cell or view belongs to an out-of-scope sheet; and `bill_header_row` < `end_row` <= the bill sheet's `rows`.
- `R59_ROW_BELOW_END_ROW` (invalid): an item (anchor, raw selection or proof), group or component link cites a cell of the bill sheet on a row greater than `end_row`. Such cells are `excluded_supply` (R59 item 3).
- `R59_LINKED_ANALYSIS_OUT_OF_SCOPE` (warning): an out-of-scope sheet has `linked_analysis_blocks` above 0. Their parents are priced or not estimated, so R51 makes no rows of them.

The route cannot see scoped-out cells. Whether a sheet should have been in scope is decided and audited in the scope stage, not by the route.

**Source roles.** Each source role is `{role, refs, reason}`, with role one of `demand_content, analysis_content, item_identifier, header, section, financial_summary, commercial_note, document_reference, footer, unresolved, excluded_supply, analysis_unlinked`. `excluded_supply` marks every cell of a line that is not a 未填 row under FIELD_ROLES R50 or R51 (no price and no status, reason per R45; outside the quoted range, reason "outside the quoted range (R49)"; an O10 omission, reason per R50; or a no-price, no-status line whose analysis block lies outside the quoted range); `analysis_unlinked` marks every cell of an analysis block with no parent demand item, except page/column headers and footers inside it (R46). No item, group or link may cite an `excluded_supply` or `analysis_unlinked` cell (`CENSUS_ONLY_CELL_USED_BY_ITEM`).

- The parent line of analysis components listed as rows takes `section` with the reason "parent of analysis components listed as rows (R51)".
- Every content cell has **exactly one** primary role, and empty cells take no role.
- An item's own description, unit, quantity, price, amount and remark cells are `demand_content` (or `analysis_content`), even when a remark is commercial in tone.
- Every `demand_content`/`analysis_content` cell must be cited by some item or group (raw, proof, anchor, group proof or basis). This detects dropped items.
- An item's cell that no raw field can carry, such as a second text cell in its quantity column, is classified by its own nonitem role, for example `commercial_note`, and stays in the census.
- Secondary uses (raw, proof, anchor, group, basis) are recorded by the route and do not change the primary role.

## 4. Unrepresentable values and holds

The existing writer rejects the **whole carrier** for any formula-like value (a value whose first non-whitespace character is `=`, `+`, `@` or `-`). Such a value is still written exactly as the source supports it. The checker then reports `FORMULA_LIKE_STRING_WHOLE_OUTPUT_HELD`, and the output stays held with the value retained. Never strip a sign, add an apostrophe or escape the value.

The same whole-output hold applies to:

- a held component link;
- a cell outside every view;
- a view that no item, group or census cell covers;
- text with control characters.

A field other than L, M and N proven only by context is not a hold: it is `field_must_be_null` (§3).

The route reports three categories:

- `invalid`: a defect in the response. Correct it from the source.
- `field_must_be_null`: the cited source cannot be carried for that field or raw role, for example a date, boolean or error cell, non-ASCII digits or text with units, or a context-only proof of a field other than L, M and N. Leave the field or selection empty with a specific reason; never alter the source meaning.
- `unrepresentable_hold`: the admitted writer cannot carry a true answer. Keep the answer; the export is held.

Before `check` passes, it builds exactly the carrier that `convert` would write and runs a Python port of writer004 `validateCarrier` and `prepareMatrices` on it. This port is parity-tested against the real writer. Its documented divergences (`PORT_RELAXATIONS`) are two: it accepts `selection_evidence` for L, M and N, where writer004 accepts it for L only (`SELECTION_ONLY_ENGINEERING_ID`; route v4, O13), and it accepts a null C with status `research_draft`, where writer004 requires `held` (`UNRESOLVED_ITEM_MUST_BE_HELD`; route v4.1, R57). Q under unverified adoption needs no port change, because writer004 never reads the adoption status. The parity tests assert that the port without these relaxations equals writer004 and that no other divergence occurs. When M or N is proven by context alone, `check` warns `O13_SELECTION_EVIDENCE_M_N`. Any overflow of the writer's count or length caps by an adapter-built string or list is reported as `WRITER_WOULD_REJECT_*` (`unrepresentable_hold`).

## 5. Carrier mapping (adapter output)

`convert` writes `cps.cached-xls-research-carrier.v1` (or `-xlsx-` for `cached_xlsx`) for `writer004.validateCarrier`:

- `source` is the inventory `carrier_source`, copied verbatim. `metadata` holds the response schema/status, the inventory, response and ledger hashes, the adapter version, the profile and the adoption status, with no path strings.
- Demand items go to `items` and analysis components to `components`, in response order. Values, status and review reasons are copied unchanged, and a type-exact comparison of values is asserted.
- `raw` is the copied canonical text.
- Non-null fields become evidence. A field with cell refs becomes `{location, anchor, raw_text (the cited canonical texts joined with LF), transformation}`. Its transformation is a JSON string `{"transformation","role_basis","context_refs"}`, so `role_basis` is kept losslessly. L, M or N proven only by context becomes `{selection_evidence, transformation}`, where `selection_evidence` is JSON with the fact's ref, namespace, value and basis plus the role basis. The convert receipt reports each relaxation class (`o13_m_n_selection_evidence`, `r57_null_c_research_draft`, `o16_q_unverified_adoption`) and the overall `export_mode_required`; a carrier that needs `v2` is exported with `research/export/writer_portable.py --mode v2`, which gates it with writer004 on a documented placeholder copy and with the route v4.2 port, pinned by sha256.
- Null fields become `null_reasons`.
- Groups map to writer groups, with the relationship and references packed into `anchor` JSON.
- Each supported link becomes `composition{parent_id, basis_quantity, basis_unit, basis_location, basis_raw}`.
- `nonitems`: one entry per cell whose primary role is `item_identifier, header, section, financial_summary, commercial_note, document_reference, footer, unresolved, excluded_supply` or `analysis_unlinked`, in inventory order. `kind` is the role and `anchor` is the cell ref. `text` is the lossless typed wrapper `{"conflicts","formula_record_present","saved_type","state","value"}`, serialized as compact sorted JSON. `reason` is the role reason.
- Anchor use never removes an identifier from the census (anchor-plus-census).
- `CENSUS_LEDGER.json` records one entry per inventory position: state, original value, formula flag, conflicts, primary role, every raw, proof, anchor, group and basis use, and census membership. It also keeps the response's empty-selection reasons and link reasons, which have no writer slot. Its hash is in the carrier metadata.
- The ledger is written even when the response is not carried, so the census is always retained.
- `check-inventory` validates an inventory before generation: writer source rules, case/family IDs, canonical text, content cells outside views and views without content.

A carrier proves structure only. Writer acceptance, ledger completeness, reader agreement and comparator pairing are not semantic correctness.

## 6. Evaluation boundary

Freeze the response bytes before conversion and the carrier before any evaluator access. The source comparator pairs rows by sheet and anchor cell. A comparator limitation is a fact about the evaluator; it must never be compensated for in generation. Historical targets, source expectations and prior outputs never enter a generation context.
