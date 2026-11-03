# The17 output fields (candidate 046c)

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

For this cell-based candidate, raw multi-cell descriptions/remarks join proven continuation cells with literal newlines. Derived C/D/J replace actual newlines/continuation boundaries with one U+0020; retain meaningful internal spaces and stored Unicode spelling. When D is assembled from source spans that are not contiguous in the source, join them in source order with U+FF1B only (rule R4 below). Trim only whitespace created at a new C/D allocation edge. Do not apply that rule to an unsplit original field or J. A separable boundary delimiter can be omitted from derived fields only with an explicit transformation; meaningful signs, ranges and identifier characters remain. Separable wrapping parentheses around a moved technical/scope qualifier stay in raw evidence, while the underlying qualifier remains in D. Parentheses integral to the technical expression are retained. The 046c allocation rules below require independent semantic review before original-source trials.

Do not remove a leading sign to satisfy a workbook writer. If a meaningful value cannot be represented safely by the admitted writer, hold the output and retain its exact value; do not silently omit or escape it into a different value.

## Allocation rules R1–R12 (046c, declared 2026-11-03 before any 046c generation)

These rules are generic. Each rule cites no contract. When a rule and an older sentence above disagree, these rules govern; when two of these rules disagree, apply R12.

**R1 Financial annotation vs supply-basis qualifier.** A financial annotation is text about price, cost inclusion, estimate status, payment, discount, tax, or who bears a cost. It never enters C or D; keep it in raw text and, when it affects scope or responsibility, in a review reason. A supply-basis qualifier states on what basis the object is provided — for example hired or leased instead of bought, temporary instead of permanent, new instead of existing, reused, or supplied by another party. A supply-basis qualifier is not a financial annotation, even when the same word can also name a fee.

**R1b Supply-basis qualifier placement: UNDECIDED (owner decision pending).** Keep a supply-basis qualifier in exactly one of C or D. Record its class ("supply-basis qualifier; placement undecided") in the proof of the field that holds it, and say in the proof or null reason of the other field that it was placed there. Never discard it. Evaluators must declare both complete placements.

**R2 Fused material/construction words.** A material, construction or type word written directly before the product noun with no delimiter, so that the two read as one product designation, stays in C. Move a material, finish, grade or construction word to D only when the source separates it from the noun (delimiter, separate cell, label) or when it carries a measurable value (thickness, grade code, rating, size). When fusion alone leaves the role unclear, keep the word in C and say so in the proof.

**R3 Counts.** A count that says how many sub-objects the supplied object contains or combines stays attached to the sub-object noun in C (composition count). A count or status word that limits how much work a service line covers — how many objects are installed, moved, removed or tested, or new versus existing — is a *scope count*; its placement is UNDECIDED pending review: keep it with its status word in exactly one of C or D, record "scope count; placement undecided" in the proof, and keep the work noun and its object in C. Neither kind of count changes F or P or creates extra rows.

**R4 D joiner.** When D is assembled from source spans that are not contiguous in the source — whether they come from different cells or from different positions in the same cell, for example a qualifier before the name and another after it — join the spans in source order with U+FF1B and nothing else. Use U+0020 only to replace a newline or continuation-cell boundary inside one continuous span. Remove separable wrapping delimiters around each moved span; keep delimiters that are part of the technical expression.

**R5 Document references.** A clause whose content is only a reference to a document, standard, drawing, catalogue or specification that is not in the source packet — including "per …", "refer to …", "according to …", "built to …" (詳…, 依…, 參照…, 按…規範) — is a document reference. Keep it in raw text and in a review reason or limitation. It never enters C or D and never supplies a value. If the same clause also states an explicit technical value, place only that value in D.

**R6 Party roles.** A company, agency or person name that appears only in a letterhead, title, addressee line, page header or footer, stamp or signature block does not establish K, M or N. Fill these fields only when the source labels the role or the contract text states it; otherwise leave the field null with a reason that names where the name appears and that no role is stated. Do not copy one party into several role fields.

**R7 Acronym beside a full name.** When the source gives a full name and, at a separate delimited position, an acronym, abbreviation or type designation, keep the full name in C and leave the acronym where its position puts it (D when it sits in a delimited attribute list). Put an acronym in C only when the source writes it as part of the name with no delimiter, or when it is the only name. Never expand or translate either form.

**R8 Undecided classes.** When a token belongs to a class whose C/D placement the policy declares undecided (protocol/interface designations, supply-basis qualifiers R1b, scope counts R3), the proof of the field that holds it must name the token's class (for example "protocol/interface designation; placement undecided"), and the null reason or proof of the other field must say the token was placed elsewhere. A token is in the protocol/interface class when it names a communication protocol, bus, port, network standard or transmission medium, whether it is written before or after the device noun, fused to it, abbreviated or transliterated.

**R9 Truthful null reasons.** A null reason must be true of the source as a whole, not only of the cell named. If text of the kind that field would hold was placed in another field or kept in raw or review records, say where and why; never state that the source has no such content.

**R10 Total discrepancies.** When a cached subtotal or total disagrees with the amounts it appears to sum, or its label leaves unclear whether it is a local subtotal or an overall total, record the observation and the ambiguity in limitations with the cells involved. Do not repair, do not recompute into any output field, and do not read a zero cache as a confirmed zero total.

**R11 Nonitem roles.** financial_summary: subtotal, total, tax, discount, management or insurance allocation and amount-in-words cells, plus the labels and qualifiers attached to those figures (such as tax-inclusion words beside a total). commercial_note: payment, delivery, validity, warranty, scope-option, supply or estimate statements that are not an item's own cell. document_reference: pointers to documents not in the packet. unresolved: only when two or more roles remain possible after reading; name them.

**R12 Precedence.** When two rules send the same text to different fields, apply the more specific rule and cite both in the proof. If neither is more specific, treat the text as an undecided class (R8) and record it in limitations so that the next policy version decides it.

## Commercial and quantity distinctions

Keep supplied-by-customer, self-transport, no-estimate, original quantity and responsibility separate. Search all financial/remark cells for these clauses. A missing price alone does not prove nonresponsibility; the no-enclosure AND no-estimate condition must be established completely. A real zero remains zero. Unknown, explicit empty string and error are not interchangeable facts.

Retain services and costs that are actual source demands. Taxes, whole-project negotiation, management allocation and totals have financial/context roles, not additional supplies merely because a unit or number is present. Do not borrow an 已填-stage deletion convention.

For composition or bundled wording, preserve the count's referent without changing F or creating extra purchases. For analysis, record literal per-unit basis and source quantities separately; no multiplication/division without independently supported scope and an admitted policy.
