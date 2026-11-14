"""Invented route fixtures for candidates 046b-046f. No project data: every name/value is made up.

Writes: fixture inventory (unverified adoption), verified- and partial-adoption variants, one valid
response, a job-input response (046f, owner decision O13 / FIELD_ROLES R48: L, M and N cite
only job-input context facts), and single-defect mutations with the violation code each must
trigger. Route v4: the inventory carries the job-input and company-resource context facts
(context:case_identity, customer_name, project_name, company_name, glossary, brand_table) with
INVENTED values; they are not the owner-reviewed company resources.
Route v4.1 (R52/R54/R56/R57, O16) adds valid responses for the relaxations: C null with status
research_draft (R003 with a review reason, component C001 without one), Q under unverified and
partial adoption, all relaxations together with the job inputs, and a one-member
physical_enclosure group. The v4 mutations null_C_not_held and Q_unverified are now valid
responses and are no longer mutations.
Route v4.2 (FIELD_ROLES R48, R56, R58; 046f review S12) applies its policy checks to 046f job packets
only, so the fixtures come in two kinds:
  - fixture_inventory.json (and the verified/partial/defect variants): a pre-046f mechanics fixture with
    context:case_identity and the company resources but no job-input facts (no context:customer_name or
    context:project_name); the base response keeps its 046b-046e mechanics (K/M/N/O from labels, P from a
    cell, a three-member contractual group) and the route reports policy_checks not_applied;
  - fixture_inventory_jobs.json: a 046f job packet (contract-like source, all six context facts); the
    job-input response follows R48/R56 (L, M, N from the job inputs on every item, K, O, P null, one
    one-member physical_enclosure group) and the v4.2 mutations test each new check.
Route v4.3 (candidate 046g, FIELD_ROLES R59) adds scoped packets: fixture_inventory_scoped.json is an invented
材料清單 job packet whose workbook has four sheets, of which only the bill sheet (index 2) is in scope; it carries
context:scope (end row 7, one linked analysis block on the scoped-out analysis sheet). Variants: no linked block (no
warning), end row 6 (the boundary: row 6 is cited and passes) and one v43 mutation per new check; 046g pass 2 adds the
R59_SCOPE_FACT_CITED mutations (context:scope cited in a proof, raw selection, anchor or group) and two controls on the
job packet without the fact (noscope_*), which keep their v4.2 codes. The scope-stage tests
(run_scope_stage_tests.py) import SCOPED_BILL, scoped_job_facts and scoped_response from this module.
Route v4.4 (candidate 046i, owner decision O72; FIELD_ROLES R59 items 2 and 9) adds, after every earlier fixture (whose
bytes are unchanged): fixture_inventory_scoped_nototal.json (the scoped fixture's bill sheet without its 合計 cell, fact
BILL1.NOTOTAL.v1 with end row 10, the last content row; SYNTHETIC_ALLOCATION_CASES A50) and fixture_inventory_whole.json
(a whole-workbook packet, fact BILL1.NOHEADER.v1: a priced list with four of the six BILL1 labels, a memo sheet and an
empty sheet out of scope; A51), their valid responses, two citing variants and one v44 mutation per new check.
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
    (11, 'D'): (N, 1.0, False), (11, 'E'): (N, 1e-05, False), (11, 'F'): (N, 1e-05, True), (11, 'G'): (T, '0~100℃', False),
    (12, 'A'): (T, '6', False), (12, 'B'): (T, '流量計', False), (12, 'C'): (T, '台', False),
    (12, 'D'): (N, 1.0, False), (12, 'E'): (N, 50000.0, False), (12, 'F'): (N, 50000.0, True),
    (12, 'G'): (T, '廠牌：示例儀器 型號：FM-100', False),
    (13, 'A'): (T, '訂購客戶：示例自來水處', False),
    (14, 'A'): (T, '使用單位：示例淨水場', False),
    (15, 'A'): (T, '訂購廠商：示例電機行', False),
    (16, 'A'): (T, '需要日期：2026-12-01', False), (16, 'C'): ('date', 46357.0, False),
    (16, 'D'): ('boolean', True, False), (16, 'E'): ('error', '#DIV/0!', True),
    (17, 'A'): (T, '流量計需要數量', False), (17, 'B'): (N, 2.0, False), (17, 'C'): (T, '0', False), (17, 'D'): (N, 0.0, False),
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


def build_inventory(adoption, overrides=None, extra_sheet=False, job_inputs=False, drop_facts=()):
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
    job_sha = hashlib.sha256(b'invented fixture per-job config').hexdigest()
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
           'context_facts': [f for f in [{'ref': 'context:case_identity', 'namespace': 'cps.internal_case_id', 'value': 'FIXTURE01',
                                          'basis': 'Invented selected case identity for route testing.',
                                          'authority_pins': [{'label': 'invented', 'sha256': fake_sha}]}]
                             + (JOB_INPUTS(job_sha) if job_inputs else []) + RESOURCE_FACTS() if f['ref'] not in drop_facts],
           'limitations': ['Invented fixture inventory for adapter route tests only.'
                           + (' 046f job packet: carries the job-input facts (route v4.2 policy checks apply).' if job_inputs else
                              ' Pre-046f mechanics fixture: no job-input facts (route v4.2 policy checks do not apply).')]}
    raw = serialize(inv).encode('utf-8')
    return inv, raw


# 046f context facts (FIELD_ROLES R48, R58). INVENTED values for route testing only.
CUSTOMER, PROJECT_NAME, COMPANY = '示例自來水事業處', '示例淨水場控制盤更新', '示例機電股份有限公司'
GLOSSARY = json.dumps({'schema': 'cps.company-glossary.v1', 'invented': True, 'generic_prefix_words': ['產品'],
                       'enclosure_word': '箱體', 'abbreviations': [{'device': '電磁接觸器', 'abbreviation': 'XM'},
                                                                 {'device': '選擇開關', 'abbreviation': 'XS'}]},
                      ensure_ascii=False, sort_keys=True)
BRAND_TABLE = json.dumps({'schema': 'cps.company-brand-table.v1', 'invented': True,
                          'entries': [{'device': '電磁接觸器', 'rating_band': 'all ratings', 'brand': '示例甲牌', 'model': 'XM-10'}]},
                         ensure_ascii=False, sort_keys=True)


def _fact(name, namespace, value, basis, label, pin):
    return {'ref': 'context:' + name, 'namespace': namespace, 'value': value, 'basis': basis,
            'authority_pins': [{'label': label, 'sha256': pin}]}


def JOB_INPUTS(job_sha):
    return [_fact('customer_name', 'cps.job_input.customer_full_name', CUSTOMER,
                  'Invented job input: customer full name supplied with the job (O13, R48).', 'invented per-job config', job_sha),
            _fact('project_name', 'cps.job_input.project_short_name', PROJECT_NAME,
                  'Invented job input: project short name supplied with the job (O13, R48).', 'invented per-job config', job_sha)]


def RESOURCE_FACTS():
    fact = _fact
    res = lambda v: hashlib.sha256(v.encode('utf-8')).hexdigest()
    return [fact('company_name', 'cps.company_resource.company_name', COMPANY,
                 'Invented company name resource (O16, R56, R58).', 'invented company resource', res(COMPANY)),
            fact('glossary', 'cps.company_resource.glossary', GLOSSARY,
                 'Invented abbreviation glossary resource (O15, R52, R58); not the owner-reviewed glossary.', 'invented company resource', res(GLOSSARY)),
            fact('brand_table', 'cps.company_resource.brand_table', BRAND_TABLE,
                 'Invented brand/model table resource (O14, R55, R58); not the owner-reviewed table.', 'invented company resource', res(BRAND_TABLE))]


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
    return dict(K=nn([S + 'A15'], 'text after label', 'explicit project-level ordering-supplier label 訂購廠商'),
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
                         E=nn([S + 'C4'], 'copied', 'unit column'), F=nn([S + 'D4'], 'copied', 'quantity column'),
                         I=nul('Leading token QX-620 has no proven model role; it is kept in raw text and the review reason.'), **project_proofs()),
             raw(desc=[S + 'B4', S + 'B5'], unit=[S + 'C4'], qty=[S + 'D4'], price=[S + 'E4'], amount=[S + 'F4'],
                 reasons={'remarks': 'remarks cell is an explicit empty string'}),
             [S + 'A4'], ['Leading token QX-620 has no proven model role.']),
        item('R002', 'demand', 'G1', 'research_draft', vals(A='示例控制盤', B='W600×H800×D300', C='三段式選擇開關', E='個', F=3),
             base_proofs(A=nn([S + 'B3'], 'copied group heading', 'group heading'), B=nn([S + 'C3'], 'copied group specification', 'group heading dimension'),
                         C=nn([S + 'B6'], 'copied', 'functional switch name'),
                         D=nul('No technical attribute in the item; the functional count 三段式 is part of the name (R2); the remark is a financial annotation (R1).'),
                         E=nn([S + 'C6'], 'copied', 'unit column'), F=nn([S + 'D6'], 'copied', 'quantity column'), **project_proofs()),
             raw(desc=[S + 'B6'], unit=[S + 'C6'], qty=[S + 'D6'], price=[S + 'E6'], amount=[S + 'F6'], remarks=[S + 'G6']),
             [S + 'A6'], ['Remark states estimate status (不含估價): financial annotation kept in raw remarks (R1); responsibility not inferred.']),
        item('R003', 'demand', 'G1', 'research_draft', vals(A='示例控制盤', B='W600×H800×D300', C='盤體組立費', E='式', F=1),
             base_proofs(A=nn([S + 'B3'], 'copied group heading', 'group heading'), B=nn([S + 'C3'], 'copied group specification', 'group heading dimension'),
                         C=nn([S + 'B7'], 'copied', 'service line'),
                         D=nul('The remark 001.00 has no established technical role (unresolved-role token); it is kept in raw remarks.'),
                         E=nn([S + 'C7'], 'copied', 'unit column'), F=nn([S + 'D7'], 'copied', 'quantity column'), **project_proofs()),
             raw(desc=[S + 'B7'], unit=[S + 'C7'], qty=[S + 'D7'], price=[S + 'E7'], amount=[S + 'F7'], remarks=[S + 'G7']),
             [S + 'A7']),
        item('R004', 'demand', None, 'research_draft', vals(C='備用接點', E='只', F=0),
             base_proofs(C=nn([S + 'B8'], 'copied', 'product noun'), E=nn([S + 'C8'], 'copied', 'unit column'),
                         F=nn([S + 'D8'], 'copied numeric zero', 'quantity column; real zero'), **project_proofs()),
             raw(desc=[S + 'B8'], unit=[S + 'C8'], qty=[S + 'D8'], price=[S + 'E8'], amount=[S + 'F8']),
             [S + 'A8']),
        item('R005', 'demand', None, 'research_draft', vals(C='溫度計', D='0~100℃', E='支', F=1),
             base_proofs(C=nn([S + 'B11'], 'copied', 'product noun'), D=nn([S + 'G11'], 'copied remark clause', 'measuring range attribute in the item remark'),
                         E=nn([S + 'C11'], 'copied', 'unit column'),
                         F=nn([S + 'D11'], 'copied', 'quantity column'), **project_proofs()),
             raw(desc=[S + 'B11'], unit=[S + 'C11'], qty=[S + 'D11'], price=[S + 'E11'], amount=[S + 'F11'], remarks=[S + 'G11']),
             [S + 'A11']),
        item('R006', 'demand', None, 'research_draft', vals(C='流量計', E='台', F=1, I='FM-100', J='示例儀器', P=2),
             base_proofs(C=nn([S + 'B12'], 'copied', 'product noun'), E=nn([S + 'C12'], 'copied', 'unit column'),
                         F=nn([S + 'D12'], 'copied', 'quantity column'),
                         I=nn([S + 'G12'], 'text after 型號 label', 'explicit model label'),
                         J=nn([S + 'G12'], 'text after 廠牌 label', 'explicit brand label'),
                         D=nul('The remark gives only brand and model, placed in J and I; no other technical attribute.'),
                         P=nn([S + 'B17'], 'copied', 'explicit required-quantity label in A17 naming this item (流量計需要數量)'), **project_proofs()),
             raw(desc=[S + 'B12'], unit=[S + 'C12'], qty=[S + 'D12'], price=[S + 'E12'], amount=[S + 'F12'], remarks=[S + 'G12']),
             [S + 'A12']),
        item('R007', 'demand', None, 'held', vals(E='式', F=1),
             base_proofs(C=nul('Only a document pointer; no supplied object is identified.'),
                         E=nn([S + 'C18'], 'copied', 'unit column'), F=nn([S + 'D18'], 'copied', 'quantity column'), **project_proofs()),
             raw(desc=[S + 'B18'], unit=[S + 'C18'], qty=[S + 'D18']), [S + 'A18'],
             ['Candidate row names only a specification document; supplied object unresolved.']),
        item('C001', 'analysis_component', None, 'research_draft', [None, None, '組立工資'] + [None] * 14,
             base_proofs(C=nn([T2 + 'A3'], 'copied', 'analysis component name'),
                         E=nul('Per-unit basis unit is carried by the component link, not as a demand unit.'),
                         F=nul('Per-unit basis quantity is carried by the component link; no purchase quantity.'),
                         L=nul(NULL_REASONS['L'])),
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


def job_input_response(base, inv_sha):
    """046f job inputs (O13, R48) on the job-packet inventory: every item carries L, M and N proven by context alone;
    K, O and P null; G1 becomes the one-member physical_enclosure carrier of R001 (R56, route v4.2).
    R001 also takes I/J from the invented brand table, citing its description cell plus context:brand_table (R55, R58);
    the fixture source is a contract-like bill, so the brand table is allowed (O17)."""
    r = one_member_group_response(base)
    r['inventory_sha256'] = inv_sha
    for it in r['items']:
        v, p = it['values'], it['proofs']
        v[COLS.index('L')] = 'FIXTURE01'
        p['L'] = nn(['context:case_identity'], 'copied job input', 'internal case id supplied with the job (R48)')
        v[COLS.index('M')] = CUSTOMER
        p['M'] = nn(['context:customer_name'], 'copied job input', 'customer full name supplied with the job (R48)')
        v[COLS.index('N')] = PROJECT_NAME
        p['N'] = nn(['context:project_name'], 'copied job input', 'project short name supplied with the job (R48)')
        for col in ('K', 'O', 'P'):
            v[COLS.index(col)] = None
            p[col] = nul(f'{col} stays null (FIELD_ROLES R48).')
    r1 = next(x for x in r['items'] if x['id'] == 'R001')
    r1['values'][COLS.index('I')], r1['values'][COLS.index('J')] = 'XM-10', '示例甲牌'
    r1['proofs']['I'] = nn(['cell:S1!B4', 'context:brand_table'], 'model from the company brand table entry for 電磁接觸器',
                           'priced equipment line of a contract job with no model stated in the bound source (R55, R58)')
    r1['proofs']['J'] = nn(['cell:S1!B4', 'context:brand_table'], 'brand from the company brand table entry for 電磁接觸器',
                           'priced equipment line of a contract job with no brand stated in the bound source (R55, R58)')
    r['limitations'] = r['limitations'] + ['Invented 046f job-input variant (O13, R48; route v4.2 policy checks apply).']
    return r


def r57_response(base):
    """Route v4.1 relaxation (a), FIELD_ROLES R52/R57: C null with status research_draft. R003 (a service line) keeps
    a review reason; the analysis component C001 (labour) has none, so the writer's validation copy must add one."""
    r = copy.deepcopy(base)
    def it(i):
        return next(x for x in r['items'] if x['id'] == i)
    r3 = it('R003')
    r3['values'][2], r3['values'][3] = None, '盤體組立費'
    r3['proofs']['C'] = nul('Service line: C is null (R52).')
    r3['proofs']['D'] = nn(['cell:S1!B7'], 'copied description', 'service line: D is the description (R52)')
    r3['review_reasons'] = ['The remark 001.00 has no established technical role; it is kept in raw remarks.']
    c1 = it('C001')
    c1['values'][2], c1['values'][3] = None, '組立工資'
    c1['proofs']['C'] = nul('Labour component: C is null (R52).')
    c1['proofs']['D'] = nn(['cell:S2!A3'], 'copied description', 'labour line: D is the description (R52)')
    c1['review_reasons'] = []
    r['limitations'] = r['limitations'] + ['Invented route v4.1 variant: C null with status research_draft (R52, R57).']
    return r


