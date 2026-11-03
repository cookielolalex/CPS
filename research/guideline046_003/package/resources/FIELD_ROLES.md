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

For this cell-based candidate, raw multi-cell descriptions/remarks join proven continuation cells with literal newlines. Derived C/D/J replace actual newlines/continuation boundaries with one U+0020; retain meaningful internal spaces and stored Unicode spelling. When D is assembled from source spans that are not contiguous in the source, join them in source order with U+FF1B only (rule R4 below). Trim only whitespace created at a new C/D allocation edge. Do not apply that rule to an unsplit original field or J. A separable boundary delimiter left at a new C/D edge is dropped (R4), and the transformation says so; meaningful signs, ranges and identifier characters remain. Separable wrapping parentheses around a moved technical/scope qualifier stay in raw evidence, while the underlying qualifier remains in D. Parentheses integral to the technical expression are retained. The 046c allocation rules below require independent semantic review before original-source trials.

Do not remove a leading sign to satisfy a workbook writer. If a meaningful value cannot be represented safely by the admitted writer, hold the output and retain its exact value; do not silently omit or escape it into a different value.

## Allocation rules R1–R12 (046c, declared 2026-11-03 before any 046c generation)

These rules are generic and cite no contract. When a rule and an older sentence above disagree, these rules govern; when two of these rules disagree, apply R12. Revised after the independent semantic review of 2026-11-03; R1b and the R6 severity follow owner decisions of the same date.

**R1 Classify by predicate.** *Financial annotation*: a price, fee, tax, discount, payment, estimate status, who bears a cost (負擔), or the inclusion/exclusion of a price, fee or estimate (含運費, 不含估價). It never enters C or D; keep it in raw text and in a review reason. *Supply-basis qualifier*: the manner or source of providing the object (租用, 臨時, 新品, 既有, 業主供料, 另案). *Inclusion/exclusion of an object, accessory or work* (含底座, 不含安裝) is a D attribute. Always give a review reason for estimate status, cost bearing and other-party supply. A service or fee demand noun (安裝費) is C.

**R1b Supply-basis qualifier placement (owner decision 2026-11-03: D).** Remove a supply-basis qualifier from C together with its separable wrapping delimiters and place it in D as a separate span, always joined to other D spans with U+FF1B (發電機 租用 100KW → D 租用；100KW). Record "supply-basis qualifier" in the D proof. Never discard it.

**R2 Fused material/construction words.** A material, construction or type word written directly before the product noun with no delimiter, so that the two read as one product designation, stays in C. Move a material, finish, grade or construction word to D only when the source separates it from the noun (delimiter, separate cell, label) or when it carries a measurable value. In R2, R3, R7 and R8, whitespace alone is not a delimiter. A measurable value is a number with a physical unit (V, A, kVA, mm², 度), a pole count (P, 極), a phase count or phase/wire system (單相, 三相, 1φ, 3φ4W, 單相三線), or a grade code containing digits (SUS304). Letter-only abbreviations (PVC, XLPE) and stage, gang or circuit counts (段式, 聯, 路) stay in C. When fusion alone leaves the role unclear, keep the word in C and say so in the proof.

**R3 Counts.** A composition count stays attached to the sub-object noun it counts, in that noun's field: C when the sub-object is part of the name (按鈕開關三只組合盒); D when it is an included accessory introduced after a delimiter by 含, 附, 內含 or 包括 (含2只底座). A count or status word that limits how much work a service line covers — how many objects are installed, moved, removed or tested, or new versus existing — is a *scope count*; its placement is UNDECIDED pending review: keep it with its status word in exactly one of C or D, record "scope count; placement undecided" in the proof, and keep the work noun and its object in C. On a work line, new/existing words are R3 scope words; on an object line they are R1 supply-basis qualifiers (R1b). A count restating the item quantity (每盤1只) is cited in F's role_basis and its placement is undecided (R8 class "quantity-basis count"). Neither kind of count changes F or P or creates extra rows.

