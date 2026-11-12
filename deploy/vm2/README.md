# cps-vm-helper.v2.1: the Dot's procedure

This page is for the Dot, the operator of CPS jobs on the VM. The helper prints one block at a time. You do exactly
what the block says, then run what its last line says. You never decide anything about the journal yourself.

Specification: `docs/handoff/VM_HELPER_V2_SPEC.md`, changed by `docs/handoff/VM_HELPER_V2_SPEC_DELTA_PROBES.md` and
`docs/handoff/VM_HELPER_V21_DELTA.md`. This page includes the v2.1 amendment from probes M008 to M012 and its fix
round (delta section 9): the helper's files are under `/tmp/cps`, each command has its route, and section 2.4 gives
the operating rules.

## 1. After a reset, or in a new operator chat

The helper keeps every file it writes under `/tmp/cps` (its base). The light setup keeps the tools in `~/cps-tools`.
Run the bootstrap below, then `go`:
- after a reset (`/home/agent` is empty), and in a new operator chat;
- when `/tmp/cps/vm.sh` or `~/cps-tools/env.sh` is missing, for example when `bash /tmp/cps/vm.sh go` says
  `No such file or directory`. When an owner or maintainer message starts your work, check both files with `ls`.

Run the lines exactly, as one command, through the elevated route (`sandbox_permissions` set to
`require_escalated`): the git lines use the network, and the setup that `session_start.sh` runs writes
`~/cps-tools`. `COMMIT` is the 40-hex commit of your last `CPSV-REPO` line. With a hint, also pass the `head` and
`kit` values of your last `CPSV` line. When that `kit` value is `none`, leave out `--hint` and `--kit` (`--kit none`
also means no hint).

<!-- bootstrap:begin -->
```
COMMIT=<the 40-hex commit of your last CPSV-REPO line>
export CPS_VM_BASE=/tmp/cps
[ -d /tmp/cps/repo/.git ] || git clone -q https://github.com/cookielolalex/CPS.git /tmp/cps/repo
git -C /tmp/cps/repo fetch -q origin "$COMMIT"; git -C /tmp/cps/repo checkout -q --detach "$COMMIT"
bash /tmp/cps/repo/deploy/vm2/session_start.sh --commit "$COMMIT" [--hint <seq6> --kit <hex12>]
```
<!-- bootstrap:end -->

- The base is set only by the line `export CPS_VM_BASE=/tmp/cps`. Without it `session_start.sh` stops with
  `SESSION_LAYOUT`, and it refuses a base inside `/home/agent`. The launcher it writes, `/tmp/cps/vm.sh`, carries the
  base and the tools folder itself, so no later command sets anything.
- **Step 0, when your notes are gone.** Find `VM2_RELEASE.md` in the folder `CPS` by exact name and download it.
  Its one line `commit: <40 hex>` gives `COMMIT`. If the file is not there, stop and tell the owner
  `SESSION_NO_COMMIT` (case C). Never guess a commit.
- If the checkout fails after a partial clone, remove `/tmp/cps/repo` (it holds no state) and run the bootstrap
  once more. A second failure: stop and tell the owner `SESSION_GIT_ERROR` (case C).
- `session_start.sh` prints `CPSV-REPO commit=<40 hex>`. Keep that line in your notes together with the last `CPSV`
  line you saw.
- **A maintainer's bootstrap.** When a maintainer message gives you a bootstrap (the block above with `COMMIT`,
  `--hint` and a new `--kit` value filled in, for example to clear a stop, section 6), run exactly that, as one
  command through the elevated route, then run `go`. Never run `session_start.sh` alone: without the line
  `export CPS_VM_BASE=/tmp/cps` it stops with `SESSION_LAYOUT`.
- **The bootstrap may be run again.** It holds nothing of the series, so it is the one command you start again
  yourself: if it died, if its session is gone, or if you ran it through the standard route by mistake (it then
  shows `Read-only file system`), run it once more through the elevated route. If it dies again, tell the owner
  `NO_BLOCK`; if it shows `Read-only file system` through the elevated route, tell the owner `READ_ONLY_FS` (both
  case C).