def q_response(base, inv_sha):
    """Route v4.1 relaxation (b), FIELD_ROLES R54/O16: Q is the unit price although adoption is not verified."""
    r = copy.deepcopy(base)
    r['inventory_sha256'] = inv_sha
    r6 = next(x for x in r['items'] if x['id'] == 'R006')
    r6['values'][16] = 50000
    r6['proofs']['Q'] = nn(['cell:S1!E12'], 'copied unit price', 'priced line: Q is its unit price, never the amount (R54)')
    r['limitations'] = r['limitations'] + ['Invented route v4.1 variant: Q under unverified adoption (R54, O16).']
    return r


def one_member_group_response(base):
    """R56 mechanism: a physical_enclosure group with exactly one member carries A and B; no other row has A or B."""
    r = copy.deepcopy(base)
    g = r['groups'][0]
    g.update(relationship='physical_enclosure', quantity_basis='the member row R001 only (R56)',
             limitations=['One-row carrier group for A and B (R56); the route requires a group for A/B.'])
    for x in r['items']:
        if x['id'] in ('R002', 'R003'):
            x['group_id'] = None
            x['values'][0] = x['values'][1] = None
            x['proofs']['A'] = nul('Not the enclosure row: A is null (R56).')
            x['proofs']['B'] = nul('Not the enclosure row: B is null (R56).')
    r['limitations'] = r['limitations'] + ['Invented route v4.1 variant: one-member physical_enclosure group (R56).']
    return r


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
        ('held_without_reason', 'HELD_REASON_REQUIRED', m(lambda r: item(r, 'R007').update(review_reasons=[]))),
        ('A_without_group', 'UNGROUPED_AB_MUST_BE_BLANK', m(lambda r: item(r, 'R002').update(group_id=None))),
        ('A_not_group_name', 'A_MUST_EQUAL_GROUP_NAME', m(lambda r: item(r, 'R002')['values'].__setitem__(0, '示例控制盤一'))),
        ('B_not_group_spec', 'B_MUST_EQUAL_GROUP_SPECIFICATION', m(lambda r: (item(r, 'R002')['values'].__setitem__(1, '600x800'), item(r, 'R002')['proofs'].update(B={'refs': [S + 'B3'], 'transformation': 't', 'role_basis': 'b'})))),
        ('unknown_group', 'UNKNOWN_GROUP_ID', m(lambda r: item(r, 'R002').update(group_id='G9'))),
        ('E_not_raw_unit', 'SOURCE_UNIT_MISMATCH', m(lambda r: item(r, 'R002')['values'].__setitem__(4, '只'))),
        ('F_not_raw_quantity', 'SOURCE_QUANTITY_MISMATCH', m(lambda r: item(r, 'R002')['values'].__setitem__(5, 4))),
        ('F_proof_other_cell', 'F_PROOF_MUST_BE_RAW_QUANTITY_CELL', m(lambda r: item(r, 'R003')['proofs']['F'].update(refs=[S + 'D12']))),
        ('F_proof_text_cell', 'NONNUMERIC_SOURCE_TEXT_FIELD_MUST_BE_NULL', m(lambda r: item(r, 'R002')['proofs']['F'].update(refs=[S + 'B6']))),
        ('formula_like_D', 'FORMULA_LIKE_STRING_WHOLE_OUTPUT_HELD', m(lambda r: item(r, 'R005')['values'].__setitem__(3, '-20~60℃'))),
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


