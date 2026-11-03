"""Invented route fixtures for candidate 046b. No project data: every name/value is made up.

Writes: fixture inventory (unverified adoption), a verified-adoption variant, one valid
response, and single-defect mutations with the violation code each must trigger.
"""
import copy, hashlib, json, sys
from pathlib import Path

OUT = Path(sys.argv[1])
COLS = 'ABCDEFGHIJKLMNOPQ'


def letters(n):
    s = ''
    while n:
        n, k = divmod(n - 1, 26)
        s = chr(65 + k) + s
    return s


S1 = '示例明細'
S2 = '單價分析'
# (row, col_letter): (saved_type, value, formula_record)
T, N = 'text', 'number'
sheet1 = {
    (1, 'A'): (T, '示例淨水場控制盤更新工程 詳細價目表', False),
    **{(2, c): (T, v, False) for c, v in zip('ABCDEFG', ['項次', '項目及說明', '單位', '數量', '單價', '複價', '備註'])},
    (3, 'A'): (T, '壹', False), (3, 'B'): (T, '示例控制盤', False), (3, 'C'): (T, 'W600×H800×D300', False),
    (4, 'A'): (T, '1', False), (4, 'B'): (T, 'QX-620電磁接觸器 AC110V', False), (4, 'C'): (T, '只', False),
    (4, 'D'): (N, 2.0, False), (4, 'E'): (N, 1500.0, False), (4, 'F'): (N, 3000.0, True), (4, 'G'): (T, '', False),
    (5, 'B'): (T, '附端子蓋', False),
    (6, 'A'): (T, '2', False), (6, 'B'): (T, '三段式選擇開關', False), (6, 'C'): (T, '個', False),
    (6, 'D'): (N, 3.0, False), (6, 'E'): (N, 120.5, False), (6, 'F'): (N, 361.5, True), (6, 'G'): (T, '不含估價', False),
    (7, 'A'): (T, '3', False), (7, 'B'): (T, '盤體組立費', False), (7, 'C'): (T, '式', False),
    (7, 'D'): (N, 1.0, False), (7, 'E'): (N, 8000.0, False), (7, 'F'): (N, 8000.0, True), (7, 'G'): (T, '001.00', False),
    (8, 'A'): (T, '4', False), (8, 'B'): (T, '備用接點', False), (8, 'C'): (T, '只', False),
    (8, 'D'): (N, 0.0, False), (8, 'E'): (N, 0.1 + 0.2, False), (8, 'F'): (N, 0.0, True),
    (9, 'B'): (T, '小計', False), (9, 'F'): (N, 11361.5, True),
    (10, 'B'): (T, '以上單價含運費', False),
    (11, 'A'): (T, '5', False), (11, 'B'): (T, '溫度計', False), (11, 'C'): (T, '支', False),
    (11, 'D'): (N, 1.0, False), (11, 'E'): (N, 1e-05, False), (11, 'F'): (N, 1e-05, True), (11, 'G'): (T, '-20~60℃', False),
    (12, 'A'): (T, '6', False), (12, 'B'): (T, '流量計', False), (12, 'C'): (T, '台', False),
    (12, 'D'): (N, 1.0, False), (12, 'E'): (N, 50000.0, False), (12, 'F'): (N, 50000.0, True),
    (12, 'G'): (T, '廠牌：示例儀器 型號：FM-100', False),
    (13, 'A'): (T, '訂購客戶：示例自來水處', False),
    (14, 'A'): (T, '使用單位：示例淨水場', False),
    (15, 'A'): (T, '供應商：示例電機行', False),
    (16, 'A'): (T, '需要日期：2026-12-01', False), (16, 'C'): ('date', 46357.0, False),
    (16, 'D'): ('boolean', True, False), (16, 'E'): ('error', '#DIV/0!', True),
    (17, 'A'): (T, '需要數量', False), (17, 'B'): (N, 2.0, False), (17, 'C'): (T, '0', False), (17, 'D'): (N, 0.0, False),
    (18, 'A'): (T, '7', False), (18, 'B'): (T, '詳配電盤規範', False), (18, 'C'): (T, '式', False), (18, 'D'): (N, 1.0, False),
}
sheet2 = {
    (1, 'A'): (T, '盤體組立費 單價分析', False),
    **{(2, c): (T, v, False) for c, v in zip('ABCD', ['名稱', '單位', '數量', '說明'])},
    (3, 'A'): (T, '組立工資', False), (3, 'B'): (T, '工', False), (3, 'C'): (N, 2.0, False), (3, 'D'): (T, '每式', False),
    (4, 'A'): (T, '配線材料', False), (4, 'B'): (T, '式', False), (4, 'C'): (N, 1.0, False), (4, 'D'): (T, '每式', False),
}
merges = {1: ['A1:G1', 'A13:G13'], 2: ['A1:D1']}
views = [{'id': 1, 'sheet': S1, 'range': 'A1:G8'}, {'id': 2, 'sheet': S1, 'range': 'A9:G18'}, {'id': 3, 'sheet': S2, 'range': 'A1:D4'}]
EXPECT_CANON = {'cell:S1!E8': '0.30000000000000004', 'cell:S1!E11': '0.00001', 'cell:S1!F11': '0.00001',
                'cell:S1!D8': '0', 'cell:S1!E6': '120.5', 'cell:S1!F4': '3000', 'cell:S1!G7': '001.00', 'cell:S1!C17': '0'}


