# Owner decisions O23–O25 (2026-11-05, after the qualification screen and the evaluator-v3 proposal)

The owner chose these through the session's question tool. The question texts are summarized; the answers are verbatim.

| ID | Question | Owner answer | Effect |
|---|---|---|---|
| O23 | Which metric governs qualification? The question described the problem: v2 leaves a row unpaired when its C/D wording differs completely from the creator's, even when it is the same source line at the same position with equal E, F, Q and I/J, and its non-description fields then count as misses. It described v3 as positional pairing inside gaps between agreed rows, with equal counts and equal E and F. It gave the development figures, v2 0.985/0.962/0.942/0.928 against v3 0.985/0.982/0.966/0.984, and said they are post hoc. | "Adopt v3 if review OK (Recommended)" | `compare_target049` governs qualification once its independent review approves it and it is frozen by SHA before any qualification output is evaluated. Until then, and for every result recorded so far, v2 (`compare_target048`) governs. v2 numbers are reported beside v3. The review asked for a stricter fill key: E and F equal, and either Q equal and non-null or I equal, non-null and not 不含估價. That key only removes fills, so it stays within "if review OK". The revised v3 still needs the reviewer's delta approval. |
| O24 | Is the C/D description target of 0.75 (O19) a deployment gate? | "Reported target only (Recommended)" | `description_cd` is reported per case and overall, and is still worked on. It does not gate deployment; the 95% governing score does. This answers review item B3 on v3. |
| O25 | If fewer than 20 independent non-reserved pairs remain, how should the 30 pairs be reached? | "Use more reserved (Recommended)" | The bar stays at 30 independently eligible pairs, at least 10 of them reserved. A shortfall in non-reserved pairs is filled from the reserved 113–115 cases. Reserved answers stay closed until all outputs are frozen, and each reserved case used is spent. Independence rules apply to reserved cases as well. |

These decisions do not reopen frozen candidates, outputs or scores.

## Addendum (2026-11-05, after the v3 delta review; the table above is kept as written)

The O23 cell says the stricter key "only removes fills". That is wrong. The revision also replaced equal-count positional pairing with an order-preserving maximum matching inside each gap. On some inputs that adds fills compared with the first proposal: reviewer fixture C8c rises from 0.024 to 0.954, and C10a from 0.717 to 0.896. Both versions were reviewed, and the matching is what the review asked for, so the change is still within "if review OK". The delta review approved the revised code. It is frozen at sha256 `b600c046…` (`research/evaluation/FREEZE_049.json`).

## O26 (2026-11-05): the qualification pool short of 30

**Question.** After the family-independence review, the counts were:
- 14 independent non-reserved candidates in 113–115 (7 without the large-workbook method);
- 14 independent reserved candidates in 113–115.

That totals 28 of 30, before any reserved target is found to be old-template. Year 112 has 30 unexposed non-reserved cases, not yet screened.

**Owner answer:** "Accept borderline cases".

**Effect.** Two borderline independence cases are counted:
- the non-reserved case whose only overlap with an exposed case comes from a shared designer specification library, containment 0.646 (1150202);
- the reserved case with a weak project-series tie to exposed cases (listing only; not named in public).

The pool is exactly 30: 15 non-reserved and 15 reserved, with no margin. Year 112 stays outside (O22).

**Consequences.**
- Any pair that turns out ineligible leaves the bar unreachable from this pool, and that goes back to the owner. This includes a reserved target found to be old-template once opened after all outputs are frozen.
- The pool is not refilled by choosing replacements after the answers are seen. The single pre-declared alternate for the one reserved duplicate-family pair is recorded privately before generation.


## O27 (2026-11-05): company tables for qualification

**Question.** The draft abbreviation glossary and brand/model table were built only from 40 exposed tuning cases and sent for review. Which entries should qualification use? The glossary had 18 recommended entries, 12 pending ones (which the creator uses less than half the time) and 14 not recommended. The brand table matters only for contract-only jobs.

**Owner answer:** "Recommended entries only (Recommended)".

**Effect.**
- The glossary carries the 18 recommended abbreviations, plus their 4 spelling variants and the builder's 4 category words. The pending and not-recommended entries are left out; for those devices CPS keeps the Chinese name.
- The brand table is used as drafted, with the O18 breaker fallback: the most common brand.
- Both private tables were rebuilt with the dev-trial builder and no exclusion. The output is byte-identical to the drafts the owner reviewed. They are marked `OWNER_APPROVED_O27` and pinned by sha256 in each qualification admission.
- No qualification or reserved case contributed to either table.
- Any later change to a table (for example new category words) needs the owner's approval.

