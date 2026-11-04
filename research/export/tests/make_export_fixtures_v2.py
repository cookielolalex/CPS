"""Invented carrier fixtures for the portable writer's mode v2 (candidate 046f, owner decision O13). No project data.

Inputs: two carriers produced by the 046f route v4 from its own invented route-test fixtures
(guideline046_006/route_tests/make_fixtures.py -> cps046b_route.py convert):
  JOBS  - valid_response_job_inputs.json: L, M and N proven by job-input context (M/N selection evidence);
  PLAIN - valid_response.json: no M/N selection evidence.
Output: valid and invalid variants for `writer_portable.py --mode v2` plus FIXTURES_V2.json
(expected outcome, refusal code and stage for each).
Usage: python3 -I -B make_export_fixtures_v2.py /abs/jobs_carrier.json /abs/plain_carrier.json /abs/new_out_dir
"""
import copy, json, sys
from pathlib import Path

COLS = 'ABCDEFGHIJKLMNOPQ'
jobs_path, plain_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=False)
JOBS_BYTES = jobs_path.read_bytes()
JOBS = json.loads(JOBS_BYTES.decode('utf-8'))
index = []
GATE_COPY = 'gate:validate_carrier_v4:o13_placeholder_copy'
PORT = 'gate:route_v4_port'


def item(c, i):
    return next(x for x in c['items'] + c['components'] if x['id'] == i)


def write(name, c=None, valid=True, code=None, stage=None, raw=None, ascii_json=False, o13=True, note=None):
    sub = 'valid' if valid else 'invalid'
    p = out / sub / f'{name}.json'
    p.parent.mkdir(exist_ok=True)
    if raw is None:
        raw = json.dumps(c, ensure_ascii=ascii_json, indent=1).encode('utf-8')
    p.write_bytes(raw)
    index.append({'name': name, 'file': str(p), 'valid': valid, 'expected_code': code, 'expected_stage': stage,
                  'o13_expected': o13, 'note': note})


def variant(f):
    c = copy.deepcopy(JOBS)
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


def set_text(c, iid, col, value):
    r = item(c, iid)
    r['values'][COLS.index(col)] = value
    r['null_reasons'].pop(col, None)
    ev = copy.deepcopy(r['evidence']['C'])
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
write('w06_plain_no_mn', raw=plain_path.read_bytes(), o13=False,
      note='046f carrier without M/N selection evidence: mode v2 takes the v1 route and gives the same bytes as mode v1')

# ---------------------------------------------------------------- invalid (mode v2)
write('x01_C_selection_with_mn', variant(lambda c: (item(c, 'R002')['values'].__setitem__(2, 'x'),
                                                    item(c, 'R002')['evidence'].update(C=dict(item(c, 'R002')['evidence']['M'])))),
      False, 'SELECTION_ONLY_ENGINEERING_ID', GATE_COPY, note='selection evidence outside L/M/N stays refused by writer004 itself')
write('x02_M_pathlike', variant(lambda c: item(c, 'R002')['evidence']['M'].update(selection_evidence='C:\\x')),
      False, 'EXTRA_SOURCE_REFERENCE', PORT, note='the copy carries the text as raw_text; the route v4 port refuses the selection evidence')
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

(out / 'FIXTURES_V2.json').write_text(json.dumps({'invented': True, 'jobs_carrier': str(jobs_path), 'plain_carrier': str(plain_path),
                                                  'fixtures': index}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
print(json.dumps({'valid': sum(x['valid'] for x in index), 'invalid': sum(not x['valid'] for x in index)}))
