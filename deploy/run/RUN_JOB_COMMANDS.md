# Running a CPS job with `cps_job.py`

This is the command sheet for the operator (the Dot). `05_RUNBOOK_CPS_JOB.md` says what each stage does and why; this sheet says exactly what to type, what to open in each new conversation, and what to do at each `NEXT:`. Every command runs on your VM.

`deploy/run/cps_job.py` runs every CPS tool for you, in order, with the pinned versions, and keeps one record per job (`RUN_RECORD.json`). It never prints cell text, job inputs or the job title: only hashes, counts, codes and the paths you need. Tool output goes to the job's `logs/` folder.

## Before the first job

1. `cps_runtime/RELEASE.json` must say `"status": "RELEASED_FOR_USE"` for real jobs, or `"RELEASED_FOR_QUALIFICATION"` for qualification jobs. The runner refuses anything else.
2. Activate the Python environment with openpyxl 3.1.5 and xlrd 2.0.2 (`source ~/cps-venv/bin/activate`). The runner calls every tool with the same `python3`.
3. `node` (v22) must be on `PATH`, with LibreOffice (`soffice`), `pdftoppm`, `pdfinfo` and `pdftotext`.
4. The builders read openpyxl and xlrd from a *deps bundle*: a folder whose `private/deps` is the venv's `site-packages`. Make it once:
   ```bash
   mkdir -p ~/cps-deps/private
   ln -s "$(python3 -c 'import openpyxl, os; print(os.path.dirname(os.path.dirname(openpyxl.__file__)))')" ~/cps-deps/private/deps
   ```
   The release names it in `source_prep.deps_bundle`.

Set these once per shell. No path may contain spaces.

```bash
CPS=~/cps                          # the repository clone at the release commit
RT=/abs/path/cps_runtime           # holds RELEASE.json and tables/
JOBS=/abs/path/jobs                # one folder per job is created here
R="python3 -I -B $CPS/deploy/run/cps_job.py"
ME="<your model name as your platform reports it>"
```

## Job inputs (runbook §2)

Get these from the owner or operator; never infer them. Write two private files for each job, outside `$JOBS`.

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

The title starts with the case id. The writer derives the delivered file name from it.

## Stage 1: prepare

```bash
$R prepare --release $RT/RELEASE.json --job /abs/JOB.json --job-title-file /abs/JOB_TITLE.json \
   --jobs-root $JOBS --operator-model "$ME"
```

It does the following:
- checks the release (status, repository commit, package manifest and every package file, the export tools against `ADMISSION_WRITER_V27.json`, the checker node, the writer folder, openpyxl);
- checks the job inputs and the company tables;
- creates `$JOBS/<case id>/` and copies the release, `JOB.json`, `JOB_TITLE.json` and the source into `input/` (read-only);
- runs `make_job_config.py`, the inventory builder (`.xlsx` or `.xls`), `render_views.py` and the route's `check-inventory`;
- runs `scope_tool.py`. More than 2,500 literal or cached-formula content cells starts the scope stage (R59). Otherwise it runs `prepare_run.py` and writes the generator prompt.

The last line is one of:

| Last line | What to do |
|---|---|
| `NEXT: GENERATE prompt=<P> folder=<F>` | Stage 3 (generation). |
| `NEXT: SCOPE_READER prompt=<P> folder=<F>` | Stage 2 (scope reader). |
| `NEXT: OWNER_DECISION` | The scope tool holds the case (zero or several bill sheets, or similar). Stop and tell the owner. Never choose yourself. |
| `NEXT: STOP_<reason>` | Stop and tell the owner the reason code. |
| `REFUSED: <code>` | Nothing was created. Fix the cause (wrong path, wrong table, unreleased node, a job input `make_job_config.py` refuses: `JOB_CONFIG_REFUSED`) and run the same command again. If the cause is not yours, tell the owner. |

## Stage 2: scope reader (only after `NEXT: SCOPE_READER`)

1. Open a **new conversation**. Give it the full text of the prompt file `<P>` (`scope/SCOPE_READER_PROMPT.md`). It may read only `<F>/input/`, which holds `SCOPE_DIGEST.json` and `SCOPE_RULES_EXCERPT.md`. It writes `<F>/output/SCOPE_READER_RESPONSE.json`.
2. Then run:
   ```bash
   $R scope-finish --job-dir $JOBS/<case id> --reader-response $JOBS/<case id>/scope/reader/output/SCOPE_READER_RESPONSE.json --operator-model "$ME"
   ```
   It freezes the reader's file before anything reads it. It then runs `scope_agree.py`, `make_scoped_inventory.py` and its `--verify`, `check-inventory` on the scoped packet (`scope: applied`), and `prepare_run.py`.