## O28–O29 (2026-11-05): two source gaps found during qualification source preparation

| ID | Question | Owner answer | Effect |
|---|---|---|---|
| O28 | One reserved case in the pool has no 材料清單 and no contract in its project folder. The only material-titled file is a quotation workbook (its title contains 報價單 and 承製價材料), which the pre-declared selection rule excludes; it has not been opened. Is it the job's company material list? | "Yes, use it" | For this one case, that workbook is bound as the material-list source (O17). The selection rule is unchanged for every other job. The pool stays at 30. |
| O29 | The 17 reserved cases from years 110–112 are outside the pool (O22). Their project folders are not in the connected Drive, and the registry has no contract for them. How should they be handled? | "Freeze as nonattempts (Recommended)" | Each is recorded as a frozen nonattempt, "source not available to this session", together with the other qualification outputs and before any reserved answer is opened. They are not scored and remain held out. |

## O30–O31 (2026-11-05): enclosure rows and the reading of the 95% bar

| ID | Question | Owner answer | Effect |
|---|---|---|---|
| O30 | Which rows carry A and B (盤體名稱/盤體規格)? The evidence: all 12 exposed year-114 files write A/B on the enclosure row only. Of the 5 exposed year-115 files, 3 (March–May) write each panel's A/B on every row of that panel's group, and 2 (January and June, June being the latest) write it on the enclosure rows only. Neither the customer nor the source layout predicts which. | "Enclosure row only (Recommended)" | A/B stay on the enclosure row only (R56). Year-115 targets that fill the whole group will score low on A/B; that is accepted. 046g revises how R56 names A and builds B, following the enclosure-practice study: the panel name from its section heading, tags kept, B only from W/H/D in the line's own description. |
| O31 | How does the 95% bar apply across the 30 qualification pairs? It had been read as every case ≥ 0.95. The creator is inconsistent on some conventions, so one atypical file could block deployment. | "Pooled ≥ 0.95, floor 0.90" | For each reader, matched/counted pooled over the 30 pairs must be at least 0.95 under evaluator v3, and no single case may be below 0.90. This replaces the per-case reading in AGENTS.md. Everything else in the bar is unchanged: 30 independent pairs with at least 10 reserved, 0 unresolved critical errors, two-reader repeatability, and saved and visual QA. It is fixed before any qualification output is scored. The aggregation is a separate script, reviewed and frozen before qualification. |


## O32 (2026-11-05): a date window for group-wide A/B

**Question.** Across 22 exposed current-template targets, A/B appears on the enclosure row only in:
- all 15 year-114 files;
- both January-115 files;
- the June-115 file.

All 3 files from March–May 115 put each panel's A/B on every row of its group. No exposed February file exists. Since June the creator is back to enclosure-only, so this changes only how historical qualification scores, not new jobs. 9 of the 30 pool cases are from year 115: 3 from February and 6 from March–May.

**Owner answer:** "Window Mar–May 115 (Recommended)".

**Effect.**
- For a job whose case id falls in 115-03 to 115-05, R56 writes each panel's A/B on every row of that panel's group. Every other job, including February 115, keeps A/B on the enclosure row only (O30).
- The window is read from the case id, which is a job input (L, R48).
- The exact group-membership rule is derived from the three window files in an evaluation-role study, then reviewed. Like every R56 change, it goes into a candidate before generation.

**Exposure note.** Rolling-validation case 1150107 was read for this decision (its A/B columns and row count only). From here on it counts as tuning-informed.

## O33–O34 (2026-11-05): deliverable naming and the G/H shading

The owner reviewed sample CPS outputs and asked for these two changes.

| ID | Owner instruction | Effect |
|---|---|---|
| O33 | "the CPS sheet should be named project code and project name followed by 未填, not 未填研究草稿". Asked which form, the owner answered "decide from evidence". Asked whether the file should be named like the creator's, the owner answered "Yes, like hers (Recommended)". | **Evidence.** All 65 non-reserved 未填 file titles in the listing end in `(未填)`. Of 61 with a registry folder title, the folder title with the dash after the customer short name removed, plus `(未填)`, reproduces 36. The folder title as written, plus `(未填)`, reproduces 30. **Rule.** The deliverable name is the project folder title (case id + customer short name + project, as a per-job input like L/M/N under O13), with the first dash after the customer short name removed, followed by `(未填)`. The file is `<name>.xlsx`, with characters Windows forbids replaced by `-`. The main sheet is `<name>`, with the characters Excel forbids (`: \ / ? * [ ]`) replaced by `-` and the text cut to 31 characters while keeping `(未填)`. Writer v2.6. |
| O34 | "why is the 單價 and 復價 column greyout? make sure its not greyed out." | G and H (單價, 複價) are no longer shaded. They look like the other body columns and stay blank, as in the creator's 未填. The visual-QA checklist item for G/H changes to match. Writer v2.6. |

