# Status addendum — 2026-11-06 (later): static CPS folder and personal preferences (O41, O42)

- **Owner's instruction.** The CPS folder is the static project folder. The survey answers and any later instructions are standing personal preferences, kept in the Dots folder and different for each user. CPS returns to the maintainer only for system failures or bugs.
- **O41: the Dot personalizes a copy.** CPS produces and checks one standard file per job, the same for every user. The Dot copies it, applies the requesting user's standing preferences, logs every change (`cps.personal-copy-log.v1`) and sends the copy. The standard file stays in the job record. Preferences never change CPS and are never sent to the maintainer.
- **O42: qualification is kept, on the frozen 046g** with writer v2.8.2 and runner v4. The maintainer scores it once and sets `RELEASED_FOR_USE` only on a pass. After that the maintainer is involved only for failures or bugs (hand-back case C, evidence in `reports/`).
- **046h.** No survey-driven 046h. `research/guideline046_008/PLAN_046h.md` is marked superseded as a survey plan; its section B is kept as a backlog for a bug-fix candidate.
- **Dot documents rewritten** in the Drive folder "CPS". New `09_PERSONAL_COPY.md`. Each user's profile is `<user profile folder>/CPS_PREFERENCES.md`, outside CPS. The empty `OPTIONS.json` mechanism and `04_handback/` are superseded. Model summary: [DEPLOYMENT_MODEL.md](DEPLOYMENT_MODEL.md).
- **Drive folder "CPS" updated (2026-11-07).**
  - The rewritten documents are uploaded, with the old copies in `_superseded/`.
  - New folders `qualification/` and `reports/`.
  - `FOLDER_MANIFEST.md` lists 45 files with their sha256. Every Drive file's size matches it.
  - `cps_runtime/RUN_PHASE1.md` and `RELEASE.json` (still `SETUP_ONLY`) now pin commit `b79a14e`, with writer v2.8.2 and runner v4.
  - Phase 1 at `b79a14e` was re-run from a fresh public clone as the unprivileged test user, using the installed `~/cps-tools`. The setup inputs are unchanged since `01eaf23`. Results: `all_met` true, export self-test 600/600 with visual tests.
- **Next.**
  1. The Dot's Phase 1 setup report.
  2. Admit the VM node and stage the qualification jobs.
  3. Publish `RELEASED_FOR_QUALIFICATION`.
  4. After the Dot's hand-back B, score once.

---

# Status addendum — 2026-11-06: dev trial, writer v2.8.2 and runner admitted, Dot setup ready

- **Dot setup.** The Dot's VM has no root and has Node 24. `deploy/setup_vm_user.sh` (commit `01eaf23`) installs everything under `~/cps-tools`, and was tested as an unprivileged user. The Drive folder "CPS" (in "Dots Folder") has the new `cps_runtime/RUN_PHASE1.md`. The owner relays the Phase 1 rerun; the survey is on hold until CPS can run right after it.
- **046g development trial.** Nine exposed tuning cases, reader A only, through the job runner: 3,183/3,292 = 0.967 pooled, lowest case 0.954, 0 critical errors. Development evidence only. Details: [RESULTS_046G_DEVTRIAL.md](RESULTS_046G_DEVTRIAL.md).
- **Owner decisions:**
  - O39: delivered columns widen to fit; the O38 widths are minimums; default font 新細明體 11, owner-confirmed;
  - O40: an attested generation record is accepted as evidence of generator isolation, with the transcript when the Dot can export one.
- **Writer v2.8.2 / saved_qa v6.4 / visual_qa v4.5 ADMITTED** (`research/export/ADMISSION_WRITER_V28.json`). Three independent review rounds; the last gave ADMIT.
  - Values are never cut, by a calibrated per-character estimate. Its scope is Big5 and ASCII; the limitation is recorded.
  - Each delivered page is also cut into tiles for the visual reviewer, with a measured legibility flag.
  - Tests: 600/600 with visual tests.
