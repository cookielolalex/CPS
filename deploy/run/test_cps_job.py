#!/usr/bin/env python3
"""End-to-end test of deploy/run/cps_job.py on invented data only.

Builds invented 材料清單 workbooks (stdlib zipfile; the small one reproduces the cells of the package's invented
EXAMPLE_INVENTORY.json, so the package's invented EXAMPLE_RESPONSE.json, adapted to the job's case id and inventory hash,
stands in for the generator and passes the route check), an invented glossary (cps.company-glossary.v1), invented
JOB.json (cps.job-config.v2) and JOB_TITLE.json (cps.job-title.v1) files, an invented qualification jobs list, invented
admissions, ledgers, generation records and release files, then runs the runner's subcommands end to end: prepare,
finish, visual-record, deliver-check, scope-finish, interrupt, freeze, verify-frozen and nonattempt, with the negative
cases (one test or more for each finding R1-R13 and each fixed note of the 2026-11-06 review, for each finding D1-D3
and each fixed note DN1-DN14 of the 2026-11-06 delta review, and for the export v2.8.2 integration: V28, the in-place
restart of protocol rule 3, the delivered tiles of visual_qa v4.5, F2 and the O40 record; E1, E2, EN1, EN4 and EN6 of the
final delta review). No private data is read or written.

Usage: python3 -I -B deploy/run/test_cps_job.py --work /abs/NEW_DIR
         [--writer-dir /abs/deploy/writer_route/writer] [--node /opt/node22/bin/node] [--node-sha256 HEX] [--node-path DIR]
Run it from a clean checkout at a commit (the runner refuses a dirty tracked tree, review R10; the test exits 2 first).
Needs what the runner needs: python3 with openpyxl 3.1.5, node 22, Playwright Chromium (NODE_PATH), LibreOffice and
poppler, and git. Prints one JSON summary; exit 0 when every test passes. Tests that tamper with a read-only file or
folder make it writable first, so they also run as an unprivileged user.
"""
import argparse, contextlib, datetime, fcntl, hashlib, importlib.util, io, json, os, shutil, signal, stat, subprocess, sys, threading, time, traceback, zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUNNER = HERE / 'cps_job.py'
PKG = REPO / 'research/guideline046_007/package'
HARNESS = REPO / 'research/guideline046_007/harness'
CUSTOMER, PROJECT, COMPANY = '示例縣自來水事業處', '示例淨水場控制盤更新', '示例機電股份有限公司'   # invented (the package example's)
PRIVATE_STRINGS = (CUSTOMER, PROJECT, COMPANY, '示例公司', '控制盤', '電磁接觸器', 'XMC', '示例材料', '示例客戶')
# R10: every file the runner executes or fills as a template, besides the package, the export tools and the writer folder
EXECUTED = (['deploy/run/cps_job.py', 'deploy/run/VISUAL_REVIEW_PROMPT_TEMPLATE.md']
            + ['research/guideline046_007/harness/' + n for n in ('make_job_config.py', 'scope_tool.py', 'scope_agree.py',
               'make_scoped_inventory.py', 'prepare_run.py', 'GENERATOR_PROMPT_TEMPLATE.md', 'SCOPE_READER_PROMPT_TEMPLATE.md')]
            + ['research/guideline046_003/source_prep/' + n for n in ('build_inventory_xlsx_v2.py', 'build_inventory_v2.py',
               'render_views.py', 'screenshot_views.cjs', 'auto_views.py')])
# The writer admission the test release names (one constant: when v2.8.2 is admitted this file is replaced and its sha256
# changes; the tests read the sha256 from the file, never a copy of it)
WRITER_ADMISSION = 'research/export/ADMISSION_WRITER_V28.json'
# R12: the further files a qualification admission pins by label (repository-relative path), and JOBS.json
ADMISSION_TOOL_LABELS = EXECUTED + [WRITER_ADMISSION, 'research/evaluation/compare_target050.py',
                                    'research/evaluation/aggregate_qualification050.py']
FEATURES = ('memory', 'custom_instructions', 'web', 'connectors', 'file_uploads', 'other_agents')
REVIEWER = {'kind': 'fresh_context_visual_reviewer', 'model': 'none (invented test)', 'effort': 'n/a',
            'conversation_id': 'invented-test-review-conversation'}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    return sha(Path(p).read_bytes())


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
    """A minimal .xlsx: sheets = [(name, [(address, value, is_cached_formula)], merges)]. Inline strings; a formula cell
    carries a placeholder formula and its saved cache (never evaluated by the builders)."""
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
    wb = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{main}" xmlns:r="{rel_ns}"><sheets>']
    wrels = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{pkg_rel}">']
    for i, (name, _, _) in enumerate(sheets):
        wb.append(f'<sheet name="{escape(name)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>')
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
        for i, (_, cells, merges) in enumerate(sheets):
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


def small_workbook(path):
    """The invented 材料清單 of the package example: header row 項次/品名規格/單位/數量/單價/複價/廠牌/型號/備註."""
    ex = json.loads((PKG / 'resources/EXAMPLE_INVENTORY.json').read_text(encoding='utf-8'))
    cells = [(c['address'], c['saved_value'], c['state'] == 'cached_formula') for c in ex['cells'] if c['state'] in ('literal', 'cached_formula')]
    sh = ex['sheets'][0]
    write_xlsx(path, [(sh['name'], cells, sh['merges'])])
    glossary = json.loads(next(f['value'] for f in ex['context_facts'] if f['ref'] == 'context:glossary'))
    return glossary


def large_workbook(path, items=450):
    """An invented two-sheet workbook with more than 2,500 content cells: a summary sheet and a priced bill sheet
    (header 項次/項目及說明/單位/數量/單價/複價, a 合計 in the price column after the last item)."""
    summary = [('A1', '項次', False), ('B1', '項目及說明', False), ('C1', '複價', False), ('A2', '壹', False), ('B2', '示例詳細表', False),
               ('C2', 900000, True)]
    bill = [('A1', '示例工程 詳細價目表', False)] + [(c + '2', t, False) for c, t in zip('ABCDEF', ('項次', '項目及說明', '單位', '數量', '單價', '複價'))]
    for i in range(items):
        r = 3 + i
        bill += [(f'A{r}', str(i + 1), False), (f'B{r}', f'示例材料第{i + 1}項，規格{i % 7 + 1}', False), (f'C{r}', '只', False),
                 (f'D{r}', i % 5 + 1, False), (f'E{r}', 100 + i, False), (f'F{r}', (i % 5 + 1) * (100 + i), True)]
    bill += [(f'E{3 + items}', '合計', False), (f'F{3 + items}', 123456, True)]
    write_xlsx(path, [('總表', summary, []), ('詳細表', bill, [])])
    return 3 + items


# ------------------------------------------------------------------ harness
class T:
    def __init__(self, args):
        self.a = args
        self.work = Path(args.work)
        self.results, self.outputs = [], []
        self.counter = 0

    def runner(self, *argv):
        p = subprocess.run([sys.executable, '-I', '-B', str(RUNNER), *[str(x) for x in argv]], capture_output=True, timeout=3600)
        out = p.stdout.decode('utf-8', 'replace')
        self.outputs.append(out)
        lines = [ln for ln in out.strip().splitlines() if ln.strip()]
        last = lines[-1] if lines else ''
        return p.returncode, out, last

    def check(self, name, cond, detail=''):
        """cond and detail may be callables: a check whose expression raises fails on its own (so every check of a
        function is evaluated, on this runner and on an older one), and the exception is its detail."""
        try:
            ok = bool(cond() if callable(cond) else cond)
        except Exception as e:                              # noqa: BLE001
            ok, detail = False, f'raised {type(e).__name__}: {e}'[:400]
        if not ok and callable(detail):
            try:
                detail = detail()
            except Exception as e:                          # noqa: BLE001
                detail = f'detail raised {type(e).__name__}'
        self.results.append({'test': name, 'passed': ok, 'detail': '' if ok else detail})
        return ok


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def force_write(p, data):
    """Write (or replace) a file even inside a read-only folder or over a read-only file: the tamper step of a test,
    as the folder's owner (who can always chmod), so it also runs without root."""
    p = Path(p)
    d = p.parent
    dmode = stat.S_IMODE(os.lstat(d).st_mode)
    os.chmod(d, dmode | stat.S_IWUSR)
    try:
        if p.exists():
            os.chmod(p, stat.S_IMODE(os.lstat(p).st_mode) | stat.S_IWUSR)
        p.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
    finally:
        os.chmod(d, dmode)


def force_unlink(p):
    p = Path(p)
    d = p.parent
    dmode = stat.S_IMODE(os.lstat(d).st_mode)
    os.chmod(d, dmode | stat.S_IWUSR)
    try:
        p.unlink()
    finally:
        os.chmod(d, dmode)


def no_write_bits(root):
    """Every file and folder under root (root included) that has a write bit."""
    bad = set()
    for dp, dns, fns in os.walk(root):
        for q in [dp] + [os.path.join(dp, n) for n in dns + fns]:
            if not os.path.islink(q) and stat.S_IMODE(os.lstat(q).st_mode) & 0o222:
                bad.add(q)
    return sorted(bad)