## O35 (2026-11-05): A/B scored once per panel; supersedes O32

**Question.** An evaluation-role study of the three March–May 115 files found that a group-wide rule would still leave two of them below the 0.90 floor, with best possible scores of 0.84 and 0.67. The cause is that one wrong or unreachable panel name gets copied onto 70–90 rows and is counted on each. The evaluator already scores K–O once per case for the same reason: the creator writes them on every row in some years and on the first row in others. Scoring A/B once per distinct panel would remove the multiplication.

**Owner answer:** "Score A/B per panel (Recommended)".

**Effect.**
- **Metric.** Evaluator v4 (`research/evaluation/compare_target050.py`, built on v3) scores A and B as panel-level positions: the distinct A values and the distinct B values of each case, compared once. A wrong or missing panel name or size still counts, but only once per panel. It no longer counts on every row that repeats it.
- **CPS.** CPS stays enclosure-row only for every date (O30).
- **O32 superseded.** The date-window rule is withdrawn before any package carried it.
- **Before qualification.** v4 needs an independent review and a freeze. The O31 gate aggregator is re-pinned to v4.
- **Earlier results.** All results recorded so far keep their v2 or v3 numbers. v3 numbers are reported beside v4 in qualification.

## O36–O37 (2026-11-05): go-live path and runner

| ID | Question | Owner answer | Effect |
|---|---|---|---|
| O36 | Should CPS go live before or after the 30-pair qualification? | "Run qualification first (Recommended)" | CPS goes live only if it passes O31 qualification. The creator interview (O37) runs first or in parallel. Its answers may change rules, and any change needs review and a freeze before qualification. |
| O37 | Who runs CPS on each job after setup? | "The Dot runs it" | A ChatGPT Dot, working from a curated Google Drive folder, interviews the creator and then runs CPS jobs. |

**Consequence (orchestrator).** All trial evidence so far used `claude-opus-5-5` as the generator, and scores do not carry across models (AGENTS.md: each run records its model and runtime). So the qualification outputs must be generated by the Dot's runtime, in fresh contexts that hold only the package and the packet. Evaluation stays a separate role.

The route, inventory builders, job-config and scope tools are pure Python. View rendering, the export writer and saved QA need Node (the writer admission pins one node binary), and visual QA needs LibreOffice. The runbook therefore starts with an environment check. When the Dot's sandbox lacks those tools, the Dot runs generation and the route checks, and a tools environment (for example a Claude Code session on this repository) runs packet building, export and QA.

The interview materials hold historical 未填 rows. They are kept apart from the runtime folder, and a generation run must never open them.

## O38 (2026-11-05): the delivered workbook in the creator's own format

**Owner instruction**, on the v2.6 re-exports: "1.未填 inside the excel title should be in brackets like this (未填) 2. Where are the cells? Lines of the excel cells are gone 3. Why is the Column C fixed and D plus latter columns has side scroll. Just keep regular the excel format. 4. Remove three of the sheets, in outputs they are no necessary Fix these issues and show me the excel sheets before upload".

**Diagnosis.**
- (1) The file and sheet names already ended in `(未填)`, with the half-width brackets the creator uses. The one name affected is the 31-character sheet-name cut: Excel's limit forces the cut on long names, and the cut keeps `(未填)`. No other place was found, and the owner was asked to point to one if it exists.
- (2) The writer turned gridlines off (writer004 `formatSheet`).
- (3) The writer froze row 1 and columns A–C (writer004 `freezeRows(1)` and `freezeColumns(3)`). The creator's files freeze the header row only.
- (4) The workbook held three review sheets besides the 未填 sheet.

**Previews.** Four one-sheet previews were built from the four v2.6 samples in the creator's format, taken from her recent 未填 files: 新細明體 12; grey `#C0C0C0` header with thin borders; gridlines shown; only the header row frozen; no wrapping; E, F, L, M, N, Q centred and C left; header row 23.25 pt and body rows 20.45 pt; column widths the medians of seven of her files. Page images were rendered from them.

