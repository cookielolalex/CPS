> Historical045 snapshot retained. For the later agent-run Markdown candidate and interrupted046review, start with [current status](../docs/handoff/CURRENT_STATUS.md).

# Retained tests and verification limits

No CPS tests were executed during this documentation/export task. Development remains paused.

Existing synthetic baseline tests are retained alongside their original implementation so their imports remain understandable:

- [`test_cps.py`](../src/installed_baseline/runtime/test_cps.py): deterministic parser mechanics, source boundaries, continuations, caches, numeric representation and no-overwrite behavior.
- [`test_screen_targets.py`](../src/installed_baseline/eligibility/test_screen_targets.py): evaluation-only dimension-plus screening, formula-cache ambiguity, forbidden sheets and changed-source handling. This file has top-level test execution and writes `ENGINE_CONTROLS.json`; do not import it merely to inspect the package.

These suites do not test the latest semantic model, prove99%correctness, or qualify deployment. The latest route's source comparer, saved-cell checker, assembly-repeat checker and rendering helper are retained under `research`; they need the separately frozen private inputs and explicit execution authority. Actual visual inspection and semantic/manual review cannot be replaced by file existence, source-code presence or successful rendering.

For the next bounded step after explicit resumption, use the [resume plan](../docs/handoff/RESUME_PLAN.md): narrow invented fixtures for the changed source-reference/coverage route, exact unchanged-byte reuse, independent review, then at most one newly admitted1140908A/Bregression pair before the next distinct complete case.
