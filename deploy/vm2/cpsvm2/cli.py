"""go / found / answer (spec §6), the glue that imports core/ and vio/. It carries out the Steps that core returns
(session_next §8, next_action §7.1) and decides nothing about the journal itself: every transition is the fold's.

Command prologue (§2.5, §X.6.7): layout check, HelperLock (busy: the CPSV-BUSY block, exit 4), cache validation, the
FOREGROUND check (a dead stage of this boot), cleanup, sticky HALT. Then the loop: a pending commit first (§5), the
session machine until RESTORE_WORK.phase is DONE (§8), then next_action. Only `go` runs a stage, in the foreground of
this process, holding the lock for the whole stage (§X.7.2); `found` and `answer` print `DO: RUN ... go` instead.
Exit codes: 0 follow the block, 3 the block ends in DO: STOP, 4 refused (state unchanged), 2 usage.

Sections: environment and cache; printing; entry drafts and commits; pending commit; prologue; found; answer; the
loop; session glue (§8 I/O phases); answers (§6.5); plan commits (CLEAR, FINAL); foreground stages."""
import errno
import os
import re
import secrets
import shlex
from pathlib import Path

from .core import entry as E
from .core import fold as F
from .core import names as N
from .core import outcome as O
from .core import plan as P
from .core import session as S
from .core.step import Ask, Commit, Halt as HaltStep, Place, PrintBlock, Reupload, RunChain, Stop
from .vio import durable, drive, host, place, runner, savepoint
from .vio.v1compat import Block, Halt
from .vio.v1mod import check_layout_release, cleanup_leftovers, session_kit
from .vio.v1reuse import (HelperLock, Layout, check_layout_basic, clock_check, current_boot_id, fingerprint,
                          kit_members, md5_file, now_dt, parse_utc, remove_tree, sha_bytes, sha_file, sjson,
                          unpack_kit, validate_pass)

WORK_SCHEMA, BLOCK_SCHEMA, HALT_SCHEMA = 'cps.vm2-restore-work.v1', 'cps.vm2-block.v1', 'cps.vm2-halt.v1'
FG_SCHEMA = 'cps.vm2-foreground.v1'
NOT_STICKY = ('FINAL', 'RELEASE_GATE_OPEN')
SETUP_DONE, SETUP_FAILED = 'var/cps_vm2_setup_ok', 'var/cps_vm2_setup_failed'
DEFAULT_GATES = {'p2_md5_visible': 'no'}        # before a kit config is read: this platform's md5-hidden mode (§X.5.5)
BARE_HDR = 'CPSV series=none head=000000 kit=none at=000000-0000-000000 mode=setup state='


class Out(Exception):
    """Ends a command with an exit code, after its block is printed."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


# ================================================================ environment and cache (§2)
class Env:
    def __init__(self, lay, lock):
        self.lay, self.lock, self.p = lay, lock, host.Paths(lay)
        self.v2, self.journal, self.boot = self.p.v2, self.p.journal, current_boot_id()
        self.cfg = self.release = self.rel_raw = self.series = None
        self.mode, self.command = 'setup', 'go'
        self.cache = self.pending = self.block = self.work = None
        cp = lay.config_path
        if cp.is_file():
            self.adopt(cp.read_bytes(), lay.release_path.read_bytes() if lay.release_path.is_file() else b'{}')

    def adopt(self, cfg_raw, rel_raw):
        """The kit config and release in use (BASE/runtime, or the kit being taken in by the session)."""
        self.rel_raw = rel_raw
        try:
            self.release = sjson(rel_raw)
        except (ValueError, UnicodeDecodeError):
            raise Halt('STOP', 'CONFIG_INVALID', 'RELEASE.json')
        self.cfg = host.load_config(cfg_raw, self.release, N.check_config_patterns, N.UPLOAD_CAP_BYTES, N.STAGE_KEYS)
        self.series = self.cfg['series']
        self.mode = N.mode_of(self.series) if self.release.get('status') in (
            'RELEASED_FOR_QUALIFICATION', 'RELEASED_FOR_USE') else 'setup'

    def now(self):
        return host.now()

    @property
    def gates(self):
        return (self.cfg or {}).get('gates') or DEFAULT_GATES

    @property
    def upload_cfg(self):
        """The config the setup-file loop reads; before a kit is read, the cap alone (§X.3)."""
        return self.cfg or {'max_upload_bytes': N.UPLOAD_CAP_BYTES}

    @property
    def series_folder(self):
        return N.series_folder(self.series)

    @property
    def state(self):
        return (self.cache or {}).get('state')

    def head_seq(self):
        return ((self.cache or {}).get('head') or {}).get('seq') or 0

    def ctx2(self):
        return host.Ctx2(self.lay, self.cfg or {'clock_wait_max_seconds': 300, 'selftest_expected_tests': 0})

    def known_ids(self, name):
        """Rule V's id shortcut (§X.5.5 step 5): the Drive ids already recorded for `name` (state.files, the head)."""
        c = self.cache or {}
        ids = {x[0] for x in ((self.state or {}).get('files') or {}).get(name) or []}
        if (c.get('head') or {}).get('name') == name:
            ids.add(c['head']['id'])
        return ids

    def idcfg(self, case=''):
        c = self.cfg or {}
        return {'drive_id_re': c.get('drive_id_re'), 'conversation_re': c.get('conversation_re') or r'(?!)',
                'doc_samples': c.get('doc_samples') or [], 'home': self.lay.home or '', 'case': case}

    def file_id(self, name):
        """A confirmed journal file's first Drive id (state.files, or the head itself)."""
        c = self.cache or {}
        if (c.get('head') or {}).get('name') == name:
            return c['head']['id']
        for cf in c.get('confirms') or []:
            if cf['name'] == name and cf['copies']:
                return cf['copies'][0]['id']
        got = (self.state or {}).get('files', {}).get(name)
        return got[0][0] if got else None


def load_cache(env):
    """§2.5 steps 1-2; a failure moves every cache file to outbox/v2/invalid_<utc14>/ (never deleted)."""
    env.v2.mkdir(parents=True, exist_ok=True)
    docs, bad = {}, False
    for k, path, schema in (('cache', env.p.state, savepoint.STATE_SCHEMA),
                            ('pending', env.p.pending, savepoint.PENDING_SCHEMA),
                            ('block', env.p.block, BLOCK_SCHEMA), ('work', env.p.work, WORK_SCHEMA)):
        d, why = durable.read_doc(path, schema, sjson)
        bad = bad or why is not None
        docs[k] = d
    st, pe, bl, wk = docs['cache'], docs['pending'], docs['block'], docs['work']
    hs = ((st or {}).get('head') or {}).get('seq') or 0
    if st is not None:
        bad = bad or st.get('boot_id') != env.boot or (st.get('state') is not None and (
            st.get('state_sha256') != N.sha(N.cjson(st['state'])) or hs != st['state']['seq']))
    if pe is not None:
        bad = bad or st is None or pe.get('seq') != hs + 1
    if bl is not None and st is not None:
        bad = bad or bl.get('head_seq') != hs
    if wk is not None:
        bad = bad or wk.get('boot_id') != env.boot
    if bad:
        dest = env.v2 / ('invalid_' + host.utc14(env.now()))
        dest.mkdir(parents=True, exist_ok=True)
        for p in (env.p.state, env.p.pending, env.p.block, env.p.work):
            if p.exists():
                os.replace(p, dest / p.name)
        st = pe = bl = wk = None
    env.cache, env.pending, env.block, env.work = st, pe, bl, wk


def save_cache(env):
    env.cache = durable.write_doc(env.p.state, dict(env.cache, written_utc=env.now()))


def save_work(env):
    env.work = durable.write_doc(env.p.work, env.work)


def new_work(env):
    hint = {}
    if env.p.hint.is_file():
        try:
            hint = sjson(env.p.hint.read_bytes())
        except (ValueError, UnicodeDecodeError):
            hint = {}
    env.work = {'schema': WORK_SCHEMA, 'boot_id': env.boot, 'phase': 'LAYOUT', 'done': [], 'operator': None,
                'hint': {'seq': int(hint['seq']) if hint.get('seq') else None, 'kit': hint.get('kit')},
                'lookups': [], 'listing': None, 'head': None, 'head_error': None, 'identity': None, 'kit': None,
                'head_kit': None, 'list_shows_none': None, 'resolve': {}, 'placed': False, 'placed_list': [],
                'reuploaded': False, 'committed': None, 'fetched': {}, 'fingerprint': None, 'pass': None,
                'setup_loop': None, 'selftest_dir': None, 'selftest_died': False, 'kit_route': None}
    save_work(env)


# ================================================================ printing (§6.1)
def basis(env):
    return N.sha(N.cjson([(env.cache or {}).get('self_sha256'), (env.pending or {}).get('self_sha256'),
                          (env.work or {}).get('self_sha256')]))


def emit(env, state_code, blk, expect, refused=None):
    """Print one block and record it in BLOCK.json (durably, before printing). Raises Out(exit)."""
    if refused is not None and env.block is not None:
        lines = env.block['lines'][:1] + ['REFUSED ' + refused] + env.block['lines'][1:]
        print('\n'.join(lines), flush=True)
        raise Out(4)
    lines = render(env, state_code, blk, expect)
    print('\n'.join(lines), flush=True)
    raise Out(3 if blk.do[0] == 'STOP' else 0)


