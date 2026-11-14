# Design for candidate 046i: owner decision O72 and the empty-sheet fix (2026-11-14)

Status: **design, written before any 046i file existed; built on 2026-11-14.** Written in the maintainer session for the qualification here (owner decision O64). A design critique (findings R1–R15 on the rule text and the tools, C1–C7 on the proof plan and the downstream steps) preceded the build. The build applied every finding on a file of the candidate; §9 (addendum) records how, and where §9 and an earlier section disagree, §9 governs. Nothing here is reviewed or frozen.

This is the public copy. It contains no case id, private path, session or agent id, and no business text (only the generic rule labels 合計, 總計, 項次 and the like, and invented 示例 values). The private annex with the structure-only evidence is not part of it. `$TOOLS` (§6.4) means "the qualification toolkit".

Inputs read for this design:
- the repository at `ff111fa`;
- the frozen candidate 046g at release commit `4c40004`;
- the empty-sheet WIP fix (commits `49b94bd`, `970ab11`, `c23c479`, `d1d2735`), its independent review (ADMIT_WITH_FIXES) and the fixer's notes;
- runner v4 (`deploy/run/cps_job.py`, `7505e98a…`) and its tests;
- the qualification toolkit's code;
- the structure-only record of the deterministic prepare dry run (codes, sheet indexes and counts only).

No historical 未填, target, answer, expectation or study file was opened. No qualification source content was opened.

---

## 0. Summary

**046i** is 046g, frozen at `4c40004`, plus two changes.
1. **The empty-sheet fix**, as reviewed, moved out of 046g. It includes the reviewer's two doc nits and one wording fix the review asked for in a later candidate (R59 item 8).
2. **Owner decision O72.** Today, a large workbook with no BILL1 bill sheet is held. O72 adds two exceptions to that hold:
   - **No total row** (`BILL1.NOTOTAL.v1`). Exactly one sheet carries the six-label bill header, and nothing below that header reads 合計 or 總計 in a price column. That sheet becomes the bill sheet, and the scope runs to its last row with content.
   - **No header** (`BILL1.NOHEADER.v1`). No sheet has a row with five or six of the six header labels. The whole workbook goes to the generator, which reads it as an unscoped packet.

   Every other hold stays.

**What changes:**
- `FIELD_ROLES.md` R59 (items 1, 2, 3 and 8, a new item 9, and the design-decision bullets);
- four other package texts;
- two invented examples;
- the scope tool (v4), `scope_agree.py`, the basis text of `make_scoped_inventory.py`;
- the route (v4.4, scope-fact check only);
- the scope-reader prompt template (bill-sheet and end-row bullets);
- the generator and evaluator templates (candidate label and path only);
- the harness README;
- the test suites.

**What does not change:**
- R47b and R49–R58;
- the scope reader's rules excerpt body;
- the threshold;
- the reader-response, decision, proposal, digest and fact schemas (key sets unchanged; only value domains grow, and only under the new bill rules);
- the builders and render_views;
- `make_job_config.py` and `prepare_run.py`;
- the freeze tools;
- runner v4;
- writer v2.8.2;
- evaluator v4;
- aggregator v2.

### Five findings the main session must act on

1. **"Unscoped" is impossible above the threshold under runner v4; the design realises it as a whole-workbook scoped packet.**
   - `prepare` stops with `SCOPE_COUNT_INCONSISTENT` unless the status is `NOT_APPLIED` exactly when content cells ≤ 2,500.
   - After `scope-finish`, both `check-inventory` on the scoped packet and `finish` require `scope: applied`, so a `context:scope` fact must exist.
   - The no-header case is therefore `PROPOSED`, then goes to a fresh scope reader and `scope-finish`.
   - The scoped packet equals the full inventory plus one context fact. Every non-empty sheet is in scope, no cell is removed and no view is renumbered.
   - R59 item 9 tells the generator to read it exactly as an unscoped packet.
   - The O72 record in `CURRENT_STATE.json` and `DEPLOYMENT_MODEL.md` says "unscoped". Add one sentence saying how it is realised.
2. **The brief overstates O72's coverage. One pool case stays held, so qualification still fails with certainty unless the owner decides.**
   - The brief says each of four held material lists has exactly one sheet with exactly one six-label row and no total row.
   - The structure-only record says otherwise for one of them: two sheets each carry one six-label row and no total row.
   - O72 covers "a unique bill-sheet header", so that workbook stays held (two candidate sheets).
   - It is a non-reserved pool case. A held pool run is scored as the empty carrier, which fails the 0.90 floor and so the gate (plan §5.7, §5.8).
   - The owner must rule on this pattern before 046i is frozen. The options are in §7.
3. **Requiring BILL1 (c) for the no-total case would probably defeat O72 on two of the three cases it is meant to cover.**
   - (c) asks for a positive number in a price column. The structure-only flag order suggests that in two of the three no-total workbooks the header sheet may carry no positive price (evidence in the private annex).
   - O72 names no price condition, so the design does not require (c). An unpriced no-total bill then goes through R51, or to the existing all-unpriced hold.
4. **The scope-reader template must change, so its pin changes.**
   - Without new instructions, a reader would set `end_row` or `bill_sheet_index` to null on the new patterns, and every such case would be held.
   - The generator template also changes: it names candidate 046g and its folder.
5. **One existing scope-stage test flips by design.** The fixture behind `tool_holds_zero_bill1_candidates` (the bill with its 合計 cell removed) is exactly O72's first pattern. The test is re-specified (§5.4).

---

## 1. Fixed inputs and constraints

- **O72 (2026-11-14), the owner's words:** "A narrow rule change: a unique bill-sheet header without a total row scopes to that sheet down to its last row; with no header at all, the whole workbook goes to the generator. The scope reader still has to agree. It gets an independent review, a re-freeze and a re-run rehearsal; the same rule applies in everyday use."
- **Runner v4, `prepare`, scope stage (no change allowed):**
  - the proposal's count must equal the runner's;
  - `NOT_APPLIED` exactly when count ≤ 2,500, otherwise `STOP_SCOPE_COUNT_INCONSISTENT`;
  - `HOLD` gives `OWNER_DECISION`;
  - `PROPOSED` gives a fresh scope reader, then `scope-finish`.
- **Runner v4, `scope-finish`:**
  - `scope_agree.py`: exit 3 holds, any other non-zero exit stops;
  - the decision must be `admissible`;
  - `make_scoped_inventory.py`, then `--verify` with the receipt hash;
  - route `check-inventory` on the scoped packet with `scope: applied`;
  - `prepare_run.py`.
- **Runner v4, `finish`:** `check` and `convert` with `scope: applied` after `scope-finish`.
- **What the runner reads:**
  - proposal: `status`, `content_cells_literal_or_cached`, `rule.threshold`, `holds[].code`, `flags[].code`, `bill.sheet_index`, `bill.end_row`;
  - decision: `status`, `admissible`, `reader`, `reader_doubts_count`, `role_differences`;
  - receipt: `scoped_inventory_sha256`, `full_inventory_sha256`, `route_check_inventory`.

  All of these keep their meaning in 046i. `bill.sheet_index` and `bill.end_row` may be null on a `PROPOSED` whole-workbook proposal; the runner only records them.
- **Frozen and unchanged:**
  - runner v4 and every file the runner admission pins, including `deploy/run/test_cps_job.py`, `RUN_JOB_COMMANDS.md` and `RELEASE.example.json`;
  - writer v2.8.2 (`ADMISSION_WRITER_V28.json`);
  - evaluator v4 (`compare_target050.py`, `fc723405…`) and aggregator v2 (`aggregate_qualification050.py`, `e5aa4fc7…`);
  - the builders, `render_views.py` and the other source-prep files (`research/guideline046_003/source_prep/`).
- **Policy:**
  - invented test workbooks only;
  - no historical answer, target, expectation or study file;
  - no qualification source content;
  - `research/guideline046_007` is only restored to its bytes at `4c40004`;
  - no case ids, private paths, Drive, session or agent ids, or business text in committed files.

---

## 2. (a) The candidate directory and its records

### 2.1 Layout of `research/guideline046_009/` (candidate 046i)

The source is `research/guideline046_007` at `4c40004`: 37 files.
- Package: 17 files, 16 listed in the manifest plus `PACKAGE_MANIFEST.json`.
- Harness: 14 files.
- Route tests: 5 files.
- `REVIEW_046g.md`.

| Path in 046i | Origin | Change |
|---|---|---|
| `DESIGN_046i.md` | new | This design without the private annex. |
| `DECISIONS_046i.md` | new | O72 verbatim, decisions D1–D10 (§3.2), the open owner question (§7) and its answer once given. Follows `research/guideline046_002/DECISIONS_046b.md`. |
| `REVIEW_046i.md` | new | The independent review, its fixes and the freeze status line (§2.3). Follows `REVIEW_046g.md`. |
| `package/CPS_GUIDELINE.md` | 046g | New 046i status paragraph at the top; title 候選046i; the route named v4.4 where the text names the current route (§3.5). |
| `package/PACKAGE_MANIFEST.json` | regenerated | §2.3. |
| `package/resources/FIELD_ROLES.md` | 046g | R59 amended (§3.3); title label 046i. |
| `package/resources/OUTPUT_CONTRACT.md`, `REVIEW_CHECKLIST.md`, `SOURCE_REFERENCE_CONTRACT.md` | 046g | R59 and route v4.4 wording (§3.5). |
| `package/resources/SYNTHETIC_ALLOCATION_CASES.json` | 046g | Header fields; new invented cases A50 and A51 (§3.5). |
| `package/tools/cps046b_route.py` | 046g | Route v4.4 (§4.4). The file name is kept. |
| `package/resources/EXAMPLE_INVENTORY.json`, `EXAMPLE_RESPONSE.json`, `COLUMNS.json`, `NAME_POLICY.json`, `NAMING_RULES.md`, `SEMANTIC_RESPONSE.schema.json`, `SOURCE_INVENTORY.schema.json`, `SOURCE_READING.md`, `SYNTHETIC_NAMING_CASES.json` | 046g | **Byte-identical.** The two examples' history notes ("revised for 046g … route v4.3, like v4.2, warns …") stay true, and keeping them identical keeps every route-test fixture derived from them identical. |
| `harness/scope_tool.py` | `d1d2735` | v3 empty-sheet fix plus O72; becomes v4 (§4.1). |
| `harness/make_scoped_inventory.py` | `d1d2735` | Empty-sheet acceptance (as reviewed); basis text per bill rule; labels (§4.3). |
| `harness/scope_agree.py` | 046g | Whole-workbook agreement; the fact's `bill_rule` from the proposal; labels (§4.2). |
| `harness/SCOPE_READER_PROMPT_TEMPLATE.md` | 046g | §4.5. |
| `harness/GENERATOR_PROMPT_TEMPLATE.md` | 046g | One line: candidate 046i and `research/guideline046_009/package/` (§4.6). |
| `harness/EVALUATOR_BRIEF_TEMPLATE.md` | 046g | Candidate label; one sentence on whole-workbook packets (§4.6). |
| `harness/README.md` | `d1d2735` | Retargeted to 046i; reviewer nit fixed; O72 documented (§4.6). |
| `harness/BUGFIX_EMPTY_SHEETS.md` | `d1d2735` | Paths, title note, and a pin table naming 046i (§4.6). |
| `harness/make_job_config.py`, `prepare_run.py`, `freeze_admission.py`, `freeze_outputs.py`, `make_release.py`, `audit_transcript.py`, `fullpath_check.py` | 046g | **Byte-identical.** None names the candidate. Their sha256 stays the same; only the path changes. |
| `route_tests/run_route_tests.py`, `make_fixtures.py`, `run_scope_stage_tests.py` | 046g | v4.4 tests and new fixtures; existing fixtures byte-identical (§5.4). |
| `route_tests/run_empty_sheet_tests.py` | `d1d2735` | Version expectation v4; NT and NH cases with empty sheets added (§5.4). |
| `route_tests/parity_batch.mjs`, `test_compare_source047.py` | 046g | **Byte-identical.** The second tests the superseded evaluator and fails the same way on 046g; it is not part of the proof. |