| Last line | What to do |
|---|---|
| `NEXT: GENERATE prompt=<P> folder=<F>` | Stage 3. |
| `NEXT: OWNER_DECISION` | The tool and the reader disagree (`scope/decision/SCOPE_HOLD.json`). Tell the owner. Never pick a side, never ask a second reader. |
| `NEXT: STOP_<reason>` | Tell the owner. For example, `STOP_SCOPE_READER_RESPONSE_REFUSED` means the reader's JSON was malformed, and `STOP_SCOPE_DECISION_NOT_ADMISSIBLE` means it was not a fresh-context reader. |

## Stage 3: generation (after `NEXT: GENERATE`)

Open a **new conversation**. Give it the full text of the prompt file `<P>` (`run/GENERATOR_PROMPT.md`). It may see only the folder `<F>` (`run/A/`): `input/package/`, `input/packet/` and `output/`. It writes `<F>/output/response.json`.

Never edit the response. Never give the conversation anything else: no other job, no interview material, no historical 未填, no earlier responses.

## Stage 4: finish

```bash
$R finish --job-dir $JOBS/<case id> --response $JOBS/<case id>/run/A/output/response.json \
   --generator-model "<the generating conversation's model>" --operator-model "$ME"
```

`finish` first re-checks the export environment. It then freezes the response: a read-only copy in `response/response.json`, with its sha256 recorded, before anything reads it. Then:
1. Route `check`. If it fails, the failure is the job's outcome (`NEXT: STOP_ROUTE_CHECK_FAILED`). It is never retried.
2. `convert`.
3. The writer, in the mode the convert receipt's `export_mode_required` names (condition 6), titled from `input/JOB_TITLE.json`. `--job-title` is optional; if given, it must equal the file.
4. The duplicate-key check of `WRITER_RECEIPT.json` (condition 5), and the tool hashes (condition 3).
5. Saved QA from a clean environment with the pinned checker node (conditions 1, 2, 4, 7).
6. Visual QA of `<name>(未填).xlsx` and of `INTERNAL_QA_WORKBOOK.xlsx` into separate folders (condition 8).
7. The page selection, `qa/QA_EVIDENCE.json`, and the visual-review prompt.

| Last line | What to do |
|---|---|
| `NEXT: VISUAL_REVIEW prompt=<P> folder=<F>` | Stage 5. |
| `NEXT: STOP_<reason>` | Record and tell the owner. Never retry, never patch by hand. Typical reasons: `STOP_ROUTE_CHECK_FAILED`, `STOP_NOT_CARRIED`, `STOP_WRITER_REFUSED`, `STOP_SAVED_QA_NOT_EVIDENCE_GRADE` (`qa/QA_EVIDENCE.json` lists the failed conditions), `STOP_VISUAL_QA_RENDER_FAILED`. |
| `REFUSED: <code>` | Nothing was consumed: the response was not frozen. For example, `CHECKER_NODE_NOT_ADMITTED` (your node binary changed) or `JOB_TITLE_MISMATCH`. Fix the cause, or tell the owner, and run the same command again. `STAGE_ALREADY_COMPLETED` means finish already ran: never run it again. |

## Stage 5: visual review (after `NEXT: VISUAL_REVIEW`)

1. Open a **new conversation**. Give it the full text of `<P>` (`qa/VISUAL_REVIEW_PROMPT.md`). It may open only the PNG files the prompt lists, and it judges PNGs only. It writes `qa/visual_review/VISUAL_REVIEW.json`.
2. Then run:
   ```bash
   $R visual-record --job-dir $JOBS/<case id> --review $JOBS/<case id>/qa/visual_review/VISUAL_REVIEW.json --operator-model "$ME"
   ```
   It checks that the review covers every selected page and every checklist item, with `n/a` only where an item does not apply. It checks that each visual manifest's `saved_xlsx.sha256` equals `SAVED_QA.json` (`deliverable_xlsx.sha256`, `xlsx.sha256`). It records PASS or FAIL.

| Last line | What to do |
|---|---|
| `NEXT: DELIVER_CHECK` | Stage 6 (real jobs). |
| `NEXT: FREEZE` | Qualification: run `freeze`. |
| `NEXT: STOP_VISUAL_REVIEW_FAILED` | Any failed item fails visual QA. Tell the owner, and do not deliver. |
| `REFUSED: REVIEW_INCOMPLETE` | The review omitted a page or item and recorded no failure. The attempt's sha256 is recorded. Have the reviewer complete it, then run the command again. A review with any `fail` is never refused: it is recorded as FAIL. |

