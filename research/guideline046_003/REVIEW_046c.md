# Independent semantic review record for candidate 046c

- Date: 2026-11-03 (Asia/Taipei). Reviewer: a fresh Claude Code subagent context (observed model `claude-opus-5-5`), independent of the package author. It read only the public package, the audit and earlier protocols. It did not read private evidence, the naming study or the web.
- Purpose: the **semantic** review of the field-role and allocation rules. Audit 048 (finding P-1) found that 046b was admitted without one.
- Result: **SEMANTIC_APPROVE** after three rounds. This is not deployment approval.

| Round | Verdict | Main findings |
|---|---|---|
| 1 | APPROVE_AFTER_LISTED_FIXES | 5 blocking: non-deterministic R12; R3 against N18; R4 contiguity and C joiner; how undecided tokens are written in each placement; EXAMPLE R005 null reason breaking R9. 9 should-fix: R1 overlap, R2 definitions, R3 gaps, R5 standards, R6 labels, R7 glosses, R8 tuning risk, R9 scope, R11 unresolved. |
| 2 | APPROVE_AFTER_LISTED_FIXES | 11 of 14 fixed. Remaining: R8 first sentence, stale guideline line, the R1b joining form, R2 whitespace scope and phase words, EXAMPLE R003. |
| 3 | APPROVE_AFTER_LISTED_FIXES, then **SEMANTIC_APPROVE** | The R14–R24 clarifications were added under the R13 gate. R16 was blocking because it overrode decided rules. Should-fix: R14, R18, R20, R22, R24, A31. All were applied verbatim and the final check passed. |

Owner decisions applied (2026-11-03): supply-basis qualifiers go to D; K/M/N inferred from document furniture is a critical error; the runtime is `claude-opus-5-5`. See [DECISIONS_046b.md](../guideline046_002/DECISIONS_046b.md).

Route and interface: unchanged from 046b (`cps046b-route.v2`, reviewed). The 046c route tests pass 114/114 with corrected invented fixtures.

Disclosure, in line with audit finding P-3: R14–R24 answer generic questions raised by the independent 1141210 source-expectation author under the R13 consistency gate. They were declared before any 046c generation, and the package author did not see 1141210 content.

## Evaluator compare_source047 (component-capable)

An independent code reviewer (a fresh context, observed model `claude-opus-5-5`) reviewed it in three rounds:

1. APPROVE_AFTER_LISTED_FIXES. Two blocking items: the basis-location direction and lax link defaults, and gate loopholes.
2. Confirmation: APPROVE_AFTER_LISTED_FIXES. Four small fixes: parent-ID typing, duplicate columns, D4 tests, and recording the limitations.
3. **APPROVE_FOR_FREEZE** at sha256 `d0959cb22fc67ca75798645127c070346a3ee148c183d03c3a0844ce03889dad`.

The evaluator tests pass 29/29. Detail-only results equal the frozen 043 comparator, and the 043 pin is unchanged. The recorded limitations L1–L4 are in the module docstring.
