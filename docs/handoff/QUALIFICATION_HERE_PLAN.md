# Qualification in the maintainer's session: plan (O64, O65)

**Status: draft plan, revision 2, 2026-11-13. Not approved. Nothing has been run.** Revision 1 went to three independent critics (integrity, operations, gate). Their 57 findings are resolved in this revision; the private operator procedure holds a table with one row per finding. No runtime, admission or ledger exists yet. The private procedure holds the exact paths, commands and configurations. This page is the public summary. It names cases only by counts and roles, and paths only by placeholders.

Placeholders:
- `<W>`: the private qualification work area on the maintainer's container. It lies outside the session scratchpad and outside the platform's transcript folders.
- `<Q>`, `<R>`: the qualification root and the rehearsal root inside `<W>`. They never share a ledger.
- `<release clone>`: a separate git clone of this repository, checked out at the release commit, inside `<W>`.

## 1. The decisions

- **O64, "Qualify here".** The qualification outputs are generated in the maintainer's Claude Code cloud session instead of on the Dot.
- **O65, "Yes, read-only".** Once every qualification output is frozen, fresh evaluator contexts may download the pool cases' historical 未填 files from their Google Drive project folders. They only read them.
- **What a pass covers.** A pass qualifies CPS as run from a Claude Code session, with the model and effort recorded in section 5.9. It does not qualify the Dot, which needs its own qualification on the same frozen system.
- **What this qualification spends.** Opening the 15 reserved pool targets spends them (O25). A later qualification of the Dot on the same system could not use them as held-out pairs. This needs the owner's answer before the admission (section 12, question 10).

## 2. What stays the same

- Frozen candidate 046g (package manifest `bf06fae2…`, route v4.3).
- Admitted writer v2.8.2, saved_qa v6.4 and visual_qa v4.5 (`research/export/ADMISSION_WRITER_V28.json`).
- Admitted runner v4 (`deploy/run/cps_job.py`, `7505e98a…`) in qualification mode, with:
  - a release that says `RELEASED_FOR_QUALIFICATION`;
  - one qualification admission, frozen before the ledger's first entry;
  - the ledger;
  - `JOBS.json`.
- Two readers, A and B. Each scope reader, generator and visual reviewer is a fresh context. It gets only its prompt and the files and folders that prompt names.
- No retries for a better result. No edits to any output.
- Every output, including every reserved one, is frozen before any historical answer is opened.
- One scoring, in separate evaluator contexts, with frozen evaluator v4 (`compare_target050.py`, `fc723405…`) and aggregator v2 (`aggregate_qualification050.py`, `e5aa4fc7…`).
- The bar (O12, O31): 30 independently eligible, revision-compatible pairs, including 10 reserved (the pool has 15 reserved); for each reader, pooled matched/counted over the 30 pool pairs at least 0.95, and no case below 0.90. C/D is reported against 0.75 and does not gate (O24). The other elements are listed in section 5.8.
- The exclusions, the WT-A5 closure, the 38 reserved projects, the dimension-plus rule and every frozen output.
- The heartbeat stays paused. Private evidence stays off GitHub.

## 3. What changes from the Dot protocol, and why

| Dot protocol | Here | Why |
|---|---|---|
| The Dot operates the runner on its VM | The maintainer session operates it, through a private driver script that wraps the runner | O64 |
| A "new conversation" on the Dot | A Workflow subagent: a fresh context whose only user message is the harness wrapper around the prompt. If rehearsal test T14 passes, it runs as a pinned custom agent type with a reduced tool set (below) | This is how this platform makes a fresh context |
| The prompt is pasted as it is | The prompt reaches the context inside a fixed harness wrapper, and the platform adds its own context. Both are listed in full below | The prompt text itself is unchanged, and this is checked from each transcript |
| The prompt text is copied by the operator | The driver writes a small launcher script that holds the prompt as a string literal. No model retypes the prompt | Exact bytes by construction |
| Isolation evidence: attested record (O40), tools-used statement (O63) | The full transcript of every AI context is kept. Generator transcripts are frozen in the job folder (`finish --transcript`). A pinned audit checks every tool call and every injected item | Transcripts are available here. An audit is stronger than an attestation |
| Generator model: the Dot's model | `claude-opus-5-5`, the model of the development trials | The session's model. Scores do not carry across models |
| Evidence goes to Drive per run (O43) | The container's disk keeps it. Small ledger anchors go to a maintainer-only Drive folder during the run. The archive goes there after the decision | The disk survives a container restart. A Dot VM reset wiped its disk |
| Dot-specific gates: VM helper admission, probes P1–P4, reset drill | A rehearsal and probe runs on exposed tuning cases in this environment (phase P2) | Those gates test the Dot's VM and helper, which are not used here |

