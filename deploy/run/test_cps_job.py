#!/usr/bin/env python3
"""End-to-end test of deploy/run/cps_job.py on invented data only.

Builds invented 材料清單 workbooks (stdlib zipfile; the small one reproduces the cells of the package's invented
EXAMPLE_INVENTORY.json, so the package's invented EXAMPLE_RESPONSE.json, adapted to the job's case id and inventory hash,
stands in for the generator and passes the route check), an invented glossary (cps.company-glossary.v1), invented
JOB.json (cps.job-config.v2) and JOB_TITLE.json (cps.job-title.v1) files and invented release files, then runs the
runner's subcommands end to end: prepare, finish, visual-record, deliver-check, scope-finish and freeze, with the
negative cases. No private data is read or written.

Usage: python3 -I -B deploy/run/test_cps_job.py --work /abs/NEW_DIR
         [--writer-dir /abs/deploy/writer_route/writer] [--node /opt/node22/bin/node] [--node-sha256 HEX] [--node-path DIR]
Needs what the runner needs: python3 with openpyxl 3.1.5, node 22, Playwright Chromium (NODE_PATH), LibreOffice and
poppler. Prints one JSON summary; exit 0 when every test passes.
"""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time, traceback, zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUNNER = HERE / 'cps_job.py'
PKG = REPO / 'research/guideline046_007/package'
HARNESS = REPO / 'research/guideline046_007/harness'
CUSTOMER, PROJECT, COMPANY = '示例縣自來水事業處', '示例淨水場控制盤更新', '示例機電股份有限公司'   # invented (the package example's)
PRIVATE_STRINGS = (CUSTOMER, PROJECT, COMPANY, '示例公司', '控制盤', '電磁接觸器', 'XMC', '示例材料', '示例客戶')


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

    def runner(self, *argv):
        p = subprocess.run([sys.executable, '-I', '-B', str(RUNNER), *[str(x) for x in argv]], capture_output=True, timeout=3600)
        out = p.stdout.decode('utf-8', 'replace')
        self.outputs.append(out)
        lines = [ln for ln in out.strip().splitlines() if ln.strip()]
        last = lines[-1] if lines else ''
        return p.returncode, out, last

    def check(self, name, cond, detail=''):
        self.results.append({'test': name, 'passed': bool(cond), 'detail': detail if not cond else ''})
        return bool(cond)


