"""One regression test per finding of admission review 1 of cps-vm-helper.v1 (deploy/vm/ADMISSION_VM_HELPER_V1.json,
44 ids), named as spec §14.4 maps them (with the probe-results delta §X.14). Invented data only.

Three kinds of test:
  direct    a function here (core, vio, maintainer or shell level; no runner), run by run();
  delegate  a function here that runs the named test of another suite which already is the regression (the id and
            the reason are in MAP);
  world     a reset scenario with the real runner v4: WORLD below is added to test_resets.scenarios() and runs there
            (its extra oracle is the function named in the scenario's 'extra'); run() reports it as 'world'.
MAP: v1 id -> (test name, kind, how v2 answers the finding). `by construction` marks the v1 paths that v2 deleted;
the test then shows that the path cannot be reached (which primitive replaces it, and that it refuses).
Entry point: run(only=None, work=None)."""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
VM2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(VM2))
sys.path.insert(0, HERE)
sys.path.insert(0, VM2)
import core_world as CW                                                     # noqa: E402
from cpsvm2.core import fold as F, names as N, outcome as O, plan as P, session as SE   # noqa: E402

WORK = None

MAP = {
    'F1': ('test_f1_wipe_after_v_r2_written_before_ai_v_r2_confirmed', 'world+direct',
           'a CONTINUED V resolves only by T46 (FREEZE_VISUAL_FAILED): no OPEN or CONTINUE for V after the reset'),
    'F2': ('test_f2_second_start_only_after_no_conversation', 'direct',
           'a second START of one attempt exists only through T43 (list shows none, once) or T31 (rebase); T32 '
           'refuses it otherwise; random cuts in test_core_props'),
    'F3': ('test_f3_classify_reads_only_head_at_every_worker_point', 'world+direct',
           'by construction: classify(head, state, ...) reads only the head; the B prepare fetches A FROZEN.json'),
    'F4': ('test_f4_outcomes_total_over_frozen_shapes', 'delegate:test_core_table',
           'one pure outcomes() over the fold state'),
    'F5': ('test_f5_audit_planted_restore_unknown_to_final', 'delegate:test_maint',
           'the audit re-folds the journal; it copies nothing from ALL_FROZEN.json'),
    'F6': ('test_f6_every_block_has_exactly_one_terminal_action', 'direct',
           'by construction: every PrintBlock renders exactly one DO line (the grammar lint runs on every block)'),
    'F7': ('test_f7_written_lost_transcript_in_restore_entry', 'world+direct',
           'an exported transcript is a RESTORE member (T48 without it); with export no (O55) nothing is exported'),
    'F8': ('test_f8_dead_commit_plus_next_stage', 'world',
           'a head without a part is rebased (T49), the next stage re-runs bound; the audit is clean'),
    'SAFE-01': ('test_safe01_unsupported_entries_halt_nothing_deleted', 'direct',
                'strict tree_list everywhere (snapshot, AI walk, evict): WALK_UNSUPPORTED_ENTRY, nothing deleted'),
    'SAFE-02': ('test_safe02_case_id_refused_before_any_write', 'direct',
                'CASE_ID fullmatch and forbidden characters: REFUSED, every cache file byte-identical'),
    'SAFE-03': ('test_safe03_probe_p5_same_call_check_refused', 'delegate:test_probe_p5',
                'probe_p5 refuses a same-call check; P5 is answered (FAIL) and gates nothing (§X.12.5)'),
    'SAFE-04': ('test_safe04_enospc_or_short_write_at_every_durable_write', 'direct',
                'durable.write checks every write, fsync and read-back: DISK_FULL/WRITE_FAILED, no UPLOAD printed'),
    'SAFE-05': ('test_safe05_trailing_newline_and_bad_id_refused', 'direct',
                're.fullmatch with re.ASCII on every attested value; ids match drive_id_re'),
    'SAFE-06': ('test_safe06_session_start_git_error_prints_stop_block', 'direct',
                'no set -e; every failure prints a full STOP block'),
    'SAFE-07': ('test_safe07_setup_runs_foreground_and_gate_uses_hold', 'direct',
                'setup in the foreground of session_start.sh; the release gate uses the foreground hold'),
    'OP-01': ('test_op01_start_on_drive_before_first_open', 'world',
              'the START is in the STAGE entry; OPEN is printed only after the entry is confirmed (O1)'),
    'OP-02': ('test_op02_lost_restore_upload_three_tries_then_stop', 'world',
              'the RESTORE is a commit like any other: at most 3 uploads, then STOP UPLOAD_FAILED'),
    'OP-03': ('test_op03_truncated_all_frozen_part_reuploaded_before_handback_b', 'world',
              'FINAL parts are confirmed before HANDBACK B; a part lost to a reset is re-uploaded (C3)'),
    'OP-04': ('test_op04_placeholders_refused_state_unchanged', 'direct',
              'placeholders, key names, pattern names and README examples are VALUE_FORBIDDEN/VALUE_PLACEHOLDER'),
    'OP-05': ('test_op05_probe_same_session_refused', 'delegate:test_probe_p5', 'as SAFE-03'),
    'OP-06': ('test_op06_helper_never_needs_a_listing', 'direct',
              'by construction: exact-name FIND only; LIST NEWEST 10 is a head hint, never a lookup'),
    'OP-07': ('test_op07_drive_calls_per_run_within_budget', 'world',
              'measured Drive calls per run and per restore within the §X.5.5 budget'),
    'OP-08': ('test_op08_every_file_uploaded_once_when_drive_is_normal', 'world',
              'by construction: one commit primitive; every journal file is uploaded once on a normal Drive'),
    'OP-09': ('test_op09_selftest_worker_death_bounded', 'direct',
              'a dead self-test is retried once (SELFTEST_DIED); OPENED is asked without a list; everyday asks in '
              'order (the world half is test_resets test_selftest_died_retried_once_then_stops)'),
    'TST-01': ('test_tst01_second_start_same_attempt_chain_invalid', 'delegate:test_core_table', 'T32'),
    'TST-02': ('test_tst02_nothing_written_with_file_found_is_written', 'direct', 'forced FILES_FOUND -> T47'),
    'TST-03': ('test_tst03_not_ended_is_written', 'direct', 'forced NOT_ENDED -> T47'),
    'TST-04': ('test_tst04_md5_hidden_download_back_mismatch_is_fork', 'direct',
               'the download-back sha256 compare (§X.5.5) meets a mismatching download: FORK'),
    'TST-05': ('test_tst05_consumer_tree_sha_mismatch_chain_invalid', 'direct+world',
               'consumed tree sha must equal the archive (fold) and is measured (worker: AI_OUTPUT_CHANGED)'),
    'TST-06': ('test_tst06_prompt_changed_halts', 'world', 'a changed generator prompt halts before the record'),
    'TST-07': ('test_tst07_b_before_a_frozen_chain_invalid_and_runner_refuses', 'direct',
               'T10 needs A frozen (T14 otherwise); the plan never proposes B first'),
    'TST-08': ('test_tst08_under_stage_direct', 'direct', 'the reused under_stage, tested directly'),
    'TST-09': ('test_tst09_no_catch_all_assertions', 'delegate:test_lints', 'lint L7'),
    'TST-10': ('test_tst10_free_space_preflight', 'direct', 'run_tests.py refuses under 1 GiB free'),
    'KIT-1': ('test_kit1_release_swap_after_genesis_stops', 'direct',
              'S5: every entry carries the genesis release; another release needs a KIT_CHANGE with no run in '
              'flight and acceptance'),
    'KIT-2': ('test_kit2_zip_route_rehashes_the_kit', 'world', 'the downloaded kit is hashed: KIT_NOT_VERIFIED'),
    'FLAGS-1': ('test_flags1_wrong_shared_or_real_carrier_inconsistent', 'delegate:test_maint', 'score_check'),
    'FLAGS-2': ('test_flags2_empty_carriers_distinct_per_reader', 'delegate:test_maint', 'score_check'),
    'FLAGS-3': ('test_flags3_runner_failed_runs_get_empty_carriers', 'delegate:test_maint', 'score_check'),
    'MK-1': ('test_mk1_header_slip_in_one_copy_recovers', 'direct',
             'deploy/make_kit.py is outside cps-vm-helper.v2; its own test of the slipped header is run here'),
    'MK-2': ('test_mk2_duplicate_binary_names_refused', 'direct',
             'outside cps-vm-helper.v2 (deploy/make_kit.py pack, unchanged): reported open, see the docstring'),
    'GATE-1': ('test_gate1_gates_checked_on_every_go', 'direct', 'gates_check runs before every plan step'),
    'TEST-1': ('test_test1_kit_change_with_run_in_flight_stops', 'direct', 'KIT_CHANGE_WITH_RUN_IN_FLIGHT'),
}


