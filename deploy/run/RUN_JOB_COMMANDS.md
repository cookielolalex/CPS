# Running a CPS job with `cps_job.py`

This is the command sheet for the operator (the Dot). `05_RUNBOOK_CPS_JOB.md` says what each stage does and why; this sheet says exactly what to type, what to open in each new conversation, and what to do at each `NEXT:`. Every command runs on your VM.

`deploy/run/cps_job.py` runs every CPS tool for you, in order, with the pinned versions, and keeps one record per job (`RUN_RECORD.json`). It never prints cell text, job inputs or the job title: only hashes, counts, codes and the paths you need. Tool output goes to the job's `logs/` folder.

## Before the first job

1. `cps_runtime/RELEASE.json` must say `"status": "RELEASED_FOR_USE"` for real jobs, or `"RELEASED_FOR_QUALIFICATION"` for qualification jobs. The runner refuses anything else.
2. The repository clone (`repository.root`) must be a git checkout at exactly `repository.commit`, with no change to any tracked file. Run the runner from that clone (`$CPS/deploy/run/cps_job.py`). The runner refuses a release without a commit (`RELEASE_COMMIT_REQUIRED`), a folder git cannot verify (`REPOSITORY_NOT_VERIFIABLE`), another commit (`REPOSITORY_COMMIT_MISMATCH`), a changed tracked file (`REPOSITORY_DIRTY`), a runner outside the clone (`RUNNER_NOT_IN_RELEASED_REPOSITORY`) and cached bytecode (`__pycache__`, `.pyc`) in the package, harness, source-prep, export or runner folders (`PYCACHE_PRESENT`; delete them).
3. The release pins every file the runner executes or fills in (`pinned_files_sha256`, or the qualification admission): `deploy/run/cps_job.py`, `deploy/run/VISUAL_REVIEW_PROMPT_TEMPLATE.md`, the seven harness files and the five source-prep files listed under "Release fields". Anything missing is refused (`RELEASE_PINS_INCOMPLETE`).
4. Load the toolchain in every new shell. On the no-root VM (`deploy/setup_vm_user.sh`, tested 2026-11-06), run `source ~/cps-tools/env.sh`: it puts the venv's `python3` (openpyxl 3.1.5, xlrd 2.0.2), node v22, `soffice`, `pdftoppm`, `pdfinfo` and `pdftotext` first on `PATH`, and sets `NODE_PATH` for Playwright (release `source_prep.node_path`). On a VM set up with `deploy/setup_vm.sh`, activate that setup's Python environment instead. The runner calls every tool with the same `python3`, and records its path and version.
5. `node` (v22) must be on `PATH`, with LibreOffice (`soffice`), `pdftoppm`, `pdfinfo` and `pdftotext`. The runner records the path and version of each at `prepare` and `finish`, and the names (never the values) of the environment variables the tools receive.
6. The builders read openpyxl and xlrd from a *deps bundle*: a folder whose `private/deps` is the venv's `site-packages`. The no-root setup makes it: `~/cps-tools/builder-deps` (`~/cps-tools/RELEASE_PATHS.json` records it). On another setup, make it once:
   ```bash
   mkdir -p ~/cps-deps/private
   ln -s "$(python3 -c 'import openpyxl, os; print(os.path.dirname(os.path.dirname(openpyxl.__file__)))')" ~/cps-deps/private/deps
   ```
   The release names it in `source_prep.deps_bundle`. `prepare` checks that the bundle's openpyxl is 3.1.5.

Set these once per shell. No path may contain spaces. `$JOBS` and every private job file must lie outside the repository clone (`JOBS_ROOT_IN_REPOSITORY`, `JOB_INPUT_IN_REPOSITORY`).

```bash
CPS=~/cps                          # the repository clone at the release commit
RT=/abs/path/cps_runtime           # holds RELEASE.json and tables/
JOBS=/abs/path/jobs                # one folder per job is created here (outside $CPS)
R="python3 -I -B $CPS/deploy/run/cps_job.py"
ME="<your model name as your platform reports it>"
```

## Rules for every command

- **One command at a time per job.** Every subcommand holds a lock on the job folder itself, and every tool it starts holds it too, so the folder stays locked until the last tool has ended, even if the runner was killed. A second command on the same job is refused with `REFUSED: JOB_BUSY`, and nothing is recorded. `finish` runs for minutes (saved QA and two LibreOffice renders). Never interrupt it, never re-issue it, and never start another command on that job while it runs. If your shell tool times out, wait and check `RUN_RECORD.json`; do not run it again.
- **An interrupted stage is final.** If a command is killed after it began consuming (for example `finish` after the response was frozen), the next command on that job records the stage as `INTERRUPTED` (`NEXT: STOP_INTERRUPTED`), and the stage never runs again in that folder. Tell the owner.
- **Keep each printed `run_record_sha256` outside the VM.** Every command prints one JSON line with `run_record_sha256`. Send it to the owner (or keep it in your notes outside the VM) after each command. The runner verifies the record's hash chain on every command (`RUN_RECORD_CHAIN_BROKEN`), but a record cut back to an earlier entry is still a valid chain: only the hashes kept outside the VM show it. In qualification the ledger keeps them too.
- **Never move or rename a job folder, a jobs root or the ledger.** The record and the qualification ledger name each folder by its path: a moved qualification folder is refused (`QUALIFICATION_JOB_NOT_IN_LEDGER`), `verify-frozen` fails on it, and a missing ledger is refused (`QUALIFICATION_LEDGER_MISSING`).
- **`REFUSED: RUNNER_ERROR`** means an unexpected error before the stage began consuming (for example an unreadable file). Nothing was consumed, and the traceback is in `logs/`. Fix the cause or tell the owner, then run the same command again. `NEXT: STOP_RUNNER_ERROR` is the same error after the stage began consuming: a recorded stop.
- **Fixed file locations.** The scope reader writes `scope/reader/output/SCOPE_READER_RESPONSE.json`, the generator writes `run/<reader>/output/response.json`, you write `run/GENERATION_RECORD.json`, and the visual reviewer writes `qa/visual_review/VISUAL_REVIEW.json`. The runner refuses any other path.

