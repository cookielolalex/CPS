"""Invented-fixture tests for compare_target050 (v4, O35: A scored once per distinct value per case, B once
per size unit; the ab_row_check diagnostic; the genuine v2 number in v2_alignment; the deterministic K-O
tie-break). The reviewer fixtures R1-R12 are tests/test_review050_fixtures.py. No real case data.
Run: python3 -I -B research/evaluation/tests/test_compare_target050.py"""
import importlib.util, itertools, json, random, subprocess, sys, tempfile
from pathlib import Path
import openpyxl

HERE = Path(__file__).resolve().parent
EV = HERE.parent / 'compare_target050.py'
spec = importlib.util.spec_from_file_location('ct', EV)
ct = importlib.util.module_from_spec(spec); spec.loader.exec_module(ct)
TMP = Path(tempfile.mkdtemp(prefix='ct050_'))
N = [0]
FAIL = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' :: ' + str(detail)))
    if not cond:
        FAIL.append(name)


def row(a=None, b=None, c=None, d=None, e='只', f=1, i=None, j=None, q=None):
    v = [None] * 17
    v[0], v[1], v[2], v[3], v[4], v[5], v[8], v[9], v[16] = a, b, c, d, e, f, i, j, q
    v[11], v[12], v[13] = 'J-1', '甲公司', '乙案'
    return v


def target(rows):
    N[0] += 1
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = '未填'; ws.append(ct.LABELS)
    for r in rows:
        ws.append(r)
    p = TMP / f't{N[0]}.xlsx'; wb.save(p); return p


def carrier(rows):
    return {'items': [{'id': f'R{k + 1:03d}', 'values': r} for k, r in enumerate(rows)]}


def ev(T, C):
    return ct.evaluate(target(T), carrier(C))


PANEL, SIZE = '甲-1 控制盤', '800W*1800H*400D'
enc = row(PANEL, SIZE, '箱體', 'SUS304', '面', 1, None, '示例電機', 30000)
devs = [row(None, None, 'NFB', f'3P {10 * k}A', '只', k, f'M{k}', 'BR', 100 * k) for k in range(1, 9)]
devs_gw = [row(PANEL, SIZE, 'NFB', f'3P {10 * k}A', '只', k, f'M{k}', 'BR', 100 * k) for k in range(1, 9)]
cps = [enc] + devs

o1 = ev([enc] + devs, cps)
o2 = ev([enc] + devs_gw, cps)
check('enclosure-only target, CPS enclosure-only: 1.0', o1['governing']['score'] == 1.0, o1['governing'])
check('group-wide target, CPS enclosure-only: same score as enclosure-only (O35)', o2['governing']['score'] == o1['governing']['score'], (o1['governing']['score'], o2['governing']['score']))
check('group-wide target: A counted once', o2['modes']['normalized']['per_field']['A'] == {'matched': 1, 'counted': 1}, o2['modes']['normalized']['per_field']['A'])
check('v3 diagnostic shows the per-row penalty for group-wide', o2['v3_per_row_AB']['normalized_score'] < o2['governing']['score'], o2['v3_per_row_AB'])

wrong = row('乙 控制盤', SIZE, '箱體', 'SUS304', '面', 1, None, '示例電機', 30000)
o3 = ev([enc] + devs_gw, [wrong] + devs)
check('wrong panel name counts once (A 0/1)', o3['modes']['normalized']['per_field']['A'] == {'matched': 0, 'counted': 1}, o3['modes']['normalized']['per_field']['A'])
check('B still matched when only A is wrong', o3['modes']['normalized']['per_field']['B'] == {'matched': 1, 'counted': 1}, o3['modes']['normalized']['per_field']['B'])

nab = row(None, None, '箱體', 'SUS304', '面', 1, None, '示例電機', 30000)
o4 = ev([enc] + devs, [nab] + devs)
check('missing panel in CPS counts A and B once each', o4['modes']['normalized']['per_field']['A'] == {'matched': 0, 'counted': 1} and o4['modes']['normalized']['per_field']['B'] == {'matched': 0, 'counted': 1}, o4['modes']['normalized']['per_field'])

enc2 = row('丙 分電箱', '400W*600H*200D', '箱體', None, '面', 1, None, '示例電機', 9000)
o5 = ev([enc] + devs, [enc] + devs + [enc2])
check('extra CPS panel counts once (A 1/2)', o5['modes']['normalized']['per_field']['A'] == {'matched': 1, 'counted': 2}, o5['modes']['normalized']['per_field']['A'])