# ---------------------------------------------------------------- route v4.3 (FIELD_ROLES R59): scoped packets, invented
SCOPED_CASE = 'SCOPED01'
SB = '示例材料清單'
# the reasons are those scope_tool.py (v2) writes; the analysis sheet's ends with its one linked block, of a priced parent
SCOPED_ANALYSIS_OUT = ('analysis: not every in-range bill line has no price and no status, so R51 takes no rows from this sheet; '
                       'a separate analysis sheet lies outside the quoted range (R49, R51, A26)')
SCOPED_SHEETS = [   # index, name, role, rows, columns, content cells (out-of-scope sheets: invented; bill: computed), reason
    (1, '示例總表', 'summary', 12, 4, 20, 'summary: never yields rows (R49)'),
    (2, SB, 'bill', 10, 7, None, 'bill: the single BILL1 candidate; rows come from this sheet (R49)'),
    (3, '示例單價分析', 'analysis', 400, 7, 2500,
     SCOPED_ANALYSIS_OUT + '; 1 linked block(s): 1 of priced or not-estimated parents (not 未填 rows, not written on a scoped packet), '
     '0 of parents with no price and no status (those lines are excluded_supply); none gives rows (R51, R59)'),
    (4, '示例資源統計', 'resource_statistics', 120, 10, 600, 'resource statistics: source check only, never yields rows (guideline section 3)'),
]
SCOPED_BILL = {
    (1, 'A'): (T, '示例淨水場控制盤更新 材料清單', False),
    **{(2, c): (T, v, False) for c, v in zip('ABCDEFG', ['項次', '項目及說明', '單位', '數量', '單價', '複價', '備註'])},
    (3, 'A'): (T, '1', False), (3, 'B'): (T, '產品，電磁接觸器，AC220V', False), (3, 'C'): (T, '只', False),
    (3, 'D'): (N, 2.0, False), (3, 'E'): (N, 1500.0, False), (3, 'F'): (N, 3000.0, True),
    (4, 'A'): (T, '2', False), (4, 'B'): (T, '產品，選擇開關，30mm', False), (4, 'C'): (T, '個', False),
    (4, 'D'): (N, 3.0, False), (4, 'F'): (T, '不含估價', False),
    (5, 'A'): (T, '3', False), (5, 'B'): (T, '溫度計', False), (5, 'C'): (T, '支', False), (5, 'D'): (N, 1.0, False),
    (6, 'B'): (T, '運費', False), (6, 'C'): (T, '式', False), (6, 'D'): (N, 1.0, False), (6, 'E'): (N, 2000.0, False), (6, 'F'): (N, 2000.0, True),
    (7, 'E'): (T, '合計', False), (7, 'F'): (N, 5000.0, True),
    (8, 'A'): (T, '議價後總價', False), (8, 'F'): (N, 4800.0, False),
    (9, 'A'): (T, '報價人：示例機電股份有限公司', False),
    (10, 'A'): (T, '4', False), (10, 'B'): (T, '產品，無熔絲開關，3P，50AT', False), (10, 'C'): (T, '只', False),
    (10, 'D'): (N, 1.0, False), (10, 'E'): (N, 900.0, False), (10, 'F'): (N, 900.0, True),
}
SCOPED_BILL_MERGES = ['A1:G1']


def sheet_cells(si, name, data, rows, cols, merge_list, vws):
    """Every position of one sheet, as build_inventory writes them."""
    cov = {}
    for m in merge_list:
        a, b = m.split(':')
        c0, r0 = ord(a[0]) - 64, int(a[1:])
        c1, r1 = ord(b[0]) - 64, int(b[1:])
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if (r, c) != (r0, c0):
                    cov[(r, c)] = f'cell:S{si}!{letters(c0)}{r0}'
    out = []
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            L = letters(c)
            typ, val, frm = data.get((r, L), ('blank', None, False))
            state, canonical, usable, reason = None, None, False, None
            if (r, c) in cov:
                state, reason = 'covered', 'covered merge position; use the merge anchor'
            elif typ == 'blank':
                state, reason = 'true_blank', 'empty cell has no raw text'
            else:
                state = 'cached_formula' if frm else 'literal'
                canonical, usable = (val, True) if typ == T else (canon(val), True)
            vv = []
            for v in vws:
                lo, hi = v['range'].split(':')
                (cl, rl), (ch, rh) = [(ord(x[0]) - 64, int(x[1:])) for x in (lo, hi)]
                if v['sheet'] == name and cl <= c <= ch and rl <= r <= rh:
                    vv.append(v['id'])
            out.append({'ref': f'cell:S{si}!{L}{r}', 'sheet_index': si, 'sheet': name, 'address': f'{L}{r}', 'row': r, 'col': c,
                        'saved_type': typ, 'state': state, 'saved_value': val, 'native_literal': None, 'formula_record_present': frm,
                        'formula': None, 'merge_anchor_ref': cov.get((r, c)), 'conflicts': [], 'canonical_raw': canonical,
                        'usable_for_raw': usable, 'raw_limit_reason': reason, 'views': vv})
    return out


def scoped_job_facts(case_id):
    """Job inputs and company resources of the invented 材料清單 job (no brand table, O17)."""
    job_sha = hashlib.sha256(b'invented scoped per-job config').hexdigest()
    return ([_fact('case_identity', 'cps.internal_case_id', case_id, 'Invented job input: internal case id (O13, R48).', 'invented per-job config', job_sha)]
            + JOB_INPUTS(job_sha) + [f for f in RESOURCE_FACTS() if f['ref'] != 'context:brand_table'])


def scope_payload(end_row=7, linked=1, bill_content=None, **over):
    sheets = []
    for idx, name, role, rows, cols, cc, reason in SCOPED_SHEETS:
        sheets.append({'index': idx, 'name': name, 'role': role, 'visibility': 'visible', 'rows': rows, 'columns': cols,
                       'content_cells': bill_content if role == 'bill' else cc, 'in_scope': role == 'bill',
                       'reason': reason if (role != 'analysis' or linked) else SCOPED_ANALYSIS_OUT,
                       'linked_analysis_blocks': linked if role == 'analysis' else 0})
    h = lambda t: hashlib.sha256(t.encode('utf-8')).hexdigest()
    d = {'schema': 'cps.scope-fact.v1', 'rule': 'R59', 'bill_rule': 'BILL1.v1',
         'threshold': {'content_cells_literal_or_cached': 3159, 'limit': 2500},
         'bill_sheet_index': 2, 'bill_header_row': 2, 'end_row': end_row, 'sheets': sheets,
         'digest_sha256': h('invented scope digest'), 'full_inventory_sha256': h('invented full inventory'),
         'decision_sha256': h('invented scope decision'), 'agreement': 'tool_and_reader_agreed'}
    d.update(over)
    return d


