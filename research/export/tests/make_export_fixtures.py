"""Invented carrier fixtures for the portable export route. No project data.

Input: the carrier produced by the 046d route from the route tests' own invented fixtures
(make_fixtures.py -> cps046b_route.py convert). Output: valid and invalid carrier variants
plus FIXTURES.json (expected outcome, refusal code and stage for each).
Usage: python3 -I -B make_export_fixtures.py /abs/base_carrier.json /abs/new_out_dir
"""
import copy, json, sys
from pathlib import Path

COLS = 'ABCDEFGHIJKLMNOPQ'
base_path, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=False)
BASE_BYTES = base_path.read_bytes()
BASE = json.loads(BASE_BYTES.decode('utf-8'))
index = []


def item(c, i):
    return next(x for x in c['items'] + c['components'] if x['id'] == i)


def set_value(c, iid, col, value, raw_text=None):
    """Set a value with matching evidence (copied locator of the C evidence) and drop its null reason."""
    r = item(c, iid)
    j = COLS.index(col)
    r['values'][j] = value
    r['null_reasons'].pop(col, None)
    ev = copy.deepcopy(r['evidence']['C'] if 'location' in r['evidence'].get('C', {}) else
                       next(e for e in r['evidence'].values() if 'location' in e))
    ev['raw_text'] = raw_text if raw_text is not None else (value if isinstance(value, str) else str(value))
    r['evidence'][col] = ev
    return r


def set_null(c, iid, col, reason):
    r = item(c, iid)
    r['values'][COLS.index(col)] = None
    r['evidence'].pop(col, None)
    r['null_reasons'][col] = reason


def set_quantity(c, iid, value, text):
    r = set_value(c, iid, 'F', value, text)
    r['raw']['quantity'] = text


def write(name, c=None, valid=True, code=None, stage=None, raw=None, ascii_json=False, note=None):
    sub = 'valid' if valid else 'invalid'
    p = out / sub / f'{name}.json'
    p.parent.mkdir(exist_ok=True)
    if raw is None:
        raw = json.dumps(c, ensure_ascii=ascii_json, indent=1).encode('utf-8')
    p.write_bytes(raw)
    index.append({'name': name, 'file': str(p), 'valid': valid, 'expected_code': code, 'expected_stage': stage, 'note': note})


def variant(f):
    c = copy.deepcopy(BASE)
    f(c)
    return c


# ---------------------------------------------------------------- valid
write('v01_base', BASE, note='route fixture carrier: groups, components, held item, selection evidence L, CJK')
write('v02_bom', raw=b'\xef\xbb\xbf' + BASE_BYTES, note='UTF-8 BOM stripped by writer004 and the portable writer')


def numeric_edges(c):
    set_quantity(c, 'R001', 2, '+2')
    set_quantity(c, 'R002', 0.1 + 0.2, '0.30000000000000004')
    set_quantity(c, 'R003', 1e-07, '0.0000001')
    set_quantity(c, 'R004', 9007199254740991, '9,007,199,254,740,991')
    set_quantity(c, 'R005', -0.0, '-0')
    set_quantity(c, 'R006', 123456789.12345679, '123456789.123456789')
    set_quantity(c, 'R007', 5e-324, '0.' + '0' * 323 + '5')
    set_value(c, 'R006', 'P', 1234.5, '1,234.5')
    set_value(c, 'R005', 'P', 7.25, '7.25')
    x = item(c, 'C001')['composition']
    x['basis_quantity'], x['basis_raw'] = 0.5, '0.5'


write('v03_numeric_edges', variant(numeric_edges), note='17-digit doubles, 1e-7, MAX_SAFE with grouping, -0, denormal, leading +')


