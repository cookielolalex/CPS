"""Invented-fixture tests for aggregate_qualification050 (aggregator v2: the O31 gate re-pinned to evaluator v4
under O35). No real case data. Adapted from test_aggregate_qualification.py (the 43 v1 checks, kept in order,
with comparisons shaped like compare_target050 output), plus v2 checks at the end.
Run: python3 -I -B research/evaluation/tests/test_aggregate_qualification050.py
(Set AGQ_PATH to test another copy.)"""
import hashlib, importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGQ = Path(os.environ.get('AGQ_PATH', HERE.parent / 'aggregate_qualification050.py'))
spec = importlib.util.spec_from_file_location('ag', AGQ)
ag = importlib.util.module_from_spec(spec); spec.loader.exec_module(ag)
TMP = Path(tempfile.mkdtemp(prefix='agq050_'))
FAIL = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' :: ' + str(detail)))
    if not cond:
        FAIL.append(name)


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def tsha(case):
    return h('target:' + case)


def csha(case, reader):
    return h(f'carrier:{reader}:{case}')


def comp(case, reader, matched, counted, schema=ag.EVALUATOR_SCHEMA, ev=ag.EVALUATOR_SHA256, filled=0, desc=(7, 10),
         target=None, carrier=None, tag='', v3=None):
    """Shaped like compare_target050.evaluate() + main() output (v4: A/B panel positions, v3_per_row_AB,
    ab_row_check), internally consistent."""
    try:
        score = (matched / counted) if counted else None
    except TypeError:
        score = None
    pf = {'E': {'matched': matched, 'counted': counted}}
    if v3 is None:
        v3 = (matched, counted)
    o = {'schema': schema, 'modes': {'normalized': {'matched': matched, 'counted': counted, 'score': score, 'per_field': pf}},
         'governing': {'mode': 'normalized', 'score': score},
         'description_cd': {'matched': desc[0], 'counted': desc[1]},
         'v2_alignment': {'normalized_matched': max(0, (matched or 0) - filled), 'normalized_counted': counted},
         'gap_filled_pairs': [{}] * filled,
         'v3_per_row_AB': {'normalized_matched': v3[0], 'normalized_counted': v3[1]},
         'ab_row_check': {'paired_conflicts': [], 'cps_unpartnered': []},
         'inputs': {'evaluator_sha256': ev, 'target_sha256': target or tsha(case), 'carrier_sha256': carrier or csha(case, reader)}}
    p = TMP / f'{reader}_{case}{tag}.json'
    p.write_text(json.dumps(o), encoding='utf-8')
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'carrier_sha256': carrier or csha(case, reader)}


POOL = [f'C{k:02d}' for k in range(30)]


def manifest(scores_a, scores_b=None, **kw):
    m = {'pool': list(POOL), 'targets': {c: tsha(c) for c in POOL}, 'readers': {}}
    for rd, sc in (('A', scores_a), ('B', scores_b if scores_b is not None else scores_a)):
        m['readers'][rd] = {c: comp(c, rd, s[0], s[1], **kw) for c, s in zip(POOL, sc)}
    return m


def codes(r, rd='A'):
    return [p['code'] for p in r['readers'][rd]['problems']]


ok = [(97, 100)] * 30
r = ag.gate(manifest(ok))
check('all 0.97: both readers pass', r['historical_match_element_passes'] and r['readers']['A']['pass'], r)

floor_case = [(97, 100)] * 29 + [(89, 100)]
r = ag.gate(manifest(floor_case))
check('one case 0.89: fails the 0.90 floor', not r['readers']['A']['pass'] and r['readers']['A']['cases_below_floor'] == ['C29'], r['readers']['A']['cases_below_floor'])

at_floor = [(97, 100)] * 29 + [(90, 100)]
r = ag.gate(manifest(at_floor))
check('a case exactly 0.90 meets the floor', r['readers']['A']['pass'], r['readers']['A'])

r = ag.gate(manifest([(95, 100)] * 30))
check('pooled exactly 0.95 passes', r['historical_match_element_passes'], r['readers']['A']['pooled'])

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
check('missing comparison fails closed', not r['readers']['A']['pass'] and 'MISSING_COMPARISON' in codes(r), codes(r))

