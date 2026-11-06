"""Invented saved-QA tamper fixtures (review 2026-11-04, ADMIT_AFTER_LISTED_FIXES). No project data.

  carrier BASE OUT   The reviewer's fidelity probe carrier (p01_fidelity), derived from the invented export fixture
                     v01_base: numeric-looking, date-looking and error-literal text, CR/LF/NEL/TAB, leading/trailing
                     spaces, 17-digit doubles, 1e-7, the denormal 5e-324, -0, JavaScript key order in metadata, a
                     formula-like and an error-literal nonitem text, a lone surrogate inside JSON review text.
  tamper SRC DEST    From a writer output SRC (made from that carrier), the reviewer's 22 tampered outputs T01..T22
                     plus extra structural tampers X01..X16, the second review's N01..N07, N10, N11 (review round 2,
                     s2_tampers.py), the third review's B01..B06 (round 3, r3_bypasses.py, verbatim edits) and the
                     consistent EXPECTED+xlsx variants C1..C3, each in its own directory, and DEST/TAMPERS.json with the
                     finding each one must produce.
  downgrade SRC DEST From a --mode v2 writer output SRC of a carrier without O13/R57 (same bytes as v1), the second
                     review's receipt-mode downgrade (F2, s3_attacks2.py): D1 the N01 tamper with the receipt mode kept
                     v2, D2 the same with the receipt mode edited to v1, D3 a change no structural check sees (pane
                     ySplit, the second review's N12) with the receipt mode edited to v1; DEST/TAMPERS.json as above.
  receipt SRC DEST   From a writer output SRC, copies whose WRITER_RECEIPT.json claims are edited and whose xlsx and
                     EXPECTED_SAVED_VALUES.json are unchanged (third review G3, its p1/): for a relaxed v2 output the
                     reviewer's falsified receipt (its eight edits together) and each edit on its own, plus edits of the
                     other compared fields; for an output without relaxations, mode and relaxation edits.
                     DEST/TAMPERS.json lists the receipt fields saved QA must name (receipt_claim_mismatch).
  naming SRC DEST TITLE2
                     Writer v2.6, owner decisions O33-O34: from a writer output SRC made with --job-title, tampers of the file
                     name, the main sheet name, the receipt's job title and deliverable fields, xl/workbook.xml outside the name,
                     and the G/H shading (K01..K12; TITLE2 is a second invented job title); DEST/TAMPERS.json lists the findings
                     each must produce and whether provenance catches it (K12, a consistent re-titling, passes: the job title is
                     the operator's check).
  deliverable SRC DEST
                     Writer v2.7, owner decision O38: from a titled writer output SRC, tampers of the one-sheet deliverable <name>.xlsx
                     (L01..L16: a value, gridlines hidden, columns frozen, the four-sheet workbook delivered, header fill, header
                     style, missing, wrapping, a stale receipt hash, the sheet renamed, a row height, an extra cell, a number as
                     text, the receipt's deliverable_xlsx dropped, a consistent change of all three files, a hidden column);
                     DEST/TAMPERS.json lists the findings each must produce (deliverable findings carry workbook "deliverable").
  The tamper set also holds group o34 (writer v2.6): G/H shaded again, through styles.xml or through the header style.
  v2.7 (O38): a titled output also holds the deliverable <name>.xlsx; the naming tampers copy it unchanged unless the tamper is
  about it, and the internal four-sheet workbook INTERNAL_QA_WORKBOOK.xlsx (the receipt's output_xlsx.file) is the one edited.
  v2.6: B01/B02 address the empty G2/H2 cells by the body style s="2" (O34 removed the G/H style s="4").
Usage: python3 -I -B make_tamper_fixtures.py carrier /abs/v01_base.json /abs/new.json
       python3 -I -B make_tamper_fixtures.py tamper /abs/writer-output /abs/new-dir
       python3 -I -B make_tamper_fixtures.py downgrade /abs/writer-output-mode-v2 /abs/new-dir
       python3 -I -B make_tamper_fixtures.py receipt /abs/writer-output /abs/new-dir
       python3 -I -B make_tamper_fixtures.py naming /abs/titled-writer-output /abs/new-dir "<second invented job title>"
       python3 -I -B make_tamper_fixtures.py deliverable /abs/titled-writer-output /abs/new-dir
"""
import copy, hashlib, importlib.util, json, re, shutil, sys, zipfile
from pathlib import Path

COLS = 'ABCDEFGHIJKLMNOPQ'
S1, WB, ST = 'xl/worksheets/sheet1.xml', 'xl/workbook.xml', 'xl/styles.xml'
HERE = Path(__file__).resolve().parent
DEFAULT_XLSX = 'research-draft.xlsx'


def xlsx_name(d):
    """The workbook file of a writer output directory: the receipt's output_xlsx.file (v2.6: <name>.xlsx with --job-title)."""
    try:
        return json.loads((d / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))['output_xlsx']['file']
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_XLSX


