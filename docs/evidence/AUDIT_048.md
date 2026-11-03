# CPS full programme audit 048 (brought forward after the 1140908 regression)

- Date: 2026-11-03 (Asia/Taipei). Auditor: independent Claude Code subagent (observed model `claude-opus-5-5`). The auditor built none of the 046a/046b work.
- Role: programme auditor with evaluator-role read access. Baseline: public repository commit `ad86058` plus the private 046b results ZIP (`CPS_046b_results_20261103_PRIVATE.zip`, sha256 `d6dad4f7…df74`, 258/258 manifest entries verified) and the extracted portable handoff bundle (bundle-relative names below).
- Not opened: `private/naming_study/`, `docs/handoff/NAMING_STUDY.md`, `research/naming_study/`, any `private/projects/*/evaluation_only/` worksheet, any reserved-project material, the web. No repository file was modified.
- This document is public-safe. It contains aggregate numbers, generic error classes and generic rule proposals only. Row-level detail is in the separate private appendix, which must never enter a generator context.

## Verdict in brief

1. **Process (046b):** outputs were frozen before evaluation, there were no retries or repairs, one prompt per generator, the observed model was recorded, and all reported scores reproduce from the saved comparisons. There are four material deviations: (a) the generic field-role text never received the independent semantic review that PLAN71 and the package's own text require; (b) a pinned harness file changed after admission; (c) two 1141208 policy declarations came from that case's expectation author; (d) the PLAN71 timing and sequencing controls were silently dropped. There are also smaller disclosure gaps. None of these changes a frozen score.
2. **Regression (1140908):** the drop is explained almost entirely by 046b's generator-facing C/D text, which diverged from conventions that the frozen 043 expectations apply and that the 045 protocol had stated. Package-text changes account for A −12 and B −2 of the core change (A −14, B −7). Behaviour changes under unchanged or ambiguous text account for A −2 and B −5. Of the 046b core misses, 34/35 (A) and 32/36 (B) fall on such policy/expectation seams; only 1 (A) breaks an explicit 046b rule. The frozen 1140908 expectations are consistent with P1, and P2 has no occurrence in them. Several of them conflict with, or cannot be derived from, other 046b sentences.
3. **Generic gaps:** 12 numbered generator-facing rules (R1–R12, with placement options R1b) and 1 process rule (R13) are proposed for 046c (section 3). Four of them carry a tuning-risk flag: R1b, R3, R7 and R8.
4. **Evaluator:** `compare_source043/046` is a detail-only, column-B-anchored comparator. `compare_source040` scores components only through hard-coded case layout constants. A component-capable evaluator needs the declared, expectation-driven features listed in section 4.
5. **Deployment:** this session has 1 eligible pair (exposed, PDF source, which the 046b route cannot read), 0 reserved and 0 performance-passed. Every saved-workbook, visual and repeatability gate needs an export runtime that only the owner can supply. The bar is far from met.

---

## 0. The audit definition applied

PLAN71 (bundle `private/refinement/PLAN_v71.md`, "Audit cadence") and `docs/handoff/RESUME_PLAN.md` define the full programme audit. It runs at 048, or earlier after a critical finding or regression. It must assess:

- whether real source and layout breadth and the eligible pairs are increasing;
- whether framework preparation has a concrete exit;
- whether deterministic capture is being confused with semantic accuracy;
- that every failed attempt and the best/last scores are preserved separately;
- that no mixed-configuration history is combined into a reliability rate.

The trigger here is the 1140908 canonical-core regression (RESULTS_046B). This audit also covers the six questions set by the requester. Section 7 records the determinations against the PLAN71 criteria.

## 1. Process compliance of the 046b cycle

### 1.1 Controls that passed (with records)