- **`STOP SETUP_MISSING HANDBACK C`.** A stage needs the setup of this boot and commit. If `~/cps-tools` is gone, was
  set up for another boot or commit, or its setup failed, `go` stops with `STOP SETUP_MISSING HANDBACK C` before the
  stage, and nothing changes. This is the one HANDBACK C stop you clear yourself: tell the owner, run the bootstrap
  once (with your notes), then `go`. If `go` stops with `SETUP_MISSING` again, wait for a maintainer message (the
  setup's log stays in `/tmp/cps/outbox`).

## 2. The rule

Run `bash /tmp/cps/vm.sh go`, then do the block it prints, exactly. Every block is:

```
CPSV series=<S> head=<seq6> kit=<hex12|none> at=<at> mode=<mode> state=<STATE>
UPLOAD <abs> TO <folder> AS <name>        (0..n, in order)
FIND <folder> NAME <name>                 (0..n)
DOWNLOAD <folder> ID <id> TO <abs>        (0..n)
DO: <exactly one action>
```

**Run every helper command in the foreground.** If the command tool gives you back a session before the command has
exited, poll that same session each time the tool returns, until the process exits, and start no other helper command
meanwhile. A command may run up to 1,200 s (a `go` that runs a stage first prints one line
`CPSV-RUNNING kind=<kind> since=<UTC> max=<s>`). The result of a command is its last block: from the last line that
starts with `CPSV ` through the `DO:` line, which is always the last line. If the process exited and its output has no
`CPSV ` line, or no `DO:` line after the last `CPSV ` line, run `go` once; if that happens again, stop and tell the
owner `NO_BLOCK` (case C).

**Routes.** Your command tool runs each command through one of two routes, chosen by `sandbox_permissions`. Run the
bootstrap of section 1, also one that a maintainer message gives you, through the elevated route
(`require_escalated`). Run everything else for the helper through the standard route (`use_default`): every helper
command (`bash /tmp/cps/vm.sh ...`) and every file you write for the helper (the saved search results under
`/tmp/cps/attest`, the `cp` of a download to the path a DOWNLOAD line names, the final message and tool lists, the
everyday inputs and the personal copy). The standard route can write `/tmp`, where all of these are. Never move a helper command to the elevated route because it failed (section 2.4). Create no
standing approval and no prefix rule: leave `prefix_rule` empty.

A refusal (exit 4) adds one line `REFUSED <CODE>` right after the header, sometimes followed by the key or the file
name it is about. Your last answer was not used. Do the block that follows the REFUSED line: usually it is the block
you had before (correct your answer and run it again); after a failed download it is a FIND block for that file
(section 3.2). After a REFUSED line, never repeat an upload: redo only the FIND lines (if your saved result was wrong)
and the command. Keep the last `CPSV` line in your notes. Exit codes: 0 follow the block, 3 the block ends in
`DO: STOP`, 4 refused, 2 usage.

Do the UPLOAD lines first, in order, each **once**, the first time you see them (never retry an upload yourself). A
block that the helper prints again, after a REFUSED line or because you ran `go` before the command it asks for, has
no UPLOAD lines. Then do every FIND line, whatever the upload returned, then every DOWNLOAD line. If a DOWNLOAD or FIND
returns a tool error or times out, run that line once more before you run the helper. A FIND by NAME is an exact-name
search in that folder; when a search says it has more pages, fetch them all.

**Save what the search tool returns, never retype it.** For each block, write what its FIND lines returned into a
**new** file, for example `/tmp/cps/attest/raw_0001.json`, then run the block's
`found --at <at> --raw <the path of that file>`. Serialize each returned object unchanged (for example with
`JSON.stringify` in your orchestration code) and write that text to the file (for example with a Python heredoc).
The helper moves the file away once it has read it, so a path is used only once. The file holds:
- for a block with one FIND line: the object that search returned, `<the object>`, or a list of it, `[<the object>]`;
- for a block with two FIND lines: a list of the two objects, in the order of the FIND lines,
  `[<the object of the first FIND>, <the object of the second FIND>]`;
- for a FIND whose search had two pages: a list of its pages in place of its object, for example
  `[[<the first page>, <the second page>]]` for a block with that one FIND line.

When the platform refused an upload of the block, add `--refused <name>` for that file (section 3.1). Only if you
cannot save a returned object, use the manual form: `found --at <at>` followed by, for every FIND line in order,
`--name <name>` and either one `--file <id>:<size>` per copy the search showed (the size in bytes exactly as shown) or
`--none`. For each DOWNLOAD line, download the raw file with that id (the Drive fetch tool with `download_raw_file`
true and `include_base64` false, then the platform's download tool, which saves the original file and tells you its
path and size), then copy that downloaded file with `cp` to exactly the path the line names (its folder exists). Never
retype a file, never decode base64 by hand, and never put any other file at that path; the helper checks the size and
sha256 of what you copied. If the platform refuses a DOWNLOAD, do not run `go`: ask the owner to approve it, download
again, then run `go`. Never edit, rename or delete a file on Drive.

### 2.1 Two lines that are not blocks

- `CPSV-RUNNING kind=... since=... max=...` is printed first by a `go` that runs a stage (or by `session_start.sh`
  before the setup). It names no result. Keep polling the same command session until the process exits; the block
  follows it.
- A helper command that finds another one still running prints exactly three lines and exits 4, changing nothing:
  `CPSV-BUSY kind=... since=...`, `REFUSED HELPER_BUSY`, `DO: POLL`. Do what POLL says (section 3). Never start a
  second helper command while one runs.

### 2.2 Qualification and drill (series Q1, D1)

1. The maintainer gives you the commit and the kit (the `--hint 000000 --kit` value of the first session). Check
   rule 8 of section 2.4 first. Then run the bootstrap of section 1, then `go`.
2. Follow every block. The helper runs the kit's job list in this order: first the cases without a source, as
   nonattempts, all of them for reader A and then all of them for reader B; then reader A for every other case in the
   list's order; then reader B for every case in the same order. A run that the helper restarts comes right after it.
   Each run goes through prepare, the generator conversation (and the scope reader for a large workbook), finish,
   the visual reviewer and freeze.
3. Every stage runs in the foreground of one `go` (up to 1,200 s; the finish stage takes minutes). Poll until it
   exits. Then the helper saves the result on Drive through its SAVE blocks (UPLOAD, FIND, `found`, DOWNLOAD, `go`);
   nothing that depends on a result is shown before it is saved.
4. When the owner must be told something (a stopped run), the block is `NOTIFY_OWNER`.
5. `STOP FINAL HANDBACK B` ends the series: tell the owner that qualification generation is complete.

### 2.3 Everyday jobs (series E1)

1. With no job running the block asks `case=CASE_ID`. Answer it only when a user asked for a job: first put the user's
   three files (`JOB.json`, `JOB_TITLE.json` and the source workbook it names) in
   `/tmp/cps/everyday_inputs/<case>/`, then answer with that case id. Before you answer `case=`, keep the exact
   text of `JOB.json` and `JOB_TITLE.json` and the place of the user's workbook in your notes.
2. Follow the blocks through prepare, the generator, finish and the visual reviewer, exactly as in qualification.
   Every upload goes into the everyday records folder (`Dots Folder/CPS_JOB_RECORDS`) or the profile's `deliveries`
   folder; both must be inside the owner's standing pre-approval of uploads (section 7).
3. Delivery: `DELIVER ... to=copy` (make the personal copy and its log, answer the two paths), then
   `DELIVER ... to=user` (send it, answer `sent=yes`). After a reset during a delivery you are asked whether the copy
   reached the user (`arrived=`); ask the user, never send a second copy on your own.
4. A failed job is never retried on your own: the block asks you to tell the user (`asked=yes`); a new job starts only
   at the user's request.
5. `REFUSED INPUTS_CHANGED`: the files in `everyday_inputs/<case>/` are not the ones the job saved (a reset empties
   that folder). Put the same three files back, unchanged, from your notes and the user's workbook, then run `go`. If
   you cannot (you no longer have them, or the user changed them), tell the owner the code and your last `CPSV` line,
   then run `go` until the helper stops with `STOP SLIP_LIMIT HANDBACK C` (it refuses at most 3 times). A maintainer
   clear of that stop abandons this job; a new job starts only at the user's request.

### 2.4 Operating rules

1. Work in the coordinating conversation: the one in which the owner (or a user) talks to you, which a maintainer
   message's `CLAIM.md` names. A worker or a scheduled check (for example a mailbox check run by a worker) never runs
   the bootstrap or a helper command. Never hand a helper command, a stage or a block's UPLOAD, FIND or DOWNLOAD lines
   to another conversation or worker. The conversations the helper asks you to open (the generator, the scope reader and
   the visual reviewer) run no helper command; never ask them to run one.
2. Run each helper command in the foreground and poll its own session until it exits (section 2).
3. Prefer polling to waiting. While a helper command runs, and while a conversation you opened for the helper (S, G
   or V) has not ended, never end your turn and never set a wait or a wake-up of the platform. Between two checks of
   such a conversation run `sleep 300` in the foreground through the standard route. If your turn ends anyway, end
   your last message to the owner with exactly this line:
   `CPS paused while a helper command or a CPS conversation ran: reply continue to resume.`
   When the owner replies `continue`, poll that command's session or check that conversation; if you no longer have
   the command's session, follow rule 5.
4. Never use `ps`, `kill` or a process id to judge whether a helper command runs: each command has its own process
   space, and the ids repeat. Only the helper's own lines decide: `CPSV-RUNNING`, `CPSV-BUSY` and the block.
5. If a poll says that the process is unknown, or the session is gone, never start that command again yourself. Run
   `go` once and do the block it prints. After a stage died, that block is `STOP FOREGROUND_DIED HANDBACK C` (after
   the self-test: `STOP SELFTEST_DIED HANDBACK C`, or, the first time, the self-test once more). If the dead command
   ran no stage, it is the block to follow. If the command still runs, `go` prints `CPSV-BUSY` and `DO: POLL`. The
   bootstrap is the exception (section 1).
6. A command that the platform's automatic review stopped before it ran (for example a review timeout) has not run.
   Only the bootstrap goes through the elevated route and its review. Retry it once through the same route. If the
   review stops it again, stop and tell the owner `REVIEW_STOPPED`, the command and the review's message, and ask the
   owner to approve it; when the owner says it is approved, run it again, and this rule applies afresh. Uploads are
   never retried: an upload the review refused follows section 3.1.
7. Any `Read-only file system` in a command's output means that the command wrote outside `/tmp` or ran through the
   wrong route. Never run it again through the elevated route or in another folder (the bootstrap is the exception,
   section 1). Stop and tell the owner `READ_ONLY_FS`, that line and your last `CPSV` line, then wait for a maintainer
   message (case C). When the helper's own write meets a read-only file system, it prints
   `STOP READ_ONLY_FS HANDBACK C` itself. One inside the runner's tools shows as another stop of the helper (for
   example `RUNNER_REFUSED`); follow that block.
