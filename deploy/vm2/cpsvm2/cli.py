"""go / found / answer (spec §6): the glue that carries out the Steps core returns and decides nothing itself.
Prologue: layout, HelperLock (busy: CPSV-BUSY, exit 4), the cache, a dead stage, cleanup, the clear check of a local
stop (delta v2.1 §2.4.3), owed post actions; then a pending commit (§5), the session (§8) and next_action (§7.1). Only
`go` runs a stage, in its own foreground (§X.7.2). Exit 0 follow, 3 STOP, 4 refused (do the block after REFUSED), 2."""
import errno
import os
import re
import secrets
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
                          kit_members, md5_file, now_dt, parse_utc, remove_tree, require_space, sha_bytes, sha_file,
                          sjson, unpack_kit, validate_pass)

WORK_SCHEMA, BLOCK_SCHEMA, HALT_SCHEMA = 'cps.vm2-restore-work.v1', 'cps.vm2-block.v1', 'cps.vm2-halt.v1'
FG_SCHEMA = 'cps.vm2-foreground.v1'
SETUP_DONE, SETUP_FAILED = 'var/cps_vm2_setup_ok', 'var/cps_vm2_setup_failed'
BARE_HDR = 'CPSV series=none head=000000 kit=none at=000000-0000-000000 mode=setup state='
ASKS = savepoint.SLIP_ASKS


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
        self.mode, self.command, self.argv, self.refusal = 'setup', 'go', [], None
        self.cache = self.pending = self.block = self.work = None
        cp = lay.config_path
        if cp.is_file():
            self.adopt(cp.read_bytes(), lay.release_path.read_bytes() if lay.release_path.is_file() else b'{}')

    def adopt(self, cfg_raw, rel_raw):
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
        return (self.cfg or {}).get('gates') or {}

    @property
    def upload_cfg(self):                       # before a kit is read, the cap alone (S-01)
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

    def known_ids(self, name):                  # rule V (a): ids recorded for the name
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
        c = self.cache or {}
        if (c.get('head') or {}).get('name') == name:
            return c['head']['id']
        for cf in c.get('confirms') or []:
            if cf['name'] == name and cf['copies']:
                return cf['copies'][0]['id']
        got = (self.state or {}).get('files', {}).get(name)
        return got[0][0] if got else None


def fresh(env, prefix, ext=''):
    """A new path outbox/v2/<prefix><utc14>[_n]<ext>."""
    base, n = str(env.v2 / (prefix + host.utc14(env.now()))), 1
    p = base + ext
    while os.path.lexists(p):
        n += 1
        p = '%s_%d%s' % (base, n, ext)
    return Path(p)


def invalidate(env, prefix):
    """Move the cache files, every file under BASE/attest and every entry of BASE/inbox except the boot mark into
    outbox/v2/<prefix><utc14>/ (never deleted, SD-68); the prefix cleared_ also moves HALT.json. Returns the folder."""
    dest = fresh(env, prefix)
    dest.mkdir(parents=True)
    for p in (env.p.state, env.p.pending, env.p.block, env.p.work) + ((env.p.halt,) if prefix == 'cleared_' else ()):
        if os.path.lexists(p):
            os.replace(p, dest / p.name)
    for root in (env.p.attest, env.lay.inbox):
        for x in (sorted(root.iterdir()) if root.is_dir() else []):
            if x.name != '.boot':
                (dest / root.name).mkdir(exist_ok=True)
                os.replace(x, dest / root.name / x.name)
    durable.fsync_dir(env.v2)
    return dest


def load_cache(env):
    """§2.5 steps 1-2: a failure invalidates the cache (invalid_<utc14>/). A BLOCK.json behind STATE's head moves
    alone, one ahead invalidates (OPX-07); so does halt_local without HALT.json (SD-64)."""
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
    if wk is not None:
        bad = bad or wk.get('boot_id') != env.boot
    if ((st or {}).get('halt_local') or (wk or {}).get('halt_local')) and not os.path.lexists(env.p.halt):
        bad = True
    if bl is not None and st is not None and not bad:
        if bl.get('head_seq', -1) > hs:
            bad = True
        elif bl.get('head_seq') != hs:
            d = fresh(env, 'invalid_')
            d.mkdir(parents=True)
            os.replace(env.p.block, d / 'BLOCK.json')
            bl = None
    if bad:
        invalidate(env, 'invalid_')
        st = pe = bl = wk = None
    env.cache, env.pending, env.block, env.work = st, pe, bl, wk


def save_cache(env):
    env.cache['written_utc'] = env.now()
    durable.write_doc(env.p.state, env.cache)


def save_work(env):
    durable.write_doc(env.p.work, env.work)


def new_work(env, operator=None, cleared_local=None, moved_pending=None):
    hint = hint_doc(env)
    env.work = {'schema': WORK_SCHEMA, 'boot_id': env.boot, 'phase': 'LAYOUT', 'done': [], 'operator': operator,
                'hint': {'seq': int(hint['seq']) if hint.get('seq') else None, 'kit': hint.get('kit')},
                'approval': None, 'lookups': [], 'head': None, 'head_error': None, 'identity': None, 'kit': None,
                'head_kit': None, 'list_shows_none': None, 'resolve': {}, 'placed': False, 'placed_list': [],
                'reuploaded': False, 'committed': None, 'fetched': {}, 'fingerprint': None, 'pass': None,
                'setup_loop': None, 'selftest_dir': None, 'selftest_died': False, 'kit_route': None, 'slips': 0,
                'cleared_local': cleared_local, 'moved_pending': moved_pending}
    save_work(env)


def hint_doc(env):
    try:
        d = sjson(env.p.hint.read_bytes()) if env.p.hint.is_file() else {}
    except (ValueError, UnicodeDecodeError):
        d = {}
    return d if isinstance(d, dict) else {}


def hint_kit(env):
    k = hint_doc(env).get('kit')
    return k if N.fm(N.HEX12, k) else None


# ================================================================ printing and stops (§6.1, §13)
def basis(env):
    return N.sha(N.cjson([(env.cache or {}).get('self_sha256'), (env.pending or {}).get('self_sha256'),
                          (env.work or {}).get('self_sha256')]))