| Control | Result | Record |
|---|---|---|
| Admission frozen before generation | PASS. The admission was frozen at 07:03:29Z, run input pins were prepared at 07:03:35Z, and the first generator started at 07:03:48Z. | `research/guideline046_002/records/ADMISSION_046b.json` (sha `db84dce9…`); results ZIP `gen/*/RUN_INPUT_PINS.json`, `STARTED_UTC.txt` |
| Admission pins match the bytes used | 23/24 match. The one mismatch is finding P-2. | Recomputed by the auditor |
| Generator inputs | Package (16 files) plus case packet only. Expectations, history and prior outputs were excluded. | `gen/*/RUN_INPUT_PINS.json` |
| One prompt per generator, no follow-up | PASS. 1 human-role prompt per run. The other user-role entries are system meta (hand-back reminder, image metadata). | `transcripts/gen_*.jsonl` (auditor recount) |
| Observed model recorded | PASS. `claude-opus-5-5` on 157/157 assistant messages (40, 36, 41, 40). Requested: inherit. Effort: not set. | `gen/*/TRANSCRIPT_AUDIT.json`; METRICS_046B.json |
| No retries, no repair of scored outputs | PASS. 4 invocations, 4 `RESPONSE_RETURNED`, 0 not carried, repair and retry flags false. In-run self-checking with the package checker is part of the product route, not a retry. | `gen/*/frozen/FREEZE.json` |
| Freeze before evaluation | PASS. Responses were frozen at 07:14:00Z (1140908) and 07:19:19–41Z (1141208). Carriers were frozen and released at 07:14:12Z and 07:19:51Z. The evaluator contexts began at 07:15:06Z and 07:20:04Z. | `gen/release_*/`, `transcripts/eval_*.jsonl` |
| Writer validation (structure) | PASS on 4/4. | `gen/*/adapter/WRITER_VALIDATION.json` |
| Comparator bound and unchanged | PASS. Wrapper `9d1f5ee9…` imports the frozen 043 code `1ececf30…`. Outputs are created exclusively, once per run. | `eval/*/COMPARISON_*.json` bindings |
| Reported numbers | Reproduced exactly from the four comparison files (all core, supported, all-position, row, raw, census, incident and gate figures). | Auditor recomputation |
| Isolation | Instruction-based, audited after the run. An independent re-audit that tracks the working directory and relative paths found 0 reads outside the run directories in all 4 transcripts. | Auditor script over `transcripts/gen_*.jsonl` |
| Exposure handling | The 1140908 pair is recorded as used, with no repeat planned. No reserved material was used. The 045 records were not rescored. | CURRENT_STATE.json, RESUME_047.md |

### 1.2 Deviations and disclosure gaps

| ID | Severity | Finding | Record |
|---|---|---|---|
| P-1 | **High** | **The field-role semantics were never independently reviewed.** PLAN71 §046 requires an independent review of the generic field-role specification (C/D boundaries, document references, commercial versus specification text) before model admission. Both reviews were interface/mechanics reviews and say they are "not semantic approval". The reviewer's prompt scoped it as a "code-and-interface reviewer". The frozen `FIELD_ROLES.md` itself says the boundary distinction "needs independent review before original-source trials". The admission went ahead anyway. The main regression classes sit in exactly this unreviewed text: compared with the 045 protocol, one clause was dropped and one exclusion was added (section 2). RESULTS_046B reports "APPROVE_FOR_BOUNDED_SOURCE_TRIAL" without saying the approval was interface-only. | REVIEW_046a.md, REVIEW_046b.md, `package/resources/FIELD_ROLES.md`, `transcripts/package_reviewer_046b.jsonl` |
| P-2 | Medium | **A pinned harness file changed after admission.** `harness/audit_transcript.py` was pinned at `03769d8c…`. Commit `c3403b5` (07:15:12Z), made after the 1140908 audits and before the 1141208 audits, narrowed its path regex (`fe02c1ae…`). Both 1141208 `TRANSCRIPT_AUDIT.json` files therefore come from an unpinned tool. This is not disclosed in RESULTS_046B. Impact: none on outcomes, because the auditor's stronger re-audit found no outside reads. | Admission pins; `git show c3403b5` |
| P-3 | Medium | **The 1141208 policy declarations are informed by that case.** P1 and P2 were surfaced by the 1141208 expectation author while drafting that case's expectations, then placed in the generator package before its first reading. P1 was settled in the direction the draft already took. The wording is generic and disclosed in DECISIONS_046b. RESULTS_046B only says the expectations were authored "under the same frozen policy the generators used". The 1141208 numeric pass should be labelled as aided by declarations, and by declared alternatives, that came from its own expectation work. | DECISIONS_046b.md; results ZIP `private_work/exp1141208/EXPECTATION_NOTES.md` |
| P-4 | Medium | **An evaluation-only class extension was turned into an obligation.** E3 extended the undecided P2 class to physical-medium designations for evaluation only. Obligation S05 then required role recording on rows the generator-visible text does not cover. The evaluator correctly found that S05 fails on the two protocol rows alone. RESULTS_046B's "4 rows … which FIELD_ROLES requires" overstates this: FIELD_ROLES covers 2 of the 4. Even on those 2, membership of fused or transliterated forms in the class is not defined in the generator text. | `eval/1141208/MANUAL_REVIEW.md` §3; RESULTS_046B |
| P-5 | Medium | **PLAN71 timing and sequencing controls were dropped without a declaration.** The admission has no fixed root stop and no prospective timing. A and B ran concurrently, although PLAN71 says normal A assembly precedes B. One 1140908 reader ran for 611 s wall-clock against the PLAN71 600+5 s model bound; the agentic multi-turn route is not directly comparable to that bound. Durations (611, 587, 295, 317 s) are not reported. Independence is unaffected: concurrent runs exclude feedback. | PLAN_v71 §046; `gen/*/STARTED_UTC.txt`, `ENDED_UTC.txt` |
| P-6 | Low–Medium | **The generator context was not fully pinned.** Each "fresh" generator context received the project `AGENTS.md` as injected instructions, and that file is not among the admission pins. Web, mail, drive and code-hosting connector tools were available, restricted by instruction only. The transcripts show none were used. This is a risk, not a breach. | `transcripts/gen_*.jsonl` attachments |
| P-7 | Low | **Deterministic gains are not labelled as such.** Raw 197→282 and census 51→95 on 1140908 come from the route: canonical copying, anchor-plus-census, and the checker's one-role-per-content-cell rule. PLAN71 requires such gains to be reported separately from model understanding. RESULTS_046B lists them as "clean mechanics" without saying they are deterministic. | PLAN_v71 §046; RESULTS_046B |
| P-8 | Low | The evaluator brief template was committed at 07:04:54Z, after the generators started, and is not pinned. Its content matches the admission's evaluation plan, and no output was accessed before release. | `git log` |
| P-9 | Info | At baseline, CURRENT_STATE.json says `development_allowed: false`. A new development commit (`7aef62b`, a component-capable comparator and an XLSX inventory builder, marked "not yet reviewed") appeared in the repository during this audit. The state file should be reconciled with the owner's explicit resume authority. | `git log` |

