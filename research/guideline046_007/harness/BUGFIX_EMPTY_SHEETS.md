# Bug fix: empty sheets refused by the scope stage (2026-11-13)

Harness of candidate 046g. Engineering fix found in qualification rehearsal R1, under owner decision O64. It changes no rule of the package, the route, the runner, the builders, the evaluator or the aggregator.

## Defect

- The inventory builders (`research/guideline046_003/source_prep/build_inventory_xlsx_v2.py` and `build_inventory_v2.py`) set a sheet's `in_scope` to `rows * columns > 0`. An empty sheet (no used cell) is therefore written with `in_scope: false`, no cells and, under automatic views, no views.
- `scope_tool.py` v2 (`cps046g-scope-tool.v2`) refused every inventory with an `in_scope: false` sheet (`FULL_INVENTORY_REQUIRED`). The check exists to reject an inventory that is already scoped, but it also caught the builders' empty sheets. `make_scoped_inventory.py` had the same check in `load_inputs`, which the build and `--verify` both use.
- Runner v4 `prepare` runs `scope_tool.py` on every job, small or large. On a workbook with an empty sheet it stopped with `STOP_SCOPE_TOOL_REFUSED`, before any AI context was opened. A rehearsal contract job (three sheets, two of them empty) stopped this way twice.
- A structure-only count shows that 4 of the 36 qualification sources have empty sheets, 3 of them pool cases. The frozen system would have failed those jobs on a pipeline bug, not on its reading.

## Why the harness and not the builders

- `in_scope: false` on an empty sheet is harmless everywhere else. The sheet has no cell and no view, so the census (`rows x columns` of the in-scope sheets equals the number of cells) is the same either way, and the route and the generator never see a cell of it.
- The builders are pinned in the release and in the qualification admission, and every inventory they have written (including the frozen ones) carries this rule. Changing it would change the inventory bytes of every source with an empty sheet, for no gain.
- On a scoped packet the route requires an in-scope sheet to have role `bill` or `analysis` (`R59_SCOPE_FACT_MISMATCH`). An empty sheet has role `other`, so it must be out of scope there in any case. Keeping it out of scope from the builder onwards is the consistent state.

## Fix

`scope_tool.py` v3 (`TOOL_VERSION = 'cps046g-scope-tool.v3'`):
- A sheet is *empty* when `rows * columns == 0` and no cell and no view lies on it (`empty_sheets`). The full-inventory check accepts an out-of-scope sheet only when it is empty. Any other out-of-scope sheet still refuses the inventory with `FULL_INVENTORY_REQUIRED`, and an inventory carrying `context:scope` is still refused with `ALREADY_SCOPED`. The order of the two checks is unchanged.
- An empty sheet keeps role `other` (the role v2 already computed for a sheet without rows) and `in_scope: false`, with its own reason: "other: an empty sheet (rows x columns = 0, no cell), which the builders write out of scope; never yields rows (R49)". It gets no flag (no `OTHER_ROLE_SHEET`, no `HIDDEN_SHEET`): it holds nothing to look at.
- Status `NOT_APPLIED`: every non-empty sheet is in scope as before; an empty sheet keeps the packet's flag (false as the builders write it), so the proposal agrees with the packet. v2 set every sheet to true.
- The digest still lists every sheet in workbook order, the empty ones included (0 rows, 0 columns, no rendered row). The scope reader answers for every sheet as before; the reader prompt already puts every sheet other than the bill sheet and an R51 analysis sheet out of scope. A reader that puts an empty sheet in scope disagrees on an `in_scope` flag, and the case is held for the owner as for any other sheet.

`make_scoped_inventory.py`: `load_inputs` applies the same acceptance rule (an out-of-scope sheet must be empty: no cell, no view, `rows * columns == 0`). The projection already kept such a sheet out of scope, with no cell and no view, so the scoped packet's census and the route's R59 checks hold. It has no version constant; the receipt records its sha256.

Unchanged: `scope_agree.py`, `SCOPE_READER_PROMPT_TEMPLATE.md`, `prepare_run.py`, `make_job_config.py`, the builders, the package (route v4.3), runner v4, the evaluator and the aggregator.

Equivalence. An empty sheet has no cell, so it adds no content cell, no BILL1 candidate or near candidate, no bill line, no analysis block, no link and no flag. Every value v3 computes for the other sheets is therefore the value it computes for the same workbook without the empty sheets. The only differences are the empty sheets' own entries (in the proposal, the digest, the decision's scope fact and the inventory's sheet list), the sheet indexes after them, and the hashes. On an inventory without an empty sheet, v3 computes exactly what v2 computed; only the version string and the tool sha256 in the proposal and digest differ.