# ================================================================ helpers
def raises(code, fn):
    try:
        fn()
    except F.ChainInvalid as c:
        assert c.code == code, 'expected %s, got %s' % (code, c.code)
        return
    raise AssertionError('expected ChainInvalid %s' % code)


def tc():
    import test_core_table
    return test_core_table


def tv():
    import test_vio
    test_vio.WORK = WORK
    return test_vio


def view(s, marks=None, boot=None):
    return {'state': s, 'marks': marks or {}, 'local': {'gates_ok': True}, 'now': CW.utc(CW.T0 + 10 ** 6),
            'boot_id': boot or CW.boot(9), 'base': CW.BASE, 'cfg': {'clear': None, 'transcript_ext': 'json'}}


def ans(**k):
    a = {'ended': True, 'files_found': False, 'transcript': 'exported', 'outcome': 'NOTHING_WRITTEN',
         'list_shows_none': None}
    a.update(k)
    return a


def resolve(w, a):
    op = CW.open_role(w.state)
    e = CW._restore(w, resolve=op, ans=a)
    return e, e['body']['resolutions'][0]


def expect_halt(code, fn, *a, **k):
    from cpsvm2.vio.v1compat import Halt
    try:
        fn(*a, **k)
    except Halt as h:
        assert h.code == code, 'got %s, want %s' % (h.code, code)
        return h
    raise AssertionError('no Halt %s' % code)


# ================================================================ direct tests
def test_f1_core_continued_v_is_t46():
    """F1, core half: REVIEW_INCOMPLETE committed (V1 CONTINUED), the reviewer's r2 lost to a reset: the only legal
    resolution is T46 FREEZE_VISUAL_FAILED; after it the plan runs the freeze chain, never CONTINUE or OPEN for V; the
    FROZEN carries VISUAL_QA_FAILED_BY_RESET and outcomes() reports the pair's visual QA as FAILED_BY_RESET."""
    T = tc()
    w = T.q_world()
    T.drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH', 'AI', 'REVIEW_INCOMPLETE')
    R = w.state['runs']['A/case01']
    assert R['roles']['V1']['status'] == 'CONTINUED'
    for oc in ('NOTHING_WRITTEN', 'WRITTEN', 'NO_CONVERSATION'):
        e, it = resolve(w, ans(outcome=oc, transcript='not_available'))
        assert it['action'] is None or it['action'] == 'FREEZE_VISUAL_FAILED', it
    e, it = resolve(w, ans(outcome='CONTINUED', transcript='not_available'))
    assert it['action'] == 'FREEZE_VISUAL_FAILED'
    bad = json.loads(json.dumps(e))
    bad['body']['resolutions'][0]['action'] = 'REPLACE'
    raises('T48', lambda: F.apply(w.state, bad))
    assert w.commit(e) == ['T42', 'T46']
    st = P.next_action(view(w.state))
    assert type(st).__name__ == 'RunChain' and st.first == 'freeze', st
    T.drive(w, 'FREEZE_')
    R = w.state['runs']['A/case01']
    assert R['status'] == 'FROZEN' and 'VISUAL_QA_FAILED_BY_RESET' in R['flags'], R['flags']
    pair = [p for p in O.outcomes(w.state)['pairs'] if p['run'] == 'A/case01'][0]
    assert pair['visual'] == 'FAILED_BY_RESET', pair


def test_f2_second_start_only_after_no_conversation():
    """F2: a START that never reached Drive cannot open a second conversation silently. A second START of one attempt
    folds only through T43 (NO_CONVERSATION with the list showing none: START_SUPERSEDED, once) ; list_shows_none=no
    is forced NO_CONVERSATION_NOT_ALLOWED (T47, AI_OUTPUT_LOST); a STAGE with another START of the attempt is T32."""
    T = tc()
    w = T.q_world()
    T.drive(w, 'PREPARE_GENERATE')
    w2 = json.loads(json.dumps(w.state))
    e, it = resolve(w, ans(outcome='NO_CONVERSATION', list_shows_none=False))
    assert (it['forced'], it['action']) == ('NO_CONVERSATION_NOT_ALLOWED', 'FREEZE_LOST'), it
    e, it = resolve(w, ans(outcome='NO_CONVERSATION', list_shows_none=True))
    assert it['action'] == 'SUPERSEDE' and e['body']['start']['start_no'] == 2
    assert w.commit(e) == ['T42', 'T43']
    R = w.state['runs']['A/case01']
    assert 'START_SUPERSEDED' in R['flags'] and len(R['roles']['G1']['starts']) == 2
    e, it = resolve(w, ans(outcome='NO_CONVERSATION', list_shows_none=True))
    assert it['forced'] == 'NO_CONVERSATION_NOT_ALLOWED', 'a second supersede of one attempt is never allowed'
    o = O.outcomes(w.state)
    assert any(x['kind'] == 'O52_SHEET' for x in o['owner_items']) or o['o52_sheet'], 'two STARTs reach the sheet'
    assert w2['runs']['A/case01']['roles']['G1']['supersedes'] == 0