def emit(env, state_code, blk, expect, hdr=None):
    """Print one block (after a slip's REFUSED line: exit 4), recorded in BLOCK.json first. Raises Out(exit)."""
    lines = render(env, state_code, blk, expect, hdr)
    if env.refusal:
        lines = lines[:1] + [env.refusal] + lines[1:]
    print('\n'.join(lines), flush=True)
    raise Out(4 if env.refusal else 3 if blk.do[0] == 'STOP' else 0)


def render(env, state_code, blk, expect, hdr=None):
    """The block's lines; each DOWNLOAD target's folder exists and holds nothing (S-09); BLOCK.json (its refusal count
    kept for the same template) is written durably."""
    for _, _, p in blk.downloads:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if os.path.lexists(p):
            remove_tree(p)
    body = drive.body_lines(blk, str(env.lay.vm))
    hs, old = env.head_seq(), env.block
    step, refused = 1, 0
    if old is not None and old.get('head_seq') == hs:
        step, refused = (old['step'], old.get('refused', 0)) if old.get('template') == body else (old['step'] + 1, 0)
    if step > 9999:
        raise Halt('STOP', 'INTERNAL_STEP_OVERFLOW', 'too many blocks at one head')
    at = N.at_string(hs, step, (env.cache or {}).get('state_sha256') or basis(env),
                     (env.pending or {}).get('self_sha256'), body)
    w = env.work or {}
    hseq, kit = hdr or (hs or ((w.get('head') or {}).get('entry') or {}).get('seq'),
                        (env.cache or {}).get('kit_sha256') or (w.get('kit') or {}).get('sha256'))
    lines = [drive.header(env.series or 'none', hseq, kit, at, env.mode, state_code)] + \
        [ln.replace(drive.AT_MARK, at) for ln in body]
    if drive.check_grammar(lines):
        raise Halt('STOP', 'INTERNAL_PRINT', 'a block breaks the grammar')
    if os.path.isdir(env.v2):
        env.block = durable.write_doc(env.p.block, {
            'schema': BLOCK_SCHEMA, 'at': at, 'step': step, 'head_seq': hs, 'state_code': state_code, 'lines': lines,
            'template': body, 'expect': expect, 'basis': basis(env), 'printed_utc': env.now(), 'refused': refused})
    return lines


def stop_block(env, code, handback='C', detail=None):
    """A STOP block; every HANDBACK C stop but RELEASE_GATE_OPEN is local sticky (HALT.json, SD-56), its header the
    head and kit a clear names."""
    hdr = None
    if handback == 'C' and code != 'RELEASE_GATE_OPEN' and os.path.isdir(env.v2):
        h = write_halt(env, code, detail)
        hdr = (h['head_seq'], h['kit_sha256'])
    args = {'code': code, 'handback': handback}
    emit(env, 'FINAL' if code == 'FINAL' else 'STOP', PrintBlock('STOP', do=('STOP', args)), {'command': 'none'}, hdr)


def write_halt(env, code, detail):
    """HALT.json (delta v2.1 §2.4.1), an older one kept as halt_<utc14>.json, a FORK's downloads moved to fork_<utc14>/
    (S-03), halt_local in STATE.json and RESTORE_WORK."""
    if os.path.lexists(env.p.halt):
        os.replace(env.p.halt, fresh(env, 'halt_', '.json'))
    if code in ('FORK', 'LINK_MISMATCH'):
        d = fresh(env, 'fork_')
        for sub in ('verify', 'journal'):
            for x in (sorted((env.lay.inbox / sub).iterdir()) if (env.lay.inbox / sub).is_dir() else []):
                (d / sub).mkdir(parents=True, exist_ok=True)
                os.replace(x, d / sub / x.name)
    c, w = env.cache or {}, env.work or {}
    hd = (w.get('head') or {}).get('entry') or {}
    st = c.get('state') or hd.get('state') or {}
    seq = (st.get('halt') or {}).get('seq') if code.startswith('HALTED_') else \
        (c.get('head') or {}).get('seq') or hd.get('seq')
    kit = st.get('kit_sha256') or (w.get('kit') or {}).get('sha256')
    tried = {x[:12] for x in (kit, c.get('kit_sha256') or (w.get('kit') or {}).get('sha256'), hint_kit(env)) if x}
    h = durable.write_doc(env.p.halt, {'schema': HALT_SCHEMA, 'series': env.series, 'code': code, 'head_seq': seq or 0,
                                       'kit_sha256': kit, 'tried': sorted(tried), 'check': None,
                                       'detail': detail or {}, 'created_utc': env.now()})
    for doc, path in ((env.cache, env.p.state), (env.work, env.p.work)):
        if doc is not None:
            doc['halt_local'] = {'code': code, 'head_seq': h['head_seq']}
            durable.write_doc(path, doc)
    return h


def halt_out(env, h):
    emit(env, 'STOP', PrintBlock('STOP', do=('STOP', {'code': h['code'], 'handback': 'C'})), {'command': 'none'},
         (h['head_seq'], h['kit_sha256']))


def wait_out(env, seconds, code='WORK'):
    emit(env, code, PrintBlock(code, do=('WAIT', {'seconds': int(max(1, seconds))})), {'command': 'go'})


def bare(lines, code):
    print('\n'.join(lines), flush=True)
    raise Out(code)


def reprint(env, line=None, code=0):
    """The current block again without its UPLOAD lines (SD-60)."""
    ls = env.block['lines']
    bare(ls[:1] + ([line] if line else []) + [ln for ln in ls[1:] if not ln.startswith('UPLOAD ')], code)


def count(env, code):
    """D3b: a refusal of this block, written durably; the fourth is SLIP_LIMIT (in a clear check: the check ends)."""
    b = env.block
    b['refused'] = b.get('refused', 0) + 1
    durable.write_doc(env.p.block, b)
    if b['refused'] > ASKS:
        if b['expect'].get('kind') == 'clear':
            end_check(env, durable.read_doc(env.p.halt, HALT_SCHEMA, sjson)[0])
        stop_block(env, 'SLIP_LIMIT', detail={'last': code})


def refuse(env, code):
    if env.block is None:
        bare(['REFUSED ' + code], 4)
    if code.split()[0] not in ('HELPER_BUSY', 'JOB_BUSY'):
        count(env, code.split()[0])
    reprint(env, 'REFUSED ' + code, 4)


