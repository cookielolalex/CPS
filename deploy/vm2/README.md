# cps-vm-helper.v2: the Dot's procedure

This page is for the Dot, the operator of CPS jobs on the VM. The helper prints one block at a time. You do exactly
what the block says, then run what its last line says. You never decide anything about the journal yourself.

Specification: `docs/handoff/VM_HELPER_V2_SPEC.md` (sections 6, 8, 11 and 13 are summarised here).

## 1. After a reset, or in a new operator chat

After a reset `/home/agent` is empty. Restore the repository at the release commit, then start the session. Run
these lines exactly. `COMMIT` is the 40-hex commit of your last `CPSV-REPO` line. With a hint, also pass the `head`
and `kit` values of your last `CPSV` line.

<!-- bootstrap:begin -->
```
COMMIT=<the 40-hex commit of your last CPSV-REPO line>
[ -d ~/cps/repo/.git ] || git clone -q https://github.com/cookielolalex/CPS.git ~/cps/repo
git -C ~/cps/repo fetch -q origin "$COMMIT"; git -C ~/cps/repo checkout -q --detach "$COMMIT"
bash ~/cps/repo/deploy/vm2/session_start.sh --commit "$COMMIT" [--hint <seq6> --kit <hex12>]
```
<!-- bootstrap:end -->

- **Step 0, when your notes are gone.** Find `VM2_RELEASE.md` in the folder `CPS` by exact name and download it.
  Its one line `commit: <40 hex>` gives `COMMIT`. If the file is not there, stop and tell the owner
  `SESSION_NO_COMMIT` (case C). Never guess a commit.
- If the checkout fails after a partial clone, remove `~/cps/repo` (it holds no state) and run the three git lines
  once more. A second failure: stop and tell the owner `SESSION_GIT_ERROR` (case C).
- `session_start.sh` prints `CPSV-REPO commit=<40 hex>`. Keep that line in your notes together with the last `CPSV`
  line you saw.

## 2. The rule

Run `bash /home/agent/cps/vm.sh go`, then do the block it prints, exactly. Every block is:

```
CPSV series=<S> head=<seq6> kit=<hex12|none> at=<at> mode=<mode> state=<STATE>
UPLOAD <abs> TO <folder> AS <name>        (0..n, in order)
FIND <folder> NAME <name>                 (0..n)  or  LIST <folder> NEWEST <k>
DOWNLOAD <folder> ID <id> TO <abs>        (0..n)
DO: <exactly one action>
```

**Run every helper command in the foreground.** If the command tool gives you back a session before the command has
exited, poll that same session until the process exits, and start no other helper command meanwhile. A command may
run up to 1,200 s (a `go` that runs a stage first prints one line `CPSV-RUNNING kind=<kind> since=<UTC> max=<s>`).
The result of a command is its last block: from the last line that starts with `CPSV ` through the `DO:` line, which
is always the last line. If the process exited and no `DO:` line follows the last `CPSV ` line, run `go` once; if
that happens again, stop and tell the owner `NO_BLOCK` (case C).

A refusal adds one line `REFUSED <CODE>` right after the header; the rest of the block is the block you had before.
Keep the last `CPSV` line in your notes. Exit codes: 0 follow the block, 3 the block ends in `DO: STOP`, 4 refused
(nothing changed; correct the answer), 2 usage.

Do the UPLOAD lines first, in order, each **once** (never retry an upload yourself), then every FIND, whatever the
upload returned, then every DOWNLOAD. A FIND by NAME is an exact-name search in that folder: report every copy over
every result page, with its id and its size in bytes exactly as the search shows it, or `--none` when it returns
nothing. Save the raw search result to a file first and copy the ids from that file. When the platform **refused**
an upload (an approval review or any refusal message, not a timeout or an error), add `--refused` right after that
`--name N`. A LIST answer names every file the listing returned as `--file NAME:ID:SIZE`. A DOWNLOAD saves the file
from Drive at exactly the path given; never copy a local file there instead. Never edit, rename or delete a file on
Drive.

### 2.1 Two lines that are not blocks

- `CPSV-RUNNING kind=... since=... max=...` is printed first by a `go` that runs a stage (or by `session_start.sh`
  before the setup). It names no result. Keep polling the same command session until the process exits; the block
  follows it.
- A helper command that finds another one still running prints exactly three lines and exits 4, changing nothing:
  `CPSV-BUSY kind=... since=...`, `REFUSED HELPER_BUSY`, `DO: POLL`. Do what POLL says (section 3). Never start a
  second helper command while one runs.

### 2.2 Qualification and drill (series Q1, D1)

1. The maintainer gives you the commit and the kit (the `--hint 000000 --kit` value of the first session). Run the
   bootstrap of section 1, then `go`.