def test_f3_core_classify_reads_only_the_head():
    """F3, core half: classify takes the head entry and its fold state only; at every chain point the same head gives
    the same row whatever else is local (C9 for a lost new run, C8 for a lost stage of an existing run)."""
    T = tc()
    w = T.q_world()
    assert SE.classify(w.entries[-1], w.state, [], None, True, CW.GATES)[0] == 'C9'
    T.drive(w, 'PREPARE_GENERATE', 'AI')
    assert SE.classify(w.entries[-1], w.state, [], None, True, CW.GATES)[0] == 'C8'
    import inspect
    assert list(inspect.signature(SE.classify).parameters) == ['head', 'state', 'missing_parts', 'clear',
                                                                'kit_config_only', 'gates']


def test_f6_every_block_has_exactly_one_terminal_action():
    """F6: a block with DOWNLOAD lines (or with nothing) still ends in exactly one DO line (RUN go); the grammar check
    refuses a block without DO, with two, or with a DO line that is not last. Every block printed by the world and vio
    suites passes drive.check_grammar (FakeDot.cmd, test_vio.parse_block)."""
    from cpsvm2.core.step import PrintBlock
    from cpsvm2.vio import drive
    for blk in (PrintBlock('KIT', downloads=(('CPS/setup', 'x' * 24, '/home/agent/cps/inbox/kit/k.zip'),)),
                PrintBlock('WORK')):
        body = drive.body_lines(blk, '/home/agent/cps/vm.sh')
        assert [ln for ln in body if ln.startswith('DO: ')] == [body[-1]], body
        assert body[-1] == 'DO: RUN bash /home/agent/cps/vm.sh go', body
    h = 'CPSV series=D1 head=000001 kit=0123456789ab at=000001-0001-abcdef mode=drill state=WORK'
    for bad in ([h, 'DOWNLOAD CPS/setup ID abc TO /x'], [h, 'DO: RUN x', 'FIND CPS NAME a'], [h, 'DO: A', 'DO: B']):
        assert drive.check_grammar(bad) is not None, bad


def test_f7_core_transcript_member_required():
    """F7, core half: a resolution with transcript=exported folds only with the transcript member in the RESTORE
    payload (T48 without it); with the O55 gate (p1_transcript_export no) the helper never asks for an export."""
    T = tc()
    w = T.q_world()
    T.drive(w, 'PREPARE_GENERATE')
    e, it = resolve(w, ans(outcome='WRITTEN', transcript='exported'))
    assert it['action'] == 'FREEZE_LOST'
    assert any(m[0].startswith('transcript/G1_1.') for m in e['payload']['members'])
    bad = json.loads(json.dumps(e))
    bad['payload']['members'] = [m for m in bad['payload']['members'] if not m[0].startswith('transcript')]
    raises('T48', lambda: F.apply(w.state, bad))
    w.commit(e)


def test_safe01_unsupported_entries_halt_nothing_deleted():
    """SAFE-01: FIFO, symlink, setuid file, sticky folder and an unreadable file in a job folder halt the snapshot, the
    AI walk and evict with WALK_UNSUPPORTED_ENTRY (or EVICT_MISMATCH), and nothing is deleted (test_vio's strict-walk
    and evict tests, plus the three call sites here)."""
    V = tv()
    V.t_walk_strict_unsupported_entries()
    V.t_evict_changed_file_and_unplace()
    from cpsvm2.vio import place
    from cpsvm2.vio.v1reuse import sha_bytes
    for kind in ('fifo', 'symlink', 'setuid'):
        root = V.tmpdir('safe01_' + kind)
        env = V.SPEnv(root)
        jd = V.make_job(root, pngs=1)
        fz = b'{"frozen": "invented"}\n'
        (jd / 'FROZEN.json').write_bytes(fz)
        pend, entry, _, _ = V.write_png_commit(env, jd, kind='FROZEN')
        out = jd / 'run/A/output'
        if kind == 'fifo':
            os.mkfifo(out / 'pipe')
        elif kind == 'symlink':
            os.symlink('/etc/hostname', out / 'link')
        else:
            (out / 'x').write_bytes(b'x')
            os.chmod(out / 'x', 0o4755)
        before = sorted(p.name for p in out.iterdir())
        expect_halt('WALK_UNSUPPORTED_ENTRY', place.snapshot, env.lay, str(jd))
        expect_halt('WALK_UNSUPPORTED_ENTRY', place.ai_members, str(out), 10 ** 6)
        try:
            place.evict(env.lay, str(jd), pend['entry']['path'], sha_bytes(fz), 'A_case01_FROZEN.json')
            raise AssertionError('evict accepted a %s' % kind)
        except V.Halt as h:
            assert h.code in ('WALK_UNSUPPORTED_ENTRY', 'EVICT_MISMATCH'), h.code
        assert sorted(p.name for p in out.iterdir()) == before and (jd / 'FROZEN.json').is_file(), 'nothing deleted'


def test_safe02_case_id_refused_before_any_write():
    """SAFE-02: everyday `answer case=` with a space, a quote, a newline, a non-ASCII or fullwidth digit, a brace or a
    placeholder is REFUSED (VALUE_FORBIDDEN/VALUE_PATTERN/VALUE_PLACEHOLDER) and every cache file stays byte-identical;
    nothing is uploaded."""
    V = tv()
    w = V.World()
    code, a = w.cmd('go')
    at = V.at_of(a)
    snap = w.cache_bytes()
    for v in ('case 01', "case'01", 'case01\n', 'casé', '１２', '{CASE_ID}', 'CASE_ID', '-lead', 'a' * 81):
        code, out = w.cmd('answer', '--at', at, 'case=' + v)
        assert code == 4 and out[1] in ('REFUSED VALUE_FORBIDDEN', 'REFUSED VALUE_PATTERN', 'REFUSED VALUE_PLACEHOLDER'), \
            (v, out)
        assert w.cache_bytes() == snap, v


def test_safe04_enospc_or_short_write_at_every_durable_write():
    """SAFE-04: ENOSPC, EIO and a short write at each durable write of a commit and of a cli command: DISK_FULL or
    WRITE_FAILED, no PENDING and no UPLOAD line printed (test_vio's durable, commit and cli tests)."""
    V = tv()
    for fn in (V.t_durable_write_ok_and_short_write, V.t_durable_zero_write_is_eio, V.t_durable_enospc_and_fsync_eio,
               V.t_commit_enospc_at_every_write, V.t_cli_enospc_halts_before_printing):
        fn()


def test_safe05_trailing_newline_and_bad_id_refused():
    """SAFE-05: every name and value pattern is re.fullmatch with re.ASCII: a trailing newline, NUL, a fullwidth digit,
    an id outside drive_id_re are refused; the found syntax rejects them before any state change."""
    for pat, good in ((N.ENTRY, 'CPSJ_Q1_000001.tgz'), (N.PASS, 'FINGERPRINT_PASS_%s0.json' % ('a' * 63)),
                      (N.CASE_ID, '9990101'), (N.UTC_S, '2026-11-10T00:00:00Z')):
        assert N.fm(pat, good)
        for bad in (good + '\n', good + '\x00', '\n' + good, good.replace('0', '０', 1)):
            assert not N.fm(pat, bad), (pat, bad)
    cfg = {'drive_id_re': N.DEFAULT_DRIVE_ID_RE, 'conversation_re': r'conv-[0-9a-f]{8}', 'doc_samples': [],
           'home': '/h', 'case': 'c'}
    assert N.check_value('id', 'ID', 'A' * 24, cfg) is None
    for bad in ('A' * 24 + '\n', 'A' * 19, 'A/' + 'A' * 22, 'A' * 23 + 'é'):
        assert N.check_value('id', 'ID', bad, cfg) is not None, bad
    from cpsvm2.vio import drive
    for f in ('%s:%d' % ('A' * 24, 5),):
        assert drive.parse_copy(f, True) is not None
    for f in ('%s:5\n' % ('A' * 24), 'A' * 24, '%s:x' % ('A' * 24), ':5'):
        c = drive.parse_copy(f, True)
        assert c is None or not N.fm(N.PATTERNS['SIZE'], c[-1]), f