## Stage 6: deliver (real jobs only, `RELEASED_FOR_USE`)

Just before sending, run:

```bash
$R deliver-check --job-dir $JOBS/<case id> --operator-model "$ME"
```

This is condition 9. The delivered file must be a regular file: not a symbolic link, and with one hard link. Its sha256 must equal `deliverable_xlsx.sha256` in `qa/SAVED_QA.json`. Saved QA must be evidence grade, and the visual review must have passed. The result is recorded in `qa/DELIVERY_CHECK.json`.

- `NEXT: DELIVER file=<path>`: send exactly that file and nothing else, as the runbook (§9) says. Never send `INTERNAL_QA_WORKBOOK.xlsx` or any QA file.
- `NEXT: STOP_DELIVERY_CHECK_FAILED`: do not send anything. Tell the owner.

`deliver-check` runs once per job. If you are not sending right away, run it when you are.

## Qualification mode (`06_QUALIFICATION_PROTOCOL.md`)

Qualification jobs differ in the following ways:
- `RELEASE.json` says `RELEASED_FOR_QUALIFICATION`. `prepare` takes `--qualification --admission <ADMISSION.json> --reader A|B`.
- **The admission is frozen before `prepare`**, with `research/guideline046_007/harness/freeze_admission.py`. It must pin, by sha256:
  - the package manifest;
  - the route `package/tools/cps046b_route.py`;
  - the job's `JOB.json`;
  - the source;
  - the glossary (and the brand table on a contract job);
  - the title file, under the label `job_title_<case id>`.

  `prepare` refuses an admission that misses one of them, or one frozen after the prepare started. It also refuses an admission whose sha256 is not in `qualification.admission_sha256` when the release lists any. The packet hashes are recorded in `RUN_RECORD.json` at prepare, before any generation.
  ```bash
  # ADMISSION_CONFIG.json: {"files": {"package_manifest": "...", "route": "...", "job_1141002": "/abs/JOB.json",
  #   "source_1141002": "/abs/source.xlsx", "glossary": "...", "job_title_1141002": "/abs/JOB_TITLE.json"}, "plan": {...}}
  python3 -I -B $CPS/research/guideline046_007/harness/freeze_admission.py --config /abs/ADMISSION_CONFIG.json --out /abs/ADMISSION.json
  ```
- **Run A and run B use separate job roots:** `--jobs-root $Q/A --reader A`, and later `--jobs-root $Q/B --reader B`. Start run B only after run A is frozen.
- **No per-user options** apply. The runner takes none, and the record says so.
- **Fixed file locations.** The response must be `run/<reader>/output/response.json`, and the scope reader's file must be `scope/reader/output/SCOPE_READER_RESPONSE.json`. `finish` refuses a `--job-title` that differs from the pinned title file.
- **Freezing.** After `NEXT: FREEZE` (visual review passed) and after any `NEXT: STOP_<reason>` or `NEXT: OWNER_DECISION`, freeze the run:
  ```bash
  $R freeze --job-dir $Q/A/<case id> --operator-model "$ME"
  ```
  It appends the last record entry, then writes `FROZEN.json`, which lists every file of the folder with its sha256, and makes the folder read-only. After that every subcommand is refused. Never touch the folder again.
- **No delivery.** `deliver-check` refuses qualification jobs.
- **Nonattempts** (rule 6) are not run through `cps_job.py`. Freeze them as the protocol says.
- **A technical interruption before the response is written** (for example `STOP_RENDER_VIEWS_FAILED` or `STOP_RUNNER_ERROR` during `prepare`) may be restarted once:
  1. freeze the interrupted folder as it is;
  2. prepare again under a new jobs root (for example `$Q/A_restart1`);
  3. tell the owner, naming both folders.

## Release fields the runner reads

`RELEASE.example.json` shows every field with invented values. Relative paths are taken from `repository.root`.

