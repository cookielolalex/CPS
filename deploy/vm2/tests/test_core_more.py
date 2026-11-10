"""More core tests (§14.1): entry validation negatives, guard branches the table enumeration does not reach, and the
core rules that the v1 mutants M06, M08, M11, M18, M21, M26 and M35 test (tests/mutants.py). Stdlib only, no I/O.
Entry point: run(only=None)."""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import core_world as CW                                                      # noqa: E402
import test_core_table as TC                                                 # noqa: E402
from cpsvm2.core import entry as EN, fold as F, names as N, outcome as O, plan as P, session as SE  # noqa: E402
from cpsvm2.core.step import Place                                          # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def view(s, boot=None):
    return {'state': s, 'marks': {}, 'local': {'gates_ok': True}, 'now': CW.utc(CW.T0 + 10 ** 6),
            'boot_id': boot or CW.boot(9), 'base': CW.BASE, 'cfg': {'clear': None, 'transcript_ext': 'json'}}


def full(w):
    e = copy.deepcopy(w.entries[-1])
    e['state'] = w.state
    e['state_sha256'] = EN.state_sha256(w.state)
    return e


def problems(e, fn):
    x = copy.deepcopy(e)
    fn(x)
    return EN.validate_entry(x)


@test
def test_validate_entry_negatives():
    """Every §3.4/§3.5 structural rule of validate_entry rejects its own violation (SCHEMA_INVALID when read)."""
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH')
    e = full(w)
    assert EN.validate_entry(e) == [] and e['parts'], EN.validate_entry(e)
    assert EN.validate_entry([]) == ['not a dict']
    cases = [
        (lambda x: x.update(schema='x'), 'schema'), (lambda x: x.update(series='Z9'), 'series'),
        (lambda x: x.update(seq=0), 'seq'), (lambda x: x.update(name='CPSJ_Q1_000001.tgz'), 'name'),
        (lambda x: x.update(prev_sha256=None), 'prev_sha256'), (lambda x: x.update(kind='XX'), 'kind'),
        (lambda x: x.update(utc='yesterday'), 'utc'), (lambda x: x.update(uid='0'), 'uid/home'),
        (lambda x: x.update(kit_sha256='k'), 'kit_sha256'), (lambda x: x.update(helper={'version': 'x'}), 'helper'),
        (lambda x: x.update(cleared_local={'code': 'X'}), 'cleared_local'),
        (lambda x: x.update(confirms='x'), 'confirms'), (lambda x: x.update(confirms=['x']), 'confirms'),
        (lambda x: x['confirms'][0]['copies'].append({'id': 'i', 'md5': 'x', 'size': 1}), 'confirms copy'),
        (lambda x: x.update(parts='x'), 'parts'), (lambda x: x['parts'].append({'name': 'n'}), 'parts keys'),
        (lambda x: x['parts'][0].update(sha256='s'), 'part %s' % e['parts'][0]['name']),
        (lambda x: x.update(payload=[]), 'payload'),
        (lambda x: x['payload']['members'].append(['job/x', 'file', 0o644, -1, None]), 'payload member'),
        (lambda x: x['payload']['members'].reverse(), 'payload order'),
        (lambda x: x['body'].pop('run'), 'body: keys'), (lambda x: x['body'].update(run=5), 'body.run'),
        (lambda x: x['body']['commands'][0].update(result='MAYBE'), 'command: values'),
        (lambda x: x['body'].update(commands=[]), 'commands: empty'),
        (lambda x: x['body']['consumed'][0].update(attempt=0), 'consumed: values'),
        (lambda x: x['body']['start'].update(reason='WHY'), 'start: values'),
    ]
    for fn, want in cases:
        got = problems(e, fn)
        assert any(g == want or g.startswith(want) for g in got), (want, got)
    x = copy.deepcopy(e)
    p2 = dict(x['parts'][0], k=3, name=x['parts'][0]['name'].replace('PNG01', 'PNG03'))
    x['parts'] = [x['parts'][0], p2]
    assert 'parts PNG not contiguous' in EN.validate_entry(x), EN.validate_entry(x)
    assert EN.validate_body('NOPE', {}) == ['kind']


@test
def test_m08_diverged_restart_conflict_stops():
    """v1 M08 (WRAP_RESTART_AFTER_DIVERGED): A frozen restart-eligible with RESET_DIVERGED and no restart: B may not
    start while A's restart rule is open, STOP QUALIFICATION_DIVERGED_RESTART_CONFLICT."""
    R = TC.frozen_run('A/c', flags=['RESET_DIVERGED'])
    R['frozen']['restart_eligible'] = True
    s = TC.ostate([R], [['c', 1, None]])
    s.update(phase='OPEN', notify=None, current=None, genesis=dict(s['genesis'], gates=CW.GATES))
    st = P.next_action(view(s))
    assert type(st).__name__ == 'Stop' and st.code == 'QUALIFICATION_DIVERGED_RESTART_CONFLICT', st


