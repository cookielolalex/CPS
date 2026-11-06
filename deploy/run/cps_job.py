#!/usr/bin/env python3
"""CPS operator job runner: one CPS job, stage by stage, with one record (deploy/run/cps_job.py).

Python 3 standard library only. Every CPS tool runs as a subprocess with `python3 -I -B` (the interpreter that runs
this file; the inventory builder with `-I -S -B`, as the harness README states) and the node on PATH. Paths are
arguments or come from the release file; relative release paths are taken from the repository root. The runner never
prints cell text, job-input values or the job title: it prints hashes, counts, codes, the path of the next prompt and,
at delivery, the path of the one file to deliver. Tool output is kept in the job folder (logs/), never printed.

Subcommands (RUN_JOB_COMMANDS.md has the exact commands and what to do at each NEXT):
  prepare       --release RELEASE.json --job JOB.json --job-title-file JOB_TITLE.json --jobs-root DIR
                [--reader A|B] [--qualification --admission ADMISSION.json] [--operator-model TEXT]
  scope-finish  --job-dir D --reader-response FILE
  finish        --job-dir D --response FILE [--job-title TEXT] [--generator-model TEXT]
  visual-record --job-dir D --review VISUAL_REVIEW.json
  deliver-check --job-dir D
  freeze        --job-dir D            (qualification protocol step 5: FROZEN.json; then the folder is read-only)

Each subcommand appends one entry (two for finish) to <job>/RUN_RECORD.json and never rewrites earlier entries; a
stage that completed (with any result, a recorded failure included) is never run again in the same job folder. The
last line printed is the next step: NEXT: SCOPE_READER, GENERATE, OWNER_DECISION, VISUAL_REVIEW, DELIVER_CHECK, FREEZE,
DELIVER, DONE or STOP_<reason>.
Exit codes: 0 continue with the NEXT step; 3 the job stopped (NEXT: STOP_<reason> or OWNER_DECISION, recorded);
4 refused (nothing consumed; the record notes the refusal when the job folder exists); 2 usage.
"""
import argparse, datetime, hashlib, json, os, re, shutil, stat, subprocess, sys, unicodedata
from pathlib import Path

sys.dont_write_bytecode = True
VERSION = 'cps-job-runner.v1'
HERE = Path(__file__).resolve().parent
RECORD_SCHEMA = 'cps.job-run-record.v1'
RELEASE_SCHEMA = 'cps.release.v1'
JOB_SCHEMA = 'cps.job-config.v2'
TITLE_SCHEMA = 'cps.job-title.v1'
ADMISSION_SCHEMA = 'cps.admission.046b.v1'
WRITER_ADMISSION_SCHEMA = 'cps.writer-admission.v1'
REVIEW_SCHEMA = 'cps.visual-review.v1'
EVIDENCE_SCHEMA = 'cps.job-qa-evidence.v1'
STATUS_FOR_MODE = {True: 'RELEASED_FOR_QUALIFICATION', False: 'RELEASED_FOR_USE'}
CASE_ID_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', re.ASCII)
LAYOUT = ('input', 'packet', 'scope', 'run', 'response', 'carrier', 'export', 'qa', 'logs')
CONDITION3_TOOLS = ('research/export/saved_qa.py', 'research/export/writer_portable.py',
                    'research/export/writer004_matrices.mjs', 'research/export/visual_qa.py')
WRITER_FILES = ('writer004.mjs', 'validate_carrier_v4.mjs', 'receipt_bytes.mjs')
REVIEW_SHEET = '來源與審查'
COMPOSITION_SHEETS = ('組成參考', '組成連結')
ITEMS = tuple(str(i) for i in range(1, 10))
RESULTS = ('pass', 'fail', 'n/a')
SAVED_PASS = 'SAVED_ALL_CELL_VALUE_TYPE_PASS'
OPENPYXL_VERSION = '3.1.5'
EXIT_CONTINUE, EXIT_USAGE, EXIT_STOP, EXIT_REFUSED = 0, 2, 3, 4
CONTINUE_STEPS = ('SCOPE_READER', 'GENERATE', 'VISUAL_REVIEW', 'DELIVER_CHECK', 'FREEZE', 'DELIVER', 'DONE')
RO = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH


# ------------------------------------------------------------------ small helpers
class Refused(Exception):
    """Refused before anything was consumed: recorded as a not-completed attempt, the stage may run again."""
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


class Outcome(Exception):
    """The stage ends here with a recorded result (completed; never run again)."""
    def __init__(self, result, next_step, codes=()):
        super().__init__(result)
        self.result, self.next_step, self.codes = result, next_step, list(codes)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _no_constant(x):
    raise ValueError('NaN/Infinity not allowed')


def strict_json(raw, what):
    """Strict JSON: UTF-8, no duplicate keys, no NaN/Infinity."""
    def hook(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise Refused('DUPLICATE_JSON_KEY', {'file': what})
            out[k] = v
        return out
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=hook, parse_constant=_no_constant)
    except (UnicodeDecodeError, ValueError):
        raise Refused('INVALID_JSON', {'file': what})


def has_duplicate_keys(raw):
    try:
        strict_json(raw, 'x')
    except Refused as e:
        return e.code == 'DUPLICATE_JSON_KEY'
    return False


def read_json(p, what):
    return strict_json(Path(p).read_bytes(), what)


def dumps(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + '\n').encode('utf-8')


def write_new(p, data, readonly=True):
    """Write a new file (never overwrite); read-only by default."""
    p = Path(p)
    with open(p, 'xb') as f:
        f.write(data if isinstance(data, bytes) else data.encode('utf-8'))
    if readonly:
        p.chmod(RO)
    return sha_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))


def freeze_copy(src_bytes, dest):
    write_new(dest, src_bytes)
    if sha_file(dest) != sha_bytes(src_bytes):
        raise Refused('FREEZE_COPY_MISMATCH')
    return sha_bytes(src_bytes)