8. The scheduled mailbox check does nothing while a maintainer message is claimed and the claim is younger than 6
   hours, so it will not resume this conversation. Once the claim is 6 hours old, the check uploads a
   `REPLY_ABANDONED_` file for that message, tells the owner and lets later runs take the next open message. A drill
   or a qualification series runs far longer than 6 hours: start one (section 2.2) only when the message that starts
   it says how the scheduled mailbox check is handled for the series (for example that the owner paused it). If it
   does not say, tell the owner `MAILBOX_UNSETTLED` (case C) and do not run `go`.

## 3. The actions (the `DO:` line)

| action | you do | then |
|---|---|---|
| `RUN bash /tmp/cps/vm.sh go` | run it | follow the new block |
| `ATTEST ... found --at A --raw FILE [--refused NAME]` | do the block's UPLOAD and FIND lines, save the FIND results in one new file (section 2), run `found` with that file | follow the output |
| `ATTEST ... answer --at A k1=PATTERN1 ...` | run `answer` with a real value for each key, matching the pattern named | follow the output |
| `ATTEST after=T bash ... answer ...` | as above; `list_shows_none=yes` means your conversation list shows **no** conversation of that role (section 4) with `attachedAt` at or after T, and `conversation=` is the id of the conversation of that role with `attachedAt` at or after T | follow the output |
| `POLL` | another helper command still runs: go back to its session and poll it until it exits, then follow its block. If you no longer have that session, `WAIT seconds=60`, then run `go` | follow that block |
| `OPEN_CONVERSATION role=R prompt=P folder=F` | open a new conversation (Create Thread, same environment, no extra settings) and give it the full text of file P as its only message. Roles S and G may use only folder F. Role V may open only the PNG files the prompt lists (under F) and may write only `F/visual_review/VISUAL_REVIEW.json`. Never send it a follow-up message. Check it once every 5 minutes, with `sleep 300` in the foreground between checks (section 2.4 rule 3) | when it has ended: write its final message to the file (section 4), run `go` |
| `CONTINUE_CONVERSATION role=V conversation=C message=M` | send the text of file M in conversation C (the only message you ever send into an existing conversation). Check it once every 5 minutes, with `sleep 300` in the foreground between checks | when it has ended: write its final message to the file, run `go` |
| `END_CONVERSATION role=R after=UTC [conversation=C]` | stop the CPS conversation of that role opened after UTC, if it is still running | run `go` |
| `EXPORT_TRANSCRIPT role=R to=P [conversation=C] [after=UTC]` | export that conversation's transcript to P; if your platform cannot, do nothing | run `go` |
| `NOTIFY_OWNER file=P ATTEST ... notified=YES` | tell the owner the content of P | run the answer |
| `ASK_USER file=P ATTEST ... k=PATTERN` | ask the user the question in P | run the answer with the user's reply |
| `DELIVER file=P to=copy ATTEST ... copy=COPYPATH log=COPYPATH` | everyday: make the user's personal copy of P with that user's preferences, as `PERSONAL_COPY.xlsx` with its `PERSONALIZATION_LOG.json` in `/tmp/cps/deliveries/<case>/<user>/<utc14>/` | run the answer with the two paths |
| `DELIVER file=P to=user ATTEST ... sent=YES` | everyday: send P to the requesting user, under the standard file name from the `JOB_TITLE.json` you wrote | run the answer |
| `WAIT seconds=N` | run `sleep N` in the foreground (standard route); set no wait or wake-up of the platform | run `go` |
| `STOP UPLOAD_REFUSED HANDBACK A name=N` | keep N in your notes as refused; tell the owner the code, the file name N and your last `CPSV` line, and ask the owner to approve or deny the upload in the platform | run `go` when the owner says so. Take N out of your notes only when the owner tells you the upload was approved or denied; if the owner only says to continue, keep N in your notes |
| `STOP WAIT_APPROVAL HANDBACK A` | an upload of this series still waits for the owner (you answered `approval=pending`): ask the owner to approve or deny it | run `go` when the owner says so. Take it out of your notes only when the owner tells you it was approved or denied; if the owner only says to continue, keep it and answer `approval=pending` again |
| `STOP SETUP_MISSING HANDBACK C` | the setup of this boot is missing: tell the owner, then run the bootstrap of section 1 once (with your notes) | run `go`; if it stops with `SETUP_MISSING` again, nothing until a maintainer message |
| `STOP <CODE> HANDBACK C` | stop; upload nothing more; tell the owner the code, your last `CPSV` line and, for `SLIP_LIMIT`, the last REFUSED line you saw | nothing until a maintainer message (section 6) |
| `STOP <CODE> HANDBACK B` | stop; tell the owner that qualification generation is complete | nothing |