def run_session_start(home, repo, commit, boot='0f0e0d0c-0b0a-4908-8706-050403020100', env_over=None):
    env = dict(os.environ, HOME=str(home), CPS_VM_BASE=str(home / 'cps'), CPS_TOOLS=str(home / 'cps-tools'),
               CPS_VM_BOOT_ID_PATH=str(home / 'boot_id'))
    env.update(env_over or {})
    (home / 'boot_id').write_text(boot + '\n')
    (home / 'cps-tools/var').mkdir(parents=True, exist_ok=True)
    (home / 'cps-tools/var/cps_vm2_setup_ok').write_text('%s %s\n' % (boot, commit))
    p = subprocess.run(['bash', str(repo / 'deploy/vm2/session_start.sh'), '--commit', commit], capture_output=True,
                       text=True, env=env, timeout=120)
    lines = [ln for ln in p.stdout.splitlines() if ln]
    import seen
    seen.scan(lines)
    return p.returncode, lines


def test_safe06_session_start_git_error_prints_stop_block():
    """SAFE-06: a git error is STOP SESSION_GIT_ERROR (a full block, exit 3), never a pass; a dirty tracked tree is
    SESSION_REPO_DIRTY, another commit SESSION_COMMIT_MISMATCH, a relative HOME or BASE/repo elsewhere SESSION_LAYOUT;
    a clean checkout at the named commit prints CPSV-REPO and RUN go."""
    root = Path(tempfile.mkdtemp(prefix='safe06_', dir=WORK))
    repo = root / 'r'
    (repo / 'deploy/vm2').mkdir(parents=True)
    shutil.copy(os.path.join(VM2, 'session_start.sh'), repo / 'deploy/vm2/session_start.sh')
    (repo / 'f.txt').write_text('invented\n')
    g = ['git', '-C', str(repo), '-c', 'user.email=t@invalid', '-c', 'user.name=t']
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(g + ['add', '-A'], check=True)
    subprocess.run(g + ['commit', '-q', '-m', 'invented'], check=True)
    commit = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    home = root / 'h'
    (home / 'cps').mkdir(parents=True)
    os.symlink(repo, home / 'cps/repo')
    code, out = run_session_start(home, repo, commit)
    assert code == 0 and out[-1] == 'DO: RUN bash %s/cps/vm.sh go' % home and 'CPSV-REPO commit=' + commit in out, out
    code, out = run_session_start(home, repo, 'f' * 40)
    assert (code, out[-1]) == (3, 'DO: STOP SESSION_COMMIT_MISMATCH HANDBACK C'), out
    (repo / 'f.txt').write_text('changed\n')
    code, out = run_session_start(home, repo, commit)
    assert (code, out[-1]) == (3, 'DO: STOP SESSION_REPO_DIRTY HANDBACK C'), out
    os.rename(repo / '.git', repo / '.git_saved')
    (repo / '.git').write_text('gitdir: %s/missing\n' % root)
    code, out = run_session_start(home, repo, commit)
    assert (code, out[-2:]) == (3, ['CPSV series=none head=000000 kit=none at=000000-0000-000000 mode=setup '
                                    'state=STOP', 'DO: STOP SESSION_GIT_ERROR HANDBACK C']), out
    code, out = run_session_start(home, repo, commit, env_over={'HOME': 'relative'})
    assert (code, out[-1]) == (3, 'DO: STOP SESSION_LAYOUT HANDBACK C'), out
    shutil.rmtree(root)


def test_safe07_setup_runs_foreground_and_gate_uses_hold():
    """SAFE-07 under P5 FAIL: session_start.sh runs the setup in the foreground (no setsid, nohup, disown or bare &;
    lint L11 over the whole helper) and prints the RUNNING line first; the release gate needs p5_setup_seconds + 60
    within foreground_hold_seconds, and the hold within p5_foreground_hold_seconds."""
    import test_lints
    test_lints.t_l11_no_detached_process()
    sh = open(os.path.join(VM2, 'session_start.sh')).read()
    i, j = sh.index('CPSV-RUNNING kind=setup'), sh.index('setup_vm_user.sh')
    assert i < j and 'max=600' in sh
    V = tv()
    V.t_gate1_foreground_hold_gate()


def test_op04_placeholders_refused_state_unchanged():
    """OP-04: '{CONVERSATION_ID}', '<id>', 'CONV' (a pattern name), 'conversation' (a key name) and a README example
    are refused as attested values (VALUE_FORBIDDEN or VALUE_PLACEHOLDER), for every free-text pattern; through the cli
    the refusal leaves every cache file byte-identical (test_vio's refusal table)."""
    import fakes
    cfg = {'drive_id_re': N.DEFAULT_DRIVE_ID_RE, 'conversation_re': r'conv-[0-9a-f]{8}', 'case': 'c', 'home': '/h',
           'doc_samples': fakes.readme_samples() + ['conv-EXAMPLE']}
    for v in ('{CONVERSATION_ID}', '<id>', 'CONV', 'conversation', 'conv-EXAMPLE') + tuple(fakes.readme_samples()[:3]):
        for pat in ('CONV', 'MODEL', 'PLATFORM'):
            r = N.check_value('conversation', pat, v, cfg)
            assert r and r[0] in ('VALUE_FORBIDDEN', 'VALUE_PLACEHOLDER'), (v, pat, r)
    err, got = N.check_answers({'conversation': 'CONV', 'ended': 'YES'}, [('conversation', '{CONVERSATION_ID}'),
                                                                          ('ended', 'yes')], cfg, {})
    assert err and err[0] == 'VALUE_FORBIDDEN', err
    tv().t_cli_idle_reprint_and_refusals()