`REVIEW_046g.md` is not copied. A candidate folder holds its own review only.

No top-level README is added: none of the earlier candidate folders (046b–046g) has one. `harness/README.md` is the candidate's README, and `DESIGN_046i.md` gives the overview.

### 2.2 Build order (separate commits, so each step can be checked on its own)

| Step | Commit content | Check before the next step |
|---|---|---|
| C0 | Restore `research/guideline046_007` to `4c40004`: check out the 3 modified files (`harness/scope_tool.py`, `harness/make_scoped_inventory.py`, `harness/README.md`) from `4c40004` and delete the 2 WIP additions (`harness/BUGFIX_EMPTY_SHEETS.md`, `route_tests/run_empty_sheet_tests.py`). | `git diff --quiet 4c40004 -- research/guideline046_007` is empty. `git ls-tree -r` of the folder equals that at `4c40004` (37 entries). The package manifest is still `bf06fae2…`. The harness hashes again equal the toolkit's current expectations (`scope_tool.py` `e9190c2f…`, `make_scoped_inventory.py` `9a6fca56…`). |
| C1 | Copy of the restored folder into `research/guideline046_009/` (package, harness, route_tests; not `REVIEW_046g.md`). | Each of the 36 copied files is byte-equal to its 046g original. |
| C2 | The reviewed WIP files at `d1d2735`, unmodified: `scope_tool.py` (`4bd332ff…`), `make_scoped_inventory.py` (`3a1aec72…`), `README.md` (`2027355d…`), `BUGFIX_EMPTY_SHEETS.md` (`b0f8a5a6…`), `run_empty_sheet_tests.py` (`b35e8232…`). | Hashes as listed. The C2 tree reproduces the reviewer's suite results: empty-sheet 64/64, scope 62/62, route 284/284. It is the "046g plus the empty-sheet fix" baseline B3 in its new folder. |
| C3 | Everything in §3 and §4, the new tests, `DECISIONS_046i.md`, `DESIGN_046i.md`, a draft manifest. | Proof plan §5.2–§5.5. |
| C4 | Review fixes (§5.7). | Suites again; manifest regenerated. |
| C5 | Freeze: manifest final, `REVIEW_046i.md` status line, `CURRENT_STATE.json` `candidate_046i`. | §5.7. |
| C6 | Docs and plan text (§6.1). This or a later commit is the release commit. | §6.2. |

C0 may share a commit with C1. The C2 commit is kept so that the reviewed bytes are visible in history at their new path. The WIP commits stay in history; nothing is rewritten.

### 2.3 Records

- **`PACKAGE_MANIFEST.json`.** Same schema and key order as 046g:
  - `schema` `cps.guideline-package.manifest.v2`;
  - `candidate` `046i`; `parent_candidate` `046g`; `parent_manifest_sha256` `bf06fae2e3ab0129ecbe6d88a97f00edac9b9cfbe47847eecc11313e5620b25f`;
  - `status` `FROZEN_FOR_BOUNDED_SOURCE_TRIAL_NOT_DEPLOYED` (the string every earlier candidate uses);
  - `target_runtime`: "Qualification: the maintainer session (owner decision O64). Use: the Dot operator runtime (O36, O37). Every run records the actual model, effort and tools; scores do not carry across models.";
  - `semantic_review` `research/guideline046_009/REVIEW_046i.md`;
  - `route` `{path: tools/cps046b_route.py, version: cps046i-route.v4.4}`;
  - `utf8_bytes` recomputed; `manifest_self_excluded` true; `deployment_approved` false;
  - `files`: the same 16 paths with bytes and sha256.
- **`DECISIONS_046i.md`** records:
  - O72 verbatim;
  - the runner constraint and why the no-header case is `PROPOSED` (finding 1);
  - D1–D10 of §3.2;
  - the one-pool-case finding (no case id) and the owner's ruling once given;
  - what was explicitly not changed.
- **`REVIEW_046i.md`**, written by the review step. The first line is the status, in 046g's form: "semantically approved …, frozen YYYY-MM-DD (manifest `…`, 16 files). Not admitted, not deployed." It also gives a table of the harness and route-test file sha256 at the freeze, since the harness is pinned by the release rather than by the manifest.
- **`CURRENT_STATE.json`.** Add `candidate_046i` in `candidate_046g`'s form:
  - path, manifest, status `FROZEN_NOT_ADMITTED`;
  - review, route `cps046i-route.v4.4`, scope tool `cps046i-scope-tool.v4`;
  - evaluator and aggregator unchanged;
  - writer V28;
  - frozen date;
  - next step (release, qualification admission, re-run rehearsal).

  `candidate_046g` stays as it is, with `next` noting that it was superseded by 046i for qualification.

### 2.4 Restoring 046g

Only C0 touches `research/guideline046_007`.
- The 3 modified files `harness/scope_tool.py`, `harness/make_scoped_inventory.py` and `harness/README.md` return to their `4c40004` bytes, so the whole folder is again the frozen tree.
- `harness/BUGFIX_EMPTY_SHEETS.md` and `route_tests/run_empty_sheet_tests.py` are removed there and live on in 046i.
- `REVIEW_046g.md` is not edited: 046g's own record does not mention the WIP fix. The history lives in git and in 046i's `BUGFIX_EMPTY_SHEETS.md`.

---

## 3. (b) The rule

### 3.1 Terms (used in the rule text and the tools)

- **The six header labels** are BILL1 (a)'s categories:
  - 項次;
  - a name word (項目及說明, 名稱, 品名 or 材料名稱);
  - 單位;
  - 數量;
  - 單價;
  - 複價 or 金額.

  A row *carries* a label when a text cell on it (saved type text, literal or cached formula), with every whitespace character removed, equals it. A row carries *five of the six* or *all six* by the number of categories it carries. Every sheet is considered, hidden ones included.
- **The last row with content** of a sheet is the greatest row number among the sheet's content cells. A content cell is one the route counts (`Inventory.has_content`): literal or cached formula with a saved value that is not null and not "", or an error, missing-cache or unresolved cell, or a covered cell with conflicts. These are exactly the rows the digest's `last_rows` lists, and the route can recompute the value from a scoped packet that keeps the sheet.
- **An empty sheet** has rows × columns = 0 and no cell or view (the empty-sheet fix). The builders write it with `in_scope` false.

### 3.2 Decisions (recorded in `DECISIONS_046i.md`)

| # | Decision | Reason |
|---|---|---|
| D1 | The O72 cases are considered only when the stage applies (more than 2,500 literal or cached-formula content cells) and no sheet is a BILL1.v1 candidate. At or below the threshold the tool computes exactly what v3 computes. | Below the threshold every sheet is already in scope. A small workbook's proposal and runner facts then stay identical even if it shows one of the patterns. |
| D2 | **No total row, `BILL1.NOTOTAL.v1`.** All of the following hold: no BILL1.v1 candidate; exactly one sheet S has a row carrying all six labels; S has exactly one such row (BILL1 (a)); no other sheet has a row carrying five of the six; and BILL1 (b) fails on S (no price-column cell below the header reads exactly 合計 or 總計). S is the bill sheet, its header row is that row, and the end row is S's last row with content. | O72's "a unique bill-sheet header without a total row". The five-of-six clause is the narrow reading of "unique": a five-of-six row elsewhere is BILL1's known "vocabulary variant" failure, possibly a second bill. Review question RQ1. |
| D3 | BILL1 (c) (a positive number in a price column) is **not** required under `BILL1.NOTOTAL.v1`. "That sheet" in O72 is read as "that sheet is the bill sheet": R59's R51 rule still brings in the analysis sheets when every line of the range has no price and no status (an interpretation beyond O72's literal words; owner confirmation, §9). | O72 names no price condition. A bill without prices may well have no total row. Its lines then go through R51 (an analysis sheet is in scope when every in-range line has no price and no status) or to the existing hold for an all-unpriced range without an analysis sheet. A sheet that has a total row but fails (c) is not covered by O72 and still holds. Review question RQ2. |
| D4 | **No header, `BILL1.NOHEADER.v1`.** No BILL1.v1 candidate, and no row of any sheet carries five or all six labels. The scope stage fixes no bill sheet and no end row (no sheet has a BILL1 header row), and every non-empty sheet is in scope with the role the tool computes (never `bill`); the generator finds the bill sheet, if any, by R49. | O72's "no header at all". A five-of-six row is a header-like row, so it is not "no header". |
| D5 | Every other workbook keeps its v3 outcome. That includes every hold:<br>- two or more BILL1.v1 candidates;<br>- zero candidates with two or more sheets carrying an all-six row;<br>- one sheet with two all-six rows;<br>- an all-six sheet plus a five-of-six row on another sheet;<br>- an all-six sheet whose price column has a total but which fails (c);<br>- only five-of-six rows;<br>- `NO_IN_RANGE_LINES`;<br>- `R51_ALL_UNPRICED_WITHOUT_ANALYSIS_SHEET`. | The task and O72 ("narrow"). Hold codes and notes are unchanged. Two boundaries are non-monotonic and follow from O72's narrow wording, not from a safety reason (exact total but no price holds, no total is scoped; a five-label header holds, a four-label header goes whole); both are owner questions (§9). The five-of-six clause also counts analysis block headers that carry 項次 (a known coverage limit; such a case is held, never wrongly scoped). |
| D6 | The two new cases still need the fresh scope reader's agreement on the bill sheet, the end row and every `in_scope` flag. A whole workbook is agreed as `bill_sheet_index` null, `end_row` null and every non-empty sheet in scope. | O72 ("the scope reader still has to agree"). For the whole-workbook case it is also required, because runner v4 sends every `PROPOSED` case to a reader. |
| D7 | The whole-workbook case is a scoped packet that is read as unscoped. Its fact has `bill_rule` `BILL1.NOHEADER.v1`, three nulls, and every non-empty sheet in scope. | Finding 1. |
| D8 | The case is carried by the existing fact key `bill_rule`, with three values. No key is added to any schema. Schema identifiers keep `.v1`. | Every output for a workbook without the new patterns stays byte-identical apart from versions and hashes (§5.2), and runner v4's tests, whose invented reader responses use `cps.scope-reader-response.v1` with exact keys, pass unchanged. Route v4.3 rejects the two new values (`R59_SCOPE_FACT_INVALID`), so no older consumer misreads them. Review question RQ4. |
| D9 | R47b and R49–R51 are unchanged, so the reader's rules excerpt body is byte-identical. The reader gets the O72 boundary rules from its prompt template, where its BILL1 instructions already live (§4.5). | R49 already says how a range without a total ends. The O72 rules are scope-stage rules (R59). Putting them in the excerpt would change every excerpt. |
| D10 | R59 item 8 also states the empty-sheet exception on every packet. | Review finding 4 of the empty-sheet review: a generator could read a 0 × 0 out-of-scope sheet on an unscoped packet as a missing source. |

### 3.3 Exact amended text of `package/resources/FIELD_ROLES.md`

Only the passages below change. Everything else in the file is byte-identical to 046g, including R47b, R49, R50 and R51.

**Line 1.** Replace `# The17 output fields (candidate 046g)` with `# The17 output fields (candidate 046i)`. ("The17" is kept exactly as written.)

**Section heading.** Replace `## Scoped packets R59 (046g, declared before any 046g generation)` with:

> `## Scoped packets R59 (046g, declared before any 046g generation; amended in 046i under owner decision O72, declared before any 046i generation)`

**Intro paragraph.** Keep it and append one sentence:

> 046i (owner decision O72) adds two boundary cases: a bill sheet without a total row (item 2) and a workbook without a bill header, which goes to the generator whole (item 9).