## 2. Regression analysis 045 → 046b on 1140908

### 2.1 Comparability

Both cycles were scored by the same frozen expectations (`04b5f42c…`) and the same `evaluate()` code (`1ececf30…`). The denominators are unchanged: 176 core, 223 supported, 799 positions, 47 rows. What differs:

- the generator-facing policy text (the 045 reading protocol versus the 046b package);
- the transport (compact carrier versus source-reference adapter);
- the runtime (045's proposed-runtime protocol versus 046b's observed `claude-opus-5-5` agent with tools).

No controlled run separates text from runtime, so the attribution below is inferential. Each changed behaviour was matched to an exact text difference, or to the absence of one.

### 2.2 Per-column and aggregate deltas (canonical; detail stratum equals overall)

| Measure | A 045 → 046b | Δ | B 045 → 046b | Δ |
|---|---:|---:|---:|---:|
| Core (175 needed) | 155 → 141 | −14 | 147 → 140 | −7 |
| C (material name), /47 | 46 → 31 | −15 | 46 → 30 | −16 |
| D (specification), /35 | 15 → 16 | +1 | 7 → 16 | +9 |
| E, F (unit, quantity), /47 each | 47 → 47 | 0 | 47 → 47 | 0 |
| L (selected identity; non-core), /47 | 47 → 47 | 0 | 47 → 47 | 0 |
| Supported, /223 | 202 → 188 | −14 | 194 → 187 | −7 |
| All positions, /799 | 778 → 764 | −14 | 760 → 716 | −44 |
| Whole rows, /47 | 27 → 28 | +1 | 9 → 0 | −9 |
| Unsupported populated positions | 0 → 0 | 0 | 10 → 47 | +37 (D → party-role column) |
| Raw literal, /282 *(deterministic route)* | 197 → 282 | +85 | 197 → 282 | +85 |
| Nonitem census, /95 *(deterministic route)* | 51 → 95 | +44 | 51 → 95 | +44 |
| Supported provenance locators, /223 | 223 → 211 | −12 | 223 → 212 | −11 |
| Mandatory obligations, /12 | 9 → 10 | +1 | 9 → 9 | 0 |
| Unresolved critical errors | 0 → 0 | 0 | 0 → 0 | 0 |

Core field transitions:

- A: C lost 16 and gained 1; D lost 3 and gained 4.
- B: C lost 17 and gained 1; D lost 2 and gained 11.

Obligations:

- A fixed the census/raw obligation, which is a route effect, and kept two failures.
- B fixed the census/raw obligation and the document-pointer obligation, but newly failed the total-discrepancy and party-role obligations.

### 2.3 Error-class deltas (core fields; each failed field assigned one primary class)

