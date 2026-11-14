# Candidate 046i: decisions (2026-11-14)

Status: **build record, not frozen.** Written in the maintainer session for the qualification here (owner decision O64) while candidate 046i was built, before any 046i generation, and amended in the review fix round of 2026-11-14 (last sections). The freeze and the release follow (`DESIGN_046i.md` §5.7, §6, §10). This file follows `research/guideline046_002/DECISIONS_046b.md`.

046i is the frozen 046g (`research/guideline046_007/`, release commit `4c40004`, package manifest `bf06fae2…`) plus the reviewed empty-sheet fix and owner decision O72. 046g itself was restored to its frozen bytes; the work-in-progress fix moved here.

## Owner decision O72 (2026-11-14, verbatim)

> A narrow rule change: a unique bill-sheet header without a total row scopes to that sheet down to its last row; with no header at all, the whole workbook goes to the generator. The scope reader still has to agree. It gets an independent review, a re-freeze and a re-run rehearsal; the same rule applies in everyday use.

## How O72 is realised under runner v4

Runner v4 (`deploy/run/cps_job.py`, admitted, unchanged) stops `prepare` with `SCOPE_COUNT_INCONSISTENT` unless the scope proposal is `NOT_APPLIED` exactly when the full inventory has at most 2,500 literal or cached-formula content cells. After `scope-finish`, `check-inventory` and `finish` require `scope: applied`. So "the whole workbook goes to the generator" cannot be an unscoped packet above the threshold. It is a **whole-workbook scoped packet**: status `PROPOSED`, a fresh scope reader, `scope-finish`; every sheet except an empty one is in scope, no cell is removed, no view is renumbered, and the packet is the full inventory plus one `context:scope` fact (`bill_rule` `BILL1.NOHEADER.v1`, bill sheet, header row and end row null). FIELD_ROLES R59 item 9 tells the generator to read it exactly as an unscoped packet.

O72's "scopes to that sheet down to its last row" is read as "that sheet is the bill sheet, and the scope keeps it down to its last row with content". R59's existing R51 rule still brings in the analysis sheets when every line of the range has no price and no status (D3). This reading goes beyond O72's literal words and needs the owner's ruling before the freeze (OWNER-2); the ruling is recorded here when given.

O72's coverage is narrower than the first O72 records say. Of the four structure-only holds whose header was found, three have a unique bill-sheet header row without a total row; in the fourth, two sheets each carry such a header, which O72 ("a unique bill-sheet header") does not cover, so that case stays held (OWNER-1). The O72 records in `CURRENT_STATE.json` and `docs/handoff/DEPLOYMENT_MODEL.md` and the qualification brief said "four have a unique bill-sheet header row"; the main session corrects them (review findings S3, F1).

## Decisions