def text_edges(c):
    set_value(c, 'R002', 'D', 'a\rb\r\nc\td e\x85f﻿g  ')
    set_value(c, 'R003', 'I', '#N/A')
    set_value(c, 'R003', 'J', '123')
    set_value(c, 'R004', 'I', '#REF!')
    set_value(c, 'R004', 'J', '2024/01/01')
    set_value(c, 'R004', 'D', ' TRUE')
    set_value(c, 'R005', 'C', '溫度計 \U0001F321️ \U00020000 é עברית')
    set_value(c, 'R005', 'I', 'AB_x12_ _x004 x0041_ _X0041_')
    set_value(c, 'R006', 'D', '0~100℃；３Φ４Ｗ ＋ 220V／110V')
    item(c, 'R001')['raw']['remarks'] = '備註\n第二行'
    c['nonitems'][0]['kind'] = 'header\tkind'


write('v04_text_edges', variant(text_edges), note='CR/LF/TAB/LS/NEL/BOM inside, error literals and numeric/date-looking text kept as text, astral/RTL/combining')


def long_text(c):
    set_value(c, 'R002', 'C', '中' * 16000)
    set_value(c, 'R001', 'D', '\U00020000' * 7000)
    c['nonitems'][0]['text'] = 'x' * 30000


write('v05_long_text', variant(long_text), note='16000 CJK chars, 7000 astral chars (14000 UTF-16 units), 30000-char nonitem text -> 30002-unit review cell')


def metadata_keys(c):
    c['metadata'].update({'10': 1, '2': 'b', 'b': -0.0, '4294967294': 1.5, '4294967295': 1e-07, '01': True, '-1': None,
                          'nested': {'3': [1, 2, {'1': 'x', '0': 'y'}], 'a': 123456.789, 'z': 1e-07}})


write('v06_metadata_keys', variant(metadata_keys), note='JavaScript property order (array-index keys first), nested numbers')


def no_components_no_groups(c):
    c['components'] = []
    c['groups'] = []
    for iid in ('R001', 'R002', 'R003'):
        item(c, iid)['group_id'] = None
        set_null(c, iid, 'A', 'no group in this invented fixture')
        set_null(c, iid, 'B', 'no group in this invented fixture')


write('v07_no_components_no_groups', variant(no_components_no_groups), note='header-only components and links sheets')


def many_items(c):
    proto = item(c, 'R002')
    for k in range(400):
        r = copy.deepcopy(proto)
        r['id'] = f'R{1000 + k}'
        r['values'][2] = f'示例材料{k:03d} 型式{k % 7}'
        r['evidence']['C']['raw_text'] = r['values'][2]
        c['items'].append(r)


write('v08_many_items', variant(many_items), note='407 items, about 10000 review rows')


def lone_surrogate_review_only(c):
    item(c, 'R002')['evidence']['C']['transformation'] = 'x\ud800y'


write('v09_lone_surrogate_review_only', variant(lone_surrogate_review_only), ascii_json=True,
      note='lone surrogate only inside a JSON-encoded review cell (escaped by JSON.stringify): writable')


def xlsx_kind(c):
    c['schema'] = 'cps.cached-xlsx-research-carrier.v1'
    c['source']['kind'] = 'cached_xlsx'
    c['source']['path'] = c['source']['path'][:-4] + '.xlsx'


write('v10_xlsx_kind', variant(xlsx_kind), note='cached_xlsx source: different review source row text')


def held_component(c):
    r = item(c, 'C002')
    r['status'] = 'held'
    r['review_reasons'] = ['Invented hold reason for a component.']


write('v11_held_component', variant(held_component), note='held component row')

