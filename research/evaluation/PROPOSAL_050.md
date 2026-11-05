# Proposed evaluator v4: compare_target050 (A/B scored per panel), 2026-11-05

**Status: proposed under owner decision O35 ("Score A/B per panel"). Not frozen, not governing.** Round 1 of the independent review returned APPROVE_AFTER_LISTED_FIXES against `feccaf21…`. The listed fixes B1, B2 and S1–S4 are applied below; S5 is deferred to the next harness version. The fixed code needs a delta review, then a freeze by SHA before any qualification output is evaluated. Until then the frozen v3, `compare_target049.py` (`b600c046…`), stays as it is.

| File | sha256 |
|---|---|
| `compare_target050.py` (after round-1 fixes) | `ca10ae5f9507e39a6e0e714b77d5b49bf39f7924d1cb55246f877e148c0a75cb` |
| `aggregate_qualification050.py` (aggregator v2, pins the line above) | `449ef4e44de446f28373ef24fe2cbcb86e3641c59d658a3db1425381544e8779` |

## Problem

The historical creator puts a panel's A/B (盤體名稱 and 盤體規格) in one of two places:
- on the enclosure row only, in most files;
- on every row of the panel's group, in the files from March–May 115.

v3 scores A/B per row. So one panel name counts once, or 70–90 times, depending only on which of her two habits the target follows.

The effect was measured in an evaluation-role study of the three exposed window files (`research/guideline046_005/DECISIONS_OWNER_O23_O25.md`, O32–O35). With a group-wide rule added to CPS, the best possible scores on two of those files were still 0.84 and 0.67, below the O31 floor of 0.90. One panel name that is wrong, or that does not appear in the source, was multiplied across the panel's rows.

The evaluator already treats K–O as job-level for exactly this reason: she writes them on every row in later files and on the first row only in older ones.

## Change

A and B leave the per-row positions. For each case:

1. **A.** Take the set of distinct non-null normalized A values on all target rows, and the same set on all CPS rows, paired or not. `counted = max(|target set|, |CPS set|)`, `matched = |intersection|`. A wrong name and the missing right one offset as one substitution.
2. **B (round-1 fix B1).** B is scored per size unit, not as a loose set of values. A unit is a distinct (A, B) pair with B non-null. A unit with no A is dropped when its B also appears with an A, so group-wide B under an enclosure-only A is not counted twice. The units of the two sides are matched one-to-one, with as many pairs as the smaller side, by a maximum-weight assignment (`_assign_max`, Kuhn–Munkres). The weights prefer an equal non-null A first and an equal B second, strictly, so the counts do not depend on ties. `matched` = matched units with equal B; `counted` = the larger number of units.

As a result:
- one wrong panel name counts once, as it did on a single row in v3;
- a size counts once per panel name, so two panels that share a size each count, and a swapped, rotated or omitted size still costs;
- a missing or extra panel name or size counts once per distinct value.

The round-1 code scored B as a value set. It gave 1.000 to swapped, rotated and omitted sizes of panels that share a size (reviewer cases C6b, C7a–C7e). With B1 those cases score as in v3 or stricter.

### Not scored, disclosed

v4 does not score:
1. two panels identical in both A and B (they count once);
2. a whole label (A and B together) moved to another panel;
3. which rows carry A/B, so a right A/B written on a device row costs nothing;
4. CPS rows that carry only A/B and no other scored value, when their A/B values also appear elsewhere;
5. a guess while CPS has fewer distinct names than the target: an extra wrong A does not raise `counted`, so it is free. v3 charged a guess written on a row whose target row had no A.

### `ab_row_check` (round-1 fix B2)

A new diagnostic, not scored, for the manual critical-error review:
- `paired_conflicts`: aligned pairs whose non-null A or B differ (target row, CPS id, field, both values);
- `cps_unpartnered`: CPS A or B on a row whose aligned target row has neither A nor B, or on an unpaired CPS row.

Cases 2–5 above appear there when the CPS value sits on a paired row with a different target value, on a row whose target has no A/B, or on an unpaired row. Case 1 never appears. A CPS null is never listed, so a group-wide target with an enclosure-only CPS lists nothing.

The reviewer also asked that `EVALUATOR_BRIEF_TEMPLATE` §3 gain this critical-error class: "a panel's A or B on another panel, or A/B on a row that is not its enclosure row (check every `ab_row_check` entry)". The brief is byte-pinned by the frozen 046f admission, so the change goes into the next harness version with S5 below.

### Job-level K–O tie-break (round-1 fix S2)

v4 picks the modal K–O value with `max(dict.fromkeys(values), key=values.count)`. On a tie, the value first in row order wins, and the result is the same in every run.

v2 and v3 use `max(set(values), key=values.count)`. That picks by set iteration order, and string hashing is randomised per process (`-I` also ignores `PYTHONHASHSEED`). **So the frozen v2 (`compare_target048.py`) and frozen v3 (`compare_target049.py`) are not repeatable on a case with a K–O tie: the same inputs can score differently between runs.** On one invented tie case (L = J-1 and J-2 on two target rows, J-1 on both CPS rows), 12 separate `-I` runs of each gave:

| Evaluator | 0.923 | 1.000 |
|---|---:|---:|
| v2 `compare_target048.py` | 8 | 4 |
| v3 `compare_target049.py` | 9 | 3 |
| v4 `compare_target050.py` | 0 | 12 |

The split between the two values changes from run to run; both occur for v2 and v3. Frozen results recorded under v2 or v3 for a target or carrier with a K–O tie are therefore one draw, not a repeatable number.

