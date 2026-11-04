"""Actual-route tests for candidates 046b-046f (route v4.2) with invented fixtures only.

Route: response -> tools/cps046b_route.py (check/convert) -> archived writer004
validate_carrier_v4.mjs (byte-identical original, @oai/artifact-tool import stubbed)
-> frozen compare_source043.evaluate pairing interface (invented expectations).
Route v4 (owner decision O13, FIELD_ROLES R48): L, M and N may be proven by job-input context alone.
Route v4.1 (R52/R54/R56/R57, O16): a null C may be research_draft; Q may be non-null under
unverified adoption (warning); the one-member physical_enclosure group still carries A/B.
Route v4.2 (R48, R56, R58; 046f review S12): on a 046f job packet (an inventory with job-input facts),
L, M and N on every item cite exactly their own fact and equal it, K, O and P are null, and every group
is a one-member physical_enclosure group; on every inventory a J citing context:company_name equals it.
The reviewer's eight probes are applied to the package example as negative tests, and the O17 boundary
(a 材料清單 packet has no context:brand_table) is checked on the example and on make_job_config.
Writer-port parity fuzz against node writer004:
  - validate_carrier_port(strict=True) must equal writer004 on every carrier;
  - every divergence of the default (relaxed) port must be classified into a documented
    relaxation class by writer004's own code and location: o13_m_n_selection_evidence
    (SELECTION_ONLY_ENGINEERING_ID at items[i].values.M|N holding selection_evidence) or
    r57_null_c_research_draft (UNRESOLVED_ITEM_MUST_BE_HELD at items[i] with C null and status
    research_draft). The class o16_q_unverified_adoption has no divergence (writer004 never reads
    the adoption status): every Q-under-unverified carrier must agree. Any other divergence fails;
  - every carrier the relaxed port accepts must be accepted by writer004 after the documented
    neutralization (research/export README, --mode v2): M/N selection evidence -> placeholder
    location evidence; C-null research_draft -> status held, plus one placeholder review reason
    when the item has none.
Usage: python3 -I run_route_tests.py --writer-dir DIR --work NEWDIR
"""
import argparse, copy, hashlib, importlib.util, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent / 'package'
ROUTE = PKG / 'tools' / 'cps046b_route.py'
COMPARER = HERE.parents[1] / 'evaluation' / 'compare_source043.py'
# writer004.mjs: archived original, or the public copy in research/checkpoint045/writer that differs only in the
# redacted Windows helper path on line 218 (not reached by validateCarrier/prepareMatrices; see research/export).
WRITER_SHA = {'writer004.mjs': ('85a7f619b9cfedc0c3c851b34c1d8cee38cfe5ab88ed050fcf4bba566c18c0d7',
                                '70d7f66455bfc5a2a6574b01509cfb78576a21b75bd7d75500746faf2661efb7'),
              'validate_carrier_v4.mjs': ('984da083219fa3df69dfd34652115fe1ddd5cd0ed723321981916adc5a87e013',),
              'receipt_bytes.mjs': ('b2ff15fd5d44a8adfbd5370f8bf8d81c432b89f5a6ea4f81d71477e283d11d2c',)}
EXAMPLE_INV = PKG / 'resources' / 'EXAMPLE_INVENTORY.json'
JOB_CONFIG = HERE.parent / 'harness' / 'make_job_config.py'
EXAMPLE_RESP = PKG / 'resources' / 'EXAMPLE_RESPONSE.json'


def _rows(c):
    try:
        return [r for r in list(c['items']) + list(c['components']) if isinstance(r, dict)]
    except (KeyError, TypeError):
        return []


def has_mn_selection(c):
    return any(isinstance(r.get('evidence'), dict) and isinstance(r['evidence'].get(k), dict) and 'selection_evidence' in r['evidence'][k]
               for r in _rows(c) for k in ('M', 'N'))


def is_r57(r):
    v = r.get('values')
    return isinstance(v, list) and len(v) > 2 and v[2] is None and r.get('status') == 'research_draft'


def has_r57(c):
    return any(is_r57(r) for r in _rows(c))


def has_q_unverified(c):
    md = c.get('metadata') if isinstance(c, dict) else None
    return (isinstance(md, dict) and md.get('source_adoption') != 'verified'
            and any(isinstance(r.get('values'), list) and len(r['values']) == 17 and r['values'][16] is not None for r in _rows(c)))


R57_PLACEHOLDER = ('R57 relaxation placeholder: C is null with status research_draft in the carrier; '
                   'status held and this reason exist only in the writer004 validation copy.')


def placeholder_copy(c):
    """Documented neutralization (research/export README, --mode v2), written independently here.
    O13: each M/N selection_evidence becomes location evidence of the same item: location = the item's own
    location, anchor = the item's anchor, raw_text = the selection_evidence text; transformation and any
    other key unchanged. R57: an item or component with C null and status research_draft gets status held,
    and, when its review_reasons is an empty list, the one placeholder review reason."""
    c = copy.deepcopy(c)
    for r in _rows(c):
        ev = r.get('evidence')
        for k in ('M', 'N'):
            e = ev.get(k) if isinstance(ev, dict) else None
            if isinstance(e, dict) and 'selection_evidence' in e:
                rest = {x: y for x, y in e.items() if x != 'selection_evidence'}
                r['evidence'][k] = dict(rest, location=copy.deepcopy(r.get('location')), anchor=r.get('anchor'), raw_text=e['selection_evidence'])
        if is_r57(r):
            r['status'] = 'held'
            if r.get('review_reasons') == []:
                r['review_reasons'] = [R57_PLACEHOLDER]
    return c


DIVERGENCE_LOC_RE = re.compile(r'items\[(0|[1-9][0-9]*)\](?:\.values\.([A-Q]))?')


def classify_divergence(c, node_code, node_loc):
    """Documented relaxation class of a port/writer004 divergence, from writer004's own code and location; else None."""
    m = DIVERGENCE_LOC_RE.fullmatch(node_loc or '')
    rows = list(c['items']) + list(c['components'])      # writer004 indexes [...items, ...components]
    if not m or int(m[1]) >= len(rows) or not isinstance(rows[int(m[1])], dict):
        return None
    r = rows[int(m[1])]
    if node_code == 'SELECTION_ONLY_ENGINEERING_ID' and m[2] in ('M', 'N'):
        e = r.get('evidence', {}).get(m[2]) if isinstance(r.get('evidence'), dict) else None
        if isinstance(e, dict) and 'selection_evidence' in e:
            return 'o13_m_n_selection_evidence'
    if node_code == 'UNRESOLVED_ITEM_MUST_BE_HELD' and m[2] is None and is_r57(r):
        return 'r57_null_c_research_draft'
    return None
COLS = 'ABCDEFGHIJKLMNOPQ'
results = []


def sha(b):
    return hashlib.sha256(b).hexdigest()


def record(name, ok, detail=None):
    results.append({'test': name, 'pass': bool(ok), **({'detail': detail} if detail is not None else {})})


