# Source-reference and coverage contract v2 (candidate 046b)

Status: candidate interface for independent review and bounded source-only trials. It is not deployment approval. `tools/cps046b_route.py` (route v2) mechanically enforces every rule below that can be checked from references alone. Semantic choices, such as which cells are descriptive or which role a cell has, stay with the AI and an independent semantic review. Where this text and the tool disagree, the response is held and the disagreement is a defect to report. Do not adapt the response to whichever one is more lenient.

The AI decides item identity, field roles, values and references. The route only validates and copies. It never selects a reference, edits a value, shortens a name, infers a brand, repairs a response or reads evaluator material.

## 1. Immutable inventory (`SOURCE_INVENTORY.schema.json`, `cps.source-inventory.cells.v2`)

A source preparer builds one inventory per pinned cached workbook (`cached_xls` or `cached_xlsx`). It holds:

- `case_id` and `family_id`.
- `source`: format, bytes, sha256, adoption status and basis, reader limits, and `carrier_source` (the exact `{kind,path,sha256,views}` object the existing writer requires; the path is original provenance, not a location to open).
- `sheets`: every sheet, including empty and hidden ones, with index, visibility, dimensions, merges, formula-record count and `in_scope`.
- `views`: reconstructed inspection images, each pinned by hash.
- `cells`: **every** physical position of every in-scope sheet.
- `context_facts`: separately authorized facts such as the selected internal case identity.
- `limitations`.

The response binds to the inventory by the SHA-256 of its file bytes.

Cell reference IDs are `cell:S<sheet index>!<A1 address>`, for example `cell:S1!B12`. Matching is exact and case-sensitive. A reference is valid only if that exact ID exists in the inventory. Equal text in two cells does not make their references interchangeable. Context IDs are `context:<name>`.

Each cell records `saved_type` (`empty|blank|text|number|date|boolean|error`) and `state` (`literal|cached_formula|true_blank|explicit_empty|covered|error|missing_cache|unresolved`). It also records the original `saved_value`, `formula_record_present`, `formula` (null where the reader cannot decompile it), `native_literal` (null where the format stores only binary64), `merge_anchor_ref`, `conflicts`, the views containing it, `canonical_raw`, `usable_for_raw` and `raw_limit_reason`.

**Content cell:** `literal`/`cached_formula` with a saved value that is not null and not `""`, plus `error`, `missing_cache`, `unresolved`, and `covered` with a recorded conflict. **Empty cell:** `true_blank`, `explicit_empty`, and `covered` without a conflict.

## 2. Canonical raw text (profile `cached-cell-raw-scalar-text.v2`)

- R1 Text: the exact saved Unicode string. No trimming, normalization or parsing; the text `001.00` stays `001.00`.
- R2 Finite number or numeric formula cache: `Decimal(repr(float(v)))` written in fixed notation, then trailing fractional zeros and any trailing `.` removed, with `-0` written as `0`. No grouping and no exponent. Examples: `12.0`→`12`, `0.1+0.2`→`0.30000000000000004`, `1e-05`→`0.00001`.
- R3 True blank, explicit empty string or covered position: `canonical_raw` is null, so the cell contributes no text.
- R4 Date, boolean, error and missing-cache cells, and text containing C0 controls other than TAB/LF/CR: `usable_for_raw=false` with a reason. They stay literal in the inventory and census, but cannot be copied into raw or proof text. A field that needs one must be held.

The inventory and census keep the original type and value. `canonical_raw` serves only raw and proof copying.

## 3. Response (`SEMANTIC_RESPONSE.schema.json`, `cps.semantic-source-refs.v2`)

Top level: `schema`, `case_id`, `family_id`, `inventory_sha256`, `status` (`research_draft|partial|held`), `groups`, `items`, `component_links`, `source_roles`, `limitations`.

**Items.** Each item has `id` (`^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$`, unique across groups and items), `role` (`demand|analysis_component`), `group_id` (a group ID or null), `status` (`research_draft|held`), `values`, `proofs`, `raw_refs`, `anchor_refs` and `review_reasons`. `values` holds exactly 17 values in A–Q order.

- Types: F, P and Q are finite numbers with absolute value at most 2^53−1, or null. G and H are always null. Every other position is a string or null. A string must be nonblank after JavaScript `trim`, at most 30,000 UTF-16 units, with no C0 control except TAB/LF/CR and no lone surrogate. A numeric-looking specification such as `110` is written as the string `"110"`.
- A null C requires `status:"held"`. `held` requires at least one review reason.

**Proofs.** `proofs` maps every letter A–Q to exactly one of:

- `{"reason": "..."}` when the value is null; the reason must be specific.
- `{"refs": [...], "transformation": "...", "role_basis": "..."}` when the value is not null.

Proof rules:

- Every proof cell must have a non-null `canonical_raw`, so a proof can never cite an empty or unusable cell.
- All proof cells of one field are on one sheet.
- F, P and Q are each proven by exactly one cell, whose canonical text parses (writer `numericRaw`) to the value. Only ASCII digits, an optional sign, optional `,` thousands grouping and one decimal point are accepted.
- If the source cell for F, P or Q is not such a plain numeric literal (for example `2台`, full-width digits, or a date-typed cell), the field is **null** with a specific reason. Its raw text is still kept.
- F's proof cell must be the item's raw `quantity` cell.
- A field proven only by `context:` references is allowed for L alone. Any other field proven only by context must be null with a reason.

**Raw references.** `raw_refs` has the six raw fields `description, unit, quantity, unit_price, amount, remarks`. Each is `{"refs":[...], "reason_if_empty": string|null}`. A non-empty list requires `reason_if_empty:null`, and an empty list requires a specific reason.

