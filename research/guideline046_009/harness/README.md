# Harness for candidate 046i (draft)

Candidate 046i copies the frozen 046g harness (`research/guideline046_007/harness/` at release commit `4c40004`) and changes:
- the empty-sheet fix (`BUGFIX_EMPTY_SHEETS.md`), developed in place in 046g's harness as work in progress, reviewed (ADMIT_WITH_FIXES) and moved here; 046g was restored to its frozen bytes;
- the two scope boundary cases of owner decision O72 (FIELD_ROLES R59 items 2 and 9; section "Scope stage" below): `scope_tool.py` v4 (`cps046i-scope-tool.v4`), `scope_agree.py` (whole-workbook agreement, the fact's bill rule from the proposal), the fact basis of `make_scoped_inventory.py`, and the bill-sheet, end-row and in-scope bullets of `SCOPE_READER_PROMPT_TEMPLATE.md`;
- the templates name candidate 046i and `research/guideline046_009/package/`; the evaluator brief adds the scope-loss sentence for the two new bill rules;
- the package route is v4.4 (`cps046i-route.v4.4`), which changes only the scope-fact check.

`make_job_config.py`, `prepare_run.py`, `freeze_admission.py`, `freeze_outputs.py`, `make_release.py`, `audit_transcript.py` and `fullpath_check.py` are byte-identical to 046g's. The decision notes of this build are at the end of this file and in `../DECISIONS_046i.md`.

Candidate 046g copied the 046f harness (`research/guideline046_006/harness/`) and changed three things (history):
- the scope stage for large workbooks (FIELD_ROLES R59; section "Scope stage" below): `scope_tool.py`, `SCOPE_READER_PROMPT_TEMPLATE.md`, `scope_agree.py` and `make_scoped_inventory.py`;
- the templates name candidate 046g and `research/guideline046_007/package/`, and the generator prompt covers scoped packets;
- the evaluator is v4, `research/evaluation/compare_target050.py` (owner decisions O23, O35: A/B scored once per panel; frozen at sha256 `fc723405c41ca4a46e4318913ecd742316682c2f9edb8b35ae59ca1a9acc3859`, `research/evaluation/FREEZE_050.json`, output schema `cps.target-comparison050.v1`). v3 (`compare_target049.py`, sha256 `b600c04619c943ec78f577c4a681df3cc3d035638fab36f9be3f946eea5904c9`) and v2 (`compare_target048.py`, sha256 `98a30acfaf6b10ede3e81a55a721741f2c7ac701925ce052bfc4ced1f7af73d6`) stay frozen; their scorings are reported beside v4 as the `v3_per_row_AB` and `v2_alignment` blocks of the v4 output (computed with v4's K–O tie-break, so each equals its frozen evaluator except on a K–O tie), and each keeps governing the results recorded under it before O35. `description_cd` is reported against 0.75 and does not gate (O24). The `ab_row_check` diagnostic feeds the manual critical-error review (`EVALUATOR_BRIEF_TEMPLATE.md`).

The other scripts behave as in 046f: `prepare_run.py` (copies the bound source packet only), `freeze_admission.py`, `freeze_outputs.py`, `make_release.py`, `audit_transcript.py`, `fullpath_check.py` and `make_job_config.py` (below). The harness scripts load the package route by path, so in 046i they use route v4.4 (`cps046i-route.v4.4`).

## Packet preparation adds context facts from a private per-job config

046f needs facts that the source does not contain (owner decisions O13–O17; FIELD_ROLES R47b, R48, R58). The source preparer adds them to `SOURCE_INVENTORY.json` `context_facts` before the packet is pinned, from one private per-job configuration file. The file and the resource files it names are company business data: keep them out of the repository, pin each by SHA-256 in the admission, and never pass anything else from them to a generator.

`make_job_config.py` turns the private job JSON into the inventory-builder config. The existing builders, `research/guideline046_003/source_prep/build_inventory_xlsx_v2.py` (`.xlsx`) and `build_inventory_v2.py` (`.xls`), copy the config's `context_facts` into the inventory verbatim (`'context_facts': cfg['context_facts']`), so they are used unchanged and were not copied here.

```sh
python3 -I -B research/guideline046_009/harness/make_job_config.py --job /abs/private/JOB.json --out /abs/new/BUILDER_CONFIG.json
python3 -I -S -B research/guideline046_003/source_prep/build_inventory_xlsx_v2.py --bundle DIR --config /abs/new/BUILDER_CONFIG.json --out NEWDIR
#   .xls sources: build_inventory_v2.py with the same arguments; the config's "builder" key names the right one
```

The tool prints hashes and fact names only, never private values. It refuses (exit 1, JSON on stderr, nothing written) a missing or unexpected key, a bad id, a job input the route would reject or hold (blank, control characters, edge whitespace, or a value starting with `=`, `+`, `-` or `@`), a source that is not an existing `.xlsx`/`.xls` file, a `carrier_path` that fails the writer's source-path rules (checked with the route's own `_source_shape`, including the forbidden-path words), a resource file with the wrong schema or shape, a `brand_table_path` on a 材料清單 job or none on a contract job, and an existing output.

Job JSON (`cps.job-config.v2`, one object per source packet):

| Key | Required | Becomes | Notes |
|---|---|---|---|
| `schema` | yes | – | `"cps.job-config.v2"` |
| `case_id` | yes | `context:case_identity` (`cps.internal_case_id`), inventory `case_id` | internal case id (L) |
| `customer_name` | yes | `context:customer_name` (`cps.job_input.customer_full_name`) | customer full name (M) |
| `project_name` | yes | `context:project_name` (`cps.job_input.project_short_name`) | project short name (N) |
| `company_name` | yes | `context:company_name` (`cps.company_resource.company_name`) | J of the enclosure row when the source states no brand (R56) |
| `glossary_path` | yes | `context:glossary` (`cps.company_resource.glossary`) | absolute path of the owner-reviewed glossary, JSON `cps.company-glossary.v1`: `generic_prefix_words`, `enclosure_word`, `abbreviations[{device, abbreviation}]`, and `category_words` (R52 drops the category words the glossary lists) |
| `brand_table_path` | contract jobs only | `context:brand_table` (`cps.company_resource.brand_table`) | absolute path of the owner-reviewed brand table, JSON `cps.company-brand-table.v1`: `entries[{device, rating_band, brand, model}]`. Required when `source_kind` is `"contract"`; refused when it is `"材料清單"` (`BRAND_TABLE_NOT_USED_WITH_MATERIAL_LIST`): the brand table is used only when the job has no 材料清單 (O17, R47b, R55), so a 材料清單 packet has no `context:brand_table` and the route's `UNKNOWN_CONTEXT_REF` rejects any citation of it |
| `source_path` | yes | config `original` (`path`, `bytes`, `sha256`) | absolute path of the source workbook; the extension picks the builder |
| `source_kind` | yes | config `source_document_kind` and the start of `adoption_basis` | `"材料清單"` (company material list, primary when present, R47b) or `"contract"` |
| `carrier_path` | yes | inventory `carrier_source.path` | the source's original canonical Windows path, provenance only (`X:\…\file.xlsx`); the writer requires that form |
| `family_id` | no | inventory `family_id` | default `case_id` |
| `adoption_status` | no | inventory `adoption_status` | `verified`, `partial` or `unverified` (default) |
| `adoption_basis` | no | inventory `adoption_basis` | appended after the source-kind sentence |
| `views` | no | builder `views` | `"auto"` (default) or the builder's view list |
| `provenance` | no | the facts' `basis` | `job_inputs`, `glossary_review`, `brand_table_review`: who supplied the inputs and the owner review record of each table. When absent, each basis says so |

Each fact gets `basis` (what it is, under which decision and rule, and who supplied it) and `authority_pins`. The job inputs and the company name pin the SHA-256 of the job JSON. The glossary and brand table values are the files' JSON re-serialised as compact JSON text (no whitespace, key order kept). Their `basis` states the SHA-256 of the file bytes and of the embedded text, and `authority_pins` holds both. The config also records `job_config_sha256` and `resource_files_sha256`; the builders ignore those keys and `schema`, `builder` and `source_document_kind`.

Build one config per job, for its bound source (R47b): the 材料清單 when the job has one, otherwise the contract.

**No reference channel (046f round 3, review item S11).** The job's other document is not packed for the generator, and `prepare_run.py` copies exactly one packet. Round 2 let R47b supply the other document as a read-only reference that no field may cite, but no harness channel carried it, and nothing could keep its content out of the fields mechanically (the route sees only cited cells of the bound inventory). The simplest consistent option was to remove the phrase rather than add a channel. A doubt the bound source leaves (for example a missing dimension) stays a null with a reason or a review reason. A reference channel, if the owner wants one, needs its own design and review in a later candidate. A job missing a required key is held: do not generate with a missing job input or resource, and never fill one from a letterhead, a historical 未填 or memory.

`EXAMPLE_INVENTORY.json` in the package shows the resulting shape with invented values (an invented 材料清單-style source).

## Scope stage for large workbooks (046g, FIELD_ROLES R59; O72 cases in 046i)

The scope stage is source preparation. It runs after the full packet is built (`make_job_config.py`, the builder with every sheet in scope, then `render_views.py`) and before `prepare_run.py`, and it is frozen before any generation. It never reads targets, outputs or evaluator files. The tools print hashes, indexes, roles and counts, never cell text or sheet names; the digest, the proposal, the reader response, the decision and the scoped inventory hold private source text and stay out of the repository.

1. **Full inventory.** Build the job packet with every sheet in scope and pin `SOURCE_INVENTORY.json` (sha256). This is the *full inventory*. The builders write an empty sheet (rows x columns = 0) as `in_scope: false`; `scope_tool.py` (v3 and v4) and `make_scoped_inventory.py` accept such a sheet when it has no cell and no view, keep it out of scope (role `other`, no flag) and refuse any other out-of-scope sheet (`FULL_INVENTORY_REQUIRED`), as before (`BUGFIX_EMPTY_SHEETS.md`, 2026-11-13).
2. **Scope tool.**
   ```sh
   python3 -I -B research/guideline046_009/harness/scope_tool.py --inventory /abs/FULL/SOURCE_INVENTORY.json --out-dir /abs/new/scope_tool
   ```
   It counts the literal and cached-formula content cells. At 2,500 or fewer it writes `SCOPE_PROPOSAL.json` with status `NOT_APPLIED`: the full inventory is the packet, there is no `context:scope`, and steps 3 to 5 are skipped. Above 2,500 it computes BILL1 and the R51 conditions (the module docstring states both exactly), proposes each sheet's role, `in_scope` flag and reason, lists its flags (hidden sheets, other-role sheets, near BILL1 candidates, out-of-scope sheets with nonzero prices or 不含估價, linked blocks on out-of-scope sheets, other price text, name-prefix-only links), and writes `SCOPE_DIGEST.json` and `SCOPE_RULES_EXCERPT.md` (R47b and R49–R51 copied verbatim from the package). Status `HOLD` (exit 4), from several BILL1 candidates, from zero candidates outside the two O72 cases (FIELD_ROLES R59), or from an all-unpriced bill without an analysis sheet, sends the case to the owner. The two O72 cases (046i, considered only above the threshold with no BILL1 candidate) are `PROPOSED`: `BILL1.NOTOTAL.v1`, a unique six-label bill header with no exact 合計/總計 in its price columns, gives that sheet as the bill sheet with the end row at its last content row (R49 ends the quoted range inside it); `BILL1.NOHEADER.v1`, no row with five or six of the labels on any sheet, gives no bill sheet and no end row and puts every non-empty sheet in scope (the whole workbook, read as an unscoped packet). Runner v4 sends every `PROPOSED` case to a scope reader, so both still need its agreement. Inventories above the route's 20 MiB input limit are refused.
3. **Scope reader.** Prepare a run directory whose `input/` holds exactly `SCOPE_DIGEST.json` and `SCOPE_RULES_EXCERPT.md` from step 2 (read-only), and give a fresh context `SCOPE_READER_PROMPT_TEMPLATE.md` with `{SCOPE_RUN}` filled in. Record the actual model, effort and tools. The reader never sees the proposal, the full inventory or the package. Its output is `output/SCOPE_READER_RESPONSE.json` (`cps.scope-reader-response.v1`).
4. **Agreement.**
   ```sh
   python3 -I -B research/guideline046_009/harness/scope_agree.py --proposal /abs/scope_tool/SCOPE_PROPOSAL.json \
       --digest /abs/scope_tool/SCOPE_DIGEST.json --reader /abs/scope_run/output/SCOPE_READER_RESPONSE.json --out-dir /abs/new/decision
   ```
   The tool and the reader must agree on the bill sheet, the end row and every `in_scope` flag. Agreement freezes `SCOPE_DECISION.json` (status `FROZEN_AGREED`, exit 0), which records every hash, the reader record, the role differences, the tool flags and the payload of `context:scope`. A decision is `admissible` only for a fresh-context scope reader, and only an admissible decision carries `agreement: "tool_and_reader_agreed"` in its `context:scope` payload; any other reader (an engineering stand-in) gives `admissible: false` and `"tool_and_stand_in_agreed"`, which route v4.4, like v4.3, rejects (`R59_SCOPE_FACT_INVALID`), so such a decision never becomes a generation packet. On a whole-workbook proposal the reader agrees only with `bill_sheet_index` and `end_row` null, no sheet of role `bill` and every non-empty sheet in scope. The digest shows the reader the tool's line and link counts, so the reader's agreement on the analysis flags is not independent of the tool; its independent part is the bill sheet and the end row. Reader doubts are recorded (`reader_doubts_count`) and do not hold a case. Disagreement writes `SCOPE_HOLD.json` (`HELD_FOR_OWNER`, exit 3): the case is held for the owner, with no tie-break run and no second reader.
5. **Scoped inventory.**
   ```sh
   python3 -I -B research/guideline046_009/harness/make_scoped_inventory.py --full /abs/FULL/SOURCE_INVENTORY.json \
       --decision /abs/decision/SCOPE_DECISION.json --out-dir /abs/new/scoped_packet
   python3 -I -B research/guideline046_009/harness/make_scoped_inventory.py --verify --full /abs/FULL/SOURCE_INVENTORY.json \
       --decision /abs/decision/SCOPE_DECISION.json --scoped /abs/new/scoped_packet/SOURCE_INVENTORY.json --expect-scoped-sha256 HEX
   ```
   The build removes the out-of-scope cells and views, renumbers the kept views 1..n (the route and writer004 require consecutive view ids; a kept cell's `views` list follows the renumbering), sets the flags and appends `context:scope`. Every other record stays byte-identical, in the builders' one-record-per-line serialization. It copies the in-scope view images, checking their pins, self-verifies, runs the route's `check-inventory`, and writes `SCOPED_INVENTORY_RECEIPT.json` with both inventory hashes, the decision hash and the view-id map. `--verify` repeats the record-by-record comparison independently and checks the scoped hash against the pinned value. The scoped packet directory (`SOURCE_INVENTORY.json` plus its `view_*.png`) is what `prepare_run.py --packet` receives.

**Admission requirement for a scoped packet.** The admission config pins, before any generation:
- the full inventory (`full_inventory_<case>`);
- the scoped inventory as the packet inventory (`packet_<case>_inventory`) and its view images;
- `SCOPE_DECISION.json` (`scope_decision_<case>`);
- the proposal, the digest, the rules excerpt and the reader response;
- `SCOPED_INVENTORY_RECEIPT.json`;
- the four scope-stage files of this harness.

`expected_sha256` lists the full and scoped inventory hashes from the receipt, so `freeze_admission.py` refuses a mismatch (`PIN_MISMATCH`). Record in the plan fields: the decision's `admissible` value (it must be true), `--verify` PASS, `check-inventory` with `scope: applied` and `policy_checks: applied`, and the in-scope content-cell count. A packet at or below the threshold records `scope: not_applied` and the tool's `NOT_APPLIED` proposal.

### Validation of `scope_tool.py` on the study inventories (046g review S14, D4)

Source role, 2026-11-05. `scope_tool.py` (`cps046g-scope-tool.v2`, sha256 `e9190c2f9f0caf9fb030d0aab2b1ab569e3606dff4d3d1752eb1b8b9c4d756af`) was run on the five full inventories of the large material-list structure study (`research/guideline046_005/STUDY_LARGE_MATLIST_STRUCTURE_20261105.md`; exposed tuning cases, every sheet in scope). No target, output or evaluator file was read. The tool's outputs hold private source text and stay outside the repository; this record gives counts only. It was run twice, before and after the delta-review wording, with identical computed values.

| Case | Literal/cached content cells | Status | BILL1 candidates | Bill sheet | Header row | Range rows | End cell | In-range lines (priced / not estimated / no price, no status) | Linked analysis blocks | Flags | Holds |
|---|---:|---|---|---:|---:|---|---|---|---:|---|---|
| 1131112 | 7,629 | PROPOSED | 1 | 2 | 8 | 14–100 | E100 | 78 (23 / 55 / 0) | 0 | none | none |
| 1131207 | 4,604 | PROPOSED | 1 | 2 | 8 | 11–78 | E78 | 67 (27 / 40 / 0) | 0 | none | none |
| 1140304 | 2,459 | NOT_APPLIED | 1 | 2 | 8 | 10–96 | E96 | 83 (36 / 47 / 0) | 0 | none | none |
| 1140607 | 3,965 | PROPOSED | 1 | 2 | 8 | 14–146 | E146 | 61 (23 / 38 / 0) | 8 (1 priced, 7 not-estimated parents) | `LINKED_BLOCKS_OUT_OF_SCOPE` (analysis sheet) | none |
| 1140808 | 5,286 | PROPOSED | 1 | 1 | 8 | 13–129 | E129 | 77 (27 / 50 / 0) | 0 | `OUT_OF_SCOPE_NONZERO_PRICES` (analysis sheet, 42 cells) | none |

- The bill sheet, header row, end row and flags reproduce the study in 5 of 5 cases. 1140304 comes out `NOT_APPLIED` at 2,459 cells (threshold 2,500), so every sheet stays in scope and there is no `context:scope`. The in-range line counts, the analysis block and component counts (189/1,075, 114/614, 31/128, 8/37, 94/488) and the in-scope content cells of the four scoped cases (543, 452, 999, 637) also match the study. There are no hidden sheets, and R51 condition (i) holds in none of the five.
- 1140607's 3,965 counts literal and cached-formula cells; the study's 3,968 also counts 3 missing-cache cells. The tool attributes its 8 links to code and name (0 by outline path), where the study reports code, name and outline path agreeing on each link; the linked-block count and the parent split are the same, so no flag or scope decision differs. 1140808's 42 cells are consistent with the study's 21 owner-fixed component prices.
- This is the tool reproducing the study whose rule it implements, on the same five cases. It is not an independent test on other layouts. No tool change followed from it.
- The tool is now v3 (`cps046g-scope-tool.v3`, 2026-11-13, `BUGFIX_EMPTY_SHEETS.md`). v3 differs from v2 only on an inventory with an empty sheet (rows x columns = 0, no cell or view), which v2 refused. v2 accepted the five study inventories, so none has such a sheet and v3 computes the same values on them; this follows from the code change and was not re-run.
- v4 (`cps046i-scope-tool.v4`, candidate 046i, owner decision O72) differs from v3 only on an inventory above the threshold with no BILL1 candidate that meets one of the two O72 cases. Each study inventory has exactly one candidate, so v4 computes v3's values on them. This follows from the code; it was not re-run (study inventories are off-limits here). The build compared v4 with v3 and v2 on invented workbooks without the new patterns (`../DECISIONS_046i.md`).

**After the freeze (evaluation role).** For a scoped packet the evaluator also receives the decision and the full inventory. It classifies an unmatched historical row whose source line lies on a scoped-out sheet, or below the declared end row, as *scope loss* and reports it separately (`EVALUATOR_BRIEF_TEMPLATE.md`). Scope loss is never repaired in a scored output.

## Admission and export notes

- Pin the guideline package, route v4.4 (`package/tools/cps046b_route.py`, `cps046i-route.v4.4`), the per-job config, each resource file, the scope-stage files of a scoped packet (above), the evaluator (`research/evaluation/compare_target050.py` v4, sha256 `fc723405c41ca4a46e4318913ecd742316682c2f9edb8b35ae59ca1a9acc3859`, for the historical-match metric, O23, O35; the frozen v3 and v2 are reported beside it through the v4 output's `v3_per_row_AB` and `v2_alignment`) and its metric, and both declared readings of the O10 boundary (A12) in the admission before any generation.
- For a qualification run, also pin the frozen O31 gate aggregator v2 `research/evaluation/aggregate_qualification050.py` (gate v2, sha256 `e5aa4fc770cbf75560c3f073f03e01360cb46fd8e0ce708726b2991bfe5bc76f`, `research/evaluation/FREEZE_AGG_O31_V2.json`; it pins evaluator v4 and refuses other outputs). Under O31 the deployment reading is pooled: for each reader, matched/counted over the 30 qualification pairs ≥ 0.95 and no case < 0.90, computed only by that aggregator over the frozen v4 comparisons (it also pools `v3_per_row_AB`, reported, not gating). The v1 aggregator (`aggregate_qualification.py`, `d48b81f3…`) refuses v4 outputs and is not used. A case's own 0.95 reading (`governing.case_matches_at_95`) is a diagnostic; no case is passed or failed on it (`EVALUATOR_BRIEF_TEMPLATE.md`).
- Route v4.4 keeps every v4.3 check and adds only the O72 fact checks (`BILL1.NOTOTAL.v1`: end row = the bill sheet's last content row; `BILL1.NOHEADER.v1`: three nulls, no bill role, every sheet in scope exactly when it is not empty, no linked blocks, no `R59_ROW_BELOW_END_ROW` check). Route v4.3 keeps every v4.2 check. Without `context:scope` it behaves as v4.2 and reports `scope: not_applied`; with it, it adds the R59 checks (`R59_SCOPE_FACT_INVALID`, `R59_SCOPE_FACT_MISMATCH`, `R59_ROW_BELOW_END_ROW`, `R59_SCOPE_FACT_CITED`, all `invalid`) and the warning `R59_LINKED_ANALYSIS_OUT_OF_SCOPE`, and reports `scope: applied`.
- Route v4.4 (like v4.3) warns, and does not reject, for the three documented relaxations: `O13_SELECTION_EVIDENCE_M_N` (M/N from job inputs), `R57_NULL_C_RESEARCH_DRAFT` (a null C on a `research_draft` row) and `O16_Q_UNVERIFIED_ADOPTION` (Q under unverified adoption). On a 046f job packet it rejects departures from R48 and the R56 group mechanism as `invalid` (`OUTPUT_CONTRACT.md`, interface point 4) and reports `policy_checks: applied`; a packet built by `make_job_config.py` is always a job packet.
- The route's `convert` receipt reports each class (`o13_m_n_selection_evidence`, `r57_null_c_research_draft`, `o16_q_unverified_adoption`) and the overall `export_mode_required`; use the overall value. Carriers that need `v2` are exported with `research/export/writer_portable.py --mode v2`; the unchanged writer004 gate refuses them (`SELECTION_ONLY_ENGINEERING_ID`, `UNRESOLVED_ITEM_MUST_BE_HELD`). Mode v2 loads the route port only if its bytes match the sha256 pinned in the writer (`ROUTE_V4_SHA256`), which is the frozen 046f route v4.2 file. Route v4.4 (like v4.3) keeps the writer-port section byte-identical (the route tests check it), so v4.4 and v4.3 carriers are validated by that pinned port unchanged. The portable writer v2.7 is admitted (`research/export/ADMISSION_WRITER_V27.json`, saved_qa v6.1, visual_qa v4.1). Run it with `--job-title` = the job's project folder title, a per-job input like L/M/N (O33). The title is not a key of the job JSON (`make_job_config.py` refuses unknown keys) and never enters the packet: keep it in a private per-job title file, pin that file in the admission (`job_title_<case>`) before any generation, and record the check of the receipt's `deliverable.job_title` against it (admission condition 7). The writer then writes the delivered one-sheet `<name>.xlsx` in the creator's format (O33, O34, O38) and `INTERNAL_QA_WORKBOOK.xlsx`, which is never delivered. Saved QA, visual QA and delivery follow that admission's conditions of use.
- `freeze_admission.py` still writes the 046b admission schema name; the plan fields in its config name the candidate.


## Admission requirement (from the 046f review, kept in 046g and 046i)

Every 046g or 046i generation run must be admitted only for a packet whose `check-inventory` reports `policy_checks: applied` (job-input facts present), and, for a scoped packet, `scope: applied` with the pins listed under "Scope stage". Record both values in the admission record. A packet without job-input facts is not a 046f/046g job packet.

## Decision notes (046i build, 2026-11-14)

The design (`../DESIGN_046i.md`) went through a design critique before the build (findings R1–R15 on the rule text and the tools, C1–C7 on the proof plan and the downstream steps). Every finding on a file of this candidate was applied; `../DECISIONS_046i.md` lists each finding and where it was applied. Not applied in the candidate, and why:
- the deterministic alternative of R3 (a hold `R51_NOTOTAL_PRICED_TAIL` when every priced or not-estimated line follows the last unpriced line) adds a hold, which needs the owner's approval; the candidate applies R3's digest and reader-template parts and records the hold as an owner question;
- C1, C2 and C6 change the qualification toolkit, its tests and its roots, and C3 the build's comparison scripts; none of them is a file of this candidate. The build applied C3 to its own scripts (each takes the candidate folder as an argument) and hands C1, C2 and C6 to the main session with the pin list;
- C4 defines the runner-level comparison classes S8–S10; they are recorded in `../DESIGN_046i.md` (addendum §9.2) for any runner-level identity comparison; the build compared tool-level outputs under S1–S7 and checked the runner-level outcomes of the O72 cases;
- R11 and R14 are owner and reviewer questions, not text fixes; they are recorded in `../DECISIONS_046i.md`.

Review fix round (2026-11-14). The semantic and code reviews of the build (both ADMIT_WITH_FIXES; findings S1–S8 and F1–F7) were applied; `../DECISIONS_046i.md` lists each finding and where it was applied, and no finding was found wrong. In this harness: the scope reader template (the continuation sentence limited to a bill sheet without a total row, the column-J label sentence, the block-total case of the no-total trigger, and a null end row for a priced tail with no analysis sheet), the no-total fact basis of `make_scoped_inventory.py`, the two route-version bullets above, and new invented tests in the scope-stage and O72 suites. Not files of this candidate, and so not applied here: the owner's rulings required before the freeze (OWNER-1, OWNER-2, OWNER-4), the RQ7 probe with real fresh-context readers, the corrections to `CURRENT_STATE.json` and `docs/handoff/DEPLOYMENT_MODEL.md`, and the toolkit re-pins. The validation table above keeps 046g's study case ids (inherited published text; finding F6).
