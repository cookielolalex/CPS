"""The world harness (spec §14.2 with the probe-results delta §X.14): FakeDrive, FakeDot, the reset seams and the World
builder. Invented data only.

FakeDrive: folders of name -> [copies {id, md5, size, sha256, created}], add-only (nothing is ever edited or deleted by
the Dot). The helper side has only exact-name FIND (every copy), a newest-first LIST of one folder limited to k (by
creation order, only when the world's gates say yes) and download by id; there is no full listing (OP-06) and, with
`hide_md5` (the default, as P2/M004 found), no md5 in any result. Knobs per name: lag (a copy stays invisible for n
FINDs), drop (the k-th upload never lands), late (a dropped or timed-out upload appears after n FINDs), timeout (the
k-th upload reports a timeout), refuse (the k-th upload is refused by the platform's approval review and lands after
approve(), or never), dup (every upload lands twice), foreign copies (plant), and a lost part (remove, the test's
side). The oracle and the audit read `table()` directly.

FakeDot: runs cli.main in-process, one command at a time to completion (the poll model of P5: a foreground command
keeps running until it exits, and the Dot starts no other helper command meanwhile). It splits the optional
`CPSV-RUNNING` line from the block, checks every block against the §6.1 grammar (F6, L5) and the printing rules (L9),
executes each block literally (UPLOAD, FIND, LIST, DOWNLOAD on FakeDrive; one DO action), reports `--refused` for an
upload the platform refused, plays the AI roles with the runner's invented stand-ins, answers like the operator (VM
clock times, conversation list read against `after=`), and keeps its notes (the last CPSV line, the CPSV-REPO line).
A reset (FakeDot.reset) deletes BASE (BASE/repo included) and the tools marker, gives a new boot id, and runs the
README bootstrap lines (§6.1) with the clone line replaced by a symbolic link to the checkout under test.

Reset seams (§X.14): stages run in-process in `go`, so a reset inside a stage is injected by wrappers around
vio.runner.run_runner, the placement steps, the snapshot, the PNG part writer and vio.durable.write that raise
`Reset` (a BaseException) at the chosen call; FakeDot catches it and resets. `Kill` is the same without a reset (a
process killed in the same boot: FOREGROUND_DIED). The shipped code has no switch.

World: HOME, BASE, TOOLS under one folder; a kit built from an invented release, admission, JOBS.json, jobs and
config; the real runner v4 (no memoization). The clock is real time everywhere (the runner checks the attested
generator times against its own clock, R21). To keep WAIT blocks short, the absence interval w_abs (core.fold.w_abs)
is patched in-process to W_ABS_TEST seconds and every WAIT is slept for at most W_ABS_TEST seconds by the Dot."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import math
import os
import shlex
import shutil
import stat
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VM2 = HERE.parent
REPO = VM2.parents[1]
sys.path.insert(0, str(VM2))
from cpsvm2 import cli                                                      # noqa: E402
from cpsvm2.core import fold as F                                           # noqa: E402
from cpsvm2.core import names as N                                          # noqa: E402
from cpsvm2.vio import drive, host, v1reuse                                 # noqa: E402
import seen                                                                 # noqa: E402

_spec = importlib.util.spec_from_file_location('tcj_for_vm2', str(REPO / 'deploy/run/test_cps_job.py'))
TCJ = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TCJ)

GATES = {'p1_vm_files': 'PASS', 'p1_transcript_export': 'no', 'p1_conversation_list': 'yes',
         'p1_end_after_reset': 'yes', 'p2_exact_search': 'PASS', 'p2_md5_visible': 'no', 'p2_newest_first': 'yes',
         'p2_lag_seconds': 0, 'p2_max_upload_bytes': 50000000, 'p2_tgz_kept': 'PASS',
         'p2_failed_upload_can_appear': 'yes', 'p3_identity_stable': 'yes', 'p3_clock_tolerance_seconds': 300,
         'p5_foreground_hold_seconds': 1200, 'p5_setup_seconds': 130}
STAGE_MAX = {'selftest': 1100, 'place': 300, 'prepare': 600, 'nonattempt': 300, 'scope-finish': 600, 'finish': 900,
             'visual-record': 600, 'interrupt': 600, 'freeze': 600}
NODE = '/opt/node22/bin/node'
NODE_SHA = '2286ce921a47349726b0e8b037ccbb6627043d24d1fc3c8f22c2dc53c4a1f7ff'
NODE_PATH = os.environ.get('NODE_PATH') or '/usr/local/lib/node_modules_global'
CONV_RE = r'conv-[0-9a-f]{8}'
DOC_SAMPLES = []


def sha(b):
    return hashlib.sha256(b).hexdigest()


def md5(b):
    return hashlib.md5(b).hexdigest()


def readme_samples():
    """The README's example values (§6.8): the doc_samples block, one value per line."""
    t = (VM2 / 'README.md').read_text(encoding='utf-8')
    blk = t.split('<!-- doc_samples:begin -->', 1)[1].split('<!-- doc_samples:end -->', 1)[0]
    return [ln for ln in blk.splitlines() if ln.strip() and not ln.startswith('```')]


def readme_bootstrap():
    t = (VM2 / 'README.md').read_text(encoding='utf-8')
    blk = t.split('<!-- bootstrap:begin -->', 1)[1].split('<!-- bootstrap:end -->', 1)[0]
    return [ln for ln in blk.splitlines() if ln.strip() and not ln.startswith('```')]


# ================================================================ the clock
W_ABS_TEST = 2


class Clock:
    """Real time (see the module docstring); advance() is the Dot's wait, at most W_ABS_TEST + 0.2 s."""
    offset = 0

    def now(self):
        return host.now()

    def advance(self, s):
        time.sleep(min(float(s), W_ABS_TEST + 0.2))


def real_utc():
    """What the Dot reads on its own (real) clock, rounded up to the second."""
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(math.ceil(time.time())))


