# Independent semantic review of candidate 046d (2026-11-03)

**Status: semantically approved; not frozen and not admitted.** Freezing waits for the generic error classes from 046c development batch 1. Any rule added from those classes needs a delta review before the freeze.

## Reviewer and scope

- One fresh general-purpose context, observed model `claude-opus-5-5`. It is independent of the package author.
- Inputs: the public package, `POLICY_BACKLOG_046d.md`, `REVIEW_046c.md` and `PLAN_046d.md`.
- Not read: private evidence, the naming study and the web.

## Round 1: SEMANTIC_APPROVE_AFTER_LISTED_FIXES

There were 4 blocking items, 13 should-fix items and 5 notes.

**Blocking:**

1. R29 contradicted R22 and the checker. A continuation-row cache next to a filled anchor cell could not be cited, so the checker failed with `CONTENT_CELL_NOT_USED_BY_ANY_ITEM`.
2. R33 was under-specified, and the example contradicted it. The rule gave no end to a heading's scope, did not say whether work on the panel belongs to the group, gave no rule for the group name, and did not cover the enclosure line.
3. R30 sent delimited nouns that can name an object (N09, N22) to D.
4. R31 also covered bracketed CJK text and sent protocol and document tokens to R16.

**Should-fix items, now applied:**

- **R25:** components take no group from their parent, and F is the literal value when the block base is above one unit.
- **R26:** the separator is defined as a run.
- **R27:** an explicit list of activity and overhead words, and a percentage rule.
- **R28:** 用-phrases that name an environment or protection condition.
- **R32:** removed the bracket circularity.
- **R34:** forms, bare numbers and core counts.
- **R35:** whitespace, and body names without a number.
- **R36:** conjunction handling and a list of cost words.
- **R37:** nothing between two CJK characters.
- **R38:** edges trimmed.
- **Precedence:** each new rule's position in the R12 order is stated.
- **Self-containment:** P1, P2 and R13 are defined inside the package, and the stale R1–R12 references are updated.
- **R2/R34:** core counts.

**Example corrections:**

- EXAMPLE_RESPONSE: R004 joins G1 under the R33 scope, plus updates to R001, R003, C001 and C002.
- Allocation cases: A21, A31, A34, A36b (new), A37, A40, A42, A47 and A48.

The fixes were applied mostly in the reviewer's own wording, in commit a7149d2. One deviation: a delimited 備用 is an R30 spare word, and fused 備用接點 stays in C under R2. It is not treated as an R1b qualifier. The reviewer found this sound.

## Round 2: SEMANTIC_APPROVE

Every blocking and should-fix item is resolved, and no new contradiction was found. The R13 check passes on all changed examples (A01–A48, A36b, N01–N30 and EXAMPLE_RESPONSE).

The reviewer ran the route `check` on the example (PASS). The reviewer did not re-run the route tests; the author's run is 114/114.

Four optional wording notes were applied after approval. They change wording only, and the check still passes:

- "spare words (備用, 預備)";
- the representation sentence no longer claims a prior review;
- R37 examples use ⏎ to mark the boundary;
- the R005–R007 A null reasons name the subtotal row that closes the heading's scope.

## Residual risk recorded by the reviewer

R33 decides the core A/B fields and rests mainly on one development case. The frozen comparator has no A/B alternatives. Any evaluator convention on panel groups therefore has to follow R33's wording exactly. A heading R33 does not settle remains an R24 doubt, to be declared or excluded before generation.