o6 = ev([enc, enc2] + devs, [enc, enc2] + devs)
check('two panels, both right: A 2/2, B 2/2', o6['modes']['normalized']['per_field']['A'] == {'matched': 2, 'counted': 2} and o6['modes']['normalized']['per_field']['B'] == {'matched': 2, 'counted': 2}, o6['modes']['normalized']['per_field'])

same_b = row('丁 控制盤', SIZE, '箱體', None, '面', 1, None, '示例電機', 30000)
o7 = ev([enc, same_b] + devs, [enc, same_b] + devs)
check('two panels sharing one size: B counted per panel (2/2)', o7['modes']['normalized']['per_field']['B'] == {'matched': 2, 'counted': 2}, o7['modes']['normalized']['per_field']['B'])

o8 = ev(devs, devs)
check('no A/B on either side: no A/B positions', 'A' not in o8['modes']['normalized']['per_field'] and 'B' not in o8['modes']['normalized']['per_field'], o8['modes']['normalized']['per_field'].keys())

for name, o in (('o2', o2), ('o3', o3), ('o5', o5), ('o6', o6)):
    g = o['modes']['normalized']
    check(f'{name}: per_field sums equal matched/counted (aggregator consistency)',
          sum(v['matched'] for v in g['per_field'].values()) == g['matched'] and sum(v['counted'] for v in g['per_field'].values()) == g['counted'], g)
    check(f'{name}: governing score equals matched/counted', o['governing']['score'] == g['matched'] / g['counted'], o['governing'])

check('schema v4', o1['schema'] == 'cps.target-comparison050.v1', o1['schema'])

# rows and other fields are scored per row exactly as in v3
spec3 = importlib.util.spec_from_file_location('ct3', HERE.parent / 'compare_target049.py')
ct3 = importlib.util.module_from_spec(spec3); spec3.loader.exec_module(ct3)
T9 = [row(None, None, 'NFB', '3P 20A', '只', 2, 'X', 'Y', 450), row(None, None, 'MC', 'AC220V', '只', 3, 'Z', 'Y', 900)]
C9 = [row(None, None, 'NFB', '3P 20A', '只', 2, 'X', 'Y', 450), row(None, None, '完全不同', None, '只', 3, 'Z', 'Y', 905)]
a, b = ev(T9, C9), ct3.evaluate(target(T9), carrier(C9))
check('without A/B, v4 equals v3 (pairs, gap fill, fields)', a['governing']['score'] == b['governing']['score'] and a['gap_filled_pairs'] == b['gap_filled_pairs'], (a['governing'], b['governing']))

# --- B1: size units -------------------------------------------------------------------------------------
o = ev([row(None, SIZE, '箱體', 'SUS304', '面', 1, None, '示例電機', 30000)] + devs, [row(None, SIZE, '箱體', 'SUS304', '面', 1, None, '示例電機', 30000)] + devs)
check('B1: a size with no A anywhere is its own unit (None, B): B 1/1', o['modes']['normalized']['per_field']['B'] == {'matched': 1, 'counted': 1} and 'A' not in o['modes']['normalized']['per_field'], o['modes']['normalized']['per_field'])

rng = random.Random(5)
ok, bad = True, None
for _ in range(300):
    n = rng.randint(1, 5); m = rng.randint(n, 6)
    w = [[rng.randint(0, 9) for _ in range(m)] for _ in range(n)]
    asg = ct._assign_max(w)
    best = max(sum(w[i][p[i]] for i in range(n)) for p in itertools.permutations(range(m), n))
    if not (sorted(asg) == list(range(n)) and len(set(asg.values())) == n and sum(w[i][j] for i, j in asg.items()) == best):
        ok, bad = False, (w, asg, best); break
check('B1: _assign_max equals the brute-force optimum, one-to-one, every row assigned (300 random matrices)', ok, bad)

# --- B2: ab_row_check -----------------------------------------------------------------------------------
def abc(o):
    return o['ab_row_check']


def cells(lst):
    return [(x['target_row'], x['cps_id'], x['field']) for x in lst]