## Tests

New suite `research/guideline046_007/route_tests/run_empty_sheet_tests.py` (invented workbooks only):

```sh
python3 -I -B research/guideline046_007/route_tests/run_empty_sheet_tests.py --work /abs/NEW_DIR --deps-bundle /abs/DEPS_BUNDLE [--soffice soffice]
```

It writes each invented workbook with and without empty sheets (one of them hidden), as `.xlsx` and as `.xls` (converted by LibreOffice), and prepares each exactly as runner v4 does: `make_job_config.py`, then the builder of the format with `python3 -I -S -B` (the unbound inventory stands in for `render_views.py`, which only binds image pins).
- Small job (contract job, three sheets, two empty; at most 2,500 content cells): the builder writes the empty sheets out of scope; the inventory equals the one without them after removing them; `check-inventory` on the full packet gives the same result (PASS, `scope: not_applied`, `policy_checks: applied`); `scope_tool.py` exits 0 with `NOT_APPLIED` and the same proposal and printed summary; the empty sheets stay out of scope in the proposal, with role `other`, the empty reason and no flag.
- Large job (material-list job, four sheets, two empty, more than 2,500 content cells): `PROPOSED` with the same proposal (bill sheet, end row, R51 values, roles, flags, holds, counts); the same digest apart from the empty sheets' entries; the same rules excerpt (byte-identical); `scope_agree.py` freezes an admissible decision with the same scope fact, tool flags and role differences; `make_scoped_inventory.py` builds the same scoped packet (cells, views, sheets and context facts after removing the empty sheets) with the same statistics; `--verify` PASS against the pinned hash; `check-inventory` on the scoped packet gives the same result (PASS, `scope: applied`, `policy_checks: applied`).
- Refusals that must not change: the scoped packet, and the same packet without `context:scope`, are refused `FULL_INVENTORY_REQUIRED` by both tools (a non-empty sheet out of scope); a full inventory with empty sheets that carries `context:scope` is refused `ALREADY_SCOPED` by both tools; an out-of-scope sheet with `rows * columns == 0` that carries a view or a cell is refused `FULL_INVENTORY_REQUIRED` by both tools. A reader that puts an empty sheet in scope makes `scope_agree.py` hold the case. The tool is deterministic on an inventory with empty sheets.

Results on 2026-11-13 (maintainer machine; work folders outside the repository):
- `run_empty_sheet_tests.py`: 64 of 64 passed (`.xlsx` and `.xls`, small and large). The same suite run against the unchanged v2 tools fails: `FULL_INVENTORY_REQUIRED` on every workbook with empty sheets (11 failed checks before the large pairs stop).
- `run_scope_stage_tests.py`: 62 of 62 passed (unchanged suite, including `tool_refuses_scoped_inventory` with `FULL_INVENTORY_REQUIRED` and `tool_refuses_inventory_already_carrying_scope_fact` with `ALREADY_SCOPED`).
- `run_route_tests.py` (route v4.3, writer004 parity): 284 of 284 passed.
- `deploy/run/test_cps_job.py` (runner v4 end to end on invented jobs, from a clean local clone with the fix committed locally): RUNNER_TESTS_RESULT.
- A runner-level dry run (a scratch driver, not in the repository) ran runner v4 `prepare` and `scope-finish`, `render_views.py` included, on the same invented workbooks with and without empty sheets: DRYRUN_RESULT.
- `test_compare_source047.py` in the same folder tests the superseded evaluator compare_source047 and does not touch the harness; it needs a fixture carrier that the 046g route tests do not produce, and fails the same way on the unchanged tree.

## Files and pins

Changed or added files and their sha256 after the fix:

FILES_TABLE

Places that pin the old sha256 of `scope_tool.py` (`e9190c2f9f0caf9fb030d0aab2b1ab569e3606dff4d3d1752eb1b8b9c4d756af`) or `make_scoped_inventory.py` (`9a6fca56af4402f296286df3853688e6366a7970c3ea90f0bc6eec8ab392b2d9`) must be updated before the fixed harness is used: the release's `pinned_files_sha256`, the qualification admission's tool pins (and its freeze record), and the qualification toolkit's expected repository hashes. The harness README's validation record keeps the v2 hash as history (the v2 runs it records); its new line names v3. `scope_agree.py`, `SCOPE_READER_PROMPT_TEMPLATE.md` and every other pinned file keep their hashes.