@test
def test_m11_ai_entry_of_another_boot_refused():
    """v1 M11 (re-archiving a lost output): an AI entry folds only in the boot of the START (T37); after a reset the
    role is resolved by a RESTORE, never archived."""
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE')
    ai = [m for m in CW.moves(w) if m[0] == 'AI'][0][1]()
    F.apply(w.state, ai)
    late = copy.deepcopy(ai)
    late['boot_id'] = CW.boot(77)
    try:
        F.apply(w.state, late)
        raise AssertionError('an AI entry of another boot folded')
    except F.ChainInvalid:
        pass


@test
def test_m18_role_consumed_once():
    """v1 M18 (stage done): a consumed role is never consumed again (the fold's consumed check)."""
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE', 'AI')
    fin = [m for m in CW.moves(w) if m[0] == 'FINISH'][0][1]()
    again = copy.deepcopy(fin)
    w.commit(fin)
    R = w.state['runs']['A/case01']
    assert R['roles']['G1']['consumed']
    assert not F._consumed_ok(R, again['body'])


@test
def test_m21_frozen_without_required_flag_refused():
    """v1 M21/M05 (failed-by-reset flag): after the T46 RESTORE, a FROZEN that does not add VISUAL_QA_FAILED_BY_RESET
    (or adds another flag) is refused; the exact flag set is required (§4.6)."""
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH', 'AI', 'REVIEW_INCOMPLETE')
    op = CW.open_role(w.state)
    e = CW._restore(w, resolve=op, ans={'ended': True, 'files_found': False, 'transcript': 'not_available',
                                        'outcome': 'CONTINUED', 'list_shows_none': None})
    w.commit(e)
    fz = [m for m in CW.moves(w) if m[0].startswith('FREEZE_')][0][1]()
    assert fz['body']['flags_added'] == ['VISUAL_QA_FAILED_BY_RESET'], fz['body']['flags_added']
    for bad in ([], ['AI_OUTPUT_LOST'], ['VISUAL_QA_FAILED_BY_RESET', 'VISUAL_QA_FAILED_BY_RESET']):
        x = copy.deepcopy(fz)
        x['body']['flags_added'] = bad
        try:
            F.apply(w.state, x)
            raise AssertionError('FROZEN with flags %s folded' % bad)
        except F.ChainInvalid:
            pass
    w.commit(fz)


@test
def test_m26_visual_reviewer_replaced_once():
    """v1 M26 (reviewer replacement): V NOTHING_WRITTEN is REPLACE once (T45); the replacement's own NOTHING_WRITTEN
    is FREEZE_VISUAL_FAILED (O45)."""
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH')
    a = {'ended': True, 'files_found': False, 'transcript': 'exported', 'outcome': 'NOTHING_WRITTEN',
         'list_shows_none': False}
    e = CW._restore(w, resolve=CW.open_role(w.state), ans=a)
    assert e['body']['resolutions'][0]['action'] == 'REPLACE'
    w.commit(e)
    assert w.state['runs']['A/case01']['replacements'] == 1
    e2 = CW._restore(w, resolve=CW.open_role(w.state), ans=a)
    it = e2['body']['resolutions'][0]
    assert it['action'] == 'FREEZE_VISUAL_FAILED', it
    bad = copy.deepcopy(e2)
    bad['body']['resolutions'][0]['action'] = 'REPLACE'
    TC.raises('T48', lambda: F.apply(w.state, bad))


@test
def test_m35_resolved_role_not_resolved_again():
    """v1 M35 (contradicting an earlier classification): a role is resolved once; a RESTORE item for a RESOLVED role is
    T48 (resolution_action)."""
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE')
    op = CW.open_role(w.state)
    a = {'ended': True, 'files_found': False, 'transcript': 'exported', 'outcome': 'WRITTEN', 'list_shows_none': None}
    e = CW._restore(w, resolve=op, ans=a)
    item = copy.deepcopy(e['body']['resolutions'][0])
    w.commit(e)
    assert w.state['runs']['A/case01']['roles']['G1']['status'] == 'RESOLVED'
    assert F.resolution_action(w.state, item, True)[0] == 'T48'


@test
def test_m06_everyday_retry_once():
    """v1 M06 (JOB_START_RESTART_USED): everyday S/G NOTHING_WRITTEN with a transcript is EVERYDAY_RETRY at attempt 1
    and FREEZE_EXHAUSTED at attempt 2 (T44)."""
    TC.test_int13_everyday_second_nothing_written_only_restart_exhausted()


@test
def test_guard_branches():
    """Guards the enumeration reaches only through illegal entries: CONFIRMS_MISMATCH on a copy's md5 (S4), the fold's
    SCHEMA_INVALID for a broken entry, names' empty and non-str values, outcomes' unlogged pair."""
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH')
    nx = [m for m in CW.moves(w) if m[0] == 'AI'][0][1]()
    bad = copy.deepcopy(nx)
    if len(bad['confirms']) > 1 and bad['confirms'][1]['copies']:
        bad['confirms'][1]['copies'][0]['md5'] = 'e' * 32
        TC.raises('CONFIRMS_MISMATCH', lambda: F.apply(w.state, bad))
    bad = copy.deepcopy(nx)
    bad['schema'] = 'x'
    TC.raises('SCHEMA_INVALID', lambda: F.apply(w.state, bad))
    assert not N.fm(N.HEX64, None) and not N.fm(N.HEX64, 5)


