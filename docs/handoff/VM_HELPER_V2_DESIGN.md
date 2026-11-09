<!-- Status: DESIGN, not built, not admitted. Produced 2026-11-09 by an independent design panel (three designs, two adversarial judges, one synthesis) after admission review 1 rejected cps-vm-helper.v1 (deploy/vm/ADMISSION_VM_HELPER_V1.json). Owner decisions Q1-Q8 in section H are pending; probe answers (P1-P3, P5, and the section F questions) are pending. -->

CPS VM-RESET HELPER v2 (cps-vm-helper.v2): RECOMMENDED DESIGN
Base: Design 3, with grafts from Design 2 (close-before-place, three verbs, transition-table oracle, import lint, reset enumeration) and Design 1 (--at, md5s never printed, one md5 per name, REUSE_MANIFEST, authenticated absence check). Runner v4 (7505e98a), evaluator v4 (fc723405) and aggregator v2 (e5aa4fc7) are unchanged.

A. SUMMARY FOR THE OWNER
Drive keeps one numbered, add-only journal, with one file per job step. The helper shows the Dot nothing that depends on a result (the next step, a conversation to open, a hand-back) until that file is confirmed on Drive. After a wipe, the helper continues from the newest journal file. It first ends any open AI conversation and has the Dot classify it from its transcript. A result that reached Drive binds any re-run. A result that never reached Drive was never shown to anyone. The Dot uses three commands, and every value it types is checked. v1 had about 19 commands, each with its own copy of the state rules. In v2, one small pure core decides everything, and a maintainer audit re-checks the journal before scoring.

B. ARCHITECTURE AND STATE MODEL

B1 State. One contiguous, hash-chained, add-only journal per series:
- CPS/qualification/CPSJ_Q1_<seq6>.tgz;
- Dots Folder/CPS_JOB_RECORDS/CPSJ_E1_<seq6>.tgz (everyday);
- CPS/reports/CPSJ_D<n>_<seq6>.tgz (drills).

Each entry holds:
- ENTRY.json: series, seq, prev_sha256, kind, body, utc, boot_id, fingerprint, and the helper, runner, kit and release sha;
- confirms: id, md5 and size of each file of the previous commit;
- parts: name, sha, md5 and bytes;
- state: the full fold, plus state_sha256;
- payload: the job-folder snapshot without page PNGs (listed by sha), the ledger bytes, an AI output folder, transcripts and attested values.

Parts are the PNG tar parts, the delivered copy, LEDGER_FINAL and ALL_FROZEN. They are named CPSJ_<series>_<seq6>_<KIND><kk>.<ext> and uploaded after their entry. Entry names reveal no case or outcome.

The local STATE.json and PENDING.json are a cache, re-hashed on every command; any mismatch takes the restore path. Writes use a full-write loop, fsync of the file and its folder, and a read-back hash. OSError or ENOSPC halts before anything is printed.

B2 Modules.
- core/ (pure):
  - names;
  - entry (schema, validators);
  - fold: apply over the transition table of about 40 rows in spec section T; anything else is CHAIN_INVALID;
  - plan: next_action, which is total, falling back to STOP UNCLASSIFIED;
  - outcome.
- io/ only carries out Steps:
  - savepoint;
  - drive;
  - runner: runner v4 as a detached argv subprocess, with stdout kept in a file and never printed;
  - place;
  - host and kit, from v1.
  A lint test fails if io/ imports anything from core/ except Step.
- cli.py (go, found, answer) and session_start.sh.
- maint/: audit, assemble, score_check.
- probe_p5.py is separate.