Handback letters: **A** the owner must do something in the platform (approve or deny an upload), then you run `go`
and the series goes on; **B** the series is complete; **C** stop and wait for the maintainer (nothing more is
uploaded). Apart from `SETUP_MISSING` (section 1), `STOP ... HANDBACK A` is the only stop after which you run the
helper again without a new message.

### 3.1 When the platform refuses an upload

The platform's automatic approval review sometimes refuses an upload, and a timed-out upload may still appear later.

1. Do every UPLOAD line once. Whatever an upload returned (success, timeout, error or refusal), do every FIND line of
   the block and save what the searches returned.
2. Add `--refused <name>` to `found` for an upload the platform refused (an approval review or any refusal message).
   If you are not sure whether the platform refused an upload or failed, treat it as refused. Never use `--refused`
   for a file the block did not ask you to upload (that is refused with `FOUND_SYNTAX`).
3. **Write every refused upload into your notes at once (the file name and the time), and keep it there until the
   owner tells you it was approved or denied.** Your notes survive a reset; the helper's files do not.
4. If the refused file is not found, the helper prints `DO: STOP UPLOAD_REFUSED HANDBACK A name=<name>`. Tell the
   owner the code, the file name and your last `CPSV` line, and ask the owner to approve or deny it in the platform.
   Do not upload it again yourself. Never work around a refused upload: do not upload the file under another name,
   into another folder, in pieces, with another tool or from another conversation; wait for the owner. Run `go` when
   the owner says so; take the name out of your notes only when the owner tells you the upload was approved or denied.