# ================================================================ FakeDrive
class FakeDrive:
    def __init__(self, gates):
        self.gates = gates
        self.hide_md5 = gates.get('p2_md5_visible') != 'yes'
        self.folders, self.blobs, self.n, self.calls = {}, {}, 0, []
        self.uploads, self.max_upload = {}, 0
        self.drop, self.lag, self.late, self.dup = {}, {}, {}, set()
        self.timeout, self.refuse, self.refused_pending, self.ghosts = {}, {}, [], []

    def _put(self, folder, name, data, hidden=0):
        self.n += 1
        c = {'id': 'fakedriveid%015d' % self.n, 'md5': md5(data), 'size': len(data), 'sha256': sha(data),
             'created': self.n, 'ctime': host.now(), 'hidden': hidden}
        self.blobs[c['id']] = data
        self.folders.setdefault(folder, {}).setdefault(name, []).append(c)
        return c

    def _out(self, c):
        """What the Dot's tool shows of a copy: id, size, creation (and md5 only when visible)."""
        r = {'id': c['id'], 'size': c['size'], 'created': c['created']}
        if not self.hide_md5:
            r['md5'] = c['md5']
        return r

    # ---- the Dot's side
    def upload(self, path, folder, name):
        """Returns 'ok', 'timeout' or 'refused' (what the Dot's tool reports)."""
        self.calls.append(('UPLOAD', folder, name))
        k = self.uploads[name] = self.uploads.get(name, 0) + 1
        data = Path(path).read_bytes()
        assert data, 'Drive rejects an empty file'
        assert len(data) <= 104857600, 'the platform refuses an upload over 100 MiB (P2)'
        self.max_upload = max(self.max_upload, len(data))
        if k in self.refuse.get(name, ()):
            self.refused_pending.append((folder, name, data))
            return 'refused'
        if k in self.drop.get(name, ()):
            if name in self.late:
                self._put(folder, name, data, hidden=self.late[name])
            return 'ok'
        if k in self.timeout.get(name, ()):
            if name in self.late:
                self._put(folder, name, data, hidden=self.late[name])
            return 'timeout'
        self._put(folder, name, data, hidden=self.lag.get(name, 0))
        if name in self.dup:
            self._put(folder, name, data)
        return 'ok'

    def approve(self, land=True):
        """The owner approves the refused uploads in the platform; they land (or, land=False, never do)."""
        for folder, name, data in self.refused_pending:
            if land:
                self._put(folder, name, data)
        self.refused_pending = []

    def _visible(self, cs):
        out = []
        for c in cs:
            if c['hidden'] > 0:
                c['hidden'] -= 1
            else:
                out.append(c)
        return out

    def find(self, folder, name):
        self.calls.append(('FIND', folder, name))
        return [self._out(c) for c in self._visible(self.folders.get(folder, {}).get(name, []))]

    def list_newest(self, folder, k):
        assert self.gates['p2_newest_first'] == 'yes', 'a LIST without the gate'
        self.calls.append(('LIST', folder, k))
        rows = [(c['created'], n, c) for n, cs in self.folders.get(folder, {}).items()
                for c in cs if c['hidden'] <= 0]
        got = [(n, self._out(c)) for _, n, c in sorted(rows, key=lambda r: -r[0])[:k]]
        return [(f_, c) for fo, f_, c in self.ghosts if fo == folder] + got          # listed, never found

    def download(self, did):
        self.calls.append(('DOWNLOAD', None, did))
        return self.blobs[did]

    # ---- the test's side (oracle, audit, injected faults)
    def table(self):
        return self.folders

    def has(self, folder, name):
        return bool(self.folders.get(folder, {}).get(name))

    def bytes_of(self, folder, name):
        return self.blobs[self.folders[folder][name][0]['id']]

    def plant(self, folder, name, data):
        return self._put(folder, name, data)

    def remove(self, folder, name):
        """A file lost on Drive (a part upload that never landed, as the scenario says)."""
        self.folders.get(folder, {}).pop(name, None)

    def listing(self, folder):
        """The maintainer tool's full listing (audit input; never offered to the helper). With md5 hidden it has no
        md5Checksum either (§X.10)."""
        out = []
        for n, cs in sorted(self.folders.get(folder, {}).items()):
            for c in cs:
                r = {'id': c['id'], 'name': n, 'size': str(c['size']), 'createdTime': c['ctime']}
                if not self.hide_md5:
                    r['md5Checksum'] = c['md5']
                out.append(r)
        return out


class Reset(BaseException):
    """A VM reset injected at a seam inside a foreground stage (§X.14)."""


class Kill(BaseException):
    """The helper process killed in the same boot (the platform ended the foreground command)."""


class Seams:
    """Wrappers around the in-process stage steps; `arm(where, n, exc, sub)` raises exc at the n-th call of `where`
    (counted from arming) whose sub-command is `sub` (a runner call's own sub-command; for the other seams the first
    runner sub-command of the current helper command), or any when sub is None. where: 'runner_before',
    'runner_after', 'snapshot', 'png_parts', 'place_job', 'place_ledger', 'write' (vio.durable.write), 'selftest'."""
    def __init__(self):
        from cpsvm2 import worker
        from cpsvm2.vio import durable, place, runner, savepoint
        self.mods = {'runner': runner, 'place': place, 'savepoint': savepoint, 'durable': durable, 'worker': worker}
        self.orig = {'run_runner': runner.run_runner, 'snapshot': place.snapshot, 'png_parts': savepoint._png_parts,
                     'place_job': place.place_job, 'place_ledger': place.place_ledger, 'write': durable.write,
                     'selftest_work': worker.selftest_work}
        self.armed, self.count, self.hits, self.times = None, 0, [], 0
        self.stage_calls, self.subs, self.cmd_subs = {}, [], []
        runner.run_runner = self._runner
        place.snapshot = self._wrap('snapshot', self.orig['snapshot'])
        savepoint._png_parts = self._wrap('png_parts', self.orig['png_parts'], after=False)
        place.place_job = self._wrap('place_job', self.orig['place_job'])
        place.place_ledger = self._wrap('place_ledger', self.orig['place_ledger'])
        durable.write = self._wrap('write', self.orig['write'], after=False)
        worker.selftest_work = self._wrap('selftest', self.orig['selftest_work'], after=False)

    def close(self):
        m = self.mods
        m['runner'].run_runner = self.orig['run_runner']
        m['place'].snapshot, m['place'].place_job = self.orig['snapshot'], self.orig['place_job']
        m['place'].place_ledger = self.orig['place_ledger']
        m['savepoint']._png_parts, m['durable'].write = self.orig['png_parts'], self.orig['write']
        m['worker'].selftest_work = self.orig['selftest_work']

    def arm(self, where, n=1, exc=Reset, sub=None, times=1):
        self.armed, self.count, self.times = (where, n, exc, sub), 0, times

    def disarm(self):
        self.armed = None

    def _hit(self, where, sub=None):
        if sub is None:
            sub = self.cmd_subs[0] if self.cmd_subs else None
        if self.armed and self.armed[0] == where and self.armed[3] in (None, sub):
            self.count += 1
            if self.count == self.armed[1]:
                exc = self.armed[2]
                self.times -= 1
                if self.times <= 0:
                    self.armed = None
                self.count = 0
                self.hits.append(where)
                raise exc(where)

    def _wrap(self, where, fn, after=True):
        def w(*a, **k):
            self.stage_calls[where] = self.stage_calls.get(where, 0) + 1
            if not after:
                self._hit(where)
            r = fn(*a, **k)
            if after:
                self._hit(where)
            return r
        return w

    def _runner(self, ctx, argv, log):
        self._hit('runner_before', argv[0])
        self.subs.append(argv[0])
        self.cmd_subs.append(argv[0])
        r = self.orig['run_runner'](ctx, argv, log)
        self.stage_calls[argv[0]] = self.stage_calls.get(argv[0], 0) + 1
        self._hit('runner_after', argv[0])
        return r


# ================================================================ FakeDot
DOT_FIELDS = ('blocks', 'notes', 'policy', 'conv_n', 'convs', 'opened', 'current', 'events', 'o2', 'refused', 'live',
              'answered', 'running', 'stops_a', 'attests_after', 'killed_tree', 'downloads', 'reset_calls')