def setup(t):
    w = t.work
    w.mkdir(parents=True, exist_ok=False)
    (w / 'tables').mkdir()
    (w / 'jobs_in').mkdir()
    src = w / 'jobs_in' / 'invented_material_list.xlsx'
    glossary = small_workbook(src)
    gpath = w / 'tables' / 'GLOSSARY.json'
    gpath.write_text(json.dumps(glossary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    large = w / 'jobs_in' / 'invented_large.xlsx'
    t.large_end_row = large_workbook(large)
    # deps bundle for the builders (-S): private/deps -> the site directory that holds openpyxl 3.1.5
    site = Path(importlib.util.find_spec('openpyxl').origin).resolve().parents[1]
    (w / 'deps' / 'private').mkdir(parents=True)
    os.symlink(site, w / 'deps' / 'private' / 'deps')
    # the checker node through a symbolic link, so a test can swap the binary it names
    (w / 'nodelink').mkdir()
    os.symlink(t.a.node, w / 'nodelink' / 'node')
    head = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    t.paths = {'src': src, 'large': large, 'glossary': gpath}
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
    }
    t.release_path = write_release(t, 'RELEASE_USE.json', t.release)
    t.release_q_path = write_release(t, 'RELEASE_QUAL.json', dict(t.release, status='RELEASED_FOR_QUALIFICATION'))


def write_release(t, name, d):
    p = t.work / name
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return p


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


def stand_in_response(t, jd, case, break_it=False):
    """The package's invented EXAMPLE_RESPONSE.json for this job: case id and inventory hash adapted. It is the
    generator's response file in run/A/output/."""
    inv = jd / 'run' / 'A' / 'input' / 'packet' / 'SOURCE_INVENTORY.json'
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
    p = jd / 'run' / 'A' / 'output' / 'response.json'
    p.write_text(json.dumps(r, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return p


def stand_in_review(jd, fail=False, drop_page=False):
    """A stand-in visual review that marks every selected item pass (or one fail)."""
    pages = json.loads((jd / 'qa' / 'VISUAL_PAGES.json').read_text(encoding='utf-8'))
    rv = {'schema': 'cps.visual-review.v1', 'reviewer': {'kind': 'test_stand_in', 'model': 'none (invented test)', 'effort': 'n/a'}}
    for key, wb in pages['workbooks'].items():
        sel = wb['selected'][:-1] if (drop_page and key == 'internal') else wb['selected']
        rv[key] = {'manifest_sha256': wb['manifest_sha256'],
                   'pages': {str(p): {str(i): {'result': 'pass', 'note': ''} for i in range(1, 10)} for p in sel}}
    rv['overall'], rv['failures'] = 'PASS', []
    if fail:
        rv['deliverable']['pages']['1']['6'] = {'result': 'fail', 'note': 'invented failure'}
        rv['overall'], rv['failures'] = 'FAIL', ['deliverable page 1 item 6: invented failure']
    out = jd / 'qa' / 'visual_review' / ('VISUAL_REVIEW.json' if not drop_page else 'VISUAL_REVIEW.partial.json')
    out.write_text(json.dumps(rv, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return out


def record(jd):
    return json.loads((jd / 'RUN_RECORD.json').read_text(encoding='utf-8'))


def stages(jd, name):
    return [s for s in record(jd)['stages'] if s['stage'] == name]


def next_path(last, key):
    for part in last.split(' '):
        if part.startswith(key + '='):
            return Path(part[len(key) + 1:])
    return None


# ------------------------------------------------------------------ tests
def test_real_job(t):
    """9990001: prepare -> GENERATE; finish -> VISUAL_REVIEW (evidence grade); visual-record PASS; deliver-check -> DELIVER;
    a second finish and a second prepare are refused."""
    code, out, last, jd = prepare(t, '9990001')
    t.check('prepare: NEXT: GENERATE, exit 0', code == 0 and last.startswith('NEXT: GENERATE '), last)
    t.check('prepare: runbook layout', all((jd / d).is_dir() for d in ('input', 'packet', 'scope', 'run', 'response', 'carrier', 'export', 'qa'))
            and (jd / 'RUN_RECORD.json').is_file())
    prompt, folder = next_path(last, 'prompt'), next_path(last, 'folder')
    t.check('prepare: generator prompt names the run folder', prompt is not None and prompt.is_file()
            and str(folder) in prompt.read_text(encoding='utf-8') and '{RUN}' not in prompt.read_text(encoding='utf-8'))
    t.check('prepare: run folder holds the package and the packet only', folder is not None
            and sorted(p.name for p in (folder / 'input').iterdir()) == ['package', 'packet'] and (folder / 'output').is_dir())
    pr = stages(jd, 'prepare')[-1]
    t.check('prepare: record entry (completed, scope tool NOT_APPLIED, check-inventory PASS)',
            pr['completed'] and pr['result'] == 'PREPARED_NOT_SCOPED' and pr['facts']['scope_tool']['status'] == 'NOT_APPLIED'
            and pr['facts']['check_inventory_full']['status'] == 'PASS' and pr['facts']['check_inventory_full']['policy_checks'] == 'applied',
            json.dumps(pr.get('facts', {}).get('scope_tool')))
    jp, tp = t.work / 'jobs_in' / '9990001' / 'JOB.json', t.work / 'jobs_in' / '9990001' / 'JOB_TITLE.json'
    code2, _, last2 = t.runner('prepare', '--release', t.release_path, '--job', jp, '--job-title-file', tp, '--jobs-root', t.work / 'jobs')
    t.check('prepare again into the same job folder: refused', code2 == 4 and last2 == 'REFUSED: JOB_DIR_EXISTS', last2)
    resp = stand_in_response(t, jd, '9990001')
    code, out, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--generator-model', 'stand-in (invented test)')
    t.check('finish: NEXT: VISUAL_REVIEW, exit 0', code == 0 and last.startswith('NEXT: VISUAL_REVIEW '), last + out[-600:])
    ev = json.loads((jd / 'qa' / 'QA_EVIDENCE.json').read_text(encoding='utf-8')) if (jd / 'qa' / 'QA_EVIDENCE.json').is_file() else {}
    t.check('finish: QA_EVIDENCE evidence_grade true', ev.get('evidence_grade') is True, json.dumps(ev.get('failed_conditions')))
    ids = {c['id']: c for c in ev.get('conditions', [])}
    t.check('finish: QA_EVIDENCE records condition 7 (title file) and condition 6 (mode v2 from the convert receipt)',
            ids.get('7.job_title', {}).get('met') is True and ids.get('6.mode', {}).get('value', {}).get('mode') == 'v2')
    t.check('finish: response frozen read-only with its sha256 recorded',
            (jd / 'response' / 'response.json').is_file() and not (os.stat(jd / 'response' / 'response.json').st_mode & 0o222)
            and stages(jd, 'freeze_response')[-1]['outputs']['response']['sha256'] == sha_file(resp))
    vp = json.loads((jd / 'qa' / 'VISUAL_PAGES.json').read_text(encoding='utf-8'))
    dl, it = vp['workbooks']['deliverable'], vp['workbooks']['internal']
    rev = [int(p) for p, e in it['pages'].items() if e['role'] == 'review']
    want = sorted({int(p) for p, e in it['pages'].items() if e['role'] != 'review'} | set(sorted(rev)[:2] + sorted(rev)[-1:]))
    t.check('finish: page selection (every delivered page; internal main/composition pages, review pages 1, 2 and last)',
            dl['selected'] == list(range(1, dl['pages_total'] + 1)) and it['selected'] == want, json.dumps(it['selected']))
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    t.check('a second finish is refused', code == 4 and last == 'REFUSED: STAGE_ALREADY_COMPLETED', last)
    review = stand_in_review(jd)
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', review)
    t.check('visual-record: PASS, NEXT: DELIVER_CHECK', code == 0 and last == 'NEXT: DELIVER_CHECK', last)
    code, out, last = t.runner('deliver-check', '--job-dir', jd)
    f = next_path(last, 'file')
    saved = json.loads((jd / 'qa' / 'SAVED_QA.json').read_text(encoding='utf-8'))
    t.check('deliver-check: NEXT: DELIVER with the absolute path of the delivered workbook', code == 0 and f is not None and f.is_absolute()
            and f.is_file() and sha_file(f) == saved['deliverable_xlsx']['sha256'] and f.name.endswith('(未填).xlsx'), last)
    dc = json.loads((jd / 'qa' / 'DELIVERY_CHECK.json').read_text(encoding='utf-8'))
    t.check('deliver-check: DELIVERY_CHECK.json DELIVERABLE', dc['result'] == 'DELIVERABLE' and all(dc['checks'].values()))
    rec = record(jd)
    t.check('RUN_RECORD: append-only chain', all(s['seq'] == i + 1 for i, s in enumerate(rec['stages']))
            and [s['stage'] for s in rec['stages'] if s['completed']] == ['prepare', 'freeze_response', 'finish', 'visual-record', 'deliver-check'])


def test_node_and_tamper(t):
    """9990002: a checker node whose binary changed after prepare is refused at finish (nothing consumed); after it is
    restored, finish runs; a tampered delivered file fails deliver-check."""
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
    t.check('finish with a checker node binary that is not admitted: refused', code == 4 and last == 'REFUSED: CHECKER_NODE_NOT_ADMITTED', last)
    t.check('the refused finish consumed nothing (no frozen response, attempt recorded as not completed)',
            not (jd / 'response' / 'response.json').exists() and stages(jd, 'finish')[-1]['completed'] is False)
    code, out, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    t.check('finish after the node is restored: NEXT: VISUAL_REVIEW', code == 0 and last.startswith('NEXT: VISUAL_REVIEW'), last)
    partial = stand_in_review(jd, drop_page=True)
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', partial)
    t.check('visual-record: a review that omits a selected page is refused (not recorded as a result)',
            code == 4 and last == 'REFUSED: REVIEW_INCOMPLETE', last)
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', stand_in_review(jd))
    t.check('visual-record after a complete review: NEXT: DELIVER_CHECK', code == 0 and last == 'NEXT: DELIVER_CHECK', last)
    saved = json.loads((jd / 'qa' / 'SAVED_QA.json').read_text(encoding='utf-8'))
    f = jd / 'export' / 'writer' / saved['deliverable_xlsx']['file']
    f.chmod(0o644)
    with open(f, 'ab') as fh:
        fh.write(b'\0')
    code, _, last = t.runner('deliver-check', '--job-dir', jd)
    dc = json.loads((jd / 'qa' / 'DELIVERY_CHECK.json').read_text(encoding='utf-8'))
    t.check('deliver-check on a tampered delivered file: STOP, DO_NOT_DELIVER', code == 3 and last == 'NEXT: STOP_DELIVERY_CHECK_FAILED'
            and dc['result'] == 'DO_NOT_DELIVER' and dc['checks']['sha256_equals_saved_qa'] is False, last)


def test_prepare_refusals(t):
    rel = json.loads(t.release_path.read_text(encoding='utf-8'))
    bad = write_release(t, 'RELEASE_NODE.json', dict(rel, admitted_checker_node_sha256=['0' * 64]))
    code, _, last, jd = prepare(t, '9990010', release=bad)
    t.check('prepare with a checker node whose sha256 is not admitted: refused, no job folder', code == 4
            and last == 'REFUSED: CHECKER_NODE_NOT_ADMITTED' and not jd.exists(), last)
    code, _, last, jd = prepare(t, '9990011', extra={'job_title': '9990011示例'})
    t.check('prepare with the title inside JOB.json: refused', code == 4 and last == 'REFUSED: JOB_TITLE_IN_JOB_JSON' and not jd.exists(), last)
    bad = write_release(t, 'RELEASE_TABLE.json', dict(rel, tables=dict(rel['tables'], glossary={'path': rel['tables']['glossary']['path'], 'sha256': '1' * 64})))
    code, _, last, jd = prepare(t, '9990012', release=bad)
    t.check('prepare with a glossary that is not the released table: refused', code == 4 and last == 'REFUSED: TABLE_SHA256_MISMATCH', last)
    code, _, last, jd = prepare(t, '9990013', release=t.release_q_path)
    t.check('prepare of a real job under a qualification release: refused', code == 4 and last == 'REFUSED: RELEASE_STATUS', last)
    jp, tp = job_files(t, 'ABC0015')
    code, _, last = t.runner('prepare', '--release', t.release_path, '--job', jp, '--job-title-file', tp, '--jobs-root', t.work / 'jobs')
    t.check('prepare with a title the writer would refuse (no 7-digit case id): refused before any folder', code == 4
            and last == 'REFUSED: JOB_TITLE_REFUSED_BY_WRITER' and not (t.work / 'jobs' / 'ABC0015').exists(), last)
    code, _, last, jd = prepare(t, '9990014', extra={'customer_name': '=示例'})
    t.check('prepare with a job input make_job_config.py refuses: refused before any folder', code == 4
            and last == 'REFUSED: JOB_CONFIG_REFUSED' and not jd.exists(), last)


def admission(t, case, jp, tp, with_title=True):
    files = {'package_manifest': PKG / 'PACKAGE_MANIFEST.json', 'route': PKG / 'tools/cps046b_route.py', f'job_{case}': jp,
             f'source_{case}': t.paths['src'], 'glossary': t.paths['glossary']}
    if with_title:
        files[f'job_title_{case}'] = tp
    cfg = {'files': {k: str(v) for k, v in files.items()}, 'plan': {'candidate': '046g', 'note': 'invented test admission'}}
    cp = t.work / f'ADMISSION_CONFIG_{case}{"" if with_title else "_notitle"}.json'
    cp.write_text(json.dumps(cfg, ensure_ascii=False), encoding='utf-8')
    out = t.work / f'ADMISSION_{case}{"" if with_title else "_notitle"}.json'
    subprocess.run([sys.executable, '-I', '-B', str(HARNESS / 'freeze_admission.py'), '--config', str(cp), '--out', str(out)],
                   check=True, capture_output=True)
    time.sleep(0.05)
    return out


def test_qualification(t):
    """9990003 in qualification mode: admission required and checked (job_title_<case> pin); a --job-title differing
    from the title file is refused; a failed visual review stops the run; freeze writes FROZEN.json; no delivery."""
    case = '9990003'
    jp, tp = job_files(t, case)
    adm_bad = admission(t, case, jp, tp, with_title=False)
    code, _, last = t.runner('prepare', '--release', t.release_q_path, '--job', jp, '--job-title-file', tp, '--jobs-root', t.work / 'qual_A',
                             '--reader', 'A', '--qualification', '--admission', adm_bad)
    t.check('qualification prepare with an admission that does not pin the title file: refused', code == 4
            and last == 'REFUSED: ADMISSION_JOB_TITLE_PIN', last)
    code, _, last = t.runner('prepare', '--release', t.release_q_path, '--job', jp, '--job-title-file', tp, '--jobs-root', t.work / 'qual_A',
                             '--qualification')
    t.check('qualification prepare without an admission: refused', code == 4 and last == 'REFUSED: QUALIFICATION_NEEDS_ADMISSION', last)
    adm = admission(t, case, jp, tp)
    code, _, last = t.runner('prepare', '--release', t.release_q_path, '--job', jp, '--job-title-file', tp, '--jobs-root', t.work / 'qual_A',
                             '--reader', 'A', '--qualification', '--admission', adm)
    jd = t.work / 'qual_A' / case
    t.check('qualification prepare: NEXT: GENERATE', code == 0 and last.startswith('NEXT: GENERATE'), last)
    resp = stand_in_response(t, jd, case)
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--job-title', '9990003另一案')
    t.check('qualification finish with a --job-title differing from the title file: refused, nothing consumed', code == 4
            and last == 'REFUSED: JOB_TITLE_MISMATCH' and not (jd / 'response' / 'response.json').exists(), last)
    elsewhere = t.work / 'response_copy.json'
    shutil.copyfile(resp, elsewhere)
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', elsewhere)
    t.check('qualification finish with a response outside the run output folder: refused', code == 4 and last == 'REFUSED: RESPONSE_PATH', last)
    title = json.loads(tp.read_text(encoding='utf-8'))['job_title']
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', resp, '--job-title', title)
    t.check('qualification finish: NEXT: VISUAL_REVIEW', code == 0 and last.startswith('NEXT: VISUAL_REVIEW'), last)
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', stand_in_review(jd, fail=True))
    t.check('visual-record with a failed item: FAIL recorded, NEXT: STOP_VISUAL_REVIEW_FAILED', code == 3
            and last == 'NEXT: STOP_VISUAL_REVIEW_FAILED' and stages(jd, 'visual-record')[-1]['completed'], last)
    code, _, last = t.runner('deliver-check', '--job-dir', jd)
    t.check('deliver-check on a qualification job: refused', code == 4 and last == 'REFUSED: DELIVERY_NOT_FOR_QUALIFICATION', last)
    code, out, last = t.runner('freeze', '--job-dir', jd)
    fz = json.loads((jd / 'FROZEN.json').read_text(encoding='utf-8')) if (jd / 'FROZEN.json').is_file() else {}
    listed = {x['path']: x['sha256'] for x in fz.get('files', [])}
    t.check('freeze: FROZEN.json lists every file with its sha256, NEXT: DONE', code == 0 and last == 'NEXT: DONE'
            and listed.get('RUN_RECORD.json') == sha_file(jd / 'RUN_RECORD.json')
            and len(listed) == sum(1 for p in jd.rglob('*') if p.is_file() and p.name != 'FROZEN.json'), last)
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', resp)
    t.check('after freeze every subcommand is refused', code == 4 and last == 'REFUSED: JOB_FROZEN', last)


def test_route_check_failure(t):
    code, out, last, jd = prepare(t, '9990004')
    resp = stand_in_response(t, jd, '9990004', break_it=True)
    code, out, last = t.runner('finish', '--job-dir', jd, '--response', resp)
    fin = stages(jd, 'finish')
    t.check('finish with a response the route check rejects: NEXT: STOP_ROUTE_CHECK_FAILED, failure recorded, no carrier',
            code == 3 and last == 'NEXT: STOP_ROUTE_CHECK_FAILED' and fin and fin[-1]['completed'] and fin[-1]['result'] == 'ROUTE_CHECK_FAILED'
            and fin[-1]['codes'] and not (jd / 'carrier' / 'convert').exists() and (jd / 'response' / 'ROUTE_CHECK.json').is_file(), last)
    code, _, last = t.runner('finish', '--job-dir', jd, '--response', stand_in_response(t, jd, '9990004'))
    t.check('no retry after a failed route check', code == 4 and last == 'REFUSED: STAGE_ALREADY_COMPLETED', last)


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
    t.check('large workbook: prepare prints NEXT: SCOPE_READER (exit 0)', code == 0 and last.startswith('NEXT: SCOPE_READER '), last)
    t.check('large workbook: content cells above 2,500, scope tool PROPOSED', pr.get('facts', {}).get('content_cells_literal_or_cached', 0) > 2500
            and pr['facts']['scope_tool']['status'] == 'PROPOSED')
    t.check('scope reader folder holds exactly the digest and the rules excerpt; prompt filled',
            sorted(p.name for p in (jd / 'scope' / 'reader' / 'input').iterdir()) == ['SCOPE_DIGEST.json', 'SCOPE_RULES_EXCERPT.md']
            and prompt is not None and '{SCOPE_RUN}' not in prompt.read_text(encoding='utf-8') and not (jd / 'run' / 'A').exists())
    rr = scope_reader_response(jd, '9990005', end=t.large_end_row)
    code, out, last = t.runner('scope-finish', '--job-dir', jd, '--reader-response', rr)
    sf = stages(jd, 'scope-finish')[-1] if (jd / 'RUN_RECORD.json').is_file() else {}
    t.check('scope-finish with an agreeing reader: NEXT: GENERATE on the scoped packet', code == 0 and last.startswith('NEXT: GENERATE')
            and sf.get('facts', {}).get('check_inventory_scoped', {}).get('scope') == 'applied'
            and sf['facts']['scoped_verify']['status'] == 'PASS', last + json.dumps(sf.get('codes')))
    inv = jd / 'run' / 'A' / 'input' / 'packet' / 'SOURCE_INVENTORY.json'
    t.check('the generation packet is the scoped inventory (context:scope)', inv.is_file()
            and any(f['ref'] == 'context:scope' for f in json.loads(inv.read_text(encoding='utf-8'))['context_facts']))
    code, out, last, jd2 = prepare(t, '9990007', source=t.paths['large'])
    rr = scope_reader_response(jd2, '9990007', end=t.large_end_row - 1)
    code, out, last = t.runner('scope-finish', '--job-dir', jd2, '--reader-response', rr)
    t.check('scope-finish with a disagreeing reader: NEXT: OWNER_DECISION, never a tie-break', code == 3 and last == 'NEXT: OWNER_DECISION'
            and (jd2 / 'scope' / 'decision' / 'SCOPE_HOLD.json').is_file() and not (jd2 / 'run' / 'A').exists(), last)
    code, out, last, jd3 = prepare(t, '9990008', source=t.paths['large'])
    rr = scope_reader_response(jd3, '9990008', kind='engineering_stand_in', end=t.large_end_row)
    code, out, last = t.runner('scope-finish', '--job-dir', jd3, '--reader-response', rr)
    t.check('scope-finish with a reader that is not a fresh-context reader: STOP (not admissible)', code == 3
            and last == 'NEXT: STOP_SCOPE_DECISION_NOT_ADMISSIBLE', last)


def test_visual_fail_blocks_delivery(t):
    code, out, last, jd = prepare(t, '9990006')
    code, out, last = t.runner('finish', '--job-dir', jd, '--response', stand_in_response(t, jd, '9990006'))
    code, _, last = t.runner('visual-record', '--job-dir', jd, '--review', stand_in_review(jd, fail=True))
    t.check('real job: a failed visual review stops the job', code == 3 and last == 'NEXT: STOP_VISUAL_REVIEW_FAILED', last)
    code, _, last = t.runner('deliver-check', '--job-dir', jd)
    t.check('deliver-check after a failed visual review: refused', code == 4 and last == 'REFUSED: VISUAL_REVIEW_NOT_PASSED', last)


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
            sel['deliverable']['selected'] == [1, 2, 3] and sel['internal']['selected'] == [1, 2, 3, 6, 7, 8, 9], json.dumps(sel['internal']['selected']))
    sel = cj.select_pages(jd, {'deliverable': dl, 'internal': fake_manifest(u / 'b', 'M.json', mapping, main,
                                                                             clipped=[{'sheet': '來源與審查', 'cell': 'E40'}])})['workbooks']
    t.check('page selection: a possibly_clipped_cells cell on the review sheet selects every review page',
            sel['internal']['selected'] == list(range(1, 10)), json.dumps(sel['internal']['selected']))
    sel = cj.select_pages(jd, {'deliverable': dl, 'internal': fake_manifest(u / 'c', 'M.json', mapping, main,
                                                                             clipped=[{'sheet': main, 'cell': 'D2'}], clipped_count=300)})['workbooks']
    t.check('page selection: a capped clipped-cell list (pages unknown) selects every review page', sel['internal']['selected'] == list(range(1, 10)))
    sel = cj.select_pages(jd, {'deliverable': dl, 'internal': fake_manifest(u / 'e', 'M.json', mapping, main,
                                                                             clipped=[{'sheet': main, 'cell': 'D2'}])})['workbooks']
    t.check('page selection: a clipped cell on the main sheet adds no review page', sel['internal']['selected'] == [1, 2, 3, 6, 7, 8, 9])
    pages = cj.select_pages(jd, {'deliverable': dl, 'internal': fake_manifest(u / 'f', 'M.json', mapping, main)})

    def review(na):
        rv = {'schema': 'cps.visual-review.v1', 'reviewer': {'kind': 'x', 'model': 'y', 'effort': 'z'}, 'overall': 'PASS', 'failures': []}
        for key, wb in pages['workbooks'].items():
            rv[key] = {'manifest_sha256': wb['manifest_sha256'],
                       'pages': {str(p): {str(i): {'result': 'pass', 'note': ''} for i in range(1, 10)} for p in wb['selected']}}
        for key, pg, it in na:
            rv[key]['pages'][pg][it] = {'result': 'n/a', 'note': ''}
        return rv
    ok = review([('internal', '2', '1'), ('internal', '2', '6'), ('internal', '2', '7'), ('internal', '1', '8'), ('internal', '7', '8'),
                 ('deliverable', '1', '8')])
    t.check('review n/a: accepted where the item does not apply', cj.check_review(ok, pages) == ([], []), json.dumps(cj.check_review(ok, pages)))
    for key, pg, it in (('deliverable', '1', '3'), ('internal', '1', '6'), ('internal', '2', '8'), ('internal', '7', '2')):
        probs, _ = cj.check_review(review([(key, pg, it)]), pages)
        t.check(f'review n/a: refused for {key} page {pg} item {it}', any('n/a not allowed' in x for x in probs), json.dumps(probs))
    bad = review([])
    bad['internal']['manifest_sha256'] = '1' * 64
    t.check('review: a manifest sha256 that is not the rendered one is a problem', 'internal: manifest_sha256' in cj.check_review(bad, pages)[0])
    t.check('condition 5: duplicate JSON keys detected', cj.has_duplicate_keys(b'{"a": 1, "b": {"c": 1, "c": 2}}')
            and not cj.has_duplicate_keys(b'{"a": 1, "b": {"c": 1}}'))
    f = u / 'deliver.xlsx'
    f.write_bytes(b'invented workbook bytes')
    want = sha(b'invented workbook bytes')
    c, _, _ = cj.delivery_file_checks(f, want)
    t.check('condition 9: a regular single-link file with the saved-QA hash passes', all(c.values()), json.dumps(c))
    link = u / 'link.xlsx'
    os.symlink(f, link)
    c, _, _ = cj.delivery_file_checks(link, want)
    t.check('condition 9: a symbolic link to identical bytes fails', not c['regular_file'] and not c['not_symlink'], json.dumps(c))
    hard = u / 'hard.xlsx'
    os.link(f, hard)
    c, _, _ = cj.delivery_file_checks(f, want)
    t.check('condition 9: a hard link to identical bytes elsewhere fails (review N3r)', not c['single_link'] and c['sha256_equals_saved_qa'], json.dumps(c))


def test_no_private_values_printed(t):
    leaks = []
    for out in t.outputs:
        for line in out.splitlines():
            if line.startswith('NEXT: DELIVER file='):
                continue                       # the one path the runner must print: the file to deliver
            leaks += [s for s in PRIVATE_STRINGS if s in line]
    t.check('no job-input value, title or cell text in any runner output (except the delivery path)', not leaks, json.dumps(sorted(set(leaks)), ensure_ascii=False))


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
    t = T(a)
    started = time.time()
    setup(t)
    for fn in (test_units, test_prepare_refusals, test_real_job, test_node_and_tamper, test_route_check_failure, test_qualification,
               test_visual_fail_blocks_delivery, test_large, test_no_private_values_printed):
        try:
            fn(t)
        except Exception:                                  # noqa: BLE001
            t.results.append({'test': fn.__name__ + ' (raised)', 'passed': False, 'detail': traceback.format_exc()[-1500:]})
    failed = [r for r in t.results if not r['passed']]
    summary = {'schema': 'cps.job-runner-tests.v1', 'runner_sha256': sha_file(RUNNER), 'tests': len(t.results),
               'passed_count': len(t.results) - len(failed), 'failed': failed, 'seconds': round(time.time() - started, 1),
               'results': [r['test'] for r in t.results]}
    (t.work / 'TEST_RESULTS.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('tests', 'passed_count', 'failed', 'seconds')}, ensure_ascii=False, indent=1))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
