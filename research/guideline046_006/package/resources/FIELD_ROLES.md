# The17 output fields (candidate 046f)

Keep this order exactly. Auxiliary evidence/coverage records do not add primary columns. Source roles govern values; an empty cell needs an actual reason and is not automatically a correct extraction.

| Field | Label | Assignment rule (046f: R48–R57 govern; see "Creator practice") |
|---|---|---|
|A|盤體名稱|Only on an enclosure row (R56): the enclosure noun. Null on every other row.|
|B|盤體規格|Only on an enclosure row (R56): `<w>W*<h>H*<d>D` from dimensions stated in the contract, else null.|
|C|材料名稱|Equipment lines: the glossary abbreviation or the head noun (R52). Enclosure row: the generic enclosure word (R56). Material, bulk, service and fee lines: null.|
|D|規格|The description text per R52/R53 (remaining specification on equipment lines; the full description on other lines).|
|E|單位|The line's own unit cell, verbatim (R57).|
|F|數量|The line's own quantity cell, verbatim (R57).|
|G|單價|Null.|
|H|複價|Null.|
|I|型號|Not-estimated line: 不含估價. Priced equipment line: contract-stated model, else the company brand table (R55). Otherwise null.|
|J|廠牌|Not-estimated line: 不含估價. Priced equipment line: contract-stated brand, else the company brand table (R55). Enclosure row: the company name (R56). Otherwise null.|
|K|訂購廠商|Null.|
|L|工程編號|Job input: internal case id, every row (R48).|
|M|訂購客戶|Job input: customer full name, every row (R48).|
|N|使用客戶|Job input: project short name, every row (R48).|
|O|需要日期|Null.|
|P|需要數量|Null.|
|Q|合約價|Priced line: its unit price (R54). Otherwise null.|

## Types, groups and stage blanks (046b interface)

F, P and Q are JSON numbers or null; G and H are always null; every other populated value is a JSON string (write a numeric-looking specification such as `110` as the string `"110"`). A or B requires a group; an ungrouped item leaves A and B null with a reason.

**P1 Panel self-relationship** (declared 2026-11-03 before any 046b generation): A/B describe the panel that contains or contractually groups the item. A demand line whose supplied object is itself an enclosure or panel does **not** populate A/B with its own name or specification; its identity goes to C and its explicit dimensions/material to D. It receives A/B only through a separate explicit relationship to another identified panel. In flat numbering, a sibling enclosure line is not the panel of the lines after it.

**P2 Protocol/interface designations** attached directly to a device noun (for example a bus or port standard before or after the noun): no versioned policy yet decides between C (as part of the lexical name) and D. Place the token in exactly one of C or D, record its protocol role in the proof, and never discard it. Evaluation of this class must declare both placements prospectively.

## Naming and representation

Explicit name/spec columns are strong structural evidence, not a prohibition against recovering a name from a mislabelled/combined specification column when the complete item proves the role. Record the actual source cells and why allocation differs from their headings. Never invent a noun to fill C.

Apply the full naming policy and source-language default. Preserve generic source prefixes under this candidate's explicit policy. Preserve both general and specific product nouns unless a separately versioned policy relocates the general category into ancillary context without losing the specific name. No automatic historical-name aliases are approved.

For this cell-based candidate, raw multi-cell descriptions/remarks join proven continuation cells with literal newlines. Derived C/D/J replace actual newlines/continuation boundaries as R37 states; retain meaningful internal spaces and stored Unicode spelling. When D is assembled from source spans that are not contiguous in the source, join them in source order with U+FF1B only (rule R4 below). Trim leading and trailing whitespace at every C, D and J edge (R38). A separable boundary delimiter left at a new C/D edge is dropped (R4), and the transformation says so; meaningful signs, ranges and identifier characters remain. Separable wrapping parentheses that enclose a whole moved span (R14) stay in raw evidence, while the underlying qualifier remains in D. Parentheses integral to the technical expression are retained. The allocation rules below require independent semantic review before admission; see the 046d review record.

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

**R7 Acronym beside a full name.** When the source gives a full name and, at a separate delimited position, an acronym, abbreviation or type designation, keep the full name in C and leave the acronym where its position puts it (D when it sits in a delimited attribute list). Put an acronym in C only when the source writes it as part of the name with no delimiter, or when it is the only name. A bracketed acronym directly after the full name (自動切換開關(ATS)) stays in C with its brackets (R47, owner decision O8). Never expand or translate either form.

