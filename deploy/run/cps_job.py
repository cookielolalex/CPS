#!/usr/bin/env python3
"""CPS operator job runner: one CPS job, stage by stage, with one record (deploy/run/cps_job.py).

Python 3 standard library only. Every CPS tool runs as a subprocess with `python3 -I -B -X pycache_prefix=<empty>` (the
interpreter that runs this file; the inventory builder with `-I -S -B`, as the harness README states) and the node on
PATH. Paths are arguments or come from the release file; relative release paths are taken from the repository root. The
runner never prints cell text, job-input values or the job title: it prints hashes, counts, codes, the path of the next
prompt and, at delivery, the path of the one file to deliver. Tool output is kept in the job folder (logs/), never printed.

Subcommands (RUN_JOB_COMMANDS.md has the exact commands and what to do at each NEXT):
  prepare       --release RELEASE.json --job JOB.json --job-title-file JOB_TITLE.json --jobs-root DIR
                [--reader A|B] [--qualification --admission ADMISSION.json] [--operator-model TEXT]
  scope-finish  --job-dir D --reader-response D/scope/reader/output/SCOPE_READER_RESPONSE.json [--reader-conversation-id TEXT]
  finish        --job-dir D --response D/run/<reader>/output/response.json [--job-title TEXT] [--generator-model TEXT]
                [--generation-record D/run/GENERATION_RECORD.json [--transcript FILE]]   (qualification: model and record required)
  visual-record --job-dir D --review D/qa/visual_review/VISUAL_REVIEW.json [--reviewer-conversation-id TEXT]
  deliver-check --job-dir D
  interrupt     --job-dir D --reason TECHNICAL_<CODE> --started-utc T --ended-utc T [--conversation-id TEXT]
                (qualification, protocol rule 3: the scope reader or generator conversation broke before its file; once
                per case and reader: NEXT: STOP_TECHNICAL_INTERRUPTION, then freeze and restart in a new folder, or, after
                an agreed scope, NEXT: GENERATE again in the same folder)
  freeze        --job-dir D            (FROZEN.json; then every file and folder of the job is read-only)
  verify-frozen --job-dir D            (recomputes FROZEN.json; never writes)
  nonattempt    --release RELEASE.json --admission ADMISSION.json --case ID --reader A|B [--jobs-root DIR] [--reason CODE]
                (qualification rule 6: a JOBS.json nonattempt, frozen at once as <jobs-root>/<case id>)

Every subcommand holds an exclusive lock on the job folder itself (flock of the folder; a second command is refused,
JOB_BUSY; the tools a stage runs hold it too) and verifies the hash chain of <job>/RUN_RECORD.json before anything else
(RUN_RECORD_CHAIN_BROKEN). Each subcommand appends one entry (two for finish) and never rewrites earlier entries; a stage
that completed (with any result, a recorded failure or an interruption included) is never run again in the same job
folder. A qualification job is also mirrored, entry by entry, in the qualification ledger the release names (outside
every job folder), which allows one run per case and reader, and one restart after a technical interruption.
Visual QA (writer admission ADMISSION_WRITER_V28.json, admitted; visual_qa v4.5): the delivered workbook is rendered without --dpi,
and the reviewer prompt lists every tile of every delivered page; every page image and tile is re-checked at visual-record.
The last line printed is the next step: NEXT: SCOPE_READER, GENERATE, OWNER_DECISION, VISUAL_REVIEW, DELIVER_CHECK,
FREEZE, DELIVER, DONE or STOP_<reason>.
Exit codes: 0 continue with the NEXT step; 3 the job stopped (NEXT: STOP_<reason> or OWNER_DECISION, recorded);
4 refused (nothing consumed; the record notes the refusal when the job folder exists); 2 usage.
"""
import argparse, atexit, datetime, fcntl, hashlib, json, os, re, shutil, stat, subprocess, sys, tempfile, time, traceback, unicodedata
from pathlib import Path

sys.dont_write_bytecode = True
VERSION = 'cps-job-runner.v4'
HERE = Path(__file__).resolve().parent
RECORD_SCHEMA = 'cps.job-run-record.v2'
RELEASE_SCHEMA = 'cps.release.v1'
JOB_SCHEMA = 'cps.job-config.v2'
TITLE_SCHEMA = 'cps.job-title.v1'
ADMISSION_SCHEMA = 'cps.admission.046b.v1'
WRITER_ADMISSION_SCHEMA = 'cps.writer-admission.v1'
REVIEW_SCHEMA = 'cps.visual-review.v1'
EVIDENCE_SCHEMA = 'cps.job-qa-evidence.v1'
GENERATION_RECORD_SCHEMA = 'cps.generation-record.v1'
LEDGER_SCHEMA = 'cps.qualification-ledger.v1'
JOBS_SCHEMA = 'cps.qualification-jobs.v1'
PACKET_PINS_SCHEMA = 'cps.packet-pins.v1'
FROZEN_SCHEMA = 'cps.job-frozen.v2'
STATUS_FOR_MODE = {True: 'RELEASED_FOR_QUALIFICATION', False: 'RELEASED_FOR_USE'}
CASE_ID_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', re.ASCII)
REASON_RE = re.compile(r'[A-Z][A-Z0-9_]{2,63}', re.ASCII)
TECHNICAL_RE = re.compile(r'TECHNICAL_[A-Z0-9_]{2,54}', re.ASCII)
NONATTEMPT_DEFAULT_REASON = 'NONATTEMPT_SOURCE_UNAVAILABLE'         # protocol rule 6: the status of a nonattempt record
# D3 (owner decision O40, 2026-11-06): the rule every generation record states
O40_DECISION_RECORD = 'research/guideline046_005/DECISIONS_OWNER_O23_O25.md'
O40_RULE = ('O40 2026-11-06 (' + O40_DECISION_RECORD + ', "O40 (2026-11-06): evidence of generator isolation in '
            'qualification"): exported or not_available, both accepted; count reported')
COMMIT_RE = re.compile(r'[0-9a-f]{40}([0-9a-f]{24})?', re.ASCII)
LAYOUT = ('input', 'packet', 'scope', 'run', 'response', 'carrier', 'export', 'qa', 'logs')
CONDITION3_TOOLS = ('research/export/saved_qa.py', 'research/export/writer_portable.py',
                    'research/export/writer004_matrices.mjs', 'research/export/visual_qa.py')
WRITER_FILES = ('writer004.mjs', 'validate_carrier_v4.mjs', 'receipt_bytes.mjs')
# R10: every other file the runner executes or fills as a template; each must be pinned by the release or the admission
RUNNER_FILES = ('deploy/run/cps_job.py', 'deploy/run/VISUAL_REVIEW_PROMPT_TEMPLATE.md')
HARNESS_FILES = ('make_job_config.py', 'scope_tool.py', 'scope_agree.py', 'make_scoped_inventory.py', 'prepare_run.py',
                 'GENERATOR_PROMPT_TEMPLATE.md', 'SCOPE_READER_PROMPT_TEMPLATE.md')
SOURCE_PREP_FILES = ('build_inventory_xlsx_v2.py', 'build_inventory_v2.py', 'render_views.py', 'screenshot_views.cjs', 'auto_views.py')
# R12: evaluation files a qualification admission pins (by repository-relative path), and the jobs list label
EVALUATION_FILES = ('research/evaluation/compare_target050.py', 'research/evaluation/aggregate_qualification050.py')
JOBS_LABEL = 'JOBS.json'
REVIEW_SHEET = '來源與審查'
COMPOSITION_SHEETS = ('組成參考', '組成連結')
ITEMS = tuple(str(i) for i in range(1, 10))
RESULTS = ('pass', 'fail', 'n/a')
REVIEWER_KIND = 'fresh_context_visual_reviewer'
SAVED_PASS = 'SAVED_ALL_CELL_VALUE_TYPE_PASS'
OPENPYXL_VERSION = '3.1.5'
FEATURES = ('memory', 'custom_instructions', 'web', 'connectors', 'file_uploads', 'other_agents')
TRANSCRIPT_STATUSES = ('exported', 'not_available')
EXTERNAL_TOOLS = (('soffice', '--version'), ('pdftoppm', '-v'), ('pdfinfo', '-v'), ('pdftotext', '-v'), ('node', '--version'))
MARKER_NAME = '.STAGE_IN_PROGRESS.json'
# D1: a scope reader or generator response frozen in a job folder (a run that froze one is never restarted)
RESPONSE_WITNESSES = ('scope/SCOPE_READER_RESPONSE.json', 'response/response.json', 'response/GENERATION_RECORD.json')
# E1: a response file the broken conversation wrote (a run whose FROZEN.json lists one is never restarted either)
WRITTEN_RESPONSES = ('scope/reader/output/SCOPE_READER_RESPONSE.json', 'run/A/output/response.json', 'run/B/output/response.json',
                     'interrupted/generator_output/response.json')
# R2: a stage's frozen outputs; one that exists while the stage has no completed entry refuses the stage
STAGE_WITNESSES = {'scope-finish': ('scope/SCOPE_READER_RESPONSE.json', 'scope/decision'),
                   'finish': ('response/response.json', 'response/GENERATION_RECORD.json', 'carrier/convert'),
                   'visual-record': ('qa/VISUAL_REVIEW.json', 'qa/VISUAL_RECORD.json'),
                   'deliver-check': ('qa/DELIVERY_CHECK.json',)}
EXIT_CONTINUE, EXIT_USAGE, EXIT_STOP, EXIT_REFUSED = 0, 2, 3, 4
CONTINUE_STEPS = ('SCOPE_READER', 'GENERATE', 'VISUAL_REVIEW', 'DELIVER_CHECK', 'FREEZE', 'DELIVER', 'DONE')
RO = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
WBITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


# ------------------------------------------------------------------ small helpers
class Refused(Exception):
    """Refused before anything was consumed: recorded as a not-completed attempt, the stage may run again. Raised after
    a stage began consuming (a freeze, a tool run), it becomes a completed recorded stop (run_stage)."""
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


def parse_utc(s):
    if not isinstance(s, str):
        return None
    try:
        t = datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return None
    return t if t.tzinfo is not None else None


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
    b = data if isinstance(data, bytes) else data.encode('utf-8')
    with open(p, 'xb') as f:
        f.write(b)
    if readonly:
        p.chmod(RO)
    return sha_bytes(b)


def freeze_copy(src_bytes, dest):
    write_new(dest, src_bytes)
    if sha_file(dest) != sha_bytes(src_bytes):
        raise Refused('FREEZE_COPY_MISMATCH')
    return sha_bytes(src_bytes)


def make_tree_readonly(root):
    """Remove every write bit, bottom-up: files, then each folder, the root folder last (symbolic links untouched)."""
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        return
    for dp, dns, fns in os.walk(root, topdown=False):
        for n in fns + dns:
            p = os.path.join(dp, n)
            m = os.lstat(p).st_mode
            if stat.S_ISREG(m) or stat.S_ISDIR(m):
                os.chmod(p, stat.S_IMODE(m) & ~WBITS)
    os.chmod(root, stat.S_IMODE(os.lstat(root).st_mode) & ~WBITS)


