# CPS — Contract Parsing System

CPS researches how to turn an original contract into a **未填** worksheet: a supply list that drafters can later modify into **已填**, using the required 17-column format.

**Current state: paused after checkpoint 045; not ready for deployment.** The owner requested the pause after that segment. This repository upload is a handoff, not authorization to resume development or scheduled runs. Snapshot date: **2026-11-02, Asia/Taipei**.

## Start here

1. Read [AGENTS.md](AGENTS.md) and [CURRENT_STATE.json](CURRENT_STATE.json).
2. Read [current status](docs/handoff/CURRENT_STATUS.md), [evaluation and deployment bar](docs/handoff/EVALUATION.md), and [decisions](docs/handoff/DECISIONS.md).
3. Read the [contract-to-未填 guideline](docs/policy/GUIDELINE_V4.md), [source and eligibility rules](docs/policy/SOURCE_AND_ELIGIBILITY.md), and [RQA requirements](docs/policy/RQA.md).
4. Use the [architecture](docs/implementation/ARCHITECTURE.md) and [local setup](docs/implementation/LOCAL_SETUP.md) to locate the installed baseline and later research route. They are different implementations.
5. After an explicit instruction to resume, follow the [resume plan](docs/handoff/RESUME_PLAN.md). It preserves the reviewed PLAN71 direction; it does not revive expired experiment permissions.

## Latest measured result

Checkpoint 045 tested two separate readings of one complete contract. These were **source-only checks**, not comparisons with a verified historical 未填 pair.

| Measure | Reader A | Reader B |
| --- | ---: | ---: |
| Correct core fields | 155/176 (88.07%) | 147/176 (83.52%) |
| Required threshold | 99% | 99% |
| Item, unit and quantity coverage | 47/47 each | 47/47 each |
| Mandatory manual obligations passed | 9/12 | 9/12 |
| Source-only case passed | No | No |

Saved-workbook and scoped visual checks passed, including one exact-input assembly repeat. They do not substitute for source correctness. No historical pair has yet passed the programme's performance bar. There is one independently eligible development pair and zero eligible reserved pairs. All **38 reserved answers remain closed**.

The main remaining defects are name/specification allocation, unsupported field use, exact raw-value representation, and required nonitem coverage. The numeric/blank representation defects did not change source quantities, and cells missing from the nonitem collection were still present as item anchors. See the [preserved cycle report](docs/evidence/CYCLE_045.md) and [aggregate metrics](docs/evidence/METRICS_045.json).

## What this repository contains

- Agent instructions, current state, decisions, evaluation rules, the next bounded plan, and a local evidence map.
- Exported baseline and research code, with original/export hashes and any publication adaptations recorded.
- Policy and RQA guidance, with the distinction between general questionnaire rules and CPS-specific source restrictions.
- Aggregate evidence and a publication inventory. Historical failures remain failures.

Original contracts, customer documents, mailbox archives, raw respondent answers, historical target worksheets, and reserved answers are not published here. The code and documentation explain how to resume, but reproducing real-case scores also requires authorized access to the private evidence and original runtime dependencies. See [publication scope](PUBLICATION_SCOPE.md). This repository does not install a production service or enable GitHub Pages.

No CPS execution, model test, or refinement cycle was run for this handoff. Packaging validation covers the files being published, not the system's deployment readiness.

To verify the published snapshot without running CPS, use Python 3.9 or newer: `python -B tools/verify_handoff.py`. This only checks the listed file hashes, JSON, local document links, and recorded pause. Later intentional repository edits require a new publication manifest; they must not overwrite the original local evidence.