**R8 Undecided classes.** When a token belongs to a class whose C/D placement the policy declares undecided (the classes listed at the end of this rule), the proof of the field that holds it must name the token's class (for example "protocol/interface designation; placement undecided"), and the null reason or proof of the other field must say the token was placed elsewhere. A token is in the protocol/interface class when it names a communication protocol, bus, port, network standard or transmission medium attached to a device noun, whether written before or after it, fused to it, abbreviated or transliterated. A medium word is in the class only when it qualifies a signal device; when it names the cable kind supplied (光纖電纜, 網路線), R2 governs. As in P2, the class covers attached tokens only; a delimited token is an ordinary D attribute. An undecided-class token kept in C keeps its source characters, including wrapping delimiters (電錶箱安裝（新設1只）); one moved to D follows R4 (新設1只); the other field never repeats it. The undecided classes are: protocol/interface designation, scope count (R3) and quantity-basis count (R3). The acronym gloss is decided (R47).

**R9 Truthful null reasons.** A null reason must be true of the item's whole logical scope (all its cells, its group heading and applied project-level text), naming any candidate text of that field's kind — including unresolved-role tokens — and where it was kept. Never state that the source has no such content.

**R10 Total discrepancies.** When a cached subtotal or total disagrees with the amounts it appears to sum, or its label leaves unclear whether it is a local subtotal or an overall total, record the observation and the ambiguity in limitations with the cells involved; judge discrepancies on canonical decimal values. Do not repair, do not recompute into any output field, and do not read a zero cache as a confirmed zero total.

**R11 Nonitem roles.** financial_summary: subtotal, total, tax, discount, management or insurance allocation and amount-in-words cells, plus the labels and qualifiers attached to those figures (such as tax-inclusion words beside a total). commercial_note: payment, delivery, validity, warranty, scope-option, supply, estimate or price-inclusion statements (以上單價含運費) that are not an item's own cell. document_reference: pointers to documents not in the packet. unresolved: two or more roles remain possible (name them) or no listed role fits (say why).

**R12 Precedence.** When rules send the same text to different destinations, the first applicable rule in this order governs: R11, R6, R5, R1 (financial annotation), R8, R3, R1b, R7, R2. Cite every matching rule in the proof. Never create a new undecided class during generation; record residual doubt in limitations.

**R13 Evaluator consistency gate (evaluator-side).** Evaluators may expect only conventions that follow from a sentence of this package, or that are covered by complete alternatives or exclusions declared before generation. Readers need not apply R13; it explains why R24 doubts are not scored.

## Clarifications R14–R24 (046c, declared 2026-11-03 before any 046c generation)

These answer generic questions raised during independent source-expectation authoring under the R13 consistency gate. They cite no contract and follow from R1–R12 and the published examples (N03, N08, N20, A13, A23). Where a clarification and R1–R12 disagree, R1–R12 govern. In the R12 order, R19, R20 and R23 rank with R5, and R16 ranks after R2.

**R14 Delimiters inside a moved span.** A moved span is the maximal run of consecutive characters in one stream that all go to D. R4 removes wrapping delimiters only when they enclose that whole run; delimiters inside it stay verbatim (A13, A25). R1b qualifiers are always separate spans.

**R15 Composing C.** Within C a bracket pair is kept or removed as a whole: removed when none of its content stays in C; kept otherwise. Two retained name spans keep the source delimiter between them; if none remains, they are joined with nothing (電纜｛45度｝彎頭 → C 電纜彎頭, D 45度).

**R16 Unidentified code tokens.** An unlabelled token of letters with digits that no other rule classifies — not a measurable value or grade code (R2), size or dimension designation (W100, DN250), attribute designation (IP65), protocol/interface designation (R8) or document number (R5) — is not part of C or D (e.g. QX-620 before a clear noun). Keep it in raw text and a review reason with its role unresolved (N03, N08, N20). A labelled code follows its label (型號 → I). A lexical name or acronym without digits (PLC-CPU模組, NFB) is a name, not a code token.

**R17 Fused measurable values.** A measurable value (R2) fused to a noun moves to D even without a delimiter (45度彎頭 → C 彎頭, D 45度; 100KW發電機 → C 發電機, D 100KW).

