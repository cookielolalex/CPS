"""Scope-stage tests for candidates 046g and 046i (FIELD_ROLES R59) with invented fixtures only.

Builds an invented FULL 材料清單 inventory (summary, bill, analysis and resource-statistics sheets; more than 2,500
content cells; the bill sheet is the one of make_fixtures.SCOPED_BILL), runs the four harness tools on it
(scope_tool.py, scope_agree.py with invented reader responses, make_scoped_inventory.py build and --verify) and checks:
BILL1 and the R51 conditions, holds, the threshold, determinism, agreement and disagreement, the projection's
byte-identity, verify on tampered outputs, view images, and that route v4.3 accepts the scoped packet together with the
valid scoped response of make_fixtures (end to end), the agreement value of an admissible and of a stand-in decision
(046g round 1, review item S13), and that the route rejects a packet built from a stand-in decision.
046i (owner decision O72, FIELD_ROLES R59 items 2 and 9): the 046g fixture whose bill lost its 合計 cell held the case
(tool_holds_zero_bill1_candidates); it is O72's first pattern, so that check is re-specified by design as
tool_no_total_scopes_to_last_content_row (BILL1.NOTOTAL.v1). The zero-candidate hold stays covered by a workbook whose only
header-like row carries five of the six labels (tool_holds_zero_bill1_candidates_five_of_six). New o72_* checks: the
no-total pipeline (digest additions, agreement and disagreements, build, verify, route), the whole-workbook pipeline
(BILL1.NOHEADER.v1: every sheet in scope, the scoped inventory equals the full one plus the fact), its agreement cases,
a stand-in decision on either rule and a hand-edited proposal with an unknown bill rule (PROPOSAL_BILL_RULE). The 046i
review fix round adds the priced-tail pattern without an analysis sheet (finding F2): no deterministic hold applies, and a
reader following the template (end_row null) holds the case. No project data is read.
Usage: python3 -I run_scope_stage_tests.py --work NEWDIR
"""
import argparse, copy, hashlib, importlib.util, json, subprocess, sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
H = HERE.parent / 'harness'
ROUTE = HERE.parent / 'package' / 'tools' / 'cps046b_route.py'
TOOL, AGREE, SCOPED = H / 'scope_tool.py', H / 'scope_agree.py', H / 'make_scoped_inventory.py'
results = []


def record(name, ok, detail=None):
    results.append({'test': name, 'pass': bool(ok), **({'detail': detail} if detail is not None else {})})


def sha(b):
    return hashlib.sha256(b).hexdigest()