- **Job runner `cps_job.py` (cps-job-runner.v4) ADMITTED** for everyday and qualification jobs (`deploy/run/ADMISSION_RUNNER_V4.json`).
  - Reviews: a first review (13 required fixes), a delta review (3), a final review (2), then a confirmation that gave ADMIT for both uses. Each fix round was implemented by a separate implementer.
  - What it enforces: a pinned and clean release; a verified record chain; frozen read-only folders; a job lock; exact input pins; fresh-context attestations; the tile hash check; re-checking the live release and the writer admission at delivery; a qualification ledger, admission and nonattempts; the rule 3 restart, once and only before a response is written; the O40 generation record.
  - Tests: 249/249 as root and 249/249 with every capability dropped.
- **Next.**
  - The Dot's Phase 1 setup report, which gives its VM paths and its node sha256.
  - Then stage the qualification jobs in Drive.
  - After the survey: candidate 046h (`research/guideline046_008/PLAN_046h.md`), its review and freeze, then the qualification admission and release.

---

# Status addendum — 2026-11-05 (deployment preparation: the Dot)

- **Deployment path (owner decisions O36, O37).** A ChatGPT agent, "the Dot", runs CPS on its own cloud VM and interviews the creator. The Dot works from a curated private Google Drive folder (`CPS_Dot_20261105`, in the project workspace). Qualification comes first.
  - All development scores so far came from `claude-opus-5-5` as generator. The Dot's runtime will be the generator, so qualification outputs must be generated by the Dot itself, in fresh contexts that hold only the package and the packet.
  - Evaluation stays a separate role, run by the maintainer.
- **Starting survey.**
  - 11 questions (DOT-01 to DOT-11, revision Q-REV-1), asked conversationally, with examples from exposed tuning cases only.
  - Every new authorized user gets the same survey. Each user's answers are saved as that user's own standing preferences.
  - A preference changes output only when the maintainer releases it as an option in `cps_runtime/OPTIONS.json`, which is empty for now.
- **Survey findings that may change rules.**
  - DOT-01: year-115 targets leave out many 不含估價 lines, mostly whole unpriced sections. That is against R50, and it is a risk for the 9 year-115 pool cases.
  - DOT-09: all 7 files from 1141001 onward keep the dash after the customer short name, which is against the O33 majority rule. Her workbooks also have two sheets, 未填 and 原材料清單.
  - DOT-02/04: A/B placement and naming.
  - These are settled by her answers, then folded into the next candidate with review and a freeze, before qualification.
- **Frozen since the last status.**
  - Evaluator v4, `compare_target050.py`, frozen at `fc723405…` after two review rounds. It scores A/B per panel (O35).
  - The O31 gate aggregator v2 (`e5aa4fc7…`).
  - `deploy/` holds the VM setup, the environment check, a writer directory using the public writer copy and the validation stub, and the example renderer.
- **Still open before qualification.**
  - Writer v2.6: O33 naming and O34 no grey G/H, then its review and admission.
  - 046g: carry the v4 references and the survey-driven changes, review, then freeze.
  - Admit the Dot VM's node binary after its self-test.
  - Build the qualification `JOBS.json`, with packets from `qual_sources` and the scope stage for 12 large jobs.

---

# Status addendum — 2026-11-05 (evening): delivered format, writer v2.7, Dot folder

- **Owner decision O38.** The delivered workbook is one sheet in the creator's own 未填 format: 新細明體 12; grey bordered header; gridlines shown; only the header row frozen; no wrapping; her widths and row heights. The owner approved it on four previews. The review and composition sheets go into `INTERNAL_QA_WORKBOOK.xlsx`, which is never delivered.
- **Writer v2.7 / saved_qa v6.1 / visual_qa v4.1 admitted** (`research/export/ADMISSION_WRITER_V27.json`; supersedes the v2.5 record for new runs). The review returned ADMIT_AFTER_LISTED_FIXES:
  - W1: column widths are now read as LibreOffice reads them;
  - D1: test titles are now invented.

  The delta review returned ADMIT. Tests: 579/579 with visual tests, 559/559 on the public copy. New condition 9: at delivery, the file sent must match `deliverable_xlsx.sha256` in `SAVED_QA.json`.
