# Owner decisions O23–O25 (2026-11-05, after the qualification screen and the evaluator-v3 proposal)

The owner chose these through the session's question tool. The question texts are summarized; the answers are verbatim.

| ID | Question | Owner answer | Effect |
|---|---|---|---|
| O23 | Which metric governs qualification? The question described the problem: v2 leaves a row unpaired when its C/D wording differs completely from the creator's, even when it is the same source line at the same position with equal E, F, Q and I/J, and its non-description fields then count as misses. It described v3 as positional pairing inside gaps between agreed rows, with equal counts and equal E and F. It gave the development figures, v2 0.985/0.962/0.942/0.928 against v3 0.985/0.982/0.966/0.984, and said they are post hoc. | "Adopt v3 if review OK (Recommended)" | `compare_target049` governs qualification once its independent review approves it and it is frozen by SHA before any qualification output is evaluated. Until then, and for every result recorded so far, v2 (`compare_target048`) governs. v2 numbers are reported beside v3. The review asked for a stricter fill key: E and F equal, and either Q equal and non-null or I equal, non-null and not 不含估價. That key only removes fills, so it stays within "if review OK". The revised v3 still needs the reviewer's delta approval. |
| O24 | Is the C/D description target of 0.75 (O19) a deployment gate? | "Reported target only (Recommended)" | `description_cd` is reported per case and overall, and is still worked on. It does not gate deployment; the 95% governing score does. This answers review item B3 on v3. |
| O25 | If fewer than 20 independent non-reserved pairs remain, how should the 30 pairs be reached? | "Use more reserved (Recommended)" | The bar stays at 30 independently eligible pairs, at least 10 of them reserved. A shortfall in non-reserved pairs is filled from the reserved 113–115 cases. Reserved answers stay closed until all outputs are frozen, and each reserved case used is spent. Independence rules apply to reserved cases as well. |

These decisions do not reopen frozen candidates, outputs or scores.