## Job inputs (runbook §2)

Get these from the owner or operator; never infer them. Write two private files for each job, outside `$JOBS` and outside `$CPS`.

`JOB.json` (`cps.job-config.v2`; `research/guideline046_007/harness/README.md` lists every key):

```json
{
 "schema": "cps.job-config.v2",
 "case_id": "1141002",
 "customer_name": "<customer full name>",
 "project_name": "<project short name>",
 "company_name": "<the company name from cps_runtime/tables>",
 "glossary_path": "/abs/path/cps_runtime/tables/<glossary file named in RELEASE.json>",
 "source_path": "/abs/path/<the bound source: the 材料清單, else the contract>.xlsx",
 "source_kind": "材料清單",
 "carrier_path": "X:\\<the source's original Windows path>.xlsx"
}
```

A contract job (no 材料清單) has `"source_kind": "contract"` and also `"brand_table_path"`. A 材料清單 job never has `brand_table_path`. The glossary and brand table paths must be exactly the files `RELEASE.json` names under `tables`, with the listed sha256.

`JOB_TITLE.json` (`cps.job-title.v1`). The project folder title is a job input like the case id, but it is **not** a key of `JOB.json`: `make_job_config.py` refuses unknown keys, and the title never enters the packet.

```json
{"schema": "cps.job-title.v1", "case_id": "1141002", "job_title": "1141002<the project folder title as given>"}
```

The title starts with exactly the case id in ASCII digits (not fullwidth digits; the next character is not another digit), and holds no invisible format character such as U+200B or U+202E and no line or paragraph separator such as U+2028 (`JOB_TITLE_INVALID`, `JOB_TITLE_FORMAT_CHARACTER`). The writer derives the delivered file name from it.

## Stage 1: prepare

```bash
$R prepare --release $RT/RELEASE.json --job /abs/JOB.json --job-title-file /abs/JOB_TITLE.json \
   --jobs-root $JOBS --operator-model "$ME"
```

It does the following:
- checks the release (status, repository commit and clean tree, the pins of every executed file, package manifest and every package file, the export tools against `ADMISSION_WRITER_V27.json`, the checker node, the writer folder, openpyxl, the deps bundle);
- checks the job inputs and the company tables;
- records the release path you gave (later stages re-read it: see Stage 4 and Stage 6);
- creates `$JOBS/<case id>/` and copies the release, `JOB.json`, `JOB_TITLE.json` and the source into `input/` (read-only);
- runs `make_job_config.py` (and checks that its config names the pinned source and tables), the inventory builder (`.xlsx` or `.xls`), `render_views.py` and the route's `check-inventory`;
- runs `scope_tool.py`. More than 2,500 literal or cached-formula content cells starts the scope stage (R59). Otherwise it runs `prepare_run.py`, writes the generator prompt and pins every in-job product in `PACKET_PINS.json`;
- makes the packet, the scope tool's files and the generator's input folders read-only.

The last line is one of:

| Last line | What to do |
|---|---|
| `NEXT: GENERATE prompt=<P> folder=<F>` | Stage 3 (generation). |
| `NEXT: SCOPE_READER prompt=<P> folder=<F>` | Stage 2 (scope reader). |
| `NEXT: OWNER_DECISION` | The scope tool holds the case (zero or several bill sheets, or similar). Stop and tell the owner. Never choose yourself. |
| `NEXT: STOP_<reason>` | Stop and tell the owner the reason code. |
| `REFUSED: <code>` | Nothing was created. Fix the cause (wrong path, wrong table, unreleased node, a dirty clone, a job input `make_job_config.py` refuses: `JOB_CONFIG_REFUSED`) and run the same command again. If the cause is not yours, tell the owner. |

## Stage 2: scope reader (only after `NEXT: SCOPE_READER`)