def render(env, state_code, blk, expect):
    """The block's lines with its --at; BLOCK.json is written durably before the caller prints them."""
    body = drive.body_lines(blk, str(env.lay.vm))
    hs, old = env.head_seq(), env.block
    step = 1
    if old is not None and old.get('head_seq') == hs:
        step = old['step'] if old.get('template') == body else old['step'] + 1
    if step > 9999:
        raise Halt('STOP', 'INTERNAL_STEP_OVERFLOW', 'too many blocks at one head')
    at = N.at_string(hs, step, (env.cache or {}).get('state_sha256') or basis(env),
                     (env.pending or {}).get('self_sha256'), body)
    kit = (env.cache or {}).get('kit_sha256') or ((env.work or {}).get('kit') or {}).get('sha256')
    lines = [drive.header(env.series or 'none', hs, kit, at, env.mode, state_code)] + \
        [ln.replace(drive.AT_MARK, at) for ln in body]
    if drive.check_grammar(lines):
        raise Halt('STOP', 'INTERNAL_PRINT', 'a block breaks the grammar')
    if os.path.isdir(env.v2):
        env.block = durable.write_doc(env.p.block, {
            'schema': BLOCK_SCHEMA, 'at': at, 'step': step, 'head_seq': hs, 'state_code': state_code, 'lines': lines,
            'template': body, 'expect': expect, 'basis': basis(env), 'printed_utc': env.now()})
    return lines


def stop_block(env, code, handback='C'):
    """A STOP block; local sticky (HALT.json) unless the code derives from the journal or the gates (§13.2)."""
    if code not in NOT_STICKY and not code.startswith('HALTED_') and os.path.isdir(env.v2) and handback == 'C':
        durable.write_doc(env.p.halt, {'schema': HALT_SCHEMA, 'series': env.series, 'code': code,
                                       'head_seq': env.head_seq(), 'detail': {}, 'created_utc': env.now()})
    emit(env, 'FINAL' if code == 'FINAL' else 'STOP',
         PrintBlock('STOP', do=('STOP', {'code': code, 'handback': handback})), {'command': 'none'})


def wait_out(env, seconds, code='WORK'):
    emit(env, code, PrintBlock(code, do=('WAIT', {'seconds': int(max(1, seconds))})), {'command': 'go'})


def bare(lines, code):
    print('\n'.join(lines), flush=True)
    raise Out(code)


def refuse(env, code):
    if env.block is None:
        bare(['REFUSED ' + code], 4)
    emit(env, env.block['state_code'], PrintBlock('X'), env.block['expect'], refused=code)


# ================================================================ entry drafts and commits (§3.4, §5.1 steps 1-4)
def draft(env, kind, body, seq=None):
    seq = seq or env.head_seq() + 1
    c = env.cache or {}
    return {'schema': E.SCHEMA, 'series': env.series, 'seq': seq, 'name': N.entry_name(env.series, seq),
            'kind': kind, 'body': body, 'utc': env.now(), 'boot_id': env.boot, 'uid': os.getuid(),
            'home': env.lay.home, 'fingerprint_sha256': c.get('fingerprint_sha256'),
            'helper': {'version': N.HELPER_VERSION, 'tree_sha256': host.helper_tree_sha256()},
            'runner_sha256': N.RUNNER_SHA256, 'kit_sha256': c.get('kit_sha256'),
            'release_sha256': sha_bytes(env.rel_raw), 'cleared_local': c.get('cleared_local')}


def completer(env):
    """§5.1 step 2: confirms, prev_sha256, the fold; an illegal transition is STOP INTERNAL_ILLEGAL_TRANSITION."""
    def complete(entry):
        c = env.cache or {}
        entry['confirms'] = (c.get('confirms') or []) if entry['seq'] > 1 else []
        entry['prev_sha256'] = (c.get('head') or {}).get('sha256') if entry['seq'] > 1 else None
        try:
            st = F.apply(env.state, entry)
        except F.ChainInvalid as e:
            raise Halt('STOP', 'INTERNAL_ILLEGAL_TRANSITION', 'the fold refused the entry', detail={'row': e.code})
        entry['state'], entry['state_sha256'] = st, E.state_sha256(st)
        if E.validate_entry(entry, cfg={'series': env.series,
                                        'accepted_helper_tree_sha256': env.cfg['accepted_helper_tree_sha256']}):
            raise Halt('STOP', 'INTERNAL_ILLEGAL_TRANSITION', 'the entry is not valid')
        return entry
    return complete


def commit(env, d, members=(), parts=(), post=(), png=None):
    d = dict(d, payload_png=png)
    pend, entry, _ = savepoint.write_commit(env, d, list(members), list(parts), list(post), completer(env))
    env.pending = pend
    if env.cache is not None and env.cache.get('cleared_local'):
        env.cache['cleared_local'] = None
        save_cache(env)
    return entry


def tmember(name, text):
    return (name, 'file', 0o644, text.encode('utf-8'))


def roots_of(members):
    have = {m[0] for m in members}
    return [(r, 'dir', 0o755, None) for r in sorted({m[0].split('/')[0] for m in members}) if r not in have]


def commit_halt(env, code, detail=None):
    commit(env, draft(env, 'HALT', {'code': code, 'detail': detail or {}, 'head_seq': env.head_seq()}))


# ================================================================ pending commit (§5.1 steps 5-8)
def pending_step(env):
    b = savepoint.block(env, env.pending)
    if b is None:
        finish_commit(env)
        return
    env.pending = durable.write_doc(env.p.pending, env.pending)
    ups, finds, dls, do, names = b
    exp = {'command': 'found', 'names': names, 'kind': 'pending', 'uploaded': do[1]['uploaded']} \
        if do[0] == 'ATTEST_FOUND' else {'command': 'go', 'kind': 'pending'}
    emit(env, 'SAVE', PrintBlock('SAVE', uploads=ups, finds=finds, downloads=dls, do=do), exp)


def finish_commit(env):
    pend = env.pending
    env.cache = savepoint.finish(env, env.cache, pend)
    env.pending = None
    if env.work is not None and env.work.get('committed') is None and env.work.get('phase') != 'DONE':
        e = pend['entry']
        env.work['committed'] = {'seq': pend['seq'], 'md5': e['md5'], 'utc': env.now(), 'sha256': e['sha256'],
                                 'bytes': e['bytes'], 'ids': [c[0] for c in e['copies']]}
        save_work(env)
    run_post(env)


def run_post(env):
    """§5.4: each post action in order, removed from STATE.post durably as it completes."""
    while env.cache.get('post'):
        act = env.cache['post'][0]
        try:
            if act[0] == 'EVICT':
                place.evict(env.lay, act[1], act[2], act[3], act[4])
            elif act[0] == 'UNPLACE_FROZEN':
                place.unplace_frozen(act[1], act[2])
            elif act[0] == 'DROP_LOCAL':
                keep = env.lay.inbox / 'journal'
                keep.mkdir(parents=True, exist_ok=True)
                for p in act[1]:
                    if os.path.lexists(p) and p.endswith('.tgz'):
                        os.replace(p, keep / Path(p).name)       # kept for this boot's consumers and placements
                    elif os.path.lexists(p):
                        os.unlink(p)
            elif act[0] in ('DROP_ATTEST', 'DROP_DOWNLOADS'):
                for p in act[1]:
                    if os.path.lexists(p):
                        remove_tree(p)
        except OSError:
            raise Halt('STOP', 'POST_ACTION_FAILED', 'a post-commit action failed')
        env.cache['post'] = env.cache['post'][1:]
        save_cache(env)


# ================================================================ prologue and dispatch (§6.7)
def main(argv):
    if not argv or argv[0] not in ('go', 'found', 'answer'):
        print('usage: vm2.py go | found --at A ... | answer --at A k=v ...')
        return 2
    lay = Layout()
    try:
        check_layout_basic(lay)
        host.layout_paths_ok(lay)
    except Halt as h:
        print(BARE_HDR + 'STOP\nDO: STOP %s HANDBACK C' % h.code)
        return 3
    try:
        lock = HelperLock(lay, wait=10)
        lock.__enter__()
    except Halt:
        return busy(lay)
    try:
        return run_command(lay, lock, argv)
    finally:
        lock.release()


def busy(lay):
    """§X.6.2: another helper command holds the lock (a foreground stage, normally). FOREGROUND.json is read without
    the lock (unreadable or absent: none); nothing changes; exit 4."""
    kind = since = 'none'
    try:
        d = sjson((lay.base / 'outbox/v2/FOREGROUND.json').read_bytes())
        if isinstance(d, dict) and d.get('kind') in ('selftest', 'place', 'chain') and N.fm(N.UTC_S,
                                                                                         d.get('started_utc')):
            kind, since = d['kind'], d['started_utc']
    except (OSError, ValueError, UnicodeDecodeError):
        pass
    print('CPSV-BUSY kind=%s since=%s\nREFUSED HELPER_BUSY\nDO: POLL' % (kind, since), flush=True)
    return 4


def run_command(lay, lock, argv):
    try:
        env = Env(lay, lock)
    except Halt as h:                                   # an invalid kit config (CONFIG_INVALID): nothing else runs
        print(BARE_HDR + 'STOP\nDO: STOP %s HANDBACK C' % h.code)
        return 3
    env.command = argv[0]
    try:
        load_cache(env)
        foreground_check(env)
        cleanup_leftovers(lay)
        w = env.work
        if w and w.get('phase') != 'DONE' and 'CONFIG' in w['done'] and w.get('installed') != w['kit']['sha256']:
            m = kit_members(w['kit']['path'])               # the kit being taken in, before it is installed
            env.adopt(m['VM_HELPER_CONFIG.json'], m['RELEASE.json'])
        sticky_halt(env)
        if argv[0] == 'go':
            if len(argv) > 1:
                bare((env.block or {}).get('lines') or ['usage: vm2.py go'], 2)
            go_checks(env)
        elif argv[0] == 'found':
            do_found(env, argv[1:])
        else:
            do_answer(env, argv[1:])
        advance(env)
    except Out as o:
        return o.code
    except durable.DurableError as e:
        return safe_stop(env, e.code)
    except Halt as h:
        kind, code = host.halt_code(h)
        try:
            if kind == 'wait':
                wait_out(env, code or 30)
            if code in N.CODES_HALT and env.state is not None and env.pending is None \
                    and env.state['phase'] == 'OPEN' and (env.work or {}).get('phase') == 'DONE':
                commit_halt(env, code)
                pending_step(env)
            stop_block(env, code)
        except Out as o:
            return o.code
        except (Halt, durable.DurableError) as h2:
            return safe_stop(env, getattr(h2, 'code', 'WRITE_FAILED'))
    return 0


