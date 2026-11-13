# Qualification in the maintainer's session: plan (O64–O69)

**Status: draft plan, revision 3, 2026-11-13. Not admitted. Nothing has run on qualification inputs.**

How we got here:
- **Revision 1** went to three critics. Their 57 findings were resolved in revision 2.
- **Revision 2** went to one independent P0 review by two reviewers, one holistic and one on feasibility. Both approved it with listed fixes: 13 and 12 findings. This revision applies every fix, or says which later input superseded it. The private operator procedure holds one row per finding.
- **The owner's answers** to the plan's questions are recorded as O66–O69 (commit `7b58c35`).
- **A mechanics probe on invented data (P1a)** has tested the platform mechanisms the plan depends on (section 7).
- **The orchestration is simpler** than in revision 2. There are no operator AI contexts and no lanes. The main session runs the deterministic driver itself and launches each fresh context as its own workflow.
- **An independent coverage check** of this revision listed 20 items: 19 fixes, all applied here, and one note to keep a text unchanged.

No runtime, admission or ledger exists yet. The private procedure holds the exact paths, commands and configurations; this page is the public summary. It names cases only by counts and roles, and paths only by placeholders.

Placeholders:
- `<W>`: the private qualification work area on the maintainer's container. It lies outside the session scratchpad and outside the platform's transcript folders.
- `<Q>`, `<R>`: the qualification root and the rehearsal root inside `<W>`. They never share a ledger.
- `<release clone>`: a separate git clone of this repository inside `<W>`, checked out at the release commit.
- `<launch folder>`: one folder inside the session scratchpad. It holds only the launcher scripts of contexts in flight, because the platform's Workflow tool refused script paths in the work area. Of the places it accepts, the working directory is this repository's checkout, which must stay untouched, so the launchers go in the session scratchpad (P1a).

## 1. The decisions

- **O64, "Qualify here".** The qualification outputs are generated in the maintainer's Claude Code cloud session instead of on the Dot.
- **O65, "Yes, read-only".** Once every qualification output is frozen, fresh evaluator contexts may download the pool cases' historical 未填 files from their Google Drive project folders. They only read them.
- **O66, "Accept": isolation evidence.**
  - The full transcript of every AI context, plus a pinned audit of every tool call and every injected item, replaces O63's tools-used statement.
  - The owner's census confirmation before any target download replaces the O52 check.
  - The rehearsal and probe runs here replace the Dot-only gates.
  - A restricted agent type is used if it works. It does (section 3), except that the platform still injects `AGENTS.md`.
- **O67, "Agree": pausing other work.** From P2 to P7, the hourly Dot-mailbox scheduled task is disabled, the VM-helper work is paused and the session task list is frozen. The owner will not use the skip or stop controls on qualification agents.
- **O68, "Approve": answer isolation.** Every answer-bearing local folder is archived to a new maintainer-only Drive folder outside the Dot's shared folder, verified, and then deleted locally. Reproducible working folders are deleted.
- **O69, "Accept all": evaluation policy.**
  - (a) Opening the 15 reserved pool answers spends them. A later Dot qualification may reuse the same 30 pairs only on the unchanged frozen system.
  - (b) O65 also covers the duplicate-family alternate's target.
  - (c) If an element that needs no target fails first, the reserved targets stay closed.
  - (d) The owner accepted a 15–20% chance that a container restart fails the gate. **The measured risk is likely higher** (section 11). If it exceeds 20%, the owner chooses before P3 between re-confirming at the measured figure and first admitting a reviewed runner revision (section 11).
- **What a pass covers.** A pass qualifies CPS as run from a Claude Code session, with the model and effort recorded in section 5.9. It does not qualify the Dot, which needs its own qualification on the same frozen system.

## 2. What stays the same

- Frozen candidate 046g (package manifest `bf06fae2…`, route v4.3).
- Admitted writer v2.8.2, saved_qa v6.4 and visual_qa v4.5 (`research/export/ADMISSION_WRITER_V28.json`).
- Admitted runner v4 (`deploy/run/cps_job.py`, `7505e98a…`) in qualification mode, with:
  - a release that says `RELEASED_FOR_QUALIFICATION`;
  - one qualification admission, frozen before the ledger's first entry;
  - the ledger;
  - `JOBS.json`.
- Two readers, A and B. Each scope reader, generator and visual reviewer is a fresh context that gets only its prompt and the files and folders that prompt names.
- No retries for a better result. No edits to any output.
- Every output, including every reserved one, is frozen before any historical answer is opened.
- One scoring, in separate evaluator contexts, with frozen evaluator v4 (`compare_target050.py`, `fc723405…`) and aggregator v2 (`aggregate_qualification050.py`, `e5aa4fc7…`).
- **The bar (O12, O31).** 30 independently eligible, revision-compatible pairs, including 10 reserved (the pool has 15 reserved). For each reader, pooled matched/counted over the 30 pool pairs must be at least 0.95, and no case may fall below 0.90. C/D is reported against 0.75 and does not gate (O24). The other elements are listed in section 5.8.
- The exclusions, the WT-A5 closure, the 38 reserved projects, the dimension-plus rule and every frozen output.
- The heartbeat stays paused. Private evidence stays off GitHub.

## 3. What changes from the Dot protocol, and why

| Dot protocol | Here | Why |
|---|---|---|
| The Dot operates the runner on its VM | The maintainer's main session operates it, through a private deterministic driver that wraps the runner. No other AI context runs the driver | O64; fewer moving parts (P0 feasibility review) |
| A "new conversation" on the Dot | A Workflow subagent of the restricted agent type `cps-qual-ctx`: a fresh context whose first user message is the harness wrapper around the prompt. Each one is launched as its own top-level workflow | This is how this platform makes a fresh context |
| The prompt is pasted as it is | The prompt reaches the context inside a fixed harness wrapper, and the platform adds its own context. Both are listed in full below | The prompt text itself is unchanged; this is checked from each transcript (P1a: exact) |
| The operator copies the prompt text | The driver writes a launcher script that holds the prompt as an escaped string literal. No model retypes the prompt | Exact bytes by construction |
| Isolation evidence: attested record (O40), tools-used statement (O63) | The full transcript of every AI context is kept. Generator transcripts are frozen in the job folder. A pinned audit checks every tool call and every injected item | O66 |
| Generator model: the Dot's model | `claude-opus-5-5` at effort `xhigh`, the model and effort of the development trials (measured) | The session's model. Scores do not carry across models |
| Evidence goes to Drive per run (O43) | The container's disk keeps it. Small hash anchors go to a maintainer-only Drive folder at three points. The archive goes there after the decision | The disk survives a container restart. A Dot VM reset wiped its disk |
| Dot-specific gates: VM helper admission, probes P1–P4, reset drill | The P1a probe, plus a rehearsal and probe runs on exposed tuning cases in this environment (P2), plus an independent admission review of the built toolkit (P2x) | O66 |

