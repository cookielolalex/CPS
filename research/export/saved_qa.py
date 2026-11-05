r"""CPS saved 17-column workbook QA (read-only; part of the NOT ADMITTED portable export route).

Reopens the saved workbook and compares every cell of every sheet with the writer's
EXPECTED_SAVED_VALUES.json (value and type, exact). Three independent readers:
openpyxl data_only=False, openpyxl data_only=True, and a raw OOXML (zip + XML) reader.
Also checks: sheet names/order, the 17-column header row of the main sheet, no formulas,
no unexpected populated cells, Excel limits, external relationships, and (unless
--no-formatting) the writer004 formatting the portable writer claims to reproduce.

Structure (v2, review S2; always checked): the zip holds exactly the 12 parts the writer produces; worksheet
children are only sheetPr, dimension, sheetViews, sheetFormatPr, cols, sheetData, pageMargins (in that order),
with the writer's attributes only (no zoom or other sheet-view attribute, no row/column/cell attribute the
writer does not write, inline strings as one plain <t>, leading/trailing whitespace kept with xml:space);
every sheet has state="visible"; no hidden or zeroHeight attribute with a true value anywhere; workbook
children and window visibility; cell-format children. Unknown cell types (t="d", ...) are findings, never a
crash. WRITER_RECEIPT.json must exist and its hashes must match.

Cell values and fonts (v3, second review F1(b); always checked): each <c> holds at most one value child, <v> for
t="n" and <is> for t="inlineStr", and an inlineStr cell has no <v>; <v> and <t> carry text only (no child element);
number text is ASCII and matches -?(0|[1-9][0-9]*)(\.[0-9]+)?(e[+-][0-9]+)? (JavaScript Number::toString of a
finite number, the writer's text); no duplicate row number or cell reference in a worksheet, every cell reference
in its own row, rows and cells in ascending order; fonts hold only name, color, sz and b (font 0, openpyxl's
default font, also family and scheme), each at most once. The formatting check also requires no italic,
strike, underline or vertAlign on any checked cell.

Provenance of EXPECTED (v3, second review F1(a)/F2; with --carrier and --writer-dir): the carrier sha256 must
equal the receipt's. Whatever the receipt's mode says, writer_portable.py --mode v2 reruns into a temporary
directory and EXPECTED_SAVED_VALUES.json and the xlsx must be byte-identical (builds are reproducible, and v2
gives the v1 bytes for a carrier without O13/R57). When the receipt says mode v1, writer004_matrices.mjs also
reruns writer004 prepareMatrices on the carrier (pinned writer files, pinned @oai/artifact-tool stub, the same
allowlisted node environment as the writer) and its text must be byte-identical to EXPECTED_SAVED_VALUES.json.
Without these options provenance is not checked (reported as such).
Self-contained: it does not import the writer (the provenance rerun runs it as a separate process).

Usage
  python3 -I -B saved_qa.py --output-dir /abs/writer-output [--report /abs/SAVED_QA.json] [--no-formatting]
      [--carrier /abs/carrier.json --writer-dir /abs/writer-dir [--node node]]
Default report: <output-dir>/SAVED_QA.json (created; must not exist). Exit 0 only on PASS.
"""
import argparse, hashlib, json, math, os, re, subprocess, sys, tempfile, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.dont_write_bytecode = True

VERSION = 'cps-export-saved-qa.v3'
HERE = Path(__file__).resolve().parent
WRITER = HERE / 'writer_portable.py'
NODE_MATRICES = HERE / 'writer004_matrices.mjs'
XLSX_NAME = 'research-draft.xlsx'
# The 12 zip parts the portable writer produces (openpyxl 3.1.5, inline strings).
EXPECTED_PARTS = ('[Content_Types].xml', '_rels/.rels', 'docProps/app.xml', 'docProps/core.xml', 'xl/workbook.xml',
                  'xl/_rels/workbook.xml.rels', 'xl/styles.xml', 'xl/theme/theme1.xml', 'xl/worksheets/sheet1.xml',
                  'xl/worksheets/sheet2.xml', 'xl/worksheets/sheet3.xml', 'xl/worksheets/sheet4.xml')
