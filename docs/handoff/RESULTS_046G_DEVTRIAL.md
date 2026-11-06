# Candidate 046g development trial (2026-11-06)

**Scope.** This is development evidence only. It earns no qualification credit, and no case can be recorded as passed.
- **Candidate.** Frozen candidate 046g (manifest `bf06fae2…`, route v4.3).
- **Cases.** Nine exposed tuning cases (none reserved, none in the qualification pool):
  - five large workbooks that use the R59 scope stage, each with a real scope reader: 1131112, 1131207, 1140607, 1140808;
  - 1140304, which is large but unscoped;
  - four current-template development regressions: 1130803, 1131202, 1140506, 1141002.
- **Readers.** Reader A only, each a fresh generator context. Reader B was not run.
- **Runner.** Jobs ran through the operator job runner `deploy/run/cps_job.py` at `ee2cf25`. Exported with admitted writer v2.7.
- **Evaluation.** Scored with frozen evaluator v4 (`compare_target050.py`, `fc723405…`). The frozen package fixed that evaluator before generation; there was no separate admission file for this trial.
- **Evaluation-role contexts.** Three, each in a fresh context with the case's pinned historical target only. Every job folder was frozen (`cps_job.py freeze`) before the evaluation plan was written and before any evaluator access.

## Results (reader A, governing v4 `normalized`)

| Case | Packet | Matched / counted | Score | Rows target / CPS / paired | Gap-filled | C/D description (not gating) | Critical errors |
|---|---|---|---|---|---|---|---|
| 1130803 | full | 257 / 261 | 0.9847 | 64 / 64 / 64 | 1 | 45 / 64 = 0.703 | 0 |
| 1131202 | full | 462 / 473 | 0.9767 | 117 / 116 / 116 | 2 | 73 / 117 = 0.624 | 0 |
| 1140506 | full | 378 / 395 | 0.9570 | 95 / 95 / 93 | 0 | 69 / 97 = 0.711 | 0 |
| 1141002 | full | 603 / 628 | 0.9602 | 151 / 151 / 149 | 2 | 127 / 153 = 0.830 | 0 |
| 1140304 | full (large) | 341 / 352 | 0.9688 | 87 / 83 / 83 | 2 | 63 / 83 = 0.759 | 0 |
| 1131207 | scoped | 268 / 281 | 0.9537 | 67 / 67 / 66 | 2 | 56 / 68 = 0.824 | 0 |
| 1131112 | scoped | 323 / 326 | 0.9908 | 78 / 78 / 78 | 0 | 59 / 78 = 0.756 | 0 |
| 1140607 | scoped | 249 / 260 | 0.9577 | 61 / 61 / 60 | 1 | 44 / 62 = 0.710 | 0 |
| 1140808 | scoped | 302 / 316 | 0.9557 | 77 / 77 / 77 | 2 | 60 / 77 = 0.779 | 0 |
| **Pooled (9)** | | **3,183 / 3,292** | **0.9669** | | | **596 / 799 = 0.746** | **0** |

- **Case floor.** Every case is above the O31 case floor of 0.90. The lowest is 0.9537. The pooled reading over these nine exposed cases is 0.9669, but it is not the qualification gate: that gate is 30 independent pairs including reserved cases, both readers, computed only by the frozen aggregator.
- **Manual review.** 0 unresolved critical errors in every class, on all nine cases.
- **Obligations.** All met on eight cases. On 1140607 one non-critical obligation was missed: two templated I null reasons mention a remark that those rows do not have, although the I values are right.
- **Scope loss.** 0 on all four scoped cases. Each unmatched historical row traces to an in-scope source line.
- **Raw and census.** Every content cell has exactly one role, no demand cell goes uncited, and the route reported 0 violations on all nine.

## Generic classes of lost positions (from the three evaluation reports)

None is critical. Most are places where the creator's practice departs from the source or from the recorded rules.

All 109 lost governing positions (3,292 − 3,183) are classified below. The 203 description misses (799 − 596) are listed separately.