| # | Decision | Reason |
|---|---|---|
| D1 | The O72 cases are considered only when the stage applies (more than 2,500 literal or cached-formula content cells) and no sheet is a BILL1.v1 candidate. At or below the threshold the scope tool computes exactly what v3 computes. | Below the threshold every sheet is already in scope; a small workbook's proposal and the runner's facts stay identical even if it shows one of the patterns. |
| D2 | **No total row, `BILL1.NOTOTAL.v1`.** No BILL1.v1 candidate; exactly one sheet S has a row carrying all six header labels; S has exactly one such row (BILL1 (a)); no other sheet has a row carrying five of the six; BILL1 (b) fails on S (no cell below the header in its 單價 or 複價 column, 金額 when the header has no 複價, reads exactly 合計 or 總計). S is the bill sheet with (a)'s header row and price columns, and the end row is S's last row with content. | O72's "a unique bill-sheet header without a total row". The five-of-six clause is the narrow reading of "unique": a five-of-six row elsewhere is BILL1's known vocabulary-variant failure, possibly a second bill (RQ1). |
| D3 | BILL1 (c) (a positive number in a price column) is **not** required under `BILL1.NOTOTAL.v1`. "That sheet" in O72 is read as "that sheet is the bill sheet": R59's existing R51 rule still brings in every analysis sheet when every in-range line has no price and no status. | O72 names no price condition, and an unpriced bill without a total would otherwise give no rows. This goes beyond O72's literal words: on an all-unpriced no-total bill the scoped packet holds the bill sheet and the analysis sheets, not the bill sheet alone (OWNER-2). A sheet that has a total row but fails (c) is not covered by O72 and still holds. |
| D4 | **No header, `BILL1.NOHEADER.v1`.** No BILL1.v1 candidate, and no row of any sheet carries five or all six labels. The scope stage fixes no bill sheet and no end row (no sheet has a BILL1 header row); every sheet except an empty one is in scope with the role the tool computes (never `bill`), and the generator finds the bill sheet, if any, by R49. | O72's "no header at all". A five-of-six row is a header-like row, so it is not "no header". "No BILL1 header row" is not "no bill sheet": a priced list headed 序號/品名規格 has a bill sheet that BILL1's labels miss (design finding R4). |
| D5 | Every other workbook keeps its v3 outcome, including every hold: two or more BILL1.v1 candidates; zero candidates with two or more sheets carrying an all-six row; one sheet with two all-six rows; an all-six sheet plus a five-of-six row on another sheet (a five-of-six row also counts when it is an analysis block header that carries 項次: a known coverage limit, the case is held, never wrongly scoped); an all-six sheet whose price column has an exact total but which fails (c); only five-of-six rows; `NO_IN_RANGE_LINES`; `R51_ALL_UNPRICED_WITHOUT_ANALYSIS_SHEET`. | O72 ("narrow"). Hold codes and notes are unchanged. Two boundaries are non-monotonic and follow from O72's narrow wording, not from a safety reason: a unique all-six sheet with an exact total but no positive price holds, while the same sheet without the total is scoped; a workbook whose best header row carries five labels holds, while one whose best row carries four goes whole to the generator (OWNER-3). |
| D6 | Both new cases still need the fresh scope reader's agreement on the bill sheet, the end row and every `in_scope` flag. A whole workbook is agreed as `bill_sheet_index` null, `end_row` null, no sheet of role `bill` and every non-empty sheet in scope. | O72 ("the scope reader still has to agree"); runner v4 sends every `PROPOSED` case to a reader anyway. |
| D7 | The whole-workbook case is a scoped packet that is read as unscoped. Its fact has `bill_rule` `BILL1.NOHEADER.v1`, three nulls and every non-empty sheet in scope; the roles and reasons in the fact are labels, not R49 decisions. | The runner constraint above; design finding R6. |
| D8 | The case is carried by the existing fact key `bill_rule`, with three values. No key is added to any schema; schema identifiers keep `.v1`. Under `BILL1.NOTOTAL.v1` the digest gains four keys on the no-total sheet only (design finding R3). | Every output for a workbook without the new patterns stays byte-identical apart from versions and hashes, and runner v4's tests pass unchanged. Route v4.3 rejects the two new values (`R59_SCOPE_FACT_INVALID`, checked by the route tests), so no older consumer misreads them (RQ4). |
| D9 | R47b and R49–R51 are unchanged, so the scope reader's rules excerpt body is byte-identical (checked). The reader gets the O72 boundary rules from its prompt template. | R49 already says how a range without a total ends. The O72 rules are scope-stage rules (R59). |
| D10 | R59 item 8 states the empty-sheet exception on every packet. | Finding 4 of the empty-sheet review. |
| D11 | Under `BILL1.NOTOTAL.v1` the digest shows the reader, for the no-total sheet, the line counts to the last content row, the first 20 rows of priced or not-estimated lines, the last line with no price and no status, and the last 3 priced or not-estimated lines with 2 rows of context; the reader template tells it to put the analysis sheet in scope when every priced or not-estimated line lies after a signature line and every line above it has no price and no status, and, when the workbook has no analysis sheet, to set `end_row` null (review finding F2). The deterministic alternative (a hold `R51_NOTOTAL_PRICED_TAIL`) is not adopted. | Design finding R3: an item-like priced line below the signature line makes the tool's R51 condition (i) false although the R49 range is all unpriced, so the analysis sheet would be scoped out silently. The reader's disagreement now catches it (tested: invented NT6). Without an analysis sheet the tool raises no `R51_ALL_UNPRICED_WITHOUT_ANALYSIS_SHEET` either; only the reader's null end row holds the case (tested: invented NT7 and the scope-stage variant). A new hold needs the owner's approval (OWNER-4). |
| D12 | The reader template tells the reader to set `bill_sheet_index` null when the bill sheet has no total row and another sheet, without a header of its own, continues its item lines in the same columns (with or without a total row). A summary sheet that lists section totals or the grand total is not a continuation. Narrowed in the review fix round (findings S1, F4): the first wording ("continue the bill sheet's item lines … or carry its total") applied under every bill rule and fitted a summary sheet that repeats the grand total, the normal layout, so it could hold O72's own cases and ordinary `BILL1.v1` workbooks that 046g's reader agreed on. | Design finding R13 (optional, adopted): a missing total can mean a bill continued on a headerless sheet, which `BILL1.NOTOTAL.v1` would scope out silently. It changes no tool rule: the tool proposes `BILL1.NOTOTAL.v1` for such a workbook (the continuation sheet has no header row), and the reader's null bill sheet holds it. The `BILL1.v1` identity proven by the build is tool-level only: the reader-template changes (the bill-sheet wording of R5, the no-bill-header paragraph, the column-J sentence) also reach readers of `BILL1.v1` cases, and no real reader has read them yet (RQ7). After the narrowing, the continuation sentence applies only to a bill sheet without a total row, which a `BILL1.v1` case never has. |
| D13 | The evaluator brief's manual-review policy path names `research/guideline046_009/package/`. | The design changed only the candidate label; the 046g path would have pointed the evaluator at 046g's R59. Recorded as a deviation from the design text. |