5. The next block FINDs the file first, never uploads at once (an approved upload may have landed). The helper
   uploads one file at most three times; after the third, it stops with `UPLOAD_FAILED HANDBACK C`.
6. A copy that appears late is a second copy; the helper downloads and checks it, and nothing else changes when it
   holds the same bytes.
7. **Every session asks `approval=`.** After a reset, after a maintainer clear and at the start of a series, the
   helper asks `approval=` before it searches the journal. Answer `approval=pending` if your notes still hold a
   refused upload of this series that the owner has not told you was approved or denied, otherwise `approval=none`.
   With `pending` it stops with `STOP WAIT_APPROVAL HANDBACK A`; when the owner has resolved it, run `go`: the helper
   asks again, then searches the journal.

### 3.2 When the helper asks again

- After `found` the helper downloads every copy it does not know yet. If a DOWNLOAD file is missing when you run `go`
  (`REFUSED DOWNLOAD_MISSING`), has another size than the one the search showed (`REFUSED DOWNLOAD_INCOMPLETE`), or is
  another file of the same save (`REFUSED COPY_MISMATCH`), the helper drops that answer and prints a FIND block for
  that file: search again, save the result to a new file, run `found` again.
- An answer it cannot use (a wrong key, a value that does not match its pattern, a missing final message file, a raw
  file it cannot read) is refused with the reason: correct it and run the command again. For a saved search result the
  reason is one word after `RAW_INVALID`:

  | after `RAW_INVALID` | what to do |
  |---|---|
  | `missing` | save the result to a new file and pass that path (the helper moves each file away once it has read it) |
  | `json` | the file is not one JSON value, or is over 1 MiB: save the returned objects again, unchanged |
  | `count` | put one element per FIND line, in the order of the FIND lines |
  | `shape` | save each object exactly as the search tool returned it |
  | `pages` | fetch every page of that search and put the pages in a list |
  | `error` | the tool returned an error: run that FIND again and save the new result |
  | `listing` | use the exact-name search of the FIND line, never a folder listing |
  | `entry` or `duplicate` | use the manual form of section 2 for this block |

