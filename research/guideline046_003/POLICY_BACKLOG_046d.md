# Policy backlog for candidate 046d (generic; collected 2026-11-03)

Independent source-expectation authors raised these questions on development cases 1130803, 1141002, 1150107 and 1140506 under the frozen 046c text. They are phrased generically, with no case content. "Cases" counts how many authors raised each one. Until 046d decides them, evaluators cover them with declared complete alternatives or with prospective R24 exclusions.

| ID | Question | Cases | Notes |
|---|---|---|---|
| Q1 | Removing a delimited middle span from C (A，X，B): keep one delimiter, both, or none? R4's literal text and R15's wording disagree. | 3 (also on 1141210) | Recurring. Decide in 046d. |
| Q2 | A priced line with no item number that combines a design service with a management fee: is it a demand row or a management allocation (financial_summary)? | 3 | Row existence cannot be covered by a C/D alternative, and the comparator has no optional rows. |
| Q3 | Purpose or application words in a remarks cell: a D attribute, or unresolved text kept in raw? | 2 | |
| Q4 | Zero-valued formula caches on continuation rows or outside items: which nonitem role? No canonical role exists, so they are currently `unresolved`. | 2 | Census is checked by locator only. |
| Q5 | A delimited noun naming the kind or type of the preceding product: C (a second identifying noun) or D (a type attribute)? | 2 | |
| Q6 | A bracketed letters-and-digits token directly after a name: an unidentified code token (R16) or a type designation (R7 acronym gloss)? | 1 | |
| Q7 | An undecided-class token moved to D inside a longer run: always its own span (as for R1b), or part of the run (R14)? | 2 | Example N14 and rule R14 give different forms. |
| Q8 | A section heading that embeds a panel name, with items under it before a subtotal: does it establish a contractual group for A/B? | 1 | It carries many A core fields, and the comparator has no A/B alternatives. |
| Q9 | Words fused after a standard number that name a test method: part of the document reference (R5) or of the service name (C)? | 1 | |
| Q10 | An inclusion clause mixing objects or work with a labour-cost word: a D attribute (R1 inclusion of work) or a financial annotation? | 1 | |
| Q11 | A continuation boundary that splits a word: still one U+0020? | 1 | |
| Q12 | Is a unitless size designation (for example W100) a measurable value under R2/R17? Example A03 implies yes. | 1 | Make it explicit. |
| Q13 | Stored trailing spaces on unsplit fields, and an unpaired bracket at a field end. | 1 | The frozen text decides both (keep verbatim). Confirm explicitly. |

Evaluator observations, recorded for the comparator after 047. They do not change any rule.

- The numeric gates ignore unsupported populated positions. A critical R6 party-role fill therefore passes the numeric gates and is caught only by the critical manual obligation. A dedicated gate is proposed.
- Alternatives exist only for C/D. There is no mechanism for A/B group alternatives or for optional rows.
- The census is checked by locator only. Roles and literal text are checked by manual review.
