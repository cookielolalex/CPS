"""CPS portable writer: reproduce writer004's saved workbook content with openpyxl.

NOT ADMITTED. This is a research export route. It may be used for CPS saved-cell and
visual QA only after an independent review admits it (owner decision 2026-11-03).

Route
  1. Gate: the archived writer004 validate_carrier_v4.mjs (unchanged bytes, run with node)
     must accept the carrier. The writer files are pinned by sha256.
  2. The four sheet matrices are computed by a Python reimplementation of writer004
     prepareMatrices (including its review-cell check), using JavaScript JSON semantics.
  3. Cross-check: writer004's own prepareMatrices runs on the same carrier through node
     (writer004_matrices.mjs) and must produce byte-identical EXPECTED_SAVED_VALUES.json
     text. Any difference refuses the carrier.
  4. Portable writability checks (characters openpyxl/XML cannot carry unambiguously).
  5. The .xlsx is written with openpyxl: same sheet names and order, cell values and value
     types (strings stay strings, numbers stay numbers, no formulas), and the writer004
     formatting that openpyxl can express. Bytes are reproducible (fixed zip/docProps times).

Mode v2 (candidate 046f carriers made by route v4.2, which keeps the route v4.1 relaxations unchanged;
FIELD_ROLES R48, R52, R54, R57; O13, O16)
  The route v4.2 Python writer port (validate_carrier_port) differs from writer004 validateCarrier in
  exactly the documented relaxation classes (cps046b_route.PORT_RELAXATIONS):
  - o13_m_n_selection_evidence: M/N proven by job-input context facts carry selection_evidence, which
    writer004 accepts for L only (SELECTION_ONLY_ENGINEERING_ID);
  - r57_null_c_research_draft: an item whose C is null has status research_draft, which writer004
    refuses (UNRESOLVED_ITEM_MUST_BE_HELD);
  - o16_q_unverified_adoption: a non-null Q while metadata.source_adoption is not verified. writer004
    never reads the adoption status, so this class needs no neutralization and no copy.
  A carrier with neither of the first two classes takes exactly the v1 route above (same bytes).
  Otherwise it is validated twice: (a) writer004 validate_carrier_v4 on a placeholder copy in which
  each relaxation is neutralized (O13: each M/N selection_evidence object becomes an equivalent-shaped
  location evidence object: location = the item's own location, anchor = the item's anchor, raw_text =
  the selection_evidence text, transformation and any other key unchanged; R57: status held, plus one
  placeholder review reason when review_reasons is empty), and (b) the route v4.2 Python port on the
  original carrier. The port file is pinned by sha256 (ROUTE_V4_SHA256), checked before it is executed. writer004 prepareMatrices runs on the copy and must equal the Python matrices of
  the copy byte for byte; the Python matrices of the original may differ from them only in the
  documented review cells: columns C-E of 欄位依據 <id>.M/.N rows of the O13 fields; column G (狀態)
  of every review row of each R57 item; and, where the copy added the placeholder reason, column F of
  that item's 項目 row plus the one added 待確認 row of the copy. The workbook and
  EXPECTED_SAVED_VALUES.json are built from the original carrier.

Usage
  python3 -I -B writer_portable.py --carrier /abs/carrier.json --out /abs/new-dir \
      --writer-dir /abs/dir-with-writer004.mjs [--node node] [--mode v1|v2]
Outputs in --out (created; must not exist): research-draft.xlsx, EXPECTED_SAVED_VALUES.json,
WRITER_RECEIPT.json. A refusal creates nothing and prints a JSON refusal on stderr (exit 1).
"""
import argparse, copy, datetime, hashlib, io, json, math, os, platform, re, subprocess, sys, tempfile, types, zipfile, zlib
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True

VERSION = 'cps-export-writer-portable.v2.2'
HERE = Path(__file__).resolve().parent
NODE_MATRICES = HERE / 'writer004_matrices.mjs'
# Mode v2: the route v4.2 Python writer port (candidate 046f). Its bytes are pinned by sha256 (046f review N3) and
# checked before the module is executed; its VERSION and PORT_RELAXATIONS keys are checked after.
ROUTE_V4_TOOL = HERE.parent / 'guideline046_006' / 'package' / 'tools' / 'cps046b_route.py'
ROUTE_V4_VERSION = 'cps046f-route.v4.2'
ROUTE_V4_SHA256 = '9db8033b8cb4fab6add87f60ba8b37e1994af6ff7f0559f305e892936df4811d'
RELAXATION_CLASSES = ('o13_m_n_selection_evidence', 'r57_null_c_research_draft', 'o16_q_unverified_adoption')
O13_COLS = ('M', 'N')
O13_PLACEHOLDER_METHOD = ('Each M/N evidence object holding selection_evidence is replaced in the copy of the carrier by: '
                          'the same object without selection_evidence, plus location = the item\'s own location, anchor = '
                          'the item\'s anchor and raw_text = the selection_evidence text (transformation and any other key '
                          'unchanged).')
R57_PLACEHOLDER_REASON = ('R57 relaxation placeholder: C is null with status research_draft in the carrier; '
                          'status held and this reason exist only in the writer004 validation copy.')
R57_PLACEHOLDER_METHOD = ('Each item or component whose C (values[2]) is null and whose status is research_draft gets, in the same '
                          'copy, status held; when its review_reasons is an empty list it also gets the one review reason '
                          + json.dumps(R57_PLACEHOLDER_REASON, ensure_ascii=False) + '. Its values, raw, evidence, null_reasons and '
                          'every other key are unchanged.')
O16_METHOD = ('No neutralization: writer004 validateCarrier and prepareMatrices never read metadata.source_adoption, so a non-null Q '
              'under unverified adoption passes writer004 unchanged; when a copy is made for another class, Q and the metadata are '
              'unchanged in it.')
PLACEHOLDER_SCOPE = 'Nothing else in the carrier changes: groups, nonitems, metadata, limitations and every other item are copied unchanged.'
XLSX_NAME = 'research-draft.xlsx'
INPUT_LIMIT = 20 * 1024 * 1024
MAX_SAFE = 9007199254740991
EXCEL_CELL_TEXT_LIMIT = 32767

