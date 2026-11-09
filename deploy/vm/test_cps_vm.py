#!/usr/bin/env python3
"""Tests of deploy/vm/cps_vm.py and deploy/vm/session_start.sh on invented data only (G1 specification, section 11).

Jobs are made with runner v4 (deploy/run/cps_job.py) through the helper, reusing deploy/run/test_cps_job.py (imported,
never edited) for the invented workbooks, stand-in responses, generation records and reviews. A FakeDrive keeps
add-only folders with paged listings; a FakeDot executes the printed lines literally (UPLOAD, SAVE_DRIVE_LISTING,
DOWNLOAD, RUN, WAIT); scenario code decides only what the Dot decides (stand-in conversation content, the option chosen,
the conversation ids, the tokens seen). Wipes delete the VM folders (everything in BASE except repo) and change the
boot id.

Usage (from a clean clone: the runner refuses a dirty tracked tree and cached bytecode):
  git clone -q <repo> W/repo && cp deploy/vm/* W/repo/deploy/vm/ && \
  python3 -I -B W/repo/deploy/vm/test_cps_vm.py --work W/run [--node /opt/node22/bin/node] [--node-sha256 HEX]
      [--node-path /opt/node-tools/node_modules] [--only NAME,...] [--keep]
Prints the summary JSON (cps.vm-helper-tests.v1) and writes <work>/TEST_RESULTS.json. Exit 0 when every test passes.
"""
import argparse, hashlib, importlib.util, json, os, re, shlex, shutil, signal, stat, subprocess, sys, time, traceback, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HELPER = HERE / 'cps_vm.py'
SESSION_SH = HERE / 'session_start.sh'
RUNNER = REPO / 'deploy' / 'run' / 'cps_job.py'
TOKENS = ('CONVERSATION_ID', 'GENERATOR_MODEL', 'COPY_FILE', 'LOG_FILE', 'PROFILE_FOLDER', 'CASE', 'REASON_TEXT', 'SEEN')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


tcj = load(REPO / 'deploy' / 'run' / 'test_cps_job.py', 'test_cps_job_v4')
vm = load(HELPER, 'cps_vm_under_test')
cj = vm.load_runner()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    return sha(Path(p).read_bytes())


def md5(b):
    return hashlib.md5(b, usedforsecurity=False).hexdigest()


# ------------------------------------------------------------------ results
class T:
    def __init__(self, a):
        self.a, self.work = a, Path(a.work)
        self.results, self.outputs = [], []
        self.titles = set()
        self.deliverables = set()       # r2 R2-07: basenames of every deliverable written in a world (leak scan)

    def check(self, name, cond, detail=''):
        try:
            ok = bool(cond() if callable(cond) else cond)
        except Exception as e:                              # noqa: BLE001
            ok, detail = False, f'raised {type(e).__name__}: {e}'[:600]
        if not ok and callable(detail):
            try:
                detail = detail()
            except Exception as e:                          # noqa: BLE001
                detail = f'detail raised {type(e).__name__}'
        self.results.append({'test': name, 'passed': ok, 'detail': '' if ok else str(detail)[:2000]})
        if not ok:
            print('FAIL', name, str(detail)[:600], file=sys.stderr, flush=True)
        return ok


# ------------------------------------------------------------------ FakeDrive
class Drive:
    """Add-only folders: every upload is a new id, duplicate names are allowed, nothing is replaced or deleted."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.root / '_meta.json'
        self.meta = json.loads(self.meta_path.read_text()) if self.meta_path.is_file() else {'n': 0, 'files': [], 'last': 0.0}
        self.hide, self.drop_last_page, self.page = set(), False, 50
        self.t = None                   # r2 R2-07: set by World; a zero-byte upload is a failed check

    def save(self):
        self.meta_path.write_text(json.dumps(self.meta))

    def put(self, folder, name, data, mime=None):
        if self.t is not None and not data:
            self.t.check('11.7: Drive rejects a zero-byte upload: ' + name, False)
            return None
        self.meta['n'] += 1
        fid = f'fid{self.meta["n"]:06d}'
        t = max(time.time(), self.meta['last'] + 0.001)
        self.meta['last'] = t
        p = self.root / fid
        blob = self.root / '_blobs' / sha(data)
        if not blob.exists():
            blob.parent.mkdir(exist_ok=True)
            blob.write_bytes(data)
            os.chmod(blob, 0o444)
        os.link(blob, p)
        e = {'id': fid, 'name': name, 'folder': folder, 'created': vm.iso(vm.datetime.datetime.fromtimestamp(t, vm.datetime.timezone.utc)),
             'md5': md5(data), 'size': len(data)}
        if mime:
            e['mimeType'] = mime
        self.meta['files'].append(e)
        self.save()
        return e

    def files(self, folder, name=None):
        return [f for f in self.meta['files'] if f['folder'] == folder and (name is None or f['name'] == name) and f['id'] not in self.hide]

    def data(self, fid):
        return (self.root / fid).read_bytes()

    def by_name(self, folder, name):
        return [f for f in self.files(folder) if f['name'] == name]

    def listing(self, folder, to, name=None):
        fs = [{'name': f['name'], 'id': f['id'], 'createdTime': f['created'], 'md5Checksum': f['md5'], 'size': str(f['size']),
               **({'mimeType': f['mimeType']} if f.get('mimeType') else {'mimeType': 'application/octet-stream'})}
              for f in self.files(folder, name)]
        pages = []
        for i in range(0, max(1, len(fs)), self.page):
            pages.append({'kind': 'drive#fileList', 'files': fs[i:i + self.page]})
        for i in range(len(pages) - 1):
            pages[i]['nextPageToken'] = f'tok{i + 1}'
        if self.drop_last_page and len(pages) > 1:
            pages = pages[:-1]
        d = {'schema': 'cps.vm-drive-listing.v1', 'folder': folder, 'name_filter': name, 'pages': pages}
        Path(to).parent.mkdir(parents=True, exist_ok=True)
        Path(to).write_text(json.dumps(d))

    def copy_to(self, root):
        """A copy of the drive (hard links: the files are immutable)."""
        root = Path(root)
        root.mkdir(parents=True)
        for f in self.root.iterdir():
            if f.name == '_meta.json':
                shutil.copyfile(f, root / f.name)
            elif f.name == '_blobs':
                (root / '_blobs').mkdir()
                for g in f.iterdir():
                    os.link(g, root / '_blobs' / g.name)
            else:
                os.link(f, root / f.name)
        d = Drive(root)
        d.t = self.t
        return d

    def flat(self, folder, dest):
        """Download a whole folder flat (the maintainer's view): the newest copy of each name."""
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        for f in self.files(folder):
            shutil.copyfile(self.root / f['id'], dest / f['name'])
        return dest


# ------------------------------------------------------------------ worlds (one BASE, TOOLS and FakeDrive each)
FOLDERS = {'setup': 'CPS/setup', 'qualification': 'CPS/qualification', 'everyday': 'Dots Folder/CPS_JOB_RECORDS'}
HEAD = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
MODEL = 'invented-dot-model'


def default_config(sentinels):
    return {'schema': 'cps.vm-helper-config.v1', 'drive': dict(FOLDERS), 'png_part_bytes': 4_000_000,
            'upload_verification': 'download', 'link_notes': True, 'selftest_expected_tests': 600,
            'audit_clock_tolerance_seconds': 60, 'listing_page_marker': 'required', 'sentinels': sentinels,
            'expected_genesis': None, 'confirm_package_before_start': True, 'confirm_ai_before_consume': True,
            'transcript_export': True, 'max_upload_bytes': 45_000_000, 'max_review_revisions': 2,
            'clock_wait_max_seconds': 600, 'wrap_foreground_seconds': 240}


class World:
    def __init__(self, t, name, mode='qualification', cases=(), nonattempts=(), large=(), cfg=None, repo=None, put_sentinels=True):
        self.t, self.name, self.mode = t, name, mode
        self.root = t.work / name
        self.base, self.tools, self.home = self.root / 'base', self.root / 'tools', self.root / 'home'
        for d in (self.base, self.tools, self.home):
            d.mkdir(parents=True)
        self.repo = Path(repo or REPO)
        self.head = HEAD if repo is None else subprocess.run(['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], capture_output=True,
                                                             text=True).stdout.strip()
        os.symlink(self.repo, self.base / 'repo')
        self.drive = Drive(self.root / 'drive')
        self.drive.t = t
        self.boot_path = self.root / 'boot_id'
        self.new_boot()
        self.cases, self.nonattempts, self.large = list(cases), list(nonattempts), set(large)
        self.make_tools()
        self.env = dict(os.environ, HOME=str(self.home), CPS_VM_BASE=str(self.base), CPS_TOOLS=str(self.tools),
                        CPS_VM_BOOT_ID_PATH=str(self.boot_path))
        self.env.pop('PYTHONPATH', None)
        self.static = self.root / 'cps_static'
        self.sentinels = {}
        for k in ('setup', 'qualification', 'everyday'):
            data = json.dumps({'sentinel': k, 'world': name, 'invented': True}).encode() + b'\n'
            nm = f'SENTINEL_{k}_{sha(data)[:8]}.json'
            self.sentinels[k] = {'name': nm, 'md5': md5(data), 'upload_by_dot': False, 'data': data}
        for k in ('setup', mode):
            if put_sentinels or k == 'setup':
                self.drive.put(FOLDERS[k], self.sentinels[k]['name'], self.sentinels[k]['data'])
        self.cfg = default_config({k: {x: v[x] for x in ('name', 'md5', 'upload_by_dot')} for k, v in self.sentinels.items()})
        if not put_sentinels:
            self.cfg['sentinels'][mode]['upload_by_dot'] = True
        self.cfg.update(cfg or {})
        self.kit_n = 0
        self.build_kit()
        self.write_vm_sh()
        self.records = FOLDERS['qualification' if mode == 'qualification' else 'everyday']

    def new_boot(self):
        self.boot = os.urandom(16).hex()
        self.boot_path.write_text(self.boot + '\n')

    def make_tools(self):
        site = Path(importlib.util.find_spec('openpyxl').origin).resolve().parents[1]
        (self.tools / 'builder-deps' / 'private').mkdir(parents=True)
        os.symlink(site, self.tools / 'builder-deps' / 'private' / 'deps')
        (self.tools / 'playwright').mkdir()
        os.symlink(self.t.a.node_path, self.tools / 'playwright' / 'node_modules')
        (self.tools / 'node' / 'bin').mkdir(parents=True)
        os.symlink(self.t.a.node, self.tools / 'node' / 'bin' / 'node')
        (self.tools / 'var').mkdir()
        (self.tools / 'env.sh').write_text(
            f'# invented test toolchain\nexport PATH="{self.tools}/node/bin:${{PATH:-/usr/bin:/bin}}"\n'
            f'export NODE_PATH="{self.t.a.node_path}"\nexport CPS_PLAYWRIGHT_NODE_PATH="{self.tools}/playwright/node_modules"\n')

    def write_vm_sh(self):
        (self.base / 'vm.sh').write_text(f'#!/bin/bash\n. "{self.tools}/env.sh"\nexport TMPDIR=/tmp\n'
                                         f'exec python3 -I -B "{self.base}/repo/deploy/vm/cps_vm.py" "$@"\n')
        os.chmod(self.base / 'vm.sh', 0o755)

    @property
    def V(self):
        return str(self.base / 'vm.sh')

    # ---- the session kit (what the maintainer's G2 builder would make)
    def build_kit(self, cfg_only=False, mutate=None):
        rt = self.base / 'runtime'
        src = self.root / 'kit_src'
        files = {}
        if not cfg_only:
            if src.exists():
                shutil.rmtree(src)
            src.mkdir()
            wb = src / 'small.xlsx'
            glossary = tcj.small_workbook(wb)
            files['tables/GLOSSARY.json'] = (json.dumps(glossary, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
            if self.large:
                tcj.large_workbook(src / 'large.xlsx')
            self.large_end_row = 3 + 450
            jobs = {'schema': 'cps.qualification-jobs.v1', 'meaning': 'INVENTED test jobs list', 'cases': []}
            order = 0
            for c in self.cases:
                order += 1
                jobs['cases'].append({'case_id': c, 'order': order, 'nonattempt': False})
                if self.mode == 'qualification':
                    jd = f'qualification/jobs/{c}'
                    srcb = (src / ('large.xlsx' if c in self.large else 'small.xlsx')).read_bytes()
                    files[f'{jd}/source.xlsx'] = srcb
                    files[f'{jd}/JOB.json'] = self.job_json(c, rt / jd / 'source.xlsx', rt / 'tables' / 'GLOSSARY.json')
                    files[f'{jd}/JOB_TITLE.json'] = self.title_json(c)
            for c in self.nonattempts:
                order += 1
                jobs['cases'].append({'case_id': c, 'order': order, 'nonattempt': True, 'reason': 'NONATTEMPT_SOURCE_UNAVAILABLE'})
            if self.mode == 'qualification':
                files['qualification/JOBS.json'] = (json.dumps(jobs, ensure_ascii=False, indent=1) + '\n').encode()
                for k, v in files.items():
                    (src / k).parent.mkdir(parents=True, exist_ok=True)
                    (src / k).write_bytes(v)
                pins = {'package_manifest': tcj.PKG / 'PACKAGE_MANIFEST.json', 'route': tcj.PKG / 'tools/cps046b_route.py',
                        'glossary': src / 'tables/GLOSSARY.json', 'JOBS.json': src / 'qualification/JOBS.json'}
                for c in self.cases:
                    pins[f'job_{c}'] = src / f'qualification/jobs/{c}/JOB.json'
                    pins[f'source_{c}'] = src / f'qualification/jobs/{c}/source.xlsx'
                    pins[f'job_title_{c}'] = src / f'qualification/jobs/{c}/JOB_TITLE.json'
                pins.update({k: self.repo / k for k in tcj.ADMISSION_TOOL_LABELS})
                cp = src / 'adm_cfg.json'
                cp.write_text(json.dumps({'files': {k: str(v) for k, v in pins.items()}, 'plan': {'candidate': '046g', 'note': 'invented'}}))
                ap = src / 'ADMISSION.json'
                subprocess.run([sys.executable, '-I', '-B', str(tcj.HARNESS / 'freeze_admission.py'), '--config', str(cp), '--out', str(ap)],
                               check=True, capture_output=True)
                files['qualification/ADMISSION_QUALIFICATION.json'] = ap.read_bytes()
                time.sleep(0.05)
            self.kit_files = files
        files = dict(self.kit_files)
        gl = files['tables/GLOSSARY.json']
        rel = {'schema': 'cps.release.v1', 'status': 'RELEASED_FOR_QUALIFICATION' if self.mode == 'qualification' else 'RELEASED_FOR_USE',
               'release_version': 'TEST-VM-' + self.name, 'repository': {'commit': self.head, 'root': str(self.base / 'repo')},
               'package': {'path': 'research/guideline046_007/package', 'manifest_sha256': sha_file(tcj.PKG / 'PACKAGE_MANIFEST.json')},
               'harness': {'path': 'research/guideline046_007/harness'},
               'source_prep': {'path': 'research/guideline046_003/source_prep', 'deps_bundle': str(self.tools / 'builder-deps'),
                               'node_path': str(self.tools / 'playwright' / 'node_modules')},
               'writer': {'admission': tcj.WRITER_ADMISSION, 'admission_sha256': sha_file(REPO / tcj.WRITER_ADMISSION),
                          'writer_dir': str(REPO / 'deploy/writer_route/writer')},
               'checker_node': {'path': str(self.tools / 'node' / 'bin' / 'node'), 'sha256': self.t.a.node_sha256},
               'admitted_checker_node_sha256': [self.t.a.node_sha256],
               'tables': {'glossary': {'path': str(rt / 'tables/GLOSSARY.json'), 'sha256': sha(gl)}, 'brand_table': None,
                          'company_name_sha256': sha(tcj.COMPANY.encode('utf-8'))},
               'pinned_files_sha256': {p: sha_file(self.repo / p) for p in tcj.EXECUTED + ['deploy/vm/cps_vm.py', 'deploy/vm/session_start.sh']}}
        if self.mode == 'qualification':
            rel['qualification'] = {'admissions': [{'path': str(rt / 'qualification/ADMISSION_QUALIFICATION.json'),
                                                    'sha256': sha(files['qualification/ADMISSION_QUALIFICATION.json'])}],
                                    'ledger': str(self.base / 'ledger' / 'LEDGER.jsonl'), 'jobs_file': str(rt / 'qualification/JOBS.json')}
        if mutate:
            mutate(rel)
        files['RELEASE.json'] = (json.dumps(rel, ensure_ascii=False, indent=1) + '\n').encode()
        files['VM_HELPER_CONFIG.json'] = (json.dumps(self.cfg, indent=1) + '\n').encode()
        for k, v in self.sentinels.items():
            files['sentinels/' + v['name']] = v['data']
        sums = ''.join(f'{sha(v)}  {k}\n' for k, v in sorted(files.items()))
        self.kit_n += 1
        kname = f'SESSION_KIT_TEST{self.kit_n}.zip'
        (self.static / 'cps_runtime').mkdir(parents=True, exist_ok=True)
        kp = self.static / 'cps_runtime' / kname
        with zipfile.ZipFile(kp, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('SHA256SUMS', sums)
            for k, v in sorted(files.items()):
                z.writestr(k, v)
        kb = kp.read_bytes()
        (self.static / 'FOLDER_MANIFEST.md').write_text(
            '# Folder manifest (invented test)\n\n| Path | Bytes | sha256 |\n|---|---:|---|\n'
            f'| `cps_runtime/{kname}` | {len(kb)} | `{sha(kb)}` |\n')
        return kp

    def job_json(self, c, source, glossary):
        job = {'schema': 'cps.job-config.v2', 'case_id': c, 'customer_name': tcj.CUSTOMER, 'project_name': tcj.PROJECT,
               'company_name': tcj.COMPANY, 'glossary_path': str(glossary), 'source_path': str(source), 'source_kind': '材料清單',
               'carrier_path': f'X:\\Fixtures\\invented\\{c}-material-list.xlsx'}
        return (json.dumps(job, ensure_ascii=False, indent=1) + '\n').encode('utf-8')

    def title_json(self, c):
        title = f'{c}示例公司-示例案'
        self.t.titles.add(title)
        return (json.dumps({'schema': 'cps.job-title.v1', 'case_id': c, 'job_title': title}, ensure_ascii=False, indent=1) + '\n').encode('utf-8')

    # ---- VM events
    def wipe(self):
        """Simulated VM reset: everything in BASE except repo goes; a new boot id. TOOLS stands for a re-run setup."""
        for p in list(self.base.iterdir()):
            if p.name == 'repo':
                continue
            vm.remove_tree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
        self.write_vm_sh()
        self.new_boot()

    def job_dir(self, tag, case):
        return self.base / 'qual' / vm.QUAL_ROOTS[tag] / case if tag in vm.QUAL_ROOTS else self.base / 'jobs' / tag[1:] / case

    def snapshot(self):
        """Every path under BASE (repo excluded) with its type and content hash, for 'nothing written' checks."""
        out = {}
        for dp, dns, fns in os.walk(self.base):
            if Path(dp) == self.base:
                dns[:] = [d for d in dns if d != 'repo']
            for n in dns + fns:
                p = Path(dp) / n
                r = str(p.relative_to(self.base))
                out[r] = 'dir' if p.is_dir() and not p.is_symlink() else sha_file(p) if p.is_file() else 'other'
        return out


# ------------------------------------------------------------------ FakeDot
LINE_RE = {
    'UPLOAD': re.compile(r'^UPLOAD (.+) -> (.+)$'),
    'SAVE': re.compile(r'^SAVE_DRIVE_LISTING folder=(.+?) to=(\S+)(?: name=(\S+))?$'),
    'DOWNLOAD': re.compile(r'^DOWNLOAD id=(\S+) name=(\S+) -> (\S+)$'),
}
PREFIXES = ('RESULT: ', 'BIND=', 'UPLOAD ', 'SAVE_DRIVE_LISTING ', 'DOWNLOAD ', 'STATE: ', 'NEXT: ', 'THEN: ', 'OPTION: ', 'STOP: ',
            'REFUSED: ', 'RUNNER| ', 'setup: ')


class Out:
    def __init__(self, code, text, cmd):
        self.code, self.text, self.cmd = code, text, cmd
        self.lines = [ln for ln in text.splitlines() if ln.strip()]
        self.result, self.bind, self.uploads, self.fetch, self.actions, self.options = {}, None, [], [], [], []
        self.stop = self.refused = None
        self.state = {}
        for ln in self.lines:
            if ln.startswith('RESULT: '):
                self.result = json.loads(ln[8:])
            elif ln.startswith('BIND='):
                self.bind = ln[5:]
            elif ln.startswith('UPLOAD '):
                self.uploads.append(ln)
            elif ln.startswith(('SAVE_DRIVE_LISTING ', 'DOWNLOAD ')):
                self.fetch.append(ln)
            elif ln.startswith(('NEXT: ', 'THEN: ')):
                self.actions.append(ln.split(': ', 1)[1])
            elif ln.startswith('OPTION: '):
                code, act = ln[8:].split(' ', 1)
                self.options.append((code, act))
            elif ln.startswith('STOP: '):
                self.stop = ln[6:].split(' ')[0]
            elif ln.startswith('REFUSED: '):
                self.refused = ln[9:].split(' ')[0]
            elif ln.startswith('STATE: '):
                self.state = dict(x.split('=', 1) for x in ln[7:].split(' ') if '=' in x)

    @property
    def codeword(self):
        return self.refused or self.stop or self.result.get('code')

    def __repr__(self):
        return f'<Out {self.cmd[:80]!r} exit={self.code} {self.codeword} next={self.actions[:2]}>'


class Dot:
    def __init__(self, w):
        self.w, self.t = w, w.t
        self.pending_tokens = []       # BIND tokens seen since the job's newest package upload succeeded
        self.values = {'GENERATOR_MODEL': 'stand-in (invented test)', 'PROFILE_FOLDER': 'Dots Folder/Profiles/invented-user'}
        self.skip_upload = None        # predicate(name) -> True: the upload fails (the Dot stops after 3 attempts)
        self.truncate_upload = None    # predicate(name) -> True: a partial copy lands (then the retry lands whole)
        self.late = []                 # uploads held back to land later
        self.conv = {}                 # role -> callable(jd, case, role, attempt)
        self.history = []
        self.stop_before_upload = None  # (prefix, cmd part): the VM is wiped before these uploads happen
        self.stop_after_upload = None   # (prefix, cmd part): stop the autopilot right after these uploads
        self.halted = None

    # ---- raw execution
    def call(self, argv, check_grammar=True):
        p = subprocess.run(argv, capture_output=True, env=dict(self.w.env, **getattr(self, 'env_extra', {})), timeout=3600)
        text = p.stdout.decode('utf-8', 'replace')
        self.t.outputs.append(text)
        for root in (self.w.base / 'qual', self.w.base / 'jobs'):
            if root.is_dir():
                self.t.deliverables |= {x.name for x in root.glob('*/*/export/writer/*.xlsx')}
        o = Out(p.returncode, text, ' '.join(str(a) for a in argv))
        self.history.append(o)
        if check_grammar:
            self.grammar(o, p.stderr.decode('utf-8', 'replace'))
        return o

    def grammar(self, o, err):
        bad = [ln for ln in o.lines if not ln.startswith(PREFIXES)]
        term = bool(o.actions) or o.stop or o.refused
        ok = not bad and (o.result or o.code == 2) and term and not (o.refused and (o.uploads or o.actions))
        for a in o.actions + [x[1] for x in o.options]:
            if 'RUN ' in a:
                cmd = a[a.index('RUN ') + 4:]
                if '<' in cmd or any(t not in TOKENS for t in re.findall(r'\{([A-Z_]+)\}', cmd)):
                    ok = False
        if not ok:
            self.t.check(f'grammar of {o.cmd[-90:]}', False, (o.text[-1500:] + '\nSTDERR ' + err[-1500:]))

    def vm(self, *args, **kw):
        return self.do(self.call([self.w.V, *[str(a) for a in args]]), **kw)

    def run_line(self, cmd, **kw):
        for k in TOKENS:
            if '{' + k + '}' in cmd:
                v = self.values.get(k)
                assert v is not None and not v.startswith('<') and "'" not in v and '\n' not in v, k
                cmd = cmd.replace('{' + k + '}', v)
        argv = shlex.split(cmd)
        if argv and argv[0] == 'bash':
            return self.do(self.call(argv), **kw)
        return self.do(self.call(argv), **kw)

    # ---- the printed lines
    def matches(self, spec, o):
        if not spec:
            return False
        prefix, part = spec
        return any(Path(LINE_RE['UPLOAD'].match(u).group(1)).name.startswith(prefix) for u in o.uploads) and (part is None or part in o.cmd)

    def do(self, o, uploads=True, fetch=True):
        if o.bind and o.bind != 'none':
            self.pending_tokens.append(o.bind)
        if self.matches(self.stop_before_upload, o):
            self.stop_before_upload, self.halted = None, o
            return o
        if self.matches(self.stop_after_upload, o):
            self.stop_after_upload, self.halted = None, o
        if uploads:
            for ln in o.uploads:
                m = LINE_RE['UPLOAD'].match(ln)
                path, folder = m.group(1), m.group(2)
                if path.startswith('{'):
                    path = self.values[path.strip('{}')]
                p = Path(path)
                self.t.check('UPLOAD path exists: ' + p.name, p.is_file())
                if self.skip_upload and self.skip_upload(p.name):
                    continue
                data = p.read_bytes()
                if self.truncate_upload and self.truncate_upload(p.name):
                    self.w.drive.put(folder, p.name, data[:max(1, len(data) // 2)])
                    self.truncate_upload = None
                if any(h(p.name) for h in self.late):
                    self.held = getattr(self, 'held', []) + [(folder, p.name, data)]
                    continue
                self.w.drive.put(folder, p.name, data)
                if re.match(r'^(CP|FZ)_', p.name):
                    self.pending_tokens = []
        if fetch:
            self.fetch(o)
        return o

    def fetch(self, o):
        for ln in o.fetch:
            m = LINE_RE['SAVE'].match(ln)
            if m:
                self.w.drive.listing(m.group(1), m.group(2), m.group(3))
                continue
            m = LINE_RE['DOWNLOAD'].match(ln)
            fid, name, to = m.group(1), m.group(2), Path(m.group(3))
            to.parent.mkdir(parents=True, exist_ok=True)
            if fid == 'CPS_FOLDER_PATH':
                shutil.copyfile(self.w.static / name, to)
            else:
                to.write_bytes(self.w.drive.data(fid))

    def land_late(self):
        for folder, name, data in getattr(self, 'held', []):
            self.w.drive.put(folder, name, data)
        self.held = []

    # ---- session start (README 9.1, S1-S6)
    def session(self, max_rounds=12):
        inbox = self.w.base / 'inbox'
        if (inbox / 'cps').exists():
            shutil.rmtree(inbox / 'cps')
        (inbox / 'cps').mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.w.static / 'FOLDER_MANIFEST.md', inbox / 'cps' / 'FOLDER_MANIFEST.md')
        self.w.drive.listing(self.w.records, inbox / 'DRIVE_LISTING.json')
        self.w.drive.listing(FOLDERS['setup'], inbox / 'SETUP_LISTING.json')
        for _ in range(max_rounds):
            o = self.do(self.call([self.w.V, 'session', '--inbox', str(inbox), '--operator-model', MODEL]))
            if o.code != 10:
                return o
            for a in o.actions:
                if a.startswith('WAIT until='):
                    self.wait_until(a.split('=', 1)[1])
        return o

    def wait_until(self, t):
        dt = vm.parse_utc(t)
        while vm.now_dt() < dt:
            time.sleep(0.2)

    # ---- the autopilot: follow NEXT and THEN like the Dot
    def find_job(self, path):
        p = Path(path)
        for q in [p] + list(p.parents):
            if (q / 'RUN_RECORD.json').is_file():
                return q
        return None

    def converse(self, role, prompt):
        jd = self.find_job(prompt)
        rec = json.loads((jd / 'RUN_RECORD.json').read_text(encoding='utf-8'))
        case, reader = rec['case_id'], rec['reader']
        n = sum(1 for o in self.history if o.result.get('command') == 'start-note' and o.code == 0 and f'--role {role}' in o.cmd)
        self.values['CONVERSATION_ID'] = f'invented-conv-{case}-{role}-{n}'
        hook = self.conv.get(role)
        if hook is not None:
            return hook(jd, case, role, reader)
        if role == 'S':
            tcj.scope_reader_response(jd, case, end=self.w.large_end_row)
        elif role == 'G':
            tcj.stand_in_response(None, jd, case, reader=reader)
        else:
            tcj.stand_in_review(jd, reviewer=dict(tcj.REVIEWER, conversation_id=self.values['CONVERSATION_ID']))

    def auto(self, o, halt=None, choose=None, max_steps=80):
        """Follow the printed actions until halt(action, out) is true or the lines end in a decision for the scenario."""
        last_run, repeats = None, 0
        for _ in range(max_steps):
            if o.code == 10 and not o.actions:
                return o
            acts = list(o.actions)
            nxt = None
            if o.stop and not acts:
                return o
            if o.refused:
                return o
            for a in acts:
                if halt and halt(a, o):
                    return o
                if a.startswith('RUN '):
                    repeats = repeats + 1 if a[4:] == last_run else 0
                    if repeats >= 4 and not a.endswith(' wait'):
                        self.t.check('autopilot: a RUN line repeated without progress: ' + a[-120:], False, o.text[-1500:])
                        return o
                    last_run = a[4:]
                    nxt = self.run_line(a[4:])
                    break
                if a == 'RUN_SAME_COMMAND_AGAIN' and last_run:
                    nxt = self.run_line(last_run)
                    break
                if a.startswith('OPEN_CONVERSATION'):
                    kv = dict(x.split('=', 1) for x in a.split(' ')[1:])
                    self.converse(kv['role'], kv['prompt'])
                    continue
                if a.startswith(('WAIT_FOR_CONVERSATION', 'CONFIRM_CONVERSATION_ENDED', 'CONTINUE_CONVERSATION', 'TELL_MAINTAINER')):
                    if a.startswith('CONTINUE_CONVERSATION') and self.conv.get('V-continue'):
                        self.conv['V-continue']()
                    continue
                if a.startswith('WRITE_GENERATION_RECORD'):
                    jd = self.find_job(a.split('path=')[1].split(' ')[0])
                    rec = json.loads((jd / 'RUN_RECORD.json').read_text(encoding='utf-8'))
                    tcj.generation_record(jd, rec['case_id'], reader=rec['reader'])
                    continue
                if a.startswith('EXPORT_TRANSCRIPT'):
                    to = Path(a.split('to=')[1])
                    to.parent.mkdir(parents=True, exist_ok=True)
                    to.write_text('invented transcript: the conversation wrote nothing\n')
                    continue
                if a.startswith('WAIT until='):
                    self.wait_until(a.split('=', 1)[1])
                    continue
                if a.startswith(('CHOOSE_', 'ASK_USER')):
                    code = choose(o) if choose else self.default_choice(o)
                    act = dict(o.options)[code]
                    if act.startswith('RUN '):
                        if '{SEEN}' in act:
                            self.values['SEEN'] = ','.join(self.pending_tokens)
                        last_run = act[4:]
                        nxt = self.run_line(act[4:])
                        break
                    return o
                return o
            if nxt is None:
                return o
            o = nxt
            if self.halted is not None:
                self.halted = None
                return o
        return o

    def default_choice(self, o):
        codes = [c for c, _ in o.options]
        if 'SEEN' in codes:
            return 'SEEN' if self.pending_tokens else 'NOT_SEEN'
        if 'NOTHING_WRITTEN' in codes:
            return 'NOTHING_WRITTEN'
        if 'RECEIVED' in codes:
            return 'RECEIVED'
        if 'SEND_NOW' in codes:
            return 'SEND_NOW'
        return codes[0]


def until_upload(prefix, cmd_part=None):
    """A halt predicate: stop before the Dot acts on the output whose UPLOAD lines include a file named prefix*."""
    def h(a, o):
        return any(Path(LINE_RE['UPLOAD'].match(u).group(1)).name.startswith(prefix) for u in o.uploads) and \
            (cmd_part is None or cmd_part in o.cmd)
    return h


def at_action(prefix):
    def h(a, o):
        return a.startswith(prefix)
    return h


def names(drive, folder, prefix=''):
    return [f['name'] for f in drive.files(folder) if f['name'].startswith(prefix)]


# ------------------------------------------------------------------ helpers for scenarios
def fake_selftest(w, ok=True):
    """E1: the self-test is faked by a results file with the expected tests, as the suite would write it."""
    st = json.loads((w.base / 'outbox' / 'SESSION_STATE.json').read_text())
    d = w.base / 'outbox' / f'selftest_{vm.utc14()}'
    (d / 'work').mkdir(parents=True)
    exp = REPO / 'research' / 'export'
    summary = {'suite': 'cps-export-portable-writer-tests.v6', 'tests': 600, 'passed_count': 600 if ok else 599, 'failed_count': 0 if ok else 1,
               'failed': [], 'visual_skipped': False, 'writer_portable_sha256': sha_file(exp / 'writer_portable.py'),
               'saved_qa_sha256': sha_file(exp / 'saved_qa.py'), 'visual_qa_sha256': sha_file(exp / 'visual_qa.py'),
               'checker_node': {'realpath': os.path.realpath(w.t.a.node), 'sha256': w.t.a.node_sha256}}
    (d / 'work' / 'EXPORT_TEST_RESULTS.json').write_text(json.dumps({'summary': summary, 'results': []}))
    run = {'fingerprint_before_sha256': st['fingerprint_sha256'], 'commit': HEAD, 'session_note': st['session_note'],
           'started_utc': vm.utc(), 'work_dir': str(d / 'work'), 'exit': 0 if ok else 1, 'ended_utc': vm.utc(), 'pid': 1}
    (d / 'RUN.json').write_text(json.dumps(run))


def state(w):
    return json.loads((w.base / 'outbox' / 'SESSION_STATE.json').read_text())


def ledger_entries(w):
    p = w.base / 'ledger' / 'LEDGER.jsonl'
    return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()] if p.is_file() else []


def start_world(t, dot, w):
    """Fresh session, faked self-test, fingerprint-pass: returns the fingerprint-pass output."""
    o = dot.session()
    t.check(f'{w.name}: fresh session asks for the self-test', lambda: o.code == 0 and o.result.get('mode') == 'fresh'
            and o.actions and o.actions[0].endswith(' selftest'), o)
    fake_selftest(w)
    return dot.vm('fingerprint-pass')


# ------------------------------------------------------------------ main
SCENARIOS = []


def scenario(fn):
    SCENARIOS.append(fn)
    return fn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--node', default='/opt/node22/bin/node')
    ap.add_argument('--node-sha256', default='2286ce921a47349726b0e8b037ccbb6627043d24d1fc3c8f22c2dc53c4a1f7ff')
    ap.add_argument('--node-path', default='/opt/node-tools/node_modules')
    ap.add_argument('--writer-dir', default=str(REPO / 'deploy/writer_route/writer'))
    ap.add_argument('--only', default='')
    ap.add_argument('--keep', action='store_true')
    a = ap.parse_args()
    if not Path(a.work).is_absolute():
        ap.error('--work must be absolute')
    dirty = subprocess.run(['git', '-C', str(REPO), 'status', '--porcelain', '--untracked-files=no'], capture_output=True, text=True)
    if dirty.returncode != 0 or dirty.stdout.strip():
        print(json.dumps({'error': 'run from a clean checkout: the runner refuses a dirty tracked tree'}))
        return 2
    pyc = cj.pycache_entries([REPO / 'research', REPO / 'deploy' / 'run'])
    if pyc:
        print(json.dumps({'error': 'cached bytecode in a runner-scanned folder (PYCACHE_PRESENT): run from a clean clone', 'first': pyc[:3]}))
        return 2
    before = subprocess.run(['git', '-C', str(REPO), 'status', '--porcelain', '--untracked-files=all'], capture_output=True, text=True).stdout
    t = T(a)
    t.work.mkdir(parents=True, exist_ok=False)
    started = time.time()
    only = [x for x in a.only.split(',') if x]
    timings = {}
    for fn in SCENARIOS:
        if only and fn.__name__ not in only:
            continue
        t0 = time.time()
        n0 = len([r for r in t.results if not r['passed']])
        try:
            fn(t)
        except Exception:                                   # noqa: BLE001
            t.results.append({'test': fn.__name__ + ' (raised)', 'passed': False, 'detail': traceback.format_exc()[-3000:]})
            print('RAISED', fn.__name__, traceback.format_exc()[-3000:], file=sys.stderr, flush=True)
        timings[fn.__name__] = round(time.time() - t0, 1)
        failed_here = len([r for r in t.results if not r['passed']]) > n0
        print(f'{fn.__name__}: {timings[fn.__name__]} s{" FAILED" if failed_here else ""}', file=sys.stderr, flush=True)
        if not a.keep and not failed_here:
            for d in list(t.work.iterdir()):
                if d.is_dir() and d.name.startswith(fn.__name__ + '_'):
                    vm.remove_tree(d)
    hygiene(t, before)
    failed = [r for r in t.results if not r['passed']]
    summary = {'schema': 'cps.vm-helper-tests.v1', 'helper_sha256': sha_file(HELPER), 'runner_sha256': sha_file(RUNNER),
               'tests': len(t.results), 'passed_count': len(t.results) - len(failed), 'failed': failed,
               'seconds': round(time.time() - started, 1), 'scenario_seconds': timings}
    (t.work / 'TEST_RESULTS.json').write_text(json.dumps(dict(summary, results=[r['test'] for r in t.results]), ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({k: summary[k] for k in ('tests', 'passed_count', 'failed', 'seconds')}, ensure_ascii=False, indent=1))
    return 0 if not failed else 1


def hygiene(t, before):
    leaks = set()
    for out in t.outputs:
        for s_ in list(tcj.PRIVATE_STRINGS) + sorted(t.titles) + sorted(t.deliverables):
            if s_ in out:
                leaks.add(s_)
    t.check('11.7: no helper output holds a private value, a job title or the deliverable name', lambda: not leaks,
            lambda: json.dumps(sorted(leaks), ensure_ascii=False))
    after = subprocess.run(['git', '-C', str(REPO), 'status', '--porcelain', '--untracked-files=all'], capture_output=True, text=True).stdout
    t.check('11.7: git status is unchanged by the suite', lambda: after == before, lambda: after[:500])
    t.check('11.7: no __pycache__ under deploy/vm', lambda: not (HERE / '__pycache__').exists())


# ------------------------------------------------------------------ E1, E2: fresh session, genesis, nonattempts; the ledger after a wipe
@scenario
def e1_fresh_genesis_nonattempts(t):
    w = World(t, 'e1_fresh_genesis_nonattempts_w', cases=['9993001'], nonattempts=['9993091'])
    dot = Dot(w)
    o = dot.session()
    t.check('E1: fresh session prints selftest', lambda: o.result.get('mode') == 'fresh' and o.actions[0].endswith(' selftest'), o)
    o = dot.vm('genesis', '--first-ledger')
    t.check('E1: genesis before the PASS is refused FINGERPRINT_NOT_PASSED', lambda: o.code == 4 and o.refused == 'FINGERPRINT_NOT_PASSED', o)
    fake_selftest(w)
    o = dot.vm('fingerprint-pass')
    t.check('E1: fingerprint-pass uploads SELFTEST then FINGERPRINT_PASS to setup and prints genesis', lambda: o.code == 0
            and [Path(u.split(' -> ')[0][7:]).name[:9] for u in o.uploads] == ['SELFTEST_', 'FINGERPRI']
            and o.actions[0].endswith('genesis --first-ledger'), o)
    o = dot.vm('genesis')
    t.check('E1: genesis without --first-ledger is refused GENESIS_FLAG', lambda: o.refused == 'GENESIS_FLAG', o)
    o = dot.vm('genesis', '--first-ledger')
    led = ledger_entries(w)
    gname = o.result.get('genesis')
    gnote = json.loads((w.base / 'outbox' / gname).read_text()) if gname else {}
    t.check('E1: genesis writes ledger line 1 through the runner (type genesis, fixed key set) and its GENESIS note',
            lambda: o.code == 0 and len(led) == 1 and led[0]['type'] == 'genesis'
            and set(led[0]) == set(vm.GENESIS_KEYS) | {'ledger', 'seq', 'previous_ledger_sha256', 'utc', 'entry_sha256'}
            and gnote['identity_line'] + '\n' == (w.base / 'ledger' / 'LEDGER.jsonl').read_text().splitlines(True)[0]
            and names(w.drive, w.records, 'GENESIS_') == [gname], o)
    o2 = dot.vm('genesis', '--first-ledger')
    t.check('E1: a second genesis is refused (GENESIS_LEDGER_EXISTS)', lambda: o2.refused == 'GENESIS_LEDGER_EXISTS', o2)
    o3 = dot.vm('wrap', 'nonattempt', '--release', w.base / 'runtime/RELEASE.json', '--admission',
                w.base / 'runtime/qualification/ADMISSION_QUALIFICATION.json', '--case', '9993091', '--reader', 'A', '--operator-model', MODEL)
    t.check('E1: wrap nonattempt without --jobs-root is refused WRAP_NONATTEMPT_JOBS_ROOT', lambda: o3.refused == 'WRAP_NONATTEMPT_JOBS_ROOT', o3)
    o = dot.vm('status')
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))
    fz = names(w.drive, w.records, 'FZ_NA-')
    t.check('E1: both nonattempts run through wrap, each makes one FZ, verified by download and evicted; status then prints the first prepare',
            lambda: len(fz) == 2 and o.actions[0].startswith(f'RUN {w.V} wrap prepare') and not (w.base / 'qual' / 'nonattempts_A' / '9993091').exists()
            and (w.base / 'outbox' / 'frozen_json' / 'NA-A_9993091_FROZEN.json').is_file(), lambda: (fz, o))
    # a second session in a new chat (same boot): local mode; genesis refused on a listing that holds GENESIS
    w2 = World(t, 'e1_fresh_genesis_nonattempts_w2', cases=['9993001'])
    d2 = Dot(w2)
    start_world(t, d2, w2)
    for f in w.drive.files(w.records):
        if f['name'].startswith('GENESIS_'):
            w2.drive.put(w2.records, f['name'], w.drive.data(f['id']))
    o = d2.session()
    t.check('E1: a records listing holding a GENESIS makes a wiped VM restore, never a second genesis', lambda: o.code in (3, 0)
            and o.result.get('mode') != 'fresh', o)



def session_note(w, o):
    n = o.result.get('session_note')
    return json.loads((w.base / 'outbox' / n).read_text()) if n else {}


def newest_pkg(w, case=None):
    ps = [vm.parse_name(f['name']) for f in w.drive.files(w.records) if f['name'][:3] in ('CP_', 'FZ_')]
    ps = [p for p in ps if case is None or p['case'] == case]
    return sorted(ps, key=lambda p: (p['seq'], p['pkind'] == 'FZ'))[-1]['name'] if ps else None


def to_prepare(t, dot, w):
    """From a fresh world: session, faked self-test, genesis, nonattempts; stops at the first printed prepare."""
    o = start_world(t, dot, w)
    return dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))


def restore_cycle(t, dot, w, label, expect_cls=None, choose=None):
    """Wipe, session start (restore), the incident status prints, the second listing and recheck."""
    w.wipe()
    o = dot.session()
    sn = session_note(w, o)
    t.check(f'{label}: session after the wipe restores (mode restore, pending incident)', lambda: o.code == 0 and sn.get('mode') == 'restore'
            and o.state.get('pending_incident') == 'yes', o)
    o2 = dot.vm('wrap', 'freeze', '--job-dir', w.base / 'qual' / 'A' / 'x', '--operator-model', MODEL)
    t.check(f'{label}: every job command waits for the incident (INCIDENT_REQUIRED)', lambda: o2.refused == 'INCIDENT_REQUIRED', o2)
    cls_line = ' '.join(o.actions + [a for _, a in o.options])
    if expect_cls:
        t.check(f'{label}: status prints the {expect_cls} incident', lambda: expect_cls in cls_line, o)
    o = dot.auto(o, choose=choose, halt=at_action(f'RUN {w.V} recheck'))
    t.check(f'{label}: the incident asks for the second listing, then recheck', lambda: o.result.get('command') == 'incident'
            and o.actions and o.actions[-1].endswith(' recheck') and any(f.startswith('SAVE_DRIVE_LISTING') for f in o.fetch), o)
    o3 = dot.vm('start-note', '--job-dir', w.base / 'qual' / 'A' / 'x', '--role', 'G')
    t.check(f'{label}: start-note before recheck is refused RESTORE_RECHECK_REQUIRED (exit 10)', lambda: o3.code == 10
            and o3.result.get('code') == 'RESTORE_RECHECK_REQUIRED', o3)
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    t.check(f'{label}: recheck accepts the second listing', lambda: o.code in (0, 10) and o.result.get('command') == 'recheck', o)
    return o, sn


@scenario
def e3_full_run_with_wipes(t):
    c = '9993101'
    w = World(t, 'e3_full_run_with_wipes_w', cases=[c])
    dot = Dot(w)
    o = to_prepare(t, dot, w)
    jd = w.base / 'qual' / 'A' / c
    # W1: after the CP-P upload
    dot.stop_after_upload = ('CP_', None)
    o = dot.auto(o)
    cpp = newest_pkg(w, c)
    t.check('E3 W1: prepare made CP-P (L seq, the job tag A)', lambda: cpp and cpp.startswith('CP_A_L') and o.result.get('runner_subcommand') == 'prepare', o)
    o, sn = restore_cycle(t, dot, w, 'E3 W1', 'NONE_IN_FLIGHT')
    t.check('E3 W1: the restore placed exactly the newest package', lambda: sn['restored']['package'] == cpp
            and vm.sha_file(jd / 'RUN_RECORD.json')[:8] == vm.parse_name(cpp)['record8'], sn.get('restored'))
    t.check('E3 W1: after recheck status prints start-note G', lambda: o.actions[0].endswith(f'start-note --job-dir {jd} --role G'), o)
    # W3: after the AI-G upload
    dot.stop_after_upload = ('AI_', 'ai-archive')
    o = dot.auto(o)
    t.check('E3 W3: ai-archive uploaded AI-G', lambda: names(w.drive, w.records, 'AI_A_G1_'), o)
    o, sn = restore_cycle(t, dot, w, 'E3 W3', 'AI_ARCHIVED')
    t.check('E3 W3: AI-G placed at its path byte for byte', lambda: sn['restored']['ai_archives_placed'] and (jd / 'run/A/output/response.json').is_file(), sn)
    t.check('E3 W3: the record was lost: status prints WRITE_GENERATION_RECORD first', lambda: o.actions[0].startswith('WRITE_GENERATION_RECORD'), o)
    o4 = dot.vm('wrap', 'finish', '--job-dir', jd, '--response', jd / 'run/A/output/response.json', '--generator-model', 'x',
                '--generation-record', jd / 'run/GENERATION_RECORD.json', '--operator-model', MODEL)
    t.check('E3: wrap finish without the generation record is refused WRAP_GENERATION_RECORD_MISSING', lambda: o4.refused is None
            and o4.result.get('code') == 'WRAP_GENERATION_RECORD_MISSING' and o4.actions[0].startswith('WRITE_GENERATION_RECORD'), o4)
    # W5: during finish (CP-F built, not uploaded), twice
    dot.stop_before_upload = ('PNG_', None)
    o = dot.auto(o)
    tok1 = o.bind
    t.check('E3 W5: finish completed and printed its bind token', lambda: tok1 and tok1.startswith('B1/finish/A/' + c + '/VISUAL_REVIEW/'), o)
    o, sn = restore_cycle(t, dot, w, 'E3 W5a', 'AI_ARCHIVED')
    dot.skip_upload = lambda n: n.startswith('CP_')
    dot.stop_after_upload = ('PNG_', None)
    o = dot.auto(o)
    t.check('E3 W5a: the bound re-run of finish matched (no divergence)', lambda: o.result.get('reset_diverged') is False
            and (o.result.get('binding') or {}).get('matched') is True and o.result['binding']['seen'] == [tok1], o)
    o, sn = restore_cycle(t, dot, w, 'E3 W5b', 'AI_ARCHIVED')
    dot.skip_upload = None
    inc = [json.loads((w.base / 'outbox' / f).read_text()) for f in os.listdir(w.base / 'outbox') if f.startswith('INCIDENT_')]
    t.check('E3 W5b: the second incident carries both tokens seen', lambda: any(len(i['seen']) == 2 for i in inc), inc)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} start-note'))
    pp = [f for f in w.drive.files(w.records) if f['name'].startswith('PNG_A_')]
    t.check('E7: parts uploaded before a lost CP-F are re-made with identical names and md5 (harmless duplicates)',
            lambda: len(pp) > len({f['name'] for f in pp}) and all(len({g['md5'] for g in pp if g['name'] == f['name']}) == 1 for f in pp), pp)
    t.check('E3 W5b: finish bound again matched, CP-F uploaded with its PNG parts', lambda: o.result.get('reset_diverged') is False
            and names(w.drive, w.records, 'PNG_A_') and newest_pkg(w, c).startswith('CP_A_'), o)
    # W7: after the CP-V upload (re-render path)
    dot.stop_after_upload = ('CP_', 'visual-record')
    o = dot.auto(o)
    if dot.halted is None and o.result.get('runner_subcommand') != 'visual-record':
        o = dot.auto(o)
    o, sn = restore_cycle(t, dot, w, 'E3 W7', 'NON_AI_STAGE_LOST')
    t.check('E3 W7: the PNG set was re-rendered byte for byte', lambda: sn['restored']['png'] == 'rerendered', sn.get('restored'))
    # freeze, then a wipe after the FZ upload
    dot.stop_after_upload = ('FZ_', None)
    o = dot.auto(o)
    fz = newest_pkg(w, c)
    t.check('E3: freeze made the FZ', lambda: fz.startswith('FZ_A_'), o)
    # r2 M2: the next runner command (reader B's prepare) is what a reset may have lost: NON_AI_STAGE_LOST (NOT_SEEN here)
    o, sn = restore_cycle(t, dot, w, 'E3 FZ', 'NON_AI_STAGE_LOST')
    t.check('E3 FZ: an FZ newest restores the ledger and the FROZEN.json copy only', lambda: sn['restored']['fz_newest'] is True
            and not jd.exists() and (w.base / 'outbox/frozen_json' / f'A_{c}_FROZEN.json').is_file(), sn.get('restored'))
    t.check('E3 FZ: status prints evict (part verification)', lambda: o.actions[0].endswith(f'evict --job-dir {jd}'), o)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))
    t.check('E3 FZ: evict verified the parts by download and status moves to reader B', lambda: '--reader B' in o.actions[0]
            and not (w.base / 'outbox' / 'FZ_PENDING.json').read_text().strip('[]\n '), o)