def test_op06_helper_never_needs_a_listing():
    """OP-06, by construction: the helper's only Drive reads are exact-name FIND (every copy), LIST <folder> NEWEST 10
    as a head hint (§X.8.4) and DOWNLOAD by id. FakeDrive offers the Dot no full listing, the grammar has no PREFIX
    form, and no shipped module prints one."""
    import fakes
    from cpsvm2.vio import drive
    assert not hasattr(fakes.FakeDrive, 'find_prefix')
    dot_side = {n for n in vars(fakes.FakeDrive) if not n.startswith('_')} - {'table', 'has', 'bytes_of', 'plant',
                                                                              'remove', 'listing', 'approve'}
    assert dot_side == {'upload', 'find', 'list_newest', 'download'}, dot_side
    h = 'CPSV series=D1 head=000001 kit=0123456789ab at=000001-0001-abcdef mode=drill state=HEAD'
    assert drive.check_grammar([h, 'LIST CPS/reports NEWEST 10', 'DO: RUN bash /x/vm.sh go']) is None
    for bad in ('FIND CPS/reports PREFIX CPSJ_D1_', 'LIST CPS/reports PREFIX CPSJ NEWEST 10', 'LIST CPS/reports'):
        assert drive.check_grammar([h, bad, 'DO: RUN bash /x/vm.sh go']) is not None, bad
    for dp, _, fns in os.walk(os.path.join(VM2, 'cpsvm2')):
        for n in fns:
            if n.endswith('.py'):
                assert 'PREFIX ' not in open(os.path.join(dp, n)).read(), n


def test_op09_selftest_worker_death_bounded():
    """OP-09: (a) a dead self-test runs again once, then SELFTEST_DIED (cli.foreground_check; the world run is
    test_resets test_selftest_died_retried_once_then_stops); (b) without a conversation list the plan asks OPENED
    before AWAIT; (c) everyday: the delivery question comes before any DELIVER to=user."""
    import inspect
    from cpsvm2 import cli
    src = inspect.getsource(cli.foreground_check)
    assert "fg.get('attempt') == 1" in src and "'SELFTEST_DIED'" in src
    T = tc()
    w = T.q_world(p1_conversation_list='no')
    T.drive(w, 'PREPARE_GENERATE')
    st = P.next_action(view(w.state, boot=w.boot))
    st2 = P.next_action(view(w.state, marks={st.mark: 'x'} if getattr(st, 'mark', None) else {}, boot=w.boot))
    acts = [x.do[0] if hasattr(x, 'do') else x.context.get('action') for x in (st, st2)]
    assert acts[0] == 'OPEN_CONVERSATION' and acts[1] == 'OPENED', acts
    T.test_everyday_delivery_rows()


def test_tst02_nothing_written_with_file_found_is_written():
    """TST-02: NOTHING_WRITTEN with a file found by the re-walk is forced FILES_FOUND: T47 (lost), never T44."""
    T = tc()
    w = T.q_world()
    T.drive(w, 'PREPARE_GENERATE')
    e, it = resolve(w, ans(files_found=True))
    assert (it['forced'], it['action']) == ('FILES_FOUND', 'FREEZE_LOST'), it
    bad = json.loads(json.dumps(e))
    bad['body']['resolutions'][0].update(forced=None, action='INTERRUPT')
    raises('T48', lambda: F.apply(w.state, bad))
    assert w.commit(e) == ['T42', 'T47']


def test_tst03_not_ended_is_written():
    """TST-03: ended=no is forced NOT_ENDED: T47 (lost), whatever the outcome."""
    T = tc()
    w = T.q_world()
    T.drive(w, 'PREPARE_GENERATE')
    for oc in ('NOTHING_WRITTEN', 'NO_CONVERSATION', 'UNSURE'):
        e, it = resolve(w, ans(ended=False, outcome=oc, list_shows_none=True))
        assert (it['forced'], it['action']) == ('NOT_ENDED', 'FREEZE_LOST'), (oc, it)
    assert w.commit(e) == ['T42', 'T47']


def test_tst04_md5_hidden_download_back_mismatch_is_fork():
    """TST-04 under P2: with md5 hidden every copy not known by id is downloaded back; a download with the same size
    and other bytes is FORK, a missing download DOWNLOAD_MISSING, and the downloads are deleted (test_vio)."""
    tv().t_commit_md5_hidden_download_back()
    tv().t_cli_md5_hidden_download_back()


def test_tst05_consumer_tree_sha_mismatch_chain_invalid():
    """TST-05: a STAGE whose consumed tree_sha256 differs from the archived one folds to no row (T25); the worker
    measures the tree (it never copies the archive's value): the world half is test_int07_output_changed_..."""
    T = tc()
    w = T.q_world()
    T.drive(w, 'PREPARE_GENERATE', 'AI')
    e = [m for m in CW.moves(w) if m[0] == 'FINISH'][0][1]()
    bad = json.loads(json.dumps(e))
    bad['body']['consumed'][0]['tree_sha256'] = CW.hx('other')
    try:
        F.apply(w.state, bad)
        raise AssertionError('a wrong consumed tree folded')
    except F.ChainInvalid:
        pass
    import inspect
    from cpsvm2 import worker
    src = inspect.getsource(worker.Chain.prologue)
    assert 'place.tree_sha(rows)' in src and "'AI_OUTPUT_CHANGED'" in src


def test_tst07_b_before_a_frozen_chain_invalid_and_runner_refuses():
    """TST-07: a new run of reader B before A's chain is frozen is T14 (no row); the plan proposes A first (the runner
    refuses it too: test_cps_job.py)."""
    T = tc()
    T.test_t10_reader_b_needs_a_frozen()
    w = T.q_world()
    st = P.next_action(view(w.state))
    assert type(st).__name__ == 'RunChain' and st.first == 'prepare' and st.run.startswith('A/'), st


def test_tst08_under_stage_direct():
    """TST-08: the reused Staging.under_stage (defence in depth for staged archive paths)."""
    from cpsvm2.vio.v1reuse import under_stage
    assert under_stage('/s/stage', 'a/b') and under_stage('/s/stage', 'a')
    for bad in ('../x', 'a/../../x', '/etc/passwd', '..', 'a/../../stage2/x'):
        assert not under_stage('/s/stage', bad), bad
    d = Path(tempfile.mkdtemp(prefix='tst08_', dir=WORK))
    (d / 'stage/sub').mkdir(parents=True)
    (d / 'outside').mkdir()
    os.symlink(d / 'outside', d / 'stage/lnk')                  # a link on the way leaves the stage
    assert under_stage(str(d / 'stage'), 'sub/x') and not under_stage(str(d / 'stage'), 'lnk/x')
    shutil.rmtree(d)


def test_tst09_no_catch_all_assertions():
    import test_lints
    test_lints.t_l7_no_or_in_exit_code_assertions()


def test_tst10_free_space_preflight():
    """TST-10: run_tests.py refuses with exit 2 and PREFLIGHT_FREE_SPACE when the work folder has under 1 GiB free."""
    import run_tests
    d = tempfile.mkdtemp(prefix='tst10_', dir=WORK)
    real = run_tests.shutil.disk_usage
    out = io.StringIO()
    try:
        run_tests.shutil.disk_usage = lambda p: real(p)._replace(free=(1 << 30) - 1)
        with contextlib.redirect_stdout(out):
            code = run_tests.main(['--work', d, '--only', 'none'])
    finally:
        run_tests.shutil.disk_usage = real
    assert code == 2 and out.getvalue().startswith('REFUSED PREFLIGHT_FREE_SPACE'), (code, out.getvalue())
    shutil.rmtree(d)


