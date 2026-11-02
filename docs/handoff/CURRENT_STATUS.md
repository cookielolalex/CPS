# Current CPS status

Snapshot prepared on **2026-11-02 (Asia/Taipei)** from the completed checkpoint 045 and the subsequent explicit user pause. Start here, then read [Evaluation](EVALUATION.md), [Decisions and constraints](DECISIONS.md), and [Resume plan](RESUME_PLAN.md).

**Development is paused. CPS is not ready for unattended deployment.** The user paused development after checkpoint 045; the scheduled refinement automation was also paused. Publishing this repository is a documentation handoff, not a request to resume development. Do not start implementation, model trials, investigation, testing, or scheduled runs until the user explicitly resumes them.

## What CPS is meant to produce

CPS means Contract Parsing System. Its goal is to produce a 未填 supply worksheet from the contract. Drafters should receive a material/supply list in the agreed format and modify it into 已填. A 未填 is not a whole-project price-negotiation worksheet. Unsupported fields remain unknown with a recorded reason; they must not be filled from later project outputs.

The frozen installed runtime, experimental research routes, historical target qualification, and deployment acceptance are separate. A research candidate passing a parser or workbook test does not replace the installed runtime or become qualified for production.

## Latest measured result

Checkpoint **045**, source case **1140908**, completed two separate original readings of the same frozen contract and protocol. Both reached saved workbook assembly. Evaluation was against independently prepared source expectations, **not against an independently eligible historical 未填**.

| Measure | Reading A | Reading B |
| --- | ---: | ---: |
| Canonical source core | 155/176 (88.068182%) | 147/176 (83.522727%) |
| Required core threshold | At least 175/176 | At least 175/176 |
| Source-only case accepted | No | No |
| Demand rows correctly corresponded | 47/47 | 47/47 |
| Units and quantities correct | 47/47 each | 47/47 each |
| Mandatory manual obligations passed | 9/12 | 9/12 |
| Critical factual errors found in that review | 0 | 0 |

Both readings failed the unchanged 99% core rule and mandatory raw/nonitem/manual gates. Zero critical factual errors does not waive those failures. Saved-workbook, scoped visual, and one exact-A assembly-repeat checks passed, but do not establish semantic correctness. See [the full metric interpretation](EVALUATION.md).

The main next work is to clarify material-name/specification field roles and preserve exact source representations through validated source-cell references. This is a prospective change; checkpoint 045 outputs and scores stay frozen.

## Qualification and available research population

| Population or result | Count | Meaning |
| --- | ---: | --- |
| Independently eligible development pairs | 1 | Exposed case 1131207; eligibility is not a performance pass |
| Independently eligible reserved pairs | 0 | No reserved answer has been opened |
| Performance-passed historical pairs | 0 | Deployment coverage is still unproven |
| Development candidate inventory | 153 | 118 tuning and 35 rolling; 139 assigned families |
| Reserved candidate inventory | 38 | 35 assigned families; answers remain closed |
| Older active comparison pool | 23 | Remainder of the original 30 after seven whole-case exclusions; not verified gold |

These are different populations and must not be added together or treated as independent successes. The older retained holdout subset is already target-exposed. It is not a substitute for the 38 reserved cases. Filename grouping and assigned family labels do not establish substantive independence. Case 1140908 is now exposed regression material; its family independence remains provisional.

## What is complete and what remains

Checkpoint 045 completed two original model calls, two original workbook exports, two source comparisons, and one separately marked exact-A assembly repeat. There were no output repairs, comparer retries, third reading, historical target comparisons, or newly admitted eligible pairs. All original outcomes were frozen before evaluation access.

The full programme audit at 045 adopted **PLAN revision 71** with zero mandatory amendments. It approved the research direction, not deployment or a new execution. The next regular full audit is **048**, or earlier after a critical finding or regression. The later pause takes precedence over all plan language that formerly authorized continuation.

Future work, only after explicit resume, is summarized in [Resume plan](RESUME_PLAN.md): one narrow source-reference/coverage change; at most one new A/B regression pair on 1140908; then the next full source trial is 1141208 once prerequisites are ready. The complete large-layout case 1140608 remains in the backlog.

## Local evidence map

The public repository contains a handoff and selected technical artifacts, not the private contract/answer corpus. A new agent can understand the state from these documents; actual source trials also require authorized access to the local evidence and dependencies. Do not reconstruct missing evidence from this summary or from historical answers.

Resolve these placeholders with the owner before using paths:

| Placeholder | Meaning on the original workstation |
| --- | --- |
| `{WORKSPACE}` | `D:\STMS Price Quote` |
| `{RUN}` | `{WORKSPACE}\runs\CONTRACT-WEITIAN-20261030-001` |
| `{REFINEMENT}` | `{RUN}\cps_refinement_001` |

| Local record | Purpose |
| --- | --- |
| `{REFINEMENT}\STATE.json` | Current programme state, including the explicit pause |
| `{WORKSPACE}\CPS\REFINEMENT_PROGRAMME.json` | Installed-project pointer to the programme and pause |
| `{REFINEMENT}\pause_after045_001\RECORD.json` | Pause authority; original state snapshots and unchanged closure pins |
| `{REFINEMENT}\PLAN_v71.md` | Exact adopted plan; private lead details are omitted from this public summary |
| `{REFINEMENT}\NEXT_CYCLE_BRIEF.md` | Closure-time next-step brief, overridden by the later pause |
| `{REFINEMENT}\checkpoint_045\current\REPORT.md` | Frozen checkpoint report |
| `{REFINEMENT}\SCORECARD_045.json` | Exact aggregate scorecard |
| `{REFINEMENT}\source_evaluation045_001\SAFE_MEASUREMENTS.json` | Detailed safe aggregate measurements |
| `{REFINEMENT}\source_evaluation045_001\FREEZE.json` | Final source-evaluation freeze; binds `MANIFEST_FINAL.json`, not the initial manifest |
| `{REFINEMENT}\course045_review001\DECISION.json` | Independent full-audit decision |
| `{REFINEMENT}\qualification045_001\ROOT_COURSE_ADOPTION.json` | Root adoption and limits of the full audit |
| `{REFINEMENT}\FINAL_VERIFICATION_045.json` | Closure-time verification; two mutable status files changed later solely to record the pause |
| `{REFINEMENT}\integration045_001` | Frozen 045 research implementation and execution evidence; old deadlines/admissions are expired |

Preserve the archived bytes. Do not edit old verification records to make them match current mutable state, and do not execute an archived invocation merely because its code is available.
