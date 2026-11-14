"""O72 pattern tests for candidate 046i (owner decision O72; FIELD_ROLES R59 items 2 and 9) with invented workbooks only.

Each invented workbook is written as .xlsx and converted to .xls by LibreOffice, then prepared exactly as runner v4 does
(make_job_config.py, then the builder of its format with python3 -I -S -B; the unbound inventory stands in for
render_views.py, which only binds view image pins), and the scope stage runs on it: scope_tool.py; for PROPOSED an
invented reader, scope_agree.py, make_scoped_inventory.py build and --verify, and route check-inventory on the scoped
packet. Every workbook holds more than 2,500 literal or cached-formula content cells unless a case says otherwise.

No total row (BILL1.NOTOTAL.v1), positive cases:
  NT1 a priced bill without a 合計/總計 row, a summary sheet and an analysis sheet: the bill sheet to its last content row,
      R51 condition (i) false, the analysis sheet out of scope, flags BILL1_NO_TOTAL_ROW and NEAR_BILL1_CANDIDATE;
  NT2 an unpriced bill without a total and an analysis sheet whose blocks link to its lines: condition (i) true, the
      analysis sheet in scope; a reader that names the bill sheet with the analysis sheet in scope freezes FROZEN_AGREED;
  NT3 a signature line and a note below the last item, no total: end_row is the note's row;
  NT5 the last content row has content only beyond column J: the digest's last rows still name it;
  NT6 unpriced lines, a signature line, then an item-like priced line, and an analysis sheet (design finding R3): the
      tool's condition (i) is false and the analysis sheet is out of scope; the digest shows the priced line; a reader
      that follows the template puts the analysis sheet in scope and the case is held.
  NT7 (046i review finding F2) NT6 without an analysis sheet: no deterministic hold applies (condition (i) is false and
      R51_ALL_UNPRICED_WITHOUT_ANALYSIS_SHEET is not raised); a reader that follows the template (no analysis sheet:
      end_row null) holds the case;
  NTB (review finding S6) a block-labelled total (甲站合計) in the price column and no exact total: BILL1.NOTOTAL.v1; the
      digest lists the block total and counts exactly the rows it lists, so a reader that follows the template's no-total
      trigger takes the last content row and freezes FROZEN_AGREED.
  (NT4, NT1 with empty sheets, is in run_empty_sheet_tests.py.)
No total row, negative cases:
  NTx1 two sheets, each with one six-label header and no total; NTx2 one sheet with two six-label header rows; NTx3 a
  no-total six-label sheet plus a five-of-six row on another sheet; NTx4 a six-label sheet with a 合計 in its price
  column but no positive price: each HOLD BILL1_CANDIDATES_NOT_ONE under BILL1.v1 (the identity comparison with the
  046g baseline is in the build's comparison run). NOTOTAL-specific holds: NTx5 no item-like line (NO_IN_RANGE_LINES),
  NTx6 an all-unpriced bill and no analysis sheet (R51_ALL_UNPRICED_WITHOUT_ANALYSIS_SHEET), NTx7 a variant 合計： in the
  price column (not exact): the tool proposes BILL1.NOTOTAL.v1 and a reader that takes that row as the end row holds it.
Whole workbook (BILL1.NOHEADER.v1), positive cases:
  NH1 a single sheet of analysis blocks only: role analysis, in scope, no linked block;
  NH2 a list headed 序號/品名規格 (four of the six labels), a summary sheet, a resource sheet and a memo: every sheet in
      scope with its computed role, flag BILL1_NO_HEADER; the scoped packet equals the full inventory plus the fact;
  NH4 NH2 plus a styled-blank sheet (rows x columns > 0, no content cell): in scope, role other, OTHER_ROLE_SHEET; the
      agreeing reader freezes FROZEN_AGREED and check-inventory passes (design finding C5).
  (NH3, NH2 with an empty and a hidden sheet, is in run_empty_sheet_tests.py.)
Whole workbook, negative and boundary cases: NHx1 only a five-of-six header row: HOLD BILL1_CANDIDATES_NOT_ONE; NHx2 NH1
below the threshold: NOT_APPLIED, rule BILL1.v1, no bill; V1J (review finding S6) a BILL1.v1 bill whose 單價 and 複價
columns lie beyond column J: PROPOSED under BILL1.v1, and the digest shows its header row with four of the six labels and
more_cells_beyond_column_J, the case the template's 'count only the labels shown' sentence covers.
Agreement: on NT1 the agreeing reader, a reader whose end row is the last item line, and a reader with nulls; on NH2 the
agreeing reader, a reader that names a bill sheet, one that leaves a non-empty sheet out, one that puts an empty sheet in
(NH2 with an empty sheet), and one with nulls and a bill role; a stand-in reader on either rule (not admissible; the
route rejects the packet). No project data is read.

Usage: python3 -I -B run_o72_tests.py --work /abs/NEWDIR --deps-bundle /abs/BUNDLE [--soffice soffice] [--formats xlsx,xls]
"""
import argparse, importlib.util, io, json, sys, zipfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ES = _load('cps046i_empty_sheet_tests_for_o72', HERE / 'run_empty_sheet_tests.py')
TOOL, AGREE, SCOPED, ROUTE = ES.TOOL, ES.AGREE, ES.SCOPED, ES.ROUTE
run, jout, sha = ES.run, ES.jout, ES.sha
NOTOTAL, NOHEADER, V1 = 'BILL1.NOTOTAL.v1', 'BILL1.NOHEADER.v1', 'BILL1.v1'
STYLED = '@@STYLED-BLANK@@'
results = []