def safe_stop(env, code):
    try:
        stop_block(env, code)
    except Out as o:
        return o.code
    except (Halt, durable.DurableError, OSError):
        print(BARE_HDR + 'STOP\nDO: STOP %s HANDBACK C' % code)
        return 3


def sticky_halt(env):
    """§13.3: a local sticky HALT is printed by every command of this boot. (Clearing it in the same boot by a
    config-only kit, §13.5, is not built: see the build report.)"""
    h, why = durable.read_doc(env.p.halt, HALT_SCHEMA, sjson)
    if h is None and why is None:
        return
    code = (h or {}).get('code') or 'UNCLASSIFIED'
    emit(env, 'STOP', PrintBlock('STOP', do=('STOP', {'code': code, 'handback': 'C'})), {'command': 'none'})


def foreground_check(env):
    """§X.7.2 step 4: a FOREGROUND.json found under the lock means its writer died. Another boot's (or an unreadable
    one) is an invalid cache file, moved aside like the cache (§2.5). This boot's: a self-test at attempt 1 is moved to
    dead_<utc14>.json and runs again at attempt 2; anything else is a local sticky STOP FOREGROUND_DIED (SELFTEST_DIED
    for a self-test at attempt 2). The job folder is left untouched for the maintainer."""
    fg, why = durable.read_doc(env.p.foreground, FG_SCHEMA, sjson)
    if fg is None and why is None:
        return
    if fg is None or fg.get('boot_id') != env.boot:
        dest = env.v2 / ('invalid_' + host.utc14(env.now()))
        dest.mkdir(parents=True, exist_ok=True)
        os.replace(env.p.foreground, dest / 'FOREGROUND.json')
        return
    if fg['kind'] == 'selftest' and fg.get('attempt') == 1 and env.work is not None:
        os.replace(env.p.foreground, env.v2 / ('dead_%s.json' % host.utc14(env.now())))
        durable.fsync_dir(env.v2)
        env.work['selftest_died'], env.work['selftest_dir'] = True, None
        save_work(env)
        return
    stop_block(env, 'SELFTEST_DIED' if fg['kind'] == 'selftest' else 'FOREGROUND_DIED')


def go_checks(env):
    """A `go`: the same block again when it expects found/answer and nothing changed (same --at); after a DOWNLOAD
    block, a missing file is REFUSED DOWNLOAD_MISSING; a pending md5-hidden verification runs (§5.5)."""
    b = env.block
    if not b:
        return
    if b['expect'].get('command') in ('found', 'answer') and b.get('basis') == basis(env):
        bare(b['lines'], 0)
    if b['expect'].get('command') != 'go' or b.get('basis') != basis(env):
        return
    dl = [shlex.split(ln.split(' TO ', 1)[1])[0] for ln in b['lines'] if ln.startswith('DOWNLOAD ')]
    if any(not os.path.isfile(p) for p in dl):
        refuse(env, 'DOWNLOAD_MISSING')
    if env.pending and env.pending.get('verify'):
        r, code = savepoint.on_verify(env, env.pending)
        if r == 'refused':
            refuse(env, code)
        if r == 'stop':
            raise Halt('STOP', code, 'a copy differs')
        env.pending = durable.write_doc(env.p.pending, env.pending)
    lp = (env.work or {}).get(b['expect'].get('loop') or 'setup_loop')
    if lp and lp.get('verify'):
        r, code = savepoint.setup_verify(env, lp)
        if r == 'refused':
            refuse(env, code)
        if r == 'stop':
            raise Halt('STOP', code, 'a copy differs')
        save_work(env)


# ================================================================ found (§6.2)
def do_found(env, args):
    b = env.block
    try:
        at, items = drive.parse_found(args)
    except drive.Usage:
        bare((b or {}).get('lines') or ['usage: found --at A --name N (--file F ... | --none)'], 2)
    if b is None or at != b['at']:
        refuse(env, 'STALE_AT')
    ex = b['expect']
    if ex.get('command') != 'found':
        refuse(env, 'COMMAND_NOT_EXPECTED')
    for name, files, _, _ in items:
        if any(N.forbidden(v) for v in ([name] if name is not None else []) + files):
            refuse(env, 'VALUE_FORBIDDEN')
    code, got, refused = drive.check_found(items, ex.get('names') or [], bool(ex.get('list')), ex.get('uploaded') or ())
    if code:
        refuse(env, code)

    def chk(v):
        return 'VALUE_PATTERN' if N.check_value('id', 'ID', v, env.idcfg()) else None
    kind, hidden = ex.get('kind'), env.gates.get('p2_md5_visible') == 'no'
    if kind in ('pending', 'setup'):
        if kind == 'pending':
            r, c = savepoint.on_found(env, env.pending, got, chk, refused, env.known_ids)
        else:
            r, c = savepoint.setup_found(env, env.work[ex.get('loop') or 'setup_loop'], got, chk, refused)
        if r == 'refused':
            refuse(env, c)
        if r == 'stop':
            raise Halt('STOP', c, 'found')
        if kind == 'pending':
            env.pending = durable.write_doc(env.p.pending, env.pending)
        else:
            save_work(env)
        if r == 'handback':          # §X.5.6 step 4: not sticky, not in HALT.json; the next `go` FINDs first
            emit(env, env.block['state_code'], PrintBlock('STOP', do=('STOP', {'code': c, 'handback': 'A'})),
                 {'command': 'go', 'kind': kind})
        return
    if ex.get('list'):
        rows = []
        for f in got.get(None) or []:
            c = drive.parse_copy(f, hidden, with_name=True)
            if c is None:
                refuse(env, 'FOUND_SYNTAX')
            if chk(c[1]) or not N.fm(N.PATTERNS['SIZE'], c[-1]):
                refuse(env, 'VALUE_PATTERN')
            if not hidden and not N.fm(N.PATTERNS['MD5'], c[2]):
                refuse(env, 'VALUE_PATTERN')
            rows.append([c[0], c[1], None if hidden else c[2], int(c[-1])])
        env.work['listing'] = rows
        save_work(env)
        return
    now, rec = env.now(), {}
    for name in ex['names']:
        cps = []
        for f in got[name] or []:
            c = drive.parse_copy(f, hidden)
            if c is None:
                refuse(env, 'FOUND_SYNTAX')
            if chk(c[0]) or not N.fm(N.PATTERNS['SIZE'], c[-1]) or (not hidden and not N.fm(N.PATTERNS['MD5'], c[1])):
                refuse(env, 'VALUE_PATTERN')
            cps.append([c[0], None if hidden else c[1], int(c[-1])])
        rec[name] = cps
    for name, cps in rec.items():
        if kind == 'fetch':
            env.work['fetched'][name] = cps
        else:
            lk = {'name': name, 'result': 'present' if cps else 'absent', 'copies': cps, 'utc': now}
            if env.work.get('committed'):
                lk['post'] = True               # a step-6 re-check FIND (§8.4): never a head-search observation
            env.work['lookups'].append(lk)
    save_work(env)


# ================================================================ answer (§6.2, §6.3)
def do_answer(env, args):
    b = env.block
    try:
        at, pairs = drive.parse_answer(args)
    except drive.Usage:
        bare((b or {}).get('lines') or ['usage: answer --at A key=value ...'], 2)
    if b is None or at != b['at']:
        refuse(env, 'STALE_AT')
    ex = b['expect']
    if ex.get('command') != 'answer':
        refuse(env, 'COMMAND_NOT_EXPECTED')
    ctx, now = ex['context'], env.now()
    win = {k: [lo, now] for k, (lo, _) in (ctx.get('window') or {}).items()}
    err, got = N.check_answers(ex['keys'], pairs, env.idcfg(ctx.get('case') or ''), win)
    if err:
        refuse(env, err[0])
    if 'started_utc' in got and got['started_utc'] > got['ended_utc']:
        refuse(env, 'UTC_OUT_OF_WINDOW')
    code = apply_answer(env, ctx, got)
    if code:
        refuse(env, code)


# ================================================================ the loop
def advance(env):
    for _ in range(300):
        if env.pending:
            pending_step(env)
            continue
        if env.work is None:
            new_work(env)
        if env.work.get('phase') != 'DONE':
            session_step(env)
            continue
        if env.cache.get('pass') is None:
            pass_phase(env, env.cache['fingerprint_sha256'])
            continue
        plan_step(env)
    raise Halt('STOP', 'UNCLASSIFIED', 'no block after 300 steps')


def gates_check(env):
    if host.gates_problem(env.cfg, env.mode, N.UPLOAD_CAP_BYTES):
        stop_block(env, 'RELEASE_GATE_OPEN')
    if env.state is not None and env.cfg['gates'] != env.state['genesis']['gates']:
        raise Halt('STOP', 'GATES_CHANGED', 'the kit gates differ from the genesis gates')


def plan_step(env):
    gates_check(env)
    st = P.next_action({'state': env.state, 'marks': env.cache.get('marks') or {}, 'local': {'gates_ok': True},
                        'now': env.now(), 'boot_id': env.boot, 'base': str(env.lay.base), 'cfg': env.cfg})
    carry(env, st)