class FakeDot:
    """Executes blocks literally. policy keys (scenario answers):
       'v': 'pass' | 'fail' | 'incomplete' (first review) ; 'v_cont': 'pass' | 'incomplete' (after CONTINUE)
       'export': True/False (EXPORT_TRANSCRIPT done) ; 'restore': {...restore answers...} ; 'arrived': 'yes'|'no'
       'list_shows_none': 'yes'|'no' (C5 rebase question) ; 'approve': True/False (the owner approves a refused
       upload, HANDBACK A, and it lands)."""
    def __init__(self, world):
        self.w = world
        self.blocks, self.notes = [], {'cpsv': None, 'repo': None}
        self.policy = {'v': 'pass', 'v_cont': 'pass', 'export': False, 'restore': {}, 'arrived': 'yes',
                       'list_shows_none': 'yes', 'role_writes': True, 'approve': True}
        self.conv_n, self.convs, self.opened = 0, {}, {}
        self.current = None
        self.hook = None                        # hook(dot, lines) -> None | 'reset' | 'stop' before a block is done
        self.events = []                        # ('OPEN', role, prompt, boot) ... in order
        self.o2, self.refused, self.live, self.answered = set(), [], {}, []
        self.running, self.stops_a, self.attests_after, self.killed_tree = [], [], [], None
        self.downloads = []                     # (boot, drive id, path) of every DOWNLOAD line done
        self.reset_calls = []                   # len(FakeDrive.calls) at each reset (the restore's call budget)

    # ---- one helper command, run to completion (P5: the Dot polls the same session until the process exits)
    def cmd(self, *argv):
        v2 = self.w.base / 'outbox/v2'
        before = cache_files(v2) if argv[0] in ('found', 'answer', 'go') else None
        out = io.StringIO()
        t0, n0 = time.time(), len(self.w.seams.subs)
        self.w.seams.cmd_subs = []
        try:
            with contextlib.redirect_stdout(out):
                code = cli.main(list(argv))
        except Reset:
            self.blocks.append({'argv': list(argv), 'code': None, 'lines': out.getvalue().splitlines(),
                                'boot': self.w.boot, 'reset': True})
            return self.reset()
        except Kill:
            lines = [ln for ln in out.getvalue().splitlines() if ln]
            self.blocks.append({'argv': list(argv), 'code': None, 'lines': lines, 'boot': self.w.boot, 'kill': True})
            self.killed_tree = self.w.jobs_tree()
            return None, lines
        lines = [ln for ln in out.getvalue().splitlines() if ln]
        if lines and lines[0].startswith('CPSV-RUNNING '):
            assert argv[0] == 'go', 'X.5: %s started a stage' % argv[0]
            r = dict(x.split('=', 1) for x in lines[0].split()[1:])
            assert set(r) == {'kind', 'since', 'max'} and r['kind'] in ('selftest', 'place', 'chain'), lines[0]
            subs = self.w.seams.subs[n0:]
            self.running.append({'kind': r['kind'], 'max': int(r['max']), 'seconds': round(time.time() - t0, 1),
                                 'first': subs[0] if subs else None, 'subs': subs})
            lines = lines[1:]
        assert not any(ln.startswith('CPSV-RUNNING') for ln in lines), 'a RUNNING line inside a block'
        if lines and lines[0].startswith('CPSV-BUSY '):
            assert code == 4 and lines[1:] == ['REFUSED HELPER_BUSY', 'DO: POLL'], lines
            assert before is None or cache_files(v2) == before, 'O7: a busy refusal changed a cache file'
        elif lines and lines[0].startswith('CPSV ') and code != 2:
            why = drive.check_grammar(lines)
            assert why is None, 'F6/L5 block grammar (%s): %s' % (why, lines)
            check_printed(lines, self.w.case_ids())
            self.notes['cpsv'] = lines[0]
            self.oracles(lines)
            self.check_uploads(lines)
        if code == 4 and before is not None and argv[0] in ('found', 'answer'):
            assert cache_files(v2) == before, 'O7: a refusal changed a cache file'
            self.refused.append(lines[1] if len(lines) > 1 else '')
        self.blocks.append({'argv': list(argv), 'code': code, 'lines': lines, 'boot': self.w.boot})
        return code, lines

    def check_uploads(self, lines):
        """L12: every UPLOAD line names a file of at most max_upload_bytes."""
        mx = self.w.config_doc()['max_upload_bytes']
        for ln in lines:
            if ln.startswith('UPLOAD '):
                p = shlex.split(ln)[1]
                assert os.path.getsize(p) <= mx, 'L12: an UPLOAD over max_upload_bytes'

    def oracles(self, lines):
        """O1 (no reveal before the commit it depends on is on Drive with every part) and O2 (one OPEN per START,
        one CONTINUE per continuation, one DELIVER to=user per permission), on every printed block."""
        do = lines[-1]
        st = self.w.cache()
        reveal = any(x in do for x in ('OPEN_CONVERSATION', 'CONTINUE_CONVERSATION', 'NOTIFY_OWNER', 'ASK_USER',
                                        'DELIVER ', 'HANDBACK B'))
        if (self.w.base / 'outbox/v2/PENDING.json').is_file() and any(ln.startswith('UPLOAD ') for ln in lines):
            assert 'state=SAVE' in lines[0] or 'state=RESTORE' in lines[0], 'O1: a commit block not in state SAVE'
        if not reveal:
            return
        assert not (self.w.base / 'outbox/v2/PENDING.json').is_file(), 'O1: revealed while a commit is pending'
        for cf in (st or {}).get('confirms') or []:
            want = {c['id'] for c in cf['copies']}
            have = {c['id'] for fo in self.w.drive.folders.values() for c in fo.get(cf['name'], [])}
            assert want and want <= have, 'O1: %s revealed before %s is on Drive' % (do[:40], cf['name'])
            for fo in self.w.drive.folders.values():
                for c in fo.get(cf['name'], []):
                    if c['id'] in want:
                        assert c['md5'] == cf['copies'][0]['md5'], 'O1: a confirmed copy has other bytes'
        s = (st or {}).get('state') or {}
        R = (s.get('runs') or {}).get(s.get('current')) if s.get('current') else None
        key = None
        if 'OPEN_CONVERSATION' in do and R:
            for k, ro in sorted(R['roles'].items()):
                if ro['status'] in ('STARTED', 'OPENED'):
                    lt = [x for x in ro['starts'] if x['superseded_by'] is None][-1]
                    key = ('OPEN', R['key'], k, lt['start_no'], lt['seq'])
        elif 'CONTINUE_CONVERSATION' in do and R:
            for k, ro in sorted(R['roles'].items()):
                if ro['status'] == 'CONTINUED':
                    key = ('CONTINUE', R['key'], k, ro['continuations'])
        elif 'to=user' in do and R:
            d = R['delivery'] or {}
            key = ('DELIVER_USER', R['key'], d.get('prepared_seq'), d.get('ack_seq'))
        if key is not None:
            assert key not in self.o2, 'O2: printed twice: %r' % (key,)
            self.o2.add(key)

    # ---- the loop
    def run(self, code, lines, max_steps=900):
        """Follow blocks until a STOP, a refusal the scenario did not expect, or max_steps. Returns (code, lines)."""
        for _ in range(max_steps):
            if self.hook is not None:
                h = self.hook(self, lines)
                if h == 'stop':
                    return code, lines
                if h == 'reset':
                    code, lines = self.reset()
                    continue
            if code is None:                    # killed in the same boot: the Dot runs go once (§X.6.1)
                code, lines = self.cmd('go')
                continue
            if code == 3 and lines and lines[-1].endswith(' HANDBACK A'):
                self.stops_a.append(lines[-1])
                self.w.drive.approve(self.policy['approve'])
                code, lines = self.cmd('go')
                continue
            if code == 4 and len(lines) > 1 and lines[1] == 'REFUSED INPUTS_CHANGED' and self.w.restore_inputs():
                code, lines = self.cmd('go')            # the Dot puts the user's files back after a reset (§11.4)
                continue
            if code not in (0,):
                return code, lines
            nxt = self.execute(lines)
            if nxt is None:
                return code, lines
            code, lines = nxt
        raise AssertionError('no end after %d blocks: %s' % (max_steps, lines))

    def execute(self, lines):
        d = self.w.drive
        finds, plist, status = [], None, {}
        for ln in lines[1:-1]:
            t = shlex.split(ln)
            if t[0] == 'REFUSED':
                continue
            if t[0] == 'UPLOAD':                          # once each, never retried by the Dot (§X.5.6 step 1)
                status[t[5]] = d.upload(t[1], t[3], t[5])
            elif t[0] == 'FIND':
                assert t[2] == 'NAME' and len(t) == 4, 'X.5: only exact-name FIND exists: %s' % ln
                finds.append((t[3], d.find(t[1], t[3])))
            elif t[0] == 'LIST':
                assert t[2] == 'NEWEST' and len(t) == 4, ln
                plist = d.list_newest(t[1], int(t[3]))
            elif t[0] == 'DOWNLOAD':
                Path(t[5]).parent.mkdir(parents=True, exist_ok=True)
                Path(t[5]).write_bytes(d.download(t[3]))
                self.downloads.append((self.w.boot, t[3], t[5], self.w.in_session()))
        do = lines[-1][len('DO: '):]
        t = shlex.split(do)
        act = t[0]
        hidden = 'ID:SIZE ...' in do                    # the block names the form the helper expects (§X.6.2)
        fmt = (lambda c: '%s:%d' % (c['id'], c['size'])) if hidden else (
            lambda c: '%s:%s:%d' % (c['id'], c['md5'], c['size']))
        if act == 'STOP':
            return None
        if act == 'RUN':
            return self.cmd('go')
        if act == 'POLL':
            return self.cmd('go')
        if act == 'WAIT':
            self.w.clock.advance(int(t[1].split('=')[1]))      # (a real wait, shortened: see W_ABS_TEST)
            return self.cmd('go')
        kv = {x.split('=', 1)[0]: x.split('=', 1)[1] for x in t[1:] if '=' in x and not x.startswith('--')}
        if act == 'ATTEST' and 'found' in t:
            at = t[t.index('--at') + 1]
            args = ['--at', at]
            if '--name' not in t:                                # a LIST answer
                for n, c in plist or []:
                    args += ['--file', '%s:%s' % (n, fmt(c))]
                if not plist:
                    args.append('--none')
                return self.cmd('found', *args)
            names = [t[i + 1] for i in range(len(t) - 1) if t[i] == '--name']
            got = dict(finds)
            for n in names:
                args += ['--name', n]
                if status.get(n) == 'refused':
                    args.append('--refused')
                cs = got.get(n, [])
                if not cs:
                    args.append('--none')
                for c in cs:
                    args += ['--file', fmt(c)]
            return self.cmd('found', *args)
        if 'ATTEST' in t:
            i = t.index('ATTEST')
            after = t[i + 1].split('=', 1)[1] if t[i + 1].startswith('after=') else None
            j = t.index('--at')
            at = t[j + 1]
            keys = [tuple(x.split('=', 1)) for x in t[j + 2:]]
            pre = (act, kv) if act != 'ATTEST' else None
            if after:
                self.attests_after.append((after, [k for k, _ in keys]))
            vals = self.answer(keys, pre, lines, after)
            return self.cmd('answer', '--at', at, *['%s=%s' % (k, vals[k]) for k, _ in keys])
        if act == 'OPEN_CONVERSATION':
            self.events.append(('OPEN', kv['role'], kv['prompt'], self.w.boot))
            self.open_conv(kv['role'], kv['prompt'], kv['folder'])
            return self.cmd('go')
        if act == 'AWAIT_CONVERSATION':
            self.events.append(('AWAIT', kv['role'], kv['conversation'], self.w.boot))
            return self.cmd('go')
        if act == 'CONTINUE_CONVERSATION':
            self.events.append(('CONTINUE', 'V', kv['message'], self.w.boot))
            self.continue_v(kv['conversation'])
            return self.cmd('go')
        if act == 'END_CONVERSATION':
            self.events.append(('END', kv['role'], kv.get('after'), self.w.boot))
            self.current = kv['role']
            return self.cmd('go')
        if act == 'EXPORT_TRANSCRIPT':
            self.events.append(('EXPORT', kv['role'], kv['to'], self.w.boot))
            self.current = kv['role']
            if self.policy['export']:
                Path(kv['to']).parent.mkdir(parents=True, exist_ok=True)
                Path(kv['to']).write_text(json.dumps({'invented': 'transcript', 'role': kv['role']}))
            return self.cmd('go')
        raise AssertionError('unknown action %r' % do)

    # ---- AI roles
    def new_conv(self, role):
        self.conv_n += 1
        c = 'conv-%08x' % (0x10000000 + self.conv_n)
        self.convs[role] = c
        return c

    def open_conv(self, role, prompt, folder):
        conv = self.new_conv(role)
        self.current = role
        self.live[role] = self.policy['role_writes']
        self.opened[role] = {'conv': conv, 'utc': real_utc(), 'prompt': prompt, 'folder': folder}
        if not self.policy['role_writes']:
            return
        time.sleep(1.05)                                       # the conversation takes time (times are in seconds)
        if role == 'G':
            write_response(Path(folder))
        elif role == 'S':
            jd = Path(folder).parents[1] if Path(folder).name == 'input' else Path(prompt).parents[1]
            self.w.write_scope_response(jd)
        elif role == 'V':
            write_review(Path(folder).parent, conv, self.policy['v'])

    def continue_v(self, conv):
        self.live['V'] = True
        time.sleep(1.05)
        s = self.w.state()                      # after a reset the Dot finds the folder from the job it runs
        jd = Path(self.opened['V']['folder']).parent if 'V' in self.opened else Path(s['runs'][s['current']]['job_dir'])
        write_review(jd, conv, self.policy['v_cont'])

    # ---- answers
    def answer(self, keys, pre, lines, after=None):
        w, pol = self.w, self.policy
        out = {}
        kd = dict(keys)
        if pre and pre[0] == 'DELIVER' and pre[1].get('to') == 'copy':
            return self.w.make_copy(pre[1]['file'])
        rs = pol['restore']
        for k, p in keys:
            if k == 'operator_model':
                out[k] = 'gpt-test-operator'
            elif k == 'platform':
                out[k] = 'test-platform'
            elif k == 'ended':
                out[k] = rs.get('ended', 'yes') if 'outcome' in kd or ('transcript' in kd and 'model' not in kd) \
                    else 'yes'
            elif k == 'conversation':
                out[k] = rs.get('conversation') or self.convs.get(self.cur_role(lines), 'conv-0fffffff')
            elif k in ('started_utc', 'ended_utc', 'opened_utc'):    # VM clock readings (§X.6.1)
                out[k] = self.opened.get(self.cur_role(lines), {}).get('utc') if k != 'ended_utc' else real_utc()
                out[k] = out[k] or real_utc()
            elif k == 'model':
                out[k] = 'stand-in-model'
            elif k == 'effort':
                out[k] = 'high'
            elif k == 'single_user_message':
                out[k] = 'yes'
            elif k in N.FEATURES:
                out[k] = 'no'
            elif k == 'tools':
                out[k] = 'none'
            elif k == 'transcript':
                if 'outcome' in kd or 'model' not in kd:
                    out[k] = rs.get('transcript', 'exported' if pol['export'] else 'not_available')
                else:
                    out[k] = 'exported' if pol['export'] else 'not_available'
            elif k == 'prompt_pasted':
                out[k] = 'yes'
            elif k == 'outcome':
                out[k] = rs.get('outcome') or ('WRITTEN' if self.live.get(self.current) else 'NO_CONVERSATION')
            elif k == 'list_shows_none':
                out[k] = rs.get('list_shows_none', pol['list_shows_none'])
            elif k in ('notified', 'asked', 'sent'):
                out[k] = 'yes'
            elif k == 'arrived':
                out[k] = pol['arrived']
            elif k == 'case':
                out[k] = w.everyday_request()
            else:
                raise AssertionError('unknown key %s' % k)
        if 'outcome' in kd or ('transcript' in kd and 'model' not in kd):
            self.answered.append(dict(out, role=self.current, after=after))
            self.live = {}
        elif 'ended' in kd:
            self.live[self.current] = False
        if 'model' in kd:                                         # the generator's final message
            fm = w.base / 'attest/final_message.txt'
            fm.parent.mkdir(parents=True, exist_ok=True)
            fm.write_text('Done: the invented response is in the output folder.\n')
        return out

    def cur_role(self, lines):
        hdr = ' '.join(lines)
        for r in ('G', 'S', 'V'):
            if ('role=%s ' % r) in hdr:
                return r
        return self.current

    # ---- a VM reset
    def reset(self, notes='hint'):
        """Everything but Drive is lost. notes: 'hint' (the last CPSV and CPSV-REPO lines survive), 'commit' (only
        the CPSV-REPO line), 'none' (step 0 of the README)."""
        w = self.w
        self.reset_calls.append(len(w.drive.calls))
        w.kill_boot()
        force_rmtree(w.base)
        w.new_boot()
        self.opened, self.convs, self.current = {}, dict(self.convs), None
        hint = None
        if notes == 'hint' and self.notes['cpsv']:
            h = dict(x.split('=', 1) for x in self.notes['cpsv'].split()[1:])
            if h['kit'] != 'none':
                hint = (h['head'], h['kit'])
        commit = self.notes['repo'] if notes != 'none' else None
        if commit is None:
            got = w.drive.find(N.FOLDERS['static'], 'VM2_RELEASE.md')
            if not got:                                   # README step 0: the Dot's own handback (§6.1)
                seen.scan(['DO: STOP SESSION_NO_COMMIT HANDBACK C'])
                return 3, ['DO: STOP SESSION_NO_COMMIT HANDBACK C']
            commit = w.drive.download(got[0]['id']).decode().split('commit: ', 1)[1].strip()
        return self.bootstrap(commit, hint)

    def bootstrap(self, commit, hint):
        w = self.w
        script = []
        for ln in readme_bootstrap():
            if ln.startswith('COMMIT='):
                ln = 'COMMIT=%s' % commit
            elif 'git clone' in ln:
                ln = '[ -d ~/cps/repo/.git ] || { mkdir -p ~/cps && ln -s %s ~/cps/repo; }' % shlex.quote(str(REPO))
            elif 'session_start.sh' in ln:
                ln = ln.replace(' [--hint <seq6> --kit <hex12>]', '')
                if hint:
                    ln += ' --hint %s --kit %s' % hint
            script.append(ln)
        p = subprocess.run(['bash', '-c', '\n'.join(script)], capture_output=True, text=True, env=w.env(),
                           timeout=600)
        lines = [ln for ln in p.stdout.splitlines() if ln]
        seen.scan(lines)
        self.boot_err = p.stderr
        self.blocks.append({'argv': ['session_start'], 'code': p.returncode, 'lines': lines, 'boot': w.boot})
        for ln in lines:
            if ln.startswith('CPSV-REPO commit='):
                self.notes['repo'] = ln.split('=', 1)[1]
        blk = [ln for ln in lines if not ln.startswith(('CPSV-REPO', 'CPSV-RUNNING'))]
        if blk and blk[0].startswith('CPSV '):
            assert drive.check_grammar(blk) is None, blk
        return p.returncode, blk


