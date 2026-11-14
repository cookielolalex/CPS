"""Empty-sheet tests for the 046i scope stage (harness/BUGFIX_EMPTY_SHEETS.md) with invented workbooks only.

The builders write a sheet with rows x columns = 0 as in_scope false. scope_tool.py v2 and make_scoped_inventory.py
refused every inventory with an in_scope-false sheet (FULL_INVENTORY_REQUIRED), so a workbook with an empty sheet could
not be prepared. This suite writes invented workbooks, each with and without empty sheets (one of them hidden), in
both formats (.xlsx written directly, .xls converted from it by LibreOffice), runs make_job_config.py and the builder of
each format exactly as the job runner does (the unbound inventory stands in for render_views.py, which only binds view
image pins), and checks that a workbook with empty sheets prepares exactly like the same workbook without them:
  - small job (at most 2,500 content cells): scope_tool.py NOT_APPLIED with the same values; the route's check-inventory
    on the full packet gives the same result; the empty sheets stay out of scope in the proposal, as in the packet;
  - large job: scope_tool.py PROPOSED with the same bill sheet, end row, R51 values, roles, in_scope flags, flags and
    holds; the same digest apart from the empty sheets' own entries; the same rules excerpt; scope_agree.py freezes the
    same scope fact (an agreeing invented reader); make_scoped_inventory.py builds the same scoped packet (cells, views,
    sheets and context facts after removing the empty sheets and renumbering the sheet indexes), --verify PASS with the
    pinned hash, and the route's check-inventory on the scoped packet gives the same result (scope applied).
It also checks the refusals that must not change: an already-scoped inventory (a non-empty sheet out of scope, with or
without context:scope) and an empty sheet that carries a view or a cell. No project data is read.
046i (owner decision O72): the tool version is cps046i-scope-tool.v4, and two more large pairs check that empty sheets
change nothing on the new bill rules: NT4 (a bill with a six-label header and no 合計/總計 row: BILL1.NOTOTAL.v1, the scope
to its last content row) and NH3 (a list whose header has four of the six labels, a summary sheet and a hidden memo
sheet: BILL1.NOHEADER.v1, the whole workbook in scope except the empty sheets).

Usage: python3 -I -B run_empty_sheet_tests.py --work /abs/NEWDIR --deps-bundle /abs/BUNDLE [--soffice soffice]
  --deps-bundle: the builders' bundle (private/deps with openpyxl 3.1.5 and xlrd 2.0.2, PORTABLE_SOURCE_INPUTS.json and
  the legacy BIFF helper it pins), as in the release's source_prep.deps_bundle.
"""
import argparse, copy, hashlib, json, re, shutil, subprocess, sys, zipfile
from pathlib import Path
from xml.sax.saxutils import escape

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
H = HERE.parent / 'harness'
PKG = HERE.parent / 'package'
ROUTE = PKG / 'tools' / 'cps046b_route.py'
TOOL, AGREE, SCOPED, JOBCFG = H / 'scope_tool.py', H / 'scope_agree.py', H / 'make_scoped_inventory.py', H / 'make_job_config.py'
CUSTOMER, PROJECT, COMPANY = '示例縣自來水事業處', '示例淨水場控制盤更新', '示例機電股份有限公司'   # invented (the package example's)
EMPTY_REASON = 'other: an empty sheet (rows x columns = 0, no cell), which the builders write out of scope; never yields rows (R49)'
LIST_KEYS = ('cells', 'sheets', 'views', 'context_facts', 'limitations')
results = []


def record(name, ok, detail=None):
    results.append({'test': name, 'pass': bool(ok), **({'detail': detail} if detail is not None and not ok else {})})


def sha(b):
    return hashlib.sha256(b).hexdigest()


