"""Reviewer fixtures R1-R12 for compare_target050 (invented data). Run: python3 -I -B tests/test_review050_fixtures.py"""
import importlib.util, subprocess, sys, tempfile
from pathlib import Path
import openpyxl
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ct', HERE.parent / 'compare_target050.py'); ct = importlib.util.module_from_spec(spec); spec.loader.exec_module(ct)
TMP = Path(tempfile.mkdtemp(prefix='rv050f_')); N = [0]; FAIL = []
def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' :: ' + str(detail)))
    if not cond: FAIL.append(name)
def row(a=None, b=None, c=None, d=None, e='只', f=1, i=None, j=None, q=None, l='J-1'):
    v = [None] * 17; v[0], v[1], v[2], v[3], v[4], v[5], v[8], v[9], v[16] = a, b, c, d, e, f, i, j, q
    v[11], v[12], v[13] = l, '甲公司', '乙案'; return v
def ev(T, C):
    N[0] += 1; wb = openpyxl.Workbook(); ws = wb.active; ws.title = '未填'; ws.append(ct.LABELS)
    for r in T: ws.append(r)
    p = TMP / f't{N[0]}.xlsx'; wb.save(p)
    return ct.evaluate(p, {'items': [{'id': f'R{k + 1:03d}', 'values': r} for k, r in enumerate(C)]})
P = ['甲-1 控制盤', '乙-2 動力盤', '丙-3 分電盤', '丁-4 照明盤', '戊-5 控制箱', '己-6 電表箱']
S = ['800W*1800H*400D', '600W*1200H*300D', '1000W*2000H*600D', '400W*600H*200D', '500W*700H*250D', '300W*400H*150D']
def build(spec, n_dev=3, gw=False):
    out = []
    for k, (a, b) in enumerate(spec):
        out.append(row(a, b, '箱體', 'SUS304', '面', 1, None, '示例電機', 30000 + k))
        out += [row(a if gw else None, b if gw else None, 'NFB', f'3P {10*(k*10+d)}A', '只', d + 1, f'M{k}{d}', 'BR', 100*(k*10+d)) for d in range(n_dev)]
    return out
pf = lambda o, k: o['modes']['normalized']['per_field'].get(k)
T4 = build(list(zip(P[:4], S[:4])))
o = ev(build([(P[0], S[0]), (P[1], S[0])]), build([(P[0], S[0]), (P[1], None)]))
check('R1 shared size, CPS omits B on panel 2: B 1/2', pf(o, 'B') == {'matched': 1, 'counted': 2}, pf(o, 'B'))
o = ev(T4, build([(P[0], S[1]), (P[1], S[0]), (P[2], S[2]), (P[3], S[3])]))
check('R2 sizes swapped between two panels: B 2/4', pf(o, 'B') == {'matched': 2, 'counted': 4}, pf(o, 'B'))
o = ev(T4, build([(P[k], S[(k + 1) % 4]) for k in range(4)]))
check('R3 sizes rotated: B 0/4', pf(o, 'B') == {'matched': 0, 'counted': 4}, pf(o, 'B'))
o = ev(T4, build([(P[(k + 1) % 4], S[k]) for k in range(4)]))
check('R4 names rotated: 4 A/B positions lost (as v3), conflicts listed', o['modes']['normalized']['counted'] - o['modes']['normalized']['matched'] == 4 and len(o['ab_row_check']['paired_conflicts']) == 4, (pf(o, 'A'), pf(o, 'B'), o['ab_row_check']))
o = ev(build([(P[0], S[0])]), build([('甲-1 控制箱', S[0])]))
check('R5 wrong name only: A 0/1, B 1/1 (no double penalty)', pf(o, 'A') == {'matched': 0, 'counted': 1} and pf(o, 'B') == {'matched': 1, 'counted': 1}, (pf(o, 'A'), pf(o, 'B')))
Tg = build([(P[0], S[0])], n_dev=10, gw=True)
for r in Tg[1:]: r[0] = None
o = ev(Tg, build([(P[0], S[0])], n_dev=10))
check('R6 group-wide B, A on enclosure only: (None,B) unit dropped, score 1.0', o['governing']['score'] == 1.0 and pf(o, 'B') == {'matched': 1, 'counted': 1}, (o['governing'], pf(o, 'B')))
o = ev(build([(P[0], S[0]), (P[1], S[1])]), build([(P[1], S[1]), (P[0], S[0])]))
check('R7 CPS lists panels in the other order, labels right: A 2/2, B 2/2 (alignment-free)', pf(o, 'A') == {'matched': 2, 'counted': 2} and pf(o, 'B') == {'matched': 2, 'counted': 2}, (pf(o, 'A'), pf(o, 'B')))
o = ev(T4, build([(P[(k + 1) % 4], S[(k + 1) % 4]) for k in range(4)]))
check('R8 whole labels rotated: not scored (disclosed), 8 paired conflicts listed', o['governing']['score'] == 1.0 and len(o['ab_row_check']['paired_conflicts']) == 8, o['ab_row_check'])
C = build([(None, None), (None, None)]); C[1][0], C[1][1] = P[0], S[0]
o = ev(build([(P[0], S[0]), (P[1], S[1])]), C)
check('R9 A/B on a device row: listed as cps_unpartnered', len(o['ab_row_check']['cps_unpartnered']) == 2 and not o['ab_row_check']['paired_conflicts'], o['ab_row_check'])
o = ev(build([(P[0], S[0])], n_dev=30, gw=True), build([(P[0], S[0])], n_dev=30))
check('R10 group-wide target, CPS enclosure-only right: 1.0 and nothing listed', o['governing']['score'] == 1.0 and not o['ab_row_check']['paired_conflicts'] and not o['ab_row_check']['cps_unpartnered'], o['ab_row_check'])
T = [row(None, None, 'NFB', '3P 20A', '只', 1, 'M1', 'BR', 100, l='J-1'), row(None, None, 'MC', 'AC220V', '只', 2, 'M2', 'BR', 200, l='J-2')]
C = [row(None, None, 'NFB', '3P 20A', '只', 1, 'M1', 'BR', 100, l='J-1'), row(None, None, 'MC', 'AC220V', '只', 2, 'M2', 'BR', 200, l='J-1')]
N[0] += 1; wb = openpyxl.Workbook(); ws = wb.active; ws.title = '未填'; ws.append(ct.LABELS)
for r in T: ws.append(r)
tp = TMP / 'tie.xlsx'; wb.save(tp)
code = ("import importlib.util,json,sys;s=importlib.util.spec_from_file_location('ct',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        "print(m.evaluate(sys.argv[2],json.loads(sys.argv[3]))['governing']['score'])")
import json
outs = {subprocess.run([sys.executable, '-I', '-B', '-c', code, str(HERE.parent / 'compare_target050.py'), str(tp), json.dumps({'items': [{'id': 'R1', 'values': C[0]}, {'id': 'R2', 'values': C[1]}]})], capture_output=True, text=True).stdout.strip() for _ in range(8)}
check('R11 K-O modal tie is deterministic across processes (first in row order)', len(outs) == 1, outs)
T = build(list(zip(P, S)), n_dev=2); C = build([(P[(k + 1) % 6], S[(k + 1) % 6]) for k in range(6)], n_dev=2)
o = ev(T, C); g = o['modes']['normalized']
check('R12 per_field sums equal matched/counted with B units (aggregator consistency)', sum(v['matched'] for v in g['per_field'].values()) == g['matched'] and sum(v['counted'] for v in g['per_field'].values()) == g['counted'], g)
print(f'{len(FAIL)} failed'); sys.exit(1 if FAIL else 0)
