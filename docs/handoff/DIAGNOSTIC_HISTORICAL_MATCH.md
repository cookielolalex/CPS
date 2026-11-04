# Historical-match diagnostic of frozen outputs (2026-11-04)

**Diagnostic only. This is not a qualification run and gives no eligibility credit.**

- **Metric:** `research/evaluation/compare_target048.py`, a draft that has not yet been reviewed. It aligns rows by the joined C+D text plus unit and quantity, then scores positions A–F and I–Q in normalized mode. The threshold is 0.95 (owner decision O12).
- **Outputs scored:** frozen outputs from earlier candidates.
- **Historical targets:** tuning or already-exposed cases only, each verified against its registry SHA-256.

## Results

Candidates 046b and 046c were written to the source-only policy, so they intentionally leave I, J, K, M, N and Q empty, and they use their own C/D split.

| Case (candidate) | Target rows | CPS rows | Paired | Matched / counted | Score |
|---|---:|---:|---:|---:|---:|
| 1141002 (046c), A and B identical | 151 | 151 | 143 | 462 / 1392 | 0.332 |
| 1130803 (046c), A and B identical | 64 | 64 | 63 | 142 / 450 | 0.316 |
| 1140506 (046c), A and B identical | 95 | 96 | 91 | 263 / 843 | 0.312 |
| 1141210 (046c) B | 11 | 18 | 10 | 30 / 136 | 0.221 |
| 1140908 (046b) A | 32 | 47 | 32 | 96 / 357 | 0.269 |

## What the gap consists of

- **Row sets** mostly agree on the three batch-1 cases, with row recall and precision of about 0.95–0.98. 1141210 and 1140908 include rows the creator left out (precision 0.56 and 0.68). This is consistent with owner decision O7 (quoted lines and panels only).
- **E and F** match on almost every paired row. L matches on two cases.
- **C and D** almost never match. The creator leaves C empty on most rows and puts the description in D. That differs from the source-only C/D allocation rules.
- **Fields the creator fills that CPS leaves empty by policy:**
  - I/J (model and brand): about 70–85% of her rows;
  - M/N (customers): every row where she uses them;
  - Q (contract price): about a third of rows.

## Next steps

- A creator-practice study on ten tuning pairs (owner decision O11). It traces where every value comes from: the contract, or outside the contract.
- Candidate 046f, calibrated to her majority practice.
- Re-measurement with the reviewed evaluator.

Fields whose values do not come from the contract cannot be reproduced by a contract-only reader. The study reports the score each case could reach at most if only contract-traceable values were reproduced.
