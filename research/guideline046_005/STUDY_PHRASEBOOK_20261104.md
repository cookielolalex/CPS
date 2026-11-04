# Phrasebook study: C/D wording from the creator's past 未填 (2026-11-04)

This was an evaluation-role, leave-one-case-out study on 39 tuning pairs (4,608 aligned rows). The findings are generic; the draft phrasebook is kept privately and has not been adopted.

## What was tested

The key was the normalized 材料清單 description; the value was the creator's most frequent (C, D) for that key. Four C/D sources were compared:

- (i) rules only;
- (ii) exact phrasebook first, then rules;
- (iii) exact phrasebook, then a template phrasebook, then rules;
- (iv) the best variant: current-template cases only, taking the value from the nearest case in time.

## Results

| Measure | Rules only | Best phrasebook |
|---|---:|---:|
| Row-level C/D "both exact" | 0.554 | 0.607 |
| Pooled case score, rows by found mapping (v1.2) | 0.831 | 0.856 |
| Cases ≥0.95 | 0 | 3 (two of them a sibling pair) |

The ceiling with the creator's own C/D is 0.983 pooled, with 34 cases at ≥0.95.

## Why the phrasebook helps so little

The creator's C/D wording varies between projects:

- Majority C/D on shared lines agrees 0.94 between 114 cases, 0.85 between 114 and 115, and 0.66–0.69 in 113.
- By distance in time, agreement is 0.85 with the next one or two cases and 0.18 with cases 16 or more apart.
- The old and current templates use different C conventions (agreement 0.01–0.03).

Most remaining differences come from how the same content is split between C and D, or from one side being blank, not from different wording:

| Difference on covered current-template rows | Share |
|---|---:|
| C filled on one side, blank on the other | 10% |
| C a different word | 11% |
| D filled on one side, blank on the other | 9.6% |
| D a substring or superstring | 9.8% |
| D differs only in spacing or punctuation | 3% |

## Conclusion

A phrasebook is not a route to 0.95. Under strict per-field C/D scoring, 0.95 per case asks for more consistency than the creator shows between her own projects. How "match" should treat the C/D split is put to the owner, with measured alternatives.
