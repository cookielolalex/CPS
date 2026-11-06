# CPS deployment model (owner decisions O36, O37, O41, O42; 2026-11-06)

This page says how CPS is deployed and who owns what. The operating documents themselves are in the private Drive folder "CPS" (in "Dots Folder"). They are not published here because the interview material holds company data.

## The parts

| Part | Where | Owner | Changes when |
|---|---|---|---|
| **CPS folder** | Drive "Dots Folder" → "CPS" | The maintainer | A new release, published by the maintainer |
| **Job runs** | The Dot's VM, `<jobs root>/<case id>/` | The Dot | Every job; each folder is never edited after it is written |
| **User preferences** | Drive "Dots Folder" → `<user profile folder>/CPS_PREFERENCES.md`, outside CPS | The Dot, with that user | The starting survey, then each standing instruction the user confirms |
| **Personal copies** | The Dot's VM, `~/cps-deliveries/<case id>/<user>/<time>/`, with `PERSONALIZATION_LOG.json` | The Dot | Every delivery |

- **The CPS folder is static (O41).** It holds the released system: the operating documents, the interview question bank, the release status and the runtime files. It is the same for every user. The Dot only adds files where a document says so:
  - `setup/`;
  - `qualification/`;
  - `reports/`;
  - the phase-1 example images.
- **The standard file.** Every CPS job produces one standard `<name>(未填).xlsx`, checked by saved QA and visual QA, and kept unchanged in the job folder.
- **Preferences are personal.** A user's survey answers and later standing instructions are that user's preferences:
  - They never change CPS rules, tables, the package or runtime files.
  - They are never sent to the maintainer, and never applied to another user.
- **The personal copy.** For an everyday job, once `deliver-check` names the standard file, the Dot copies it and applies the requesting user's preferences.
  - A change may only use values from the standard file, the job inputs or the preference text.
  - Each change is logged (`cps.personal-copy-log.v1`), with the sha256 of the standard file and of the profile.
  - The copy is compared cell by cell with the standard file.
  - The user receives the personal copy. The standard file stays in the job record.

## Phases

1. **Setup.** The Dot installs the pinned tools without root, runs the environment check and the export self-test, and uploads the reports to `setup/`. The maintainer admits the VM's node binary and publishes `RELEASED_FOR_QUALIFICATION` (hand-back A).
2. **Qualification (O42).** The Dot runs the qualification jobs on CPS exactly as released:
   - the frozen rules 046g;
   - the admitted writer v2.8.2 (`research/export/ADMISSION_WRITER_V28.json`);
   - runner v4 (`deploy/run/ADMISSION_RUNNER_V4.json`);
   - two readers, fresh conversations, and no preferences.

   It freezes every run and uploads the archive (hand-back B). The maintainer scores the runs once, in a separate evaluation role, with the frozen evaluator v4 and gate aggregator v2. It sets `RELEASED_FOR_USE` only on a pass. The bar is unchanged (O12, O31).
3. **Everyday use.** Each job runs through the runner. The Dot then sends the requesting user their personal copy.

The starting survey and new-user onboarding can happen at any time. They never affect qualification.

## When CPS returns to the maintainer

Only in three cases:
- **A**, the setup report (once);
- **B**, qualification generation complete (once);
- **C**, a system failure or a bug, at any time.

Case C covers:
- a runner stop the Dot cannot explain;
- a stage failure on a normal job;
- a standard file that is wrong against its source;
- a broken tool;
- a document that does not match the system.

The Dot uploads the evidence to `reports/` and the owner pastes the prompt into a maintainer session. A difference from what a user prefers is not a bug: it stays a standing preference. The maintainer answers a bug with a fix, its tests and review, and a new release. Survey answers no longer feed a new rule candidate (`research/guideline046_008/PLAN_046h.md` is superseded as a survey plan).

## Not changed

- the exclusions and WT-A5 closure;
- the 38 reserved projects, closed until all qualification outputs are frozen;
- the deployment thresholds;
- every frozen output.
