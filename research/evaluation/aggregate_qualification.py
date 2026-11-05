"""Qualification gate aggregation for CPS (owner decision O31, 2026-11-05). Evaluation role only.

Gate (declared before any qualification output is scored):
  For each reader separately, over the frozen qualification pool (30 pairs, O25/O26):
    pooled = sum(matched) / sum(counted) of the governing `normalized` mode of evaluator v3
             (`compare_target049.py`, schema `cps.target-comparison049.v1`, frozen sha256 below);
    pooled >= 0.95 and every case's governing score >= 0.90.
  The deployment-bar element "historical match" passes only when every reader passes.
  Fail closed:
    - a pool case with no comparison;
    - a comparison not produced by the frozen evaluator (wrong schema or evaluator sha256);
    - a comparison whose file sha256 differs from the manifest;
    - a duplicate case;
    - a case outside the pool.
  A nonattempt is evaluated as an empty carrier (`items: []`), so it scores 0 and fails the floor.
  Reported, not gating:
    - pooled `description_cd` (O24, target 0.75);
    - the v2-alignment pooled score (`v2_alignment`);
    - the count of gap-filled pairs.
  This script decides only the historical-match element. Critical errors, saved QA, visual QA,
  two-reader repeatability and the other bar elements are separate obligations.

Manifest (JSON):
  {"pool": ["<case>", ...],
   "readers": {"A": {"<case>": {"path": "...COMPARISON.json", "sha256": "..."}, ...}, "B": {...}}}
Usage: python3 -I -B aggregate_qualification.py --manifest M.json --manifest-sha HEX --out OUT.json
"""
import argparse, hashlib, json
from pathlib import Path

VERSION = 'cps.qualification-gate.v1'
EVALUATOR_SCHEMA = 'cps.target-comparison049.v1'
EVALUATOR_SHA256 = 'b600c04619c943ec78f577c4a681df3cc3d035638fab36f9be3f946eea5904c9'
POOLED_MIN = 0.95
CASE_FLOOR = 0.90
POOL_SIZE = 30


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def gate(manifest, pool_size=POOL_SIZE):
    pool = manifest['pool']
    problems = []
    if len(pool) != len(set(pool)):
        problems.append({'code': 'POOL_DUPLICATE_CASE'})
    if len(set(pool)) != pool_size:
        problems.append({'code': 'POOL_SIZE', 'expected': pool_size, 'found': len(set(pool))})
    if not manifest.get('readers'):
        problems.append({'code': 'NO_READERS'})
    out = {'schema': VERSION, 'decision': 'O31', 'pooled_min': POOLED_MIN, 'case_floor': CASE_FLOOR,
           'evaluator_schema': EVALUATOR_SCHEMA, 'evaluator_sha256': EVALUATOR_SHA256, 'readers': {}}
    for rd, cases in sorted(manifest.get('readers', {}).items()):
        rp = []
        per, m_sum, c_sum, d_m, d_c, v2_m, v2_c, filled = {}, 0, 0, 0, 0, 0, 0, 0
        for cid in cases:
            if cid not in pool:
                rp.append({'code': 'CASE_OUTSIDE_POOL', 'case': cid})
        for cid in pool:
            e = cases.get(cid)
            if e is None:
                rp.append({'code': 'MISSING_COMPARISON', 'case': cid}); continue
            if sha(e['path']) != e['sha256']:
                rp.append({'code': 'COMPARISON_SHA_MISMATCH', 'case': cid}); continue
            o = json.loads(Path(e['path']).read_text(encoding='utf-8'))
            if o.get('schema') != EVALUATOR_SCHEMA:
                rp.append({'code': 'EVALUATOR_SCHEMA', 'case': cid, 'found': o.get('schema')}); continue
            if o.get('inputs', {}).get('evaluator_sha256') != EVALUATOR_SHA256:
                rp.append({'code': 'EVALUATOR_SHA256', 'case': cid}); continue
            g = o['modes']['normalized']
            if not isinstance(g.get('matched'), int) or not isinstance(g.get('counted'), int) or g['counted'] < 0 \
                    or g['matched'] < 0 or g['matched'] > g['counted']:
                rp.append({'code': 'BAD_COUNTS', 'case': cid}); continue
            score = (g['matched'] / g['counted']) if g['counted'] else None
            per[cid] = {'matched': g['matched'], 'counted': g['counted'], 'score': score,
                        'floor_met': score is not None and score >= CASE_FLOOR,
                        'gap_filled_pairs': len(o.get('gap_filled_pairs', []))}
            m_sum += g['matched']; c_sum += g['counted']
            d = o.get('description_cd', {}); d_m += d.get('matched', 0); d_c += d.get('counted', 0)
            v = o.get('v2_alignment', {}); v2_m += v.get('normalized_matched', 0); v2_c += v.get('normalized_counted', 0)
            filled += per[cid]['gap_filled_pairs']
        pooled = (m_sum / c_sum) if c_sum else None
        below = sorted(c for c, x in per.items() if not x['floor_met'])
        complete = not rp and len(per) == len(set(pool))
        passed = bool(complete and not problems and pooled is not None and pooled >= POOLED_MIN and not below)
        out['readers'][rd] = {'cases_scored': len(per), 'pooled': {'matched': m_sum, 'counted': c_sum, 'score': pooled},
                              'min_case_score': min((x['score'] for x in per.values() if x['score'] is not None), default=None),
                              'cases_below_floor': below, 'problems': rp, 'pass': passed,
                              'reported_not_gating': {'description_cd_pooled': (d_m / d_c) if d_c else None,
                                                      'v2_alignment_pooled': (v2_m / v2_c) if v2_c else None,
                                                      'gap_filled_pairs_total': filled},
                              'per_case': per}
    out['pool_problems'] = problems
    out['historical_match_element_passes'] = bool(out['readers'] and not problems and all(r['pass'] for r in out['readers'].values()))
    return out


def main():
    ap = argparse.ArgumentParser()
    for k in ('manifest', 'manifest-sha', 'out'):
        ap.add_argument('--' + k, required=True)
    a = ap.parse_args()
    if sha(a.manifest) != a.manifest_sha:
        raise SystemExit('MANIFEST_SHA_MISMATCH')
    res = gate(json.loads(Path(a.manifest).read_text(encoding='utf-8')))
    res['inputs'] = {'manifest_sha256': a.manifest_sha, 'aggregator_sha256': sha(__file__)}
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({rd: {'pooled': r['pooled']['score'], 'min_case': r['min_case_score'], 'below_floor': len(r['cases_below_floor']),
                           'problems': len(r['problems']), 'pass': r['pass']} for rd, r in res['readers'].items()}
                     | {'historical_match_element_passes': res['historical_match_element_passes']}))


if __name__ == '__main__':
    main()
