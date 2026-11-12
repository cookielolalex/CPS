"""The reset scenarios of delta v2.1 (§2.15.5 rs) that run on a world of their own (test_resets specials): D6 approval
across a reset, D5 same-boot clears, D3 slip sequences, D4 raw files, OPX-06, and the real-subprocess SIGKILL (S-12).
First written by track C as scratch (builder_c/keep/tests_c/scen_c.py), lifted here by track T. Invented data only.
Each function takes a fakes.World (series and cases from SPEC) and raises AssertionError on a failure."""
import json
import os
import signal
import subprocess
import sys
import time

import fakes
from cpsvm2.core import names as N

VM2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def hdr(lines):
    h = lines[0] if lines and lines[0].startswith('CPSV ') else ''
    return dict(x.split('=', 1) for x in h.split()[1:]) if h else {}


def finish(w, code, lines, want='FINAL'):
    assert lines and want in lines[-1], (code, lines)
    if want == 'FINAL':
        c, rep, out = w.audit(str(w.root) + '_aud')
        assert c == 0 and rep['clean'], out[-800:]
    return lines[-1]


def entry(w, seq):
    from cpsvm2.vio import savepoint
    n = N.entry_name(w.series, seq)
    p = w.fixed / ('.e_' + n)
    p.write_bytes(w.drive.bytes_of(N.series_folder(w.series), n))
    try:
        return savepoint.read_entry(p)
    finally:
        os.unlink(p)


def go(w):
    code, lines = w.start()
    assert code == 0, lines
    return w.dot.cmd('go')


def reset_at(seq, state=None):
    """A hook: reset once when a block of head `seq` (and state) is about to be done."""
    done = []

    def h(dot, lines):
        d = hdr(lines)
        if not done and d.get('head') == '%06d' % seq and (state is None or d.get('state') == state):
            done.append(1)
            return 'reset'
    return h


def clear(w, lines, **over):
    """The maintainer's clear: a config-only kit naming the STOP of the Dot's last CPSV line, then its bootstrap."""
    d = hdr(lines)
    code = lines[-1].split()[2]
    k = w.clear_kit(code[7:] if code.startswith('HALTED_') else code, int(d['head']), **over)
    code, ls = w.dot.bootstrap(w.dot.notes['repo'], (d['head'], k))
    assert code == 0, ls
    return k


def D_reset_commit_boundary(w):
    code, lines = go(w)
    w.dot.hook = reset_at(5)
    code, lines = w.dot.run(code, lines)
    assert any(b.get('reset') is None and 'approval=APPROVAL' in (b['lines'] or [''])[-1] for b in w.dot.blocks)
    return finish(w, code, lines)


def D_refuse_reset_approval_pending(w):
    w.drive.refuse = {N.entry_name('D1', 4): (1,)}
    code, lines = go(w)
    seen = []

    def h(dot, ls):
        if ls and 'UPLOAD_REFUSED' in ls[-1] and not seen:
            seen.append(ls[-1])
            assert ls[-1].endswith('name=' + N.entry_name('D1', 4)), ls
            return 'reset'
    w.dot.hook = h
    code, lines = w.dot.run(code, lines)
    assert seen and any('STOP WAIT_APPROVAL HANDBACK A' in x for x in w.dot.stops_a), w.dot.stops_a
    i = [k for k, b in enumerate(w.dot.blocks) if b['lines'] and 'WAIT_APPROVAL' in b['lines'][-1]][0]
    before = [ln for b in w.dot.blocks[:i] if b['boot'] == w.dot.blocks[i]['boot'] for ln in b['lines']
              if ln.startswith('FIND ') and ' NAME CPSJ_' in ln]
    assert not before, 'approval= is asked before any FIND of the journal: %s' % before
    return finish(w, code, lines)


def D_refuse_reset_approval_wrong_none(w):
    w.dot.policy['approval'] = 'none'
    w.drive.refuse = {N.entry_name('D1', 4): (1,)}
    code, lines = go(w)
    state = {'n': 0}

    def h(dot, ls):
        if ls and 'UPLOAD_REFUSED' in ls[-1] and not state['n']:
            state['n'] = 1
            return 'reset'
        d = hdr(ls)
        if state['n'] == 1 and d.get('head', '0') >= '000006':
            state['n'] = 2
            w.drive.approve()                          # the approval lands after the RESTORE took that seq
    w.dot.hook = h
    code, lines = w.dot.run(code, lines)
    c, rep, out = w.audit(str(w.root) + '_aud')
    assert not rep['clean'] and 'AUD_DUPLICATE_SEQ' in json.dumps(rep), out[-600:]
    return 'audit unclean (AUD_DUPLICATE_SEQ)'