def record(name, ok, detail=None):
    results.append({'test': name, 'pass': bool(ok), **({'detail': detail} if detail is not None and not ok else {})})


# ------------------------------------------------------------------ invented sheets
SIX = ('項次', '項目及說明', '單位', '數量', '單價', '複價')


def bill(n, priced=True, total=False, header=SIX, title='示例工程 詳細價目表', tail=(), start=1, name_fmt='示例材料第{}項', unit='只'):
    """A bill sheet: title row, header row, n item lines (priced or unpriced), an optional 合計 row in the price column and
    trailing rows (list of (column, value) per row). Returns (cells, last row)."""
    cells = [('A1', title, False)] + [(c + '2', x, False) for c, x in zip('ABCDEF', header)]
    for i in range(n):
        r = 3 + i
        cells += [(f'A{r}', str(start + i), False), (f'B{r}', name_fmt.format(start + i), False), (f'C{r}', unit, False), (f'D{r}', i % 5 + 1, False)]
        if priced:
            cells += [(f'E{r}', 100 + i, False), (f'F{r}', (i % 5 + 1) * (100 + i), True)]
    r = 3 + n
    if total:
        cells += [(f'E{r}', total if isinstance(total, str) else '合計', False), (f'F{r}', 123456 if priced else 0, True)]
        r += 1
    for row in tail:
        cells += [(f'{c}{r}', v, False) for c, v in row]
        r += 1
    return cells, r - 1


def bill_wide(n):
    """A BILL1.v1 bill whose 單價 and 複價 columns are K and L (beyond the digest's column J), with an exact 合計 in K."""
    head = ('項次', '項目及說明', '單位', '數量', '規格', '廠牌', '型號', '產地', '交期', '備註', '單價', '複價')
    cells = [('A1', '示例工程 詳細價目表', False)] + [(c + '2', x, False) for c, x in zip('ABCDEFGHIJKL', head)]
    for i in range(n):
        r = 3 + i
        cells += [(f'A{r}', str(1 + i), False), (f'B{r}', f'示例寬表材料第{1 + i}項', False), (f'C{r}', '只', False), (f'D{r}', i % 5 + 1, False),
                  (f'K{r}', 100 + i, False), (f'L{r}', (i % 5 + 1) * (100 + i), True)]
    r = 3 + n
    return cells + [(f'K{r}', '合計', False), (f'L{r}', 123456, True), (f'A{r + 1}', SIG[0][1], False)]


def summary():
    return [('A1', '項次', False), ('B1', '項目及說明', False), ('C1', '複價', False), ('A2', '壹', False), ('B2', '示例詳細表', False),
            ('C2', 900000, True)]


def analysis(n, name_fmt='示例材料第{}項', start=1, header=('工料名稱', '單位', '數量', '單價', '複價')):
    cells, r = [], 1
    for i in range(n):
        cells += [(f'A{r}', f'示例{i + 1}', False), (f'B{r}', '工作項目：' + name_fmt.format(start + i), False),
                  (f'E{r}', f'計價代碼：M{10000000 + i}', False)]
        cells += [(c + str(r + 1), x, False) for c, x in zip('BCDEF', header)]
        cells += [(f'B{r + 2}', '示例零件甲', False), (f'C{r + 2}', '個', False), (f'D{r + 2}', 2, False),
                  (f'B{r + 3}', '示例零件乙', False), (f'C{r + 3}', '式', False), (f'D{r + 3}', 1, False), (f'B{r + 4}', '合計', False)]
        r += 5
    return cells


def resource():
    return [(c + '1', x, False) for c, x in zip('ABCD', ('工項代碼', '人工', '機具', '材料'))] + [('A2', 'X0001', False), ('B2', 1, False)]


def memo():
    return [('A1', '示例說明', False), ('A2', '示例內容第二行', False)]


def nh_list(n=450):
    cells, last = bill(n, header=('序號', '品名規格', '單位', '數量', '單價', '金額'), title='示例工程 價目表', total=True)
    return cells


SIG = [('A', '報價人：示例機電股份有限公司')]
NOTE = [('A', '以上單價含運費')]


def S(name, cells, state='visible'):
    return (name, cells, [], state)