**What each fresh context receives besides the prompt.** Observed in this session's workflow transcripts on 2026-11-13. The rehearsal records the exact list and content hashes again, and the admission pins them:
- **The harness wrapper.** Before the prompt, a short block says that the text was computed by a workflow script, was not typed by the session's user, and carries no user authority. The harness indents every prompt line by two spaces. The subagent system prompt adds that such a note is not by itself a reason to skip the task.
- **The platform system prompt and environment.** This includes the working directory (the repository), the date, the model name, and a session scratchpad folder that every context is told to use for temporary files.
- **The repository's `AGENTS.md`**, injected as project instructions marked as overriding defaults. It is generic policy text and holds no case data, but it opens with "read these files before acting". It is not part of the reviewed package. Test T14 checks whether a custom agent type runs without it.
- **Tool and skill listings and connector instructions**, including web, Drive, mail, GitHub, task-list and agent tools, and the instruction text of the connected servers.
- **Session identifiers**: the session link, the account's organization id and the repository attribution lines.
- **A shell-first working steer** (auto mode).
- **The session's shared task list.** It is re-sent during the conversation, and any context can write to it. It is archived and emptied before P2, and nobody writes to it until `ALL_FROZEN.json` is anchored (section 5.10).
- **Notices during the conversation**: a changed file it had read, a finished background task, a long tool output saved to a file, and possibly a context summary on very long runs.

The development trials used a different subagent mechanism, the main session's Agent tool. It gave a pointer prompt with no wrapper and, at that time, an empty task list. Their injection was therefore not the same as here.

**The custom agent type (if T14 passes).** A user-level agent definition, not committed and pinned by sha256 in the admission. It allows only Read, Write, Edit, Bash, Glob and Grep, so it has no connector, web, task-list or agent tools. Its short neutral system prompt says to use only the paths the task names, for reading and for temporary files. T14 records which platform items still remain with it. If T14 fails, the default subagent type is used, with the full list above disclosed and audited.

These parts of the reset rules still apply in substance:
- O45: one replacement visual reviewer if a reviewer was cut off for a technical reason and wrote nothing;
- O46: a written output is never regenerated;
- O56: transcripts of interrupted conversations are kept;
- O57: a cut-off completion fails visual QA;
- O58: a context may be launched again only if none was opened;
- O61: at most two completion requests;
- O52: a conversation census for the owner.

## 4. Numbers and duration

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
- **Duration estimate.** One run takes about 40–90 minutes: prepare 1–4, scope reader 5–10, generator 20–45, finish 1–3, visual review 10–30, plus 3–4 operator steps. That makes about 70–100 run-hours, or 14–24 hours of wall time for P5–P6 at 4–6 runs in flight. Add P2 (about 10–14 hours, with the probe runs) and P8 (about 6–10 hours).

## 5. Pre-registered rules

These are fixed in the admission before the ledger's first entry. They never change during qualification. The evaluation plan (section 8) is part of the admission.

### 5.1 No retries

- A run that fails at any stage is frozen as it is, with its error.
- Nothing is regenerated, edited, re-saved or repaired.
- A run B never sees anything from run A, and no run carries anything into another.

### 5.2 Restarts (protocol rule 3, as the runner enforces it)

- A scope-reader or generator conversation may be restarted once per case and reader. It must have ended for a **technical** reason before it wrote its file.
- **Technical means positive evidence**, judged mechanically from codes and transcript markers, never from output content:
  - a container restart after the launch (the boot id recorded at the launch has changed); or
  - a platform API error that ended the conversation, recorded as such in the transcript (overload, rate limit, server or network error; the exact markers are pinned at the rehearsal).
- **Not technical, so a failed run with no restart:**
  - a skip or stop of the agent by a person or by the main session (the owner is asked not to use the skip or stop controls on qualification agents);
  - running out of context length;
  - a normal end of the conversation without the file;
  - any ending without positive technical evidence.