**The restricted agent type.** It is a user-level agent definition, not committed, pinned by sha256 (`df063c56…`), and it never changes.
- **Tools:** Read, Write, Edit, Bash, Glob and Grep, plus the platform's hand-back tool. There is no connector, web, Drive, mail, GitHub, task-list, scheduling, skill or agent tool, and no tool-schema loader.
- **System prompt:** the definition's short instruction to use only the paths the task names, and temporary files only in the task's output folder, plus the platform's fixed workflow-subagent notes.
- **When it became available.** The platform loads agent definitions only at session start. So the type failed when it was first tried mid-session, and worked after the next container restart reloaded the registry (P1a).
- **Fallback.** If `cps-qual-ctx` is unavailable before P3, P3 waits. The general-purpose type is used only after the owner re-confirms O66's fallback, shown the measured task-list writes (8 of 132 default-type transcripts: 16 creates, 15 updates, 7 stops) and its 58-tool list. T1b, T8 and T14 are then re-run on that type, and the P2x review re-checks. There is never a switch after P3.
- **Why it is needed.** In this session's earlier workflow subagents of the default type, 8 of 132 transcripts held task-list writes (16 creates, 15 updates and 7 stops), two of them by review agents. Under 5.5 any such write is a breach, and the restricted type has no such tools.

**What each fresh context receives besides the prompt** (measured on the restricted type at P1a; the rehearsal records the exact list and content hashes again, and the admission pins them):
- **The harness wrapper.** Before the prompt, a fixed block says that the text was computed by a workflow script, was not typed by the session's user, and carries no user authority. Every prompt line is indented by two spaces.
- **A fixed hand-back note**, as a second message: the final report goes back through the hand-back tool.
- **The platform system prompt and environment.** That covers the working directory (the repository), the date, the model name, and a session scratchpad folder that the platform advertises for temporary files.
- **The repository's `AGENTS.md`**, injected as project instructions marked as overriding defaults. It is generic policy text with no case data, but it opens with "read these files before acting". **It is still injected for the restricted type**, so the "no `AGENTS.md`" part of O66 is not achievable here. No rule changes: any read it prompts outside the role's files is a breach.
- **Connector instruction text** of the connected servers. These are instructions only; no connector tool is callable.
- **Session identifiers:** the session link, the account's organization id and the repository attribution lines.
- **A shell-first working steer** (auto mode).
- **Not received by the restricted type** in the probe: tool-schema or skill listings, or deferred tools. The probe also showed no task-list reminder, but it was short. On longer runs, default-type contexts receive the reminder in an empty form even when the list is empty. The pins allow it absent or empty, and the rehearsal measures long restricted runs.
- **Possible notices** during the conversation: a changed file it had read, its own long output saved to a file, its own background task, and a context summary on very long runs. In this session, every one of 332 background-task notices in subagent transcripts belonged to that subagent's own task.

The development trials used a different mechanism, the main session's Agent tool with the general-purpose type. It gave a pointer prompt with no wrapper and a different system prompt. The rehearsal therefore compares the restricted type's behaviour on the same exposed cases with the development-trial summaries (target-free counts only).

These parts of the reset rules still apply in substance:
- O45: one replacement visual reviewer if a reviewer was cut off for a technical reason and wrote nothing;
- O46: a written output is never regenerated;
- O56: transcripts of interrupted conversations are kept;
- O57: a cut-off completion fails visual QA;
- O58: a context may be launched again only if none was opened;
- O61: at most two completion requests;
- O52, as replaced by O66: a conversation census for the owner.

## 4. Numbers and duration

- `JOBS.json`: 53 cases. 36 are attempted jobs and 17 are nonattempts (O29).
- The 36 attempted jobs:
  - 15 non-reserved pool cases. One is a contract job, and 8 are large.
  - 15 reserved pool cases, 2 of them large.
  - 6 reserved cases outside the pool, 2 of them large. One is the pre-declared alternate of a duplicate-family pair.
- Runs: 72 (36 jobs × readers A and B). All reader A runs come first.
- Nonattempt folders: 17, frozen once, under reader A.
- **Fresh AI contexts during generation**, without restarts. All of them come under the stop rule of 5.5:
  - 24 scope readers (12 large jobs × 2);
  - 72 generators;
  - up to 72 visual reviewers;
  - one auditor for each run whose audit has calls the script cannot classify, so up to 72.

  That is about 168–240 contexts, plus relaunches and replacements. Up to 144 completion turns are continuations of finished reviewers, not new contexts. There are **no operator contexts**: the main session runs the driver.
- Evaluation contexts: 30 downloads (31 with the alternate), 31 target-blind reviews, confirming reviews as needed, 2 eligibility runners, 30 comparisons and the evaluation auditors.
- Scored runs: 60 (30 pool pairs × 2 readers). The target-free stage 0 covers 62, adding the alternate's two runs. The other non-pool reserved runs are frozen for closure. They are not scored, and their targets stay closed.
- **Duration estimate:**
  - P1 build: about 1.5–3 days of session work, including the cleanup uploads that the owner approves.
  - P2 rehearsal: about 10–14 hours.
  - P2x review: 0.5–1.5 days, including fix rounds.
  - One run: about 25–80 minutes (prepare 1–4, scope reader 5–10 for large jobs, generator mostly 4–15 and up to about 50, finish 1–3, visual review 10–30).
  - P5–P6: about 40–80 run-hours, or 10–20 hours of wall time with up to 6 contexts in flight.
  - P8: 6–10 hours.

## 5. Pre-registered rules

These are fixed in the admission before the ledger's first entry, and they never change during qualification. The evaluation plan (section 8) is part of the admission.

### 5.1 No retries

- A run that fails at any stage is frozen as it is, with its error.
- Nothing is regenerated, edited, re-saved or repaired.
- A run B never sees anything from run A, and no run carries anything into another.

