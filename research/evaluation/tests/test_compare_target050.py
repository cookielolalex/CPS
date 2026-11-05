"""Invented-fixture tests for compare_target050 (v4, O35: A and B scored once per distinct value per case).
Run: python3 -I -B research/evaluation/tests/test_compare_target050.py"""
import importlib.util, sys, tempfile
from pathlib import Path
import openpyxl

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ct', HERE.parent / 'compare_target050.py')
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
check('two panels sharing one size: B counted once', o7['modes']['normalized']['per_field']['B'] == {'matched': 1, 'counted': 1}, o7['modes']['normalized']['per_field']['B'])

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

print(f'{len(FAIL)} failed')
sys.exit(1 if FAIL else 0)