- **Dot folder uploaded.** `CPS_Dot_20261105` in Drive holds 45 files with their manifest. Release status is `SETUP_ONLY`. The owner has the folder link and the Dot's starting prompt. Next from the Dot: the phase-1 setup report (admit its VM node binary), then the creator survey hand-back.
- **Phase-1 steps verified** from a clean checkout: 459/459 with the admitted v2.5 tools at commit `dc1638b`.

# Status addendum — 2026-11-05 (late)

- **Done since the last status:**
  - The portable writer v2.5 / saved_qa v4 is **admitted** (`research/export/ADMISSION_WRITER_V25.json`, four review rounds).
  - The O31 gate aggregator is frozen (`research/evaluation/FREEZE_AGG_O31.json`).
  - 046g round-1 review fixes are applied, plus the 箱體 exception from the creator-data replay. Route tests pass 284/284 and scope-stage tests 62/62. A delta review is in progress.
  - The 9-case dev-trial packets are built, with metadata-only job inputs and leave-one-out tables.
- **Main risk to qualification: year-115 A/B convention.**
  - Of the 5 exposed year-115 targets, the 3 from March–May put each panel's A/B on every row of its group. The January and June ones put it on the enclosure row only.
  - All 9 year-115 pool cases (Feb–May) fall in that window. Under O30, enclosure row only, a group-wide target scores about 0.7, below the O31 per-case floor of 0.90.
  - The owner asked for one more exposed check (1150107, plus late-114 cases) before deciding.
- **Estimate given to the owner:**
  - about 3–4 session days to a qualification result if nothing else fails;
  - about a week with one more candidate revision after the dev trial.
  - A failed qualification spends the reserved cases, and no fresh 113–115 pool remains.

---

# Current status — 2026-11-05 (pool fixed at 30; evaluator v3 frozen; 046g in progress)

**Not deployment-ready.**
- **Qualification pool:** exactly 30 pairs, 15 non-reserved and 15 reserved, with no margin (O25, O26; [QUALIFICATION_SCREEN_20261104.md](QUALIFICATION_SCREEN_20261104.md)). 8 of the 15 non-reserved pairs need the large-workbook scope stage.
- **Evaluator v3** (`research/evaluation/compare_target049.py`, gap fill) is frozen at `b600c046…`, after an adversarial review and a delta review. It governs qualification (O23). v2 numbers are reported beside it, and the 046f dev results stay v2-governed.
- **C/D 0.75:** reported only (O24).
- **Company tables:** owner-approved recommended entries (O27), private and pinned by hash.
- **Portable writer:** v2.3 passed its second review except for two saved-QA findings, F1 and F2 (values that LibreOffice reads differently, and a receipt-mode downgrade). v2.4 hardening is in progress. Not admitted.
- **Candidate 046g** (in progress):
  - R59 scope stage for large workbooks: the BILL1 rule, a scope reader, an agreement check, the scoped inventory, and route v4.3;
  - an enclosure A/B practice study;
  - harness references moved to v3.
- **Next:**
  1. Admit the writer.
  2. Review and freeze 046g.
  3. Run a 046g dev trial on the five large exposed tuning cases plus a regression on the dev cases.
  4. Qualification: 30 pool outputs plus all 38 reserved outputs, frozen before any reserved answer is opened. Saved and visual QA on each.

---

# Current status — 2026-11-04, later (046f trial done; qualification screen done)

**Not deployment-ready.** The gate is 95% match with the creator's historical 未填 (O12, O19), on 30 independently eligible pairs including 10 reserved, drawn from 113–115 current-template targets only (O21, O22).

- **Candidate 046f** (`research/guideline046_006/`) is frozen (manifest `5f5502a7…`), reviewed and approved after two rounds. Route v4.2 passes 221/221.
- **046f development trial** on five exposed tuning cases ([RESULTS_046F_DEV.md](RESULTS_046F_DEV.md)):
  - Governing scores were 0.985, 0.962, 0.942, 0.928, and 0.585. The last case is an old-template target, now excluded under O21.
  - Readers A and B produced identical results, with 0 critical errors.
  - The trial earns no eligibility credit.
