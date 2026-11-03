# Independent review record for candidate 046b and route v2

- Date: 2026-11-03 (Asia/Taipei).
- Reviewer: a fresh Claude Code subagent context (observed model `claude-opus-5-5`). It was independent of the package author. It read only public code and docs, the archived writer copy and its own scratch fixtures. It did not read the naming study or any private evidence.
- Status: **APPROVE_FOR_BOUNDED_SOURCE_TRIAL** after the round-1 fixes and a confirmation round. This is not semantic approval or deployment approval.

## Round 1 (package draft): APPROVE_AFTER_LISTED_FIXES

**Blocking**

- B1: Unicode digits passed the checker's numeric rule but not the writer's ASCII-only JS `\d`.
- B2: Writer count and length caps were not applied to strings and lists built by the adapter, such as packed transformations, census wrappers, more than 5000 nonitems, and more than 500 group limitations.

**Should-fix**

- S1: A dropped item was not detected.
- S2: The docs and the example disagreed on the role of remark cells.
- S3: True values the writer cannot carry were categorized as `invalid`.
- S4: No census ledger was written for a held response.
- S5: Some contract rules were not enforced.
- S6: There was no pre-generation inventory gate.
- S7: The example was inconsistent.

**Notes:** a crash on malformed input, a tautological value guard, dropped formula and conflict flags, comparator ambiguity risks, and the case-ID assert missing from the wrapper.

## Fixes (commit `d759f42`)

- `check` builds the exact carrier and runs a Python port of writer004 `validateCarrier` and `prepareMatrices`. A 98-case fuzz shows the port gives the same verdict as the real writer. Numeric literals are ASCII-only.
- A new `field_must_be_null` category covers uncarriable source cells and non-numeric quantity text.
- New checks: content cells that no item uses, row-major order of raw streams, description exclusions, anchor row rules, basis unit must be a text cell, and cross-item sharing.
- The ledger is always written, including the empty-selection and link reasons.
- New `check-inventory` command.
- The checker reports errors instead of crashing.
- The examples were made consistent.

## Round 2 (confirmation): APPROVE_FOR_BOUNDED_SOURCE_TRIAL

- B1, B2, S1–S5, S7 and the notes: **fixed**.
- S6: partial. The comparison of the inventory with the frozen `carrier_contract` was then run separately for both cases (see below).
- New should-fix item: an anchor sitting on another item's description cell was not caught. Fixed afterwards with a single identity-cell owner map, together with these minor items:
  - an uncarriable basis is now a hold;
  - the schema item cap now matches the writer (2000 demand items + 2000 components);
  - the docs now cover a cell that holds both the item number and the description, and count group uses.
- Route tests: **113/113 pass**. They use invented fixtures through the archived writer004 bytes, with only the `@oai/artifact-tool` import stubbed.

## Interface checks against the frozen evaluators (results only; no expected values seen)

- **1140908:** checked in the evaluation role. The frozen expectations (`04b5f42c…`, status `FROZEN_BEFORE_MODEL_INVOCATION`) have `carrier_contract` schema, case, family and source equal to the v2 inventory `carrier_source`. The archived comparer matches the public `compare_source043.py` (`1ececf30…`).
- **1141208:** the final expectations' `carrier_contract` equals the v2 inventory `carrier_source`. Status is `FROZEN_BEFORE_MODEL_INVOCATION`.

## Known limits (by design, recorded)

- Comparator limits: pairing uses the column-B anchor; a covered-merge B cell cannot pair; any carrier component makes the numeric gates false; the unsupported-field flag is computed against canonical values only.
- Workbook export, saved-cell QA and visual QA cannot run here (no `@oai/artifact-tool`, Windows-only source helper). They are recorded as unattempted.
- The isolation of generator contexts is instruction-based and audited after the run. It is not OS-level.