def set_mark(env, key):
    env.cache['marks'] = dict(env.cache.get('marks') or {}, **{key: env.now()})
    save_cache(env)


def carry(env, st):
    if isinstance(st, PrintBlock):
        if st.mark:
            set_mark(env, st.mark)
        emit(env, st.state_code, st, {'command': 'go', 'kind': 'plan'})
    if isinstance(st, Ask):
        ask(env, st)
    if isinstance(st, Stop):
        if st.code == 'UNCLASSIFIED' and env.state is not None and env.state['phase'] == 'OPEN':
            return commit_halt(env, 'UNCLASSIFIED')
        stop_block(env, st.code, st.handback or 'C')
    if isinstance(st, HaltStep):
        if st.commit and env.state is not None and env.state['phase'] == 'OPEN':
            return commit_halt(env, st.code)
        stop_block(env, st.code)
    if isinstance(st, RunChain):
        return start_chain(env, {'run': st.run, 'first': st.first, 'info': st.info})
    if isinstance(st, Commit):
        return plan_commit(env, st)
    raise Halt('STOP', 'UNCLASSIFIED', 'a step the plan does not return')


# ================================================================ session glue (§8)
def session_view(env):
    return {'work': env.work, 'series': env.series or 'Q1', 'gates': env.gates, 'clear': (env.cfg or {}).get('clear'),
            'now': env.now(), 'base': str(env.lay.base), 'transcript_ext': (env.cfg or {}).get('transcript_ext', 'json')}


def done(env, phase):
    if phase not in env.work['done']:
        env.work['done'].append(phase)
    save_work(env)


def session_step(env):
    phase, st = S.session_next(session_view(env))
    w = env.work
    if S.phase_index(phase) > S.phase_index(w['phase']) and phase != 'DONE':
        w['phase'] = phase
        save_work(env)
    if phase == 'DONE' and (st is None or (isinstance(st, Commit) and w.get('committed'))):
        return finish_session(env)
    if st is None:
        return IO_PHASES[phase](env)
    if isinstance(st, Commit):
        return session_commit(env, st)
    if isinstance(st, Place):
        return start_place(env, st.plan)
    if isinstance(st, Reupload):
        return reupload(env, st)
    if isinstance(st, Ask):
        return ask(env, st)
    if isinstance(st, Stop):
        stop_block(env, st.code, st.handback or 'C')
    if isinstance(st, HaltStep):
        build_state(env)
        install_kit(env)
        commit_halt(env, st.code)
        w['phase'] = 'DONE'
        save_work(env)
        return
    if isinstance(st, PrintBlock):
        if st.downloads and all(os.path.isfile(x[2]) for x in st.downloads):
            if phase == 'HEAD' and not w.get('head'):
                return verify_head(env, st.downloads)
            return record_downloads(env, st.downloads)
        if st.do[0] == 'END_CONVERSATION':
            w['resolve'] = dict(w['resolve'], end=True)
            save_work(env)
        if st.do[0] == 'EXPORT_TRANSCRIPT':
            w['resolve'] = dict(w['resolve'], export=True, export_to=st.do[1]['to'])
            save_work(env)
        if st.do[0] == 'ATTEST_FOUND':
            do = ('ATTEST_FOUND', dict(st.do[1], md5_hidden=env.gates.get('p2_md5_visible') == 'no'))
            emit(env, st.state_code, PrintBlock(st.state_code, st.uploads, st.finds, st.lists, st.downloads, do),
                 {'command': 'found', 'names': st.do[1].get('names') or [], 'list': bool(st.do[1].get('list')),
                  'kind': 'session'})
        emit(env, st.state_code, st, {'command': 'go', 'kind': 'session'})
    raise Halt('STOP', 'UNCLASSIFIED', 'an unknown session step')


def ph_layout(env):
    env.work['identity'] = {'home': env.lay.home, 'uid': os.getuid()}
    done(env, 'LAYOUT')


def record_downloads(env, downloads):
    """Rule V (§X.5.5, §X.8.4): hash every copy the session asked to download; the session compares. A head-part copy
    1 in inbox/journal/ is kept as inbox/journal/<name> for placement (no second download); the others are deleted."""
    w = env.work
    ver = dict(w.get('verified') or {})
    for _, did, path in downloads:
        ver[did] = [sha_file(path), os.lstat(path).st_size]
        jr = os.path.dirname(path) == str(env.lay.inbox / 'journal')
        if jr and path.endswith('.1') and not os.path.lexists(path[:-2]):
            os.replace(path, path[:-2])
        else:
            os.unlink(path)
    w['verified'] = ver
    save_work(env)


def marker(path):
    try:
        return Path(path).read_text().split()
    except (OSError, UnicodeDecodeError):
        return None


def ph_setup(env):
    """§X.6.6: session_start.sh ran the setup in the foreground. The ok marker for this boot and commit: continue; the
    failed marker: the setup log goes to CPS/reports through the setup-file loop, then STOP SETUP_FAILED; neither:
    STOP SETUP_FAILED (not done: the Dot re-runs a killed session_start.sh, so `go` never waits for setup)."""
    want = [env.boot, host.repo_commit(env.lay) or '']
    if marker(env.lay.tools / SETUP_DONE) == want:
        return done(env, 'SETUP')
    logs = sorted(env.lay.outbox.glob('setup_*.log'))
    if marker(env.lay.tools / SETUP_FAILED) == want and logs and os.lstat(logs[-1]).st_size > 0:
        if upload_files(env, 'report_loop', [(logs[-1], N.FOLDERS['reports'], logs[-1].name)], 'SETUP'):
            stop_block(env, 'SETUP_FAILED')
    stop_block(env, 'SETUP_FAILED')


def upload_files(env, key, files, state_code):
    """The setup-file loop (§5 steps 5-7 without a chain, §X.5.6) for report files kept in RESTORE_WORK[key]: prints
    the next block, or returns True once every file is confirmed."""
    w = env.work
    if w.get(key) is None:
        for p, _, _ in files:
            if os.lstat(p).st_size > env.upload_cfg['max_upload_bytes']:
                raise Halt('STOP', 'UPLOAD_TOO_LARGE', 'a report file over max_upload_bytes')
        w[key] = savepoint.setup_loop(files)
        save_work(env)
    b = savepoint.setup_block(env, w[key])
    if b is None:
        return True
    save_work(env)
    ups, finds, dls, do, names = b
    emit(env, state_code, PrintBlock(state_code, ups, finds, (), dls, do),
         {'command': 'found', 'names': names, 'kind': 'setup', 'loop': key, 'uploaded': do[1]['uploaded']}
         if do[0] == 'ATTEST_FOUND' else {'command': 'go', 'kind': 'setup', 'loop': key})


def fetch(env, folder, name, local, code_missing='KIT_NOT_VERIFIED'):
    """FIND then DOWNLOAD one file by exact name (kit, head kit, PASS). Returns the local path once present."""
    if os.path.isfile(local):
        return local
    cps = env.work['fetched'].get(name)
    if cps is None:
        emit(env, 'KIT', PrintBlock('KIT', finds=((folder, 'NAME', name),), do=('ATTEST_FOUND', {
            'names': [name], 'md5_hidden': env.gates.get('p2_md5_visible') == 'no'})),
            {'command': 'found', 'names': [name], 'kind': 'fetch'})
    if not cps:
        return None
    if len({(c[1], c[2]) for c in cps}) > 1:                 # §X.8.2: one size (and md5, when visible)
        raise Halt('STOP', 'FORK', 'two copies of one setup file differ')
    Path(local).parent.mkdir(parents=True, exist_ok=True)
    emit(env, 'KIT', PrintBlock('KIT', downloads=((folder, cps[0][0], str(local)),)), {'command': 'go', 'kind': 'fetch'})


def ph_kit(env):
    """§8.2 kit intake: the hinted SESSION_KIT_<kit12>.zip in CPS/setup, else the FOLDER_MANIFEST route."""
    w, inbox = env.work, env.lay.inbox
    k12 = (w['hint'] or {}).get('kit')
    use = None
    if k12 and re.fullmatch(N.HEX12, k12) and w.get('kit_route') != 'manifest':
        name = 'SESSION_KIT_%s.zip' % k12
        use = fetch(env, N.FOLDERS['setup'], name, inbox / 'kit' / name)
        if use is None:
            w['kit_route'] = 'manifest'
            save_work(env)
        elif not sha_file(use).startswith(k12):
            raise Halt('STOP', 'KIT_NOT_VERIFIED', 'the kit is not the hinted one')
    if use is None:
        blk = Block()
        try:
            info, _ = session_kit(env.lay, inbox, blk)
            use = Path(info['path'])
        except Halt as h:
            if h.kind != 'NEED':
                raise
            for _, _, ref, local in blk.fetch:
                fetch(env, os.path.dirname(ref), os.path.basename(ref), local)
            raise Halt('STOP', 'KIT_NOT_IN_MANIFEST', 'a kit file is not on Drive')
    members = kit_members(use)
    for need in ('RELEASE.json', 'VM_HELPER_CONFIG.json'):
        if need not in members:
            raise Halt('STOP', 'KIT_NOT_VERIFIED', 'a kit member is missing')
    w['kit'] = {'sha256': sha_file(use), 'path': str(use), 'members': sorted([k, sha_bytes(v)] for k, v in
                                                                             members.items()),
                'config': sjson(members['VM_HELPER_CONFIG.json']), 'release_sha256': sha_bytes(members['RELEASE.json'])}
    done(env, 'KIT')


def kit_bytes(env):
    return kit_members(env.work['kit']['path'])