**Item 1.** Replace the sentence "It also gives `bill_sheet_index`, `bill_header_row`, the R49 end row `end_row`, the rule versions (`R59`, `BILL1.v1`), the threshold count and the SHA-256 of the scope digest, of the full inventory and of the frozen scope decision." with:

> It also gives `bill_sheet_index`, `bill_header_row`, the end row `end_row`, the rule `R59`, the bill rule `bill_rule` that fixed the bill sheet and the end row (`BILL1.v1`, `BILL1.NOTOTAL.v1` or `BILL1.NOHEADER.v1`; items 2 and 9), the threshold count and the SHA-256 of the scope digest, of the full inventory and of the frozen scope decision.

**Item 2.** Keep the existing text and append one paragraph, indented as item 6's second paragraph is:

> *No total row (`bill_rule` `BILL1.NOTOTAL.v1`, owner decision O72).*
> - The bill sheet has no cell reading 合計 or 總計 in its unit-price or amount column below the header, and `end_row` is its last row with content, so the scope keeps every row of it.
> - The sheet is still the bill sheet; do not re-decide it.
> - `end_row` is not a total row. The quoted range runs from the first item line below `bill_header_row` and ends as R49 says when no total row exists: at the last item line before the signature line, or at the end of the sheet.
> - The cells after that line take their roles as on an unscoped packet.

**Item 3.** Replace the sentence "The end row itself is `financial_summary` (R11)." with:

> The end row itself is `financial_summary` (R11), except under `BILL1.NOTOTAL.v1`, where no row follows it and every cell of the bill sheet takes its role as on an unscoped packet (item 2).

**Item 8.** Replace it with:

> 8. **Unscoped packets.** Without `context:scope`, every sheet of the workbook is in scope, as in 046f.
>    - On every packet, the exception is an empty sheet (no cell; `rows` × `columns` = 0). The inventory builders list it with `in_scope` false.
>    - It holds nothing. It is not a missing, unreadable or incomplete source, and it is no reason to hold (item 5).

**New item 9**, after item 8:

> 9. **Whole workbook (`bill_rule` `BILL1.NOHEADER.v1`, owner decision O72).** No sheet of the workbook has a bill header row: no row carries five or all six of the six BILL1 header labels (design decision below).
>    - `bill_sheet_index`, `bill_header_row` and `end_row` are null, and no sheet has role `bill`.
>    - Every sheet except an empty one is in scope, whatever its `role`.
>    - The packet is the whole workbook. Read it exactly as an unscoped packet (item 8): R49–R51 decide the bill sheet, the quoted range and the rows from the cells, and the census covers every sheet.
>    - Items 2, 3 and 6 do not apply. Items 1, 4, 5 and 7 apply; `context:scope` is still never evidence.

**Design decision, *Procedure* step 3.** Replace "and returns each sheet's role and flag, the bill sheet and the end row." with:

> and returns each sheet's role and flag, the bill sheet and the end row (both null when it finds no bill header, item 9).

**Design decision, the paragraph after the procedure.** Replace "Zero or several BILL1 sheets hold the case. A range with no item-like line, or an all-unpriced range without an analysis sheet, also holds the case." with:

> - Several BILL1 sheets hold the case.
> - Zero BILL1 sheets hold it too, unless one of the two O72 cases below applies.
> - A range with no item-like line, or an all-unpriced range without an analysis sheet, also holds the case, under `BILL1.NOTOTAL.v1` as under `BILL1.v1`.

**Design decision, new bullet** after the *BILL1.v1* bullet (which is unchanged) and before *Limits*:

> - *O72 cases (046i; owner decision O72, 2026-11-14).*
>   - *When they are considered.* Only when the stage applies and no sheet is a BILL1 candidate. The six header labels are those of (a): 項次; a name word; 單位; 數量; 單價; 複價 or 金額.
>   - *No total row, `BILL1.NOTOTAL.v1`.*
>     - The conditions: exactly one sheet of the workbook has a row carrying all six labels; it has exactly one such row, so it meets (a); no other sheet has a row carrying five of them; and (b) fails on it, so no price-column cell below the header reads 合計 or 總計.
>     - That sheet is the bill sheet, and the end row is its last row with content.
>     - (c) is not required. A bill without prices may have no total row. Its lines then go through R51 (an analysis sheet is in scope when every in-range line has no price and no status) or to the hold for an all-unpriced range without an analysis sheet.
>   - *No header, `BILL1.NOHEADER.v1`.* No row of any sheet carries five or all six of the labels. There is no bill sheet, and every sheet except an empty one is in scope (item 9).
>   - *Every other workbook with no candidate still holds.* That covers:
>     - two or more sheets with an all-six row;
>     - a sheet with two such rows;
>     - an all-six row together with a five-of-six row on another sheet;
>     - a sheet that has a total row but fails (c);
>     - a workbook whose only header-like rows carry five of the six labels.
>   - *Reader agreement.* The scope reader must agree on both cases, as on any other (procedure step 4).
>     - On a no-total sheet, its independent check is that the digest shows no total in the price columns. A total the tool's exact test misses (a variant such as 合計： or an unlabelled total) shows there, the reader disagrees, and the case is held.
>     - On a whole workbook, its independent check is that no header row shown in the digest carries the labels.

**Design decision, *Limits*.** Append:

> A whole-workbook packet is as large as the workbook. Scoping does not shrink it, so the census limit that the 046g study found for one reader applies to it in full.

### 3.4 R47b and R49–R51 (the reader's excerpt): no change

`scope_tool.extract_rules` copies the paragraphs that start `**R47b `, `**R49 `, `**R50 ` and `**R51 ` verbatim. In 046i they are byte-identical to 046g.
- R49 already says: "When no total row exists, the range ends at the last item line before the signature line or the end of the sheet." That is exactly what the generator does inside a no-total bill sheet.
- R51 is untouched.

The excerpt file therefore differs from 046g's only in its header line: the candidate label `046i` and the FIELD_ROLES sha256.

An alternative was considered and not adopted: add an O72 paragraph to the excerpt (for example `**R59a`). It would give the reader its boundary rules as package text, but it changes every excerpt and every reader input, including those of ordinary workbooks, and breaks the identity proof of §5.2.

### 3.5 Other package texts

- **`CPS_GUIDELINE.md`.**
  - Title `…候選046i`.
  - A new first status paragraph, in the guideline's language and register. It says that 046i is the frozen 046g plus:
    - (1) O72's two scope boundary cases (R59 items 2 and 9);
    - (2) the empty-sheet wording of R59 item 8;
    - and that the route is v4.4 (`cps046i-route.v4.4`), which changes only the scope-fact check.
  - The 046g paragraph stays as history.
  - Where the text names the current route's behaviour (the R54/O16 sentence "路由v4.3（同v4.2）"), write v4.4.
- **`OUTPUT_CONTRACT.md`.**
  - Title `(candidate 046i, draft)`.
  - Intro: "046i (owner decision O72) adds two scope boundary cases (R59 items 2 and 9)."
  - In the inventory description, after "the bill sheet, its header row and the end row": "(all three null on a whole-workbook packet, R59 item 9)".
  - Step 1, after "(R59 item 2)": "; under `BILL1.NOTOTAL.v1` the end row is the bill sheet's last row with content and R49 ends the range inside the sheet; under `BILL1.NOHEADER.v1` the packet is the whole workbook and is read as an unscoped packet (R59 item 9)".
  - The analysis_unlinked sentence for scoped packets: add "(not on a whole-workbook packet)".
  - Heading "Interface points (route v4.4)"; the intro sentence adds "route v4.4 (candidate 046i) extends point 4a to the two O72 bill rules".
  - Point 4a: add the v4.4 checks of §4.4 in one sentence each.
- **`REVIEW_CHECKLIST.md`.**
  - Title label.
  - 3a: add "Above the threshold, a workbook with no BILL1 candidate is scoped only under the two O72 cases (`BILL1.NOTOTAL.v1`, `BILL1.NOHEADER.v1`), with the reader's agreement; every other zero-candidate workbook went to the owner."
  - Item 7: `cps046i-route.v4.4`.
  - 15a: add "Under `BILL1.NOTOTAL.v1` the end row is the bill sheet's last row with content and R49 decides the range inside the sheet; under `BILL1.NOHEADER.v1` the packet is read as unscoped: the bill sheet and range are decided from the cells, and components of priced or not-estimated parents are `analysis_component` items as on an unscoped packet."
- **`SOURCE_REFERENCE_CONTRACT.md`.**
  - Title and status line: candidate 046i, route v4.4.
  - §1b: `bill_rule` is `BILL1.v1`, `BILL1.NOTOTAL.v1` or `BILL1.NOHEADER.v1`. The three bill fields are positive integers, or all three null under `BILL1.NOHEADER.v1`.
  - "Scope checks (route v4.4)": the three code bullets restated exactly as §4.4 checks them.
- **`SYNTHETIC_ALLOCATION_CASES.json`.**
  - Header: `candidate` `046i`; `rules` "FIELD_ROLES R47b-R59 (candidate 046i, route v4.4; R59 amended under O72; …rest as 046g)"; the scoped-packet assumption names "A35-A37, A50, A51"; `case_count` 51. The "Scoped packets" sentence gains: "A50 and A51 show the two O72 bill rules."
  - **A50** (rule "R59 item 2 (BILL1.NOTOTAL.v1), R49, R11"):
    - Input: A35's workbook with the 合計 row removed and no line after the signature. The fact has `bill_rule` `BILL1.NOTOTAL.v1`, bill sheet 2, header row 2, `end_row` 9 (the last row with content). Rows 3–6 are A35's lines, row 8 is A35's invented signature line, and row 9 is the price-inclusion statement 以上單價含運費 (R11's own example).
    - Expected: rows 3, 4 and 6 exactly as in A35; row 5 `excluded_supply` (R45); row 8 `footer` (OUTPUT_CONTRACT: signature lines) and row 9 `commercial_note` (R11), as on an unscoped packet, not item 3's `excluded_supply`. The route check passes with `scope: applied`.
    - Reason: the scope keeps the whole sheet, and R49 ends the range at the last item line before the signature.
  - **A51** (rule "R59 item 9 (BILL1.NOHEADER.v1), R49"):
    - Input: two sheets above the threshold. Sheet 1 is a priced list whose header reads 序號, 品名規格, 單位, 數量, 單價, 金額: only four of the six labels, because 序號 and 品名規格 are not BILL1 words. It has a 合計 in the 金額 column. Sheet 2 is an invented memo. The fact has `bill_rule` `BILL1.NOHEADER.v1`, three nulls, and both sheets in scope with role `other`.
    - Expected: the generator finds the bill sheet itself (R49) and gives sheet 1's lines as rows, as on an unscoped packet. The memo cells take census roles. Nothing is `excluded_supply` under R59 item 3. The route check passes with `scope: applied`.
    - Reason: the scope stage could not fix a bill sheet by labels, so the whole workbook is read as unscoped.

---

## 4. (c) The tools

### 4.1 `harness/scope_tool.py` v4 (`TOOL_VERSION = 'cps046i-scope-tool.v4'`)

The baseline is the reviewed v3 file at `d1d2735` (`4bd332ff…`). Everything in v3 stays, including the empty-sheet acceptance and its refusals (`FULL_INVENTORY_REQUIRED`, `ALREADY_SCOPED`, in the same order), the threshold, BILL1.v1 (a)–(c), roles, R51, links, flags, the digest and the excerpt. v4 changes only the steps below.

1. **BILL1 decision.** Compute `b1` per sheet exactly as v3 (this already records, per sheet, the all-six rows and the five-of-six rows), then:
   - **one** v1 candidate: as v3, rule `BILL1.v1`;
   - **two or more** v1 candidates: as v3, hold `BILL1_CANDIDATES_NOT_ONE`, rule `BILL1.v1`;
   - **zero** candidates and the stage does **not** apply: as v3 (no bill, no hold reported), rule `BILL1.v1`;
   - **zero** candidates, the stage applies, and D2 holds: rule `BILL1.NOTOTAL.v1`, bill = S;
   - **zero** candidates, the stage applies, and D4 holds: rule `BILL1.NOHEADER.v1`, no bill;
   - otherwise: as v3, hold `BILL1_CANDIDATES_NOT_ONE`, rule `BILL1.v1`.

   D2 and D4 cannot both hold, because D2 needs an all-six row and D4 forbids one.