def build_scoped_inventory(payload=None, fact_value=None, extra_views=(), cell_swap=False, **pkw):
    vws = [{'id': 1, 'sheet': SB, 'range': 'A1:G10'}] + list(extra_views)
    cells = sheet_cells(2, SB, SCOPED_BILL, 10, 7, SCOPED_BILL_MERGES, vws)
    if cell_swap:       # an out-of-scope sheet's cell replaces a blank in-scope position: the census count still matches
        g10 = next(i for i, c in enumerate(cells) if c['address'] == 'G10')
        cells[g10] = dict(cells[g10], ref='cell:S1!A1', sheet_index=1, sheet='示例總表', address='A1', row=1, col=1, views=[])
    content = sum(1 for c in cells if c['state'] in ('literal', 'cached_formula') and c['saved_value'] not in (None, ''))
    payload = payload if payload is not None else scope_payload(bill_content=content, **pkw)
    fake_sha = hashlib.sha256(b'invented scoped fixture workbook bytes').hexdigest()
    sheets = [{'index': idx, 'name': name, 'visibility': 'visible', 'rows': rows, 'columns': cols,
               'merges': SCOPED_BILL_MERGES if role == 'bill' else [],
               'formula_records': sum(1 for v in SCOPED_BILL.values() if v[2]) if role == 'bill' else 0, 'in_scope': role == 'bill'}
              for idx, name, role, rows, cols, _, _ in SCOPED_SHEETS]
    value = fact_value if fact_value is not None else json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    scope_fact = {'ref': 'context:scope', 'namespace': 'cps.source_prep.scope', 'value': value,
                  'basis': 'Invented scope decision for route testing (FIELD_ROLES R59); not a real scope stage.',
                  'authority_pins': [{'label': 'invented scope decision', 'sha256': payload['decision_sha256'] if isinstance(payload.get('decision_sha256'), str) else fake_sha}]}
    inv = {'schema': 'cps.source-inventory.cells.v2', 'case_id': SCOPED_CASE, 'family_id': SCOPED_CASE,
           'representation_profile': 'cached-cell-raw-scalar-text.v2',
           'source': {'source_id': 'S', 'format': 'cached_xlsx', 'bytes': 2048, 'sha256': fake_sha, 'adoption_status': 'unverified',
                      'adoption_basis': 'Invented scoped fixture; no real material list.',
                      'reader': {'name': 'invented', 'version': '0', 'biff_format': None, 'formula_expressions_available': False},
                      'carrier_source': {'kind': 'cached_xlsx', 'path': 'X:\\Fixtures\\invented\\fixture-material-list.xlsx',
                                         'sha256': fake_sha, 'views': vws}},
           'sheets': sheets,
           'views': [dict(v, image={'file': f"view_{v['id']:02d}.png", 'bytes': 1, 'sha256': fake_sha}) for v in vws],
           'external_links': [], 'cells': cells,
           'context_facts': scoped_job_facts(SCOPED_CASE) + [scope_fact],
           'limitations': ['Invented scoped fixture inventory for route v4.3 tests only (FIELD_ROLES R59).']}
    return inv, serialize(inv).encode('utf-8')


def scoped_response(inv_sha, case_id=SCOPED_CASE):
    """Valid response on the scoped fixture: rows 3, 4 and 6 of the bill sheet (R49-R59); rows 8-10 are out of range."""
    S = 'cell:S2!'
    jin = dict(L=nn(['context:case_identity'], 'copied job input', 'internal case id supplied with the job (R48)'),
               M=nn(['context:customer_name'], 'copied job input', 'customer full name supplied with the job (R48)'),
               N=nn(['context:project_name'], 'copied job input', 'project short name supplied with the job (R48)'))
    def nulls(**over):
        p = {c: nul(f'{c} stays null on this row.') for c in COLS}
        p['A'] = nul('Not the enclosure row: A is null (R56).')
        p['B'] = nul('Not the enclosure row: B is null (R56).')
        p['G'] = nul('Procurement unit price is blank at the 未填 stage.')
        p['H'] = nul('Procurement extended price is blank at the 未填 stage.')
        for c in 'KOP':
            p[c] = nul(f'{c} stays null (FIELD_ROLES R48).')
        p.update(jin)
        p.update(over)
        return p
    def v(**kw):
        x = [None] * 17
        x[11], x[12], x[13] = case_id, CUSTOMER, PROJECT_NAME
        for k, y in kw.items():
            x[COLS.index(k)] = y
        return x
    items = [
        item('R001', 'demand', None, 'research_draft', v(C='XM', D='AC220V', E='只', F=2, Q=1500),
             nulls(C=nn([S + 'B3', 'context:glossary'], 'glossary abbreviation of the device 電磁接觸器', 'equipment line; glossary device (R52)'),
                   D=nn([S + 'B3'], 'rest of the description after the glossary device', 'R52 glossary step'),
                   E=nn([S + 'C3'], 'copied', 'unit cell'), F=nn([S + 'D3'], 'copied', 'quantity cell'),
                   I=nul('No model stated in the line\'s own cells; a 材料清單 job takes I only from its cells (R55, O17).'),
                   J=nul('No brand stated in the line\'s own cells; a 材料清單 job takes J only from its cells (R55, O17).'),
                   Q=nn([S + 'E3'], 'copied unit price', 'priced line: Q is its unit price (R54)')),
             raw(desc=[S + 'B3'], unit=[S + 'C3'], qty=[S + 'D3'], price=[S + 'E3'], amount=[S + 'F3'], reasons={'remarks': 'remarks cell is empty'}),
             [S + 'A3']),
        item('R002', 'demand', None, 'research_draft', v(C='XS', D='30mm', E='個', F=3, I='不含估價', J='不含估價'),
             nulls(C=nn([S + 'B4', 'context:glossary'], 'glossary abbreviation of the device 選擇開關', 'equipment line; glossary device (R52)'),
                   D=nn([S + 'B4'], 'rest of the description after the glossary device', 'R52 glossary step'),
                   E=nn([S + 'C4'], 'copied', 'unit cell'), F=nn([S + 'D4'], 'copied', 'quantity cell'),
                   I=nn([S + 'F4'], 'copied status text', 'not-estimated line: I = 不含估價 (R55)'),
                   J=nn([S + 'F4'], 'copied status text', 'not-estimated line: J = 不含估價 (R55)'),
                   Q=nul('Not-estimated line: Q is null (R54).')),
             raw(desc=[S + 'B4'], unit=[S + 'C4'], qty=[S + 'D4'], amount=[S + 'F4'],
                 reasons={'unit_price': 'unit-price cell is empty', 'remarks': 'remarks cell is empty'}),
             [S + 'A4']),
        item('R003', 'demand', None, 'research_draft', v(D='運費', E='式', F=1, Q=2000),
             nulls(C=nul('Fee line: C is null (R52).'), D=nn([S + 'B6'], 'copied description', 'fee line: D is the description (R52)'),
                   E=nn([S + 'C6'], 'copied', 'unit cell'), F=nn([S + 'D6'], 'copied', 'quantity cell'),
                   I=nul('Fee line with no stated model (R55).'), J=nul('Fee line with no stated brand (R55).'),
                   Q=nn([S + 'E6'], 'copied unit price', 'priced fee line: Q is its unit price (R54)')),
             raw(desc=[S + 'B6'], unit=[S + 'C6'], qty=[S + 'D6'], price=[S + 'E6'], amount=[S + 'F6'], reasons={'remarks': 'remarks cell is empty'}),
             [S + 'B6']),
    ]
    roles = [
        {'role': 'header', 'refs': [S + 'A1'] + [S + c + '2' for c in 'ABCDEFG'], 'reason': 'title and column headers'},
        {'role': 'item_identifier', 'refs': [S + 'A3', S + 'A4'], 'reason': 'item numbers'},
        {'role': 'demand_content', 'refs': [S + x for x in ['B3', 'C3', 'D3', 'E3', 'F3', 'B4', 'C4', 'D4', 'F4', 'B6', 'C6', 'D6', 'E6', 'F6']],
         'reason': 'item description, unit, quantity, price and amount cells'},
        {'role': 'excluded_supply', 'refs': [S + x for x in ['A5', 'B5', 'C5', 'D5']],
         'reason': 'no enclosure and no estimate: not in the quoted supply (R45); price cells empty'},
        {'role': 'financial_summary', 'refs': [S + 'E7', S + 'F7'], 'reason': 'end row of the quoted range (R49)'},
        {'role': 'excluded_supply', 'refs': [S + x for x in ['A8', 'F8', 'A9', 'A10', 'B10', 'C10', 'D10', 'E10', 'F10']],
         'reason': 'outside the quoted range (R49, R59)'},
    ]
    return {'schema': 'cps.semantic-source-refs.v2', 'case_id': case_id, 'family_id': case_id, 'inventory_sha256': inv_sha,
            'status': 'research_draft', 'groups': [], 'items': items, 'component_links': [], 'source_roles': roles,
            'limitations': ['Invented scoped fixture response (FIELD_ROLES R59).']}


