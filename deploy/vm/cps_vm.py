#!/usr/bin/env python3
"""CPS reset-proof VM helper (G1): save points, notes, restore and the end-of-qualification records for the Dot's VM.

Specification: G1 implementation specification revision 2 (2026-11-09), adopted design
docs/handoff/RESET_PROOF_DESIGN_DRAFT.md, owner decisions O43-O52. Runner v4 (deploy/run/cps_job.py) is imported for
its ledger and record primitives and otherwise always run as a subprocess; it is never changed.

The helper never contacts Drive or the network. It writes files into BASE/outbox and prints exact instructions:
  RESULT: <json>            the machine-readable result (first instruction line)
  BIND=<token>              wrap and package: the checked bind token of the completed runner stage
  UPLOAD <path> -> <Drive folder>
  SAVE_DRIVE_LISTING folder=<Drive folder> to=<path> [name=<file name>]
  DOWNLOAD id=<Drive id> name=<file name> -> <path>
  STATE: key=value ...
  NEXT: <action> / THEN: <action> / OPTION: <CODE> <action>  |  STOP: <CODE> <hint>  |  REFUSED: <CODE>
Exit codes: 0 done, 2 usage, 3 STOP, 4 REFUSED (nothing changed), 10 NEED_DOWNLOADS, 11 IN_PROGRESS.
It never prints cell text, job inputs, the job title or any response content: only names, paths, hashes, counts, codes.

Usage: python3 -I -B deploy/vm/cps_vm.py <subcommand> [options]   (normally through BASE/vm.sh; see deploy/vm/README.md)
Standard library only.
"""
import argparse
import datetime
import fcntl
import gzip
import hashlib
import importlib.util
import io
import json
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

VERSION = 'cps-vm-helper.v1'
HELPER_FILE = Path(os.path.abspath(__file__))
HELPER_REPO = Path(os.path.realpath(Path(os.path.abspath(__file__)).parents[2]))
EXIT_OK, EXIT_USAGE, EXIT_STOP, EXIT_REFUSED, EXIT_NEED, EXIT_BUSY = 0, 2, 3, 4, 10, 11
BOOT_ID_DEFAULT = '/proc/sys/kernel/random/boot_id'
CONFIG_SCHEMA = 'cps.vm-helper-config.v1'
LISTING_SCHEMA = 'cps.vm-drive-listing.v1'
UNREADABLE_FROZEN = "the earlier folder's FROZEN.json cannot be read"
ROLE_STEP = {'S': 'SCOPE_READER', 'G': 'GENERATE', 'V': 'VISUAL_REVIEW'}
STEP_ROLE = {v: k for k, v in ROLE_STEP.items()}
RESPONSE_FILE = {'S': 'SCOPE_READER_RESPONSE.json', 'G': 'response.json', 'V': 'VISUAL_REVIEW.json'}
WRAP_SUBS = ('prepare', 'scope-finish', 'finish', 'visual-record', 'deliver-check', 'interrupt', 'freeze', 'nonattempt')
CONSUMING = {'scope-finish': 'S', 'finish': 'G', 'visual-record': 'V'}
CLASSES = ('NONE_IN_FLIGHT', 'NON_AI_STAGE_LOST', 'AI_NO_CONVERSATION', 'AI_NOTHING_WRITTEN', 'AI_WRITTEN_LOST', 'AI_ARCHIVED')
TOKENS = ('CONVERSATION_ID', 'GENERATOR_MODEL', 'COPY_FILE', 'LOG_FILE', 'PROFILE_FOLDER', 'CASE', 'REASON_TEXT', 'SEEN')
GENESIS_KEYS = ('type', 'ledger_id', 'helper', 'release_sha256', 'admission_sha256', 'jobs_sha256', 'boot_id',
                'fingerprint_sha256', 'base')
QUAL_ROOTS = {'A': 'A', 'B': 'B', 'A-restart1': 'A_restart1', 'B-restart1': 'B_restart1', 'NA-A': 'nonattempts_A',
              'NA-B': 'nonattempts_B'}
ROOT_TAGS = {v: k for k, v in QUAL_ROOTS.items()}
CONFIG_KEYS = {'schema': str, 'drive': dict, 'png_part_bytes': int, 'upload_verification': str, 'link_notes': bool,
               'selftest_expected_tests': int, 'audit_clock_tolerance_seconds': int, 'listing_page_marker': str,
               'sentinels': dict, 'expected_genesis': (str, type(None)), 'confirm_package_before_start': bool,
               'confirm_ai_before_consume': bool, 'transcript_export': bool, 'max_upload_bytes': int,
               'max_review_revisions': int, 'clock_wait_max_seconds': int, 'wrap_foreground_seconds': int}
NOTE_MAX = 1 << 20
CHUNK = 1 << 20

# ------------------------------------------------------------------ file names (spec 3.1)
TAG = r'(?:A|B|A-restart1|B-restart1|NA-A|NA-B|E\d{8}T\d{6}Z)'
CASE = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}'
H8 = r'[0-9a-f]{8}'
UTC14 = r'\d{8}T\d{6}Z'
CLASS_RE = '(?:' + '|'.join(CLASSES) + ')'
PATTERNS = {
    'package': rf'^(CP|FZ)_({TAG})_([LR])(\d{{5}})_({H8})_({H8})_({H8})_({H8})_({H8})_({CASE})\.tgz$',
    'png': rf'^PNG_({TAG})_({H8})_(\d{{2}})of(\d{{2}})_({CASE})\.part$',
    'ai': rf'^AI_({TAG})_([SGV])([12])(?:r([2-9]))?_({H8})_({CASE})\.tgz$',
    'start': rf'^START_({TAG})_([SGV])([12])_({UTC14})_({H8})_({CASE})\.json$',
    'link': rf'^LINK_({TAG})_([SGV])([12])_({H8})_({CASE})\.json$',
    'transcript': rf'^TRANSCRIPT_({TAG})_([SGV])([12])_({H8})_({CASE})\.([A-Za-z0-9]{{1,10}})$',
    'incident': rf'^INCIDENT_({UTC14})_({H8})_({CLASS_RE})_({TAG}|NOJOB)_([SGV][12]|NA)_({CASE}|none)\.json$',
    'session': rf'^SESSION_({UTC14})_({H8})_({H8})\.json$',
    'genesis': rf'^GENESIS_({H8})_({UTC14})\.json$',
    'fpass': rf'^FINGERPRINT_PASS_({H8})_({UTC14})\.json$',
    'selftest': rf'^SELFTEST_({H8})_({UTC14})\.json$',
    'inputs': rf'^INPUTS_(E\d{{8}}T\d{{6}}Z)_(E\d{{8}}T\d{{6}}Z|E0)_({H8})_({CASE})\.tgz$',
    'ledger_final': rf'^LEDGER_FINAL_L(\d{{5}})_({H8})\.jsonl$',
    'all_frozen': r'^ALL_FROZEN\.json$',
    'delivery': rf'^DELIVERY_(PREPARED|SENT)_({CASE})_({UTC14})\.json$',
    'sentinel': rf'^SENTINEL_(setup|qualification|everyday)_({H8})\.json$',
    'stray': rf'^STRAY_({UTC14})_({H8})\.tgz$',
    'split': rf'^SPLIT_({H8})_(\d{{2}})of(\d{{2}})__(.+)$',
}
RX = {k: re.compile(v, re.ASCII) for k, v in PATTERNS.items()}


def parse_name(name):
    """The fields of a recognised file name (spec 3.1), else None."""
    if not isinstance(name, str):
        return None
    for kind, rx in RX.items():
        m = rx.match(name)
        if not m:
            continue
        g = m.groups()
        d = {'kind': kind, 'name': name}
        if kind == 'package':
            d.update(pkind=g[0], tag=g[1], seqkind=g[2], seq=int(g[3]), ledger8=g[4], record8=g[5], frozen8=g[6], fp8=g[7],
                     pkg8=g[8], case=g[9])
        elif kind == 'png':
            d.update(tag=g[0], set8=g[1], k=int(g[2]), n=int(g[3]), case=g[4])
        elif kind == 'ai':
            d.update(tag=g[0], role=g[1], attempt=int(g[2]), revision=int(g[3]) if g[3] else 1, tree8=g[4], case=g[5])
        elif kind == 'start':
            d.update(tag=g[0], role=g[1], attempt=int(g[2]), utc14=g[3], nonce8=g[4], case=g[5])
        elif kind == 'link':
            d.update(tag=g[0], role=g[1], attempt=int(g[2]), nonce8=g[3], case=g[4])
        elif kind == 'transcript':
            d.update(tag=g[0], role=g[1], attempt=int(g[2]), sha8=g[3], case=g[4], ext=g[5])
        elif kind == 'incident':
            ra = g[4]
            d.update(utc14=g[0], boot8=g[1], cls=g[2], tag=None if g[3] == 'NOJOB' else g[3],
                     role=None if ra == 'NA' else ra[0], attempt=None if ra == 'NA' else int(ra[1]),
                     case=None if g[5] == 'none' else g[5])
        elif kind == 'session':
            d.update(utc14=g[0], boot8=g[1], fp8=g[2])
        elif kind == 'genesis':
            d.update(id8=g[0], utc14=g[1])
        elif kind in ('fpass', 'selftest'):
            d.update(fp8=g[0], utc14=g[1])
        elif kind == 'inputs':
            d.update(tag=g[0], restart_of=None if g[1] == 'E0' else g[1], sha8=g[2], case=g[3])
        elif kind == 'ledger_final':
            d.update(seq=int(g[0]), l8=g[1])
        elif kind == 'delivery':
            d.update(which=g[0], case=g[1], utc14=g[2])
        elif kind == 'sentinel':
            d.update(folder=g[0], h8=g[1])
        elif kind == 'stray':
            d.update(utc14=g[0], boot8=g[1])
        elif kind == 'split':
            d.update(h8=g[0], k=int(g[1]), n=int(g[2]), original=g[3])
        return d
    return None


def package_name(pkind, tag, seqkind, seq, ledger8, record8, frozen8, fp8, pkg8, case):
    return f'{pkind}_{tag}_{seqkind}{seq:05d}_{ledger8}_{record8}_{frozen8}_{fp8}_{pkg8}_{case}.tgz'


def is_qual_tag(tag):
    return tag in QUAL_ROOTS


def chain_of(tag):
    """Qualification: one chain (the ledger). Everyday: one chain per run tag."""
    return 'Q' if is_qual_tag(tag) else tag


# ------------------------------------------------------------------ small helpers
def now_dt():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(dt):
    return dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def utc():
    return iso(now_dt())


def utc14(dt=None):
    return (dt or now_dt()).strftime('%Y%m%dT%H%M%SZ')


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
        for c in iter(lambda: f.read(CHUNK), b''):
            h.update(c)
    return h.hexdigest()


def md5_file(p):
    h = hashlib.md5(usedforsecurity=False)
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(CHUNK), b''):
            h.update(c)
    return h.hexdigest()


def h8(x):
    return x[:8]


def canon(obj):
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=False, sort_keys=False)


def note_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


def sjson(raw, what='json'):
    """Strict JSON (UTF-8, no duplicate keys, no NaN/Infinity) without the runner (usable before the pin check)."""
    def hook(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError('duplicate key')
            out[k] = v
        return out

    def bad_const(x):
        raise ValueError('constant')
    return json.loads(raw.decode('utf-8') if isinstance(raw, bytes) else raw, object_pairs_hook=hook, parse_constant=bad_const)


def read_json_file(p, what='json'):
    try:
        return sjson(Path(p).read_bytes(), what)
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def write_atomic(p, data, mode=0o644):
    p = Path(p)
    b = data if isinstance(data, bytes) else data.encode('utf-8')
    tmp = p.with_name('.tmp_' + str(os.getpid()) + '_' + p.name)
    with open(tmp, 'wb') as f:
        f.write(b)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, p)
    return sha_bytes(b)


def write_new(p, data, mode=0o644):
    """A new named output: never overwritten (open 'xb'); never empty (Drive rejects zero-byte files)."""
    b = data if isinstance(data, bytes) else data.encode('utf-8')
    if not b:
        raise Halt('STOP', 'INTERNAL_EMPTY_OUTPUT', 'an output file would be empty')
    p = Path(p)
    if os.path.lexists(p):
        raise FileExistsError(str(p))
    # T-07: a temporary file in the same folder, fsynced, then linked to the final name (a failed write leaves no
    # partial file under the final name; the link fails if the name exists, like open 'xb')
    tmp = p.with_name(f'.tmp_{os.getpid()}_{secrets.token_hex(4)}_{p.name}'[:250])
    try:
        with open(tmp, 'xb') as f:
            f.write(b)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.link(tmp, p)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return sha_bytes(b)


def ensure_file(p, data, mode=0o644):
    """T-07: the named output holds exactly data: written when absent, rewritten when a partial or other copy is there."""
    p = Path(p)
    if os.path.lexists(p):
        if not os.path.islink(p) and p.is_file() and os.lstat(p).st_size == len(data) and sha_file(p) == sha_bytes(data):
            return
        os.unlink(p)
    write_new(p, data, mode)


def make_writable_tree(root):
    root = Path(root)
    if not os.path.lexists(root) or os.path.islink(root):
        return
    if not root.is_dir():
        os.chmod(root, stat.S_IMODE(os.lstat(root).st_mode) | stat.S_IWUSR)
        return
    os.chmod(root, stat.S_IMODE(os.lstat(root).st_mode) | stat.S_IRWXU)
    for dp, dns, fns in os.walk(root):
        for n in dns:
            q = os.path.join(dp, n)
            if not os.path.islink(q):
                os.chmod(q, stat.S_IMODE(os.lstat(q).st_mode) | stat.S_IRWXU)


def remove_tree(root):
    root = Path(root)
    if os.path.islink(root) or (os.path.lexists(root) and not root.is_dir()):
        os.unlink(root)
        return
    if root.is_dir():
        make_writable_tree(root)
        shutil.rmtree(root)


def q(s):
    return shlex.quote(str(s))


def boot_id_path():
    return os.environ.get('CPS_VM_BOOT_ID_PATH') or BOOT_ID_DEFAULT


def current_boot_id():
    try:
        return Path(boot_id_path()).read_text(encoding='ascii').strip()
    except OSError:
        return 'unknown-boot'


def helper_info():
    return {'version': VERSION, 'sha256': sha_file(HELPER_FILE)}


# ------------------------------------------------------------------ output protocol (spec 1.2, 1.3)
class Block:
    def __init__(self):
        self.pre, self.result, self.bind, self.uploads, self.fetch, self.state, self.tail = [], {}, None, [], [], None, []
        self.code = EXIT_OK
        self.raw_text = None

    def upload(self, path, folder):
        line = f'UPLOAD {path} -> {folder}'
        if line not in self.uploads:
            self.uploads.append(line)

    def listing(self, folder, to, name=None):
        line = f'SAVE_DRIVE_LISTING folder={folder} to={to}' + (f' name={name}' if name else '')
        if line not in self.fetch:
            self.fetch.append(line)

    def download(self, did, name, to):
        line = f'DOWNLOAD id={did} name={name} -> {to}'
        if line not in self.fetch:
            self.fetch.append(line)

    def next(self, action):
        self.tail.append('NEXT: ' + action)

    def then(self, action):
        self.tail.append('THEN: ' + action)

    def option(self, code, action):
        self.tail.append(f'OPTION: {code} {action}')

    def text(self):
        if self.raw_text is not None:
            return self.raw_text
        out = list(self.pre)
        out.append('RESULT: ' + json.dumps(self.result, separators=(',', ':'), ensure_ascii=True))
        if self.bind is not None:
            out.append('BIND=' + self.bind)
        out += self.uploads + self.fetch
        if self.state:
            out.append('STATE: ' + ' '.join(f'{k}={v}' for k, v in self.state.items()))
        out += self.tail
        return '\n'.join(out) + '\n'


class Halt(Exception):
    """kind: REFUSED (exit 4, nothing changed, no UPLOAD), STOP (exit 3), NEED (exit 10), BUSY (exit 11)."""
    def __init__(self, kind, code, hint='', block=None, exit_code=None, detail=None):
        super().__init__(code)
        self.kind, self.code, self.hint, self.block, self.detail = kind, code, hint, block, detail
        self.exit_code = exit_code if exit_code is not None else {'REFUSED': EXIT_REFUSED, 'STOP': EXIT_STOP,
                                                                    'NEED': EXIT_NEED, 'BUSY': EXIT_BUSY}[kind]

    def to_block(self):
        b = self.block or Block()
        if self.kind == 'REFUSED':
            b.uploads = []
        b.result = dict(b.result, status=self.kind, code=self.code)
        if self.detail is not None:
            b.result['detail'] = self.detail
        if self.hint:
            b.result['hint'] = self.hint
        if self.kind == 'REFUSED':
            b.fetch = []
            b.tail = [t for t in b.tail if t.startswith(('NEXT:', 'THEN:'))]
            if not b.tail:                      # a refusal that names what to do instead (JOB_BUSY, HELPER_BUSY) prints NEXT
                b.tail.append('REFUSED: ' + self.code)
        elif self.kind == 'STOP':
            b.tail.append('STOP: ' + self.code + (' ' + self.hint if self.hint else ''))
        elif self.kind == 'NEED':
            if not any(t.startswith('NEXT:') for t in b.tail):
                b.next('RUN_SAME_COMMAND_AGAIN')
        b.code = self.exit_code
        return b


def refuse(code, hint='', detail=None, block=None):
    raise Halt('REFUSED', code, hint, block=block, detail=detail)


def stop(code, hint='', block=None, detail=None):
    raise Halt('STOP', code, hint, block=block, detail=detail)


def need(block, code='NEED_DOWNLOADS', detail=None):
    raise Halt('NEED', code, block=block, detail=detail)


# ------------------------------------------------------------------ layout, configuration, runner import (spec 2)
class Layout:
    def __init__(self):
        self.home = os.environ.get('HOME')
        self.overrides = {k: os.environ[k] for k in ('CPS_VM_BASE', 'CPS_TOOLS', 'CPS_VM_BOOT_ID_PATH') if os.environ.get(k)}
        h = self.home or ''
        self.base = Path(os.environ.get('CPS_VM_BASE') or (h + '/cps'))
        self.tools = Path(os.environ.get('CPS_TOOLS') or (h + '/cps-tools'))
        b = self.base
        self.repo, self.runtime, self.ledger_dir = b / 'repo', b / 'runtime', b / 'ledger'
        self.ledger = self.ledger_dir / 'LEDGER.jsonl'
        self.inbox, self.outbox, self.transcripts = b / 'inbox', b / 'outbox', b / 'transcripts'
        self.qual, self.jobs, self.everyday_inputs = b / 'qual', b / 'jobs', b / 'everyday_inputs'
        self.vm = b / 'vm.sh'
        self.index_path, self.state_path = self.outbox / 'INDEX.jsonl', self.outbox / 'SESSION_STATE.json'
        self.frozen_json = self.outbox / 'frozen_json'
        self.release_path, self.config_path = self.runtime / 'RELEASE.json', self.runtime / 'VM_HELPER_CONFIG.json'

    def V(self):
        return str(self.vm)

    def job_dir(self, tag, case):
        if is_qual_tag(tag):
            return self.qual / QUAL_ROOTS[tag] / case
        return self.jobs / tag[1:] / case

    def tag_of(self, job_dir):
        """(tag, case) of a job folder path in this layout, else (None, None)."""
        p = Path(os.path.abspath(job_dir))
        try:
            rel = p.relative_to(self.qual)
            parts = rel.parts
            if len(parts) == 2 and parts[0] in ROOT_TAGS:
                return ROOT_TAGS[parts[0]], parts[1]
        except ValueError:
            pass
        try:
            parts = p.relative_to(self.jobs).parts
            if len(parts) == 2 and re.fullmatch(r'\d{8}T\d{6}Z', parts[0]):
                return 'E' + parts[0], parts[1]
        except ValueError:
            pass
        return None, None

    def job_folders(self):
        """Every job folder under qual/* and jobs/* (sorted)."""
        out = []
        for root in (self.qual, self.jobs):
            if not root.is_dir():
                continue
            for r in sorted(root.iterdir()):
                if r.is_dir() and not r.name.startswith('.'):
                    out += [c for c in sorted(r.iterdir()) if c.is_dir() and not c.name.startswith('.')]
        return out


def check_layout_basic(lay):
    if not lay.home or not os.path.isabs(lay.home) or any(c.isspace() for c in lay.home):
        refuse('LAYOUT_HOME', '$HOME must be set, absolute and without whitespace')
    if not lay.base.is_absolute() or any(c.isspace() for c in str(lay.base)) or os.path.lexists(lay.base / '.git'):
        refuse('LAYOUT_BASE', 'the base must be absolute, without whitespace, and not a git checkout (move an old ~/cps away)')
    if os.path.realpath(lay.repo) != str(HELPER_REPO):
        refuse('LAYOUT_HELPER_NOT_IN_BASE_REPO', 'run BASE/repo/deploy/vm/cps_vm.py (through BASE/vm.sh)')


def under(p, root):
    try:
        Path(os.path.abspath(p)).relative_to(os.path.abspath(root))
        return True
    except ValueError:
        return False


def mode_of(release):
    st = (release or {}).get('status')
    return {'RELEASED_FOR_QUALIFICATION': 'qualification', 'RELEASED_FOR_USE': 'everyday'}.get(st, 'setup')


def check_layout_release(lay, rel):
    """2.2: the release names exactly this layout's paths, pins the helper and the runner."""
    mode = mode_of(rel)
    bad = []
    root = (rel.get('repository') or {}).get('root')
    if not isinstance(root, str) or os.path.realpath(root) != os.path.realpath(lay.repo):
        bad.append('repository.root')
    qd = rel.get('qualification') if isinstance(rel.get('qualification'), dict) else {}
    if mode == 'qualification':
        if qd.get('ledger') != str(lay.ledger):
            bad.append('qualification.ledger')
        if not isinstance(qd.get('jobs_file'), str) or not under(qd['jobs_file'], lay.runtime):
            bad.append('qualification.jobs_file')
        for a in qd.get('admissions') or []:
            if not isinstance(a, dict) or not isinstance(a.get('path'), str) or not under(a['path'], lay.runtime):
                bad.append('qualification.admissions')
    for k, t in (rel.get('tables') or {}).items():
        if isinstance(t, dict) and isinstance(t.get('path'), str) and not under(t['path'], lay.runtime):
            bad.append('tables.' + k)
    sp = rel.get('source_prep') or {}
    if sp.get('deps_bundle') != str(lay.tools / 'builder-deps'):
        bad.append('source_prep.deps_bundle')
    if sp.get('node_path') is not None and sp.get('node_path') != str(lay.tools / 'playwright' / 'node_modules'):
        bad.append('source_prep.node_path')
    cn = rel.get('checker_node') or {}
    if cn.get('path') is not None and not under(cn['path'], lay.tools):
        bad.append('checker_node.path')
    if bad:
        refuse('LAYOUT_RELEASE_MISMATCH', 'the release does not name this layout', detail={'fields': sorted(set(bad))})
    pins = rel.get('pinned_files_sha256') or {}
    for f in ('deploy/vm/cps_vm.py', 'deploy/vm/session_start.sh'):
        p = HELPER_REPO / f
        if not p.is_file() or pins.get(f) != sha_file(p):
            refuse('LAYOUT_HELPER_NOT_PINNED', 'the release must pin deploy/vm/cps_vm.py and session_start.sh', detail={'file': f})
    rp = HELPER_REPO / 'deploy/run/cps_job.py'
    if not rp.is_file() or pins.get('deploy/run/cps_job.py') != sha_file(rp):
        refuse('LAYOUT_RUNNER_NOT_PINNED', 'the release must pin deploy/run/cps_job.py')
    return mode


CJ = None


def runner_path():
    return HELPER_REPO / 'deploy/run/cps_job.py'


def load_runner():
    """Import runner v4 for its primitives (never its cmd_* functions), after the pin check."""
    global CJ
    if CJ is None:
        spec = importlib.util.spec_from_file_location('cps_job_v4', str(runner_path()))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        CJ = m
    return CJ


def load_config(lay):
    raw = None
    try:
        raw = lay.config_path.read_bytes()
        c = sjson(raw)
    except (OSError, ValueError, UnicodeDecodeError):
        c = None
    if not isinstance(c, dict) or set(c) != set(CONFIG_KEYS) or c.get('schema') != CONFIG_SCHEMA:
        stop('CONFIG_INVALID', 'runtime/VM_HELPER_CONFIG.json: keys or schema')
    for k, t in CONFIG_KEYS.items():
        v = c[k]
        if not isinstance(v, t) or (t is int and isinstance(v, bool)):
            stop('CONFIG_INVALID', 'type of ' + k)
    d = c['drive']
    if set(d) != {'setup', 'qualification', 'everyday'} or not all(isinstance(v, str) and v for v in d.values()):
        stop('CONFIG_INVALID', 'drive')
    if c['upload_verification'] not in ('md5', 'download') or c['listing_page_marker'] not in ('required', 'absent'):
        stop('CONFIG_INVALID', 'upload_verification or listing_page_marker')
    if not 1_000_000 <= c['png_part_bytes'] <= 2_000_000_000 or c['png_part_bytes'] > c['max_upload_bytes']:
        stop('CONFIG_INVALID', 'png_part_bytes')
    for k in ('setup', 'qualification', 'everyday'):
        s = c['sentinels'].get(k)
        if not isinstance(s, dict) or set(s) != {'name', 'md5', 'upload_by_dot'} or not RX['sentinel'].match(str(s.get('name'))):
            stop('CONFIG_INVALID', 'sentinels.' + k)
    return c


# ------------------------------------------------------------------ INDEX.jsonl and SESSION_STATE.json (spec 2.6)
INDEX_FIELDS = ('name', 'kind', 'folder', 'sha256', 'md5', 'bytes', 'created_utc', 'origin', 'drive_id', 'drive_created',
                'job_dir', 'case_id', 'tag', 'role', 'attempt', 'seq', 'record_sha256', 'ledger_sha256', 'tree_sha256', 'payload')
ORIGIN_RANK = {'listed': 0, 'restored': 1, 'made': 2}


class Index:
    def __init__(self, path):
        self.path = Path(path)
        self.lines = []
        if self.path.is_file():
            raw = self.path.read_bytes()
            for ln in raw.split(b'\n')[:-1]:                 # an incomplete last line (no newline) is ignored
                try:
                    self.lines.append(json.loads(ln.decode('utf-8')))
                except ValueError:
                    continue
        self._rebuild()

    def _rebuild(self):
        self.files, self.events, self.copies = {}, [], {}
        for e in self.lines:
            if 'event' in e:
                self.events.append(e)
                continue
            n = e['name']
            if e.get('origin') == 'listed' and e.get('drive_id'):
                self.copies.setdefault(n, {})[e['drive_id']] = e
            cur = self.files.get(n)
            if cur is None:
                self.files[n] = dict(e)
            else:
                hi, lo = (e, cur) if ORIGIN_RANK.get(e.get('origin'), 0) >= ORIGIN_RANK.get(cur.get('origin'), 0) else (cur, e)
                merged = dict(lo)
                merged.update({k: v for k, v in hi.items() if v is not None})
                for k in ('drive_id', 'drive_created', 'md5'):
                    if merged.get(k) is None and lo.get(k) is not None:
                        merged[k] = lo[k]
                merged['origin'] = hi.get('origin')
                self.files[n] = merged

    def append(self, obj):
        line = (json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            size = os.fstat(fd).st_size
            if size:
                os.lseek(fd, max(0, size - CHUNK), os.SEEK_SET)
                tail = os.read(fd, CHUNK)
                if not tail.endswith(b'\n'):
                    cut = tail.rfind(b'\n')
                    os.ftruncate(fd, size - len(tail) + cut + 1 if cut >= 0 else max(0, size - len(tail)))
            os.lseek(fd, 0, os.SEEK_END)
            os.write(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)
        self.lines.append(json.loads(line.decode('utf-8')))
        self._rebuild()

    def add(self, **kw):
        e = {k: kw.get(k) for k in INDEX_FIELDS}
        for k in ('meta', 'content'):
            if kw.get(k) is not None:
                e[k] = kw[k]
        self.append(e)
        return self.files[e['name']]

    def event(self, ev, name, **kw):
        self.append(dict({'event': ev, 'name': name}, **kw))

    def get(self, name):
        return self.files.get(name)

    def has_event(self, ev, name):
        return any(e['event'] == ev and e['name'] == name for e in self.events)

    def confirmed(self, name):
        return self.has_event('confirmed', name) or self.has_event('verified', name)

    def of(self, kind, **match):
        out = []
        for e in self.files.values():
            if e.get('kind') != kind:
                continue
            if all(e.get(k) == v for k, v in match.items()):
                out.append(e)
        return sorted(out, key=lambda e: (e.get('created_utc') or '', e['name']))


def read_state(lay):
    return read_json_file(lay.state_path) if lay.state_path.is_file() else None


def write_state(lay, st):
    write_atomic(lay.state_path, note_bytes(st))


# ------------------------------------------------------------------ locks (spec 4)
class HelperLock:
    def __init__(self, lay, wait=10.0):
        self.lay, self.wait, self.fd = lay, wait, None

    def __enter__(self):
        self.lay.outbox.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.lay.outbox / '.lock', os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.time() + self.wait
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.time() >= deadline:
                    os.close(self.fd)
                    self.fd = None
                    b = Block()
                    if (self.lay.outbox / 'DETACHED.json').is_file():
                        b.next('RUN ' + self.lay.V() + ' wait')
                    refuse('HELPER_BUSY', 'another helper command is running', block=b)
                time.sleep(0.1)

    def release(self):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None

    def __exit__(self, *exc):
        self.release()
        return False


class JobLock:
    def __init__(self, lay, job_dir):
        self.lay, self.dir, self.fd = lay, Path(job_dir), None

    def __enter__(self):
        if not self.dir.is_dir():
            return self
        self.fd = os.open(self.dir, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            b = Block()
            b.next('RUN ' + self.lay.V() + ' wait')
            b.then('RUN ' + self.lay.V() + ' status')
            refuse('JOB_BUSY', 'a runner command or a tool it started holds the job folder: wait, never re-issue it', block=b)
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None
        return False


# ------------------------------------------------------------------ trees and archives (spec 3.3-3.6)
def tree_list(root, unsupported_code='PACKAGE_UNSUPPORTED_ENTRY'):
    """Sorted [rel, 'dir'|'file', mode, bytes|None, sha256|None] of every entry below root, never following a link."""
    out = []
    root = str(root)
    for dp, dns, fns in os.walk(root, followlinks=False):
        dns.sort()
        for n in dns + fns:
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, root).replace(os.sep, '/')
            try:                                    # r2 R2-07: only names restore accepts are packed
                rel.encode('utf-8')
                bad = unsafe_name(rel)
            except UnicodeEncodeError:
                bad = 'utf-8'
            if bad:
                stop(unsupported_code, 'a file name the archive format does not keep (backslash, NUL or not UTF-8)',
                     detail={'path': rel.encode('utf-8', 'replace').decode('ascii', 'replace')[:200], 'why': bad})
            st = os.lstat(p)
            m = stat.S_IMODE(st.st_mode)
            if m & 0o7000:
                stop(unsupported_code, 'a setuid, setgid or sticky bit in the job folder', detail={'path': rel[:200]})
            if stat.S_ISDIR(st.st_mode):
                out.append([rel, 'dir', m, None, None])
            elif stat.S_ISREG(st.st_mode):
                out.append([rel, 'file', m, st.st_size, sha_file(p)])
            else:
                stop(unsupported_code, 'a symbolic link, device, socket or FIFO in the folder', detail={'path': rel[:200]})
    return sorted(out, key=lambda e: e[0])


def tree_sha(entries):
    return sha_bytes(json.dumps(entries, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))


def _tarinfo(name, mode, mtime, size=None, is_dir=False):
    ti = tarfile.TarInfo(name)
    ti.mode, ti.uid, ti.gid, ti.uname, ti.gname, ti.mtime = mode, 0, 0, '', '', int(mtime)
    if is_dir:
        ti.type = tarfile.DIRTYPE
    else:
        ti.size = size
    return ti


def write_tgz(dest, members):
    """members: [(arcname, kind, mode, mtime, bytes|path|None)] in order. gzip mtime=0, level 6, PAX."""
    with open(dest, 'xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=6, mtime=0) as gz:
            write_tar_stream(gz, members)
        raw.flush()
        os.fsync(raw.fileno())


def write_tar_stream(fobj, members):
    with tarfile.open(fileobj=fobj, mode='w', format=tarfile.PAX_FORMAT) as tf:
        for name, kind, mode, mtime, src in members:
            if kind == 'dir':
                tf.addfile(_tarinfo(name, mode, mtime, is_dir=True))
            elif isinstance(src, (bytes, bytearray)):
                tf.addfile(_tarinfo(name, mode, mtime, size=len(src)), io.BytesIO(src))
            else:
                size = os.lstat(src).st_size
                with open(src, 'rb') as f:
                    tf.addfile(_tarinfo(name, mode, mtime, size=size), f)


def unsafe_name(n):
    if not n or '\\' in n or '\0' in n or n.startswith('/'):
        return 'path'
    parts = n.split('/')
    if any(p in ('', '.', '..') for p in parts):
        return 'component'
    return None


ARCHIVE_EXACT = {'MANIFEST.json': ('MANIFEST.json',), 'ledger': ('ledger', 'ledger/LEDGER.jsonl')}


def under_stage(stage, rel):
    """T-04: a member path that stays inside the staging folder (no '..', no absolute path, no link on the way)."""
    if not isinstance(rel, str) or unsafe_name(rel):
        return False
    root = os.path.realpath(stage)
    parent = os.path.realpath(os.path.join(root, os.path.dirname(rel)) if os.path.dirname(rel) else root)
    return parent == root or parent.startswith(root + os.sep)


PNG_SUBS = ('job/qa/visual_deliverable/', 'job/qa/visual_internal/')


def png_manifest_problem(man):
    """T-04: None when the manifest's PNG set is safe to read and write (3.6), else a reason. Every png.files path is a
    safe name under job/qa/visual_deliverable/ or job/qa/visual_internal/, unique, not a core member, with no
    setuid/setgid/sticky bit; every part name is a PNG part name of this package's tag and case."""
    png = man.get('png') if isinstance(man, dict) else None
    if not png:
        return None
    if not isinstance(png, dict) or not isinstance(png.get('files'), list) or not isinstance(png.get('parts') or [], list):
        return 'png'
    core = {m.get('path') for m in man.get('members') or [] if isinstance(m, dict)}
    seen = set()
    for f in png['files']:
        p = f.get('path') if isinstance(f, dict) else None
        mode = f.get('mode') if isinstance(f, dict) else None
        if not isinstance(p, str) or unsafe_name(p) or not p.startswith(PNG_SUBS) or p in seen or p in core:
            return 'png path'
        if not isinstance(mode, int) or isinstance(mode, bool) or mode & ~0o777:
            return 'png mode'
        seen.add(p)
    for part in png.get('parts') or []:
        n = part.get('name') if isinstance(part, dict) else None
        pn = parse_name(n)
        if not pn or pn['kind'] != 'png' or pn['tag'] != man.get('tag') or pn['case'] != man.get('case_id'):
            return 'png part name'
    return None


def pkg_manifest_problem(man):
    """T-04/T-25: every core member is job or under job/, with a plain mode; the PNG set passes png_manifest_problem."""
    for m in (man.get('members') or []) if isinstance(man, dict) else []:
        p = m.get('path') if isinstance(m, dict) else None
        if not isinstance(p, str) or unsafe_name(p) or not (p == 'job' or p.startswith('job/')):
            return 'member path'
        if not isinstance(m.get('mode'), int) or isinstance(m.get('mode'), bool) or m['mode'] & ~0o777:
            return 'member mode'
    return png_manifest_problem(man)


def check_pkg_manifest(a):
    why = pkg_manifest_problem(a.manifest)
    if why:
        a.bad('ARCHIVE_UNSAFE_MEMBER', {'why': why})


class Archive:
    """Safe reading (3.6): members by getmembers/extractfile only; every check passes before anything is written."""
    def __init__(self, path, prefixes, gz=True, code_stop=True):
        self.path, self.prefixes = Path(path), prefixes
        try:
            self.tf = tarfile.open(str(path), mode='r:gz' if gz else 'r:')
            self.members = self.tf.getmembers()
        except (tarfile.TarError, OSError, EOFError, zlib_error()) as e:
            self.bad('ARCHIVE_UNREADABLE', {'why': type(e).__name__})
        self.by = {}
        exact, trees = set(), []
        for p in prefixes:                              # T-25: MANIFEST.json and the ledger are exact names; others are trees
            if p in ARCHIVE_EXACT:
                exact |= set(ARCHIVE_EXACT[p])
            else:
                trees.append(p)
        for m in self.members:
            why = None
            if not (m.isreg() or m.isdir()):
                why = 'type'
            elif unsafe_name(m.name):
                why = unsafe_name(m.name)
            elif not (m.name in exact or any(m.name == p or m.name.startswith(p + '/') for p in trees)):
                why = 'outside'
            elif m.name in self.by:
                why = 'duplicate'
            elif m.mode & 0o7000:
                why = 'mode'
            if why:
                self.bad('ARCHIVE_UNSAFE_MEMBER', {'path': m.name[:200], 'why': why})
            self.by[m.name] = m
        if not self.members or self.members[0].name != 'MANIFEST.json' or not self.members[0].isreg():
            self.bad('ARCHIVE_MANIFEST_MISMATCH', {'why': 'MANIFEST.json is not the first member'})
        try:
            self.manifest = sjson(self.read('MANIFEST.json'))
        except ValueError:
            self.bad('ARCHIVE_MANIFEST_MISMATCH', {'why': 'MANIFEST.json is not strict JSON'})

    def bad(self, code, detail):
        stop(code, 'the archive is not one the helper made, or it is damaged', detail=dict(detail, archive=self.path.name))

    def read(self, name):
        f = self.tf.extractfile(self.by[name])
        return f.read()

    def check(self, expected):
        """expected: {arcname: ('dir', mode) | ('file', mode, bytes, sha256)}; exactly these members besides MANIFEST.json."""
        names = set(self.by) - {'MANIFEST.json'}
        if names != set(expected):
            extra, missing = sorted(names - set(expected))[:5], sorted(set(expected) - names)[:5]
            self.bad('ARCHIVE_MANIFEST_MISMATCH', {'unlisted': extra, 'missing': missing})
        for n, e in expected.items():
            m = self.by[n]
            if (e[0] == 'dir') != m.isdir() or stat.S_IMODE(m.mode) != e[1]:
                self.bad('ARCHIVE_MANIFEST_MISMATCH', {'path': n[:200], 'why': 'type or mode'})
            if e[0] == 'file':
                if m.size != e[2] or sha_bytes(self.read(n)) != e[3]:
                    self.bad('ARCHIVE_MEMBER_SHA_MISMATCH', {'path': n[:200]})

    def close(self):
        try:
            self.tf.close()
        except Exception:                               # noqa: BLE001
            pass


def zlib_error():
    import zlib
    return zlib.error


class Staging:
    """Write a folder tree into a sibling staging folder, then rename it into place (3.6 steps 1-6)."""
    def __init__(self, target):
        self.target = Path(target)
        self.stage = self.target.parent / f'.cps_vm_stage_{self.target.name}_{os.getpid()}'
        self.modes, self.root_mode = {}, 0o755

    def begin(self, root_mode):
        for old in self.target.parent.glob(f'.cps_vm_stage_{self.target.name}_*'):
            remove_tree(old)
        self.target.parent.mkdir(parents=True, exist_ok=True)
        os.mkdir(self.stage, 0o700)
        self.root_mode = root_mode
        return self

    def _check(self, rel, mode):
        if not under_stage(self.stage, rel) or not isinstance(mode, int) or isinstance(mode, bool) or mode & ~0o777:
            stop('ARCHIVE_UNSAFE_MEMBER', 'a member would be written outside its folder or with a special mode',
                 detail={'path': str(rel)[:200]})

    def add_dir(self, rel, mode):
        self._check(rel, mode)
        p = self.stage / rel
        if not p.is_dir():
            os.mkdir(p, 0o700)
        self.modes[rel] = ('dir', mode)

    def add_file(self, rel, data, mode):
        self._check(rel, mode)
        p = self.stage / rel
        with open(p, 'xb') as f:
            f.write(data)
        self.modes[rel] = ('file', mode)

    def finish(self):
        for rel, (k, m) in self.modes.items():
            if k == 'file':
                os.chmod(self.stage / rel, m)
        for rel in sorted((r for r, (k, _) in self.modes.items() if k == 'dir'), key=lambda r: -r.count('/')):
            os.chmod(self.stage / rel, self.modes[rel][1])
        os.chmod(self.stage, self.root_mode)            # T-24: the root mode is set before the rename (renaming needs only the parent)
        os.rename(self.stage, self.target)


def png_set(job_dir):
    """3.4: exactly the page images and tiles the two VISUAL_QA manifests list, when regular files."""
    out = []
    for sub in ('qa/visual_deliverable', 'qa/visual_internal'):
        man = Path(job_dir) / sub / 'VISUAL_QA_MANIFEST.json'
        d = read_json_file(man) if man.is_file() else None
        if not isinstance(d, dict):
            continue
        for img in d.get('images') or []:
            files = [img.get('file')] + [t.get('file') for t in (img.get('tiles') or []) if isinstance(t, dict)]
            for f in files:
                if isinstance(f, str) and not unsafe_name(f):
                    rel = sub + '/' + f
                    p = Path(job_dir) / rel
                    if stat.S_ISREG(os.lstat(p).st_mode) if os.path.lexists(p) else False:
                        out.append(rel)
    return sorted(set(out))


def png_tar_members(job_dir, rels):
    out = []
    for rel in rels:
        p = Path(job_dir) / rel
        out.append(('job/' + rel, 'file', stat.S_IMODE(os.lstat(p).st_mode), 0, str(p)))
    return out


# ------------------------------------------------------------------ Drive listings (spec 3.2)
class Listing:
    def __init__(self, folder, name_filter, files, pages):
        self.folder, self.name_filter, self.files, self.pages = folder, name_filter, files, pages
        self.by = {}
        for f in files:
            self.by.setdefault(f['name'], []).append(f)
        for n in self.by:
            self.by[n].sort(key=lambda f: (f['created'] or '', f['id']))

    def copies(self, name):
        """Distinct copies of one name (same md5, or same size without md5, is one file), ascending createdTime."""
        out, seen = [], set()
        for f in self.by.get(name, []):
            key = ('md5', f['md5']) if f['md5'] else ('size', f['size'], f['id'] if f['size'] is None else '')
            if key in seen:
                continue
            seen.add(key)
            out.append(f)
        return out

    def names(self, kind=None):
        out = []
        for n in self.by:
            p = parse_name(n)
            if p and (kind is None or p['kind'] == kind):
                out.append(p)
        return out

    def has(self, name):
        return name in self.by


LISTING_FIELDS_HINT = ('save every page with the fields nextPageToken, incompleteSearch, kind and '
                       'files(id,name,createdTime,md5Checksum,size,mimeType) (README 0 rule 2), following every page to the end')


def listing_refuse(code, hint='list the folder again, following every page to the end', detail=None):
    refuse(code, hint, detail=detail)


def parse_listing(path, folder, name_filter, cfg, sentinel=None, sentinel_bytes=None):
    """Read a saved listing (the wrapper of 3.2) and apply every refusal of 3.2; returns a Listing."""
    d = read_json_file(path)
    if not isinstance(d, dict) or d.get('schema') != LISTING_SCHEMA or not isinstance(d.get('pages'), list) or not d['pages']:
        listing_refuse('LISTING_INVALID', 'save the pages in the wrapper of README 0 rule 2: '
                       '{"schema": "cps.vm-drive-listing.v1", "folder": ..., "name_filter": ..., "pages": [...]}',
                       {'why': 'wrapper'})
    if d.get('folder') != folder or d.get('name_filter') != name_filter:
        listing_refuse('LISTING_WRONG_FOLDER')
    files, marker = [], False
    pages = d['pages']
    for i, pg in enumerate(pages):
        if isinstance(pg, list):
            pg = {'files': pg}
        if not isinstance(pg, dict) or not isinstance(pg.get('files', []), list):
            listing_refuse('LISTING_INVALID', LISTING_FIELDS_HINT, {'why': 'page', 'page': i + 1})
        if any(k in pg for k in ('nextPageToken', 'incompleteSearch', 'kind')):
            marker = True
        tok = pg.get('nextPageToken')
        if pg.get('incompleteSearch') is True:
            listing_refuse('LISTING_INCOMPLETE')
        if i == len(pages) - 1 and tok:
            listing_refuse('LISTING_INCOMPLETE')
        if i < len(pages) - 1 and not tok:
            listing_refuse('LISTING_INCOMPLETE')
        for j, f in enumerate(pg.get('files', [])):
            where = {'page': i + 1, 'entry': j + 1}
            if not isinstance(f, dict):
                listing_refuse('LISTING_INVALID', LISTING_FIELDS_HINT, dict(where, why='entry'))
            miss = [k for k in ('name', 'id', 'createdTime') if not (isinstance(f.get(k), str) and f.get(k))]
            if miss:                                # r2 R2-03: name the missing field and the entry
                listing_refuse('LISTING_INVALID', LISTING_FIELDS_HINT, dict(where, missing=miss))
            if parse_utc(f['createdTime']) is None:
                listing_refuse('LISTING_INVALID', 'createdTime must be RFC 3339 as Drive gives it: save the page unchanged',
                               dict(where, field='createdTime'))
            md5 = f.get('md5Checksum')
            if md5 is not None and not (isinstance(md5, str) and re.fullmatch(r'[0-9a-f]{32}', md5)):
                listing_refuse('LISTING_INVALID', 'md5Checksum must be 32 lowercase hex digits: save the page unchanged',
                               dict(where, field='md5Checksum'))
            size = f.get('size')
            if size is not None:
                if isinstance(size, bool) or not (isinstance(size, int) or (isinstance(size, str) and size.isdigit())):
                    listing_refuse('LISTING_INVALID', 'size must be a number of bytes: save the page unchanged', dict(where, field='size'))
                size = int(size)
            mt = f.get('mimeType')
            if isinstance(mt, str) and mt.startswith('application/vnd.google-apps.'):
                listing_refuse('LISTING_CONVERTED_FILE', 'Drive converted an upload: upload it again with conversion off')
            if name_filter is not None and f['name'] != name_filter:
                continue
            files.append({'name': f['name'], 'id': f['id'], 'created': iso(parse_utc(f['createdTime'])), 'md5': md5,
                          'size': size})
    if cfg['listing_page_marker'] == 'required' and not marker:
        listing_refuse('LISTING_NO_PAGE_MARKER', 'save each page as the connector returns it, with its kind, nextPageToken '
                       'and incompleteSearch fields (README 0 rule 2)')
    lst = Listing(folder, name_filter, files, len(pages))
    if name_filter is None and sentinel is not None:
        want_size = len(sentinel_bytes) if sentinel_bytes is not None else None
        ok = any((f['md5'] == sentinel['md5']) if f['md5'] else (want_size is not None and f['size'] == want_size)
                 for f in lst.by.get(sentinel['name'], []))
        if not ok:
            listing_refuse('LISTING_SENTINEL_MISSING', 'the listing must show the folder sentinel: list the right folder, every page')
    return lst


LISTING_REFUSALS_MAX = 3


def read_listing(ctx, path, folder, name_filter, sentinel=None, sentinel_bytes=None, block=None):
    """parse_listing; T-12: a listing refusal sets the bad file aside and asks for the same listing again (exit 10)."""
    try:
        lst = parse_listing(path, folder, name_filter, ctx.cfg, sentinel, sentinel_bytes)
    except Halt as h:
        if h.kind != 'REFUSED' or not h.code.startswith('LISTING_'):
            raise
        relist(ctx, path, folder, name_filter, h.code, h.hint, block, extra=h.detail)
    for old in quarantined(ctx, path):
        old.unlink()
    return lst


def quarantined(ctx, path):
    q = ctx.lay.outbox / 'rejected_listings'
    key = h8(sha_bytes(str(path).encode('utf-8')))
    return sorted(q.glob(key + '_*')) if q.is_dir() else []


def relist(ctx, path, folder, name_filter, code, hint, block=None, extra=None):
    """T-12: move the refused listing to outbox/rejected_listings/ (so no later command reads it), print the exact
    SAVE_DRIVE_LISTING again and exit 10; the third refusal of the same listing in a row is STOP (case C)."""
    q = ctx.lay.outbox / 'rejected_listings'
    q.mkdir(parents=True, exist_ok=True)
    n = len(quarantined(ctx, path)) + 1
    key = h8(sha_bytes(str(path).encode('utf-8')))
    if os.path.lexists(path):
        os.replace(path, q / f'{key}_{n:02d}_{Path(path).name}')
    detail = {'folder': folder, 'to': str(path), 'name_filter': name_filter, 'refusals': n}
    if isinstance(extra, dict):
        detail['problem'] = extra
    b = block if block is not None else Block()
    if n >= LISTING_REFUSALS_MAX:
        b.tail = []
        stop('LISTING_REFUSED_REPEATEDLY', f'{code}: the listing was refused {n} times: hand back case C', block=b, detail=detail)
    b.listing(folder, path, name_filter)
    raise Halt('NEED', code, hint or 'list the folder again, following every page to the end', block=b, detail=detail)


def file_matches(f, md5, size):
    if f.get('md5') and md5:
        return f['md5'] == md5 and (f.get('size') is None or size is None or f['size'] == size)
    return f.get('size') is not None and size is not None and f['size'] == size


def ingest_listing(ctx, lst):
    """Confirm made files that the listing shows (md5, else size), and record every other recognised name as listed."""
    ix = ctx.index
    for name, fs in lst.by.items():
        p = parse_name(name)
        if p is None or p['kind'] == 'sentinel':
            continue
        e = ix.get(name)
        if e is not None and e.get('origin') in ('made', 'restored') and e.get('sha256'):
            hit = next((f for f in fs if file_matches(f, e.get('md5'), e.get('bytes'))), None)
            if hit is not None and not ix.confirmed(name) and e.get('origin') == 'made':
                ix.event('confirmed', name, drive_id=hit['id'], md5=hit['md5'], bytes=hit['size'])
        known = ix.copies.get(name, {})
        for f in fs:
            if f['id'] in known:
                continue
            ix.add(name=name, kind=p['kind'], folder=lst.folder, md5=f['md5'], bytes=f['size'], origin='listed',
                   drive_id=f['id'], drive_created=f['created'], tag=p.get('tag'), case_id=p.get('case'),
                   role=p.get('role'), attempt=p.get('attempt'), seq=p.get('seq'))
    # split originals: confirmed when every slice is
    for e in list(ix.files.values()):
        if e.get('kind') == 'split' and e.get('origin') == 'made':
            orig = (e.get('meta') or {}).get('of')
            sl = [x for x in ix.files.values() if x.get('kind') == 'split' and (x.get('meta') or {}).get('of') == orig]
            if orig and sl and all(ix.confirmed(x['name']) for x in sl) and not ix.confirmed(orig):
                ix.event('confirmed', orig, drive_id=None, md5=None, bytes=None)


# ------------------------------------------------------------------ made files, uploads and splits (spec 3.9)
def made(ctx, path, kind, folder, **fields):
    """Record a file the helper made (INDEX origin made) and return the paths to upload, slices first when oversized."""
    path = Path(path)
    st = os.lstat(path)
    if st.st_size == 0:
        stop('INTERNAL_EMPTY_OUTPUT', 'an output file is empty')
    sha, md5 = sha_file(path), md5_file(path)
    ctx.index.add(name=path.name, kind=kind, folder=folder, sha256=sha, md5=md5, bytes=st.st_size, created_utc=utc(),
                  origin='made', payload=str(path), **fields)
    return upload_paths(ctx, path, folder)


def upload_paths(ctx, path, folder):
    path = Path(path)
    size = os.lstat(path).st_size
    limit = ctx.cfg['max_upload_bytes'] if ctx.cfg else 1 << 62
    if size <= limit or path.name.startswith('PNG_'):
        return [path]
    sha = sha_file(path)
    n = (size + limit - 1) // limit
    if n > 99:
        stop('INTERNAL_SPLIT_TOO_MANY', 'max_upload_bytes is too small for this file')
    out = []
    with open(path, 'rb') as f:
        for k in range(1, n + 1):
            name = f'SPLIT_{h8(sha)}_{k:02d}of{n:02d}__{path.name}'
            sp = path.parent / name
            data = f.read(limit)
            ensure_file(sp, data)
            if ctx.index.get(name) is None:
                ctx.index.add(name=name, kind='split', folder=folder, sha256=sha_bytes(data),
                              md5=hashlib.md5(data, usedforsecurity=False).hexdigest(), bytes=len(data), created_utc=utc(),
                              origin='made', payload=str(sp), meta={'of': path.name})
            out.append(sp)
    return out


def join_slices(paths_by_k, want_name):
    """Join SPLIT_ slices (k -> path) of one file; None when incomplete or the whole-file hash fails."""
    if not paths_by_k:
        return None
    ps = [parse_name(Path(p).name) for p in paths_by_k.values()]
    n = ps[0]['n']
    if set(paths_by_k) != set(range(1, n + 1)) or any(x['n'] != n or x['original'] != want_name for x in ps):
        return None
    data = b''.join(Path(paths_by_k[k]).read_bytes() for k in range(1, n + 1))
    if h8(sha_bytes(data)) != ps[0]['h8']:
        return None
    return data


# ------------------------------------------------------------------ fingerprint (spec 7)
class FP:
    def __init__(self):
        self.cache = {}

    def sha(self, p):
        r = os.path.realpath(p)
        if r not in self.cache:
            try:
                self.cache[r] = sha_file(r)
            except OSError:
                self.cache[r] = None
        return self.cache[r]

    def closure(self, binary):
        if not binary or not os.path.isfile(binary):
            return None
        try:
            out = subprocess.run(['ldd', binary], capture_output=True, text=True, timeout=60).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        libs = set()
        for ln in out.splitlines():
            if '=>' in ln:
                tgt = ln.split('=>', 1)[1].strip().split(' (')[0].strip()
                if tgt.startswith('/'):
                    libs.add(os.path.realpath(tgt))
            elif ln.strip().startswith('/'):
                libs.add(os.path.realpath(ln.strip().split(' (')[0]))
        if os.path.exists('/lib64/ld-linux-x86-64.so.2'):
            libs.add(os.path.realpath('/lib64/ld-linux-x86-64.so.2'))
        return sorted([p, self.sha(p)] for p in libs)


def first_line(cmd, env=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
        t = (p.stdout or p.stderr).strip().splitlines()
        return t[0][:300] if t else ''
    except (OSError, subprocess.SubprocessError):
        return None


def fingerprint(lay):
    fp = FP()
    comp = {}
    node = shutil.which('node')
    comp['node'] = None if not node else {'realpath': os.path.realpath(node), 'sha256': fp.sha(node),
                                          'version': first_line([node, '--version']), 'closure': fp.closure(os.path.realpath(node))}
    try:
        import importlib.metadata as md
        dists = sorted([d.metadata['Name'] or '', d.version or '', sha_bytes((d.read_text('RECORD') or '').encode('utf-8'))]
                       for d in md.distributions())
    except Exception:                                       # noqa: BLE001
        dists = None
    comp['python'] = {'realpath': os.path.realpath(sys.executable), 'sha256': fp.sha(sys.executable), 'version': sys.version,
                      'closure': fp.closure(os.path.realpath(sys.executable)), 'distributions': dists}
    host = None
    for d in os.environ.get('PATH', '').split(':'):
        c = os.path.join(d, 'soffice')
        if d and os.path.isfile(c) and os.access(c, os.X_OK) and not under(os.path.realpath(c), os.path.realpath(lay.tools)) \
                and not under(c, lay.tools):
            host = c
            break
    lo = {'wrapper_sha256': fp.sha(lay.tools / 'bin' / 'soffice') if (lay.tools / 'bin' / 'soffice').is_file() else None, 'host': None}
    if host:
        real = os.path.realpath(host)
        root = Path(real).parent.parent if Path(real).parent.name == 'program' else Path(real).parent
        with tempfile.TemporaryDirectory(prefix='cps_vm_lo_') as th:
            ver = first_line([real, '--version'], env=dict(os.environ, HOME=th))
        files = []
        for dp, dns, fns in os.walk(root, followlinks=False):
            for n in fns:
                p = os.path.join(dp, n)
                if stat.S_ISREG(os.lstat(p).st_mode):
                    files.append([os.path.relpath(p, root), os.lstat(p).st_size, fp.sha(p)])
        files.sort()
        lo['host'] = {'path': host, 'realpath': real, 'sha256': fp.sha(real), 'version': ver, 'install_root': str(root),
                      'tree_sha256': sha_bytes(json.dumps(files, separators=(',', ':')).encode()), 'files': len(files),
                      'closure_soffice_bin': fp.closure(str(root / 'program' / 'soffice.bin')),
                      'closure_libmergedlo': fp.closure(str(root / 'program' / 'libmergedlo.so'))}
    comp['libreoffice'] = lo
    pop = {}
    for t in ('pdftoppm', 'pdfinfo', 'pdftotext'):
        w = shutil.which(t)
        pop[t] = None if not w else {'realpath': os.path.realpath(w), 'sha256': fp.sha(w), 'closure': fp.closure(os.path.realpath(w))}
    w = shutil.which('pdftoppm')
    pop['version'] = first_line([w, '-v']) if w else None
    comp['poppler'] = pop
    ch = None
    bp = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
    if bp and os.path.isdir(bp):
        ch = {}
        for pat in ('chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell', 'chromium-*/chrome-linux64/chrome'):
            for p in sorted(Path(bp).glob(pat)):
                ch[str(p.relative_to(bp))] = fp.sha(p)
        hs = sorted(Path(bp).glob('chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell'))
        ch['closure'] = fp.closure(str(hs[0])) if hs else None
    pw = os.environ.get('CPS_PLAYWRIGHT_NODE_PATH')
    if pw:
        ch = ch or {}
        for pk in ('playwright/package.json', 'playwright-core/package.json'):
            p = Path(pw) / pk
            ch[pk] = fp.sha(p) if p.is_file() else None
    comp['chromium'] = ch
    fc = os.environ.get('FONTCONFIG_FILE')
    fonts = {'fontconfig_file_sha256': fp.sha(fc) if fc and os.path.isfile(fc) else None, 'files': None}
    fcl = shutil.which('fc-list')
    if fcl:
        try:
            out = subprocess.run([fcl, '--format', '%{file}\n'], capture_output=True, text=True, timeout=120).stdout
            fonts['files'] = sorted([p, fp.sha(p)] for p in set(x for x in out.splitlines() if x.strip()))
        except (OSError, subprocess.SubprocessError):
            pass
    comp['fonts'] = fonts
    libc = None
    try:
        for ln in Path('/proc/self/maps').read_text().splitlines():
            parts = ln.split()
            if parts and parts[-1].startswith('/') and os.path.basename(parts[-1]).startswith('libc.so'):
                libc = parts[-1]
                break
    except OSError:
        pass
    try:
        gv = os.confstr('CS_GNU_LIBC_VERSION')
    except (ValueError, OSError):
        gv = None
    comp['glibc'] = {'version': gv, 'libc': libc, 'sha256': fp.sha(libc) if libc else None}
    try:
        ls = subprocess.run(['git', '-C', str(HELPER_REPO), 'ls-files', '-s', 'research/export', 'deploy/writer_route'],
                            capture_output=True, timeout=120).stdout
        comp['export_tree'] = sha_bytes(ls)
    except (OSError, subprocess.SubprocessError):
        comp['export_tree'] = None
    env_sh = lay.tools / 'env.sh'
    comp['env_sh_sha256'] = sha_file(env_sh) if env_sh.is_file() else None
    full = {'schema': 'cps.vm-fingerprint.v1', 'components': comp}
    return sha_bytes(json.dumps(comp, sort_keys=True, separators=(',', ':')).encode('utf-8')), full


# ------------------------------------------------------------------ context
class Ctx:
    def __init__(self, need_session=True):
        self.lay = lay = Layout()
        check_layout_basic(lay)
        self.rel_raw, self.rel, self.mode, self.cfg = None, None, 'setup', None
        if lay.release_path.is_file():
            self.load_release()
        self.index = Index(lay.index_path)
        self.state = read_state(lay)
        if need_session and (not isinstance(self.state, dict) or self.state.get('boot_id') != current_boot_id()):
            refuse('NO_SESSION', 'run session_start.sh first (a session of this boot)')

    def load_release(self):
        lay = self.lay
        self.rel_raw = lay.release_path.read_bytes()
        try:
            self.rel = sjson(self.rel_raw)
        except (ValueError, UnicodeDecodeError):
            stop('KIT_RELEASE_INVALID', 'runtime/RELEASE.json is not strict JSON')
        self.mode = check_layout_release(lay, self.rel)
        load_runner()
        self.cfg = load_config(lay)

    @property
    def V(self):
        return self.lay.V()

    @property
    def model(self):
        return (self.state or {}).get('operator_model') or 'unknown'

    def records_folder(self):
        return self.cfg['drive']['everyday' if self.mode == 'everyday' else 'qualification']

    def setup_folder(self):
        return self.cfg['drive']['setup']

    def save_state(self):
        write_state(self.lay, self.state)

    def admission_path(self):
        a = ((self.rel or {}).get('qualification') or {}).get('admissions') or []
        return a[0]['path'] if a else None

    def jobs_list(self):
        p = ((self.rel or {}).get('qualification') or {}).get('jobs_file')
        d = read_json_file(p) if p else None
        cases = d.get('cases') if isinstance(d, dict) else []
        return sorted(cases, key=lambda c: (c.get('order', 0), c.get('case_id')))


def clean_placed(ctx):
    """Section 4: remove folders a dead wrap prepare placed (FROZEN.json only, recorded sha256)."""
    p = ctx.lay.outbox / 'PLACED.json'
    if not p.is_file():
        return
    d = read_json_file(p) or []
    for e in d:
        jd = Path(e['job_dir'])
        if not os.path.lexists(jd):
            continue
        if not jd.is_dir() or jd.is_symlink():
            stop('PLACED_FROZEN_CHANGED', 'a placed FROZEN.json folder holds something else: do not delete anything; hand back case C')
        names = sorted(os.listdir(jd))
        fz = jd / 'FROZEN.json'
        # T-24: a folder this helper placed may be empty or hold a temporary file of an interrupted write_new
        rest = [n for n in names if n != 'FROZEN.json' and not (n.startswith('.tmp_') and n.endswith('_FROZEN.json'))]
        if rest or ('FROZEN.json' in names and (not fz.is_file() or fz.is_symlink() or sha_file(fz) != e['frozen_sha256'])):
            stop('PLACED_FROZEN_CHANGED', 'a placed FROZEN.json folder holds something else: do not delete anything; hand back case C')
        remove_tree(jd)
    p.unlink()


def placed_dirs(ctx):
    p = ctx.lay.outbox / 'PLACED.json'
    return {e['job_dir'] for e in (read_json_file(p) or [])} if p.is_file() else set()


# ------------------------------------------------------------------ job views
class JobView:
    def __init__(self, ctx, job_dir):
        self.ctx, self.dir = ctx, Path(os.path.abspath(job_dir))
        self.tag, self.case = ctx.lay.tag_of(self.dir)
        self.raw, self.rec = None, None
        rp = self.dir / 'RUN_RECORD.json'
        if rp.is_file():
            self.raw = rp.read_bytes()
            self.rec = read_json_file(rp)

    @property
    def exists(self):
        return self.dir.is_dir()

    @property
    def frozen(self):
        return (self.dir / 'FROZEN.json').is_file()

    def stages(self, name=None):
        return [s for s in (self.rec or {}).get('stages', []) if name is None or s.get('stage') == name]

    def completed(self):
        return [s for s in self.stages() if s.get('completed')]

    def last(self):
        c = self.completed()
        return c[-1] if c else None

    def last_next(self):
        s = self.last()
        return s.get('next') if s else None

    @property
    def reader(self):
        return (self.rec or {}).get('reader')

    def record_sha(self):
        return sha_bytes(self.raw) if self.raw is not None else None

    def freeze_done(self):
        c = self.completed()
        return bool(c) and c[-1]['stage'] == 'freeze' and c[-1]['result'] == 'FROZEN'

    def role(self):
        return STEP_ROLE.get(self.last_next())

    def g_attempt(self):
        return 1 + sum(1 for s in self.completed() if s['stage'] == 'interrupt' and s.get('next') == 'GENERATE')

    def output_dir(self, role):
        if role == 'S':
            return self.dir / 'scope' / 'reader' / 'output'
        if role == 'G':
            gen = CJ.generation_stage(self) if self.rec else None
            rd = ((gen or {}).get('facts', {}).get('generation') or {}).get('run_dir') if gen else None
            return self.dir / (rd or ('run/' + str(self.reader))) / 'output'
        return self.dir / 'qa' / 'visual_review'

    # duck typing for CJ.generation_stage(jd): it calls jd.done(name)
    def done(self, name):
        return [s for s in self.stages(name) if s.get('completed')]


def in_flight(ctx):
    """Job folders without FROZEN.json (placed folders excluded)."""
    pl = placed_dirs(ctx)
    return [d for d in ctx.lay.job_folders() if not (d / 'FROZEN.json').is_file() and str(d) not in pl]


def read_ledger(ctx):
    """(raw bytes, entries) of the local qualification ledger, or (None, []) when absent."""
    if not ctx.lay.ledger.is_file():
        return None, []
    try:
        with CJ.Ledger(ctx.lay.ledger, create=False, readonly=True) as led:
            return led.raw, list(led.entries)
    except CJ.Refused as r:
        stop('LEDGER_CHAIN_BROKEN', 'the local ledger does not verify', detail={'code': r.code})


class LedgerView:
    """Enough of cj.Ledger for cj.restart_problem and cj.in_place_restart_used."""
    def __init__(self, entries):
        self.entries = entries

    def of(self, kind, **match):
        return [e for e in self.entries if e.get('type') == kind and all(e.get(k) == v for k, v in match.items())]


def pkg_order(e):
    p = parse_name(e['name'])
    return (p['seq'], 1 if p['pkind'] == 'FZ' else 0, e.get('created_utc') or e.get('drive_created') or '')


def rejected_ids(ctx, name):
    """T-02: the Drive ids of a name that failed their own hash or archive check here (INDEX 'rejected' events) or in an
    earlier restore (the rejected_copies of any INCIDENT this VM knows)."""
    rej = {e.get('drive_id') for e in ctx.index.events if e['event'] == 'rejected' and e['name'] == name}
    for i in ctx.index.of('incident'):
        for r in ((i.get('content') or {}).get('rejected_copies') or []):
            if isinstance(r, dict) and r.get('name') == name and r.get('drive_id'):
                rej.add(r['drive_id'])
    return rej


def dead(ctx, name, lst=None):
    """A name all of whose listed copies were rejected (and no local payload of it exists). With lst, the copies are
    that listing's (a copy this VM never examined keeps the name alive)."""
    ids = {f['id'] for f in lst.by.get(name, [])} if lst is not None else set(ctx.index.copies.get(name, {}))
    e = ctx.index.get(name)
    if e and e.get('origin') in ('made', 'restored'):
        return False
    return bool(ids) and ids <= rejected_ids(ctx, name)


def dead_names(ctx, names, lst=None):
    return {n for n in names if dead(ctx, n, lst)}


def packages(ctx, tag=None, case=None, chain=None):
    out = []
    for e in ctx.index.of('package'):
        p = parse_name(e['name'])
        if tag is not None and p['tag'] != tag:
            continue
        if case is not None and p['case'] != case:
            continue
        if chain is not None and chain_of(p['tag']) != chain:
            continue
        if dead(ctx, e['name']):
            continue
        out.append(e)
    return sorted(out, key=pkg_order)


def newest_package(ctx, tag=None, case=None, chain=None):
    ps = packages(ctx, tag, case, chain)
    return ps[-1] if ps else None


def starts(ctx, tag, role, case):
    return [e for e in ctx.index.of('start') if e.get('tag') == tag and e.get('role') == role and e.get('case_id') == case]


def newest_start(ctx, tag, role, case):
    ss = starts(ctx, tag, role, case)
    if not ss:
        return None
    top = max(e.get('attempt') or 0 for e in ss)
    cand = [e for e in ss if e.get('attempt') == top]
    sup = {(e.get('content') or {}).get('supersedes') for e in ss}
    free = [e for e in cand if e['name'] not in sup]
    return (free or cand)[-1]


def ai_all(ctx, tag, role, attempt, case):
    return [e for e in ctx.index.of('ai') if e.get('tag') == tag and e.get('role') == role and e.get('attempt') == attempt
            and e.get('case_id') == case]


def ai_lost(ctx, tag, role, attempt, case):
    """T-01 (spec 6.3 step 13): the names of the newest revision of this attempt's AI archive when every listed copy
    of each failed its check (it reached Drive damaged: the output counts as written and lost, O46), else []."""
    al = ai_all(ctx, tag, role, attempt, case)
    if not al:
        return []
    top = max(parse_name(e['name'])['revision'] for e in al)
    newest = [e for e in al if parse_name(e['name'])['revision'] == top]
    if all(dead(ctx, e['name']) for e in newest):
        return [e['name'] for e in newest]
    return []


def ai_archives(ctx, tag, role, attempt, case):
    """The intact archives of an attempt in revision order; none when the newest revision is lost (an earlier revision
    never stands in for it, T-01)."""
    if ai_lost(ctx, tag, role, attempt, case):
        return []
    out = [e for e in ai_all(ctx, tag, role, attempt, case) if not dead(ctx, e['name'])]
    return sorted(out, key=lambda e: parse_name(e['name'])['revision'])


def incidents(ctx):
    return [e for e in ctx.index.of('incident') if isinstance(e.get('content'), dict)]


def resolving(ctx, start_name):
    inc = [e for e in incidents(ctx) if e['content'].get('start_note') == start_name
           and e['content'].get('classification') in ('AI_NO_CONVERSATION', 'AI_NOTHING_WRITTEN', 'AI_WRITTEN_LOST')]
    if not inc:
        return None
    lost = [e for e in inc if e['content'].get('classification') == 'AI_WRITTEN_LOST']
    return (lost or inc)[-1]


def link_of(ctx, start_name):
    for e in ctx.index.of('link'):
        if (e.get('content') or {}).get('start_note') == start_name:
            return e
    return None


def frozen_copy(ctx, tag, case):
    p = ctx.lay.frozen_json / f'{tag}_{case}_FROZEN.json'
    return p.read_bytes() if p.is_file() else None


def flags_copy(ctx, tag, case):
    return read_json_file(ctx.lay.frozen_json / f'{tag}_{case}_FLAGS.json') or {}


def restart_eligible(led, prev, frozen_bytes):
    """5.17 rule 7: cj.restart_problem, completed with the three file-dependent checks on frozen_bytes. None = eligible."""
    r = CJ.restart_problem(led, prev)
    if r != UNREADABLE_FROZEN:
        return r
    if frozen_bytes is None:
        return UNREADABLE_FROZEN
    try:
        listed = {f.get('path') for f in CJ.strict_json(frozen_bytes, 'FROZEN.json').get('files') or [] if isinstance(f, dict)}
    except (CJ.Refused, AttributeError):
        return UNREADABLE_FROZEN
    fz = led.of('freeze', job_dir=prev)
    if sha_bytes(frozen_bytes) != fz[-1].get('frozen_sha256'):
        return "the earlier folder's FROZEN.json is not the one the ledger recorded"
    if listed & set(CJ.RESPONSE_WITNESSES):
        return 'the earlier run froze a scope reader or generator response'
    if listed & set(CJ.WRITTEN_RESPONSES):
        return 'the earlier run\'s conversation wrote its response file (rule 3 restarts only before the response is written)'
    return None


# ------------------------------------------------------------------ status planning (spec 5.17)
class Plan:
    def __init__(self):
        self.block = Block()
        self.wrap = None            # {'sub', 'tag', 'case', 'job_dir', 'pending'} when the next step is a runner command
        self.code = EXIT_OK

    def run(self, cmd):
        self.block.next('RUN ' + cmd) if not self.block.tail else self.block.then('RUN ' + cmd)

    def act(self, action):
        self.block.next(action) if not self.block.tail else self.block.then(action)


def lock_free(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return True
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


def transcript_path(ctx, case, tag, role, attempt):
    return ctx.lay.transcripts / f'{case}_{tag}_{role}{attempt}.txt'


def conv_token(ctx, start_name):
    lk = link_of(ctx, start_name) if start_name else None
    c = (lk or {}).get('content', {}).get('conversation') if lk else None
    return q(c) if c else "'{CONVERSATION_ID}'"


def freeze_line(ctx, jd):
    return f'{ctx.V} wrap freeze --job-dir {jd} --operator-model {q(ctx.model)}'


def prepare_line(ctx, case, root, reader):
    lay = ctx.lay
    jdir = lay.runtime / 'qualification' / 'jobs' / case
    return (f'{ctx.V} wrap prepare --release {lay.release_path} --job {jdir}/JOB.json --job-title-file {jdir}/JOB_TITLE.json '
            f'--jobs-root {lay.qual / root} --reader {reader} --qualification --admission {ctx.admission_path()} '
            f'--operator-model {q(ctx.model)}')


def consuming_line(ctx, jv, role, start):
    """The wrap that consumes an archived AI output (5.9), or None for G without its generation record."""
    D, V, M = jv.dir, ctx.V, q(ctx.model)
    sc = (start or {}).get('content') or {}
    if role == 'S':
        return (f'{V} wrap scope-finish --job-dir {D} --reader-response {D}/scope/reader/output/SCOPE_READER_RESPONSE.json '
                f'--reader-prompt-sha256 {sc.get("prompt_sha256")} --reader-conversation-id {conv_token(ctx, start["name"])} '
                f'--operator-model {M}')
    if role == 'V':
        return (f'{V} wrap visual-record --job-dir {D} --review {D}/qa/visual_review/VISUAL_REVIEW.json '
                f'--reviewer-conversation-id {conv_token(ctx, start["name"])} --operator-model {M}')
    gr = D / 'run' / 'GENERATION_RECORD.json'
    if not gr.is_file():
        return None
    g = read_json_file(gr) or {}
    model = q(g['model']) if isinstance(g.get('model'), str) and g.get('model') else "'{GENERATOR_MODEL}'"
    resp = jv.output_dir('G') / 'response.json'
    line = (f'{V} wrap finish --job-dir {D} --response {resp} --generator-model {model} '
            f'--generation-record {gr}')
    if g.get('transcript_status') == 'exported':
        att = (start or {}).get('attempt') or 1
        tp = transcript_path(ctx, jv.case, jv.tag, 'G', att)
        if tp.is_file():
            line += f' --transcript {tp}'
    return line + f' --operator-model {M}'


def gen_record_lines(ctx, plan, jv, attempt):
    D = jv.dir
    plan.act(f'WRITE_GENERATION_RECORD path={D}/run/GENERATION_RECORD.json example={ctx.lay.repo}/deploy/run/GENERATION_RECORD.example.json')
    plan.act(f'EXPORT_TRANSCRIPT to={transcript_path(ctx, jv.case, jv.tag, "G", attempt)}')
    plan.run(f'{ctx.V} status')


def interrupt_times(ctx, start, inc):
    sc = start.get('content') or {}
    t0 = parse_utc(sc.get('created_utc'))
    lk = link_of(ctx, start['name'])
    ls = parse_utc(((lk or {}).get('content') or {}).get('started_utc'))
    if ls is not None:
        up = ls.replace(microsecond=0) + (datetime.timedelta(seconds=1) if ls.microsecond else datetime.timedelta(0))
        t0 = max(t0, up) if t0 else up
    t1 = now_dt().replace(microsecond=0)
    return t0, t1


def role_plan(ctx, plan, jv, role):
    """5.17 rule 5 for a job whose last completed stage opened a conversation of role."""
    V, D = ctx.V, jv.dir
    T = newest_start(ctx, jv.tag, role, jv.case)
    if role == 'G' and T is not None and (T.get('attempt') or 1) < jv.g_attempt():
        T = None
    if role == 'V':
        last = jv.stages()[-1] if jv.stages() else None
        archs = ai_archives(ctx, jv.tag, 'V', T['attempt'], jv.case) if T else []
        if last and last['stage'] == 'visual-record' and not last.get('completed') and 'REVIEW_INCOMPLETE' in (last.get('codes') or []) \
                and archs and last['seq'] > ((archs[-1].get('meta') or {}).get('record_seq_at_archive') or 0):
            plan.act('CONTINUE_CONVERSATION role=V')
            plan.run(f'{V} ai-archive --job-dir {D} --role V --revision')
            return
    if T is None:
        plan.run(f'{V} start-note --job-dir {D} --role {role}')
        return
    att = T.get('attempt') or 1
    inc = resolving(ctx, T['name'])
    cls = inc['content'].get('classification') if inc else None
    if cls == 'AI_NO_CONVERSATION':
        plan.run(f'{V} start-note --job-dir {D} --role {role}')
        return
    if cls == 'AI_WRITTEN_LOST':
        plan.run(freeze_line(ctx, D))
        plan.wrap = {'sub': 'freeze', 'tag': jv.tag, 'case': jv.case, 'job_dir': str(D), 'pending': False}
        if ctx.mode == 'everyday':
            plan.act('STOP_AFTER_FREEZE code=EVERYDAY_AI_OUTPUT_LOST')
        return
    if cls == 'AI_NOTHING_WRITTEN':
        if role == 'V':
            if att == 1:
                plan.run(f'{V} start-note --job-dir {D} --role V')
            else:
                plan.run(freeze_line(ctx, D))
                plan.wrap = {'sub': 'freeze', 'tag': jv.tag, 'case': jv.case, 'job_dir': str(D), 'pending': False}
            return
        if ctx.mode == 'qualification' and CJ.restart_used_here(jv) is None:
            t0, t1 = interrupt_times(ctx, T, inc)
            if t0 is None or t1 < t0:
                plan.act('WAIT until=' + iso((t0 or now_dt()).replace(microsecond=0) + datetime.timedelta(seconds=1)))
                plan.run(f'{V} status')
                return
            reason = 'TECHNICAL_VM_RESET' if inc['content'].get('after_restore') else 'TECHNICAL_CONVERSATION_BROKE'
            conv = inc['content'].get('conversation')
            plan.run(f'{V} wrap interrupt --job-dir {D} --reason {reason} --started-utc {iso(t0)} --ended-utc {iso(t1)} '
                     f'--conversation-id {q(conv) if conv else conv_token(ctx, T["name"])} --operator-model {q(ctx.model)}')
            plan.wrap = {'sub': 'interrupt', 'tag': jv.tag, 'case': jv.case, 'job_dir': str(D), 'pending': False}
            return
        plan.run(freeze_line(ctx, D))
        plan.wrap = {'sub': 'freeze', 'tag': jv.tag, 'case': jv.case, 'job_dir': str(D), 'pending': False}
        return
    archs = ai_archives(ctx, jv.tag, role, att, jv.case)
    if not archs and ai_lost(ctx, jv.tag, role, att, jv.case):
        written_lost_lines(ctx, plan, jv, role, T)
        return
    if not archs:
        plan.act(f'WAIT_FOR_CONVERSATION role={role}')
        plan.run(f'{V} ai-archive --job-dir {D} --role {role}')
        return
    a = archs[-1]
    meta = a.get('meta') or {}
    out = jv.output_dir(role)
    cur = tree_sha(tree_list(out)) if out.is_dir() else None
    if cur != a.get('tree_sha256'):
        plan.run(f'{V} ai-archive --job-dir {D} --role {role}')
        return
    if meta.get('response_present'):
        line = consuming_line(ctx, jv, role, T)
        if line is None:
            gen_record_lines(ctx, plan, jv, att)
            return
        plan.run(line)
        plan.wrap = {'sub': {'S': 'scope-finish', 'G': 'finish', 'V': 'visual-record'}[role], 'tag': jv.tag, 'case': jv.case,
                     'job_dir': str(D), 'pending': False}
        return
    nothing_written_lines(ctx, plan, jv, role, att, T, meta)


def written_lost_lines(ctx, plan, jv, role, T):
    """T-01: the AI archive of this attempt reached Drive damaged: only AI_WRITTEN_LOST (O46), never a new conversation."""
    plan.act(f'CONFIRM_CONVERSATION_ENDED role={role}')
    plan.run(f'{ctx.V} incident --classification AI_WRITTEN_LOST --job-dir {jv.dir} --role {role} '
             f'--conversation {conv_token(ctx, T["name"])} --conversation-ended')


def nothing_written_lines(ctx, plan, jv, role, att, T, meta):
    V, D = ctx.V, jv.dir
    tp = transcript_path(ctx, jv.case, jv.tag, role, att)
    conv = conv_token(ctx, T['name'])
    plan.act(f'CONFIRM_CONVERSATION_ENDED role={role}')
    if meta.get('unexpected') or not ctx.cfg['transcript_export']:
        plan.run(f'{V} incident --classification AI_WRITTEN_LOST --job-dir {D} --role {role} --conversation {conv} --conversation-ended')
        return
    plan.act(f'EXPORT_TRANSCRIPT to={tp}')
    # r2 R2-01: the export may fail; without a transcript doubt counts as written, so both lines are printed as options
    plan.act('CHOOSE_FROM_TRANSCRIPT')
    plan.block.option('NOTHING_WRITTEN', f'RUN {V} incident --classification AI_NOTHING_WRITTEN --job-dir {D} --role {role} '
                                         f'--conversation {conv} --conversation-ended --transcript {tp}')
    plan.block.option('WRITTEN_OR_DOUBT', f'RUN {V} incident --classification AI_WRITTEN_LOST --job-dir {D} --role {role} '
                                          f'--conversation {conv} --conversation-ended')


def run_failed_by_reset(ctx, tag, case):
    """The run has failed by reset divergence: its newest package says so, or an INCIDENT of it forces it (r2 C2/M1)."""
    prev = newest_package(ctx, tag, case)
    if ((prev or {}).get('meta') or {}).get('reset_diverged'):
        return True
    return any(i['content'].get('forces_reset_diverged') for i in incidents(ctx) if concerns(i, tag, case))


def job_plan(ctx, plan, jv):
    V, D = ctx.V, jv.dir
    if run_failed_by_reset(ctx, jv.tag, jv.case):      # r2 M1: only freeze may run; print it, never a refused line
        plan.run(freeze_line(ctx, D))
        plan.wrap = {'sub': 'freeze', 'tag': jv.tag, 'case': jv.case, 'job_dir': str(D), 'pending': False}
        if ctx.mode == 'everyday':
            plan.act('STOP_AFTER_FREEZE code=EVERYDAY_RESET_DIVERGED')
        return
    if (D / CJ.MARKER_NAME).exists() and lock_free(D):
        plan.run(freeze_line(ctx, D))
        plan.wrap = {'sub': 'freeze', 'tag': jv.tag, 'case': jv.case, 'job_dir': str(D), 'pending': False}
        return
    if jv.freeze_done() and not jv.frozen:
        plan.run(freeze_line(ctx, D))
        plan.wrap = {'sub': 'freeze', 'tag': jv.tag, 'case': jv.case, 'job_dir': str(D), 'pending': False}
        return
    nx = jv.last_next()
    role = STEP_ROLE.get(nx)
    if role:
        return role_plan(ctx, plan, jv, role)
    if nx == 'DELIVER_CHECK' and ctx.mode == 'everyday':
        plan.act('WAIT_FOR_USER_REQUEST')
        plan.act(f'ASK_USER_IF_SEND_NOW case={jv.case}')
        plan.block.option('SEND_NOW', f'RUN {V} wrap deliver-check --job-dir {D} --operator-model {q(ctx.model)}')
        plan.block.option('NOT_NOW', 'RUN ' + freeze_line(ctx, D))
        plan.wrap = {'sub': 'deliver-check', 'tag': jv.tag, 'case': jv.case, 'job_dir': str(D), 'pending': False}
        return
    if nx == 'DELIVER' and ctx.mode == 'everyday':
        notes = [e for e in ctx.index.of('delivery') if e.get('case_id') == jv.case and (e.get('content') or {}).get('run_id') == jv.tag]
        sent = [e for e in notes if parse_name(e['name'])['which'] == 'SENT']
        prep = [e for e in notes if parse_name(e['name'])['which'] == 'PREPARED']
        if sent:
            plan.run(freeze_line(ctx, D))
            plan.wrap = {'sub': 'freeze', 'tag': jv.tag, 'case': jv.case, 'job_dir': str(D), 'pending': False}
        elif prep:
            pn = prep[-1]['name']
            plan.act(f'ASK_USER_IF_RECEIVED case={jv.case}')
            plan.block.option('RECEIVED', f"RUN {V} delivery-note --job-dir {D} --sent --prepared-note {pn} --profile-folder '{{PROFILE_FOLDER}}'")
            plan.block.option('NOT_RECEIVED', f"SEND_PREPARED_COPY_AGAIN then RUN {V} delivery-note --job-dir {D} --sent --prepared-note {pn} "
                                              f"--profile-folder '{{PROFILE_FOLDER}}'")
        else:
            dsha = ((read_json_file(D / 'qa' / 'SAVED_QA.json') or {}).get('deliverable_xlsx') or {}).get('sha256')
            plan.act(f'DELIVER folder={D}/export/writer sha256={dsha}')
            plan.run(f"{V} delivery-note --job-dir {D} --prepared --copy '{{COPY_FILE}}' --log '{{LOG_FILE}}' "
                     f"--profile-folder '{{PROFILE_FOLDER}}'")
        return
    if nx is None or nx == 'FREEZE' or str(nx).startswith('STOP_') or nx == 'OWNER_DECISION' or nx == 'DONE':
        plan.run(freeze_line(ctx, D))
        plan.wrap = {'sub': 'freeze', 'tag': jv.tag, 'case': jv.case, 'job_dir': str(D), 'pending': False}
        return
    plan.run(freeze_line(ctx, D))
    plan.wrap = {'sub': 'freeze', 'tag': jv.tag, 'case': jv.case, 'job_dir': str(D), 'pending': False}


def fz_for(ctx, tag, case):
    fz = [e for e in packages(ctx, tag, case) if parse_name(e['name'])['pkind'] == 'FZ']
    return fz[-1] if fz else None


def fz_pending(ctx):
    p = ctx.lay.outbox / 'FZ_PENDING.json'
    return read_json_file(p) or [] if p.is_file() else []


def eligible_restart(ctx, plan, led, prev_entry):
    """None when the run of prev_entry may be restarted; else a reason. May add a DOWNLOAD (plan.code = EXIT_NEED)."""
    prev = prev_entry['job_dir']
    tag, case = ctx.lay.tag_of(prev)
    fl = flags_copy(ctx, tag, case)
    fz = fz_for(ctx, tag, case)
    diverged = bool(fl.get('reset_diverged') or ((fz or {}).get('meta') or {}).get('reset_diverged'))
    fb = None
    if Path(prev, 'FROZEN.json').is_file():
        fb = Path(prev, 'FROZEN.json').read_bytes()
    else:
        fb = frozen_copy(ctx, tag, case)
    if fb is None and CJ.restart_problem(led, prev) == UNREADABLE_FROZEN:
        if fz is None:
            return 'no FZ package of the earlier run is known'
        p = ctx.lay.inbox / fz['name']
        if p.is_file() and h8(sha_file(p)) == parse_name(fz['name'])['pkg8']:
            info = read_fz_member(p)
            diverged = diverged or info['reset_diverged']
            fb = info['frozen']
            if fb is not None:                      # T-21: keep the copy (frozen_json) and empty the inbox
                ctx.lay.frozen_json.mkdir(parents=True, exist_ok=True)
                write_atomic(ctx.lay.frozen_json / f'{tag}_{case}_FROZEN.json', fb)
                write_atomic(ctx.lay.frozen_json / f'{tag}_{case}_FLAGS.json',
                             note_bytes({'reset_diverged': bool(info['reset_diverged']), 'fz': fz['name']}))
            p.unlink()
        else:
            plan.block.download(fz.get('drive_id'), fz['name'], p)
            plan.code = EXIT_NEED
            return 'download needed'
    why = restart_eligible(led, prev, fb)
    if diverged:
        # T-18: the helper never restarts a diverged run; when the runner would still expect the restart (it does not
        # know divergence), reader B's prepare can never pass: an owner decision (case C)
        return 'reset diverged, runner expects the restart' if why is None else 'reset diverged'
    return why


def read_fz_member(path):
    a = Archive(path, ('MANIFEST.json', 'ledger', 'job'))
    try:
        check_pkg_manifest(a)
        man = a.manifest
        fb = a.read('job/FROZEN.json') if 'job/FROZEN.json' in a.by else None
        return {'frozen': fb, 'reset_diverged': bool(man.get('reset_diverged')), 'manifest': man}
    finally:
        a.close()


def qual_plan(ctx, plan):
    V, lay = ctx.V, ctx.lay
    raw, entries = read_ledger(ctx)
    led = LedgerView(entries)
    cases = ctx.jobs_list()
    adm = ctx.admission_path()
    for R in 'AB':
        for c in cases:
            if c.get('nonattempt') and not led.of('nonattempt', case_id=c['case_id'], reader=R):
                plan.run(f'{V} wrap nonattempt --release {lay.release_path} --admission {adm} --case {c["case_id"]} --reader {R} '
                         f'--jobs-root {lay.qual / ("nonattempts_" + R)} --operator-model {q(ctx.model)}')
                plan.wrap = {'sub': 'nonattempt', 'tag': 'NA-' + R, 'case': c['case_id'], 'pending': True,
                             'job_dir': str(lay.job_dir('NA-' + R, c['case_id']))}
                return
    for R in 'AB':
        for c in cases:
            if c.get('nonattempt'):
                continue
            cid = c['case_id']
            runs = led.of('prepare', case_id=cid, reader=R)
            if not runs:
                if R == 'B':
                    ar = led.of('prepare', case_id=cid, reader='A')
                    if len(ar) == 1 and led.of('freeze', job_dir=ar[0]['job_dir']):
                        why = eligible_restart(ctx, plan, led, ar[0])
                        if plan.code == EXIT_NEED:
                            return
                        if why == 'reset diverged, runner expects the restart':
                            stop('QUALIFICATION_DIVERGED_RESTART_CONFLICT', 'reader A\'s run failed by reset divergence after a '
                                 'stop the runner would restart; reader B cannot be prepared without an owner decision: hand back case C',
                                 detail={'case_id': cid})
                        if why is None:
                            plan.run(prepare_line(ctx, cid, 'A_restart1', 'A'))
                            plan.wrap = {'sub': 'prepare', 'tag': 'A-restart1', 'case': cid, 'pending': True,
                                         'job_dir': str(lay.job_dir('A-restart1', cid))}
                            return
                plan.run(prepare_line(ctx, cid, R, R))
                plan.wrap = {'sub': 'prepare', 'tag': R, 'case': cid, 'pending': True, 'job_dir': str(lay.job_dir(R, cid))}
                return
            if len(runs) == 1 and led.of('freeze', job_dir=runs[0]['job_dir']):
                why = eligible_restart(ctx, plan, led, runs[0])
                if plan.code == EXIT_NEED:
                    return
                if why is None:
                    tag = R + '-restart1'
                    plan.run(prepare_line(ctx, cid, R + '_restart1', R))
                    plan.wrap = {'sub': 'prepare', 'tag': tag, 'case': cid, 'pending': True, 'job_dir': str(lay.job_dir(tag, cid))}
                    return
    plan.run(f'{V} final')


def everyday_prepare_line(ctx, tag, case):
    lay = ctx.lay
    d = lay.everyday_inputs / case
    return (f'{ctx.V} wrap prepare --release {lay.release_path} --job {d}/JOB.json --job-title-file {d}/JOB_TITLE.json '
            f'--jobs-root {lay.jobs / tag[1:]} --operator-model {q(ctx.model)}')


def inputs_manifest(e):
    """The MANIFEST.json of an INPUTS archive (INDEX content when made here, else read from the payload)."""
    c = e.get('content')
    if isinstance(c, dict) and c.get('schema') == 'cps.vm-inputs.v1':
        return c
    p = e.get('payload')
    if p and Path(p).is_file():
        a = Archive(p, ('MANIFEST.json', 'inputs'))
        try:
            return a.manifest
        finally:
            a.close()
    return None


def inputs_shas(d, man):
    out = {}
    for n in (man or {}).get('files') or {}:
        p = Path(d) / n
        out[n] = sha_file(p) if p.is_file() and not p.is_symlink() else None
    return out


def run_inputs(ctx, tag):
    """r2 M5: the INPUTS entry that a run's prepare uses: the newest INPUTS of the run whose manifest can be read (job-start
    may give a run new inputs after the runner refused its prepare before making the folder)."""
    es = [e for e in ctx.index.of('inputs') if e.get('tag') == tag]
    es = [e for e in es if inputs_manifest(e) is not None] or es
    return max(es, key=lambda e: (max(e.get('created_utc') or '', e.get('drive_created') or ''), e['name'])) if es else None


def prepare_refusal(ctx, e):
    """r2 M5: the runner code that refused this INPUTS run's prepare before any job folder existed (INDEX prepare_refused
    for exactly this INPUTS name), else None."""
    ev = [x for x in ctx.index.events if x['event'] == 'prepare_refused' and x['name'] == (e or {}).get('name')]
    return ev[-1].get('code') if ev else None


def everyday_pending_prepare(ctx):
    """T-08: the newest INPUTS run with no package and no job folder: its prepare is the job in flight."""
    runs = sorted(ctx.index.of('inputs'), key=lambda e: e.get('tag') or '')
    for e in reversed(runs):
        tag, case = e.get('tag'), e.get('case_id')
        if not tag or not case:
            continue
        if packages(ctx, tag) or ctx.lay.job_dir(tag, case).exists():
            return None
        return e
    return None


def everyday_plan(ctx, plan):
    V = ctx.V
    pend = everyday_pending_prepare(ctx)
    if pend is not None:
        tag, case = pend['tag'], pend['case_id']
        rc = prepare_refusal(ctx, run_inputs(ctx, tag))
        if rc is not None:                          # r2 M5: the inputs need fixing; job-start gives the run new inputs
            plan.act(f'FIX code=RUNNER_{rc}')
            plan.run(f'{V} job-start --case {case}')
            return
        plan.run(everyday_prepare_line(ctx, tag, case))
        plan.wrap = {'sub': 'prepare', 'tag': tag, 'case': case, 'pending': True, 'job_dir': str(ctx.lay.job_dir(tag, case))}
        return
    runs = {}
    for e in ctx.index.of('inputs'):
        runs[e['tag']] = e
    for tag in sorted(runs, reverse=True):
        e = runs[tag]
        p = parse_name(e['name'])
        if p['restart_of']:
            continue
        restarted = any(parse_name(x['name'])['restart_of'] == tag for x in ctx.index.of('inputs'))
        inc = [i for i in incidents(ctx) if i['content'].get('tag') == tag and i['content'].get('classification') == 'AI_NOTHING_WRITTEN'
               and i['content'].get('role') in ('S', 'G')]
        fz = fz_for(ctx, tag, p['case'])
        if inc and not restarted and fz is not None:
            plan.run(f'{V} job-start --case {p["case"]} --restart-of {tag} --incident {inc[-1]["name"]}')
            return
        break
    plan.act('WAIT_FOR_USER_REQUEST')
    plan.run(f"{V} job-start --case '{{CASE}}'")


def plan_status(ctx, ignore_pending=False, in_worker=False, past_fz_pending=False):
    """The first applicable rule of 5.17 (0, 1 and 3-8; rule 2 is incident_plan). past_fz_pending (r2 M2): skip the
    verification-only evict of FZ_PENDING to see the runner command after it (what a reset may have lost)."""
    plan = Plan()
    V, lay, st = ctx.V, ctx.lay, ctx.state or {}
    if (lay.outbox / 'DETACHED.json').is_file() and not in_worker and detached_live(lay):
        plan.run(f'{V} wait')
        return plan
    if not st.get('fingerprint_pass'):
        run = newest_selftest(ctx)
        if run and run.get('exit') is not None and run.get('session_note') == st.get('session_note'):
            plan.run(f'{V} fingerprint-pass')
        else:
            plan.run(f'{V} selftest')
        return plan
    if st.get('pending_incident') and not ignore_pending:
        return incident_plan(ctx)
    if st.get('restore_recheck') and not ignore_pending:
        plan.block.listing(ctx.records_folder(), lay.inbox / 'DRIVE_LISTING.json')
        plan.run(f'{V} recheck')
        return plan
    if ctx.mode == 'setup':
        plan.act('DONE')
        return plan
    if ctx.mode == 'qualification' and not lay.ledger_dir.exists():
        lst = st.get('listing') or {}
        names = [parse_name(n) for n in lst.get('records', [])]
        blocked = any(p and p['kind'] in ('genesis', 'package', 'start', 'incident') for p in names)
        if ctx.cfg['expected_genesis'] is None and not blocked:
            plan.run(f'{V} genesis --first-ledger')
            return plan
        b = Block()
        stop('LISTING_MISSING_GENESIS', 'the records listing shows qualification history but no ledger is here: run session_start.sh again', block=b)
    fl = in_flight(ctx)
    if fl:
        job_plan(ctx, plan, JobView(ctx, fl[0]))
        return plan
    pl = placed_dirs(ctx)
    for d in lay.job_folders():
        if str(d) in pl:
            continue
        jv = JobView(ctx, d)
        fz = [e for e in packages(ctx, jv.tag, jv.case) if parse_name(e['name'])['pkind'] == 'FZ'
              and parse_name(e['name'])['frozen8'] == h8(sha_file(d / 'FROZEN.json'))]
        if not fz:
            plan.run(f'{V} package --job-dir {d}')
        else:
            plan.run(f'{V} evict --job-dir {d}')
        return plan
    for e in ([] if past_fz_pending else fz_pending(ctx)):
        plan.run(f'{V} evict --job-dir {e["job_dir"]}')
        return plan
    if ctx.mode == 'qualification':
        qual_plan(ctx, plan)
    else:
        everyday_plan(ctx, plan)
    return plan


def newest_selftest(ctx):
    runs = sorted(ctx.lay.outbox.glob('selftest_*/RUN.json')) if ctx.lay.outbox.is_dir() else []
    return read_json_file(runs[-1]) if runs else None


# ------------------------------------------------------------------ bind tokens (spec 1.2)
def saved_xlsx8(job_dir):
    d = read_json_file(Path(job_dir) / 'qa' / 'SAVED_QA.json')
    s = ((d or {}).get('deliverable_xlsx') or {}).get('sha256') if isinstance(d, dict) else None
    return h8(s) if isinstance(s, str) and len(s) >= 8 else '0'


def token_text(sub, tag, case, entry, xlsx8, diverged):
    codes8 = h8(sha_bytes(json.dumps(sorted(entry.get('codes') or [])).encode('utf-8')))
    step = str(entry.get('next') or '').split(' ')[0] or 'NONE'
    body = f'B1/{sub}/{tag}/{case}/{step}/{entry.get("result")}/{codes8}/{xlsx8}/{"D" if diverged else "N"}'
    return body + '/' + sha_bytes(body.encode('utf-8'))[:4]


def parse_token(tok):
    """The fields of a bind token, or None when malformed or its check digits fail. 'none' is a refusal."""
    if tok == 'none':
        return {'none': True}
    parts = tok.split('/')
    if len(parts) != 10 or parts[0] != 'B1' or parts[8] not in ('D', 'N'):
        return None
    body = '/'.join(parts[:9])
    if sha_bytes(body.encode('utf-8'))[:4] != parts[9]:
        return None
    return {'none': False, 'sub': parts[1], 'tag': parts[2], 'case': parts[3], 'step': parts[4], 'result': parts[5],
            'codes8': parts[6], 'xlsx8': parts[7], 'D': parts[8] == 'D', 'fields': parts[1:8]}


def stage_name(sub):
    return sub


def newest_completed(jv, sub):
    c = [s for s in jv.completed() if s['stage'] == stage_name(sub)]
    return c[-1] if c else None


# ------------------------------------------------------------------ situation after a restore (5.17 rule 2, 5.11)
def situation(ctx):
    """What the pending incident concerns: {'kind': open_start|archive_nothing|archived|runner|none, ...}."""
    fl = in_flight(ctx)
    jv = JobView(ctx, fl[0]) if fl else None
    if jv is not None:
        role = jv.role()
        if role:
            T = newest_start(ctx, jv.tag, role, jv.case)
            if role == 'G' and T is not None and (T.get('attempt') or 1) < jv.g_attempt():
                T = None
            if T is not None and resolving(ctx, T['name']) is None:
                archs = ai_archives(ctx, jv.tag, role, T['attempt'], jv.case)
                if not archs and ai_lost(ctx, jv.tag, role, T['attempt'], jv.case):
                    return {'kind': 'archive_lost', 'jv': jv, 'role': role, 'start': T,
                            'lost': ai_lost(ctx, jv.tag, role, T['attempt'], jv.case)}
                if not archs:
                    return {'kind': 'open_start', 'jv': jv, 'role': role, 'start': T}
                meta = archs[-1].get('meta') or {}
                if meta.get('response_present'):
                    inner = plan_status(ctx, ignore_pending=True)
                    return {'kind': 'archived', 'jv': jv, 'role': role, 'start': T, 'archive': archs[-1], 'wrap': inner.wrap,
                            'sub': CONSUMING_SUB[role]}
                return {'kind': 'archive_nothing', 'jv': jv, 'role': role, 'start': T, 'archive': archs[-1]}
    # r2 M2: an FZ_PENDING evict is verification only: the runner command after it (a prepare or nonattempt that may
    # have run before the reset) is what the incident concerns, so its seen token binds the re-run (O44)
    inner = plan_status(ctx, ignore_pending=True, past_fz_pending=True)
    if inner.wrap:
        return {'kind': 'runner', 'jv': jv, 'wrap': inner.wrap, 'sub': inner.wrap['sub']}
    return {'kind': 'none', 'jv': jv}


CONSUMING_SUB = {'S': 'scope-finish', 'G': 'finish', 'V': 'visual-record'}


def incident_plan(ctx):
    plan = Plan()
    V = ctx.V
    s = situation(ctx)
    jv = s.get('jv')
    jd = f' --job-dir {jv.dir}' if jv is not None and s['kind'] != 'none' else ''
    if s['kind'] == 'open_start':
        T, role = s['start'], s['role']
        att = T['attempt']
        tp = transcript_path(ctx, jv.case, jv.tag, role, att)
        conv = conv_token(ctx, T['name'])
        plan.act(f'CONFIRM_CONVERSATION_ENDED role={role}')
        plan.act(f'EXPORT_TRANSCRIPT to={tp}')
        plan.act('CHOOSE_FROM_TRANSCRIPT')
        if no_conversation_allowed(ctx, jv, role, T) in (None, 'AI_NO_CONVERSATION_REPEATED'):     # T-20: repeated -> STOP there
            plan.block.option('NO_CONVERSATION', f'RUN {V} incident --classification AI_NO_CONVERSATION{jd} --role {role} --conversation-ended')
        if ctx.cfg['transcript_export']:
            plan.block.option('NOTHING_WRITTEN', f'RUN {V} incident --classification AI_NOTHING_WRITTEN{jd} --role {role} '
                                                 f'--conversation {conv} --conversation-ended --transcript {tp}')
        plan.block.option('WRITTEN_OR_DOUBT', f'RUN {V} incident --classification AI_WRITTEN_LOST{jd} --role {role} '
                                              f'--conversation {conv} --conversation-ended')
        return plan
    if s['kind'] == 'archive_nothing':
        nothing_written_lines(ctx, plan, jv, s['role'], s['start']['attempt'], s['start'], s['archive'].get('meta') or {})
        return plan
    if s['kind'] == 'archive_lost':
        written_lost_lines(ctx, plan, jv, s['role'], s['start'])
        return plan
    if s['kind'] in ('archived', 'runner'):
        cls = 'AI_ARCHIVED' if s['kind'] == 'archived' else 'NON_AI_STAGE_LOST'
        role = f' --role {s["role"]}' if s['kind'] == 'archived' else ''
        plan.act('CHOOSE_SEEN_TOKENS')
        plan.block.option('SEEN', f"RUN {V} incident --classification {cls}{jd}{role} --seen '{{SEEN}}'")
        plan.block.option('NOT_SEEN', f'RUN {V} incident --classification {cls}{jd}{role} --not-seen')
        return plan
    plan.run(f'{V} incident --classification NONE_IN_FLIGHT')
    return plan


def no_conversation_allowed(ctx, jv, role, T):
    """None when AI_NO_CONVERSATION may be recorded for START T (5.11), else the refusal code."""
    if link_of(ctx, T['name']) is not None:
        return 'INCIDENT_LINK_EXISTS'
    out = jv.output_dir(role)
    if out.is_dir() and any(e[1] == 'file' for e in tree_list(out)):
        return 'INCIDENT_OUTPUT_NOT_EMPTY'
    if ai_all(ctx, jv.tag, role, T['attempt'], jv.case):          # T-01: an archive listed intact or damaged
        return 'INCIDENT_ARCHIVE_EXISTS'
    if any(e['content'].get('start_note') == T['name'] for e in incidents(ctx)):
        return 'INCIDENT_CHAIN_USED'
    if (T.get('content') or {}).get('supersedes'):
        return 'AI_NO_CONVERSATION_REPEATED'
    return None


def state_line(ctx):
    st = ctx.state or {}
    fl = in_flight(ctx) if ctx.rel else []
    jv = JobView(ctx, fl[0]) if fl else None
    seq = '-'
    if ctx.mode == 'qualification' and ctx.lay.ledger.is_file() and CJ:
        try:
            seq = str(len(read_ledger(ctx)[1]))
        except Halt:
            seq = 'broken'
    role = jv.role() if jv else None
    T = newest_start(ctx, jv.tag, role, jv.case) if jv and role else None
    restart = 'no'
    if jv and jv.rec and ctx.mode == 'qualification':
        restart = 'yes' if CJ.restart_used_here(jv) else 'no'
    return {'mode': ctx.mode, 'case': jv.case if jv else '-', 'tag': jv.tag if jv else '-', 'last_next': (jv.last_next() if jv else None) or '-',
            'ledger_seq': seq, 'attempt': (T or {}).get('attempt') or '-', 'restart_used': restart,
            'pending_incident': 'yes' if st.get('pending_incident') else 'no',
            'fingerprint_pass': 'yes' if st.get('fingerprint_pass') else 'no'}


def cmd_status(a):
    ctx = Ctx()
    plan = plan_status(ctx)
    b = plan.block
    b.result = {'command': 'status', 'mode': ctx.mode}
    b.state = state_line(ctx)
    b.code = plan.code
    return b


# ------------------------------------------------------------------ session kit (spec 2.3)
MANIFEST_ROW = re.compile(r'^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*`([0-9a-f]{64})`\s*\|', re.M)


def reports_folder(ctx_or_cfg):
    cfg = ctx_or_cfg.cfg if hasattr(ctx_or_cfg, 'cfg') else ctx_or_cfg
    setup = (cfg or {}).get('drive', {}).get('setup', 'CPS/setup')
    return setup.rsplit('/', 1)[0] + '/reports' if '/' in setup else 'reports'


def kit_members(zp):
    """The kit zip's members {path: bytes} after the archive rules (3.6) and SHA256SUMS (2.3)."""
    try:
        z = zipfile.ZipFile(zp)
    except (zipfile.BadZipFile, OSError):
        stop('KIT_NOT_VERIFIED', 'the session kit is not a zip file')
    out = {}
    with z:
        for i in z.infolist():
            n = i.filename
            mode = (i.external_attr >> 16) & 0o177777
            if n.endswith('/'):
                if unsafe_name(n.rstrip('/')):
                    stop('ARCHIVE_UNSAFE_MEMBER', 'kit', detail={'path': n[:200], 'why': 'path'})
                continue
            if unsafe_name(n):
                stop('ARCHIVE_UNSAFE_MEMBER', 'kit', detail={'path': n[:200], 'why': unsafe_name(n)})
            if mode and not (stat.S_ISREG(mode) or mode & 0o170000 == 0):
                stop('ARCHIVE_UNSAFE_MEMBER', 'kit', detail={'path': n[:200], 'why': 'type'})
            if mode & 0o7000:
                stop('ARCHIVE_UNSAFE_MEMBER', 'kit', detail={'path': n[:200], 'why': 'mode'})
            if n in out:
                stop('ARCHIVE_UNSAFE_MEMBER', 'kit', detail={'path': n[:200], 'why': 'duplicate'})
            out[n] = z.read(i)
    sums = out.pop('SHA256SUMS', None)
    if sums is None:
        stop('KIT_SUMS_MISMATCH', 'SHA256SUMS is missing')
    listed = {}
    for ln in sums.decode('utf-8', 'replace').splitlines():
        if not ln.strip():
            continue
        m = re.fullmatch(r'([0-9a-f]{64})  (.+)', ln)
        if not m:
            stop('KIT_SUMS_MISMATCH', 'SHA256SUMS line')
        listed[m.group(2)] = m.group(1)
    if set(listed) != set(out) or any(sha_bytes(out[k]) != v for k, v in listed.items()):
        stop('KIT_SUMS_MISMATCH', 'the kit members differ from SHA256SUMS')
    return out


def unpack_kit(lay, members, run_in_flight):
    rt = lay.runtime
    if rt.is_dir() and any(rt.iterdir()):
        have = {}
        for dp, dns, fns in os.walk(rt):
            for n in fns:
                p = Path(dp) / n
                have[p.relative_to(rt).as_posix()] = p.read_bytes()
        if have == members:
            return 'same'
        diff = {k for k in set(have) | set(members) if have.get(k) != members.get(k)}
        if diff == {'VM_HELPER_CONFIG.json'}:
            p = rt / 'VM_HELPER_CONFIG.json'
            write_atomic(p, members['VM_HELPER_CONFIG.json'], 0o444)
            return 'config'
        if run_in_flight:
            refuse('KIT_CHANGE_WITH_RUN_IN_FLIGHT', 'a different kit while a job folder exists: finish or evict the runs first')
        remove_tree(rt)
    rt.mkdir(parents=True, exist_ok=True)
    os.chmod(rt, 0o755)
    for k in sorted(members):
        p = rt / k
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'xb') as f:
            f.write(members[k])
        os.chmod(p, 0o444)
    for dp, dns, fns in os.walk(rt):
        for n in dns:
            os.chmod(Path(dp) / n, 0o755)
    return 'unpacked'


def session_kit(lay, inbox, block, state):
    man = inbox / 'cps' / 'FOLDER_MANIFEST.md'
    if not man.is_file():
        refuse('NEED_FOLDER_MANIFEST', 'download FOLDER_MANIFEST.md to BASE/inbox/cps/FOLDER_MANIFEST.md by hand')
    rows = [(p, int(n), h) for p, n, h in MANIFEST_ROW.findall(man.read_text(encoding='utf-8', errors='replace'))]
    kits = [r for r in rows if re.fullmatch(r'cps_runtime/SESSION_KIT_[A-Za-z0-9._-]+\.zip', r[0])]
    if len(kits) != 1:
        stop('KIT_NOT_IN_MANIFEST', 'FOLDER_MANIFEST.md must list exactly one cps_runtime/SESSION_KIT_<v>.zip')
    path, size, sha = kits[0]
    info = {'name': path.split('/')[-1], 'sha256': sha, 'repaired': False}
    if (state or {}).get('kit_sha256') == sha and lay.release_path.is_file():
        return info, 'same'
    zp = inbox / 'cps' / path
    if not zp.is_file():
        block.download('CPS_FOLDER_PATH', path, zp)
        need(block, 'NEED_KIT')
    vd = HELPER_REPO / 'deploy' / 'verify_drive_files.py'
    rep = inbox / 'repaired'
    p = subprocess.run([sys.executable, '-I', '-B', str(vd), str(man), str(inbox / 'cps'), '--repair-to', str(rep), path],
                       capture_output=True, text=True, timeout=3600)
    status = None
    for ln in p.stdout.splitlines():
        m = re.match(r'^(ok|MISSING|MISMATCH|REPAIRED|NOT REPAIRED)\s+(\S+)$', ln.strip())
        if m and m.group(2) == path:
            status = m.group(1)
    if status == 'ok':
        use = zp
    elif status == 'REPAIRED' and (rep / path).is_file():
        use = rep / path
        info['repaired'] = True
    else:
        stop('KIT_NOT_VERIFIED', 'the downloaded kit does not match FOLDER_MANIFEST.md and could not be repaired: tell the maintainer')
    members = kit_members(use)
    fl = [d for d in Layout().job_folders()]
    how = unpack_kit(lay, members, bool(fl))
    if info['repaired']:
        keep = lay.outbox / ('REPAIRED_' + info['name'])
        if not keep.exists():
            shutil.copyfile(use, keep)
        info['repaired_path'] = str(keep)
    return info, how


# ------------------------------------------------------------------ session (spec 5.1)
def sentinel_for(ctx, which):
    s = ctx.cfg['sentinels'][which]
    p = ctx.lay.runtime / 'sentinels' / s['name']
    return s, (p.read_bytes() if p.is_file() else None), p


def load_session_listing(ctx, path, folder, which, block):
    s, sb, sp = sentinel_for(ctx, which)
    if not path.is_file():
        block.listing(folder, path)
        need(block, 'SESSION_LISTING_MISSING')
    try:
        lst = parse_listing(path, folder, None, ctx.cfg, s, sb)
    except Halt as h:
        if h.code == 'LISTING_SENTINEL_MISSING' and s['upload_by_dot'] and sp.is_file() and \
                not (ctx.lay.outbox / f'SENTINEL_UPLOADED_{which}').is_file():
            block.upload(sp, folder)
            block.listing(folder, path)
            path.unlink()
            write_atomic(ctx.lay.outbox / f'SENTINEL_UPLOADED_{which}', b'1')
            need(block, 'SENTINEL_UPLOAD')
        if h.kind == 'REFUSED' and h.code.startswith('LISTING_'):
            relist(ctx, path, folder, None, h.code, h.hint, block)
        raise
    return lst                                      # the caller clears the set-aside copies once its own checks pass


def validate_pass(ctx, raw, fp_sha):
    try:
        d = sjson(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(d, dict) or d.get('schema') != 'cps.vm-fingerprint-pass.v1' or d.get('fingerprint_sha256') != fp_sha:
        return None
    s = d.get('selftest') or {}
    n = ctx.cfg['selftest_expected_tests']
    if s.get('failed_count') != 0 or s.get('tests') != n or s.get('passed_count') != n:
        return None
    return d


def detached_live(lay):
    """r2 R2-03: a DETACHED.json written in another boot names a worker that died with that boot: it is not waited for."""
    d = read_json_file(lay.outbox / 'DETACHED.json') if (lay.outbox / 'DETACHED.json').is_file() else None
    return not isinstance(d, dict) or d.get('boot_id') == current_boot_id()


def cleanup_leftovers(lay):
    """T-23: leftovers of a killed earlier helper (staging folders, outbox temporary files), removed under the helper
    lock and only when no detached worker of this boot is alive (a worker writes its own temporary files)."""
    dp = lay.outbox / 'DETACHED.json'
    d = read_json_file(dp) if dp.is_file() else None
    if isinstance(d, dict) and worker_alive(d):
        return
    if isinstance(d, dict) and d.get('boot_id') != current_boot_id():
        dp.unlink()                                 # r2 R2-03: its worker died with the earlier boot (the incident follows)
    globs = [lay.base.glob('.cps_vm_stage_*'), lay.outbox.glob('.tmp_*')]
    for root in (lay.qual, lay.jobs):
        if root.is_dir():
            globs.append(root.glob('*/.cps_vm_stage_*'))
            globs.append(root.glob('*/.cps_vm_evict_*'))   # r2 R2-04: an evict killed while deleting
    for g in globs:
        for p in list(g):
            try:
                remove_tree(p)
            except OSError:
                pass


def cmd_session(a):
    lay = Layout()
    check_layout_basic(lay)
    for d in (lay.outbox, lay.inbox, lay.runtime, lay.qual, lay.jobs, lay.transcripts, lay.everyday_inputs):
        d.mkdir(parents=True, exist_ok=True)
    inbox = Path(a.inbox) if a.inbox else lay.inbox
    if not a.operator_model or not a.operator_model.strip() or a.operator_model.strip().startswith('<') or "'" in a.operator_model:
        refuse('SESSION_OPERATOR_MODEL', 'give --operator-model with your model name')
    with HelperLock(lay):
        block = Block()
        cleanup_leftovers(lay)
        old = read_state(lay)
        kit, how = session_kit(lay, inbox, block, old)
        try:
            ctx = Ctx(need_session=False)
        except Halt as h:
            if h.code.startswith('LAYOUT_'):
                stop(h.code, 'the kit and this layout disagree: tell the maintainer', detail=h.detail)
            raise
        if ctx.rel is None:
            stop('KIT_RELEASE_MISSING', 'the kit holds no RELEASE.json')
        clean_placed(ctx)
        if kit.get('repaired'):
            block.upload(kit['repaired_path'], reports_folder(ctx))
        return session_body(ctx, a, inbox, block, old, kit)


def session_body(ctx, a, inbox, block, old, kit):
    lay = ctx.lay
    boot = current_boot_id()
    rec_folder = ctx.records_folder() if ctx.mode != 'setup' else None
    setup_lst = load_session_listing(ctx, inbox / 'SETUP_LISTING.json', ctx.setup_folder(), 'setup', block)
    lst = None
    if rec_folder:
        which = 'everyday' if ctx.mode == 'everyday' else 'qualification'
        lst = load_session_listing(ctx, inbox / 'DRIVE_LISTING.json', rec_folder, which, block)
        eg = ctx.cfg['expected_genesis']
        if ctx.mode == 'qualification' and eg is not None and not lst.has(eg):
            relist(ctx, inbox / 'DRIVE_LISTING.json', rec_folder, None, 'LISTING_MISSING_GENESIS',
                   'the recorded GENESIS is not in the listing: list the folder again, following every page to the end', block)
    # newest SESSION note of the listing: its newest_package must be listed (3.2)
    notes_dl = {}
    if lst is not None:
        sess = sorted(lst.names('session'), key=lambda p: lst.by[p['name']][-1]['created'])
        if sess:
            sn = sess[-1]['name']
            content = (ctx.index.get(sn) or {}).get('content')
            if content is None:
                p = inbox / sn
                if not p.is_file():
                    f = lst.copies(sn)[0]
                    block.download(f['id'], sn, p)
                else:
                    content = read_json_file(p)
                    notes_dl[sn] = p
            if content is not None:
                np_ = ((content or {}).get('records_listing') or {}).get('newest_package')
                if np_ and not lst.has(np_):
                    relist(ctx, inbox / 'DRIVE_LISTING.json', rec_folder, None, 'LISTING_OLDER_THAN_SESSION',
                           'the newest SESSION note names a package this listing lacks: list again, every page', block)
    # fingerprint and its PASS (step 4)
    fp_sha, fp_full = fingerprint(lay)
    fp8 = h8(fp_sha)
    pass_name = None
    if isinstance(old, dict) and old.get('fingerprint_sha256') == fp_sha and old.get('fingerprint_pass'):
        pass_name = old['fingerprint_pass']
    for p in sorted(setup_lst.names('fpass'), key=lambda p: p['name']):
        if pass_name or p['fp8'] != fp8:
            continue
        e = ctx.index.get(p['name'])
        if e and e.get('content') and validate_pass(ctx, note_bytes(e['content']), fp_sha):
            pass_name = p['name']
            continue
        f = inbox / p['name']
        if not f.is_file():
            block.download(setup_lst.copies(p['name'])[0]['id'], p['name'], f)
            continue
        d = validate_pass(ctx, f.read_bytes(), fp_sha)
        if d is not None:
            pass_name = p['name']
            notes_dl[p['name']] = f
    if block.fetch:
        need(block, 'NEED_DOWNLOADS')
    for lp in (inbox / 'SETUP_LISTING.json', inbox / 'DRIVE_LISTING.json'):
        for old in quarantined(ctx, lp):            # T-12: both listings passed every check of this session
            old.unlink()
    # mode (step 5)
    st = {'boot_id': boot, 'session_note': None, 'mode': None, 'fingerprint_sha256': fp_sha, 'fingerprint_pass': pass_name,
          'pending_incident': False, 'restore_recheck': False, 'operator_model': a.operator_model, 'kit_sha256': kit['sha256'],
          'listing': {'records': sorted(lst.by) if lst else [], 'setup': sorted(setup_lst.by)}, 'unconfirmed': [],
          'ai_corrupt': [], 'rejected_copies': []}
    restored, pending_uploads, mode = None, [], 'fresh'
    boot_changed = False
    evidence = os.path.lexists(lay.ledger_dir) or bool(lay.job_folders())
    # T-09: local state is ours only when this VM's SESSION_STATE or INDEX (other than a STRAY record) knows it
    known = isinstance(old, dict) or any(e.get('kind') != 'stray' for e in ctx.index.files.values())
    if (lay.outbox / 'RESTORE_IN_PROGRESS.json').is_file():
        mode = 'restore'
        restored = restore_resume(ctx)
        st['pending_incident'] = True
    elif evidence and not known:
        stray_stop(ctx, block)
    elif evidence:
        mode = 'local'
        if ctx.mode == 'qualification':
            check_ledger_identity(ctx)
        if lst is not None:
            pending_uploads = local_checks(ctx, lst, setup_lst, block, st)
        if isinstance(old, dict):
            st['pending_incident'] = bool(old.get('pending_incident'))
            st['restore_recheck'] = bool(old.get('restore_recheck'))
            st['ai_corrupt'] = old.get('ai_corrupt') or []
            st['rejected_copies'] = old.get('rejected_copies') or []
            for k in ('recheck_incident', 'restore_session'):
                if old.get(k) and st['pending_incident']:
                    st[k] = old[k]
            if old.get('recheck_incident'):
                st['recheck_incident'] = old['recheck_incident']
            if old.get('boot_id') != boot:
                st['pending_incident'], boot_changed = True, True
        else:                                   # T-09: a known INDEX without its SESSION_STATE (a killed session): incident first
            st['pending_incident'], boot_changed = True, True
    elif lst is not None and restore_needed(ctx, lst):
        mode = 'restore'
        restored = restore(ctx, lst, inbox, block, st)
        st['pending_incident'] = True
    if restored is not None:                    # T-01: what the restore rejected reaches SESSION_STATE (and so the INCIDENT)
        st['ai_corrupt'] = list(restored.get('ai_corrupt') or [])
        st['rejected_copies'] = list(restored.get('rejected_copies') or [])
    elif mode == 'fresh' and ctx.mode == 'qualification' and ctx.cfg['expected_genesis'] is not None:
        stop('LISTING_MISSING_GENESIS', 'fresh mode is impossible once a GENESIS is recorded: list the folder again, every page')
    # clock (step 3, local and fresh)
    if mode != 'restore':
        floor = local_floor(ctx)
        clock_check(ctx, floor, block, a.operator_model)
    st['mode'] = mode
    if lst is not None:
        ingest_listing(ctx, lst)
    ingest_listing(ctx, setup_lst)
    for name, p in notes_dl.items():
        restore_note(ctx, name, p, setup_lst if parse_name(name)['kind'] == 'fpass' else lst)
    # SESSION note (step 6)
    newest = None
    if lst is not None:
        pk = sorted(lst.names('package'), key=lambda p: (p['seq'], p['pkind'] == 'FZ'))
        newest = pk[-1]['name'] if pk else None
    prev_sess = sorted(lst.names('session'), key=lambda p: lst.by[p['name']][-1]['created'])[-1]['name'] if lst and lst.names('session') else None
    env_reports = sorted(lay.outbox.glob('ENV_REPORT_*.json'))
    vm_sh = lay.vm
    now = now_dt()
    name = f'SESSION_{utc14(now)}_{h8(sha_bytes(boot.encode()))}_{fp8}.json'
    note = {'schema': 'cps.vm-session.v1', 'helper': helper_info(), 'boot_id': boot, 'created_utc': iso(now),
            'boot_id_source': boot_id_path(), 'overrides': ctx.lay.overrides, 'uid': os.getuid(), 'home': lay.home,
            'base': str(lay.base), 'tools': str(lay.tools), 'vm_sh_sha256': sha_file(vm_sh) if vm_sh.is_file() else None,
            'env_report_sha256': sha_file(env_reports[-1]) if env_reports else None, 'fingerprint_sha256': fp_sha,
            'fingerprint_pass': pass_name, 'mode': mode, 'kit': {k: kit[k] for k in ('name', 'sha256', 'repaired')},
            'release': {'sha256': sha_bytes(ctx.rel_raw), 'release_version': ctx.rel.get('release_version'),
                        'commit': (ctx.rel.get('repository') or {}).get('commit'), 'status': ctx.rel.get('status')},
            'previous_session': prev_sess, 'restored': restored, 'pending_uploads': [str(Path(p).name) for p in pending_uploads],
            'operator_model': a.operator_model, 'boot_changed_without_restore': boot_changed,
            'records_listing': {'count': len(lst.files) if lst else 0, 'pages': lst.pages if lst else 0, 'newest_package': newest,
                                'newest_session': prev_sess, 'sentinel': ctx.cfg['sentinels'][('everyday' if ctx.mode == 'everyday' else 'qualification')]['name'] if lst else None},
            'clock': {'floor_utc': None, 'waited_seconds': 0}, 'state': None}
    st['session_note'] = name
    if mode == 'restore' or boot_changed:          # r2 N1: the incident names the SESSION that asked for it
        st['restore_session'] = name
    ctx.state = st
    note['state'] = state_line(ctx)
    path = lay.outbox / name
    write_new(path, note_bytes(note))
    folder = rec_folder or ctx.setup_folder()
    for p in pending_uploads:
        e = ctx.index.get(Path(p).name)
        block.upload(p, (e or {}).get('folder') or folder)
    for up in made(ctx, path, 'session', folder, content=note):
        block.upload(up, folder)
    ctx.save_state()
    restore_done(lay)
    if inbox.exists():
        remove_tree(inbox)
    inbox.mkdir(parents=True, exist_ok=True)
    plan = plan_status(ctx)
    block.result = {'command': 'session', 'mode': mode, 'release_mode': ctx.mode, 'session_note': name,
                    'fingerprint8': fp8, 'fingerprint_pass': pass_name, 'restored': restored, 'kit_unpack': None}
    block.state = state_line(ctx)
    block.tail = plan.block.tail
    block.fetch += plan.block.fetch
    block.code = plan.code
    return block


def stray_stop(ctx, block):
    """T-09: a job folder or ledger that no SESSION_STATE or INDEX of this VM knows (a conversation still writing after a
    reset, or a planted path): archive it as STRAY, print its UPLOAD, STOP RESTORE_TARGET_NOT_EMPTY (case C)."""
    lay = ctx.lay
    paths = ([lay.ledger_dir] if os.path.lexists(lay.ledger_dir) else []) + list(lay.job_folders())
    folder = ctx.records_folder() if ctx.mode != 'setup' else reports_folder(ctx)
    old = [e for e in ctx.index.of('stray') if e.get('payload') and Path(e['payload']).is_file()]
    b = Block()
    b.pre = list(block.pre)
    b.uploads = list(block.uploads)
    if old:
        for up in upload_paths(ctx, old[-1]['payload'], old[-1].get('folder') or folder):
            b.upload(up, old[-1].get('folder') or folder)
    else:
        sp = write_stray(ctx, paths)
        if sp:
            for up in made(ctx, sp, 'stray', folder):
                b.upload(up, folder)
    stop('RESTORE_TARGET_NOT_EMPTY', 'job folders or a ledger this VM did not restore or make: do not delete anything; '
         'upload the STRAY archive and hand back case C', block=b, detail={'paths': [str(p) for p in paths][:10]})


def check_ledger_identity(ctx):
    if not ctx.lay.ledger.is_file() and ctx.lay.job_folders():
        stop('LEDGER_MISSING', 'job folders remain but BASE/ledger/LEDGER.jsonl is gone: nothing may run; hand back case C')
    raw = ctx.lay.ledger.read_bytes() if ctx.lay.ledger.is_file() else b''
    first = raw.split(b'\n', 1)[0] if raw else b''
    try:
        e = sjson(first) if first else None
    except (ValueError, UnicodeDecodeError):
        e = None
    if not isinstance(e, dict) or e.get('type') != 'genesis' or e.get('seq') != 1:
        stop('LEDGER_NO_IDENTITY', 'BASE/ledger exists without a genesis line: nothing may run; hand back case C')


def local_checks(ctx, lst, setup_lst, block, st):
    """5.1 step 5 local mode: re-offer made files missing from the listing; LOCAL_BEHIND_DRIVE; forks."""
    ix = ctx.index
    pending = []
    cur = set()
    fl = in_flight(ctx)
    if fl:
        t, c = ctx.lay.tag_of(fl[0])
        cur = {(t, c)}
    lists = {lst.folder: lst, setup_lst.folder: setup_lst}
    for e in sorted((e for e in ix.files.values() if e.get('origin') == 'made'), key=lambda e: (e.get('created_utc') or '', 0 if e['name'].startswith('PNG_') else 1)):
        if e.get('folder') not in lists:
            continue
        n = e['name']
        listed = lists[e['folder']].by.get(n, [])
        if any(file_matches(f, e.get('md5'), e.get('bytes')) for f in listed):
            continue
        if e.get('kind') == 'split' and ix.confirmed((e.get('meta') or {}).get('of')):
            continue
        if slices_of(ctx, n):                           # T-22: an oversized original reaches Drive as its slices only
            if not ix.confirmed(n) and (e.get('tag'), e.get('case_id')) in cur and e.get('kind') in ('start', 'link', 'ai', 'package'):
                st['unconfirmed'].append(n)
            continue
        if listed and not (e.get('payload') and Path(e['payload']).is_file()):
            stop('UPLOAD_CORRUPT_ON_DRIVE', 'a file this VM made is on Drive with other bytes and its local copy is gone', detail={'name': n})
        if e.get('payload') and Path(e['payload']).is_file():
            pending.append(e['payload'])
            if (e.get('tag'), e.get('case_id')) in cur and e.get('kind') in ('start', 'link', 'ai', 'package'):
                st['unconfirmed'].append(n)
    local_pk = [e for e in ix.of('package') if e.get('origin') in ('made', 'restored')]
    chains = {}
    for e in local_pk:
        p = parse_name(e['name'])
        ch = chain_of(p['tag'])
        chains[ch] = max(chains.get(ch, -1), p['seq'])
    dn = dead_names(ctx, [p['name'] for p in lst.names('package')], lst)  # T-02: rejected names do not count
    for p in lst.names('package'):
        ch = chain_of(p['tag'])
        if ch in chains and p['seq'] > chains[ch] and (ctx.index.get(p['name']) or {}).get('origin') not in ('made', 'restored') \
                and p['name'] not in dn:
            stop('LOCAL_BEHIND_DRIVE', 'Drive holds a newer package of this chain than this VM: hand back case C')
    fork = find_fork(lst.names('package'), dn)
    if fork:
        stop('RESTORE_FORK', 'two different packages at one seq: hand back case C', detail=fork)
    return pending


def find_fork(pkgs, dead_names=()):
    by = {}
    for p in pkgs:
        if p['name'] in dead_names:
            continue
        by.setdefault((chain_of(p['tag']), p['seq']), []).append(p)
    for (ch, seq), ps in by.items():
        for kind in ('CP', 'FZ'):
            k = {p['pkg8'] for p in ps if p['pkind'] == kind}
            if len(k) > 1:
                return {'seq': seq, 'kind': kind}
        cps = [p for p in ps if p['pkind'] == 'CP']
        fzs = [p for p in ps if p['pkind'] == 'FZ']
        for c in cps:
            for f in fzs:
                if (c['ledger8'], c['record8'], c['tag'], c['case']) != (f['ledger8'], f['record8'], f['tag'], f['case']) \
                        or c['frozen8'] != '00000000':
                    return {'seq': seq, 'kind': 'CP/FZ'}
    return None


def local_floor(ctx):
    ts = []
    if ctx.lay.ledger.is_file() and CJ is not None:
        try:
            _, ents = read_ledger(ctx)
            if ents:
                ts.append(parse_utc(ents[-1].get('utc')))
        except Halt:
            pass
    for d in in_flight(ctx):
        jv = JobView(ctx, d)
        for s in jv.stages():
            ts.append(parse_utc(s.get('ended_utc')))
    for e in ctx.index.files.values():
        if e.get('origin') in ('made', 'restored') and e.get('kind') in ('start', 'link', 'incident', 'session', 'ai'):
            ts.append(parse_utc(((e.get('content') or {}).get('created_utc')) or e.get('created_utc')))
    ts = [t for t in ts if t is not None]
    return max(ts) if ts else None


def clock_check(ctx, floor, block, model, code='CLOCK_BEHIND'):
    if floor is None:
        return
    nw = now_dt()
    if nw >= floor:
        return
    behind = (floor - nw).total_seconds()
    if behind <= ctx.cfg['clock_wait_max_seconds']:
        block.tail = []
        block.next('WAIT until=' + iso(floor + datetime.timedelta(seconds=2)))
        block.then(f'RUN bash {ctx.lay.repo}/deploy/vm/session_start.sh --operator-model {q(model)}')
        raise Halt('NEED', 'CLOCK_WAIT', block=block)
    stop(code, 'this VM clock is behind the records: hand back case C')


def restore_note(ctx, name, path, lst):
    """Copy a downloaded note into the outbox and INDEX (origin restored) with its parsed content."""
    p = parse_name(name)
    raw = Path(path).read_bytes()
    content = None
    if name.endswith('.json'):
        content = read_json_file(path)
    dest = ctx.lay.outbox / name
    ensure_file(dest, raw)
    f = (lst.copies(name)[0] if lst is not None and lst.has(name) else {}) if lst is not None else {}
    if ctx.index.get(name) is None or ctx.index.get(name).get('origin') == 'listed':
        ctx.index.add(name=name, kind=p['kind'], folder=lst.folder if lst is not None else None, sha256=sha_bytes(raw),
                      md5=hashlib.md5(raw, usedforsecurity=False).hexdigest(), bytes=len(raw),
                      created_utc=(content or {}).get('created_utc') if isinstance(content, dict) else None, origin='restored',
                      drive_id=f.get('id'), drive_created=f.get('created'), tag=p.get('tag') or (content or {}).get('tag'),
                      case_id=p.get('case') or (content or {}).get('case_id'), role=p.get('role'), attempt=p.get('attempt'),
                      payload=str(dest), content=content if isinstance(content, dict) else None, meta=None)


# ------------------------------------------------------------------ restore (spec 6)
def pkg_meta(man):
    png = man.get('png') or None
    return {'pkind': man.get('kind'), 'job_dir': man.get('job_dir'), 'record_sha256': (man.get('record') or {}).get('sha256'),
            'record_seq': (man.get('record') or {}).get('seq'), 'last_completed': (man.get('record') or {}).get('last_completed'),
            'ledger_sha256': (man.get('ledger') or {}).get('sha256'), 'ledger_seq': (man.get('ledger') or {}).get('seq'),
            'frozen_sha256': (man.get('frozen') or {}).get('frozen_sha256'), 'reset_diverged': bool(man.get('reset_diverged')),
            'png_set_sha256': png.get('set_sha256') if png else None, 'png_parts': png.get('parts') if png else [],
            'png_made_by': png.get('made_by_package') if png else None, 'bind': ((man.get('binding') or {}).get('own')),
            'binding': man.get('binding'), 'command': (man.get('command') or {}).get('runner_subcommand'),
            'verify_frozen_exit': ((man.get('frozen') or {}).get('verify_frozen') or {}).get('exit')}


def restore_needed(ctx, lst):
    if ctx.mode == 'qualification':
        return bool(lst.names('genesis') or lst.names('package'))
    return everyday_unfinished(lst) is not None or everyday_newest_finished(lst) is not None     # T-08


def everyday_newest_finished(lst):
    """T-08 (6.1 step 1): with no unfinished run, the newest run that ended on an FZ is restored for verification only."""
    tags = sorted({p['tag'] for p in virtual_names(lst).values() if p['kind'] == 'package' and p['tag'].startswith('E')})
    return tags[-1] if tags else None


def virtual_names(lst):
    """Recognised names of the listing, with complete SPLIT_ slice sets standing for their original."""
    out = {p['name']: p for p in lst.names() if p['kind'] != 'split'}
    sl = {}
    for p in lst.names('split'):
        sl.setdefault(p['original'], []).append(p)
    for orig, ps in sl.items():
        n = ps[0]['n']
        if {p['k'] for p in ps} == set(range(1, n + 1)) and orig not in out and parse_name(orig):
            out[orig] = parse_name(orig)
    return out


def created_of(lst, name):
    if lst.has(name):
        return lst.by[name][0]['created']
    sl = [f for n, fs in lst.by.items() for f in fs if (parse_name(n) or {}).get('kind') == 'split' and parse_name(n)['original'] == name]
    return max(f['created'] for f in sl) if sl else None


def everyday_unfinished(lst):
    names = virtual_names(lst)
    tags = {}
    for p in names.values():
        if p['kind'] in ('package', 'inputs') and p['tag'].startswith('E'):
            tags.setdefault(p['tag'], []).append(p)
    unf = []
    for tag, ps in tags.items():
        pk = sorted([p for p in ps if p['kind'] == 'package'], key=lambda p: (p['seq'], p['pkind'] == 'FZ'))
        if not pk or pk[-1]['pkind'] != 'FZ':
            unf.append(tag)
    if len(unf) > 1:
        stop('RESTORE_EVERYDAY_TWO_UNFINISHED', 'two unfinished everyday runs on Drive: hand back case C')
    return unf[0] if unf else None


DEAD = object()
REDOWNLOAD_MAX = 3


class Fetcher:
    """Downloads by Drive id into the inbox, trying same-name copies in ascending createdTime (3.2, 6.2)."""
    def __init__(self, ctx, lst, inbox, block, plan):
        self.ctx, self.lst, self.inbox, self.block, self.plan = ctx, lst, inbox, block, plan
        plan.setdefault('rejected', {})
        plan.setdefault('requested', {})

    def rejected(self, name):
        return self.plan['rejected'].get(name, [])

    def reject(self, name, fid, why):
        self.plan['rejected'].setdefault(name, []).append(fid)
        self.plan.setdefault('rejected_why', []).append({'name': name, 'drive_id': fid, 'why': why})
        self.ctx.index.event('rejected', name, drive_id=fid, why=why)

    def get(self, name, check):
        """The local path of a copy that passes check(path) -> None|why, None while a download is pending, or DEAD."""
        if not self.lst.has(name):
            return self.get_split(name, check)
        while True:
            copies = [f for f in self.lst.copies(name) if f['id'] not in self.rejected(name)]
            if not copies:
                return DEAD
            f = copies[0]
            p = self.inbox / name
            if not p.is_file():
                self.block.download(f['id'], name, p)
                self.plan['requested'][name] = f['id']
                return None
            md5 = md5_file(p)
            others = [g for g in self.lst.by.get(name, []) if g['id'] != f['id'] and g['md5'] and g['md5'] == md5]
            if f['md5'] and f['md5'] != md5 and others:
                p.unlink()
                refuse('RESTORE_WRONG_COPY', 'save each download under the printed path, by the printed id')
            why = check(p)
            if self.download_at_fault(f, p, md5):
                # r2 R2-02: bytes that differ from the listing are a damaged download unless their whole-file hash (the
                # name's) verifies: only then does the listing contradict intact bytes
                if why is None and whole_hash_ok(p):
                    if f['md5'] and f['md5'] != md5:
                        stop('RESTORE_MD5_MISMATCH', 'the listing contradicts the downloaded bytes: hand back case C', detail={'name': name})
                    stop('RESTORE_SIZE_MISMATCH', 'the listing contradicts the downloaded bytes: hand back case C', detail={'name': name})
                return self.redownload(f, name, p)
            if why is None:
                self.plan.setdefault('chosen', {})[name] = f
                return p
            self.reject(name, f['id'], why)
            p.unlink()

    def download_at_fault(self, f, p, md5):
        """T-03: the local bytes differ from what the listing says this copy holds: the download was cut off or damaged
        here, so the copy on Drive is not rejected."""
        return bool((f.get('md5') and f['md5'] != md5) or (f.get('size') is not None and f['size'] != os.lstat(p).st_size))

    def redownload(self, f, name, p):
        n = self.plan.setdefault('redownloads', {}).get(f['id'], 0) + 1
        self.plan['redownloads'][f['id']] = n
        p.unlink()
        if n > REDOWNLOAD_MAX:
            stop('RESTORE_DOWNLOAD_FAILED', 'the same Drive copy downloaded damaged several times: hand back case C',
                 detail={'name': name, 'drive_id': f['id']})
        self.block.download(f['id'], name, p)
        self.plan['requested'][name] = f['id']
        return None

    def get_split(self, name, check):
        sl = [p for p in self.lst.names('split') if p['original'] == name]
        if not sl:
            return DEAD
        paths, pending = {}, False
        for s in sorted(sl, key=lambda p: p['k']):
            fs = [f for f in self.lst.copies(s['name']) if f['id'] not in self.rejected(s['name'])]
            if not fs:
                return DEAD
            p = self.inbox / s['name']
            if not p.is_file():
                self.block.download(fs[0]['id'], s['name'], p)
                pending = True
            paths[s['k']] = p
        if pending:
            return None
        data = join_slices(paths, name)
        out = self.inbox / name
        if data is None:
            bad = False
            for k, p in paths.items():                  # T-03: a slice whose local bytes differ from its listing is downloaded again
                f = [g for g in self.lst.copies(p.name) if g['id'] not in self.rejected(p.name)][0]
                if self.download_at_fault(f, p, md5_file(p)):
                    self.redownload(f, p.name, p)
                    bad = True
            if bad:
                return None
            for k, p in paths.items():
                self.reject(p.name, [g for g in self.lst.copies(p.name) if g['id'] not in self.rejected(p.name)][0]['id'],
                            'slice set does not join')
                p.unlink()
            return self.get_split(name, check)
        if not out.exists():
            out.write_bytes(data)
        why = check(out)
        if why is not None:
            out.unlink()
            return DEAD
        self.plan.setdefault('chosen', {})[name] = {'id': None, 'created': created_of(self.lst, name), 'md5': None, 'size': len(data)}
        return out


def whole_hash_ok(p):
    """The file's name carries a hash of its whole bytes (package pkg8, transcript or INPUTS sha8) and it matches."""
    pn = parse_name(Path(p).name) or {}
    if pn.get('kind') == 'package':
        return h8(sha_file(p)) == pn['pkg8']
    if pn.get('kind') in ('transcript', 'inputs'):
        return h8(sha_file(p)) == pn['sha8']
    return False


def check_pkg_bytes(p):
    pn = parse_name(Path(p).name)
    return None if h8(sha_file(p)) == pn['pkg8'] else 'sha8'


def check_note(p):
    pn = parse_name(Path(p).name)
    d = read_json_file(p)
    if not isinstance(d, dict):
        return 'json'
    want = {'start': 'cps.vm-start.v1', 'link': 'cps.vm-link.v1', 'incident': 'cps.vm-incident.v1', 'session': 'cps.vm-session.v1',
            'genesis': 'cps.vm-genesis.v1', 'fpass': 'cps.vm-fingerprint-pass.v1', 'delivery': 'cps.vm-delivery.v1'}.get(pn['kind'])
    if want and d.get('schema') != want:
        return 'schema'
    return None


def check_ai_bytes(p):
    pn = parse_name(Path(p).name)
    try:
        a = Archive(p, ('MANIFEST.json', 'output'))
        try:
            ai_expected_check(a)
            return None if h8(a.manifest.get('tree_sha256') or '') == pn['tree8'] else 'tree8'
        finally:
            a.close()
    except Halt:
        return 'archive'


def check_sha8(p):
    pn = parse_name(Path(p).name)
    if pn['kind'] == 'transcript':
        return None if h8(sha_file(p)) == pn['sha8'] else 'sha8'
    if pn['kind'] == 'inputs':
        return None if h8(sha_file(p)) == pn['sha8'] else 'sha8'
    return None


def ai_expected_check(a):
    man = a.manifest
    exp = {'output': ('dir', man.get('output_mode', 0o755))}
    for rel, kind, mode, size, sha in man.get('tree') or []:
        exp['output/' + rel] = ('dir', mode) if kind == 'dir' else ('file', mode, size, sha)
    a.check(exp)
    if tree_sha(man.get('tree') or []) != man.get('tree_sha256'):
        a.bad('ARCHIVE_MANIFEST_MISMATCH', {'why': 'tree_sha256'})


def pkg_expected(man):
    exp = {}
    for m in man.get('members') or []:
        exp[m['path']] = ('dir', m['mode']) if m['type'] == 'dir' else ('file', m['mode'], m['bytes'], m['sha256'])
    if man.get('ledger'):
        L = man['ledger']
        exp['ledger/LEDGER.jsonl'] = ('file', L.get('mode', 0o644), L['bytes'], L['sha256'])
    return exp


def plan_dead(ctx, lst, plan, chain):
    """T-02: package names of the chain all of whose listed copies failed their own hash (this restore or earlier)."""
    rej = plan.get('rejected') or {}
    out = {n for n in rej if not [f for f in lst.copies(n) if f['id'] not in rej[n]]}
    return out | dead_names(ctx, [p['name'] for p in chain], lst)


def resolve_forks(ctx, lst, inbox, block, plan, F, chain, newest):
    """T-02 (6.1 steps 2-3): two packages at one seq are a fork only when both are intact. A name whose every copy fails
    its own hash counts as not uploaded (the E22 recovery re-runs the stage and makes a second package at that seq), so
    the members of a fork group are downloaded and checked before RESTORE_FORK."""
    checked = set(plan.get('fork_checked') or [])
    top = (newest['seq'] if newest else None)
    for _ in range(100):
        dn = plan_dead(ctx, lst, plan, chain)
        live = [p for p in chain if top is None or p['seq'] <= top]
        fork = find_fork(live, dn)
        if not fork:
            return
        grp = [p for p in live if p['seq'] == fork['seq'] and p['name'] not in dn]
        todo = [p for p in grp if p['name'] not in checked]
        if not todo:
            stop('RESTORE_FORK', 'two different intact packages at one seq: hand back case C', detail=fork)
        pending = False
        for p in todo:
            r = F.get(p['name'], check_pkg_bytes)
            if r is None:
                pending = True
                continue
            checked.add(p['name'])
            if r is not DEAD and (newest is None or p['name'] != newest['name']) and Path(r).is_file():
                Path(r).unlink()
        plan['fork_checked'] = sorted(checked)
        save_plan(ctx, plan)
        if pending:
            need(block, 'RESTORE_FORK_CHECK')
    stop('RESTORE_FORK', 'two different packages at one seq: hand back case C')


def check_incidents_ahead(ctx, lst, notes, tp, job, live_jobs):
    """T-03 (6.1 step 5, incident clause): every INCIDENT later than the restored package names that job, no job, or a
    pending prepare whose job has no intact package on Drive; otherwise RESTORE_NOTES_AHEAD_OF_PACKAGE."""
    pk_jobs = set(live_jobs)
    for n, path in notes.items():
        pn = parse_name(n)
        if pn['kind'] != 'incident' or (tp is not None and (created_of(lst, n) or '') <= tp):
            continue
        c = read_json_file(path) or {}
        tag, case = c.get('tag', pn['tag']), c.get('case_id', pn['case'])
        if tag is None or (job is not None and (tag, case) == job):
            continue
        pj = c.get('pending_job') or {}
        if pj and (pj.get('tag'), pj.get('case')) == (tag, case) and (tag, case) not in pk_jobs:
            continue
        stop('RESTORE_NOTES_AHEAD_OF_PACKAGE', 'an INCIDENT on Drive names a job whose package is not there: hand back case C',
             detail={'name': n})


def save_plan(ctx, plan):
    write_atomic(ctx.lay.outbox / 'RESTORE_PLAN.json', note_bytes(plan))


def restore(ctx, lst, inbox, block, st):
    lay = ctx.lay
    plan = read_json_file(lay.outbox / 'RESTORE_PLAN.json') or {}
    F = Fetcher(ctx, lst, inbox, block, plan)
    names = virtual_names(lst)
    qual = ctx.mode == 'qualification'
    gen_path, gen = None, None
    if qual:
        gens = sorted({p['name'] for p in names.values() if p['kind'] == 'genesis'})
        pk_all = [p for p in names.values() if p['kind'] == 'package' and is_qual_tag(p['tag'])]
        if not gens:
            stop('RESTORE_GENESIS_MISSING', 'packages without a GENESIS note: hand back case C')
        if len(gens) > 1:
            stop('RESTORE_GENESIS_DUPLICATE', 'two GENESIS notes: hand back case C')
        eg = ctx.cfg['expected_genesis']
        if eg is not None and gens[0] != eg:
            stop('RESTORE_GENESIS_UNEXPECTED', 'the GENESIS on Drive is not the recorded one: hand back case C')
        gen_path = F.get(gens[0], check_note)
        if gen_path is DEAD:
            stop('RESTORE_GENESIS_MISSING', 'no intact copy of the GENESIS note')
        chain = pk_all
        run_tag = None
    else:
        run_tag = everyday_unfinished(lst) or everyday_newest_finished(lst)
        chain = [p for p in names.values() if p['kind'] == 'package' and p['tag'] == run_tag]
    newest, npath = None, None
    for c in sorted(chain, key=lambda p: (p['seq'], p['pkind'] == 'FZ'), reverse=True):
        r = F.get(c['name'], check_pkg_bytes)
        if r is DEAD:
            continue
        if r is None:
            break
        newest, npath = c, r
        break
    save_plan(ctx, plan)
    if newest is not None:
        asked = set(plan.get('requested') or {}) | set(plan.get('fork_checked') or [])
        for f in inbox.iterdir() if inbox.is_dir() else []:
            pf = parse_name(f.name)
            if pf and pf['kind'] == 'package' and chain_of(pf['tag']) == chain_of(newest['tag']) and f.name not in asked and \
                    (pf['seq'], pf['pkind'] == 'FZ') < (newest['seq'], newest['pkind'] == 'FZ'):
                f.unlink()
                refuse('RESTORE_NOT_NEWEST', 'the inbox held an older package than the newest: download only the printed files')
    if block.fetch:
        need(block, 'NEED_DOWNLOADS')
    resolve_forks(ctx, lst, inbox, block, plan, F, chain, newest)
    live_jobs = {(p['tag'], p['case']) for p in chain if p['name'] not in plan_dead(ctx, lst, plan, chain)}
    plan['live_jobs'] = sorted(list(j) for j in live_jobs)
    if gen_path is not None:
        gen = read_json_file(gen_path)
    # notes of the job (and incidents after the package)
    tp = (plan.get('chosen') or {}).get(newest['name'], {}).get('created') if newest else None
    job = (newest['tag'], newest['case']) if newest else None
    want = []
    for p in names.values():
        if p['kind'] in ('start', 'link', 'incident', 'ai', 'transcript', 'delivery', 'inputs'):
            mine = job is not None and p.get('tag') == job[0] and p.get('case') == job[1]
            if p['kind'] == 'delivery':
                mine = run_tag is not None and job is not None and p['case'] == job[1]
            if p['kind'] == 'inputs':                  # r2 M5: only the newest INPUTS of the run (new inputs replace refused ones)
                mine = p['tag'] == run_tag and p['name'] == max((q_['name'] for q_ in names.values() if q_['kind'] == 'inputs'
                                                                 and q_['tag'] == run_tag), key=lambda n: (created_of(lst, n) or '', n))
            later = tp is None or (created_of(lst, p['name']) or '') > tp
            if p['kind'] in ('start', 'link', 'ai') and later and not mine and (qual or p.get('tag') == run_tag):
                stop('RESTORE_NOTES_AHEAD_OF_PACKAGE', 'a START, LINK or AI archive on Drive names a job whose package is not there: hand back case C',
                     detail={'name': p['name']})
            if mine or (p['kind'] == 'incident' and later and (qual or p.get('tag') == run_tag)):
                want.append(p)
    sess = sorted(lst.names('session'), key=lambda p: lst.by[p['name']][-1]['created'])
    notes = {}
    for p in want + (sess[-1:] if sess else []):
        chk = check_ai_bytes if p['kind'] == 'ai' else (check_sha8 if p['kind'] in ('transcript', 'inputs') else check_note)
        r = F.get(p['name'], chk)
        if r is DEAD or r is None:
            if r is DEAD and p['kind'] == 'ai':
                plan.setdefault('ai_dead', []).append(p['name'])
            continue
        notes[p['name']] = r
    save_plan(ctx, plan)
    if block.fetch:
        need(block, 'NEED_DOWNLOADS')
    if newest is None:
        check_incidents_ahead(ctx, lst, notes, None, None, live_jobs)
        rp = {'package': None, 'fz_newest': False, 'genesis': str(gen_path) if gen_path else None, 'notes': {k: str(v) for k, v in notes.items()},
              'run_tag': run_tag, 'job_dir': None, 'rejected_copies': plan.get('rejected_why', []), 'ai_corrupt': []}
        return place_restore(ctx, rp, lst)
    return restore_package(ctx, lst, inbox, block, plan, F, newest, npath, gen, gen_path, notes, tp, names)


def restore_package(ctx, lst, inbox, block, plan, F, newest, npath, gen, gen_path, notes, tp, names):
    lay = ctx.lay
    qual = ctx.mode == 'qualification'
    a = Archive(npath, ('MANIFEST.json', 'ledger', 'job'))
    man = a.manifest
    check_pkg_manifest(a)
    a.check(pkg_expected(man))
    fz_newest = newest['pkind'] == 'FZ'
    bad = []
    if man.get('kind') != newest['pkind'] or man.get('tag') != newest['tag'] or man.get('case_id') != newest['case']:
        bad.append('name')
    rec_raw = a.read('job/RUN_RECORD.json') if 'job/RUN_RECORD.json' in a.by else b''
    if sha_bytes(rec_raw) != (man.get('record') or {}).get('sha256') or h8(sha_bytes(rec_raw)) != newest['record8']:
        bad.append('record')
    led_raw = None
    if qual:
        led_raw = a.read('ledger/LEDGER.jsonl') if 'ledger/LEDGER.jsonl' in a.by else b''
        if (man.get('ledger') or {}).get('seq') != newest['seq'] or h8(sha_bytes(led_raw)) != newest['ledger8']:
            bad.append('ledger')
    elif (man.get('record') or {}).get('seq') != newest['seq']:
        bad.append('seq')
    if bad:
        stop('RESTORE_MANIFEST_MISMATCH', 'the package manifest does not name this chain: hand back case C', detail={'fields': bad})
    # notes ahead: a later START must carry this package's record
    for n, path in notes.items():
        pn = parse_name(n)
        if pn['kind'] == 'start' and (created_of(lst, n) or '') > (tp or ''):
            if (read_json_file(path) or {}).get('record_sha256') != man['record']['sha256']:
                stop('RESTORE_NOTES_AHEAD_OF_PACKAGE', 'a START on Drive was made on a record whose package is not there: hand back case C')
    check_incidents_ahead(ctx, lst, notes, tp, (newest['tag'], newest['case']), {tuple(j) for j in plan.get('live_jobs') or []})
    # parts (step 7)
    png = man.get('png')
    if png and not fz_newest:
        core_created = tp or ''
        for part in png.get('parts') or []:
            fs = [f for f in lst.by.get(part['name'], []) if file_matches(f, part.get('md5'), part.get('bytes'))] if lst.has(part['name']) else []
            if not lst.has(part['name']):
                stop('RESTORE_PARTS_INCOMPLETE', 'a PNG part of the newest package is not on Drive: hand back case C', detail={'name': part['name']})
            use = fs[0] if fs else lst.by[part['name']][0]
            if use['created'] > core_created:
                stop('RESTORE_PARTS_AFTER_CORE', 'a PNG part reached Drive after its core: hand back case C', detail={'name': part['name']})
    # layout (step 10, checked before the chain: the chain checks key on the manifest's job folder)
    if man.get('job_dir') != str(lay.job_dir(newest['tag'], newest['case'])) or \
            (qual and (man.get('ledger') or {}).get('path') != str(lay.ledger)):
        stop('RESTORE_LAYOUT_MISMATCH', '$HOME or the base changed since the package was made: hand back case C')
    # chain (step 8)
    rec = None
    try:
        rec = sjson(rec_raw)
    except (ValueError, UnicodeDecodeError):
        stop('RESTORE_RECORD_CHAIN_BROKEN', 'the record does not parse')
    if CJ.chain_problem(rec, rec_raw):
        stop('RESTORE_RECORD_CHAIN_BROKEN', 'the record chain does not verify: hand back case C')
    if qual:
        first = led_raw.split(b'\n', 1)[0] + b'\n'
        if gen is None or first != (gen.get('identity_line') or '').encode('utf-8') + b'\n' or sha_bytes(first) != gen.get('identity_line_sha256'):
            stop('RESTORE_GENESIS_MISMATCH', 'the ledger is not the one the GENESIS note names: hand back case C')
        with tempfile.TemporaryDirectory(prefix='cps_vm_led_') as td:
            tl = Path(td) / 'LEDGER.jsonl'
            tl.write_bytes(led_raw)
            try:
                with CJ.Ledger(tl, create=False, readonly=True) as led:
                    entries = list(led.entries)
            except CJ.Refused:
                stop('RESTORE_LEDGER_CHAIN_BROKEN', 'the package ledger does not verify: hand back case C')
        lines = led_raw.split(b'\n')[:-1]
        qchain = [p for p in names.values() if p['kind'] == 'package' and is_qual_tag(p['tag'])]
        pending = False
        for p in qchain:
            if p['name'] in plan_dead(ctx, lst, plan, qchain):
                continue
            s = p['seq']
            pre = b''.join(x + b'\n' for x in lines[:s])
            if s > len(lines) or h8(sha_bytes(pre)) != p['ledger8']:
                if s > newest['seq']:
                    continue
                r = F.get(p['name'], check_pkg_bytes)     # T-02: a name that fails its own hash counts as not uploaded
                if r is None:
                    pending = True
                    continue
                if r is DEAD:
                    continue
                stop('RESTORE_LEDGER_PREFIX_MISMATCH', 'a package on Drive does not extend this ledger: hand back case C', detail={'package': p['name']})
        if pending:
            save_plan(ctx, plan)
            a.close()
            need(block, 'RESTORE_PREFIX_CHECK')
        jd = man['job_dir']
        recs = [e for e in entries if e.get('job_dir') == jd and e.get('type') in ('prepare', 'nonattempt', 'record')]
        if not recs or recs[-1].get('run_record_sha256') != sha_bytes(rec_raw):
            stop('RESTORE_RECORD_NOT_LEDGER', 'the record is not the one the ledger last recorded: hand back case C')
        floor_ts = [parse_utc(entries[-1].get('utc'))] if entries else []
    else:
        for p in names.values():
            if p['kind'] == 'package' and p['tag'] == newest['tag'] and p['case'] == newest['case'] and p['seq'] <= newest['seq']:
                k = p['seq']
                if h8(sha_bytes(CJ.dumps(dict(rec, stages=rec['stages'][:k])))) != p['record8']:
                    stop('RESTORE_RECORD_PREFIX_MISMATCH', 'a package of this run does not extend its record: hand back case C', detail={'package': p['name']})
        floor_ts = []
    # clock (step 9)
    floor_ts += [parse_utc(s.get('ended_utc')) for s in rec.get('stages', [])[-1:]]
    floor_ts.append(parse_utc(man.get('created_utc')))
    for n, path in notes.items():
        if n.endswith('.json'):
            floor_ts.append(parse_utc((read_json_file(path) or {}).get('created_utc')))
    floor = max([t for t in floor_ts if t is not None], default=None)
    if floor is not None and now_dt() < floor:
        if (floor - now_dt()).total_seconds() <= ctx.cfg['clock_wait_max_seconds']:
            block.tail = []
            block.next('WAIT until=' + iso(floor + datetime.timedelta(seconds=2)))
            block.then(f'RUN bash {lay.repo}/deploy/vm/session_start.sh --operator-model {q(ctx.state.get("operator_model") if ctx.state else "")}')
            raise Halt('NEED', 'CLOCK_WAIT', block=block)
        stop('RESTORE_CLOCK_BEHIND', 'this VM clock is behind the records: hand back case C')
    # targets empty (step 11)
    jd = Path(man['job_dir'])
    stray = []
    if qual and os.path.lexists(lay.ledger_dir):
        stray.append(lay.ledger_dir)
    stray += [d for d in lay.job_folders()]
    if os.path.lexists(jd) and jd not in stray:
        stray.append(jd)
    if stray:
        sp = write_stray(ctx, stray)
        b = Block()
        if sp:
            for up in made(ctx, sp, 'stray', ctx.records_folder()):
                b.upload(up, ctx.records_folder())
        stop('RESTORE_TARGET_NOT_EMPTY', 'do not delete anything; hand back case C', block=b)
    # AI archive (step 13) and the staged output folder (step 11)
    ai = None
    role = STEP_ROLE.get(next((s['next'] for s in reversed(rec['stages']) if s.get('completed')), None))
    if role and not fz_newest:
        starts_ = [(n, read_json_file(p) or {}) for n, p in notes.items() if parse_name(n)['kind'] == 'start' and parse_name(n)['role'] == role]
        att = None
        if starts_:
            top = max(parse_name(n)['attempt'] for n, _ in starts_)
            att = top
            if role == 'G':
                g_att = 1 + sum(1 for s in rec['stages'] if s.get('completed') and s['stage'] == 'interrupt' and s.get('next') == 'GENERATE')
                att = top if top >= g_att else None
        if att is not None:
            cands = [p for p in names.values() if p['kind'] == 'ai' and p['tag'] == newest['tag'] and p['case'] == newest['case']
                     and p['role'] == role and p['attempt'] == att]
            if cands:
                topr = max(p['revision'] for p in cands)
                same = [p for p in cands if p['revision'] == topr]
                if len({p['tree8'] for p in same}) > 1:
                    stop('RESTORE_AI_CONFLICT', 'two different AI archives of one attempt: hand back case C')
                if same[0]['name'] in notes:
                    ai = (same[0]['name'], str(notes[same[0]['name']]))
                else:
                    plan.setdefault('ai_corrupt_start', []).append(role + str(att))
        out_rel = 'job/' + {'S': 'scope/reader/output', 'G': (rec['stages'] and 'run/' + str(rec.get('reader')) + '/output'),
                            'V': 'qa/visual_review'}[role]
        if role == 'G':
            gen_st = None
            for nm in ('scope-finish', 'prepare'):
                d = [s for s in rec['stages'] if s['stage'] == nm and s.get('completed')]
                if d and str(d[-1]['next']).startswith('GENERATE'):
                    gen_st = d[-1]
                    break
            rd = ((gen_st or {}).get('facts', {}).get('generation') or {}).get('run_dir')
            if rd:
                out_rel = 'job/' + rd + '/output'
        staged = [m for m in man['members'] if m['path'].startswith(out_rel + '/')]
        if staged and any(m['type'] == 'file' for m in staged):
            if ai is None:
                pass
            else:
                aa = Archive(ai[1], ('MANIFEST.json', 'output'))
                at = aa.manifest.get('tree') or []
                aa.close()
                mine = sorted([[m['path'][len(out_rel) + 1:], m['type'], m['mode'], m.get('bytes'), m.get('sha256')] for m in staged])
                if mine != sorted(at):
                    stop('RESTORE_AI_CONFLICT', 'the package output folder differs from the archived AI output: hand back case C')
                ai = (ai[0], ai[1], 'already')
        if ai is not None:
            aa = Archive(ai[1], ('MANIFEST.json', 'output'))
            if aa.manifest.get('job_dir') != man['job_dir']:
                stop('RESTORE_AI_CONFLICT', 'the AI archive names another job folder')
            aa.close()
        plan['out_rel'] = out_rel
    # PNG (step 12)
    png_src = None
    if png and not fz_newest:
        png_src = restore_png(ctx, lst, inbox, block, a, man, plan)
        if png_src is None:
            save_plan(ctx, plan)
            need(block, 'RESTORE_NEED_PARTS')
    a.close()
    rp = {'package': newest['name'], 'package_path': str(npath), 'fz_newest': fz_newest, 'genesis': str(gen_path) if gen_path else None,
          'notes': {k: str(v) for k, v in notes.items()}, 'run_tag': newest['tag'] if not qual else None, 'job_dir': man['job_dir'],
          'png': png_src, 'ai': list(ai) if ai else None, 'out_rel': plan.get('out_rel'),
          'rejected_copies': plan.get('rejected_why', []), 'ai_corrupt': plan.get('ai_corrupt_start', []),
          'chosen': (plan.get('chosen') or {}).get(newest['name'])}
    return place_restore(ctx, rp, lst)


def write_stray(ctx, paths):
    members = []
    base = ctx.lay.base
    for root in paths:
        root = Path(root)
        if os.path.islink(root):
            continue
        if root.is_file():
            members.append((root.relative_to(base).as_posix(), 'file', stat.S_IMODE(os.lstat(root).st_mode) & 0o777, 0, str(root)))
            continue
        if not root.is_dir():
            continue
        members.append((root.relative_to(base).as_posix(), 'dir', stat.S_IMODE(os.lstat(root).st_mode), 0, None))
        for dp, dns, fns in os.walk(root, followlinks=False):
            for n in sorted(dns + fns):
                p = Path(dp) / n
                st_ = os.lstat(p)
                rel = p.relative_to(base).as_posix()
                if stat.S_ISDIR(st_.st_mode):
                    members.append((rel, 'dir', stat.S_IMODE(st_.st_mode) & 0o777, 0, None))
                elif stat.S_ISREG(st_.st_mode):
                    members.append((rel, 'file', stat.S_IMODE(st_.st_mode) & 0o777, int(st_.st_mtime), str(p)))
    if not members:
        return None
    name = f'STRAY_{utc14()}_{h8(sha_bytes(current_boot_id().encode()))}.tgz'
    dest = ctx.lay.outbox / name
    man = {'schema': 'cps.vm-stray.v1', 'created_utc': utc(), 'paths': [m[0] for m in members]}
    write_tgz(dest, [('MANIFEST.json', 'file', 0o444, 0, note_bytes(man))] + members)
    return dest


def rerender(ctx, a, man, workdir):
    """6.4: re-render the PNG set from the package's rendered.pdf files; {member path: bytes} or None."""
    want = {f['path']: f for f in (man.get('png') or {}).get('files') or []}
    got = {}
    env = dict(os.environ, LC_ALL='C.UTF-8', TZ='UTC')
    pdftoppm = shutil.which('pdftoppm')
    if not pdftoppm:
        return None
    for sub in ('qa/visual_deliverable', 'qa/visual_internal'):
        mp, pp = f'job/{sub}/VISUAL_QA_MANIFEST.json', f'job/{sub}/rendered.pdf'
        if mp not in a.by or pp not in a.by:
            continue
        vm = sjson(a.read(mp))
        d = Path(workdir) / sub.replace('/', '_')
        d.mkdir(parents=True)
        pdf = d / 'rendered.pdf'
        pdf.write_bytes(a.read(pp))
        if not isinstance(vm.get('dpi'), int) or isinstance(vm.get('dpi'), bool):
            return None
        dpi = str(vm.get('dpi'))
        try:
            subprocess.run([pdftoppm, '-r', dpi, '-png', str(pdf), str(d / 'page')], env=env, capture_output=True, timeout=1800, check=True)
        except (subprocess.SubprocessError, OSError):
            return None
        for p in d.glob('page-*.png'):
            n = int(p.stem.split('-')[-1])
            got[f'job/{sub}/page-{n:04d}.png'] = p.read_bytes()
        for img in vm.get('images') or []:
            n = img.get('page')
            tiles = img.get('tiles') or []
            if not isinstance(n, int) or isinstance(n, bool) or not all(isinstance(t, dict) and all(
                    isinstance(t.get(k), int) and not isinstance(t.get(k), bool) for k in ('x', 'y', 'width_px', 'height_px'))
                    and isinstance(t.get('file'), str) and not unsafe_name(t['file']) for t in tiles):
                return None                             # T-04: only plain numbers and safe names reach pdftoppm and paths
            for k, t in enumerate(tiles, start=1):
                stem = d / f'tile-{n}-{k}'
                try:
                    subprocess.run([pdftoppm, '-r', dpi, '-f', str(n), '-l', str(n), '-x', str(t['x']), '-y', str(t['y']),
                                    '-W', str(t['width_px']), '-H', str(t['height_px']), '-singlefile', '-png', str(pdf), str(stem)],
                                   env=env, capture_output=True, timeout=600, check=True)
                except (subprocess.SubprocessError, OSError):
                    return None
                out = stem.with_name(stem.name + '.png')
                if out.is_file():
                    got[f'job/{sub}/{t["file"]}'] = out.read_bytes()
    res = {}
    for path, f in want.items():
        b = got.get(path)
        if b is None or sha_bytes(b) != f['sha256']:
            return None
        res[path] = b
    return res


def restore_png(ctx, lst, inbox, block, a, man, plan=None):
    png = man['png']
    parts = png.get('parts') or []
    have = [inbox / p['name'] for p in parts]
    store = inbox / 'png_restore'
    plan = plan if plan is not None else {}
    if all(p.is_file() for p in have) and parts:
        again = False
        for part, p in zip(parts, have):
            if sha_file(p) != part['sha256']:
                fs = [f for f in lst.by.get(part['name'], []) if file_matches(f, part.get('md5'), part.get('bytes'))]
                if fs and md5_file(p) != part['md5']:  # T-03: Drive holds the right part; this download was damaged
                    n = plan.setdefault('redownloads', {}).get(fs[0]['id'], 0) + 1
                    plan['redownloads'][fs[0]['id']] = n
                    p.unlink()
                    if n > REDOWNLOAD_MAX:
                        stop('RESTORE_DOWNLOAD_FAILED', 'a PNG part downloaded damaged several times: hand back case C',
                             detail={'name': part['name']})
                    block.download(fs[0]['id'], part['name'], p)
                    again = True
                    continue
                p.unlink()
                stop('RESTORE_PARTS_MISMATCH', 'a downloaded PNG part differs from the manifest: hand back case C', detail={'name': part['name']})
        if again:
            return None
        data = b''.join(p.read_bytes() for p in have)
        if sha_bytes(data) != png['set_sha256']:
            stop('RESTORE_PARTS_MISMATCH', 'the joined PNG tar differs from the manifest: hand back case C')
        tpath = inbox / 'png_set.tar'
        tpath.write_bytes(data)
        return {'source': 'parts', 'tar': str(tpath)}
    with tempfile.TemporaryDirectory(prefix='cps_vm_png_') as td:
        res = rerender(ctx, a, man, td)
    if res is not None:
        if store.exists():
            remove_tree(store)
        store.mkdir(parents=True)
        idx = {}
        for i, (path, b) in enumerate(sorted(res.items())):
            f = store / f'{i:05d}.png'
            f.write_bytes(b)
            idx[path] = str(f)
        return {'source': 'rerendered', 'files': idx}
    for part in parts:
        fs = [f for f in lst.by.get(part['name'], []) if file_matches(f, part.get('md5'), part.get('bytes'))] or lst.by.get(part['name'], [])
        block.download(fs[0]['id'], part['name'], inbox / part['name'])
    return None


def png_tar_files(tf, man):
    """T-04: the PNG tar's members under the 3.6 rules: regular files, safe names, each listed once in png.files with its
    sha256, nothing else; {path: bytes}."""
    want = {x['path']: x for x in man['png']['files']}
    out = {}
    for m in tf.getmembers():
        if not m.isreg() or unsafe_name(m.name) or m.name not in want or m.name in out or m.mode & 0o7000:
            stop('ARCHIVE_UNSAFE_MEMBER', 'PNG tar', detail={'path': m.name[:200]})
        b = tf.extractfile(m).read()
        if len(b) != want[m.name].get('bytes', len(b)) or sha_bytes(b) != want[m.name]['sha256']:
            stop('ARCHIVE_MEMBER_SHA_MISMATCH', 'PNG tar', detail={'path': m.name[:200]})
        out[m.name] = b
    if set(out) != set(want):
        stop('ARCHIVE_MANIFEST_MISMATCH', 'PNG tar', detail={'missing': sorted(set(want) - set(out))[:5]})
    return out


def place_restore(ctx, rp, lst):
    """6.5 steps 14-18, resumable through RESTORE_IN_PROGRESS.json."""
    lay = ctx.lay
    rp = dict(rp, listing_folder=lst.folder if lst is not None else None)
    rp['listing_copies'] = {}
    if lst is not None:
        for n in list(rp['notes']) + ([rp['package']] if rp.get('package') else []):
            if lst.has(n):
                f = lst.copies(n)[0]
                rp['listing_copies'][n] = {'id': f['id'], 'created': f['created'], 'md5': f['md5'], 'size': f['size']}
    write_atomic(lay.outbox / 'RESTORE_IN_PROGRESS.json', note_bytes(rp))
    return do_place(ctx, rp)


def restore_done(lay):
    """r2 R2-05: called once SESSION_STATE (and, for a session, its SESSION note) holds the restore's result."""
    for n in ('RESTORE_IN_PROGRESS.json', 'RESTORE_PLAN.json'):
        if (lay.outbox / n).exists():
            (lay.outbox / n).unlink()


def restore_resume(ctx):
    rp = read_json_file(ctx.lay.outbox / 'RESTORE_IN_PROGRESS.json')
    if not isinstance(rp, dict):
        stop('RESTORE_RESUME_INVALID', 'RESTORE_IN_PROGRESS.json is damaged: hand back case C')
    return do_place(ctx, rp)


def do_place(ctx, rp):
    lay = ctx.lay
    qual = ctx.mode == 'qualification'
    man, led_raw = None, None
    a = None
    if rp.get('package'):
        a = Archive(rp['package_path'], ('MANIFEST.json', 'ledger', 'job'))
        check_pkg_manifest(a)
        man = a.manifest
        if qual:
            led_raw = a.read('ledger/LEDGER.jsonl')
    elif qual:
        gen = read_json_file(rp['genesis'])
        led_raw = gen['identity_line'].encode('utf-8') + b'\n'
    # 14: INDEX
    if rp.get('package') and (ctx.index.get(rp['package']) or {}).get('origin') != 'restored':
        p = parse_name(rp['package'])
        lc = rp['listing_copies'].get(rp['package']) or {}
        pp = Path(rp['package_path'])
        ctx.index.add(name=rp['package'], kind='package', folder=rp.get('listing_folder'), sha256=sha_file(pp), md5=md5_file(pp),
                      bytes=os.lstat(pp).st_size, created_utc=man.get('created_utc'), origin='restored', drive_id=lc.get('id'),
                      drive_created=lc.get('created'), job_dir=man.get('job_dir'), case_id=p['case'], tag=p['tag'], seq=p['seq'],
                      record_sha256=man['record']['sha256'], ledger_sha256=(man.get('ledger') or {}).get('sha256'), meta=pkg_meta(man))
        ctx.index.event('verified', rp['package'], drive_id=lc.get('id'), method='restore_download')
    # 15: ledger
    if qual and not lay.ledger_dir.exists():
        for old in lay.base.glob('.cps_vm_stage_ledger_*'):
            remove_tree(old)
        sd = lay.base / f'.cps_vm_stage_ledger_{os.getpid()}'
        os.mkdir(sd, 0o755)
        lp = sd / 'LEDGER.jsonl'
        with open(lp, 'xb') as f:
            f.write(led_raw)
        os.chmod(lp, ((man or {}).get('ledger') or {}).get('mode', 0o644))
        os.rename(sd, lay.ledger_dir)
    # 16: job folder
    if man is not None and not rp.get('fz_newest') and not Path(man['job_dir']).exists():
        stg = Staging(man['job_dir'])
        root_mode = next((m['mode'] for m in man['members'] if m['path'] == 'job'), 0o755)
        stg.begin(root_mode)
        for m in man['members']:
            if m['path'] == 'job':
                continue
            if not m['path'].startswith('job/'):          # T-25
                stop('ARCHIVE_UNSAFE_MEMBER', 'a package member outside job/', detail={'path': m['path'][:200]})
            rel = m['path'][4:]
            if m['type'] == 'dir':
                stg.add_dir(rel, m['mode'])
            else:
                stg.add_file(rel, a.read(m['path']), m['mode'])
        png = rp.get('png')
        if png and png['source'] == 'rerendered':
            for path, f in png['files'].items():
                pm = next(x for x in man['png']['files'] if x['path'] == path)
                stg.add_file(path[4:], Path(f).read_bytes(), pm['mode'])
        elif png and png['source'] == 'parts':
            with tarfile.open(png['tar'], 'r:') as tf:
                want = {x['path']: x for x in man['png']['files']}
                for path, b in png_tar_files(tf, man).items():
                    stg.add_file(path[4:], b, want[path]['mode'])
        ai = rp.get('ai')
        if ai and len(ai) == 2:
            aa = Archive(ai[1], ('MANIFEST.json', 'output'))
            out_rel = rp['out_rel'][4:]
            if out_rel not in stg.modes:
                stg.add_dir(out_rel, aa.manifest.get('output_mode', 0o755))
            for rel, kind, mode, size, sha in aa.manifest.get('tree') or []:
                if kind == 'dir':
                    stg.add_dir(out_rel + '/' + rel, mode)
                else:
                    stg.add_file(out_rel + '/' + rel, aa.read('output/' + rel), mode)
            aa.close()
        stg.finish()
    # 17: notes, FZ-light records
    for n, p in rp['notes'].items():
        if Path(p).is_file():
            restore_note(ctx, n, p, ListingStub(rp))
            if parse_name(n)['kind'] == 'ai':
                e = ctx.index.get(n)
                aa = Archive(p, ('MANIFEST.json', 'output'))
                m = aa.manifest
                aa.close()
                ctx.index.add(name=n, kind='ai', folder=e.get('folder'), sha256=e.get('sha256'), md5=e.get('md5'), bytes=e.get('bytes'),
                              created_utc=m.get('created_utc'), origin='restored', drive_id=e.get('drive_id'), drive_created=e.get('drive_created'),
                              job_dir=m.get('job_dir'), case_id=m.get('case_id'), tag=m.get('tag'), role=m.get('role'), attempt=m.get('attempt'),
                              tree_sha256=m.get('tree_sha256'), payload=e.get('payload'), meta=ai_meta(m))
            if parse_name(n)['kind'] == 'inputs':
                place_inputs(ctx, p)
    if rp.get('genesis') and Path(rp['genesis']).is_file():
        restore_note(ctx, Path(rp['genesis']).name, rp['genesis'], ListingStub(rp))
    if man is not None and rp.get('fz_newest'):
        tag, case = man['tag'], man['case_id']
        lay.frozen_json.mkdir(parents=True, exist_ok=True)
        fj = lay.frozen_json / f'{tag}_{case}_FROZEN.json'
        if not fj.exists():
            write_atomic(fj, a.read('job/FROZEN.json'))
        write_atomic(lay.frozen_json / f'{tag}_{case}_FLAGS.json', note_bytes({'reset_diverged': bool(man.get('reset_diverged')), 'fz': rp['package']}))
        pend = fz_pending(ctx)
        if not any(e['fz'] == rp['package'] for e in pend):
            pend.append({'fz': rp['package'], 'job_dir': man['job_dir'], 'tag': tag, 'case': case})
            write_atomic(lay.outbox / 'FZ_PENDING.json', note_bytes(pend))
    if a is not None:
        a.close()
    # 18
    st = ctx.state if isinstance(ctx.state, dict) else {}
    st['ai_corrupt'] = rp.get('ai_corrupt') or []
    st['rejected_copies'] = rp.get('rejected_copies') or []
    # r2 R2-05: RESTORE_IN_PROGRESS.json stays until the caller has saved SESSION_STATE (and the SESSION note): a kill in
    # between resumes the (idempotent) placement instead of falling into local mode without them
    return {'package': rp.get('package'), 'ai_archives_placed': [rp['ai'][0]] if rp.get('ai') and len(rp['ai']) == 2 else [],
            'png': (rp.get('png') or {}).get('source'), 'notes': sorted(rp['notes']), 'rejected_copies': rp.get('rejected_copies') or [],
            'ai_corrupt': rp.get('ai_corrupt') or [], 'fz_newest': bool(rp.get('fz_newest'))}


class ListingStub:
    def __init__(self, rp):
        self.folder = rp.get('listing_folder')
        self.cp = rp.get('listing_copies') or {}

    def has(self, n):
        return n in self.cp

    def copies(self, n):
        c = self.cp[n]
        return [{'id': c['id'], 'created': c['created'], 'md5': c['md5'], 'size': c['size']}]


def ai_meta(m):
    return {'response_present': m.get('response_present'), 'response_sha256': m.get('response_sha256'),
            'unexpected': m.get('unexpected') or [], 'revision': m.get('revision', 1), 'after_refusal': m.get('after_refusal'),
            'start_note': m.get('start_note'), 'record_seq_at_archive': m.get('record_seq_at_archive')}


def place_inputs(ctx, p):
    a = Archive(p, ('MANIFEST.json', 'inputs'))
    try:
        man = a.manifest
        case = man.get('case_id')
        files = man.get('files') or {}
        if not isinstance(case, str) or not re.fullmatch(CASE, case, re.ASCII) or not isinstance(files, dict) or \
                any(not isinstance(n, str) or '/' in n or unsafe_name(n) for n in files):
            a.bad('ARCHIVE_UNSAFE_MEMBER', {'why': 'inputs manifest'})
        exp = {'inputs': ('dir', 0o755)}
        for n, h in files.items():
            m = a.by.get('inputs/' + n)
            exp['inputs/' + n] = ('file', stat.S_IMODE(m.mode) if m else 0o644, m.size if m else -1, h)
        a.check(exp)
        d = ctx.lay.everyday_inputs / case
        if d.exists():                              # T-24: a placement already made (a resumed restore) must match the manifest
            if inputs_shas(d, man) != files:
                stop('RESTORE_TARGET_NOT_EMPTY', 'BASE/everyday_inputs/<case> holds other files: do not delete anything; hand back case C')
            return
        stg = Staging(d)
        stg.begin(0o755)
        for n in sorted(files):
            stg.add_file(n, a.read('inputs/' + n), 0o644)
        stg.finish()
    finally:
        a.close()


# ------------------------------------------------------------------ packages (spec 3.3, 3.4)
def concerns(inc, tag, case):
    c = inc['content']
    if c.get('tag') == tag and c.get('case_id') == case:
        return True
    pj = c.get('pending_job') or {}
    return pj.get('tag') == tag and pj.get('case') == case


def seen_tokens(incs):
    out = []
    for i in incs:
        for t in i['content'].get('seen') or []:
            out.append(t)
    return out


def carried_obligations(ctx, pre_newest, tag, case):
    """T-05: incident names a package carried forward because its runner stage was refused before any comparison."""
    e = ctx.index.get(pre_newest) if pre_newest else None
    if not e or (e.get('tag'), e.get('case_id')) != (tag, case):
        return []
    return list((((e.get('meta') or {}).get('binding')) or {}).get('pending') or [])


def compute_binding(ctx, jv, sub, pre_newest, completed_entry):
    """5.5 step 4: (reset_diverged, binding dict or None). T-05: an obligation with a real seen token is consumed only by a
    comparison (a completed stage); a refused stage carries it forward in its package's binding.pending."""
    carried = set(carried_obligations(ctx, pre_newest, jv.tag, jv.case))
    obl = [i for i in incidents(ctx) if concerns(i, jv.tag, jv.case) and i['content'].get('next_subcommand') == sub
           and (i['content'].get('newest_package') == pre_newest or i['name'] in carried)]
    prev = newest_package(ctx, jv.tag, jv.case)
    inherited = bool(((prev or {}).get('meta') or {}).get('reset_diverged'))
    forced = any(i['content'].get('forces_reset_diverged') for i in incidents(ctx) if concerns(i, jv.tag, jv.case))
    if not obl:
        return inherited or forced, None
    toks = [parse_token(t) for t in seen_tokens(obl)]
    real = [t for t in toks if t and not t['none']]
    own = None
    if completed_entry is not None:
        own = token_text(sub, jv.tag, jv.case, completed_entry, saved_xlsx8(jv.dir), False)
    diverged, matched, compared, pending = inherited or forced, True, False, []
    if any(t['D'] for t in real) or len({tuple(t['fields']) for t in real}) > 1:
        diverged, matched, compared = True, False, True
    elif real and own is not None:
        of = parse_token(own)['fields']
        compared = True
        if any(tuple(t['fields']) != tuple(of) for t in real):
            diverged, matched = True, False
    elif real:                                      # refused before a comparison: kept in force for the next run of sub
        matched = None
        pending = [i['name'] for i in obl if any((parse_token(t) or {}).get('none') is False for t in i['content'].get('seen') or [])]
    b = {'subcommand': sub, 'incidents': [i['name'] for i in obl], 'seen': seen_tokens(obl),
         'not_seen': [i['name'] for i in obl if i['content'].get('not_seen')], 'own': own, 'matched': matched,
         'compared': compared, 'pending': pending, 'applied_by': None}
    return diverged, b


def build_package(ctx, jv, sub, pre_newest, command, completed_entry, applied_by='wrap'):
    """Make the save point of the job's current state when its state key changed; returns info or None (no folder)."""
    lay = ctx.lay
    if not jv.dir.is_dir():
        return None
    jv = JobView(ctx, jv.dir)
    if jv.record_sha() is None:                     # T-09: a folder without RUN_RECORD.json is no runner job
        stop('PACKAGE_NO_RECORD', 'the job folder has no RUN_RECORD.json: do not delete anything; hand back case C',
             block=Block(), detail={'job_dir': str(jv.dir)})
    qual = ctx.mode == 'qualification'
    led_raw, led_entries = (None, [])
    if qual:
        led_raw, led_entries = read_ledger(ctx)
        recs = [e for e in led_entries if e.get('job_dir') == str(jv.dir) and e.get('type') in ('prepare', 'nonattempt', 'record')]
        if not recs or recs[-1].get('run_record_sha256') != jv.record_sha():
            stop('LEDGER_BEHIND_RECORD', 'the ledger has not recorded the newest record entry; the next runner command catches it up',
                 block=Block())
    fz_path = jv.dir / 'FROZEN.json'
    last = jv.last()
    frozen_done = fz_path.is_file() and last is not None and last['stage'] == 'freeze' and last['result'] == 'FROZEN'
    kind = 'FZ' if frozen_done else 'CP'
    fsha = sha_file(fz_path) if frozen_done else None
    lsha = sha_bytes(led_raw) if qual else None
    rsha = jv.record_sha()
    prev = newest_package(ctx, jv.tag, jv.case)
    pm = (prev or {}).get('meta') or {}
    if prev is not None and (pm.get('pkind'), pm.get('ledger_sha256'), pm.get('record_sha256'), pm.get('frozen_sha256')) == (kind, lsha, rsha, fsha):
        return {'name': prev['name'], 'path': prev.get('payload'), 'existing': True, 'reset_diverged': bool(pm.get('reset_diverged')),
                'parts': [p['name'] for p in pm.get('png_parts') or []], 'meta': pm}
    diverged, binding = compute_binding(ctx, jv, sub, pre_newest, completed_entry)
    if binding is not None:
        binding['applied_by'] = applied_by
    own = token_text(sub, jv.tag, jv.case, completed_entry, saved_xlsx8(jv.dir), diverged) if completed_entry is not None else None
    if binding is not None:
        binding['own'] = own
    # PNG set and parts
    rels = png_set(jv.dir)
    png = None
    new_parts = []
    if rels:
        tmp = lay.outbox / f'.tmp_{os.getpid()}_png.tar'
        if tmp.exists():
            tmp.unlink()
        with open(tmp, 'xb') as f:
            write_tar_stream(f, png_tar_members(jv.dir, rels))
        set_sha = sha_file(tmp)
        files = [{'path': 'job/' + r, 'mode': stat.S_IMODE(os.lstat(jv.dir / r).st_mode), 'bytes': os.lstat(jv.dir / r).st_size,
                  'sha256': sha_file(jv.dir / r)} for r in rels]
        earlier = [p for p in packages(ctx, jv.tag, jv.case) if (p.get('meta') or {}).get('png_set_sha256') == set_sha]
        if earlier:
            em = earlier[-1]['meta']
            parts, made_by = em['png_parts'], em.get('png_made_by') if em.get('png_made_by') not in (None, 'self') else earlier[-1]['name']
            tmp.unlink()
        else:
            pb = ctx.cfg['png_part_bytes']
            size = os.lstat(tmp).st_size
            n = max(1, (size + pb - 1) // pb)
            parts = []
            with open(tmp, 'rb') as f:
                for k in range(1, n + 1):
                    data = f.read(pb)
                    name = f'PNG_{jv.tag}_{h8(set_sha)}_{k:02d}of{n:02d}_{jv.case}.part'
                    pp = lay.outbox / name
                    ensure_file(pp, data)
                    parts.append({'name': name, 'bytes': len(data), 'sha256': sha_bytes(data),
                                  'md5': hashlib.md5(data, usedforsecurity=False).hexdigest()})
                    new_parts.append(pp)
            tmp.unlink()
            made_by = 'self'
        png = {'set_sha256': set_sha, 'files': files, 'parts': parts, 'part_bytes': ctx.cfg['png_part_bytes'], 'made_by_package': made_by}
    skip = set(rels)
    entries = [e for e in tree_list(jv.dir) if e[0] not in skip]
    root_mode = stat.S_IMODE(os.lstat(jv.dir).st_mode)
    members = [{'path': 'job', 'type': 'dir', 'mode': root_mode}]
    for rel, k, mode, size, sha in entries:
        members.append({'path': 'job/' + rel, 'type': k, 'mode': mode} if k == 'dir' else
                       {'path': 'job/' + rel, 'type': k, 'mode': mode, 'bytes': size, 'sha256': sha})
    rec_seq = len(jv.stages())
    frozen = None
    if kind == 'FZ':
        frozen = {'frozen_sha256': fsha, 'verify_frozen': (command or {}).get('verify_frozen')}
    ident = sha_bytes(led_raw.split(b'\n', 1)[0] + b'\n') if qual and led_raw else None
    man = {'schema': 'cps.vm-package.v1', 'kind': kind, 'created_utc': utc(), 'helper': helper_info(),
           'runner_sha256': sha_file(runner_path()), 'boot_id': current_boot_id(), 'fingerprint_sha256': ctx.state['fingerprint_sha256'],
           'mode': ctx.mode, 'case_id': jv.case, 'reader': jv.reader, 'tag': jv.tag, 'job_dir': str(jv.dir),
           'jobs_root': str(jv.dir.parent), 'run_id': None if qual else jv.tag,
           'ledger': ({'path': str(lay.ledger), 'seq': len(led_entries), 'bytes': len(led_raw), 'sha256': lsha,
                       'identity_line_sha256': ident, 'mode': stat.S_IMODE(os.lstat(lay.ledger).st_mode)} if qual else None),
           'record': {'sha256': rsha, 'seq': rec_seq, 'last_completed': ({'stage': last['stage'], 'result': last['result'], 'next': last['next']}
                                                                        if last else None),
                      'marker_present': (jv.dir / CJ.MARKER_NAME).exists()},
           'frozen': frozen, 'command': command if command else None, 'binding': binding, 'reset_diverged': bool(diverged),
           'previous_package': ({'name': prev['name'], 'sha256': prev.get('sha256')} if prev else None),
           'members': members, 'png': png,
           'deliverable_xlsx_sha256': ((read_json_file(jv.dir / 'qa' / 'SAVED_QA.json') or {}).get('deliverable_xlsx') or {}).get('sha256')
           if (jv.dir / 'qa' / 'SAVED_QA.json').is_file() else None}
    if command is None:
        man['command'] = None
        man['reason'] = 'package'
    seqkind, seq = ('L', len(led_entries)) if qual else ('R', rec_seq)
    tmp = lay.outbox / f'.tmp_{os.getpid()}.tgz'
    if tmp.exists():
        tmp.unlink()
    mm = [('MANIFEST.json', 'file', 0o444, 0, note_bytes(man))]
    if qual:
        mm.append(('ledger/LEDGER.jsonl', 'file', man['ledger']['mode'], 0, led_raw))
    mm.append(('job', 'dir', root_mode, int(os.lstat(jv.dir).st_mtime), None))
    for rel, k, mode, size, sha in entries:
        p = jv.dir / rel
        mm.append(('job/' + rel, k, mode, int(os.lstat(p).st_mtime), None if k == 'dir' else str(p)))
    write_tgz(tmp, mm)
    chk = Archive(tmp, ('MANIFEST.json', 'ledger', 'job'))  # r2 R2-07: read the package back as restore will
    try:
        check_pkg_manifest(chk)
        chk.check(pkg_expected(chk.manifest))
    finally:
        chk.close()
    pkg8 = h8(sha_file(tmp))
    name = package_name(kind, jv.tag, seqkind, seq, h8(lsha) if qual else '00000000', h8(rsha), h8(fsha) if fsha else '00000000',
                        h8(ctx.state['fingerprint_sha256']), pkg8, jv.case)
    final = lay.outbox / name
    os.rename(tmp, final)
    folder = ctx.records_folder()
    uploads = []
    for pp in new_parts:
        e = next(x for x in png['parts'] if x['name'] == pp.name)
        if ctx.index.get(pp.name) is None:
            ctx.index.add(name=pp.name, kind='png', folder=folder, sha256=e['sha256'], md5=e['md5'], bytes=e['bytes'], created_utc=utc(),
                          origin='made', payload=str(pp), job_dir=str(jv.dir), case_id=jv.case, tag=jv.tag)
        uploads.append(pp)
    meta = pkg_meta(man)
    uploads += made(ctx, final, 'package', folder, job_dir=str(jv.dir), case_id=jv.case, tag=jv.tag, seq=seq, record_sha256=rsha,
                    ledger_sha256=lsha, meta=meta)
    # an older CP payload of the job is deleted once a listing confirmed it (integrity-F14)
    for old in packages(ctx, jv.tag, jv.case):
        if old['name'] != name and (old.get('meta') or {}).get('pkind') == 'CP' and old.get('origin') == 'made' and old.get('payload') \
                and ctx.index.confirmed(old['name']) and Path(old['payload']).is_file():
            Path(old['payload']).unlink()
            ctx.index.event('payload_deleted', old['name'])
    if kind == 'FZ':
        lay.frozen_json.mkdir(parents=True, exist_ok=True)
        write_atomic(lay.frozen_json / f'{jv.tag}_{jv.case}_FROZEN.json', fz_path.read_bytes())
        write_atomic(lay.frozen_json / f'{jv.tag}_{jv.case}_FLAGS.json', note_bytes({'reset_diverged': bool(diverged), 'fz': name}))
    return {'name': name, 'path': str(final), 'existing': False, 'reset_diverged': bool(diverged), 'uploads': uploads,
            'parts': [p['name'] for p in (png or {}).get('parts', [])], 'meta': meta, 'binding': binding, 'own': own}


def package_uploads(ctx, info):
    """The UPLOAD paths of a package: its parts (when still local and unconfirmed), then the core (slices first)."""
    if info is None:
        return []
    if not info.get('existing'):
        return info['uploads']
    out = []
    for pn in info.get('parts') or []:
        e = ctx.index.get(pn)
        if e and e.get('payload') and Path(e['payload']).is_file() and not ctx.index.confirmed(pn):
            out.append(Path(e['payload']))
    if info.get('path') and Path(info['path']).is_file():
        out += upload_paths(ctx, info['path'], ctx.records_folder())
    return out


# ------------------------------------------------------------------ wrap, package, detached workers (spec 5.5, 5.6, 5.19)
def runner_opts(rargs):
    d, i = {}, 0
    while i < len(rargs):
        k = rargs[i]
        if k == '--qualification':
            d['qualification'] = True
            i += 1
            continue
        if k.startswith('--') and i + 1 < len(rargs):
            d[k[2:].replace('-', '_')] = rargs[i + 1]
            i += 2
            continue
        refuse('WRAP_ARGUMENTS', 'run the exact line status printed')
    return d


def require_session_ready(ctx, block=None):
    st = ctx.state
    if not st.get('fingerprint_pass'):
        refuse('FINGERPRINT_NOT_PASSED', 'run the self-test on this VM first (RUN $V selftest)')


def require_no_incident(ctx):
    if ctx.state.get('pending_incident'):
        b = Block()
        refuse('INCIDENT_REQUIRED', 'record the incident status prints first', block=b)


def require_recheck(ctx):
    if ctx.state.get('restore_recheck'):
        b = Block()
        b.listing(ctx.records_folder(), ctx.lay.inbox / 'DRIVE_LISTING.json')
        b.next(f'RUN {ctx.V} recheck')
        need(b, 'RESTORE_RECHECK_REQUIRED')


def consume_confirms(ctx):
    d = ctx.lay.inbox / 'confirm'
    if not d.is_dir():
        return
    for p in sorted(d.glob('*.json')):
        name = p.name[:-5]
        lst = read_listing(ctx, p, ctx.records_folder(), name)
        ingest_listing(ctx, lst)
        if not ctx.index.confirmed(name):           # T-06: this narrow listing showed no matching copy
            ctx.index.event('narrow_miss', name)
        p.unlink()
    try:
        d.rmdir()
    except OSError:
        pass


def confirm_line(ctx, block, name):
    block.listing(ctx.records_folder(), ctx.lay.inbox / 'confirm' / (name + '.json'), name)


def require_unconfirmed(ctx, jv):
    st = ctx.state
    left = [n for n in st.get('unconfirmed') or [] if not ctx.index.confirmed(n)]
    if left != (st.get('unconfirmed') or []):
        st['unconfirmed'] = left
        ctx.save_state()
    mine = [n for n in left if jv is None or ((ctx.index.get(n) or {}).get('tag'), (ctx.index.get(n) or {}).get('case_id')) == (jv.tag, jv.case)]
    if mine:
        b = Block()
        for n in mine:
            confirm_or_upload(ctx, b, n)
        need(b, 'UPLOAD_NOT_CONFIRMED')


def ai_guard(ctx, jv, role):
    T = newest_start(ctx, jv.tag, role, jv.case)
    archs = ai_archives(ctx, jv.tag, role, T['attempt'], jv.case) if T else []
    if not archs:
        refuse('AI_ARCHIVE_MISSING', 'run ai-archive first: the AI output must reach Drive before anything reads it')
    a = archs[-1]
    out = jv.output_dir(role)
    if not out.is_dir() or tree_sha(tree_list(out)) != a.get('tree_sha256'):
        refuse('AI_ARCHIVE_STALE', 'the output folder differs from its archive: run status')
    if ctx.cfg['confirm_ai_before_consume'] and not ctx.index.confirmed(a['name']) and a.get('origin') == 'made':
        b = Block()
        confirm_or_upload(ctx, b, a['name'])
        need(b, 'AI_ARCHIVE_NOT_CONFIRMED')
    return T, a


def wrap_target(ctx, sub, o):
    if sub == 'prepare':
        jp = o.get('job')
        jr = o.get('jobs_root')
        case = (read_json_file(jp) or {}).get('case_id') if jp else None
        if not jr or not isinstance(case, str):
            refuse('WRAP_ARGUMENTS', 'prepare needs --job and --jobs-root')
        return Path(jr) / case
    if sub == 'nonattempt':
        if not o.get('jobs_root') or not o.get('case'):
            refuse('WRAP_NONATTEMPT_JOBS_ROOT', 'nonattempt needs --jobs-root BASE/qual/nonattempts_<reader>')
        return Path(o['jobs_root']) / o['case']
    if not o.get('job_dir'):
        refuse('WRAP_ARGUMENTS', 'the runner command needs --job-dir')
    return Path(o['job_dir'])


def wrap_checks(ctx, sub, rargs):
    lay = ctx.lay
    if sub not in WRAP_SUBS:
        refuse('WRAP_SUBCOMMAND', 'wrap runs prepare, scope-finish, finish, visual-record, deliver-check, interrupt, freeze or nonattempt')
    require_session_ready(ctx)
    require_no_incident(ctx)
    require_recheck(ctx)
    consume_confirms(ctx)
    o = runner_opts(rargs)
    qual = ctx.mode == 'qualification'
    if ctx.mode == 'setup':
        refuse('WRAP_MODE', 'no released kit')
    if 'release' in o and os.path.abspath(o['release']) != str(lay.release_path):
        refuse('WRAP_PATH_OUTSIDE_LAYOUT', '--release is BASE/runtime/RELEASE.json')
    if 'admission' in o and not under(o['admission'], lay.runtime / 'qualification'):
        refuse('WRAP_PATH_OUTSIDE_LAYOUT', '--admission lies under BASE/runtime/qualification/')
    if sub == 'nonattempt' and (not o.get('jobs_root') or o.get('reader') not in ('A', 'B')
                                or os.path.abspath(o['jobs_root']) != str(lay.qual / ('nonattempts_' + o['reader']))):
        refuse('WRAP_NONATTEMPT_JOBS_ROOT', 'nonattempt needs --jobs-root BASE/qual/nonattempts_<reader>')
    target = Path(os.path.abspath(wrap_target(ctx, sub, o)))
    tag, case = lay.tag_of(target)
    if tag is None or (qual != is_qual_tag(tag)):
        refuse('WRAP_PATH_OUTSIDE_LAYOUT', 'the job folder is not in this mode\'s layout')
    if sub == 'prepare' and qual:
        root = target.parent.name
        if o.get('reader', 'A') not in ('A', 'B') or root.startswith('nonattempts_') or root not in (o.get('reader', 'A'), o.get('reader', 'A') + '_restart1'):
            refuse('WRAP_READER_ROOT_MISMATCH', '--reader must match the jobs root (qual/A or qual/A_restart1 for reader A)')
        _, ents = read_ledger(ctx)
        first = [e for e in ents if e.get('type') == 'prepare' and e.get('case_id') == case and e.get('reader') == o.get('reader', 'A')]
        if root.endswith('_restart1') and not first:
            refuse('WRAP_READER_ROOT_MISMATCH', 'a restart root is used only after the first run of this case and reader')
    if sub == 'prepare' and not qual:
        runs = [e for e in ctx.index.of('inputs') if e.get('tag') == tag]
        if not runs:
            refuse('WRAP_PATH_OUTSIDE_LAYOUT', 'an everyday prepare uses the run id job-start printed')
        if packages(ctx, tag) or len([e for e in incidents(ctx) if e['content'].get('next_subcommand') == 'prepare'
                                      and (e['content'].get('pending_job') or {}).get('tag') == tag]) > 1:
            refuse('WRAP_EVERYDAY_REPREPARE_USED', 'this run was prepared already (one re-prepare after a lost prepare)')
        im = inputs_manifest(run_inputs(ctx, tag))
        jp = Path(o.get('job') or '')
        if im is None or jp.parent != lay.everyday_inputs / case or inputs_shas(jp.parent, im) != im.get('files'):
            refuse('WRAP_INPUTS_CHANGED', 'the inputs differ from the INPUTS archive job-start made: run status')
    fl = in_flight(ctx)
    if sub in ('prepare', 'nonattempt') and fl:
        refuse('WRAP_RUN_IN_FLIGHT', 'another job folder is not frozen')
    if sub == 'interrupt' and not qual:
        refuse('WRAP_INTERRUPT_EVERYDAY', 'everyday: freeze, then job-start --restart-of (once)')
    jv = JobView(ctx, target)
    prev = newest_package(ctx, tag, case)
    failed = run_failed_by_reset(ctx, tag, case)
    if sub != 'freeze' and failed:
        refuse('WRAP_RUN_FAILED_RESET_DIVERGED', 'this run has failed (reset diverged): only freeze may run; run status')
    if sub == 'prepare' and qual and tag.endswith('-restart1'):
        prev_tag = tag.split('-')[0]
        fl_ = flags_copy(ctx, prev_tag, case)
        fz = fz_for(ctx, prev_tag, case)
        if fl_.get('reset_diverged') or ((fz or {}).get('meta') or {}).get('reset_diverged'):
            refuse('WRAP_RESTART_AFTER_DIVERGED', 'a run that failed by reset divergence never gets the rule-3 restart')
    chain_newest = newest_package(ctx, chain=chain_of(tag))
    pre_newest = prev['name'] if prev else (chain_newest['name'] if chain_newest else None)
    cur_chain = chain_newest['name'] if chain_newest else None
    carried = set(carried_obligations(ctx, pre_newest, tag, case))
    # r2 C2: a run failed by reset divergence may always be frozen, whatever runner command a seen token bound
    binding_incidents = [] if (sub == 'freeze' and failed) else incidents(ctx)
    for i in binding_incidents:
        if i['name'] in carried and i['content'].get('next_subcommand') != sub:
            refuse('WRAP_BINDING_SUBCOMMAND', 'a seen token still binds another runner command of this job: run the line status prints')
    for i in binding_incidents:
        c = i['content']
        if c.get('next_subcommand') and c.get('newest_package') in (pre_newest, cur_chain):
            jb = (c.get('tag'), c.get('case_id')) if c.get('tag') else ((c.get('pending_job') or {}).get('tag'), (c.get('pending_job') or {}).get('case'))
            if c.get('newest_package') == (newest_package(ctx, *jb)['name'] if jb[0] and newest_package(ctx, *jb) else cur_chain) and \
                    (c['next_subcommand'] != sub or not concerns(i, tag, case)):
                refuse('WRAP_BINDING_SUBCOMMAND', 'the incident binds another runner command or job: run the line status prints')
    if sub in CONSUMING and jv.exists and jv.done(sub):     # T-10: never call the runner for a completed consuming stage
        b = Block()
        b.next(f'RUN {ctx.V} status')
        refuse('WRAP_STAGE_DONE', 'this stage completed already: run status for the next step', block=b)
    if sub in CONSUMING and jv.exists:
        require_unconfirmed(ctx, jv)
        ai_guard(ctx, jv, CONSUMING[sub])
    if sub == 'finish' and not (target / 'run' / 'GENERATION_RECORD.json').is_file():
        b = Block()
        T = newest_start(ctx, tag, 'G', case)
        b.next(f'WRITE_GENERATION_RECORD path={target}/run/GENERATION_RECORD.json example={lay.repo}/deploy/run/GENERATION_RECORD.example.json')
        b.then(f'EXPORT_TRANSCRIPT to={transcript_path(ctx, case, tag, "G", (T or {}).get("attempt") or 1)}')
        b.then(f'RUN {ctx.V} status')
        refuse('WRAP_GENERATION_RECORD_MISSING', 'write the generation record first', block=b)
    if sub == 'interrupt':
        role = jv.role()
        T = newest_start(ctx, tag, role, case) if role in ('S', 'G') else None
        ok = T is not None and any(i['content'].get('classification') == 'AI_NOTHING_WRITTEN' and i['content'].get('start_note') == T['name']
                                   for i in incidents(ctx))
        if not ok:
            refuse('WRAP_INCIDENT_REQUIRED', 'an interrupt needs its AI_NOTHING_WRITTEN incident (with the transcript) first')
    placed = []
    if sub == 'prepare' and qual:
        placed = place_frozen(ctx, case)
    return {'sub': sub, 'tag': tag, 'case': case, 'job_dir': str(target), 'pre_newest': pre_newest, 'placed': placed,
            'pre_len': len(jv.stages()) if jv.rec else 0, 'rargs': rargs}


def place_frozen(ctx, case):
    """5.5: before a qualification prepare of case X, put back every evicted frozen run's FROZEN.json of X."""
    lay = ctx.lay
    _, entries = read_ledger(ctx)
    led = LedgerView(entries)
    todo = []
    for e in led.of('prepare', case_id=case):
        fz = led.of('freeze', job_dir=e['job_dir'])
        if not fz or Path(e['job_dir']).exists():
            continue
        tag, c = lay.tag_of(e['job_dir'])
        b = frozen_copy(ctx, tag, c)
        if b is None:
            f = fz_for(ctx, tag, c)
            if f is None:
                stop('PLACE_FROZEN_MISMATCH', 'no FZ of an evicted run is known: hand back case C')
            p = lay.inbox / f['name']
            if not p.is_file():
                blk = Block()
                blk.download(f.get('drive_id'), f['name'], p)
                need(blk, 'NEED_FZ_FOR_PLACEMENT')
            if h8(sha_file(p)) != parse_name(f['name'])['pkg8']:
                p.unlink()
                stop('PLACE_FROZEN_MISMATCH', 'the downloaded FZ fails its name hash: download it again')
            info = read_fz_member(p)
            b = info['frozen']
            lay.frozen_json.mkdir(parents=True, exist_ok=True)
            write_atomic(lay.frozen_json / f'{tag}_{c}_FROZEN.json', b)
            write_atomic(lay.frozen_json / f'{tag}_{c}_FLAGS.json', note_bytes({'reset_diverged': info['reset_diverged'], 'fz': f['name']}))
            p.unlink()
        if sha_bytes(b) != fz[-1]['frozen_sha256']:
            stop('PLACE_FROZEN_MISMATCH', 'the kept FROZEN.json is not the one the ledger recorded: hand back case C')
        todo.append((e['job_dir'], b))
    if not todo:
        return []
    pl = lay.outbox / 'PLACED.json'
    cur = read_json_file(pl) or [] if pl.is_file() else []
    cur += [{'job_dir': j, 'frozen_sha256': sha_bytes(b)} for j, b in todo]
    write_atomic(pl, note_bytes(cur))
    for j, b in todo:
        Path(j).mkdir(parents=True, mode=0o755)
        write_new(Path(j) / 'FROZEN.json', b, 0o444)
    return [j for j, _ in todo]


def remove_placed(ctx, placed):
    pl = ctx.lay.outbox / 'PLACED.json'
    cur = read_json_file(pl) or [] if pl.is_file() else []
    for j in placed:
        jd = Path(j)
        if jd.exists():
            if sorted(os.listdir(jd)) != ['FROZEN.json']:
                stop('PLACED_FROZEN_CHANGED', 'a placed FROZEN.json folder holds something else: do not delete anything; hand back case C')
            remove_tree(jd)
        cur = [e for e in cur if e['job_dir'] != j]
    if cur:
        write_atomic(pl, note_bytes(cur))
    elif pl.exists():
        pl.unlink()


def spawn(ctx, kind, info, lock):
    lay = ctx.lay
    wid = utc14() + '_' + secrets.token_hex(4)
    d = {'id': wid, 'kind': kind, 'info': info, 'pid': None, 'started_utc': utc(), 'boot_id': current_boot_id(),
         'log': str(lay.outbox / f'{kind}_{wid}.log'), 'out': str(lay.outbox / f'{kind}_{wid}.out'), 'exit': None}
    write_atomic(lay.outbox / 'DETACHED.json', note_bytes(d))
    lock.release()
    with open(d['log'], 'ab') as log:
        p = subprocess.Popen([sys.executable, '-I', '-B', str(HELPER_FILE), '_worker', wid], start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, close_fds=True, env=os.environ.copy())
    d['pid'] = p.pid
    cur = read_json_file(lay.outbox / 'DETACHED.json') or {}
    if cur.get('id') == wid and cur.get('out_written') is None:
        cur['pid'] = p.pid
        write_atomic(lay.outbox / 'DETACHED.json', note_bytes(cur))
    return wait_block(ctx, ctx.cfg['wrap_foreground_seconds'] if ctx.cfg else 240)


def worker_alive(d):
    pid = d.get('pid')
    if not pid or d.get('boot_id') != current_boot_id():
        return False
    try:
        cmd = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    except OSError:
        return False
    return b'_worker' in cmd and d['id'].encode() in cmd


def wait_block(ctx, seconds):
    lay = ctx.lay
    p = lay.outbox / 'DETACHED.json'
    deadline = time.time() + seconds
    while True:
        d = read_json_file(p) if p.is_file() else None
        if not isinstance(d, dict):
            b = plan_status(ctx).block
            b.result = {'command': 'wait', 'detached': None}
            return b
        out = Path(d['out'])
        if out.is_file() and d.get('exit') is not None:
            text = out.read_text(encoding='utf-8')
            with HelperLock(lay, wait=30):
                cur = read_json_file(p)
                if isinstance(cur, dict) and cur.get('id') == d['id']:
                    p.unlink()
            b = Block()
            b.raw_text, b.code = text, d['exit']
            return b
        if not worker_alive(d) and not (d.get('pid') is None and time.time() - (parse_utc(d['started_utc']) or now_dt()).timestamp() < 30):
            time.sleep(0.5)
            d2 = read_json_file(p) or {}
            if Path(d['out']).is_file() and d2.get('exit') is not None:
                continue
            b = Block()
            b.result = {'command': 'wait', 'detached': d['id'], 'kind': d['kind']}
            if d['kind'] == 'wrap':
                b.next(f'RUN {ctx.V} package --job-dir {d["info"]["job_dir"]}')
            else:
                b.next(f'RUN {ctx.V} selftest')
            with HelperLock(lay, wait=30):
                if p.is_file():
                    p.unlink()
            raise Halt('STOP', 'WORKER_DIED', 'the detached command ended without its result', block=b)
        if time.time() >= deadline:
            b = Block()
            b.result = {'command': 'wait', 'detached': d['id'], 'in_progress': True}
            b.next(f'RUN {ctx.V} wait')
            b.code = EXIT_BUSY
            return b
        time.sleep(0.5)


def cmd_wait(a):
    ctx = Ctx()
    return wait_block(ctx, ctx.cfg['wrap_foreground_seconds'] if ctx.cfg else 240)


def cmd_wrap(a):
    ctx = Ctx()
    if not a.args:
        refuse('WRAP_SUBCOMMAND')
    sub, rargs = a.args[0], list(a.args[1:])
    lock = HelperLock(ctx.lay)
    lock.__enter__()
    try:
        clean_placed(ctx)
        if (ctx.lay.outbox / 'DETACHED.json').is_file():
            b = Block()
            b.next(f'RUN {ctx.V} wait')
            refuse('HELPER_BUSY', 'a detached command is in progress', block=b)
        info = wrap_checks(ctx, sub, rargs)
        return spawn(ctx, 'wrap', info, lock)
    finally:
        lock.release()


def cmd_worker(a):
    lay = Layout()
    p = lay.outbox / 'DETACHED.json'
    d = None
    for _ in range(100):
        d = read_json_file(p)
        if isinstance(d, dict) and d.get('id') == a.wid:
            break
        time.sleep(0.1)
    if not isinstance(d, dict) or d.get('id') != a.wid:
        return 2
    with HelperLock(lay, wait=10):
        ctx = Ctx()
        try:
            if d['kind'] == 'wrap':
                b = wrap_work(ctx, d['info'])
            else:
                b = selftest_work(ctx, d['info'])
        except Halt as h:
            b = h.to_block()
        text = b.text()
        write_atomic(Path(d['out']), text.encode('utf-8'))
        cur = read_json_file(p) or d
        cur['exit'] = b.code
        write_atomic(p, note_bytes(cur))
    return 0


def run_runner(ctx, argv, log):
    p = subprocess.run([sys.executable, '-I', '-B', str(runner_path()), *argv], capture_output=True, timeout=7200, env=os.environ.copy())
    with open(log, 'ab') as f:
        f.write(b'$ cps_job.py ' + ' '.join(argv[:1]).encode() + b'\n' + p.stdout + p.stderr)
    out = p.stdout.decode('utf-8', 'replace')
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    lj = None
    for ln in reversed(lines):
        try:
            lj = json.loads(ln)
            break
        except ValueError:
            continue
    return p.returncode, lines, (lines[-1] if lines else ''), lj, sha_bytes(p.stdout)


def scrub(line):
    """Runner lines are copied with RUNNER| ; a DELIVER path holds the title, so it is replaced by its hash."""
    if 'DELIVER file=' in line:
        i = line.index('DELIVER file=') + len('DELIVER file=')
        return line[:i] + CJ.safe_path(line[i:]) if not line[i:].isascii() else line
    return line


def wrap_work(ctx, info):
    lay = ctx.lay
    sub, jd = info['sub'], Path(info['job_dir'])
    log = lay.outbox / f'wrap_{utc14()}_{sub}.log'
    code, lines, last, lj, osha = run_runner(ctx, [sub, *info['rargs']], log)
    if info.get('placed'):
        remove_placed(ctx, info['placed'])
    b = Block()
    b.pre = ['RUNNER| ' + scrub(ln) for ln in lines]
    verify = None
    if sub in ('freeze', 'nonattempt') and last == 'NEXT: DONE':
        vc, _, vlast, vj, _ = run_runner(ctx, ['verify-frozen', '--job-dir', str(jd)], log)
        verify = {'exit': vc if vlast == 'NEXT: DONE' or vc != 0 else 3, 'result': (vj or {}).get('result'), 'json': vj,
                  'last_line': vlast}
    jv = JobView(ctx, jd)
    completed = None
    if last.startswith('NEXT:') and jv.rec:
        e = newest_completed(jv, sub)
        if e is not None and (e['seq'] > info.get('pre_len', 0) or sub == 'freeze'):
            completed = e
    command = {'runner_subcommand': sub, 'argv': [sub, *info['rargs']], 'exit': code, 'last_line': scrub(last), 'last_json': lj,
               'stdout_sha256': osha, 'verify_frozen': verify}
    pk = None
    if jd.is_dir():
        with JobLock(lay, jd):
            pk = build_package(ctx, jv, sub, info['pre_newest'], command, completed)
    uploads = package_uploads(ctx, pk)
    folder = ctx.records_folder()
    for u in uploads:
        b.upload(u, folder)
    diverged = bool(pk and pk.get('reset_diverged'))
    tok = None
    if completed is not None:
        tok = token_text(sub, info['tag'], info['case'], completed, saved_xlsx8(jd), diverged)
    b.bind = tok or 'none'
    b.result = {'command': 'wrap', 'runner_subcommand': sub, 'runner_exit': code, 'runner_last_line': scrub(last), 'runner_json': lj,
                'job_dir': str(jd), 'package': pk['name'] if pk else None, 'png_parts': (pk or {}).get('parts') or [],
                'deliverable_xlsx_sha256': (pk or {}).get('meta', {}).get('deliverable') if False else
                ((read_json_file(jd / 'qa' / 'SAVED_QA.json') or {}).get('deliverable_xlsx') or {}).get('sha256') if (jd / 'qa' / 'SAVED_QA.json').is_file() else None,
                'record_sha256': jv.record_sha(), 'bind': b.bind, 'reset_diverged': diverged, 'binding': (pk or {}).get('binding')}
    V, D = ctx.V, jd
    b.code = code if code in (0, 3) else EXIT_OK
    if verify is not None and verify['exit'] != 0:     # the FZ (uploaded above) is the evidence; never evicted (r2 R2-01)
        raise Halt('STOP', 'FROZEN_FOLDER_CHANGED', 'verify-frozen found the frozen folder changed: upload, then hand back case C',
                   block=b)
    if pk is not None and pk.get('reset_diverged') and not pk.get('existing') and sub != 'freeze':
        b.next('RUN ' + freeze_line(ctx, D))
        raise Halt('STOP', 'RESET_DIVERGED', 'the re-run differs from what was seen: the run has failed; freeze it', block=b)
    if last.startswith('REFUSED:'):
        rc = last.split(':', 1)[1].strip()
        made_pkg = pk is not None and not pk.get('existing')
        if rc == 'JOB_BUSY':
            b.next(f'RUN {V} wait')
            b.then(f'RUN {V} status')
            b.code = EXIT_REFUSED
        elif sub == 'prepare' and ctx.mode == 'everyday' and not jd.exists() and pk is None:
            # r2 M5: refused before the job folder existed: the run has not started; record it, so job-start may give it
            # corrected inputs (the same run id) instead of leaving the run in flight for good
            ri = run_inputs(ctx, info['tag'])
            if ri is not None:
                ctx.index.event('prepare_refused', ri['name'], tag=info['tag'], code=rc)
            b.uploads = []
            b.next(f'FIX code=RUNNER_{rc}')
            b.then(f'RUN {V} job-start --case {info["case"]}')
            b.code = EXIT_REFUSED
        elif rc == 'REVIEW_INCOMPLETE':
            b.next('CONTINUE_CONVERSATION role=V')
            b.then(f'RUN {V} ai-archive --job-dir {D} --role V --revision')
            b.code = EXIT_OK
        elif rc == 'QUALIFICATION_READER_A_RESTART_UNUSED':
            plan = plan_status(ctx, ignore_pending=True, in_worker=True)
            b.tail = plan.block.tail
            b.fetch += plan.block.fetch
            b.code = EXIT_REFUSED
        elif made_pkg:
            b.next(f'FIX code={rc}')
            b.then(f'RUN {V} status')
            b.code = EXIT_OK
        elif rc in ('STAGE_ALREADY_COMPLETED', 'STAGE_OUTPUT_EXISTS', 'JOB_FROZEN'):
            raise Halt('STOP', 'RUNNER_' + rc, 'tell the owner (case C)', block=b)
        else:
            b.uploads = []
            b.tail = ['REFUSED: RUNNER_' + rc]
            b.code = EXIT_REFUSED
        return b
    if not last.startswith('NEXT:'):
        raise Halt('STOP', 'RUNNER_OUTPUT', 'the runner printed no NEXT line: hand back case C', block=b)
    step = last[len('NEXT:'):].strip().split(' ')[0]
    if step in STEP_ROLE:
        b.next(f'RUN {V} start-note --job-dir {D} --role {STEP_ROLE[step]}')
    elif step == 'FREEZE':
        b.next('RUN ' + freeze_line(ctx, D))
    elif step == 'DELIVER_CHECK':
        plan = Plan()
        job_plan(ctx, plan, JobView(ctx, D))
        b.tail = plan.block.tail
    elif step == 'DELIVER':
        dsha = ((read_json_file(D / 'qa' / 'SAVED_QA.json') or {}).get('deliverable_xlsx') or {}).get('sha256')
        b.next(f'DELIVER folder={D}/export/writer sha256={dsha}')
        b.then(f"RUN {V} delivery-note --job-dir {D} --prepared --copy '{{COPY_FILE}}' --log '{{LOG_FILE}}' --profile-folder '{{PROFILE_FOLDER}}'")
    elif step == 'DONE':
        b.next(f'RUN {V} evict --job-dir {D}')
    elif step == 'STOP_FREEZE_INCOMPLETE':
        b.next('RUN ' + freeze_line(ctx, D))
    elif step == 'STOP_RECORD_CONFLICT':
        raise Halt('STOP', 'RUNNER_STOP_RECORD_CONFLICT', 'hand back case C', block=b)
    elif step == 'STOP_TECHNICAL_INTERRUPTION':
        b.next('RUN ' + freeze_line(ctx, D))
        b.then(f'RUN {V} status')
    else:
        b.next('RUN ' + freeze_line(ctx, D))
        if ctx.mode == 'qualification':
            b.then('HANDBACK case=C' if step == 'OWNER_DECISION' or step.startswith('STOP_') and step not in ('STOP_VISUAL_REVIEW_FAILED',) else f'RUN {V} status')
        else:
            b.then(f'TELL_OWNER code=RUNNER_{step}')
    return b


def cmd_package(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        require_no_incident(ctx)                    # r2 R2-03: spec 4, every non-exempt command
        clean_placed(ctx)
        jd = Path(os.path.abspath(a.job_dir))
        jv = JobView(ctx, jd)
        if not jv.exists or jv.tag is None:
            refuse('PACKAGE_NO_JOB', 'no job folder at that path')
        b = Block()
        V = ctx.V
        last = jv.last()
        with JobLock(ctx.lay, jd):
            if last and last['stage'] == 'freeze' and last['result'] == 'FROZEN' and not jv.frozen:
                b.result = {'command': 'package', 'package': None}
                b.next('RUN ' + freeze_line(ctx, jd))
                return b
            sub = last['stage'] if last else None
            completed = last if last and last['stage'] in WRAP_SUBS else None
            verify = None
            if jv.frozen:                           # r2 R2-01: every frozen folder, nonattempts included
                _, _, vlast, vj, _ = run_runner(ctx, ['verify-frozen', '--job-dir', str(jd)], ctx.lay.outbox / f'package_{utc14()}.log')
                verify = {'exit': 0 if vlast == 'NEXT: DONE' else 3, 'result': (vj or {}).get('result'), 'json': vj, 'last_line': vlast}
            prev = newest_package(ctx, jv.tag, jv.case)
            pre = prev['name'] if prev else (newest_package(ctx, chain=chain_of(jv.tag)) or {}).get('name')
            pk = build_package(ctx, jv, sub or 'package', pre, {'runner_subcommand': None, 'reason': 'package', 'verify_frozen': verify}
                               if verify else None, completed, applied_by='package')
        for u in package_uploads(ctx, pk):
            b.upload(u, ctx.records_folder())
        tok = token_text(sub, jv.tag, jv.case, completed, saved_xlsx8(jd), bool(pk and pk['reset_diverged'])) if completed else 'none'
        b.bind = tok
        b.result = {'command': 'package', 'package': pk['name'] if pk else None, 'bind': tok, 'reset_diverged': bool(pk and pk['reset_diverged'])}
        if verify is not None and verify['exit'] != 0:
            raise Halt('STOP', 'FROZEN_FOLDER_CHANGED', 'verify-frozen found the frozen folder changed: upload, then hand back case C',
                       block=b)
        if (jd / CJ.MARKER_NAME).exists():
            b.next('RUN ' + freeze_line(ctx, jd))
            if ctx.mode == 'everyday':
                b.then('TELL_OWNER code=STAGE_INTERRUPTED')
        else:
            b.next(f'RUN {V} status')
        return b


# ------------------------------------------------------------------ notes: start, link, ai-archive (spec 5.7-5.9)
START_RULES = ('a new conversation; the full text of the prompt file is its only message; no Drive connector; no uploads; '
               'no other job')


def prompt_pin(jv, role):
    if role == 'S':
        s = jv.done('prepare')
        o = (s[-1].get('outputs') or {}).get('scope_reader_prompt') if s else None
        return jv.dir / 'scope' / 'SCOPE_READER_PROMPT.md', (o or {}).get('sha256')
    if role == 'G':
        g = CJ.generation_stage(jv)
        o = ((g or {}).get('outputs') or {}).get('generator_prompt')
        return jv.dir / 'run' / 'GENERATOR_PROMPT.md', (o or {}).get('sha256')
    f = jv.done('finish')
    o = (f[-1].get('outputs') or {}).get('visual_review_prompt') if f else None
    return jv.dir / 'qa' / 'VISUAL_REVIEW_PROMPT.md', (o or {}).get('sha256')


def run_path(jv, role):
    if role == 'S':
        return jv.dir / 'scope' / 'reader'
    if role == 'G':
        return jv.output_dir('G').parent
    return jv.dir / 'qa'


def job_arg(ctx, path):
    jv = JobView(ctx, path)
    if jv.tag is None or not jv.exists or jv.rec is None:
        refuse('NO_JOB', 'no job folder of this layout at that path')
    return jv


def next_attempt(ctx, jv, role):
    """5.7 attempt rule: (attempt, supersedes, replaces) or a refusal. supersedes is set only for the AI_NO_CONVERSATION
    re-START (the same attempt); the replacement reviewer names the START it replaces in replaces (r2 M3)."""
    T = newest_start(ctx, jv.tag, role, jv.case)
    k = jv.g_attempt() - 1 if role == 'G' else 0
    if T is None:
        return 1 + k, None, None
    att = T.get('attempt') or 1
    if role == 'G' and att < 1 + k:
        return 1 + k, None, None
    archs = ai_archives(ctx, jv.tag, role, att, jv.case)
    inc = resolving(ctx, T['name'])
    cls = inc['content'].get('classification') if inc else None
    if not archs:
        if inc is None:
            refuse('START_ALREADY_RECORDED', 'a START of this attempt exists: run status')
        if cls == 'AI_NO_CONVERSATION':
            return att, T['name'], None
        if cls == 'AI_NOTHING_WRITTEN':
            if role == 'V':
                if att >= 2:
                    refuse('REVIEWER_REPLACEMENT_USED', 'the one replacement reviewer was used')
                return 2, None, T['name']
            refuse('START_NOT_ALLOWED', 'the scope reader or generator is restarted by interrupt (or a new folder), not by a new START')
        refuse('START_NOT_ALLOWED', 'the incident on this START does not allow another conversation')
    if role == 'V' and cls == 'AI_NOTHING_WRITTEN':
        if att >= 2:
            refuse('REVIEWER_REPLACEMENT_USED', 'the one replacement reviewer was used')
        return 2, None, T['name']
    refuse('START_ALREADY_RECORDED', 'this attempt has its conversation: run status')


def cmd_start_note(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        clean_placed(ctx)
        consume_confirms(ctx)
        require_session_ready(ctx)
        require_no_incident(ctx)
        require_recheck(ctx)
        jv = job_arg(ctx, a.job_dir)
        role = a.role
        lay = ctx.lay
        if jv.frozen or jv.last_next() != ROLE_STEP[role]:
            refuse('START_STATE', 'the job does not wait for this conversation: run status')
        if run_failed_by_reset(ctx, jv.tag, jv.case):
            refuse('WRAP_RUN_FAILED_RESET_DIVERGED', 'this run has failed (reset diverged): only freeze may run; run status')
        rsha = jv.record_sha()
        pk = [e for e in packages(ctx, jv.tag, jv.case) if (e.get('meta') or {}).get('record_sha256') == rsha]
        if not pk:
            refuse('START_PACKAGE_MISSING', 'no save point of the current record: run status')
        pk = pk[-1]
        if ctx.cfg['confirm_package_before_start'] and not ctx.index.confirmed(pk['name']) and pk.get('origin') == 'made':
            b = Block()
            for part in ((pk.get('meta') or {}).get('png_parts') or []):
                if (ctx.index.get(part['name']) or {}).get('origin') == 'made' and not ctx.index.confirmed(part['name']) \
                        and count_events(ctx, 'narrow_miss', pk['name']) > count_events(ctx, 'reupload', pk['name']):
                    reupload(ctx, b, part['name'])
            confirm_or_upload(ctx, b, pk['name'])
            need(b, 'START_PACKAGE_NOT_CONFIRMED')
        require_unconfirmed(ctx, jv)
        if lay.inbox.exists() and any(lay.inbox.iterdir()):
            refuse('START_INBOX_PRESENT', 'BASE/inbox must be empty during a conversation')
        others = [d for d in lay.job_folders() if d != jv.dir]
        if others:
            refuse('START_OTHER_RUN_PRESENT', 'only this job folder may exist during a conversation (evict frozen runs first)')
        pref = f'{jv.case}_{jv.tag}_'
        if lay.transcripts.exists() and any(not p.name.startswith(pref) for p in lay.transcripts.iterdir()):
            refuse('START_TRANSCRIPTS_PRESENT', 'BASE/transcripts holds files of another run')
        out = jv.output_dir(role)
        if out.is_dir() and any(e[1] == 'file' for e in tree_list(out)):
            refuse('START_OUTPUT_NOT_EMPTY', 'the output folder is not empty: do not delete anything; run status')
        prompt, pin = prompt_pin(jv, role)
        if not prompt.is_file() or sha_file(prompt) != pin:
            refuse('START_PROMPT_CHANGED', 'the prompt file differs from the record pin: hand back case C')
        att, sup, repl = next_attempt(ctx, jv, role)
        nonce = secrets.token_hex(16)
        now = now_dt()
        name = f'START_{jv.tag}_{role}{att}_{utc14(now)}_{h8(nonce)}_{jv.case}.json'
        led_seq = len(read_ledger(ctx)[1]) if ctx.mode == 'qualification' else None
        inc = None
        if sup or repl:
            r = resolving(ctx, sup or repl)
            inc = r['name'] if r else None
        note = {'schema': 'cps.vm-start.v1', 'helper': helper_info(), 'boot_id': current_boot_id(), 'created_utc': iso(now),
                'case_id': jv.case, 'reader': jv.reader, 'tag': jv.tag, 'job_dir': str(jv.dir), 'role': role, 'attempt': att,
                'nonce': nonce, 'prompt_path': str(prompt), 'prompt_sha256': pin, 'run_path': str(run_path(jv, role)),
                'output_dir': str(out), 'record_sha256': rsha, 'ledger_seq': led_seq,
                'fingerprint_sha256': ctx.state['fingerprint_sha256'], 'supersedes': sup, 'replaces': repl, 'incident': inc,
                'rules': START_RULES,
                'package_confirmed': {'name': pk['name'], 'drive_id': pk.get('drive_id'), 'md5': pk.get('md5'), 'listing': 'narrow'},
                'output_dir_empty': True}
        p = lay.outbox / name
        write_new(p, note_bytes(note))
        b = Block()
        for u in made(ctx, p, 'start', ctx.records_folder(), tag=jv.tag, case_id=jv.case, role=role, attempt=att, job_dir=str(jv.dir),
                      record_sha256=rsha, content=note):
            b.upload(u, ctx.records_folder())
        b.result = {'command': 'start-note', 'start_note': name, 'role': role, 'attempt': att, 'supersedes': sup, 'replaces': repl}
        b.next(f'OPEN_CONVERSATION role={role} prompt={prompt}')
        if ctx.cfg['link_notes']:                   # T-10: the RUN line's own output carries the steps after it
            b.then(f"RUN {ctx.V} link-note --job-dir {jv.dir} --role {role} --conversation '{{CONVERSATION_ID}}'")
        else:
            b.then(f'WAIT_FOR_CONVERSATION role={role}')
            b.then(f'RUN {ctx.V} ai-archive --job-dir {jv.dir} --role {role}')
        return b


def current_start(ctx, jv, role):
    T = newest_start(ctx, jv.tag, role, jv.case)
    if T is None or (role == 'G' and (T.get('attempt') or 1) < jv.g_attempt()):
        return None
    return T


def cmd_link_note(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        require_no_incident(ctx)                    # r2 R2-03: spec 4, every non-exempt command
        jv = job_arg(ctx, a.job_dir)
        role = a.role
        T = current_start(ctx, jv, role)
        if T is None or ai_all(ctx, jv.tag, role, T['attempt'], jv.case):
            refuse('LINK_NO_OPEN_START', 'no open START of this role')
        if link_of(ctx, T['name']) is not None:
            refuse('LINK_ALREADY_RECORDED', 'the LINK of this START exists')
        c = a.conversation
        if not isinstance(c, str) or not c.strip() or c.strip().startswith('<') or '\n' in c:
            refuse('LINK_CONVERSATION', 'the conversation id or link, as the platform shows it')
        if a.started_utc is not None and (parse_utc(a.started_utc) is None or not a.started_utc.endswith('Z')):
            refuse('LINK_STARTED_UTC', 'ISO 8601 with Z')
        sc = T.get('content') or {}
        name = f'LINK_{jv.tag}_{role}{T["attempt"]}_{h8(sc.get("nonce", "0" * 8))}_{jv.case}.json'
        note = {'schema': 'cps.vm-link.v1', 'helper': helper_info(), 'boot_id': current_boot_id(), 'created_utc': utc(),
                'start_note': T['name'], 'nonce': sc.get('nonce'), 'conversation': c, 'started_utc': a.started_utc}
        p = ctx.lay.outbox / name
        if p.exists():
            refuse('LINK_ALREADY_RECORDED')
        write_new(p, note_bytes(note))
        b = Block()
        for u in made(ctx, p, 'link', ctx.records_folder(), tag=jv.tag, case_id=jv.case, role=role, attempt=T['attempt'], content=note):
            b.upload(u, ctx.records_folder())
        b.result = {'command': 'link-note', 'link_note': name}
        b.next(f'WAIT_FOR_CONVERSATION role={role}')
        b.then(f'RUN {ctx.V} ai-archive --job-dir {jv.dir} --role {role}')
        return b


def unexpected_entries(tree, role):
    resp = RESPONSE_FILE[role]
    out = []
    for rel, k, *_ in tree:
        if rel == resp:
            continue
        if role == 'G' and (rel == 'scratch' or rel.startswith('scratch/')):
            continue
        out.append(rel)
    return out


def cmd_ai_archive(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        require_no_incident(ctx)                    # r2 R2-03: spec 4, every non-exempt command
        jv = job_arg(ctx, a.job_dir)
        role = a.role
        lay = ctx.lay
        T = current_start(ctx, jv, role)
        if T is None:
            refuse('AI_WITHOUT_START', 'no START of the current attempt')
        att = T['attempt']
        with JobLock(lay, jv.dir):
            out = jv.output_dir(role)
            tree = tree_list(out, 'AI_OUTPUT_UNSUPPORTED_ENTRY') if out.is_dir() else []
            tsha = tree_sha(tree)
            archs = ai_archives(ctx, jv.tag, role, att, jv.case)
            if not archs and ai_lost(ctx, jv.tag, role, att, jv.case):
                b = Block()
                b.next(f'RUN {ctx.V} status')
                refuse('AI_ARCHIVE_REJECTED', 'this attempt\'s archive reached Drive damaged: no new archive; run status', block=b)
            b = Block()
            rev, prev, after = 1, None, None
            if archs and not a.revision:
                last = archs[-1]
                if last.get('tree_sha256') != tsha:
                    stop('AI_OUTPUT_CHANGED_AFTER_ARCHIVE', 'something wrote after the conversation ended: hand back case C')
                p = last.get('payload')
                if p and Path(p).is_file() and not ctx.index.confirmed(last['name']):
                    for u in upload_paths(ctx, p, ctx.records_folder()):
                        b.upload(u, ctx.records_folder())
                b.result = {'command': 'ai-archive', 'archive': last['name'], 'existing': True}
                if consumer_done(jv, role, last):       # T-10: the consuming stage ran already: status's next step
                    plan = plan_status(ctx)
                    b.tail, b.code = plan.block.tail, plan.code
                    b.fetch += plan.block.fetch
                    return b
                ai_next(ctx, b, jv, role, T, last.get('meta') or {})
                return b
            if a.revision:
                if role != 'V' or not archs:
                    refuse('REVISION_NOT_ALLOWED', 'a revision follows a REVIEW_INCOMPLETE refusal of the archived review')
                last = archs[-1]
                lm = last.get('meta') or {}
                st_ = jv.stages()
                e = st_[-1] if st_ else None
                ra = ((e or {}).get('inputs') or {}).get('review_attempt') if e else None
                if not (e and e['stage'] == 'visual-record' and e['result'] == 'REFUSED' and 'REVIEW_INCOMPLETE' in (e.get('codes') or [])
                        and ra and e['seq'] > (lm.get('record_seq_at_archive') or 0)):
                    refuse('REVISION_NOT_ALLOWED', 'the newest record entry is not a REVIEW_INCOMPLETE refusal after the archive')
                if ra.get('sha256') != lm.get('response_sha256'):
                    refuse('REVISION_NOT_ALLOWED', 'the refused review is not the archived one')
                if tsha == last.get('tree_sha256'):
                    refuse('REVISION_NOT_ALLOWED', 'the reviewer has not completed anything yet')
                if len(archs) > ctx.cfg['max_review_revisions']:
                    stop('REVISION_LIMIT', 'the reviewer revision limit is reached: hand back case C')
                rev = len(archs) + 1
                prev = {'name': last['name'], 'tree_sha256': last.get('tree_sha256')}
                after = {'record_seq': e['seq'], 'code': 'REVIEW_INCOMPLETE', 'review_attempt_sha256': ra.get('sha256')}
            resp = out / RESPONSE_FILE[role]
            present = os.path.lexists(resp)
            man = {'schema': 'cps.vm-ai-archive.v1', 'case_id': jv.case, 'reader': jv.reader, 'tag': jv.tag, 'job_dir': str(jv.dir),
                   'role': role, 'attempt': att, 'output_dir': str(out), 'start_note': T['name'], 'tree': tree, 'tree_sha256': tsha,
                   'output_mode': stat.S_IMODE(os.lstat(out).st_mode) if out.is_dir() else 0o755,
                   'response_file': RESPONSE_FILE[role], 'response_present': present,
                   'response_sha256': sha_file(resp) if present and resp.is_file() else None, 'created_utc': utc(),
                   'boot_id': current_boot_id(), 'fingerprint_sha256': ctx.state['fingerprint_sha256'], 'revision': rev,
                   'previous_revision': prev, 'after_refusal': after, 'unexpected': unexpected_entries(tree, role),
                   'record_seq_at_archive': len(jv.stages())}
            name = f'AI_{jv.tag}_{role}{att}' + (f'r{rev}' if rev > 1 else '') + f'_{h8(tsha)}_{jv.case}.tgz'
            dest = lay.outbox / name
            if dest.exists():
                dest.unlink()
            mm = [('MANIFEST.json', 'file', 0o444, 0, note_bytes(man)), ('output', 'dir', man['output_mode'], 0, None)]
            for rel, k, mode, size, sha in tree:
                mm.append(('output/' + rel, k, mode, 0, None if k == 'dir' else str(out / rel)))
            write_tgz(dest, mm)
            ai = Archive(dest, ('MANIFEST.json', 'output'))
            ai_expected_check(ai)
            ai.close()
            for u in made(ctx, dest, 'ai', ctx.records_folder(), tag=jv.tag, case_id=jv.case, role=role, attempt=att, job_dir=str(jv.dir),
                          tree_sha256=tsha, meta=ai_meta(man)):
                b.upload(u, ctx.records_folder())
            b.result = {'command': 'ai-archive', 'archive': name, 'response_present': present, 'revision': rev,
                        'unexpected': len(man['unexpected'])}
            ai_next(ctx, b, jv, role, T, ai_meta(man))
            return b


def consumer_done(jv, role, arch):
    """T-10: the stage that consumes this archive completed after it was made."""
    stage = {'S': 'scope-finish', 'G': 'finish', 'V': 'visual-record'}[role]
    at = ((arch or {}).get('meta') or {}).get('record_seq_at_archive') or 0
    return any(s['stage'] == stage and s['seq'] > at for s in jv.completed())


def ai_next(ctx, b, jv, role, T, meta):
    plan = Plan()
    if meta.get('response_present'):
        line = consuming_line(ctx, jv, role, T)
        if line is None:
            gen_record_lines(ctx, plan, jv, T['attempt'])
        else:
            plan.run(line)
    else:
        nothing_written_lines(ctx, plan, jv, role, T['attempt'], T, meta)
    b.tail = plan.block.tail


# ------------------------------------------------------------------ incident (spec 5.11)
def transcript_given(path):
    """A transcript file that exists and is not empty (r2 R2-01: an empty export counts as no transcript)."""
    return bool(path) and Path(path).is_file() and os.path.getsize(path) > 0


def cmd_incident(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        clean_placed(ctx)
        return incident_body(ctx, a)


def incident_body(ctx, a):
    lay, st = ctx.lay, ctx.state
    cls = a.classification
    if cls not in CLASSES:
        refuse('INCIDENT_CLASSIFICATION', 'one of ' + ', '.join(CLASSES))
    after = bool(st.get('pending_incident'))
    if cls in ('NONE_IN_FLIGHT', 'NON_AI_STAGE_LOST', 'AI_ARCHIVED', 'AI_NO_CONVERSATION') and not after:
        refuse('INCIDENT_NOT_AFTER_RESTORE', 'this classification exists only after a restore')
    ai_cls = cls in ('AI_NO_CONVERSATION', 'AI_NOTHING_WRITTEN', 'AI_WRITTEN_LOST')
    s = situation(ctx) if after else None
    jv, role, T, arch, lost_names = None, None, None, None, []
    if ai_cls or cls == 'AI_ARCHIVED':
        if not a.job_dir or not a.role:
            refuse('INCIDENT_NEEDS_JOB', '--job-dir and --role')
        jv = job_arg(ctx, a.job_dir)
        role = a.role
        if jv.role() != role:
            refuse('INCIDENT_NO_OPEN_START', 'the job does not wait for this role')
        T = current_start(ctx, jv, role)
        if T is None:
            refuse('INCIDENT_NO_OPEN_START', 'no START of the current attempt')
        archs = ai_archives(ctx, jv.tag, role, T['attempt'], jv.case)
        arch = archs[-1] if archs else None
        lost = lost_names = ai_lost(ctx, jv.tag, role, T['attempt'], jv.case)
        if lost and cls in ('AI_NOTHING_WRITTEN', 'AI_NO_CONVERSATION', 'AI_ARCHIVED'):
            refuse('INCIDENT_ARCHIVE_REJECTED', 'this attempt\'s AI archive reached Drive damaged: the output counts as written '
                   '(AI_WRITTEN_LOST); run status', detail={'archive': lost})
    if ai_cls and not a.conversation_ended:
        refuse('INCIDENT_CONVERSATION_NOT_ENDED', 'stop the conversation if it still runs, confirm it has ended, then pass --conversation-ended')
    seen, not_seen = [], bool(a.not_seen)
    for t in a.seen or []:
        seen += [x for x in t.split(',') if x]
    if seen and not_seen:
        refuse('INCIDENT_NEEDS_SEEN', 'either --seen or --not-seen')
    pending_job = None
    sub = None
    if cls == 'NONE_IN_FLIGHT':
        if s['kind'] != 'none':
            refuse('INCIDENT_CLASSIFICATION', 'status prints another classification: run status')
    elif cls == 'NON_AI_STAGE_LOST':
        if s['kind'] != 'runner':
            refuse('INCIDENT_CLASSIFICATION', 'status prints another classification: run status')
        w = s['wrap']
        sub = w['sub']
        if w.get('pending'):
            pending_job = {'tag': w['tag'], 'case': w['case'], 'subcommand': sub}
        else:
            jv = JobView(ctx, w['job_dir'])
        if a.job_dir and (jv is None or os.path.abspath(a.job_dir) != str(jv.dir)):
            refuse('INCIDENT_NEEDS_JOB', 'the job folder status names')
    elif cls == 'AI_ARCHIVED':
        if s['kind'] != 'archived':
            refuse('INCIDENT_CLASSIFICATION', 'status prints another classification: run status')
        sub = CONSUMING_SUB[role]
    elif cls == 'AI_NO_CONVERSATION':
        if s['kind'] != 'open_start':
            refuse('INCIDENT_CLASSIFICATION', 'status prints another classification: run status')
        why = no_conversation_allowed(ctx, jv, role, T)
        if why == 'AI_NO_CONVERSATION_REPEATED':
            stop('AI_NO_CONVERSATION_REPEATED', 'a second reset before the conversation existed: hand back case C')
        if why:
            refuse(why, 'AI_NO_CONVERSATION does not apply')
    elif cls == 'AI_NOTHING_WRITTEN':
        if not ctx.cfg['transcript_export']:
            refuse('INCIDENT_CLASSIFICATION', 'transcripts cannot be exported: doubt counts as written (AI_WRITTEN_LOST)')
        if arch is not None:
            m = arch.get('meta') or {}
            if m.get('response_present'):
                refuse('INCIDENT_RESPONSE_PRESENT', 'the response was archived: run status')
            if m.get('unexpected'):
                refuse('INCIDENT_CLASSIFICATION', 'the archive holds other files: something was written (AI_WRITTEN_LOST)')
        if os.path.lexists(jv.output_dir(role) / RESPONSE_FILE[role]):
            refuse('INCIDENT_RESPONSE_PRESENT', 'the response file exists: run ai-archive and go on')
        if arch is None:
            out = jv.output_dir(role)
            if out.is_dir() and unexpected_entries([e for e in tree_list(out) if e[1] == 'file'], role):
                refuse('INCIDENT_CLASSIFICATION', 'the output folder holds files: AI_WRITTEN_LOST')
        if not a.conversation or not a.conversation.strip() or a.conversation.strip().startswith('<'):
            refuse('INCIDENT_NEEDS_JOB', '--conversation (the conversation id) is required')
        if not transcript_given(a.transcript):     # r2 R2-01: absent or empty; the refusal prints the line that applies
            b0 = Block()
            b0.next(f'RUN {ctx.V} incident --classification AI_WRITTEN_LOST --job-dir {jv.dir} --role {role} '
                    f'--conversation {q(a.conversation)} --conversation-ended')
            refuse('INCIDENT_TRANSCRIPT_REQUIRED', 'without a transcript (or with an empty one) doubt counts as written: AI_WRITTEN_LOST',
                   block=b0)
        if ctx.mode == 'qualification' and role in ('S', 'G'):
            sub = 'interrupt' if CJ.restart_used_here(jv) is None else 'freeze'
        elif role in ('S', 'G'):
            sub = 'freeze'
    elif cls == 'AI_WRITTEN_LOST':
        sub = 'freeze'
    if cls in ('NON_AI_STAGE_LOST', 'AI_ARCHIVED') and not seen and not not_seen:
        refuse('INCIDENT_NEEDS_SEEN', 'give every BIND= token you saw since the last upload (--seen), or --not-seen')
    tag = jv.tag if jv else (pending_job or {}).get('tag')
    case = jv.case if jv else (pending_job or {}).get('case')
    parsed = []
    for t in seen:
        p = parse_token(t)
        if p is None or (not p['none'] and (p['tag'] != tag or p['case'] != case)):
            refuse('INCIDENT_SEEN_INVALID', 'copy the BIND= token again exactly')
        parsed.append(p)
    real = [p for p in parsed if not p['none']]
    forces = any(p['D'] for p in real) or len({tuple(p['fields']) for p in real}) > 1
    earlier = []
    if T is not None:
        earlier = [i for i in incidents(ctx) if i['content'].get('start_note') == T['name']]
        for i in earlier:
            ec = i['content'].get('classification')
            if ec != cls and cls != 'AI_WRITTEN_LOST':
                refuse('INCIDENT_CONTRADICTS_EARLIER', 'an earlier incident on this START has another classification')
    elif pending_job:
        earlier = [i for i in incidents(ctx) if (i['content'].get('pending_job') or {}).get('tag') == tag
                   and (i['content'].get('pending_job') or {}).get('case') == case]
    newest = newest_package(ctx, tag, case) if tag else None
    if newest is None:
        cn = newest_package(ctx, chain='Q') if ctx.mode == 'qualification' else (newest_package(ctx, chain=tag) if tag else None)
        newest = cn
    # transcript copy
    b = Block()
    tinfo = None
    if transcript_given(a.transcript):
        tb = Path(a.transcript).read_bytes()
        ext = ''.join(c for c in Path(a.transcript).suffix[1:] if c.isascii() and c.isalnum())[:10] or 'txt'
        att = T['attempt'] if T else 1
        tn = f'TRANSCRIPT_{tag}_{role or "G"}{att}_{h8(sha_bytes(tb))}_{case}.{ext}'
        tp = lay.outbox / tn
        if not tp.exists():
            write_new(tp, tb)
            for u in made(ctx, tp, 'transcript', ctx.records_folder(), tag=tag, case_id=case, role=role, attempt=att):
                b.upload(u, ctx.records_folder())
        else:
            for u in upload_paths(ctx, tp, ctx.records_folder()):
                b.upload(u, ctx.records_folder())
        tinfo = {'name': tn, 'sha256': sha_bytes(tb)}
    elif ai_cls:
        tinfo = {'not_available': 'no transcript file given'}
    if jv is not None and T is not None:
        step = f'AI_CONVERSATION_{role}{T["attempt"]}'
    elif pending_job:
        step = 'NON_AI_PENDING_' + pending_job['subcommand']
    elif newest is not None:
        lc = ((newest.get('meta') or {}).get('last_completed') or {}).get('stage')
        step = 'NON_AI_AFTER_' + str(lc)
    else:
        step = 'NONE'
    sess = [e for e in ctx.index.of('session') if (e.get('content') or {}).get('boot_id') != current_boot_id()]
    now = now_dt()
    boot8 = h8(sha_bytes(current_boot_id().encode()))
    ra = f'{role}{T["attempt"]}' if T else 'NA'
    name = f'INCIDENT_{utc14(now)}_{boot8}_{cls}_{tag or "NOJOB"}_{ra}_{case or "none"}.json'
    note = {'schema': 'cps.vm-incident.v1', 'helper': helper_info(), 'boot_id': current_boot_id(), 'created_utc': iso(now),
            'boot_id_new': current_boot_id(), 'boot_id_old': (sess[-1].get('content') or {}).get('boot_id') if sess else None,
            'session_note': st.get('session_note'), 'restore_session': st.get('restore_session') if after else None,
            'newest_package': newest['name'] if newest else None, 'step_in_flight': step,
            'classification': cls, 'job_dir': str(jv.dir) if jv else None, 'case_id': case, 'tag': tag, 'role': role,
            'attempt': T['attempt'] if T else None, 'start_note': T['name'] if T else None, 'conversation': a.conversation,
            'transcript': tinfo, 'note': a.note, 'after_restore': after, 'pending_job': pending_job, 'seen': seen, 'not_seen': not_seen,
            'next_subcommand': sub, 'forces_reset_diverged': bool(forces), 'conversation_ended': bool(a.conversation_ended),
            'ai_archive': ({'name': arch['name'], 'response_present': (arch.get('meta') or {}).get('response_present'),
                            'unexpected': (arch.get('meta') or {}).get('unexpected')} if arch else
                           ({'name': lost_names[-1], 'rejected': True} if lost_names else None)),
            'rejected_copies': st.get('rejected_copies') or [], 'earlier_incidents': [i['name'] for i in earlier]}
    p = lay.outbox / name
    write_new(p, note_bytes(note))
    for u in made(ctx, p, 'incident', ctx.records_folder(), tag=tag, case_id=case, role=role, attempt=T['attempt'] if T else None,
                  content=note):
        b.upload(u, ctx.records_folder())
    st['pending_incident'] = False
    st.pop('restore_session', None)
    if after:
        st['restore_recheck'] = True
        st['recheck_incident'] = name
    st['rejected_copies'] = []
    ctx.save_state()
    b.result = {'command': 'incident', 'incident': name, 'classification': cls, 'next_subcommand': sub, 'forces_reset_diverged': forces}
    if after:
        b.listing(ctx.records_folder(), lay.inbox / 'DRIVE_LISTING.json')
        b.next(f'RUN {ctx.V} recheck')
    else:
        plan = plan_status(ctx)
        b.tail = plan.block.tail
        b.fetch += plan.block.fetch
    if forces:
        b.tail = []
        if after:
            b.listing(ctx.records_folder(), lay.inbox / 'DRIVE_LISTING.json')
            b.next(f'RUN {ctx.V} recheck')
            b.then('RUN ' + freeze_line(ctx, jv.dir) if jv else f'RUN {ctx.V} status')
        else:
            b.next('RUN ' + freeze_line(ctx, jv.dir) if jv else f'RUN {ctx.V} status')
        raise Halt('STOP', 'RESET_DIVERGED', 'the seen tokens disagree: the run has failed; freeze it', block=b)
    return b


# ------------------------------------------------------------------ recheck (spec 6.6)
def cmd_recheck(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        st, lay = ctx.state, ctx.lay
        if not st.get('restore_recheck'):
            refuse('RECHECK_NOT_NEEDED', 'no restore awaits its second listing')
        p = lay.inbox / 'DRIVE_LISTING.json'
        b = Block()
        if not p.is_file():
            b.listing(ctx.records_folder(), p)
            need(b, 'RECHECK_LISTING_MISSING')
        which = 'everyday' if ctx.mode == 'everyday' else 'qualification'
        s, sb, _ = sentinel_for(ctx, which)
        lst = read_listing(ctx, p, ctx.records_folder(), None, s, sb, b)
        if not lst.has(st.get('recheck_incident') or ''):
            p.unlink()
            b.listing(ctx.records_folder(), p)
            need(b, 'RECHECK_LISTING_STALE')
        known = set(st.get('listing', {}).get('records') or [])
        restored_pk = [e for e in ctx.index.of('package') if e.get('origin') in ('made', 'restored')]
        top = {}
        for e in restored_pk:
            pn = parse_name(e['name'])
            top[chain_of(pn['tag'])] = max(top.get(chain_of(pn['tag']), (-1, 0)), (pn['seq'], pn['pkind'] == 'FZ'))
        for pn in lst.names('package'):
            ch = chain_of(pn['tag'])
            if pn['name'] not in known and ch in top and (pn['seq'], pn['pkind'] == 'FZ') > top[ch] \
                    and (ctx.index.get(pn['name']) or {}).get('origin') != 'made':
                stop('RESTORE_STALE_LISTING', 'an upload believed lost landed late: nothing is re-run; hand back case C',
                     detail={'package': pn['name']})
        for p_ in lst.names():                      # r2 N2: 6.1 step 5 on the second listing (a late START, LINK or AI)
            if p_['kind'] in ('start', 'link', 'ai') and p_['name'] not in known \
                    and (ctx.index.get(p_['name']) or {}).get('origin') not in ('made', 'restored'):
                stop('RESTORE_STALE_LISTING', 'a START, LINK or AI archive landed after the restore\'s listing: nothing is re-run; '
                     'hand back case C', detail={'name': p_['name']})
        rej = {e['name'] for e in ctx.index.events if e['event'] == 'rejected'}
        for n in rej:
            ids = {f['id'] for f in lst.by.get(n, [])}
            known_ids = set(ctx.index.copies.get(n, {}))
            if ids - known_ids:
                stop('RESTORE_STALE_LISTING', 'a new copy of a rejected file appeared: hand back case C', detail={'name': n})
        ingest_listing(ctx, lst)
        st['restore_recheck'] = False
        st['listing']['records'] = sorted(set(known) | set(lst.by))
        ctx.save_state()
        p.unlink()
        plan = plan_status(ctx)
        b = plan.block
        b.result = {'command': 'recheck', 'ok': True}
        b.code = plan.code
        return b


# ------------------------------------------------------------------ genesis (spec 5.4)
def cmd_genesis(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        lay, st = ctx.lay, ctx.state
        if ctx.mode != 'qualification':
            refuse('GENESIS_MODE', 'genesis is for a qualification release')
        if not a.first_ledger:
            refuse('GENESIS_FLAG', 'genesis --first-ledger, only as status prints it')
        if ctx.cfg['expected_genesis'] is not None:
            refuse('GENESIS_ALREADY_EXPECTED', 'a GENESIS is recorded: run session_start.sh for a restore')
        require_no_incident(ctx)                    # r2 R2-03: spec 4, every non-exempt command
        require_session_ready(ctx)
        if os.path.lexists(lay.ledger_dir):
            refuse('GENESIS_LEDGER_EXISTS', 'BASE/ledger exists')
        names = [parse_name(n) for n in (st.get('listing') or {}).get('records') or []]
        if any(p and p['kind'] in ('genesis', 'package', 'start', 'incident') for p in names):
            refuse('GENESIS_EXISTS_IN_DRIVE', 'the records folder holds qualification history: run session_start.sh again (restore)')
        adm = ((ctx.rel.get('qualification') or {}).get('admissions') or [None])[0]
        try:
            araw = Path(adm['path']).read_bytes()
            ad = sjson(araw)
            fu = parse_utc(ad.get('frozen_utc'))
        except (OSError, ValueError, TypeError, KeyError):
            ad, fu, araw = None, None, b''
        if adm is None or adm.get('sha256') != sha_bytes(araw) or fu is None or fu >= now_dt():
            refuse('GENESIS_ADMISSION', 'the released admission must be listed with its sha256 and frozen before now')
        jraw = Path(ctx.rel['qualification']['jobs_file']).read_bytes()
        for old in lay.base.glob('.cps_vm_stage_ledger_*'):
            remove_tree(old)
        sd = lay.base / f'.cps_vm_stage_ledger_{os.getpid()}'
        os.mkdir(sd, 0o755)
        entry = {'type': 'genesis', 'ledger_id': secrets.token_hex(16), 'helper': helper_info(), 'release_sha256': sha_bytes(ctx.rel_raw),
                 'admission_sha256': sha_bytes(araw), 'jobs_sha256': sha_bytes(jraw), 'boot_id': current_boot_id(),
                 'fingerprint_sha256': st['fingerprint_sha256'], 'base': str(lay.base)}
        assert set(entry) == set(GENESIS_KEYS)
        with CJ.Ledger(sd / 'LEDGER.jsonl', create=True) as led:
            e = led.append(entry)
        with CJ.Ledger(sd / 'LEDGER.jsonl', create=False, readonly=True) as led:
            raw = led.raw
        genesis_hook()
        os.rename(sd, lay.ledger_dir)
        line = raw.split(b'\n', 1)[0]
        now = now_dt()
        name = f'GENESIS_{h8(e["ledger_id"])}_{utc14(now)}.json'
        note = {'schema': 'cps.vm-genesis.v1', 'helper': helper_info(), 'boot_id': current_boot_id(), 'created_utc': iso(now),
                'ledger_path': str(lay.ledger), 'identity_line': line.decode('utf-8'), 'identity_line_sha256': sha_bytes(line + b'\n'),
                'ledger_id': e['ledger_id'], 'release_sha256': entry['release_sha256'], 'admission_sha256': entry['admission_sha256'],
                'jobs_sha256': entry['jobs_sha256'], 'fingerprint_sha256': st['fingerprint_sha256']}
        p = lay.outbox / name
        write_new(p, note_bytes(note))
        b = Block()
        for u in made(ctx, p, 'genesis', ctx.records_folder(), content=note):
            b.upload(u, ctx.records_folder())
        b.result = {'command': 'genesis', 'genesis': name, 'ledger_id8': h8(e['ledger_id'])}
        b.next(f'TELL_MAINTAINER genesis={name}')
        b.then(f'RUN {ctx.V} status')
        return b


def genesis_hook():
    """A test seam (E25): the in-process test replaces it to kill genesis between staging and rename."""
    return None


# ------------------------------------------------------------------ self-test and FINGERPRINT_PASS (spec 5.3)
def cmd_selftest(a):
    ctx = Ctx()
    lock = HelperLock(ctx.lay)
    lock.__enter__()
    try:
        if ctx.state.get('fingerprint_pass'):
            refuse('SELFTEST_NOT_NEEDED', 'this session already has a FINGERPRINT_PASS')
        if (ctx.lay.outbox / 'DETACHED.json').is_file():
            b = Block()
            b.next(f'RUN {ctx.V} wait')
            refuse('HELPER_BUSY', 'a detached command is in progress', block=b)
        fp, _ = fingerprint(ctx.lay)
        if fp != ctx.state.get('fingerprint_sha256'):
            stop('FINGERPRINT_CHANGED', 'the toolchain changed since session start: run session_start.sh again')
        d = ctx.lay.outbox / f'selftest_{utc14()}'
        d.mkdir()
        commit = (subprocess.run(['git', '-C', str(HELPER_REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout or '').strip()
        run = {'fingerprint_before_sha256': fp, 'commit': commit, 'session_note': ctx.state.get('session_note'), 'started_utc': utc(),
               'work_dir': str(d / 'work'), 'exit': None, 'ended_utc': None, 'pid': None}
        write_atomic(d / 'RUN.json', note_bytes(run))
        return spawn(ctx, 'selftest', {'dir': str(d)}, lock)
    finally:
        lock.release()


def selftest_work(ctx, info):
    d = Path(info['dir'])
    run = read_json_file(d / 'RUN.json')
    run['pid'] = os.getpid()
    write_atomic(d / 'RUN.json', note_bytes(run))
    suite = HELPER_REPO / 'research' / 'export' / 'tests' / 'run_export_tests.py'
    with open(d / 'selftest.log', 'ab') as log:
        p = subprocess.run([sys.executable, '-I', '-B', str(suite), '--writer-dir', str(HELPER_REPO / 'deploy' / 'writer_route' / 'writer'),
                            '--work', str(d / 'work')], stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy())
    run['exit'], run['ended_utc'] = p.returncode, utc()
    write_atomic(d / 'RUN.json', note_bytes(run))
    b = Block()
    b.result = {'command': 'selftest', 'exit': p.returncode, 'dir': str(d)}
    b.next(f'RUN {ctx.V} fingerprint-pass')
    return b


def cmd_fingerprint_pass(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        lay, st = ctx.lay, ctx.state
        runs = sorted(lay.outbox.glob('selftest_*/RUN.json'))
        run = read_json_file(runs[-1]) if runs else None
        if not run or run.get('session_note') != st.get('session_note'):
            refuse('SELFTEST_NOT_RUN', 'run the self-test first: RUN $V selftest')
        if run.get('exit') is None:
            b = Block()
            b.next(f'RUN {ctx.V} wait')
            raise Halt('BUSY', 'SELFTEST_STILL_RUNNING', block=b)
        fp, full = fingerprint(lay)
        if fp != run.get('fingerprint_before_sha256') or fp != st.get('fingerprint_sha256'):
            stop('FINGERPRINT_CHANGED', 'something changed the toolchain during the self-test: hand back case C')
        d = runs[-1].parent
        res_p = d / 'work' / 'EXPORT_TEST_RESULTS.json'
        res_raw = res_p.read_bytes() if res_p.is_file() else b''
        s = ((read_json_file(res_p) or {}).get('summary') or {}) if res_raw else {}
        n = ctx.cfg['selftest_expected_tests']
        exp = HELPER_REPO / 'research' / 'export'
        node_sha = ((full['components'].get('node') or {}).get('sha256'))
        ok = (run.get('exit') == 0 and s.get('failed_count') == 0 and s.get('tests') == n and s.get('passed_count') == n
              and s.get('visual_skipped') is False and s.get('writer_portable_sha256') == sha_file(exp / 'writer_portable.py')
              and s.get('saved_qa_sha256') == sha_file(exp / 'saved_qa.py') and s.get('visual_qa_sha256') == sha_file(exp / 'visual_qa.py')
              and (s.get('checker_node') or {}).get('sha256') == node_sha)
        if not ok:
            b = Block()
            if res_raw:
                b.upload(res_p, reports_folder(ctx))
            lg = d / 'selftest.log'                 # r2 R2-08: the suite's own log, when it holds anything
            if lg.is_file() and lg.stat().st_size > 0:
                b.upload(lg, reports_folder(ctx))
            stop('SELFTEST_FAILED', 'the export self-test did not pass on this VM: upload the results and hand back case C', block=b)
        now = now_dt()
        fp8 = h8(fp)
        sn = lay.outbox / f'SELFTEST_{fp8}_{utc14(now)}.json'
        write_new(sn, res_raw)
        pn = lay.outbox / f'FINGERPRINT_PASS_{fp8}_{utc14(now)}.json'
        note = {'schema': 'cps.vm-fingerprint-pass.v1', 'helper': helper_info(), 'boot_id': current_boot_id(), 'created_utc': iso(now),
                'fingerprint_sha256': fp, 'fingerprint': full, 'commit': run.get('commit'),
                'selftest': {'results_name': sn.name, 'sha256': sha_bytes(res_raw), 'tests': s.get('tests'), 'passed_count': s.get('passed_count'),
                             'failed_count': s.get('failed_count'), 'suite': s.get('suite')},
                'fingerprint_before_sha256': run.get('fingerprint_before_sha256'), 'fingerprint_after_sha256': fp,
                'run': {k: run.get(k) for k in ('work_dir', 'started_utc', 'ended_utc', 'exit', 'pid', 'session_note')},
                'results_tools': {k: s.get(k) for k in ('writer_portable_sha256', 'saved_qa_sha256', 'visual_qa_sha256')} |
                {'checker_node_sha256': (s.get('checker_node') or {}).get('sha256')}}
        write_new(pn, note_bytes(note))
        b = Block()
        for p_, k in ((sn, 'selftest'), (pn, 'fpass')):
            for u in made(ctx, p_, k, ctx.setup_folder(), content=note if k == 'fpass' else None):
                b.upload(u, ctx.setup_folder())
        st['fingerprint_pass'] = pn.name
        ctx.save_state()
        if (d / 'work').exists():
            remove_tree(d / 'work')
        plan = plan_status(ctx)
        b.tail, b.code = plan.block.tail, plan.code
        b.fetch += plan.block.fetch
        b.result = {'command': 'fingerprint-pass', 'fingerprint_pass': pn.name}
        return b


def cmd_fingerprint(a):
    lay = Layout()
    fp, full = fingerprint(lay)
    b = Block()
    b.result = {'command': 'fingerprint', 'fingerprint_sha256': fp, 'fp8': h8(fp)}
    if a.json:
        b.result['fingerprint'] = full
    b.next('DONE')
    return b


# ------------------------------------------------------------------ evict (spec 5.13)
def fz_manifest(ctx, fz):
    p = fz.get('payload')
    if p and Path(p).is_file():
        a = Archive(p, ('MANIFEST.json', 'ledger', 'job'))
        m = a.manifest
        a.close()
        return m
    return None


def verify_refs(ctx, fz):
    """[(name, sha256, md5, bytes, local_source)] that must be verified for an FZ (core or its slices, and its parts)."""
    refs = []
    sl = [e for e in ctx.index.of('split') if (e.get('meta') or {}).get('of') == fz['name']]
    if sl:
        refs += [(e['name'], e['sha256'], e['md5'], e['bytes'], e.get('payload')) for e in sl]
    elif fz.get('origin') == 'made':
        refs.append((fz['name'], fz['sha256'], fz['md5'], fz['bytes'], fz.get('payload')))
    for part in (fz.get('meta') or {}).get('png_parts') or []:
        e = ctx.index.get(part['name']) or {}
        refs.append((part['name'], part['sha256'], part['md5'], part['bytes'], e.get('payload') if e.get('origin') == 'made' else None))
    return refs


REUPLOAD_MAX = 3


def count_events(ctx, ev, name):
    return sum(1 for e in ctx.index.events if e['event'] == ev and e['name'] == name)


def local_upload(ctx, name):
    """The UPLOAD paths of a file this VM made and still holds (slices first when oversized), else None."""
    e = ctx.index.get(name)
    p = (e or {}).get('payload')
    if e and e.get('origin') == 'made' and p and Path(p).is_file():
        return upload_paths(ctx, p, e.get('folder') or ctx.records_folder()), e.get('folder') or ctx.records_folder()
    return None


def reupload(ctx, b, name):
    """T-06: print the UPLOAD of the local copy again, at most REUPLOAD_MAX times per name, then STOP."""
    lu = local_upload(ctx, name)
    if lu is None:
        return False
    if count_events(ctx, 'reupload', name) >= REUPLOAD_MAX:
        stop('UPLOAD_NOT_CONFIRMED', 'the upload never showed on Drive with the right bytes: hand back case C', detail={'name': name})
    paths, folder = lu
    for u in paths:
        b.upload(u, folder)
    ctx.index.event('reupload', name)
    return True


def slices_of(ctx, name):
    return [e for e in ctx.index.of('split') if (e.get('meta') or {}).get('of') == name]


def confirm_or_upload(ctx, b, name):
    """T-06/T-22: the narrow listing that confirms name; when one was consumed already and showed no matching copy, the
    UPLOAD of the local copy is printed again first (bounded). An oversized original is confirmed through its slices."""
    sl = slices_of(ctx, name)
    if sl:
        for e in sl:
            if not ctx.index.confirmed(e['name']):
                confirm_or_upload(ctx, b, e['name'])
        return
    if count_events(ctx, 'narrow_miss', name) > count_events(ctx, 'reupload', name):
        reupload(ctx, b, name)
    confirm_line(ctx, b, name)


def verify_one(ctx, b, name, sha, md5, size, src, mode):
    """T-06 (5.13): verify one uploaded file of an FZ. Returns 'verified', 'pending' (lines printed) or 'rebuild'.
    Download mode tries the listed copies in ascending createdTime, each id once; md5 mode trusts a listed md5. When
    every copy failed: the local copy is uploaded again (bounded), else a PNG part is rebuilt, else STOP."""
    lay = ctx.lay
    copies = sorted((ctx.index.copies.get(name) or {}).values(), key=lambda c: (c.get('drive_created') or '', c.get('drive_id') or ''))
    is_part = (parse_name(name) or {}).get('kind') == 'png'
    if mode == 'md5':
        hits = [e for e in ctx.index.events if e['event'] == 'confirmed' and e['name'] == name and e.get('md5') == md5
                and (e.get('bytes') in (None, size))]
        listed = [c for c in copies if c.get('md5') == md5]
        if hits or listed:
            ctx.index.event('verified', name, drive_id=(hits or listed)[0].get('drive_id'), method='md5')
            return 'verified'
        seen_listing = bool(copies) or count_events(ctx, 'narrow_miss', name) > 0
    else:
        vp = lay.inbox / 'verify' / name
        if vp.is_file():
            req = [e for e in ctx.index.events if e['event'] == 'verify_requested' and e['name'] == name]
            did = req[-1].get('drive_id') if req else None
            if sha_file(vp) == sha:
                ctx.index.event('verified', name, drive_id=did, method='download')
                vp.unlink()
                return 'verified'
            vp.unlink()
            ctx.index.event('verify_failed', name, drive_id=did)
        tried = {e.get('drive_id') for e in ctx.index.events if e['event'] == 'verify_failed' and e['name'] == name}
        cands = [c for c in copies if c.get('drive_id') not in tried and (not c.get('md5') or c.get('md5') == md5)
                 and (c.get('bytes') is None or c.get('bytes') == size)]
        if cands:
            did = cands[0]['drive_id']
            vp.parent.mkdir(parents=True, exist_ok=True)
            b.download(did, name, vp)
            ctx.index.event('verify_requested', name, drive_id=did)
            return 'pending'
        seen_listing = bool(copies) or count_events(ctx, 'narrow_miss', name) > 0
    if not seen_listing:
        confirm_line(ctx, b, name)
        return 'pending'
    if src and Path(src).is_file() and reupload(ctx, b, name):
        confirm_line(ctx, b, name)
        return 'pending'
    if is_part:
        return 'rebuild'
    stop('VERIFY_PART_MISMATCH', 'no copy on Drive has the right bytes and no local source exists: hand back case C', detail={'name': name})


def drive_id_of(ctx, name):
    for e in reversed(ctx.index.events):
        if e['name'] == name and e['event'] in ('confirmed', 'verified') and e.get('drive_id'):
            return e['drive_id']
    c = ctx.index.copies.get(name) or {}
    return next(iter(c), None)


def cmd_evict(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        require_no_incident(ctx)                    # r2 R2-03: spec 4, every non-exempt command
        clean_placed(ctx)
        consume_confirms(ctx)
        lay = ctx.lay
        b = Block()
        targets = []
        if a.all:
            targets = [d for d in lay.job_folders() if (d / 'FROZEN.json').is_file()] + [Path(e['job_dir']) for e in fz_pending(ctx)]
        elif a.job_dir:
            targets = [Path(os.path.abspath(a.job_dir))]
        else:
            refuse('EVICT_ARGUMENTS', '--job-dir D or --all')
        done, needs = [], False
        for root in (lay.qual, lay.jobs):           # r2 R2-04: leftovers of a killed evict
            for g in (root.glob('*/.cps_vm_evict_*') if root.is_dir() else []):
                remove_tree(g)
        for jd in targets:
            pend = [e for e in fz_pending(ctx) if e['job_dir'] == str(jd)]
            if jd.is_dir():
                jv = JobView(ctx, jd)
                if not jv.frozen or not jv.freeze_done():
                    refuse('EVICT_NOT_FROZEN', 'freeze the run first')
                f8 = h8(sha_file(jd / 'FROZEN.json'))
                fzs = [e for e in packages(ctx, jv.tag, jv.case) if parse_name(e['name'])['pkind'] == 'FZ' and parse_name(e['name'])['frozen8'] == f8]
                if not fzs:
                    refuse('EVICT_NO_FZ', 'no FZ package of this frozen folder: run status')
                fz = fzs[-1]
                man = fz_manifest(ctx, fz)
                if man is not None:
                    with JobLock(lay, jd):
                        have = {('job/' + e[0], e[1], e[2], e[3], e[4]) for e in tree_list(jd)}
                        have.add(('job', 'dir', stat.S_IMODE(os.lstat(jd).st_mode), None, None))
                        want = {(m['path'], m['type'], m['mode'], m.get('bytes'), m.get('sha256')) for m in man['members']}
                        want |= {(f['path'], 'file', f['mode'], f['bytes'], f['sha256']) for f in (man.get('png') or {}).get('files') or []}
                        if have != want:
                            stop('EVICT_FOLDER_CHANGED', 'the frozen folder differs from its FZ: hand back case C')
            elif pend:
                fz = ctx.index.get(pend[0]['fz'])
                jv = None
            else:
                refuse('EVICT_NOT_FROZEN', 'no frozen folder there')
            vfe = (fz.get('meta') or {}).get('verify_frozen_exit')
            if vfe is None and fz.get('payload'):
                vfe = (((fz_manifest(ctx, fz) or {}).get('frozen') or {}).get('verify_frozen') or {}).get('exit')
            if vfe not in (None, 0):                 # r2 R2-01: a folder that failed verify-frozen is kept as found
                stop('EVICT_FROZEN_UNVERIFIED', 'the FZ records a failed verify-frozen: do not delete anything; hand back case C',
                     detail={'fz': fz['name']})
            mode = ctx.cfg['upload_verification']
            missing, rebuild = [], False
            for name, sha, md5, size, src in verify_refs(ctx, fz):
                if ctx.index.has_event('verified', name):
                    continue
                r = verify_one(ctx, b, name, sha, md5, size, src, mode)
                if r == 'rebuild':
                    rebuild = True
                elif r != 'verified':
                    missing.append(name)
            if rebuild and not missing:
                b.result = {'command': 'evict', 'evicted': done}
                b.next(f'RUN {ctx.V} rebuild-parts --fz {fz["name"]}')
                need(b, 'EVICT_PARTS_REBUILD')
            if rebuild:
                missing.append('rebuild')
            if missing:
                needs = True
                continue
            ctx.index.event('verified', fz['name'], drive_id=drive_id_of(ctx, fz['name']), method=mode) if not ctx.index.has_event('verified', fz['name']) else None
            if jv is not None:
                lay.frozen_json.mkdir(parents=True, exist_ok=True)
                write_atomic(lay.frozen_json / f'{jv.tag}_{jv.case}_FROZEN.json', (jd / 'FROZEN.json').read_bytes())
                if not (lay.frozen_json / f'{jv.tag}_{jv.case}_FLAGS.json').is_file():
                    write_atomic(lay.frozen_json / f'{jv.tag}_{jv.case}_FLAGS.json',
                                 note_bytes({'reset_diverged': bool((fz.get('meta') or {}).get('reset_diverged')), 'fz': fz['name']}))
                gone = jd.parent / f'.cps_vm_evict_{jd.name}_{os.getpid()}'
                os.rename(jd, gone)                 # r2 R2-04: atomic; a kill during the delete leaves only a dot folder
                ctx.index.event('evicted', fz['name'], job_dir=str(jd))
                remove_tree(gone)
                tag, case = jv.tag, jv.case
            else:
                tag, case = pend[0]['tag'], pend[0]['case']
                rest = [e for e in fz_pending(ctx) if e['job_dir'] != str(jd)]
                write_atomic(lay.outbox / 'FZ_PENDING.json', note_bytes(rest))
            kept = []
            for e in list(ctx.index.files.values()):
                if e.get('origin') != 'made' or e.get('tag') != tag or e.get('case_id') != case:
                    continue
                if e.get('kind') not in ('package', 'png', 'ai', 'transcript', 'split'):
                    continue
                p = e.get('payload')
                if not p or not Path(p).is_file():
                    continue
                if ctx.index.confirmed(e['name']):
                    Path(p).unlink()
                    ctx.index.event('payload_deleted', e['name'])
                else:
                    kept.append(e['name'])
                    b.upload(p, e.get('folder') or ctx.records_folder())
            if lay.transcripts.is_dir():
                for t in lay.transcripts.glob(f'{case}_{tag}_*'):
                    t.unlink()
            done.append({'job_dir': str(jd), 'fz': fz['name'], 'kept_unconfirmed': kept})
        if needs:
            b.result = {'command': 'evict', 'evicted': done}
            need(b, 'EVICT_NOT_VERIFIED')
        if (lay.inbox / 'verify').exists():
            remove_tree(lay.inbox / 'verify')
        if (lay.inbox / 'DRIVE_LISTING.json').exists():
            (lay.inbox / 'DRIVE_LISTING.json').unlink()
        plan = plan_status(ctx)
        b.tail, b.code = plan.block.tail, plan.code
        b.fetch += plan.block.fetch
        b.result = {'command': 'evict', 'evicted': done, 'method': ctx.cfg['upload_verification']}
        return b


# ------------------------------------------------------------------ everyday: job-start, delivery-note (spec 5.18)
def cmd_job_start(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        clean_placed(ctx)
        lay = ctx.lay
        if ctx.mode != 'everyday':
            refuse('JOB_START_MODE', 'job-start is for a released-for-use kit')
        require_session_ready(ctx)
        require_no_incident(ctx)
        require_recheck(ctx)
        case = a.case
        pend = everyday_pending_prepare(ctx)
        reinput = None
        if pend is not None and not in_flight(ctx):
            cur = run_inputs(ctx, pend['tag'])
            if prepare_refusal(ctx, cur) is not None and pend.get('case_id') == case and not a.restart_of:
                if parse_name(cur['name'])['restart_of']:
                    stop('EVERYDAY_PREPARE_REFUSED', 'the runner refused the prepare of a restart run: hand back case C',
                         detail={'run_id': pend['tag']})
                if len([e for e in ctx.index.of('inputs') if e.get('tag') == pend['tag']]) > REINPUT_MAX:
                    stop('EVERYDAY_PREPARE_REFUSED', 'the runner refused this run\'s prepare again after new inputs: hand back case C',
                         detail={'run_id': pend['tag']})
                reinput = cur
        if in_flight(ctx) or (pend is not None and reinput is None):
            refuse('WRAP_RUN_IN_FLIGHT', 'one everyday job at a time: finish and evict the current one (status prints its next step)')
        d = lay.everyday_inputs / case
        restart_of, incn = a.restart_of, a.incident
        if restart_of:
            if not incn:
                refuse('JOB_START_RESTART_INCIDENT', '--restart-of needs --incident')
            inc = ctx.index.get(incn)
            c = (inc or {}).get('content') or {}
            if c.get('classification') != 'AI_NOTHING_WRITTEN' or c.get('tag') != restart_of or c.get('role') not in ('S', 'G'):
                refuse('JOB_START_RESTART_INCIDENT', 'an AI_NOTHING_WRITTEN incident of that run for the scope reader or generator')
            if fz_for(ctx, restart_of, case) is None:
                refuse('JOB_START_RESTART_NOT_FROZEN', 'freeze the original run first')
            orig = [x for x in [run_inputs(ctx, restart_of)] if x is not None]
            if any(parse_name(e['name'])['restart_of'] == restart_of for e in ctx.index.of('inputs')) or \
                    any(parse_name(e['name'])['restart_of'] for e in orig):
                refuse('JOB_START_RESTART_USED', 'that run was restarted once already (or is itself a restart)')
        for f in ('JOB.json', 'JOB_TITLE.json'):
            if not (d / f).is_file():
                refuse('JOB_START_INPUTS_MISSING', 'write JOB.json, JOB_TITLE.json and the source into BASE/everyday_inputs/<case>/')
        job = read_json_file(d / 'JOB.json') or {}
        if job.get('case_id') != case:
            refuse('JOB_START_CASE_MISMATCH', 'JOB.json case_id differs from --case')
        src = Path(str(job.get('source_path', '')))
        if not src.is_file() or src.parent != d:
            refuse('JOB_START_SOURCE_OUTSIDE', 'source_path must be the source file in that folder')
        if restart_of:                              # T-08: a restart runs on the original run's inputs, byte for byte
            om = inputs_manifest(orig[0]) if orig else None
            if om is None or om.get('case_id') != case or inputs_shas(d, om) != om.get('files') or \
                    set(om.get('files') or {}) != {'JOB.json', 'JOB_TITLE.json', src.name}:
                refuse('JOB_START_RESTART_INPUTS_DIFFER', 'the restart must use the inputs of the original run unchanged')
        now = now_dt()
        files = {n: sha_file(d / n) for n in ('JOB.json', 'JOB_TITLE.json', src.name)}
        if reinput is not None:                     # r2 M5: the same run id, new inputs (nothing of the run exists yet)
            if files == (inputs_manifest(reinput) or {}).get('files'):
                refuse('JOB_START_INPUTS_UNCHANGED', 'the runner refused these inputs: fix them first (RUN_JOB_COMMANDS.md names the code)')
            tag = reinput['tag']
        else:
            tag = 'E' + utc14(now)
        man = {'schema': 'cps.vm-inputs.v1', 'case_id': case, 'run_id': tag, 'restart_of': restart_of, 'incident': incn,
               'created_utc': iso(now), 'helper': helper_info(), 'files': files,
               'replaces': reinput['name'] if reinput is not None else None,
               'replaced_because': ('RUNNER_' + prepare_refusal(ctx, reinput)) if reinput is not None else None}
        tmp = lay.outbox / f'.tmp_{os.getpid()}_inputs.tgz'
        if tmp.exists():
            tmp.unlink()
        mm = [('MANIFEST.json', 'file', 0o444, 0, note_bytes(man)), ('inputs', 'dir', 0o755, 0, None)]
        for n in ('JOB.json', 'JOB_TITLE.json', src.name):
            mm.append(('inputs/' + n, 'file', 0o644, 0, str(d / n)))
        write_tgz(tmp, mm)
        name = f'INPUTS_{tag}_{restart_of or "E0"}_{h8(sha_file(tmp))}_{case}.tgz'
        if (lay.outbox / name).exists() or ctx.index.get(name) is not None:
            tmp.unlink()
            refuse('JOB_START_INPUTS_UNCHANGED', 'these inputs were given to this run already: fix them first')
        os.rename(tmp, lay.outbox / name)
        b = Block()
        for u in made(ctx, lay.outbox / name, 'inputs', ctx.records_folder(), tag=tag, case_id=case, content=man):
            b.upload(u, ctx.records_folder())
        b.result = {'command': 'job-start', 'run_id': tag, 'inputs': name, 'replaces': man['replaces']}
        b.next('RUN ' + everyday_prepare_line(ctx, tag, case))
        return b


def cmd_delivery_note(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        require_no_incident(ctx)                    # r2 R2-03: spec 4, every non-exempt command
        jv = job_arg(ctx, a.job_dir)
        if ctx.mode != 'everyday':
            refuse('DELIVERY_MODE', 'everyday only')
        dc = jv.done('deliver-check')
        if not dc or dc[-1]['result'] != 'DELIVERABLE':
            refuse('DELIVERY_NOT_CHECKED', 'deliver-check did not complete with DELIVERABLE')
        saved = ((read_json_file(jv.dir / 'qa' / 'SAVED_QA.json') or {}).get('deliverable_xlsx') or {}).get('sha256')
        now = now_dt()
        b = Block()
        prof = a.profile_folder
        if not prof or prof.startswith('<') or '\n' in prof:
            refuse('DELIVERY_PROFILE_FOLDER', 'the user profile folder on Drive')
        if a.prepared:
            log = read_json_file(a.log) if a.log else None
            if not isinstance(log, dict) or ((log.get('standard_file') or {}).get('sha256')) != saved:
                refuse('DELIVERY_LOG_MISMATCH', 'the personalization log must name the standard file by its sha256')
            if not a.copy or not Path(a.copy).is_file():
                refuse('DELIVERY_COPY_MISSING', 'the personal copy file')
            cb = Path(a.copy).read_bytes()
            name = f'DELIVERY_PREPARED_{jv.case}_{utc14(now)}.json'
            note = {'schema': 'cps.vm-delivery.v1', 'helper': helper_info(), 'boot_id': current_boot_id(), 'created_utc': iso(now),
                    'case_id': jv.case, 'run_id': jv.tag, 'job_dir': str(jv.dir), 'standard_sha256': saved,
                    'copy': {'name_sha256': sha_bytes(Path(a.copy).name.encode('utf-8')), 'sha256': sha_bytes(cb)},
                    'log_sha256': sha_file(a.log), 'prepared_note': None}
            p = ctx.lay.outbox / name
            write_new(p, note_bytes(note))
            # T-26: the copy's own file name may hold the job title, so the UPLOAD lines carry the tokens the Dot replaced
            # in the RUN line (README 0: tokens are replaced in UPLOAD paths too); the file keeps its name on Drive
            b.upload('{COPY_FILE}', prof + '/deliveries/')
            b.upload('{LOG_FILE}', prof + '/deliveries/')
            b.upload(p, prof + '/deliveries/')
            for u in made(ctx, p, 'delivery', ctx.records_folder(), tag=jv.tag, case_id=jv.case, content=note):
                b.upload(u, ctx.records_folder())
            b.result = {'command': 'delivery-note', 'note': name}
            b.next(f'SEND_COPY case={jv.case}')
            b.then(f"RUN {ctx.V} delivery-note --job-dir {jv.dir} --sent --prepared-note {name} --profile-folder '{{PROFILE_FOLDER}}'")
            return b
        if not a.sent or not a.prepared_note or ctx.index.get(a.prepared_note) is None:
            refuse('DELIVERY_ARGUMENTS', '--prepared ... or --sent --prepared-note <name>')
        name = f'DELIVERY_SENT_{jv.case}_{utc14(now)}.json'
        pn = ctx.index.get(a.prepared_note)
        note = dict((pn.get('content') or {}), created_utc=iso(now), prepared_note=a.prepared_note, boot_id=current_boot_id())
        p = ctx.lay.outbox / name
        write_new(p, note_bytes(note))
        b.upload(p, prof + '/deliveries/')
        for u in made(ctx, p, 'delivery', ctx.records_folder(), tag=jv.tag, case_id=jv.case, content=note):
            b.upload(u, ctx.records_folder())
        b.result = {'command': 'delivery-note', 'note': name}
        b.next('RUN ' + freeze_line(ctx, jv.dir))
        return b


# ------------------------------------------------------------------ final (spec 5.14)
FINAL_DOWNLOAD_MAX = 3
REINPUT_MAX = 3


def matching_copy(ctx, lst, name, md5=None, size=None):
    """r2 M4: the listed copy of name that holds the bytes this VM knows (a 'verified' or 'confirmed' event's Drive id,
    else the first copy whose listed md5/size equal the known ones), or None."""
    fs = lst.by.get(name, [])
    e = ctx.index.get(name) or {}
    known = e.get('origin') in ('made', 'restored')
    if md5 is None and known:
        md5 = e.get('md5')
    if size is None and known:
        size = e.get('bytes')
    for ev in reversed(ctx.index.events):
        if ev['name'] == name and ev['event'] in ('verified', 'confirmed') and ev.get('drive_id'):
            hit = next((f for f in fs if f['id'] == ev['drive_id'] and (md5 is None or f['md5'] in (None, md5))), None)
            if hit is not None:
                return hit
    if md5 is None and size is None:
        return None
    return next((f for f in fs if file_matches(f, md5, size)), None)


def ensure_fz_meta(ctx, fz, lst, block):
    """The FZ manifest summary (INDEX meta), downloading the FZ when this VM never held it. r2 M4: the copies are tried
    in ascending createdTime, each Drive id rejected once its listed bytes fail the name hash (INDEX final_rejected); a
    download whose bytes differ from the listing is asked again (at most FINAL_DOWNLOAD_MAX times per id)."""
    if (fz.get('meta') or {}).get('pkind') == 'FZ':
        return fz['meta']
    name = fz['name']
    p = ctx.lay.inbox / name
    req = [e for e in ctx.index.events if e['event'] == 'final_requested' and e['name'] == name]
    did = req[-1].get('drive_id') if req else None
    if p.is_file():
        lf = next((f for f in lst.by.get(name, []) if f['id'] == did), None)
        if h8(sha_file(p)) == parse_name(name)['pkg8']:
            a = Archive(p, ('MANIFEST.json', 'ledger', 'job'))
            try:
                check_pkg_manifest(a)
                a.check(pkg_expected(a.manifest))
                meta = pkg_meta(a.manifest)
            finally:
                a.close()
            e = ctx.index.add(name=name, kind='package', folder=fz.get('folder'), sha256=sha_file(p), md5=md5_file(p),
                              bytes=os.lstat(p).st_size, origin='restored', drive_id=did or fz.get('drive_id'),
                              drive_created=(lf or {}).get('created') or fz.get('drive_created'),
                              tag=fz.get('tag'), case_id=fz.get('case_id'), seq=fz.get('seq'), meta=meta)
            if did:
                ctx.index.event('verified', name, drive_id=did, method='download')
            p.unlink()
            return e['meta']
        local_md5, local_size = md5_file(p), os.lstat(p).st_size
        p.unlink()
        if lf is not None and file_matches(lf, local_md5, local_size):
            ctx.index.event('final_rejected', name, drive_id=did)       # the copy on Drive itself is damaged
        elif sum(1 for e in req if e.get('drive_id') == did) >= FINAL_DOWNLOAD_MAX:
            stop('FINAL_DOWNLOAD_FAILED', 'an FZ download kept arriving damaged: hand back case C', detail={'name': name, 'id': did})
        else:
            block.download(did, name, p)                                # damaged on the way here: the same id again
            ctx.index.event('final_requested', name, drive_id=did)
            return None
    rejected = {e.get('drive_id') for e in ctx.index.events if e['event'] == 'final_rejected' and e['name'] == name} | rejected_ids(ctx, name)
    cands = [f for f in lst.copies(name) if f['id'] not in rejected]
    if not cands:
        stop('FINAL_FROZEN_ARCHIVE_MISSING', 'no copy of an FZ on Drive passes its hash: hand back case C', detail={'name': name})
    block.download(cands[0]['id'], name, p)
    ctx.index.event('final_requested', name, drive_id=cands[0]['id'])
    return None


def run_flags(ctx, tag, case, meta, lst, led, job_dir):
    fl = []
    incs = [p for p in lst.names('incident') if p['tag'] == tag and p['case'] == case]
    if (meta or {}).get('reset_diverged') or any((i.get('content') or {}).get('forces_reset_diverged') for i in incidents(ctx)
                                                 if concerns(i, tag, case)):
        fl.append('RESET_DIVERGED')
    if any(p['cls'] == 'AI_WRITTEN_LOST' and p['role'] in ('S', 'G') for p in incs):
        fl.append('AI_OUTPUT_LOST')
    sts = [p for p in lst.names('start') if p['tag'] == tag and p['case'] == case]
    if any(p['role'] == 'V' and p['attempt'] == 2 for p in sts):
        fl.append('REVIEWER_REPLACED')
    if any(p['role'] == 'V' and p['attempt'] == 2 and p['cls'] in ('AI_NOTHING_WRITTEN', 'AI_WRITTEN_LOST') for p in incs) or \
            any(p['role'] == 'V' and p['cls'] == 'AI_WRITTEN_LOST' for p in incs):
        fl.append('REVIEWER_LOST')
    pe = led.of('prepare', job_dir=job_dir)
    if (pe and pe[0].get('restart_of')) or CJ.in_place_restart_used(led, job_dir):
        fl.append('RESTARTED')
    keys = {}
    for p in sts:
        keys[(p['role'], p['attempt'])] = keys.get((p['role'], p['attempt']), 0) + 1
    if any(v > 1 for v in keys.values()) or any(p['cls'] == 'AI_NO_CONVERSATION' for p in incs):
        fl.append('START_SUPERSEDED')
    if any(p['revision'] > 1 for p in lst.names('ai') if p['tag'] == tag and p['case'] == case):
        fl.append('REVIEW_REVISED')
    if (meta or {}).get('verify_frozen_exit') not in (None, 0):
        fl.append('FROZEN_UNVERIFIED')
    return fl


def cmd_final(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        require_no_incident(ctx)                    # r2 R2-03: spec 4, every non-exempt command
        lay = ctx.lay
        if ctx.mode != 'qualification':
            refuse('FINAL_MODE', 'final is for qualification')
        b = Block()
        p = lay.inbox / 'DRIVE_LISTING.json'
        if not p.is_file():
            b.listing(ctx.records_folder(), p)
            need(b, 'FINAL_LISTING_MISSING')
        s, sb, _ = sentinel_for(ctx, 'qualification')
        lst = read_listing(ctx, p, ctx.records_folder(), None, s, sb, b)
        ingest_listing(ctx, lst)
        if lst.names('all_frozen'):
            refuse('FINAL_ALREADY', 'ALL_FROZEN.json exists')
        if in_flight(ctx):
            refuse('FINAL_RUN_IN_FLIGHT', 'a job folder is not frozen')
        raw, entries = read_ledger(ctx)
        led = LedgerView(entries)
        for c in ctx.jobs_list():
            for R in 'AB':
                if led.of('nonattempt', case_id=c['case_id'], reader=R):
                    continue
                pr = led.of('prepare', case_id=c['case_id'], reader=R)
                if not pr or not led.of('freeze', job_dir=pr[-1]['job_dir']):
                    refuse('FINAL_INCOMPLETE', 'a case and reader has no frozen run or nonattempt yet')
        pk = [x for x in lst.names('package') if not dead(ctx, x['name'], lst)]
        if find_fork(pk):
            stop('FINAL_FORK', 'two different packages at one seq: hand back case C')
        lines = raw.split(b'\n')[:-1]
        for x in pk:
            pre = b''.join(l + b'\n' for l in lines[:x['seq']])
            if x['seq'] > len(lines) or h8(sha_bytes(pre)) != x['ledger8']:
                stop('FINAL_CHAIN', 'a package does not extend the local ledger: hand back case C', detail={'package': x['name']})
        gens = lst.names('genesis')
        ge = ctx.index.get(gens[0]['name']) if gens else None
        gc = (ge or {}).get('content') or {}
        if len(gens) != 1 or (gc.get('identity_line') or '').encode('utf-8') + b'\n' != lines[0] + b'\n':
            stop('FINAL_CHAIN', 'the GENESIS identity is not ledger line 1')
        top = sorted(pk, key=lambda x: (x['seq'], x['pkind'] == 'FZ'))[-1] if pk else None
        if top is None or top['seq'] != len(lines) or top['ledger8'] != h8(sha_bytes(raw)):
            stop('FINAL_CHAIN', 'the local ledger is not the newest package\'s: hand back case C')
        runs = []
        metas = {}
        for e in led.entries:
            if e.get('type') not in ('prepare', 'nonattempt'):
                continue
            tag, case = lay.tag_of(e['job_dir'])
            fz = led.of('freeze', job_dir=e['job_dir'])
            if not fz:
                stop('FINAL_FROZEN_ARCHIVE_MISSING', 'a run is not frozen')
            fzn = [x for x in pk if x['pkind'] == 'FZ' and x['tag'] == tag and x['case'] == case
                   and x['frozen8'] == h8(fz[-1]['frozen_sha256']) and x['record8'] == h8(fz[-1]['run_record_sha256'])]
            if len({x['pkg8'] for x in fzn}) != 1:
                stop('FINAL_FROZEN_ARCHIVE_MISSING', 'a frozen run has no FZ on Drive (or two)', detail={'job_dir': e['job_dir']})
            ent = ctx.index.get(fzn[0]['name'])
            meta = ensure_fz_meta(ctx, ent, lst, b)
            metas[e['job_dir']] = (fzn[0]['name'], meta, e, fz[-1], tag, case)
        if b.fetch:
            need(b, 'FINAL_NEEDS_FZ')
        accounted = set()
        for jd, (fzname, meta, e, fze, tag, case) in metas.items():
            for part in meta.get('png_parts') or []:
                if not lst.has(part['name']):
                    stop('FINAL_PARTS_MISSING', 'a PNG part of an FZ is not on Drive', detail={'name': part['name']})
            ent = ctx.index.get(fzname)
            fc = matching_copy(ctx, lst, fzname)                 # r2 M4: the copy whose bytes were checked, never copies[0]
            if fc is None:
                stop('FINAL_FROZEN_ARCHIVE_MISSING', 'no listed copy of an FZ holds the checked bytes: hand back case C',
                     detail={'name': fzname})
            part_copies = []
            for p_ in meta.get('png_parts') or []:
                pc = matching_copy(ctx, lst, p_['name'], p_.get('md5'), p_.get('bytes'))
                if pc is None:
                    stop('FINAL_PARTS_MISSING', 'no listed copy of a PNG part holds its bytes: hand back case C', detail={'name': p_['name']})
                part_copies.append(pc)
            mine = lambda k: sorted(x['name'] for x in lst.names(k) if x.get('tag') == tag and x.get('case') == case)
            for k in ('start', 'link', 'ai', 'incident', 'transcript', 'package'):
                accounted |= set(mine(k))
            runs.append({'case_id': case, 'reader': e.get('reader'), 'tag': tag, 'kind': 'run' if e['type'] == 'prepare' else 'nonattempt',
                         'job_dir': jd, 'restart_of': e.get('restart_of'), 'frozen_sha256': fze['frozen_sha256'],
                         'run_record_sha256': fze['run_record_sha256'], 'final_stage': fze.get('final_stage'), 'transcript': fze.get('transcript'),
                         'archive': {'name': fzname, 'id': fc['id'], 'md5': fc['md5'], 'sha256': ent.get('sha256') if ent.get('origin') != 'listed' else None,
                                     'sha8': parse_name(fzname)['pkg8'], 'created': fc['created']},
                         'png_parts': [{'name': p_['name'], 'id': pc['id'], 'md5': p_['md5'], 'sha256': p_['sha256']}
                                       for p_, pc in zip(meta.get('png_parts') or [], part_copies)],
                         'packages': mine('package'), 'start_notes': mine('start'), 'link_notes': mine('link'), 'ai_archives': mine('ai'),
                         'transcripts': mine('transcript'), 'incidents': mine('incident'),
                         'fingerprints': sorted({x['fp8'] for x in pk if x['tag'] == tag and x['case'] == case}),
                         'flags': run_flags(ctx, tag, case, meta, lst, led, jd)})
        for k in ('start', 'ai', 'incident'):
            for x in lst.names(k):
                if x['name'] not in accounted and not (k == 'incident' and x['tag'] is None):
                    stop('FINAL_UNACCOUNTED_NOTE', 'a note on Drive belongs to no run: hand back case C', detail={'name': x['name']})
        lf = lay.outbox / f'LEDGER_FINAL_L{len(lines):05d}_{h8(sha_bytes(raw))}.jsonl'
        if not lf.exists():
            write_new(lf, raw)
        gl = matching_copy(ctx, lst, gens[0]['name']) or lst.copies(gens[0]['name'])[0]
        af = {'schema': 'cps.all-frozen.v2', 'created_utc': utc(), 'helper': helper_info(), 'release_sha256': sha_bytes(ctx.rel_raw),
              'admission_sha256': sha_file(ctx.admission_path()), 'jobs_sha256': sha_file(ctx.rel['qualification']['jobs_file']),
              'ledger': {'path': str(lay.ledger), 'final_seq': len(lines), 'sha256': sha_bytes(raw), 'bytes': len(raw),
                         'identity_line_sha256': sha_bytes(lines[0] + b'\n'), 'ledger_id': gc.get('ledger_id'), 'final_upload': lf.name,
                         'genesis': {'name': gens[0]['name'], 'id': gl['id'], 'md5': gl['md5']}},
              'runs': runs,
              'sessions': [{'name': x['name'], 'boot8': x['boot8'], 'fp8': x['fp8'], 'created': lst.copies(x['name'])[0]['created']}
                           for x in lst.names('session')],
              'fingerprint_passes': [],
              'runs_failed_by_reset': sorted(r['job_dir'] for r in runs if {'RESET_DIVERGED', 'AI_OUTPUT_LOST', 'REVIEWER_LOST'} & set(r['flags'])),
              'checks': {'one_chain': True, 'no_fork': True, 'genesis_matches': True, 'every_freeze_archived': True, 'jobs_complete': True}}
        sl = ctx.state.get('listing', {}).get('setup') or []
        af['fingerprint_passes'] = [{'name': n, 'fp8': parse_name(n)['fp8'], 'created': None} for n in sl if (parse_name(n) or {}).get('kind') == 'fpass']
        ap = lay.outbox / 'ALL_FROZEN.json'
        if ap.exists():
            ap.unlink()
        write_new(ap, note_bytes(af))
        for u in made(ctx, lf, 'ledger_final', ctx.records_folder()):
            b.upload(u, ctx.records_folder())
        for u in made(ctx, ap, 'all_frozen', ctx.records_folder(), content=None):
            b.upload(u, ctx.records_folder())
        p.unlink()
        b.result = {'command': 'final', 'runs': len(runs), 'ledger_final': lf.name}
        b.next('HANDBACK case=B')
        return b


# ------------------------------------------------------------------ rebuild-parts (spec 6.7) and standalone restore (5.10)
def cmd_rebuild_parts(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        require_no_incident(ctx)                    # r2 R2-03: spec 4, every non-exempt command
        fz = ctx.index.get(a.fz)
        if fz is None:
            refuse('REBUILD_UNKNOWN_FZ', 'no such FZ in this session')
        p = ctx.lay.inbox / a.fz
        b = Block()
        if not p.is_file():
            b.download(fz.get('drive_id'), a.fz, p)
            need(b, 'NEED_FZ')
        if h8(sha_file(p)) != parse_name(a.fz)['pkg8']:
            p.unlink()
            stop('REBUILD_FZ_MISMATCH', 'the downloaded FZ fails its hash: download it again')
        ar = Archive(p, ('MANIFEST.json', 'ledger', 'job'))
        check_pkg_manifest(ar)
        ar.check(pkg_expected(ar.manifest))
        man = ar.manifest
        if not man.get('png'):
            stop('PARTS_UNRECOVERABLE', 'the FZ lists no PNG set')
        with tempfile.TemporaryDirectory(prefix='cps_vm_rb_') as td:
            res = rerender(ctx, ar, man, td)
        ar.close()
        if res is None:
            stop('PARTS_UNRECOVERABLE', 'the PNG set cannot be reproduced: hand back case C (the core keeps rendered.pdf)')
        with tempfile.TemporaryDirectory(prefix='cps_vm_rb2_') as td:
            files = {f['path']: f for f in man['png']['files']}
            mm = [(path, 'file', files[path]['mode'], 0, res[path]) for path in sorted(res)]
            tp = Path(td) / 'set.tar'
            with open(tp, 'xb') as f:
                write_tar_stream(f, mm)
            data = tp.read_bytes()
        if sha_bytes(data) != man['png']['set_sha256']:
            stop('PARTS_UNRECOVERABLE', 'the rebuilt PNG tar differs: hand back case C')
        off = 0
        for part in man['png']['parts']:
            chunk = data[off:off + part['bytes']]
            off += part['bytes']
            pp = ctx.lay.outbox / part['name']
            ensure_file(pp, chunk)
            ctx.index.add(name=part['name'], kind='png', folder=ctx.records_folder(), sha256=part['sha256'], md5=part['md5'],
                          bytes=part['bytes'], created_utc=utc(), origin='made', payload=str(pp), tag=man['tag'], case_id=man['case_id'])
            if not ctx.index.has_event('verified', part['name']):
                b.upload(pp, ctx.records_folder())
                ctx.index.event('reupload', part['name'])
                confirm_line(ctx, b, part['name'])      # T-06: the new copy's id comes from this narrow listing
        p.unlink()
        b.result = {'command': 'rebuild-parts', 'parts': [x['name'] for x in man['png']['parts']]}
        b.next(f'RUN {ctx.V} evict --job-dir {man["job_dir"]}')
        return b


def cmd_restore(a):
    ctx = Ctx()
    with HelperLock(ctx.lay):
        lay = ctx.lay
        p = lay.inbox / 'DRIVE_LISTING.json'
        b = Block()
        if not p.is_file():
            b.listing(ctx.records_folder(), p)
            need(b, 'SESSION_LISTING_MISSING')
        which = 'everyday' if ctx.mode == 'everyday' else 'qualification'
        s, sb, _ = sentinel_for(ctx, which)
        lst = read_listing(ctx, p, ctx.records_folder(), None, s, sb, b)
        if (lay.outbox / 'RESTORE_IN_PROGRESS.json').is_file():
            r = restore_resume(ctx)
        else:
            if lay.ledger_dir.exists() or lay.job_folders():
                refuse('RESTORE_LOCAL_STATE', 'this VM holds local state: run session_start.sh')
            r = restore(ctx, lst, lay.inbox, b, ctx.state)
        ingest_listing(ctx, lst)
        ctx.state['pending_incident'] = True
        ctx.save_state()
        restore_done(lay)
        plan = incident_plan(ctx)
        b.tail = plan.block.tail
        b.result = {'command': 'restore', 'restored': r}
        b.state = state_line(ctx)
        return b


# ------------------------------------------------------------------ assemble (spec 5.15, maintainer side)
def dir_file(d, name):
    """A file of a downloaded Drive folder: the file itself, or its SPLIT_ slices joined (in a temporary file)."""
    p = Path(d) / name
    if p.is_file():
        return p
    sl = {}
    for q_ in Path(d).glob('SPLIT_*__' + name):
        pn = parse_name(q_.name)
        if pn and pn['original'] == name:
            sl[pn['k']] = q_
    data = join_slices(sl, name) if sl else None
    if data is None:
        return None
    out = Path(tempfile.mkdtemp(prefix='cps_vm_join_')) / name
    out.write_bytes(data)
    return out


def cmd_assemble(a):
    d = Path(a.drive_dir)
    af = read_json_file(d / 'ALL_FROZEN.json')
    if not isinstance(af, dict) or af.get('schema') != 'cps.all-frozen.v2':
        stop('ASSEMBLE_INPUT', 'DIR/ALL_FROZEN.json')
    cj = load_runner()
    lfs = sorted(d.glob('LEDGER_FINAL_*.jsonl'))
    if len(lfs) != 1:
        stop('ASSEMBLE_INPUT', 'exactly one LEDGER_FINAL_*.jsonl')
    led_raw = lfs[0].read_bytes()
    if sha_bytes(led_raw) != af['ledger']['sha256']:
        stop('ASSEMBLE_INPUT', 'the final ledger differs from ALL_FROZEN.json')
    with tempfile.TemporaryDirectory(prefix='cps_vm_asm_') as td:
        (Path(td) / 'L.jsonl').write_bytes(led_raw)
        try:
            with cj.Ledger(Path(td) / 'L.jsonl', create=False, readonly=True):
                pass
        except cj.Refused:
            stop('ASSEMBLE_LEDGER_CHAIN', 'the final ledger chain does not verify')
    gen = read_json_file(d / af['ledger']['genesis']['name'])
    if not isinstance(gen, dict) or (gen.get('identity_line') or '').encode('utf-8') + b'\n' != led_raw.split(b'\n', 1)[0] + b'\n':
        stop('ASSEMBLE_GENESIS', 'ledger line 1 is not the GENESIS identity')
    plans = []
    for r in af['runs']:
        name = r['archive']['name']
        p = dir_file(d, name)
        if p is None or h8(sha_file(p)) != parse_name(name)['pkg8']:
            stop('ASSEMBLE_ARCHIVE', 'an FZ archive is missing or fails its hash', detail={'name': name})
        if r['archive'].get('md5') and md5_file(p) != r['archive']['md5']:
            stop('ASSEMBLE_ARCHIVE', 'md5 differs', detail={'name': name})
        if r['archive'].get('sha256') and sha_file(p) != r['archive']['sha256']:
            stop('ASSEMBLE_ARCHIVE', 'sha256 differs', detail={'name': name})
        ar = Archive(p, ('MANIFEST.json', 'ledger', 'job'))
        check_pkg_manifest(ar)
        man = ar.manifest
        ar.check(pkg_expected(man))
        lb = ar.read('ledger/LEDGER.jsonl')
        if not led_raw.startswith(lb):
            stop('ASSEMBLE_LEDGER_PREFIX', 'an FZ ledger is not a prefix of the final ledger', detail={'name': name})
        png = man.get('png')
        tar = None
        if png:
            chunks = []
            for part in png['parts']:
                pp = d / part['name']
                if not pp.is_file() or sha_file(pp) != part['sha256'] or md5_file(pp) != part['md5']:
                    stop('ASSEMBLE_PARTS', 'a PNG part is missing or differs', detail={'name': part['name']})
                chunks.append(pp.read_bytes())
            tar = b''.join(chunks)
            if sha_bytes(tar) != png['set_sha256']:
                stop('ASSEMBLE_PARTS', 'the joined PNG tar differs from the manifest')
        plans.append((r, ar, man, tar))
    # r2 R2-09: every target has the layout of its tag and case under one base, agrees with ALL_FROZEN, and is unique
    lpath = af['ledger'].get('path')
    if not isinstance(lpath, str) or not os.path.isabs(lpath) or Path(lpath).name != 'LEDGER.jsonl' \
            or Path(lpath).parent.name != 'ledger' or os.path.normpath(lpath) != lpath:
        stop('ASSEMBLE_TARGET_LAYOUT', 'the ledger path of ALL_FROZEN.json is not BASE/ledger/LEDGER.jsonl')
    base = Path(lpath).parent.parent
    seen_dirs = set()
    for r, _, m, _ in plans:
        jd = m.get('job_dir')
        tag, case = m.get('tag'), m.get('case_id')
        want = str(base / 'qual' / QUAL_ROOTS.get(tag, '?') / str(case)) if tag in QUAL_ROOTS else None
        if not isinstance(jd, str) or want is None or jd != want or r.get('job_dir') != jd or r.get('tag') != tag \
                or r.get('case_id') != case or (m.get('ledger') or {}).get('path') != lpath or jd in seen_dirs \
                or parse_name(r['archive']['name'])['tag'] != tag or parse_name(r['archive']['name'])['case'] != case:
            stop('ASSEMBLE_TARGET_LAYOUT', 'a frozen folder path does not match its tag, case, ALL_FROZEN.json and the ledger path, '
                 'or appears twice', detail={'archive': r['archive']['name']})
        seen_dirs.add(jd)
    targets = [Path(m['job_dir']) for _, _, m, _ in plans] + [Path(af['ledger']['path'])]
    if any(os.path.lexists(t) for t in targets):
        stop('ASSEMBLE_TARGET_EXISTS', 'a target path exists; assemble writes only new paths')
    report = {'schema': 'cps.vm-assemble-report.v1', 'created_utc': utc(), 'helper': helper_info(), 'runs': [], 'ledger': af['ledger']['path']}
    newest_mode = 0o644
    for r, ar, man, tar in plans:
        stg = Staging(man['job_dir'])
        stg.begin(next(m['mode'] for m in man['members'] if m['path'] == 'job'))
        for m in man['members']:
            if m['path'] == 'job':
                continue
            if not m['path'].startswith('job/'):
                stop('ARCHIVE_UNSAFE_MEMBER', 'a package member outside job/', detail={'path': m['path'][:200]})
            if m['type'] == 'dir':
                stg.add_dir(m['path'][4:], m['mode'])
            else:
                stg.add_file(m['path'][4:], ar.read(m['path']), m['mode'])
        if tar is not None:
            with tarfile.open(fileobj=io.BytesIO(tar), mode='r:') as tf:
                for path, b_ in png_tar_files(tf, man).items():
                    stg.add_file(path[4:], b_, {f['path']: f for f in man['png']['files']}[path]['mode'])
        stg.finish()
        newest_mode = (man.get('ledger') or {}).get('mode', newest_mode)
        ar.close()
        report['runs'].append({'job_dir': man['job_dir'], 'archive': r['archive']['name'], 'runner_sha256': man.get('runner_sha256')})
    lp = Path(af['ledger']['path'])
    lp.parent.mkdir(parents=True, exist_ok=True)
    with open(lp, 'xb') as f:
        f.write(led_raw)
    os.chmod(lp, newest_mode)
    ok = True
    if a.verify_frozen:
        rs = sha_file(runner_path())
        for run in report['runs']:
            if run['runner_sha256'] != rs:
                stop('ASSEMBLE_RUNNER_MISMATCH', 'the helper repository runner differs from the manifests')
            p = subprocess.run([sys.executable, '-I', '-B', str(runner_path()), 'verify-frozen', '--job-dir', run['job_dir']],
                               capture_output=True, text=True, timeout=3600)
            lines = [x for x in p.stdout.splitlines() if x.strip()]
            run['verify_frozen'] = {'exit': p.returncode, 'last_line': lines[-1] if lines else '', 'json': json.loads(lines[-2]) if len(lines) > 1 else None}
            ok = ok and run['verify_frozen']['last_line'] == 'NEXT: DONE'
    out = Path(a.report) if a.report else Path(d) / 'ASSEMBLE_REPORT.json'
    write_atomic(out, note_bytes(report))
    b = Block()
    b.result = {'command': 'assemble', 'runs': len(report['runs']), 'verify_frozen_all_done': ok if a.verify_frozen else None,
                'report': str(out)}
    if not ok:
        raise Halt('STOP', 'ASSEMBLE_VERIFY_FROZEN_FAILED', 'a folder did not verify', block=b)
    b.next('DONE')
    return b


# ------------------------------------------------------------------ audit (spec 5.16, maintainer side)
def cmd_audit(a):
    load_runner()
    d = Path(a.drive_dir)
    cfg_like = {'listing_page_marker': 'required'}
    rel = read_json_file(a.release) or {}
    pins = rel.get('pinned_files_sha256') or {}
    af = read_json_file(d / 'ALL_FROZEN.json') or {}
    qf = ((af.get('ledger') or {}).get('path'))
    lst_raw = read_json_file(a.listing) or {}
    lst = parse_listing(a.listing, lst_raw.get('folder'), None, cfg_like)
    slst_raw = read_json_file(a.setup_listing) or {}
    slst = parse_listing(a.setup_listing, slst_raw.get('folder'), None, cfg_like)
    cp_ = Path(a.config) if a.config else Path(a.release).parent / 'VM_HELPER_CONFIG.json'
    kcfg = (read_json_file(cp_) or {}) if cp_.is_file() else {}
    tol = kcfg.get('audit_clock_tolerance_seconds') if isinstance(kcfg.get('audit_clock_tolerance_seconds'), int) else 60   # T-19
    n_tests = kcfg.get('selftest_expected_tests') if isinstance(kcfg.get('selftest_expected_tests'), int) else 600
    sdir = Path(a.setup_dir)
    an, listed = [], []

    def A(code, names, detail=None):
        an.append({'code': code, 'names': names, 'detail': detail})

    def created(n, L=lst):
        return parse_utc(L.by[n][0]['created']) if L.has(n) else None

    notes = {}
    for f in d.iterdir():
        p = parse_name(f.name)
        if p and f.name.endswith('.json'):
            notes[f.name] = read_json_file(f)
    led_raw = Path(qf).read_bytes() if qf and Path(qf).is_file() else b''
    lines = led_raw.split(b'\n')[:-1]
    entries = [json.loads(x) for x in lines]
    led = LedgerView(entries)
    gens = lst.names('genesis')
    if len(gens) != 1 or (notes.get(gens[0]['name']) or {}).get('identity_line', '').encode('utf-8') != (lines[0] if lines else b''):
        A('AUD_GENESIS', [g['name'] for g in gens])
    rej_ids = {}
    for n_, c_ in notes.items():
        if (parse_name(n_) or {}).get('kind') == 'incident' and isinstance(c_, dict):
            for r in c_.get('rejected_copies') or []:
                if isinstance(r, dict):
                    rej_ids.setdefault(r.get('name'), set()).add(r.get('drive_id'))

    def aud_dead(n):
        """T-02: a package name every listed copy of which an INCIDENT rejected, or whose downloaded bytes fail the name
        hash while every listed copy has those bytes: never uploaded intact, so not a save point."""
        cs = lst.by.get(n, [])
        if cs and {f['id'] for f in cs} <= rej_ids.get(n, set()):
            return True
        f = d / n
        if cs and f.is_file() and h8(sha_file(f)) != parse_name(n)['pkg8']:
            m5 = md5_file(f)
            return all(x['md5'] == m5 for x in cs) if all(x['md5'] for x in cs) else len(cs) == 1
        return False
    pk_all = lst.names('package')
    pk = [p for p in pk_all if not aud_dead(p['name'])]
    by = {}
    for p in pk:
        by.setdefault((chain_of(p['tag']), p['seq'], p['pkind']), set()).add(p['name'])
    for k, v in by.items():
        if len({parse_name(n)['pkg8'] for n in v}) > 1:
            A('AUD_FORK', sorted(v))
            listed.append({'code': 'AUD_LATE_UPLOAD_PAIR', 'names': sorted(v), 'created': [lst.by[n][0]['created'] for n in sorted(v)]})
    for p in pk:
        pre = b''.join(x + b'\n' for x in lines[:p['seq']])
        if p['seq'] > len(lines) or h8(sha_bytes(pre)) != p['ledger8']:
            A('AUD_CHAIN', [p['name']])
    for fz in led.of('freeze'):
        tag, case = tag_case_of(fz['job_dir'])
        if not [p for p in pk if p['pkind'] == 'FZ' and p['tag'] == tag and p['case'] == case and p['frozen8'] == h8(fz['frozen_sha256'])]:
            A('AUD_FROZEN_MISSING', [fz['job_dir']])
    starts_ = lst.names('start')
    ais = lst.names('ai')
    incs = [(p, notes.get(p['name']) or {}) for p in lst.names('incident')]
    links = {(notes.get(p['name']) or {}).get('start_note'): notes.get(p['name']) for p in lst.names('link')}
    for s in starts_:
        has_ai = any(x['tag'] == s['tag'] and x['role'] == s['role'] and x['attempt'] == s['attempt'] and x['case'] == s['case'] for x in ais)
        has_inc = any(c.get('start_note') == s['name'] for _, c in incs)
        if not has_ai and not has_inc:
            A('AUD_START_UNRESOLVED', [s['name']])
    # assembled records
    recs = {}
    for r in af.get('runs') or []:
        rp = Path(r['job_dir']) / 'RUN_RECORD.json'
        if rp.is_file():
            recs[r['job_dir']] = (r, read_json_file(rp))
    for jd, (r, rec) in recs.items():
        tag, case = r['tag'], r['case_id']
        st_ = [x for x in starts_ if x['tag'] == tag and x['case'] == case]
        done = [s for s in rec.get('stages', []) if s.get('completed')]
        need_roles = []
        for s in done:
            if s['stage'] == 'scope-finish':
                need_roles.append('S')
            if s['stage'] == 'freeze_response':
                need_roles.append('G')
            if s['stage'] == 'visual-record':
                need_roles.append('V')
            if s['stage'] == 'interrupt':
                prev = [x for x in done if x['seq'] < s['seq']]
                role = 'S' if prev and prev[-1]['next'] == 'SCOPE_READER' else 'G'
                need_roles.append(role)
                ok = any(c.get('classification') == 'AI_NOTHING_WRITTEN' and c.get('tag') == tag and c.get('case_id') == case
                         and c.get('role') == role and c.get('transcript') for _, c in incs)
                if not ok:
                    A('AUD_INTERRUPT_WITHOUT_INCIDENT', [jd])
        for role in set(need_roles):
            if not [x for x in st_ if x['role'] == role]:
                A('AUD_START_MISSING', [jd], {'role': role})
        # AI archives against the frozen copies
        for x in [x for x in ais if x['tag'] == tag and x['case'] == case]:
            m = ai_manifest(d / x['name'])
            if not m or not m.get('response_present'):
                continue
            cands = {'G': ['response/response.json', 'interrupted/generator_output/response.json'],
                     'S': ['scope/SCOPE_READER_RESPONSE.json'], 'V': ['qa/VISUAL_REVIEW.json']}[x['role']]
            if x['role'] == 'V':
                va = Path(jd) / 'qa' / 'visual_review_attempts'
                cands += ['qa/visual_review_attempts/' + f.name for f in va.glob('*.json')] if va.is_dir() else []
            shas = {sha_file(Path(jd) / c) for c in cands if (Path(jd) / c).is_file()}
            if m.get('response_sha256') not in shas:
                A('AUD_AI_SHA_MISMATCH', [x['name']])
            if m.get('revision', 1) > 1:
                ar_ = m.get('after_refusal') or {}
                prevm = ai_manifest(d / (m.get('previous_revision') or {}).get('name', '')) if m.get('previous_revision') else None
                ap = Path(jd) / 'qa' / 'visual_review_attempts' / f'{ar_.get("record_seq", 0):02d}.json'
                if not prevm or not ap.is_file() or sha_file(ap) != prevm.get('response_sha256'):
                    A('AUD_REVISION_MISMATCH', [x['name']])
            # AI after consumer
            sn = m.get('start_note')
            tA, tS = created(x['name']), created(sn) if sn else None
            if tA and tS and tA < tS:
                A('AUD_AI_AFTER_CONSUMER', [x['name']], {'why': 'before its START'})
            cons = {'S': 'scope-finish', 'G': 'freeze_response', 'V': 'visual-record'}[x['role']]
            ce = [s for s in rec.get('stages', []) if s['stage'] == cons and s['seq'] > (m.get('record_seq_at_archive') or 0)]
            if ce:
                first = sorted([p for p in pk if p['tag'] == tag and p['case'] == case and pkg_record_seq(d, p['name']) >= ce[0]['seq']],
                               key=lambda p: p['seq'])
                if first and tA and created(first[0]['name']) and tA > created(first[0]['name']):
                    A('AUD_AI_AFTER_CONSUMER', [x['name'], first[0]['name']])
    for s in starts_:
        if s['role'] == 'V' and s['attempt'] == 2:
            v1 = [x['name'] for x in starts_ if x['tag'] == s['tag'] and x['case'] == s['case'] and x['role'] == 'V' and x['attempt'] == 1]
            if not any(c.get('classification') == 'AI_NOTHING_WRITTEN' and c.get('start_note') in v1 for _, c in incs):
                A('AUD_REPLACEMENT_WITHOUT_INCIDENT', [s['name']])
    sess = sorted(lst.names('session'), key=lambda p: created(p['name']) or now_dt())
    skew = {}
    for i, sp in enumerate(sess):
        c = notes.get(sp['name']) or {}
        t = created(sp['name'])
        if t and parse_utc(c.get('created_utc')):
            sk = (t - parse_utc(c['created_utc'])).total_seconds()
            skew[c.get('boot_id')] = sk
            if abs(sk) > 300:
                listed.append({'code': 'AUD_CLOCK_SKEW', 'names': [sp['name']], 'seconds': sk})
        if (c.get('overrides') or c.get('boot_id_source') != BOOT_ID_DEFAULT) and not a.allow_test_overrides:
            A('AUD_TEST_OVERRIDE', [sp['name']])
        if i > 0 and c.get('mode') == 'restore':
            pc = notes.get(sess[i - 1]['name']) or {}
            if pc.get('boot_id') == c.get('boot_id'):
                A('AUD_RESET_SAME_BOOT', [sess[i - 1]['name'], sp['name']])
        if c.get('mode') == 'restore' or c.get('boot_changed_without_restore'):
            nxt = [p for p in pk + starts_ if created(p['name']) and t and created(p['name']) > t]
            limit = min((created(p['name']) for p in nxt), default=None)
            mine = [p for p, ic in incs if sp['name'] in (ic.get('session_note'), ic.get('restore_session'))
                    and (limit is None or (created(p['name']) or t) <= limit)]
            if len(mine) != 1:
                A('AUD_RESTORE_WITHOUT_INCIDENT', [sp['name']])
    for p, c in incs:
        if c.get('boot_id_old') and c.get('boot_id_old') == c.get('boot_id_new'):
            A('AUD_RESET_SAME_BOOT', [p['name']])
    for s in starts_:
        c = notes.get(s['name']) or {}
        lk = links.get(s['name']) or {}
        t0 = parse_utc(lk.get('started_utc'))
        if t0 is None and s['role'] == 'G':
            for jd, (r, rec) in recs.items():
                if r['tag'] == s['tag'] and r['case_id'] == s['case']:
                    g = read_json_file(Path(jd) / 'response' / 'GENERATION_RECORD.json') or {}
                    t0 = parse_utc(g.get('started_utc'))
        if t0 is None:
            continue
        sk = skew.get(c.get('boot_id'), 0)
        tc = created(s['name'])
        if tc and tc > t0 + datetime.timedelta(seconds=sk + tol):
            A('AUD_START_AFTER_CONVERSATION', [s['name']])
    by_start = {}
    for p, c in incs:
        if c.get('start_note'):
            by_start.setdefault(c['start_note'], []).append((p, c))
    for sn, lst_i in by_start.items():
        cls = [c.get('classification') for _, c in lst_i]
        base = [x for x in cls if x != 'AI_WRITTEN_LOST']
        if len(set(base)) > 1:
            A('AUD_CLASSIFICATION_INCONSISTENT', [p['name'] for p, _ in lst_i])
        if 'AI_NO_CONVERSATION' in cls and sn in links:
            A('AUD_CLASSIFICATION_INCONSISTENT', [p['name'] for p, _ in lst_i], {'why': 'LINK exists'})
    for s in starts_:
        c = notes.get(s['name']) or {}
        if c.get('supersedes'):
            listed.append({'code': 'AUD_START_SUPERSEDED', 'names': [c['supersedes'], s['name']],
                           'created': [str(created(c['supersedes'])), str(created(s['name']))]})
            if any(ic.get('classification') == 'AI_NO_CONVERSATION' for _, ic in by_start.get(s['name'], [])) and \
                    any(ic.get('classification') == 'AI_NO_CONVERSATION' for _, ic in by_start.get(c['supersedes'], [])):
                A('AUD_CLASSIFICATION_INCONSISTENT', [s['name']], {'why': 'AI_NO_CONVERSATION twice on one chain'})
    def pass_ok(p):
        """T-19: a FINGERPRINT_PASS note in SDIR that is the helper's (schema, fingerprint, counts, tools) and names a SELFTEST
        results file in SDIR with that sha256 whose summary agrees."""
        doc = read_json_file(sdir / p['name'])
        if not isinstance(doc, dict) or doc.get('schema') != 'cps.vm-fingerprint-pass.v1' or \
                h8(str(doc.get('fingerprint_sha256') or '')) != p['fp8']:
            return False
        st_ = doc.get('selftest') or {}
        if st_.get('failed_count') != 0 or st_.get('tests') != n_tests or st_.get('passed_count') != n_tests:
            return False
        rt = doc.get('results_tools') or {}
        if not all(isinstance(rt.get(k), str) and len(rt[k]) == 64 for k in
                   ('writer_portable_sha256', 'saved_qa_sha256', 'visual_qa_sha256', 'checker_node_sha256')):
            return False
        rn = st_.get('results_name')
        pr = parse_name(rn) if isinstance(rn, str) else None
        if not pr or pr['kind'] != 'selftest' or pr['fp8'] != p['fp8'] or not (sdir / rn).is_file() or \
                sha_file(sdir / rn) != st_.get('sha256'):
            return False
        sm = ((read_json_file(sdir / rn) or {}).get('summary')) or {}
        return sm.get('tests') == n_tests and sm.get('passed_count') == n_tests and sm.get('failed_count') == 0 and \
            all(sm.get(k) == rt.get(k) for k in ('writer_portable_sha256', 'saved_qa_sha256', 'visual_qa_sha256'))
    passes = []
    for p in slst.names('fpass'):
        if pass_ok(p):
            passes.append((p, created(p['name'], slst)))
        else:
            A('AUD_FINGERPRINT_PASS_INVALID', [p['name']])
    failed_runs = set(af.get('runs_failed_by_reset') or [])
    for p in pk:
        m = pkg_manifest(d, p['name'])
        tp = created(p['name'])
        if not any(fp['fp8'] == p['fp8'] and t and tp and t <= tp for fp, t in passes):
            A('AUD_FINGERPRINT_NOT_PASSED', [p['name']])
        if m is None:
            continue
        if (m.get('helper') or {}).get('sha256') != pins.get('deploy/vm/cps_vm.py') or m.get('runner_sha256') != pins.get('deploy/run/cps_job.py'):
            A('AUD_HELPER_NOT_PINNED', [p['name']])
        bd = m.get('binding') or {}
        if (bd.get('matched') is False or m.get('reset_diverged')) and m.get('job_dir') not in failed_runs:
            A('AUD_BINDING_MISMATCH', [p['name']])
    bind_of = {}
    for p in pk:
        bd = ((pkg_manifest(d, p['name']) or {}).get('binding')) or {}
        for n in bd.get('incidents') or []:
            bind_of.setdefault(n, []).append(bd)
    for p, c in incs:
        if c.get('seen') and c.get('newest_package') is not None:
            later = [q_ for q_ in pk if q_['tag'] == c.get('tag') and q_['case'] == c.get('case_id') and created(q_['name']) and created(p['name'])
                     and created(q_['name']) > created(p['name'])]
            if later:
                m = pkg_manifest(d, sorted(later, key=lambda q_: created(q_['name']))[0]['name'])
                if m is not None and p['name'] not in ((m.get('binding') or {}).get('incidents') or []):
                    A('AUD_BINDING_MISMATCH', [p['name']], {'why': 'seen tokens not consumed'})
            real = [t for t in c.get('seen') or [] if (parse_token(t) or {}).get('none') is False]
            bds = bind_of.get(p['name'], [])
            # T-05: a real seen token must meet a comparison (a completed re-run), never only refused re-runs
            if real and bds and not any(bd.get('compared', bd.get('matched') is not None) for bd in bds) \
                    and c.get('job_dir') not in failed_runs:
                A('AUD_BINDING_MISMATCH', [p['name']], {'why': 'seen tokens never compared'})
    rows = []
    for s in starts_:
        c = notes.get(s['name']) or {}
        lk = links.get(s['name']) or {}
        ai = [x['name'] for x in ais if (x['tag'], x['role'], x['attempt'], x['case']) == (s['tag'], s['role'], s['attempt'], s['case'])]
        ii = by_start.get(s['name'], [])
        rows.append({'start': s['name'], 'drive_created': str(created(s['name'])), 'case_id': s['case'], 'reader': c.get('reader'),
                     'role': s['role'], 'attempt': s['attempt'], 'conversation': lk.get('conversation'), 'attested_start': lk.get('started_utc'),
                     'ai_archive': ai, 'incidents': [{'name': p['name'], 'classification': ic.get('classification'),
                                                      'conversation': ic.get('conversation'), 'transcript': (ic.get('transcript') or {}).get('name')}
                                                     for p, ic in ii],
                     'superseded': any((notes.get(x['name']) or {}).get('supersedes') == s['name'] for x in starts_),
                     'open_and_check': any(ic.get('classification') in ('AI_NOTHING_WRITTEN', 'AI_NO_CONVERSATION') for _, ic in ii),
                     'owner_platform_created': None})
    rep = Path(a.report) if a.report else d / 'AUDIT_REPORT.json'
    write_atomic(rep, note_bytes({'schema': 'cps.vm-audit-report.v1', 'created_utc': utc(), 'helper': helper_info(), 'anomalies': an,
                                  'listed': listed, 'runs_failed_by_reset': sorted(failed_runs)}))
    write_atomic(rep.parent / 'O52_COMPARISON.json', note_bytes({'schema': 'cps.vm-o52-comparison.v1', 'rows': rows}))
    b = Block()
    b.result = {'command': 'audit', 'anomalies': len(an), 'codes': sorted({x['code'] for x in an}), 'report': str(rep)}
    b.next('DONE')
    b.code = EXIT_OK if not an else EXIT_STOP
    return b


def tag_case_of(job_dir):
    p = Path(job_dir)
    root, case = p.parent.name, p.name
    if root in ROOT_TAGS:
        return ROOT_TAGS[root], case
    return 'E' + root, case


_MAN_CACHE = {}


def pkg_manifest(d, name):
    p = Path(d) / name
    if name in _MAN_CACHE:
        return _MAN_CACHE[name]
    m = None
    if p.is_file():
        try:
            with tarfile.open(p, 'r:gz') as tf:
                f = tf.extractfile(tf.getmembers()[0])
                m = json.loads(f.read())
        except Exception:                                   # noqa: BLE001
            m = None
    _MAN_CACHE[name] = m
    return m


def pkg_record_seq(d, name):
    m = pkg_manifest(d, name)
    return ((m or {}).get('record') or {}).get('seq') or 0


def ai_manifest(p):
    return pkg_manifest(Path(p).parent, Path(p).name) if Path(p).is_file() else None


# ------------------------------------------------------------------ command line
def build_parser():
    ap = argparse.ArgumentParser(prog='cps_vm.py', description='CPS reset-proof VM helper (see deploy/vm/README.md)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('session')
    p.add_argument('--inbox')
    p.add_argument('--operator-model', required=True)
    p = sub.add_parser('fingerprint')
    p.add_argument('--json', action='store_true')
    sub.add_parser('selftest')
    sub.add_parser('fingerprint-pass')
    p = sub.add_parser('genesis')
    p.add_argument('--first-ledger', action='store_true')
    p = sub.add_parser('wrap')
    p.add_argument('args', nargs=argparse.REMAINDER)
    p = sub.add_parser('package')
    p.add_argument('--job-dir', required=True)
    p = sub.add_parser('start-note')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--role', required=True, choices=['S', 'G', 'V'])
    p = sub.add_parser('link-note')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--role', required=True, choices=['S', 'G', 'V'])
    p.add_argument('--conversation', required=True)
    p.add_argument('--started-utc')
    p = sub.add_parser('ai-archive')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--role', required=True, choices=['S', 'G', 'V'])
    p.add_argument('--revision', action='store_true')
    sub.add_parser('restore')
    p = sub.add_parser('incident')
    p.add_argument('--classification', required=True)
    p.add_argument('--job-dir')
    p.add_argument('--role', choices=['S', 'G', 'V'])
    p.add_argument('--conversation')
    p.add_argument('--conversation-ended', action='store_true')
    p.add_argument('--transcript')
    p.add_argument('--seen', action='append')
    p.add_argument('--not-seen', action='store_true')
    p.add_argument('--note')
    sub.add_parser('recheck')
    p = sub.add_parser('evict')
    p.add_argument('--job-dir')
    p.add_argument('--all', action='store_true')
    sub.add_parser('final')
    p = sub.add_parser('assemble')
    p.add_argument('--drive-dir', required=True)
    p.add_argument('--verify-frozen', action='store_true')
    p.add_argument('--report')
    p = sub.add_parser('audit')
    p.add_argument('--drive-dir', required=True)
    p.add_argument('--listing', required=True)
    p.add_argument('--setup-dir', required=True)
    p.add_argument('--setup-listing', required=True)
    p.add_argument('--release', required=True)
    p.add_argument('--allow-test-overrides', action='store_true')
    p.add_argument('--config', help='the kit VM_HELPER_CONFIG.json (default: next to --release)')
    p.add_argument('--report')
    sub.add_parser('status')
    sub.add_parser('wait')
    p = sub.add_parser('job-start')
    p.add_argument('--case', required=True)
    p.add_argument('--restart-of')
    p.add_argument('--incident')
    p = sub.add_parser('delivery-note')
    p.add_argument('--job-dir', required=True)
    p.add_argument('--prepared', action='store_true')
    p.add_argument('--sent', action='store_true')
    p.add_argument('--copy')
    p.add_argument('--log')
    p.add_argument('--profile-folder')
    p.add_argument('--prepared-note')
    p = sub.add_parser('rebuild-parts')
    p.add_argument('--fz', required=True)
    p = sub.add_parser('_worker')
    p.add_argument('wid')
    return ap


COMMANDS = {'session': cmd_session, 'fingerprint': cmd_fingerprint, 'selftest': cmd_selftest, 'fingerprint-pass': cmd_fingerprint_pass,
            'genesis': cmd_genesis, 'wrap': cmd_wrap, 'package': cmd_package, 'start-note': cmd_start_note, 'link-note': cmd_link_note,
            'ai-archive': cmd_ai_archive, 'restore': cmd_restore, 'incident': cmd_incident, 'recheck': cmd_recheck, 'evict': cmd_evict,
            'final': cmd_final, 'assemble': cmd_assemble, 'audit': cmd_audit, 'status': cmd_status, 'wait': cmd_wait,
            'job-start': cmd_job_start, 'delivery-note': cmd_delivery_note, 'rebuild-parts': cmd_rebuild_parts}


def main(argv=None):
    ap = build_parser()
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else 0
    if a.cmd == '_worker':
        return cmd_worker(a)
    try:
        b = COMMANDS[a.cmd](a)
    except Halt as h:
        b = h.to_block()
    except Exception as e:                                  # noqa: BLE001 - an internal error is a STOP (case C), never a guess
        import traceback
        traceback.print_exc(file=sys.stderr)
        b = Halt('STOP', 'INTERNAL_ERROR', 'an unexpected helper error: hand back case C with the output',
                 detail={'error': type(e).__name__}).to_block()
    sys.stdout.write(b.text())
    sys.stdout.flush()
    return b.code


if __name__ == '__main__':
    sys.exit(main())