**Owner answer:** "Looks good, approved".

**Effect (writer v2.7, saved_qa v6, visual_qa v4).**
- With a job title, the delivered workbook `<name>.xlsx` is one sheet `<name>` in exactly the approved format. Its values are the main sheet of `EXPECTED_SAVED_VALUES.json`, as before.
- The v2.6 four-sheet workbook is kept as `INTERNAL_QA_WORKBOOK.xlsx`, with the same bytes, for saved QA and internal review. It is never delivered.
- Saved QA checks the delivered workbook too: its package, its three readers against the main sheet, its format and its rerun bytes.
- Visual QA renders the delivered workbook with printed gridlines. It lists no-wrap cells whose text may not show in full (`possibly_cut_cells`).
- Her second sheet, 原材料清單, is not added. Whether CPS should add it is survey question DOT-09.
- The writer v2.7 deliverables of the four samples have zero cell, style, width and height differences from the approved previews.

## O39 (2026-11-06): column widths in the delivered workbook

**Finding.** In the 046g development trial, two delivered workbooks were reviewed visually. Both failed: some values were cut at the column edge. In one job the first character of every 使用客戶 cell was cut and one 型號 cell lost its last character; in the other, two 單位 cells were cut (a unit followed by eight spaces, kept verbatim from the source). The stored values were intact (saved QA passed). The cause is the fixed O38 widths.

The creator's own files show the same effect, and she sets widths per job. Across 46 of her 未填 files, text is wider than her column in 403 of 4,782 規格 cells (15 files) and 88 of 2,685 材料名稱 cells (6 files); 使用客戶 is 13 wide in one file and 27.4 in another.

**Question to the owner:** widen to fit, or keep the widths exactly and accept cut text?

**Owner answer:** "Widen to fit (Recommended)": keep the approved widths as the minimum, and widen a column only when a value in it would be cut, just enough to show it in full.

**Effect (writer v2.8, saved_qa v6.2, visual_qa v4.2).**
- **Width rule.** Each column's width is the larger of its O38 width and the widest value in it, header included, capped at Excel's 255. The value estimate is counted in tenths of a column-width unit: 23 per non-ASCII character, 22 per M W m w @ %, 18 per other ASCII capital, 14 per other ASCII character, plus 10.
- **Counts of writer v2.8.2 (after the delta review of v2.8.1, F1).** A non-ASCII character that is not East Asian wide or full-width (Ⅷ ① ‰ ℃ × …) counts 27. The other counts below are unchanged.
  - **Coverage claim.** It covers every Big5 character and the printable ASCII, as measured in both LibreOffice environments. The widest is Ⅷ at 2.53 units (maintainer environment).
  - **Recorded limitation.** A few characters outside Big5 are wider than their count: ⸻ ⸺ ‱, long arrows, emoji and a few symbols (README, O39). The PNG review is the check for them.
  - **Tiles.** visual_qa v4.4 also cuts each delivered page into tiles, so that the visual reviewer sees the text at full size.
- **Calibration (corrected after the independent review of v2.8, R1/R2; counts of writer v2.8.1).**
  - The counts are 24 per non-ASCII character, 22 per M W m w @ %, 18 per other ASCII capital and 15 per other ASCII character, plus 10.
  - Each count covers the widest character of its class measured in the v2.8 configuration on invented workbooks. The Dot toolchain (unit 7.00 pt): ‰ 2.30, `#` 1.43. The maintainer environment (unit 7.10 pt): ① 2.35.
  - Excel is computed for full-width characters only: 2.29 units with a 7-pixel default digit, the less favourable assumption.
  - The fixed headers 需要日期 and 合約價 widen O and Q slightly (10.6, 8.2) in every deliverable.
- **Default font.** The workbook default font (fonts[0], the Normal style) is 新細明體 11, as in all 46 of her files. Excel converts column-width units to pixels with this font's digit width, so the delivered columns get her pixel widths. This was the maintainer's addition. The owner confirmed it on 2026-11-06 ("Keep 新細明體 11 (Recommended)"), after being told the columns may look up to about 14% wider in Excel than in the approved previews, matching her own files more closely.
- **Checks.** Saved QA recomputes the expected widths from `EXPECTED_SAVED_VALUES.json` with its own copy of the rule. Visual QA's `possibly_cut_cells` uses the same estimate.
- **What does not change.** Every other O38 property. `INTERNAL_QA_WORKBOOK.xlsx` and the untitled outputs keep their bytes.
- **Not changed by O39.** The values themselves. A unit with trailing spaces stays verbatim under R57; its column is widened. Whether such outer spaces should be trimmed is a 046h backlog item.

