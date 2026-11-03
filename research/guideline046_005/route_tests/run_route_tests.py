"""Actual-route tests for candidate 046b with invented fixtures only.

Route: response -> tools/cps046b_route.py (check/convert) -> archived writer004
validate_carrier_v4.mjs (byte-identical original, @oai/artifact-tool import stubbed)
-> frozen compare_source043.evaluate pairing interface (invented expectations).
Usage: python3 -I run_route_tests.py --writer-dir DIR --work NEWDIR
"""
import argparse, copy, hashlib, importlib.util, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent / 'package'
ROUTE = PKG / 'tools' / 'cps046b_route.py'
COMPARER = HERE.parents[1] / 'evaluation' / 'compare_source043.py'
WRITER_SHA = {'writer004.mjs': '85a7f619b9cfedc0c3c851b34c1d8cee38cfe5ab88ed050fcf4bba566c18c0d7',
              'validate_carrier_v4.mjs': '984da083219fa3df69dfd34652115fe1ddd5cd0ed723321981916adc5a87e013',
              'receipt_bytes.mjs': 'b2ff15fd5d44a8adfbd5370f8bf8d81c432b89f5a6ea4f81d71477e283d11d2c'}
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
        record(f'writer_bytes_{f}', sha((wd / f).read_bytes()) == h)
    fx = work / 'fixtures'
    code, out, err = run([sys.executable, '-I', str(HERE / 'make_fixtures.py'), str(fx)])
    record('make_fixtures', code == 0, err[-300:] if code else None)
    inv, valid = fx / 'fixture_inventory.json', fx / 'valid_response.json'

    # positive route
    code, out, _ = route('check', '--inventory', str(inv), '--response', str(valid))
    rep = json.loads(out)
    record('valid_check_pass', code == 0 and rep['status'] == 'PASS', rep['violations'][:5])
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
                    'unknown_ref': 'invalid', 'dropped_item': 'invalid'}.get(mu['name'])
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
    fp = work / 'parity_carriers.json'
    fp.write_text(json.dumps([c for _, c in fuzz], ensure_ascii=False), encoding='utf-8')
    pcode, pout, perr = run(['node', str(HERE / 'parity_batch.mjs'), str((wd / 'writer004.mjs').resolve()), str(fp.resolve())])
    node_codes = json.loads(pout) if pcode == 0 else []
    mism = []
    for (label, c), nc in zip(fuzz, node_codes):
        try:
            route_mod.validate_carrier_port(c)
            pc = 'PASS'
        except route_mod.WriterReject as e:
            pc = e.code
        if pc != nc:
            mism.append({'case': label, 'python': pc, 'node': nc})
    record('writer_port_parity_fuzz', pcode == 0 and len(node_codes) == len(fuzz) and not mism,
           {'cases': len(fuzz), 'node_pass': sum(x == 'PASS' for x in node_codes), 'mismatches': mism[:10], 'stderr': perr[-300:]})
    record('valid_carrier_port_pass', route_mod.validate_carrier_port(carrier) is True)

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

    summary = {'route': 'cps046e-route.v3', 'tests': len(results), 'passed': sum(r['pass'] for r in results),
               'failed': [r for r in results if not r['pass']], 'fixtures_invented': True,
               'route_sha256': sha(ROUTE.read_bytes()), 'comparer_sha256': sha(COMPARER.read_bytes()),
               'writer_files': WRITER_SHA, 'export_attempted': False}
    (work / 'ROUTE_TEST_RESULTS.json').write_text(json.dumps({'summary': summary, 'results': results}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if not summary['failed'] else 1


if __name__ == '__main__':
    sys.exit(main())