| # | Generic class | A 045 | A 046b | Δ A | B 045 | B 046b | Δ B |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | Supply-basis qualifier (hire/lease-type basis): wrong field or delimiters kept | 13 | 26 | −13 | 13 | 26 | −13 |
| 2 | Separable wrapping delimiters kept on other moved qualifiers | 5 | 0 | +5 | 5 | 0 | +5 |
| 3 | Financial annotation placed in D | 0 | 0 | 0 | 8 | 0 | +8 |
| 4 | Unavailable-document pointer placed in D | 1 | 1 | 0 | 1 | 0 | +1 |
| 5 | Composition count detached from its noun | 2 | 0 | +2 | 2 | 0 | +2 |
| 6 | Scope/new-quantity qualifier left in C | 0 | 2 | −2 | 0 | 2 | −2 |
| 7 | Fused material/construction prefix moved C→D | 0 | 4 | −4 | 0 | 2 | −2 |
| 8 | Acronym moved from the attribute list into C | 0 | 0 | 0 | 0 | 4 | −4 |
| 9 | Non-contiguous D clauses joined with a space instead of U+FF1B | 0 | 2 | −2 | 0 | 2 | −2 |
| | **Total core misses** | **21** | **35** | **−14** | **29** | **36** | **−7** |

Non-core:

- 045 B: 10 unsupported positions (financial annotation in D on rows where D is expected to be null).
- 046b B: 47 unsupported positions (a party-role field filled from a document header).

### 2.4 Attribution

**What changed between 045 and 046b**

| Lens | Classes | Δ A | Δ B | Basis |
|---|---|---:|---:|---|
| Package/policy text change | 1, 2, 3, 5, 6, 7 | **−12** | **−2** | Gains: new rules for wrapping delimiters, the exclusion of financial annotations from D, and composition counts (+7 A, +15 B). Losses: (i) no rule for supply-basis qualifiers, while D now excludes "financial annotations", so both readers kept the qualifier in C on all 13 affected rows, identically; (ii) the 045 clause "C retains integral material prefixes" was dropped; (iii) the new composition-count rule now covers a scope count the expectations put in D. |
| Behaviour change under unchanged or ambiguous text (runtime or reader variance) | 4, 8, 9 | **−2** | **−5** | The joiner sentence is the same in both versions, but behaviour changed uniformly. The acronym placement is ambiguous in both versions and differed in one reader. The pointer rule is explicit in both versions and was broken in 3 of 4 reader-runs across 045 and 046b. |

**Whether the expected value can be derived from the 046b text (evaluator-convention lens)**

- Classes 1, 6, 7 and 9 are misses where the frozen 043 expectations apply a convention that the 046b generator text omits, contradicts or leaves ambiguous.
- These account for 34/35 (A) and 32/36 (B) of the 046b core misses. B's remaining 4 (class 8) sit on an ambiguous rule.
- Only 1 A miss (class 4) breaks an explicit 046b rule.
- The conventions concerned are stated in the evaluator-side `private/refinement/source_expectations043_001/SOURCE_AUDIT_POLICY.md` and were largely present in the 045 reading protocol.

**Conclusion.**

- The regression is primarily a policy–expectation consistency failure introduced by unreviewed field-role text (P-1). It is not a loss of source-reading ability and not, on the available evidence, mainly a runtime effect.
- The same evidence shows that targeted generic sentences reliably change this runtime's behaviour, in both directions.
- The frozen scores stand. This attribution is diagnostic input for 046c, not a rescore.

### 2.5 Are the frozen 1140908 expectations consistent with the 046b declarations?

- **P1 (panel self-relationship): consistent.** A and B are null on 47/47 expected rows. Enclosure lines carry their identity in C and their explicit qualifiers in D.
- **P2 (protocol/interface tokens): not applicable.** No in-class token occurs in the expected C/D values, so the requirement to declare both placements is never triggered.
- **Other 046b sentences: inconsistent or not derivable on 19 of 47 rows.** No 046b output may be rescored for this.
  - 1 row: the canonical expectation and obligation require a scope/new-quantity count in D. NAMING_RULES §5 (keep counts attached to their noun) points the other way, and no alternative is declared. This is a direct conflict.
  - 13 rows: a supply-basis qualifier is expected in D as a scope clause. FIELD_ROLES D excludes "financial annotations" and defines no supply-basis role. This is a tension.
  - 3 rows: expected C keeps a fused material/construction prefix. 046b no longer states the 045 clause that required this, and it lists material under D. Not derivable.
  - 2 rows outside the above (plus overlaps): a U+FF1B join of non-contiguous spans from one cell. The 046b sentence covers "distinct description and remark clauses" only. Ambiguous.

**Consequence.** Any future use of 1140908 can only be regression evidence. If its expectations are revised, the revision must be a new, prospectively frozen version, and must never be applied to the 045 or 046b outputs. The root cause is addressed by the process rule R13 below.

## 3. Generic policy gaps and proposed rules for candidate 046c