- If the file exists, even partly written, there is no restart. The run goes on with `scope-finish` or `finish`, so a bad file becomes a recorded failure.
- The runner's two forms apply unchanged:
  - **Form 1:** freeze the folder, then prepare again under the restart jobs root.
  - **Form 2:** in place, after an agreed scope.
- **Technical stops before any response.** After a recorded interruption, a killed `prepare`, or a technical `STOP_` at `prepare` (for example a render failure), the driver always takes the one Form 1 restart that the runner allows, and tells the owner. No case is left to a run-by-run decision. If the restarted folder stops again, it is frozen as a failed run and run B goes ahead.

### 5.3 Container restarts

A restart kills running agents and commands. Files on disk survive.
- **Never resume a qualification workflow.** Resuming would replay cached results and silently start a second conversation for any agent that was running.
- The driver records the boot id with every launch and every runner command. After a restart it inspects every run that was in flight, then applies these rules:
  - **A killed `prepare`.** The stage is recorded as `INTERRUPTED`, and the run takes its one Form 1 restart.
  - **A killed `scope-finish` or `finish`.** These stages freeze the response before anything else, so the run has failed. There is no restart. The runner allows no other outcome, and the ledger cannot be rolled back.
  - **A killed `visual-record`.** Visual QA has failed for the run.
  - **A killed scope reader or generator.** If its file was not written, record `interrupt` with the times from the transcript, then restart (5.2). If it was written, go on (5.2).
  - **A killed visual reviewer.** If it wrote nothing, one replacement reviewer is allowed for that run (O45). If it wrote anything, visual QA has failed.
  - **A context was launched but no conversation was opened** (no journal entry and no transcript). Launch it again (O58), once per attempt.
- Every such event gets a private incident record with the restart's time and the evidence of its cause. The killed context's transcript is kept (O56).
- Fresh workflows then continue the remaining work.

### 5.4 Visual-review completion (O61)

- When `visual-record` refuses a review as incomplete, the same reviewer may be asked to complete it, at most twice. The request text is fixed and pinned. It contains only the runner's problem codes.
- A third refusal fails visual QA. So does a container restart during a completion (O57).
- **Mechanism.** Workflow subagents cannot be sent a follow-up from inside a workflow. The main session sends the completion request to the same reviewer by its agent id. Rehearsal test T4 must show that this reaches the same conversation. **T4 is a hard exit condition of P2.** If it fails, the plan returns to review with a different reviewer design. There is no pre-accepted "no completion" fallback.
- **The reviewer's stated conversation id.** Every context can see the session's link. A reviewer may write it as its own conversation id. When the review states an id that differs from the reviewer's agent id, the driver records the review without the operator's id flag (the runner accepts this when the review states one). It records both ids privately and maps the review to its transcript in the census. This costs no completion and is not a visual QA failure.

### 5.5 Isolation audit

- **Who and when.** A pinned audit script reads every transcript in the window from the admission freeze to the anchoring of `ALL_FROZEN.json`. That covers scope readers, generators, visual reviewers, completions, interrupted contexts, operator steps and the main session itself. It runs after each run is frozen, and again in full before `ALL_FROZEN.json`. A tripwire in the driver also scans new transcripts at every step for forbidden tool names, and stops new launches at once if it finds one.
- **What it checks.** Every tool call, with every path normalized and resolved, including `cd` and relative paths. It also checks every item the platform injected: each injected item's type and content hash must match the pinned values for the role. A transcript line that cannot be decoded is an audit error that goes to the owner. It is never skipped.
- **Allowed:**
  - a generator reads its run's `input/`, writes its `output/`, and runs `python3`;
  - a scope reader reads its two input files and writes its one response;
  - a visual reviewer opens only the listed PNG files and writes its review;
  - an operator step runs only the two driver commands of its lane;
  - the main session uses only its listed records, the driver, the pinned completion text and the anchor uploads.
- **Provenance rule.** A read outside those sets is still allowed in two cases only:
  - the file is the platform's saved copy of a long output of the same context, named in an earlier tool result of the same transcript;
  - the file was created earlier in the same transcript, by a command whose inputs were all allowed, at a path no other transcript in the window wrote to. The audit builds a write index across all transcripts to check this.
- **Deviation (recorded, not a breach):**
  - loading a tool schema without using the tool;
  - reading the shared task list when it holds only the pinned content;
  - a scratch write outside the run folder that no other context touches;
  - a non-`python3` shell command confined to the role's files;
  - reading a repository file that the prompt itself names, at the release commit's bytes. These are generic, public files with no case data.
