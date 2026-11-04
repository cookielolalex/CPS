# Independent review of candidate 046f (2026-11-04)

**Status: semantically and interface-approved, then frozen (manifest `5f5502a7117e734c5a2f999227c6f0a8a95927c7dce959d28f11e11dbb620467`, 16 files). Not admitted.**

Candidate 046f recalibrates CPS so that it reproduces the historical 未填 creator's majority practice. It follows owner decisions O10–O20 (`research/guideline046_005/DECISIONS_OWNER_*.md`) and the generic studies `STUDY_*_20261104.md`.

## What 046f adds

| Rule | Content |
|---|---|
| R47b | One bound source: the 材料清單 when present, otherwise the contract |
| R48 | L, M and N come from job inputs |
| R49–R51 | Quoted range, which lines become rows, analysis components as rows |
| R52–R53 | The C/D procedure and rating-token spacing |
| R54 | Q is the unit price |
| R55 | I/J taken from the source; the brand table is used only on contract jobs |
| R56 | The enclosure row, carried by a one-row `physical_enclosure` group |
| R57–R58 | The remaining field and evidence rules |

Route v4.2 adds three documented relaxations, each mirrored in portable writer v2.2:
- job-input evidence for L/M/N;
- C-null rows allowed as `research_draft`;
- Q accepted under unverified adoption.

It also adds invalid checks on job inputs, the K/O/P blanks, the company name and enclosure groups.

## Reviewer

One fresh context, observed model `claude-opus-5-5`. It is independent of the package author and of the three engineering rounds.

## Rounds

| Round | Verdict | Findings and resolution |
|---|---|---|
| 1 | SEMANTIC_APPROVE_AFTER_LISTED_FIXES | **B1:** the brand table must apply only when no 材料清單 exists (O17). **B2:** the evaluator brief counted correctly excluded zero-state lines as critical. **S1–S12:** segment definition, acronym scope, an exhaustive equipment list, rating-token definition, range boundaries, the component range, the enclosure definition, the O10 "inside" definition, brand-only and model-only lines, stale text, and route enforcement of L/M/N, K/O/P, J company name and one-member enclosure groups. All applied in round 3 (commit 7b7b5f0). The reviewer's probes, including M from a letterhead and K from a footer, now reject. |
| 2 | SEMANTIC_APPROVE_AFTER_LISTED_FIXES | Two R52 wording gaps: the acronym step dropped trailing text, and a noun segment starting with a digit token was mishandled. Applied with the reviewer's wording, plus examples N31–N33. Notes applied: a C/D evidence note (`STUDY_CD_FOLLOWUP_20261104.md`); protocol tokens placed in D by R52, with evaluators free to declare both (O9); and an admission gate requiring `policy_checks: applied`. |

## Checks before freezing

| Check | Result |
|---|---|
| Route tests | 221/221 (reviewer and author) |
| Export tests | 224/224 with visual QA (reviewer) |
| EXAMPLE | `check` PASS on route v4.2, `policy_checks: applied`, with the three documented warnings |

## Residual risks

- **The A12 boundary (owner-supplied panel contents) stays open for the owner.** Evaluators declare both readings.
- **Unmarked block omissions by the creator cannot be predicted.** The 材料清單 study found them in 9 of 39 cases.
- **The company tables are DRAFT_NOT_OWNER_APPROVED** until the owner reviews them. They affect only C, which is outside the governing score, and contract-only jobs.