m = manifest(ok); Path(m['readers']['A']['C03']['path']).write_text('{}', encoding='utf-8')
r = ag.gate(m)
check('tampered comparison file fails closed', 'COMPARISON_SHA_MISMATCH' in codes(r), codes(r))

r = ag.gate(manifest(ok, schema='cps.target-comparison048.v2'))
check('v2 comparisons are refused', not r['historical_match_element_passes'] and codes(r)[0] == 'EVALUATOR_SCHEMA', codes(r)[:1])

r = ag.gate(manifest(ok, ev='0' * 64))
check('wrong evaluator sha256 refused', codes(r)[0] == 'EVALUATOR_SHA256', codes(r)[:1])

m = manifest(ok); m['pool'] = POOL[:29]; del m['targets']['C29']
r = ag.gate(m)
check('pool of 29 fails (POOL_SIZE) and extra case flagged', not r['historical_match_element_passes'] and r['pool_problems'][0]['code'] == 'POOL_SIZE'
      and 'CASE_OUTSIDE_POOL' in codes(r), (r['pool_problems'], codes(r)[:2]))

m = manifest(ok); m['pool'] = POOL + ['C00']
r = ag.gate(m)
check('duplicate pool case fails and is not double counted', any(p['code'] == 'POOL_DUPLICATE_CASE' for p in r['pool_problems'])
      and r['readers']['A']['pooled']['counted'] == 3000 and not r['historical_match_element_passes'], (r['pool_problems'], r['readers']['A']['pooled']))

nonattempt = [(97, 100)] * 29 + [(0, 120)]
r = ag.gate(manifest(nonattempt))
check('nonattempt (empty carrier, score 0) fails the floor', not r['readers']['A']['pass'] and 'C29' in r['readers']['A']['cases_below_floor'], r['readers']['A']['cases_below_floor'])

for k, bad in enumerate([(101, 100), (-1, 100), (5, -1), (97.0, 100), (True, True), (None, 100)]):
    r = ag.gate(manifest([(97, 100)] * 29 + [bad]))
    check(f'bad counts {bad} refused', 'BAD_COUNTS' in codes(r) and not r['historical_match_element_passes'], codes(r))

r = ag.gate(manifest([(97, 100)] * 29 + [(0, 0)]))
ra = r['readers']['A']
check('counted == 0: ZERO_COUNTED, below floor, min_case_score None', 'ZERO_COUNTED' in codes(r) and 'C29' in ra['cases_below_floor']
      and ra['min_case_score'] is None and not r['historical_match_element_passes'], (codes(r), ra['min_case_score']))

r = ag.gate(manifest(ok, filled=2, desc=(6, 10)))
x = r['readers']['A']['reported_not_gating']
check('reported-not-gating fields', x['gap_filled_pairs_total'] == 60 and abs(x['description_cd_pooled'] - 0.6) < 1e-12 and x['v2_alignment_pooled'] < r['readers']['A']['pooled']['score'], x)
check('description below 0.75 does not gate (O24)', r['readers']['A']['pass'], r['readers']['A']['pass'])

# --- reviewer additions -------------------------------------------------------------------
m = manifest(ok); del m['readers']['B']
r = ag.gate(m)
check('reader A only: READER_SET, element fails', not r['historical_match_element_passes'] and r['pool_problems'][0]['code'] == 'READER_SET', r['pool_problems'])

m = manifest(ok); m['readers']['A_retry'] = m['readers']['A']
r = ag.gate(m)
check('third reader: READER_SET, element fails', not r['historical_match_element_passes'] and any(p['code'] == 'READER_SET' for p in r['pool_problems']), r['pool_problems'])

for label, readers in (('readers {}', {}), ('readers absent', None)):
    m = manifest(ok)
    if readers is None:
        del m['readers']
    else:
        m['readers'] = readers
    r = ag.gate(m)
    check(f'{label}: NO_READERS', not r['historical_match_element_passes'] and r['pool_problems'][0]['code'] == 'NO_READERS', r['pool_problems'])