def expect_ci(fn):
    try:
        fn()
    except F.ChainInvalid as c:
        return c.code
    raise AssertionError('no ChainInvalid')


@test
def test_fold_guard_false_branches():
    """The false branches of the shared guards (§4.3) with crafted inputs: _common_ok (rebase binding, rerun binding,
    a PNG reference to an earlier entry), start_problem/_t30, _virtual and the new-run rows T11/T12, T49, T41/T42
    (reprepare, delivery question), T01's genesis body rule, the fold's catch of a broken guard (SCHEMA_INVALID) and
    of two positive rows (AMBIGUOUS_ROWS)."""
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE', 'AI')
    s, R = w.state, w.state['runs']['A/case01']
    fin = [m for m in CW.moves(w) if m[0] == 'FINISH'][0][1]()
    c = {'Q': True, 'mode': s['mode'], 'gates': s['genesis']['gates']}
    bind = dict(R, rebase_bind={'head_seq': 5, 'base_seq': 3, 'bound': {}, 'list_shows_none': None})
    assert not F._common_ok(s, bind, fin)
    x = copy.deepcopy(fin)
    x['body']['rebase'] = {'head_seq': 6, 'base_seq': 3, 'bound': True, 'diverged': False}
    assert not F._common_ok(s, bind, x)
    x = copy.deepcopy(fin)
    x['body']['rerun'] = {'after_seq': 3, 'unbound': True}
    assert not F._common_ok(s, dict(R, rerun_expected={'seq': 4}), x)
    f1 = ['job/qa/visual_deliverable/p.png', 0o644, 10, 'a' * 64]
    x = copy.deepcopy(fin)
    x['parts'] = []
    x['body']['png'] = {'files': [f1], 'whole_sha256': None, 'parts_seq': 2}
    assert F._common_ok(s, dict(R, png={'parts_seq': 2, 'files': [f1]}), x)
    assert not F._common_ok(s, dict(R, png=None), x)
    st = fin['body']['start']
    x = copy.deepcopy(fin)
    x['body']['start']['role'] = 'S'
    assert F.start_problem(s, R, x) == 'T32'
    assert F._t30(s, R, fin, dict(st, start_no=2)) is False
    prep = w.entries[1]                                    # the STAGE that made run A (prepare)
    x = copy.deepcopy(prep)
    x['body']['run'] = 'A/other'
    assert F._virtual(w.entries and TC.q_world().state, x) is None
    assert F._new_run_progress(TC.q_world().state, x, c) == (None, None)
    assert F._virtual(s, prep) is None                     # the run exists already
    e_state = dict(s, mode='everyday')
    assert F._virtual(e_state, dict(prep, body=dict(prep['body'], new_run=dict(prep['body']['new_run'], case='zz'),
                                                    run=prep['body']['new_run']['tag'] + '/zz'))) is None
    jobs = [['c', 1, None]]
    st0 = TC.ostate([], jobs)
    st0.update(current=None, genesis=dict(st0['genesis'], gates=CW.GATES))

    def nr(tag, case='c', restart_of=None, kind='STAGE', subs=('prepare',)):
        return {'kind': kind, 'body': {'new_run': {'tag': tag, 'case': case, 'reader': F.reader_of(tag),
                                                   'job_dir': '/j', 'restart_of': restart_of},
                                       'run': tag + '/' + case, 'commands': [{'sub': x} for x in subs]}}
    assert F.g11(st0, nr('A-restart1', restart_of='A/c'), c) is False                       # no chain
    A = TC.frozen_run('A/c')
    st1 = dict(st0, runs={'A/c': A}, order=['A/c'])
    assert F.g11(st1, nr('A-restart1', restart_of='A/c'), c) is False                       # not restart-eligible
    A2 = TC.frozen_run('A/c')
    A2['frozen']['restart_eligible'] = True
    st2 = dict(st0, runs={'A/c': A2, 'B/c': TC.frozen_run('B/c')}, order=['A/c', 'B/c'])
    assert F.g11(st2, nr('A-restart1', restart_of='A/c'), c) is False                       # B already ran
    assert F.g12(st0, nr('NA-A', kind='FROZEN', subs=('nonattempt', 'verify-frozen')), c) is False   # not a NA job
    st3 = dict(st0, genesis=dict(st0['genesis'], jobs=[['c', 1, 'WHY']]))
    assert F.g12(st3, nr('NA-B', kind='FROZEN', subs=('nonattempt', 'verify-frozen')), c) is False   # NA-A first
    w2 = TC.q_world()
    TC.drive(w2, 'PREPARE_GENERATE', 'AI', 'FINISH')
    rb = CW._restore(copy.deepcopy(w2), rebase=True)
    c2 = {'Q': True, 'mode': w2.state['mode'], 'gates': w2.state['genesis']['gates']}
    x = copy.deepcopy(rb)
    x['body']['rebase']['head_seq'] = 99
    assert F.g49(w2.state, x, c2) is False
    x = copy.deepcopy(rb)
    x['body']['rebase']['list_shows_none'] = False
    assert F.g49(w2.state, x, c2) is False
    wg = CW.World('Q1', jobs=[['case01', 1, None]])
    g = CW.genesis(wg)
    g['body']['mode'] = 'everyday'
    assert expect_ci(lambda: F.apply(None, g)) == 'SCHEMA_INVALID'
    assert [r for r in F.TABLE if r.kind_of == 'negative'][0].guard(s, fin, c) is False
    real = F.TABLE
    try:
        def boom(*a):
            raise KeyError('x')
        F.TABLE = tuple(r._replace(guard=boom) if r.kind_of == 'positive' else r for r in real)
        assert expect_ci(lambda: F.apply(s, fin)) == 'SCHEMA_INVALID'
        F.TABLE = real + tuple(r for r in real if r.id == 'T20')
        assert expect_ci(lambda: F.apply(s, fin)) == 'AMBIGUOUS_ROWS'
    finally:
        F.TABLE = real