def test_kit1_release_swap_after_genesis_stops():
    """KIT-1: after GENESIS every entry carries the genesis release and kit (S5, RELEASE_NOT_ACCEPTED); a kit with
    another RELEASE.json needs a KIT_CHANGE: refused with a run in flight, a non-accepted release, or a config-only
    claim that is false (session.kit_change: the session stops before any commit)."""
    T = tc()
    w = T.q_world()
    T.test_fold_foreign_release_sha_chain_invalid()
    s = w.state
    hk = {'sha256': CW.KIT, 'members': CW.MEMBERS, 'config': {'gates': s['genesis']['gates'], 'series': 'Q1'},
          'release_sha256': CW.REL}
    other = [['RELEASE.json', CW.hx('r2')]] + CW.MEMBERS[1:]
    kit = {'sha256': CW.KIT2, 'members': other, 'config': dict(hk['config']), 'release_sha256': CW.REL2}
    assert SE.kit_change(s, kit, hk)[0] == 'RELEASE_NOT_ACCEPTED'
    T.drive(w, 'PREPARE_GENERATE')
    assert SE.kit_change(w.state, kit, hk)[0] == 'KIT_CHANGE_WITH_RUN_IN_FLIGHT'


def test_mk1_header_slip_in_one_copy_recovers():
    """MK-1 belongs to deploy/make_kit.py (not part of cps-vm-helper.v2, unchanged here); its A/B recovery tests run
    from the checkout: the damaged and the slipped header in one copy."""
    p = subprocess.run([sys.executable, '-I', '-B', os.path.join(REPO, 'deploy/test_make_kit.py'),
                        'MakeKitTest.test_damaged_header_line_in_one_copy',
                        'MakeKitTest.test_slipped_header_sha_in_one_copy'], cwd=WORK, capture_output=True, text=True,
                       timeout=600)
    assert p.returncode == 0 and 'Ran 2 tests' in p.stderr, p.stderr[-800:]


def test_mk2_duplicate_binary_names_refused():
    """MK-2 (open, outside the helper): deploy/make_kit.py pack is not changed by v2. v2's kit intake reads the kit zip
    through the reused kit_members, which refuses a zip with two members of one name (KIT_SUMS_MISMATCH); this test
    shows that side only."""
    import zipfile
    from cpsvm2.vio.v1compat import Halt
    from cpsvm2.vio.v1reuse import kit_members
    d = Path(tempfile.mkdtemp(prefix='mk2_', dir=WORK))
    z = d / 'k.zip'
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')                 # zipfile warns about the duplicate name it is asked to write
        with zipfile.ZipFile(z, 'w') as zf:
            zf.writestr('RELEASE.json', b'{}')
            zf.writestr('RELEASE.json', b'{"x": 1}')
            zf.writestr('SHA256SUMS', b'')
        try:
            kit_members(z)
            raise AssertionError('a kit with a duplicate member was accepted')
        except Halt as h:
            assert h.code.startswith('KIT_') or h.code.startswith('ARCHIVE_'), h.code
    shutil.rmtree(d)


def test_gate1_gates_checked_on_every_go():
    """GATE-1: the release gates (and genesis-gate equality) are checked before every plan step of every command, not
    only at the session; a gate that is open gives STOP RELEASE_GATE_OPEN (not sticky)."""
    import inspect
    from cpsvm2 import cli
    assert inspect.getsource(cli.plan_step).split('\n')[1].strip() == 'gates_check(env)'
    assert 'RELEASE_GATE_OPEN' in cli.NOT_STICKY
    tv().t_gate1_foreground_hold_gate()


def test_test1_kit_change_with_run_in_flight_stops():
    """TEST-1: a non-config kit while a run is in flight is KIT_CHANGE_WITH_RUN_IN_FLIGHT (session); a config-only kit
    is allowed; the fold refuses a KIT_CHANGE whose run_in_flight claim is false."""
    T = tc()
    w = T.q_world()
    T.drive(w, 'PREPARE_GENERATE')
    s = w.state
    hk = {'sha256': CW.KIT, 'members': CW.MEMBERS, 'config': {'gates': s['genesis']['gates'], 'series': 'Q1'},
          'release_sha256': CW.REL}
    other = CW.MEMBERS[:2] + [['tables/t.json', CW.hx('t2')]]
    assert SE.kit_change(s, dict(hk, sha256=CW.KIT2, members=other), hk)[0] == 'KIT_CHANGE_WITH_RUN_IN_FLIGHT'
    cfg_only = [CW.MEMBERS[0], ['VM_HELPER_CONFIG.json', CW.hx('c2')], CW.MEMBERS[2]]
    code, kc = SE.kit_change(s, dict(hk, sha256=CW.KIT2, members=cfg_only, config=dict(hk['config'],
                                                                                       clock_wait_max_seconds=9)), hk)
    assert code is None and kc['config_only'] and kc['run_in_flight']
    T.test_kit_change_rules()


# ---- design §E extras and kill tests named by the mutation set
def test_stale_at_refused():
    """§6.3: an --at that is not the printed block's is STALE_AT, for found and answer; nothing changes."""
    V = tv()
    w = V.World()
    code, a = w.cmd('go')
    snap = w.cache_bytes()
    for args in (('answer', '--at', '000001-0001-ffffff', 'case=case01'),
                 ('found', '--at', '000001-0002-000000', '--name', 'x', '--none')):
        code, out = w.cmd(*args)
        assert code == 4 and out[1] == 'REFUSED STALE_AT', out
        assert w.cache_bytes() == snap


def test_fork_at_restore_lagging_n_plus_1():
    """G3: N+1 that lags once is found by the second FIND (w_abs later) and moves the head; a lagging foreign copy of
    N+1 next to ours is FORK; a single absence is never accepted."""
    D = tc().Drive
    r = D('Q1', 6, lag={6: 1}).search(hint=5)
    assert (r['verdict'], r.get('seq')) == ('head', 6), r
    r = D('Q1', 6, lag={6: 1}, foreign=6).search(hint=5)
    assert r == {'verdict': 'stop', 'code': 'FORK'}, r


def test_rewalk_forces_written():
    """G6 (§8.6 step 3): the placement re-walk of the open role's output reports files_found, and files_found forces
    FILES_FOUND (TST-02) whatever the Dot answered."""
    import test_codes
    test_codes.WORK = WORK
    test_codes.test_rewalk_reports_a_file_not_in_the_snapshot()
    test_tst02_nothing_written_with_file_found_is_written()


def test_no_conversation_without_list_is_written():
    """§8.6, O58: without a conversation list, NO_CONVERSATION for a role never OPENED is forced NO_LIST (T47)."""
    T = tc()
    w = T.q_world(p1_conversation_list='no')
    T.drive(w, 'PREPARE_GENERATE')
    e, it = resolve(w, ans(outcome='NO_CONVERSATION'))
    assert (it['forced'], it['action']) == ('NO_LIST', 'FREEZE_LOST'), it