## Owner and reviewer questions

- **OWNER-1, required before the freeze** (design §7). One non-reserved pool workbook has two sheets, each with one six-label header and no total row. O72 covers "a unique bill-sheet header", so it stays held, and a held pool run is scored as the empty carrier, which fails the 0.90 case floor and so the gate. Options: (a) keep the hold; (b) no unique header means the whole workbook (one more condition in D4); (c) several bill sheets (a semantic change needing its own study); (d) the pool is the owner's call.
- **OWNER-2** (design finding R10, extends RQ2). Confirm the reading of O72's "that sheet": the bill sheet, with R59's R51 rule still bringing in the analysis sheets on an all-unpriced no-total bill. On the inferred real pattern this makes the scoped packet several times larger than the bill sheet alone.
- **OWNER-3** (design finding R11). The two non-monotonic boundaries of D5. Options for each: keep the hold (O72 as worded), or apply the same rule (scope the exact-total unpriced sheet under `BILL1.NOTOTAL.v1`-like rules; send a five-of-six workbook whole to the generator).
- **OWNER-4** (design finding R3). Whether to add the deterministic hold `R51_NOTOTAL_PRICED_TAIL` (an analysis sheet exists and every priced or not-estimated line follows the last line with no price and no status) instead of relying on the reader's disagreement.
- **OWNER-5 / reviewer** (design finding R14). The only no-header pattern in the structure-only record is a single analysis-only sheet. What R49–R51 give on a workbook with analysis blocks and no bill lines is an open semantic question outside O72; R59 item 9 leaves it to the existing rules ("the bill sheet, if any") and implies no answer. Raise it with the owner before the probe, not after a scored run.
- **RQ1.** D2's five-of-six clause is narrower than O72's literal "unique header". It also counts analysis block headers that carry 項次 (D5). Keep it?
- **RQ2.** D3 (see OWNER-2).
- **RQ3.** D1: the O72 cases only above the threshold.
- **RQ4.** D8: schema ids kept at `.v1`, value domains extended.
- **RQ5.** The reader template's literal label list (with the whitespace rule and the list of words that are not labels). Is it clear enough for a fresh reader?
- **RQ6.** A whole-workbook packet can be large (accepted under O72).
- **RQ7.** A probe with invented NT1, NT2 and NH2 workbooks and real fresh-context readers. The qualification toolkit cannot stage invented sources in a probe root as it stands (design finding C6), so either (a) run the probe through a scratch runner driver with manually launched fresh contexts, as development evidence outside the toolkit, or (b) extend the toolkit (a probe profile and root, a stage record for invented sources, invented case ids confirmed absent from the jobs list), tested and re-pinned before any root is admitted. The build recommends (a).

## Design-critic findings (R1–R15, C1–C7) and where each was applied