@test
def test_fold_restore_guard_branches():
    """T41/T42 false branches: a RESTORE with both reprepare and abandon, a reprepare where the plain row applies, a
    missing or wrong START for a SUPERSEDE, an everyday delivery question that is missing, and an item outcome that
    fits no row (T48)."""
    we = CW.World('E1')
    we.commit(CW.genesis(we))
    TC.drive(we, 'INPUTS')
    rp = [m for m in CW.moves(we) + CW.restore_variant_moves(we) if m[0] == 'RESTORE_REPREPARE'][0][1]()
    c = {'Q': False, 'mode': 'everyday', 'gates': we.state['genesis']['gates']}
    x = copy.deepcopy(rp)
    x['body']['abandon'] = {'run': x['body']['reprepare']['run']}
    assert F.g41(we.state, x, c) is False
    assert F.g42(we.state, rp, c) is False
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE')
    e = CW._restore(w, resolve=CW.open_role(w.state), ans={'ended': True, 'files_found': False,
                                                            'transcript': 'exported', 'outcome': 'NO_CONVERSATION',
                                                            'list_shows_none': True})
    for mut in (lambda b: b.update(start=None), lambda b: b['start'].update(utc='2026-01-01T00:00:00Z')):
        x = copy.deepcopy(e)
        mut(x['body'])
        expect_ci(lambda: F.apply(w.state, x))
    it = dict(e['body']['resolutions'][0], outcome='CONTINUED', forced=None)
    assert F.resolution_action(w.state, it, True)[0] == 'T48'
    wd = CW.World('E1')
    wd.commit(CW.genesis(wd))
    TC.drive(wd, 'INPUTS', 'PREPARE_E', 'AI', 'FINISH', 'AI', 'DELIVER_CHECK', 'DELIVERY')
    r = [m for m in CW.moves(wd) + CW.restore_variant_moves(wd) if m[0] == 'RESTORE'][0][1]()
    assert r['body']['delivery_question'] is not None
    x = copy.deepcopy(r)
    x['body']['delivery_question'] = None
    expect_ci(lambda: F.apply(wd.state, x))


