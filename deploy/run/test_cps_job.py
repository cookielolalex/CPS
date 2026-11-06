#!/usr/bin/env python3
"""End-to-end test of deploy/run/cps_job.py on invented data only.

Builds invented 材料清單 workbooks (stdlib zipfile; the small one reproduces the cells of the package's invented
EXAMPLE_INVENTORY.json, so the package's invented EXAMPLE_RESPONSE.json, adapted to the job's case id and inventory hash,
stands in for the generator and passes the route check), an invented glossary (cps.company-glossary.v1), invented
JOB.json (cps.job-config.v2) and JOB_TITLE.json (cps.job-title.v1) files, an invented qualification jobs list, invented
admissions, ledgers, generation records and release files, then runs the runner's subcommands end to end: prepare,
finish, visual-record, deliver-check, scope-finish, freeze, verify-frozen and nonattempt, with the negative cases (one
test or more for each finding R1-R13 and each fixed note of the 2026-11-06 review). No private data is read or written.

Usage: python3 -I -B deploy/run/test_cps_job.py --work /abs/NEW_DIR
         [--writer-dir /abs/deploy/writer_route/writer] [--node /opt/node22/bin/node] [--node-sha256 HEX] [--node-path DIR]
Run it from a clean checkout at a commit (the runner refuses a dirty tracked tree, review R10; the test exits 2 first).
Needs what the runner needs: python3 with openpyxl 3.1.5, node 22, Playwright Chromium (NODE_PATH), LibreOffice and
poppler, and git. Prints one JSON summary; exit 0 when every test passes. Tests that tamper with a read-only file or
folder make it writable first, so they also run as an unprivileged user.
"""
import argparse, contextlib, datetime, hashlib, importlib.util, io, json, os, shutil, signal, stat, subprocess, sys, time, traceback, zipfile
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
# R12: the further files a qualification admission pins by label (repository-relative path), and JOBS.json
ADMISSION_TOOL_LABELS = EXECUTED + ['research/export/ADMISSION_WRITER_V27.json', 'research/evaluation/compare_target050.py',
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
        'writer': {'admission': 'research/export/ADMISSION_WRITER_V27.json',
                   'admission_sha256': sha_file(REPO / 'research/export/ADMISSION_WRITER_V27.json'), 'writer_dir': t.a.writer_dir},
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
        {'case_id': '9991007', 'order': 5, 'nonattempt': False}]}
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
    code, out, last, jd = prepare(t, '9990002')
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
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', full, '--reviewer-conversation-id', 'invented-operator-attested-id')
    vrec = json.loads((jd / 'qa' / 'VISUAL_RECORD.json').read_text(encoding='utf-8')) if (jd / 'qa' / 'VISUAL_RECORD.json').is_file() else {}
    t.check('R6: with the operator-attested --reviewer-conversation-id the review is recorded PASS, NEXT: DELIVER_CHECK',
            lambda: code == 0 and last == 'NEXT: DELIVER_CHECK' and vrec.get('reviewer_conversation_id') == 'invented-operator-attested-id'
            and vrec.get('reviewer_conversation_id_source', '').startswith('operator'), last)
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
    code, out, last = t.runner('nonattempt', '--release', rq, '--admission', adms['9990032'], '--case', '9990032', '--reader', 'A',
                               '--reason', 'NONATTEMPT_SOURCE_UNAVAILABLE', '--operator-model', 'test-harness')
    t.check('N13/R11: nonattempt records a nonattempt in the ledger: NEXT: DONE', lambda: code == 0 and last == 'NEXT: DONE'
            and any(e['type'] == 'nonattempt' and e['case_id'] == '9990032' and e['reason'] == 'NONATTEMPT_SOURCE_UNAVAILABLE' for e in ledger(L)), last)
    code, _, last = qprepare(t, rq, *cases['9990032'], 'qr_A', 'A', adms['9990032'])
    t.check('R11: a case and reader with a recorded nonattempt cannot be prepared', lambda: code == 4
            and last == 'REFUSED: QUALIFICATION_NONATTEMPT_RECORDED', last)
    code, _, last = qprepare(t, rq, *cases['9990033'], 'qr_A', 'A', adms['9990033'])
    jd1 = t.work / 'qr_A' / '9990033'
    t.check('a technical stop at prepare (the builder cannot read the invented broken source): NEXT: STOP_INVENTORY_BUILD_FAILED',
            lambda: code == 3 and last == 'NEXT: STOP_INVENTORY_BUILD_FAILED', last)
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
    code, _, last = qprepare(t, rq, *cases['9990033'], 'qr_A_restart1', 'A', adms['9990033'])
    jd2 = t.work / 'qr_A_restart1' / '9990033'
    t.check('R11: one restart after a frozen technical stop at prepare is allowed; both the record and the ledger name it',
            lambda: code == 3 and last == 'NEXT: STOP_INVENTORY_BUILD_FAILED' and record(jd2)['restart_of'] == str(jd1)
            and any(e['type'] == 'prepare' and e['job_dir'] == str(jd2) and e['restart_of'] == str(jd1) for e in ledger(L)), last)
    code, _, last = t.runner('freeze', '--job-dir', jd2)
    code, _, last = qprepare(t, rq, *cases['9990033'], 'qr_A_restart2', 'A', adms['9990033'])
    t.check('R11: a second restart is refused QUALIFICATION_RESTART_USED', lambda: code == 4 and last == 'REFUSED: QUALIFICATION_RESTART_USED', last)


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
    def png_swap():
        vi = jd / 'qa' / 'visual_internal'
        force_write(vi / 'page-0002.png', (vi / 'page-0003.png').read_bytes())
        code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', stand_in_review(jd))
        vr = stages(jd, 'visual-record')[-1] if stages(jd, 'visual-record') else {}
        return (code == 3 and last == 'NEXT: STOP_VISUAL_PAGES_CHANGED' and vr.get('completed') and 'internal page 2' in vr.get('codes', [])
                and not (jd / 'qa' / 'VISUAL_RECORD.json').exists())
    t.check('R8: a page image swapped after finish stops visual-record as tampering (NEXT: STOP_VISUAL_PAGES_CHANGED, recorded)', png_swap)
    code, out, last, jd = prepare(t, '9990024')
    resp = stand_in_response(t, jd, '9990024')
    p = subprocess.Popen([sys.executable, '-I', '-B', str(RUNNER), 'finish', '--job-dir', str(jd), '--response', str(resp)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    wait_for(lambda: any(s['stage'] == 'freeze_response' for s in record(jd)['stages']))
    time.sleep(0.5)
    p.send_signal(signal.SIGKILL)                           # e.g. the operator's shell tool timed out
    p.communicate()
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
               test_r4_lock_and_interruption, test_r5_run_folder, test_no_private_values_printed):
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
