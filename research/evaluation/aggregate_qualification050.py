"""Qualification gate aggregation for CPS, v2 (owner decisions O31 and O35, 2026-11-05). Evaluation role only.
v2 is the frozen v1 (`aggregate_qualification.py`, sha256 d48b81f3...) re-pinned to evaluator v4 under O35
("the O31 gate aggregator is re-pinned to v4"); the gate logic is unchanged. v1 stays frozen and refuses
v4 outputs (EVALUATOR_SCHEMA). The gate output schema is `cps.qualification-gate.v2` (v1 writes
`cps.qualification-gate.v1`); it also adds `reported_not_gating.v3_per_row_AB_pooled`.

Gate (declared before any qualification output is scored):
  For each of the two original readers (A and B), over the frozen qualification pool (30 pairs, O25/O26):
    pooled = sum(matched) / sum(counted) of the governing `normalized` mode of evaluator v4
             (`compare_target050.py`, schema `cps.target-comparison050.v1`, sha256 below; O35);
    pooled >= 0.95 and every case's governing score >= 0.90.
  The deployment-bar element "historical match" passes only when both readers pass.
  Fail closed:
    - a reader set other than exactly A and B;
    - a pool that is not a list of distinct non-empty strings, or whose canonical sha256 differs from --pool-sha;
    - a pool case with no comparison, or no declared target sha256, or a target sha256 shared by two cases;
    - a comparison not bound to its case: inputs.target_sha256 differs from the case's declared target, or
      inputs.carrier_sha256 differs from the entry's declared carrier;
    - both readers bound to the same carrier for one case, or one comparison path used twice;
    - a comparison whose schema or recorded evaluator sha256 is not the frozen one, or whose score fields are
      inconsistent with its counts (not evaluator output);
    - a comparison whose file sha256 differs from the manifest;
    - a duplicate case or reader, including duplicate JSON keys;
    - a case outside the pool;
    - counts that are not non-negative integers with matched <= counted;
    - a case with counted == 0 (nothing to score: not an eligible pair; reported as ZERO_COUNTED).
  The comparison files are trusted to come from the frozen evaluator only through these checks; the declared
  target and carrier hashes must be the ones pinned in the frozen expectations and output records.
  A nonattempt is evaluated as an empty carrier (`items: []`), so it scores 0 and fails the floor.
  Reported, not gating:
    - pooled `description_cd` (O24, target 0.75);
    - the v2-alignment pooled score (`v2_alignment`, the genuine v2 number);
    - the pooled v3 score (`v3_per_row_AB`: v3 scoring, A and B per row, on the v4 pairs), because O35
      says v3 numbers are reported beside v4 in qualification;
    - the count of gap-filled pairs.
  This script decides only the historical-match element. Critical errors, saved QA, visual QA,
  two-reader repeatability and the other bar elements are separate obligations.

Manifest (JSON):
  {"pool": ["<case>", ...],
   "targets": {"<case>": "<target sha256>", ...},
   "readers": {"A": {"<case>": {"path": "...COMPARISON.json", "sha256": "...", "carrier_sha256": "..."}, ...},
               "B": {...}}}
Usage: python3 -I -B aggregate_qualification.py --manifest M.json --manifest-sha HEX --pool-sha HEX --out OUT.json
  --pool-sha is sha256 of json.dumps(sorted(pool), ensure_ascii=False, separators=(',', ':')) in UTF-8.
  OUT.json must not exist.
"""
import argparse, hashlib, json, re
from pathlib import Path

VERSION = 'cps.qualification-gate.v2'
EVALUATOR_SCHEMA = 'cps.target-comparison050.v1'
EVALUATOR_SHA256 = 'fc723405c41ca4a46e4318913ecd742316682c2f9edb8b35ae59ca1a9acc3859'
POOLED_MIN = 0.95
CASE_FLOOR = 0.90
POOL_SIZE = 30
READERS = ('A', 'B')
HEX64 = re.compile(r'[0-9a-f]{64}')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _no_dup(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f'DUPLICATE_JSON_KEY {k!r}')
        d[k] = v
    return d


def load_json(p):
    return json.loads(Path(p).read_text(encoding='utf-8'), object_pairs_hook=_no_dup)


