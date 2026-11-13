# Qualification in the maintainer's session: plan (O64, O65)

**Status: draft plan, 2026-11-13. Not reviewed. Nothing has been run.** No runtime, admission or ledger exists yet. The private operator procedure holds the exact paths, commands and configurations. This page is the public summary. It names cases only by counts and roles, and paths only by placeholders.

Placeholders:
- `<Q>`: the private qualification root on the maintainer's container.
- `<release clone>`: a separate git clone of this repository, checked out at the release commit.
- `<R>`: the private rehearsal root, separate from `<Q>`.

## 1. The decisions

- **O64, "Qualify here".** The qualification outputs are generated in the maintainer's Claude Code cloud session instead of on the Dot.
- **O65, "Yes, read-only".** Once every qualification output is frozen, fresh evaluator contexts may download the pool cases' historical 未填 files from their Google Drive project folders. They only read them.
- **What a pass covers.** A pass qualifies CPS as run from a Claude Code session. It does not qualify the Dot, which needs its own qualification on the same frozen system.

## 2. What stays the same

- Frozen candidate 046g (package manifest `bf06fae2…`, route v4.3).
- Admitted writer v2.8.2, saved_qa v6.4 and visual_qa v4.5 (`research/export/ADMISSION_WRITER_V28.json`).
- Admitted runner v4 (`deploy/run/cps_job.py`, `7505e98a…`) in qualification mode, with:
  - a release that says `RELEASED_FOR_QUALIFICATION`;
  - one qualification admission, frozen before the ledger's first entry;
  - the ledger;
  - `JOBS.json`.
- Two readers, A and B. Each scope reader, generator and visual reviewer is a fresh context. It gets only its prompt and the folders that prompt names.
- No retries for a better result. No edits to any output.
- Every output, including every reserved one, is frozen before any historical answer is opened.
- One scoring, in separate evaluator contexts, with frozen evaluator v4 (`compare_target050.py`, `fc723405…`) and aggregator v2 (`aggregate_qualification050.py`, `e5aa4fc7…`).
- The bar (O12, O31): for each reader, pooled matched/counted over the 30 pool pairs at least 0.95, and no case below 0.90. C/D is reported against 0.75 and does not gate (O24). The other elements are listed in section 6.
- The exclusions, the WT-A5 closure, the 38 reserved projects, the dimension-plus rule and every frozen output.
- The heartbeat stays paused. Private evidence stays off GitHub.

## 3. What changes from the Dot protocol, and why

| Dot protocol | Here | Why |
|---|---|---|
| The Dot operates the runner on its VM | The maintainer session operates it, through a private driver script that wraps the runner | O64 |
| A "new conversation" on the Dot | A Workflow subagent: a fresh context whose only user message is the prompt | This is how this platform makes a fresh context |
| The prompt is pasted as it is | The workflow harness adds one fixed preamble line and indents every line by two spaces. The platform also injects its standard context: the repository's `AGENTS.md`, the environment, the date, the model name and the lists of available tools and skills | The harness does this for every subagent. The prompt text itself is unchanged, and this is checked from each transcript |
| The prompt text is copied by the operator | The driver writes a small launcher script that holds the prompt as a string literal. The lane workflow runs it. No model retypes the prompt | Exact bytes by construction |
| Isolation evidence: attested record (O40), tools-used statement (O63) | The full transcript of every AI context is kept. Generator transcripts are frozen in the job folder (`finish --transcript`). A pinned audit checks every tool call | Transcripts are available here. An audit is stronger than an attestation |
| Generator model: the Dot's model | `claude-opus-5-5`, the model of the development trials | The session's model. Scores do not carry across models |
| Evidence goes to Drive per run (O43) | The container's disk keeps it. After the freeze, it is archived to the private Drive folder. Small ledger anchors are uploaded while runs go on | The disk survives a container restart. A Dot VM reset wiped its disk |
| Dot-specific gates: VM helper admission, probes P1–P4, reset drill | A rehearsal on exposed tuning cases in this environment (phase P2) | Those gates test the Dot's VM and helper, which are not used here |