Evidence comes from both cases' comparisons and manual reviews, in aggregate.

- **1140908:** the core classes 1–9 above; follow-on null-reason defects (A 12 rows, B 11); the total-discrepancy obligation (B); unsupported party-role positions (B 47).
- **1141208:** undecided-class role not recorded (4 class rows per reader, 2 of them covered by generator-visible text); incomplete null reasons on class rows (A 4, B 5); nonitem role-label deviations (A 2 cells); one declared-alternative placement (B, not an error).

The rule texts below are proposed verbatim for 046c. They contain no case content. **Flag** marks a proposal that risks tuning to one case.

| ID | Gap (generic) | Proposed rule text (verbatim) | Flag |
|---|---|---|---|
| R1 | No definition separating financial annotations from supply-basis qualifiers | "A financial annotation is text about price, cost inclusion, estimate status, payment, discount, tax, or who bears a cost. It never enters C or D; keep it in raw text and, when it affects scope or responsibility, in a review reason. A supply-basis qualifier states on what basis the object is provided — for example hired or leased instead of bought, temporary instead of permanent, new instead of existing, reused, or supplied by another party. A supply-basis qualifier is not a financial annotation, even when the same word can also name a fee." | — |
| R1b | Placement of supply-basis qualifiers undecided | Option A: "Remove a supply-basis qualifier from C together with its separable wrapping delimiters and place it as its own clause in D; record 'supply-basis qualifier' in the D proof." Option B (until the owner decides): "Placement of a supply-basis qualifier is undecided: keep it in exactly one of C or D, record its class in the proof of the field that holds it and in the null reason or proof of the other field. Evaluators declare both complete placements." | **Flag.** Choosing A only because it matches one exposed case's frozen expectations would be tuning. The owner should decide from drafting practice; until then use B. |
| R2 | The fused material/construction prefix rule was lost | "A material, construction or type word written directly before the product noun with no delimiter, so that the two read as one product designation, stays in C. Move a material, finish, grade or construction word to D only when the source separates it from the noun (delimiter, separate cell, label) or when it carries a measurable value (thickness, grade code, rating, size). When fusion alone leaves the role unclear, keep the word in C and say so in the proof." | This restores a generic clause from the earlier reading protocol. Low risk. |
| R3 | Composition counts and scope counts conflict | "A count that says how many sub-objects the supplied object contains or combines stays attached to the sub-object noun in C. A count or status word that limits how much work a service line covers — how many objects are installed, moved, removed or tested, or new versus existing — is a scope clause: move it, with its status word, to D and keep the work noun and its object in C. Neither kind of count changes F or P or creates extra rows." | **Flag.** Formulated after seeing one miss. It is generic, but needs invented fixtures and an independent review. If the reviewer cannot confirm the distinction reflects drafting practice, declare both placements instead. |
| R4 | The D clause joiner is under-specified | "When D is assembled from source spans that are not contiguous in the source — whether they come from different cells or from different positions in the same cell, for example a qualifier before the name and another after it — join the spans in source order with U+FF1B and nothing else. Use U+0020 only to replace a newline or continuation-cell boundary inside one continuous span. Remove separable wrapping delimiters around each moved span; keep delimiters that are part of the technical expression." | — |
| R5 | Document-reference clauses keep entering D (3 of 4 reader-runs across two versions) | "A clause whose content is only a reference to a document, standard, drawing, catalogue or specification that is not in the source packet — including 'per …', 'refer to …', 'according to …', 'built to …' — is a document reference. Keep it in raw text and in a review reason or limitation. It never enters C or D and never supplies a value. If the same clause also states an explicit technical value, place only that value in D." | — |
| R6 | Party roles inferred from document furniture | "A company, agency or person name that appears only in a letterhead, title, addressee line, page header or footer, stamp or signature block does not establish K, M or N. Fill these fields only when the source labels the role or the contract text states it; otherwise leave the field null with a reason that names where the name appears and that no role is stated. Do not copy one party into several role fields." | — |
| R7 | Acronym beside a full name | "When the source gives a full name and, at a separate delimited position, an acronym, abbreviation or type designation, keep the full name in C and leave the acronym where its position puts it (D when it sits in a delimited attribute list). Put an acronym in C only when the source writes it as part of the name with no delimiter, or when it is the only name. Never expand or translate either form." | **Flag (mild).** Derived from one reader's behaviour on 2 rows. Needs fixtures. |
| R8 | Undecided classes: role recording and class membership | "When a token belongs to a class whose C/D placement the policy declares undecided, the proof of the field that holds it must name the token's class (for example 'protocol/interface designation; placement undecided'), and the null reason or proof of the other field must say the token was placed elsewhere. A token is in the protocol/interface class when it names a communication protocol, bus, port, network standard or transmission medium, whether it is written before or after the device noun, fused to it, abbreviated or transliterated." | **Flag.** The extension to medium and to fused or transliterated forms came from one case's evaluation (E3). It must be reviewed and published to the generator before any evaluator relies on it. |
| R9 | Null reasons contradicted by allocation choices (both cases) | "A null reason must be true of the source as a whole, not only of the cell named. If text of the kind that field would hold was placed in another field or kept in raw or review records, say where and why; never state that the source has no such content." | — |
| R10 | Total/subtotal discrepancies not flagged | "When a cached subtotal or total disagrees with the amounts it appears to sum, or its label leaves unclear whether it is a local subtotal or an overall total, record the observation and the ambiguity in limitations with the cells involved. Do not repair, do not recompute into any output field, and do not read a zero cache as a confirmed zero total." | — |
| R11 | Nonitem role taxonomy undefined | "financial_summary: subtotal, total, tax, discount, management or insurance allocation and amount-in-words cells, plus the labels and qualifiers attached to those figures (such as tax-inclusion words beside a total). commercial_note: payment, delivery, validity, warranty, scope-option, supply or estimate statements that are not an item's own cell. document_reference: pointers to documents not in the packet. unresolved: only when two or more roles remain possible after reading; name them." | Low priority (2 cells). |
| R12 | No precedence between conflicting rules | "When two rules send the same text to different fields, apply the more specific rule and cite both in the proof. If neither is more specific, treat the text as an undecided class (R8) and record it in limitations so that the next policy version decides it." | — |
| R13 | *(Process; not generator-facing.)* Policy–expectation consistency gate | "Before admission, a reviewer independent of the package author lists every convention that each frozen expectation set applies to C/D, role and null decisions, and cites the generator-facing sentence that yields it. A convention without such a sentence blocks admission unless it is covered by prospectively declared complete alternatives. Evaluators may attach an obligation only to a class as defined in the generator-visible policy; a class extension decided during evaluation is published prospectively or excluded from obligations." | — |