1. Open a **new conversation**. Give it the full text of the prompt file `<P>` (`scope/SCOPE_READER_PROMPT.md`). It may read only `<F>/input/`, which holds `SCOPE_DIGEST.json` and `SCOPE_RULES_EXCERPT.md`. It writes `<F>/output/SCOPE_READER_RESPONSE.json`, and nothing else.
2. Then run:
   ```bash
   $R scope-finish --job-dir $JOBS/<case id> --reader-response $JOBS/<case id>/scope/reader/output/SCOPE_READER_RESPONSE.json \
      --reader-prompt-sha256 "$(sha256sum $JOBS/<case id>/scope/SCOPE_READER_PROMPT.md | cut -d' ' -f1)" \
      --reader-conversation-id "<the reader conversation's id or link>" --operator-model "$ME"
   ```
   `--reader-prompt-sha256` is the sha256 of the prompt file you pasted; it must equal the one `prepare` wrote (`READER_PROMPT_SHA256_MISMATCH`, nothing consumed). It is required for qualification jobs (`READER_PROMPT_SHA256_REQUIRED`). It freezes the reader's file before anything reads it. It then re-checks the scope tool's files, the full packet, the reader prompt and the reader's folder against the `prepare` pins, and runs `scope_agree.py`, `make_scoped_inventory.py` and its `--verify` (both must report the route's own check of the scoped inventory as PASS), `check-inventory` on the scoped packet (`scope: applied`), and `prepare_run.py`. `--reader-conversation-id` is optional; it is your attestation, recorded as given (never a template placeholder such as `<...>`).

| Last line | What to do |
|---|---|
| `NEXT: GENERATE prompt=<P> folder=<F>` | Stage 3. |
| `NEXT: OWNER_DECISION` | The tool and the reader disagree (`scope/decision/SCOPE_HOLD.json`). Tell the owner. Never pick a side, never ask a second reader. |
| `NEXT: STOP_<reason>` | Tell the owner. For example, `STOP_SCOPE_READER_RESPONSE_REFUSED` means the reader's JSON was malformed, `STOP_SCOPE_DECISION_NOT_ADMISSIBLE` means it was not a fresh-context reader, and `STOP_SCOPE_INPUTS_CHANGED` or `STOP_SCOPE_READER_INPUT_CHANGED` means a file pinned at `prepare` changed (`CHANGED_SCOPE_READER_PROMPT`: the reader prompt). |

## Stage 3: generation (after `NEXT: GENERATE`)

Open a **new conversation**. Give it the full text of the prompt file `<P>` (`run/GENERATOR_PROMPT.md`) as its only message. It may see only the folder `<F>` (`run/A/`): `input/package/`, `input/packet/` and `output/`. It writes `<F>/output/response.json`, and scratch files only under `<F>/output/scratch/`.

Never edit the response. Never give the conversation anything else: no other job, no interview material, no historical 未填, no earlier responses, no follow-up message, no attachment.

Then write the **generation record** `$JOBS/<case id>/run/GENERATION_RECORD.json` (`cps.generation-record.v1`). It is required for qualification jobs and recorded when given for real jobs. `deploy/run/GENERATION_RECORD.example.json` shows every field with invented values:
- `case_id`, `reader`;
- `platform`, `model` (the observed model id as your platform shows it), `effort` (the reasoning setting, or `unknown`), `conversation_id` (the id or share link, so an account export can be matched later);
- `started_utc`, `ended_utc` of the conversation (ISO 8601 with `Z`, to the second), between the end of the stage that printed `NEXT: GENERATE` and the start of `finish`. If your platform shows minutes only, round the start up and the end down, so both lie inside that window;
- `prompt_sha256`: `sha256sum $JOBS/<case id>/run/GENERATOR_PROMPT.md`, the text you pasted;
- `single_user_message`: `true` when the prompt was the only user message (no follow-up, no attachment);
- `features`: `memory`, `custom_instructions`, `web`, `connectors`, `file_uploads`, `other_agents`, each `true` or `false`; `tools_enabled`: the tools the conversation had;
- `final_message`: the generator's final message, verbatim;
- `transcript_status`: `exported` with `transcript_sha256` (the sha256 of the exported transcript file, which you then give to `finish --transcript`), or `not_available` with `transcript_not_available_reason`.

No field may be a template placeholder such as `<...>` (`GENERATION_RECORD_INVALID`).

