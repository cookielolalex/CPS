# Keeping CPS working when the Dot's VM is wiped (adopted in principle by O43–O52; pending probes and the build)

Status: **ADOPTED IN PRINCIPLE (owner decisions O43–O52 approve OD-1 to OD-10 as recommended, 2026-11-09). Not yet built or qualified.** Written on 2026-11-09 by a design workflow: a constraints study, three independent designs,
two adversarial judges, then a synthesis based on design 3, with the judges' required fixes. It still needs:
- the owner's answers to OD-1 to OD-10, to be recorded as O43 onward;
- the Dot's probe results P1 to P3 (asked in maintainer message M002) and P4;
- building the helpers G1 with an independent review and admission;
- a reset drill on invented data.

Nothing here changes runner v4 or any admitted tool.

Facts learned after it was written (2026-11-09):
- The Dot's Drive downloads and uploads are byte-faithful. The earlier "transfer corruption" was the maintainer's own
  base64 upload slips. See `deploy/README.md`, "Files the maintainer uploads to Drive".
- This partly answers P2's byte-identity question, for small files only. Size limits and speed are still open.

---

RECOMMENDED DESIGN: KEEPING CPS WORKING WHEN THE DOT'S VM IS WIPED
Base: Design 3 (save what cannot be rebuilt as it happens, rebuild the rest; runner v4 unchanged), with the judges' grafts and fixes. Length is about 2,390 words, over the 2,000 target; the detail needed for the judges' must-fix items made it hard to cut further.

A. SUMMARY FOR THE OWNER
The Dot's computer can be wiped at any moment, so everything that matters must reach Google Drive as soon as it exists. After every runner step the Dot saves a package to Drive. Before opening any AI conversation it leaves a note in Drive. It uploads each AI answer the moment it exists, before anyone reads it. After a wipe it rebuilds its tools (about 5 minutes), restores the last package and continues. Qualification runs one job at a time. A step without AI may be repeated after a wipe, but it must match any result the Dot already saw. An AI conversation may be repeated only under your one-restart rule, and only if it provably wrote nothing. An AI answer that was written and then lost counts as a failure. You answer the questions in B and, before scoring, compare your conversation list with the Dot's log.

B. OWNER DECISIONS (recommendation, then reason)
OD-1 Should per-run Drive archives, the final ledger and ALL_FROZEN.json replace QUAL_FROZEN.tar as the frozen evidence, with each local frozen folder deleted after its upload is verified? Yes: 72 runs need about 11 GB, and the VM disk holds 4.9 GB.
OD-2 May a stage without AI that a reset lost run again from the newest verified package? It would be logged, would not use the rule-3 restart, and would run only on a fingerprint that passed the self-test. If its result had already been seen, the re-run must reproduce it, or the run fails. Yes: with fixed inputs and that binding it is a re-execution, not a retry.
OD-3 If a reset interrupts a scope-reader, generator or reviewer conversation whose transcript shows it wrote nothing, may one fresh conversation follow? For the scope reader and the generator this is the one rule-3 restart; for the reviewer it is allowed once per run. Yes: this is exactly rule 3's technical interruption.
OD-4 If an AI output was written, partly written or possibly written, and then lost before reaching Drive, is that a failure (a failed run, or failed visual QA for the reviewer), counted in that reader's O31 denominators and never regenerated? Yes; otherwise resets become a filter. Under the 0.90 per-case floor one such loss fails qualification, so this window is kept to one or two tool calls.
OD-5 Is any VM whose fingerprint has a recorded self-test PASS "the admitted VM"? May a run span such VMs? Does a new fingerprint stop all jobs until its self-test passes? Yes to all three: the host LibreOffice is not pinned, so the fingerprint is the only thing that can be admitted.
OD-6 Should every page PNG stay in the evidence, including the internal-workbook pages nobody reviewed? Yes, unless the Drive test P2 shows it cannot be uploaded; then the question comes back to you.
OD-7 Everyday jobs: should records go in a Dot-owned CPS_JOB_RECORDS folder shared only with you? May a job lost before any AI output be prepared again once, logged? And after a lost AI output, should a new job start only at the user's request? Yes: O41 needs the record kept off the VM.
OD-8 If conversations the Dot opens cannot see its VM's files (test P1), should all CPS jobs wait for a separately reviewed transfer design? Yes: the prompts name VM paths, and the runner reads answers only from those paths.
OD-9 Should runner v5 (G5) stay optional and be admitted only before or after qualification, never during it? Yes: runner v4 with the new folder layout already refuses to run on a wiped VM, and switching runner versions mid-run would do more harm.
OD-10 Will you, or someone you name, compare your account's conversation list with the Dot's START notes before scoring? Yes: nothing else catches a conversation the Dot did not log.