def ph_config(env):
    m = kit_bytes(env)
    env.adopt(m['VM_HELPER_CONFIG.json'], m['RELEASE.json'])
    if host.gates_problem(env.cfg, env.mode, N.UPLOAD_CAP_BYTES):
        stop_block(env, 'RELEASE_GATE_OPEN')
    check_layout_release(env.lay, env.release, host.helper_tree_sha256(), host.repo_commit(env.lay))
    done(env, 'CONFIG')


def ph_fingerprint(env):
    env.work['fingerprint'] = fingerprint(env.lay)[0]
    done(env, 'FINGERPRINT')


def ph_pass(env):
    pass_phase(env, env.work['fingerprint'])


def pass_phase(env, fp):
    """§8.3, §X.8.3: FIND the PASS of this fingerprint; a copy with the known md5 (md5 visible only) is accepted without
    download, else every copy is downloaded and validated; none valid: the self-test runs and its PASS is uploaded
    through the setup-file loop."""
    w, setup = env.work, N.FOLDERS['setup']
    name = 'FINGERPRINT_PASS_%s.json' % fp
    passes = ((w.get('head') or {}).get('entry') or {}).get('state', {}).get('passes') or (env.state or {}).get(
        'passes') or {}
    if w.get('setup_loop') is None and not w.get('selftest_dir'):
        if name not in w['fetched']:
            fetch(env, setup, name, env.lay.inbox / 'pass' / name)
        cps = w['fetched'][name] or []
        known = passes.get(fp)
        hit = [c for c in cps if known and c[1] is not None and c[1] == known['md5']]
        if hit:
            return accept_pass(env, {'name': name, 'md5': hit[0][1], 'size': hit[0][2]})
        lps = [env.lay.inbox / 'pass' / ('%s.%d' % (name, k)) for k in range(1, len(cps) + 1)]
        dl = tuple((setup, c[0], str(lp)) for c, lp in zip(cps, lps) if not lp.is_file())
        if dl:
            lps[0].parent.mkdir(parents=True, exist_ok=True)
            emit(env, 'KIT', PrintBlock('KIT', downloads=dl), {'command': 'go'})
        for c, lp in zip(cps, lps):
            if os.lstat(lp).st_size == c[2] and validate_pass(env.ctx2(), lp.read_bytes(), fp):
                return accept_pass(env, {'name': name, 'md5': md5_file(lp), 'size': os.lstat(lp).st_size})
        return start_selftest(env, fp)
    if w.get('setup_loop') is None:
        return finish_selftest(env, fp)
    b = savepoint.setup_block(env, w['setup_loop'])
    if b is None:
        f = [x for x in w['setup_loop']['files'] if x['name'] == name][0]
        w['setup_loop'] = None
        return accept_pass(env, {'name': name, 'md5': f['md5'], 'size': f['bytes']})
    save_work(env)
    ups, finds, dls, do, names = b
    emit(env, 'SELFTEST', PrintBlock('SELFTEST', ups, finds, (), dls, do),
         {'command': 'found', 'names': names, 'kind': 'setup', 'uploaded': do[1]['uploaded']}
         if do[0] == 'ATTEST_FOUND' else {'command': 'go', 'kind': 'setup'})


def accept_pass(env, ps):
    env.work.update(selftest_dir=None, setup_loop=None, selftest_died=False)
    if env.work.get('phase') == 'DONE':
        env.cache['pass'] = ps
        save_cache(env)
        return
    env.work['pass'] = ps
    done(env, 'PASS')


def start_selftest(env, fp):
    """§8.3: the self-test as a foreground stage (attempt 2 after a dead attempt 1 of this boot, §X.7.2 step 4)."""
    if env.command != 'go':
        run_go(env)
    d = env.lay.outbox / ('selftest_' + host.utc14(env.now()))
    d.mkdir(parents=True, exist_ok=True)
    durable.write_plain(d / 'RUN.json', {'fingerprint_before_sha256': fp, 'commit': host.repo_commit(env.lay),
                                         'started_utc': env.now(), 'work_dir': str(d / 'work'), 'exit': None,
                                         'ended_utc': None, 'pid': None})
    run_stage(env, 'selftest', {'dir': str(d), 'attempt': 2 if env.work.get('selftest_died') else 1})


def finish_selftest(env, fp):
    d = Path(env.work['selftest_dir'])
    run = sjson((d / 'RUN.json').read_bytes())
    fp2, full = fingerprint(env.lay)
    res_p = d / 'work' / 'EXPORT_TEST_RESULTS.json'
    res_raw = res_p.read_bytes() if res_p.is_file() else b''
    s = (sjson(res_raw).get('summary') or {}) if res_raw else {}
    node_sha = (full['components'].get('node') or {}).get('sha256')
    if fp2 != fp or not host.selftest_ok(env.cfg, run, s, node_sha):
        raise Halt('STOP', 'SELFTEST_FAILED', 'the export self-test did not pass on this VM')
    sn, pn = 'SELFTEST_%s.json' % fp, 'FINGERPRINT_PASS_%s.json' % fp
    durable.write(env.lay.outbox / sn, res_raw)
    durable.write(env.lay.outbox / pn, durable.doc_bytes(host.pass_doc(fp, full, run.get('commit'), sn, res_raw, s,
                                                                      run)))
    env.work['setup_loop'] = savepoint.setup_loop([(env.lay.outbox / sn, N.FOLDERS['setup'], sn),
                                                   (env.lay.outbox / pn, N.FOLDERS['setup'], pn)])
    save_work(env)


def ph_clock(env):
    head = env.work['head']['entry']
    try:
        clock_check(env.ctx2(), parse_utc(head['utc']), Block(), env.work['operator']['model'])
    except Halt as h:
        if h.code == 'CLOCK_WAIT':
            wait_out(env, (parse_utc(head['utc']) - now_dt()).total_seconds() + 2, 'RESTORE')
        raise
    done(env, 'CLOCK')


def ph_kit_accept(env):
    """§8.2 KIT_CHANGE: fetch the kit the journal names and read its members."""
    hk = env.work['head']['entry']['state']['kit_sha256']
    name = 'SESSION_KIT_%s.zip' % hk[:12]
    lp = fetch(env, N.FOLDERS['setup'], name, env.lay.inbox / 'kit' / 'head' / name)
    if lp is None or sha_file(lp) != hk:
        raise Halt('STOP', 'KIT_NOT_VERIFIED', 'the head kit is not on Drive')
    m = kit_members(lp)
    env.work['head_kit'] = {'sha256': hk, 'members': sorted([k, sha_bytes(v)] for k, v in m.items()),
                            'config': sjson(m['VM_HELPER_CONFIG.json']), 'release_sha256': sha_bytes(m['RELEASE.json'])}
    save_work(env)


IO_PHASES = {'LAYOUT': ph_layout, 'SETUP': ph_setup, 'KIT': ph_kit, 'CONFIG': ph_config,
             'FINGERPRINT': ph_fingerprint, 'PASS': ph_pass, 'CLOCK': ph_clock, 'KIT_ACCEPT': ph_kit_accept}


def verify_head(env, downloads):
    """§8.4 step 3 (§X.8.4): every copy of N was downloaded to inbox/journal/<name>.<k>; all must be byte-identical
    and of the size the FIND reported (else FORK); copy 1 is the head, kept as inbox/journal/<name>. Then Archive and
    check, validate_entry, state sha, helper tree, runner pin, release acceptance; any failure is the specific code
    (C1, a local sticky STOP)."""
    w = env.work
    cfg = {'series': env.series, 'accepted_helper_tree_sha256': env.cfg['accepted_helper_tree_sha256']}
    paths = [x[2] for x in downloads]
    sizes = {c[0]: c[2] for lk in w['lookups'] for c in lk['copies']}
    shas = {sha_file(p_) for p_ in paths}
    if len(shas) > 1 or any(os.lstat(p_).st_size != sizes.get(x[1]) for x, p_ in zip(downloads, paths)):
        w['head_error'] = 'FORK'
        save_work(env)
        return
    path = paths[0][:-2]
    os.replace(paths[0], path)
    for p_ in paths[1:]:
        os.unlink(p_)
    code = None
    try:
        man = savepoint.read_entry(path)
    except Halt:
        man, code = None, 'HEAD_CORRUPT'
    if man is not None:
        pr = E.validate_entry(man, cfg=cfg)
        code = None if not pr else 'HELPER_UNKNOWN' if any('helper' in x or 'runner' in x for x in pr) else \
            'STATE_SHA_MISMATCH' if pr == ['state_sha256'] else 'SCHEMA_INVALID'
        st = man.get('state') or {}
        if code is None and man['release_sha256'] != st['genesis']['release_sha256'] and \
                man['release_sha256'] not in env.cfg['accepts_release_sha256']:
            code = 'RELEASE_NOT_ACCEPTED'
        cps = [lk for lk in w['lookups'] if lk['name'] == man['name'] and lk['copies']]
        if code is None and cps and cps[-1]['copies'][0][1] not in (None, md5_file(path)):
            code = 'HEAD_CORRUPT'
    if code:
        w['head_error'] = code
    else:
        w['head'] = {'entry': man, 'sha256': sha_file(path), 'bytes': os.lstat(path).st_size, 'md5': md5_file(path),
                     'path': str(path)}
    save_work(env)