WORKSHEET_CHILDREN = ('sheetPr', 'dimension', 'sheetViews', 'sheetFormatPr', 'cols', 'sheetData', 'pageMargins')
WORKBOOK_CHILDREN = ('fileVersion', 'workbookPr', 'workbookProtection', 'bookViews', 'sheets', 'definedNames', 'calcPr')
SHEET_VIEW_ATTRS = ('tabSelected', 'showGridLines', 'workbookViewId')
SHEET_FORMAT_ATTRS = {'baseColWidth': '8', 'defaultRowHeight': '15'}
CELL_TYPES = ('n', 's', 'inlineStr', 'b', 'e', 'str')
FALSE_VALUES = ('0', 'false')
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
# v3 (second review F1(b)): the number text the writer writes is JavaScript Number::toString of a finite number
# (writer_portable js_number: '1e-7', '5e-324', '0.30000000000000004', '-0' written as '0'). ASCII only; fullmatch.
NUMBER_TEXT_RE = re.compile(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?(e[+-][0-9]+)?')
CELL_REF_RE = re.compile(r'([A-Z]{1,3})([1-9][0-9]*)')
ROW_NUMBER_RE = re.compile(r'[1-9][0-9]*')
# Font children the writer's styles.xml holds: openpyxl's default font 0 (Calibri: name, family, color, sz, scheme)
# and the writer's body and header fonts (name, color, sz; b on the header). Each at most once.
FONT0_CHILDREN = ('name', 'family', 'color', 'sz', 'scheme')
FONT_CHILDREN = ('name', 'color', 'sz', 'b')
# Node environment (v3, second review N-c); the same allowlist as writer_portable.py (the tests check equality):
# only these variables reach node (no OPENSSL_CONF, LD_PRELOAD, LD_LIBRARY_PATH, NODE_* or any other variable).
NODE_ENV_KEEP = ('PATH', 'HOME', 'TMPDIR', 'LANG')
NODE_ENV_KEEP_PREFIXES = ('LC_',)
# Node environment for mode v1 provenance; the same pins as writer_portable.py (the tests check equality).
WRITER_PINS = {
    'writer004.mjs': ('85a7f619b9cfedc0c3c851b34c1d8cee38cfe5ab88ed050fcf4bba566c18c0d7', '70d7f66455bfc5a2a6574b01509cfb78576a21b75bd7d75500746faf2661efb7'),
    'validate_carrier_v4.mjs': ('984da083219fa3df69dfd34652115fe1ddd5cd0ed723321981916adc5a87e013',),
    'receipt_bytes.mjs': ('b2ff15fd5d44a8adfbd5370f8bf8d81c432b89f5a6ea4f81d71477e283d11d2c',),
}
ARTIFACT_TOOL_SPECIFIER = '@oai/artifact-tool'
ARTIFACT_TOOL_STUB_SHA256 = '67134acad4326089bca7cd074c753bda88887a64c6a1499d15e1153d673796a4'
ARTIFACT_TOOL_STUB_PACKAGE = {'name': '@oai/artifact-tool', 'version': '0.0.0-cps-validation-stub', 'type': 'module',
                              'main': 'index.mjs', 'exports': './index.mjs'}
RESOLVE_CJS = ("const {createRequire}=require('node:module');const {pathToFileURL}=require('node:url');"
               "process.stdout.write(JSON.stringify({resolved:createRequire(pathToFileURL(process.argv[1]).href)"
               ".resolve(process.argv[2])}));")
RESOLVE_ESM = ("import {fileURLToPath} from 'node:url';"
               "process.stdout.write(JSON.stringify({resolved:fileURLToPath(import.meta.resolve(process.argv[1]))}));")
HEADERS = ['盤體名稱', '盤體規格', '材料名稱', '規格', '單位', '數量', '單價', '複價', '型號', '廠牌',
           '訂購廠商', '工程編號', '訂購客戶', '使用客戶', '需要日期', '需要數量', '合約價']
SHEETS = ['未填研究草稿', '來源與審查', '組成參考', '組成連結']
SHEET_COLS = {'未填研究草稿': 17, '來源與審查': 7, '組成參考': 17, '組成連結': 8}
WIDTHS = {'未填研究草稿': [18, 30, 38, 48, 9, 12, 12, 12, 20, 18, 22, 18, 24, 24, 18, 12, 14],
          '來源與審查': [18, 23, 38, 38, 88, 62, 18],
          '組成參考': [18, 30, 38, 48, 9, 12, 12, 12, 20, 18, 22, 18, 24, 24, 18, 12, 14],
          '組成連結': [24, 12, 24, 12, 12, 12, 65, 65]}
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
EXCEL = {'max_rows': 1048576, 'max_columns': 16384, 'cell_text_utf16_units': 32767, 'line_feeds_per_cell': 253,
         'max_abs_number': 9.99999999999999e307, 'sheet_name_chars': 31, 'column_width': 255, 'row_height_points': 409}
ERROR_LITERALS = ('#REF!', '#DIV/0!', '#VALUE!', '#NAME?', '#N/A', '#NUM!', '#NULL!', '#SPILL!', '#CALC!')
LIST_CAP = 200


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def utf16_len(s):
    return len(s.encode('utf-16-le', 'surrogatepass')) // 2


def col_letters(n):
    s = ''
    while n:
        n, k = divmod(n - 1, 26)
        s = chr(65 + k) + s
    return s


def addr_to_rc(a):
    m = re.fullmatch(r'([A-Z]+)([0-9]+)', a)
    c = 0
    for ch in m[1]:
        c = c * 26 + ord(ch) - 64
    return int(m[2]), c


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def kind(v):
    if v is None:
        return 'empty'
    if isinstance(v, bool):
        return 'boolean'
    if is_number(v):
        return 'number'
    if isinstance(v, str):
        return 'string'
    return type(v).__name__


class Findings:
    def __init__(self):
        self.items = {}

    def add(self, check, entry):
        lst = self.items.setdefault(check, [])
        lst.append(entry)

    def count(self, check):
        return len(self.items.get(check, []))

    def total(self):
        return sum(len(v) for v in self.items.values())

    def report(self):
        return {k: {'count': len(v), 'first': v[:LIST_CAP]} for k, v in self.items.items()}


# ------------------------------------------------------------------ readers
def read_openpyxl(path, data_only):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=data_only, rich_text=False, keep_links=True)
    sheets = {}
    for ws in wb.worksheets:
        cells = {}
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                if cell.value is not None or cell.data_type == 'f':
                    cells[(cell.row, cell.column)] = (cell.value, cell.data_type)
        sheets[ws.title] = {'cells': cells, 'max_row': ws.max_row, 'max_column': ws.max_column}
    return wb, [ws.title for ws in wb.worksheets], sheets


def string_item_text(el):
    """Text of a CT_Rst (<si> or <is>): plain <t> plus rich-text runs <r><t>; phonetic <rPh> excluded."""
    parts = []
    for child in el:
        if child.tag == '{%s}t' % NS['m']:
            parts.append(child.text or '')
        elif child.tag == '{%s}r' % NS['m']:
            parts.extend(t.text or '' for t in child.findall('m:t', NS))
    return ''.join(parts)


def local(tag):
    return tag.rsplit('}', 1)[-1]