**R4 Joiners.** D spans are contiguous only within one source stream (description, specification or remarks) when every character between them stays in D; a newline or continuation boundary between them becomes one U+0020. Spans are non-contiguous otherwise, including when a removed wrapping delimiter or text placed elsewhere lies between them. Join non-contiguous D spans with U+FF1B only, ordered by stream (description, specification, remarks), then row-major, then by character. Remove separable wrapping delimiters around each moved span; keep delimiters that are part of the technical expression. For C, drop separators left at new edges (never half of a kept bracket pair), keep any delimiter between two retained spans, and add nothing (產品，端子台).

**R5 Document references.** A clause whose content is only a reference to a document, standard, drawing, catalogue or specification that is not in the source packet — including "per …", "refer to …", "according to …", "built to …" (詳…, 依…, 參照…, 按…規範) — is a document reference. Keep it in raw text and in a review reason or limitation. It never enters C or D and never supplies a value. If the same clause also states an explicit technical value, place only that value in D. A number that only names the governing document (CNS…, 台電規範, 圖號) is a reference even without 依/詳; a designation stating the attribute itself (IP65) is a value. A missing detail schedule that defines the demand holds the affected items (guideline §1).

**R6 Party roles.** A company, agency or person name that appears only in a letterhead, title, addressee line, page header or footer, stamp or signature block does not establish K, M or N. Only a label naming that relation to this order (訂購廠商; 訂購客戶 or 訂購單位; 使用客戶 or 使用單位) or contract text stating it establishes K, M or N; contract-party, contractor, supplier or quote-sender labels (甲方, 乙方, 業主, 供應商, 承包商) do not. Otherwise leave the field null with a reason that names where the name appears and that no role is stated. One party fills several roles only when each is separately labelled or stated. Inferring K, M or N from document furniture is a **critical error** (owner decision 2026-11-03).

**R7 Acronym beside a full name.** When the source gives a full name and, at a separate delimited position, an acronym, abbreviation or type designation, keep the full name in C and leave the acronym where its position puts it (D when it sits in a delimited attribute list). Put an acronym in C only when the source writes it as part of the name with no delimiter, or when it is the only name. A bracketed acronym directly after the full name (自動切換開關(ATS)) is an undecided class (R8 class "acronym gloss"). Never expand or translate either form.

**R8 Undecided classes.** When a token belongs to a class whose C/D placement the policy declares undecided (the classes listed at the end of this rule), the proof of the field that holds it must name the token's class (for example "protocol/interface designation; placement undecided"), and the null reason or proof of the other field must say the token was placed elsewhere. A token is in the protocol/interface class when it names a communication protocol, bus, port, network standard or transmission medium attached to a device noun, whether written before or after it, fused to it, abbreviated or transliterated. A medium word is in the class only when it qualifies a signal device; when it names the cable kind supplied (光纖電纜, 網路線), R2 governs. As in P2, the class covers attached tokens only; a delimited token is an ordinary D attribute. An undecided-class token kept in C keeps its source characters, including wrapping delimiters (電錶箱安裝（新設1只）); one moved to D follows R4 (新設1只); the other field never repeats it. The undecided classes are: protocol/interface designation, scope count (R3), quantity-basis count (R3) and acronym gloss (R7).

**R9 Truthful null reasons.** A null reason must be true of the item's whole logical scope (all its cells, its group heading and applied project-level text), naming any candidate text of that field's kind — including unresolved-role tokens — and where it was kept. Never state that the source has no such content.

**R10 Total discrepancies.** When a cached subtotal or total disagrees with the amounts it appears to sum, or its label leaves unclear whether it is a local subtotal or an overall total, record the observation and the ambiguity in limitations with the cells involved; judge discrepancies on canonical decimal values. Do not repair, do not recompute into any output field, and do not read a zero cache as a confirmed zero total.