def forge_token(tok, field=6):
    """A token whose given field (codes8 by default) differs, with a valid check digit (a different result seen)."""
    parts = tok.split('/')
    parts[field] = 'f' * len(parts[field]) if parts[field] != 'f' * len(parts[field]) else '0' * len(parts[field])
    body = '/'.join(parts[:9])
    return body + '/' + sha(body.encode())[:4]


@scenario
def e4_e18_qualification_world(t):
    """E4-E6, E9, E16 on one ledger, then final; E12 assemble, verify-frozen and audit; E13 planted anomalies (E18: t17)."""
    c2, c3, c4, c5, c7, na = '9994002', '9994003', '9994004', '9994005', '9994007', '9994091'
    w = World(t, 'e4_e18_qualification_world_w', cases=[c2, c3, c4, c5, c7], nonattempts=[na])
    dot = Dot(w)
    behaviour = {}

    def conv(jd, case, role, reader):
        ok = [o for o in dot.history if o.result.get('command') == 'start-note' and o.code == 0 and f'--role {role}' in o.cmd and str(jd) in o.cmd]
        n = ok[-1].result.get('attempt') if ok else 0
        how = behaviour.get((case, reader, jd.parent.name, role, n), 'normal')
        if how == 'nothing':
            return
        if role == 'G':
            tcj.stand_in_response(None, jd, case, reader=reader)
        elif role == 'V':
            tcj.stand_in_review(jd, drop_page=(how == 'incomplete'), reviewer=dict(tcj.REVIEWER, conversation_id=dot.values['CONVERSATION_ID']))
    dot.conv = {'G': conv, 'V': conv, 'S': conv}
    o = to_prepare(t, dot, w)
    A = lambda c: w.base / 'qual' / 'A' / c
    # ---- c2 (E4): the generator conversation in flight at a reset; nothing written
    behaviour[(c2, 'A', 'A', 'G', 1)] = 'nothing'
    o = dot.auto(o, halt=at_action('OPEN_CONVERSATION'))
    t.check('E4: start-note G after CP-P printed OPEN_CONVERSATION', lambda: o.result.get('command') == 'start-note', o)
    oi = dot.vm('wrap', 'interrupt', '--job-dir', A(c2), '--reason', 'TECHNICAL_VM_RESET', '--started-utc', vm.utc(), '--ended-utc', vm.utc(),
                '--operator-model', MODEL)
    t.check('E4: wrap interrupt without its AI_NOTHING_WRITTEN incident is refused WRAP_INCIDENT_REQUIRED', lambda: oi.refused == 'WRAP_INCIDENT_REQUIRED', oi)
    dot.stop_after_upload = ('LINK_', None)
    o = dot.auto(o)
    o, sn = restore_cycle(t, dot, w, 'E4 W2', 'AI_NOTHING_WRITTEN')
    inc = [x for x in names(w.drive, w.records, 'INCIDENT_') if '_AI_NOTHING_WRITTEN_A_G1_' + c2 in x]
    t.check('E4 W2: the incident names class, job, role and attempt; status then prints wrap interrupt TECHNICAL_VM_RESET',
            lambda: inc and 'wrap interrupt' in o.actions[0] and '--reason TECHNICAL_VM_RESET' in o.actions[0], o)
    # a wipe between the incident upload and wrap interrupt: the restored incident satisfies it
    o, sn = restore_cycle(t, dot, w, 'E4 W2b', 'NON_AI_STAGE_LOST')
    dot.stop_after_upload = ('FZ_', None)
    o = dot.auto(o)
    led = ledger_entries(w)
    t.check('E4: interrupt form 1 then freeze (FZ uploaded)', lambda: any(e.get('stage') == 'interrupt' and e.get('next') == 'STOP_TECHNICAL_INTERRUPTION'
                                                                       for e in led) and newest_pkg(w, c2).startswith('FZ_A_'), o)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))
    t.check('E4: after evict status prints A\'s restart prepare first (restart_eligible on the kept FROZEN.json)',
            lambda: '--jobs-root ' + str(w.base / 'qual' / 'A_restart1') in o.actions[0] and f'/jobs/{c2}/' in o.actions[0], o)
    ob = dot.vm('wrap', 'prepare', '--release', w.base / 'runtime/RELEASE.json', '--job', w.base / f'runtime/qualification/jobs/{c2}/JOB.json',
                '--job-title-file', w.base / f'runtime/qualification/jobs/{c2}/JOB_TITLE.json', '--jobs-root', w.base / 'qual' / 'B',
                '--reader', 'B', '--qualification', '--admission', w.base / 'runtime/qualification/ADMISSION_QUALIFICATION.json',
                '--operator-model', MODEL)
    if ob.actions == [f'RUN {w.V} wait']:
        ob = dot.auto(ob, halt=lambda a, o_: not a.endswith(' wait'))
    t.check('E4: B\'s prepare by hand is refused QUALIFICATION_READER_A_RESTART_UNUSED (A\'s FROZEN.json placed) and the NEXT is the restart',
            lambda: 'QUALIFICATION_READER_A_RESTART_UNUSED' in ob.result.get('runner_last_line', '') and '_restart1' in ob.actions[0]
            and not (w.base / 'qual' / 'A' / c2).exists() and not (w.base / 'outbox' / 'PLACED.json').exists(), lambda: ob.text[-3000:])
    o = dot.auto(o, halt=lambda a, o_: a.startswith(f'RUN {w.V} wrap prepare') and f'/jobs/{c3}/' in a)
    pr = [e for e in ledger_entries(w) if e.get('type') == 'prepare' and e['case_id'] == c2]
    t.check('E4: the restart run was accepted by the runner (restart_of = the A folder) and frozen',
            lambda: len(pr) == 2 and pr[1]['restart_of'] == str(A(c2)) and newest_pkg(w, c2).startswith('FZ_A-restart1_'), pr)
    # ---- c3 (E5): written and lost before ai-archive
    t.check('E5: status moved to case c3', lambda: f'/jobs/{c3}/' in o.actions[0], o)
    dot.stop_after_upload = ('LINK_', None)
    o = dot.auto(o)
    os_ = dot.vm('start-note', '--job-dir', A(c3), '--role', 'G')
    o, sn = restore_cycle(t, dot, w, 'E5 W4', 'AI_WRITTEN_LOST', choose=lambda o_: 'WRITTEN_OR_DOUBT')
    os_ = dot.vm('start-note', '--job-dir', A(c3), '--role', 'G')
    t.check('E5: after AI_WRITTEN_LOST start-note is refused START_NOT_ALLOWED', lambda: os_.refused == 'START_NOT_ALLOWED', os_)
    t.check('E5: status prints wrap freeze (failed run)', lambda: 'wrap freeze' in o.actions[0], o)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))
    t.check('E5: no restart is printed for c3; status moves to c4', lambda: f'/jobs/{c4}/' in o.actions[0] and '_restart1' not in o.actions[0], o)
    orr = dot.vm('wrap', 'prepare', '--release', w.base / 'runtime/RELEASE.json', '--job', w.base / f'runtime/qualification/jobs/{c3}/JOB.json',
                 '--job-title-file', w.base / f'runtime/qualification/jobs/{c3}/JOB_TITLE.json', '--jobs-root', w.base / 'qual' / 'A_restart1',
                 '--reader', 'A', '--qualification', '--admission', w.base / 'runtime/qualification/ADMISSION_QUALIFICATION.json',
                 '--operator-model', MODEL)
    if orr.actions == [f'RUN {w.V} wait']:
        orr = dot.auto(orr, halt=lambda a, o_: not a.endswith(' wait'))
    t.check('E5: the restart prepare of a run frozen at GENERATE is refused by the runner (QUALIFICATION_RESTART_NOT_ALLOWED, C24)',
            lambda: orr.refused == 'RUNNER_QUALIFICATION_RESTART_NOT_ALLOWED', orr)
    # ---- c4 (E6): a seen token that differs: RESET_DIVERGED
    dot.stop_before_upload = ('PNG_', None)
    o = dot.auto(o)
    real = list(dot.pending_tokens)
    w.wipe()
    o = dot.session()
    dot.pending_tokens = [forge_token(real[-1])]
    o = dot.auto(o, choose=lambda o_: 'SEEN', halt=at_action(f'RUN {w.V} recheck'))
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    dot.pending_tokens = []
    o = dot.auto(o, halt=lambda a, o_: o_.stop is not None)
    t.check('E6: the bound re-run differs from the token seen: STOP RESET_DIVERGED, reset_diverged in RESULT and the package',
            lambda: o.stop == 'RESET_DIVERGED' and o.result.get('reset_diverged') is True and 'wrap freeze' in o.actions[0], o)
    ov = dot.vm('start-note', '--job-dir', A(c4), '--role', 'V')
    t.check('E6: a diverged run allows only freeze (start-note refused)', lambda: ov.refused == 'WRAP_RUN_FAILED_RESET_DIVERGED', ov)
    o = dot.run_line(o.actions[0][4:])
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))
    fzn = newest_pkg(w, c4)
    t.check('E6: the FZ inherits reset_diverged; status moves on without a restart', lambda: fzn.startswith('FZ_A_')
            and json.loads((w.base / 'outbox/frozen_json' / f'A_{c4}_FLAGS.json').read_text())['reset_diverged'] is True
            and f'/jobs/{c5}/' in o.actions[0], o)
    od = dot.vm('wrap', 'prepare', '--release', w.base / 'runtime/RELEASE.json', '--job', w.base / f'runtime/qualification/jobs/{c4}/JOB.json',
                '--job-title-file', w.base / f'runtime/qualification/jobs/{c4}/JOB_TITLE.json', '--jobs-root', w.base / 'qual' / 'A_restart1',
                '--reader', 'A', '--qualification', '--admission', w.base / 'runtime/qualification/ADMISSION_QUALIFICATION.json', '--operator-model', MODEL)
    t.check('E6: the restart prepare after divergence is refused WRAP_RESTART_AFTER_DIVERGED', lambda: od.refused == 'WRAP_RESTART_AFTER_DIVERGED', od)
    # ---- c5 (E16, E18): an incomplete review, a revision; a freeze whose FROZEN.json cannot be written
    behaviour[(c5, 'A', 'A', 'V', 1)] = 'incomplete'
    dot.conv['V-continue'] = lambda: tcj.stand_in_review(A(c5), reviewer=dict(tcj.REVIEWER, conversation_id=dot.values['CONVERSATION_ID']))
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap visual-record'))
    orv = dot.vm('ai-archive', '--job-dir', A(c5), '--role', 'V', '--revision')
    t.check('E16: a revision without the refusal is refused REVISION_NOT_ALLOWED', lambda: orv.refused == 'REVISION_NOT_ALLOWED', orv)
    o = dot.auto(o, halt=at_action('CONTINUE_CONVERSATION'))
    t.check('E16: visual-record refused REVIEW_INCOMPLETE made a CP and printed CONTINUE_CONVERSATION', lambda: o.result.get('package')
            and 'REVIEW_INCOMPLETE' in o.result.get('runner_last_line', ''), o)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap freeze'))
    t.check('E16: the revision archive AI-V1r2 was made and visual-record passed', lambda: names(w.drive, w.records, 'AI_A_V1r2_')
            and o.result.get('runner_subcommand') == 'visual-record' and o.result.get('runner_exit') == 0, o)
    # E18 runs in t17_selftest_e18 (a repository copy whose runner write fails on request: no root, no chattr, T-29)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))
    # ---- c7 (E9): the reviewer writes nothing, twice
    behaviour[(c7, 'A', 'A', 'V', 1)] = 'nothing'
    behaviour[(c7, 'A', 'A', 'V', 2)] = 'nothing'
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap freeze'))
    o2 = dot.vm('start-note', '--job-dir', A(c7), '--role', 'V')
    t.check('E9: after two nothing-written reviewers the replacement is used (REVIEWER_REPLACEMENT_USED) and NEXT is freeze',
            lambda: o2.refused == 'REVIEWER_REPLACEMENT_USED' and names(w.drive, w.records, 'START_A_V2_') and 'wrap freeze' in o.actions[0], (o, o2))
    # ---- the B runs (normal), then final
    o = dot.auto(o, halt=at_action(f'RUN {w.V} final'), max_steps=400)
    t.check('E4-E9: every case and reader is done: status prints final', lambda: o.actions and o.actions[0].endswith(' final'), o)
    o = dot.auto(o, halt=at_action('HANDBACK'))
    af = json.loads((w.base / 'outbox' / 'ALL_FROZEN.json').read_text()) if (w.base / 'outbox' / 'ALL_FROZEN.json').is_file() else {}
    flags = {(r['case_id'], r['tag']): r['flags'] for r in af.get('runs', [])}
    t.check('E5/E6/E9 final: ALL_FROZEN flags carry AI_OUTPUT_LOST, RESET_DIVERGED, REVIEWER_REPLACED/LOST, RESTARTED, REVIEW_REVISED',
            lambda: 'AI_OUTPUT_LOST' in flags[(c3, 'A')] and 'RESET_DIVERGED' in flags[(c4, 'A')] and 'REVIEWER_REPLACED' in flags[(c7, 'A')]
            and 'REVIEWER_LOST' in flags[(c7, 'A')] and 'RESTARTED' in flags[(c2, 'A-restart1')] and 'REVIEW_REVISED' in flags[(c5, 'A')]
            and names(w.drive, w.records, 'ALL_FROZEN') == ['ALL_FROZEN.json'], flags)
    t.check('final: uploads LEDGER_FINAL then ALL_FROZEN.json last', lambda: [Path(u.split(' -> ')[0][7:]).name[:7] for u in o.uploads] == ['LEDGER_', 'ALL_FRO'], o)
    e12_assemble_audit(t, w, dot)