check('ab_row_check: correct enclosure-only case lists nothing', abc(o1)['paired_conflicts'] == [] and abc(o1)['cps_unpartnered'] == [], abc(o1))
check('ab_row_check: group-wide target, CPS enclosure-only lists nothing (CPS null is never listed)', abc(o2)['paired_conflicts'] == [] and abc(o2)['cps_unpartnered'] == [], abc(o2))
check('ab_row_check: wrong name on the enclosure row is one paired conflict with its rows and values',
      abc(o3)['paired_conflicts'] == [{'target_row': 2, 'cps_id': 'R001', 'field': 'A', 'target': PANEL, 'cps': '乙 控制盤'}] and abc(o3)['cps_unpartnered'] == [], abc(o3))
lab_only = row('丙 分電箱', '400W*600H*200D', None, None, None, None)
o9 = ev([enc] + devs, [enc] + devs + [lab_only])
check('ab_row_check: A/B on an unpaired CPS row is cps_unpartnered with target_row None',
      cells(abc(o9)['cps_unpartnered']) == [(None, 'R010', 'A'), (None, 'R010', 'B')] and abc(o9)['paired_conflicts'] == [] and o9['unpaired_cps_ids'] == ['R010'], abc(o9))
C10 = [list(enc)] + [list(d) for d in devs]; C10[3][0], C10[3][1] = PANEL, SIZE
o10 = ev([enc] + devs, C10)
check('ab_row_check: right A/B repeated on a paired device row: scored 1.0 (disclosed (3)), listed as cps_unpartnered',
      o10['governing']['score'] == 1.0 and cells(abc(o10)['cps_unpartnered']) == [(5, 'R004', 'A'), (5, 'R004', 'B')] and abc(o10)['paired_conflicts'] == [], (o10['governing'], abc(o10)))
encA = row(PANEL, None, '箱體', 'SUS304', '面', 1, None, '示例電機', 30000)
o11 = ev([encA] + devs, [enc] + devs)
check('ab_row_check: CPS B on a paired row whose target row has A only is not listed (the rule is "neither")',
      abc(o11)['paired_conflicts'] == [] and abc(o11)['cps_unpartnered'] == [] and o11['modes']['normalized']['per_field']['B'] == {'matched': 0, 'counted': 1}, (abc(o11), o11['modes']['normalized']['per_field']))
check('ab_row_check is not scored: per_field has no ab_row_check entry and sums still hold',
      'ab_row_check' not in o10['modes']['normalized']['per_field']
      and sum(v['counted'] for v in o10['modes']['normalized']['per_field'].values()) == o10['modes']['normalized']['counted'], o10['modes']['normalized'])

# --- S3: disclosed unscored cases -------------------------------------------------------------------------
extra = [row(PANEL, SIZE, None, None, None, None) for _ in range(10)]
o12 = ev([enc] + devs, [enc] + devs + extra)
check('disclosed (4): ten extra CPS rows carrying only the right A/B score 1.0; ab_row_check lists all 20; v3 charged them',
      o12['governing']['score'] == 1.0 and len(abc(o12)['cps_unpartnered']) == 20 and o12['v3_per_row_AB']['normalized_score'] < 1.0,
      (o12['governing'], len(abc(o12)['cps_unpartnered']), o12['v3_per_row_AB']))
encB = row('乙-2 動力盤', '600W*1200H*300D', '箱體', 'SPHC', '面', 1, None, '示例電機', 20000)
encBn = row(None, None, '箱體', 'SPHC', '面', 1, None, '示例電機', 20000)
guess = [list(d) for d in devs]; guess[0][0] = '錯 盤'
o13a, o13b = ev([enc, encB] + devs, [enc, encBn] + devs), ev([enc, encB] + devs, [enc, encBn] + guess)
check('disclosed (5): while CPS has fewer names than the target, a wrong guess is free in v4 (A 1/2 both), charged in v3, listed',
      o13a['modes']['normalized']['per_field']['A'] == o13b['modes']['normalized']['per_field']['A'] == {'matched': 1, 'counted': 2}
      and o13a['governing']['score'] == o13b['governing']['score'] and o13b['v3_per_row_AB']['normalized_score'] < o13a['v3_per_row_AB']['normalized_score']
      and cells(abc(o13b)['cps_unpartnered']) == [(4, 'R003', 'A')], (o13a['governing'], o13b['governing'], abc(o13b)))
twin = row(PANEL, SIZE, '箱體', 'SUS304', '面', 1, None, '示例電機', 30000)
o14 = ev([enc, twin] + devs, [enc] + devs)
check('disclosed (1): two panels identical in A and B count once (A 1/1, B 1/1)',
      o14['modes']['normalized']['per_field']['A'] == {'matched': 1, 'counted': 1} and o14['modes']['normalized']['per_field']['B'] == {'matched': 1, 'counted': 1}, o14['modes']['normalized']['per_field'])

