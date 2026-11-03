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

Usage
  python3 -I -B writer_portable.py --carrier /abs/carrier.json --out /abs/new-dir \
      --writer-dir /abs/dir-with-writer004.mjs [--node node]
Outputs in --out (created; must not exist): research-draft.xlsx, EXPECTED_SAVED_VALUES.json,
WRITER_RECEIPT.json. A refusal creates nothing and prints a JSON refusal on stderr (exit 1).
"""
import argparse, datetime, hashlib, io, json, math, os, platform, re, subprocess, sys, zipfile, zlib
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True

VERSION = 'cps-export-writer-portable.v1'
HERE = Path(__file__).resolve().parent
NODE_MATRICES = HERE / 'writer004_matrices.mjs'
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
JS_WS = '\t\n\x0b\x0c\r                  　﻿'
FORMULA_LIKE_RE = re.compile('^[' + re.escape(JS_WS) + ']*[=+@-]')       # writer004 formulaLike
ARRAY_INDEX_RE = re.compile(r'(?:0|[1-9][0-9]*)', re.ASCII)
OOXML_ESCAPE_RE = re.compile(r'_x[0-9A-Fa-f]{4}_')
XML_ILLEGAL_RE = re.compile('[\u0000-\u0008\u000b\u000c\u000e-\u001f\ud800-\udfff￾￿]')

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
    if text.startswith('﻿'):
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


def node_gate(node, writer_dir, carrier_path, carrier_sha):
    code, out, err = run([node, str(writer_dir / 'validate_carrier_v4.mjs'), '--carrier', str(carrier_path)])
    if code != 0:
        try:
            e = json.loads(err.decode('utf-8'))
        except ValueError:
            e = {'code': 'NODE_GATE_ERROR', 'message': err.decode('utf-8', 'replace')[-500:]}
        raise Refused(e.get('code', 'ERROR'), 'gate:validate_carrier_v4', e.get('message'))
    res = json.loads(out.decode('utf-8'))
    if res.get('status') != 'WRITER_STRUCTURAL_VALIDATION_ONLY' or res.get('carrier_sha256') != carrier_sha:
        raise Refused('GATE_RESULT_UNEXPECTED', 'gate:validate_carrier_v4', res)
    return res


def node_matrices(node, writer_dir, carrier_path):
    code, out, err = run([node, str(NODE_MATRICES), '--writer', str(writer_dir / 'writer004.mjs'), '--carrier', str(carrier_path)])
    if code != 0:
        try:
            e = json.loads(err.decode('utf-8'))
        except ValueError:
            e = {'code': 'NODE_MATRICES_ERROR', 'message': err.decode('utf-8', 'replace')[-500:]}
        raise Refused(e.get('code', 'ERROR'), 'cross_check:writer004.prepareMatrices', e.get('message'))
    return out


def _first_difference(a, b):
    n = min(len(a), len(b))
    k = next((i for i in range(n) if a[i] != b[i]), n)
    return {'byte_offset': k, 'python': a[max(0, k - 60):k + 60].decode('utf-8', 'replace'),
            'writer004': b[max(0, k - 60):k + 60].decode('utf-8', 'replace'), 'python_len': len(a), 'writer004_len': len(b)}


# ------------------------------------------------------------------ main build
def build(carrier_path, out_dir, writer_dir, node='node'):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
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
    gate = node_gate(node, writer_dir, carrier_path, carrier_sha)
    carrier = js_parse(raw)
    m = prepare_matrices(carrier)
    expected = expected_saved_values(m)
    node_expected = node_matrices(node, writer_dir, carrier_path)
    if expected != node_expected:
        raise Refused('CROSS_CHECK_MISMATCH', 'cross_check', _first_difference(expected, node_expected))
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
            'admitted': False, 'required_review': 'Independent review of the portable writer before any CPS use.',
            'input_carrier': {'path': str(carrier_path), 'sha256': carrier_sha, 'bytes': len(raw)},
            'output_xlsx': {'file': XLSX_NAME, 'sha256': sha256(xlsx), 'bytes': len(xlsx)},
            'expected_saved_values': {'file': 'EXPECTED_SAVED_VALUES.json', 'sha256': sha256(expected),
                                      'identical_to_writer004_prepareMatrices_output': True},
            'matrices_sha256': {name: sha256(js_stringify(rows).encode('utf-8')) for name, rows in sheet_matrices(m)},
            'matrices_sha256_definition': 'sha256 of UTF-8 JSON.stringify(values) (compact, JavaScript semantics) per sheet',
            'sheets': [{'name': name, 'rows': len(rows), 'columns': len(rows[0]),
                        'nonempty_cells': sum(v is not None for row in rows for v in row)} for name, rows in sheet_matrices(m)],
            'gate': {'tool': 'writer004 validate_carrier_v4.mjs (node)', 'result': gate},
            'cross_check': {'tool': 'writer004 prepareMatrices via writer004_matrices.mjs (node)', 'result': 'BYTE_IDENTICAL',
                            'sha256': sha256(node_expected)},
            'writer_files': pins,
            'tool_versions': {'python': platform.python_version(), 'openpyxl': openpyxl.__version__, 'lxml': lxml_version,
                              'zlib': zlib.ZLIB_RUNTIME_VERSION, 'node': tool_version([node, '--version']),
                              'writer_portable.py_sha256': sha256(Path(__file__).read_bytes()),
                              'writer004_matrices.mjs_sha256': sha256(NODE_MATRICES.read_bytes())},
            'formulas_written': False, 'arithmetic': False, 'semantic_source_validation': False, 'native_excel_validation': False,
            'limitations': LIMITATIONS, 'started': started,
            'ended': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        with open(out_dir / 'WRITER_RECEIPT.json', 'x', encoding='utf-8') as f:
            f.write(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    except Exception as e:
        with open(out_dir / 'WRITER_FAILURE.json', 'x', encoding='utf-8') as f:
            f.write(json.dumps({'status': 'FAILED_PARTIAL_OUTPUT_PRESERVED', 'error': repr(e)[:2000]}, ensure_ascii=False, indent=2) + '\n')
        raise
    return {'status': receipt['status'], 'out': str(out_dir), 'xlsx_sha256': receipt['output_xlsx']['sha256'],
            'expected_sha256': receipt['expected_saved_values']['sha256'], 'sheets': receipt['sheets']}


def main(argv=None):
    ap = argparse.ArgumentParser(description='CPS portable writer (NOT ADMITTED)')
    ap.add_argument('--carrier', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--writer-dir', required=True, help='directory holding the archived writer004.mjs and validate_carrier_v4.mjs')
    ap.add_argument('--node', default='node')
    a = ap.parse_args(argv)
    try:
        res = build(Path(a.carrier), Path(a.out), Path(a.writer_dir), a.node)
    except Refused as e:
        sys.stderr.write(json.dumps({'status': 'REFUSED', 'code': e.code, 'stage': e.stage, 'detail': e.detail}, ensure_ascii=True) + '\n')
        return 1
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