# Archived writer files. writer004.mjs: original archive bytes, or the public copy in
# research/checkpoint045/writer whose only difference is the redacted Windows helper path
# on line 218 (verifyOriginalSource, not reached by validateCarrier/prepareMatrices).
WRITER_PINS = {
    'writer004.mjs': {'85a7f619b9cfedc0c3c851b34c1d8cee38cfe5ab88ed050fcf4bba566c18c0d7': 'archived original',
                      '70d7f66455bfc5a2a6574b01509cfb78576a21b75bd7d75500746faf2661efb7': 'public copy (helper path redacted)'},
    'validate_carrier_v4.mjs': {'984da083219fa3df69dfd34652115fe1ddd5cd0ed723321981916adc5a87e013': 'archived original'},
    'receipt_bytes.mjs': {'b2ff15fd5d44a8adfbd5370f8bf8d81c432b89f5a6ea4f81d71477e283d11d2c': 'archived original'},
}

HEADERS = ['盤體名稱', '盤體規格', '材料名稱', '規格', '單位', '數量', '單價', '複價', '型號', '廠牌',
           '訂購廠商', '工程編號', '訂購客戶', '使用客戶', '需要日期', '需要數量', '合約價']
LINK_HEADERS = ['組成識別', '組成表列', '主項識別', '主表列', '基準數量', '基準單位', '基準來源', '組成來源']
REVIEW_HEADERS = ['類型', '識別／欄位', '工作表／儲存格／重建視圖', '來源定位', '原文／資料（JSON）', '處理／審查原因', '狀態']
SHEET_MAIN, SHEET_REVIEW, SHEET_COMPONENTS, SHEET_LINKS = '未填研究草稿', '來源與審查', '組成參考', '組成連結'
SHEET_ORDER = [SHEET_MAIN, SHEET_REVIEW, SHEET_COMPONENTS, SHEET_LINKS]   # writer004 worksheets.add order
WIDTHS_17 = [18, 30, 38, 48, 9, 12, 12, 12, 20, 18, 22, 18, 24, 24, 18, 12, 14]
WIDTHS_LINKS = [24, 12, 24, 12, 12, 12, 65, 65]
WIDTHS_REVIEW = [18, 23, 38, 38, 88, 62, 18]
COLOR_TEXT, COLOR_HEADER_FILL, COLOR_HEADER_TEXT, COLOR_PRICE_FILL = '172033', '29445D', 'FFFFFF', 'F1F3F5'
FIXED_TIME = datetime.datetime(1980, 1, 1, 0, 0, 0)

# JavaScript \s (and String.prototype.trim) whitespace: WhiteSpace + LineTerminator.
JS_WS = '\t\n\x0b\x0c\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'
FORMULA_LIKE_RE = re.compile('^[' + re.escape(JS_WS) + ']*[=+@-]')       # writer004 formulaLike
ARRAY_INDEX_RE = re.compile(r'(?:0|[1-9][0-9]*)', re.ASCII)
OOXML_ESCAPE_RE = re.compile(r'_x[0-9A-Fa-f]{4}_')
XML_ILLEGAL_RE = re.compile('[\u0000-\u0008\u000b\u000c\u000e-\u001f\ud800-\udfff\ufffe\uffff]')

LIMITATIONS = [
    'NOT ADMITTED: research export route; requires an independent review before CPS may use it.',
    'Gate is writer004 validateCarrier only. writer004 authorizeSource (allowlist pin, original-file sha256 and the Windows '
    'source_verify.py helper receipt) is not run: the helper and the original source files are not available here.',
    'Cell values and types follow writer004 EXPECTED_SAVED_VALUES.json (the matrices writer004 hands to artifact-tool). '
    'Whether @oai/artifact-tool itself saved exactly those values and types (for example numeric-looking or date-looking '
    'text kept as text) is unverified: artifact-tool is not available here.',
    'Column widths are written as openpyxl/OOXML character-width units using writer004 numbers. artifact-tool columnWidth '
    'units are unverified (the installed baseline treats them as characters; Office.js uses points).',
    'writer004 autofitRows is not reproduced: data rows carry no explicit height, so the opening application sizes them. '
    'The header row height 36 is written.',
    'writer004 calls freezeRows(1) then freezeColumns(3); written as one frozen pane at D2 (rows 1 and columns A:C). '
    'Whether artifact-tool kept both freezes is unverified.',
    'Not produced: INSPECTION.ndjson, ERROR_SCAN.ndjson and the three artifact-tool PNG renders (artifact-tool inspect/render), '
    'source-carrier.json, INPUT_PINS.json, research-draft.json, BUILD_RESULT.json. visual_qa.py renders with LibreOffice instead.',
    'Extra refusals beyond writer004 (the portable writer refuses, writer004 might accept): non-UTF-8 carrier bytes; '
    'a written cell string containing a lone surrogate, U+FFFE/U+FFFF or a literal OOXML escape sequence _xHHHH_ '
    '(spreadsheet applications decode _xHHHH_; openpyxl writes it unescaped); any Python/node matrix difference.',
    'openpyxl number serialisation ("%.16g", lossy for 17-digit doubles) is replaced during save by JavaScript '
    'Number-to-String text; strings equal to Excel error literals (#N/A, #REF!, ...) are forced to string type.',
    'docProps created/modified and zip member times are fixed to 1980-01-01T00:00:00 so the bytes are reproducible; '
    'the actual run time is in WRITER_RECEIPT.json.',
]


RELAXATION_LIMITATION = ('Route v4.1 relaxations (candidate 046f; route v4.2 keeps them unchanged): this carrier uses M/N job-input selection_evidence (O13, R48; '
                         'writer004 accepts it for L only) and/or a null C with status research_draft (R52, R57; writer004 requires '
                         'held). It was gated by writer004 validate_carrier_v4 on the placeholder copy, in which each relaxation is '
                         'neutralized, and by the sha256-pinned route v4.2 Python port on the original. writer004 prepareMatrices on the copy equals '
                         'the Python matrices of the copy; the saved matrices differ from it only in the documented review cells '
                         '(M/N evidence columns C-E; the status column of neutralized items; the review-reason column of the 項目 row '
                         'and one added 待確認 row where the copy added the placeholder reason).')