**R18 Condition words that name the object.** A condition word that says what the object is (廢料, 廢水, 污泥, 舊品 when it names the material handled by a service) is part of the object noun in C. R3 status words are new/existing/reused words saying which objects the work covers (新設, 既設, 利用舊品). A word naming the kind of work or the material handled (臨時用電, 廢料清運) is part of C.

**R19 Procedural clauses.** An instruction, coordination or approval clause (依監造指示, 配合現場, 經核可後) is treated like a document reference (R5): raw text and a review reason only; never C or D.

**R20 Conformity verbs.** 符合…, 合於…, conforming to … are document-reference verbs under R5. If the object of the verb is an attribute designation (符合IP65), place only that value in D (R5).

**R21 Analysis basis cells.** For a supported component link, `basis_raw_ref` is the component row's own quantity cell and `basis_unit_ref` is the component row's own unit cell. A block-header unit label is context for the link proof, not the basis unit.

**R22 Single-cell raw roles on multi-row items.** The unit, quantity, unit-price and amount raw cells are the item's single cells in those columns: the anchor-row cell. If that cell is empty, use the one continuation-row cell of the same item that has content there. When both rows have content in a column, the anchor-row cell is raw; the other is classified by its own role, or as unresolved naming the possible roles, and stays in the census.

**R23 Cost-line codes.** A pricing, resource or work-item code (工料編碼, 資源代碼, 工項編號) identifies a cost line, not a technical attribute: keep it in raw text; never C or D.

**R24 Remaining doubt.** Any C/D question these rules still leave open is recorded in limitations with the cells involved (R12). Evaluators exclude it from C/D correctness obligations unless complete alternatives were declared before generation; the next policy version decides it.


## Decisions R25–R44 (046d, declared before any 046d generation)

R25 corrects the analysis-component example found misleading in a 046c trial. R26–R38 decide the questions that independent source-expectation authors raised under 046c (policy backlog Q1–Q13); R39–R44 address generic error classes and disagreements observed in 046c development batch 1. They are generic and cite no contract; the examples are invented. They were revised after the independent semantic review of 046d. R25–R44 left the R8 classes unchanged; R47 later decided the acronym gloss. **Precedence:** R25–R44 govern R1–R24 and the older sentences above where they disagree. In the R12 order, R27 and R29 rank with R11; R35 with R5; R28 and R36 with R1 (financial annotation); R32 with R8; R31 with R7; R30 and R34 with R2; R39 and R40 with R1 (financial annotation); R41 with R1 (financial annotation), so it precedes R8, R3 and R1b; R42 with R5. R25, R26, R33, R37, R38, R43 and R44 are outside the order: they say how to compose or scope a result, not where a token goes.

**R25 Analysis component rows.** An `analysis_component` item carries its own row's literal unit in E and its own literal per-unit quantity in F: the same cells as its link's `basis_unit_ref` and `basis_raw_ref` (R21). F is the literal cell value even when the block's base exceeds one unit (每100M); never multiply or divide it, and never copy the parent's unit or quantity. Project-level values that apply to every item of the order (K, L, M, N, O, each only with the support the field table and R6 require) apply to component rows exactly as to demand rows. P stays null unless the component row itself states a required quantity; G and H stay null; Q stays null, because an analysis price is not an accepted contract rate. A component never carries A or B: they stay null with the reason "analysis component; A/B belong to 未填 rows (R25)". An analysis-block heading that names a panel is analysis context, not an R33 group. Example: a 單價分析 row 組立工資 | 工 | 2 under a heading that links it to a 式 item gives C 組立工資, E 工, F 2, and the same L as the demand rows.

**R26 One separator after a middle removal.** A separator is the whole run of delimiter and whitespace characters between two spans. When text removed from the middle of C leaves two or more separators between two retained spans, C keeps exactly one: the run that directly followed the left retained span (產品甲，100V，端子台 with 100V to D → C 產品甲，端子台).

