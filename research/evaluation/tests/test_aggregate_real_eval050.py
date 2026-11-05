"""Round-trip test: aggregate_qualification050 (aggregator v2: the O31 gate re-pinned to evaluator v4 under O35)
on genuine outputs of evaluator v4 (compare_target050, run through its CLI) for invented targets and carriers.
Adapted from test_aggregate_real_eval.py (its six checks kept), plus v4 checks R1b and R5-R8. No real case data.
Run: python3 -I -B research/evaluation/tests/test_aggregate_real_eval050.py"""
import hashlib, importlib.util, json, shutil, subprocess, sys, tempfile
from pathlib import Path
import openpyxl

HERE = Path(__file__).resolve().parent
EV = HERE.parent / 'compare_target050.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


ag = load('ag', HERE.parent / 'aggregate_qualification050.py')
ag1 = load('ag1', HERE.parent / 'aggregate_qualification.py')     # frozen v1 (pins v3)
ct2 = load('ct2', HERE.parent / 'compare_target048.py')           # frozen v2
ct3 = load('ct3', HERE.parent / 'compare_target049.py')           # frozen v3
FX = Path(tempfile.mkdtemp(prefix='agq050_real_'))
LABELS = ['盤體名稱', '盤體規格', '材料名稱', '規格', '單位', '數量', '單價', '複價', '型號', '廠牌', '訂購廠商',
          '工程編號', '訂購客戶', '使用客戶', '需要日期', '需要數量', '合約價']
POOL = [f'X{k:02d}' for k in range(30)]
FAIL = []
RUNS = {}   # comparison path -> (target path, carrier path)


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' :: ' + str(detail)))
    if not cond:
        FAIL.append(name)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def target(case, rows):
    p = FX / f'T_{case}.xlsx'
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = '未填'; ws.append(LABELS)
    for r in rows:
        ws.append(r)
    wb.save(p); return p


def evaluate(case, rd, t, items, tag=''):
    c = FX / f'C_{rd}_{case}{tag}.json'; o = FX / f'CMP_{rd}_{case}{tag}.json'
    c.write_text(json.dumps({'reader': rd, 'items': [{'id': f'i{k}', 'values': v} for k, v in enumerate(items)]}), encoding='utf-8')
    subprocess.run([sys.executable, '-I', '-B', str(EV), '--target', str(t), '--target-sha', sha(t), '--carrier', str(c),
                    '--carrier-sha', sha(c), '--out', str(o)], check=True, capture_output=True)
    RUNS[str(o)] = (t, c)
    return {'path': str(o), 'sha256': sha(o), 'carrier_sha256': sha(c)}


def row(k, case, q=None):
    return [None, None, f'品項{case}{k}', f'規格{k}', '只', k + 1, None, None, f'M{k}', 'BR', None, 'J1', 'CU', 'CU', None, k + 1, q or 100 + k]


def pooled_frozen(mod, reader_entries):
    """Pool a frozen evaluator's governing normalized counts, run in-process on the same target and carrier files."""
    m = c = 0
    for e in reader_entries.values():
        t, car = RUNS[e['path']]
        g = mod.evaluate(t, json.loads(Path(car).read_text(encoding='utf-8')))['modes']['normalized']
        m += g['matched']; c += g['counted']
    return m / c


check('evaluator on disk is the pinned v4', sha(EV) == ag.EVALUATOR_SHA256, sha(EV))
T = {c: target(c, [row(k, c) for k in range(40)]) for c in POOL}
m = {'pool': list(POOL), 'targets': {c: sha(T[c]) for c in POOL}, 'readers': {}}
for rd in 'AB':
    m['readers'][rd] = {}
    for c in POOL:
        items = [row(k, c) for k in range(40)]
        if rd == 'B':
            items[3] = row(3, c, q=999)       # one miss per case for B
            items.append(row(77, 'extra'))    # one extra CPS row for B
        m['readers'][rd][c] = evaluate(c, rd, T[c], items)
r = ag.gate(m)
check('R1 genuine outputs, both readers pass', r['historical_match_element_passes'] and not r['readers']['A']['problems']
      and not r['readers']['B']['problems'] and r['readers']['A']['pooled']['score'] == 1.0
      and 0.95 <= r['readers']['B']['pooled']['score'] < 1.0, (r['readers']['A']['pooled'], r['readers']['B']['pooled']))
check('R1b without A/B, v3_per_row_AB pooled equals the v4 pool for each reader',
      all(r['readers'][rd]['reported_not_gating']['v3_per_row_AB_pooled'] == r['readers'][rd]['pooled']['score'] for rd in 'AB'),
      {rd: r['readers'][rd]['reported_not_gating'] for rd in 'AB'})

m2 = json.loads(json.dumps(m))
na = target('X28na', [row(k, 'X28') for k in range(40)])
m2['targets']['X28'] = sha(na)
m2['readers']['A']['X28'] = evaluate('X28', 'A', na, [], tag='_na_A')
m2['readers']['B']['X28'] = evaluate('X28', 'B', na, [], tag='_na_B')
r = ag.gate(m2)
check('R2 nonattempt (empty carrier) fails the floor for both readers', not r['historical_match_element_passes']
      and 'X28' in r['readers']['A']['cases_below_floor'] and 'X28' in r['readers']['B']['cases_below_floor'],
      (r['readers']['A']['cases_below_floor'], r['readers']['B']['problems']))

