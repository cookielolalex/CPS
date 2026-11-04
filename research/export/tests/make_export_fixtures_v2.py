"""Invented carrier fixtures for the portable writer's mode v2 (candidate 046f, route v4.1 relaxations). No project data.

Inputs: carriers produced by the 046f route v4.1 from invented inputs (guideline046_006/route_tests/make_fixtures.py
and the package's invented EXAMPLE_INVENTORY.json/EXAMPLE_RESPONSE.json -> cps046b_route.py convert):
  JOBS    - valid_response_job_inputs.json: L, M and N proven by job-input context (O13: M/N selection evidence);
  PLAIN   - valid_response.json: no relaxation;
  R57     - valid_response_r57_null_c.json: C null with status research_draft (R003 with a review reason, C001 without);
  Q       - valid_response_q_unverified.json: Q under unverified adoption (O16), no other relaxation;
  ALL     - valid_response_relaxed_all.json: all three classes;
  EXAMPLE - the package example (材料清單-style source; all three classes).
Output: valid and invalid variants for `writer_portable.py --mode v2` plus FIXTURES_V2.json
(expected outcome, refusal code and stage for each; relaxed_expected = the writer must use the placeholder copy).
Usage: python3 -I -B make_export_fixtures_v2.py JOBS PLAIN R57 Q ALL EXAMPLE /abs/new_out_dir
"""
import copy, json, sys
from pathlib import Path

COLS = 'ABCDEFGHIJKLMNOPQ'
jobs_path, plain_path, r57_path, q_path, all_path, example_path, out = [Path(x) for x in sys.argv[1:8]]
out.mkdir(parents=True, exist_ok=False)
JOBS_BYTES = jobs_path.read_bytes()
JOBS = json.loads(JOBS_BYTES.decode('utf-8'))
R57 = json.loads(r57_path.read_text(encoding='utf-8'))
QC = json.loads(q_path.read_text(encoding='utf-8'))
index = []
GATE = 'gate:validate_carrier_v4'
GATE_COPY = 'gate:validate_carrier_v4:placeholder_copy'
PORT = 'gate:route_v4_port'


def item(c, i):
    return next(x for x in c['items'] + c['components'] if x['id'] == i)


def write(name, c=None, valid=True, code=None, stage=None, raw=None, ascii_json=False, relaxed=True, note=None):
    sub = 'valid' if valid else 'invalid'
    p = out / sub / f'{name}.json'
    p.parent.mkdir(exist_ok=True)
    if raw is None:
        raw = json.dumps(c, ensure_ascii=ascii_json, indent=1).encode('utf-8')
    p.write_bytes(raw)
    index.append({'name': name, 'file': str(p), 'valid': valid, 'expected_code': code, 'expected_stage': stage,
                  'relaxed_expected': relaxed, 'note': note})


def variant(f, base=JOBS):
    c = copy.deepcopy(base)
    f(c)
    return c


def to_location(c, ids):
    """Documented placeholder conversion for the listed items only (leaves the others' selection evidence)."""
    for r in c['items'] + c['components']:
        if r['id'] not in ids:
            continue
        for k in ('M', 'N'):
            e = r['evidence'][k]
            if 'selection_evidence' in e:
                r['evidence'][k] = {'transformation': e['transformation'], 'location': copy.deepcopy(r['location']),
                                    'anchor': r['anchor'], 'raw_text': e['selection_evidence']}


def set_text(c, iid, col, value, like='C'):
    r = item(c, iid)
    r['values'][COLS.index(col)] = value
    r['null_reasons'].pop(col, None)
    ev = copy.deepcopy(r['evidence'][like])
    ev['raw_text'] = value
    r['evidence'][col] = ev


# ---------------------------------------------------------------- valid (mode v2)
write('w01_job_inputs', JOBS, note='route v4 job-input carrier: M/N selection evidence on 7 demand rows and 2 components')
write('w02_job_inputs_bom', raw=b'\xef\xbb\xbf' + JOBS_BYTES, note='UTF-8 BOM stripped (node and the portable writer)')
write('w03_components_only', variant(lambda c: to_location(c, {r['id'] for r in c['items']})),
      note='only the two components keep M/N selection evidence')


def text_edges(c):
    r = item(c, 'R002')
    r['values'][12] = '示例客戶 \U00020000 עברית e\u0301'
    sel = json.loads(r['evidence']['M']['selection_evidence'])
    sel['context'][0]['value'] = r['values'][12]
    r['evidence']['M']['selection_evidence'] = json.dumps(sel, ensure_ascii=False, sort_keys=True) + '\u2028\t第二行\n'


write('w04_text_edges', variant(text_edges), note='astral, RTL and combining text; LS, TAB and LF inside selection evidence')
write('w05_lone_surrogate_selection_review_only', variant(lambda c: item(c, 'R003')['evidence']['N'].update(transformation='x\ud800y')),
      ascii_json=True, note='lone surrogate only inside a JSON-encoded review cell (escaped by JSON.stringify): writable')
write('w06_plain_no_mn', raw=plain_path.read_bytes(), relaxed=False,
      note='046f carrier without relaxations: mode v2 takes the v1 route and gives the same bytes as mode v1')
write('w07_r57_null_c', R57, note='C null with status research_draft: R003 keeps its review reason, C001 gets the placeholder reason in the copy')
write('w08_q_unverified', raw=q_path.read_bytes(), relaxed=False,
      note='Q under unverified adoption only: writer004 never reads the adoption status, so mode v2 takes the v1 route (same bytes as v1)')
write('w09_relaxed_all', raw=all_path.read_bytes(), note='M/N selection evidence, C-null research_draft and Q under unverified adoption together')
write('w10_example046f', raw=example_path.read_bytes(), note='the package example (材料清單-style source; all three relaxation classes)')


