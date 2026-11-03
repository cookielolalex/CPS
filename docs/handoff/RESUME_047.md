# Next bounded steps after the 046b trials

Read [the 046b results](RESULTS_046B.md) first. Its sections "What ran" and "Not attempted" record exactly what was done and what was left out.

1. **Run audit 048 now.** It was brought forward because 1140908 regressed against 045 (A −14, B −7 canonical core fields). The runtime also differed: the observed model was `claude-opus-5-5`, not sol6.1/xhigh. The audit reviews the whole programme: whether a runtime change alone explains the regression, the evaluator's limits (column-B pairing, merged-B rows, components turning the numeric gates false, canonical-only unsupported flags), and whether 1140908's frozen 043 expectations still match the 046b policy declarations.
2. **Fix only generic gaps, in a new candidate (046c), never in 046b.** The aggregate evaluator classes point to these:
   - allocation of rental/basis qualifiers to C or D, which affected both readers on 13 rows;
   - recording the protocol role in proofs for P2-class tokens (obligation S05 on 1141208);
   - customer roles (N) must not be filled from a letterhead;
   - D clause joiners;
   - pointers to unavailable standards.
   Each fix needs independent review and route tests before any new admission. Never repair or rescore the frozen 046b outputs.
3. **Do not run 1140908 again** to obtain a pass. Its one admitted 046b pair is used up. Choose the next development source case under the plan and the eligibility rules. Keep the 1140608 structure backlog.
4. **Run the export checks** in an admitted export runtime with `@oai/artifact-tool` and the Windows helper. Run the existing writer on the four frozen 046b carriers and do saved-cell and visual QA. This is assembly only: carrier bytes are unchanged and nothing is repaired.
5. **Keep in force:** the deployment bar, all 38 reserved answers closed, the case and dimension-plus exclusions, the WT-A5 closure, source/evaluation separation, and the paused heartbeat.

How to run a new trial: follow the `research/guideline046_002/harness/` sequence:

1. `prepare_run.py` for each reader.
2. One fresh generator per reader, using `GENERATOR_PROMPT_TEMPLATE.md`.
3. `audit_transcript.py` on each generator transcript.
4. `freeze_outputs.py`.
5. Route `convert` and the writer validation.
6. `make_release.py`.
7. Evaluation in a separate context using `EVALUATOR_BRIEF_TEMPLATE.md`.

Freeze an admission record with `freeze_admission.py` before any generator starts.
