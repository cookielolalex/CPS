# Candidate and output review checklist (candidate 046f, draft)

Use actual evidence for each entry. Record pass, fail, unresolved or not applicable with a reason; do not fill all entries from a global disclaimer.

## Before generation

1. Exact generic guideline/resources and allowed tool route identified and hashed; no target/evaluator/prior-output facts in the generation context.
2. Actual requested and observed model/effort/tool settings recorded without asserting unobserved backend behavior.
3. Source bytes, version/adoption, scope, identity namespaces and missing annexes documented; originals read-only.
4. Complete source inventory and views available; format/merge/cache/formula/hidden-state limitations explicit.
5. Job inputs and company resources present as context facts (`context:case_identity`, `context:customer_name`, `context:project_name`, `context:company_name`, `context:glossary`, `context:brand_table`), each pinned by SHA-256 to the private per-job configuration or the owner-reviewed resource file. The resources were built only from non-reserved files and reviewed by the owner (O13–O16). No historical 未填 row, target or evaluator datum is among them.
6. Representation profile, role policy, independent source expectations or historical-match metric, alternatives and failure behavior fixed before the model sees the source.
7. Current candidate schemas, route v4.1/adapter, export mode, safety and coverage route independently reviewed and meaningfully tested. This authoring candidate does not satisfy that gate by itself. `tools/cps046b_route.py check` passes on the frozen response, or every remaining violation is an honestly recorded `unrepresentable_hold`. The interface points and the open policy question in `OUTPUT_CONTRACT.md` are decided or explicitly carried.

## Semantic review (FIELD_ROLES R48–R58 govern; earlier rules where they do not disagree)

8. **Quoted range (R49).** The detailed bill sheet with the sender's prices is identified; the range starts at the first item line under the column header and ends at the row whose unit-price or amount column holds 合計 or 總計; a 合計 in the description column was treated as a block total; summary sheets yield no rows.
9. **Rows (R50).** Every priced, not-estimated and zero-state line in range, and every unnumbered sender fee line before the end row, gives exactly one row in source order. No line is split, merged or added. Lines with no price and no status, and item-like lines out of range, are `excluded_supply` with the stated reasons. Remarks saying "not included" did not remove a line. Supply and separate-contract markers did not decide inclusion and appear in no field. Any O10 omission is recorded as provisional.
10. **Components (R51).** Components are rows only when their parent has no price and no status and the block is in range, or when every bill line is unpriced; the parent then takes `section` and block totals are not rows. Components of a priced or not-estimated parent stay `analysis_component` items or `analysis_unlinked` cells.
11. **C/D (R52, R53).** The generic prefix named in the glossary is dropped. Equipment lines carry the glossary abbreviation or the head noun in C and the rest in D; material, bulk, service, labour and fee lines carry C null and the description in D; single segments follow R52. Breaker-type D joins rating tokens with single spaces; every other D keeps punctuation verbatim. Remarks, codes and price text are not in C or D. No abbreviation outside the glossary.
12. **I/J (R55).** Not-estimated lines carry I = J = 不含估價 from the amount cell. Priced equipment lines carry a brand or model stated in the line's own cells, else the brand-table entry for the device and rating band, else null with a reason. Material, service, fee and zero-state lines carry none. No brand or model from memory.
13. **Enclosure row (R56).** A priced line supplying an enclosure is one row with A, B (`<w>W*<h>H*<d>D` or null), C (the glossary's enclosure word), D (remaining material/finish/type), E, F, Q, I null and J = the company name. No other row carries A or B.
14. **Values (R48, R54, R57).** L, M and N equal the job inputs on every row and cite only their context refs; M and N were not inferred from document furniture (R6, critical). K, O, P, G and H are null. Q is the unit price on priced lines and null otherwise. E and F are the line's own cells verbatim.
15. **Citations (R58).** Fields derived through a resource cite the source cell and the context ref; null reasons are true of the whole source (R9); total discrepancies are recorded, not repaired (R10).

## Mechanics and completion

16. Every source reference matches inventory/case/scope; all 17 non-null proofs and null reasons consistent; no silent repair or favorable reference substitution.
17. Original source types/raw states retained; canonical raw fields follow the declared profile; source coverage and anchor-plus-census obligations complete.
18. Frozen response/expanded carrier/output hashes and failed/unattempted outcomes preserved before scoring. The export mode used (v1, or v2 for M/N selection evidence) and its receipt are recorded.
19. Saved-cell comparisons and full readable workbook checks pass for the actually claimed output scope; assembly repeat measured separately.
20. Independent correctness and critical-error checks pass; reader agreement alone does not qualify.
21. Historical target eligibility/stage/revision and exposure handled in a separate evaluation context. The deployment bar is the owner's (O12: 95% match on eligible, revision-compatible pairs, with the metric frozen before any qualification run; the other bar elements unchanged). Draft status cannot turn into business approval without the actual programme gate.