B3 The save-point primitive, commit(). Every Drive write goes through it.
1. Refuse if PENDING exists. Compute state' = apply(state, entry); an illegal transition is never written.
2. Write the entry and parts durably, all non-empty, then PENDING.
3. Print UPLOAD of the entry, FIND by exact name, then ATTEST found.
4. Accept only if every copy carries the helper's md5 and size. Same-md5 duplicates are fine. A second md5 is STOP FORK. On "none": WAIT 30 s, FIND again, then re-upload, at most 3 uploads, then STOP UPLOAD_FAILED. md5s are never printed, so a match proves a real lookup.
5. Only then print and confirm the parts. Their number reveals the outcome.
6. Record the ids, clear PENDING, run the post-commit action (evict after FROZEN; remove a placed FROZEN.json after prepare), then print next_action(state').

No reveal: no runner result, OPEN, CONTINUE, NOTIFY_OWNER or HANDBACK is printed before its commit is confirmed. A START rides in the commit of the stage whose NEXT names that AI role, so START is confirmed before OPEN.

B4 Stages.
- go runs the next stage in a detached worker under HelperLock.
- Chained, because none needs AI or a human: visual-record, freeze, verify-frozen; freeze again on STOP_FREEZE_INCOMPLETE; freeze after STOP_* or OWNER_DECISION. One STAGE commit per chain.
- A REFUSED that changed nothing commits nothing.
- REVIEW_INCOMPLETE changes the folder (the runner writes the attempt file and the refused record and ledger entries), so it is committed together with CONTINUE-V.
- STOP_* and OWNER_DECISION commits are followed by NOTIFY_OWNER.
- The helper writes GENERATION_RECORD.json from validated answers, and passes --transcript only when the status is exported.

B5 The open-conversation rule. Per (run, role S/G/V, attempt):
STARTED -> [OPENED, if configured] -> ARCHIVED (AI entry) or RESOLVED (RESTORE).
REVIEW_INCOMPLETE sets CONTINUED.

STARTED, OPENED and CONTINUED are open. While a role is open:
- no OPEN or CONTINUE is printed for it;
- only its AI entry or a resolving RESTORE is legal;
- the AI entry needs ended=yes and the START's boot_id, and its output folder is walked strictly and tarred unopened.

Other rules:
- Consumers (scope-finish, finish, visual-record) need ARCHIVED, with a tree sha equal to the current output folder.
- A second START per attempt is legal only after NO_CONVERSATION.
- The fold counts reviewer replacements; rule-3 restarts stay with the runner.

After a reset, before anything else:
1. END_CONVERSATION (without OPENED, the Dot finds it in its list after the START's utc).
2. Place, then re-walk every AI output folder; any file forces WRITTEN.
3. EXPORT_TRANSCRIPT.
4. ATTEST the outcome.

| Outcome | Allowed | Result |
|---|---|---|
| NOTHING_WRITTEN | S or G, with the transcript sha, or Q2 | runner interrupt --reason TECHNICAL_VM_RESET; the runner picks the form or refuses INTERRUPT_RESTART_USED, and then the run is frozen with RESTART_EXHAUSTED_BY_RESET |
| NOTHING_WRITTEN | V, not continued | one replacement reviewer per run; if used, freeze with VISUAL_QA_FAILED_BY_RESET |
| WRITTEN (also UNSURE, no transcript, or a file at step 2) | always | S or G: freeze at the restored NEXT without interrupt, AI_OUTPUT_LOST. V: VISUAL_QA_FAILED_BY_RESET |
| continued V | not asked (r1 is written, Q4) | freeze with VISUAL_QA_FAILED_BY_RESET, no replacement |
| NO_CONVERSATION | from STARTED only, once per attempt, with the Dot's conversation list showing none; otherwise WRITTEN | a superseding START; the O52 sheet shows the START1-START2 window |

The RESTORE carries each transcript (F7, Q3). It is committed before any interrupt, replacement or freeze is printed. Runner v4's RESPONSE_WRITTEN check cannot see what a wipe removed, so it is no safeguard here.

B6 Restore, failing closed. session_start.sh:
1. takes the kit in and re-hashes it;
2. checks $HOME, uid, layout and clock;
3. computes the fingerprint and looks up setup/FINGERPRINT_PASS_<fp64>.json; with no PASS, only selftest runs;
4. finds the head from the hint, a newest-first listing (if P2 allows) or galloping. N must be found. N+1 must be absent twice, with a wait of at least the measured lag (60 s or more) between. N+2 must be absent. N-1's md5 must equal N's confirms;
5. downloads N and checks its tgz, state_sha256 and link;
6. runs classify(head.state).

| Situation | Action |
|---|---|
| link, state or schema mismatch; unknown helper; release neither genesis's nor kit-accepted; HEAD_CORRUPT; hint ahead of Drive | STOP, HANDBACK C, sticky HALT |
| HALTED | STOP, unless the kit carries a CLEAR naming the series, seq and code (Q6) |
| FINAL with a part missing | re-upload it from the entry's members; HANDBACK B |
| AI role open | B5 |
| visible head with a PNG part missing (so OPEN was never printed) | rebase: re-run the stage from the base entry, bound to the head's NEXT/STOP, codes and deliverable and SAVED_QA sha, otherwise RESET_DIVERGED; the unopened START is superseded and logged |
| run in flight, nothing open | place the head and its parts; the uncommitted stage re-runs unbound (it was never shown, Q1), logged |
| no run in flight | the next JOBS.json run; for B's prepare or A's restart, A's FROZEN.json is placed and removed after the prepare commit, before OPEN |
| everyday PREPARED without SENT | ASK_USER whether it arrived; never re-send blindly |

Placement goes into empty targets at the original absolute paths, with the ledger alone in its helper-created folder, and every sha is checked. Then the RESTORE entry is committed: boots, fingerprint, PASS, head, resolutions, transcripts, and any re-runs or rebase. Its lookup of N+1 must show exactly one md5. That is an authenticated second absence check: a lagging N+1 becomes FORK before anything runs. Classification reads only the head (F3).

B7 Failure flags. outcomes(state) is one pure function, called by final, audit and score_check. For each (case, reader), the last run of the restart chain counts:
- SCORE: a frozen carrier/convert/carrier.json exists, with no AI_OUTPUT_LOST or RESET_DIVERGED;
- EMPTY(reason): AI_OUTPUT_LOST, RESET_DIVERGED, RESTART_EXHAUSTED_BY_RESET, frozen at GENERATE or SCOPE_READER without interrupt, a technical stop after the restart was used, OWNER_DECISION, or no carrier;
- NONATTEMPT.

It also gives the visual class and lists superseded STARTs (with their windows), re-runs, rebases and pending owner checks.

score_check builds each EMPTY carrier itself, as {"items": [], "cps_failed_run": {series, seq, case_id, reader, job_dir, reason, frozen_sha256}}. Each one is distinct per reader (READERS_SHARE_CARRIER), and the scorer never supplies a sha. I checked that compare_target050 reads only items, and that empty items score 0 out of the full target count.

C. OPERATOR SURFACE

Rule: run "bash /home/agent/cps/vm.sh go" (after a wipe, session_start.sh first), then do the block.
```
CPSV series=Q1 head=000124 at=000124-03-a1b2c3 mode=qualification state=<CODE>
UPLOAD <abs> TO <folder> AS <name>     (0..n, in order)
FIND <folder> NAME <exact name>         (0..n)
DOWNLOAD <folder> ID <id> TO <abs>      (0..n)
DO: <exactly one terminal action>
```

Terminal actions:
- RUN vm.sh go
- ATTEST vm.sh found --at A --name N (--file ID:MD5:SIZE ... | --none) [--name ...]
- ATTEST vm.sh answer --at A key=PATTERN ...
- OPEN_CONVERSATION role= prompt= folder=, or CONTINUE_CONVERSATION role=V conversation= message=; either way, when it has ended, RUN go
- END_CONVERSATION, or EXPORT_TRANSCRIPT to=; then RUN go
- NOTIFY_OWNER file=, or ASK_USER file=, or DELIVER file=; each then ATTEST answer
- WAIT seconds=; then RUN go
- STOP CODE HANDBACK C, HANDBACK B, or IDLE

There are no THEN chains, OPTION lists or {TOKEN}s. Paths are shlex-quoted and must round-trip; the helper runs the runner itself, so no line interpolates a case id. Exits: 0 follow, 3 STOP, 4 REFUSED (state unchanged; the block is printed again).

Validation (re.fullmatch on str, ASCII):
- --at must equal the last printed at (seq, step, and 6 hex of sha256 of state, pending and step); otherwise REFUSED STALE_AT, so a stale answer cannot apply.
- Refused everywhere: { } < > ' " ` $ \, whitespace, a newline, non-ASCII, and any key name, placeholder or documentation example.
- Per field:
  - Drive id: [A-Za-z0-9_-]{20,80} (narrowed after P2);
  - md5: [0-9a-f]{32}, which must equal the local value;
  - size: [1-9]\d{0,11}, which must equal the local bytes;
  - conversation: the kit's P1 regex (the kit is refused if the regex matches a doc sample);
  - utc: \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ, within [end of the NEXT stage, now];
  - model: [A-Za-z0-9._:-]{2,64};
  - effort: [a-z0-9_-]{1,32};
  - features: yes|no;
  - tools: a comma list or none;
  - outcome: NOTHING_WRITTEN|WRITTEN|UNSURE|NO_CONVERSATION;
  - transcript: exported|not_available;
  - case: CASE_ID_RE, checked before any write.
- The final message goes in ~/cps/attest/final_message.txt: UTF-8, at most 8 KB, non-empty, with no <...> or {...}.
- Exactly the keys the block asked for must be given.

D. DRIVE USAGE

The Dot's tool must upload to a folder, search a folder by exact name (returning every copy with id, md5 and size), and download by id. No listing is ever saved (OP-06); only the audit reads createdTime.

Completeness: entry N+1 is built only after N is confirmed, so the head is the unique N present with N+1 absent. Everything else is reached through names, hashes and ids in the state. A false "none" can only cause a FORK at RESTORE or an audit anomaly, never a silent re-run.

Prefix search (one FIND per commit) and a newest-first listing (a one-call head) are used only once P2 records them. If md5 is hidden, found takes ID:SIZE and the helper downloads the file back and compares its sha (+1 call). Without exact-name search the design is blocked.

Other files:
- setup/FINGERPRINT_PASS_<fp64>.json and SELFTEST_<fp64>.json, both confirmed the same way;
- the kit, setup/SESSION_KIT_<release12>.zip;
- the everyday delivered copy and its log, which go to the profile folder under the writer's name.
O43: the FROZEN entries plus their PNG parts are the per-run archives. FINAL adds LEDGER_FINAL and ALL_FROZEN_Q1.json (with the O52 sheet), md5-confirmed before HANDBACK B.

Budget (one upload plus one FIND per file; p PNG parts, 1-3; md5 visible):

| Item | Calls |
|---|---|
| Normal run: prepare+START-G, AI-G, finish+START-V (+p), AI-V, FROZEN | 12-16 |
| OPENED commits (no conversation list) | +4 |
| Scope run (AI-S, scope-finish+START-G) | +4 (+2) |
| REVIEW_INCOMPLETE | +4 |
| Everyday: INPUTS+prepare, AI-G, finish, AI-V, visual-record, deliver-check+copy (2 profile parts), SENT | 20-24 |
| Resume with a hint: kit 2, PASS 1, lookups 5, head 1, parts 0-3, A's FROZEN 0-1, RESTORE 2 | 11-15 |
| Without a hint or newest-first listing | about +20 |
| md5 hidden | +1 per file |

Qualification is about 72 runs plus genesis, 17 nonattempts, final and resets: about 1,100-1,500 calls (6-8 hours at 20 s each). Storage is about 260 MB per run, about 19 GB in all. The tmpfs peak is under 3.1 GB.

E. FINDING COVERAGE

Scenario tests use FakeDrive (exact search only) and FakeDot (follows the blocks). A v1 driver built on the test_cps_vm.py harness shows each blocking test failing on 95df270.

| Finding | Prevented by | Regression test |
|---|---|---|
| F1 (critical) | REVIEW_INCOMPLETE commit sets CONTINUED; continued V resolves only as VISUAL_QA_FAILED_BY_RESET | wipe after r2 is written, before AI-V r2 is confirmed: no OPEN or CONTINUE for V again; flag in ALL_FROZEN |
| F2, TST-01 | a second START only after NO_CONVERSATION from STARTED, once | property test over random cuts; a missing START causes a re-upload, never a new START |
| OP-01 | START in the stage commit | FakeDrive holds the entry before the first OPEN |
| SAFE-04 | durable writes; cache re-hash | ENOSPC or a short write at every write: HALT, no UPLOAD |
| F3 | classify reads only head.state | wipe at every worker point, including one needing A's FROZEN |
| F4, FLAGS-3 | total outcomes() | table over every frozen-run shape |
| F5 | audit re-folds from its own listing and diffs with ALL_FROZEN | a planted RESTORE unknown to final: audit fails |
| SAFE-01 | strict walk; evict only confirmed (path, sha) pairs | FIFO, symlink, unreadable folder, mode 4755: HALT, nothing deleted |
| FLAGS-1, FLAGS-2 | score_check builds the carriers | wrong, shared or real carrier: INCONSISTENT |
| OP-04 | fullmatch and global refusals | '{CONVERSATION_ID}', '<id>' refused, state unchanged |
| OP-02 | one bounded loop | lost RESTORE upload: 3 tries, then STOP |
| OP-03 | FINAL is a commit | truncated ALL_FROZEN is re-uploaded |
| SAFE-02 | case checked first; no interpolation | space, quote, newline, Unicode |
| SAFE-03, OP-05 | probe_p5 compares sid and ppid | same-call check: FAIL |
| OP-06 | exact search only | FakeDrive has no listing |
| KIT-1, TEST-1 | genesis release sha, checked at RESTORE, final, audit | kit swap: STOP |
| minors (F6-F8, OP-07-09, SAFE-05-07, GATE-1, KIT-2, MK-1, MK-2, TST-02-10) | by construction or a small fix | one test each |

Also tested: stale --at; FORK at RESTORE; a diverging rebase; a re-walk forcing WRITTEN; NO_CONVERSATION without a conversation list; a consumer tree-sha mismatch.

F. PROBES

| Probe | Pass | Fail |
|---|---|---|
| P1 VM files, no Drive | as designed | O50: all jobs wait |
| P1 transcript export | NOTHING_WRITTEN by transcript | Q2, otherwise WRITTEN |
| P1 conversation list with times | OPENED off; NO_CONVERSATION allowed | OPENED mandatory; NO_CONVERSATION is WRITTEN |
| P1 end a conversation after a reset | as designed | every open role is WRITTEN |
| P2 exact search returns all copies | required | blocked |
| P2 md5, prefix search, newest-first | confirm from FIND; 1 FIND per commit; 1-call head | download-back; per-name FIND; hint or gallop |
| P2 lag, size, speed | wait = twice the measured lag; parts below the limit | more FORK STOPs; owner (O48) |
| P3 | as designed | $HOME or uid change with a run in flight: STOP |
| P4 | not needed | — |
| P5 | detached stages and setup | a stage over the tool-call limit: release-gate STOP |

Probe message (paste as is; invented data; use only CPS/reports/PROBE_V2/):
1. Run: printf 'cps-probe-alpha\n' > /tmp/pa.txt; md5sum /tmp/pa.txt; cat /proc/sys/kernel/random/boot_id; id -u; echo $HOME; date -u +%FT%TZ. Paste the output.
2. Upload /tmp/pa.txt twice as T.txt. Search for exactly "T.txt" and paste the raw result with every field. Are both copies returned? Was one renamed? Does the upload response give id and md5?
3. Upload P1_a, P1_b and P10_c. Does a "starts with P1_" search return exactly two? Can you list newest-first, limited to 5? What is the page size?
4. Run: for i in $(seq 1 20); do printf 'n%02d\n' $i > /tmp/l$i.txt; done. Upload each file and search for it at once. Was any file missing, and for how many seconds?
5. Run: head -c 26214400 /dev/urandom > /tmp/b25.bin; sha256sum /tmp/b25.bin. Upload it, download it by id, and sha256sum the copy. Repeat with 130 MB and 300 MB, timing each. Are .tgz and .tar files unconverted? Can a failed or timed-out upload still appear? Can you save a search result to a VM file without retyping it?
6. What does a conversation id or link look like? Can you list conversations with creation times, export a transcript with its file writes to a VM file, and see that a conversation ended, or stop it? In a new conversation, run printf 'p1\n' > /tmp/p1_conv.txt. Does that conversation have a Drive tool?
7. Does your chat, including the last "head=" value, survive a VM reset? Does a conversation still running write into the new VM?
8. Call 1: ps -o sid= -p $$; setsid nohup sh -c 'sleep 420; date -u +%FT%TZ > /tmp/p5_done' >/dev/null 2>&1 & echo started. Then a separate call at least 8 minutes later: ps -o sid= -p $$; cat /tmp/p5_done. What is your longest allowed tool call?
9. Is the VM clock synced?

G. BUILD PLAN

| Part | Lines |
|---|---|
| core/: names 120, entry 160, fold 220, plan 220, outcome 80 | 800 (hand-written, reviewed line by line) |
| io/ new: savepoint 200, drive 150, runner 250, place 250, cli 150; session_start.sh 80 | 1,080 |
| reused v1: 880 verbatim, 330 modified | 1,210 |
| maint/: audit 350, assemble 120, score_check 180; probe_p5 80 | 730 |
| helper total | about 3,100 (measured budget, not a cap) |

Reused verbatim, with REUSE_MANIFEST.json giving each one's AST-segment sha at 95df270, checked by a test: sha_bytes, sha_file, md5_file, h8, canon, sjson, read_json_file, write_atomic, write_new, make_writable_tree, remove_tree, q, parse_utc, now_dt, iso, utc, utc14, boot_id_path, current_boot_id, HelperLock, JobLock, _tarinfo, write_tgz, write_tar_stream, unsafe_name, under_stage, png_manifest_problem, pkg_manifest_problem, check_pkg_manifest, Archive, zlib_error, Staging, png_set, png_tar_members, PartWriter, tree_bytes, join_slices, require_space, disk_full_halt, FP, first_line, fingerprint, kit_members, unpack_kit, validate_pass, spawn, worker_alive, run_runner, scrub, clock_check, check_layout_basic, Layout, check_ledger_identity, selftest_work.

Modified, each reviewed as a diff: tree_list (strict), rebuild_kit and session_kit (re-hash, exact names), place_frozen, cmd_worker and wait_block (bounded chain table), cleanup_leftovers, check_layout_release.

Deleted: INDEX and listings, situation and every *_plan, tokens and binding, find_fork, resolve_forks, local_floor, Fetcher, rerender, restore_png, the recheck, start-note, link-note, ai-archive, incident, rebuild-parts and probe-p5 commands, run_flags and apply_frozen_flags.py.

Tests (about 3,000 lines; under 15 minutes with 4 jobs):
- core table and invariant property tests: 900 lines;
- reset enumeration with runner v4 on invented jobs, wiping at every commit boundary and worker point, crossed with every visibility outcome (lag, duplicate, foreign md5, missing part) and every Dot answer: 1,100 lines;
- reused archive tests: 400 lines;
- v1-driver regressions: 400 lines;
- lints: every REFUSED, STOP and HALT code reached, core line coverage, io imports, REUSE_MANIFEST;
- a preflight that refuses to run with less than 1 GB free and records the test count.

Mutants:
- the v1 set M08, M10, M14, M16, M19, M24, M26, M27, M30-M32, M34, M37 and M39, each mapped or marked "path deleted" with the reason;
- new: G1 OPEN before confirmation, G2 wrong md5 accepted, G3 no second absence check, G4 NO_CONVERSATION from OPENED, G5 NOTHING_WRITTEN for a continued V, G6 no re-walk, G7 lenient evict walk, G8 no STALE_AT, G9 unbound rebase, G10 SCORE for a run frozen at GENERATE, G11 shared carrier, G12 no release compare, G13 match instead of fullmatch, G14 second START, G15 result printed before commit.
All must be killed.

Admission, in order: owner answers to H; probes recorded; spec with the transition table; build; one green full run on at least 1 GB free; an independent five-lens review (with adversarial verifiers) under the new version id. The review covers core/ in full, io/ only for "carries out the Step", modified functions as diffs, and reused ones by REUSE_MANIFEST. score_check, probe_p5 and make_kit are admitted separately. Before qualification: a series-D reset drill that ends with assemble, verify-frozen at the /home/agent paths, a clean audit and score_check. The audit is a mandatory pre-gate: full API listing, re-fold, duplicate seqs, gaps, unreachable files, the ledger prefix chain with declared rebases, and the outcomes diff. The 38 reserved answers stay closed.

H. OWNER DECISIONS (all recommended yes)

| | Question | Why yes |
|---|---|---|
| Q1 (O44) | Results are never shown before they are on Drive. A committed result binds re-runs mechanically. An uncommitted one was never shown, so it re-runs unbound and logged. Does this satisfy "a result already seen binds"? | otherwise tokens and the Dot's memory return |
| Q2 | Without transcript export, may the Dot's attested reading allow the restart, flagged OWNER_CHECK, with your check of that conversation before scoring? A write found fails that reader's case. | otherwise every interrupted conversation fails a case |
| Q3 (F7) | Commit every resolved conversation's transcript, written-and-lost included, in the RESTORE entry? | failure evidence |
| Q4 | A REVIEW_INCOMPLETE continuation interrupted by a reset fails visual QA, with no replacement? | r1 is written output |
| Q5 (O45) | A superseding START, once per attempt, only from a never-opened START, only with the Dot's conversation list showing none, and listed with its window on the O52 sheet? | fail-closed evidence |
| Q6 (O53) | May the maintainer clear a HALT with a config-only kit naming the series, seq and code (no code, rule or evaluator change)? | defined recovery |
| Q7 (O49) | Everyday jobs resume from the last committed entry without limit, and "prepared again once" applies only to re-preparing from inputs? | a resume is not a re-preparation |
| Q8 | At most 2 REVIEW_INCOMPLETE continuations per reviewer; a third refusal freezes as REVIEW_INCOMPLETE_LIMIT, failing visual QA? | the runner has no bound |

I. OPEN RISKS
- P1 failure means everything waits (O50); no exact-name search means the design is blocked.
- Search lag turns some real uploads into FORK STOPs; they fail closed but cost maintainer cycles, as does HEAD_CORRUPT.
- "Not seen" excludes side channels (entry size, timing, the Dot opening local files); Q1 must accept this, and the audit logs every re-run.
- Conversation classification rests on the Dot's transcript reading and on O52. Doubt counts as written, so under the 0.90 floor one lost written output fails a case.
- A changed $HOME or uid strands a run in flight.
- 6-8 hours of Drive calls and about 19 GB of storage; P2 speed is unknown.
- The budget may grow; the 800-line core must stay reviewable.