def tree(root):
    """Every entry under root, never following a symbolic link: {'files': {rel: {bytes, sha256}}, 'dirs': [rel],
    'other': [rel]} (other: symbolic links, devices, sockets). None when root is not a real folder."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        return None
    files, dirs, other = {}, [], []
    for dp, dns, fns in os.walk(root, followlinks=False):
        for n in dns + fns:
            p = Path(dp) / n
            r = p.relative_to(root).as_posix()
            m = os.lstat(p).st_mode
            if stat.S_ISDIR(m):
                dirs.append(r)
            elif stat.S_ISREG(m):
                files[r] = {'bytes': os.lstat(p).st_size, 'sha256': sha_file(p)}
            else:
                other.append(r)
    return {'files': files, 'dirs': sorted(dirs), 'other': sorted(other)}


def tree_shas(root):
    t = tree(root)
    return None if t is None else {k: v['sha256'] for k, v in sorted(t['files'].items())}


def regular(p):
    try:
        return stat.S_ISREG(os.lstat(p).st_mode)
    except FileNotFoundError:
        return False


def inside(p, root):
    try:
        Path(os.path.realpath(p)).relative_to(os.path.realpath(root))
        return True
    except ValueError:
        return False


def safe_path(p):
    """A path for printing: runner-chosen paths are ASCII; any other path (the delivered workbook's name holds the
    title) is printed as a hash."""
    return p if p.isascii() else 'non-ascii-path-sha256:' + sha_bytes(p.encode('utf-8'))[:16]


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


def nonblank(x):
    return isinstance(x, str) and bool(x.strip())


def placeholder(x):
    """DN14: a value copied from a template placeholder such as "<only if your platform shows it>"."""
    return isinstance(x, str) and x.strip().startswith('<')


def attested(x):
    """A non-blank attested value that is not a template placeholder."""
    return nonblank(x) and not placeholder(x)


_NOPYC = []


def nopyc():
    """N10: an empty folder for -X pycache_prefix, so no tool ever reads a cached .pyc next to a pinned source file."""
    if not _NOPYC:
        d = tempfile.mkdtemp(prefix='cps_job_nopyc_')
        _NOPYC.append(d)
        atexit.register(shutil.rmtree, d, True)
    return _NOPYC[0]


def py(*flags):
    return [sys.executable, *flags, '-X', 'pycache_prefix=' + nopyc()]


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
        self.writer_admission_sha = get(d, 'writer', 'admission_sha256', kind=str)      # E2: required in every release
        if not is_sha(self.writer_admission_sha):
            raise Refused('RELEASE_FIELD_TYPE', {'field': 'writer.admission_sha256'})
        self.writer_dir = self.path(get(d, 'writer', 'writer_dir', kind=str))
        self.admitted_nodes = get(d, 'admitted_checker_node_sha256', kind=list)
        self.clean_path = get(d, 'saved_qa_clean_path', required=False, kind=str) or '/usr/bin:/bin'
        self.tables = get(d, 'tables', kind=dict)
        self.pinned = get(d, 'pinned_files_sha256', required=False, kind=dict) or {}
        self.accepts_versions = get(d, 'accepts_jobs_from_release_versions', required=False, kind=list) or []
        q = d.get('qualification') if isinstance(d.get('qualification'), dict) else {}
        adms = q.get('admissions') if isinstance(q.get('admissions'), list) else []
        self.qual_admissions = [(Path(e['path']), e['sha256']) for e in adms if isinstance(e, dict) and isinstance(e.get('path'), str)
                                and Path(e['path']).is_absolute() and is_sha(e.get('sha256'))]
        self.ledger = Path(q['ledger']) if isinstance(q.get('ledger'), str) else None
        self.jobs_file = Path(q['jobs_file']) if isinstance(q.get('jobs_file'), str) else None
        acc = q.get('accepted_transcript_status', list(TRANSCRIPT_STATUSES))
        self.accepted_transcripts = acc if isinstance(acc, list) else None
        self.route = self.package / 'tools' / 'cps046b_route.py'

    def path(self, value):
        p = Path(os.path.expanduser(value))
        return p if p.is_absolute() else self.root / p

    def summary(self):
        return {'sha256': self.sha, 'status': self.status, 'release_version': self.d.get('release_version'),
                'repository_commit': get(self.d, 'repository', 'commit', required=False),
                'package_manifest_sha256': self.manifest_sha}

    def require_qualification_fields(self):
        """R11/R12: a qualification release names the ledger and the jobs list (absolute paths outside every job folder).
        D3 (O40): qualification accepts both transcript statuses, so accepted_transcript_status, when given, lists exactly
        exported and not_available."""
        bad = [k for k, v in (('qualification.ledger', self.ledger), ('qualification.jobs_file', self.jobs_file))
               if v is None or not v.is_absolute()]
        acc = self.accepted_transcripts
        if (acc is None or not all(isinstance(x, str) for x in acc) or len(acc) != len(TRANSCRIPT_STATUSES)
                or set(acc) != set(TRANSCRIPT_STATUSES)):
            bad.append('qualification.accepted_transcript_status')
        if bad:
            raise Refused('QUALIFICATION_RELEASE_FIELDS', {'fields': bad})

    def admission_listed(self, path, raw):
        """R12: the release lists this admission by path and sha256 (qualification.admissions[{path, sha256}])."""
        return path is not None and any(os.path.realpath(p) == os.path.realpath(path) and sha == sha_bytes(raw)
                                        for p, sha in self.qual_admissions)

    def label(self, p):
        """The admission label of a file: its path relative to the repository root (else the absolute path)."""
        try:
            return Path(os.path.realpath(p)).relative_to(os.path.realpath(self.root)).as_posix()
        except ValueError:
            return str(p)


def executed_files(rel):
    """R10: every file the runner executes or fills as a template, besides the package (manifest), the export tools and
    the writer folder (writer admission)."""
    return ([rel.root / f for f in RUNNER_FILES] + [rel.harness / n for n in HARNESS_FILES]
            + [rel.source_prep / n for n in SOURCE_PREP_FILES])


def git(root, *args):
    try:
        p = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.decode('utf-8', 'replace') if p.returncode == 0 else None


def check_repository(root, commit):
    """R10: the release names the commit; repository.root is the top of a git checkout at exactly that commit, with no
    change to any tracked file. A missing commit, a folder git cannot verify and a dirty tracked tree are refused."""
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise Refused('RELEASE_COMMIT_REQUIRED', 'repository.commit: the full commit hash the release was made from')
    top, head = git(root, 'rev-parse', '--show-toplevel'), git(root, 'rev-parse', 'HEAD')
    if top is None or head is None or os.path.realpath(top.strip()) != os.path.realpath(root):
        raise Refused('REPOSITORY_NOT_VERIFIABLE', 'repository.root must be the top folder of a git checkout')
    if head.strip() != commit:
        raise Refused('REPOSITORY_COMMIT_MISMATCH', {'release_commit': commit, 'head': head.strip()})
    dirty = git(root, 'status', '--porcelain', '--untracked-files=no')
    if dirty is None:
        raise Refused('REPOSITORY_NOT_VERIFIABLE', 'git status failed')
    if dirty.strip():
        raise Refused('REPOSITORY_DIRTY', {'changed_tracked_files': len(dirty.strip().splitlines())})
    return {'commit': commit, 'commit_verified_with_git': True, 'tracked_tree_clean': True}


def pycache_entries(dirs):
    """N10: cached bytecode beside pinned sources (a planted .pyc would run code no pin covers)."""
    out = []
    for d in dirs:
        d = Path(d)
        if d.is_dir():
            out += [str(p) for p in d.rglob('*') if (p.name == '__pycache__' and p.is_dir()) or p.suffix in ('.pyc', '.pyo')]
    return sorted(out)


def check_release_static(rel, qualification, st, adm=None):
    """Checks that hold for every subcommand: status, the runner's own checkout, repository commit and clean tree, the
    package (manifest, the folder the harness loads), no cached bytecode, and every executed file pinned (R10)."""
    want = STATUS_FOR_MODE[qualification]
    if rel.status != want:
        raise Refused('RELEASE_STATUS', {'status': rel.status, 'required': want})
    if os.path.realpath(__file__) != os.path.realpath(rel.root / 'deploy/run/cps_job.py'):
        raise Refused('RUNNER_NOT_IN_RELEASED_REPOSITORY', 'run repository.root/deploy/run/cps_job.py of the release')
    st.facts['repository'] = check_repository(rel.root, get(rel.d, 'repository', 'commit', required=False))
    if os.path.realpath(rel.harness.parent / 'package') != os.path.realpath(rel.package):
        raise Refused('HARNESS_PACKAGE_MISMATCH', 'the harness tools load <harness.path>/../package; package.path must be that folder')
    check_package(rel, st)
    pyc = pycache_entries([rel.package, rel.harness, rel.source_prep, rel.root / 'research/export', rel.root / 'deploy/run'])
    if pyc:
        raise Refused('PYCACHE_PRESENT', {'entries': len(pyc), 'first': [safe_path(p) for p in pyc[:5]]})
    bad = []
    for rp, want_sha in sorted(rel.pinned.items()):
        p = rel.path(rp)
        got = sha_file(p) if p.is_file() else None
        st.tools[rp] = got
        if got != want_sha:
            bad.append(rp)
    if bad:
        raise Refused('PINNED_FILE_MISMATCH', {'files': bad})
    pinned_real = {os.path.realpath(rel.path(k)) for k in rel.pinned}
    apins = (adm or {}).get('pins') or {}
    missing, by = [], {}
    for p in executed_files(rel):
        label = rel.label(p)
        got = sha_file(p) if p.is_file() else None
        st.tools[label] = got
        if got is not None and os.path.realpath(p) in pinned_real:
            by[label] = 'release pinned_files_sha256'
            continue
        ap = apins.get(label)
        if adm is not None and got is not None and isinstance(ap, dict) and ap.get('sha256') == got:
            by[label] = 'admission'
            continue
        missing.append(label)
    if missing:
        raise Refused('RELEASE_PINS_INCOMPLETE', {'not_pinned': missing})
    st.facts['executed_files_pinned'] = by


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
    """The writer admission the release names, by its required pin (E2), its schema and its status ADMITTED."""
    if not rel.writer_admission.is_file():
        raise Refused('WRITER_ADMISSION_MISSING')
    raw = rel.writer_admission.read_bytes()
    if sha_bytes(raw) != rel.writer_admission_sha:
        raise Refused('WRITER_ADMISSION_SHA256_MISMATCH')
    adm = strict_json(raw, 'writer admission')
    if adm.get('schema') != WRITER_ADMISSION_SCHEMA:
        raise Refused('WRITER_ADMISSION_SCHEMA')
    if adm.get('status') != 'ADMITTED':        # a provisional admission, or one that records no status, is refused
        raise Refused('WRITER_ADMISSION_NOT_ADMITTED', {'status': adm.get('status')})
    return adm, sha_bytes(raw)


def writer_admission_live(rel, qual_adm=None):
    """E2: re-read the writer admission the release names, as R9 re-reads the live release: at visual-record and
    deliver-check (and finish) it must still say status ADMITTED and have the release's pinned sha256 (in qualification
    also the qualification admission's pin of it), so an admission withdrawn or edited after finish stops the job, with
    nothing consumed."""
    try:
        raw = rel.writer_admission.read_bytes()
        d = strict_json(raw, 'writer admission')
    except (OSError, Refused):
        raise Refused('WRITER_ADMISSION_MISSING', 'the writer admission the release names cannot be read as JSON')
    d = d if isinstance(d, dict) else {}
    facts = {'path': str(rel.writer_admission), 'sha256': sha_bytes(raw), 'release_pin': rel.writer_admission_sha,
             'status': d.get('status') if isinstance(d.get('status'), str) else None}
    if d.get('status') != 'ADMITTED':
        raise Refused('WRITER_ADMISSION_NOT_ADMITTED', {'status': facts['status']})
    if facts['sha256'] != rel.writer_admission_sha:
        raise Refused('WRITER_ADMISSION_SHA256_MISMATCH', 'the writer admission differs from writer.admission_sha256')
    if qual_adm is not None:
        label = rel.label(rel.writer_admission)
        pin = ((qual_adm.get('pins') or {}).get(label) or {}).get('sha256')
        if pin != facts['sha256']:
            raise Refused('ADMISSION_MISSING_PINS', {'mismatched': [label]})
        facts['qualification_admission_pin'] = True
    return facts


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
        reg = p.exists() and stat.S_ISREG(os.lstat(p).st_mode)
        got = sha_file(p) if reg else None
        out[name] = {'sha256': got, 'regular_file': reg, 'match': got in allowed}
        if not reg or got not in allowed:
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


def lxml_version(adm):
    """EN6: the lxml the tools import with this python3 (recorded, with the version the writer admission lists)."""
    p = subprocess.run(py('-I', '-B') + ['-c', 'import lxml; print(lxml.__version__)'], capture_output=True, timeout=120)
    v = p.stdout.decode('ascii', 'replace').strip() if p.returncode == 0 else None
    want = (adm.get('environment') or {}).get('lxml') if isinstance(adm, dict) else None
    return {'version': v or None, 'admission_environment': want, 'matches_admission': v == want if want else None}


def check_openpyxl():
    p = subprocess.run(py('-I', '-B') + ['-c', 'import openpyxl; print(openpyxl.__version__)'], capture_output=True, timeout=120)
    v = p.stdout.decode('ascii', 'replace').strip() if p.returncode == 0 else None
    if v != OPENPYXL_VERSION:
        raise Refused('OPENPYXL_VERSION', {'found': v, 'required': OPENPYXL_VERSION})
    return v


BUNDLE_PROBE = '''import json, sys
sys.path.insert(0, sys.argv[1])
out = {}
for name in ('openpyxl', 'xlrd'):
    try:
        m = __import__(name)
        out[name] = {'version': m.__version__, 'file': m.__file__}
    except Exception:
        out[name] = None
print(json.dumps(out))
'''


def bundle_versions(bundle):
    """N9: the openpyxl and xlrd the builders import from the deps bundle (not the interpreter's own site-packages)."""
    dep = Path(bundle) / 'private' / 'deps'
    p = subprocess.run(py('-I', '-S', '-B') + ['-c', BUNDLE_PROBE, str(dep)], capture_output=True, timeout=120)
    d = last_json_line(p.stdout) if p.returncode == 0 else None
    d = d if isinstance(d, dict) else {}
    out = {}
    for name in ('openpyxl', 'xlrd'):
        m = d.get(name) or {}
        f = m.get('file')
        out[name] = {'version': m.get('version'), 'from_bundle': bool(f) and inside(f, dep)}
    return out


def external_tools():
    """N9: the path and version of each external program the renderers use, as found on PATH (recorded, not pinned)."""
    out = {}
    for name, flag in EXTERNAL_TOOLS:
        w = shutil.which(name)
        rec = {'path': w, 'realpath': os.path.realpath(w) if w else None, 'version': None}
        if w:
            try:
                p = subprocess.run([w, flag], capture_output=True, timeout=60)
                lines = (p.stdout or p.stderr).decode('utf-8', 'replace').strip().splitlines()
                rec['version'] = lines[0][:200] if lines else None
            except (OSError, subprocess.SubprocessError):
                pass
        out[name] = rec
    return out


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
    st.facts['lxml'] = lxml_version(adm)                     # EN6: recorded with openpyxl (V28 environment), not enforced
    st.facts['external_tools'] = external_tools()
    st.facts['python'] = {'executable': sys.executable, 'realpath': os.path.realpath(sys.executable),
                          'version': sys.version.split()[0], 'implementation': sys.implementation.name}       # DN9
    st.facts['tool_env_names'] = sorted(tool_env(rel))     # DN9, N9: the names (never the values) of the tool environment
    return adm, adm_sha, node, tools


def check_live_release(jd):
    """R9: the live release file named at prepare still releases this job: same status and the same file, or a release
    that names this job's release_version in accepts_jobs_from_release_versions."""
    want = STATUS_FOR_MODE[jd.rec['qualification']]
    p = jd.rec['release'].get('path')
    try:
        raw = Path(p).read_bytes()
        d = strict_json(raw, 'live release')
    except (OSError, TypeError, Refused):
        raise Refused('RELEASE_NOT_LIVE', {'reason': 'the live release file named at prepare cannot be read as JSON'})
    d = d if isinstance(d, dict) else {}
    same = sha_bytes(raw) == jd.rec['release']['sha256']
    acc = d.get('accepts_jobs_from_release_versions')
    version = jd.rec['release'].get('release_version')
    accepted = isinstance(acc, list) and version is not None and version in acc
    if d.get('status') != want or not (same or accepted):
        raise Refused('RELEASE_NOT_LIVE', {'status': d.get('status'), 'required': want, 'same_release_file': same,
                                           'this_release_version_accepted': accepted})
    return {'path': p, 'sha256': sha_bytes(raw), 'status': d.get('status'), 'same_release_file': same,
            'this_release_version_accepted': accepted}


# ------------------------------------------------------------------ qualification ledger (R11)
def ledger_line(e):
    return (json.dumps(e, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def self_sha(e, dump):
    """The sha256 of an entry without its own entry_sha256 key, so a later edit of the last entry is caught too."""
    return sha_bytes(dump({k: v for k, v in e.items() if k != 'entry_sha256'}))


class Ledger:
    """The qualification ledger (R11): one JSON object per line, each with seq and the sha256 of every byte before it,
    appended only, at the path the release names, outside every job folder. Held under an exclusive lock while open.
    DN6: only prepare and nonattempt (create=True) may create it; every other command refuses a missing ledger
    (QUALIFICATION_LEDGER_MISSING), and verify-frozen opens it read-only (readonly=True, a shared lock)."""
    def __init__(self, path, create=True, readonly=False):
        self.path = Path(path)
        self.create, self.readonly = create and not readonly, readonly
        self.fd, self.entries, self.raw = None, [], b''

    def __enter__(self):
        if not self.path.is_absolute() or not self.path.parent.is_dir():
            raise Refused('QUALIFICATION_LEDGER_PATH', 'an absolute path in an existing folder')
        flags = os.O_RDONLY if self.readonly else os.O_RDWR | os.O_APPEND
        try:
            self.fd = os.open(self.path, flags | (os.O_CREAT if self.create else 0), 0o644)
        except FileNotFoundError:
            raise Refused('QUALIFICATION_LEDGER_MISSING', 'the qualification ledger the release names does not exist; '
                          'never move, rename or delete it: tell the owner')
        except OSError as e:
            raise Refused('QUALIFICATION_LEDGER_UNAVAILABLE', {'errno': e.errno})
        deadline = time.time() + 60
        while True:
            try:
                fcntl.flock(self.fd, (fcntl.LOCK_SH if self.readonly else fcntl.LOCK_EX) | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > deadline:
                    os.close(self.fd)
                    raise Refused('QUALIFICATION_LEDGER_BUSY')
                time.sleep(0.1)
        with open(self.path, 'rb') as f:
            self.raw = f.read()
        problem = self.chain_problem()
        if problem:
            self.__exit__()
            raise Refused('QUALIFICATION_LEDGER_CHAIN_BROKEN', {'problem': problem})
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None
        return False

    def chain_problem(self):
        self.entries = []
        if self.raw and not self.raw.endswith(b'\n'):
            return 'the last line is incomplete'
        off = 0
        for i, line in enumerate(self.raw.split(b'\n')[:-1]):
            try:
                e = strict_json(line, 'ledger')
            except Refused:
                return f'line {i + 1} is not strict JSON'
            if (not isinstance(e, dict) or e.get('ledger') != LEDGER_SCHEMA or e.get('seq') != i + 1
                    or e.get('previous_ledger_sha256') != sha_bytes(self.raw[:off]) or ledger_line(e) != line + b'\n'
                    or e.get('entry_sha256') != self_sha(e, ledger_line)):
                return f'line {i + 1} breaks the chain'
            self.entries.append(e)
            off += len(line) + 1
        return None

    def append(self, entry):
        if self.readonly:
            raise Refused('QUALIFICATION_LEDGER_READ_ONLY')
        e = dict(entry, ledger=LEDGER_SCHEMA, seq=len(self.entries) + 1, previous_ledger_sha256=sha_bytes(self.raw), utc=utc())
        e['entry_sha256'] = self_sha(e, ledger_line)
        b = ledger_line(e)
        n = os.write(self.fd, b)
        if n != len(b):
            raise Refused('QUALIFICATION_LEDGER_WRITE_SHORT')
        os.fsync(self.fd)
        self.raw += b
        self.entries.append(e)
        return e

    def of(self, kind, **match):
        return [e for e in self.entries if e.get('type') == kind and all(e.get(k) == v for k, v in match.items())]


def ledger_record_entry(jd, s, record_sha=None):
    return {'type': 'record', 'job_dir': str(jd.dir), 'case_id': jd.rec['case_id'], 'reader': jd.rec['reader'], 'seq': s['seq'],
            'stage': s['stage'], 'result': s['result'], 'next': s['next'], 'completed': s['completed'],
            'run_record_sha256': record_sha or sha_bytes(jd.raw)}


def ledger_check_record(led, jd, catch_up=True):
    """The record must be the one the ledger last recorded for this folder (a truncated, edited or replaced record is
    refused). DN5: a record whose verified chain extends the last recorded record (the ledger writes after it failed) is
    caught up, one ledger entry per missing record entry, each with the sha256 of the record after that entry. The folder's
    first ledger entry is its prepare, or its nonattempt (D2)."""
    key = str(jd.dir)
    prep = led.of('prepare', job_dir=key) + led.of('nonattempt', job_dir=key)
    if len(prep) != 1:
        raise Refused('QUALIFICATION_JOB_NOT_IN_LEDGER', 'the ledger has no prepare entry for this job folder')
    known = [prep[0]['run_record_sha256']] + [e['run_record_sha256'] for e in led.of('record', job_dir=key)]
    if sha_bytes(jd.raw) == known[-1]:
        return
    st = jd.rec['stages']
    start = next((i for i, s in enumerate(st) if s.get('previous_record_sha256') == known[-1]), None)
    if start is None or not catch_up:
        raise Refused('RUN_RECORD_NOT_IN_LEDGER', 'the record differs from the last one the qualification ledger recorded')
    for i in range(start, len(st)):             # the chain was verified at load: these are the record's exact earlier bytes
        led.append(ledger_record_entry(jd, st[i], sha_bytes(dumps(dict(jd.rec, stages=st[:i + 1])))))


def ledger_admission_order(led, adm):
    """R12: the admission was frozen before the ledger's first entry."""
    if led.entries:
        first, frozen = parse_utc(led.entries[0].get('utc')), parse_utc(adm.get('frozen_utc'))
        if first is None or frozen is None or frozen >= first:
            raise Refused('ADMISSION_FROZEN_AFTER_FIRST_PREPARE', 'the admission must be frozen before the first qualification prepare')


def in_place_restart_used(led, job_dir):
    """Rule 3 limit: the ledger records an in-place restart (an interrupt that printed NEXT: GENERATE) of this folder."""
    return any(e.get('stage') == 'interrupt' and e.get('completed') and e.get('next') == 'GENERATE'
               for e in led.of('record', job_dir=job_dir))


def restart_problem(led, prev):
    """D1 (protocol rule 3): why the frozen run in folder prev may not be restarted, or None. A run may be restarted when it
    froze no scope reader or generator response (no freeze_response entry in the ledger; none of RESPONSE_WITNESSES in
    its FROZEN.json, whose sha256 is the ledger's freeze entry) and its last completed stage before freeze ended in a
    stop: a recorded technical interruption (NEXT: STOP_TECHNICAL_INTERRUPTION), an INTERRUPTED stage, or a technical
    STOP_ reached before any response. E1: a FROZEN.json that lists a written response file (WRITTEN_RESPONSES) is not
    restartable either."""
    fz = led.of('freeze', job_dir=prev)
    if not fz:
        return 'the earlier run is not frozen'
    recs = led.of('record', job_dir=prev)
    if in_place_restart_used(led, prev):
        return 'the earlier run already used its one technical restart in place'
    if any(e.get('stage') == 'freeze_response' for e in recs):
        return 'the earlier run froze a generator response'
    done = [(e['stage'], e['next']) for e in recs if e['completed'] and e['stage'] != 'freeze']
    if not done or not str(done[-1][1]).startswith('STOP_'):
        return ('the earlier run did not end in a recorded technical interruption, an interrupted stage or a technical stop '
                'before any response (a run frozen at NEXT: GENERATE or SCOPE_READER without interrupt is a failed run)')
    try:
        raw = (Path(prev) / 'FROZEN.json').read_bytes()
        listed = {f.get('path') for f in strict_json(raw, 'FROZEN.json').get('files') or [] if isinstance(f, dict)}
    except (OSError, Refused, AttributeError):
        return "the earlier folder's FROZEN.json cannot be read"
    if sha_bytes(raw) != fz[-1].get('frozen_sha256'):
        return "the earlier folder's FROZEN.json is not the one the ledger recorded"
    if listed & set(RESPONSE_WITNESSES):
        return 'the earlier run froze a scope reader or generator response'
    if listed & set(WRITTEN_RESPONSES):                      # E1: written, even if never submitted
        return 'the earlier run\'s conversation wrote its response file (rule 3 restarts only before the response is written)'
    return None


def ledger_admit_prepare(led, jobs, case, reader, job_dir, adm):
    """R11 at prepare --qualification: a JOBS.json case, no recorded nonattempt, the admission frozen before the first
    prepare of the ledger, one run per case and reader, a restart once and only after a technical interruption or stop
    before any reader or generator response (D1, restart_problem), and reader B only after reader A of the case is frozen
    and, DN7, only once A's one restart is used or A cannot be restarted."""
    c = jobs.get(case)
    if c is None:
        raise Refused('QUALIFICATION_CASE_NOT_IN_JOBS', 'the case is not listed in the pinned JOBS.json')
    if c.get('nonattempt'):
        raise Refused('QUALIFICATION_CASE_IS_NONATTEMPT', 'JOBS.json marks the case as a nonattempt')
    if led.of('nonattempt', case_id=case, reader=reader):
        raise Refused('QUALIFICATION_NONATTEMPT_RECORDED', 'the ledger records a nonattempt for this case and reader')
    ledger_admission_order(led, adm)
    if any(e.get('job_dir') == job_dir for e in led.entries):
        raise Refused('QUALIFICATION_JOB_DIR_REUSED')
    mine = led.of('prepare', case_id=case, reader=reader)
    restart_of = None
    if mine:
        if len(mine) > 1:
            raise Refused('QUALIFICATION_RESTART_USED', 'this case and reader were already restarted once')
        prev = mine[0]['job_dir']
        if not led.of('freeze', job_dir=prev):
            raise Refused('QUALIFICATION_RUN_EXISTS', 'this case and reader already have a run that is not frozen')
        if in_place_restart_used(led, prev):
            raise Refused('QUALIFICATION_RESTART_USED', 'this case and reader were already restarted once, in place')
        why = restart_problem(led, prev)
        if why:
            raise Refused('QUALIFICATION_RESTART_NOT_ALLOWED', 'a restart is allowed once, only after a recorded technical '
                          'interruption or a technical stop before any scope reader or generator response: ' + why)
        if reader == 'A' and led.of('prepare', case_id=case, reader='B'):
            raise Refused('QUALIFICATION_RESTART_NOT_ALLOWED', 'run B of this case has started')
        restart_of = prev
    if reader == 'B':
        a = led.of('prepare', case_id=case, reader='A')
        if not a or not led.of('freeze', job_dir=a[-1]['job_dir']):
            raise Refused('QUALIFICATION_READER_A_NOT_FROZEN', 'run B starts only after run A of the case is frozen')
        if len(a) == 1 and restart_problem(led, a[0]['job_dir']) is None:
            raise Refused('QUALIFICATION_READER_A_RESTART_UNUSED', 'run A of this case ended in a technical interruption or '
                          'stop whose one restart is unused: restart run A first (protocol rule 1: run A in full before run B)')
    return restart_of


def load_jobs(rel, adm):
    """The pinned qualification jobs list (cps.qualification-jobs.v1): cases[{case_id, order, nonattempt[, reason]}].
    Returns (cases by id, sha256, raw bytes). A reason, when given, is an upper-case code (D2)."""
    if rel.jobs_file is None or not rel.jobs_file.is_file():
        raise Refused('QUALIFICATION_JOBS_FILE_MISSING')
    raw = rel.jobs_file.read_bytes()
    pin = (adm.get('pins') or {}).get(JOBS_LABEL)
    if not isinstance(pin, dict) or pin.get('sha256') != sha_bytes(raw):
        raise Refused('ADMISSION_MISSING_PINS', {'mismatched': [JOBS_LABEL]})
    d = strict_json(raw, 'JOBS.json')
    if not isinstance(d, dict) or d.get('schema') != JOBS_SCHEMA or not isinstance(d.get('cases'), list):
        raise Refused('QUALIFICATION_JOBS_SCHEMA', {'expected': JOBS_SCHEMA})
    out = {}
    for c in d['cases']:
        if (not isinstance(c, dict) or not isinstance(c.get('case_id'), str) or not CASE_ID_RE.fullmatch(c['case_id'])
                or c['case_id'] in out or not isinstance(c.get('nonattempt', False), bool)
                or ('reason' in c and not (isinstance(c['reason'], str) and REASON_RE.fullmatch(c['reason'])))):
            raise Refused('QUALIFICATION_JOBS_SCHEMA', 'each case: {case_id, order, nonattempt[, reason]}, case ids unique, '
                          'a reason an upper-case code')
        out[c['case_id']] = c
    return out, sha_bytes(raw), raw


# ------------------------------------------------------------------ job folder and record
def chain_problem(rec, raw):
    """R2: the bytes are the runner's own serialization, seq runs 1..n, entry i chains to the exact bytes of the record
    with entries 1..i-1 (the header included), and each entry carries the sha256 of its own content (entry_sha256)."""
    stages = rec.get('stages')
    if not isinstance(stages, list):
        return 'no stages list'
    if raw != dumps(rec):
        return 'the bytes are not the runner serialization'
    for i, s in enumerate(stages):
        if not isinstance(s, dict) or s.get('seq') != i + 1:
            return f'entry {i + 1}: seq'
        if s.get('previous_record_sha256') != sha_bytes(dumps(dict(rec, stages=stages[:i]))):
            return f'entry {i + 1}: previous_record_sha256'
        if s.get('entry_sha256') != self_sha(s, dumps):
            return f'entry {i + 1}: entry_sha256'
    return None


class Job:
    def __init__(self, d):
        self.dir = Path(d).resolve()
        self.record_path = self.dir / 'RUN_RECORD.json'
        self.rec, self.raw, self.lock_fd, self.ledger_path, self.ledger_error = None, None, None, None, None

    def p(self, *parts):
        return self.dir.joinpath(*parts)

    def rel(self, p):
        p = Path(p)
        try:
            return p.resolve().relative_to(self.dir).as_posix()
        except ValueError:
            return str(p)

    def lock(self, wait=False):
        """R4: one exclusive lock per job folder, held until this command and every tool it started have exited. DN3: the
        lock is a flock of the job folder itself (no lock file that could be deleted); DN4: Stage.run passes the locked
        descriptor to each tool, so a tool that outlives a killed runner keeps the folder locked."""
        if not self.dir.is_dir() or self.dir.is_symlink():
            raise Refused('NO_RUN_RECORD', 'run prepare first; --job-dir is <jobs-root>/<case id>')
        try:
            fd = os.open(self.dir, os.O_RDONLY | os.O_DIRECTORY)
        except OSError as e:
            raise Refused('JOB_LOCK_UNAVAILABLE', {'errno': e.errno})
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            os.close(fd)
            raise Refused('JOB_BUSY', 'another cps_job.py command, or a tool it started, is running in this job folder: wait '
                          'until it ends; never re-issue it')
        self.lock_fd = fd

    def load(self, readonly=False):
        """The verified record; in qualification also checked against the ledger (readonly: verify-frozen, which opens
        the ledger read-only and never catches it up)."""
        if not self.record_path.is_file():
            raise Refused('NO_RUN_RECORD', 'run prepare first; --job-dir is <jobs-root>/<case id>')
        raw = self.record_path.read_bytes()
        try:
            rec = strict_json(raw, 'RUN_RECORD.json')
        except Refused:
            raise Refused('RUN_RECORD_CHAIN_BROKEN', {'problem': 'not strict JSON'})
        if not isinstance(rec, dict) or rec.get('schema') != RECORD_SCHEMA:
            raise Refused('RUN_RECORD_SCHEMA', {'expected': RECORD_SCHEMA})
        problem = chain_problem(rec, raw)
        if problem:
            raise Refused('RUN_RECORD_CHAIN_BROKEN', {'problem': problem})
        self.rec, self.raw = rec, raw
        if rec.get('qualification'):
            rel = self.release()
            if rel.ledger is None:
                raise Refused('QUALIFICATION_RELEASE_FIELDS', {'fields': ['qualification.ledger']})
            self.ledger_path = rel.ledger
            with Ledger(self.ledger_path, create=False, readonly=readonly) as led:
                ledger_check_record(led, self, catch_up=not readonly)
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
        entry['entry_sha256'] = self_sha(entry, dumps)
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
        if self.ledger_path is not None:
            try:
                with Ledger(self.ledger_path, create=False) as led:
                    led.append(ledger_record_entry(self, entry))
            except (Refused, OSError) as e:                 # the next command catches the ledger up, or refuses
                self.ledger_error = getattr(e, 'code', type(e).__name__)

    def release(self):
        """Later stages use the release copy frozen at prepare, so the release cannot change mid-job (the live file is
        checked separately, check_live_release)."""
        raw = self.p('input', 'RELEASE.json').read_bytes()
        if sha_bytes(raw) != self.rec['release']['sha256']:
            raise Refused('RELEASE_COPY_CHANGED')
        return Release(raw, 'input/RELEASE.json')

    def admission(self):
        if not self.rec['qualification']:
            return None
        raw = self.p('input', 'ADMISSION.json').read_bytes()
        if sha_bytes(raw) != (self.rec.get('admission') or {}).get('sha256'):
            raise Refused('ADMISSION_COPY_CHANGED')
        return strict_json(raw, 'admission')

    def frozen(self):
        return bool(self.done('freeze')) or self.p('FROZEN.json').exists()

    def require_not_frozen(self, reapply_modes=False):
        if self.frozen():
            detail = {'note': 'the job folder is frozen; nothing more may run in it'}
            if self.p('FROZEN.json').is_file():
                v = verify_frozen(self)
                detail.update(frozen_folder_intact=v['intact'], unlisted=len(v['unlisted']), changed=len(v['changed']),
                              missing=len(v['missing']))
                if reapply_modes and v['intact']:
                    make_tree_readonly(self.dir)
            raise Refused('JOB_FROZEN', detail)

    def require_stage_open(self, name, also=()):
        for n in (name,) + tuple(also):
            if self.done(n):
                raise Refused('STAGE_ALREADY_COMPLETED', {'stage': n, 'result': self.done(n)[-1]['result']})
        for w in STAGE_WITNESSES.get(name, ()):
            if os.path.lexists(self.p(w)):
                raise Refused('STAGE_OUTPUT_EXISTS', {'stage': name, 'path': w, 'note': 'a frozen output of this stage exists '
                              'without its completing record entry; tell the owner'})

    def pinned_file(self, rel_path, sha):
        p = self.p(rel_path)
        if not regular(p) or sha_file(p) != sha:
            raise Refused('JOB_FILE_CHANGED', {'file': safe_path(rel_path)})
        return p

    def mark(self, st):
        """R4: the stage starts consuming. The marker is removed once the stage's entry is appended; a marker found by a
        later command means the stage was interrupted (reconcile)."""
        p = self.p(MARKER_NAME)
        if os.path.lexists(p):
            p.unlink()
        write_new(p, dumps({'stage': st.name, 'started_utc': st.started, 'seq_base': len(self.rec['stages']), 'pid': os.getpid()}),
                  readonly=False)

    def unmark(self):
        try:
            self.p(MARKER_NAME).unlink()
        except FileNotFoundError:
            pass


def open_job(job_dir):
    """Every subcommand on an existing job: the lock, the verified record (and ledger), then any interruption recorded."""
    jd = Job(job_dir)
    jd.lock()
    jd.load()
    if not jd.frozen():
        reconcile(jd)
    return jd


def reconcile(jd):
    """R4: a stage that began consuming and left no entry (a marker without the stage's entry, a freeze_response
    without a finish entry, a record without any prepare entry) is recorded as INTERRUPTED (completed, never run again)."""
    marker, m = jd.p(MARKER_NAME), None
    if os.path.lexists(marker):
        try:
            m = strict_json(marker.read_bytes(), 'marker')
        except (Refused, OSError):
            m = {}
        m = m if isinstance(m, dict) else {}
        base = m.get('seq_base') if isinstance(m.get('seq_base'), int) else 0
        if any(s['stage'] == m.get('stage') and s['completed'] for s in jd.rec['stages'][base:]):
            jd.unmark()                                     # the stage's own entry was appended: a stale marker
            return
    stage, how = None, None
    if m is not None:
        stage, how = str(m.get('stage') or 'unknown'), 'stage marker'
    elif not jd.rec['stages']:
        stage, how = ('nonattempt' if jd.rec.get('nonattempt') else 'prepare'), 'record without any entry'
    else:
        fr = jd.done('freeze_response')
        if fr and not [s for s in jd.stages('finish') if s['seq'] > fr[-1]['seq']]:
            stage, how = 'finish', 'freeze_response without a finish entry'
    if stage is None:
        return
    st = Stage(jd, stage, None)
    st.started = (m or {}).get('started_utc') or st.started
    st.codes = ['STAGE_INTERRUPTED']
    st.facts = {'interrupted': {'detected_by': how, 'marker': m}}
    jd.append(st.entry('INTERRUPTED', 'STOP_INTERRUPTED', True))
    jd.unmark()


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
        """Run one tool; stdout and stderr go to logs/ (never printed). Returns (exit code, stdout bytes, stderr bytes).
        DN4: the tool inherits the job lock's descriptor, so the folder stays locked while the tool runs, even when this
        runner is killed (a later command is refused JOB_BUSY until the tool has ended)."""
        script = Path(script)
        self.tools[self.job.rel(script) if str(script).startswith(str(self.job.dir)) else str(script)] = sha_file(script)
        self.counter += 1
        base = f'{self.seq:02d}_{self.name}_{self.counter:02d}_{label}'
        argv = py(*python_flags) + [str(script), *[str(a) for a in args]]
        keep = (self.job.lock_fd,) if self.job.lock_fd is not None else ()
        try:
            p = subprocess.run(argv, capture_output=True, env=env, cwd=cwd, timeout=timeout, pass_fds=keep)
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
TITLE_PROBE = '''import hashlib, importlib.util, json, sys
spec = importlib.util.spec_from_file_location('cps_writer_title_probe', sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
try:
    r = m.deliverable_record(sys.stdin.buffer.read().decode('utf-8'))
    print(json.dumps({'ok': True, 'xlsx_file_sha256': hashlib.sha256(r['xlsx_file'].encode('utf-8')).hexdigest()}))
except m.Refused as e:
    print(json.dumps({'ok': False, 'code': e.code, 'reason': (e.detail or {}).get('reason') if isinstance(e.detail, dict) else None}))
'''


def check_title_with_writer(rel, title):
    """The writer's own O33 naming rule (deliverable_record), run before anything is generated: a title the writer would
    refuse at finish is refused here. The title goes on stdin, never on a command line. Returns the sha256 of the
    delivered file name the writer derives (N7)."""
    w = rel.root / 'research/export/writer_portable.py'
    p = subprocess.run(py('-I', '-B') + ['-c', TITLE_PROBE, str(w)], input=title.encode('utf-8'), capture_output=True, timeout=120)
    d = last_json_line(p.stdout) or {}
    if p.returncode != 0 or d.get('ok') is not True:
        raise Refused('JOB_TITLE_REFUSED_BY_WRITER', {'reason': d.get('reason')})
    return d.get('xlsx_file_sha256')


def check_title_shape(t, case):
    """N6, DN10: no invisible format character or line or paragraph separator (Unicode categories Cf, Zl, Zp: U+200B,
    U+202E, U+FEFF, U+2028, U+2029 ...), and the title starts with exactly the case id in ASCII digits (not fullwidth
    digits), the next character not another digit."""
    if not isinstance(t, str):
        raise Refused('JOB_TITLE_INVALID', 'the title is a string')
    if any(unicodedata.category(ch) in ('Cf', 'Zl', 'Zp') for ch in t):
        raise Refused('JOB_TITLE_FORMAT_CHARACTER', 'the title holds an invisible format character or a line or paragraph '
                      'separator (Unicode category Cf, Zl or Zp)')
    norm = ''.join(ch for ch in nfkc(t) if not ch.isspace())
    if (not t.startswith(case) or not norm.startswith(case)
            or (len(norm) > len(case) and norm[len(case)].isdigit()) or (len(t) > len(case) and t[len(case)].isdigit())):
        raise Refused('JOB_TITLE_INVALID', 'the project folder title starts with exactly the case id, in ASCII digits')


def parse_admission(admission_raw):
    adm = strict_json(admission_raw, 'admission')
    if not isinstance(adm, dict) or adm.get('schema') != ADMISSION_SCHEMA or not isinstance(adm.get('pins'), dict):
        raise Refused('ADMISSION_SCHEMA', {'expected': ADMISSION_SCHEMA})
    return adm


def admission_required_files(rel):
    """R12 (review 4(d) item 1): the files a qualification admission pins by label (the repository-relative path)."""
    out = [(rel.label(p), p) for p in executed_files(rel)]
    out.append((rel.label(rel.writer_admission), rel.writer_admission))
    out += [(f, rel.root / f) for f in EVALUATION_FILES]
    out.append((JOBS_LABEL, rel.jobs_file))
    return out


def check_admission(rel, admission_raw, facts, case, tables, admission_path=None):
    """R12: the admission is listed in the release by path and sha256, frozen before this prepare, and pins every job
    input and every tool, the evaluator, the aggregator and JOBS.json, each against the bytes the runner uses."""
    adm = parse_admission(admission_raw)
    a_sha = sha_bytes(admission_raw)
    if not rel.admission_listed(admission_path, admission_raw):
        raise Refused('ADMISSION_NOT_RELEASED', 'the release qualification.admissions must list this admission file by path and sha256')
    frozen = parse_utc(adm.get('frozen_utc'))
    if frozen is None:
        raise Refused('ADMISSION_FROZEN_UTC')
    if frozen >= datetime.datetime.now(datetime.timezone.utc):
        raise Refused('ADMISSION_NOT_FROZEN_BEFORE_PREPARE')
    pins = adm['pins']
    pinned = {v.get('sha256') for v in pins.values() if isinstance(v, dict)}
    tpin = pins.get('job_title_' + case)
    if not isinstance(tpin, dict) or tpin.get('sha256') != facts['job_title_sha256']:
        raise Refused('ADMISSION_JOB_TITLE_PIN', {'label': 'job_title_' + case})
    rel.require_qualification_fields()
    need = {'package manifest': rel.manifest_sha, 'route': sha_file(rel.route), 'JOB.json': facts['job_json_sha256'],
            'source': facts['source_sha256'], **{'table ' + k: v for k, v in tables.items()}}
    missing = sorted(k for k, v in need.items() if v not in pinned)
    mismatched = []
    for label, p in admission_required_files(rel):
        pin = pins.get(label)
        got = sha_file(p) if p is not None and p.is_file() else None
        if not isinstance(pin, dict) or not is_sha(pin.get('sha256')):
            missing.append(label)
        elif pin['sha256'] != got:
            mismatched.append(label)
    if missing or mismatched:
        raise Refused('ADMISSION_MISSING_PINS', {'missing': missing, 'mismatched': mismatched})
    facts['admission'] = {'sha256': a_sha, 'frozen_utc': adm['frozen_utc'], 'pins': len(pins),
                          'checked_pins': sorted(need) + ['job_title_' + case] + [lb for lb, _ in admission_required_files(rel)]}
    return adm


def job_inputs(job_raw, title_raw, rel, qualification, admission_raw, admission_path=None):
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
    check_title_shape(title['job_title'], case)
    # company tables: the job must use exactly the released, hash-pinned tables (never edited)
    tables, table_paths = {}, {}
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
        tables[tkey], table_paths[tkey] = h, jp
    cn_sha = rel.tables.get('company_name_sha256')
    if cn_sha is not None:
        if not isinstance(job.get('company_name'), str) or sha_bytes(job['company_name'].encode('utf-8')) != cn_sha:
            raise Refused('COMPANY_NAME_NOT_RELEASED')
    facts = {'case_id': case, 'source_kind_sha256': sha_bytes(str(job.get('source_kind')).encode('utf-8')),
             'job_json_sha256': sha_bytes(job_raw), 'job_title_sha256': sha_bytes(title_raw), 'source_sha256': sha_file(src),
             'source_bytes': src.stat().st_size, 'source_extension': src.suffix.lower(), 'tables_sha256': tables,
             'table_paths': table_paths}
    if qualification:
        if admission_raw is None:
            raise Refused('QUALIFICATION_NEEDS_ADMISSION')
        facts['admission_doc'] = check_admission(rel, admission_raw, facts, case, tables, admission_path)
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


def builder_config_problems(cfg, facts):
    """N14: the builder config made from JOB.json names exactly the pinned source, job file and released tables (the
    builder refuses a source whose bytes differ from the config's original.sha256)."""
    rs = cfg.get('resource_files_sha256') or {}
    out = []
    if (cfg.get('original') or {}).get('sha256') != facts['source_sha256']:
        out.append('BUILDER_CONFIG_SOURCE_SHA256')
    if cfg.get('job_config_sha256') != facts['job_json_sha256']:
        out.append('BUILDER_CONFIG_JOB_SHA256')
    for k in ('glossary', 'brand_table'):
        if rs.get(k) != facts['tables_sha256'].get(k):
            out.append('BUILDER_CONFIG_TABLE_SHA256_' + k.upper())
    return out


def write_packet_pins(st, jd):
    """R12 (review 4(d) item 2): every in-job product the generation depends on, pinned in a read-only PACKET_PINS.json
    before NEXT: GENERATE; in qualification its sha256 goes to the ledger, outside the job folder."""
    files = {}
    for root in ('packet', 'scope/tool', 'scope/reader/input', 'scope/decision', 'scope/scoped_packet'):
        t = tree(jd.p(root))
        for k, v in sorted((t or {'files': {}})['files'].items()):
            files[root + '/' + k] = v
    for one in ('scope/SCOPE_READER_PROMPT.md', 'scope/SCOPE_READER_RESPONSE.json', 'run/GENERATOR_PROMPT.md',
                f'run/{jd.rec["reader"]}/RUN_INPUT_PINS.json'):
        p = jd.p(one)
        if regular(p):
            files[one] = {'bytes': p.stat().st_size, 'sha256': sha_file(p)}
    keys = ('check_inventory_full', 'content_cells_literal_or_cached', 'scope_tool', 'scope_decision', 'scoped_verify',
            'check_inventory_scoped', 'generation')
    prep = jd.done('prepare')[-1]['facts'] if st.name != 'prepare' and jd.done('prepare') else {}
    doc = {'schema': PACKET_PINS_SCHEMA, 'case_id': jd.rec['case_id'], 'reader': jd.rec['reader'], 'stage': st.name,
           'written_utc': utc(), 'files': files,
           'facts': {k: st.facts.get(k, prep.get(k)) for k in keys if k in st.facts or k in prep}}
    p = jd.p('PACKET_PINS.json')
    write_new(p, dumps(doc))
    sha = st.pin_out('packet_pins', p)
    if jd.ledger_path is not None:
        with Ledger(jd.ledger_path, create=False) as led:
            led.append({'type': 'packet_pins', 'job_dir': str(jd.dir), 'case_id': jd.rec['case_id'], 'reader': jd.rec['reader'],
                        'stage': st.name, 'packet_pins_sha256': sha})
    st.facts['packet_pins'] = {'sha256': sha, 'files': len(files), 'in_ledger': jd.ledger_path is not None}


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
    make_tree_readonly(run_dir / 'input')                    # R5: the generator's input folders too
    (run_dir / 'RUN_INPUT_PINS.json').chmod(RO)
    st.pin_out('run_input_pins', run_dir / 'RUN_INPUT_PINS.json')
    st.pin_out('generator_prompt', prompt)
    st.facts['generation'] = {'run_dir': job.rel(run_dir), 'reader': reader, 'packet_inventory_sha256': packet_sha,
                              'inputs_pinned': len(pins['inputs']), 'response_path': job.rel(run_dir / 'output' / 'response.json')}
    write_packet_pins(st, job)
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
    if a.admission and not Path(a.admission).is_absolute():
        raise Refused('ABSOLUTE_PATH_REQUIRED', {'argument': '--admission'})
    if a.reader not in ('A', 'B'):
        raise Refused('READER', 'A or B')
    jobs_root = Path(a.jobs_root).resolve()
    if any(ch.isspace() for ch in str(jobs_root)):
        raise Refused('JOBS_ROOT_WHITESPACE', 'printed paths must not contain whitespace')
    rel_raw = Path(a.release).read_bytes()
    rel = Release(rel_raw, a.release)
    if inside(jobs_root, rel.root):                           # N11: private copies never sit in the public checkout
        raise Refused('JOBS_ROOT_IN_REPOSITORY', 'the jobs root must be outside repository.root')
    job_raw, title_raw = Path(a.job).read_bytes(), Path(a.job_title_file).read_bytes()
    adm_raw = Path(a.admission).read_bytes() if a.admission else None
    adm0 = parse_admission(adm_raw) if adm_raw is not None else None
    probe = Stage(Job(jobs_root / '_'), 'prepare', a)        # collects facts before the folder exists
    check_release_static(rel, a.qualification, probe, adm0)
    export_preflight(rel, probe)                             # fail early: a job never waits on an unadmitted node
    job, title, src, facts = job_inputs(job_raw, title_raw, rel, a.qualification, adm_raw, a.admission)
    name_sha = check_title_with_writer(rel, title['job_title'])
    case = facts['case_id']
    privates = [('--job', a.job), ('--job-title-file', a.job_title_file), ('source_path', src), ('--admission', a.admission)]
    privates += [('table ' + k, p) for k, p in facts['table_paths'].items()]
    if a.qualification:
        privates += [('qualification.ledger', rel.ledger), ('qualification.jobs_file', rel.jobs_file)]
    for label, p in privates:
        if p is not None and inside(p, rel.root):
            raise Refused('JOB_INPUT_IN_REPOSITORY', {'input': label})
    jobs = None
    if a.qualification:
        if inside(rel.ledger, jobs_root):
            raise Refused('QUALIFICATION_LEDGER_PATH', 'the ledger lies outside the jobs root and every job folder')
        jobs, jobs_sha, _ = load_jobs(rel, facts['admission_doc'])
        facts['admission']['jobs_sha256'] = jobs_sha
    jd = Job(jobs_root / case)
    if jd.dir.exists():
        raise Refused('JOB_DIR_EXISTS', 'a job folder is used once; never re-prepare into it')
    for name in HARNESS_FILES:
        if not (rel.harness / name).is_file():
            raise Refused('HARNESS_FILE_MISSING', {'file': name})
    for name in SOURCE_PREP_FILES:
        if not (rel.source_prep / name).is_file():
            raise Refused('SOURCE_PREP_FILE_MISSING', {'file': name})
    if not (rel.deps_bundle / 'private' / 'deps').is_dir():
        raise Refused('DEPS_BUNDLE_MISSING', 'source_prep.deps_bundle must hold private/deps (openpyxl 3.1.5, xlrd 2.0.2)')
    bv = bundle_versions(rel.deps_bundle)
    if bv['openpyxl']['version'] != OPENPYXL_VERSION or not bv['openpyxl']['from_bundle']:
        raise Refused('DEPS_BUNDLE_OPENPYXL_VERSION', {'found': bv['openpyxl']['version'], 'required': OPENPYXL_VERSION})
    probe.facts['deps_bundle'] = bv
    # make_job_config validates the job inputs before the job folder exists (a refusal leaves nothing behind)
    vdir = jobs_root / ('.validate_' + case + '_' + str(os.getpid()))
    jobs_root.mkdir(parents=True, exist_ok=True)
    vdir.mkdir()
    try:
        vjob = vdir / 'JOB.json'
        write_new(vjob, job_raw)
        p = subprocess.run(py('-I', '-B') + [str(rel.harness / 'make_job_config.py'), '--job', str(vjob),
                           '--out', str(vdir / 'BUILDER_CONFIG.json')], capture_output=True, timeout=600, env=tool_env(rel))
        if p.returncode != 0:
            raise Refused('JOB_CONFIG_REFUSED', {'make_job_config_code': refusal_code(p.stderr)})
    finally:
        shutil.rmtree(vdir, ignore_errors=True)
    rec = {'schema': RECORD_SCHEMA, 'runner': {'version': VERSION, 'sha256': sha_file(__file__)}, 'case_id': case,
           'reader': a.reader, 'qualification': bool(a.qualification), 'created_utc': utc(),
           'release': dict(rel.summary(), path=os.path.abspath(a.release)),
           'job_inputs': {k: facts[k] for k in ('job_json_sha256', 'job_title_sha256', 'source_sha256', 'source_bytes',
                                                'source_extension', 'source_kind_sha256', 'tables_sha256')},
           'deliverable_file_name_sha256': name_sha, 'admission': facts.get('admission'), 'restart_of': None,
           'ledger': str(rel.ledger) if a.qualification else None,
           'user_options': 'none: the runner takes no per-user options', 'operator_model': a.operator_model, 'stages': []}
    if a.qualification:
        with Ledger(rel.ledger) as led:
            rec['restart_of'] = ledger_admit_prepare(led, jobs, case, a.reader, str(jd.dir), facts['admission_doc'])
            make_job_folder(jd, rel_raw, job_raw, title_raw, src, facts, adm_raw, rec)
            led.append({'type': 'prepare', 'case_id': case, 'reader': a.reader, 'jobs_root': str(jobs_root), 'job_dir': str(jd.dir),
                        'admission_sha256': facts['admission']['sha256'], 'release_sha256': rel.sha,
                        'restart_of': rec['restart_of'], 'run_record_sha256': sha_bytes(jd.raw)})
        jd.ledger_path = rel.ledger
    else:
        make_job_folder(jd, rel_raw, job_raw, title_raw, src, facts, adm_raw, rec)
    st = Stage(jd, 'prepare', a)
    st.facts.update(probe.facts)
    st.tools.update(probe.tools)
    st.facts['restart_of'] = rec['restart_of']
    for label, rp in (('release', 'RELEASE.json'), ('job_json', 'JOB.json'), ('job_title', 'JOB_TITLE.json'),
                      ('source', 'source' + facts['source_extension'])):
        st.pin_in(label, jd.p('input', rp))
    if adm_raw is not None:
        st.pin_in('admission', jd.p('input', 'ADMISSION.json'))
    return run_stage(jd, st, lambda: prepare_body(st, jd, rel, case, a.reader, facts))


def make_job_folder(jd, rel_raw, job_raw, title_raw, src, facts, adm_raw, rec):
    try:
        jd.dir.mkdir()
    except FileExistsError:
        raise Refused('JOB_DIR_EXISTS', 'a job folder is used once; never re-prepare into it')
    jd.lock(wait=True)
    for d in LAYOUT:
        jd.p(d).mkdir()
    write_new(jd.p('input', 'RELEASE.json'), rel_raw)
    write_new(jd.p('input', 'JOB.json'), job_raw)
    write_new(jd.p('input', 'JOB_TITLE.json'), title_raw)
    write_new(jd.p('input', 'source' + facts['source_extension']), src.read_bytes())
    if adm_raw is not None:
        write_new(jd.p('input', 'ADMISSION.json'), adm_raw)
    jd.create(rec)


def seal_prepare(jd):
    """R1: the packet and the scope tool's files are read-only once prepare has pinned them (scope-finish re-verifies)."""
    for root in ('packet', 'scope/tool', 'scope/reader/input'):
        make_tree_readonly(jd.p(root))


def prepare_body(st, jd, rel, case, reader, facts):
    env = tool_env(rel)
    cfg = jd.p('packet', 'BUILDER_CONFIG.json')
    code, _, _ = st.run('make_job_config', rel.harness / 'make_job_config.py', ['--job', jd.p('input', 'JOB.json'), '--out', cfg], env=env)
    if code != 0:
        raise Outcome('JOB_CONFIG_REFUSED', 'STOP_JOB_CONFIG_REFUSED')
    st.pin_out('builder_config', cfg)
    cfg_doc = read_json(cfg, 'builder config')
    bad = builder_config_problems(cfg_doc, facts)
    if bad:
        st.codes += bad
        raise Outcome('BUILDER_CONFIG_MISMATCH', 'STOP_BUILDER_CONFIG_MISMATCH')
    builder = rel.source_prep / Path(cfg_doc['builder']).name
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
    for name, label in (('SCOPE_DIGEST.json', 'scope_digest'), ('SCOPE_RULES_EXCERPT.md', 'scope_rules_excerpt')):
        if jd.p('scope', 'tool', name).is_file():
            st.pin_out(label, jd.p('scope', 'tool', name))
    status = proposal['status']
    st.facts['scope_tool'] = {'status': status, 'content_cells_literal_or_cached': proposal['content_cells_literal_or_cached'],
                              'threshold': proposal['rule']['threshold'], 'holds': [h['code'] for h in proposal['holds']],
                              'flags': [f['code'] for f in proposal['flags']], 'bill_sheet_index': proposal['bill']['sheet_index'],
                              'end_row': proposal['bill']['end_row']}
    st.facts['pinned_trees'] = {'packet': tree_shas(jd.p('packet')), 'scope/tool': tree_shas(jd.p('scope', 'tool'))}
    if proposal['content_cells_literal_or_cached'] != count or (status == 'NOT_APPLIED') != (count <= proposal['rule']['threshold']):
        raise Outcome('SCOPE_COUNT_INCONSISTENT', 'STOP_SCOPE_COUNT_INCONSISTENT')
    if status == 'HOLD':
        st.codes += [h['code'] for h in proposal['holds']]
        raise Outcome('SCOPE_TOOL_HOLD', 'OWNER_DECISION')
    if status == 'NOT_APPLIED':
        seal_prepare(jd)
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
    seal_prepare(jd)
    return 'SCOPE_PROPOSED', f'SCOPE_READER prompt={prompt} folder={sr}'


# ------------------------------------------------------------------ scope-finish
def cmd_scope_finish(a):
    jd = open_job(a.job_dir)
    st = Stage(jd, 'scope-finish', a)
    return run_stage(jd, st, lambda: scope_finish_body(st, jd, a), preflight=lambda: scope_finish_pre(st, jd, a))


def require_not_interrupted(jd):
    """D1: after a technical interruption that stopped the folder only freeze runs in it (the restart is a new prepare);
    an in-place restart (an interrupt that printed NEXT: GENERATE) lets the run go on."""
    if any(x['next'] == 'STOP_TECHNICAL_INTERRUPTION' for x in jd.done('interrupt')):
        raise Refused('JOB_INTERRUPTED', 'a technical interruption is recorded: freeze the folder; a restart is a new prepare')


def scope_finish_pre(st, jd, a):
    jd.require_not_frozen()
    jd.require_stage_open('scope-finish')
    require_not_interrupted(jd)
    prep = jd.done('prepare')
    if not prep or not str(prep[-1]['next']).startswith('SCOPE_READER'):
        raise Refused('SCOPE_STAGE_NOT_OPEN', 'prepare did not end with NEXT: SCOPE_READER')
    rel = jd.release()
    check_release_static(rel, jd.rec['qualification'], st, jd.admission())
    st.facts['live_release'] = check_live_release(jd)
    resp = Path(a.reader_response)
    if not resp.is_absolute() or not resp.is_file():
        raise Refused('READER_RESPONSE_REQUIRED', 'an absolute path to the reader JSON')
    expected = jd.p('scope', 'reader', 'output', 'SCOPE_READER_RESPONSE.json')
    if os.path.realpath(resp) != str(expected) or not regular(expected):
        raise Refused('READER_RESPONSE_PATH', 'the reader writes scope/reader/output/SCOPE_READER_RESPONSE.json')
    if a.reader_conversation_id is not None and not attested(a.reader_conversation_id):
        raise Refused('READER_CONVERSATION_ID_BLANK', 'a non-blank id or link, not a template placeholder')
    # DN1: the operator states the sha256 of the prompt it gave the reader (as the generation record does for the
    # generator; the reader's JSON has no such key in scope_agree.py); required in qualification
    want = (prep[-1]['outputs'].get('scope_reader_prompt') or {}).get('sha256')
    if a.reader_prompt_sha256 is None and jd.rec['qualification']:
        raise Refused('READER_PROMPT_SHA256_REQUIRED', 'qualification: --reader-prompt-sha256 (sha256sum scope/SCOPE_READER_PROMPT.md)')
    if a.reader_prompt_sha256 is not None and a.reader_prompt_sha256 != want:
        raise Refused('READER_PROMPT_SHA256_MISMATCH', '--reader-prompt-sha256 is not the sha256 of the prompt prepare wrote')
    return {'rel': rel, 'raw': resp.read_bytes(), 'prep': prep[-1]}


def scope_inputs_changed(jd, prep):
    """R1: the scope tool's files, the full packet and the proposal's facts, against the prepare pins."""
    codes = []
    for root, want in (prep['facts'].get('pinned_trees') or {}).items():
        t = tree(jd.p(root))
        if t is None or t['other'] or {k: v['sha256'] for k, v in t['files'].items()} != want:
            codes.append('CHANGED_' + root.upper().replace('/', '_'))
    if not prep['facts'].get('pinned_trees'):
        codes.append('NO_PREPARE_PINS')
    for label in ('scope_proposal', 'scope_digest', 'scope_rules_excerpt', 'full_inventory', 'builder_config',
                  'scope_reader_prompt'):                    # DN1: the reader prompt too (scope/ itself stays writable)
        o = prep['outputs'].get(label)
        if o is None or not regular(jd.p(o['path'])) or sha_file(jd.p(o['path'])) != o['sha256']:
            codes.append('CHANGED_' + label.upper())
    if not codes:
        proposal = read_json(jd.p('scope', 'tool', 'SCOPE_PROPOSAL.json'), 'scope proposal')
        f = prep['facts']['scope_tool']
        if (proposal.get('status'), proposal['bill'].get('sheet_index'), proposal['bill'].get('end_row')) != \
                (f['status'], f['bill_sheet_index'], f['end_row']):
            codes.append('SCOPE_PROPOSAL_FACTS_CHANGED')
    return codes


def scope_reader_folder_problems(jd, prep):
    """R5 at scope-finish: the reader's folder holds exactly input/ (the two pinned files) and output/ (its response)."""
    sr = jd.p('scope', 'reader')
    inputs, outputs = [], []
    if sorted(os.listdir(sr)) != ['input', 'output']:
        inputs.append('SCOPE_READER_FOLDER_UNEXPECTED_ENTRIES')
    t = tree(sr / 'input')
    want = {n: prep['outputs'].get('scope_reader_' + n, {}).get('sha256') for n in ('SCOPE_DIGEST.json', 'SCOPE_RULES_EXCERPT.md')}
    if t is None or t['dirs'] or t['other'] or {k: v['sha256'] for k, v in t['files'].items()} != want:
        inputs.append('SCOPE_READER_INPUT_NOT_THE_PINNED_FILES')
    o = tree(sr / 'output')
    if o is None or o['dirs'] or o['other'] or sorted(o['files']) != ['SCOPE_READER_RESPONSE.json']:
        outputs.append('SCOPE_READER_OUTPUT_UNEXPECTED_ENTRIES')
    return inputs, outputs


def scoped_route_status(receipt, ver):
    """N1: the receipt's and --verify's own route check of the scoped inventory, besides --verify's status."""
    r = (receipt or {}).get('route_check_inventory') or {}
    v = (ver or {}).get('route_check_inventory') or {}
    out = {'verify_status': (ver or {}).get('status'), 'receipt_route_check_inventory': r.get('status'),
           'verify_route_check_inventory': v.get('status'), 'receipt_route_violations': r.get('violations'),
           'verify_route_violations': v.get('violations')}
    out['pass'] = out['verify_status'] == 'PASS' and r.get('status') == 'PASS' and v.get('status') == 'PASS'
    return out


def scope_finish_body(st, jd, a):
    rel, raw, prep = st.pre['rel'], st.pre['raw'], st.pre['prep']
    env = tool_env(rel)
    frozen = jd.p('scope', 'SCOPE_READER_RESPONSE.json')     # frozen before any tool reads it
    freeze_copy(raw, frozen)
    st.inputs['reader_response_original'] = {'path': str(a.reader_response), 'sha256': sha_bytes(raw), 'bytes': len(raw)}
    st.pin_in('reader_response', frozen)
    st.facts['reader_conversation_id_attested_by_operator'] = a.reader_conversation_id
    st.facts['reader_prompt_sha256_attested_by_operator'] = a.reader_prompt_sha256
    codes = scope_inputs_changed(jd, prep)
    if codes:
        st.codes += codes
        raise Outcome('SCOPE_INPUTS_CHANGED', 'STOP_SCOPE_INPUTS_CHANGED')
    inputs, outputs = scope_reader_folder_problems(jd, prep)
    if inputs or outputs:
        st.codes += inputs + outputs
        if inputs:
            raise Outcome('SCOPE_READER_INPUT_CHANGED', 'STOP_SCOPE_READER_INPUT_CHANGED')
        raise Outcome('SCOPE_READER_OUTPUT_UNEXPECTED', 'STOP_SCOPE_READER_OUTPUT_UNEXPECTED')
    dec_dir = jd.p('scope', 'decision')
    code, out, err = st.run('scope_agree', rel.harness / 'scope_agree.py',
                            ['--proposal', jd.p('scope', 'tool', 'SCOPE_PROPOSAL.json'), '--digest', jd.p('scope', 'tool', 'SCOPE_DIGEST.json'),
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
    rs = scoped_route_status(receipt, ver)
    st.facts['scoped_verify'] = {'status': ver.get('status'), 'problem_count': ver.get('problem_count'), 'stats': ver.get('stats'),
                                 'route_check': rs, 'in_scope_content_cells': (ver.get('stats') or {}).get('content_cells_scoped')}
    if code != 0 or ver.get('status') != 'PASS':
        raise Outcome('SCOPED_VERIFY_FAILED', 'STOP_SCOPED_VERIFY_FAILED')
    if not rs['pass']:
        st.codes += sorted(set((rs['receipt_route_violations'] or []) + (rs['verify_route_violations'] or []))) or ['ROUTE_CHECK_NOT_PASS']
        raise Outcome('SCOPED_ROUTE_CHECK_FAILED', 'STOP_SCOPED_ROUTE_CHECK_FAILED')
    check_inventory(st, rel, scoped, 'check_inventory_scoped', 'applied')
    make_tree_readonly(jd.p('scope', 'decision'))
    make_tree_readonly(scoped_dir)
    return 'SCOPE_AGREED', prepare_generation(st, jd, rel, scoped_dir, jd.rec['reader'], jd.rec['case_id'])


# ------------------------------------------------------------------ finish
def cmd_finish(a):
    jd = open_job(a.job_dir)
    st = Stage(jd, 'finish', a)
    return run_stage(jd, st, lambda: finish_body(st, jd, a), preflight=lambda: finish_pre(st, jd, a))


def generation_stage(jd):
    """The stage that pinned the generation run (scope-finish or prepare, NEXT: GENERATE)."""
    for name in ('scope-finish', 'prepare'):
        d = jd.done(name)
        if d and str(d[-1]['next']).startswith('GENERATE'):
            return d[-1]
    return None


def generation_window_start(jd, gen):
    """The generator conversation starts after the last completed stage that printed NEXT: GENERATE: the stage that pinned
    the run, or the in-place restart after it (rule 3)."""
    after = [x for x in jd.rec['stages'] if x['completed'] and x['next'] == 'GENERATE' and x['seq'] >= gen.get('seq', 0)]
    return (after[-1] if after else gen)


GEN_KEYS = {'schema', 'case_id', 'reader', 'platform', 'model', 'effort', 'conversation_id', 'started_utc', 'ended_utc',
            'prompt_sha256', 'single_user_message', 'features', 'tools_enabled', 'final_message', 'transcript_status',
            'transcript_sha256', 'transcript_not_available_reason', 'notes'}
GEN_OPTIONAL = {'transcript_sha256', 'transcript_not_available_reason', 'notes'}


def generation_record_problems(g, case, reader):
    """R13: the shape of GENERATION_RECORD.json (cps.generation-record.v1; RUN_JOB_COMMANDS.md)."""
    if not isinstance(g, dict):
        return ['not an object']
    p = []
    if set(g) - GEN_KEYS:
        p.append(f'{len(set(g) - GEN_KEYS)} unknown keys')
    p += [f'missing {k}' for k in sorted(GEN_KEYS - GEN_OPTIONAL - set(g))]
    if g.get('schema') != GENERATION_RECORD_SCHEMA:
        p.append('schema')
    if g.get('case_id') != case:
        p.append('case_id')
    if g.get('reader') != reader:
        p.append('reader')
    p += [k for k in ('platform', 'model', 'effort', 'conversation_id') if not attested(g.get(k))]   # DN14: no placeholder
    p += [k for k in ('started_utc', 'ended_utc') if parse_utc(g.get(k)) is None]
    if not is_sha(g.get('prompt_sha256')):
        p.append('prompt_sha256')
    if not isinstance(g.get('single_user_message'), bool):
        p.append('single_user_message')
    f = g.get('features')
    if not isinstance(f, dict) or set(f) != set(FEATURES) or not all(isinstance(v, bool) for v in f.values()):
        p.append('features {' + ', '.join(FEATURES) + '}')
    t = g.get('tools_enabled')
    if not isinstance(t, list) or not all(isinstance(x, str) for x in t):
        p.append('tools_enabled')
    if not isinstance(g.get('final_message'), str):
        p.append('final_message')
    ts = g.get('transcript_status')
    if ts not in TRANSCRIPT_STATUSES:
        p.append('transcript_status')
    if ts == 'exported' and not is_sha(g.get('transcript_sha256')):
        p.append('transcript_sha256')
    if ts == 'not_available' and (not nonblank(g.get('transcript_not_available_reason')) or g.get('transcript_sha256') is not None):
        p.append('transcript_not_available_reason')
    if 'notes' in g and not isinstance(g['notes'], str):
        p.append('notes')
    return p


def check_generation_record(st, jd, a, gen, rel):
    """R13: required for qualification, recorded when given. The prompt hash equals run/GENERATOR_PROMPT.md, and the
    conversation lies between the end of the stage that printed NEXT: GENERATE and the start of this finish. D3 (owner
    decision O40): qualification accepts both transcript statuses; a qualification record that says exported must come
    with the transcript file (--transcript, frozen and hash-checked), and isolation_evidence follows the frozen file."""
    q = jd.rec['qualification']
    if q and not nonblank(a.generator_model):
        raise Refused('GENERATOR_MODEL_REQUIRED', 'qualification: --generator-model')
    if a.generation_record is None:
        if q:
            raise Refused('GENERATION_RECORD_REQUIRED', 'qualification: --generation-record run/GENERATION_RECORD.json')
        if a.transcript is not None:
            raise Refused('TRANSCRIPT_WITHOUT_RECORD')
        return None
    p, expected = Path(a.generation_record), jd.p('run', 'GENERATION_RECORD.json')
    if not p.is_absolute() or os.path.realpath(p) != str(expected) or not regular(expected):
        raise Refused('GENERATION_RECORD_PATH', 'the generation record is run/GENERATION_RECORD.json of this job')
    raw = expected.read_bytes()
    st.inputs['generation_record_original'] = {'path': str(p), 'sha256': sha_bytes(raw), 'bytes': len(raw)}
    g = strict_json(raw, 'generation record')
    bad = generation_record_problems(g, jd.rec['case_id'], jd.rec['reader'])
    if bad:
        raise Refused('GENERATION_RECORD_INVALID', {'fields': bad})
    if g['prompt_sha256'] != gen['outputs']['generator_prompt']['sha256']:
        raise Refused('GENERATION_RECORD_PROMPT_MISMATCH', 'prompt_sha256 is not the sha256 of run/GENERATOR_PROMPT.md')
    win = generation_window_start(jd, gen)
    t0, t1, lo, hi = parse_utc(g['started_utc']), parse_utc(g['ended_utc']), parse_utc(win['ended_utc']), parse_utc(st.started)
    if not (lo <= t0 <= t1 <= hi):
        raise Refused('GENERATION_RECORD_TIMES', 'started_utc and ended_utc lie between the end of the stage that printed '
                      'NEXT: GENERATE and the start of this finish')
    if a.generator_model is not None and a.generator_model != g['model']:
        raise Refused('GENERATOR_MODEL_MISMATCH', '--generator-model differs from the record model')
    accepted = rel.accepted_transcripts if q else list(TRANSCRIPT_STATUSES)
    if g['transcript_status'] not in (accepted or []):
        raise Refused('TRANSCRIPT_STATUS_NOT_ACCEPTED', {'status': g['transcript_status'], 'accepted': accepted})
    if q and g['transcript_status'] == 'exported' and a.transcript is None:
        raise Refused('TRANSCRIPT_REQUIRED', 'qualification: transcript_status exported needs --transcript <the exported file>')
    transcript = None
    if a.transcript is not None:
        tp = Path(a.transcript)
        if not tp.is_absolute() or not regular(tp):
            raise Refused('TRANSCRIPT_REQUIRED', 'an absolute path to the exported transcript')
        if g['transcript_status'] != 'exported':
            raise Refused('TRANSCRIPT_NOT_EXPORTED', 'transcript_status is not exported')
        traw = tp.read_bytes()
        if sha_bytes(traw) != g['transcript_sha256']:
            raise Refused('TRANSCRIPT_SHA256_MISMATCH')
        transcript = (traw, ''.join(ch for ch in tp.suffix if ch.isascii() and (ch.isalnum() or ch == '.'))[:10])
    exported, frozen_file = g['transcript_status'] == 'exported', transcript is not None
    facts = {'sha256': sha_bytes(raw), 'platform': g['platform'], 'model': g['model'], 'effort': g['effort'],
             'transcript_status': g['transcript_status'], 'transcript_file_frozen': frozen_file,
             'transcript_not_available_flagged': not exported,
             'transcript_claimed_but_not_frozen': exported and not frozen_file,
             'isolation_evidence': 'transcript_exported' if frozen_file else 'attested_not_audited',      # D3: the file, not the claim
             'transcript_audit': ('not_run_by_the_runner' if frozen_file else 'no_transcript_frozen' if exported else 'not_available'),
             'single_user_message': g['single_user_message'], 'features_enabled': sorted(k for k, v in g['features'].items() if v),
             'tools_enabled': len(g['tools_enabled']), 'prompt_sha256_matches_generator_prompt': True, 'times_within_bounds': True,
             'generation_seconds': round((t1 - t0).total_seconds(), 1), 'window_seconds': round((hi - lo).total_seconds(), 1),
             'window_from_stage': {'stage': win.get('stage'), 'seq': win.get('seq')}, 'qualification_transcript_rule': O40_RULE}
    return {'raw': raw, 'facts': facts, 'transcript': transcript}


def finish_pre(st, jd, a):
    jd.require_not_frozen()
    jd.require_stage_open('finish', also=('freeze_response',))
    require_not_interrupted(jd)
    gen = generation_stage(jd)
    if gen is None:
        raise Refused('GENERATION_NOT_PREPARED', 'no stage ended with NEXT: GENERATE')
    rel = jd.release()
    check_release_static(rel, jd.rec['qualification'], st, jd.admission())
    st.facts['live_release'] = check_live_release(jd)
    adm, adm_sha, node, tools = export_preflight(rel, st)
    st.facts['writer_admission_live'] = writer_admission_live(rel, jd.admission())           # E2
    title_rec = jd.pinned_file('input/JOB_TITLE.json', jd.rec['job_inputs']['job_title_sha256'])
    title = read_json(title_rec, 'JOB_TITLE.json')['job_title']
    if a.job_title is not None and a.job_title != title:
        raise Refused('JOB_TITLE_MISMATCH', 'the --job-title given differs from input/JOB_TITLE.json')
    resp = Path(a.response)
    if not resp.is_absolute() or not resp.is_file():
        raise Refused('RESPONSE_REQUIRED', 'an absolute path to the response file')
    expected = jd.p(gen['facts']['generation']['response_path'])
    if os.path.realpath(resp) != str(expected) or not regular(expected):        # N5: real jobs too
        raise Refused('RESPONSE_PATH', 'the response is run/<reader>/output/response.json')
    st.facts['response_from_run_output'] = True
    gr = check_generation_record(st, jd, a, gen, rel)
    return {'rel': rel, 'adm': adm, 'adm_sha': adm_sha, 'node': node, 'title': title, 'gen': gen, 'gr': gr}


def run_folder_problems(jd, rel, gen):
    """R5: the generation folder holds exactly RUN_INPUT_PINS.json (its prepare pin), input/ (exactly the pinned files and
    their folders, no symbolic link; the package copy equal to PACKAGE_MANIFEST.json) and output/ (response.json and
    optionally scratch/). Returns (input codes, output codes, output listing)."""
    run_dir = jd.p(gen['facts']['generation']['run_dir'])
    pp = run_dir / 'RUN_INPUT_PINS.json'
    if not regular(pp) or sha_file(pp) != gen['outputs']['run_input_pins']['sha256']:
        return ['RUN_INPUT_PINS_CHANGED'], [], None
    pins = read_json(pp, 'RUN_INPUT_PINS.json')
    want = {x['path']: x['sha256'] for x in pins['inputs']}
    codes = []
    if sorted(os.listdir(run_dir)) != sorted(['input', 'output', 'RUN_INPUT_PINS.json']):
        codes.append('RUN_FOLDER_UNEXPECTED_ENTRIES')
    t = tree(run_dir / 'input') or {'files': {}, 'dirs': [], 'other': ['input']}
    have = {'input/' + k: v['sha256'] for k, v in t['files'].items()}
    if set(have) != set(want):
        codes.append('RUN_INPUT_FILES_NOT_THE_PINNED_SET')
    if any(have[k] != want[k] for k in set(have) & set(want)):
        codes.append('RUN_INPUT_FILE_CHANGED')
    want_dirs = set()
    for k in want:
        parts = k.split('/')[1:-1]
        want_dirs |= {'/'.join(parts[:i]) for i in range(1, len(parts) + 1)}
    if set(t['dirs']) != want_dirs:
        codes.append('RUN_INPUT_FOLDERS_NOT_THE_PINNED_SET')
    if t['other']:
        codes.append('RUN_INPUT_SYMLINK_OR_SPECIAL_FILE')
    man = run_dir / 'input' / 'package' / 'PACKAGE_MANIFEST.json'
    if not regular(man) or sha_file(man) != rel.manifest_sha:
        codes.append('PACKAGE_COPY_MANIFEST_CHANGED')
    else:
        listed = {f['path']: f['sha256'] for f in read_json(man, 'package manifest').get('files', [])}
        copy = {k[len('package/'):]: v['sha256'] for k, v in t['files'].items() if k.startswith('package/')}
        copy.pop('PACKAGE_MANIFEST.json', None)
        if copy != listed:
            codes.append('PACKAGE_COPY_NOT_THE_MANIFEST')
    if codes:
        return codes, [], None
    o = tree(run_dir / 'output')
    if o is None:
        return [], ['RUN_OUTPUT_NOT_A_FOLDER'], None
    ocodes = []
    top = {k.split('/')[0] for k in list(o['files']) + o['dirs'] + o['other']}
    if top - {'response.json', 'scratch'}:
        ocodes.append('RUN_OUTPUT_UNEXPECTED_ENTRIES')
    if 'scratch' in top and 'scratch' not in o['dirs']:
        ocodes.append('RUN_OUTPUT_SCRATCH_NOT_A_FOLDER')
    if o['other']:
        ocodes.append('RUN_OUTPUT_SYMLINK_OR_SPECIAL_FILE')
    if 'response.json' not in o['files']:
        ocodes.append('RUN_OUTPUT_NO_RESPONSE')
    return [], ocodes, o['files']


def packet_pins_problems(jd, gen):
    """R12: PACKET_PINS.json is the one pinned before NEXT: GENERATE (and, in qualification, the one in the ledger), and
    every file it lists is unchanged."""
    o = gen['outputs'].get('packet_pins')
    p = jd.p('PACKET_PINS.json')
    if o is None or not regular(p) or sha_file(p) != o['sha256']:
        return ['PACKET_PINS_CHANGED']
    if jd.ledger_path is not None:
        with Ledger(jd.ledger_path, create=False) as led:
            if not led.of('packet_pins', job_dir=str(jd.dir), packet_pins_sha256=o['sha256']):
                return ['PACKET_PINS_NOT_IN_LEDGER']
    doc = read_json(p, 'PACKET_PINS.json')
    changed = [k for k, v in doc['files'].items() if not regular(jd.p(k)) or sha_file(jd.p(k)) != v['sha256']]
    return [f'{len(changed)} PACKET_PINS files changed'] if changed else []


def finish_body(st, jd, a):
    pre = st.pre
    rel, adm, node, title, gen, gr = pre['rel'], pre['adm'], pre['node'], pre['title'], pre['gen'], pre['gr']
    # 1. freeze the generation record and the response bytes before anything reads them
    fr = Stage(jd, 'freeze_response', a)
    if gr is not None:
        freeze_copy(gr['raw'], jd.p('response', 'GENERATION_RECORD.json'))
        fr.pin_out('generation_record', jd.p('response', 'GENERATION_RECORD.json'))
        st.pin_in('generation_record', jd.p('response', 'GENERATION_RECORD.json'))
        if gr['transcript'] is not None:
            tdest = jd.p('response', 'GENERATOR_TRANSCRIPT' + gr['transcript'][1])
            freeze_copy(gr['transcript'][0], tdest)
            fr.pin_out('generator_transcript', tdest)
    raw = Path(a.response).read_bytes()
    frozen = jd.p('response', 'response.json')
    freeze_copy(raw, frozen)
    fr.inputs['response_original'] = {'path': str(a.response), 'sha256': sha_bytes(raw), 'bytes': len(raw)}
    fr.pin_out('response', frozen)
    fr.facts = {'generator_model': a.generator_model, 'response_from_run_output': True,
                'generation_record': gr['facts'] if gr is not None else None}
    jd.append(fr.entry('RESPONSE_FROZEN', 'FINISH', True))
    st.pin_in('response', frozen)
    resp_sha = sha_file(frozen)
    st.facts['generator_model'] = a.generator_model
    st.facts['generation_record'] = gr['facts'] if gr is not None else None
    # R5 and R12: the generation folder and every in-job product exactly as pinned before NEXT: GENERATE
    icodes, ocodes, listing = run_folder_problems(jd, rel, gen)
    st.facts['run_inputs_unchanged'] = not icodes
    st.facts['run_output_files'] = listing
    if icodes:
        st.codes += icodes
        raise Outcome('RUN_INPUTS_CHANGED', 'STOP_RUN_INPUTS_CHANGED')
    if ocodes:
        st.codes += ocodes
        raise Outcome('RUN_OUTPUT_UNEXPECTED', 'STOP_RUN_OUTPUT_UNEXPECTED')
    pcodes = packet_pins_problems(jd, gen)
    if pcodes:
        st.codes += pcodes
        raise Outcome('PACKET_CHANGED', 'STOP_PACKET_CHANGED')
    run_dir = jd.p(gen['facts']['generation']['run_dir'])
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
    make_tree_readonly(conv)
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
    make_tree_readonly(out_dir)
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
    st.facts['visual_qa_dpi'] = {}
    for key, fname, saved_sha in (('deliverable', sq['deliverable_xlsx']['file'], sq['deliverable_xlsx']['sha256']),
                                  ('internal', sq['xlsx']['file'], sq['xlsx']['sha256'])):
        dest = jd.p('qa', 'visual_' + key)
        # v2.8.2 condition 8 (O39, F3): never --dpi, so visual_qa's automatic dpi rule applies (the delivered sheet by its width)
        code, out, err = st.run('visual_qa_' + key, rel.root / 'research/export/visual_qa.py', ['--xlsx', out_dir / fname, '--dest', dest], env=env)
        man_p = dest / 'VISUAL_QA_MANIFEST.json'
        man = read_json(man_p, 'visual manifest') if code == 0 and man_p.is_file() else None
        if man is not None:
            make_tree_readonly(dest)
            st.pin_out('visual_manifest_' + key, man_p)
        sx = (man or {}).get('saved_xlsx') or {}
        ok = man is not None and sx.get('sha256') == saved_sha and sx.get('unchanged_after_render') is True and man.get('complete_render') is True
        tp = deliverable_tile_problems(man) if key == 'deliverable' else []
        st.facts['visual_qa_dpi'][key] = {'dpi_argument_given': False, 'dpi': (man or {}).get('dpi'), 'dpi_rule': (man or {}).get('dpi_rule')}
        ev.add('8.render_' + key, f'visual QA of the {key} workbook: manifest saved_xlsx.sha256 equals SAVED_QA.json '
               + ('deliverable_xlsx.sha256' if key == 'deliverable' else 'xlsx.sha256') + ', unchanged after render, complete render'
               + ('; every page has its tiles (visual_qa v4.5, F3)' if key == 'deliverable' else ''),
               {'exit': code, 'manifest_saved_xlsx_sha256': sx.get('sha256'), 'saved_qa_sha256': saved_sha,
                'complete_render': (man or {}).get('complete_render'), 'pages': (man or {}).get('pages'),
                **({'tiles': tiles_summary(man), 'tile_problems': tp} if key == 'deliverable' else {})}, ok and not tp)
        vis[key] = (man, man_p)
    if not ev.grade():
        ev.write(jd, st, pre, sq)
        st.codes += ev.failed()
        raise Outcome('VISUAL_QA_RENDER_FAILED', 'STOP_VISUAL_QA_RENDER_FAILED')
    # F3: beyond visual_qa's legibility bound the 600-dpi cap shrinks the glyphs: an unreadable sheet cannot be judged, so the
    # delivered workbook fails visual QA here (a recorded visual failure), before any reviewer is asked
    dman = vis['deliverable'][0]
    exceeded = legibility_bound_exceeded(dman)
    ev.add('8.legibility', 'the delivered workbook lies within visual_qa\'s legibility bound (manifest tiles.legibility_bound_exceeded '
           'false); an unreadable sheet cannot be judged and fails visual QA', tiles_summary(dman), not exceeded)
    if exceeded:
        ev.write(jd, st, pre, sq)
        rec = {'schema': 'cps.visual-record.v1', 'case_id': jd.rec['case_id'], 'recorded_utc': utc(), 'result': 'FAIL',
               'reviewer': None, 'failed_items': ['deliverable: tiles.legibility_bound_exceeded (an unreadable sheet cannot be judged)'],
               'tiles': tiles_summary(dman), 'note': 'recorded by finish from the delivered visual manifest; no visual review was asked'}
        write_new(jd.p('qa', 'VISUAL_RECORD.json'), dumps(rec))
        st.pin_out('visual_record', jd.p('qa', 'VISUAL_RECORD.json'))
        st.codes += ['TILES_LEGIBILITY_BOUND_EXCEEDED']
        raise Outcome('VISUAL_QA_FAILED', 'STOP_VISUAL_REVIEW_FAILED')
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
               'evidence_grade_meaning': (f'true only when every condition of {pre["rel"].writer_admission.name} that this machine can check holds; '
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


TILE_KEYS = ('file', 'sha256', 'bytes', 'x', 'y', 'width_px', 'height_px', 'png_width_px', 'png_height_px')


def tile_file_ok(name):
    """A tile's file is a relative path inside the render folder (tiles/<name>.png), never absolute or with '..'."""
    return isinstance(name, str) and not name.startswith('/') and '\\' not in name and '..' not in name.split('/') and name.endswith('.png')


def deliverable_tile_problems(man):
    """F3 (visual_qa v4.5): the delivered workbook's manifest has a tiles block, every page has a non-empty tiles list of
    complete entries, and the block's count is their total."""
    if man is None:
        return []
    tb, imgs = man.get('tiles'), man.get('images') or []
    if not isinstance(tb, dict):
        return ['DELIVERED_TILES_MISSING']
    out = []
    if any(not isinstance(i.get('tiles'), list) or not i['tiles'] for i in imgs):
        out.append('DELIVERED_PAGE_WITHOUT_TILES')
    if any(not isinstance(t_, dict) or set(TILE_KEYS) - set(t_) or not tile_file_ok(t_.get('file')) or not is_sha(t_.get('sha256'))
           for i in imgs for t_ in (i.get('tiles') if isinstance(i.get('tiles'), list) else [])):
        out.append('DELIVERED_TILE_ENTRY_INVALID')
    if tb.get('count') != sum(len(i.get('tiles') or []) for i in imgs if isinstance(i.get('tiles'), list)):
        out.append('DELIVERED_TILES_COUNT_MISMATCH')
    if not isinstance(tb.get('legibility_bound_exceeded'), bool):
        out.append('DELIVERED_TILES_LEGIBILITY_FLAG_MISSING')
    return out


def legibility_bound_exceeded(man):
    """F3: true unless the delivered manifest says its total A:Q width lies within the legibility bound."""
    tb = (man or {}).get('tiles')
    return not (isinstance(tb, dict) and tb.get('legibility_bound_exceeded') is False)


def tiles_summary(man):
    tb = (man or {}).get('tiles')
    return ({k: tb.get(k) for k in ('count', 'total_width', 'glyph_px_min_page_median', 'legibility_bound_exceeded')}
            if isinstance(tb, dict) else None)


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
        tiles = {str(i['page']): [{'image': str(man_p.parent / x['file']), 'sha256': x.get('sha256'), 'x': x.get('x'), 'y': x.get('y'),
                                   'width_px': x.get('width_px'), 'height_px': x.get('height_px')} for x in i.get('tiles') or []]
                 for i in man['images']} if key == 'deliverable' else {}
        out['workbooks'][key] = {
            'manifest': jd.rel(man_p), 'manifest_sha256': sha_file(man_p), 'saved_xlsx_sha256': man['saved_xlsx']['sha256'],
            'pages_total': len(allp), 'selected': [int(p) for p in selected], 'selection': why,
            'pages': {p: dict({'image': imgs[p], 'role': roles_label[p], 'review_sheet_page': review_index.get(p)},
                              **({'tiles': tiles.get(p, [])} if key == 'deliverable' else {})) for p in allp},
            **({'tiles': tiles_summary(man)} if key == 'deliverable' else {}),
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
            tl = e.get('tiles') or []
            lines.append(f'- page {p} ({role}): `{e["image"]}`' + (f' (the overview; read its {len(tl)} tiles below)' if tl else ''))
            for k, x in enumerate(tl, start=1):          # F3: every tile of every delivered page, by absolute path
                lines.append(f'  - page {p}, tile {k} of {len(tl)} (x {x["x"]}, y {x["y"]}, {x["width_px"]} x {x["height_px"]} px): `{x["image"]}`')
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
    jd = open_job(a.job_dir)
    st = Stage(jd, 'visual-record', a)
    return run_stage(jd, st, lambda: visual_record_body(st, jd, a), preflight=lambda: visual_record_pre(st, jd, a),
                     on_refused=lambda: save_review_attempt(st, jd))


def finish_entry(jd):
    d = jd.done('finish')
    return d[-1] if d else None


def save_review_attempt(st, jd):
    """N2: a refused review keeps its bytes: qa/visual_review_attempts/<seq>.json (read-only), pinned in the refused entry."""
    raw = getattr(st, 'attempt_raw', None)
    if raw is None:
        return
    d = jd.p('qa', 'visual_review_attempts')
    d.mkdir(exist_ok=True)
    p = d / f'{st.seq:02d}.json'
    write_new(p, raw)
    st.pin_in('review_attempt', p)


def visual_record_pre(st, jd, a):
    jd.require_not_frozen()
    jd.require_stage_open('visual-record')
    fin = finish_entry(jd)
    if fin is None or not str(fin['next']).startswith('VISUAL_REVIEW'):
        raise Refused('VISUAL_REVIEW_NOT_OPEN', 'finish did not end with NEXT: VISUAL_REVIEW')
    rel = jd.release()
    check_release_static(rel, jd.rec['qualification'], st, jd.admission())
    st.facts['writer_admission_live'] = writer_admission_live(rel, jd.admission())           # E2: still admitted and pinned
    p = Path(a.review)
    if not p.is_absolute() or not p.is_file():
        raise Refused('REVIEW_REQUIRED', 'an absolute path to VISUAL_REVIEW.json')
    expected = jd.p('qa', 'visual_review', 'VISUAL_REVIEW.json')
    if os.path.realpath(p) != str(expected) or not regular(expected):           # N3: one fixed location
        raise Refused('REVIEW_PATH', 'the reviewer writes qa/visual_review/VISUAL_REVIEW.json')
    raw = expected.read_bytes()
    st.attempt_raw = raw
    st.inputs['review_original'] = {'path': str(p), 'sha256': sha_bytes(raw), 'bytes': len(raw)}
    if a.reviewer_conversation_id is not None and not attested(a.reviewer_conversation_id):
        raise Refused('REVIEWER_CONVERSATION_ID_REQUIRED', 'a non-empty --reviewer-conversation-id, not a template placeholder')
    pages = read_json(jd.pinned_file('qa/VISUAL_PAGES.json', fin['outputs']['visual_pages']['sha256']), 'VISUAL_PAGES.json')
    saved = read_json(jd.pinned_file('qa/SAVED_QA.json', fin['outputs']['saved_qa']['sha256']), 'SAVED_QA.json')
    mans = {}
    # each manifest unchanged since finish, and its saved_xlsx.sha256 equal to the matching SAVED_QA.json hash
    for key, want in (('deliverable', saved['deliverable_xlsx']['sha256']), ('internal', saved['xlsx']['sha256'])):
        o = fin['outputs']['visual_manifest_' + key]
        mp = jd.pinned_file(o['path'], o['sha256'])
        man = read_json(mp, 'visual manifest')
        if man['saved_xlsx']['sha256'] != want:
            raise Refused('MANIFEST_SAVED_XLSX_MISMATCH', {'workbook': key})
        mans[key] = (man, mp)
    review = strict_json(raw, 'visual review')
    problems, fails = check_review(review, pages, a.reviewer_conversation_id)
    reviewer_fail = isinstance(review, dict) and review.get('overall') == 'FAIL'
    if problems and not fails and not reviewer_fail:
        if any(x in problems for x in ('reviewer.kind', 'reviewer.model', 'reviewer.effort')):
            raise Refused('REVIEW_NOT_FRESH_CONTEXT', {'required': {'reviewer.kind': REVIEWER_KIND, 'reviewer.model': 'non-empty',
                                                                    'reviewer.effort': 'non-empty'}})
        if any(x.startswith('reviewer.conversation_id') for x in problems):
            raise Refused('REVIEWER_CONVERSATION_ID_REQUIRED', 'reviewer.conversation_id in the review, or --reviewer-conversation-id '
                          '(the operator attests the review ran in that new conversation); both, when given, must be equal')
        raise Refused('REVIEW_INCOMPLETE', {'problems': problems[:20], 'problem_count': len(problems)})
    return {'raw': raw, 'problems': problems, 'fails': fails, 'review': review, 'pages': pages, 'manifests': mans}


def check_review(review, pages, conversation_id=None):
    """Every selected page and every checklist item present, results pass/fail/n/a, n/a only where an item does not
    apply; a fresh-context reviewer (R6) with a conversation id; every listed cut cell judged, and item 8 not n/a on every
    delivered page when cut cells exist (R7); a non-empty failures list is a failure (N4)."""
    problems, fails = [], []
    if not isinstance(review, dict) or review.get('schema') != REVIEW_SCHEMA:
        return ['schema'], fails
    rv = review.get('reviewer')
    rv = rv if isinstance(rv, dict) else {}
    if rv.get('kind') != REVIEWER_KIND:
        problems.append('reviewer.kind')
    problems += ['reviewer.' + k for k in ('model', 'effort') if not attested(rv.get(k))]
    conv = rv.get('conversation_id')
    if conv is not None and not attested(conv):                 # DN14: a copied "<only if your platform shows it>" too
        problems.append('reviewer.conversation_id')
    elif conv is None and conversation_id is None:
        problems.append('reviewer.conversation_id')
    elif conv is not None and conversation_id is not None and conv != conversation_id:
        problems.append('reviewer.conversation_id differs from --reviewer-conversation-id')
    if review.get('overall') not in ('PASS', 'FAIL'):
        problems.append('overall')
    fl = review.get('failures')
    if not isinstance(fl, list) or not all(isinstance(x, str) for x in fl):
        problems.append('failures')
    elif fl:
        fails += [f'reviewer failures list: {len(fl)} entries']
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
        item8 = []
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
                if it == '8':
                    item8.append(r)
            extra = sorted(set(items) - set(ITEMS))
            if extra:
                problems.append(f'{key}: page {pg} unknown items')
        if key == 'deliverable':
            cut = sel.get('possibly_cut_cells') or {}
            if (cut.get('count') or 0) > 0 and item8 and all(r == 'n/a' for r in item8):
                problems.append('deliverable: item 8 is n/a on every page although possibly_cut_cells lists cells')
            listed = sorted({c.get('cell') for c in cut.get('cells') or [] if c.get('cell')})
            cc = wb.get('cut_cells', {} if not listed else None)
            if not isinstance(cc, dict):
                problems.append('deliverable: cut_cells')
            else:
                if sorted(cc) != listed:
                    problems.append('deliverable: cut_cells keys are not the listed possibly_cut_cells')
                for cell in listed:
                    e = cc.get(cell)
                    r = e.get('result') if isinstance(e, dict) else None
                    if r not in ('pass', 'fail'):
                        problems.append(f'deliverable: cut cell {cell}')
                    elif r == 'fail':
                        fails.append(f'deliverable cut cell {cell}')
    return problems, fails


def na_allowed(key, role, item):
    if key == 'deliverable':
        return item == '8'                                    # no possibly_cut_cells cell on the page
    if item in ('1', '6', '7'):
        return role != 'main'                                 # main-sheet items
    if item == '8':
        return role != 'review'                               # review-sheet JSON text
    return False


def page_image_problems(mans):
    """R8: every page image both manifests list (the pages the reviewer opened among them), and every tile of a delivered
    page (F3), unchanged since finish."""
    bad = []
    for key, (man, mp) in mans.items():
        for img in man.get('images') or []:
            f = Path(mp).parent / str(img.get('file'))
            if not regular(f) or os.lstat(f).st_size != img.get('bytes') or sha_file(f) != img.get('sha256'):
                bad.append(f'{key} page {img.get("page")}')
            for k, t_ in enumerate(img.get('tiles') or [], start=1):
                tf = Path(mp).parent / str(t_.get('file'))
                if (not tile_file_ok(t_.get('file')) or not inside(tf, Path(mp).parent) or not regular(tf)
                        or os.lstat(tf).st_size != t_.get('bytes') or sha_file(tf) != t_.get('sha256')):
                    bad.append(f'{key} page {img.get("page")} tile {k}')
    return bad


def visual_record_body(st, jd, a):
    pre = st.pre
    frozen = jd.p('qa', 'VISUAL_REVIEW.json')
    freeze_copy(pre['raw'], frozen)
    st.pin_in('visual_review', frozen)
    bad = page_image_problems(pre['manifests'])
    st.facts['page_images_match_manifests'] = not bad
    if bad:
        st.codes += ['PAGE_IMAGE_CHANGED'] + bad[:20]
        raise Outcome('VISUAL_PAGES_CHANGED', 'STOP_VISUAL_PAGES_CHANGED')
    review = pre['review'] if isinstance(pre['review'], dict) else {}
    if legibility_bound_exceeded(pre['manifests']['deliverable'][0]):        # F3: an unreadable sheet cannot be judged
        pre['fails'] = pre['fails'] + ['deliverable: tiles.legibility_bound_exceeded (an unreadable sheet cannot be judged)']
    result = 'FAIL' if (pre['fails'] or review.get('overall') == 'FAIL') else 'PASS'
    inconsistent = (review.get('overall') == 'PASS') != (result == 'PASS')
    rv = review.get('reviewer') if isinstance(review.get('reviewer'), dict) else {}
    conv = rv.get('conversation_id') or a.reviewer_conversation_id
    rec = {'schema': 'cps.visual-record.v1', 'case_id': jd.rec['case_id'], 'recorded_utc': utc(), 'result': result,
           'review_sha256': sha_bytes(pre['raw']), 'reviewer': review.get('reviewer'), 'reviewer_overall': review.get('overall'),
           'reviewer_conversation_id': conv,
           'reviewer_conversation_id_source': 'review' if rv.get('conversation_id') else 'operator (--reviewer-conversation-id)',
           'fresh_context': 'attested by the operator: the runner cannot see the conversation; it checks the recorded kind, model, '
                            'effort and conversation id',
           'overall_consistent_with_items': not inconsistent, 'failed_items': pre['fails'], 'structural_problems': pre['problems'],
           'pages_reviewed': {k: len((review.get(k) or {}).get('pages') or {}) for k in ('deliverable', 'internal')},
           'pages_selected': {k: len(v['selected']) for k, v in pre['pages']['workbooks'].items()},
           'manifests_match_saved_qa': True, 'page_images_match_manifests': True}
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
    jd = open_job(a.job_dir)
    st = Stage(jd, 'deliver-check', a)
    return run_stage(jd, st, lambda: deliver_body(st, jd), preflight=lambda: deliver_pre(st, jd))


def deliver_pre(st, jd):
    jd.require_not_frozen()
    jd.require_stage_open('deliver-check')
    if jd.rec['qualification']:
        raise Refused('DELIVERY_NOT_FOR_QUALIFICATION', 'qualification outputs are frozen, never delivered')
    rel = jd.release()
    if rel.status != 'RELEASED_FOR_USE':
        raise Refused('RELEASE_STATUS', {'status': rel.status, 'required': 'RELEASED_FOR_USE'})
    vr = jd.done('visual-record')
    if not vr or vr[-1]['result'] != 'VISUAL_REVIEW_PASS':
        raise Refused('VISUAL_REVIEW_NOT_PASSED')
    check_release_static(rel, False, st, None)
    st.facts['live_release'] = check_live_release(jd)          # R9: a withdrawn release never delivers
    st.facts['writer_admission_live'] = writer_admission_live(rel)   # E2: nor does a withdrawn or edited writer admission
    fin = finish_entry(jd)
    saved = read_json(jd.pinned_file('qa/SAVED_QA.json', fin['outputs']['saved_qa']['sha256']), 'SAVED_QA.json')
    evd = read_json(jd.pinned_file('qa/QA_EVIDENCE.json', fin['outputs']['qa_evidence']['sha256']), 'QA_EVIDENCE.json')
    vrec = read_json(jd.pinned_file('qa/VISUAL_RECORD.json', vr[-1]['outputs']['visual_record']['sha256']), 'VISUAL_RECORD.json')
    return {'fin': fin, 'saved': saved, 'evd': evd, 'vrec': vrec}


def delivery_file_checks(f, want):
    """Condition 9: a regular file (not a symbolic link, one hard link) whose sha256 equals the saved-QA hash."""
    try:
        ls = os.lstat(f)
        reg, link, nlink = stat.S_ISREG(ls.st_mode), stat.S_ISLNK(ls.st_mode), ls.st_nlink
    except FileNotFoundError:
        reg, link, nlink = False, False, None
    got = sha_file(f) if reg else None
    return ({'regular_file': reg, 'not_symlink': not link, 'single_link': nlink == 1, 'sha256_equals_saved_qa': got == want},
            got, nlink)


def delivery_name_checks(name, expected_name_sha, internal_name):
    """N7: the delivered file name is a bare name, the one the writer derives from the pinned title (its sha256 recorded
    at prepare), and not the internal workbook's."""
    bare = isinstance(name, str) and name not in ('', '.', '..') and not any(c in name for c in '/\\\0')
    return {'file_name_bare': bare,
            'file_name_is_the_titled_name': isinstance(name, str) and sha_bytes(name.encode('utf-8')) == expected_name_sha,
            'file_name_not_internal_workbook': isinstance(name, str) and name != internal_name and name != 'INTERNAL_QA_WORKBOOK.xlsx'}


def deliver_body(st, jd):
    pre = st.pre
    saved, evd, vrec = pre['saved'], pre['evd'], pre['vrec']
    want = saved['deliverable_xlsx']['sha256']
    name = saved['deliverable_xlsx']['file']
    names = delivery_name_checks(name, jd.rec.get('deliverable_file_name_sha256'), (saved.get('xlsx') or {}).get('file'))
    f = jd.p('export', 'writer', name if names['file_name_bare'] else 'INVALID_NAME')
    checks, got, nlink = delivery_file_checks(f, want)
    checks.update(names)
    checks.update(bytes_differ_from_internal_workbook=got is not None and got != (saved.get('xlsx') or {}).get('sha256'),
                  saved_qa_evidence_grade=evd.get('evidence_grade') is True, visual_review_pass=vrec.get('result') == 'PASS')
    ok = all(checks.values())
    doc = {'schema': 'cps.delivery-check.v1', 'case_id': jd.rec['case_id'], 'checked_utc': utc(), 'condition': 9,
           'file': str(f), 'sha256': got, 'saved_qa_deliverable_xlsx_sha256': want, 'st_nlink': nlink, 'checks': checks,
           'live_release': st.facts.get('live_release'), 'result': 'DELIVERABLE' if ok else 'DO_NOT_DELIVER'}
    write_new(jd.p('qa', 'DELIVERY_CHECK.json'), dumps(doc))
    st.pin_out('delivery_check', jd.p('qa', 'DELIVERY_CHECK.json'))
    st.facts['delivery'] = {'checks': checks, 'sha256': got}
    if not ok:
        st.codes += [k for k, v in checks.items() if not v]
        raise Outcome('DELIVERY_CHECK_FAILED', 'STOP_DELIVERY_CHECK_FAILED')
    return 'DELIVERABLE', f'DELIVER file={f}'


# ------------------------------------------------------------------ freeze, verify-frozen
def cmd_freeze(a):
    jd = open_job(a.job_dir)
    last = [s for s in jd.rec['stages'] if s['completed']]
    if last and last[-1]['stage'] == 'freeze' and last[-1]['result'] == 'FROZEN' and not jd.p('FROZEN.json').exists():
        return finish_freeze(jd, completing=True)           # N12: an earlier freeze recorded its entry but not FROZEN.json
    st = Stage(jd, 'freeze', a)

    def pre():
        jd.require_not_frozen(reapply_modes=True)
        if not jd.rec['stages']:
            raise Refused('NOTHING_TO_FREEZE')
    return run_stage(jd, st, lambda: freeze_body(st, jd), preflight=pre)


def freeze_body(st, jd):
    last = [s for s in jd.rec['stages'] if s['completed']]
    st.facts['final_stage'] = {'stage': last[-1]['stage'], 'result': last[-1]['result']} if last else None
    st.facts['note'] = 'FROZEN.json lists every file and folder of the job folder with this record entry included; never touch the folder again'
    return 'FROZEN', 'DONE'


def frozen_doc(jd):
    fz = jd.done('freeze')[-1]
    t = tree(jd.dir)
    files = [{'path': k, 'bytes': v['bytes'], 'sha256': v['sha256']} for k, v in sorted(t['files'].items())
             if k not in ('FROZEN.json', '.FROZEN.json.tmp')]
    return {'schema': FROZEN_SCHEMA, 'case_id': jd.rec['case_id'], 'reader': jd.rec['reader'], 'qualification': jd.rec['qualification'],
            'ledger': jd.rec.get('ledger'), 'frozen_utc': fz['ended_utc'], 'freeze_seq': fz['seq'],
            'run_record_sha256': sha_file(jd.record_path), 'files': files, 'directories': t['dirs'], 'other_entries': t['other'],
            'retry_permitted': False, 'repair_permitted': False}


def transcript_summary(jd):
    """D3 (O40, "the report states how many runs had transcripts"): the frozen generation record's transcript status and
    whether the transcript file was frozen, carried in the ledger's freeze entry; None when no record was frozen."""
    fr = jd.done('freeze_response')
    g = (fr[-1]['facts'].get('generation_record') if fr else None) or None
    return None if g is None else {'transcript_status': g.get('transcript_status'), 'transcript_file_frozen': g.get('transcript_file_frozen')}


def finish_freeze(jd, completing=False, extra=None):
    """R3: FROZEN.json (deterministic: a later freeze recomputes the same bytes), its sha256 in the ledger (qualification)
    before the file is written, then every file and folder read-only, bottom-up, the job folder last."""
    try:
        doc = frozen_doc(jd)
        b = dumps(doc)
        fsha = sha_bytes(b)
        if jd.ledger_path is not None:
            with Ledger(jd.ledger_path, create=False) as led:
                prior = led.of('freeze', job_dir=str(jd.dir))
                if prior and prior[-1]['frozen_sha256'] != fsha:
                    raise Refused('FROZEN_LEDGER_MISMATCH', 'the folder differs from the one the ledger recorded as frozen')
                if not prior:
                    led.append({'type': 'freeze', 'job_dir': str(jd.dir), 'case_id': jd.rec['case_id'], 'reader': jd.rec['reader'],
                                'frozen_sha256': fsha, 'final_stage': jd.done('freeze')[-1]['facts'].get('final_stage'),
                                'run_record_sha256': doc['run_record_sha256'], 'files': len(doc['files']),
                                'status': jd.rec.get('status'), 'transcript': transcript_summary(jd)})
        tmp = jd.p('.FROZEN.json.tmp')
        if tmp.exists():
            tmp.unlink()
        write_new(tmp, b)
        os.replace(tmp, jd.p('FROZEN.json'))
        make_tree_readonly(jd.dir)
    except (Refused, OSError) as e:
        code = getattr(e, 'code', type(e).__name__)
        print(json.dumps({'stage': 'freeze', 'result': 'FREEZE_INCOMPLETE', 'codes': [code], 'values_printed': False}))
        print('NEXT: STOP_FREEZE_INCOMPLETE')
        return EXIT_STOP
    out = {'stage': 'freeze', 'result': 'FROZEN', 'codes': [], 'run_record_sha256': doc['run_record_sha256'],
           'frozen_sha256': fsha, 'files': len(doc['files']), 'values_printed': False}
    out.update(extra or {})
    if completing:
        out['completed_frozen_json_of_the_recorded_freeze'] = True
    print(json.dumps(out, ensure_ascii=False))
    print('NEXT: DONE')
    return EXIT_CONTINUE


def verify_frozen(jd):
    """R3: recompute every entry of the job folder against FROZEN.json (unlisted, changed and missing files and folders)."""
    p = jd.p('FROZEN.json')
    try:
        fz = strict_json(p.read_bytes(), 'FROZEN.json')
    except (OSError, Refused):
        return {'intact': False, 'unlisted': [], 'changed': [], 'missing': ['FROZEN.json'], 'fz': None, 'writable': 0}
    t = tree(jd.dir)
    have = {k: v['sha256'] for k, v in t['files'].items() if k != 'FROZEN.json'}
    listed = {x['path']: x['sha256'] for x in fz.get('files') or []}
    unlisted = sorted(set(have) - set(listed)) + sorted(set(t['dirs']) - set(fz.get('directories') or [])) + \
        sorted(set(t['other']) - set(fz.get('other_entries') or []))
    changed = sorted(k for k in set(have) & set(listed) if have[k] != listed[k])
    missing = sorted(set(listed) - set(have)) + sorted(set(fz.get('directories') or []) - set(t['dirs']))
    entries = [str(jd.dir)]
    for dp, dns, fns in os.walk(jd.dir):
        entries += [os.path.join(dp, n) for n in dns + fns]
    writable = 0
    for q in entries:
        m = os.lstat(q).st_mode
        if (stat.S_ISREG(m) or stat.S_ISDIR(m)) and stat.S_IMODE(m) & WBITS:
            writable += 1
    return {'intact': not (unlisted or changed or missing), 'unlisted': unlisted, 'changed': changed, 'missing': missing,
            'fz': fz, 'writable': writable}


def cmd_verify_frozen(a):
    jd = Job(a.job_dir)
    jd.lock()
    if not jd.p('FROZEN.json').is_file():
        raise Refused('NOT_FROZEN', 'the job folder has no FROZEN.json')
    try:
        jd.load(readonly=True)                              # DN6: never creates, catches up or writes the ledger
        chain = 'verified'
    except Refused as r:
        chain = r.code
    v = verify_frozen(jd)
    fsha = sha_file(jd.p('FROZEN.json'))
    ledger_ok = None
    fz = v['fz'] or {}
    if fz.get('qualification'):
        try:
            with Ledger(Path(str(fz.get('ledger'))), create=False, readonly=True) as led:
                e = led.of('freeze', job_dir=str(jd.dir))
                ledger_ok = bool(e) and e[-1]['frozen_sha256'] == fsha
        except Refused:
            ledger_ok = False
    record_ok = jd.record_path.is_file() and sha_file(jd.record_path) == fz.get('run_record_sha256')
    ok = v['intact'] and chain == 'verified' and record_ok and ledger_ok is not False
    print(json.dumps({'stage': 'verify-frozen', 'result': 'FROZEN_INTACT' if ok else 'FROZEN_FOLDER_CHANGED', 'frozen_sha256': fsha,
                      'unlisted': len(v['unlisted']), 'changed': len(v['changed']), 'missing': len(v['missing']),
                      'paths': {k: [safe_path(x) for x in v[k][:20]] for k in ('unlisted', 'changed', 'missing')},
                      'record_chain': chain, 'record_matches_frozen': record_ok, 'ledger_freeze_entry_matches': ledger_ok,
                      'writable_entries': v['writable'], 'values_printed': False}, ensure_ascii=False))
    print('NEXT: DONE' if ok else 'NEXT: STOP_FROZEN_FOLDER_CHANGED')
    return EXIT_CONTINUE if ok else EXIT_STOP


# ------------------------------------------------------------------ interrupt (qualification rule 3, D1)
def cmd_interrupt(a):
    jd = open_job(a.job_dir)
    w = written_response(jd) if jd.rec['qualification'] and not jd.frozen() else None
    if w is not None:                                       # E1: refused with nothing appended (record and ledger unchanged)
        return refused(Refused('RESPONSE_WRITTEN', {'file': w, 'note': 'protocol rule 3 restarts only an interruption before the '
                                                    'response is written: go on with the written file (scope-finish or finish)'}))
    st = Stage(jd, 'interrupt', a)
    return run_stage(jd, st, lambda: interrupt_body(st, jd, a), preflight=lambda: interrupt_pre(st, jd, a))


def written_response(jd):
    """E1 (protocol rule 3: "before the response is written"): the file the broken conversation would have written, when it
    exists, for the conversation the last completed stage started: scope/reader/output/SCOPE_READER_RESPONSE.json after
    NEXT: SCOPE_READER, run/<reader>/output/response.json after NEXT: GENERATE. A partly written or unreadable file is a
    written file. None otherwise."""
    done = [x for x in jd.rec['stages'] if x['completed']]
    nxt = done[-1]['next'] if done else None
    if nxt == 'SCOPE_READER':
        rel_path = 'scope/reader/output/SCOPE_READER_RESPONSE.json'
    elif nxt == 'GENERATE':
        gen = generation_stage(jd)
        rel_path = ((gen or {}).get('facts', {}).get('generation') or {}).get('response_path') or f'run/{jd.rec["reader"]}/output/response.json'
    else:
        return None
    return rel_path if os.path.lexists(jd.p(rel_path)) else None


def restart_used_here(jd):
    """Rule 3 limit: why this folder's case and reader have used their one technical restart, or None: the folder is
    itself a folder restart (restart_of), or it records an in-place restart (an interrupt that printed NEXT: GENERATE)."""
    if jd.rec.get('restart_of'):
        return 'this folder is the restart of an earlier run'
    if any(x['stage'] == 'interrupt' and x['completed'] and x['next'] == 'GENERATE' for x in jd.rec['stages']):
        return 'this folder was already restarted in place'
    return None


def interrupt_pre(st, jd, a):
    """D1 and the in-place restart (protocol rule 3: "A technical interruption before the response is written may be
    restarted once"), qualification only, at most one technical restart per case and reader in either form:
    - restart in a new folder: the last completed stage printed NEXT: GENERATE or NEXT: SCOPE_READER and no scope reader
      or generator response is frozen (no freeze_response entry, none of RESPONSE_WITNESSES in the folder);
    - restart in place: the last completed stage printed NEXT: GENERATE after scope-finish froze the scope reader's
      response and agreed the scope, and no generator response is frozen.
    The operator attests the broken conversation's id (optional) and times."""
    jd.require_not_frozen()
    if not jd.rec['qualification']:
        raise Refused('INTERRUPT_QUALIFICATION_ONLY', 'a technical interruption is recorded for qualification jobs (protocol rule 3)')
    used = restart_used_here(jd)
    if used:
        raise Refused('INTERRUPT_RESTART_USED', {'reason': used, 'note': 'at most one technical restart per case and reader: '
                                                 'freeze the run as it is (a failed run) and tell the owner'})
    jd.require_stage_open('interrupt')
    done = [x for x in jd.rec['stages'] if x['completed']]
    last = done[-1] if done else None
    if last is None or last['next'] not in ('GENERATE', 'SCOPE_READER'):
        raise Refused('INTERRUPT_NOT_ALLOWED', {'reason': 'the last completed stage did not print NEXT: GENERATE or NEXT: SCOPE_READER',
                                                'last_completed_stage': (last or {}).get('stage'), 'next': (last or {}).get('next')})
    gen_frozen = [w for w in RESPONSE_WITNESSES if w.startswith('response/') and os.path.lexists(jd.p(w))]
    if jd.stages('freeze_response') or gen_frozen:
        raise Refused('INTERRUPT_NOT_ALLOWED', {'reason': 'a generator response is frozen', 'frozen': gen_frozen})
    in_place = os.path.lexists(jd.p('scope', 'SCOPE_READER_RESPONSE.json'))
    if in_place:
        sf = jd.done('scope-finish')
        if last['next'] != 'GENERATE' or not sf or sf[-1]['next'] != 'GENERATE':
            raise Refused('INTERRUPT_NOT_ALLOWED', {'reason': 'a scope reader response is frozen but scope-finish did not agree '
                                                    'the scope and print NEXT: GENERATE', 'frozen': ['scope/SCOPE_READER_RESPONSE.json']})
        if os.path.lexists(jd.p('interrupted')):
            raise Refused('INTERRUPT_NOT_ALLOWED', {'reason': 'interrupted/ exists: the set-aside folder of an in-place restart'})
    if not isinstance(a.reason, str) or not TECHNICAL_RE.fullmatch(a.reason):
        raise Refused('INTERRUPT_REASON', 'an upper-case code TECHNICAL_<CODE>, for example TECHNICAL_CONVERSATION_BROKE')
    if a.conversation_id is not None and not attested(a.conversation_id):
        raise Refused('INTERRUPT_CONVERSATION_ID', 'a non-blank conversation id or link, not a template placeholder')
    t0, t1, lo, hi = parse_utc(a.started_utc), parse_utc(a.ended_utc), parse_utc(last['ended_utc']), parse_utc(st.started)
    if t0 is None or t1 is None or not (lo <= t0 <= t1 <= hi):
        raise Refused('INTERRUPTION_TIMES', '--started-utc and --ended-utc (ISO 8601 with Z) lie between the end of the stage '
                      'that printed NEXT: ' + last['next'] + ' and the start of this command')
    rel = jd.release()
    check_release_static(rel, True, st, jd.admission())
    return {'last': last, 'window': (lo, hi), 'times': (t0, t1), 'in_place': in_place, 'rel': rel}


def interrupt_body(st, jd, a):
    last, (lo, hi), (t0, t1), in_place = st.pre['last'], st.pre['window'], st.pre['times'], st.pre['in_place']
    role = 'scope_reader' if last['next'] == 'SCOPE_READER' else 'generator'
    gen = generation_stage(jd) if role == 'generator' else None
    out_dir = jd.p('scope', 'reader', 'output') if role == 'scope_reader' else \
        jd.p((gen['facts'].get('generation') or {}).get('run_dir') or ('run/' + jd.rec['reader']), 'output')
    t = tree(out_dir)
    listing = {k: v['sha256'] for k, v in sorted(t['files'].items())} if t else None
    st.codes.append(a.reason)
    st.facts['interruption'] = {
        'protocol_rule': 3, 'reason': a.reason, 'conversation_role': role,
        'restart': 'in_place' if in_place else 'new_folder_after_freeze',
        'after_stage': {'stage': last['stage'], 'seq': last['seq'], 'next': last['next']},
        'conversation_id_attested_by_operator': a.conversation_id, 'started_utc': a.started_utc, 'ended_utc': a.ended_utc,
        'times_within_bounds': True, 'conversation_seconds': round((t1 - t0).total_seconds(), 1),
        'window_seconds': round((hi - lo).total_seconds(), 1), 'response_frozen': False,
        'output_folder': jd.rel(out_dir), 'output_files': listing,
        'response_file_present': bool(listing) and ('response.json' in listing or 'SCOPE_READER_RESPONSE.json' in listing),
        'note': ('attested by the operator: the runner cannot see the conversation; ' + (
            'the scope is agreed and frozen, so this folder allows one more generator conversation on the same pinned run '
            'inputs and scope decision (the restart of this case and reader)' if in_place else
            'freeze the folder, then one restart in a new folder is allowed'))}
    if not in_place:
        raise Outcome('TECHNICAL_INTERRUPTION', 'STOP_TECHNICAL_INTERRUPTION')
    # in place: the generation run is exactly as pinned by scope-finish; the broken conversation's output is set aside
    icodes, _, _ = run_folder_problems(jd, st.pre['rel'], gen)
    pcodes = packet_pins_problems(jd, gen)
    prompt = jd.p('run', 'GENERATOR_PROMPT.md')
    if not regular(prompt) or sha_file(prompt) != gen['outputs']['generator_prompt']['sha256']:
        icodes.append('GENERATOR_PROMPT_CHANGED')
    if icodes or pcodes:
        st.codes += icodes + pcodes
        raise Outcome('RUN_INPUTS_CHANGED', 'STOP_RUN_INPUTS_CHANGED')
    aside = jd.p('interrupted', 'generator_output')
    aside.parent.mkdir()
    os.rename(out_dir, aside)
    out_dir.mkdir()
    make_tree_readonly(aside.parent)
    st.facts['interruption']['set_aside'] = {'folder': jd.rel(aside), 'files': tree_shas(aside)}
    st.facts['generation'] = dict(gen['facts']['generation'], pinned_by={'stage': gen['stage'], 'seq': gen['seq']})
    run_dir = jd.p(gen['facts']['generation']['run_dir'])
    return 'TECHNICAL_INTERRUPTION', f'GENERATE prompt={prompt} folder={run_dir}'


# ------------------------------------------------------------------ nonattempt (qualification rule 6, R11, D2)
def cmd_nonattempt(a):
    """D2: only a case the pinned JOBS.json marks nonattempt; the reason is JOBS.json's (protocol rule 6's
    NONATTEMPT_SOURCE_UNAVAILABLE when it names none), and --reason, when given, must equal it. The runner writes and
    freezes at once a nonattempt folder <jobs-root>/<case id>: input/ (the release, the admission and JOBS.json), a
    RUN_RECORD.json whose status is the reason, and FROZEN.json, its sha256 in the ledger (ALL_FROZEN.json lists it like
    any run folder)."""
    for k in ('release', 'admission'):
        if not Path(getattr(a, k)).is_absolute():
            raise Refused('ABSOLUTE_PATH_REQUIRED', {'argument': '--' + k})
    if a.jobs_root is not None and not Path(a.jobs_root).is_absolute():
        raise Refused('ABSOLUTE_PATH_REQUIRED', {'argument': '--jobs-root'})
    if a.reader not in ('A', 'B'):
        raise Refused('READER', 'A or B')
    if a.reason is not None and not REASON_RE.fullmatch(a.reason):
        raise Refused('NONATTEMPT_REASON', 'an upper-case code such as NONATTEMPT_SOURCE_UNAVAILABLE, or omit --reason')
    rel_raw = Path(a.release).read_bytes()
    rel = Release(rel_raw, a.release)
    adm_raw = Path(a.admission).read_bytes()
    adm = parse_admission(adm_raw)
    probe = Stage(Job(Path(a.release).parent / '_'), 'nonattempt', a)
    check_release_static(rel, True, probe, adm)
    if not rel.admission_listed(a.admission, adm_raw):
        raise Refused('ADMISSION_NOT_RELEASED', 'the release qualification.admissions must list this admission file by path and sha256')
    frozen_at = parse_utc(adm.get('frozen_utc'))
    if frozen_at is None:
        raise Refused('ADMISSION_FROZEN_UTC')
    if frozen_at >= datetime.datetime.now(datetime.timezone.utc):
        raise Refused('ADMISSION_NOT_FROZEN_BEFORE_PREPARE')
    rel.require_qualification_fields()
    jobs, jobs_sha, jobs_raw = load_jobs(rel, adm)
    c = jobs.get(a.case)
    if c is None:
        raise Refused('QUALIFICATION_CASE_NOT_IN_JOBS', 'the case is not listed in the pinned JOBS.json')
    if c.get('nonattempt') is not True:
        raise Refused('QUALIFICATION_CASE_NOT_NONATTEMPT', 'the pinned JOBS.json does not mark this case nonattempt: run it')
    reason = c.get('reason') or NONATTEMPT_DEFAULT_REASON
    source = 'JOBS.json' if c.get('reason') else 'protocol rule 6 (JOBS.json names no reason)'
    if a.reason is not None and a.reason != reason:
        raise Refused('NONATTEMPT_REASON_MISMATCH', '--reason differs from the reason JOBS.json gives; omit --reason')
    jobs_root = Path(a.jobs_root).resolve() if a.jobs_root else rel.ledger.parent / ('nonattempts_' + a.reader)
    if any(ch.isspace() for ch in str(jobs_root)):
        raise Refused('JOBS_ROOT_WHITESPACE', 'printed paths must not contain whitespace')
    if inside(jobs_root, rel.root):
        raise Refused('JOBS_ROOT_IN_REPOSITORY', 'the jobs root must be outside repository.root')
    for label, pth in (('--admission', a.admission), ('qualification.ledger', rel.ledger), ('qualification.jobs_file', rel.jobs_file)):
        if inside(pth, rel.root):
            raise Refused('JOB_INPUT_IN_REPOSITORY', {'input': label})
    if inside(rel.ledger, jobs_root):
        raise Refused('QUALIFICATION_LEDGER_PATH', 'the ledger lies outside the jobs root and every job folder')
    jd = Job(jobs_root / a.case)
    if jd.dir.exists():
        raise Refused('JOB_DIR_EXISTS', 'a job folder is used once')
    rec = {'schema': RECORD_SCHEMA, 'runner': {'version': VERSION, 'sha256': sha_file(__file__)}, 'case_id': a.case,
           'reader': a.reader, 'qualification': True, 'created_utc': utc(), 'status': reason,
           'nonattempt': {'protocol_rule': 6, 'reason': reason, 'reason_source': source, 'jobs_sha256': jobs_sha,
                          'jobs_order': c.get('order')},
           'release': dict(rel.summary(), path=os.path.abspath(a.release)), 'job_inputs': None,
           'deliverable_file_name_sha256': None, 'admission': {'sha256': sha_bytes(adm_raw), 'frozen_utc': adm.get('frozen_utc')},
           'restart_of': None, 'ledger': str(rel.ledger), 'user_options': 'none: the runner takes no per-user options',
           'operator_model': a.operator_model, 'stages': []}
    with Ledger(rel.ledger, create=True) as led:
        if led.of('prepare', case_id=a.case, reader=a.reader):
            raise Refused('QUALIFICATION_RUN_EXISTS', 'this case and reader already have a run')
        if led.of('nonattempt', case_id=a.case, reader=a.reader):
            raise Refused('QUALIFICATION_NONATTEMPT_RECORDED')
        if any(e.get('job_dir') == str(jd.dir) for e in led.entries):
            raise Refused('QUALIFICATION_JOB_DIR_REUSED')
        ledger_admission_order(led, adm)
        jobs_root.mkdir(parents=True, exist_ok=True)
        make_nonattempt_folder(jd, rel_raw, adm_raw, jobs_raw, rec)
        e = led.append({'type': 'nonattempt', 'case_id': a.case, 'reader': a.reader, 'reason': reason, 'reason_source': source,
                        'jobs_root': str(jobs_root), 'job_dir': str(jd.dir), 'admission_sha256': sha_bytes(adm_raw),
                        'release_sha256': rel.sha, 'jobs_sha256': jobs_sha, 'operator_model': a.operator_model,
                        'run_record_sha256': sha_bytes(jd.raw)})
    jd.ledger_path = rel.ledger
    st = Stage(jd, 'nonattempt', a)
    st.facts.update(probe.facts)
    st.tools.update(probe.tools)
    for label, rp in (('release', 'RELEASE.json'), ('admission', 'ADMISSION.json'), ('jobs', 'JOBS.json')):
        st.pin_in(label, jd.p('input', rp))
    st.facts['nonattempt'] = dict(rec['nonattempt'], ledger_seq=e['seq'])
    jd.append(st.entry(reason, 'FREEZE', True))
    fz = Stage(jd, 'freeze', a)
    fz.facts = {'final_stage': {'stage': 'nonattempt', 'result': reason},
                'note': 'a nonattempt is frozen at once (protocol rule 6); never touch the folder again'}
    jd.append(fz.entry('FROZEN', 'DONE', True))
    return finish_freeze(jd, extra={'stage': 'nonattempt', 'result': 'NONATTEMPT_FROZEN', 'status': reason,
                                    'nonattempt_ledger_seq': e['seq']})


def make_nonattempt_folder(jd, rel_raw, adm_raw, jobs_raw, rec):
    try:
        jd.dir.mkdir()
    except FileExistsError:
        raise Refused('JOB_DIR_EXISTS', 'a job folder is used once')
    jd.lock(wait=True)
    jd.p('input').mkdir()
    write_new(jd.p('input', 'RELEASE.json'), rel_raw)
    write_new(jd.p('input', 'ADMISSION.json'), adm_raw)
    write_new(jd.p('input', 'JOBS.json'), jobs_raw)
    jd.create(rec)


# ------------------------------------------------------------------ stage wrapper and CLI
def run_stage(jd, st, body, preflight=None, on_refused=None):
    st.pre = None
    consumed = False
    try:
        if preflight is not None:
            st.pre = preflight()
        jd.mark(st)
        consumed = True
        result, nxt = body()
        completed = True
    except Refused as r:
        st.codes.append(r.code)
        if not consumed:
            if on_refused is not None:
                try:
                    on_refused()
                except (Refused, OSError):
                    pass
            if not jd.frozen():                             # a frozen folder is never written again
                try:
                    jd.append(st.entry('REFUSED', None, False))
                except (Refused, OSError):
                    pass
            return refused(r)
        result, nxt, completed = 'REFUSED_AFTER_CONSUMPTION', 'STOP_' + r.code, True     # R4: a recorded stop
    except Outcome as o:
        result, nxt, completed = o.result, o.next_step, True
        st.codes += o.codes
    except Exception as e:                                  # noqa: BLE001 - recorded; the job stops (no retry)
        result, nxt, completed = 'RUNNER_ERROR', 'STOP_RUNNER_ERROR', True
        st.codes.append(type(e).__name__)
        if not jd.frozen():
            try:                                            # N12: the traceback is kept in logs/ (never printed)
                tb = jd.p('logs', f'{st.seq:02d}_{st.name}_RUNNER_ERROR.traceback.txt')
                write_new(tb, traceback.format_exc())
                st.pin_out('runner_error_traceback', tb)
            except OSError:
                pass
        if not consumed:                                    # DN2: nothing was consumed: a refusal, not a completed stop
            r = Refused('RUNNER_ERROR', {'error': type(e).__name__, 'note': 'an unexpected error before the stage began '
                                         'consuming; the traceback is in logs/; fix the cause or tell the owner, then run '
                                         'the same command again'})
            st.codes.insert(0, r.code)
            if not jd.frozen():
                try:
                    jd.append(st.entry('REFUSED', None, False))
                except (Refused, OSError):
                    pass
            return refused(r)
    try:
        jd.append(st.entry(result, nxt.split(' ')[0], completed))
    except (Refused, OSError) as e:                         # the marker stays: the next command records INTERRUPTED
        print(json.dumps({'stage': st.name, 'result': result, 'record_append_failed': getattr(e, 'code', type(e).__name__),
                          'values_printed': False}))
        print('NEXT: STOP_RECORD_CONFLICT')
        return EXIT_STOP
    jd.unmark()
    if st.name == 'freeze' and result == 'FROZEN':
        return finish_freeze(jd)
    out = {'stage': st.name, 'result': result, 'codes': st.codes, 'run_record_sha256': sha_file(jd.record_path), 'values_printed': False}
    if jd.ledger_error:
        out['ledger_append_failed'] = jd.ledger_error
    print(json.dumps(out, ensure_ascii=False))
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
    p.add_argument('--admission', help='qualification only: the admission the release lists, frozen before the first qualification prepare')
    p.add_argument('--operator-model')
    p = sub.add_parser('scope-finish', help='agreement of the scope tool and the scope reader; scoped packet; generation run')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--reader-response', required=True)
    p.add_argument('--reader-conversation-id', help='optional: the scope reader conversation, attested by the operator')
    p.add_argument('--reader-prompt-sha256', help='the sha256 of scope/SCOPE_READER_PROMPT.md, the prompt given to the reader '
                   '(attested by the operator; required for qualification)')
    p.add_argument('--operator-model')
    p = sub.add_parser('finish', help='freeze the generation record and the response; route check and convert; export; saved QA; visual QA')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--response', required=True)
    p.add_argument('--job-title', help='optional: must equal input/JOB_TITLE.json (the title always comes from that file)')
    p.add_argument('--generator-model')
    p.add_argument('--generation-record', help='run/GENERATION_RECORD.json (cps.generation-record.v1); required for qualification')
    p.add_argument('--transcript', help='optional: the exported generator transcript the record names (transcript_status exported)')
    p.add_argument('--operator-model')
    p = sub.add_parser('visual-record', help='record the visual review')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--review', required=True)
    p.add_argument('--reviewer-conversation-id', help='the visual reviewer conversation id or link, attested by the operator '
                   '(required unless the review states reviewer.conversation_id)')
    p.add_argument('--operator-model')
    p = sub.add_parser('deliver-check', help='condition 9 at delivery; prints the one file to deliver')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--operator-model')
    p = sub.add_parser('interrupt', help='qualification: record a technical interruption of the scope reader or generator '
                       'conversation before its file was written (protocol rule 3)')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--reason', required=True, help='TECHNICAL_<CODE>, for example TECHNICAL_CONVERSATION_BROKE')
    p.add_argument('--started-utc', required=True, help='when the broken conversation started (ISO 8601 with Z)')
    p.add_argument('--ended-utc', required=True, help='when it broke (ISO 8601 with Z)')
    p.add_argument('--conversation-id', help='the broken conversation id or link, attested by the operator')
    p.add_argument('--operator-model')
    p = sub.add_parser('freeze', help='write FROZEN.json and make every file and folder of the job read-only')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--operator-model')
    p = sub.add_parser('verify-frozen', help='recompute FROZEN.json against the folder (writes nothing)')
    p.add_argument('--job-dir', required=True)
    p = sub.add_parser('nonattempt', help='qualification: freeze a JOBS.json nonattempt of a case and reader at once')
    p.add_argument('--release', required=True)
    p.add_argument('--admission', required=True)
    p.add_argument('--case', required=True)
    p.add_argument('--reader', required=True)
    p.add_argument('--jobs-root', help='the jobs root of this reader (default: <ledger folder>/nonattempts_<reader>)')
    p.add_argument('--reason', help='optional: must equal the reason JOBS.json gives')
    p.add_argument('--operator-model')
    a = ap.parse_args(argv)
    if hasattr(a, 'job_dir') and not Path(a.job_dir).is_absolute():
        return refused(Refused('ABSOLUTE_PATH_REQUIRED', {'argument': '--job-dir'}))
    fn = {'prepare': cmd_prepare, 'scope-finish': cmd_scope_finish, 'finish': cmd_finish, 'visual-record': cmd_visual_record,
          'deliver-check': cmd_deliver_check, 'interrupt': cmd_interrupt, 'freeze': cmd_freeze,
          'verify-frozen': cmd_verify_frozen, 'nonattempt': cmd_nonattempt}[a.cmd]
    try:
        return fn(a)
    except Refused as r:                    # refused before a job folder could record it
        return refused(r)


if __name__ == '__main__':
    sys.exit(main())