C. SESSION START AFTER A RESET
Fixed paths, all under /home/agent/cps and confirmed by test P3:
- repo/, runtime/, jobs/, transcripts/, inbox/;
- ledger/LEDGER.jsonl, alone in its folder;
- qual/A, qual/B, qual/A_restart1, qual/B_restart1, qual/nonattempts_A, qual/nonattempts_B;
- TMPDIR=/tmp.

1. The Dot downloads into inbox/ with its connector:
   - the maintainer's SESSION_KIT_<release>.zip (release, tables, admission, JOBS.json, deps bundle, SHA256SUMS);
   - the FINGERPRINT_PASS files;
   - a saved Drive listing of the run log (names, ids, md5, createdTime);
   - for a run in flight, its newest package and any later AI archives.
2. It runs one command, where $R is the release's repository.root:
   git clone -q <repo> $R && git -C $R checkout -q <commit> && bash $R/deploy/vm/session_start.sh --inbox <inbox>
   The script:
   - checks $HOME, the uid and the paths, and that the clock is not behind the last ended_utc in the newest package;
   - runs CPS_WITH_LIBREOFFICE=host setup and check_env;
   - computes the fingerprint: hashes and versions of node, the Python packages, soffice, poppler, Chromium, the fonts, glibc and research/export;
   - unpacks the kit, checking every sha;
   - restores the run in flight, then deletes inbox/;
   - writes SESSION_<UTC>_<boot8>.json (boot_id, fingerprint, newest package, what was restored);
   - prints STATE: case, reader, last NEXT, ledger seq, whether the restart is used, and the next action.
3. The Dot uploads SESSION, plus an INCIDENT note if the previous session did not end at a clean point.

Restore refuses unless all of these hold:
- The package is the newest by ledger seq. The same seq with the same sha is a harmless duplicate. The same seq with a different sha is a fork: stop, case C.
- Its md5 and sha match, all its parts exist, and its core was uploaded after them.
- The target paths are empty.
- The ledger begins with the identity line (E1) and extends every earlier package's ledger byte for byte.
- In qualification, the job's record equals the ledger's last record for that job_dir.

Folders come back at their original absolute paths. The qa PNGs are re-rendered from the frozen rendered.pdf and checked against the manifest sha; if any differs, the Dot downloads the PNG parts instead.

Self-test rule: skip it only when the fingerprint equals a FINGERPRINT_PASS. Otherwise run it (13 minutes) and upload a new PASS before any job. A failed setup or self-test is case C.

Timing: 4-6 minutes plus downloads, or 17-19 minutes when the self-test runs.

D. EVERYDAY JOBS
Location: Dots Folder/CPS_JOB_RECORDS/<case>/<UTC run id>/, visible to the owner only. Never a profile folder, because users must not receive the internal QA workbook.

Save points: an INPUTS zip (JOB.json, JOB_TITLE.json, source) before prepare, then the same save points as qualification, without a ledger. CP-F holds the standard (未填).xlsx and SAVED_QA, which meets O41.