- `unit`, `quantity`, `unit_price` and `amount` hold at most one cell each: the item's own cell in that role on its anchor row (FIELD_ROLES R22).
- `description` lists the logical item's descriptive text cells in row-major order (top to bottom, then left to right). These are its name/description column and any separate specification or description column, including proven continuation rows. Exclude the item-number cell and the unit, quantity, price, amount and remarks cells. The checker enforces row-major order and these exclusions.
- `remarks` lists the item's remarks-column cells in row-major order.
- Every listed cell must have non-null `canonical_raw`; empty cells are never listed. The copied raw text is the canonical texts joined with U+000A.
- A content cell that cannot be carried (date, boolean, error, or control characters) is never listed. A raw role that would need such a cell has an empty selection and a specific reason. The cell stays in the census.
- A description cell or anchor cell belongs to exactly one item. Sharing one across items is an item-boundary error.
- Consistency: a non-null E equals the copied raw unit exactly. A non-null F equals `numericRaw(raw quantity)`. A non-null Q equals `numericRaw(raw unit_price)`.

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
- A non-null A or B needs a non-null `group_id`. A must equal that group's `name` exactly, and B must equal its `specification` exactly.
- A contractual grouping alone does not prove physical ownership or enclosure count.

**Component links.** Every `analysis_component` item has exactly one link, and a demand item has none. A link is `{component_id, parent_id, status, basis_quantity, basis_raw_ref, basis_unit_ref, refs, reason}`.

- `supported` (basis cells per FIELD_ROLES R21: the component row's own quantity and unit cells): the parent is a demand item other than itself, `basis_quantity` is greater than 0, `basis_raw_ref` is one cell whose canonical text parses to `basis_quantity`, and `basis_unit_ref` is one nonblank, non-formula-like cell of saved type `text`. All basis cells are on one sheet. Never multiply by the parent quantity.
- `held`: the admitted writer cannot carry a held or unlinked component, so the **whole export is held**. The response and census are still retained. Never delete a component or invent a link to avoid this.

**Source roles.** Each source role is `{role, refs, reason}`, with role one of `demand_content, analysis_content, item_identifier, header, section, financial_summary, commercial_note, document_reference, footer, unresolved`.

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
- text with control characters;
- a non-L field proven only by context.

The route reports three categories:

- `invalid`: a defect in the response. Correct it from the source.
- `field_must_be_null`: the cited source cannot be carried for that field or raw role, for example a date, boolean or error cell, non-ASCII digits or text with units, or a non-L context-only proof. Leave the field or selection empty with a specific reason; never alter the source meaning.
- `unrepresentable_hold`: the admitted writer cannot carry a true answer. Keep the answer; the export is held.

Before `check` passes, it builds exactly the carrier that `convert` would write and runs a Python port of writer004 `validateCarrier` and `prepareMatrices` on it. This port is parity-tested against the real writer. Any overflow of the writer's count or length caps by an adapter-built string or list is reported as `WRITER_WOULD_REJECT_*` (`unrepresentable_hold`).

## 5. Carrier mapping (adapter output)

`convert` writes `cps.cached-xls-research-carrier.v1` (or `-xlsx-` for `cached_xlsx`) for `writer004.validateCarrier`:

- `source` is the inventory `carrier_source`, copied verbatim. `metadata` holds the response schema/status, the inventory, response and ledger hashes, the adapter version, the profile and the adoption status, with no path strings.
- Demand items go to `items` and analysis components to `components`, in response order. Values, status and review reasons are copied unchanged, and a type-exact comparison of values is asserted.
- `raw` is the copied canonical text.
- Non-null fields become evidence. A field with cell refs becomes `{location, anchor, raw_text (the cited canonical texts joined with LF), transformation}`. Its transformation is a JSON string `{"transformation","role_basis","context_refs"}`, so `role_basis` is kept losslessly. L proven only by context becomes `{selection_evidence, transformation}`, where `selection_evidence` is JSON with the fact's ref, namespace, value and basis plus the role basis.
- Null fields become `null_reasons`.
- Groups map to writer groups, with the relationship and references packed into `anchor` JSON.
- Each supported link becomes `composition{parent_id, basis_quantity, basis_unit, basis_location, basis_raw}`.
- `nonitems`: one entry per cell whose primary role is `item_identifier, header, section, financial_summary, commercial_note, document_reference, footer` or `unresolved`, in inventory order. `kind` is the role and `anchor` is the cell ref. `text` is the lossless typed wrapper `{"conflicts","formula_record_present","saved_type","state","value"}`, serialized as compact sorted JSON. `reason` is the role reason.
- Anchor use never removes an identifier from the census (anchor-plus-census).
- `CENSUS_LEDGER.json` records one entry per inventory position: state, original value, formula flag, conflicts, primary role, every raw, proof, anchor, group and basis use, and census membership. It also keeps the response's empty-selection reasons and link reasons, which have no writer slot. Its hash is in the carrier metadata.
- The ledger is written even when the response is not carried, so the census is always retained.
- `check-inventory` validates an inventory before generation: writer source rules, case/family IDs, canonical text, content cells outside views and views without content.

A carrier proves structure only. Writer acceptance, ledger completeness, reader agreement and comparator pairing are not semantic correctness.

## 6. Evaluation boundary

Freeze the response bytes before conversion and the carrier before any evaluator access. The source comparator pairs rows by sheet and anchor cell. A comparator limitation is a fact about the evaluator; it must never be compensated for in generation. Historical targets, source expectations and prior outputs never enter a generation context.