@test
def test_plan_rows_not_in_the_table_tests():
    """next_action rows the table tests do not reach: S end keys, a pending freeze of a lost role, an open role of
    another run (UNCLASSIFIED), the V continuation (CONTINUE then the ended question), DELIVER_SENT's freeze, the
    owner notice, an unfinished wait (UNCLASSIFIED), and chain_next's X20 (no change, tree changed; an unknown
    verify-frozen result)."""
    assert P.end_keys({'role': 'S'}) == {'ended': 'YES', 'conversation': 'CONV', 'prompt_pasted': 'YES'}
    assert P.end_keys({'role': 'V'}) == {'ended': 'YES', 'conversation': 'CONV'}
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH', 'AI', 'REVIEW_INCOMPLETE')
    v = view(w.state, w.boot)
    st = P.next_action(v)
    assert st.do[0] == 'CONTINUE_CONVERSATION', st
    st2 = P.next_action(dict(v, marks={st.mark: 'x'}))
    assert type(st2).__name__ == 'Ask' and st2.keys == {'ended': 'YES'}, st2
    s = copy.deepcopy(w.state)
    s['current'] = None
    assert P.next_action(view(s, w.boot)).code == 'UNCLASSIFIED'
    w3 = TC.q_world()
    TC.drive(w3, 'PREPARE_GENERATE')
    e = CW._restore(w3, resolve=CW.open_role(w3.state), ans={'ended': False, 'files_found': False,
                                                              'transcript': 'not_available', 'outcome': 'WRITTEN',
                                                              'list_shows_none': None})
    w3.commit(e)
    pc = P.pending_chain(w3.state)
    assert pc[0] == 'freeze' and pc[1]['resolution']['action'] == 'FREEZE_LOST', pc
    w4 = TC.q_world()
    TC.drive(w4, 'PREPARE_GENERATE')
    m = P.mark_key('OPEN', 'A/case01', 'G1', CW.latest(w4.state['runs']['A/case01']['roles']['G1']))
    s4 = copy.deepcopy(w4.state)
    s4['runs']['A/case01']['roles']['G1']['status'] = 'OPENED'
    s4['runs']['A/case01']['roles']['G1']['opened'] = {'conversation': 'conv-00000001', 'utc': CW.utc(CW.T0)}
    v4 = view(s4, w4.boot)
    a = P.next_action(v4)
    assert a.do[0] == 'AWAIT_CONVERSATION'
    s5 = copy.deepcopy(w4.state)
    s5['runs']['A/case01']['roles']['G1']['status'] = 'OPENED'
    s5['runs']['A/case01']['roles']['G1']['opened'] = None
    assert m not in v4['marks']
    wd = CW.World('E1')
    wd.commit(CW.genesis(wd))
    TC.drive(wd, 'INPUTS', 'PREPARE_E', 'AI', 'FINISH', 'AI', 'DELIVER_CHECK', 'DELIVERY')
    R = wd.state['runs'][wd.state['current']]
    d = R['delivery']
    if d.get('prepared_seq') and not d['sent'] and d['resend_ok']:
        sm = P.sent_mark(R['key'], d['prepared_seq'], d)
        st = P.next_action(dict(view(wd.state, wd.boot), marks={sm: 'x'}))
        assert type(st).__name__ == 'RunChain' and st.first == 'freeze', st
    s6 = copy.deepcopy(wd.state)
    s6['notify'] = {'what': 'NOTIFY_OWNER', 'seq': 3, 'about': 'RUN'}
    assert P.next_action(view(s6, wd.boot)).context['action'] == 'NOTIFY_OWNER'
    s7 = copy.deepcopy(wd.state)
    s7['runs'][s7['current']]['status'] = 'INPUTS_DONE'
    assert P.next_action(view(s7, wd.boot)).code == 'UNCLASSIFIED'
    base = {'record_changed': False, 'ledger_changed': False, 'tree_changed': True, 'bound': None, 'codes': []}
    cn = {'n': 1, 'freeze_retries': 0, 'v_review_incomplete': 0, 'diverged': False}
    r = P.chain_next('finish', dict(base, result='REFUSED', next='SOME_REFUSAL'), cn, 'drill', None)
    assert (r['row'], r['code']) == ('X20', 'UNCLASSIFIED'), r
    r = P.chain_next('verify-frozen', dict(base, result='NEXT', next='SOMETHING_ELSE'), cn, 'drill', None)
    assert (r['row'], r['code']) == ('X20', 'UNCLASSIFIED'), r


