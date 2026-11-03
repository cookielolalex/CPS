"""Evaluator tests for compare_source047 with invented fixtures (no project data).
1) Detail-only parity: 047 metrics equal frozen 043 metrics on the same carrier/expectations.
2) Components: pairing by explicit anchor_cell, role checks, link scoring, gates.
Usage: python3 -I -B test_compare_source047.py --carrier FIXTURE_CARRIER.json
"""
import argparse, copy, importlib.util, json, sys
from pathlib import Path
sys.dont_write_bytecode = True
EV = Path(__file__).resolve().parents[2] / 'evaluation'


def load(name):
    spec = importlib.util.spec_from_file_location(name, EV / f'{name}.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--carrier', required=True)
    a = ap.parse_args()
    c043, c047 = load('compare_source043'), load('compare_source047')
    carrier = json.loads(Path(a.carrier).read_text(encoding='utf-8'))
    byid = {r['id']: r for r in carrier['items'] + carrier['components']}
    anchors = {'R001': 4, 'R002': 6, 'R003': 7, 'R004': 8, 'R005': 11, 'R006': 12, 'R007': 18}
    rows = [{'id': 'E' + k, 'category': 'detail', 'sheet': '示例明細', 'anchor_row': r, 'expected_values': byid[k]['values'],
             'raw': byid[k]['raw'], 'supported_columns': list('CEFL'), 'core_columns': list('CEF')} for k, r in anchors.items()]
    rows[1]['expected_values'] = list(rows[1]['expected_values']); rows[1]['expected_values'][2] = '不同名稱'
    contract = {k: carrier[k] for k in ('schema', 'case_id', 'family_id', 'source')}
    exp = {'case_id': 'FIXTURE01', 'rows': rows, 'denominators': {'component_rows': 0}, 'carrier_contract': contract,
           'nonitem_cell_census': [{'sheet': '示例明細', 'cell': 'A4'}]}
    results = []
    no_comp = copy.deepcopy(carrier); no_comp['components'] = []
    r43, r47 = c043.evaluate(exp, no_comp), c047.evaluate(exp, no_comp)
    for cat in ('detail', 'overall'):
        for mode in ('canonical', 'declared_alternatives'):
            results.append(('parity_' + cat + '_' + mode, r43['metrics'][cat]['modes'][mode] == r47['metrics'][cat]['modes'][mode]))
    results.append(('parity_incidents', r43['correspondence_incidents'] == r47['correspondence_incidents']))
    results.append(('parity_census', r43['nonitem_cell_locator_coverage'] == r47['nonitem_cell_locator_coverage']))
    results.append(('parity_gates', r43['numeric_99_percent_gates'] == r47['numeric_99_percent_gates']))
    # components
    crow = lambda eid, gid, cell, parent, bq, bu: {'id': eid, 'category': 'component', 'sheet': '單價分析', 'anchor_cell': cell,
        'expected_values': byid[gid]['values'], 'raw': byid[gid]['raw'], 'supported_columns': ['C'], 'core_columns': ['C'],
        'link': {'parent_expected_id': parent, 'basis_quantity': bq, 'basis_unit': bu, 'basis_raw': str(bq), 'basis_sheet': '單價分析',
                 'basis_cells_admissible': [cell.replace('A', 'C'), cell.replace('A', 'B'), cell.replace('A', 'D')],
                 'basis_cells_required': [cell.replace('A', 'C'), cell.replace('A', 'B')]}}
    rows2 = [dict(r) for r in rows]
    rows2[1] = dict(rows2[1], expected_values=byid['R002']['values'])
    rows2 += [crow('EC1', 'C001', 'A3', 'ER003', 2, '工'), crow('EC2', 'C002', 'A4', 'ER003', 1, '式')]
    exp2 = dict(exp, rows=rows2, denominators={'component_rows': 2})
    r = c047.evaluate(exp2, carrier)
    results.append(('components_pair_by_anchor_cell', not r['correspondence_incidents'] and r['metrics']['component']['corresponded'] == 2))
    results.append(('component_links_all_pass', r['component_links']['matches'] == 2 and r['component_links']['denominator'] == 2 and not r['component_links']['extra_generated_components']))
    results.append(('gates_pass_with_components', r['numeric_99_percent_gates']['canonical'] is True))
    bad = copy.deepcopy(carrier); next(x for x in bad['components'] if x['id'] == 'C001')['composition']['parent_id'] = 'R002'
    rb = c047.evaluate(exp2, bad)
    results.append(('wrong_parent_fails_link_and_gate', rb['component_links']['matches'] == 1 and rb['numeric_99_percent_gates']['canonical'] is False))
    bad2 = copy.deepcopy(carrier); next(x for x in bad2['components'] if x['id'] == 'C002')['composition']['basis_unit'] = '組'
    results.append(('wrong_basis_unit_fails_link', c047.evaluate(exp2, bad2)['component_links']['matches'] == 1))
    bad3 = copy.deepcopy(carrier); next(x for x in bad3['components'] if x['id'] == 'C001')['composition']['basis_location']['cells'] = ['C3', 'B3', 'C4']
    results.append(('wrong_basis_location_fails_link', c047.evaluate(exp2, bad3)['component_links']['matches'] == 1))
    bad4 = copy.deepcopy(carrier); next(x for x in bad4['components'] if x['id'] == 'C001')['composition']['basis_raw'] = '2.0'
    results.append(('wrong_basis_raw_fails_link', c047.evaluate(exp2, bad4)['component_links']['matches'] == 1))
    moved = copy.deepcopy(carrier); comp = moved['components'].pop(0); comp.pop('composition'); moved['items'].append(comp)
    rm = c047.evaluate(exp2, moved)
    results.append(('component_as_detail_is_role_defect', 'EC1' in rm['role_defects']))
    try:
        c047.evaluate(dict(exp2, denominators={'component_rows': 0}), carrier); results.append(('denominator_mismatch_raises', False))
    except ValueError:
        results.append(('denominator_mismatch_raises', True))
    held = copy.deepcopy(carrier); next(x for x in held['components'] if x['id'] == 'C001').update(status='held', review_reasons=['held'])
    results.append(('held_component_link_fails', c047.evaluate(exp2, held)['component_links']['matches'] == 1))
    extra = copy.deepcopy(carrier); ex = copy.deepcopy(extra['components'][0]); ex['id'] = 'C999'; ex['location'] = dict(ex['location'], cells=['A1']); extra['components'].append(ex)
    re_ = c047.evaluate(exp2, extra)
    results.append(('extra_component_fails_links_and_gate', re_['case_gate']['all_parent_links'] is False and re_['numeric_99_percent_gates']['canonical'] is False))
    rd = c047.evaluate(exp, carrier)
    results.append(('detail_only_expectations_with_components_fail_gate', rd['numeric_99_percent_gates']['canonical'] is False))
    for name, mut in (('empty_rows_raise', lambda e: e.update(rows=[])), ('category_typo_raises', lambda e: e['rows'][0].update(category='Detail')),
                      ('duplicate_ids_raise', lambda e: e['rows'][1].update(id=e['rows'][0]['id'])),
                      ('link_missing_required_cells_raises', lambda e: e['rows'][-1]['link'].pop('basis_cells_required'))):
        ee = copy.deepcopy(exp2); mut(ee)
        try:
            c047.evaluate(ee, carrier); results.append((name, False))
        except ValueError:
            results.append((name, True))
    pv = copy.deepcopy(no_comp); pv['items'][0]['evidence']['C']['location']['sheet'] = '他表'
    results.append(('provenance_requires_expected_sheet', c047.evaluate(exp, pv)['supported_provenance_locators']['present'] == c043.evaluate(exp, pv)['supported_provenance_locators']['present']))
    try:
        c043.evaluate(exp2, carrier); results.append(('frozen_043_refuses_components', False))
    except ValueError:
        results.append(('frozen_043_refuses_components', True))
    out = {'tests': len(results), 'passed': sum(ok for _, ok in results), 'failed': [n for n, ok in results if not ok]}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not out['failed'] else 1


if __name__ == '__main__':
    sys.exit(main())
