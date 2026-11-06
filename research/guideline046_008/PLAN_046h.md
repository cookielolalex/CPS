# Plan for candidate 046h (draft, 2026-11-06)

> **Superseded as a survey plan (2026-11-06, owner decisions O41 and O42).** Survey answers and later instructions are each user's standing preferences. The Dot applies them to that user's personal copy of the standard file. They do not change CPS rules. Qualification runs on the frozen 046g. No survey-driven 046h will be built. A later candidate is built only to fix a reported system failure or bug. The plan below is kept as written, as a record. Its section B findings are kept as a backlog for that case. See `research/guideline046_005/DECISIONS_OWNER_O23_O25.md`, O41–O42.

046h is the next candidate after frozen 046g. Its purpose is to fold in the creator's survey answers (the Dot's hand-back, `04_handback/HANDBACK.md`) and the generic findings of the 046g development trial (`docs/handoff/RESULTS_046G_DEVTRIAL.md`).

It is the candidate that qualification will run. So it is built, reviewed and frozen once, after the survey, and its route tests and harness are re-run before the qualification release.

This plan lists the changes in advance, so the post-survey work is mechanical. Nothing here is a rule yet.

## A. Survey questions and the rules each answer sets

| Survey | Rule(s) | What the answer decides | Dev-trial positions at stake |
|---|---|---|---|
| DOT-01 不含估價 lines | R49, R55 (I/J `不含估價`) | whether not-estimated lines are rows, and whether I/J carry `不含估價` | 15 (I/J blank by the creator), part of 40 unpaired |
| DOT-02 rows carrying A/B | R56, O30 | the enclosure row only, or every row of the panel's group | panel-level (scored once per panel, O35) |
| DOT-03 B without a size in the 材料清單 | R56 (B source) | an empty B, or a size from another stated source | 25 (A or B not derivable) |
| DOT-04 how A is named | R56 (A boundary and form) | heading, panel tag or box noun | within the 25 above |
| DOT-05 owner-supplied panel with priced contents | R50, O10 | the two O10 readings | none in the trial |
| DOT-06 N wording | R48 (N from the job input) | the form of the project name in N | within 22 (K–O) |
| DOT-07 breaker brand on contract-only jobs | R58, O18 | the brand-table fallback | contract-only jobs only |
| DOT-08 abbreviation or Chinese for some devices | R52, O20, O27 glossary | including the acronym-only C (the cross-reader difference on NFB/ELCB) | description (not gating); alignment |
| DOT-09 the "-" after the customer short name | O33 (file and sheet name) | the name derivation | none (naming) |
| DOT-10 rows carrying L/M/N | R48 | the first row only, or every row | within 22 (K–O) |
| DOT-11 M full name or short name | R48, O13 | the form of M | within 22 (K–O) |

Each answer is stored verbatim as a standing preference. A rule changes only where the answer is clear. An answer marked "unsure" leaves the rule unchanged and is recorded as such.

## B. Generic findings outside the survey

1. **R52 category-word gap** (046g deferred item N7).
   - **Problem.** A first segment that the glossary does not list as a category word blocks the glossary step. The creator's abbreviation then does not pair, and on a not-estimated line the v3 gap fill cannot pair the row (it has no identity field outside C/D). Of the 40 unpaired positions, 8 trace to this.
   - **Change.** It needs new category words in the glossary, which is an O27 table change. That needs the owner's approval, together with the DOT-08 answer.
2. **Templated null reasons.**
   - **Problem.** On one case, two I null reasons named a remark that the row does not have. The values were right, but obligation OB13 was missed.
   - **Change.** The generator prompt and OUTPUT_CONTRACT must say that a null reason states only what the cited cells show.
3. **R56 A boundary with two enclosure words in one segment.**
   - **Problem.** A meter-box segment ending in 箱體 holds two enclosure words, and the rule's wording is ambiguous for it (1 position). The generator disclosed the alternative.
   - **Change.** Fix the wording, with an invented example.
4. **Outer spaces in a value.**
   - **Problem.** A 單位 cell was a unit followed by eight spaces, kept verbatim under R57. The evaluator trims outer spaces, so no position was lost. Writer v2.8.1 widens the column, so nothing is cut.
   - **Decision for 046h:** whether field values trim outer ASCII and full-width spaces (the raw selection keeps the original).
   - **What her files show.** Her own values almost never carry outer spaces. Across 46 of her 未填 files, outer ASCII or full-width spaces are on:
     - 4 of 5,176 單位 values (3 files);
     - 8 of 2,685 材料名稱 values;
     - 18 of 4,782 規格 values;
     - 26 of 3,478 型號 values;
     - 27 of 3,818 廠牌 values.
   - **Recommendation:** trim. The evaluator trims outer spaces anyway, so the score does not move.
5. **Acronym-only C.** One reader set C to the acronym on a line whose only noun is a Latin acronym (NFB, ELCB); another set C to null. O20 says "acronym alone in C". The R52 text must make this unambiguous. The DOT-08 answer may refine it.

## C. Process after the survey

1. Read the hand-back and the profile answers. Map each answer to section A, and record it as an owner decision (O41 and on). Ask the owner only where an answer is unclear.
2. Build `research/guideline046_008/package` from 046g with the changes of A and B. Re-run the route tests and the scope tests, and add invented examples for every changed rule.
3. Independent review of 046h against 046g. Apply the listed fixes, then freeze.
4. Re-run a development regression on the exposed tuning cases with a fresh generator. It earns no qualification credit, and only confirms that nothing regressed.
5. Write the qualification admission (runner v2 design) pinning the 046h package, runner, harness, source prep, writer admission v2.8.1, evaluator v4, aggregator v2 and `JOBS.json`. Then the release `RELEASED_FOR_QUALIFICATION`.