2. Follow every block. The helper runs the jobs in the order of the kit's job list: for each case reader A, then
   reader B, each through prepare, the generator conversation (and the scope reader for a large workbook), finish,
   the visual reviewer, freeze. A case without its source is frozen as a nonattempt without any conversation.
3. Every stage runs in the foreground of one `go` (up to 1,200 s; the finish stage takes minutes). Poll until it
   exits. Then the helper saves the result on Drive through its SAVE blocks (UPLOAD, FIND, `found`, DOWNLOAD,
   `go`); nothing that depends on a result is shown before it is saved.
4. When the owner must be told something (a stopped run, a finished series), the block is `NOTIFY_OWNER`.
5. `STOP FINAL HANDBACK B` ends the series: tell the owner that qualification generation is complete.

### 2.3 Everyday jobs (series E1)

1. With no job running the block is `STOP IDLE` or the idle question `case=CASE_ID`. When a user asks for a job,
   put the user's three files (`JOB.json`, `JOB_TITLE.json` and the source workbook it names) in
   `/home/agent/cps/everyday_inputs/` under a folder named by the case id, then answer with that case id.
2. Follow the blocks through prepare, the generator, finish and the visual reviewer, exactly as in qualification.
3. Delivery: `DELIVER ... to=copy` (make the personal copy and its log, answer the two paths), then
   `DELIVER ... to=user` (send it, answer `sent=yes`). After a reset during a delivery you are asked whether the copy
   reached the user (`arrived=`); ask the user, never send a second copy on your own.
4. A failed job is never retried on your own: the block asks you to tell the user (`asked=yes`); a new job starts only
   at the user's request.

## 3. The actions (the `DO:` line)

| action | you do | then |
|---|---|---|
| `RUN bash /home/agent/cps/vm.sh go` | run it | follow the new block |
| `ATTEST ... found --at A --name N [--refused] (--file ID:SIZE ... \| --none) ...` | do the block's UPLOAD/FIND lines, then run `found` with one `--file` per copy each FIND returned, or `--none` | follow the output |
| `ATTEST after=T bash ... answer ...` | as below; `list_shows_none=yes` means your conversation list shows **no** conversation with `attachedAt` at or after T, and `conversation=` is the id of the conversation of that role with `attachedAt` at or after T | follow the output |
| `POLL` | another helper command still runs: go back to its session and poll it until it exits, then follow its block. If you no longer have that session, `WAIT seconds=60`, then run `go` | follow that block |
| `ATTEST ... answer --at A k1=PATTERN1 ...` | run `answer` with a real value for each key, matching the pattern named | follow the output |
| `OPEN_CONVERSATION role=R prompt=P folder=F then=when_ended` | open a new conversation and give it the full text of file P as its only message. Roles S and G may use only folder F. Role V may open only the PNG files the prompt lists (under F) and may write only `F/visual_review/VISUAL_REVIEW.json` | when it has ended: run `go` |
| `OPEN_CONVERSATION ... then=now` | the same | as soon as the prompt is sent: run `go` (it asks for the conversation and the time you opened it) |
| `AWAIT_CONVERSATION role=R conversation=C` | wait until that conversation has ended | run `go` |
| `CONTINUE_CONVERSATION role=V conversation=C message=M` | send the text of file M in conversation C | when it has ended: run `go` |
| `END_CONVERSATION role=R after=UTC [conversation=C]` | stop the CPS conversation of that role opened after UTC, if it is still running | run `go` |
| `EXPORT_TRANSCRIPT role=R to=P [conversation=C] [after=UTC]` | export that conversation's transcript to P; if your platform cannot, do nothing | run `go` |
| `NOTIFY_OWNER file=P ATTEST ... notified=YES` | tell the owner the content of P | run the answer |
| `ASK_USER file=P ATTEST ... k=PATTERN` | ask the user the question in P | run the answer with the user's reply |
| `DELIVER file=P to=copy ATTEST ... copy=COPYPATH log=COPYPATH` | everyday: make the user's personal copy of P with that user's preferences, as `PERSONAL_COPY.xlsx` with its `PERSONALIZATION_LOG.json` in `~/cps-deliveries/<case>/<user>/<utc14>/` | run the answer with the two paths |
| `DELIVER file=P to=user ATTEST ... sent=YES` | everyday: send P to the requesting user, under the standard file name from the `JOB_TITLE.json` you wrote | run the answer |
| `WAIT seconds=N` | wait N seconds | run `go` |
| `STOP UPLOAD_REFUSED HANDBACK A` | tell the owner the code, the file name and your last `CPSV` line, and ask the owner to approve the refused upload in the platform | when the owner says it is approved (or to continue): run `go` |
| `STOP <CODE> HANDBACK C` | stop; upload nothing more; tell the owner the code and your last `CPSV` line | nothing |
| `STOP <CODE> HANDBACK B` | stop; tell the owner that qualification generation is complete | nothing |
| `STOP IDLE` | stop | nothing |

