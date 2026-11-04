"""Historical-match evaluator for CPS (owner decision O12, 2026-11-04): agreement of a frozen CPS
carrier's 未填 rows with the creator's historical 未填 workbook. Evaluation role only.

Metric (declared before any qualification run; changes need a new version and review):
  Rows. Target rows are the non-empty rows below the 17-column header of the target sheet named 未填
  (or the first sheet whose header row carries at least 15 of the 17 labels). Columns are mapped by
  header label, not position (older templates swap 型號/廠牌); the map is reported (v1.1). CPS rows are the carrier `items`
  (demand rows; analysis components live on the composition-reference sheet and are not 未填 rows).
  Rows are aligned by an order-preserving dynamic programme maximizing total similarity; a pair is
  admitted only when its similarity is >= 0.5. Similarity = 0.7*sim(C+' '+D) + 0.15*eq(E) + 0.15*eq(F)
  on normalized values (C and D joined so the creator's C/D split does not block alignment), where sim
  is difflib's ratio and eq is 1/0.
  Fields. The 10 item positions A–F, I, J, P and Q are scored per row; G and H (stage blanks) are
  reported but not scored. K, L, M, N and O are job-level identifiers (the creator writes them on
  every row in later files and on the first row only in older files): each is scored once per case
  as one position, the target's modal non-null value against the CPS modal non-null value (v1.2). For an aligned pair, a position counts when either side is non-null; it matches when the
  normalized values are equal. A target row with no partner contributes each non-null position as a
  miss; a CPS row with no partner contributes each non-null position as an error.
  Score = matched / counted (per case). The governing mode is `normalized`; `strict` is reported.
  normalized: strings NFKC-folded, internal whitespace runs collapsed to one space, outer whitespace
  trimmed; numbers and numeric text compared as decimals; dates as ISO yyyy-mm-dd; empty -> null.
  strict: strings trimmed only; numbers compared as decimals; text never equals a number.
  Deployment reading (O12): a case "matches" at score >= 0.95 in the governing mode. Row recall,
  row precision and per-field rates are diagnostics.
Usage: python3 -I -B compare_target048.py --target T.xlsx --target-sha HEX --carrier C.json
       --carrier-sha HEX --out OUT.json
"""
import argparse, datetime, difflib, hashlib, json, re, unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

LABELS = ['盤體名稱', '盤體規格', '材料名稱', '規格', '單位', '數量', '單價', '複價', '型號', '廠牌', '訂購廠商',
          '工程編號', '訂購客戶', '使用客戶', '需要日期', '需要數量', '合約價']