- **Breach:**
  - any other read, listing or search, including any other repository file (such as the files the injected `AGENTS.md` asks to read) and anything in the platform's transcript folders;
  - any connector, web, Drive, mail, GitHub, skill, artifact, agent, session or scheduling tool;
  - any write to the shared task list;
  - any write into another job folder, the runtime, the evidence or the ledger;
  - an injected item that does not match its pin (for example a task list that carries another context's writes, or a notice about another context's file).
- **Consequences:**
  - A breach by a generator or scope reader fails the run. It is scored as the empty carrier, which gives 0 and fails the 0.90 floor.
  - A breach by a visual reviewer fails visual QA for the run.
  - A breach that writes into another run's folder before that run is frozen fails that run too. Both are listed in `ALL_FROZEN.json`.
  - A write to the shared task list also fails every later qualification context that received the written content. New launches stop until the owner is told.
  - A write by an operator step or by the main session into a job folder, the runtime, the evidence or the ledger fails that run and goes to the owner. A read of run content by the main session is reported.
  - **Any read outside its role set by a qualification context, or a read of a non-qualification private path by the main session, is treated as possible answer access.** It goes to the owner, and protocol rule 2 applies (qualification stops) unless the owner, shown only the path class, rules otherwise.
  - Deviations are reported with counts and change no score.
- **Auditor.** One fresh auditor context per run rules on the calls the script cannot classify, in bounded batches. It sees tool names and tool inputs only, never results or targets. A call it cannot clear counts as a breach. A dead auditor is replaced once, only for the calls it left unruled. Its verdicts are frozen before any target is downloaded.
- **Measured first.** The rehearsal and probe runs (section 7) and the 9 development-trial generator transcripts are audited with the same script before the admission. Any benign pattern that recurs is resolved before P3, by the rubric or by the custom agent type, and never after.

### 5.6 Conversation census (O52)

- The census covers every transcript with any entry in the window, of any workflow, of the main session and of any other agent of this session.
- Every qualification agent must match a driver record, one to one, by workflow run, label and agent id: an operator step, a launch, a completion or a replacement.
- Any other context found writing into, or producing an output for, a qualification job fails that run, and the owner is told.
- The owner gets the census summary to confirm before any target is downloaded.

### 5.7 What counts as a failed run, and which carrier is scored

The run is frozen as it is, and these outcomes are fixed in advance. A pinned script writes each run's **scored carrier** into `ALL_FROZEN.json` before any target is downloaded: the frozen carrier's sha256, or `EMPTY` with its reason. For a case and reader, the scored run is the ledger's last `prepare` of that pair.
- **Carried.** The finish entry pins a carrier and its result is not a route-check failure, "not carried" or a convert-receipt mismatch. An interrupted `finish` counts as carried only if the carrier and the adapter receipt are both frozen, both parse, and the receipt's hashes match the frozen carrier, response and inventory, with policy checks applied.
- **No carrier, scored as the empty carrier.** This covers:
  - a stop before `convert`, including a killed `scope-finish` and a technical stop after the one restart;
  - a route check that fails, "not carried" or a convert-receipt mismatch;
  - an interrupted `finish` that does not meet the carried test;
  - a conversation that ended without its file for a reason that is not technical;
  - a second technical break after the one restart;
  - an isolation breach by the generator or scope reader, or contamination from another context;
  - a prompt delivery that does not match the prompt file;
  - an unlogged conversation (5.6).
- **Carried, but a QA element fails.** This covers:
  - saved QA that is not evidence grade, including a writer refusal or a stop after the carrier;
  - a visual QA failure: a failed item, the legibility bound, a review that is incomplete and cannot be completed, a killed review or `visual-record`, or a reviewer breach;
  - an interrupted `finish` that meets the carried test.

  The carrier is still scored. The QA element of the bar fails.

### 5.8 The gate