These parts of the reset rules still apply in substance:
- O45: one replacement visual reviewer if a reviewer was cut off and wrote nothing;
- O46: a written output is never regenerated;
- O56: transcripts of interrupted conversations are kept;
- O57: a cut-off completion fails visual QA;
- O58: a context may be launched again only if none was opened;
- O61: at most two completion requests;
- O52: a conversation census for the owner.

## 4. Numbers

- `JOBS.json`: 53 cases. 36 are attempted jobs and 17 are nonattempts (O29).
- The 36 attempted jobs:
  - 15 non-reserved pool cases. One is a contract job, and 8 are large.
  - 15 reserved pool cases, 2 of them large.
  - 6 reserved cases outside the pool, 2 of them large. One is the pre-declared alternate of a duplicate-family pair.
- Runs: 72 (36 jobs × readers A and B). Reader A runs all come first.
- Nonattempt folders: 17, frozen once, under reader A.
- Fresh AI contexts, without restarts:
  - 24 scope readers (12 large jobs × 2);
  - 72 generators;
  - up to 72 visual reviewers;
  - about 240 operator steps. These run the driver only; they are not AI outputs.
- Scored runs: 60 (30 pool pairs × 2 readers). The 12 runs of the non-pool reserved cases are frozen for closure. They are not scored, and their targets stay closed.

## 5. Pre-registered rules

These are fixed in the admission before the ledger's first entry. They never change during qualification.

### 5.1 No retries

- A run that fails at any stage is frozen as it is, with its error.
- Nothing is regenerated, edited, re-saved or repaired.
- A run B never sees anything from run A, and no run carries anything into another.

### 5.2 Restarts (protocol rule 3, as the runner enforces it)

- A scope-reader or generator conversation may be restarted once per case and reader, and only before it wrote its file. "Before it wrote its file" covers three cases:
  - the conversation broke;
  - the platform failed;
  - it ended without writing its file.
- If the file exists, even partly written, there is no restart. The run goes on with `scope-finish` or `finish`, so a bad file becomes a recorded failure.
- The runner's two forms apply unchanged:
  - **Form 1:** freeze the folder, then prepare again under the restart jobs root.
  - **Form 2:** in place, after an agreed scope.
- The driver uses the restart automatically only for a broken conversation or an `INTERRUPTED` stage before any response. Any other technical stop goes to the owner, as the runner's command sheet says.

### 5.3 Container restarts

A restart kills running agents and commands. Files on disk survive.
- **Never resume a qualification workflow.** Resuming would replay cached results and silently start a second conversation for any agent that was running.
- The driver inspects every run that was in flight, then applies these rules:
  - **A runner command was killed.** The next command records the stage as `INTERRUPTED`. Before any response is frozen, the run may use its one restart (Form 1). After the response is frozen (that is, during `finish`), the run has failed. The runner allows no other outcome, and the ledger cannot be rolled back.
  - **A scope reader or generator was killed.** If its file was not written, record `interrupt` with the times from the transcript, then restart (5.2). If it was written, go on (5.2).
  - **A visual reviewer was killed.** If it wrote nothing, one replacement reviewer is allowed for that run (O45). If it wrote anything, freeze the run at `NEXT: VISUAL_REVIEW`: visual QA has failed.
  - **A context was launched but no conversation was opened** (the journal shows none). Launch it again (O58).
- Every such event gets a private incident record. The killed context's transcript is kept (O56).
- Fresh workflows then continue the remaining work.

### 5.4 Visual-review completion (O61)

- When `visual-record` refuses a review as incomplete, the same reviewer may be asked to complete it, at most twice. The request text is fixed and pinned. It contains only the runner's problem codes.
- A third refusal fails visual QA. So does a container restart during a completion (O57).
- **Mechanism.** Workflow subagents cannot be sent a follow-up from inside a workflow. The main session sends the completion request to the same reviewer by its agent id. The rehearsal must show that this reaches the same conversation.
- If it does not, completion is not available on this platform. An incomplete review then fails visual QA for that run. This choice is fixed before the admission.

### 5.5 Isolation audit