def check_printed(lines, case_ids=()):
    """L9: every printed token is ASCII, every absolute path round-trips through shlex, and a case id occurs only as a
    component of an absolute path (never a free token or an argument value)."""
    for ln in lines:
        assert ln.isascii(), 'L9: a non-ASCII printed line'
        for tok in shlex.split(ln):
            v = tok.split('=', 1)[1] if '=' in tok and not tok.startswith('/') else tok
            if v.startswith('/'):
                assert shlex.split(shlex.quote(v)) == [v] and ' ' not in v, 'L9: a path that does not round-trip'
                continue
            for c in case_ids:
                assert c not in v, 'L9: a case id outside a path: %s' % tok


def cache_files(v2):
    return {p.name: p.read_bytes() for p in Path(v2).glob('*.json')} if Path(v2).is_dir() else {}


# ================================================================ invented AI outputs
def write_response(folder):
    """G: the package's invented example response for this job (case id and inventory hash adapted)."""
    jd = folder.parents[1]
    case = jd.name
    inv = folder / 'input' / 'packet' / 'SOURCE_INVENTORY.json'
    r = json.loads((TCJ.PKG / 'resources/EXAMPLE_RESPONSE.json').read_text(encoding='utf-8'))

    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return case if x == 'EXAMPLE046F' else x
    r = walk(r)
    r['inventory_sha256'] = sha(inv.read_bytes())
    out = folder / 'output' / 'response.json'
    out.write_text(json.dumps(r, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def write_review(jd, conv, how):
    """V: a complete PASS review (or FAIL, or incomplete: one internal page dropped)."""
    rv = dict(TCJ.REVIEWER, conversation_id=conv)
    TCJ.stand_in_review(jd, fail=how == 'fail', drop_page=how == 'incomplete', reviewer=rv)


# ================================================================ the world
class World:
    """One invented VM world. series 'D1' (drill: qualification rules), 'Q1' or 'E1'. cases: list of
    (case_id, kind) with kind 'small', 'large' (scope stage) or 'nonattempt'."""
    def __init__(self, root, series='D1', gates=None, cases=(('9990101', 'small'), ('9990102', 'nonattempt')),
                 cfg=None, plant_pass=True):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.series, self.gates = series, dict(GATES, **(gates or {}))
        self.cases = list(cases)
        self.home = self.root / 'home'
        self.base, self.tools = self.home / 'cps', self.home / 'cps-tools'
        self.boot_path = self.root / 'boot_id'
        self.fixed = self.root / 'fixed'
        self.clock = Clock()
        self.drive = FakeDrive(self.gates)
        self.nboot, self.boot = 0, None
        self.env0 = dict(os.environ)
        self.saved = {}
        os.environ.update(self.env())
        self.clock_patch()
        self.seams = Seams()
        self.commit = subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True,
                                     text=True).stdout.strip()
        self.fixed.mkdir(parents=True, exist_ok=True)
        self.new_boot()
        self.cfg_over = cfg or {}
        self.kit = self.build_kit()
        self.drive.plant(N.FOLDERS['setup'], 'SESSION_KIT_%s.zip' % sha(self.kit)[:12], self.kit)
        self.drive.plant(N.FOLDERS['static'], 'VM2_RELEASE.md', ('commit: %s\n' % self.commit).encode())
        kn = 'SESSION_KIT_%s.zip' % sha(self.kit)[:12]            # §8.2 the FOLDER_MANIFEST route (zip row)
        self.drive.plant('CPS/cps_runtime', kn, self.kit)
        self.drive.plant(N.FOLDERS['static'], 'FOLDER_MANIFEST.md', (
            '# FOLDER_MANIFEST (invented test kit)\n\n| path | bytes | sha256 |\n|---|---|---|\n'
            '| `cps_runtime/%s` | %d | `%s` |\n' % (kn, len(self.kit), sha(self.kit))).encode())
        self.fp = v1reuse.fingerprint(v1reuse.Layout())[0]
        pdoc = {'schema': 'cps.vm-fingerprint-pass.v1', 'fingerprint_sha256': self.fp,
                'selftest': {'failed_count': 0, 'tests': 1, 'passed_count': 1}, 'invented': True}
        if plant_pass:
            self.drive.plant(N.FOLDERS['setup'], 'FINGERPRINT_PASS_%s.json' % self.fp, json.dumps(pdoc).encode())
        self.dot = FakeDot(self)
        self.everyday, self.kinds, self.inputs_saved = [], {}, {}

    # ---- environment
    def env(self):
        e = dict(os.environ)
        e.update({'HOME': str(self.home), 'CPS_VM_BASE': str(self.base), 'CPS_TOOLS': str(self.tools),
                  'CPS_VM_BOOT_ID_PATH': str(self.boot_path)})
        return e

    def clock_patch(self):
        from cpsvm2 import worker
        self.saved = {'w_abs': F.w_abs, 'sleep': worker.sleep}
        F.w_abs = lambda gates: W_ABS_TEST
        worker.sleep = lambda s: time.sleep(min(s, 0.2))

    def close(self):
        self.kill_boot()
        self.seams.close()
        F.w_abs = self.saved['w_abs']
        from cpsvm2 import worker
        worker.sleep = self.saved['sleep']
        os.environ.clear()
        os.environ.update(self.env0)

    def destroy(self):
        self.close()
        force_rmtree(self.root)

    def new_boot(self):
        self.nboot += 1
        self.boot = '%08x-0b0a-4908-8706-%012x' % (0x0f0e0d00 + self.nboot, self.nboot)
        self.boot_path.write_text(self.boot + '\n')
        self.simulate_setup()

    def simulate_setup(self):
        """What setup_vm_user.sh leaves in TOOLS for this boot (it is not run here; SAFE-07 is tested on its own)."""
        t = self.tools
        (t / 'var').mkdir(parents=True, exist_ok=True)
        (t / 'var/cps_vm2_setup_ok').write_text('%s %s\n' % (self.boot, self.commit))
        site = Path(importlib.util.find_spec('openpyxl').origin).resolve().parents[1]
        if not (t / 'builder-deps').exists():
            (t / 'builder-deps/private').mkdir(parents=True)
            os.symlink(site, t / 'builder-deps/private/deps')
        if not (t / 'playwright').exists():
            (t / 'playwright').mkdir(parents=True)
            os.symlink(NODE_PATH, t / 'playwright/node_modules')
        if not (t / 'nodelink').exists():
            (t / 'nodelink').mkdir()
            os.symlink(NODE, t / 'nodelink/node')

    def kill_boot(self):
        """A reset ends every process of the boot. Stages run in-process and runner commands in the foreground, so
        nothing of this boot outlives the command that the seam interrupted; only zombies are reaped."""
        reap()

    def in_session(self):
        """True while the session machine (§8) of this boot has not committed its RESTORE or GENESIS."""
        try:
            return json.loads((self.base / 'outbox/v2/RESTORE_WORK.json').read_text()).get('committed') is None
        except (OSError, ValueError):
            return True

    def jobs_tree(self):
        """(path, size, sha256) of every file under BASE/qual and BASE/jobs (the job folders a dead stage leaves)."""
        out = []
        for root in (self.base / 'qual', self.base / 'jobs'):
            for dp, dns, fns in os.walk(root):
                for n in fns:
                    p = os.path.join(dp, n)
                    if not os.path.islink(p):
                        out.append((p, os.path.getsize(p), sha(Path(p).read_bytes())))
        return sorted(out)

    def drive_snapshot(self):
        return {(f, n): [c['md5'] for c in cs] for f, fo in self.drive.folders.items() for n, cs in fo.items()}

    # ---- the kit
    def release_doc(self, extra=None):
        b, t = self.base, self.tools
        q = self.series[0] in 'QD'
        rel = {'schema': 'cps.release.v1', 'status': 'RELEASED_FOR_QUALIFICATION' if q else 'RELEASED_FOR_USE',
               'release_version': 'TEST-INVENTED-VM2',
               'repository': {'commit': self.commit, 'root': str(b / 'repo')},
               'package': {'path': 'research/guideline046_007/package',
                           'manifest_sha256': sha((TCJ.PKG / 'PACKAGE_MANIFEST.json').read_bytes())},
               'harness': {'path': 'research/guideline046_007/harness'},
               'source_prep': {'path': 'research/guideline046_003/source_prep', 'deps_bundle': str(t / 'builder-deps'),
                               'node_path': str(t / 'playwright/node_modules')},
               'writer': {'admission': TCJ.WRITER_ADMISSION,
                          'admission_sha256': sha((REPO / TCJ.WRITER_ADMISSION).read_bytes()),
                          'writer_dir': str(b / 'repo/deploy/writer_route/writer')},
               'checker_node': {'path': str(t / 'nodelink/node'), 'sha256': NODE_SHA},
               'admitted_checker_node_sha256': [NODE_SHA],
               'tables': {'glossary': {'path': str(b / 'runtime/tables/GLOSSARY.json'), 'sha256': self.gloss_sha},
                          'brand_table': None, 'company_name_sha256': sha(TCJ.COMPANY.encode('utf-8'))},
               'pinned_files_sha256': {p: sha((REPO / p).read_bytes()) for p in TCJ.EXECUTED},
               'vm_helper': {'series': self.series, 'tree_sha256': host.helper_tree_sha256()}}
        if q:
            rel['qualification'] = {'admissions': [{'path': str(b / 'runtime/qualification/ADMISSION_VM2.json'),
                                                    'sha256': self.adm_sha}],
                                    'ledger': str(b / 'ledger/LEDGER.jsonl'),
                                    'jobs_file': str(b / 'runtime/qualification/JOBS.json')}
        rel.update(extra or {})
        return rel

    def config_doc(self, **over):
        c = {'schema': 'cps.vm2-config.v1', 'series': self.series,
             'accepted_helper_tree_sha256': [host.helper_tree_sha256()], 'accepts_release_sha256': [],
             'selftest_expected_tests': 1, 'clock_wait_max_seconds': 300, 'foreground_hold_seconds': 1200,
             'stage_max_seconds': dict(STAGE_MAX), 'max_upload_bytes': 50000000,
             'png_part_bytes': 1000000, 'max_entry_bytes': 50000000, 'max_transcript_bytes': 20000000,
             'max_ai_output_bytes': 20000000, 'conversation_re': CONV_RE, 'transcript_ext': 'json',
             'drive_id_re': r'[A-Za-z0-9_-]{20,80}', 'gates': self.gates, 'clear': None,
             'doc_samples': readme_samples() + ['conv-EXAMPLE']}
        c.update(self.cfg_over)
        c.update(over)
        return c

    def build_kit(self, rel_extra=None, cfg_over=None):
        """The kit zip: RELEASE.json, VM_HELPER_CONFIG.json, tables/, qualification/ (Q, D)."""
        st = self.fixed / 'kitsrc'
        if st.exists():
            force_rmtree(st)
        st.mkdir(parents=True)
        mem = {}
        rt = self.base / 'runtime'
        src = st / 'src.xlsx'
        gloss = TCJ.small_workbook(src)
        mem['tables/GLOSSARY.json'] = (json.dumps(gloss, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
        self.gloss_sha = sha(mem['tables/GLOSSARY.json'])
        q = self.series[0] in 'QD'
        if q:
            jobs = {'schema': 'cps.qualification-jobs.v1', 'meaning': 'INVENTED test jobs list', 'cases': []}
            for i, (case, kind) in enumerate(self.cases, 1):
                row = {'case_id': case, 'order': i, 'nonattempt': kind == 'nonattempt'}
                if kind == 'nonattempt':
                    row['reason'] = 'NONATTEMPT_SOURCE_UNAVAILABLE'
                jobs['cases'].append(row)
            mem['qualification/JOBS.json'] = (json.dumps(jobs, indent=1) + '\n').encode()
            files = {'package_manifest': TCJ.PKG / 'PACKAGE_MANIFEST.json',
                     'route': TCJ.PKG / 'tools/cps046b_route.py'}
            for case, kind in self.cases:
                if kind == 'nonattempt':
                    continue
                m = self.job_members(case, kind, rt / 'qualification/jobs' / case)
                for k, v in m.items():
                    mem['qualification/jobs/%s/%s' % (case, k)] = v
                    p = st / case / k
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(v)
                files['job_' + case] = st / case / 'JOB.json'
                files['job_title_' + case] = st / case / 'JOB_TITLE.json'
                files['source_' + case] = st / case / 'source.xlsx'
            (st / 'GLOSSARY.json').write_bytes(mem['tables/GLOSSARY.json'])
            (st / 'JOBS.json').write_bytes(mem['qualification/JOBS.json'])
            files['glossary'] = st / 'GLOSSARY.json'
            files.update({k: REPO / k for k in TCJ.ADMISSION_TOOL_LABELS})
            files['JOBS.json'] = st / 'JOBS.json'
            cp = st / 'ADMISSION_CONFIG.json'
            cp.write_text(json.dumps({'files': {k: str(v) for k, v in files.items()},
                                      'plan': {'candidate': '046g', 'note': 'invented vm2 test admission'}}))
            subprocess.run([sys.executable, '-I', '-B', str(TCJ.HARNESS / 'freeze_admission.py'), '--config', str(cp),
                            '--out', str(st / 'ADMISSION_VM2.json')], check=True, capture_output=True)
            mem['qualification/ADMISSION_VM2.json'] = (st / 'ADMISSION_VM2.json').read_bytes()
            self.adm_sha = sha(mem['qualification/ADMISSION_VM2.json'])
            time.sleep(1.1)                                    # the admission is frozen before the first prepare
        mem['RELEASE.json'] = (json.dumps(self.release_doc(rel_extra), ensure_ascii=False, indent=1) + '\n').encode()
        mem['VM_HELPER_CONFIG.json'] = (json.dumps(self.config_doc(**(cfg_over or {})), indent=1) + '\n').encode()
        return zip_kit(mem)

    def job_members(self, case, kind, dest):
        """JOB.json, JOB_TITLE.json and source.xlsx of an invented job whose files will live in `dest`."""
        tmp = self.fixed / ('src_%s.xlsx' % case)
        if kind == 'large':
            self.large_end_row = TCJ.large_workbook(tmp)
        else:
            TCJ.small_workbook(tmp)
        job = {'schema': 'cps.job-config.v2', 'case_id': case, 'customer_name': TCJ.CUSTOMER,
               'project_name': TCJ.PROJECT, 'company_name': TCJ.COMPANY,
               'glossary_path': str(self.base / 'runtime/tables/GLOSSARY.json'), 'source_path': str(dest / 'source.xlsx'),
               'source_kind': '材料清單', 'carrier_path': 'X:\\Fixtures\\invented\\%s-material-list.xlsx' % case}
        title = {'schema': 'cps.job-title.v1', 'case_id': case, 'job_title': '%s示例公司-示例案' % case}
        return {'JOB.json': (json.dumps(job, ensure_ascii=False, indent=1) + '\n').encode('utf-8'),
                'JOB_TITLE.json': (json.dumps(title, ensure_ascii=False, indent=1) + '\n').encode('utf-8'),
                'source.xlsx': tmp.read_bytes()}

    def write_scope_response(self, jd):
        TCJ.scope_reader_response(jd, jd.name, end=self.large_end_row)

    # ---- everyday
    def everyday_request(self):
        """The case of the next everyday request; its three input files are put in everyday_inputs/<case>/."""
        case = '9990%03d' % (201 + len(self.everyday))
        self.everyday.append(case)
        d = self.base / 'everyday_inputs' / case
        d.mkdir(parents=True, exist_ok=True)
        self.inputs_saved[case] = self.job_members(case, 'small', d)
        for k, v in self.inputs_saved[case].items():
            (d / k).write_bytes(v)
        return case

    def restore_inputs(self):
        """The Dot still has the user's three files (in its chat) and puts them back into everyday_inputs/<case>/
        after a reset; False when there is nothing to put back or they are already there."""
        put = False
        for case, mem in self.inputs_saved.items():
            d = self.base / 'everyday_inputs' / case
            for k, v in mem.items():
                if not (d / k).is_file():
                    d.mkdir(parents=True, exist_ok=True)
                    (d / k).write_bytes(v)
                    put = True
        return put

    def drive_state(self):
        """The fold state of the newest entry on FakeDrive (the test's side), or None."""
        from cpsvm2.vio import savepoint
        names = self.head_entries()
        if not names:
            return None
        p = self.fixed / ('.state_' + names[-1])
        p.write_bytes(self.drive.bytes_of(N.series_folder(self.series), names[-1]))
        try:
            return savepoint.read_entry(p)['state']
        finally:
            os.unlink(p)

    def make_copy(self, standard):
        """The Dot's personal copy (DEPLOYMENT_MODEL layout) and its log."""
        st = Path(standard).read_bytes()
        hdr = next(b['lines'][0] for b in reversed(self.dot.blocks) if b['lines'] and b['lines'][0].startswith('CPSV'))
        u = host.utc14(self.clock.now())
        cur = json.loads((self.base / 'outbox/v2/STATE.json').read_text())['state']['current']
        case = cur.split('/', 1)[1]
        d = self.home / 'cps-deliveries' / case / 'user01' / u
        d.mkdir(parents=True, exist_ok=True)
        (d / 'PERSONAL_COPY.xlsx').write_bytes(st + b'')
        (d / 'PERSONALIZATION_LOG.json').write_text(json.dumps({
            'schema': 'cps.personal-copy-log.v1', 'standard_file': {'sha256': sha(st)},
            'profile_folder': 'Dots Folder/profiles/user01', 'invented': hdr[:4]}))
        return {'copy': str(d / 'PERSONAL_COPY.xlsx'), 'log': str(d / 'PERSONALIZATION_LOG.json')}

    # ---- driving
    def start(self, hint_seq='000000'):
        """The first session of a series: the maintainer gave the commit and the kit; no head yet."""
        self.dot.notes['repo'] = self.commit
        return self.dot.bootstrap(self.commit, (hint_seq, sha(self.kit)[:12]))

    def cache(self):
        p = self.base / 'outbox/v2/STATE.json'
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return None

    def state(self):
        return (self.cache() or {}).get('state')

    def case_ids(self):
        return [c for c, _ in self.cases] + list(self.everyday)

    # ---- snapshots (the job-state cache of §14.2: a world forked at a block, at the same absolute paths)
    def snapshot(self, dest):
        dest = Path(dest)
        force_rmtree(dest)
        dest.mkdir(parents=True)
        shutil.copytree(self.home, dest / 'home', symlinks=True)
        d = self.dot
        return {'dir': dest, 'drive': copy.deepcopy(self.drive), 'offset': self.clock.offset, 'nboot': self.nboot,
                'boot': self.boot, 'everyday': list(self.everyday), 'kinds': dict(self.kinds),
                'inputs_saved': dict(self.inputs_saved),
                'dot': copy.deepcopy({k: getattr(d, k) for k in DOT_FIELDS})}

    def restore(self, snap):
        self.kill_boot()
        force_rmtree(self.home)
        shutil.copytree(snap['dir'] / 'home', self.home, symlinks=True)
        self.drive = copy.deepcopy(snap['drive'])
        self.nboot, self.boot, self.everyday = snap['nboot'], snap['boot'], list(snap['everyday'])
        self.kinds = dict(snap['kinds'])
        self.inputs_saved = dict(snap['inputs_saved'])
        self.boot_path.write_text(self.boot + '\n')
        for k, v in copy.deepcopy(snap['dot']).items():
            setattr(self.dot, k, v)
        self.dot.hook = None

    # ---- the maintainer side over FakeDrive's internal table (oracles O4, O5)
    def maint_inputs(self, d):
        d = Path(d)
        force_rmtree(d)
        for sub, folder in (('dl', N.series_folder(self.series)), ('setup', N.FOLDERS['setup'])):
            rows = self.drive.listing(folder)
            if sub == 'dl':                                   # DELIV/DLOG parts live in profile folders (§11.3)
                for f in self.drive.folders:
                    if f.endswith('/deliveries'):
                        rows += self.drive.listing(f)
            for r in rows:
                p = d / sub / r['id'] / r['name']
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(self.drive.blobs[r['id']])
            (d / (sub + '.json')).write_text(json.dumps(rows))
        return d

    def audit(self, d):
        from cpsvm2.maint import audit as A
        d = self.maint_inputs(d)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = A.main(['--series', self.series, '--listing', str(d / 'dl.json'), '--dir', str(d / 'dl'),
                           '--setup-listing', str(d / 'setup.json'), '--setup-dir', str(d / 'setup'),
                           '--out', str(d / 'AUDIT.json')])
        rep = json.loads((d / 'AUDIT.json').read_text()) if (d / 'AUDIT.json').is_file() else None
        return code, rep, out.getvalue()

    def assemble(self, d, verify=True, root='/'):
        """O5: assemble at the original absolute paths (root '/', after BASE is wiped): the runner keys its ledger by
        the job folder path (R25), so verify-frozen holds only there."""
        from cpsvm2.maint import assemble as AS
        d = Path(d)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = AS.main(['--series', self.series, '--dir', str(d / 'dl'), '--root', root,
                            '--out', str(d / 'ASSEMBLE.json')] + (['--verify-frozen'] if verify else []))
        rep = json.loads((d / 'ASSEMBLE.json').read_text()) if (d / 'ASSEMBLE.json').is_file() else None
        return code, rep, out.getvalue()

    def all_frozen(self):
        """ALL_FROZEN.json from the FINAL part on FakeDrive, or None."""
        fo = self.drive.folders.get(N.series_folder(self.series), {})
        for n, cs in fo.items():
            if '_ALLFZ01' in n and cs:
                return json.loads(self.drive.blobs[cs[0]['id']])
        return None

    def head_entries(self):
        return sorted(n for n in self.drive.folders.get(N.series_folder(self.series), {}) if n.endswith('.tgz'))


def zip_kit(mem):
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, 'w') as z:
        for k, v in sorted(mem.items()):
            zi = zipfile.ZipInfo(k, (2026, 1, 1, 0, 0, 0))
            zi.external_attr = 0o644 << 16
            z.writestr(zi, v)
        sums = ''.join('%s  %s\n' % (sha(v), k) for k, v in sorted(mem.items()))
        zi = zipfile.ZipInfo('SHA256SUMS', (2026, 1, 1, 0, 0, 0))
        zi.external_attr = 0o644 << 16
        z.writestr(zi, sums)
    return zb.getvalue()


def reap():
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def force_rmtree(p):
    p = Path(p)
    if not os.path.lexists(p):
        return
    if p.is_symlink() or not p.is_dir():
        os.unlink(p)
        return
    for dp, dns, fns in os.walk(p):
        for n in dns:
            q = os.path.join(dp, n)
            if not os.path.islink(q):
                os.chmod(q, 0o755)
    os.chmod(p, 0o755)
    shutil.rmtree(p)


def chmod_w(p):
    os.chmod(p, stat.S_IMODE(os.lstat(p).st_mode) | 0o200)