m = manifest(ok); m['readers']['A'] = {}
r = ag.gate(m)
check('reader with empty dict fails', not r['historical_match_element_passes'] and codes(r).count('MISSING_COMPARISON') == 30, codes(r)[:2])

m = manifest(ok); [m['readers']['B'].pop(c) for c in POOL[15:]]
r = ag.gate(m)
check('reader present for some cases only fails', not r['readers']['B']['pass'] and not r['historical_match_element_passes'], codes(r, 'B')[:2])

r = ag.gate({'pool': [], 'targets': {}, 'readers': {'A': {}, 'B': {}}})
check('empty pool fails', not r['historical_match_element_passes'] and any(p['code'] == 'POOL_SIZE' for p in r['pool_problems']), r['pool_problems'])

m = manifest(ok); m['pool'] = 'abcdefghijklmnopqrstuvwxyz0123'
r = ag.gate(m)
check('pool given as a string: POOL_TYPE', not r['historical_match_element_passes'] and r['pool_problems'][0]['code'] == 'POOL_TYPE', r['pool_problems'][:1])

m = manifest(ok); m['readers']['B'] = {c: dict(v) for c, v in m['readers']['A'].items()}
r = ag.gate(m)
check('reader B aliases reader A files: refused', not r['historical_match_element_passes'] and 'COMPARISON_PATH_REUSED' in codes(r, 'B'), codes(r, 'B')[:1])

m = manifest(ok)
for c in POOL:
    m['readers']['B'][c] = comp(c, 'B', 97, 100, carrier=csha(c, 'A'), tag='_copyA')
r = ag.gate(m)
check('reader B bound to reader A carriers: READERS_SHARE_CARRIER', not r['historical_match_element_passes'] and 'READERS_SHARE_CARRIER' in codes(r, 'B'), codes(r, 'B')[:1])

m = manifest(ok); m['readers']['A']['C05'] = dict(m['readers']['A']['C06'])
r = ag.gate(m)
check('C05 pointed at C06 comparison: refused', 'COMPARISON_PATH_REUSED' in codes(r) and not r['historical_match_element_passes'], codes(r))

m = manifest(ok); m['readers']['A']['C05'] = comp('C06', 'A', 97, 100, carrier=csha('C05', 'A'), tag='_as05')
r = ag.gate(m)
check('C05 bound to C06 target: TARGET_BINDING', 'TARGET_BINDING' in codes(r) and not r['historical_match_element_passes'], codes(r))

m = manifest(ok); m['readers']['A']['C05'] = comp('C05', 'A', 97, 100, tag='_badcar'); m['readers']['A']['C05']['carrier_sha256'] = h('other')
r = ag.gate(m)
check('declared carrier differs from comparison input: CARRIER_BINDING', 'CARRIER_BINDING' in codes(r), codes(r))

m = manifest(ok); m['targets']['C05'] = m['targets']['C06']
r = ag.gate(m)
check('two cases share a target sha: TARGET_SHARED_BY_CASES', any(p['code'] == 'TARGET_SHARED_BY_CASES' for p in r['pool_problems']) and not r['historical_match_element_passes'], r['pool_problems'])

m = manifest(ok); del m['targets']['C07']
r = ag.gate(m)
check('missing target sha: TARGET_SHA_MISSING', any(p['code'] == 'TARGET_SHA_MISSING' for p in r['pool_problems']) and not r['historical_match_element_passes'], r['pool_problems'])

m = manifest(ok)
e = m['readers']['A']['C08']; o = json.loads(Path(e['path']).read_text()); o['governing']['score'] = 0.1; o['modes']['normalized']['score'] = 0.1
Path(e['path']).write_text(json.dumps(o)); e['sha256'] = hashlib.sha256(Path(e['path']).read_bytes()).hexdigest()
r = ag.gate(m)
check('score fields inconsistent with counts: EVALUATOR_OUTPUT_INCONSISTENT', 'EVALUATOR_OUTPUT_INCONSISTENT' in codes(r), codes(r))

