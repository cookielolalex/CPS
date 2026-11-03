# Continue without the original Data Center

Use the GitHub repository and the private `CPS_handoff_20261103_portable.zip`. The immediate review, implementation work and source-only tests on1140908 and1141208 do not require the original Data Center folders. The ZIP includes the exact selected contract bytes, source preparation material, existing source comparator/expectations and saved evaluation artifacts. It also includes original1140608 for the deferred four-sheet structure study, without admitting a model trial.

## Verified offline

| Check | Result |
|---|---|
|1140908 original XLS |1sheet,560positions; all560saved values/types/formula flags matched the frozen source snapshot;3pinned views|
|1141208 original XLS |3sheets including2empty,376positions,220nonempty;16formula records; stored cells matched the previous source census; complete inventory and2reconstructed views supplied|
|1140908 existing evaluation replay |Existing comparator and expectations reproduced the entire saved results for A155/176 and B147/176 exactly, excluding original invocation-binding metadata|
|1140908 saved workbook readback |A9,549 and B9,269 cells matched the saved assembly matrices; no formulas observed|
|Direct frozen manifest dependencies |210references in16selected source/evaluator/setup manifests;29missing project files added;0unresolved project file references in that audit.4historical executable/artifact-runtime pins are external environment requirements.|

The checks used separate source and evaluation processes under Python3.12.14 with site packages disabled and the ZIP's vendored readers. A Python file-open guard denied original-root access and external project-file reads. The source phase forbids reads of historical targets, prior model outputs and evaluator data. It is a scoped file-access test, not OS-level isolation or a new model trial.

## Start on another computer

1. Extract the ZIP to a short local path and open `START_HERE.md`. The original drive letters in frozen records are provenance. Resolve them through `RESOURCE_MAP.json`, and use the relative file pins in `private/PORTABLE_SOURCE_INPUTS.json` for selected source preparation. Do not rewrite old manifests in place.
2. From the extracted root run `python -B tools/verify_bundle.py`.
3. In a source-only verification context run `python -I -S -B public_repo/tools/verify_portable_bundle.py --bundle . --phase source`.
4. Separately, in an evaluation context run `python -I -S -B public_repo/tools/verify_portable_bundle.py --bundle . --phase evaluation`. This replays saved045 only. Do not provide its expectations, outputs or results to a fresh generator.
5. Follow [the next steps](RESUME_046.md). Read the generic candidate and its preliminary review findings, finish review/fixes and the narrow adapter, complete independent1141208source expectations, then freeze a fresh invocation. For generation use only the chosen contract packet plus the reviewed generic guideline/resources. Do not attach the full ZIP to a reader.

The bundled `xlrd`, `openpyxl` and `et_xmlfile` support the offline checks. Real trials still require an authorized AI session, current runtime and workbook export tooling, a reviewed adapter and fresh bindings. Legacy scripts with original paths/deadlines are historical references. Nothing in the portable checks qualifies a model, an amended guideline or a deployment.

The bundle does not replace the full project archive. Other development or reserved projects, mailbox/database eligibility investigations and any new historical target evaluation need additional authorized evidence.1141208historical未填 was not opened or bundled; its next planned test is source-only. The quote's adoption and rates remain unverified. All38reserved projects stay closed.