def D_clear_same_boot_fork(w):
    name = N.entry_name('D1', 4)
    code, lines = go(w)
    planted = []

    def h(dot, ls):
        if not planted and any(x.startswith('UPLOAD ') and x.endswith(' AS ' + name) for x in ls):
            planted.append(w.drive.plant(N.series_folder('D1'), name, b'foreign invented entry bytes'))
    w.dot.hook = h
    code, lines = w.dot.run(code, lines)
    assert lines[-1] == 'DO: STOP FORK HANDBACK C' and hdr(lines)['head'] == '000003', lines
    assert list((w.base / 'outbox/v2').glob('fork_*/verify/*')), 'S-03: the downloaded copies are kept'
    w.dot.hook = None
    code, lines = w.dot.cmd('go')
    assert lines[-1] == 'DO: STOP FORK HANDBACK C', 'local sticky'
    cs = w.drive.folders[N.series_folder('D1')][name]
    cs.remove([c for c in cs if c['id'] == planted[0]['id']][0])          # the owner deletes the foreign copy
    k = clear(w, lines)
    code, lines = w.dot.cmd('go')
    assert 'FIND CPS/setup NAME SESSION_KIT_%s.zip' % k in lines, lines
    code, lines = w.dot.run(code, lines)
    assert list((w.base / 'outbox/v2').glob('cleared_*/HALT.json')), 'the clear moved HALT.json'
    r = [entry(w, s) for s in range(4, 7) if w.drive.has(N.series_folder('D1'), N.entry_name('D1', s))]
    rs = [e for e in r if e['kind'] == 'RESTORE']
    assert rs and (rs[0]['cleared_local'] or {}).get('code') == 'FORK' and rs[0]['cleared_local']['head_seq'] == 3, \
        [(e['kind'], e['cleared_local']) for e in r]
    return finish(w, code, lines)


def D_clear_same_boot_setup_failed(w):
    code, lines = w.start()                       # (the ok marker skips the real setup; then it is made a failure)
    (w.tools / 'var/cps_vm2_setup_ok').unlink()
    (w.tools / 'var/cps_vm2_setup_failed').write_text('%s %s\n' % (w.boot, w.commit))
    (w.base / 'outbox/setup_20261111T000000Z.log').write_text('invented setup log\n')
    code, lines = w.dot.cmd('go')
    code, lines = w.dot.run(code, lines)
    assert lines[-1] == 'DO: STOP SETUP_FAILED HANDBACK C', lines
    assert w.drive.has('CPS/reports', 'setup_20261111T000000Z.log')
    h = json.loads((w.base / 'outbox/v2/HALT.json').read_text())
    assert h['kit_sha256'] is None and h['tried'] == [fakes.sha(w.kit)[:12]], h
    code, lines = w.dot.cmd('go')
    assert lines[-1] == 'DO: STOP SETUP_FAILED HANDBACK C' and not any(x.startswith('FIND') for x in lines)
    w.simulate_setup()
    (w.tools / 'var/cps_vm2_setup_failed').unlink()
    clear(w, lines)
    code, lines = w.dot.cmd('go')
    code, lines = w.dot.run(code, lines)
    g = entry(w, 1)
    assert g['kind'] == 'GENESIS' and g['cleared_local'] == {'code': 'SETUP_FAILED', 'head_seq': 0,
                                                              'kit_sha256': None}, g['cleared_local']
    assert (w.base / 'inbox/.boot').is_file()
    return finish(w, code, lines)


