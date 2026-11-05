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

v4 (third review): G1 the 8 parts that are byte-constant in every writer output (styles.xml, workbook.xml, theme1.xml,
[Content_Types].xml, both rels, both docProps) are pinned by sha256 (finding pinned_part), and every element of every
worksheet must be in the transitional SpreadsheetML main namespace, by exact tag (finding element_namespace; the
structure checks compare exact tags, so a Strict-namespace or foreign element never matches an allowed name).
G2 the node binary: with --checker-node /abs/node and --checker-node-sha256 HEX, the binary's sha256 is verified before
any node call and every node call (the writer004 check, and the writer rerun, which gets it by absolute path) runs it;
the value is never taken from the receipt or from PATH. expected_provenance records the realpath and sha256 of the node
of the writer004 check and of the rerun (from the rerun receipt, checked against the checker node), and the receipt's
own node claim (information only). Without --checker-node (--node, default node from PATH) the run is not CPS evidence.
G3 receipt claims: the delivered receipt's deterministic fields (mode, relaxations without the route port path,
cross_check, expected_saved_values, matrices_sha256, sheets, writer, writer_files, status, admitted) must equal the
rerun receipt's (for a receipt that says v1: mode v1 and relaxations {"applied": false, "scanned": false}, which a v1
run of a carrier without O13/R57 writes; finding receipt_claim_mismatch, naming the fields); expected_provenance records
the rerun's relaxation classes and documented cells. Other receipt fields are the producer's claim, not evidence.
v5 (writer v2.6, owner decisions O33-O34): the workbook file and main-sheet names are re-derived here from the receipt's
deliverable.job_title (derive_deliverable, this module's own implementation of the writer's rule; without a job title the
v2.5 names research-draft.xlsx and 未填研究草稿), never taken from the receipt: the workbook read is <output-dir>/<derived file>,
its sheets must be the derived names in order, the receipt's deliverable fields and output_xlsx.file must equal the
derivation, and no other .xlsx may be in the output directory (finding deliverable_name). EXPECTED_SAVED_VALUES.json keeps
writer004's sheet names; each is compared with the workbook sheet the derived mapping names. xl/workbook.xml, the only part
that varies with the sheet name, is checked against a pinned template with the XML-attribute-escaped derived sheet name
substituted, byte for byte (finding pinned_template); the other 7 constant parts keep their sha256 pins (styles.xml re-pinned
for O34). The provenance rerun gets --job-title=<the receipt's title> when it has one, and its receipt's deliverable is a
compared claim. Formatting: G and H (單價, 複價) body cells have no fill, like every body cell (O34).
v6 (writer v2.7, owner decision O38): a titled output holds two workbooks. INTERNAL_QA_WORKBOOK.xlsx (the derived
qa_workbook_file) is the four-sheet workbook: every check above runs on it unchanged, and the receipt's output_xlsx names it.
<name>.xlsx (the derived xlsx_file) is the deliverable: one sheet <name> in the creator's format (receipt deliverable_xlsx).
The deliverable is checked by check_deliverable: its own 9-part package (DELIVERABLE_PARTS; 7 parts pinned by sha256, 4 of them
the same bytes as the internal workbook's, and xl/workbook.xml equal to its one-sheet template with the escaped derived name),
the same worksheet, cell and font structure checks (sheetView without showGridLines, so gridlines show, and exactly the
header-row pane; row heights 23.25 and 20.45 only), its cells against the main sheet of EXPECTED_SAVED_VALUES.json with the
three readers (which must agree), no formula, error cell, defined name or external relationship, and (formatting) the O38
format cell by cell. Its findings carry "workbook": "deliverable". The receipt's deliverable_xlsx is compared with the rerun's
(receipt claims), its sha256 with the file, and the provenance rerun byte-compares the deliverable too. An untitled output
has no deliverable (receipt deliverable_xlsx null) and is checked exactly as in v5.
v6.1 (review of v2.7, W1 and N3): every worksheet's <cols> must hold exactly one <col> per column, in order, with
min = max = the column, customWidth="1" and the pinned width (WIDTHS per internal sheet, DELIVERY widths for the deliverable):
LibreOffice uses the first <col> that covers a column, openpyxl the last, and openpyxl gives a column without width its
default, so a leading wide-range <col> or a dropped one passed the openpyxl width check. The workbooks, EXPECTED_SAVED_VALUES.json
and WRITER_RECEIPT.json must be regular files in the output directory, not symbolic links (finding integrity).
Self-contained: it does not import the writer (the provenance rerun runs it as a separate process).

Usage
  python3 -I -B saved_qa.py --output-dir /abs/writer-output [--report /abs/SAVED_QA.json] [--no-formatting]
      [--carrier /abs/carrier.json --writer-dir /abs/writer-dir
       [--checker-node /abs/node --checker-node-sha256 HEX | --node node]]
Default report: <output-dir>/SAVED_QA.json (created; must not exist). Exit 0 only on PASS.
"""
import argparse, copy, hashlib, json, math, os, re, shutil, subprocess, sys, tempfile, unicodedata, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.dont_write_bytecode = True

VERSION = 'cps-export-saved-qa.v6.1'
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
MAIN_PREFIX = '{%s}' % NS['m']
# v4 (third review G1): the parts that are byte-constant in every writer output (openpyxl 3.1.5; docProps/core.xml holds
# the writer's fixed 1980-01-01T00:00:00Z created/modified, docProps/app.xml the openpyxl version). Verified on every
# output of the test suite (test g_pinned_parts_constant_in_every_output) and of the third review's runs.
# v5 (writer v2.6): styles.xml re-pinned (O34: no G/H fill, so one fill and one cell format fewer); xl/workbook.xml holds the
# main sheet's name (O33) and moved to PINNED_TEMPLATES. docProps/app.xml holds no sheet name (openpyxl 3.1.5 writes no
# TitlesOfParts), so it keeps its v4 byte pin, the same bytes in titled and untitled outputs.
PINNED_PARTS = {
    '[Content_Types].xml': 'd734b6624e76225b3efeebddad13bc1a2323d1cf0eaa639dee513d2249a6d5ef',
    '_rels/.rels': 'c545941ba36c15fcdce4ae4568c663f3ced1a2226ad5082d3fd66b178bfac11a',
    'docProps/app.xml': '209fca6b00afe72a5029754b94be5953d8f16d96f67130325566b9366ad4ccc5',
    'docProps/core.xml': 'c5757c5cc9ccb0c26118443a2f1e1c6ced3dc5c409fc0738cae5ef69aa8548b1',
    'xl/_rels/workbook.xml.rels': 'ab22e25bdbbd461cf03d0d9e971a0c4558219dbc10d9e46a68c419dee94b2a81',
    'xl/styles.xml': '1a5ff017aafeada8347ec417982f3decacce97bdab69cf504d588a61e863ea9c',
    'xl/theme/theme1.xml': 'd15e8ebf78ef7b9720839d7ae8fdc81a7df5bc24706d8e137df61a5683c358d9',
}
# v5 (O33): xl/workbook.xml must equal this template with MAIN_SHEET_TOKEN replaced by xml_attribute_escape(<derived main
# sheet>), byte for byte. The template is the v4-pinned workbook.xml (cb9bc221...f3ce) with name="未填研究草稿" replaced by
# the token; the template's own sha256 is pinned (the tests check both).
MAIN_SHEET_TOKEN = '@@CPS_MAIN_SHEET@@'
WORKBOOK_TEMPLATE = ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><workbookPr/>'
                     '<workbookProtection/><bookViews>'
                     '<workbookView visibility="visible" minimized="0" showHorizontalScroll="1" showVerticalScroll="1" showSheetTabs="1" tabRatio="600" firstSheet="0" activeTab="0" autoFilterDateGrouping="1"/>'
                     '</bookViews><sheets>'
                     '<sheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" name="@@CPS_MAIN_SHEET@@" sheetId="1" state="visible" r:id="rId1"/>'
                     '<sheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" name="來源與審查" sheetId="2" state="visible" r:id="rId2"/>'
                     '<sheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" name="組成參考" sheetId="3" state="visible" r:id="rId3"/>'
                     '<sheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" name="組成連結" sheetId="4" state="visible" r:id="rId4"/>'
                     '</sheets><definedNames/><calcPr calcId="124519" fullCalcOnLoad="0"/></workbook>')
PINNED_TEMPLATES = {
    'xl/workbook.xml': {'template_sha256': '3b831f50f102d38062f2c4abe30ef190f8a755daa20f48fe36363afd7b31f13a',
                        'token': MAIN_SHEET_TOKEN, 'substituted': 'the derived main sheet name, XML-attribute-escaped (xml_attribute_escape)'},
}
# v6 (writer v2.7, O38): the deliverable <name>.xlsx, one sheet. Its parts: the internal workbook's minus sheets 2-4. Pinned:
# 4 parts with the internal workbook's bytes (_rels/.rels, both docProps, theme1.xml) and 3 of its own (one worksheet in
# [Content_Types].xml and workbook.xml.rels; the O38 styles). xl/workbook.xml: the one-sheet template.
DELIVERABLE_PARTS = tuple(p for p in EXPECTED_PARTS if p not in ('xl/worksheets/sheet2.xml', 'xl/worksheets/sheet3.xml',
                                                                 'xl/worksheets/sheet4.xml'))
DELIVERABLE_PINNED_PARTS = dict(PINNED_PARTS, **{
    '[Content_Types].xml': 'ba5af858089dd3357b4e4408a86694ff0a62ec37f21ef57a3a09544dc0ab18c4',
    'xl/_rels/workbook.xml.rels': '26ad8fcc38d41229833e624496df364492772697ad2e5d6696e1738f05ba225f',
    'xl/styles.xml': '59f01b1510a60a56aaa6fb6654fb998aa80632d30369ae5e76c9a469784fb5f0'})
DELIVERABLE_WORKBOOK_TEMPLATE = ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><workbookPr/>'
                                 '<workbookProtection/><bookViews>'
                                 '<workbookView visibility="visible" minimized="0" showHorizontalScroll="1" showVerticalScroll="1" showSheetTabs="1" tabRatio="600" firstSheet="0" activeTab="0" autoFilterDateGrouping="1"/>'
                                 '</bookViews><sheets>'
                                 '<sheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" name="@@CPS_MAIN_SHEET@@" sheetId="1" state="visible" r:id="rId1"/>'
                                 '</sheets><definedNames/><calcPr calcId="124519" fullCalcOnLoad="0"/></workbook>')
DELIVERABLE_PINNED_TEMPLATES = {
    'xl/workbook.xml': {'template_sha256': '06baba0b2acbe1af0d2b8c215bd95d4ae588fa7072d8003476bbd447f2090b27',
                        'token': MAIN_SHEET_TOKEN, 'substituted': 'the derived main sheet name, XML-attribute-escaped (xml_attribute_escape)'},
}
# v6 (O38): the deliverable format, checked cell by cell (check_deliverable_formatting); saved QA's own copy of the writer's rule.
QA_WORKBOOK_NAME = 'INTERNAL_QA_WORKBOOK.xlsx'
DELIVERY_FORMAT = 'owner_O38_creator_format_v1'
DELIVERY = {'font': '新細明體', 'size': 12, 'header_fill': 'FFC0C0C0', 'border_style': 'thin', 'border_color': 'FF000000',
            'centred': 'EFLMNQ', 'left': 'C', 'header_height': 23.25, 'row_height': 20.45, 'freeze': 'A2',
            'widths': [16.1, 23.1, 21.3, 81.9, 6.9, 8.3, 12.9, 13.0, 12.3, 13.0, 21.4, 11.0, 24.1, 34.1, 10.3, 13.0, 8.1]}
DELIVERY_ROW_HT = {'header': '23.25', 'body': '20.45'}       # the row ht attribute text openpyxl writes
DELIVERY_PANE = {'ySplit': '1', 'topLeftCell': 'A2', 'activePane': 'bottomLeft', 'state': 'frozen'}
DELIVERY_SHEET_VIEW_ATTRS = ('tabSelected', 'workbookViewId')  # no showGridLines: gridlines show
WIDTH_TEXT_RE = re.compile(r'[0-9]+(?:\.[0-9]+)?')


def expected_cols(kind, part):
    """v6.1 (review W1): the pinned widths of a worksheet part, one per column from A; None for a part with no pin."""
    if kind == 'deliverable':
        return DELIVERY['widths'] if part == 'xl/worksheets/sheet1.xml' else None
    return {'xl/worksheets/sheet%d.xml' % (i + 1): WIDTHS[name] for i, name in enumerate(SHEETS)}.get(part)


def cols_ok(cols, want):
    """Exactly one <col> per column 1..len(want), in order: attributes exactly min, max, width, customWidth; min = max = the
    column; customWidth "1"; width plain decimal text within 1e-9 of the pin (openpyxl writes 81.9 as 81.90000000000001)."""
    if len(cols) != len(want):
        return False
    for j, (c, w) in enumerate(zip(cols, want), start=1):
        a = c.attrib
        if tag_name(c) != 'col' or set(a) != {'min', 'max', 'width', 'customWidth'} or a['min'] != str(j) or a['max'] != str(j) \
                or a['customWidth'] != '1' or not WIDTH_TEXT_RE.fullmatch(a['width']) or abs(float(a['width']) - w) > 1e-9:
            return False
    return True


def xml_attribute_escape(name):
    """How lxml (openpyxl 3.1.5 serialises workbook.xml with lxml, UTF-8) writes a sheet name in the double-quoted name attribute:
    & < > " as &amp; &lt; &gt; &quot;; the apostrophe and every other character unchanged, as UTF-8. A derived name holds no
    whitespace, control, surrogate or U+FFFE/U+FFFF character, so no character reference (&#9; &#10; &#13;) occurs."""
    return name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def template_part(part, main_sheet, kind='qa'):
    """kind 'qa': the four-sheet workbook's template (v5); 'deliverable': the one-sheet deliverable's (v6, O38)."""
    t = (PINNED_TEMPLATES if kind == 'qa' else DELIVERABLE_PINNED_TEMPLATES)[part]
    text = WORKBOOK_TEMPLATE if kind == 'qa' else DELIVERABLE_WORKBOOK_TEMPLATE
    if part != 'xl/workbook.xml' or sha256(text.encode('utf-8')) != t['template_sha256'] or text.count(t['token']) != 1:
        raise ValueError('pinned template integrity')
    return text.replace(t['token'], xml_attribute_escape(main_sheet)).encode('utf-8')


# v5 (writer v2.6, owner decision O33): the deliverable name, re-derived here from the receipt's job title. This is saved
# QA's own implementation of the writer's rule (writer_portable.deliverable_record); the tests check that both give the same
# record, or refuse with the same reason, on every test title and on random titles.
PROFILE = 'owner_O33_O34_O38'
XLSX_SUFFIX_NAME = '(未填)'
TITLE_WS_RE = re.compile(r'[\s\ufeff]')                  # str.isspace() characters and U+FEFF
TITLE_DASH_RE = re.compile(r'([0-9]{7}[^-]{0,5})-')      # the first '-' among the 6 characters after the 7-digit case id
TITLE_BAD_RE = re.compile('[\u0000-\u001f\u007f-\u009f\ud800-\udfff\ufffe\uffff]')   # Cc, Cs, U+FFFE, U+FFFF
OOXML_ESCAPE_RE = re.compile(r'_x[0-9A-Fa-f]{4}_')
FILE_FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|]')           # Windows
SHEET_FORBIDDEN_RE = re.compile(r'[:\\/?*\[\]]')          # Excel
DELIVERABLE_FIELDS = ('profile', 'job_title', 'o33_naming_applied', 'normalized_title', 'dash_removed_at', 'name', 'xlsx_file',
                      'main_sheet', 'main_sheet_cut', 'qa_workbook_file', 'deliverable_workbook', 'deliverable_format',
                      'sheet_mapping', 'o34_price_columns_unshaded')


class DeliverableNameError(Exception):
    def __init__(self, reason, **detail):
        super().__init__(reason)
        self.reason, self.detail = reason, detail


def derive_deliverable(title):
    """O33: the workbook file name, the main sheet name and the EXPECTED -> workbook sheet mapping from a job title (None: the
    v2.5 names). Raises DeliverableNameError(reason) where the writer refuses JOB_TITLE_INVALID with that reason."""
    d = {'profile': PROFILE, 'job_title': title, 'o33_naming_applied': title is not None, 'normalized_title': None,
         'dash_removed_at': None, 'name': None, 'xlsx_file': XLSX_NAME, 'main_sheet': SHEETS[0], 'main_sheet_cut': False,
         'qa_workbook_file': XLSX_NAME if title is None else QA_WORKBOOK_NAME, 'deliverable_workbook': title is not None,
         'deliverable_format': None if title is None else DELIVERY_FORMAT}
    if title is not None:
        if not isinstance(title, str):
            raise DeliverableNameError('NOT_A_STRING')
        norm = TITLE_WS_RE.sub('', unicodedata.normalize('NFKC', title))
        if not re.match(r'[0-9]{7}', norm):
            raise DeliverableNameError('CASE_ID_REQUIRED', normalized_title=norm[:100])
        if TITLE_BAD_RE.search(norm):
            raise DeliverableNameError('UNREPRESENTABLE_CHARACTER', code_points=['U+%04X' % ord(c) for c in TITLE_BAD_RE.findall(norm)[:10]])
        m = TITLE_DASH_RE.match(norm)
        base = m.group(1) + norm[m.end():] if m else norm
        name = base + XLSX_SUFFIX_NAME
        xlsx_file = FILE_FORBIDDEN_RE.sub('-', name) + '.xlsx'
        sheet_text = SHEET_FORBIDDEN_RE.sub('-', base)
        keep = min(len(sheet_text), EXCEL['sheet_name_chars'])      # a code point is at least one UTF-16 unit
        while utf16_len(sheet_text[:keep]) > EXCEL['sheet_name_chars'] - utf16_len(XLSX_SUFFIX_NAME):
            keep -= 1
        sheet = sheet_text[:keep] + XLSX_SUFFIX_NAME
        if OOXML_ESCAPE_RE.search(sheet):
            raise DeliverableNameError('LITERAL_OOXML_ESCAPE_SEQUENCE', main_sheet=sheet)
        if len(xlsx_file.encode('utf-8')) > 255:
            raise DeliverableNameError('FILE_NAME_TOO_LONG', utf8_bytes=len(xlsx_file.encode('utf-8')), limit=255)
        d.update(normalized_title=norm, dash_removed_at=m.end() - 1 if m else None, name=name, xlsx_file=xlsx_file,
                 main_sheet=sheet, main_sheet_cut=keep < len(sheet_text))
    d['sheet_mapping'] = [{'expected_saved_values_sheet': n, 'workbook_sheet': d['main_sheet'] if n == SHEETS[0] else n} for n in SHEETS]
    d['o34_price_columns_unshaded'] = True
    return d
# v4 (third review G3): the receipt fields compared with the rerun receipt. A v1 run of a carrier without O13/R57 takes the
# same route as the v2 rerun and writes the same fields except mode and these relaxations.
RECEIPT_CLAIM_FIELDS = ('mode', 'relaxations', 'cross_check', 'expected_saved_values', 'matrices_sha256', 'sheets', 'writer',
                        'writer_files', 'status', 'admitted', 'deliverable', 'deliverable_xlsx')
V1_RELAXATIONS = {'applied': False, 'scanned': False}
SHA256_RE = re.compile(r'[0-9a-f]{64}')
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


class TaggedFindings:
    """v6: findings about the deliverable workbook carry "workbook": "deliverable" (same check names as the internal workbook's)."""
    def __init__(self, F, tag):
        self.F, self.tag = F, tag

    def add(self, check, entry):
        self.F.add(check, dict(entry, workbook=self.tag) if isinstance(entry, dict) else {'workbook': self.tag, 'entry': entry})

    def count(self, check):
        return self.F.count(check)


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


def tag_name(el):
    """v4 (third review G1): an element's name for the structure checks. The local name only when the element is in the
    transitional SpreadsheetML main namespace; otherwise the full tag ('{ns}name', or '{}name' without a namespace), which
    no allowed name equals. (local() is kept for attribute names in the deny check for hidden/zeroHeight.)"""
    t = el.tag if isinstance(el.tag, str) else repr(el.tag)
    if t.startswith(MAIN_PREFIX):
        return t[len(MAIN_PREFIX):]
    return t if t.startswith('{') else '{}' + t


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
def check_structure(path, F, main_sheet=SHEETS[0], kind='qa'):
    """The workbook may hold only what the portable writer produces: no hidden content, no extra parts, no view or
    format element that can hide or alter what a cell shows. main_sheet: the derived main sheet name (v5, O33), substituted
    into the pinned workbook.xml template. kind 'qa': the four-sheet workbook; 'deliverable' (v6, O38): the one-sheet
    deliverable (its parts, pins and template; sheetView without showGridLines and with exactly the header-row pane; its
    row heights). Returns a small summary."""
    deliv = kind == 'deliverable'
    expected_parts = DELIVERABLE_PARTS if deliv else EXPECTED_PARTS
    pinned_parts = DELIVERABLE_PINNED_PARTS if deliv else PINNED_PARTS
    pinned_templates = DELIVERABLE_PINNED_TEMPLATES if deliv else PINNED_TEMPLATES

    def bad(check, **kw):
        F.add(check, kw)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            bad('zip_parts', problem='duplicate zip entry names', names=sorted(n for n in set(names) if names.count(n) > 1))
        for n in sorted(set(names) - set(expected_parts)):
            bad('zip_parts', part=n, problem='part the writer does not produce')
        for n in sorted(set(expected_parts) - set(names)):
            bad('zip_parts', part=n, problem='missing part')
        # v4 (third review G1): the byte-constant parts are pinned by sha256; every zip entry with a pinned name is read,
        # so a duplicate entry is checked too. This covers every styles.xml change (colour tint, fonts in another
        # namespace, ...) that openpyxl and LibreOffice read differently.
        for info in z.infolist():
            if info.filename in pinned_parts:
                h = sha256(z.read(info))
                if h != pinned_parts[info.filename]:
                    bad('pinned_part', part=info.filename, sha256=h, pinned=pinned_parts[info.filename],
                        problem='differs from the bytes every writer output has')
        for n in sorted(set(pinned_parts) - set(names)):
            bad('pinned_part', part=n, problem='missing', pinned=pinned_parts[n])
        # v5 (O33): the part that holds the main sheet's name equals its pinned template with the escaped derived name
        for info in z.infolist():
            if info.filename in pinned_templates:
                want = template_part(info.filename, main_sheet, kind)
                got = z.read(info)
                if got != want:
                    k = next((i for i in range(min(len(got), len(want))) if got[i] != want[i]), min(len(got), len(want)))
                    bad('pinned_template', part=info.filename, sha256=sha256(got), expected_sha256=sha256(want), main_sheet=main_sheet,
                        first_difference_at=k, actual=got[max(0, k - 40):k + 60].decode('utf-8', 'replace'),
                        expected=want[max(0, k - 40):k + 60].decode('utf-8', 'replace'),
                        problem='differs from the pinned template with the escaped derived main sheet name substituted')
        for n in sorted(set(pinned_templates) - set(names)):
            bad('pinned_template', part=n, problem='missing')
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
        kids = [tag_name(e) for e in wb]
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
    for n in expected_parts:
        root = roots.get(n)
        if root is None or not n.startswith('xl/worksheets/'):
            continue
        # v4 (third review G1): every element in the transitional main namespace, by exact tag (LibreOffice maps the Strict
        # namespace to the transitional one; openpyxl and the raw reader read only the transitional <v>/<is>)
        for el in root.iter():
            if not (isinstance(el.tag, str) and el.tag.startswith(MAIN_PREFIX)):
                bad('element_namespace', part=n, element=str(el.tag)[:160],
                    problem='worksheet element not in the transitional SpreadsheetML main namespace')
        if root.tag != MAIN_PREFIX + 'worksheet':
            bad('worksheet_structure', part=n, problem='root element', actual=str(root.tag)[:160])
        kids = [tag_name(e) for e in root]
        order = [k for k in WORKSHEET_CHILDREN if k in kids]
        if any(k not in WORKSHEET_CHILDREN for k in kids) or kids != order or 'sheetData' not in kids:
            bad('worksheet_structure', part=n, problem='worksheet child elements',
                unexpected=[k for k in kids if k not in WORKSHEET_CHILDREN], actual=kids[:20])
        if expected_cols(kind, n) is not None and 'cols' not in kids:
            bad('worksheet_structure', part=n, problem='cols missing (v6.1: every column has its pinned width)')
        for el in root:
            tag = tag_name(el)
            if tag == 'sheetPr':
                if el.attrib or any(tag_name(x) not in ('tabColor', 'outlinePr', 'pageSetUpPr') for x in el):
                    bad('worksheet_structure', part=n, problem='sheetPr', attributes=dict(el.attrib), children=[tag_name(x) for x in el])
            elif tag == 'sheetViews':
                views = list(el)
                if len(views) != 1 or tag_name(views[0]) != 'sheetView':
                    bad('worksheet_structure', part=n, problem='sheetViews must hold one sheetView', actual=[tag_name(x) for x in views])
                for v in views:
                    if deliv:              # v6 (O38): gridlines shown (no showGridLines attribute), only the header row frozen
                        extra = sorted(k for k in v.attrib if k not in DELIVERY_SHEET_VIEW_ATTRS)
                        if extra:
                            bad('worksheet_structure', part=n, problem='sheetView attributes (deliverable: gridlines shown, no '
                                'showGridLines or other view attribute)', attributes=dict(v.attrib))
                        panes = [x for x in v if tag_name(x) == 'pane']
                        if len(panes) != 1 or dict(panes[0].attrib) != DELIVERY_PANE:
                            bad('worksheet_structure', part=n, problem='pane (deliverable: exactly the header-row freeze)',
                                actual=[dict(x.attrib) for x in panes], expected=DELIVERY_PANE)
                    else:
                        extra = sorted(k for k in v.attrib if k not in SHEET_VIEW_ATTRS)
                        if extra or v.attrib.get('showGridLines') != '0':
                            bad('worksheet_structure', part=n, problem='sheetView attributes', attributes=dict(v.attrib))
                    if any(tag_name(x) not in ('pane', 'selection') for x in v):
                        bad('worksheet_structure', part=n, problem='sheetView children', actual=[tag_name(x) for x in v])
            elif tag == 'sheetFormatPr':
                if dict(el.attrib) != SHEET_FORMAT_ATTRS:
                    bad('worksheet_structure', part=n, problem='sheetFormatPr attributes', attributes=dict(el.attrib), expected=SHEET_FORMAT_ATTRS)
            elif tag == 'cols':
                for col in el:
                    if tag_name(col) != 'col' or any(k not in ('min', 'max', 'width', 'customWidth') for k in col.attrib):
                        bad('worksheet_structure', part=n, problem='col', attributes=dict(col.attrib))
                want_cols = expected_cols(kind, n)
                if want_cols is not None and not cols_ok(list(el), want_cols):
                    bad('worksheet_structure', part=n, problem='cols: exactly one <col> per column, in order, min = max = the column, '
                        'customWidth="1", the pinned width (LibreOffice uses the first <col> covering a column, openpyxl the last; v6.1)',
                        actual=[dict(c.attrib) for c in list(el)[:30]], expected=want_cols)
            elif tag == 'sheetData':
                check_sheet_data(n, el, bad, kind)
            elif tag == 'pageMargins':
                if any(k not in ('left', 'right', 'top', 'bottom', 'header', 'footer') for k in el.attrib):
                    bad('worksheet_structure', part=n, problem='pageMargins attributes', attributes=dict(el.attrib))
    # cell formats: alignment only, with the writer's attributes
    st = roots.get('xl/styles.xml')
    if st is not None:
        for k, xf in enumerate(st.iterfind('m:cellXfs/m:xf', NS)):
            for x in xf:
                if tag_name(x) != 'alignment' or any(a not in ('horizontal', 'vertical', 'wrapText') for a in x.attrib):
                    bad('styles_structure', xf=k, element=tag_name(x), attributes=dict(x.attrib))
        # fonts (v3, second review F1(b)): the writer's children only, each at most once (no strike, italic,
        # underline, vertAlign, outline, shadow, ...)
        for fonts in st.iterfind('m:fonts', NS):
            for k, font in enumerate(fonts):
                kids = [tag_name(x) for x in font]
                allowed = FONT0_CHILDREN if k == 0 else FONT_CHILDREN
                if tag_name(font) != 'font' or any(x not in allowed for x in kids) or len(kids) != len(set(kids)):
                    bad('font_structure', font=k, element=tag_name(font), children=kids, allowed=list(allowed))
    return {'kind': kind, 'parts': sorted(set(names)), 'expected_parts': list(expected_parts), 'pinned_parts': dict(pinned_parts),
            'pinned_templates': {k: dict(v, main_sheet=main_sheet, expected_sha256=sha256(template_part(k, main_sheet, kind)))
                                 for k, v in pinned_templates.items()}}


def number_text_ok(text):
    """Number text the writer writes: ASCII, JavaScript Number::toString of a finite number (NUMBER_TEXT_RE, whole text)."""
    return isinstance(text, str) and text.isascii() and NUMBER_TEXT_RE.fullmatch(text) is not None


def check_sheet_data(part, sheet_data, bad, kind='qa'):
    """Rows and cells of one worksheet's <sheetData> (review S2; v3 second review F1(b): value children, number text,
    duplicate and out-of-row references). Readers differ on these: Python readers take the first matching child and
    accept any text int()/float() accept; LibreOffice took the last <v>/<is>, an empty cell for a <v> beside <is>, and
    1 or 0 for '1_234_567' or fullwidth digits (review round 2, N01-N07)."""
    n = part
    seen_rows, seen_cells, last_row = set(), set(), 0
    for row in sheet_data:
        ra = row.attrib
        if kind == 'deliverable':          # v6 (O38): every row has its height, 23.25 for the header and 20.45 for the others
            ht_ok = ra.get('ht') == DELIVERY_ROW_HT['header' if ra.get('r') == '1' else 'body'] and ra.get('customHeight') == '1'
        else:
            ht_ok = not ('ht' in ra or 'customHeight' in ra) or (ra.get('r') == '1' and ra.get('ht') == '36')
        if tag_name(row) != 'row' or any(k not in ('r', 'spans', 'ht', 'customHeight') for k in ra) or not ht_ok:
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
            if tag_name(c) != 'c' or any(k not in ('r', 's', 't') for k in c.attrib):
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
            kids = [tag_name(x) for x in c]
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
                xt = tag_name(x)
                if xt not in ('v', 'is', 'f'):
                    bad('worksheet_structure', part=n, problem='cell child', cell=where, child=xt)
                if xt == 'v':
                    if x.attrib or len(x):
                        bad('cell_value_children', part=n, cell=where, problem='<v> with attributes or child elements',
                            attributes=dict(x.attrib), children=[tag_name(y) for y in x])
                    text = x.text or ''
                    if typ == 'n' and not number_text_ok(text):
                        bad('number_text', part=n, cell=where, text=text[:100],
                            problem='number text is not ASCII JavaScript Number::toString text')
                if xt == 'is':
                    ts = list(x)
                    if len(ts) != 1 or tag_name(ts[0]) != 't':
                        bad('worksheet_structure', part=n, problem='inline string must be one plain <t> (no rich-text runs)',
                            cell=where, actual=[tag_name(t) for t in ts])
                    for t in ts:
                        if any(k != XML_SPACE for k in t.attrib):
                            bad('worksheet_structure', part=n, problem='<t> attributes', cell=where, attributes=dict(t.attrib))
                        if len(t):
                            bad('cell_value_children', part=n, cell=where, problem='<t> with child elements',
                                children=[tag_name(y) for y in t])
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
    """info: the finding; code: the expected_provenance result code; record: a partial record (checker node)."""
    def __init__(self, info, code='NODE_ENVIRONMENT_REFUSED', record=None):
        super().__init__(info)
        self.info, self.code, self.record = info, code, record


def resolve_node(node, pinned_sha256=None):
    """v4 (third review G2): the one node binary of every node call of this saved-QA run (the writer004 check and the writer
    rerun, which gets its realpath as --node). Pinned (--checker-node, --checker-node-sha256): the absolute path given,
    its realpath read and its sha256 compared with the pin before any node call; neither PATH nor the receipt is read.
    Unpinned (--node, default 'node'): a bare name is searched in the allowlisted PATH, as the writer does; such a run
    is not CPS evidence, and its record shows which binary ran. Raises ProvenanceRefused (CHECKER_NODE_REFUSED,
    NODE_UNAVAILABLE)."""
    pinned = pinned_sha256 is not None
    rec = {'pinned': pinned, 'command': node}
    refuse = 'CHECKER_NODE_REFUSED' if pinned else 'NODE_UNAVAILABLE'
    if pinned:
        rec['source'] = '--checker-node: the absolute path given (neither PATH nor the receipt is read)'
        rec['pinned_sha256'] = pinned_sha256
        found = node if os.path.isabs(node) else None
        if found is None:
            raise ProvenanceRefused({'check': 'checker node is not an absolute path', 'node': node}, refuse, rec)
    else:
        rec['source'] = '--node (unpinned: a name without a directory is searched in the allowlisted PATH); not CPS evidence'
        found = shutil.which(node, path=node_env()[0].get('PATH'))
        if found is None:
            raise ProvenanceRefused({'check': 'node not found or not executable', 'node': node}, refuse, rec)
    rec['executable'] = found
    real = os.path.realpath(found)
    rec['realpath'] = real
    try:
        h = sha256(Path(real).read_bytes()) if os.path.isfile(real) else None
    except OSError:
        h = None
    rec['sha256'] = h
    if h is None:
        raise ProvenanceRefused({'check': 'node binary is not a readable file', 'realpath': real}, refuse, rec)
    if pinned:
        rec['sha256_verified'] = h == pinned_sha256
        if h != pinned_sha256:
            raise ProvenanceRefused({'check': 'checker node sha256 differs from --checker-node-sha256 (no node call was made)',
                                     'realpath': real, 'sha256': h, 'pinned_sha256': pinned_sha256}, refuse, rec)
    code, out, err = run_node([real, '--version'], 60)
    rec['version'] = out.decode('utf-8', 'replace').strip()[:80] if code == 0 else None
    return rec


def receipt_node_claim(receipt):
    """The producer receipt's node record (node_environment.node): shown, never used and never compared (not evidence)."""
    node = (receipt.get('node_environment') or {}).get('node') if isinstance(receipt, dict) else None
    if not isinstance(node, dict):
        return None
    return {k: (str(node.get(k))[:300] if node.get(k) is not None else None) for k in ('command', 'executable', 'realpath', 'sha256', 'version')}


def canonical(v):
    return json.dumps(v, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def receipt_claims(r):
    """v4 (third review G3): the deterministic receipt fields, as [present, value]. The route port's path (a location on
    the machine that ran the writer) is left out of relaxations; its sha256, version and result stay in."""
    out = {}
    for k in RECEIPT_CLAIM_FIELDS:
        v = copy.deepcopy(r.get(k))
        if k == 'relaxations' and isinstance(v, dict) and isinstance(v.get('route_v4_port'), dict):
            v['route_v4_port'].pop('path', None)
        out[k] = [k in r, v]
    return out


def compare_receipt_claims(receipt, rerun, receipt_mode, F):
    """v4 (third review G3): the delivered receipt's RECEIPT_CLAIM_FIELDS must equal the rerun receipt's (canonical JSON, so
    false is not 0 and 1 is not 1.0). The rerun is always --mode v2; for a receipt that says v1 the expected mode is v1 and
    the expected relaxations {"applied": false, "scanned": false}, which is what a v1 run writes for a carrier without
    O13/R57 (the v1 route is the v2 route without O13/R57; every other compared field is the same). A rerun that applied
    relaxations keeps mode v2, so a v1 claim on a relaxed output mismatches."""
    got, want = receipt_claims(receipt), receipt_claims(rerun)
    v1 = receipt_mode == 'v1' and (rerun.get('relaxations') or {}).get('applied') is False
    if v1:
        want['mode'], want['relaxations'] = [True, 'v1'], [True, dict(V1_RELAXATIONS)]
    mismatched = [k for k in RECEIPT_CLAIM_FIELDS if canonical(got[k]) != canonical(want[k])]
    if mismatched:
        F.add('receipt_claim_mismatch', {
            'fields': mismatched,
            'problem': 'WRITER_RECEIPT.json claims differ from the writer rerun receipt',
            'detail': {k: {'receipt': canonical(got[k])[:300], 'rerun': canonical(want[k])[:300],
                           'receipt_sha256': sha256(canonical(got[k]).encode('ascii')),
                           'rerun_sha256': sha256(canonical(want[k]).encode('ascii'))} for k in mismatched}})
    return {'compared_fields': list(RECEIPT_CLAIM_FIELDS), 'match': not mismatched, 'mismatched_fields': mismatched,
            'expected_from': 'the writer rerun receipt (--mode v2)' + (
                '; receipt mode v1: mode "v1" and relaxations {"applied": false, "scanned": false}, as a v1 run of this carrier '
                'writes' if v1 else ''),
            'relaxations_compared_without': ['route_v4_port.path'],
            'not_compared': 'every other receipt field (paths, times, node_environment, tool_versions, gate, limitations) is '
                            "the producer's claim and is not evidence"}


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


def check_provenance(receipt, ebytes, xbytes, carrier, writer_dir, node, F, checker_node_sha256=None, deliverable='untitled',
                     dbytes=None):
    """v3 (second review F1(a), F2): the writer rerun (--mode v2) always runs and both EXPECTED_SAVED_VALUES.json and the
    xlsx are byte-compared, whatever the receipt's mode says. A receipt that says v1 also gets the writer004
    prepareMatrices comparison (run first). v4 (third review G2, G3): one node binary for every node call (resolve_node;
    pinned with checker_node_sha256), its realpath and sha256 recorded for the writer004 check and for the rerun (the rerun
    receipt's node must be the same file); the receipt's deterministic claims compared with the rerun receipt
    (compare_receipt_claims); the rerun's relaxation classes and documented cells recorded. The result is PASS;
    CHECKER_NODE_REFUSED or NODE_UNAVAILABLE when the node binary is refused (then no node call and no rerun is made);
    otherwise the first refusal code (UNKNOWN_MODE, NODE_ENVIRONMENT_REFUSED, WRITER004_REFUSED, WRITER_RERUN_FAILED,
    CHECKER_NODE_REFUSED for a pinned binary changed during the check), or FAILED (also for a receipt_claim_mismatch).
    v5 (O33): deliverable is saved QA's own derivation from the receipt's job title (derive_deliverable; None when the title
    cannot be derived: then no rerun is made, JOB_TITLE_INVALID). The rerun gets --job-title=<that title> when there is one, and
    its workbook is read under the derived file name. v6 (O38): the four-sheet workbook is the derived qa_workbook_file, and a
    titled rerun's deliverable <name>.xlsx is byte-compared with dbytes (the delivered deliverable)."""
    def bad(**kw):
        F.add('provenance', kw)
    if deliverable == 'untitled':
        deliverable = derive_deliverable(None)
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
    rec['method'] = ('writer_portable.py --mode v2 rerun into a temporary directory, whatever the receipt mode says, with '
                     '--job-title=<the receipt\'s job title> when it has one (v5, O33; its file and sheet names re-derived here); '
                     'EXPECTED_SAVED_VALUES.json and the xlsx byte-compared (builds are reproducible; v2 gives the v1 bytes for a '
                     'carrier without O13/R57)' + ('; receipt mode v1: also writer004_matrices.mjs (writer004 prepareMatrices on the '
                                                   'carrier) byte-compared with EXPECTED_SAVED_VALUES.json' if mode == 'v1' else ''))
    rec['writer004_check'] = 'run (receipt mode v1)' if mode == 'v1' else 'not run (receipt mode is not v1)'
    rec['receipt_node'] = receipt_node_claim(receipt)
    rec['receipt_node_note'] = "the producer receipt's node_environment.node: shown for the record, not used, not compared, not evidence"
    try:
        node_rec = resolve_node(node, checker_node_sha256)
    except ProvenanceRefused as e:
        rec['checker_node'] = e.record
        bad(**e.info)
        rec['result'] = e.code
        return rec
    rec['checker_node'] = node_rec
    node = node_rec['realpath']                  # every node call below, and the rerun's --node
    if rec['receipt_node'] is not None:
        rec['receipt_node_matches_checker_node'] = (rec['receipt_node'].get('realpath') == node_rec['realpath']
                                                    and rec['receipt_node'].get('sha256') == node_rec['sha256'])
    if mode == 'v1':
        try:
            real, env_rec = pinned_node_environment(node, writer_dir)
        except ProvenanceRefused as e:
            bad(**e.info)
            codes.append(e.code)
        else:
            rec['node_environment'] = env_rec
            rec['writer004_check_node'] = {'realpath': node, 'sha256': node_rec['sha256'], 'pinned': node_rec['pinned']}
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
    title = deliverable.get('job_title') if deliverable is not None else None
    rec['rerun_job_title'] = title
    rec['rerun_xlsx_file'] = deliverable.get('qa_workbook_file') if deliverable is not None else None
    rec['rerun_deliverable_file'] = deliverable.get('xlsx_file') if deliverable is not None and deliverable.get('deliverable_workbook') else None
    with tempfile.TemporaryDirectory(prefix='cps_saved_qa_rerun_') as td:
        dest = Path(td) / 'rerun'
        rec['writer_portable.py_sha256'] = sha256(WRITER.read_bytes())
        if deliverable is None:
            p = None
            bad(check='writer rerun not made: the job title in WRITER_RECEIPT.json cannot be derived (finding deliverable_name)')
            codes.append('JOB_TITLE_INVALID')
        else:
            p = subprocess.run([sys.executable, '-I', '-B', str(WRITER), '--carrier', str(carrier), '--out', str(dest),
                                '--writer-dir', str(writer_dir), '--node', node, '--mode', 'v2']
                               + (['--job-title=' + title] if title is not None else []), capture_output=True, timeout=1800)
        if p is None:
            e2 = x2 = r2 = d2 = None
        elif p.returncode != 0:
            err = p.stderr.decode('utf-8', 'replace')
            try:
                ref = json.loads(err.strip().splitlines()[-1])
                ref = {'code': ref.get('code'), 'stage': ref.get('stage')}
            except (ValueError, IndexError, AttributeError):
                ref = None
            bad(check='writer rerun refused or failed', refusal=ref, stderr=err[-400:])
            codes.append('WRITER_RERUN_FAILED')
            e2 = x2 = r2 = d2 = None
        else:
            xp = dest / deliverable['qa_workbook_file']
            e2, x2 = (dest / 'EXPECTED_SAVED_VALUES.json').read_bytes(), (xp.read_bytes() if xp.is_file() else None)
            dp = dest / deliverable['xlsx_file'] if deliverable.get('deliverable_workbook') else None
            d2 = dp.read_bytes() if dp is not None and dp.is_file() else None
            if dp is not None and d2 is None:
                bad(check='the writer rerun wrote no deliverable under the derived file name', file=deliverable['xlsx_file'])
            r2 = json.loads((dest / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
            if x2 is None:
                bad(check='the writer rerun wrote no workbook under the derived file name', file=deliverable['xlsx_file'],
                    rerun_files=sorted(q.name for q in dest.iterdir()))
    if r2 is not None:
        rec['rerun_writer'] = r2.get('writer')
        rec['rerun_mode'] = r2.get('mode')
        rel = r2.get('relaxations') or {}
        rec['rerun_relaxations_applied'] = rel.get('applied')
        # v4 (third review G3): the relaxation classes and documented cells come from the rerun, not from the receipt
        rec['rerun_relaxation_classes'] = {k: {kk: vv for kk, vv in v.items() if kk != 'neutralization'}
                                           for k, v in (rel.get('classes') or {}).items() if isinstance(v, dict)}
        rec['rerun_documented_cells'] = rel.get('saved_matrices_differ_from_placeholder_copy_only_in')
        rec['rerun_node_environment'] = r2.get('node_environment')
        rn = (r2.get('node_environment') or {}).get('node') or {}
        rec['rerun_node'] = {k: rn.get(k) for k in ('command', 'executable', 'realpath', 'sha256', 'version')}
        if rn.get('realpath') != node or rn.get('sha256') != node_rec['sha256']:
            bad(check='the writer rerun receipt names another node binary than the checker node',
                rerun_node={'realpath': rn.get('realpath'), 'sha256': rn.get('sha256')}, checker_node={'realpath': node, 'sha256': node_rec['sha256']})
        rec['expected_byte_identical'], rec['xlsx_byte_identical'] = e2 == ebytes, x2 is not None and x2 == xbytes
        if e2 != ebytes:
            bad(check='EXPECTED_SAVED_VALUES.json differs from the writer rerun on the carrier')
        if x2 != xbytes:
            bad(check='the workbook differs from the writer rerun on the carrier', file=rec['rerun_xlsx_file'])
        if rec['rerun_deliverable_file'] is not None:
            rec['deliverable_xlsx_byte_identical'] = d2 is not None and d2 == dbytes
            if not rec['deliverable_xlsx_byte_identical']:
                bad(check='the deliverable workbook differs from the writer rerun on the carrier', file=rec['rerun_deliverable_file'],
                    workbook='deliverable')
        if receipt is not None:
            rec['receipt_claims'] = compare_receipt_claims(receipt, r2, mode, F)
    if node_rec['pinned']:                       # the pinned file is unchanged after the last node call
        try:
            after = sha256(Path(node).read_bytes())
        except OSError:
            after = None
        rec['checker_node']['sha256_after_check'] = after
        if after != node_rec['sha256']:
            bad(check='checker node changed during the check', sha256_before=node_rec['sha256'], sha256_after=after)
            codes.append('CHECKER_NODE_REFUSED')
    failed = F.count('provenance') or F.count('receipt_claim_mismatch')
    rec['result'] = 'PASS' if not failed else (codes[0] if codes else 'FAILED')
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


def compare_sheet(name, rows, cells, reader, F, label=None):
    """name: the EXPECTED_SAVED_VALUES.json (writer004) sheet name; label: the workbook sheet it maps to (v5, O33)."""
    ncols = SHEET_COLS.get(name)
    label = name if label is None else label
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
                F.add('value_type_mismatch', {'reader': reader, 'sheet': label, 'cell': f'{col_letters(j)}{i}',
                                              'expected_type': k, 'actual_type': kind(got), 'actual_cell_type': dtype,
                                              'expected': want, 'actual': got})
    for (r, c), (got, dtype) in sorted(remaining.items()):
        if got is not None or dtype in ('f', 'str', 'e'):
            F.add('unexpected_populated_cell', {'reader': reader, 'sheet': label, 'cell': f'{col_letters(c)}{r}',
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
    if not name.strip() or utf16_len(name) > EXCEL['sheet_name_chars'] or re.search(r'[\[\]:*?/\\]', name) or name.startswith("'") or name.endswith("'"):
        F.add('excel_limit', {'sheet': name, 'limit': 'sheet_name'})


def font_extras(font):
    """v3 (second review F1(b), N10/N11): font properties the writer never sets; each must be off."""
    return (('font.italic', False, bool(font.i)), ('font.strike', False, bool(font.strike)),
            ('font.underline', None, font.u), ('font.vertAlign', None, font.vertAlign))


def check_formatting(wb, expected_rows, F, mapping=None):
    """The writer004 formatSheet/main-sheet formatting as the portable writer expresses it. v5: every body cell has no fill,
    G and H (單價, 複價) of the main sheet included (O34; writer004 filled them #F1F3F5). mapping: EXPECTED sheet name ->
    workbook sheet name (O33)."""
    mapping = mapping or {}
    checked = 0

    def bad(sheet, cell, prop, want, got):
        F.add('formatting', {'sheet': sheet, 'cell': cell, 'property': prop, 'expected': want, 'actual': got})

    def rgb(color):
        return None if color is None else getattr(color, 'rgb', None)
    for xname in SHEETS:
        name = mapping.get(xname, xname)
        if name not in wb.sheetnames or xname not in expected_rows:
            continue
        ws = wb[name]
        ncols, nrows = SHEET_COLS[xname], len(expected_rows[xname])
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
                main_num = xname == SHEETS[0] and c in (6, 16, 17)
                price = xname == SHEETS[0] and c in (7, 8)          # O34: G and H have no fill, like every body cell
                for prop, want, got in (('font.name', 'Arial', cell.font.name), ('font.size', 11, cell.font.sz), ('font.bold', False, bool(cell.font.b)),
                                        ('font.color', 'FF172033', rgb(cell.font.color)), ('align.vertical', 'top', cell.alignment.vertical),
                                        ('align.wrap', True, cell.alignment.wrap_text),
                                        ('align.horizontal', 'right' if main_num else None, cell.alignment.horizontal),
                                        ('number_format', 'General', cell.number_format),
                                        ('fill.type.o34_price_column' if price else 'fill.type', None, cell.fill.fill_type)) + font_extras(cell.font):
                    if got != want:
                        bad(name, a, prop, want, got)
        for j, w in enumerate(WIDTHS[xname], start=1):
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
        want_tab = 'FF29445D' if xname == SHEETS[0] else None
        if tab != want_tab:
            bad(name, None, 'tab_color', want_tab, tab)
    return checked


def check_deliverable_formatting(wb, nrows, F, sheet):
    """v6 (O38): the deliverable's format cell by cell on A1:Q<nrows>, the widths, row heights, header-row freeze, gridlines
    shown and no tab colour. F is the deliverable's TaggedFindings."""
    checked = 0

    def bad(cell, prop, want, got):
        F.add('formatting', {'sheet': sheet, 'cell': cell, 'property': prop, 'expected': want, 'actual': got})

    def rgb(color):
        return None if color is None else getattr(color, 'rgb', None)
    if sheet not in wb.sheetnames:
        return 0
    ws = wb[sheet]
    side = (DELIVERY['border_style'], DELIVERY['border_color'])
    for r in range(1, nrows + 1):
        for c in range(1, 18):
            cell = ws.cell(row=r, column=c)
            a, x = cell.coordinate, col_letters(c)
            checked += 1
            head = r == 1
            b = cell.border
            sides = [(s_.style, rgb(s_.color)) for s_ in (b.left, b.right, b.top, b.bottom)]
            props = [('font.name', DELIVERY['font'], cell.font.name), ('font.size', DELIVERY['size'], cell.font.sz),
                     ('font.bold', False, bool(cell.font.b)), ('font.color', None, rgb(cell.font.color)),
                     ('align.horizontal', 'center' if head or x in DELIVERY['centred'] else 'left' if x in DELIVERY['left'] else None,
                      cell.alignment.horizontal),
                     ('align.vertical', 'center', cell.alignment.vertical), ('align.wrap', False, bool(cell.alignment.wrap_text)),
                     ('align.shrink', False, bool(cell.alignment.shrink_to_fit)), ('align.indent', 0, cell.alignment.indent),
                     ('align.rotation', 0, cell.alignment.text_rotation),
                     ('number_format', 'General', cell.number_format),
                     ('fill.type', 'solid' if head else None, cell.fill.fill_type),
                     ('border', [side] * 4 if head else [(None, None)] * 4, sides),
                     ('protection.hidden', False, bool(cell.protection.hidden))] + list(font_extras(cell.font))
            if head:
                props.append(('fill.color', DELIVERY['header_fill'], rgb(cell.fill.fgColor)))
            for prop, want, got in props:
                if got != want:
                    bad(a, prop, want, got)
    for j, w in enumerate(DELIVERY['widths'], start=1):
        got = ws.column_dimensions[col_letters(j)].width
        if got is None or abs(got - w) > 1e-9:           # openpyxl writes 81.9 as 81.90000000000001
            bad(col_letters(j), 'column_width', w, got)
        if ws.column_dimensions[col_letters(j)].hidden:
            bad(col_letters(j), 'column_hidden', False, True)
    for r in range(1, nrows + 1):
        want = DELIVERY['header_height'] if r == 1 else DELIVERY['row_height']
        got = ws.row_dimensions[r].height
        if got != want:
            bad(f'row {r}', 'row_height', want, got)
    extra = sorted(r for r, d in ws.row_dimensions.items() if r > nrows and d.height is not None)
    if extra:
        bad(None, 'rows_after_the_last_with_height', [], extra[:20])
    if ws.freeze_panes != DELIVERY['freeze']:
        bad(None, 'freeze_panes', DELIVERY['freeze'], ws.freeze_panes)
    if ws.sheet_view.showGridLines is False:
        bad(None, 'showGridLines', 'shown (attribute absent)', False)
    if rgb(ws.sheet_properties.tabColor) is not None:
        bad(None, 'tab_color', None, rgb(ws.sheet_properties.tabColor))
    return checked


def check_deliverable(path, exp_rows, main_sheet, F, formatting):
    """v6 (O38): the deliverable workbook <name>.xlsx (one sheet main_sheet) against the main sheet of
    EXPECTED_SAVED_VALUES.json. Findings go to F tagged "workbook": "deliverable". Returns the report section."""
    T = TaggedFindings(F, 'deliverable')
    sec = {'file': path.name, 'sheet': main_sheet, 'checked': False}
    if not path.is_file():
        return sec
    xb = path.read_bytes()
    sec.update(checked=True, sha256=sha256(xb), bytes=len(xb))
    try:
        sec['structure'] = check_structure(path, T, main_sheet, 'deliverable')
    except Exception as e:                      # noqa: BLE001
        T.add('reader_error', {'reader': 'structure', 'error': repr(e)[:300]})
    main_rows = exp_rows.get(SHEETS[0]) if exp_rows else None
    if main_rows is None:
        return sec
    readers, counts, raw, wb_f = {}, {}, None, None
    for reader, fn in (('openpyxl_formulas', lambda: read_openpyxl(path, data_only=False)),
                       ('openpyxl_data_only', lambda: read_openpyxl(path, data_only=True)),
                       ('raw_ooxml', lambda: read_raw(path, T))):
        try:
            res = fn()
        except Exception as e:                  # noqa: BLE001
            T.add('reader_error', {'reader': reader, 'error': repr(e)[:300]})
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
        if order != [main_sheet]:
            T.add('sheet_order', {'reader': reader, 'actual': order, 'expected': [main_sheet],
                                  'problem': 'the deliverable holds exactly one sheet, the derived main sheet name'})
        for name, cells in cells_by_sheet.items():
            if name != main_sheet:
                compare_sheet(SHEETS[0], [], cells, reader, T, name)      # any populated cell of another sheet is unexpected
        cells = cells_by_sheet.get(main_sheet, {})
        counts[reader] = compare_sheet(SHEETS[0], main_rows, cells, reader, T, main_sheet)
        row1 = [cells.get((1, c), (None, None))[0] for c in range(1, 18)]
        if row1 != HEADERS:
            T.add('header_row', {'reader': reader, 'check': 'deliverable row 1 A-Q equals the 17 headers'})
        if reader == 'raw_ooxml':
            for name in order:
                check_sheet_name(name, T)
    if wb_f is not None:
        for name, sh in wb_f[1].items():
            for (r, c), (v, dt) in sh['cells'].items():
                if dt == 'f':
                    T.add('formula', {'reader': 'openpyxl_formulas', 'sheet': name, 'cell': f'{col_letters(c)}{r}'})
                if dt == 'e':
                    T.add('error_cell_type', {'reader': 'openpyxl_formulas', 'sheet': name, 'cell': f'{col_letters(c)}{r}'})
            check_limits(name, {k: v for k, v in sh['cells'].items()}, T)
    if raw is not None:
        for f in raw['formulas']:
            T.add('formula', {'reader': 'raw_ooxml', **f})
        for name, cells in raw['sheets'].items():
            for (r, c), (_, typ) in cells.items():
                if typ in ('str', 'e'):
                    T.add('error_cell_type' if typ == 'e' else 'formula', {'reader': 'raw_ooxml', 'sheet': name, 'cell': f'{col_letters(c)}{r}', 'type': typ})
        if raw['defined_names']:
            T.add('defined_names', {'count': raw['defined_names']})
        for e in raw['external_relationships']:
            T.add('external_relationship', e)
        for q in [q for q in raw['parts'] if re.search(r'(?:vbaProject|externalLink|connections\.xml|calcChain)', q)]:
            T.add('unexpected_part', {'part': q})
    if len(readers) == 3:
        names = set()
        for _, (order, cbs) in readers.items():
            names |= set(cbs)
        for name in sorted(names):
            a = {k: v[0] for k, v in readers['openpyxl_formulas'][1].get(name, {}).items() if v[0] is not None}
            b = {k: v[0] for k, v in readers['openpyxl_data_only'][1].get(name, {}).items() if v[0] is not None}
            c_ = {k: v[0] for k, v in readers['raw_ooxml'][1].get(name, {}).items() if v[0] is not None}
            for key in set(a) | set(b) | set(c_):
                va, vb, vc = a.get(key), b.get(key), c_.get(key)
                if not (va == vb == vc and kind(va) == kind(vb) == kind(vc)):
                    T.add('reader_disagreement', {'sheet': name, 'cell': f'{col_letters(key[1])}{key[0]}',
                                                  'openpyxl_formulas': va, 'openpyxl_data_only': vb, 'raw_ooxml': vc})
    sec['readers'] = list(readers)
    sec['counts_by_reader'] = counts
    sec['sheet_order'] = raw['order'] if raw else None
    sec['formatting_cells_checked'] = None
    if formatting and wb_f is not None:
        try:
            sec['formatting_cells_checked'] = check_deliverable_formatting(wb_f[0], len(main_rows), T, main_sheet)
        except Exception as e:                  # noqa: BLE001
            T.add('reader_error', {'reader': 'formatting', 'error': repr(e)[:300]})
    sec['compared_with'] = 'the main sheet of EXPECTED_SAVED_VALUES.json (' + SHEETS[0] + ')'
    return sec


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


def resolve_deliverable(out_dir, receipt, F):
    """v5 (O33): the workbook to read and its sheet names, re-derived from the receipt's deliverable.job_title with saved QA's
    own derive_deliverable (never the receipt's file or sheet names). Findings (deliverable_name): a receipt without a
    deliverable record, a job title that cannot be derived, receipt deliverable fields or output_xlsx.file that differ from
    the derivation, no workbook under the derived file name, another .xlsx in the output directory. Returns (derived record
    or None, the record whose names are used, report section); when the title cannot be derived the v2.5 names are used."""
    def bad(**kw):
        F.add('deliverable_name', kw)
    for q in sorted(out_dir.iterdir()):        # v6.1 (review N3): the files saved QA reads are regular files, not links
        if q.is_symlink() and (q.name.lower().endswith('.xlsx') or q.name in ('EXPECTED_SAVED_VALUES.json', 'WRITER_RECEIPT.json')):
            F.add('integrity', {'check': 'a symbolic link in the output directory: the workbooks, EXPECTED_SAVED_VALUES.json and '
                                         'WRITER_RECEIPT.json must be regular files', 'file': q.name})
    dl = receipt.get('deliverable') if isinstance(receipt, dict) else None
    title = dl.get('job_title') if isinstance(dl, dict) else None
    if receipt is not None and not isinstance(dl, dict):
        bad(check='WRITER_RECEIPT.json has no deliverable record (writer v2.6)')
    try:
        derived = derive_deliverable(title)
    except DeliverableNameError as e:
        bad(check='the job title in WRITER_RECEIPT.json cannot be derived', reason=e.reason, **e.detail)
        derived = None
    use = derived or derive_deliverable(None)
    mismatched = []
    if isinstance(dl, dict) and derived is not None:
        mismatched = [k for k in DELIVERABLE_FIELDS if canonical([k in dl, dl.get(k)]) != canonical([True, derived[k]])]
        if mismatched:
            bad(check='WRITER_RECEIPT.json deliverable differs from the derivation from its job title', fields=mismatched,
                detail={k: {'receipt': canonical(dl.get(k))[:300], 'derived': canonical(derived[k])[:300]} for k in mismatched})
    receipt_file = (receipt.get('output_xlsx') or {}).get('file') if isinstance(receipt, dict) else None
    if receipt is not None and receipt_file != use['qa_workbook_file']:
        bad(check='WRITER_RECEIPT.json output_xlsx.file differs from the derived internal workbook file name', receipt=str(receipt_file)[:300],
            derived=use['qa_workbook_file'])
    xlsx = out_dir / use['qa_workbook_file']
    if not xlsx.is_file():
        bad(check='no workbook under the derived internal workbook file name', file=use['qa_workbook_file'])
    # v6 (O38): a titled output also holds the deliverable <name>.xlsx, named in the receipt's deliverable_xlsx
    allowed = {use['qa_workbook_file']} | ({use['xlsx_file']} if use['deliverable_workbook'] else set())
    rdx = receipt.get('deliverable_xlsx') if isinstance(receipt, dict) else None
    if use['deliverable_workbook']:
        if not (out_dir / use['xlsx_file']).is_file():
            bad(check='no deliverable workbook under the derived file name', file=use['xlsx_file'])
        if receipt is not None and (not isinstance(rdx, dict) or rdx.get('file') != use['xlsx_file'] or rdx.get('sheet') != use['main_sheet']
                                    or rdx.get('format') != DELIVERY_FORMAT):
            bad(check='WRITER_RECEIPT.json deliverable_xlsx differs from the derived deliverable (file, sheet, format)',
                receipt=canonical(rdx)[:300], derived={'file': use['xlsx_file'], 'sheet': use['main_sheet'], 'format': DELIVERY_FORMAT})
    elif receipt is not None and rdx is not None:
        bad(check='WRITER_RECEIPT.json names a deliverable workbook for an untitled output', receipt=canonical(rdx)[:300])
    others = sorted(q.name for q in out_dir.iterdir() if q.name.lower().endswith('.xlsx') and q.name not in allowed)
    if others:
        bad(check='another workbook in the output directory', files=others[:20], derived=sorted(allowed))
    section = {'job_title': title, 'derived_here': derived is not None, 'xlsx_file': use['xlsx_file'], 'main_sheet': use['main_sheet'],
               'qa_workbook_file': use['qa_workbook_file'], 'deliverable_workbook': use['deliverable_workbook'],
               'sheet_mapping': use['sheet_mapping'], 'receipt_fields_equal_derivation': bool(derived is not None and isinstance(dl, dict)
                                                                                                and not mismatched),
               'receipt_output_xlsx_file': receipt_file, 'derivation': (
                   {k: derived[k] for k in ('normalized_title', 'dash_removed_at', 'name', 'main_sheet_cut')} if derived else None),
               'note': ('File and sheet names re-derived here from the receipt\'s job title (saved QA\'s own implementation of the O33 '
                        'rule). The job title itself is a per-job input like the carrier: whether it is the harness\'s title for this '
                        'job is the operator\'s check, not made here.')}
    return derived, use, section


def run_qa(out_dir, formatting=True, carrier=None, writer_dir=None, node='node', checker_node_sha256=None):
    """checker_node_sha256 given: node is the --checker-node absolute path, pinned by that sha256 (third review G2).
    v5 (O33): the workbook and its sheet names come from resolve_deliverable."""
    exp_path = out_dir / 'EXPECTED_SAVED_VALUES.json'
    ebytes = exp_path.read_bytes()
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
    derived, use, deliverable = resolve_deliverable(out_dir, receipt, F)
    mapping = {m['expected_saved_values_sheet']: m['workbook_sheet'] for m in use['sheet_mapping']}
    xlsx = out_dir / use['qa_workbook_file']                     # v6: the four-sheet workbook (INTERNAL_QA_WORKBOOK.xlsx if titled)
    xbytes = xlsx.read_bytes() if xlsx.is_file() else None
    dpath = out_dir / use['xlsx_file'] if use['deliverable_workbook'] else None
    dbytes = dpath.read_bytes() if dpath is not None and dpath.is_file() else None
    if receipt is not None:
        if xbytes is not None and (receipt.get('output_xlsx') or {}).get('sha256') != sha256(xbytes):
            F.add('integrity', {'check': 'xlsx sha256 differs from WRITER_RECEIPT.json'})
        if dbytes is not None and (receipt.get('deliverable_xlsx') or {}).get('sha256') != sha256(dbytes):
            F.add('integrity', {'check': 'deliverable xlsx sha256 differs from WRITER_RECEIPT.json deliverable_xlsx', 'workbook': 'deliverable'})
        if (receipt.get('expected_saved_values') or {}).get('sha256') != sha256(ebytes):
            F.add('integrity', {'check': 'EXPECTED_SAVED_VALUES.json sha256 differs from WRITER_RECEIPT.json'})

    structure = None
    if xbytes is not None:
        try:
            structure = check_structure(xlsx, F, use['main_sheet'])
        except Exception as e:                  # noqa: BLE001 - a malformed package is a finding, not a crash
            F.add('reader_error', {'reader': 'structure', 'error': repr(e)[:300]})

    provenance = {'checked': False, 'note': 'Not checked: run with --carrier and --writer-dir. Without them a consistent replacement of '
                                            'EXPECTED_SAVED_VALUES.json and the workbook (with or without WRITER_RECEIPT.json) is not detected.'}
    if carrier is not None:
        try:
            provenance = check_provenance(receipt, ebytes, xbytes, carrier, writer_dir, node, F, checker_node_sha256, derived, dbytes)
        except Exception as e:                  # noqa: BLE001
            F.add('provenance', {'check': 'provenance check failed', 'error': repr(e)[:300]})
            provenance = {'checked': True, 'result': 'ERROR'}

    readers, per_reader, header_checks, raw, wb_f, fmt_checked = {}, {}, {}, None, None, None
    if exp_sheets is not None and xbytes is not None:
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
        want_order = [mapping.get(s['name'], s['name']) for s in exp_sheets]      # v5 (O33): the derived workbook names
        for reader, (order, cells_by_sheet) in readers.items():
            if order != want_order:
                F.add('sheet_order', {'reader': reader, 'actual': order, 'expected': want_order})
            counts = []
            for s in exp_sheets:
                cells = cells_by_sheet.get(mapping.get(s['name'], s['name']), {})
                counts.append(compare_sheet(s['name'], s['values'], cells, reader, F, mapping.get(s['name'], s['name'])))
            per_reader[reader] = counts
            if reader == 'raw_ooxml':
                for name in order:
                    check_sheet_name(name, F)
                if (order[:1] or [None])[0] != use['main_sheet']:
                    F.add('deliverable_name', {'check': 'the workbook\'s first sheet is not the derived main sheet name',
                                               'actual': (order[:1] or [None])[0], 'derived': use['main_sheet']})
            main = cells_by_sheet.get(mapping[SHEETS[0]], {})
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
            for name in (mapping[x] for x in SHEETS):
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
                fmt_checked = check_formatting(wb_f[0], exp_rows, F, mapping)
            except Exception as e:              # noqa: BLE001
                F.add('reader_error', {'reader': 'formatting', 'error': repr(e)[:300]})

    deliverable_wb = {'checked': False, 'present': use['deliverable_workbook'],
                      'note': 'untitled output: no deliverable workbook (writer v2.7 writes it only with --job-title, O38)'}
    if use['deliverable_workbook'] and dpath is not None:
        try:
            deliverable_wb = check_deliverable(dpath, ({s['name']: s['values'] for s in exp_sheets} if exp_sheets is not None else None),
                                               use['main_sheet'], F, formatting)
        except Exception as e:                  # noqa: BLE001
            F.add('reader_error', {'reader': 'deliverable', 'error': repr(e)[:300], 'workbook': 'deliverable'})
        deliverable_wb['present'] = dbytes is not None

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
                    'font_structure', 'pinned_part', 'element_namespace', 'provenance', 'receipt_claim_mismatch',
                    'pinned_template', 'deliverable_name')
    unclassified = sorted(k for k in F.items if k not in value_checks and k != 'formatting')
    value_fail = sum(F.count(k) for k in value_checks) + sum(F.count(k) for k in unclassified)
    fmt_fail = F.count('formatting')
    status = 'SAVED_ALL_CELL_VALUE_TYPE_PASS' if value_fail == 0 and (not formatting or fmt_fail == 0) else 'SAVED_QA_FAILED'
    import openpyxl
    return {
        'schema': 'cps.export.saved-qa.v1', 'tool': VERSION, 'status': status,
        'xlsx': {'file': xlsx.name, 'sha256': sha256(xbytes) if xbytes is not None else None,
                 'bytes': len(xbytes) if xbytes is not None else None,
                 'role': 'the four-sheet workbook (internal QA workbook when titled)'},
        'deliverable_xlsx': deliverable_wb,
        'expected_saved_values': {'file': exp_path.name, 'sha256': sha256(ebytes)},
        'writer_receipt_present': receipt is not None,
        'deliverable': deliverable,
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
                                                                  'cell_value_children', 'number_text', 'duplicate_reference', 'font_structure',
                                                                  'pinned_part', 'element_namespace', 'pinned_template')),
                   'deliverable_name_failures': F.count('deliverable_name'),
                   'deliverable_workbook_findings': sum(1 for v in F.items.values() for e in v if isinstance(e, dict) and e.get('workbook') == 'deliverable'),
                   'deliverable_formatting_cells_checked': deliverable_wb.get('formatting_cells_checked'),
                   'provenance_failures': F.count('provenance'), 'receipt_claim_mismatches': F.count('receipt_claim_mismatch'),
                   'expected_provenance_checked': bool(provenance.get('checked')),
                   'formatting_failures': fmt_fail if formatting else None,
                   'formatting_cells_checked': fmt_checked, 'value_check_failures': value_fail},
        'header_checks': header_checks,
        'excel_limits_checked': EXCEL,
        'literal_error_text_cells': {'count': len(error_text), 'first': error_text[:50],
                                     'note': 'informational, like writer004 ERROR_SCAN: carried text may legitimately contain error text'},
        'findings': F.report(),
        'scope': ('Saved-workbook fidelity to the writer matrix (EXPECTED_SAVED_VALUES.json) and package structure; with --carrier and '
                  '--writer-dir also the provenance of EXPECTED and of the xlsx from the carrier (a writer rerun) and the receipt fields '
                  'saved QA compares. Not source semantics, not what @oai/artifact-tool would have saved (L2-L5), not Excel display, '
                  'not visual QA.'),
        'cps_evidence_preconditions': evidence_preconditions(status, provenance, formatting, deliverable, deliverable_wb),
        'native_excel_validation': False, 'openpyxl': openpyxl.__version__,
    }


def evidence_preconditions(status, provenance, formatting, deliverable=None, deliverable_wb=None):
    """README "Conditions of use": what this report can show of them. The carrier check against the route convert receipt
    or the freeze record is the operator's, the job-title check against the harness's per-job input too (v5, O33), and
    visual QA is a separate reviewer's."""
    cn = provenance.get('checker_node') or {}
    pinned = bool(provenance.get('checked') and cn.get('pinned') and cn.get('sha256_verified')
                  and cn.get('sha256_after_check') == cn.get('sha256'))
    out = {'provenance_checked': bool(provenance.get('checked')), 'provenance_result': provenance.get('result'),
           'formatting_checked': bool(formatting), 'pinned_checker_node': pinned,
           'checker_node': ({k: cn.get(k) for k in ('executable', 'realpath', 'sha256', 'pinned_sha256', 'version')} if cn else None),
           'job_title': (deliverable or {}).get('job_title'), 'xlsx_file': (deliverable or {}).get('xlsx_file'),
           'main_sheet': (deliverable or {}).get('main_sheet'), 'qa_workbook_file': (deliverable or {}).get('qa_workbook_file'),
           'deliverable_workbook': bool((deliverable or {}).get('deliverable_workbook')),
           'deliverable_checked': bool((deliverable_wb or {}).get('checked')),
           'deliverable_byte_identical_to_rerun': provenance.get('deliverable_xlsx_byte_identical')}
    deliv_ok = not out['deliverable_workbook'] or (out['deliverable_checked'] and out['deliverable_byte_identical_to_rerun'] is True)
    out['all_checked_here_met'] = bool(status == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' and out['provenance_result'] == 'PASS'
                                       and out['formatting_checked'] and pinned and deliv_ok)
    out['note'] = ('CPS evidence needs all of these (README "Conditions of use"): status PASS; provenance checked with result PASS; '
                   'formatting checked (a run with --no-formatting is not CPS evidence); the checker node pinned by --checker-node '
                   'and --checker-node-sha256 from the admission record (pinned_checker_node). all_checked_here_met says whether '
                   'they hold. Not checked here: that --carrier is the frozen route carrier (expected_provenance.carrier_sha256 '
                   'against the route convert receipt or the freeze record), that job_title is the harness\'s per-job project '
                   'folder title for this job (the file and sheet names are derived from it here), and the visual QA.')
    return out


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
    ap.add_argument('--checker-node', help='required for CPS evidence: absolute path of the checker\'s node binary (with '
                                           '--checker-node-sha256); every node call of the provenance check runs it')
    ap.add_argument('--checker-node-sha256', help='the sha256 of the checker node binary, from the admission record')
    ap.add_argument('--node', help='unpinned node for the provenance check (default: node from PATH); not CPS evidence')
    a = ap.parse_args(argv)
    if bool(a.carrier) != bool(a.writer_dir):
        ap.error('--carrier and --writer-dir go together')
    if bool(a.checker_node) != bool(a.checker_node_sha256):
        ap.error('--checker-node and --checker-node-sha256 go together')
    if a.checker_node and a.node:
        ap.error('--checker-node and --node exclude each other')
    if a.checker_node and not a.carrier:
        ap.error('--checker-node pins the node of the provenance check: it needs --carrier and --writer-dir')
    if a.checker_node and not os.path.isabs(a.checker_node):
        ap.error('--checker-node must be an absolute path')
    pin = a.checker_node_sha256.lower() if a.checker_node_sha256 else None
    if pin is not None and not SHA256_RE.fullmatch(pin):
        ap.error('--checker-node-sha256 must be 64 hexadecimal digits')
    out_dir = Path(a.output_dir).resolve(strict=True)
    carrier = Path(a.carrier).resolve(strict=True) if a.carrier else None
    writer_dir = Path(a.writer_dir).absolute() if a.writer_dir else None
    report_path = Path(a.report) if a.report else out_dir / 'SAVED_QA.json'

    def workbooks():                            # v5: every .xlsx of the output directory (the name is derived, O33)
        return {q.name: sha256(q.read_bytes()) for q in sorted(out_dir.iterdir()) if q.is_file() and q.name.lower().endswith('.xlsx')}
    before = workbooks()
    try:
        rep = run_qa(out_dir, formatting=not a.no_formatting, carrier=carrier, writer_dir=writer_dir,
                     node=a.checker_node or a.node or 'node', checker_node_sha256=pin)
    except Exception as e:                      # noqa: BLE001 - never crash without a report
        rep = {'schema': 'cps.export.saved-qa.v1', 'tool': VERSION, 'status': 'SAVED_QA_FAILED',
               'findings': {'qa_error': {'count': 1, 'first': [repr(e)[:1000]]}}, 'totals': {'value_check_failures': 1}}
    if workbooks() != before:
        rep['status'] = 'SAVED_QA_FAILED'
        rep.setdefault('findings', {})['workbook_changed_during_qa'] = {'count': 1}
        if isinstance(rep.get('cps_evidence_preconditions'), dict):
            rep['cps_evidence_preconditions']['all_checked_here_met'] = False
    with open(report_path, 'xb') as f:
        f.write(dump(rep))
    print(json.dumps({'status': rep['status'], 'report': str(report_path), **rep['totals']}, ensure_ascii=False))
    return 0 if rep['status'] == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