def scoped_fixtures(enc, index):
    """Route v4.3 (R59): scoped fixture inventories, valid responses and one mutation per new check."""
    inv, raw_ = build_scoped_inventory()
    (OUT / 'fixture_inventory_scoped.json').write_bytes(raw_)
    base = scoped_response(hashlib.sha256(raw_).hexdigest())
    (OUT / 'valid_response_scoped.json').write_bytes(enc(base))
    for tag, kw in (('nolink', {'linked': 0}), ('end6', {'end_row': 6})):
        _, vraw = build_scoped_inventory(**kw)
        (OUT / f'fixture_inventory_scoped_{tag}.json').write_bytes(vraw)
        (OUT / f'valid_response_scoped_{tag}.json').write_bytes(enc(scoped_response(hashlib.sha256(vraw).hexdigest())))
    content = sum(1 for c in inv['cells'] if c['state'] in ('literal', 'cached_formula') and c['saved_value'] not in (None, ''))
    S = 'cell:S2!'
    def it(r, i):
        return next(x for x in r['items'] if x['id'] == i)
    def resp_mut(name, code, f):
        r = copy.deepcopy(base)
        f(r)
        (OUT / f'mut_{name}.json').write_bytes(enc(r))
        index.append({'name': name, 'file': f'mut_{name}.json', 'expected_code': code, 'inventory': 'fixture_inventory_scoped.json'})
    def add_row10(r):
        cells = [S + x for x in ('A10', 'B10', 'C10', 'D10', 'E10', 'F10')]
        for sr in r['source_roles']:
            sr['refs'] = [x for x in sr['refs'] if x not in cells]
        r['source_roles'].append({'role': 'item_identifier', 'refs': [S + 'A10'], 'reason': 'item number'})
        r['source_roles'].append({'role': 'demand_content', 'refs': cells[1:], 'reason': 'item cells'})
        x = copy.deepcopy(it(r, 'R001'))
        x['id'] = 'R004'
        x['values'][2], x['values'][3], x['values'][5], x['values'][16] = None, '產品，無熔絲開關，3P，50AT', 1, 900
        x['proofs'].update(C=nul('no glossary device'), D=nn([S + 'B10'], 'copied', 'description'), E=nn([S + 'C10'], 'copied', 'unit cell'),
                           F=nn([S + 'D10'], 'copied', 'quantity cell'), Q=nn([S + 'E10'], 'copied', 'unit price'))
        x['raw_refs'] = raw(desc=[S + 'B10'], unit=[S + 'C10'], qty=[S + 'D10'], price=[S + 'E10'], amount=[S + 'F10'], reasons={'remarks': 'empty'})
        x['anchor_refs'] = [S + 'A10']
        r['items'].append(x)
    resp_mut('v43_row_below_end_item', 'R59_ROW_BELOW_END_ROW', add_row10)
    resp_mut('v43_row_below_end_raw_remarks', 'R59_ROW_BELOW_END_ROW',
             lambda r: it(r, 'R001')['raw_refs'].update(remarks={'refs': [S + 'A9'], 'reason_if_empty': None}))
    resp_mut('v43_row_below_end_proof', 'R59_ROW_BELOW_END_ROW', lambda r: it(r, 'R003')['proofs']['D'].update(refs=[S + 'B6', S + 'A8']))
    resp_mut('v43_row_below_end_anchor', 'R59_ROW_BELOW_END_ROW', lambda r: it(r, 'R003').update(anchor_refs=[S + 'A8']))
    def group_below(r):
        r['groups'].append({'id': 'G1', 'name': None, 'specification': None, 'relationship': 'physical_enclosure', 'anchor_refs': [S + 'A10'],
                            'name_refs': [], 'specification_refs': [], 'quantity_basis': 'one row', 'limitations': ['invented defect']})
        it(r, 'R001')['group_id'] = 'G1'
    resp_mut('v43_row_below_end_group', 'R59_ROW_BELOW_END_ROW', group_below)
    # (e) 046g pass 2: context:scope is never evidence; every reference list that cites it is rejected (R59 item 7)
    cited = 'R59_SCOPE_FACT_CITED'
    resp_mut('v43_scope_cited_proof_with_cell', cited, lambda r: it(r, 'R001')['proofs']['D'].update(refs=[S + 'B3', 'context:scope']))
    resp_mut('v43_scope_cited_proof_context_only', cited, lambda r: it(r, 'R002')['proofs'].update(
        D=nn(['context:scope'], 'copied from the scope fact', 'invented defect')))
    resp_mut('v43_scope_cited_job_input', cited, lambda r: it(r, 'R003')['proofs']['L'].update(refs=['context:case_identity', 'context:scope']))
    resp_mut('v43_scope_cited_null_proof', cited, lambda r: it(r, 'R001')['proofs'].update(I={'reason': 'x', 'refs': ['context:scope']}))
    resp_mut('v43_scope_cited_raw_description', cited,
             lambda r: it(r, 'R001')['raw_refs'].update(description={'refs': [S + 'B3', 'context:scope'], 'reason_if_empty': None}))
    resp_mut('v43_scope_cited_raw_remarks', cited,
             lambda r: it(r, 'R002')['raw_refs'].update(remarks={'refs': ['context:scope'], 'reason_if_empty': None}))
    resp_mut('v43_scope_cited_anchor', cited, lambda r: it(r, 'R003').update(anchor_refs=[S + 'B6', 'context:scope']))
    def group_scope(r):
        r['groups'].append({'id': 'G1', 'name': '示例', 'specification': None, 'relationship': 'physical_enclosure', 'anchor_refs': [S + 'A3'],
                            'name_refs': ['context:scope'], 'specification_refs': [], 'quantity_basis': 'one row', 'limitations': []})
        it(r, 'R001')['group_id'] = 'G1'
    resp_mut('v43_scope_cited_group', cited, group_scope)
    resp_mut('v43_scope_cited_component_link', cited, lambda r: r['component_links'].append(
        {'component_id': 'C999', 'parent_id': 'R001', 'status': 'supported', 'basis_quantity': 1, 'basis_raw_ref': 'context:scope',
         'basis_unit_ref': S + 'C3', 'refs': ['context:scope'], 'reason': 'invented defect'}))
    def inv_mut(name, code, **kw):
        _, vraw = build_scoped_inventory(**kw)
        (OUT / f'inv_{name}.json').write_bytes(vraw)
        r = copy.deepcopy(base)
        r['inventory_sha256'] = hashlib.sha256(vraw).hexdigest()
        (OUT / f'mut_{name}.json').write_bytes(enc(r))
        index.append({'name': name, 'file': f'mut_{name}.json', 'expected_code': code, 'inventory': f'inv_{name}.json'})
    P = lambda **o: scope_payload(bill_content=content, **o)
    def P_sheet(i, **o):
        d = P()
        d['sheets'][i].update(o)
        return d
    inv_mut('v43_row_below_end_boundary', 'R59_ROW_BELOW_END_ROW', end_row=5)
    bad = 'R59_SCOPE_FACT_INVALID'
    inv_mut('v43_fact_not_json', bad, payload=P(), fact_value='{"schema": "cps.scope-fact.v1",')
    inv_mut('v43_fact_value_number', bad, payload=P(), fact_value=7)
    inv_mut('v43_fact_wrong_schema', bad, payload=P(schema='cps.scope-fact.v0'))
    inv_mut('v43_fact_wrong_bill_rule', bad, payload=P(bill_rule='BILL2'))
    inv_mut('v43_fact_wrong_agreement', bad, payload=P(agreement='tool_only'))
    d = P(); d.pop('digest_sha256')
    inv_mut('v43_fact_missing_key', bad, payload=d)
    inv_mut('v43_fact_extra_key', bad, payload=P(note='x'))
    inv_mut('v43_fact_below_threshold', bad, payload=P(threshold={'content_cells_literal_or_cached': 2500, 'limit': 2500}))
    inv_mut('v43_fact_bad_hash', bad, payload=P(decision_sha256='ABC'))
    inv_mut('v43_fact_end_row_not_integer', bad, payload=P(end_row='7'))
    inv_mut('v43_fact_sheet_count_text', bad, payload=P_sheet(1, content_cells='39'))
    inv_mut('v43_fact_sheet_blank_reason', bad, payload=P_sheet(0, reason='\u3000'))
    mm = 'R59_SCOPE_FACT_MISMATCH'
    inv_mut('v43_fact_flag_disagrees', mm, payload=P_sheet(2, in_scope=True, reason='analysis: in scope'))
    inv_mut('v43_fact_name_mismatch', mm, payload=P_sheet(0, name='另一總表'))
    inv_mut('v43_fact_dimensions_mismatch', mm, payload=P_sheet(1, rows=11))
    d = P(); d['sheets'] = d['sheets'][:3]
    inv_mut('v43_fact_missing_sheet', mm, payload=d)
    inv_mut('v43_fact_two_bills', mm, payload=P_sheet(2, role='bill'))
    inv_mut('v43_fact_bill_index_wrong', mm, payload=P(bill_sheet_index=1))
    inv_mut('v43_fact_bill_out_of_scope', mm, payload=P_sheet(1, in_scope=False))
    inv_mut('v43_fact_in_scope_role_summary', mm, payload=P_sheet(1, role='summary'))
    inv_mut('v43_fact_out_of_scope_role_unknown', mm, payload=P_sheet(3, role='statistics'))
    inv_mut('v43_fact_content_count_mismatch', mm, payload=P_sheet(1, content_cells=content - 1))
    inv_mut('v43_fact_end_row_beyond_sheet', mm, payload=P(end_row=11))
    inv_mut('v43_fact_end_row_not_after_header', mm, payload=P(end_row=2))
    inv_mut('v43_out_of_scope_view_present', mm, extra_views=[{'id': 2, 'sheet': '示例總表', 'range': 'A1:D12'}])
    inv_mut('v43_out_of_scope_cell_present', mm, cell_swap=True)


# ---------------------------------------------------------------- route v4.4 (046i, owner decision O72): no total row; whole workbook
NOTOTAL_BILL = {k: v for k, v in SCOPED_BILL.items() if k != (7, 'E')}      # SCOPED_BILL without its 合計 cell (scope-stage NT1)
NOTOTAL_REASON = ('bill: the only sheet with a BILL1 header row and no 合計 or 總計 below it in a price column; the scope runs to its '
                  'last content row and R49 ends the quoted range inside it (R59 item 2, O72)')
WHOLE_REASON = ('whole workbook: no sheet has a BILL1 header row (five or six of its labels), so every sheet except an empty one is in '
                'scope and the packet is read as an unscoped packet; the role is a label, not an R49 decision (R59 item 9, O72)')