- **Who and when.** A pinned audit script reads every AI transcript. That covers scope readers, generators, visual reviewers, completions, interrupted contexts and the operator steps. It runs after each run is frozen, and again in full before `ALL_FROZEN.json`. One fresh auditor context rules on the calls the script cannot classify. It sees tool names and tool inputs, never any target. Its verdicts are frozen before any target is downloaded.
- **Allowed:**
  - a generator reads its run's `input/`, writes its `output/`, and runs `python3`;
  - a scope reader reads its two input files and writes its one response;
  - a visual reviewer opens only the listed PNG files and writes its review;
  - an operator step runs only the driver.
- **Breach:**
  - any read, listing or search of a path outside those, including the repository (the default folder of every subagent);
  - any connector, web, Drive, mail, GitHub, skill, artifact or agent or session tool;
  - any write into another job folder, the runtime or the evidence.
- **Deviation (recorded, not a breach):**
  - loading a tool schema without using the tool;
  - local task-list bookkeeping;
  - a scratch write outside the run folder;
  - a non-`python3` shell command confined to the run folder.
- **Consequences:**
  - A breach by a generator or scope reader fails the run. It is scored as the empty carrier, which gives 0 and fails the 0.90 floor.
  - A breach by a visual reviewer fails visual QA for the run.
  - Any context that opens a historical 未填 or target before `ALL_FROZEN.json` stops qualification. It goes to the owner (protocol rule 2).
  - Deviations are reported with counts and change no score.
- A call the auditor cannot clear counts as a breach.

### 5.6 Conversation census (O52)

- Every agent in every qualification workflow journal must match a driver record: an operator step, a launch, a completion or a replacement.
- Any other context found writing into, or producing an output for, a qualification job fails that case's run, and the owner is told.
- The owner gets the census summary to confirm before any target is downloaded.

### 5.7 What counts as a failed run

The run is frozen as it is, and these outcomes are fixed in advance:
- **No carrier, scored as the empty carrier.** This covers:
  - a stop or owner decision before `convert`;
  - a route check that fails;
  - an interrupted `finish` before the carrier;
  - a second broken conversation after the one restart;
  - an isolation breach by the generator or scope reader;
  - a prompt delivery that does not match the prompt file;
  - an unlogged conversation (5.6).
- **Carried, but a QA element fails.** This covers:
  - saved QA that is not evidence grade;
  - a visual QA failure: a failed item, the legibility bound, a review that is incomplete and cannot be completed, or a reviewer breach;
  - an interrupted `finish` after the carrier.

  The carrier is still scored. The QA element of the bar fails.

### 5.8 The gate

The result is **PASS** only if all of the following hold:
1. `ALL_FROZEN.json` lists all 72 runs (and any restarted predecessor folders) and the 17 nonattempts. `verify-frozen` passed on every folder before any target was opened.
2. All 30 pool targets pass the pre-registered checks before any comparison: hash, current template (O21), dimension-plus screen, internal design. Only the pre-declared duplicate-family alternate may replace its primary.
3. Aggregator v2 reports the historical-match element as passing for reader A and for reader B. Failed and breached runs enter as empty carriers.
4. There are zero unresolved critical errors on the 60 pool runs.
5. Every obligation is met on the 60 pool runs: raw, provenance, nonitem and manual.
6. Saved QA is evidence grade, and visual QA passed, on all 60 pool runs.
7. Assembly is repeatable: each of the 60 pool carriers re-assembles to the same saved matrices.
8. The isolation audit found no breach on a pool run, and the census has no unexplained conversation.

The result is **FAIL** if any of items 3–8 fails. It is **NOT DECIDED**, and goes to the owner, if item 1 or 2 fails. Item 2 failing would mean the pool falls below 30, and the pool has no margin.

### 5.9 Fixed settings

- **Release.** Release commit `4c40004` (`4c40004329e4f8897185f9b3f04c643e9da58dc3`), the commit that records O64 and O65. Every pinned file there equals its admitted bytes:
  - runner `7505e98a…` and visual template `07f7ea25…`;
  - generator template `eef06e73…` and scope-reader template `ab306792…`;
  - writer admission `cbd4afd5…`;
  - package manifest `bf06fae2…` and route `ba8414a0…`;
  - evaluator `fc723405…` and aggregator `e5aa4fc7…`.

  No pinned file has changed since the runner admission (`3dfcb16`). The commit must be pushed before the admission freeze. The runner runs from `<release clone>`, never from the main checkout, whose HEAD moves.