**Optional mechanical aid (to be reported as deterministic):** let proofs carry explicit source spans for C and D, and have the adapter assemble D (R4 joiner, declared delimiter stripping). This would make classes 2 and 9 a route property. Any resulting score gain must be reported separately from semantic accuracy.

## 4. Evaluator fitness

### 4.1 Limits of `compare_source043` / `compare_source046` (detail-only)

1. **Column-B pairing.** An expected row pairs only with an item whose carrier location contains `B<anchor_row>`. Pairing works only when the generated location happens to include a column-B cell, as an item's description cell normally does. Sources whose descriptions are not in column B, or whose column-B cell is a covered merge, cannot pair: proofs and raw references may not cite empty cells, so every such row is reported MISSING.
2. **Components.** `evaluate()` raises an error for any expected component row. The numeric gates are forced false if the carrier contains any component. Link scoring is always empty (denominator 0).
3. **Canonical-only flags.** `unsupported_populated_columns` and the supported-provenance denominator are computed against canonical values. A declared-alternative match therefore appears as an unsupported D or a missing locator; 1141208 B's 136/137 is such an artifact.
4. **Alternatives.** Only complete C/D tuples are supported. There are no alternatives for other columns, such as group naming or party roles.
5. **Covered merges and census.** Nonitem coverage is locator presence only. Literal, role and type fidelity, and covered-cell conflicts, are left to the manual review.
6. **Provenance.** Structural presence only, not semantic correctness.
7. **CLI.** 043 hard-codes its case. 046 generalizes only the release check.

### 4.2 `compare_source040` (bundle `private/refinement/source_expectations040_001/compare_source040.py`)

It does score component rows and links, and it includes the component stratum in the gate. It does so through hard-coded case layout constants:

- analysis header and total rows and basis cell addresses;
- a fixed basis unit literal and basis quantity of 1;
- a fixed link denominator;
- a hard-coded case ID in the CLI.

It also still pairs every row by its column-B anchor. With zero component rows its gate would fail on a null percentage. It is therefore not reusable beyond its original layout.

### 4.3 Requirements for a component-capable evaluator (an XLSX case with a unit-price-analysis sheet)

1. **Expectation schema.** Per row: `category` (detail or component), `sheet` (analysis rows may sit on a different sheet from their parents), and an explicit `anchor_cell`. Per component: the expected parent row ID, basis quantity, literal basis unit, literal basis raw text, and the admissible basis locator cells. All of these are declared in the expectations, none hard-coded.
2. **Pairing** by explicit anchor cell per sheet, with exactly one hit. Detail rows may only pair with demand items and component rows only with components.
3. **Link scoring:**
   - the parent is the generated row paired with the expected parent, compared by pairing rather than by ID string;
   - basis quantity is numerically equal;
   - basis unit and basis raw are literally equal;
   - the basis locator lies within the declared cells;
   - held, missing or extra links fail.