2. **No-total geometry.**
   - Header row, header columns and price columns exactly as v1's (a) and (b): the 單價 columns and the 複價 columns, or the 金額 columns when the header has no 複價.
   - `end_row` = L, S's last row with content. `end_cell` = null.
   - **In-range lines:** v1's line procedure (item-like rows, continuation rows, states, code tokens) over rows after the header row up to **and including** L. In v1 the end row, a total row, is excluded; here there is no total row to exclude.
   - `first_item_row` is the first item-like row in that span.
   - `NO_IN_RANGE_LINES` and `R51_ALL_UNPRICED_WITHOUT_ANALYSIS_SHEET` then apply exactly as under v1.
   - S's role is `bill` (the role function is called with "is the bill sheet" true for S instead of "is a v1 candidate").
3. **Whole workbook.**
   - No bill, no lines; `condition_i` false; no R51 hold.
   - Roles as computed for a sheet that is not the bill sheet.
   - Every non-empty sheet: `in_scope` true. Every empty sheet: `in_scope` false with v3's empty reason.
   - `linked_analysis_blocks` 0. Analysis-block counts are still computed, with zero links.
4. **Reasons.** Two new entries; every v3 reason string is unchanged.
   - No-total bill sheet: `bill: the only sheet with a BILL1 header row and no 合計 or 總計 below it in a price column; the scope runs to its last content row and R49 ends the quoted range inside it (R59 item 2, O72)`.
   - Whole workbook, each non-empty sheet: `<role words>: no sheet has a BILL1 header row (five or six of its labels), so the whole workbook is in scope and is read as an unscoped packet (R59 item 9, O72)`. The role words are `analysis`, `summary`, `resource statistics` or `other`, as the existing reasons write them.
5. **Flags.**
   - All v3 flags are computed as before; on the no-total sheet that includes `NEAR_BILL1_CANDIDATE`, since it is a v1 near candidate.
   - New informational flags, appended before the per-sheet flags:
     - `BILL1_NO_TOTAL_ROW` (sheet S; detail `header_row`, `end_row`, note "no 合計/總計 in a price column below the header (O72)");
     - `BILL1_NO_HEADER` (`sheet_index` null; detail `sheets_in_scope`, note "no row carries five or six BILL1 header labels (O72)").
   - Neither is compared by `scope_agree.py`. Both reach the decision's `tool_flags` and the runner's facts.
6. **Proposal fields.** No new key. `rule.bill` and `bill.rule` are the deciding rule id. Every other field keeps its v3 meaning:
   - `bill.candidates` stays the v1 candidate list, so it is `[]` under both O72 rules;
   - `bill.sheet_index`, `header_row`, `price_columns`, `end_row` and `first_item_row` are filled under `BILL1.NOTOTAL.v1`;
   - `end_cell` is null under `BILL1.NOTOTAL.v1`;
   - all of these are null under `BILL1.NOHEADER.v1`.

   Status is `PROPOSED` unless a hold applies. Holds and their notes are verbatim v3.
7. **Digest.** No change for `BILL1.v1` or for holds. Under `BILL1.NOTOTAL.v1`, two additions, both only in no-total digests:
   - S's `counts` gains `lines_from_first_item_below_header_to_last_content_row` with the same sub-keys as the v1 key (`lines`, `priced`, `not_estimated`, `other_price_text`, `unpriced_no_status`).
   - The digest `note` gains one sentence: "On a sheet with a bill header and no exact 合計/總計 price-column row, the lines run to its last content row."

   Under `BILL1.NOHEADER.v1` the digest is unchanged in form; the v3 note stays literally true, since there are no lines.
8. **Excerpt.** Same paragraphs, byte-identical body. The header line reads `# Scope reader rules excerpt (candidate 046i)` and carries the 046i FIELD_ROLES sha256.
9. **Docstring.** Line 3 now says the full inventory has every *non-empty* sheet in scope (review nit). Add an "O72 cases (v4)" paragraph stating D1–D5 as above.
10. **Internal module name** `cps046i_route_for_scope_tool`. It never appears in an output.

Determinism is unchanged: no clock or randomness in the proposal or digest.

### 4.2 `harness/scope_agree.py`

1. `check_reader`: unchanged. The reader schema stays v1 with exact keys.
2. `decide` validates the proposal's rule:
   - `bill.rule` must be one of the route's `SCOPE_BILL_RULES`;
   - under `BILL1.NOHEADER.v1`, `bill.sheet_index`, `header_row` and `end_row` are null;
   - under the other two rules they are positive integers;
   - otherwise refuse `PROPOSAL_BILL_RULE` (exit 1). This is a guard that the tool never triggers.
3. The bill-sheet and end-row comparisons are unchanged. A whole-workbook proposal agrees only with a reader whose `bill_sheet_index` and `end_row` are null.
4. The reader's bill role:
   - under `BILL1.v1` and `BILL1.NOTOTAL.v1`, the v3 check runs verbatim: role `bill` exactly on `bill_sheet_index`, otherwise the difference `reader_bill_role`;
   - under `BILL1.NOHEADER.v1`, the reader must give role `bill` to no sheet, otherwise `reader_bill_role` with the same note.

   Keeping the v3 statement for the other rules keeps every hold file of a v1 case byte-identical (a v1 reader with a null index still gets both differences, as before).
5. The `in_scope` flag comparison is unchanged, so the reader must put every non-empty sheet in scope and leave empty sheets out to agree on a whole workbook.
6. The fact: `bill_rule` is the proposal's `bill.rule` (for `BILL1.v1` the same value v3 wrote from the route constant), and `bill_header_row` is the proposal's (null under `BILL1.NOHEADER.v1`). Other fields as v3.
7. Docstring and module label 046i. `DECISION_SCHEMA` stays `cps.scope-decision.v1`.

### 4.3 `harness/make_scoped_inventory.py`

The baseline is the reviewed file at `d1d2735` (`3a1aec72…`). The projection, `--verify`, `load_inputs` (including the empty-sheet acceptance), the receipt and the serialization are unchanged. Projection under `BILL1.NOHEADER.v1` needs no code change: every non-empty sheet is in scope, so no cell or view is removed and the view map is the identity. The scoped inventory then equals the full inventory, record by record, except the appended fact.

Only `fact_record`'s `basis` text changes, by `bill_rule`:
- **`BILL1.v1`.** v3's text with "candidate 046g" replaced by "candidate 046i", and in the stand-in variant "route v4.3 rejects this fact" replaced by "route v4.4 rejects this fact". These are version substitutions only.
- **`BILL1.NOTOTAL.v1`.** v3's text, with "the two agreed on the bill sheet, the R49 end row and every in_scope flag" replaced by:

  > the two agreed on the bill sheet, that it has no 合計 or 總計 row in its price columns (so end_row is its last row with content and R49 ends the quoted range inside it; owner decision O72), and every in_scope flag
- **`BILL1.NOHEADER.v1`.**

  > Scope decision for this packet (FIELD_ROLES R59 item 9, candidate 046i, owner decision O72). The source preparer found no bill header row on any sheet of the full inventory (harness/scope_tool.py); <reader phrase>; the two agreed that there is no bill sheet and that every sheet with a cell is in scope (harness/scope_agree.py), and the decision was frozen before generation. This inventory holds the whole workbook; an empty sheet has no cell and stays out of scope. Read it as an unscoped packet. This fact is never field evidence.

  `<reader phrase>` is v3's phrase, admissible or stand-in.

The docstring and module label also change.

### 4.4 Route v4.4 (`package/tools/cps046b_route.py`, `VERSION = 'cps046i-route.v4.4'`)

**Constants.**
- `SCOPE_BILL_RULE = 'BILL1.v1'` is kept.
- New: `SCOPE_O72_RULES = ('BILL1.NOTOTAL.v1', 'BILL1.NOHEADER.v1')` and `SCOPE_BILL_RULES = (SCOPE_BILL_RULE,) + SCOPE_O72_RULES`.
- `SCOPE_FACT_KEYS`, `SCOPE_SHEET_KEYS`, `SCOPE_FACT_SCHEMA`, `SCOPE_RULE`, `SCOPE_THRESHOLD`, `SCOPE_AGREEMENT`, `SCOPE_IN_ROLES` and `SCOPE_OUT_ROLES` are unchanged.

**`scope_fact` (check (a)).** Every statement of v4.3 runs in the same order with the same messages, except as follows.

1. **Schema, rule, bill rule and agreement.**
   - If schema, rule and agreement are right and `bill_rule` is one of `SCOPE_O72_RULES`, the v4.3 tuple check is skipped.
   - Otherwise the v4.3 check runs verbatim, with the same message and expected list naming `BILL1.v1`.

   So a stand-in agreement, or an unknown rule, still gives `R59_SCOPE_FACT_INVALID` with v4.3's exact detail.
2. **Positive integers.**
   - Under `BILL1.NOHEADER.v1`: `bill_sheet_index`, `bill_header_row` and `end_row` must each be null, otherwise `R59_SCOPE_FACT_INVALID` "null required under BILL1.NOHEADER.v1" with the key.
   - Otherwise the v4.3 loop runs verbatim.
3. **Sheet types and join:** unchanged.
4. **Roles.**
   - Under `BILL1.NOHEADER.v1`, an in-scope sheet's role must be in `SCOPE_OUT_ROLES` (summary, analysis, resource statistics, other). The problem text is v4.3's, with the allowed list.
   - Otherwise the v4.3 statement runs verbatim.
5. **Bill sheet.**
   - Under `BILL1.NOHEADER.v1`, three problem types:
     - (i) any sheet with role `bill`: "no sheet has role bill under BILL1.NOHEADER.v1";
     - (ii) a sheet whose `in_scope` differs from `rows × columns > 0`: "under BILL1.NOHEADER.v1 a sheet is in scope exactly when it is not empty";
     - (iii) any `linked_analysis_blocks` other than 0.
   - Otherwise the v4.3 statements run verbatim: exactly one in-scope bill sheet named by `bill_sheet_index`, and `bill_header_row < end_row <=` its rows.
   - Under `BILL1.NOTOTAL.v1` only, an extra problem: `end_row` differs from the greatest row of the bill sheet's content cells in the inventory ("under BILL1.NOTOTAL.v1 end_row is the bill sheet's last row with content").
   - All of these are reported as `R59_SCOPE_FACT_MISMATCH`, as v4.3 reports its problems.
6. **Content-cell counts, out-of-scope cells and views, the warning `R59_LINKED_ANALYSIS_OUT_OF_SCOPE`:** unchanged.

**Check (b) `R59_ROW_BELOW_END_ROW`.** Applied when the fact's `bill_sheet_index` is not null, which is every fact except `BILL1.NOHEADER.v1`. The statement is otherwise verbatim. Under `BILL1.NOTOTAL.v1` no content cell lies below `end_row`, so it can fire only on a citation of a blank cell below the sheet's last content row; that rejection is still right.

**Unchanged:**
- checks (c)–(e), including `R59_SCOPE_FACT_CITED`;
- the `scope: applied|not_applied` field;
- every v4.2 check;
- `check-inventory`, `check` and `convert` behaviour without `context:scope`;
- the writer port and `PORT_RELAXATIONS`: the port section must stay byte-identical to v4.2's, which the parity test checks.

**Docstring.** Add a "v4.4 (candidate 046i, FIELD_ROLES R59 items 2 and 9, owner decision O72)" paragraph:
- The fact's `bill_rule` may also be `BILL1.NOTOTAL.v1` (`end_row` = the bill sheet's last content row) or `BILL1.NOHEADER.v1` (three nulls, no bill role, every non-empty sheet in scope with a non-bill role, no linked blocks, check (b) not applied).
- A `BILL1.v1` fact, and any fact whose schema, rule or agreement is wrong, is checked exactly as in v4.3.
- Everything else is v4.3; the route tests compare v4.4 with the frozen v4.3 on every 046g fixture and mutation.

