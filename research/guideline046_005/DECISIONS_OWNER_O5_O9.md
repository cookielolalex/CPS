# Owner decisions O5–O9 (2026-11-03, after 046c batch 1 and the large-workbook study)

The owner answered these through the session's question tool. Answers are quoted where the owner wrote free text. They apply from candidate 046e onward. Frozen 046c/046d, their expectations and their scored outputs are unchanged.

| ID | Question | Owner answer | Effect |
|---|---|---|---|
| O5 | Export runtime for saved 17-column and visual QA | "Build portable writer" | Build an openpyxl writer that reproduces writer004's validation and sheet content, prove parity on invented fixtures, then have it independently reviewed. Once admitted it becomes the export route for saved-cell and visual QA. It is not admitted yet. |
| O6 | Analysis (單價分析) blocks whose item is not in the workbook's detail table | "Census only" | Such blocks are not components. Every cell goes into the census with role `analysis_unlinked` and a fixed reason. No component rows or links. Blocks with an identified parent keep R21/R25. |
| O7 | Which lines are 未填 rows | Free text on the protocol question: "電力監視器 RS485, Modbus電錶, 乙太網路交換器; these items without quote price should not be included into 未填. Only items when panels are quoted should be include inside 未填 most of the time." Follow-up answers: "Include all priced lines"; panel contents → "Yes, include them"; left-out lines → "Census with reason". | A line is a 未填 row when it has a quoted price or lies inside a panel of this contract. A line with no quoted price that is not inside a panel (no enclosure and no estimate, CRQA-11) is not a row: its cells go into the census with role `excluded_supply` and a fixed reason. |
| O8 | Acronym gloss in brackets after a full name | "Keep in C with brackets" | The R7/R8 acronym-gloss class is decided: 自動切換開關(ATS) → C 自動切換開關(ATS). It is no longer an undecided class. |
| O9 | Protocol/interface token placement for included items | Not answered as a placement: the owner answered with the item-scope rule above (O7). | The protocol/interface class stays undecided. Evaluators keep declaring both placements. |

The deployment bar, reserved closure, exclusions and WT-A5 closure are unchanged. O7 applies the recorded CRQA-11 rule ("no enclosure and no estimate"), now confirmed by the owner as the test for 未填 rows. Missing price alone still never deletes a line inside a panel.

## Package-author decisions in 046e (not owner decisions; independently reviewed)

- **R25 amendment** (components never carry A/B). The basis is the generic open question raised by two independent 046d expectation authors: does an analysis-block heading that names a panel create an R33 group for its components? Components are written only to the writer's composition-reference sheet, never to the 17-column 未填 sheet, so A/B have no 未填 meaning for them. The route enforces this with `COMPONENT_GROUP_FORBIDDEN`.
- **R45 boundary.** A line is excluded only where "no enclosure and no estimate" is actually established (CRQA-11). Lines held under R42, lines inside a panel, and R45 doubts are kept as demand items with a review reason. The doubts are other price content, a price possibly carried by a parent or analysis block, a heading that names a panel but forms no group, owner-supplied or 另案 panel lines, and contracts without line prices.
- **Open question for the owner.** O7 says "items when panels are quoted". A panel line whose own price text says 業主供料 or 另案 (owner-supplied or a separate contract) is kept as an R45 doubt for now, together with its contents, until the owner rules. Enclosure-like objects (接線盒, 拉線箱) and existing panels (既設盤) are evaluator-declared doubts.