## O40 (2026-11-06): evidence of generator isolation in qualification

**Question to the owner.** Each qualification run must be shown to have seen only the allowed inputs: the rule package and that job's packet. Earlier audits used each generator's full transcript. The Dot starts those generator conversations itself and may not be able to export full transcripts. What should count as evidence for each run?

**Owner answer:** "Attested record (Recommended)".

**Effect.**
- **The record.** For every qualification run the runner freezes a generation record:
  - the model;
  - the conversation id or share link;
  - the start and end times;
  - the prompt sha256;
  - the tools or features enabled;
  - the final message;
  - `transcript_status`.
- **Transcripts.** The transcript is added and pinned when the Dot can export one; otherwise it is marked `not_available`. Qualification accepts either.
- **Reporting.** The qualification report states how many runs had transcripts.
- **Scope.** The decision is about the evidence of isolation. It does not change the isolation rules themselves.

## O41–O42 (2026-11-06): a static CPS folder, per-user preferences, and qualification on 046g

**Owner's instruction (verbatim):** "This CPS is meant to be the static project folder, the survey and any future instructions are designed to be standing personal preferences inside dots folder different for each user. Make the necessary final file edits and make these instructions clear in the docs. CPS will only return to you for system failures or bugs."

**O41. Question to the owner:** how should a user's standing preferences reach the files they receive?
**Owner answer:** "Dot personalizes a copy (Recommended)".

**Effect.**
- **The CPS folder is static.** The Drive folder "CPS" holds the released system: rules, tools, runbooks and release status. It is the same for every user. Only the maintainer changes it, through a new release. The Dot only adds files where a document says so: `setup/`, `qualification/`, `reports/` and the phase-1 example images.
- **CPS output is the same for everyone.** Every job produces one standard 未填 file, checked by saved QA and visual QA, and kept unchanged in the job record.
- **Preferences belong to each user.** Each user's survey answers and later standing instructions are kept in their own profile folder in the Dots folder, outside CPS (`CPS_PREFERENCES.md`). They are never CPS rules, never sent to the maintainer, and never applied to another user.
- **The personal copy.** For an everyday job, after the delivery check names the standard file, the Dot copies it and applies the requesting user's standing preferences.
  - A change may only use values from the standard file, the job inputs or the preference text.
  - Every change is logged in `PERSONALIZATION_LOG.json` (`cps.personal-copy-log.v1`), with the standard file's sha256 and the profile's sha256, and checked cell by cell against the standard file.
  - The user receives the personal copy.
- **Qualification measures only the standard file.** No preferences, personal copies or survey answers enter a qualification job.
- **No survey-driven rule change.** Survey answers no longer feed a new rule candidate. `PLAN_046h.md` is superseded as a survey plan (see its header). A later candidate is built only to fix a reported system failure or bug.

**O42. Question to the owner:** with preferences outside CPS, should qualification still run before everyday use, and on which rules?
**Owner answer:** "Keep qualification (Recommended)".

**Effect.**
- **What qualification runs.** The frozen rules 046g, the admitted writer v2.8.2 (ADMISSION_WRITER_V28.json) and runner v4 (ADMISSION_RUNNER_V4.json), on the Dot's admitted VM. The bar is unchanged (O12, O31).
- **Scoring.** The maintainer scores the frozen runs once, in a separate evaluation role, with the frozen evaluator v4 and gate aggregator v2. `RELEASED_FOR_USE` is set only on a pass.
- **After that, the maintainer is involved only for failures or bugs.** The Dot's documents name the only hand-backs:
  - A, the setup report, once;
  - B, qualification generation complete, once;
  - C, a system failure or a bug, any time, with evidence uploaded to `reports/`.
- **What counts as a bug** is defined in the Dot's `07_MAINTAINER_HANDBACK.md`:
  - a runner stop it cannot explain;
  - a stage failure on a normal job;
  - a standard file wrong against its source;
  - a broken tool;
  - a document that does not match the system.
  A difference from what a user prefers is not a bug. It stays a standing preference.
- **Not changed.** The exclusions, WT-A5 closure, the 38 reserved projects, the deployment thresholds and every frozen output.
