# Harness for candidate 046g (draft)

Candidate 046g copies the 046f harness (`research/guideline046_006/harness/`) and changes three things:
- the scope stage for large workbooks (FIELD_ROLES R59; section "Scope stage" below): `scope_tool.py`, `SCOPE_READER_PROMPT_TEMPLATE.md`, `scope_agree.py` and `make_scoped_inventory.py`;
- the templates name candidate 046g and `research/guideline046_007/package/`, and the generator prompt covers scoped packets;
- the evaluator is v3, `research/evaluation/compare_target049.py` (owner decision O23; frozen at sha256 `b600c04619c943ec78f577c4a681df3cc3d035638fab36f9be3f946eea5904c9`, `research/evaluation/FREEZE_049.json`, output schema `cps.target-comparison049.v1`). The v2 metric (`compare_target048.py`, sha256 `98a30acfaf6b10ede3e81a55a721741f2c7ac701925ce052bfc4ced1f7af73d6`) stays frozen and is reported beside v3 as the `v2_alignment` block of the v3 output; it governs every result recorded before the v3 freeze. `description_cd` is reported against 0.75 and does not gate (O24).

The other scripts behave as in 046f: `prepare_run.py` (copies the bound source packet only), `freeze_admission.py`, `freeze_outputs.py`, `make_release.py`, `audit_transcript.py`, `fullpath_check.py` and `make_job_config.py` (below). The harness scripts load the package route by path, so they use route v4.3 (`cps046g-route.v4.3`).

## Packet preparation adds context facts from a private per-job config

046f needs facts that the source does not contain (owner decisions O13–O17; FIELD_ROLES R47b, R48, R58). The source preparer adds them to `SOURCE_INVENTORY.json` `context_facts` before the packet is pinned, from one private per-job configuration file. The file and the resource files it names are company business data: keep them out of the repository, pin each by SHA-256 in the admission, and never pass anything else from them to a generator.

`make_job_config.py` turns the private job JSON into the inventory-builder config. The existing builders, `research/guideline046_003/source_prep/build_inventory_xlsx_v2.py` (`.xlsx`) and `build_inventory_v2.py` (`.xls`), copy the config's `context_facts` into the inventory verbatim (`'context_facts': cfg['context_facts']`), so they are used unchanged and were not copied here.

```sh
python3 -I -B research/guideline046_007/harness/make_job_config.py --job /abs/private/JOB.json --out /abs/new/BUILDER_CONFIG.json
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

## Scope stage for large workbooks (046g, FIELD_ROLES R59)

The scope stage is source preparation. It runs after the full packet is built (`make_job_config.py`, the builder with every sheet in scope, then `render_views.py`) and before `prepare_run.py`, and it is frozen before any generation. It never reads targets, outputs or evaluator files. The tools print hashes, indexes, roles and counts, never cell text or sheet names; the digest, the proposal, the reader response, the decision and the scoped inventory hold private source text and stay out of the repository.

1. **Full inventory.** Build the job packet with every sheet in scope and pin `SOURCE_INVENTORY.json` (sha256). This is the *full inventory*.
2. **Scope tool.**
   ```sh
   python3 -I -B research/guideline046_007/harness/scope_tool.py --inventory /abs/FULL/SOURCE_INVENTORY.json --out-dir /abs/new/scope_tool
   ```
   It counts the literal and cached-formula content cells. At 2,500 or fewer it writes `SCOPE_PROPOSAL.json` with status `NOT_APPLIED`: the full inventory is the packet, there is no `context:scope`, and steps 3 to 5 are skipped. Above 2,500 it computes BILL1 and the R51 conditions (the module docstring states both exactly), proposes each sheet's role, `in_scope` flag and reason, lists its flags (hidden sheets, other-role sheets, near BILL1 candidates, out-of-scope sheets with nonzero prices or 不含估價, linked blocks on out-of-scope sheets, other price text, name-prefix-only links), and writes `SCOPE_DIGEST.json` and `SCOPE_RULES_EXCERPT.md` (R47b and R49–R51 copied verbatim from the package). Status `HOLD` (exit 4), from zero or several BILL1 candidates or an all-unpriced bill without an analysis sheet, sends the case to the owner. Inventories above the route's 20 MiB input limit are refused.
3. **Scope reader.** Prepare a run directory whose `input/` holds exactly `SCOPE_DIGEST.json` and `SCOPE_RULES_EXCERPT.md` from step 2 (read-only), and give a fresh context `SCOPE_READER_PROMPT_TEMPLATE.md` with `{SCOPE_RUN}` filled in. Record the actual model, effort and tools. The reader never sees the proposal, the full inventory or the package. Its output is `output/SCOPE_READER_RESPONSE.json` (`cps.scope-reader-response.v1`).
4. **Agreement.**
   ```sh
   python3 -I -B research/guideline046_007/harness/scope_agree.py --proposal /abs/scope_tool/SCOPE_PROPOSAL.json \
       --digest /abs/scope_tool/SCOPE_DIGEST.json --reader /abs/scope_run/output/SCOPE_READER_RESPONSE.json --out-dir /abs/new/decision
   ```
   The tool and the reader must agree on the bill sheet, the end row and every `in_scope` flag. Agreement freezes `SCOPE_DECISION.json` (status `FROZEN_AGREED`, exit 0), which records every hash, the reader record, the role differences, the tool flags and the payload of `context:scope`. A decision is `admissible` only for a fresh-context scope reader. Disagreement writes `SCOPE_HOLD.json` (`HELD_FOR_OWNER`, exit 3): the case is held for the owner, with no tie-break run and no second reader.
5. **Scoped inventory.**
   ```sh
   python3 -I -B research/guideline046_007/harness/make_scoped_inventory.py --full /abs/FULL/SOURCE_INVENTORY.json \
       --decision /abs/decision/SCOPE_DECISION.json --out-dir /abs/new/scoped_packet
   python3 -I -B research/guideline046_007/harness/make_scoped_inventory.py --verify --full /abs/FULL/SOURCE_INVENTORY.json \
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

