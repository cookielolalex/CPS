"""Component-capable source comparator (version 047), generalizing the frozen 043 comparator.

Unchanged from 043 (imported, hash-pinned): same()/norm()/count()/check_interface(), exact typed
field comparison, declared complete C/D tuple alternatives, raw literal/normalized comparison,
provenance-locator presence, nonitem census locator coverage. No fuzzy matching, recalculation,
target reading, row deletion or post-output alternatives.

Generalized:
- Pairing uses an explicit expected `anchor_cell` (e.g. "A12") on the expected sheet when present,
  else B<anchor_row> exactly as 043. A generated row pairs only if exactly one item/component
  location on that sheet contains the anchor cell.
- Expected rows may be category "component". A component pairs only with a generated
  component (role check); its link is scored separately: the generated composition parent must
  be the generated row paired with the expected parent row; basis_quantity must equal; basis_unit
  and basis_raw must be literally equal; basis_location must be on the expected basis sheet and
  contain every declared expected basis cell.
- Numeric 99% gates require detail, component (when expected components exist) and overall core
  >= 99%, and every expected link correct. Generated components with no expected counterpart are
  extras, as in 043 (row-role completeness stays in case_gate, as in 043).
- unsupported_populated_columns no longer flags C/D positions satisfied by a declared complete
  alternative (043 computed this against canonical values only; recorded limitation).
The CLI enforces the same release/freeze bindings as compare_source046.
"""
import argparse, datetime, hashlib, importlib.util, json, sys
from pathlib import Path