def usage(env, text):                         # counted (D3b), exit 2, no REFUSED line
    if env.block is not None:
        count(env, 'USAGE')
    bare((env.block or {}).get('lines') or [text], 2)


# ================================================================ entry drafts and commits (§3.4, §5.1 steps 1-4)
def draft(env, kind, body, seq=None):
    seq = seq or env.head_seq() + 1
    c = env.cache or {}
    return {'schema': E.SCHEMA, 'series': env.series, 'seq': seq, 'name': N.entry_name(env.series, seq),
            'kind': kind, 'body': body, 'utc': env.now(), 'boot_id': env.boot, 'uid': os.getuid(),
            'home': env.lay.home, 'fingerprint_sha256': c.get('fingerprint_sha256'),
            'helper': {'version': N.HELPER_VERSION, 'tree_sha256': host.helper_tree_sha256()},
            'runner_sha256': N.RUNNER_SHA256, 'kit_sha256': c.get('kit_sha256'),
            'release_sha256': sha_bytes(env.rel_raw),
            'cleared_local': c.get('cleared_local') if kind in ('RESTORE', 'GENESIS') else None}


def completer(env):                           # §5.1 step 2
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


# ================================================================ the upload loops (§5.1 steps 5-8, S-01)
def persist(env, loop, key):
    if key is None:
        env.pending = durable.write_doc(env.p.pending, loop)
    else:
        save_work(env)


def loop_block(env, loop, state_code, key=None):
    """PENDING (key None) or the setup-file loop RESTORE_WORK[key]: True when confirmed, else its next block."""
    b = savepoint.block(loop, env.upload_cfg['max_upload_bytes'], env.gates.get('p2_lag_seconds'),
                        env.series and env.series_folder, reprint=bool(env.refusal))
    if b is None:
        return True
    persist(env, loop, key)
    ups, finds, dls, do, names = b
    kind = 'pending' if key is None else 'setup'
    exp = {'command': 'found', 'names': names, 'kind': kind, 'loop': key, 'uploaded': do[1]['uploaded']} \
        if do[0] == 'ATTEST_FOUND' else {'command': 'go', 'kind': kind, 'loop': key}
    emit(env, state_code, PrintBlock(state_code, ups, finds, dls, do), exp)


def loop_verify(env, loop, key):              # a slip re-FINDs (bounded); a FORK keeps its bytes
    r = savepoint.on_verify(loop)
    if r[0] == 'slip':
        lim = savepoint.slip(loop, r[2], r[1])
        persist(env, loop, key)
        if lim:
            stop_block(env, 'SLIP_LIMIT', detail={'name': r[2], 'last': r[1]})
        env.refusal = 'REFUSED %s %s' % (r[1], r[2])
        return
    if r[0] == 'stop':
        raise Halt('STOP', 'FORK', 'a copy differs')
    persist(env, loop, key)


def pending_step(env):
    if loop_block(env, env.pending, 'SAVE'):
        finish_commit(env)


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


def run_post(env):                            # §5.4, each removed from STATE.post as it completes
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


# ================================================================ prologue, dispatch and the clear check (§6.7)
def main(argv):
    if not argv or argv[0] not in ('go', 'found', 'answer'):
        print('usage: vm2.py go | found --at A --raw FILE ... | answer --at A k=v ...')
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
    """§X.6.2: another command holds the lock; FOREGROUND.json is read without it; nothing changes; exit 4."""
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
    env.command, env.argv = argv[0], argv
    try:
        load_cache(env)
        died = foreground_check(env)
        cleanup_leftovers(lay)
        if died:
            stop_block(env, died)
        w = env.work
        if w and w.get('phase') != 'DONE' and 'CONFIG' in w['done'] and w.get('installed') != w['kit']['sha256']:
            m = kit_members(w['kit']['path'])               # the kit being taken in, before it is installed
            env.adopt(m['VM_HELPER_CONFIG.json'], m['RELEASE.json'])
        clear_check(env)
        if env.cache is not None and env.cache.get('post') and env.pending is None:
            run_post(env)                   # S-04: owed by an earlier command; a pending commit finishes first
        if argv[0] == 'go':
            if len(argv) > 1:
                usage(env, 'usage: vm2.py go')
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
            stop_block(env, code, detail=h.detail if isinstance(h.detail, dict) else None)
        except Out as o:
            return o.code
        except (Halt, durable.DurableError) as h2:
            return safe_stop(env, getattr(h2, 'code', 'WRITE_FAILED'))
    except OSError as e:                                    # S-11
        return safe_stop(env, durable.DurableError(e.errno).code)
    return 0


def safe_stop(env, code):
    try:
        stop_block(env, code)
    except Out as o:
        return o.code
    except (Halt, durable.DurableError, OSError):
        print(BARE_HDR + 'STOP\nDO: STOP %s HANDBACK C' % code)
        return 3


