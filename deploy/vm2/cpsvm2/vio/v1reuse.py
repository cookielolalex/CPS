"""The 52 reused segments of deploy/vm/cps_vm.py at 95df270 (spec §1.4), byte-identical, in v1 order.
Generated from the v1 file; tests/test_reuse.py checks every segment hash against REUSE_MANIFEST.json. Do not edit:
a changed function belongs in v1mod.py (§1.6)."""
import datetime
import errno
import fcntl
import gzip
import hashlib
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

from .v1compat import *  # noqa: F401,F403


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

    def hand_off(self):
        """r3 failure-R3-03: close this descriptor without unlocking: a child that inherited it keeps the lock."""
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    @classmethod
    def adopt(cls, lay, fd):
        """The lock a detached worker inherited; None when the descriptor is not the helper lock or the lock is not ours."""
        try:
            st, want = os.fstat(fd), os.stat(lay.outbox / '.lock')
            if (st.st_dev, st.st_ino) != (want.st_dev, want.st_ino):
                return None
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)     # our own open file description: succeeds at once
        except OSError:
            return None
        lk = cls(lay)
        lk.fd = fd
        return lk

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
                # r3 failure-R3-05: never follow a link; the size is the opened file's own (a member is never cut short)
                fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, 'rb') as f:
                    st = os.fstat(f.fileno())
                    if not stat.S_ISREG(st.st_mode):
                        raise OSError(f'not a regular file: {src}')
                    tf.addfile(_tarinfo(name, mode, mtime, size=st.st_size), f)


def unsafe_name(n):
    if not n or '\\' in n or '\0' in n or n.startswith('/'):
        return 'path'
    parts = n.split('/')
    if any(p in ('', '.', '..') for p in parts):
        return 'component'
    return None


def under_stage(stage, rel):
    """T-04: a member path that stays inside the staging folder (no '..', no absolute path, no link on the way)."""
    if not isinstance(rel, str) or unsafe_name(rel):
        return False
    root = os.path.realpath(stage)
    parent = os.path.realpath(os.path.join(root, os.path.dirname(rel)) if os.path.dirname(rel) else root)
    return parent == root or parent.startswith(root + os.sep)


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


class PartWriter:
    """r3 failure-R3-06: a file-like sink that cuts a tar stream into part files as it is written (no whole PNG tar on
    disk) and hashes the whole stream. Parts are written under temporary names; finish() returns [(tmp path, bytes,
    sha256, md5)] in order and the whole stream's sha256."""
    def __init__(self, outdir, part_bytes, prefix):
        self.outdir, self.pb, self.prefix = Path(outdir), part_bytes, prefix
        self.whole = hashlib.sha256()
        self.parts, self.cur, self.cur_n = [], None, 0

    def _open(self):
        p = self.outdir / f'{self.prefix}{len(self.parts) + 1:03d}.tmp'
        if os.path.lexists(p):
            os.unlink(p)
        self.cur = open(p, 'xb')
        self.cur_path, self.cur_n = p, 0
        self.cur_sha, self.cur_md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)

    def _close(self):
        if self.cur is not None:
            self.cur.flush()
            os.fsync(self.cur.fileno())
            self.cur.close()
            self.parts.append((self.cur_path, self.cur_n, self.cur_sha.hexdigest(), self.cur_md5.hexdigest()))
            self.cur = None

    def write(self, b):
        b = memoryview(b)
        self.whole.update(b)
        while len(b):
            if self.cur is None:
                self._open()
            k = min(len(b), self.pb - self.cur_n)
            self.cur.write(b[:k])
            self.cur_sha.update(b[:k])
            self.cur_md5.update(b[:k])
            self.cur_n += k
            b = b[k:]
            if self.cur_n >= self.pb:
                self._close()
        return None

    def flush(self):
        pass

    def tell(self):
        return sum(x[1] for x in self.parts) + (self.cur_n if self.cur is not None else 0)

    def finish(self):
        self._close()
        return self.parts, self.whole.hexdigest()

    def discard(self):
        if self.cur is not None:
            self.cur.close()
            self.cur = None
        for p_, *_ in self.parts:
            if os.path.lexists(p_):
                os.unlink(p_)
        if getattr(self, 'cur_path', None) is not None and os.path.lexists(self.cur_path):
            os.unlink(self.cur_path)


def tree_bytes(root):
    """The bytes of every regular file below root (never following a link)."""
    n = 0
    for dp, dns, fns in os.walk(str(root), followlinks=False):
        for f in fns:
            try:
                st = os.lstat(os.path.join(dp, f))
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                n += st.st_size
    return n


def disk_full_halt(lay, need=None, what=None):
    """r3 failure-R3-06: STOP DISK_FULL (case C) naming the free space and the largest files under BASE to free."""
    free = None
    try:
        free = shutil.disk_usage(str(lay.outbox if lay.outbox.exists() else lay.base)).free
    except OSError:
        pass
    big = []
    for root in (lay.outbox, lay.inbox):
        if root.is_dir():
            for f in root.iterdir():
                try:
                    if f.is_file() and not f.is_symlink():
                        big.append((os.lstat(f).st_size, str(f)))
                except OSError:
                    continue
    big.sort(reverse=True)
    return Halt('STOP', 'DISK_FULL', 'the VM file system is full: nothing was uploaded for this step; hand back case C with the '
                'RESULT (the owner decides what to free)', detail={'free_bytes': free, 'need_bytes': need, 'step': what,
                                                                  'largest_files': [p_ for _, p_ in big[:8]]})


def require_space(lay, need, what):
    """r3 failure-R3-06: refuse to start a step that cannot finish on the free space left (STOP DISK_FULL)."""
    try:
        free = shutil.disk_usage(str(lay.outbox if lay.outbox.exists() else lay.base)).free
    except OSError:
        return
    if free < need + SPACE_MARGIN:
        raise disk_full_halt(lay, need, what)


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