**After the freeze (evaluation role).** For a scoped packet the evaluator also receives the decision and the full inventory. It classifies an unmatched historical row whose source line lies on a scoped-out sheet, or below the declared end row, as *scope loss* and reports it separately (`EVALUATOR_BRIEF_TEMPLATE.md`). Scope loss is never repaired in a scored output.

## Admission and export notes

- Pin the guideline package, route v4.3 (`package/tools/cps046b_route.py`, `cps046g-route.v4.3`), the per-job config, each resource file, the scope-stage files of a scoped packet (above), the evaluator (`research/evaluation/compare_target049.py` v3, sha256 `b600c04619c943ec78f577c4a681df3cc3d035638fab36f9be3f946eea5904c9`, for the historical-match metric, O23; the frozen v2 `compare_target048.py` is reported beside it through the v3 output's `v2_alignment`) and its metric, and both declared readings of the O10 boundary (A12) in the admission before any generation.
- Route v4.3 keeps every v4.2 check. Without `context:scope` it behaves as v4.2 and reports `scope: not_applied`; with it, it adds the R59 checks (`R59_SCOPE_FACT_INVALID`, `R59_SCOPE_FACT_MISMATCH`, `R59_ROW_BELOW_END_ROW`, `R59_SCOPE_FACT_CITED`, all `invalid`) and the warning `R59_LINKED_ANALYSIS_OUT_OF_SCOPE`, and reports `scope: applied`.
- Route v4.3 warns, and does not reject, for the three documented relaxations: `O13_SELECTION_EVIDENCE_M_N` (M/N from job inputs), `R57_NULL_C_RESEARCH_DRAFT` (a null C on a `research_draft` row) and `O16_Q_UNVERIFIED_ADOPTION` (Q under unverified adoption). On a 046f job packet it rejects departures from R48 and the R56 group mechanism as `invalid` (`OUTPUT_CONTRACT.md`, interface point 4) and reports `policy_checks: applied`; a packet built by `make_job_config.py` is always a job packet.
- The route's `convert` receipt reports each class (`o13_m_n_selection_evidence`, `r57_null_c_research_draft`, `o16_q_unverified_adoption`) and the overall `export_mode_required`; use the overall value. Carriers that need `v2` are exported with `research/export/writer_portable.py --mode v2`; the unchanged writer004 gate refuses them (`SELECTION_ONLY_ENGINEERING_ID`, `UNRESOLVED_ITEM_MUST_BE_HELD`). Mode v2 loads the route port only if its bytes match the sha256 pinned in the writer (`ROUTE_V4_SHA256`), which is the frozen 046f route v4.2 file. Route v4.3 keeps the writer-port section byte-identical (the route tests check it), so v4.3 carriers are validated by that pinned port unchanged. The portable writer is not admitted yet.
- `freeze_admission.py` still writes the 046b admission schema name; the plan fields in its config name the candidate.


## Admission requirement (from the 046f review, kept in 046g)

Every 046g generation run must be admitted only for a packet whose `check-inventory` reports `policy_checks: applied` (job-input facts present), and, for a scoped packet, `scope: applied` with the pins listed under "Scope stage". Record both values in the admission record. A packet without job-input facts is not a 046f/046g job packet.
