"""CPS visual QA renderer (read-only; part of the NOT ADMITTED portable export route).

Converts the saved workbook to PDF with LibreOffice headless in a temporary copy directory,
renders every PDF page to PNG with pdftoppm (fallback: LibreOffice PNG export, first page
only), and writes VISUAL_QA_MANIFEST.json. It produces images reproducibly; the visual QA
judgement is made later by a reviewer looking at the PNGs.

Modes
  fit-width (default)  The temp copy gets print settings only: landscape A3, fit to one page
                       wide, header row repeated on every page, page header = [[sheet name]]
                       (a marker no cell text produces at the top of a page) and page number.
                       These edits are outside <sheetData>; the tool verifies every sheet's
                       <sheetData> bytes are identical to the saved file. Pages are mapped to
                       sheets by the [[sheet name]] marker in the page header.
  exact                The temp copy is byte-identical to the saved file (LibreOffice default
                       pagination; wide sheets split across pages).

Usage
  python3 -I -B visual_qa.py --xlsx /abs/research-draft.xlsx --dest /abs/new-dir [--mode fit-width|exact] [--dpi N (default auto)]
      [--sheets name1,name2] [--sheet NAME ...]   (PNG only for those sheets; rendered.pdf keeps every page)

v3 (writer v2.6, owner decision O33): the main sheet may be named <name> from the job title instead of 未填研究草稿. Pages
map to sheets by the [[sheet name]] marker whatever the name; the manifest records the workbook's sheet order and its main
sheet (the first sheet, the 17-column deliverable). --sheet NAME (repeatable) selects sheets by exact name, so a name that
holds a comma (NFKC turns a fullwidth comma into ',') can be selected; --sheets keeps its comma-separated form.

v4 (writer v2.7, owner decision O38): the deliverable <name>.xlsx is one sheet in the creator's format, with gridlines shown,
no wrapping and fixed row heights. In fit-width mode a sheet whose view shows gridlines (no showGridLines="0") also gets
<printOptions gridLines="1"/>, so the render shows its cell lines as the screen does (recorded in the modifications; sheets
with gridlines off, such as the internal workbook's, get none). possibly_cut_cells lists the string cells of no-wrap cells
whose estimated text width exceeds the column width or that hold a line feed: in Excel such text runs into an empty
neighbour or is cut at a filled one, and a line feed is not shown as a new line. possibly_clipped_cells now considers only
cells that wrap (every cell of the internal workbook, as before).

v4.1 (review of v2.7, N1 and N6): the column-width map takes the first <col> that covers a column, as LibreOffice does;
possibly_cut_cells also lists no-wrap number cells whose General-format text is wider than the column (Excel and LibreOffice then
show fewer digits, an exponent form such as 1E+06, or ####), with kind "number" (string cells have kind "string").
v4.2 (writer v2.8, owner decision O39): possibly_cut_cells estimates text width with the writer's conservative O39 rule
(fit_tenths: in tenths of a column-width unit, 23 per non-ASCII character, 22 per M W m w @ %, 18 per other ASCII capital,
14 per other ASCII character, plus 10; times font size / 12 pt) for strings and for number text alike. The v4.1 estimate
(2 units per wide character, times size / 11) missed values that the maintainer renderer cut with the v2.7 Calibri default
font (a column unit is 5.55 pt there). On a deliverable widened by the writer it lists only cells that hold a line feed and
values beyond Excel's 255 limit: it applies the writer's own rule, so it is not an independent check of the widths; the PNG
review is (checklist item 9).
v4.3 (review of v2.8): the counts follow writer v2.8.1 (24 per non-ASCII, 15 per other ASCII character). --dpi defaults to
auto: 150 dpi, except for a one-sheet workbook whose view shows gridlines (the delivered workbook) in fit-width mode, which is
rendered at 200 dpi times its total A:Q width over the O38 total 330.8, rounded up, at most 400 dpi (N5). The manifest records
the dpi and the rule.
v4.4 (delta review of v2.8.1): counts of writer v2.8.2 (27 per non-ASCII character that is not East Asian wide or full-width,
F1). The dpi cap is 600. A reviewer's viewer that shrinks images to 2000 px shows a whole page reduced whatever the dpi, so each
page of the delivered workbook is also cut into row-major tiles of at most 1900 x 1900 px, overlapping by at least 120 px,
rendered from the PDF at the page dpi (manifest images[].tiles and tiles). At full size a tile shows CJK body glyphs of about
15 px up to a total A:Q width of about 990; tiles.legibility_bound_exceeded flags a sheet whose glyphs are smaller than 9.2 px
(the v2.7 render as seen on the Dot) (F3; v4.4 inferred it from a width of 1650, v4.5 measures it). A non-finite width counts as the default width (F5).
v4.5 (second delta review of v2.8.x): LibreOffice halves its fit-width scale above a total A:Q width of about 1275, so the
legibility flag is measured, not inferred from the width: the smallest per-page median height of the CJK words (all words when
a page has none) in the PDF text layer, in px at the render dpi, must be at least 9.2 (G1); without pdftotext the flag falls back
to a total width above 1270. A width above 255 counts as 255 (G3). Width estimate scope (writer v2.8.2): the counts cover every
Big5 character and the printable ASCII as measured in both LibreOffice environments; a few characters outside Big5 are wider
than their count (README, O39), and the PNG review is their check.

What the render does not show (v2, review S4; also in the manifest limitations): numbers display in the
General format, so the stored binary64 precision is not visible; a row taller than a printed page is
clipped (LibreOffice does not split a row across pages); complete_render means every page was rendered,
not that all text is visible. possibly_clipped_cells in the manifest lists the cells whose estimated
wrapped text height exceeds the Excel maximum row height (409 pt), from the saved workbook itself.
Never re-save the workbook with LibreOffice (or any application) for QA: QA runs on the writer's bytes.
"""
import argparse, datetime, hashlib, json, math, os, re, shutil, struct, subprocess, sys, tempfile, unicodedata, zipfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