m3 = json.loads(json.dumps(m2))
m3['readers']['A']['X28'] = dict(m['readers']['A']['X00']); m3['readers']['B']['X28'] = dict(m['readers']['B']['X00'])
r = ag.gate(m3)
check('R3 a case mapped to another case\'s comparison is refused', not r['historical_match_element_passes']
      and 'COMPARISON_PATH_REUSED' in [p['code'] for p in r['readers']['A']['problems']], r['readers']['A']['problems'][:3])
for rd in 'AB':
    src = Path(m['readers'][rd]['X00']['path']); dst = FX / f'copy_{rd}_X00_as_X28.json'; shutil.copy(src, dst)
    m3['readers'][rd]['X28'] = {'path': str(dst), 'sha256': sha(dst), 'carrier_sha256': m['readers'][rd]['X00']['carrier_sha256']}
r = ag.gate(m3)
check('R3b a copy of another case\'s comparison is refused (TARGET_BINDING)', not r['historical_match_element_passes']
      and 'TARGET_BINDING' in [p['code'] for p in r['readers']['A']['problems']], r['readers']['A']['problems'][:3])

z = target('X29z', [])
m4 = json.loads(json.dumps(m)); m4['targets']['X29'] = sha(z)
m4['readers']['A']['X29'] = evaluate('X29', 'A', z, [], tag='_z')
m4['readers']['B']['X29'] = evaluate('X29', 'B', z, [[None] * 17], tag='_z')
r = ag.gate(m4)
check('R4 counted 0 is ZERO_COUNTED, min_case None, not a pass', not r['historical_match_element_passes']
      and 'ZERO_COUNTED' in [p['code'] for p in r['readers']['A']['problems']] and r['readers']['A']['min_case_score'] is None,
      (r['readers']['A']['problems'][:3], r['readers']['A']['min_case_score']))

# --- v4 additions -----------------------------------------------------------------------------------------
PANEL, SIZE = '甲-1 控制盤', '800W*1800H*400D'


def prow(k, case, gw, q=None):
    v = row(k, case, q)
    if gw or k == 0:
        v[0], v[1] = PANEL, SIZE
    return v


T5 = {c: target(c + 'gw', [prow(k, c, True) for k in range(40)]) for c in POOL}     # group-wide targets (March-May 115 habit)
m5 = {'pool': list(POOL), 'targets': {c: sha(T5[c]) for c in POOL}, 'readers': {}}
for rd in 'AB':
    m5['readers'][rd] = {}
    for c in POOL:
        items = [prow(k, c, False) for k in range(40)]                              # CPS: A/B on the enclosure row only (O30)
        if rd == 'B':
            items[3] = prow(3, c, False, q=999)
        m5['readers'][rd][c] = evaluate(c, rd, T5[c], items, tag='_gw')
r5 = ag.gate(m5)
ra, rb = r5['readers']['A'], r5['readers']['B']
check('R5 group-wide targets, CPS enclosure-only: v4 pools pass for both readers (O35)', r5['historical_match_element_passes']
      and ra['pooled']['score'] == 1.0 and 0.95 <= rb['pooled']['score'] < 1.0 and not ra['problems'] and not rb['problems'],
      (ra['pooled'], rb['pooled'], ra['problems'][:2]))
v3a, v3b = pooled_frozen(ct3, m5['readers']['A']), pooled_frozen(ct3, m5['readers']['B'])
check('R6 v3_per_row_AB pooled is reported, below 0.95, and equals frozen v3 (compare_target049) pooled on the same files',
      ra['reported_not_gating']['v3_per_row_AB_pooled'] == v3a and rb['reported_not_gating']['v3_per_row_AB_pooled'] == v3b and v3a < 0.95,
      (ra['reported_not_gating'], v3a, v3b))
v2a, v2b = pooled_frozen(ct2, m5['readers']['A']), pooled_frozen(ct2, m5['readers']['B'])
check('R7 v2_alignment pooled equals frozen v2 (compare_target048) pooled on the same files',
      ra['reported_not_gating']['v2_alignment_pooled'] == v2a and rb['reported_not_gating']['v2_alignment_pooled'] == v2b,
      (ra['reported_not_gating'], v2a, v2b))
r = ag1.gate(m5)
check('R8 the frozen aggregator v1 refuses genuine v4 outputs (EVALUATOR_SCHEMA on every case), fail closed',
      not r['historical_match_element_passes'] and [p['code'] for p in r['readers']['A']['problems']] == ['EVALUATOR_SCHEMA'] * 30
      and [p['code'] for p in r['readers']['B']['problems']] == ['EVALUATOR_SCHEMA'] * 30, r['readers']['A']['problems'][:2])

print(f'{len(FAIL)} failed')
sys.exit(1 if FAIL else 0)