# CLI: duplicate JSON keys, pool sha, write-once
m = manifest(ok)
a_items = [f'"C05": {json.dumps(comp("C05", "A", 10, 100, tag="_dupbad"))}'] + [f'"{c}": {json.dumps(v)}' for c, v in m['readers']['A'].items()]
txt = '{"pool": %s, "targets": %s, "readers": {"A": {%s}, "B": %s}}' % (json.dumps(POOL), json.dumps(m['targets']), ', '.join(a_items), json.dumps(m['readers']['B']))
mp = TMP / 'dup.json'; mp.write_text(txt, encoding='utf-8')
dig = hashlib.sha256(mp.read_bytes()).hexdigest()
p = subprocess.run([sys.executable, '-I', '-B', str(AGQ), '--manifest', str(mp), '--manifest-sha', dig, '--pool-sha', ag.pool_sha(POOL),
                    '--out', str(TMP / 'dup_out.json')], capture_output=True, text=True)
check('CLI: duplicate JSON key refused, nothing written', p.returncode != 0 and 'DUPLICATE_JSON_KEY' in p.stderr and not (TMP / 'dup_out.json').exists(), p.stderr[-200:])

mp = TMP / 'good.json'; mp.write_text(json.dumps(manifest(ok)), encoding='utf-8'); dig = hashlib.sha256(mp.read_bytes()).hexdigest()
out = TMP / 'good_out.json'
p = subprocess.run([sys.executable, '-I', '-B', str(AGQ), '--manifest', str(mp), '--manifest-sha', dig, '--pool-sha', '0' * 64,
                    '--out', str(out)], capture_output=True, text=True)
check('CLI: wrong --pool-sha fails the element', p.returncode == 0 and json.loads(out.read_text())['historical_match_element_passes'] is False, p.stdout)
p = subprocess.run([sys.executable, '-I', '-B', str(AGQ), '--manifest', str(mp), '--manifest-sha', dig, '--pool-sha', ag.pool_sha(POOL),
                    '--out', str(out)], capture_output=True, text=True)
check('CLI: existing output is never overwritten', p.returncode != 0 and json.loads(out.read_text())['historical_match_element_passes'] is False, p.stderr[-200:])
out2 = TMP / 'good_out2.json'
p = subprocess.run([sys.executable, '-I', '-B', str(AGQ), '--manifest', str(mp), '--manifest-sha', dig, '--pool-sha', ag.pool_sha(POOL),
                    '--out', str(out2)], capture_output=True, text=True)
check('CLI: correct pins pass', p.returncode == 0 and json.loads(out2.read_text())['historical_match_element_passes'] is True, p.stdout + p.stderr[-200:])

# --- v2 (O35) additions ---------------------------------------------------------------------------------
check('v2 pins: v4 schema and the sha256 of compare_target050.py on disk',
      ag.EVALUATOR_SCHEMA == 'cps.target-comparison050.v1' and ag.EVALUATOR_SHA256 == hashlib.sha256((HERE.parent / 'compare_target050.py').read_bytes()).hexdigest(),
      (ag.EVALUATOR_SCHEMA, ag.EVALUATOR_SHA256))
check('v2 gate schema is cps.qualification-gate.v2 and keeps the v1 gate constants', (ag.VERSION, ag.POOLED_MIN, ag.CASE_FLOOR, ag.POOL_SIZE, ag.READERS) == ('cps.qualification-gate.v2', 0.95, 0.90, 30, ('A', 'B')),
      (ag.VERSION, ag.POOLED_MIN, ag.CASE_FLOOR, ag.POOL_SIZE, ag.READERS))

