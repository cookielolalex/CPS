# Independent review of candidate 046e (2026-11-03)

**Status: semantically and interface-approved, then frozen (manifest `85efda95fd30de51fff79edda30ee791ec4c9f3df48dd90db310273d5b6e20c9`, 16 files). Not admitted.**

Candidate 046e applies owner decisions O6–O8 ([DECISIONS_OWNER_O5_O9.md](DECISIONS_OWNER_O5_O9.md)):

- **R45:** item scope;
- **R46:** analysis blocks with no parent demand item;
- **R47:** acronym glosses.

It also includes:

- a package-author amendment to R25: components never carry A/B;
- route v3, which adds the census roles `excluded_supply` and `analysis_unlinked` and the checks `CENSUS_ONLY_CELL_USED_BY_ITEM` and `COMPONENT_GROUP_FORBIDDEN`.

## Reviewer

- **Context:** one fresh general-purpose context, independent of the package author.
- **Observed model:** `claude-opus-5-5`.
- **Read:** the public package, the diffs against 046d, the decisions file, the supply-list semantics, CRQA-11 and the large-workbook design note.
- **Not read:** private evidence, the naming study and the web.

## Round 1: SEMANTIC_APPROVE_AFTER_LISTED_FIXES (2 blocking)

**Blocking findings:**

1. R45 overrode the nonitem rules. A priced tax, overhead or resource row would have become an item.
2. R45 excluded lines where "no enclosure and no estimate" was not established. The cases were:
   - a lump-sum contract;
   - an unpriced breakdown under a priced parent;
   - a line priced by its analysis block;
   - an R42 pointer line, which is EXAMPLE R007.

**Should-fix findings:**

- gaps in the price and panel tests;
- a fixed reason that erased distinctions between causes;
- R46 was not deterministic;
- R47 conflicted with R31's attribute clause;
- stale text;
- a route gap: items could cite census-only cells;
- the writer's census cap;
- a stale harness.

**Resolution:**

- All findings were applied, mostly in the reviewer's wording, in commit a56bf75.
- The route gained two checks, and route tests rose to 122.
- EXAMPLE R007 returned to its held 046d form with an R45 review reason.
- The R25 basis and the open question on owner-supplied panels are recorded in the decisions file.

## Round 2: SEMANTIC_APPROVE_AFTER_LISTED_FIXES (wording only)

Three exact string changes were required:

- OUTPUT_CONTRACT step 2: keep, exclude, or leave other rows to their own roles;
- SOURCE_REFERENCE_CONTRACT: document the two new checks and the R46 header/footer exception;
- EXAMPLE R007: add a limitation.

All three were applied as written, together with note 5: an exclusion overrides R29 for caches on continuation rows. The reviewer said no further semantic review was needed after these changes.

## Checks before freezing

- **EXAMPLE:** passes route `check` (route v3).
- **Route tests:** 122/122. Both the reviewer's run and the author's final run passed.

## Residual risks

- **R45 doubts become new evaluator declarations.** Each doubt is kept as a demand item. Whether a doubt counts must be declared before generation, because the comparator has no optional rows.
- **The writer census cap is unchanged.** Writer004 accepts at most 5,000 nonitems, so the largest workbook (1131112) stays held.
- **Owner-supplied or 另案 panel lines are an open question.** They are kept as doubts until the owner rules.
