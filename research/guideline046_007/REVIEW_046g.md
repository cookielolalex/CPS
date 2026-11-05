# Independent semantic review of candidate 046g (2026-11-05)

**Status: round 1 returned SEMANTIC_APPROVE_AFTER_LISTED_FIXES. Fixes are being applied. 046g is not frozen and not admitted.**

## Scope

The candidate adds three things:
- **R59 scoped packets** for large workbooks: BILL1, a fresh-context scope reader, an agreement check, the scoped inventory and route v4.3.
- **R56 enclosure A/B rewritten under O30:** A/B on the enclosure row only; A from a panel heading, or else from the line's own enclosure noun phrase, with tags kept; B only from W/H/D in the line's own description.
- **Evaluator references moved to the frozen v3** (O23, O24).

The evidence behind the changes is in `research/guideline046_005/STUDY_LARGE_MATLIST_STRUCTURE_20261105.md` and `STUDY_ENCLOSURE_20261105.md`.

## Reviewer

- One fresh general-purpose context, independent of the author.
- Inputs: the public repository and the two studies.
- Not read: private data, targets, outputs and the web.

## Round 1: SEMANTIC_APPROVE_AFTER_LISTED_FIXES

**Checks run by the reviewer:**
- route tests 284/284;
- scope-stage tests 56/56;
- route `check` on the package example: PASS, with `scope: not_applied`;
- v4.2 parity without `context:scope`: identical apart from the route string and `scope`, and the census ledger byte-identical;
- manifest hashes match;
- the R13 gate holds on the example and on synthetic cases A18–A46 as written.

**Blocking**
- **B1. The R56 heading test misfired on common headings.** Work words were kept (控制盤工程 gave A = 控制盤工程). 盤體 and 盤內 were read as a box. "Contains" in the category clause dropped the panel noun. The fix gives a closed definition of a box noun, and of a panel name that must end with its only box noun. Trailing 設備, 工程, 製作, 更新 and enclosure counts are removed (open question Q1).

**Open questions decided**
- **Q1, trailing work words:** stripped, together with B1.
- **Q2, the engineer's completions:** accepted, with clarifications.
- **Q3:** a panel heading names the first enclosure row in its scope that is not a meter, terminal, test, isolation or instrument box.

**Should-fix**
- **S1:** the O31 pooled reading in the evaluator brief and the checklist, using the frozen aggregator.
- **S2:** a tag is never lost.
- **S3:** a tag written after the noun is kept.
- **S4:** component rows take only their block title.
- **S5:** every leading category segment is dropped.
- **S6:** the hyphen rule.
- **S7:** type parentheses.
- **S8:** 附/含 accessory boxes.
- **S9:** B precision (unit, order, labels).
- **S10:** the enclosure list is not exhaustive.
- **S11:** whether an unpriced parent panel line counts as a heading. This is to be checked against the creator's data before adoption.
- **S12:** R59 added to `OUTPUT_CONTRACT.md`.
- **S13:** a stand-in scope decision can never become admissible.
- **S14:** validation of the scope tool on the study's five inventories, and a replay of the revised R56 on the study's exposed cases.
- **S15:** BILL1 wording.

**Notes N1–N8**
- Wording: R11 against R59 after the end row; workbook-size dependence; the limits of the scope reader's independence; stale references to v4.2.
- R52 C/D items deferred (N7).
- A dev-trial watch item: two panel sections with no heading between them (N8).

## Next

1. Apply the fixes in the reviewer's wording.
2. Run an evaluation-role replay of the revised R56 on the 15 exposed source cases. It decides S11, and checks that the agreement still holds (47/65 A and 26/28 heading-derived before the revision).
3. Delta review, then freeze.
4. Run a dev trial on the five large exposed tuning cases, with a real scope reader, plus a regression on the four current-template dev cases under evaluator v3.