| Finding | Applied in 046i |
|---|---|
| R1 | FIELD_ROLES R59 item 2: the no-total paragraph replaces the rest of the item (bill sheet kept, range ended by R49 as on an unscoped packet, cells after the range unscoped roles; the tool's exact test stated). Mirrored in OUTPUT_CONTRACT step 2 and REVIEW_CHECKLIST 15a. |
| R2 | R59 item 3's exception sentence; REVIEW_CHECKLIST 15a: blocks of priced or not-estimated parents inside the bill sheet stay `analysis_unlinked` (item 6). |
| R3 | Scope tool v4 digest keys (D11); reader template end-row bullet; R59 *Limits* states the risk; invented NT6 in the scope-stage and O72 suites; the deterministic hold is OWNER-4. |
| R4 | "The scope stage fixes no bill sheet and no end row" in R59 item 9, the design-decision bullet, the `make_scoped_inventory.py` basis, the reader template (no-bill-header and In-scope bullets) and D4. |
| R5 | Reader template bill-sheet bullet ("its item lines below it (normally priced; …)"); invented NT2 with a reader that names the unpriced bill sheet with the analysis sheet in scope (FROZEN_AGREED, O72 suite). |
| R6 | R59 item 9 bullet on labels; the neutral whole-workbook reason of the scope tool; REVIEW_CHECKLIST 15a. |
| R7 | Reader template In-scope sentence (rows × columns above 0); R59 item 8 "It has no cell or view in the inventory"; R59 *Limits* on drawing-only sheets. |
| R8 | R59 design-decision *Reader agreement* sub-bullets replaced. |
| R9 | Reader template no-bill-header sentence (every whitespace character; words that are not labels) and end-row sentence (`price_column_total_rows_count` is 0). |
| R10 | D3, the O72 realisation paragraph above, the R59 design-decision bullet; OWNER-2. |
| R11 | D5, the R59 design-decision bullet; OWNER-3; RQ1. |
| R12 | R59 intro, item 1 and the In-scope/Out-of-scope bullets; OUTPUT_CONTRACT insertion in step 2; REVIEW_CHECKLIST 15a. |
| R13 | Adopted (D12). |
| R14 | OWNER-5; R59 item 9 says "the bill sheet, if any". |
| R15 | `DESIGN_046i.md` §5.3 heading split; the O72 suite tests NTx1–NTx4 as v1 holds and NTx5–NTx7 as NOTOTAL-specific outcomes; the identity comparison covers NTx1–NTx4, NHx1 and NHx2 against both baselines. |
| C1 | Toolkit test paths (not a file of this candidate): handed to the main session in the pin list. |
| C2 | Root reset and re-pin of every edited always-pinned toolkit file (not a file of this candidate): handed to the main session. |
| C3 | The build's comparison scripts take each candidate folder as an argument and record the tool hashes; pre-registration below. |
| C4 | Comparison classes S8–S10 defined in `DESIGN_046i.md` (addendum §9); `DESIGN_046i.md` §4.8 corrected (writer004 renders `metadata.adapter` as data). |
| C5 | Reader template In-scope sentence; `make_scoped_inventory.py` basis ("every sheet except an empty one (rows x columns = 0)"); invented NH4 (a styled-blank sheet) in the O72 suite. |
| C6 | RQ7 above. |
| C7 | The scope tool and `scope_agree.py` take every bill-rule id from the loaded route (`SCOPE_BILL_RULE`, `SCOPE_O72_RULES`, `SCOPE_BILL_RULES`); the two new constants follow `SCOPE_BILL_RULE`, outside the writer-port section; the `CONTENT_ROLES` line is byte-identical; route test `v44_port_section_and_content_roles_line_equal_v43`. |

## Pre-registered expectations for the structure-only re-run (design §5.6)

Written before the run. The re-run uses the frozen 046i harness. Its record is read only if the `scope_tool.py` sha256 it records equals the value frozen at C5 (design finding C3).
- The jobs that reached GENERATE or SCOPE_READER in the 046g dry run reach them again with the same facts under the comparison rule of design §5.1.
- Three of the five held jobs reach SCOPE_READER with `BILL1.NOTOTAL.v1`.
- One reaches SCOPE_READER with `BILL1.NOHEADER.v1`.
- One stays `OWNER_DECISION` with `BILL1_CANDIDATES_NOT_ONE`, unless the owner rules otherwise (OWNER-1).
- The rehearsal jobs are unchanged.

A deviation goes to the owner as a finding. It never changes the rule after the run. The empty sheets of the sources that have them are checked for drawing parts (xlsx sheet relationships, xls drawing records) before the empty-sheet exclusion is relied on.

## Explicitly not changed

R47b and R49–R58; the scope reader's rules excerpt body; the threshold; the reader-response, decision, proposal, digest and fact schemas (key sets unchanged; value domains grow only under the new bill rules); the builders and `render_views.py`; `make_job_config.py`, `prepare_run.py`, `freeze_admission.py`, `freeze_outputs.py`, `make_release.py`, `audit_transcript.py`, `fullpath_check.py`; the 9 package resources that 046g's examples depend on; runner v4 and its tests; writer v2.8.2; evaluator v4; aggregator v2.

## Build record

See the last section of `DESIGN_046i.md` (addendum §9) for the suites and comparisons run on 2026-11-14.