def workbooks():
    """tag -> (sheets, expectations)."""
    nt1_bill, nt1_last = bill(450, tail=[[('F', 226000)], SIG])
    nt2_bill, nt2_last = bill(450, priced=False)
    nt3_bill, nt3_last = bill(450, tail=[SIG, NOTE])
    nt5_bill, nt5_last = bill(450, tail=[[('L', '示例欄外備註')]])
    nt6_bill, nt6_last = bill(450, priced=False, tail=[SIG, [('A', '451'), ('B', '示例運費'), ('C', '式'), ('D', 1), ('E', 2000), ('F', 2000)]])
    ntx7_bill, ntx7_last = bill(450, total='合計：', tail=[SIG])
    nt7_bill, nt7_last = bill(700, priced=False, tail=[SIG, [('A', '701'), ('B', '示例運費'), ('C', '式'), ('D', 1), ('E', 2000), ('F', 2000)]])
    ntb_bill, ntb_last = bill(450, total='甲站合計', tail=[SIG])
    return {
        'nt1': ([S('總表', summary()), S('詳細表', nt1_bill), S('單價分析', analysis(180, '示例分析項目{}'))],
                {'status': 'PROPOSED', 'rule': NOTOTAL, 'bill': 2, 'end_row': nt1_last, 'in_scope': [2], 'cond_i': False,
                 'flags': {'BILL1_NO_TOTAL_ROW', 'NEAR_BILL1_CANDIDATE'}}),
        'nt2': ([S('詳細表', nt2_bill), S('單價分析', analysis(180))],
                {'status': 'PROPOSED', 'rule': NOTOTAL, 'bill': 1, 'end_row': nt2_last, 'in_scope': [1, 2], 'cond_i': True}),
        'nt3': ([S('總表', summary()), S('詳細表', nt3_bill)],
                {'status': 'PROPOSED', 'rule': NOTOTAL, 'bill': 2, 'end_row': nt3_last, 'in_scope': [2], 'cond_i': False}),
        'nt5': ([S('總表', summary()), S('詳細表', nt5_bill)],
                {'status': 'PROPOSED', 'rule': NOTOTAL, 'bill': 2, 'end_row': nt5_last, 'in_scope': [2], 'cond_i': False}),
        'nt6': ([S('詳細表', nt6_bill), S('單價分析', analysis(180))],
                {'status': 'PROPOSED', 'rule': NOTOTAL, 'bill': 1, 'end_row': nt6_last, 'in_scope': [1], 'cond_i': False}),
        'ntx1': ([S('詳細表甲', bill(230, name_fmt='示例甲材料第{}項')[0]), S('詳細表乙', bill(230, name_fmt='示例乙材料第{}項')[0])],
                 {'status': 'HOLD', 'rule': V1, 'holds': ['BILL1_CANDIDATES_NOT_ONE']}),
        'ntx2': ([S('詳細表', bill(230)[0] + [(c + '240', x, False) for c, x in zip('ABCDEF', SIX)]
                    + [(f'{c}{r}', v, False) for r in range(241, 471) for c, v in (('A', str(r)), ('B', f'示例續項{r}'), ('C', '只'), ('D', 1), ('E', 50), ('F', 50))])],
                 {'status': 'HOLD', 'rule': V1, 'holds': ['BILL1_CANDIDATES_NOT_ONE']}),
        'ntx3': ([S('詳細表', bill(450)[0]), S('另表', bill(5, header=('項次', '項目及說明', '單位', '數量', '單價', '總價'), name_fmt='示例另項{}', total=True)[0])],
                 {'status': 'HOLD', 'rule': V1, 'holds': ['BILL1_CANDIDATES_NOT_ONE']}),
        'ntx4': ([S('詳細表', bill(450, priced=False, total=True)[0]), S('單價分析', analysis(180))],
                 {'status': 'HOLD', 'rule': V1, 'holds': ['BILL1_CANDIDATES_NOT_ONE']}),
        'ntx5': ([S('詳細表', bill(0, tail=[[('A', '示例說明一')], [('A', '示例說明二')]])[0]), S('單價分析', analysis(300))],
                 {'status': 'HOLD', 'rule': NOTOTAL, 'holds': ['NO_IN_RANGE_LINES']}),
        'ntx6': ([S('詳細表', bill(700, priced=False)[0])],
                 {'status': 'HOLD', 'rule': NOTOTAL, 'holds': ['R51_ALL_UNPRICED_WITHOUT_ANALYSIS_SHEET']}),
        'ntx7': ([S('總表', summary()), S('詳細表', ntx7_bill)],
                 {'status': 'PROPOSED', 'rule': NOTOTAL, 'bill': 2, 'end_row': ntx7_last, 'in_scope': [2], 'cond_i': False}),
        'nh1': ([S('單價分析', analysis(450))],
                {'status': 'PROPOSED', 'rule': NOHEADER, 'in_scope': [1], 'roles': ['analysis']}),
        'nh2': ([S('價目表', nh_list()), S('總表', summary()), S('資源統計', resource()), S('說明', memo())],
                {'status': 'PROPOSED', 'rule': NOHEADER, 'in_scope': [1, 2, 3, 4], 'roles': ['other', 'summary', 'resource_statistics', 'other']}),
        'nh2e': ([S('價目表', nh_list()), S('空白', []), S('總表', summary()), S('資源統計', resource()), S('說明', memo())],
                 {'status': 'PROPOSED', 'rule': NOHEADER, 'in_scope': [1, 3, 4, 5], 'roles': ['other', 'other', 'summary', 'resource_statistics', 'other']}),
        'nh4': ([S('價目表', nh_list()), S('總表', summary()), S('資源統計', resource()), S('說明', memo()), S('格式', [('B2', STYLED, False), ('C4', STYLED, False)])],
                {'status': 'PROPOSED', 'rule': NOHEADER, 'in_scope': [1, 2, 3, 4, 5], 'roles': ['other', 'summary', 'resource_statistics', 'other', 'other']}),
        'nhx1': ([S('價目表', bill(450, header=('項次', '品名規格', '單位', '數量', '單價', '複價'), total=True)[0])],
                 {'status': 'HOLD', 'rule': V1, 'holds': ['BILL1_CANDIDATES_NOT_ONE']}),
        'nhx2': ([S('單價分析', analysis(40))],
                 {'status': 'NOT_APPLIED', 'rule': V1}),
        'nt7': ([S('詳細表', nt7_bill)],
                {'status': 'PROPOSED', 'rule': NOTOTAL, 'bill': 1, 'end_row': nt7_last, 'in_scope': [1], 'cond_i': False}),
        'ntb': ([S('總表', summary()), S('詳細表', ntb_bill)],
                {'status': 'PROPOSED', 'rule': NOTOTAL, 'bill': 2, 'end_row': ntb_last, 'in_scope': [2], 'cond_i': False}),
        'v1j': ([S('總表', summary()), S('詳細表', bill_wide(450))],
                {'status': 'PROPOSED', 'rule': V1, 'in_scope': [2]}),
    }