@test
def test_session_branches():
    """session.py branches the session tests do not reach: rule_V's md5, download and sha results, a forked part
    name in absent_twice, kit_change's GATES_CHANGED and series change, classify's REBASE_LIMIT and C10, the head
    search's HEAD_UNSTABLE end, session_next's early phases, a HINT_AHEAD stop, the LIST step, the fresh PASS phase,
    the phase index and the work sha."""
    cp = [['I1', None, 10], ['I2', None, 10]]
    assert SE.rule_v([['I1', 'a' * 32, 10]], 10, 's', set(), {}, 'b' * 32) == ('bad', 'md5')
    assert SE.rule_v(cp, 10, 's', {'I1'}, {}) == ('download', [cp[1]])
    assert SE.rule_v(cp, 10, 's', {'I1'}, {'I2': ['t', 10]}) == ('bad', 'sha')
    assert SE.rule_v(cp, 10, 's', {'I1'}, {'I2': ['s', 10]}) == ('ok', None)
    lk = [{'name': 'p', 'result': 'present', 'copies': [['I1', None, 10]], 'utc': CW.utc(CW.T0)},
          {'name': 'p', 'result': 'present', 'copies': [['I2', None, 11]], 'utc': CW.utc(CW.T0)}]
    assert SE.absent_twice(['p'], lk, 60, CW.utc(CW.T0))[1] == {'p': 'fork'}
    w = TC.q_world()
    s = w.state
    hk = {'sha256': CW.KIT, 'members': CW.MEMBERS, 'config': {'gates': s['genesis']['gates'], 'series': 'Q1'},
          'release_sha256': CW.REL}
    other = [['RELEASE.json', CW.hx('r2')]] + CW.MEMBERS[1:]
    k2 = {'sha256': CW.KIT2, 'members': other, 'config': {'gates': {}, 'series': 'Q1'}, 'release_sha256': CW.REL}
    assert SE.kit_change(s, k2, hk)[0] == 'GATES_CHANGED'
    k3 = dict(k2, config={'gates': s['genesis']['gates'], 'series': 'Q2'})
    assert SE.kit_change(s, k3, hk)[0] == 'CONFIG_CHANGE_NOT_ALLOWED'
    TC.drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH')
    h = w.entries[-1]
    s2 = copy.deepcopy(w.state)
    st = h['body']['start']
    s2['runs'][h['body']['run']]['roles'][st['role'] + str(st['attempt'])]['supersedes'] = 1
    assert SE.classify(h, s2, [h['parts'][0]['name']], None, True, CW.GATES) == ('C5', {'stop': 'REBASE_LIMIT'})
    s3 = copy.deepcopy(w.state)
    s3['runs'][s3['current']]['status'] = 'FROZEN'
    for ro in s3['runs'][s3['current']]['roles'].values():
        ro['status'] = 'ARCHIVED'
    assert SE.classify(w.entries[0], s3, [], None, True, CW.GATES)[0] == 'C10'
    d = TC.Drive('Q1', 40, lag={k: 1 for k in range(2, 40, 3)})
    assert d.search(hint=None)['verdict'] in ('head', 'stop')
    for done in (['LAYOUT', 'SETUP'], ['LAYOUT', 'SETUP', 'KIT', 'CONFIG']):
        assert SE.session_next({'work': TC.work(done=done), 'series': 'Q1', 'gates': CW.GATES, 'clear': None,
                                'now': CW.utc(CW.T0), 'base': CW.BASE})[1] is None
    dd = TC.Drive('Q1', 3)
    dd.search(hint=3)
    ph, st = SE.session_next({'work': TC.work(hint={'seq': 9, 'kit': None}, lookups=dd.lookups), 'series': 'Q1',
                              'gates': CW.GATES, 'clear': None, 'now': CW.utc(dd.t + 999), 'base': CW.BASE})
    assert ph == 'HEAD'
    g = dict(CW.GATES, p2_newest_first='yes')
    ph, st = SE.session_next({'work': TC.work(), 'series': 'Q1', 'gates': g, 'clear': None, 'now': CW.utc(CW.T0),
                              'base': CW.BASE})
    assert ph == 'HEAD' and st.lists, st
    wk = TC.work(done=['LAYOUT', 'SETUP', 'KIT', 'CONFIG', 'FINGERPRINT'])
    for _ in range(3):
        ph, st = SE.session_next({'work': wk, 'series': 'Q1', 'gates': CW.GATES, 'clear': None,
                                  'now': CW.utc(CW.T0 + 1000), 'base': CW.BASE})
        if ph != 'HEAD':
            break
        wk['lookups'].append({'name': st.finds[0][2], 'result': 'absent', 'copies': [], 'utc': CW.utc(CW.T0)})
        wk['lookups'].append({'name': st.finds[0][2], 'result': 'absent', 'copies': [], 'utc': CW.utc(CW.T0 + 500)})
    assert (ph, st) == ('PASS', None), (ph, st)
    assert SE.phase_index('LAYOUT') == 0 and len(SE.work_sha({'a': 1})) == 64


@test
def test_names_and_outcome_branches():
    """utc_epoch of an impossible date, check_answers' value refusal, final_dispositions' unlogged pair."""
    assert N.utc_epoch('2026-02-30T00:00:00Z') is None and N.utc_epoch('x') is None
    cfg = {'drive_id_re': N.DEFAULT_DRIVE_ID_RE, 'conversation_re': r'conv-[0-9a-f]{8}', 'doc_samples': [],
           'home': '/h', 'case': 'c'}
    err, got = N.check_answers({'ended': 'YES'}, [('ended', 'no')], cfg, {})
    assert err and err[0] == 'VALUE_PATTERN' and got is None, err
    w = TC.q_world()
    o = O.outcomes(w.state)
    try:
        O.final_dispositions(o, {'outcomes_sha256': N.sha(N.cjson(o)), 'verdicts': [],
                                 'unlogged': [{'case': 'nope', 'reader': 'A'}]})
        raise AssertionError('an unlogged pair that is not in the outcomes was accepted')
    except O.OwnerChecksInvalid as x:
        assert x.code == 'OWNER_CHECKS_INVALID'