def r57_text_edges(c):
    r = item(c, 'R003')
    r['review_reasons'] = ['審查 \U00020000 עברית e\u0301\u2028第二行']
    r['null_reasons']['C'] = '服務列 C 為空 (R52)\t\n'


write('w11_r57_text_edges', variant(r57_text_edges, R57), note='astral, RTL, combining, LS, TAB and LF in the R57 item reasons')

# ---------------------------------------------------------------- invalid (mode v2)
write('x01_C_selection_with_mn', variant(lambda c: (item(c, 'R002')['values'].__setitem__(2, 'x'),
                                                    item(c, 'R002')['evidence'].update(C=dict(item(c, 'R002')['evidence']['M'])))),
      False, 'SELECTION_ONLY_ENGINEERING_ID', GATE_COPY, note='selection evidence outside L/M/N stays refused by writer004 itself')
write('x02_M_pathlike', variant(lambda c: item(c, 'R002')['evidence']['M'].update(selection_evidence='C:\\x')),
      False, 'EXTRA_SOURCE_REFERENCE', PORT, note='the copy carries the text as raw_text; the route v4.1 port refuses the selection evidence')
write('x03_M_extra_key', variant(lambda c: item(c, 'R002')['evidence']['M'].update(note='x')),
      False, 'EXACT_KEYS_REQUIRED', GATE_COPY, note='other keys survive the conversion, so writer004 refuses the copy')
write('x04_formula_D_with_mn', variant(lambda c: set_text(c, 'R002', 'D', '-20~60℃')),
      False, 'FORMULA_STRING_FORBIDDEN', GATE_COPY)
write('x05_N_review_cell_too_long', variant(lambda c: item(c, 'R004')['evidence']['N'].update(selection_evidence='n' * 29990, transformation='t' * 2900)),
      False, 'REVIEW_CELL_UNSAFE_OR_TOO_LONG', PORT, note='validate_carrier_v4 accepts the copy; the port runs the prepareMatrices review-cell check')
bad = JOBS_BYTES.replace('Invented fixture response.'.encode(), b'Invented fixture \xff response.', 1)
assert bad != JOBS_BYTES
write('x06_invalid_utf8_with_mn', raw=bad, valid=False, code='UTF8_REQUIRED', stage='parse')
write('x07_M_selection_blank', variant(lambda c: item(c, 'R005')['evidence']['M'].update(selection_evidence='\u3000')),
      False, 'STRING_REQUIRED', GATE_COPY)
write('x08_N_selection_number', variant(lambda c: item(c, 'C001')['evidence']['N'].update(selection_evidence=5)),
      False, 'STRING_REQUIRED', GATE_COPY)
write('x09_quantity_mismatch_with_mn', variant(lambda c: item(c, 'R002')['raw'].update(quantity='+4')),
      False, 'SOURCE_QUANTITY_MISMATCH', GATE_COPY)
write('x10_r57_missing_null_reason_C', variant(lambda c: item(c, 'C001')['null_reasons'].pop('C'), R57),
      False, 'STRING_REQUIRED', GATE_COPY, note='the relaxation keeps the null-reason requirement: writer004 refuses the copy')
write('x11_r57_blank_null_reason_C', variant(lambda c: item(c, 'R003')['null_reasons'].update(C='\u3000'), R57),
      False, 'STRING_REQUIRED', GATE_COPY)
write('x12_r57_review_reasons_not_list', variant(lambda c: item(c, 'C001').update(review_reasons='x'), R57),
      False, 'STRING_ARRAY_REQUIRED', GATE_COPY, note='the copy adds a placeholder reason only to an empty list, so the defect survives')
write('x13_r57_formula_D', variant(lambda c: set_text(c, 'R003', 'D', '-x', like='D'), R57),
      False, 'FORMULA_STRING_FORBIDDEN', GATE_COPY)
write('x14_r57_review_cell_too_long', variant(lambda c: item(c, 'R003').update(review_reasons=['r' * 30000, 'r' * 3000]), R57),
      False, 'REVIEW_CELL_UNSAFE_OR_TOO_LONG', PORT, note='validate_carrier_v4 accepts the copy; the port runs the prepareMatrices review-cell check')
write('x15_r57_other_item_status_partial', variant(lambda c: item(c, 'R002').update(status='partial'), R57),
      False, 'REVIEW_STATUS_REQUIRED', GATE_COPY, note='only C-null research_draft items are neutralized; any other status defect survives')
write('x16_q_unverified_value_mismatch', variant(lambda c: item(c, 'R006')['values'].__setitem__(16, 50001), QC),
      False, 'NUMERIC_EVIDENCE_MISMATCH', GATE, relaxed=False,
      note='Q-only carrier takes the v1 route: writer004 still checks Q against its evidence and the raw unit price')
write('x17_q_unverified_raw_mismatch', variant(lambda c: (item(c, 'R006')['values'].__setitem__(16, 50001),
                                                         item(c, 'R006')['evidence']['Q'].update(raw_text='50001')), QC),
      False, 'SOURCE_UNIT_PRICE_MISMATCH', GATE, relaxed=False)

(out / 'FIXTURES_V2.json').write_text(json.dumps({'invented': True, 'carriers': {
    'jobs': str(jobs_path), 'plain': str(plain_path), 'r57': str(r57_path), 'q': str(q_path), 'all': str(all_path),
    'example': str(example_path)}, 'fixtures': index}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
print(json.dumps({'valid': sum(x['valid'] for x in index), 'invalid': sum(not x['valid'] for x in index)}))