def clear_check(env):
    """Delta v2.1 §2.4.3 (O59): a local stop stays until the kit HINT.json names (not in `tried`) is found, downloaded
    and names exactly this stop with a settings-only change; then it all moves aside and this `go` restores."""
    h, why = durable.read_doc(env.p.halt, HALT_SCHEMA, sjson)
    if h is None and why is None:
        return
    if h is None:
        stop_block(env, 'UNCLASSIFIED')                     # a damaged HALT.json is replaced, never ignored
    k, b = hint_kit(env), env.block
    if env.command == 'found' and h['check'] and b and b['expect'].get('kind') == 'clear':
        do_found(env, env.argv[1:])
        h = durable.read_doc(env.p.halt, HALT_SCHEMA, sjson)[0]
    elif env.command != 'go' or k is None or k in h['tried']:
        halt_out(env, h)
    name = 'SESSION_KIT_%s.zip' % k
    c, target = h['check'], env.v2 / 'clear' / name
    if c is None or c['kit12'] != k:
        c = h['check'] = {'kit12': k, 'copies': None, 'slips': 0, 'dl': False}
        durable.write_doc(env.p.halt, h)
    find = PrintBlock('KIT', finds=((N.FOLDERS['setup'], 'NAME', name),), do=('ATTEST_FOUND', {'names': [name]}))
    if c['copies'] is None:
        emit(env, 'KIT', find, {'command': 'found', 'names': [name], 'kind': 'clear'})
    if not c['copies']:
        h['check'] = None
        durable.write_doc(env.p.halt, h)
        halt_out(env, h)
    if not c['dl']:
        c['dl'] = True
        durable.write_doc(env.p.halt, h)
        emit(env, 'KIT', PrintBlock('KIT', downloads=((N.FOLDERS['setup'], c['copies'][0][0], str(target)),)),
             {'command': 'go', 'kind': 'clear'})
    code = 'DOWNLOAD_MISSING' if not target.is_file() else 'DOWNLOAD_INCOMPLETE' \
        if os.lstat(target).st_size != c['copies'][0][1] else None
    if code:
        if os.path.lexists(target):
            os.unlink(target)
        c.update(copies=None, dl=False, slips=c['slips'] + 1)
        if c['slips'] > ASKS:
            end_check(env, h)
        durable.write_doc(env.p.halt, h)
        env.refusal = 'REFUSED %s %s' % (code, name)
        emit(env, 'KIT', find, {'command': 'found', 'names': [name], 'kind': 'clear'})
    w = env.work or {}
    try:
        cand, m = kit_dict(target), kit_members(target)
        host.load_config(m['VM_HELPER_CONFIG.json'], sjson(m['RELEASE.json']), N.check_config_patterns,
                         N.UPLOAD_CAP_BYTES, N.STAGE_KEYS)
    except (Halt, ValueError, UnicodeDecodeError):
        cand = {'sha256': sha_file(target), 'config': None}                 # verdict 'members' (or 'sha')
    if S.clear_verdict(h, cand, [x for x in ((env.cache or {}).get('kit'), w.get('kit'), w.get('head_kit')) if x]):
        end_check(env, h)
    do_clear(env, h, target)


def kit_dict(path):
    m = kit_members(path)
    if not {'RELEASE.json', 'VM_HELPER_CONFIG.json'} <= set(m):
        raise Halt('STOP', 'KIT_NOT_VERIFIED', 'a kit member is missing')
    return {'sha256': sha_file(path), 'path': str(path), 'members': sorted([k, sha_bytes(v)] for k, v in m.items()),
            'config': sjson(m['VM_HELPER_CONFIG.json']), 'release_sha256': sha_bytes(m['RELEASE.json'])}


def end_check(env, h):                        # a refused candidate: tried, and the stop again
    h['tried'], h['check'] = sorted(set(h['tried']) | {h['check']['kit12']}), None
    durable.write_doc(env.p.halt, h)
    halt_out(env, h)


def do_clear(env, h, target):
    """Delta v2.1 §2.4.3 steps 1-4: invalidate(cleared_), the candidate becomes the session's kit, a new RESTORE_WORK
    carries cleared_local and the moved PENDING."""
    c, w, pe = env.cache or {}, env.work or {}, env.pending
    moved = {'seq': pe['seq'], 'name': pe['entry']['name'], 'sha256': pe['entry']['sha256'],
             'uploaded': sorted(n for n, t in pe['tries'].items() if t['uploads'])} if pe else None
    cl = None if h['code'].startswith('HALTED_') else {'code': h['code'], 'head_seq': h['head_seq'],
                                                       'kit_sha256': h['kit_sha256']}
    invalidate(env, 'cleared_')
    (env.lay.inbox / 'kit').mkdir(parents=True, exist_ok=True)
    os.replace(target, env.lay.inbox / 'kit' / target.name)
    env.cache = env.pending = env.block = None
    new_work(env, c.get('operator') or w.get('operator'), cl, moved)


def foreground_check(env):
    """§X.7.2 step 4: a FOREGROUND.json under the lock means its writer died. Another boot's moves to invalid_; this
    boot's to dead_<utc14>.json, then a self-test at attempt 1 runs again, else the stop to print after the cleanup."""
    fg, why = durable.read_doc(env.p.foreground, FG_SCHEMA, sjson)
    if fg is None and why is None:
        return None
    if fg is None or fg.get('boot_id') != env.boot:
        d = fresh(env, 'invalid_')
        d.mkdir(parents=True)
        os.replace(env.p.foreground, d / 'FOREGROUND.json')
        return None
    os.replace(env.p.foreground, fresh(env, 'dead_', '.json'))
    durable.fsync_dir(env.v2)
    if fg['kind'] == 'selftest' and fg.get('attempt') == 1 and env.work is not None:
        env.work['selftest_died'], env.work['selftest_dir'] = True, None
        save_work(env)
        return None
    return 'SELFTEST_DIED' if fg['kind'] == 'selftest' else 'FOREGROUND_DIED'


def go_checks(env):
    """A `go`: the block again when it expects found or answer; after a DOWNLOAD block, the download check (a confirmed
    id's file is refused, any other is a slip)."""
    b = env.block
    if not b:
        return
    ex = b['expect']
    if ex.get('command') in ('found', 'answer') and b.get('basis') == basis(env):
        reprint(env)
    if ex.get('command') != 'go' or b.get('basis') != basis(env):
        return
    if ex.get('kind') == 'pending' and env.pending and env.pending['verify']:
        loop_verify(env, env.pending, None)
    elif ex.get('kind') == 'setup' and (env.work or {}).get(ex['loop']) and env.work[ex['loop']]['verify']:
        loop_verify(env, env.work[ex['loop']], ex['loop'])
    elif ex.get('kind') in ('local', 'fetch'):
        for p, (name, size) in ex['dl'].items():
            code = 'DOWNLOAD_MISSING' if not os.path.isfile(p) else 'DOWNLOAD_INCOMPLETE' \
                if os.lstat(p).st_size != size else None
            if code and ex['kind'] == 'local':
                refuse(env, code)
            if code:
                return session_slip(env, name, code, list(ex['dl']))


