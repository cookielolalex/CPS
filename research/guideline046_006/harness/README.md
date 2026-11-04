# Harness for candidate 046f (draft)

The scripts are unchanged from 046e (`prepare_run.py`, `freeze_admission.py`, `freeze_outputs.py`, `make_release.py`, `audit_transcript.py`, `fullpath_check.py`). The two templates now name candidate 046f and `research/guideline046_006/package/`.

## Packet preparation adds context facts from a private per-job config

046f needs facts that the contract does not contain (owner decisions O13–O16; FIELD_ROLES R48, R58). The source preparer adds them to `SOURCE_INVENTORY.json` `context_facts` before the packet is pinned, from one private per-job configuration file. The file and the resource files it points to are company business data: keep them out of the repository, pin each by SHA-256 in the admission, and never pass anything else from them to a generator.

Config keys (`cps.job-config.v1`, one JSON object per job):

| Key | Required | Becomes context fact | Namespace | Value |
|---|---|---|---|---|
| `schema` | yes | – | – | `"cps.job-config.v1"` |
| `case_id` | yes | `context:case_identity` | `cps.internal_case_id` | internal case id (L); must equal the inventory `case_id` |
| `customer_full_name` | yes | `context:customer_name` | `cps.job_input.customer_full_name` | customer full name (M) |
| `project_short_name` | yes | `context:project_name` | `cps.job_input.project_short_name` | project short name (N) |
| `company_name` | yes | `context:company_name` | `cps.company_resource.company_name` | the company name (J on the enclosure row) |
| `glossary_file` | yes | `context:glossary` | `cps.company_resource.glossary` | path of the owner-reviewed glossary; its bytes become the value as JSON text `cps.company-glossary.v1` (`generic_prefix_words`, `enclosure_word`, `abbreviations[{device, abbreviation}]`) |
| `brand_table_file` | yes | `context:brand_table` | `cps.company_resource.brand_table` | path of the owner-reviewed brand table; its bytes become the value as JSON text `cps.company-brand-table.v1` (`entries[{device, rating_band, brand, model}]`) |
| `provenance` | yes | `basis` and `authority_pins` | – | who supplied the job inputs and when; the owner review record of each resource |

Each fact gets `basis` (who supplied it and under which decision) and `authority_pins` (the SHA-256 of the per-job config for the job inputs, and of each resource file for the resources). A job without one of the required keys is held: do not generate with a missing job input or resource, and never fill one from a letterhead, a historical 未填 or memory.

`EXAMPLE_INVENTORY.json` in the package shows the shape with invented values.

## Admission and export notes

- Pin the guideline package, route v4 (`package/tools/cps046b_route.py`, `cps046f-route.v4`), the per-job config, each resource file, the evaluator and its metric in the admission before any generation.
- The route's `convert` receipt reports `o13_m_n_selection_evidence`. Carriers with M/N selection evidence are exported with `research/export/writer_portable.py --mode v2`; the unchanged writer004 gate refuses them (`SELECTION_ONLY_ENGINEERING_ID`). The portable writer is not admitted yet.
- `freeze_admission.py` still writes the 046b admission schema name; the plan fields in its config name the candidate.