def make_readonly(root):
    for p in Path(root).rglob('*'):
        if p.is_file() and not p.is_symlink():
            p.chmod(p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def nfkc(s):
    return unicodedata.normalize('NFKC', s)


def get(d, *keys, required=True, kind=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            if required:
                raise Refused('RELEASE_FIELD_MISSING', {'field': '.'.join(keys)})
            return None
        cur = cur[k]
    if kind is not None and not isinstance(cur, kind):
        raise Refused('RELEASE_FIELD_TYPE', {'field': '.'.join(keys)})
    return cur


def is_sha(x):
    return isinstance(x, str) and len(x) == 64 and all(c in '0123456789abcdef' for c in x)


# ------------------------------------------------------------------ release file
class Release:
    """The fields of RELEASE.json the runner reads (RUN_JOB_COMMANDS.md, RELEASE.example.json)."""
    def __init__(self, raw, path_note):
        self.raw, self.sha = raw, sha_bytes(raw)
        d = strict_json(raw, 'release')
        if not isinstance(d, dict) or d.get('schema') != RELEASE_SCHEMA:
            raise Refused('RELEASE_SCHEMA', {'expected': RELEASE_SCHEMA})
        self.d, self.path_note = d, path_note
        root = get(d, 'repository', 'root', required=False)
        self.root = Path(os.path.expanduser(root)).resolve() if root else HERE.parents[1]
        if root and not Path(os.path.expanduser(root)).is_absolute():
            raise Refused('RELEASE_PATH_NOT_ABSOLUTE', {'field': 'repository.root'})
        self.status = get(d, 'status', kind=str)
        self.package = self.path(get(d, 'package', 'path', kind=str))
        self.manifest_sha = get(d, 'package', 'manifest_sha256', kind=str)
        self.harness = self.path(get(d, 'harness', 'path', kind=str))
        self.source_prep = self.path(get(d, 'source_prep', 'path', kind=str))
        self.deps_bundle = self.path(get(d, 'source_prep', 'deps_bundle', kind=str))
        np_ = get(d, 'source_prep', 'node_path', required=False, kind=str)
        self.node_path = self.path(np_) if np_ else None
        self.writer_admission = self.path(get(d, 'writer', 'admission', kind=str))
        self.writer_admission_sha = get(d, 'writer', 'admission_sha256', required=False, kind=str)
        self.writer_dir = self.path(get(d, 'writer', 'writer_dir', kind=str))
        self.admitted_nodes = get(d, 'admitted_checker_node_sha256', kind=list)
        self.clean_path = get(d, 'saved_qa_clean_path', required=False, kind=str) or '/usr/bin:/bin'
        self.tables = get(d, 'tables', kind=dict)
        self.pinned = get(d, 'pinned_files_sha256', required=False, kind=dict) or {}
        self.qual_admissions = get(d, 'qualification', 'admission_sha256', required=False, kind=list) or []
        self.route = self.package / 'tools' / 'cps046b_route.py'

    def path(self, value):
        p = Path(os.path.expanduser(value))
        return p if p.is_absolute() else self.root / p

    def summary(self):
        return {'sha256': self.sha, 'status': self.status, 'release_version': self.d.get('release_version'),
                'repository_commit': get(self.d, 'repository', 'commit', required=False),
                'package_manifest_sha256': self.manifest_sha}


def check_release_static(rel, qualification, st):
    """Checks that hold for every subcommand: status, repository commit, package manifest, pinned files."""
    want = STATUS_FOR_MODE[qualification]
    if rel.status != want:
        raise Refused('RELEASE_STATUS', {'status': rel.status, 'required': want})
    commit = get(rel.d, 'repository', 'commit', required=False)
    verified = None
    if commit:
        try:
            p = subprocess.run(['git', '-C', str(rel.root), 'rev-parse', 'HEAD'], capture_output=True, timeout=60)
            head = p.stdout.decode('ascii', 'replace').strip() if p.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            head = None
        if head is not None:
            if head != commit:
                raise Refused('REPOSITORY_COMMIT_MISMATCH', {'release_commit': commit, 'head': head})
            verified = True
    st.facts['repository'] = {'commit': commit, 'commit_verified_with_git': verified}
    check_package(rel, st)
    bad = []
    for rp, want_sha in sorted(rel.pinned.items()):
        p = rel.path(rp)
        got = sha_file(p) if p.is_file() else None
        st.tools[rp] = got
        if got != want_sha:
            bad.append(rp)
    if bad:
        raise Refused('PINNED_FILE_MISMATCH', {'files': bad})


def check_package(rel, st):
    man = rel.package / 'PACKAGE_MANIFEST.json'
    if not man.is_file():
        raise Refused('PACKAGE_MANIFEST_MISSING')
    raw = man.read_bytes()
    if sha_bytes(raw) != rel.manifest_sha:
        raise Refused('PACKAGE_MANIFEST_SHA256_MISMATCH', {'release': rel.manifest_sha, 'found': sha_bytes(raw)})
    m = strict_json(raw, 'package manifest')
    listed = {}
    for f in m.get('files', []):
        listed[f['path']] = f['sha256']
    bad = sorted(p for p, h in listed.items() if not (rel.package / p).is_file() or sha_file(rel.package / p) != h)
    extra = sorted(p.relative_to(rel.package).as_posix() for p in rel.package.rglob('*')
                   if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'
                   and p.relative_to(rel.package).as_posix() not in listed and p.name != 'PACKAGE_MANIFEST.json')
    if bad or extra:
        raise Refused('PACKAGE_FILES_MISMATCH', {'changed_or_missing': bad, 'unlisted': extra})
    st.facts['package'] = {'manifest_sha256': rel.manifest_sha, 'files_verified': len(listed)}


def load_writer_admission(rel):
    if not rel.writer_admission.is_file():
        raise Refused('WRITER_ADMISSION_MISSING')
    raw = rel.writer_admission.read_bytes()
    if rel.writer_admission_sha and sha_bytes(raw) != rel.writer_admission_sha:
        raise Refused('WRITER_ADMISSION_SHA256_MISMATCH')
    adm = strict_json(raw, 'writer admission')
    if adm.get('schema') != WRITER_ADMISSION_SCHEMA:
        raise Refused('WRITER_ADMISSION_SCHEMA')
    return adm, sha_bytes(raw)


def checker_node(rel, adm):
    """Condition 2: the pinned checker node (release checker_node, else the admission's), admitted by sha256."""
    cn = rel.d.get('checker_node') or adm.get('checker_node') or {}
    path, declared = cn.get('path'), cn.get('sha256')
    if not isinstance(path, str) or not Path(path).is_absolute() or not is_sha(declared):
        raise Refused('CHECKER_NODE_UNDECLARED', 'checker_node.path (absolute) and checker_node.sha256 in the release or the admission')
    p = Path(path)
    if not p.is_file():
        raise Refused('CHECKER_NODE_MISSING')
    actual = sha_file(p)
    if declared not in rel.admitted_nodes or actual not in rel.admitted_nodes:
        raise Refused('CHECKER_NODE_NOT_ADMITTED', {'sha256': actual, 'admitted': rel.admitted_nodes})
    if actual != declared:
        raise Refused('CHECKER_NODE_SHA256_MISMATCH', {'declared': declared, 'actual': actual})
    return {'path': str(p), 'realpath': os.path.realpath(p), 'sha256': actual,
            'source': 'release checker_node' if rel.d.get('checker_node') else 'writer admission checker_node'}


def check_export_tools(rel, adm):
    """Condition 3: the four export tools against files_sha256 (hard), every other listed file recorded."""
    fs = adm.get('files_sha256') or {}
    out, bad = {}, []
    for k, want in sorted(fs.items()):
        p = rel.root / k
        got = sha_file(p) if p.is_file() else None
        out[k] = {'sha256': got, 'admitted': want, 'match': got == want, 'required': k in CONDITION3_TOOLS}
        if k in CONDITION3_TOOLS and got != want:
            bad.append(k)
    missing = [k for k in CONDITION3_TOOLS if k not in fs]
    if bad or missing:
        raise Refused('EXPORT_TOOL_HASH_MISMATCH', {'files': bad, 'not_in_admission': missing})
    return out


def check_writer_dir(rel, adm):
    """Condition 4: the pinned writer files as regular files, and the CPS validation stub."""
    pins = adm.get('writer_dir_sha256') or {}
    w = rel.writer_dir
    out, bad = {}, []
    for name in WRITER_FILES:
        p = w / name
        allowed = pins.get(name)
        allowed = set(allowed.values()) if isinstance(allowed, dict) else {allowed}
        regular = p.exists() and stat.S_ISREG(os.lstat(p).st_mode)
        got = sha_file(p) if regular else None
        out[name] = {'sha256': got, 'regular_file': regular, 'match': got in allowed}
        if not regular or got not in allowed:
            bad.append(name)
    stub = w.parent / 'node_modules' / '@oai' / 'artifact-tool'
    for name, key in (('index.mjs', 'artifact_tool_stub_index.mjs'), ('package.json', 'artifact_tool_stub_package.json')):
        p = stub / name
        got = sha_file(p) if p.is_file() else None
        out['stub/' + name] = {'sha256': got, 'match': got == pins.get(key)}
        if got != pins.get(key):
            bad.append('stub/' + name)
    if bad:
        raise Refused('WRITER_DIR_NOT_PINNED', {'files': bad})
    return out


def check_openpyxl():
    p = subprocess.run([sys.executable, '-I', '-B', '-c', 'import openpyxl; print(openpyxl.__version__)'], capture_output=True, timeout=120)
    v = p.stdout.decode('ascii', 'replace').strip() if p.returncode == 0 else None
    if v != OPENPYXL_VERSION:
        raise Refused('OPENPYXL_VERSION', {'found': v, 'required': OPENPYXL_VERSION})
    return v


def export_preflight(rel, st):
    adm, adm_sha = load_writer_admission(rel)
    st.facts['writer_admission_sha256'] = adm_sha
    node = checker_node(rel, adm)
    st.facts['checker_node'] = node
    tools = check_export_tools(rel, adm)
    for k, v in tools.items():
        st.tools[k] = v['sha256']
    st.facts['export_tools_condition3'] = {k: v['match'] for k, v in tools.items() if v['required']}
    st.facts['writer_dir_condition4'] = check_writer_dir(rel, adm)
    st.facts['openpyxl'] = check_openpyxl()
    return adm, adm_sha, node, tools


# ------------------------------------------------------------------ job folder and record
class Job:
    def __init__(self, d):
        self.dir = Path(d).resolve()
        self.record_path = self.dir / 'RUN_RECORD.json'
        self.rec, self.raw = None, None

    def p(self, *parts):
        return self.dir.joinpath(*parts)

    def rel(self, p):
        p = Path(p)
        try:
            return p.resolve().relative_to(self.dir).as_posix()
        except ValueError:
            return str(p)

    def load(self):
        if not self.record_path.is_file():
            raise Refused('NO_RUN_RECORD', 'run prepare first; --job-dir is <jobs-root>/<case id>')
        self.raw = self.record_path.read_bytes()
        rec = strict_json(self.raw, 'RUN_RECORD.json')
        if rec.get('schema') != RECORD_SCHEMA:
            raise Refused('RUN_RECORD_SCHEMA')
        self.rec = rec
        return rec

    def create(self, rec):
        self.rec, self.raw = rec, dumps(rec)
        write_new(self.record_path, self.raw)

    def stages(self, name=None):
        return [s for s in self.rec['stages'] if name is None or s['stage'] == name]

    def done(self, name):
        return [s for s in self.stages(name) if s['completed']]

    def append(self, entry):
        cur = self.record_path.read_bytes()
        if cur != self.raw:
            raise Refused('RUN_RECORD_CHANGED_ON_DISK', 'the record differs from the one this command read; nothing appended')
        old = strict_json(cur, 'RUN_RECORD.json')
        entry = dict(entry, seq=len(old['stages']) + 1, previous_record_sha256=sha_bytes(cur))
        new = dict(old, stages=old['stages'] + [entry])
        raw = dumps(new)
        if strict_json(raw, 'RUN_RECORD.json')['stages'][:-1] != old['stages']:
            raise Refused('RUN_RECORD_APPEND_ONLY')
        tmp = self.dir / '.RUN_RECORD.json.tmp'
        if tmp.exists():
            tmp.unlink()
        write_new(tmp, raw)
        os.replace(tmp, self.record_path)
        self.rec, self.raw = new, raw

    def release(self):
        """Later stages use the release copy frozen at prepare, so the release cannot change mid-job."""
        raw = self.p('input', 'RELEASE.json').read_bytes()
        if sha_bytes(raw) != self.rec['release']['sha256']:
            raise Refused('RELEASE_COPY_CHANGED')
        return Release(raw, 'input/RELEASE.json')

    def require_not_frozen(self):
        if self.done('freeze') or self.p('FROZEN.json').exists():
            raise Refused('JOB_FROZEN', 'the job folder is frozen; nothing more may run in it')

    def require_not_done(self, *names):
        for n in names:
            if self.done(n):
                raise Refused('STAGE_ALREADY_COMPLETED', {'stage': n, 'result': self.done(n)[-1]['result']})

    def pinned_file(self, rel_path, sha):
        p = self.p(rel_path)
        if not p.is_file() or sha_file(p) != sha:
            raise Refused('JOB_FILE_CHANGED', {'file': rel_path})
        return p


class Stage:
    def __init__(self, job, name, args):
        self.job, self.name, self.started = job, name, utc()
        self.inputs, self.outputs, self.tools, self.steps, self.codes, self.facts = {}, {}, {}, [], [], {}
        self.operator_model = getattr(args, 'operator_model', None)
        self.counter = 0
        self.seq = len(job.rec['stages']) + 1 if job.rec else 1      # unique log names across attempts

    def pin(self, where, label, path):
        p = Path(path)
        where[label] = {'path': self.job.rel(p), 'bytes': p.stat().st_size, 'sha256': sha_file(p)}
        return where[label]['sha256']

    def pin_in(self, label, path):
        return self.pin(self.inputs, label, path)

    def pin_out(self, label, path):
        return self.pin(self.outputs, label, path)

    def run(self, label, script, args, env=None, python_flags=('-I', '-B'), cwd=None, timeout=3600):
        """Run one tool; stdout and stderr go to logs/ (never printed). Returns (exit code, stdout bytes, stderr bytes)."""
        script = Path(script)
        self.tools[self.job.rel(script) if str(script).startswith(str(self.job.dir)) else str(script)] = sha_file(script)
        self.counter += 1
        base = f'{self.seq:02d}_{self.name}_{self.counter:02d}_{label}'
        argv = [sys.executable, *python_flags, str(script), *[str(a) for a in args]]
        try:
            p = subprocess.run(argv, capture_output=True, env=env, cwd=cwd, timeout=timeout)
            code, out, err = p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired as e:
            code, out, err = 'TIMEOUT', e.stdout or b'', e.stderr or b''
        logs = self.job.p('logs')
        write_new(logs / (base + '.stdout'), out)
        write_new(logs / (base + '.stderr'), err)
        self.steps.append({'tool': label, 'script_sha256': sha_file(script), 'exit': code, 'stdout_sha256': sha_bytes(out),
                           'log': 'logs/' + base + '.stdout'})
        return code, out, err

    def entry(self, result, next_step, completed):
        return {'stage': self.name, 'started_utc': self.started, 'ended_utc': utc(), 'completed': completed, 'result': result,
                'next': next_step, 'codes': self.codes, 'inputs': self.inputs, 'outputs': self.outputs, 'tools': self.tools,
                'steps': self.steps, 'facts': self.facts, 'operator_model': self.operator_model,
                'runner': {'version': VERSION, 'sha256': sha_file(__file__)}}


def last_json_line(b):
    for line in reversed(b.decode('utf-8', 'replace').strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def parse_stdout(out):
    """A tool's JSON stdout: the whole text (the route prints indented JSON), else its last JSON line."""
    try:
        d = json.loads(out.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        d = last_json_line(out)
    return d if isinstance(d, dict) else {}


def refusal_code(err):
    d = last_json_line(err)
    return (d or {}).get('code') if isinstance(d, dict) else None


def tool_env(rel, extra=None):
    env = dict(os.environ)
    if rel.node_path is not None:
        env['NODE_PATH'] = str(rel.node_path)
    env.setdefault('LANG', 'C.UTF-8')
    env.update(extra or {})
    return env


def clean_env(rel):
    """Condition 2: saved QA from a clean shell, independent of the producer's environment."""
    env = {'PATH': rel.clean_path, 'HOME': os.environ.get('HOME', '/'), 'LANG': 'C.UTF-8'}
    if os.environ.get('TMPDIR'):
        env['TMPDIR'] = os.environ['TMPDIR']
    return env


# ------------------------------------------------------------------ job inputs
TITLE_PROBE = '''import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('cps_writer_title_probe', sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
try:
    m.deliverable_record(sys.stdin.buffer.read().decode('utf-8'))
    print(json.dumps({'ok': True}))
except m.Refused as e:
    print(json.dumps({'ok': False, 'code': e.code, 'reason': (e.detail or {}).get('reason') if isinstance(e.detail, dict) else None}))
'''


def check_title_with_writer(rel, title):
    """The writer's own O33 naming rule (deliverable_record), run before anything is generated: a title the writer would
    refuse at finish is refused here. The title goes on stdin, never on a command line."""
    w = rel.root / 'research/export/writer_portable.py'
    p = subprocess.run([sys.executable, '-I', '-B', '-c', TITLE_PROBE, str(w)], input=title.encode('utf-8'), capture_output=True, timeout=120)
    d = last_json_line(p.stdout) or {}
    if p.returncode != 0 or d.get('ok') is not True:
        raise Refused('JOB_TITLE_REFUSED_BY_WRITER', {'reason': d.get('reason')})


def job_inputs(job_raw, title_raw, rel, qualification, admission_raw):
    job = strict_json(job_raw, 'JOB.json')
    if not isinstance(job, dict) or job.get('schema') != JOB_SCHEMA:
        raise Refused('JOB_SCHEMA', {'expected': JOB_SCHEMA})
    case = job.get('case_id')
    if not isinstance(case, str) or not CASE_ID_RE.fullmatch(case):        # the route's ID_RE; the case id names the job folder
        raise Refused('JOB_CASE_ID')
    if 'job_title' in job or 'title' in job:
        raise Refused('JOB_TITLE_IN_JOB_JSON', 'the title is not a key of JOB.json (make_job_config.py refuses unknown keys); use --job-title-file')
    src = Path(str(job.get('source_path', '')))
    if not src.is_absolute() or not src.is_file():
        raise Refused('SOURCE_FILE_REQUIRED')
    title = strict_json(title_raw, 'JOB_TITLE.json')
    if not isinstance(title, dict) or set(title) != {'schema', 'case_id', 'job_title'} or title['schema'] != TITLE_SCHEMA:
        raise Refused('JOB_TITLE_FILE_SHAPE', {'expected_keys': ['schema', 'case_id', 'job_title'], 'schema': TITLE_SCHEMA})
    if title['case_id'] != case:
        raise Refused('JOB_TITLE_CASE_ID_MISMATCH')
    t = title['job_title']
    if not isinstance(t, str) or not ''.join(ch for ch in nfkc(t) if not (ch.isspace() or ch == '\ufeff')).startswith(case):
        raise Refused('JOB_TITLE_INVALID', 'the project folder title starts with the case id')
    # company tables: the job must use exactly the released, hash-pinned tables (never edited)
    tables = {}
    for key, tkey in (('glossary_path', 'glossary'), ('brand_table_path', 'brand_table')):
        spec = rel.tables.get(tkey)
        if key not in job:
            continue
        if not isinstance(spec, dict) or not spec.get('path') or not is_sha(spec.get('sha256')):
            raise Refused('TABLE_NOT_RELEASED', {'table': tkey})
        jp = Path(str(job[key]))
        if not jp.is_absolute() or not jp.is_file() or os.path.realpath(jp) != os.path.realpath(rel.path(spec['path'])):
            raise Refused('TABLE_PATH_NOT_RELEASED', {'table': tkey})
        h = sha_file(jp)
        if h != spec['sha256']:
            raise Refused('TABLE_SHA256_MISMATCH', {'table': tkey})
        tables[tkey] = h
    cn_sha = rel.tables.get('company_name_sha256')
    if cn_sha is not None:
        if not isinstance(job.get('company_name'), str) or sha_bytes(job['company_name'].encode('utf-8')) != cn_sha:
            raise Refused('COMPANY_NAME_NOT_RELEASED')
    facts = {'case_id': case, 'source_kind_sha256': sha_bytes(str(job.get('source_kind')).encode('utf-8')),
             'job_json_sha256': sha_bytes(job_raw), 'job_title_sha256': sha_bytes(title_raw), 'source_sha256': sha_file(src),
             'source_bytes': src.stat().st_size, 'source_extension': src.suffix.lower(), 'tables_sha256': tables}
    if qualification:
        if admission_raw is None:
            raise Refused('QUALIFICATION_NEEDS_ADMISSION')
        adm = strict_json(admission_raw, 'admission')
        if not isinstance(adm, dict) or adm.get('schema') != ADMISSION_SCHEMA or not isinstance(adm.get('pins'), dict):
            raise Refused('ADMISSION_SCHEMA', {'expected': ADMISSION_SCHEMA})
        a_sha = sha_bytes(admission_raw)
        if rel.qual_admissions and a_sha not in rel.qual_admissions:
            raise Refused('ADMISSION_NOT_RELEASED')
        try:
            frozen = datetime.datetime.fromisoformat(str(adm.get('frozen_utc')).replace('Z', '+00:00'))
        except ValueError:
            raise Refused('ADMISSION_FROZEN_UTC')
        if frozen.tzinfo is None or frozen >= datetime.datetime.now(datetime.timezone.utc):
            raise Refused('ADMISSION_NOT_FROZEN_BEFORE_PREPARE')
        pinned = {v.get('sha256') for v in adm['pins'].values() if isinstance(v, dict)}
        tpin = adm['pins'].get('job_title_' + case)
        if not isinstance(tpin, dict) or tpin.get('sha256') != facts['job_title_sha256']:
            raise Refused('ADMISSION_JOB_TITLE_PIN', {'label': 'job_title_' + case})
        need = {'package manifest': rel.manifest_sha, 'route': sha_file(rel.route), 'JOB.json': facts['job_json_sha256'],
                'source': facts['source_sha256'], **{'table ' + k: v for k, v in tables.items()}}
        missing = sorted(k for k, v in need.items() if v not in pinned)
        if missing:
            raise Refused('ADMISSION_MISSING_PINS', {'missing': missing})
        facts['admission'] = {'sha256': a_sha, 'frozen_utc': adm['frozen_utc'], 'pins': len(adm['pins']),
                              'checked_pins': sorted(need) + ['job_title_' + case]}
    return job, title, src, facts


def content_cells(inv_bytes):
    inv = json.loads(inv_bytes.decode('utf-8'))
    return sum(1 for c in inv['cells'] if c['state'] in ('literal', 'cached_formula') and c['saved_value'] is not None and c['saved_value'] != '')


def check_inventory(st, rel, inv_path, label, want_scope):
    code, out, _ = st.run(label, rel.route, ['check-inventory', '--inventory', inv_path], env=tool_env(rel))
    d = parse_stdout(out)
    res = {'status': d.get('status'), 'route': d.get('route'), 'policy_checks': d.get('policy_checks'), 'scope': d.get('scope'),
           'violations': sorted({v['code'] for v in d.get('violations', [])}), 'warnings': sorted({w['code'] for w in d.get('warnings', [])})}
    st.facts[label] = res
    if code != 0 or res['status'] != 'PASS' or res['policy_checks'] != 'applied' or res['scope'] != want_scope:
        st.codes += res['violations'] or [str(res['status'])]
        raise Outcome('CHECK_INVENTORY_FAILED', 'STOP_CHECK_INVENTORY_FAILED')
    return res


def prepare_generation(st, job, rel, packet_dir, reader, case):
    run_dir = job.p('run', reader)
    code, out, err = st.run('prepare_run', rel.harness / 'prepare_run.py',
                            ['--package', rel.package, '--packet', packet_dir, '--run', run_dir, '--case', case, '--reader', reader],
                            env=tool_env(rel))
    if code != 0:
        raise Outcome('PREPARE_RUN_FAILED', 'STOP_PREPARE_RUN_FAILED')
    pins = read_json(run_dir / 'RUN_INPUT_PINS.json', 'RUN_INPUT_PINS.json')
    packet_sha = sha_file(Path(packet_dir) / 'SOURCE_INVENTORY.json')
    if pins['package_manifest_sha256'] != rel.manifest_sha or pins['inventory_sha256'] != packet_sha:
        raise Outcome('RUN_INPUTS_NOT_PINNED', 'STOP_RUN_INPUTS_NOT_PINNED')
    tpl = (rel.harness / 'GENERATOR_PROMPT_TEMPLATE.md').read_text(encoding='utf-8')
    st.tools[str(rel.harness / 'GENERATOR_PROMPT_TEMPLATE.md')] = sha_file(rel.harness / 'GENERATOR_PROMPT_TEMPLATE.md')
    prompt = job.p('run', 'GENERATOR_PROMPT.md')
    write_new(prompt, tpl.replace('{RUN}', str(run_dir)))
    st.pin_out('run_input_pins', run_dir / 'RUN_INPUT_PINS.json')
    st.pin_out('generator_prompt', prompt)
    st.facts['generation'] = {'run_dir': job.rel(run_dir), 'reader': reader, 'packet_inventory_sha256': packet_sha,
                              'inputs_pinned': len(pins['inputs']), 'response_path': job.rel(run_dir / 'output' / 'response.json')}
    return f'GENERATE prompt={prompt} folder={run_dir}'


# ------------------------------------------------------------------ prepare
def cmd_prepare(a):
    for k in ('release', 'job', 'job_title_file', 'jobs_root'):
        if not Path(getattr(a, k)).is_absolute():
            raise Refused('ABSOLUTE_PATH_REQUIRED', {'argument': '--' + k.replace('_', '-')})
    if a.qualification and not a.admission:
        raise Refused('QUALIFICATION_NEEDS_ADMISSION')
    if a.admission and not a.qualification:
        raise Refused('ADMISSION_ONLY_WITH_QUALIFICATION')
    if a.reader not in ('A', 'B'):
        raise Refused('READER', 'A or B')
    jobs_root = Path(a.jobs_root).resolve()
    if any(ch.isspace() for ch in str(jobs_root)):
        raise Refused('JOBS_ROOT_WHITESPACE', 'printed paths must not contain whitespace')
    rel_raw = Path(a.release).read_bytes()
    rel = Release(rel_raw, a.release)
    job_raw, title_raw = Path(a.job).read_bytes(), Path(a.job_title_file).read_bytes()
    adm_raw = Path(a.admission).read_bytes() if a.admission else None
    probe = Stage(Job(jobs_root / '_'), 'prepare', a)        # collects facts before the folder exists
    check_release_static(rel, a.qualification, probe)
    export_preflight(rel, probe)                             # fail early: a job never waits on an unadmitted node
    job, title, src, facts = job_inputs(job_raw, title_raw, rel, a.qualification, adm_raw)
    check_title_with_writer(rel, title['job_title'])
    case = facts['case_id']
    jd = Job(jobs_root / case)
    if jd.dir.exists():
        raise Refused('JOB_DIR_EXISTS', 'a job folder is used once; never re-prepare into it')
    for name in ('make_job_config.py', 'scope_tool.py', 'scope_agree.py', 'make_scoped_inventory.py', 'prepare_run.py',
                 'GENERATOR_PROMPT_TEMPLATE.md', 'SCOPE_READER_PROMPT_TEMPLATE.md'):
        if not (rel.harness / name).is_file():
            raise Refused('HARNESS_FILE_MISSING', {'file': name})
    for name in ('build_inventory_xlsx_v2.py', 'build_inventory_v2.py', 'render_views.py', 'screenshot_views.cjs', 'auto_views.py'):
        if not (rel.source_prep / name).is_file():
            raise Refused('SOURCE_PREP_FILE_MISSING', {'file': name})
    if not (rel.deps_bundle / 'private' / 'deps').is_dir():
        raise Refused('DEPS_BUNDLE_MISSING', 'source_prep.deps_bundle must hold private/deps (openpyxl 3.1.5, xlrd 2.0.2)')
    # make_job_config validates the job inputs before the job folder exists (a refusal leaves nothing behind)
    vdir = jobs_root / ('.validate_' + case + '_' + str(os.getpid()))
    jobs_root.mkdir(parents=True, exist_ok=True)
    vdir.mkdir()
    try:
        vjob = vdir / 'JOB.json'
        write_new(vjob, job_raw)
        p = subprocess.run([sys.executable, '-I', '-B', str(rel.harness / 'make_job_config.py'), '--job', str(vjob),
                            '--out', str(vdir / 'BUILDER_CONFIG.json')], capture_output=True, timeout=600, env=tool_env(rel))
        if p.returncode != 0:
            raise Refused('JOB_CONFIG_REFUSED', {'make_job_config_code': refusal_code(p.stderr)})
    finally:
        shutil.rmtree(vdir, ignore_errors=True)
    # the job folder
    jd.dir.mkdir()
    for d in LAYOUT:
        jd.p(d).mkdir()
    write_new(jd.p('input', 'RELEASE.json'), rel_raw)
    write_new(jd.p('input', 'JOB.json'), job_raw)
    write_new(jd.p('input', 'JOB_TITLE.json'), title_raw)
    write_new(jd.p('input', 'source' + facts['source_extension']), src.read_bytes())
    if adm_raw is not None:
        write_new(jd.p('input', 'ADMISSION.json'), adm_raw)
    rec = {'schema': RECORD_SCHEMA, 'runner': {'version': VERSION, 'sha256': sha_file(__file__)}, 'case_id': case,
           'reader': a.reader, 'qualification': bool(a.qualification), 'created_utc': utc(), 'release': rel.summary(),
           'job_inputs': {k: facts[k] for k in ('job_json_sha256', 'job_title_sha256', 'source_sha256', 'source_bytes',
                                                'source_extension', 'source_kind_sha256', 'tables_sha256')},
           'admission': facts.get('admission'), 'user_options': 'none: the runner takes no per-user options',
           'operator_model': a.operator_model, 'stages': []}
    jd.create(rec)
    st = Stage(jd, 'prepare', a)
    st.facts.update(probe.facts)
    st.tools.update(probe.tools)
    for label, rp in (('release', 'RELEASE.json'), ('job_json', 'JOB.json'), ('job_title', 'JOB_TITLE.json'),
                      ('source', 'source' + facts['source_extension'])):
        st.pin_in(label, jd.p('input', rp))
    if adm_raw is not None:
        st.pin_in('admission', jd.p('input', 'ADMISSION.json'))
    return run_stage(jd, st, lambda: prepare_body(st, jd, rel, case, a.reader))


def prepare_body(st, jd, rel, case, reader):
    env = tool_env(rel)
    cfg = jd.p('packet', 'BUILDER_CONFIG.json')
    code, _, _ = st.run('make_job_config', rel.harness / 'make_job_config.py', ['--job', jd.p('input', 'JOB.json'), '--out', cfg], env=env)
    if code != 0:
        raise Outcome('JOB_CONFIG_REFUSED', 'STOP_JOB_CONFIG_REFUSED')
    st.pin_out('builder_config', cfg)
    builder = rel.source_prep / Path(read_json(cfg, 'builder config')['builder']).name
    full = jd.p('packet', 'full')
    code, _, _ = st.run('build_inventory', builder, ['--bundle', rel.deps_bundle, '--config', cfg, '--out', full],
                        env=env, python_flags=('-I', '-S', '-B'))
    if code != 0:
        raise Outcome('INVENTORY_BUILD_FAILED', 'STOP_INVENTORY_BUILD_FAILED')
    code, _, _ = st.run('render_views', rel.source_prep / 'render_views.py', ['--packet', full], env=env)
    st.tools[str(rel.source_prep / 'screenshot_views.cjs')] = sha_file(rel.source_prep / 'screenshot_views.cjs')
    st.tools[str(rel.source_prep / 'auto_views.py')] = sha_file(rel.source_prep / 'auto_views.py')
    if code != 0 or not (full / 'SOURCE_INVENTORY.json').is_file():
        raise Outcome('RENDER_VIEWS_FAILED', 'STOP_RENDER_VIEWS_FAILED')
    inv = full / 'SOURCE_INVENTORY.json'
    st.pin_out('full_inventory', inv)
    st.facts['views'] = len(list(full.glob('view_*.png')))
    check_inventory(st, rel, inv, 'check_inventory_full', 'not_applied')
    count = content_cells(inv.read_bytes())
    st.facts['content_cells_literal_or_cached'] = count
    # scope stage: decided by scope_tool.py exactly as the harness README says (R59: more than 2,500 such cells)
    code, out, _ = st.run('scope_tool', rel.harness / 'scope_tool.py', ['--inventory', inv, '--out-dir', jd.p('scope', 'tool')], env=env)
    if code not in (0, 4):
        raise Outcome('SCOPE_TOOL_REFUSED', 'STOP_SCOPE_TOOL_REFUSED')
    proposal = read_json(jd.p('scope', 'tool', 'SCOPE_PROPOSAL.json'), 'scope proposal')
    st.pin_out('scope_proposal', jd.p('scope', 'tool', 'SCOPE_PROPOSAL.json'))
    status = proposal['status']
    st.facts['scope_tool'] = {'status': status, 'content_cells_literal_or_cached': proposal['content_cells_literal_or_cached'],
                              'threshold': proposal['rule']['threshold'], 'holds': [h['code'] for h in proposal['holds']],
                              'flags': [f['code'] for f in proposal['flags']], 'bill_sheet_index': proposal['bill']['sheet_index'],
                              'end_row': proposal['bill']['end_row']}
    if proposal['content_cells_literal_or_cached'] != count or (status == 'NOT_APPLIED') != (count <= proposal['rule']['threshold']):
        raise Outcome('SCOPE_COUNT_INCONSISTENT', 'STOP_SCOPE_COUNT_INCONSISTENT')
    if status == 'HOLD':
        st.codes += [h['code'] for h in proposal['holds']]
        raise Outcome('SCOPE_TOOL_HOLD', 'OWNER_DECISION')
    if status == 'NOT_APPLIED':
        return 'PREPARED_NOT_SCOPED', prepare_generation(st, jd, rel, full, reader, case)
    # PROPOSED: the scope reader sees exactly the digest and the rules excerpt (read-only) in a new conversation
    sr = jd.p('scope', 'reader')
    (sr / 'input').mkdir(parents=True)
    (sr / 'output').mkdir()
    for name in ('SCOPE_DIGEST.json', 'SCOPE_RULES_EXCERPT.md'):
        b = jd.p('scope', 'tool', name).read_bytes()
        freeze_copy(b, sr / 'input' / name)
        st.pin_out('scope_reader_' + name, sr / 'input' / name)
    tpl_path = rel.harness / 'SCOPE_READER_PROMPT_TEMPLATE.md'
    st.tools[str(tpl_path)] = sha_file(tpl_path)
    prompt = jd.p('scope', 'SCOPE_READER_PROMPT.md')
    write_new(prompt, tpl_path.read_text(encoding='utf-8').replace('{SCOPE_RUN}', str(sr)))
    st.pin_out('scope_reader_prompt', prompt)
    return 'SCOPE_PROPOSED', f'SCOPE_READER prompt={prompt} folder={sr}'


# ------------------------------------------------------------------ scope-finish
def cmd_scope_finish(a):
    jd = Job(a.job_dir)
    jd.load()
    st = Stage(jd, 'scope-finish', a)
    return run_stage(jd, st, lambda: scope_finish_body(st, jd, a), preflight=lambda: scope_finish_pre(st, jd, a))


def scope_finish_pre(st, jd, a):
    jd.require_not_frozen()
    jd.require_not_done('scope-finish')
    prep = jd.done('prepare')
    if not prep or not str(prep[-1]['next']).startswith('SCOPE_READER'):
        raise Refused('SCOPE_STAGE_NOT_OPEN', 'prepare did not end with NEXT: SCOPE_READER')
    rel = jd.release()
    check_release_static(rel, jd.rec['qualification'], st)
    resp = Path(a.reader_response)
    if not resp.is_absolute() or not resp.is_file():
        raise Refused('READER_RESPONSE_REQUIRED', 'an absolute path to the reader JSON')
    expected = jd.p('scope', 'reader', 'output', 'SCOPE_READER_RESPONSE.json')
    if jd.rec['qualification'] and os.path.realpath(resp) != str(expected):
        raise Refused('READER_RESPONSE_PATH', 'qualification: the reader writes scope/reader/output/SCOPE_READER_RESPONSE.json')
    return rel


def scope_finish_body(st, jd, a):
    rel = st.pre
    env = tool_env(rel)
    raw = Path(a.reader_response).read_bytes()          # frozen before any tool reads it
    frozen = jd.p('scope', 'SCOPE_READER_RESPONSE.json')
    freeze_copy(raw, frozen)
    st.inputs['reader_response_original'] = {'path': str(a.reader_response), 'sha256': sha_bytes(raw), 'bytes': len(raw)}
    st.pin_in('reader_response', frozen)
    for name in ('SCOPE_DIGEST.json', 'SCOPE_RULES_EXCERPT.md'):
        if sha_file(jd.p('scope', 'reader', 'input', name)) != sha_file(jd.p('scope', 'tool', name)):
            raise Outcome('SCOPE_READER_INPUT_CHANGED', 'STOP_SCOPE_READER_INPUT_CHANGED')
    dec_dir = jd.p('scope', 'decision')
    code, out, err = st.run('scope_agree', rel.harness / 'scope_agree.py',
                            ['--proposal', jd.p('scope', 'tool', 'SCOPE_PROPOSAL.json'), '--digest', jd.p('scope', 'reader', 'input', 'SCOPE_DIGEST.json'),
                             '--reader', frozen, '--out-dir', dec_dir], env=env)
    if code == 3:
        st.pin_out('scope_hold', dec_dir / 'SCOPE_HOLD.json')
        hold = read_json(dec_dir / 'SCOPE_HOLD.json', 'scope hold')
        st.codes += sorted({d['what'] for d in hold.get('differences', [])})
        raise Outcome('SCOPE_HELD_FOR_OWNER', 'OWNER_DECISION')
    if code != 0:
        st.codes.append(str(refusal_code(err)))
        raise Outcome('SCOPE_READER_RESPONSE_REFUSED', 'STOP_SCOPE_READER_RESPONSE_REFUSED')
    decision = dec_dir / 'SCOPE_DECISION.json'
    st.pin_out('scope_decision', decision)
    dec = read_json(decision, 'scope decision')
    st.facts['scope_decision'] = {'status': dec['status'], 'admissible': dec['admissible'], 'reader': dec['reader'],
                                  'reader_doubts_count': dec['reader_doubts_count'], 'role_differences': len(dec['role_differences'])}
    if dec['admissible'] is not True:
        raise Outcome('SCOPE_DECISION_NOT_ADMISSIBLE', 'STOP_SCOPE_DECISION_NOT_ADMISSIBLE')
    full = jd.p('packet', 'full', 'SOURCE_INVENTORY.json')
    scoped_dir = jd.p('scope', 'scoped_packet')
    code, out, err = st.run('make_scoped_inventory', rel.harness / 'make_scoped_inventory.py',
                            ['--full', full, '--decision', decision, '--out-dir', scoped_dir], env=env)
    if code != 0:
        st.codes.append(str(refusal_code(err)))
        raise Outcome('SCOPED_INVENTORY_REFUSED', 'STOP_SCOPED_INVENTORY_REFUSED')
    receipt = read_json(scoped_dir / 'SCOPED_INVENTORY_RECEIPT.json', 'scoped receipt')
    scoped = scoped_dir / 'SOURCE_INVENTORY.json'
    st.pin_out('scoped_inventory', scoped)
    st.pin_out('scoped_inventory_receipt', scoped_dir / 'SCOPED_INVENTORY_RECEIPT.json')
    if receipt['scoped_inventory_sha256'] != sha_file(scoped) or receipt['full_inventory_sha256'] != sha_file(full):
        raise Outcome('SCOPED_RECEIPT_MISMATCH', 'STOP_SCOPED_RECEIPT_MISMATCH')
    code, out, err = st.run('make_scoped_inventory_verify', rel.harness / 'make_scoped_inventory.py',
                            ['--verify', '--full', full, '--decision', decision, '--scoped', scoped,
                             '--expect-scoped-sha256', receipt['scoped_inventory_sha256']], env=env)
    ver = parse_stdout(out)
    st.facts['scoped_verify'] = {'status': ver.get('status'), 'problem_count': ver.get('problem_count'), 'stats': ver.get('stats')}
    if code != 0 or ver.get('status') != 'PASS':
        raise Outcome('SCOPED_VERIFY_FAILED', 'STOP_SCOPED_VERIFY_FAILED')
    check_inventory(st, rel, scoped, 'check_inventory_scoped', 'applied')
    return 'SCOPE_AGREED', prepare_generation(st, jd, rel, scoped_dir, jd.rec['reader'], jd.rec['case_id'])


# ------------------------------------------------------------------ finish
def cmd_finish(a):
    jd = Job(a.job_dir)
    jd.load()
    st = Stage(jd, 'finish', a)
    return run_stage(jd, st, lambda: finish_body(st, jd, a), preflight=lambda: finish_pre(st, jd, a))


def generation_stage(jd):
    for name in ('scope-finish', 'prepare'):
        d = jd.done(name)
        if d and str(d[-1]['next']).startswith('GENERATE'):
            return d[-1]
    return None


def finish_pre(st, jd, a):
    jd.require_not_frozen()
    jd.require_not_done('freeze_response', 'finish')
    gen = generation_stage(jd)
    if gen is None:
        raise Refused('GENERATION_NOT_PREPARED', 'no stage ended with NEXT: GENERATE')
    rel = jd.release()
    check_release_static(rel, jd.rec['qualification'], st)
    adm, adm_sha, node, tools = export_preflight(rel, st)
    title_rec = jd.pinned_file('input/JOB_TITLE.json', jd.rec['job_inputs']['job_title_sha256'])
    title = read_json(title_rec, 'JOB_TITLE.json')['job_title']
    if a.job_title is not None and a.job_title != title:
        raise Refused('JOB_TITLE_MISMATCH', 'the --job-title given differs from input/JOB_TITLE.json')
    resp = Path(a.response)
    if not resp.is_absolute() or not resp.is_file():
        raise Refused('RESPONSE_REQUIRED', 'an absolute path to the response file')
    expected = jd.p(gen['facts']['generation']['response_path'])
    st.facts['response_from_run_output'] = os.path.realpath(resp) == str(expected)
    if jd.rec['qualification'] and not st.facts['response_from_run_output']:
        raise Refused('RESPONSE_PATH', 'qualification: the response is run/<reader>/output/response.json')
    return {'rel': rel, 'adm': adm, 'adm_sha': adm_sha, 'node': node, 'title': title, 'gen': gen}


def finish_body(st, jd, a):
    pre = st.pre
    rel, adm, node, title, gen = pre['rel'], pre['adm'], pre['node'], pre['title'], pre['gen']
    # 1. freeze the response bytes before anything reads them
    raw = Path(a.response).read_bytes()
    frozen = jd.p('response', 'response.json')
    freeze_copy(raw, frozen)
    fr = Stage(jd, 'freeze_response', a)
    fr.inputs['response_original'] = {'path': str(a.response), 'sha256': sha_bytes(raw), 'bytes': len(raw)}
    fr.pin_out('response', frozen)
    fr.facts = {'generator_model': a.generator_model, 'response_from_run_output': st.facts['response_from_run_output']}
    jd.append(fr.entry('RESPONSE_FROZEN', 'FINISH', True))
    st.pin_in('response', frozen)
    resp_sha = sha_file(frozen)
    st.facts['generator_model'] = a.generator_model
    run_dir = jd.p(gen['facts']['generation']['run_dir'])
    pins = read_json(run_dir / 'RUN_INPUT_PINS.json', 'RUN_INPUT_PINS.json')
    changed = [x['path'] for x in pins['inputs'] if not (run_dir / x['path']).is_file() or sha_file(run_dir / x['path']) != x['sha256']]
    st.facts['run_inputs_unchanged'] = not changed
    if changed:
        raise Outcome('RUN_INPUTS_CHANGED', 'STOP_RUN_INPUTS_CHANGED', [f'{len(changed)} input files changed'])
    inv = run_dir / 'input' / 'packet' / 'SOURCE_INVENTORY.json'
    if sha_file(inv) != gen['facts']['generation']['packet_inventory_sha256']:
        raise Outcome('PACKET_CHANGED', 'STOP_PACKET_CHANGED')
    st.pin_in('packet_inventory', inv)
    want_scope = 'applied' if gen['stage'] == 'scope-finish' else 'not_applied'
    env = tool_env(rel)
    # 2. route check, then convert; a failed check is the outcome (never retried)
    code, out, _ = st.run('route_check', rel.route, ['check', '--inventory', inv, '--response', frozen], env=env)
    write_new(jd.p('response', 'ROUTE_CHECK.json'), out)
    d = parse_stdout(out)
    chk = {'status': d.get('status'), 'route': d.get('route'), 'policy_checks': d.get('policy_checks'), 'scope': d.get('scope'),
           'response_sha256_matches': d.get('response_sha256') == resp_sha,
           'violations': sorted({v['code'] for v in d.get('violations', [])}), 'violation_count': len(d.get('violations', [])),
           'warnings': sorted({w['code'] for w in d.get('warnings', [])})}
    st.facts['route_check'] = chk
    st.pin_out('route_check', jd.p('response', 'ROUTE_CHECK.json'))
    if code != 0 or chk['status'] != 'PASS' or chk['policy_checks'] != 'applied' or chk['scope'] != want_scope or not chk['response_sha256_matches']:
        st.codes += chk['violations'] or [str(chk['status'])]
        raise Outcome('ROUTE_CHECK_FAILED', 'STOP_ROUTE_CHECK_FAILED')
    conv = jd.p('carrier', 'convert')
    code, out, err = st.run('route_convert', rel.route, ['convert', '--inventory', inv, '--response', frozen, '--out-dir', conv], env=env)
    if code != 0 or not (conv / 'carrier.json').is_file():
        st.codes.append(str(parse_stdout(out).get('status')))
        raise Outcome('NOT_CARRIED', 'STOP_NOT_CARRIED')
    carrier = conv / 'carrier.json'
    receipt = read_json(conv / 'ADAPTER_RECEIPT.json', 'adapter receipt')
    carrier_sha = st.pin_out('carrier', carrier)
    st.pin_out('adapter_receipt', conv / 'ADAPTER_RECEIPT.json')
    mode = receipt.get('export_mode_required')
    st.facts['convert'] = {k: receipt.get(k) for k in ('status', 'items', 'components', 'groups', 'nonitems', 'policy_checks', 'scope',
                                                        'export_mode_required', 'writer004_validateCarrier_accepts')}
    st.facts['convert']['relaxation_counts'] = {k: (receipt.get(k) or {}).get('count') for k in
                                                ('o13_m_n_selection_evidence', 'r57_null_c_research_draft', 'o16_q_unverified_adoption')}
    if (receipt.get('carrier_sha256') != carrier_sha or receipt.get('response_sha256') != resp_sha or receipt.get('inventory_sha256') != sha_file(inv)
            or receipt.get('policy_checks') != 'applied' or mode not in ('v1', 'v2')):
        raise Outcome('CONVERT_RECEIPT_MISMATCH', 'STOP_CONVERT_RECEIPT_MISMATCH')
    make_readonly(conv)
    # 3. the admitted writer, in the mode the convert receipt names (condition 6), titled from the pinned title file
    out_dir = jd.p('export', 'writer')
    writer = rel.root / 'research/export/writer_portable.py'
    code, out, err = st.run('writer', writer, ['--carrier', carrier, '--out', out_dir, '--writer-dir', rel.writer_dir, '--mode', mode,
                                               '--job-title=' + title], env=env)
    if code != 0 or not (out_dir / 'WRITER_RECEIPT.json').is_file():
        st.codes.append(str(refusal_code(err)))
        raise Outcome('WRITER_REFUSED', 'STOP_WRITER_REFUSED')
    rraw = (out_dir / 'WRITER_RECEIPT.json').read_bytes()
    st.pin_out('writer_receipt', out_dir / 'WRITER_RECEIPT.json')
    make_readonly(out_dir)
    dup = has_duplicate_keys(rraw)
    wr = json.loads(rraw.decode('utf-8'))
    deliv = wr.get('deliverable') or {}
    dx = wr.get('deliverable_xlsx') or {}
    st.facts['writer'] = {'status': wr.get('status'), 'mode': wr.get('mode'), 'receipt_duplicate_keys': dup,
                          'receipt_job_title_equals_title_file': deliv.get('job_title') == title,
                          'deliverable_xlsx_sha256': dx.get('sha256'), 'internal_xlsx_sha256': (wr.get('output_xlsx') or {}).get('sha256')}
    for label, fname in (('deliverable_xlsx', dx.get('file')), ('internal_xlsx', (wr.get('output_xlsx') or {}).get('file')),
                         ('expected_saved_values', 'EXPECTED_SAVED_VALUES.json')):
        if fname and (out_dir / fname).is_file():
            st.pin_out(label, out_dir / fname)
    ev = Evidence()
    ev.add('5.receipt_no_duplicate_keys', 'WRITER_RECEIPT.json has no duplicate JSON keys (open note N1; checked before saved QA)', not dup, not dup)
    ev.add('6.mode', 'writer --mode equals the convert receipt export_mode_required, with policy_checks applied',
           {'mode': mode, 'receipt_mode': wr.get('mode'), 'policy_checks': receipt.get('policy_checks')},
           wr.get('mode') == mode and receipt.get('policy_checks') == 'applied')
    ev.add('7.job_title', 'the receipt deliverable.job_title equals the pinned per-job title file (input/JOB_TITLE.json)',
           {'title_file_sha256': jd.rec['job_inputs']['job_title_sha256'], 'equal': deliv.get('job_title') == title},
           deliv.get('job_title') == title)
    if dup:
        ev.write(jd, st, pre, None)
        raise Outcome('WRITER_RECEIPT_DUPLICATE_KEYS', 'STOP_WRITER_RECEIPT_DUPLICATE_KEYS')
    # 4. saved QA from a clean environment with the pinned checker node; tool hashes re-checked first (condition 3)
    try:
        tools = check_export_tools(rel, adm)
    except Refused as r:                                    # after the response freeze a refusal is an outcome
        ev.write(jd, st, pre, None)
        raise Outcome('EXPORT_TOOLS_CHANGED', 'STOP_EXPORT_TOOLS_CHANGED', [r.code])
    report = jd.p('qa', 'SAVED_QA.json')
    cenv = clean_env(rel)
    code, out, err = st.run('saved_qa', rel.root / 'research/export/saved_qa.py',
                            ['--output-dir', out_dir, '--report', report, '--carrier', carrier, '--writer-dir', rel.writer_dir,
                             '--checker-node', node['path'], '--checker-node-sha256', node['sha256']], env=cenv)
    st.facts['saved_qa_env_keys'] = sorted(cenv)
    if not report.is_file():
        ev.write(jd, st, pre, None)
        raise Outcome('SAVED_QA_NO_REPORT', 'STOP_SAVED_QA_NO_REPORT')
    report.chmod(RO)
    st.pin_out('saved_qa', report)
    sq = read_json(report, 'SAVED_QA.json')
    saved_conditions(ev, sq, receipt, carrier_sha, node, tools, adm, pre, title, mode, cenv)
    if not ev.grade():
        ev.write(jd, st, pre, sq)
        st.codes += ev.failed()
        raise Outcome('SAVED_QA_NOT_EVIDENCE_GRADE', 'STOP_SAVED_QA_NOT_EVIDENCE_GRADE')
    # 5. visual QA on both workbooks, separately (condition 8)
    vis = {}
    for key, fname, saved_sha in (('deliverable', sq['deliverable_xlsx']['file'], sq['deliverable_xlsx']['sha256']),
                                  ('internal', sq['xlsx']['file'], sq['xlsx']['sha256'])):
        dest = jd.p('qa', 'visual_' + key)
        code, out, err = st.run('visual_qa_' + key, rel.root / 'research/export/visual_qa.py', ['--xlsx', out_dir / fname, '--dest', dest], env=env)
        man_p = dest / 'VISUAL_QA_MANIFEST.json'
        man = read_json(man_p, 'visual manifest') if code == 0 and man_p.is_file() else None
        if man is not None:
            make_readonly(dest)
            st.pin_out('visual_manifest_' + key, man_p)
        sx = (man or {}).get('saved_xlsx') or {}
        ok = man is not None and sx.get('sha256') == saved_sha and sx.get('unchanged_after_render') is True and man.get('complete_render') is True
        ev.add('8.render_' + key, f'visual QA of the {key} workbook: manifest saved_xlsx.sha256 equals SAVED_QA.json '
               + ('deliverable_xlsx.sha256' if key == 'deliverable' else 'xlsx.sha256') + ', unchanged after render, complete render',
               {'exit': code, 'manifest_saved_xlsx_sha256': sx.get('sha256'), 'saved_qa_sha256': saved_sha,
                'complete_render': (man or {}).get('complete_render'), 'pages': (man or {}).get('pages')}, ok)
        vis[key] = (man, man_p)
    if not ev.grade():
        ev.write(jd, st, pre, sq)
        st.codes += ev.failed()
        raise Outcome('VISUAL_QA_RENDER_FAILED', 'STOP_VISUAL_QA_RENDER_FAILED')
    pages = select_pages(jd, vis)
    write_new(jd.p('qa', 'VISUAL_PAGES.json'), dumps(pages))
    st.pin_out('visual_pages', jd.p('qa', 'VISUAL_PAGES.json'))
    ev.add('8.visual_review', 'a separate reviewer checks the selected pages against both checklists (visual-record)', 'pending', None, checkable=False)
    ev.add('9.delivery', 'at delivery: the delivered file is a regular file whose sha256 equals deliverable_xlsx.sha256 (deliver-check)',
           'pending', None, checkable=False)
    ev.write(jd, st, pre, sq)
    prompt = write_review_prompt(jd, pages)
    st.pin_out('visual_review_prompt', prompt)
    st.facts['visual_pages_selected'] = {k: len(v['selected']) for k, v in pages['workbooks'].items()}
    return 'QA_EVIDENCE_GRADE', f'VISUAL_REVIEW prompt={prompt} folder={jd.p("qa")}'


class Evidence:
    def __init__(self):
        self.items = []

    def add(self, cid, text, value, met, checkable=True):
        self.items.append({'id': cid, 'condition': text, 'value': value, 'met': met, 'checkable_here': checkable})

    def grade(self):
        return all(c['met'] is True for c in self.items if c['checkable_here'])

    def failed(self):
        return [c['id'] for c in self.items if c['checkable_here'] and c['met'] is not True]

    def write(self, jd, st, pre, sq):
        doc = {'schema': EVIDENCE_SCHEMA, 'case_id': jd.rec['case_id'], 'written_utc': utc(),
               'writer_admission_sha256': pre['adm_sha'], 'admission_file': str(pre['rel'].writer_admission),
               'evidence_grade': self.grade(), 'failed_conditions': self.failed(),
               'evidence_grade_meaning': ('true only when every condition of ADMISSION_WRITER_V27.json that this machine can check holds; '
                                          'the visual review (condition 8) and the delivery check (condition 9) are recorded later by '
                                          'visual-record and deliver-check'),
               'saved_qa_sha256': sha_file(jd.p('qa', 'SAVED_QA.json')) if sq is not None else None,
               'conditions': sorted(self.items, key=lambda c: (int(c['id'].split('.')[0]), c['id']))}
        p = jd.p('qa', 'QA_EVIDENCE.json')
        write_new(p, dumps(doc))
        st.pin_out('qa_evidence', p)
        st.facts['evidence_grade'] = doc['evidence_grade']


def saved_conditions(ev, sq, receipt, carrier_sha, node, tools, adm, pre, title, mode, cenv):
    ep = sq.get('expected_provenance') or {}
    pc = sq.get('cps_evidence_preconditions') or {}
    cn = ep.get('checker_node') or {}
    fs = adm.get('files_sha256') or {}
    ev.add('1.status', 'saved QA status SAVED_ALL_CELL_VALUE_TYPE_PASS', sq.get('status'), sq.get('status') == SAVED_PASS)
    ev.add('1.provenance', 'expected_provenance.result PASS', ep.get('result'), ep.get('result') == 'PASS')
    ev.add('1.receipt_claims', 'expected_provenance.receipt_claims.match true', (ep.get('receipt_claims') or {}).get('match'),
           (ep.get('receipt_claims') or {}).get('match') is True)
    ev.add('1.all_checked_here_met', 'cps_evidence_preconditions.all_checked_here_met true', pc.get('all_checked_here_met'),
           pc.get('all_checked_here_met') is True)
    ev.add('1.deliverable', 'deliverable_checked and deliverable_byte_identical_to_rerun true (titled output)',
           {'deliverable_checked': pc.get('deliverable_checked'), 'byte_identical': pc.get('deliverable_byte_identical_to_rerun')},
           pc.get('deliverable_checked') is True and pc.get('deliverable_byte_identical_to_rerun') is True)
    ev.add('1.carrier', 'expected_provenance.carrier_sha256 equals ADAPTER_RECEIPT.json carrier_sha256 (the frozen route carrier)',
           {'saved_qa': ep.get('carrier_sha256'), 'adapter_receipt': receipt.get('carrier_sha256'), 'carrier_file': carrier_sha},
           ep.get('carrier_sha256') == receipt.get('carrier_sha256') == carrier_sha)
    ev.add('1.run_options', 'saved QA ran with --carrier and --writer-dir, without --no-formatting',
           {'provenance_checked': pc.get('provenance_checked'), 'formatting_checked': pc.get('formatting_checked')},
           pc.get('provenance_checked') is True and pc.get('formatting_checked') is True)
    ev.add('2.node_admitted', 'the checker node binary sha256 is admitted (release admitted_checker_node_sha256) and declared',
           {'path': node['path'], 'sha256': node['sha256'], 'source': node['source']}, True)
    ev.add('2.node_in_report', 'saved QA ran the pinned checker node: realpath, sha256 and sha256_after_check match; pinned_checker_node true',
           {k: cn.get(k) for k in ('realpath', 'sha256', 'sha256_verified', 'sha256_after_check', 'version')},
           cn.get('pinned') is True and cn.get('sha256_verified') is True and cn.get('realpath') == node['realpath']
           and cn.get('sha256') == node['sha256'] and cn.get('sha256_after_check') == node['sha256'] and pc.get('pinned_checker_node') is True)
    rn, wn = ep.get('rerun_node') or {}, ep.get('writer004_check_node')
    ev.add('2.rerun_node', 'the writer rerun (and the writer004 check, v1 receipts) ran the same checker node file',
           {'rerun_node_realpath': rn.get('realpath'), 'writer004_check_node': wn},
           rn.get('realpath') == node['realpath'] and rn.get('sha256') == node['sha256']
           and (wn is None or (wn.get('realpath') == node['realpath'] and wn.get('sha256') == node['sha256'])))
    ev.add('2.clean_environment', 'saved QA ran in a clean environment set by the runner, not the producer\'s', sorted(cenv), True)
    ev.add('3.tool_hashes', 'saved_qa.py, writer_portable.py, writer004_matrices.mjs and visual_qa.py equal files_sha256 (checked before saved QA)',
           {k: v['match'] for k, v in tools.items() if v['required']}, all(v['match'] for v in tools.values() if v['required']))
    w_sha = fs.get('research/export/writer_portable.py')
    ev.add('3.saved_qa_writer_hash', 'the saved-QA record shows the admitted writer_portable.py hash', ep.get('writer_portable.py_sha256'),
           ep.get('writer_portable.py_sha256') == w_sha)
    m_shown = ep.get('writer004_matrices.mjs_sha256')
    ev.add('3.saved_qa_matrices_hash', 'the saved-QA record shows the admitted writer004_matrices.mjs hash (saved_qa records it only for a '
           'v1 receipt; for a v2 receipt the runner\'s own check above stands)', m_shown,
           (m_shown == fs.get('research/export/writer004_matrices.mjs')) if m_shown is not None else None, checkable=m_shown is not None)
    ev.add('4.openpyxl', 'openpyxl 3.1.5 (saved QA report)', sq.get('openpyxl'), sq.get('openpyxl') == OPENPYXL_VERSION)
    ev.add('4.writer_dir', 'pinned writer files are regular files with admitted hashes; the validation stub is pinned (checked before the run)',
           True, True)
    ev.add('7.title_in_saved_qa', 'cps_evidence_preconditions.job_title equals the pinned per-job title file', pc.get('job_title') == title,
           pc.get('job_title') == title)
    ev.add('10.admission', 'the writer admission record used', {'sha256': pre['adm_sha'],
           'release_pin': pre['rel'].writer_admission_sha}, pre['rel'].writer_admission_sha in (None, pre['adm_sha']))


def page_no(k):
    return int(k)


def select_pages(jd, vis):
    """Condition 8: every page of the delivered workbook; of the internal workbook every page of the main and composition
    sheets, review-sheet pages 1, 2 and the last, every page holding a possibly_clipped_cells cell, and every page whose
    sheet the manifest could not map. The manifest names no page for a clipped cell, so when a clipped cell lies on the
    review sheet (or the list is capped or unavailable) every review-sheet page is selected."""
    out = {'schema': 'cps.visual-pages.v1', 'rule': select_pages.__doc__.strip().replace('\n    ', ' '), 'workbooks': {}}
    for key, (man, man_p) in vis.items():
        imgs = {str(i['page']): str(man_p.parent / i['file']) for i in man['images']}
        mapping = man.get('page_sheet_mapping') or {}
        allp = sorted(imgs, key=page_no)
        main = man.get('main_sheet')
        roles = {}
        for p in allp:
            s = mapping.get(p)
            roles[p] = ('main' if s == main else 'review' if s == REVIEW_SHEET else 'composition' if s in COMPOSITION_SHEETS
                        else 'unmapped' if s is None else 'other')
        clipped = man.get('possibly_clipped_cells') or {}
        cut = man.get('possibly_cut_cells') or {}
        if key == 'deliverable':
            selected, why = allp, 'every page of the delivered workbook'
        else:
            rev = [p for p in allp if roles[p] == 'review']
            sel = {p for p in allp if roles[p] != 'review'}
            sel |= set(rev[:2] + rev[-1:])
            first = clipped.get('first') or []
            on_review = [c for c in first if c.get('sheet') == REVIEW_SHEET]
            unknown = clipped.get('count') is None or (clipped.get('count') or 0) > len(first)
            if on_review or (unknown and rev):
                sel |= set(rev)
            selected = sorted(sel, key=page_no)
            why = ('main, composition and unmapped pages; review pages 1, 2 and the last'
                   + ('; every review page (possibly_clipped_cells on the review sheet, pages not named by the manifest)' if (on_review or (unknown and rev)) else ''))
        roles_label = {p: ('delivered sheet' if key == 'deliverable' else roles[p]) for p in allp}
        review_index = {}
        n = 0
        for p in allp:
            if roles[p] == 'review':
                n += 1
                review_index[p] = n
        out['workbooks'][key] = {
            'manifest': jd.rel(man_p), 'manifest_sha256': sha_file(man_p), 'saved_xlsx_sha256': man['saved_xlsx']['sha256'],
            'pages_total': len(allp), 'selected': [int(p) for p in selected], 'selection': why,
            'pages': {p: {'image': imgs[p], 'role': roles_label[p], 'review_sheet_page': review_index.get(p)} for p in allp},
            'possibly_cut_cells': {'count': cut.get('count'), 'cells': [
                {'sheet_role': ('delivered sheet' if key == 'deliverable' else ('main' if c.get('sheet') == main else c.get('sheet'))),
                 'cell': c.get('cell'), 'kind': c.get('kind'), 'neighbours_filled': c.get('neighbours_filled')} for c in cut.get('first') or []]},
            'possibly_clipped_cells': {'count': clipped.get('count'), 'cells': [
                {'sheet_role': ('main' if c.get('sheet') == main else c.get('sheet')), 'cell': c.get('cell')} for c in clipped.get('first') or []]},
        }
    return out


def write_review_prompt(jd, pages):
    tpl = (HERE / 'VISUAL_REVIEW_PROMPT_TEMPLATE.md').read_text(encoding='utf-8')
    w = pages['workbooks']

    def page_lines(key):
        lines = []
        for p in w[key]['selected']:
            e = w[key]['pages'][str(p)]
            role = e['role'] + (f', its page {e["review_sheet_page"]}' if e['review_sheet_page'] else '')
            lines.append(f'- page {p} ({role}): `{e["image"]}`')
        return '\n'.join(lines)

    def cells(key, which):
        c = w[key][which]
        if not c['cells']:
            return 'none' if c['count'] == 0 else f'count {c["count"]}, none listed'
        return '\n'.join(f'- {x["sheet_role"]} {x["cell"]}' + (f' ({x["kind"]}, neighbours filled: {x["neighbours_filled"]})' if 'kind' in x else '')
                         for x in c['cells']) + (f'\n- (list capped; total {c["count"]})' if (c['count'] or 0) > len(c['cells']) else '')
    out_dir = jd.p('qa', 'visual_review')
    out_dir.mkdir()
    text = (tpl.replace('{OUT}', str(out_dir))
            .replace('{DELIVERED_PAGES}', page_lines('deliverable')).replace('{INTERNAL_PAGES}', page_lines('internal'))
            .replace('{DELIVERED_MANIFEST_SHA256}', w['deliverable']['manifest_sha256'])
            .replace('{INTERNAL_MANIFEST_SHA256}', w['internal']['manifest_sha256'])
            .replace('{CUT_CELLS}', cells('deliverable', 'possibly_cut_cells'))
            .replace('{CLIPPED_CELLS}', cells('internal', 'possibly_clipped_cells')))
    p = jd.p('qa', 'VISUAL_REVIEW_PROMPT.md')
    write_new(p, text)
    return p


# ------------------------------------------------------------------ visual-record
def cmd_visual_record(a):
    jd = Job(a.job_dir)
    jd.load()
    st = Stage(jd, 'visual-record', a)
    return run_stage(jd, st, lambda: visual_record_body(st, jd, a), preflight=lambda: visual_record_pre(st, jd, a))


def finish_entry(jd):
    d = jd.done('finish')
    return d[-1] if d else None


def visual_record_pre(st, jd, a):
    jd.require_not_frozen()
    jd.require_not_done('visual-record')
    fin = finish_entry(jd)
    if fin is None or not str(fin['next']).startswith('VISUAL_REVIEW'):
        raise Refused('VISUAL_REVIEW_NOT_OPEN', 'finish did not end with NEXT: VISUAL_REVIEW')
    p = Path(a.review)
    if not p.is_absolute() or not p.is_file():
        raise Refused('REVIEW_REQUIRED', 'an absolute path to VISUAL_REVIEW.json')
    raw = p.read_bytes()
    st.inputs['review_original'] = {'path': str(p), 'sha256': sha_bytes(raw), 'bytes': len(raw)}
    pages = read_json(jd.pinned_file('qa/VISUAL_PAGES.json', fin['outputs']['visual_pages']['sha256']), 'VISUAL_PAGES.json')
    saved = read_json(jd.pinned_file('qa/SAVED_QA.json', fin['outputs']['saved_qa']['sha256']), 'SAVED_QA.json')
    # each manifest unchanged since finish, and its saved_xlsx.sha256 equal to the matching SAVED_QA.json hash
    for key, want in (('deliverable', saved['deliverable_xlsx']['sha256']), ('internal', saved['xlsx']['sha256'])):
        o = fin['outputs']['visual_manifest_' + key]
        man = read_json(jd.pinned_file(o['path'], o['sha256']), 'visual manifest')
        if man['saved_xlsx']['sha256'] != want:
            raise Refused('MANIFEST_SAVED_XLSX_MISMATCH', {'workbook': key})
    review = strict_json(raw, 'visual review')
    problems, fails = check_review(review, pages)
    reviewer_fail = isinstance(review, dict) and review.get('overall') == 'FAIL'
    if problems and not fails and not reviewer_fail:
        raise Refused('REVIEW_INCOMPLETE', {'problems': problems[:20], 'problem_count': len(problems)})
    return {'raw': raw, 'problems': problems, 'fails': fails, 'review': review, 'pages': pages}


def check_review(review, pages):
    """Every selected page and every checklist item present, results pass/fail/n/a, n/a only where an item does not apply."""
    problems, fails = [], []
    if not isinstance(review, dict) or review.get('schema') != REVIEW_SCHEMA:
        return ['schema'], fails
    rv = review.get('reviewer')
    if not isinstance(rv, dict) or not all(isinstance(rv.get(k), str) and rv.get(k).strip() for k in ('kind', 'model')):
        problems.append('reviewer {kind, model, effort}')
    if review.get('overall') not in ('PASS', 'FAIL'):
        problems.append('overall')
    for key in ('deliverable', 'internal'):
        wb, sel = review.get(key), pages['workbooks'][key]
        if not isinstance(wb, dict) or not isinstance(wb.get('pages'), dict):
            problems.append(f'{key}: pages')
            continue
        if wb.get('manifest_sha256') != sel['manifest_sha256']:
            problems.append(f'{key}: manifest_sha256')
        for pg in wb['pages']:
            if pg not in sel['pages']:
                problems.append(f'{key}: page {pg} is not a rendered page')
        for pg in sel['selected']:
            items = wb['pages'].get(str(pg))
            if not isinstance(items, dict):
                problems.append(f'{key}: page {pg} missing')
                continue
            role = sel['pages'][str(pg)]['role']
            for it in ITEMS:
                e = items.get(it)
                r = e.get('result') if isinstance(e, dict) else None
                if r not in RESULTS:
                    problems.append(f'{key}: page {pg} item {it}')
                    continue
                if r == 'fail':
                    fails.append(f'{key} page {pg} item {it}')
                if r == 'n/a' and not na_allowed(key, role, it):
                    problems.append(f'{key}: page {pg} item {it} n/a not allowed')
            extra = sorted(set(items) - set(ITEMS))
            if extra:
                problems.append(f'{key}: page {pg} unknown items')
    return problems, fails


def na_allowed(key, role, item):
    if key == 'deliverable':
        return item == '8'                                    # no possibly_cut_cells cell on the page
    if item in ('1', '6', '7'):
        return role != 'main'                                 # main-sheet items
    if item == '8':
        return role != 'review'                               # review-sheet JSON text
    return False


def visual_record_body(st, jd, a):
    pre = st.pre
    frozen = jd.p('qa', 'VISUAL_REVIEW.json')
    freeze_copy(pre['raw'], frozen)
    st.pin_in('visual_review', frozen)
    review = pre['review'] if isinstance(pre['review'], dict) else {}
    result = 'FAIL' if (pre['fails'] or review.get('overall') == 'FAIL') else 'PASS'
    inconsistent = (review.get('overall') == 'PASS') != (result == 'PASS')
    rec = {'schema': 'cps.visual-record.v1', 'case_id': jd.rec['case_id'], 'recorded_utc': utc(), 'result': result,
           'review_sha256': sha_bytes(pre['raw']), 'reviewer': review.get('reviewer'), 'reviewer_overall': review.get('overall'),
           'overall_consistent_with_items': not inconsistent, 'failed_items': pre['fails'], 'structural_problems': pre['problems'],
           'pages_reviewed': {k: len((review.get(k) or {}).get('pages') or {}) for k in ('deliverable', 'internal')},
           'pages_selected': {k: len(v['selected']) for k, v in pre['pages']['workbooks'].items()},
           'manifests_match_saved_qa': True}
    write_new(jd.p('qa', 'VISUAL_RECORD.json'), dumps(rec))
    st.pin_out('visual_record', jd.p('qa', 'VISUAL_RECORD.json'))
    st.facts['visual'] = {k: rec[k] for k in ('result', 'pages_reviewed', 'pages_selected', 'overall_consistent_with_items')}
    st.facts['visual']['failed_items'] = len(pre['fails'])
    st.facts['reviewer'] = review.get('reviewer')
    if result != 'PASS':
        st.codes += ['VISUAL_REVIEW_FAIL'] + (['REVIEW_OVERALL_INCONSISTENT'] if inconsistent else [])
        raise Outcome('VISUAL_REVIEW_FAILED', 'STOP_VISUAL_REVIEW_FAILED')
    return 'VISUAL_REVIEW_PASS', ('FREEZE' if jd.rec['qualification'] else 'DELIVER_CHECK')


# ------------------------------------------------------------------ deliver-check
def cmd_deliver_check(a):
    jd = Job(a.job_dir)
    jd.load()
    st = Stage(jd, 'deliver-check', a)
    return run_stage(jd, st, lambda: deliver_body(st, jd), preflight=lambda: deliver_pre(st, jd))


def deliver_pre(st, jd):
    jd.require_not_frozen()
    jd.require_not_done('deliver-check')
    if jd.rec['qualification']:
        raise Refused('DELIVERY_NOT_FOR_QUALIFICATION', 'qualification outputs are frozen, never delivered')
    rel = jd.release()
    if rel.status != 'RELEASED_FOR_USE':
        raise Refused('RELEASE_STATUS', {'status': rel.status, 'required': 'RELEASED_FOR_USE'})
    vr = jd.done('visual-record')
    if not vr or vr[-1]['result'] != 'VISUAL_REVIEW_PASS':
        raise Refused('VISUAL_REVIEW_NOT_PASSED')
    return finish_entry(jd)


def delivery_file_checks(f, want):
    """Condition 9: a regular file (not a symbolic link, one hard link) whose sha256 equals the saved-QA hash."""
    try:
        ls = os.lstat(f)
        regular, link, nlink = stat.S_ISREG(ls.st_mode), stat.S_ISLNK(ls.st_mode), ls.st_nlink
    except FileNotFoundError:
        regular, link, nlink = False, False, None
    got = sha_file(f) if regular else None
    return ({'regular_file': regular, 'not_symlink': not link, 'single_link': nlink == 1, 'sha256_equals_saved_qa': got == want},
            got, nlink)


def deliver_body(st, jd):
    fin = st.pre
    saved = read_json(jd.pinned_file('qa/SAVED_QA.json', fin['outputs']['saved_qa']['sha256']), 'SAVED_QA.json')
    evd = read_json(jd.pinned_file('qa/QA_EVIDENCE.json', fin['outputs']['qa_evidence']['sha256']), 'QA_EVIDENCE.json')
    vr = jd.done('visual-record')[-1]
    vrec = read_json(jd.pinned_file('qa/VISUAL_RECORD.json', vr['outputs']['visual_record']['sha256']), 'VISUAL_RECORD.json')
    want = saved['deliverable_xlsx']['sha256']
    f = jd.p('export', 'writer', saved['deliverable_xlsx']['file'])
    checks, got, nlink = delivery_file_checks(f, want)
    checks.update(saved_qa_evidence_grade=evd.get('evidence_grade') is True, visual_review_pass=vrec.get('result') == 'PASS')
    ok = all(checks.values())
    doc = {'schema': 'cps.delivery-check.v1', 'case_id': jd.rec['case_id'], 'checked_utc': utc(), 'condition': 9,
           'file': str(f), 'sha256': got, 'saved_qa_deliverable_xlsx_sha256': want, 'st_nlink': nlink, 'checks': checks,
           'result': 'DELIVERABLE' if ok else 'DO_NOT_DELIVER'}
    write_new(jd.p('qa', 'DELIVERY_CHECK.json'), dumps(doc))
    st.pin_out('delivery_check', jd.p('qa', 'DELIVERY_CHECK.json'))
    st.facts['delivery'] = {'checks': checks, 'sha256': got}
    if not ok:
        st.codes += [k for k, v in checks.items() if not v]
        raise Outcome('DELIVERY_CHECK_FAILED', 'STOP_DELIVERY_CHECK_FAILED')
    return 'DELIVERABLE', f'DELIVER file={f}'


# ------------------------------------------------------------------ freeze (qualification protocol step 5)
def cmd_freeze(a):
    jd = Job(a.job_dir)
    jd.load()
    st = Stage(jd, 'freeze', a)

    def pre():
        jd.require_not_frozen()
        if not jd.rec['stages']:
            raise Refused('NOTHING_TO_FREEZE')
    return run_stage(jd, st, lambda: freeze_body(st, jd), preflight=pre)


def freeze_body(st, jd):
    last = [s for s in jd.rec['stages'] if s['completed']]
    st.facts['final_stage'] = {'stage': last[-1]['stage'], 'result': last[-1]['result']} if last else None
    st.facts['note'] = 'FROZEN.json lists every file of the job folder with this record entry included; never touch the folder again'
    return 'FROZEN', 'DONE'


def write_frozen(jd):
    files = []
    for p in sorted(jd.dir.rglob('*')):
        if p.is_file() and p.name != 'FROZEN.json':
            files.append({'path': p.relative_to(jd.dir).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha_file(p)})
    doc = {'schema': 'cps.job-frozen.v1', 'case_id': jd.rec['case_id'], 'reader': jd.rec['reader'], 'frozen_utc': utc(),
           'run_record_sha256': sha_file(jd.record_path), 'files': files, 'retry_permitted': False, 'repair_permitted': False}
    write_new(jd.p('FROZEN.json'), dumps(doc))
    make_readonly(jd.dir)
    return sha_file(jd.p('FROZEN.json')), len(files)


# ------------------------------------------------------------------ stage wrapper and CLI
def run_stage(jd, st, body, preflight=None):
    st.pre = None
    try:
        if preflight is not None:
            st.pre = preflight()
        result, nxt = body()
        completed = True
    except Refused as r:
        st.codes.append(r.code)
        if not jd.p('FROZEN.json').exists():                # a frozen folder is never written again
            try:
                jd.append(st.entry('REFUSED', None, False))
            except (Refused, OSError):
                pass
        return refused(r)
    except Outcome as o:
        result, nxt, completed = o.result, o.next_step, True
        st.codes += o.codes
    except Exception as e:                                  # noqa: BLE001 - recorded; the job stops (no retry)
        result, nxt, completed = 'RUNNER_ERROR', 'STOP_RUNNER_ERROR', True
        st.codes.append(type(e).__name__)
    jd.append(st.entry(result, nxt.split(' ')[0], completed))
    extra = {}
    if st.name == 'freeze' and result == 'FROZEN':
        extra['frozen_sha256'], extra['files'] = write_frozen(jd)
    print(json.dumps({'stage': st.name, 'result': result, 'codes': st.codes,
                      'run_record_sha256': sha_file(jd.record_path), **extra, 'values_printed': False}, ensure_ascii=False))
    print('NEXT: ' + nxt)
    return EXIT_CONTINUE if nxt.split(' ')[0] in CONTINUE_STEPS else EXIT_STOP


def refused(r):
    detail = r.detail if isinstance(r.detail, (str, dict, list)) or r.detail is None else str(r.detail)
    print(json.dumps({'status': 'REFUSED', 'code': r.code, 'detail': detail, 'values_printed': False}, ensure_ascii=False))
    print('REFUSED: ' + r.code)
    return EXIT_REFUSED


def main(argv=None):
    ap = argparse.ArgumentParser(description='CPS operator job runner (see RUN_JOB_COMMANDS.md)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('prepare', help='build the packet; scope stage when needed; prepare the generation run')
    p.add_argument('--release', required=True)
    p.add_argument('--job', required=True, help='the private JOB.json (cps.job-config.v2)')
    p.add_argument('--job-title-file', required=True, help='the private JOB_TITLE.json (cps.job-title.v1)')
    p.add_argument('--jobs-root', required=True)
    p.add_argument('--reader', default='A', help='A or B (qualification: run A and run B in separate jobs roots)')
    p.add_argument('--qualification', action='store_true')
    p.add_argument('--admission', help='qualification only: the admission frozen with freeze_admission.py before this prepare')
    p.add_argument('--operator-model')
    p = sub.add_parser('scope-finish', help='agreement of the scope tool and the scope reader; scoped packet; generation run')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--reader-response', required=True)
    p.add_argument('--operator-model')
    p = sub.add_parser('finish', help='freeze the response; route check and convert; export; saved QA; visual QA')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--response', required=True)
    p.add_argument('--job-title', help='optional: must equal input/JOB_TITLE.json (the title always comes from that file)')
    p.add_argument('--generator-model')
    p.add_argument('--operator-model')
    p = sub.add_parser('visual-record', help='record the visual review')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--review', required=True)
    p.add_argument('--operator-model')
    p = sub.add_parser('deliver-check', help='condition 9 at delivery; prints the one file to deliver')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--operator-model')
    p = sub.add_parser('freeze', help='write FROZEN.json and make the job folder read-only (qualification protocol step 5)')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--operator-model')
    a = ap.parse_args(argv)
    if a.cmd != 'prepare' and not Path(a.job_dir).is_absolute():
        return refused(Refused('ABSOLUTE_PATH_REQUIRED', {'argument': '--job-dir'}))
    fn = {'prepare': cmd_prepare, 'scope-finish': cmd_scope_finish, 'finish': cmd_finish, 'visual-record': cmd_visual_record,
          'deliver-check': cmd_deliver_check, 'freeze': cmd_freeze}[a.cmd]
    try:
        return fn(a)
    except Refused as r:                    # refused before a job folder could record it
        return refused(r)


if __name__ == '__main__':
    sys.exit(main())