class Refused(Exception):
    def __init__(self, code, stage, detail=None):
        super().__init__(code)
        self.code, self.stage, self.detail = code, stage, detail


def sha256(b):
    return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------ JavaScript JSON semantics
def js_len(s):
    """String.prototype.length (UTF-16 code units)."""
    return len(s.encode('utf-16-le', 'surrogatepass')) // 2


def formula_like(s):
    return isinstance(s, str) and FORMULA_LIKE_RE.match(s) is not None


def js_number(x):
    """ECMAScript Number::toString for a finite number (JSON.stringify gives 'null' otherwise)."""
    x = float(x)
    if not math.isfinite(x):
        return 'null'
    if x == 0:
        return '0'
    if x < 0:
        return '-' + js_number(-x)
    _, digits, exp = Decimal(repr(x)).as_tuple()     # repr: shortest round-trip digits
    digits = list(digits)
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exp += 1
    s = ''.join(map(str, digits))
    k = len(s)
    n = exp + k
    if k <= n <= 21:
        return s + '0' * (n - k)
    if 0 < n <= 21:
        return s[:n] + '.' + s[n:]
    if -6 < n <= 0:
        return '0.' + '0' * (-n) + s
    e = n - 1
    sign = '+' if e >= 0 else '-'
    return (s if k == 1 else s[0] + '.' + s[1:]) + 'e' + sign + str(abs(e))


_SHORT_ESC = {'"': '\\"', '\\': '\\\\', '\b': '\\b', '\f': '\\f', '\n': '\\n', '\r': '\\r', '\t': '\\t'}
_QUOTE_RE = re.compile('["\\\\\u0000-\u001f\ud800-\udfff]')


def js_quote(s):
    """JSON.stringify string quoting (well-formed JSON.stringify: lone surrogates escaped)."""
    def sub(m):
        ch = m.group(0)
        return _SHORT_ESC.get(ch) or '\\u%04x' % ord(ch)
    return '"' + _QUOTE_RE.sub(sub, s) + '"'


def js_keys(d):
    """OrdinaryOwnPropertyKeys order: array-index keys ascending, then insertion order."""
    idx = [k for k in d if ARRAY_INDEX_RE.fullmatch(k) and int(k) <= 4294967294]
    idx_set = set(idx)
    return sorted(idx, key=int) + [k for k in d if k not in idx_set]


def js_truthy(v):
    """ToBoolean for parsed-JSON values (missing key = undefined = None)."""
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)):
        return v == v and v != 0
    if isinstance(v, str):
        return v != ''
    return True


def js_entries(d):
    return [(k, d[k]) for k in js_keys(d)]


def js_stringify(v, indent=None, _level=0):
    """JSON.stringify(v) or JSON.stringify(v, null, indent) for parsed-JSON values."""
    if v is None:
        return 'null'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, (int, float)):
        return js_number(v)
    if isinstance(v, str):
        return js_quote(v)
    if isinstance(v, (list, tuple)):
        if not v:
            return '[]'
        if indent is None:
            return '[' + ','.join(js_stringify(x) for x in v) + ']'
        pad, inner = ' ' * (indent * _level), ' ' * (indent * (_level + 1))
        return '[\n' + ',\n'.join(inner + js_stringify(x, indent, _level + 1) for x in v) + '\n' + pad + ']'
    if isinstance(v, dict):
        keys = js_keys(v)
        if not keys:
            return '{}'
        if indent is None:
            return '{' + ','.join(js_quote(k) + ':' + js_stringify(v[k]) for k in keys) + '}'
        pad, inner = ' ' * (indent * _level), ' ' * (indent * (_level + 1))
        return '{\n' + ',\n'.join(inner + js_quote(k) + ': ' + js_stringify(v[k], indent, _level + 1) for k in keys) + '\n' + pad + '}'
    raise TypeError('unsupported value type: ' + type(v).__name__)