def canon(v):
    from decimal import Decimal
    s = format(Decimal(repr(float(v))), 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def serialize(inv):
    def dump(x):
        return json.dumps(x, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    parts = []
    for k, v in inv.items():
        if k in ('cells', 'sheets', 'views', 'context_facts', 'limitations') and isinstance(v, list):
            body = ',\n'.join('  ' + dump(x) for x in v)
            parts.append(f' {dump(k)}:[\n{body}\n ]' if v else f' {dump(k)}:[]')
        else:
            parts.append(f' {dump(k)}:{dump(v)}')
    return '{\n' + ',\n'.join(parts) + '\n}\n'


def build_inventory(adoption, overrides=None, extra_sheet=False):
    cells = []
    sheets = []
    s1 = dict(sheet1)
    s1.update(overrides or {})
    specs = [(S1, s1, 18, 7), (S2, sheet2, 4, 4)]
    vws = list(views)
    if extra_sheet:
        specs.append(('資源統計', {(r, letters(c)): (T, f'統計{r}-{c}', False) for r in range(1, 52) for c in range(1, 101)}, 51, 100))
        merges[3] = []
        vws.append({'id': 4, 'sheet': '資源統計', 'range': 'A1:CV51'})
    for si, (name, data, rows, cols) in enumerate(specs, start=1):
        cov = {}
        for m in merges[si]:
            a, b = m.split(':')
            c0, r0 = ord(a[0]) - 64, int(a[1:])
            c1, r1 = ord(b[0]) - 64, int(b[1:])
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    if (r, c) != (r0, c0):
                        cov[(r, c)] = f'cell:S{si}!{letters(c0)}{r0}'
        sheets.append({'index': si, 'name': name, 'visibility': 'visible', 'rows': rows, 'columns': cols,
                       'merges': merges[si], 'formula_records': sum(1 for v in data.values() if v[2]), 'in_scope': True})
        for r in range(1, rows + 1):
            for c in range(1, cols + 1):
                L = letters(c)
                ref = f'cell:S{si}!{L}{r}'
                typ, val, frm = data.get((r, L), ('blank', None, False))
                state, canonical, usable, reason, conflicts = None, None, False, None, []
                if (r, c) in cov:
                    state, reason = 'covered', 'covered merge position; use the merge anchor'
                elif typ == 'blank':
                    state, reason = 'true_blank', 'empty cell has no raw text'
                elif typ == T and val == '':
                    state, reason = 'explicit_empty', 'explicit empty string has no raw text'
                elif typ == 'error':
                    state, reason = 'error', 'saved error value is not raw text'
                else:
                    state = 'cached_formula' if frm else 'literal'
                    if typ == T:
                        canonical, usable = val, True
                    elif typ == N:
                        canonical, usable = canon(val), True
                    elif typ == 'date':
                        reason = 'date-typed serial; display format is not reproduced by this profile'
                    elif typ == 'boolean':
                        reason = 'boolean saved value is not material raw text in this profile'
                vv = [v['id'] for v in vws if v['sheet'] == name and r >= int(''.join(ch for ch in v['range'].split(':')[0] if ch.isdigit())) and r <= int(''.join(ch for ch in v['range'].split(':')[1] if ch.isdigit()))]
                cells.append({'ref': ref, 'sheet_index': si, 'sheet': name, 'address': f'{L}{r}', 'row': r, 'col': c,
                              'saved_type': typ if typ != 'blank' else 'blank', 'state': state, 'saved_value': val,
                              'native_literal': None, 'formula_record_present': frm, 'formula': None,
                              'merge_anchor_ref': cov.get((r, c)), 'conflicts': conflicts, 'canonical_raw': canonical,
                              'usable_for_raw': usable, 'raw_limit_reason': reason, 'views': vv})
    fake_sha = hashlib.sha256(b'invented fixture workbook bytes').hexdigest()
    inv = {'schema': 'cps.source-inventory.cells.v2', 'case_id': 'FIXTURE01', 'family_id': 'FIXTURE01',
           'representation_profile': 'cached-cell-raw-scalar-text.v2',
           'source': {'source_id': 'S', 'format': 'cached_xls', 'bytes': 1024, 'sha256': fake_sha,
                      'adoption_status': adoption, 'adoption_basis': 'Invented fixture; no real contract.',
                      'reader': {'name': 'invented', 'version': '0', 'biff_format': None, 'formula_expressions_available': False},
                      'carrier_source': {'kind': 'cached_xls', 'path': 'X:\\Fixtures\\invented\\fixture-contract.xls',
                                         'sha256': fake_sha, 'views': vws}},
           'sheets': sheets,
           'views': [dict(v, image={'file': f"view_{v['id']:02d}.png", 'bytes': 1, 'sha256': fake_sha}) for v in vws],
           'external_links': [], 'cells': cells,
           'context_facts': [{'ref': 'context:case_identity', 'namespace': 'cps.internal_case_id', 'value': 'FIXTURE01',
                              'basis': 'Invented selected case identity for route testing.',
                              'authority_pins': [{'label': 'invented', 'sha256': fake_sha}]}],
           'limitations': ['Invented fixture inventory for adapter route tests only.']}
    raw = serialize(inv).encode('utf-8')
    return inv, raw


def nn(refs, t, rb):
    return {'refs': refs, 'transformation': t, 'role_basis': rb}


def nul(reason):
    return {'reason': reason}


def raw(desc=(), unit=(), qty=(), price=(), amount=(), remarks=(), reasons=None):
    reasons = reasons or {}
    out = {}
    for k, v in zip(('description', 'unit', 'quantity', 'unit_price', 'amount', 'remarks'), (desc, unit, qty, price, amount, remarks)):
        out[k] = {'refs': list(v), 'reason_if_empty': None if v else reasons.get(k, 'no source cell in this role for this item')}
    return out


def item(iid, role, group, status, values, proofs, rawrefs, anchors, reasons=()):
    return {'id': iid, 'role': role, 'group_id': group, 'status': status, 'values': values,
            'proofs': {c: proofs[c] for c in COLS}, 'raw_refs': rawrefs, 'anchor_refs': anchors, 'review_reasons': list(reasons)}


NULL_REASONS = {
    'A': 'Item is not inside an explicitly identified panel group.',
    'B': 'Item is not inside an explicitly identified panel group, so no group specification applies.',
    'C': 'No supplied object is identified.',
    'D': 'No separable technical specification text in this item.',
    'E': 'No unit cell for this row.',
    'F': 'No quantity cell for this row.',
    'I': 'No source-supported model role in this item.',
    'J': 'No source-supported brand role in this item.',
    'K': 'Supplier role is project-level and not asserted on analysis composition rows.',
    'L': 'Engineering identity is not asserted on analysis composition rows.',
    'M': 'Ordering-customer role is project-level and not asserted on analysis composition rows.',
    'N': 'Using-customer role is project-level and not asserted on analysis composition rows.',
    'O': 'Required date is project-level and not asserted on analysis composition rows.',
    'P': 'No explicit required/ordering quantity is stated for this item; F is not copied.',
}


def base_proofs(**over):
    p = {c: nul(NULL_REASONS.get(c, 'n/a')) for c in COLS}
    p['G'] = nul('Procurement unit price is blank at the 未填 stage.')
    p['H'] = nul('Procurement extended price is blank at the 未填 stage.')
    p['Q'] = nul('Source adoption is unverified, so no accepted contract rate can be asserted.')
    p['L'] = nn(['context:case_identity'], 'copied selected internal case identity', 'selected internal case identity, not a printed code')
    p.update(over)
    return p


PROJECT = dict(K='示例電機行', M='示例自來水處', N='示例淨水場', O='2026-12-01')


def project_proofs():
    S = 'cell:S1!'
    return dict(K=nn([S + 'A15'], 'text after label', 'explicit project-level supplier label'),
                M=nn([S + 'A13'], 'text after label', 'explicit project-level ordering-customer label'),
                N=nn([S + 'A14'], 'text after label', 'explicit project-level using-unit label'),
                O=nn([S + 'A16'], 'text after label', 'explicit project-level required-date label'))


def vals(**kw):
    v = [None] * 17
    v[11] = 'FIXTURE01'
    for k, x in PROJECT.items():
        v[COLS.index(k)] = x
    for k, x in kw.items():
        v[COLS.index(k)] = x
    return v


def valid_response(inv_sha):
    S = 'cell:S1!'
    T2 = 'cell:S2!'
    items = [
        item('R001', 'demand', 'G1', 'research_draft',
             vals(A='示例控制盤', B='W600×H800×D300', C='電磁接觸器', D='AC110V 附端子蓋', E='只', F=2),
             base_proofs(A=nn([S + 'B3'], 'copied group heading', 'contractual panel group heading owns items 1-3'),
                         B=nn([S + 'C3'], 'copied group specification', 'dimension printed on the group heading row'),
                         C=nn([S + 'B4'], 'span after leading code', 'identifying product noun'),
                         D=nn([S + 'B4', S + 'B5'], 'rating span plus continuation; newline to U+0020', 'rating and included accessory'),
                         E=nn([S + 'C4'], 'copied', 'unit column'), F=nn([S + 'D4'], 'copied', 'quantity column'), **project_proofs()),
             raw(desc=[S + 'B4', S + 'B5'], unit=[S + 'C4'], qty=[S + 'D4'], price=[S + 'E4'], amount=[S + 'F4'],
                 reasons={'remarks': 'remarks cell is an explicit empty string'}),
             [S + 'A4'], ['Leading token QX-620 has no proven model role.']),
        item('R002', 'demand', 'G1', 'research_draft', vals(A='示例控制盤', B='W600×H800×D300', C='三段式選擇開關', E='個', F=3),
             base_proofs(A=nn([S + 'B3'], 'copied group heading', 'group heading'), B=nn([S + 'C3'], 'copied group specification', 'group heading dimension'),
                         C=nn([S + 'B6'], 'copied', 'functional switch name'),
                         E=nn([S + 'C6'], 'copied', 'unit column'), F=nn([S + 'D6'], 'copied', 'quantity column'), **project_proofs()),
             raw(desc=[S + 'B6'], unit=[S + 'C6'], qty=[S + 'D6'], price=[S + 'E6'], amount=[S + 'F6'], remarks=[S + 'G6']),
             [S + 'A6']),
        item('R003', 'demand', 'G1', 'research_draft', vals(A='示例控制盤', B='W600×H800×D300', C='盤體組立費', E='式', F=1),
             base_proofs(A=nn([S + 'B3'], 'copied group heading', 'group heading'), B=nn([S + 'C3'], 'copied group specification', 'group heading dimension'),
                         C=nn([S + 'B7'], 'copied', 'service line'),
                         E=nn([S + 'C7'], 'copied', 'unit column'), F=nn([S + 'D7'], 'copied', 'quantity column'), **project_proofs()),
             raw(desc=[S + 'B7'], unit=[S + 'C7'], qty=[S + 'D7'], price=[S + 'E7'], amount=[S + 'F7'], remarks=[S + 'G7']),
             [S + 'A7']),
        item('R004', 'demand', None, 'research_draft', vals(C='備用接點', E='只', F=0),
             base_proofs(C=nn([S + 'B8'], 'copied', 'product noun'), E=nn([S + 'C8'], 'copied', 'unit column'),
                         F=nn([S + 'D8'], 'copied numeric zero', 'quantity column; real zero'), **project_proofs()),
             raw(desc=[S + 'B8'], unit=[S + 'C8'], qty=[S + 'D8'], price=[S + 'E8'], amount=[S + 'F8']),
             [S + 'A8']),
        item('R005', 'demand', None, 'research_draft', vals(C='溫度計', E='支', F=1),
             base_proofs(C=nn([S + 'B11'], 'copied', 'product noun'), E=nn([S + 'C11'], 'copied', 'unit column'),
                         F=nn([S + 'D11'], 'copied', 'quantity column'), **project_proofs()),
             raw(desc=[S + 'B11'], unit=[S + 'C11'], qty=[S + 'D11'], price=[S + 'E11'], amount=[S + 'F11'], remarks=[S + 'G11']),
             [S + 'A11']),
        item('R006', 'demand', None, 'research_draft', vals(C='流量計', E='台', F=1, I='FM-100', J='示例儀器', P=2),
             base_proofs(C=nn([S + 'B12'], 'copied', 'product noun'), E=nn([S + 'C12'], 'copied', 'unit column'),
                         F=nn([S + 'D12'], 'copied', 'quantity column'),
                         I=nn([S + 'G12'], 'text after 型號 label', 'explicit model label'),
                         J=nn([S + 'G12'], 'text after 廠牌 label', 'explicit brand label'),
                         P=nn([S + 'B17'], 'copied', 'explicit required-quantity label in A17'), **project_proofs()),
             raw(desc=[S + 'B12'], unit=[S + 'C12'], qty=[S + 'D12'], price=[S + 'E12'], amount=[S + 'F12'], remarks=[S + 'G12']),
             [S + 'A12']),
        item('R007', 'demand', None, 'held', vals(E='式', F=1),
             base_proofs(C=nul('Only a document pointer; no supplied object is identified.'),
                         E=nn([S + 'C18'], 'copied', 'unit column'), F=nn([S + 'D18'], 'copied', 'quantity column'), **project_proofs()),
             raw(desc=[S + 'B18'], unit=[S + 'C18'], qty=[S + 'D18']), [S + 'A18'],
             ['Candidate row names only a specification document; supplied object unresolved.']),
        item('C001', 'analysis_component', None, 'research_draft', [None, None, '組立工資', None, '工', 2] + [None] * 11,
             base_proofs(C=nn([T2 + 'A3'], 'copied', 'analysis component name'), E=nn([T2 + 'B3'], 'copied', 'unit'),
                         F=nn([T2 + 'C3'], 'copied', 'per-unit quantity'), L=nul(NULL_REASONS['L'])),
             raw(desc=[T2 + 'A3'], unit=[T2 + 'B3'], qty=[T2 + 'C3'], remarks=[T2 + 'D3']), [T2 + 'A3']),
        item('C002', 'analysis_component', None, 'research_draft', [None, None, '配線材料'] + [None] * 14,
             base_proofs(C=nn([T2 + 'A4'], 'copied', 'analysis component name'),
                         E=nul('Per-unit basis unit is carried by the component link, not as a demand unit.'),
                         F=nul('Per-unit basis quantity is carried by the component link; no purchase quantity.'),
                         L=nul(NULL_REASONS['L'])),
             raw(desc=[T2 + 'A4'], unit=[T2 + 'B4'], qty=[T2 + 'C4'], remarks=[T2 + 'D4']), [T2 + 'A4']),
    ]
    # Ensure every column except G/H/Q has a nonnull somewhere and every column has a null somewhere.
    groups = [{'id': 'G1', 'name': '示例控制盤', 'specification': 'W600×H800×D300', 'relationship': 'contractual_group',
               'anchor_refs': [S + 'A3'], 'name_refs': [S + 'B3'], 'specification_refs': [S + 'C3'], 'quantity_basis': 'one contractual group; physical enclosure count unproven',
               'limitations': ['Physical enclosure ownership not established.']}]
    links = [{'component_id': 'C001', 'parent_id': 'R003', 'status': 'supported', 'basis_quantity': 2,
              'basis_raw_ref': T2 + 'C3', 'basis_unit_ref': T2 + 'B3', 'refs': [T2 + 'D3'], 'reason': 'analysis heading names item 3 per 式'},
             {'component_id': 'C002', 'parent_id': 'R003', 'status': 'supported', 'basis_quantity': 1,
              'basis_raw_ref': T2 + 'C4', 'basis_unit_ref': T2 + 'B4', 'refs': [], 'reason': 'analysis heading names item 3 per 式'}]
    roles = [
        {'role': 'header', 'refs': [S + 'A1'] + [S + c + '2' for c in 'ABCDEFG'], 'reason': 'title and column headers'},
        {'role': 'section', 'refs': [S + 'A3', S + 'B3', S + 'C3'], 'reason': 'section number, contractual group heading and its dimension'},
        {'role': 'item_identifier', 'refs': [S + 'A4', S + 'A6', S + 'A7', S + 'A8', S + 'A11', S + 'A12', S + 'A18'], 'reason': 'item numbers'},
        {'role': 'demand_content', 'refs': [S + x for x in ['B4', 'C4', 'D4', 'E4', 'F4', 'B5', 'B6', 'C6', 'D6', 'E6', 'F6',
                                                          'G6', 'B7', 'C7', 'D7', 'E7', 'F7', 'G7', 'B8', 'C8', 'D8', 'E8', 'F8',
                                                          'B11', 'C11', 'D11', 'E11', 'F11', 'G11', 'B12', 'C12', 'D12', 'E12', 'F12', 'G12',
                                                          'B18', 'C18', 'D18']], 'reason': 'item description, unit, quantity, price, amount and remarks cells'},
        {'role': 'commercial_note', 'refs': [S + 'B10'], 'reason': 'standalone freight note outside any item'},
        {'role': 'financial_summary', 'refs': [S + 'B9', S + 'F9'], 'reason': 'subtotal'},
        {'role': 'header', 'refs': [S + 'A13', S + 'A14', S + 'A15', S + 'A16', S + 'A17', S + 'B17', S + 'C17', S + 'D17'], 'reason': 'project information block'},
        {'role': 'unresolved', 'refs': [S + 'C16', S + 'D16', S + 'E16'], 'reason': 'date serial, boolean and error states without a supported role'},
        {'role': 'header', 'refs': [T2 + 'A1', T2 + 'A2', T2 + 'B2', T2 + 'C2', T2 + 'D2'], 'reason': 'analysis title and headers'},
        {'role': 'analysis_content', 'refs': [T2 + x for x in ['A3', 'B3', 'C3', 'D3', 'A4', 'B4', 'C4', 'D4']], 'reason': 'per-unit composition rows'},
    ]
    return {'schema': 'cps.semantic-source-refs.v2', 'case_id': 'FIXTURE01', 'family_id': 'FIXTURE01',
            'inventory_sha256': inv_sha, 'status': 'partial', 'groups': groups, 'items': items,
            'component_links': links, 'source_roles': roles, 'limitations': ['Invented fixture response.']}


def mutations(base):
    """(name, expected violation code, mutate(response)->response or raw bytes)."""
    S = 'cell:S1!'
    def m(f):
        def g(r):
            r = copy.deepcopy(r)
            f(r)
            return r
        return g
    def item(r, i):
        return next(x for x in r['items'] if x['id'] == i)
    cases = [
        ('unknown_ref', 'UNKNOWN_CELL_REF', m(lambda r: item(r, 'R002')['proofs']['C'].update(refs=[S + 'B99']))),
        ('wrong_case_ref', 'UNKNOWN_CELL_REF', m(lambda r: item(r, 'R002')['proofs']['C'].update(refs=['cell:s1!b6']))),
        ('wrong_sheet_index_ref', 'UNKNOWN_CELL_REF', m(lambda r: item(r, 'R002')['proofs']['C'].update(refs=['cell:S9!B6']))),
        ('duplicate_ref', 'DUPLICATE_OR_NONSTRING_REF', m(lambda r: item(r, 'R001')['proofs']['D'].update(refs=[S + 'B4', S + 'B4']))),
        ('wrong_inventory_hash', 'INVENTORY_HASH_MISMATCH', m(lambda r: r.update(inventory_sha256='0' * 64))),
        ('wrong_case', 'CASE_ID_MISMATCH', m(lambda r: r.update(case_id='FIXTURE02'))),
        ('wrong_family', 'FAMILY_ID_MISMATCH', m(lambda r: r.update(family_id='FIXTURE02'))),
        ('F_as_text', 'FINITE_SAFE_NUMBER_REQUIRED', m(lambda r: item(r, 'R002')['values'].__setitem__(5, '3'))),
        ('D_as_number', 'STRING_REQUIRED', m(lambda r: item(r, 'R001')['values'].__setitem__(3, 110))),
        ('G_nonnull', 'PURCHASE_PRICE_MUST_BE_BLANK', m(lambda r: (item(r, 'R002')['values'].__setitem__(6, 120.5), item(r, 'R002')['proofs'].update(G={'refs': [S + 'E6'], 'transformation': 't', 'role_basis': 'b'})))),
        ('item_partial', 'ITEM_STATUS', m(lambda r: item(r, 'R002').update(status='partial'))),
        ('null_C_not_held', 'NULL_C_REQUIRES_HELD', m(lambda r: item(r, 'R007').update(status='research_draft'))),
        ('held_without_reason', 'HELD_REASON_REQUIRED', m(lambda r: item(r, 'R007').update(review_reasons=[]))),
        ('A_without_group', 'UNGROUPED_AB_MUST_BE_BLANK', m(lambda r: item(r, 'R002').update(group_id=None))),
        ('A_not_group_name', 'A_MUST_EQUAL_GROUP_NAME', m(lambda r: item(r, 'R002')['values'].__setitem__(0, '示例控制盤一'))),
        ('B_not_group_spec', 'B_MUST_EQUAL_GROUP_SPECIFICATION', m(lambda r: (item(r, 'R002')['values'].__setitem__(1, '600x800'), item(r, 'R002')['proofs'].update(B={'refs': [S + 'B3'], 'transformation': 't', 'role_basis': 'b'})))),
        ('unknown_group', 'UNKNOWN_GROUP_ID', m(lambda r: item(r, 'R002').update(group_id='G9'))),
        ('E_not_raw_unit', 'SOURCE_UNIT_MISMATCH', m(lambda r: item(r, 'R002')['values'].__setitem__(4, '只'))),
        ('F_not_raw_quantity', 'SOURCE_QUANTITY_MISMATCH', m(lambda r: item(r, 'R002')['values'].__setitem__(5, 4))),
        ('F_proof_other_cell', 'F_PROOF_MUST_BE_RAW_QUANTITY_CELL', m(lambda r: item(r, 'R003')['proofs']['F'].update(refs=[S + 'D12']))),
        ('F_proof_text_cell', 'NONNUMERIC_SOURCE_TEXT_FIELD_MUST_BE_NULL', m(lambda r: item(r, 'R002')['proofs']['F'].update(refs=[S + 'B6']))),
        ('Q_unverified', 'Q_REQUIRES_VERIFIED_ADOPTION', m(lambda r: (item(r, 'R006')['values'].__setitem__(16, 50000), item(r, 'R006')['proofs'].update(Q={'refs': [S + 'E12'], 'transformation': 'copied', 'role_basis': 'unit price column'})))),
        ('formula_like_D', 'FORMULA_LIKE_STRING_WHOLE_OUTPUT_HELD', m(lambda r: (item(r, 'R005')['values'].__setitem__(3, '-20~60℃'), item(r, 'R005')['proofs'].update(D={'refs': [S + 'G11'], 'transformation': 'copied remark', 'role_basis': 'temperature range'})))),
        ('raw_blank_cell', 'EMPTY_CELL_CITED_IN_RAW', m(lambda r: item(r, 'R001')['raw_refs'].update(remarks={'refs': [S + 'G4'], 'reason_if_empty': None}))),
        ('raw_covered_cell', 'EMPTY_CELL_CITED_IN_RAW', m(lambda r: item(r, 'R005')['raw_refs'].update(remarks={'refs': [S + 'G11', S + 'B13'], 'reason_if_empty': None}))),
        ('raw_date_cell', 'SOURCE_CELL_NOT_CARRIABLE_IN_RAW', m(lambda r: item(r, 'R005')['raw_refs'].update(remarks={'refs': [S + 'C16'], 'reason_if_empty': None}))),
        ('raw_unit_two_cells', 'SINGLE_CELL_RAW_FIELD', m(lambda r: item(r, 'R002')['raw_refs'].update(unit={'refs': [S + 'C6', S + 'C7'], 'reason_if_empty': None}))),
        ('empty_raw_without_reason', 'EMPTY_SELECTION_REASON_REQUIRED', m(lambda r: item(r, 'R004')['raw_refs'].update(remarks={'refs': [], 'reason_if_empty': None}))),
        ('reason_with_refs', 'REASON_ONLY_FOR_EMPTY_SELECTION', m(lambda r: item(r, 'R002')['raw_refs'].update(remarks={'refs': [S + 'G6'], 'reason_if_empty': 'x'}))),
        ('missing_role_basis', 'NONNULL_PROOF_REQUIRED', m(lambda r: item(r, 'R002')['proofs'].update(C={'refs': [S + 'B6'], 'transformation': 'copied'}))),
        ('null_with_nonnull_proof', 'NULL_PROOF_REQUIRED', m(lambda r: item(r, 'R002')['proofs'].update(D={'refs': [S + 'B6'], 'transformation': 't', 'role_basis': 'b'}))),
        ('nonnull_with_null_proof', 'NONNULL_PROOF_REQUIRED', m(lambda r: item(r, 'R002')['proofs'].update(C={'reason': 'x'}))),
        ('context_only_C', 'CONTEXT_ONLY_PROOF_UNREPRESENTABLE', m(lambda r: item(r, 'R002')['proofs'].update(C={'refs': ['context:case_identity'], 'transformation': 't', 'role_basis': 'b'}))),
        ('unknown_context', 'UNKNOWN_CONTEXT_REF', m(lambda r: item(r, 'R002')['proofs'].update(L={'refs': ['context:other'], 'transformation': 't', 'role_basis': 'b'}))),
        ('proof_spans_sheets', 'LOCATION_SPANS_SHEETS', m(lambda r: item(r, 'R003')['proofs']['C'].update(refs=[S + 'B7', 'cell:S2!A1']))),
        ('proof_blank_cell', 'EMPTY_CELL_CITED_IN_PROOF', m(lambda r: item(r, 'R002')['proofs']['C'].update(refs=[S + 'B6', S + 'G8']))),
        ('anchor_other_sheet', 'LOCATION_SPANS_SHEETS', m(lambda r: item(r, 'R002').update(anchor_refs=['cell:S2!A1']))),
        ('component_link_held', 'COMPONENT_LINK_HELD_WHOLE_EXPORT_HELD', m(lambda r: r['component_links'][1].update(status='held', parent_id=None, basis_quantity=None, basis_raw_ref=None, basis_unit_ref=None))),
        ('component_basis_mismatch', 'BASIS_LITERAL_MISMATCH', m(lambda r: r['component_links'][0].update(basis_quantity=3))),
        ('component_parent_is_component', 'COMPONENT_PARENT_MUST_BE_DEMAND', m(lambda r: r['component_links'][0].update(parent_id='C002'))),
        ('component_without_link', 'COMPONENT_LINK_REQUIRED', m(lambda r: r['component_links'].pop())),
        ('unclassified_content', 'UNCLASSIFIED_CONTENT_CELLS', m(lambda r: r['source_roles'][4].update(refs=[S + 'G6']))),
        ('duplicate_primary_role', 'DUPLICATE_PRIMARY_ROLE', m(lambda r: r['source_roles'][4]['refs'].append(S + 'B4'))),
        ('role_for_blank', 'ROLE_FOR_EMPTY_CELL', m(lambda r: r['source_roles'][4]['refs'].append(S + 'G8'))),
        ('role_for_explicit_empty', 'ROLE_FOR_EMPTY_CELL', m(lambda r: r['source_roles'][4]['refs'].append(S + 'G4'))),
        ('duplicate_item_id', 'DUPLICATE_ID', m(lambda r: item(r, 'R002').update(id='R001'))),
        ('bad_id', 'ID_REQUIRED', m(lambda r: item(r, 'R002').update(id='R 002'))),
        ('extra_key', 'EXACT_KEYS_REQUIRED', m(lambda r: item(r, 'R002').update(note='x'))),
        ('control_char_C', 'CONTROL_CHARACTER_UNREPRESENTABLE', m(lambda r: item(r, 'R002')['values'].__setitem__(2, '三段式\x0b選擇開關'))),
        ('blank_C', 'NONBLANK_STRING_REQUIRED', m(lambda r: item(r, 'R002')['values'].__setitem__(2, '\u3000'))),
        ('P_as_text', 'FINITE_SAFE_NUMBER_REQUIRED', m(lambda r: item(r, 'R006')['values'].__setitem__(15, '2'))),
        ('response_status_bad', 'RESPONSE_STATUS', m(lambda r: r.update(status='approved'))),
        ('view_unaccounted', 'VIEW_SCOPE_UNACCOUNTED', m(lambda r: (r['items'].__delitem__(slice(7, 9)), r['component_links'].clear(),
                                                                    [x.update(role='demand_content') for x in r['source_roles'] if x['role'] == 'analysis_content'],
                                                                    [x.update(role='demand_content') for x in r['source_roles'] if x['refs'][0] == 'cell:S2!A1']))),
    ]
    cases += [
        ('dropped_item', 'CONTENT_CELL_NOT_USED_BY_ANY_ITEM', m(lambda r: r['items'].pop(1))),
        ('desc_not_row_major', 'RAW_STREAM_NOT_ROW_MAJOR', m(lambda r: item(r, 'R001')['raw_refs'].update(description={'refs': [S + 'B5', S + 'B4'], 'reason_if_empty': None}))),
        ('desc_includes_unit', 'DESCRIPTION_INCLUDES_EXCLUDED_CELL', m(lambda r: item(r, 'R002')['raw_refs'].update(description={'refs': [S + 'B6', S + 'C6'], 'reason_if_empty': None}))),
        ('anchor_not_first_row', 'ANCHOR_NOT_ON_FIRST_ROW', m(lambda r: item(r, 'R001').update(anchor_refs=[S + 'G5']))),
        ('anchor_shared', 'ANCHOR_SHARED_ACROSS_ITEMS', m(lambda r: item(r, 'R002').update(anchor_refs=[S + 'A4']))),
        ('anchor_on_other_description', 'ANCHOR_SHARED_ACROSS_ITEMS', m(lambda r: item(r, 'R004').update(anchor_refs=[S + 'B6']))),
        ('basis_unit_number_cell', 'BASIS_UNIT_MUST_BE_TEXT_CELL', m(lambda r: r['component_links'][0].update(basis_unit_ref='cell:S2!C3'))),
        ('desc_shared', 'DESCRIPTION_CELL_SHARED_ACROSS_ITEMS', m(lambda r: item(r, 'R002')['raw_refs'].update(description={'refs': [S + 'B4', S + 'B6'], 'reason_if_empty': None}))),
        ('group_id_list', 'UNKNOWN_GROUP_ID', m(lambda r: item(r, 'R002').update(group_id=[]))),
        ('huge_int_F', 'UNSAFE_INTEGER', m(lambda r: item(r, 'R002')['values'].__setitem__(5, 10 ** 400))),
        ('date_cell_proof_O', 'SOURCE_CELL_NOT_CARRIABLE_IN_PROOF', m(lambda r: item(r, 'R005')['proofs']['O'].update(refs=[S + 'C16']))),
        ('long_packed_transformation', 'WRITER_WOULD_REJECT_STRING_REQUIRED', m(lambda r: item(r, 'R002')['proofs']['C'].update(transformation='x' * 16000, role_basis='y' * 16000))),
        ('escaped_expansion_transformation', 'WRITER_WOULD_REJECT_STRING_REQUIRED', m(lambda r: item(r, 'R002')['proofs']['C'].update(transformation='"\n' * 9000))),
        ('group_limitations_501', 'TOO_MANY_GROUP_LIMITATIONS_FOR_WRITER', m(lambda r: r['groups'][0].update(limitations=['limit'] * 501))),
    ]
    raws = [('duplicate_json_key', 'DUPLICATE_JSON_KEY', lambda b: b.replace(b'"status": "partial"', b'"status": "partial", "status": "partial"', 1)),
            ('nonfinite_number', 'NONFINITE_NUMBER', lambda b: b.replace(b'"basis_quantity": 2', b'"basis_quantity": NaN', 1))]
    return cases, raws


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inv, inv_raw = build_inventory('unverified')
    (OUT / 'fixture_inventory.json').write_bytes(inv_raw)
    inv_v, inv_v_raw = build_inventory('verified')
    (OUT / 'fixture_inventory_verified.json').write_bytes(inv_v_raw)
    base = valid_response(hashlib.sha256(inv_raw).hexdigest())
    enc = lambda r: (json.dumps(r, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
    (OUT / 'valid_response.json').write_bytes(enc(base))
    # verified adoption: Q may be asserted from the unit-price cell
    q = copy.deepcopy(base)
    q['inventory_sha256'] = hashlib.sha256(inv_v_raw).hexdigest()
    r6 = next(x for x in q['items'] if x['id'] == 'R006')
    r6['values'][16] = 50000
    r6['proofs']['Q'] = {'refs': ['cell:S1!E12'], 'transformation': 'copied', 'role_basis': 'accepted unit rate column (invented verified adoption)'}
    (OUT / 'valid_response_verified_Q.json').write_bytes(enc(q))
    cases, raws = mutations(base)
    index = []
    for name, code, f in cases:
        (OUT / f'mut_{name}.json').write_bytes(enc(f(base)))
        index.append({'name': name, 'file': f'mut_{name}.json', 'expected_code': code})
    for name, code, f in raws:
        b = f(enc(base))
        assert b != enc(base), name
        (OUT / f'mut_{name}.json').write_bytes(b)
        index.append({'name': name, 'file': f'mut_{name}.json', 'expected_code': code})
    def var(name, code, inv_kw, mutate):
        _, vraw = build_inventory('unverified', **inv_kw)
        (OUT / f'inv_{name}.json').write_bytes(vraw)
        rr = copy.deepcopy(base)
        rr['inventory_sha256'] = hashlib.sha256(vraw).hexdigest()
        mutate(rr)
        (OUT / f'mut_{name}.json').write_bytes(enc(rr))
        index.append({'name': name, 'file': f'mut_{name}.json', 'inventory': f'inv_{name}.json', 'expected_code': code})

    def big_roles(r):
        r['source_roles'].append({'role': 'unresolved', 'refs': [f'cell:S3!{letters(c)}{rr}' for rr in range(1, 52) for c in range(1, 101)],
                                  'reason': 'resource statistics sheet not used for demands'})
    var('unicode_digit_quantity', 'NONNUMERIC_RAW_QUANTITY_FIELD_MUST_BE_NULL', {'overrides': {(6, 'D'): (T, '３', False)}}, lambda r: None)
    var('too_many_nonitems', 'WRITER_WOULD_REJECT_NONITEMS_REQUIRED', {'extra_sheet': True}, big_roles)
    var('long_header_census', 'WRITER_WOULD_REJECT_STRING_REQUIRED', {'overrides': {(1, 'A'): (T, '題' * 29990, False)}}, lambda r: None)
    (OUT / 'MUTATIONS.json').write_text(json.dumps({'expected_canonical': EXPECT_CANON, 'mutations': index}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'mutations': len(index)}))


if __name__ == '__main__':
    main()
