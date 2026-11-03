# CPS — Contract Parsing System

CPS turns authorized contracts into a17-column **未填** draft for drafters. The deployment product is a **Markdown guideline with supplementary resources followed by an AI agent**, with tools for source reading, validation and workbook export.

**2026-11-03, after the 046b trials:** candidate 046b and its reviewed source-reference adapter were tested on 1140908 (exposed regression) and 1141208, two readers each. Neither case passed. 1140908 scored A 141/176 and B 140/176, a regression against 045's 155 and 147. On 1141208 both readers reached 107/107 in the governing declared-alternatives mode, but both failed a mandatory obligation. See [046b results](docs/handoff/RESULTS_046B.md) and [next steps](docs/handoff/RESUME_047.md). CPS is not deployment-ready.

**Portable handoff verified:** use the [offline continuation guide](docs/handoff/PORTABILITY.md) and the revised private ZIP. No original Data Center folders are needed for the next two source-only cases.

## Continue from here

1. Read [AGENTS.md](AGENTS.md), [current state](CURRENT_STATE.json) and [current status](docs/handoff/CURRENT_STATUS.md).
2. Read the [046b results](docs/handoff/RESULTS_046B.md) and [next steps](docs/handoff/RESUME_047.md).
3. The current candidate is [046b](research/guideline046_002/package/CPS_GUIDELINE.md), with its [reviews](research/guideline046_002/REVIEW_046b.md), [decisions](research/guideline046_002/DECISIONS_046b.md), adapter `research/guideline046_002/package/tools/cps046b_route.py`, and the trial harness in `research/guideline046_002/harness/`. Candidate 046a stays preserved for comparison.
4. Private evidence: the original `CPS_handoff_20261103_portable.zip`, plus the session results ZIP `CPS_046b_results_20261103_PRIVATE.zip` (packets, frozen expectations, responses, carriers, comparisons, manual reviews, transcripts). Never pass expectations or prior outputs to a generator.

## Latest actual performance

The latest model tests are 046b (observed model claude-opus-5-5; the proposed sol6.1/xhigh could not be selected).

- 1140908 canonical core: A 141/176 (80.11%), B 140/176 (79.55%), below the 99% bar and below 045 (155/176, 147/176).
- 1141208: A and B both 107/107 in the governing declared-alternatives mode (canonical: A 107, B 105). Both failed the source-case gate on one mandatory obligation.
- Raw, census and pairing mechanics were clean, with 0 critical errors.
- Saved-workbook QA and visual QA were not attempted.
- There remain 1 eligible development pair, 0 eligible reserved pairs and 0 performance-passed historical pairs. All 38 reserved answers remain closed.

The repository includes the previously published baseline/research code, policy and deployment bar, plus the new12-file generic candidate and current continuation docs. [Older045 evidence](docs/evidence/CYCLE_045.md) and historical plans remain preserved. Where an older file says the programme is paused after045, use the current state and046handoff for the later history.

## Private data

The user selected **private project evidence in the downloadable ZIP; code and documentation on public GitHub**. Original contracts, prices, real worksheet rows, images, historical targets, raw reader responses and factual evaluator expectations are excluded from this repository. Case identifiers and aggregate metrics remain documented. Credentials, API keys, authentication/configuration files and mailbox archives are excluded from both packages.

Verify publication files with `python -B tools/verify_handoff.py`. This checks hashes, JSON and document links without executing CPS. See [publication scope](PUBLICATION_SCOPE.md). A GitHub clone alone cannot reproduce real-case scores; use the private ZIP and its resource map under the source/evaluation separation rules.