Delivery:
1. Run deliver-check only when the copy can be sent in the same session, then upload package CP-D.
2. Make the personal copy from the standard file whose sha equals the one in SAVED_QA.
3. Upload the copy, PERSONALIZATION_LOG.json and DELIVERY_PREPARED_<case>_<UTC>.json to <profile>/deliveries/<case>/<UTC>/.
4. Send.
5. Upload DELIVERY_SENT_<case>_<UTC>.json.
If a reset leaves a prepared note with no sent note, ask the user whether the file arrived; never re-send blindly. Use new dated files instead of editing CPS_DELIVERIES.md until in-place editing is shown to work.

Lost steps follow OD-2 and OD-7. interrupt works only for qualification, so an everyday restart is a new folder that cites the INCIDENT.

E. QUALIFICATION
E1 Ledger
- With the ledger alone in its folder, runner v4 refuses every qualification command on a wiped VM with QUALIFICATION_LEDGER_PATH (cps_job.py L721) instead of silently starting an empty ledger. This works because prepare's jobs_root.mkdir (L1521) no longer creates the ledger's folder before Ledger(create=True) (L1541).
- Nonattempts always get --jobs-root under qual/, because the default is <ledger dir>/nonattempts_<R>.
- Only cps_vm.py creates the ledger folder: through genesis, once (refused if Drive already holds a GENESIS), or through restore.
- The ledger's identity is the sha of its first line, recorded in the first package.
- Each package name carries the ledger seq, ledger sha8 and record sha8. Each manifest adds boot_id, the fingerprint, the command and its printed result. Together these give a hash log after every command.

E2 Order and isolation
- First GENESIS; then all 17 nonattempts in one session, packaged and archived; then the runs, one at a time.
- During an AI conversation the VM holds only the current run, the tools, the runtime files and the repository: no other run, no inbox, no A response.
- AI conversations get no Drive connector and no uploads, because 03_interview holds historical 未填.

E3 Save points per run (each CP is a tar.gz of the job folder without the qa PNGs, plus the ledger)
- CP-P after prepare.
- Scope runs: START-S, then AI-S, then CP-S after scope-finish.
- START-G before the generator opens. It records case, reader, role, prompt sha, run path, nonce, UTC and boot_id.
- LINK-G just after the generator opens, unless P1 shows the Dot can list its own conversations.
- AI-G the moment the generator ends: run/<R>/output, unopened. GENERATION_RECORD.json and the transcript follow; both can be re-created from the conversation.
- After finish: the PNG parts (plain tar, split at the P2 size limit), then the CP-F core, which lists the parts and marks the set complete.
- START-V, LINK-V, then AI-V (qa/visual_review, unopened).
- visual-record, freeze and verify-frozen back to back, then the FROZEN core: the folder minus the PNGs already in CP-F's parts, which it lists by sha. Verify the upload by md5 or by downloading it back, then evict the local folder.
- A CP after any other command that changes the record or the ledger, such as a refusal or interrupt.