def js_parse(raw):
    """JSON.parse(raw.toString('utf8').replace(/^\\uFEFF/, '')) with JavaScript number semantics."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise Refused('UTF8_REQUIRED', 'parse', 'node would replace invalid bytes with U+FFFD; the portable writer refuses')
    if text.startswith('\ufeff'):
        text = text[1:]

    def parse_int(t):
        try:
            return float(int(t))
        except OverflowError:
            return math.copysign(math.inf, -1.0 if t.startswith('-') else 1.0)

    def bad_constant(name):
        raise ValueError('JSON.parse rejects ' + name)
    try:
        return json.loads(text, parse_int=parse_int, parse_float=float, parse_constant=bad_constant)
    except (ValueError, RecursionError) as e:
        raise Refused('INVALID_JSON', 'parse', str(e)[:200])


# ------------------------------------------------------------------ writer004 prepareMatrices
def _review_rows(c):
    src = c['source']
    xls = src.get('kind') == 'cached_xls'
    S = js_stringify
    rows = [['狀態', '整份研究稿', None, None, 'held', '來源語義及正式用途尚待獨立審查', 'held'],
            ['來源', '選定原始 XLS（BIFF8）' if xls else '選定原始 XLSX', None, None, S(src),
             '核對允許原始路徑、SHA256、OLE Workbook 與 BIFF8 記錄；未重算來源公式' if xls else '核對允許原始路徑、SHA256 與 ZIP 標頭；未重算來源公式', 'held']]
    for k, v in js_entries(c['metadata']):
        rows.append(['識別資料', S(k), None, None, S(v), '保留輸入識別與限制', 'held'])
    for i, v in enumerate(c['limitations']):
        rows.append(['全案限制', str(i + 1), None, None, S(v), '原載限制', 'held'])
    for g in c['groups']:
        rows.append(['群組', g['id'], S(g['location']), S(g['anchor']), S(g), '群組不推導實體箱數或分配', 'held'])
    n_items = len(c['items'])
    for i, r in enumerate(c['items'] + c['components']):
        detail = i < n_items
        loc, anc = S(r['location']), S(r['anchor'])
        rows.append(['項目', r['id'], loc, anc,
                     S({'group_id': r['group_id'], 'sheet': SHEET_MAIN if detail else SHEET_COMPONENTS,
                        'saved_row': i + 2 if detail else i - n_items + 2,
                        'composition': r.get('composition'), 'values': r['values']}),
                     S(r['review_reasons']), r['status']])
        for k, v in js_entries(r['raw']):
            rows.append(['原文', f"{r['id']}.{k}", loc, anc, S(v), 'JSON 字串保留原文與換行', r['status']])
        for k, v in js_entries(r['evidence']):
            rows.append(['欄位依據', f"{r['id']}.{k}", S(v['location']) if js_truthy(v.get('location')) else None,
                         S(v['anchor'] if v.get('anchor') is not None else '已核對工程選取'), S(v), S(v['transformation']), r['status']])
        for k, v in js_entries(r['null_reasons']):
            rows.append(['空白原因', f"{r['id']}.{k}", loc, anc, S(v), '空白不等於零或抽取成功', r['status']])
        for j, v in enumerate(r['review_reasons']):
            rows.append(['待確認', f"{r['id']}.{j + 1}", loc, anc, S(v), '保留受阻列', r['status']])
    for i, n in enumerate(c['nonitems']):
        rows.append([f"非材料：{n['kind']}", str(i + 1), S(n['location']), S(n['anchor']), S(n['text']), S(n['reason']), 'held'])
    return rows


def prepare_matrices(c):
    """writer004 prepareMatrices after validateCarrier (the gate runs validateCarrier itself)."""
    items, comps = c['items'], c['components']
    main = [list(HEADERS)] + [list(r['values']) for r in items]
    components = [list(HEADERS)] + [list(r['values']) for r in comps]
    item_index = {}
    for k, r in enumerate(items):
        item_index.setdefault(r['id'], k)
    links = [list(LINK_HEADERS)]
    for i, r in enumerate(comps):
        x = r['composition']
        links.append([r['id'], i + 2, x['parent_id'], item_index.get(x['parent_id'], -1) + 2, x['basis_quantity'], x['basis_unit'],
                      js_stringify(x['basis_location']), js_stringify(r['location'])])
    review = [list(REVIEW_HEADERS)] + _review_rows(c)
    for i, row in enumerate(review):
        for j, v in enumerate(row):
            if isinstance(v, str) and (js_len(v) > 32767 or formula_like(v)):
                raise Refused('REVIEW_CELL_UNSAFE_OR_TOO_LONG', 'prepare_matrices', f'{i + 1}:{j + 1}')
    return {'main': main, 'components': components, 'links': links, 'review': review}


def expected_saved_values(m):
    """writer004: saveJson(EXPECTED_SAVED_VALUES.json, {sheets:[...]}) = JSON.stringify(v,null,2)+'\\n'."""
    doc = {'sheets': [{'name': SHEET_MAIN, 'values': m['main']}, {'name': SHEET_REVIEW, 'values': m['review']},
                      {'name': SHEET_COMPONENTS, 'values': m['components']}, {'name': SHEET_LINKS, 'values': m['links']}]}
    return (js_stringify(doc, 2) + '\n').encode('utf-8', 'strict')


def sheet_matrices(m):
    return [(SHEET_MAIN, m['main']), (SHEET_REVIEW, m['review']), (SHEET_COMPONENTS, m['components']), (SHEET_LINKS, m['links'])]


def portable_writability(m):
    """Characters the openpyxl/XML route cannot carry unambiguously. Returns a list of problems."""
    problems = []
    for name, rows in sheet_matrices(m):
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                where = f'{name}!R{i + 1}C{j + 1}'
                if isinstance(v, str):
                    if XML_ILLEGAL_RE.search(v):
                        problems.append({'cell': where, 'code': 'XML_UNREPRESENTABLE_CHARACTER'})
                    if OOXML_ESCAPE_RE.search(v):
                        problems.append({'cell': where, 'code': 'LITERAL_OOXML_ESCAPE_SEQUENCE'})
                    if js_len(v) > EXCEL_CELL_TEXT_LIMIT:
                        problems.append({'cell': where, 'code': 'EXCEL_CELL_TEXT_LIMIT'})
                    if v.startswith('='):
                        problems.append({'cell': where, 'code': 'FORMULA_TEXT'})
                elif isinstance(v, bool) or (v is not None and not isinstance(v, (int, float))):
                    problems.append({'cell': where, 'code': 'UNSUPPORTED_VALUE_TYPE'})
                elif isinstance(v, (int, float)) and (not math.isfinite(v) or abs(v) > MAX_SAFE):
                    problems.append({'cell': where, 'code': 'UNSAFE_NUMBER'})
    return problems


# ------------------------------------------------------------------ xlsx assembly (openpyxl)
def _number_cell_value(v):
    f = float(v)
    return int(f) if f.is_integer() and abs(f) <= MAX_SAFE else f


def _fill_values(ws, rows):
    for i, row in enumerate(rows, start=1):
        for j, v in enumerate(row, start=1):
            if v is None:
                continue
            cell = ws.cell(row=i, column=j)
            if isinstance(v, str):
                cell.value = v
                if cell.data_type != 's':        # '#N/A', '#REF!', ... would become error cells
                    cell.data_type = 's'
                if cell._value != v:
                    raise Refused('OPENPYXL_CHANGED_TEXT', 'assemble', f'{ws.title}!R{i}C{j}')
            else:
                cell.value = _number_cell_value(v)
                if cell.data_type != 'n':
                    raise Refused('OPENPYXL_CHANGED_NUMBER', 'assemble', f'{ws.title}!R{i}C{j}')


def _format_sheet(ws, nrows, ncols, widths):
    """writer004 formatSheet, in openpyxl terms (autofitRows not expressible)."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    body_font = Font(name='Arial', size=11, color='FF' + COLOR_TEXT)
    body_align = Alignment(vertical='top', wrap_text=True)
    for r in range(1, nrows + 1):
        for col in range(1, ncols + 1):
            cell = ws.cell(row=r, column=col)
            cell.font = body_font
            cell.alignment = body_align
    head_fill = PatternFill(fill_type='solid', fgColor='FF' + COLOR_HEADER_FILL)
    head_font = Font(name='Arial', size=11, bold=True, color='FF' + COLOR_HEADER_TEXT)
    head_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    for col in range(1, ncols + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill, cell.font, cell.alignment = head_fill, head_font, head_align
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = ws.cell(row=2, column=min(ncols, 3) + 1).coordinate
    ws.row_dimensions[1].height = 36


def build_workbook(m, n_items):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, PatternFill
    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet(SHEET_MAIN)
    rs = wb.create_sheet(SHEET_REVIEW)
    ws.sheet_properties.tabColor = 'FF' + COLOR_HEADER_FILL
    cs = wb.create_sheet(SHEET_COMPONENTS)
    ls = wb.create_sheet(SHEET_LINKS)
    _fill_values(cs, m['components'])
    _fill_values(ls, m['links'])
    _format_sheet(cs, len(m['components']), 17, WIDTHS_17)
    _format_sheet(ls, len(m['links']), 8, WIDTHS_LINKS)
    _fill_values(ws, m['main'])
    _fill_values(rs, m['review'])
    _format_sheet(ws, len(m['main']), 17, WIDTHS_17)
    _format_sheet(rs, len(m['review']), 7, WIDTHS_REVIEW)
    right = Alignment(horizontal='right', vertical='top', wrap_text=True)
    for j in (5, 15, 16):
        for r in range(2, n_items + 2):
            cell = ws.cell(row=r, column=j + 1)
            cell.number_format = 'General'
            cell.alignment = right
    price_fill = PatternFill(fill_type='solid', fgColor='FF' + COLOR_PRICE_FILL)
    for j in (6, 7):
        for r in range(2, n_items + 2):
            ws.cell(row=r, column=j + 1).fill = price_fill
    wb.active = 0
    wb.calculation.fullCalcOnLoad = False          # no formulas; do not ask the application to recalculate
    wb.properties.creator = 'CPS writer_portable (openpyxl)'
    wb.properties.created = FIXED_TIME
    wb.properties.modified = FIXED_TIME
    return wb


def _xlsx_number_text(value, _orig=None):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return js_number(value)
    return _orig(value)


def save_workbook_bytes(wb):
    """Serialize without save_workbook's modified=now, with exact number text, then fix zip times."""
    import openpyxl.cell._writer as cell_writer
    from openpyxl.writer.excel import ExcelWriter
    orig = cell_writer.safe_string
    cell_writer.safe_string = lambda v: _xlsx_number_text(v, orig)
    try:
        buf = io.BytesIO()
        ExcelWriter(wb, zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, allowZip64=True)).save()
    finally:
        cell_writer.safe_string = orig
    out = io.BytesIO()
    with zipfile.ZipFile(buf) as src, zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            zi = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 0
            zi.external_attr = 0
            dst.writestr(zi, src.read(info.filename))
    return out.getvalue()