def e12_assemble_audit(t, w, dot):
    flat = w.drive.flat(w.records, w.root / 'maint' / 'qualification')
    sflat = w.drive.flat(FOLDERS['setup'], w.root / 'maint' / 'setup')
    w.drive.listing(w.records, w.root / 'maint' / 'Q_LISTING.json')
    w.drive.listing(FOLDERS['setup'], w.root / 'maint' / 'S_LISTING.json')
    rel = w.root / 'maint' / 'RELEASE.json'
    shutil.copyfile(w.base / 'runtime' / 'RELEASE.json', rel)
    af = json.loads((flat / 'ALL_FROZEN.json').read_text())
    modes = {}
    for r in af['runs']:
        m = vm.pkg_manifest(flat, r['archive']['name'])
        modes[r['job_dir']] = {x['path']: x['mode'] for x in m['members']}
    # wipe everything, the base included (the repo link is kept: assemble runs from the helper's own repository)
    w.wipe()
    env = dict(os.environ)
    p = subprocess.run([sys.executable, '-I', '-B', str(HELPER), 'assemble', '--drive-dir', str(flat), '--verify-frozen'],
                       capture_output=True, text=True, env=env, timeout=3600)
    t.outputs.append(p.stdout)
    o = Out(p.returncode, p.stdout, 'assemble')
    rep = json.loads((flat / 'ASSEMBLE_REPORT.json').read_text()) if (flat / 'ASSEMBLE_REPORT.json').is_file() else {}
    t.check('E12: assemble writes every folder at its original path and runner v4 verify-frozen prints NEXT: DONE for each',
            lambda: o.code == 0 and len(rep['runs']) == len(af['runs']) and all(r['verify_frozen']['last_line'] == 'NEXT: DONE' for r in rep['runs']),
            lambda: (o.text[-800:], p.stderr[-1500:], [r.get('verify_frozen') for r in rep.get('runs', [])][:3]))
    bad_modes = []
    for jd, mm in modes.items():
        for path, mode in mm.items():
            q_ = Path(jd) / path[4:] if path != 'job' else Path(jd)
            if stat_mode(q_) != mode:
                bad_modes.append(str(q_))
    t.check('E12: every S_IMODE equals the FZ manifest (lstat), zero-byte logs present', lambda: not bad_modes
            and any(f.stat().st_size == 0 for jd in modes for f in (Path(jd) / 'logs').glob('*') if (Path(jd) / 'logs').is_dir()), bad_modes[:5])
    one = Path(af['runs'][0]['job_dir'])
    other = w.root / 'elsewhere' / one.name
    other.parent.mkdir()
    subprocess.run(['cp', '-a', str(one), str(other)], check=True)
    p = subprocess.run([sys.executable, '-I', '-B', str(RUNNER), 'verify-frozen', '--job-dir', str(other)], capture_output=True, text=True)
    t.check('E12/C18: the same folder at another path: FROZEN_FOLDER_CHANGED with record_chain QUALIFICATION_JOB_NOT_IN_LEDGER',
            lambda: 'FROZEN_FOLDER_CHANGED' in p.stdout and 'QUALIFICATION_JOB_NOT_IN_LEDGER' in p.stdout, p.stdout[-600:])
    vm.remove_tree(other.parent)
    args = ['audit', '--drive-dir', str(flat), '--listing', str(w.root / 'maint' / 'Q_LISTING.json'), '--setup-dir', str(sflat),
            '--setup-listing', str(w.root / 'maint' / 'S_LISTING.json'), '--release', str(rel)]
    p = subprocess.run([sys.executable, '-I', '-B', str(HELPER), *args, '--allow-test-overrides'], capture_output=True, text=True, timeout=3600)
    ar = json.loads((flat / 'AUDIT_REPORT.json').read_text()) if (flat / 'AUDIT_REPORT.json').is_file() else {}
    t.check('E12: audit --allow-test-overrides reports no anomaly and lists the failed-by-reset runs', lambda: p.returncode == 0
            and not ar['anomalies'] and len(ar['runs_failed_by_reset']) >= 3, lambda: (p.stdout[-500:], p.stderr[-800:], ar.get('anomalies', [])[:6]))
    t.check('r2 M3: AUD_START_SUPERSEDED never names a reviewer START (the replacement reviewer replaces, it does not supersede)',
            lambda: not any(x.get('code') == 'AUD_START_SUPERSEDED' and any(re.match(r'^START_[^_]+_V', n) for n in x.get('names', []))
                            for x in ar.get('listed', [])), ar.get('listed'))
    o52 = json.loads((flat / 'O52_COMPARISON.json').read_text()) if (flat / 'O52_COMPARISON.json').is_file() else {}
    t.check('E12: O52_COMPARISON lists every START and marks nothing-written ones open_and_check', lambda: len(o52['rows']) == len(names(w.drive, w.records, 'START_'))
            and any(r['open_and_check'] for r in o52['rows']), o52)
    e13_anomalies(t, w, flat, sflat, rel)


def stat_mode(p):
    return stat.S_IMODE(os.lstat(p).st_mode)


def e13_anomalies(t, w, flat, sflat, rel):
    base_args = ['--setup-dir', str(sflat), '--setup-listing', str(w.root / 'maint' / 'S_LISTING.json'), '--release', str(rel)]
    lst = json.loads((w.root / 'maint' / 'Q_LISTING.json').read_text())

    def run_case(label, code, change, allow=True):
        d = w.root / 'maint' / ('e13_' + label)
        shutil.copytree(flat, d, copy_function=os.link)
        L = json.loads(json.dumps(lst))
        change(d, L)
        lp = d.parent / (d.name + '_LISTING.json')
        lp.write_text(json.dumps(L))
        p = subprocess.run([sys.executable, '-I', '-B', str(HELPER), 'audit', '--drive-dir', str(d), '--listing', str(lp), *base_args,
                            *(['--allow-test-overrides'] if allow else [])], capture_output=True, text=True, timeout=3600)
        ar = json.loads((d / 'AUDIT_REPORT.json').read_text()) if (d / 'AUDIT_REPORT.json').is_file() else {}
        codes = {x['code'] for x in ar.get('anomalies', [])}
        t.check(f'E13: {label} fires {code}', lambda: p.returncode == 3 and code in codes, lambda: (sorted(codes), p.stderr[-600:]))

    def files(L):
        return [f for pg in L['pages'] for f in pg['files']]

    def drop(prefix):
        def ch(d, L):
            for pg in L['pages']:
                pg['files'] = [f for f in pg['files'] if not f['name'].startswith(prefix)]
            for f in d.glob(prefix + '*'):
                f.unlink()
        return ch

    run_case('ai_deleted', 'AUD_START_UNRESOLVED', drop('AI_A_G1_'))
    run_case('incident_deleted', 'AUD_INTERRUPT_WITHOUT_INCIDENT', drop('INCIDENT_'))
    run_case('start_deleted', 'AUD_START_MISSING', drop('START_A_G1_'))
    run_case('overrides', 'AUD_TEST_OVERRIDE', lambda d, L: None, allow=False)

    def same_boot(d, L):
        ss = sorted(d.glob('SESSION_*.json'))
        a_, b_ = json.loads(ss[-2].read_text()), json.loads(ss[-1].read_text())
        b_['boot_id'], b_['mode'] = a_['boot_id'], 'restore'
        ss[-1].unlink()
        ss[-1].write_text(json.dumps(b_))
    run_case('same_boot', 'AUD_RESET_SAME_BOOT', same_boot)

    def late_start(d, L):
        for f in files(L):
            if f['name'].startswith('START_A_G1_'):
                f['createdTime'] = '2099-01-01T00:00:00.000Z'
    run_case('start_late', 'AUD_START_AFTER_CONVERSATION', late_start)

    def fork(d, L):
        fz = sorted(d.glob('CP_A_*'))[0]
        p = vm.parse_name(fz.name)
        data = b'invented fork bytes, intact by their name hash'   # T-02: a name that fails its own hash is no fork
        n2 = fz.name.replace('_' + p['pkg8'] + '_', '_' + sha(data)[:8] + '_')
        (d / n2).write_bytes(data)
        f0 = next(f for f in files(L) if f['name'] == fz.name)
        L['pages'][-1]['files'].append(dict(f0, name=n2, id='fid999999', md5Checksum=md5(data), size=str(len(data))))
    run_case('fork', 'AUD_FORK', fork)

    def no_pass(d, L):
        pass
    sl = json.loads((w.root / 'maint' / 'S_LISTING.json').read_text())
    for pg in sl['pages']:
        pg['files'] = [f for f in pg['files'] if not f['name'].startswith('FINGERPRINT_PASS_')]
    (w.root / 'maint' / 'S_NOPASS.json').write_text(json.dumps(sl))
    base_args[base_args.index(str(w.root / 'maint' / 'S_LISTING.json'))] = str(w.root / 'maint' / 'S_NOPASS.json')
    run_case('no_pass', 'AUD_FINGERPRINT_NOT_PASSED', no_pass)
    base_args[base_args.index(str(w.root / 'maint' / 'S_NOPASS.json'))] = str(w.root / 'maint' / 'S_LISTING.json')
    # T-19: a FINGERPRINT_PASS note in SDIR whose content does not validate counts as no pass
    sbad = w.root / 'maint' / 'setup_badpass'
    shutil.copytree(sflat, sbad, copy_function=shutil.copyfile)
    for fp_ in sbad.glob('FINGERPRINT_PASS_*.json'):
        doc = json.loads(fp_.read_text())
        doc['selftest']['passed_count'] = 599
        fp_.write_text(json.dumps(doc))
    base_args[base_args.index(str(sflat))] = str(sbad)
    run_case('pass_note_invalid', 'AUD_FINGERPRINT_PASS_INVALID', no_pass)
    run_case('pass_note_invalid_means_no_pass', 'AUD_FINGERPRINT_NOT_PASSED', no_pass)
    base_args[base_args.index(str(sbad))] = str(sflat)
    run_case('replacement_incident_deleted', 'AUD_REPLACEMENT_WITHOUT_INCIDENT',
             lambda d, L: [f.unlink() for f in d.glob('INCIDENT_*_AI_NOTHING_WRITTEN_A_V1_*')])
    run_case('restore_incident_deleted', 'AUD_RESTORE_WITHOUT_INCIDENT',
             lambda d, L: [f.unlink() for f in d.glob('INCIDENT_*_NON_AI_STAGE_LOST_*')])

    def swap_ai(d, L):
        gs = sorted(d.glob('AI_A*_G1_*'))
        a_, b_ = gs[0], gs[-1]
        data = a_.read_bytes()
        b_.unlink()
        b_.write_bytes(data)
    run_case('ai_swapped', 'AUD_AI_SHA_MISMATCH', swap_ai)

    def contradict(d, L):
        f = sorted(d.glob('INCIDENT_*_AI_WRITTEN_LOST_*'))[0]
        doc = json.loads(f.read_text())
        doc['classification'] = 'AI_NO_CONVERSATION'
        n = f.name.replace('AI_WRITTEN_LOST', 'AI_NO_CONVERSATION').replace('INCIDENT_2', 'INCIDENT_3', 1)
        (d / n).write_text(json.dumps(doc))
        f0 = next(x for x in files(L) if x['name'] == f.name)
        L['pages'][-1]['files'].append(dict(f0, name=n, id='fid999998'))
    run_case('classification_contradicts', 'AUD_CLASSIFICATION_INCONSISTENT', contradict)

    def not_failed(d, L):                       # r2 R2-04: a diverged run that ALL_FROZEN.json does not count as failed
        af_ = json.loads((d / 'ALL_FROZEN.json').read_text())
        af_['runs_failed_by_reset'] = []
        (d / 'ALL_FROZEN.json').unlink()
        (d / 'ALL_FROZEN.json').write_text(json.dumps(af_))
    run_case('diverged_not_failed', 'AUD_BINDING_MISMATCH', not_failed)
    r2 = json.loads(rel.read_text())
    r2['pinned_files_sha256']['deploy/vm/cps_vm.py'] = '0' * 64
    rel2 = w.root / 'maint' / 'RELEASE_other_pin.json'
    rel2.write_text(json.dumps(r2))
    base_args[base_args.index(str(rel))] = str(rel2)
    run_case('helper_not_pinned', 'AUD_HELPER_NOT_PINNED', lambda d, L: None)



# ------------------------------------------------------------------ unit tests (11.2)
def halt_code(fn, *a, **k):
    try:
        fn(*a, **k)
    except vm.Halt as h:
        return h.code
    return None


def invented_tree(root):
    """U1: zero-byte files, empty dirs at several depths, modes 0444/0555/0644/0755/0600/0700, a CJK name, a read-only tree."""
    root.mkdir(parents=True)
    (root / 'logs').mkdir()
    (root / 'logs' / '01_x.stdout').write_bytes(b'')
    (root / 'logs' / '01_x.stderr').write_bytes(b'')
    (root / 'empty1' / 'empty2' / 'empty3').mkdir(parents=True)
    (root / 'a.json').write_text('{"invented": 1}\n')
    (root / '示例檔案.txt').write_text('invented CJK name\n', encoding='utf-8')
    (root / 'priv').mkdir()
    (root / 'priv' / 'secret.txt').write_text('invented 0600\n')
    ro = root / 'ro1' / 'ro2' / 'ro3'
    ro.mkdir(parents=True)
    (ro / 'deep.bin').write_bytes(os.urandom(3000))
    (root / 'ro1' / 'top.txt').write_text('x\n')
    os.chmod(root / 'a.json', 0o444)
    os.chmod(root / 'priv' / 'secret.txt', 0o600)
    os.chmod(root / 'priv', 0o700)
    os.chmod(root / 'logs', 0o555)
    for p in [ro / 'deep.bin', root / 'ro1' / 'top.txt']:
        os.chmod(p, 0o444)
    for d in [ro, ro.parent, ro.parent.parent]:
        os.chmod(d, 0o555)
    os.chmod(root / 'empty1', 0o755)
    os.chmod(root, 0o555)


def lmodes(root):
    out = {}
    for dp, dns, fns in os.walk(root):
        for n in dns + fns:
            p = os.path.join(dp, n)
            out[os.path.relpath(p, root)] = stat.S_IMODE(os.lstat(p).st_mode)
    out['.'] = stat.S_IMODE(os.lstat(root).st_mode)
    return out


def pack_tree(src, dest):
    entries = vm.tree_list(src)
    members = [{'path': 'job', 'type': 'dir', 'mode': stat_mode(src)}] + [
        {'path': 'job/' + r, 'type': k, 'mode': m} if k == 'dir' else {'path': 'job/' + r, 'type': k, 'mode': m, 'bytes': b, 'sha256': h}
        for r, k, m, b, h in entries]
    man = {'schema': 'cps.vm-package.v1', 'members': members, 'ledger': None}
    mm = [('MANIFEST.json', 'file', 0o444, 0, vm.note_bytes(man)), ('job', 'dir', stat_mode(src), 0, None)]
    mm += [('job/' + r, k, m, 0, None if k == 'dir' else str(Path(src) / r)) for r, k, m, b, h in entries]
    vm.write_tgz(dest, mm)
    return man


def unpack(arch, target):
    a = vm.Archive(arch, ('MANIFEST.json', 'ledger', 'job'))
    a.check(vm.pkg_expected(a.manifest))
    stg = vm.Staging(target)
    stg.begin(next(m['mode'] for m in a.manifest['members'] if m['path'] == 'job'))
    for m in a.manifest['members']:
        if m['path'] == 'job':
            continue
        if m['type'] == 'dir':
            stg.add_dir(m['path'][4:], m['mode'])
        else:
            stg.add_file(m['path'][4:], a.read(m['path']), m['mode'])
    stg.finish()
    a.close()