E4 Resume, after restoring the newest package
- A non-AI stage was lost: run it again (OD-2). A result already seen binds: the re-run must give the same NEXT/STOP, codes and deliverable sha, otherwise freeze the run as failed (RESET_DIVERGED). For finish, restore CP-P or CP-S plus AI-G.
- A START note exists but no AI archive: find the conversation (from the LINK note, or the conversation list after START's createdTime) and read its transcript.
  - No conversation exists: open one under a new START note.
  - Nothing was written (OD-3): run interrupt --reason TECHNICAL_VM_RESET with its id and times.
    - Form 1 (no frozen scope response): freeze, upload FROZEN, then prepare under <R>_restart1 while the old folder is still on disk, because restart_problem reads its FROZEN.json. Evict the old folder before the new conversation.
    - Form 2 (after scope-finish): restart in place, upload a package, write a new START note.
    - If the restart is already used: freeze; the run has failed.
  - Written, partly written or unclear (OD-4): freeze at the restored NEXT without interrupt; the run has failed. Runner v4 already refuses to restart a run frozen at NEXT: GENERATE without interrupt.
- The AI archive is in Drive: place it byte for byte, check its sha, and continue.
- Reviewer: if nothing was written, one replacement reviewer. Otherwise freeze at NEXT: VISUAL_REVIEW; visual QA has failed.
- Lost after visual-record or during freeze, before the FROZEN upload: restore CP-F, its parts and AI-V. Run visual-record again (bound to any verdict already seen) and freeze. The INCIDENT note names the new FROZEN sha.
- Before B's prepare or A's restart, when A's folder has been evicted: restore only A's FROZEN.json at A's path, then prepare, then delete it before the next conversation. Without that file, v4 lets B start while A's restart is still unused.

E5 Assembling ALL_FROZEN.json, and the audit
- cps_vm.py final checks the final ledger against a saved Drive listing. It requires one FROZEN archive per ledger freeze entry, with the same sha, and one prefix chain of package ledgers starting at GENESIS.
- It then writes ALL_FROZEN.json v2, listing:
  - for each run: the FROZEN and record sha, the archive and part ids and hashes, restart_of, transcript status, fingerprints and incidents;
  - the nonattempts;
  - the ledger shas;
  - the sessions.
  It is uploaded last; its presence means the set is complete.
- The maintainer runs cps_vm.py assemble in a container that recreates the /home/agent paths, then runner v4 verify-frozen on every folder, then audit. At any other path verify-frozen fails with QUALIFICATION_JOB_NOT_IN_LEDGER. The 38 reserved answers stay closed until this passes.
- Each reset gets one INCIDENT note: old and new boot_id, the newest package, the step in flight, its classification, the conversation link and what its transcript shows, and any result already seen.
- audit checks that:
  - there is one ledger chain and no fork;
  - every START note has an AI archive or an INCIDENT;
  - every interrupt and every replacement reviewer has both;
  - every reset shows a new boot_id;
  - each START createdTime precedes its conversation;
  - each AI archive's sha equals its frozen copy.

F. INTEGRITY
- Rule 3 is judged from the conversation's transcript, not from the VM. The runner's RESPONSE_WRITTEN check (os.path.lexists, L2895) cannot see a file that a wipe removed. Doubt counts as written.
- An AI step is repeated only through interrupt, which the ledger counts once, or through the one reviewer replacement. Each needs an INCIDENT and the earlier transcript. A conversation without a START note shows up in the owner's comparison (OD-10): that case fails, and qualification is flagged.
- Stored state cannot hide a retry:
  - the ledger cannot restart empty;
  - restore takes only the newest package;
  - add-only Drive keeps both sides of a rollback;
  - a reset without a new boot_id is flagged;
  - non-AI re-runs are bound to any result already seen.
- Every AI output reaches Drive within one or two tool calls, before anything reads it. An output lost anyway fails the run, so losing one never pays.
- Limit: a deliberate breach, such as creating the ledger folder by hand or an unlogged conversation, is detected but not prevented. v5 R1 would close the first.

G. CHANGES TO BUILD
G1 Helpers: deploy/vm/cps_vm.py and deploy/vm/session_start.sh. No runner admission needed.
- cps_vm.py is about 500 lines, uses only the standard library, runs with python3 -I -B, and sits outside the trees the runner scans for pycache.
- The release pins both files, so runner v4 checks their sha at every command except freeze and verify-frozen.
- Tests in deploy/vm/test_cps_vm.py, on invented jobs made with runner v4:
  - round trips keep zero-byte files, empty directories and file modes, and verify-frozen passes at the original path;
  - every restore refusal;
  - the re-render fallback;
  - QUALIFICATION_LEDGER_PATH after a simulated wipe;
  - the B and restart refusals when only A's FROZEN.json is restored;
  - audit catches planted anomalies.
- Review: an independent fresh review of the exact diff, then ADMISSION_VM_HELPER_V1.json.
G2 Release and kit (maintainer): the path layout, the helper pins, SESSION_KIT and the per-case input zips, checked against the runner's path refusals.
G3 Documents, reviewed by the maintainer against the owner's decisions:
- deploy/vm/RESET_PROTOCOL.md (new);
- Dot documents 00, 05, 06 (steps 3-4 replaced), 07, 09, RUN_PHASE1 (upload after each step) and FOLDER_MANIFEST. 07 covers setup attempt subfolders with a SUBMITTED file uploaded last, the audit for case B, and incidents for case C;
- docs/handoff/DEPLOYMENT_MODEL.md and docs/handoff/CURRENT_STATUS.md;
- the owner's answers recorded as O43 onward.
G4 Unchanged: cps_job.py, RUN_JOB_COMMANDS.md, ADMISSION_RUNNER_V4.json, the harness and the export tools.
G5 Optional runner v5, which NEEDS A NEW RUNNER ADMISSION (tests, independent review, admission):
- R1: an explicit --create-ledger with a random ledger_id;
- R2: boot_id and the fingerprint in every entry;
- R3: restart_eligible in the freeze entry.
G6 Before qualification, all on invented data:
- P1: a new conversation can read and write a nonce file on the operator VM and has no Drive tool. Also check whether the Dot can list its own conversations.
- P2: Drive round trips up to 300 MB. Measure byte identity, conversion, size limit, speed, md5Checksum, createdTime and subfolder creation.
- P3: two fresh VMs give the same $HOME, uid and paths, and a new boot_id.
- P4: pages and tiles re-render byte-identical.
- The export self-test at the new commit.
- A reset drill with wipes after CP-P, during a generator, after a write, during finish, during an upload and after visual-record. It ends with assemble, verify-frozen and audit passing.

H. STORAGE AND TIME (assumes 20 s per Drive call; MB/s not yet measured)
- Local tmpfs peak: tools 2.1 GB + one run 0.3 GB + staging 0.3 GB + inbox 0.3 GB = about 3.0 GB of 4.9 GB.
- Drive per run: about 160 MB (PNG parts 130 MB, cores 25 MB, AI outputs under 1 MB).
- Drive for 72 runs: about 11.5 GB, plus ledgers under 0.1 GB.
- Uploads per run: 8 normal, 11 scope, plus 2 or 3 LINK notes if needed.
- Uploads for qualification: about 670-840, which is 3.7-4.7 hours of calls plus transfer time.
- The runs themselves: 12-24 hours in sequence, more for large jobs.
- Resume: 4-6 minutes plus downloads (under 25 MB, or up to 250 MB of parts if re-rendering fails). Add 13 minutes on a new fingerprint.
- At risk if a wipe hits: for an AI output, one or two tool calls; for a non-AI stage, its own run time, and it can be re-run.
- Everyday job: about 160 MB and 10 uploads.

I. OPEN RISKS
- If P1 fails, everything is blocked.
- Drive's size limits, speed, quota (about 12 GB needed) and byte fidelity are unknown until P2.
- Under the 0.90 per-case floor, one written output lost to a reset fails qualification.
- A changed $HOME or uid strands any run in flight, because its paths are embedded in the prompts and the ledger. Only a runner change could fix that.
- A LibreOffice change pauses work for a self-test.
- A VM clock behind the recorded times would trip GENERATION_RECORD_TIMES, so session start checks the clock first.
- Classifying a lost conversation depends on the Dot reading its transcript correctly; treating doubt as written limits the damage.

Files read: /home/user/CPS/deploy/run/cps_job.py (the ledger lines checked are L715-732, L1498-1546, L834-906 and L3030-3062), /home/user/CPS/deploy/run/RELEASE.example.json, /home/user/CPS/deploy/setup_vm_user.sh. No repository files were changed.