| Class | Positions | Package action |
|---|---:|---|
| Not-estimated line left unpaired by a C/D difference. The line has no identity field outside C/D, so the v3 gap fill cannot pair it; 8 of these trace to the R52 category-word gap | 40 | 046h: the R52 category-word gap (046g deferred item N7) |
| Panel name A or size B not derivable from the bound source, or a panel-level effect (one A boundary ambiguity, one v4 size unit) | 25 | none, except the A boundary (R56 wording) |
| Job-level K–O. The older target leaves K–O blank (one report's 7 positions in this class also include A left blank on an enclosure row), or the creator's form differs from the stand-in job input; CPS writes the job inputs (R48) | 22 | none (stand-in job inputs in this trial) |
| I/J `不含估價` on not-estimated lines, or enclosure J, where the creator left the cells blank (R55, R56 as written) | 15 | survey question |
| A zero-state line the creator wrote as a row (R50 excludes it: 4), or two source lines she merged (3) | 7 | survey question |
| **Total** | **109** | |
| C/D description (not gating): glossary device not reached, a leading heading-like segment, a glossary choice, the enclosure-row convention, reordered rating text | 203 | 046h glossary and R52 items |

**Cross-reader consistency.** On a line whose only noun is a Latin acronym (NFB, ELCB), one reader set C to the acronym and another set C to null. Both disclosed their choice under R24. The package should decide (046h).

## Export and visual QA

- **Saved QA.** Passed on both workbooks for all nine.
- **Visual review.** Done on two jobs, through the runner's `visual-record`, by fresh visual reviewers. Both FAILED. Both failures are recorded and frozen, not repaired.
  - **1131202.** Values were cut at the column edge: every 使用客戶 cell lost its first character, and one 型號 cell its last.
  - **1131112.** Two 單位 cells were cut. Each holds a unit followed by eight spaces, kept verbatim from the source (R57).
- **Cause.** The fixed O38 column widths. The cut was worse in the maintainer renderer than it would be on the Dot toolchain (one column unit is 5.55 pt there and 7.0 pt on the Dot).
- **Fix.** The owner decided "widen to fit" (O39), implemented as writer v2.8 / saved_qa v6.2 / visual_qa v4.2, not yet admitted. See `research/export/README.md`.
- **Detector gap.** visual_qa v4.1's `possibly_cut_cells` did not list the 1131202 cuts. Its estimate (2 units per wide character, times size / 11) was too low for the renderer used. v4.2 uses the conservative O39 estimate.

## Runner incidents and review

- **Commit mismatch during the trial.** The main checkout's HEAD moved to a WIP commit, and the runner refused (`REPOSITORY_COMMIT_MISMATCH`), as designed. All jobs were re-prepared from a worktree pinned at the release commit, with byte-identical inputs. Responses already written were copied unchanged.
- **Independent review of the runner** (2026-11-06, at `01eaf23`; the runner itself is unchanged since `ee2cf25`): **ADMIT_AFTER_LISTED_FIXES**, with 13 required fixes and 15 notes.
  - **Everyday jobs need R1–R10:**
    - re-verify scope inputs at `scope-finish`;
    - verify the run-record hash chain;
    - a frozen folder truly read-only and re-checked;
    - a job lock;
    - exactly-pinned generation folders;
    - visual review accepted only from a fresh-context reviewer;
    - item 8 not `n/a` when cut cells exist;
    - reviewed PNGs checked against the manifest;
    - the live release re-read at delivery;
    - every executed file pinned, on a clean tree.
  - **Qualification also needs R11–R13:**
    - a ledger across job folders;
    - an admission listed in the release that pins the tools and the evaluator;
    - a frozen generation record.
  - **Status.** The fixes are being implemented. A delta review follows. The runner is not admitted until then.
- **Open owner question (review 4(c)).** The Dot may not be able to export generator transcripts. Is an attested generation record acceptable evidence of generator isolation for qualification? The record holds the model, conversation id, times, prompt hash, features, the final message and `transcript_status: not_available`.

## Evidence

All case data, outputs, comparisons and manual reviews are private, outside the repository:
- the maintainer's `trial046g/jobsB/` (nine frozen job folders);
- `eval046g_dev/` (`EVAL_PLAN.json` sha256 `b29f1586…`, then per case `COMPARISON_A.json`, `EVALUATION_SUMMARY.json`, `MANUAL_REVIEW.md`).

This record holds counts only.