def writer_module():
    spec = importlib.util.spec_from_file_location('writer_portable_for_fixtures', HERE.parent / 'writer_portable.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- the reviewer's fidelity carrier (mk_probes.py p01)
def fidelity_carrier(base):
    c = copy.deepcopy(base)

    def it(i):
        return next(x for x in c['items'] + c['components'] if x['id'] == i)

    def loc_ev(r, raw_text):
        return {'location': {'sheet': r['location']['sheet'], 'cells': [r['location']['cells'][0]], 'views': list(r['location']['views'])},
                'anchor': r['anchor'], 'raw_text': raw_text, 'transformation': 'reviewer probe'}

    def setv(iid, col, v, raw_text=None):
        r = it(iid)
        r['values'][COLS.index(col)] = v
        r['null_reasons'].pop(col, None)
        r['evidence'][col] = loc_ev(r, raw_text if raw_text is not None else (v if isinstance(v, str) else repr(v)))
        return r

    def setq(iid, v, text):
        setv(iid, 'F', v, text)
        it(iid)['raw']['quantity'] = text
    texty = {('R001', 'D'): '123', ('R002', 'D'): '2024/01/01', ('R003', 'D'): '#N/A', ('R004', 'D'): 'TRUE', ('R005', 'D'): '1e5',
             ('R006', 'D'): ' 0012 ', ('R003', 'I'): '#DIV/0!', ('R003', 'J'): 'FALSE', ('R002', 'I'): '50%', ('R002', 'J'): '$1,234',
             ('R001', 'I'): 'a\rb', ('R001', 'J'): 'a\r\nb\u2028c\u0085d\te', ('R004', 'I'): ']]><x/>&amp;', ('R004', 'J'): 'AB_x004_x12_',
             ('R005', 'I'): '12:30', ('R005', 'J'): '3/4', ('R006', 'I'): '１２３', ('R007', 'D'): '0x1F',
             ('R007', 'I'): '1.0', ('R007', 'J'): '00123'}
    for (i, col), v in texty.items():
        setv(i, col, v)
    setq('R001', 0.30000000000000004, '0.30000000000000004')
    setq('R002', 1e-7, '0.0000001')
    setq('R003', 4503599627370497.0, '4503599627370497')
    setq('R004', 5e-324, '0.' + '0' * 323 + '5')
    setq('R005', -0.0, '-0')
    setq('R006', 0.7999999999999999, '0.7999999999999999')
    setv('R006', 'P', 123456789.12345678, '123,456,789.12345678')
    setv('R003', 'P', 1.0000000000000002, '1.0000000000000002')
    setv('R005', 'Q', 1e-6, '0.000001')['raw']['unit_price'] = '0.000001'
    setv('R002', 'Q', 1234567.0, '1,234,567')['raw']['unit_price'] = '1,234,567'
    c['metadata'] = {'zeta': 1, '10': 1e-7, '2': [1, 2.5, -0.0], 'a': {'1': 5e-324, 'b': 'x', '0': None}, '': 'empty key',
                     '4294967295': 'not index', '01': 'not index', '4294967294': 'index', **c['metadata']}
    c['nonitems'][0]['text'] = '=SUM(A1)'
    c['nonitems'][1]['text'] = '#REF!'
    c['limitations'].append('a lone \ud800 surrogate only inside JSON review text')
    return c


# ---------------------------------------------------------------- tampers
def sub1(pat, rep):
    def f(x):
        y, n = re.subn(pat, rep, x, count=1)
        assert n == 1, pat
        return y
    return f


def styles_white(x):
    y, n = re.subn(r'rgb="FF172033"', 'rgb="FFFFFFFF"', x)
    assert n >= 1
    return y


def numfmt_hide(x):
    y = x.replace('<numFmts count="0"/>', '<numFmts count="1"><numFmt numFmtId="164" formatCode=";;;"/></numFmts>', 1)
    z = y.replace('<xf numFmtId="0" fontId="1" fillId="0" borderId="0" applyAlignment="1"',
                  '<xf numFmtId="164" fontId="1" fillId="0" borderId="0" applyNumberFormat="1" applyAlignment="1"', 1)
    assert x != y != z
    return z


# name: (edits {part: fn}, finding each must produce without provenance; None = passes without provenance)
REVIEWER_TAMPERS = {
    'T01_number_text_rounded': ({S1: sub1(r'<v>0\.30000000000000004</v>', '<v>0.3</v>')}, 'value_type_mismatch'),
    'T02_text_123_to_number': ({S1: sub1(r'<c r="D2" s="2" t="inlineStr"><is><t>123</t></is></c>', '<c r="D2" s="2"><v>123</v></c>')}, 'value_type_mismatch'),
    'T03_formula_with_cached_value': ({S1: sub1(r'<c r="F3" s="3" t="n"><v>1e-7</v></c>', '<c r="F3" s="3"><f>1/10000000</f><v>1e-7</v></c>')}, 'formula'),
    'T04_sheet_order_swapped': ({WB: sub1(r'(<sheet [^>]*name="未填研究草稿"[^>]*/>)(<sheet [^>]*name="來源與審查"[^>]*/>)', r'\2\1')}, 'sheet_order'),
    'T05_main_sheet_hidden': ({WB: sub1(r'name="未填研究草稿" sheetId="1" state="visible"', 'name="未填研究草稿" sheetId="1" state="hidden"')}, 'sheet_state'),
    'T06_column_D_hidden': ({S1: sub1(r'<col width="48" customWidth="1" min="4" max="4"/>', '<col width="48" customWidth="1" hidden="1" min="4" max="4"/>')}, 'hidden_attribute'),
    'T07_row3_hidden': ({S1: sub1(r'<row r="3"', '<row r="3" hidden="1"')}, 'hidden_attribute'),
    'T08_all_rows_zero_height_default': ({S1: sub1(r'<sheetFormatPr ', '<sheetFormatPr zeroHeight="1" ')}, 'hidden_attribute'),
    'T09_conditional_format_white_text': ({S1: sub1(r'</sheetData>', '</sheetData><conditionalFormatting sqref="A2:Q8"><cfRule type="expression" dxfId="0" priority="1"><formula>TRUE</formula></cfRule></conditionalFormatting>'),
                                           ST: sub1(r'</cellStyles>', '</cellStyles><dxfs count="1"><dxf><font><color rgb="FFFFFFFF"/></font></dxf></dxfs>')}, 'worksheet_structure'),
    'T10_body_numfmt_hide': ({ST: numfmt_hide}, 'formatting'),
    'T11_t_str_cell': ({S1: sub1(r'<c r="D2" s="2" t="inlineStr"><is><t>123</t></is></c>', '<c r="D2" s="2" t="str"><v>123</v></c>')}, 'formula'),
    'T12_date_cell': ({S1: sub1(r'<c r="D3" s="2" t="inlineStr"><is><t>2024/01/01</t></is></c>', '<c r="D3" s="2" t="d"><v>2024-01-01T00:00:00</v></c>')}, 'unknown_cell_type'),
    'T13_header_text_changed': ({S1: sub1(r'<c r="Q1" s="1" t="inlineStr"><is><t>[^<]*</t></is></c>', '<c r="Q1" s="1" t="inlineStr"><is><t>合約單價</t></is></c>')}, 'header_row'),
    'T14_cr_lost': ({S1: sub1(r'a&#13;b', 'a\nb')}, 'value_type_mismatch'),
    'T15_trailing_space_preserve_dropped': ({S1: sub1(r'<t xml:space="preserve"> 0012 </t>', '<t> 0012 </t>')}, 'whitespace_not_preserved'),
    'T16_print_area_defined_name': ({WB: sub1(r'</sheets>', '</sheets><definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">\'未填研究草稿\'!$A$1:$C$8</definedName></definedNames>')}, 'defined_names'),
    'T17_freeze_removed': ({S1: sub1(r'<pane [^>]*/>', '')}, 'formatting'),
    'T18_data_validation_formula': ({S1: sub1(r'</sheetData>', '</sheetData><dataValidations count="1"><dataValidation type="custom" sqref="A2:Q8"><formula1>FALSE</formula1></dataValidation></dataValidations>')}, 'worksheet_structure'),
    'T19_zoom_1pct_view': ({S1: sub1(r'<sheetView ', '<sheetView zoomScale="10" ')}, 'worksheet_structure'),
    'T20_font_white_body': ({ST: styles_white}, 'formatting'),
}
EXTRA_TAMPERS = {
    'X01_extra_part_comments': ({'+xl/comments1.xml': lambda x: '<comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'}, 'zip_parts'),
    'X02_rich_text_run_white': ({S1: sub1(r'<c r="D2" s="2" t="inlineStr"><is><t>123</t></is></c>',
                                          '<c r="D2" s="2" t="inlineStr"><is><r><rPr><color rgb="FFFFFFFF"/></rPr><t>123</t></r></is></c>')}, 'worksheet_structure'),
    'X03_workbook_window_hidden': ({WB: sub1(r'<workbookView visibility="visible"', '<workbookView visibility="hidden"')}, 'workbook_structure'),
    'X04_show_zeros_off': ({S1: sub1(r'<sheetView ', '<sheetView showZeros="0" ')}, 'worksheet_structure'),
    'X05_duplicate_zip_entry': ({'+' + S1: lambda x: '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>'}, 'zip_parts'),
    'X06_protection_hidden': ({ST: sub1(r'<alignment vertical="top" wrapText="1"/></xf>', '<alignment vertical="top" wrapText="1"/><protection hidden="1"/></xf>')}, 'hidden_attribute'),
    'X07_row_tiny_height': ({S1: sub1(r'<row r="3"', '<row r="3" ht="1" customHeight="1"')}, 'worksheet_structure'),
    'X08_style_index_out_of_range': ({S1: sub1(r'<c r="D2" s="2"', '<c r="D2" s="99"')}, 'any'),
    'X09_not_a_zip': ({'=': lambda x: b'not a zip file'}, 'any'),
}


# Second review (round 2, F1): tampers LibreOffice reads differently from the three Python readers (s2_tampers.py,
# verbatim edits). N04/N05 (duplicates first; LibreOffice is last-wins like Python) and N11 (superscript) are added
# because the checks for them were added too.
D2_CELL = '<c r="D2" s="2" t="inlineStr"><is><t>123</t></is></c>'
BODY_FONT = r'<font><name val="Arial"/><color rgb="FF172033"/>'
REVIEW2_TAMPERS = {
    'N01_second_v_in_number_cell': ({S1: sub1(r'<v>0\.30000000000000004</v>', '<v>0.30000000000000004</v><v>999</v>')}, 'cell_value_children'),
    'N02_second_is_in_string_cell': ({S1: sub1(re.escape(D2_CELL), '<c r="D2" s="2" t="inlineStr"><is><t>123</t></is><is><t>EVIL</t></is></c>')}, 'cell_value_children'),
    'N03_v_beside_is': ({S1: sub1(re.escape(D2_CELL), '<c r="D2" s="2" t="inlineStr"><v>EVIL</v><is><t>123</t></is></c>')}, 'cell_value_children'),
    'N04_duplicate_cell_ref_first': ({S1: sub1(re.escape('<c r="C2" s="2" t="inlineStr">'),
                                                '<c r="C2" s="2" t="inlineStr"><is><t>EVIL</t></is></c><c r="C2" s="2" t="inlineStr">')}, 'duplicate_reference'),
    'N05_duplicate_row_first': ({S1: sub1(r'<row r="2">', '<row r="2"><c r="A2" s="2" t="inlineStr"><is><t>EVIL</t></is></c></row><row r="2">')}, 'duplicate_reference'),
    'N06_number_text_underscore': ({S1: sub1(r'<v>1234567</v>', '<v>1_234_567</v>')}, 'number_text'),
    'N07_number_text_fullwidth': ({S1: sub1(r'<v>1234567</v>', '<v>\uff11\uff12\uff13\uff14\uff15\uff16\uff17</v>')}, 'number_text'),
    'N10_strike_body_font': ({ST: sub1(BODY_FONT, '<font><name val="Arial"/><strike val="1"/><color rgb="FF172033"/>')}, 'font_structure'),
    'N11_superscript_body_font': ({ST: sub1(BODY_FONT, '<font><name val="Arial"/><vertAlign val="superscript"/><color rgb="FF172033"/>')}, 'font_structure'),
}
# Extra checks of saved_qa v3 beyond the second review's list, one tamper each.
EXTRA_TAMPERS.update({
    'X10_t_child_element': ({S1: sub1(re.escape(D2_CELL), '<c r="D2" s="2" t="inlineStr"><is><t>12<b/>3</t></is></c>')}, 'cell_value_children'),
    'X11_v_child_element': ({S1: sub1(r'<v>1234567</v>', '<v>1234567<b/></v>')}, 'cell_value_children'),
    'X12_cell_ref_outside_its_row': ({S1: sub1(r'<c r="B2" ', '<c r="B9" ')}, 'worksheet_structure'),
    'X13_cells_out_of_order': ({S1: sub1(r'(<c r="A2" [^>]*><is><t>[^<]*</t></is></c>)(<c r="B2" [^>]*><is><t>[^<]*</t></is></c>)', r'\2\1')}, 'worksheet_structure'),
    'X14_number_text_leading_space': ({S1: sub1(r'<v>1234567</v>', '<v> 1234567</v>')}, 'number_text'),
    'X15_number_text_uppercase_exponent': ({S1: sub1(r'<v>1e-7</v>', '<v>1E-7</v>')}, 'number_text'),
    'X16_font_second_color': ({ST: sub1(BODY_FONT, '<font><name val="Arial"/><color rgb="FF172033"/><color rgb="FFFFFFFF"/>')}, 'font_structure'),
})
# Third review (round 3, G1): tampers that saved QA v3 passed without provenance while LibreOffice reads them differently
# (r3_bypasses.py, verbatim edits): Strict-namespace value children and cells (LibreOffice maps the Strict namespace to the
# transitional one), a colour tint on the body font or the header fill (openpyxl's rgb ignores tint), and foreign-namespace
# fonts that shift openpyxl's font indices but not LibreOffice's.
STRICT = 'http://purl.oclc.org/ooxml/spreadsheetml/main'       # ISO 29500 Strict SpreadsheetML namespace
FOREIGN = 'urn:invented:cps-review3'                            # an unknown namespace
R3_FONT0 = '<font><name val="Calibri"/><family val="2"/><color theme="1"/><sz val="11"/><scheme val="minor"/></font>'
R3_BODY_FONT = '<font><name val="Arial"/><color rgb="FF172033"/><sz val="11"/></font>'
R3_HEAD_FONT = '<font><name val="Arial"/><b val="1"/><color rgb="FFFFFFFF"/><sz val="11"/></font>'
REVIEW3_TAMPERS = {
    'B01_strict_ns_v_in_empty_G2': ({S1: sub1(re.escape('<c r="G2" s="2" t="n"></c>'),
                                              f'<c r="G2" s="2" t="n"><v xmlns="{STRICT}">999</v></c>')}, 'element_namespace'),
    'B02_strict_ns_is_in_empty_H2': ({S1: sub1(re.escape('<c r="H2" s="2" t="n"></c>'),
                                               f'<c r="H2" s="2" t="inlineStr"><is xmlns="{STRICT}"><t>EVIL</t></is></c>')}, 'element_namespace'),
    'B03_strict_ns_cell_beyond_Q2': ({S1: sub1(re.escape('<c r="Q2" s="3" t="n"></c></row>'),
                                               f'<c r="Q2" s="3" t="n"></c><c xmlns="{STRICT}" r="R2" t="inlineStr"><is><t>EVIL</t></is></c></row>')},
                                     'element_namespace'),
    'B04_body_font_color_tint': ({ST: sub1(re.escape('<color rgb="FF172033"/>'), '<color rgb="FF172033" tint="0.95"/>')}, 'pinned_part'),
    'B05_header_fill_tint': ({ST: sub1(re.escape('<fgColor rgb="FF29445D"/>'), '<fgColor rgb="FF29445D" tint="0.95"/>')}, 'pinned_part'),
    'B06_foreign_ns_fonts_shift_index': ({ST: sub1(re.escape('<fonts count="3">' + R3_FONT0 + R3_BODY_FONT),
                                                   '<fonts count="3">' + R3_FONT0
                                                   + R3_BODY_FONT.replace('<font>', f'<x:font xmlns:x="{FOREIGN}">').replace('</font>', '</x:font>')
                                                   + R3_HEAD_FONT.replace('<font>', f'<x:font xmlns:x="{FOREIGN}">').replace('</font>', '</x:font>')
                                                   + R3_BODY_FONT.replace('FF172033', 'FFFFFFFF'))}, 'pinned_part'),
}
# Writer v2.6, owner decision O34: G and H (單價, 複價) shaded again. a: the v2.5 grey (#F1F3F5) fill and cell format restored in
# styles.xml and given to the G/H body cells (styles.xml then differs from its pin; the formatting check also sees the fill);
# b: the G/H body cells given the header cell format s="1" (fill #29445D), styles.xml unchanged, so only the formatting check
# can see it.
GREY_FILL = '<fill><patternFill patternType="solid"><fgColor rgb="FFF1F3F5"/></patternFill></fill>'
GREY_XF = ('<xf numFmtId="0" fontId="1" fillId="3" borderId="0" applyAlignment="1" pivotButton="0" quotePrefix="0" xfId="0">'
           '<alignment vertical="top" wrapText="1"/></xf>')
GH_BODY = r'(<c r="[GH](?:[2-9]|[1-9][0-9]+)" s=")2(")'


def styles_grey_restored(x):
    y = x.replace('<fills count="3">', '<fills count="4">', 1).replace('</fills>', GREY_FILL + '</fills>', 1)
    z = y.replace('<cellXfs count="4">', '<cellXfs count="5">', 1).replace('</cellXfs>', GREY_XF + '</cellXfs>', 1)
    assert x != y != z and z.count('FFF1F3F5') == 1
    return z


def gh_style(index):
    def f(x):
        y, n = re.subn(GH_BODY, r'\g<1>' + index + r'\g<2>', x)
        assert n >= 2
        return y
    return f


O34_TAMPERS = {
    'O34a_gh_grey_fill_restored': ({ST: styles_grey_restored, S1: gh_style('4')}, 'pinned_part'),
    'O34b_gh_header_style_fill': ({S1: gh_style('1')}, 'formatting'),
}
# Receipt-mode downgrade (second review F2): name -> (edits, receipt mode to write, finding without provenance or None,
# receipt fields saved QA v4 names in receipt_claim_mismatch: a v1 claim on a v2 receipt keeps the v2 relaxations record)
DOWNGRADE_TAMPERS = {
    'D1_v2_output_second_v_mode_kept': ({S1: REVIEW2_TAMPERS['N01_second_v_in_number_cell'][0][S1]}, 'v2', 'cell_value_children', []),
    'D2_v2_output_second_v_mode_downgraded_to_v1': ({S1: REVIEW2_TAMPERS['N01_second_v_in_number_cell'][0][S1]}, 'v1', 'cell_value_children',
                                                    ['relaxations']),
    'D3_v2_output_pane_ysplit_mode_downgraded_to_v1': ({S1: sub1(r'ySplit="1" topLeftCell="D2"', 'ySplit="60" topLeftCell="D2"')}, 'v1', None,
                                                       ['relaxations']),
}


# Third review G3 (its p1/): receipt claims edited, xlsx and EXPECTED unchanged. name -> (edit of the receipt dict, fields
# saved QA must name in receipt_claim_mismatch; [] = not a compared field, the claim passes and is shown only)
def _reviewer_falsified(r):
    """The third reviewer's p1 receipt, its eight edits together."""
    r['node_environment']['node']['executable'] = '/invented/node'
    r['cross_check']['saved_values_differ_only_in'] = 0
    r['status'] = 'INVENTED_ADMITTED'
    r['expected_saved_values']['identical_to_writer004_prepareMatrices_output'] = True
    r['admitted'] = True
    del r['relaxations']['classes']['r57_null_c_research_draft']
    r['relaxations']['saved_matrices_differ_from_placeholder_copy_only_in']['cells'] = []
    r['writer_files']['writer004.mjs']['identity'] = 'invented identity'


OTHER_WRITER004 = {'85a7f619b9cfedc0c3c851b34c1d8cee38cfe5ab88ed050fcf4bba566c18c0d7': ('70d7f66455bfc5a2a6574b01509cfb78576a21b75bd7d75500746faf2661efb7',
                                                                                        'public copy (helper path redacted)'),
                   '70d7f66455bfc5a2a6574b01509cfb78576a21b75bd7d75500746faf2661efb7': ('85a7f619b9cfedc0c3c851b34c1d8cee38cfe5ab88ed050fcf4bba566c18c0d7',
                                                                                        'archived original')}


def _other_writer004(r):
    """Claim the other pinned writer004.mjs (both pins are allowed; the rerun's writer directory holds one of them)."""
    h, ident = OTHER_WRITER004[r['writer_files']['writer004.mjs']['sha256']]
    r['writer_files']['writer004.mjs'] = {'sha256': h, 'identity': ident}


RECEIPT_TAMPERS_RELAXED = {
    'P1_reviewer_falsified_receipt': (_reviewer_falsified, ['relaxations', 'cross_check', 'expected_saved_values', 'writer_files', 'status', 'admitted']),
    'P1a_r57_class_removed': ((lambda r: r['relaxations']['classes'].pop('r57_null_c_research_draft')), ['relaxations']),
    'P1b_documented_cells_emptied': ((lambda r: (r['relaxations']['saved_matrices_differ_from_placeholder_copy_only_in'].__setitem__('cells', []),
                                                      r['cross_check'].__setitem__('saved_values_differ_only_in', 0))), ['relaxations', 'cross_check']),
    'P1c_identical_to_writer004_claimed': ((lambda r: r['expected_saved_values'].__setitem__('identical_to_writer004_prepareMatrices_output', True)),
                                           ['expected_saved_values']),
    'P1d_writer_files_identity_changed': ((lambda r: r['writer_files']['writer004.mjs'].__setitem__('identity', 'invented identity')), ['writer_files']),
    'P1e_admitted_true': ((lambda r: r.__setitem__('admitted', True)), ['admitted']),
    'P1f_status_changed': ((lambda r: r.__setitem__('status', 'INVENTED_ADMITTED')), ['status']),
    'P1g_node_executable_changed_not_compared': ((lambda r: r['node_environment']['node'].__setitem__('executable', '/invented/node')), []),
    'P2_mode_edited_to_v1': ((lambda r: r.__setitem__('mode', 'v1')), ['mode']),
    'P3_writer_version_changed': ((lambda r: r.__setitem__('writer', 'cps-export-writer-portable.v0-invented')), ['writer']),
    'P4_matrices_sha256_changed': ((lambda r: r['matrices_sha256'].__setitem__(next(iter(r['matrices_sha256'])), '0' * 64)), ['matrices_sha256']),
    'P5_sheets_rows_changed': ((lambda r: r['sheets'][0].__setitem__('rows', r['sheets'][0]['rows'] + 1)), ['sheets']),
    'P6_admitted_zero_not_false': ((lambda r: r.__setitem__('admitted', 0)), ['admitted']),
    'P7_other_pinned_writer004_claimed': (_other_writer004, ['writer_files']),
    'P8_o16_items_emptied': ((lambda r: r['relaxations']['classes']['o16_q_unverified_adoption'].__setitem__('items', [])), ['relaxations']),
    'P9_route_port_path_changed_not_compared': ((lambda r: r['relaxations']['route_v4_port'].__setitem__('path', '/elsewhere/cps046b_route.py')), []),
}
RECEIPT_TAMPERS_PLAIN = {
    'Q1_cross_check_result_changed': ((lambda r: r['cross_check'].__setitem__('result', 'BYTE_IDENTICAL_ON_PLACEHOLDER_COPY')), ['cross_check']),
    'Q2_mode_edited_to_v2': ((lambda r: r.__setitem__('mode', 'v2')), ['relaxations']),
    'Q3_relaxations_claimed_applied': ((lambda r: r['relaxations'].__setitem__('applied', True)), ['relaxations']),
    'Q4_expected_saved_values_claim_dropped': ((lambda r: r['expected_saved_values'].pop('identical_to_writer004_prepareMatrices_output')),
                                               ['expected_saved_values']),
    'Q5_status_field_removed': ((lambda r: r.pop('status')), ['status']),
}


def write_tampered(src_xlsx, dst_xlsx, edits):
    if '=' in edits:
        dst_xlsx.write_bytes(edits['='](None))
        return
    with zipfile.ZipFile(src_xlsx) as zi, zipfile.ZipFile(dst_xlsx, 'w', zipfile.ZIP_DEFLATED) as zo:
        for info in zi.infolist():
            data = zi.read(info.filename)
            if info.filename in edits:
                data = edits[info.filename](data.decode('utf-8')).encode('utf-8')
            zo.writestr(info, data)
        for k, f in edits.items():
            if k.startswith('+'):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')          # X05 writes a duplicate entry on purpose
                    zo.writestr(zipfile.ZipInfo(k[1:], date_time=(1980, 1, 1, 0, 0, 0)), f(None).encode('utf-8'))


def update_receipt(d):
    r = json.loads((d / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
    r['output_xlsx']['sha256'] = sha((d / r['output_xlsx']['file']).read_bytes())
    dx = r.get('deliverable_xlsx')
    if isinstance(dx, dict) and (d / dx['file']).is_file():          # v2.7 (O38): the deliverable's hash and size too
        dx['sha256'] = sha((d / dx['file']).read_bytes())
        dx['bytes'] = len((d / dx['file']).read_bytes())
    r['expected_saved_values']['sha256'] = sha((d / 'EXPECTED_SAVED_VALUES.json').read_bytes())
    (d / 'WRITER_RECEIPT.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def o39_width(main_rows, j):
    """Writer v2.8 (O39) width of deliverable column j (0-based) for MAIN_ROWS: the tests' own copy of the rule (23 per non-ASCII
    character, 22 per M W m w @ %, 18 per other ASCII capital, 15 per other ASCII character, plus 10; at least the O38 width;
    counts of writer v2.8.1)."""
    mins = [16.1, 23.1, 21.3, 81.9, 6.9, 8.3, 12.9, 13.0, 12.3, 13.0, 21.4, 11.0, 24.1, 34.1, 10.3, 13.0, 8.1]

    def fit(v):
        if not isinstance(v, str) or v == '':
            return 0 if not isinstance(v, (int, float)) or isinstance(v, bool) else None
        return sum(0 if ch in '\r\n' else 24 if ord(ch) > 0x7e else 22 if ch in 'MWmw@%' else 18 if 'A' <= ch <= 'Z' else 15
                   for ch in v) + 10
    need = [fit(r[j]) for r in main_rows if j < len(r)]
    assert None not in need, 'o39_width: numbers are not used by the tampers'
    return min(max(round(mins[j] * 10), max(need or [0])), 2550) / 10


def consistent_change(src, d):
    """Change main-sheet C2 consistently in EXPECTED_SAVED_VALUES.json (bytes otherwise unchanged) and in the xlsx."""
    text = (src / 'EXPECTED_SAVED_VALUES.json').read_text(encoding='utf-8')
    doc = json.loads(text)
    old = doc['sheets'][0]['values'][1][2]
    new = old + ' tampered'
    k = text.index(json.dumps(old, ensure_ascii=False))
    text2 = text[:k] + json.dumps(new, ensure_ascii=False) + text[k + len(json.dumps(old, ensure_ascii=False)):]
    doc2 = json.loads(text2)
    doc['sheets'][0]['values'][1][2] = new
    assert doc2 == doc
    (d / 'EXPECTED_SAVED_VALUES.json').write_text(text2, encoding='utf-8')
    enc = ''.join(c if ord(c) < 128 else '&#%d;' % ord(c) for c in new)
    write_tampered(src / xlsx_name(src), d / xlsx_name(src),
                   {S1: sub1(r'(<c r="C2" [^>]*><is><t[^>]*>)[^<]*(</t></is></c>)', lambda m: m.group(1) + enc + m.group(2))})


def make_tampers(src, dest, consistent_only=False):
    dest.mkdir(parents=True, exist_ok=False)
    index = []
    groups = [] if consistent_only else [('reviewer', REVIEWER_TAMPERS), ('extra', EXTRA_TAMPERS), ('review2', REVIEW2_TAMPERS),
                                         ('review3', REVIEW3_TAMPERS), ('o34', O34_TAMPERS)]
    xn = xlsx_name(src)
    for group, table in groups:
        for name, (edits, finding) in table.items():
            d = dest / name
            d.mkdir()
            for f in ('EXPECTED_SAVED_VALUES.json', 'WRITER_RECEIPT.json'):
                (d / f).write_bytes((src / f).read_bytes())
            write_tampered(src / xn, d / xn, edits)
            update_receipt(d)          # consistent receipt: the integrity hashes alone cannot catch it
            index.append({'name': name, 'dir': str(d), 'group': group, 'finding': finding, 'passes_without_provenance': False,
                          'provenance_finding': 'provenance'})
    # consistent EXPECTED+xlsx change: C1 receipt left stale, C2 receipt hashes updated (review T21), C3 receipt deleted (T22)
    for name, receipt in (('C1_consistent_receipt_stale', 'stale'), ('C2_consistent_receipt_updated_T21', 'updated'),
                          ('C3_consistent_receipt_deleted_T22', 'deleted')):
        d = dest / name
        d.mkdir()
        (d / 'WRITER_RECEIPT.json').write_bytes((src / 'WRITER_RECEIPT.json').read_bytes())
        consistent_change(src, d)
        if receipt == 'updated':
            update_receipt(d)
        elif receipt == 'deleted':
            (d / 'WRITER_RECEIPT.json').unlink()
        index.append({'name': name, 'dir': str(d), 'group': 'consistent', 'finding': 'integrity' if receipt != 'updated' else None,
                      'passes_without_provenance': receipt == 'updated', 'provenance_finding': 'provenance'})
    (dest / 'TAMPERS.json').write_text(json.dumps({'invented': True, 'source_output': str(src), 'tampers': index},
                                                  ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return index


def make_downgrade(src, dest):
    """The second review's receipt-mode downgrade (F2) from a --mode v2 output of a carrier without O13/R57."""
    rc = json.loads((src / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
    assert rc['mode'] == 'v2' and rc['relaxations']['applied'] is False, 'needs a mode v2 output without O13/R57 relaxations'
    dest.mkdir(parents=True, exist_ok=False)
    index = []
    for name, (edits, mode, finding, claim_fields) in DOWNGRADE_TAMPERS.items():
        d = dest / name
        d.mkdir()
        for f in ('EXPECTED_SAVED_VALUES.json', 'WRITER_RECEIPT.json'):
            (d / f).write_bytes((src / f).read_bytes())
        write_tampered(src / xlsx_name(src), d / xlsx_name(src), edits)
        update_receipt(d)
        r = json.loads((d / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
        r['mode'] = mode
        (d / 'WRITER_RECEIPT.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        index.append({'name': name, 'dir': str(d), 'group': 'downgrade', 'receipt_mode': mode, 'finding': finding,
                      'passes_without_provenance': finding is None, 'provenance_finding': 'provenance',
                      'receipt_claim_fields': claim_fields})
    (dest / 'TAMPERS.json').write_text(json.dumps({'invented': True, 'source_output': str(src), 'tampers': index},
                                                  ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return index


def make_receipt_tampers(src, dest):
    """Third review G3: receipt claims edited, the xlsx and EXPECTED_SAVED_VALUES.json copied unchanged (so the integrity
    hashes still match). A relaxed v2 output gets RECEIPT_TAMPERS_RELAXED, any other output RECEIPT_TAMPERS_PLAIN."""
    base = json.loads((src / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
    relaxed = base['relaxations'].get('applied') is True
    table = RECEIPT_TAMPERS_RELAXED if relaxed else RECEIPT_TAMPERS_PLAIN
    if relaxed:
        assert 'r57_null_c_research_draft' in base['relaxations']['classes'] and base['relaxations']['classes']['r57_null_c_research_draft']['items']
    dest.mkdir(parents=True, exist_ok=False)
    index = []
    for name, (edit, fields) in table.items():
        d = dest / name
        d.mkdir()
        for f in ('EXPECTED_SAVED_VALUES.json', xlsx_name(src)):
            (d / f).write_bytes((src / f).read_bytes())
        r = copy.deepcopy(base)
        edit(r)
        assert json.dumps(r, sort_keys=True) != json.dumps(base, sort_keys=True), name      # 0 == False in Python, not in JSON
        (d / 'WRITER_RECEIPT.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        index.append({'name': name, 'dir': str(d), 'group': 'receipt', 'receipt_claim_fields': fields, 'finding': None,
                      'passes_without_provenance': True, 'source_relaxed': relaxed})
    (dest / 'TAMPERS.json').write_text(json.dumps({'invented': True, 'source_output': str(src), 'tampers': index},
                                                  ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return index


# ---------------------------------------------------------------- writer v2.6, owner decisions O33-O34: naming tampers
def make_naming_tampers(src, dest, title2):
    """From a titled writer output SRC. Each entry: findings saved QA must report without provenance (all of them; 'only':
    exactly these), and 'provenance': 'provenance' (fails with a provenance finding), 'fails' (fails, by its own findings) or
    'passes' (K12, a consistent re-titling: the job title is a per-job input the operator checks); provenance_result: the
    expected expected_provenance.result (K13: JOB_TITLE_INVALID, no rerun)."""
    wp = writer_module()
    base = json.loads((src / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
    title, xn = base['deliverable']['job_title'], base['output_xlsx']['file']
    d1, d2 = wp.deliverable_record(title), wp.deliverable_record(title2)
    dn = base['deliverable_xlsx']['file']                       # v2.7 (O38): the deliverable, copied unless the tamper is about it
    assert d1['qa_workbook_file'] == xn == wp.QA_WORKBOOK_NAME and d1['xlsx_file'] == dn and d2['xlsx_file'] != dn
    assert d2['main_sheet'] != d1['main_sheet'] and d1['main_sheet'].isascii() is False
    esc1, esc2 = (wp_escape(x['main_sheet']) for x in (d1, d2))
    first_non_ascii = next(ch for ch in d1['main_sheet'] if ord(ch) > 127)

    def name_attr(new):
        return sub1(re.escape(f'name="{esc1}"'), lambda m: f'name="{new}"')

    def retitle(r, d):
        r['deliverable'].update({k: d[k] for k in d})
        r['output_xlsx']['file'] = d['qa_workbook_file']
        r['deliverable_xlsx'].update(file=d['xlsx_file'], sheet=d['main_sheet'])
    table = {
        # name: (workbook edits, receipt edit, new xlsx file name or None, findings, only, provenance)
        'K01_wrong_sheet_name': ({WB: name_attr('未填研究草稿')}, None, None, ['deliverable_name', 'sheet_order', 'pinned_template'], False, 'provenance'),
        'K02_sheet_and_receipt_renamed_title_kept': ({WB: name_attr(esc2)}, lambda r: (r['deliverable'].__setitem__('main_sheet', d2['main_sheet']),
                                                                               r['deliverable']['sheet_mapping'][0].__setitem__('workbook_sheet', d2['main_sheet'])),
                                                     None, ['deliverable_name', 'sheet_order', 'pinned_template'], False, 'provenance'),
        # v2.7: the internal workbook keeps its constant name, so it is found and checked against the second title's sheet name
        'K03_receipt_title_changed_only': ({}, lambda r: r['deliverable'].__setitem__('job_title', title2), None,
                                           ['deliverable_name', 'sheet_order', 'pinned_template'], False, 'provenance'),
        'K04_retitled_file_renamed_sheet_kept': ({}, lambda r: retitle(r, d2), None, ['deliverable_name', 'sheet_order', 'pinned_template'],
                                                 False, 'provenance'),
        'K05_workbook_xml_extra_change': ({WB: sub1(r'tabRatio="600"', 'tabRatio="601"')}, None, None, ['pinned_template'], True, 'provenance'),
        'K06_sheet_name_escaped_differently': ({WB: name_attr(esc1.replace(first_non_ascii, '&#%d;' % ord(first_non_ascii), 1))}, None, None,
                                               ['pinned_template'], True, 'provenance'),
        'K07_gh_grey_fill_restored': (dict(O34_TAMPERS['O34a_gh_grey_fill_restored'][0]), None, None, ['pinned_part', 'formatting'], True, 'provenance'),
        'K08_xlsx_renamed_research_draft': ({}, None, DEFAULT_XLSX, ['deliverable_name'], True, 'provenance'),
        'K09_receipt_output_file_edited': ({}, lambda r: r['output_xlsx'].__setitem__('file', DEFAULT_XLSX), None, ['deliverable_name'], True, 'fails'),
        'K10_second_workbook_in_dir': ({}, None, None, ['deliverable_name'], True, 'fails'),
        'K11_receipt_deliverable_dropped': ({}, lambda r: r.pop('deliverable'), None, ['deliverable_name'], True, 'provenance'),
        'K12_consistent_retitle': ({WB: name_attr(esc2)}, lambda r: retitle(r, d2), None, [], True, 'passes'),
        'K13_receipt_title_without_case_id': ({}, lambda r: r['deliverable'].__setitem__('job_title', '甲公司-乙案'), None, ['deliverable_name'], True,
                                              'provenance'),
    }
    results = {'provenance': 'FAILED', 'fails': 'PASS', 'passes': 'PASS'}
    dest.mkdir(parents=True, exist_ok=False)
    index = []
    for name, (edits, redit, new_file, findings, only, prov) in table.items():
        d = dest / name
        d.mkdir()
        (d / 'EXPECTED_SAVED_VALUES.json').write_bytes((src / 'EXPECTED_SAVED_VALUES.json').read_bytes())
        r = copy.deepcopy(base)
        out_name = new_file or xn
        if edits:
            write_tampered(src / xn, d / out_name, edits)
        else:
            shutil.copyfile(src / xn, d / out_name)
        if name.startswith('K10_'):
            shutil.copyfile(src / xn, d / 'copy of the deliverable.xlsx')
        # v2.7: the deliverable; K04 and K12 retitle it (file renamed; K12 also renames its sheet, consistently)
        dn_out = d2['xlsx_file'] if name[:3] in ('K04', 'K12') else dn
        if name.startswith('K12_'):
            write_tampered(src / dn, d / dn_out, {WB: name_attr(esc2)})
        else:
            shutil.copyfile(src / dn, d / dn_out)
        if redit is not None:
            redit(r)
        if 'output_xlsx' in r and r['output_xlsx']['file'] == out_name:
            r['output_xlsx']['sha256'] = sha((d / out_name).read_bytes())          # consistent receipt hash
        if isinstance(r.get('deliverable_xlsx'), dict) and r['deliverable_xlsx']['file'] == dn_out:
            r['deliverable_xlsx']['sha256'] = sha((d / dn_out).read_bytes())
            r['deliverable_xlsx']['bytes'] = len((d / dn_out).read_bytes())     # a compared receipt claim (v6)
        (d / 'WRITER_RECEIPT.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        index.append({'name': name, 'dir': str(d), 'group': 'naming', 'findings': findings, 'only': only, 'provenance': prov,
                      'provenance_result': 'JOB_TITLE_INVALID' if name.startswith('K13_') else results[prov],
                      'xlsx_file': out_name, 'job_title': title, 'job_title2': title2})
    (dest / 'TAMPERS.json').write_text(json.dumps({'invented': True, 'source_output': str(src), 'tampers': index},
                                                  ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return index


# ---------------------------------------------------------------- writer v2.7, owner decision O38: deliverable tampers
def _first_inline(x, cell):
    m = re.search(r'(<c r="%s" [^>]*><is><t[^>]*>)([^<]*)(</t></is></c>)' % cell, x)
    assert m, cell
    return m


def deliverable_value_changed(x):
    m = _first_inline(x, 'C2')
    return x[:m.start(2)] + m.group(2) + ' tampered' + x[m.end(2):]


def deliverable_number_as_text(x):
    m = re.search(r'<c r="(F[2-9][0-9]*)" s="([0-9]+)" t="n"><v>([0-9]+)</v></c>', x)
    assert m
    return x[:m.start()] + f'<c r="{m.group(1)}" s="{m.group(2)}" t="inlineStr"><is><t>{m.group(3)}</t></is></c>' + x[m.end():]


def deliverable_extra_cell(x):
    k = x.index('</row>', x.index('<row r="2"'))
    return x[:k] + '<c r="R2" t="inlineStr"><is><t>extra</t></is></c>' + x[k:]


def deliverable_v27_fixed_widths(x):
    """v2.8 (O39): every <col> back to its O38 minimum (the v2.7 fixed widths), although some value needs a wider column."""
    mins = [16.1, 23.1, 21.3, 81.9, 6.9, 8.3, 12.9, 13.0, 12.3, 13.0, 21.4, 11.0, 24.1, 34.1, 10.3, 13.0, 8.1]
    y = x
    changed = 0
    for j, w in enumerate(mins, start=1):
        pat = r'<col width="([^"]*)" customWidth="1" min="%d" max="%d"/>' % (j, j)
        m = re.search(pat, y)
        assert m, pat
        if abs(float(m.group(1)) - w) > 1e-9:
            changed += 1
        y = y[:m.start()] + '<col width="%s" customWidth="1" min="%d" max="%d"/>' % ('%.16g' % w, j, j) + y[m.end():]
    assert changed >= 1, 'the source deliverable needs at least one widened column'
    return y


def deliverable_header_body_style(x):
    y, n = re.subn(r'(<c r="[A-Q]1" s=")1(")', r'\g<1>2\g<2>', x)
    assert n == 17
    return y


DELIVERABLE_TAMPERS = {
    # name: (deliverable edits, findings (all tagged workbook "deliverable" unless listed in untagged), untagged findings,
    #        passes without provenance)
    'L01_value_changed': ({S1: deliverable_value_changed}, ['value_type_mismatch'], [], False),
    'L02_gridlines_hidden': ({S1: sub1(r'<sheetView workbookViewId="0">', '<sheetView showGridLines="0" workbookViewId="0">')},
                             ['worksheet_structure', 'formatting'], [], False),
    'L03_columns_frozen': ({S1: sub1(r'<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>',
                                     '<pane xSplit="3" ySplit="1" topLeftCell="D2" activePane="bottomRight" state="frozen"/>')},
                           ['worksheet_structure', 'formatting'], [], False),
    'L04_four_sheet_workbook_delivered': ({'=': None}, ['zip_parts', 'pinned_part', 'pinned_template', 'sheet_order'], [], False),
    'L05_header_fill_dark_blue': ({ST: sub1(r'FFC0C0C0', 'FF29445D')}, ['pinned_part', 'formatting'], [], False),
    'L06_header_cells_body_style': ({S1: deliverable_header_body_style}, ['formatting'], [], False),
    'L07_deliverable_missing': ({'-': None}, [], ['deliverable_name'], False),
    'L08_wrap_on': ({ST: sub1(r'<alignment horizontal="left" vertical="center"/>', '<alignment horizontal="left" vertical="center" wrapText="1"/>')},
                    ['pinned_part', 'formatting'], [], False),
    'L09_receipt_hash_stale': ({S1: deliverable_value_changed}, ['value_type_mismatch', 'integrity'], [], False),
    'L10_sheet_renamed': ({WB: sub1(r'name="[^"]*"', 'name="未填"')}, ['pinned_template', 'sheet_order'], [], False),
    'L11_row_height_changed': ({S1: sub1(r'<row r="3" ht="20.45" customHeight="1"', '<row r="3" ht="1" customHeight="1"')},
                               ['worksheet_structure', 'formatting'], [], False),
    'L12_extra_cell_R2': ({S1: deliverable_extra_cell}, ['unexpected_populated_cell'], [], False),
    'L13_number_as_text': ({S1: deliverable_number_as_text}, ['value_type_mismatch'], [], False),
    'L14_receipt_deliverable_xlsx_dropped': ({}, ['integrity'], ['deliverable_name'], False),
    'L15_consistent_change_all_three': ({}, [], [], True),
    'L16_hidden_column': ({S1: sub1(r'<col width="81.90000000000001" customWidth="1" min="4" max="4"/>',
                                    '<col width="81.90000000000001" customWidth="1" hidden="1" min="4" max="4"/>')},
                          ['hidden_attribute', 'worksheet_structure', 'formatting'], [], False),
    'L17_v27_fixed_widths': ({S1: deliverable_v27_fixed_widths}, ['worksheet_structure', 'formatting'], [], False),
    # review of v2.8: N1, a width text that parses within 1e-9 but is not openpyxl's text; N8, the receipt's widths claim edited
    'L18_width_text_look_alike': ({S1: sub1(r'(<col width=")([^"]*)(" customWidth="1" min="1" max="1"/>)',
                                            lambda m: m.group(1) + m.group(2) + ('0000000001' if '.' in m.group(2) else '.0000000001') + m.group(3))},
                                  ['worksheet_structure'], [], False),
    'L19_receipt_column_widths_edited': ({}, [], ['integrity'], False),
}


def make_deliverable_tampers(src, dest):
    """From a titled writer output SRC (v2.7): each tamper copies the output, edits the deliverable and updates the receipt's
    deliverable_xlsx.sha256 (except L09), so only the deliverable checks can see it. L15 changes main-sheet C2 consistently in
    EXPECTED_SAVED_VALUES.json, the internal workbook and the deliverable, with the receipt hashes updated: it passes without
    provenance (as T21) and fails with it."""
    base = json.loads((src / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
    xn, dn = base['output_xlsx']['file'], base['deliverable_xlsx']['file']
    dest.mkdir(parents=True, exist_ok=False)
    index = []
    for name, (edits, tagged, untagged, passes) in DELIVERABLE_TAMPERS.items():
        d = dest / name
        d.mkdir()
        for f in ('EXPECTED_SAVED_VALUES.json', 'WRITER_RECEIPT.json', xn):
            (d / f).write_bytes((src / f).read_bytes())
        if '-' in edits:
            pass
        elif '=' in edits:
            assert base['deliverable_xlsx']['sheet'] == base['deliverable']['main_sheet']
            (d / dn).write_bytes((src / xn).read_bytes())          # the four-sheet workbook under the deliverable's name
        elif name.startswith('L15_'):
            consistent_change(src, d)                               # EXPECTED and the internal workbook
            main_new = json.loads((d / 'EXPECTED_SAVED_VALUES.json').read_text(encoding='utf-8'))['sheets'][0]['values']
            c_width = o39_width(main_new, 2)                        # v2.8 (O39): column C's width follows the new value
            write_tampered(src / dn, d / dn, {S1: lambda x: sub1(r'(<col width=")[^"]*(" customWidth="1" min="3" max="3"/>)',
                                                                 lambda m: m.group(1) + '%.16g' % c_width + m.group(2))(
                                                  sub1(r'(<c r="C2" [^>]*><is><t[^>]*>)[^<]*(</t></is></c>)',
                                                       lambda m: m.group(1) + ''.join(c if ord(c) < 128 else '&#%d;' % ord(c) for c in
                                                                                      main_new[1][2]) + m.group(2))(x))})
        else:
            write_tampered(src / dn, d / dn, edits)
        if name.startswith('L14_'):
            r = json.loads((d / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
            r['deliverable_xlsx'] = None
            (d / 'WRITER_RECEIPT.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        elif name.startswith('L19_'):
            (d / dn).write_bytes((src / dn).read_bytes())
            update_receipt(d)
            r = json.loads((d / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
            r['deliverable_xlsx']['column_widths'] = [1.0] * 17
            (d / 'WRITER_RECEIPT.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        elif not name.startswith('L09_'):
            update_receipt(d)
        if name.startswith('L15_'):                                 # v2.8.1: the receipt's widths claim follows column C too
            r = json.loads((d / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
            r['deliverable_xlsx']['column_widths'][2] = c_width
            (d / 'WRITER_RECEIPT.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        index.append({'name': name, 'dir': str(d), 'group': 'deliverable', 'deliverable_findings': tagged, 'other_findings': untagged,
                      'passes_without_provenance': passes, 'provenance_finding': 'provenance', 'deliverable_file': dn})
    (dest / 'TAMPERS.json').write_text(json.dumps({'invented': True, 'source_output': str(src), 'tampers': index},
                                                  ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return index


def wp_escape(name):
    """The main sheet name as openpyxl/lxml writes it in workbook.xml (the same rule as saved_qa xml_attribute_escape)."""
    return name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'carrier':
        base = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
        Path(sys.argv[3]).write_bytes(json.dumps(fidelity_carrier(base), ensure_ascii=True, indent=1).encode('ascii'))
    elif len(sys.argv) in (4, 5) and sys.argv[1] == 'tamper':
        idx = make_tampers(Path(sys.argv[2]), Path(sys.argv[3]), consistent_only=len(sys.argv) == 5 and sys.argv[4] == '--consistent-only')
        print(json.dumps({'tampers': len(idx)}))
    elif len(sys.argv) == 4 and sys.argv[1] == 'downgrade':
        print(json.dumps({'tampers': len(make_downgrade(Path(sys.argv[2]), Path(sys.argv[3])))}))
    elif len(sys.argv) == 4 and sys.argv[1] == 'receipt':
        print(json.dumps({'tampers': len(make_receipt_tampers(Path(sys.argv[2]), Path(sys.argv[3])))}))
    elif len(sys.argv) == 5 and sys.argv[1] == 'naming':
        print(json.dumps({'tampers': len(make_naming_tampers(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]))}))
    elif len(sys.argv) == 4 and sys.argv[1] == 'deliverable':
        print(json.dumps({'tampers': len(make_deliverable_tampers(Path(sys.argv[2]), Path(sys.argv[3])))}))
    else:
        sys.exit(__doc__)