def setup(t):
    w = t.work
    w.mkdir(parents=True, exist_ok=False)
    (w / 'tables').mkdir()
    (w / 'jobs_in').mkdir()
    (w / 'qualification').mkdir()
    src = w / 'jobs_in' / 'invented_material_list.xlsx'
    glossary = small_workbook(src)
    gpath = w / 'tables' / 'GLOSSARY.json'
    gpath.write_text(json.dumps(glossary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    large = w / 'jobs_in' / 'invented_large.xlsx'
    t.large_end_row = large_workbook(large)
    broken = w / 'jobs_in' / 'invented_broken.xlsx'
    broken.write_bytes(b'invented bytes that are not a workbook: the inventory builder stops on them\n')
    # deps bundle for the builders (-S): private/deps -> the site directory that holds openpyxl 3.1.5
    site = Path(importlib.util.find_spec('openpyxl').origin).resolve().parents[1]
    (w / 'deps' / 'private').mkdir(parents=True)
    os.symlink(site, w / 'deps' / 'private' / 'deps')
    # the checker node through a symbolic link, so a test can swap the binary it names
    (w / 'nodelink').mkdir()
    os.symlink(t.a.node, w / 'nodelink' / 'node')
    head = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    t.paths = {'src': src, 'large': large, 'glossary': gpath, 'broken': broken}
    t.release = {
        'schema': 'cps.release.v1', 'status': 'RELEASED_FOR_USE', 'release_version': 'TEST-INVENTED',
        'repository': {'commit': head.stdout.strip() if head.returncode == 0 else None, 'root': str(REPO)},
        'package': {'path': 'research/guideline046_007/package', 'manifest_sha256': sha_file(PKG / 'PACKAGE_MANIFEST.json')},
        'harness': {'path': 'research/guideline046_007/harness'},
        'source_prep': {'path': 'research/guideline046_003/source_prep', 'deps_bundle': str(w / 'deps'),
                        **({'node_path': t.a.node_path} if t.a.node_path else {})},
        'writer': {'admission': WRITER_ADMISSION, 'admission_sha256': sha_file(REPO / WRITER_ADMISSION), 'writer_dir': t.a.writer_dir},
        'checker_node': {'path': str(w / 'nodelink' / 'node'), 'sha256': t.a.node_sha256},
        'admitted_checker_node_sha256': [t.a.node_sha256],
        'tables': {'glossary': {'path': str(gpath), 'sha256': sha_file(gpath)}, 'brand_table': None,
                   'company_name_sha256': sha(COMPANY.encode('utf-8'))},
        'pinned_files_sha256': {p: sha_file(REPO / p) for p in EXECUTED},
    }
    t.release_path = write_release(t, 'RELEASE_USE.json', t.release)
    t.release_q_path = write_release(t, 'RELEASE_QUAL.json', dict(t.release, status='RELEASED_FOR_QUALIFICATION'))
    # the invented qualification jobs list (cps.qualification-jobs.v1); 9991007 is the review's attack case
    jobs = {'schema': 'cps.qualification-jobs.v1', 'meaning': 'INVENTED test jobs list', 'cases': [
        {'case_id': '9990003', 'order': 1, 'nonattempt': False}, {'case_id': '9990032', 'order': 2, 'nonattempt': False},
        {'case_id': '9990033', 'order': 3, 'nonattempt': False},
        {'case_id': '9990034', 'order': 4, 'nonattempt': True, 'reason': 'NONATTEMPT_SOURCE_UNAVAILABLE'},
        {'case_id': '9991007', 'order': 5, 'nonattempt': False},
        # the delta review's D1-D3 and DN notes: an interrupted generator, an interrupted scope reader, the ledger cases,
        # and two nonattempts (one naming its reason, one naming none)
        {'case_id': '9990040', 'order': 6, 'nonattempt': False}, {'case_id': '9990041', 'order': 7, 'nonattempt': False},
        {'case_id': '9990042', 'order': 8, 'nonattempt': False},
        {'case_id': '9990044', 'order': 9, 'nonattempt': True, 'reason': 'NONATTEMPT_SOURCE_UNAVAILABLE'},
        {'case_id': '9990045', 'order': 10, 'nonattempt': True},
        # the in-place restart of protocol rule 3 after an agreed scope (a large invented workbook)
        {'case_id': '9990046', 'order': 11, 'nonattempt': False},
        # E1: a written generator response, a written scope reader file, a response written after the interruption
        {'case_id': '9990047', 'order': 12, 'nonattempt': False}, {'case_id': '9990048', 'order': 13, 'nonattempt': False},
        {'case_id': '9990049', 'order': 14, 'nonattempt': False}]}
    t.jobs_path = w / 'qualification' / 'JOBS.json'
    t.jobs_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def write_release(t, name, d):
    p = t.work / name
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return p


def qual_release(t, name, admissions, ledger, **extra):
    q = {'admissions': [{'path': str(a), 'sha256': sha_file(a)} for a in admissions], 'ledger': str(ledger), 'jobs_file': str(t.jobs_path)}
    return write_release(t, name, dict(t.release, status='RELEASED_FOR_QUALIFICATION', qualification=q, **extra))


def job_files(t, case, source=None, extra=None):
    d = t.work / 'jobs_in' / case
    d.mkdir()
    job = {'schema': 'cps.job-config.v2', 'case_id': case, 'customer_name': CUSTOMER, 'project_name': PROJECT, 'company_name': COMPANY,
           'glossary_path': str(t.paths['glossary']), 'source_path': str(source or t.paths['src']), 'source_kind': '材料清單',
           'carrier_path': f'X:\\Fixtures\\invented\\{case}-material-list.xlsx', **(extra or {})}
    title = {'schema': 'cps.job-title.v1', 'case_id': case, 'job_title': f'{case}示例公司-示例案'}
    jp, tp = d / 'JOB.json', d / 'JOB_TITLE.json'
    jp.write_text(json.dumps(job, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    tp.write_text(json.dumps(title, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return jp, tp


def prepare(t, case, root='jobs', release=None, source=None, extra=None, more=()):
    jp, tp = job_files(t, case, source, extra)
    code, out, last = t.runner('prepare', '--release', release or t.release_path, '--job', jp, '--job-title-file', tp,
                               '--jobs-root', t.work / root, '--operator-model', 'test-harness', *more)
    return code, out, last, t.work / root / case


def qprepare(t, release, jp, tp, root, reader, adm):
    return t.runner('prepare', '--release', release, '--job', jp, '--job-title-file', tp, '--jobs-root', t.work / root,
                    '--reader', reader, '--qualification', '--admission', adm, '--operator-model', 'test-harness')


def stand_in_response(t, jd, case, break_it=False, reader='A'):
    """The package's invented EXAMPLE_RESPONSE.json for this job: case id and inventory hash adapted. It is the
    generator's response file in run/<reader>/output/."""
    inv = jd / 'run' / reader / 'input' / 'packet' / 'SOURCE_INVENTORY.json'
    r = json.loads((PKG / 'resources/EXAMPLE_RESPONSE.json').read_text(encoding='utf-8'))

    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return case if x == 'EXAMPLE046F' else x
    r = walk(r)
    r['inventory_sha256'] = sha_file(inv)
    if break_it:                              # a citation of a cell that does not exist: the route check rejects it
        r['items'][0]['proofs']['E']['refs'] = ['cell:S1!Z99']
    p = jd / 'run' / reader / 'output' / 'response.json'
    p.write_text(json.dumps(r, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return p


def generation_record(jd, case, reader='A', **over):
    """An invented generation record (cps.generation-record.v1) in run/GENERATION_RECORD.json: the operator's attested
    record of the generator conversation, here with transcript_status not_available."""
    now = utc_now()
    g = {'schema': 'cps.generation-record.v1', 'case_id': case, 'reader': reader, 'platform': 'invented test platform',
         'model': 'stand-in (invented test)', 'effort': 'n/a', 'conversation_id': 'invented-generation-conversation',
         'started_utc': now, 'ended_utc': now, 'prompt_sha256': sha_file(jd / 'run' / 'GENERATOR_PROMPT.md'),
         'single_user_message': True, 'features': {k: False for k in FEATURES}, 'tools_enabled': ['Read', 'Write', 'Bash'],
         'final_message': 'invented final message of the stand-in generator', 'transcript_status': 'not_available',
         'transcript_not_available_reason': 'invented: the platform offers no transcript export'}
    g.update(over)
    p = jd / 'run' / 'GENERATION_RECORD.json'
    force_write(p, json.dumps(g, ensure_ascii=False, indent=1) + '\n')
    return p


def stand_in_review(jd, fail=False, drop_page=False, reviewer=None):
    """A stand-in visual review that marks every selected item pass (or one fail), in qa/visual_review/VISUAL_REVIEW.json.
    The reviewer record is the fresh-context reviewer's shape (R6); the stand-in is invented."""
    pages = json.loads((jd / 'qa' / 'VISUAL_PAGES.json').read_text(encoding='utf-8'))
    rv = {'schema': 'cps.visual-review.v1', 'reviewer': dict(REVIEWER) if reviewer is None else reviewer}
    for key, wb in pages['workbooks'].items():
        sel = wb['selected'][:-1] if (drop_page and key == 'internal') else wb['selected']
        rv[key] = {'manifest_sha256': wb['manifest_sha256'],
                   'pages': {str(p): {str(i): {'result': 'pass', 'note': ''} for i in range(1, 10)} for p in sel}}
    rv['deliverable']['cut_cells'] = {c['cell']: {'result': 'pass', 'note': ''}
                                      for c in pages['workbooks']['deliverable']['possibly_cut_cells']['cells'] if c.get('cell')}
    rv['overall'], rv['failures'] = 'PASS', []
    if fail:
        rv['deliverable']['pages']['1']['6'] = {'result': 'fail', 'note': 'invented failure'}
        rv['overall'], rv['failures'] = 'FAIL', ['deliverable page 1 item 6: invented failure']
    out = jd / 'qa' / 'visual_review' / 'VISUAL_REVIEW.json'
    out.write_text(json.dumps(rv, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return out


def record(jd):
    return json.loads((jd / 'RUN_RECORD.json').read_text(encoding='utf-8'))


def stages(jd, name):
    return [s for s in record(jd)['stages'] if s['stage'] == name]


def ledger(p):
    return [json.loads(x) for x in Path(p).read_text(encoding='utf-8').splitlines()] if Path(p).is_file() else []


def next_path(last, key):
    for part in last.split(' '):
        if part.startswith(key + '='):
            return Path(part[len(key) + 1:])
    return None


def last_json(out):
    for line in reversed(out.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {}


def unlocked(jd):
    """True when nothing holds the job folder's lock (DN3/DN4: the lock is a flock of the folder itself)."""
    fd = os.open(jd, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


def wait_for(pred, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if pred():
                return True
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.1)
    return False


# ------------------------------------------------------------------ tests
def test_real_job(t):
    """9990001: prepare -> GENERATE; finish -> VISUAL_REVIEW (evidence grade); visual-record PASS; deliver-check -> DELIVER;
    a second finish and a second prepare are refused. R9: a withdrawn live release refuses finish and deliver-check; a
    new release that names this release version delivers. N5: a response outside run/A/output is refused. R13: a
    generation record given to an everyday job is frozen and recorded. N9: tool versions recorded."""
    live = write_release(t, 'RELEASE_9990001.json', t.release)
    code, out, last, jd = prepare(t, '9990001', release=live)
    t.check('prepare: NEXT: GENERATE, exit 0', lambda: code == 0 and last.startswith('NEXT: GENERATE '), last)
    t.check('prepare: runbook layout', lambda: all((jd / d).is_dir() for d in ('input', 'packet', 'scope', 'run', 'response', 'carrier', 'export', 'qa'))
            and (jd / 'RUN_RECORD.json').is_file())
    prompt, folder = next_path(last, 'prompt'), next_path(last, 'folder')
    t.check('prepare: generator prompt names the run folder', lambda: prompt is not None and prompt.is_file()
            and str(folder) in prompt.read_text(encoding='utf-8') and '{RUN}' not in prompt.read_text(encoding='utf-8'))
    t.check('prepare: run folder holds the package and the packet only', lambda: folder is not None
            and sorted(p.name for p in (folder / 'input').iterdir()) == ['package', 'packet'] and (folder / 'output').is_dir())
    pr = stages(jd, 'prepare')[-1]
    t.check('prepare: record entry (completed, scope tool NOT_APPLIED, check-inventory PASS)',
            lambda: pr['completed'] and pr['result'] == 'PREPARED_NOT_SCOPED' and pr['facts']['scope_tool']['status'] == 'NOT_APPLIED'
            and pr['facts']['check_inventory_full']['status'] == 'PASS' and pr['facts']['check_inventory_full']['policy_checks'] == 'applied',
            lambda: json.dumps(pr.get('facts', {}).get('scope_tool')))
    t.check('N9: prepare records the deps-bundle openpyxl (from the bundle) and the external tools on PATH',
            lambda: pr['facts']['deps_bundle']['openpyxl'] == {'version': '3.1.5', 'from_bundle': True}
            and set(pr['facts']['external_tools']) == {'soffice', 'pdftoppm', 'pdfinfo', 'pdftotext', 'node'},
            lambda: json.dumps(pr['facts'].get('deps_bundle')))
    lx = subprocess.run([sys.executable, '-I', '-c', 'import lxml; print(lxml.__version__)'], capture_output=True, text=True).stdout.strip()
    adm_env = json.loads((REPO / WRITER_ADMISSION).read_text(encoding='utf-8'))['environment']['lxml']
    t.check('EN6: prepare records lxml with openpyxl (the version this python3 imports, and the one the writer admission lists)',
            lambda: pr['facts']['lxml'] == {'version': lx, 'admission_environment': adm_env, 'matches_admission': lx == adm_env}
            and pr['facts']['openpyxl'] == '3.1.5', lambda: json.dumps(pr['facts'].get('lxml')))
    t.check('DN9: prepare records the interpreter (path, realpath, version) and the names, never the values, of the tool environment',
            lambda: pr['facts']['python']['version'] == sys.version.split()[0] and pr['facts']['python']['realpath'] == os.path.realpath(sys.executable)
            and 'PATH' in pr['facts']['tool_env_names'] and all(isinstance(k, str) for k in pr['facts']['tool_env_names'])
            and os.environ.get('PATH', '\0') not in json.dumps(pr['facts']['tool_env_names']), lambda: json.dumps(pr['facts'].get('python')))
    t.check('R10: prepare records every executed file as pinned (release pinned_files_sha256) and a clean verified tree',
            lambda: len(pr['facts']['executed_files_pinned']) == len(EXECUTED) and pr['facts']['repository']['tracked_tree_clean'] is True
            and pr['facts']['repository']['commit_verified_with_git'] is True, lambda: json.dumps(pr['facts'].get('repository')))
    t.check('R9: the record names the live release path', lambda: record(jd)['release']['path'] == str(live))
    jp, tp = t.work / 'jobs_in' / '9990001' / 'JOB.json', t.work / 'jobs_in' / '9990001' / 'JOB_TITLE.json'
    code2, _, last2 = t.runner('prepare', '--release', live, '--job', jp, '--job-title-file', tp, '--jobs-root', t.work / 'jobs')
    t.check('prepare again into the same job folder: refused', lambda: code2 == 4 and last2 == 'REFUSED: JOB_DIR_EXISTS', last2)
    resp = stand_in_response(t, jd, '9990001')
    good = live.read_bytes()
    live.write_text(json.dumps(dict(t.release, status='WITHDRAWN'), ensure_ascii=False), encoding='utf-8')
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    t.check('R9: finish after the live release is withdrawn: refused RELEASE_NOT_LIVE, nothing consumed', lambda: code == 4
            and last == 'REFUSED: RELEASE_NOT_LIVE' and not (jd / 'response' / 'response.json').exists(), last)
    live.write_bytes(good)
    elsewhere = t.work / 'response_9990001_elsewhere.json'
    shutil.copyfile(resp, elsewhere)
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', elsewhere)
    t.check('N5: a real job refuses a response outside run/A/output (RESPONSE_PATH), nothing consumed', lambda: code == 4
            and last == 'REFUSED: RESPONSE_PATH' and not (jd / 'response' / 'response.json').exists(), last)
    gpath = generation_record(jd, '9990001')
    code, out, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--generator-model', 'stand-in (invented test)',
                               '--generation-record', gpath)
    t.check('finish: NEXT: VISUAL_REVIEW, exit 0', lambda: code == 0 and last.startswith('NEXT: VISUAL_REVIEW '), lambda: last + out[-600:])
    fin = stages(jd, 'finish')[-1]
    t.check('R13: an everyday job given a generation record freezes it and records transcript_status (not_available flagged)',
            lambda: (jd / 'response' / 'GENERATION_RECORD.json').is_file() and sha_file(jd / 'response' / 'GENERATION_RECORD.json') == sha_file(gpath)
            and fin['facts']['generation_record']['transcript_status'] == 'not_available'
            and fin['facts']['generation_record']['transcript_not_available_flagged'] is True
            and fin['facts']['generation_record']['isolation_evidence'] == 'attested_not_audited', lambda: json.dumps(fin['facts'].get('generation_record')))
    ev = json.loads((jd / 'qa' / 'QA_EVIDENCE.json').read_text(encoding='utf-8')) if (jd / 'qa' / 'QA_EVIDENCE.json').is_file() else {}
    t.check('finish: QA_EVIDENCE evidence_grade true', lambda: ev.get('evidence_grade') is True, lambda: json.dumps(ev.get('failed_conditions')))
    t.check('V28: QA_EVIDENCE.json states the conditions of the writer admission the release names (ADMISSION_WRITER_V28.json)',
            lambda: 'ADMISSION_WRITER_V28.json' in ev['evidence_grade_meaning'] and 'V27' not in ev['evidence_grade_meaning']
            and ev['admission_file'].endswith(WRITER_ADMISSION), lambda: ev.get('evidence_grade_meaning'))
    ids = {c['id']: c for c in ev.get('conditions', [])}
    t.check('finish: QA_EVIDENCE records condition 7 (title file) and condition 6 (mode v2 from the convert receipt)',
            lambda: ids.get('7.job_title', {}).get('met') is True and ids.get('6.mode', {}).get('value', {}).get('mode') == 'v2')
    t.check('finish: response frozen read-only with its sha256 recorded',
            lambda: (jd / 'response' / 'response.json').is_file() and not (os.stat(jd / 'response' / 'response.json').st_mode & 0o222)
            and stages(jd, 'freeze_response')[-1]['outputs']['response']['sha256'] == sha_file(resp))
    t.check('R5: finish lists every file of run/A/output with its sha256', lambda: fin['facts']['run_output_files'] is not None
            and fin['facts']['run_output_files'].get('response.json', {}).get('sha256') == sha_file(resp), lambda: json.dumps(fin['facts'].get('run_output_files')))
    vp = json.loads((jd / 'qa' / 'VISUAL_PAGES.json').read_text(encoding='utf-8'))
    dl, it = vp['workbooks']['deliverable'], vp['workbooks']['internal']
    rev = [int(p) for p, e in it['pages'].items() if e['role'] == 'review']
    want = sorted({int(p) for p, e in it['pages'].items() if e['role'] != 'review'} | set(sorted(rev)[:2] + sorted(rev)[-1:]))
    t.check('finish: page selection (every delivered page; internal main/composition pages, review pages 1, 2 and last)',
            lambda: dl['selected'] == list(range(1, dl['pages_total'] + 1)) and it['selected'] == want, lambda: json.dumps(it['selected']))
    dman = safe(lambda: json.loads((jd / 'qa' / 'visual_deliverable' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')), {})
    iman = safe(lambda: json.loads((jd / 'qa' / 'visual_internal' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')), {})
    want_tiles = safe(lambda: {str(i['page']): [(str(jd / 'qa' / 'visual_deliverable' / x['file']), x['sha256']) for x in i['tiles']]
                               for i in dman['images']}, {})
    t.check('F3-tiles: VISUAL_PAGES.json lists every tile of every delivered page (absolute path and the manifest sha256), the internal '
            'workbook none', lambda: dman['tiles']['count'] >= 1 and all(want_tiles[p] for p in want_tiles)
            and {p: [(x['image'], x['sha256']) for x in e['tiles']] for p, e in dl['pages'].items()} == want_tiles
            and dl['tiles']['legibility_bound_exceeded'] is False and iman['tiles'] is None
            and all('tiles' not in e for e in it['pages'].values()), lambda: json.dumps(dl['pages'])[:600])
    vprompt = safe(lambda: (jd / 'qa' / 'VISUAL_REVIEW_PROMPT.md').read_text(encoding='utf-8'), '')
    t.check('F3-tiles: the review prompt lists every tile of every delivered page by absolute path and tells the reviewer to read every '
            'tile (the page PNG is the overview)', lambda: all(f'`{path}`' in vprompt for v in want_tiles.values() for path, _ in v)
            and 'Read every tile of every page, at full size' in vprompt and 'the overview' in vprompt)
    fin_ = stages(jd, 'finish')[-1]
    t.check('F3-tiles: the runner renders the delivered workbook without --dpi: its manifest records the automatic rule, and finish '
            'records that no --dpi was given', lambda: dman['dpi_rule'].startswith('auto: delivered one-sheet workbook')
            and fin_['facts']['visual_qa_dpi']['deliverable'] == {'dpi_argument_given': False, 'dpi': dman['dpi'], 'dpi_rule': dman['dpi_rule']}
            and fin_['facts']['visual_qa_dpi']['internal']['dpi_rule'].startswith('auto: 150'), lambda: json.dumps(fin_['facts'].get('visual_qa_dpi')))
    t.check('F3-tiles: QA_EVIDENCE records the delivered tiles (no problem) and the legibility bound (8.legibility met)',
            lambda: ids['8.render_deliverable']['value']['tile_problems'] == [] and ids['8.render_deliverable']['value']['tiles']['count'] == dman['tiles']['count']
            and ids['8.legibility']['met'] is True and ids['8.legibility']['value']['legibility_bound_exceeded'] is False,
            lambda: json.dumps({k: ids.get(k) for k in ('8.render_deliverable', '8.legibility')})[:600])
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    t.check('a second finish is refused', lambda: code == 4 and last == 'REFUSED: STAGE_ALREADY_COMPLETED', last)
    review = stand_in_review(jd)
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', review)
    t.check('visual-record: PASS, NEXT: DELIVER_CHECK', lambda: code == 0 and last == 'NEXT: DELIVER_CHECK', last)
    live.write_text(json.dumps(dict(t.release, status='WITHDRAWN'), ensure_ascii=False), encoding='utf-8')
    code, _, last = t.runner('deliver-check', '--job-dir', jd)
    t.check('R9: deliver-check after the live release is withdrawn: refused RELEASE_NOT_LIVE (not completed)', lambda: code == 4
            and last == 'REFUSED: RELEASE_NOT_LIVE' and not stages(jd, 'deliver-check')[-1]['completed']
            and not (jd / 'qa' / 'DELIVERY_CHECK.json').exists(), last)
    live.write_text(json.dumps(dict(t.release, release_version='TEST-INVENTED-2', accepts_jobs_from_release_versions=['TEST-INVENTED']),
                               ensure_ascii=False), encoding='utf-8')
    code, out, last = t.runner('deliver-check', '--job-dir', jd)
    f = next_path(last, 'file')
    saved = json.loads((jd / 'qa' / 'SAVED_QA.json').read_text(encoding='utf-8'))
    t.check('deliver-check: NEXT: DELIVER with the absolute path of the delivered workbook (R9: a new release naming this version)',
            lambda: code == 0 and f is not None and f.is_absolute()
            and f.is_file() and sha_file(f) == saved['deliverable_xlsx']['sha256'] and f.name.endswith('(未填).xlsx'), last)
    dc = json.loads((jd / 'qa' / 'DELIVERY_CHECK.json').read_text(encoding='utf-8'))
    t.check('deliver-check: DELIVERY_CHECK.json DELIVERABLE (N7: the titled name, not the internal workbook)',
            lambda: dc['result'] == 'DELIVERABLE' and all(dc['checks'].values()) and dc['checks'].get('file_name_is_the_titled_name') is True
            and dc['checks'].get('bytes_differ_from_internal_workbook') is True and dc['live_release']['this_release_version_accepted'] is True)
    rec = record(jd)
    t.check('RUN_RECORD: append-only chain', lambda: all(s['seq'] == i + 1 for i, s in enumerate(rec['stages']))
            and [s['stage'] for s in rec['stages'] if s['completed']] == ['prepare', 'freeze_response', 'finish', 'visual-record', 'deliver-check'])


def test_node_and_tamper(t):
    """9990002: a checker node whose binary changed after prepare is refused at finish (nothing consumed); after it is
    restored, finish runs; R6 (reviewer kind and conversation id), N2 (refused attempts kept) and N3 (fixed review path);
    a tampered delivered file fails deliver-check."""
    acopy = t.work / 'adm_copy_9990002' / 'ADMISSION_WRITER_V28.json'      # E2: a pinned copy the test can withdraw
    acopy.parent.mkdir()
    acopy.write_bytes((REPO / WRITER_ADMISSION).read_bytes())
    rel_e2 = write_release(t, 'RELEASE_9990002.json', dict(t.release, writer=dict(t.release['writer'], admission=str(acopy),
                                                                                    admission_sha256=sha_file(acopy))))
    code, out, last, jd = prepare(t, '9990002', release=rel_e2)
    resp = stand_in_response(t, jd, '9990002')
    link = t.work / 'nodelink' / 'node'
    link.unlink()
    os.symlink(sys.executable, link)                      # another binary: its sha256 is not admitted
    try:
        code, out, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    finally:
        link.unlink()
        os.symlink(t.a.node, link)
    t.check('finish with a checker node binary that is not admitted: refused', lambda: code == 4 and last == 'REFUSED: CHECKER_NODE_NOT_ADMITTED', last)
    t.check('the refused finish consumed nothing (no frozen response, attempt recorded as not completed)',
            lambda: not (jd / 'response' / 'response.json').exists() and stages(jd, 'finish')[-1]['completed'] is False)
    code, out, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    t.check('finish after the node is restored: NEXT: VISUAL_REVIEW', lambda: code == 0 and last.startswith('NEXT: VISUAL_REVIEW'), last)
    partial = stand_in_review(jd, drop_page=True)
    partial_sha = sha_file(partial)
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', partial)
    t.check('visual-record: a review that omits a selected page is refused (not recorded as a result)',
            lambda: code == 4 and last == 'REFUSED: REVIEW_INCOMPLETE', last)
    vr = stages(jd, 'visual-record')[-1]
    att = jd / vr['inputs'].get('review_attempt', {}).get('path', 'missing')
    t.check('N2: the refused review is kept read-only in qa/visual_review_attempts/<seq>.json and pinned in the refused entry',
            lambda: att.is_file() and sha_file(att) == partial_sha and att.parent.name == 'visual_review_attempts' and not (os.stat(att).st_mode & 0o222),
            lambda: json.dumps(vr['inputs']))
    full = stand_in_review(jd)
    other = jd / 'qa' / 'visual_review' / 'ELSEWHERE.json'
    shutil.copyfile(full, other)
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', other)
    t.check('N3: a review at any path but qa/visual_review/VISUAL_REVIEW.json is refused (REVIEW_PATH)', lambda: code == 4
            and last == 'REFUSED: REVIEW_PATH', last)
    other.unlink()
    stand_in_review(jd, reviewer={'kind': 'operator_self_check', 'model': 'the operator itself (invented)', 'effort': 'n/a',
                                  'conversation_id': 'invented'})
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', full)
    t.check('R6: an operator self-review (reviewer.kind operator_self_check) is refused REVIEW_NOT_FRESH_CONTEXT, not recorded as PASS',
            lambda: code == 4 and last == 'REFUSED: REVIEW_NOT_FRESH_CONTEXT' and not stages(jd, 'visual-record')[-1]['completed'], last)
    stand_in_review(jd, reviewer={'kind': 'fresh_context_visual_reviewer', 'model': 'invented', 'effort': 'n/a'})
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', full)
    t.check('R6: a fresh-context review with no conversation id (review or --reviewer-conversation-id) is refused',
            lambda: code == 4 and last == 'REFUSED: REVIEWER_CONVERSATION_ID_REQUIRED', last)
    good_adm = acopy.read_bytes()
    acopy.write_bytes(good_adm.replace(b'"decision": "', b'"decision": "INVENTED EDIT. ', 1))
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', full, '--reviewer-conversation-id', 'invented-operator-attested-id')
    acopy.write_bytes(good_adm)
    t.check('E2: visual-record re-reads the writer admission: one edited after finish is refused WRITER_ADMISSION_SHA256_MISMATCH, '
            'not completed, nothing frozen', lambda: code == 4 and last == 'REFUSED: WRITER_ADMISSION_SHA256_MISMATCH'
            and not stages(jd, 'visual-record')[-1]['completed'] and not (jd / 'qa' / 'VISUAL_REVIEW.json').exists(), last)
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', full, '--reviewer-conversation-id', 'invented-operator-attested-id')
    vrec = json.loads((jd / 'qa' / 'VISUAL_RECORD.json').read_text(encoding='utf-8')) if (jd / 'qa' / 'VISUAL_RECORD.json').is_file() else {}
    t.check('R6: with the operator-attested --reviewer-conversation-id the review is recorded PASS, NEXT: DELIVER_CHECK',
            lambda: code == 0 and last == 'NEXT: DELIVER_CHECK' and vrec.get('reviewer_conversation_id') == 'invented-operator-attested-id'
            and vrec.get('reviewer_conversation_id_source', '').startswith('operator'), last)
    wd = json.loads(good_adm.decode('utf-8'))
    wd['status'] = 'WITHDRAWN'
    acopy.write_text(json.dumps(wd, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    code, _, last = t.runner('deliver-check', '--job-dir', jd)
    acopy.write_bytes(good_adm)
    t.check('E2: a writer admission whose status is changed to WITHDRAWN after visual-record stops deliver-check '
            '(WRITER_ADMISSION_NOT_ADMITTED, not completed, no DELIVERY_CHECK.json)', lambda: code == 4
            and last == 'REFUSED: WRITER_ADMISSION_NOT_ADMITTED' and not stages(jd, 'deliver-check')[-1]['completed']
            and not (jd / 'qa' / 'DELIVERY_CHECK.json').exists(), last)
    saved = json.loads((jd / 'qa' / 'SAVED_QA.json').read_text(encoding='utf-8'))
    f = jd / 'export' / 'writer' / saved['deliverable_xlsx']['file']
    force_write(f, f.read_bytes() + b'\0')
    code, _, last = t.runner('deliver-check', '--job-dir', jd)
    dc = json.loads((jd / 'qa' / 'DELIVERY_CHECK.json').read_text(encoding='utf-8'))
    t.check('deliver-check on a tampered delivered file: STOP, DO_NOT_DELIVER', lambda: code == 3 and last == 'NEXT: STOP_DELIVERY_CHECK_FAILED'
            and dc['result'] == 'DO_NOT_DELIVER' and dc['checks']['sha256_equals_saved_qa'] is False, last)


def test_prepare_refusals(t):
    rel = json.loads(t.release_path.read_text(encoding='utf-8'))
    bad = write_release(t, 'RELEASE_NODE.json', dict(rel, admitted_checker_node_sha256=['0' * 64]))
    code, _, last, jd = prepare(t, '9990010', release=bad)
    t.check('prepare with a checker node whose sha256 is not admitted: refused, no job folder', lambda: code == 4
            and last == 'REFUSED: CHECKER_NODE_NOT_ADMITTED' and not jd.exists(), last)
    code, _, last, jd = prepare(t, '9990011', extra={'job_title': '9990011示例'})
    t.check('prepare with the title inside JOB.json: refused', lambda: code == 4 and last == 'REFUSED: JOB_TITLE_IN_JOB_JSON' and not jd.exists(), last)
    bad = write_release(t, 'RELEASE_TABLE.json', dict(rel, tables=dict(rel['tables'], glossary={'path': rel['tables']['glossary']['path'], 'sha256': '1' * 64})))
    code, _, last, jd = prepare(t, '9990012', release=bad)
    t.check('prepare with a glossary that is not the released table: refused', lambda: code == 4 and last == 'REFUSED: TABLE_SHA256_MISMATCH', last)
    code, _, last, jd = prepare(t, '9990013', release=t.release_q_path)
    t.check('prepare of a real job under a qualification release: refused', lambda: code == 4 and last == 'REFUSED: RELEASE_STATUS', last)
    jp, tp = job_files(t, 'ABC0015')
    code, _, last = t.runner('prepare', '--release', t.release_path, '--job', jp, '--job-title-file', tp, '--jobs-root', t.work / 'jobs')
    t.check('prepare with a title the writer would refuse (no 7-digit case id): refused before any folder', lambda: code == 4
            and last == 'REFUSED: JOB_TITLE_REFUSED_BY_WRITER' and not (t.work / 'jobs' / 'ABC0015').exists(), last)
    code, _, last, jd = prepare(t, '9990014', extra={'customer_name': '=示例'})
    t.check('prepare with a job input make_job_config.py refuses: refused before any folder', lambda: code == 4
            and last == 'REFUSED: JOB_CONFIG_REFUSED' and not jd.exists(), last)
    pins = dict(rel['pinned_files_sha256'])
    pins.pop('research/guideline046_007/harness/scope_agree.py')
    bad = write_release(t, 'RELEASE_PINS.json', dict(rel, pinned_files_sha256=pins))
    code, out, last, jd = prepare(t, '9990016', release=bad)
    t.check('R10: a release that does not pin an executed harness file is refused RELEASE_PINS_INCOMPLETE, no job folder',
            lambda: code == 4 and last == 'REFUSED: RELEASE_PINS_INCOMPLETE' and not jd.exists()
            and 'research/guideline046_007/harness/scope_agree.py' in json.dumps(last_json(out)), last)
    bad = write_release(t, 'RELEASE_PINWRONG.json', dict(rel, pinned_files_sha256=dict(rel['pinned_files_sha256'], **{
        'research/guideline046_003/source_prep/render_views.py': '2' * 64})))
    code, _, last, jd = prepare(t, '9990017', release=bad)
    t.check('R10 (guard): a pinned executed file whose bytes differ is refused PINNED_FILE_MISMATCH', lambda: code == 4
            and last == 'REFUSED: PINNED_FILE_MISMATCH' and not jd.exists(), last)
    bad = write_release(t, 'RELEASE_NOCOMMIT.json', dict(rel, repository={'root': rel['repository']['root']}))
    code, _, last, jd = prepare(t, '9990018', release=bad)
    t.check('R10: a release without repository.commit is refused RELEASE_COMMIT_REQUIRED', lambda: code == 4
            and last == 'REFUSED: RELEASE_COMMIT_REQUIRED' and not jd.exists(), last)
    prov = json.loads((REPO / WRITER_ADMISSION).read_text(encoding='utf-8'))
    prov['status'] = 'PROVISIONAL_NOT_ADMITTED'
    prov_p = t.work / 'ADMISSION_WRITER_PROVISIONAL.json'
    prov_p.write_text(json.dumps(prov, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    bad = write_release(t, 'RELEASE_PROVISIONAL_ADMISSION.json',
                        dict(rel, writer=dict(rel['writer'], admission=str(prov_p), admission_sha256=sha_file(prov_p))))
    code, _, last, jd = prepare(t, '9990020', release=bad)
    t.check('integration: a writer admission whose status is not ADMITTED (a provisional one) is refused WRITER_ADMISSION_NOT_ADMITTED, '
            'no job folder', lambda: code == 4 and last == 'REFUSED: WRITER_ADMISSION_NOT_ADMITTED' and not jd.exists(), last)
    nopin = write_release(t, 'RELEASE_NO_ADMISSION_PIN.json', dict(rel, writer={k: v for k, v in rel['writer'].items() if k != 'admission_sha256'}))
    code, out, last, jd = prepare(t, '9990027', release=nopin)
    t.check('E2: a release without writer.admission_sha256 is refused RELEASE_FIELD_MISSING, no job folder', lambda: code == 4
            and last == 'REFUSED: RELEASE_FIELD_MISSING' and last_json(out).get('detail', {}).get('field') == 'writer.admission_sha256'
            and not jd.exists(), last)
    edited = json.loads((REPO / WRITER_ADMISSION).read_text(encoding='utf-8'))
    edited.update(status='ADMITTED', decision='INVENTED: a provisional record whose status was edited to ADMITTED')
    edited_p = t.work / 'ADMISSION_WRITER_EDITED_COPY.json'
    edited_p.write_text(json.dumps(edited, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    code, out, last, jd = prepare(t, '9990028', release=write_release(t, 'RELEASE_EDITED_ADMISSION_NOPIN.json', dict(
        rel, writer={**{k: v for k, v in rel['writer'].items() if k != 'admission_sha256'}, 'admission': str(edited_p)})))
    code2, _, last2, jd2 = prepare(t, '9990029', release=write_release(t, 'RELEASE_EDITED_ADMISSION_PIN.json', dict(
        rel, writer=dict(rel['writer'], admission=str(edited_p)))))
    t.check('E2: a copied writer admission with its status edited to ADMITTED is refused: without a pin RELEASE_FIELD_MISSING, with the '
            'admitted file\'s pin WRITER_ADMISSION_SHA256_MISMATCH; no job folder', lambda: code == 4 and last == 'REFUSED: RELEASE_FIELD_MISSING'
            and code2 == 4 and last2 == 'REFUSED: WRITER_ADMISSION_SHA256_MISMATCH' and not jd.exists() and not jd2.exists(), lambda: f'{last} / {last2}')
    inside_repo = REPO / 'deploy' / 'run' / '_invented_jobs_root_must_not_be_created'
    jp, tp = job_files(t, '9990019')
    code, _, last = t.runner('prepare', '--release', t.release_path, '--job', jp, '--job-title-file', tp, '--jobs-root', inside_repo)
    t.check('N11: a jobs root inside the repository checkout is refused before anything is created', lambda: code == 4
            and last == 'REFUSED: JOBS_ROOT_IN_REPOSITORY' and not inside_repo.exists(), last)


def admission(t, case, jp, tp, with_title=True, tools=True):
    """An invented qualification admission (freeze_admission.py). tools: also the files of review 4(d) item 1 by
    repository-relative label (runner, harness, source prep, writer admission, evaluator, aggregator) and JOBS.json."""
    files = {'package_manifest': PKG / 'PACKAGE_MANIFEST.json', 'route': PKG / 'tools/cps046b_route.py', f'job_{case}': jp,
             f'source_{case}': Path(json.loads(Path(jp).read_text(encoding='utf-8'))['source_path']), 'glossary': t.paths['glossary']}
    if with_title:
        files[f'job_title_{case}'] = tp
    if tools:
        files.update({k: REPO / k for k in ADMISSION_TOOL_LABELS})
        files['JOBS.json'] = t.jobs_path
    t.counter += 1
    cfg = {'files': {k: str(v) for k, v in files.items()}, 'plan': {'candidate': '046g', 'note': 'invented test admission'}}
    cp = t.work / f'ADMISSION_CONFIG_{case}_{t.counter}.json'
    cp.write_text(json.dumps(cfg, ensure_ascii=False), encoding='utf-8')
    out = t.work / f'ADMISSION_{case}_{t.counter}.json'
    subprocess.run([sys.executable, '-I', '-B', str(HARNESS / 'freeze_admission.py'), '--config', str(cp), '--out', str(out)],
                   check=True, capture_output=True)
    time.sleep(0.05)
    return out


def test_qualification(t):
    """9990003 in qualification mode: R12 (admission listed in the release, every tool pinned, frozen before the first
    prepare), R11 (B only after A is frozen; no second run of A after its response; the ledger mirrors the record),
    R13 (generation record required, checked, frozen), R3 (freeze read-only; verify-frozen), PACKET_PINS.json."""
    case = '9990003'
    jp, tp = job_files(t, case)
    L = t.work / 'qualification' / 'LEDGER_main.jsonl'
    adm_bad, adm, adm_notools = admission(t, case, jp, tp, with_title=False), admission(t, case, jp, tp), admission(t, case, jp, tp, tools=False)
    relq = qual_release(t, 'RELEASE_QUAL_MAIN.json', [adm_bad, adm, adm_notools], L)
    code, _, last = qprepare(t, relq, jp, tp, 'qual_A', 'A', adm_bad)
    t.check('qualification prepare with an admission that does not pin the title file: refused', lambda: code == 4
            and last == 'REFUSED: ADMISSION_JOB_TITLE_PIN', last)
    code, _, last = t.runner('prepare', '--release', relq, '--job', jp, '--job-title-file', tp, '--jobs-root', t.work / 'qual_A',
                             '--qualification')
    t.check('qualification prepare without an admission: refused', lambda: code == 4 and last == 'REFUSED: QUALIFICATION_NEEDS_ADMISSION', last)
    code, _, last = qprepare(t, t.release_q_path, jp, tp, 'qual_A', 'A', adm)
    t.check('R12: an admission the release does not list (a self-made one) is refused ADMISSION_NOT_RELEASED', lambda: code == 4
            and last == 'REFUSED: ADMISSION_NOT_RELEASED' and not (t.work / 'qual_A' / case).exists(), last)
    moved = t.work / 'ADMISSION_9990003_copy.json'
    shutil.copyfile(adm, moved)
    code, _, last = qprepare(t, relq, jp, tp, 'qual_A', 'A', moved)
    t.check('R12: the listed admission bytes at a path the release does not name are refused ADMISSION_NOT_RELEASED', lambda: code == 4
            and last == 'REFUSED: ADMISSION_NOT_RELEASED', last)
    code, out, last = qprepare(t, relq, jp, tp, 'qual_A', 'A', adm_notools)
    t.check('R12: a listed admission that does not pin the tools, evaluator, aggregator and JOBS.json is refused ADMISSION_MISSING_PINS',
            lambda: code == 4 and last == 'REFUSED: ADMISSION_MISSING_PINS' and 'research/evaluation/compare_target050.py' in out
            and 'JOBS.json' in out and not ledger(L), last)
    code, _, last = qprepare(t, relq, jp, tp, 'qual_A', 'A', adm)
    jd = t.work / 'qual_A' / case
    t.check('qualification prepare: NEXT: GENERATE', lambda: code == 0 and last.startswith('NEXT: GENERATE'), last)
    led = ledger(L)
    pp = jd / 'PACKET_PINS.json'
    t.check('R12: PACKET_PINS.json is read-only before NEXT: GENERATE and its sha256 is in the ledger, outside the job folder',
            lambda: pp.is_file() and not (os.stat(pp).st_mode & 0o222)
            and any(e['type'] == 'packet_pins' and e['packet_pins_sha256'] == sha_file(pp) for e in led)
            and 'packet/full/SOURCE_INVENTORY.json' in json.loads(pp.read_text(encoding='utf-8'))['files'], lambda: json.dumps([e['type'] for e in led]))
    t.check('R11: the ledger records the prepare (case, reader, folder, admission) and mirrors every record entry',
            lambda: [e['type'] for e in led] == ['prepare', 'packet_pins', 'record'] and led[0]['case_id'] == case and led[0]['reader'] == 'A'
            and led[0]['job_dir'] == str(jd) and led[0]['admission_sha256'] == sha_file(adm)
            and led[-1]['run_record_sha256'] == sha_file(jd / 'RUN_RECORD.json'), lambda: json.dumps([e['type'] for e in led]))
    jpB, tpB = jp, tp
    code, _, last = qprepare(t, relq, jpB, tpB, 'qual_B', 'B', adm)
    t.check('R11: run B before run A is frozen is refused QUALIFICATION_READER_A_NOT_FROZEN', lambda: code == 4
            and last == 'REFUSED: QUALIFICATION_READER_A_NOT_FROZEN' and not (t.work / 'qual_B' / case).exists(), last)
    resp = stand_in_response(t, jd, case)
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--job-title', '9990003另一案')
    t.check('qualification finish with a --job-title differing from the title file: refused, nothing consumed', lambda: code == 4
            and last == 'REFUSED: JOB_TITLE_MISMATCH' and not (jd / 'response' / 'response.json').exists(), last)
    elsewhere = t.work / 'response_copy.json'
    shutil.copyfile(resp, elsewhere)
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', elsewhere)
    t.check('qualification finish with a response outside the run output folder: refused', lambda: code == 4 and last == 'REFUSED: RESPONSE_PATH', last)
    title = json.loads(tp.read_text(encoding='utf-8'))['job_title']
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--job-title', title)
    t.check('R13: qualification finish without --generator-model is refused, nothing consumed', lambda: code == 4
            and last == 'REFUSED: GENERATOR_MODEL_REQUIRED' and not (jd / 'response' / 'response.json').exists(), last)
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--generator-model', 'stand-in (invented test)')
    t.check('R13: qualification finish without a generation record is refused GENERATION_RECORD_REQUIRED, nothing consumed', lambda: code == 4
            and last == 'REFUSED: GENERATION_RECORD_REQUIRED' and not (jd / 'response' / 'response.json').exists(), last)
    g = generation_record(jd, case, prompt_sha256='3' * 64)
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--generator-model', 'stand-in (invented test)', '--generation-record', g)
    t.check('R13: a generation record whose prompt sha256 is not run/GENERATOR_PROMPT.md is refused', lambda: code == 4
            and last == 'REFUSED: GENERATION_RECORD_PROMPT_MISMATCH' and not (jd / 'response' / 'response.json').exists(), last)
    g = generation_record(jd, case, started_utc='2020-01-01T00:00:00.000Z')
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--generator-model', 'stand-in (invented test)', '--generation-record', g)
    t.check('R13: a generation record whose times start before the generation stage ended is refused', lambda: code == 4
            and last == 'REFUSED: GENERATION_RECORD_TIMES', last)
    g = generation_record(jd, case, features={'memory': False})
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--generator-model', 'stand-in (invented test)', '--generation-record', g)
    t.check('R13: a generation record without every feature flag is refused GENERATION_RECORD_INVALID', lambda: code == 4
            and last == 'REFUSED: GENERATION_RECORD_INVALID', last)
    g = generation_record(jd, case)
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--generator-model', 'stand-in (invented test)',
                             '--generation-record', g, '--job-title', title)
    t.check('qualification finish: NEXT: VISUAL_REVIEW', lambda: code == 0 and last.startswith('NEXT: VISUAL_REVIEW'), last)
    fr = stages(jd, 'freeze_response')[-1] if stages(jd, 'freeze_response') else {}
    gf = jd / 'response' / 'GENERATION_RECORD.json'
    t.check('R13: the generation record is frozen read-only before the response, with transcript_status recorded as stated',
            lambda: gf.is_file() and not (os.stat(gf).st_mode & 0o222) and sha_file(gf) == sha_file(g)
            and fr.get('outputs', {}).get('generation_record', {}).get('sha256') == sha_file(g)
            and fr['facts']['generation_record']['transcript_status'] == 'not_available'
            and fr['facts']['generation_record']['model'] == 'stand-in (invented test)', lambda: json.dumps(fr.get('facts')))
    t.check('D3: the qualification record states the O40 rule (qualification_transcript_rule), not an open owner decision; '
            'not_available is attested_not_audited', lambda: fr['facts']['generation_record']['qualification_transcript_rule']
            == 'O40 2026-11-06 (research/guideline046_005/DECISIONS_OWNER_O23_O25.md, "O40 (2026-11-06): evidence of generator '
            'isolation in qualification"): exported or not_available, both accepted; count reported'
            and 'owner_decision_open' not in fr['facts']['generation_record']
            and fr['facts']['generation_record']['isolation_evidence'] == 'attested_not_audited', lambda: json.dumps(fr.get('facts')))
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', stand_in_review(jd, fail=True))
    t.check('visual-record with a failed item: FAIL recorded, NEXT: STOP_VISUAL_REVIEW_FAILED', lambda: code == 3
            and last == 'NEXT: STOP_VISUAL_REVIEW_FAILED' and stages(jd, 'visual-record')[-1]['completed'], last)
    code, _, last = t.runner('deliver-check', '--job-dir', jd)
    t.check('deliver-check on a qualification job: refused', lambda: code == 4 and last == 'REFUSED: DELIVERY_NOT_FOR_QUALIFICATION', last)
    code, out, last = t.runner('freeze', '--job-dir', jd)
    fz = json.loads((jd / 'FROZEN.json').read_text(encoding='utf-8')) if (jd / 'FROZEN.json').is_file() else {}
    listed = {x['path']: x['sha256'] for x in fz.get('files', [])}
    t.check('freeze: FROZEN.json lists every file with its sha256, NEXT: DONE', lambda: code == 0 and last == 'NEXT: DONE'
            and listed.get('RUN_RECORD.json') == sha_file(jd / 'RUN_RECORD.json')
            and len(listed) == sum(1 for p in jd.rglob('*') if p.is_file() and p.name != 'FROZEN.json'), last)
    t.check('R3: after freeze no file and no folder of the job (the job folder included) has a write bit', lambda: not no_write_bits(jd),
            lambda: json.dumps(no_write_bits(jd)[:5]))
    led = ledger(L)
    t.check('R11: the ledger holds the freeze with the FROZEN.json sha256 and the final stage', lambda: any(
        e['type'] == 'freeze' and e['job_dir'] == str(jd) and e['frozen_sha256'] == sha_file(jd / 'FROZEN.json')
        and e['final_stage'] == {'stage': 'visual-record', 'result': 'VISUAL_REVIEW_FAILED'} for e in led))
    t.check('D3: the ledger freeze entry carries the run\'s transcript status and whether its file was frozen (the O40 count)',
            lambda: [e.get('transcript') for e in led if e['type'] == 'freeze' and e['job_dir'] == str(jd)]
            == [{'transcript_status': 'not_available', 'transcript_file_frozen': False}],
            lambda: json.dumps([e.get('transcript') for e in led if e['type'] == 'freeze']))
    code, _, last = t.runner('verify-frozen', '--job-dir', jd)
    t.check('R3: verify-frozen on the untouched frozen folder: NEXT: DONE, exit 0', lambda: code == 0 and last == 'NEXT: DONE', last)
    code, out, last = t.runner('visual-record', '--job-dir', jd, '--review', resp)
    t.check('after freeze every subcommand is refused (and the refusal reports the folder intact)', lambda: code == 4
            and last == 'REFUSED: JOB_FROZEN' and last_json(out).get('detail', {}).get('frozen_folder_intact') is True, last)
    code, _, last = qprepare(t, relq, jp, tp, 'qual_A_retry', 'A', adm)
    t.check('R11: run A again under another jobs root after its response was frozen: refused QUALIFICATION_RESTART_NOT_ALLOWED',
            lambda: code == 4 and last == 'REFUSED: QUALIFICATION_RESTART_NOT_ALLOWED' and not (t.work / 'qual_A_retry' / case).exists(), last)
    adm_late = admission(t, case, jp, tp)
    rel_late = qual_release(t, 'RELEASE_QUAL_LATE.json', [adm, adm_late], L)
    code, _, last = qprepare(t, rel_late, jpB, tpB, 'qual_B', 'B', adm_late)
    t.check('R12: an admission frozen after the first qualification prepare of the ledger is refused', lambda: code == 4
            and last == 'REFUSED: ADMISSION_FROZEN_AFTER_FIRST_PREPARE', last)
    code, _, last = qprepare(t, relq, jpB, tpB, 'qual_B', 'B', adm)
    jdB = t.work / 'qual_B' / case
    t.check('R11: run B after run A is frozen: NEXT: GENERATE', lambda: code == 0 and last.startswith('NEXT: GENERATE'), last)
    summary = jdB / 'packet' / 'full' / 'PACKET_SUMMARY.json'
    force_write(summary, summary.read_bytes() + b' ')
    respB = stand_in_response(t, jdB, case, reader='B')
    gB = generation_record(jdB, case, reader='B')
    code, _, last = t.runner('finish', '--job-dir', jdB, '--response', respB, '--generator-model', 'stand-in (invented test)',
                             '--generation-record', gB)
    t.check('R12: a file PACKET_PINS.json lists, changed after NEXT: GENERATE, stops finish (STOP_PACKET_CHANGED)', lambda: code == 3
            and last == 'NEXT: STOP_PACKET_CHANGED', last)
    code, _, last = t.runner('freeze', '--job-dir', jdB)
    t.check('qualification run B frozen after its stop', lambda: code == 0 and last == 'NEXT: DONE', last)
    added = jd / 'qa' / 'ADDED_AFTER_FREEZE.txt'
    force_write(added, 'invented: a file added to a frozen folder')
    code, out, last = t.runner('verify-frozen', '--job-dir', jd)
    d = last_json(out)
    t.check('R3: verify-frozen finds a file added after freeze: NEXT: STOP_FROZEN_FOLDER_CHANGED, exit 3, and counts the writable entries once',
            lambda: code == 3 and last == 'NEXT: STOP_FROZEN_FOLDER_CHANGED' and d.get('unlisted') == 1
            and d.get('writable_entries') == len(no_write_bits(jd)), last)
    code, out, last = t.runner('freeze', '--job-dir', jd)
    t.check('R3: a command refused JOB_FROZEN reports the folder changed', lambda: code == 4 and last == 'REFUSED: JOB_FROZEN'
            and last_json(out).get('detail', {}).get('frozen_folder_intact') is False, last)
    force_unlink(added)


def test_qualification_ledger(t):
    """R11 on its own ledger: only JOBS.json cases; a JOBS.json nonattempt; a recorded nonattempt (N13); one run per case
    and reader; a restart only once and only after a technical stop at prepare; a truncated record refused."""
    L = t.work / 'qualification' / 'LEDGER_rules.jsonl'
    cases = {c: job_files(t, c, source=t.paths['broken'] if c == '9990033' else None) for c in ('9990031', '9990032', '9990033', '9990034')}
    adms = {c: admission(t, c, *cases[c]) for c in cases}
    rq = qual_release(t, 'RELEASE_QUAL_RULES.json', list(adms.values()), L)
    code, _, last = qprepare(t, rq, *cases['9990031'], 'qr_A', 'A', adms['9990031'])
    t.check('R11: a case that is not in the pinned JOBS.json is refused QUALIFICATION_CASE_NOT_IN_JOBS', lambda: code == 4
            and last == 'REFUSED: QUALIFICATION_CASE_NOT_IN_JOBS' and not (t.work / 'qr_A' / '9990031').exists(), last)
    code, _, last = qprepare(t, rq, *cases['9990034'], 'qr_A', 'A', adms['9990034'])
    t.check('R11: a case JOBS.json marks as a nonattempt is refused', lambda: code == 4 and last == 'REFUSED: QUALIFICATION_CASE_IS_NONATTEMPT', last)
    before = ledger(L)
    code, out, last = t.runner('nonattempt', '--release', rq, '--admission', adms['9990032'], '--case', '9990032', '--reader', 'A',
                               '--reason', 'NONATTEMPT_SOURCE_UNAVAILABLE', '--jobs-root', t.work / 'qr_NA', '--operator-model', 'test-harness')
    t.check('D2: nonattempt of a case JOBS.json schedules (nonattempt false) is refused QUALIFICATION_CASE_NOT_NONATTEMPT, '
            'nothing appended, no folder', lambda: code == 4 and last == 'REFUSED: QUALIFICATION_CASE_NOT_NONATTEMPT'
            and ledger(L) == before and not (t.work / 'qr_NA' / '9990032').exists(), last)
    code, out, last = t.runner('nonattempt', '--release', rq, '--admission', adms['9990034'], '--case', '9990034', '--reader', 'B',
                               '--reason', 'NONATTEMPT_OPERATOR_CHOICE', '--jobs-root', t.work / 'qr_NA_B', '--operator-model', 'test-harness')
    t.check('D2: nonattempt with a --reason other than the JOBS.json reason is refused NONATTEMPT_REASON_MISMATCH, nothing appended',
            lambda: code == 4 and last == 'REFUSED: NONATTEMPT_REASON_MISMATCH' and ledger(L) == before
            and not (t.work / 'qr_NA_B' / '9990034').exists(), last)
    code, out, last = t.runner('nonattempt', '--release', rq, '--admission', adms['9990034'], '--case', '9990034', '--reader', 'A',
                               '--reason', 'NONATTEMPT_SOURCE_UNAVAILABLE', '--jobs-root', t.work / 'qr_NA', '--operator-model', 'test-harness')
    t.check('N13/R11: nonattempt records a nonattempt in the ledger: NEXT: DONE', lambda: code == 0 and last == 'NEXT: DONE'
            and any(e['type'] == 'nonattempt' and e['case_id'] == '9990034' and e['reason'] == 'NONATTEMPT_SOURCE_UNAVAILABLE' for e in ledger(L)), last)
    na = t.work / 'qr_NA' / '9990034'
    nrec = (lambda: json.loads((na / 'RUN_RECORD.json').read_text(encoding='utf-8')))
    fzs = [e for e in ledger(L) if e['type'] == 'freeze' and e.get('job_dir') == str(na)]
    t.check('D2: the nonattempt is frozen at once: RUN_RECORD.json status NONATTEMPT_SOURCE_UNAVAILABLE (the JOBS.json reason), '
            'FROZEN.json, no write bit, its sha256 in the ledger',
            lambda: nrec()['status'] == 'NONATTEMPT_SOURCE_UNAVAILABLE' and nrec()['nonattempt']['reason_source'] == 'JOBS.json'
            and [s['stage'] for s in nrec()['stages']] == ['nonattempt', 'freeze'] and (na / 'FROZEN.json').is_file()
            and not no_write_bits(na) and len(fzs) == 1 and fzs[0]['frozen_sha256'] == sha_file(na / 'FROZEN.json')
            and sorted(p.name for p in (na / 'input').iterdir()) == ['ADMISSION.json', 'JOBS.json', 'RELEASE.json']
            and any(e['type'] == 'nonattempt' and e.get('job_dir') == str(na) for e in ledger(L)), last)
    code, _, last = t.runner('verify-frozen', '--job-dir', na)
    t.check('D2: verify-frozen on the nonattempt folder (listed in ALL_FROZEN.json like any run folder): NEXT: DONE',
            lambda: code == 0 and last == 'NEXT: DONE', last)
    code, _, last = t.runner('nonattempt', '--release', rq, '--admission', adms['9990034'], '--case', '9990034', '--reader', 'A',
                             '--jobs-root', t.work / 'qr_NA_again', '--operator-model', 'test-harness')
    t.check('D2: a second nonattempt of the same case and reader is refused QUALIFICATION_NONATTEMPT_RECORDED, no folder',
            lambda: code == 4 and last == 'REFUSED: QUALIFICATION_NONATTEMPT_RECORDED' and not (t.work / 'qr_NA_again').exists(), last)
    code, out, last = t.runner('nonattempt', '--release', rq, '--admission', adms['9990034'], '--case', '9990045', '--reader', 'A',
                               '--operator-model', 'test-harness')
    dflt = L.parent / 'nonattempts_A' / '9990045'
    t.check('D2: without --reason, a JOBS.json nonattempt that names no reason is recorded NONATTEMPT_SOURCE_UNAVAILABLE (protocol '
            'rule 6), in the default folder <ledger folder>/nonattempts_<reader>/<case id>',
            lambda: code == 0 and last == 'NEXT: DONE' and json.loads((dflt / 'RUN_RECORD.json').read_text(encoding='utf-8'))['status']
            == 'NONATTEMPT_SOURCE_UNAVAILABLE' and (dflt / 'FROZEN.json').is_file(), last)
    cj = load_runner()
    led_u = cj.Ledger(t.work / 'unit_never_written.jsonl')
    led_u.entries = [{'type': 'nonattempt', 'case_id': '9990032', 'reader': 'A', 'utc': '2026-01-02T00:00:00.000Z'}]
    t.check('R11: a case and reader with a recorded nonattempt cannot be prepared', lambda: refusal(
        cj.ledger_admit_prepare, led_u, {'9990032': {'case_id': '9990032', 'nonattempt': False}}, '9990032', 'A', '/x/9990032',
        {'frozen_utc': '2026-01-01T00:00:00.000Z'}) == 'QUALIFICATION_NONATTEMPT_RECORDED')
    code, _, last = qprepare(t, rq, *cases['9990033'], 'qr_A', 'A', adms['9990033'])
    jd1 = t.work / 'qr_A' / '9990033'
    t.check('a technical stop at prepare (the builder cannot read the invented broken source): NEXT: STOP_INVENTORY_BUILD_FAILED',
            lambda: code == 3 and last == 'NEXT: STOP_INVENTORY_BUILD_FAILED', last)
    now = utc_now()
    code, _, last = t.runner('interrupt', '--job-dir', jd1, '--reason', 'TECHNICAL_CONVERSATION_BROKE', '--started-utc', now,
                             '--ended-utc', now, '--operator-model', 'test-harness')
    t.check('D1: interrupt after a stage that did not print NEXT: GENERATE or SCOPE_READER is refused INTERRUPT_NOT_ALLOWED',
            lambda: code == 4 and last == 'REFUSED: INTERRUPT_NOT_ALLOWED' and not stages(jd1, 'interrupt')[-1]['completed'], last)
    code, _, last = qprepare(t, rq, *cases['9990033'], 'qr_A_restart1', 'A', adms['9990033'])
    t.check('R11: a second run of the same case and reader while the first is not frozen is refused QUALIFICATION_RUN_EXISTS',
            lambda: code == 4 and last == 'REFUSED: QUALIFICATION_RUN_EXISTS', last)
    keep = (jd1 / 'RUN_RECORD.json').read_bytes()
    r = json.loads(keep)
    force_write(jd1 / 'RUN_RECORD.json', (json.dumps(dict(r, stages=[]), ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
    code, _, last = t.runner('freeze', '--job-dir', jd1)
    t.check('R2/R11: a qualification record truncated to a valid shorter chain is refused RUN_RECORD_NOT_IN_LEDGER, nothing appended',
            lambda: code == 4 and last == 'REFUSED: RUN_RECORD_NOT_IN_LEDGER' and json.loads((jd1 / 'RUN_RECORD.json').read_bytes())['stages'] == [], last)
    force_write(jd1 / 'RUN_RECORD.json', keep)
    code, _, last = t.runner('freeze', '--job-dir', jd1)
    t.check('the restored record freezes: NEXT: DONE', lambda: code == 0 and last == 'NEXT: DONE', last)
    code, _, last = qprepare(t, rq, *cases['9990033'], 'qr_B', 'B', adms['9990033'])
    t.check('DN7: run B while run A ended in a technical stop whose one restart is unused is refused '
            'QUALIFICATION_READER_A_RESTART_UNUSED, no folder', lambda: code == 4
            and last == 'REFUSED: QUALIFICATION_READER_A_RESTART_UNUSED' and not (t.work / 'qr_B' / '9990033').exists(), last)
    code, _, last = qprepare(t, rq, *cases['9990033'], 'qr_A_restart1', 'A', adms['9990033'])
    jd2 = t.work / 'qr_A_restart1' / '9990033'
    t.check('R11: one restart after a frozen technical stop at prepare is allowed; both the record and the ledger name it',
            lambda: code == 3 and last == 'NEXT: STOP_INVENTORY_BUILD_FAILED' and record(jd2)['restart_of'] == str(jd1)
            and any(e['type'] == 'prepare' and e['job_dir'] == str(jd2) and e['restart_of'] == str(jd1) for e in ledger(L)), last)
    code, _, last = t.runner('freeze', '--job-dir', jd2)
    code, _, last = qprepare(t, rq, *cases['9990033'], 'qr_A_restart2', 'A', adms['9990033'])
    t.check('R11: a second restart is refused QUALIFICATION_RESTART_USED', lambda: code == 4 and last == 'REFUSED: QUALIFICATION_RESTART_USED', last)
    code, _, last = qprepare(t, rq, *cases['9990033'], 'qr_B', 'B', adms['9990033'])
    t.check('DN7 (guard): once run A\'s one restart is used and frozen, run B may start', lambda: code == 3
            and last == 'NEXT: STOP_INVENTORY_BUILD_FAILED' and (t.work / 'qr_B' / '9990033' / 'RUN_RECORD.json').is_file(), last)


def test_route_check_failure(t):
    """9990004: a failed route check is the outcome, never retried; R2: an edited record is refused before anything is
    appended; N12: freeze completes a missing FROZEN.json with the same bytes."""
    code, out, last, jd = prepare(t, '9990004')
    resp = stand_in_response(t, jd, '9990004', break_it=True)
    code, out, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    fin = stages(jd, 'finish')
    t.check('finish with a response the route check rejects: NEXT: STOP_ROUTE_CHECK_FAILED, failure recorded, no carrier',
            lambda: code == 3 and last == 'NEXT: STOP_ROUTE_CHECK_FAILED' and fin and fin[-1]['completed'] and fin[-1]['result'] == 'ROUTE_CHECK_FAILED'
            and fin[-1]['codes'] and not (jd / 'carrier' / 'convert').exists() and (jd / 'response' / 'ROUTE_CHECK.json').is_file(), last)
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', stand_in_response(t, jd, '9990004'))
    t.check('no retry after a failed route check', lambda: code == 4 and last == 'REFUSED: STAGE_ALREADY_COMPLETED', last)
    keep = (jd / 'RUN_RECORD.json').read_bytes()
    r = json.loads(keep)
    for s in r['stages']:
        if s['stage'] in ('freeze_response', 'finish') and s['completed']:
            s['completed'] = False                        # the review's S2: unmark the failed stage
    edited = (json.dumps(r, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
    force_write(jd / 'RUN_RECORD.json', edited)
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', stand_in_response(t, jd, '9990004'))
    t.check('R2: a record edited by hand (a failed finish unmarked) refuses every command RUN_RECORD_CHAIN_BROKEN, nothing appended',
            lambda: code == 4 and last == 'REFUSED: RUN_RECORD_CHAIN_BROKEN' and (jd / 'RUN_RECORD.json').read_bytes() == edited, last)
    r['stages'] = list(reversed(r['stages']))
    force_write(jd / 'RUN_RECORD.json', (json.dumps(r, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
    code, _, last = t.runner('freeze', '--job-dir', jd)
    t.check('R2: a reordered record is refused RUN_RECORD_CHAIN_BROKEN', lambda: code == 4 and last == 'REFUSED: RUN_RECORD_CHAIN_BROKEN', last)
    force_write(jd / 'RUN_RECORD.json', keep)
    code, out, last = t.runner('freeze', '--job-dir', jd)
    first = (jd / 'FROZEN.json').read_bytes() if (jd / 'FROZEN.json').is_file() else b''
    os.chmod(jd, stat.S_IMODE(os.lstat(jd).st_mode) | stat.S_IWUSR)
    (jd / 'FROZEN.json').unlink()                         # as if writing FROZEN.json had failed after the freeze entry
    code, out, last = t.runner('freeze', '--job-dir', jd)
    t.check('N12: freeze after a recorded freeze without FROZEN.json completes it, byte-identical (deterministic), nothing appended',
            lambda: code == 0 and last == 'NEXT: DONE' and (jd / 'FROZEN.json').read_bytes() == first and first
            and last_json(out).get('completed_frozen_json_of_the_recorded_freeze') is True and stages(jd, 'freeze')[-1]['seq'] == len(record(jd)['stages']), last)
    code, _, last = t.runner('verify-frozen', '--job-dir', jd)
    t.check('verify-frozen after the completed freeze: NEXT: DONE', lambda: code == 0 and last == 'NEXT: DONE', last)


def test_stage_output_exists(t):
    """R2: a frozen output of a stage that exists without the stage's completing entry refuses the stage."""
    code, out, last, jd = prepare(t, '9990022')
    resp = stand_in_response(t, jd, '9990022')
    (jd / 'response' / 'response.json').write_bytes(resp.read_bytes())
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    t.check('R2: response/response.json present without a completed freeze_response: finish refused STAGE_OUTPUT_EXISTS',
            lambda: code == 4 and last == 'REFUSED: STAGE_OUTPUT_EXISTS' and stages(jd, 'finish')[-1]['completed'] is False, last)


def scope_reader_response(jd, case, kind='fresh_context_scope_reader', end_row=None, end=None):
    dg = jd / 'scope' / 'reader' / 'input' / 'SCOPE_DIGEST.json'
    r = {'schema': 'cps.scope-reader-response.v1', 'case_id': case, 'digest_sha256': sha_file(dg),
         'reader': {'kind': kind, 'model': 'invented-test-stand-in', 'effort': 'n/a'},
         'bill_sheet_index': 2, 'end_row': end_row or end,
         'sheets': [{'index': 1, 'role': 'summary', 'in_scope': False, 'reason': 'section totals without unit prices'},
                    {'index': 2, 'role': 'bill', 'in_scope': True, 'reason': 'item, name, unit, quantity, unit price and amount header'}],
         'doubts': []}
    p = jd / 'scope' / 'reader' / 'output' / 'SCOPE_READER_RESPONSE.json'
    p.write_text(json.dumps(r, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return p


def test_large(t):
    """More than 2,500 content cells: prepare -> NEXT: SCOPE_READER; an agreeing reader -> scoped packet, NEXT: GENERATE;
    a disagreeing reader -> NEXT: OWNER_DECISION; a stand-in reader kind -> not admissible, STOP."""
    code, out, last, jd = prepare(t, '9990005', source=t.paths['large'])
    prompt = next_path(last, 'prompt')
    pr = stages(jd, 'prepare')[-1] if (jd / 'RUN_RECORD.json').is_file() else {}
    t.check('large workbook: prepare prints NEXT: SCOPE_READER (exit 0)', lambda: code == 0 and last.startswith('NEXT: SCOPE_READER '), last)
    t.check('large workbook: content cells above 2,500, scope tool PROPOSED', lambda: pr.get('facts', {}).get('content_cells_literal_or_cached', 0) > 2500
            and pr['facts']['scope_tool']['status'] == 'PROPOSED')
    t.check('scope reader folder holds exactly the digest and the rules excerpt; prompt filled',
            lambda: sorted(p.name for p in (jd / 'scope' / 'reader' / 'input').iterdir()) == ['SCOPE_DIGEST.json', 'SCOPE_RULES_EXCERPT.md']
            and prompt is not None and '{SCOPE_RUN}' not in prompt.read_text(encoding='utf-8') and not (jd / 'run' / 'A').exists())
    rr = scope_reader_response(jd, '9990005', end=t.large_end_row)
    code, out, last = t.runner('scope-finish', '--job-dir', jd, '--reader-response', rr)
    sf = stages(jd, 'scope-finish')[-1] if (jd / 'RUN_RECORD.json').is_file() else {}
    t.check('scope-finish with an agreeing reader: NEXT: GENERATE on the scoped packet', lambda: code == 0 and last.startswith('NEXT: GENERATE')
            and sf.get('facts', {}).get('check_inventory_scoped', {}).get('scope') == 'applied'
            and sf['facts']['scoped_verify']['status'] == 'PASS', lambda: last + json.dumps(sf.get('codes')))
    t.check('N1: scope-finish requires and records the receipt\'s and --verify\'s own route check of the scoped inventory (PASS)',
            lambda: sf.get('facts', {}).get('scoped_verify', {}).get('route_check', {}).get('pass') is True
            and sf['facts']['scoped_verify']['route_check']['receipt_route_check_inventory'] == 'PASS'
            and sf['facts']['scoped_verify']['route_check']['verify_route_check_inventory'] == 'PASS', lambda: json.dumps(sf.get('facts', {}).get('scoped_verify')))
    inv = jd / 'run' / 'A' / 'input' / 'packet' / 'SOURCE_INVENTORY.json'
    t.check('the generation packet is the scoped inventory (context:scope)', lambda: inv.is_file()
            and any(f['ref'] == 'context:scope' for f in json.loads(inv.read_text(encoding='utf-8'))['context_facts']))
    pp = json.loads((jd / 'PACKET_PINS.json').read_text(encoding='utf-8')) if (jd / 'PACKET_PINS.json').is_file() else {'files': {}}
    t.check('R12: a scoped job pins the decision, the receipt, the scoped packet and the frozen reader response in PACKET_PINS.json',
            lambda: all(k in pp['files'] for k in ('scope/decision/SCOPE_DECISION.json', 'scope/scoped_packet/SCOPED_INVENTORY_RECEIPT.json',
                                           'scope/scoped_packet/SOURCE_INVENTORY.json', 'scope/SCOPE_READER_RESPONSE.json',
                                           'scope/tool/SCOPE_PROPOSAL.json', 'run/GENERATOR_PROMPT.md', 'run/A/RUN_INPUT_PINS.json')),
            lambda: json.dumps(sorted(pp['files'])[:10]))
    code, out, last, jd2 = prepare(t, '9990007', source=t.paths['large'])
    rr = scope_reader_response(jd2, '9990007', end=t.large_end_row - 1)
    code, out, last = t.runner('scope-finish', '--job-dir', jd2, '--reader-response', rr)
    t.check('scope-finish with a disagreeing reader: NEXT: OWNER_DECISION, never a tie-break', lambda: code == 3 and last == 'NEXT: OWNER_DECISION'
            and (jd2 / 'scope' / 'decision' / 'SCOPE_HOLD.json').is_file() and not (jd2 / 'run' / 'A').exists(), last)
    code, out, last, jd3 = prepare(t, '9990008', source=t.paths['large'])
    rr = scope_reader_response(jd3, '9990008', kind='engineering_stand_in', end=t.large_end_row)
    code, out, last = t.runner('scope-finish', '--job-dir', jd3, '--reader-response', rr)
    t.check('scope-finish with a reader that is not a fresh-context reader: STOP (not admissible)', lambda: code == 3
            and last == 'NEXT: STOP_SCOPE_DECISION_NOT_ADMISSIBLE', last)


def test_r1_scope_inputs(t):
    """R1: prepare makes the scope tool's files and the full packet read-only; scope-finish re-verifies them, so a proposal
    edited to side with a disagreeing reader stops the job (STOP_SCOPE_INPUTS_CHANGED) and nothing is generated."""
    code, out, last, jd = prepare(t, '9990021', source=t.paths['large'])
    t.check('R1: after prepare the scope tool files, the full packet and the reader inputs have no write bit',
            lambda: code == 0 and not no_write_bits(jd / 'scope' / 'tool') and not no_write_bits(jd / 'packet')
            and not no_write_bits(jd / 'scope' / 'reader' / 'input'), lambda: json.dumps(no_write_bits(jd / 'packet')[:3]))
    prop = jd / 'scope' / 'tool' / 'SCOPE_PROPOSAL.json'
    p = json.loads(prop.read_text(encoding='utf-8'))
    p['bill']['end_row'] = t.large_end_row - 1            # the operator "sides" with the reader
    force_write(prop, json.dumps(p, ensure_ascii=False, indent=1) + '\n')
    rr = scope_reader_response(jd, '9990021', end=t.large_end_row - 1)
    code, out, last = t.runner('scope-finish', '--job-dir', jd, '--reader-response', rr)
    sf = stages(jd, 'scope-finish')[-1] if stages(jd, 'scope-finish') else {}
    t.check('R1: scope-finish with an edited scope proposal: NEXT: STOP_SCOPE_INPUTS_CHANGED (recorded), no decision, no run folder',
            lambda: code == 3 and last == 'NEXT: STOP_SCOPE_INPUTS_CHANGED' and sf.get('completed') and 'CHANGED_SCOPE_TOOL' in sf.get('codes', [])
            and not (jd / 'scope' / 'decision').exists() and not (jd / 'run' / 'A').exists(), lambda: last + json.dumps(sf.get('codes')))


def test_r4_lock_and_interruption(t):
    """R4: a second command while finish runs is refused JOB_BUSY (finish's result is kept); a finish killed after the
    response freeze is recorded as INTERRUPTED by the next command, never re-run, and freeze names it. R8 on the same
    job: a page image swapped after finish stops visual-record (STOP_VISUAL_PAGES_CHANGED)."""
    code, out, last, jd = prepare(t, '9990023')
    resp = stand_in_response(t, jd, '9990023')
    p = subprocess.Popen([sys.executable, '-I', '-B', str(RUNNER), 'finish', '--job-dir', str(jd), '--response', str(resp)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ok = wait_for(lambda: any(s['stage'] == 'freeze_response' for s in record(jd)['stages']))
    code2, _, last2 = t.runner('freeze', '--job-dir', jd)
    running = p.poll() is None
    out_b, _ = p.communicate(timeout=1800)
    flast = out_b.decode('utf-8', 'replace').strip().splitlines()[-1] if out_b.strip() else ''
    t.check('R4: freeze while finish runs is refused JOB_BUSY and appends nothing; finish then completes NEXT: VISUAL_REVIEW',
            lambda: ok and running and code2 == 4 and last2 == 'REFUSED: JOB_BUSY' and not stages(jd, 'freeze') and not (jd / 'FROZEN.json').exists()
            and flast.startswith('NEXT: VISUAL_REVIEW') and stages(jd, 'finish')[-1]['completed'], lambda: f'{last2} / {flast}')
    swapped = {}

    def png_swap():
        vi = jd / 'qa' / 'visual_internal'
        force_write(vi / 'page-0002.png', (vi / 'page-0003.png').read_bytes())
        tl = jd / 'qa' / 'visual_deliverable' / 'tiles'          # F3: a delivered tile swapped at the same time
        if (tl / 'page-0001-tile-02.png').exists():
            force_write(tl / 'page-0001-tile-02.png', (tl / 'page-0001-tile-01.png').read_bytes())
        code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', stand_in_review(jd))
        vr = stages(jd, 'visual-record')[-1] if stages(jd, 'visual-record') else {}
        swapped['codes'] = vr.get('codes', [])
        return (code == 3 and last == 'NEXT: STOP_VISUAL_PAGES_CHANGED' and vr.get('completed') and 'internal page 2' in vr.get('codes', [])
                and not (jd / 'qa' / 'VISUAL_RECORD.json').exists())
    t.check('R8: a page image swapped after finish stops visual-record as tampering (NEXT: STOP_VISUAL_PAGES_CHANGED, recorded)', png_swap)
    t.check('F3-tiles/R8: a delivered tile swapped after finish is caught as tampering too (deliverable page 1 tile 2 in the codes)',
            lambda: 'deliverable page 1 tile 2' in swapped['codes'], lambda: json.dumps(swapped.get('codes')))
    code, out, last, jd = prepare(t, '9990024')
    resp = stand_in_response(t, jd, '9990024')
    p = subprocess.Popen([sys.executable, '-I', '-B', str(RUNNER), 'finish', '--job-dir', str(jd), '--response', str(resp)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    wait_for(lambda: any(s['stage'] == 'freeze_response' for s in record(jd)['stages']))
    time.sleep(0.5)
    p.send_signal(signal.SIGKILL)                           # e.g. the operator's shell tool timed out
    p.communicate()
    wait_for(lambda: unlocked(jd), timeout=600)             # DN4: a tool the killed runner started holds the lock until it ends
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    fin = stages(jd, 'finish')
    t.check('R4: after a finish killed past the response freeze, the next command records INTERRUPTED and finish is never re-run',
            lambda: code == 4 and last == 'REFUSED: STAGE_ALREADY_COMPLETED' and fin and fin[0]['result'] == 'INTERRUPTED' and fin[0]['completed']
            and fin[0]['next'] == 'STOP_INTERRUPTED' and not (jd / '.STAGE_IN_PROGRESS.json').exists(), last)
    code, _, last = t.runner('freeze', '--job-dir', jd)
    fz = stages(jd, 'freeze')[-1] if stages(jd, 'freeze') else {}
    t.check('R4: freeze names the interrupted stage as the final stage', lambda: code == 0 and last == 'NEXT: DONE'
            and fz.get('facts', {}).get('final_stage') == {'stage': 'finish', 'result': 'INTERRUPTED'}, lambda: json.dumps(fz.get('facts')))


def test_r5_run_folder(t):
    """R5: prepare makes the generator's input folders read-only; an unpinned file next to the generator's inputs, or an
    unexpected file in its output folder, stops finish."""
    code, out, last, jd = prepare(t, '9990025')
    inp = jd / 'run' / 'A' / 'input'
    t.check('R5: after prepare run/A/input (files and folders) has no write bit', lambda: code == 0 and not no_write_bits(inp),
            lambda: json.dumps(no_write_bits(inp)[:3]))
    force_write(inp / 'packet' / 'INVENTED_HISTORICAL_TARGET.json', '{"invented": "a historical answer that must never reach the generator"}')
    resp = stand_in_response(t, jd, '9990025')
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    fin = stages(jd, 'finish')[-1] if stages(jd, 'finish') else {}
    t.check('R5: an unpinned file in run/A/input/packet: NEXT: STOP_RUN_INPUTS_CHANGED (recorded), no route check',
            lambda: code == 3 and last == 'NEXT: STOP_RUN_INPUTS_CHANGED' and 'RUN_INPUT_FILES_NOT_THE_PINNED_SET' in fin.get('codes', [])
            and not (jd / 'response' / 'ROUTE_CHECK.json').exists(), lambda: last + json.dumps(fin.get('codes')))
    code, out, last, jd = prepare(t, '9990026')
    resp = stand_in_response(t, jd, '9990026')
    (jd / 'run' / 'A' / 'output' / 'INVENTED_EARLIER_RESPONSE.json').write_text('{"invented": "an earlier response"}', encoding='utf-8')
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    t.check('R5: an unexpected file in run/A/output: NEXT: STOP_RUN_OUTPUT_UNEXPECTED', lambda: code == 3 and last == 'NEXT: STOP_RUN_OUTPUT_UNEXPECTED', last)


def test_visual_fail_blocks_delivery(t):
    code, out, last, jd = prepare(t, '9990006')
    code, out, last = t.runner('finish', '--job-dir', jd, '--response', stand_in_response(t, jd, '9990006'))
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', stand_in_review(jd, fail=True))
    t.check('real job: a failed visual review stops the job', lambda: code == 3 and last == 'NEXT: STOP_VISUAL_REVIEW_FAILED', last)
    code, _, last = t.runner('deliver-check', '--job-dir', jd)
    t.check('deliver-check after a failed visual review: refused', lambda: code == 4 and last == 'REFUSED: VISUAL_REVIEW_NOT_PASSED', last)


def load_runner():
    spec = importlib.util.spec_from_file_location('cps_job_under_test', RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_manifest(d, name, mapping, main, clipped=None, clipped_count=None):
    d.mkdir(parents=True, exist_ok=True)
    m = {'saved_xlsx': {'sha256': '0' * 64}, 'main_sheet': main, 'page_sheet_mapping': {str(k): v for k, v in mapping.items()},
         'images': [{'page': k, 'file': f'page-{k:04d}.png'} for k in mapping],
         'possibly_clipped_cells': {'count': len(clipped or []) if clipped_count is None else clipped_count, 'first': clipped or []},
         'possibly_cut_cells': {'count': 0, 'first': []}}
    p = d / name
    p.write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
    return m, p


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def refusal(fn, *a, **k):
    try:
        fn(*a, **k)
    except Exception as e:                                  # noqa: BLE001
        return getattr(e, 'code', type(e).__name__)
    return None


def test_units(t):
    """Unit checks of the page selection (condition 8), the review n/a rules, the duplicate-key check (condition 5) and the
    delivery file check (condition 9), on invented manifests and files."""
    cj = load_runner()
    u = t.work / 'unit'
    jd = cj.Job(u)
    main = '9990009示例(未填)'
    mapping = {1: main, 2: '來源與審查', 3: '來源與審查', 4: '來源與審查', 5: '來源與審查', 6: '來源與審查', 7: '組成參考', 8: '組成連結', 9: None}
    dl = fake_manifest(u / 'd', 'M.json', {1: main, 2: main, 3: main}, main)
    sel = cj.select_pages(jd, {'deliverable': dl, 'internal': fake_manifest(u / 'a', 'M.json', mapping, main)})['workbooks']
    t.check('page selection: every delivered page; internal main, composition, unmapped pages and review pages 1, 2 and the last',
            lambda: sel['deliverable']['selected'] == [1, 2, 3] and sel['internal']['selected'] == [1, 2, 3, 6, 7, 8, 9], lambda: json.dumps(sel['internal']['selected']))
    sel = cj.select_pages(jd, {'deliverable': dl, 'internal': fake_manifest(u / 'b', 'M.json', mapping, main,
                                                                             clipped=[{'sheet': '來源與審查', 'cell': 'E40'}])})['workbooks']
    t.check('page selection: a possibly_clipped_cells cell on the review sheet selects every review page',
            lambda: sel['internal']['selected'] == list(range(1, 10)), lambda: json.dumps(sel['internal']['selected']))
    sel = cj.select_pages(jd, {'deliverable': dl, 'internal': fake_manifest(u / 'c', 'M.json', mapping, main,
                                                                             clipped=[{'sheet': main, 'cell': 'D2'}], clipped_count=300)})['workbooks']
    t.check('page selection: a capped clipped-cell list (pages unknown) selects every review page', lambda: sel['internal']['selected'] == list(range(1, 10)))
    sel = cj.select_pages(jd, {'deliverable': dl, 'internal': fake_manifest(u / 'e', 'M.json', mapping, main,
                                                                             clipped=[{'sheet': main, 'cell': 'D2'}])})['workbooks']
    t.check('page selection: a clipped cell on the main sheet adds no review page', lambda: sel['internal']['selected'] == [1, 2, 3, 6, 7, 8, 9])
    pages = cj.select_pages(jd, {'deliverable': dl, 'internal': fake_manifest(u / 'f', 'M.json', mapping, main)})

    def review(na, pg_=None, reviewer=None):
        pg_ = pg_ or pages
        rv = {'schema': 'cps.visual-review.v1', 'reviewer': dict(REVIEWER) if reviewer is None else reviewer, 'overall': 'PASS', 'failures': []}
        for key, wb in pg_['workbooks'].items():
            rv[key] = {'manifest_sha256': wb['manifest_sha256'],
                       'pages': {str(p): {str(i): {'result': 'pass', 'note': ''} for i in range(1, 10)} for p in wb['selected']}}
        for key, pg, it in na:
            rv[key]['pages'][pg][it] = {'result': 'n/a', 'note': ''}
        return rv
    ok = review([('internal', '2', '1'), ('internal', '2', '6'), ('internal', '2', '7'), ('internal', '1', '8'), ('internal', '7', '8'),
                 ('deliverable', '1', '8')])
    t.check('review n/a: accepted where the item does not apply', lambda: cj.check_review(ok, pages) == ([], []), lambda: json.dumps(cj.check_review(ok, pages)))
    for key, pg, it in (('deliverable', '1', '3'), ('internal', '1', '6'), ('internal', '2', '8'), ('internal', '7', '2')):
        probs, _ = cj.check_review(review([(key, pg, it)]), pages)
        t.check(f'review n/a: refused for {key} page {pg} item {it}', lambda: any('n/a not allowed' in x for x in probs), lambda: json.dumps(probs))
    bad = review([])
    bad['internal']['manifest_sha256'] = '1' * 64
    t.check('review: a manifest sha256 that is not the rendered one is a problem', lambda: 'internal: manifest_sha256' in cj.check_review(bad, pages)[0])
    t.check('condition 5: duplicate JSON keys detected', lambda: cj.has_duplicate_keys(b'{"a": 1, "b": {"c": 1, "c": 2}}')
            and not cj.has_duplicate_keys(b'{"a": 1, "b": {"c": 1}}'))
    f = u / 'deliver.xlsx'
    f.write_bytes(b'invented workbook bytes')
    want = sha(b'invented workbook bytes')
    c, _, _ = cj.delivery_file_checks(f, want)
    t.check('condition 9: a regular single-link file with the saved-QA hash passes', lambda: all(c.values()), lambda: json.dumps(c))
    link = u / 'link.xlsx'
    os.symlink(f, link)
    c, _, _ = cj.delivery_file_checks(link, want)
    t.check('condition 9: a symbolic link to identical bytes fails', lambda: not c['regular_file'] and not c['not_symlink'], lambda: json.dumps(c))
    hard = u / 'hard.xlsx'
    os.link(f, hard)
    c, _, _ = cj.delivery_file_checks(f, want)
    t.check('condition 9: a hard link to identical bytes elsewhere fails (review N3r)', lambda: not c['single_link'] and c['sha256_equals_saved_qa'], lambda: json.dumps(c))


def unit_review(cj, u, reviewer=None, cut=None):
    """Invented manifests and a review that passes every selected item; cut: possibly_cut_cells of the delivered one."""
    jd = cj.Job(u)
    main = '9990009示例(未填)'
    mapping = {1: main, 2: '來源與審查', 3: '來源與審查', 7: '組成參考'}
    dlc, dlcp = fake_manifest(u / 'd', 'M.json', {1: main, 2: main}, main)
    if cut:
        dlc['possibly_cut_cells'] = {'count': len(cut), 'first': [{'sheet': main, 'cell': c, 'kind': 'string',
                                                                   'neighbours_filled': {'left': True}} for c in cut]}
        dlcp.write_text(json.dumps(dlc, ensure_ascii=False), encoding='utf-8')
    pages = cj.select_pages(jd, {'deliverable': (dlc, dlcp), 'internal': fake_manifest(u / 'i', 'M.json', mapping, main)})
    rv = {'schema': 'cps.visual-review.v1', 'reviewer': dict(REVIEWER) if reviewer is None else reviewer, 'overall': 'PASS', 'failures': []}
    for key, wb in pages['workbooks'].items():
        rv[key] = {'manifest_sha256': wb['manifest_sha256'],
                   'pages': {str(p): {str(i): {'result': 'pass', 'note': ''} for i in range(1, 10)} for p in wb['selected']}}
    for p in rv['internal']['pages']:
        if pages['workbooks']['internal']['pages'][p]['role'] != 'review':
            rv['internal']['pages'][p]['8'] = {'result': 'n/a', 'note': ''}
    return pages, rv


def test_units_review(t):
    """R6 (reviewer kind, model, effort and conversation id), R7 (cut cells) and N4 (a failures list) on invented reviews."""
    cj = load_runner()
    u = t.work / 'unit_review'
    pages, rv = unit_review(cj, u / 'a', reviewer={'kind': 'operator_self_check', 'model': 'y', 'effort': 'z', 'conversation_id': 'c'})
    t.check('R6: a reviewer kind other than fresh_context_visual_reviewer is a problem (never PASS)',
            lambda: 'reviewer.kind' in cj.check_review(rv, pages)[0] and not cj.check_review(rv, pages)[1])
    pages, rv = unit_review(cj, u / 'b', reviewer={'kind': 'fresh_context_visual_reviewer', 'model': 'y', 'effort': ' '})
    t.check('R6: a blank effort and no conversation id are problems',
            lambda: {'reviewer.effort', 'reviewer.conversation_id'} <= set(cj.check_review(rv, pages)[0]))
    pages, rv = unit_review(cj, u / 'c', reviewer={'kind': 'fresh_context_visual_reviewer', 'model': 'y', 'effort': 'z'})
    t.check('R6: without a conversation id the review is a problem; the operator-attested id stands in for it',
            lambda: cj.check_review(rv, pages)[0] == ['reviewer.conversation_id'] and cj.check_review(rv, pages, 'attested-id') == ([], []))
    pages, rv = unit_review(cj, u / 'd', cut=['C5', 'C40'])
    for p in rv['deliverable']['pages'].values():
        p['8'] = {'result': 'n/a', 'note': ''}
    rv['deliverable']['cut_cells'] = {'C5': {'result': 'pass', 'note': ''}, 'C40': {'result': 'pass', 'note': ''}}
    t.check('R7: item 8 n/a on every delivered page while possibly_cut_cells lists cells is a problem (REVIEW_INCOMPLETE)',
            lambda: any('item 8 is n/a on every page' in x for x in cj.check_review(rv, pages)[0]), lambda: json.dumps(cj.check_review(rv, pages)))
    pages, rv = unit_review(cj, u / 'e', cut=['C5', 'C40'])
    rv['deliverable']['cut_cells'] = {'C5': {'result': 'pass', 'note': ''}}
    t.check('R7: a listed cut cell missing from deliverable.cut_cells is a problem',
            lambda: any('cut_cells keys' in x or 'cut cell C40' in x for x in cj.check_review(rv, pages)[0]))
    rv2 = json.loads(json.dumps(rv))
    rv2['deliverable']['cut_cells']['C40'] = {'result': 'fail', 'note': 'invented: text cut'}
    t.check('R7: a cut cell judged fail is a failure; every listed cell judged and item 8 used on a page is accepted',
            lambda: cj.check_review(rv2, pages) == ([], ['deliverable cut cell C40']), lambda: json.dumps(cj.check_review(rv2, pages)))
    pages, rv = unit_review(cj, u / 'f')
    rv['failures'] = ['deliverable page 1 item 6: invented']
    t.check('N4: overall PASS with a non-empty failures list is a failure (recorded FAIL), not an accepted PASS',
            lambda: bool(cj.check_review(rv, pages)[1]))
    pages, rv = unit_review(cj, u / 'g')
    t.check('R6/R7 (guard): the complete fresh-context review with no cut cell has no problem', lambda: cj.check_review(rv, pages) == ([], []),
            lambda: json.dumps(cj.check_review(rv, pages)))


def test_units_record(t):
    """R2 (the record chain), R4 (recorded stop after consumption, interruption marker, job lock) and N12 (traceback)."""
    cj = load_runner()
    rdir = t.work / 'unit_record'
    rdir.mkdir()
    (rdir / 'logs').mkdir()
    rj = cj.Job(rdir)
    rj.create({'schema': cj.RECORD_SCHEMA, 'case_id': '9990009', 'reader': 'A', 'qualification': False, 'stages': []})
    for i in range(3):
        rj.append(cj.Stage(rj, f'invented_{i}', None).entry('INVENTED', 'DONE', True))
    raw = (rdir / 'RUN_RECORD.json').read_bytes()
    rec = json.loads(raw)
    t.check('R2: the runner\'s own record verifies (seq 1..n, each entry chained to the exact earlier bytes)', lambda: cj.chain_problem(rec, raw) is None)
    e = json.loads(raw)
    e['stages'][1]['result'] = 'EDITED_BY_OPERATOR'
    r2 = json.loads(raw)
    r2['stages'] = [r2['stages'][1], r2['stages'][0], r2['stages'][2]]
    r3 = json.loads(raw)
    r3['case_id'] = '9990019'
    r4 = json.loads(raw)
    r4['stages'][-1]['result'] = 'EDITED_BY_OPERATOR'              # the last entry: no later entry chains to it
    r5 = json.loads(raw)
    r5['stages'] = r5['stages'][:1]
    r5['stages'][0]['completed'] = False                            # the review's S2b: truncate, then edit what is left
    t.check('R2: an edited entry, a reordered record, an edited header and reformatted bytes each break the chain',
            lambda: all(cj.chain_problem(x, cj.dumps(x)) is not None for x in (e, r2, r3)) and cj.chain_problem(rec, raw.replace(b'\n', b'\n ', 1)) is not None)
    t.check('R2: an edit of the last entry, alone or after a truncation, breaks the chain (entry_sha256)',
            lambda: cj.chain_problem(r4, cj.dumps(r4)) == 'entry 3: entry_sha256' and cj.chain_problem(r5, cj.dumps(r5)) == 'entry 1: entry_sha256')
    code = quiet(cj.run_stage, rj, cj.Stage(rj, 'finish', None), lambda: (_ for _ in ()).throw(cj.Refused('INVENTED_AFTER_FREEZE')))
    last_e = json.loads((rdir / 'RUN_RECORD.json').read_bytes())['stages'][-1]
    t.check('R4: a refusal raised after a stage began consuming is recorded as a completed stop (exit 3), never as a REFUSED retry',
            lambda: code == 3 and last_e['completed'] is True and last_e['next'] == 'STOP_INVENTED_AFTER_FREEZE'
            and last_e['result'] == 'REFUSED_AFTER_CONSUMPTION' and not (rdir / '.STAGE_IN_PROGRESS.json').exists(), lambda: json.dumps(last_e))
    code2 = quiet(cj.run_stage, rj, cj.Stage(rj, 'visual-record', None), lambda: 1 / 0)
    last_e2 = json.loads((rdir / 'RUN_RECORD.json').read_bytes())['stages'][-1]
    t.check('N12: a runner error is recorded (STOP_RUNNER_ERROR) with its traceback in logs/', lambda: code2 == 3 and last_e2['result'] == 'RUNNER_ERROR'
            and 'ZeroDivisionError' in (rdir / last_e2['outputs']['runner_error_traceback']['path']).read_text(encoding='utf-8'),
            lambda: json.dumps(last_e2.get('outputs')))

    def interrupted():
        rj2 = cj.Job(rdir)
        rj2.load()
        rj2.mark(cj.Stage(rj2, 'deliver-check', None))
        rj3 = cj.Job(rdir)
        rj3.load()
        cj.reconcile(rj3)
        s = rj3.rec['stages'][-1]
        return s['stage'] == 'deliver-check' and s['result'] == 'INTERRUPTED' and s['completed'] and not (rdir / '.STAGE_IN_PROGRESS.json').exists()
    t.check('R4: a stage marker without its entry is recorded INTERRUPTED (completed) by the next command, and the marker removed', interrupted)
    holder = []

    def second_lock():
        lk = cj.Job(rdir)
        lk.lock()
        holder.append(lk)
        return refusal(cj.Job(rdir).lock) == 'JOB_BUSY'
    t.check('R4: a second lock on the same job folder is refused JOB_BUSY', second_lock)

    def lock_free():
        os.close(holder[0].lock_fd)
        lk = cj.Job(rdir)
        lk.lock()
        os.close(lk.lock_fd)
        return True
    t.check('R4: the lock is free again once its holder ends', lock_free)


def test_units_release(t):
    """R10 (repository commit and clean tree; the runner's own checkout; the package the harness loads) and N10."""
    cj = load_runner()
    u = t.work / 'unit_release'
    g = u / 'git_repo'
    g.mkdir(parents=True)
    gitc = ['git', '-C', str(g), '-c', 'user.email=invented@example.invalid', '-c', 'user.name=invented']
    subprocess.run(gitc + ['init', '-q'], check=True, capture_output=True)
    (g / 'f.txt').write_text('invented\n', encoding='utf-8')
    subprocess.run(gitc + ['add', 'f.txt'], check=True, capture_output=True)
    subprocess.run(gitc + ['commit', '-q', '-m', 'invented'], check=True, capture_output=True)
    head = subprocess.run(['git', '-C', str(g), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    t.check('R10: a clean checkout at the release commit passes', lambda: refusal(cj.check_repository, g, head) is None)
    (g / 'f.txt').write_text('invented, changed\n', encoding='utf-8')
    t.check('R10: a dirty tracked tree is refused REPOSITORY_DIRTY', lambda: refusal(cj.check_repository, g, head) == 'REPOSITORY_DIRTY')
    t.check('R10: a release without a commit is refused RELEASE_COMMIT_REQUIRED', lambda: refusal(cj.check_repository, g, None) == 'RELEASE_COMMIT_REQUIRED')
    ng = u / 'not_git'
    ng.mkdir()
    t.check('R10: a folder that is not a git checkout is refused REPOSITORY_NOT_VERIFIABLE',
            lambda: refusal(cj.check_repository, ng, head) == 'REPOSITORY_NOT_VERIFIABLE')
    (g / 'sub').mkdir()
    t.check('R10: a folder inside a checkout but not its top is refused REPOSITORY_NOT_VERIFIABLE',
            lambda: refusal(cj.check_repository, g / 'sub', head) == 'REPOSITORY_NOT_VERIFIABLE')
    rel_d = json.loads(t.release_path.read_text(encoding='utf-8'))
    other_root = dict(rel_d, repository=dict(rel_d['repository'], root=str(g)))
    st = cj.Stage(cj.Job(u / '_'), 'prepare', None)
    t.check('R10: a running cps_job.py that is not repository.root/deploy/run/cps_job.py is refused',
            lambda: refusal(cj.check_release_static, cj.Release(cj.dumps(other_root), 'x'), False, st) == 'RUNNER_NOT_IN_RELEASED_REPOSITORY')
    pkg_copy = u / 'package_copy'
    shutil.copytree(PKG, pkg_copy)
    moved = dict(rel_d, package=dict(rel_d['package'], path=str(pkg_copy)))
    t.check('R10: a package.path that is not the folder the harness loads (<harness>/../package) is refused',
            lambda: refusal(cj.check_release_static, cj.Release(cj.dumps(moved), 'x'), False, st) == 'HARNESS_PACKAGE_MISMATCH')
    t.check('R10 (guard): the test release itself passes every static check',
            lambda: refusal(cj.check_release_static, cj.Release(t.release_path.read_bytes(), 'x'), False, st) is None)
    pyd = u / 'pyc' / 'tools' / '__pycache__'
    pyd.mkdir(parents=True)
    (pyd / 'invented.cpython-313.pyc').write_bytes(b'invented')
    t.check('N10: cached bytecode beside pinned sources is found (refused PYCACHE_PRESENT), and tools run with -X pycache_prefix',
            lambda: len(cj.pycache_entries([u / 'pyc'])) == 2 and '-X' in cj.py('-I') and cj.py('-I')[-1].startswith('pycache_prefix='))


def test_units_misc(t):
    """R13 (generation record shape), R11 (ledger chain), N1, N6, N7 and N14 on invented records."""
    cj = load_runner()
    u = t.work / 'unit_misc'
    u.mkdir()
    g0 = {'schema': 'cps.generation-record.v1', 'case_id': '9990009', 'reader': 'A', 'platform': 'p', 'model': 'm', 'effort': 'e',
          'conversation_id': 'c', 'started_utc': '2026-01-01T00:00:00Z', 'ended_utc': '2026-01-01T00:10:00Z', 'prompt_sha256': '4' * 64,
          'single_user_message': True, 'features': {k: False for k in FEATURES}, 'tools_enabled': [], 'final_message': '',
          'transcript_status': 'exported', 'transcript_sha256': '5' * 64}
    t.check('R13: a complete record with transcript_status exported and its sha256 has no problem',
            lambda: cj.generation_record_problems(g0, '9990009', 'A') == [])
    t.check('R13: exported without a transcript sha256, not_available without a reason, an unknown key and an unknown status are problems',
            lambda: all(cj.generation_record_problems(x, '9990009', 'A') for x in (
                dict(g0, transcript_sha256=None), dict(g0, transcript_status='not_available', transcript_sha256=None),
                dict(g0, invented_key=1), dict(g0, transcript_status='attested'))))
    lp = u / 'LEDGER_unit.jsonl'

    def ledger_ok():
        with cj.Ledger(lp) as led:
            led.append({'type': 'nonattempt', 'case_id': '9990009', 'reader': 'A'})
            led.append({'type': 'nonattempt', 'case_id': '9990009', 'reader': 'B'})
        return refusal(lambda: cj.Ledger(lp).__enter__().__exit__()) is None
    t.check('R11: the ledger the runner appended verifies', ledger_ok)

    def ledger_edit(old, new):
        keep = lp.read_bytes()
        lp.write_bytes(keep.replace(old, new))
        try:
            return refusal(lambda: cj.Ledger(lp).__enter__()) == 'QUALIFICATION_LEDGER_CHAIN_BROKEN'
        finally:
            lp.write_bytes(keep)
    t.check('R11: an edited ledger line is refused QUALIFICATION_LEDGER_CHAIN_BROKEN', lambda: ledger_edit(b'"reader":"A"', b'"reader":"C"'))
    t.check('R11: an edit of the last ledger line is refused too (entry_sha256)', lambda: ledger_edit(b'"reader":"B"', b'"reader":"C"'))
    t.check('N1: a scoped inventory the route rejects fails even when --verify says PASS',
            lambda: cj.scoped_route_status({'route_check_inventory': {'status': 'PASS'}}, {'status': 'PASS', 'route_check_inventory': {'status': 'PASS'}})['pass'] is True
            and cj.scoped_route_status({'route_check_inventory': {'status': 'REJECTED', 'violations': ['R59_SCOPE_FACT_MISMATCH']}},
                                       {'status': 'PASS', 'route_check_inventory': {'status': 'REJECTED'}})['pass'] is False)
    rel = cj.Release(t.release_path.read_bytes(), 'x')

    def title_refused(case, title):
        job = {'schema': 'cps.job-config.v2', 'case_id': case, 'source_path': str(t.paths['src']), 'source_kind': '材料清單',
               'glossary_path': str(t.paths['glossary']), 'company_name': COMPANY}
        tr = {'schema': 'cps.job-title.v1', 'case_id': case, 'job_title': title}
        return refusal(cj.job_inputs, cj.dumps(job), cj.dumps(tr), rel, False, None)
    t.check('N6: titles with U+202E or U+200B, or whose digit run differs from the case id, are refused at prepare (job_inputs)',
            lambda: title_refused('9990009', '9990009示例‮案') == 'JOB_TITLE_FORMAT_CHARACTER'
            and title_refused('9990009', '9990009示​例') == 'JOB_TITLE_FORMAT_CHARACTER'
            and title_refused('9990009', '99900091示例案') == 'JOB_TITLE_INVALID'
            and title_refused('999000', '9990009示例案') == 'JOB_TITLE_INVALID')
    t.check('N6 (guard): a title that starts with exactly the case id is accepted', lambda: title_refused('9990009', '9990009示例-案') is None)
    name = '9990009示例(未填).xlsx'
    t.check('N7: the delivered name must be bare, the titled name and not the internal workbook',
            lambda: all(cj.delivery_name_checks(name, sha(name.encode('utf-8')), 'INTERNAL_QA_WORKBOOK.xlsx').values())
            and not cj.delivery_name_checks('../' + name, sha(name.encode('utf-8')), 'INTERNAL_QA_WORKBOOK.xlsx')['file_name_bare']
            and not cj.delivery_name_checks('INTERNAL_QA_WORKBOOK.xlsx', sha(name.encode('utf-8')), 'INTERNAL_QA_WORKBOOK.xlsx')['file_name_not_internal_workbook'])
    facts = {'source_sha256': '6' * 64, 'job_json_sha256': '7' * 64, 'tables_sha256': {'glossary': '8' * 64}}
    cfg = {'original': {'sha256': '6' * 64}, 'job_config_sha256': '7' * 64, 'resource_files_sha256': {'glossary': '8' * 64, 'brand_table': None}}
    t.check('N14: the builder config must name the pinned source, job file and tables', lambda: cj.builder_config_problems(cfg, facts) == []
            and cj.builder_config_problems(dict(cfg, original={'sha256': '9' * 64}), facts) == ['BUILDER_CONFIG_SOURCE_SHA256'])


def interrupt(t, jd, reason='TECHNICAL_CONVERSATION_BROKE', started=None, ended=None, conv='invented-broken-conversation'):
    """The operator records that the scope reader or generator conversation broke (invented times: just now)."""
    now = utc_now()
    extra = ['--conversation-id', conv] if conv is not None else []
    return t.runner('interrupt', '--job-dir', jd, '--reason', reason, '--started-utc', started or now, '--ended-utc', ended or now,
                    *extra, '--operator-model', 'test-harness')


def safe(fn, default=None):
    try:
        return fn()
    except Exception:                                       # noqa: BLE001 - a missing file on an older runner
        return default


def test_delta_qualification(t):
    """The delta review's D1 (protocol rule 3: a recorded technical interruption after NEXT: GENERATE or SCOPE_READER,
    and one restart), D3 (O40: exported needs the transcript file), DN1 (the scope reader prompt), DN5 (a ledger two
    entries behind) and DN6 (no implicit ledger), on invented qualification jobs 9990040-9990042 and their own ledger."""
    L = t.work / 'qualification' / 'LEDGER_delta.jsonl'
    cases = {c: job_files(t, c, source=t.paths['large'] if c == '9990041' else None) for c in ('9990040', '9990041', '9990042')}
    adms = {c: admission(t, c, *cases[c]) for c in cases}
    rq = qual_release(t, 'RELEASE_QUAL_DELTA.json', list(adms.values()), L)
    led = lambda: ledger(L)                                 # noqa: E731
    # D1 on a real job: interrupt is for qualification jobs only
    real = t.work / 'jobs' / '9990022'                      # prepared at NEXT: GENERATE by test_stage_output_exists
    code, _, last = interrupt(t, real)
    t.check('D1: interrupt on a real job is refused INTERRUPT_QUALIFICATION_ONLY, not recorded as completed', lambda: code == 4
            and last == 'REFUSED: INTERRUPT_QUALIFICATION_ONLY' and not stages(real, 'interrupt')[-1]['completed'], last)
    # ---- 9990040: the generator conversation broke after NEXT: GENERATE
    case = '9990040'
    code, _, last = qprepare(t, rq, *cases[case], 'qd_A', 'A', adms[case])
    jd = t.work / 'qd_A' / case
    t.check('qualification prepare of 9990040 (the D1 and D3 scenario): NEXT: GENERATE', lambda: code == 0 and last.startswith('NEXT: GENERATE'), last)
    resp = safe(lambda: stand_in_response(t, jd, case))
    tx = t.work / 'invented_transcript_9990040.txt'
    tx.write_text('invented transcript bytes of an invented conversation\n', encoding='utf-8')
    g = safe(lambda: generation_record(jd, case, transcript_status='exported', transcript_sha256=sha_file(tx),
                                       transcript_not_available_reason=None))
    if g is not None:
        gd = json.loads(g.read_text(encoding='utf-8'))
        gd.pop('transcript_not_available_reason', None)
        force_write(g, json.dumps(gd, ensure_ascii=False, indent=1) + '\n')
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--generator-model', 'stand-in (invented test)',
                             '--generation-record', g)
    t.check('D3: a qualification finish whose record says exported without --transcript is refused TRANSCRIPT_REQUIRED, nothing consumed',
            lambda: code == 4 and last == 'REFUSED: TRANSCRIPT_REQUIRED' and not (jd / 'response' / 'response.json').exists()
            and not (jd / 'response' / 'GENERATION_RECORD.json').exists() and not stages(jd, 'finish')[-1]['completed'], last)
    safe(lambda: resp.unlink())                             # the broken conversation wrote no response
    code, _, last = interrupt(t, jd, reason='CONVERSATION_BROKE')
    t.check('D1: interrupt with a reason that is not TECHNICAL_<CODE> is refused INTERRUPT_REASON', lambda: code == 4
            and last == 'REFUSED: INTERRUPT_REASON', last)
    code, _, last = interrupt(t, jd, conv='<the broken conversation id>')
    t.check('D1/DN14: interrupt with a template placeholder as the conversation id is refused INTERRUPT_CONVERSATION_ID',
            lambda: code == 4 and last == 'REFUSED: INTERRUPT_CONVERSATION_ID', last)
    code, _, last = interrupt(t, jd, started='2020-01-01T00:00:00Z', ended='2020-01-01T00:10:00Z')
    t.check('D1: interrupt with times before the stage that printed NEXT: GENERATE ended is refused INTERRUPTION_TIMES, nothing consumed',
            lambda: code == 4 and last == 'REFUSED: INTERRUPTION_TIMES' and not any(s['completed'] for s in stages(jd, 'interrupt')), last)
    code, out, last = interrupt(t, jd)
    it = safe(lambda: [s for s in stages(jd, 'interrupt') if s['completed']][-1], {})
    t.check('D1: interrupt after NEXT: GENERATE records a completed TECHNICAL_INTERRUPTION (NEXT: STOP_TECHNICAL_INTERRUPTION, exit 3) '
            'with the attested conversation id and times, mirrored in the ledger',
            lambda: code == 3 and last == 'NEXT: STOP_TECHNICAL_INTERRUPTION' and it['result'] == 'TECHNICAL_INTERRUPTION'
            and it['codes'] == ['TECHNICAL_CONVERSATION_BROKE'] and it['facts']['interruption']['conversation_role'] == 'generator'
            and it['facts']['interruption']['conversation_id_attested_by_operator'] == 'invented-broken-conversation'
            and it['facts']['interruption']['times_within_bounds'] is True and it['facts']['interruption']['response_file_present'] is False
            and any(e['type'] == 'record' and e['job_dir'] == str(jd) and e['stage'] == 'interrupt' and e['completed']
                    and e['next'] == 'STOP_TECHNICAL_INTERRUPTION' and e['run_record_sha256'] == sha_file(jd / 'RUN_RECORD.json') for e in led()),
            lambda: last + json.dumps(it.get('facts')))
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', jd / 'run' / 'A' / 'output' / 'response.json',
                             '--generator-model', 'stand-in (invented test)', '--generation-record', g, '--transcript', tx)
    code2, _, last2 = interrupt(t, jd)
    t.check('D1: after the interruption finish is refused JOB_INTERRUPTED and a second interrupt STAGE_ALREADY_COMPLETED, nothing consumed',
            lambda: code == 4 and last == 'REFUSED: JOB_INTERRUPTED' and code2 == 4 and last2 == 'REFUSED: STAGE_ALREADY_COMPLETED'
            and not (jd / 'response' / 'response.json').exists(), lambda: f'{last} / {last2}')
    code, _, last = t.runner('freeze', '--job-dir', jd)
    fz = safe(lambda: stages(jd, 'freeze')[-1], {})
    t.check('D1: the interrupted run freezes, its final stage the interruption', lambda: code == 0 and last == 'NEXT: DONE'
            and fz['facts']['final_stage'] == {'stage': 'interrupt', 'result': 'TECHNICAL_INTERRUPTION'}, last)
    code, _, last = qprepare(t, rq, *cases[case], 'qd_A_restart1', 'A', adms[case])
    jd2 = t.work / 'qd_A_restart1' / case
    t.check('D1: after freeze one restart of the interrupted case and reader is allowed (restart_of in the record and the ledger), NEXT: GENERATE',
            lambda: code == 0 and last.startswith('NEXT: GENERATE') and record(jd2)['restart_of'] == str(jd)
            and any(e['type'] == 'prepare' and e['job_dir'] == str(jd2) and e['restart_of'] == str(jd) for e in led()), last)
    code, _, last = interrupt(t, jd2)
    t.check('R3-limit: interrupt in a folder that is itself a restart (restart_of) is refused INTERRUPT_RESTART_USED, nothing consumed',
            lambda: code == 4 and last == 'REFUSED: INTERRUPT_RESTART_USED' and not any(s['completed'] for s in stages(jd2, 'interrupt')), last)
    code, _, last = t.runner('freeze', '--job-dir', jd2)
    code, _, last = qprepare(t, rq, *cases[case], 'qd_A_restart2', 'A', adms[case])
    t.check('D1: a second restart, after the restarted run was frozen as a failed run, is refused QUALIFICATION_RESTART_USED', lambda: code == 4
            and last == 'REFUSED: QUALIFICATION_RESTART_USED' and not (t.work / 'qd_A_restart2' / case).exists(), last)
    # ---- 9990041: the scope reader conversation broke after NEXT: SCOPE_READER
    case = '9990041'
    code, _, last = qprepare(t, rq, *cases[case], 'qd_A', 'A', adms[case])
    jd = t.work / 'qd_A' / case
    t.check('qualification prepare of the large 9990041 (the D1 and DN1 scenario): NEXT: SCOPE_READER', lambda: code == 0 and last.startswith('NEXT: SCOPE_READER'), last)
    rr = safe(lambda: scope_reader_response(jd, case, end=t.large_end_row))
    prompt_sha = safe(lambda: sha_file(jd / 'scope' / 'SCOPE_READER_PROMPT.md'))
    code, _, last = t.runner('scope-finish', '--job-dir', jd, '--reader-response', rr, '--operator-model', 'test-harness')
    code2, _, last2 = t.runner('scope-finish', '--job-dir', jd, '--reader-response', rr, '--reader-prompt-sha256', '9' * 64)
    t.check('DN1: qualification scope-finish without --reader-prompt-sha256 is refused READER_PROMPT_SHA256_REQUIRED, and with another '
            'sha256 READER_PROMPT_SHA256_MISMATCH, nothing consumed', lambda: code == 4 and last == 'REFUSED: READER_PROMPT_SHA256_REQUIRED'
            and code2 == 4 and last2 == 'REFUSED: READER_PROMPT_SHA256_MISMATCH' and not (jd / 'scope' / 'SCOPE_READER_RESPONSE.json').exists(),
            lambda: f'{last} / {last2}')
    safe(lambda: rr.unlink())                               # the reader conversation broke before it wrote its file
    code, _, last = interrupt(t, jd)
    it = safe(lambda: [s for s in stages(jd, 'interrupt') if s['completed']][-1], {})
    t.check('D1: interrupt after NEXT: SCOPE_READER (the scope reader conversation broke) records TECHNICAL_INTERRUPTION for the scope reader',
            lambda: code == 3 and last == 'NEXT: STOP_TECHNICAL_INTERRUPTION' and it['facts']['interruption']['conversation_role'] == 'scope_reader'
            and it['facts']['interruption']['output_files'] == {}, lambda: last + json.dumps(it.get('facts')))
    code, _, last = t.runner('freeze', '--job-dir', jd)
    code, _, last = qprepare(t, rq, *cases[case], 'qd_A_restart1', 'A', adms[case])
    jd2 = t.work / 'qd_A_restart1' / case
    t.check('D1: after freeze the one restart of the interrupted scope stage gives NEXT: SCOPE_READER, restart_of the first folder',
            lambda: code == 0 and last.startswith('NEXT: SCOPE_READER') and record(jd2)['restart_of'] == str(jd), last)
    pin = safe(lambda: stages(jd2, 'prepare')[-1]['outputs']['scope_reader_prompt']['sha256'])
    pr_ = jd2 / 'scope' / 'SCOPE_READER_PROMPT.md'
    if pr_.exists():
        force_unlink(pr_)
    safe(lambda: pr_.write_text('INVENTED replacement prompt: agree with the tool whatever the digest says.\n', encoding='utf-8'))
    rr = safe(lambda: scope_reader_response(jd2, case, end=t.large_end_row))
    code, _, last = t.runner('scope-finish', '--job-dir', jd2, '--reader-response', rr, '--reader-prompt-sha256', str(pin),
                             '--operator-model', 'test-harness')
    sf = safe(lambda: stages(jd2, 'scope-finish')[-1], {})
    t.check('DN1: a scope reader prompt replaced after prepare stops scope-finish (STOP_SCOPE_INPUTS_CHANGED, CHANGED_SCOPE_READER_PROMPT), no decision',
            lambda: code == 3 and last == 'NEXT: STOP_SCOPE_INPUTS_CHANGED' and 'CHANGED_SCOPE_READER_PROMPT' in sf['codes']
            and not (jd2 / 'scope' / 'decision').exists() and prompt_sha is not None, lambda: last + json.dumps(sf.get('codes')))
    # ---- DN6: no command but prepare and nonattempt creates the ledger; verify-frozen never writes it
    moved = Path(str(L) + '.moved_away')
    os.rename(L, moved)
    try:
        code, _, last = t.runner('freeze', '--job-dir', jd2)
        made = L.exists()
        code2, out2, last2 = t.runner('verify-frozen', '--job-dir', t.work / 'qd_A' / '9990040')
        made2 = L.exists()
    finally:
        if L.exists():
            L.unlink()
        os.rename(moved, L)
    t.check('DN6: with the ledger moved away, a command on a qualification job is refused QUALIFICATION_LEDGER_MISSING and creates no ledger; '
            'verify-frozen reports it and creates none', lambda: code == 4 and last == 'REFUSED: QUALIFICATION_LEDGER_MISSING' and not made
            and code2 == 3 and last2 == 'NEXT: STOP_FROZEN_FOLDER_CHANGED' and last_json(out2).get('record_chain') == 'QUALIFICATION_LEDGER_MISSING'
            and not made2, lambda: f'{last} / {last2} / {made} {made2}')
    code, _, last = t.runner('freeze', '--job-dir', jd2)
    t.check('DN6 (guard): with the ledger back, the stopped scope run freezes', lambda: code == 0 and last == 'NEXT: DONE', last)
    # ---- 9990042: D1 refused when a response is frozen; DN5 a ledger two entries behind; D1 guard
    case = '9990042'
    code, _, last = qprepare(t, rq, *cases[case], 'qd_A', 'A', adms[case])
    jd = t.work / 'qd_A' / case
    planted = jd / 'response' / 'response.json'
    planted.write_text('{"invented": "a frozen response"}\n', encoding='utf-8')
    code, _, last = interrupt(t, jd)
    planted.unlink()
    t.check('D1: interrupt is refused INTERRUPT_NOT_ALLOWED when a generator response is frozen (response/response.json present)',
            lambda: code == 4 and last == 'REFUSED: INTERRUPT_NOT_ALLOWED', last)
    for _ in range(2):
        t.runner('visual-record', '--job-dir', jd, '--review', jd / 'qa' / 'visual_review' / 'VISUAL_REVIEW.json')
    raw = L.read_bytes()
    lines = raw.split(b'\n')[:-1]
    tail = [json.loads(x) for x in lines[-2:]]
    two_records = all(e['type'] == 'record' and e['job_dir'] == str(jd) for e in tail) and len(tail) == 2
    L.write_bytes(b''.join(x + b'\n' for x in lines[:-2]))   # two ledger writes lost (the record is two entries ahead)
    code, out, last = t.runner('freeze', '--job-dir', jd)
    caught = [e for e in ledger(L) if e['type'] == 'record' and e['job_dir'] == str(jd) and e['seq'] in (tail[0]['seq'], tail[1]['seq'])]
    t.check('DN5: a qualification record two entries ahead of the ledger is caught up entry by entry (each with the sha256 of the record '
            'after that entry), and freeze proceeds', lambda: two_records and code == 0 and last == 'NEXT: DONE'
            and [(e['seq'], e['run_record_sha256']) for e in caught] == [(x['seq'], x['run_record_sha256']) for x in tail], last)
    code, _, last = t.runner('verify-frozen', '--job-dir', jd)
    t.check('DN5 (guard): verify-frozen after the catch-up: NEXT: DONE', lambda: code == 0 and last == 'NEXT: DONE', last)
    code, _, last = qprepare(t, rq, *cases[case], 'qd_A_restart1', 'A', adms[case])
    t.check('D1 (guard): a run frozen at NEXT: GENERATE without a recorded interruption is a failed run, never restarted '
            '(QUALIFICATION_RESTART_NOT_ALLOWED)', lambda: code == 4 and last == 'REFUSED: QUALIFICATION_RESTART_NOT_ALLOWED', last)


def fake_ledger(cj, path, entries):
    led = cj.Ledger(path)
    led.entries = entries
    return led


def test_units_delta(t):
    """Units of the delta review's D1 (the restart rule), D3 (the generation record facts, the release field), DN2, DN3,
    DN4, DN10 and DN14, on invented ledgers, folders, records and reviews."""
    cj = load_runner()
    u = t.work / 'unit_delta'
    u.mkdir()

    def prev(name, records, files, ledger_sha=None):
        d = u / name
        d.mkdir()
        fz = cj.dumps({'schema': 'cps.job-frozen.v2', 'files': [{'path': f, 'bytes': 1, 'sha256': '0' * 64} for f in files]})
        (d / 'FROZEN.json').write_bytes(fz)
        es = [{'type': 'record', 'job_dir': str(d), 'stage': st_, 'next': nx, 'completed': c} for st_, nx, c in records]
        es.append({'type': 'freeze', 'job_dir': str(d), 'frozen_sha256': ledger_sha or sha(fz)})
        return str(d), es

    cases = {
        'interrupt': ([('prepare', 'GENERATE', True), ('finish', None, False), ('interrupt', 'STOP_TECHNICAL_INTERRUPTION', True),
                       ('freeze', 'DONE', True)], ['RUN_RECORD.json', 'run/A/output/scratch/x'], None, True),
        'killed_finish': ([('prepare', 'GENERATE', True), ('finish', 'STOP_INTERRUPTED', True), ('freeze', 'DONE', True)], [], None, True),
        'prepare_stop': ([('prepare', 'STOP_RENDER_VIEWS_FAILED', True), ('freeze', 'DONE', True)], [], None, True),
        'scope_interrupt': ([('prepare', 'SCOPE_READER', True), ('interrupt', 'STOP_TECHNICAL_INTERRUPTION', True), ('freeze', 'DONE', True)],
                            ['scope/reader/output/partial.json'], None, True),
        'frozen_at_generate': ([('prepare', 'GENERATE', True), ('freeze', 'DONE', True)], [], None, False),
        'response_frozen': ([('prepare', 'GENERATE', True), ('freeze_response', 'FINISH', True), ('finish', 'STOP_ROUTE_CHECK_FAILED', True),
                             ('freeze', 'DONE', True)], ['response/response.json'], None, False),
        'owner_decision': ([('prepare', 'OWNER_DECISION', True), ('freeze', 'DONE', True)], [], None, False),
        'reader_response_frozen': ([('prepare', 'SCOPE_READER', True), ('scope-finish', 'STOP_SCOPE_INPUTS_CHANGED', True), ('freeze', 'DONE', True)],
                                   ['scope/SCOPE_READER_RESPONSE.json'], None, False),
        'frozen_json_not_the_ledgers': ([('prepare', 'GENERATE', True), ('interrupt', 'STOP_TECHNICAL_INTERRUPTION', True), ('freeze', 'DONE', True)],
                                        [], 'f' * 64, False),
    }
    got = {}
    for name, (recs, files, lsha, want) in cases.items():
        d, es = prev(name, recs, files, lsha)
        got[name] = (safe(lambda: cj.restart_problem(fake_ledger(cj, u / 'L.jsonl', es), d), 'raised') is None) == want
    t.check('D1: the restart rule: a recorded interruption, an INTERRUPTED stage or a technical stop before any response is restartable; '
            'a run frozen at GENERATE, a frozen response, OWNER_DECISION, a frozen reader response or a FROZEN.json the ledger did not record is not',
            lambda: all(got.values()), lambda: json.dumps(got))
    # D3: the generation record facts follow the frozen file; O40 stated; the qualification release field
    jd = cj.Job(u / 'job')
    (u / 'job' / 'run').mkdir(parents=True)
    prompt_sha = '4' * 64
    lo = utc_now()
    tx = u / 'TRANSCRIPT.txt'
    tx.write_text('invented transcript\n', encoding='utf-8')
    g = {'schema': 'cps.generation-record.v1', 'case_id': '9990009', 'reader': 'A', 'platform': 'p', 'model': 'm', 'effort': 'e',
         'conversation_id': 'c', 'started_utc': utc_now(), 'ended_utc': utc_now(), 'prompt_sha256': prompt_sha, 'single_user_message': True,
         'features': {k: False for k in FEATURES}, 'tools_enabled': [], 'final_message': '', 'transcript_status': 'exported',
         'transcript_sha256': sha_file(tx)}
    gp = u / 'job' / 'run' / 'GENERATION_RECORD.json'
    gp.write_text(json.dumps(g), encoding='utf-8')
    time.sleep(0.01)
    gen = {'outputs': {'generator_prompt': {'sha256': prompt_sha}}, 'ended_utc': lo}

    def gr(qual, transcript):
        jd.rec = {'qualification': qual, 'case_id': '9990009', 'reader': 'A', 'stages': []}
        st = cj.Stage(jd, 'finish', None)
        a = argparse.Namespace(generator_model='m', generation_record=str(gp), transcript=str(transcript) if transcript else None)
        rel = argparse.Namespace(accepted_transcripts=['exported', 'not_available'])
        try:
            return cj.check_generation_record(st, jd, a, gen, rel)['facts']
        except Exception as e:                              # noqa: BLE001
            return getattr(e, 'code', type(e).__name__)
    f1, f2, f3 = gr(False, None), gr(False, tx), gr(True, None)
    t.check('D3: isolation_evidence follows the frozen transcript file, not the claim, and every record states the O40 rule, not an open owner decision',
            lambda: f1['isolation_evidence'] == 'attested_not_audited' and f1['transcript_claimed_but_not_frozen'] is True
            and f1['transcript_file_frozen'] is False and f2['isolation_evidence'] == 'transcript_exported' and f2['transcript_file_frozen'] is True
            and f1['qualification_transcript_rule'] == f2['qualification_transcript_rule'] == cj.O40_RULE
            and 'owner_decision_open' not in f1 and 'owner_decision_open' not in f2, lambda: json.dumps([f1, f2], default=str))
    t.check('D3: a qualification record that says exported without --transcript is refused TRANSCRIPT_REQUIRED (unit)', lambda: f3 == 'TRANSCRIPT_REQUIRED',
            lambda: json.dumps(f3, default=str))
    rel_d = json.loads(t.release_path.read_text(encoding='utf-8'))
    q = {'admissions': [], 'ledger': str(u / 'L.jsonl'), 'jobs_file': str(t.jobs_path)}

    def rel_fields(acc):
        qq = dict(q) if acc == 'absent' else dict(q, accepted_transcript_status=acc)
        return refusal(cj.Release(cj.dumps(dict(rel_d, qualification=qq)), 'x').require_qualification_fields)
    t.check('D3: a qualification release whose accepted_transcript_status is not exactly both statuses is refused QUALIFICATION_RELEASE_FIELDS; '
            'both, or the field absent, pass', lambda: rel_fields(['exported']) == rel_fields(['not_available']) == rel_fields(['exported', 'exported'])
            == 'QUALIFICATION_RELEASE_FIELDS' and rel_fields(['exported', 'not_available']) is None and rel_fields(['not_available', 'exported']) is None
            and rel_fields('absent') is None)
    # DN2: an unexpected error before anything is consumed is a refusal, not a completed stop
    rdir = u / 'record'
    (rdir / 'logs').mkdir(parents=True)
    rj = cj.Job(rdir)
    rj.create({'schema': cj.RECORD_SCHEMA, 'case_id': '9990009', 'reader': 'A', 'qualification': False, 'stages': []})

    def unreadable():
        raise PermissionError(13, 'invented: the reader file is unreadable')
    code = quiet(cj.run_stage, rj, cj.Stage(rj, 'scope-finish', None), lambda: ('INVENTED', 'DONE'), preflight=unreadable)
    e1 = safe(lambda: json.loads((rdir / 'RUN_RECORD.json').read_bytes())['stages'][-1], {})
    code2 = quiet(cj.run_stage, rj, cj.Stage(rj, 'scope-finish', None), lambda: ('INVENTED', 'DONE'), preflight=lambda: None)
    e2 = safe(lambda: json.loads((rdir / 'RUN_RECORD.json').read_bytes())['stages'][-1], {})
    t.check('DN2: an unexpected error before a stage consumes anything is a not-completed refusal (REFUSED: RUNNER_ERROR, exit 4, traceback '
            'kept), and the stage can run again', lambda: code == 4 and e1['completed'] is False and e1['result'] == 'REFUSED'
            and e1['codes'][:2] == ['RUNNER_ERROR', 'PermissionError']
            and 'PermissionError' in (rdir / e1['outputs']['runner_error_traceback']['path']).read_text(encoding='utf-8')
            and code2 == 0 and e2['completed'] is True and e2['stage'] == 'scope-finish', lambda: json.dumps([e1, e2])[:600])
    # DN3: the lock is the folder itself
    ldir = u / 'lock'
    ldir.mkdir()
    holder = cj.Job(ldir)
    holder.lock()
    had_file = os.path.lexists(ldir / '.cps_job.lock')
    if had_file:
        os.unlink(ldir / '.cps_job.lock')                   # the reviewer's R4l: the lock file deleted while finish runs
    second = refusal(cj.Job(ldir).lock)
    os.close(holder.lock_fd)
    t.check('DN3: the job lock is a lock on the folder itself (no lock file to delete): a second command is refused JOB_BUSY',
            lambda: not had_file and second == 'JOB_BUSY', lambda: f'lock file: {had_file}, second lock: {second}')
    # DN4: a tool a stage started keeps the folder locked after the runner's own descriptor is gone
    tdir = u / 'tool'
    (tdir / 'logs').mkdir(parents=True)
    tool = u / 'invented_tool.py'
    tool.write_text('import pathlib, sys, time\npathlib.Path(sys.argv[1]).write_text("started")\ntime.sleep(float(sys.argv[2]))\n', encoding='utf-8')
    tj = cj.Job(tdir)
    tj.lock()
    tj.rec = {'stages': []}
    started = tdir / 'started.txt'
    th = threading.Thread(target=lambda: cj.Stage(tj, 'finish', None).run('invented_tool', tool, [started, 4]))
    th.start()
    wait_for(lambda: started.exists(), timeout=60)
    os.close(tj.lock_fd)                                    # the runner is gone; only the tool still runs
    while_tool = refusal(cj.Job(tdir).lock)
    th.join(timeout=120)
    after = cj.Job(tdir)
    after_tool = refusal(after.lock)
    if after.lock_fd is not None:
        os.close(after.lock_fd)
    t.check('DN4: a tool started by a stage holds the job lock: after the runner\'s own descriptor is closed the folder stays locked '
            '(JOB_BUSY) until the tool ends', lambda: started.exists() and while_tool == 'JOB_BUSY' and after_tool is None,
            lambda: f'{while_tool} / {after_tool}')
    # DN10: line and paragraph separators, fullwidth case-id digits
    rel = cj.Release(t.release_path.read_bytes(), 'x')

    def title_refused(case, title):
        job = {'schema': 'cps.job-config.v2', 'case_id': case, 'source_path': str(t.paths['src']), 'source_kind': '材料清單',
               'glossary_path': str(t.paths['glossary']), 'company_name': COMPANY}
        tr = {'schema': 'cps.job-title.v1', 'case_id': case, 'job_title': title}
        return refusal(cj.job_inputs, cj.dumps(job), cj.dumps(tr), rel, False, None)
    t.check('DN10: titles with U+2028 or U+2029, or whose case id is in fullwidth digits, are refused at prepare (job_inputs)',
            lambda: title_refused('9990009', '9990009示例 案') == 'JOB_TITLE_FORMAT_CHARACTER'
            and title_refused('9990009', '9990009示例 案') == 'JOB_TITLE_FORMAT_CHARACTER'
            and title_refused('9990009', '９９９０００９示例案') == 'JOB_TITLE_INVALID'
            and title_refused('9990009', '9990009示例 案') is None)
    # DN14: template placeholders
    pages, rv = unit_review(cj, u / 'review', reviewer={'kind': 'fresh_context_visual_reviewer', 'model': 'm', 'effort': 'e',
                                                        'conversation_id': '<only if your platform shows it>'})
    _, rv2 = unit_review(cj, u / 'review2', reviewer={'kind': 'fresh_context_visual_reviewer', 'model': '<your observed model id>',
                                                      'effort': 'e', 'conversation_id': 'c'})
    g2 = dict(g, conversation_id='<the conversation id or share link>')
    t.check('DN14: a template placeholder (<...>) as the reviewer conversation id or model, or as a generation record field, is a problem',
            lambda: 'reviewer.conversation_id' in cj.check_review(rv, pages)[0] and 'reviewer.model' in cj.check_review(rv2, pages)[0]
            and 'conversation_id' in cj.generation_record_problems(g2, '9990009', 'A')
            and cj.generation_record_problems(g, '9990009', 'A') == [], lambda: json.dumps(cj.check_review(rv, pages)))


def test_docs_delta(t):
    """DN11 and DN13 (the command sheet), D1-D3 (the command sheet names the paths) and the visual checklist item 9 (export
    writer v2.8 review N6)."""
    doc = (HERE / 'RUN_JOB_COMMANDS.md').read_text(encoding='utf-8')
    tpl = (HERE / 'VISUAL_REVIEW_PROMPT_TEMPLATE.md').read_text(encoding='utf-8')
    t.check('DN11: RUN_JOB_COMMANDS asks for times to the second, the start rounded up and the end down', lambda: 'to the second' in doc
            and 'round the start up and the end down' in doc)
    t.check('DN13: RUN_JOB_COMMANDS names ~/cps-tools/env.sh and ~/cps-tools/builder-deps, and says never to move or rename a job folder or jobs root',
            lambda: 'source ~/cps-tools/env.sh' in doc and '~/cps-tools/builder-deps' in doc and 'source ~/cps-venv/bin/activate' not in doc
            and 'Never move or rename a job folder, a jobs root or the ledger' in doc)
    t.check('D1/D2/D3: RUN_JOB_COMMANDS describes interrupt and the restart, the frozen nonattempt folder and the O40 rule (no open decision)',
            lambda: '$R interrupt --job-dir' in doc and 'STOP_TECHNICAL_INTERRUPTION' in doc and 'QUALIFICATION_CASE_NOT_NONATTEMPT' in doc
            and '"status": "NONATTEMPT_SOURCE_UNAVAILABLE"' in doc and 'O40' in doc and 'still open' not in doc)
    a = tpl.index('**Delivered workbook checklist')
    b = tpl.index('## B.')
    items = [ln.split('.')[0] for ln in tpl[a:b].splitlines() if ln[:1].isdigit() and ln[1:3] == '. ']
    t.check('Visual checklist (export writer v2.8 review N6): delivered item 9 fails a value cut at a column edge or by a filled neighbour; nine items remain',
            lambda: '9. body text is black and legible, and no value is cut at a column edge or by a filled neighbour (a cut value fails this item);' in tpl[a:b]
            and items == [str(i) for i in range(1, 10)], lambda: json.dumps(items))


def test_int_inplace(t):
    """Protocol rule 3 after scope agreement (the export v2.8.2 integration, item 2): a generator conversation that broke
    after scope-finish froze the reader's response is restarted in place, once: interrupt records the TECHNICAL_INTERRUPTION
    and prints NEXT: GENERATE again in the same folder; a second interrupt is refused; no further restart in a new folder."""
    case = '9990046'
    L = t.work / 'qualification' / 'LEDGER_inplace.jsonl'
    jp, tp = job_files(t, case, source=t.paths['large'])
    adm = admission(t, case, jp, tp)
    rq = qual_release(t, 'RELEASE_QUAL_INPLACE.json', [adm], L)
    code, _, last = qprepare(t, rq, jp, tp, 'qi_A', 'A', adm)
    jd = t.work / 'qi_A' / case
    rr = safe(lambda: scope_reader_response(jd, case, end=t.large_end_row))
    psha = safe(lambda: sha_file(jd / 'scope' / 'SCOPE_READER_PROMPT.md'), '0' * 64)
    code, _, last = t.runner('scope-finish', '--job-dir', jd, '--reader-response', rr, '--reader-prompt-sha256', psha,
                             '--operator-model', 'test-harness')
    gen_last = last
    t.check('qualification prepare and scope-finish of the large 9990046 (the in-place scenario): NEXT: GENERATE after an agreed scope',
            lambda: code == 0 and last.startswith('NEXT: GENERATE') and (jd / 'scope' / 'SCOPE_READER_RESPONSE.json').is_file(), last)
    out_dir = jd / 'run' / 'A' / 'output'
    safe(lambda: (out_dir / 'scratch').mkdir())
    safe(lambda: (out_dir / 'scratch' / 'partial.txt').write_text('invented scratch of the broken conversation\n', encoding='utf-8'))
    resp_w = safe(lambda: stand_in_response(t, jd, case))
    rec_b, led_b = safe(lambda: (jd / 'RUN_RECORD.json').read_bytes()), safe(lambda: L.read_bytes())
    code, _, last = interrupt(t, jd, reason='TECHNICAL_PLATFORM_ERROR')
    t.check('E1: in place, after an agreed scope, interrupt is refused RESPONSE_WRITTEN once the generator wrote response.json; nothing '
            'appended, nothing set aside', lambda: code == 4 and last == 'REFUSED: RESPONSE_WRITTEN'
            and (jd / 'RUN_RECORD.json').read_bytes() == rec_b and L.read_bytes() == led_b and not (jd / 'interrupted').exists(), last)
    safe(lambda: resp_w.unlink())                           # test only: the scenario below is a conversation that wrote no response
    code, out, last = interrupt(t, jd, reason='TECHNICAL_PLATFORM_ERROR')
    it = safe(lambda: [s for s in stages(jd, 'interrupt') if s['completed']][-1], {})
    aside = jd / 'interrupted' / 'generator_output'
    t.check('R3-inplace: after scope-finish froze the reader response, interrupt records TECHNICAL_INTERRUPTION and prints NEXT: GENERATE '
            'again in the same folder (same prompt and folder, exit 0), mirrored in the ledger; the broken conversation\'s output is set '
            'aside read-only and output/ is empty', lambda: code == 0 and last == gen_last and it['result'] == 'TECHNICAL_INTERRUPTION'
            and it['next'] == 'GENERATE' and it['facts']['interruption']['restart'] == 'in_place'
            and it['facts']['interruption']['set_aside']['files'] == {'scratch/partial.txt': sha(b'invented scratch of the broken conversation\n')}
            and (aside / 'scratch' / 'partial.txt').is_file() and not no_write_bits(jd / 'interrupted') and sorted(os.listdir(out_dir)) == []
            and any(e['type'] == 'record' and e['job_dir'] == str(jd) and e['stage'] == 'interrupt' and e['next'] == 'GENERATE'
                    and e['completed'] for e in ledger(L)), lambda: last + json.dumps(it.get('facts', {}).get('interruption'))[:400])
    code, _, last = interrupt(t, jd)
    t.check('R3-limit: a second interrupt in the folder restarted in place is refused INTERRUPT_RESTART_USED, nothing consumed',
            lambda: code == 4 and last == 'REFUSED: INTERRUPT_RESTART_USED' and len([s for s in stages(jd, 'interrupt') if s['completed']]) == 1, last)
    resp = safe(lambda: stand_in_response(t, jd, case))
    sf_end = safe(lambda: stages(jd, 'scope-finish')[-1]['ended_utc'], '2020-01-01T00:00:00.000Z')
    g = safe(lambda: generation_record(jd, case, started_utc=sf_end, ended_utc=it['ended_utc']))
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--generator-model', 'stand-in (invented test)',
                             '--generation-record', g)
    t.check('R3-inplace: a generation record timed before the in-place restart (the broken conversation) is refused '
            'GENERATION_RECORD_TIMES, nothing consumed', lambda: code == 4 and last == 'REFUSED: GENERATION_RECORD_TIMES'
            and not (jd / 'response' / 'response.json').exists(), last)
    g = safe(lambda: generation_record(jd, case))
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--generator-model', 'stand-in (invented test)',
                             '--generation-record', g)
    fr = safe(lambda: stages(jd, 'freeze_response')[-1], {})
    t.check('R3-inplace: finish takes the second generator conversation in the same folder: its record (timed after the interruption) '
            'and its response are frozen, on the pinned scoped run inputs', lambda: code in (0, 3) and fr.get('completed') is True
            and fr['facts']['generation_record']['window_from_stage']['stage'] == 'interrupt' and (jd / 'response' / 'response.json').is_file()
            and stages(jd, 'finish')[-1]['facts']['run_inputs_unchanged'] is True, lambda: last + json.dumps(fr.get('facts'))[:400])
    code, _, last = t.runner('freeze', '--job-dir', jd)
    code, _, last = qprepare(t, rq, jp, tp, 'qi_A_restart1', 'A', adm)
    t.check('R3-limit: after an in-place restart no restart in a new folder is allowed for that case and reader (QUALIFICATION_RESTART_USED), '
            'nothing created', lambda: code == 4 and last == 'REFUSED: QUALIFICATION_RESTART_USED' and not (t.work / 'qi_A_restart1' / case).exists(), last)
    code, _, last = qprepare(t, rq, jp, tp, 'qi_B', 'B', adm)
    t.check('R3-limit (guard): run B may start once run A is frozen and its one restart was used in place', lambda: code == 0
            and last.startswith('NEXT: SCOPE_READER'), last)


def test_units_int(t):
    """Units of the integration items 2 and 3: the restart limit on an invented ledger, the delivered tiles (render problems,
    the legibility bound, R8 on every tile) on invented manifests and files."""
    cj = load_runner()
    u = t.work / 'unit_int'
    u.mkdir()
    d = u / 'prev'
    d.mkdir()
    fz = cj.dumps({'schema': 'cps.job-frozen.v2', 'files': []})
    (d / 'FROZEN.json').write_bytes(fz)
    es = [{'type': 'record', 'job_dir': str(d), 'stage': st_, 'next': nx, 'completed': True, 'utc': '2026-01-02T00:00:00.000Z'}
          for st_, nx in (('prepare', 'SCOPE_READER'), ('scope-finish', 'GENERATE'), ('interrupt', 'GENERATE'), ('finish', 'STOP_INTERRUPTED'))]
    es += [{'type': 'freeze', 'job_dir': str(d), 'frozen_sha256': sha(fz)},
           {'type': 'prepare', 'case_id': '9990009', 'reader': 'A', 'job_dir': str(d), 'utc': '2026-01-02T00:00:00.000Z'}]
    led = fake_ledger(cj, u / 'L.jsonl', es)
    t.check('R3-limit (unit): a run restarted in place is never restarted again: the restart rule refuses it, and prepare is refused '
            'QUALIFICATION_RESTART_USED', lambda: 'in place' in str(safe(lambda: cj.restart_problem(led, str(d)), ''))
            and refusal(cj.ledger_admit_prepare, led, {'9990009': {'case_id': '9990009', 'nonattempt': False}}, '9990009', 'A', '/x/new',
                        {'frozen_utc': '2026-01-01T00:00:00.000Z'}) == 'QUALIFICATION_RESTART_USED')
    # tiles: an invented delivered render folder with one page and two tiles
    r = u / 'render'
    (r / 'tiles').mkdir(parents=True)
    page, t1, t2 = b'invented page png', b'invented tile 1 png', b'invented tile 2 png'
    (r / 'page-0001.png').write_bytes(page)
    (r / 'tiles' / 'page-0001-tile-01.png').write_bytes(t1)
    (r / 'tiles' / 'page-0001-tile-02.png').write_bytes(t2)

    def tile(k, b):
        return {'file': f'tiles/page-0001-tile-{k:02d}.png', 'sha256': sha(b), 'bytes': len(b), 'x': 0, 'y': 0, 'width_px': 1900,
                'height_px': 1900, 'png_width_px': 1900, 'png_height_px': 1900}

    def man(**over):
        m = {'images': [{'file': 'page-0001.png', 'page': 1, 'sha256': sha(page), 'bytes': len(page), 'tiles': [tile(1, t1), tile(2, t2)]}],
             'tiles': {'count': 2, 'total_width': 332.2, 'legibility_bound_exceeded': False}}
        m.update(over)
        return m
    good = man()
    no_tiles = man(images=[{'file': 'page-0001.png', 'page': 1, 'sha256': sha(page), 'bytes': len(page)}])
    escaped = man(images=[dict(good['images'][0], tiles=[dict(tile(1, t1), file='../outside.png'), tile(2, t2)])])
    t.check('F3-tiles: a delivered page without tiles, a missing tiles block, a count that is not the tiles listed, or a tile path '
            'outside the render folder is a render problem; the complete manifest has none',
            lambda: safe(lambda: cj.deliverable_tile_problems(good), 'raised') == []
            and 'DELIVERED_PAGE_WITHOUT_TILES' in cj.deliverable_tile_problems(dict(no_tiles, tiles=dict(good['tiles'], count=0)))
            and cj.deliverable_tile_problems(man(tiles=None)) == ['DELIVERED_TILES_MISSING']
            and 'DELIVERED_TILES_COUNT_MISMATCH' in cj.deliverable_tile_problems(man(tiles=dict(good['tiles'], count=3)))
            and 'DELIVERED_TILE_ENTRY_INVALID' in cj.deliverable_tile_problems(escaped))
    t.check('F3-tiles: tiles.legibility_bound_exceeded true (or a delivered manifest without its tiles block) is a visual failure: the '
            'sheet cannot be judged', lambda: cj.legibility_bound_exceeded(man(tiles=dict(good['tiles'], legibility_bound_exceeded=True)))
            is True and cj.legibility_bound_exceeded(man(tiles=None)) is True and cj.legibility_bound_exceeded(good) is False)
    mp = r / 'VISUAL_QA_MANIFEST.json'
    mp.write_text(json.dumps(good), encoding='utf-8')
    before = safe(lambda: cj.page_image_problems({'deliverable': (good, mp)}), ['raised'])
    (r / 'tiles' / 'page-0001-tile-02.png').write_bytes(t1)              # a tile swapped
    after = safe(lambda: cj.page_image_problems({'deliverable': (good, mp)}), ['raised'])
    esc = safe(lambda: cj.page_image_problems({'deliverable': (escaped, mp)}), ['raised'])
    t.check('F3-tiles/R8 (unit): every tile of a delivered page is checked against its manifest sha256 and path (a swapped tile and a '
            'tile outside the render folder are problems)', lambda: before == [] and after == ['deliverable page 1 tile 2']
            and 'deliverable page 1 tile 1' in esc, lambda: json.dumps([before, after, esc]))


def test_docs_int(t):
    """Items 1-4 in the command sheet, the template and the code: V28, the two restart forms, the tiles and the template
    heading, F2 (item 9 equals the README's), and the O40 record."""
    doc = (HERE / 'RUN_JOB_COMMANDS.md').read_text(encoding='utf-8')
    tpl = (HERE / 'VISUAL_REVIEW_PROMPT_TEMPLATE.md').read_text(encoding='utf-8')
    readme = (REPO / 'research/export/README.md').read_text(encoding='utf-8')
    cj = load_runner()
    texts = {n: (HERE / n).read_text(encoding='utf-8') for n in ('cps_job.py', 'RUN_JOB_COMMANDS.md', 'RELEASE.example.json',
                                                             'VISUAL_REVIEW_PROMPT_TEMPLATE.md')}
    rel_ex = json.loads(texts['RELEASE.example.json'])
    t.check('V28: deploy/run names research/export/ADMISSION_WRITER_V28.json and no longer ADMISSION_WRITER_V27.json (the test release '
            'names it through one constant)', lambda: WRITER_ADMISSION == 'research/export/ADMISSION_WRITER_V28.json'
            and rel_ex['writer']['admission'] == WRITER_ADMISSION and all('ADMISSION_WRITER_V' + '27' not in x for x in texts.values())
            and 'ADMISSION_WRITER_V28.json' in texts['VISUAL_REVIEW_PROMPT_TEMPLATE.md'] and doc.count('ADMISSION_WRITER_V28.json') >= 3
            and json.loads(t.release_path.read_text(encoding='utf-8'))['writer']['admission'] == WRITER_ADMISSION)
    t.check('R3-inplace: RUN_JOB_COMMANDS "Restart" describes both forms (a new folder, and in place after an agreed scope) and the one '
            'restart per case and reader in total', lambda: '**Form 1: restart in a new folder.**' in doc
            and '**Form 2: restart in place, after the scope is agreed.**' in doc and 'once per case and reader in total' in doc
            and 'INTERRUPT_RESTART_USED' in doc and 'interrupted/generator_output/' in doc)

    def checklist(text, heading):
        a = text.index(heading)
        lines = text[a:].splitlines()[1:]
        items = {}
        for ln in lines:
            ln = ln.strip()
            if ln[:2] in [f'{i}.' for i in range(1, 10)]:
                items[ln[0]] = ln[3:]
            elif items and (ln.startswith('#') or ln.startswith('- **') or ln.startswith('**')):
                break
        return items

    def core(x):
        """An item without its closing parenthetical note and final punctuation."""
        x = x.rstrip(' .;')
        if x.endswith(')') and ' (' in x:
            x = x[:x.rindex(' (')]
        return x.rstrip(' .;')
    tpl_items = checklist(tpl, '**Delivered workbook checklist')
    rd_items = checklist(readme, '- **Delivered workbook checklist')
    t.check('F2 (guard): the template\'s delivered checklist item 9 equals item 9 of the README delivered checklist '
            '(research/export/README.md, "Conditions of use"), up to its closing note; both lists have nine items',
            lambda: sorted(tpl_items) == sorted(rd_items) == [str(i) for i in range(1, 10)] and core(tpl_items['9']) == core(rd_items['9'])
            and 'no value is cut at a column edge or by a filled neighbour' in core(tpl_items['9']),
            lambda: json.dumps([tpl_items.get('9'), rd_items.get('9')], ensure_ascii=False))
    t.check('F3-tiles: the template\'s delivered checklist heading names v2.8, O38 and O39, and section A tells the reviewer to read every '
            'tile of every page (the page PNG is the overview)', lambda: '**Delivered workbook checklist (v2.8, owner decisions O38 and O39).**' in tpl
            and 'Read every tile of every page, at full size' in tpl and 'the tiles of each page' in tpl)
    rec = (REPO / 'research/guideline046_005/DECISIONS_OWNER_O23_O25.md').read_text(encoding='utf-8')
    t.check('O40: qualification_transcript_rule cites research/guideline046_005/DECISIONS_OWNER_O23_O25.md, which records O40, and '
            'RUN_JOB_COMMANDS cites it', lambda: 'research/guideline046_005/DECISIONS_OWNER_O23_O25.md' in cj.O40_RULE
            and '## O40 (2026-11-06): evidence of generator isolation in qualification' in rec
            and 'evidence of generator isolation in qualification' in cj.O40_RULE
            and 'recorded in `research/guideline046_005/DECISIONS_OWNER_O23_O25.md`' in doc)


def test_e1_written(t):
    """E1 (protocol rule 3, "before the response is written"): once the broken conversation wrote its file, interrupt is
    refused with nothing appended and the file goes through finish or scope-finish; a run whose FROZEN.json lists a written
    file is not restarted."""
    L = t.work / 'qualification' / 'LEDGER_e1.jsonl'
    cases = {c: job_files(t, c, source=t.paths['large'] if c == '9990048' else None) for c in ('9990047', '9990048', '9990049')}
    adms = {c: admission(t, c, *cases[c]) for c in cases}
    rq = qual_release(t, 'RELEASE_QUAL_E1.json', list(adms.values()), L)
    # 9990047: the generator wrote its response, then the operator calls it a technical break
    code, _, last = qprepare(t, rq, *cases['9990047'], 'qe_A', 'A', adms['9990047'])
    jd = t.work / 'qe_A' / '9990047'
    resp = safe(lambda: stand_in_response(t, jd, '9990047', break_it=True))
    rec_b, led_b = safe(lambda: (jd / 'RUN_RECORD.json').read_bytes()), safe(lambda: L.read_bytes())
    code, out, last = interrupt(t, jd)
    t.check('E1: after NEXT: GENERATE, interrupt is refused RESPONSE_WRITTEN once the generator wrote run/<reader>/output/response.json, '
            'with nothing appended (record and ledger unchanged)', lambda: code == 4 and last == 'REFUSED: RESPONSE_WRITTEN'
            and last_json(out).get('detail', {}).get('file') == 'run/A/output/response.json'
            and (jd / 'RUN_RECORD.json').read_bytes() == rec_b and L.read_bytes() == led_b, last)
    g = safe(lambda: generation_record(jd, '9990047'))
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--generator-model', 'stand-in (invented test)',
                             '--generation-record', g)
    t.check('E1: the operator goes on with the written response: finish records it as the run\'s result (here a failed route check)',
            lambda: code == 3 and last == 'NEXT: STOP_ROUTE_CHECK_FAILED' and stages(jd, 'freeze_response')[-1]['completed'], last)
    # 9990048: the scope reader wrote a disagreeing file
    code, _, last = qprepare(t, rq, *cases['9990048'], 'qe_A', 'A', adms['9990048'])
    jd = t.work / 'qe_A' / '9990048'
    rr = safe(lambda: scope_reader_response(jd, '9990048', end=t.large_end_row - 1))
    rec_b, led_b = safe(lambda: (jd / 'RUN_RECORD.json').read_bytes()), safe(lambda: L.read_bytes())
    code, out, last = interrupt(t, jd)
    t.check('E1: after NEXT: SCOPE_READER, interrupt is refused RESPONSE_WRITTEN once the reader wrote '
            'scope/reader/output/SCOPE_READER_RESPONSE.json (a disagreeing one), nothing appended', lambda: code == 4
            and last == 'REFUSED: RESPONSE_WRITTEN' and last_json(out).get('detail', {}).get('file') == 'scope/reader/output/SCOPE_READER_RESPONSE.json'
            and (jd / 'RUN_RECORD.json').read_bytes() == rec_b and L.read_bytes() == led_b, last)
    psha = safe(lambda: sha_file(jd / 'scope' / 'SCOPE_READER_PROMPT.md'), '0' * 64)
    code, _, last = t.runner('scope-finish', '--job-dir', jd, '--reader-response', rr, '--reader-prompt-sha256', psha)
    t.check('E1: the operator goes on with the written reader file: scope-finish records the disagreement (NEXT: OWNER_DECISION)',
            lambda: code == 3 and last == 'NEXT: OWNER_DECISION', last)
    # 9990049: the interruption was recorded, then the conversation's response appeared before freeze
    code, _, last = qprepare(t, rq, *cases['9990049'], 'qe_A', 'A', adms['9990049'])
    jd = t.work / 'qe_A' / '9990049'
    code, _, last = interrupt(t, jd)
    first = (code, last)
    safe(lambda: stand_in_response(t, jd, '9990049'))
    code, _, last = t.runner('freeze', '--job-dir', jd)
    code, _, last = qprepare(t, rq, *cases['9990049'], 'qe_A_restart1', 'A', adms['9990049'])
    t.check('E1: a run whose FROZEN.json lists a written response file is not restarted (QUALIFICATION_RESTART_NOT_ALLOWED), even after '
            'a recorded interruption; no folder', lambda: first == (3, 'NEXT: STOP_TECHNICAL_INTERRUPTION') and code == 4
            and last == 'REFUSED: QUALIFICATION_RESTART_NOT_ALLOWED' and not (t.work / 'qe_A_restart1' / '9990049').exists(), last)
    # the restart rule on invented ledgers: each written response path
    cj = load_runner()
    u = t.work / 'unit_e1'
    u.mkdir()
    got = {}
    for k, path in enumerate(('scope/reader/output/SCOPE_READER_RESPONSE.json', 'run/A/output/response.json', 'run/B/output/response.json',
                              'interrupted/generator_output/response.json')):
        d = u / f'prev{k}'
        d.mkdir()
        fz = cj.dumps({'schema': 'cps.job-frozen.v2', 'files': [{'path': path, 'bytes': 1, 'sha256': '0' * 64}]})
        (d / 'FROZEN.json').write_bytes(fz)
        es = [{'type': 'record', 'job_dir': str(d), 'stage': st_, 'next': nx, 'completed': True}
              for st_, nx in (('prepare', 'SCOPE_READER' if 'scope' in path else 'GENERATE'), ('interrupt', 'STOP_TECHNICAL_INTERRUPTION'))]
        es.append({'type': 'freeze', 'job_dir': str(d), 'frozen_sha256': sha(fz)})
        got[path] = safe(lambda: cj.restart_problem(fake_ledger(cj, u / 'L.jsonl', es), str(d)))
    t.check('E1 (unit): the restart rule refuses a run whose FROZEN.json lists scope/reader/output/SCOPE_READER_RESPONSE.json, '
            'run/A|B/output/response.json or interrupted/generator_output/response.json', lambda: len(got) == 4
            and all(v and 'wrote its response file' in v for v in got.values()), lambda: json.dumps(got))


def test_docs_final(t):
    """EN1 (no stale text), EN4 (persistent JOB_BUSY) and the E1 and E2 instructions in the command sheet."""
    doc = (HERE / 'RUN_JOB_COMMANDS.md').read_text(encoding='utf-8')
    texts = {n: (HERE / n).read_text(encoding='utf-8') for n in ('cps_job.py', 'RUN_JOB_COMMANDS.md', 'VISUAL_REVIEW_PROMPT_TEMPLATE.md',
                                                             'RELEASE.example.json')}
    t.check('EN1: deploy/run names visual_qa v4.5 and the admitted V28: no text names visual_qa v4.4 or a provisional V28',
            lambda: all('v4.' + '4' not in x and 'PROVISIONAL_NOT_' + 'ADMITTED' not in x for x in texts.values())
            and 'visual_qa v4.5' in doc and '`research/export/visual_qa.py` v4.5' in texts['VISUAL_REVIEW_PROMPT_TEMPLATE.md']
            and 'admitted 2026-11-06' in doc)
    t.check('EN4: RUN_JOB_COMMANDS says what to do when JOB_BUSY persists: tell the owner, never delete anything',
            lambda: 'If `JOB_BUSY` persists' in doc and 'tell the owner' in doc and 'Never delete, move or kill anything' in doc)
    t.check('E1/E2: RUN_JOB_COMMANDS says that a written file has no restart (RESPONSE_WRITTEN: go on with scope-finish or finish) and that '
            'writer.admission_sha256 is required and re-checked at visual-record and deliver-check',
            lambda: '**Once the conversation has written its file, there is no restart.**' in doc and 'RESPONSE_WRITTEN' in doc
            and '**both required**' in doc and 'again at `visual-record` and `deliver-check`' in doc)


def test_no_private_values_printed(t):
    leaks = []
    for out in t.outputs:
        for line in out.splitlines():
            if line.startswith('NEXT: DELIVER file='):
                continue                       # the one path the runner must print: the file to deliver
            leaks += [s for s in PRIVATE_STRINGS if s in line]
    t.check('no job-input value, title or cell text in any runner output (except the delivery path)', lambda: not leaks, lambda: json.dumps(sorted(set(leaks)), ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--writer-dir', default=str(REPO / 'deploy/writer_route/writer'))
    ap.add_argument('--node', default='/opt/node22/bin/node')
    ap.add_argument('--node-sha256', default='2286ce921a47349726b0e8b037ccbb6627043d24d1fc3c8f22c2dc53c4a1f7ff')
    ap.add_argument('--node-path', default=os.environ.get('NODE_PATH'), help='NODE_PATH that resolves playwright (release source_prep.node_path)')
    a = ap.parse_args()
    if not Path(a.work).is_absolute():
        ap.error('--work must be absolute')
    dirty = subprocess.run(['git', '-C', str(REPO), 'status', '--porcelain', '--untracked-files=no'], capture_output=True, text=True)
    if dirty.returncode != 0 or dirty.stdout.strip():
        print(json.dumps({'error': 'run the test from a clean git checkout at a commit: the runner refuses a dirty tracked tree (R10)'}))
        return 2
    t = T(a)
    started = time.time()
    setup(t)
    for fn in (test_units, test_units_review, test_units_record, test_units_release, test_units_misc, test_prepare_refusals,
               test_real_job, test_node_and_tamper, test_route_check_failure, test_stage_output_exists, test_qualification,
               test_qualification_ledger, test_visual_fail_blocks_delivery, test_large, test_r1_scope_inputs,
               test_r4_lock_and_interruption, test_r5_run_folder, test_units_delta, test_docs_delta, test_delta_qualification,
               test_units_int, test_docs_int, test_int_inplace, test_e1_written, test_docs_final, test_no_private_values_printed):
        try:
            fn(t)
        except Exception:                                  # noqa: BLE001
            t.results.append({'test': fn.__name__ + ' (raised)', 'passed': False, 'detail': traceback.format_exc()[-1500:]})
    failed = [r for r in t.results if not r['passed']]
    summary = {'schema': 'cps.job-runner-tests.v2', 'runner_sha256': sha_file(RUNNER), 'tests': len(t.results),
               'passed_count': len(t.results) - len(failed), 'failed': failed, 'seconds': round(time.time() - started, 1),
               'results': [r['test'] for r in t.results]}
    (t.work / 'TEST_RESULTS.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('tests', 'passed_count', 'failed', 'seconds')}, ensure_ascii=False, indent=1))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