# ------------------------------------------------------------------ gate and cross-check
def run(cmd, timeout=180):
    p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def tool_version(cmd):
    try:
        code, out, err = run(cmd, 60)
        return (out or err).decode('utf-8', 'replace').strip().splitlines()[0] if (out or err) else None
    except Exception as e:            # noqa: BLE001 - version capture only
        return 'unavailable: ' + type(e).__name__


def check_writer_dir(writer_dir):
    pins = {}
    for name, allowed in WRITER_PINS.items():
        p = writer_dir / name
        if not p.is_file():
            raise Refused('WRITER_FILE_MISSING', 'gate', name)
        h = sha256(p.read_bytes())
        if h not in allowed:
            raise Refused('WRITER_FILE_NOT_PINNED', 'gate', {'file': name, 'sha256': h})
        pins[name] = {'sha256': h, 'identity': allowed[h]}
    stub = writer_dir.parent / 'node_modules' / '@oai' / 'artifact-tool' / 'index.mjs'
    pins['@oai/artifact-tool/index.mjs (resolved beside the writer, if present)'] = sha256(stub.read_bytes()) if stub.is_file() else None
    return pins


def node_gate(node, writer_dir, carrier_path, carrier_sha, stage='gate:validate_carrier_v4'):
    code, out, err = run([node, str(writer_dir / 'validate_carrier_v4.mjs'), '--carrier', str(carrier_path)])
    if code != 0:
        try:
            e = json.loads(err.decode('utf-8'))
        except ValueError:
            e = {'code': 'NODE_GATE_ERROR', 'message': err.decode('utf-8', 'replace')[-500:]}
        raise Refused(e.get('code', 'ERROR'), stage, e.get('message'))
    res = json.loads(out.decode('utf-8'))
    if res.get('status') != 'WRITER_STRUCTURAL_VALIDATION_ONLY' or res.get('carrier_sha256') != carrier_sha:
        raise Refused('GATE_RESULT_UNEXPECTED', stage, res)
    return res


def node_matrices(node, writer_dir, carrier_path, stage='cross_check:writer004.prepareMatrices'):
    code, out, err = run([node, str(NODE_MATRICES), '--writer', str(writer_dir / 'writer004.mjs'), '--carrier', str(carrier_path)])
    if code != 0:
        try:
            e = json.loads(err.decode('utf-8'))
        except ValueError:
            e = {'code': 'NODE_MATRICES_ERROR', 'message': err.decode('utf-8', 'replace')[-500:]}
        raise Refused(e.get('code', 'ERROR'), stage, e.get('message'))
    return out


# ------------------------------------------------------------------ mode v2: route v4.1 relaxations
def r57_item(r):
    """C null with status research_draft (relaxation r57_null_c_research_draft)."""
    v = r.get('values') if isinstance(r, dict) else None
    return isinstance(v, list) and len(v) > 2 and v[2] is None and r.get('status') == 'research_draft'


def relaxation_scan(raw):
    """The relaxation classes a carrier uses, as lists of (row index in items+components, id, ...).
    Decoded like node (invalid UTF-8 replaced) so detection does not depend on the later UTF-8 refusal;
    an unparsable or unexpectedly shaped carrier uses none and takes the v1 route (the gates report the real defect)."""
    scan = {'o13': [], 'r57': [], 'o16': [], 'source_adoption': None}
    try:
        text = raw.decode('utf-8', 'replace')
        c = json.loads(text[1:] if text.startswith('﻿') else text)     # node: .replace(/^﻿/, '')
        rows = list(c['items']) + list(c['components'])
        md = c.get('metadata')
    except Exception:          # noqa: BLE001 - detection only
        return scan
    adoption = md.get('source_adoption') if isinstance(md, dict) else None
    scan['source_adoption'] = adoption
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        ev = r.get('evidence')
        for k in O13_COLS:
            e = ev.get(k) if isinstance(ev, dict) else None
            if isinstance(e, dict) and 'selection_evidence' in e:
                scan['o13'].append((i, r.get('id'), k))
        if r57_item(r):
            scan['r57'].append((i, r.get('id'), r.get('review_reasons') == []))
        v = r.get('values')
        if isinstance(v, list) and len(v) == 17 and v[16] is not None and adoption != 'verified':
            scan['o16'].append((i, r.get('id')))
    return scan