### 4.5 `harness/SCOPE_READER_PROMPT_TEMPLATE.md` (pin changes)

Exact edits. Every other byte is unchanged.

1. **Line 1.** `(candidate 046g, FIELD_ROLES R59)` becomes `(candidate 046i, FIELD_ROLES R59)`.
2. **Bill sheet bullet.**
   - Replace "Exactly one sheet is the bill sheet." with "Exactly one sheet is the bill sheet, unless the workbook has no bill header (below)."
   - After "…explain in `doubts`.", append:

     > **No bill header (owner decision O72).** If no row the digest shows, on any sheet, has as the whole text of its cells (spaces ignored) at least five of these six: 項次; one of 項目及說明, 名稱, 品名 or 材料名稱; 單位; 數量; 單價; and 複價 or 金額, the workbook has no bill sheet. Set `bill_sheet_index` and `end_row` to null and give no sheet the role `bill`; the whole workbook goes to the generator (see **In scope**).
3. **End row bullet.** Before "If the digest does not let you fix the end row, …", insert:

   > **No total row (owner decision O72).** If no row below the bill sheet's header has 合計 or 總計 in its unit-price or amount column, the bill sheet has no total row: `end_row` is the bill sheet's last row with content (the last row listed under `last_rows` for that sheet), and R49 then ends the quoted range inside the sheet.
4. **In scope bullet.** Append:

   > **With no bill sheet** (no bill header, above), every sheet with content is in scope, whatever its role; a sheet the digest shows with 0 rows and 0 columns has no content and stays out of scope.
5. **Item 4, the sentence after the JSON.** Replace "and exactly the sheet you name as `bill_sheet_index` has role `bill`." with "and exactly the sheet you name as `bill_sheet_index` has role `bill` (no sheet has it when `bill_sheet_index` is null)."

**Why each edit is needed:**
- Without edit 3, a v3 reader sets `end_row` to null on a no-total sheet (or picks the last item line), and the case is held.
- Without edits 2 and 4, a reader on a whole workbook sets null and keeps the summary, resource and other sheets out of scope, and the case is held.
- The label set in edit 2 is BILL1's literal set, so a reader who sees 序號 or 品名規格 does not read them as the item-number and name labels and disagree with the tool. The reader still can disagree, which holds the case: that is O72's agreement requirement working.

### 4.6 Other harness files

- **`GENERATOR_PROMPT_TEMPLATE.md`.** Line 3 only: "(candidate 046g, from `research/guideline046_007/package/`)" becomes "(candidate 046i, from `research/guideline046_009/package/`)". The scoped-packet sentence on line 4 already covers a whole-workbook packet (only empty sheets are scoped out). The pin changes.
- **`EVALUATOR_BRIEF_TEMPLATE.md`.** Line 1 "under candidate 046g" becomes "under candidate 046i". In the scope-loss sentence of the evaluation notes, add: "On a whole-workbook packet (`bill_rule` `BILL1.NOHEADER.v1`) only empty sheets are scoped out and there is no end row, so there is no scope loss."
- **`README.md`** (from `d1d2735`):
  - Title and intro name 046i. The intro lists what 046i changes against 046g: the empty-sheet fix, the O72 cases (`scope_tool.py` v4, `scope_agree.py`, `make_scoped_inventory.py` basis, reader template), the templates naming 046i and `research/guideline046_009/package/`, and route v4.4.
  - Every command path becomes `research/guideline046_009/harness/…`.
  - Scope stage step 2: holds come "from several BILL1 candidates, from zero candidates outside the two O72 cases (FIELD_ROLES R59), or from an all-unpriced bill without an analysis sheet". Add one sentence on the two O72 outcomes.
  - Step 4: "route v4.4 rejects".
  - Validation record:
    - keep the v2 table and the v3 line;
    - fix the reviewer's nit: v3 differs from v2 "only on an inventory with an empty sheet (rows × columns = 0, no cell or view)";
    - add: "v4 (046i) differs from v3 only on an inventory above the threshold with no BILL1 candidate that meets one of the two O72 cases. Each study inventory has exactly one candidate, so v4 computes v3's values on them. This follows from the code; it was not re-run (study inventories are off-limits here)."
  - Admission notes: route v4.4, `cps046i-route.v4.4`.
- **`BUGFIX_EMPTY_SHEETS.md`** (from `d1d2735`):
  - First line: "Harness of candidate 046i. Developed in place in 046g's harness as work in progress, reviewed (ADMIT_WITH_FIXES), then moved into 046i; 046g was restored to its frozen bytes."
  - Paths become `research/guideline046_009/…`.
  - The pin table keeps the v2 and v3 hashes as history and adds one row: "046i: shipped in `scope_tool.py` v4 together with O72".
  - Note that the review's finding on R59 item 8 is addressed by D10.

### 4.7 Versions and identifiers

| Item | 046g | 046i |
|---|---|---|
| Candidate, folder | 046g, `research/guideline046_007` | 046i, `research/guideline046_009` |
| Package manifest | `bf06fae2…` | new |
| Route | `cps046g-route.v4.3` (`ba8414a0…`) | `cps046i-route.v4.4` |
| Scope tool | `cps046g-scope-tool.v2` (v3 was WIP only) | `cps046i-scope-tool.v4` |
| Bill rules in `bill_rule` | `BILL1.v1` | `BILL1.v1`, `BILL1.NOTOTAL.v1`, `BILL1.NOHEADER.v1` |
| `cps.scope-proposal.v1`, `cps.scope-digest.v1`, `cps.scope-reader-response.v1`, `cps.scope-decision.v1`, `cps.scope-hold.v1`, `cps.scope-fact.v1`, `cps.scoped-inventory-receipt.v1` | v1 | v1 (D8; key sets unchanged) |
| New proposal flag codes | none | `BILL1_NO_TOTAL_ROW`, `BILL1_NO_HEADER` |
| New refusal code | none | `PROPOSAL_BILL_RULE` (`scope_agree.py`; never expected) |
| Threshold | 2,500 | 2,500 |

### 4.8 Unchanged and why

| Component | Why it can stay |
|---|---|
| Runner v4 | It is path-generic (release `package.path`, `harness.path`). Every field it reads keeps its meaning (§1). |
| Builders, `render_views.py` | Empty sheets are handled in the harness (the reviewed decision). |
| `make_job_config.py`, `prepare_run.py`, freeze tools | They do not name the candidate and have no scope logic. |
| Writer v2.8.2 | It loads its own pinned v4.2 port. writer004 renders the carrier's `metadata.adapter` (the route version) as data in the workbook's identification rows; it does not validate it (design finding C4). Route v4.4's port is byte-identical. |
| Evaluator v4, aggregator v2 | Neither reads scope facts. The evaluator brief only lists the decision file for manual review. |

---

## 5. (d) Proof plan

All workbooks are invented. Every run is in a fresh scratch clone, outside the repository and outside the session scratchpad, with `python3 -I -B` as the runner uses it, LibreOffice for `.xls`, and the deps bundle.

### 5.1 Baselines and the comparison rule

**Baselines.**
- **B2:** 046g at `4c40004` (scope tool v2, route v4.3).
- **B3:** 046g plus the empty-sheet fix: the C2 tree, which is byte-equal to `d1d2735`'s five files (scope tool v3).
- **C:** 046i at C3, and again at C5.

**Comparison rule.** A pinned compare script, reusing the reviewer's tree comparer and extending its substitution list, compares output trees file by file. Every byte must be equal after only these substitutions:
- S1: `cps046g-scope-tool.v2` or `cps046g-scope-tool.v3` → `cps046i-scope-tool.v4`;
- S2: `cps046g-route.v4.3` → `cps046i-route.v4.4`;
- S3: `(candidate 046g)` → `(candidate 046i)` in the excerpt header, and `candidate 046g` → `candidate 046i` in a fact `basis`;
- S4: `route v4.3 rejects this fact` → `route v4.4 rejects this fact` (stand-in basis);
- S5: the sha256 of `scope_tool.py`, `scope_agree.py`, `make_scoped_inventory.py`, the route and `FIELD_ROLES.md`, and recursively the sha256 of any file that is equal under S1–S7;
- S6: timestamps (`frozen_utc` and runner record times);
- S7: in runner records only, the harness path `research/guideline046_007/harness` → `research/guideline046_009/harness`, and the package path likewise.

Nothing else may differ. B2 is compared only on inputs without empty sheets (B2 refuses the others), and B3 on all inputs.

### 5.2 Identity on invented workbooks without the new patterns

A workbook is **without the new patterns** when C's proposal has `bill.rule` `BILL1.v1`, or its status is `NOT_APPLIED`, and an independent check written in the compare script agrees that neither D2 nor D4 holds. The check is recomputed from the BILL1 per-sheet counts the tool records, as in the dry run's diagnostic. The classification of every input is printed, so no input silently moves between groups.

**Inputs:**
1. the 046g scope-stage suite's fixtures, except `no_total` (§5.3);
2. the empty-sheet suite's workbooks (`.xlsx` and `.xls`; small and large; with and without empty sheets);
3. the empty-sheet review's 24 base jobs and 72 with-empty jobs (8 layouts, 3 writer flavours). By construction all of these are without the new patterns: each bill has a 合計 in its price column, and the zero-candidate layouts (an unpriced bill with its 合計 row, so (b) holds and (c) fails) stay held as before;
4. the runner suite's invented small and large workbooks.

**Outputs compared (B3 against C; B2 against C where valid):**
- `SCOPE_PROPOSAL.json`, `SCOPE_DIGEST.json`, `SCOPE_RULES_EXCERPT.md` and the tool's stdout;
- `SCOPE_DECISION.json` or `SCOPE_HOLD.json` for each invented reader response: agreeing, each disagreement kind, stand-in, missing key, wrong digest. Each reader response is re-hashed per tree, because the digest hash differs by S1 and S5;
- the scoped `SOURCE_INVENTORY.json`, `SCOPED_INVENTORY_RECEIPT.json` and the `--verify` report;
- route `check-inventory` on the full and the scoped packet;
- route `check` and `convert` (reports, carriers, census ledgers, receipts) on every route-test fixture and mutation and on the package example.

**Pass:** 0 differences under §5.1.

**What this proves.** v4 = v3 = v2 apart from versions and hashes wherever O72 does not apply. The excerpt body is byte-identical, so the reader's and generator's rule text for R47b and R49–R51 did not move. Route v4.4 = v4.3 on every `BILL1.v1` fact, including the stand-in and malformed ones.

### 5.3 The new patterns (invented `.xlsx`, plus `.xls` by LibreOffice, through `make_job_config.py` and the builders as the runner runs them)

**No-total, positive cases. Expected: `PROPOSED`, rule `BILL1.NOTOTAL.v1`.**
- **NT1.** The 046g scope fixture with its 合計 cell removed (the old `no_total` HOLD fixture).
  - Expected: bill sheet 2, header row 2, `end_row` 10, `end_cell` null.
  - In-range lines: 5 (priced 3 at rows 3, 6 and 10; not estimated 1; unpriced 1).
  - `condition_i` false, so the analysis sheet is out of scope.
  - Flags include `BILL1_NO_TOTAL_ROW` and `NEAR_BILL1_CANDIDATE`.
- **NT2.** An unpriced bill with no total, plus an analysis sheet whose blocks link to its lines.
  - Expected: `condition_i` true; the analysis sheet is in scope with reason `analysis_i`.
- **NT3.** A signature line and a note below the last item, no total.
  - Expected: `end_row` = the note's row.
- **NT4.** NT1 with empty sheets (first, middle, last, hidden).
  - Expected: equal to NT1 after removing the empty sheets, as the empty-sheet suite checks.