# --- S1 (genuine v2 number) and the v3/v4 invariants, on random invented cases ------------------------
spec2 = importlib.util.spec_from_file_location('ct2', HERE.parent / 'compare_target048.py')
ct2 = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(ct2)
rnd = random.Random(50)
NAMES = ['甲-1 控制盤', '乙 分電箱', '丙 PANEL', '丁盤', None]
SIZES = ['800W*1800H*400D', '600W*1200H*300D', '400W*600H*200D', None]
MATS = ['NFB', 'MC', 'TH-RY', '電驛', '指示燈', '箱體', '端子台', '配線']


def rr():
    v = row(rnd.choice(NAMES) if rnd.random() < .3 else None, rnd.choice(SIZES) if rnd.random() < .3 else None,
            rnd.choice(MATS), rnd.choice(['3P 20A', 'AC220V', None, 'SUS304']), rnd.choice(['只', '式', '面', '個', None]),
            rnd.choice([1, 2, 3, None]), rnd.choice(['M1', 'M2', None, '不含估價']), rnd.choice(['BR', None]), rnd.choice([100, 200, None, 450]))
    v[11] = rnd.choice(['J-1', 'J-1', 'J-1', 'J-2', None])
    return v


def ko_tie(R):
    for mode in ('normalized', 'strict'):
        for k in ct.JOB_LEVEL:
            vals = [ct.norm(r[k], mode) for r in R if ct.norm(r[k], mode) is not None]
            cnt = sorted((vals.count(x) for x in set(vals)), reverse=True)
            if len(cnt) > 1 and cnt[0] == cnt[1]:
                return True
    return False


TRIALS = 200
n_plain = n_tie = v2_bad = v3_bad = inv_bad = sum_bad = n_v2_differs = n_v4_differs = 0
first_bad = {}
for t in range(TRIALS):
    T = [rr() for _ in range(rnd.randint(0, 14))]
    C = [list(T[rnd.randrange(len(T))]) if T and rnd.random() < .5 else rr() for _ in range(rnd.randint(0, 14))]
    p, c = target(T), carrier(C)
    o2v, o3v, o4v = ct2.evaluate(p, c), ct3.evaluate(p, c), ct.evaluate(p, c)
    for mode in ('normalized', 'strict'):
        g = o4v['modes'][mode]
        if not (sum(v['matched'] for v in g['per_field'].values()) == g['matched'] and sum(v['counted'] for v in g['per_field'].values()) == g['counted']):
            sum_bad += 1; first_bad.setdefault('sums', t)
    if ko_tie(T) or ko_tie(C):
        n_tie += 1
        continue
    n_plain += 1
    v2 = o4v['v2_alignment']; g2 = o2v['modes']['normalized']
    if (v2['paired_rows'], v2['normalized_matched'], v2['normalized_counted'], v2['normalized_score'], v2['description_cd']) != \
            (o2v['paired_rows'], g2['matched'], g2['counted'], g2['score'], o2v['description_cd']) or o2v['governing']['score'] != g2['score']:
        v2_bad += 1; first_bad.setdefault('v2', t)
    g3 = o3v['modes']['normalized']; x3 = o4v['v3_per_row_AB']
    if (x3['normalized_matched'], x3['normalized_counted'], x3['normalized_score']) != (g3['matched'], g3['counted'], o3v['governing']['score']):
        v3_bad += 1; first_bad.setdefault('v3', t)
    same = all(o3v[k] == o4v[k] for k in ('pairs', 'gap_filled_pairs', 'description_cd', 'row_recall', 'row_precision',
                                              'unpaired_target_rows', 'unpaired_cps_ids', 'paired_rows'))
    same &= {k: v for k, v in o3v['v2_alignment'].items() if k != 'note'} == {k: v for k, v in o4v['v2_alignment'].items() if k != 'note'}
    for mode in ('normalized', 'strict'):
        same &= all(o3v['modes'][mode]['per_field'][k] == v for k, v in o4v['modes'][mode]['per_field'].items() if k not in 'AB')
        same &= o3v['modes'][mode]['cps_GH_nonnull_on_paired_rows'] == o4v['modes'][mode]['cps_GH_nonnull_on_paired_rows']
    if not same:
        inv_bad += 1; first_bad.setdefault('inv', t)
    n_v2_differs += v2['normalized_score'] != o4v['governing']['score']
    n_v4_differs += o4v['governing']['score'] != o3v['governing']['score']