**R11 Nonitem roles.** financial_summary: subtotal, total, tax, discount, management or insurance allocation and amount-in-words cells, plus the labels and qualifiers attached to those figures (such as tax-inclusion words beside a total). commercial_note: payment, delivery, validity, warranty, scope-option, supply or estimate statements that are not an item's own cell. document_reference: pointers to documents not in the packet. unresolved: two or more roles remain possible (name them) or no listed role fits (say why).

**R12 Precedence.** When rules send the same text to different destinations, the first applicable rule in this order governs: R11, R6, R5, R1 (financial annotation), R8, R3, R1b, R7, R2. Cite every matching rule in the proof. Never create a new undecided class during generation; record residual doubt in limitations.

## Clarifications R14–R24 (046c, declared 2026-11-03 before any 046c generation)

These answer generic questions raised during independent source-expectation authoring under the R13 consistency gate. They cite no contract and follow from R1–R12 and the published examples (N03, N08, N20, A13, A23).

**R14 Delimiters inside a moved span.** R4 removes wrapping delimiters only when they enclose the whole moved span. Delimiters, parentheses and brackets inside one contiguous moved span are kept verbatim (A13: D PLC，16點輸入).

**R15 Composing C.** Within C a bracket pair is kept or removed as a whole: kept when its content stays in C, removed when its whole content moves to D. Two retained name spans keep the source delimiter between them; if none remains, they are joined with nothing (電纜｛45度｝彎頭 → C 電纜彎頭, D 45度).

**R16 Code tokens.** An alphanumeric code token without a measurable unit (letters with digits, e.g. QX-620) written before or after a clear noun with no source label is not part of C and not part of D. Keep it in raw text and a review reason with its role unresolved (N03, N08, N20). A labelled code follows its label (型號 → I). A lexical name or acronym without digits (PLC-CPU模組, NFB) is a name, not a code token.

**R17 Fused measurable values.** A measurable value (R2) fused to a noun moves to D even without a delimiter (45度彎頭 → C 彎頭, D 45度; 100KW發電機 → C 發電機, D 100KW).

**R18 Condition words that name the object.** A condition word that says what the object is (廢料, 廢水, 污泥, 舊品 when it names the material handled by a service) is part of the object noun in C. R3 status words are limited to new/existing/reused/temporary words that limit scope.

**R19 Procedural clauses.** An instruction, coordination or approval clause (依監造指示, 配合現場, 經核可後) is treated like a document reference (R5): raw text and a review reason only; never C or D.

**R20 Conformity verbs.** 符合…, 合於…, conforming to … are document-reference verbs under R5.

**R21 Analysis basis cells.** For a supported component link, `basis_raw_ref` is the component row's own quantity cell and `basis_unit_ref` is the component row's own unit cell. A block-header unit label is context for the link proof, not the basis unit.

**R22 Single-cell raw roles on multi-row items.** The unit, quantity, unit-price and amount raw cells are the item's cells in those columns on its anchor row. Cells in those columns on continuation rows are classified by their own role (financial_summary, commercial_note, …) and stay in the census; they are not concatenated into the item's raw fields.

**R23 Cost-line codes.** A pricing, resource or work-item code (工料編碼, 資源代碼, 工項編號) identifies a cost line, not a technical attribute: keep it in raw text; never C or D.

**R24 Remaining doubt.** Any C/D question these rules still leave open is recorded in limitations with the cells involved (R12); evaluators declare complete alternatives for it, and the next policy version decides it.

## Commercial and quantity distinctions

Keep supplied-by-customer, self-transport, no-estimate, original quantity and responsibility separate. Search all financial/remark cells for these clauses. A missing price alone does not prove nonresponsibility; the no-enclosure AND no-estimate condition must be established completely. A real zero remains zero. Unknown, explicit empty string and error are not interchangeable facts.

Retain services and costs that are actual source demands. Taxes, whole-project negotiation, management allocation and totals have financial/context roles, not additional supplies merely because a unit or number is present. Do not borrow an 已填-stage deletion convention.

For composition or bundled wording, preserve the count's referent without changing F or creating extra purchases. For analysis, record literal per-unit basis and source quantities separately; no multiplication/division without independently supported scope and an admitted policy.