- **Model and effort.** Model `claude-opus-5-5`. One effort setting for every scope reader, generator and visual reviewer, given explicitly. The same setting applies to A and B.
- **What is recorded.** The generation record states:
  - the platform, the agent id, the times from the transcript, the prompt sha256 and the final message;
  - the features and tools the context had, truthfully: project instructions injected, web and connectors available, agent tools available.

  `transcript_status` is `exported`.
- **No changes mid-qualification.** The release, the admission and the runner are never changed during qualification. Runner v5 is never swapped in (O51).

## 6. Phases

| Phase | Entry | Work | Exit |
|---|---|---|---|
| P0 Plan review | This plan and the private procedure written | One independent fresh-context review. The owner answers the open questions | Review approves; answers recorded |
| P1 Build | P0 exit | Release clone; disk headroom; a clean dependency bundle; the driver, the audit and the launcher, with tests on invented data; runner and export self-tests; environment fingerprint | All tests pass; enough free disk; fingerprint recorded |
| P2 Rehearsal | P1 exit | `<R>` with its own release, admission, ledger and `JOBS.json`: 2 exposed tuning cases (one large and scoped, one ordinary) and 1 invented nonattempt; runs A then B through the real workflow shape; induced faults (a killed workflow, a killed generator); platform tests (section 7) | Every test passes, or the plan is amended and reviewed again; per-run disk and time measured |
| P3 Admission | P2 exit; owner go | Regenerate the runtime for `<Q>` and check it is byte-identical to the staged kit (sources, titles, tables, `JOBS.json`); freeze the evaluation plan; freeze the admission; write the release; independent hash-only pre-flight; upload hash anchors | Pre-flight passes; anchors on Drive |
| P4 Nonattempts | P3 exit | 17 nonattempts, reader A | 17 folders frozen and verified |
| P5 Run A | P4 exit | 36 runs in parallel lanes; freeze, verify and audit each | Every A run frozen, verified and audited; no lane running |
| P6 Run B | P5 exit | The same for B | Every B run frozen, verified and audited |
| P7 Close generation | P6 exit | Census; full audit; `ALL_FROZEN.json`; anchors and archive to Drive; owner census check (O52) | `ALL_FROZEN.json` anchored on Drive |
| P8 Evaluation | P7 exit | Section 8 | Every comparison and review frozen |
| P9 Decision | P8 exit | Gate record; public results; state update | Recorded |

Concurrency: at most 2 agents per workflow, at most 3 workflows, and at most 2 `finish` commands at once. No other heavy workflow runs during P5–P6.

## 7. The rehearsal tests (P2)

The rehearsal must show each of these:
1. A launcher script holding the prompt runs as a child workflow. The transcript's first message, with the preamble removed and each line de-indented, has exactly the prompt file's bytes.
2. The journal maps every label to one agent id. Labels are unique.
3. The generation record can be built from the transcript and passes `finish`, with the transcript frozen.
4. The main session can send a follow-up to a finished workflow reviewer by its agent id, and it reaches the same conversation (for 5.4).
5. A killed workflow is recovered by the state-aware driver without a second conversation for the same step. This includes a Form 1 restart and, on the scoped case, a Form 2 restart.
6. The ledger and job locks hold with parallel lanes. A busy refusal consumes nothing.
7. The isolation audit classifies every call of the rehearsal transcripts.
8. A `.xls` source builds through the clean bundle.
9. Disk, time and transcript size per run are measured, and the projection fits the free disk with margin.

## 8. Evaluation (P8), in outline

These are fixed in the evaluation plan **before `ALL_FROZEN.json`** (most of them already at the admission):
- the pool list and its canonical sha256 (`bb949367…`), and the alternate rule;
- for each pool case, the rule that names its target file in its project folder, taken from listing metadata already held, without opening any file;
- the pre-comparison checks and their consequences (gate item 2);
- the evaluator v4 invocation, one comparison per pool run (60), with the `normalized` mode governing;
- how the empty carrier is built for a failed run, with the reader id embedded;
- the aggregator v2 manifest and its call;
- the manual-review brief, the critical-error classes and the obligations;
- the method of the assembly-repeat and saved-QA re-run;
- the gate rule (5.8).