def run(script, *args, flags=('-I', '-B')):
    p = subprocess.run([sys.executable, *flags, str(script), *map(str, args)], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def jout(text):
    try:
        return json.loads(text)
    except ValueError:
        return {}


def serialize(inv):
    """The builders' serialization (one record per line)."""
    def dump(x):
        return json.dumps(x, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    parts = []
    for k, v in inv.items():
        if k in LIST_KEYS and isinstance(v, list):
            body = ',\n'.join('  ' + dump(x) for x in v)
            parts.append(f' {dump(k)}:[\n{body}\n ]' if v else f' {dump(k)}:[]')
        else:
            parts.append(f' {dump(k)}:{dump(v)}')
    return ('{\n' + ',\n'.join(parts) + '\n}\n').encode('utf-8')


# ------------------------------------------------------------------ invented workbooks
def col_no(addr):
    n = 0
    for ch in addr:
        if ch.isalpha():
            n = n * 26 + ord(ch) - 64
    return n


def num(v):
    return repr(v) if isinstance(v, float) else str(v)


def write_xlsx(path, sheets):
    """A minimal .xlsx: sheets = [(name, [(address, value, is_cached_formula)], merges, state)]; a sheet without cells is
    written with an empty sheetData (an empty sheet); state is visible or hidden."""
    main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel_ns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    pkg_rel = 'http://schemas.openxmlformats.org/package/2006/relationships'
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    ct += [f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
           'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(sheets))]
    ct.append('</Types>')
    active = next(i for i, s in enumerate(sheets) if s[3] == 'visible')
    wb = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{main}" xmlns:r="{rel_ns}">'
          f'<bookViews><workbookView activeTab="{active}" firstSheet="{active}"/></bookViews><sheets>']
    wrels = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{pkg_rel}">']
    for i, (name, _, _, state) in enumerate(sheets):
        st = '' if state == 'visible' else f' state="{state}"'
        wb.append(f'<sheet name="{escape(name)}" sheetId="{i + 1}"{st} r:id="rId{i + 1}"/>')
        wrels.append(f'<Relationship Id="rId{i + 1}" Type="{rel_ns}/worksheet" Target="worksheets/sheet{i + 1}.xml"/>')
    wb.append('</sheets></workbook>')
    wrels.append(f'<Relationship Id="rId{len(sheets) + 1}" Type="{rel_ns}/styles" Target="styles.xml"/></Relationships>')
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="{main}">'
              '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
              '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ''.join(ct))
        z.writestr('_rels/.rels', f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{pkg_rel}">'
                                  f'<Relationship Id="rId1" Type="{rel_ns}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', ''.join(wb))
        z.writestr('xl/_rels/workbook.xml.rels', ''.join(wrels))
        z.writestr('xl/styles.xml', styles)
        for i, (_, cells, merges, _) in enumerate(sheets):
            rows = {}
            for addr, v, f in cells:
                rows.setdefault(int(''.join(ch for ch in addr if ch.isdigit())), []).append((col_no(addr), addr, v, f))
            out = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="{main}"><sheetData>']
            for r in sorted(rows):
                out.append(f'<row r="{r}">')
                for _, addr, v, f in sorted(rows[r]):
                    if f and isinstance(v, str):
                        out.append(f'<c r="{addr}" t="str"><f>A1</f><v>{escape(v)}</v></c>')
                    elif f:
                        out.append(f'<c r="{addr}"><f>SUM(A1)</f><v>{num(v)}</v></c>')
                    elif isinstance(v, str):
                        out.append(f'<c r="{addr}" t="inlineStr"><is><t xml:space="preserve">{escape(v)}</t></is></c>')
                    else:
                        out.append(f'<c r="{addr}"><v>{num(v)}</v></c>')
                out.append('</row>')
            out.append('</sheetData>')
            if merges:
                out.append(f'<mergeCells count="{len(merges)}">' + ''.join(f'<mergeCell ref="{m}"/>' for m in merges) + '</mergeCells>')
            out.append('</worksheet>')
            z.writestr(f'xl/worksheets/sheet{i + 1}.xml', ''.join(out))


def small_sheet():
    """The invented 材料清單 sheet of the package example (EXAMPLE_INVENTORY.json), literal and cached-formula cells."""
    ex = json.loads((PKG / 'resources' / 'EXAMPLE_INVENTORY.json').read_text(encoding='utf-8'))
    cells = [(c['address'], c['saved_value'], c['state'] == 'cached_formula') for c in ex['cells'] if c['state'] in ('literal', 'cached_formula')]
    sh = ex['sheets'][0]
    glossary = json.loads(next(f['value'] for f in ex['context_facts'] if f['ref'] == 'context:glossary'))
    return (sh['name'], cells, sh['merges'], 'visible'), glossary


def large_sheets(items=450):
    """An invented summary sheet and a priced bill sheet (項次/項目及說明/單位/數量/單價/複價, 合計 in the price column)
    with more than 2,500 content cells."""
    summary = [('A1', '項次', False), ('B1', '項目及說明', False), ('C1', '複價', False), ('A2', '壹', False), ('B2', '示例詳細表', False),
               ('C2', 900000, True)]
    bill = [('A1', '示例工程 詳細價目表', False)] + [(c + '2', t, False) for c, t in zip('ABCDEF', ('項次', '項目及說明', '單位', '數量', '單價', '複價'))]
    for i in range(items):
        r = 3 + i
        bill += [(f'A{r}', str(i + 1), False), (f'B{r}', f'示例材料第{i + 1}項，規格{i % 7 + 1}', False), (f'C{r}', '只', False),
                 (f'D{r}', i % 5 + 1, False), (f'E{r}', 100 + i, False), (f'F{r}', (i % 5 + 1) * (100 + i), True)]
    bill += [(f'E{3 + items}', '合計', False), (f'F{3 + items}', 123456, True)]
    return [('總表', summary, [], 'visible'), ('詳細表', bill, [], 'visible')], 3 + items


def empty(name, state='visible'):
    return (name, [], [], state)


# ------------------------------------------------------------------ job preparation, as the runner does it
class Env:
    def __init__(self, work, bundle, soffice):
        self.work, self.bundle, self.soffice = work, bundle, soffice
        self.tables = work / 'tables'
        self.tables.mkdir()
        self.glossary = self.tables / 'GLOSSARY.json'
        self.brand = self.tables / 'BRAND_TABLE.json'
        self.brand.write_text(json.dumps({'schema': 'cps.company-brand-table.v1', 'entries': [
            {'device': '示例斷路器', 'rating_band': '示例額定', 'brand': '示例廠牌', 'model': 'EX-0001'}]}, ensure_ascii=False, indent=1) + '\n',
            encoding='utf-8')

    def source(self, tag, sheets, fmt):
        d = self.work / 'sources' / tag
        d.mkdir(parents=True)
        x = d / 'source.xlsx'
        write_xlsx(x, sheets)
        if fmt == 'xlsx':
            return x
        prof = self.work / 'lo_profile'
        p = subprocess.run([self.soffice, f'-env:UserInstallation=file://{prof}', '--headless', '--convert-to', 'xls', '--outdir', str(d / 'xls'), str(x)],
                           capture_output=True, text=True, timeout=300)
        out = d / 'xls' / 'source.xls'
        if p.returncode != 0 or not out.is_file():
            raise RuntimeError('LibreOffice conversion failed: ' + (p.stderr or p.stdout)[-300:])
        return out

    def prepare(self, tag, src, kind, case):
        """make_job_config.py, then the builder of the source's format (python3 -I -S -B), as runner v4 prepare."""
        d = self.work / 'jobs' / tag
        d.mkdir(parents=True)
        job = {'schema': 'cps.job-config.v2', 'case_id': case, 'customer_name': CUSTOMER, 'project_name': PROJECT, 'company_name': COMPANY,
               'glossary_path': str(self.glossary), 'source_path': str(src), 'source_kind': kind,
               'carrier_path': f'X:\\Fixtures\\invented\\{case}-source{src.suffix}',
               **({'brand_table_path': str(self.brand)} if kind == 'contract' else {})}
        jp = d / 'JOB.json'
        jp.write_text(json.dumps(job, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        code, out, err = run(JOBCFG, '--job', jp, '--out', d / 'BUILDER_CONFIG.json')
        if code != 0:
            raise RuntimeError('make_job_config refused: ' + err[-300:])
        cfg = json.loads((d / 'BUILDER_CONFIG.json').read_text(encoding='utf-8'))
        code, out, err = run(REPO / cfg['builder'], '--bundle', self.bundle, '--config', d / 'BUILDER_CONFIG.json', '--out', d / 'full',
                             flags=('-I', '-S', '-B'))
        if code != 0:
            raise RuntimeError('builder failed: ' + err[-300:])
        inv = d / 'full' / 'SOURCE_INVENTORY.json'          # render_views.py only binds the image pins; none are needed here
        shutil.copyfile(d / 'full' / 'SOURCE_INVENTORY.unbound.json', inv)
        return d, inv


def check_inventory(inv):
    code, out, _ = run(ROUTE, 'check-inventory', '--inventory', inv)
    d = jout(out)
    return {'exit': code, 'status': d.get('status'), 'route': d.get('route'), 'scope': d.get('scope'), 'policy_checks': d.get('policy_checks'),
            'violations': sorted({v['code'] for v in d.get('violations', [])}), 'warnings': sorted({w['code'] for w in d.get('warnings', [])})}


def reader_for(prop, dig, flip=None):
    p = json.loads(prop.read_text(encoding='utf-8'))
    r = {'schema': 'cps.scope-reader-response.v1', 'case_id': p['case_id'], 'digest_sha256': sha(dig.read_bytes()),
         'reader': {'kind': 'fresh_context_scope_reader', 'model': 'invented-test-reader', 'effort': 'n/a'},
         'bill_sheet_index': p['bill']['sheet_index'], 'end_row': p['bill']['end_row'],
         'sheets': [{'index': s['index'], 'role': s['role'], 'in_scope': s['in_scope'] if s['index'] != flip else not s['in_scope'],
                     'reason': 'invented test reason'} for s in p['sheets']], 'doubts': []}
    return r


def scope_stage(d, inv, flip=None):
    """The runner's scope stage on one full inventory: tool, (agreeing invented reader), agree, build, --verify, check-inventory."""
    res = {'d': d}
    code, out, err = run(TOOL, '--inventory', inv, '--out-dir', d / 'tool')
    res.update(tool_code=code, tool_out=jout(out), tool_err=err)
    if code != 0:
        return res
    prop, dig = d / 'tool' / 'SCOPE_PROPOSAL.json', d / 'tool' / 'SCOPE_DIGEST.json'
    res['proposal'] = json.loads(prop.read_text(encoding='utf-8'))
    if res['proposal']['status'] != 'PROPOSED':
        return res
    res['digest'] = json.loads(dig.read_text(encoding='utf-8'))
    res['excerpt'] = (d / 'tool' / 'SCOPE_RULES_EXCERPT.md').read_bytes()
    rp = d / 'SCOPE_READER_RESPONSE.json'
    rp.write_text(json.dumps(reader_for(prop, dig, flip), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    code, out, err = run(AGREE, '--proposal', prop, '--digest', dig, '--reader', rp, '--out-dir', d / 'decision')
    res.update(agree_code=code, agree_out=jout(out), agree_err=err)
    if code != 0:
        return res
    dec = d / 'decision' / 'SCOPE_DECISION.json'
    res['decision'] = json.loads(dec.read_text(encoding='utf-8'))
    code, out, err = run(SCOPED, '--full', inv, '--decision', dec, '--out-dir', d / 'scoped_packet')
    res.update(build_code=code, build_out=jout(out), build_err=err)
    if code != 0:
        return res
    scoped = d / 'scoped_packet' / 'SOURCE_INVENTORY.json'
    receipt = json.loads((d / 'scoped_packet' / 'SCOPED_INVENTORY_RECEIPT.json').read_text(encoding='utf-8'))
    code, out, err = run(SCOPED, '--verify', '--full', inv, '--decision', dec, '--scoped', scoped, '--expect-scoped-sha256', receipt['scoped_inventory_sha256'])
    res.update(scoped=scoped, receipt=receipt, verify_code=code, verify=jout(out), check_scoped=check_inventory(scoped))
    return res


# ------------------------------------------------------------------ normalisation: remove the empty sheets, renumber
def index_map(inv_with, inv_without):
    """with-variant sheet index -> without-variant index, by sheet name; and the set of empty sheet indexes."""
    names = {s['name']: s['index'] for s in inv_without['sheets']}
    m = {s['index']: names[s['name']] for s in inv_with['sheets'] if s['name'] in names}
    empties = {s['index'] for s in inv_with['sheets'] if s['name'] not in names}
    return m, empties


def norm_proposal(p, m, empties):
    p = copy.deepcopy(p)
    p.pop('full_inventory_sha256')
    if p.get('digest'):
        p['digest'] = {k: v for k, v in p['digest'].items() if k not in ('sha256', 'bytes')}
    p['sheets'] = [dict(s, index=m[s['index']]) for s in p['sheets'] if s['index'] not in empties]
    b = p['bill']
    b['candidates'] = [m[i] for i in b['candidates']]
    b['near_candidates'] = [m[i] for i in b['near_candidates']]
    b['per_sheet'] = {str(m[int(k)]): v for k, v in b['per_sheet'].items() if int(k) not in empties}
    b['sheet_index'] = m.get(b['sheet_index'])
    p['r51']['analysis_sheets'] = {str(m[int(k)]): v for k, v in p['r51']['analysis_sheets'].items()}
    p['flags'] = [dict(f, sheet_index=m.get(f['sheet_index'])) for f in p['flags']]     # 046i: BILL1_NO_HEADER has sheet_index null
    for h in p['holds']:
        if 'candidates' in h:
            h['candidates'] = [m[i] for i in h['candidates']]
    return p


def norm_digest(dg, m, empties):
    dg = copy.deepcopy(dg)
    dg.pop('full_inventory_sha256')
    dg['sheets'] = [dict(s, index=m[s['index']]) for s in dg['sheets'] if s['index'] not in empties]
    return dg


def norm_fact(f, m, empties):
    f = {k: v for k, v in f.items() if k not in ('digest_sha256', 'full_inventory_sha256', 'decision_sha256')}
    f['sheets'] = [dict(s, index=m[s['index']]) for s in f['sheets'] if s['index'] not in empties]
    f['bill_sheet_index'] = m.get(f['bill_sheet_index'])      # 046i: null under BILL1.NOHEADER.v1
    return f


def renumber_ref(ref, m):
    if ref is None:
        return None
    mm = re.fullmatch(r'cell:S(\d+)!(.+)', ref)
    return f'cell:S{m[int(mm[1])]}!{mm[2]}'


def norm_inventory(inv, m, empties):
    """The inventory without the empty sheets, sheet indexes renumbered; source hashes and context-fact provenance dropped
    (they name the source bytes and the job file), the scope fact normalised."""
    out = {'sheets': [dict(s, index=m[s['index']]) for s in inv['sheets'] if s['index'] not in empties],
           'cells': [dict(c, sheet_index=m[c['sheet_index']], ref=renumber_ref(c['ref'], m), merge_anchor_ref=renumber_ref(c['merge_anchor_ref'], m))
                     for c in inv['cells']],
           'views': inv['views'], 'carrier_views': inv['source']['carrier_source']['views'], 'limitations': inv['limitations'],
           'facts': []}
    for f in inv['context_facts']:
        if f['ref'] == 'context:scope':
            out['facts'].append(('context:scope', norm_fact(json.loads(f['value']), m, empties)))
        else:
            out['facts'].append((f['ref'], f['namespace'], f['value']))
    return out


def diff_keys(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return sorted({k for k in set(a) | set(b) if a.get(k) != b.get(k)})
    return ['<value>'] if a != b else []


# ------------------------------------------------------------------ tests
def pair_small(env, fmt, kind):
    base, glossary = small_sheet()
    if not env.glossary.exists():
        env.glossary.write_text(json.dumps(glossary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    tag = f'small_{fmt}'
    case = '9990901' if fmt == 'xlsx' else '9990902'
    with_ = env.source(tag + '_with', [empty('示例空白一'), base, empty('示例空白二', 'hidden')], fmt)
    without = env.source(tag + '_without', [base], fmt)
    dw, iw = env.prepare(tag + '_with', with_, kind, case)
    do, io = env.prepare(tag + '_without', without, kind, case)
    invw, invo = json.loads(iw.read_text(encoding='utf-8')), json.loads(io.read_text(encoding='utf-8'))
    m, empties = index_map(invw, invo)
    record(f'{tag}: the builder writes the two empty sheets with rows x columns = 0 and in_scope false (one hidden)',
           len(invw['sheets']) == 3 and sorted(empties) == [1, 3]
           and all(s['rows'] * s['columns'] == 0 and s['in_scope'] is False for s in invw['sheets'] if s['index'] in empties)
           and [s['visibility'] for s in invw['sheets']] == ['visible', 'visible', 'hidden'],
           [(s['index'], s['rows'], s['columns'], s['in_scope'], s['visibility']) for s in invw['sheets']])
    record(f'{tag}: the inventory with empty sheets equals the one without them after removing the empty sheets',
           norm_inventory(invw, m, empties) == norm_inventory(invo, {i: i for i in m.values()}, set()),
           diff_keys(norm_inventory(invw, m, empties), norm_inventory(invo, {i: i for i in m.values()}, set())))
    cw, co = check_inventory(iw), check_inventory(io)
    record(f'{tag}: route check-inventory on the full packet: same result (PASS, scope not_applied, policy_checks applied)',
           cw == co and cw['status'] == 'PASS' and cw['scope'] == 'not_applied' and cw['policy_checks'] == 'applied', [cw, co])
    rw, ro = scope_stage(dw, iw), scope_stage(do, io)
    record(f'{tag}: scope_tool.py accepts the inventory with empty sheets (exit 0, NOT_APPLIED, no digest)',
           rw['tool_code'] == 0 and rw['proposal']['status'] == 'NOT_APPLIED' and rw['proposal']['digest'] is None
           and not (dw / 'tool' / 'SCOPE_DIGEST.json').exists() and rw['proposal']['tool']['version'] == 'cps046i-scope-tool.v4',
           [rw['tool_code'], rw['tool_err'][-300:]])
    pw, po = rw.get('proposal', {}), ro.get('proposal', {})
    nw = norm_proposal(pw, m, empties) if pw else None
    no = norm_proposal(po, {i: i for i in m.values()}, set()) if po else None
    record(f'{tag}: the NOT_APPLIED proposal equals the one without empty sheets (after removing them)', nw == no and nw is not None, diff_keys(nw, no))
    record(f'{tag}: the proposal keeps each empty sheet out of scope, as in the packet, with role other, the empty reason and no flag',
           [(s['index'], s['in_scope']) for s in pw.get('sheets', [])] == [(s['index'], s['in_scope']) for s in invw['sheets']]
           and all(s['role'] == 'other' and s['reason'] == EMPTY_REASON and s['content_cells'] == 0 and s['linked_analysis_blocks'] == 0
                   for s in pw.get('sheets', []) if s['index'] in empties) and pw.get('flags') == [], pw.get('sheets'))
    skip = ('full_inventory_sha256', 'proposal_sha256', 'sheets', 'bill_candidates', 'bill_sheet_index')
    record(f'{tag}: the tool prints the same summary apart from the hashes and the empty sheets',
           {k: v for k, v in rw['tool_out'].items() if k not in skip} == {k: v for k, v in ro['tool_out'].items() if k not in skip}
           and [m[i] for i in rw['tool_out']['bill_candidates']] == ro['tool_out']['bill_candidates']
           and m.get(rw['tool_out']['bill_sheet_index']) == ro['tool_out']['bill_sheet_index']
           and [dict(s, index=m[s['index']]) for s in rw['tool_out']['sheets'] if s['index'] not in empties] == ro['tool_out']['sheets']
           and rw['tool_out'].get('values_printed') is False)


def pair_large(env, fmt):
    sheets, end_row = large_sheets()
    tag = f'large_{fmt}'
    case = '9990903' if fmt == 'xlsx' else '9990904'
    with_ = env.source(tag + '_with', [empty('示例空白甲'), sheets[0], empty('示例空白乙', 'hidden'), sheets[1]], fmt)
    without = env.source(tag + '_without', sheets, fmt)
    dw, iw = env.prepare(tag + '_with', with_, '材料清單', case)
    do, io = env.prepare(tag + '_without', without, '材料清單', case)
    invw, invo = json.loads(iw.read_text(encoding='utf-8')), json.loads(io.read_text(encoding='utf-8'))
    m, empties = index_map(invw, invo)
    ident = {i: i for i in m.values()}
    record(f'{tag}: the builder writes the empty sheets with rows x columns = 0 and in_scope false',
           sorted(empties) == [1, 3] and all(s['rows'] * s['columns'] == 0 and s['in_scope'] is False for s in invw['sheets'] if s['index'] in empties)
           and sum(1 for c in invw['cells'] if c['state'] in ('literal', 'cached_formula') and c['saved_value'] not in (None, '')) > 2500,
           [(s['index'], s['rows'], s['columns'], s['in_scope']) for s in invw['sheets']])
    record(f'{tag}: the full inventory with empty sheets equals the one without them after removing the empty sheets',
           norm_inventory(invw, m, empties) == norm_inventory(invo, ident, set()), diff_keys(norm_inventory(invw, m, empties), norm_inventory(invo, ident, set())))
    cw, co = check_inventory(iw), check_inventory(io)
    record(f'{tag}: route check-inventory on the full packet: same result', cw == co and cw['status'] == 'PASS' and cw['scope'] == 'not_applied', [cw, co])
    rw, ro = scope_stage(dw, iw), scope_stage(do, io)
    pw, po = rw.get('proposal', {}), ro.get('proposal', {})
    record(f'{tag}: scope_tool.py accepts the inventory with empty sheets: PROPOSED (exit 0)', rw['tool_code'] == 0 and pw.get('status') == 'PROPOSED'
           and po.get('status') == 'PROPOSED', [rw['tool_code'], rw['tool_err'][-300:]])
    if not pw:
        return
    nw, no = norm_proposal(pw, m, empties), norm_proposal(po, ident, set())
    record(f'{tag}: the proposal equals the one without empty sheets (bill sheet, end row, R51, roles, flags, holds, counts)', nw == no, diff_keys(nw, no))
    record(f'{tag}: bill sheet and end row as invented', pw['bill']['sheet_index'] == 4 and po['bill']['sheet_index'] == 2
           and pw['bill']['end_row'] == end_row == po['bill']['end_row'], [pw['bill']['sheet_index'], pw['bill']['end_row']])
    record(f'{tag}: the empty sheets are role other, out of scope, with the empty reason and no flag',
           all(s['role'] == 'other' and s['in_scope'] is False and s['reason'] == EMPTY_REASON for s in pw['sheets'] if s['index'] in empties)
           and not any(f['sheet_index'] in empties for f in pw['flags']), [pw['sheets'], pw['flags']])
    record(f'{tag}: the digest equals the one without empty sheets apart from their entries, which show 0 rows, 0 columns and no row',
           norm_digest(rw['digest'], m, empties) == norm_digest(ro['digest'], ident, set())
           and all(s['rows'] == 0 and s['columns'] == 0 and s['content_cells']['total'] == 0 and s['first_rows'] == [] and s['last_rows'] == []
                   for s in rw['digest']['sheets'] if s['index'] in empties),
           diff_keys(norm_digest(rw['digest'], m, empties), norm_digest(ro['digest'], ident, set())))
    record(f'{tag}: the scope reader rules excerpt is byte-identical', rw['excerpt'] == ro['excerpt'])
    record(f'{tag}: scope_agree.py freezes an admissible decision for both', rw.get('agree_code') == 0 and ro.get('agree_code') == 0
           and rw['agree_out'].get('status') == 'FROZEN_AGREED' and rw['agree_out'].get('admissible') is True, [rw.get('agree_err', '')[-300:]])
    if 'decision' not in rw or 'decision' not in ro:
        return
    fw, fo = rw['decision']['scope_fact'], ro['decision']['scope_fact']
    record(f'{tag}: the frozen scope fact equals the one without empty sheets (after removing them)',
           norm_fact(fw, m, empties) == norm_fact(fo, ident, set()), diff_keys(norm_fact(fw, m, empties), norm_fact(fo, ident, set())))
    record(f'{tag}: the decision records the same tool flags and role differences',
           [dict(f, sheet_index=m[f['sheet_index']]) for f in rw['decision']['tool_flags']] == ro['decision']['tool_flags']
           and rw['decision']['role_differences'] == ro['decision']['role_differences'])
    bw, bo = rw.get('build_out', {}), ro.get('build_out', {})
    record(f'{tag}: make_scoped_inventory.py builds the scoped packet (WRITTEN, self-verify PASS)', rw.get('build_code') == 0 and bw.get('status') == 'WRITTEN'
           and bw.get('verify') == 'PASS', [rw.get('build_code'), rw.get('build_err', '')[-300:]])
    if 'scoped' not in rw or 'scoped' not in ro:
        return
    sw = {k: v for k, v in bw['stats'].items() if k != 'sheets'}
    so = {k: v for k, v in bo['stats'].items() if k != 'sheets'}
    record(f'{tag}: the projection statistics equal those without empty sheets', sw == so and bw['stats']['sheets'] == bo['stats']['sheets'] + 2, [sw, so])
    record(f'{tag}: --verify PASS with the pinned scoped hash', rw['verify_code'] == 0 and rw['verify'].get('status') == 'PASS'
           and rw['verify'].get('problem_count') == 0, rw['verify'].get('problems'))
    record(f'{tag}: route check-inventory on the scoped packet: same result (PASS, scope applied, policy_checks applied)',
           rw['check_scoped'] == ro['check_scoped'] and rw['check_scoped']['status'] == 'PASS' and rw['check_scoped']['scope'] == 'applied'
           and rw['check_scoped']['policy_checks'] == 'applied', [rw['check_scoped'], ro['check_scoped']])
    record(f'{tag}: the receipt route check and the --verify route check are PASS for both', bw['route_check_inventory']['status'] == 'PASS'
           and rw['verify']['route_check_inventory']['status'] == 'PASS' and bo['route_check_inventory'] == {**bw['route_check_inventory']})
    scw, sco = json.loads(rw['scoped'].read_text(encoding='utf-8')), json.loads(ro['scoped'].read_text(encoding='utf-8'))
    record(f'{tag}: the scoped packet equals the one without empty sheets (cells, views, sheets, context facts) after removing them',
           norm_inventory(scw, m, empties) == norm_inventory(sco, ident, set()), diff_keys(norm_inventory(scw, m, empties), norm_inventory(sco, ident, set())))
    record(f'{tag}: the scoped packet keeps the empty sheets out of scope, without cells or views',
           all(s['in_scope'] is False for s in scw['sheets'] if s['index'] in empties)
           and not any(c['sheet_index'] in empties for c in scw['cells'])
           and not any(v['sheet'] in {s['name'] for s in scw['sheets'] if s['index'] in empties} for v in scw['views']))
    return {'dir': dw, 'full': iw, 'invw': invw, 'scoped': rw['scoped'], 'scw': scw, 'empties': empties, 'decision': dw / 'decision' / 'SCOPE_DECISION.json'}


def nt_sheets(items=450):
    """046i NT4: large_sheets without the 合計 cell: one six-label header, no 合計/總計 in a price column (BILL1.NOTOTAL.v1)."""
    sheets, end = large_sheets(items)
    name, cells, merges, state = sheets[1]
    return [sheets[0], (name, [c for c in cells if c[0] != f'E{end}'], merges, state)], end


def nh_sheets(items=450):
    """046i NH3: a priced list headed 序號/品名規格/單位/數量/單價/金額 (four of the six BILL1 labels), the summary sheet and a
    hidden memo sheet: no sheet has a BILL1 header row (BILL1.NOHEADER.v1)."""
    lst = [('A1', '示例工程 價目表', False)] + [(c + '2', x, False) for c, x in zip('ABCDEF', ('序號', '品名規格', '單位', '數量', '單價', '金額'))]
    for i in range(items):
        r = 3 + i
        lst += [(f'A{r}', str(i + 1), False), (f'B{r}', f'示例材料第{i + 1}項，規格{i % 7 + 1}', False), (f'C{r}', '只', False),
                (f'D{r}', i % 5 + 1, False), (f'E{r}', 100 + i, False), (f'F{r}', (i % 5 + 1) * (100 + i), True)]
    lst += [(f'E{3 + items}', '合計', False), (f'F{3 + items}', 123456, True)]
    summary = large_sheets(1)[0][0]
    memo = ('示例說明', [('A1', '示例說明', False), ('A2', '示例內容第二行', False)], [], 'hidden')
    return [('價目表', lst, [], 'visible'), summary, memo]


def pair_o72(env, fmt, variant):
    """046i: a large O72 workbook with and without empty sheets prepares the same way (proposal, digest, excerpt, decision,
    scoped packet, verify, route check-inventory)."""
    tag = f'{variant}_{fmt}'
    case = {('nt4', 'xlsx'): '9990905', ('nt4', 'xls'): '9990906', ('nh3', 'xlsx'): '9990907', ('nh3', 'xls'): '9990908'}[(variant, fmt)]
    if variant == 'nt4':
        sheets, end_row = nt_sheets()
        with_sheets = [empty('示例空白甲'), sheets[0], empty('示例空白乙', 'hidden'), sheets[1], empty('示例空白丙')]
    else:
        sheets, end_row = nh_sheets(), None
        with_sheets = [empty('示例空白甲'), sheets[0], empty('示例空白乙', 'hidden'), sheets[1], sheets[2]]
    dw, iw = env.prepare(tag + '_with', env.source(tag + '_with', with_sheets, fmt), '材料清單', case)
    do, io = env.prepare(tag + '_without', env.source(tag + '_without', sheets, fmt), '材料清單', case)
    invw, invo = json.loads(iw.read_text(encoding='utf-8')), json.loads(io.read_text(encoding='utf-8'))
    m, empties = index_map(invw, invo)
    ident = {i: i for i in m.values()}
    record(f'{tag}: the builder writes the empty sheets with rows x columns = 0 and in_scope false',
           len(empties) == (3 if variant == 'nt4' else 2)
           and all(s['rows'] * s['columns'] == 0 and s['in_scope'] is False for s in invw['sheets'] if s['index'] in empties),
           [(s['index'], s['rows'], s['columns'], s['in_scope']) for s in invw['sheets']])
    rw, ro = scope_stage(dw, iw), scope_stage(do, io)
    pw, po = rw.get('proposal', {}), ro.get('proposal', {})
    rule = 'BILL1.NOTOTAL.v1' if variant == 'nt4' else 'BILL1.NOHEADER.v1'
    record(f'{tag}: scope_tool.py: PROPOSED under {rule} for both', rw['tool_code'] == 0 and ro['tool_code'] == 0 and pw.get('status') == 'PROPOSED'
           and po.get('status') == 'PROPOSED' and pw['bill']['rule'] == po['bill']['rule'] == rule and pw['tool']['version'] == 'cps046i-scope-tool.v4',
           [rw['tool_code'], rw['tool_err'][-300:], pw.get('bill')])
    if not pw or not po:
        return
    nw, no = norm_proposal(pw, m, empties), norm_proposal(po, ident, set())
    record(f'{tag}: the proposal equals the one without empty sheets (after removing them)', nw == no, diff_keys(nw, no))
    if variant == 'nt4':
        record(f'{tag}: bill sheet and end row (the last content row)', pw['bill']['sheet_index'] == 4 and po['bill']['sheet_index'] == 2
               and pw['bill']['end_row'] == end_row == po['bill']['end_row'] and pw['bill']['end_cell'] is None, pw['bill'])
    else:
        hid = next(s['index'] for s in invw['sheets'] if s['name'] == '示例說明')
        record(f'{tag}: every non-empty sheet in scope, the hidden memo flagged, no bill', pw['bill']['sheet_index'] is None and pw['bill']['end_row'] is None
               and [s['index'] for s in pw['sheets'] if s['in_scope']] == sorted(set(m) - empties)
               and {(f['sheet_index'], f['code']) for f in pw['flags']} >= {(None, 'BILL1_NO_HEADER'), (hid, 'HIDDEN_SHEET')}, [pw['sheets'], pw['flags']])
    record(f'{tag}: the empty sheets are role other, out of scope, with the empty reason and no flag',
           all(s['role'] == 'other' and s['in_scope'] is False and s['reason'] == EMPTY_REASON for s in pw['sheets'] if s['index'] in empties)
           and not any(f['sheet_index'] in empties for f in pw['flags']), [pw['sheets'], pw['flags']])
    record(f'{tag}: the digest equals the one without empty sheets apart from their entries',
           norm_digest(rw['digest'], m, empties) == norm_digest(ro['digest'], ident, set()),
           diff_keys(norm_digest(rw['digest'], m, empties), norm_digest(ro['digest'], ident, set())))
    record(f'{tag}: the scope reader rules excerpt is byte-identical', rw['excerpt'] == ro['excerpt'])
    if 'decision' not in rw or 'decision' not in ro:
        record(f'{tag}: scope_agree.py freezes an admissible decision for both', False, [rw.get('agree_err', '')[-300:], ro.get('agree_err', '')[-300:]])
        return
    fw, fo = rw['decision']['scope_fact'], ro['decision']['scope_fact']
    record(f'{tag}: the frozen scope fact equals the one without empty sheets (after removing them)', fw['bill_rule'] == rule
           and norm_fact(fw, m, empties) == norm_fact(fo, ident, set()), diff_keys(norm_fact(fw, m, empties), norm_fact(fo, ident, set())))
    if 'scoped' not in rw or 'scoped' not in ro:
        record(f'{tag}: make_scoped_inventory.py builds the scoped packet', False, [rw.get('build_err', '')[-300:]])
        return
    record(f'{tag}: --verify PASS with the pinned hash; check-inventory on the scoped packet: same result (PASS, scope applied)',
           rw['verify_code'] == 0 and rw['verify'].get('status') == 'PASS' and rw['check_scoped'] == ro['check_scoped']
           and rw['check_scoped']['status'] == 'PASS' and rw['check_scoped']['scope'] == 'applied', [rw['verify'].get('problems'), rw['check_scoped']])
    scw, sco = json.loads(rw['scoped'].read_text(encoding='utf-8')), json.loads(ro['scoped'].read_text(encoding='utf-8'))
    record(f'{tag}: the scoped packet equals the one without empty sheets after removing them, empty sheets out of scope',
           norm_inventory(scw, m, empties) == norm_inventory(sco, ident, set()) and all(s['in_scope'] is False for s in scw['sheets'] if s['index'] in empties),
           diff_keys(norm_inventory(scw, m, empties), norm_inventory(sco, ident, set())))
    if variant == 'nh3':
        sw = rw['receipt']['verify']['stats']
        record(f'{tag}: the whole-workbook projection removes no cell or view', sw['cells_removed'] == 0 and sw['views_removed'] == 0
               and sw['views_renumbered'] == 0, sw)


def refusals(env, lw):
    """The refusals that must not change, and the empty-sheet conditions (no cell, no view)."""
    work = env.work / 'refusals'
    work.mkdir()

    def tool_refuses(tag, raw, code_want):
        p = work / f'{tag}.json'
        p.write_bytes(raw)
        code, out, err = run(TOOL, '--inventory', p, '--out-dir', work / f'tool_{tag}')
        return code == 1 and jout(err).get('code') == code_want and not (work / f'tool_{tag}').exists(), [code, err[-200:]]

    def build_refuses(tag, raw, code_want):
        p = work / f'{tag}_b.json'
        p.write_bytes(raw)
        code, out, err = run(SCOPED, '--full', p, '--decision', lw['decision'], '--out-dir', work / f'build_{tag}')
        return code == 1 and jout(err).get('code') == code_want and not (work / f'build_{tag}').exists(), [code, err[-200:]]

    scoped_raw = lw['scoped'].read_bytes()
    ok, det = tool_refuses('scoped_packet', scoped_raw, 'FULL_INVENTORY_REQUIRED')
    record('scope_tool.py refuses the scoped packet of a workbook with empty sheets: FULL_INVENTORY_REQUIRED (non-empty sheet out of scope)', ok, det)
    ok, det = build_refuses('scoped_packet', scoped_raw, 'FULL_INVENTORY_REQUIRED')
    record('make_scoped_inventory.py refuses the scoped packet as a full inventory: FULL_INVENTORY_REQUIRED', ok, det)
    sc = copy.deepcopy(lw['scw'])
    sc['context_facts'] = [f for f in sc['context_facts'] if f['ref'] != 'context:scope']
    ok, det = tool_refuses('scoped_without_fact', serialize(sc), 'FULL_INVENTORY_REQUIRED')
    record('scope_tool.py refuses an already-scoped inventory without context:scope: FULL_INVENTORY_REQUIRED', ok, det)
    ok, det = build_refuses('scoped_without_fact', serialize(sc), 'FULL_INVENTORY_REQUIRED')
    record('make_scoped_inventory.py refuses an already-scoped inventory without context:scope: FULL_INVENTORY_REQUIRED', ok, det)
    fa = copy.deepcopy(lw['invw'])
    fa['context_facts'].append(next(f for f in lw['scw']['context_facts'] if f['ref'] == 'context:scope'))
    ok, det = tool_refuses('full_with_fact', serialize(fa), 'ALREADY_SCOPED')
    record('scope_tool.py refuses a full inventory with empty sheets that carries context:scope: ALREADY_SCOPED', ok, det)
    ok, det = build_refuses('full_with_fact', serialize(fa), 'ALREADY_SCOPED')
    record('make_scoped_inventory.py refuses a full inventory with empty sheets that carries context:scope: ALREADY_SCOPED', ok, det)
    # an empty sheet that carries a view, or a cell (census kept by dropping one blank cell of an in-scope sheet), is not empty
    e1 = min(lw['empties'])
    ename = next(s['name'] for s in lw['invw']['sheets'] if s['index'] == e1)
    fv = copy.deepcopy(lw['invw'])
    nid = len(fv['views']) + 1
    fv['views'].append({'id': nid, 'sheet': ename, 'range': 'A1', 'image': {'file': f'view_{nid:02d}.png', 'bytes': 1, 'sha256': '0' * 64}})
    fv['source']['carrier_source']['views'].append({'id': nid, 'sheet': ename, 'range': 'A1'})
    ok, det = tool_refuses('empty_sheet_with_view', serialize(fv), 'FULL_INVENTORY_REQUIRED')
    record('scope_tool.py refuses an out-of-scope sheet with rows x columns = 0 that carries a view: FULL_INVENTORY_REQUIRED', ok, det)
    ok, det = build_refuses('empty_sheet_with_view', serialize(fv), 'FULL_INVENTORY_REQUIRED')
    record('make_scoped_inventory.py refuses an out-of-scope sheet with rows x columns = 0 that carries a view: FULL_INVENTORY_REQUIRED', ok, det)
    fc = copy.deepcopy(lw['invw'])
    blank = next(c for c in fc['cells'] if c['state'] == 'true_blank')
    fc['cells'].remove(blank)
    fc['cells'].insert(0, dict(blank, ref=f'cell:S{e1}!A1', sheet_index=e1, sheet=ename, address='A1', row=1, col=1, views=[]))
    ok, det = tool_refuses('empty_sheet_with_cell', serialize(fc), 'FULL_INVENTORY_REQUIRED')
    record('scope_tool.py refuses an out-of-scope sheet with rows x columns = 0 that carries a cell: FULL_INVENTORY_REQUIRED', ok, det)
    ok, det = build_refuses('empty_sheet_with_cell', serialize(fc), 'FULL_INVENTORY_REQUIRED')
    record('make_scoped_inventory.py refuses an out-of-scope sheet with rows x columns = 0 that carries a cell: FULL_INVENTORY_REQUIRED', ok, det)
    # a reader that puts an empty sheet in scope disagrees on an in_scope flag, which holds the case as on any sheet
    d = env.work / 'reader_flips_empty'
    d.mkdir()
    r = scope_stage(d, lw['full'], flip=e1)
    record('scope_agree.py holds the case when the reader puts an empty sheet in scope (no tie-break)', r.get('agree_code') == 3
           and r['agree_out'].get('status') == 'HELD_FOR_OWNER'
           and [x for x in r['agree_out'].get('differences', []) if x['what'] == 'in_scope'] == [{'what': 'in_scope', 'sheet': e1, 'tool': False, 'reader': True}],
           r.get('agree_out'))
    # determinism
    code, out, err = run(TOOL, '--inventory', lw['full'], '--out-dir', work / 'determinism')
    record('scope_tool.py is deterministic on an inventory with empty sheets', code == 0
           and (work / 'determinism' / 'SCOPE_PROPOSAL.json').read_bytes() == (lw['dir'] / 'tool' / 'SCOPE_PROPOSAL.json').read_bytes()
           and (work / 'determinism' / 'SCOPE_DIGEST.json').read_bytes() == (lw['dir'] / 'tool' / 'SCOPE_DIGEST.json').read_bytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True, type=Path)
    ap.add_argument('--deps-bundle', required=True, type=Path)
    ap.add_argument('--soffice', default='soffice')
    a = ap.parse_args()
    if not a.work.is_absolute() or not a.deps_bundle.is_absolute():
        ap.error('absolute paths required')
    a.work.mkdir(parents=True, exist_ok=False)
    env = Env(a.work, a.deps_bundle, a.soffice)
    large = {}
    for fmt in ('xlsx', 'xls'):
        for name, fn in (('small', lambda: pair_small(env, fmt, 'contract')), ('large', lambda: pair_large(env, fmt))):
            try:
                large[(name, fmt)] = fn()
            except Exception as e:          # a preparation failure fails the pair, and the suite
                record(f'{name}_{fmt}: preparation ran', False, repr(e)[:400])
    for fmt in ('xlsx', 'xls'):
        for variant in ('nt4', 'nh3'):
            try:
                pair_o72(env, fmt, variant)
            except Exception as e:
                record(f'{variant}_{fmt}: preparation ran', False, repr(e)[:400])
    lw = large.get(('large', 'xlsx'))
    if lw:
        refusals(env, lw)
    else:
        record('refusals: the large xlsx pair prepared', False)
    summary = {'tests': len(results), 'passed': sum(r['pass'] for r in results), 'failed': [r for r in results if not r['pass']],
               'fixtures_invented': True,
               'tools_sha256': {p.name: sha(p.read_bytes()) for p in (TOOL, AGREE, SCOPED, JOBCFG, ROUTE)}}
    (a.work / 'EMPTY_SHEET_TEST_RESULTS.json').write_text(json.dumps({'summary': summary, 'results': results}, ensure_ascii=False, indent=1) + '\n',
                                                          encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if not summary['failed'] else 1


if __name__ == '__main__':
    sys.exit(main())