def bad_tar(path, members, manifest=None):
    """A gzip tar with MANIFEST.json first and the given raw TarInfo members [(TarInfo, bytes|None)]."""
    import gzip
    import io
    import tarfile
    with open(path, 'wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as gz, tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as tf:
        mb = vm.note_bytes(manifest or {'members': [], 'ledger': None})
        ti = tarfile.TarInfo('MANIFEST.json')
        ti.size, ti.mode = len(mb), 0o444
        tf.addfile(ti, io.BytesIO(mb))
        for ti, data in members:
            tf.addfile(ti, io.BytesIO(data) if data is not None else None)


@scenario
def u_units(t):
    import tarfile
    root = t.work / 'u_units_w'
    root.mkdir()
    # U1: round trip, at the original path
    src = root / 'job_round_trip'
    invented_tree(src)
    before_tree, before_modes = cj.tree(src), lmodes(src)
    arch = root / 'rt.tgz'
    pack_tree(src, arch)
    a1 = sha_file(arch)
    vm.remove_tree(src)
    unpack(arch, src)
    t.check('U1: package round trip at the original path: identical tree and S_IMODE of every entry (lstat), zero-byte files and empty dirs kept',
            lambda: cj.tree(src) == before_tree and lmodes(src) == before_modes and (src / 'empty1/empty2/empty3').is_dir()
            and (src / 'logs/01_x.stdout').stat().st_size == 0, lambda: (cj.tree(src) == before_tree, lmodes(src), before_modes))
    pack_tree(src, root / 'rt2.tgz')
    t.check('U1: a staging sibling is used and nothing is left behind', lambda: not list(root.glob('.cps_vm_stage_*')))
    del a1
    # U2: unsafe members refused before anything is written
    def ti(name, typ=tarfile.REGTYPE, size=0, mode=0o644, link=''):
        x = tarfile.TarInfo(name)
        x.type, x.size, x.mode, x.linkname = typ, size, mode, link
        return x
    cases = {
        'absolute': ([(ti('/job/x', size=1), b'x')], 'ARCHIVE_UNSAFE_MEMBER'),
        'dotdot': ([(ti('job/../x', size=1), b'x')], 'ARCHIVE_UNSAFE_MEMBER'),
        'symlink': ([(ti('job/l', tarfile.SYMTYPE, link='/etc/passwd'), None)], 'ARCHIVE_UNSAFE_MEMBER'),
        'hardlink': ([(ti('job/h', tarfile.LNKTYPE, link='job/x'), None)], 'ARCHIVE_UNSAFE_MEMBER'),
        'chardev': ([(ti('job/c', tarfile.CHRTYPE), None)], 'ARCHIVE_UNSAFE_MEMBER'),
        'fifo': ([(ti('job/f', tarfile.FIFOTYPE), None)], 'ARCHIVE_UNSAFE_MEMBER'),
        'setuid': ([(ti('job/s', size=1, mode=0o4755), b'x')], 'ARCHIVE_UNSAFE_MEMBER'),
        'duplicate': ([(ti('job/d', size=1), b'x'), (ti('job/d', size=1), b'y')], 'ARCHIVE_UNSAFE_MEMBER'),
        'outside': ([(ti('other/x', size=1), b'x')], 'ARCHIVE_UNSAFE_MEMBER'),
        'unlisted': ([(ti('job', tarfile.DIRTYPE, mode=0o755), None), (ti('job/u', size=1), b'x')], 'ARCHIVE_MANIFEST_MISMATCH'),
    }
    for label, (mem, code) in cases.items():
        p = root / f'bad_{label}.tgz'
        bad_tar(p, mem, {'members': [{'path': 'job', 'type': 'dir', 'mode': 0o755}], 'ledger': None})
        got = halt_code(lambda: vm.Archive(p, ('MANIFEST.json', 'ledger', 'job')).check(
            vm.pkg_expected({'members': [{'path': 'job', 'type': 'dir', 'mode': 0o755}], 'ledger': None})))
        t.check(f'U2: {label} member refused {code}', lambda: got == code, got)
    man = {'members': [{'path': 'job', 'type': 'dir', 'mode': 0o755}, {'path': 'job/x', 'type': 'file', 'mode': 0o644, 'bytes': 1, 'sha256': sha(b'y')}],
           'ledger': None}
    bad_tar(root / 'bad_sha.tgz', [(ti('job', tarfile.DIRTYPE, mode=0o755), None), (ti('job/x', size=1), b'x')], man)
    t.check('U2: a member whose sha differs from the manifest: ARCHIVE_MEMBER_SHA_MISMATCH', lambda: halt_code(
        lambda: vm.Archive(root / 'bad_sha.tgz', ('MANIFEST.json', 'job')).check(vm.pkg_expected(man))) == 'ARCHIVE_MEMBER_SHA_MISMATCH')
    man2 = dict(man, members=[man['members'][0], dict(man['members'][1], bytes=2, sha256=sha(b'x'))])
    t.check('U2: a member whose size differs: ARCHIVE_MEMBER_SHA_MISMATCH', lambda: halt_code(
        lambda: vm.Archive(root / 'bad_sha.tgz', ('MANIFEST.json', 'job')).check(vm.pkg_expected(man2))) == 'ARCHIVE_MEMBER_SHA_MISMATCH')
    # U3: deterministic PNG tar
    pd = root / 'pngs'
    (pd / 'qa').mkdir(parents=True)
    for i in range(3):
        (pd / 'qa' / f'page-{i:04d}.png').write_bytes(os.urandom(1000 + i))
    rels = sorted(f'qa/page-{i:04d}.png' for i in range(3))
    import io
    b1, b2 = io.BytesIO(), io.BytesIO()
    vm.write_tar_stream(b1, vm.png_tar_members(pd, rels))
    os.utime(pd / 'qa' / 'page-0000.png', (1, 1))
    vm.write_tar_stream(b2, vm.png_tar_members(pd, rels))
    t.check('U3: the same PNG bytes give an identical PNG tar (mtime 0, sorted)', lambda: b1.getvalue() == b2.getvalue())
    # U4: names
    pk = vm.package_name('CP', 'A-restart1', 'L', 17, 'a' * 8, 'b' * 8, '0' * 8, 'c' * 8, 'd' * 8, '99_9.x-1')
    samples = [pk, 'PNG_B_0123abcd_01of03_9990001.part', 'AI_E20261109T101500Z_V2r3_0123abcd_case_1.tgz',
               'START_NA-A_S1_20261109T101500Z_0123abcd_c.json', 'LINK_A_G2_0123abcd_c.json', 'TRANSCRIPT_A_G1_0123abcd_c.txt',
               'INCIDENT_20261109T101500Z_0123abcd_AI_NOTHING_WRITTEN_A_G1_c_1.json', 'INCIDENT_20261109T101500Z_0123abcd_NONE_IN_FLIGHT_NOJOB_NA_none.json',
               'SESSION_20261109T101500Z_0123abcd_89abcdef.json', 'GENESIS_0123abcd_20261109T101500Z.json',
               'FINGERPRINT_PASS_0123abcd_20261109T101500Z.json', 'SELFTEST_0123abcd_20261109T101500Z.json',
               'INPUTS_E20261109T101500Z_E0_0123abcd_c.tgz', 'LEDGER_FINAL_L00012_0123abcd.jsonl', 'ALL_FROZEN.json',
               'DELIVERY_SENT_c.1_20261109T101500Z.json', 'SENTINEL_everyday_0123abcd.json', 'STRAY_20261109T101500Z_0123abcd.tgz',
               'SPLIT_0123abcd_01of02__' + pk]
    parsed = [vm.parse_name(n) for n in samples]
    t.check('U4: every 3.1 pattern parses; a case id with _ . - parses because the case is last', lambda: all(parsed)
            and parsed[0]['case'] == '99_9.x-1' and parsed[0]['tag'] == 'A-restart1' and parsed[0]['seq'] == 17
            and parsed[2]['revision'] == 3 and parsed[6]['case'] == 'c_1' and parsed[7]['tag'] is None, parsed)
    t.check('U4: malformed names are ignored', lambda: not any(vm.parse_name(n) for n in ('CP_X_L00001_a_b_c_d_e_f.tgz', 'AI_A_G3_0123abcd_c.tgz',
                                                                                          'START_A_G1_2026_0123abcd_c.json', 'readme.md')))
    # U5 / U11: listings
    cfg = {'listing_page_marker': 'required'}
    sent = {'name': 'SENTINEL_qualification_0123abcd.json', 'md5': md5(b'S'), 'upload_by_dot': False}

    def L(pages, folder='CPS/qualification', nf=None, schema='cps.vm-drive-listing.v1'):
        p = root / 'listing.json'
        p.write_text(json.dumps({'schema': schema, 'folder': folder, 'name_filter': nf, 'pages': pages}))
        return p
    f = lambda n, i, m='0' * 32, size=1: {'name': n, 'id': i, 'createdTime': '2026-11-09T10:00:00.000Z', 'md5Checksum': m, 'size': str(size)}
    sf = f(sent['name'], 's0', sent['md5'])
    ok = L([{'files': [sf, f('A', 'i1')], 'nextPageToken': 't'}, {'files': [f('A', 'i2', '1' * 32)], 'kind': 'drive#fileList'}])
    lst = vm.parse_listing(ok, 'CPS/qualification', None, cfg, sent, b'S')
    t.check('U5: a paged listing parses; a same-name file with another md5 is a candidate copy', lambda: len(lst.copies('A')) == 2)
    for label, pages, code, kw in (
            ('last page with nextPageToken', [{'files': [sf], 'nextPageToken': 'x'}], 'LISTING_INCOMPLETE', {}),
            ('incompleteSearch', [{'files': [sf], 'incompleteSearch': True}], 'LISTING_INCOMPLETE', {}),
            ('a middle page without nextPageToken', [{'files': [sf], 'kind': 'k'}, {'files': [], 'kind': 'k'}], 'LISTING_INCOMPLETE', {}),
            ('no page marker', [{'files': [sf]}], 'LISTING_NO_PAGE_MARKER', {}),
            ('wrong folder', [{'files': [sf], 'kind': 'k'}], 'LISTING_WRONG_FOLDER', {'folder': 'CPS/setup'}),
            ('sentinel missing', [{'files': [f('A', 'i1')], 'kind': 'k'}], 'LISTING_SENTINEL_MISSING', {}),
            ('sentinel with another md5', [{'files': [f(sent['name'], 's0', '2' * 32)], 'kind': 'k'}], 'LISTING_SENTINEL_MISSING', {}),
            ('converted mimeType', [{'files': [sf, dict(f('A', 'i1'), mimeType='application/vnd.google-apps.document')], 'kind': 'k'}],
             'LISTING_CONVERTED_FILE', {}),
            ('a file without createdTime', [{'files': [sf, {'name': 'A', 'id': 'x'}], 'kind': 'k'}], 'LISTING_INVALID', {}),
            ('not the wrapper', [], 'LISTING_INVALID', {})):
        p = L(pages, **kw)
        got = halt_code(vm.parse_listing, p, 'CPS/qualification', None, cfg, sent, b'S')
        t.check(f'U11: {label}: {code}', lambda: got == code, got)
    # U6 / U14: the genesis line under the runner's Ledger
    gd = root / 'gl'
    gd.mkdir()
    entry = {k: 'x' for k in vm.GENESIS_KEYS}
    entry['type'] = 'genesis'
    with cj.Ledger(gd / 'LEDGER.jsonl', create=True) as led:
        led.append(entry)
    with cj.Ledger(gd / 'LEDGER.jsonl', create=False) as led:
        e2 = led.append({'type': 'prepare', 'case_id': 'x', 'reader': 'A', 'job_dir': '/x'})
    with cj.Ledger(gd / 'LEDGER.jsonl', create=False, readonly=True) as led:
        types = [e['type'] for e in led.entries]
    t.check('U6: a genesis line opens under cj.Ledger and a later runner append chains to it', lambda: e2['seq'] == 2 and types == ['genesis', 'prepare'])
    t.check('U14: the genesis key set never carries job_dir, case_id, reader or stage', lambda: not ({'job_dir', 'case_id', 'reader', 'stage'} & set(vm.GENESIS_KEYS)))
    raw = (gd / 'LEDGER.jsonl').read_bytes().split(b'\n')
    pre1 = h8b(raw[0] + b'\n')
    t.check('U6: a ledger prefix mismatch is seen by name (ledger8 of the first s lines)', lambda: pre1 != h8b(raw[0] + b'\n' + raw[1] + b'\n'))
    # U10: restart_eligible against cj.restart_problem with the file placed
    u10(t, root)
    # U12: bind tokens
    e = {'next': 'VISUAL_REVIEW', 'result': 'QA_EVIDENCE_GRADE', 'codes': ['X']}
    tok = vm.token_text('finish', 'A', '9990001', e, 'abcd1234', False)
    p = vm.parse_token(tok)
    flip = tok[:-6] + ('0' if tok[-6] != '0' else '1') + tok[-5:]
    t.check('U12: a bind token builds and parses; one changed character fails the check digits; none is a refusal', lambda: p and p['step'] == 'VISUAL_REVIEW'
            and vm.parse_token(flip) is None and vm.parse_token('none') == {'none': True} and vm.parse_token(forge_token(tok))['codes8'] != p['codes8'])
    # U13: fork rule
    def pn(kind, seq, l8, r8, f8, p8, tag='A', case='c'):
        return vm.parse_name(vm.package_name(kind, tag, 'L', seq, l8, r8, f8, 'f' * 8, p8, case))
    cp, fz = pn('CP', 9, 'a' * 8, 'b' * 8, '0' * 8, '1' * 8), pn('FZ', 9, 'a' * 8, 'b' * 8, 'c' * 8, '2' * 8)
    cp2 = pn('CP', 9, 'a' * 8, 'b' * 8, '0' * 8, '3' * 8)
    t.check('U13: a CP and an FZ at one seq with equal ledger8/record8 are no fork; two CPs are; a dead name does not count',
            lambda: vm.find_fork([cp, fz]) is None and vm.find_fork([cp, cp2]) is not None and vm.find_fork([cp, cp2], {cp2['name']}) is None
            and vm.find_fork([pn('CP', 3, 'a' * 8, 'b' * 8, '0' * 8, '4' * 8), pn('CP', 3, 'a' * 8, 'b' * 8, '0' * 8, '5' * 8), cp]) is not None)
    # U14: INDEX partial last line; SPLIT slices
    ip = root / 'INDEX.jsonl'
    ip.write_bytes(b'{"name":"a","kind":"x","origin":"made"}\n{"name":"b","ki')
    ix = vm.Index(ip)
    ok1 = list(ix.files) == ['a']
    ix.add(name='c', kind='x', origin='made')
    t.check('U14: an INDEX with a partial last line is read without it and repaired by the next append', lambda: ok1
            and vm.Index(ip).files.keys() == {'a', 'c'} and ip.read_bytes().endswith(b'\n'))
    data = os.urandom(2500)
    whole = root / 'BIG.bin'
    whole.write_bytes(data)
    class C:
        cfg = {'max_upload_bytes': 1000}
        index = vm.Index(root / 'IDX2.jsonl')
    sl = vm.upload_paths(C, whole, 'F')
    parts = {vm.parse_name(p.name)['k']: p for p in sl}
    t.check('U14: SPLIT_ slices round trip; a missing slice is a missing file', lambda: len(sl) == 3 and vm.join_slices(parts, 'BIG.bin') == data
            and vm.join_slices({k: v for k, v in parts.items() if k != 2}, 'BIG.bin') is None)


def h8b(b):
    return sha(b)[:8]


def u10(t, root):
    """U10: every branch of restart_problem, with FROZEN.json placed (runner) and with only its bytes (helper)."""
    prev = str(root / 'u10' / 'prev')
    good_fz = json.dumps({'files': [{'path': 'RUN_RECORD.json'}]}).encode()
    resp_fz = json.dumps({'files': [{'path': 'response/response.json'}]}).encode()
    writ_fz = json.dumps({'files': [{'path': 'run/A/output/response.json'}]}).encode()

    def L(freeze=True, inplace=False, fresp=False, stop=True, fsha=None):
        e = []
        if inplace:
            e.append({'type': 'record', 'job_dir': prev, 'stage': 'interrupt', 'completed': True, 'next': 'GENERATE'})
        if fresp:
            e.append({'type': 'record', 'job_dir': prev, 'stage': 'freeze_response', 'completed': True, 'next': 'x'})
        e.append({'type': 'record', 'job_dir': prev, 'stage': 'interrupt', 'completed': True,
                  'next': 'STOP_TECHNICAL_INTERRUPTION' if stop else 'GENERATE' if False else 'VISUAL_REVIEW'})
        if freeze:
            e.append({'type': 'freeze', 'job_dir': prev, 'frozen_sha256': fsha})
        return vm.LedgerView(e)
    branches = {'not frozen': (L(freeze=False), good_fz), 'in-place used': (L(inplace=True, fsha=sha(good_fz)), good_fz),
                'freeze_response': (L(fresp=True, fsha=sha(good_fz)), good_fz), 'no stop': (L(stop=False, fsha=sha(good_fz)), good_fz),
                'sha mismatch': (L(fsha='0' * 64), good_fz), 'response witness': (L(fsha=sha(resp_fz)), resp_fz),
                'written response': (L(fsha=sha(writ_fz)), writ_fz), 'eligible': (L(fsha=sha(good_fz)), good_fz)}
    for label, (led, fb) in branches.items():
        Path(prev).mkdir(parents=True, exist_ok=True)
        (Path(prev) / 'FROZEN.json').write_bytes(fb)
        want = cj.restart_problem(led, prev)
        shutil.rmtree(prev)
        got = vm.restart_eligible(led, prev, fb)
        t.check(f'U10: restart_eligible equals cj.restart_problem with the file placed: {label}', lambda: got == want
                and ((want is None) == (label == 'eligible')), (got, want))
    # C13: without the placed file, B's prepare check passes while A's restart is unused
    led = branches['eligible'][0]
    t.check('U10/C13: without FROZEN.json, cj.restart_problem cannot read it (so the runner would let B start): wrap places it',
            lambda: cj.restart_problem(led, prev) == vm.UNREADABLE_FROZEN)



# ------------------------------------------------------------------ E11, E21-E23: restore refusals with real packages
def repack(src, dest_dir, members_fn=None, manifest_fn=None, seq_delta=0, orig_name=None):
    """Rebuild a package with the helper's own writer after changing members or the manifest; returns the new name."""
    import tarfile
    with tarfile.open(src, 'r:gz') as tf:
        mem = [(m, tf.extractfile(m).read() if m.isreg() else None) for m in tf.getmembers()]
    man = json.loads(mem[0][1])
    body = {m.name: (m, b) for m, b in mem[1:]}
    if members_fn:
        members_fn(body, man)
    if manifest_fn:
        manifest_fn(man)
    import gzip
    import io
    tmp = Path(dest_dir) / '.repack.tgz'
    if tmp.exists():
        tmp.unlink()
    with open(tmp, 'wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as gz, \
            tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as tf:
        mb = vm.note_bytes(man)
        ti = tarfile.TarInfo('MANIFEST.json')
        ti.size, ti.mode = len(mb), 0o444
        tf.addfile(ti, io.BytesIO(mb))
        for name, (m, b) in body.items():
            if m.isreg():
                m.size = len(b)
            tf.addfile(m, io.BytesIO(b) if m.isreg() else None)
    p = vm.parse_name(orig_name or Path(src).name)
    led = body.get('ledger/LEDGER.jsonl', (None, None))[1]
    rec = body['job/RUN_RECORD.json'][1]
    name = vm.package_name(p['pkind'], p['tag'], p['seqkind'], p['seq'] + seq_delta, sha(led)[:8] if led else p['ledger8'], sha(rec)[:8],
                           p['frozen8'], p['fp8'], sha_file(tmp)[:8], p['case'])
    os.rename(tmp, Path(dest_dir) / name)
    return name


def set_member(body, man, name, data):
    m, _ = body[name]
    m.size = len(data)
    body[name] = (m, data)
    for x in man['members']:
        if x['path'] == name:
            x['bytes'], x['sha256'] = len(data), sha(data)


@scenario
def e11_restore_refusals(t):
    c = '9995001'
    w = World(t, 'e11_restore_refusals_w', cases=[c])
    dot = Dot(w)
    o = to_prepare(t, dot, w)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} start-note --job-dir {w.base / "qual/A" / c} --role V'))
    t.check('E11: setup: CP-F uploaded with its parts', lambda: newest_pkg(w, c).startswith('CP_A_') and names(w.drive, w.records, 'PNG_A_'), o)
    orig = w.drive
    folder = w.records
    cpf = newest_pkg(w, c)
    cpp = sorted(n for n in names(orig, folder, 'CP_A_'))[0]
    meta = {f['name']: f for f in orig.files(folder)}
    tmp = w.root / 'repacks'
    tmp.mkdir()
    k = [0]

    def attempt(label, code, mutate, plant=None, expect_ok=False):
        k[0] += 1
        d2 = orig.copy_to(w.root / f'drive_{k[0]}')
        mutate(d2)
        w.drive = d2
        w.wipe()
        if plant:
            plant()
        o = dot.session()
        got = o.codeword
        clean = not (w.base / 'ledger').exists() and not any((w.base / 'qual').glob('*/*'))
        if expect_ok:
            t.check(f'E11: {label}', lambda: o.code == 0 and code(o), o)
        else:
            t.check(f'E11: {label} -> {code}', lambda: got == code and (clean or code == 'RESTORE_TARGET_NOT_EMPTY'), (o, clean))
        w.drive = orig
        vm.remove_tree(w.root / f'drive_{k[0]}')
        return o

    def add(d2, name, data, created=None):
        e = d2.put(folder, name, data)
        if created:
            for f in d2.meta['files']:
                if f['id'] == e['id']:
                    f['created'] = created
            d2.save()

    def hide(prefix):
        return lambda d2: d2.hide.update(f['id'] for f in d2.files(folder) if f['name'].startswith(prefix))

    def edit(name, **kw):
        def m(d2):
            for f in d2.meta['files']:
                if f['name'] == name:
                    f.update(kw)
            d2.save()
        return m

    def with_repack(members_fn=None, manifest_fn=None, seq_delta=0, src=None):
        def m(d2):
            s_ = src or cpf
            n = repack(orig.root / meta[s_]['id'], tmp, members_fn, manifest_fn, seq_delta, orig_name=s_)
            d2.hide.update(f['id'] for f in d2.files(folder) if f['name'] == s_)
            add(d2, n, (tmp / n).read_bytes())
        return m
    p = vm.parse_name(cpp)
    fbytes = b'invented fork bytes'                     # intact by its name hash (T-02: a name failing its hash is no fork)
    fork = vm.package_name('CP', 'A', 'L', p['seq'], p['ledger8'], p['record8'], p['frozen8'], p['fp8'], sha(fbytes)[:8], c)
    attempt('a second package at an old seq', 'RESTORE_FORK', lambda d2: add(d2, fork, fbytes))
    jbytes = b'invented junk bytes'
    junk = vm.package_name('CP', 'A', 'L', p['seq'], p['ledger8'], p['record8'], p['frozen8'], p['fp8'], 'f0f0f0f0', c)
    attempt('T-02: a second package at an old seq whose only copy fails its own hash is no fork (restore proceeds)',
            lambda o_: session_note(w, o_)['restored']['package'] == cpf and any(r['name'] == junk for r in session_note(w, o_)['restored']['rejected_copies']),
            lambda d2: add(d2, junk, jbytes), expect_ok=True)
    attempt('the listing md5 contradicts the bytes', 'RESTORE_MD5_MISMATCH', edit(cpf, md5='0' * 32))
    attempt('the listing size contradicts the bytes', 'RESTORE_SIZE_MISMATCH', edit(cpf, size=1))
    part = sorted(names(orig, folder, 'PNG_A_'))[0]
    attempt('a PNG part missing', 'RESTORE_PARTS_INCOMPLETE', hide(part))
    attempt('a PNG part after its core', 'RESTORE_PARTS_AFTER_CORE', edit(part, created='2099-01-01T00:00:00.000Z'))
    attempt('a planted file at the job folder path', 'RESTORE_TARGET_NOT_EMPTY', lambda d2: None,
            plant=lambda: ((w.base / 'qual' / 'A').mkdir(parents=True, exist_ok=True), (w.base / 'qual' / 'A' / c).write_text('planted')))
    t.check('E11: TARGET_NOT_EMPTY uploads a STRAY archive first', lambda: any('STRAY_' in u for u in dot.history[-1].uploads), dot.history[-1])
    attempt('no GENESIS', 'RESTORE_GENESIS_MISSING', hide('GENESIS_'))

    def other_genesis(d2):
        g = next(f for f in d2.files(folder) if f['name'].startswith('GENESIS_'))
        doc = json.loads(d2.data(g['id']))
        doc['identity_line'] = doc['identity_line'].replace('"genesis"', '"genesis" ')
        d2.hide.add(g['id'])
        add(d2, g['name'], (json.dumps(doc, indent=1) + '\n').encode())
    attempt('a GENESIS whose identity is not ledger line 1', 'RESTORE_GENESIS_MISMATCH', other_genesis)
    bad = vm.package_name('CP', 'A', 'L', 2, '0' * 8, 'b' * 8, '0' * 8, p['fp8'], sha(b'x')[:8], c)
    attempt('a planted name with a wrong ledger8', 'RESTORE_LEDGER_PREFIX_MISMATCH', lambda d2: add(d2, bad, b'x'))

    def break_chain(body, man):
        led = body['ledger/LEDGER.jsonl'][1].split(b'\n')
        led[1] = led[1].replace(b'"seq":2', b'"seq":2 ')
        nb = b'\n'.join(led)
        m, _ = body['ledger/LEDGER.jsonl']
        m.size = len(nb)
        body['ledger/LEDGER.jsonl'] = (m, nb)
        man['ledger'].update(bytes=len(nb), sha256=sha(nb))
    attempt('a ledger whose chain is broken', 'RESTORE_LEDGER_CHAIN_BROKEN', with_repack(break_chain))
    import tarfile
    with tarfile.open(orig.root / meta[cpp]['id'], 'r:gz') as tf:
        old_rec = tf.extractfile('job/RUN_RECORD.json').read()

    def older_record(body, man):
        set_member(body, man, 'job/RUN_RECORD.json', old_rec)
        man['record']['sha256'] = sha(old_rec)
    attempt('a package repacked with an older record', 'RESTORE_RECORD_NOT_LEDGER', with_repack(older_record))

    def ahead(body, man):
        led = body['ledger/LEDGER.jsonl'][1]
        lp = tmp / 'L.jsonl'
        if lp.exists():
            lp.unlink()
        lp.write_bytes(led)
        real = cj.utc
        cj.utc = lambda: vm.iso(vm.now_dt() + vm.datetime.timedelta(days=1))
        try:
            with cj.Ledger(lp, create=False) as L:
                L.append({'type': 'note', 'note': 'invented entry one day ahead'})
        finally:
            cj.utc = real
        nb = lp.read_bytes()
        m, _ = body['ledger/LEDGER.jsonl']
        m.size = len(nb)
        body['ledger/LEDGER.jsonl'] = (m, nb)
        man['ledger'].update(bytes=len(nb), sha256=sha(nb), seq=man['ledger']['seq'] + 1)
    attempt('a ledger one day ahead of this clock', 'RESTORE_CLOCK_BEHIND', with_repack(ahead, seq_delta=1))
    attempt('a manifest naming another base', 'RESTORE_LAYOUT_MISMATCH', with_repack(manifest_fn=lambda man: man.update(job_dir='/elsewhere/qual/A/' + c)))

    def unsafe(body, man):
        m = tarfile.TarInfo('job/evil')
        m.type, m.linkname = tarfile.SYMTYPE, '/etc/passwd'
        body['job/evil'] = (m, None)
    attempt('a symlink member', 'ARCHIVE_UNSAFE_MEMBER', with_repack(unsafe))
    ai = sorted(names(orig, folder, 'AI_A_G1_'))[0]
    pa = vm.parse_name(ai)
    ai2 = ai.replace('_' + pa['tree8'] + '_', '_0badc0de_')

    def two_ai(d2):
        add(d2, ai2, orig.data(meta[ai]['id']))
        d2.hide.update(f['id'] for f in d2.files(folder) if f['name'] == cpf or f['name'].startswith('PNG_'))
    attempt('two AI archives of one attempt with different trees', 'RESTORE_AI_CONFLICT', two_ai)

    def wrong_inbox():
        (w.base / 'inbox').mkdir(parents=True, exist_ok=True)
        (w.base / 'inbox' / cpp).write_bytes(orig.data(meta[cpp]['id']))
    attempt('an older package in the inbox', 'RESTORE_NOT_NEWEST', lambda d2: None, plant=wrong_inbox)

    def start_ahead(d2):
        d2.hide.update(f['id'] for f in d2.files(folder) if f['name'] == cpf or f['name'].startswith(('PNG_', 'CP_A_L')) and f['name'] != cpp)
        st = next(f for f in orig.files(folder) if f['name'].startswith('START_A_G1_'))
        add(d2, st['name'].replace('START_A_', 'START_B_'), orig.data(st['id']))
    attempt('a START whose job package is not on Drive (E21)', 'RESTORE_NOTES_AHEAD_OF_PACKAGE', start_ahead)
    # E22: the only copy of CP-F truncated: it counts as not uploaded; restore uses CP-P with AI-G and names the rejected copy
    def trunc(d2):
        d2.hide.update(f['id'] for f in d2.files(folder) if f['name'] == cpf)
        add(d2, cpf, orig.data(meta[cpf]['id'])[:1000])
    fake = w.root / 'fakebin'
    fake.mkdir()
    (fake / 'pdftoppm').write_text('#!/bin/sh\nexit 1\n')
    os.chmod(fake / 'pdftoppm', 0o755)
    dot.env_extra = {'PATH': f'{fake}:{os.environ.get("PATH", "")}'}
    attempt('6.4 parts fallback (r2 R2-05: not the W8 scenario): re-render fails (pdftoppm broken): the parts are downloaded and the PNG set restored from them',
            lambda o_: session_note(w, o_)['restored']['png'] == 'parts' and any('PNG_' in h.text and 'DOWNLOAD' in h.text for h in dot.history[-4:]),
            lambda d2: None, expect_ok=True)
    dot.env_extra = {}
    o = attempt('E22: a truncated-only CP-F counts as not uploaded (restore uses the package before it)',
                lambda o_: session_note(w, o_)['restored']['package'] != cpf and session_note(w, o_)['restored']['rejected_copies'],
                trunc, expect_ok=True)



# ------------------------------------------------------------------ E14, E24: everyday jobs (one at a time, ending frozen), detached wraps
def everyday_inputs(w, case):
    d = w.base / 'everyday_inputs' / case
    d.mkdir(parents=True, exist_ok=True)
    src = d / 'source.xlsx'
    tcj.small_workbook(src)
    (d / 'JOB.json').write_bytes(w.job_json(case, src, w.base / 'runtime' / 'tables' / 'GLOSSARY.json'))
    (d / 'JOB_TITLE.json').write_bytes(w.title_json(case))


@scenario
def e14_everyday(t):
    c1, c2 = '9996001', '9996002'
    w = World(t, 'e14_everyday_w', mode='everyday', cases=[c1], cfg={'wrap_foreground_seconds': 1})
    dot = Dot(w)
    o = start_world(t, dot, w)
    t.check('E14: an everyday session with nothing in flight waits for the user', lambda: o.actions[0] == 'WAIT_FOR_USER_REQUEST'
            and o.actions[1].endswith("job-start --case '{CASE}'"), o)
    everyday_inputs(w, c1)
    dot.values['CASE'] = c1
    o = dot.run_line(o.actions[1][4:])
    t.check('E14: job-start writes INPUTS and prints the prepare of its run id', lambda: o.code == 0 and o.result['inputs'].startswith('INPUTS_E')
            and 'wrap prepare' in o.actions[0], o)
    run_tag = o.result['run_id']
    jd = w.base / 'jobs' / run_tag[1:] / c1
    o = dot.auto(o, halt=at_action(f'RUN {w.V} start-note --job-dir {jd} --role G'))
    t.check('E24: with wrap_foreground_seconds = 1 a wrap prints RUN wait (exit 11) and wait prints the same block',
            lambda: any(h.code == 11 and h.actions == [f'RUN {w.V} wait'] for h in dot.history if 'wrap prepare' in h.cmd)
            and any(h.result.get('runner_subcommand') == 'prepare' for h in dot.history if h.cmd.endswith(' wait')), [h for h in dot.history[-6:]])
    o2 = dot.vm('job-start', '--case', c1)
    t.check('E14: job-start while a job is not frozen is refused WRAP_RUN_IN_FLIGHT', lambda: o2.refused == 'WRAP_RUN_IN_FLIGHT', o2)
    o3 = dot.vm('wrap', 'interrupt', '--job-dir', jd, '--reason', 'TECHNICAL_X', '--started-utc', vm.utc(), '--ended-utc', vm.utc())
    t.check('E14: wrap interrupt in everyday mode is refused WRAP_INTERRUPT_EVERYDAY', lambda: o3.refused == 'WRAP_INTERRUPT_EVERYDAY', o3)
    dot.stop_after_upload = ('CP_', 'wait')
    o = dot.auto(o, halt=at_action(f'RUN {w.V} start-note --job-dir {jd} --role V'))
    if not o.actions[0].startswith(f'RUN {w.V} start-note --job-dir {jd} --role V'):
        o = dot.auto(o, halt=at_action(f'RUN {w.V} start-note --job-dir {jd} --role V'))
    t.check('E14: finish made CP-F (R seq: one chain per run)', lambda: vm.parse_name(newest_pkg(w, c1))['seqkind'] == 'R', o)
    o, sn = restore_cycle(t, dot, w, 'E14 after CP-F', 'NONE_IN_FLIGHT')
    t.check('E14: the everyday run was restored from CP-F with its inputs', lambda: sn['restored']['package'] == newest_pkg(w, c1)
            and (w.base / 'everyday_inputs' / c1 / 'JOB.json').is_file(), sn.get('restored'))
    o = dot.auto(o, halt=at_action('WAIT_FOR_USER_REQUEST'))
    t.check('E14: after visual-record status waits for the user and offers deliver-check or freeze', lambda: o.actions[0] == 'WAIT_FOR_USER_REQUEST'
            and dict(o.options).get('SEND_NOW', '').endswith(f'wrap deliver-check --job-dir {jd} --operator-model {MODEL}'), o)
    dot.stop_after_upload = ('CP_', 'wait')
    o = dot.run_line(dict(o.options)['SEND_NOW'][4:])
    o = dot.auto(o, halt=at_action('DELIVER '))
    o, sn = restore_cycle(t, dot, w, 'E14 after CP-D', 'NONE_IN_FLIGHT')
    t.check('E14: after the CP-D restore status prints DELIVER from the restored standard file (never deliver-check again)',
            lambda: o.actions[0].startswith(f'DELIVER folder={jd}/export/writer sha256=') and 'delivery-note' in o.actions[1], o)
    dsha = o.actions[0].split('sha256=')[1]
    std = next(f for f in (jd / 'export' / 'writer').iterdir() if f.suffix == '.xlsx' and sha_file(f) == dsha)
    copy = w.root / 'personal_copy.xlsx'
    shutil.copyfile(std, copy)
    logp = w.root / 'PERSONALIZATION_LOG.json'
    logp.write_text(json.dumps({'standard_file': {'sha256': dsha}, 'invented': True}))
    dot.values.update(COPY_FILE=str(copy), LOG_FILE=str(logp))
    dot.stop_after_upload = ('DELIVERY_PREPARED_', None)
    o = dot.run_line(o.actions[1][4:])
    t.check('E14: delivery-note --prepared uploads the copy, the log and the note to the profile deliveries and the note to the records folder',
            lambda: names(w.drive, 'Dots Folder/Profiles/invented-user/deliveries/', 'DELIVERY_PREPARED_') and names(w.drive, w.records, 'DELIVERY_PREPARED_')
            and not any(std.name in ln for ln in o.lines), o)
    o, sn = restore_cycle(t, dot, w, 'E14 after DELIVERY_PREPARED', 'NONE_IN_FLIGHT')
    t.check('E14: after the reset status asks the user whether the copy arrived', lambda: o.actions[0].startswith('ASK_USER_IF_RECEIVED')
            and 'RECEIVED' in dict(o.options), o)
    o = dot.auto(o, halt=at_action('WAIT_FOR_USER_REQUEST'))
    t.check('E14: sent, frozen, verified and evicted: the job ended frozen', lambda: names(w.drive, w.records, 'DELIVERY_SENT_')
            and newest_pkg(w, c1).startswith('FZ_') and not jd.exists(), o)
    # a second job, then a generator that wrote nothing: freeze, then one restart
    everyday_inputs(w, c2)
    dot.values['CASE'] = c2
    o = dot.run_line(o.actions[1][4:])
    t.check('E14: a second job-start is accepted after the first ended frozen', lambda: o.code == 0, o)
    jd2 = w.base / 'jobs' / o.result['run_id'][1:] / c2
    dot.conv['G'] = lambda jd, case, role, reader: None
    o = dot.auto(o, halt=lambda a, o_: a == 'WAIT_FOR_USER_REQUEST' or '--restart-of' in a)
    hs = [h for h in dot.history if 'incident' in h.cmd and 'AI_NOTHING_WRITTEN' in h.cmd]
    t.check('E14: an everyday generator that wrote nothing: incident, freeze, then status offers job-start --restart-of once',
            lambda: hs and newest_pkg(w, c2).startswith('FZ_') and '--restart-of' in o.actions[0], o)
    rs = o
    del dot.conv['G']
    tp_ = w.base / 'everyday_inputs' / c2 / 'JOB_TITLE.json'
    keep_ = tp_.read_bytes()
    tp_.write_bytes(keep_.replace(b'\n}', b' \n}'))
    o = dot.run_line(rs.actions[0][4:])
    tp_.write_bytes(keep_)
    t.check('E14/T-08: job-start --restart-of with inputs that differ from the original INPUTS is refused JOB_START_RESTART_INPUTS_DIFFER',
            lambda: o.refused == 'JOB_START_RESTART_INPUTS_DIFFER', o)
    o = dot.run_line(rs.actions[0][4:])
    t.check('E14: job-start --restart-of accepted once (INPUTS with the restart field)', lambda: o.code == 0 and o.result['inputs'].split('_')[2].startswith('E2'), o)
    o4 = dot.vm(*shlex.split(rs.actions[0][4:])[1:])
    t.check('E14/T-08: a second job-start while the restart run is only INPUTS (no package yet) is refused WRAP_RUN_IN_FLIGHT',
            lambda: o4.refused == 'WRAP_RUN_IN_FLIGHT', o4)
    del jd2
    # E24: a detached finish whose worker is killed before packaging: WORKER_DIED, package, then freeze (INTERRUPTED recorded)
    o = dot.auto(o, halt=at_action('WAIT_FOR_USER_REQUEST'))
    if 'NOT_NOW' in dict(o.options):
        o = dot.auto(dot.run_line(dict(o.options)['NOT_NOW'][4:]), halt=at_action('WAIT_FOR_USER_REQUEST'))
    t.check('E14: the restarted job closed by freeze when the user does not want the file now', lambda: o.actions[1].startswith('RUN ')
            and 'job-start' in o.actions[1], o)
    o5 = dot.vm(*shlex.split(rs.actions[0][4:])[1:])
    t.check('E14/T-28: after the restart run is frozen and evicted, a second restart of the same run is refused exactly JOB_START_RESTART_USED',
            lambda: o5.refused == 'JOB_START_RESTART_USED', o5)
    everyday_inputs(w, '9996003')
    dot.values['CASE'] = '9996003'
    o = dot.run_line(o.actions[1][4:])
    jd3 = w.base / 'jobs' / o.result['run_id'][1:] / '9996003'
    o = dot.auto(o, halt=lambda a, o_: 'wrap finish' in a)
    raw = dot.call(shlex.split(o.actions[0][4:]))
    for _ in range(3):
        if raw.code != 10:
            break
        dot.fetch(raw)
        raw = dot.call(shlex.split(o.actions[0][4:]))
    d = json.loads((w.base / 'outbox' / 'DETACHED.json').read_text())
    time.sleep(2)
    try:
        os.killpg(d['pid'], signal.SIGKILL)
    except ProcessLookupError:
        pass
    time.sleep(1)
    o = dot.vm('wait')
    t.check('E24: a worker killed before packaging: wait prints STOP WORKER_DIED and NEXT package', lambda: raw.code == 11 and o.stop == 'WORKER_DIED'
            and o.actions[0].endswith(f'package --job-dir {jd3}'), (raw, o))
    o = dot.run_line(o.actions[0][4:])
    t.check('E24: package after a killed stage prints wrap freeze (the runner records INTERRUPTED)', lambda: 'wrap freeze' in o.actions[0], o)
    o = dot.auto(o, halt=at_action('WAIT_FOR_USER_REQUEST'))
    t.check('E24: the killed job ended frozen with an INTERRUPTED finish', lambda: newest_pkg(w, '9996003').startswith('FZ_')
            and any(e.get('result') == 'INTERRUPTED' for e in fz_record(w, '9996003')['stages']), o)


def fz_record(w, case):
    import tarfile
    n = newest_pkg(w, case)
    f = next(f for f in w.drive.files(w.records) if f['name'] == n)
    with tarfile.open(w.drive.root / f['id'], 'r:gz') as tf:
        return json.loads(tf.extractfile('job/RUN_RECORD.json').read())


# ------------------------------------------------------------------ 11.6: session_start.sh
@scenario
def s_session_start(t):
    p = subprocess.run(['bash', '-n', str(SESSION_SH)], capture_output=True, text=True)
    t.check('11.6: bash -n session_start.sh', lambda: p.returncode == 0, p.stderr)
    w = World(t, 's_session_start_w', cases=['9997001'])
    commit = HEAD
    (w.tools / 'var' / 'cps_vm_session_ok').write_text(f'{w.boot} {commit}')
    def run(env=None, args=('--operator-model', MODEL), script=None):
        e = dict(w.env if env is None else env)
        r = subprocess.run(['bash', str(script or (w.base / 'repo' / 'deploy' / 'vm' / 'session_start.sh')), *args], capture_output=True, text=True, env=e)
        t.outputs.append(r.stdout)
        return r
    e = dict(w.env)
    e.pop('HOME')
    r = run(env=e)
    t.check('11.6: HOME unset: REFUSED SESSION_HOME', lambda: r.returncode == 4 and 'REFUSED: SESSION_HOME' in r.stdout, r.stdout)
    r = run(args=())
    t.check('11.6: no operator model: SESSION_OPERATOR_MODEL', lambda: 'REFUSED: SESSION_OPERATOR_MODEL' in r.stdout, r.stdout)
    r = run(args=('--operator-model', '<ME>'))
    t.check('11.6: operator model <ME>: SESSION_OPERATOR_MODEL', lambda: 'REFUSED: SESSION_OPERATOR_MODEL' in r.stdout, r.stdout)
    (w.base / '.git').mkdir()
    r = run()
    t.check('11.6: a .git in BASE: SESSION_BASE_IS_REPOSITORY', lambda: 'REFUSED: SESSION_BASE_IS_REPOSITORY' in r.stdout, r.stdout)
    (w.base / '.git').rmdir()
    other = w.root / 'other_clone'
    shutil.copytree(REPO / 'deploy' / 'vm', other / 'deploy' / 'vm')
    r = run(script=other / 'deploy' / 'vm' / 'session_start.sh')
    t.check('11.6: run from another clone: SESSION_REPO_NOT_AT_BASE', lambda: 'REFUSED: SESSION_REPO_NOT_AT_BASE' in r.stdout, r.stdout)
    for stale in (w.base / 'qual' / 'A' / '.cps_vm_stage_x', w.base / 'jobs' / '20261109T000000Z' / '.cps_vm_stage_y', w.base / '.cps_vm_stage_ledger_1'):
        stale.mkdir(parents=True)
        (stale / 'f').write_text('x')
        os.chmod(stale, 0o555)
    (w.base / 'vm.sh').unlink()
    inbox = w.base / 'inbox'
    (inbox / 'cps').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(w.static / 'FOLDER_MANIFEST.md', inbox / 'cps' / 'FOLDER_MANIFEST.md')
    r = run()
    t.check('11.6: first run (setup skipped by the marker): exit 10 with the listing and kit lines', lambda: r.returncode == 10
            and 'setup: already done in this boot' in r.stdout and ('SAVE_DRIVE_LISTING' in r.stdout or 'DOWNLOAD' in r.stdout), r.stdout[-800:])
    t.check('11.6: leftover stage folders were removed; vm.sh written and executable; BASE/ledger never created',
            lambda: not list(w.base.glob('.cps_vm_stage_*')) and not list((w.base / 'qual' / 'A').glob('.cps_vm_stage_*'))
            and os.access(w.base / 'vm.sh', os.X_OK) and not (w.base / 'ledger').exists(), r.stdout[-400:])
    dot = Dot(w)
    for _ in range(5):
        if r.returncode != 10:
            break
        dot.fetch(Out(r.returncode, r.stdout, 'session_start'))
        r = run()
    o = Out(r.returncode, r.stdout, 'session_start')
    dot.do(o)
    t.check('11.6: after the Dot does the lines, exit 0 (fresh session)', lambda: r.returncode == 0 and o.result.get('mode') == 'fresh', r.stdout[-800:])
    (inbox / 'cps').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(w.static / 'FOLDER_MANIFEST.md', inbox / 'cps' / 'FOLDER_MANIFEST.md')
    w.drive.listing(w.records, inbox / 'DRIVE_LISTING.json')
    w.drive.listing(FOLDERS['setup'], inbox / 'SETUP_LISTING.json')
    r = run()
    o2 = Out(r.returncode, r.stdout, 'session_start')
    t.check('11.6: a second run in the same boot prints no restore and re-prints no upload already listed', lambda: r.returncode == 0
            and o2.result.get('mode') != 'restore' and len(o2.uploads) == 1 and 'SESSION_' in o2.uploads[0], r.stdout[-800:])


# ------------------------------------------------------------------ U7, U8: fingerprint and kit
@scenario
def u_fingerprint_kit(t):
    w = World(t, 'u_fingerprint_kit_w', cases=['9998001'])
    fonts = w.root / 'fonts'
    fonts.mkdir()
    some = sorted(Path('/usr/share/fonts').rglob('*.ttf'))[:1]
    if some:
        shutil.copyfile(some[0], fonts / 'a.ttf')
    conf = w.root / 'fonts.conf'
    conf.write_text(f'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>{fonts}</dir>'
                    f'<cachedir>{w.root}/fccache</cachedir></fontconfig>')
    env = dict(w.env, FONTCONFIG_FILE=str(conf))

    def fp(e):
        p = subprocess.run([w.V, 'fingerprint'], capture_output=True, text=True, env=e)
        return json.loads(p.stdout.splitlines()[0][8:])['fingerprint_sha256']
    a, b = fp(env), fp(env)
    t.check('U7: two fingerprint computations are equal', lambda: a == b)
    t.check('U7: TMPDIR or the boot id does not change it', lambda: fp(dict(env, TMPDIR=str(w.root))) == a)
    (w.tools / 'env.sh').write_text((w.tools / 'env.sh').read_text() + '# changed\n')
    c = fp(env)
    t.check('U7: changing TOOLS/env.sh changes it', lambda: c != a)
    t.check('U7: a .ttf font exists on this machine for the font-change check (r2 R2-08: never skipped silently)', lambda: bool(some))
    if some:
        shutil.copyfile(some[0], fonts / 'b.ttf')
        t.check('U7: adding a font file under the fontconfig dir changes it', lambda: fp(env) != c)
    # U8: kits
    dot = Dot(w)
    kp = sorted((w.static / 'cps_runtime').glob('*.zip'))[-1]
    good = kp.read_bytes()

    def bad_kit(label, code, make, row_of_good=False):
        data = make(good)
        kp.write_bytes(data)
        row = good if row_of_good else data
        (w.static / 'FOLDER_MANIFEST.md').write_text('| Path | Bytes | sha256 |\n|---|---:|---|\n'
                                                     f'| `cps_runtime/{kp.name}` | {len(row)} | `{sha(row)}` |\n')
        vm.remove_tree(w.base / 'runtime') if (w.base / 'runtime').exists() else None
        o = dot.session()
        t.check(f'U8: {label}: {code}', lambda: o.codeword == code, o)
        kp.write_bytes(good)

    def rezip(extra=None, drop_sum=False, tamper=None):
        def mk(data):
            import io
            zin = zipfile.ZipFile(io.BytesIO(data))
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w') as z:
                for i in zin.infolist():
                    b_ = zin.read(i)
                    if i.filename == 'SHA256SUMS' and drop_sum:
                        continue
                    if tamper and i.filename == tamper:
                        b_ = b_ + b' '
                    z.writestr(i, b_)
                for zi, b_ in (extra or []):
                    z.writestr(zi, b_)
            return buf.getvalue()
        return mk
    zs = zipfile.ZipInfo('../evil.txt')
    bad_kit('a zip-slip member', 'ARCHIVE_UNSAFE_MEMBER', rezip([(zs, b'x')]))
    zl = zipfile.ZipInfo('link')
    zl.external_attr = (0o120777 << 16)
    bad_kit('a symlink member', 'ARCHIVE_UNSAFE_MEMBER', rezip([(zl, b'/etc/passwd')]))
    bad_kit('a member that differs from SHA256SUMS', 'KIT_SUMS_MISMATCH', rezip(tamper='RELEASE.json'))
    bad_kit('a kit whose size differs from the manifest row (not repairable)', 'KIT_NOT_VERIFIED', lambda d: d + b'x', row_of_good=True)
    # a base64 slip in the maintainer's upload: repaired by verify_drive_files.py
    import base64
    def slip(d):
        z = zipfile.ZipFile(__import__('io').BytesIO(d))
        info = z.getinfo('RELEASE.json')
        off = info.header_offset + 30 + len(info.filename) + len(info.extra) + 5
        t64 = bytearray(base64.b64encode(d))
        i = off * 4 // 3 + 1
        t64[i] = ord('A') if t64[i] != ord('A') else ord('B')
        return base64.b64decode(bytes(t64))
    data = slip(good)
    (w.static / 'cps_runtime' / kp.name).write_bytes(data)
    (w.static / 'FOLDER_MANIFEST.md').write_text('| Path | Bytes | sha256 |\n|---|---:|---|\n'
                                                 f'| `cps_runtime/{kp.name}` | {len(good)} | `{sha(good)}` |\n')
    o = dot.session()
    sn = session_note(w, o) if o.result.get('session_note') else {}
    t.check('U8: a base64-slip kit is repaired (kit.repaired) and the repaired copy is uploaded to CPS/reports', lambda: o.code == 0
            and sn['kit']['repaired'] is True and any(u.endswith('-> CPS/reports') for u in o.uploads), o)
    (w.static / 'FOLDER_MANIFEST.md').write_text('| Path | Bytes | sha256 |\n|---|---:|---|\n')
    o = dot.session()
    t.check('U8: a manifest without the kit row: KIT_NOT_IN_MANIFEST', lambda: o.codeword == 'KIT_NOT_IN_MANIFEST', o)



# ------------------------------------------------------------------ E2, E15, E19, E23, E25, E26: guards and refusals
def runner_direct(w, *argv):
    p = subprocess.run([sys.executable, '-I', '-B', str(RUNNER), *[str(a) for a in argv]], capture_output=True, text=True, env=w.env)
    lines = [x for x in p.stdout.splitlines() if x.strip()]
    return p.returncode, (lines[-1] if lines else '')


@scenario
def e15_guards(t):
    import fcntl
    c = '9999101'
    w = World(t, 'e15_guards_w', cases=[c], nonattempts=['9999191'])
    dot = Dot(w)
    o = to_prepare(t, dot, w)
    rel, adm = w.base / 'runtime/RELEASE.json', w.base / 'runtime/qualification/ADMISSION_QUALIFICATION.json'
    jdir = w.base / 'runtime/qualification/jobs' / c
    jd = w.base / 'qual' / 'A' / c
    # E2: the ledger folder gone (a partial wipe): runner prepare and nonattempt refuse QUALIFICATION_LEDGER_PATH and create nothing
    aside = w.root / 'ledger_aside'
    os.rename(w.base / 'ledger', aside)
    code, last = runner_direct(w, 'prepare', '--release', rel, '--job', jdir / 'JOB.json', '--job-title-file', jdir / 'JOB_TITLE.json',
                               '--jobs-root', w.base / 'qual' / 'A', '--reader', 'A', '--qualification', '--admission', adm)
    code2, last2 = runner_direct(w, 'nonattempt', '--release', rel, '--admission', adm, '--case', '9999191', '--reader', 'A',
                                 '--jobs-root', w.base / 'qual' / 'nonattempts_A')
    t.check('E2/C1: runner prepare and nonattempt refuse QUALIFICATION_LEDGER_PATH, no ledger folder created', lambda: last == 'REFUSED: QUALIFICATION_LEDGER_PATH'
            and last2 == 'REFUSED: QUALIFICATION_LEDGER_PATH' and not (w.base / 'ledger').exists() and not jd.exists(), (last, last2))
    code3, last3 = runner_direct(w, 'scope-finish', '--job-dir', jd, '--reader-response', '/x/y.json')
    t.check('E2/C5: scope-finish on a missing job folder refuses NO_RUN_RECORD', lambda: last3 == 'REFUSED: NO_RUN_RECORD', last3)
    ow = dot.run_line(o.actions[0][4:])
    if ow.actions == [f'RUN {w.V} wait']:
        ow = dot.auto(ow, halt=lambda a, o_: not a.endswith(' wait'))
    t.check('E2: wrap prepare is refused through the runner and makes no package', lambda: ow.refused == 'RUNNER_QUALIFICATION_LEDGER_PATH'
            and not ow.uploads and not (w.base / 'ledger').exists(), ow)
    os.rename(aside, w.base / 'ledger')
    # E26: a boot change with the disk kept: local mode with a pending incident
    w.new_boot()
    o = dot.session()
    sn = session_note(w, o)
    t.check('E26: a reboot that kept the disk: local mode, boot_changed_without_restore, pending incident', lambda: sn['mode'] == 'local'
            and sn['boot_changed_without_restore'] is True and o.state.get('pending_incident') == 'yes', o)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} recheck'))
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    # E15: prepare, then the isolation guards of start-note
    o = dot.auto(o, halt=at_action(f'RUN {w.V} start-note'))
    sn_line = o.actions[0][4:]
    raw = dot.call(shlex.split(sn_line))
    t.check('E15: start-note before the CP-P narrow listing: START_PACKAGE_NOT_CONFIRMED (exit 10)', lambda: raw.code == 10
            and raw.result.get('code') == 'START_PACKAGE_NOT_CONFIRMED' and any('name=CP_' in f for f in raw.fetch), raw)
    dot.fetch(raw)
    junk = w.base / 'inbox' / 'junk.txt'

    def guard(label, code, plant, unplant):
        plant()
        r = dot.run_line(sn_line)
        unplant()
        t.check(f'E15: start-note with {label}: {code}', lambda: r.refused == code, r)
    guard('a non-empty inbox', 'START_INBOX_PRESENT', lambda: junk.write_text('x'), lambda: junk.unlink())
    other = w.base / 'qual' / 'B' / 'x'
    guard('another job folder', 'START_OTHER_RUN_PRESENT', lambda: other.mkdir(parents=True), lambda: other.rmdir())
    stray = w.base / 'transcripts' / 'other_run.txt'
    guard('a stray transcript', 'START_TRANSCRIPTS_PRESENT', lambda: stray.write_text('x'), lambda: stray.unlink())
    outx = jd / 'run' / 'A' / 'output' / 'early.txt'
    guard('a non-empty output folder', 'START_OUTPUT_NOT_EMPTY', lambda: outx.write_text('x'), lambda: outx.unlink())
    relraw = rel.read_bytes()
    d = json.loads(relraw)
    del d['pinned_files_sha256']['deploy/vm/cps_vm.py']
    os.chmod(rel, 0o644)
    rel.write_text(json.dumps(d))
    r = dot.vm('status')
    rel.write_bytes(relraw)
    os.chmod(rel, 0o444)
    t.check('E15: a release without the helper pin: LAYOUT_HELPER_NOT_PINNED', lambda: r.refused == 'LAYOUT_HELPER_NOT_PINNED', r)
    o = dot.run_line(sn_line)
    t.check('E15: start-note passes once the guards are clear', lambda: o.code == 0 and o.result.get('attempt') == 1, o)
    r = dot.vm('incident', '--classification', 'AI_NO_CONVERSATION', '--job-dir', jd, '--role', 'G', '--conversation-ended')
    t.check('E19: AI_NO_CONVERSATION inside a session is refused INCIDENT_NOT_AFTER_RESTORE', lambda: r.refused == 'INCIDENT_NOT_AFTER_RESTORE', r)
    tcj.stand_in_response(None, jd, c, reader='A')
    tcj.generation_record(jd, c)
    fin = ['wrap', 'finish', '--job-dir', jd, '--response', jd / 'run/A/output/response.json', '--generator-model', 'stand-in (invented test)',
           '--generation-record', jd / 'run/GENERATION_RECORD.json', '--operator-model', MODEL]
    r = dot.vm(*fin)
    t.check('E15: wrap finish without AI-G: AI_ARCHIVE_MISSING', lambda: r.refused == 'AI_ARCHIVE_MISSING', r)
    r = dot.vm('ai-archive', '--job-dir', jd, '--role', 'G')
    t.check('E15: ai-archive makes AI-G (response present) and prints the finish line', lambda: r.result.get('response_present') is True
            and 'wrap finish' in r.actions[0], r)
    raw = dot.call([w.V, *[str(x) for x in fin]])
    t.check('E15: wrap finish before the narrow listing of AI-G: AI_ARCHIVE_NOT_CONFIRMED (exit 10)', lambda: raw.code == 10
            and raw.result.get('code') == 'AI_ARCHIVE_NOT_CONFIRMED', raw)
    extra = jd / 'run/A/output/late.txt'
    extra.write_text('written after the archive')
    r = dot.vm(*fin)
    t.check('E15: output changed after the archive: wrap refuses AI_ARCHIVE_STALE', lambda: r.refused == 'AI_ARCHIVE_STALE', r)
    r = dot.vm('ai-archive', '--job-dir', jd, '--role', 'G')
    t.check('E15: ai-archive after the output changed: STOP AI_OUTPUT_CHANGED_AFTER_ARCHIVE', lambda: r.stop == 'AI_OUTPUT_CHANGED_AFTER_ARCHIVE', r)
    extra.unlink()
    fd = os.open(jd, os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    r = dot.vm('package', '--job-dir', jd)
    os.close(fd)
    t.check('E15: JOB_BUSY prints wait then status, never the same command', lambda: r.code == 4 and r.result.get('code') == 'JOB_BUSY'
            and r.actions == [f'RUN {w.V} wait', f'RUN {w.V} status'], r)
    lfd = os.open(w.base / 'outbox' / '.lock', os.O_RDWR)
    fcntl.flock(lfd, fcntl.LOCK_EX)
    r = dot.vm('start-note', '--job-dir', jd, '--role', 'G')
    os.close(lfd)
    t.check('E15: HELPER_BUSY while another helper process holds the lock', lambda: r.refused == 'HELPER_BUSY', r)
    bad = Out(0, 'RESULT: {}\nNEXT: RUN /x/vm.sh incident --seen {FOO}\n', 'synthetic')
    n0 = len(t.results)
    Dot(w).grammar(bad, '')
    flagged = len(t.results) > n0 and not t.results[-1]['passed']
    if flagged:
        t.results.pop()
    t.check('E15: FakeDot rejects a RUN line with an unknown {TOKEN}', lambda: flagged)
    # E23: CP-F lands late, after the restore that re-runs finish: recheck STOPs RESTORE_STALE_LISTING
    dot.fetch(raw)
    dot.late = [lambda n: n.startswith('CP_')]
    o = dot.auto(dot.vm(*fin), halt=at_action(f'RUN {w.V} start-note'))
    dot.late = []
    w.wipe()
    o = dot.session()
    o = dot.auto(o, halt=at_action(f'RUN {w.V} recheck'))
    dot.land_late()
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    r = dot.vm('recheck')
    t.check('E23: a package that lands after the restore listing: recheck STOPs RESTORE_STALE_LISTING', lambda: r.stop == 'RESTORE_STALE_LISTING', r)


@scenario
def e25_genesis_killed(t):
    w = World(t, 'e25_genesis_killed_w', cases=['9999201'])
    dot = Dot(w)
    start_world(t, dot, w)
    code = ("import importlib.util, sys\n"
            f"s = importlib.util.spec_from_file_location('h', {str(w.base / 'repo/deploy/vm/cps_vm.py')!r})\n"
            "m = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
            "def boom():\n    raise SystemExit(9)\n"
            "m.genesis_hook = boom\nsys.exit(m.main(['genesis', '--first-ledger']))\n")
    p = subprocess.run([sys.executable, '-I', '-B', '-c', code], capture_output=True, text=True, env=w.env)
    t.check('E25: genesis killed between staging and rename leaves no BASE/ledger', lambda: p.returncode == 9 and not (w.base / 'ledger').exists()
            and list(w.base.glob('.cps_vm_stage_ledger_*')), p.stderr[-500:])
    o = dot.vm('status')
    t.check('E25: status still prints genesis after the killed attempt', lambda: o.actions[0].endswith('genesis --first-ledger'), o)
    o = dot.vm('genesis', '--first-ledger')
    t.check('E25: genesis completes and removes the leftover stage folder', lambda: o.code == 0 and (w.base / 'ledger/LEDGER.jsonl').is_file()
            and not list(w.base.glob('.cps_vm_stage_ledger_*')), o)
    w2 = World(t, 'e25_genesis_killed_w2', cases=['9999202'])
    d2 = Dot(w2)
    start_world(t, d2, w2)
    (w2.base / 'ledger').mkdir()
    (w2.base / 'ledger' / 'LEDGER.jsonl').write_text('{"not": "a genesis line"}\n')
    o = d2.session()
    t.check('E25: a BASE/ledger without a genesis line: STOP LEDGER_NO_IDENTITY', lambda: o.stop == 'LEDGER_NO_IDENTITY', o)


# ------------------------------------------------------------------ round 2 (review triage T-01..T-29): regression tests
def wait_done(dot, o, limit=60):
    """Follow RUN wait lines until the detached command printed its block."""
    for _ in range(limit):
        if o.code != 11:
            return o
        o = dot.vm('wait')
    return o


def run_wrap(dot, line):
    """Run a printed wrap line (narrow-listing rounds included) and return its final block."""
    o = dot.run_line(line)
    for _ in range(6):
        if o.code == 10 and o.actions == ['RUN_SAME_COMMAND_AGAIN']:
            o = dot.run_line(line)
            continue
        break
    return wait_done(dot, o)


def incident_notes(w):
    return [json.loads((w.base / 'outbox' / f).read_text()) for f in sorted(os.listdir(w.base / 'outbox')) if f.startswith('INCIDENT_')]


@scenario
def u_round2(t):
    """Units for T-01 (a dead newest revision never lets an earlier one stand in), T-02 (incident rejected_copies make a name
    dead), T-04/T-25 (unsafe PNG paths, modes and package members), T-07 (partial outputs are repaired), T-12 (relist)."""
    import tarfile
    root = t.work / 'u_round2_w'
    root.mkdir()
    ix = vm.Index(root / 'IDX.jsonl')

    class C:
        index = ix
    r1, r2 = 'AI_A_V1_0123abcd_c.tgz', 'AI_A_V1r2_89abcdef_c.tgz'
    for n, i in ((r1, 'i1'), (r2, 'i2')):
        ix.add(name=n, kind='ai', origin='listed', drive_id=i, tag='A', role='V', attempt=1, case_id='c', created_utc='x')
    ok_before = [e['name'] for e in vm.ai_archives(C, 'A', 'V', 1, 'c')] == [r1, r2] and not vm.ai_lost(C, 'A', 'V', 1, 'c')
    ix.event('rejected', r2, drive_id='i2', why='archive')
    t.check('T-01 unit: when every copy of the newest revision fails, ai_archives is empty (r1 never stands in) and ai_lost names r2',
            lambda: ok_before and vm.ai_archives(C, 'A', 'V', 1, 'c') == [] and vm.ai_lost(C, 'A', 'V', 1, 'c') == [r2])
    pk = vm.package_name('CP', 'A', 'L', 6, 'a' * 8, 'b' * 8, '0' * 8, 'c' * 8, 'd' * 8, 'c')
    ix.add(name=pk, kind='package', origin='listed', drive_id='p1', tag='A', case_id='c', seq=6)
    alive = not vm.dead(C, pk)
    ix.add(name='INCIDENT_20261109T101500Z_0123abcd_AI_ARCHIVED_A_G1_c.json', kind='incident', origin='restored', tag='A', case_id='c',
           content={'rejected_copies': [{'name': pk, 'drive_id': 'p1', 'why': 'sha8'}]})
    t.check('T-02 unit: a package name every copy of which an INCIDENT\'s rejected_copies names is dead (INDEX rejected events lost)',
            lambda: alive and vm.dead(C, pk) and vm.find_fork([vm.parse_name(pk), vm.parse_name(pk.replace('_dddddddd_', '_eeeeeeee_'))],
                                                                vm.dead_names(C, [pk])) is None)
    # T-04 / T-25: manifests and members
    good = {'tag': 'A', 'case_id': 'c', 'members': [{'path': 'job', 'type': 'dir', 'mode': 0o755}],
            'png': {'files': [{'path': 'job/qa/visual_internal/page-0001.png', 'mode': 0o444}],
                    'parts': [{'name': 'PNG_A_0123abcd_01of01_c.part'}]}}
    bads = {'dotdot': ('job/qa/visual_internal/../../../../ESCAPE.png', 0o444), 'absolute': ('/tmp/ABSOLUTE.png', 0o444),
            'outside the QA folders': ('job/RUN_RECORD.json', 0o444), 'setuid mode': ('job/qa/visual_internal/x.png', 0o4755)}
    t.check('T-04 unit: a safe PNG set passes', lambda: vm.pkg_manifest_problem(good) is None)
    for label, (path, mode) in bads.items():
        m = json.loads(json.dumps(good))
        m['png']['files'][0] = {'path': path, 'mode': mode}
        t.check(f'T-04 unit: a PNG path or mode refused before any read: {label}', lambda: vm.pkg_manifest_problem(m) is not None)
    m = json.loads(json.dumps(good))
    m['png']['parts'][0]['name'] = '../../PNG_A_0123abcd_01of01_c.part'
    t.check('T-04 unit: a PNG part name that is not a part name of this tag and case is refused', lambda: vm.pkg_manifest_problem(m) is not None)
    m = json.loads(json.dumps(good))
    m['members'].append({'path': 'ledger/x', 'type': 'file', 'mode': 0o644})
    t.check('T-25 unit: a core member outside job/ is refused', lambda: vm.pkg_manifest_problem(m) is not None)
    stg = vm.Staging(root / 'stage_target')
    stg.begin(0o755)
    t.check('T-04 unit: Staging refuses a path that leaves the stage, and a setuid mode', lambda: halt_code(stg.add_file, '../x', b'x', 0o644) == 'ARCHIVE_UNSAFE_MEMBER'
            and halt_code(stg.add_file, 'y', b'y', 0o4755) == 'ARCHIVE_UNSAFE_MEMBER' and not (root / 'x').exists())
    stg.add_file('ok.txt', b'ok', 0o444)
    stg.finish()
    t.check('T-24 unit: Staging sets the root mode before the rename', lambda: stat_mode(root / 'stage_target') == 0o755)

    def ti(name, typ=tarfile.REGTYPE, size=0, mode=0o644):
        x = tarfile.TarInfo(name)
        x.type, x.size, x.mode = typ, size, mode
        return x
    bad_tar(root / 'ledger_x.tgz', [(ti('ledger/x', size=1), b'x')], {'members': [], 'ledger': None})
    t.check('T-25 unit: an archive member ledger/x is refused (only ledger/LEDGER.jsonl)', lambda: halt_code(
        lambda: vm.Archive(root / 'ledger_x.tgz', ('MANIFEST.json', 'ledger', 'job'))) == 'ARCHIVE_UNSAFE_MEMBER')
    # T-07: a slice left partial by a failed write is rewritten; a failed write leaves no file
    data = os.urandom(2500)
    big = root / 'BIG2.bin'
    big.write_bytes(data)

    class C2:
        cfg = {'max_upload_bytes': 1000}
        index = vm.Index(root / 'IDX3.jsonl')
    sl = vm.upload_paths(C2, big, 'F')
    sl[1].unlink()
    sl[1].write_bytes(data[1000:1300])              # the state a disk-full write leaves
    sl2 = vm.upload_paths(C2, big, 'F')
    t.check('T-07 unit: a partial slice under the final name is rewritten to the bytes INDEX records', lambda: [p.name for p in sl2] == [p.name for p in sl]
            and sl2[1].read_bytes() == data[1000:2000] and vm.sha_file(sl2[1]) == C2.index.get(sl2[1].name)['sha256'])
    real = os.fsync

    def boom(fd):
        raise OSError(28, 'No space left on device (invented)')
    os.fsync = boom
    try:
        got = None
        try:
            vm.write_new(root / 'NEW_OUT.json', b'{}')
        except OSError as e:
            got = e.errno
    finally:
        os.fsync = real
    t.check('T-07 unit: a write_new that fails leaves neither the final name nor a temporary file', lambda: got == 28
            and not (root / 'NEW_OUT.json').exists() and not list(root.glob('.tmp_*')))


@scenario
def t01_ai_rejected(t):
    """T-01, T-03 (E22 for AI archives): a cut-off local download is downloaded again; an AI archive damaged on Drive gives
    only AI_WRITTEN_LOST, never AI_NOTHING_WRITTEN or a second conversation."""
    c = '9991101'
    w = World(t, 't01_ai_rejected_w', cases=[c])
    dot = Dot(w)
    o = to_prepare(t, dot, w)
    dot.stop_after_upload = ('AI_', 'ai-archive')
    o = dot.auto(o)
    jd = w.job_dir('A', c)
    ai = names(w.drive, w.records, 'AI_A_G1_')
    t.check('T-01 setup: AI-G (response present) is on Drive', lambda: len(ai) == 1, ai)
    orig = w.drive
    # T-03: the local download of AI-G is cut off once; Drive's copy is intact
    w.drive = orig.copy_to(w.root / 'drive_t03')
    real = dot.fetch
    cut = {'n': 0}

    def fetch(o_):
        real(o_)
        for ln in o_.fetch:
            m = LINE_RE['DOWNLOAD'].match(ln)
            if m and m.group(2).startswith('AI_') and cut['n'] == 0:
                p = Path(m.group(3))
                p.write_bytes(p.read_bytes()[:500])
                cut['n'] += 1
    dot.fetch = fetch
    w.wipe()
    o = dot.session()
    dot.fetch = real
    sn = session_note(w, o)
    dl = [h for h in dot.history[-12:] if any(f'name={ai[0]}' in x for x in h.fetch)]
    t.check('T-03: a cut-off local download is printed again (same id), the copy on Drive is not rejected, AI-G is placed and AI_ARCHIVED offered',
            lambda: o.code == 0 and cut['n'] == 1 and len(dl) >= 2 and sn['restored']['ai_archives_placed'] == ai
            and not sn['restored']['rejected_copies'] and 'CHOOSE_SEEN_TOKENS' in o.actions, lambda: (o, sn.get('restored')))
    # T-01: the only copy of AI-G on Drive is damaged
    d2 = orig.copy_to(w.root / 'drive_t01')
    f0 = next(f for f in d2.files(w.records) if f['name'] == ai[0])
    d2.hide.add(f0['id'])
    d2.put(w.records, ai[0], d2.data(f0['id'])[:700])
    w.drive = d2
    w.wipe()
    o = dot.session()
    st_ = state(w)
    t.check('T-01: an AI archive whose every copy fails: status prints only AI_WRITTEN_LOST (no NOTHING_WRITTEN or NO_CONVERSATION option)',
            lambda: o.code == 0 and not o.options and any('incident --classification AI_WRITTEN_LOST' in a for a in o.actions), o)
    t.check('T-01: SESSION_STATE keeps the rejected copy (rejected_copies) and the corrupt attempt (ai_corrupt)',
            lambda: any(r['name'] == ai[0] for r in st_.get('rejected_copies') or []) and st_.get('ai_corrupt'), st_)
    tr = w.root / 'transcript.txt'
    tr.write_text('invented transcript\n')
    r1 = dot.vm('incident', '--classification', 'AI_NOTHING_WRITTEN', '--job-dir', jd, '--role', 'G', '--conversation', 'invented-c',
                '--conversation-ended', '--transcript', tr)
    r2 = dot.vm('incident', '--classification', 'AI_NO_CONVERSATION', '--job-dir', jd, '--role', 'G', '--conversation-ended')
    r3 = dot.vm('ai-archive', '--job-dir', jd, '--role', 'G')
    t.check('T-01: AI_NOTHING_WRITTEN and AI_NO_CONVERSATION are refused INCIDENT_ARCHIVE_REJECTED; ai-archive waits for the incident '
            '(INCIDENT_REQUIRED, r2 R2-03)',
            lambda: r1.codeword == 'INCIDENT_ARCHIVE_REJECTED' and r2.codeword == 'INCIDENT_ARCHIVE_REJECTED' and r3.codeword == 'INCIDENT_REQUIRED',
            (r1, r2, r3))
    o = dot.auto(o, halt=at_action(f'RUN {w.V} recheck'))
    inc = [i for i in incident_notes(w) if i['classification'] == 'AI_WRITTEN_LOST']
    t.check('T-01: the AI_WRITTEN_LOST incident names the rejected copy and the damaged archive', lambda: inc
            and any(r['name'] == ai[0] for r in inc[-1]['rejected_copies']) and inc[-1]['ai_archive'] == {'name': ai[0], 'rejected': True}, inc)
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    os_ = dot.vm('start-note', '--job-dir', jd, '--role', 'G')
    r3 = dot.vm('ai-archive', '--job-dir', jd, '--role', 'G')
    t.check('T-01: after recheck status prints wrap freeze (a failed run) and no second generator START is allowed',
            lambda: 'wrap freeze' in o.actions[0] and os_.refused == 'START_NOT_ALLOWED' and not names(w.drive, w.records, 'START_A_G2_'), (o, os_))
    t.check('T-01: after the incident ai-archive refuses AI_ARCHIVE_REJECTED', lambda: r3.result.get('code') == 'AI_ARCHIVE_REJECTED', r3)


@scenario
def t02_fork_after_e22(t):
    """T-02 (E22): after the 'counts as not uploaded' recovery the re-run's package at the same seq is no fork: a later
    session in a new chat, a second wipe, final and audit all accept the chain."""
    c = '9991201'
    w = World(t, 't02_fork_after_e22_w', cases=[c])
    dot = Dot(w)
    o = to_prepare(t, dot, w)
    dot.stop_after_upload = ('AI_', 'ai-archive')
    o = dot.auto(o)
    real_put = w.drive.put
    arm = {'on': True, 'name': None}

    def put(folder, name, data, mime=None):
        if arm['on'] and name.startswith('CP_'):
            arm['on'], arm['name'] = False, name
            data = data[:1000]
        return real_put(folder, name, data, mime)
    w.drive.put = put
    dot.stop_after_upload = ('PNG_', None)
    o = dot.auto(o)
    trunc = arm['name']
    o, sn = restore_cycle(t, dot, w, 'T-02 first wipe', 'AI_ARCHIVED')
    t.check('T-02: the truncated-only CP-F counts as not uploaded (restore used the package before it, named the rejected copy)',
            lambda: sn['restored']['package'] != trunc and any(r['name'] == trunc for r in sn['restored']['rejected_copies']), sn.get('restored'))
    jd = w.job_dir('A', c)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} start-note --job-dir {jd} --role V'))
    same = [n for n in names(w.drive, w.records, 'CP_A_') if vm.parse_name(n)['seq'] == vm.parse_name(trunc)['seq']]
    t.check('T-02 setup: the re-run made a second CP at the same seq', lambda: len(set(same)) == 2, same)
    inc = [i for i in incident_notes(w) if i['classification'] == 'AI_ARCHIVED']
    t.check('T-02: the INCIDENT records the rejected copy (rejected_copies, with its Drive id)', lambda: inc and any(
        r['name'] == trunc and r['drive_id'] for r in inc[-1]['rejected_copies']), inc)
    o2 = dot.session()
    t.check('T-02: a later session in a new chat on the same VM: local mode, no RESTORE_FORK, no LOCAL_BEHIND_DRIVE', lambda: o2.code == 0
            and session_note(w, o2).get('mode') == 'local', o2)
    o, sn = restore_cycle(t, dot, w, 'T-02 second wipe')
    t.check('T-02: a second wipe restores the re-run\'s CP-F (the dead name is checked by download, never a fork)',
            lambda: sn['restored']['package'] in same and sn['restored']['package'] != trunc, sn.get('restored'))
    o = dot.auto(o, halt=at_action(f'RUN {w.V} final'), max_steps=400)
    t.check('T-02 setup: both readers are done: status prints final', lambda: o.actions and o.actions[0].endswith(' final'), o)
    o = dot.auto(o, halt=at_action('HANDBACK'))
    t.check('T-02: final accepts the chain (no FINAL_FORK, no FINAL_CHAIN) and uploads ALL_FROZEN.json', lambda: o.result.get('command') == 'final'
            and names(w.drive, w.records, 'ALL_FROZEN') == ['ALL_FROZEN.json'], o)
    flat = w.drive.flat(w.records, w.root / 'maint' / 'qualification')
    sflat = w.drive.flat(FOLDERS['setup'], w.root / 'maint' / 'setup')
    w.drive.listing(w.records, w.root / 'maint' / 'Q.json')
    w.drive.listing(FOLDERS['setup'], w.root / 'maint' / 'S.json')
    rel = w.root / 'maint' / 'RELEASE.json'
    shutil.copyfile(w.base / 'runtime' / 'RELEASE.json', rel)
    p = subprocess.run([sys.executable, '-I', '-B', str(HELPER), 'audit', '--drive-dir', str(flat), '--listing', str(w.root / 'maint' / 'Q.json'),
                        '--setup-dir', str(sflat), '--setup-listing', str(w.root / 'maint' / 'S.json'), '--release', str(rel),
                        '--allow-test-overrides'], capture_output=True, text=True, timeout=3600)
    ar = json.loads((flat / 'AUDIT_REPORT.json').read_text()) if (flat / 'AUDIT_REPORT.json').is_file() else {}
    codes = {x['code'] for x in ar.get('anomalies', [])}
    t.check('T-02: audit does not call the dead name a fork or a chain break (AUD_FORK, AUD_CHAIN absent)', lambda: ar and not ({'AUD_FORK', 'AUD_CHAIN'} & codes),
            lambda: (sorted(codes), p.stderr[-600:]))


