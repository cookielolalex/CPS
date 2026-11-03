"""Component-capable source comparator (version 047), generalizing the frozen 043 comparator.

Reused unchanged from 043 (imported, hash-pinned): same()/norm()/count()/check_interface()/load(),
exact typed field comparison, declared complete C/D tuple alternatives, raw literal/normalized
comparison and the nonitem census locator check. No fuzzy matching, recalculation, target reading,
row deletion or post-output alternatives.

Deviations from 043 (all deliberate, listed here and tested in test_compare_source047.py):
 D1 Pairing uses an explicit expected `anchor_cell` on the expected sheet when present, else
    B<anchor_row> exactly as 043. Expected detail rows pair only within generated items and
    expected component rows only within generated components (category pools).
 D2 Component rows and links: a link passes only if the generated composition resolves its
    parent_id to exactly one generated detail that is the very row paired with the expected parent,
    basis_quantity equals, basis_unit and basis_raw are literally equal, the basis location is on
    the expected basis sheet, is non-empty, lies within `basis_cells_admissible` and contains every
    `basis_cells_required` cell, and the component is not held. Generated components that pair with
    no expected component make all_parent_links false.
 D3 Numeric gates: categories must be exactly detail/component; overall and every included stratum
    need a positive core denominator; detail, component (when expected) and overall core >= 99% in
    the mode, and all_parent_links. As in 043, a carrier with components against detail-only
    expectations fails the gates.
 D4 unsupported_populated_columns and provenance requirements honour a matched declared complete
    alternative (043 computed both against canonical values only).
 D5 Expectation and link schemas are validated strictly; violations raise before scoring
    (unique ids and columns, core_columns ⊆ supported_columns, A1 anchor cells, link fields).
 D6 Generated location `cells` must be a list (a string is never substring-matched).
Recorded limitations (not gates): (L1) when a matched alternative fills a C/D column that the
canonical row leaves unsupported, no provenance locator is demanded for it (writer004 already
requires evidence for every filled value); (L2) the carrier is not re-validated against the
writer004 schema here (the CPS route validates every carrier with writer004 before release);
(L3) the raw representation profile is not re-derived here (expectations bind the inventory and
profile); (L4) distinctness of census cells and component cells is not enforced.
The CLI enforces the same release/freeze bindings as compare_source046 with explicit raises.
"""
import argparse, datetime, hashlib, importlib.util, json, re, sys
from pathlib import Path

FROZEN = Path(__file__).with_name('compare_source043.py')
FROZEN_SHA256 = '1ececf30b034495bff049a629a15ccfa430f76a769d8f651d122be00aa069cb1'
COLS = 'ABCDEFGHIJKLMNOPQ'
RAW = ('description', 'unit', 'quantity', 'unit_price', 'amount', 'remarks')
MODES = ('canonical', 'normalized', 'declared_alternatives', 'declared_alternatives_normalized')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def need(ok, code):
    if not ok:
        raise ValueError(code)