EMPTY_REASON = 'other: an empty sheet (rows x columns = 0, no cell), which the builders write out of scope; never yields rows (R49)'
WL = '示例價目表'
WHOLE_LIST = {      # SYNTHETIC_ALLOCATION_CASES A51: four of the six BILL1 labels (序號 and 品名規格 are not BILL1 words)
    (1, 'A'): (T, '示例淨水場控制盤更新 價目表', False),
    **{(2, c): (T, v, False) for c, v in zip('ABCDEF', ['序號', '品名規格', '單位', '數量', '單價', '金額'])},
    (3, 'A'): (T, '1', False), (3, 'B'): (T, '產品，電磁接觸器，AC220V', False), (3, 'C'): (T, '只', False),
    (3, 'D'): (N, 2.0, False), (3, 'E'): (N, 1500.0, False), (3, 'F'): (N, 3000.0, True),
    (4, 'A'): (T, '2', False), (4, 'B'): (T, '示例配線材料', False), (4, 'C'): (T, '式', False),
    (4, 'D'): (N, 1.0, False), (4, 'E'): (N, 800.0, False), (4, 'F'): (N, 800.0, True),
    (5, 'E'): (T, '合計', False), (5, 'F'): (N, 3800.0, True),
    (6, 'A'): (T, '報價人：示例機電股份有限公司', False),
}
WHOLE_MEMO = {(1, 'A'): (T, '示例說明', False), (2, 'A'): (T, '示例內容第二行', False)}
NOTOTAL_SPECS = [(1, '示例總表', 'summary', None, 12, 4, [], 20, 'summary: never yields rows (R49)'),
                 (2, SB, 'bill', NOTOTAL_BILL, 10, 7, SCOPED_BILL_MERGES, None, NOTOTAL_REASON),
                 (3, '示例單價分析', 'analysis', None, 400, 7, [], 2500, SCOPED_ANALYSIS_OUT),
                 (4, '示例資源統計', 'resource_statistics', None, 120, 10, [], 600,
                  'resource statistics: source check only, never yields rows (guideline section 3)')]
WHOLE_SPECS = [(1, WL, 'other', WHOLE_LIST, 6, 6, ['A1:F1'], None, WHOLE_REASON),
               (2, '示例說明', 'other', WHOLE_MEMO, 2, 1, [], None, WHOLE_REASON),
               (3, '示例空白', 'other', {}, 0, 0, [], None, EMPTY_REASON)]


def _content(data):
    return sum(1 for v in data.values() if v[1] is not None and v[1] != '')


def o72_payload(specs, flags, rule, bill, header, end, **over):
    h = lambda t: hashlib.sha256(t.encode('utf-8')).hexdigest()
    sheets = [{'index': i, 'name': n, 'role': role, 'visibility': 'visible', 'rows': r, 'columns': c,
               'content_cells': _content(data) if data is not None else cc, 'in_scope': flags[i], 'reason': reason, 'linked_analysis_blocks': 0}
              for i, n, role, data, r, c, _, cc, reason in specs]
    d = {'schema': 'cps.scope-fact.v1', 'rule': 'R59', 'bill_rule': rule,
         'threshold': {'content_cells_literal_or_cached': 3001, 'limit': 2500},
         'bill_sheet_index': bill, 'bill_header_row': header, 'end_row': end, 'sheets': sheets,
         'digest_sha256': h('invented scope digest'), 'full_inventory_sha256': h('invented full inventory'),
         'decision_sha256': h('invented scope decision'), 'agreement': 'tool_and_reader_agreed'}
    d.update(over)
    return d


def o72_inventory(specs, flags, payload, fact_value=None):
    """An invented packet with the given sheets; cells and one view for every in-scope sheet with rows x columns > 0."""
    vws = []
    for i, n, _, data, r, c, _, _, _ in specs:
        if flags[i] and r * c:
            vws.append({'id': len(vws) + 1, 'sheet': n, 'range': f'A1:{letters(c)}{r}'})
    cells = []
    for i, n, _, data, r, c, mg, _, _ in specs:
        if flags[i] and r * c:
            cells += sheet_cells(i, n, data, r, c, mg, vws)
    fake_sha = hashlib.sha256(b'invented O72 fixture workbook bytes').hexdigest()
    sheets = [{'index': i, 'name': n, 'visibility': 'visible', 'rows': r, 'columns': c, 'merges': mg if flags[i] else [],
               'formula_records': sum(1 for v in (data or {}).values() if v[2]) if flags[i] else 0, 'in_scope': flags[i]}
              for i, n, _, data, r, c, mg, _, _ in specs]
    value = fact_value if fact_value is not None else json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    scope_fact = {'ref': 'context:scope', 'namespace': 'cps.source_prep.scope', 'value': value,
                  'basis': 'Invented scope decision for route testing (FIELD_ROLES R59, O72); not a real scope stage.',
                  'authority_pins': [{'label': 'invented scope decision', 'sha256': fake_sha}]}
    inv = {'schema': 'cps.source-inventory.cells.v2', 'case_id': SCOPED_CASE, 'family_id': SCOPED_CASE,
           'representation_profile': 'cached-cell-raw-scalar-text.v2',
           'source': {'source_id': 'S', 'format': 'cached_xlsx', 'bytes': 2048, 'sha256': fake_sha, 'adoption_status': 'unverified',
                      'adoption_basis': 'Invented O72 fixture; no real material list.',
                      'reader': {'name': 'invented', 'version': '0', 'biff_format': None, 'formula_expressions_available': False},
                      'carrier_source': {'kind': 'cached_xlsx', 'path': 'X:\\Fixtures\\invented\\fixture-material-list.xlsx',
                                         'sha256': fake_sha, 'views': vws}},
           'sheets': sheets,
           'views': [dict(v, image={'file': f"view_{v['id']:02d}.png", 'bytes': 1, 'sha256': fake_sha}) for v in vws],
           'external_links': [], 'cells': cells,
           'context_facts': scoped_job_facts(SCOPED_CASE) + [scope_fact],
           'limitations': ['Invented O72 fixture inventory for route v4.4 tests only (FIELD_ROLES R59 items 2 and 9).']}
    return inv, serialize(inv).encode('utf-8')


NOTOTAL_FLAGS = {1: False, 2: True, 3: False, 4: False}
WHOLE_FLAGS = {1: True, 2: True, 3: False}


def nototal_payload(**over):
    return o72_payload(NOTOTAL_SPECS, NOTOTAL_FLAGS, 'BILL1.NOTOTAL.v1', 2, 2, 10, **over)


def whole_payload(flags=None, **over):
    return o72_payload(WHOLE_SPECS, flags or WHOLE_FLAGS, 'BILL1.NOHEADER.v1', None, None, None, **over)


def nototal_response(inv_sha):
    """Valid response on the no-total packet (A50): rows 3, 4 and 6; R49 ends the range at row 6, the last item line before the
    signature line; the cells after it take their roles as on an unscoped packet (R59 item 2)."""
    r = scoped_response(inv_sha)
    S = 'cell:S2!'
    roles = [x for x in r['source_roles'] if x['role'] not in ('financial_summary', 'excluded_supply') or x['reason'].startswith('no enclosure')]
    roles += [{'role': 'financial_summary', 'refs': [S + 'F7'], 'reason': 'unlabelled total after the last item line (R11)'},
              {'role': 'financial_summary', 'refs': [S + 'A8', S + 'F8'], 'reason': 'negotiated total after the quoted range (R11)'},
              {'role': 'footer', 'refs': [S + 'A9'], 'reason': 'signature line'},
              {'role': 'excluded_supply', 'refs': [S + x for x in ('A10', 'B10', 'C10', 'D10', 'E10', 'F10')],
               'reason': 'outside the quoted range (R49): an item line after the signature line'}]
    r['source_roles'] = roles
    r['limitations'] = ['Invented no-total scoped fixture response (FIELD_ROLES R59 item 2, owner decision O72).']
    return r


def whole_response(inv_sha):
    """Valid response on the whole-workbook packet (A51): the generator found the priced list itself (R49); rows 3 and 4."""
    S, M_ = 'cell:S1!', 'cell:S2!'
    r = scoped_response(inv_sha)
    a, c = copy.deepcopy(r['items'][0]), copy.deepcopy(r['items'][2])
    def resheet(x):
        return json.loads(json.dumps(x, ensure_ascii=False).replace('cell:S2!', S))
    a = resheet(a)
    c = resheet(c)
    c['id'] = 'R002'
    c['values'][3], c['values'][4], c['values'][5], c['values'][16] = '示例配線材料', '式', 1, 800
    c['proofs'].update(C=nul('Material line with no glossary device: C is null (R52).'),
                       D=nn([S + 'B4'], 'copied description', 'material line: D is the description (R52)'),
                       E=nn([S + 'C4'], 'copied', 'unit cell'), F=nn([S + 'D4'], 'copied', 'quantity cell'),
                       I=nul('No model stated in the line\'s own cells (R55, O17).'), J=nul('No brand stated in the line\'s own cells (R55, O17).'),
                       Q=nn([S + 'E4'], 'copied unit price', 'priced line: Q is its unit price (R54)'))
    c['raw_refs'] = raw(desc=[S + 'B4'], unit=[S + 'C4'], qty=[S + 'D4'], price=[S + 'E4'], amount=[S + 'F4'], reasons={'remarks': 'remarks cell is empty'})
    c['anchor_refs'] = [S + 'A4']
    r['items'] = [a, c]
    r['source_roles'] = [
        {'role': 'header', 'refs': [S + 'A1'] + [S + x + '2' for x in 'ABCDEF'], 'reason': 'title and column headers'},
        {'role': 'item_identifier', 'refs': [S + 'A3', S + 'A4'], 'reason': 'item numbers'},
        {'role': 'demand_content', 'refs': [S + x + y for y in '34' for x in 'BCDEF'], 'reason': 'item description, unit, quantity, price and amount cells'},
        {'role': 'financial_summary', 'refs': [S + 'E5', S + 'F5'], 'reason': 'end row of the quoted range (R49)'},
        {'role': 'footer', 'refs': [S + 'A6'], 'reason': 'signature line'},
        {'role': 'header', 'refs': [M_ + 'A1'], 'reason': 'memo title'},
        {'role': 'commercial_note', 'refs': [M_ + 'A2'], 'reason': 'memo text'}]
    r['limitations'] = ['Invented whole-workbook fixture response (FIELD_ROLES R59 item 9, owner decision O72).']
    return r


