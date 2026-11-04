# Harness for candidate 046f (draft)

The scripts are unchanged from 046e (`prepare_run.py`, `freeze_admission.py`, `freeze_outputs.py`, `make_release.py`, `audit_transcript.py`, `fullpath_check.py`), plus the new `make_job_config.py` (below). The two templates now name candidate 046f and `research/guideline046_006/package/`.

## Packet preparation adds context facts from a private per-job config

046f needs facts that the source does not contain (owner decisions O13–O17; FIELD_ROLES R47b, R48, R58). The source preparer adds them to `SOURCE_INVENTORY.json` `context_facts` before the packet is pinned, from one private per-job configuration file. The file and the resource files it names are company business data: keep them out of the repository, pin each by SHA-256 in the admission, and never pass anything else from them to a generator.

`make_job_config.py` turns the private job JSON into the inventory-builder config. The existing builders, `research/guideline046_003/source_prep/build_inventory_xlsx_v2.py` (`.xlsx`) and `build_inventory_v2.py` (`.xls`), copy the config's `context_facts` into the inventory verbatim (`'context_facts': cfg['context_facts']`), so they are used unchanged and were not copied here.

```sh
python3 -I -B research/guideline046_006/harness/make_job_config.py --job /abs/private/JOB.json --out /abs/new/BUILDER_CONFIG.json
python3 -I -S -B research/guideline046_003/source_prep/build_inventory_xlsx_v2.py --bundle DIR --config /abs/new/BUILDER_CONFIG.json --out NEWDIR
#   .xls sources: build_inventory_v2.py with the same arguments; the config's "builder" key names the right one
```

The tool prints hashes and fact names only, never private values. It refuses (exit 1, JSON on stderr, nothing written) a missing or unexpected key, a bad id, a job input the route would reject or hold (blank, control characters, edge whitespace, or a value starting with `=`, `+`, `-` or `@`), a source that is not an existing `.xlsx`/`.xls` file, a `carrier_path` that fails the writer's source-path rules (checked with the route's own `_source_shape`, including the forbidden-path words), a resource file with the wrong schema or shape, and an existing output.

Job JSON (`cps.job-config.v2`, one object per source packet):

| Key | Required | Becomes | Notes |
|---|---|---|---|
| `schema` | yes | – | `"cps.job-config.v2"` |
| `case_id` | yes | `context:case_identity` (`cps.internal_case_id`), inventory `case_id` | internal case id (L) |
| `customer_name` | yes | `context:customer_name` (`cps.job_input.customer_full_name`) | customer full name (M) |
| `project_name` | yes | `context:project_name` (`cps.job_input.project_short_name`) | project short name (N) |
| `company_name` | yes | `context:company_name` (`cps.company_resource.company_name`) | J of the enclosure row when the source states no brand (R56) |
| `glossary_path` | yes | `context:glossary` (`cps.company_resource.glossary`) | absolute path of the owner-reviewed glossary, JSON `cps.company-glossary.v1`: `generic_prefix_words`, `enclosure_word`, `abbreviations[{device, abbreviation}]`, and `category_words` (R52 drops the category words the glossary lists) |
| `brand_table_path` | yes | `context:brand_table` (`cps.company_resource.brand_table`) | absolute path of the owner-reviewed brand table, JSON `cps.company-brand-table.v1`: `entries[{device, rating_band, brand, model}]` |
| `source_path` | yes | config `original` (`path`, `bytes`, `sha256`) | absolute path of the source workbook; the extension picks the builder |
| `source_kind` | yes | config `source_document_kind` and the start of `adoption_basis` | `"材料清單"` (company material list, primary when present, R47b) or `"contract"` |
| `carrier_path` | yes | inventory `carrier_source.path` | the source's original canonical Windows path, provenance only (`X:\…\file.xlsx`); the writer requires that form |
| `family_id` | no | inventory `family_id` | default `case_id` |
| `adoption_status` | no | inventory `adoption_status` | `verified`, `partial` or `unverified` (default) |
| `adoption_basis` | no | inventory `adoption_basis` | appended after the source-kind sentence |
| `views` | no | builder `views` | `"auto"` (default) or the builder's view list |
| `provenance` | no | the facts' `basis` | `job_inputs`, `glossary_review`, `brand_table_review`: who supplied the inputs and the owner review record of each table. When absent, each basis says so |

Each fact gets `basis` (what it is, under which decision and rule, and who supplied it) and `authority_pins`. The job inputs and the company name pin the SHA-256 of the job JSON. The glossary and brand table values are the files' JSON re-serialised as compact JSON text (no whitespace, key order kept). Their `basis` states the SHA-256 of the file bytes and of the embedded text, and `authority_pins` holds both. The config also records `job_config_sha256` and `resource_files_sha256`; the builders ignore those keys and `schema`, `builder` and `source_document_kind`.

A job with both a 材料清單 and a contract needs one config, and so one inventory, per source. The route checks a response against one inventory, so a response cannot yet cite the contract to resolve a doubt the 材料清單 leaves (R47b); see the engineer's report. A job missing a required key is held: do not generate with a missing job input or resource, and never fill one from a letterhead, a historical 未填 or memory.

`EXAMPLE_INVENTORY.json` in the package shows the resulting shape with invented values (an invented 材料清單-style source).

## Admission and export notes

- Pin the guideline package, route v4.1 (`package/tools/cps046b_route.py`, `cps046f-route.v4.1`), the per-job config, each resource file, the evaluator and its metric in the admission before any generation.
- Route v4.1 warns, and does not reject, for the three documented relaxations: `O13_SELECTION_EVIDENCE_M_N` (M/N from job inputs), `R57_NULL_C_RESEARCH_DRAFT` (a null C on a `research_draft` row) and `O16_Q_UNVERIFIED_ADOPTION` (Q under unverified adoption).
- The route's `convert` receipt reports each class (`o13_m_n_selection_evidence`, `r57_null_c_research_draft`, `o16_q_unverified_adoption`) and the overall `export_mode_required`; use the overall value. Carriers that need `v2` are exported with `research/export/writer_portable.py --mode v2`; the unchanged writer004 gate refuses them (`SELECTION_ONLY_ENGINEERING_ID`, `UNRESOLVED_ITEM_MUST_BE_HELD`). The portable writer is not admitted yet.
- `freeze_admission.py` still writes the 046b admission schema name; the plan fields in its config name the candidate.