V1 = HERE.parent / 'aggregate_qualification.py'
if AGQ.resolve() == (HERE.parent / 'aggregate_qualification050.py').resolve():
    import ast

    def body(path):
        t = ast.parse(Path(path).read_text(encoding='utf-8')); t.body = t.body[1:]; return ast.unparse(t)
    exp, got = body(V1), body(AGQ)
    reps = [("VERSION = 'cps.qualification-gate.v1'", "VERSION = 'cps.qualification-gate.v2'"),
            ("EVALUATOR_SCHEMA = 'cps.target-comparison049.v1'", "EVALUATOR_SCHEMA = 'cps.target-comparison050.v1'"),
            ("EVALUATOR_SHA256 = 'b600c04619c943ec78f577c4a681df3cc3d035638fab36f9be3f946eea5904c9'", f"EVALUATOR_SHA256 = '{ag.EVALUATOR_SHA256}'"),
            ("per, m_sum, c_sum, d_m, d_c, v2_m, v2_c, filled = ({}, 0, 0, 0, 0, 0, 0, 0)",
             "per, m_sum, c_sum, d_m, d_c, v2_m, v2_c, v3_m, v3_c, filled = ({}, 0, 0, 0, 0, 0, 0, 0, 0, 0)"),
            ("            v2_c += v.get('normalized_counted', 0)\n",
             "            v2_c += v.get('normalized_counted', 0)\n            v = o.get('v3_per_row_AB') or {}\n"
             "            v3_m += v.get('normalized_matched', 0)\n            v3_c += v.get('normalized_counted', 0)\n"),
            ("'v2_alignment_pooled': v2_m / v2_c if v2_c else None, ",
             "'v2_alignment_pooled': v2_m / v2_c if v2_c else None, 'v3_per_row_AB_pooled': v3_m / v3_c if v3_c else None, ")]
    once = all(exp.count(a) == 1 for a, _ in reps)
    for a, b in reps:
        exp = exp.replace(a, b)
    check('v2 code equals frozen v1 apart from the module docstring, VERSION, the two pins and the v3_per_row_AB pooling (AST)',
          once and exp == got, 'diff aggregate_qualification.py aggregate_qualification050.py')

r = ag.gate(manifest(ok, schema='cps.target-comparison049.v1', ev='b600c04619c943ec78f577c4a681df3cc3d035638fab36f9be3f946eea5904c9'))
check('v3 (compare_target049) comparisons are refused: EVALUATOR_SCHEMA', not r['historical_match_element_passes'] and codes(r)[0] == 'EVALUATOR_SCHEMA' and codes(r).count('EVALUATOR_SCHEMA') == 30, codes(r)[:1])
r = ag.gate(manifest(ok, ev='b600c04619c943ec78f577c4a681df3cc3d035638fab36f9be3f946eea5904c9'))
check('v4 schema with the v3 evaluator sha256 is refused: EVALUATOR_SHA256', not r['historical_match_element_passes'] and codes(r)[0] == 'EVALUATOR_SHA256', codes(r)[:1])
r = ag.gate(manifest(ok, schema='cps.target-comparison050.v1', ev='feccaf21753e167a768d1cbdaf1755fdd31ad8fbcea7f7aef2f309b03c22929c'))
check('v4 schema with the pre-fix (reviewed round 1) evaluator sha256 is refused', not r['historical_match_element_passes'] and codes(r)[0] == 'EVALUATOR_SHA256', codes(r)[:1])

r = ag.gate(manifest(ok, v3=(80, 100)))
x = r['readers']['A']['reported_not_gating']
check('v3_per_row_AB pooled is reported (0.80) and does not gate (v4 pooled 0.97 passes)',
      abs(x['v3_per_row_AB_pooled'] - 0.8) < 1e-12 and r['historical_match_element_passes'] and r['readers']['A']['pooled']['score'] == 0.97, (x, r['readers']['A']['pooled']))
r = ag.gate(manifest([(85, 100)] * 30, v3=(99, 100)))
check('a high v3_per_row_AB cannot rescue a failing v4 pool', not r['historical_match_element_passes']
      and abs(r['readers']['A']['reported_not_gating']['v3_per_row_AB_pooled'] - 0.99) < 1e-12, r['readers']['A']['reported_not_gating'])
r = ag.gate(manifest([(1000, 1000)] + [(91, 100)] * 29, v3=None))
x = r['readers']['A']['reported_not_gating']
check('v3_per_row_AB pooled is weighted by its own counted', abs(x['v3_per_row_AB_pooled'] - (1000 + 91 * 29) / (1000 + 100 * 29)) < 1e-12, x)

print(f'{len(FAIL)} failed')
sys.exit(1 if FAIL else 0)