check(f'S1: v2_alignment equals compare_target048 (paired rows, matched, counted, score, description) on {n_plain} random cases without a K-O tie',
      v2_bad == 0 and n_plain >= 100, (v2_bad, n_plain, first_bad))
check('S1: v2_alignment equals frozen v3\'s v2_alignment block (apart from the note) on the same cases', inv_bad == 0, (inv_bad, first_bad))
check(f'v3_per_row_AB equals frozen v3 (compare_target049) matched/counted/score on the {n_plain} cases', v3_bad == 0, (v3_bad, first_bad))
check(f'random cases are not trivial: v4 differs from v3 in {n_v4_differs}, v2_alignment from v4 in {n_v2_differs}, {n_tie} K-O tie cases skipped',
      n_v4_differs >= 20 and n_v2_differs >= 20 and n_tie >= 10, (n_v4_differs, n_v2_differs, n_tie))
check(f'per_field sums equal matched/counted in both modes in all {TRIALS} random cases (aggregator consistency)', sum_bad == 0, (sum_bad, first_bad))

tpath = target([enc] + devs_gw)
o = ct.evaluate(tpath, carrier(cps))
Tg = [r['values'] for r in ct.load_target(tpath)['rows']]
g = ct.score(Tg, cps, ct.align(Tg, cps), 'normalized', scored=ct.SCORED_V3, panel=[])
check('S1: v2_alignment is score(T, C, v2_pairs, normalized, scored=SCORED_V3, panel=[])',
      (o['v2_alignment']['normalized_matched'], o['v2_alignment']['normalized_counted'], o['v2_alignment']['normalized_score']) == (g['matched'], g['counted'], g['score']), (o['v2_alignment'], g))
check('S1: on a group-wide target v2_alignment keeps the v2 per-row A/B penalty (not the v4 number)',
      o['v2_alignment']['normalized_score'] < o['governing']['score'] == 1.0, (o['v2_alignment'], o['governing']))

# --- S2: deterministic K-O tie-break ----------------------------------------------------------------------
tieT = [row(None, None, 'NFB', '3P 20A', '只', 1, 'M1', 'BR', 100), row(None, None, 'MC', 'AC220V', '只', 2, 'M2', 'BR', 200)]
tieT[0][11], tieT[1][11] = 'J-1', 'J-2'
tieC = [list(r) for r in tieT]; tieC[1][11] = 'J-1'
tp = target(tieT)
code = ("import importlib.util,json,sys;s=importlib.util.spec_from_file_location('ct',sys.argv[1]);m=importlib.util.module_from_spec(s);"
        "s.loader.exec_module(m);print(json.dumps(m.evaluate(sys.argv[2],json.loads(sys.argv[3])),sort_keys=True,ensure_ascii=False,default=str))")
runs = [subprocess.run([sys.executable, '-I', '-B', '-c', code, str(EV), str(tp), json.dumps(carrier(tieC))], capture_output=True, text=True) for _ in range(10)]
outs = {r.stdout for r in runs}
check('S2: a K-O tie case gives byte-identical output in 10 separate -I processes', len(outs) == 1 and all(r.returncode == 0 for r in runs),
      (len(outs), sorted({json.loads(x)['governing']['score'] for x in outs if x}), [r.stderr[-200:] for r in runs if r.returncode][:1]))
ot = json.loads(next(iter(outs))) if len(outs) == 1 and runs[0].returncode == 0 else {}
check('S2: on a tie the first value in row order wins (target J-1, J-2 -> J-1 = CPS): L 1/1, score 1.0, v2 and v3 diagnostics too',
      ot.get('modes', {}).get('normalized', {}).get('per_field', {}).get('L') == {'matched': 1, 'counted': 1} and ot['governing']['score'] == 1.0
      and ot['v2_alignment']['normalized_score'] == 1.0 and ot['v3_per_row_AB']['normalized_score'] == 1.0, ot.get('modes'))
rev = [list(r) for r in tieT]; rev[0][11], rev[1][11] = 'J-2', 'J-1'
orv = ev(rev, tieC)
check('S2: target J-2, J-1 -> J-2 wins, so CPS J-1 misses L (0/1)', orv['modes']['normalized']['per_field']['L'] == {'matched': 0, 'counted': 1}, orv['modes']['normalized']['per_field'])

print(f'{len(FAIL)} failed')
sys.exit(1 if FAIL else 0)