def pool_sha(pool):
    return hashlib.sha256(json.dumps(sorted(pool), ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def _hex(x):
    return isinstance(x, str) and HEX64.fullmatch(x) is not None


def _count(x):
    return type(x) is int and x >= 0


def gate(manifest, pool_size=POOL_SIZE, readers_required=READERS):
    problems = []
    pool = manifest.get('pool') if isinstance(manifest, dict) else None
    if not (isinstance(pool, list) and all(isinstance(c, str) and c for c in pool)):
        problems.append({'code': 'POOL_TYPE'}); pool = []
    if len(pool) != len(set(pool)):
        problems.append({'code': 'POOL_DUPLICATE_CASE'})
    pool = list(dict.fromkeys(pool))
    if len(pool) != pool_size:
        problems.append({'code': 'POOL_SIZE', 'expected': pool_size, 'found': len(pool)})
    targets = manifest.get('targets') if isinstance(manifest, dict) else None
    if not isinstance(targets, dict):
        problems.append({'code': 'TARGETS_TYPE'}); targets = {}
    for cid in pool:
        if not _hex(targets.get(cid)):
            problems.append({'code': 'TARGET_SHA_MISSING', 'case': cid})
    for cid in targets:
        if cid not in pool:
            problems.append({'code': 'TARGET_OUTSIDE_POOL', 'case': cid})
    tv = [targets.get(c) for c in pool if _hex(targets.get(c))]
    if len(tv) != len(set(tv)):
        problems.append({'code': 'TARGET_SHARED_BY_CASES'})
    readers = manifest.get('readers') if isinstance(manifest, dict) else None
    if not isinstance(readers, dict) or not readers:
        problems.append({'code': 'NO_READERS'}); readers = {}
    elif set(readers) != set(readers_required):
        problems.append({'code': 'READER_SET', 'expected': sorted(readers_required), 'found': sorted(readers)})
    out = {'schema': VERSION, 'decision': 'O31', 'pooled_min': POOLED_MIN, 'case_floor': CASE_FLOOR,
           'evaluator_schema': EVALUATOR_SCHEMA, 'evaluator_sha256': EVALUATOR_SHA256,
           'pool_canonical_sha256': pool_sha(pool), 'readers': {}}
    paths, carriers = {}, {}
    for rd, cases in sorted(readers.items()):
        rp = []
        per, m_sum, c_sum, d_m, d_c, v2_m, v2_c, v3_m, v3_c, filled = {}, 0, 0, 0, 0, 0, 0, 0, 0, 0
        if not isinstance(cases, dict):
            rp.append({'code': 'READER_TYPE'}); cases = {}
        for cid in cases:
            if cid not in pool:
                rp.append({'code': 'CASE_OUTSIDE_POOL', 'case': cid})
        for cid in pool:
            e = cases.get(cid)
            if e is None:
                rp.append({'code': 'MISSING_COMPARISON', 'case': cid}); continue
            if not (isinstance(e, dict) and isinstance(e.get('path'), str) and _hex(e.get('sha256')) and _hex(e.get('carrier_sha256'))):
                rp.append({'code': 'ENTRY_TYPE', 'case': cid}); continue
            key = str(Path(e['path']).resolve())
            if key in paths:
                rp.append({'code': 'COMPARISON_PATH_REUSED', 'case': cid, 'also': paths[key]}); continue
            paths[key] = [rd, cid]
            other = carriers.setdefault(cid, {})
            if e['carrier_sha256'] in other.values():
                rp.append({'code': 'READERS_SHARE_CARRIER', 'case': cid}); continue
            other[rd] = e['carrier_sha256']
            if sha(e['path']) != e['sha256']:
                rp.append({'code': 'COMPARISON_SHA_MISMATCH', 'case': cid}); continue
            o = load_json(e['path'])
            if not isinstance(o, dict) or o.get('schema') != EVALUATOR_SCHEMA:
                rp.append({'code': 'EVALUATOR_SCHEMA', 'case': cid, 'found': o.get('schema') if isinstance(o, dict) else None}); continue
            inp = o.get('inputs') if isinstance(o.get('inputs'), dict) else {}
            if inp.get('evaluator_sha256') != EVALUATOR_SHA256:
                rp.append({'code': 'EVALUATOR_SHA256', 'case': cid}); continue
            if inp.get('target_sha256') != targets.get(cid):
                rp.append({'code': 'TARGET_BINDING', 'case': cid}); continue
            if inp.get('carrier_sha256') != e['carrier_sha256']:
                rp.append({'code': 'CARRIER_BINDING', 'case': cid}); continue
            g = (o.get('modes') or {}).get('normalized')
            if not isinstance(g, dict) or not _count(g.get('matched')) or not _count(g.get('counted')) or g['matched'] > g['counted']:
                rp.append({'code': 'BAD_COUNTS', 'case': cid}); continue
            score = (g['matched'] / g['counted']) if g['counted'] else None
            pf = g.get('per_field')
            gv = o.get('governing') if isinstance(o.get('governing'), dict) else {}
            if g.get('score') != score or gv.get('mode') != 'normalized' or gv.get('score') != score \
                    or not isinstance(pf, dict) or not all(isinstance(v, dict) and _count(v.get('matched')) and _count(v.get('counted')) for v in pf.values()) \
                    or sum(v['matched'] for v in pf.values()) != g['matched'] or sum(v['counted'] for v in pf.values()) != g['counted']:
                rp.append({'code': 'EVALUATOR_OUTPUT_INCONSISTENT', 'case': cid}); continue
            if not g['counted']:
                rp.append({'code': 'ZERO_COUNTED', 'case': cid})
            per[cid] = {'matched': g['matched'], 'counted': g['counted'], 'score': score,
                        'floor_met': score is not None and score >= CASE_FLOOR,
                        'gap_filled_pairs': len(o.get('gap_filled_pairs') or [])}
            m_sum += g['matched']; c_sum += g['counted']
            d = o.get('description_cd') or {}; d_m += d.get('matched', 0); d_c += d.get('counted', 0)
            v = o.get('v2_alignment') or {}; v2_m += v.get('normalized_matched', 0); v2_c += v.get('normalized_counted', 0)
            v = o.get('v3_per_row_AB') or {}; v3_m += v.get('normalized_matched', 0); v3_c += v.get('normalized_counted', 0)
            filled += per[cid]['gap_filled_pairs']
        pooled = (m_sum / c_sum) if c_sum else None
        below = sorted(c for c, x in per.items() if not x['floor_met'])
        complete = not rp and len(per) == len(pool)
        passed = bool(complete and not problems and pooled is not None and pooled >= POOLED_MIN and not below)
        scores = [x['score'] for x in per.values()]
        out['readers'][rd] = {'cases_scored': len(per), 'complete': complete,
                              'pooled': {'matched': m_sum, 'counted': c_sum, 'score': pooled},
                              'min_case_score': None if (not scores or None in scores) else min(scores),
                              'cases_below_floor': below, 'problems': rp, 'pass': passed,
                              'reported_not_gating': {'description_cd_pooled': (d_m / d_c) if d_c else None,
                                                      'v2_alignment_pooled': (v2_m / v2_c) if v2_c else None,
                                                      'v3_per_row_AB_pooled': (v3_m / v3_c) if v3_c else None,
                                                      'gap_filled_pairs_total': filled},
                              'per_case': per}
    out['pool_problems'] = problems
    out['historical_match_element_passes'] = bool(set(out['readers']) == set(readers_required) and not problems
                                                  and all(r['pass'] for r in out['readers'].values()))
    return out


def main():
    ap = argparse.ArgumentParser()
    for k in ('manifest', 'manifest-sha', 'pool-sha', 'out'):
        ap.add_argument('--' + k, required=True)
    a = ap.parse_args()
    if sha(a.manifest) != a.manifest_sha:
        raise SystemExit('MANIFEST_SHA_MISMATCH')
    m = load_json(a.manifest)
    res = gate(m)
    if res['pool_canonical_sha256'] != a.pool_sha:
        res['pool_problems'].append({'code': 'POOL_SHA_MISMATCH'})
        res['historical_match_element_passes'] = False
        for r in res['readers'].values():
            r['pass'] = False
    res['inputs'] = {'manifest_sha256': a.manifest_sha, 'pool_sha256': a.pool_sha, 'aggregator_sha256': sha(__file__)}
    with open(a.out, 'x', encoding='utf-8') as f:
        f.write(json.dumps(res, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({rd: {'pooled': r['pooled']['score'], 'complete': r['complete'], 'min_case': r['min_case_score'],
                           'below_floor': len(r['cases_below_floor']), 'problems': len(r['problems']), 'pass': r['pass']}
                      for rd, r in res['readers'].items()}
                     | {'pool_problems': len(res['pool_problems']),
                        'historical_match_element_passes': res['historical_match_element_passes']}))


if __name__ == '__main__':
    main()