4. **Strata and gates.** Detail, component and overall core are each at least 99%, and every expected link is correct. A zero-denominator stratum is "not applicable", never 100%. Extra components fail row-role completeness.
5. **Alternative-aware bookkeeping.** Unsupported-field flags and the provenance denominator are computed against the matched complete alternative.
6. **Not-carried outcomes.** A held export (the admitted writer cannot carry a held component link) scores 0 on every row and is recorded as a frozen failure.
7. **XLSX raw profile.** A declared profile for cached XLSX values: the stored decimal text versus the binary64 rendering, shared strings, and formula text alongside its cache. The inventory and the expectations must use the same profile.
8. **Census** includes the analysis-sheet headers and subtotals. Component rows are neither demands nor nonitems.
9. **Controls.** Artificial ideal and mutated carriers, parity with 043 on detail-only cases, an independent review, and hash-freezing before any generator starts.
10. **Exposure.** The case named as an example was exposed at checkpoint 041, so any new reading of it is regression evidence only.

**Note on `compare_source047.py`.** It appeared in commit `7aef62b` during this audit, is outside the audit baseline, and is marked "not yet reviewed". A preliminary read shows explicit anchors, component pairing, parent-by-pairing, a component gate and alternative-aware unsupported flags. It lacks basis-raw and basis-locator checks. Its provenance check no longer restricts sheets to expected sheets. Its provenance denominator is still canonical. It needs the independent review and freeze in items 9–10 before use.

## 5. Deployment feasibility

| Bar element | Current evidence | Missing in this cloud session | Owner must supply or decide |
|---|---|---|---|
| 30 independently eligible, revision-compatible pairs including 10 reserved | **1 eligible pair (exposed development, PDF source); 0 reserved; 0 performance-passed.** The bundle holds 5 projects: 3 with exposed targets (1 eligible), 2 without targets. Flat at 1 since checkpoint 044. | Eligibility evidence (initial stage, revision compatibility, pre-creation availability and adoption) for at least 29 more pairs. Source packets for those cases. All 38 reserved input packets. | Data Center originals; eligibility evidence and the bounded mail-archive lead (the multi-GB archive is not in this session); full RQA reference set if a questionnaire is needed. Reserved inputs, with reserved targets released only after all 38 outputs are frozen. |
| ≥99% per case, detail/component stratum, layout and overall | 0 cases pass. 1140908 fails. 1141208 passes the numeric gate but fails the source-case gate. Components have never been measured on the current route. PDF and multi-sheet layouts are unsupported. | An admitted PDF-region route (the single eligible pair is PDF). A reviewed XLSX route. A held-component carrying path. A reviewed component-capable evaluator. | — |
| Complete raw, provenance, nonitem and manual obligations | Raw and census mechanics complete on 2 cases (deterministic). Manual obligations failing in 4/4 runs. | — | — |
| Zero unresolved critical errors | 0 in 4 runs, with a caveat: 47 party-role positions are critical if customer-role inference is classified critical. | — | A ruling on that classification. |
| Two-reader correctness and assembly repeatability | Not met. Assembly repeatability not attempted. | The `@oai/artifact-tool` module; the pinned Windows source-verification helper and a Windows host. | The admitted export runtime. |
| Saved 17-column and visual QA | Not attempted on any 046b carrier. | As above, plus the saved-workbook viewer and renderer. | Same. |
| Runtime | The proposed sol6.1/xhigh is not selectable. Observed `claude-opus-5-5`. Results are not like-for-like with 045. | — | Either provide the proposed runtime or formally adopt the observed one, and rebaseline. |

**Eligible pairs available now: 1 (0 reserved), and 0 runnable on the current 046b route**, because the only eligible pair needs a PDF route that is not admitted.

## 6. Recommended next bounded steps (prioritized)