@scenario
def t05_bound_refused(t):
    """T-05 and E17: a bound finish refused in preflight (GENERATION_RECORD_TIMES) keeps the seen token in force, across a
    wipe after its CP-R; the finish that then completes with a different token is RESET_DIVERGED."""
    c = '9991501'
    w = World(t, 't05_bound_refused_w', cases=[c])
    dot = Dot(w)
    o = to_prepare(t, dot, w)
    jd = w.job_dir('A', c)
    dot.stop_before_upload = ('PNG_', None)
    o = dot.auto(o)
    tok = o.bind
    t.check('T-05 setup: finish completed and printed its bind token (CP-F not uploaded)', lambda: tok and tok.startswith('B1/finish/'), o)
    w.wipe()
    o = dot.session()
    dot.pending_tokens = [forge_token(tok)]
    o = dot.auto(o, choose=lambda o_: 'SEEN', halt=at_action(f'RUN {w.V} recheck'))
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    dot.pending_tokens = []
    t.check('T-05 setup: after the restore status asks for the generation record (lost with CP-F)', lambda: o.actions[0].startswith('WRITE_GENERATION_RECORD'), o)
    tcj.generation_record(jd, c, started_utc='2000-01-01T00:00:00.000Z', ended_utc='2000-01-01T00:00:01.000Z')
    o = dot.vm('status')
    line = next(a for a in o.actions if 'wrap finish' in a)[4:]
    o = run_wrap(dot, line)
    bd = o.result.get('binding') or {}
    t.check('T-05: the bound finish refused GENERATION_RECORD_TIMES makes CP-R whose binding is not compared and keeps the incident pending',
            lambda: 'GENERATION_RECORD_TIMES' in o.result.get('runner_last_line', '') and o.result.get('package', '').startswith('CP_')
            and bd.get('compared') is False and bd.get('matched') is None and bd.get('pending') and o.result.get('reset_diverged') is False, o)
    cpr = o.result['package']
    # E17: a wipe after CP-R: the staged output equals AI-G, so placement is skipped (no RESTORE_TARGET_NOT_EMPTY)
    o, sn = restore_cycle(t, dot, w, 'E17 after CP-R', 'AI_ARCHIVED', choose=lambda o_: 'NOT_SEEN')
    t.check('E17: the CP-R restore keeps the output folder from the core (AI-G not placed again) and the response is there',
            lambda: sn['restored']['package'] == cpr and sn['restored']['ai_archives_placed'] == [] and (jd / 'run/A/output/response.json').is_file(),
            sn.get('restored'))
    tcj.generation_record(jd, c)
    o = dot.vm('status')
    line = next(a for a in o.actions if 'wrap finish' in a)[4:]
    o = run_wrap(dot, line)
    bd = o.result.get('binding') or {}
    t.check('T-05: the completed finish is compared with the token still in force: STOP RESET_DIVERGED (binding compared, matched false)',
            lambda: o.stop == 'RESET_DIVERGED' and o.result.get('reset_diverged') is True and bd.get('compared') is True and bd.get('matched') is False, o)