DIRECT = [test_f1_core_continued_v_is_t46, test_f2_second_start_only_after_no_conversation,
          test_f3_core_classify_reads_only_the_head, test_f6_every_block_has_exactly_one_terminal_action,
          test_f7_core_transcript_member_required, test_safe01_unsupported_entries_halt_nothing_deleted,
          test_safe02_case_id_refused_before_any_write, test_safe04_enospc_or_short_write_at_every_durable_write,
          test_safe05_trailing_newline_and_bad_id_refused, test_safe06_session_start_git_error_prints_stop_block,
          test_safe07_setup_runs_foreground_and_gate_uses_hold, test_op04_placeholders_refused_state_unchanged,
          test_op06_helper_never_needs_a_listing, test_op09_selftest_worker_death_bounded,
          test_tst02_nothing_written_with_file_found_is_written, test_tst03_not_ended_is_written,
          test_tst04_md5_hidden_download_back_mismatch_is_fork, test_tst05_consumer_tree_sha_mismatch_chain_invalid,
          test_tst07_b_before_a_frozen_chain_invalid_and_runner_refuses, test_tst08_under_stage_direct,
          test_tst09_no_catch_all_assertions, test_tst10_free_space_preflight, test_kit1_release_swap_after_genesis_stops,
          test_mk1_header_slip_in_one_copy_recovers, test_mk2_duplicate_binary_names_refused,
          test_gate1_gates_checked_on_every_go, test_test1_kit_change_with_run_in_flight_stops, test_stale_at_refused,
          test_fork_at_restore_lagging_n_plus_1, test_rewalk_forces_written,
          test_no_conversation_without_list_is_written]
DELEGATE = {'test_f4_outcomes_total_over_frozen_shapes': 'test_core_table',
            'test_tst01_second_start_same_attempt_chain_invalid': 'test_core_table',
            'test_f5_audit_planted_restore_unknown_to_final': 'test_maint',
            'test_flags1_wrong_shared_or_real_carrier_inconsistent': 'test_maint',
            'test_flags2_empty_carriers_distinct_per_reader': 'test_maint',
            'test_flags3_runner_failed_runs_get_empty_carriers': 'test_maint',
            'test_safe03_probe_p5_same_call_check_refused': 'test_probe_p5',
            'test_op05_probe_same_session_refused': 'test_probe_p5'}


# ================================================================ world scenarios (run by test_resets)
def _entries(w):
    """Every journal entry manifest on FakeDrive (first copy), by name."""
    from cpsvm2.vio import savepoint
    out = {}
    for n in w.head_entries():
        p = w.fixed / ('.e_' + n)
        p.write_bytes(w.drive.bytes_of(N.series_folder(w.series), n))
        try:
            out[n] = savepoint.read_entry(p)
        finally:
            os.unlink(p)
    return out


def _boots(w):
    return [b['boot'] for b in w.dot.blocks]


def x_f1(w, s):
    first = w.dot.blocks[0]['boot']
    st = w.state() or w.drive_state()
    R = st['runs']['A/9990101']
    m8 = N.run8('A/9990101')
    after = [e for e in w.dot.events if e[0] in ('OPEN', 'CONTINUE') and e[1] == 'V' and e[3] != first
             and (m8 in e[2] or '/A/9990101/' in e[2])]
    assert not after, 'F1: V of run A was opened or continued again after the reset: %s' % after
    assert 'VISUAL_QA_FAILED_BY_RESET' in R['flags'], R['flags']
    pair = [p for p in w.all_frozen()['outcomes']['pairs'] if p['run'] == 'A/9990101'][0]
    assert pair['visual'] == 'FAILED_BY_RESET', pair


def x_op01(w, s):
    opens = [e for e in w.dot.events if e[0] == 'OPEN' and e[1] == 'G' and '/A/9990101/' in e[2]]
    assert len(opens) == 1 and opens[0][3] != w.dot.blocks[0]['boot'], 'OP-01: G of run A opened %s' % opens


def x_f3(w, s):
    first = w.dot.blocks[0]['boot']
    st = w.state() or w.drive_state()
    A = st['runs']['A/9990101']
    fz = N.entry_name(w.series, A['frozen']['seq'])
    ids = {c['id'] for c in w.drive.folders[N.series_folder(w.series)][fz]}
    assert any(b != first and did in ids for b, did, _, _ in w.dot.downloads), \
        'F3: the B prepare after the reset did not fetch A\'s FROZEN entry'
    B = [R for R in st['runs'].values() if R['reader'] == 'B' and R['case'] == '9990101']
    assert len(B) == 1 and B[0]['status'] == 'FROZEN', [(R['key'], R['status']) for R in B]


def x_f7(w, s):
    es = _entries(w)
    rs = [e for e in es.values() if e['kind'] == 'RESTORE' and e['body']['resolutions']]
    assert rs and any(m[0].startswith('transcript/G1_1.') for m in rs[-1]['payload']['members']), \
        'F7: the exported transcript is not in the RESTORE entry'
    st = w.state() or w.drive_state()
    assert 'AI_OUTPUT_LOST' in st['runs']['A/9990101']['flags']


def x_f8(w, s):
    es = _entries(w)
    rb = [e for e in es.values() if e['kind'] == 'RESTORE' and e['body']['rebase']]
    assert rb and rb[0]['body']['rebase']['missing_parts'], 'F8: no rebase RESTORE'
    later = [e for e in es.values() if e['seq'] > rb[0]['seq'] and e['kind'] in ('STAGE', 'FROZEN')
             and e['body'].get('rebase')]
    assert later, 'F8: the next stage was not re-run bound to the rebase'


def x_op02(w, s):
    dropped = sorted(w.drive.drop)
    assert dropped and all(w.drive.uploads.get(k) == 3 for k in dropped), (dropped, w.drive.uploads)


def x_op03(w, s):
    allfz = [n for n in w.drive.uploads if '_ALLFZ01' in n]
    assert allfz and w.drive.uploads[allfz[0]] == 2, 'OP-03: ALL_FROZEN was not re-uploaded once: %s' % allfz
    fin = [e for e in _entries(w).values() if e['kind'] == 'FINAL'][0]
    p = [x for x in fin['parts'] if x['kind'] == 'ALLFZ'][0]
    cs = w.drive.folders[N.series_folder(w.series)][p['name']]
    assert cs and all(c['sha256'] == p['sha256'] for c in cs)


def _calls_by_name(w):
    ids = {c['id']: n for fo in w.drive.folders.values() for n, cs in fo.items() for c in cs}
    out = {}
    for i, (k, folder, x) in enumerate(w.drive.calls):
        n = ids.get(x, x) if k == 'DOWNLOAD' else x
        out.setdefault(n, []).append(k)
    return out


def x_op07(w, s):
    """§X.5.5 budget: a normal Q-rule run (prepare STAGE, AI-G, finish STAGE + p PNG parts, AI-V, FROZEN) costs
    15 + 3p Drive calls, at most 24 with p <= 3."""
    by = _calls_by_name(w)
    es = _entries(w)
    for key in ('A/9990101', 'B/9990101'):
        mine = [e for e in es.values() if e['kind'] in ('STAGE', 'AI', 'FROZEN') and e['body'].get('run') == key]
        names = [e['name'] for e in mine] + [p['name'] for e in mine for p in e['parts']]
        p = sum(1 for n in names if '_PNG' in n)
        calls = sum(len(by.get(n, [])) for n in names)
        assert len(mine) == 5 and calls == 15 + 3 * p, (key, len(mine), p, calls)   # <= 24 when p <= 3