def hidden_drive(cw, wk, verified_sha=None, t=None, limit=200, stop_at=()):
    """session_next against the World's entries as the Drive in the md5-hidden mode (P2): FIND gives [id, None, size];
    a DOWNLOAD is answered as the glue does (rule V: the downloaded copy's sha256 into work.verified; copy 1 of the head
    becomes work.head). verified_sha(name) -> the sha256 the download had (default: the expected one)."""
    t = t or cw.t + 100
    names = {e['name']: e for e in cw.entries}
    for p in [p for e in cw.entries for p in e['parts']]:
        names[p['name']] = p
    for _ in range(limit):
        v = {'work': wk, 'series': cw.series, 'gates': dict(cw.gates, p2_md5_visible='no'), 'clear': None,
             'now': CW.utc(t), 'base': CW.BASE, 'transcript_ext': 'json'}
        ph, st = SE.session_next(v)
        if ph in stop_at:
            return ph, st, wk, t
        if isinstance(st, P.PrintBlock) and st.do[0] == 'WAIT':
            t += st.do[1]['seconds']
        elif isinstance(st, P.PrintBlock) and st.do[0] == 'ATTEST_FOUND':
            for f in st.finds:
                x = names.get(f[2])
                size = None if x is None else 1000 if 'parts' in x else x['bytes']
                cp = [] if x is None or f[2] in wk.get('_deleted', ()) else [['ID%020d' % len(wk['lookups']), None,
                                                                              size]]
                wk['lookups'].append({'name': f[2], 'result': 'present' if cp else 'absent', 'copies': cp,
                                      'utc': CW.utc(t)})
                if wk.get('committed'):
                    wk['lookups'][-1]['post'] = True
            t += 5
        elif isinstance(st, P.PrintBlock) and st.downloads:
            for folder, did, path in st.downloads:
                name = path.rsplit('/', 1)[1].rsplit('.', 1)[0]
                x = names[name]
                if name == cw.entries[-1]['name'] and not wk.get('head'):
                    wk['head'] = {'entry': dict(x, state=cw.state, state_sha256=EN.state_sha256(cw.state))}
                    break
                want = cw.entries[-1]['prev_sha256'] if 'parts' in x else x['sha256']
                if wk.get('committed') and name == N.entry_name(cw.series, cw.entries[-1]['seq'] + 1):
                    want = wk['committed']['sha256']
                got = verified_sha(name) if verified_sha else want
                wk.setdefault('verified', {})[did] = [got or want, 0]
        elif isinstance(st, P.PrintBlock) and st.do[0] in ('END_CONVERSATION', 'EXPORT_TRANSCRIPT'):
            wk['resolve']['end' if st.do[0] == 'END_CONVERSATION' else 'export'] = True
        elif isinstance(st, Place):
            if ph == 'RESOLVE_PLACE':
                wk['resolve'].update(placed=True, files_found=False)
            else:
                wk['placed'] = True
        elif isinstance(st, P.Ask) and st.context['action'] == 'RESTORE_ROLE':
            wk['resolve']['answers'] = {'ended': 'yes', 'outcome': 'NOTHING_WRITTEN', 'transcript': 'exported',
                                        'list_shows_none': 'no'}
        elif isinstance(st, P.Ask) and st.context['action'] == 'LIST_SHOWS_NONE':
            wk['list_shows_none'] = True
        else:
            return ph, st, wk, t
    raise AssertionError('no end')


@test
def test_session_md5_hidden_rule_v_paths():
    """§X.8.4 under P2 through session_next: the link N-1 downloaded and compared (LINK_MISMATCH on another sha), a
    head part downloaded (FORK on another sha, FORK on two sizes), the PASS and CLOCK phases of a restore, C10 as a
    committed HALT, and the step-6 re-check of a gallop-found Q head (WAIT, the RESTORE's copy downloaded, DONE, FORK
    on another sha)."""
    from cpsvm2.core.step import Halt as HaltStep
    cw = TC.q_world()
    TC.drive(cw, 'PREPARE_GENERATE', 'AI', 'FINISH')
    base = lambda: dict(TC.work(), kit=dict(TC.work()['kit'], config={'gates': cw.gates}))   # noqa: E731
    ph, st, wk, t = hidden_drive(cw, base())
    assert ph == 'COMMIT', (ph, st)
    pn = N.entry_name(cw.series, cw.state['seq'] - 1)
    ph, st, wk, t = hidden_drive(cw, base(), verified_sha=lambda n: 'b' * 64 if n == pn else None)
    assert (ph, st) == ('HEAD', Stop_('LINK_MISMATCH')), (ph, st)
    part = cw.entries[-1]['parts'][0]['name']
    ph, st, wk, t = hidden_drive(cw, base(), verified_sha=lambda n: 'c' * 64 if n == part else None)
    assert (ph, st) == ('HEAD', Stop_('FORK')), (ph, st)
    wk = base()
    wk['lookups'].append({'name': part, 'result': 'present', 'copies': [['IDX', None, 7]], 'utc': CW.utc(cw.t)})
    ph, st, wk, t = hidden_drive(cw, wk)
    assert (ph, st) == ('HEAD', Stop_('FORK')), (ph, st)
    wk = base()
    wk['done'] = [d for d in wk['done'] if d != 'PASS']
    ph, st, wk, t = hidden_drive(cw, wk)
    assert (ph, st) == ('PASS', None), (ph, st)
    wk = base()
    ph, st, wk, t = hidden_drive(cw, wk)
    wk['committed'] = {'seq': cw.state['seq'] + 1, 'md5': 'x' * 32, 'utc': CW.utc(t), 'bytes': 1000,
                       'sha256': 's' * 64, 'ids': []}
    nx = N.entry_name(cw.series, cw.state['seq'] + 1)
    cw.entries.append(dict(cw.entries[-1], name=nx, seq=cw.state['seq'] + 1, parts=[]))
    try:
        ph, st, wk2, t2 = hidden_drive(cw, json.loads(json.dumps(wk)), t=t + 1, stop_at=('RECHECK',))
        assert ph == 'RECHECK' and st.do[0] == 'WAIT', (ph, st)
        ph, st, wk2, t2 = hidden_drive(cw, json.loads(json.dumps(wk)), t=t + 10 ** 4)
        assert (ph, st) == ('DONE', None), (ph, st)
        ph, st, wk3, t3 = hidden_drive(cw, json.loads(json.dumps(wk)), t=t + 10 ** 4,
                                       verified_sha=lambda n: 'd' * 64 if n == nx else None)
        assert (ph, st) == ('RECHECK', Stop_('FORK')), (ph, st)
    finally:
        cw.entries.pop()
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE', 'AI')
    s3 = copy.deepcopy(w.state)
    s3['runs'][s3['current']]['status'] = 'FROZEN'
    for ro in s3['runs'][s3['current']]['roles'].values():
        ro['status'] = 'ARCHIVED'
    g1 = TC.q_world()
    g1.state = s3
    g1.entries = [g1.entries[0]]
    ph, st, wk, t = hidden_drive(g1, dict(TC.work(), kit=dict(TC.work()['kit'], config={'gates': g1.gates}),
                                          identity={'home': g1.entries[0]['home'], 'uid': g1.entries[0]['uid']}))
    assert ph == 'CLASSIFY' and isinstance(st, HaltStep) and st.code == 'UNCLASSIFIED', (ph, st)


