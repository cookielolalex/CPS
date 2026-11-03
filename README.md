# CPS — Contract Parsing System

CPS turns authorized contracts into a17-column **未填** draft for drafters. The deployment product is a **Markdown guideline with supplementary resources followed by an AI agent**, with tools for source reading, validation and workbook export.

**2026-11-03 handoff: candidate046a is prepared; independent review and fixes are incomplete. CPS is not deployment-ready.** The previous chat was interrupted before new model tests on1140908 or1141208. Publishing this snapshot does not run CPS or restart the paused automation.

## Continue from here

1. Read [AGENTS.md](AGENTS.md), [current state](CURRENT_STATE.json) and [current status](docs/handoff/CURRENT_STATUS.md).
2. Read the [candidate guideline](research/guideline046_001/package/CPS_GUIDELINE.md) and its pinned supplementary resources. The proposed source-reference adapter has not been implemented.
3. Read the [naming study summary](docs/handoff/NAMING_STUDY.md), [preliminary review findings](docs/handoff/INTERRUPTED_REVIEW_046.json) and [next steps](docs/handoff/RESUME_046.md).
4. Use the [handoff prompt](docs/handoff/HANDOFF_PROMPT.md) and [resource bundle guide](docs/handoff/RESOURCE_BUNDLE.md) with the separately supplied private ZIP. That ZIP contains selected originals, historical evaluation targets, saved outputs, source/evaluator evidence and local working files for four projects.

## Latest actual performance

Checkpoint045 remains the last completed model test. On1140908 its two readers scored155/176(88.07%) and147/176(83.52%) source-core fields, below99%. Saved/visual checks passed; source performance failed. There are1eligible development pair,0eligible reserved pairs and0performance-passed historical pairs. All38reserved answers remain closed. The candidate's33 authoring checks verify package consistency and do not create a new accuracy result.

The repository includes the previously published baseline/research code, policy and deployment bar, plus the new12-file generic candidate and current continuation docs. [Older045 evidence](docs/evidence/CYCLE_045.md) and historical plans remain preserved. Where an older file says the programme is paused after045, use the current state and046handoff for the later history.

## Private data

The user selected **private project evidence in the downloadable ZIP; code and documentation on public GitHub**. Original contracts, prices, real worksheet rows, images, historical targets, raw reader responses and factual evaluator expectations are excluded from this repository. Case identifiers and aggregate metrics remain documented. Credentials, API keys, authentication/configuration files and mailbox archives are excluded from both packages.

Verify publication files with `python -B tools/verify_handoff.py`. This checks hashes, JSON and document links without executing CPS. See [publication scope](PUBLICATION_SCOPE.md). A GitHub clone alone cannot reproduce real-case scores; use the private ZIP and its resource map under the source/evaluation separation rules.
