"""Invented-fixture tests for compare_target049 (v3 gap fill). No real case data.
Run: python3 -I -B research/evaluation/tests/test_compare_target049.py"""
import importlib.util, sys, tempfile
from pathlib import Path
import openpyxl

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ct', HERE.parent / 'compare_target049.py')
ct = importlib.util.module_from_spec(spec); spec.loader.exec_module(ct)
TMP = Path(tempfile.mkdtemp(prefix='ct049_'))
N = [0]


def row(c=None, d=None, e=None, f=None, i=None, j=None, q=None, l='J-1', m='甲公司', n='乙案'):
    v = [None] * 17
    v[2], v[3], v[4], v[5], v[8], v[9], v[16] = c, d, e, f, i, j, q
    v[11], v[12], v[13] = l, m, n
    return v


def target(rows):
    N[0] += 1
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = '未填'
    ws.append(ct.LABELS)
    for r in rows:
        ws.append(r)
    p = TMP / f't{N[0]}.xlsx'; wb.save(p)
    return p


def carrier(rows):
    return {'items': [{'id': f'R{k + 1:03d}', 'values': r} for k, r in enumerate(rows)]}


FAIL = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' :: ' + str(detail)))
    if not cond:
        FAIL.append(name)


A = row('NFB', '3P 20A', '只', 2, 'X1', 'Y', 100)
B = row('MC', 'AC220V', '只', 4, 'X2', 'Y', 50)
Cc = row('PL', '綠色', '只', 6, 'X3', 'Y', 10)

# 1 identical rows: all v2 pairs, nothing filled
o = ct.evaluate(target([A, B, Cc]), carrier([A, B, Cc]))
check('identical: score 1', o['governing']['score'] == 1.0, o['governing'])
check('identical: no gap fill', o['gap_filled_pairs'] == [], o['gap_filled_pairs'])

# 2 same position, wording entirely different, E/F equal -> filled and scored
Bt = row('甲甲', None, '只', 4, 'X2', 'Y', 50)
Bc = row(None, '完全不同的長描述文字內容', '只', 4, 'X2', 'Y', 50)
o = ct.evaluate(target([A, Bt, Cc]), carrier([A, Bc, Cc]))
check('reworded: v2 leaves it unpaired', o['v2_alignment']['paired_rows'] == 2, o['v2_alignment'])
check('reworded: gap filled one pair', len(o['gap_filled_pairs']) == 1 and o['gap_filled_pairs'][0]['cps_id'] == 'R002', o['gap_filled_pairs'])
check('reworded: governing 1.0 after fill', o['governing']['score'] == 1.0, o['governing'])
check('reworded: description position still a miss', o['description_cd']['matched'] == 2 and o['description_cd']['counted'] == 3, o['description_cd'])
check('reworded: v2 score reported lower', o['v2_alignment']['normalized_score'] < 1.0, o['v2_alignment'])

# 3 filled pair with a different Q: Q counts as a miss, no automatic credit
Bc2 = row(None, '完全不同的長描述文字內容', '只', 4, 'X2', 'Y', 55)
o = ct.evaluate(target([A, Bt, Cc]), carrier([A, Bc2, Cc]))
check('filled pair is scored: Q miss', o['modes']['normalized']['per_field']['Q'] == {'matched': 2, 'counted': 3}, o['modes']['normalized']['per_field']['Q'])

# 4 unequal gap counts -> not filled
X = row(None, '另一個完全不同的描述', '式', 1, None, None, 9)
o = ct.evaluate(target([A, Bt, Cc]), carrier([A, Bc, X, Cc]))
check('unequal gap: not filled', o['gap_filled_pairs'] == [], o['gap_filled_pairs'])

# 5 E differs -> not filled
Bc3 = row(None, '完全不同的長描述文字內容', '組', 4, 'X2', 'Y', 50)
o = ct.evaluate(target([A, Bt, Cc]), carrier([A, Bc3, Cc]))
check('E differs: not filled', o['gap_filled_pairs'] == [], o['gap_filled_pairs'])

# 6 F differs -> not filled
Bc4 = row(None, '完全不同的長描述文字內容', '只', 5, 'X2', 'Y', 50)
o = ct.evaluate(target([A, Bt, Cc]), carrier([A, Bc4, Cc]))
check('F differs: not filled', o['gap_filled_pairs'] == [], o['gap_filled_pairs'])

# 7 E and F both null on both sides -> not filled
Bt5 = row('甲甲', None, None, None, None, None, None)
Bc5 = row(None, '完全不同的長描述文字內容', None, None, None, None, None)
o = ct.evaluate(target([A, Bt5, Cc]), carrier([A, Bc5, Cc]))
check('E/F null: not filled', o['gap_filled_pairs'] == [], o['gap_filled_pairs'])

# 8 a gap of two: one pair fails -> whole gap left unpaired
Bt6 = row('乙乙', None, '只', 6, None, None, 1)
Bc6 = row(None, '另一段完全不同的文字', '只', 7, None, None, 1)
o = ct.evaluate(target([A, Bt, Bt6, Cc]), carrier([A, Bc, Bc6, Cc]))
check('gap of two with one failure: none filled', o['gap_filled_pairs'] == [], o['gap_filled_pairs'])

# 9 a gap of two, both pass -> both filled in order
Bc7 = row(None, '另一段完全不同的文字', '只', 6, None, None, 1)
o = ct.evaluate(target([A, Bt, Bt6, Cc]), carrier([A, Bc, Bc7, Cc]))
check('gap of two: both filled in order', [p['cps_id'] for p in o['gap_filled_pairs']] == ['R002', 'R003'], o['gap_filled_pairs'])

# 10 leading and trailing gaps
o = ct.evaluate(target([Bt, A, Cc, Bt]), carrier([Bc, A, Cc, Bc]))
check('leading and trailing gaps filled', [p['cps_id'] for p in o['gap_filled_pairs']] == ['R001', 'R004'], o['gap_filled_pairs'])

# 11 no anchors at all: whole sequence is one gap
o = ct.evaluate(target([Bt]), carrier([Bc]))
check('no anchors: single gap filled', len(o['gap_filled_pairs']) == 1, o['gap_filled_pairs'])

# 12 schema
check('schema v3', o['schema'] == 'cps.target-comparison049.v1', o['schema'])

print(f'{len(FAIL)} failed')
sys.exit(1 if FAIL else 0)