The result is **PASS** only if all of the following hold:
1. `ALL_FROZEN.json` lists the 72 runs (36 attempted cases × readers A and B), every restarted predecessor folder, and the 17 nonattempts (reader A only). `verify-frozen` passed on every folder before any target was opened.
2. All 30 pool targets pass the pre-registered eligibility checks before any comparison: identity (hash and Drive metadata), current template (O21), dimension-plus screen, revision compatibility, not internally designed, and the evaluator's own target checks. Only the pre-declared duplicate-family alternate may replace its primary, and only under the alternate rule (section 8).
3. Aggregator v2 reports the historical-match element as passing for reader A and for reader B. Failed and breached runs enter as empty carriers.
4. There are zero unresolved critical errors on the 60 pool runs. Unresolved means confirmed under the review rule of section 8; no fix is possible in qualification.
5. Every listed obligation is met on the 60 pool runs.
6. Saved QA is evidence grade, and visual QA passed, on all 60 pool runs.
7. Assembly is repeatable: each of the 60 pool carriers re-assembles to the same saved matrices.
8. The isolation audit found no breach on a pool run, and the census has no unexplained conversation.

Outcomes, in this order of precedence:
- **No PASS is possible, and the result goes to the owner,** if any context opened a historical 未填 or target before `ALL_FROZEN.json` (protocol rule 2), or a possible answer access was not cleared by the owner.
- **FAIL** if any element that needs no target fails: items 1, 4 to 8, or an empty carrier on a pool run (which cannot reach the 0.90 floor). This holds whatever item 2 shows.
- **NOT DECIDED**, and the result goes to the owner, if item 2 fails and no permitted alternate swap fixes it. No comparison and no aggregator run in that case, and the owner sees the eligibility record only, without scores. The pool is not refilled after answers are seen (O26).
- Otherwise **FAIL** if item 3 fails, and **PASS** if every item holds.

### 5.9 Fixed settings

- **Release.** Release commit `4c40004` (`4c40004329e4f8897185f9b3f04c643e9da58dc3`), the commit that records O64 and O65. It is on the public branch (checked 2026-11-13), and the pre-flight checks that again. Every pinned file there equals its admitted bytes:
  - runner `7505e98a…` and visual template `07f7ea25…`;
  - generator template `eef06e73…` and scope-reader template `ab306792…`;
  - writer admission `cbd4afd5…`;
  - package manifest `bf06fae2…` and route `ba8414a0…`;
  - evaluator `fc723405…` and aggregator `e5aa4fc7…`.

  No pinned file has changed since the runner admission (`3dfcb16`). The runner runs from `<release clone>`, never from the main checkout, whose HEAD moves.
- **Model and effort.** Model `claude-opus-5-5`. One effort setting for every scope reader, generator and visual reviewer, the same for A and B. Rehearsal test T11 records how each setting shows in the transcript and agent metadata, and the setting is pinned from that. If a run's transcript shows a fallback model on any message, the run is scored as it is, with no retry. The gate record and the public report state the model mix per reader.
- **Injected context.** The sha256 of `AGENTS.md`, the custom agent definition (if used), the platform settings files and the emptied task list's reminder are pinned. The driver refuses every launch if any of them differs.
- **Runner environment.** Every runner command runs with an explicit, pinned environment (paths, locale, browser location, temporary folder), whatever shell issued it. Its names and values are part of the environment fingerprint.
- **What is recorded.** The generation record states, from each transcript itself:
  - the platform and agent type, the agent id, the times, the prompt sha256 and the final message;
  - the features and tools the context actually had: the tool list from the transcript's own snapshot plus any later additions, and every injected item with its content hash (in a sidecar file whose hash the record's notes give).

  `transcript_status` is `exported`.
- **No changes mid-qualification.** The release, the admission and the runner are never changed during qualification. Runner v5 is never swapped in (O51).

### 5.10 Session discipline (entry conditions of P2, rechecked at P3 and P5)

- The session's task list is archived privately and emptied, and its remaining reminder content is pinned. From P3 until `ALL_FROZEN.json` is anchored, nobody creates, updates or stops a task-list item.
- The maintainer's hourly mailbox scheduled task (O62) is disabled, and kept for its history. The VM-helper work is paused, with its workflows stopped. Neither resumes before P7 ends without the owner's word.
- No other CPU-heavy job runs during P2 measurements or during P5–P6.
- No commit, checkout, pull or edit happens in the main checkout, and no instruction or settings file changes, from P3 until `ALL_FROZEN.json` is anchored.
- The main session starts no background shell tasks during P5–P6. Their notices can reach other contexts.
- Historical answers and other answer-bearing material are not on the container (section 6, P1).

## 6. Phases

