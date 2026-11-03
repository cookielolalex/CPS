# Proposed source-reference and coverage contract v1

Status: specification for independent review. No production resolver or writer adapter is implemented/admitted by this package. Do not feed this proposal directly into an older compact-carrier exporter. This changes transport, not the requirement that the AI decide item identity and field roles.

## Immutable preparation input

The source preparer builds a complete inventory from only authorized, pinned source bytes. It includes the exact case/source identity, selected scope, every physical cell position in that scope, original value/type and available cache/formula/merge metadata, a stable reference ID, and a declared canonical raw-field representation. It also includes separately authorized contextual identity facts with namespace and selection evidence. A context fact is not a workbook cell.

Cell references are unique and bind exact source hash, sheet and address. Equal text in two cells does not make references interchangeable. Preserve the whole inventory, including typed blanks, explicit empty strings, zeros, covered cells and conflicts. Hash the completed inventory before generation. The model response echoes that inventory hash; case IDs alone are insufficient.

The schema's `canonical_raw` is a declared representation for expanded raw fields, not a replacement for the original saved value. Preparation must derive it from the original source and the frozen representation profile, never from generated names or evaluator values. The complete preparation route and profile require independent review before admission.

## Scalar representation profile proposed for the cached-cell route

1. Preserve text cells byte-for-byte at the Unicode-string level, including spaces, glyphs, punctuation and textual numerals. Text `001.00` remains that text. Do not parse a string into a number.
2. For an actual finite numeric cell/cache, the expanded raw field is plain base10 text of its observed numeric value, without a redundant fractional `.0` or trailing fractional zeros. No grouping separators or exponent are introduced. Preserve the original numeric type/value and available native literal separately. A reader that already lost precision cannot be made exact by serialization; hold it.
3. A true blank and an explicit empty string both yield null in this particular derived raw-field profile, while the inventory and nonitem census still retain their distinct original states. This prospectively states the existing cached-cell raw expectation; it is not permission to change frozen scores or to apply this profile to other formats automatically.
4. Error, missing cache, unresolved text and covered-conflict states are not ordinary nulls. They retain the original state and block supported copying for affected required fields. A covered cell may refer to a validated anchor only under the recorded merge rule; it cannot supply an independent quantity or specification.
   Boolean saved values also remain literal in the inventory/census. This initial material raw-field profile does not interpret them as numbers or ordinary blanks; unsupported boolean raw selections are held with an explicit reason.
5. For a single raw field reference, copy that cell's prepared canonical value. Unit/quantity/unit-price/amount have at most one cell reference each in this initial profile. A proven multiline description or remarks stream can have ordered references; preserve each stream separately and join its source fragments with U+000A. Null/empty fragments keep their boundary in a multi-fragment join rather than fusing adjacent tokens. An empty reference list yields null only with an explicit source-absence/unsupported-role reason. Do not combine unrelated specification and remark streams merely to make output match an expectation.
6. Nonitem census and coverage records copy original saved values and types, including explicit empty strings and numerical zeros; they do not use the derived raw-field null mapping. Raw fields, source inventory and derived C/D fields have distinct serialization purposes.

The legacy canonicalization must be checked against the unchanged prospectively frozen evaluator contract before a trial. A mismatch blocks admission; it is not solved by editing expected values or adding post-output alternatives. Numeric lexical formatting in a cached value is not the same as workbook display formatting or proof of formula correctness.

## AI response and copying responsibilities

The proposed `SEMANTIC_RESPONSE.schema.json` contains the AI's17 values, per-field evidence or null reason, item identity/role, raw-field references, anchor references, component-link decisions and grouped primary source-role assignments. Evidence uses exact cell/context reference IDs and a transformation/role explanation. An I/J assertion requires semantic role evidence; valid IDs alone are insufficient.

The resolver may validate and copy only. It must reject an unknown reference, wrong inventory/case/hash, unavailable source value, duplicate item identity, invalid parent link, out-of-scope cell, wrong context namespace or inconsistent value/reference selection. It must not select a more favorable reference, shorten a name, change a technical value, infer a brand, repair a model response, or borrow evaluator answers. Do not equate structural reference validity with semantic support.

An adapter to the existing expanded carrier must be separately specified and reviewed. It preserves the original response and source inventory, adds copied raw/proof/coverage records as a new derived artifact, and checks every17-field value is unchanged. The old writer remains a value copier; its safety rules can still hold an unsupported output. Original response failures are retained, not reformatted into successes.

## Coverage ledger and nonitem census

Create one ledger entry for **every** position in the immutable inventory before consuming the response. Record source state, primary semantic classification, raw uses, field-evidence uses, anchor uses, census inclusion and any conflict/unresolved status separately.

The model supplies grouped primary classifications for every nonblank usable source cell: demand content, analysis content, item identifier, header, section, financial summary, commercial note, document reference, footer or unresolved. One cell has one primary classification in this proposal; multiple secondary uses are allowed and individually recorded. Ambiguous mixed content is retained as unresolved until a declared split/role rule accounts for it. Do not classify it as nonitem merely because it was not used in a value.

True blanks/empty strings and covered states remain in the ledger from the inventory. Mechanically preserving an unclassified cell sets `unresolved`, not `reviewed`. A complete positional ledger does not prove a correct demand denominator.

Nonitem census includes classified headers/sections/financial/commercial/reference/footer cells **and item identifiers**, copied from the original inventory with exact locators. If an identifier is also an item anchor, keep both uses. Anchor use never suppresses census inclusion. The census comes from the complete source and declared role policy, not a remembered list of expected cells or a post-generation diff. Demand/analysis content still retains full source records in the ledger even when it is not a nonitem entry.

The validator must report omitted classifications, duplicate/conflicting assignments, unresolved roles and relevant blank/covered conflicts. Incomplete semantic coverage cannot receive complete-source acceptance merely because all source bytes were stored. The output remains partial/held where material obligations are unresolved.

## Review boundary

Before any original model call: independently review this exact specification, schemas, source preparation/canonicalization, source-role expectations, accepted alternatives, adapter and failure behavior. Test invalid and overlapping references, typed empty states, wrong-case identities, anchor-plus-census use and unchanged model values through the actual changed route. No such route trial is claimed by the authoring checks for this package.