- **NT5.** The last content row has content only beyond column J.
  - Expected: the digest's `last_rows` still names the row, with `more_cells_beyond_column_J`.

**No-total, negative cases.** NTx1–NTx4: `HOLD` `BILL1_CANDIDATES_NOT_ONE`, byte-equal to B3 under §5.1. NTx5–NTx7: NOTOTAL-specific holds (tool or reader), not compared with B3.
- **NTx1.** Two sheets, each with one all-six row and no total.
- **NTx2.** One sheet with two all-six rows (a repeated header) and no total.
- **NTx3.** A no-total all-six sheet plus a five-of-six row on another sheet (for example 總價 as the amount label).
- **NTx4.** An all-six sheet with a 合計 in its price column but no positive number: fails (c), not covered.
- **NTx5.** A no-total all-six sheet with no item-like line below the header. Expected: rule `BILL1.NOTOTAL.v1`, hold `NO_IN_RANGE_LINES`.
- **NTx6.** A no-total, all-unpriced bill and no analysis sheet. Expected: rule `BILL1.NOTOTAL.v1`, hold `R51_ALL_UNPRICED_WITHOUT_ANALYSIS_SHEET`.
- **NTx7.** A no-total sheet whose price column holds a variant 合計： (not exact). Expected: the tool proposes `BILL1.NOTOTAL.v1`; an invented reader that takes the variant row as the end row makes `scope_agree.py` hold on `end_row`. This is the designed safety net.

**Whole workbook, positive cases. Expected: `PROPOSED`, rule `BILL1.NOHEADER.v1`, three nulls.**
- **NH1.** A single sheet of analysis blocks only (工作項目 headings, 工料名稱 headers), above the threshold.
  - Expected: role `analysis`, in scope, `linked_analysis_blocks` 0.
- **NH2.** The A51 layout: a 序號/品名規格 list, a summary-like sheet, a resource sheet and a memo.
  - Expected: every sheet in scope with its computed role; `BILL1_NO_HEADER` flag.
- **NH3.** NH2 with an empty sheet and a hidden non-empty sheet.
  - Expected: the empty sheet is out of scope with the empty reason and no flag; the hidden sheet is in scope with `HIDDEN_SHEET`.

**Whole workbook, negative and boundary cases.**
- **NHx1.** Only a five-of-six header row. Expected: HOLD, byte-equal to B3.
- **NHx2.** NH1 below the threshold. Expected: `NOT_APPLIED`, byte-equal to B3, with rule `BILL1.v1` and bill null.

**Agreement (`scope_agree.py` with invented readers).**
- No-total:
  - agreeing reader: `FROZEN_AGREED`, admissible, fact `bill_rule` `BILL1.NOTOTAL.v1`;
  - reader `end_row` = last item line: HOLD `end_row`;
  - reader nulls: HOLD (bill sheet, end row, bill role).
- Whole workbook:
  - agreeing reader (nulls, every non-empty sheet in scope, no bill role): `FROZEN_AGREED`, fact `BILL1.NOHEADER.v1`;
  - reader names a bill sheet: HOLD;
  - reader leaves one non-empty sheet out: HOLD `in_scope`;
  - reader puts an empty sheet in: HOLD `in_scope`;
  - reader nulls with one role `bill`: HOLD `reader_bill_role`.