| Phase | Entry | Work | Exit |
|---|---|---|---|
| P0 Plan review | This plan and the private procedure | One independent fresh-context review. The owner answers the open questions | Review approves; answers recorded |
| P1 Build | P0 exit | Answer isolation: every answer-, target-, comparison-, expectation-, raw-row-, study- and prior-output-bearing folder is archived to a maintainer-only Drive folder, verified by md5, then deleted locally; a hash scan of the whole filesystem finds no registered target. Working area `<W>` outside the scratchpad; release clone; disk headroom; clean dependency bundle; the driver, the audit, the launcher and lane templates, and the evaluation scripts, with tests on invented data; runner and export self-tests from a throwaway clone; environment fingerprint; Drive upload limits measured | All tests pass; clean hash scan; enough free disk; fingerprint recorded |
| P2 Rehearsal | P1 exit; section 5.10 conditions met | `<R>` with its own release, admission, ledger and `JOBS.json`: 4 exposed tuning cases (one large and scoped, one ordinary `.xlsx`, one more `.xls`, one contract job), A then B, through the full workflow shape (3 lanes, 2 runs in flight each); induced faults; platform tests; probe runs on exposed cases in separate probe roots, so that at least 16 generators and 16 visual reviewers are measured | Every test passes, or the plan is amended and reviewed again; rates, disk and time measured |
| P3 Admission | P2 exit; owner go | Regenerate the runtime and check it is byte-identical to the staged kit except for the path prefix; freeze the evaluation plan; freeze the admission; write the release; independent hash-only pre-flight; upload hash anchors | Pre-flight passes; anchors on Drive |
| P4 Nonattempts | P3 exit | 17 nonattempts, reader A | 17 folders frozen and verified |
| P5 Run A | P4 exit; 5.10 rechecked | 36 runs in parallel lanes; freeze, verify and audit each | Every A run frozen, verified and audited; no lane running |
| P6 Run B | P5 exit | The same for B | Every B run frozen, verified and audited |
| P7 Close generation | P6 exit | Census; full audit; `ALL_FROZEN.json` with the scored carriers; anchors to Drive; owner census check (O52) | `ALL_FROZEN.json` anchored on Drive |
| P8 Evaluation | P7 exit | Section 8 | Every record frozen |
| P9 Decision | P8 exit | Gate record; public results; state update; bulk archive | Recorded |

Concurrency: each lane runs at most 2 runs in flight, through an explicit two-worker pool. At most 3 lanes run at once, so at most 6 runs and 6 AI contexts. The driver also holds global slots: at most 2 `prepare` and at most 2 `finish` or `scope-finish` at once. While the machine is loaded (load average above 3.5 or less than 3 GB of free memory), the driver waits before starting `prepare`, `scope-finish` or `finish`. A wait consumes nothing.

## 7. The rehearsal tests (P2)

The rehearsal must show each of these (the labels match the private procedure):
- **T1.** A launcher script holding the prompt runs as a child workflow. The transcript's first message, with the wrapper removed and each line de-indented, has exactly the prompt file's bytes.
- **T1b.** Every injected item is listed, with type and content hash, for every rehearsal transcript. With the task list emptied, its reminder is absent or has the pinned empty content. Whether a main-session background task's notice reaches other contexts is measured.
- **T2.** The journal maps every label to one agent id. Labels are unique across lanes and relaunches.
- **T3.** The generation record can be built from the transcript and passes `finish`, with the transcript frozen.
- **T4 (hard exit).** The main session can send a follow-up to a finished workflow reviewer by its agent id, and it reaches the same conversation (5.4). What reviewers write as their conversation id is recorded.
- **T5.** Recovery without a second conversation: a stopped lane (and whether its child workflows stop with it), a killed runner `prepare` and `finish`, a launcher that fails before any agent, a Form 1 and a Form 2 restart. What a stop or skip leaves in the transcripts is recorded, and so are the transcript markers of a platform error.
- **T6.** The ledger, job locks, run leases and global slots hold under the full shape (3 lanes, 2 runs in flight each). A busy refusal consumes nothing.
- **T8.** The isolation audit classifies every call and every injected item of every rehearsal, probe and development-trial transcript. The flag and breach rates are reported per role.
- **T9.** A `.xls` source and a contract job build through the clean bundle and the runner's pinned environment, with the runner started from an operator step.
- **T10.** Disk, time and transcript size per run are measured, and the projection fits the free disk with margin.
- **T11.** The pinned model and each candidate effort setting are accepted, and the transcripts and agent metadata show them.
- **T12.** A binary file of known sha256 (a bound source, not a target) downloads byte-exact through the Drive connector, and an anchor and an archive upload verify by md5 and size.
- **T13.** The evaluation scripts run correctly on invented fixtures.
- **T14.** The custom agent type: which tools, instructions and injected items remain, and whether it keeps the prompt delivery of T1.

