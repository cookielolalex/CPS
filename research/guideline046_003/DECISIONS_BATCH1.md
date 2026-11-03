# Evaluator-side decisions for 046c development batch 1

Dated 2026-11-03 (Asia/Taipei). All were made after the second independent expectation reviews and before any batch-1 generation. They are generic. Case content stays in the private evaluator files.

None of these decisions changes the 046c generator package. Each one narrows what the evaluator scores, and only where frozen 046c does not decide a question and the frozen comparator (`compare_source047.py`) cannot express the alternatives the policy allows. Each exclusion is recorded with its reason in the frozen expectations, the denominators are reduced to match, and a manual obligation still checks that the output classifies the material and invents nothing. The underlying questions go to candidate 046d (see `POLICY_BACKLOG_046d.md`).

| ID | Policy gap | Evaluator treatment | Applies to |
|---|---|---|---|
| B1-Q2 | A priced line with no item number that combines a design service with a management fee. Frozen 046c could make it a demand row (guideline §3 and FIELD_ROLES, retain services that are source demands) or a financial or management nonitem (R11/R12). Independent reviewers read it differently across cases. | Remove the row from the scored rows and keep its cells out of the required census. A manual obligation accepts either reading, provided the cells are classified and nothing is invented. Applied the same way in every affected case. | Every batch-1 case containing such a line (3 cases) |
| B1-Q8 | A numbered cost-category heading that embeds a panel name, with items under it. Frozen 046c does not decide whether it sets up a contractual panel group for A/B, what the group is called, or which rows belong to it. The comparator has no A/B alternatives. | Remove A from core and supported on the affected rows. The manual obligation that assumed the group reading is rewritten to accept either reading, with the enclosure line still following P1. | 1 case |
| B1-Q1 | Removing a middle element from a delimited list in C (R4 literal text against R15 wording). | Declare complete C alternatives for each policy-reachable spelling (comparator-supported). This is not an exclusion. | Every case where it occurs |
| B1-R24 | Count-after-delimiter and similar open R24 C/D placements. | Declare complete C/D alternatives. This is not an exclusion. | Every case where it occurs |

Manual obligations that asked more than the generator-facing text supports were softened or removed under the R13 gate. One example is requiring cost-line codes to be named in D null reasons. Each change is logged in the private expectation notes.

These decisions make the batch-1 numeric gates more lenient only where the policy itself is undecided. They do not change the deployment bar, and no batch-1 case earns eligibility credit.
