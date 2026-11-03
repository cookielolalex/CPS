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

## Revision after audit 048 (2026-11-03)

Audit 048 ([AUDIT_048.md](../evidence/AUDIT_048.md)) is complete. It confirmed every 046b score and found process gaps P-1 to P-9; see the addendum in [RESULTS_046B.md](RESULTS_046B.md). The plan is now:

1. **Semantic review before any admission (P-1 fix).** Candidate 046c (`research/guideline046_003/`) adds the audit's generic rules R1–R12 to FIELD_ROLES, with invented examples. An independent semantic reviewer must approve it; an interface review is not enough.
2. **Policy–expectation consistency gate (R13).** Before admission, a reviewer independent of the package author lists each convention used by the frozen expectations and cites the generator-facing sentence that yields it. A convention without such a sentence blocks admission unless declared complete alternatives cover it.
3. **Timing and sequencing (P-5).**
   - Declare a wall-clock bound per reader before generation. A run that exceeds it is a recorded timing failure.
   - Run reader A and assemble its carrier before starting B.
   - Pin AGENTS.md and the evaluator brief.
4. **Component-capable evaluator.** `research/evaluation/compare_source047.py` must be independently reviewed and frozen before use on a case with analysis components. It covers explicit anchor cells, component rows and links, including basis quantity, unit, raw text and location.
5. **Next source case.** 1141210 (cached XLSX with a unit-price analysis sheet; exposed at checkpoint 041) is prepared as a v2 packet. It needs fresh independent source expectations under 046c, the R13 gate and a frozen 047 before an A/B regression. Any result is labelled exposed development, not eligibility credit.

**Owner decisions requested**
- Placement of supply-basis qualifiers (R1b: C or D). It stays undecided until you rule.
- Whether customer-role inference (K/M/N filled from document furniture) is a critical error.
- The deployment runtime: sol6.1, or formally adopt `claude-opus-5-5`.
- Supplying deployment evidence: Data Center originals and eligibility evidence for at least 29 more pairs, and the 38 reserved input packets. Also an admitted export runtime (`@oai/artifact-tool` plus the Windows helper), or approval to build and review a portable writer.
