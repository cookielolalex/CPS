"""Invented-fixture tests for aggregate_qualification (O31 gate). No real case data.
Run: python3 -I -B research/evaluation/tests/test_aggregate_qualification.py"""
import hashlib, importlib.util, json, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ag', HERE.parent / 'aggregate_qualification.py')
ag = importlib.util.module_from_spec(spec); spec.loader.exec_module(ag)
TMP = Path(tempfile.mkdtemp(prefix='agq_'))
FAIL = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' :: ' + str(detail)))
    if not cond:
        FAIL.append(name)


def comp(case, reader, matched, counted, schema=ag.EVALUATOR_SCHEMA, ev=ag.EVALUATOR_SHA256, filled=0, desc=(7, 10)):
    o = {'schema': schema, 'modes': {'normalized': {'matched': matched, 'counted': counted}},
         'description_cd': {'matched': desc[0], 'counted': desc[1]},
         'v2_alignment': {'normalized_matched': max(0, matched - filled), 'normalized_counted': counted},
         'gap_filled_pairs': [{}] * filled, 'inputs': {'evaluator_sha256': ev}}
    p = TMP / f'{reader}_{case}.json'
    p.write_text(json.dumps(o), encoding='utf-8')
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


POOL = [f'C{k:02d}' for k in range(30)]


def manifest(scores_a, scores_b=None, **kw):
    m = {'pool': list(POOL), 'readers': {}}
    for rd, sc in (('A', scores_a), ('B', scores_b if scores_b is not None else scores_a)):
        m['readers'][rd] = {c: comp(c, rd, s[0], s[1], **kw) for c, s in zip(POOL, sc)}
    return m


ok = [(97, 100)] * 30
r = ag.gate(manifest(ok))
check('all 0.97: both readers pass', r['historical_match_element_passes'] and r['readers']['A']['pass'], r['readers']['A']['pooled'])

floor_case = [(97, 100)] * 29 + [(89, 100)]
r = ag.gate(manifest(floor_case))
check('one case 0.89: fails the 0.90 floor', not r['readers']['A']['pass'] and r['readers']['A']['cases_below_floor'] == ['C29'], r['readers']['A']['cases_below_floor'])

at_floor = [(97, 100)] * 29 + [(90, 100)]
r = ag.gate(manifest(at_floor))
check('a case exactly 0.90 meets the floor', r['readers']['A']['pass'], r['readers']['A'])

pooled_low = [(94, 100)] * 30
r = ag.gate(manifest(pooled_low))
check('all 0.94: pooled below 0.95 fails', not r['readers']['A']['pass'] and abs(r['readers']['A']['pooled']['score'] - 0.94) < 1e-12, r['readers']['A']['pooled'])

weighted = [(1000, 1000)] + [(91, 100)] * 29
r = ag.gate(manifest(weighted))
s = r['readers']['A']['pooled']['score']
check('pooled is matched/counted, weighted by counted', abs(s - (1000 + 91 * 29) / (1000 + 100 * 29)) < 1e-12 and r['readers']['A']['pass'] == (s >= 0.95), s)

r = ag.gate(manifest(ok, floor_case))
check('reader B fails: element fails even though A passes', r['readers']['A']['pass'] and not r['readers']['B']['pass'] and not r['historical_match_element_passes'], r['historical_match_element_passes'])

m = manifest(ok); del m['readers']['A']['C05']
r = ag.gate(m)
check('missing comparison fails closed', not r['readers']['A']['pass'] and any(p['code'] == 'MISSING_COMPARISON' for p in r['readers']['A']['problems']), r['readers']['A']['problems'])

m = manifest(ok); Path(m['readers']['A']['C03']['path']).write_text('{}', encoding='utf-8')
r = ag.gate(m)
check('tampered comparison file fails closed', any(p['code'] == 'COMPARISON_SHA_MISMATCH' for p in r['readers']['A']['problems']), r['readers']['A']['problems'])

r = ag.gate(manifest(ok, schema='cps.target-comparison048.v2'))
check('v2 comparisons are refused', not r['historical_match_element_passes'] and r['readers']['A']['problems'][0]['code'] == 'EVALUATOR_SCHEMA', r['readers']['A']['problems'][:1])

r = ag.gate(manifest(ok, ev='0' * 64))
check('wrong evaluator sha256 refused', r['readers']['A']['problems'][0]['code'] == 'EVALUATOR_SHA256', r['readers']['A']['problems'][:1])

m = manifest(ok); m['pool'] = POOL[:29]
r = ag.gate(m)
check('pool of 29 fails (POOL_SIZE) and extra case flagged', not r['historical_match_element_passes'] and r['pool_problems'][0]['code'] == 'POOL_SIZE'
      and any(p['code'] == 'CASE_OUTSIDE_POOL' for p in r['readers']['A']['problems']), (r['pool_problems'], r['readers']['A']['problems'][:2]))

m = manifest(ok); m['pool'] = POOL + ['C00']
r = ag.gate(m)
check('duplicate pool case fails', any(p['code'] == 'POOL_DUPLICATE_CASE' for p in r['pool_problems']), r['pool_problems'])

nonattempt = [(97, 100)] * 29 + [(0, 120)]
r = ag.gate(manifest(nonattempt))
check('nonattempt (empty carrier, score 0) fails the floor', not r['readers']['A']['pass'] and 'C29' in r['readers']['A']['cases_below_floor'], r['readers']['A']['cases_below_floor'])

bad = [(97, 100)] * 29 + [(101, 100)]
r = ag.gate(manifest(bad))
check('matched > counted refused', any(p['code'] == 'BAD_COUNTS' for p in r['readers']['A']['problems']), r['readers']['A']['problems'])

r = ag.gate(manifest(ok, filled=2, desc=(6, 10)))
x = r['readers']['A']['reported_not_gating']
check('reported-not-gating fields', x['gap_filled_pairs_total'] == 60 and abs(x['description_cd_pooled'] - 0.6) < 1e-12 and x['v2_alignment_pooled'] < r['readers']['A']['pooled']['score'], x)
check('description below 0.75 does not gate (O24)', r['readers']['A']['pass'], r['readers']['A']['pass'])

print(f'{len(FAIL)} failed')
sys.exit(1 if FAIL else 0)
