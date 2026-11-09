# CPS on a VM that can be wiped: the operator procedure (G1)

For the Dot. The VM can be reset at any moment; only Google Drive persists. The helper `cps_vm.py` saves everything
that matters as files you upload, and puts it back after a reset. It never touches Drive or the network: it prints
what you do. Specification: G1 implementation specification revision 6 (its sections 16-19 override earlier text); design `docs/handoff/RESET_PROOF_DESIGN_DRAFT.md`;
owner decisions O43-O52.

`$V` below is `~/cps/vm.sh` (the helper prints its absolute path in every RUN line).

## 0. The rules for every printed line

Each command prints, in order: `RESULT: {...}` (keep it in your notes), sometimes `BIND=<token>` (keep this line), then:

1. every `UPLOAD <local path> -> <Drive folder>`: upload that file to that folder, in the order printed, and wait for
   each to succeed. A failed upload may be repeated; **at most 3 attempts per file**, then stop and hand back case C
   with the file name and the error;
2. every `SAVE_DRIVE_LISTING folder=<Drive folder> to=<local path> [name=<file name>]`: list that folder (the text
   between `folder=` and ` to=` is the folder; it may contain spaces). With `name=`, list only that file name. Save
   **every page the connector returns, each page's response unchanged**, in this wrapper, at the printed path:
   `{"schema": "cps.vm-drive-listing.v1", "folder": "<folder>", "name_filter": <the name or null>, "pages": [<page 1>, <page 2>, ...]}`.
   Keep asking for the next page until the connector gives no next-page token. Never shorten, sort or retype a listing.
   Ask the connector for these fields: `kind, nextPageToken, incompleteSearch, files(id, name, createdTime, md5Checksum,
   size, mimeType)`. Every file entry must carry `id`, `name` and `createdTime`, and every page must carry at least one of
   `kind`, `nextPageToken`, `incompleteSearch` (the helper refuses `LISTING_INVALID` / `LISTING_NO_PAGE_MARKER`
   otherwise; RESULT names the page, the entry and the missing field). A minimal one-page example:
   `{"schema": "cps.vm-drive-listing.v1", "folder": "CPS/qualification", "name_filter": null, "pages": [{"kind": "drive#fileList",
   "incompleteSearch": false, "files": [{"id": "1AbC", "name": "GENESIS_0a1b2c3d_20261109T120000Z.json",
   "createdTime": "2026-11-09T12:00:05.123Z", "md5Checksum": "0123456789abcdef0123456789abcdef", "size": "1024",
   "mimeType": "application/json"}]}]}`;
3. every `DOWNLOAD id=<Drive id> name=<file name> -> <local path>`: download **that id** to that exact path
   (`id=CPS_FOLDER_PATH` means: the file at `<name>` in the static CPS folder). The local path may end in a name other
   than `<name>` (a second copy of one file): save it under the printed path all the same. The helper creates the folder
   of every printed listing and download path; if it is missing anyway, create it (`mkdir -p`) and save there;
4. then `NEXT:` and each `THEN:` in order. **A `RUN` line replaces everything still pending:** once you have run it, the
   lines after it in the earlier output are void; follow only the new output (its UPLOADs, listings, downloads and its
   own NEXT and THEN lines). Then the command is finished.