State `transcript_status` exactly as it is. **Owner decision O40 (2026-11-06):** the runner freezes the generation record for each qualification run; the transcript is added if the platform can export one, otherwise it is marked `not_available`. Qualification accepts either, and the report states how many runs had transcripts. So:
- `exported` in a qualification job needs `finish --transcript <the exported file>`: the runner freezes it as `response/GENERATOR_TRANSCRIPT.<ext>` and checks its sha256 (`TRANSCRIPT_REQUIRED` without it, nothing consumed);
- `isolation_evidence` follows the frozen file: `transcript_exported` only when a transcript was frozen, otherwise `attested_not_audited` (an everyday job's `exported` without `--transcript` is recorded as `transcript_claimed_but_not_frozen`);
- every record states `qualification_transcript_rule: "O40 2026-11-06: exported or not_available, both accepted; count reported"`, and the ledger's freeze entry carries each run's transcript status and whether its file was frozen, for the count.

## Stage 4: finish

```bash
$R finish --job-dir $JOBS/<case id> --response $JOBS/<case id>/run/A/output/response.json \
   --generator-model "<the generating conversation's model>" \
   --generation-record $JOBS/<case id>/run/GENERATION_RECORD.json --operator-model "$ME"
```

With `transcript_status: exported`, add `--transcript /abs/<the exported transcript file>` (required for qualification jobs).

`finish` first re-checks the export environment, the release you gave at `prepare` (it must still say the same status and be the same file, or name this job's `release_version` in `accepts_jobs_from_release_versions`), and the generation record. It then freezes the generation record and the response: read-only copies in `response/`, with their sha256 recorded, before anything reads them. Then:
1. The generation folder must hold exactly its pinned inputs (no added, changed or linked file; the package copy equal to its manifest), and `output/` only `response.json` and `scratch/`; every file of `PACKET_PINS.json` must be unchanged.
2. Route `check`. If it fails, the failure is the job's outcome (`NEXT: STOP_ROUTE_CHECK_FAILED`). It is never retried.
3. `convert`.
4. The writer, in the mode the convert receipt's `export_mode_required` names (condition 6), titled from `input/JOB_TITLE.json`. `--job-title` is optional; if given, it must equal the file.
5. The duplicate-key check of `WRITER_RECEIPT.json` (condition 5), and the tool hashes (condition 3).
6. Saved QA from a clean environment with the pinned checker node (conditions 1, 2, 4, 7).
7. Visual QA of `<name>(未填).xlsx` and of `INTERNAL_QA_WORKBOOK.xlsx` into separate folders (condition 8).
8. The page selection, `qa/QA_EVIDENCE.json`, and the visual-review prompt.

| Last line | What to do |
|---|---|
| `NEXT: VISUAL_REVIEW prompt=<P> folder=<F>` | Stage 5. |
| `NEXT: STOP_<reason>` | Record and tell the owner. Never retry, never patch by hand. Typical reasons: `STOP_RUN_INPUTS_CHANGED`, `STOP_RUN_OUTPUT_UNEXPECTED`, `STOP_PACKET_CHANGED`, `STOP_ROUTE_CHECK_FAILED`, `STOP_NOT_CARRIED`, `STOP_WRITER_REFUSED`, `STOP_SAVED_QA_NOT_EVIDENCE_GRADE` (`qa/QA_EVIDENCE.json` lists the failed conditions), `STOP_VISUAL_QA_RENDER_FAILED`, `STOP_INTERRUPTED`. Any refusal after the response was frozen is also a stop (`NEXT: STOP_<code>`, recorded). |
| `REFUSED: <code>` | Nothing was consumed: the response was not frozen. For example, `CHECKER_NODE_NOT_ADMITTED` (your node binary changed), `RELEASE_NOT_LIVE` (the release was withdrawn or replaced), `JOB_TITLE_MISMATCH`, `GENERATION_RECORD_*`, `TRANSCRIPT_REQUIRED` or `JOB_BUSY`. Fix the cause, or tell the owner, and run the same command again. `STAGE_ALREADY_COMPLETED` means finish already ran: never run it again. `STAGE_OUTPUT_EXISTS` means a frozen output exists without its record entry: tell the owner. |

## Stage 5: visual review (after `NEXT: VISUAL_REVIEW`)

The visual review is done by a **fresh conversation that you start**. The runner cannot see that conversation; it checks only what is recorded. By recording the review you attest that it ran in a new conversation that saw nothing of this job but the prompt and the listed PNGs.

1. Open a **new conversation**. Give it the full text of `<P>` (`qa/VISUAL_REVIEW_PROMPT.md`). It may open only the PNG files the prompt lists, and it judges PNGs only. It writes `qa/visual_review/VISUAL_REVIEW.json` with `reviewer.kind` `fresh_context_visual_reviewer`, its model and effort, and a result for every page, item and listed cut cell.
2. Then run:
   ```bash
   $R visual-record --job-dir $JOBS/<case id> --review $JOBS/<case id>/qa/visual_review/VISUAL_REVIEW.json \
      --reviewer-conversation-id "<the review conversation's id or link>" --operator-model "$ME"
   ```
   `--reviewer-conversation-id` is your attestation of the conversation; it is required unless the review itself states `reviewer.conversation_id` (both, when given, must be equal). The runner checks that the review covers every selected page and every checklist item, with `n/a` only where an item does not apply; that every cell listed under `possibly_cut_cells` has a result and item 8 is not `n/a` on every delivered page when such cells exist; that each visual manifest's `saved_xlsx.sha256` equals `SAVED_QA.json`; and that every page image still has the sha256 its manifest lists. It records PASS or FAIL.

**Clipped cells and page count.** The visual-QA manifest names no page for a `possibly_clipped_cells` cell, so when one lies on the review sheet `來源與審查` (or the list is capped), the runner lists every page of that sheet for review. That is the safe reading of condition 8 and is kept as it is. Naming the page of each clipped cell is a change to `research/export/visual_qa.py` (a new version, reviewed and admitted), not to the runner.

| Last line | What to do |
|---|---|
| `NEXT: DELIVER_CHECK` | Stage 6 (real jobs). |
| `NEXT: FREEZE` | Qualification: run `freeze`. |
| `NEXT: STOP_VISUAL_REVIEW_FAILED` | Any failed item or cut cell fails visual QA. Tell the owner, and do not deliver. |
| `NEXT: STOP_VISUAL_PAGES_CHANGED` | A page image differs from its manifest (tampering). Tell the owner. |
| `REFUSED: REVIEW_INCOMPLETE` | The review omitted a page, item or cut cell and recorded no failure. The attempt is kept in `qa/visual_review_attempts/<seq>.json`. Have the reviewer complete it, then run the command again. A review with any `fail` is never refused: it is recorded as FAIL. |
| `REFUSED: REVIEW_NOT_FRESH_CONTEXT` | `reviewer.kind` is not `fresh_context_visual_reviewer`, or the model or effort is blank. A review by you or by any other conversation is never recorded as a PASS. |
| `REFUSED: REVIEWER_CONVERSATION_ID_REQUIRED` | Give `--reviewer-conversation-id`. |
| `REFUSED: REVIEW_PATH` | The review is not `qa/visual_review/VISUAL_REVIEW.json`. |

## Stage 6: deliver (real jobs only, `RELEASED_FOR_USE`)

Just before sending, run:

```bash
$R deliver-check --job-dir $JOBS/<case id> --operator-model "$ME"
```

This is condition 9. The release you gave at `prepare` is read again: it must say `RELEASED_FOR_USE` and be the same file, or name this job's `release_version` in `accepts_jobs_from_release_versions` (else `REFUSED: RELEASE_NOT_LIVE`, not recorded as a result; ask the owner). The delivered file must be a regular file: not a symbolic link, and with one hard link. Its name must be the one the writer derives from the title, and not the internal workbook's. Its sha256 must equal `deliverable_xlsx.sha256` in `qa/SAVED_QA.json`. Saved QA must be evidence grade, and the visual review must have passed. The result is recorded in `qa/DELIVERY_CHECK.json`.

- `NEXT: DELIVER file=<path>`: send exactly that file and nothing else, as the runbook (§9) says. Never send `INTERNAL_QA_WORKBOOK.xlsx` or any QA file.
- `NEXT: STOP_DELIVERY_CHECK_FAILED`: do not send anything. Tell the owner.

`deliver-check` runs once per job. If you are not sending right away, run it when you are.

## Qualification mode (`06_QUALIFICATION_PROTOCOL.md`)

Qualification jobs differ in the following ways.

**The release.** `RELEASE.json` says `RELEASED_FOR_QUALIFICATION` and has a `qualification` block:
- `admissions`: the admitted qualification admission files, each `{"path": "/abs/ADMISSION.json", "sha256": "..."}` (non-empty); `--admission` must be one of these paths, with these bytes;
- `ledger`: the absolute path of the qualification ledger, outside every jobs root and outside `$CPS` (for example `$Q/LEDGER.jsonl`; its folder must exist);
- `jobs_file`: the absolute path of `qualification/JOBS.json`;
- `accepted_transcript_status`: optional; when given it must list exactly `exported` and `not_available` (O40: qualification accepts both). Any other list is refused (`QUALIFICATION_RELEASE_FIELDS`).

**The admission** is frozen once, with `research/guideline046_007/harness/freeze_admission.py`, and listed in the release, **before the first qualification `prepare` of the ledger**. `prepare` refuses an admission the release does not list by path and sha256 (`ADMISSION_NOT_RELEASED`) and one frozen after the ledger's first entry (`ADMISSION_FROZEN_AFTER_FIRST_PREPARE`). The admission pins, by sha256:
- the package manifest and the route `package/tools/cps046b_route.py`;
- per job: `JOB.json`, the source, the glossary (and the brand table on a contract job), and the title file under the label `job_title_<case id>`;
- under labels equal to their repository-relative paths: `deploy/run/cps_job.py`, `deploy/run/VISUAL_REVIEW_PROMPT_TEMPLATE.md`, the seven harness files, the five source-prep files, `research/export/ADMISSION_WRITER_V27.json`, the evaluator `research/evaluation/compare_target050.py` and the aggregator `research/evaluation/aggregate_qualification050.py`;
- `JOBS.json` under the label `JOBS.json`.

Each pin is checked against the bytes the runner uses (`ADMISSION_MISSING_PINS` lists what is missing or different).
```bash
# ADMISSION_CONFIG.json: {"files": {"package_manifest": "...", "route": "...",
#   "job_1141002": "/abs/JOB.json", "source_1141002": "/abs/source.xlsx", "glossary": "...", "job_title_1141002": "/abs/JOB_TITLE.json",
#   "deploy/run/cps_job.py": "$CPS/deploy/run/cps_job.py", ..., "JOBS.json": "/abs/qualification/JOBS.json"}, "plan": {...}}
python3 -I -B $CPS/research/guideline046_007/harness/freeze_admission.py --config /abs/ADMISSION_CONFIG.json --out /abs/ADMISSION.json
```

**`JOBS.json`** (`cps.qualification-jobs.v1`; `deploy/run/JOBS.example.json`): `cases`, each `{"case_id", "order", "nonattempt": false|true[, "reason"]}`. Only listed cases that are not marked `nonattempt` can be prepared.

**The ledger** (`cps.qualification-ledger.v1`, one JSON object per line, each chained to the sha256 of every byte before it and carrying the sha256 of its own content) is written only by the runner. It records each `prepare` (case, reader, jobs root, folder, admission, release), every record entry with its `run_record_sha256`, the `PACKET_PINS.json` sha256, each freeze with the `FROZEN.json` sha256, and each nonattempt. Every command on a qualification job checks that the job's record is the one the ledger last recorded (`RUN_RECORD_NOT_IN_LEDGER`). Never edit the ledger; copy it outside the VM after each job.

**`prepare --qualification`** takes `--admission <ADMISSION.json> --reader A|B` and refuses:
- a case not in `JOBS.json`, or marked `nonattempt` there or in the ledger;
- a second run of the same case and reader (`QUALIFICATION_RUN_EXISTS` while the first is not frozen);
- run B before run A of the case is frozen (`QUALIFICATION_READER_A_NOT_FROZEN`);
- run B while run A ended in a technical interruption or stop whose one restart is unused (`QUALIFICATION_READER_A_RESTART_UNUSED`): restart run A first (rule 1: run A in full before run B).

**Run A and run B use separate job roots:** `--jobs-root $Q/A --reader A`, and later `--jobs-root $Q/B --reader B`.

**Restart (protocol rule 3).** A technical interruption before any scope reader or generator response is written may be restarted **once** per case and reader.

*The scope reader or generator conversation broke* (after `NEXT: SCOPE_READER` or `NEXT: GENERATE`, before it wrote its file: the platform failed, the conversation was lost, it ended without writing). Record it first, then freeze:
```bash
$R interrupt --job-dir $Q/A/<case id> --reason TECHNICAL_CONVERSATION_BROKE \
   --started-utc 2026-11-06T09:00:05Z --ended-utc 2026-11-06T09:12:40Z \
   --conversation-id "<the broken conversation's id or link, if it has one>" --operator-model "$ME"
$R freeze --job-dir $Q/A/<case id> --operator-model "$ME"
```
- `interrupt` is allowed only when the last completed stage printed `NEXT: GENERATE` or `NEXT: SCOPE_READER` and no scope reader or generator response is frozen (`INTERRUPT_NOT_ALLOWED` otherwise; never after `finish` or `scope-finish` froze a file). So on a large workbook, once `scope-finish` has frozen the reader's file, a broken generator conversation is not restartable: freeze the folder and tell the owner. It is for qualification jobs only (`INTERRUPT_QUALIFICATION_ONLY`).
- `--reason` is `TECHNICAL_<CODE>` in capitals (`TECHNICAL_CONVERSATION_BROKE`, `TECHNICAL_PLATFORM_ERROR`, ...). The times are the broken conversation's, to the second, between the end of the stage that printed `NEXT:` and now (`INTERRUPTION_TIMES`); round the start up and the end down. `--conversation-id` is your attestation, recorded as given.
- It records a completed `TECHNICAL_INTERRUPTION` (`NEXT: STOP_TECHNICAL_INTERRUPTION`, exit 3) with the conversation id, the times and a listing of the conversation's output folder, mirrored in the ledger. After it only `freeze` runs in that folder (`JOB_INTERRUPTED`).
- Use it only for a technical break, never because you dislike a result. If the conversation wrote its file, run `scope-finish` or `finish` as usual.

*A technical stop before any response* (`NEXT: STOP_<reason>` at `prepare`, such as `STOP_RENDER_VIEWS_FAILED` or `STOP_RUNNER_ERROR`, or `NEXT: STOP_INTERRUPTED` of a stage killed before it froze a response): freeze the folder as it is.

Then:
1. prepare again under a new jobs root (for example `$Q/A_restart1`);
2. tell the owner, naming both folders.

The new record's `restart_of` and the ledger name the earlier folder. The runner allows the restart only when the earlier run is frozen, froze no scope reader or generator response (no `freeze_response`, and its `FROZEN.json` lists neither `scope/SCOPE_READER_RESPONSE.json` nor anything in `response/`), and ended in the recorded interruption, an `INTERRUPTED` stage or a technical `STOP_` before any response. It refuses every other restart (`QUALIFICATION_RESTART_NOT_ALLOWED`: a response was frozen; the run ended in `OWNER_DECISION`; it was frozen at `NEXT: GENERATE` or `NEXT: SCOPE_READER` without `interrupt`, which makes it a failed run; or run B of the case has started) and a second one (`QUALIFICATION_RESTART_USED`).

**`PACKET_PINS.json`.** Before it prints `NEXT: GENERATE`, the runner pins every in-job product (builder config, full and scoped packets with their views, scope files, decision, receipt, frozen reader response, generator prompt and run pins) in a read-only `PACKET_PINS.json`, and writes its sha256 to the ledger. `finish` stops (`STOP_PACKET_CHANGED`) if any of them changed.

**`finish --qualification`** requires `--generator-model` (equal to the record's `model`) and `--generation-record` (Stage 3), and `--transcript` when the record says `exported` (O40). Without them it refuses, with nothing consumed.

**`scope-finish --qualification`** requires `--reader-prompt-sha256` (Stage 2).

**No per-user options** apply. The runner takes none, and the record says so.

**Freezing.** After `NEXT: FREEZE` (visual review passed) and after any `NEXT: STOP_<reason>` or `NEXT: OWNER_DECISION`, freeze the run:
```bash
$R freeze --job-dir $Q/A/<case id> --operator-model "$ME"
$R verify-frozen --job-dir $Q/A/<case id>
```
`freeze` appends the last record entry, writes the `FROZEN.json` sha256 to the ledger, then writes `FROZEN.json` (every file and folder with its sha256) and removes write permission from every file and every folder, the job folder last. After that every subcommand is refused (`JOB_FROZEN`, which also reports whether the folder still matches `FROZEN.json`). Never touch the folder again. If `freeze` prints `NEXT: STOP_FREEZE_INCOMPLETE`, run `freeze` again: it completes `FROZEN.json` with the same bytes.

`verify-frozen` recomputes every sha256 against `FROZEN.json`, the record chain and the ledger's freeze entry, and writes nothing (it opens the ledger read-only). It prints `NEXT: DONE` (exit 0) or `NEXT: STOP_FROZEN_FOLDER_CHANGED` (exit 3) with the counts of unlisted, changed and missing entries. Run it on every folder before you write `ALL_FROZEN.json`.

**No delivery.** `deliver-check` refuses qualification jobs.

**Nonattempts** (rule 6) are the cases `JOBS.json` marks `"nonattempt": true`. They are frozen at once, not run:
```bash
$R nonattempt --release $RT/RELEASE.json --admission /abs/ADMISSION.json --case <case id> --reader A \
   --jobs-root $Q/A --operator-model "$ME"
$R verify-frozen --job-dir $Q/A/<case id>
```
- It refuses a case `JOBS.json` does not list (`QUALIFICATION_CASE_NOT_IN_JOBS`) or does not mark as a nonattempt (`QUALIFICATION_CASE_NOT_NONATTEMPT`), and a case and reader that already have a run or a nonattempt. A refusal appends nothing and creates nothing.
- The reason is the one `JOBS.json` gives (protocol rule 6's `NONATTEMPT_SOURCE_UNAVAILABLE` when it gives none). `--reason` is optional; if given, it must equal it (`NONATTEMPT_REASON_MISMATCH`).
- It writes the nonattempt folder `<jobs root>/<case id>/`: `input/` (the release, the admission and `JOBS.json`), `RUN_RECORD.json` with `"status": "NONATTEMPT_SOURCE_UNAVAILABLE"` (the reason) and the `nonattempt` entry, and `FROZEN.json`. The folder is read-only, and the `FROZEN.json` sha256 is in the ledger. Without `--jobs-root` the folder is `<ledger folder>/nonattempts_<reader>/<case id>/`.
- List it in `ALL_FROZEN.json` like any run folder.

## Release fields the runner reads

`RELEASE.example.json` shows every field with invented values. Relative paths are taken from `repository.root`.

| Field | Used for |
|---|---|
| `schema` | must be `cps.release.v1` |
| `status` | `RELEASED_FOR_USE` (real jobs) or `RELEASED_FOR_QUALIFICATION` (with `--qualification`) |
| `release_version` | recorded; a later release may name it in `accepts_jobs_from_release_versions` |
| `accepts_jobs_from_release_versions` | optional: earlier release versions whose jobs may still finish and deliver under this release file |
| `repository.root` | the clone on this VM (default: the repository that holds `cps_job.py`); the runner must be its `deploy/run/cps_job.py` |
| `repository.commit` | required: must equal `git rev-parse HEAD`, with no change to any tracked file |
| `package.path`, `package.manifest_sha256` | the guideline package. The manifest hash, every listed file's hash and no unlisted file are checked. It must be `<harness.path>/../package`, the folder the harness tools load. |
| `harness.path` | `make_job_config.py`, `scope_tool.py`, `scope_agree.py`, `make_scoped_inventory.py`, `prepare_run.py`, `GENERATOR_PROMPT_TEMPLATE.md`, `SCOPE_READER_PROMPT_TEMPLATE.md` |
| `source_prep.path` | `build_inventory_xlsx_v2.py`, `build_inventory_v2.py`, `render_views.py`, `screenshot_views.cjs`, `auto_views.py` |
| `source_prep.deps_bundle` | folder holding `private/deps` (openpyxl 3.1.5, xlrd 2.0.2) for the builders' `--bundle` |
| `source_prep.node_path` | optional `NODE_PATH` that resolves `playwright` for `render_views.py` |
| `writer.admission`, `writer.admission_sha256` | `research/export/ADMISSION_WRITER_V27.json` and its pin. Its `files_sha256` is condition 3; its `writer_dir_sha256` is condition 4; its `checker_node` is used when the release has none. |
| `writer.writer_dir` | the writer folder (`deploy/writer_route/writer`) for the writer and saved QA |
| `checker_node.path`, `checker_node.sha256` | the checker's node binary (condition 2). Its sha256 must be listed in `admitted_checker_node_sha256`. |
| `admitted_checker_node_sha256` | the node binaries the maintainer admitted after a full self-test |
| `saved_qa_clean_path` | optional `PATH` of saved QA's clean environment (default `/usr/bin:/bin`) |
| `tables.glossary.{path,sha256}`, `tables.brand_table.{path,sha256}` | the only company tables a job may use |
| `tables.company_name_sha256` | optional: the sha256 of the UTF-8 company name a job must use |
| `qualification.admissions` | qualification: the admitted admission files, `[{path, sha256}]` (non-empty) |
| `qualification.ledger`, `qualification.jobs_file` | qualification: the ledger and `JOBS.json` (absolute paths) |
| `qualification.accepted_transcript_status` | qualification, optional: if given, exactly `exported` and `not_available` (O40) |
| `pinned_files_sha256` | map of repository-relative path to sha256, checked by every subcommand. It must cover `deploy/run/cps_job.py`, `deploy/run/VISUAL_REVIEW_PROMPT_TEMPLATE.md` and every harness and source-prep file above (in qualification the admission may cover them instead). |

## The job folder

`$JOBS/<case id>/`:

| Path | Contents |
|---|---|
| `input/` | `RELEASE.json`, `JOB.json`, `JOB_TITLE.json`, `source.<ext>` and, in qualification, `ADMISSION.json`. All are read-only copies; later stages use this release copy, and re-read the live release file for its status. |
| `packet/` | `BUILDER_CONFIG.json`; `full/` (`SOURCE_INVENTORY.json`, `view_*.png`); read-only after `prepare` |
| `scope/` | `tool/` (the scope proposal, and the digest when the stage applies; read-only); `reader/input/` (read-only), `reader/output/`; `SCOPE_READER_PROMPT.md`; `SCOPE_READER_RESPONSE.json` (frozen); `decision/`; `scoped_packet/` |
| `run/` | `A/` (or `B/`), the bounded generation folder from `prepare_run.py` (its `input/` read-only); `GENERATOR_PROMPT.md`; `GENERATION_RECORD.json` (yours) |
| `PACKET_PINS.json` | every in-job product pinned before `NEXT: GENERATE` (read-only) |
| `response/` | `GENERATION_RECORD.json`, `GENERATOR_TRANSCRIPT.<ext>` (when exported) and `response.json` (frozen), `ROUTE_CHECK.json` |
| `carrier/` | `convert/`: `carrier.json`, `ADAPTER_RECEIPT.json`, `CENSUS_LEDGER.json` |
| `export/` | `writer/`: `<name>(未填).xlsx` (the delivered workbook), `INTERNAL_QA_WORKBOOK.xlsx`, `EXPECTED_SAVED_VALUES.json`, `WRITER_RECEIPT.json` |
| `qa/` | `SAVED_QA.json`; `visual_deliverable/`, `visual_internal/`; `VISUAL_PAGES.json`; `QA_EVIDENCE.json`; `VISUAL_REVIEW_PROMPT.md`; `visual_review/`; `visual_review_attempts/` (refused reviews); `VISUAL_REVIEW.json` (frozen); `VISUAL_RECORD.json`; `DELIVERY_CHECK.json` |
| `logs/` | every tool's stdout and stderr, and the traceback of a `RUNNER_ERROR` (private; never paste them anywhere) |
| `RUN_RECORD.json` | the record (below) |
| `.STAGE_IN_PROGRESS.json` | the marker of a stage that is consuming (never touch it). The job lock is a lock on the folder itself, not a file. |
| `FROZEN.json` | after `freeze` |

`RUN_RECORD.json` (`cps.job-run-record.v2`) holds:
- the case id;
- the reader, and whether the job is a qualification job;
- the release (sha256, status, version, commit, package manifest, and the path you gave);
- the job-input hashes, and the sha256 of the delivered file name;
- the admission, the ledger and `restart_of`;
- your model.

It then holds one entry per command, appended and never rewritten. Each entry records:
- the stage, its start and end time (UTC), and whether it completed;
- the result, the next step and its codes;
- the input and output files with their sha256;
- every tool's sha256, and each tool step with its exit code and log;
- the facts the stage checked;
- the operator's model;
- `seq`, the sha256 of the exact record before the entry, and the sha256 of the entry itself (`entry_sha256`). Every command verifies this chain first.

A completed stage, failures and interruptions included, is never run again in the same folder. A refused attempt is recorded too, as not completed.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | continue with the `NEXT` step |
| 3 | the job stopped (`NEXT: STOP_<reason>` or `NEXT: OWNER_DECISION`) and the stop is recorded; for `verify-frozen`, the folder changed |
| 4 | `REFUSED: <code>`: nothing was consumed |
| 2 | usage error |

## Never

- Re-run a completed stage, or re-prepare into an existing folder or under another jobs root to get a different result.
- Record a technical interruption for anything but a technical break.
- Move or rename a job folder, a jobs root or the ledger.
- Run two commands on one job at the same time, interrupt `finish`, or re-issue a command whose shell timed out.
- Edit a response, a reader file, a review, a generation record, a workbook, the record, the ledger or any file in a job folder.
- Open and re-save a workbook.
- Review the rendered pages yourself in place of a fresh conversation.
- Paste private file contents into a conversation other than the one the prompt names.
- Send anything but the file `deliver-check` names.