Then, in order:
1. Fresh evaluator contexts download the 30 pool targets read-only (O65), each into an empty folder. They pin each target's sha256 before any comparison. The 6 non-pool reserved targets stay closed.
2. An eligibility-role context runs the pre-comparison checks and freezes its record.
3. One evaluator context per case runs evaluator v4 on each frozen carrier of that case and does the manual review. It never repairs or rescores anything.
4. Saved QA re-runs, and the assembly repeat, in the evaluation role.
5. Aggregator v2 runs once over the frozen comparisons.
6. The gate record is written. The local qualification release keeps `RELEASED_FOR_QUALIFICATION`. What a pass enables is the owner's decision.

## 9. Evidence kept (private)

- The release, the admission, the runtime inputs and the evaluation plan.
- The ledger and the driver's own hash-chained record: every launch, agent id, transcript sha256, runner command and printed `run_record_sha256`.
- Every frozen job folder and nonattempt folder.
- Every transcript, including the operator steps and the interrupted contexts. Copies of the workflow journals.
- The incident records, the isolation audit, the census and `ALL_FROZEN.json`.
- The rehearsal evidence, kept apart.
- Everything is archived to the private Drive folder `CPS/qualification/`, verified by size and md5. Small hash anchors go up during the run.

## 10. What is reported publicly

Counts and hashes only:
- runs attempted, frozen and failed, by class;
- restarts and incidents;
- transcripts kept (O40);
- isolation deviations and breaches;
- per reader, the pooled score, the lowest case score and the number of cases below 0.90;
- critical errors, obligations, saved and visual QA, assembly repeat;
- C/D against 0.75;
- the gate result.

The public record never includes case ids, Drive ids, session or agent ids, private paths or business text.

## 11. Risks

- **Disk.** About 7 GB is free now. Development job folders took 85–264 MB each, so 72 runs need roughly 11–20 GB, plus the rehearsal and the archive staging. Space must be freed or added before P2 (blocking).
- **A container restart during `finish`** fails that run, with no remedy under runner v4. `finish` took 1–3 minutes per job in the development trial.
- **One failed pool run fails the gate** (0.90 floor), and the pool has no margin.
- **The platform cannot remove tools.** Every context can see connectors, web and agent tools. Its default folder is the repository, so a relative path or a path-less search reads the repository. Isolation is by instruction, and every call is audited after the run.
- **The injected `AGENTS.md`** is generic policy text, but it is not part of the reviewed package. The development trials had the same injection.
- **Unverified platform mechanics:** launcher scripts, label lookup and follow-up to a workflow agent. The rehearsal tests them, and the plan changes if they fail.
- **Long workflows, CPU contention and model fallback.** Model fallback is recorded per message and reported.
- **Drive uploads** need the owner's approval per file.
- **Reserved targets** may turn out ineligible when opened (old template). That makes the result NOT DECIDED, not PASS.
- **A scope-tool hold** sends a case to the owner. It is frozen as it is.

## 12. Open questions for the owner

1. Which effort setting for the AI roles? Recommended: the one the development trials used, given explicitly.
2. Accept the workflow harness's preamble, indentation and injected platform context as the "fresh context"? Recommended: yes. The alternative is a configuration change: a custom agent type without project instructions.
3. O63 asks every prompt to request a tools-used statement. The pinned templates do not, and cannot change. Accept the full transcript audit in its place? Recommended: yes.
4. If a workflow reviewer cannot be sent a follow-up, accept "incomplete review fails visual QA" (no completion)? Recommended: yes.
5. Keep the O52 owner check as a census confirmation before target downloads? Recommended: yes.
6. Confirm that the Dot-specific gates (VM helper admission, probes, reset drill) are replaced here by the rehearsal.
7. Pause the maintainer's scheduled Dot-mailbox check and the VM-helper workflow during P5–P7?
8. Disk: which old private working folders may be archived to Drive and removed locally to make room?
9. What does a pass enable: who runs everyday jobs while the Dot is unavailable, and under which release status?