### 5.2 Restarts (protocol rule 3, as the runner enforces it)

- A scope-reader or generator conversation may be restarted once per case and reader. It must have ended for a **technical** reason before it wrote its file.
- **Technical means positive evidence**, judged mechanically from codes and transcript markers, never from output content:
  - **A container restart after the launch.** The boot id recorded at the launch has changed, there is no recorded result, **and** the transcript does not end with a normal final turn (a completed hand-back, or a normal end of turn with text).
  - **A platform API error** that ended the conversation, recorded as such in the transcript (overload, rate limit, server or network error; the exact markers are pinned at the rehearsal).
- **Not technical, so a failed run with no restart:**
  - a stop or skip of the agent by a person or by the main session. The transcript then ends with the platform's interrupt marker and the boot id is unchanged (measured at P1a);
  - running out of context length;
  - a normal end of the conversation without the file, even if a container restart followed;
  - any ending without positive technical evidence.
- If the file exists, even partly written, there is no restart. The run goes on with `scope-finish` or `finish`, so a bad file becomes a recorded failure.
- The runner's two forms apply unchanged:
  - **Form 1:** freeze the folder, then prepare again under a restart jobs root (`<reader>_restart1`, or `<reader>_restart2` after an orphan prepare, 5.3).
  - **Form 2:** in place, after an agreed scope.
- **Stops before any response.** After any `STOP_` or `INTERRUPTED` stage before a response, the driver always takes the one Form 1 restart that the runner's restart rule allows, and tells the owner. Prepare is deterministic, so this selects nothing. If the restarted folder stops again, it is frozen as a failed run and run B goes ahead.

### 5.3 Container restarts

A restart kills running agents and commands. Files on disk survive.
- **Never resume a qualification workflow.** Resuming would replay cached results and silently start a second conversation for any agent that was running.
- **The boot id.** The driver records it with every launch and every runner command. A changed boot id proves that every earlier process and workflow is dead, so recovery needs no waiting period.
- **The main session.** It resumes the qualification when it is next prompted. In this session, the last two restarts each brought it a system notice.
- **Rules for each run that was in flight:**
  - **A killed `prepare`.** The stage is recorded as `INTERRUPTED`, and the run takes its one Form 1 restart.
  - **A `prepare` killed after it created the job folder but before its ledger entry.** That prepare opened no AI context and selects nothing, so it is not counted as the pair's restart. The orphan folder gets a manifest and is listed as an unledgered predecessor. The pair is prepared again under `<reader>_restart1` (under `<reader>_restart2` if the orphan was itself in `<reader>_restart1`). The runner's restart rule then applies unchanged, and any restart it allows goes under `<reader>_restart2`. A second orphan of the same pair goes to the owner, with nothing consumed.
  - **A killed `scope-finish` or `finish`.** These stages freeze the response before anything else, so the run has failed, with no restart. The runner allows no other outcome, and the ledger cannot be rolled back.
  - **A killed `visual-record`.** Visual QA has failed for the run.
  - **A killed `freeze` that left no `FROZEN.json`.** The folder can never be frozen under runner v4. Gate item 1 fails, and so the gate fails.
  - **A killed scope reader or generator.** If its file was not written, and the technical test of 5.2 holds, record `interrupt` with the times from the transcript, then restart (5.2). If the file was written, go on (5.2).
  - **A killed visual reviewer.** If it wrote nothing, one replacement reviewer is allowed for that run (O45). If it wrote anything, visual QA has failed.
  - **A context that was launched but never opened a conversation** (no journal entry and no transcript). Launch it again (O58), once per attempt.
- Every such event gets a private incident record with the restart's time and the evidence of its cause. The killed context's transcript is kept (O56).

### 5.4 Visual-review completion (O61)

- **The rule.** When `visual-record` refuses a review as incomplete, the same reviewer may be asked to complete it, at most twice. The request text is fixed and pinned, and contains only the runner's problem codes.
- **Failures.** A third refusal fails visual QA. So does a container restart during a completion (O57).
- **Mechanism (P1a: works).** Only the main session can send a follow-up. It sends the completion request to the finished reviewer by its agent id, and the platform resumes that same conversation.
  - The platform delivers the request inside a fixed wrapper, and the reply comes back inside another. Both are pinned.
  - The resumed conversation is written to a second transcript file: a full copy of the earlier entries plus the new turn. The audit and the census read both files.
  - If the delivered text differs from the pinned text, the completion counts as used and visual QA fails.
- **Test T4 is still a hard exit condition of P2.** The probe used a default-type agent, so the rehearsal repeats it on the restricted type. If it fails, the plan returns to review with a different reviewer design. There is no pre-accepted "no completion" fallback.
- **The reviewer's stated conversation id.** Every context can see the session's link, and a reviewer may write it as its own conversation id. When the review states an id that differs from the reviewer's agent id, the driver records the review without the driver's `--reviewer-conversation-id` flag (the runner accepts this when the review states one). It records both ids privately, and the census maps the review to its transcript. This costs no completion and is not a visual QA failure.

### 5.5 Isolation audit

- **Who and when.** A pinned audit script reads every transcript in the window, from the admission freeze to the anchoring of `ALL_FROZEN.json`. That covers scope readers, generators, visual reviewers, completions, interrupted contexts, auditors and the main session itself.
  - The deterministic audit runs after each run is frozen, and again in full before `ALL_FROZEN.json`.
  - A tripwire in the driver scans new transcripts at every driver pass. It looks for any tool outside the role's agent type, any unpinned injected item, any change of the platform version recorded in the transcript, and any prompt-delivery mismatch. It stops new launches at once if it finds one, and the owner is told before anything else is launched.