sys.dont_write_bytecode = True

VERSION = 'cps-export-visual-qa.v4.5'
HEADER_MARKER = '[[{}]]'                 # page header text: [[sheet name]] (review N1)
EXCEL_MAX_ROW_HEIGHT_PT = 409.0          # Excel row-height limit; also far below one A3 page in LibreOffice
LINE_HEIGHT_PT = 15.0                    # approximate line height of 11 pt text with the CJK fallback font
DEFAULT_COLUMN_WIDTH = 8.43
CLIP_LIST_CAP = 200
MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


class RenderError(Exception):
    pass


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def run(cmd, timeout, env=None):
    p = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def version(cmd):
    try:
        code, out, err = run(cmd, 60)
        text = (out.strip() or err.strip())
        return text.splitlines()[0] if text else None
    except (OSError, subprocess.SubprocessError) as e:
        return 'unavailable: ' + type(e).__name__


def png_size(b):
    if b[:8] != b'\x89PNG\r\n\x1a\n':
        raise RenderError('NOT_A_PNG')
    return struct.unpack('>II', b[16:24])


# ------------------------------------------------------------------ print-settings copy
def sheet_parts(z):
    import xml.etree.ElementTree as ET
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    rels = {r.attrib['Id']: r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    out = []
    for sh in wb.find('{%s}sheets' % MAIN_NS):
        t = rels[sh.attrib['{%s}id' % REL_NS]]
        out.append((sh.attrib['name'], t.lstrip('/') if t.startswith('/') else 'xl/' + t))
    return out


def sheet_data(xml):
    i, j = xml.find('<sheetData'), xml.find('</sheetData>')
    if i < 0:
        return ''
    return xml[i:j + len('</sheetData>')] if j >= 0 else xml[i:xml.find('>', i) + 1]


def shows_gridlines(xml):
    """v4: the sheet view shows gridlines (no showGridLines="0"/"false" on any sheetView)."""
    return re.search(r'<sheetView\b[^>]*\bshowGridLines="(?:0|false)"', xml) is None


def patch_sheet(xml):
    """Insert fit-to-width landscape A3 page setup and a sheet-name header (outside sheetData); v4: printed gridlines for a
    sheet whose view shows them."""
    if '<pageSetup' in xml or '<headerFooter' in xml:
        raise RenderError('SHEET_ALREADY_HAS_PAGE_SETUP')
    if '<printOptions' in xml:
        raise RenderError('SHEET_ALREADY_HAS_PRINT_OPTIONS')
    grid = '<printOptions gridLines="1"/>' if shows_gridlines(xml) else ''
    if '<pageSetUpPr/>' in xml:
        xml = xml.replace('<pageSetUpPr/>', '<pageSetUpPr fitToPage="1"/>', 1)
    elif '</sheetPr>' in xml:
        if '<pageSetUpPr' in xml:
            raise RenderError('UNEXPECTED_PAGESETUPPR')
        xml = xml.replace('</sheetPr>', '<pageSetUpPr fitToPage="1"/></sheetPr>', 1)
    elif '<sheetPr/>' in xml:
        xml = xml.replace('<sheetPr/>', '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>', 1)
    else:
        m = re.search(r'<worksheet\b[^>]*>', xml)
        xml = xml[:m.end()] + '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>' + xml[m.end():]
    setup = ('<pageSetup paperSize="8" orientation="landscape" fitToWidth="1" fitToHeight="0"/>'
             '<headerFooter><oddHeader>&amp;L[[&amp;A]]&amp;RPage &amp;P / &amp;N</oddHeader></headerFooter>')
    m = re.search(r'<pageMargins\b[^>]*/>', xml)
    if m:
        xml = xml[:m.start()] + grid + xml[m.start():m.end()] + setup + xml[m.end():]
    else:
        pm = '<pageMargins left="0.4" right="0.4" top="0.6" bottom="0.4" header="0.3" footer="0.3"/>'
        k = xml.rfind('</worksheet>')
        xml = xml[:k] + grid + pm + setup + xml[k:]
    return xml


def patch_workbook(xml, names):
    titles = ''.join('<definedName name="_xlnm.Print_Titles" localSheetId="%d">%s</definedName>'
                     % (i, xml_escape("'" + n.replace("'", "''") + "'!$1:$1")) for i, n in enumerate(names))
    if '_xlnm.Print_Titles' in xml:
        raise RenderError('WORKBOOK_ALREADY_HAS_PRINT_TITLES')
    if '<definedNames/>' in xml:
        return xml.replace('<definedNames/>', '<definedNames>' + titles + '</definedNames>', 1)
    if '</definedNames>' in xml:
        return xml.replace('</definedNames>', titles + '</definedNames>', 1)
    return xml.replace('</sheets>', '</sheets><definedNames>' + titles + '</definedNames>', 1)


def make_fit_width_copy(src, dst):
    changes = []
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        parts = sheet_parts(zin)
        names = [n for n, _ in parts]
        targets = {p: n for n, p in parts}
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename in targets:
                xml = data.decode('utf-8')
                new = patch_sheet(xml)
                if sheet_data(new) != sheet_data(xml):
                    raise RenderError('SHEETDATA_CHANGED_BY_PRINT_PATCH')
                data = new.encode('utf-8')
                changes.append({'part': info.filename, 'sheet': targets[info.filename],
                                'inserted': 'pageSetUpPr fitToPage=1; pageSetup A3 landscape fitToWidth=1 fitToHeight=0; headerFooter [[&A]] / &P'
                                            + ('; printOptions gridLines=1 (the sheet view shows gridlines)' if shows_gridlines(xml) else '')})
            elif info.filename == 'xl/workbook.xml':
                data = patch_workbook(data.decode('utf-8'), names).encode('utf-8')
                changes.append({'part': info.filename, 'inserted': 'definedName _xlnm.Print_Titles $1:$1 per sheet'})
            zi = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type, zi.create_system, zi.external_attr = zipfile.ZIP_DEFLATED, 0, 0
            zout.writestr(zi, data)
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(dst) as b:
        for _, part in sheet_parts(a):
            if sheet_data(a.read(part).decode('utf-8')) != sheet_data(b.read(part).decode('utf-8')):
                raise RenderError('SHEETDATA_VERIFY_FAILED')
    return names, changes


def map_pages(text, names, pages=None):
    """Page number -> sheet name from the [[sheet name]] marker in the page header (first 3 text lines of each page);
    None when no marker of a known sheet is found. Cell text cannot be mistaken for the header."""
    out = {}
    chunks = text.split('\f')
    known = set(names)
    for n, chunk in enumerate(chunks[:pages] if pages else chunks, start=1):
        head = '\n'.join(chunk.strip('\n').splitlines()[:3])
        hits = [m for m in re.findall(r'\[\[(.+?)\]\]', head) if m in known]
        out[n] = hits[0] if hits else None
    return out


# ------------------------------------------------------------------ cells that may be clipped (review S4)
FIT_TENTHS_NON_ASCII, FIT_TENTHS_BROAD, FIT_TENTHS_CAPITAL, FIT_TENTHS_OTHER, FIT_TENTHS_PAD = 24, 22, 18, 15, 10
FIT_TENTHS_NON_ASCII_OTHER = 27                 # v4.4: writer v2.8.2 (non-ASCII, not East Asian wide or full-width)
FIT_BROAD = 'MWmw@%'


def fit_tenths_text(text):
    """v4.2: visual QA's copy of the writer's O39 width estimate for one cell text at 12 pt (line breaks count nothing)."""
    if text == '':
        return 0
    t = 0
    for ch in text:
        if ch in '\r\n':
            continue
        if ord(ch) > 0x7e:
            t += FIT_TENTHS_NON_ASCII if unicodedata.east_asian_width(ch) in 'WF' else FIT_TENTHS_NON_ASCII_OTHER
        elif ch in FIT_BROAD:
            t += FIT_TENTHS_BROAD
        elif 'A' <= ch <= 'Z':
            t += FIT_TENTHS_CAPITAL
        else:
            t += FIT_TENTHS_OTHER
    return t + FIT_TENTHS_PAD


def _text_units(line):
    return sum(2 if unicodedata.east_asian_width(ch) in 'WF' else 1 for ch in line)


def estimated_lines(text, width):
    usable = max(1.0, width)
    return sum(max(1, math.ceil(_text_units(line) / usable)) for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'))


def cell_styles(z):
    """v4: per cellXfs index, (wraps, font size in points) from xl/styles.xml; index 0 when a cell has no s attribute."""
    import xml.etree.ElementTree as ET
    m = '{%s}' % MAIN_NS
    if 'xl/styles.xml' not in z.namelist():
        return {}
    st = ET.fromstring(z.read('xl/styles.xml'))
    sizes = []
    for font in st.iterfind(m + 'fonts/' + m + 'font'):
        sz = font.find(m + 'sz')
        try:
            sizes.append(float(sz.attrib.get('val')) if sz is not None else 11.0)
        except (TypeError, ValueError):
            sizes.append(11.0)
    out = {}
    for k, xf in enumerate(st.iterfind(m + 'cellXfs/' + m + 'xf')):
        al = xf.find(m + 'alignment')
        wraps = al is not None and al.attrib.get('wrapText') in ('1', 'true')
        horizontal = al.attrib.get('horizontal') if al is not None else None
        try:
            size = sizes[int(xf.attrib.get('fontId', 0))]
        except (IndexError, ValueError):
            size = 11.0
        out[k] = (wraps, size, horizontal)
    return out


def _string_cells(z, root, shared, m):
    for c in root.iter(m + 'c'):
        t = c.attrib.get('t')
        if t == 'inlineStr':
            text = ''.join(x.text or '' for x in c.iter(m + 't'))
        elif t == 's' and c.find(m + 'v') is not None:
            text = shared[int(c.find(m + 'v').text)]
        else:
            continue
        yield c, text


def _col_no(ref):
    col_no = 0
    for ch in re.match(r'[A-Z]*', ref).group(0):
        col_no = col_no * 26 + ord(ch) - 64
    return col_no


def possibly_cut_cells(xlsx):
    """v4 (O38): no-wrap string cells whose text may not show in full. v4.2/v4.3: flagged when the O39 estimated text width
    (fit_tenths_text, scaled by font size / 12 pt) exceeds the column width, or when the text holds a line feed (not shown
    as a new line without wrapping). neighbours_filled says whether the cells beside it hold anything: Excel lets text run into
    empty neighbours (both sides for centred text) and cuts it at a filled one. Heuristic; the stored values are checked by
    saved_qa.py."""
    import xml.etree.ElementTree as ET
    m = '{%s}' % MAIN_NS
    flagged, checked, checked_numbers = [], 0, 0
    with zipfile.ZipFile(xlsx) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(t.text or '' for t in si.iter(m + 't')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        styles = cell_styles(z)
        for name, part in sheet_parts(z):
            root = ET.fromstring(z.read(part))
            widths = {}
            for col in root.iter(m + 'col'):
                for k in range(int(col.attrib.get('min', 1)), int(col.attrib.get('max', 1)) + 1):
                    widths.setdefault(k, float(col.attrib.get('width', DEFAULT_COLUMN_WIDTH)))   # v4.1: the first <col> wins
            filled = {c.attrib.get('r') for c in root.iter(m + 'c') if c.find(m + 'v') is not None or c.find(m + 'is') is not None}
            for c, text in _string_cells(z, root, shared, m):
                wraps, size, horizontal = styles.get(int(c.attrib.get('s', 0) or 0), (False, 11.0, None))
                if wraps:
                    continue
                checked += 1
                ref = c.attrib.get('r', '')
                col_no, row = _col_no(ref), re.sub(r'^[A-Z]*', '', ref)
                w = widths.get(col_no, DEFAULT_COLUMN_WIDTH)
                lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
                est = fit_tenths_text(text) * size / 12.0 / 10.0          # v4.2: the O39 estimate, in column-width units
                if est > w or len(lines) > 1:
                    def letters(n):
                        out = ''
                        while n:
                            n, r_ = divmod(n - 1, 26)
                            out = chr(65 + r_) + out
                        return out
                    left = letters(col_no - 1) + row if col_no > 1 else None
                    right = letters(col_no + 1) + row
                    flagged.append({'sheet': name, 'cell': ref, 'kind': 'string', 'chars': len(text), 'line_feeds': len(lines) - 1,
                                    'column_width': w, 'estimated_width': round(est, 2), 'horizontal': horizontal,
                                    'neighbours_filled': {'left': left in filled if left else None, 'right': right in filled}})
            for c in root.iter(m + 'c'):          # v4.1 (review N1): numbers wider than their column
                v = c.find(m + 'v')
                if c.attrib.get('t', 'n') != 'n' or v is None or not v.text:
                    continue
                wraps, size, horizontal = styles.get(int(c.attrib.get('s', 0) or 0), (False, 11.0, None))
                if wraps:
                    continue
                checked_numbers += 1
                ref = c.attrib.get('r', '')
                w = widths.get(_col_no(ref), DEFAULT_COLUMN_WIDTH)
                est = fit_tenths_text(v.text) * size / 12.0 / 10.0     # v4.2: the O39 estimate
                if est > w:
                    flagged.append({'sheet': name, 'cell': ref, 'kind': 'number', 'chars': len(v.text), 'line_feeds': 0, 'column_width': w,
                                    'estimated_width': round(est, 2), 'horizontal': horizontal, 'neighbours_filled': None})
    return {'count': len(flagged), 'first': flagged[:CLIP_LIST_CAP], 'no_wrap_string_cells_checked': checked,
            'no_wrap_number_cells_checked': checked_numbers,
            'criterion': ('v4.2: no-wrap string or number cell whose O39 estimated width (tenths of a unit: 23 per non-ASCII '
                          'character, 22 per M W m w @ %, 18 per other ASCII capital, 14 per other ASCII character, plus 10; times '
                          'font size / 12 pt) exceeds the column width, or a string that holds a line feed (a number too wide is '
                          'shown with fewer digits, as 1E+06, or as ####)'),
            'note': ('Heuristic. In Excel the text of these cells runs into empty neighbours and is cut at a filled one; a line feed '
                     'shows as one line. Check their values in SAVED_QA.json / the saved workbook, not in the PNGs.')}


def possibly_clipped_cells(xlsx):
    """Cells of the saved workbook whose estimated wrapped text height exceeds the Excel maximum row height: in Excel
    their text is cut at 409 pt; in the render a row taller than one page is cut at the page. Heuristic (wide East Asian
    characters count as 2 column-width units, LINE_HEIGHT_PT per line); the stored values are checked by saved_qa.py.
    v4: only cells that wrap (a cell that does not wrap is in possibly_cut_cells instead)."""
    import xml.etree.ElementTree as ET
    m = '{%s}' % MAIN_NS
    flagged, checked = [], 0
    with zipfile.ZipFile(xlsx) as z:
        styles = cell_styles(z)
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(t.text or '' for t in si.iter(m + 't')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        for name, part in sheet_parts(z):
            root = ET.fromstring(z.read(part))
            widths = {}
            for col in root.iter(m + 'col'):
                for k in range(int(col.attrib.get('min', 1)), int(col.attrib.get('max', 1)) + 1):
                    widths.setdefault(k, float(col.attrib.get('width', DEFAULT_COLUMN_WIDTH)))   # v4.1: the first <col> wins
            for c, text in _string_cells(z, root, shared, m):
                if styles and not styles.get(int(c.attrib.get('s', 0) or 0), (True,))[0]:
                    continue                                 # v4: a cell that does not wrap (possibly_cut_cells)
                checked += 1
                ref = c.attrib.get('r', '')
                letters = re.match(r'[A-Z]*', ref).group(0)
                col_no = 0
                for ch in letters:
                    col_no = col_no * 26 + ord(ch) - 64
                w = widths.get(col_no, DEFAULT_COLUMN_WIDTH)
                lines = estimated_lines(text, w)
                if lines * LINE_HEIGHT_PT > EXCEL_MAX_ROW_HEIGHT_PT:
                    flagged.append({'sheet': name, 'cell': ref, 'chars': len(text), 'line_feeds': text.count('\n'),
                                    'column_width': w, 'estimated_lines': lines, 'estimated_height_pt': lines * LINE_HEIGHT_PT})
    return {'count': len(flagged), 'first': flagged[:CLIP_LIST_CAP], 'string_cells_checked': checked,
            'criterion': (f'estimated wrapped height > {EXCEL_MAX_ROW_HEIGHT_PT:g} pt (Excel maximum row height): lines = sum over the '
                          f'cell\'s line-feed-separated lines of ceil(width units / column width), wide East Asian characters = 2 units; '
                          f'{LINE_HEIGHT_PT:g} pt per line'),
            'note': ('Heuristic. Text of these cells may be cut in Excel (409 pt row limit) and in the render (a row taller than one '
                     'printed page is cut at the page). Check their values in SAVED_QA.json / the saved workbook, not in the PNGs.')}


# ------------------------------------------------------------------ rendering
O38_MIN_WIDTHS = [16.1, 23.1, 21.3, 81.9, 6.9, 8.3, 12.9, 13.0, 12.3, 13.0, 21.4, 11.0, 24.1, 34.1, 10.3, 13.0, 8.1]
O38_TOTAL_WIDTH = round(sum(O38_MIN_WIDTHS), 6)   # v4.3: 330.8, the sum of the O38 minimum widths A:Q
AUTO_DPI_BASE, AUTO_DPI_DELIVERABLE, AUTO_DPI_MAX = 150, 200, 600     # v4.4 (F3): cap 600 (v4.3: 400)
TILE_MAX_PX, TILE_OVERLAP_PX = 1900, 120      # v4.4 (F3): tiles of a delivered page, at most 1900 px each way, overlapping
LEGIBLE_GLYPH_PX_MIN = 9.2                    # v4.5 (G1): the CJK body glyph height a tile must show, in px
LEGIBLE_TOTAL_WIDTH_MAX = 1270.0             # v4.5 (G1): fallback bound without pdftotext (LibreOffice halves its scale above ~1275)


def delivered_shape(xlsx, mode):
    """v4.4: (True, total A:Q width) for a one-sheet workbook whose view shows gridlines (the delivered workbook) rendered in
    fit-width mode; otherwise (False, reason). A non-finite or unparsable width counts as the default width (F5)."""
    if mode != 'fit-width':
        return False, 'not fit-width'
    with zipfile.ZipFile(xlsx) as z:
        parts = sheet_parts(z)
        if len(parts) != 1:
            return False, 'not a one-sheet workbook'
        xml = z.read(parts[0][1]).decode('utf-8')
    if not shows_gridlines(xml):
        return False, 'gridlines off'
    widths = {}
    for m_ in re.finditer(r'<col\b([^>]*)/?>', xml):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m_.group(1)))
        try:
            lo, hi, w = int(a.get('min', 1)), int(a.get('max', 1)), float(a.get('width', DEFAULT_COLUMN_WIDTH))
        except ValueError:
            continue
        if not math.isfinite(w) or w < 0:
            w = DEFAULT_COLUMN_WIDTH
        w = min(w, 255.0)                          # v4.5 (G3): Excel's maximum; a larger width cannot be shown
        for k in range(max(1, lo), min(hi, 17) + 1):
            widths.setdefault(k, w)                # the first <col> that covers a column, as LibreOffice
    return True, sum(widths.get(k, DEFAULT_COLUMN_WIDTH) for k in range(1, 18))


def auto_dpi(xlsx, mode):
    """v4.3 (review of v2.8, N5): 150 dpi, except for the delivered workbook in fit-width mode: 200 dpi times its total A:Q
    column width over the O38 total, rounded up; v4.4: at most 600 (F3)."""
    shaped, info = delivered_shape(xlsx, mode)
    if not shaped:
        return AUTO_DPI_BASE, f'auto: 150 ({info})'
    dpi = min(AUTO_DPI_MAX, max(AUTO_DPI_DELIVERABLE, math.ceil(AUTO_DPI_DELIVERABLE * info / O38_TOTAL_WIDTH)))
    return dpi, f'auto: delivered one-sheet workbook, total A:Q width {round(info, 2)} -> {dpi} dpi (200 x total / 330.8, 200..600)'


def measured_glyph_px(pdf, dpi, timeout=600):
    """v4.5 (G1): the smallest per-page median word-box height of the CJK words (all words on a page without CJK) in the PDF
    text layer, in px at dpi; None when pdftotext gives no words."""
    code, text, _ = run(['pdftotext', '-bbox', str(pdf), '-'], timeout)
    if code != 0:
        return None
    meds = []
    for page in re.findall(r'<page\b.*?</page>', text, re.S):
        words = re.findall(r'<word xMin="[^"]*" yMin="([^"]*)" xMax="[^"]*" yMax="([^"]*)">([^<]*)</word>', page)
        cjk = [float(b) - float(a) for a, b, w_ in words if any(0x3400 <= ord(c) <= 0x9fff or 0xf900 <= ord(c) <= 0xfaff or ord(c) >= 0x20000
                                                                for c in w_)]
        hs = sorted(cjk or [float(b) - float(a) for a, b, w_ in words])
        if hs:
            meds.append(hs[len(hs) // 2])
    return round(min(meds) * dpi / 72.0, 2) if meds else None


def tile_boxes(w, h, tmax=TILE_MAX_PX, ov=TILE_OVERLAP_PX):
    """v4.4 (F3): row-major tiles (x, y, width, height) covering a w x h page, each at most tmax px each way, neighbours
    overlapping by at least ov px; the last tile of a row or column is anchored to the page edge."""
    def spans(n):
        if n <= tmax:
            return [(0, n)]
        out, x = [], 0
        while x + tmax < n:
            out.append((x, tmax))
            x += tmax - ov
        out.append((n - tmax, tmax))
        return out
    return [(x, y, ww, hh) for (y, hh) in spans(h) for (x, ww) in spans(w)]


def render(xlsx, dest, mode='fit-width', dpi=None, soffice='soffice', pdftoppm='pdftoppm', timeout=900, tmp_root=None, sheets=None):
    if not xlsx.is_file():
        raise RenderError('XLSX_MISSING')
    if dpi is None:
        dpi, dpi_rule = auto_dpi(xlsx, mode)
    else:
        dpi_rule = 'given (--dpi)'
    tiled, shape_info = delivered_shape(xlsx, mode)  # v4.4 (F3): the delivered workbook's pages are also tiled
    if dest.exists():
        raise RenderError('DEST_EXISTS')
    before = xlsx.read_bytes()
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    dest.mkdir(parents=False)
    have_pdftoppm = shutil.which(pdftoppm) is not None
    have_pdfinfo = shutil.which('pdfinfo') is not None
    have_pdftotext = shutil.which('pdftotext') is not None
    with tempfile.TemporaryDirectory(prefix='cps_visual_', dir=tmp_root) as tmp:
        tmp = Path(tmp)
        work, profile = tmp / 'in', tmp / 'profile'
        work.mkdir()
        copy = work / 'render-copy.xlsx'
        if mode == 'exact':
            copy.write_bytes(before)
            names, changes = None, []
            with zipfile.ZipFile(xlsx) as z:
                order = [n for n, _ in sheet_parts(z)]
        elif mode == 'fit-width':
            names, changes = make_fit_width_copy(xlsx, copy)
            order = list(names)
        else:
            raise RenderError('UNKNOWN_MODE')
        copy_bytes = copy.read_bytes()
        env = dict(os.environ, HOME=str(tmp), LC_ALL='C.UTF-8', TZ='UTC', SAL_USE_VCLPLUGIN='svp')
        cmd = [soffice, '--headless', '--norestore', '--nolockcheck', '-env:UserInstallation=' + profile.as_uri(),
               '--convert-to', 'pdf', '--outdir', str(work), str(copy)]
        code, out, err = run(cmd, timeout, env)
        pdf = work / 'render-copy.pdf'
        if code != 0 or not pdf.is_file():
            raise RenderError('LIBREOFFICE_PDF_FAILED: ' + (err or out)[-500:])
        pdf_bytes = pdf.read_bytes()
        shutil.copyfile(pdf, dest / 'rendered.pdf')
        pages = None
        if have_pdfinfo:
            c2, info, _ = run(['pdfinfo', str(pdf)], 120)
            m = re.search(r'^Pages:\s+(\d+)', info, re.M)
            pages = int(m.group(1)) if m else None
        page_sheets = {}
        if have_pdftotext and names:
            c4, text, _ = run(['pdftotext', '-layout', str(pdf), '-'], timeout)
            page_sheets = map_pages(text, names, pages)
        selected = None
        if sheets:
            if not page_sheets or not pages:
                raise RenderError('SHEET_FILTER_NEEDS_FIT_WIDTH_MODE_PDFINFO_AND_PDFTOTEXT')
            unknown = [x for x in sheets if x not in names]
            if unknown:
                raise RenderError('UNKNOWN_SHEET: ' + ', '.join(unknown))
            # pages whose sheet could not be read from the page header are kept
            selected = [n for n in range(1, pages + 1) if page_sheets.get(n) in sheets or page_sheets.get(n) is None]
        images = []
        render_cmds = []
        tiles_by_page = {}
        glyph_px = None
        if have_pdftoppm:
            ranges = []
            for n in (selected if selected is not None else []):
                if ranges and ranges[-1][1] == n - 1:
                    ranges[-1][1] = n
                else:
                    ranges.append([n, n])
            for rng in (ranges if selected is not None else [None]):
                rc = [pdftoppm, '-r', str(dpi)] + (['-f', str(rng[0]), '-l', str(rng[1])] if rng else []) + ['-png', str(pdf), str(work / 'page')]
                render_cmds.append(rc)
                c3, o3, e3 = run(rc, timeout, env)
                if c3 != 0:
                    raise RenderError('PDFTOPPM_FAILED: ' + e3[-500:])
            pngs = sorted(work.glob('page-*.png'), key=lambda p: int(p.stem.split('-')[-1]))
            for p in pngs:
                n = int(p.stem.split('-')[-1])
                name = f'page-{n:04d}.png'
                shutil.copyfile(p, dest / name)
                images.append((n, name))
            fallback = False
            if tiled:                                # v4.4 (F3): crops of each delivered page, rendered from the PDF at the same dpi
                (dest / 'tiles').mkdir()
                for n, name in images:
                    pw, ph = png_size((dest / name).read_bytes())
                    page_tiles = []
                    for k, (tx, ty, tw, th) in enumerate(tile_boxes(pw, ph), start=1):
                        stem = work / f'tile-{n}-{k}'
                        rc = [pdftoppm, '-r', str(dpi), '-f', str(n), '-l', str(n), '-x', str(tx), '-y', str(ty), '-W', str(tw),
                              '-H', str(th), '-singlefile', '-png', str(pdf), str(stem)]
                        c5, o5, e5 = run(rc, timeout, env)
                        out_png = stem.with_name(stem.name + '.png')
                        if c5 != 0 or not out_png.is_file():
                            raise RenderError('PDFTOPPM_TILE_FAILED: ' + e5[-500:])
                        tname = f'tiles/page-{n:04d}-tile-{k:02d}.png'
                        shutil.copyfile(out_png, dest / tname)
                        page_tiles.append({'file': tname, 'x': tx, 'y': ty, 'width_px': tw, 'height_px': th})
                    tiles_by_page[n] = page_tiles
                glyph_px = measured_glyph_px(pdf, dpi, timeout) if have_pdftotext else None
        else:
            c3, o3, e3 = run([soffice, '--headless', '--norestore', '-env:UserInstallation=' + profile.as_uri(),
                              '--convert-to', 'png', '--outdir', str(work), str(copy)], timeout, env)
            png = work / 'render-copy.png'
            if c3 != 0 or not png.is_file():
                raise RenderError('LIBREOFFICE_PNG_FAILED: ' + (e3 or o3)[-500:])
            shutil.copyfile(png, dest / 'page-0001.png')
            images.append((1, 'page-0001.png'))
            fallback = True
    after = xlsx.read_bytes()
    if sha256(after) != sha256(before):
        raise RenderError('SAVED_WORKBOOK_CHANGED_DURING_RENDER')
    entries = []
    for n, name in images:
        b = (dest / name).read_bytes()
        w, h = png_size(b)
        entry = {'file': name, 'page': n, 'sheet': page_sheets.get(n), 'sha256': sha256(b), 'bytes': len(b), 'width_px': w, 'height_px': h}
        if n in tiles_by_page:                       # v4.4 (F3)
            for t_ in tiles_by_page[n]:
                tb = (dest / t_['file']).read_bytes()
                tw_, th_ = png_size(tb)
                t_.update(sha256=sha256(tb), bytes=len(tb), png_width_px=tw_, png_height_px=th_)
            entry['tiles'] = tiles_by_page[n]
        entries.append(entry)
    fonts = {q: version(['fc-match', q]) for q in ('Arial', 'Arial:lang=zh-tw', 'sans-serif:lang=zh-tw', '新細明體', 'PMingLiU')}
    try:
        clipped = possibly_clipped_cells(xlsx)
    except Exception as e:                      # noqa: BLE001 - the images stand; the list is then unavailable
        clipped = {'count': None, 'first': [], 'error': repr(e)[:300]}
    try:
        cut = possibly_cut_cells(xlsx)
    except Exception as e:                      # noqa: BLE001
        cut = {'count': None, 'first': [], 'error': repr(e)[:300]}
    manifest = {
        'schema': 'cps.export.visual-qa-manifest.v1', 'tool': VERSION, 'status': 'RENDERED_AWAITING_VISUAL_INSPECTION',
        'visual_inspection_complete': False,
        'reviewer_task': 'An independent reviewer inspects every PNG (all sheets, all rows, all 17 columns of the main and components sheets) and records the judgement separately.',
        'saved_xlsx': {'path': str(xlsx), 'sha256': sha256(before), 'unchanged_after_render': True},
        'mode': mode, 'dpi': dpi, 'dpi_rule': dpi_rule,
        'tiles': ({'max_px': TILE_MAX_PX, 'overlap_px': TILE_OVERLAP_PX, 'count': sum(len(v) for v in tiles_by_page.values()),
                   'total_width': round(shape_info, 2), 'glyph_px_min_page_median': glyph_px,
                   'legibility_bound_exceeded': (glyph_px < LEGIBLE_GLYPH_PX_MIN) if glyph_px is not None else shape_info > LEGIBLE_TOTAL_WIDTH_MAX,
                   'legibility_rule': ('v4.5 (G1): measured; the smallest per-page median CJK word height in the PDF text layer must be '
                                       'at least 9.2 px at the render dpi' if glyph_px is not None else
                                       'v4.5 (G1): fallback without a text layer: total A:Q width above 1270'),
                   'rule': 'v4.4 (F3): each page of the delivered workbook is also cut into row-major tiles of at most 1900 x 1900 px, '
                           'overlapping by at least 120 px, rendered from the PDF at the page dpi; a reviewer whose viewer shrinks '
                           'images to 2000 px sees each tile at full size'} if tiles_by_page else None),
        'render_copy': {'sha256': sha256(copy_bytes), 'identical_to_saved': copy_bytes == before,
                        'sheetData_identical_to_saved': True, 'modifications': changes},
        'pdf': {'file': 'rendered.pdf', 'sha256': sha256(pdf_bytes), 'pages': pages,
                'note': 'PDF bytes carry LibreOffice creation metadata and may differ between runs; PNG pixels are the reproducible artifact.'},
        'pages': len(entries), 'images': entries,
        'sheet_order': order, 'main_sheet': order[0] if order else None,
        'main_sheet_note': ('the first sheet: the 17-column sheet (未填研究草稿, or <name> from the job title under owner decision '
                            'O33). Writer v2.7 (O38): the delivered <name>.xlsx holds only this sheet, in the creator\'s format; '
                            'INTERNAL_QA_WORKBOOK.xlsx holds it with the review and composition sheets'),
        'sheet_filter': sheets or None,
        'complete_render': selected is None and not fallback and (pages is None or len(entries) == pages),
        'page_sheet_mapping': ({str(n): v for n, v in sorted(page_sheets.items())} if page_sheets else None),
        'page_sheet_mapping_basis': ('[[sheet name]] marker read from the rendered page header (fit-width mode only)'
                                     if page_sheets else None),
        'possibly_clipped_cells': clipped,
        'possibly_cut_cells': cut,
        'render_tools': {'libreoffice': version([soffice, '--version']), 'pdftoppm': version([pdftoppm, '-v']) if have_pdftoppm else None,
                         'pdfinfo': version(['pdfinfo', '-v']) if have_pdfinfo else None,
                         'pdftotext': version(['pdftotext', '-v']) if have_pdftotext else None, 'fc-match': fonts,
                         'python': sys.version.split()[0]},
        'commands': {'convert': [x if not x.startswith('-env:') else '-env:UserInstallation=<fresh temp profile>' for x in cmd[:-3]] + ['--outdir', '<temp>', '<temp>/render-copy.xlsx'],
                     'render': ([[x if not x.startswith(str(tmp)) else '<temp>/' + Path(x).name for x in rc] for rc in render_cmds]
                                if render_cmds else 'soffice --convert-to png (first page only)')},
        'limitations': (['pdftoppm unavailable: LibreOffice PNG export renders only the first page.'] if fallback else []) + [
            'LibreOffice rendering, not Excel; Arial is substituted by the font fc-match reports.',
            'Rows without explicit height are sized by LibreOffice at load (writer004 autofitRows is not reproduced); the O38 '
            'deliverable sets every row height (23.25 pt header, 20.45 pt body).',
            'Text of a cell that does not wrap is drawn on one line: it runs into empty neighbours and is cut at a filled one, '
            'and a line feed is not a new line. See possibly_cut_cells (v4).',
            'Numbers display in the General format: the rendered text shows a rounded value (at most about 10 significant digits, '
            'fewer in narrow columns), so the stored binary64 precision (for example 0.30000000000000004 or 5e-324) is not visible. '
            'saved_qa.py checks the stored values.',
            'A row taller than one printed page is clipped: LibreOffice does not split a row across pages, so the text beyond the page '
            'is not rendered. See possibly_clipped_cells.',
            'complete_render means that every PDF page was rendered to a PNG; it does not mean that all text of every cell is visible.',
            'Never re-save the workbook with LibreOffice (or any application) for QA: visual QA renders a temporary copy and never '
            'changes the saved file, and saved QA must run on the writer\'s bytes.',
        ] + (['--sheets filter: PNGs cover only the selected sheets; rendered.pdf keeps every page.'] if sheets else []) + (['fit-width mode: the rendered copy adds print settings that the saved workbook does not contain.'] if mode == 'fit-width' else []),
        'started': started, 'ended': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with open(dest / 'VISUAL_QA_MANIFEST.json', 'x', encoding='utf-8') as f:
        f.write(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description='CPS visual QA renderer (read-only)')
    ap.add_argument('--xlsx', required=True)
    ap.add_argument('--dest', required=True)
    ap.add_argument('--mode', choices=('fit-width', 'exact'), default='fit-width')
    ap.add_argument('--dpi', type=int, default=None, help='v4.3: default auto (150; the delivered workbook 200..400 by its width)')
    ap.add_argument('--soffice', default='soffice')
    ap.add_argument('--pdftoppm', default='pdftoppm')
    ap.add_argument('--timeout', type=int, default=900)
    ap.add_argument('--tmp-root')
    ap.add_argument('--sheets', help='comma-separated sheet names to render as PNG (fit-width mode); default all')
    ap.add_argument('--sheet', action='append', help='v3: one sheet name to render as PNG, exact (repeatable; for names with a comma)')
    a = ap.parse_args(argv)
    sheets = ([x for x in a.sheets.split(',') if x] if a.sheets else []) + list(a.sheet or [])
    sheets = list(dict.fromkeys(sheets)) or None
    try:
        m = render(Path(a.xlsx).resolve(strict=True), Path(a.dest).absolute(), a.mode, a.dpi, a.soffice, a.pdftoppm, a.timeout, a.tmp_root, sheets)
    except (RenderError, subprocess.SubprocessError, OSError) as e:
        sys.stderr.write(json.dumps({'status': 'RENDER_FAILED', 'error': str(e)[:1000]}) + '\n')
        return 1
    print(json.dumps({'status': m['status'], 'pages_rendered': m['pages'], 'pdf_pages': m['pdf']['pages'], 'complete_render': m['complete_render'],
                      'mode': m['mode'], 'dest': a.dest}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