def placeholder_copy(c):
    """The documented placeholder copy (O13_PLACEHOLDER_METHOD, R57_PLACEHOLDER_METHOD, O16_METHOD, PLACEHOLDER_SCOPE).
    Input and output are json.loads objects."""
    c = copy.deepcopy(c)
    for r in list(c['items']) + list(c['components']):
        if not isinstance(r, dict):
            continue
        ev = r.get('evidence')
        for k in O13_COLS:
            e = ev.get(k) if isinstance(ev, dict) else None
            if isinstance(e, dict) and 'selection_evidence' in e:
                new = {x: y for x, y in e.items() if x != 'selection_evidence'}
                new.update(location=copy.deepcopy(r.get('location')), anchor=r.get('anchor'), raw_text=e['selection_evidence'])
                ev[k] = new
        if r57_item(r):
            r['status'] = 'held'
            if r.get('review_reasons') == []:
                r['review_reasons'] = [R57_PLACEHOLDER_REASON]
    return c


def o13_placeholder_copy(c):
    """Name kept from writer v2.0; the copy now also neutralizes R57 items (placeholder_copy)."""
    return placeholder_copy(c)


def load_route_port(path):
    """Load the route port from the exact bytes whose sha256 equals ROUTE_V4_SHA256 (read once, hashed, then
    executed from those bytes, so no other file content can run); then check VERSION and PORT_RELAXATIONS."""
    if not path.is_file():
        raise Refused('ROUTE_V4_TOOL_MISSING', 'gate:route_v4_port', str(path))
    raw = path.read_bytes()
    h = sha256(raw)
    if h != ROUTE_V4_SHA256:
        raise Refused('ROUTE_V4_TOOL_NOT_PINNED', 'gate:route_v4_port', {'sha256': h, 'pinned': ROUTE_V4_SHA256})
    mod = types.ModuleType('cps046f_route_v4_port')
    mod.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), mod.__dict__)      # noqa: S102 - pinned bytes only
    if getattr(mod, 'VERSION', None) != ROUTE_V4_VERSION or not hasattr(mod, 'validate_carrier_port'):
        raise Refused('ROUTE_V4_TOOL_VERSION', 'gate:route_v4_port', getattr(mod, 'VERSION', None))
    if set(getattr(mod, 'PORT_RELAXATIONS', {})) != set(RELAXATION_CLASSES):
        raise Refused('ROUTE_V4_TOOL_RELAXATIONS', 'gate:route_v4_port', sorted(getattr(mod, 'PORT_RELAXATIONS', {})))
    return mod, h


def _review_spans(c):
    """0-based row ranges (row 0 = header) of each item/component block in the review matrix (_review_rows order),
    and the row where the nonitem rows start."""
    i = 1 + 2 + len(c['metadata']) + len(c['limitations']) + len(c['groups'])
    spans = []
    for r in list(c['items']) + list(c['components']):
        n = 1 + len(r['raw']) + len(r['evidence']) + len(r['null_reasons']) + len(r['review_reasons'])
        spans.append((i, i + n))
        i += n
    return spans, i


def relaxation_matrix_difference(m, m_copy, c, c_copy, scan):
    """The saved matrices (original carrier) may differ from the placeholder-copy matrices only in the documented
    review cells. Rows are aligned positionally from the writer004 review-row layout of both carriers, so every row of
    both matrices is accounted for. Returns the differing cells (saved-matrix coordinates) and the added copy rows."""
    D, stage = 'RELAXATION_DIFF_OUTSIDE_DOCUMENTED_CELLS', 'cross_check:relaxations'
    for name in ('main', 'components', 'links'):
        if js_stringify(m[name]) != js_stringify(m_copy[name]):
            raise Refused(D, stage, name)
    a, b = m['review'], m_copy['review']
    sa, na = _review_spans(c)
    sb, nb = _review_spans(c_copy)
    if len(sa) != len(sb) or len(a) != na + len(c['nonitems']) or len(b) != nb + len(c_copy['nonitems']):
        raise Refused(D, stage, 'review row layout')
    rows = list(c['items']) + list(c['components'])
    rows_copy = list(c_copy['items']) + list(c_copy['components'])
    o13 = {(i, k) for i, _, k in scan['o13']}
    r57 = {i: added for i, _, added in scan['r57']}
    first_a, first_b = (sa[0][0] if sa else na), (sb[0][0] if sb else nb)
    if first_a != first_b:
        raise Refused(D, stage, 'review prefix rows')
    pairs = [(t, t, frozenset()) for t in range(first_a)]
    added_rows = []
    for k, ((a0, a1), (b0, b1)) in enumerate(zip(sa, sb)):
        added = r57.get(k, False)
        if b1 - b0 != (a1 - a0) + (1 if added else 0):
            raise Refused(D, stage, f'review rows of item {k + 1}')
        ev_keys = js_keys(rows[k]['evidence'])
        ev0 = 1 + len(rows[k]['raw'])
        for t in range(a1 - a0):
            allowed = set()
            if k in r57:
                allowed.add(6)
                if t == 0 and added:
                    allowed.add(5)
            if ev0 <= t < ev0 + len(ev_keys) and (k, ev_keys[t - ev0]) in o13:
                allowed |= {2, 3, 4}
            pairs.append((a0 + t, b0 + t, frozenset(allowed), k, t))
        if added:
            rc = rows_copy[k]
            want = ['待確認', f"{rc['id']}.1", js_stringify(rc['location']), js_stringify(rc['anchor']),
                    js_stringify(R57_PLACEHOLDER_REASON), '保留受阻列', 'held']
            if js_stringify(b[b1 - 1]) != js_stringify(want):
                raise Refused('RELAXATION_DIFF_FORM', stage, f'{SHEET_REVIEW}!R{b1} (copy placeholder row)')
            added_rows.append(f'{SHEET_REVIEW}!R{b1} (copy)')
    pairs += [(na + t, nb + t, frozenset()) for t in range(len(c['nonitems']))]
    cells = []
    for pr in pairs:
        ia, ib, allowed = pr[0], pr[1], pr[2]
        ra, rb = a[ia], b[ib]
        if len(ra) != len(rb):
            raise Refused(D, stage, f'review row {ia + 1} width')
        for j, (x, y) in enumerate(zip(ra, rb)):
            if js_stringify(x) == js_stringify(y):
                continue
            if j not in allowed:
                raise Refused(D, stage, f'{SHEET_REVIEW}!R{ia + 1}C{j + 1}')
            cells.append(f'{SHEET_REVIEW}!R{ia + 1}C{j + 1}')
        if len(pr) == 5:                     # item rows: check the documented forms of the relaxed cells
            k, t = pr[3], pr[4]
            if k in r57 and (ra[6] != 'research_draft' or rb[6] != 'held'):
                raise Refused('RELAXATION_DIFF_FORM', stage, f'{SHEET_REVIEW}!R{ia + 1}C7')
            if k in r57 and t == 0 and r57[k] and (ra[5] != '[]' or rb[5] != js_stringify([R57_PLACEHOLDER_REASON])):
                raise Refused('RELAXATION_DIFF_FORM', stage, f'{SHEET_REVIEW}!R{ia + 1}C6')
            if {2, 3, 4} <= allowed and (ra[2] is not None or ra[3] != js_stringify('已核對工程選取')):
                raise Refused('RELAXATION_DIFF_FORM', stage, f'{SHEET_REVIEW}!R{ia + 1}')
    return {'sheet': SHEET_REVIEW, 'cells': cells, 'rows_added_in_copy': added_rows}