- **Portable writer** (`research/export/`) has a review verdict of ADMIT_AFTER_LISTED_FIXES. The S1–S4 hardening is in progress. It is not admitted yet, so visual QA has not run.
- **Qualification screen** ([QUALIFICATION_SCREEN_20261104.md](QUALIFICATION_SCREEN_20261104.md)):
  - Of 22 non-reserved candidates, 10 are eligible now, 10 are large workbooks that need a reviewed scope method, and 2 are old-template and ineligible.
  - Reaching 20 non-reserved pairs needs all 20 current-template candidates, with no margin.
  - Family independence has not been established; that review is running.
  - 21 reserved cases are in scope, with templates checked only after all outputs are frozen.
- **Next:**
  1. Finish the writer hardening, then confirm and admit it.
  2. Finish the family review.
  3. Run a structure study of large 材料清單 files on exposed tuning cases.
  4. Build candidate 046g: the scope stage for large workbooks, glossary category words, R52 matching after a qualifier, the equipment test, and enclosure A naming. Then review it and run a regression on the dev cases.
  5. Run qualification. Reserved targets stay closed until all outputs are frozen.

---

# Current status — 2026-11-04 (calibrating CPS to the historical 未填 creator)

**Not deployment-ready.** The owner reset the goal: CPS must match the creator's historical 未填 at 95% (owner decisions O10–O20 in `research/guideline046_005/DECISIONS_OWNER_*.md`). The studies behind this are in `research/guideline046_005/STUDY_*.md`.

- **The 95% bar (O19).** It counts rows and every non-description field. C/D wording is reported separately against a 0.75 target, because the creator's own C/D agrees with her earlier projects only 72–77% of the time.
- **Inputs.**
  - The contract, plus the company material list 材料清單 (O17). It carries brand/model on 99.9%/93.7% of her values.
  - Job inputs for L/M/N (O13).
  - Owner-reviewed private tables: an abbreviation glossary and a brand table (O14/O15/O18). The drafts were sent to the owner for review.
- **Reachability.** The studies were simulations, not generated outputs. With the 材料清單, rules and no phrasebook, 14–23 of 39 tuning cases reach ≥0.95 under the O19 metric, and 29–33 reach ≥0.90.
- **Candidate 046f** (`research/guideline046_006/`) is a draft with creator-practice rules R47b–R58. Two things are in progress: interface relaxations (C null, Q without verified adoption, and L/M/N job-input evidence in route v4 and portable writer v2), and updated examples.
- **Next:**
  1. An independent review of 046f.
  2. A first 046f generation on tuning cases with their 材料清單, measured with `compare_target048.py` v2.
  3. Then qualification on rolling-validation and reserved cases (30 pairs including 10 reserved), with saved and visual QA through the portable writer once it is reviewed.
- **Earlier work.** Candidates 046a–046e and the source-only expectation track are kept as history. The batch-1 results are in `RESULTS_046C_BATCH1.md` and the diagnostic in `DIAGNOSTIC_HISTORICAL_MATCH.md`.

---

# Current status — 2026-11-03 (after 046c development batch 1; 046d frozen)

- **Candidate 046c, development batch 1 (three tuning cases; rolling-validation case 1150107 held out before generation).** On 1141002, 1130803 and 1140506, both readers cleared the governing numeric gate in declared-alternatives mode: 550/550 for both readers; 239/239 for both readers; 353/354 and 354/354. Every manual obligation was met and there were 0 critical errors. Canonical core falls below 99% on two cases, entirely because of placements 046c leaves undecided. No case counts as passed: export, saved 17-column QA and visual QA were not attempted, and tuning cases earn no eligibility credit. Details: [RESULTS_046C_BATCH1.md](RESULTS_046C_BATCH1.md).
- **Candidate 046d** (`research/guideline046_004/`), frozen with manifest `b2c5177a…` and not admitted. It adds:
  - R25 for analysis-component rows, fixing the example defect that failed 1141210 reader A ([RESULTS_046C_1141210.md](RESULTS_046C_1141210.md));
  - R26–R38, deciding backlog Q1–Q13;
  - R39–R44, from the batch-1 error classes.
  
  An independent semantic review, including a delta round, approved it ([REVIEW_046d.md](../../research/guideline046_004/REVIEW_046d.md)). The harness audit tool now extracts paths from full commands.