FROZEN = Path(__file__).with_name('compare_source043.py')
FROZEN_SHA256 = '1ececf30b034495bff049a629a15ccfa430f76a769d8f651d122be00aa069cb1'
COLS = 'ABCDEFGHIJKLMNOPQ'
RAW = ('description', 'unit', 'quantity', 'unit_price', 'amount', 'remarks')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_frozen():
    if sha(FROZEN) != FROZEN_SHA256:
        raise SystemExit('FROZEN_COMPARATOR_CHANGED')
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('compare_source043_frozen', FROZEN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


F = load_frozen()


def anchor_of(e):
    return e.get('anchor_cell') or f'B{e["anchor_row"]}'


def corresponding(expected, items):
    result, used, incidents = {}, set(), []
    for e in expected:
        key = anchor_of(e)
        hits = [(k, x) for k, x in enumerate(items) if x.get('location', {}).get('sheet') == e['sheet'] and key in x.get('location', {}).get('cells', [])]
        if len(hits) == 1 and hits[0][0] not in used:
            k, x = hits[0]
            result[e['id']] = x
            used.add(k)
        else:
            incidents.append({'expected_id': e['id'], 'sheet': e['sheet'], 'anchor': key, 'match_count': len(hits),
                              'status': 'MISSING' if not hits else 'AMBIGUOUS_OR_DUPLICATED'})
    return result, [x for k, x in enumerate(items) if k not in used], incidents


def evaluate(expected, carrier):
    rr = expected['rows']
    details, components = carrier.get('items', []), carrier.get('components', [])
    items = details + components
    if expected['denominators'].get('component_rows', 0) != sum(e['category'] == 'component' for e in rr):
        raise ValueError('COMPONENT_DENOMINATOR_MISMATCH')
    detail_ids = {id(x) for x in details}
    comp_ids = {id(x) for x in components}
    paired, extras, incidents = corresponding(rr, items)
    same = F.same
    row_results, role_defects = [], []
    for e in rr:
        a = paired.get(e['id'])
        av = a.get('values', []) if a else []
        v = e['expected_values']
        raw = a.get('raw', {}) if a else {}
        canonical = {c: len(av) == 17 and same(av[j], v[j]) for j, c in enumerate(COLS)}
        normalized = {c: len(av) == 17 and same(av[j], v[j], True) for j, c in enumerate(COLS)}
        declared, declared_norm, ma, man = dict(canonical), dict(normalized), [], []
        for k, alt in enumerate(e.get('C_D_alternatives', [])):
            if len(av) == 17 and same(av[2], alt['C']) and same(av[3], alt['D']):
                declared['C'] = declared['D'] = True
                ma.append(k)
            if len(av) == 17 and same(av[2], alt['C'], True) and same(av[3], alt['D'], True):
                declared_norm['C'] = declared_norm['D'] = True
                man.append(k)
        raw_equal = {k: a is not None and same(raw.get(k), e['raw'][k]) for k in RAW}
        raw_norm = {k: a is not None and same(raw.get(k), e['raw'][k], True) for k in RAW}
        comp = a.get('composition') if a else None
        role_ok = a is not None and ((e['category'] == 'detail' and id(a) in detail_ids and 'composition' not in a)
                                     or (e['category'] == 'component' and id(a) in comp_ids and isinstance(comp, dict)))
        if not role_ok:
            role_defects.append(e['id'])
        row_results.append({'id': e['id'], 'category': e['category'], 'generated_id': a.get('id') if a else None,
                            'correspondence': a is not None, 'role_pass': role_ok, 'canonical': canonical, 'normalized': normalized,
                            'declared_alternatives': declared, 'declared_alternatives_normalized': declared_norm,
                            'matched_complete_tuple_alternatives': ma, 'matched_complete_tuple_alternatives_normalized': man,
                            'raw_literal': raw_equal, 'raw_normalized': raw_norm,
                            'unsupported_populated_columns': [c for j, c in enumerate(COLS) if len(av) == 17 and v[j] is None and av[j] is not None and not (c in 'CD' and declared[c] and not canonical[c])],
                            'field_differences': [{'column': c, 'expected': v[j], 'actual': av[j] if len(av) == 17 else None} for j, c in enumerate(COLS) if not canonical[c]],
                            'raw_differences': [{'field': k, 'expected': e['raw'][k], 'actual': raw.get(k)} for k in RAW if not raw_equal[k]]})
    # component links
    link_results = []
    gen_by_expected = {eid: x for eid, x in paired.items()}
    for e in rr:
        if e['category'] != 'component':
            continue
        exp = e['link']
        a = paired.get(e['id'])
        comp = a.get('composition') if a else None
        parent = gen_by_expected.get(exp['parent_expected_id'])
        ok_parent = isinstance(comp, dict) and parent is not None and comp.get('parent_id') == parent.get('id')
        ok_basis = isinstance(comp, dict) and same(comp.get('basis_quantity'), exp['basis_quantity'])
        ok_unit = isinstance(comp, dict) and same(comp.get('basis_unit'), exp['basis_unit'])
        ok_raw = isinstance(comp, dict) and same(comp.get('basis_raw'), exp['basis_raw'])
        loc = comp.get('basis_location', {}) if isinstance(comp, dict) else {}
        want = exp.get('basis_cells', [])
        ok_loc = isinstance(loc, dict) and loc.get('sheet') == exp.get('basis_sheet', e['sheet']) and all(c in loc.get('cells', []) for c in want)
        link_results.append({'id': e['id'], 'parent_pass': ok_parent, 'basis_quantity_pass': ok_basis, 'basis_unit_pass': ok_unit,
                             'basis_raw_pass': ok_raw, 'basis_location_pass': ok_loc,
                             'pass': ok_parent and ok_basis and ok_unit and ok_raw and ok_loc})
    metrics = {}
    has_comp = any(e['category'] == 'component' for e in rr)
    for cat in ['detail', 'component', 'overall']:
        ee = [e for e in rr if cat == 'overall' or e['category'] == cat]
        oo = [o for o in row_results if cat == 'overall' or o['category'] == cat]
        lookup = {o['id']: o for o in oo}
        m = {'rows': len(ee), 'corresponded': sum(o['correspondence'] for o in oo), 'roles_correct': sum(o['role_pass'] for o in oo),
             'extra_rows_are_not_removed_from_case_gate': True, 'modes': {}}
        for mode in ['canonical', 'normalized', 'declared_alternatives', 'declared_alternatives_normalized']:
            total = sum(sum(lookup[e['id']][mode].values()) for e in ee)
            support = sum(sum(lookup[e['id']][mode][c] for c in e['supported_columns']) for e in ee)
            core = sum(sum(lookup[e['id']][mode][c] for c in e['core_columns']) for e in ee)
            m['modes'][mode] = {'all_positions': F.count(total, 17 * len(ee)),
                                'supported': F.count(support, sum(len(e['supported_columns']) for e in ee)),
                                'core': F.count(core, sum(len(e['core_columns']) for e in ee)),
                                'whole_rows': F.count(sum(all(lookup[e['id']][mode].values()) for e in ee), len(ee)),
                                'per_column': {c: F.count(sum(lookup[e['id']][mode][c] for e in ee if c in e['supported_columns']),
                                                          sum(c in e['supported_columns'] for e in ee)) for c in COLS}}
        m['raw_literal'] = F.count(sum(sum(o['raw_literal'].values()) for o in oo), 6 * len(ee))
        m['raw_normalized'] = F.count(sum(sum(o['raw_normalized'].values()) for o in oo), 6 * len(ee))
        m['nonnull_raw_literal'] = F.count(sum(lookup[e['id']]['raw_literal'][k] for e in ee for k in RAW if e['raw'][k] is not None),
                                           sum(e['raw'][k] is not None for e in ee for k in RAW))
        metrics[cat] = m
    links_ok = all(x['pass'] for x in link_results)
    gates = {}
    for mode in ['canonical', 'normalized', 'declared_alternatives', 'declared_alternatives_normalized']:
        cats = ['detail', 'overall'] + (['component'] if has_comp else [])
        gates[mode] = all((metrics[c]['modes'][mode]['core']['percent'] or 0) >= 99 for c in cats if metrics[c]['rows']) and links_ok
    provenance = []
    for e in rr:
        a = paired.get(e['id'])
        ev = a.get('evidence', {}) if a else {}
        for c in e['supported_columns']:
            fld = ev.get(c, {})
            ok = isinstance(fld, dict) and (bool(fld.get('selection_evidence')) if c == 'L' else bool(fld.get('location', {}).get('sheet') and fld.get('location', {}).get('cells')))
            provenance.append({'id': e['id'], 'column': c, 'structural_locator_present': ok})
    covered = {(n.get('location', {}).get('sheet'), c) for n in carrier.get('nonitems', []) for c in n.get('location', {}).get('cells', [])}
    ni = [{'sheet': x['sheet'], 'cell': x['cell'], 'located_in_nonitems': (x['sheet'], x['cell']) in covered} for x in expected.get('nonitem_cell_census', [])]
    return {'schema': 'cps.source-comparison047.v1', 'case_id': expected['case_id'], 'metrics': metrics, 'row_results': row_results,
            'correspondence_incidents': incidents, 'extra_generated_ids': [x.get('id') for x in extras], 'role_defects': role_defects,
            'component_links': {'matches': sum(x['pass'] for x in link_results), 'denominator': len(link_results), 'records': link_results},
            'supported_provenance_locators': {'present': sum(x['structural_locator_present'] for x in provenance), 'denominator': len(provenance), 'records': provenance},
            'nonitem_cell_locator_coverage': {'covered': sum(x['located_in_nonitems'] for x in ni), 'denominator': len(ni), 'records': ni,
                                              'literal_fidelity': 'MANDATORY_MANUAL_REVIEW_PENDING'},
            'numeric_99_percent_gates': gates,
            'case_gate': {'source_only_research': True, 'complete_row_roles': not incidents and not extras and not role_defects,
                          'all_parent_links': links_ok, 'semantic_obligations': 'MANDATORY_MANUAL_REVIEW_PENDING',
                          'zero_critical_errors': 'MANDATORY_MANUAL_REVIEW_PENDING', 'source_case_pass': False, 'deployment_eligible_pair_credit': 0}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--expectations', required=True); p.add_argument('--expectations-sha', required=True)
    p.add_argument('--carrier', required=True); p.add_argument('--carrier-sha', required=True)
    p.add_argument('--release', required=True); p.add_argument('--release-sha', required=True)
    p.add_argument('--run', required=True); p.add_argument('--output', required=True)
    a = p.parse_args()
    assert sha(a.expectations) == a.expectations_sha and sha(a.release) == a.release_sha
    expected = F.load(a.expectations)
    assert expected['status'] == 'FROZEN_BEFORE_MODEL_INVOCATION'
    assert expected['case_id'] == expected['carrier_contract']['case_id']
    release = F.load(a.release)
    assert release['both_outcomes_frozen'] is True and expected['case_id'] in release['case_ids'] and a.run in release['allowed_runs']
    assert release['reserved_answers_opened'] is False
    dt = datetime.datetime.fromisoformat(release['generated_access_released_utc'].replace('Z', '+00:00'))
    assert dt.utcoffset() == datetime.timedelta(0)
    frozen = Path(release['generated_output_freeze_path'])
    assert sha(frozen) == release['generated_output_freeze_sha256']
    pins = F.load(frozen)['pins']
    hits = [x for x in pins if Path(x['path']).resolve() == Path(a.carrier).resolve()]
    assert len(hits) == 1 and hits[0]['sha256'] == a.carrier_sha and sha(a.carrier) == a.carrier_sha
    carrier = F.load(a.carrier)
    F.check_interface(expected, carrier)
    result = evaluate(expected, carrier)
    result['bindings'] = {'expectations_sha256': a.expectations_sha, 'carrier_sha256': a.carrier_sha, 'release_sha256': a.release_sha,
                          'run': a.run, 'evaluator_sha256': sha(__file__), 'frozen_comparator_sha256': FROZEN_SHA256}
    with Path(a.output).open('x', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'run': a.run, 'case_id': expected['case_id'], 'core': result['metrics']['overall']['modes']['canonical']['core'],
                      'links': result['component_links']['matches'], 'gates': result['numeric_99_percent_gates']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
