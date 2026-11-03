"""CPS saved 17-column workbook QA (read-only; part of the NOT ADMITTED portable export route).

Reopens the saved workbook and compares every cell of every sheet with the writer's
EXPECTED_SAVED_VALUES.json (value and type, exact). Three independent readers:
openpyxl data_only=False, openpyxl data_only=True, and a raw OOXML (zip + XML) reader.
Also checks: sheet names/order, the 17-column header row of the main sheet, no formulas,
no unexpected populated cells, Excel limits, external relationships, and (unless
--no-formatting) the writer004 formatting the portable writer claims to reproduce.
Self-contained: it does not import the writer.

Usage
  python3 -I -B saved_qa.py --output-dir /abs/writer-output [--report /abs/SAVED_QA.json] [--no-formatting]
Default report: <output-dir>/SAVED_QA.json (created; must not exist). Exit 0 only on PASS.
"""
import argparse, hashlib, json, math, re, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.dont_write_bytecode = True

VERSION = 'cps-export-saved-qa.v1'
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


def read_raw(path):
    """Independent OOXML reader (shared strings, inline strings, numbers, booleans, errors, formulas)."""
    out = {'order': [], 'sheets': {}, 'formulas': [], 'external_relationships': [], 'defined_names': 0, 'parts': []}
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
                else:
                    if v is None or v.text is None:
                        value = None
                    else:
                        t = v.text
                        value = float(t) if re.search('[.eEnN]', t) else int(t)
                if value is not None or typ in ('str', 'e'):
                    cells[rc] = (value, typ)
            out['sheets'][name] = cells
        for part in names:
            if part.endswith('.rels'):
                for r in ET.fromstring(z.read(part)):
                    if r.attrib.get('TargetMode') == 'External':
                        out['external_relationships'].append({'part': part, 'target': r.attrib.get('Target')})
    return out


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
                                    ('align.vertical', 'center', cell.alignment.vertical), ('align.wrap', True, cell.alignment.wrap_text)):
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
                                        ('fill.type', 'solid' if main_fill else None, cell.fill.fill_type)):
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
def run_qa(out_dir, formatting=True):
    xlsx = out_dir / 'research-draft.xlsx'
    exp_path = out_dir / 'EXPECTED_SAVED_VALUES.json'
    xbytes, ebytes = xlsx.read_bytes(), exp_path.read_bytes()
    expected = json.loads(ebytes.decode('utf-8'))
    exp_sheets = expected['sheets']
    exp_rows = {s['name']: s['values'] for s in exp_sheets}
    F = Findings()
    receipt_path = out_dir / 'WRITER_RECEIPT.json'
    receipt = None
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt.get('output_xlsx', {}).get('sha256') != sha256(xbytes):
            F.add('integrity', {'check': 'xlsx sha256 differs from WRITER_RECEIPT.json'})
        if receipt.get('expected_saved_values', {}).get('sha256') != sha256(ebytes):
            F.add('integrity', {'check': 'EXPECTED_SAVED_VALUES.json sha256 differs from WRITER_RECEIPT.json'})

    # expected-file shape
    if [s['name'] for s in exp_sheets] != SHEETS:
        F.add('expected_shape', {'check': 'sheet names/order', 'actual': [s['name'] for s in exp_sheets]})
    for s in exp_sheets:
        ncols = SHEET_COLS.get(s['name'])
        for i, row in enumerate(s['values'], start=1):
            if len(row) != ncols:
                F.add('expected_shape', {'sheet': s['name'], 'row': i, 'columns': len(row), 'expected_columns': ncols})
    header_checks = {'expected_file_main_row1_is_17_headers': exp_rows.get(SHEETS[0], [[]])[0] == HEADERS,
                     'expected_file_components_row1_is_17_headers': exp_rows.get(SHEETS[2], [[]])[0] == HEADERS}

    wb_f, order_f, sheets_f = read_openpyxl(xlsx, data_only=False)
    _, order_d, sheets_d = read_openpyxl(xlsx, data_only=True)
    raw = read_raw(xlsx)
    readers = {'openpyxl_formulas': (order_f, {k: v['cells'] for k, v in sheets_f.items()}),
               'openpyxl_data_only': (order_d, {k: v['cells'] for k, v in sheets_d.items()}),
               'raw_ooxml': (raw['order'], raw['sheets'])}
    per_reader = {}
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
    for name, sh in sheets_f.items():
        for (r, c), (v, dt) in sh['cells'].items():
            if dt == 'f':
                F.add('formula', {'reader': 'openpyxl_formulas', 'sheet': name, 'cell': f'{col_letters(c)}{r}'})
            if dt == 'e':
                F.add('error_cell_type', {'reader': 'openpyxl_formulas', 'sheet': name, 'cell': f'{col_letters(c)}{r}'})
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
    bad_parts = [p for p in raw['parts'] if re.search(r'(?:vbaProject|externalLink|connections\.xml|calcChain)', p)]
    for p in bad_parts:
        F.add('unexpected_part', {'part': p})

    # readers agree with each other on every populated cell
    for name in SHEETS:
        a = {k: v[0] for k, v in readers['openpyxl_formulas'][1].get(name, {}).items() if v[0] is not None}
        b = {k: v[0] for k, v in readers['openpyxl_data_only'][1].get(name, {}).items() if v[0] is not None}
        c_ = {k: v[0] for k, v in readers['raw_ooxml'][1].get(name, {}).items() if v[0] is not None}
        for key in set(a) | set(b) | set(c_):
            va, vb, vc = a.get(key), b.get(key), c_.get(key)
            if not (va == vb == vc and kind(va) == kind(vb) == kind(vc)):
                F.add('reader_disagreement', {'sheet': name, 'cell': f'{col_letters(key[1])}{key[0]}',
                                              'openpyxl_formulas': va, 'openpyxl_data_only': vb, 'raw_ooxml': vc})

    for name, cells in readers['openpyxl_formulas'][1].items():
        check_limits(name, cells, F)

    fmt_checked = None
    if formatting:
        fmt_checked = check_formatting(wb_f, exp_rows, F)

    error_text = []
    for name, cells in readers['raw_ooxml'][1].items():
        for (r, c), (v, _) in sorted(cells.items()):
            if isinstance(v, str) and any(t in v for t in ERROR_LITERALS):
                error_text.append({'sheet': name, 'cell': f'{col_letters(c)}{r}'})

    value_checks = ('value_type_mismatch', 'unexpected_populated_cell', 'sheet_order', 'header_row', 'formula', 'error_cell_type',
                    'defined_names', 'external_relationship', 'unexpected_part', 'reader_disagreement', 'excel_limit',
                    'expected_shape', 'integrity')
    value_fail = sum(F.count(k) for k in value_checks)
    fmt_fail = F.count('formatting')
    status = 'SAVED_ALL_CELL_VALUE_TYPE_PASS' if value_fail == 0 and (not formatting or fmt_fail == 0) else 'SAVED_QA_FAILED'
    import openpyxl
    return {
        'schema': 'cps.export.saved-qa.v1', 'tool': VERSION, 'status': status,
        'xlsx': {'file': xlsx.name, 'sha256': sha256(xbytes), 'bytes': len(xbytes)},
        'expected_saved_values': {'file': exp_path.name, 'sha256': sha256(ebytes)},
        'writer_receipt_present': receipt is not None,
        'readers': list(readers), 'sheet_order': raw['order'],
        'counts_by_reader': per_reader,
        'totals': {'sheets': len(exp_sheets), 'cells_compared_per_reader': sum(c['checked_cells'] for c in per_reader['raw_ooxml']),
                   'value_type_mismatches': F.count('value_type_mismatch'), 'unexpected_populated_cells': F.count('unexpected_populated_cell'),
                   'formulas': F.count('formula'), 'excel_limit_violations': F.count('excel_limit'),
                   'reader_disagreements': F.count('reader_disagreement'), 'formatting_failures': fmt_fail if formatting else None,
                   'formatting_cells_checked': fmt_checked, 'value_check_failures': value_fail},
        'header_checks': header_checks,
        'excel_limits_checked': EXCEL,
        'literal_error_text_cells': {'count': len(error_text), 'first': error_text[:50],
                                     'note': 'informational, like writer004 ERROR_SCAN: carried text may legitimately contain error text'},
        'findings': F.report(),
        'scope': 'Saved-workbook fidelity to the writer matrix (EXPECTED_SAVED_VALUES.json); not source semantics, not visual QA.',
        'native_excel_validation': False, 'openpyxl': openpyxl.__version__,
    }


def dump(obj):
    text = json.dumps(obj, ensure_ascii=False, indent=2) + '\n'
    try:
        return text.encode('utf-8')
    except UnicodeEncodeError:
        return (json.dumps(obj, ensure_ascii=True, indent=2) + '\n').encode('ascii')


def main(argv=None):
    ap = argparse.ArgumentParser(description='CPS saved workbook QA (read-only)')
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--report')
    ap.add_argument('--no-formatting', action='store_true')
    a = ap.parse_args(argv)
    out_dir = Path(a.output_dir).resolve(strict=True)
    report_path = Path(a.report) if a.report else out_dir / 'SAVED_QA.json'
    before = sha256((out_dir / 'research-draft.xlsx').read_bytes())
    rep = run_qa(out_dir, formatting=not a.no_formatting)
    if sha256((out_dir / 'research-draft.xlsx').read_bytes()) != before:
        rep['status'] = 'SAVED_QA_FAILED'
        rep.setdefault('findings', {})['workbook_changed_during_qa'] = {'count': 1}
    with open(report_path, 'xb') as f:
        f.write(dump(rep))
    print(json.dumps({'status': rep['status'], 'report': str(report_path), **rep['totals']}, ensure_ascii=False))
    return 0 if rep['status'] == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
