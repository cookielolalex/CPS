# Creator-practice study: 10 tuning or already-exposed pairs (2026-11-04)

This was an evaluation-role study of 10 non-reserved pairs (891 target rows). Each pair is a contract and the creator's historical 未填. The findings below are generic; case evidence stays private. It answers owner decision O11 and gives the reachability analysis for O12.

## Majority conventions (≥80% of applicable rows)

**Row inclusion**
- **INC-02:** a priced line inside the quoted range gives one row (326/338).
- **INC-03:** a line marked "not estimated" (不含估價) inside that range also gives a row (539/546).
- **INC-04:** a line with no price and no status gives no row (91/92).
- **INC-05:** lines after the quote total give no row (40/41).
- **INC-06:** analysis components become rows only when the parent line is unpriced and the block lies in range (184/191).
- **INC-07:** service, labour and fee lines are treated like materials.
- **INC-09/10/11:** contract order is kept; no line is split; no rows are added.

**E, F and stage blanks**
- **EF:** unit and quantity are copied verbatim.
- **K, O, P:** blank.
- **G, H:** blank. One older template puts the contract price and amount there instead.

**C and D**
- **CD-01:** a generic leading "product" word is dropped.
- **CD-13:** when C is blank, D is the full description with its category chain.
- **CD-02:** on service lines, C is blank and D is the full description.
- **CD-04:** on priced material lines, C is filled.
- **CD-05:** on device-family lines, C holds a habitual Latin abbreviation. The contract contains that abbreviation in only 12% of cases.
- **CD-07:** a noun moved to C is not repeated in D.
- **CD-09:** remark and code text never enters C or D.
- **CD-10:** continuation rows are joined with no separator.

**Q, I and J**
- **Q:** on priced lines, Q is the quoted unit price, never the amount. Q is blank on "not estimated" lines.
- **IJ-01:** on "not estimated" lines, I and J both hold the status text. Pooled rate 0.87, with 7 of 9 pairs at 100%.

**Enclosure row, A and B**
- **AB:** A and B are blank except on the supplied-enclosure row. That row has A, and B in the form `<w>W*<h>H*<d>D`.
- **IJ-05:** on the enclosure row, J is the sender's company name from the signature line.

**L, M, N**
- **KL-03..07:** when filled, L is the internal case id, M the customer's full name and N an edited project name. All three are constant for the sheet.

**Mixed or minority conventions** (left undecided): the C/D cut on some line types, comma and bracket rewriting in specification lists, and which rows carry L.

## Where the values come from (non-empty target values)

| Field | Traceable to the contract |
|---|---|
| E, F | 98% |
| Q | 99% |
| L | 100% |
| D | 83% verbatim, 11% with punctuation folded |
| A | 69% |
| C | 49% (the rest are habit abbreviations) |
| I/J | about 72%, almost all of it the copied status text (91% of real brand/model values are external) |
| N | 25% |
| B | 22% |
| M | 0% |
| K | 0% |

## Reachability of 95% (compare_target048, normalized)

These upper bounds assume each pair's own choices are known perfectly.

| Level | What CPS reproduces | Pairs reaching 0.95 | Best pair |
|---|---|---:|---:|
| Contract-traceable values only | everything that can be traced to the contract | 0 of 10 | 0.92 |
| plus M and N supplied | as above, with the customer name and project short name given | 4 of 10 | |
| plus I and J supplied | as above, with brand/model given | 4 of 10 | |
| plus M, N, I and J supplied | all four given | 9 of 10 | |

- A single uniform policy simulated on all pairs scored 0.52–0.59 pooled.
- One target was built from internal design rather than the contract. It reaches only 0.54 even with every field given, and should be screened as ineligible.

## Consequences

The inclusion, Q, I/J status, enclosure-row and C/D conventions can be reproduced from the contract. They go into candidate 046f.

Reaching 95% also needs inputs that are not in the contract:
- the customer full name (M);
- the project short name (N);
- the company's brand/model choices (I/J);
- the creator's abbreviation glossary (C).

These are owner decisions.
