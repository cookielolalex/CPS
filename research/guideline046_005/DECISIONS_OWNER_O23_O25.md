# Owner decisions O23–O25 (2026-11-05, after the qualification screen and the evaluator-v3 proposal)

The owner chose these through the session's question tool. The question texts are summarized; the answers are verbatim.

| ID | Question | Owner answer | Effect |
|---|---|---|---|
| O23 | Which metric governs qualification? The question described the problem: v2 leaves a row unpaired when its C/D wording differs completely from the creator's, even when it is the same source line at the same position with equal E, F, Q and I/J, and its non-description fields then count as misses. It described v3 as positional pairing inside gaps between agreed rows, with equal counts and equal E and F. It gave the development figures, v2 0.985/0.962/0.942/0.928 against v3 0.985/0.982/0.966/0.984, and said they are post hoc. | "Adopt v3 if review OK (Recommended)" | `compare_target049` governs qualification once its independent review approves it and it is frozen by SHA before any qualification output is evaluated. Until then, and for every result recorded so far, v2 (`compare_target048`) governs. v2 numbers are reported beside v3. The review asked for a stricter fill key: E and F equal, and either Q equal and non-null or I equal, non-null and not 不含估價. That key only removes fills, so it stays within "if review OK". The revised v3 still needs the reviewer's delta approval. |
| O24 | Is the C/D description target of 0.75 (O19) a deployment gate? | "Reported target only (Recommended)" | `description_cd` is reported per case and overall, and is still worked on. It does not gate deployment; the 95% governing score does. This answers review item B3 on v3. |
| O25 | If fewer than 20 independent non-reserved pairs remain, how should the 30 pairs be reached? | "Use more reserved (Recommended)" | The bar stays at 30 independently eligible pairs, at least 10 of them reserved. A shortfall in non-reserved pairs is filled from the reserved 113–115 cases. Reserved answers stay closed until all outputs are frozen, and each reserved case used is spent. Independence rules apply to reserved cases as well. |

These decisions do not reopen frozen candidates, outputs or scores.

## Addendum (2026-11-05, after the v3 delta review; the table above is kept as written)

The O23 cell says the stricter key "only removes fills". That is wrong. The revision also replaced equal-count positional pairing with an order-preserving maximum matching inside each gap. On some inputs that adds fills compared with the first proposal: reviewer fixture C8c rises from 0.024 to 0.954, and C10a from 0.717 to 0.896. Both versions were reviewed, and the matching is what the review asked for, so the change is still within "if review OK". The delta review approved the revised code. It is frozen at sha256 `b600c046…` (`research/evaluation/FREEZE_049.json`).

## O26 (2026-11-05): the qualification pool short of 30

**Question.** After the family-independence review, the counts were:
- 14 independent non-reserved candidates in 113–115 (7 without the large-workbook method);
- 14 independent reserved candidates in 113–115.

That totals 28 of 30, before any reserved target is found to be old-template. Year 112 has 30 unexposed non-reserved cases, not yet screened.

**Owner answer:** "Accept borderline cases".

**Effect.** Two borderline independence cases are counted:
- the non-reserved case whose only overlap with an exposed case comes from a shared designer specification library, containment 0.646 (1150202);
- the reserved case with a weak project-series tie to exposed cases (listing only; not named in public).

The pool is exactly 30: 15 non-reserved and 15 reserved, with no margin. Year 112 stays outside (O22).

**Consequences.**
- Any pair that turns out ineligible leaves the bar unreachable from this pool, and that goes back to the owner. This includes a reserved target found to be old-template once opened after all outputs are frozen.
- The pool is not refilled by choosing replacements after the answers are seen. The single pre-declared alternate for the one reserved duplicate-family pair is recorded privately before generation.