def run(args):
    p = subprocess.run(args, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def route(*args):
    return run([sys.executable, '-I', str(ROUTE), *args])


def node_validate(writer_dir, carrier_path):
    code, out, err = run(['node', str(Path(writer_dir) / 'validate_carrier_v4.mjs'), '--carrier', str(carrier_path)])
    return code, (json.loads(out) if code == 0 else json.loads(err))


def load_module(path, name):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--writer-dir', required=True)
    ap.add_argument('--work', required=True)
    a = ap.parse_args()
    wd, work = Path(a.writer_dir), Path(a.work)
    work.mkdir(parents=True, exist_ok=False)
    for f, h in WRITER_SHA.items():
        record(f'writer_bytes_{f}', sha((wd / f).read_bytes()) in h)
    fx = work / 'fixtures'
    code, out, err = run([sys.executable, '-I', str(HERE / 'make_fixtures.py'), str(fx)])
    record('make_fixtures', code == 0, err[-300:] if code else None)
    inv, valid = fx / 'fixture_inventory.json', fx / 'valid_response.json'
    jinv = fx / 'fixture_inventory_jobs.json'

    # positive route
    code, out, _ = route('check', '--inventory', str(inv), '--response', str(valid))
    rep = json.loads(out)
    record('valid_check_pass', code == 0 and rep['status'] == 'PASS', rep['violations'][:5])
    record('v42_legacy_fixture_policy_checks_not_applied', rep.get('policy_checks') == 'not_applied_no_job_input_facts'
           and rep['warnings'] == [], rep.get('policy_checks'))
    code, out, _ = route('convert', '--inventory', str(inv), '--response', str(valid), '--out-dir', str(work / 'valid_out'))
    record('valid_convert', code == 0, out[-300:])
    carrier_path = work / 'valid_out' / 'carrier.json'
    code, res = node_validate(wd, carrier_path)
    record('valid_writer004_validateCarrier', code == 0 and res['status'] == 'WRITER_STRUCTURAL_VALIDATION_ONLY', res)
    carrier = json.loads(carrier_path.read_text(encoding='utf-8'))
    resp = json.loads(valid.read_text(encoding='utf-8'))
    invd = json.loads(inv.read_text(encoding='utf-8'))
    byid = {r['id']: r for r in carrier['items'] + carrier['components']}
    record('values_unchanged_type_exact', all(json.dumps(byid[i['id']]['values'], ensure_ascii=False) == json.dumps(i['values'], ensure_ascii=False)
                                              and [type(x) for x in byid[i['id']]['values']] == [type(x) for x in i['values']] for i in resp['items']))
    exp_raw = {('R001', 'description'): 'QX-620電磁接觸器 AC110V\n附端子蓋', ('R001', 'remarks'): None,
               ('R003', 'remarks'): '001.00', ('R004', 'unit_price'): '0.30000000000000004', ('R004', 'quantity'): '0',
               ('R005', 'unit_price'): '0.00001', ('R002', 'unit_price'): '120.5', ('R001', 'amount'): '3000',
               ('R005', 'remarks'): '0~100℃', ('C001', 'quantity'): '2'}
    bad = {k: byid[k[0]]['raw'][k[1]] for k, v in exp_raw.items() if byid[k[0]]['raw'][k[1]] != v}
    record('raw_profile_numeric_text_and_joins', not bad, bad or None)
    cells = {c['ref']: c for c in invd['cells']}
    record('inventory_canonical_values', all(cells[r]['canonical_raw'] == v for r, v in json.loads((fx / 'MUTATIONS.json').read_text(encoding='utf-8'))['expected_canonical'].items()))
    census = {n['anchor']: n for n in carrier['nonitems']}
    r1 = byid['R001']
    record('anchor_plus_census', 'cell:S1!A4' in census and 'A4' in r1['location']['cells'] and census['cell:S1!A4']['kind'] == 'item_identifier')
    t0, n0 = json.loads(census['cell:S1!C17']['text']), json.loads(census['cell:S1!D17']['text'])
    record('typed_census_distinguishes_text_zero_and_number_zero', t0 == {'saved_type': 'text', 'state': 'literal', 'value': '0', 'formula_record_present': False, 'conflicts': []}
           and n0 == {'saved_type': 'number', 'state': 'literal', 'value': 0.0, 'formula_record_present': False, 'conflicts': []})
    record('census_excludes_demand_content_and_empty', 'cell:S1!B4' not in census and 'cell:S1!G4' not in census and 'cell:S1!G6' not in census and 'cell:S1!B10' in census)
    record('census_keeps_formula_flag', json.loads(census['cell:S1!E16']['text'])['formula_record_present'] is True and json.loads(census['cell:S1!F9']['text'])['formula_record_present'] is True)
    record('typed_census_unusable_states_kept', json.loads(census['cell:S1!E16']['text'])['state'] == 'error'
           and json.loads(census['cell:S1!D16']['text'])['value'] is True)
    ev = r1['evidence']
    record('evidence_keys_exact', all(set(e) in ({'location', 'anchor', 'raw_text', 'transformation'}, {'selection_evidence', 'transformation'}) for r in byid.values() for e in r['evidence'].values()))
    record('L_selection_evidence_only', set(ev['L']) == {'selection_evidence', 'transformation'} and json.loads(ev['L']['selection_evidence'])['context'][0]['value'] == 'FIXTURE01')
    packed = json.loads(ev['D']['transformation'])
    record('role_basis_losslessly_packed', packed == {'transformation': resp['items'][0]['proofs']['D']['transformation'],
                                                      'role_basis': resp['items'][0]['proofs']['D']['role_basis'], 'context_refs': []})
    record('multi_cell_proof_raw_text', ev['D']['raw_text'] == 'QX-620電磁接觸器 AC110V\n附端子蓋' and ev['D']['location']['cells'] == ['B4', 'B5'])
    record('null_reasons_complete', all(set(r['null_reasons']) == {c for j, c in enumerate('ABCDEFGHIJKLMNOPQ') if r['values'][j] is None} for r in byid.values()))
    comp = byid['C001']['composition']
    record('component_composition', comp == {'parent_id': 'R003', 'basis_quantity': 2, 'basis_unit': '工',
                                              'basis_location': {'sheet': '單價分析', 'cells': ['C3', 'B3', 'D3'], 'views': [3]}, 'basis_raw': '2'})
    record('group_carried', carrier['groups'][0]['name'] == '示例控制盤' and json.loads(carrier['groups'][0]['anchor'])['relationship'] == 'contractual_group')
    led = json.loads((work / 'valid_out' / 'CENSUS_LEDGER.json').read_text(encoding='utf-8'))
    record('ledger_complete_positions', led['positions'] == len(invd['cells']) and sum(e['census'] for e in led['entries']) == len(carrier['nonitems'])
           and carrier['metadata']['census_ledger_sha256'] == sha((work / 'valid_out' / 'CENSUS_LEDGER.json').read_bytes()))
    record('carrier_source_verbatim', carrier['source'] == invd['source']['carrier_source'])
    cols17 = {c: [False, False] for c in 'ABCDEFGHIJKLMNOPQ'}
    for r in resp['items']:
        for j, c in enumerate('ABCDEFGHIJKLMNOPQ'):
            cols17[c][0 if r['values'][j] is not None else 1] = True
    record('all_17_null_paths_exercised', all(v[1] for v in cols17.values()))
    record('nonnull_paths_exercised_except_G_H_Q', all(v[0] for c, v in cols17.items() if c not in 'GHQ'))
    record('example_follows_046c_R6_label', json.loads(json.dumps(resp['items'][0]['proofs']['K']))['role_basis'].endswith('訂購廠商'))

    # verified adoption Q path
    code, out, _ = route('convert', '--inventory', str(fx / 'fixture_inventory_verified.json'), '--response', str(fx / 'valid_response_verified_Q.json'), '--out-dir', str(work / 'q_out'))
    qc, qres = node_validate(wd, work / 'q_out' / 'carrier.json') if code == 0 else (1, out)
    record('Q_nonnull_with_verified_adoption_route', code == 0 and qc == 0, qres if qc else None)

    # comparator pairing interface (frozen evaluator code, invented expectations)
    cmp = load_module(COMPARER, 'compare_source043_frozen')
    rows = []
    anchors = {'R001': 4, 'R002': 6, 'R003': 7, 'R004': 8, 'R005': 11, 'R006': 12, 'R007': 18}
    for r in resp['items']:
        if r['id'] in anchors:
            rows.append({'id': 'E' + r['id'], 'category': 'detail', 'sheet': '示例明細', 'anchor_row': anchors[r['id']],
                         'expected_values': r['values'], 'raw': byid[r['id']]['raw'], 'supported_columns': list('CEF'),
                         'core_columns': list('CEF')})
    expected = {'case_id': 'FIXTURE01', 'rows': rows, 'denominators': {'component_rows': 0}, 'nonitem_cell_census':
                [{'sheet': '示例明細', 'cell': c} for c in ('A2', 'A4', 'B9', 'B10')],
                'carrier_contract': {k: carrier[k] for k in ('schema', 'case_id', 'family_id', 'source')}}
    cmp.check_interface(expected, carrier)
    out = cmp.evaluate(expected, carrier)
    core = out['metrics']['detail']['modes']['canonical']['core']
    record('comparator_pairs_every_anchor_row', not out['correspondence_incidents'] and core['matches'] == core['denominator']
           and out['nonitem_cell_locator_coverage']['covered'] == 4, {'incidents': out['correspondence_incidents'], 'core': core})

    # mutations
    idx = json.loads((fx / 'MUTATIONS.json').read_text(encoding='utf-8'))['mutations']
    for mu in idx:
        minv = fx / mu.get('inventory', 'fixture_inventory.json')
        code, out, _ = route('check', '--inventory', str(minv), '--response', str(fx / mu['file']))
        rep = json.loads(out)
        codes = sorted({v['code'].split(':')[0] for v in rep['violations']})
        cats = {v['code'].split(':')[0]: v['category'] for v in rep['violations']}
        want_cat = {'raw_date_cell': 'field_must_be_null', 'F_proof_text_cell': 'field_must_be_null', 'date_cell_proof_O': 'field_must_be_null',
                    'unicode_digit_quantity': 'field_must_be_null', 'context_only_C': 'field_must_be_null',
                    'formula_like_D': 'unrepresentable_hold', 'component_link_held': 'unrepresentable_hold',
                    'long_packed_transformation': 'unrepresentable_hold', 'too_many_nonitems': 'unrepresentable_hold',
                    'unknown_ref': 'invalid', 'dropped_item': 'invalid',
                    'v4_I_brand_table_only': 'field_must_be_null', 'v4_J_brand_table_only': 'field_must_be_null',
                    'v4_C_glossary_only': 'field_must_be_null', 'v4_J_company_name_only': 'field_must_be_null',
                    'v4_K_company_name_only': 'field_must_be_null', 'v4_D_project_name_only': 'field_must_be_null',
                    'v4_M_unknown_context': 'invalid', 'v4_N_numeric_value': 'invalid',
                    'v41_null_C_research_draft_no_reason': 'invalid', 'v41_null_C_research_draft_blank_reason': 'invalid',
                    'v41_null_C_research_draft_reason_with_refs': 'invalid', 'v41_null_C_status_partial': 'invalid',
                    'v41_Q_unverified_amount_not_unit_price': 'invalid', 'v41_Q_unverified_text_cell': 'field_must_be_null',
                    'v41_Q_unverified_as_text': 'invalid'}.get(mu['name'], 'invalid' if mu['name'].startswith('v42_') else None)
        ok = code == 1 and mu['expected_code'] in codes and (want_cat is None or cats.get(mu['expected_code']) == want_cat)
        c2, out2, _ = route('convert', '--inventory', str(minv), '--response', str(fx / mu['file']), '--out-dir', str(work / ('mut_' + mu['name'])))
        refused = c2 == 1 and not (work / ('mut_' + mu['name']) / 'carrier.json').exists() and (work / ('mut_' + mu['name']) / 'CENSUS_LEDGER.json').exists()
        record('mutation_' + mu['name'], ok and refused, None if ok and refused else {'expected': mu['expected_code'], 'got': codes})

    # writer parity: the same defects injected directly into a carrier are rejected by writer004 itself
    def inject(name, f, want):
        c = copy.deepcopy(carrier)
        f(c)
        p = work / f'parity_{name}.json'
        p.write_text(json.dumps(c, ensure_ascii=False), encoding='utf-8')
        code, res = node_validate(wd, p)
        record('writer_parity_' + name, code == 1 and res.get('code') == want, res)
    it = lambda c, i: next(x for x in c['items'] + c['components'] if x['id'] == i)
    inject('formula_like_value', lambda c: it(c, 'R005')['values'].__setitem__(3, '-20~60℃'), 'FORMULA_STRING_FORBIDDEN')
    inject('purchase_price', lambda c: it(c, 'R002')['values'].__setitem__(6, 1), 'PURCHASE_PRICE_MUST_BE_BLANK')
    inject('ungrouped_ab', lambda c: it(c, 'R002').update(group_id=None), 'UNGROUPED_AB_MUST_BE_BLANK')
    inject('item_partial', lambda c: it(c, 'R002').update(status='partial'), 'REVIEW_STATUS_REQUIRED')
    inject('quantity_mismatch', lambda c: it(c, 'R002')['raw'].update(quantity='4'), 'SOURCE_QUANTITY_MISMATCH')
    inject('unit_mismatch', lambda c: it(c, 'R002')['raw'].update(unit='只'), 'SOURCE_UNIT_MISMATCH')
    inject('role_basis_key', lambda c: it(c, 'R002')['evidence']['C'].update(role_basis='x'), 'EXACT_KEYS_REQUIRED')
    inject('text_census', lambda c: c['nonitems'][0].update(text=0), 'STRING_REQUIRED')
    inject('component_basis', lambda c: it(c, 'C001')['composition'].update(basis_raw='3'), 'POSITIVE_LITERAL_BASIS_REQUIRED')
    inject('view_unaccounted', lambda c: (c['components'].clear(), c.update(nonitems=[n for n in c['nonitems'] if n['location']['sheet'] != '單價分析'])), 'VIEW_SCOPE_UNACCOUNTED')
    inject('pathlike_selection', lambda c: it(c, 'R001')['evidence']['L'].update(selection_evidence='C:\\x'), 'EXTRA_SOURCE_REFERENCE')

    # writer parity fuzz: Python port vs the real writer004 prepareMatrices on the same carriers
    route_mod = load_module(ROUTE, 'cps046b_route_under_test')
    fuzz = []
    def variant(label, f):
        c = copy.deepcopy(carrier)
        f(c)
        fuzz.append((label, c))
    nums = ['3', '3.0', '+3', '03', '3,000', '1,00', '３', '٣', ' 3 ', '\u30003', '\u00a03', '3\u2028', '\ufeff3', '3.', '.3',
            '3e0', '0x3', '\u22123', '-3', '', '\t3\n', '3\x0b', '0003.000', '2.9999999999999999', '9007199254740993']
    for s_ in nums:
        variant('qty:' + repr(s_), lambda c, s_=s_: (it(c, 'R002')['raw'].update(quantity=s_), it(c, 'R002')['evidence']['F'].update(raw_text=s_)))
    texts = ['a' * 30000, 'a' * 30001, '\U00020000' * 15000, '\U00020000' * 15001, ' ', '\u3000', '\ufeff', '\u200b', '\x0b', '\x7f', '\u0085',
             '=a', '\u3000=a', '\ufeff+a', '\u00a0@a', '\u2028-a', '\u200b-a', '\u0085-a', 'a\u2029b']
    for s_ in texts:
        variant('C:' + repr(s_[:12]) + f'/{len(s_)}', lambda c, s_=s_: it(c, 'R002')['values'].__setitem__(2, s_))
        variant('nonitem_text:' + repr(s_[:12]) + f'/{len(s_)}', lambda c, s_=s_: c['nonitems'][0].update(text=s_))
        variant('transformation:' + repr(s_[:12]) + f'/{len(s_)}', lambda c, s_=s_: it(c, 'R002')['evidence']['C'].update(transformation=s_))
    for s_ in ['C:\\x', 'c:/x', '\\\\srv\\x', 'file://x', 'HTTP://x', 'x:y', 'cell:S1!A1']:
        variant('meta:' + repr(s_), lambda c, s_=s_: c['metadata'].update(note=s_))
    variant('meta_key_sources', lambda c: c['metadata'].update(sources='x'))
    variant('nonitems_5001', lambda c: c.update(nonitems=[c['nonitems'][0]] * 5001))
    variant('review_cell_long', lambda c: it(c, 'R002').update(review_reasons=['r' * 30000, 'r' * 3000]))
    variant('values_review_cell_long', lambda c: (it(c, 'R002')['values'].__setitem__(3, 'd' * 20000), it(c, 'R002')['null_reasons'].pop('D'),
                                                 it(c, 'R002')['evidence'].update(D=dict(it(c, 'R002')['evidence']['C'])), it(c, 'R002')['values'].__setitem__(8, 'i' * 20000),
                                                 it(c, 'R002')['null_reasons'].pop('I'), it(c, 'R002')['evidence'].update(I=dict(it(c, 'R002')['evidence']['C']))))
    variant('group_limitations_501', lambda c: c['groups'][0].update(limitations=['x'] * 501))
    variant('duplicate_location_cell', lambda c: it(c, 'R002')['location']['cells'].append(it(c, 'R002')['location']['cells'][0]))
    variant('view_zero', lambda c: it(c, 'R002')['location'].update(views=[0]))
    variant('basis_unit_formula', lambda c: it(c, 'C001')['composition'].update(basis_unit='-x'))
    variant('basis_raw_unicode', lambda c: it(c, 'C001')['composition'].update(basis_raw='２'))
    # 046f job-input carrier (M/N selection evidence on demand and component rows)
    jv = fx / 'valid_response_job_inputs.json'
    code, out, _ = route('check', '--inventory', str(jinv), '--response', str(jv))
    jrep = json.loads(out)
    record('v4_job_inputs_check_pass_with_O13_warning', code == 0 and jrep['status'] == 'PASS' and jrep['route'] == route_mod.VERSION == 'cps046f-route.v4.2'
           and [w['code'] for w in jrep['warnings']] == ['O13_SELECTION_EVIDENCE_M_N'] and jrep['warnings'][0]['detail']['count'] == 18,
           jrep['violations'][:5] or jrep['warnings'])
    record('v42_job_packet_policy_checks_applied', jrep.get('policy_checks') == 'applied', jrep.get('policy_checks'))
    code, out, _ = route('convert', '--inventory', str(jinv), '--response', str(jv), '--out-dir', str(work / 'jobs_out'))
    record('v4_job_inputs_convert', code == 0, out[-300:])
    jcarrier = json.loads((work / 'jobs_out' / 'carrier.json').read_text(encoding='utf-8'))
    jrec = json.loads((work / 'jobs_out' / 'ADAPTER_RECEIPT.json').read_text(encoding='utf-8'))
    jresp = json.loads(jv.read_text(encoding='utf-8'))
    ctxv = {x['ref']: x['value'] for x in json.loads(jinv.read_text(encoding='utf-8'))['context_facts']}
    jall = jcarrier['items'] + jcarrier['components']
    def sel(r, k):
        e = r['evidence'][k]
        return set(e) == {'selection_evidence', 'transformation'} and json.loads(e['selection_evidence'])['context'][0]['value'] == r['values'][COLS.index(k)]
    record('v4_M_N_L_selection_evidence_from_job_inputs', all(sel(r, k) for r in jall for k in 'LMN')
           and all(r['values'][12] == ctxv['context:customer_name'] and r['values'][13] == ctxv['context:project_name'] for r in jall)
           and len(jcarrier['components']) == 2 and jcarrier['metadata']['adapter'] == 'cps046f-route.v4.2'
           and all(r['values'][k] is None for r in jall for k in (10, 14, 15))
           and [r['id'] for r in jcarrier['items'] if r['group_id'] is not None] == ['R001'])
    record('v42_receipt_reports_policy_checks', jrec.get('policy_checks') == 'applied', jrec.get('policy_checks'))
    record('v4_receipt_reports_O13', jrec['o13_m_n_selection_evidence']['count'] == 18 and jrec['o13_m_n_selection_evidence']['export_mode_required'] == 'v2'
           and jrec['o13_m_n_selection_evidence']['writer004_validateCarrier_accepts'] is False)
    r1j = next(r for r in jcarrier['items'] if r['id'] == 'R001')
    record('v4_resource_proof_cell_plus_context_is_location_evidence', set(r1j['evidence']['I']) == {'location', 'anchor', 'raw_text', 'transformation'}
           and json.loads(r1j['evidence']['I']['transformation'])['context_refs'] == ['context:brand_table'] and r1j['values'][8] == 'XM-10'
           and r1j['evidence']['I']['location']['cells'] == ['B4'])
    record('v4_values_unchanged_type_exact', all(json.dumps(r['values'], ensure_ascii=False) == json.dumps(i['values'], ensure_ascii=False)
                                                 for r, i in zip(jcarrier['items'] + jcarrier['components'], [x for x in jresp['items'] if x['role'] == 'demand'] + [x for x in jresp['items'] if x['role'] != 'demand'])))
    code, res = node_validate(wd, work / 'jobs_out' / 'carrier.json')
    record('v4_writer004_rejects_M_N_selection_evidence_documented_divergence', code == 1 and res.get('code') == 'SELECTION_ONLY_ENGINEERING_ID'
           and '.values.M' in res.get('message', ''), res)
    record('v4_python_port_accepts_M_N_selection_evidence', route_mod.validate_carrier_port(copy.deepcopy(jcarrier)) is True)
    pc_path = work / 'jobs_placeholder_carrier.json'
    pc_path.write_text(json.dumps(placeholder_copy(jcarrier), ensure_ascii=False), encoding='utf-8')
    code, res = node_validate(wd, pc_path)
    record('v4_writer004_accepts_placeholder_copy', code == 0 and res['status'] == 'WRITER_STRUCTURAL_VALIDATION_ONLY', res)
    def port_code(c, strict=False):
        try:
            route_mod.validate_carrier_port(c, strict=strict)
            return 'PASS'
        except route_mod.WriterReject as e:
            return e.code
        except Exception as e:      # a crash is a defect: it never matches a writer004 code
            return 'PORT_EXCEPTION:' + type(e).__name__
    for col in ('C', 'I', 'K', 'O', 'P'):
        bad = copy.deepcopy(jcarrier)
        it(bad, 'R002')['values'][COLS.index(col)] = 2 if col == 'P' else 'x'
        it(bad, 'R002')['null_reasons'].pop(col, None)
        it(bad, 'R002')['evidence'][col] = dict(it(bad, 'R002')['evidence']['M'])
        record(f'v4_port_rejects_selection_evidence_on_{col}', port_code(bad) == 'SELECTION_ONLY_ENGINEERING_ID')

    # ------------------------------------------------ route v4.1 relaxations (a) R57, (b) O16 Q, (c) R56 one-member group
    record('v41_route_version_and_documented_port_relaxations', route_mod.VERSION == 'cps046f-route.v4.2'
           and set(route_mod.PORT_RELAXATIONS) == {'o13_m_n_selection_evidence', 'r57_null_c_research_draft', 'o16_q_unverified_adoption'}
           and route_mod.SELECTION_COLS == ('L', 'M', 'N') and route_mod.WRITER004_SELECTION_COLS == ('L',))
    v41 = {}
    for tag, resp_name, inv_name in (('r57', 'valid_response_r57_null_c.json', 'fixture_inventory.json'),
                                     ('q', 'valid_response_q_unverified.json', 'fixture_inventory.json'),
                                     ('q_partial', 'valid_response_q_partial.json', 'fixture_inventory_partial.json'),
                                     ('all', 'valid_response_relaxed_all.json', 'fixture_inventory_jobs.json'),
                                     ('group1', 'valid_response_one_member_group.json', 'fixture_inventory.json')):
        code, out, _ = route('check', '--inventory', str(fx / inv_name), '--response', str(fx / resp_name))
        rep_ = json.loads(out)
        c2, out2, _ = route('convert', '--inventory', str(fx / inv_name), '--response', str(fx / resp_name), '--out-dir', str(work / f'v41_{tag}_out'))
        ok = c2 == 0 and (work / f'v41_{tag}_out' / 'carrier.json').is_file()
        v41[tag] = {'check_code': code, 'report': rep_, 'convert_ok': ok,
                    'carrier': json.loads((work / f'v41_{tag}_out' / 'carrier.json').read_text(encoding='utf-8')) if ok else None,
                    'receipt': json.loads((work / f'v41_{tag}_out' / 'ADAPTER_RECEIPT.json').read_text(encoding='utf-8')) if ok else None,
                    'path': work / f'v41_{tag}_out' / 'carrier.json'}
        record(f'v41_{tag}_check_pass_and_convert', code == 0 and rep_['status'] == 'PASS' and ok, rep_['violations'][:5])
    wcodes = lambda tag: [w['code'] for w in v41[tag]['report']['warnings']]
    # (a) R57: C null with status research_draft
    a_ = v41['r57']
    ca = a_['carrier']
    w57 = next((w for w in a_['report']['warnings'] if w['code'] == 'R57_NULL_C_RESEARCH_DRAFT'), {})
    record('v41_a_r57_warning_not_violation', wcodes('r57') == ['R57_NULL_C_RESEARCH_DRAFT'] and w57['detail']['count'] == 2
           and w57['detail']['first'] == ['R003', 'C001'], a_['report']['warnings'])
    record('v41_a_r57_carrier_keeps_null_reason_and_status', ca is not None
           and all(it(ca, i)['values'][2] is None and it(ca, i)['status'] == 'research_draft' and isinstance(it(ca, i)['null_reasons'].get('C'), str)
                   and 'C' not in it(ca, i)['evidence'] for i in ('R003', 'C001'))
           and it(ca, 'C001')['review_reasons'] == [] and it(ca, 'R003')['review_reasons'] != [])
    ra = a_['receipt']
    record('v41_a_r57_receipt_requires_mode_v2', ra['r57_null_c_research_draft'] == {'count': 2, 'first': ['R003', 'C001'],
           'writer004_validateCarrier_accepts': False, 'export_mode_required': 'v2'} and ra['export_mode_required'] == 'v2'
           and ra['writer004_validateCarrier_accepts'] is False and ra['o13_m_n_selection_evidence']['count'] == 0, ra)
    code, res = node_validate(wd, a_['path'])
    r3i = [x['id'] for x in ca['items'] + ca['components']].index('R003')
    record('v41_a_writer004_rejects_null_c_research_draft_documented_divergence', code == 1 and res.get('code') == 'UNRESOLVED_ITEM_MUST_BE_HELD'
           and res.get('message', '').endswith(f'items[{r3i}]'), res)
    record('v41_a_port_relaxed_accepts_strict_rejects', port_code(copy.deepcopy(ca)) == 'PASS' and port_code(copy.deepcopy(ca), strict=True) == 'UNRESOLVED_ITEM_MUST_BE_HELD')
    nc_ = copy.deepcopy(ca)
    it(nc_, 'R003')['null_reasons'].pop('C')
    record('v41_a_port_still_requires_null_reason_C', port_code(nc_) in ('STRING_REQUIRED', 'EXACT_KEYS_REQUIRED'), port_code(nc_))
    nc_ = copy.deepcopy(ca)
    it(nc_, 'C001')['null_reasons']['C'] = ' '
    record('v41_a_port_rejects_blank_null_reason_C', port_code(nc_) == 'STRING_REQUIRED')
    nc_ = copy.deepcopy(ca)
    it(nc_, 'R003')['status'] = 'partial'
    record('v41_a_port_still_rejects_other_status', port_code(nc_) == 'REVIEW_STATUS_REQUIRED')
    p57 = work / 'v41_r57_neutralized_copy.json'
    p57.write_text(json.dumps(placeholder_copy(ca), ensure_ascii=False), encoding='utf-8')
    code, res = node_validate(wd, p57)
    pcopy = json.loads(p57.read_text(encoding='utf-8'))
    record('v41_a_writer004_accepts_neutralized_copy', code == 0 and res['status'] == 'WRITER_STRUCTURAL_VALIDATION_ONLY'
           and it(pcopy, 'C001')['review_reasons'] == [R57_PLACEHOLDER] and it(pcopy, 'R003')['review_reasons'] == it(ca, 'R003')['review_reasons']
           and it(pcopy, 'R003')['status'] == it(pcopy, 'C001')['status'] == 'held', res)
    # (b) O16: Q under unverified (and partial) adoption
    for tag, status_ in (('q', 'unverified'), ('q_partial', 'partial')):
        b_ = v41[tag]
        wq = next((w for w in b_['report']['warnings'] if w['code'] == 'O16_Q_UNVERIFIED_ADOPTION'), {})
        record(f'v41_b_{tag}_warning_not_violation', wcodes(tag) == ['O16_Q_UNVERIFIED_ADOPTION'] and wq['detail']['count'] == 1
               and wq['detail']['first'] == ['R006'] and wq['detail']['adoption_status'] == status_, b_['report']['warnings'])
        cb = b_['carrier']
        rb = b_['receipt']
        record(f'v41_b_{tag}_carrier_and_receipt', cb is not None and it(cb, 'R006')['values'][16] == 50000
               and it(cb, 'R006')['evidence']['Q']['raw_text'] == '50000' and cb['metadata']['source_adoption'] == status_
               and rb['o16_q_unverified_adoption']['count'] == 1 and rb['o16_q_unverified_adoption']['adoption_status'] == status_
               and rb['export_mode_required'] == 'v1' and rb['writer004_validateCarrier_accepts'] is True, rb)
        code, res = node_validate(wd, b_['path'])
        record(f'v41_b_{tag}_writer004_accepts_directly_no_adoption_check', code == 0 and res['status'] == 'WRITER_STRUCTURAL_VALIDATION_ONLY', res)
        record(f'v41_b_{tag}_port_relaxed_and_strict_accept', port_code(copy.deepcopy(cb)) == 'PASS' and port_code(copy.deepcopy(cb), strict=True) == 'PASS')
    code, out, _ = route('check', '--inventory', str(fx / 'fixture_inventory_verified.json'), '--response', str(fx / 'valid_response_verified_Q.json'))
    record('v41_b_verified_adoption_Q_has_no_warning', code == 0 and json.loads(out)['warnings'] == [], json.loads(out)['warnings'])
    # all relaxations together with the job inputs
    al = v41['all']
    record('v41_all_three_warnings', wcodes('all') == ['O13_SELECTION_EVIDENCE_M_N', 'R57_NULL_C_RESEARCH_DRAFT', 'O16_Q_UNVERIFIED_ADOPTION'], wcodes('all'))
    code, res = node_validate(wd, al['path'])
    record('v41_all_writer004_rejects_original', code == 1 and res.get('code') in ('SELECTION_ONLY_ENGINEERING_ID', 'UNRESOLVED_ITEM_MUST_BE_HELD'), res)
    pal = work / 'v41_all_neutralized_copy.json'
    pal.write_text(json.dumps(placeholder_copy(al['carrier']), ensure_ascii=False), encoding='utf-8')
    code, res = node_validate(wd, pal)
    record('v41_all_port_accepts_and_writer004_accepts_neutralized_copy', code == 0 and port_code(copy.deepcopy(al['carrier'])) == 'PASS'
           and al['receipt']['export_mode_required'] == 'v2', res)
    # (c) R56: a physical_enclosure group with exactly one member
    g_ = v41['group1']
    cg = g_['carrier']
    members = [x['id'] for x in cg['items'] + cg['components'] if x['group_id'] == 'G1']
    code, res = node_validate(wd, g_['path'])
    record('v41_c_one_member_group_accepted', wcodes('group1') == [] and len(cg['groups']) == 1 and members == ['R001']
           and json.loads(cg['groups'][0]['anchor'])['relationship'] == 'physical_enclosure'
           and all(x['values'][0] is None and x['values'][1] is None for x in cg['items'] if x['id'] != 'R001')
           and it(cg, 'R001')['values'][:2] == [cg['groups'][0]['name'], cg['groups'][0]['specification']]
           and code == 0 and port_code(copy.deepcopy(cg)) == 'PASS' == port_code(copy.deepcopy(cg), strict=True), res)

    def jvariant(label, f):
        c = copy.deepcopy(jcarrier)
        f(c)
        fuzz.append(('jobs:' + label, c))
    jvariant('unchanged', lambda c: None)
    def component_only(c):      # demand rows converted to placeholders: only the components keep M/N selection evidence
        pcopy = placeholder_copy(c)
        for r, q in zip(c['items'], pcopy['items']):
            r['evidence'] = q['evidence']
    jvariant('component_only_MN', component_only)
    jvariant('M_pathlike', lambda c: it(c, 'R002')['evidence']['M'].update(selection_evidence='C:\\x'))
    jvariant('N_url', lambda c: it(c, 'C001')['evidence']['N'].update(selection_evidence='see https://x'))
    jvariant('M_extra_key', lambda c: it(c, 'R002')['evidence']['M'].update(anchor='x'))
    jvariant('N_blank_selection', lambda c: it(c, 'R003')['evidence']['N'].update(selection_evidence=' '))
    jvariant('M_blank_transformation', lambda c: it(c, 'R003')['evidence']['M'].update(transformation='\u3000'))
    jvariant('M_control_char', lambda c: it(c, 'R004')['evidence']['M'].update(selection_evidence='a\x07b'))
    jvariant('N_long_30001', lambda c: it(c, 'R004')['evidence']['N'].update(selection_evidence='n' * 30001))
    jvariant('N_review_cell_32768', lambda c: it(c, 'R005')['evidence']['N'].update(selection_evidence='n' * 29000, transformation='t' * 3000))
    jvariant('M_value_formula', lambda c: it(c, 'R005')['values'].__setitem__(12, '-客戶'))
    jvariant('M_value_number', lambda c: it(c, 'R006')['values'].__setitem__(12, 3))
    jvariant('C_selection', lambda c: (it(c, 'R002')['values'].__setitem__(2, 'x'), it(c, 'R002')['evidence'].update(C=dict(it(c, 'R002')['evidence']['M']))))
    jvariant('K_selection', lambda c: (it(c, 'R002')['values'].__setitem__(10, 'x'), it(c, 'R002')['null_reasons'].pop('K'), it(c, 'R002')['evidence'].update(K=dict(it(c, 'R002')['evidence']['M']))))
    jvariant('qty_unicode', lambda c: (it(c, 'R002')['raw'].update(quantity='３'), it(c, 'R002')['evidence']['F'].update(raw_text='３')))
    jvariant('formula_C', lambda c: it(c, 'R002')['values'].__setitem__(2, '=a'))
    jvariant('ungrouped_ab', lambda c: it(c, 'R001').update(group_id=None))
    jvariant('view_zero', lambda c: it(c, 'R002')['location'].update(views=[0]))

    # v4.1 relaxation variants: C null research_draft (R57) and Q under unverified adoption (O16), on both base carriers
    def null_c(c, i, reason='Service or labour line: C is null (R52).', reasons=None):
        r = it(c, i)
        r['values'][2] = None
        r['evidence'].pop('C', None)
        if reason is not None:
            r['null_reasons']['C'] = reason
        r['status'] = 'research_draft'
        if reasons is not None:
            r['review_reasons'] = reasons
    def q_on(c, i='R006', value=50000, raw_text='50000', adoption=None):
        r = it(c, i)
        r['values'][16] = value
        r['null_reasons'].pop('Q', None)
        r['evidence']['Q'] = dict(r['evidence']['F'], raw_text=raw_text)
        if adoption is not None:
            c['metadata']['source_adoption'] = adoption
    for tag, base_c in (('r57', carrier), ('jobs_r57', jcarrier)):
        def rv(label, f, base_c=base_c, tag=tag):
            c = copy.deepcopy(base_c)
            f(c)
            fuzz.append((f'{tag}:{label}', c))
        rv('R007_research_draft_with_reasons', lambda c: it(c, 'R007').update(status='research_draft'))
        rv('R007_research_draft_no_reasons', lambda c: it(c, 'R007').update(status='research_draft', review_reasons=[]))
        rv('C001_null_c_no_reasons', lambda c: null_c(c, 'C001', reasons=[]))
        rv('R003_null_c_with_reason', lambda c: null_c(c, 'R003', reasons=['kept for review']))
        rv('two_null_c', lambda c: (null_c(c, 'R003', reasons=[]), null_c(c, 'C002', reasons=[])))
        rv('null_c_missing_null_reason', lambda c: null_c(c, 'R003', reason=None, reasons=[]))
        rv('null_c_blank_null_reason', lambda c: null_c(c, 'C001', reason='\u3000', reasons=[]))
        rv('null_c_held_reasons_empty', lambda c: (null_c(c, 'R003', reasons=[]), it(c, 'R003').update(status='held')))
        rv('null_c_status_partial', lambda c: (null_c(c, 'R003'), it(c, 'R003').update(status='partial')))
        rv('null_c_reasons_not_list', lambda c: null_c(c, 'C001', reasons='x'))
        rv('null_c_then_qty_mismatch', lambda c: (null_c(c, 'R003', reasons=[]), it(c, 'R003')['raw'].update(quantity='+4')))
        rv('null_c_then_formula_D', lambda c: (null_c(c, 'R004', reasons=[]), it(c, 'R004')['values'].__setitem__(3, '-x'),
                                              it(c, 'R004')['null_reasons'].pop('D', None), it(c, 'R004')['evidence'].update(D=dict(it(c, 'R004')['evidence']['F'], raw_text='-x'))))
        rv('null_c_then_review_cell_long', lambda c: (null_c(c, 'R003', reasons=['r' * 30000, 'r' * 3000])))
        rv('null_c_and_q', lambda c: (null_c(c, 'R003', reasons=[]), q_on(c)))
    for tag, base_c in (('q', carrier), ('jobs_q', jcarrier)):
        def qv(label, f, base_c=base_c, tag=tag):
            c = copy.deepcopy(base_c)
            f(c)
            fuzz.append((f'{tag}:{label}', c))
        qv('unverified', lambda c: q_on(c, adoption='unverified'))
        qv('partial', lambda c: q_on(c, adoption='partial'))
        qv('adoption_key_missing', lambda c: (q_on(c), c['metadata'].pop('source_adoption')))
        qv('value_mismatch', lambda c: q_on(c, value=50001))
        qv('raw_mismatch', lambda c: q_on(c, value=50001, raw_text='50001'))
        qv('unicode_raw', lambda c: q_on(c, raw_text='５0000'))
        qv('as_text', lambda c: q_on(c, value='50000'))
        qv('q_R002_decimal', lambda c: q_on(c, 'R002', value=120.5, raw_text='120.5'))
    for tag in ('r57', 'q', 'q_partial', 'all', 'group1'):
        if v41[tag]['carrier'] is not None:
            fuzz.append((f'convert:{tag}', copy.deepcopy(v41[tag]['carrier'])))
    for label, c in list(fuzz):
        if has_mn_selection(c) or has_r57(c):
            fuzz.append((label + ':neutralized_copy', placeholder_copy(c)))

    fp = work / 'parity_carriers.json'
    fp.write_text(json.dumps([c for _, c in fuzz], ensure_ascii=False), encoding='utf-8')
    pcode, pout, perr = run(['node', str(HERE / 'parity_batch.mjs'), str((wd / 'writer004.mjs').resolve()), str(fp.resolve())])
    node_res = json.loads(pout) if pcode == 0 else []
    strict_mism, unclassified, classified, q_cases, q_div = [], [], [], [], []
    for (label, c), nr in zip(fuzz, node_res):
        nc, nloc = nr['code'], nr['location']
        ps, pr = port_code(c, strict=True), port_code(c)
        if ps != nc:
            strict_mism.append({'case': label, 'python_strict': ps, 'node': nc, 'location': nloc})
        if has_q_unverified(c):
            q_cases.append(label)
            if not has_mn_selection(c) and not has_r57(c) and pr != nc:
                q_div.append({'case': label, 'python': pr, 'node': nc})
        if pr != nc:
            cls = classify_divergence(c, nc, nloc)
            (classified if cls else unclassified).append({'case': label, 'class': cls, 'python': pr, 'node': nc, 'location': nloc})
    ran = pcode == 0 and len(node_res) == len(fuzz)
    record('writer_port_strict_equals_writer004_on_every_carrier', ran and not strict_mism,
           {'cases': len(fuzz), 'mismatches': strict_mism[:10], 'stderr': perr[-300:]})
    record('writer_port_parity_fuzz_every_divergence_classified', ran and not unclassified,
           {'cases': len(fuzz), 'node_pass': sum(x['code'] == 'PASS' for x in node_res), 'unclassified': unclassified[:10]})
    classes = {d['class'] for d in classified}
    record('writer_port_parity_divergence_classes_documented_and_exercised', ran and classes == {'o13_m_n_selection_evidence', 'r57_null_c_research_draft'}
           and {d['case'] for d in classified} >= {'jobs:unchanged', 'jobs:component_only_MN', 'r57:R007_research_draft_no_reasons',
                                                    'r57:C001_null_c_no_reasons', 'convert:r57', 'convert:all'}
           and all(has_mn_selection(c) or has_r57(c) for lab, c in fuzz if lab in {d['case'] for d in classified}),
           {'classified': len(classified), 'by_class': {k: sum(d['class'] == k for d in classified) for k in classes}})
    record('writer_port_parity_q_unverified_class_has_no_divergence', ran and len(q_cases) >= 10 and not q_div,
           {'q_cases': len(q_cases), 'divergences': q_div[:5]})
    # completeness of the documented neutralization: whatever the relaxed port accepts, writer004 accepts after neutralization
    accepted = [(lab, c) for lab, c in fuzz if port_code(c) == 'PASS' and (has_mn_selection(c) or has_r57(c))]
    np_ = work / 'parity_neutralized.json'
    np_.write_text(json.dumps([placeholder_copy(c) for _, c in accepted], ensure_ascii=False), encoding='utf-8')
    ncode, nout, nerr = run(['node', str(HERE / 'parity_batch.mjs'), str((wd / 'writer004.mjs').resolve()), str(np_.resolve())])
    nres = json.loads(nout) if ncode == 0 else []
    bad_n = [{'case': lab, 'node_on_copy': r['code'], 'location': r['location']} for (lab, _), r in zip(accepted, nres) if r['code'] != 'PASS']
    record('writer_port_relaxed_accept_implies_writer004_accepts_neutralized_copy', ncode == 0 and len(nres) == len(accepted) >= 8 and not bad_n,
           {'accepted_relaxed': len(accepted), 'failures': bad_n[:5], 'stderr': nerr[-300:]})
    record('valid_carrier_port_pass', route_mod.validate_carrier_port(carrier) is True and route_mod.validate_carrier_port(carrier, strict=True) is True)

    # package example (046f, R47b-R58): check-inventory, check, convert, writer004 on the placeholder copy
    code, out, _ = route('check-inventory', '--inventory', str(EXAMPLE_INV))
    record('example_inventory_check_pass', code == 0 and json.loads(out)['status'] == 'PASS', out[-400:])
    exinv = json.loads(EXAMPLE_INV.read_text(encoding='utf-8'))
    record('example_inventory_has_046f_context_facts_without_brand_table', {x['ref'] for x in exinv['context_facts']} == {
        'context:case_identity', 'context:customer_name', 'context:project_name', 'context:company_name', 'context:glossary'}
           and json.loads(out).get('policy_checks') == 'applied', 'a 材料清單 packet carries no context:brand_table (O17, R47b, R55)')
    code, out, _ = route('check', '--inventory', str(EXAMPLE_INV), '--response', str(EXAMPLE_RESP))
    exrep = json.loads(out)
    record('example_response_check_pass', code == 0 and exrep['status'] == 'PASS', exrep['violations'][:5])
    record('example_uses_all_three_v41_relaxations_as_warnings', [w['code'] for w in exrep.get('warnings', [])]
           == ['O13_SELECTION_EVIDENCE_M_N', 'R57_NULL_C_RESEARCH_DRAFT', 'O16_Q_UNVERIFIED_ADOPTION']
           and exinv['source']['adoption_status'] == 'unverified', exrep.get('warnings'))
    code, out, _ = route('convert', '--inventory', str(EXAMPLE_INV), '--response', str(EXAMPLE_RESP), '--out-dir', str(work / 'example_out'))
    ok = code == 0
    exc = None
    if ok:
        exc = json.loads((work / 'example_out' / 'carrier.json').read_text(encoding='utf-8'))
        (work / 'example_placeholder_carrier.json').write_text(json.dumps(placeholder_copy(exc), ensure_ascii=False), encoding='utf-8')
        c1, r1x = node_validate(wd, work / 'example_placeholder_carrier.json')
        c0, r0x = node_validate(wd, work / 'example_out' / 'carrier.json')
        ok = c1 == 0 and route_mod.validate_carrier_port(exc) is True and c0 == 1 and port_code(copy.deepcopy(exc), strict=True) == r0x.get('code')
    record('example_convert_port_and_writer004_placeholder_pass', ok)
    if exc is not None:         # R56: the enclosure row is the only member of a one-row physical_enclosure group
        exresp = json.loads(EXAMPLE_RESP.read_text(encoding='utf-8'))
        ab = [x['id'] for x in exc['items'] + exc['components'] if x['values'][0] is not None or x['values'][1] is not None]
        grp = exresp['groups']
        record('example_R56_one_row_physical_enclosure_group', len(grp) == 1 and grp[0]['relationship'] == 'physical_enclosure'
               and [x['id'] for x in exc['items'] if x['group_id'] == grp[0]['id']] == ab and len(ab) == 1
               and all(x['group_id'] is None for x in exc['items'] if x['id'] not in ab), {'ab_rows': ab})
        null_c = [x for x in exc['items'] if x['values'][2] is None]
        record('example_null_C_rows_are_research_draft', null_c and all(x['status'] == 'research_draft' and x['null_reasons'].get('C') for x in null_c),
               [x['id'] for x in null_c])
    # route v4.2 negative tests (046f review S12): the semantic reviewer's eight probes, rebuilt here as the same single
    # mutations of the current package example (the reviewer's files pin the earlier example inventory), plus O17
    exbase = json.loads(EXAMPLE_RESP.read_text(encoding='utf-8'))
    def ex_it(r, i):
        return next(x for x in r['items'] if x['id'] == i)
    def ex_set(iid, col, value, proof):
        def f(r):
            ex_it(r, iid)['values'][COLS.index(col)] = value
            ex_it(r, iid)['proofs'][col] = proof
        return f
    def ex_second_member(r):
        x = ex_it(r, 'R002')
        x['group_id'] = 'G1'
        x['values'][0], x['values'][1] = '控制盤', '600W*800H*300D'
        x['proofs']['A'] = {'refs': ['cell:S1!B4'], 'transformation': 't', 'role_basis': 'b'}
        x['proofs']['B'] = {'refs': ['cell:S1!B4'], 'transformation': 't', 'role_basis': 'b'}
    def ex_wrong_ref(iid, col, ref):
        return lambda r: ex_it(r, iid)['proofs'][col].update(refs=[ref])
    probes = [
        ('m_value_mismatch', ex_set('R002', 'M', '示例客戶甲', ex_it(exbase, 'R002')['proofs']['M']), 'R48_JOB_INPUT_VALUE_MISMATCH'),
        ('m_wrong_ref', ex_wrong_ref('R002', 'M', 'context:project_name'), 'R48_JOB_INPUT_REF'),
        ('l_wrong_ref', ex_wrong_ref('R002', 'L', 'context:customer_name'), 'R48_JOB_INPUT_REF'),
        ('m_letterhead_cell', ex_set('R002', 'M', '示例淨水場控制盤更新工程 材料清單',
                                     {'refs': ['cell:S1!A1'], 'transformation': 'copied job input', 'role_basis': 'customer full name supplied with the job (R48)'}),
         'R48_JOB_INPUT_REF'),
        ('k_from_footer', ex_set('R002', 'K', '示例供應商', {'refs': ['cell:S1!A23'], 'transformation': 't', 'role_basis': 'b'}), 'R48_FIELD_MUST_BE_NULL'),
        ('m_null', ex_set('R002', 'M', None, {'reason': 'not given'}), 'R48_JOB_INPUT_REQUIRED'),
        ('ab_second_member', ex_second_member, 'R56_GROUP_ONE_MEMBER_REQUIRED'),
        ('j_company_mismatch', ex_set('R001', 'J', '別的公司', {'refs': ['cell:S1!B4', 'context:company_name'], 'transformation': 't', 'role_basis': 'b'}),
         'R56_J_COMPANY_NAME_MISMATCH'),
        ('o17_brand_table_on_material_list', lambda r: (ex_set('R002', 'I', 'XM-10', {'refs': ['cell:S1!B5', 'context:brand_table'],
                                                                                       'transformation': 'brand-table model', 'role_basis': 'b'})(r),
                                                        ex_set('R002', 'J', '示例甲牌', {'refs': ['cell:S1!B5', 'context:brand_table'],
                                                                                       'transformation': 'brand-table brand', 'role_basis': 'b'})(r)),
         'UNKNOWN_CONTEXT_REF'),
        ('group_contractual', lambda r: r['groups'][0].update(relationship='contractual_group'), 'R56_GROUP_RELATIONSHIP'),
    ]
    for name, f, want in probes:
        pr = copy.deepcopy(exbase)
        f(pr)
        pp = work / f'probe_{name}.json'
        pp.write_text(json.dumps(pr, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        code, out, _ = route('check', '--inventory', str(EXAMPLE_INV), '--response', str(pp))
        got = {v['code'].split(':')[0]: v['category'] for v in json.loads(out)['violations']}
        record(f'v42_probe_{name}', code == 1 and got.get(want) == 'invalid', sorted(got))
    # make_job_config (B1, O17): a 材料清單 job gets no context:brand_table, a contract job does; invented inputs only
    mj = work / 'job_config'
    mj.mkdir()
    (mj / 'glossary.json').write_text(json.dumps({'schema': 'cps.company-glossary.v1', 'invented': True, 'generic_prefix_words': ['產品'],
                                                  'enclosure_word': '箱體', 'category_words': ['電磁開關'],
                                                  'abbreviations': [{'device': '電磁接觸器', 'abbreviation': 'XMC'}]}, ensure_ascii=False), encoding='utf-8')
    (mj / 'brand_table.json').write_text(json.dumps({'schema': 'cps.company-brand-table.v1', 'invented': True,
                                                     'entries': [{'device': '電磁接觸器', 'rating_band': 'all ratings', 'brand': '示例甲牌', 'model': 'XM-10'}]},
                                                    ensure_ascii=False), encoding='utf-8')
    (mj / 'invented_source.xlsx').write_bytes(b'invented workbook bytes; make_job_config pins only size and sha256')
    def job_config(tag, kind, brand_table):
        job = {'schema': 'cps.job-config.v2', 'case_id': 'JOBTEST01', 'customer_name': '示例自來水事業處', 'project_name': '示例淨水場更新',
               'company_name': '示例機電股份有限公司', 'glossary_path': str(mj / 'glossary.json'), 'source_path': str(mj / 'invented_source.xlsx'),
               'source_kind': kind, 'carrier_path': 'X:\\Jobs\\JOBTEST01\\invented_source.xlsx'}
        if brand_table:
            job['brand_table_path'] = str(mj / 'brand_table.json')
        (mj / f'job_{tag}.json').write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
        code, out, err = run([sys.executable, '-I', '-B', str(JOB_CONFIG), '--job', str(mj / f'job_{tag}.json'), '--out', str(mj / f'config_{tag}.json')])
        cfg = json.loads((mj / f'config_{tag}.json').read_text(encoding='utf-8')) if code == 0 else None
        return code, (json.loads(err) if code == 1 and err.strip() else {}), cfg
    base_refs = ['context:case_identity', 'context:customer_name', 'context:project_name', 'context:company_name', 'context:glossary']
    c_, e_, cfg = job_config('matlist', '材料清單', False)
    record('v42_make_job_config_material_list_has_no_brand_table', c_ == 0 and [f['ref'] for f in cfg['context_facts']] == base_refs
           and cfg['resource_files_sha256']['brand_table'] is None, e_)
    c_, e_, cfg = job_config('contract', 'contract', True)
    record('v42_make_job_config_contract_has_brand_table', c_ == 0 and [f['ref'] for f in cfg['context_facts']] == base_refs + ['context:brand_table'], e_)
    c_, e_, cfg = job_config('matlist_brand', '材料清單', True)
    record('v42_make_job_config_refuses_brand_table_with_material_list', c_ == 1 and e_.get('code') == 'BRAND_TABLE_NOT_USED_WITH_MATERIAL_LIST'
           and cfg is None and not (mj / 'config_matlist_brand.json').exists(), e_)
    c_, e_, cfg = job_config('contract_nobrand', 'contract', False)
    record('v42_make_job_config_contract_requires_brand_table', c_ == 1 and e_.get('code') == 'JOB_KEYS'
           and e_.get('detail', {}).get('missing') == ['brand_table_path'], e_)

    try:                        # optional: JSON-schema validation of the example (jsonschema is not stdlib)
        import jsonschema
    except ImportError:
        jsonschema = None
    schema_validation = 'skipped: jsonschema not installed'
    if jsonschema is not None:
        errs = {}
        for data, schema in ((EXAMPLE_INV, 'SOURCE_INVENTORY.schema.json'), (EXAMPLE_RESP, 'SEMANTIC_RESPONSE.schema.json')):
            sch = json.loads((PKG / 'resources' / schema).read_text(encoding='utf-8'))
            v = jsonschema.validators.validator_for(sch)(sch)
            errs[data.name] = [e.message[:200] for e in v.iter_errors(json.loads(data.read_text(encoding='utf-8')))][:5]
        record('example_files_valid_under_package_schemas', not any(errs.values()), errs)
        schema_validation = 'run'

    # 046e census roles (owner decisions O6/O7): excluded_supply and analysis_unlinked
    def roles_variant(name, mutate):
        r = json.loads(valid.read_text(encoding='utf-8'))
        mutate(r)
        path = work / f'{name}.json'
        path.write_text(json.dumps(r, ensure_ascii=False), encoding='utf-8')
        return path
    def exclude_item(r, iid='R005'):
        it = next(x for x in r['items'] if x['id'] == iid)
        cells = set(it['anchor_refs'])
        for slot in it['raw_refs'].values():
            cells.update(slot['refs'])
        r['items'] = [x for x in r['items'] if x['id'] != iid]
        for sr in r['source_roles']:
            sr['refs'] = [x for x in sr['refs'] if x not in cells]
        r['source_roles'] = [sr for sr in r['source_roles'] if sr['refs']]
        r['source_roles'].append({'role': 'excluded_supply', 'refs': sorted(cells), 'reason': 'no enclosure and no estimate: not in the quoted supply (R45)'})
    v1 = roles_variant('variant_excluded_supply', exclude_item)
    code, out, _ = route('check', '--inventory', str(inv), '--response', str(v1))
    rep = json.loads(out)
    record('e_excluded_supply_check_pass', code == 0 and rep['status'] == 'PASS', rep['violations'][:5])
    code, out, _ = route('convert', '--inventory', str(inv), '--response', str(v1), '--out-dir', str(work / 'variant_excluded_supply_out'))
    ok = code == 0
    if ok:
        cv = json.loads((work / 'variant_excluded_supply_out' / 'carrier.json').read_text(encoding='utf-8'))
        kinds = {n['kind'] for n in cv['nonitems']}
        wc, wres = node_validate(wd, work / 'variant_excluded_supply_out' / 'carrier.json')
        ok = 'excluded_supply' in kinds and all(x['id'] != 'R005' for x in cv['items']) and wc == 0
    record('e_excluded_supply_carried_as_census_and_writer_valid', ok)
    def unlink_analysis(r):
        comp_cells = set()
        for x in r['items']:
            if x['role'] == 'analysis_component':
                comp_cells.update(x['anchor_refs'])
                for slot in x['raw_refs'].values():
                    comp_cells.update(slot['refs'])
        r['items'] = [x for x in r['items'] if x['role'] != 'analysis_component']
        r['component_links'] = []
        s2 = set(comp_cells)
        for sr in r['source_roles']:
            if sr['role'] in ('analysis_content',) or any(x.startswith('cell:S2!') for x in sr['refs']):
                s2.update(x for x in sr['refs'] if x.startswith('cell:S2!'))
        for sr in r['source_roles']:
            sr['refs'] = [x for x in sr['refs'] if x not in s2]
        r['source_roles'] = [sr for sr in r['source_roles'] if sr['refs']]
        r['source_roles'].append({'role': 'analysis_unlinked', 'refs': sorted(s2), 'reason': "analysis block for an item not among this draft's demand items (R46)"})
    v2 = roles_variant('variant_analysis_unlinked', unlink_analysis)
    code, out, _ = route('check', '--inventory', str(inv), '--response', str(v2))
    rep = json.loads(out)
    record('e_analysis_unlinked_check_pass', code == 0 and rep['status'] == 'PASS', rep['violations'][:5])
    code, out, _ = route('convert', '--inventory', str(inv), '--response', str(v2), '--out-dir', str(work / 'variant_analysis_unlinked_out'))
    ok = code == 0
    if ok:
        cv = json.loads((work / 'variant_analysis_unlinked_out' / 'carrier.json').read_text(encoding='utf-8'))
        wc, _ = node_validate(wd, work / 'variant_analysis_unlinked_out' / 'carrier.json')
        lg = json.loads((work / 'variant_analysis_unlinked_out' / 'CENSUS_LEDGER.json').read_text(encoding='utf-8'))
        entries = lg['entries'] if isinstance(lg, dict) and 'entries' in lg else lg
        s2 = [e for e in entries if isinstance(e, dict) and str(e.get('ref', '')).startswith('cell:S2!') and e.get('primary_role') == 'analysis_unlinked']
        ok = (wc == 0 and cv['components'] == [] and any(n['kind'] == 'analysis_unlinked' for n in cv['nonitems'])
              and s2 and all(e.get('census') is True for e in s2))
    record('e_analysis_unlinked_convert_writer_and_ledger_census', bool(ok))
    def cite_excluded(r):
        exclude_item(r)
        excl = r['source_roles'][-1]['refs']
        r1 = next(x for x in r['items'] if x['id'] == 'R001')
        r1['proofs']['C']['refs'] = r1['proofs']['C']['refs'] + [excl[0]]
    v5 = roles_variant('variant_cite_excluded', cite_excluded)
    code, out, _ = route('check', '--inventory', str(inv), '--response', str(v5))
    record('e_census_only_cell_cited_by_item_rejected', code != 0 and 'CENSUS_ONLY_CELL_USED_BY_ITEM' in out)
    def component_group(r):
        c1 = next(x for x in r['items'] if x['role'] == 'analysis_component')
        g = r['groups'][0]
        c1['group_id'] = g['id']; c1['values'][0] = g['name']
    v6 = roles_variant('variant_component_group', component_group)
    code, out, _ = route('check', '--inventory', str(inv), '--response', str(v6))
    record('e_component_group_rejected', code != 0 and 'COMPONENT_GROUP_FORBIDDEN' in out)
    def bad_role(r):
        r['source_roles'][0]['role'] = 'excluded'
    v3 = roles_variant('variant_unknown_role', bad_role)
    code, out, _ = route('check', '--inventory', str(inv), '--response', str(v3))
    record('e_unknown_role_rejected', code != 0 and 'SOURCE_ROLE' in out)
    def demand_unused(r):
        exclude_item(r)
        r['source_roles'][-1]['role'] = 'demand_content'
    v4 = roles_variant('variant_demand_content_unused', demand_unused)
    code, out, _ = route('check', '--inventory', str(inv), '--response', str(v4))
    record('e_unused_demand_content_still_rejected', code != 0 and 'CONTENT_CELL_NOT_USED_BY_ANY_ITEM' in out)

    summary = {'route': route_mod.VERSION, 'tests': len(results), 'passed': sum(r['pass'] for r in results),
               'failed': [r for r in results if not r['pass']], 'fixtures_invented': True,
               'route_sha256': sha(ROUTE.read_bytes()), 'comparer_sha256': sha(COMPARER.read_bytes()),
               'writer_files': WRITER_SHA, 'export_attempted': False, 'example_schema_validation': schema_validation}
    (work / 'ROUTE_TEST_RESULTS.json').write_text(json.dumps({'summary': summary, 'results': results}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if not summary['failed'] else 1


if __name__ == '__main__':
    sys.exit(main())