- **Batch 2 under 046d:** three tuning cases (1130204, 1131202, 1140507), with packets built from Drive originals verified against the registry hashes. Independent expectations are being authored. Six large workbooks (1131112, 1140607, 1140304, 1131207, 1140808, 1140608) need a chunked reading method first.
- **Unchanged blockers:**
  - No admitted export runtime exists, so saved-workbook and visual QA cannot run.
  - No eligibility evidence exists for the 30-pair bar.
  - All 38 reserved answers stay closed.
  - The four R8 undecided classes still need owner decisions before canonical scoring can govern.
- **Pair counts:** 1 eligible development pair, 0 eligible reserved pairs, 0 performance-passed historical pairs.

---

## Status after the 046b trials (2026-11-03, kept as history)

The resumed session finished the interrupted review and built candidate 046b, with the source-reference adapter (route v2), a writer-port parity check and invented-fixture route tests (113/113). An independent reviewer approved 046b for bounded source trials after two rounds. Independent 1141208 source expectations were authored, reviewed and frozen. One exposed 1140908 A/B pair and one 1141208 A/B pair then ran in fresh contexts. All outcomes were frozen before evaluation, and evaluation ran in separate contexts.

- 1140908: A 141/176, B 140/176 canonical core. This is a regression against 045 (155 and 147), with a different runtime (observed `claude-opus-5-5`). Failed.
- 1141208: A and B both 107/107 declared-alternatives core (canonical: A 107, B 105). Both failed the source-case gate on obligation S05. No critical errors.
- Saved-workbook QA, visual QA and assembly repeatability were not attempted, because no export runtime is available here.
- 1 eligible development pair, 0 eligible reserved pairs, 0 performance-passed historical pairs. All 38 reserved answers stay closed.

Details: [RESULTS_046B.md](RESULTS_046B.md). Next steps: [RESUME_047.md](RESUME_047.md). The section below is the earlier interrupted-handoff status, kept as history.

---

## Earlier status (interrupted handoff, 2026-11-03)

The later [portable supplement](PORTABILITY.md) adds exact missing project dependencies, a complete1141208saved-cache inventory and two reconstructed views. It did not finish independent expectations or any new model trial. The interruption state below remains historical evidence.

## What exists

The completed naming study reviewed292 saved output observations/146distinct source items across045,041,039 and153development source profiles. Many apparent translations were source-language names versus historical abbreviations. It also identified leading-code/rating, cross-column and compound/accessory/service naming gaps. The full study is private; this repository has a generic summary and resources.

Candidate046a has12files,70,557 UTF-8 bytes and63,363Unicode characters, excluding its manifest. Its33authoring checks passed. The original candidate is frozen; do not edit it in place. No source-reference resolver/old-carrier adapter exists yet, and no full JSON Schema engine or model test was claimed.

The user asked to proceed with independent review, fix findings and test1140908and1141208. The interrupted review verified all12package hashes and sent mandatory interface findings. No final signed review report/approval was saved, and no fixes were implemented. See [review notes](INTERRUPTED_REVIEW_046.json). Treat those notes as preliminary evidence, not approval.

The1141208reconnaissance captured all3sheets (2empty),47physical rows/376positions/220nonempty values. A later source-preparation directory contains only4files: inventory script, scope, source census and cached-cell data. It has no completed reader packet, visuals, independent final expectations or freeze. The expectation directory is empty. Complete it before a test. The prep role's accidental1140908audit-policy exposure is recorded; keep it out of fresh1140908generation/evaluation independence claims.

## What was not completed

No046original model call, no new1140908or1141208score, no amended candidate, no production adapter and no deployment qualification. The last completed model readings are045, whose failures remain unchanged. Source/format/copying checks are separate from semantic correctness.

## Authority and next action

The current request packages a handoff and selected private resources. All workers are idle/completed; heartbeat remains paused. Continue when the user gives the handoff prompt to an agent. Finish independent review, resolve findings in a new version and run meaningful route checks, then one new exposed1140908A/B regression followed by1141208. Keep source-only generation and historical evaluation separate, preserve all exclusions and38reserved projects, and retain the fixed deployment bar.
