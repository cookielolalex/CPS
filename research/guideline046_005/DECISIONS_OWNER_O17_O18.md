# Owner decisions O17–O18 (2026-11-04, after the company-table build)

The owner chose these through the session's question tool.

| ID | Question | Owner answer | Effect |
|---|---|---|---|
| O17 | May CPS read the project's company material list (材料清單) as a second input? The creator copies it into the 原材料清單 sheet of her 未填, and its brand/model columns matched her 未填 on all 1,128 checked rows. | "Yes, use 材料清單" | When a job's project folder has a 材料清單, CPS reads it alongside the contract, for brand, model and other item details. The company brand table (O14) is used only as a fallback when no 材料清單 exists. |
| O18 | Breaker brand when no 材料清單 is available | "Most common brand" | Breakers get the overall most common breaker brand from her past non-reserved 未填, with the table's rating-band models. |

## Data boundaries

- **Two sources per job.** The 材料清單 is a job input, prepared like the contract: a v2 inventory with views, hash-pinned. It is the company's own pre-未填 document. It is not a historical 未填, not a target and not evaluator data.
- **Reserved projects.** Their 材料清單 files are prepared only at qualification time, together with their contracts, and their targets stay closed.
- **Eligibility.** A pair needs evidence that the 材料清單 predates or accompanies the contract stage. Its file times or revision must not come from after the 未填 was created.
