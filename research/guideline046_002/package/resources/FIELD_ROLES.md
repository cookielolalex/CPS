# The17 output fields (candidate 046b)

Keep this order exactly. Auxiliary evidence/coverage records do not add primary columns. Source roles govern values; an empty cell needs an actual reason and is not automatically a correct extraction.

| Field | Label | Assignment rule |
|---|---|---|
|A|盤體名稱|Name of the panel the item belongs to, proven by an explicit contractual-group, sub-panel or in-box relationship to a separately identified panel; carried as a response `group` (relationship kind recorded) and A must equal that group's name. A location or general work section is insufficient.|
|B|盤體規格|Explicit supported specification of that same group panel; B must equal the group's specification. No later-stage dimension inference.|
|C|材料名稱|Complete identifying supply/accessory/compound/service name from the logical item, wherever the noun occurs. Preserve functional/specific nouns and attached composition counts.|
|D|規格|Source-backed technical rating, material, dimension, type, accessory and scope attributes with their referents. Bare unavailable-document pointers and financial annotations stay in ancillary records.|
|E|單位|Literal source unit in its proven role. No conversion.|
|F|數量|Literal source quantity with type and basis. No box-count multiplication, component expansion or rounding.|
|G|單價|Procurement price: null at this stage. Do not substitute a contract rate.|
|H|複價|Procurement extended price: null at this stage. Do not calculate zero or F×Q.|
|I|型號|Identifier with supported model/type role in authorized source context; no code-shape or memorized catalog inference.|
|J|廠牌|Supported manufacturer/brand, not a supplier/customer or a guessed model brand.|
|K|訂購廠商|Explicitly supported ordering supplier; contractor or quote sender alone is insufficient.|
|L|工程編號|Confirmed internal project identity with namespace/selection evidence, not a printed asset/accounting/owner code.|
|M|訂購客戶|Confirmed ordering customer role; do not expand abbreviations into guessed company names.|
|N|使用客戶|Confirmed using customer role; keep distinct from M and the worksite.|
|O|需要日期|Explicit required-date role; delivery clauses alone do not establish this value.|
|P|需要數量|Explicit ordering/required quantity; do not automatically copy F.|
|Q|合約價|Confirmed accepted item unit-rate role. Quoted amount, total, discount, analysis price or negotiation value is insufficient. Adoption uncertainty holds Q.|

## Types, groups and stage blanks (046b interface)

F, P and Q are JSON numbers or null; G and H are always null; every other populated value is a JSON string (write a numeric-looking specification such as `110` as the string `"110"`). A or B requires a group; an ungrouped item leaves A and B null with a reason.

Panel self-relationship (declared 2026-11-03 before any 046b generation): A/B describe the panel that contains or contractually groups the item. A demand line whose supplied object is itself an enclosure or panel does **not** populate A/B with its own name or specification; its identity goes to C and its explicit dimensions/material to D. It receives A/B only through a separate explicit relationship to another identified panel. In flat numbering, a sibling enclosure line is not the panel of the lines after it.

Protocol/interface designations attached directly to a device noun (for example a bus or port standard before or after the noun): no versioned policy yet decides between C (as part of the lexical name) and D. Place the token in exactly one of C or D, record its protocol role in the proof, and never discard it. Evaluation of this class must declare both placements prospectively.

## Naming and representation

Explicit name/spec columns are strong structural evidence, not a prohibition against recovering a name from a mislabelled/combined specification column when the complete item proves the role. Record the actual source cells and why allocation differs from their headings. Never invent a noun to fill C.

Apply the full naming policy and source-language default. Preserve generic source prefixes under this candidate's explicit policy. Preserve both general and specific product nouns unless a separately versioned policy relocates the general category into ancillary context without losing the specific name. No automatic historical-name aliases are approved.

For this cell-based candidate, raw multi-cell descriptions/remarks join proven continuation cells with literal newlines. Derived C/D/J replace actual newlines/continuation boundaries with one U+0020; retain meaningful internal spaces and stored Unicode spelling. Distinct description and remark clauses in D use U+FF1B. Trim only whitespace created at a new C/D allocation edge. Do not apply that rule to an unsplit original field or J. A separable boundary delimiter can be omitted from derived fields only with an explicit transformation; meaningful signs, ranges and identifier characters remain. Separable wrapping parentheses around a moved technical/scope qualifier stay in raw evidence, while the underlying qualifier remains in D. Parentheses integral to the technical expression are retained. This boundary distinction needs independent review before original-source trials.

Do not remove a leading sign to satisfy a workbook writer. If a meaningful value cannot be represented safely by the admitted writer, hold the output and retain its exact value; do not silently omit or escape it into a different value.

## Commercial and quantity distinctions

Keep supplied-by-customer, self-transport, no-estimate, original quantity and responsibility separate. Search all financial/remark cells for these clauses. A missing price alone does not prove nonresponsibility; the no-enclosure AND no-estimate condition must be established completely. A real zero remains zero. Unknown, explicit empty string and error are not interchangeable facts.

Retain services and costs that are actual source demands. Taxes, whole-project negotiation, management allocation and totals have financial/context roles, not additional supplies merely because a unit or number is present. Do not borrow an 已填-stage deletion convention.

For composition or bundled wording, preserve the count's referent without changing F or creating extra purchases. For analysis, record literal per-unit basis and source quantities separately; no multiplication/division without independently supported scope and an admitted policy.