def x_op07_restore(w, s):
    """§X.5.5: a restore with a Dot hint costs 13-20 Drive calls, counted from the reset to the RESTORE's own verify."""
    i0 = w.dot.reset_calls[0]
    names = [x for k, f, x in w.drive.calls[i0:] if k == 'UPLOAD' and x.endswith('.tgz')]
    rest = names[0]
    calls = w.drive.calls[i0:]
    ids = {c['id'] for c in w.drive.folders[N.series_folder(w.series)][rest]}
    last = max(i for i, c in enumerate(calls) if c[2] == rest or c[2] in ids)
    assert 13 <= last + 1 <= 20, 'OP-07: a restore with a hint took %d Drive calls' % (last + 1)


def x_op08(w, s):
    ups = {n: k for n, k in w.drive.uploads.items() if n.startswith('CPSJ_')}
    assert ups and all(k == 1 for k in ups.values()), {n: k for n, k in ups.items() if k != 1}


def x_halted(code):
    def f(w, s):
        es = _entries(w)
        h = [e for e in es.values() if e['kind'] == 'HALT']
        assert h and h[-1]['body']['code'] == code, [e['body'] for e in h]
        assert not [e for e in es.values() if e['seq'] > h[-1]['seq']], 'nothing is committed after the HALT'
    return f


WORLD = [
    dict(name='test_f1_wipe_after_v_r2_written_before_ai_v_r2_confirmed', cfg='DRI', target=('AI', 3), point='a',
         extra='x_f1'),
    dict(name='test_op01_start_on_drive_before_first_open', cfg='D', target=('STAGE', 1), point='a', extra='x_op01'),
    dict(name='test_f3_classify_reads_only_head_at_every_worker_point', cfg='D', target=('FROZEN', 3), point='a',
         seam=('runner_after', 'prepare', 'reset'), extra='x_f3'),
    dict(name='test_f7_written_lost_transcript_in_restore_entry', cfg='DV', target=('AI', 1), point='a',
         answer='written', extra='x_f7'),
    dict(name='test_f8_dead_commit_plus_next_stage', cfg='D', target=('STAGE', 2), point='d', vis='lose_part',
         extra='x_f8'),
    dict(name='test_op02_lost_restore_upload_three_tries_then_stop', cfg='D', target=('AI', 1), point='e',
         vis='drop_restore', stop='UPLOAD_FAILED', extra='x_op02'),
    dict(name='test_op03_truncated_all_frozen_part_reuploaded_before_handback_b', cfg='D', target=('FINAL', 1),
         point='d', vis='lose_allfz', extra='x_op03'),
    dict(name='test_op07_drive_calls_per_run_within_budget', cfg='D', target=None, point=None, extra='x_op07'),
    dict(name='test_op07_restore_calls_within_budget', cfg='D', target=('AI', 1), point='e', extra='x_op07_restore'),
    dict(name='test_op08_every_file_uploaded_once_when_drive_is_normal', cfg='D', target=None, point=None,
         extra='x_op08'),
    dict(name='test_tst06_prompt_changed_halts', cfg='D', target=('AI', 1), point='a', vis='change_prompt',
         stop='HALTED_PROMPT_CHANGED', extra='x_tst06'),
    dict(name='test_int07_output_changed_after_archive_halts_before_consumer', cfg='D', target=('AI', 1), point='a',
         vis='change_output', stop='HALTED_AI_OUTPUT_CHANGED', extra='x_int07'),
    dict(name='test_kit2_zip_route_rehashes_the_kit', cfg='X', target=None, point=None,
         special='test_kit2_zip_route_rehashes_the_kit'),
    dict(name='test_imp04_no_commit_file_stops', cfg='X', target=None, point=None,
         special='test_imp04_no_commit_file_stops'),
]
x_tst06 = x_halted('PROMPT_CHANGED')


def test_imp04_no_commit_file_stops(w):
    """IMP-04, README step 0: the Dot's notes are gone and CPS/VM2_RELEASE.md is not on Drive: the Dot stops with
    SESSION_NO_COMMIT (case C) and never guesses a commit; with the file it finds the commit (D_notes_none_step0)."""
    w.drive.folders[N.FOLDERS['static']].pop('VM2_RELEASE.md')
    code, lines = w.dot.reset(notes='none')
    assert (code, lines) == (3, ['DO: STOP SESSION_NO_COMMIT HANDBACK C']), (code, lines)
    assert not (w.base / 'repo').exists(), 'nothing was cloned'


def test_kit2_zip_route_rehashes_the_kit(w):
    """KIT-2: the hinted kit zip on Drive holds other bytes under its name (same size): the downloaded kit is hashed
    and does not start with the hinted kit12, so the session stops with KIT_NOT_VERIFIED before anything is read."""
    k = w.drive.folders[N.FOLDERS['setup']]
    c = k[[n for n in k if n.startswith('SESSION_KIT_')][0]][0]
    raw = w.drive.blobs[c['id']]
    w.drive.blobs[c['id']] = raw[:-1] + bytes([raw[-1] ^ 1])
    code, lines = w.dot.run(*w.start())
    assert lines[-1] == 'DO: STOP KIT_NOT_VERIFIED HANDBACK C', lines
    assert not (w.base / 'runtime/RELEASE.json').exists(), 'nothing of the kit was installed'
x_int07 = x_halted('AI_OUTPUT_CHANGED')


# ================================================================ entry point
def run(only=None, work=None):
    global WORK
    WORK = str(work or tempfile.mkdtemp(prefix='v1reg_'))
    os.makedirs(WORK, exist_ok=True)
    import seen
    seen.install()
    passed, failed = 0, []
    tests = list(DIRECT) + [('delegate', n, m) for n, m in DELEGATE.items()]
    for t in tests:
        name = t.__name__ if callable(t) else t[1]
        if only and name not in only and 'test_v1_regressions' not in only:
            continue
        try:
            if callable(t):
                t()
            else:
                mod = __import__(t[2])
                if t[2] in ('test_maint', 'test_probe_p5'):
                    mod.WORK = tempfile.mkdtemp(prefix=t[2] + '_', dir=WORK)
                fn = getattr(mod, name)
                fn()
            passed += 1
        except Exception as e:                                       # noqa: BLE001 - recorded per test
            failed.append({'test': name, 'error': '%s: %s' % (type(e).__name__, str(e)[:1200]),
                           'trace': traceback.format_exc()[-1500:]})
    seen.dump()
    ids = sorted(MAP)
    return {'name': 'test_v1_regressions', 'tests': passed + len(failed), 'passed': passed,
            'failed': [f['test'] for f in failed], 'detail': failed,
            'counts': {'v1_ids': len(ids), 'map': {k: list(MAP[k]) for k in ids},
                       'world_scenarios_in_test_resets': [x['name'] for x in WORLD]}}


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