def session_slip(env, name, code, paths):
    """The slip rule in RESTORE_WORK (delta v2.1 §2.2.1): the downloads go, `name`'s lookups are void (its ids leave
    `verified`, `fetched` forgets it), the slip is counted; the next block (its FIND) follows the REFUSED line."""
    w = env.work
    for p in paths:
        if os.path.lexists(p):
            os.unlink(p)
    ids = set()
    for lk in w['lookups']:
        if lk['name'] == name:
            lk['void'] = True
            ids |= {c[0] for c in lk['copies']}
    w['verified'] = {k: v for k, v in (w.get('verified') or {}).items() if k not in ids}
    w['fetched'].pop(name, None)
    w['slips'] = w.get('slips', 0) + 1
    save_work(env)
    if w['slips'] > ASKS:
        stop_block(env, 'SLIP_LIMIT', detail={'name': name, 'last': code})
    env.refusal = 'REFUSED %s %s' % (code, name)


# ================================================================ found (§6.2, delta v2.1 §2.3)
def do_found(env, args):
    b = env.block
    try:
        at, raw, items, refused = drive.parse_found(args)
    except drive.Usage:
        usage(env, 'usage: found --at A --raw FILE [--refused NAME]')
    if b is None or at != b['at']:
        refuse(env, 'STALE_AT')
    ex = b['expect']
    if ex.get('command') != 'found':
        refuse(env, 'COMMAND_NOT_EXPECTED')
    if any(n not in (ex.get('uploaded') or ()) for n in refused):
        refuse(env, 'FOUND_SYNTAX')
    names = ex.get('names') or []

    def id_ok(v):
        return N.check_value('id', 'ID', v, env.idcfg()) is None
    if raw is not None:
        if not os.path.isabs(raw) or os.path.islink(raw) or not os.path.isfile(raw):
            refuse(env, 'RAW_INVALID missing')
        data = Path(raw).read_bytes() if os.lstat(raw).st_size <= N.RAW_MAX_BYTES else None
        try:
            doc = sjson(data)
        except (ValueError, UnicodeDecodeError, TypeError):
            refuse(env, 'RAW_INVALID json')
        why, got = drive.parse_raw(doc, names, id_ok)
        if why:
            refuse(env, 'RAW_INVALID ' + why)
        (env.v2 / 'raw').mkdir(exist_ok=True)
        os.replace(raw, fresh(env, 'raw/' + at + '_', '.json'))                     # consumed (SD-61)
    else:
        if any(N.forbidden(v) for it in items for v in [it[0]] + it[1]):
            refuse(env, 'VALUE_FORBIDDEN')
        code, got = drive.manual_copies(items, names, id_ok)
        if code:
            refuse(env, code)
    kind = ex.get('kind')
    if kind in ('pending', 'setup'):
        loop = env.pending if kind == 'pending' else env.work[ex['loop']]
        r, c = savepoint.on_found(loop, got, set(refused), env.known_ids, str(env.lay.inbox / 'verify'))
        if r == 'stop':
            raise Halt('STOP', c, 'found')
        persist(env, loop, ex.get('loop'))
        if r == 'handback':          # §X.5.6 step 4: not sticky, not in HALT.json; the next `go` FINDs first
            emit(env, b['state_code'], PrintBlock('STOP', do=('STOP', {'code': 'UPLOAD_REFUSED', 'handback': 'A',
                                                                       'name': c})), {'command': 'go', 'kind': kind})
        return
    if kind == 'clear':
        h = durable.read_doc(env.p.halt, HALT_SCHEMA, sjson)[0]
        h['check']['copies'] = got[names[0]]
        durable.write_doc(env.p.halt, h)
        return
    now = env.now()
    for name in names:
        if kind == 'fetch':
            env.work['fetched'][name] = got[name]
        else:
            lk = {'name': name, 'result': 'present' if got[name] else 'absent', 'copies': got[name], 'utc': now}
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
        usage(env, 'usage: answer --at A key=value ...')
    if b is None or at != b['at']:
        refuse(env, 'STALE_AT')
    ex = b['expect']
    if ex.get('command') != 'answer':
        refuse(env, 'COMMAND_NOT_EXPECTED')
    ctx, now = ex['context'], env.now()
    win = {k: [lo, now] for k, (lo, _) in (ctx.get('window') or {}).items()}
    err, got = N.check_answers(ex['keys'], pairs, env.idcfg(ctx.get('case') or ''), win)
    if err:
        refuse(env, '%s %s' % err)
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
def done(env, phase):
    if phase not in env.work['done']:
        env.work['done'].append(phase)
    save_work(env)


def dl_map(env, downloads):                   # {target: [name, the size this session's FINDs attested]}
    sizes = {c[0]: c[1] for lk in env.work['lookups'] if not lk.get('void') for c in lk['copies']}
    return {p: [re.sub(r'\.[0-9]+$', '', os.path.basename(p)), sizes.get(did)] for _, did, p in downloads}


def session_step(env):
    phase, st = S.session_next({'work': env.work, 'series': env.series or 'Q1', 'gates': env.gates, 'now': env.now(),
                                'clear': (env.cfg or {}).get('clear'), 'base': str(env.lay.base),
                                'transcript_ext': (env.cfg or {}).get('transcript_ext', 'json')})
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
    if st.downloads:
        dl, b = dl_map(env, st.downloads), env.block
        if env.command == 'go' and b and b['expect'].get('dl') == dl and not env.refusal:
            return session_downloads(env, phase, st.downloads, dl)
        emit(env, st.state_code, st, {'command': 'go', 'kind': 'session', 'dl': dl})
    if st.do[0] == 'END_CONVERSATION':
        w['resolve'] = dict(w['resolve'], end=True)
        save_work(env)
    if st.do[0] == 'EXPORT_TRANSCRIPT':
        w['resolve'] = dict(w['resolve'], export=True, export_to=st.do[1]['to'])
        save_work(env)
    if st.do[0] == 'ATTEST_FOUND':
        emit(env, st.state_code, st, {'command': 'found', 'names': st.do[1]['names'], 'kind': 'session'})
    emit(env, st.state_code, st, {'command': 'go', 'kind': 'session'})


