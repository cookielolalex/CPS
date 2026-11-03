# Candidate 046d: plan (frozen 2026-11-03, manifest `b2c5177a…`; see REVIEW_046d.md)

`package/` starts as an exact copy of frozen 046c (`research/guideline046_003/package/`, manifest `4d8602db…`). 046c stays untouched. Every change below must be generic, use invented examples only, and pass an independent semantic review plus the route tests before any admission. The changes come from three places:

1. **Known defect from the 1141210 trial.** The analysis-component example in `EXAMPLE_RESPONSE.json` leaves E/F/L null, and its null reasons claim that component rows do not carry their unit, quantity or project identity. That contradicts the FIELD_ROLES E/F definitions and the R21 basis cells, and it led a reader to drop component E/F/L. Planned fix:
   - add an explicit rule: a component row carries its own literal unit (E) and per-unit quantity (F) from the same cells as its link basis, never multiplied, plus the same explicitly supported project-level K–O values that apply to demand rows;
   - correct the example so it follows that rule.
2. **Gate extension (R13 on examples).** Every value and null reason in `EXAMPLE_RESPONSE.json` and every expected answer in the synthetic cases must follow from a FIELD_ROLES or guideline sentence. The semantic reviewer checks this the same way it checks evaluator conventions.
3. **Policy backlog Q1–Q13** (`research/guideline046_003/POLICY_BACKLOG_046d.md`), plus the generic error classes from 046c development batch 1. Those classes are added only after the batch-1 evaluations are frozen.
   - Each question is decided in one sentence with an invented example.
   - If a decision needs an owner ruling, it is asked as a question and the class stays undecided, keeping declared alternatives.

Not in scope: the route tool and schemas, unless a review finds an interface defect. The evaluator `compare_source047.py` stays frozen. Its recorded limitations (no A/B alternatives, no optional rows, census by locator only) are handled through declared exclusions and manual obligations.