def _first_difference(a, b):
    n = min(len(a), len(b))
    k = next((i for i in range(n) if a[i] != b[i]), n)
    return {'byte_offset': k, 'python': a[max(0, k - 60):k + 60].decode('utf-8', 'replace'),
            'writer004': b[max(0, k - 60):k + 60].decode('utf-8', 'replace'), 'python_len': len(a), 'writer004_len': len(b)}


# ------------------------------------------------------------------ main build
def build(carrier_path, out_dir, writer_dir, node='node', mode='v1', route_tool=ROUTE_V4_TOOL):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if mode not in ('v1', 'v2'):
        raise Refused('MODE_UNKNOWN', 'usage', mode)
    for p, k in ((carrier_path, 'carrier'), (out_dir, 'out'), (writer_dir, 'writer_dir')):
        if not p.is_absolute():
            raise Refused('ABSOLUTE_CLI_PATH_REQUIRED', 'usage', k)
    if out_dir.exists() or out_dir.is_symlink():
        raise Refused('OUTPUT_EXISTS', 'usage', str(out_dir))
    if not out_dir.parent.is_dir():
        raise Refused('OUTPUT_PARENT_MISSING', 'usage', str(out_dir.parent))
    raw = carrier_path.read_bytes()
    if len(raw) > INPUT_LIMIT:
        raise Refused('INPUT_SIZE_LIMIT', 'usage')
    carrier_sha = sha256(raw)
    pins = check_writer_dir(writer_dir)
    scan = relaxation_scan(raw) if mode == 'v2' else None
    needs_copy = bool(scan and (scan['o13'] or scan['r57']))
    relax = {'applied': False, 'scanned': scan is not None}
    if scan is not None:
        relax['classes'] = {
            'o13_m_n_selection_evidence': {'fields': [f'{iid}.{k}' for _, iid, k in scan['o13']], 'neutralization': O13_PLACEHOLDER_METHOD},
            'r57_null_c_research_draft': {'items': [iid for _, iid, _ in scan['r57']],
                                          'placeholder_reason_added_to': [iid for _, iid, added in scan['r57'] if added],
                                          'neutralization': R57_PLACEHOLDER_METHOD},
            'o16_q_unverified_adoption': {'items': [iid for _, iid in scan['o16']], 'source_adoption': scan['source_adoption'],
                                          'neutralization': O16_METHOD}}
    if not needs_copy:                   # v1 route (also v2 without O13/R57; an O16 Q needs no neutralization)
        gate = node_gate(node, writer_dir, carrier_path, carrier_sha)
        carrier = js_parse(raw)
        m = prepare_matrices(carrier)
        expected = expected_saved_values(m)
        node_expected = node_matrices(node, writer_dir, carrier_path)
        if expected != node_expected:
            raise Refused('CROSS_CHECK_MISMATCH', 'cross_check', _first_difference(expected, node_expected))
        cross = {'tool': 'writer004 prepareMatrices via writer004_matrices.mjs (node)', 'result': 'BYTE_IDENTICAL',
                 'sha256': sha256(node_expected)}
        gate_rec = {'tool': 'writer004 validate_carrier_v4.mjs (node)', 'result': gate}
    else:                                # v2 with the route v4.1 relaxations
        carrier = js_parse(raw)
        text = raw.decode('utf-8')
        plain = json.loads(text[1:] if text.startswith('﻿') else text)
        copy_bytes = (json.dumps(placeholder_copy(plain), ensure_ascii=True, indent=1) + '\n').encode('ascii')
        with tempfile.TemporaryDirectory(prefix='cps_relax_') as td:
            cp = Path(td) / 'placeholder_carrier.json'
            cp.write_bytes(copy_bytes)
            gate = node_gate(node, writer_dir, cp, sha256(copy_bytes), 'gate:validate_carrier_v4:placeholder_copy')
            port, port_sha = load_route_port(route_tool)
            try:
                port.validate_carrier_port(plain)
            except port.WriterReject as e:
                raise Refused(e.code, 'gate:route_v4_port', e.where)
            m = prepare_matrices(carrier)
            copy_carrier = js_parse(copy_bytes)
            m_copy = prepare_matrices(copy_carrier)
            expected_copy = expected_saved_values(m_copy)
            node_copy = node_matrices(node, writer_dir, cp, 'cross_check:writer004.prepareMatrices:placeholder_copy')
        if expected_copy != node_copy:
            raise Refused('CROSS_CHECK_MISMATCH', 'cross_check:placeholder_copy', _first_difference(expected_copy, node_copy))
        diff = relaxation_matrix_difference(m, m_copy, carrier, copy_carrier, scan)
        expected = expected_saved_values(m)
        relax.update(applied=True, placeholder_scope=PLACEHOLDER_SCOPE, placeholder_carrier_sha256=sha256(copy_bytes),
                     route_v4_port={'path': str(route_tool), 'sha256': port_sha, 'sha256_pinned': port_sha == ROUTE_V4_SHA256,
                                    'version': ROUTE_V4_VERSION, 'result': 'PASS'},
                     writer004_cross_check_on_placeholder_copy={'result': 'BYTE_IDENTICAL', 'sha256': sha256(node_copy)},
                     saved_matrices_differ_from_placeholder_copy_only_in=diff)
        cross = {'tool': 'writer004 prepareMatrices via writer004_matrices.mjs (node) on the placeholder copy',
                 'result': 'BYTE_IDENTICAL_ON_PLACEHOLDER_COPY', 'sha256': sha256(node_copy),
                 'saved_values_differ_only_in': len(diff['cells']), 'rows_added_in_copy': len(diff['rows_added_in_copy'])}
        gate_rec = {'tool': 'writer004 validate_carrier_v4.mjs (node) on the placeholder copy, plus the sha256-pinned route v4.2 Python port '
                            'on the original carrier', 'result': gate}
    problems = portable_writability(m)
    if problems:
        raise Refused('PORTABLE_UNREPRESENTABLE', 'writability', {'count': len(problems), 'first': problems[:20]})
    xlsx = save_workbook_bytes(build_workbook(m, len(carrier['items'])))

    out_dir.mkdir(parents=False, exist_ok=False)
    try:
        with open(out_dir / XLSX_NAME, 'xb') as f:
            f.write(xlsx)
        with open(out_dir / 'EXPECTED_SAVED_VALUES.json', 'xb') as f:
            f.write(expected)
        import openpyxl
        try:
            import lxml.etree as letree
            lxml_version = '.'.join(map(str, letree.LXML_VERSION))
        except ImportError:
            lxml_version = None
        receipt = {
            'schema': 'cps.export.writer-receipt.v1', 'status': 'PORTABLE_ASSEMBLED_NOT_ADMITTED', 'writer': VERSION,
            'mode': mode, 'relaxations': relax,
            'admitted': False, 'required_review': 'Independent review of the portable writer before any CPS use.',
            'input_carrier': {'path': str(carrier_path), 'sha256': carrier_sha, 'bytes': len(raw)},
            'output_xlsx': {'file': XLSX_NAME, 'sha256': sha256(xlsx), 'bytes': len(xlsx)},
            'expected_saved_values': {'file': 'EXPECTED_SAVED_VALUES.json', 'sha256': sha256(expected),
                                      'identical_to_writer004_prepareMatrices_output': not relax['applied'],
                                      **({'identical_to_writer004_prepareMatrices_on_placeholder_copy_except_documented_cells': True}
                                         if relax['applied'] else {})},
            'matrices_sha256': {name: sha256(js_stringify(rows).encode('utf-8')) for name, rows in sheet_matrices(m)},
            'matrices_sha256_definition': 'sha256 of UTF-8 JSON.stringify(values) (compact, JavaScript semantics) per sheet',
            'sheets': [{'name': name, 'rows': len(rows), 'columns': len(rows[0]),
                        'nonempty_cells': sum(v is not None for row in rows for v in row)} for name, rows in sheet_matrices(m)],
            'gate': gate_rec,
            'cross_check': cross,
            'writer_files': pins,
            'tool_versions': {'python': platform.python_version(), 'openpyxl': openpyxl.__version__, 'lxml': lxml_version,
                              'zlib': zlib.ZLIB_RUNTIME_VERSION, 'node': tool_version([node, '--version']),
                              'writer_portable.py_sha256': sha256(Path(__file__).read_bytes()),
                              'writer004_matrices.mjs_sha256': sha256(NODE_MATRICES.read_bytes())},
            'formulas_written': False, 'arithmetic': False, 'semantic_source_validation': False, 'native_excel_validation': False,
            'limitations': LIMITATIONS + ([RELAXATION_LIMITATION] if relax['applied'] else []), 'started': started,
            'ended': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        with open(out_dir / 'WRITER_RECEIPT.json', 'x', encoding='utf-8') as f:
            f.write(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    except Exception as e:
        with open(out_dir / 'WRITER_FAILURE.json', 'x', encoding='utf-8') as f:
            f.write(json.dumps({'status': 'FAILED_PARTIAL_OUTPUT_PRESERVED', 'error': repr(e)[:2000]}, ensure_ascii=False, indent=2) + '\n')
        raise
    return {'status': receipt['status'], 'mode': mode, 'relaxations_applied': relax['applied'], 'out': str(out_dir),
            'xlsx_sha256': receipt['output_xlsx']['sha256'],
            'expected_sha256': receipt['expected_saved_values']['sha256'], 'sheets': receipt['sheets']}


def main(argv=None):
    ap = argparse.ArgumentParser(description='CPS portable writer (NOT ADMITTED)')
    ap.add_argument('--carrier', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--writer-dir', required=True, help='directory holding the archived writer004.mjs and validate_carrier_v4.mjs')
    ap.add_argument('--node', default='node')
    ap.add_argument('--mode', default='v1', choices=('v1', 'v2'),
                    help='v2: candidate 046f carriers (route v4.2, with the v4.1 relaxations: M/N selection evidence, C-null research_draft); '
                         'v1: unchanged writer004 gate')
    a = ap.parse_args(argv)
    try:
        res = build(Path(a.carrier), Path(a.out), Path(a.writer_dir), a.node, a.mode)
    except Refused as e:
        sys.stderr.write(json.dumps({'status': 'REFUSED', 'code': e.code, 'stage': e.stage, 'detail': e.detail}, ensure_ascii=True) + '\n')
        return 1
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
