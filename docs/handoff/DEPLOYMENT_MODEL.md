# CPS deployment model (owner decisions O36, O37, O41, O42, O43–O61; 2026-11-06, extended 2026-11-09 and 2026-11-10)

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

## VM resets and the maintainer's messages (O43–O53, 2026-11-09)

The Dot's VM keeps nothing across a reset; only Google Drive persists.
- On 2026-11-09 the owner approved OD-1 to OD-10 of [RESET_PROOF_DESIGN_DRAFT.md](RESET_PROOF_DESIGN_DRAFT.md) as recommended, recorded as O43–O52:
  - evidence goes to Drive per run, as it is made;
  - a lost step without AI may run again, bound to any result already seen;
  - an AI conversation that provably wrote nothing may restart once, under rule 3;
  - a written AI output that is lost counts as a failure;
  - any VM whose fingerprint passed the self-test is admitted;
  - all page PNGs are kept;
  - everyday-job records go to an owner-only folder;
  - if new conversations cannot use the VM, everything waits;
  - runner v5 is never swapped in mid-qualification;
  - the owner compares the conversation list with the Dot's notes before scoring.
- Qualification stays blocked until the helpers G1 are built, reviewed and admitted, the probes P1–P4 pass, and a reset drill passes.
- **O53:** the maintainer may edit the Dot's folder. Instructions reach the Dot as `CPS/maintainer_messages/Mnnn_*.md` when the owner says "mail", and the Dot replies in `reports/Mnnn_*/REPLY.md`.
- Every file the Dot downloads from the CPS folder is first checked with `deploy/verify_drive_files.py` against `FOLDER_MANIFEST.md`, because the maintainer's uploads can carry base64 slips.
- The "mail" route did not work: no Dot document mentioned the mailbox. Since 2026-11-09 the owner pastes each maintainer message to the Dot; a record copy stays in `CPS/maintainer_messages/`, and replies still go to `reports/Mnnn_*/`.

## VM helper v2 rules (O54–O61, 2026-11-10)

Admission review 1 rejected helper v1 (`deploy/vm/ADMISSION_VM_HELPER_V1.json`). On 2026-11-10 the owner approved Q1–Q8 of [VM_HELPER_V2_DESIGN.md](VM_HELPER_V2_DESIGN.md) section H as recommended, recorded as O54–O61:
- **O54:** no result is shown before it is saved and confirmed on Drive; a saved result binds any re-run; an unsaved one was never shown, so its step re-runs unbound and logged (how O44 is met).
- **O55:** without transcript export, the Dot's own reading that an interrupted conversation wrote nothing may allow the one restart, flagged for the owner to check that conversation before scoring; a write found fails that reader's case.
- **O56:** every interrupted conversation's transcript is kept on Drive, including ones whose output was lost.
- **O57:** a reset during a visual reviewer's completion of an unfinished review fails visual QA for that run, with no replacement reviewer.
- **O58:** a fresh START is allowed once per attempt, only if no conversation was opened and the Dot's conversation list shows none; the gap is listed on the O52 sheet.
- **O59:** the maintainer may clear a helper halt with a settings-only kit naming exactly that halt; no code, rule or scoring change.
- **O60:** everyday jobs resume from the last saved step without limit; "prepared again once" (O49) counts only starting over from the inputs.
- **O61:** a visual reviewer may be asked to complete an unfinished review at most twice; a third time fails visual QA.
