# Output contract (candidate 046e)

Return one JSON file conforming to `SEMANTIC_RESPONSE.schema.json` (`cps.semantic-source-refs.v2`) and to every rule in `SOURCE_REFERENCE_CONTRACT.md`. The response states your semantic decisions and points at exact inventory cells. The adapter later copies the source text and builds the writer carrier. It cannot fix or complete your response.

## What you receive

- `SOURCE_INVENTORY.json`: the complete typed positional inventory. It is authoritative for characters, types and addresses. Compute `inventory_sha256` as the SHA-256 of this file's exact bytes.
- `view_NN.png`: reconstructed inspection images of the same saved cells. They help you see the layout. They do not add characters, and their line wrapping is artificial.
- The selected case identity is in `context_facts` (`context:case_identity`). It supports L only.

## How to build the response

1. Read the whole inventory and all views. Identify sheet roles, table headers and column roles, every logical item and continuation, groups, analysis blocks and every nonitem region.
2. For each demand line that FIELD_ROLES R45 keeps (a row, a doubt or an R42 hold), write one `demand` item; classify the cells of each line R45 excludes as `excluded_supply`; other rows keep their own roles (R11, R27, R29). For each per-unit analysis component of a block whose referenced item is a demand item, write one `analysis_component` item plus one component link; classify the cells of every other analysis block as `analysis_unlinked` (R46). Use IDs such as `R001…` in source order and `C001…` in analysis order.
3. Fill all 17 values, then give each column either a non-null proof (`refs`, `transformation`, `role_basis`) or a specific null `reason`. The transformation says how the value was obtained from the cited text, for example "copied", "text after label 型號", or "rating span moved to D; newline → U+0020". The role basis says why that text has this field role. Keep values exactly as the policy and source support them; never adjust a value to pass a check.
4. Fill `raw_refs` per `SOURCE_REFERENCE_CONTRACT.md` §3: description and remarks streams in row-major order, and at most one cell each for unit, quantity, unit price and amount. Never list an empty cell, and give a specific reason for every empty selection.
5. Set `anchor_refs` to the item's identity cell(s) on its first row, normally the item number. If an item has no item-number cell, use the first cell of its description.
6. Assign exactly one primary `source_roles` entry to every content cell in the inventory, and none to empty cells.
   - Classify an item's own description, unit, quantity, price, amount and remark cells as `demand_content` (or `analysis_content`), even when a remark is commercial in tone.
   - Every such cell must be cited by its item.
   - Classify item numbers as `item_identifier`.
   - An item cell that no raw field can carry (for example extra text in its quantity column) takes its own role, such as `commercial_note`.
   - Mark anything you cannot resolve as `unresolved` and explain why.
   - A single role entry can list many refs that share one reason.
7. Apply FIELD_ROLES R1–R47 and P1/P2. For every token of an undecided class (R8), name the class in the proof of the field that holds it and mention it in the other field's proof or null reason. Make every null reason true of the whole source (R9). Record total/subtotal discrepancies in `limitations` without repairing them (R10).
8. Set item `status` to `research_draft` or `held`; `held` needs review reasons. Set the top-level `status` to `research_draft`, `partial` (some scope is unresolved or held) or `held`. Record every unresolved obligation in `limitations` or review reasons.

## Self-check before returning

Run the package checker on your file. It reads only the two files you name:

```bash
python3 -I tools/cps046b_route.py check --inventory SOURCE_INVENTORY.json --response response.json
```

- `invalid` violations are structural defects, such as an unknown or wrong-case reference, a missing proof, a wrong type, a mismatched unit or quantity, a missing role, a duplicate role, or a content cell that no item uses. Correct the response from the source, not by deleting meaning.
- `field_must_be_null` violations mean the cited source cannot be carried for that field. Examples: a quantity written as text with a unit or with full-width digits, a date-typed or error cell, or a non-L field proven only by context. Set that field null, or that raw selection empty, with a specific reason. The source cell stays in the census.
- `unrepresentable_hold` violations mean a true answer cannot be carried by the admitted writer. Examples: a value that begins with `-`, `=`, `+` or `@`; a held component link; a non-L field proven only by context. Do not change a true value to make one disappear. Keep it, explain it in `limitations`, and return the response. The export is then held, and that outcome is recorded honestly.
- A passing check proves structure only. It is not semantic approval.

## Prohibited

- Translating, normalizing spelling, inventing a name, a model or a brand, or copying F into P.
- Filling G or H, or filling Q without verified adoption.
- Multiplying analysis bases.
- Merging separate items or dropping rows.
- Reading anything except the supplied packet and this package, and using historical worksheets, prior outputs or evaluator material.

## After return (not the generator's job)

The orchestrator freezes the response bytes, then runs `convert` to produce the carrier and census ledger, then runs the unchanged writer validation. Evaluation happens in a separate role. Workbook export, saved-cell QA and visual QA need an admitted export runtime. Where none is available, they are recorded as unattempted.