def build_state(env):
    """STATE.json for the session's commit (§2.3): the head found on Drive (or none), the confirms of its files as
    found (missing head parts with no copy), and this boot's operator, kit, fingerprint and PASS."""
    w = env.work
    head = state = None
    confirms = []
    if w.get('head'):
        man = w['head']['entry']
        cps = {}
        for lk in w['lookups']:
            for c in lk['copies']:
                cps.setdefault(lk['name'], {})[c[0]] = c
        hc = sorted(cps.get(man['name'], {}).values())
        head = {'seq': man['seq'], 'name': man['name'], 'id': hc[0][0], 'md5': w['head']['md5'],
                'bytes': w['head']['bytes'], 'sha256': w['head']['sha256']}
        confirms = [{'name': man['name'], 'copies': [{'id': c[0], 'md5': w['head']['md5'], 'size': c[2]} for c in hc]}]
        for p in man['parts']:
            confirms.append({'name': p['name'], 'copies': [{'id': c[0], 'md5': p['md5'], 'size': c[2]}
                                                           for c in sorted(cps.get(p['name'], {}).values())]})
        state = man['state']
    if env.p.block.exists():                    # the session's blocks belong to no head: every old --at is stale
        os.unlink(env.p.block)
    env.block = None
    env.cache = {'schema': savepoint.STATE_SCHEMA, 'series': env.series, 'boot_id': env.boot, 'uid': os.getuid(),
                 'home': env.lay.home, 'operator': w['operator'], 'marks': (env.cache or {}).get('marks') or {},
                 'kit_sha256': w['kit']['sha256'], 'kit': {k: w['kit'][k] for k in ('sha256', 'members', 'config',
                                                                                     'release_sha256')},
                 'fingerprint_sha256': w['fingerprint'], 'pass': w['pass'], 'gates_ok': True, 'head': head,
                 'state': state, 'state_sha256': E.state_sha256(state) if state else None, 'post': [],
                 'confirms': confirms, 'cleared_local': (env.cache or {}).get('cleared_local'),
                 'written_utc': env.now()}
    save_cache(env)


def install_kit(env):
    """unpack_kit installs the accepted kit into BASE/runtime (§8.2: its return value decides nothing)."""
    if env.work.get('installed') == env.work['kit']['sha256']:
        return
    m = kit_bytes(env)
    unpack_kit(env.lay, m, F.run_in_flight(env.state) if env.state else False)
    env.work['installed'] = env.work['kit']['sha256']
    save_work(env)


def finish_session(env):
    install_kit(env)
    if env.cache is None:
        build_state(env)
    env.work['phase'] = 'DONE'
    save_work(env)


def session_commit(env, st):
    """GENESIS (§7.12) or RESTORE (§8.7)."""
    build_state(env)
    install_kit(env)
    if st.entry['kind'] == 'GENESIS':
        return genesis(env, st.entry['body'])
    w, b = env.work, dict(st.entry['body'])
    d = draft(env, 'RESTORE', None)
    b['fingerprint_sha256'], b['pass'], b['placed'] = w['fingerprint'], w['pass'], w['placed_list']
    if b['start'] is not None:
        b['start'] = dict(b['start'], utc=d['utc'], boot_id=env.boot)
    members, post = [], [['DROP_DOWNLOADS', [str(env.lay.inbox / x) for x in ('journal', 'verify', 'kit', 'pass')]]]
    for it in b['resolutions']:
        if it['transcript'] == 'exported':
            src = w['resolve'].get('export_to')
            ext = (env.cfg or {}).get('transcript_ext', 'json')
            members.append(('transcript/%s%d_%d.%s' % (it['role'], it['attempt'], it['start_no'], ext), 'file', 0o644,
                            src))
            post.append(['DROP_ATTEST', [src]])
    if b['abandon'] is not None:
        members.append(tmember('attest/ask.txt', 'The job could not be prepared after a reset; a new job only at your '
                                                 'request.\n'))
    if b['delivery_question'] is not None:
        members.append(tmember('attest/ask.txt', 'Did the copy of the job reach you? Answer yes or no.\n'))
    d['body'] = b
    commit(env, d, roots_of(members) + members, post=post)


def genesis(env, sb):
    """§7.12: Q/D create the ledger exactly as v1 cmd_genesis (staging folder, the runner's Ledger, rename); E none."""
    lay, w, q = env.lay, env.work, env.series[0] in 'QD'
    rel = env.release
    body = {'mode': env.mode if env.mode != 'setup' else N.mode_of(env.series), 'operator': w['operator'],
            'jobs': None, 'ledger': None, 'layout': {'base': str(lay.base), 'qual': str(lay.qual),
                                                      'jobs': str(lay.jobs), 'ledger': str(lay.ledger),
                                                      'runtime': str(lay.runtime)},
            'gates': env.cfg['gates'], 'pass': w['pass'], 'other_series_absent': sb.get('other_series_absent')}
    members = []
    if q:
        if (w['hint'] or {}).get('seq') or os.path.lexists(lay.ledger_dir):
            raise Halt('STOP', 'PLACE_TARGET_NOT_EMPTY', 'genesis needs no hint and no BASE/ledger')
        adm = ((rel.get('qualification') or {}).get('admissions') or [None])[0]
        try:
            araw = Path(adm['path']).read_bytes()
            fu = parse_utc(sjson(araw).get('frozen_utc'))
        except (OSError, ValueError, TypeError, KeyError):
            araw, fu = b'', None
        if adm is None or adm.get('sha256') != sha_bytes(araw) or fu is None or fu >= now_dt():
            raise Halt('STOP', 'RELEASE_NOT_ACCEPTED', 'the admission must be listed with its sha256 and frozen')
        jraw = Path(rel['qualification']['jobs_file']).read_bytes()
        jobs = sjson(jraw)['cases']
        body['jobs'] = [[c['case_id'], c.get('order'), (c.get('reason') or True) if c.get('nonattempt') else None]
                        for c in jobs]
        cj = runner.load_runner()
        sd = lay.base / ('.cps_vm_stage_ledger_%d' % os.getpid())
        if os.path.lexists(sd):
            remove_tree(sd)
        os.mkdir(sd, 0o755)
        e = {'type': 'genesis', 'ledger_id': secrets.token_hex(16),
             'helper': {'version': N.HELPER_VERSION, 'tree_sha256': host.helper_tree_sha256()},
             'release_sha256': sha_bytes(env.rel_raw), 'admission_sha256': sha_bytes(araw),
             'jobs_sha256': sha_bytes(jraw), 'boot_id': env.boot, 'fingerprint_sha256': w['fingerprint'],
             'base': str(lay.base)}
        with cj.Ledger(sd / 'LEDGER.jsonl', create=True) as led:
            led.append(e)
        os.rename(sd, lay.ledger_dir)
        raw = lay.ledger.read_bytes()
        line = raw.split(b'\n', 1)[0] + b'\n'
        body['ledger'] = {'identity_line_sha256': sha_bytes(line), 'ledger_id': e['ledger_id']}
        members = [('ledger', 'dir', 0o755, None), ('ledger/LEDGER.jsonl', 'file', 0o644, raw)]
    commit(env, draft(env, 'GENESIS', body, seq=1), members)


def start_place(env, plan):
    """§8.5.1: download what the placement needs (by id), then a worker of kind `place`."""
    st, ser = env.state, env.series
    names = []
    if plan.get('ledger'):
        names.append(N.entry_name(ser, plan['ledger']['seq']))
    if plan.get('job_dir'):
        if plan.get('snapshot_seq'):
            names.append(N.entry_name(ser, plan['snapshot_seq']))
        names += list((plan.get('png') or {}).get('parts') or [])
        names += [N.entry_name(ser, a['seq']) for a in plan.get('ai') or []]
        names += [N.entry_name(ser, a['seq']) for a in plan.get('transcripts') or []]
    if not plan.get('ledger') and not plan.get('job_dir'):
        env.work['placed'] = True
        save_work(env)
        return
    if env.cache is None or env.cache.get('head') is None:
        build_state(env)
    ensure_local(env, sorted(set(names)), 'PLACE')
    if env.command != 'go':
        run_go(env)
    run_stage(env, 'place', dict(plan, files=None, series=ser, inbox=str(env.lay.inbox / 'journal')))


def ensure_local(env, names, code):
    """Print DOWNLOAD lines for the journal files named that are not in inbox/journal (ids from the state)."""
    dl = []
    for n in names:
        lp = env.lay.inbox / 'journal' / n
        if not lp.is_file():
            did = env.file_id(n)
            if did is None:
                raise Halt('STOP', 'UNCLASSIFIED', 'a journal file without a known id')
            lp.parent.mkdir(parents=True, exist_ok=True)
            dl.append((env.series_folder, did, str(lp)))
    if dl:
        emit(env, code, PrintBlock(code, downloads=tuple(dl)), {'command': 'go', 'kind': 'fetch'})


def reupload(env, st):
    """§8.5 C3/C4: re-upload missing head parts from the head entry's own members (setup-file loop)."""
    w = env.work
    if w.get('setup_loop') is None:
        head = w['head']
        src = {'LEDGER': 'final/LEDGER_FINAL.jsonl', 'ALLFZ': 'final/ALL_FROZEN.json', 'DELIV': 'delivery/copy.xlsx',
               'DLOG': 'delivery/log.json'}
        files = []
        for n in st.names:
            p = [x for x in head['entry']['parts'] if x['name'] == n][0]
            b = savepoint.member_bytes(head['path'], src[p['kind']])
            lp = env.journal / n
            env.journal.mkdir(parents=True, exist_ok=True)
            durable.write(lp, b)
            files.append((lp, p['folder'], n))
        w['setup_loop'] = savepoint.setup_loop(files)
        save_work(env)
    b = savepoint.setup_block(env, w['setup_loop'])
    if b is None:                       # the confirmed copies are this session's observations of those parts
        now, ver = env.now(), dict(w.get('verified') or {})
        for f in w['setup_loop']['files']:
            w['lookups'].append({'name': f['name'], 'result': 'present', 'copies': f['copies'], 'utc': now})
            for c in f['copies']:
                ver[c[0]] = [f['sha256'], f['bytes']]
        w['setup_loop'], w['reuploaded'], w['verified'] = None, True, ver
        save_work(env)
        return
    save_work(env)
    ups, finds, dls, do, names = b
    emit(env, 'RESTORE', PrintBlock('RESTORE', ups, finds, (), dls, do),
         {'command': 'found', 'names': names, 'kind': 'setup', 'uploaded': do[1]['uploaded']}
         if do[0] == 'ATTEST_FOUND' else {'command': 'go', 'kind': 'setup'})