def read_raw(path, F):
    """Independent OOXML reader (shared strings, inline strings, numbers, booleans, errors, formulas).
    A cell type outside CELL_TYPES (for example t="d") or unparsable number text is a finding, never a crash;
    the cell keeps its raw text and type, so the value comparison fails too."""
    out = {'order': [], 'states': [], 'sheets': {}, 'formulas': [], 'external_relationships': [], 'defined_names': 0, 'parts': []}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        out['parts'] = names
        shared = []
        if 'xl/sharedStrings.xml' in names:
            shared = [string_item_text(si) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        dn = wb.find('m:definedNames', NS)
        out['defined_names'] = 0 if dn is None else len(list(dn))
        rels = {r.attrib['Id']: r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sh in wb.find('m:sheets', NS):
            name = sh.attrib['name']
            out['order'].append(name)
            out['states'].append(sh.attrib.get('state'))
            target = rels[sh.attrib['{%s}id' % NS['r']]]
            target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
            root = ET.fromstring(z.read(target))
            cells = {}
            for c in root.findall('.//m:sheetData/m:row/m:c', NS):
                rc = addr_to_rc(c.attrib['r'])
                typ = c.attrib.get('t', 'n')
                v = c.find('m:v', NS)
                if c.find('m:f', NS) is not None:
                    out['formulas'].append({'sheet': name, 'cell': c.attrib['r']})
                if typ == 's':
                    value = shared[int(v.text)] if v is not None else None
                elif typ == 'inlineStr':
                    is_ = c.find('m:is', NS)
                    value = None if is_ is None else string_item_text(is_)
                elif typ == 'b':
                    value = None if v is None else v.text == '1'
                elif typ in ('str', 'e'):
                    value = v.text if v is not None else None
                elif typ == 'n':
                    if v is None or v.text is None:
                        value = None
                    else:
                        t = v.text
                        try:
                            value = float(t) if re.search('[.eEnN]', t) else int(t)
                        except ValueError:
                            F.add('unparsable_number', {'sheet': name, 'cell': c.attrib['r'], 'text': t[:100]})
                            value, typ = t, 'n?'
                else:
                    F.add('unknown_cell_type', {'sheet': name, 'cell': c.attrib['r'], 'type': typ})
                    value = v.text if v is not None else None
                if value is not None or typ in ('str', 'e') or typ not in CELL_TYPES:
                    cells[rc] = (value, typ)
            out['sheets'][name] = cells
        for part in names:
            if part.endswith('.rels'):
                for r in ET.fromstring(z.read(part)):
                    if r.attrib.get('TargetMode') == 'External':
                        out['external_relationships'].append({'part': part, 'target': r.attrib.get('Target')})
    return out


# ------------------------------------------------------------------ structure (review S2)
def check_structure(path, F):
    """The workbook may hold only what the portable writer produces: no hidden content, no extra parts, no view or
    format element that can hide or alter what a cell shows. Returns a small summary."""
    def bad(check, **kw):
        F.add(check, kw)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            bad('zip_parts', problem='duplicate zip entry names', names=sorted(n for n in set(names) if names.count(n) > 1))
        for n in sorted(set(names) - set(EXPECTED_PARTS)):
            bad('zip_parts', part=n, problem='part the writer does not produce')
        for n in sorted(set(EXPECTED_PARTS) - set(names)):
            bad('zip_parts', part=n, problem='missing part')
        roots = {}
        for n in sorted(set(names)):
            if not (n.endswith('.xml') or n.endswith('.rels')):
                continue
            try:
                roots[n] = ET.fromstring(z.read(n))
            except ET.ParseError as e:
                bad('xml_structure', part=n, problem='not well-formed XML', detail=str(e)[:200])
                continue
            for el in roots[n].iter():
                for k, v in el.attrib.items():
                    if local(k) in ('hidden', 'zeroHeight') and v not in FALSE_VALUES:
                        bad('hidden_attribute', part=n, element=local(el.tag), attribute=local(k), value=v)
    # workbook: children, window visibility, sheet states
    wb = roots.get('xl/workbook.xml')
    if wb is not None:
        kids = [local(e.tag) for e in wb]
        if any(k not in WORKBOOK_CHILDREN for k in kids) or kids != [k for k in WORKBOOK_CHILDREN if k in kids]:
            bad('workbook_structure', problem='workbook child elements', actual=kids)
        prot = wb.find('m:workbookProtection', NS)
        if prot is not None and prot.attrib:
            bad('workbook_structure', problem='workbookProtection attributes', actual=dict(prot.attrib))
        for view in wb.iterfind('m:bookViews/m:workbookView', NS):
            if view.attrib.get('visibility', 'visible') != 'visible' or view.attrib.get('minimized', '0') not in FALSE_VALUES:
                bad('workbook_structure', problem='workbook window not visible', actual=dict(view.attrib))
        for sh in wb.iterfind('m:sheets/m:sheet', NS):
            if sh.attrib.get('state') != 'visible':
                bad('sheet_state', sheet=sh.attrib.get('name'), state=sh.attrib.get('state'), expected='visible')
    # worksheets
    for n in EXPECTED_PARTS:
        root = roots.get(n)
        if root is None or not n.startswith('xl/worksheets/'):
            continue
        kids = [local(e.tag) for e in root]
        order = [k for k in WORKSHEET_CHILDREN if k in kids]
        if any(k not in WORKSHEET_CHILDREN for k in kids) or kids != order or 'sheetData' not in kids:
            bad('worksheet_structure', part=n, problem='worksheet child elements',
                unexpected=[k for k in kids if k not in WORKSHEET_CHILDREN], actual=kids[:20])
        for el in root:
            tag = local(el.tag)
            if tag == 'sheetPr':
                if el.attrib or any(local(x.tag) not in ('tabColor', 'outlinePr', 'pageSetUpPr') for x in el):
                    bad('worksheet_structure', part=n, problem='sheetPr', attributes=dict(el.attrib), children=[local(x.tag) for x in el])
            elif tag == 'sheetViews':
                views = list(el)
                if len(views) != 1 or local(views[0].tag) != 'sheetView':
                    bad('worksheet_structure', part=n, problem='sheetViews must hold one sheetView', actual=[local(x.tag) for x in views])
                for v in views:
                    extra = sorted(k for k in v.attrib if k not in SHEET_VIEW_ATTRS)
                    if extra or v.attrib.get('showGridLines') != '0':
                        bad('worksheet_structure', part=n, problem='sheetView attributes', attributes=dict(v.attrib))
                    if any(local(x.tag) not in ('pane', 'selection') for x in v):
                        bad('worksheet_structure', part=n, problem='sheetView children', actual=[local(x.tag) for x in v])
            elif tag == 'sheetFormatPr':
                if dict(el.attrib) != SHEET_FORMAT_ATTRS:
                    bad('worksheet_structure', part=n, problem='sheetFormatPr attributes', attributes=dict(el.attrib), expected=SHEET_FORMAT_ATTRS)
            elif tag == 'cols':
                for col in el:
                    if local(col.tag) != 'col' or any(k not in ('min', 'max', 'width', 'customWidth') for k in col.attrib):
                        bad('worksheet_structure', part=n, problem='col', attributes=dict(col.attrib))
            elif tag == 'sheetData':
                check_sheet_data(n, el, bad)
            elif tag == 'pageMargins':
                if any(k not in ('left', 'right', 'top', 'bottom', 'header', 'footer') for k in el.attrib):
                    bad('worksheet_structure', part=n, problem='pageMargins attributes', attributes=dict(el.attrib))
    # cell formats: alignment only, with the writer's attributes
    st = roots.get('xl/styles.xml')
    if st is not None:
        for k, xf in enumerate(st.iterfind('m:cellXfs/m:xf', NS)):
            for x in xf:
                if local(x.tag) != 'alignment' or any(a not in ('horizontal', 'vertical', 'wrapText') for a in x.attrib):
                    bad('styles_structure', xf=k, element=local(x.tag), attributes=dict(x.attrib))
        # fonts (v3, second review F1(b)): the writer's children only, each at most once (no strike, italic,
        # underline, vertAlign, outline, shadow, ...)
        for fonts in st.iterfind('m:fonts', NS):
            for k, font in enumerate(fonts):
                kids = [local(x.tag) for x in font]
                allowed = FONT0_CHILDREN if k == 0 else FONT_CHILDREN
                if local(font.tag) != 'font' or any(x not in allowed for x in kids) or len(kids) != len(set(kids)):
                    bad('font_structure', font=k, element=local(font.tag), children=kids, allowed=list(allowed))
    return {'parts': sorted(set(names)), 'expected_parts': list(EXPECTED_PARTS)}


def number_text_ok(text):
    """Number text the writer writes: ASCII, JavaScript Number::toString of a finite number (NUMBER_TEXT_RE, whole text)."""
    return isinstance(text, str) and text.isascii() and NUMBER_TEXT_RE.fullmatch(text) is not None


def check_sheet_data(part, sheet_data, bad):
    """Rows and cells of one worksheet's <sheetData> (review S2; v3 second review F1(b): value children, number text,
    duplicate and out-of-row references). Readers differ on these: Python readers take the first matching child and
    accept any text int()/float() accept; LibreOffice took the last <v>/<is>, an empty cell for a <v> beside <is>, and
    1 or 0 for '1_234_567' or fullwidth digits (review round 2, N01-N07)."""
    n = part
    seen_rows, seen_cells, last_row = set(), set(), 0
    for row in sheet_data:
        ra = row.attrib
        if local(row.tag) != 'row' or any(k not in ('r', 'spans', 'ht', 'customHeight') for k in ra) \
                or (('ht' in ra or 'customHeight' in ra) and (ra.get('r') != '1' or ra.get('ht') != '36')):
            bad('worksheet_structure', part=n, problem='row attributes', row=ra.get('r'), attributes=dict(ra))
        rn = ra.get('r')
        rnum = int(rn) if rn is not None and ROW_NUMBER_RE.fullmatch(rn) else None
        if rnum is None:
            bad('worksheet_structure', part=n, problem='row without a valid r attribute', row=rn)
        elif rnum in seen_rows:
            bad('duplicate_reference', part=n, problem='duplicate row number', row=rn)
        elif rnum < last_row:
            bad('worksheet_structure', part=n, problem='rows not in ascending order', row=rn, after=last_row)
        if rnum is not None:
            seen_rows.add(rnum)
            last_row = max(last_row, rnum)
        last_col = 0
        for c in row:
            where = c.attrib.get('r')
            if local(c.tag) != 'c' or any(k not in ('r', 's', 't') for k in c.attrib):
                bad('worksheet_structure', part=n, problem='cell attributes', cell=where, attributes=dict(c.attrib))
            m = CELL_REF_RE.fullmatch(where) if where is not None else None
            if m is None:
                bad('worksheet_structure', part=n, problem='cell without a valid r attribute', cell=where, row=rn)
            else:
                cr, cc = addr_to_rc(where)
                if where in seen_cells:
                    bad('duplicate_reference', part=n, problem='duplicate cell reference', cell=where)
                elif cc <= last_col and cr == rnum:
                    bad('worksheet_structure', part=n, problem='cells not in ascending column order', cell=where)
                if rnum is not None and cr != rnum:
                    bad('worksheet_structure', part=n, problem='cell reference outside its row', cell=where, row=rn)
                seen_cells.add(where)
                last_col = max(last_col, cc)
            typ = c.attrib.get('t', 'n')
            kids = [local(x.tag) for x in c]
            values = [k for k in kids if k in ('v', 'is')]
            problems = []
            if len(values) > 1:
                problems.append('more than one value child')
            if kids.count('f') > 1:
                problems.append('more than one <f>')
            if typ == 'inlineStr' and 'v' in kids:
                problems.append('<v> in an inlineStr cell')
            if typ != 'inlineStr' and 'is' in kids:
                problems.append('<is> in a cell that is not inlineStr')
            if problems:
                bad('cell_value_children', part=n, cell=where, type=typ, children=kids, problem='; '.join(problems))
            for x in c:
                xt = local(x.tag)
                if xt not in ('v', 'is', 'f'):
                    bad('worksheet_structure', part=n, problem='cell child', cell=where, child=xt)
                if xt == 'v':
                    if x.attrib or len(x):
                        bad('cell_value_children', part=n, cell=where, problem='<v> with attributes or child elements',
                            attributes=dict(x.attrib), children=[local(y.tag) for y in x])
                    text = x.text or ''
                    if typ == 'n' and not number_text_ok(text):
                        bad('number_text', part=n, cell=where, text=text[:100],
                            problem='number text is not ASCII JavaScript Number::toString text')
                if xt == 'is':
                    ts = list(x)
                    if len(ts) != 1 or local(ts[0].tag) != 't':
                        bad('worksheet_structure', part=n, problem='inline string must be one plain <t> (no rich-text runs)',
                            cell=where, actual=[local(t.tag) for t in ts])
                    for t in ts:
                        if any(k != XML_SPACE for k in t.attrib):
                            bad('worksheet_structure', part=n, problem='<t> attributes', cell=where, attributes=dict(t.attrib))
                        if len(t):
                            bad('cell_value_children', part=n, cell=where, problem='<t> with child elements',
                                children=[local(y.tag) for y in t])
                        text = t.text or ''
                        if text != text.strip(' \t\r\n') and t.attrib.get(XML_SPACE) != 'preserve':
                            bad('whitespace_not_preserved', part=n, cell=where,
                                problem='leading or trailing whitespace without xml:space="preserve" (applications may drop it)')


# ------------------------------------------------------------------ provenance of EXPECTED (review S3)
def node_env_allowed(name):
    return name in NODE_ENV_KEEP or name.startswith(NODE_ENV_KEEP_PREFIXES)


def node_env(environ=None):
    """The environment of every node process: only the allowlisted variables (NODE_ENV_KEEP and LC_*), as in
    writer_portable.py. Returns (env, kept names, removed names)."""
    environ = os.environ if environ is None else environ
    env = {k: v for k, v in environ.items() if node_env_allowed(k)}
    return env, sorted(env), sorted(k for k in environ if not node_env_allowed(k))


def run_node(cmd, timeout=600, cwd=None):
    p = subprocess.run(cmd, capture_output=True, timeout=timeout, env=node_env()[0], cwd=cwd)
    return p.returncode, p.stdout, p.stderr


class ProvenanceRefused(Exception):
    pass


def pinned_node_environment(node, writer_dir):
    """The writer's S1 checks: pinned writer files in the writer directory itself, @oai/artifact-tool resolved from
    writer004.mjs (require and import resolvers agree) to the pinned stub, the allowlisted node environment."""
    real = Path(os.path.realpath(writer_dir))
    for name, allowed in WRITER_PINS.items():
        p = writer_dir / name
        if not p.is_file() or p.is_symlink() or Path(os.path.realpath(p)) != real / name:
            raise ProvenanceRefused({'check': 'writer file missing or outside the writer directory', 'file': name})
        if sha256(p.read_bytes()) not in allowed:
            raise ProvenanceRefused({'check': 'writer file not pinned', 'file': name})
    code, out, err = run_node([node, '-e', RESOLVE_CJS, str(real / 'writer004.mjs'), ARTIFACT_TOOL_SPECIFIER], 60)
    if code != 0:
        raise ProvenanceRefused({'check': '@oai/artifact-tool not resolvable from writer004.mjs', 'stderr': err.decode('utf-8', 'replace')[-300:]})
    cjs = json.loads(out.decode('utf-8'))['resolved']
    code, out, err = run_node([node, '--input-type=module', '-e', RESOLVE_ESM, ARTIFACT_TOOL_SPECIFIER], 60, cwd=str(real))
    esm = json.loads(out.decode('utf-8'))['resolved'] if code == 0 else None
    if esm is None or os.path.realpath(esm) != os.path.realpath(cjs):
        raise ProvenanceRefused({'check': 'require and import resolution of @oai/artifact-tool differ', 'require': cjs, 'import': esm})
    stub = Path(cjs)
    h = sha256(stub.read_bytes()) if stub.is_file() else None
    try:
        pkg = json.loads((stub.parent / 'package.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pkg = None
    if h != ARTIFACT_TOOL_STUB_SHA256 or pkg != ARTIFACT_TOOL_STUB_PACKAGE:
        raise ProvenanceRefused({'check': '@oai/artifact-tool is not the pinned CPS validation stub', 'resolved': cjs, 'sha256': h})
    _, kept, removed = node_env()
    return real, {'artifact_tool_resolved_path': cjs, 'artifact_tool_sha256': h, 'kept_variables': kept, 'removed_variables': removed}


def check_provenance(receipt, ebytes, xbytes, carrier, writer_dir, node, F):
    """v3 (second review F1(a), F2): the writer rerun (--mode v2) always runs and both EXPECTED_SAVED_VALUES.json and the
    xlsx are byte-compared, whatever the receipt's mode says (the receipt is not authenticated). A receipt that says v1
    also gets the writer004 prepareMatrices comparison (run first). The result is PASS, or the first refusal code
    (NODE_ENVIRONMENT_REFUSED, WRITER004_REFUSED, WRITER_RERUN_FAILED, UNKNOWN_MODE), or FAILED."""
    def bad(**kw):
        F.add('provenance', kw)
    codes = []
    rec = {'checked': True, 'carrier': str(carrier), 'writer_dir': str(writer_dir)}
    raw = carrier.read_bytes()
    rec['carrier_sha256'] = sha256(raw)
    mode = None
    if receipt is None:
        bad(check='WRITER_RECEIPT.json missing: the carrier sha256 cannot be checked against the receipt')
    else:
        rec['receipt_carrier_sha256'] = (receipt.get('input_carrier') or {}).get('sha256')
        if rec['receipt_carrier_sha256'] != rec['carrier_sha256']:
            bad(check='carrier sha256 differs from WRITER_RECEIPT.json input_carrier.sha256',
                carrier=rec['carrier_sha256'], receipt=rec['receipt_carrier_sha256'])
        mode = receipt.get('mode')
        if mode not in ('v1', 'v2'):
            bad(check='unknown receipt mode', mode=mode)
            codes.append('UNKNOWN_MODE')
    rec['receipt_mode'] = mode
    rec['method'] = ('writer_portable.py --mode v2 rerun into a temporary directory, whatever the receipt mode says; '
                     'EXPECTED_SAVED_VALUES.json and the xlsx byte-compared (builds are reproducible; v2 gives the v1 bytes for a '
                     'carrier without O13/R57)' + ('; receipt mode v1: also writer004_matrices.mjs (writer004 prepareMatrices on the '
                                                   'carrier) byte-compared with EXPECTED_SAVED_VALUES.json' if mode == 'v1' else ''))
    rec['writer004_check'] = 'run (receipt mode v1)' if mode == 'v1' else 'not run (receipt mode is not v1)'
    if mode == 'v1':
        try:
            real, env_rec = pinned_node_environment(node, writer_dir)
        except ProvenanceRefused as e:
            bad(**e.args[0])
            codes.append('NODE_ENVIRONMENT_REFUSED')
        else:
            rec['node_environment'] = env_rec
            code, out, err = run_node([node, str(NODE_MATRICES), '--writer', str(real / 'writer004.mjs'), '--carrier', str(carrier)])
            rec['writer004_matrices.mjs_sha256'] = sha256(NODE_MATRICES.read_bytes())
            if code != 0:
                try:
                    ref_code = json.loads(err.decode('utf-8').strip().splitlines()[-1]).get('code')
                except (ValueError, IndexError, AttributeError, UnicodeDecodeError):
                    ref_code = None
                bad(check='writer004 prepareMatrices refused the carrier', code=ref_code, stderr=err.decode('utf-8', 'replace')[-300:])
                codes.append('WRITER004_REFUSED')
            else:
                rec['writer004_expected_sha256'] = sha256(out)
                rec['writer004_expected_byte_identical'] = out == ebytes
                if out != ebytes:
                    bad(check='EXPECTED_SAVED_VALUES.json differs from writer004 prepareMatrices on the carrier')
    with tempfile.TemporaryDirectory(prefix='cps_saved_qa_rerun_') as td:
        dest = Path(td) / 'rerun'
        p = subprocess.run([sys.executable, '-I', '-B', str(WRITER), '--carrier', str(carrier), '--out', str(dest),
                            '--writer-dir', str(writer_dir), '--node', node, '--mode', 'v2'], capture_output=True, timeout=1800)
        rec['writer_portable.py_sha256'] = sha256(WRITER.read_bytes())
        if p.returncode != 0:
            err = p.stderr.decode('utf-8', 'replace')
            try:
                ref = json.loads(err.strip().splitlines()[-1])
                ref = {'code': ref.get('code'), 'stage': ref.get('stage')}
            except (ValueError, IndexError, AttributeError):
                ref = None
            bad(check='writer rerun refused or failed', refusal=ref, stderr=err[-400:])
            codes.append('WRITER_RERUN_FAILED')
            e2 = x2 = r2 = None
        else:
            e2, x2 = (dest / 'EXPECTED_SAVED_VALUES.json').read_bytes(), (dest / XLSX_NAME).read_bytes()
            r2 = json.loads((dest / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
    if r2 is not None:
        rec['rerun_writer'] = r2.get('writer')
        rec['rerun_mode'] = r2.get('mode')
        rec['rerun_relaxations_applied'] = (r2.get('relaxations') or {}).get('applied')
        rec['rerun_node_environment'] = r2.get('node_environment')
        rec['expected_byte_identical'], rec['xlsx_byte_identical'] = e2 == ebytes, x2 == xbytes
        if e2 != ebytes:
            bad(check='EXPECTED_SAVED_VALUES.json differs from the writer rerun on the carrier')
        if x2 != xbytes:
            bad(check='research-draft.xlsx differs from the writer rerun on the carrier')
    rec['result'] = 'PASS' if not F.count('provenance') else (codes[0] if codes else 'FAILED')
    return rec


# ------------------------------------------------------------------ comparisons
STRING_CELL_TYPES = {'openpyxl_formulas': ('s',), 'openpyxl_data_only': ('s',), 'raw_ooxml': ('s', 'inlineStr')}


def value_ok(want, got, dtype, reader):
    """Exact value and type: empty stays empty, text stays text, numbers stay numbers."""
    if want is None:
        return got is None
    if isinstance(want, str):
        return dtype in STRING_CELL_TYPES[reader] and isinstance(got, str) and got == want
    if is_number(want):
        return dtype == 'n' and is_number(got) and math.isfinite(got) and got == want
    return False


def compare_sheet(name, rows, cells, reader, F):
    ncols = SHEET_COLS.get(name)
    counts = {'rows': len(rows), 'columns': ncols, 'checked_cells': 0, 'nonempty_expected': 0,
              'strings': 0, 'numbers': 0, 'empty': 0}
    remaining = dict(cells)
    for i, row in enumerate(rows, start=1):
        for j, want in enumerate(row, start=1):
            got, dtype = remaining.pop((i, j), (None, None))
            counts['checked_cells'] += 1
            k = kind(want)
            counts[{'string': 'strings', 'number': 'numbers', 'empty': 'empty'}.get(k, 'empty')] += 1
            if want is not None:
                counts['nonempty_expected'] += 1
            if not value_ok(want, got, dtype, reader):
                F.add('value_type_mismatch', {'reader': reader, 'sheet': name, 'cell': f'{col_letters(j)}{i}',
                                              'expected_type': k, 'actual_type': kind(got), 'actual_cell_type': dtype,
                                              'expected': want, 'actual': got})
    for (r, c), (got, dtype) in sorted(remaining.items()):
        if got is not None or dtype in ('f', 'str', 'e'):
            F.add('unexpected_populated_cell', {'reader': reader, 'sheet': name, 'cell': f'{col_letters(c)}{r}',
                                                'actual': got, 'actual_cell_type': dtype})
    return counts


def check_limits(name, cells, F):
    for (r, c), (v, _) in cells.items():
        where = {'sheet': name, 'cell': f'{col_letters(c)}{r}'}
        if r > EXCEL['max_rows'] or c > EXCEL['max_columns']:
            F.add('excel_limit', {**where, 'limit': 'grid'})
        if isinstance(v, str):
            if utf16_len(v) > EXCEL['cell_text_utf16_units']:
                F.add('excel_limit', {**where, 'limit': 'cell_text_utf16_units', 'length': utf16_len(v)})
            if v.count('\n') > EXCEL['line_feeds_per_cell']:
                F.add('excel_limit', {**where, 'limit': 'line_feeds_per_cell', 'line_feeds': v.count('\n')})
        elif is_number(v) and (not math.isfinite(v) or abs(v) > EXCEL['max_abs_number']):
            F.add('excel_limit', {**where, 'limit': 'number', 'value': repr(v)})


def check_sheet_name(name, F):
    if not name.strip() or len(name) > EXCEL['sheet_name_chars'] or re.search(r'[\[\]:*?/\\]', name) or name.startswith("'") or name.endswith("'"):
        F.add('excel_limit', {'sheet': name, 'limit': 'sheet_name'})


def font_extras(font):
    """v3 (second review F1(b), N10/N11): font properties the writer never sets; each must be off."""
    return (('font.italic', False, bool(font.i)), ('font.strike', False, bool(font.strike)),
            ('font.underline', None, font.u), ('font.vertAlign', None, font.vertAlign))


def check_formatting(wb, expected_rows, F):
    """The writer004 formatSheet/main-sheet formatting as the portable writer expresses it."""
    checked = 0

    def bad(sheet, cell, prop, want, got):
        F.add('formatting', {'sheet': sheet, 'cell': cell, 'property': prop, 'expected': want, 'actual': got})

    def rgb(color):
        return None if color is None else getattr(color, 'rgb', None)
    for name in SHEETS:
        if name not in wb.sheetnames:
            continue
        ws = wb[name]
        ncols, nrows = SHEET_COLS[name], len(expected_rows[name])
        for c in range(1, ncols + 1):
            cell = ws.cell(row=1, column=c)
            a = cell.coordinate
            checked += 1
            for prop, want, got in (('font.name', 'Arial', cell.font.name), ('font.size', 11, cell.font.sz), ('font.bold', True, cell.font.b),
                                    ('font.color', 'FFFFFFFF', rgb(cell.font.color)), ('fill.type', 'solid', cell.fill.fill_type),
                                    ('fill.color', 'FF29445D', rgb(cell.fill.fgColor)), ('align.horizontal', 'center', cell.alignment.horizontal),
                                    ('align.vertical', 'center', cell.alignment.vertical), ('align.wrap', True, cell.alignment.wrap_text)) + font_extras(cell.font):
                if got != want:
                    bad(name, a, prop, want, got)
        for r in range(2, nrows + 1):
            for c in range(1, ncols + 1):
                cell = ws.cell(row=r, column=c)
                a = cell.coordinate
                checked += 1
                main_num = name == SHEETS[0] and c in (6, 16, 17)
                main_fill = name == SHEETS[0] and c in (7, 8)
                for prop, want, got in (('font.name', 'Arial', cell.font.name), ('font.size', 11, cell.font.sz), ('font.bold', False, bool(cell.font.b)),
                                        ('font.color', 'FF172033', rgb(cell.font.color)), ('align.vertical', 'top', cell.alignment.vertical),
                                        ('align.wrap', True, cell.alignment.wrap_text),
                                        ('align.horizontal', 'right' if main_num else None, cell.alignment.horizontal),
                                        ('number_format', 'General', cell.number_format),
                                        ('fill.type', 'solid' if main_fill else None, cell.fill.fill_type)) + font_extras(cell.font):
                    if got != want:
                        bad(name, a, prop, want, got)
                if main_fill and rgb(cell.fill.fgColor) != 'FFF1F3F5':
                    bad(name, a, 'fill.color', 'FFF1F3F5', rgb(cell.fill.fgColor))
        for j, w in enumerate(WIDTHS[name], start=1):
            got = ws.column_dimensions[col_letters(j)].width
            if got != w:
                bad(name, col_letters(j), 'column_width', w, got)
            if got is not None and got > EXCEL['column_width']:
                F.add('excel_limit', {'sheet': name, 'column': col_letters(j), 'limit': 'column_width', 'value': got})
        if ws.freeze_panes != 'D2':
            bad(name, None, 'freeze_panes', 'D2', ws.freeze_panes)
        if ws.sheet_view.showGridLines is not False:
            bad(name, None, 'showGridLines', False, ws.sheet_view.showGridLines)
        if ws.row_dimensions[1].height != 36:
            bad(name, None, 'row1_height', 36, ws.row_dimensions[1].height)
        explicit = [r for r, d in ws.row_dimensions.items() if r != 1 and d.height is not None]
        if explicit:
            bad(name, None, 'data_rows_explicit_height', [], explicit[:20])
        for r, d in ws.row_dimensions.items():
            if d.height is not None and d.height > EXCEL['row_height_points']:
                F.add('excel_limit', {'sheet': name, 'row': r, 'limit': 'row_height_points', 'value': d.height})
        tab = rgb(ws.sheet_properties.tabColor)
        want_tab = 'FF29445D' if name == SHEETS[0] else None
        if tab != want_tab:
            bad(name, None, 'tab_color', want_tab, tab)
    return checked


# ------------------------------------------------------------------ main
def load_expected(ebytes, F):
    """EXPECTED_SAVED_VALUES.json, shape-checked; None (with a finding) when it cannot be compared at all."""
    try:
        expected = json.loads(ebytes.decode('utf-8'))
        sheets = expected['sheets']
        if not isinstance(sheets, list) or not all(isinstance(x, dict) and isinstance(x.get('name'), str) and isinstance(x.get('values'), list)
                                                   and all(isinstance(r, list) for r in x['values']) for x in sheets):
            raise ValueError('sheets must be a list of {name, values: [[...]]}')
        return sheets
    except (UnicodeDecodeError, ValueError, KeyError, TypeError) as e:
        F.add('expected_shape', {'check': 'EXPECTED_SAVED_VALUES.json unreadable', 'detail': str(e)[:200]})
        return None


def run_qa(out_dir, formatting=True, carrier=None, writer_dir=None, node='node'):
    xlsx = out_dir / XLSX_NAME
    exp_path = out_dir / 'EXPECTED_SAVED_VALUES.json'
    xbytes, ebytes = xlsx.read_bytes(), exp_path.read_bytes()
    F = Findings()
    exp_sheets = load_expected(ebytes, F)
    receipt_path = out_dir / 'WRITER_RECEIPT.json'
    receipt = None
    if not receipt_path.is_file():
        F.add('integrity', {'check': 'WRITER_RECEIPT.json missing'})
    else:
        try:
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            if not isinstance(receipt, dict):
                raise ValueError('not an object')
        except (UnicodeDecodeError, ValueError) as e:
            F.add('integrity', {'check': 'WRITER_RECEIPT.json unreadable', 'detail': str(e)[:200]})
            receipt = None
    if receipt is not None:
        if (receipt.get('output_xlsx') or {}).get('sha256') != sha256(xbytes):
            F.add('integrity', {'check': 'xlsx sha256 differs from WRITER_RECEIPT.json'})
        if (receipt.get('expected_saved_values') or {}).get('sha256') != sha256(ebytes):
            F.add('integrity', {'check': 'EXPECTED_SAVED_VALUES.json sha256 differs from WRITER_RECEIPT.json'})

    structure = None
    try:
        structure = check_structure(xlsx, F)
    except Exception as e:                      # noqa: BLE001 - a malformed package is a finding, not a crash
        F.add('reader_error', {'reader': 'structure', 'error': repr(e)[:300]})

    provenance = {'checked': False, 'note': 'Not checked: run with --carrier and --writer-dir. Without them a consistent replacement of '
                                            'EXPECTED_SAVED_VALUES.json and the workbook (with or without WRITER_RECEIPT.json) is not detected.'}
    if carrier is not None:
        try:
            provenance = check_provenance(receipt, ebytes, xbytes, carrier, writer_dir, node, F)
        except Exception as e:                  # noqa: BLE001
            F.add('provenance', {'check': 'provenance check failed', 'error': repr(e)[:300]})
            provenance = {'checked': True, 'result': 'ERROR'}

    readers, per_reader, header_checks, raw, wb_f, fmt_checked = {}, {}, {}, None, None, None
    if exp_sheets is not None:
        exp_rows = {s['name']: s['values'] for s in exp_sheets}
        if [s['name'] for s in exp_sheets] != SHEETS:
            F.add('expected_shape', {'check': 'sheet names/order', 'actual': [s['name'] for s in exp_sheets]})
        for s in exp_sheets:
            ncols = SHEET_COLS.get(s['name'])
            for i, row in enumerate(s['values'], start=1):
                if len(row) != ncols:
                    F.add('expected_shape', {'sheet': s['name'], 'row': i, 'columns': len(row), 'expected_columns': ncols})
        header_checks = {'expected_file_main_row1_is_17_headers': (exp_rows.get(SHEETS[0]) or [[]])[0] == HEADERS,
                         'expected_file_components_row1_is_17_headers': (exp_rows.get(SHEETS[2]) or [[]])[0] == HEADERS}
        for reader, fn in (('openpyxl_formulas', lambda: read_openpyxl(xlsx, data_only=False)),
                           ('openpyxl_data_only', lambda: read_openpyxl(xlsx, data_only=True)),
                           ('raw_ooxml', lambda: read_raw(xlsx, F))):
            try:
                res = fn()
            except Exception as e:              # noqa: BLE001 - recorded, the QA fails
                F.add('reader_error', {'reader': reader, 'error': repr(e)[:300]})
                continue
            if reader == 'raw_ooxml':
                raw = res
                readers[reader] = (raw['order'], raw['sheets'])
            else:
                wb, order, sheets = res
                if reader == 'openpyxl_formulas':
                    wb_f = (wb, sheets)
                readers[reader] = (order, {k: v['cells'] for k, v in sheets.items()})
        for reader, (order, cells_by_sheet) in readers.items():
            if order != [s['name'] for s in exp_sheets]:
                F.add('sheet_order', {'reader': reader, 'actual': order, 'expected': [s['name'] for s in exp_sheets]})
            counts = []
            for s in exp_sheets:
                cells = cells_by_sheet.get(s['name'], {})
                counts.append(compare_sheet(s['name'], s['values'], cells, reader, F))
            per_reader[reader] = counts
            if reader == 'raw_ooxml':
                for name in order:
                    check_sheet_name(name, F)
            main = cells_by_sheet.get(SHEETS[0], {})
            row1 = [main.get((1, c), (None, None))[0] for c in range(1, 18)]
            header_checks[f'{reader}_main_row1_A_Q_equals_17_headers'] = row1 == HEADERS
            header_checks[f'{reader}_main_R1_empty'] = main.get((1, 18), (None, None))[0] is None
            header_checks[f'{reader}_main_max_column_le_17'] = all(c <= 17 for (_, c) in main)
        for k, ok in header_checks.items():
            if not ok:
                F.add('header_row', {'check': k})

        # formulas: openpyxl formula mode, raw <f> elements, formula-result/error cell types
        if wb_f is not None:
            for name, sh in wb_f[1].items():
                for (r, c), (v, dt) in sh['cells'].items():
                    if dt == 'f':
                        F.add('formula', {'reader': 'openpyxl_formulas', 'sheet': name, 'cell': f'{col_letters(c)}{r}'})
                    if dt == 'e':
                        F.add('error_cell_type', {'reader': 'openpyxl_formulas', 'sheet': name, 'cell': f'{col_letters(c)}{r}'})
        if raw is not None:
            for f in raw['formulas']:
                F.add('formula', {'reader': 'raw_ooxml', **f})
            for name, cells in raw['sheets'].items():
                for (r, c), (_, typ) in cells.items():
                    if typ in ('str', 'e'):
                        F.add('error_cell_type' if typ == 'e' else 'formula', {'reader': 'raw_ooxml', 'sheet': name, 'cell': f'{col_letters(c)}{r}', 'type': typ})
            if raw['defined_names']:
                F.add('defined_names', {'count': raw['defined_names']})
            for e in raw['external_relationships']:
                F.add('external_relationship', e)
            for p in [p for p in raw['parts'] if re.search(r'(?:vbaProject|externalLink|connections\.xml|calcChain)', p)]:
                F.add('unexpected_part', {'part': p})

        # readers agree with each other on every populated cell
        if len(readers) == 3:
            for name in SHEETS:
                a = {k: v[0] for k, v in readers['openpyxl_formulas'][1].get(name, {}).items() if v[0] is not None}
                b = {k: v[0] for k, v in readers['openpyxl_data_only'][1].get(name, {}).items() if v[0] is not None}
                c_ = {k: v[0] for k, v in readers['raw_ooxml'][1].get(name, {}).items() if v[0] is not None}
                for key in set(a) | set(b) | set(c_):
                    va, vb, vc = a.get(key), b.get(key), c_.get(key)
                    if not (va == vb == vc and kind(va) == kind(vb) == kind(vc)):
                        F.add('reader_disagreement', {'sheet': name, 'cell': f'{col_letters(key[1])}{key[0]}',
                                                      'openpyxl_formulas': va, 'openpyxl_data_only': vb, 'raw_ooxml': vc})
        if 'openpyxl_formulas' in readers:
            for name, cells in readers['openpyxl_formulas'][1].items():
                check_limits(name, cells, F)
        if formatting and wb_f is not None:
            try:
                fmt_checked = check_formatting(wb_f[0], exp_rows, F)
            except Exception as e:              # noqa: BLE001
                F.add('reader_error', {'reader': 'formatting', 'error': repr(e)[:300]})

    error_text = []
    for name, cells in (raw['sheets'].items() if raw else []):
        for (r, c), (v, _) in sorted(cells.items()):
            if isinstance(v, str) and any(t in v for t in ERROR_LITERALS):
                error_text.append({'sheet': name, 'cell': f'{col_letters(c)}{r}'})

    value_checks = ('value_type_mismatch', 'unexpected_populated_cell', 'sheet_order', 'header_row', 'formula', 'error_cell_type',
                    'defined_names', 'external_relationship', 'unexpected_part', 'reader_disagreement', 'excel_limit',
                    'expected_shape', 'integrity', 'reader_error', 'unknown_cell_type', 'unparsable_number',
                    'zip_parts', 'xml_structure', 'hidden_attribute', 'sheet_state', 'workbook_structure', 'worksheet_structure',
                    'whitespace_not_preserved', 'styles_structure', 'cell_value_children', 'number_text', 'duplicate_reference',
                    'font_structure', 'provenance')
    unclassified = sorted(k for k in F.items if k not in value_checks and k != 'formatting')
    value_fail = sum(F.count(k) for k in value_checks) + sum(F.count(k) for k in unclassified)
    fmt_fail = F.count('formatting')
    status = 'SAVED_ALL_CELL_VALUE_TYPE_PASS' if value_fail == 0 and (not formatting or fmt_fail == 0) else 'SAVED_QA_FAILED'
    import openpyxl
    return {
        'schema': 'cps.export.saved-qa.v1', 'tool': VERSION, 'status': status,
        'xlsx': {'file': xlsx.name, 'sha256': sha256(xbytes), 'bytes': len(xbytes)},
        'expected_saved_values': {'file': exp_path.name, 'sha256': sha256(ebytes)},
        'writer_receipt_present': receipt is not None,
        'expected_provenance': provenance,
        'structure': structure,
        'readers': list(readers), 'sheet_order': raw['order'] if raw else None,
        'counts_by_reader': per_reader,
        'totals': {'sheets': len(exp_sheets or []),
                   'cells_compared_per_reader': sum(c['checked_cells'] for c in per_reader.get('raw_ooxml', [])),
                   'value_type_mismatches': F.count('value_type_mismatch'), 'unexpected_populated_cells': F.count('unexpected_populated_cell'),
                   'formulas': F.count('formula'), 'excel_limit_violations': F.count('excel_limit'),
                   'reader_disagreements': F.count('reader_disagreement'),
                   'structure_failures': sum(F.count(k) for k in ('zip_parts', 'xml_structure', 'hidden_attribute', 'sheet_state',
                                                                  'workbook_structure', 'worksheet_structure', 'whitespace_not_preserved',
                                                                  'styles_structure', 'unknown_cell_type', 'unparsable_number',
                                                                  'cell_value_children', 'number_text', 'duplicate_reference', 'font_structure')),
                   'provenance_failures': F.count('provenance'), 'expected_provenance_checked': bool(provenance.get('checked')),
                   'formatting_failures': fmt_fail if formatting else None,
                   'formatting_cells_checked': fmt_checked, 'value_check_failures': value_fail},
        'header_checks': header_checks,
        'excel_limits_checked': EXCEL,
        'literal_error_text_cells': {'count': len(error_text), 'first': error_text[:50],
                                     'note': 'informational, like writer004 ERROR_SCAN: carried text may legitimately contain error text'},
        'findings': F.report(),
        'scope': ('Saved-workbook fidelity to the writer matrix (EXPECTED_SAVED_VALUES.json) and package structure; with --carrier and '
                  '--writer-dir also the provenance of EXPECTED from the carrier. Not source semantics, not visual QA.'),
        'cps_evidence_preconditions': {
            'provenance_checked': bool(provenance.get('checked')), 'formatting_checked': bool(formatting),
            'note': ('CPS evidence needs both (README "Conditions of use"): --carrier must be the frozen route carrier, its sha256 '
                     '(expected_provenance.carrier_sha256) checked against the route convert receipt or the freeze record, and a run '
                     'with --no-formatting is not CPS evidence.')},
        'native_excel_validation': False, 'openpyxl': openpyxl.__version__,
    }


def dump(obj):
    text = json.dumps(obj, ensure_ascii=False, indent=2, default=repr) + '\n'
    try:
        return text.encode('utf-8')
    except UnicodeEncodeError:
        return (json.dumps(obj, ensure_ascii=True, indent=2, default=repr) + '\n').encode('ascii')


def main(argv=None):
    ap = argparse.ArgumentParser(description='CPS saved workbook QA (read-only)')
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--report')
    ap.add_argument('--no-formatting', action='store_true')
    ap.add_argument('--carrier', help='the input carrier: check the provenance of EXPECTED_SAVED_VALUES.json (needs --writer-dir)')
    ap.add_argument('--writer-dir', help='the archived writer directory (needs --carrier)')
    ap.add_argument('--node', default='node')
    a = ap.parse_args(argv)
    if bool(a.carrier) != bool(a.writer_dir):
        ap.error('--carrier and --writer-dir go together')
    out_dir = Path(a.output_dir).resolve(strict=True)
    carrier = Path(a.carrier).resolve(strict=True) if a.carrier else None
    writer_dir = Path(a.writer_dir).absolute() if a.writer_dir else None
    report_path = Path(a.report) if a.report else out_dir / 'SAVED_QA.json'
    before = sha256((out_dir / XLSX_NAME).read_bytes())
    try:
        rep = run_qa(out_dir, formatting=not a.no_formatting, carrier=carrier, writer_dir=writer_dir, node=a.node)
    except Exception as e:                      # noqa: BLE001 - never crash without a report
        rep = {'schema': 'cps.export.saved-qa.v1', 'tool': VERSION, 'status': 'SAVED_QA_FAILED',
               'findings': {'qa_error': {'count': 1, 'first': [repr(e)[:1000]]}}, 'totals': {'value_check_failures': 1}}
    if sha256((out_dir / XLSX_NAME).read_bytes()) != before:
        rep['status'] = 'SAVED_QA_FAILED'
        rep.setdefault('findings', {})['workbook_changed_during_qa'] = {'count': 1}
    with open(report_path, 'xb') as f:
        f.write(dump(rep))
    print(json.dumps({'status': rep['status'], 'report': str(report_path), **rep['totals']}, ensure_ascii=False))
    return 0 if rep['status'] == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