@scenario
def t06_evict_and_literal(t):
    """T-06: verification never loops on one copy: a bad FZ or PNG part is re-uploaded (bounded) and the new copy verified;
    after a wipe a bad part with no local source is rebuilt. T-10: the literal reading of the printed lines."""
    c = '9991601'
    w = World(t, 't06_evict_and_literal_w', cases=[c])
    dot = Dot(w)
    o = to_prepare(t, dot, w)
    jd = w.job_dir('A', c)
    real_put = w.drive.put
    bad = {'FZ_A_': True, 'PNG_A_': True, 'PNG_B_': True}
    corrupted = []

    def put(folder, name, data, mime=None):
        for k in list(bad):
            if bad[k] and name.startswith(k) and (k != 'PNG_A_' or '_01of' in name):
                bad[k] = False
                corrupted.append(name)
                data = data[:-10] + b'\0' * 10      # the connector stored other bytes (silent corruption)
        return real_put(folder, name, data, mime)
    w.drive.put = put
    o = dot.auto(o, halt=at_action(f'RUN {w.V} start-note --job-dir {jd} --role V'))
    sg = next(h for h in dot.history if h.result.get('command') == 'start-note' and '--role G' in h.cmd and h.code == 0)
    t.check('T-10: start-note ends at the link-note RUN line (the wait and ai-archive come from link-note\'s own output)',
            lambda: sg.actions[-1].startswith(f'RUN {w.V} link-note') and not any('ai-archive' in a for a in sg.actions), sg)
    rec0 = vm.sha_file(jd / 'RUN_RECORD.json')
    ra = dot.vm('ai-archive', '--job-dir', jd, '--role', 'G')
    t.check('T-10: ai-archive (existing) after finish completed prints status\'s next step, not the finish line again',
            lambda: ra.result.get('existing') is True and not any('wrap finish' in a for a in ra.actions)
            and any('start-note' in a and '--role V' in a for a in ra.actions), ra)
    fin = next(a for h in dot.history for a in h.actions if a.startswith('RUN ') and ' wrap finish ' in a)
    rf = dot.run_line(fin[4:])
    t.check('T-10: a leftover wrap finish after the stage completed is refused WRAP_STAGE_DONE without the runner (record unchanged)',
            lambda: rf.result.get('code') == 'WRAP_STAGE_DONE' and vm.sha_file(jd / 'RUN_RECORD.json') == rec0 and not rf.uploads, rf)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} evict'))
    rounds = []
    for _ in range(6):
        o = dot.run_line(o.actions[0][4:]) if not rounds else dot.vm('evict', '--job-dir', jd)
        rounds.append(o)
        if o.code != 10:
            break
    dls = [ln for r in rounds for ln in r.fetch if ln.startswith('DOWNLOAD ')]
    t.check('T-06: a corrupt FZ and PNG part: each bad copy is downloaded once, the local file re-uploaded, the new copy verified, the folder evicted',
            lambda: not jd.exists() and len(rounds) <= 5 and len(dls) == len(set(dls))
            and any(u for r in rounds for u in r.uploads if Path(u.split(' -> ')[0][7:]).name in corrupted), lambda: (corrupted, rounds))
    # reader B: its first PNG part is damaged on Drive; a wipe after its FZ leaves no local source: rebuild-parts
    jb = w.job_dir('B', c)
    dot.stop_after_upload = ('FZ_B_', None)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} evict --job-dir {jb}'))
    t.check('T-06 setup: reader B frozen, its FZ uploaded, a part damaged', lambda: any(x.startswith('PNG_B_') for x in corrupted)
            and newest_pkg(w).startswith('FZ_B_'), (o, corrupted))
    o, sn = restore_cycle(t, dot, w, 'T-06 FZ newest', 'NONE_IN_FLIGHT')
    seen_rebuild, rounds = False, []
    for _ in range(10):
        if not o.actions or not o.actions[0].startswith('RUN '):
            break
        if 'rebuild-parts' in o.actions[0]:
            seen_rebuild = True
        if 'wrap ' in o.actions[0] or o.actions[0].endswith(' final'):
            break
        o = dot.run_line(o.actions[0][4:])
        rounds.append(o)
        while o.code == 10 and o.actions == ['RUN_SAME_COMMAND_AGAIN'] and len(rounds) < 20:
            o = dot.run_line(o.cmd)
            rounds.append(o)
    pend = json.loads((w.base / 'outbox' / 'FZ_PENDING.json').read_text()) if (w.base / 'outbox' / 'FZ_PENDING.json').is_file() else []
    t.check('T-06: after the FZ-newest restore the damaged part (no local source) is rebuilt by rebuild-parts, uploaded and verified; FZ_PENDING empties',
            lambda: seen_rebuild and not pend and o.actions and o.actions[0].endswith(' final'), lambda: (o, [r.cmd[-60:] for r in rounds]))


@scenario
def t06_md5_mode(t):
    """T-06 in md5 mode: a corrupt FZ (a nonattempt) is re-uploaded after its narrow listing shows other bytes, then verified."""
    w = World(t, 't06_md5_mode_w', cases=['9991602'], nonattempts=['9991691'], cfg={'upload_verification': 'md5'})
    dot = Dot(w)
    o = start_world(t, dot, w)
    real_put = w.drive.put
    arm = {'on': True}

    def put(folder, name, data, mime=None):
        if arm['on'] and name.startswith('FZ_NA-A_'):
            arm['on'] = False
            data = data[:-10] + b'\0' * 10
        return real_put(folder, name, data, mime)
    w.drive.put = put
    o = dot.auto(o, halt=at_action(f'RUN {w.V} evict'))
    rounds = []
    for _ in range(6):
        o = dot.run_line(o.actions[0][4:]) if not rounds else dot.vm(*shlex.split(rounds[0].cmd)[1:])
        rounds.append(o)
        if o.code != 10:
            break
    ups = [u for r in rounds for u in r.uploads if 'FZ_NA-A_' in u]
    t.check('T-06 md5 mode: the narrow listing showing other bytes makes evict print the FZ UPLOAD again, then it verifies and evicts',
            lambda: o.code == 0 and len(rounds) <= 4 and len(ups) == 1 and len(names(w.drive, w.records, 'FZ_NA-A_')) == 2
            and not (w.base / 'qual' / 'nonattempts_A' / '9991691').exists(), rounds)


@scenario
def t08_everyday_inputs(t):
    """T-08 (E14 rows): a run with only its INPUTS is the job in flight (status prints its prepare, job-start refuses a second
    run); a wipe restores the inputs (NON_AI_STAGE_LOST, the same prepare); a finished newest FZ is restored for verification
    only; the prepare refuses changed inputs."""
    c = '9991801'
    w = World(t, 't08_everyday_inputs_w', mode='everyday', cases=[c], cfg={'wrap_foreground_seconds': 1})
    dot = Dot(w)
    o = start_world(t, dot, w)
    everyday_inputs(w, c)
    dot.values['CASE'] = c
    o = dot.run_line(o.actions[1][4:])
    run_tag = o.result['run_id']
    prep = o.actions[0]
    o2 = dot.vm('job-start', '--case', c)
    st_ = dot.vm('status')
    t.check('T-08: with only INPUTS (no package, no folder) job-start refuses WRAP_RUN_IN_FLIGHT and status prints that run\'s prepare',
            lambda: o2.refused == 'WRAP_RUN_IN_FLIGHT' and st_.actions == [prep], (o2, st_))
    tp = w.base / 'everyday_inputs' / c / 'JOB_TITLE.json'
    keep = tp.read_bytes()
    tp.write_bytes(keep.replace(b'\n}', b' \n}'))
    o3 = dot.run_line(prep[4:])
    tp.write_bytes(keep)
    t.check('T-08: a prepare whose inputs differ from the INPUTS archive is refused WRAP_INPUTS_CHANGED', lambda: o3.refused == 'WRAP_INPUTS_CHANGED', o3)
    o, sn = restore_cycle(t, dot, w, 'T-08 INPUTS only', 'NON_AI_STAGE_LOST')
    t.check('T-08: the INPUTS-only run is restored (inputs placed back) and status prints the same prepare', lambda: sn['restored']['package'] is None
            and (w.base / 'everyday_inputs' / c / 'JOB.json').is_file() and o.actions == [prep], (o, sn.get('restored')))
    jd = w.base / 'jobs' / run_tag[1:] / c
    o = dot.auto(o, halt=at_action('WAIT_FOR_USER_REQUEST'))
    t.check('T-08 setup: the run reached the user question', lambda: 'NOT_NOW' in dict(o.options), o)
    o = dot.auto(dot.run_line(dict(o.options)['NOT_NOW'][4:]), halt=at_action('WAIT_FOR_USER_REQUEST'))
    t.check('T-08 setup: frozen and evicted', lambda: newest_pkg(w, c).startswith('FZ_') and not jd.exists(), o)
    o, sn = restore_cycle(t, dot, w, 'T-08 FZ newest', 'NONE_IN_FLIGHT')
    t.check('T-08: with no unfinished run the newest FZ is restored for verification only (no folder), status prints evict',
            lambda: sn['restored']['fz_newest'] is True and not jd.exists() and o.actions[0].endswith(f'evict --job-dir {jd}'), (o, sn.get('restored')))
    o = dot.auto(o, halt=at_action('WAIT_FOR_USER_REQUEST'))
    ver = [h for h in dot.history[-8:] if h.result.get('command') == 'evict']
    t.check('T-08: evict verifies the FZ parts by download and status waits for the next request', lambda: ver and o.actions[0] == 'WAIT_FOR_USER_REQUEST'
            and any('DOWNLOAD ' in ln and 'PNG_' in ln for h in ver for ln in h.fetch), ver)


@scenario
def t09_stray(t):
    """T-09: a job folder recreated after a wipe (a conversation still writing) is archived as STRAY and STOPs
    RESTORE_TARGET_NOT_EMPTY, never local mode or LEDGER_NO_IDENTITY; a folder without RUN_RECORD.json never crashes package."""
    c = '9991901'
    w = World(t, 't09_stray_w', cases=[c])
    dot = Dot(w)
    o = to_prepare(t, dot, w)
    dot.stop_after_upload = ('CP_', None)
    o = dot.auto(o)
    w.wipe()
    out = w.job_dir('A', c) / 'run' / 'A' / 'output'
    out.mkdir(parents=True)
    (out / 'response.json').write_text('{"invented": "written by a conversation still running"}\n')
    o = dot.session()
    st_ = [u for u in o.uploads if '/STRAY_' in u]
    o2 = dot.session()
    st2 = [u for u in o2.uploads if '/STRAY_' in u]
    t.check('T-09: an unknown job folder after a wipe: STRAY archive uploaded, STOP RESTORE_TARGET_NOT_EMPTY (not LEDGER_NO_IDENTITY)',
            lambda: o.stop == 'RESTORE_TARGET_NOT_EMPTY' and len(st_) == 1 and not (w.base / 'ledger').exists(), o)
    t.check('T-09: a second session re-prints the same STRAY upload (no new archive)', lambda: o2.stop == 'RESTORE_TARGET_NOT_EMPTY' and st2 == st_, o2)
    w2 = World(t, 't09_stray_w2', mode='everyday', cases=[c])
    d2 = Dot(w2)
    start_world(t, d2, w2)
    jd = w2.base / 'jobs' / '20261109T000000Z' / c
    jd.mkdir(parents=True)
    (jd / 'note.txt').write_text('invented: a folder without a record\n')
    o = d2.vm('package', '--job-dir', jd)
    t.check('T-09: package of a folder without RUN_RECORD.json is STOP PACKAGE_NO_RECORD, never INTERNAL_ERROR', lambda: o.stop == 'PACKAGE_NO_RECORD', o)


