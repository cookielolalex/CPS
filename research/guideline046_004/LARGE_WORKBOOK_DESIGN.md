# Large workbooks: structure findings and proposed method (design note, not admitted)

Source: a counts-only, source-role structure study of five large tuning-cohort workbooks: 1131112, 1140607, 1140304, 1131207 and 1140808. 1140608 has no packet yet. The study read only the v2 inventories and views; it read no targets or outputs, and no case text appears below.

## Findings

| Case | Content cells (all sheets) | Detail-sheet content | Est. demand items | Analysis blocks / components | Blocks resolvable to a detail item |
|---|---:|---:|---:|---:|---:|
| 1131112 | 7,596 | 510 | 78 | 190 / 1,075 | 0 |
| 1140607 | 3,927 | 960 | 92 | 8 / 37 | 8 |
| 1140304 | 2,414 | 479 | 83 | 32 / 128 | 0 |
| 1131207 | 4,571 | 419 | 67 | 118 / 612 | 0 |
| 1140808 | 5,256 | 607 | 77 | 94 / 488 | 0 |

- **Detail sheets are not the problem.** Each has 419–960 content cells, in line with batch-1 cases that one reader completed in about 10–15 minutes (826 content cells, 151 rows).
- **The size is in unit-price analysis and resource sheets.**
- **No atomic unit is large.** The largest item group is 32 cells and the largest analysis block 116.
- **Heading scopes cross natural split points.** A unit can open inside up to four heading scopes.
- **Most analysis blocks have no parent in the workbook.** In four of five cases, no block resolves to a detail item by code, name or unit. Block references are local sequences or outline paths for sub-sections that the detail sheet does not contain. The detail sheet holds one sub-section and the analysis sheet covers others. That reading is an inference, not proven.
- **Patterns a chunked method must handle:**
  - sheet roles identified by header vocabulary;
  - paginated analysis sheets with page frames, which are safe split points;
  - block headings and basis other than 1 (in the quantity column or embedded in total-row unit text);
  - blocks that reference other blocks;
  - continuation rows carrying formula zeros;
  - integer markers shared by site headings and items;
  - outline level inversion and numbering restarts;
  - unnumbered priced rows after the last subtotal;
  - mid-table trailer totals, page footers, helper columns and heavy merging.

## Policy question for the owner (blocking for these workbooks)

Under 046d, every analysis component must be written as an `analysis_component` item with a supported link (SOURCE_REFERENCE_CONTRACT, OUTPUT_CONTRACT step 2). The admitted writer then refuses a component without a detail parent (`COMPONENT_PARENT_MUST_BE_DETAIL`), so the whole export is held. Components never appear in the 17-column 未填 sheet itself; the writer places them on a separate composition-reference sheet. Four of these five workbooks would therefore always end held, however well they are read.

Options:

- **(a) Keep the current rule.** A workbook with analysis blocks that have no detail parent is held. This is honest but never deployable for such workbooks.
- **(b) No-parent blocks are not components.** An analysis block whose referenced item is not in this workbook's detail table is classified in the nonitem census, every cell kept with role `analysis_content` and the reason "analysis block for an item not in this workbook's detail table". No component item or link is written, and the 未填 sheet is unchanged. Blocks with an identifiable parent keep the R21/R25 component rule. This needs a reviewed route and contract change.
- **(c) Carry no-parent components without a link.** This needs a writer change, which is outside the admitted writer.

Recommendation: (b), because it preserves every source cell and invents no link. It needs an owner decision, because "never delete a component" is current policy.

## Proposed chunked method (046e; to be implemented and reviewed)

1. **Unit plan (deterministic tool).**
   - Classify sheets from header vocabulary and propose work units at safe split points: item boundaries, block headings and page frames.
   - Cap each unit at about 1,000 content cells for detail sheets, roughly the largest single-pass size seen so far, and about 400 for analysis sheets.
   - Carry heading context (the open heading scopes) into each unit as read-only context cells.
2. **Detail units.** One reader per unit, with the full package and the full inventory. It writes items only for its own rows, plus census roles for its cells.
3. **Analysis units.** One reader per unit. It receives a frozen digest of the detail items (ID, C, unit and anchor) from step 2, and writes components with links proven by code, name or unit. Under option (b), no-parent blocks are census-only.
4. **Deterministic merge.**
   - Concatenate unit responses in sheet and row order and renumber IDs.
   - Union the census.
   - Any cell claimed twice or claimed by no unit is a merge failure: recorded, never repaired.
   - The merged response must pass the unchanged checker.
5. **Two readers.** Each runs the whole chain independently. Unit outputs are frozen before the merge, and the merge before evaluation.
6. **Expectations for large cases.** Authored by unit and frozen before generation, with the same R13 gate.

Not started:
- the unit-plan tool;
- the per-unit check mode in the route (the current checker requires every content cell to be used, so it can validate only the merged response);
- merge tests with invented fixtures;
- an independent review.
