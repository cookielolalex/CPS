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
FIND <folder> NAME <name>                 (0..n)  or  FIND <folder> PREFIX <prefix>  or  LIST <folder> PREFIX <prefix> NEWEST <k>
DOWNLOAD <folder> ID <id> TO <abs>        (0..n)
DO: <exactly one action>
```

A refusal adds one line `REFUSED <CODE>` right after the header; the rest of the block is the block you had before.
Keep the last `CPSV` line in your notes. Exit codes: 0 follow the block, 3 the block ends in `DO: STOP`, 4 refused
(nothing changed; correct the answer), 2 usage.

Do the UPLOAD lines first, in order, then every FIND, then every DOWNLOAD. A FIND by NAME is an exact-name search in
that folder. Report every copy it returns, or `--none` when it returns nothing. Never edit, rename or delete a file
on Drive.

## 3. The actions (the `DO:` line)

| action | you do | then |
|---|---|---|
| `RUN bash /home/agent/cps/vm.sh go` | run it | follow the new block |
| `ATTEST ... found --at A --name N (--file ID:MD5:SIZE ... \| --none) ...` | do the block's UPLOAD/FIND lines, then run `found` with one `--file` per copy each FIND returned, or `--none` | follow the output |
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
| `STOP <CODE> HANDBACK C` | stop; upload nothing more; tell the owner the code and your last `CPSV` line | nothing |
| `STOP <CODE> HANDBACK B` | stop; tell the owner that qualification generation is complete | nothing |
| `STOP IDLE` | stop | nothing |

## 4. What you are asked, and where

- **First `go` of a session:** `operator_model=MODEL platform=PLATFORM` (your own model id and platform).
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
<the 40-hex commit of your last CPSV-REPO line>
<seq6>
<hex12>
<abs>
<folder>
<name>
<prefix>
<id>
<mode>
<STATE>
<case>
<user>
<utc14>
<CODE>
```
<!-- doc_samples:end -->