@scenario
def t11_t12_listings(t):
    """T-11, T-12, T-16 (U11, E1): the sentinel upload loop ends; a refused listing is set aside and printed again; truncated
    or hidden-entry listings never give fresh mode or an older restore; genesis guards."""
    w0 = World(t, 't11_t12_listings_w0', cases=['9992101'], put_sentinels=False)
    d0 = Dot(w0)
    o = d0.session()
    sent = w0.sentinels['qualification']['name']
    up = [h for h in d0.history if any(sent in u for u in h.uploads)]
    t.check('T-11: with upload_by_dot the session prints the sentinel UPLOAD before the listing; doing UPLOAD first ends the exit-10 loop',
            lambda: o.code == 0 and len(names(w0.drive, w0.records, 'SENTINEL_')) == 1 and up and up[0].code == 10
            and up[0].lines.index(next(l for l in up[0].lines if l.startswith('UPLOAD '))) <
            up[0].lines.index(next(l for l in up[0].lines if l.startswith('SAVE_DRIVE_LISTING '))), lambda: (o, up[:1]))
    c, na = '9992102', '9992191'
    w = World(t, 't11_t12_listings_w', cases=[c], nonattempts=[na])
    dot = Dot(w)
    start_world(t, dot, w)
    sp = w.base / 'outbox' / 'SESSION_STATE.json'
    keep = sp.read_bytes()
    st_ = json.loads(keep)
    st_['listing']['records'].append(f'START_A_G1_20261109T000000Z_0123abcd_{c}.json')
    sp.write_text(json.dumps(st_))
    og = dot.vm('genesis', '--first-ledger')
    sp.write_bytes(keep)
    t.check('T-16: genesis on a records listing that holds qualification history: GENESIS_EXISTS_IN_DRIVE', lambda: og.refused == 'GENESIS_EXISTS_IN_DRIVE', og)
    raw = dot.call([w.V, 'genesis', '--first-ledger'])
    w.wipe()
    o = dot.session()
    t.check('T-16: a wipe between genesis and its upload: fresh mode again and status prints genesis (the lost ledger never existed on Drive)',
            lambda: raw.code == 0 and session_note(w, o).get('mode') == 'fresh' and o.actions[0].endswith('genesis --first-ledger'), o)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))
    gen = names(w.drive, w.records, 'GENESIS_')
    t.check('T-16 setup: genesis and both nonattempts on Drive', lambda: len(gen) == 1 and len(names(w.drive, w.records, 'FZ_NA-')) == 2, o)
    # T-12: a malformed narrow listing is set aside and printed again (exit 10), so the next run is not refused the same way
    fzn = names(w.drive, w.records, 'FZ_NA-A_')[0]
    cf = w.base / 'inbox' / 'confirm' / (fzn + '.json')
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text('{"not": "a listing"}')
    o1 = dot.call([w.V, 'evict', '--all'])
    t.check('T-12: a malformed narrow listing: exit 10, RESULT names code, folder and path, the same SAVE_DRIVE_LISTING is printed, the file set aside',
            lambda: o1.code == 10 and o1.result.get('code') == 'LISTING_INVALID' and o1.result['detail']['to'] == str(cf)
            and any(f.endswith(f'to={cf} name={fzn}') for f in o1.fetch) and not cf.exists(), o1)
    dot.fetch(o1)
    o1 = dot.vm('evict', '--all')
    t.check('T-12: after the Dot saves the listing again the command runs', lambda: o1.code == 0, o1)
    # T-12: a session listing of the wrong folder
    inbox = w.base / 'inbox'
    (inbox / 'cps').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(w.static / 'FOLDER_MANIFEST.md', inbox / 'cps' / 'FOLDER_MANIFEST.md')
    w.drive.listing(FOLDERS['setup'], inbox / 'SETUP_LISTING.json')
    w.drive.listing(FOLDERS['setup'], inbox / 'DRIVE_LISTING.json')
    o2 = dot.call([w.V, 'session', '--inbox', str(inbox), '--operator-model', MODEL])
    t.check('T-12: a wrong-folder session listing: exit 10 with SAVE_DRIVE_LISTING folder=CPS/qualification to=.../DRIVE_LISTING.json',
            lambda: o2.code == 10 and o2.result.get('code') == 'LISTING_WRONG_FOLDER'
            and f'SAVE_DRIVE_LISTING folder={w.records} to={inbox / "DRIVE_LISTING.json"}' in o2.fetch, o2)
    # T-16: a truncated listing (last page dropped): exit 10 each time, STOP after the third, never fresh mode or a restore
    w.drive.page, w.drive.drop_last_page = 2, True
    w.wipe()
    o3 = dot.session()
    t.check('T-16: a truncated listing after a wipe: refused and asked again, the third time STOP LISTING_REFUSED_REPEATEDLY; no ledger, no fresh mode',
            lambda: o3.stop == 'LISTING_REFUSED_REPEATEDLY' and not (w.base / 'ledger').exists()
            and not any(h.result.get('mode') == 'fresh' for h in dot.history[-6:]), o3)
    w.drive.page, w.drive.drop_last_page = 50, False
    o3 = dot.session()
    t.check('T-16: with the complete listing the restore runs', lambda: o3.code == 0 and session_note(w, o3).get('mode') == 'restore', o3)
    o3 = dot.auto(o3, halt=at_action(f'RUN {w.V} recheck'))
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o3 = dot.vm('recheck')
    # T-16: LISTING_OLDER_THAN_SESSION: the listing lacks the package the newest SESSION note names
    o4 = dot.session()
    npk = session_note(w, o4)['records_listing']['newest_package']
    hid = {f['id'] for f in w.drive.files(w.records) if f['name'] == npk}
    w.drive.hide |= hid
    o5 = dot.session()
    w.drive.hide -= hid
    t.check('T-16: a listing older than the newest SESSION note: LISTING_OLDER_THAN_SESSION, asked again (exit 10)',
            lambda: npk and any(h.result.get('code') == 'LISTING_OLDER_THAN_SESSION' and h.code == 10 for h in dot.history[-4:]), o5)
    # T-16: expected_genesis set, the GENESIS hidden: never fresh; genesis refused GENESIS_ALREADY_EXPECTED
    w.cfg['expected_genesis'] = gen[0]
    w.build_kit(cfg_only=True)
    ghid = {f['id'] for f in w.drive.files(w.records) if f['name'] == gen[0]}
    w.drive.hide |= ghid
    w.wipe()
    o6 = dot.session()
    w.drive.hide -= ghid
    t.check('T-16: expected_genesis set and the GENESIS missing from the listing: LISTING_MISSING_GENESIS asked again, then STOP; never fresh',
            lambda: o6.stop == 'LISTING_REFUSED_REPEATEDLY' and any(h.result.get('code') == 'LISTING_MISSING_GENESIS' for h in dot.history[-6:])
            and not (w.base / 'ledger').exists(), o6)
    o7 = dot.session()
    og = dot.vm('genesis', '--first-ledger')
    t.check('T-16: with the GENESIS listed the restore runs; genesis is refused GENESIS_ALREADY_EXPECTED', lambda: o7.code == 0
            and session_note(w, o7).get('mode') == 'restore' and og.refused == 'GENESIS_ALREADY_EXPECTED', (o7, og))
    w.cfg['expected_genesis'] = None
    w.build_kit(cfg_only=True)
    orig = w.drive
    w.drive = orig.copy_to(w.root / 'drive_two_genesis')
    g0 = next(f for f in w.drive.files(w.records) if f['name'] == gen[0])
    w.drive.put(w.records, gen[0].replace('GENESIS_', 'GENESIS_').replace(gen[0][8:16], 'f0f0f0f0'), w.drive.data(g0['id']))
    w.wipe()
    o8 = dot.session()
    w.drive = orig
    t.check('T-16: two GENESIS notes on Drive: STOP RESTORE_GENESIS_DUPLICATE', lambda: o8.stop == 'RESTORE_GENESIS_DUPLICATE', o8)


@scenario
def t15_no_conversation(t):
    """E19, T-15, T-20: AI_NO_CONVERSATION's success path and its guards (LINK, output written), the superseding START, the
    repeated case reachable from the printed option (STOP), and audit's AUD_START_SUPERSEDED listing."""
    c = '9991505'
    w = World(t, 't15_no_conversation_w', cases=[c])
    dot = Dot(w)
    o = to_prepare(t, dot, w)
    jd = w.job_dir('A', c)
    dot.stop_after_upload = ('START_', None)
    o = dot.auto(o)
    s1 = names(w.drive, w.records, 'START_A_G1_')
    t.check('E19 setup: START-G1 uploaded, no conversation yet', lambda: len(s1) == 1 and o.result.get('command') == 'start-note', o)
    snap = w.drive.copy_to(w.root / 'drive_after_start')
    ol = dot.vm('link-note', '--job-dir', jd, '--role', 'G', '--conversation', 'invented-conv-link')
    w.wipe()
    o = dot.session()
    ri = dot.vm('incident', '--classification', 'AI_NO_CONVERSATION', '--job-dir', jd, '--role', 'G', '--conversation-ended')
    t.check('E19: with a LINK on Drive the NO_CONVERSATION option is absent and the incident is refused INCIDENT_LINK_EXISTS',
            lambda: ol.code == 0 and 'NO_CONVERSATION' not in dict(o.options) and ri.refused == 'INCIDENT_LINK_EXISTS', (o, ri))
    w.drive = snap
    w.wipe()
    o = dot.session()
    t.check('E19: without a LINK status offers NO_CONVERSATION', lambda: 'NO_CONVERSATION' in dict(o.options), o)
    extra = jd / 'run' / 'A' / 'output' / 'early.txt'
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text('invented: written after the restore')
    ri = dot.vm('incident', '--classification', 'AI_NO_CONVERSATION', '--job-dir', jd, '--role', 'G', '--conversation-ended')
    extra.unlink()
    t.check('E19: with a file in the output folder AI_NO_CONVERSATION is refused INCIDENT_OUTPUT_NOT_EMPTY', lambda: ri.refused == 'INCIDENT_OUTPUT_NOT_EMPTY', ri)
    o = dot.auto(o, choose=lambda o_: 'NO_CONVERSATION', halt=at_action(f'RUN {w.V} recheck'))
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    t.check('E19: AI_NO_CONVERSATION accepted; status prints start-note G again (same attempt)', lambda: o.actions[0].endswith(f'start-note --job-dir {jd} --role G'), o)
    dot.stop_after_upload = ('START_', None)
    o = dot.auto(o)
    s2 = [n for n in names(w.drive, w.records, 'START_A_G1_') if n not in s1]
    t.check('E19: the superseding START (attempt 1) names the first in supersedes', lambda: len(s2) == 1
            and json.loads((w.base / 'outbox' / s2[0]).read_text())['supersedes'] == s1[0], s2)
    w.wipe()
    o = dot.session()
    t.check('T-20: a second reset before the conversation existed: the NO_CONVERSATION option is printed', lambda: 'NO_CONVERSATION' in dict(o.options), o)
    o = dot.auto(o, choose=lambda o_: 'NO_CONVERSATION')
    t.check('T-20/E19: choosing it STOPs AI_NO_CONVERSATION_REPEATED (case C)', lambda: o.stop == 'AI_NO_CONVERSATION_REPEATED', o)
    flat = w.drive.flat(w.records, w.root / 'maint' / 'q')
    sflat = w.drive.flat(FOLDERS['setup'], w.root / 'maint' / 's')
    w.drive.listing(w.records, w.root / 'maint' / 'Q.json')
    w.drive.listing(FOLDERS['setup'], w.root / 'maint' / 'S.json')
    subprocess.run([sys.executable, '-I', '-B', str(HELPER), 'audit', '--drive-dir', str(flat), '--listing', str(w.root / 'maint' / 'Q.json'),
                    '--setup-dir', str(sflat), '--setup-listing', str(w.root / 'maint' / 'S.json'), '--release', str(w.base / 'runtime' / 'RELEASE.json'),
                    '--allow-test-overrides'], capture_output=True, text=True, timeout=3600)
    ar = json.loads((flat / 'AUDIT_REPORT.json').read_text()) if (flat / 'AUDIT_REPORT.json').is_file() else {}
    o52 = json.loads((flat / 'O52_COMPARISON.json').read_text()) if (flat / 'O52_COMPARISON.json').is_file() else {}
    t.check('E19: audit lists AUD_START_SUPERSEDED and O52_COMPARISON marks the superseded START', lambda: any(x['code'] == 'AUD_START_SUPERSEDED'
            for x in ar.get('listed', [])) and any(r['superseded'] for r in o52.get('rows', [])), (ar.get('listed'), o52.get('rows')))


@scenario
def t14_scope_e10(t):
    """E10 (T-14): a large-workbook case through the scope reader: a wipe after START-S with no conversation
    (AI_NO_CONVERSATION), a wipe after AI-S, a wipe after CP-S, then the generator broken in flight after a wipe
    (AI_NOTHING_WRITTEN), the in-place interrupt (form 2), generator attempt 2, finish and freeze. (The package's invented
    example response does not fit a scoped inventory, so finish completes with STOP_ROUTE_CHECK_FAILED; the helper path
    is the same.)"""
    c = '9991408'
    w = World(t, 't14_scope_e10_w', cases=[c], large=[c])
    dot = Dot(w)
    gen_calls = {'n': 0}

    def conv_g(jd, case, role, reader):
        gen_calls['n'] += 1
        if gen_calls['n'] == 1:
            return                                  # attempt 1 writes nothing (broken in flight)
        tcj.stand_in_response(None, jd, case, reader=reader)
    o = to_prepare(t, dot, w)
    jd = w.job_dir('A', c)
    dot.stop_after_upload = ('START_', None)
    o = dot.auto(o)
    t.check('E10 setup: the large case prepares to the scope reader and START-S is uploaded', lambda: names(w.drive, w.records, 'START_A_S1_'), o)
    o, sn = restore_cycle(t, dot, w, 'E10 in the scope reader', 'AI_NO_CONVERSATION', choose=lambda o_: 'NO_CONVERSATION')
    t.check('E10: after AI_NO_CONVERSATION status prints start-note S again', lambda: o.actions[0].endswith(f'start-note --job-dir {jd} --role S'), o)
    dot.stop_after_upload = ('AI_', 'ai-archive')
    o = dot.auto(o)
    t.check('E10: AI-S uploaded (start-note S, link-note, ai-archive)', lambda: names(w.drive, w.records, 'AI_A_S1_'), o)
    o, sn = restore_cycle(t, dot, w, 'E10 after AI-S', 'AI_ARCHIVED')
    t.check('E10: AI-S placed; status prints wrap scope-finish', lambda: sn['restored']['ai_archives_placed'] and 'wrap scope-finish' in o.actions[0], o)
    dot.stop_after_upload = ('CP_', None)
    o = dot.auto(o)
    cps = newest_pkg(w, c)
    o, sn = restore_cycle(t, dot, w, 'E10 after CP-S', 'NONE_IN_FLIGHT')
    frozen = jd / 'scope' / 'SCOPE_READER_RESPONSE.json'
    t.check('E10: the CP-S restore keeps the frozen scope response read-only and status prints start-note G', lambda: sn['restored']['package'] == cps
            and frozen.is_file() and not (stat_mode(frozen) & 0o222) and o.actions[0].endswith(f'start-note --job-dir {jd} --role G'),
            lambda: (o, oct(stat_mode(frozen)) if frozen.exists() else None))
    dot.conv['G'] = conv_g
    dot.stop_after_upload = ('LINK_', None)
    o = dot.auto(o)
    o, sn = restore_cycle(t, dot, w, 'E10 generator in flight', 'AI_NOTHING_WRITTEN')
    t.check('E10: status prints wrap interrupt after the generator wrote nothing', lambda: 'wrap interrupt' in o.actions[0], o)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))
    stages = fz_record(w, c)['stages']
    t.check('E10: the in-place interrupt (form 2, NEXT: GENERATE), generator attempt 2 (START-G2), finish completed (the stand-in '
            'response does not fit the scoped inventory: STOP_ROUTE_CHECK_FAILED), freeze and evict; status moves to reader B',
            lambda: any(s['stage'] == 'interrupt' and s.get('next') == 'GENERATE' for s in stages)
            and names(w.drive, w.records, 'START_A_G2_') and any(s['stage'] == 'finish' and s.get('completed') for s in stages)
            and newest_pkg(w, c).startswith('FZ_A_') and '--reader B' in o.actions[0] and not jd.exists(), o)


STUB_SUITE = '''#!/usr/bin/env python3
"""INVENTED stand-in for research/export/tests/run_export_tests.py in a test copy of the repository (E24, T-17)."""
import hashlib, json, os, shutil, sys, time
from pathlib import Path
a = sys.argv
work = Path(a[a.index('--work') + 1])
work.mkdir(parents=True, exist_ok=True)
time.sleep(float(os.environ.get('CPS_TEST_STUB_SLEEP', '0')))
exp = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
node = os.path.realpath(shutil.which('node'))
s = {'suite': 'invented stub', 'tests': 600, 'passed_count': 600, 'failed_count': 0, 'failed': [], 'visual_skipped': False,
     'writer_portable_sha256': sha(exp / 'writer_portable.py'), 'saved_qa_sha256': sha(exp / 'saved_qa.py'),
     'visual_qa_sha256': sha(exp / 'visual_qa.py'), 'checker_node': {'realpath': node, 'sha256': sha(node)}}
(work / 'EXPORT_TEST_RESULTS.json').write_text(json.dumps({'summary': s, 'results': []}))
'''


def repo_copy(t, name):
    """A clone of the checkout with deploy/vm copied, a stub export suite, and a runner whose FROZEN.json write fails when
    CPS_TEST_FAIL_FROZEN_WRITE=1 (only in this copy; runner v4 itself is never changed)."""
    d = t.work / name
    subprocess.run(['git', 'clone', '-q', str(REPO), str(d)], check=True, capture_output=True)
    (d / 'deploy' / 'vm').mkdir(exist_ok=True)
    for f in ('cps_vm.py', 'session_start.sh', 'test_cps_vm.py', 'README.md'):
        shutil.copyfile(HERE / f, d / 'deploy' / 'vm' / f)
    (d / 'research' / 'export' / 'tests' / 'run_export_tests.py').write_text(STUB_SUITE)
    rp = d / 'deploy' / 'run' / 'cps_job.py'
    src = rp.read_text(encoding='utf-8')
    old = "        write_new(tmp, b)\n        os.replace(tmp, jd.p('FROZEN.json'))\n"
    assert src.count(old) == 1
    rp.write_text(src.replace(old, "        if os.environ.get('CPS_TEST_FAIL_FROZEN_WRITE') == '1':\n"
                                   "            raise OSError(28, 'invented injected fault (test copy)')\n" + old), encoding='utf-8')
    # the runner refuses a dirty tracked tree: the copy's changes are committed in the copy (its own HEAD)
    subprocess.run(['git', '-C', str(d), '-c', 'user.name=invented test', '-c', 'user.email=invented@example.invalid', 'commit', '-q', '-am',
                    'invented test copy: stub export suite, injectable FROZEN.json write fault'], check=True, capture_output=True)
    return d


@scenario
def t17_selftest_e18(t):
    """E24 (T-17): $V selftest runs the detached worker (a stub suite): a killed worker is WORKER_DIED, a killed foreground
    leaves the worker to finish, then fingerprint-pass; a stale PLACED.json folder is removed. E18 (T-29): a FROZEN.json write
    that fails gives STOP_FREEZE_INCOMPLETE and a CP; the completing freeze makes the FZ at that seq; no fork after a wipe."""
    rc = repo_copy(t, 't17_selftest_e18_repo')
    c = '9991701'
    w = World(t, 't17_selftest_e18_w', cases=[c], repo=rc, cfg={'wrap_foreground_seconds': 1})
    dot = Dot(w)
    o = dot.session()
    t.check('E24: a fresh session on a new fingerprint prints selftest', lambda: o.code == 0 and o.actions[0].endswith(' selftest'), o)
    dot.env_extra = {'CPS_TEST_STUB_SLEEP': '6'}
    o = dot.vm('selftest')
    d = json.loads((w.base / 'outbox' / 'DETACHED.json').read_text()) if (w.base / 'outbox' / 'DETACHED.json').is_file() else {}
    t.check('E24: selftest runs detached (exit 11, RUN wait)', lambda: o.code == 11 and o.actions == [f'RUN {w.V} wait'] and d.get('kind') == 'selftest', o)
    try:
        os.killpg(d['pid'], signal.SIGKILL)
    except (KeyError, ProcessLookupError):
        pass
    time.sleep(1)
    o = dot.vm('wait')
    t.check('E24: a killed self-test worker: STOP WORKER_DIED, NEXT selftest', lambda: o.stop == 'WORKER_DIED' and o.actions[0].endswith(' selftest'), o)
    time.sleep(1.1)
    p = subprocess.Popen([w.V, 'selftest'], env=dict(w.env, **dot.env_extra), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    for _ in range(300):
        dd = read_json(w.base / 'outbox' / 'DETACHED.json')
        if dd.get('pid') and dd.get('kind') == 'selftest':
            break
        time.sleep(0.1)
    os.killpg(p.pid, signal.SIGKILL)
    p.wait()
    o = wait_done(dot, dot.vm('wait'))
    t.check('E24: the foreground selftest killed: the worker finishes and wait prints its block (NEXT fingerprint-pass)',
            lambda: o.result.get('command') == 'selftest' and o.result.get('exit') == 0 and o.actions[0].endswith(' fingerprint-pass'), o)
    dot.env_extra = {}
    o = dot.vm('fingerprint-pass')
    t.check('E24: fingerprint-pass accepts the worker\'s results and prints genesis', lambda: o.code == 0 and o.actions[0].endswith('genesis --first-ledger'), o)
    # a stale PLACED.json (a killed prepare): a complete placed folder and an empty one are removed at the next start (T-24)
    fa, fb = w.base / 'qual' / 'A' / 'X1', w.base / 'qual' / 'B' / 'X2'
    fa.mkdir(parents=True)
    fb.mkdir(parents=True)
    (fa / 'FROZEN.json').write_bytes(b'{"invented": true}\n')
    (w.base / 'outbox' / 'PLACED.json').write_text(json.dumps([{'job_dir': str(fa), 'frozen_sha256': sha(b'{"invented": true}\n')},
                                                              {'job_dir': str(fb), 'frozen_sha256': sha(b'x')}]))
    o = dot.session()
    t.check('E24/T-24: a stale PLACED.json folder (complete or empty) is removed at the next start', lambda: o.code == 0 and not fa.exists()
            and not fb.exists() and not (w.base / 'outbox' / 'PLACED.json').exists(), o)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))
    jd = w.job_dir('A', c)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap freeze'))
    t.check('E18 setup: the run reached its freeze', lambda: 'wrap freeze' in o.actions[0] and str(jd) in o.actions[0], o)
    line = o.actions[0][4:]
    dot.env_extra = {'CPS_TEST_FAIL_FROZEN_WRITE': '1'}
    o = run_wrap(dot, line)
    dot.env_extra = {}
    t.check('E18: FROZEN.json cannot be written: STOP_FREEZE_INCOMPLETE, a CP is made, NEXT is freeze again',
            lambda: 'STOP_FREEZE_INCOMPLETE' in o.result.get('runner_last_line', '') and (o.result.get('package') or '').startswith('CP_')
            and 'wrap freeze' in o.actions[0], o)
    cp_seq = vm.parse_name(o.result['package'])['seq']
    st_ = dot.vm('status')
    t.check('E18: status prints wrap freeze for "freeze recorded, FROZEN.json absent"', lambda: 'wrap freeze' in st_.actions[0], st_)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} evict'))
    t.check('E18: the completing freeze made an FZ at the CP\'s seq (no fork)', lambda: vm.parse_name(newest_pkg(w, c))['seq'] == cp_seq
            and newest_pkg(w, c).startswith('FZ_'), o)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))
    o, sn = restore_cycle(t, dot, w, 'E18 after evict', 'NON_AI_STAGE_LOST')     # r2 M2: the prepare printed after it
    t.check('E18: the restore after the FZ of that seq sees no fork (FZ newest)', lambda: sn['restored']['fz_newest'] is True, sn.get('restored'))


# ------------------------------------------------------------------ review round 2 (r2): regression tests
def wrap_line(o, sub):
    return next((a for a in o.actions if a.startswith('RUN ') and f' wrap {sub} ' in a), None)


@scenario
def r2_fixes_a(t):
    """r2 C1 (local session after expected_genesis), WRAP_BINDING_SUBCOMMAND, INCIDENT_SEEN_INVALID, C2 (divergence forced at the
    incident, then the freeze) and M1 (status and a new-chat session print freeze for a diverged run)."""
    ca, cb = '9992101', '9992102'
    w = World(t, 'r2_fixes_a_w', cases=[ca, cb])
    dot = Dot(w)
    o = to_prepare(t, dot, w)
    prep = o.actions[0]
    # C1: the maintainer records the GENESIS (TELL_MAINTAINER); the next new chat on the same VM is a local session
    gen = names(w.drive, w.records, 'GENESIS_')
    w.cfg['expected_genesis'] = gen[0]
    w.build_kit(cfg_only=True)
    o = dot.session()
    t.check('r2 C1: a local-mode session after expected_genesis is set exits 0 and prints the same prepare (no LISTING_MISSING_GENESIS)',
            lambda: o.code == 0 and session_note(w, o).get('mode') == 'local' and o.actions == [prep], o)
    # WRAP_BINDING_SUBCOMMAND: a seen finish token binds finish; freeze of a run that did not fail is refused
    ja, jb = w.job_dir('A', ca), w.job_dir('A', cb)
    dot.stop_before_upload = ('PNG_', None)
    o = dot.auto(o)
    real = list(dot.pending_tokens)
    t.check('r2 setup: finish of case a ran and printed its token, nothing uploaded', lambda: real and real[-1].startswith(f'B1/finish/A/{ca}/'), o)
    w.wipe()
    o = dot.session()
    t.check('r2 setup: the restore asks for AI_ARCHIVED SEEN/NOT_SEEN', lambda: 'SEEN' in dict(o.options) and 'AI_ARCHIVED' in dict(o.options)['SEEN'], o)
    bad1 = dot.vm('incident', '--classification', 'AI_ARCHIVED', '--job-dir', ja, '--role', 'G', '--seen', 'B1/not/a/token')
    bad2 = dot.vm('incident', '--classification', 'AI_ARCHIVED', '--job-dir', ja, '--role', 'G', '--seen', forge_token(real[-1], field=3))
    t.check('r2 R2-04: a malformed token and a token of another case are refused INCIDENT_SEEN_INVALID',
            lambda: bad1.refused == 'INCIDENT_SEEN_INVALID' and bad2.refused == 'INCIDENT_SEEN_INVALID', (bad1, bad2))
    dot.pending_tokens = [real[-1]]
    o = dot.auto(o, choose=lambda o_: 'SEEN', halt=at_action(f'RUN {w.V} recheck'))
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap finish'))
    of = dot.vm('wrap', 'freeze', '--job-dir', ja, '--operator-model', MODEL)
    t.check('r2 R2-04: while a seen token binds finish, wrap freeze of that run is refused WRAP_BINDING_SUBCOMMAND',
            lambda: of.refused == 'WRAP_BINDING_SUBCOMMAND', of)
    dot.pending_tokens = []
    o = dot.run_line(wrap_line(o, 'finish')[4:])
    o = wait_done(dot, o)
    t.check('r2 setup: the bound finish matched', lambda: (o.result.get('binding') or {}).get('matched') is True and o.code == 0, o)
    o = dot.auto(o, halt=lambda a, o_: a.startswith(f'RUN {w.V} wrap prepare') and f'/jobs/{cb}/' in a)
    t.check('r2 setup: case a frozen and evicted, status moves to case b', lambda: f'/jobs/{cb}/' in o.actions[0] and not ja.exists(), o)
    # C2: two seen tokens that disagree force RESET_DIVERGED at the incident; the run can still be frozen
    dot.stop_before_upload = ('PNG_', None)
    o = dot.auto(o)
    real = list(dot.pending_tokens)
    w.wipe()
    o = dot.session()
    dot.pending_tokens = [real[-1], forge_token(real[-1])]
    o = dot.auto(o, choose=lambda o_: 'SEEN', halt=at_action(f'RUN {w.V} recheck'))
    t.check('r2 C2: two disagreeing seen tokens: STOP RESET_DIVERGED at the incident, NEXT recheck, THEN wrap freeze',
            lambda: o.stop == 'RESET_DIVERGED' and o.code == 3 and o.actions[0].endswith(' recheck') and 'wrap freeze' in o.actions[1], o)
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    st_ = dot.vm('status')
    t.check('r2 M1: after the forced divergence recheck and status print only wrap freeze (never the generation record or finish)',
            lambda: o.actions and 'wrap freeze' in o.actions[0] and st_.actions == o.actions[:1], (o, st_))
    of = dot.vm('wrap', 'finish', '--job-dir', jb, '--operator-model', MODEL)
    t.check('r2 C2: wrap finish of the diverged run is refused WRAP_RUN_FAILED_RESET_DIVERGED', lambda: of.refused == 'WRAP_RUN_FAILED_RESET_DIVERGED', of)
    o2 = dot.session()
    t.check('r2 M1: a new-chat session prints wrap freeze for the diverged run', lambda: o2.code == 0 and o2.actions and 'wrap freeze' in o2.actions[0], o2)
    o = dot.run_line(o2.actions[0][4:])
    o = wait_done(dot, o)
    t.check('r2 C2: the freeze of a run diverged at the incident runs (no WRAP_BINDING_SUBCOMMAND) and its FZ is marked reset_diverged',
            lambda: o.code == 0 and (o.result.get('package') or '').startswith('FZ_A_') and o.result.get('reset_diverged') is True
            and o.actions and o.actions[0].endswith(f'evict --job-dir {jb}'), o)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} wrap prepare'))
    t.check('r2 C2: after the evict status moves on to reader B (case a), no restart of the diverged run',
            lambda: '--reader B' in o.actions[0] and f'/jobs/{ca}/' in o.actions[0]
            and json.loads((w.base / 'outbox/frozen_json' / f'A_{cb}_FLAGS.json').read_text())['reset_diverged'] is True, o)