def load_frozen():
    if sha(FROZEN) != FROZEN_SHA256:
        raise SystemExit('FROZEN_COMPARATOR_CHANGED')
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('compare_source043_frozen', FROZEN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


F = load_frozen()


def validate_expectations(expected):
    rr = expected.get('rows')
    need(isinstance(rr, list) and rr, 'EXPECTED_ROWS_REQUIRED')
    ids = [e.get('id') for e in rr]
    need(len(set(ids)) == len(ids) and all(isinstance(i, str) and i for i in ids), 'EXPECTED_IDS_UNIQUE')
    byid = {e['id']: e for e in rr}
    for e in rr:
        need(e.get('category') in ('detail', 'component'), 'EXPECTED_CATEGORY')
        need(isinstance(e.get('sheet'), str) and e['sheet'], 'EXPECTED_SHEET')
        ac = e.get('anchor_cell')
        need(ac is None or (isinstance(ac, str) and re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]*', ac) is not None), 'EXPECTED_ANCHOR_CELL')
        need(ac is not None or isinstance(e.get('anchor_row'), int), 'EXPECTED_ANCHOR')
        need(isinstance(e.get('expected_values'), list) and len(e['expected_values']) == 17, 'EXPECTED_VALUES_17')
        need(isinstance(e.get('raw'), dict) and set(e['raw']) == set(RAW), 'EXPECTED_RAW_KEYS')
        need(isinstance(e.get('core_columns'), list) and e['core_columns'] and set(e['core_columns']) <= set(COLS)
             and len(set(e['core_columns'])) == len(e['core_columns']), 'EXPECTED_CORE_COLUMNS')
        need(isinstance(e.get('supported_columns'), list) and set(e['supported_columns']) <= set(COLS)
             and len(set(e['supported_columns'])) == len(e['supported_columns']), 'EXPECTED_SUPPORTED_COLUMNS')
        need(set(e['core_columns']) <= set(e['supported_columns']), 'CORE_NOT_SUBSET_OF_SUPPORTED')
        if e['category'] == 'component':
            lk = e.get('link')
            need(isinstance(lk, dict), 'EXPECTED_LINK')
            need(lk.get('parent_expected_id') in byid and byid[lk['parent_expected_id']]['category'] == 'detail', 'EXPECTED_LINK_PARENT')
            bq = lk.get('basis_quantity')
            need(isinstance(bq, (int, float)) and not isinstance(bq, bool) and bq > 0, 'EXPECTED_LINK_BASIS_QUANTITY')
            need(isinstance(lk.get('basis_unit'), str) and lk['basis_unit'], 'EXPECTED_LINK_BASIS_UNIT')
            need(isinstance(lk.get('basis_raw'), str) and lk['basis_raw'], 'EXPECTED_LINK_BASIS_RAW')
            need(isinstance(lk.get('basis_sheet'), str) and lk['basis_sheet'], 'EXPECTED_LINK_BASIS_SHEET')
            adm, req = lk.get('basis_cells_admissible'), lk.get('basis_cells_required')
            need(isinstance(adm, list) and adm and isinstance(req, list) and req and set(req) <= set(adm), 'EXPECTED_LINK_BASIS_CELLS')
    need(expected.get('denominators', {}).get('component_rows') == sum(e['category'] == 'component' for e in rr), 'COMPONENT_DENOMINATOR_MISMATCH')


def anchor_of(e):
    return e.get('anchor_cell') or f'B{e["anchor_row"]}'


def corresponding(expected, pools):
    result, used, incidents = {}, set(), []
    for e in expected:
        key = anchor_of(e)
        hits = [(k, x) for k, x in pools[e['category']]
                if x.get('location', {}).get('sheet') == e['sheet'] and isinstance(x.get('location', {}).get('cells'), list)
                and key in x['location']['cells']]
        if len(hits) == 1 and hits[0][0] not in used:
            k, x = hits[0]
            result[e['id']] = x
            used.add(k)
        else:
            incidents.append({'expected_id': e['id'], 'sheet': e['sheet'], 'anchor': key, 'match_count': len(hits),
                              'status': 'MISSING' if not hits else 'AMBIGUOUS_OR_DUPLICATED'})
    return result, used, incidents


def evaluate(expected, carrier):
    validate_expectations(expected)
    rr = expected['rows']
    details, components = carrier.get('items', []), carrier.get('components', [])
    allrows = list(enumerate(details + components))
    pools = {'detail': allrows[:len(details)], 'component': allrows[len(details):]}
    detail_ids = {id(x) for x in details}
    comp_ids = {id(x) for x in components}
    paired, used, incidents = corresponding(rr, pools)
    extras = [x for k, x in allrows if k not in used]
    same = F.same
    row_results, role_defects, matched_alt = [], [], {}
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
        matched_alt[e['id']] = [e['C_D_alternatives'][k] for k in ma] if not (canonical['C'] and canonical['D']) else []
        raw_equal = {k: a is not None and same(raw.get(k), e['raw'][k]) for k in RAW}
        raw_norm = {k: a is not None and same(raw.get(k), e['raw'][k], True) for k in RAW}
        comp = a.get('composition') if a else None
        role_ok = a is not None and ((e['category'] == 'detail' and id(a) in detail_ids and 'composition' not in a)
                                     or (e['category'] == 'component' and id(a) in comp_ids and isinstance(comp, dict)))
        if not role_ok:
            role_defects.append(e['id'])
        alts = matched_alt[e['id']]
        unsupported = [c for j, c in enumerate(COLS) if len(av) == 17 and v[j] is None and av[j] is not None
                       and not (c in 'CD' and alts and any(same(av[j], x[c]) for x in alts))]
        row_results.append({'id': e['id'], 'category': e['category'], 'generated_id': a.get('id') if a else None,
                            'correspondence': a is not None, 'role_pass': role_ok, 'canonical': canonical, 'normalized': normalized,
                            'declared_alternatives': declared, 'declared_alternatives_normalized': declared_norm,
                            'matched_complete_tuple_alternatives': ma, 'matched_complete_tuple_alternatives_normalized': man,
                            'raw_literal': raw_equal, 'raw_normalized': raw_norm, 'unsupported_populated_columns': unsupported,
                            'field_differences': [{'column': c, 'expected': v[j], 'actual': av[j] if len(av) == 17 else None} for j, c in enumerate(COLS) if not canonical[c]],
                            'raw_differences': [{'field': k, 'expected': e['raw'][k], 'actual': raw.get(k)} for k in RAW if not raw_equal[k]]})
    link_results = []
    for e in rr:
        if e['category'] != 'component':
            continue
        lk = e['link']
        a = paired.get(e['id'])
        comp = a.get('composition') if a else None
        parent_expected = paired.get(lk['parent_expected_id'])
        pid = comp.get('parent_id') if isinstance(comp, dict) else None
        cands = [x for x in details if isinstance(pid, str) and pid and isinstance(x.get('id'), str) and x.get('id') == pid]
        ok_parent = len(cands) == 1 and parent_expected is not None and cands[0] is parent_expected
        ok_basis = isinstance(comp, dict) and 'basis_quantity' in comp and same(comp.get('basis_quantity'), lk['basis_quantity'])
        ok_unit = isinstance(comp, dict) and 'basis_unit' in comp and same(comp.get('basis_unit'), lk['basis_unit'])
        ok_raw = isinstance(comp, dict) and 'basis_raw' in comp and same(comp.get('basis_raw'), lk['basis_raw'])
        loc = comp.get('basis_location') if isinstance(comp, dict) else None
        cells = loc.get('cells') if isinstance(loc, dict) else None
        ok_loc = (isinstance(cells, list) and bool(cells) and loc.get('sheet') == lk['basis_sheet']
                  and set(cells) <= set(lk['basis_cells_admissible']) and set(lk['basis_cells_required']) <= set(cells))
        ok_status = a is not None and a.get('status') == 'research_draft'
        link_results.append({'id': e['id'], 'parent_pass': ok_parent, 'basis_quantity_pass': ok_basis, 'basis_unit_pass': ok_unit,
                             'basis_raw_pass': ok_raw, 'basis_location_pass': ok_loc, 'not_held': ok_status,
                             'pass': ok_parent and ok_basis and ok_unit and ok_raw and ok_loc and ok_status})
    extra_components = [x.get('id') for x in extras if id(x) in comp_ids]
    has_comp = any(e['category'] == 'component' for e in rr)
    links_ok = all(x['pass'] for x in link_results) and not extra_components
    metrics = {}
    for cat in ['detail', 'component', 'overall']:
        ee = [e for e in rr if cat == 'overall' or e['category'] == cat]
        oo = [o for o in row_results if cat == 'overall' or o['category'] == cat]
        lookup = {o['id']: o for o in oo}
        m = {'rows': len(ee), 'corresponded': sum(o['correspondence'] for o in oo), 'roles_correct': sum(o['role_pass'] for o in oo),
             'extra_rows_are_not_removed_from_case_gate': True, 'modes': {}}
        for mode in MODES:
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
    gates = {}
    for mode in MODES:
        strata = ['overall'] + [c for c in ('detail', 'component') if metrics[c]['rows']]
        ok = all(metrics[c]['modes'][mode]['core']['denominator'] > 0 and metrics[c]['modes'][mode]['core']['percent'] >= 99 for c in strata)
        gates[mode] = ok and links_ok and not (components and not has_comp)
    provenance = []
    sheets = {x['sheet'] for x in rr}
    for e in rr:
        a = paired.get(e['id'])
        ev = a.get('evidence', {}) if a else {}
        alts = matched_alt[e['id']]
        for c in e['supported_columns']:
            if c in 'CD' and alts and all(x[c] is None for x in alts):
                continue
            fld = ev.get(c, {})
            ok = isinstance(fld, dict) and (bool(fld.get('selection_evidence')) if c == 'L' else bool(fld.get('location', {}).get('sheet') in sheets and fld.get('location', {}).get('cells')))
            provenance.append({'id': e['id'], 'column': c, 'structural_locator_present': ok})
    covered = {(n.get('location', {}).get('sheet'), c) for n in carrier.get('nonitems', []) for c in n.get('location', {}).get('cells', [])}
    ni = [{'sheet': x['sheet'], 'cell': x['cell'], 'located_in_nonitems': (x['sheet'], x['cell']) in covered} for x in expected.get('nonitem_cell_census', [])]
    return {'schema': 'cps.source-comparison047.v2', 'case_id': expected['case_id'], 'metrics': metrics, 'row_results': row_results,
            'correspondence_incidents': incidents, 'extra_generated_ids': [x.get('id') for x in extras], 'role_defects': role_defects,
            'component_links': {'matches': sum(x['pass'] for x in link_results), 'denominator': len(link_results), 'records': link_results,
                                'extra_generated_components': extra_components,
                                'status': 'SCORED' if has_comp else 'NOT_APPLICABLE_NO_SOURCE_COMPONENTS_NO_PERCENT_CREDIT'},
            'supported_provenance_locators': {'present': sum(x['structural_locator_present'] for x in provenance), 'denominator': len(provenance),
                                              'records': provenance, 'semantic_correctness': 'MANDATORY_MANUAL_REVIEW_PENDING'},
            'nonitem_cell_locator_coverage': {'covered': sum(x['located_in_nonitems'] for x in ni), 'denominator': len(ni), 'records': ni,
                                              'literal_fidelity': 'MANDATORY_MANUAL_REVIEW_PENDING'},
            'numeric_99_percent_gates': gates,
            'case_gate': {'source_only_research': True, 'complete_row_roles': not incidents and not extras and not role_defects,
                          'all_parent_links': links_ok, 'semantic_obligations': 'MANDATORY_MANUAL_REVIEW_PENDING',
                          'zero_critical_errors': 'MANDATORY_MANUAL_REVIEW_PENDING', 'full_semantic_provenance': 'MANDATORY_MANUAL_REVIEW_PENDING',
                          'source_case_pass': False, 'deployment_eligible_pair_credit': 0,
                          'reason': 'Numeric scores alone cannot satisfy complete semantic/nonitem/provenance/critical-error gates; target eligibility remains unverified.'}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--expectations', required=True); p.add_argument('--expectations-sha', required=True)
    p.add_argument('--carrier', required=True); p.add_argument('--carrier-sha', required=True)
    p.add_argument('--release', required=True); p.add_argument('--release-sha', required=True)
    p.add_argument('--run', required=True); p.add_argument('--output', required=True)
    a = p.parse_args()
    need(sha(a.expectations) == a.expectations_sha, 'EXPECTATIONS_SHA_MISMATCH')
    need(sha(a.release) == a.release_sha, 'RELEASE_SHA_MISMATCH')
    expected = F.load(a.expectations)
    need(expected.get('status') == 'FROZEN_BEFORE_MODEL_INVOCATION', 'EXPECTATIONS_NOT_FROZEN')
    need(expected['case_id'] == expected['carrier_contract']['case_id'], 'CASE_CONTRACT_MISMATCH')
    release = F.load(a.release)
    need(release.get('both_outcomes_frozen') is True and expected['case_id'] in release.get('case_ids', []) and a.run in release.get('allowed_runs', []), 'RELEASE_SCOPE')
    need(release.get('reserved_answers_opened') is False, 'RESERVED_ANSWERS_OPENED')
    dt = datetime.datetime.fromisoformat(release['generated_access_released_utc'].replace('Z', '+00:00'))
    need(dt.utcoffset() == datetime.timedelta(0), 'RELEASE_TIME_NOT_UTC')
    frozen = Path(release['generated_output_freeze_path'])
    need(sha(frozen) == release['generated_output_freeze_sha256'], 'FREEZE_SHA_MISMATCH')
    pins = F.load(frozen)['pins']
    hits = [x for x in pins if Path(x['path']).resolve() == Path(a.carrier).resolve()]
    need(len(hits) == 1 and hits[0]['sha256'] == a.carrier_sha and sha(a.carrier) == a.carrier_sha, 'CARRIER_NOT_FROZEN_MEMBER')
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
