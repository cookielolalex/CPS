# Output contract and current implementation boundary

Candidate046a proposes a source-reference response separate from existing compact carrier versions. `SEMANTIC_RESPONSE.schema.json` is a draft data contract; a schema-shaped document alone is not an accepted carrier. The resolver/adapter and source inventory must be independently reviewed and tested before any original-source trial. There is no automatic fallback to an older profile.

## Required response

- Exact schema identifier, case identity and inventory hash; research_draft, partial or held status only.
- Main demands and analysis components with unique IDs and explicit roles. Each has exactly17 values in A–Q order and exactly17 proof entries. Every null has a nonempty specific explanation; every supported nonnull has actual source references, a transformation and a role basis.
- Raw-field reference lists for original description, unit, quantity, quoted unit price, amount and remarks, plus absence/unsupported reasons when applicable. These references identify source roles and do not authorize Q or procurement values.
- Anchor references and truthful source item identity. An arbitrary row number cannot establish item scope.
- Component links with supported parent/component IDs, positive literal per-unit basis and source evidence, or explicit held reasons. Main demands and components remain separate, with no implicit multiplication.
- Primary source-role assignments and limitations, including every unresolved source region/role. A failure must not be hidden by pruning declarations or selecting only successful rows.

The JSON schema can check shapes, required members and basic types. Additional guards must check reference identity/scope, value/proof consistency, null-reason coverage, unique IDs and parents, stage blanks, semantic source coverage, schema/profile compatibility and complete source obligations. None of these substitutes for independent semantic reading.

The exact17 columns are in `FIELD_ROLES.md`. Nonfinite numbers, formula execution and active content are prohibited. Meaningful strings that begin with spreadsheet-sensitive characters must be preserved and handled only by an admitted safe writer; if unsupported, hold rather than stripping them. Original source files remain unchanged.

## Freeze and review

Freeze original response bytes before expansion or evaluation. Freeze expanded carrier, source inventory, input/package hashes, model/effort/tool observations, all limitations and all failed/unattempted outcomes. Do not repair an original response to obtain a better score. An assembly repeat copies the same frozen carrier and measures export repeatability, not another independent reader.

For each saved workbook compare every saved primary/auxiliary cell against the frozen carrier and inspect readable exported views. Keep source semantics, reference/raw/coverage mechanics, writer fidelity, visual usability, historical eligibility and historical agreement as separate results. Unknowns and critical failures prevent business release. This package has no deployment-approved status.