def session_downloads(env, phase, downloads, dl):
    """The session's download check (delta v2.1 §2.1, §2.2): a missing file or another size than attested is a slip;
    every copy is hashed into `verified`; the head N's copies go to verify_head; a journal copy 1 is kept as
    inbox/journal/<name>; the others stay until the RESTORE's DROP_DOWNLOADS (FORK evidence)."""
    w = env.work
    for p, (name, size) in dl.items():
        if not os.path.isfile(p) or os.lstat(p).st_size != size:
            return session_slip(env, name, 'DOWNLOAD_MISSING' if not os.path.isfile(p) else 'DOWNLOAD_INCOMPLETE',
                                list(dl))
    ver = dict(w.get('verified') or {})
    for _, did, p in downloads:
        ver[did] = [sha_file(p), os.lstat(p).st_size]
    w['verified'] = ver
    if phase == 'HEAD' and not w.get('head'):
        return verify_head(env, [x[2] for x in downloads], {ver[x[1]][0] for x in downloads})
    for _, _, p in downloads:
        if os.path.dirname(p) == str(env.lay.inbox / 'journal') and p.endswith('.1') and not os.path.lexists(p[:-2]):
            os.replace(p, p[:-2])
    save_work(env)


def verify_head(env, paths, shas):
    """§8.4 step 3: N's copies agree (and hold the moved PENDING's bytes when N is its seq, else FORK); then Archive,
    validate_entry, state sha, helper tree, runner pin, release; a failure is its code (C1)."""
    w = env.work
    mp = w.get('moved_pending') or {}
    path = re.sub(r'\.[0-9]+$', '', paths[0])
    if len(shas) > 1 or (mp.get('name') == os.path.basename(path) and shas != {mp['sha256']}):
        w['head_error'] = 'FORK'
        return save_work(env)
    os.replace(paths[0], path)
    code = None
    try:
        man = savepoint.read_entry(path)
    except Halt:
        man, code = None, 'HEAD_CORRUPT'
    if man is not None:
        pr = E.validate_entry(man, cfg={'series': env.series,
                                        'accepted_helper_tree_sha256': env.cfg['accepted_helper_tree_sha256']})
        code = None if not pr else 'HELPER_UNKNOWN' if any('helper' in x or 'runner' in x for x in pr) else \
            'STATE_SHA_MISMATCH' if pr == ['state_sha256'] else 'SCHEMA_INVALID'
        if code is None and man['release_sha256'] != man['state']['genesis']['release_sha256'] and \
                man['release_sha256'] not in env.cfg['accepts_release_sha256']:
            code = 'RELEASE_NOT_ACCEPTED'
    if code:
        w['head_error'] = code
    else:
        w['head'] = {'entry': man, 'sha256': sha_file(path), 'bytes': os.lstat(path).st_size, 'md5': md5_file(path),
                     'path': str(path)}
    save_work(env)


def ph_layout(env):
    env.work['identity'] = {'home': env.lay.home, 'uid': os.getuid()}
    done(env, 'LAYOUT')


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
    """The setup-file loop for files kept in RESTORE_WORK[key]: prints the next block, or returns True once every file
    is confirmed."""
    w = env.work
    if w.get(key) is None:
        for p, _, _ in files:
            if os.lstat(p).st_size > env.upload_cfg['max_upload_bytes']:
                raise Halt('STOP', 'UPLOAD_TOO_LARGE', 'a report file over max_upload_bytes')
        w[key] = savepoint.setup_loop(files)
        save_work(env)
    return loop_block(env, w[key], state_code, key)


def fetch(env, folder, name, local):
    """FIND then DOWNLOAD one file by exact name (kit, head kit). Returns the local path once present."""
    if os.path.isfile(local):
        return local
    cps = env.work['fetched'].get(name)
    if cps is None:
        emit(env, 'KIT', PrintBlock('KIT', finds=((folder, 'NAME', name),), do=('ATTEST_FOUND', {'names': [name]})),
             {'command': 'found', 'names': [name], 'kind': 'fetch'})
    if not cps:
        return None
    emit(env, 'KIT', PrintBlock('KIT', downloads=((folder, cps[0][0], str(local)),)),
         {'command': 'go', 'kind': 'fetch', 'dl': {str(local): [name, cps[0][1]]}})


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
    w['kit'] = kit_dict(use)
    done(env, 'KIT')


def kit_bytes(env):
    return kit_members(env.work['kit']['path'])


def ph_config(env):
    """The kit's config and release in use; its TOOL_INVENTORY.txt is the list its sha256 key pins (D9)."""
    m = kit_bytes(env)
    env.adopt(m['VM_HELPER_CONFIG.json'], m['RELEASE.json'])
    inv = m.get('TOOL_INVENTORY.txt')
    if inv is None or sha_bytes(inv) != env.cfg['tool_inventory_sha256'] or N.tool_list(inv) is None:
        raise Halt('STOP', 'CONFIG_INVALID', 'TOOL_INVENTORY.txt')
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
    """§8.3: FIND the PASS of this fingerprint; every copy is downloaded and validated; none valid: the self-test runs
    and its PASS is uploaded through the setup-file loop."""
    w, setup = env.work, N.FOLDERS['setup']
    name = 'FINGERPRINT_PASS_%s.json' % fp
    if w.get('setup_loop') is None and not w.get('selftest_dir'):
        if name not in w['fetched']:
            fetch(env, setup, name, env.lay.inbox / 'pass' / name)
        cps = w['fetched'][name] or []
        lps = [env.lay.inbox / 'pass' / ('%s.%d' % (name, k)) for k in range(1, len(cps) + 1)]
        dl = tuple((setup, c[0], str(lp)) for c, lp in zip(cps, lps) if not lp.is_file())
        if dl:
            emit(env, 'KIT', PrintBlock('KIT', downloads=dl), {'command': 'go', 'kind': 'fetch', 'dl': {
                str(lp): [name, c[1]] for c, lp in zip(cps, lps)}})
        for c, lp in zip(cps, lps):
            if validate_pass(env.ctx2(), lp.read_bytes(), fp):
                return accept_pass(env, {'name': name, 'md5': md5_file(lp), 'size': os.lstat(lp).st_size})
        return start_selftest(env, fp)
    if w.get('setup_loop') is None:
        return finish_selftest(env, fp)
    if upload_files(env, 'setup_loop', None, 'SELFTEST'):
        f = [x for x in w['setup_loop']['parts'] if x['name'] == name][0]
        w['setup_loop'] = None
        return accept_pass(env, {'name': name, 'md5': f['md5'], 'size': f['bytes']})


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
    env.work['head_kit'] = kit_dict(lp)
    save_work(env)


