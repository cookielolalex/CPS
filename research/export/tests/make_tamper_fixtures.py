"""Invented saved-QA tamper fixtures (review 2026-11-04, ADMIT_AFTER_LISTED_FIXES). No project data.

  carrier BASE OUT   The reviewer's fidelity probe carrier (p01_fidelity), derived from the invented export fixture
                     v01_base: numeric-looking, date-looking and error-literal text, CR/LF/NEL/TAB, leading/trailing
                     spaces, 17-digit doubles, 1e-7, the denormal 5e-324, -0, JavaScript key order in metadata, a
                     formula-like and an error-literal nonitem text, a lone surrogate inside JSON review text.
  tamper SRC DEST    From a writer output SRC (made from that carrier), the reviewer's 22 tampered outputs T01..T22
                     plus extra structural tampers X01..X16, the second review's N01..N07, N10, N11 (review round 2,
                     s2_tampers.py) and the consistent EXPECTED+xlsx variants C1..C3, each in its own directory, and
                     DEST/TAMPERS.json with the finding each one must produce.
  downgrade SRC DEST From a --mode v2 writer output SRC of a carrier without O13/R57 (same bytes as v1), the second
                     review's receipt-mode downgrade (F2, s3_attacks2.py): D1 the N01 tamper with the receipt mode kept
                     v2, D2 the same with the receipt mode edited to v1, D3 a change no structural check sees (pane
                     ySplit, the second review's N12) with the receipt mode edited to v1; DEST/TAMPERS.json as above.
Usage: python3 -I -B make_tamper_fixtures.py carrier /abs/v01_base.json /abs/new.json
       python3 -I -B make_tamper_fixtures.py tamper /abs/writer-output /abs/new-dir
       python3 -I -B make_tamper_fixtures.py downgrade /abs/writer-output-mode-v2 /abs/new-dir
"""
import copy, hashlib, json, re, sys, zipfile
from pathlib import Path

COLS = 'ABCDEFGHIJKLMNOPQ'
S1, WB, ST = 'xl/worksheets/sheet1.xml', 'xl/workbook.xml', 'xl/styles.xml'


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
# Receipt-mode downgrade (second review F2): name -> (edits, receipt mode to write, finding without provenance or None)
DOWNGRADE_TAMPERS = {
    'D1_v2_output_second_v_mode_kept': ({S1: REVIEW2_TAMPERS['N01_second_v_in_number_cell'][0][S1]}, 'v2', 'cell_value_children'),
    'D2_v2_output_second_v_mode_downgraded_to_v1': ({S1: REVIEW2_TAMPERS['N01_second_v_in_number_cell'][0][S1]}, 'v1', 'cell_value_children'),
    'D3_v2_output_pane_ysplit_mode_downgraded_to_v1': ({S1: sub1(r'ySplit="1" topLeftCell="D2"', 'ySplit="60" topLeftCell="D2"')}, 'v1', None),
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
    r['output_xlsx']['sha256'] = sha((d / 'research-draft.xlsx').read_bytes())
    r['expected_saved_values']['sha256'] = sha((d / 'EXPECTED_SAVED_VALUES.json').read_bytes())
    (d / 'WRITER_RECEIPT.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


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
    write_tampered(src / 'research-draft.xlsx', d / 'research-draft.xlsx',
                   {S1: sub1(r'(<c r="C2" [^>]*><is><t[^>]*>)[^<]*(</t></is></c>)', lambda m: m.group(1) + enc + m.group(2))})


def make_tampers(src, dest, consistent_only=False):
    dest.mkdir(parents=True, exist_ok=False)
    index = []
    groups = [] if consistent_only else [('reviewer', REVIEWER_TAMPERS), ('extra', EXTRA_TAMPERS), ('review2', REVIEW2_TAMPERS)]
    for group, table in groups:
        for name, (edits, finding) in table.items():
            d = dest / name
            d.mkdir()
            for f in ('EXPECTED_SAVED_VALUES.json', 'WRITER_RECEIPT.json'):
                (d / f).write_bytes((src / f).read_bytes())
            write_tampered(src / 'research-draft.xlsx', d / 'research-draft.xlsx', edits)
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
    for name, (edits, mode, finding) in DOWNGRADE_TAMPERS.items():
        d = dest / name
        d.mkdir()
        for f in ('EXPECTED_SAVED_VALUES.json', 'WRITER_RECEIPT.json'):
            (d / f).write_bytes((src / f).read_bytes())
        write_tampered(src / 'research-draft.xlsx', d / 'research-draft.xlsx', edits)
        update_receipt(d)
        r = json.loads((d / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
        r['mode'] = mode
        (d / 'WRITER_RECEIPT.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        index.append({'name': name, 'dir': str(d), 'group': 'downgrade', 'receipt_mode': mode, 'finding': finding,
                      'passes_without_provenance': finding is None, 'provenance_finding': 'provenance'})
    (dest / 'TAMPERS.json').write_text(json.dumps({'invented': True, 'source_output': str(src), 'tampers': index},
                                                  ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return index


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'carrier':
        base = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
        Path(sys.argv[3]).write_bytes(json.dumps(fidelity_carrier(base), ensure_ascii=True, indent=1).encode('ascii'))
    elif len(sys.argv) in (4, 5) and sys.argv[1] == 'tamper':
        idx = make_tampers(Path(sys.argv[2]), Path(sys.argv[3]), consistent_only=len(sys.argv) == 5 and sys.argv[4] == '--consistent-only')
        print(json.dumps({'tampers': len(idx)}))
    elif len(sys.argv) == 4 and sys.argv[1] == 'downgrade':
        print(json.dumps({'tampers': len(make_downgrade(Path(sys.argv[2]), Path(sys.argv[3])))}))
    else:
        sys.exit(__doc__)