# ---------------------------------------------------------------- invalid
G = 'gate:validate_carrier_v4'
write('i01_minus_value', variant(lambda c: set_value(c, 'R005', 'D', '-20~60℃')), False, 'FORMULA_STRING_FORBIDDEN', G)
write('i02_equals_value', variant(lambda c: set_value(c, 'R002', 'D', '=SUM(A1:A2)')), False, 'FORMULA_STRING_FORBIDDEN', G)
write('i03_plus_value', variant(lambda c: set_value(c, 'R002', 'I', '+886-2-1234')), False, 'FORMULA_STRING_FORBIDDEN', G)
write('i04_at_value', variant(lambda c: set_value(c, 'R002', 'J', '@vendor')), False, 'FORMULA_STRING_FORBIDDEN', G)
write('i05_ideographic_space_equals', variant(lambda c: set_value(c, 'R002', 'D', '　=x')), False, 'FORMULA_STRING_FORBIDDEN', G)
write('i06_bom_minus', variant(lambda c: set_value(c, 'R002', 'D', '﻿-5')), False, 'FORMULA_STRING_FORBIDDEN', G)
write('i07_basis_unit_minus', variant(lambda c: item(c, 'C001')['composition'].update(basis_unit='-工')), False, 'FORMULA_STRING_FORBIDDEN', G)
write('i08_quantity_mismatch', variant(lambda c: item(c, 'R002')['raw'].update(quantity='+4')), False, 'SOURCE_QUANTITY_MISMATCH', G)
write('i09_purchase_price', variant(lambda c: set_value(c, 'R002', 'G', 1, '1')), False, 'PURCHASE_PRICE_MUST_BE_BLANK', G)
write('i10_review_cell_too_long', variant(lambda c: (set_value(c, 'R002', 'C', 'x' * 20000), set_value(c, 'R002', 'D', 'y' * 20000))),
      False, 'REVIEW_CELL_UNSAFE_OR_TOO_LONG', 'prepare_matrices', note='validate_carrier_v4 passes; writer004 prepareMatrices refuses')
write('i11_nan_literal', raw=BASE_BYTES.replace(b'"basis_quantity": 2', b'"basis_quantity": NaN', 1), valid=False, code='ERROR', stage=G)
write('i12_duplicate_item_id', variant(lambda c: item(c, 'R002').update(id='R001')), False, 'DUPLICATE_ITEM_ID', G)
write('i13_wrong_headers', variant(lambda c: c['headers'].__setitem__(16, '合約單價')), False, 'EXACT_HEADERS_REQUIRED', G)
write('i14_lone_surrogate_value', variant(lambda c: set_value(c, 'R002', 'D', 'a\ud800b')), False, 'PORTABLE_UNREPRESENTABLE', 'writability',
      ascii_json=True, note='writer004 accepts; the portable writer refuses (not XML-representable in a cell)')
write('i15_ooxml_escape_value', variant(lambda c: set_value(c, 'R002', 'D', 'AB_x0041_C')), False, 'PORTABLE_UNREPRESENTABLE', 'writability',
      note='writer004 accepts; spreadsheet applications would decode _x0041_ as A')
write('i16_fffe_in_review', variant(lambda c: item(c, 'R002')['evidence']['C'].update(transformation='a￾b')), False,
      'PORTABLE_UNREPRESENTABLE', 'writability', note='U+FFFE survives JSON.stringify into a review cell; not an XML character')
bad = BASE_BYTES.replace('Invented fixture response.'.encode(), b'Invented fixture \xff response.', 1)
write('i17_invalid_utf8', raw=bad, valid=False, code='UTF8_REQUIRED', stage='parse', note='node decodes with U+FFFD and accepts; the portable writer refuses')
write('i18_missing_key', variant(lambda c: item(c, 'R001').pop('anchor')), False, 'EXACT_KEYS_REQUIRED', G)
write('i19_held_without_reason', variant(lambda c: item(c, 'R007').update(review_reasons=[])), False, 'HELD_REASON_REQUIRED', G)
write('i20_control_char', variant(lambda c: set_value(c, 'R002', 'D', 'a\x07b')), False, 'STRING_REQUIRED', G)
write('i21_unsafe_number', variant(lambda c: set_quantity(c, 'R002', 9007199254740993, '9007199254740993')), False, 'FINITE_SAFE_NUMBER_REQUIRED', G)

(out / 'FIXTURES.json').write_text(json.dumps({'invented': True, 'base_carrier': str(base_path), 'fixtures': index},
                                              ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
print(json.dumps({'valid': sum(x['valid'] for x in index), 'invalid': sum(not x['valid'] for x in index)}))