def styled_xlsx(path):
    """Turn the STYLED placeholder cells into styled cells without a value (a fill style), as a spreadsheet program writes
    formatted blank cells: the sheet gets rows x columns > 0 and no content cell."""
    src = path.read_bytes()
    zin = zipfile.ZipFile(io.BytesIO(src))
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for i in zin.infolist():
            b = zin.read(i.filename)
            if i.filename == 'xl/styles.xml':
                b = (b.replace(b'<fills count="2">', b'<fills count="3">')
                     .replace(b'<fill><patternFill patternType="gray125"/></fill></fills>',
                              b'<fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/></patternFill></fill></fills>')
                     .replace(b'<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>',
                              b'<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                              b'<xf numFmtId="0" fontId="0" fillId="2" borderId="0" xfId="0" applyFill="1"/></cellXfs>'))
            elif i.filename.startswith('xl/worksheets/'):
                for addr in (b'B2', b'C4'):
                    b = b.replace(b'<c r="' + addr + b'" t="inlineStr"><is><t xml:space="preserve">' + STYLED.encode() + b'</t></is></c>',
                                  b'<c r="' + addr + b'" s="1"/>')
            z.writestr(i, b)
    path.write_bytes(out.getvalue())


class Env(ES.Env):
    def source(self, tag, sheets, fmt):
        d = self.work / 'sources' / tag
        d.mkdir(parents=True)
        x = d / 'source.xlsx'
        ES.write_xlsx(x, sheets)
        if any(STYLED in str(c[1]) for s in sheets for c in s[1]):
            styled_xlsx(x)
        if fmt == 'xlsx':
            return x
        import subprocess
        prof = self.work / 'lo_profile'
        p = subprocess.run([self.soffice, f'-env:UserInstallation=file://{prof}', '--headless', '--convert-to', 'xls', '--outdir', str(d / 'xls'), str(x)],
                           capture_output=True, text=True, timeout=300)
        out = d / 'xls' / 'source.xls'
        if p.returncode != 0 or not out.is_file():
            raise RuntimeError('LibreOffice conversion failed: ' + (p.stderr or p.stdout)[-300:])
        return out


def reader(prop, dig, **over):
    p = json.loads(prop.read_text(encoding='utf-8'))
    r = {'schema': 'cps.scope-reader-response.v1', 'case_id': p['case_id'], 'digest_sha256': sha(dig.read_bytes()),
         'reader': {'kind': over.pop('kind', 'fresh_context_scope_reader'), 'model': 'invented-test-reader', 'effort': 'n/a'},
         'bill_sheet_index': p['bill']['sheet_index'], 'end_row': p['bill']['end_row'],
         'sheets': [{'index': s['index'], 'role': s['role'], 'in_scope': s['in_scope'], 'reason': 'invented test reason'} for s in p['sheets']],
         'doubts': []}
    for k, v in over.items():
        if k == 'flags':
            for i, f in v.items():
                r['sheets'][i - 1]['in_scope'] = f
        elif k == 'roles':
            for i, role in v.items():
                r['sheets'][i - 1]['role'] = role
        else:
            r[k] = v
    return r


def agree(d, tag, rd):
    prop, dig = d / 'tool' / 'SCOPE_PROPOSAL.json', d / 'tool' / 'SCOPE_DIGEST.json'
    rp = d / f'reader_{tag}.json'
    rp.write_text(json.dumps(rd, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    code, out, err = run(AGREE, '--proposal', prop, '--digest', dig, '--reader', rp, '--out-dir', d / f'agree_{tag}')
    return code, jout(out), jout(err), d / f'agree_{tag}'


def case(env, fmt, tag, n, sheets, exp):
    cid = f'99972{n:02d}'
    d, inv = env.prepare(f'{tag}_{fmt}', env.source(f'{tag}_{fmt}', sheets, fmt), '材料清單', cid)
    invd = json.loads(inv.read_text(encoding='utf-8'))
    litcf = sum(1 for c in invd['cells'] if c['state'] in ('literal', 'cached_formula') and c['saved_value'] not in (None, ''))
    sd = d / 'stage'
    sd.mkdir()
    code, out, err = run(TOOL, '--inventory', inv, '--out-dir', sd / 'tool')
    p = json.loads((sd / 'tool' / 'SCOPE_PROPOSAL.json').read_text(encoding='utf-8')) if code in (0, 4) else {}
    name = f'{tag}_{fmt}'
    ok = (code == (4 if exp['status'] == 'HOLD' else 0) and p.get('status') == exp['status'] and p['bill']['rule'] == p['rule']['bill'] == exp['rule']
          and (litcf > 2500) == (exp['status'] != 'NOT_APPLIED'))
    if 'holds' in exp:
        ok = ok and [h['code'] for h in p['holds']] == exp['holds']
    if 'bill' in exp:
        ok = ok and p['bill']['sheet_index'] == exp['bill'] and p['bill']['end_row'] == exp['end_row'] and p['bill']['end_cell'] is None \
            and p['bill']['header_row'] == 2 and p['bill']['candidates'] == []
    if 'in_scope' in exp:
        ok = ok and [s['index'] for s in p['sheets'] if s['in_scope']] == exp['in_scope']
    if 'cond_i' in exp:
        ok = ok and p['r51']['condition_i_all_unpriced_no_status'] is exp['cond_i']
    if 'flags' in exp:
        ok = ok and exp['flags'] <= {f['code'] for f in p['flags']}
    if 'roles' in exp:
        ok = ok and [s['role'] for s in p['sheets']] == exp['roles'] and p['bill']['sheet_index'] is None and p['bill']['end_row'] is None \
            and p['bill']['header_row'] is None and p['r51']['in_range_lines'] == 0 and p['flags'][0]['code'] == 'BILL1_NO_HEADER' \
            and all(s['linked_analysis_blocks'] == 0 for s in p['sheets'])
    record(f'{name}: scope_tool.py {exp["status"]} under {exp["rule"]} as expected', ok,
           {'code': code, 'err': err[-300:], 'litcf': litcf, 'status': p.get('status'), 'bill': p.get('bill'), 'holds': p.get('holds'),
            'sheets': [(s['index'], s['role'], s['in_scope']) for s in p.get('sheets', [])], 'flags': [f['code'] for f in p.get('flags', [])],
            'r51': p.get('r51', {}).get('by_state')})
    return {'d': sd, 'inv': inv, 'invd': invd, 'proposal': p, 'code': code}


def build(c, dec_dir, tag):
    dec = dec_dir / 'SCOPE_DECISION.json'
    code, out, err = run(SCOPED, '--full', c['inv'], '--decision', dec, '--out-dir', c['d'] / f'packet_{tag}')
    if code != 0:
        return {'code': code, 'err': err[-300:]}
    scoped = c['d'] / f'packet_{tag}' / 'SOURCE_INVENTORY.json'
    rc = json.loads((c['d'] / f'packet_{tag}' / 'SCOPED_INVENTORY_RECEIPT.json').read_text(encoding='utf-8'))
    vcode, vout, _ = run(SCOPED, '--verify', '--full', c['inv'], '--decision', dec, '--scoped', scoped, '--expect-scoped-sha256', rc['scoped_inventory_sha256'])
    return {'code': 0, 'scoped': scoped, 'receipt': rc, 'verify_code': vcode, 'verify': jout(vout), 'check': ES.check_inventory(scoped)}


def checks(fmt, cs):
    """Digest, agreement and build checks on the cases of one format."""
    nt1, nt2, nt3, nt5, nt6, ntx7 = (cs[k] for k in ('nt1', 'nt2', 'nt3', 'nt5', 'nt6', 'ntx7'))
    nh2, nh2e, nh4, nh1 = cs['nh2'], cs['nh2e'], cs['nh4'], cs['nh1']
    nt7, ntb, v1j = cs['nt7'], cs['ntb'], cs['v1j']
    # NT1: digest additions, reason, agreement, build
    dg = json.loads((nt1['d'] / 'tool' / 'SCOPE_DIGEST.json').read_text(encoding='utf-8'))
    b = next(s for s in dg['sheets'] if s['index'] == 2)
    lines = b['counts'].get('lines_from_first_item_below_header_to_last_content_row', {})
    record(f'nt1_{fmt}: the digest counts the lines to the last content row and shows the last priced lines',
           lines.get('lines') == 450 and lines.get('priced') == 450 and b['counts'].get('last_unpriced_no_status_line_row') is None
           and b['counts'].get('priced_or_not_estimated_line_rows') == list(range(3, 23)) and len(b.get('priced_or_not_estimated_lines_tail', [])) == 3
           and b['price_column_total_rows_count'] == 0 and b['last_rows'][-1]['row'] == nt1['proposal']['bill']['end_row'], b.get('counts'))
    code, o, e, ad = agree(nt1['d'], 'agreeing', reader(nt1['d'] / 'tool' / 'SCOPE_PROPOSAL.json', nt1['d'] / 'tool' / 'SCOPE_DIGEST.json'))
    fact = json.loads((ad / 'SCOPE_DECISION.json').read_text(encoding='utf-8'))['scope_fact'] if code == 0 else {}
    record(f'nt1_{fmt}: an agreeing reader freezes an admissible BILL1.NOTOTAL.v1 decision', code == 0 and o.get('admissible') is True
           and fact.get('bill_rule') == NOTOTAL and fact.get('end_row') == nt1['proposal']['bill']['end_row'] and fact.get('bill_header_row') == 2, [o, e])
    if code == 0:
        bo = build(nt1, ad, 'agreeing')
        record(f'nt1_{fmt}: the scoped packet keeps the bill sheet only; --verify PASS; check-inventory PASS, scope applied, policy applied',
               bo['code'] == 0 and bo['verify_code'] == 0 and bo['verify']['status'] == 'PASS' and bo['check']['status'] == 'PASS'
               and bo['check']['scope'] == 'applied' and bo['check']['policy_checks'] == 'applied'
               and [s['index'] for s in json.loads(bo['scoped'].read_text(encoding='utf-8'))['sheets'] if s['in_scope']] == [2], bo)
    last_item = nt1['proposal']['bill']['end_row'] - 2
    for tag, over, whats in (('end_row_last_item', {'end_row': last_item}, {'end_row'}),
                             ('nulls', {'bill_sheet_index': None, 'end_row': None}, {'bill_sheet_index', 'end_row', 'reader_bill_role'})):
        code, o, e, _ = agree(nt1['d'], tag, reader(nt1['d'] / 'tool' / 'SCOPE_PROPOSAL.json', nt1['d'] / 'tool' / 'SCOPE_DIGEST.json', **over))
        record(f'nt1_{fmt}: a reader with {tag} holds the case ({sorted(whats)})', code == 3 and o.get('status') == 'HELD_FOR_OWNER'
               and {x['what'] for x in o.get('differences', [])} == whats, o)
    code, o, e, ad = agree(nt1['d'], 'standin', reader(nt1['d'] / 'tool' / 'SCOPE_PROPOSAL.json', nt1['d'] / 'tool' / 'SCOPE_DIGEST.json', kind='engineering_stand_in'))
    bo = build(nt1, ad, 'standin') if code == 0 else {}
    record(f'nt1_{fmt}: a stand-in decision is not admissible and the route rejects its packet', code == 0 and o.get('admissible') is False
           and bo.get('check', {}).get('violations') == ['R59_SCOPE_FACT_INVALID'], [o, bo.get('check')])
    # NT2: R51 (i); the reader names the unpriced bill sheet with the analysis sheet in scope (design finding R5)
    record(f'nt2_{fmt}: the analysis sheet is in scope under R51 (i) with blocks linked to the unpriced lines',
           nt2['proposal']['sheets'][1]['reason'].startswith('analysis: every in-range bill line') and
           nt2['proposal']['r51']['analysis_sheets']['2']['linked_blocks'] == 180, nt2['proposal']['r51'].get('analysis_sheets'))
    code, o, e, ad = agree(nt2['d'], 'agreeing', reader(nt2['d'] / 'tool' / 'SCOPE_PROPOSAL.json', nt2['d'] / 'tool' / 'SCOPE_DIGEST.json'))
    record(f'nt2_{fmt}: a reader that names the unpriced bill sheet with the analysis sheet in scope freezes FROZEN_AGREED',
           code == 0 and o.get('status') == 'FROZEN_AGREED' and o.get('admissible') is True, [o, e])
    if code == 0:
        bo = build(nt2, ad, 'agreeing')
        record(f'nt2_{fmt}: the scoped packet keeps the bill and analysis sheets; --verify PASS; check-inventory PASS',
               bo['code'] == 0 and bo['verify_code'] == 0 and bo['check']['status'] == 'PASS' and bo['check']['scope'] == 'applied', bo)
    # NT3, NT5: end rows
    nt3b = nt3['proposal']['bill']
    record(f'nt3_{fmt}: the end row is the note row after the signature line, not the last item line', nt3b['end_row'] == 454 and nt3b['first_item_row'] == 3, nt3b)
    dg5 = json.loads((nt5['d'] / 'tool' / 'SCOPE_DIGEST.json').read_text(encoding='utf-8'))
    lr = next(s for s in dg5['sheets'] if s['index'] == 2)['last_rows'][-1]
    record(f'nt5_{fmt}: the last content row (content only beyond column J) is the end row and the digest names it',
           lr['row'] == nt5['proposal']['bill']['end_row'] == 453 and lr['cells'] == [] and lr.get('more_cells_beyond_column_J') == 1, lr)
    # NT6 (design finding R3): a priced line below the signature line under an all-unpriced range
    dg6 = json.loads((nt6['d'] / 'tool' / 'SCOPE_DIGEST.json').read_text(encoding='utf-8'))
    c6 = next(s for s in dg6['sheets'] if s['index'] == 1)
    record(f'nt6_{fmt}: the digest shows the only priced line after the signature line and the last unpriced line before it',
           c6['counts']['priced_or_not_estimated_line_rows'] == [454] and c6['counts']['last_unpriced_no_status_line_row'] == 452
           and [x['row'] for x in c6['priced_or_not_estimated_lines_tail']] == [454]
           and [r['row'] for r in c6['priced_or_not_estimated_lines_tail'][0]['context']] == [452, 453, 454], c6['counts'])
    code, o, e, _ = agree(nt6['d'], 'template_reader', reader(nt6['d'] / 'tool' / 'SCOPE_PROPOSAL.json', nt6['d'] / 'tool' / 'SCOPE_DIGEST.json', flags={2: True}))
    record(f'nt6_{fmt}: a reader following the template puts the analysis sheet in scope: held (in_scope)', code == 3
           and [x['what'] for x in o.get('differences', [])] == ['in_scope'], o)
    # NTx7: a variant total 合計： is not exact; the tool proposes BILL1.NOTOTAL.v1, the digest shows the row, a reader holds
    dg7 = json.loads((ntx7['d'] / 'tool' / 'SCOPE_DIGEST.json').read_text(encoding='utf-8'))
    t7 = next(s for s in dg7['sheets'] if s['index'] == 2)
    record(f'ntx7_{fmt}: the digest lists the variant total among the price-column total rows', t7['price_column_total_rows_count'] == 1
           and t7['price_column_total_rows'][0]['row'] == 453, t7.get('price_column_total_rows_count'))
    code, o, e, _ = agree(ntx7['d'], 'variant_end', reader(ntx7['d'] / 'tool' / 'SCOPE_PROPOSAL.json', ntx7['d'] / 'tool' / 'SCOPE_DIGEST.json', end_row=453))
    record(f'ntx7_{fmt}: a reader that takes the variant total row as the end row holds the case (end_row)', code == 3
           and [x['what'] for x in o.get('differences', [])] == ['end_row'], o)
    # NT7 (review finding F2): NT6 without an analysis sheet; nothing holds deterministically; the template's reader holds it
    p7 = nt7['proposal']
    dg7b = json.loads((nt7['d'] / 'tool' / 'SCOPE_DIGEST.json').read_text(encoding='utf-8'))
    c7 = next(s for s in dg7b['sheets'] if s['index'] == 1)['counts']
    record(f'nt7_{fmt}: no analysis sheet and a priced line after the signature line: no hold, the digest shows the priced line',
           p7['holds'] == [] and p7['r51']['analysis_sheets'] == {} and p7['r51']['by_state']['priced'] == 1
           and c7['priced_or_not_estimated_line_rows'] == [704] and c7['last_unpriced_no_status_line_row'] == 702, [p7.get('r51'), c7])
    code, o, e, _ = agree(nt7['d'], 'template_reader', reader(nt7['d'] / 'tool' / 'SCOPE_PROPOSAL.json', nt7['d'] / 'tool' / 'SCOPE_DIGEST.json', end_row=None))
    record(f'nt7_{fmt}: a reader following the template (no analysis sheet: end_row null) holds the case (end_row)', code == 3
           and o.get('status') == 'HELD_FOR_OWNER' and [x['what'] for x in o.get('differences', [])] == ['end_row'], o)
    # NTB (review finding S6): a block-labelled total in the price column is listed and counted; the no-total trigger applies
    dgb = json.loads((ntb['d'] / 'tool' / 'SCOPE_DIGEST.json').read_text(encoding='utf-8'))
    tb = next(s for s in dgb['sheets'] if s['index'] == 2)
    record(f'ntb_{fmt}: the digest lists the block total as the only price-column total row and its count equals the rows listed',
           tb['price_column_total_rows_count'] == len(tb['price_column_total_rows']) == 1 and tb['price_column_total_rows'][0]['row'] == 453
           and tb['last_rows'][-1]['row'] == ntb['proposal']['bill']['end_row'] == 454, tb.get('price_column_total_rows_count'))
    code, o, e, ad = agree(ntb['d'], 'template_reader', reader(ntb['d'] / 'tool' / 'SCOPE_PROPOSAL.json', ntb['d'] / 'tool' / 'SCOPE_DIGEST.json'))
    record(f'ntb_{fmt}: a reader that takes the last content row (block total only) freezes FROZEN_AGREED under BILL1.NOTOTAL.v1',
           code == 0 and o.get('status') == 'FROZEN_AGREED' and o.get('admissible') is True, [o, e])
    # V1J (review finding S6): a BILL1.v1 bill whose price columns lie beyond column J
    pj = v1j['proposal']
    dgj = json.loads((v1j['d'] / 'tool' / 'SCOPE_DIGEST.json').read_text(encoding='utf-8'))
    hj = next(s for s in dgj['sheets'] if s['index'] == 2)['first_header_row']
    shown = {str(c_['v']).strip() for c_ in hj['cells']}
    record(f'v1j_{fmt}: BILL1.v1 finds the wide bill; its digest header row shows four of the six labels and more cells beyond column J',
           pj['bill']['candidates'] == [2] and pj['bill']['sheet_index'] == 2 and pj['bill']['price_columns'] == ['K', 'L']
           and pj['bill']['end_row'] == 453 and hj['row'] == 2 and hj.get('more_cells_beyond_column_J') == 2
           and len(shown & {'項次', '項目及說明', '單位', '數量', '單價', '複價'}) == 4, [pj.get('bill'), hj.get('more_cells_beyond_column_J')])
    # NH1
    record(f'nh1_{fmt}: a single analysis sheet: in scope, no linked block, whole-workbook reason',
           nh1['proposal']['sheets'][0]['reason'].startswith('whole workbook:') and nh1['proposal']['r51']['analysis_sheets']['1']['linked_blocks'] == 0
           and nh1['proposal']['r51']['analysis_sheets']['1']['blocks'] == 450, nh1['proposal'].get('r51'))
    # NH2: agreement, build (identity), readers
    P2, D2 = nh2['d'] / 'tool' / 'SCOPE_PROPOSAL.json', nh2['d'] / 'tool' / 'SCOPE_DIGEST.json'
    code, o, e, ad = agree(nh2['d'], 'agreeing', reader(P2, D2))
    fact = json.loads((ad / 'SCOPE_DECISION.json').read_text(encoding='utf-8'))['scope_fact'] if code == 0 else {}
    record(f'nh2_{fmt}: an agreeing reader (nulls, every sheet in scope, no bill role) freezes an admissible BILL1.NOHEADER.v1 decision',
           code == 0 and o.get('admissible') is True and fact.get('bill_rule') == NOHEADER
           and [fact.get(k) for k in ('bill_sheet_index', 'bill_header_row', 'end_row')] == [None] * 3, [o, e])
    if code == 0:
        bo = build(nh2, ad, 'agreeing')
        full_lines = nh2['inv'].read_text(encoding='utf-8').split('\n')
        sl = bo['scoped'].read_text(encoding='utf-8').split('\n') if bo['code'] == 0 else []
        record(f'nh2_{fmt}: the scoped packet is the full inventory plus context:scope; --verify PASS; check-inventory PASS, scope applied',
               bo['code'] == 0 and bo['verify_code'] == 0 and bo['check']['status'] == 'PASS' and bo['check']['scope'] == 'applied'
               and bo['check']['policy_checks'] == 'applied' and bo['receipt']['verify']['stats']['cells_removed'] == 0
               and bo['receipt']['verify']['stats']['views_renumbered'] == 0
               and [x.rstrip(',') for x in sl if 'context:scope' not in x] == [x.rstrip(',') for x in full_lines] and len(sl) == len(full_lines) + 1, bo)
    for tag, over, whats in (('names_bill_sheet', {'bill_sheet_index': 1, 'end_row': 453, 'roles': {1: 'bill'}}, {'bill_sheet_index', 'end_row'}),
                             ('leaves_sheet_out', {'flags': {3: False}}, {'in_scope'}),
                             ('nulls_bill_role', {'roles': {1: 'bill'}}, {'reader_bill_role'})):
        code, o, e, _ = agree(nh2['d'], tag, reader(P2, D2, **over))
        record(f'nh2_{fmt}: a reader that {tag.replace("_", " ")} holds the case', code == 3 and whats <= {x['what'] for x in o.get('differences', [])}, o)
    code, o, e, ad = agree(nh2['d'], 'standin', reader(P2, D2, kind='engineering_stand_in'))
    bo = build(nh2, ad, 'standin') if code == 0 else {}
    record(f'nh2_{fmt}: a stand-in decision is not admissible and the route rejects its packet', code == 0 and o.get('admissible') is False
           and bo.get('check', {}).get('violations') == ['R59_SCOPE_FACT_INVALID'], [o, bo.get('check')])
    # NH2 with an empty sheet: the reader that puts the empty sheet in scope holds the case
    code, o, e, _ = agree(nh2e['d'], 'empty_in', reader(nh2e['d'] / 'tool' / 'SCOPE_PROPOSAL.json', nh2e['d'] / 'tool' / 'SCOPE_DIGEST.json', flags={2: True}))
    record(f'nh2e_{fmt}: a reader that puts the empty sheet in scope holds the case (in_scope)', code == 3
           and [x for x in o.get('differences', []) if x['what'] == 'in_scope'] == [{'what': 'in_scope', 'sheet': 2, 'tool': False, 'reader': True}], o)
    # NH4 (design finding C5): a styled-blank sheet is in scope (rows x columns > 0), role other, OTHER_ROLE_SHEET
    sb = next(s for s in nh4['invd']['sheets'] if s['index'] == 5)
    fl = [(f['sheet_index'], f['code']) for f in nh4['proposal']['flags']]
    record(f'nh4_{fmt}: the styled-blank sheet has rows x columns > 0, no content cell, is in scope with role other and OTHER_ROLE_SHEET',
           sb['rows'] * sb['columns'] > 0 and sb['in_scope'] is True and nh4['proposal']['sheets'][4]['content_cells'] == 0
           and nh4['proposal']['sheets'][4]['in_scope'] is True and (5, 'OTHER_ROLE_SHEET') in fl, [sb, fl])
    code, o, e, ad = agree(nh4['d'], 'agreeing', reader(nh4['d'] / 'tool' / 'SCOPE_PROPOSAL.json', nh4['d'] / 'tool' / 'SCOPE_DIGEST.json'))
    bo = build(nh4, ad, 'agreeing') if code == 0 else {}
    record(f'nh4_{fmt}: the agreeing reader freezes FROZEN_AGREED and check-inventory passes with scope applied',
           code == 0 and o.get('status') == 'FROZEN_AGREED' and bo.get('verify_code') == 0 and bo.get('check', {}).get('status') == 'PASS'
           and bo['check']['scope'] == 'applied', [o, bo.get('check')])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True, type=Path)
    ap.add_argument('--deps-bundle', required=True, type=Path)
    ap.add_argument('--soffice', default='soffice')
    ap.add_argument('--formats', default='xlsx,xls')
    a = ap.parse_args()
    if not a.work.is_absolute() or not a.deps_bundle.is_absolute():
        ap.error('absolute paths required')
    a.work.mkdir(parents=True, exist_ok=False)
    env = Env(a.work, a.deps_bundle, a.soffice)
    env.glossary.write_text(json.dumps(ES.small_sheet()[1], ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    wbs = workbooks()
    for fmt in a.formats.split(','):
        cs = {}
        for n, (tag, (sheets, exp)) in enumerate(wbs.items()):
            try:
                cs[tag] = case(env, fmt, tag, n + (0 if fmt == 'xlsx' else 50), sheets, exp)
            except Exception as e:
                record(f'{tag}_{fmt}: preparation ran', False, repr(e)[:400])
        try:
            checks(fmt, cs)
        except Exception as e:
            record(f'checks_{fmt}: ran', False, repr(e)[:600])
    summary = {'tests': len(results), 'passed': sum(r['pass'] for r in results), 'failed': [r for r in results if not r['pass']],
               'fixtures_invented': True, 'tools_sha256': {p.name: sha(p.read_bytes()) for p in (TOOL, AGREE, SCOPED, ES.JOBCFG, ROUTE)}}
    (a.work / 'O72_TEST_RESULTS.json').write_text(json.dumps({'summary': summary, 'results': results}, ensure_ascii=False, indent=1) + '\n',
                                                 encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if not summary['failed'] else 1


if __name__ == '__main__':
    sys.exit(main())