- Stand-in reader on either rule: `admissible` false, then the route rejects the packet (`R59_SCOPE_FACT_INVALID`, v4.3's detail).
- A hand-edited proposal with an unknown `bill.rule`: refused `PROPOSAL_BILL_RULE`.

**Scoped inventory.**
- No-total build: the other sheets are removed; `--verify` PASS; `check-inventory` PASS, `scope: applied`, `policy_checks: applied`.
- Whole-workbook build: every cell record and view is byte-identical to the full inventory, the view map is the identity, and the only difference is the appended fact; `--verify` PASS; `check-inventory` PASS `scope: applied`.

**Route v4.4 unit cases** (new fixtures from `make_fixtures.py`; existing fixtures untouched):
- valid no-total fact; valid whole-workbook fact;
- no-total with `end_row` one less than the last content row: MISMATCH;
- no-total with two bill roles: MISMATCH;
- whole-workbook with a non-null `bill_sheet_index`: INVALID;
- whole-workbook with role `bill`: MISMATCH;
- whole-workbook with a non-empty sheet out of scope: MISMATCH;
- whole-workbook with `linked_analysis_blocks` 1: MISMATCH;
- unknown `bill_rule`: INVALID with v4.3's detail;
- an O72 rule with the stand-in agreement: INVALID with v4.3's detail;
- on the whole-workbook packet, a response citing any sheet's cells passes, and one citing `context:scope` gives `R59_SCOPE_FACT_CITED`;
- on the no-total packet, a response citing the last content row passes.

**End to end.** Invented responses for the A50 and A51 packets: `check` PASS with `scope: applied`, `convert` carried, writer port parity (strict and relaxed classes as in 046g).

### 5.4 Suites (exact expectations)

- **Route** (`route_tests/run_route_tests.py`):
  - The 284 existing tests keep their names and checks. The version constant moves to v4.4 where a test asserts the current version.
  - The "v4.3 = frozen v4.2 without the fact" parity becomes two comparisons:
    - v4.4 = frozen v4.3 (046g's route, sha256 `ba8414a0…`, read from `research/guideline046_007` at the release commit) on every fixture and mutation, with and without `context:scope`, apart from the version string;
    - the port section byte-identical to v4.2's, kept.
  - Plus the new `v44_*` tests of §5.3.
  - Pass: all. The new total is recorded.
- **Scope stage** (`run_scope_stage_tests.py`):
  - 61 of the 62 checks keep their names and expectations.
  - `tool_holds_zero_bill1_candidates` is re-specified: its `no_total` fixture is NT1, so it becomes `tool_no_total_scopes_to_last_content_row` with NT1's expected values.
  - A new `tool_holds_zero_bill1_candidates_five_of_six` uses NHx1 and keeps the zero-candidate hold covered.
  - Plus the §5.3 tool, agreement and build cases.
  - Pass: all. Report "62 existing (1 re-specified by design) + N new".
- **Empty-sheet** (`run_empty_sheet_tests.py`):
  - 64 existing checks; the one version assertion becomes `cps046i-scope-tool.v4`.
  - Plus NT4 and NH3 in both formats.
  - Pass: all.
- **Runner** (`deploy/run/test_cps_job.py`, 249 tests). The suite is pinned by the runner admission and hard-codes `research/guideline046_007` on 7 lines (29, 30, 35, 254, 255, 666, 671). Run it twice:
  - (i) **unmodified**, at the release commit, against the restored 046g: 249/249. This shows that the restored folder and the runner are as admitted;
  - (ii) **from a scratch clone** where those 7 lines are substituted to `research/guideline046_009` and committed locally (never pushed), because the suite refuses a dirty tree: 249/249.

  Record the derived file's sha256 and its exact 7-line diff in `REVIEW_046i.md`. No runner test uses a workbook without a total, so (ii) exercises only the unchanged v1 path through the 046i harness.
- **Export self-test:** not needed. The writer and its port are unchanged.

### 5.5 Runner-level checks (scratch driver, as in the empty-sheet fix)

Real runner v4 `prepare`, `scope-finish` and `finish`, with `render_views` included, on invented NT1, NT2, NH1, NH2 and NH3 (`.xlsx` and `.xls`):
- `prepare`: `NEXT: SCOPE_READER`.
- `scope-finish` with an agreeing invented reader: `NEXT: GENERATE`, `check_inventory_scoped` PASS `scope: applied`.
- `finish` with the matching invented A50- and A51-style responses: route check PASS, `convert` carried, writer, saved QA.
- A disagreeing reader gives `NEXT: OWNER_DECISION`.
- The negatives NTx1–NTx4 and NHx1 give `prepare` `OWNER_DECISION` with `BILL1_CANDIDATES_NOT_ONE`.
- The recorded facts for the v1 workbooks equal B3's under §5.1.

### 5.6 Deterministic structure-only re-run on the qualification inputs (pre-registered)

Before the release, re-run the same no-AI prepare dry run with the C5 harness. It records codes, sheet indexes and counts only, and writes nothing to the repository.

**Expectations, written into `DECISIONS_046i.md` before the run:**
- the jobs that reached GENERATE or SCOPE_READER in the 046g dry run reach them again with the same facts under §5.1;
- three of the five held jobs reach SCOPE_READER with `BILL1.NOTOTAL.v1`;
- one reaches SCOPE_READER with `BILL1.NOHEADER.v1`;
- one stays `OWNER_DECISION` with `BILL1_CANDIDATES_NOT_ONE`, unless the owner rules otherwise (§7);
- the rehearsal jobs are unchanged.

A deviation goes to the owner as a finding. It never changes the rule after the run. This is a structure-only check of a pre-declared rule. No answer is involved.

**The empty-sheet review's structure check.** The empty sheets of the sources that have them must be checked for drawing parts: xlsx `xl/worksheets/_rels/sheetN.xml.rels`, xls MSODRAWING records. The record must show none before the exclusion is relied on.

### 5.7 Review, freeze, rehearsal

1. **Independent review** in a fresh context, of C3 against 046g and the C2 baseline. Inputs: the repository and this design without the private annex.
   - Scope:
     - O72 fidelity (D1–D10, RQ1–RQ7 in §7);
     - the R59 text;
     - the tool, agree, scoped-inventory and route changes;
     - the reader template;
     - the proof outputs of §5.2–§5.5;
     - public hygiene.
   - Verdict and findings go into `REVIEW_046i.md`. Fixes are applied verbatim (C4), the suites are re-run, and a delta review follows if the reviewer asks.
2. **Freeze (C5).** Regenerate the manifest, set the review status line, add `CURRENT_STATE.json` `candidate_046i`, and record the harness and route-test hash table.
3. **Release, admission and toolkit re-pin** (§6.2–§6.4). Then the toolkit suites:
   - `run_b2_tests --slow`;
   - `run_b1_tests --with-runner --real-audit`, with the nc1 trigger replaced (§6.4).
4. **Re-run rehearsal (O72).** The rehearsal root re-runs on the new release; its four jobs take only unchanged paths. To exercise the new rule with real fresh-context readers, add a probe root with two invented large workbooks, NT1 and NH2, under invented case ids from the toolkit's invented range. Run them through the scope reader and the generator. This is development evidence only and earns no credit. The main session decides whether to add it (§7, RQ7).

---

## 6. (e) Downstream pins and texts for the main session

### 6.1 Repository

| Where | Change |
|---|---|
| `research/guideline046_007/**` | Restored (C0); no pin moves. |
| `research/guideline046_009/**` | New. Files whose hashes change: manifest; route; `scope_tool.py`, `scope_agree.py`, `make_scoped_inventory.py`; both prompt templates; evaluator brief; README; FIELD_ROLES; guideline; three contracts and checklist; synthetic cases. Byte-identical but at new paths: `make_job_config.py` (`4913b87b…`), `prepare_run.py` (`8a1bf4df…`), `freeze_admission.py` (`89c29f78…`), `freeze_outputs.py`, `make_release.py`, `audit_transcript.py`, `fullpath_check.py`, the 9 unchanged package resources. |
| `CURRENT_STATE.json` | `candidate_046i`. The O72 entry gains one sentence: "with no header row at all, every non-empty sheet is in scope and the packet, the full inventory plus a whole-workbook `context:scope`, is read as unscoped; runner v4 does not allow NOT_APPLIED above the threshold". Add the one-pool-case finding and the owner's ruling. The qualification-progress entry names 046i. Change the release-commit mention (`4c40004`) when the new release exists. |
| `docs/handoff/DEPLOYMENT_MODEL.md`, O72 section | The same realisation sentence. "Four have a unique bill-sheet header row" becomes "three have a unique bill-sheet header row without a total row; in one, two sheets each carry such a header, which O72 does not cover". |
| `docs/handoff/QUALIFICATION_HERE_PLAN.md` | §2: "Frozen candidate 046i (package manifest `…`, route v4.4)". §5.9: release commit, generator and scope-reader template hashes, manifest and route hashes. Replace "No pinned file has changed since the runner admission (`3dfcb16`)" with "The runner, writer, evaluator, aggregator and source-prep files are unchanged since the runner admission; the harness is 046i's". Update the scope-reader and context counts (four more scope-reader contexts per reader if all four O72 cases reach the reader), and the open-window restart-risk figures that depend on them. §5.7 is unchanged; a held case is still the empty carrier. |
| `docs/handoff/CURRENT_STATUS.md` | Candidate line. |
| `AGENTS.md` | **Do not edit.** Its sha256 is pinned as injected context; an edit makes the driver refuse every launch until it is re-pinned. |
| `deploy/run/test_cps_job.py`, `RUN_JOB_COMMANDS.md`, `RELEASE.example.json` | **Unchanged.** They are pinned by the runner admission. They name `research/guideline046_007` as test and example paths; this is stale but admitted, and noted in `REVIEW_046i.md`. |
| `deploy/vm2/ADMISSION_VM_HELPER_V21.json` | Unchanged: a frozen record of a helper that is not admitted. A future Dot release on 046i ("the same rule applies in everyday use") needs a VM admission that pins 046i's templates. |
| `PUBLICATION_MANIFEST.json` | Unchanged. It is the 2026-11-03 publication snapshot and is not kept per candidate. |

### 6.2 Release

- **Release commit:** the commit after C6 that holds the restored 046g, the frozen 046i and the docs. It must be on the public branch. Move the release clone to it.
- **`RELEASE.json`:**
  - `repository.commit` = the new commit;
  - `package.path` `research/guideline046_009/package`;
  - `package.manifest_sha256` new;
  - `harness.path` `research/guideline046_009/harness`;
  - `pinned_files_sha256`: the 14 executed files. The 7 harness keys get the new paths; `scope_tool.py`, `scope_agree.py`, `make_scoped_inventory.py` and both templates get new values. `make_job_config.py` and `prepare_run.py` keep theirs. `cps_job.py`, the visual template and the 5 source-prep files are unchanged.
  - `meaning` names 046i.
- No other field changes: writer admission, checker node, tables, qualification block.

### 6.3 Qualification admission

Frozen fresh, before the ledger's first entry (none exists yet), with `research/guideline046_009/harness/freeze_admission.py`. The bytes are identical to 046g's, so the freezer pin `89c29f78…` holds. Pins:
- the package manifest and route (new);
- the 7 harness labels at the new paths;
- the 5 source-prep files, writer admission, evaluator, aggregator and `JOBS.json`: unchanged values;
- per-job pins: unchanged unless a toolkit-generated per-job file embeds the candidate path or commit. Regenerate and compare; re-pin any that differs.

Write the freeze record again.

### 6.4 Toolkit (`$TOOLS`)

| File | Change |
|---|---|
| `qual_here.py` | `G_PACKAGE`; `RUNNER_EXECUTED` harness paths; `REPO_EXPECTED` (7 harness keys with new paths; new hashes for `scope_tool.py`, `scope_agree.py`, `make_scoped_inventory.py` and both templates; `FREEZER_REL` path, optional but recommended for consistency, with the same `FREEZER_SHA`); `RELEASE_COMMIT`; `PACKAGE_MANIFEST_SHA`; the rehearsal-plan `candidate` string; the release `meaning` ("frozen 046i") and `harness.path`. |
| `isolation_audit.py` | The generator role's named repository folder becomes `research/guideline046_009/package/`. It must match the generator template's line 3. |
| `eval/eval_next.py`, `eval/EVAL_PLAN_TEMPLATE.json` | Package path; route path and sha256. |
| `eval/briefs/*` | "under candidate 046i"; the private copy of the evaluator brief re-derived from 046i's template with the same G18 changes, including the whole-workbook scope-loss sentence. |
| `tests/run_b1_tests.py`, `tests/run_b2_tests.py`, `tests/test_driver_fixtures.py` | Release commit constants and harness paths. |
| `tests/test_bugfix_nocontext.py` | Replace nc1's trigger, as the empty-sheet review required. The trigger relied on the empty-sheet bug, which 046i fixes. Use the reviewer's all-empty workbook, which stops `prepare` at `check-inventory` (`WRITER_SOURCE_VIEWS_REQUIRED`), or keep only nc3. |
| `DESIGN.md` | Commit, paths and candidate; the no-context audit paragraph (review nit). |
| `TOOLKIT_MANIFEST*.json`, `DRIVER_CONFIG` of every root | Regenerated or re-pinned: `qual_here.py`, `isolation_audit.py`, the tests, and `tool_sha256` of `isolation_audit.py` in each root. First confirm where the earlier unexplained rewrite of `TOOLKIT_MANIFEST_P1B.json` came from (review nit). |
| Private operator procedure (`r3c`) | Becomes `r3d`, with commit, candidate and paths. |

### 6.5 What the runner prints that changes in practice

- For the O72 cases, `prepare` now ends with `NEXT: SCOPE_READER` instead of `OWNER_DECISION`.
- The runner facts carry `bill_sheet_index` and `end_row` null for a whole workbook, and the two new flag codes.

Nothing in the runner, the ledger or the freeze reads those values.

---

## 7. Questions for the owner and for the reviewer

- **OWNER-1, required before freeze.** The pool case with two sheets, each carrying a unique six-label header and no total row, stays held under O72 as worded. The gate then fails with certainty (an empty carrier on a pool run). The options:
  - **(a) Keep the hold.** The qualification can only fail; it is then informative only.
  - **(b) No unique header means whole workbook.** Zero candidates and two or more no-total header sheets: the whole workbook goes to the generator, as `BILL1.NOHEADER.v1` does.
    - Small change: one more condition in D4, one more reason, and the reader template sentence.
    - That workbook is several times the size at which the 046g study found the census impossible for one reader, so the run would probably fail anyway.
  - **(c) Several bill sheets.** Every such sheet in scope as a bill sheet, each to its last row, with R51 over all their lines.
    - This changes R49's "the detailed bill sheet" and the fact (a list of bill sheets), and needs creator-practice evidence from exposed cases.
    - It is a semantic change that needs its own source-only study and review.
  - **(d) The pool.** Any change to the pool is the owner's call. O72 states that the pool is unchanged.

  If the owner picks (b) or (c), it goes into 046i before the review.
- **RQ1.** D2's clause "no other sheet has a five-of-six row" is narrower than O72's literal "unique bill-sheet header". It covers all three no-total cases in the record. Keep it?
- **RQ2.** D3 drops (c) for the no-total case: an unpriced no-total bill goes through R51. Agree?
- **RQ3.** D1: the O72 cases only above the threshold. Agree?
- **RQ4.** D8: schema ids kept at `.v1`, with value domains extended, rather than bumped. Agree?
- **RQ5.** The reader template's literal label list (§4.5). Is it clear enough for a fresh reader?
- **RQ6.** A whole-workbook packet can be large. Accept the risk, as O72 implies?
- **RQ7.** Add the invented NT1 and NH2 probe root to the re-run rehearsal (§5.7, step 4)?

## 8. Risks

- **A fresh reader may still disagree on the new patterns.** For example, it may pick the last item line, or read a header variant as a header. The case is then held: O72's agreement requirement working. The re-run rehearsal's probe measures how often.
- **Whole-workbook packets are large.** The generator may not finish the census. This is accepted under O72; it is not a pipeline defect.
- **A no-total sheet's last row with content may be a stray cell far below the bill.** The scope then keeps the whole sheet, and R49 still ends the range at the last item line. Only census work grows, unless an item-like priced or not-estimated row lies below the R49 range: it then makes R51 condition (i) false and scopes the analysis sheet out although the quoted range is all unpriced; only the reader's disagreement catches this (§9, finding R3).
- **The drawing-only sheet limit (empty-sheet review).** It is unchanged. Do the structure check of §5.6.

---

---

## 9. Addendum: the build of 2026-11-14 and the design critique

The build followed §2.2 to C3: `research/guideline046_007` restored to its bytes at `4c40004` (C0, the diff is empty), the folder copied to `research/guideline046_009` (C1, 36 files byte-equal), the reviewed work-in-progress files at `d1d2735` (C2, hashes as in §2.2), then §3 and §4 with the critique applied (C3). The main session commits; nothing was released, reviewed or frozen. `DECISIONS_046i.md` records the decisions (D1–D13), the owner and reviewer questions and, finding by finding, where each critique finding was applied.

### 9.1 Changes to the earlier sections

Where these and §0–§8 disagree, these govern.
- **R59 (§3.3).** Item 2's no-total text replaces the rest of the item: the bill sheet is kept, R49 ends the quoted range as on an unscoped packet, the cells after it take their unscoped roles, and the tool's exact test is stated (finding R1). Item 3's exception follows finding R2. Item 9 says "the scope stage fixes no bill sheet and no end row", adds that the roles and reasons in the fact are labels, and says "the bill sheet, if any" (R4, R6, R14). Item 8 says an empty sheet has no cell or view in the inventory (R7). The intro, item 1 and the In-scope and Out-of-scope bullets name the bill rules (R12). The design-decision bullet records the reading of "that sheet" (R10), the non-monotonic boundaries and the analysis-block-header limit (R11), and the replaced *Reader agreement* sub-bullets (R8); *Limits* records the priced-tail risk (R3) and drawing-only sheets (R7).
- **Other package texts (§3.5).** The OUTPUT_CONTRACT insertion is in step 2, "Find the quoted range" (R12); REVIEW_CHECKLIST 15a follows R1, R2, R6 and R12.
- **Scope tool (§4.1).** Every bill-rule id comes from the loaded route (C7). The no-total reason reads "no cell reading exactly 合計 or 總計 below it in a price column". The whole-workbook reason is neutral: "whole workbook: no sheet has a BILL1 header row (five or six of its labels), so every sheet except an empty one is in scope and the packet is read as an unscoped packet; the role is a label, not an R49 decision (R59 item 9, O72)" (R6). Under `BILL1.NOTOTAL.v1` the no-total sheet's digest `counts` also carry `priced_or_not_estimated_line_rows` (the first 20 rows, ascending) and `last_unpriced_no_status_line_row` (lines with other price text count as such, as for the R51 conditions), and the sheet carries `priced_or_not_estimated_lines_tail`: the last 3 such lines, each with 2 rows of context above it (R3).
- **`scope_agree.py` (§4.2)** reads the rule ids from the route (C7). **`make_scoped_inventory.py` (§4.3)**: the whole-workbook basis says "the two agreed that no sheet has a bill header row, so the scope stage fixed no bill sheet and no end row, and that every sheet except an empty one (rows x columns = 0) is in scope" and adds that the roles are labels (R4, C5); the no-total basis states the exact test and that R49 decides where the range ends inside the sheet (R1).
- **Route (§4.4).** `SCOPE_O72_RULES` and `SCOPE_BILL_RULES` follow `SCOPE_BILL_RULE`, outside the writer-port section; the `CONTENT_ROLES` line is byte-identical; a route test checks both against v4.3 (C7).
- **Reader template (§4.5).** Edit 2: the bill sheet has "its item lines below it (normally priced; when every line has no price and no status it is still the bill sheet, and R51 takes the rows from the analysis sheet)" (R5); a sheet whose rows continue the bill sheet's lines or carry its total makes the reader set the bill sheet null (R13); the label sentence defines "carries" with the whitespace rule and lists words that are not labels, and the reader is told that the scope stage fixes no bill sheet (R4, R9). Edit 3 begins with `price_column_total_rows_count` 0 and adds the priced-tail sentence (R3, R9). Edit 4: "every sheet whose rows × columns is above 0 is in scope, whatever its role and even if the digest shows no content cell on it; only a sheet the digest shows with 0 rows or 0 columns stays out of scope" (R7, C5).
- **Evaluator brief (§4.6).** Besides the label and the scope-loss sentence, the manual-review policy path names `research/guideline046_009/package/` (D13); the scope-loss sentence also covers `BILL1.NOTOTAL.v1`.
- **§5.3.** NTx1–NTx4 are `HOLD BILL1_CANDIDATES_NOT_ONE`, byte-equal to B3 under §5.1; NTx5–NTx7 are NOTOTAL-specific holds, not compared with B3 (R15). New invented cases: NT6, a priced item-like line below the signature line under an all-unpriced range (R3); NH4, a styled-blank sheet (C5); NT2 with a reader that names the unpriced bill sheet and the analysis sheet in scope (R5).
- **§8, third risk**, as amended in place (R3).

### 9.2 Comparison classes for runner-level records (finding C4)

Added to §5.1 before any runner-level comparison:
- **S8, the two filled prompt files** (`scope/SCOPE_READER_PROMPT.md`, `run/GENERATOR_PROMPT.md`): equal after applying the B3-to-C template diff (the exact 046i template edits). Once equal, their sha256 count as S5-equal, and so do `PACKET_PINS.json` and its ledger and record hashes.
- **S9, writer and QA outputs:** `carrier.json`, `ADAPTER_RECEIPT.json`, `CENSUS_LEDGER.json` and the expected saved values compared under S2; the saved xlsx compared after unzipping, with S2 applied to its XML parts. PDF and PNG bytes and file sizes are an exempt class, with saved-QA status PASS required on both sides.
- **S10:** job-root temporary paths.

§5.5's last bullet reads "the recorded facts for the v1 workbooks equal B3's under S1–S10", and `REVIEW_046i.md` lists the classes and their counts. This build compared tool-level outputs (S1–S7); its runner-level check of the O72 cases (§9.4) asserts outcomes, not identity.

### 9.3 Downstream steps added by the critique (for the main session; not files of this candidate)

- **C1, toolkit tests.** Besides the tests named in §6.4: the audit-role test's named package `FIELD_ROLES.md` path; every harness and package path in the driver-fixture test (package manifest, route, release package path and manifest, harness), not only the harness path; the stage-0 evaluation test's package path; optionally the cosmetic `046g` strings. Then `run_b2_tests` (including the audit-role test) and `run_b1_tests --with-runner` pass on the re-pinned toolkit before any root is built.
- **C2, roots.** The used rehearsal root cannot re-run in place. Move it to an archive path, read-only, as the 046g record (ledger, evidence and job folders kept, never deleted); rebuild it at its standard path: restage from the data-track kit and check it against the rehearsal stage record; regenerate the rehearsal evaluation plan from the updated template (route path and sha256 of 046i); then make-driver-config, make-admission-config (rehearsal profile), make-release-fields, session-check, finalize-root, freeze-admission, make-release. On the probe roots re-make the driver config, the admission config and the release fields with `--replace` (allowed while no admission or driver ledger exists). In every driver config re-pin every edited always-pinned toolkit file (the driver, the isolation audit and the evaluation driver), not only the isolation audit. Re-take the session-check references after the release commit.
- **C3, scripts.** Every script that runs a candidate takes the candidate folder as an argument (B2: `research/guideline046_007` at `4c40004`; B3: the C2 tree; C: `research/guideline046_009`) and records the sha256 of the scope tool, `scope_agree.py`, `make_scoped_inventory.py` and the route. The §5.6 record is read only if its scope-tool sha256 equals the value frozen at C5 (pre-registered in `DECISIONS_046i.md`).
- **C6, RQ7.** The toolkit cannot stage invented sources in a probe root as it stands. Either run the probe through a scratch runner driver with manually launched fresh contexts, as development evidence outside the toolkit, or extend the toolkit (a probe profile and root, a stage record for invented sources, invented case ids confirmed absent from the jobs list) and re-test and re-pin it before any root is admitted.

### 9.4 Proof run by the build (2026-11-14, invented data only, outside the repository)

All on 2026-11-14, invented data only, work folders outside the repository. The runner suite ran from a local clone.

| Run | Result | Notes |
|---|---|---|
| Route suite `route_tests/run_route_tests.py` (writer004 parity, node 22) | 317/317 | The 284 existing tests keep their names and checks (the current-version constant is v4.4; the v4.3-vs-v4.2 comparison without `context:scope` now runs on the current route and leaves out the v4.4 mutations too). New: 15 `v44_*` mutations and 18 tests: the no-total and whole-workbook packets (check-inventory, check, convert, writer004 on the placeholder copy, strict-port class); each new fact problem with its message; v4.3's detail kept for a stand-in agreement or an unknown rule; no `R59_ROW_BELOW_END_ROW` on a whole workbook; v4.4 equal to the frozen v4.3 (`ba8414a0…`, read from `research/guideline046_007`) on all 155 fixture and mutation pairs v4.3 knows, 44 of them with `context:scope` (check, check-inventory, and convert on 8 pairs: carriers, census ledgers, receipts) apart from the version string; v4.3 rejects both O72 facts; the writer-port section and the `CONTENT_ROLES` line equal v4.3's. |
| Scope-stage suite `route_tests/run_scope_stage_tests.py` | 92/92 | 62 existing checks: 61 unchanged and `tool_holds_zero_bill1_candidates` re-specified by design as `tool_no_total_scopes_to_last_content_row` (its fixture is O72's first pattern: bill sheet 2, header row 2, end row 10, end cell null, 5 lines, 3 priced at rows 3, 6 and 10, condition (i) false, flags `BILL1_NO_TOTAL_ROW` and `NEAR_BILL1_CANDIDATE`). New: `tool_holds_zero_bill1_candidates_five_of_six` and 29 `o72_*` checks (digest additions, reasons and flags, agreement and each disagreement, refusals of hand-edited proposals, invented NT6, the whole-workbook pipeline with an identity projection, stand-in decisions rejected by the route, determinism, below-threshold NOT_APPLIED under `BILL1.v1`). |
| Empty-sheet suite `route_tests/run_empty_sheet_tests.py` | 106/106 | 64 existing checks (version assertion `cps046i-scope-tool.v4`) and 42 new: NT4 and NH3, each in .xlsx and .xls, with and without empty sheets, equal after removing the empty sheets (proposal, digest, excerpt, scope fact, scoped packet, verify, check-inventory). |
| O72 suite `route_tests/run_o72_tests.py` (new) | 86/86 | 43 checks in each format: NT1–NT3, NT5, NT6, NTx1–NTx7, NH1, NH2, NH2 with an empty sheet, NH4, NHx1, NHx2 through `make_job_config.py` and the real builders, then the agreement, build, verify and route checks of §5.3 and of findings R3, R5 and C5. |
| Identity comparison (§5.2; build script outside the repository, each tree named by argument) | 0 differences | 150 invented inputs (the 046g scope-stage fixtures except `no_total`: 8; the empty-sheet suite's workbooks: 8; the empty-sheet review's 40 workbooks in 3 writer flavours: 120; the runner suite's small and large workbooks: 2; the O72 negatives NTx1–NTx4, NHx1, NHx2 in two formats: 12), each classified by an independent BILL1 label census: none has a new pattern, and C's proposals are 71 `PROPOSED`, 23 `NOT_APPLIED` and 56 `HOLD`, all under `BILL1.v1`. For every input: proposal, digest, excerpt, tool output, eight invented reader responses (agreeing, end row, other bill sheet, flag flip, null bill sheet, stand-in, missing key, wrong digest) with their decisions or holds, the scoped packets and receipts of the agreeing and stand-in decisions, `--verify`, and check-inventory on the full and scoped packets; and route check, check-inventory and convert on 155 route-test pairs and the package example. B3 (the C2 tree) against C: 7,113 common files, 3,917 byte-identical, 3,196 equal under S1–S7, 0 different, none missing. B2 (046g) against C, on the 50 inputs without empty sheets and the route pairs: 3,349 files, 2,039 byte-identical, 1,310 equal under S1–S7, 0 different. A negative control (a changed end row and a changed candidate label in one copied tree) was detected. |
| Runner suite `deploy/run/test_cps_job.py`, run (i) | 249/249 (348.9 s) | Unmodified, from a clone at the work-in-progress commit holding the restored 046g and the 046i build; it exercises the restored 046g as admitted. |
| Runner suite, run (ii) | 249/249 (342.3 s) | The same clone with the 7 lines that name `research/guideline046_007` (29, 30, 35, 254, 255, 666, 671) substituted to `research/guideline046_009`, committed locally (never pushed), because the suite refuses a dirty tree. Derived file sha256 `999a6b1d9e142b7179fe1e8f5f2154825305e00ad10c5d2a82c300856bc397b8` (the admitted file is `c8fcd491…`). No runner test uses an O72 pattern, so this exercises the unchanged `BILL1.v1` path through the 046i harness. |
| Runner-level check of the O72 cases (§5.5; scratch driver outside the repository, on the run (ii) clone) | 48/48 | Real runner v4 `prepare` and `scope-finish` (`render_views.py` included) on invented NT1, NT2, NH1, NH2, NH4 (.xlsx and .xls): `prepare` ends `NEXT: SCOPE_READER` with the bill rule's facts (`bill_sheet_index` and `end_row` null and `BILL1_NO_HEADER` for a whole workbook), `scope-finish` with an agreeing invented reader ends `NEXT: GENERATE` with check-inventory on the scoped packet `scope: applied` and `--verify` PASS, a disagreeing reader ends `NEXT: OWNER_DECISION`; NTx1, NTx5, NTx6 and NHx1 end `prepare` with `OWNER_DECISION` and their hold code. `finish` was not run on the O72 packets (no invented full response for a packet of that size); the route suite's A50 and A51 packets cover check and convert. |

Not run by the build: the toolkit suites (they need the re-pinned toolkit, §6.4), the structure-only re-run on the qualification inputs (§5.6, after the freeze), and any fresh-context reader or generator.


## 10. Addendum: the review fix round (2026-11-14)

Two independent reviews (semantic and code) of the build as committed at `7566eb9` returned ADMIT_WITH_FIXES. `DECISIONS_046i.md` lists each finding (S1–S8, F1–F7), where it was applied, and the fix round's proof. Where this section and §0–§9 disagree, this section governs.
- **Reader template (§4.5, §9.1).** The continuation sentence of finding R13 now applies only when the bill sheet has no total row, and only to a sheet without a header of its own that continues its item lines in the same columns; a summary sheet that lists section totals or the grand total is not a continuation (S1, F4). The no-bill-header paragraph counts only the labels shown and draws no conclusion from a row with cells beyond column J (S6). The no-total trigger also covers listed block totals when the count equals the rows listed (S6). With no analysis sheet, a priced tail makes the reader set `end_row` null (F2).
- **R59 (§3.3, §9.1).** Item 2's no-total paragraph states where the range starts, the item-6 exception for blocks after the range and the `limitations` record of a contradiction (S5); item 3, the OUTPUT_CONTRACT census table and the guideline status paragraph name the item-6 exception. *Limits* says no deterministic hold covers the priced tail and names OWNER-4 (F2). The *Reader agreement* sub-bullet names the block total (S6). The *In scope* design bullet names no case id (F6).
- **`make_scoped_inventory.py` (§4.3).** The no-total basis says what the tool found and what the tool and the reader agreed on (F7).
- **§5.3.** New invented cases: NT7 (NT6 without an analysis sheet), NTB (a block total in the price column) and V1J (a `BILL1.v1` bill with its price columns beyond column J); the scope-stage suite adds the priced-tail variant without an analysis sheet.
- **§5.7, §7.** The owner's rulings on OWNER-1, OWNER-2 and OWNER-4, and the RQ7 probe with real fresh-context readers and at least one generator run plus `finish` on a whole-workbook packet, are required before the freeze (S2, S3, S4, F1, F2, F3). OWNER-3 and OWNER-5 go to the owner before any run on those patterns (S8).