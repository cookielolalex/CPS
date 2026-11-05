# Qualification eligibility screen, years 113–115 (2026-11-04)

**Result:** 20 independently eligible non-reserved pairs can be reached only if three things hold:
1. the large-workbook method is built and admitted;
2. all 20 current-template candidates pass family-independence review;
3. none fails another obligation.

There is no margin. Without the large-workbook method the count is 10, a shortfall of 10. The 10 reserved pairs are possible on count, with 21 reserved cases in scope, but their templates cannot be checked until every output is frozen.

This is a screen only. Nothing was generated or scored, and no case is admitted by it.

## Scope and method

- **Scope:**
  - Owner decision O22: years 113–115 only.
  - O21: current-template targets only.
  - O17: the 材料清單 is the job input, with the contract as fallback.
- **Excluded as exposed:** 47 cases in 113–115 were used in tuning, studies or trials (the evaluation target sets, the creator-practice and naming studies, and the development trials). Rolling-validation cases 1150107, 1140908 and 1141210 are among them.
- **Who read what:**
  - The screen ran in an eligibility role, separate from generation and tuning. For non-reserved candidates it opened sources and targets for template and trace counts.
  - For reserved cases it read Drive listing titles only.
  - The orchestrating session read only verdicts and counts. Nothing from the screen goes to a generator or into candidate design.
  - The screen's private record is kept off GitHub.
- **Earlier access:** the private exposure record also logs evaluator-only access, on 2026-10-30, to all 153 development targets, which includes every candidate here. No tuning use of these 22 is recorded.

## Non-reserved candidates (22)

The pool is 15 rolling-validation cases (18 in 113–115, minus the 3 exposed) and 7 unexposed tuning cases.

| Verdict | Count | Cases |
|---|---:|---|
| Eligible, ordinary size | 10 | 1130708, 1131005, 1140406, 1141006, 1141101, 1150103, 1150203, 1150306, 1150404, 1150506 |
| Large: needs the large-workbook method | 10 | 1130311, 1130405, 1130601, 1131007, 1131106, 1140101, 1140603, 1140608, 1141008, 1150202 |
| Ineligible: old template (O21) | 2 | 1130109, 1130208 |

**Checks:**
- **Target hash:** 22/22 match the registry, with 0 mismatches.
- **Panel-dimension plus sign:** 0 exclusions, using the installed screener v1.7. This screening alone does not establish gold eligibility.
- **Internal-design targets:** 0 exclusions.
- **Job input:** 21 of 22 have a 材料清單. 1141006 is a contract job; its contract matches the registry source hash.
- **Revision:** the creator's copied source sheet is at least 99.3% contained in the 材料清單 in 20 of the 20 cases where both could be compared.
- **Timing:** in 20 of 20 cases the source's last save is not later than the target's. This is weak evidence, because the targets' created dates come from the template.
- **Large:** the whole 材料清單 file holds 3,296–15,947 content cells, against a 2,500-cell threshold. Sheet choice must come from the source, never from the target, so these stay large until a reviewed scope method exists.
- **For owner review:** two current-template targets carry values in H, which the evaluator does not score. One has a single status cell. The other has 46 numbers that are neither the unit price nor the amount.
- **Trace:** in 4 candidates, fewer than 80% of target rows trace to 材料清單 lines; the range is 0.647–0.802. The untraced rows may come from contract lines, which the screen was not allowed to open. This is not an exclusion rule. Under O17 such rows would count as misses.

**Family independence: not yet established.** Ten candidates share a project series by name with an exposed case, another candidate or a reserved case: 1130311, 1131005, 1131007, 1131106, 1140101, 1140608, 1150103, 1150202, 1150306 and 1150506. An independent family review is running. It looks at customer and project identity and at source-description similarity.

## Reserved (113–115, listing only)

| Check | Count |
|---|---:|
| Reserved cases in scope | 21 |
| 未填 listed | 21 |
| A file with 材料 in its title listed | 21, of which 20 are titled as a material list and 1 is a quotation only (possibly a contract job) |
| Template check | pending, closed until all outputs are frozen |

Two of the 22 non-reserved early-113 targets use the old template. Some early-113 reserved targets may therefore also fall under O21 once opened.

## Consequences

1. **The large-workbook scope method is on the critical path.** It covers 10 of the 20 reachable non-reserved pairs. Under 046f, rows come only from the priced bill sheet (R49), so the method is a reviewed scope stage that selects the sheet, not chunked reading of every sheet. A source-only structure study on exposed tuning cases is running.
2. **Any family-dependence finding creates a shortfall.** Even with the scope method, the bar of 20 non-reserved plus 10 reserved cannot then be met from 113–115. This would go to the owner as a question about the pool. It is not a reason to lower the bar.

---

## Family-independence review and the qualification pool (2026-11-05)

An independent eligibility-role review read the candidates' source files, an extra 16 exposed material lists and listing metadata. Reserved cases were checked from listing titles only. Two kinds of evidence were weighed:
- identity: customer plus project or site, ignoring phase, section and area suffixes;
- containment: the share of priced-line descriptions in common. This was evidence, not a verdict, because standard designer specifications can reach 0.87–0.96 even across different projects.

**Non-reserved (20 current-template candidates):**

| Verdict | Cases |
|---|---|
| Independent (12, review verdict) | 1130405, 1130601, 1130708, 1131005, 1131007, 1140406, 1140603, 1141006, 1141008, 1141101, 1150203, 1150404 |
| Independent, orchestrator's call on a REVIEW verdict (1) | 1130311. Its related case is a 112 rolling-validation case never used for tuning; its overlap with exposed cases is ≤0.16, and the customer is different. |
| Kept for its same-series group (1) | 1131106. Only one case per group counts. 1150103 is dropped, which also resolves the group's link to a reserved case. |
| Counted under owner decision O26, "Accept borderline cases" (1) | 1150202, whose overlap with an exposed case (0.646) comes from a shared designer specification library |
| Same family as an exposed case (4) | 1140101, 1140608, 1150306, 1150506 |
| Same group as a kept case (1) | 1150103 |

Two pairs fall below the 0.6 containment criterion and have different identities, so both members are counted: 1130708/1150203 (0.566) and 1131007/1141008 (0.589).

**Reserved, years 113–115, from listings only:**
- 21 in scope;
- 4 excluded as tied to exposed project series;
- 1 excluded as in the same group as kept candidate 1131106;
- 1 duplicate-family pair, of which one counts, with a pre-declared alternate recorded privately;
- 1 weakly tied case counted under O26.

That leaves **15**.

**Pool: exactly 30.** It is 15 non-reserved and 15 reserved, with no margin (O25, O26):
- 7 non-reserved are ordinary size: 1130708, 1131005, 1140406, 1141006, 1141101, 1150203, 1150404;
- 8 need the large-workbook scope stage: 1130311, 1130405, 1130601, 1131007, 1131106, 1140603, 1141008, 1150202.

Any pair found ineligible later, including a reserved target that turns out to be old-template when opened, leaves the bar unreachable from this pool and goes back to the owner. Under AGENTS.md, all 38 reserved outputs, not just these 15, must be generated and frozen before any reserved answer is opened.

**Other decisions recorded on 2026-11-05:**
- Evaluator v3 (`compare_target049`, gap fill) was approved after two reviews and frozen at `b600c046…`. It governs qualification (O23).
- The 0.75 C/D target is reported only (O24).
- The company tables are the owner-approved recommended entries (O27). Neither was built from any qualification or reserved case.