- This happens at most 3 times for one save, one restore or one block. The fourth time is `STOP SLIP_LIMIT HANDBACK C`;
  while the helper checks a maintainer's kit (section 6), the fourth time prints your earlier STOP again instead.
- A copy with the size the search showed and other bytes than the helper's is a real second copy on Drive:
  `STOP FORK HANDBACK C`. The helper keeps the downloaded bytes for the maintainer.

## 4. What you are asked, and where

- **First `go` of a session:** `operator_model=MODEL platform=PLATFORM` (your own model id and platform).
- **In every session, before the helper searches the journal:** `approval=pending` or `approval=none`
  (section 3.1).
- **Times you attest** (`started_utc`, `ended_utc`) are VM clock readings: run `date -u +%Y-%m-%dT%H:%M:%SZ` on the VM
  just before you send the prompt, and again right after you see the conversation end, and answer the two readings
  exactly as printed. Never copy a time from the conversation list or from Drive.
- **Every conversation you open (S, G, V):** it gets the prompt file's text as its only message. Never send it a
  follow-up message, never answer its questions, never attach anything. When it has ended, write its final message
  exactly as it is (any characters, up to the kit's max_ai_output_bytes, larger: `STOP AI_OUTPUT_TOO_LARGE HANDBACK C`;
  never edit, shorten or summarize it) to
  `/tmp/cps/attest/final_message.txt`, then run `go` and answer. If the conversation shows no final message,
  create the file empty. Write the message with your file-write tool; if you use the shell, use a quoted heredoc whose
  delimiter line does not occur in the message. After a review continuation, write its new final message the same way.