COLS = 'ABCDEFGHIJKLMNOPQ'
JOB_LEVEL = [i for i, c in enumerate(COLS) if c in 'KLMNO']
SCORED = [i for i, c in enumerate(COLS) if c not in 'GHKLMNO']
VERSION = 'cps.target-comparison048.v1.2'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _dec(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            return Decimal(repr(v)).normalize()
        except InvalidOperation:
            return None
    if isinstance(v, str):
        t = unicodedata.normalize('NFKC', v).strip().replace(',', '')
        if re.fullmatch(r'[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?', t):
            try:
                return Decimal(t).normalize()
            except InvalidOperation:
                return None
    return None


def norm(v, mode):
    if v is None:
        return None
    if isinstance(v, (datetime.datetime, datetime.date)):
        return ('date', v.strftime('%Y-%m-%d'))
    if isinstance(v, bool):
        return ('bool', v)
    if isinstance(v, (int, float)):
        d = _dec(v)
        return ('num', d) if d is not None else ('str', str(v))
    s = str(v)
    if mode == 'normalized':
        s = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', s)).strip()
        if s == '':
            return None
        if re.fullmatch(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', s):
            y, m, d = re.split(r'[-/]', s)
            return ('date', f'{int(y):04d}-{int(m):02d}-{int(d):02d}')
        d = _dec(s)
        return ('num', d) if d is not None else ('str', s)
    s = s.strip()
    return ('str', s) if s != '' else None


def text_of(n):
    return '' if n is None else str(n[1])


def load_target(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = [ws for ws in wb.worksheets if ws.title.strip() == '未填'] + [ws for ws in wb.worksheets if ws.title.strip() != '未填']
    for ws in sheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        for hi, r in enumerate(rows[:30]):
            cells = [re.sub(r'\s+', '', str(x)) if x is not None else '' for x in r]
            pos = {}
            for ci, lab in enumerate(cells):
                if lab in LABELS and lab not in pos:
                    pos[lab] = ci
            if len(pos) >= 15:
                idx = [pos.get(lab) for lab in LABELS]
                body = []
                for j, r2 in enumerate(rows[hi + 1:], start=hi + 2):
                    vals = [r2[i] if i is not None and i < len(r2) else None for i in idx]
                    if any(norm(v, 'normalized') is not None for v in vals):
                        body.append({'row': j, 'values': vals})
                return {'sheet': ws.title, 'header_row': hi + 1, 'rows': body,
                        'column_map': {COLS[k]: (None if i is None else i + 1) for k, i in enumerate(idx)},
                        'columns_in_canonical_order': idx == list(range(17))}
    raise SystemExit('TARGET_HEADER_NOT_FOUND')


def similarity(t, c, mode='normalized'):
    tv = [norm(x, mode) for x in t]
    cv = [norm(x, mode) for x in c]
    td = (text_of(tv[2]) + ' ' + text_of(tv[3])).strip()
    cd = (text_of(cv[2]) + ' ' + text_of(cv[3])).strip()
    s = 0.7 * difflib.SequenceMatcher(None, td, cd).ratio()
    s += 0.15 * (tv[4] == cv[4]) + 0.15 * (tv[5] == cv[5])
    return s


def align(T, C):
    n, m = len(T), len(C)
    sim = [[similarity(T[i], C[j]) for j in range(m)] for i in range(n)]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    move = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            opts = [(best[i + 1][j], 'skip_t'), (best[i][j + 1], 'skip_c')]
            if sim[i][j] >= 0.5:
                opts.append((best[i + 1][j + 1] + sim[i][j], 'pair'))
            best[i][j], move[i][j] = max(opts, key=lambda x: x[0])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        mv = move[i][j]
        if mv == 'pair':
            pairs.append((i, j, sim[i][j])); i += 1; j += 1
        elif mv == 'skip_t':
            i += 1
        else:
            j += 1
    return pairs


def score(T, C, pairs, mode):
    pt = {i for i, _, _ in pairs}
    pc = {j for _, j, _ in pairs}
    matched = counted = 0
    per = {COLS[k]: [0, 0] for k in SCORED}
    gh_nonnull = 0
    for i, j, _ in pairs:
        for k in SCORED:
            a, b = norm(T[i][k], mode), norm(C[j][k], mode)
            if a is None and b is None:
                continue
            counted += 1; per[COLS[k]][1] += 1
            if a == b:
                matched += 1; per[COLS[k]][0] += 1
        gh_nonnull += sum(norm(C[j][k], mode) is not None for k in (6, 7))
    for i in range(len(T)):
        if i not in pt:
            for k in SCORED:
                if norm(T[i][k], mode) is not None:
                    counted += 1; per[COLS[k]][1] += 1
    for j in range(len(C)):
        if j not in pc:
            for k in SCORED:
                if norm(C[j][k], mode) is not None:
                    counted += 1; per[COLS[k]][1] += 1
    for k in JOB_LEVEL:
        tv = [norm(r[k], mode) for r in T if norm(r[k], mode) is not None]
        cv = [norm(r[k], mode) for r in C if norm(r[k], mode) is not None]
        if not tv and not cv:
            continue
        tm = max(set(tv), key=tv.count) if tv else None
        cm = max(set(cv), key=cv.count) if cv else None
        counted += 1; per[COLS[k]] = [int(tm == cm), 1]
        matched += int(tm == cm)
    return {'matched': matched, 'counted': counted, 'score': (matched / counted) if counted else None,
            'per_field': {k: {'matched': v[0], 'counted': v[1]} for k, v in per.items()},
            'cps_GH_nonnull_on_paired_rows': gh_nonnull}


def evaluate(target_path, carrier):
    tg = load_target(target_path)
    T = [r['values'] for r in tg['rows']]
    C = [it['values'] for it in carrier['items']]
    pairs = align(T, C)
    out = {'schema': VERSION, 'target_sheet': tg['sheet'], 'target_header_row': tg['header_row'],
           'target_column_map': tg['column_map'], 'target_columns_in_canonical_order': tg['columns_in_canonical_order'],
           'target_rows': len(T), 'cps_rows': len(C), 'paired_rows': len(pairs),
           'row_recall': (len(pairs) / len(T)) if T else None, 'row_precision': (len(pairs) / len(C)) if C else None,
           'unpaired_target_rows': [tg['rows'][i]['row'] for i in range(len(T)) if i not in {p[0] for p in pairs}],
           'unpaired_cps_ids': [carrier['items'][j]['id'] for j in range(len(C)) if j not in {p[1] for p in pairs}],
           'pairs': [{'target_row': tg['rows'][i]['row'], 'cps_id': carrier['items'][j]['id'], 'similarity': round(s, 4)} for i, j, s in pairs],
           'modes': {m: score(T, C, pairs, m) for m in ('normalized', 'strict')}}
    g = out['modes']['normalized']['score']
    out['governing'] = {'mode': 'normalized', 'score': g, 'threshold': 0.95, 'case_matches_at_95': (g is not None and g >= 0.95)}
    return out


def main():
    ap = argparse.ArgumentParser()
    for k in ('target', 'target-sha', 'carrier', 'carrier-sha', 'out'):
        ap.add_argument('--' + k, required=True)
    a = ap.parse_args()
    if sha(a.target) != a.target_sha:
        raise SystemExit('TARGET_SHA_MISMATCH')
    if sha(a.carrier) != a.carrier_sha:
        raise SystemExit('CARRIER_SHA_MISMATCH')
    carrier = json.loads(Path(a.carrier).read_text(encoding='utf-8'))
    res = evaluate(a.target, carrier)
    res['inputs'] = {'target_sha256': a.target_sha, 'carrier_sha256': a.carrier_sha, 'evaluator_sha256': sha(__file__)}
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + '\n', encoding='utf-8')
    m = res['modes']
    print(json.dumps({'target_rows': res['target_rows'], 'cps_rows': res['cps_rows'], 'paired': res['paired_rows'],
                      'normalized': [m['normalized']['matched'], m['normalized']['counted']],
                      'strict': [m['strict']['matched'], m['strict']['counted']], 'governing': res['governing']}, default=str))


if __name__ == '__main__':
    main()