def D_slip_wrong_id_refinds(w):
    w.dot.policy.update(found='manual', slips=[['wrong_id', 4], ['wrong_id_save', 5]])   # a session FIND, then a SAVE
    code, lines = go(w)
    code, lines = w.dot.run(code, lines)
    blk = [b['lines'] for b in w.dot.blocks if len(b['lines']) > 1 and b['lines'][1].startswith('REFUSED DOWNLOAD_MISSING ')]
    assert len(blk) == 2 and ' state=SAVE' in blk[1][0], [b[:2] for b in blk]
    for b in blk:                                     # GAP-5: the block after the REFUSED line FINDs that name again
        name = b[1].split()[2]
        assert any(x.startswith('FIND ') and x.endswith(' NAME ' + name) for x in b[2:]) and not any(
            x.startswith('DOWNLOAD ') for x in b[2:]), b
        assert any(w.drive.has(f, name) for f in list(w.drive.folders)), name     # and the commit completes
    return finish(w, code, lines)


def D_slip_size_refinds(w):
    w.dot.policy.update(slips=[['size', 4]])
    code, lines = go(w)
    code, lines = w.dot.run(code, lines)
    assert any(x.startswith('REFUSED DOWNLOAD_INCOMPLETE ') for x in w.dot.refused), w.dot.refused
    return finish(w, code, lines)


def D_slip_short_download_refinds(w):
    w.dot.policy.update(slips=[['short_download', 2]])
    code, lines = go(w)
    code, lines = w.dot.run(code, lines)
    assert any(x.startswith('REFUSED DOWNLOAD_INCOMPLETE ') for x in w.dot.refused), w.dot.refused
    return finish(w, code, lines)


def D_slip_stale_raw_head_search(w):
    w.dot.policy.update(slips=[['stale_raw', 5]])
    code, lines = go(w)
    code, lines = w.dot.run(code, lines)
    assert 'REFUSED RAW_INVALID missing' in w.dot.refused, w.dot.refused
    return finish(w, code, lines)