**R27 Priced lines without an item number.** A line with its own unit, quantity or amount is a demand item, even without an item number, when it names an activity on the project's objects (設計, 製圖, 組立, 配線, 安裝, 測試, 試運轉, 搬運, 拆除) or a fee for one (運費, 安裝費), even when it adds a management word (試運轉及管理費 | 式 | 1 → demand, C 試運轉及管理費). A line that names only overhead or levies (管理, 品管, 安全衛生, 保險, 利潤, 稅, 雜費), or that states its amount as a percentage of other amounts, is financial_summary even with 式 | 1; a review reason then names any activity word in it.

**R28 Purpose and application phrases.** A phrase that only says what the object is for or where it is used (供加藥機使用, 機房用, 於二樓) is not a technical attribute: keep it in raw text, never in D, and name it in the D null reason when D is null (R9). Written as part of the product name with no delimiter (加藥機用泵浦), it stays in C (R2). A delimited 用-phrase that names an environment or protection condition (屋外用, 防爆場所用) is a type attribute under R30, like 戶外型.

**R29 Formula caches outside an item's own cells.** A formula cache on an item's continuation row, in its unit-price or amount column, is the item's raw cell and `demand_content` (or `analysis_content`) only when R22 selects it, that is, when the anchor-row cell in that column is empty. Otherwise, zero or not, it is `unresolved` with the reason "formula cache on a continuation row; the anchor-row cell is the item's raw <column> (R22)". A formula cache on a row that carries no item and no label is `unresolved` with the reason "formula cache on a row without an item; no listed role fits". A cache in a subtotal or total row is financial_summary.

**R30 Delimited kind or type words.** A delimited word that classifies the preceding product and cannot name an object by itself is a type attribute (D): words ending in 式, 型 or 形 (沉水式, 蝶型, 防爆型), spare words (備用, 預備), and delimited stage, gang or circuit counts (選擇開關，三段式). A delimited noun that can name an object stays in C with the preceding noun unless R3 makes it an included accessory, whether it is a more specific name for the same product (照明燈具，LED燈具) or a co-equal part (產品，端子台). Written with no delimiter, R2 governs (三段式選擇開關 stays in C).

**R31 Bracketed Latin tokens directly after a name.** This rule covers only a bracketed token of Latin letters, optionally with digits, hyphens, dots or slashes, written directly after a name; bracketed CJK text follows R1b, R2, R3, R28 or R30. Such a token is, in this order: a protocol/interface designation (R8; a bracket directly after the noun counts as attached for class membership only), a document number (R5), a measurable value, size or attribute designation (D, R2/R17/R34), an acronym gloss when it has no digit (R7, R47: it stays in C with its brackets), otherwise an unidentified code token (R16: raw text and a review reason).

**R32 Undecided-class tokens moved to D.** Wrapping brackets that enclose exactly an undecided-class token are always removed when it moves to D, so it forms its own span joined by U+FF1B (電力監視器(RS485) 220V with the protocol token placed in D → D RS485；220V). Otherwise it joins the maximal moved run (R14; A41). R1b qualifiers remain separate spans.

**R33 Panel names in section headings.** A section heading establishes a contractual panel group when its whole noun phrase, after the section number, names one panel designation: a panel noun, optionally with one tag, that panel's own specification, a count of identical enclosures, and one work word on that panel (工程, 製作, 更新) (三、控制盤; 一、動力盤P-1 2面). The group name is that noun phrase with its tag, without the section number, count or work word; B is the heading's own specification, otherwise null. A heading that names two or more panels, a panel with other objects or work (控制盤及配線工程), or a work category, location or system (機房設備工程) establishes no group: items under it keep A and B null, and the A null reason names the heading. Scope runs from the heading to the first of: the next heading of the same or higher level, a subtotal or total row, or the end of the table; when qualifying headings nest, the innermost governs. Every demand item in scope takes the group, including work on that panel (組立, 配線); the exception is a line supplying that panel or its enclosure itself, which leaves A and B null and cites P1.