IO_PHASES = {'LAYOUT': ph_layout, 'SETUP': ph_setup, 'KIT': ph_kit, 'CONFIG': ph_config,
             'FINGERPRINT': ph_fingerprint, 'PASS': ph_pass, 'CLOCK': ph_clock, 'KIT_ACCEPT': ph_kit_accept}


def build_state(env):
    """STATE.json for the session's commit (§2.3): the head found on Drive (or none), the confirms of its files as
    found (missing head parts with no copy; a copy that is ours has the file's own size), and this boot's operator,
    kit, fingerprint, PASS and cleared_local."""
    w = env.work
    head = state = None
    confirms = []
    if w.get('head'):
        man = w['head']['entry']
        cps = {}
        for lk in w['lookups']:
            for c in [] if lk.get('void') else lk['copies']:
                cps.setdefault(lk['name'], {})[c[0]] = c
        hc = sorted(cps.get(man['name'], {}).values())
        head = {'seq': man['seq'], 'name': man['name'], 'id': hc[0][0], 'md5': w['head']['md5'],
                'bytes': w['head']['bytes'], 'sha256': w['head']['sha256']}
        confirms = [{'name': man['name'], 'copies': [{'id': c[0], 'md5': head['md5'], 'size': head['bytes']}
                                                     for c in hc]}]
        for p in man['parts']:
            confirms.append({'name': p['name'], 'copies': [{'id': c[0], 'md5': p['md5'], 'size': p['bytes']}
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
                 'confirms': confirms, 'cleared_local': w.get('cleared_local'), 'written_utc': env.now()}
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
    """GENESIS (§7.12) or RESTORE (§8.7); the RESTORE's entry kit is its body's (SD-51: kept while HALTED)."""
    build_state(env)
    install_kit(env)
    if st.entry['kind'] == 'GENESIS':
        return genesis(env, st.entry['body'])
    w, b = env.work, dict(st.entry['body'])
    d = draft(env, 'RESTORE', None)
    d['kit_sha256'] = b['kit_sha256']
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
            'jobs': None, 'ledger': None, 'layout': F.layout_of(str(lay.base)), 'gates': env.cfg['gates'],
            'pass': w['pass'], 'other_series_absent': sb.get('other_series_absent'), 'approval': sb['approval']}
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
        body['jobs'] = F.jobs_of(sjson(jraw))
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
    ser, names = env.series, []
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
    """Print DOWNLOAD lines for the journal files named that are not in inbox/journal (confirmed ids and sizes)."""
    dl = []
    for n in names:
        lp = env.lay.inbox / 'journal' / n
        if not lp.is_file():
            did = env.file_id(n)
            if did is None:
                raise Halt('STOP', 'UNCLASSIFIED', 'a journal file without a known id')
            dl.append((env.series_folder, did, str(lp)))
    if dl:
        size = {cp['id']: cp['size'] for cf in (env.cache or {}).get('confirms') or [] for cp in cf['copies']}
        size.update({c[0]: c[2] for cs in ((env.state or {}).get('files') or {}).values() for c in cs})
        size[(env.cache.get('head') or {}).get('id')] = (env.cache.get('head') or {}).get('bytes')
        emit(env, code, PrintBlock(code, downloads=tuple(dl)), {'command': 'go', 'kind': 'local', 'dl': {
            p: [os.path.basename(p), size.get(did)] for _, did, p in dl}})


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
    if loop_block(env, w['setup_loop'], 'RESTORE', 'setup_loop'):   # the confirmed copies are this session's
        now, ver = env.now(), dict(w.get('verified') or {})          # observations of those parts
        for f in w['setup_loop']['parts']:
            w['lookups'].append({'name': f['name'], 'result': 'present', 'copies': [[c[0], c[2]] for c in f['copies']],
                                 'utc': now})
            for c in f['copies']:
                ver[c[0]] = [f['sha256'], f['bytes']]
        w['setup_loop'], w['reuploaded'], w['verified'] = None, True, ver
        save_work(env)


# ================================================================ asks and answers (§6.5)
def ask(env, st):
    ctx, a = dict(st.context), st.context['action']
    prefix = None
    if a in ('NOTIFY_OWNER', 'ASK_USER'):
        ensure_member(env, ctx['file'], ctx['for_seq'], 'attest/%s.txt' % ('notice' if a == 'NOTIFY_OWNER' else 'ask'))
        prefix = (a, {'file': ctx['file']})
    elif a == 'DELIVER_COPY':
        ensure_standard(env, ctx)
        prefix = ('DELIVER', {'file': ctx['file'], 'to': 'copy'})
    elif a == 'DELIVER_USER':
        f = str(env.p.deliver / N.run8(ctx['run']) / 'PERSONAL_COPY.xlsx')
        ensure_member(env, f, ctx['prepared_seq'], 'delivery/copy.xlsx')
        prefix = ('DELIVER', {'file': f, 'to': 'user'})
    if ctx.get('mark'):
        set_mark(env, ctx['mark'])
    emit(env, ctx.get('state_code', 'ATTEST'), PrintBlock(ctx.get('state_code', 'ATTEST'), do=(
        'ATTEST_ANSWER', {'keys': st.keys, 'prefix': prefix, 'after': ctx.get('after')})),
        {'command': 'answer', 'keys': st.keys, 'context': ctx})


def ensure_member(env, path, seq, member):
    """A notice, question or personal copy file the plan names, re-made from its entry's member after a reset."""
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


def apply_answer(env, ctx, got):
    """Apply validated answers. Returns None or a REFUSED code (nothing changed)."""
    a, w = ctx['action'], env.work
    if a == 'OPERATOR':
        w['operator'] = {'model': got['operator_model'], 'platform': got['platform']}
        save_work(env)
    elif a == 'APPROVAL':                         # D6: `pending` changes nothing; the owner resolves it, then `go`
        if got['approval'] == 'pending':
            emit(env, 'RESTORE', PrintBlock('STOP', do=('STOP', {'code': 'WAIT_APPROVAL', 'handback': 'A'})),
                 {'command': 'go', 'kind': 'session'})
        w['approval'] = 'none'
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


def tools_of(env, value):
    """D9: the tool list a conversation had, as (bytes, source, file to drop), or TOOLS_FILE_INVALID. `inventory` is
    the kit's TOOL_INVENTORY.txt (its sha256 checked again); `file:<abs>` a regular file the Dot saved under attest/."""
    if value == 'inventory':
        p = env.lay.runtime / 'TOOL_INVENTORY.txt'
        b = p.read_bytes() if p.is_file() else b''
        if sha_bytes(b) != env.cfg['tool_inventory_sha256'] or N.tool_list(b) is None:
            raise Halt('STOP', 'CONFIG_INVALID', 'TOOL_INVENTORY.txt')
        return b, 'inventory', None
    p = value[len('file:'):]
    if not p.startswith(str(env.p.attest) + '/') or os.path.islink(p) or not os.path.isfile(p) \
            or os.path.realpath(p) != p or os.lstat(p).st_size > 1 << 20 or N.tool_list(Path(p).read_bytes()) is None:
        return 'TOOLS_FILE_INVALID'
    return Path(p).read_bytes(), 'file', p


def ai_commit(env, ctx, got):
    """§7.5: walk the role's output folder strictly, take the final message as data (D3c) and, at revision 1, the tool
    list (D9), commit the AI entry."""
    R = env.state['runs'][ctx['run']]
    ro = R['roles'][ctx['role'] + str(ctx['attempt'])]
    lt = F.latest(ro)
    members, files, tree = place.ai_members(lt['output'], env.cfg['max_ai_output_bytes'])
    conv = got.get('conversation') or ro['archives'][0]['conversation']
    fmp = env.p.attest / 'final_message.txt'
    if os.path.islink(fmp) or not fmp.is_file():
        return 'FINAL_MESSAGE_INVALID missing'
    if os.lstat(fmp).st_size > env.cfg['max_ai_output_bytes']:
        raise Halt('STOP', 'AI_OUTPUT_TOO_LARGE', 'the final message is over max_ai_output_bytes')
    raw = fmp.read_bytes()
    try:
        raw.decode('utf-8')
    except UnicodeDecodeError:
        return 'FINAL_MESSAGE_INVALID utf8'
    members.append(('attest/final_message.txt', 'file', 0o644, raw))
    att, tr, drop = {}, None, [str(fmp)]
    if ctx['revision'] == 1:
        tl = tools_of(env, got['tools'])
        if isinstance(tl, str):
            return tl
        members.append(('attest/tools.txt', 'file', 0o644, tl[0]))
        att['tools_present'] = {'source': tl[1], 'sha256': sha_bytes(tl[0])}
        drop += [tl[2]] if tl[2] else []
    if ro['role'] == 'S':
        att['prompt_pasted'] = True
    if ro['role'] == 'G':
        tp, ext = ctx.get('transcript_path'), env.cfg['transcript_ext']
        if got['transcript'] == 'exported':
            code = transcript_problem(env, tp)
            if code:
                return code
            members.append(('transcript/G%d_%d.%s' % (ro['attempt'], lt['start_no'], ext), 'file', 0o644, tp))
            tr = {'status': 'exported', 'sha256': sha_file(tp), 'ext': ext}
        else:
            tr = {'status': 'not_available', 'sha256': None, 'ext': None}
        att.update({'platform': got['platform'], 'model': got['model'], 'effort': got['effort'],
                    'started_utc': got['started_utc'], 'ended_utc': got['ended_utc'],
                    'single_user_message': got['single_user_message'] == 'yes',
                    'features': {k: got[k] == 'yes' for k in N.FEATURES}, 'transcript_status': got['transcript']})
    body = {'run': ctx['run'], 'role': ro['role'], 'attempt': ro['attempt'], 'revision': ctx['revision'],
            'start_no': lt['start_no'], 'start_boot_id': lt['boot_id'], 'ended': True, 'conversation': conv,
            'attested': att, 'tree_sha256': tree, 'files': files, 'transcript': tr, 'final_message_sha256':
            sha_bytes(raw)}
    commit(env, draft(env, 'AI', body), roots_of(members) + members, post=[['DROP_ATTEST', drop]])
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
    """§11.3: the personal copy and its log checked, then DELIVERY with parts DELIV01, DLOG01 to the profile folder,
    which must print (S-06)."""
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
            not any(c in pf for c in '\'"\\') and drive.prints(pf.rstrip('/') + '/deliveries')
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
    if k == 'CLEAR':                    # SD-51: the RESTORE kept the halted kit; the CLEAR takes the new one
        hk, kit = env.work.get('head_kit'), env.cache.get('kit')
        if not hk or not kit:
            stop_block(env, 'HALTED_' + st.entry['body']['code'])
        code, kc = S.kit_change(env.state, kit, hk)
        if code or not kc['config_only']:
            stop_block(env, code or 'CONFIG_CHANGE_NOT_ALLOWED')
        d = draft(env, 'CLEAR', dict(st.entry['body'], kit_sha256=kit['sha256'], kit_change=kc))
        d['kit_sha256'] = kit['sha256']
        commit(env, d)
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
    """§7.1 RunChain: the local journal files the chain reads, the INPUTS re-check (a counted refusal, D3d), then the
    foreground stage."""
    ensure_local(env, needed_entries(env, 'chain', info), 'WORK')
    if info['first'] == 'prepare' and (info.get('info') or {}).get('inputs_seq'):
        R = env.state['runs'][info['run']]
        got = inputs_of(env, R['case'])
        if got is None or N.sha(N.cjson(got)) != R['inputs']['sha256']:
            render(env, 'WORK', PrintBlock('WORK', do=('RUN', {})), {'command': 'go', 'kind': 'plan'})
            refuse(env, 'INPUTS_CHANGED')
    if env.command != 'go':
        run_go(env)
    run_stage(env, 'chain', info)


def run_stage(env, kind, info):
    """§X.7.2 steps 2-3: the free space a chain needs (SD-69), FOREGROUND.json (durably), the RUNNING line (flushed at
    once), the body in this process under the helper lock, then FOREGROUND.json unlinked and outbox/v2 fsynced on
    return of any status (never in a `finally`: a stage that dies leaves it for step 4), then the result absorbed. The
    caller's loop prints the block."""
    from . import worker
    first = info.get('first') if kind == 'chain' else None
    mx = env.cfg['stage_max_seconds'][first or kind]
    if kind == 'chain':
        require_space(env.lay, N.STAGE_FREE_BYTES, 'stage')
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
