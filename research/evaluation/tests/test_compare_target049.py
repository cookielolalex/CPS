"""Invented-fixture tests for compare_target049 (v3 gap fill, review fix B1: identity key + in-gap matching).
Sections 1-13: author tests (4 and 8 changed on purpose by B1). Section R: the independent reviewer's
adversarial fixtures (C0-C11), with the results the reviewer computed for the fixed rule. No real case data.
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

# 4 unequal gap counts: in-gap matching pairs the identity-matching row, the extra row stays unpaired (B1)
X = row(None, '另一個完全不同的描述', '式', 1, None, None, 9)
o = ct.evaluate(target([A, Bt, Cc]), carrier([A, Bc, X, Cc]))
check('unequal gap: matching row filled, extra stays unpaired', [p['cps_id'] for p in o['gap_filled_pairs']] == ['R002'] and o['unpaired_cps_ids'] == ['R003'], (o['gap_filled_pairs'], o['unpaired_cps_ids']))

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

# 8 a gap of two where one pair fails the key: only the passing pair is filled (B1)
Bt6 = row('乙乙', None, '只', 6, None, None, 1)
Bc6 = row(None, '另一段完全不同的文字', '只', 7, None, None, 1)
o = ct.evaluate(target([A, Bt, Bt6, Cc]), carrier([A, Bc, Bc6, Cc]))
check('gap of two with one failure: only the passing pair filled', [p['cps_id'] for p in o['gap_filled_pairs']] == ['R002'], o['gap_filled_pairs'])

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

# 12 schema, flags and diagnostics
check('schema v3', o['schema'] == 'cps.target-comparison049.v1', o['schema'])
check('pairs flag gap_filled', [p['gap_filled'] for p in o['pairs']] == [True], o['pairs'])
check('v2 diagnostic carries its description rate', 'description_cd' in o['v2_alignment'], o['v2_alignment'].keys())

# 13 E/F equal but no identity outside C/D (Q differs and I null) -> not filled
Bt8 = row('丙丙', None, '式', 1, None, None, 3000)
Bc8 = row(None, '不同費用文字', '式', 1, None, None, 8000)
o = ct.evaluate(target([A, Bt8, Cc]), carrier([A, Bc8, Cc]))
check('no identity key (Q differs, I null): not filled', o['gap_filled_pairs'] == [], o['gap_filled_pairs'])
# 13b reworded not-estimated lines (I = 不含估價, Q null) -> not filled
NEt = row(None, '甲工程', '式', 1, '不含估價', '不含估價', None)
NEc = row(None, '乙工程', '式', 1, '不含估價', '不含估價', None)
o = ct.evaluate(target([A, NEt, Cc]), carrier([A, NEc, Cc]))
check('status-only identity: not filled', o['gap_filled_pairs'] == [], o['gap_filled_pairs'])
# 13c identity by I alone (Q null on both) -> filled
It = row('丁丁', None, '只', 3, 'MOD-1', 'Y', None)
Ic = row(None, '完全不一樣', '只', 3, 'MOD-1', 'Y', None)
o = ct.evaluate(target([A, It, Cc]), carrier([A, Ic, Cc]))
check('identity by I alone: filled', len(o['gap_filled_pairs']) == 1, o['gap_filled_pairs'])

# ---- Section R: reviewer adversarial fixtures (expected results computed by the reviewer for B1) ----
STATUS = '不含估價'


def r(c=None, d=None, e=None, f=None, i=None, j=None, q=None, a=None, b=None):
    v = row(c, d, e, f, i, j, q)
    v[0], v[1] = a, b
    return v


def reword(v, newc, newd):
    w = list(v); w[2], w[3] = newc, newd
    return w


ENC = r('箱體', 'SPCC 烤漆', '面', 1, None, '甲電機', 35000, a='控制盤', b='800W*1800H*400D')
P1 = r('NFB', '3P 20A', '只', 2, 'BW-50', '士林', 450)
P2 = r('MC', 'AC220V 20A', '只', 3, 'S-P21', '士林', 900)
P3 = r('PL', '綠色 AC220V', '只', 6, 'AD16', '天得', 60)
P4 = r('CT', '100/5A', '只', 3, 'CT-100', '台製', 300)
P5 = r('TR', 'ON-DELAY 60S', '只', 2, 'H3CR', '歐姆龍', 750)
FEE_T = r(None, '運費', '式', 1, None, None, 3000)
FEE_C = r(None, '吊裝工資', '式', 1, None, None, 8000)
NE_T = r(None, '電纜線架', '式', 1, STATUS, STATUS, None)
NE_C = r(None, '接地工程', '式', 1, STATUS, STATUS, None)
X_T = r('NFB', '3P 100A', '只', 2, 'BW-100', '士林', 1800)
Y_C = r(None, '繼電器 小型 DC24V', '只', 2, 'MY2N', '歐姆龍', 120)
FILL = [r('PL', f'{k}號 紅色', '只', 1 + k % 3, f'AD{k}', '天得', 60 + k) for k in range(12)]


def gov(T, C):
    o = ct.evaluate(target(T), carrier(C))
    return o['governing']['score'], o


def near(x, y):
    return abs(x - y) < 0.0005


P2r = reword(P2, None, '電磁接觸器 交流二二〇伏 二十安培')
g, o = gov(FILL[:4] + [P1, P2, P3] + FILL[4:8], FILL[:4] + [P1, P2r, P3] + FILL[4:8])
check('R C0 same line reworded: 1.000, 1 fill', near(g, 1.0) and len(o['gap_filled_pairs']) == 1, (g, o['gap_filled_pairs']))
g, o = gov(FILL[:5] + [P1, FEE_T, P3] + FILL[5:9], FILL[:5] + [P1, FEE_C, P3] + FILL[5:9])
check('R C1 different fee line same 式/1: 0.906, no fill', near(g, 0.9062) and not o['gap_filled_pairs'], g)
g, o = gov(FILL[:5] + [P1, NE_T, P3] + FILL[5:9], FILL[:5] + [P1, NE_C, P3] + FILL[5:9])
check('R C2 different 不含估價 line: 0.879, no fill', near(g, 0.8788) and not o['gap_filled_pairs'], g)
g, o = gov(FILL[:5] + [P1, X_T, P3] + FILL[5:9], FILL[:5] + [P1, Y_C, P3] + FILL[5:9])
check('R C3 different device same 只/2: 0.853, no fill', near(g, 0.8529) and not o['gap_filled_pairs'], g)
FT = [r(None, w, '式', 1, None, None, 1000 * (k + 1)) for k, w in enumerate(['運費', '測試調整費', '安裝工資', '管理費', '保險費', '雜項材料'])]
G3 = r(None, '吊車', '式', 1, None, None, 7777)
G4 = r(None, '設計圖說', '式', 1, None, None, 8888)
g, o = gov(FILL[:6] + [P1, P2] + FT + [P3], FILL[:6] + [P1, P2] + FT[:2] + [G3, G4] + FT[4:] + [P3])
check('R C5 two of six fee lines replaced: 0.833, no fill', near(g, 0.8333) and not o['gap_filled_pairs'], g)
HT = [r('RY', f'{k}號 DC24V', '只', 1, f'MY{k}', '歐姆龍', 100 + k) for k in range(10)]
KC = [r(None, '■■' + '□' * k, '只', 1, f'G{k}', '歐姆龍', 500 + k) for k in range(10)]
g, o = gov(FILL[:4] + [P1] + HT + [P3] + FILL[4:8], FILL[:4] + [P1] + KC + [P3] + FILL[4:8])
check('R C6a long gap of different lines: no fill', not o['gap_filled_pairs'] and near(g, 0.3462), (g, len(o['gap_filled_pairs'])))
HR = [reword(h, None, '中間繼電器第' + '一二三四五六七八九十'[k] + '號') for k, h in enumerate(HT)]
g, o = gov(FILL[:4] + [P1] + HT + [P3] + FILL[4:8], FILL[:4] + [P1] + HR + [P3] + FILL[4:8])
check('R C6b long gap same lines reworded: 1.000, 10 fills', near(g, 1.0) and len(o['gap_filled_pairs']) == 10, g)
ENC2 = reword(r('箱體', '不銹鋼 霧面', '面', 1, None, '甲電機', 12000, a='端子箱', b='400W*600H*200D'), None, '端子箱體')
ENC_T = reword(ENC, None, 'SPCC烤漆')
g, o = gov([ENC_T] + FILL[:8] + [P1, P2, FEE_T], [ENC2] + FILL[:8] + [P1, P2, FEE_C])
check('R C7 different rows at both ends: 0.746, no fill', near(g, 0.7465) and not o['gap_filled_pairs'], g)
BASE = [ENC, P1, P2, P3, P4, P5, FEE_T] + FILL[:5]
GARB = [reword(x, None, '■' * (k + 2)) for k, x in enumerate(BASE)]
g, o = gov(BASE, GARB + [reword(FEE_C, None, '■' * 32)])
check('R C8c garbage C/D plus one extra row: 0.954', near(g, 0.9538), g)
g, o = gov(BASE, GARB)
check('R C8a garbage C/D, all else right: governing 1.000 but description 0.0 (O24: reported only)', near(g, 1.0) and o['description_cd']['rate'] == 0.0, (g, o['description_cd']))
JUNK = []
for k, x in enumerate(BASE):
    w = reword(x, None, '■' * (k + 2)); w[8], w[9], w[16] = 'ZZ', 'ZZ', 1; JUNK.append(w)
g, o = gov(BASE, JUNK)
check('R C8b garbage C/D, E/F copied, junk I/J/Q: no fill', not o['gap_filled_pairs'] and g < 0.05, g)
D15 = [r('MCCB', f'{k}P {10 * k}A', '只', 1, f'NF{k}', '士林', 100 * k) for k in range(15)]
D4 = [r('PL', f'{k}號 黃色', '只', 2, f'AD{k}', '天得', 50) for k in range(4)]
D4r = [reword(x, None, '指示燈' + '甲乙丙丁'[k]) for k, x in enumerate(D4)]
g, o = gov(D15[:8] + D4[:2] + D15[8:] + D4[2:], D15[:8] + D4r[:2] + D15[8:] + D4r[2:])
check('R C9 description rate disclosed: v2 0.652, v3 0.789', near(o['v2_alignment']['description_cd']['rate'], 0.6522) and near(o['description_cd']['rate'], 0.7895), (o['v2_alignment']['description_cd'], o['description_cd']))
Yt = r('PB', '紅色', '只', 1, 'AR22F', '天得', 70)
Yr = reword(Yt, None, '按鈕赤')
X1 = r('MCCB', '3P 50A', '只', 2, 'NF-50', '士林', 1200)
ga, _ = gov(FILL[:6] + [Yt, X1], FILL[:6] + [Yr, X1, list(X1)])
gb, _ = gov(FILL[:6] + [X1, Yt], FILL[:6] + [list(X1), X1, Yr])
check('R C10a/b duplicate extra row before or after: both 0.896', near(ga, 0.8955) and near(gb, 0.8955), (ga, gb))
Bq = r('TB', '30A 12P', '只', 1, 'TB-3012', '台製', 40)
Xq = r('FS', '2A 玻璃管', '只', 1, 'F-2', '台製', 15)
Yq = r(None, '標示牌 壓克力', '只', 1, None, None, 25)
g, o = gov(FILL[:6] + [P1, Xq, Bq, P3], FILL[:6] + [P1, reword(Bq, None, '端子台三十安'), Yq, P3])
check('R C11 crossing drop/add with reworded line: 0.857', near(g, 0.8571), g)

print(f'{len(FAIL)} failed')
sys.exit(1 if FAIL else 0)