def run(*args):
    p = subprocess.run([sys.executable, '-I', '-B', *map(str, args)], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def jout(text):
    try:
        return json.loads(text)
    except ValueError:
        return {}


def load_fixtures():
    argv = sys.argv
    sys.argv = [argv[0], '/nonexistent-not-used']
    try:
        spec = importlib.util.spec_from_file_location('cps046g_make_fixtures', HERE / 'make_fixtures.py')
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        sys.argv = argv
    return m


F = load_fixtures()
T, N = F.T, F.N
SUMMARY = {(1, 'A'): (T, '示例工程 總表', False),
           **{(2, c): (T, v, False) for c, v in zip('ABCD', ['項次', '工作項目', '金額(元)', '備註'])},
           (3, 'A'): (T, '壹', False), (3, 'B'): (T, '示例控制盤更新', False), (3, 'C'): (N, 5000.0, True),
           (4, 'B'): (T, '總價', False), (4, 'C'): (N, 5000.0, True)}
RESOURCE_HEAD = ['工項代碼', '工項名稱', '單位', '工程用量', '單價', '複價', '人工', '機具', '材料', '雜項']


def analysis_sheet(blocks, first_name='產品，電磁接觸器，AC220V', priced_component=False):
    data = {(1, 'A'): (T, '示例單價分析表', False)}
    r = 2
    for k in range(1, blocks + 1):
        name = first_name if k == 1 else f'示例分析項目{k:03d}'
        data[(r, 'A')] = (T, str(k), False)
        data[(r, 'B')] = (T, f'工作項目：{name}', False)
        data[(r, 'E')] = (T, f'計價代碼：Q{k:09d}', False)
        for c, v in zip('BCDEFG', ['工料名稱', '單位', '數量', '單價', '複價', '編碼(備註)']):
            data[(r + 1, c)] = (T, v, False)
        for j in range(3):
            data[(r + 2 + j, 'B')] = (T, f'示例材料{k:03d}-{j}', False)
            data[(r + 2 + j, 'C')] = (T, '式', False)
            data[(r + 2 + j, 'D')] = (N, 1.0, False)
        if priced_component and k == 2:
            data[(r + 2, 'E')] = (N, 120.0, False)
        data[(r + 5, 'B')] = (T, '合計', False)
        data[(r + 5, 'F')] = (N, 0.0, True)
        r += 6
    return data, r - 1


def resource_sheet(rows):
    data = {(1, 'A'): (T, '示例資源統計表', False), **{(2, F.letters(i + 1)): (T, v, False) for i, v in enumerate(RESOURCE_HEAD)}}
    for r in range(3, rows + 1):
        for i in range(10):
            data[(r, F.letters(i + 1))] = (T, f'統計{r}-{i}', False) if i < 3 else (N, float(r + i), False)
    return data


def views_for(name, rows, cols, start_id, step=30):
    out, vid = [], start_id
    for r0 in range(1, rows + 1, step):
        out.append({'id': vid, 'sheet': name, 'range': f'A{r0}:{F.letters(cols)}{min(rows, r0 + step - 1)}'})
        vid += 1
    return out


def build_full(blocks=130, bill=None, extra_bill_copy=False, hidden_resource=False, analysis_kw=None, images=None, analysis=True, resource_rows=40):
    """Invented full inventory, every sheet in scope; returns (dict, bytes). analysis=False leaves out the analysis sheet
    (the resource sheet is then sheet 3; give resource_rows enough rows to stay above the threshold)."""
    bill = bill or F.SCOPED_BILL
    adata, arows = analysis_sheet(blocks, **(analysis_kw or {}))
    specs = [('示例總表', SUMMARY, 12, 4, []), (F.SB, bill, 10, 7, F.SCOPED_BILL_MERGES), ('示例單價分析', adata, arows, 7, []),
             ('示例資源統計', resource_sheet(resource_rows), resource_rows, 10, [])]
    if not analysis:
        specs.pop(2)
    if extra_bill_copy:
        specs.append(('示例材料清單二', bill, 10, 7, F.SCOPED_BILL_MERGES))
    vws, cells, sheets = [], [], []
    for si, (name, data, rows, cols, merges) in enumerate(specs, start=1):
        vws += views_for(name, rows, cols, len(vws) + 1)
    for si, (name, data, rows, cols, merges) in enumerate(specs, start=1):
        cells += F.sheet_cells(si, name, data, rows, cols, merges, vws)
        sheets.append({'index': si, 'name': name, 'visibility': 'hidden' if (hidden_resource and si == 4) else 'visible', 'rows': rows,
                       'columns': cols, 'merges': merges, 'formula_records': sum(1 for v in data.values() if v[2]), 'in_scope': True})
    fake = sha(b'invented full fixture workbook bytes')
    img = images or {}
    inv = {'schema': 'cps.source-inventory.cells.v2', 'case_id': F.SCOPED_CASE, 'family_id': F.SCOPED_CASE,
           'representation_profile': 'cached-cell-raw-scalar-text.v2',
           'source': {'source_id': 'S', 'format': 'cached_xlsx', 'bytes': 4096, 'sha256': fake, 'adoption_status': 'unverified',
                      'adoption_basis': 'Invented full fixture; no real material list.',
                      'reader': {'name': 'invented', 'version': '0', 'biff_format': None, 'formula_expressions_available': False},
                      'carrier_source': {'kind': 'cached_xlsx', 'path': 'X:\\Fixtures\\invented\\fixture-material-list.xlsx', 'sha256': fake, 'views': vws}},
           'sheets': sheets,
           'views': [dict(v, image=img.get(v['id'], {'file': f"view_{v['id']:02d}.png", 'bytes': 1, 'sha256': fake})) for v in vws],
           'external_links': [], 'cells': cells, 'context_facts': F.scoped_job_facts(F.SCOPED_CASE),
           'limitations': ['Invented full fixture inventory for the scope-stage tests (FIELD_ROLES R59).']}
    return inv, F.serialize(inv).encode('utf-8')


def reader_for(proposal_path, digest_path, kind='fresh_context_scope_reader', **over):
    p = json.loads(Path(proposal_path).read_text(encoding='utf-8'))
    r = {'schema': 'cps.scope-reader-response.v1', 'case_id': p['case_id'], 'digest_sha256': sha(Path(digest_path).read_bytes()),
         'reader': {'kind': kind, 'model': 'invented-test-reader', 'effort': 'n/a'},
         'bill_sheet_index': p['bill']['sheet_index'], 'end_row': p['bill']['end_row'],
         'sheets': [{'index': s['index'], 'role': s['role'], 'in_scope': s['in_scope'], 'reason': 'invented test reason'} for s in p['sheets']],
         'doubts': []}
    for k, v in over.items():
        if k == 'sheet_flag':
            r['sheets'][v[0]]['in_scope'] = v[1]
        else:
            r[k] = v
    return r


def pipeline(work, tag, raw, reader_over=None, kind='fresh_context_scope_reader', expect_tool=0):
    d = work / tag
    d.mkdir()
    full = d / 'full' / 'SOURCE_INVENTORY.json'
    full.parent.mkdir()
    full.write_bytes(raw)
    code, out, err = run(TOOL, '--inventory', full, '--out-dir', d / 'tool')
    res = {'dir': d, 'full': full, 'tool_code': code, 'tool_out': jout(out), 'tool_err': err}
    if code != 0 or expect_tool != 0:
        return res
    prop, dig = d / 'tool' / 'SCOPE_PROPOSAL.json', d / 'tool' / 'SCOPE_DIGEST.json'
    res['proposal'] = json.loads(prop.read_text(encoding='utf-8'))
    if res['proposal']['status'] != 'PROPOSED':
        return res
    rd = d / 'reader.json'
    rd.write_text(json.dumps(reader_for(prop, dig, kind, **(reader_over or {})), ensure_ascii=False), encoding='utf-8')
    code, out, err = run(AGREE, '--proposal', prop, '--digest', dig, '--reader', rd, '--out-dir', d / 'decision')
    res.update(agree_code=code, agree_out=jout(out), agree_err=err)
    if code != 0:
        return res
    dec = d / 'decision' / 'SCOPE_DECISION.json'
    code, out, err = run(SCOPED, '--full', full, '--decision', dec, '--out-dir', d / 'packet')
    res.update(build_code=code, build_out=jout(out), build_err=err, decision=dec, scoped=d / 'packet' / 'SOURCE_INVENTORY.json')
    return res


def o72_tests(work, h, nb, main_prop, main_dig):
    """046i (owner decision O72, FIELD_ROLES R59 items 2 and 9): inventory-level checks of the two new bill rules."""
    hp = h.get('proposal', {})
    dg = json.loads((h['dir'] / 'tool' / 'SCOPE_DIGEST.json').read_text(encoding='utf-8'))
    s2 = next(s for s in dg['sheets'] if s['index'] == 2)
    record('o72_nototal_digest_line_counts_and_tail', s2['counts'].get('lines_from_first_item_below_header_to_last_content_row') ==
           {'lines': 5, 'priced': 3, 'not_estimated': 1, 'other_price_text': 0, 'unpriced_no_status': 1}
           and s2['counts'].get('priced_or_not_estimated_line_rows') == [3, 4, 6, 10] and s2['counts'].get('last_unpriced_no_status_line_row') == 5
           and [x['row'] for x in s2.get('priced_or_not_estimated_lines_tail', [])] == [4, 6, 10]
           and [r['row'] for r in s2['priced_or_not_estimated_lines_tail'][-1]['context']] == [8, 9, 10]
           and 'lines_from_first_item_below_header_to_first_exact_price_column_total' not in s2['counts']
           and s2['price_column_total_rows_count'] == 0 and s2['last_rows'][-1]['row'] == 10
           and dg['note'].endswith('On a sheet with a bill header and no exact 合計/總計 price-column row, the lines run to its last content row.')
           and all('priced_or_not_estimated_lines_tail' not in s for s in dg['sheets'] if s['index'] != 2), s2.get('counts'))
    record('o72_nototal_bill_reason_and_flag', hp['sheets'][1]['reason'].startswith('bill: the only sheet with a BILL1 header row and no cell reading exactly')
           and [f['detail'] for f in hp['flags'] if f['code'] == 'BILL1_NO_TOTAL_ROW'] == [
               {'header_row': 2, 'end_row': 10, 'note': 'no 合計/總計 in a price column below the header (O72)'}]
           and hp['flags'][0]['code'] == 'BILL1_NO_TOTAL_ROW', hp.get('flags'))
    record('o72_nototal_agree_frozen_admissible_fact_rule', h.get('agree_code') == 0 and h['agree_out'].get('admissible') is True
           and json.loads(h['decision'].read_text(encoding='utf-8'))['scope_fact']['bill_rule'] == 'BILL1.NOTOTAL.v1'
           and json.loads(h['decision'].read_text(encoding='utf-8'))['scope_fact']['end_row'] == 10, h.get('agree_err'))
    bo = h.get('build_out', {})
    record('o72_nototal_build_verify_route_pass', h.get('build_code') == 0 and bo.get('verify') == 'PASS'
           and bo['route_check_inventory'] == {'status': 'PASS', 'route': 'cps046i-route.v4.4', 'scope': 'applied', 'policy_checks': 'applied',
                                               'violations': [], 'warnings': ['R59_LINKED_ANALYSIS_OUT_OF_SCOPE']}
           and bo['stats']['content_cells_scoped'] == 38, bo)
    sraw = h['scoped'].read_bytes() if 'scoped' in h else b''
    fact = next((f_ for f_ in json.loads(sraw or b'{"context_facts":[]}')['context_facts'] if f_['ref'] == 'context:scope'), {})
    record('o72_nototal_basis', 'R49 decides where the quoted range ends inside it; owner decision O72' in fact.get('basis', '')
           and 'candidate 046i' in fact.get('basis', ''), fact.get('basis', '')[:200])
    # the A50-style response on the built no-total packet: rows 3, 4 and 6; the cells after row 6 as on an unscoped packet
    rp = work / 'o72_nototal_response.json'
    rp.write_text(json.dumps(F.nototal_response(sha(sraw)), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    code, out, _ = run(ROUTE, 'check', '--inventory', h['scoped'], '--response', rp)
    o = jout(out)
    record('o72_nototal_e2e_route_check_pass', code == 0 and o.get('status') == 'PASS' and o.get('scope') == 'applied', o.get('violations', [])[:5])
    prop, dig = h['dir'] / 'tool' / 'SCOPE_PROPOSAL.json', h['dir'] / 'tool' / 'SCOPE_DIGEST.json'

    def agree(tag, rd):
        rp_ = work / f'reader_o72_{tag}.json'
        rp_.write_text(json.dumps(rd, ensure_ascii=False), encoding='utf-8')
        code, out, err = run(AGREE, '--proposal', prop, '--digest', dig, '--reader', rp_, '--out-dir', work / f'agree_o72_{tag}')
        return code, jout(out), jout(err)
    for tag, over, whats in (('nototal_end_row_last_item', {'end_row': 6}, {'end_row'}),
                             ('nototal_nulls', {'bill_sheet_index': None, 'end_row': None}, {'bill_sheet_index', 'end_row', 'reader_bill_role'})):
        code, o, e = agree(tag, reader_for(prop, dig, **over))
        record(f'o72_agree_holds_{tag}', code == 3 and o.get('status') == 'HELD_FOR_OWNER' and {d_['what'] for d_ in o.get('differences', [])} == whats, o)
    code, o, e = agree('nototal_standin', reader_for(prop, dig, kind='engineering_stand_in'))
    sd = work / 'agree_o72_nototal_standin' / 'SCOPE_DECISION.json'
    ok = code == 0 and o.get('admissible') is False and sd.exists()
    if ok:
        code, out, err = run(SCOPED, '--full', h['full'], '--decision', sd, '--out-dir', work / 'o72_nototal_standin_packet')
        so = jout(out)
        ok = code == 0 and so['route_check_inventory']['violations'] == ['R59_SCOPE_FACT_INVALID']
    record('o72_nototal_stand_in_not_admissible_route_rejects', ok, o)
    # hand-edited proposals: an unknown bill rule, or a BILL1.NOHEADER.v1 rule with a bill sheet, are refused
    for tag, edit in (('unknown_rule', lambda p_: p_['bill'].update(rule='BILL1.v9')),
                      ('noheader_with_bill_sheet', lambda p_: p_['bill'].update(rule='BILL1.NOHEADER.v1')),
                      ('nototal_null_end_row', lambda p_: p_['bill'].update(end_row=None))):
        pj = json.loads(prop.read_text(encoding='utf-8'))
        edit(pj)
        pe = work / f'proposal_{tag}.json'
        pe.write_bytes((json.dumps(pj, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
        code, out, err = run(AGREE, '--proposal', pe, '--digest', dig, '--reader', work / 'reader_o72_nototal_standin.json', '--out-dir', work / f'agree_{tag}')
        record(f'o72_agree_refuses_proposal_{tag}', code == 1 and jout(err).get('code') == 'PROPOSAL_BILL_RULE' and not (work / f'agree_{tag}').exists(), err[-200:])
    # an item-like priced line below a signature line under an all-unpriced range (design finding R3, NT6): the tool's
    # condition (i) is false and the analysis sheet is scoped out; a reader following the template puts it in scope and holds
    ub = {k: v for k, v in F.SCOPED_BILL.items() if not (k[0] in (3, 6, 7) and k[1] in 'EF') and k not in ((4, 'F'), (8, 'F'))}
    w = pipeline(work, 'o72_priced_tail', build_full(bill=ub)[1])
    wp = w.get('proposal', {})
    record('o72_nototal_priced_tail_scopes_analysis_out', wp.get('status') == 'PROPOSED' and wp['bill']['rule'] == 'BILL1.NOTOTAL.v1'
           and wp['r51']['condition_i_all_unpriced_no_status'] is False and wp['r51']['by_state']['priced'] == 1
           and [s['index'] for s in wp['sheets'] if s['in_scope']] == [2], wp.get('r51'))
    wdg = json.loads((w['dir'] / 'tool' / 'SCOPE_DIGEST.json').read_text(encoding='utf-8'))
    c2 = next(s for s in wdg['sheets'] if s['index'] == 2)['counts']
    record('o72_nototal_priced_tail_visible_in_digest', c2['priced_or_not_estimated_line_rows'] == [10] and c2['last_unpriced_no_status_line_row'] == 6, c2)
    rd = reader_for(w['dir'] / 'tool' / 'SCOPE_PROPOSAL.json', w['dir'] / 'tool' / 'SCOPE_DIGEST.json', sheet_flag=(2, True))
    rp_ = work / 'reader_o72_priced_tail.json'
    rp_.write_text(json.dumps(rd, ensure_ascii=False), encoding='utf-8')
    code, out, err = run(AGREE, '--proposal', w['dir'] / 'tool' / 'SCOPE_PROPOSAL.json', '--digest', w['dir'] / 'tool' / 'SCOPE_DIGEST.json',
                         '--reader', rp_, '--out-dir', work / 'agree_o72_priced_tail')
    record('o72_nototal_priced_tail_reader_puts_analysis_in_scope_holds', code == 3 and [d_['what'] for d_ in jout(out).get('differences', [])] == ['in_scope'], out)
    # the same pattern with no analysis sheet (046i review finding F2): no deterministic hold applies (condition (i) is false,
    # no R51_ALL_UNPRICED_WITHOUT_ANALYSIS_SHEET); a reader following the template (no analysis sheet: end_row null) holds the case
    w2 = pipeline(work, 'o72_priced_tail_no_analysis', build_full(bill=ub, analysis=False, resource_rows=260)[1])
    wp2 = w2.get('proposal', {})
    record('o72_nototal_priced_tail_no_analysis_sheet_not_held_by_tool', w2['tool_code'] == 0 and wp2.get('status') == 'PROPOSED'
           and wp2['bill']['rule'] == 'BILL1.NOTOTAL.v1' and wp2['holds'] == [] and wp2['r51']['condition_i_all_unpriced_no_status'] is False
           and wp2['r51']['by_state']['priced'] == 1 and wp2['r51']['analysis_sheets'] == {} and [s['role'] for s in wp2['sheets']] == ['summary', 'bill', 'resource_statistics']
           and [s['index'] for s in wp2['sheets'] if s['in_scope']] == [2], [wp2.get('r51'), w2.get('tool_err', '')[-300:]])
    P2_, D2_ = w2['dir'] / 'tool' / 'SCOPE_PROPOSAL.json', w2['dir'] / 'tool' / 'SCOPE_DIGEST.json'
    c2b = next(s for s in json.loads(D2_.read_text(encoding='utf-8'))['sheets'] if s['index'] == 2)['counts'] if D2_.exists() else {}
    record('o72_nototal_priced_tail_no_analysis_sheet_visible_in_digest', c2b.get('priced_or_not_estimated_line_rows') == [10]
           and c2b.get('last_unpriced_no_status_line_row') == 6 and 'analysis_blocks' not in c2b, c2b)
    rp_ = work / 'reader_o72_priced_tail_no_analysis.json'
    rp_.write_text(json.dumps(reader_for(P2_, D2_, end_row=None), ensure_ascii=False), encoding='utf-8')
    code, out, err = run(AGREE, '--proposal', P2_, '--digest', D2_, '--reader', rp_, '--out-dir', work / 'agree_o72_priced_tail_no_analysis')
    record('o72_nototal_priced_tail_no_analysis_sheet_reader_null_end_row_holds', code == 3 and jout(out).get('status') == 'HELD_FOR_OWNER'
           and [d_['what'] for d_ in jout(out).get('differences', [])] == ['end_row'], out)
    # BILL1.NOHEADER.v1: the bill header with 序號 and 品名規格 carries four of the six labels; no sheet has a header row
    hb = dict(F.SCOPED_BILL)
    hb[(2, 'A')], hb[(2, 'B')] = (T, '序號', False), (T, '品名規格', False)
    full_d, full_raw = build_full(bill=hb)
    n = pipeline(work, 'o72_whole', full_raw)
    np_ = n.get('proposal', {})
    record('o72_whole_proposed_three_nulls_every_sheet_in_scope', n['tool_code'] == 0 and np_.get('status') == 'PROPOSED'
           and np_['bill']['rule'] == np_['rule']['bill'] == 'BILL1.NOHEADER.v1'
           and [np_['bill'][k] for k in ('sheet_index', 'header_row', 'end_row', 'end_cell', 'first_item_row', 'price_columns')] == [None] * 6
           and np_['bill']['candidates'] == [] and np_['holds'] == [] and np_['r51']['in_range_lines'] == 0
           and np_['r51']['condition_i_all_unpriced_no_status'] is False
           and [(s['index'], s['role'], s['in_scope'], s['linked_analysis_blocks']) for s in np_['sheets']] == [
               (1, 'summary', True, 0), (2, 'other', True, 0), (3, 'analysis', True, 0), (4, 'resource_statistics', True, 0)]
           and all(s['reason'].startswith('whole workbook: no sheet has a BILL1 header row') for s in np_['sheets'])
           and np_['flags'][0] == {'id': 'F1', 'sheet_index': None, 'code': 'BILL1_NO_HEADER',
                                   'detail': {'sheets_in_scope': 4, 'note': 'no row carries five or six BILL1 header labels (O72)'}}
           and np_['in_scope_content_cells'] == np_['content_cells_census'], [n['tool_out'], n['tool_err'][-300:]])
    record('o72_whole_agree_frozen_fact', n.get('agree_code') == 0 and n['agree_out'].get('admissible') is True
           and json.loads(n['decision'].read_text(encoding='utf-8'))['scope_fact']['bill_rule'] == 'BILL1.NOHEADER.v1'
           and [json.loads(n['decision'].read_text(encoding='utf-8'))['scope_fact'][k] for k in ('bill_sheet_index', 'bill_header_row', 'end_row')] == [None] * 3,
           n.get('agree_err'))
    bo = n.get('build_out', {})
    rec = json.loads((n['dir'] / 'packet' / 'SCOPED_INVENTORY_RECEIPT.json').read_text(encoding='utf-8')) if n.get('build_code') == 0 else {}
    record('o72_whole_build_identity_projection_verify_route_pass', n.get('build_code') == 0 and bo.get('verify') == 'PASS'
           and bo['stats']['cells_removed'] == 0 and bo['stats']['views_removed'] == 0 and bo['stats']['views_renumbered'] == 0
           and bo['stats']['cells_kept_byte_identical'] == len(full_d['cells']) and bo['stats']['sheet_in_scope_flags_changed'] == 0
           and all(int(k) == v for k, v in rec.get('view_id_map', {}).items())
           and bo['route_check_inventory']['status'] == 'PASS' and bo['route_check_inventory']['scope'] == 'applied', bo)
    sraw = n['scoped'].read_bytes() if 'scoped' in n else b''
    sl, fl = sraw.decode('utf-8').split('\n'), full_raw.decode('utf-8').split('\n')
    record('o72_whole_scoped_equals_full_plus_the_fact', len(sl) == len(fl) + 1 and [x.rstrip(',') for x in sl if 'context:scope' not in x]
           == [x.rstrip(',') for x in fl], [len(sl), len(fl)])
    fact = next((f_ for f_ in json.loads(sraw or b'{"context_facts":[]}')['context_facts'] if f_['ref'] == 'context:scope'), {})
    record('o72_whole_basis', fact.get('basis', '').startswith('Scope decision for this packet (FIELD_ROLES R59 item 9, candidate 046i, owner decision O72).')
           and 'the scope stage fixed no bill sheet and no end row' in fact['basis'] and 'Read it as an unscoped packet' in fact['basis'])
    prop, dig = n['dir'] / 'tool' / 'SCOPE_PROPOSAL.json', n['dir'] / 'tool' / 'SCOPE_DIGEST.json'
    ndg = json.loads(dig.read_text(encoding='utf-8'))
    record('o72_whole_digest_unchanged_in_form', ndg['note'].endswith('first exact 合計/總計 price-column row.')
           and not any('priced_or_not_estimated_lines_tail' in s or 'lines_from_first_item_below_header_to_last_content_row' in s['counts'] for s in ndg['sheets']))
    for tag, mutate, whats in (
            ('names_bill_sheet', lambda r: (r.update(bill_sheet_index=2, end_row=7), r['sheets'][1].update(role='bill')),
             {'bill_sheet_index', 'end_row', 'reader_bill_role'}),
            ('nonempty_sheet_out', lambda r: r['sheets'][3].update(in_scope=False), {'in_scope'}),
            ('bill_role_with_nulls', lambda r: r['sheets'][1].update(role='bill'), {'reader_bill_role'})):
        rd = reader_for(prop, dig)
        mutate(rd)
        rp_ = work / f'reader_o72_whole_{tag}.json'
        rp_.write_text(json.dumps(rd, ensure_ascii=False), encoding='utf-8')
        code, out, err = run(AGREE, '--proposal', prop, '--digest', dig, '--reader', rp_, '--out-dir', work / f'agree_o72_whole_{tag}')
        record(f'o72_whole_agree_holds_{tag}', code == 3 and {d_['what'] for d_ in jout(out).get('differences', [])} == whats, out[-300:])
    rd = reader_for(prop, dig)
    rd['sheets'][0]['role'] = 'other'
    rp_ = work / 'reader_o72_whole_role_only.json'
    rp_.write_text(json.dumps(rd, ensure_ascii=False), encoding='utf-8')
    code, out, err = run(AGREE, '--proposal', prop, '--digest', dig, '--reader', rp_, '--out-dir', work / 'agree_o72_whole_role_only')
    record('o72_whole_role_difference_recorded_not_held', code == 0 and jout(out).get('role_differences') == 1)
    rp_ = work / 'reader_o72_whole_standin.json'
    rp_.write_text(json.dumps(reader_for(prop, dig, kind='engineering_stand_in'), ensure_ascii=False), encoding='utf-8')
    code, out, err = run(AGREE, '--proposal', prop, '--digest', dig, '--reader', rp_, '--out-dir', work / 'agree_o72_whole_standin')
    ok = code == 0 and jout(out).get('admissible') is False
    if ok:
        code, out, err = run(SCOPED, '--full', n['full'], '--decision', work / 'agree_o72_whole_standin' / 'SCOPE_DECISION.json',
                             '--out-dir', work / 'o72_whole_standin_packet')
        ok = code == 0 and jout(out)['route_check_inventory']['violations'] == ['R59_SCOPE_FACT_INVALID']
    record('o72_whole_stand_in_not_admissible_route_rejects', ok)
    # determinism on both rules
    for tag, res in (('nototal', h), ('whole', n)):
        d2 = work / f'determinism_{tag}'
        run(TOOL, '--inventory', res['full'], '--out-dir', d2)
        record(f'o72_tool_deterministic_{tag}', (d2 / 'SCOPE_PROPOSAL.json').read_bytes() == (res['dir'] / 'tool' / 'SCOPE_PROPOSAL.json').read_bytes()
               and (d2 / 'SCOPE_DIGEST.json').read_bytes() == (res['dir'] / 'tool' / 'SCOPE_DIGEST.json').read_bytes())
    # below the threshold a no-header workbook computes exactly what v3 computed: NOT_APPLIED, rule BILL1.v1, no bill
    small = pipeline(work, 'o72_whole_small', build_full(bill=hb, blocks=100)[1])
    sp = small.get('proposal', {})
    record('o72_below_threshold_not_applied_rule_v1', sp.get('status') == 'NOT_APPLIED' and sp['bill']['rule'] == sp['rule']['bill'] == 'BILL1.v1'
           and sp['bill']['sheet_index'] is None and sp['holds'] == [] and sp['flags'] == [], sp.get('bill'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    a = ap.parse_args()
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=False)
    full_d, full_raw = build_full()
    litcf = sum(1 for c in full_d['cells'] if c['state'] in ('literal', 'cached_formula') and c['saved_value'] not in (None, ''))
    record('fixture_full_inventory_above_threshold', litcf > 2500, litcf)

    # ---- main pipeline
    m = pipeline(work, 'main', full_raw)
    p = m.get('proposal', {})
    b = p.get('bill', {})
    record('tool_proposed', m['tool_code'] == 0 and p.get('status') == 'PROPOSED', m['tool_err'][-300:])
    record('tool_bill1_bill_sheet_header_end', b.get('candidates') == [2] and b.get('sheet_index') == 2 and b.get('header_row') == 2
           and b.get('end_row') == 7 and b.get('end_cell') == 'E7' and b.get('price_columns') == ['E', 'F'] and b.get('first_item_row') == 3, b)
    r51 = p.get('r51', {})
    record('tool_r51_lines_and_states', r51.get('in_range_lines') == 4 and r51.get('by_state') == {'priced': 2, 'not_estimated': 1, 'other_price_text': 0,
           'unpriced_no_status': 1} and r51.get('condition_i_all_unpriced_no_status') is False and r51.get('option_iii_adopted') is False
           and r51.get('condition_ii_adopted') is False, r51)
    an = r51.get('analysis_sheets', {}).get('3', {})
    record('tool_analysis_blocks_and_links', an.get('blocks') == 130 and an.get('components') == 390 and an.get('linked_blocks') == 1
           and an.get('links_by') == {'code': 0, 'name': 1, 'outline_path': 0} and an.get('linked_blocks_by_parent_state', {}).get('priced') == 1
           and an.get('linked_blocks_of_unpriced_lines') == 0 and 'condition_ii' not in an, an)
    roles = {s['index']: (s['role'], s['in_scope'], s['linked_analysis_blocks']) for s in p.get('sheets', [])}
    record('tool_roles_and_flags', roles == {1: ('summary', False, 0), 2: ('bill', True, 0), 3: ('analysis', False, 1), 4: ('resource_statistics', False, 0)}
           and [(f['sheet_index'], f['code']) for f in p.get('flags', [])] == [(1, 'OUT_OF_SCOPE_NONZERO_PRICES'), (3, 'LINKED_BLOCKS_OUT_OF_SCOPE'),
                                                                              (4, 'OUT_OF_SCOPE_NONZERO_PRICES')], [roles, p.get('flags')])
    record('tool_in_scope_content_cells', p.get('in_scope_content_cells') == 39 and p.get('content_cells_literal_or_cached') == litcf, p.get('in_scope_content_cells'))
    dig_b = (m['dir'] / 'tool' / 'SCOPE_DIGEST.json').read_bytes()
    exc = (m['dir'] / 'tool' / 'SCOPE_RULES_EXCERPT.md').read_text(encoding='utf-8')
    record('tool_digest_pinned_and_excerpt_verbatim', p.get('digest', {}).get('sha256') == sha(dig_b) and p.get('rules_excerpt', {}).get('sha256') == sha(exc.encode('utf-8'))
           and all(k in exc for k in ('**R47b ', '**R49 ', '**R50 ', '**R51 ')) and '**R52 ' not in exc and '**R59 ' not in exc
           and all(chunk in (HERE.parent / 'package' / 'resources' / 'FIELD_ROLES.md').read_text(encoding='utf-8') for chunk in exc.split('\n\n')[2:]), p.get('digest'))
    dg = json.loads(dig_b)
    s3 = next(s for s in dg['sheets'] if s['index'] == 3)
    s4 = next(s for s in dg['sheets'] if s['index'] == 4)
    record('digest_contents', len(dg['sheets']) == 4 and s3['block_headings']['count'] == 130 and len(s3['block_headings']['first']) == 2
           and s3['header_repeats']['count'] == 129 and all(len(rw['cells']) <= 10 for s in dg['sheets'] for k in ('rows_below_header', 'last_rows') for rw in s.get(k, []))
           and s4['first_header_row']['cells'][-1]['a'] == 'J2' and next(s for s in dg['sheets'] if s['index'] == 2)['price_column_total_rows'][0]['row'] == 7
           and len(next(s for s in dg['sheets'] if s['index'] == 2)['price_column_total_rows'][0]['context']) == 5, [s3['header_repeats'], s3['block_headings']['count']])
    record('tool_prints_no_cell_text_or_sheet_names', '示例' not in m['tool_out'].__repr__() and m['tool_out'].get('values_printed') is False)
    # determinism
    d2 = work / 'determinism'
    run(TOOL, '--inventory', m['full'], '--out-dir', d2)
    record('tool_deterministic', (d2 / 'SCOPE_DIGEST.json').read_bytes() == dig_b
           and (d2 / 'SCOPE_PROPOSAL.json').read_bytes() == (m['dir'] / 'tool' / 'SCOPE_PROPOSAL.json').read_bytes())
    record('agree_frozen_admissible', m.get('agree_code') == 0 and m['agree_out'].get('status') == 'FROZEN_AGREED' and m['agree_out'].get('admissible') is True, m.get('agree_err'))
    dec = json.loads(m['decision'].read_text(encoding='utf-8'))
    sf = dec['scope_fact']
    record('decision_scope_fact', sf['bill_sheet_index'] == 2 and sf['end_row'] == 7 and sf['digest_sha256'] == sha(dig_b) and sf['full_inventory_sha256'] == sha(full_raw)
           and [s['in_scope'] for s in sf['sheets']] == [False, True, False, False] and dec['reader_response_sha256'] == sha((m['dir'] / 'reader.json').read_bytes()))
    bo = m.get('build_out', {})
    record('build_written_verified_route_pass', m.get('build_code') == 0 and bo.get('verify') == 'PASS' and bo.get('route_check_inventory', {}).get('status') == 'PASS'
           and bo['route_check_inventory'].get('scope') == 'applied' and bo['route_check_inventory'].get('policy_checks') == 'applied'
           and bo['route_check_inventory'].get('warnings') == ['R59_LINKED_ANALYSIS_OUT_OF_SCOPE'], [bo, m.get('build_err', '')[-300:]])
    st = bo.get('stats', {})
    nviews_s1 = len(views_for('示例總表', 12, 4, 1))
    record('build_projection_stats', st.get('cells_removed') == len(full_d['cells']) - 70 and st.get('cells_kept_byte_identical', 0) + st.get('cells_kept_views_renumbered_only', 0) == 70
           and st.get('views_kept') == 1 and st.get('content_cells_scoped') == 39 and st.get('context_facts_unchanged') == len(full_d['context_facts'])
           and st.get('context_facts_appended') == 1, st)
    rec = json.loads((m['dir'] / 'packet' / 'SCOPED_INVENTORY_RECEIPT.json').read_text(encoding='utf-8'))
    record('build_view_renumbering', rec['view_id_map'] == {str(nviews_s1 + 1): 1}, rec['view_id_map'])
    scoped_raw = m['scoped'].read_bytes()
    full_lines = {x.rstrip(',') for x in full_raw.decode('utf-8').split('\n')}      # the list separator after a record is not part of it
    sl = [x.rstrip(',') for x in scoped_raw.decode('utf-8').split('\n')]
    changed = [x for x in sl if x not in full_lines]
    record('build_kept_lines_byte_identical_except_documented', all(('"views":[1]' in x and '"sheet_index":2' in x) or '"in_scope":' in x or 'context:scope' in x
                                                                    or x.startswith(' "source":') or x.startswith('  {"id":1,') for x in changed), [x[:80] for x in changed if not (
        ('"views":[1]' in x and '"sheet_index":2' in x) or '"in_scope":' in x or 'context:scope' in x or x.startswith(' "source":') or x.startswith('  {"id":1,'))][:5])
    # end to end: route v4.3 accepts the pipeline's scoped packet with the make_fixtures scoped response
    resp = F.scoped_response(sha(scoped_raw))
    rp = work / 'e2e_response.json'
    rp.write_text(json.dumps(resp, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    code, out, _ = run(ROUTE, 'check', '--inventory', m['scoped'], '--response', rp)
    o = jout(out)
    record('e2e_route_check_pass_on_pipeline_scoped_packet', code == 0 and o.get('status') == 'PASS' and o.get('scope') == 'applied'
           and [w['code'] for w in o.get('warnings', [])][0] == 'R59_LINKED_ANALYSIS_OUT_OF_SCOPE', o.get('violations', [])[:5])
    code, out, _ = run(ROUTE, 'check', '--inventory', m['full'], '--response', rp)
    record('e2e_same_response_fails_on_full_inventory', code == 1 and 'UNCLASSIFIED_CONTENT_CELLS' in {v['code'] for v in jout(out).get('violations', [])})
    # verify: PASS, pinned hash, tampers
    code, out, _ = run(SCOPED, '--verify', '--full', m['full'], '--decision', m['decision'], '--scoped', m['scoped'], '--expect-scoped-sha256', sha(scoped_raw))
    record('verify_pass_with_pinned_hash', code == 0 and jout(out).get('status') == 'PASS', jout(out).get('problems'))
    code, out, _ = run(SCOPED, '--verify', '--full', m['full'], '--decision', m['decision'], '--scoped', m['scoped'], '--expect-scoped-sha256', '0' * 64)
    record('verify_fails_on_wrong_pinned_hash', code == 2 and jout(out).get('status') == 'FAIL')
    sd = json.loads(scoped_raw)
    fd = json.loads(full_raw)

    def tamper(name, f, raw_override=None):
        t = copy.deepcopy(sd)
        f(t)
        b = raw_override(t) if raw_override else F.serialize(t).encode('utf-8')
        tp = work / f'tamper_{name}.json'
        tp.write_bytes(b)
        code, out, _ = run(SCOPED, '--verify', '--full', m['full'], '--decision', m['decision'], '--scoped', tp)
        record(f'verify_detects_{name}', code == 2 and jout(out).get('status') == 'FAIL' and jout(out).get('problem_count', 0) >= 1, jout(out).get('problems', [])[:3])
    def cell(t, addr):
        return next(c for c in t['cells'] if c['address'] == addr)
    tamper('changed_cell_value', lambda t: cell(t, 'B3').update(saved_value='產品，電磁接觸器，AC110V', canonical_raw='產品，電磁接觸器，AC110V'))
    tamper('removed_kept_cell', lambda t: t['cells'].remove(cell(t, 'G10')))
    tamper('out_of_scope_cell_added', lambda t: t['cells'].append(next(c for c in fd['cells'] if c['sheet_index'] == 3)))
    tamper('flag_flipped', lambda t: t['sheets'][2].update(in_scope=True))
    tamper('context_fact_edited', lambda t: t['context_facts'][1].update(value='另一客戶'))
    def fact_end(t):
        v = json.loads(t['context_facts'][-1]['value'])
        v['end_row'] = 8
        t['context_facts'][-1]['value'] = json.dumps(v, ensure_ascii=False, separators=(',', ':'))
    tamper('scope_fact_edited', fact_end)
    tamper('view_ids_not_renumbered', lambda t: [c.update(views=[nviews_s1 + 1]) for c in t['cells'] if c['views'] == [1]])
    tamper('limitation_edited', lambda t: t['limitations'].append('extra'))
    tamper('layout_changed', lambda t: None, raw_override=lambda t: (json.dumps(t, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
    tamper('other_view_kept', lambda t: (t['views'].append(dict(fd['views'][0], id=2)), t['source']['carrier_source']['views'].append({k: fd['views'][0][k] for k in ('sheet', 'range')} | {'id': 2})))
    # build refusals
    code, _, err = run(SCOPED, '--full', m['full'], '--decision', m['decision'], '--out-dir', m['dir'] / 'packet')
    record('build_refuses_existing_output', code == 1 and jout(err).get('code') == 'OUTPUT_EXISTS')
    other_d, other_raw = build_full(blocks=131)
    op = work / 'other_full.json'
    op.write_bytes(other_raw)
    code, _, err = run(SCOPED, '--full', op, '--decision', m['decision'], '--out-dir', work / 'refuse_other')
    record('build_refuses_decision_of_other_inventory', code == 1 and jout(err).get('code') == 'FULL_INVENTORY_SHA256_MISMATCH' and not (work / 'refuse_other').exists())
    lp = work / 'full_indented.json'
    lp.write_bytes((json.dumps(full_d, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
    code, _, err = run(SCOPED, '--full', lp, '--decision', m['decision'], '--out-dir', work / 'refuse_layout')
    record('build_refuses_noncanonical_full_layout', code == 1 and jout(err).get('code') == 'FULL_INVENTORY_LAYOUT')
    code, _, err = run(TOOL, '--inventory', m['scoped'], '--out-dir', work / 'refuse_scoped')
    record('tool_refuses_scoped_inventory', code == 1 and jout(err).get('code') == 'FULL_INVENTORY_REQUIRED')
    af = copy.deepcopy(full_d)
    af['context_facts'].append(copy.deepcopy(sd['context_facts'][-1]))
    ap_ = work / 'full_with_scope_fact.json'
    ap_.write_bytes(F.serialize(af).encode('utf-8'))
    code, _, err = run(TOOL, '--inventory', ap_, '--out-dir', work / 'refuse_already')
    record('tool_refuses_inventory_already_carrying_scope_fact', code == 1 and jout(err).get('code') == 'ALREADY_SCOPED' and not (work / 'refuse_already').exists())
    # agreement: disagreements hold, malformed readers are refused
    prop, dig = m['dir'] / 'tool' / 'SCOPE_PROPOSAL.json', m['dir'] / 'tool' / 'SCOPE_DIGEST.json'
    def agree(tag, rd, want_code):
        rp_ = work / f'reader_{tag}.json'
        rp_.write_text(json.dumps(rd, ensure_ascii=False), encoding='utf-8')
        code, out, err = run(AGREE, '--proposal', prop, '--digest', dig, '--reader', rp_, '--out-dir', work / f'agree_{tag}')
        return code, jout(out), jout(err)
    for tag, over, what in (('end_row', {'end_row': 8}, 'end_row'), ('bill', {'bill_sheet_index': 1}, 'bill_sheet_index'),
                            ('flag', {'sheet_flag': (2, True)}, 'in_scope'), ('bill_null', {'bill_sheet_index': None}, 'bill_sheet_index')):
        code, o, e = agree(tag, reader_for(prop, dig, **over), 3)
        record(f'agree_holds_on_{tag}_disagreement', code == 3 and o.get('status') == 'HELD_FOR_OWNER' and what in {d_['what'] for d_ in o.get('differences', [])}
               and (work / f'agree_{tag}' / 'SCOPE_HOLD.json').exists() and not (work / f'agree_{tag}' / 'SCOPE_DECISION.json').exists(), o)
    code, o, e = agree('standin', reader_for(prop, dig, kind='engineering_stand_in'), 0)
    record('agree_stand_in_reader_not_admissible', code == 0 and o.get('admissible') is False)
    # 046g round 1, S13: the payload says tool_and_reader_agreed only for an admissible decision; a stand-in decision
    # says tool_and_stand_in_agreed, which route v4.3 rejects, so it can never become a generation packet
    record('agree_admissible_decision_agreement_tool_and_reader', dec.get('admissible') is True
           and sf.get('agreement') == 'tool_and_reader_agreed', sf.get('agreement'))
    sdec_p = work / 'agree_standin' / 'SCOPE_DECISION.json'
    sdec = json.loads(sdec_p.read_text(encoding='utf-8')) if sdec_p.exists() else {}
    record('agree_stand_in_decision_agreement_tool_and_stand_in', sdec.get('admissible') is False
           and sdec.get('scope_fact', {}).get('agreement') == 'tool_and_stand_in_agreed'
           and {k: v for k, v in sdec.get('scope_fact', {}).items() if k != 'agreement'} == {k: v for k, v in sf.items() if k != 'agreement'},
           sdec.get('scope_fact', {}).get('agreement'))
    code, out, err = run(SCOPED, '--full', m['full'], '--decision', sdec_p, '--out-dir', work / 'standin_packet')
    so = jout(out)
    rci = so.get('route_check_inventory', {})
    record('build_from_stand_in_decision_rejected_by_route', code == 0 and so.get('decision_admissible') is False
           and rci.get('status') == 'REJECTED' and rci.get('violations') == ['R59_SCOPE_FACT_INVALID'], [so, err[-300:]])
    sp_ = work / 'standin_packet' / 'SOURCE_INVENTORY.json'
    if sp_.exists():
        sfact = next(f_ for f_ in json.loads(sp_.read_text(encoding='utf-8'))['context_facts'] if f_['ref'] == 'context:scope')
        record('stand_in_packet_basis_names_stand_in', 'not a fresh-context scope reader' in sfact['basis']
               and 'a fresh-context scope reader decided' not in sfact['basis'])
        rps = work / 'e2e_response_stand_in.json'
        rps.write_text(json.dumps(F.scoped_response(sha(sp_.read_bytes())), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        code, out, _ = run(ROUTE, 'check', '--inventory', sp_, '--response', rps)
        record('e2e_route_check_rejects_stand_in_packet', code == 1 and 'R59_SCOPE_FACT_INVALID' in {v['code'] for v in jout(out).get('violations', [])},
               [v['code'] for v in jout(out).get('violations', [])][:5])
    else:
        record('stand_in_packet_basis_names_stand_in', False, 'no stand-in packet written')
        record('e2e_route_check_rejects_stand_in_packet', False, 'no stand-in packet written')
    main_fact = next(f_ for f_ in sd['context_facts'] if f_['ref'] == 'context:scope')
    record('admissible_packet_basis_unchanged', 'a fresh-context scope reader decided from the scope digest alone; the two agreed' in main_fact['basis'])
    rd = reader_for(prop, dig)
    rd['sheets'][0]['role'] = 'other'
    code, o, e = agree('role_only', rd, 0)
    record('agree_role_difference_recorded_not_held', code == 0 and o.get('status') == 'FROZEN_AGREED' and o.get('role_differences') == 1)
    rd = reader_for(prop, dig)
    rd.pop('doubts')
    code, o, e = agree('missing_key', rd, 1)
    record('agree_refuses_malformed_reader', code == 1 and e.get('code') == 'READER_KEYS' and not (work / 'agree_missing_key').exists())
    code, o, e = agree('wrong_digest', reader_for(prop, dig, digest_sha256='0' * 64), 1)
    record('agree_refuses_reader_of_other_digest', code == 1 and e.get('code') == 'READER_DIGEST_SHA256')
    # BILL1 holds and the threshold
    nb = dict(F.SCOPED_BILL)
    nb.pop((7, 'E'))
    # 046i (O72): this 046g hold fixture is O72's first pattern (one six-label header, no 合計/總計 in a price column);
    # re-specified by design: BILL1.NOTOTAL.v1, the bill sheet to its last content row
    h = pipeline(work, 'no_total', build_full(bill=nb)[1])
    hp = h.get('proposal', {})
    record('tool_no_total_scopes_to_last_content_row', h['tool_code'] == 0 and hp.get('status') == 'PROPOSED' and hp['bill']['candidates'] == []
           and hp['bill']['rule'] == hp['rule']['bill'] == 'BILL1.NOTOTAL.v1' and hp['bill']['sheet_index'] == 2 and hp['bill']['header_row'] == 2
           and hp['bill']['end_row'] == 10 and hp['bill']['end_cell'] is None and hp['bill']['first_item_row'] == 3 and hp['holds'] == []
           and hp['r51']['in_range_lines'] == 5 and hp['r51']['by_state'] == {'priced': 3, 'not_estimated': 1, 'other_price_text': 0, 'unpriced_no_status': 1}
           and hp['r51']['condition_i_all_unpriced_no_status'] is False and [s['index'] for s in hp['sheets'] if s['in_scope']] == [2]
           and {'BILL1_NO_TOTAL_ROW', 'NEAR_BILL1_CANDIDATE'} <= {f['code'] for f in hp['flags']}, h['tool_out'])
    # 046i: the zero-candidate hold stays: the only header-like row carries five of the six labels (品名規格 is not a name word)
    fb = dict(F.SCOPED_BILL)
    fb[(2, 'B')] = (T, '品名規格', False)
    h5 = pipeline(work, 'five_of_six', build_full(bill=fb)[1], expect_tool=4)
    hp5 = json.loads((h5['dir'] / 'tool' / 'SCOPE_PROPOSAL.json').read_text(encoding='utf-8')) if h5['tool_code'] == 4 else {}
    record('tool_holds_zero_bill1_candidates_five_of_six', h5['tool_code'] == 4 and hp5.get('status') == 'HOLD' and hp5['bill']['candidates'] == []
           and hp5['bill']['rule'] == 'BILL1.v1' and [x['code'] for x in hp5['holds']] == ['BILL1_CANDIDATES_NOT_ONE'], h5['tool_out'])
    o72_tests(work, h, nb, prop, dig)
    h = pipeline(work, 'two_bills', build_full(extra_bill_copy=True)[1], expect_tool=4)
    record('tool_holds_two_bill1_candidates', h['tool_code'] == 4 and h['tool_out'].get('bill_candidates') == [2, 5] and h['tool_out'].get('holds') == ['BILL1_CANDIDATES_NOT_ONE'], h['tool_out'])
    code, _, err = run(AGREE, '--proposal', h['dir'] / 'tool' / 'SCOPE_PROPOSAL.json', '--digest', h['dir'] / 'tool' / 'SCOPE_DIGEST.json',
                       '--reader', work / 'reader_end_row.json', '--out-dir', work / 'agree_on_hold')
    record('agree_refuses_tool_hold', code == 1 and jout(err).get('code') == 'PROPOSAL_NOT_PROPOSED')
    small = pipeline(work, 'small', build_full(blocks=100)[1])
    sp = small.get('proposal', {})
    record('tool_threshold_not_applied', small['tool_code'] == 0 and sp.get('status') == 'NOT_APPLIED' and sp.get('applies') is False and sp.get('digest') is None
           and all(s['in_scope'] for s in sp.get('sheets', [])) and not (small['dir'] / 'tool' / 'SCOPE_DIGEST.json').exists()
           and sp.get('content_cells_literal_or_cached', 9999) <= 2500, sp.get('content_cells_literal_or_cached'))
    code, _, err = run(AGREE, '--proposal', small['dir'] / 'tool' / 'SCOPE_PROPOSAL.json', '--digest', dig, '--reader', work / 'reader_end_row.json',
                       '--out-dir', work / 'agree_small')
    record('agree_refuses_not_applied', code == 1 and jout(err).get('code') == 'PROPOSAL_NOT_PROPOSED')
    # former R51 condition (ii), dropped in 046g pass 2: a block linked to the unpriced, no-status line leaves the analysis sheet
    # out of scope (a separate analysis sheet lies outside the quoted range, A26); the line stays excluded_supply
    c2 = pipeline(work, 'r51_ii', build_full(analysis_kw={'first_name': '溫度計'})[1])
    cp = c2.get('proposal', {})
    an2 = cp.get('r51', {}).get('analysis_sheets', {}).get('3', {})
    lf = [f for f in cp.get('flags', []) if f['code'] == 'LINKED_BLOCKS_OUT_OF_SCOPE']
    record('tool_unpriced_line_linked_block_stays_out_of_scope', cp.get('status') == 'PROPOSED' and [s['index'] for s in cp['sheets'] if s['in_scope']] == [2]
           and an2.get('linked_blocks') == 1 and an2.get('linked_blocks_of_unpriced_lines') == 1 and cp['sheets'][2]['linked_analysis_blocks'] == 1
           and cp['sheets'][2]['reason'].startswith('analysis: not every in-range bill line has no price and no status')
           and '0 of priced or not-estimated parents' in cp['sheets'][2]['reason'] and '1 of parents with no price and no status' in cp['sheets'][2]['reason']
           and len(lf) == 1 and lf[0]['detail'] == {'blocks': 1, 'of_priced_or_not_estimated_parents': 0, 'of_parents_with_no_price_and_no_status': 1},
           [cp.get('sheets'), lf])
    bo2 = c2.get('build_out', {})
    record('build_unpriced_linked_block_scoped_without_analysis_cells', c2.get('build_code') == 0 and bo2.get('verify') == 'PASS'
           and bo2['route_check_inventory']['status'] == 'PASS' and bo2['route_check_inventory']['warnings'] == ['R59_LINKED_ANALYSIS_OUT_OF_SCOPE']
           and bo2['stats']['content_cells_scoped'] == 39, bo2.get('stats'))
    # the same response as on the main packet (bill row 5 excluded_supply, no components) passes on this packet
    rp2 = work / 'e2e_response_unpriced_link.json'
    rp2.write_text(json.dumps(F.scoped_response(sha(c2['scoped'].read_bytes())), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    code, out, _ = run(ROUTE, 'check', '--inventory', c2['scoped'], '--response', rp2)
    o2 = jout(out)
    record('e2e_unpriced_linked_block_line_excluded_supply_passes', code == 0 and o2.get('status') == 'PASS' and o2.get('scope') == 'applied'
           and [w['code'] for w in o2.get('warnings', [])][0] == 'R59_LINKED_ANALYSIS_OUT_OF_SCOPE', o2.get('violations', [])[:5])
    # R51 (i): every in-range line unpriced with no status (a priced heading row satisfies BILL1 (c))
    ub = {k: v for k, v in F.SCOPED_BILL.items() if not (k[0] in (3, 6) and k[1] in 'EF') and k != (4, 'F')}
    ub[(3, 'C')] = ub[(3, 'D')] = None
    ub = {k: v for k, v in ub.items() if v is not None}
    ub.update({(3, 'A'): (T, '一', False), (3, 'B'): (T, '示例控制盤', False), (3, 'F'): (N, 8000.0, False)})
    c1 = pipeline(work, 'r51_i', build_full(bill=ub, blocks=135)[1])
    p1 = c1.get('proposal', {})
    record('tool_r51_condition_i_all_unpriced', p1.get('status') == 'PROPOSED' and p1['r51']['condition_i_all_unpriced_no_status'] is True
           and p1['r51']['by_state'] == {'priced': 0, 'not_estimated': 0, 'other_price_text': 0, 'unpriced_no_status': 3}
           and [s['index'] for s in p1['sheets'] if s['in_scope']] == [2, 3] and p1['sheets'][2]['reason'].startswith('analysis: every in-range bill line'), p1.get('r51'))
    # flags: hidden sheet, nonzero prices on an out-of-scope analysis sheet
    f_ = pipeline(work, 'flags', build_full(hidden_resource=True, analysis_kw={'priced_component': True})[1])
    fl = [x['code'] for x in f_.get('proposal', {}).get('flags', [])]
    record('tool_flags_hidden_and_out_of_scope_prices', 'HIDDEN_SHEET' in fl and 'OUT_OF_SCOPE_NONZERO_PRICES' in fl and f_['proposal']['status'] == 'PROPOSED', fl)
    # view images: copied with pins checked, only for in-scope views
    vd, vraw = build_full()
    imgs = {v['id']: f'invented view image {v["id"]}'.encode() for v in vd['views']}
    vd2, vraw2 = build_full(images={k: {'file': f'view_{k:02d}.png', 'bytes': len(b), 'sha256': sha(b)} for k, b in imgs.items()})
    iv = pipeline(work, 'images', vraw2)
    for k, b in imgs.items():
        (iv['dir'] / 'full' / f'view_{k:02d}.png').write_bytes(b)
    dec_i = iv['dir'] / 'decision' / 'SCOPE_DECISION.json'
    code, out, err = run(SCOPED, '--full', iv['full'], '--decision', dec_i, '--out-dir', iv['dir'] / 'packet_img')
    names = sorted(x.name for x in (iv['dir'] / 'packet_img').glob('view_*.png')) if code == 0 else []
    record('build_copies_only_in_scope_view_images', code == 0 and names == [f'view_{nviews_s1 + 1:02d}.png'], [code, names, err[-200:]])
    (iv['dir'] / 'full' / f'view_{nviews_s1 + 1:02d}.png').write_bytes(b'tampered')
    code, out, err = run(SCOPED, '--full', iv['full'], '--decision', dec_i, '--out-dir', iv['dir'] / 'packet_img2')
    record('build_refuses_view_image_pin_mismatch', code == 1 and jout(err).get('code') == 'VIEW_IMAGE_PIN_MISMATCH' and not (iv['dir'] / 'packet_img2').exists())

    summary = {'tests': len(results), 'passed': sum(r['pass'] for r in results), 'failed': [r for r in results if not r['pass']],
               'fixtures_invented': True, 'tools_sha256': {p_.name: sha(p_.read_bytes()) for p_ in (TOOL, AGREE, SCOPED, ROUTE)}}
    (work / 'SCOPE_STAGE_TEST_RESULTS.json').write_text(json.dumps({'summary': summary, 'results': results}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if not summary['failed'] else 1


if __name__ == '__main__':
    sys.exit(main())