Handback letters: **A** the owner must approve something in the platform, then you run `go` and the series goes on;
**B** the series is complete; **C** stop and wait for the maintainer (nothing more is uploaded). `STOP IDLE` and
`STOP ... HANDBACK A` are the only stops after which you run the helper again without new instructions.

### 3.1 When the platform refuses an upload

The platform's automatic approval review sometimes refuses an upload, and a timed-out upload may still appear later.

1. Do every UPLOAD line once. Whatever an upload returned (success, timeout, error or refusal), do every FIND line of
   the block and report what the search shows.
2. Only for an upload the platform **refused**, add `--refused` after its `--name N` in `found`. Never use
   `--refused` for a timeout or an error, and never for a file the block did not ask you to upload (that is refused
   with `FOUND_SYNTAX`).
3. If the refused file is not found, the helper prints `DO: STOP UPLOAD_REFUSED HANDBACK A`. Tell the owner the code,
   the file name and your last `CPSV` line, and ask the owner to approve the upload in the platform. Do not upload it
   again yourself. When the owner says it is approved (or to continue), run `go`.
4. The next block FINDs the file first, never uploads at once (the approved upload may have landed). The helper
   uploads one file at most three times; after the third, it stops with `UPLOAD_FAILED HANDBACK C`.
5. A copy that appears late is a second copy with the same bytes; the helper checks it (it may ask you to DOWNLOAD
   it) and nothing else changes.
6. A DOWNLOAD the platform refuses: ask the owner to approve it, then download again and run `go`. Running `go`
   without the file gives `REFUSED DOWNLOAD_MISSING` and the same block again.

## 4. What you are asked, and where

- **First `go` of a session:** `operator_model=MODEL platform=PLATFORM` (your own model id and platform).
- **Times you attest** (`started_utc`, `ended_utc`, `opened_utc`) are VM clock readings: run
  `date -u +%Y-%m-%dT%H:%M:%SZ` on the VM just before you send the prompt, and again right after you see the
  conversation end. Never copy a time from the conversation list or from Drive.
- **A generator (G) conversation ended:** whether it ended, its conversation id, its start and end times (seconds,
  UTC; the start rounded up, the end rounded down), the generator's platform, model and effort, whether you sent a
  single message, the six features (memory, custom instructions, web, connectors, file uploads, other agents: `yes` or
  `no`), the tools (`none` or a comma list) and the transcript status (`exported` or `not_available`). Before you
  answer, write the generator's final message, verbatim, to `/home/agent/cps/attest/final_message.txt`.
- **A scope reader (S) conversation ended:** `ended=yes`, its conversation id, `prompt_pasted=yes`.
- **A visual reviewer (V) conversation ended:** `ended=yes` and its conversation id; after a continuation only
  `ended=yes`.
- **After `then=now`:** the conversation id and the time you opened it.
- **After a reset, for a conversation that was open:** whether it ended, what it wrote (`NOTHING_WRITTEN`, `WRITTEN`,
  `UNSURE` or `NO_CONVERSATION`), the transcript status, and sometimes whether your conversation list shows no
  conversation after the time given, and the conversation id.
- **An owner notice:** `notified=yes` after you told the owner.
- **Everyday, idle:** `case=CASE_ID`, only when a user asked for a job and its three input files are in
  `/home/agent/cps/everyday_inputs/<case>/`.
- **Everyday delivery:** the two paths of the personal copy and its log, then `sent=yes` once you sent it.
- **Everyday, after a reset during a delivery:** `arrived=yes` or `arrived=no` (ask the user).
- **Everyday, after a failed job:** `asked=yes` once you told the user the job failed (a new job starts only at the
  user's request).

Give real values only. A value with a space, a quote, a brace, an angle bracket, `$`, a backslash or a non-ASCII
character is refused, and so is a key name, a pattern name or an example value from this page.

## 5. After a reset: what the helper does

The helper restores from the journal on Drive, never from your memory. It finds the newest journal entry by exact
name (it asks you to FIND names one by one, waits, and FINDs some names twice), downloads it, checks it, puts the job
folders back, and asks you about any conversation that was open. It then saves a RESTORE entry before anything else
runs. A conversation that may have written something is never re-opened: the run fails safely instead. Follow the
blocks; never re-open a conversation on your own.

## 6. Example values (refused as answers)

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
<k>
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