@scenario
def r2_fixes_b(t):
    """r2 M2 (a prepare lost after an FZ binds the seen token), R2-03 (a boot change while a detached wrap ran goes to the
    incident; job commands wait for it), N1 (the incident names the restore session after a new chat), and
    QUALIFICATION_DIVERGED_RESTART_CONFLICT (reader A's run failed by divergence after a stop the runner would restart)."""
    c, na = '9992201', '9992291'
    w = World(t, 'r2_fixes_b_w', cases=[c], nonattempts=[na])
    dot = Dot(w)
    behaviour = {'G': 'nothing'}

    def conv(jd, case, role, reader):
        if behaviour.get(role) == 'nothing':
            return
        if role == 'G':
            tcj.stand_in_response(None, jd, case, reader=reader)
        else:
            tcj.stand_in_review(jd, reviewer=dict(tcj.REVIEWER, conversation_id=dot.values['CONVERSATION_ID']))
    dot.conv = {'G': conv, 'V': conv}
    o = to_prepare(t, dot, w)
    jd = w.job_dir('A', c)
    # M2: the prepare after the nonattempt FZs ran, its CP-P never reached Drive
    dot.stop_before_upload = ('CP_', 'wrap prepare')
    o = dot.auto(o)
    tok = list(dot.pending_tokens)
    t.check('r2 setup: the prepare ran (token seen), CP-P not uploaded', lambda: tok and tok[-1].startswith(f'B1/prepare/A/{c}/'), o)
    w.wipe()
    o = dot.session()
    t.check('r2 M2: a prepare lost after an FZ: the restore offers NON_AI_STAGE_LOST SEEN/NOT_SEEN (not NONE_IN_FLIGHT)',
            lambda: 'NON_AI_STAGE_LOST' in dict(o.options).get('SEEN', '') and 'NOT_SEEN' in dict(o.options), o)
    o = dot.auto(o, choose=lambda o_: 'SEEN', halt=at_action(f'RUN {w.V} recheck'))
    inc = [i for i in incident_notes(w) if i['classification'] == 'NON_AI_STAGE_LOST']
    t.check('r2 M2: the incident binds the pending prepare with the seen token', lambda: inc and inc[-1]['next_subcommand'] == 'prepare'
            and inc[-1]['seen'] == tok[-1:] and (inc[-1]['pending_job'] or {}).get('case') == c, inc)
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    o = dot.auto(o, halt=at_action('OPEN_CONVERSATION'))
    rp = [h for h in dot.history if h.result.get('command') == 'wrap' and h.result.get('runner_subcommand') == 'prepare']
    t.check('r2 M2: after the evict the re-run prepare compared its token with the one seen: matched',
            lambda: rp and (rp[-1].result.get('binding') or {}).get('matched') is True and rp[-1].result['binding']['seen'] == tok[-1:], rp[-1:])
    # R2-03: a reboot that keeps the disk while a detached wrap of the old boot is recorded; the conversation was open
    d = {'id': '20261109T000000Z_deadbeef', 'kind': 'wrap', 'info': {'job_dir': str(jd), 'sub': 'finish'}, 'pid': 999999,
         'started_utc': '2026-11-09T00:00:00Z', 'boot_id': w.boot, 'log': str(w.base / 'outbox' / 'x.log'),
         'out': str(w.base / 'outbox' / 'x.out'), 'exit': None}
    (w.base / 'outbox' / 'DETACHED.json').write_text(json.dumps(d))
    w.new_boot()
    o = dot.session()
    first_session = o.result.get('session_note')
    t.check('r2 R2-03: after a boot change with a detached wrap of the old boot, session prints the incident (no wait, no WORKER_DIED) '
            'and drops DETACHED.json', lambda: o.code == 0 and o.state.get('pending_incident') == 'yes' and 'CHOOSE_FROM_TRANSCRIPT' in o.actions
            and not (w.base / 'outbox' / 'DETACHED.json').exists(), o)
    gate = [dot.vm('ai-archive', '--job-dir', jd, '--role', 'G'), dot.vm('package', '--job-dir', jd),
            dot.vm('link-note', '--job-dir', jd, '--role', 'G', '--conversation', 'invented-c'), dot.vm('evict', '--job-dir', jd),
            dot.vm('final')]
    t.check('r2 R2-03: ai-archive, package, link-note, evict and final wait for the incident (INCIDENT_REQUIRED)',
            lambda: all(g.refused == 'INCIDENT_REQUIRED' for g in gate), gate)
    o = dot.session()
    dot.values['CONVERSATION_ID'] = 'invented-conv-r2b-G'
    t.check('r2 N1: a new chat before the incident keeps the pending incident (local mode)', lambda: o.code == 0
            and o.state.get('pending_incident') == 'yes' and session_note(w, o).get('mode') == 'local', o)
    o = dot.auto(o, choose=lambda o_: 'NOTHING_WRITTEN', halt=at_action(f'RUN {w.V} recheck'))
    inc = [i for i in incident_notes(w) if i['classification'] == 'AI_NOTHING_WRITTEN']
    t.check('r2 N1: the incident names the SESSION that asked for it (restore_session), not only the later chat\'s',
            lambda: inc and inc[-1].get('restore_session') == first_session and inc[-1].get('session_note') != first_session, inc)
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    t.check('r2 setup: status prints wrap interrupt', lambda: o.actions and ' wrap interrupt ' in o.actions[0], o)
    # QUALIFICATION_DIVERGED_RESTART_CONFLICT: the freeze after the interrupt ran; its FZ was lost; a different token is seen
    dot.stop_before_upload = ('FZ_', 'wrap freeze')
    o = dot.auto(o)
    real = list(dot.pending_tokens)
    t.check('r2 setup: interrupt (form 1) then the freeze ran, the FZ not uploaded', lambda: real and real[-1].startswith(f'B1/freeze/A/{c}/'), o)
    w.wipe()
    o = dot.session()
    dot.pending_tokens = [forge_token(real[-1])]
    o = dot.auto(o, choose=lambda o_: 'SEEN', halt=at_action(f'RUN {w.V} recheck'))
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    dot.pending_tokens = []
    o = dot.auto(o, halt=lambda a, o_: o_.stop is not None)
    t.check('r2 R2-04: reader A failed by divergence after a stop the runner would restart: STOP QUALIFICATION_DIVERGED_RESTART_CONFLICT',
            lambda: o.stop == 'QUALIFICATION_DIVERGED_RESTART_CONFLICT'
            and json.loads((w.base / 'outbox/frozen_json' / f'A_{c}_FLAGS.json').read_text())['reset_diverged'] is True, o)


@scenario
def r2_fixes_c(t):
    """r2 M3 (the replacement reviewer's START does not supersede; a reset before its conversation is AI_NO_CONVERSATION), R2-01
    (nothing written: both options; INCIDENT_TRANSCRIPT_REQUIRED for an absent or empty transcript, with the AI_WRITTEN_LOST
    line), INCIDENT_NEEDS_JOB, REVISION_LIMIT and INCIDENT_CONTRADICTS_EARLIER."""
    c1, c2 = '9992301', '9992302'
    w = World(t, 'r2_fixes_c_w', cases=[c1, c2], cfg={'max_review_revisions': 0})
    dot = Dot(w)
    calls = {}

    def conv(jd, case, role, reader):
        k = (case, role)
        calls[k] = calls.get(k, 0) + 1
        if case == c1 and role == 'V' and calls[k] == 1:
            return                                          # the first reviewer writes nothing
        if case == c2 and role == 'G':
            return                                          # c2's generator writes nothing
        if role == 'G':
            tcj.stand_in_response(None, jd, case, reader=reader)
        elif role == 'V':
            tcj.stand_in_review(jd, drop_page=True, reviewer=dict(tcj.REVIEWER, conversation_id=dot.values['CONVERSATION_ID']))
    dot.conv = {'G': conv, 'V': conv}
    j1 = w.job_dir('A', c1)
    dot.conv['V-continue'] = lambda: tcj.stand_in_review(j1, reviewer=dict(tcj.REVIEWER, conversation_id=dot.values['CONVERSATION_ID']))
    o = to_prepare(t, dot, w)
    o = dot.auto(o, halt=at_action('CHOOSE_FROM_TRANSCRIPT'))
    tp = w.base / 'transcripts' / f'{c1}_A_V1.txt'
    t.check('r2 R2-01: a reviewer that wrote nothing: CHOOSE_FROM_TRANSCRIPT with NOTHING_WRITTEN and WRITTEN_OR_DOUBT (AI_WRITTEN_LOST)',
            lambda: o.result.get('command') == 'ai-archive' and set(dict(o.options)) == {'NOTHING_WRITTEN', 'WRITTEN_OR_DOUBT'}
            and 'AI_WRITTEN_LOST' in dict(o.options)['WRITTEN_OR_DOUBT'] and '--transcript' not in dict(o.options)['WRITTEN_OR_DOUBT'], o)
    n1 = dot.vm('incident', '--classification', 'AI_NOTHING_WRITTEN', '--conversation-ended', '--conversation', 'invented-c')
    n2 = dot.vm('incident', '--classification', 'AI_NOTHING_WRITTEN', '--job-dir', j1, '--role', 'V', '--conversation-ended',
                '--transcript', tp)
    t.check('r2 R2-04: incident without --job-dir/--role, or without --conversation, is refused INCIDENT_NEEDS_JOB',
            lambda: n1.refused == 'INCIDENT_NEEDS_JOB' and n2.refused == 'INCIDENT_NEEDS_JOB', (n1, n2))
    if tp.exists():
        tp.unlink()
    r_abs = dot.vm('incident', '--classification', 'AI_NOTHING_WRITTEN', '--job-dir', j1, '--role', 'V', '--conversation', 'invented-c',
                   '--conversation-ended', '--transcript', tp)
    tp.parent.mkdir(parents=True, exist_ok=True)
    tp.write_bytes(b'')
    r_empty = dot.vm('incident', '--classification', 'AI_NOTHING_WRITTEN', '--job-dir', j1, '--role', 'V', '--conversation', 'invented-c',
                     '--conversation-ended', '--transcript', tp)
    t.check('r2 R2-01: an absent or empty transcript is refused INCIDENT_TRANSCRIPT_REQUIRED, with the AI_WRITTEN_LOST line as NEXT',
            lambda: all(r.code == 4 and r.result.get('code') == 'INCIDENT_TRANSCRIPT_REQUIRED' and r.actions
                        and 'incident --classification AI_WRITTEN_LOST' in r.actions[0] for r in (r_abs, r_empty))
            and not names(w.drive, w.records, 'TRANSCRIPT_'), (r_abs, r_empty))
    tp.unlink()
    dot.stop_after_upload = ('START_A_V2', None)
    o = dot.auto(o)
    sv2 = o.result
    t.check('r2 M3: the replacement reviewer START (V2) has no supersedes; it names V1 in replaces', lambda: sv2.get('command') == 'start-note'
            and sv2.get('attempt') == 2 and sv2.get('supersedes') is None and (sv2.get('replaces') or '').startswith('START_A_V1_'), sv2)
    w.wipe()
    o = dot.session()
    t.check('r2 M3: a reset before the V2 conversation existed offers NO_CONVERSATION', lambda: 'NO_CONVERSATION' in dict(o.options), o)
    o = dot.auto(o, choose=lambda o_: 'NO_CONVERSATION', halt=at_action(f'RUN {w.V} recheck'))
    t.check('r2 M3: AI_NO_CONVERSATION for the replacement reviewer is recorded (no STOP AI_NO_CONVERSATION_REPEATED)',
            lambda: o.stop is None and o.result.get('classification') == 'AI_NO_CONVERSATION', o)
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    o = dot.auto(o, halt=at_action('OPEN_CONVERSATION'))
    t.check('r2 M3: the re-START is attempt 2 and supersedes the first V2 START', lambda: o.result.get('attempt') == 2
            and o.result.get('supersedes') == sv2['start_note'], o)
    # REVISION_LIMIT (max_review_revisions 0): the review comes back incomplete; the first revision stops
    o = dot.auto(o, halt=lambda a, o_: o_.stop is not None)
    t.check('r2 R2-04: a revision beyond max_review_revisions is STOP REVISION_LIMIT', lambda: o.stop == 'REVISION_LIMIT', o)
    o = dot.run_line(f'{w.V} wrap freeze --job-dir {j1} --operator-model {MODEL}')
    o = wait_done(dot, o)
    o = dot.auto(o, halt=lambda a, o_: a.startswith(f'RUN {w.V} wrap prepare') and f'/jobs/{c2}/' in a)
    t.check('r2 setup: case 1 frozen by hand after the STOP; status moves to case 2', lambda: f'/jobs/{c2}/' in o.actions[0], o)
    # INCIDENT_CONTRADICTS_EARLIER: c2's generator wrote nothing; WRITTEN_OR_DOUBT is recorded; NOTHING_WRITTEN is then refused
    j2 = w.job_dir('A', c2)
    o = dot.auto(o, halt=at_action('CHOOSE_FROM_TRANSCRIPT'))
    o = dot.run_line(dict(o.options)['WRITTEN_OR_DOUBT'][4:].replace('{CONVERSATION_ID}', 'invented-c2'))
    t.check('r2 setup: AI_WRITTEN_LOST recorded for c2\'s generator; status prints wrap freeze', lambda: o.code == 0
            and o.result.get('classification') == 'AI_WRITTEN_LOST' and 'wrap freeze' in o.actions[0], o)
    tr = w.root / 'transcript_c2.txt'
    tr.write_text('invented transcript\n')
    rc = dot.vm('incident', '--classification', 'AI_NOTHING_WRITTEN', '--job-dir', j2, '--role', 'G', '--conversation', 'invented-c2',
                '--conversation-ended', '--transcript', tr)
    t.check('r2 R2-04: AI_NOTHING_WRITTEN after AI_WRITTEN_LOST on the same START is refused INCIDENT_CONTRADICTS_EARLIER',
            lambda: rc.refused == 'INCIDENT_CONTRADICTS_EARLIER', rc)


@scenario
def r2_fixes_d(t):
    """r2 M5 (an everyday prepare refused before its folder existed: FIX, then job-start gives the same run new inputs; a restore
    places the newest inputs) and RESTORE_RECORD_PREFIX_MISMATCH (everyday)."""
    c = '9992401'
    w = World(t, 'r2_fixes_d_w', mode='everyday', cases=[c], cfg={'wrap_foreground_seconds': 1})
    dot = Dot(w)
    o = start_world(t, dot, w)
    everyday_inputs(w, c)
    jp = w.base / 'everyday_inputs' / c / 'JOB.json'
    good = jp.read_bytes()
    jp.write_bytes((json.dumps(dict(json.loads(good), invented_unknown_key=1), ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
    dot.values['CASE'] = c
    o = dot.run_line(o.actions[1][4:])
    tag, first_inputs = o.result['run_id'], o.result['inputs']
    o = wait_done(dot, dot.run_line(o.actions[0][4:]))
    t.check('r2 M5: the runner refuses the prepare before making the folder: FIX code=RUNNER_<code>, THEN job-start --case',
            lambda: o.code == 4 and o.actions and o.actions[0].startswith('FIX code=RUNNER_') and o.actions[1] == f'RUN {w.V} job-start --case {c}'
            and not w.job_dir(tag, c).exists(), o)
    st_ = dot.vm('status')
    same = dot.vm('job-start', '--case', c)
    t.check('r2 M5: status prints the same FIX and job-start; job-start with the inputs unchanged is refused JOB_START_INPUTS_UNCHANGED',
            lambda: st_.actions == o.actions and same.refused == 'JOB_START_INPUTS_UNCHANGED', (st_, same))
    jp.write_bytes(good)
    o = dot.run_line(st_.actions[1][4:])
    t.check('r2 M5: job-start after the fix gives the same run new inputs (replaces the refused INPUTS) and prints its prepare',
            lambda: o.code == 0 and o.result.get('run_id') == tag and o.result.get('replaces') == first_inputs
            and o.result.get('inputs') != first_inputs and 'wrap prepare' in o.actions[0], o)
    dot.stop_before_upload = ('CP_', None)
    o = dot.auto(o)
    t.check('r2 setup: the prepare with the corrected inputs ran', lambda: w.job_dir(tag, c).exists() and dot.pending_tokens, o)
    w.wipe()
    o = dot.session()
    t.check('r2 M5: the restore places the newest INPUTS of the run (the corrected JOB.json) and offers NON_AI_STAGE_LOST',
            lambda: o.code == 0 and jp.is_file() and jp.read_bytes() == good and 'NON_AI_STAGE_LOST' in dict(o.options).get('SEEN', ''), o)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} recheck'))
    w.drive.listing(w.records, w.base / 'inbox' / 'DRIVE_LISTING.json')
    o = dot.vm('recheck')
    o = dot.auto(o, halt=at_action('OPEN_CONVERSATION'))
    t.check('r2 M5: the run goes on (prepare re-run, START G)', lambda: o.result.get('command') == 'start-note', o)
    # RESTORE_RECORD_PREFIX_MISMATCH: a package of this run whose record is not a prefix of the restored one
    cpp = newest_pkg(w, c)
    p_ = vm.parse_name(cpp)
    fake = vm.package_name('CP', tag, 'R', 0, '00000000', 'ffffffff', '00000000', p_['fp8'], '0' * 8, c)
    w.drive.put(w.records, fake, b'invented package that never existed\n')
    w.wipe()
    o = dot.session()
    t.check('r2 R2-04: a listed package of the run that does not extend its record: STOP RESTORE_RECORD_PREFIX_MISMATCH',
            lambda: o.stop == 'RESTORE_RECORD_PREFIX_MISMATCH', o)


@scenario
def r2_fixes_e(t):
    """r2 M4 (final takes the FZ copy whose bytes were checked, never the first listed copy), UPLOAD_NOT_CONFIRMED and
    VERIFY_PART_MISMATCH (evict), on worlds with nonattempts only."""
    na = '9992591'
    w = World(t, 'r2_fixes_e_w', nonattempts=[na])
    dot = Dot(w)
    dot.truncate_upload = lambda n: n.startswith('FZ_NA-A_')
    o = start_world(t, dot, w)
    o = dot.auto(o, halt=at_action(f'RUN {w.V} final'))
    fza = [f for f in w.drive.files(w.records) if f['name'].startswith('FZ_NA-A_')]
    t.check('r2 setup: NA-A\'s FZ landed twice (a partial copy first, then the whole one)', lambda: len(fza) == 2 and fza[0]['size'] < fza[1]['size'], fza)
    w.wipe()
    o = dot.session()
    o = dot.auto(o, halt=at_action(f'RUN {w.V} final'))
    t.check('r2 setup: after a wipe status reaches final again', lambda: o.actions and o.actions[0].endswith(' final'), o)
    o = dot.auto(o, halt=at_action('HANDBACK'))
    af = read_json(w.base / 'outbox' / 'ALL_FROZEN.json')
    run = next((r for r in af.get('runs', []) if r['tag'] == 'NA-A'), {})
    ev = [json.loads(x) for x in (w.base / 'outbox' / 'INDEX.jsonl').read_text().splitlines() if '"final_rejected"' in x]
    t.check('r2 M4: final rejects the partial first copy and records the whole copy\'s id and md5 in ALL_FROZEN.json',
            lambda: o.actions == ['HANDBACK case=B'] and run.get('archive', {}).get('id') == fza[1]['id']
            and run['archive']['md5'] == fza[1]['md5'] and any(e.get('drive_id') == fza[0]['id'] for e in ev), (o, run.get('archive'), ev))
    flat = w.drive.flat(w.records, w.root / 'maint' / 'qualification')
    w.wipe()
    p = subprocess.run([sys.executable, '-I', '-B', str(HELPER), 'assemble', '--drive-dir', str(flat)], capture_output=True, text=True, timeout=600)
    t.outputs.append(p.stdout)
    t.check('r2 M4: assemble accepts ALL_FROZEN.json (the md5 it records is the intact copy\'s)', lambda: p.returncode == 0, p.stdout[-600:])
    # UPLOAD_NOT_CONFIRMED: an FZ upload that never lands
    w2 = World(t, 'r2_fixes_e_w2', nonattempts=[na])
    dot2 = Dot(w2)
    dot2.skip_upload = lambda n: n.startswith('FZ_NA-A_')
    o = start_world(t, dot2, w2)
    o = dot2.auto(o, halt=lambda a, o_: o_.stop is not None, max_steps=60)
    t.check('r2 R2-04: an FZ that never shows on Drive: evict re-uploads it three times, then STOP UPLOAD_NOT_CONFIRMED',
            lambda: o.stop == 'UPLOAD_NOT_CONFIRMED' and o.result.get('detail', {}).get('name', '').startswith('FZ_NA-A_'), o)
    # VERIFY_PART_MISMATCH: the only copy on Drive is damaged and the local FZ is gone
    w3 = World(t, 'r2_fixes_e_w3', nonattempts=[na])
    dot3 = Dot(w3)
    dot3.skip_upload = lambda n: n.startswith('FZ_NA-A_')
    o = start_world(t, dot3, w3)
    o = dot3.auto(o, halt=at_action(f'RUN {w3.V} evict'))
    fzp = sorted((w3.base / 'outbox').glob('FZ_NA-A_*.tgz'))
    t.check('r2 setup: NA-A frozen, its FZ held back', lambda: len(fzp) == 1 and not names(w3.drive, w3.records, 'FZ_NA-A_'), o)
    w3.drive.put(w3.records, fzp[0].name, fzp[0].read_bytes()[:300])
    fzp[0].unlink()
    dot3.skip_upload = None
    o = dot3.auto(o, halt=lambda a, o_: o_.stop is not None, max_steps=20)
    t.check('r2 R2-04: no intact copy on Drive and no local source: evict STOPs VERIFY_PART_MISMATCH', lambda: o.stop == 'VERIFY_PART_MISMATCH', o)


@scenario
def r2_units(t):
    """r2 R2-03 tests (a Drive default-fields listing names the missing field), R2-07 (packing refuses names restore refuses),
    R2-08 (session_start uploads only non-empty files), R2-02 (a cut-off note download is downloaded again)."""
    root = t.work / 'r2_units_w'
    root.mkdir()
    lp = root / 'L.json'
    lp.write_text(json.dumps({'schema': 'cps.vm-drive-listing.v1', 'folder': 'CPS/qualification', 'name_filter': None,
                              'pages': [{'kind': 'drive#fileList', 'files': [{'kind': 'drive#file', 'id': 'x1', 'name': 'GENESIS_0a1b2c3d_20261109T120000Z.json',
                                                                              'mimeType': 'application/json'}]}]}))
    try:
        vm.parse_listing(lp, 'CPS/qualification', None, {'listing_page_marker': 'required'})
        h = None
    except vm.Halt as e:
        h = e
    t.check('r2 R2-03: a default-fields Drive page is refused LISTING_INVALID naming createdTime, the page and the entry',
            lambda: h is not None and h.code == 'LISTING_INVALID' and h.detail.get('missing') == ['createdTime'] and h.detail.get('entry') == 1
            and 'createdTime' in h.hint, lambda: (h and (h.code, h.hint, h.detail)))
    readme = (HERE / 'README.md').read_text()
    t.check('r2 R2-03: README rule 0.2 names the listing fields', lambda: all(f in readme for f in ('createdTime', 'md5Checksum', 'nextPageToken',
                                                                                                     'incompleteSearch')))
    src = root / 'src'
    src.mkdir()
    (src / 'a\\b.txt').write_text('x')
    t.check('r2 R2-07: tree_list refuses a name restore would refuse (backslash)', lambda: halt_code(vm.tree_list, src) == 'PACKAGE_UNSUPPORTED_ENTRY')
    # session_start.sh with a failing setup (empty log) and a failing environment check (no report written)
    mini = root / 'mini'
    (mini / 'deploy' / 'vm').mkdir(parents=True)
    shutil.copyfile(SESSION_SH, mini / 'deploy' / 'vm' / 'session_start.sh')
    (mini / 'deploy' / 'setup_vm_user.sh').write_text('#!/bin/bash\n# invented stub\nif [ -f "$STUB_SETUP_OK" ]; then mkdir -p "$CPS_TOOLS"; '
                                                      'echo "export INVENTED=1" > "$CPS_TOOLS/env.sh"; exit 0; fi\nexit 1\n')
    (mini / 'deploy' / 'check_env.py').write_text('import sys\nprint("invented check: not met", file=sys.stderr)\nprint("{\\"all_met\\": false}")\n')
    g = ['git', '-C', str(mini), '-c', 'user.name=invented test', '-c', 'user.email=invented@example.invalid']
    subprocess.run(['git', 'init', '-q', str(mini)], check=True)
    subprocess.run(g + ['add', '-A'], check=True)
    subprocess.run(g + ['commit', '-q', '-m', 'invented mini repo'], check=True)
    base, tools, home = root / 'base', root / 'tools', root / 'home'
    for d_ in (base, home):
        d_.mkdir()
    os.symlink(mini, base / 'repo')
    (root / 'boot').write_text('invented-boot\n')
    env = dict(os.environ, HOME=str(home), CPS_VM_BASE=str(base), CPS_TOOLS=str(tools), CPS_VM_BOOT_ID_PATH=str(root / 'boot'),
               STUB_SETUP_OK=str(root / 'setup_ok'))
    r1 = subprocess.run(['bash', str(base / 'repo' / 'deploy' / 'vm' / 'session_start.sh'), '--operator-model', MODEL], capture_output=True, text=True, env=env)
    t.outputs.append(r1.stdout)
    t.check('r2 R2-08: a failed setup with an empty log: STOP SETUP_FAILED and no UPLOAD of the empty log', lambda: r1.returncode == 3
            and 'STOP: SETUP_FAILED' in r1.stdout and 'UPLOAD ' not in r1.stdout, r1.stdout[-600:])
    (root / 'setup_ok').write_text('1')
    r2 = subprocess.run(['bash', str(base / 'repo' / 'deploy' / 'vm' / 'session_start.sh'), '--operator-model', MODEL], capture_output=True, text=True, env=env)
    t.outputs.append(r2.stdout)
    ups = [ln[7:].split(' -> ')[0] for ln in r2.stdout.splitlines() if ln.startswith('UPLOAD ')]
    t.check('r2 R2-08: a failed environment check without its report: STOP CHECK_ENV_FAILED, UPLOAD only of the non-empty check log',
            lambda: r2.returncode == 3 and 'STOP: CHECK_ENV_FAILED' in r2.stdout and len(ups) == 1 and 'check_env_' in ups[0]
            and os.path.getsize(ups[0]) > 0, r2.stdout[-600:])
    t.check('r2 R2-08: every line session_start printed has the helper grammar', lambda: all(ln.startswith(PREFIXES) for ln in
            (r1.stdout + r2.stdout).splitlines() if ln.strip()), (r1.stdout + r2.stdout)[-800:])


def read_json(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return {}


if __name__ == "__main__":
    sys.exit(main())
