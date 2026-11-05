"""Round-trip test: aggregate_qualification (O31 gate) on genuine outputs of the frozen evaluator v3
(compare_target049) for invented targets and carriers. Adapted from the independent review's
patched_real_eval.py (delta review optional item O5). No real case data.
Run: python3 -I -B research/evaluation/tests/test_aggregate_real_eval.py"""
import hashlib, importlib.util, json, shutil, subprocess, sys, tempfile
from pathlib import Path
import openpyxl

HERE = Path(__file__).resolve().parent
EV = HERE.parent / 'compare_target049.py'
spec = importlib.util.spec_from_file_location('ag', HERE.parent / 'aggregate_qualification.py')
ag = importlib.util.module_from_spec(spec); spec.loader.exec_module(ag)
FX = Path(tempfile.mkdtemp(prefix='agq_real_'))
LABELS = ['盤體名稱', '盤體規格', '材料名稱', '規格', '單位', '數量', '單價', '複價', '型號', '廠牌', '訂購廠商',
          '工程編號', '訂購客戶', '使用客戶', '需要日期', '需要數量', '合約價']
POOL = [f'X{k:02d}' for k in range(30)]
FAIL = []


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
    return {'path': str(o), 'sha256': sha(o), 'carrier_sha256': sha(c)}


def row(k, case, q=None):
    return [None, None, f'品項{case}{k}', f'規格{k}', '只', k + 1, None, None, f'M{k}', 'BR', None, 'J1', 'CU', 'CU', None, k + 1, q or 100 + k]


check('evaluator on disk is the frozen v3', sha(EV) == ag.EVALUATOR_SHA256, sha(EV))
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

print(f'{len(FAIL)} failed')
sys.exit(1 if FAIL else 0)