def o72_fixtures(enc, index):
    """Route v4.4 (owner decision O72): no-total and whole-workbook fixture packets, valid responses and one mutation per new check."""
    _, nraw = o72_inventory(NOTOTAL_SPECS, NOTOTAL_FLAGS, nototal_payload())
    (OUT / 'fixture_inventory_scoped_nototal.json').write_bytes(nraw)
    nbase = nototal_response(hashlib.sha256(nraw).hexdigest())
    (OUT / 'valid_response_scoped_nototal.json').write_bytes(enc(nbase))
    # citing the last content row passes: under BILL1.NOTOTAL.v1 end_row is the last content row (route check (b))
    r10 = copy.deepcopy(nbase)
    S = 'cell:S2!'
    cells10 = [S + x for x in ('A10', 'B10', 'C10', 'D10', 'E10', 'F10')]
    r10['source_roles'] = [x for x in r10['source_roles'] if not set(x['refs']) & set(cells10)]
    r10['source_roles'] += [{'role': 'item_identifier', 'refs': [S + 'A10'], 'reason': 'item number'},
                            {'role': 'demand_content', 'refs': cells10[1:], 'reason': 'item cells (route test only)'}]
    x = copy.deepcopy(r10['items'][0])
    x['id'] = 'R004'
    x['values'][2], x['values'][3], x['values'][5], x['values'][16] = None, '產品，無熔絲開關，3P，50AT', 1, 900
    x['proofs'].update(C=nul('no glossary device'), D=nn([S + 'B10'], 'copied', 'description'), E=nn([S + 'C10'], 'copied', 'unit cell'),
                       F=nn([S + 'D10'], 'copied', 'quantity cell'), Q=nn([S + 'E10'], 'copied', 'unit price'))
    x['raw_refs'] = raw(desc=[S + 'B10'], unit=[S + 'C10'], qty=[S + 'D10'], price=[S + 'E10'], amount=[S + 'F10'], reasons={'remarks': 'empty'})
    x['anchor_refs'] = [S + 'A10']
    r10['items'].append(x)
    (OUT / 'valid_response_scoped_nototal_row10.json').write_bytes(enc(r10))
    _, wraw = o72_inventory(WHOLE_SPECS, WHOLE_FLAGS, whole_payload())
    (OUT / 'fixture_inventory_whole.json').write_bytes(wraw)
    wbase = whole_response(hashlib.sha256(wraw).hexdigest())
    (OUT / 'valid_response_whole.json').write_bytes(enc(wbase))
    # a response citing a cell of the other in-scope sheet passes on the whole-workbook packet (an item on sheet 2, route test only)
    w2 = copy.deepcopy(wbase)
    y = copy.deepcopy(w2['items'][1])
    M2 = 'cell:S2!A2'
    y['id'] = 'R003'
    y['values'][3], y['values'][4], y['values'][5], y['values'][16] = '示例內容第二行', None, None, None
    y['proofs'].update(D=nn([M2], 'copied description', 'route test only'), E=nul('no unit cell'), F=nul('no quantity cell'),
                       Q=nul('no price on this line'))
    y['raw_refs'] = raw(desc=[M2], reasons={'unit': 'no unit cell', 'quantity': 'no quantity cell', 'unit_price': 'no price cell',
                                            'amount': 'no amount cell', 'remarks': 'no remarks cell'})
    y['anchor_refs'] = [M2]
    w2['items'].append(y)
    w2['source_roles'] = [x for x in w2['source_roles'] if x['refs'] != [M2]]
    w2['source_roles'].append({'role': 'demand_content', 'refs': [M2], 'reason': 'memo line cited by R003 (route test only)'})
    (OUT / 'valid_response_whole_cites_sheet2.json').write_bytes(enc(w2))

    def inv_mut(name, code, specs, flags, payload, base_fn, fact_value=None):
        _, vraw = o72_inventory(specs, flags, payload, fact_value)
        (OUT / f'inv_{name}.json').write_bytes(vraw)
        (OUT / f'mut_{name}.json').write_bytes(enc(base_fn(hashlib.sha256(vraw).hexdigest())))
        index.append({'name': name, 'file': f'mut_{name}.json', 'expected_code': code, 'inventory': f'inv_{name}.json'})
    def nsheet(i, **o):
        d = nototal_payload()
        d['sheets'][i].update(o)
        return d
    def wsheet(i, flags=None, **o):
        d = whole_payload(flags)
        d['sheets'][i].update(o)
        return d
    bad, mm = 'R59_SCOPE_FACT_INVALID', 'R59_SCOPE_FACT_MISMATCH'
    NS, NF, WS, WF = NOTOTAL_SPECS, NOTOTAL_FLAGS, WHOLE_SPECS, WHOLE_FLAGS
    inv_mut('v44_nototal_end_row_not_last_content_row', mm, NS, NF, nototal_payload(end_row=9), nototal_response)
    inv_mut('v44_nototal_two_bills', mm, NS, NF, nsheet(2, role='bill'), nototal_response)
    inv_mut('v44_nototal_stand_in_agreement', bad, NS, NF, nototal_payload(agreement='tool_and_stand_in_agreed'), nototal_response)
    inv_mut('v44_nototal_null_end_row', bad, NS, NF, nototal_payload(end_row=None), nototal_response)
    inv_mut('v44_whole_bill_index_not_null', bad, WS, WF, whole_payload(bill_sheet_index=1), whole_response)
    inv_mut('v44_whole_header_row_not_null', bad, WS, WF, whole_payload(bill_header_row=2), whole_response)
    inv_mut('v44_whole_end_row_not_null', bad, WS, WF, whole_payload(end_row=5), whole_response)
    inv_mut('v44_whole_role_bill', mm, WS, WF, wsheet(0, role='bill'), whole_response)
    inv_mut('v44_whole_nonempty_sheet_out_of_scope', mm, WS, {1: True, 2: False, 3: False},
            whole_payload({1: True, 2: False, 3: False}), whole_response)
    inv_mut('v44_whole_empty_sheet_in_scope', mm, WS, {1: True, 2: True, 3: True}, whole_payload({1: True, 2: True, 3: True}), whole_response)
    inv_mut('v44_whole_linked_blocks', mm, WS, WF, wsheet(0, linked_analysis_blocks=1), whole_response)
    inv_mut('v44_unknown_bill_rule', bad, WS, WF, whole_payload(bill_rule='BILL1.NOHEADER.v2'), whole_response)
    inv_mut('v44_whole_stand_in_agreement', bad, WS, WF, whole_payload(agreement='tool_and_stand_in_agreed'), whole_response)
    def wcite(name, f):
        r = copy.deepcopy(wbase)
        f(r)
        (OUT / f'mut_{name}.json').write_bytes(enc(r))
        index.append({'name': name, 'file': f'mut_{name}.json', 'expected_code': 'R59_SCOPE_FACT_CITED', 'inventory': 'fixture_inventory_whole.json'})
    wcite('v44_whole_scope_cited_proof', lambda r: r['items'][0]['proofs']['D'].update(refs=['cell:S1!B3', 'context:scope']))
    def ncite(r):
        r['items'][0]['proofs']['D'].update(refs=['cell:S2!B3', 'context:scope'])
    r = copy.deepcopy(nbase)
    ncite(r)
    (OUT / 'mut_v44_nototal_scope_cited_proof.json').write_bytes(enc(r))
    index.append({'name': 'v44_nototal_scope_cited_proof', 'file': 'mut_v44_nototal_scope_cited_proof.json', 'expected_code': 'R59_SCOPE_FACT_CITED',
                  'inventory': 'fixture_inventory_scoped_nototal.json'})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inv, inv_raw = build_inventory('unverified')
    (OUT / 'fixture_inventory.json').write_bytes(inv_raw)
    _, jinv_raw = build_inventory('unverified', job_inputs=True)
    (OUT / 'fixture_inventory_jobs.json').write_bytes(jinv_raw)
    jinv_sha = hashlib.sha256(jinv_raw).hexdigest()
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
    jobs = job_input_response(base, jinv_sha)
    (OUT / 'valid_response_job_inputs.json').write_bytes(enc(jobs))
    # route v4.1 relaxations (R52/R57 C null research_draft; R54/O16 Q under unverified adoption; R56 one-member group)
    inv_p, inv_p_raw = build_inventory('partial')
    (OUT / 'fixture_inventory_partial.json').write_bytes(inv_p_raw)
    inv_sha = hashlib.sha256(inv_raw).hexdigest()
    r57 = r57_response(base)
    (OUT / 'valid_response_r57_null_c.json').write_bytes(enc(r57))
    (OUT / 'valid_response_q_unverified.json').write_bytes(enc(q_response(base, inv_sha)))
    (OUT / 'valid_response_q_partial.json').write_bytes(enc(q_response(base, hashlib.sha256(inv_p_raw).hexdigest())))
    (OUT / 'valid_response_relaxed_all.json').write_bytes(enc(job_input_response(q_response(r57, inv_sha), jinv_sha)))
    (OUT / 'valid_response_one_member_group.json').write_bytes(enc(one_member_group_response(base)))
    cases, raws = mutations(base)
    index = []
    # route v4.1: the relaxations keep the null-reason requirement and every Q consistency check
    def rm(name, code, f, src=r57):
        rr = copy.deepcopy(src)
        f(rr)
        (OUT / f'mut_{name}.json').write_bytes(enc(rr))
        index.append({'name': name, 'file': f'mut_{name}.json', 'expected_code': code})
    def ri(rr, i):
        return next(x for x in rr['items'] if x['id'] == i)
    rm('v41_null_C_research_draft_no_reason', 'NULL_PROOF_REQUIRED', lambda rr: ri(rr, 'R003')['proofs'].update(C={}))
    rm('v41_null_C_research_draft_blank_reason', 'NONBLANK_STRING_REQUIRED', lambda rr: ri(rr, 'C001')['proofs'].update(C={'reason': '　'}))
    rm('v41_null_C_research_draft_reason_with_refs', 'NULL_PROOF_REQUIRED',
       lambda rr: ri(rr, 'R003')['proofs'].update(C={'reason': 'x', 'refs': ['cell:S1!B7']}))
    rm('v41_null_C_status_partial', 'ITEM_STATUS', lambda rr: ri(rr, 'R003').update(status='partial'))
    q_src = q_response(base, inv_sha)
    rm('v41_Q_unverified_amount_not_unit_price', 'SOURCE_UNIT_PRICE_MISMATCH',
       lambda rr: (ri(rr, 'R002')['values'].__setitem__(16, 361.5), ri(rr, 'R002')['proofs'].update(Q=nn(['cell:S1!F6'], 'copied', 'amount'))), q_src)
    rm('v41_Q_unverified_text_cell', 'NONNUMERIC_SOURCE_TEXT_FIELD_MUST_BE_NULL',
       lambda rr: ri(rr, 'R006')['proofs'].update(Q=nn(['cell:S1!B12'], 'copied', 'unit price')), q_src)
    rm('v41_Q_unverified_as_text', 'FINITE_SAFE_NUMBER_REQUIRED', lambda rr: ri(rr, 'R006')['values'].__setitem__(16, '50000'), q_src)
    # route v4 (O13): only L, M and N may be proven by context alone
    def jm(name, code, f, inventory='fixture_inventory_jobs.json'):
        rr = copy.deepcopy(jobs)
        f(rr)
        if inventory != 'fixture_inventory_jobs.json':
            _, vraw = build_inventory('unverified', job_inputs=True, drop_facts=('context:case_identity',))
            (OUT / inventory).write_bytes(vraw)
            rr['inventory_sha256'] = hashlib.sha256(vraw).hexdigest()
        (OUT / f'mut_{name}.json').write_bytes(enc(rr))
        index.append({'name': name, 'file': f'mut_{name}.json', 'expected_code': code, 'base': 'valid_response_job_inputs.json',
                      'inventory': inventory})
    def ji(rr, i):
        return next(x for x in rr['items'] if x['id'] == i)
    def ctx_only(col, value, ref, iid='R002'):
        def f(rr):
            it = ji(rr, iid)
            it['values'][COLS.index(col)] = value
            it['proofs'][col] = nn([ref], 'copied context fact', 'context only')
        return f
    jm('v4_I_brand_table_only', 'CONTEXT_ONLY_PROOF_UNREPRESENTABLE', ctx_only('I', 'XM-10', 'context:brand_table'))
    jm('v4_J_brand_table_only', 'CONTEXT_ONLY_PROOF_UNREPRESENTABLE', ctx_only('J', '示例甲牌', 'context:brand_table'))
    jm('v4_C_glossary_only', 'CONTEXT_ONLY_PROOF_UNREPRESENTABLE', ctx_only('C', 'XS', 'context:glossary'))
    jm('v4_J_company_name_only', 'CONTEXT_ONLY_PROOF_UNREPRESENTABLE', ctx_only('J', COMPANY, 'context:company_name'))
    jm('v4_K_company_name_only', 'CONTEXT_ONLY_PROOF_UNREPRESENTABLE', ctx_only('K', COMPANY, 'context:company_name'))
    jm('v4_D_project_name_only', 'CONTEXT_ONLY_PROOF_UNREPRESENTABLE', ctx_only('D', PROJECT_NAME, 'context:project_name'))
    jm('v4_M_unknown_context', 'UNKNOWN_CONTEXT_REF', ctx_only('M', CUSTOMER, 'context:customer'))
    jm('v4_N_numeric_value', 'STRING_REQUIRED', ctx_only('N', 7, 'context:project_name'))
    # route v4.2 (R48, R56, R58; 046f review S12): policy checks on the job packet, one defect each
    S = 'cell:S1!'
    def set_field(iid, col, value, proof):
        def f(rr):
            it = ji(rr, iid)
            it['values'][COLS.index(col)] = value
            it['proofs'][col] = proof
        return f
    jm('v42_L_null', 'R48_JOB_INPUT_REQUIRED', set_field('R002', 'L', None, nul('not given')))
    jm('v42_component_M_null', 'R48_JOB_INPUT_REQUIRED', set_field('C001', 'M', None, nul('not given')))
    jm('v42_M_from_label_cell', 'R48_JOB_INPUT_REF', set_field('R002', 'M', '訂購客戶：示例自來水處', nn([S + 'A13'], 'copied label cell', 'customer label')))
    jm('v42_N_context_plus_cell', 'R48_JOB_INPUT_REF', set_field('R003', 'N', PROJECT_NAME,
                                                                 nn(['context:project_name', S + 'A14'], 'copied job input', 'project name')))
    jm('v42_L_cites_customer_fact', 'R48_JOB_INPUT_REF', set_field('R004', 'L', 'FIXTURE01', nn(['context:customer_name'], 'copied', 'case id')))
    jm('v42_N_value_mismatch', 'R48_JOB_INPUT_VALUE_MISMATCH', set_field('R005', 'N', '示例淨水場', nn(['context:project_name'], 'copied', 'project name')))
    jm('v42_K_nonnull', 'R48_FIELD_MUST_BE_NULL', set_field('R002', 'K', '示例電機行', nn([S + 'A15'], 'text after label', 'supplier label')))
    jm('v42_O_nonnull', 'R48_FIELD_MUST_BE_NULL', set_field('R005', 'O', '2026-12-01', nn([S + 'A16'], 'text after label', 'date label')))
    jm('v42_P_nonnull', 'R48_FIELD_MUST_BE_NULL', set_field('R006', 'P', 2, nn([S + 'B17'], 'copied', 'required quantity')))
    def second_member(rr):
        it = ji(rr, 'R002')
        it['group_id'] = 'G1'
        it['values'][0], it['values'][1] = '示例控制盤', 'W600×H800×D300'
        it['proofs']['A'] = nn([S + 'B3'], 'copied group heading', 'group heading')
        it['proofs']['B'] = nn([S + 'C3'], 'copied group specification', 'group heading dimension')
    jm('v42_group_second_member', 'R56_GROUP_ONE_MEMBER_REQUIRED', second_member)
    jm('v42_group_contractual', 'R56_GROUP_RELATIONSHIP', lambda rr: rr['groups'][0].update(relationship='contractual_group'))
    def empty_group(rr):
        rr['groups'].append(dict(copy.deepcopy(rr['groups'][0]), id='G2', anchor_refs=[S + 'A3']))
    jm('v42_group_without_member', 'R56_GROUP_ONE_MEMBER_REQUIRED', empty_group)
    jm('v42_J_company_name_mismatch', 'R56_J_COMPANY_NAME_MISMATCH',
       set_field('R004', 'J', '別的公司', nn([S + 'B8', 'context:company_name'], 'company name', 'enclosure row')))
    jm('v42_job_fact_missing', 'R48_JOB_INPUT_FACT_MISSING', lambda rr: None, inventory='inv_v42_no_case_identity.json')
    # 046g pass 2 controls: without the fact, a citation of context:scope keeps its v4.2 codes (compared with v4.2 byte for byte)
    jm('noscope_scope_ref_in_proof', 'UNKNOWN_CONTEXT_REF', lambda rr: ji(rr, 'R002')['proofs']['C']['refs'].append('context:scope'))
    jm('noscope_scope_ref_in_raw', 'UNKNOWN_CELL_REF',
       lambda rr: ji(rr, 'R002')['raw_refs'].update(remarks={'refs': ['cell:S1!G6', 'context:scope'], 'reason_if_empty': None}))
    def legacy_j_mismatch(r):          # the J/company-name check (v4.2) applies on every inventory
        rr = copy.deepcopy(r)
        set_field('R004', 'J', '別的公司', nn([S + 'B8', 'context:company_name'], 'company name', 'enclosure row'))(rr)
        return rr
    cases.append(('v42_J_company_name_mismatch_legacy', 'R56_J_COMPANY_NAME_MISMATCH', legacy_j_mismatch))
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
    scoped_fixtures(enc, index)          # route v4.3 (R59)
    o72_fixtures(enc, index)             # route v4.4 (046i, owner decision O72)
    (OUT / 'MUTATIONS.json').write_text(json.dumps({'expected_canonical': EXPECT_CANON, 'mutations': index}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'mutations': len(index)}))


if __name__ == '__main__':
    main()