- **Tools** (`tools=` in the first answer about each conversation): answer `tools=inventory` when you created the
  conversation exactly as section 3 says (Create Thread, same environment, no extra settings); its tools are then the
  platform's usual set, which the kit lists. If you created it in any other way, or you know that its tools differ,
  save the list of tools you know it had, one name per line, to a file under `/tmp/cps/attest/` and answer
  `tools=file:<the absolute path of that file>`. Never answer `none`: conversations on this platform always have tools.
  With `tools=inventory` the record holds the kit's list (by its sha256), the platform's usual set, not a list read
  from that conversation.
- **A generator (G) conversation ended:** whether it ended, its conversation id, its start and end times, the
  generator's platform, model and effort, whether you sent a single message, the six features (memory, custom
  instructions, web, connectors, file uploads, other agents: `yes` or `no` as the platform shows them for that
  conversation; with the usual tools of this platform `web` and `connectors` are `yes`), the tools and the transcript
  status (always `not_available` on this platform).
- **A scope reader (S) conversation ended:** `ended=yes`, its conversation id, `prompt_pasted=yes`, the tools.
- **A visual reviewer (V) conversation ended:** `ended=yes`, its conversation id and the tools; after a continuation
  only `ended=yes`.
- **After a reset or a clear, for a conversation that was open:** whether it ended (`ended=yes` once you stopped it or
  saw it end), what it wrote (`outcome=`), the transcript status (always `not_available` on this platform: it cannot
  export a transcript with the files written), and sometimes whether your conversation list shows no conversation at or
  after the time given (`list_shows_none=`) and the conversation's id. Decide `outcome=` only from what you can see:
  your conversation list with each conversation's `attachedAt` time, that conversation's recorded messages and turn
  status, and, only if the VM was not reset, the files in its output folder. A conversation is this role's only when
  its first message is the full text of the role's prompt file; conversations whose first message is anything else
  (for example your mailbox checks) do not count. The readback never shows what a conversation wrote through its
  tools.
  - `NO_CONVERSATION`: your list shows no conversation of this role with `attachedAt` at or after the `after=` time.
    Answer `list_shows_none=yes` with it.
  - `NOTHING_WRITTEN`: exactly one conversation is this role's, its recorded messages hold your prompt and nothing from
    it, and its turn status shows that it failed or was cancelled before it began to run.
  - `WRITTEN`: it replied (any message from it after your prompt), or its turn status says it completed, or (the VM
    was not reset) its output folder holds any file.
  - `UNSURE`: anything else: a turn that ran, whatever its status now (also one you stopped yourself), more than one
    conversation that could be this role's, a status you cannot read, or doubt. When in doubt, answer `UNSURE`.

  A conversation that may have written something is never opened again: the run fails safely instead. In
  qualification, `NOTHING_WRITTEN` lets the helper restart that conversation once, and the owner checks it before
  scoring; in an everyday job it never restarts.
- **An owner notice:** `notified=yes` after you told the owner.
- **Everyday, idle:** `case=CASE_ID`, only when a user asked for a job and its three input files are in
  `/tmp/cps/everyday_inputs/<case>/`.