- **What it checks.** Every tool call, with every path normalized and resolved, including `cd` and relative paths. Every injected item: its type and content hash must match the pinned values for the role, agent type and turn. A transcript line that cannot be decoded is an audit error that goes to the owner; it is never skipped.
- **Allowed:**
  - a generator reads its run's `input/`, writes its `output/`, and runs `python3`;
  - a scope reader reads its two input files and writes its one response;
  - a visual reviewer opens only the listed PNG files and writes its review;
  - an auditor reads nothing (its list is in its prompt) and writes only its verdict files;
  - every role hands back its report once, at the end;
  - the main session uses only its listed records, the driver, the pinned completion text, the anchor uploads, and its own background commands (the boot-id log and the driver's wake-up check).
- **Provenance rule.** A read outside those sets is still allowed in two cases only:
  - the file is the platform's saved copy of a long output of the same context, named in an earlier tool result of the same transcript;
  - the file was created earlier in the same transcript, by a command whose inputs were all allowed, at a path no other transcript in the window wrote to. The audit builds a write index across all transcripts to check this.
- **Deviation (recorded, not a breach):**
  - reading the shared task list while it holds only the pinned (empty) content;
  - a write in the session scratchpad, outside the launch folder, that no other context touches, and a listing of the scratchpad that shows only the context's own files and the launch folder's name;
  - a non-`python3` shell command confined to the role's files;
  - reading a repository file that the prompt itself names, at the release commit's bytes. These are generic, public files with no case data.
- **Breach:**
  - any other read, listing or search, including:
    - any other repository file (such as the files the injected `AGENTS.md` asks to read);
    - anything inside the launch folder (other contexts' prompts);
    - anything in the platform's transcript folders;
  - any connector, web, Drive, mail, GitHub, skill, artifact, agent, session, scheduling or tool-schema tool, and any background task started by a context other than the main session;
  - any task-list tool that writes, or that reads another task's output;
  - any write into another job folder, the runtime, the evidence or the ledger;
  - an injected item that does not match its pin, for example a task-list reminder that carries content, or a notice about another context's file.
- **Consequences:**
  - A breach by a generator or scope reader fails the run. It is scored as the empty carrier, which gives 0 and fails the 0.90 floor.
  - A breach by a visual reviewer fails visual QA for the run.
  - A breach that writes into another run's folder before that run is frozen fails that run too. Both are listed in `ALL_FROZEN.json`.
  - A write to the shared task list also fails every later qualification context that received the written content. New launches stop until the owner is told.
  - A write by the main session into a job folder, the runtime, the evidence or the ledger fails that run and goes to the owner. A read of run content by the main session is reported.
  - **Any read outside its role set by a qualification context, or a read of a non-qualification private path by the main session, is treated as possible answer access.** New launches stop, and it goes to the owner. Protocol rule 2 applies (qualification stops) unless the owner, shown only the path class, rules otherwise.
  - Deviations are reported with counts and change no score.
- **Auditor.** When a run's deterministic audit has calls it cannot classify, one fresh auditor context rules on them in bounded batches. It is launched as soon as the run is frozen.
  - It sees tool names and tool inputs only, never results or targets. A call it cannot clear counts as a breach.
  - While such a call involves a read outside the role's files, nothing else is launched until it is ruled.
  - A dead auditor is replaced once, only for the calls it left unruled.
  - Phase B opens only after every phase A verdict is frozen. Every verdict is frozen before any target is downloaded.
- **Measured first.** The audit is run, before the admission, on the rehearsal and probe runs (section 7), the P1a probes and the development-trial transcripts. Any benign pattern that recurs is resolved before P3 by the rubric, and never after. Zero breaches by restricted-type contexts in the rehearsal is an exit condition of P2.

### 5.6 Conversation census (O52, as replaced by O66)

- The census covers every transcript with any entry in the window: every workflow, every resumed-conversation file, the main session and any other agent of this session.
- Every qualification agent must match a driver record, one to one, by workflow run, label and agent id: a launch, a relaunch, a replacement, an auditor or a completion.
- Any other context found writing into, or producing an output for, a qualification job fails that run, and the owner is told.
- The owner gets the census summary to confirm before any target is downloaded.

### 5.7 What counts as a failed run, and which carrier is scored

Each run is frozen as it is, and these outcomes are fixed in advance. A pinned script writes each run's **scored carrier** into `ALL_FROZEN.json` before any target is downloaded: either the frozen carrier's sha256, or `EMPTY` with its reason. For a case and reader, the scored run is the ledger's last `prepare` of that pair.
- **Carried.** The finish entry pins a carrier, and its result is not a route-check failure, "not carried" or a convert-receipt mismatch. An interrupted `finish` counts as carried only if the carrier and the adapter receipt are both frozen, both parse, and the receipt's hashes match the frozen carrier, response and inventory, with policy checks applied.
- **No carrier, scored as the empty carrier.** This covers:
  - a stop before `convert`, including a killed `scope-finish` and a technical stop after the one restart;
  - a scope hold sent to the owner (`OWNER_DECISION`);
  - a route check that fails, "not carried" or a convert-receipt mismatch;
  - an interrupted `finish` that does not meet the carried test;
  - a run whose `finish` cannot be issued (an unexpected refusal that no reviewed driver fix clears), frozen with its file and no carrier;
  - a conversation that ended without its file for a reason that is not technical;
  - a second technical break after the one restart;
  - an isolation breach by the generator or scope reader, or contamination from another context;
  - an audit error on the generator's or scope reader's transcript;
  - a prompt delivery that does not match the prompt file;
  - an unlogged conversation (5.6).
- **Carried, but a QA element fails.** This covers:
  - saved QA that is not evidence grade, including a writer refusal or a stop after the carrier;
  - a visual QA failure: a failed item, the legibility bound, a review that is incomplete and cannot be completed, a completion whose delivered text differs from the pinned text, a killed review or `visual-record`, or a reviewer breach;
  - an interrupted `finish` that meets the carried test.

  The carrier is still scored. The QA element of the bar fails.
- **A run folder that cannot be frozen** (a killed `freeze` that left no `FROZEN.json`) fails gate item 1.

### 5.8 The gate

The result is **PASS** only if all of the following hold:
1. `ALL_FROZEN.json` lists:
   - the 72 runs (36 attempted cases × readers A and B);
   - every restarted or unledgered predecessor folder;
   - the 17 nonattempts (reader A only).

   `verify-frozen` passed on every folder before any target was opened.
2. All 30 pool targets pass the pre-registered eligibility checks before any comparison: identity (hash and Drive metadata), current template (O21), dimension-plus screen, revision compatibility, not internally designed, and the evaluator's own target checks. Only the pre-declared duplicate-family alternate may replace its primary. It may do so only under the alternate rule (section 8), and only if its own runs passed stage 0.
3. Aggregator v2 reports the historical-match element as passing for reader A and for reader B. Failed and breached runs enter as empty carriers.
4. There are zero unresolved critical errors on the 60 pool runs. A flagged error counts unless two further fresh, target-blind reviews both reject it. No fix is possible in qualification.
5. Every listed obligation is met on the 60 pool runs.
6. Saved QA is evidence grade, and visual QA passed, on all 60 pool runs.
7. Assembly is repeatable: each of the 60 pool carriers re-assembles to the same saved matrices.
8. The isolation audit found no breach on a pool run, and the census has no unexplained conversation.

**Stage 0** checks items 1 and 4 to 8 before any target is opened. It covers 62 runs: the 60 pool runs plus the alternate's two.

Outcomes, in this order of precedence:
- **No PASS is possible, and the result goes to the owner,** if any context opened a historical 未填 or target before `ALL_FROZEN.json` (protocol rule 2), or a possible answer access was not cleared by the owner.
- **FAIL** if any element that needs no target fails on the 60 pool runs. That means items 1, 4 to 8, or an empty carrier on a pool run, which cannot reach the 0.90 floor. It holds whatever item 2 later shows, and even when the failure lies only on the duplicate-family primary's runs: the alternate replaces a primary only for an ineligible target, never for a failed run. That choice is conservative. The reserved targets then stay closed (O69(c)).
- **NOT DECIDED**, and the result goes to the owner, if item 2 fails and no permitted alternate swap fixes it. In that case there is no comparison and no aggregator run, and the owner sees the eligibility record only, without scores. The pool is not refilled after answers are seen (O26).
- Otherwise **FAIL** if item 3 fails, and **PASS** if every item holds.

### 5.9 Fixed settings

- **Release.** Release commit `4c40004` (`4c40004329e4f8897185f9b3f04c643e9da58dc3`), the commit that records O64 and O65. It is on the public branch, and the pre-flight checks that again. Every pinned file there equals its admitted bytes:
  - runner `7505e98a…` and visual template `07f7ea25…`;
  - generator template `eef06e73…` and scope-reader template `ab306792…`;
  - writer admission `cbd4afd5…`;
  - package manifest `bf06fae2…` and route `ba8414a0…`;
  - evaluator `fc723405…` and aggregator `e5aa4fc7…`.

  No pinned file has changed since the runner admission (`3dfcb16`). The runner runs from `<release clone>`, never from the main checkout, whose HEAD moves.
- **Model and effort.** Model `claude-opus-5-5` (the session model). Effort `xhigh`, passed explicitly for every AI role, the same for A and B. P1a measured `xhigh` on every message of the probes and of the development-trial generators. If a run's transcript shows a fallback model, or another effort, on any message, the run is scored as it is, with no retry. The gate record and the public report state the model mix per reader.
- **Agent type.** `cps-qual-ctx` (definition sha256 pinned) for scope readers, generators, visual reviewers, auditors and every evaluation role except the download role. The download role needs the Drive tools, so it runs as the general-purpose type and is audited to its one declared file.
- **Injected context and platform.** These are pinned, and the driver refuses every launch if any of them differs:
  - the sha256 of `AGENTS.md` and of the agent definition;
  - the platform settings files that stay byte-stable across restarts (the others are recorded per boot, as accepted at the P2x review);
  - the platform's plugin and skill folders;
  - the Claude Code CLI version and entry file;
  - the allowed task-list reminder forms (absent, or empty).

  A container restart can bring a new CLI. If one does, the qualification stops and the owner is asked.
- **Runner environment.** Every runner command runs with an explicit, pinned environment (paths, locale, browser location, temporary folder), whatever shell issued it. Its names and values are part of the environment fingerprint.
- **What is recorded.** The generation record states, from each transcript itself:
  - the platform, the CLI version, the agent type, the agent id, the times, the prompt sha256 and the final message;
  - the features and tools the context actually had: the tool list from the transcript's own snapshot, and every injected item with its content hash (in a sidecar file whose hash the record's notes give).

  `transcript_status` is `exported`.
- **No changes mid-qualification.** The release, the admission, the runner, the driver and the agent definition are never changed during qualification. Runner v5 is never swapped in (O51).

### 5.10 Session discipline (entry conditions of P2, rechecked at P3, at P5 and after every restart)

- **The task list.** It was archived privately and emptied before P1a. From then until `ALL_FROZEN.json` is anchored, nobody creates or updates a task-list item. The main session stops a workflow only for the pinned rehearsal faults in P2, and never after P3 (O67).
- **Other work.** The maintainer's hourly mailbox scheduled task (O62) is disabled and kept for its history. The VM-helper work is paused. Neither resumes before P7 ends without the owner's word (O67).
- **CPU.** No other CPU-heavy job runs during P2 measurements or during P5–P6.
- **The main checkout.** From P3 until `ALL_FROZEN.json` is anchored, nothing is committed, checked out, pulled or edited there, and no instruction, settings or agent-definition file changes.
- **Background commands.** The main session may run its own background commands and monitors: the boot-id log and the driver's wake-up check. Their notices reach only the main session, as measured. No other context may start one.
- **The scratchpad.** The main session writes nothing in the session scratchpad except launchers in the launch folder.
- **Answers.** Historical answers and other answer-bearing material are not on the container (P1). The one exception is the live main-session transcript. It holds earlier evaluation text and cannot be removed; it lies outside every role's files and is audited.

## 6. Phases

| Phase | Entry | Work | Exit |
|---|---|---|---|
| P0 Plan review | Revision 2 | One independent fresh-context review (two reviewers). The owner answers the open questions | **Done:** both reviewers approved with listed fixes, applied in this revision; O66–O69 recorded |
| P1a Mechanics probe | P0 | Invented data only, after the task list was emptied: prompt delivery through a launcher, injected items, label mapping, follow-up to a finished agent, a stop, effort, the restricted agent type, the general-purpose type, cross-context notices | **Done** (section 7) |
| P1 Build | P1a | **First, while their inputs are in place:** the qualification runtime generated with the pinned staging script, the clean dependency bundle, the rehearsal inputs and the development-trial behaviour counts. **Then answer isolation (O68):** every answer-, target-, comparison-, expectation-, raw-row-, study- and prior-output-bearing folder, and every earlier subagent transcript and saved tool output of this session (except the development-trial and probe transcripts the audit needs, after a scan), archived to the maintainer-only Drive folder as one split stream, verified by md5, then deleted locally; reproducible working folders deleted; the maintainer's records moved out of the scratchpad; a hash scan of the whole filesystem finds no registered target. **Then:** release clone; the driver, the audit, the launcher template and the evaluation scripts, with tests on invented data; runner and export self-tests from a throwaway clone; environment fingerprint including the CLI; Drive upload limit measured | All tests pass; clean hash scan; at least 10 GB free; fingerprint recorded |
| P2 Rehearsal | P1 exit; section 5.10 conditions met | `<R>` with its own release, admission, ledger and `JOBS.json`: 4 exposed tuning cases (one large and scoped, one ordinary `.xlsx`, one more `.xls`, one contract job), A then B, driven by the main session. A full-shape run with 6 contexts in flight. Induced faults. Probe runs on exposed cases in separate probe roots, so that at least 16 generators and 16 visual reviewers are measured. At least one auditor, one target-blind reviewer and one download context | Every test passes, or the plan is amended and reviewed again; rates, disk, time, unrecoverable windows and the restart rate measured |
| P2x Admission review | P2 exit | One independent fresh-context review of the built toolkit (driver, audit, launcher and completion templates, injected-item pins, evaluation scripts, evaluation plan, review briefs and rubric, agent definition), its tests and the P2 results, against this plan. It can send the plan back to P0. One or two fix rounds are budgeted. If the recomputed restart risk exceeds 20%, the owner chooses between the two options of section 11 (O69(d)) | The review admits the toolkit; the owner's choice is recorded if needed |
| P3 Admission | P2x exit; owner go | Session check and hash scan again; disk gate (projected need from P2, about 18–20 GB); check the runtime is byte-identical to the staged kit except for the path prefix; freeze the evaluation plan; freeze the admission; write the release; independent hash-only pre-flight; upload a hash anchor | Pre-flight passes; anchor on Drive |
| P4 Nonattempts | P3 exit | 17 nonattempts, reader A | 17 folders frozen and verified |
| P5 Run A | P4 exit; 5.10 rechecked | 36 runs, up to 6 contexts in flight; freeze, verify and audit each; auditors as needed | Every A run frozen, verified and audited, with every auditor verdict frozen; anchor on Drive |
| P6 Run B | P5 exit | The same for B | Every B run frozen, verified and audited |
| P7 Close generation | P6 exit | Census; full audit; `ALL_FROZEN.json` with the scored carriers; one archive of the closing records to Drive; owner census check (O66) | `ALL_FROZEN.json` anchored on Drive |
| P8 Evaluation | P7 exit | Section 8 | Every record frozen |
| P9 Decision | P8 exit | Gate record; public results; state update; bulk archive | Recorded |

**Concurrency.**
- **The loop.** The main session runs one driver pass at a time. Each pass starts every deterministic runner command that is due, as a detached process, and lists the fresh contexts to launch now. The main session launches each one as its own top-level workflow.
- **Waking.** A main-session monitor wakes it when a runner command ends or a deadline passes. Workflow completion notices and agent replies wake it too.
- **Limits:**
  - at most 6 AI contexts in flight. P2 measures the platform's limit, and a lower limit only costs time;
  - at most 2 `prepare`, and at most 2 `finish` or `scope-finish`, at once;
  - while the machine is loaded (load average above 3.5 or less than 3 GB of free memory), the driver holds `prepare`, `scope-finish` and `finish`. A hold consumes nothing.

## 7. The tests

**Done at P1a**, with invented data:
- **T1.** A launcher holding the prompt as an escaped literal ran as a top-level workflow. The transcript's first message, with the wrapper removed and each line de-indented, had exactly the prompt file's bytes (6,680 bytes with CJK text, backticks, template-like text, quotes, a backslash, a tab and trailing spaces). The same held for the restricted type.
- **T1b.** The injected items were listed per agent type. A short probe received no task-list reminder with the list empty. A longer default-type context later received the empty form, so the pin allows absent or empty.
- **T2.** The journal maps each label to one agent id.
- **T4.** The main session's follow-up to a finished agent resumed the same conversation. The reply came back as a hand-back, and the resumed turn was written to a second transcript file. **This must be repeated on the restricted type at P2 (hard exit).**
- **T5a.** A stop leaves the platform's interrupt marker, no result, and an unchanged boot id.
- **T11.** Effort `xhigh` on every message, the same as the development-trial generators.
- **T14.** The restricted type: it failed mid-session and worked after the next restart. Delivery was exact, the tool set was reduced as intended, and `AGENTS.md` was still injected.
- **T15.** The general-purpose type works (the fallback, and the download role's type).
- **Notices.** No cross-context notices: every background notice belonged to its own agent.

**At P2**, the rehearsal must show each of these (the labels match the private procedure):
- **T1 and T1b.** Every rehearsal transcript passes the delivery check. The injected-item list is complete for every role, type and turn. Long restricted-type runs show no task-list reminder other than the empty form.
- **T2.** Labels are unique and map to one agent id and one launch.
- **T3.** The generation record can be built from the transcript and passes `finish`, with the transcript frozen.
- **T4 (hard exit).** The follow-up mechanism works on a restricted-type visual reviewer, and the resumed turn's items are recorded.
- **T5.** Recovery without a second conversation:
  - a stopped context;
  - a technical break mid-turn (simulated by a rehearsal-only driver variant), and the same after a normal final turn (must be non-technical);
  - a launcher that fails before any agent;
  - a killed runner `prepare`, `finish` and `freeze`;
  - a Form 1 and a Form 2 restart.
- **T6.** The ledger, job locks and global slots hold with 6 contexts in flight. A busy refusal consumes nothing. The platform's limit on concurrent workflows is measured.
- **T8 (exit).** The isolation audit classifies every call and every injected item of every rehearsal, probe, P1a and development-trial transcript. The flag and breach rates are reported per role. There are zero breaches by restricted-type contexts.
- **T9.** A `.xls` source and a contract job build through the clean bundle and the runner's pinned environment.
- **T10.** Measured: disk, time and transcript size per run; every unrecoverable window per role (section 11); and the container restart rate under qualification-like load, from the boot-id log. The disk projection fits with margin.
- **T11.** The explicit effort option is accepted and recorded.
- **T12.** A binary file of known sha256 (a bound source, not a target) downloads byte-exact through the Drive connector, and an anchor upload verifies.
- **T13.** The evaluation scripts run correctly on invented fixtures, including the 62-run stage 0, the review rule and every eligibility branch.
- **T14.** Every restricted-role context ran as the restricted type. Its behaviour on the rehearsal cases (checker status, item and hold counts, timings) is compared with the development-trial summaries of the same cases. A material difference goes to the P2x review and the owner.

## 8. Evaluation (P8)

Everything below is fixed in the evaluation plan **at the admission (P3)**, after the P2x review. It is pinned by sha256 and never amended after the ledger's first entry:
- the pool list and its canonical sha256 (`bb949367…`), the alternate pool's sha256, and the alternate rule;
- for each pool case and the alternate, the declared target: its Drive file id, parent folder, title, modification time and size, from listing metadata already held, and for non-reserved cases the registered sha256;
- the eligibility script and its exact rules: header layout, column use, dimension-plus statuses that pass, revision compatibility with its threshold, the internal-design threshold, the evaluator's own target checks, and the contract and quotation-bound cases;
- the scripts for download verification, the empty carrier, the scored-carrier list, the evaluator runs, the manifest and its verification, the assembly repeat and the saved-QA re-run, each with its exact command;
- the review briefs, the critical-error classes (every class of the evaluator brief, including the check of every row that carries an A or B mark), and the full obligation list with pass criteria;
- the audit rules for evaluation contexts, the order of the stages below, and the gate rule (5.8).

**Thresholds** (accepted at P0, reviewed again at P2x). The revision-compatibility and internal-design rules match the target screen, with one exception, which is stricter. A target that has no copy of the creator's source sheet needs a trace share of at least 0.8, where the screen treated a lower share only as a caution. A reserved case in that situation, with a share between 0.5 and 0.8, makes the result NOT DECIDED; it can never make a false PASS.

**The review rule.** Every critical error that the target-blind review flags goes to a fresh target-blind confirming context. If that context rejects it, it goes to a second one. The flag counts unless both reject it. The same rule applies to the A/B errors found at the comparison stage.

Then, in order:
1. **Stage 0, no target opened.** It covers 62 runs: the 30 pool cases and the duplicate-family alternate, both readers.
   - The saved-QA re-run and the assembly repeat (a same-environment repeat).
   - A target-blind review of critical errors and obligations, from the source, the frozen response, the carrier and the inventory only: one fresh context per case, with the review rule above.
   - The isolation and census results.

   This record is frozen. If any element fails on the 60 pool runs, the result is FAIL and the reserved targets stay closed (O69(c)). The alternate's own result decides only whether it may later replace its primary.
2. **Download.** One fresh context per pool case downloads its target read-only (O65). Its tools are fixed, and nothing else is allowed:
   - the tool-schema loader, used only once, to load exactly the Drive metadata and download tools;
   - those two tools, on its one declared file id;
   - a read of its own saved download result;
   - the shell, running only the pinned decode-and-verify script, which writes only into that case's target folder;
   - the hand-back.

   Checks:
   - The bytes must equal Drive's md5 and size, and the id, parent folder, title and modification time must equal the held listing.
   - A non-reserved target must also equal its registered sha256. A non-reserved target whose bytes differ from the registered sha256 is ineligible.
3. **Eligibility, in two steps.**
   - First the checks that read no answer values (identity, header layout, dimension-plus screen), frozen on their own.
   - Only if the duplicate-family primary fails one of those, and the alternate's runs passed stage 0, is the alternate's target downloaded (O69(b)) and put through the same checks, by the second eligibility runner before its remaining checks.
   - Then the remaining checks, frozen as the eligibility record.
   - If a pool case is ineligible and no permitted swap fixes it, the evaluation stops here (5.8).
4. **Comparison.** A pinned script runs evaluator v4 on each of the 60 scored carriers (or the empty carrier), in a fresh evaluator context per case, and freezes the outputs. That context then reads the A/B row pointers only, to find A/B errors, each confirmed from the source by the review rule. It never repairs or rescores anything.
5. **Aggregate.** The manifest is built and verified against the scored carriers and the target pins. Aggregator v2 runs once over the frozen comparisons.
6. **Gate record.** It is written from the frozen records. The local qualification release keeps `RELEASED_FOR_QUALIFICATION`. What a pass enables is the owner's decision (section 12).

Rules for the evaluation contexts:
- **Launch.** They are launched like the generation contexts, from driver-written launchers, with the delivery check and the census. They run as the restricted type, except the download role.
- **Audit.** They are audited, with roles for download, eligibility, review and comparison, before the aggregator runs. Any Drive call other than the declared ones, or any read of another target, goes to the owner and is reported with the gate.
- **Failures.** A context that dies having written nothing is replaced once, with the same input. A partly written output is frozen as it is, and that case is NOT DECIDED and goes to the owner. A second death is also NOT DECIDED. For a confirming review, a second death, or a partly written output, means the flag counts (5.8 item 4). Deterministic steps may run again only if they reproduce the same bytes.
- **Download tool breaches.** Any other tool use by a download context voids that download (at P1a, default-type agents loaded other deferred tools unprompted, such as the monitor tool). One replacement download context is allowed per case, whether the first one died or breached; a second breach (or a second failure of either kind) makes the case NOT DECIDED, and it goes to the owner.
- **The brief.** The evaluation brief allows exactly the case's pinned target, and states that `ALL_FROZEN.json` is anchored.
- **Closed targets.** The other 23 reserved targets stay closed (22 if the alternate is used).

## 9. Evidence kept (private)

- The release, the admission, the runtime inputs, the evaluation plan and the P2x admission record.
- The ledger, and the driver's own hash-chained record: every launch, launcher hash, agent id, boot id, transcript sha256, runner command and printed `run_record_sha256`.
- Every frozen job folder and nonattempt folder, and every unledgered predecessor with its manifest.
- Every transcript in the window, with each one's saved long-output files and every resumed-conversation file: the interrupted contexts, the auditors and the main session's own. Copies of the workflow journals.
- The incident records, the isolation audit, the census, the injected-item records and `ALL_FROZEN.json`.
- The P1a, rehearsal and probe evidence, kept apart.
- Everything is archived to a **maintainer-only Drive folder outside the Dot's shared folder**, verified by size and md5. The Dot's conversations must never be able to read these outputs, transcripts or evaluation files. Hash anchors go up at P3, at the end of P5 and at P7; the bulk archive follows the decision.

## 10. What is reported publicly

Counts and hashes only:
- runs attempted, frozen and failed, by class;
- restarts and incidents, including container restarts;
- transcripts kept (O40);
- isolation deviations and breaches, by role;
- per reader: pooled matched/counted, C/D matched/counted against 0.75, the lowest case's matched/counted, and the number of cases below 0.90;
- the model and effort mix per reader;
- critical errors, obligations met/total, saved and visual QA, assembly repeat (same environment);
- the gate result.

The public record never includes case ids, Drive ids, session or agent ids, private paths or business text.

## 11. Risks

- **Infrastructure failure: container restarts.** Under 5.2–5.4, a restart is unrecoverable for a run if it lands in any of these windows:
  - the commit steps `scope-finish`, `finish`, `visual-record` and `freeze`;
  - a scope reader's or generator's time after it first wrote its file (counting the whole window is conservative, because the file as written may still be carried);
  - a visual reviewer's time after its first write;
  - every completion turn.

  On development numbers these windows add up to about 5–9 run-hours, which overlap to about 4–7 hours of wall time. The container restarted three times on 2026-11-13 before 07:10 UTC. Revision 2 assumed about two a day.

  The chance that a restart fails at least one pool run is roughly 1 − exp(−rate × open-window time): about 28–44% at two restarts a day, and about 70–94% at the rate seen on 2026-11-13. One failed pool run fails the gate (the 0.90 floor), and the pool has no margin. O69(d) accepted 15–20%, so the owner decides before P3 with the figure measured at P2 (next item). A boot-id log has run since 2026-11-13 to measure the rate. No rule of this plan can be relaxed within the qualification. Waiting at the P2 exit for a longer measurement can only refine the figure.
- **The restarts so far came under heavy load.** The three container restarts on 2026-11-13 each happened while heavy VM-helper test or mutant runs (4 parallel jobs) were running. A load or memory cause is a hypothesis. It is now measured: a logger in `<W>` records the boot id, load, free memory and the largest process every 60 seconds. P2 records the restart rate under qualification-like load. If the measured risk over all unrecoverable windows exceeds 20%, two options go to the owner before P3:
  - re-confirm O69(d) at the measured figure; or
  - first build and admit a runner revision that lets an interrupted deterministic stage (`scope-finish` after the response freeze, `finish`, `visual-record`, `freeze`) be re-run when it reproduces the same bytes. That revision needs an independent review and its own admission, and it is never made mid-qualification.
- **A CLI change at a restart** could change the wrapper, the system prompt, the tools or the injected items mid-qualification. It is fingerprinted and checked per transcript entry, and it stops the qualification until the owner decides.
- **Disk.** About 21.7 GB is free after the removal of a reproducible 8.5 GB test install, out of about 40 GB usable. Development job folders took 85–264 MB each. With generator transcripts in two copies, P5–P8 need roughly 18–20 GB. More space comes from the answer-isolation cleanup in P1. The driver holds a new `prepare` when the remaining projected need does not fit.
- **The platform cannot confine file access.** Every context can reach the whole disk. Isolation therefore rests on:
  - the restricted agent type, which has no connector, web, Drive, task-list or agent tools;
    - In this session's earlier default-type workflow subagents, 8 of 132 transcripts held task-list writes (16 creates, 15 updates, 7 stops). The restricted type has no task-list tools. The download role (general-purpose) is the only qualification role that still has them.
  - instruction;
  - removing answers from the disk;
  - the tripwire and the full audit.

  `AGENTS.md`, which asks the reader to read other files, is still injected. One stray read by any of about 168–240 generation contexts fails a pool run and stops the qualification for the owner. The rehearsal and probes measure how often this happens, but they cannot rule out a rare pattern.
- **Behaviour of the restricted type.** Its system prompt differs from the development trials' prompt. The rehearsal compares behaviour on the same exposed cases, but the effect on scores cannot be measured before the evaluation. The development margin was a lowest case of 0.954 against the 0.90 floor.
- **Concurrency.** Six concurrent workflows have not been shown yet. A lower platform limit costs only time.
- **Drive uploads** by file reference need the owner's approval per file. The cleanup archive is uploaded as a few split parts, not one file per folder.
- **Reserved targets** may turn out ineligible when opened (an old template, another revision, or no copy sheet with a trace share between 0.5 and 0.8). That makes the result NOT DECIDED, not PASS.
- **A scope-tool hold** sends a case to the owner. It is frozen as it is and scored as the empty carrier.

## 12. Open questions and notices for the owner

**Answered** (revision 2 numbering):

| Question | Answer |
|---|---|
| 2, 3, 4, 5 | O66 |
| 6, 9 | O67 |
| 7 | O68 |
| 10, 11, 12, 13 | O69(a)–(d) |

Question 1 (effort) and the deletion of the test install are taken by the maintainer's reading, not by an owner answer; both are listed under the notices below.

**Still open:**
- **What a pass enables.** Who runs everyday jobs while the Dot is unavailable, and under which release status. This is needed before P9.

**Conditional, at the P2x exit:**
- **Infrastructure risk.** If the restart risk measured at P2 over all unrecoverable windows exceeds 20%, choose before P3: re-confirm O69(d) at the measured figure, or first have a runner revision built, independently reviewed and admitted that lets an interrupted deterministic stage be re-run when it reproduces the same bytes (section 11). On today's numbers this choice is expected.

**Notices** (no answer needed):
- **`AGENTS.md`.** The "no `AGENTS.md`" part of O66 cannot be met on this platform: it is injected even for the restricted type. Everything else in O66 holds, and any read that `AGENTS.md` prompts outside a role's files is still a breach.
- **Stage 0.** A target-free failure confined to the duplicate-family primary's runs makes the result FAIL. The alternate replaces its primary only for an ineligible target, and only if its own runs passed stage 0.
- **Thresholds.** A reserved case with no copy sheet and a trace share between 0.5 and 0.8 makes the result NOT DECIDED.
- **Orphan prepare.** A `prepare` killed before its ledger entry is handled by the pre-registered orphan rule (5.3), and it does not use up the pair's one restart.
- **Effort.** Question 1 is taken as answered by its own recommended rule (T11 measured `xhigh`, the development-trial setting). Say if this reading is wrong.
- **Test install.** The 8.5 GB reproducible test install was deleted under the maintainer's reading of O68 (reproducible working folders). The P0 review had asked for an explicit OK. Say if this reading is wrong.