# ================================================================ asks and answers (§6.5)
def ask(env, st):
    ctx, a = dict(st.context), st.context['action']
    prefix = None
    if a == 'NOTIFY_OWNER':
        ensure_text(env, ctx['file'], ctx['for_seq'], 'attest/notice.txt')
        prefix = ('NOTIFY_OWNER', {'file': ctx['file']})
    elif a == 'ASK_USER':
        ensure_text(env, ctx['file'], ctx['for_seq'], 'attest/ask.txt')
        prefix = ('ASK_USER', {'file': ctx['file']})
    elif a == 'DELIVER_COPY':
        ensure_standard(env, ctx)
        prefix = ('DELIVER', {'file': ctx['file'], 'to': 'copy'})
    elif a == 'DELIVER_USER':
        f = ensure_copy(env, ctx)
        prefix = ('DELIVER', {'file': f, 'to': 'user'})
    if ctx.get('mark'):
        set_mark(env, ctx['mark'])
    ctx.pop('then', None)
    emit(env, ctx.get('state_code', 'ATTEST'), PrintBlock(ctx.get('state_code', 'ATTEST'), do=(
        'ATTEST_ANSWER', {'keys': st.keys, 'prefix': prefix, 'after': ctx.get('after')})),
        {'command': 'answer', 'keys': st.keys, 'context': ctx})


def ensure_text(env, path, seq, member):
    """A notice or question file named by the plan: re-made from its entry's attest/ member after a reset."""
    if os.path.isfile(path):
        return
    n = N.entry_name(env.series, seq)
    ensure_local(env, [n], 'NOTIFY')
    place.place_member(env.lay.inbox / 'journal' / n, member, path)


def ensure_standard(env, ctx):
    """§11.3: BASE/deliver/<run8>/STANDARD.xlsx, its sha256 equal to saved_qa.deliverable_sha256 (re-checked)."""
    R = env.state['runs'][ctx['run']]
    want = R['saved_qa']['deliverable_sha256']
    if not os.path.isfile(ctx['file']):                 # after a placement: the runner's copy in the job folder
        src = [r[0] for r in place.walk(R['job_dir']) if r[1] == 'file' and r[4] == want]
        if src:
            Path(ctx['file']).parent.mkdir(parents=True, exist_ok=True)
            durable.write(ctx['file'], (Path(R['job_dir']) / src[0]).read_bytes())
    if not (os.path.isfile(ctx['file']) and sha_file(ctx['file']) == want):
        raise Halt('STOP', 'UNCLASSIFIED', 'the standard file copy is missing or differs')


def ensure_copy(env, ctx):
    f = env.p.deliver / N.run8(ctx['run']) / 'PERSONAL_COPY.xlsx'
    if not f.is_file():
        n = N.entry_name(env.series, ctx['prepared_seq'])
        ensure_local(env, [n], 'DELIVER')
        place.place_member(env.lay.inbox / 'journal' / n, 'delivery/copy.xlsx', f)
    return str(f)


def apply_answer(env, ctx, got):
    """Apply validated answers. Returns None or a REFUSED code (nothing changed)."""
    a, w = ctx['action'], env.work
    if a == 'OPERATOR':
        w['operator'] = {'model': got['operator_model'], 'platform': got['platform']}
        save_work(env)
    elif a == 'LIST_SHOWS_NONE':
        w['list_shows_none'] = got['list_shows_none'] == 'yes'
        save_work(env)
    elif a == 'RESTORE_ROLE':
        if got.get('transcript') == 'exported':
            code = transcript_problem(env, w['resolve'].get('export_to'))
            if code:
                return code
        w['resolve'] = dict(w['resolve'], answers=got)
        save_work(env)
    elif a == 'OPENED':
        commit(env, draft(env, 'OPENED', {'run': ctx['run'], 'role': ctx['role'], 'attempt': ctx['attempt'],
                                          'start_no': ctx['start_no'], 'conversation': got['conversation'],
                                          'opened_utc': got['opened_utc']}))
    elif a == 'AI':
        return ai_commit(env, ctx, got)
    elif a == 'IDLE':
        return inputs_commit(env, got['case'])
    elif a in ('NOTIFY_OWNER', 'ASK_USER'):
        commit(env, draft(env, 'ACK', {'for_seq': ctx['for_seq'], 'what': a, 'answer': got}),
               post=[['DROP_ATTEST', [ctx['file']]]])
    elif a == 'DELIVER_COPY':
        return delivery_commit(env, ctx, got)
    elif a in ('DELIVER_USER', 'DELIVER_SENT'):       # §X.5 step 8: the freeze chain runs in the next `go`
        set_mark(env, P.sent_mark(ctx['run'], ctx['prepared_seq'], env.state['runs'][ctx['run']]['delivery']))
    return None


def transcript_problem(env, path):
    if not path or not os.path.isfile(path) or os.lstat(path).st_size == 0:
        return 'TRANSCRIPT_FILE_MISSING'
    if os.lstat(path).st_size > env.cfg['max_transcript_bytes']:
        return 'TRANSCRIPT_TOO_LARGE'
    return None


def ai_commit(env, ctx, got):
    """§7.5: walk the role's output folder strictly, read the G final message and transcript, commit the AI entry."""
    R = env.state['runs'][ctx['run']]
    ro = R['roles'][ctx['role'] + str(ctx['attempt'])]
    lt = F.latest(ro)
    members, files, tree = place.ai_members(lt['output'], env.cfg['max_ai_output_bytes'])
    conv = got.get('conversation') or ro['archives'][0]['conversation']
    att, tr, fm_sha, post = {}, None, None, []
    if ro['role'] == 'S':
        att = {'prompt_pasted': True}
    if ro['role'] == 'G':
        fmp = env.p.attest / 'final_message.txt'
        raw = fmp.read_bytes() if fmp.is_file() else b''
        try:
            txt = raw.decode('utf-8')
        except UnicodeDecodeError:
            txt = None
        if txt is None or not 1 <= len(raw) <= 8192 or re.search(r'<[^>]*>|\{[^}]*\}', txt):
            return 'FINAL_MESSAGE_INVALID'
        tp, ext = ctx.get('transcript_path'), env.cfg['transcript_ext']
        if got['transcript'] == 'exported':
            code = transcript_problem(env, tp)
            if code:
                return code
            members.append(('transcript/G%d_%d.%s' % (ro['attempt'], lt['start_no'], ext), 'file', 0o644, tp))
            tr = {'status': 'exported', 'sha256': sha_file(tp), 'ext': ext}
        else:
            tr = {'status': 'not_available', 'sha256': None, 'ext': None}
        members.append(('attest/final_message.txt', 'file', 0o644, raw))
        fm_sha = sha_bytes(raw)
        att = {'platform': got['platform'], 'model': got['model'], 'effort': got['effort'],
               'started_utc': got['started_utc'], 'ended_utc': got['ended_utc'],
               'single_user_message': got['single_user_message'] == 'yes',
               'features': {k: got[k] == 'yes' for k in N.FEATURES},
               'tools': [] if got['tools'] == 'none' else got['tools'].split(','), 'transcript_status': got['transcript']}
        post = [['DROP_ATTEST', [str(fmp)]]]
    body = {'run': ctx['run'], 'role': ro['role'], 'attempt': ro['attempt'], 'revision': ctx['revision'],
            'start_no': lt['start_no'], 'start_boot_id': lt['boot_id'], 'ended': True, 'conversation': conv,
            'attested': att, 'tree_sha256': tree, 'files': files, 'transcript': tr, 'final_message_sha256': fm_sha}
    commit(env, draft(env, 'AI', body), roots_of(members) + members, post=post)
    return None


def inputs_of(env, case):
    """§11.2 row 0: the INPUTS shas of BASE/everyday_inputs/<case>/ (regular files, one link), or None."""
    d = env.lay.everyday_inputs / case
    try:
        job = sjson((d / 'JOB.json').read_bytes())
        src = Path(str(job.get('source_path', '')))
        files = [d / 'JOB.json', d / 'JOB_TITLE.json', src]
        ok = job.get('case_id') == case and src.parent == d and all(
            os.path.isfile(f) and not os.path.islink(f) and os.lstat(f).st_nlink == 1 for f in files)
    except (OSError, ValueError, UnicodeDecodeError, AttributeError):
        ok = False
    if not ok:
        return None
    return {'job_sha256': sha_file(files[0]), 'title_sha256': sha_file(files[1]), 'source_name': src.name,
            'source_sha256': sha_file(src)}


def inputs_commit(env, case):
    """§11.2 row 0: INPUTS is committed before anything runs (r2 INT-10)."""
    got = inputs_of(env, case)
    if got is None:
        return 'INPUTS_INVALID'
    now = env.now()
    commit(env, draft(env, 'INPUTS', {'tag': 'E' + host.utc14(now), 'case': case, 'request_utc': now, 'inputs': got}))
    return None


