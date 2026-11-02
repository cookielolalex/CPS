# CPS local runtime

> Public export notice: this is the historical installed-baseline interface documentation. Development is PAUSED. The commands below are documentary examples, not current execution authority or a portable setup: the private manifests, qualification artifacts, dependency bindings and host runtimes are absent, and host paths are placeholders. Read [current local prerequisites](../../../docs/implementation/LOCAL_SETUP.md) before any future use. This baseline is distinct from the checkpoint045 semantic research route and is not deployment-approved.

This is a deterministic, read-only contract parser, not an LLM semantic executor. Importing `cps` performs no file access or execution. It never imports prior experiment scripts. Those scripts were reviewed only for source-reading and mechanical-assembly mechanisms.

Use the bundled Python executable `C:/CPS_LOCAL_USER/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe` with `-X utf8 -B`. From this directory:

```
python -X utf8 -B cps.py validate-manifest --manifest ../inputs/generation_exposed.json
python -X utf8 -B cps.py generate --manifest ../inputs/generation_exposed.json --output-dir fresh_output_dir --dependency-dir ../../deps
python -X utf8 -B -m unittest -v test_cps
```

The manifest contains `schema_version: 1`, exact absolute `allowed_source_paths`, and `contracts`. Each contract needs `case_id` and `sources` with `path`, `sha256`, and role `contract` or `original_annex`. Optional `split`, `scope_status` (`verified`, `partial`, `unverified`), `scope_reason`, `internal_project_id: {value,basis}`, and `adopted_sheets: [{source_path,sheet,authority,basis}]` describe independent scope evidence. `generation_mode: review_only` or `block_material_generation: true` prohibits material-row generation while preserving source review evidence. Worksheet adoption authorities are `contract_detail` or `verified_annex`.

The allowlist is caller-owned authority, not evidence that the scope is legally adopted. `adopted_sheets` records independently reviewed source-content roles; it does not certify legal adoption, version completeness, company supply responsibility or automatic release. The parser validates exact membership, source roles, file extensions, source hashes before/after reading, and forbidden path indicators. XLSX workbook metadata sheet names are checked before worksheet loaders decode content; XLS uses on-demand metadata names before any sheet iteration. A forbidden embedded 未填/已填/OK/drawing/original-materials sheet blocks the entire workbook. The pure snapshot parser repeats this guard defensively. It does not discover source files, follow workbook links, recalculate formulas, run macros, or read target workbooks. It does not write workbook artifacts. Source snapshots and row dispositions are included in each output for root-level artifact export and review.

Callable interface:

```python
import cps
cps.validate_manifest(manifest)              # structure/path policy, no source reads
result = cps.generate_contract(case, manifest, dependency_dir)
receipt = cps.batch_generate(manifest, fresh_output_directory, dependency_dir)
```

Every generated row has 17 `values` in the required order, a stable source-based `id`, `source_rows`, `source_sheet`, field `A` through `Q` provenance, commercial markers, review reasons and release state. Missing values are JSON null. Source numeric quantity values are copied without multiplication or rounding. Valid text numerals retain their exact text; malformed comma grouping is not interpreted numerically. G/H remain blank. Q requires independently reviewed detail-role evidence plus a numeric unit-price field; a numeric candidate estimate price alone is retained in raw evidence, not promoted into Q. Explicit model/brand/supplier columns are copied; remarks are preserved as source text, never guessed into these roles. Dedicated continuation fields fill only a blank field with a usable role; conflicting values, unusable caches and unreviewed Q roles remain in `continuation_anomalies` and trigger partial review. Continuation financial-cell markers are retained. L requires a declared namespace-specific identifier basis.

Material tables are detected from actual header cells, including combined two-row headers. Candidate sheets without adoption produce diagnostic `PARTIAL_REVIEW_REQUIRED` rows. All sheets preserve every physical row disposition. Analysis/resource tables are staged separately and never expanded into materials. Hidden sheets, merged conflicts, competing/incomplete scopes and unusable key caches require review. Numbered panel ancestry is accepted only when a panel-like heading has explicit compound-number descendants; unit or blank quantity alone does not establish a panel. Group allocation and physical inside-box relationships stay unproven. Description/specification/remark continuations retain source cells. Newlines prevent neighboring numeric fragments from fusing. Separate specification and remark streams are assembled independently.

`supported` means supported mechanical structure within explicitly supplied adoption evidence, not automatic-release approval. `partial` means candidate rows with unresolved scope/extraction conditions. `blocked` means no material rows are available or a manifest review-only hold applies. Every result remains `deployment_status: NOT_APPROVED` and requires independent semantic review. Blank output fields are unknowns, not extraction success. Coverage means readable physical-row dispositions are complete; it does not mean all material meanings were recovered.

Per-case JSON is deterministic: no runtime timestamp is embedded in structured results. The batch receipt records execution time and pins the input-manifest representation, runtime file and output files. The output directory must be empty; earlier runs cannot be overwritten. An independent repeat can compare exact per-case hashes.

Known limitations: legacy XLS formulas cannot be distinguished from saved cached values by xlrd; this is explicit in every XLS source. No automatic main-item/analysis linking or quantity-basis expansion, no contextual manufacturer resolution, no semantic C/D family splitting of combined descriptions, no proof of complete contract scope or revision compatibility. Chinese/flat numbering without explicit compound descendants does not receive invented panel ancestry. Diagnostic rows from multiple sheets retain their sheet scope and must not be treated as a reconciled combined order. Historical comparison and eligibility adjudication are separate evaluator responsibilities.