## 8. Evaluation (P8)

Everything below is fixed in the evaluation plan **at the admission (P3)**, pinned by sha256 in it, and never amended after the ledger's first entry:
- the pool list and its canonical sha256 (`bb949367…`), the alternate pool's sha256, and the alternate rule;
- for each pool case, the declared target: its Drive file id, parent folder, title, modification time and size from listing metadata already held, and for non-reserved cases the registered sha256;
- the eligibility script and its exact rules: header layout, column use, dimension-plus statuses that pass, revision compatibility with its threshold, the internal-design threshold, the evaluator's own target checks, and the contract and quotation-bound cases;
- the scripts for download verification, the empty carrier, the scored-carrier list, the evaluator runs, the manifest and its verification, the assembly repeat and the saved-QA re-run, each with its exact command;
- the review briefs, the critical-error classes and the full obligation list with pass criteria;
- the audit rules for evaluation contexts, the order of stages below, and the gate rule (5.8).

Then, in order:
1. **Stage 0, no target opened.** Saved-QA re-run and assembly repeat (a same-environment repeat). A target-blind review of critical errors and obligations, from the source, the frozen response, the carrier and the inventory only: one fresh context per case, and every flagged error confirmed by a second fresh, target-blind context, with a disagreement counted as an error. The isolation and census results. This record is frozen. If any element here fails, the result is FAIL. The reserved targets then stay closed or are opened for diagnostics only, as the owner answers in advance (question 12).
2. **Download.** One fresh context per pool case downloads its target read-only (O65). It may call only the metadata and download tools, on its one declared file id. The bytes must equal Drive's md5 and size, and the id, parent folder, title and modification time must equal the held listing. A non-reserved target must also equal its registered sha256. If the Drive file has changed since the screen, the registered copy from the maintainer-only archive is used and the difference is recorded. A mismatch with no registered copy makes the target ineligible.
3. **Eligibility, in two steps.** First the checks that read no answer values (identity, header layout, dimension-plus screen), frozen on their own. Only if the duplicate-family primary fails one of those is the alternate's target downloaded (if the owner confirms O65 covers it, question 11) and put through the same checks. Then the remaining checks, frozen as the eligibility record. If a pool case is ineligible and no permitted swap fixes it, the evaluation stops here (5.8).
4. **Comparison.** A pinned script runs evaluator v4 on each of the 60 scored carriers (or the empty carrier), in a fresh evaluator context per case, and freezes the outputs. That context then reads the A/B row pointers only to find A/B errors, each confirmed from the source as in stage 0. It never repairs or rescores anything.
5. **Aggregate.** The manifest is built and verified against the scored carriers and the target pins. Aggregator v2 runs once over the frozen comparisons.
6. **Gate record.** It is written from the frozen records. The local qualification release keeps `RELEASED_FOR_QUALIFICATION`. What a pass enables is the owner's decision.

Rules for the evaluation contexts:
- They are audited like the generation contexts, with roles for download, eligibility, review and comparison, before the aggregator runs. Any Drive call other than the declared ones, or any read of another target, goes to the owner and is reported with the gate.
- A context that dies having written nothing is replaced once, with the same input. A partly written output is frozen as it is, and that case is NOT DECIDED and goes to the owner. Deterministic steps may run again only if they reproduce the same bytes.
- The evaluation brief allows exactly the case's pinned target and states that `ALL_FROZEN.json` is anchored.
- The other 23 reserved targets stay closed (22 if the alternate is used).

## 9. Evidence kept (private)

- The release, the admission, the runtime inputs and the evaluation plan.
- The ledger and the driver's own hash-chained record: every lane, lease, launch, agent id, boot id, transcript sha256, runner command and printed `run_record_sha256`.
- Every frozen job folder and nonattempt folder.
- Every transcript in the window, including the operator steps, the interrupted contexts and the main session's own, with each one's saved long-output files. Copies of the workflow journals.
- The incident records, the isolation audit, the census, the injected-item records and `ALL_FROZEN.json`.
- The rehearsal and probe evidence, kept apart.
- Everything is archived to a **maintainer-only Drive folder outside the Dot's shared folder**, verified by size and md5. The Dot's conversations must never be able to read these outputs, transcripts or evaluation files. Small hash anchors go up during the run; the bulk archive follows the decision.

