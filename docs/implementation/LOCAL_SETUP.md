# Local continuation prerequisites

Development is paused. Reading this handoff and validating its packaging are allowed by the upload task; running CPS, changing its implementation, conducting source investigations, or starting scheduled refinement requires the user's explicit resume instruction. The public repository contains historical source and documentation, not ready-to-run deployment configuration.

## Environment and dependencies

The original research route ran on Windows using PowerShell 7.6.5, bundled Python and Node executables, a locally available Codex CLI, `xlrd` 2.0.2, `openpyxl`, and the separately supplied `@oai/artifact-tool` workbook library. The original artifact bundle was 26.1017.22136. Executable bytes and dependency source files were pinned in local manifests; the public export is not a claim that arbitrary versions are compatible.

No vendor libraries, binary executables, authentication material, machine settings or `node_modules` are included. Obtain dependencies through the authorized local environment or approved package channels after resumption, then create new exact bindings. Do not assume `@oai/artifact-tool` is freely available from a public package registry. Its loader and operation-marker requirements belong to the active artifact environment.

`C:\CPS_LOCAL_USER` and `D:\CPS_LOCAL_WORKSPACE` are deliberate placeholders in transformed source copies. They are not environment variables or usable paths. The original implementation was Windows-path-specific. Porting paths, subprocesses, dependency loading, timing or artifact APIs is a changed method requiring its own review and tests, not a transparent relocation.

## Which local state governs

On the source machine, resolve these logical roots:

| Logical root | Original role |
|---|---|
| `{WORKSPACE}` | Shared project workspace containing `CPS` and `runs` |
| `{RUN}` | `{WORKSPACE}/runs/CONTRACT-WEITIAN-20261030-001` |
| `{REFINEMENT}` | `{RUN}/cps_refinement_001` |
| `{PRIVATE_DATA}` | Owner-controlled Data Center, completed projects and approved database/mail evidence |

Read `{REFINEMENT}/STATE.json`, `{WORKSPACE}/CPS/REFINEMENT_PROGRAMME.json`, `pause_after045_001/RECORD.json`, `PLAN_v71.md`, `NEXT_CYCLE_BRIEF.md` and `FINAL_VERIFICATION_045.json`. The pause occurred after the final045 snapshot: two mutable status files were intentionally changed to record PAUSED; the closed045 evidence is unchanged. Do not interpret a historical closure-time hash for those current status files as a license to revert the pause.

The public code is mapped to original local files in `SOURCE_EXPORT_MANIFEST.json`. Source and export hashes differ where documented transformations were made, including host-path substitutions and a historical-reference notice. Exact public code identity does not establish that the full private candidate or environment is present.

## Data that must be restored separately

1. Recover the complete original contract and approved literal source packet for the selected case. Reverify source hashes, all sheets/cells, saved types, formula cache provenance and image ranges; do not copy only a favorable excerpt.
2. Recover the separately frozen expectations and comparer bindings in the evaluator role. Do not pass expected material values, private review or historical targets into preparation/generation. The public detail-only comparator is specific to case1140908; it must not be relabelled as a general evaluator for1141208 or component layouts.
3. Recover immutable baseline/candidate, input, dependency, runtime and output-freeze manifests through the local evidence map. The public package deliberately excludes executable allowlists and admissions. The hard-coded dependency manifest digest in `source_verify.py` is historical and will not match an invented replacement.
4. Preserve authoritative split/family manifests, exclusions and all38 reserved-answer closure. Current assignments are not proof of family independence or historical stage compatibility.
5. Use a fresh owned run/output directory, exact new candidate and evaluator freeze, independent review, current invocation proposal and the actual native producer/consumer date/reserve check before any real call. The old045 clock and admissions cannot be renewed.

The historical complete path reserved at least735seconds per reading, with at least2130seconds remaining before A and1395before B, and a600second model plus5second own-child cleanup bound. A changed path may require more time. The model runs A then B with identical input bytes and no feedback; at most two originals, no repairs/retries/third call, freeze every actual/failed/unattempted outcome before evaluation. Those limits are recorded method constraints, not a ready-made permission to execute.

## Packaging validation versus CPS testing

The public snapshot can be checked without importing or executing CPS: verify export hashes; parse Python with `ast.parse`; use a JavaScript syntax check without running a module; parse PowerShell text using its syntax parser; check JSON, relative documentation links and absence of private data. Do not use an import smoke test on every file: the legacy eligibility test module executes synthetic checks at import and writes its own result.

The existing synthetic baseline tests are retained next to their implementation for future use. They were not rerun for this handoff, do not test the current semantic reader, and cannot qualify deployment. The next046 work needs narrow new meaningful fixtures through its actual changed route, independently reviewed, while unchanged code is reused by hash.

No cloud worker can reproduce private-case scores from this repository alone. It can understand the state, inspect the implementation, and plan the next bounded work; running source trials additionally requires owner-approved private evidence and execution access.