def D_slip_limit_then_clear(w):
    w.dot.policy.update(slips=[['missing', k] for k in (3, 4, 5, 6)])
    code, lines = go(w)
    code, lines = w.dot.run(code, lines)
    assert lines[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C', lines
    h = json.loads((w.base / 'outbox/v2/HALT.json').read_text())
    assert h['detail']['last'] == 'DOWNLOAD_MISSING', h
    clear(w, lines)
    code, lines = w.dot.cmd('go')
    code, lines = w.dot.run(code, lines)
    return finish(w, code, lines)


def E_inputs_lost_after_reset_bounded(w):
    w.dot.policy['inputs'] = 'lost'
    code, lines = go(w)
    w.dot.hook = reset_at(2)
    code, lines = w.dot.run(code, lines)
    assert lines[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C', lines
    assert sum(1 for x in w.dot.refused if x == 'REFUSED INPUTS_CHANGED') == 3, w.dot.refused
    w.dot.hook = None
    clear(w, lines)
    w.dot.hook = lambda dot, ls: 'stop' if ls and 'case=CASE_ID' in ls[-1] else None
    code, lines = w.dot.cmd('go')
    code, lines = w.dot.run(code, lines)
    s = w.drive_state()
    assert [R['status'] for R in s['runs'].values()] == ['ABANDONED'], s['runs']
    return 'abandoned after the clear'


def test_foreground_died_same_boot_stops(w):
    """S-12 (W16, W49, W58): a real subprocess of `vm2.py go` in its own process group, SIGKILL after the RUNNING line
    (returncode -9; it never passes on a race), then: STOP FOREGROUND_DIED with the real head and kit, STATE.json kept,
    the job folder as the kill left it, no staging or temporary leftovers; then the clear: the check's FIND and
    DOWNLOAD, the cache moved, settle moves the killed job folder aside, the RESTORE records cleared_local."""
    code, lines = go(w)

    def h(dot, ls):                   # the download-back of AI1's entry; the `go` after it runs the finish chain
        dl = [ln.split() for ln in ls if ln.startswith('DOWNLOAD ') and N.entry_name('D1', 5) + '.1' in ln]
        for t in dl:
            dot.download(t[3], t[5])
        return 'stop' if dl else None
    w.dot.hook = h
    code, lines = w.dot.run(code, lines)
    w.dot.hook = None
    tree0 = w.jobs_tree()
    p = subprocess.Popen([sys.executable, '-I', '-B', os.path.join(VM2, 'vm2.py'), 'go'], env=w.env(),
                         stdout=subprocess.PIPE, text=True, start_new_session=True)
    first = p.stdout.readline()
    assert first.startswith('CPSV-RUNNING kind=chain'), first + p.stdout.read()
    assert (w.base / 'outbox/v2/FOREGROUND.json').is_file() and p.poll() is None, 'exited before the kill'
    time.sleep(1.5)
    assert p.poll() is None, 'the stage ended before the kill: no race is ever a pass'
    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    assert p.wait() == -9
    killed = w.jobs_tree()
    (w.base / 'outbox/v2/.tmp_killed_write').write_bytes(b'half')      # what a kill inside a durable write or a
    (w.base / '.cps_vm_stage_killed').mkdir()                          # staging leaves (this kill hit the runner)
    code, lines = w.dot.cmd('go')
    assert lines[-1] == 'DO: STOP FOREGROUND_DIED HANDBACK C', lines
    st = json.loads((w.base / 'outbox/v2/STATE.json').read_text())
    assert hdr(lines)['head'] == '%06d' % st['head']['seq'] and hdr(lines)['kit'] == st['kit_sha256'][:12], lines
    assert w.jobs_tree() == killed and list((w.base / 'outbox/v2').glob('dead_*.json'))
    assert not list(w.base.glob('**/.cps_vm_stage_*')) and not list((w.base / 'outbox').glob('**/.tmp_*'))
    k = clear(w, lines)
    code, lines = w.dot.cmd('go')
    assert 'FIND CPS/setup NAME SESSION_KIT_%s.zip' % k in lines, lines
    code, lines = w.dot.run(code, lines)
    assert tree0 is not None and list((w.base / 'outbox/v2').glob('cleared_*/STATE.json'))
    assert list((w.base / 'outbox/v2').glob('aside_*/*')), 'settle moved the killed job folder aside'
    rs = [e for e in (entry(w, s) for s in range(1, 30) if w.drive.has(N.series_folder('D1'), N.entry_name('D1', s)))
          if e['kind'] == 'RESTORE' and e['cleared_local']]
    assert rs and rs[0]['cleared_local']['code'] == 'FOREGROUND_DIED', rs
    return finish(w, code, lines)



def after_clear(w, i0, k):
    """Every D_clear_same_boot_* scenario: after the clear the check's FIND and DOWNLOAD of the clear kit, then at
    least one `found` and one `answer` of the restore."""
    bl = w.dot.blocks[i0:]
    lines = [ln for b in bl for ln in b['lines'] or []]
    assert 'FIND CPS/setup NAME SESSION_KIT_%s.zip' % k in lines, 'the check FIND'
    assert any(ln.startswith('DOWNLOAD CPS/setup ') for ln in lines), 'the check DOWNLOAD'
    assert {'found', 'answer'} <= {b['argv'][0] for b in bl}, 'a found and an answer of the restore'


def restores(w):
    out = []
    for s in range(1, 60):
        if not w.drive.has(N.series_folder(w.series), N.entry_name(w.series, s)):
            break
        out.append(entry(w, s))
    return out


def D_clear_same_boot_foreground_died(w):
    """D5 (W03): a stage killed in the same boot (fakes.Kill after the finish stage's runner): STOP FOREGROUND_DIED;
    the clear moves the cache, settle moves the dead stage's job folder aside, the RESTORE records cleared_local."""
    code, lines = go(w)
    w.seams.arm('runner_after', 1, fakes.Kill, 'finish')
    code, lines = w.dot.run(code, lines)
    assert lines[-1] == 'DO: STOP FOREGROUND_DIED HANDBACK C' and w.seams.hits, lines
    i0, k = len(w.dot.blocks), clear(w, lines)
    code, lines = w.dot.cmd('go')
    code, lines = w.dot.run(code, lines)
    after_clear(w, i0, k)
    assert list((w.base / 'outbox/v2').glob('aside_*/*')), 'settle moved the dead stage\'s folder aside'
    rs = [e for e in restores(w) if e['kind'] == 'RESTORE' and e['cleared_local']]
    assert rs and rs[0]['cleared_local']['code'] == 'FOREGROUND_DIED', rs
    return finish(w, code, lines)


def D_sameboot_damaged_cache_restores(w):
    """D5 (W03): STATE.json damaged in the same boot: the cache moves to invalid_<utc14>/, the restore runs in this
    boot, and placement keeps the job folder whose walk equals the plan (no PLACE_TARGET_NOT_EMPTY)."""
    code, lines = go(w)
    done = []

    def h(dot, ls):
        if not done and hdr(ls).get('head') == '000005':
            done.append(1)
            p = w.base / 'outbox/v2/STATE.json'
            p.write_bytes(p.read_bytes()[:-7] + b'damaged')
            for n in ('.tmp_2_VM_HELPER_CONFIG.json', '.tmp_3_x'):      # A4 (W122): a killed write_atomic's leftovers
                (w.base / 'runtime' / n).write_bytes(b'{"left": "by a killed command"}')
            return 'stop'
    w.dot.hook = h
    code, lines = w.dot.run(code, lines)
    w.dot.hook = None
    code, lines = w.dot.cmd('go')                         # the Dot's next command: the cache is invalid, a restore
    code, lines = w.dot.run(code, lines)
    assert done and list((w.base / 'outbox/v2').glob('invalid_*/STATE.json')), 'the damaged cache moved aside'
    rs = [e for e in restores(w) if e['kind'] == 'RESTORE']
    assert rs and rs[0]['boot_id'] == entry(w, rs[0]['seq'] - 1)['boot_id'], 'a same-boot RESTORE'
    assert not list((w.base / 'runtime').glob('.tmp_*')), 'A4: the leftovers left runtime, the kit stayed the same'
    return finish(w, code, lines)


def notes_hint(w):
    h = dict(x.split('=', 1) for x in w.dot.notes['cpsv'].split()[1:])
    return None if h['kit'] == 'none' else (h['head'], h['kit'])


def D_base_wiped_same_boot_restores(w):
    """Amendment A5 (i): BASE is gone in the same boot (the Dot's /tmp/cps) while TOOLS and its setup marker for this boot
    and commit stay. The Dot runs the bootstrap (README section 1: vm.sh is missing): no setup runs, the session restores
    from the journal in the same boot, and the audit lists that RESTORE as a same-boot restore."""
    code, lines = go(w)
    w.dot.hook = lambda dot, ls: 'stop' if hdr(ls).get('head') == '000005' else None
    code, lines = w.dot.run(code, lines)
    w.dot.hook = None
    assert hdr(lines).get('head') == '000005', lines
    mark, n0 = (w.tools / 'var/cps_vm2_setup_ok').read_text(), len(restores(w))
    fakes.force_rmtree(w.base)
    w.dot.opened, w.dot.convs, w.dot.current = {}, dict(w.dot.convs), None       # as FakeDot.reset, without a new boot
    code, ls = w.dot.bootstrap(w.dot.notes['repo'], notes_hint(w))
    assert code == 0 and not any(x.startswith('CPSV-RUNNING') for x in w.dot.blocks[-1]['lines']), ls
    assert (w.tools / 'var/cps_vm2_setup_ok').read_text() == mark and (w.base / 'tmp').is_dir()
    code, lines = w.dot.cmd('go')
    code, lines = w.dot.run(code, lines)
    rs = [e for e in restores(w)[n0:] if e['kind'] == 'RESTORE']
    assert rs and rs[0]['boot_id'] == entry(w, rs[0]['seq'] - 1)['boot_id'], 'a same-boot RESTORE'
    last = finish(w, code, lines)
    c, rep, out = w.audit(str(w.root) + '_aud2')
    assert rep['clean'] and rs[0]['seq'] in rep['same_boot_restores'], (rep['same_boot_restores'], rs[0]['seq'])
    return last


def D_tools_wiped_same_boot_continues(w):
    """Amendment A5 (ii) (W127): TOOLS (~/cps-tools) is gone in the same boot while BASE stays. The next stage stops with
    STOP SETUP_MISSING before the runner, and nothing is sticky (no HALT.json; a second `go` prints the same stop). The
    Dot then does what README section 1 says (fix round PF-8): it runs the bootstrap once, whose light setup runs again
    (simulated, as in every World), and the helper continues from BASE: no RESTORE after the wipe, FINAL."""
    code, lines = go(w)
    w.dot.hook = lambda dot, ls: 'stop' if hdr(ls).get('head') == '000003' else None
    code, lines = w.dot.run(code, lines)
    w.dot.hook = None
    n0, st0 = len(restores(w)), json.loads((w.base / 'outbox/v2/STATE.json').read_text())['boot_id']
    fakes.force_rmtree(w.tools)
    code, lines = w.dot.run(code, lines)
    assert lines[-1] == 'DO: STOP SETUP_MISSING HANDBACK C', lines
    assert not (w.base / 'outbox/v2/HALT.json').exists() and not (w.base / 'outbox/v2/FOREGROUND.json').exists()
    code, again = w.dot.cmd('go')
    assert again[-1] == 'DO: STOP SETUP_MISSING HANDBACK C', again
    w.simulate_setup()
    code, ls = w.dot.bootstrap(w.dot.notes['repo'], notes_hint(w))
    assert code == 0, ls
    code, lines = w.dot.cmd('go')
    code, lines = w.dot.run(code, lines)
    assert not [e for e in restores(w)[n0:] if e['kind'] == 'RESTORE'], 'continued from BASE, no restore'
    assert json.loads((w.base / 'outbox/v2/STATE.json').read_text())['boot_id'] == st0
    return finish(w, code, lines)


def D_clear_committed_halt_same_boot(w):
    """SD-51 (W51): a committed HALT (HALTED_PROMPT_CHANGED) cleared in the same boot: the RESTORE keeps the halted
    kit (kit_change null, cleared_local null); the CLEAR that follows takes the clear kit (from != to)."""
    code, lines = go(w)
    done = []

    def h(dot, ls):                   # at the AI entry's SAVE block, before the found that runs the finish stage
        d = hdr(ls)
        st = w.state() if (w.base / 'outbox/v2/STATE.json').is_file() else None
        R = st and st['current'] and st['runs'][st['current']]
        if not done and R and d.get('state') == 'SAVE' and 'G1' in R['roles'] and \
                (w.base / 'outbox/v2/PENDING.json').is_file() and \
                json.loads((w.base / 'outbox/v2/PENDING.json').read_text())['seq'] == 5:     # AI1 of the D series
            done.append(1)
            lt = [x for x in R['roles']['G1']['starts'] if x['superseded_by'] is None][-1]
            os.chmod(lt['prompt'], 0o644)
            with open(lt['prompt'], 'ab') as fh:
                fh.write(b'\n')
    w.dot.hook = h
    code, lines = w.dot.run(code, lines)
    w.dot.hook = None
    assert lines[-1] == 'DO: STOP HALTED_PROMPT_CHANGED HANDBACK C', lines
    halt = [e for e in restores(w) if e['kind'] == 'HALT'][-1]
    i0, k = len(w.dot.blocks), clear(w, lines)
    code, lines = w.dot.cmd('go')
    code, lines = w.dot.run(code, lines)
    after_clear(w, i0, k)
    es = [e for e in restores(w) if e['seq'] > halt['seq']]
    assert es[0]['kind'] == 'RESTORE' and es[0]['body']['kit_change'] is None and es[0]['cleared_local'] is None \
        and es[0]['kit_sha256'] == halt['kit_sha256'], es[0]['kind']
    assert es[1]['kind'] == 'CLEAR' and es[1]['kit_sha256'] != halt['kit_sha256'] and \
        es[1]['body']['kit_change']['from_kit_sha256'] == halt['kit_sha256'], es[1]['kind']
    return lines[-1]


def D_clear_same_boot_fork_foreign_only(w):
    """GAP-04 (W77): our upload of seq 4 never lands and a foreign copy of that name does: FORK; after the clear the
    head search finds only the foreign copy at the moved PENDING's seq, and the clearing restore stops FORK again."""
    name = N.entry_name('D1', 4)
    w.drive.drop[name] = {1, 2, 3}
    code, lines = go(w)
    planted = []

    def h(dot, ls):
        if not planted and any(x.startswith('UPLOAD ') and x.endswith(' AS ' + name) for x in ls):
            planted.append(w.drive.plant(N.series_folder('D1'), name, b'foreign invented entry bytes only'))
    w.dot.hook = h
    code, lines = w.dot.run(code, lines)
    w.dot.hook = None
    assert lines[-1] == 'DO: STOP FORK HANDBACK C', lines
    i0, k = len(w.dot.blocks), clear(w, lines)
    code, lines = w.dot.cmd('go')
    code, lines = w.dot.run(code, lines)
    assert lines[-1] == 'DO: STOP FORK HANDBACK C', ('FORK again', lines)
    assert not w.drive.has(N.series_folder('D1'), N.entry_name('D1', 5)), 'nothing committed after the fork'
    return 'FORK again'


def D_clear_same_boot_open_generator(w):
    """GAP-02 (W76): the G answer is refused four times (an invalid tools file): SLIP_LIMIT; the clear; the restore's
    FakeDot outcome policy is NOTHING_WRITTEN, but the conversation's files are found before settle, so `outcome` is
    never asked, the item is forced FILES_FOUND and the run freezes with T47 (AI_OUTPUT_LOST)."""
    real = w.dot.tools_answer
    w.dot.tools_answer = lambda: 'file:' + str(w.base / 'attest/no_such_tools.txt')
    code, lines = go(w)
    code, lines = w.dot.run(code, lines)
    for _ in range(5):                                    # the Dot answers each re-asked block again
        if not (code == 4 and lines[1].startswith('REFUSED TOOLS_FILE_INVALID')):
            break
        code, lines = w.dot.execute(lines)
    w.dot.tools_answer = real
    assert lines[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C', lines
    assert sum(1 for x in w.dot.refused if x.startswith('REFUSED TOOLS_FILE_INVALID')) == 3, w.dot.refused
    w.dot.policy['restore'] = {'outcome': 'NOTHING_WRITTEN'}
    n0 = len(w.dot.answered)
    i0, k = len(w.dot.blocks), clear(w, lines)
    code, lines = w.dot.cmd('go')
    code, lines = w.dot.run(code, lines)
    after_clear(w, i0, k)
    assert not [a for a in w.dot.answered[n0:] if a.get('role') == 'G' and 'outcome' in a], w.dot.answered[n0:]
    rs = [e for e in restores(w) if e['kind'] == 'RESTORE' and e['body']['resolutions']]
    assert rs and rs[0]['body']['resolutions'][0]['forced'] == 'FILES_FOUND', rs and rs[0]['body']['resolutions']
    return finish(w, code, lines)


def D_hint_restore_late_copy_at_n1_forks_at_recheck(w):
    """D6/SD-59 (W78): a reset with the Dot's hint; while the restore waits for its RECHECK, a different copy lands at
    the RESTORE's own name: the RECHECK stops FORK before any later commit."""
    code, lines = go(w)
    state = {'n': 0}

    def h(dot, ls):
        d = hdr(ls)
        if state['n'] == 0 and d.get('head') == '000005':
            state['n'] = 1
            return 'reset'
        wk = w.base / 'outbox/v2/RESTORE_WORK.json'
        if state['n'] == 1 and wk.is_file() and (json.loads(wk.read_text()).get('committed') or {}).get('seq') \
                and ls[-1].startswith('DO: WAIT'):
            state['n'] = 2
            state['seq'] = json.loads(wk.read_text())['committed']['seq']
            w.drive.plant(N.series_folder('D1'), N.entry_name('D1', state['seq']), b'a different invented copy')
    w.dot.hook = h
    code, lines = w.dot.run(code, lines)
    assert state['n'] == 2 and lines[-1] == 'DO: STOP FORK HANDBACK C', (state, lines)
    assert not w.drive.has(N.series_folder('D1'), N.entry_name('D1', state['seq'] + 1)), 'no later commit'
    return 'FORK at the RECHECK'


# name -> (series, cases or None for the World's default): registered in test_resets.scenarios() as specials
SPEC = {n: ('E1', ()) if n.startswith('E_') else ('D1', None) for n in (
    'D_reset_commit_boundary', 'D_refuse_reset_approval_pending', 'D_refuse_reset_approval_wrong_none',
    'D_clear_same_boot_fork', 'D_clear_same_boot_setup_failed', 'D_slip_wrong_id_refinds', 'D_slip_size_refinds',
    'D_slip_short_download_refinds', 'D_slip_stale_raw_head_search', 'D_slip_limit_then_clear',
    'E_inputs_lost_after_reset_bounded', 'test_foreground_died_same_boot_stops', 'D_clear_same_boot_foreground_died',
    'D_sameboot_damaged_cache_restores', 'D_clear_committed_halt_same_boot', 'D_clear_same_boot_fork_foreign_only',
    'D_clear_same_boot_open_generator', 'D_hint_restore_late_copy_at_n1_forks_at_recheck',
    'D_base_wiped_same_boot_restores', 'D_tools_wiped_same_boot_continues')}