Other endings:
- `STOP: <CODE> <hint>`: a STOP counts first and stays in force. Do its UPLOAD lines; then, if it printed NEXT/THEN
  lines, follow that chain (each RUN line's output replaces the pending lines as usual) only through the freeze of this
  job, its upload, its verification and `evict`; never run a command of another job (a `prepare`, `nonattempt`,
  `job-start`, `final`, or a `start-note` of another job). Then stop and tell the owner the STOP code (handback case C
  unless the hint says otherwise). `STOP_AFTER_FREEZE code=X` means the same. Two STOPs are not handbacks:
  `STOP: WORKER_DIED` of a self-test (its NEXT is `$V selftest`): run that line and go on (a new self-test, not a retry);
  `STOP: FINGERPRINT_CHANGED` (the toolchain changed since session start, O47): do its UPLOAD lines, note the code for the
  owner, then run its NEXT (session start again, section 1.4), which prints the self-test of the new fingerprint; every
  job waits until that self-test has passed.
- `REFUSED: <CODE>` (or exit 4 with a code in RESULT): nothing changed and nothing is to be uploaded. If it printed NEXT
  lines, do them. Otherwise read `hint` in RESULT, fix the cause, run the same command again. **If you cannot fix the
  cause, run `$V status` once; if status prints the same refused command again, stop and hand back case C** with the
  RESULT line (never loop on a refusal).
- Exit code 10 (usually `NEXT: RUN_SAME_COMMAND_AGAIN`): do its UPLOAD lines first, then its SAVE_DRIVE_LISTING and
  DOWNLOAD lines, then run the same command again. A listing the helper refused is set aside by the helper and printed
  again (`RESULT` names the code, folder and path); after the third refusal of the same listing it stops (case C).
- `NEXT: RUN $V wait`: a long command runs in the background. Run `$V wait` again until it prints something else.

RUN lines are exact. Replace only these tokens, each with the value you yourself attest, and change nothing else:
`{CONVERSATION_ID}` (the id or link of the conversation the line is about), `{GENERATOR_MODEL}`, `{COPY_FILE}`,
`{LOG_FILE}`, `{PROFILE_FOLDER}`, `{CASE}`, `{REASON_TEXT}`, `{SEEN}`. A value must not start with `<` and must not
contain a newline or a `'`. The same tokens appear in some UPLOAD lines (`UPLOAD {COPY_FILE} -> ...`, after
`delivery-note --prepared`): there they stand for the same file you gave in the RUN line (the helper never prints the
copy's own file name); upload that file under its own name.

Actions you will see:

| Action | What you do |
|---|---|
| `RUN <command>` | run it exactly (tokens replaced) |
| `OPEN_CONVERSATION role=R prompt=P` | open a **new** conversation; its only message is the full text of file P; no Drive connector, no uploads, no other job |
| `WAIT_FOR_CONVERSATION role=R` | wait until that conversation has ended (or broke); then go on at once |
| `CONTINUE_CONVERSATION role=V` | ask the same reviewer, in the same conversation, to complete `qa/visual_review/VISUAL_REVIEW.json` |
| `CONFIRM_CONVERSATION_ENDED role=R` | stop the conversation if it still runs; confirm in the platform that it has ended |
| `EXPORT_TRANSCRIPT to=P` | export that conversation's transcript to P (if the platform cannot, skip it: the options that follow have a line without a transcript, `WRITTEN_OR_DOUBT`) |
| `WRITE_GENERATION_RECORD path=P example=E` | write the generation record at P, following E (deploy/run/RUN_JOB_COMMANDS.md) |
| `CHOOSE_FROM_TRANSCRIPT` + `OPTION:` lines | read the transcript; do exactly one OPTION: `NO_CONVERSATION` (no conversation exists in your conversation list after the START upload), `NOTHING_WRITTEN` (the transcript shows nothing was written), `WRITTEN_OR_DOUBT` (written, partly written, maybe written, or no transcript: the export failed or came out empty) |
| `CHOOSE_SEEN_TOKENS since=P [dead=D1,D2]` + `OPTION:` lines | `SEEN` when you saw any `BIND=` token of this job printed after you uploaded package P (the token printed just before P's own upload may be included: it is recorded and ignored), or printed by the command that made a package named in `dead=` (it reached Drive damaged): put **all** of them, comma-separated, in `{SEEN}`; else `NOT_SEEN`. A token of another stage is refused `INCIDENT_SEEN_INVALID`: copy the tokens again |
| `ASK_USER_IF_RECEIVED` / `ASK_USER_IF_SEND_NOW` + `OPTION:` | ask the user; do the matching OPTION |
| `WAIT until=T` | run nothing until T (UTC), then the THEN lines |
| `DELIVER folder=F sha256=S` | the deliverable is the `.xlsx` in F whose sha256 is S: make the personal copy (09_PERSONAL_COPY.md) |
| `STOP_AFTER_FREEZE code=X` | after the freeze line before it (and its verification and evict) is done, stop and tell the owner X |
| `SEND_PREPARED_COPY_AGAIN` (in an OPTION) | send the prepared copy again from the profile's `deliveries/`, then the RUN line of that option |
| `END_TOOL_CALL` | (probe P5 only) end the tool call now and run nothing more in it; the next line runs in a new tool call |
| `TELL_MAINTAINER kit=K sha256=S copy_from=F copy_to=cps_runtime/` | tell the maintainer that the kit K you rebuilt is in F, and that it should be copied (a Drive copy) into `cps_runtime/` with its row added to `FOLDER_MANIFEST.md`; then go on at once |
| `SEND_COPY`, `TELL_MAINTAINER`, `TELL_OWNER`, `HANDBACK case=B/C`, `FIX code=X`, `WAIT_FOR_USER_REQUEST`, `DONE` | as named; `FIX` means what RUN_JOB_COMMANDS.md says that runner code needs |

## 1. Session start (after every reset, and at the start of every new chat)

1. If `~/cps/.git` exists: `mv ~/cps ~/cps-phase1-old-$(date -u +%Y%m%dT%H%M%SZ)` (a new name each time, so it never
   moves into an earlier one). Then `rm -rf ~/cps/inbox/cps; mkdir -p ~/cps/inbox/cps` (only that subfolder: the rest of
   the inbox may hold a restore in progress).
2. Download `FOLDER_MANIFEST.md` from the CPS folder to `~/cps/inbox/cps/FOLDER_MANIFEST.md`.
3. Save the listing of the records folder (`CPS/qualification`; after `RELEASED_FOR_USE`, `Dots Folder/CPS_JOB_RECORDS`)
   as `~/cps/inbox/DRIVE_LISTING.json`, and the listing of `CPS/setup` as `~/cps/inbox/SETUP_LISTING.json` (every page,
   rule 0.2; `name_filter` null).
4. Run, with `COMMIT` set to the 40-hex release commit (the `commit:` line of `cps_runtime/RUN_SESSION.md` in the CPS
   folder; until the maintainer has put that file there, ask the maintainer and do not guess) and your model name in
   quotes:
   ```sh
   [ -d ~/cps/repo/.git ] || git clone -q https://github.com/cookielolalex/CPS.git ~/cps/repo
   git -C ~/cps/repo fetch -q origin "$COMMIT" 2>/dev/null; git -C ~/cps/repo checkout -q "$COMMIT" && bash ~/cps/repo/deploy/vm/session_start.sh --operator-model "<model>"
   ```
   If the checkout fails after a partial clone, remove `~/cps/repo` (it holds no state) and repeat once.
5. While it exits 10: do its UPLOAD lines (a folder sentinel, for example), then its SAVE_DRIVE_LISTING and DOWNLOAD
   lines, and run the same `session_start.sh` command again. The session kit comes one of two ways, chosen by
   `FOLDER_MANIFEST.md`; you only follow the printed lines:
   - **zip route** (a `cps_runtime/SESSION_KIT_<v>.zip` row): one `DOWNLOAD id=CPS_FOLDER_PATH` of the zip, about 20 s;
   - **parts route** (no zip row, one line `kit-sha256: SESSION_KIT_<v>.zip <bytes> <sha256>`): the maintainer uploaded
     the kit as text bundle parts (copies A and B, `cps_runtime/kit/<stem>/`) and copied its workbooks inside Drive
     (`cps_runtime/kit/<stem>/bin/`). The first run exits 10 `NEED_KIT_PARTS` with one DOWNLOAD per part copy and
     binary; the next run rebuilds the zip with `deploy/make_kit.py assemble` (a slip in one copy is skipped) and checks
     its sha256 against that line (`STOP: KIT_NOT_REBUILT` otherwise; tell the maintainer). The first session that
     rebuilt a kit also uploads it to `CPS/setup` and prints `TELL_MAINTAINER kit=...`; once the maintainer has copied it
     into `cps_runtime/` and added its row, every later session takes the zip route.
   Rebuilding costs about 2 Drive calls per bundle part plus 1 per workbook after **every** reset (estimate for the
   qualification kit, about 4.7 MB with 36 workbooks: at 30 KB parts about 10 parts, so about 20 + 36 + 1 = 57 calls,
   about 19 minutes at 20 s per call; with 300 KB parts about 40 calls, about 13 minutes; the rebuild itself takes under
   2 s). The zip route costs one call, so ask the maintainer for the copy at once.
6. Do its UPLOADs (the SESSION note last), then its NEXT:
   - `$V selftest` on a new fingerprint, then `$V wait` until it prints `fingerprint-pass` (about 13 minutes);
   - after a restore: the incident line or options (section 4), then the second listing and `$V recheck`;
   - otherwise the next step of the job.

## 2. One qualification run

Uploads go to `CPS/qualification`, in the printed order. Always take the next command from the previous output or
from `$V status`; never type runner arguments yourself. Every `wrap` and `start-note` recomputes the toolchain
fingerprint (2-4 s) and STOPs `FINGERPRINT_CHANGED` (rule 0) when it differs from the session's; a change during a stage
is recorded in its package and STOPs after the package's upload.

1. `$V wrap prepare ...` (the line status printed; `$V wait` while it prints that). Upload CP-P.
2. `$V start-note --job-dir D --role G`. It first asks for a narrow listing of CP-P (exit 10): save it, run it again.
   If that listing does not show CP-P, it prints CP-P's UPLOAD again before the listing (at most three times, then
   `STOP: UPLOAD_NOT_CONFIRMED`). Upload START-G.
3. Open the new conversation (OPEN_CONVERSATION). If opening seems to fail: look at your conversation list. If a
   conversation with this prompt was created after the START upload, it is the conversation: use it. Only if none
   exists, open it again under the same START. Never open a second conversation while one exists, and never run
   `incident` for this inside a session.
4. `$V link-note --job-dir D --role G --conversation {CONVERSATION_ID}` (start-note's last line). Upload LINK-G; its
   output prints the wait and the `ai-archive` line.
5. When the conversation has ended: at once `$V ai-archive --job-dir D --role G`. Upload AI-G.
6. Export the transcript if the platform can (`EXPORT_TRANSCRIPT`), then write `run/GENERATION_RECORD.json`
   (`WRITE_GENERATION_RECORD`): `transcript_status: exported` with the exported file's sha256, or `not_available` with
   the reason. Then `$V status` (its `wrap finish` passes the transcript when the record says `exported`).
7. `$V wrap finish ...` (printed by status; first the narrow listing of AI-G it asks for). Upload the PNG parts, then CP-F.
8. `start-note --role V` (narrow listing of CP-F first), the new reviewer conversation, `link-note`, `ai-archive`.
   Upload START-V, LINK-V, AI-V.
9. `$V wrap visual-record ...` (narrow listing of AI-V first). Upload CP-V.
   If the review is refused as incomplete: `CONTINUE_CONVERSATION role=V`, then `$V ai-archive --role V --revision`
   and the printed `wrap visual-record` again. No new START.
10. `$V wrap freeze --job-dir D --operator-model <model>` (it runs freeze and verify-frozen). Upload FZ.
11. `$V evict --job-dir D`: it asks for the downloads (or listing) that verify the FZ and its parts; do them, run it
    again. A copy that fails is never asked for again: the next copy, an UPLOAD of the local file (at most three times)
    or `rebuild-parts` follows. Then `$V status` gives the next run.

A conversation that ends without its file: `CONFIRM_CONVERSATION_ENDED`, `EXPORT_TRANSCRIPT`, then
`CHOOSE_FROM_TRANSCRIPT` with two options: `NOTHING_WRITTEN` (the transcript was exported, is not empty, and shows
nothing was written: its RUN line passes the transcript) or `WRITTEN_OR_DOUBT` (anything else, **including an export
that failed or came out empty**: doubt counts as written). Then `wrap interrupt`, the replacement reviewer or the freeze,
as printed. You never edit a RUN line to drop an argument: each case has its own printed line.

A run that failed by reset divergence (`STOP: RESET_DIVERGED`) can only be frozen: `status` and session start print its
`wrap freeze` (never another step of it).

Before qualification: `$V genesis --first-ledger` once (status prints it), upload GENESIS, tell the maintainer its name
(`TELL_MAINTAINER`). Then all nonattempts (`wrap nonattempt`, one FZ each, each evicted). At the end: `$V final`
(it asks for a fresh listing; uploads LEDGER_FINAL, then ALL_FROZEN.json last), then handback case B.

## 3. One everyday job (one at a time; it always ends frozen)

1. Write `JOB.json`, `JOB_TITLE.json` and the source into `~/cps/everyday_inputs/<case>/`; `$V job-start --case {CASE}`.
   Upload INPUTS (to `Dots Folder/CPS_JOB_RECORDS`). If the runner refuses the `wrap prepare` before it made the job
   folder (for example `RUNNER_JOB_CONFIG_REFUSED`), the output prints `FIX code=...` and `$V job-start --case <case>`:
   correct the inputs in that folder, then run that line. It gives the same run new inputs (a new INPUTS upload; at most
   three times, then `STOP: EVERYDAY_PREPARE_REFUSED`, case C). Unchanged inputs are refused `JOB_START_INPUTS_UNCHANGED`.
2. Steps 1-9 of section 2 with the printed everyday lines.
3. When the copy can be sent now: `$V wrap deliver-check ...` (CP-D). Make the personal copy (`DELIVER`).
4. `$V delivery-note --prepared ...`: upload the copy, the log and the note to `<profile>/deliveries/`, the note also to
   the records folder. Send the copy.
5. `$V delivery-note --sent ...`: upload; then the printed `wrap freeze`, the verification and `$V evict --job-dir D`.
   If the user does not want the file now, or the job stopped, the printed `wrap freeze` closes it the same way.
6. A generator or scope conversation that wrote nothing: the printed `wrap freeze`, evict, then
   `$V job-start --case <case> --restart-of E<run id> --incident <name>` (status prints it; once per job).

## 4. After a reset

Session start restores the newest package and prints **one** incident line, or, for a conversation that was open,
`CONFIRM_CONVERSATION_ENDED`, `EXPORT_TRANSCRIPT` and the options. First stop that conversation if it still runs.
Classify **from the transcript**, never from the VM; doubt (or no transcript) counts as written. Give every `BIND=`
token of the job you saw after the upload of the package `CHOOSE_SEEN_TOKENS` names (`since=`), and every token of a
command whose package it names in `dead=` (`SEEN`), or `NOT_SEEN`. Then save the second listing and run `$V recheck`.

| Where the reset hit | Classification | Then |
|---|---|---|
| during or after a runner command whose package did not reach Drive | `NON_AI_STAGE_LOST` (seen or not) | the same `wrap` again, bound to the token; a mismatch is `STOP: RESET_DIVERGED`, then `wrap freeze` (a failed run) |
| after START, no conversation in your list | `AI_NO_CONVERSATION` (once per START) | `start-note` (same attempt) |
| conversation open or broken, transcript shows nothing written | `AI_NOTHING_WRITTEN` | `wrap interrupt ...` (qualification S/G), the replacement reviewer (V), or freeze |
| written, partly written, maybe written, or no transcript | `AI_WRITTEN_LOST` | `wrap freeze`: for S or G a failed run, for V failed visual QA (O46); never regenerated |
| after the AI archive upload | `AI_ARCHIVED` (seen or not) | the consuming wrap (finish after re-writing the generation record) |
| after the FZ upload, nothing printed after it but `evict` or `final` | `NONE_IN_FLIGHT` | verification and `evict` |
| after the FZ upload, while the next runner command was printed (a `prepare` or `nonattempt`) | `NON_AI_STAGE_LOST` (seen or not: `NOT_SEEN` if it never ran) | verification and `evict`, then that command again, bound to the token |
| an AI archive that reached Drive damaged (every copy fails its check) | `AI_WRITTEN_LOST` only (printed alone) | `wrap freeze` (failed run) |
| everyday: after job-start, before the prepare's package | `NON_AI_STAGE_LOST` | the run's `wrap prepare` (once) |
| a START on Drive whose package is not | — | `STOP: RESTORE_NOTES_AHEAD_OF_PACKAGE` (case C) |
| a `prepare`/`nonattempt` that left no job folder, with tokens that disagree | `NON_AI_STAGE_LOST` (`SEEN`) | `STOP: PENDING_JOB_DIVERGED` (case C; nothing to freeze) |

`RESTORE_TARGET_NOT_EMPTY`: **do not delete anything**; upload the STRAY archive and hand back case C. It is also printed
at session start when a job folder or ledger exists that this VM did not make or restore (for example a conversation
still writing after a reset).

## 5. Maintainer: assemble and audit

After `ALL_FROZEN.json` is on Drive, download the qualification folder flat into `DIR` and the setup folder into `SDIR`,
with their saved listings (the same wrapper), in a container where the original absolute paths can be created
(`/home/agent/...`), from a clean checkout at the release commit. Drive may hold several copies of one name (a retried
upload): for every FZ archive and PNG part that `ALL_FROZEN.json` names, download **the Drive id it records**
(`runs[].archive.id`, `runs[].png_parts[].id`), never "the newest copy"; for any other name with several copies, keep the
one whose md5 the listing shows for the copy you use. `assemble` refuses a wrong copy (`ASSEMBLE_ARCHIVE`,
`ASSEMBLE_PARTS`), it never accepts one:

```sh
python3 -I -B deploy/vm/cps_vm.py assemble --drive-dir DIR --verify-frozen --report DIR/ASSEMBLE_REPORT.json
python3 -I -B deploy/vm/cps_vm.py audit --drive-dir DIR --listing DIR_LISTING.json --setup-dir SDIR \
    --setup-listing SETUP_LISTING.json --release RELEASE.json --config VM_HELPER_CONFIG.json --report DIR/AUDIT_REPORT.json
```

`assemble` writes every frozen folder and the ledger at their original paths (it refuses existing targets) and, with
`--verify-frozen`, runs runner v4 `verify-frozen` on each: exit 0 only when every folder prints `NEXT: DONE`. `audit`
writes `AUDIT_REPORT.json` (anomalies, listed items, `runs_failed_by_reset`) and `O52_COMPARISON.json` (one row per
START; fill `owner_platform_created` from the platform's conversation list before scoring, O52). It reads every
FINGERPRINT_PASS and SELFTEST note in SDIR (a pass that does not validate counts as none) and takes the clock tolerance
and the expected test count from `--config` (the kit's `VM_HELPER_CONFIG.json`; default: next to `--release`).
Exit 0 means no anomaly.
Runs flagged `RESET_DIVERGED` or `AI_OUTPUT_LOST` in `ALL_FROZEN.json` (listed in `runs_failed_by_reset`) count as failed
runs (O44, O46). A run flagged `VISUAL_QA_FAILED_BY_RESET` (its reviewer output was lost, or the replacement reviewer
also wrote nothing; listed in `runs_visual_qa_failed_by_reset`) has failed visual QA; its frozen output is scored as it is
(O46, design E4). `FROZEN_UNVERIFIED` runs (`runs_needing_owner`) are not scored until the owner rules on them.

Before the frozen O31 aggregator runs, check its manifest against these flags:
```sh
python3 -I -B deploy/vm/apply_frozen_flags.py --all-frozen DIR/ALL_FROZEN.json --manifest GATE_MANIFEST.json \
    --empty-carrier-sha <sha256 of the empty carrier> [--owner-rulings RULINGS.json] --out DIR/FLAGS_CHECK.json
```
Exit 0 only when every failed run and nonattempt is scored as the empty carrier (score 0, in the reader's denominators),
no other run is, and every `FROZEN_UNVERIFIED` run has an owner ruling. **This check is a G3 candidate, not admitted:
until it (or an admitted aggregator change that does the same) is reviewed and admitted, qualification scoring is
blocked**, because the frozen aggregators do not read `ALL_FROZEN.json`.

## 6. Release gates and probe P5 (before the first released kit)

A released kit (`RELEASED_FOR_QUALIFICATION` or `RELEASED_FOR_USE`) runs nothing until its `VM_HELPER_CONFIG.json`
`release_gates` are answered; session start STOPs `RELEASE_GATE_OPEN` (case C) otherwise:
- `p5_detached_survival` `PASS` with `p5_tool_call_seconds` (the longest tool call that completed) at least
  `wrap_foreground_seconds` + 60. `FAIL` means every job waits (O50-like) until the design is changed;
- `transcript_policy`: `EXPORT_CONFIRMED` (probe P1 showed a transcript can be exported; needs `transcript_export: true`)
  or `OWNER_DECISION` with its decision id (`transcript_owner_decision`, for example whether an owner check of the
  conversation may replace the transcript; without one, every interrupted conversation counts as written).

Probe P5 (the maintainer asks for it with P1-P4; no kit or session is needed, only the repository at `~/cps/repo`):
1. `python3 -I -B ~/cps/repo/deploy/vm/cps_vm.py probe-p5 start`. It starts a detached worker and prints
   `END_TOOL_CALL`, a `WAIT` and the check line: end the tool call, wait, then run the check in a **new** tool call.
2. `python3 -I -B ~/cps/repo/deploy/vm/cps_vm.py probe-p5 hold --seconds 60`, then each printed `hold` line (240, 600,
   1200 s), each in its own tool call. When a call is killed or never returns, stop holding.
3. `python3 -I -B ~/cps/repo/deploy/vm/cps_vm.py probe-p5 check` (at least 60 s after start): upload the printed
   `PROBE_P5_*.json` to `CPS/reports` and tell the maintainer (`TELL_MAINTAINER probe=P5`). Its `verdict` is `PASS` only
   when the worker outlived the tool call that started it; `longest_completed_hold_seconds` is the tool-call limit.

Tests: `python3 -I -B deploy/vm/test_cps_vm.py --work /abs/NEW_DIR --jobs 4` from a clean clone (see the test file's
docstring). `--jobs N` runs the scenarios in N parallel processes (each in its own folder) and merges the results.
Measured 2026-11-09 on a 4-CPU machine (round 4): 1,678 tests, 749 s with `--jobs 4`; the scenario times sum to
2,768 s, so the serial run (`--jobs 1`) is over the 30-minute limit of spec 11.5: use `--jobs 4` or more.
