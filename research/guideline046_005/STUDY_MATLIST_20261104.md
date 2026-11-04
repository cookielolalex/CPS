# What the 材料清單 can reproduce (study, 2026-11-04)

This was an evaluation-role study of 39 tuning pairs. It used the creator's 原材料清單 sheet as a stand-in for the 材料清單, which was verified to be a faithful copy. The findings are generic; case evidence is kept privately. 1140507 was built from internal design and is excluded from the pooled figures.

## Rows

- 4,608 of 4,625 target rows trace to a 材料清單 line, and source order is kept.
- Lines inside the quoted range that became rows, by type:

| Line type | Became rows |
|---|---:|
| priced | 97.7% |
| 不含估價 | 88.3% |
| zero-state | 5.2% |
| no price and no status | 1.9% |
| after the end row | 0% |

- In 9 cases the creator dropped whole blocks with no marker in the source, mostly 不含估價 sections.

## Fields

| Field | Found in the 材料清單 |
|---|---:|
| E | 99.0% |
| F | 100% |
| Q (unit price) | 100% |
| J, real brands | 99.9% |
| I, real models | 93.7% |
| C | text present for 56%; habitual abbreviation for 41% |
| D | whole description 51%; substring 30%; punctuation-folded 13%; edited 6.5% |

## Upper bounds (compare_target048 v1.1, normalized; L/M/N per row as in each target)

| Variant | Pooled | Cases ≥0.95 |
|---|---:|---:|
| Deterministic rules for every field, leave-one-out glossary | 0.841 | 1 of 39 |
| The same, with the creator's own C | 0.912 | 12 of 39 |
| The same, with the creator's own C and D | 0.980 | 34 of 39 |
| Rows chosen by rule instead of the found mapping, with the creator's C and D | 0.891 | 29 of 39 |

## Conclusions

- With the 材料清單 as input, the remaining gaps are C/D wording and unmarked block omissions.
- Scoring L/M/N on every row against older targets that write them once distorts the score. Metric v1.2 therefore scores K, L, M, N and O once per case.
- The creator's majority C/D practice differs from draft R52 in four ways:
  - she drops the category chain on most rows, including rows where C is blank;
  - she writes a bracketed Latin acronym alone in C (75%), which conflicts with owner decision O8;
  - single-segment lines go to D 65% of the time;
  - she writes a space between rating-like tokens on all device types, not only breakers.