**R34 Size designations and counts are measurable values.** A size designation is a dimension letter or symbol with a number (W100, DN250, φ50, #14), a number with a length unit or inch mark (2", 2B, 100mm), or a dimension product (100×60); a bare number is not one. Core or pair counts (芯, C, 對) are measurable values too. Fused or delimited, all of these go to D (R2, R17). An unlabelled bare number that no rule classifies is an R16 token (raw text and a review reason).

**R35 Standard numbers fused to a service name.** When a document or standard number is written directly before a service or test name, with or without whitespace (CNS1234耐壓試驗), the number is a document reference (R5: raw text and a review reason) and the service name alone is C (耐壓試驗). A body name without a number (IEC耐壓試驗, 台電檢驗) stays in C.

**R36 Mixed inclusion clauses.** In an inclusion or exclusion clause, words naming specific objects or work (底座, 安裝) are D attributes (R1). Cost words are financial annotations: words ending in 費 or 資, 費用, 稅, 人工, and a bare 材料, 料 or 工料 used as a cost category (含材料及工資, 連工帶料). Remove each cost word with the conjunction or separator that links it (及, 與, 和, 、); the inclusion word and the remaining objects form one D span joined with nothing (含工資及底座 → D 含底座; 含底座及工資 → D 含底座). The cost words go to raw text and a review reason. A clause left with no object is a financial annotation as a whole.

**R37 Continuation boundaries.** A newline or continuation boundary inside a span, together with any whitespace beside it, becomes one U+0020, or nothing when both neighbouring characters are CJK ideographs or full-width punctuation (附端子⏎蓋 → 附端子蓋; AC110V⏎附端子蓋 → AC110V 附端子蓋, where ⏎ marks the boundary). Do not judge word breaks otherwise.

**R38 Edges and verbatim copying.** Remove leading and trailing whitespace (U+0020, U+3000, TAB) at every C, D and J edge and record it in the transformation. Copy every other character that no rule moves, removes or replaces exactly, including internal spaces and an unpaired bracket at an edge.

**R39 Remarks about the item itself.** A remark that only excludes, cancels, suspends or marks the item as unused without naming an object or work (不含, 不使用, 免, 取消, 暫停) is not a technical attribute: keep it in raw text with a review reason. It never deletes the row, never changes F and never enters D; the item keeps status `research_draft` unless another rule holds it, and the D null reason names the remark (R9). A generic verb that refers to the item itself (施作, 設置, 使用, 採購) is not a named work (本項暫不施作 → R39). A remark that excludes a named object or work (不含底座, 不含安裝) follows R1 and R36.

**R40 Change remarks.** A remark that changes the item's method, material or type (改用不鏽鋼, 改為埋設) states a technical attribute: the change phrase as written goes to D. A justification or condition in the same remark (因現場…, 配合…, 依…) stays in raw text with a review reason (R19). A change does not delete the attribute it supersedes; each stays where its own rule puts it (電纜管，鍍鋅 + remark 改用不鏽鋼 → D 鍍鋅；改用不鏽鋼). A change that replaces the supplied object itself (改為接線盒) keeps C from the description, puts the change phrase in D and adds a review reason. A change of location or purpose follows R28.

**R41 Words inside inclusion clauses.** A status or count word inside an inclusion or exclusion clause (含新設線路2處) belongs to that clause. The clause as a whole follows R1 and R36; the word is not a separate R3 scope-count token, and R8 class naming does not apply. The proof cites R1 and names the word. This is a rule about class membership (such words are not R3 scope-count tokens), not a decision on the placement of any R8 class.

**R42 Holding for unavailable documents.** Hold an item (status `held`, values kept, the hold explained) when either: (a) after removing the document pointer and generic work verbs (施作, 施工, 辦理, 製作), no object or specific work noun remains (詳設計圖 | 式 | 1; 依規範施作 | 式 | 1); or (b) the pointer is to a missing detail schedule, list or quantity table (明細表, 附表, 清單, 數量表) (R5 last sentence; guideline §1). Otherwise, even with unit 式, do not hold an item whose own text names an object or specific work (配線工程 依圖施作 | 式 | 1; 電纜 3.5mm² 依圖施作): record the pointer under R5, and for a 式 item add a review reason that its extent is defined by the missing document.

**R43 Brackets at the start or middle of a moved run.** R4 removes wrapping delimiters only when they enclose a whole moved span. A bracket pair at the start or in the middle of a longer contiguous moved run is inside it and stays verbatim (R14): 電磁接觸器 (防塵型) AC220V → D (防塵型) AC220V. The only exceptions are R1b qualifiers, which are always removed with their wrapping delimiters as a separate span (A01), and R32: brackets that enclose exactly an undecided-class token.

**R44 Naming source columns in reasons.** Proofs and null reasons name a source column by its header text (quoted or translated) or its address, never by a document role the source does not state (R9).

## Owner decisions R45–R47 (046e, declared before any 046e generation)

These apply owner decisions O6–O8 of 2026-11-03 (`research/guideline046_005/DECISIONS_OWNER_O5_O9.md`). R45 and R46 apply after guideline §3, R11, R27 and R29 have identified demand lines, nonitem rows and analysis blocks, and before every allocation rule. They never make a nonitem row an item. R47 ranks with R7.

**R45 Which demand lines are 未填 rows (O7).** R45 sorts only the demand lines of the detail table.
- **Quoted price.** The line's unit-price or amount cell (R22) holds a number above zero (literal or cached) or text stating a positive amount (1,200元), or one of the line's own cells says its price is included in another priced item (含於第3項, 併…計價).
- **No quoted price.** Both cells are empty or zero (number or text 0), or hold only 不計價, 業主供料, 不含估價 or 另案.
- **Inside a panel.** The line is in an R33 scope; it is a numbered descendant of a panel line (1 控制盤 → 1.1); its own cells state that it is in or for a panel of this contract (盤內, 裝於控制盤); or it supplies a panel or enclosure itself (P1). A flat-numbered sibling after a panel line is not inside it.
- **Rows.** A line with a quoted price, or inside a panel, is a demand item. Never exclude a line inside a panel for lack of a price.
- **Kept, never excluded.** The following stay demand items even without a quoted price, each with a review reason and a limitation:
  - a line that R42 holds (hold it and cite R45);
  - an R45 doubt: other price content (另計, 詳單價分析, 免費, a lone dash, a negative number, an error or a missing cache); a line whose price may be carried by a priced parent line or by an analysis block of this source; a line under a heading that names a panel but forms no R33 group; a panel line whose own price text says 業主供料 or 另案, and the lines inside it; or every line of a contract that has no line prices.

  An R45 doubt is not an R24 C/D doubt; evaluators declare before generation whether it counts (R13).
- **Excluded.** Any other line with no quoted price that is not inside a panel (no enclosure and no estimate, CRQA-11) is not a 未填 row. Classify every one of its cells, including its item number and continuation rows, as `excluded_supply`; this overrides R29 for formula caches on those rows. The reason begins "no enclosure and no estimate: not in the quoted supply (R45)" and names the condition: price cells empty, zero, or the quoted text. Write no item for it, and cite none of its cells in any item.

Examples:
- 電力監視器 RS485 | 台 | 1, price cells empty, outside any panel → `excluded_supply`.
- 無熔絲開關 3P50A | 只 | 2, price cells empty, in the scope of 三、控制盤 → demand item with A 控制盤.
- 流量計 | 台 | 1 | 業主供料, outside any panel → `excluded_supply`, with the reason naming 業主供料.

**R46 Analysis blocks without a parent demand item (O6).** A block runs from its heading to the next block heading or the end of the sheet; page and column headers and footers inside it keep their own roles.
- **No parent.** The block's referenced item is absent when no demand item of this response shares its reference code or item name; a reference to another block's component counts as absent. Classify every other cell of such a block, including its heading, as `analysis_unlinked` with the reason "analysis block for an item not among this draft's demand items (R46)". Write no component items or links for it, and cite none of its cells in any item.
- **One match.** R21 and R25 apply, with a held link unless unit and basis prove it.
- **Two or more matches.** The link is held.

**R47 Acronym glosses (O8).** A bracketed acronym or abbreviation without digits, written directly after the full name that it abbreviates (無熔絲開關(NFB); 自動切換開關(ATS) 3P160A → C 自動切換開關(ATS), D 3P160A), stays in C with its brackets. It is no longer an undecided class. A letter-only bracketed token stating a material, light source or current type (電纜(PVC), 燈具(LED)) is an R31 attribute designation (D).

## Creator practice and owner decisions R48–R58 (046f, declared before any 046f generation)

These rules implement owner decisions O10–O16 (`research/guideline046_005/DECISIONS_OWNER_O10_O12.md`, `DECISIONS_OWNER_O13_O16.md`) and the historical 未填 creator's majority practice (`STUDY_CREATOR_PRACTICE_20261104.md`, `STUDY_SUPPLY_MARKERS_20261104.md`). They govern every earlier sentence, rule (R1–R47), P1/P2, NAMING_RULES and example where they disagree. Earlier text stays in force for source reading, raw and provenance mechanics, census roles (R11, R29, R45, R46), holds (R42), document references (R5: never in C or D), cost-line codes (R23) and anything these rules do not address. In particular R1–R4, R7, R14–R17, R26, R30–R32, R34–R38, R43, R47 (reversed by O20) and NAMING_RULES no longer decide C/D; P1, R33 and the group mechanism no longer decide A/B; R6 and the field-table K/M/N wording are replaced by R48; the Q adoption hold is replaced by R54; R45's row tests are replaced by R49–R51.

**R47b Sources (O17).** A job has up to two source packets: the company material list (材料清單, primary when present) and the contract. Rows, descriptions, units, quantities, prices, brands, models and status come from the 材料清單 when the packet has one, and from the contract otherwise. The contract then serves only to resolve doubts the 材料清單 leaves (for example a missing dimension). The brand table (R55) is used only when neither source states a brand or model.

**R48 Job inputs (O13).** The inventory carries three job-input context facts: `context:case_identity` (internal case id), `context:customer_name` (customer full name) and `context:project_name` (project short name). Every 未填 row carries L, M and N copied exactly from them, citing the context ref. K, O and P stay null. Never infer M or N from a letterhead (R6 still holds for inference).

**R49 Quoted range.** Rows come from the detailed bill sheet that carries the sender's prices; summary sheets never yield rows. The quoted range runs from the first item line under the column header down to the row whose unit-price or amount column holds 合計 or 總計 (a 合計 written in the description column is a block total, not the end). Repeated site sections and goods/labour subsections inside the range are all in it. Everything after the end row (the signature line, notes, later sections, later analysis blocks) is out of range. When several total rows follow one another (合計, then tax, then 總計), the first one ends the range. When no total row exists, the range ends at the last item line before the signature line or the end of the sheet. When every bill line is unpriced, rows come from the analysis sheet instead (R51).

**R50 Which lines are rows.** Inside the quoted range, in source order, each of these lines gives exactly one row:
- a priced line (its unit-price or amount cell holds a number above zero, or text stating a positive amount such as 1,200元);
- a not-estimated line (its amount cell holds the literal 不含估價);
- the sender's unnumbered fee lines before the end row (freight, drawing, design or management fee).

Not rows: a zero-state line (a cached 0 or empty amount with no unit price and no status) and any other line with no price and no status (`excluded_supply`, reason per R45); block totals, subtotals, the end row, tax and negotiation lines (R11); headings; item-like lines out of range (`excluded_supply` with the reason "outside the quoted range (R49)"). A remark saying a line is not included or not used does not remove it. Never split or merge lines, never add rows. Supply and separate-contract markers (業主供料, 甲供, 業主自備, 業主自理, 另案, 另案發包, supplied by others) do not decide inclusion and are never copied into a field. Provisionally (O10): a panel line marked owner-supplied is omitted together with its contents only when no line inside it has a price inside the quoted range.

**R51 Analysis components as rows.** When a bill line inside the quoted range has no price and no status and has its own analysis block (on the same or an analysis sheet), or when every bill line is unpriced, that block's components are the rows instead of the parent line: block by block, in analysis order, written as `demand` items. The parent line is not a row (its cells take the census role `section` with the reason "parent of analysis components listed as rows (R51)"), and the block's own 合計/計 rows are not rows. Component rows follow R52–R57 like bill lines: E and F are the component's own unit and quantity, Q its unit price, and I = J = 不含估價 when the component is not estimated. When the parent line is priced or not estimated, its components are never rows; they stay `analysis_component` items (R21, R25) or `analysis_unlinked` cells (R46).

**R52 C and D (O15, O20).** First drop the generic leading prefix word named in the glossary resource and its delimiter. Then drop the leading category chain: the delimited segments before the item's own noun that only name a product category, such as segments ending in 類 or the category words the glossary lists. The chain is dropped on every line type.
- **Equipment line** (the head noun names a discrete, individually specified device: switches, breakers, contactors, relays, timers, meters, instruments, pumps, motors, fans, lamps, sockets, transformers, starters). C = the glossary abbreviation for that device when the glossary lists one. Otherwise, when the source writes a Latin acronym fused to or in brackets after the noun, C = the acronym alone (自動切換開關(ATS) → C ATS). Otherwise C = the head noun: the item's first segment, cut before the first digit or bracket. D = the rest of the description after removing the prefix, the chain and C's segment (or its leading noun part), verbatim except R53.
- **Every other line** (cable and wire, conduit, pipe and fittings, size-first valves, hardware, busbar, sundries, PLC modules and software, services, labour and fees, descriptions starting with a digit, and nouns that are not clearly equipment): C null; D = the description without the prefix and the chain, verbatim except R53.
- **Single-segment description:** C null and D = the text, unless the glossary lists the noun, in which case C = its abbreviation and D null.
- Remarks, code columns and price text never enter C or D; they stay in raw text. Continuation rows are joined to the description with no separator.

Invented examples:
- 產品，控制開關類，選擇開關，30mm → C = the glossary abbreviation for 選擇開關 (or 選擇開關), D = 30mm.
- 產品，電線電纜類，600V XLPE電纜，3C，2mm² → C null, D = 600V XLPE電纜，3C 2mm² (only the comma between the two rating tokens becomes a space, R53).

**R53 Rating tokens.** Wherever a comma or other list delimiter sits between two rating-like tokens (pole counts, currents, voltages, frame or breaking ratings, sizes), D writes a single space instead and drops the wrapping brackets around those tokens: 2P，20AT，(AC，Ics) → 2P 20AT AC Ics; φ30mm，2a2b → φ30mm 2a2b. Other punctuation in D is kept verbatim.

**R54 Q (O16).** On a priced line, Q is the line's unit price as a number, cited from its unit-price cell, never the amount. Q does not wait for adoption to be verified; the route accepts it under O16. Q is null on not-estimated and zero-state lines.

**R55 I and J (O14, O16).** On a not-estimated line, I = J = 不含估價, citing the amount cell. On a priced equipment line, a brand or model stated in the line's own cells is copied; otherwise apply the company brand table resource by device type and rating band, citing the description cell and `context:brand_table`. A device or rating the table does not cover leaves I and J null with a reason. Material, service, fee and zero-state lines leave I and J null.

**R56 Enclosure row (O16).** A priced line that supplies an enclosure itself (panel box, control box, meter box) is one row in source order. A = the enclosure noun from the line, or from its section heading when the line names only a generic box. B = `<w>W*<h>H*<d>D` built from dimensions stated in the contract (mm), else null. C = the generic enclosure word named in the glossary resource. D = the remaining material, finish or type text (the description minus the prefix, the category word, the enclosure noun and the dimensions). E and F verbatim; Q = unit price; I null; J = the company name from the company resource (`context:company_name`). The enclosure row is carried by a one-row group (relationship `physical_enclosure`) whose name and specification equal A and B, because the interface requires a group for A/B. No other row carries A or B, and no other groups are formed. When the 材料清單 states the enclosure's brand column, J = that value; otherwise J = the company name.

**R57 E, F, G, H.** E and F are copied verbatim from the line's own unit and quantity cells, even when they look implausible. F must be a number; a quantity written as text with a unit (2台) leaves F null with a reason. G and H stay null. C may be null on any row R52 makes C-null; the route accepts such rows as `research_draft`, not held (046f relaxation).

**R58 Resources and citations.** The company glossary, brand table and company name are owner-reviewed private resources supplied with each packet as context facts (`context:glossary`, `context:brand_table`, `context:company_name`). A field derived through them cites the source cell it was derived from together with the context ref; L, M and N cite only their job-input context refs.


## Commercial and quantity distinctions

Keep supplied-by-customer, self-transport, no-estimate, original quantity and responsibility separate. Search all financial/remark cells for these clauses. A missing price alone does not prove nonresponsibility; the no-enclosure AND no-estimate condition must be established completely. A real zero remains zero. Unknown, explicit empty string and error are not interchangeable facts.

Retain services and costs that are actual source demands. Taxes, whole-project negotiation, management allocation and totals have financial/context roles, not additional supplies merely because a unit or number is present. Do not borrow an 已填-stage deletion convention.

For composition or bundled wording, preserve the count's referent without changing F or creating extra purchases. For analysis, record literal per-unit basis and source quantities separately; no multiplication/division without independently supported scope and an admitted policy.