| Field | Used for |
|---|---|
| `schema` | must be `cps.release.v1` |
| `status` | `RELEASED_FOR_USE` (real jobs) or `RELEASED_FOR_QUALIFICATION` (with `--qualification`) |
| `release_version` | recorded |
| `repository.root` | the clone on this VM (default: the repository that holds `cps_job.py`) |
| `repository.commit` | must equal `git rev-parse HEAD` when git is available (recorded either way) |
| `package.path`, `package.manifest_sha256` | the guideline package. The manifest hash, every listed file's hash and no unlisted file are checked. |
| `harness.path` | `make_job_config.py`, `scope_tool.py`, `scope_agree.py`, `make_scoped_inventory.py`, `prepare_run.py` and both prompt templates |
| `source_prep.path` | the builders, `render_views.py`, `screenshot_views.cjs`, `auto_views.py` |
| `source_prep.deps_bundle` | folder holding `private/deps` (openpyxl 3.1.5, xlrd 2.0.2) for the builders' `--bundle` |
| `source_prep.node_path` | optional `NODE_PATH` that resolves `playwright` for `render_views.py` |
| `writer.admission`, `writer.admission_sha256` | `research/export/ADMISSION_WRITER_V27.json` and its pin. Its `files_sha256` is condition 3; its `writer_dir_sha256` is condition 4; its `checker_node` is used when the release has none. |
| `writer.writer_dir` | the writer folder (`deploy/writer_route/writer`) for the writer and saved QA |
| `checker_node.path`, `checker_node.sha256` | the checker's node binary (condition 2). Its sha256 must be listed in `admitted_checker_node_sha256`. |
| `admitted_checker_node_sha256` | the node binaries the maintainer admitted after a full self-test |
| `saved_qa_clean_path` | optional `PATH` of saved QA's clean environment (default `/usr/bin:/bin`) |
| `tables.glossary.{path,sha256}`, `tables.brand_table.{path,sha256}` | the only company tables a job may use |
| `tables.company_name_sha256` | optional: the sha256 of the UTF-8 company name a job must use |
| `qualification.admission_sha256` | optional list of admitted qualification admissions |
| `pinned_files_sha256` | optional map of repository-relative path to sha256, checked by every subcommand. For example, the runner itself and the harness scripts. |

## The job folder

`$JOBS/<case id>/`:

| Path | Contents |
|---|---|
| `input/` | `RELEASE.json`, `JOB.json`, `JOB_TITLE.json`, `source.<ext>` and, in qualification, `ADMISSION.json`. All are read-only copies; later stages use this release copy. |
| `packet/` | `BUILDER_CONFIG.json`; `full/` (`SOURCE_INVENTORY.json`, `view_*.png`) |
| `scope/` | `tool/` (the scope proposal, and the digest when the stage applies); `reader/input/`, `reader/output/`; `SCOPE_READER_PROMPT.md`; `SCOPE_READER_RESPONSE.json` (frozen); `decision/`; `scoped_packet/` |
| `run/` | `A/` (or `B/`), the bounded generation folder from `prepare_run.py`; `GENERATOR_PROMPT.md` |
| `response/` | `response.json` (frozen), `ROUTE_CHECK.json` |
| `carrier/` | `convert/`: `carrier.json`, `ADAPTER_RECEIPT.json`, `CENSUS_LEDGER.json` |
| `export/` | `writer/`: `<name>(未填).xlsx` (the delivered workbook), `INTERNAL_QA_WORKBOOK.xlsx`, `EXPECTED_SAVED_VALUES.json`, `WRITER_RECEIPT.json` |
| `qa/` | `SAVED_QA.json`; `visual_deliverable/`, `visual_internal/`; `VISUAL_PAGES.json`; `QA_EVIDENCE.json`; `VISUAL_REVIEW_PROMPT.md`; `visual_review/`; `VISUAL_REVIEW.json` (frozen); `VISUAL_RECORD.json`; `DELIVERY_CHECK.json` |
| `logs/` | every tool's stdout and stderr (private; never paste them anywhere) |
| `RUN_RECORD.json` | the record (below) |
| `FROZEN.json` | after `freeze` |

`RUN_RECORD.json` (`cps.job-run-record.v1`) holds:
- the case id;
- the reader, and whether the job is a qualification job;
- the release (sha256, status, version, commit, package manifest);
- the job-input hashes;
- the admission;
- your model.

It then holds one entry per command, appended and never rewritten. Each entry records:
- the stage, its start and end time (UTC), and whether it completed;
- the result, the next step and its codes;
- the input and output files with their sha256;
- every tool's sha256, and each tool step with its exit code and log;
- the facts the stage checked;
- the operator's model;
- the sha256 of the record before the entry.

A completed stage, failures included, is never run again in the same folder. A refused attempt is recorded too, as not completed.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | continue with the `NEXT` step |
| 3 | the job stopped (`NEXT: STOP_<reason>` or `NEXT: OWNER_DECISION`) and the stop is recorded |
| 4 | `REFUSED: <code>`: nothing was consumed |
| 2 | usage error |

## Never

- Re-run a completed stage, or re-prepare into an existing folder to get a different result.
- Edit a response, a reader file, a review, a workbook or any file in a job folder.
- Open and re-save a workbook.
- Paste private file contents into a conversation other than the one the prompt names.
- Send anything but the file `deliver-check` names.