- **Everyday delivery:** the two paths of the personal copy and its log, then `sent=yes` once you sent it.
- **Everyday, after a reset during a delivery:** `arrived=yes` or `arrived=no` (ask the user).
- **Everyday, after a failed job:** `asked=yes` once you told the user the job failed (a new job starts only at the
  user's request).

Give real values only. A value with a space, a quote, a brace, an angle bracket, `$`, a backslash or a non-ASCII
character is refused, and so is a key name, a pattern name or an example value from this page. The files you write for
the helper (the final message, a saved search result, a tool list) may hold any characters.

## 5. After a reset: what the helper does

The helper restores from the journal on Drive, never from your memory. It asks you `approval=` before it searches the
journal. Then it finds the newest journal entry by exact name (it asks you to FIND names one by one, waits, and FINDs some names twice),
downloads it, checks it, puts the job folders back, and asks you about any conversation that was open. It then saves a
RESTORE entry before anything else runs; in qualification and drills it then waits about a minute and FINDs the next
three names once more. A conversation that may have written something is never re-opened: the run fails safely
instead. Follow the blocks; never re-open a conversation on your own.

## 6. When the maintainer clears a stop

A `STOP <CODE> HANDBACK C` stays until the maintainer clears it. The maintainer's message gives you the bootstrap of
section 1 with its values filled in (`COMMIT`, `--hint` and a new `--kit` value). Run it exactly, as one command
through the elevated route, then `go`. The helper first finds and downloads the new kit (one FIND
block, one DOWNLOAD block) and checks that it names exactly your stop. If it does not, or if the kit cannot be found
or downloaded, it prints the same STOP again: tell the owner, and wait for the next message. If it does, it continues
from the journal as after a reset: answer its questions, `approval=` first. Do nothing else on the VM in between, and
never delete the helper's files. If the message asks the owner to remove a copy of a file from Drive, pass that on:
the owner deletes it for good in Drive (moves it to the trash, then deletes it from the trash) after the maintainer
has saved it; you never delete files on Drive.

## 7. How much work a run is

The helper's test harness counts the helper commands, Drive calls and saved search results on invented jobs; the
conversation steps are counted from this page (each is one tool call: `date -u`, creating the conversation, reading it
back, writing its final message to the file); the polls and checks are estimates until the stage times and
conversation lengths are measured on this VM. Poll a running helper command each time the command tool returns; check
a running conversation once every 5 minutes, with `sleep 300` between checks.

| item | helper commands | Drive calls | saved search results | conversation steps | polls and checks | tool calls in all |
|---|---|---|---|---|---|---|
| a normal run (prepare, generator, finish with p PNG parts, visual reviewer, freeze; p is 1 to 3) | 16 | 15 + 3p | 6 | about 10 | about 15 | about 65 to 71 |
| a scope reader in the run, or a review continuation | +6 | +6 | +2 | about +4 | about +3 | about +21 |
| a nonattempt | 2 | 3 | 1 | 0 | 0 | 6 |
| a restore after a reset, with your notes (the last `CPSV` line and the commit; `approval=` and the re-check) | 18 | 15 | 8 | 0 to 2 | 3 (2 waits) | about 45 |
| a restore with only the commit line in your notes | 39 | 46 | 14 | 0 to 2 | 3 (2 waits) | about 103 |
| a restore without your notes (step 0), measured on a journal of 6 entries | 24 | 23 | 13 | 0 to 2 | 3 (2 waits) | about 64 |
| a restore without your notes after about 400 journal entries (an estimate, not measured) | about 50 | about 45 | about 23 | 0 to 2 | 3 | about 120 |
| a maintainer clear (the kit check, then a restore) | +2 | +2 | +1 | 0 | 0 | a restore + 5 |
| one refused upload | +2 | +3 | +1 | 0 | 0 | about +6, plus the owner's time |

**Disk.** `/tmp` is a 4.9 GB file system held in memory. It holds the repository copy, everything under `/tmp/cps`
and the runner's temporary files in `/tmp/cps/tmp`, which the helper empties before every stage. A runner stage needs
2 GB free there; with less the helper stops with `STOP DISK_FULL HANDBACK C` before the runner starts. Never delete
the helper's files to make room.

A qualification (38 runs, 34 nonattempts, about 10 scope readers and continuations, about 10 restores, the start and
the end of the series) is about 3,600 tool calls: about 20 hours at 20 seconds per call, plus the conversations' own
time, the stages' running time and the owner's approval waits. This assumes that the owner has approved in advance
every upload the helper prints (new files into `CPS/qualification`, `CPS/drills`, `CPS/reports` and `CPS/setup`, and
for everyday jobs into the everyday records folder `Dots Folder/CPS_JOB_RECORDS` and the profile's `deliveries` folder);
otherwise expect refused uploads on most days.

## 8. Example values (refused as answers)

Every example value printed on this page. The maintainer copies this list into the kit config (`doc_samples`); the
helper refuses each of them as an answer.

<!-- doc_samples:begin -->
```
<40 hex>
<S>
<at>
<exactly one action>
<hex12|none>
<the 40-hex commit of your last CPSV-REPO line>
<seq6>
<hex12>
<abs>
<folder>
<name>
<id>
<size>
<UTC>
<kind>
<s>
<mode>
<STATE>
<case>
<user>
<utc14>
<CODE>
```
<!-- doc_samples:end -->