def Stop_(code):
    from cpsvm2.core.step import Stop
    return Stop(code, 'C')


@test
def test_head_search_unstable_and_hint_ahead():
    """§8.4: a Drive whose entries keep appearing beyond each head found is HEAD_UNSTABLE after MAX_FLIPS gallops;
    a hint beyond the newest entry is HINT_AHEAD through session_next (C1)."""
    lookups, t = [], CW.T0
    for _ in range(400):
        r = SE.head_search('Q1', None, lookups, CW.GATES, CW.utc(t))
        if 'verdict' in r:
            break
        if r['need'] == 'wait':
            t += r['seconds']
            continue
        k = int(r['name'][-10:-4])
        cp = [['ID%06d' % k, 'a' * 32, 10]] if k % 2 == 1 and k < 99 else []
        lookups.append({'name': r['name'], 'result': 'present' if cp else 'absent', 'copies': cp, 'utc': CW.utc(t)})
        t += 5
    assert r == {'verdict': 'stop', 'code': 'HEAD_UNSTABLE'}, r
    cw = TC.q_world()
    ph, st, wk, t = hidden_drive(cw, dict(TC.work(hint={'seq': 9, 'kit': None}),
                                          kit=dict(TC.work()['kit'], config={'gates': cw.gates})))
    assert (ph, st) == ('HEAD', Stop_('HINT_AHEAD')), (ph, st)


@test
def test_more_guard_lines():
    """g42's everyday INPUTS refusal, utc_epoch of year 0, next_run's UNCLASSIFIED end, _open_role's UNCLASSIFIED for
    a STARTED role that claims an opening."""
    we = CW.World('E1')
    we.commit(CW.genesis(we))
    TC.drive(we, 'INPUTS')
    rp = [m for m in CW.moves(we) + CW.restore_variant_moves(we) if m[0] == 'RESTORE_REPREPARE'][0][1]()
    x = copy.deepcopy(rp)
    x['body']['reprepare'] = None
    assert F.g42(we.state, x, {'Q': False, 'mode': 'everyday', 'gates': we.state['genesis']['gates']}) is False
    assert N.utc_epoch('0000-01-01T00:00:00Z') is None
    A, B = dict(TC.frozen_run('A/c'), status='ACTIVE'), dict(TC.frozen_run('B/c'), status='ACTIVE')
    s = TC.ostate([A, B], [['c', 1, None]])
    s.update(phase='OPEN', notify=None, current=None, genesis=dict(s['genesis'], gates=CW.GATES))
    assert P.next_action(view(s)).code == 'UNCLASSIFIED'
    w = TC.q_world()
    TC.drive(w, 'PREPARE_GENERATE')
    s5 = copy.deepcopy(w.state)
    s5['runs']['A/case01']['roles']['G1']['opened'] = {'conversation': 'conv-00000001', 'utc': CW.utc(CW.T0)}
    assert P.next_action(view(s5, w.boot)).code == 'UNCLASSIFIED'


def run(only=None):
    passed, failed = 0, []
    for fn in TESTS:
        if only and fn.__name__ not in only:
            continue
        try:
            fn()
            passed += 1
        except Exception as x:                                            # noqa: BLE001 - the report names it
            import traceback
            failed.append({'test': fn.__name__, 'error': '%s: %s' % (type(x).__name__, str(x)[:600]),
                           'trace': traceback.format_exc()[-1200:]})
    return {'name': 'test_core_more', 'tests': passed + len(failed), 'passed': passed,
            'failed': [f['test'] for f in failed], 'detail': failed, 'counts': {}}


if __name__ == '__main__':
    r = run([a for a in sys.argv[1:] if not a.startswith('--')] or None)
    for f in r['detail']:
        print('FAILED', f['test'], f['error'])
        print(f['trace'])
    print(json.dumps({k: r[k] for k in ('tests', 'passed', 'failed')}))
    sys.exit(0 if not r['failed'] else 1)