## 10. What is reported publicly

Counts and hashes only:
- runs attempted, frozen and failed, by class;
- restarts and incidents, including container restarts;
- transcripts kept (O40);
- isolation deviations and breaches, by role;
- per reader: pooled matched/counted, C/D matched/counted against 0.75, the lowest case's matched/counted, and the number of cases below 0.90;
- the model mix per reader;
- critical errors, obligations met/total, saved and visual QA, assembly repeat (same environment);
- the gate result.

The public record never includes case ids, Drive ids, session or agent ids, private paths or business text.

## 11. Risks

- **Infrastructure failure.** A container restart during `scope-finish`, `finish` or `visual-record` fails that run, with no remedy under runner v4. These stages add up to about 3 hours of exposure across the 72 runs. The container restarted twice on 2026-11-13. At that rate, the chance that a restart fails at least one pool run is roughly 15–20%. One failed pool run fails the gate (0.90 floor), and the pool has no margin. The owner is asked to accept this before P3 (question 13).
- **Disk.** About 7 GB is free now, out of about 39 GB usable. Development job folders took 85–264 MB each. With transcripts in three copies, P5–P8 need roughly 20–22 GB, plus the rehearsal. Space comes from the answer-isolation cleanup and from owner-approved removals (P1). The driver refuses a new `prepare` when the remaining projected need does not fit.
- **The platform cannot confine file access.** Every context can reach the whole disk. The default subagent type also has connector, web, task-list and agent tools. Isolation is by instruction, by removing answers from the disk, by the custom agent type if T14 passes, by the tripwire, and by the full audit. One benign-looking call by any of about 168 contexts can still fail a pool run. The rehearsal and probes measure how often this happens, but they cannot rule out a rare pattern.
- **The injected context** is listed in section 3, and the owner decides whether to accept it (question 2).
- **Unverified platform mechanics:** launcher scripts, label lookup, follow-up to a workflow agent, the custom agent type, and what a stop or error leaves in a transcript. The rehearsal tests them, and the plan changes if they fail.
- **Long workflows and CPU contention.** These are handled by the slots and the load wait.
- **Drive uploads** need the owner's approval per file.
- **Reserved targets** may turn out ineligible when opened (old template, other revision). That makes the result NOT DECIDED, not PASS.
- **A scope-tool hold** sends a case to the owner. It is frozen as it is.

## 12. Open questions for the owner

1. **Effort.** Which effort setting for the AI roles? Recommended: the setting that reproduces the development trials, as test T11 identifies it.
2. **Fresh context.** Accept the harness wrapper and the injected platform context listed in section 3 as the "fresh context" of O64? Recommended: yes, with the custom agent type if T14 passes. Accept also that a read of a repository file the prompt itself names is a deviation, not a breach.
3. **O63.** O63 asks every prompt to request a tools-used statement. The pinned templates do not, and cannot change. Accept the full transcript audit in its place? Recommended: yes.
4. **O52.** Keep the O52 owner check as a census confirmation before the first target download? Recommended: yes.
5. **Dot gates.** Confirm that the Dot-specific gates (VM helper admission, probes, reset drill) are replaced here by the rehearsal and probe runs.
6. **Pausing other work.** Confirm that the hourly mailbox scheduled task (O62) is disabled and the VM-helper work paused from P2 until P7 ends. Without this the qualification cannot start.
7. **Answer isolation and disk.** Approve the private list of folders to archive to the maintainer-only Drive folder and delete locally (all answer-bearing material), and the list of reproducible working folders to delete.
8. **What a pass enables:** who runs everyday jobs while the Dot is unavailable, and under which release status.
9. **Skip and stop.** Agree not to use the skip or stop controls on qualification agents. Under 5.2, a skip or stop fails the run.
10. **Reserved targets.** Accept that this qualification spends the 15 reserved pool targets for any later qualification of the Dot on the same system, or define a new held-out set for it.
11. **The alternate.** Confirm that O65 also covers downloading the duplicate-family alternate's target, when the alternate rule is triggered.
12. **An early FAIL.** If an element that needs no target already fails at stage 0, keep the reserved targets closed (recommended), or open them for diagnostics only?
13. **Infrastructure risk.** Accept the estimated 15–20% chance that a container restart alone fails the gate (section 11)?