def delivery_commit(env, ctx, got):
    """§11.3: the personal copy and its log checked, then DELIVERY with parts DELIV01, DLOG01 to the profile folder."""
    R = env.state['runs'][ctx['run']]
    a, b = N.copypath(got['copy'], env.lay.home, R['case']), N.copypath(got['log'], env.lay.home, R['case'])
    if a[2] != 'PERSONAL_COPY.xlsx' or b[2] != 'PERSONALIZATION_LOG.json' or a[:2] != b[:2] or \
            a[1] < host.utc14(env.block['printed_utc']):
        return 'COPY_INVALID'
    for p in (got['copy'], got['log']):
        if os.path.realpath(p) != p or not os.path.isfile(p) or os.path.islink(p) or os.lstat(p).st_nlink != 1 \
                or not 1 <= os.lstat(p).st_size <= env.cfg['png_part_bytes']:
            return 'COPY_INVALID'
    cb, lb = Path(got['copy']).read_bytes(), Path(got['log']).read_bytes()
    try:
        log = sjson(lb)
        pf = log.get('profile_folder')
        okl = (log.get('standard_file') or {}).get('sha256') == R['saved_qa']['deliverable_sha256'] and \
            isinstance(pf, str) and 0 < len(pf) <= 200 and all(32 < ord(c) < 127 or c == ' ' for c in pf) and \
            not any(c in pf for c in '\'"\\')
    except (ValueError, UnicodeDecodeError, AttributeError):
        okl = False
    if not okl:
        return 'COPY_LOG_MISMATCH'
    folder = pf.rstrip('/') + '/deliveries'
    body = {'run': ctx['run'], 'standard_sha256': R['saved_qa']['deliverable_sha256'],
            'copy': {'sha256': sha_bytes(cb), 'bytes': len(cb)}, 'log': {'sha256': sha_bytes(lb), 'bytes': len(lb)},
            'profile_folder': pf}
    members = [('delivery', 'dir', 0o755, None), ('delivery/copy.xlsx', 'file', 0o644, cb),
               ('delivery/log.json', 'file', 0o644, lb)]
    dest = env.p.deliver / N.run8(ctx['run'])
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / 'PERSONAL_COPY.xlsx').is_file():
        durable.write(dest / 'PERSONAL_COPY.xlsx', cb)
    commit(env, draft(env, 'DELIVERY', body), members,
           [{'kind': 'DELIV', 'data': cb, 'folder': folder}, {'kind': 'DLOG', 'data': lb, 'folder': folder}])
    return None


# ================================================================ plan commits (CLEAR §13.5, FINAL §9.4)
def plan_commit(env, st):
    k = st.entry['kind']
    if k == 'CLEAR':
        hk, kit = env.work.get('head_kit'), env.cache.get('kit')
        if not hk or not kit:
            stop_block(env, 'HALTED_' + st.entry['body']['code'])
        code, kc = S.kit_change(env.state, kit, hk)
        if code or not kc['config_only']:
            stop_block(env, code or 'CONFIG_CHANGE_NOT_ALLOWED')
        commit(env, draft(env, 'CLEAR', dict(st.entry['body'], kit_sha256=kit['sha256'], kit_change=kc)))
        return
    if k == 'FINAL':
        return final_commit(env)
    raise Halt('STOP', 'UNCLASSIFIED', 'an unexpected commit')


def final_commit(env):
    s, seq = env.state, env.head_seq() + 1
    raw = env.lay.ledger.read_bytes()
    if sha_bytes(raw) != s['ledger']['sha256']:
        raise Halt('STOP', 'UNCLASSIFIED', 'the ledger differs from the journal')
    oc = O.outcomes(dict(s, seq=seq, phase='FINAL', final={'seq': seq}))     # outcomes(state') after FINAL (§9.4)
    runs = [{'run': k, 'job_dir': R['job_dir'], 'frozen_sha256': R['frozen']['frozen_sha256'],
             'frozen_seq': R['frozen']['seq'], 'frozen_entry': N.entry_name(env.series, R['frozen']['seq']),
             'png_parts': (R['png'] or {}).get('parts') or [], 'flags': R['flags'], 'visual': R['frozen']['visual']}
            for k, R in ((k, s['runs'][k]) for k in s['order']) if R['status'] == 'FROZEN']
    af = {'schema': 'cps.vm2-all-frozen.v1', 'series': env.series, 'final_seq': seq, 'genesis': s['genesis'],
          'release_sha256': s['release_sha256'], 'kit_sha256': s['kit_sha256'],
          'ledger_final': {'sha256': sha_bytes(raw), 'bytes': len(raw)}, 'runs': runs, 'outcomes': oc,
          'outcomes_sha256': N.sha(N.cjson(oc))}
    ab = durable.doc_bytes(af)
    body = {'all_frozen_sha256': sha_bytes(ab), 'ledger_final_sha256': sha_bytes(raw), 'runs': len(runs),
            'outcomes_sha256': af['outcomes_sha256']}
    members = [('final', 'dir', 0o755, None), ('final/ALL_FROZEN.json', 'file', 0o644, ab),
               ('final/LEDGER_FINAL.jsonl', 'file', 0o644, raw)]
    commit(env, draft(env, 'FINAL', body), members, [{'kind': 'LEDGER', 'data': raw, 'folder': env.series_folder},
                                                     {'kind': 'ALLFZ', 'data': ab, 'folder': env.series_folder}])


# ================================================================ foreground stages (§X.7.2)
def needed_entries(env, kind, info):
    """Journal entries a chain worker reads that are not local: an earlier run's FROZEN entry for §7.7 placement, the
    AI entry of a G consumer (attested values, transcript)."""
    if kind != 'chain':
        return []
    s, names = env.state, []
    for rk in (info.get('info') or {}).get('place_frozen') or []:
        R = s['runs'][rk]
        if not (env.lay.frozen_json / ('%s_%s_FROZEN.json' % (R['tag'], R['case']))).is_file():
            names.append(N.entry_name(env.series, R['frozen']['seq']))
    ci = info.get('info') or {}
    rk = ci.get('consume') or (P.consumer_role(s['runs'][info['run']]) if ci.get('bind') and info['first'] in
                               P.CONSUMER.values() else None)
    if rk and rk[0] == 'G':
        names.append(N.entry_name(env.series, s['runs'][info['run']]['roles'][rk]['archives'][-1]['seq']))
    return names


def run_go(env):
    """§X.5 step 8: `found` and `answer` never start a stage; they print the WORK block that hands it to `go`."""
    emit(env, 'WORK', PrintBlock('WORK', do=('RUN', {})), {'command': 'go', 'kind': 'plan'})


def start_chain(env, info):
    """§7.1 RunChain: the local journal files the chain reads, the INPUTS re-check, then the foreground stage."""
    ensure_local(env, needed_entries(env, 'chain', info), 'WORK')
    if info['first'] == 'prepare' and (info.get('info') or {}).get('inputs_seq'):
        R = env.state['runs'][info['run']]
        got = inputs_of(env, R['case'])
        if got is None or N.sha(N.cjson(got)) != R['inputs']['sha256']:
            # nothing runs; the refusal is a fresh block of this head: this `go` may have finished a commit, so the
            # last block (BLOCK.json) can belong to the previous head and must not be reprinted (§2.5)
            lines = render(env, 'WORK', PrintBlock('WORK', do=('RUN', {})), {'command': 'go', 'kind': 'plan'})
            bare(lines[:1] + ['REFUSED INPUTS_CHANGED'] + lines[1:], 4)
    if env.command != 'go':
        run_go(env)
    run_stage(env, 'chain', info)


def run_stage(env, kind, info):
    """§X.7.2 steps 2-3: FOREGROUND.json (durably), the RUNNING line (flushed at once), the body in this process
    under the helper lock, then FOREGROUND.json unlinked and outbox/v2 fsynced on return of any status (never in a
    `finally`: a stage that dies leaves it for step 4), then the result absorbed. The caller's loop prints the block."""
    from . import worker
    first = info.get('first') if kind == 'chain' else None
    mx = env.cfg['stage_max_seconds'][first or kind]
    since = env.now()
    durable.write_doc(env.p.foreground, {'schema': FG_SCHEMA, 'kind': kind, 'run': info.get('run'), 'first': first,
                                         'attempt': info.get('attempt', 1), 'boot_id': env.boot, 'pid': os.getpid(),
                                         'started_utc': since, 'max_seconds': mx})
    print('CPSV-RUNNING kind=%s since=%s max=%d' % (kind, since, mx), flush=True)
    try:
        res = worker.dispatch(kind, info, env)
    except Halt as h:
        res = {'status': 'halt', 'code': h.code}
    except durable.DurableError as e:
        res = {'status': 'halt', 'code': e.code}
    except OSError as e:
        res = {'status': 'halt', 'code': 'DISK_FULL' if e.errno in (errno.ENOSPC, errno.EDQUOT) else 'WRITE_FAILED'}
    durable.remove(env.p.foreground)
    absorb(env, kind, info, res)


def absorb(env, kind, info, res):
    """§7.2 step 4 in memory: halt is a STOP (or a committed HALT, run_command); pending continues with the SAVE block
    (env.pending is set); place and selftest record their result in RESTORE_WORK; fingerprint resets the PASS."""
    if res.get('status') == 'halt':
        raise Halt('STOP', res['code'], 'the stage stopped')
    if kind == 'place' and env.work is not None:
        env.work['placed'], env.work['placed_list'] = True, res.get('placed') or []
        if res.get('files_found') is not None:
            env.work['resolve'] = dict(env.work['resolve'], placed=True, files_found=res['files_found'])
        save_work(env)
    if kind == 'selftest' and env.work is not None:
        env.work['selftest_dir'] = info['dir']
        save_work(env)
    if res.get('status') == 'fingerprint' and env.cache is not None:
        env.cache['pass'], env.cache['fingerprint_sha256'] = None, res['fingerprint']
        save_cache(env)
