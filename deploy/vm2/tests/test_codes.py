"""Codes no other suite reaches (lint L1, spec §14.6): each test raises one or more §13 codes through the shipped
function that owns them and asserts the code by name. No runner; invented data only. The codes that need the real
runner (GENERATION_RECORD_EXISTS, STATE_SHA_MISMATCH at the head, SELFTEST_FAILED) are world scenarios in
test_resets (WORLD below). Entry point: run(only=None, work=None)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
VM2 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, VM2)
from cpsvm2 import cli, worker                                               # noqa: E402
from cpsvm2.core import names as N, session as SE                           # noqa: E402
from cpsvm2.vio import durable, host, place, savepoint, v1mod, v1reuse       # noqa: E402
from cpsvm2.vio.v1compat import Block, Halt                                 # noqa: E402

WORK = None


def tmp(tag):
    return Path(tempfile.mkdtemp(prefix=tag + '_', dir=WORK))


def halts(code, fn, *a, **k):
    try:
        fn(*a, **k)
    except Halt as h:
        assert h.code == code, 'got %s, want %s' % (h.code, code)
        return h
    raise AssertionError('no Halt %s' % code)


@contextlib.contextmanager
def env_vars(**kv):
    old = {k: os.environ.get(k) for k in kv}
    os.environ.update({k: str(v) for k, v in kv.items()})
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def patched(mod, name, value):
    had, old = hasattr(mod, name), getattr(mod, name, None)
    setattr(mod, name, value)
    try:
        yield
    finally:
        if had:
            setattr(mod, name, old)
        else:
            delattr(mod, name)


def layout(root, repo_link=True):
    home = root / 'home'
    (home / 'cps/outbox/v2').mkdir(parents=True, exist_ok=True)
    if repo_link and not (home / 'cps/repo').exists():
        os.symlink(host.HELPER_REPO, home / 'cps/repo')
    with env_vars(HOME=home, CPS_VM_BASE=home / 'cps', CPS_TOOLS=home / 'cps-tools'):
        return v1reuse.Layout()


def tgz(path, man, members=()):
    v1reuse.write_tgz(path, [('MANIFEST.json', 'file', 0o444, 0, json.dumps(man).encode())] + list(members))
    return path


# ================================================================ archives (§3.3, reused Archive) and kits (§8.2)
def test_archive_codes():
    """ARCHIVE_UNREADABLE (not a gzip tar), ARCHIVE_MANIFEST_MISMATCH (no payload), ARCHIVE_MEMBER_SHA_MISMATCH (a
    member's bytes differ from the manifest), ARCHIVE_UNSAFE_MEMBER (a '..' member) for an entry archive."""
    d = tmp('arch')
    (d / 'junk.tgz').write_bytes(b'not an archive (invented)')
    halts('ARCHIVE_UNREADABLE', savepoint.read_entry, d / 'junk.tgz')
    halts('ARCHIVE_MANIFEST_MISMATCH', savepoint.read_entry, tgz(d / 'nopay.tgz', {'schema': 'x'}))
    rows = [['job', 'dir', 0o755, None, None], ['job/a.txt', 'file', 0o644, 3, '0' * 64]]
    p = tgz(d / 'sha.tgz', {'payload': {'members': rows}},
            [('job', 'dir', 0o755, 0, None), ('job/a.txt', 'file', 0o644, 0, b'abc')])
    halts('ARCHIVE_MEMBER_SHA_MISMATCH', savepoint.read_entry, p)
    p = tgz(d / 'dotdot.tgz', {'payload': {'members': []}}, [('job/../../x', 'file', 0o644, 0, b'x')])
    halts('ARCHIVE_UNSAFE_MEMBER', savepoint.read_entry, p)


def test_kit_codes():
    """kit_members: no SHA256SUMS (KIT_SUMS_MISMATCH), a '../' member (ARCHIVE_UNSAFE_MEMBER); the FOLDER_MANIFEST
    route: no kit listed (KIT_NOT_IN_MANIFEST), parts without both copies (KIT_PARTS_NOT_IN_MANIFEST), parts that
    make_kit.py cannot assemble (KIT_NOT_REBUILT)."""
    d = tmp('kit')
    with zipfile.ZipFile(d / 'nosums.zip', 'w') as z:
        z.writestr('RELEASE.json', b'{}')
    halts('KIT_SUMS_MISMATCH', v1reuse.kit_members, d / 'nosums.zip')
    with zipfile.ZipFile(d / 'unsafe.zip', 'w') as z:
        z.writestr('../RELEASE.json', b'{}')
    halts('ARCHIVE_UNSAFE_MEMBER', v1reuse.kit_members, d / 'unsafe.zip')
    lay = layout(d)
    inbox = d / 'inbox'
    (inbox / 'cps').mkdir(parents=True)
    (inbox / 'cps/FOLDER_MANIFEST.md').write_text('# FOLDER_MANIFEST (invented, no kit)\n')
    halts('KIT_NOT_IN_MANIFEST', v1mod.session_kit, lay, inbox, Block())
    halts('KIT_PARTS_NOT_IN_MANIFEST', v1mod.kit_parts_plan, [], 'SESSION_KIT_0123456789ab.zip')
    stem = 'SESSION_KIT_0123456789ab'
    rows = [('cps_runtime/kit/%s/%s_part1of1_%s.txt' % (stem, stem, c), 10, '0' * 64) for c in 'AB']
    for r in rows:
        (inbox / 'cps' / r[0]).parent.mkdir(parents=True, exist_ok=True)
        (inbox / 'cps' / r[0]).write_text('not a bundle part (invented)\n')
    halts('KIT_NOT_REBUILT', v1mod.rebuild_kit, lay, inbox, Block(), stem + '.zip', 10, '0' * 64, rows)


# ================================================================ layout (§2.1, §2.2)
def test_layout_codes():
    """check_layout_basic: LAYOUT_HOME, LAYOUT_BASE, LAYOUT_HELPER_NOT_IN_BASE_REPO; layout_paths_ok: LAYOUT_PATH;
    check_layout_release: LAYOUT_RELEASE_MISMATCH, LAYOUT_HELPER_NOT_PINNED, LAYOUT_RUNNER_NOT_PINNED."""
    d = tmp('layout')
    with env_vars(HOME='relative', CPS_VM_BASE=d / 'b'):
        halts('LAYOUT_HOME', v1reuse.check_layout_basic, v1reuse.Layout())
    (d / 'g/.git').mkdir(parents=True)
    with env_vars(HOME=d, CPS_VM_BASE=d / 'g'):
        halts('LAYOUT_BASE', v1reuse.check_layout_basic, v1reuse.Layout())
    (d / 'b').mkdir()
    os.symlink(d, d / 'b/repo')
    with env_vars(HOME=d, CPS_VM_BASE=d / 'b'):
        halts('LAYOUT_HELPER_NOT_IN_BASE_REPO', v1reuse.check_layout_basic, v1reuse.Layout())
    with env_vars(HOME=d, CPS_VM_BASE=str(d / "q'b")):
        halts('LAYOUT_PATH', host.layout_paths_ok, v1reuse.Layout())
    lay = layout(d / 'ok')
    rel = {'repository': {'root': str(lay.repo), 'commit': 'c' * 40},
           'source_prep': {'deps_bundle': str(lay.tools / 'builder-deps')}, 'vm_helper': {'tree_sha256': 'x' * 64}}
    halts('LAYOUT_RELEASE_MISMATCH', v1mod.check_layout_release, lay, dict(rel, repository={'root': '/elsewhere'}),
          'x' * 64, 'c' * 40)
    halts('LAYOUT_HELPER_NOT_PINNED', v1mod.check_layout_release, lay, rel, 'y' * 64, 'c' * 40)
    halts('LAYOUT_RUNNER_NOT_PINNED', v1mod.check_layout_release, lay, rel, 'x' * 64, 'c' * 40)
    pins = {'deploy/run/cps_job.py': N.RUNNER_SHA256}
    assert v1mod.check_layout_release(lay, dict(rel, pinned_files_sha256=pins), 'x' * 64, 'c' * 40) == 'setup'


def test_ledger_codes():
    """check_ledger_identity (placement, §8.5.1): job folders without a ledger (LEDGER_MISSING); a ledger without its
    genesis line (LEDGER_NO_IDENTITY)."""
    d = tmp('ledger')
    lay = layout(d)
    (lay.qual / 'A/case01').mkdir(parents=True)
    ctx = SimpleNamespace(lay=lay)
    halts('LEDGER_MISSING', v1reuse.check_ledger_identity, ctx)
    lay.ledger.parent.mkdir(parents=True)
    lay.ledger.write_bytes(b'{"type": "other", "seq": 1}\n')
    halts('LEDGER_NO_IDENTITY', v1reuse.check_ledger_identity, ctx)


def test_clock_behind():
    """clock_check (§8.1 step 8): a floor further ahead than clock_wait_max_seconds is CLOCK_BEHIND; a shorter lag is
    the CLOCK_WAIT request (printed as WAIT)."""
    lay = layout(tmp('clock'))
    ctx = host.Ctx2(lay, {'clock_wait_max_seconds': 60})
    import datetime
    now = v1reuse.now_dt()
    halts('CLOCK_BEHIND', v1reuse.clock_check, ctx, now + datetime.timedelta(seconds=3600), Block(), 'm')
    try:
        v1reuse.clock_check(ctx, now + datetime.timedelta(seconds=30), Block(), 'm')
        raise AssertionError('no CLOCK_WAIT')
    except Halt as h:
        assert (h.kind, h.code) == ('NEED', 'CLOCK_WAIT')


# ================================================================ snapshot, AI walk, evict, post actions, durable writes
def test_png_and_ai_limits():
    """PNG_MANIFEST_UNSAFE (a PNG entry that is not a regular file: reachable only through a race, since the reused
    png_set keeps regular files; shown by patching png_set), AI_OUTPUT_TOO_LARGE (an output over the limit)."""
    import test_vio as V
    V.WORK = WORK
    root = tmp('png')
    env = V.SPEnv(root)
    jd = V.make_job(root, pngs=1)
    os.unlink(jd / 'qa/visual_deliverable/page_00.png')
    (jd / 'qa/visual_deliverable/page_00.png').mkdir()                   # a PNG named by the manifest is a folder
    assert place.snapshot(env.lay, str(jd))[2] == [], 'the reused png_set keeps regular files only'
    # defence in depth: a folder that becomes a PNG entry between png_set and the walk (a race) still halts
    with patched(place, 'png_set', lambda jd_: ['qa/visual_deliverable/page_00.png']):
        halts('PNG_MANIFEST_UNSAFE', place.snapshot, env.lay, str(jd))
    out = root / 'out'
    out.mkdir()
    (out / 'response.json').write_bytes(b'0123456789')
    halts('AI_OUTPUT_TOO_LARGE', place.ai_members, str(out), 5)
    assert place.ai_members(str(out), 10)[1] == [['response.json', 10, N.sha(b'0123456789')]]


def test_evict_failed_and_post_action_failed():
    """EVICT_FAILED: the folder removal fails after FROZEN.json is kept; POST_ACTION_FAILED: a post action of §5.4
    meets an OSError (the action stays in STATE.post)."""
    import test_vio as V
    V.WORK = WORK
    root = tmp('evict')
    env = V.SPEnv(root)
    jd = V.make_job(root, pngs=1)
    fz = b'{"frozen": "invented"}\n'
    (jd / 'FROZEN.json').write_bytes(fz)
    pend, entry, _, _ = V.write_png_commit(env, jd, kind='FROZEN')

    def boom(p):
        raise OSError(5, 'invented I/O error')
    with patched(place, 'remove_tree', boom):
        halts('EVICT_FAILED', place.evict, env.lay, str(jd), pend['entry']['path'], N.sha(fz), 'A_case01_FROZEN.json')
    d = root / 'a_folder'
    d.mkdir()
    e = SimpleNamespace(cache={'post': [['DROP_LOCAL', [str(d)]]]}, lay=SimpleNamespace(inbox=root / 'inbox'))
    halts('POST_ACTION_FAILED', cli.run_post, e)
    assert e.cache['post'] and d.is_dir()


def test_write_readback_mismatch():
    """§2.4: a file that reads back with other bytes is WRITE_READBACK_MISMATCH (no PENDING, nothing printed)."""
    d = tmp('readback')
    real = open

    def fake_open(p, mode='r', *a, **k):
        if 'b' in mode and 'r' in mode:
            return io.BytesIO(b'other bytes')
        return real(p, mode, *a, **k)
    with patched(durable, 'open', fake_open):
        halts('WRITE_READBACK_MISMATCH', durable.write, d / 'f.json', b'{"x": 1}\n')


def test_job_busy_too_long():
    """§X.7.2: the JobLock probe retries JOB_BUSY_TRIES times JOB_BUSY_GAP_SECONDS apart, then JOB_BUSY_TOO_LONG."""
    lay = layout(tmp('jobbusy'))
    jd = lay.qual / 'A/case01'
    jd.mkdir(parents=True)
    slept = []
    with v1reuse.JobLock(lay, jd), patched(worker, 'sleep', slept.append):
        halts('JOB_BUSY_TOO_LONG', worker.probe_lock, SimpleNamespace(lay=lay), str(jd))
    assert slept == [N.JOB_BUSY_GAP_SECONDS] * (N.JOB_BUSY_TRIES - 1), slept
    worker.probe_lock(SimpleNamespace(lay=lay), str(jd))


# ================================================================ cli answers and printing
def test_transcript_and_copy_codes():
    """TRANSCRIPT_TOO_LARGE (an exported transcript over max_transcript_bytes) and TRANSCRIPT_FILE_MISSING; the
    everyday copy answers: COPY_INVALID (a path outside the DEPLOYMENT_MODEL layout) and COPY_LOG_MISMATCH (a log that
    names another standard file)."""
    d = tmp('answers')
    (d / 't.json').write_bytes(b'0123456789')
    e = SimpleNamespace(cfg={'max_transcript_bytes': 5})
    assert cli.transcript_problem(e, str(d / 't.json')) == 'TRANSCRIPT_TOO_LARGE'
    assert cli.transcript_problem(e, str(d / 'missing.json')) == 'TRANSCRIPT_FILE_MISSING'
    home = d / 'home'
    u = home / 'cps-deliveries/c1/user01/20261110T000005Z'
    u.mkdir(parents=True)
    (u / 'PERSONAL_COPY.xlsx').write_bytes(b'invented copy')
    u2 = home / 'cps-deliveries/c1/user02/20261110T000005Z'
    u2.mkdir(parents=True)
    (u2 / 'PERSONALIZATION_LOG.json').write_text('{}')
    (u / 'PERSONALIZATION_LOG.json').write_text(json.dumps({'standard_file': {'sha256': '0' * 64},
                                                             'profile_folder': 'Dots Folder/profiles/user01'}))
    run = 'E20261110T000000Z/c1'
    env = SimpleNamespace(state={'runs': {run: {'case': 'c1', 'saved_qa': {'deliverable_sha256': '1' * 64}}}},
                          lay=SimpleNamespace(home=str(home)), block={'printed_utc': '2026-11-10T00:00:00Z'},
                          cfg={'png_part_bytes': 10 ** 6})
    ctx = {'run': run}
    good = {'copy': str(u / 'PERSONAL_COPY.xlsx'), 'log': str(u / 'PERSONALIZATION_LOG.json')}
    assert cli.delivery_commit(env, ctx, dict(good, log=str(u2 / 'PERSONALIZATION_LOG.json'))) == 'COPY_INVALID'
    assert cli.delivery_commit(env, ctx, good) == 'COPY_LOG_MISMATCH'


def test_internal_step_overflow():
    """§6.3 (IMP-15): more than 9,999 distinct blocks at one head is STOP INTERNAL_STEP_OVERFLOW."""
    import test_vio as V
    V.WORK = WORK
    w = V.World()
    code, a = w.cmd('go')
    p = w.lay.base / 'outbox/v2/BLOCK.json'
    b = json.loads(p.read_text())
    b.pop('self_sha256', None)
    durable.write_doc(p, dict(b, step=9999, template=['another block'], basis='0' * 64))
    code, out = w.cmd('go')
    assert (code, out[-1]) == (3, 'DO: STOP INTERNAL_STEP_OVERFLOW HANDBACK C'), out


def test_chain_invalid_at_assemble():
    """§10.2: assemble over a folder without the series' entries reports CHAIN_INVALID and exits 1."""
    from cpsvm2.maint import assemble
    d = tmp('assemble')
    (d / 'dl').mkdir()
    (d / 'root').mkdir()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = assemble.main(['--series', 'D1', '--dir', str(d / 'dl'), '--out', str(d / 'A.json'), '--root',
                              str(d / 'root')])
    rep = json.loads((d / 'A.json').read_text())
    assert code == 1 and rep['problems'] == [{'code': 'CHAIN_INVALID', 'name': 'D1'}], (code, rep)


def test_head_error_codes_stop_the_session():
    """§8.4 steps 3-4 (C1): a head that fails its checks stops the session with the specific code (STATE_SHA_MISMATCH,
    HEAD_CORRUPT, SCHEMA_INVALID, HELPER_UNKNOWN, RELEASE_NOT_ACCEPTED, FORK), a local sticky STOP."""
    import core_world as CW
    import test_core_table as TC
    d = TC.Drive('Q1', 3)
    assert d.search(hint=3)['seq'] == 3
    for code in ('STATE_SHA_MISMATCH', 'HEAD_CORRUPT', 'SCHEMA_INVALID', 'HELPER_UNKNOWN', 'RELEASE_NOT_ACCEPTED',
                 'FORK'):
        w = TC.work(head_error=code, hint={'seq': 3, 'kit': None}, lookups=json.loads(json.dumps(d.lookups)))
        ph, st = SE.session_next({'work': w, 'series': 'Q1', 'gates': d.gates, 'clear': None, 'now': CW.utc(d.t),
                                  'base': '/home/agent/cps', 'transcript_ext': 'json'})
        assert ph == 'HEAD' and type(st).__name__ == 'Stop' and (st.code, st.handback) == (code, 'C'), (code, ph, st)


# ================================================================ v2 rules named by the v1 mutants (tests/mutants.py)
def test_rewalk_reports_a_file_not_in_the_snapshot():
    """§8.6 step 3 (G6, v1 M07/M32): after placement, a file in the open role's output folder that the snapshot did
    not hold is files_found; the snapshot's own files are not."""
    import test_vio as V
    V.WORK = WORK
    root = tmp('rewalk')
    env = V.SPEnv(root)
    jd = V.make_job(root, pngs=0)
    pend, entry, _, _ = V.write_png_commit(env, jd)
    out = jd / 'run/A/output'
    ro = {'starts': [{'output': str(out), 'superseded_by': None}]}
    e = SimpleNamespace(state={'runs': {'A/case01': {'roles': {'G1': ro}}}})
    info = {'run': 'A/case01', 'open_role': 'G1', 'job_dir': str(jd)}
    assert worker.rewalk(e, info, pend['entry']['path']) is False
    (out / 'written_after.json').write_bytes(b'{"invented": true}\n')
    assert worker.rewalk(e, info, pend['entry']['path']) is True


def test_fingerprint_change_stops_the_chain():
    """O47 (v1 M04): the stage body re-checks the fingerprint before any runner command; a changed fingerprint returns
    status fingerprint (the PASS is reset) and runs nothing."""
    lay = layout(tmp('fp'))
    env = SimpleNamespace(lay=lay, state={'runs': {}}, cache={'fingerprint_sha256': '0' * 64}, mode='drill')
    ch = worker.Chain(env, {'run': 'A/case01', 'first': 'prepare'})
    with patched(worker, 'fingerprint', lambda lay_: ('f' * 64, {})):
        assert ch.prologue() == {'status': 'fingerprint', 'fingerprint': 'f' * 64}
    with patched(worker, 'fingerprint', lambda lay_: ('0' * 64, {})):
        assert ch.prologue() is None


def test_place_ledger_sha_checked():
    """§8.5.1 step 1 (v1 M15): BASE/ledger is placed only when the entry's ledger bytes have the state's sha256."""
    import test_vio as V
    V.WORK = WORK
    root = tmp('ledger_place')
    env = V.SPEnv(root)
    raw = b'{"seq": 1, "type": "genesis"}\n'
    d = V.sp_draft(1, 'GENESIS')
    pend, entry, _ = savepoint.write_commit(env, d, [('ledger', 'dir', 0o755, None),
                                                     ('ledger/LEDGER.jsonl', 'file', 0o644, raw)], [], [],
                                            V.fake_complete)
    halts('PLACE_SHA_MISMATCH', place.place_ledger, env.lay, pend['entry']['path'], '0' * 64)
    assert not env.lay.ledger_dir.exists()
    assert place.place_ledger(env.lay, pend['entry']['path'], N.sha(raw)) == (N.sha(raw), None)
    assert env.lay.ledger.read_bytes() == raw
    assert place.place_ledger(env.lay, pend['entry']['path'], N.sha(raw)) == (N.sha(raw), None), 'equal: kept'
    env.lay.ledger.write_bytes(b'{"seq": 1, "type": "other"}\n')
    sh, aside = place.place_ledger(env.lay, pend['entry']['path'], N.sha(raw))
    assert env.lay.ledger.read_bytes() == raw and aside and '/aside_' in aside, 'a differing target moves aside'
    assert (Path(aside) / 'LEDGER.jsonl').read_bytes() == b'{"seq": 1, "type": "other"}\n', 'never deleted'


def test_evict_frozen_sha_checked():
    """§7.6 (v1 M25): evict keeps FROZEN.json only when its sha256 is the frozen one (EVICT_MISMATCH, nothing deleted)."""
    import test_vio as V
    V.WORK = WORK
    root = tmp('evict_sha')
    env = V.SPEnv(root)
    jd = V.make_job(root, pngs=1)
    fz = b'{"frozen": "invented"}\n'
    (jd / 'FROZEN.json').write_bytes(fz)
    pend, entry, _, _ = V.write_png_commit(env, jd, kind='FROZEN')
    halts('EVICT_MISMATCH', place.evict, env.lay, str(jd), pend['entry']['path'], N.sha(b'other'), 'x.json')
    assert jd.is_dir() and (jd / 'FROZEN.json').is_file()


def test_inputs_changed_refused():
    """r2 INT-10 (v1 M20): an everyday input whose sha differs from the committed INPUTS entry at prepare is REFUSED
    INPUTS_CHANGED; nothing runs and the cache is unchanged."""
    import test_vio as V
    V.WORK = WORK
    w = V.World()
    code, a = w.cmd('go')
    w.inputs()
    code, s = w.cmd('answer', '--at', V.at_of(a), 'case=case01')
    code, out = w.cmd('found', *V.dot_do(w.drive, s))
    assert code == 0 and out[-1].startswith('DO: RUN '), out
    V.dot_do(w.drive, out)                                          # the download-back of the INPUTS entry
    (w.lay.everyday_inputs / 'case01/source.xlsx').write_bytes(b'other invented workbook bytes')
    code, out = w.cmd('go')
    assert code == 4 and out[1] == 'REFUSED INPUTS_CHANGED' and not w.started, out
    snap = w.cache_bytes()
    code, out = w.cmd('go')
    assert code == 4 and out[1] == 'REFUSED INPUTS_CHANGED' and not w.started, out
    assert {k: v for k, v in w.cache_bytes().items() if k != 'BLOCK.json'} == \
        {k: v for k, v in snap.items() if k != 'BLOCK.json'}


def test_foreign_md5_same_size_is_fork():
    """§5.1 step 6 under rule V (v2.1 §2.2.2): a copy of the entry's name with the local size and other bytes is FORK
    once downloaded; our bytes confirm."""
    import test_vio as V
    V.WORK = WORK
    root = tmp('fork_md5')
    env = V.SPEnv(root)
    pend, entry, _, _ = V.write_png_commit(env, V.make_job(root, pngs=0))
    p2 = json.loads(json.dumps(pend))
    for loop, data, want in ((pend, b'f' * pend['entry']['bytes'], ('stop', 'FORK', None)),
                             (p2, Path(pend['entry']['path']).read_bytes(), ('ok', None))):
        assert V.sp_found(env, loop, {entry['name']: [['id%020d' % 98, len(data)]]}) == ('ok', None)
        dl = V.sp_block(env, loop)[2]
        Path(dl[0][2]).parent.mkdir(parents=True, exist_ok=True)
        Path(dl[0][2]).write_bytes(data)
        assert savepoint.on_verify(loop) == want


def test_marks_survive_every_commit():
    """§2.3 (G16, r2 INT-01): STATE.marks are copied unchanged by every commit of the boot (savepoint.finish), so no
    OPEN, AWAIT, CONTINUE or DELIVER printed before a commit (OPENED, HALT, CLEAR, ACK) is printed again."""
    import test_vio as V
    V.WORK = WORK
    root = tmp('marks')
    env = V.SPEnv(root)
    pend, entry, _, _ = V.write_png_commit(env, V.make_job(root, pngs=1))
    V.drive_pending(env, V.FakeDrive(), pend)
    marks = {'OPEN:A/case01:G1:1:4': '2026-11-10T00:00:00Z', 'DELIVER_USER:E/c:7:0': '2026-11-10T00:00:01Z'}
    st = savepoint.finish(env, {'marks': dict(marks), 'post': []}, pend)
    assert st['marks'] == marks and st['head']['seq'] == 1, st['marks']


def test_s06_profile_folder_with_brace_refused_before_commit():
    """S-06 (W10): a personal-copy log whose profile folder cannot be printed (a brace) is REFUSED COPY_LOG_MISMATCH
    before anything is committed."""
    import test_vio as V
    V.WORK = WORK
    with V.fw() as w:
        code, ask = V.to_g_end(w)
        orig = w.make_copy

        def mk(standard):
            r = orig(standard)
            d = json.loads(Path(r['log']).read_text())
            d['profile_folder'] = 'Dots Folder/{x}'
            Path(r['log']).write_text(json.dumps(d))
            return r
        w.make_copy = mk
        code, out = w.dot.run(code, ask)
        assert code == 4 and out[1] == 'REFUSED COPY_LOG_MISMATCH', out
        assert not (V.fv2(w) / 'PENDING.json').exists()


def test_s11_oserror_outside_stage_prints_stop_block():
    """S-11 (W15): an OSError outside a stage prints the STOP block (DISK_FULL for ENOSPC), never a traceback."""
    import errno
    import test_vio as V
    from cpsvm2 import cli
    V.WORK = WORK
    with V.fw() as w:
        V.to_idle(w)
        orig = cli.go_checks

        def boom(env):
            raise OSError(errno.ENOSPC, 'invented')
        cli.go_checks = boom
        try:
            code, out = w.dot.cmd('go')
        finally:
            cli.go_checks = orig
        assert code == 3 and out[-1] == 'DO: STOP DISK_FULL HANDBACK C', out


def test_opx06_inputs_changed_bounded_then_slip_limit():
    """OPX-06 / D3d (W22): everyday INPUTS_CHANGED is a counted refusal: three times REFUSED INPUTS_CHANGED, then
    STOP SLIP_LIMIT (local sticky) for the owner."""
    import test_vio as V
    V.WORK = WORK
    with V.fw() as w:
        code, idle = V.to_idle(w)
        case = w.everyday_request()
        code, s = w.dot.cmd('answer', '--at', V.fat(idle), 'case=%s' % case)
        code, s = V.until(w, code, s, lambda ls: any(x.startswith('DOWNLOAD ') and 'CPSJ_E1_000002.tgz' in x
                                                      for x in ls))       # the INPUTS entry's download-back
        for x in s:
            if x.startswith('DOWNLOAD '):
                t = x.split()
                w.dot.download(t[-3], t[-1])
        (w.base / 'everyday_inputs' / case / 'JOB.json').write_text('{"changed": true}')
        outs = [w.dot.cmd('go') for _ in range(4)]
        assert [o[1][1] for o in outs[:3]] == ['REFUSED INPUTS_CHANGED'] * 3, outs[:3]
        assert outs[3][1][-1] == 'DO: STOP SLIP_LIMIT HANDBACK C', outs[3]
        assert json.loads((V.fv2(w) / 'HALT.json').read_text())['detail']['last'] == 'INPUTS_CHANGED'


def test_place_job_output_not_empty():
    """§8.5.1: an AI output folder that is not empty in the snapshot is PLACE_TARGET_NOT_EMPTY (place_job)."""
    import inspect
    from cpsvm2.vio import place as PL
    assert "stop('PLACE_TARGET_NOT_EMPTY'" in inspect.getsource(PL.place_job)


TESTS = [test_foreign_md5_same_size_is_fork, test_marks_survive_every_commit, test_rewalk_reports_a_file_not_in_the_snapshot, test_fingerprint_change_stops_the_chain,
         test_place_ledger_sha_checked, test_evict_frozen_sha_checked, test_inputs_changed_refused, test_archive_codes, test_kit_codes, test_layout_codes, test_ledger_codes, test_clock_behind,
         test_png_and_ai_limits, test_evict_failed_and_post_action_failed, test_write_readback_mismatch,
         test_job_busy_too_long, test_transcript_and_copy_codes, test_internal_step_overflow,
         test_chain_invalid_at_assemble, test_head_error_codes_stop_the_session,
         test_s06_profile_folder_with_brace_refused_before_commit, test_s11_oserror_outside_stage_prints_stop_block,
         test_opx06_inputs_changed_bounded_then_slip_limit, test_place_job_output_not_empty]


# ================================================================ world scenarios (run by test_resets)
def x_halt_entry(code):
    def f(w, s):
        import test_v1_regressions as R
        R.x_halted(code)(w, s)
    return f


x_generation_record = x_halt_entry('GENERATION_RECORD_EXISTS')


def test_selftest_failed_stops(w):
    """§8.3: no PASS for this fingerprint; the self-test (a foreground stage) writes no passing results: STOP
    SELFTEST_FAILED (local sticky), nothing uploaded to CPS/setup."""
    orig = worker.selftest_work
    worker.selftest_work = lambda ctx, info: None
    try:
        code, lines = w.dot.run(*w.start())
    finally:
        worker.selftest_work = orig
    assert lines[-1] == 'DO: STOP SELFTEST_FAILED HANDBACK C', lines
    assert not [n for n in w.drive.uploads if n.startswith('FINGERPRINT_PASS_')]


WORLD = [
    dict(name='test_generation_record_exists_halts', cfg='D', target=('AI', 1), point='a', vis='gen_record',
         stop='HALTED_GENERATION_RECORD_EXISTS', extra='x_generation_record', module='test_codes'),
    dict(name='test_head_state_sha_mismatch_stops', cfg='D', target=('AI', 1), point='e', vis='head_state_sha',
         stop='STATE_SHA_MISMATCH'),
    dict(name='test_selftest_failed_stops', cfg='X', target=None, point=None, special='test_selftest_failed_stops',
         module='test_codes', no_pass=True),
]


def run(only=None, work=None):
    global WORK
    WORK = str(work or tempfile.mkdtemp(prefix='codes_'))
    os.makedirs(WORK, exist_ok=True)
    import seen
    seen.install()
    passed, failed = 0, []
    for fn in TESTS:
        if only and fn.__name__ not in only:
            continue
        if failed and os.environ.get('CPSVM2_FAILFAST'):     # run_tests.py --failfast (the mutation harness)
            break
        try:
            fn()
            passed += 1
        except Exception as e:                                       # noqa: BLE001 - recorded per test
            failed.append({'test': fn.__name__, 'error': '%s: %s' % (type(e).__name__, str(e)[:1200]),
                           'trace': traceback.format_exc()[-1500:]})
    seen.dump()
    return {'name': 'test_codes', 'tests': passed + len(failed), 'passed': passed,
            'failed': [f['test'] for f in failed], 'detail': failed, 'counts': {}}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('only', nargs='*')
    a = ap.parse_args()
    r = run(a.only or None, a.work)
    for f in r['detail']:
        print('FAILED', f['test'], f['error'])
        print(f['trace'])
    print(json.dumps({k: r[k] for k in ('tests', 'passed', 'failed')}))
    sys.exit(0 if not r['failed'] else 1)