### Output schema (corrects the earlier claim that it was unchanged)

The round-1 text said the schema of the outputs was unchanged. That was wrong. Against v3, the output changes as follows:
- `schema` is `cps.target-comparison050.v1`;
- `per_field.A` and `per_field.B` hold panel counts (B in size units), and are present only when they count at least one position, as for K–O. v3 always wrote both keys;
- `v3_per_row_AB` is new: v3 scoring (A and B per row) on the v3/v4 pairs;
- `ab_row_check` is new;
- `v2_alignment` again holds the genuine v2 number (fix S1). The round-1 code applied v4 field rules to the v2 pairs, and so differed from `compare_target048` in 279 of 400 random cases. It is now `score(T, C, v2_pairs, 'normalized', scored=SCORED_V3, panel=[])`.

`v3_per_row_AB` and `v2_alignment` use the v4 tie-break. Each equals its frozen evaluator except on a K–O tie.

Everything else is v3: row alignment, gap fill, the other fields, normalization and the description score.

CPS keeps writing A/B on the enclosure row only (O30), its current practice. The date-window rule (O32) is withdrawn.

## Effect on the frozen 046f development outputs (reader A, diagnostic, post hoc)

The v3 and round-1 v4 columns were recorded before the review. The fixed-v4 columns were run by the orchestrator in the evaluation role with `compare_target050.py` at `ca10ae5f…` (2026-11-05). None of these five cases has a K–O tie on either side, so their recorded v2/v3 numbers are repeatable.

| Case | v3 | v4 round 1 (`feccaf21…`, superseded) | v4 fixed (`ca10ae5f…`) | `ab_row_check` conflicts / unpartnered |
|---|---:|---:|---:|---:|
| 1130803 | 0.985 | 0.985 | 0.985 | 0 / 1 |
| 1140506 | 0.962 | 0.962 | 0.962 | 1 / 0 |
| 1131202 | 0.966 | 0.968 | 0.968 | 3 / 0 |
| 1141002 | 0.959 | 0.962 | 0.960 | 4 / 0 |
| 1130204 (old template, excluded) | 0.585 | 0.586 | 0.586 | 0 / 2 |

On these enclosure-only targets, round-1 v4 was equal to v3 or slightly higher. It was higher where several enclosure rows share one name. No CPS output exists yet for the three window files.

## Aggregator v2 (round-1 fix S4)

`aggregate_qualification050.py` is the frozen O31 gate `aggregate_qualification.py` (`d48b81f3…`), re-pinned to v4. The frozen v1 file is not changed, and it refuses v4 outputs (`EVALUATOR_SCHEMA`).

Apart from the module docstring, the code differs from v1 in three places, and a test checks this on the AST:
- `EVALUATOR_SCHEMA = 'cps.target-comparison050.v1'`;
- `EVALUATOR_SHA256` = the sha256 of `compare_target050.py` above;
- `v3_per_row_AB` is pooled as `reported_not_gating.v3_per_row_AB_pooled`, because O35 says v3 numbers are reported beside v4. It does not gate.

The gate output keeps schema `cps.qualification-gate.v1`. A v2 output is told apart by `evaluator_schema`, `evaluator_sha256`, `inputs.aggregator_sha256` and the added field.

## Tests

All tests use invented data only.

| Suite | Result | What it covers |
|---|---:|---|
| `tests/test_compare_target049.py` (frozen v3, not touched) | 36/36 | v3 unchanged |
| `tests/test_compare_target050.py` | 43/43 | the original 21 checks, with test 10 changed on purpose to B 2/2 (two panels that share a size count per panel); B size units and `_assign_max` against brute force on 300 random matrices; `ab_row_check` contents; disclosed cases 1, 3, 4 and 5 (case 2 is reviewer R8); S1: `v2_alignment` equals `compare_target048` on 168 random cases without a K–O tie, and `v3_per_row_AB` equals frozen v3 on the same cases; per-field sums in both modes on all 200 random cases; S2: a tie case gives byte-identical output in 10 separate `-I` processes, and the first value in row order wins |
| `tests/test_review050_fixtures.py` (reviewer R1–R12, byte-identical to the reviewer's file) | 12/12 | shared, swapped and rotated sizes; rotated names and labels; device-row A/B; group-wide targets; tie repeatability; per-field sums |
| `tests/test_aggregate_qualification050.py` | 52/52 | the 43 v1 checks adapted to v4-shaped outputs, plus the pins, the AST identity with v1, refusal of v3 and round-1 v4 outputs, and `v3_per_row_AB` reported but not gating |
| `tests/test_aggregate_real_eval050.py` | 11/11 | genuine v4 CLI outputs: the six v1 checks, plus group-wide targets passing under v4, pooled `v3_per_row_AB` equal to frozen v3 and pooled `v2_alignment` equal to frozen v2 on the same files, and the frozen v1 aggregator refusing v4 outputs |

The new S1 and S2 checks were mutation-tested. With the round-1 `v2_alignment` line restored, 5 checks fail. With the old `max(set(...))` tie-break restored, the 10-process check failed in each of 3 runs.

## Open before the freeze

- **Delta review** of `compare_target050.py`, `aggregate_qualification050.py` and the tests.
- **Freeze records** for evaluator v4 and aggregator v2, in the form of `FREEZE_049.json` and `FREEZE_AGG_O31.json`.
- **S5, the next harness version.** The harness README, `EVALUATOR_BRIEF_TEMPLATE` and the review checklist still name v3, describe A/B as per row and call `v2_alignment` the v2 number. They also lack the `ab_row_check` critical-error class above.
- **The post-hoc development table** above.