1. **Adopt this audit and publish a dated addendum to RESULTS_046B.** It should disclose P-1 to P-7: the interface-only review, the harness change, the case-informed declarations, the S05 scope wording, the timing and concurrency deviations, the unpinned injected instructions, and deterministic labelling. Do not edit frozen records and do not rescore.
2. **Run the policy–expectation consistency review (R13)** on both frozen expectation sets against 046b, and obtain owner decisions on (a) where supply-basis qualifiers go (R1b) and (b) whether customer-role inference is a critical class.
3. **Author 046c in a new directory** with R1–R12. Take flagged items either with an independent justification or as declared-undecided classes. Add invented changed-path fixtures per rule, and obtain an **independent semantic field-role review** in addition to the interface review, as PLAN71 requires. Keep 046b frozen.
4. **Freeze a reviewed component-capable evaluator** (section 4.3) before any component or XLSX case is admitted.
5. **Choose the next real source case** under the plan and eligibility rules. Prefer an unexposed tuning case with a layout not yet measured on the current route (components or XLSX); this needs owner-supplied originals. Do not rerun 1140908. Treat 1141208 as exposed regression material. With bundle-only resources, the 1140608 source-only structure study (no model trial) is the available breadth step.
6. **Run the export QA on the four frozen 046b carriers** in an owner-supplied export runtime: assembly only, carrier bytes unchanged.
7. **Harden the generator runtime:**
   - run generators outside the repository working directory, or pin the injected instructions;
   - restrict the tool allowlist to file read, Python and write inside the run directory;
   - declare a per-reader wall-clock bound to replace the 600+5 s model bound;
   - record durations;
   - prefer OS-level isolation where available.
8. **Restart the eligibility pipeline (owner side).** Source accuracy alone cannot reach the bar while eligible pairs stay at 1.

## 7. Full-programme-audit determinations (PLAN71 criteria)

| Criterion | Determination |
|---|---|
| Real source/layout breadth growing | **Marginal.** One new small single-sheet, detail-only case. Historically 4 distinct measured source cases; the current route has been measured on 2 cases, 1 layout class and 0 component rows. Component, PDF, multi-sheet and large layouts did not grow. The 1140608 backlog is untouched. |
| Eligible pairs growing | **No.** 1 → 1 (0 reserved, 0 performance-passed). |
| Preparation has a concrete exit | **Partly.** There is an exit for detail-only cached workbooks (route plus checker plus evaluator). There are no defined exits for PDF regions, XLSX inventories, held components or the export runtime. Exit criteria should be set before more framework work. |
| Deterministic capture confused with semantic accuracy | **Risk present.** The perfect raw and census scores are route effects, while the semantic core regressed. The public summaries should label the route effects. The 1141208 numeric pass is aided by case-informed declarations and declared alternatives. |
| Failures and best/last scores preserved | **Yes.** All 046b outcomes are frozen. The 045 scores are unchanged. |
| No mixed-configuration reliability rate | **Yes.** None reported. |

## 8. Audit limitations and exposure statement

- Comparators were not re-run. Every reported figure was recomputed from the saved comparison files, whose hashes match the evaluation summaries.
- The 045 frozen responses were not opened. The 045 comparison row results (which carry field values) were used.
- The attribution is inferential. No controlled text-versus-runtime experiment exists.
- No export runtime was available.
- The auditor read evaluator-role material for 1140908 and 1141208, including expectations and output values. The rules in section 3 derive from these two exposed cases. Future results on them are regression evidence only. The private appendix must never be passed to a generator.

## Key input hashes (sha256)

| Input | sha256 |
|---|---|
| Private results ZIP | `d6dad4f7af7ef694e47b80284ddb4d459cfdf7b74624a9d78c74eb3166d8df74` |
| ADMISSION_046b.json | `db84dce97ff4a82fbc047b1c18aedbc2d89d40c33cb51b35343e056f521b7c8e` |
| 046b PACKAGE_MANIFEST.json | `7748be1de62683f57a57398ba6a89dd6cd50c4b925471291f3839a2ab4e559f4` |
| compare_source043.py (frozen) | `1ececf30b034495bff049a629a15ccfa430f76a769d8f651d122be00aa069cb1` |
| compare_source046.py | `9d1f5ee98c570ffe1d5a03b661313e8420112b8361d48b9f0ec906e8b9731aaa` |
| 1140908 frozen expectations (043) | `04b5f42cd0ea5b198dce6a1b2cb7cda624315395b099d077989c5bf1476935ea` |
| 1141208 final expectations | `0b974752a5639f16797be8a08ae8e292db7b9fcc2479d2aa343fcd85e11d7905` |
| audit_transcript.py, pinned at admission | `03769d8cfbf9467d19dc065e50bfd298353a5f04f1065919e0d1fc2356421d3f` |
| audit_transcript.py, current (after `c3403b5`) | `fe02c1ae0409a6c01a93fa7f96d227f44e3b9d0ce0f9238a868f7aad46934dbb` |
| 046b comparisons 1140908 A / B | `78f637b6…45d2` / `89888c6f…15d5` |
| 046b comparisons 1141208 A / B | `99a5332d…9c25` / `eb25c2d4…4e06` |
