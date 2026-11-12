"""§14.1 / §4.8: the transition-table enumeration and the core unit tables (names, chain_next, next_action, head_search,
classify, session_next, outcomes, final_dispositions, the core import lint). Stdlib only, no runner, no I/O beyond
reading tests/table_golden.json (written only with --update-golden)."""
import ast
import copy
import json
import os
import random
import re
import signal
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import core_world as CW                                                      # noqa: E402
from cpsvm2.core import entry as EN, fold as F, names as N, outcome as O, plan as P, session as SE  # noqa: E402
from cpsvm2.core.step import Ask, Commit, Place, PrintBlock, Reupload, RunChain, Stop  # noqa: E402

GOLDEN = os.path.join(HERE, 'table_golden.json')
TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def raises(code, fn):
    try:
        fn()
    except F.ChainInvalid as c:
        assert c.code == code, 'expected %s, got %s' % (code, c.code)
        return
    raise AssertionError('expected ChainInvalid %s, nothing raised' % code)


def wcopy(w):
    """A copy of a core_world.World (JSON data cloned, the committed entries shared, the rng deep-copied): copy.deepcopy's cost without its
    generality, so the enumeration stays fast enough for the guard-mutant runs (D11b)."""
    c = object.__new__(type(w))
    c.__dict__ = {k: list(v) if k in ('entries', 'rows') else F.clone(v) if type(v) in (dict, list) else
                  copy.deepcopy(v) if k == 'rng' and v is not None else v for k, v in w.__dict__.items()}
    return c


def drive(w, *labels):
    """Commit, in order, the legal move whose label starts with each given label."""
    for lab in labels:
        mv = [m for m in CW.moves(w) + CW.restore_variant_moves(w) if m[0].startswith(lab)]
        assert mv, 'no move %s from %s; have %s' % (lab, akey(w.state), [m[0] for m in CW.moves(w)])
        w.commit(mv[0][1]())
    return w


# ============================================================ §4.8 enumeration
def akey(s):
    """The abstract state class of §4.8: phase x current run (status:next) x role status of S1, G1, G2, V1, V2,
    plus mode, notify and the three P1 gates (they change which rows are reachable)."""
    if s is None:
        return 'none'
    cur = s['current']
    R = s['runs'].get(cur) if cur else None
    if R is None:
        run = 'FROZEN' if any(x['status'] == 'FROZEN' for x in s['runs'].values()) else 'none'
    else:
        nx = R['next'] or 'NONE'
        run = '%s:%s' % (R['status'], 'STOP_X' if nx.startswith('STOP_') else nx)
    roles = ','.join(((R or {}).get('roles', {}).get(k) or {}).get('status', '-')[:4] for k in
                     ('S1', 'G1', 'G2', 'V1', 'V2'))
    g = s['genesis']['gates']
    gk = ''.join(g[k][0] for k in ('p1_conversation_list', 'p1_transcript_export', 'p1_end_after_reset'))
    extra = ('bind' if R and R['rebase_bind'] else '') + ('rerun' if R and R.get('rerun_expected') else '') \
        + ('final_ready' if F.final_ready(s) else '')
    return '|'.join([s['mode'][0], s['phase'], run, roles, (s['notify'] or {}).get('what') or '-', gk, extra])


GATE_SETS = [{'p1_conversation_list': a, 'p1_transcript_export': b, 'p1_end_after_reset': c}
             for a in ('yes',) for b in ('yes', 'no') for c in ('yes', 'no')]       # t01 requires the list (v2.1)


def reachable(depth=12):
    """Breadth-first search over generated entries (legal moves and every restore answer), one representative World
    per abstract class."""
    reps, frontier = {}, []
    for series in ('Q1', 'E1'):
        for g in GATE_SETS:
            w = CW.World(series, gates=g, jobs=[['case01', 1, None], ['case02', 2, 'NA_REASON']])
            w.commit(CW.genesis(w))
            frontier.append(w)
            reps.setdefault(akey(w.state), w)
    for labels in (('PREPARE_STOP', 'ACK'), ('PREPARE_STOP', 'ACK') * 4,
                   ('PREPARE_GENERATE', 'AI', 'FINISH', 'AI', 'REVIEW_INCOMPLETE', 'AI_CONT',
                                              'REVIEW_INCOMPLETE', 'AI_CONT')):
        w = CW.World('Q1', jobs=[['case01', 1, None]])
        w.commit(CW.genesis(w))
        drive(w, *labels)
        frontier.append(w)
        reps.setdefault(akey(w.state), w)
    for _ in range(depth):
        nxt = []
        for w in frontier:
            for lab, _th in CW.moves(w) + CW.restore_variant_moves(w):
                c = wcopy(w)
                th = dict(CW.moves(c) + CW.restore_variant_moves(c))[lab]
                try:
                    c.commit(th())
                except F.ChainInvalid as x:
                    raise AssertionError('legal %s refused %s at %s' % (lab, x.code, akey(w.state)))
                k = akey(c.state)
                if k not in reps:
                    reps[k] = c
                    nxt.append(c)
        frontier = nxt
    return reps


LEGAL_ROW = [('PREPARE', None), ('NA', 'T12'), ('INPUTS', 'T15'), ('SCOPE_FINISH', 'T20'), ('FINISH_STOP', 'T24'),
             ('FINISH', 'T20'), ('DELIVER_CHECK', 'T20'), ('INTERRUPT_IN_PLACE', 'T20'), ('REBASE_SAME', 'T20'),
             ('REVIEW_INCOMPLETE', 'T21'), ('REFUSED_HALT', 'T23'), ('AI_CONT', 'T38'),
             ('AI', 'T37'), ('RESTORE_REPREPARE', 'T41'), ('RESTORE_ABANDON', 'T41'), ('RESTORE', 'T42'),
             ('ACK', 'T52'), ('DELIVERY', 'T55'), ('HALT', 'T58'), ('CLEAR', 'T59'), ('FINAL', 'T62'), ('', 'T24')]


def legal_row(label, e):
    for pre, row in LEGAL_ROW:
        if label.startswith(pre):
            if row is None:
                tag = e['body']['new_run']['tag']
                return 'T13' if tag.startswith('E') else 'T11' if 'restart' in tag else 'T10'
            return row
    raise AssertionError(label)


def illegal_variants(w):
    """(label, entry, expected code before the series guards) for one state; each is illegal by construction."""
    s, out = w.state, []
    seq = s['seq']
    out.append(('GENESIS', _with_seq(CW.genesis(w), w), 'T02'))
    out.append(('INPUTS_BAD', w.entry('INPUTS', {'tag': 'E20260101T000000Z', 'case': 'x1', 'inputs': {},
                                                 'request_utc': CW.utc(w.t)}),
                'T16' if s['mode'] != 'everyday' or s['current'] or any(
                    R['tag'] == 'E20260101T000000Z' for R in s['runs'].values()) else None))
    run = s['current'] or 'A/case01'
    out.append(('AI_BAD', w.entry('AI', {'run': run, 'role': 'S', 'attempt': 7, 'revision': 1, 'start_no': 1,
                                         'start_boot_id': w.boot, 'ended': True, 'conversation': 'c',
                                         'attested': {'tools_present': {'source': 'inventory', 'sha256': CW.hx('i')}},
                                         'tree_sha256': CW.hx('t'), 'files': [], 'transcript': None,
                                         'final_message_sha256': CW.hx('fm')}), 'T39'))
    out.append(('ACK_BAD', w.entry('ACK', {'for_seq': seq + 50, 'what': 'NOTIFY_OWNER',
                                           'answer': {'notified': 'yes'}}), 'T53'))
    out.append(('DELIVERY_BAD', w.entry('DELIVERY', {'run': run, 'standard_sha256': CW.hx('wrong'),
                                                     'copy': {}, 'log': {}, 'profile_folder': 'p'},
                                        parts=[('DELIV', 1), ('DLOG', 1)]), 'T56'))
    out.append(('HALT_BAD', w.entry('HALT', {'code': 'UNCLASSIFIED', 'detail': {}, 'head_seq': seq + 5}), 'T60'))
    nk = CW.hx('kitX', seq)
    out.append(('CLEAR_BAD', w.entry('CLEAR', {'halt_seq': 999999, 'code': 'X', 'kit_sha256': nk,
                                               'kit_change': CW.kit_change(s, nk)}, kit=nk), 'T60'))
    if not CW._final_ready(s):
        out.append(('FINAL_BAD', w.entry('FINAL', {'all_frozen_sha256': CW.hx('a'), 'ledger_final_sha256': CW.hx('l'),
                                                   'runs': 0, 'outcomes_sha256': CW.hx('o')},
                                         parts=[('LEDGER', 1), ('ALLFZ', 1)]), 'T63'))
    tag = 'A' if s['mode'] != 'everyday' else 'E20000101T000000Z'
    nr = CW.new_run(tag, 'case02')
    out.append(('STAGE_NEWRUN_BAD', w.entry('STAGE', CW.stage_body(tag + '/case02', [CW.cmd('prepare', 'GENERATE')],
                                                                   'GENERATE', new_run=nr)), 'T14'))
    out.append(('STAGE_OTHER_RUN', w.entry('STAGE', CW.stage_body('B/zz9', [CW.cmd('finish', 'FREEZE')], 'FREEZE')),
                'T25'))
    if CW.open_role(s):
        out.append(('RESTORE_EMPTY', w.entry('RESTORE', CW.restore_body(w)), 'T50'))
    for lab, th in CW.moves(wcopy(w)):
        if lab in ('SCOPE_FINISH', 'FINISH', 'INTERRUPT_IN_PLACE') or lab.startswith('PREPARE_G'):
            e = th()
            e['body']['start']['reason'] = 'REPLACEMENT'
            out.append(('START_REASON_' + lab, e, 'T14' if e['body']['new_run'] else 'T32'))
    R = s['runs'].get(s['current']) if s['current'] else None
    V = CW.newest_v(R) if R else None
    if V and V['status'] == 'ARCHIVED' and V['review_incomplete'] == 2 and not V['consumed'] and not CW.open_role(s):
        b = CW.stage_body(R['key'], [CW.cmd('visual-record', 'REVIEW_INCOMPLETE', result='REFUSED')], 'VISUAL_REVIEW',
                          review_incomplete=True, refused='REVIEW_INCOMPLETE')
        if R.get('rerun_expected'):
            b['rerun'] = {'after_seq': R['rerun_expected']['seq'], 'unbound': True}
        out.append(('THIRD_REVIEW_INCOMPLETE', w.entry('STAGE', b, members=CW.ledger_members(seq + 1)), 'T22'))
    return out


def _with_seq(g, w):
    tmpl = w.entry('HALT', {'code': 'X', 'detail': {}, 'head_seq': 0})
    g.update(seq=tmpl['seq'], name=tmpl['name'], prev_sha256=tmpl['prev_sha256'], confirms=tmpl['confirms'])
    return g


def series_guard(s, kind):
    if kind == 'GENESIS':
        return 'T02'
    if s['phase'] == 'HALTED' and kind not in ('RESTORE', 'CLEAR'):
        return 'T04'
    if s['phase'] == 'FINAL':
        return 'T05'
    if kind in ('INPUTS', 'STAGE', 'FROZEN', 'DELIVERY', 'AI') and s['notify'] is not None:
        return 'T06'
    return None


def positive_count(s, e):
    c = {'Q': F.is_q(s), 'mode': s['mode'], 'gates': s['genesis']['gates']}
    try:
        F.structural(s, e)
    except F.ChainInvalid:
        return 0
    if series_guard(s, e['kind']):
        return 0
    return sum(1 for r in F.TABLE if r.kind_of == 'positive' and e['kind'] in r.kinds and r.guard(s, e, c))


def oracle_sub(s, it):
    R = s['runs'][it['run']]
    ro = R['roles'][it['role'] + str(it['attempt'])]
    if ro['status'] == 'CONTINUED':
        return 'T46'
    if it['forced'] or it['outcome'] in ('WRITTEN', 'UNSURE'):
        return 'T47'
    if it['outcome'] == 'NO_CONVERSATION':
        return 'T43'
    return 'T44' if ro['role'] in 'SG' else 'T45'


ENUM = {}


def enumeration():
    if ENUM:
        return ENUM
    reps = reachable()
    golden, hits, problems, ambiguous = {}, set(), [], 0
    for k in sorted(reps):
        w = reps[k]
        s = w.state
        cases = []
        for lab, th in CW.moves(wcopy(w)) + CW.restore_variant_moves(wcopy(w)):
            c = wcopy(w)
            e = dict(CW.moves(c) + CW.restore_variant_moves(c))[lab]()
            cases.append((lab, c, e, legal_row(lab, e)))
            if e['kind'] == 'RESTORE' and e['body']['resolutions']:
                bad = copy.deepcopy(e)
                it = bad['body']['resolutions'][0]
                it['action'] = 'FREEZE_LOST' if it['action'] != 'FREEZE_LOST' else 'INTERRUPT'
                cases.append((lab + '_WRONG_ACTION', c, bad, 'T48'))
        for lab, e, code in illegal_variants(wcopy(w)):
            if code is not None:
                cases.append((lab, w, e, series_guard(s, e['kind']) or code))
        for lab, cw_, e, want in cases:
            n = positive_count(cw_.state, e)
            ambiguous += n > 1
            try:
                st2, rows = F.apply_traced(cw_.state, e)
                got = rows[0]
                hits.update(rows)
                if e['kind'] == 'RESTORE' and e['body']['resolutions']:
                    sub = oracle_sub(cw_.state if not e['body']['rebase'] else st2, e['body']['resolutions'][0])
                    if sub not in rows:
                        problems.append('%s %s: sub %s not in %s' % (k, lab, sub, rows))
            except F.ChainInvalid as x:
                got = x.code
                hits.add(x.code)
            if got != want:
                problems.append('%s %s: want %s got %s' % (k, lab, want, got))
            res = got if not (e['kind'] == 'RESTORE' and got == 'T42') else '+'.join(rows)
            kinds = golden.setdefault(k, {})
            kinds[e['kind']] = sorted(set(kinds.get(e['kind'], [])) | {res})
    hits.update(F.apply_traced(None, CW.genesis(CW.World('Q1')))[1])    # T01
    for kind in ('STAGE', 'ACK', 'RESTORE', 'HALT'):                    # T03: any kind but GENESIS on None
        w = CW.World('Q1')
        try:
            F.apply(None, w.entry(kind, {}))
        except F.ChainInvalid as x:
            hits.add('T03' if x.code == 'SCHEMA_INVALID' else x.code)
    try:
        w = CW.World('Q1')
        e = w.entry('HALT', {'code': 'X', 'detail': {}, 'head_seq': 0}, boot_id='unknown-boot')
        F.apply(None, e)
    except F.ChainInvalid as x:
        hits.add(x.code)
    ENUM.update(reps=reps, golden=golden, hits=hits, problems=problems, ambiguous=ambiguous)
    return ENUM


@test
def test_enumeration_rows_match_spec():
    en = enumeration()
    assert len(en['reps']) > 200, len(en['reps'])
    assert not en['problems'], en['problems'][:10]


@test
def test_enumeration_no_two_positive_rows():
    assert enumeration()['ambiguous'] == 0


@test
def test_enumeration_every_row_hit():
    missing = sorted(set(F.ROWS) - enumeration()['hits'])
    assert not missing, missing


@test
def test_enumeration_golden():
    g = enumeration()['golden']
    if '--update-golden' in sys.argv:
        with open(GOLDEN, 'w') as f:
            f.write('{\n' + ',\n'.join('%s: %s' % (json.dumps(k), json.dumps(g[k], sort_keys=True, separators=(',', ':')))
                                      for k in sorted(g)) + '\n}\n')
    with open(GOLDEN) as f:
        old = json.load(f)
    diff = sorted(k for k in set(g) | set(old) if g.get(k) != old.get(k))
    assert len(g) > 600                         # 4 gate sets in v2.1 (the list gate is always yes)
    assert not diff, 'golden differs (%d): %s' % (len(diff), diff[:5])



# ============================================================ one-field perturbations (D11a, D11b)
PERTURB_GOLDEN = os.path.join(HERE, 'perturb_golden.json')
GUARD_GOLDEN = os.path.join(HERE, 'guard_golden.json')
CASES = []                                          # the perturbation cases (state, entry) of the last run
_SKIP_TOP = {'schema'}
_SKIP_STATE = {'schema', 'series', 'seq', 'files', 'boots'}


def _leaves(x, path=()):
    yield path, x
    if type(x) is dict:
        for k in sorted(x):
            yield from _leaves(x[k], path + (k,))
    elif type(x) is list:
        for i, v in enumerate(x):
            yield from _leaves(v, path + (i,))


def _key_of(path):
    return next((p for p in reversed(path) if isinstance(p, str)), '')


def _alts(v, pool):
    out = [not v] if isinstance(v, bool) else [v + 1, v - 1] if isinstance(v, int) else [v + 'x'] \
        if isinstance(v, str) else [[], v[:-1]] if isinstance(v, list) and v else [None] if isinstance(v, dict) else []
    for p in pool:
        if p != v and p not in out and len(out) < 4:
            out.append(p)
    return out


def _shape(x):
    """The state with every sha256 value replaced by 'H' (core_world draws some at random)."""
    if type(x) is dict:
        return {k: _shape(v) for k, v in x.items()}
    if type(x) is list:
        return [_shape(v) for v in x]
    return re.sub('[0-9a-f]{64}', 'H', x) if isinstance(x, str) else x


def _outcome(s, e):
    try:
        st, rows = F.apply_traced(s, e)
        return '+'.join(rows) + ':' + N.sha(N.cjson(_shape(st)))[:8]
    except F.ChainInvalid as x:
        return x.code


def perturbations():
    """Every legal move of the enumeration (up to 6 states per move label, one per restore variant) and GENESIS, each
    with every leaf of the entry (but its schema) changed once: to its negation, +-1, a suffix, empty, None, or up to three
    values the same key has in other moves. -> {case: {outcome: [changes]}}, outcome a row trace with the sha of the
    new state's shape or the ChainInvalid code. Every guard of the fold decides some field; a guard mutant changes an outcome."""
    reps, by = enumeration()['reps'], {}
    for k in sorted(reps):
        w = reps[k]
        for lab, th in CW.moves(wcopy(w)) + CW.restore_variant_moves(wcopy(w)):
            by.setdefault(lab, []).append((k, w))
    cases, pool = [], {}
    for lab in sorted(by):
        L = by[lab]
        n = 1 if lab.startswith('RESTORE_VARIANT_') else 6
        for k, w in L[::max(1, len(L) // n)][:n]:
            c = wcopy(w)
            e = dict(CW.moves(c) + CW.restore_variant_moves(c))[lab]()
            cases.append((k + ' ' + lab, c.state, e))
            for path, v in _leaves(e['body']):
                vals = pool.setdefault(_key_of(path), [])
                if path and v not in vals and len(vals) < 3 and len(json.dumps(v)) < 400:
                    vals.append(v)
    for series in ('Q1', 'E1'):                     # GENESIS on no state, for each gate set
        for g in GATE_SETS:
            gw = CW.World(series, gates=g, jobs=[['case01', 1, None], ['case02', 2, 'NA_REASON']])
            cases.append(('GENESIS %s %s' % (series, sorted(g.items())), None, CW.genesis(gw)))
    CASES[:] = [(k, F.clone(s), F.clone(e)) for k, s, e in cases]
    res = {}
    for lab in sorted(by):                          # each move's entry folded on the other states of its label and
        L = [x for ser in ('Q1', 'E1') for x in [y for y in by[lab] if y[1].series == ser][::3][:4]]  # series (the
        built = []                                  # chain fields restamped): the guards that read the state
        for k, w in L:
            c = wcopy(w)
            built.append((k, w, dict(CW.moves(c) + CW.restore_variant_moves(c))[lab]()))
        for k, w, e in built:
            for k2, w2, _ in built:
                if k2 != k and w2.series == w.series:
                    t = wcopy(w2).entry('HALT', {'code': 'X', 'detail': {}, 'head_seq': 0})   # w2's clock unmoved
                    e2 = dict(F.clone(e), **{f: t[f] for f in ('seq', 'name', 'prev_sha256', 'confirms', 'utc')})
                    for p in e2['parts']:
                        p['name'] = CW.part_name(e2['series'], e2['seq'], p['kind'], p['k'])
                    res.setdefault('X %s | %s | %s' % (lab, k, k2), {})[_outcome(w2.state, e2)] = ['cross']
        k, w, e = built[0]                          # the label's entry on states of the other series (the c['Q']
        other = [x for x in sorted(reps) if reps[x].series != w.series][::37][:4]    # and mode conjuncts)
        for k2 in other:
            w2 = reps[k2]
            t = wcopy(w2).entry('HALT', {'code': 'X', 'detail': {}, 'head_seq': 0})
            e2 = dict(F.clone(e), **{f: t[f] for f in ('series', 'seq', 'name', 'prev_sha256', 'confirms', 'utc')})
            for p in e2['parts']:
                p['name'] = CW.part_name(e2['series'], e2['seq'], p['kind'], p['k'])
            res.setdefault('Y %s | %s | %s' % (lab, k, k2), {})[_outcome(w2.state, e2)] = ['series']
    spool = {}                                      # the state's own leaves, changed once (the guards that read it)
    for w in reps.values():
        for path, v in _leaves(w.state):
            vals = spool.setdefault(_key_of(path), [])
            if path and v not in vals and len(vals) < 3 and len(json.dumps(v)) < 200:
                vals.append(v)
    seen_lab = set()
    for key, s, e in cases:
        lab = key.split(' ')[-1]
        if s is None or lab in seen_lab:
            continue
        seen_lab.add(lab)
        r = res.setdefault('S ' + key, {})
        for path, v in _leaves(s):
            if not path or path[0] in _SKIP_STATE or isinstance(v, (dict, list)) and path[0] != 'halt':
                continue
            for a in _alts(v, spool.get(_key_of(path), []))[:3]:
                s2 = F.clone(s)
                x = s2
                for q in path[:-1]:
                    x = x[q]
                x[path[-1]] = F.clone(a)
                r.setdefault(_outcome(s2, e), []).append('.'.join(map(str, path)) + '=' + re.sub(
                    '[0-9a-f]{64}', 'H', json.dumps(a))[:40])
    for key, s, e in cases:
        r = res.setdefault(key, {})
        for path, v in _leaves(e):
            if not path or path[0] in _SKIP_TOP or path == ('body',):
                continue
            for a in _alts(v, pool.get(_key_of(path), [])):
                e2 = F.clone(e)
                x = e2
                for p in path[:-1]:
                    x = x[p]
                x[path[-1]] = F.clone(a)
                r.setdefault(_outcome(s, e2), []).append('.'.join(map(str, path)) + '=' + re.sub(
                    '[0-9a-f]{64}', 'H', json.dumps(a))[:40])
    return res



def _rows_true(s, e, c):
    """The positive rows of e's kind whose guard holds on (s, e, c), each guard called directly ('!' when it raises)."""
    out = []
    for r in F.TABLE:
        if r.kind_of == 'positive' and e.get('kind') in r.kinds:
            try:
                if r.guard(s, e, c):
                    out.append(r.id)
            except Exception:                           # noqa: BLE001 - a raising guard is a recorded result
                out.append('!' + r.id)
    return ','.join(out)


def guard_grid(cases):
    """D11a: every row guard called directly on each perturbation case, with every leaf of the entry and of the state
    changed once (to None, and for a scalar to up to four other values) and with the context flipped (Q, mode): the guard's own decision, which the
    row dispatch can mask in the fold's outcome. -> {case: sha16}."""
    out, pool = {}, {}
    for _, s, e in cases:
        for path, v in list(_leaves(s or {})) + list(_leaves(e)):
            vals = pool.setdefault(_key_of(path), [])
            if path and v not in vals and len(vals) < 4 and len(json.dumps(v)) < 300:
                vals.append(v)
    for key, s, e in cases:
        if s is None:
            continue
        c = {'Q': F.is_q(s), 'mode': s['mode'], 'gates': s['genesis']['gates']}
        r = [_rows_true(s, e, c), _rows_true(s, e, dict(c, Q=not c['Q'])),
             _rows_true(s, e, dict(c, mode='everyday' if c['mode'] != 'everyday' else 'qualification'))]
        for tag, obj in (('e', e), ('s', s)):
            for path, v in _leaves(obj):
                if not path or path[0] in _SKIP_STATE | _SKIP_TOP:
                    continue
                alts = [None] if isinstance(v, (dict, list)) and v else _alts(v, pool.get(_key_of(path), []))
                for a in alts + ([None] if v is not None and None not in alts else []):
                    o = F.clone(obj)
                    x = o
                    for q in path[:-1]:
                        x = x[q]
                    x[path[-1]] = a
                    s2, e2 = (s, o) if tag == 'e' else (o, e)
                    try:
                        c2 = c if tag == 'e' else {'Q': F.is_q(s2), 'mode': s2['mode'], 'gates': s2['genesis']['gates']}
                    except Exception:                   # noqa: BLE001 - the fold builds c only from a whole state
                        continue
                    r.append(tag + '.'.join(map(str, path)) + '=' + _rows_true(s2, e2, c2))
        out[key] = N.sha(N.cjson(r))[:16]
    return out


@test
def test_guard_perturbations_golden():
    """D11a/D11b: the fold's outcome of every one-field change of a legal entry equals tests/perturb_golden.json (per
    case: the outcome counts and the sha256 of the full outcome map; written with --update-golden)."""
    got = {k: [N.sha(N.cjson(v))[:16], {o: len(c) for o, c in sorted(v.items())}] for k, v in perturbations().items()}
    if '--update-golden' in sys.argv:
        with open(PERTURB_GOLDEN, 'w') as f:
            f.write('{\n' + ',\n'.join('%s: %s' % (json.dumps(k), json.dumps(got[k], sort_keys=True, separators=(
                ',', ':'))) for k in sorted(got)) + '\n}\n')
    with open(PERTURB_GOLDEN) as f:
        old = json.load(f)
    diff = sorted(k for k in set(got) | set(old) if got.get(k) != old.get(k))
    assert len(got) > 200 and not diff, 'perturbations differ (%d): %s' % (len(diff), [
        (k, got.get(k, [0, {}])[1], old.get(k, [0, {}])[1]) for k in diff[:2]])



@test
def test_guard_rows_golden():
    """D11a/D11b: every row guard's own decision on the perturbation cases (guard_grid) equals tests/guard_golden.json
    (written with --update-golden)."""
    if not CASES:
        perturbations()
    got = guard_grid(CASES)
    if '--update-golden' in sys.argv:
        with open(GUARD_GOLDEN, 'w') as f:
            json.dump(got, f, indent=0, sort_keys=True)
            f.write('\n')
    with open(GUARD_GOLDEN) as f:
        old = json.load(f)
    diff = sorted(k for k in set(got) | set(old) if got.get(k) != old.get(k))
    assert len(got) > 80 and not diff, 'row guards differ (%d): %s' % (len(diff), diff[:3])


WITNESS_FILE = os.path.join(HERE, 'guard_witnesses.json')


@test
def test_d11_fold_guard_witnesses():
    """D11a: the direct cases of the fold guards that the broad goldens leave undecided. Each row of
    tests/guard_witnesses.json names a guard site, a perturbation case, one or two changes to its state ('s') or entry
    ('e'), and the fold's outcome there (a row trace with the new state's shape sha, or the ChainInvalid code); the
    site's mutant gives another outcome. Rows were found by a differential search and each was reviewed."""
    if not CASES:
        perturbations()
    by = {}
    for k, s, e in CASES:
        by.setdefault(k, (s, e))                       # a key can repeat: the first case, as the search took
    with open(WITNESS_FILE) as f:
        rows = json.load(f)
    bad = []
    for r in rows:
        s, e = (F.clone(x) for x in by[r['case']])
        R = s['runs'].get(e['body'].get('run') or s['current']) or {}
        val = {'{rec}': R.get('record_sha256'), '{led}': (s['ledger'] or {}).get('sha256'),    # values core_world
               '{rel}': s['genesis']['release_sha256'],                                         # draws per run
               '{epngfiles}': (e['body'].get('png') or {}).get('files')}
        for tag, path, a in r['changes']:
            a = {k: val.get(v, v) if isinstance(v, str) else v for k, v in a.items()} if isinstance(a, dict) \
                else val.get(a, a) if isinstance(a, str) else a
            x = s if tag == 's' else e
            for q in path[:-1]:
                x = x[q]
            x[path[-1]] = F.clone(a)
        got = _outcome(s, e)
        if got != r['outcome']:
            bad.append((r['site'], got, r['outcome']))
    assert len(rows) > 0 and not bad, bad[:5]

SESSION_GOLDEN = os.path.join(HERE, 'session_golden.json')


def _call(fn, *a):
    try:
        return _shape(json.loads(json.dumps(fn(*a), default=repr)))
    except Exception as x:                              # noqa: BLE001 - the exception class is the recorded result
        return 'raises ' + type(x).__name__


def session_grid():
    """D11a/D11b for core/session.py: the pure session functions over every enumerated state, with a grid of their
    arguments: classify (head with and without missing parts, a matching clear and none, kit config-only or not),
    _classify_rest, place_plan (every run, none, with and without rebase), restore_keys and build_item for every open
    role (files found or not, conversation known or not, every outcome and answer combination). -> {state: sha16}."""
    out = {}
    answers = [{'ended': en, 'transcript': tr, 'outcome': oc, 'list_shows_none': ls, 'conversation': cv}
               for en in ('yes', 'no') for tr in ('exported', 'not_available')
               for oc in ('NOTHING_WRITTEN', 'WRITTEN', 'UNSURE', 'NO_CONVERSATION') for ls in ('yes', 'no', None)
               for cv in ('conv-abcd1234', None)]
    for k in sorted(enumeration()['reps']):
        w = enumeration()['reps'][k]
        s, head = w.state, w.entries[-1]
        r = []
        h = s.get('halt') or {}
        for missing in ([], [p['name'] for p in head['parts']][:1]):
            for clear in (None, {'series': s['series'], 'seq': h.get('seq'), 'code': h.get('code')}):
                for kco in (True, False):
                    r.append(_call(SE.classify, head, s, missing, clear, kco, s['genesis']['gates']))
        r.append(_call(SE._classify_rest, s))
        for run in [None] + sorted(s['runs']):
            for rb in (False, True):
                r.append(_call(SE.place_plan, s, run, rb))
        for run, R in sorted(s['runs'].items()):
            for rkey, ro in sorted(R['roles'].items()):
                if ro['status'] not in F.OPEN:
                    continue
                for ff in (False, True):
                    for ck in (False, True):
                        r.append(_call(SE.restore_keys, s, run, rkey, ff, ck))
                    for a in answers:
                        r.append(_call(SE.build_item, s, run, rkey, a, ff))
        op = CW.open_role(s) if s['phase'] != 'FINAL' else None
        yn = {True: 'yes', False: 'no', None: None}
        for hint in (s['seq'], None):                          # the whole session (session_next) from this head
            for ff in (False, True) if op else (False,):
                a = CW.answer_variants(s, op[2])[0] if op else None
                ans = a and {'ended': yn[a['ended']], 'transcript': a['transcript'], 'outcome': a['outcome'],
                             'list_shows_none': yn[a['list_shows_none']]}
                cw = wcopy(w)
                wk = work(hint={'seq': hint, 'kit': None})
                wk['kit'] = dict(wk['kit'], config={'gates': cw.gates})
                try:
                    ph, st, wk = run_session(cw, wk, ans, files_found=ff)
                    r.append(_shape(json.loads(json.dumps([ph, repr(st), wk.get('resolve'), wk.get('placed')],
                                                          default=repr))))
                except Exception as x:                  # noqa: BLE001 - the exception class is the result
                    r.append('raises ' + type(x).__name__)
        out[k] = N.sha(N.cjson(r))[:16]
    return out


@test
def test_session_functions_golden():
    """D11a/D11b: the session functions' results over the enumeration equal tests/session_golden.json (written with
    --update-golden)."""
    got = session_grid()
    if '--update-golden' in sys.argv:
        with open(SESSION_GOLDEN, 'w') as f:
            json.dump(got, f, indent=0, sort_keys=True)
            f.write('\n')
    with open(SESSION_GOLDEN) as f:
        old = json.load(f)
    diff = sorted(k for k in set(got) | set(old) if got.get(k) != old.get(k))
    assert len(got) > 600 and not diff, 'session results differ (%d): %s' % (len(diff), diff[:3])

# ============================================================ explicit rows and spec-named core tests
def q_world(**g):
    w = CW.World('Q1', gates=g, jobs=[['case01', 1, None]])
    w.commit(CW.genesis(w))
    return w


@test
def test_t03_t02_and_genesis():
    w = CW.World('Q1')
    raises('T03', lambda: F.apply(None, w.entry('HALT', {'code': 'X', 'detail': {}, 'head_seq': 0})))
    w.commit(CW.genesis(w))
    raises('T02', lambda: F.apply(w.state, _with_seq(CW.genesis(w), w)))
    assert w.state['phase'] == 'OPEN' and w.state['ledger']['seq'] == 1


@test
def test_structural_codes():
    w = q_world()
    e = w.entry('HALT', {'code': 'X', 'detail': {}, 'head_seq': 1})
    for mut, code in ((lambda x: x.update(seq=3, name=N.entry_name('Q1', 3)), 'SEQ_GAP'),
                      (lambda x: x.update(series='Q2', name=N.entry_name('Q2', 2)), 'SERIES_MISMATCH'),
                      (lambda x: x['confirms'][0].update(copies=[]), 'CONFIRMS_MISMATCH'),
                      (lambda x: x['confirms'].append({'name': 'n', 'copies': []}), 'CONFIRMS_MISMATCH'),
                      (lambda x: x.update(release_sha256=CW.hx('foreign')), 'RELEASE_NOT_ACCEPTED'),
                      (lambda x: x.update(kit_sha256=CW.hx('foreign kit')), 'RELEASE_NOT_ACCEPTED'),
                      (lambda x: x['body'].pop('detail'), 'SCHEMA_INVALID'),
                      (lambda x: x.update(boot_id='unknown-boot', kind='ACK',
                                          body={'for_seq': 1, 'what': 'NOTIFY_OWNER', 'answer': {}}), 'SCHEMA_INVALID')):
        x = copy.deepcopy(e)
        mut(x)
        raises(code, lambda: F.apply(w.state, x))
    x = copy.deepcopy(e)
    x['helper']['version'] = 'cps-vm-helper.v1'
    raises('HELPER_UNKNOWN', lambda: F.apply(w.state, x))
    x = copy.deepcopy(e)
    x['runner_sha256'] = CW.hx('other runner')
    raises('HELPER_UNKNOWN', lambda: F.apply(w.state, x))
    assert EN.validate_entry(dict(x, state=w.state, state_sha256=EN.state_sha256(w.state)))


@test
def test_fold_foreign_release_sha_chain_invalid():
    """G12 (IMP-16): a crafted entry with a foreign release_sha256 folded directly."""
    w = q_world()
    drive(w, 'PREPARE_GENERATE')
    e = w.entry('HALT', {'code': 'X', 'detail': {}, 'head_seq': w.state['seq']}, release=CW.hx('foreign'))
    raises('RELEASE_NOT_ACCEPTED', lambda: F.apply(w.state, e))
    r = CW._restore(w)
    r['release_sha256'] = CW.REL2
    raises('RELEASE_NOT_ACCEPTED', lambda: F.apply(w.state, r))


@test
def test_series_guards_t04_t05_t06():
    w = q_world()
    drive(w, 'HALT')
    raises('T04', lambda: F.apply(w.state, w.entry('ACK', {'for_seq': 1, 'what': 'NOTIFY_OWNER',
                                                         'answer': {'notified': 'yes'}})))
    drive(w, 'CLEAR', 'PREPARE_STOP')
    assert w.state['notify']['what'] == 'NOTIFY_OWNER'
    raises('T06', lambda: F.apply(w.state, w.entry('INPUTS', {'tag': 'E20260101T000000Z', 'case': 'x',
                                                            'inputs': {}, 'request_utc': CW.utc(w.t)})))


@test
def test_imp08_restore_at_final_is_t05():
    w = CW.World('Q1', jobs=[['c1', 1, 'NA']])
    w.commit(CW.genesis(w))
    drive(w, 'NA', 'NA', 'FINAL')
    assert w.state['phase'] == 'FINAL'
    raises('T05', lambda: F.apply(w.state, CW._restore(w)))
    raises('T05', lambda: F.apply(w.state, w.entry('FINAL', {'all_frozen_sha256': CW.hx('a'),
                                                          'ledger_final_sha256': CW.hx('l'), 'runs': 2,
                                                          'outcomes_sha256': CW.hx('o')},
                                                  parts=[('LEDGER', 1), ('ALLFZ', 1)])))


@test
def test_tst01_second_start_same_attempt_chain_invalid():
    w = q_world()
    drive(w, 'PREPARE_SCOPE', 'AI')
    e = [m for m in CW.moves(w) if m[0] == 'SCOPE_FINISH'][0][1]()
    e['body']['start']['attempt'] = 1
    e['body']['start']['role'] = 'G'
    ok = copy.deepcopy(e)
    F.apply(w.state, ok)
    for reason in ('NO_CONVERSATION', 'REPLACEMENT', 'EVERYDAY_RETRY'):
        x = copy.deepcopy(e)
        x['body']['start']['reason'] = reason
        raises('T32', lambda: F.apply(w.state, x))
    w.commit(e)
    drive(w, 'AI', 'FINISH')                       # G1 consumed, V1 started
    x = [m for m in CW.moves(w) if m[0] == 'AI'][0][1]()
    w.commit(x)
    e2 = [m for m in CW.moves(w) if m[0] == 'REVIEW_INCOMPLETE'][0][1]()
    e2['body']['next'], e2['body']['review_incomplete'], e2['body']['refused'] = 'GENERATE', False, None
    e2['body']['start'] = dict(CW.start('/j', 'G', 1, 1, 'STAGE'), utc=e2['utc'], boot_id=e2['boot_id'])
    raises('T32', lambda: F.apply(w.state, e2))    # G attempt 1 exists: a second START for it


@test
def test_t43_supersede_once_then_written():
    w = q_world()
    drive(w, 'PREPARE_GENERATE')
    op = CW.open_role(w.state)
    a = {'ended': True, 'files_found': False, 'transcript': 'exported', 'outcome': 'NO_CONVERSATION',
         'list_shows_none': True}
    e = CW._restore(w, resolve=op, ans=a)
    assert e['body']['resolutions'][0]['action'] == 'SUPERSEDE'
    assert w.commit(e) == ['T42', 'T43']
    ro = w.state['runs']['A/case01']['roles']['G1']
    assert ro['supersedes'] == 1 and ro['status'] == 'STARTED' and 'START_SUPERSEDED' in w.state['runs'][
        'A/case01']['flags']
    e = CW._restore(w, resolve=CW.open_role(w.state), ans=a)
    assert e['body']['resolutions'][0]['forced'] == 'NO_CONVERSATION_NOT_ALLOWED'
    assert w.commit(e) == ['T42', 'T47']


@test
def test_int02_v_nothing_written_not_available_without_owner_check_chain_invalid():
    w = q_world()
    drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH')
    op = CW.open_role(w.state)
    a = {'ended': True, 'files_found': False, 'transcript': 'not_available', 'outcome': 'NOTHING_WRITTEN',
         'list_shows_none': False}
    e = CW._restore(w, resolve=op, ans=a)
    it = e['body']['resolutions'][0]
    assert (it['action'], it['owner_check']) == ('REPLACE', True)
    bad = copy.deepcopy(e)
    bad['body']['resolutions'][0]['owner_check'] = False
    raises('T48', lambda: F.apply(w.state, bad))
    assert w.commit(e) == ['T42', 'T45']
    R = w.state['runs']['A/case01']
    assert 'OWNER_CHECK' in R['flags'] and R['replacements'] == 1 and R['roles']['V2']['status'] == 'STARTED'


@test
def test_int02_v_not_available_everyday_freezes_visual():
    w = CW.World('E1')
    w.commit(CW.genesis(w))
    drive(w, 'INPUTS', 'PREPARE_E', 'AI', 'FINISH')
    a = {'ended': True, 'files_found': False, 'transcript': 'not_available', 'outcome': 'NOTHING_WRITTEN',
         'list_shows_none': False}
    e = CW._restore(w, resolve=CW.open_role(w.state), ans=a)
    assert e['body']['resolutions'][0]['action'] == 'FREEZE_VISUAL_FAILED'
    w.commit(e)
    drive(w, 'FREEZE_FREEZE_VISUAL_FAILED')
    R = [x for x in w.state['runs'].values()][0]
    assert R['frozen']['visual'] == 'FAILED_BY_RESET' and w.state['notify']['what'] == 'ASK_USER'


@test
def test_int13_everyday_second_nothing_written_only_restart_exhausted():
    w = CW.World('E1')
    w.commit(CW.genesis(w))
    drive(w, 'INPUTS', 'PREPARE_E')
    a = {'ended': True, 'files_found': False, 'transcript': 'exported', 'outcome': 'NOTHING_WRITTEN',
         'list_shows_none': False}
    e = CW._restore(w, resolve=CW.open_role(w.state), ans=a)
    assert e['body']['resolutions'][0]['action'] == 'EVERYDAY_RETRY' and e['body']['start']['attempt'] == 2
    w.commit(e)
    e = CW._restore(w, resolve=CW.open_role(w.state), ans=a)
    assert e['body']['resolutions'][0]['action'] == 'FREEZE_EXHAUSTED'
    w.commit(e)
    fz = [m for m in CW.moves(w) if m[0].startswith('FREEZE')][0][1]()
    assert fz['body']['flags_added'] == ['RESTART_EXHAUSTED_BY_RESET']
    for flags in (['RESTART_EXHAUSTED_BY_RESET', 'AI_OUTPUT_LOST'], ['AI_OUTPUT_LOST'], []):
        x = copy.deepcopy(fz)
        x['body']['flags_added'] = flags
        raises('T25', lambda: F.apply(w.state, x))
    w.commit(fz)


@test
def test_imp06_restart_run_frozen_at_prepare_stop_reaches_final():
    w = q_world()
    drive(w, 'PREPARE_STOP')                         # A frozen at STOP, restart-eligible
    assert w.state['runs']['A/case01']['frozen']['restart_eligible']
    drive(w, 'ACK')
    labels = [m[0] for m in CW.moves(w)]
    assert 'FINAL' not in labels                     # a restart is owed (T62)
    e = [m for m in CW.moves(w) if m[0] == 'PREPARE_STOP_SOURCE_UNREADABLE'][0][1]()
    assert e['body']['new_run']['tag'] == 'A-restart1'
    bad = copy.deepcopy(e)
    bad['body']['restart_eligible'] = True
    raises('T14', lambda: F.apply(w.state, bad))    # a restart run is never restart-eligible (T24, IMP-06)
    e['body']['restart_eligible'] = False
    assert w.commit(e)[0] == 'T11'
    drive(w, 'ACK', 'PREPARE_STOP', 'ACK', 'PREPARE_STOP', 'ACK', 'FINAL')
    assert w.state['phase'] == 'FINAL'


@test
def test_t10_reader_b_needs_a_frozen():
    w = q_world()
    e = w.entry('STAGE', CW.stage_body('B/case01', [CW.cmd('prepare', 'GENERATE')], 'GENERATE',
                                      new_run=CW.new_run('B', 'case01'),
                                      start=CW.start('/j', 'G', 1, 1, 'STAGE')))
    raises('T14', lambda: F.apply(w.state, e))      # I3, TST-07


@test
def test_t21_t22_review_incomplete_limit():
    w = q_world()
    drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH', 'AI', 'REVIEW_INCOMPLETE', 'AI_CONT', 'REVIEW_INCOMPLETE', 'AI_CONT')
    V = w.state['runs']['A/case01']['roles']['V1']
    assert V['review_incomplete'] == 2 and V['status'] == 'ARCHIVED'
    a = V['archives'][-1]                              # the consumed V names the archive, as the third refusal would
    x = w.entry('STAGE', CW.stage_body('A/case01', [CW.cmd('visual-record', 'REVIEW_INCOMPLETE', result='REFUSED')],
                                      'VISUAL_REVIEW', review_incomplete=True, refused='REVIEW_INCOMPLETE',
                                      consumed=[{'role': 'V', 'attempt': 1, 'revision': a['revision'],
                                                 'tree_sha256': a['tree_sha256']}]),
                members=CW.ledger_members(w.state['seq'] + 1))
    R = w.state['runs']['A/case01']
    assert F._consumed_ok(R, x['body']) and F._common_ok(w.state, R, x)        # only the limit decides (M2-23)
    raises('T22', lambda: F.apply(w.state, x))
    drive(w, 'REVIEW_LIMIT')
    R = w.state['runs']['A/case01']
    assert 'REVIEW_INCOMPLETE_LIMIT' in R['flags'] and R['frozen']['visual'] == 'REVIEW_INCOMPLETE_LIMIT'


def _rebase_world():
    w = q_world()
    drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH')    # head: finish STAGE with START V and two PNG parts
    return w


@test
def test_int04_rebase_restore_over_finish_stage_folds():
    w = _rebase_world()
    e = CW._restore(w, rebase=True)
    assert [c['copies'] for c in e['confirms'] if c['name'].endswith('PNG01.part')] == [[]]
    st, rows = F.apply_traced(w.state, e)
    assert rows == ['T42', 'T49'], rows
    R = st['runs']['A/case01']
    assert R['rebase_bind']['head_seq'] == w.state['seq'] and 'V1' not in R['roles']
    assert R['roles']['G1']['status'] == 'ARCHIVED' and not R['roles']['G1']['consumed']
    w.commit(e)
    rows = drive(w, 'REBASE_SAME').rows[-1]
    assert rows == ['T20', 'T31'], rows
    R = w.state['runs']['A/case01']
    assert [s['reason'] for s in R['roles']['V1']['starts']] == ['STAGE', 'REBASE'] and 'REBASED' in R['flags']
    assert R['rebases'][-1]['diverged'] is False and R['rebase_bind'] is None


@test
def test_int04_rebase_missing_part_not_declared_confirms_mismatch():
    w = _rebase_world()
    e = CW._restore(w, rebase=True)
    e['body']['rebase']['missing_parts'] = [e['confirms'][2]['name']]          # the other part
    e['body']['rebase']['absence'][0]['name'] = e['confirms'][2]['name']
    raises('CONFIRMS_MISMATCH', lambda: F.apply(w.state, e))


@test
def test_int05_single_absence_window_not_enough_t50():
    w = _rebase_world()
    e = CW._restore(w, rebase=True)
    t = e['body']['rebase']['absence'][0]['utc']
    t[1] = CW.utc(N.utc_epoch(t[0]) + 10)
    raises('T50', lambda: F.apply(w.state, e))


@test
def test_rebase_diverged_flags_reset_diverged():
    w = _rebase_world()
    w.commit(CW._restore(w, rebase=True))
    drive(w, 'REBASE_DIVERGED')
    R = w.state['runs']['A/case01']
    assert 'RESET_DIVERGED' in R['flags'] and R['rebases'][-1]['diverged'] is True


@test
def test_t49_second_supersede_refused():
    w = q_world()
    drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH')
    a = {'ended': True, 'files_found': False, 'transcript': 'exported', 'outcome': 'NO_CONVERSATION',
         'list_shows_none': True}
    w.commit(CW._restore(w, resolve=CW.open_role(w.state), ans=a))           # V1 superseded once (T43)
    assert not [m for m in CW._restore_moves(w) if m[0] == 'RESTORE_REBASE']


@test
def test_t23_refusal_halts_and_t41_reprepare_abandon():
    w = q_world()
    drive(w, 'PREPARE_GENERATE', 'AI', 'REFUSED_HALT')
    assert w.state['phase'] == 'HALTED' and w.state['halt']['code'] == 'RUNNER_REFUSED'
    w = CW.World('E1')
    w.commit(CW.genesis(w))
    drive(w, 'INPUTS', 'RESTORE_REPREPARE')
    assert [m[0] for m in CW._restore_moves(w)] == ['RESTORE_ABANDON']
    drive(w, 'RESTORE_ABANDON')
    assert w.state['current'] is None and w.state['notify']['what'] == 'ASK_USER'


@test
def test_everyday_delivery_rows():
    w = CW.World('E1')
    w.commit(CW.genesis(w))
    drive(w, 'INPUTS', 'PREPARE_E', 'AI', 'FINISH', 'AI', 'DELIVER_CHECK', 'DELIVERY')
    e = CW._restore(w, delivery_question={'run': w.state['current'], 'prepared_seq': w.state['seq']})
    assert w.commit(e) == ['T42']
    assert w.state['notify']['about'] == 'DELIVERY'
    drive(w, 'ACK_no')
    assert w.state['runs'][w.state['current']]['delivery']['resend_ok'] is True
    drive(w, 'SENT_FREEZE')
    assert w.state['current'] is None and w.state['notify'] is None


# ============================================================ chain_next (§7.3)
def res(kind='NEXT', nxt='DONE', rec=False, led=False, tree=False, codes=(), bound=None):
    return {'result': kind, 'next': nxt, 'codes': list(codes), 'record_changed': rec, 'ledger_changed': led,
            'tree_changed': tree, 'bound': bound}


CN = {'n': 1, 'freeze_retries': 0, 'v_review_incomplete': 0, 'diverged': False}
CANON = {
    'X1': ('finish', res(nxt='STOP_X'), CN, 'qualification', {'commands': [['finish', 'VISUAL_REVIEW', []]],
                                                                'values': {}}),
    'X2': ('finish', res('REFUSED', 'JOB_BUSY'), CN, 'qualification', None),
    'X3': ('visual-record', res('REFUSED', 'REVIEW_INCOMPLETE', rec=True), CN, 'qualification', None),
    'X4': ('visual-record', res('REFUSED', 'REVIEWER_CONVERSATION_ID_REQUIRED'), dict(CN, v_review_incomplete=2),
           'qualification', None),
    'X5': ('interrupt', res('REFUSED', 'INTERRUPT_RESTART_USED'), CN, 'qualification', None),
    'X6': ('finish', res('REFUSED', 'RESPONSE_INVALID', rec=True), CN, 'qualification', None),
    'X7': ('finish', res('REFUSED', 'RESPONSE_WRITTEN'), CN, 'qualification', None),
    'X8': ('verify-frozen', res(nxt='STOP_FROZEN_FOLDER_CHANGED'), CN, 'qualification', None),
    'X9': ('verify-frozen', res(), CN, 'qualification', None),
    'X10': ('freeze', res(nxt='STOP_FREEZE_INCOMPLETE'), CN, 'qualification', None),
    'X11': ('freeze', res(nxt='STOP_FREEZE_INCOMPLETE'), dict(CN, freeze_retries=2), 'qualification', None),
    'X12': ('nonattempt', res(), CN, 'qualification', None),
    'X13': ('interrupt', res(nxt='STOP_TECHNICAL_INTERRUPTION'), CN, 'qualification', None),
    'X14': ('interrupt', res(nxt='GENERATE'), CN, 'qualification', None),
    'X15': ('prepare', res(nxt='SCOPE_READER'), CN, 'qualification', None),
    'X16': ('visual-record', res(nxt='FREEZE'), CN, 'qualification', None),
    'X17': ('visual-record', res(nxt='DELIVER_CHECK'), CN, 'everyday', None),
    'X18': ('deliver-check', res(nxt='DELIVER'), CN, 'everyday', None),
    'X19': ('finish', res(nxt='OWNER_DECISION'), CN, 'qualification', None),
    'X20': ('visual-record', res(nxt='DELIVER_CHECK'), CN, 'qualification', None),
}


@test
def test_imp07_chain_rows_first_match_none_shadowed():
    for row, args in CANON.items():
        assert P.chain_next(*args)['row'] == row, (row, P.chain_next(*args))
    assert P.chain_next('freeze', res(nxt='STOP_FREEZE_INCOMPLETE'), dict(CN, n=6), 'qualification',
                        None)['code'] == 'INTERNAL_CHAIN_TOO_LONG'
    r = P.chain_next('finish', res('UNPARSEABLE', ''), CN, 'qualification', None)
    assert (r['row'], r['code']) == ('X7', 'RUNNER_OUTPUT_UNPARSEABLE')
    r = P.chain_next('freeze', res(nxt='DONE'), dict(CN, n=2), 'qualification',
                     {'commands': [['finish', 'STOP_X', []]], 'values': {}})
    assert (r['row'], r['sub'], r['diverged']) == ('X12', 'verify-frozen', True)
    b = {'commands': [['finish', 'VISUAL_REVIEW', []]], 'values': {'next': 'VISUAL_REVIEW'}}
    r = P.chain_next('finish', res(nxt='VISUAL_REVIEW', bound={'next': 'VISUAL_REVIEW'}), CN, 'qualification', b)
    assert (r['row'], r['start']) == ('X15', 'V')
    r = P.chain_next('finish', res(nxt='VISUAL_REVIEW', bound={'next': 'OTHER'}), CN, 'qualification', b)
    assert r['row'] == 'X1'


# ============================================================ next_action (§7.1)
def view(w, marks=None, **kw):
    v = {'state': w.state if w else None, 'marks': marks or {}, 'local': {'gates_ok': True}, 'now': CW.utc(
        w.t + 30 if w else CW.T0), 'boot_id': w.boot if w else CW.boot(1), 'base': CW.BASE,
         'cfg': {'transcript_ext': 'json', 'clear': None}}
    v.update(kw)
    return v


@test
def test_next_action_rows():
    assert P.next_action(view(None))== Commit({'kind': 'GENESIS', 'body': None})
    w = q_world()
    assert P.next_action(view(w)) == RunChain('A/case01', 'prepare', {'new_run': {
        'tag': 'A', 'case': 'case01', 'reader': 'A', 'root': 'A', 'restart_of': None}, 'place_frozen': []})
    drive(w, 'PREPARE_GENERATE')
    st = P.next_action(view(w))
    assert isinstance(st, PrintBlock) and st.do[0] == 'OPEN_CONVERSATION' and 'then' not in st.do[1]
    marks = {st.mark: 'x'}
    ex = P.next_action(view(w, marks))                                  # v2.1: no OPENED, no AWAIT (SD-37)
    assert ex.do[0] == 'EXPORT_TRANSCRIPT' and 'conversation' not in ex.do[1]
    marks[ex.mark] = 'x'
    ask = P.next_action(view(w, marks))
    assert ask.context['action'] == 'AI' and list(ask.keys) == list(P.G_KEYS) and ask.keys['tools'] == 'TOOLS'
    drive(w, 'HALT')
    assert P.next_action(view(w, marks)) == Stop('HALTED_UNCLASSIFIED', 'C')
    cl = P.next_action(view(w, marks, cfg={'clear': {'series': 'Q1', 'seq': w.state['seq'], 'code': 'UNCLASSIFIED'}}))
    assert cl.entry['kind'] == 'CLEAR'
    drive(w, 'CLEAR')
    assert P.next_action(view(w, marks)).context['action'] == 'AI'         # INT-01 after HALT and CLEAR
    assert P.next_action(view(w, marks, boot_id='other')).context['action'] == 'AI'
    assert P.next_action(view(w, {}, local={'gates_ok': False})) == Stop('RELEASE_GATE_OPEN', 'C')


@test
def test_next_action_row5_other_boot_unclassified():
    w = q_world()
    drive(w, 'PREPARE_GENERATE')
    assert P.next_action(view(w, boot_id='another')) == Stop('UNCLASSIFIED', 'C')


@test
def test_next_action_chains_and_everyday():
    w = CW.World('E1')
    w.commit(CW.genesis(w))
    assert P.next_action(view(w)).context['action'] == 'IDLE'
    drive(w, 'INPUTS')
    assert P.next_action(view(w)).first == 'prepare'
    drive(w, 'PREPARE_E', 'AI')
    assert P.next_action(view(w)) == RunChain(w.state['current'], 'finish', {'consume': 'G1'})
    drive(w, 'FINISH', 'AI', 'DELIVER_CHECK')
    a = P.next_action(view(w))
    assert a.context['action'] == 'DELIVER_COPY' and a.context['file'].endswith('/STANDARD.xlsx')
    drive(w, 'DELIVERY')
    a = P.next_action(view(w))
    assert a.context['action'] == 'DELIVER_USER'
    b = P.next_action(view(w, {a.context['mark']: 'x'}))
    assert b.context['action'] == 'DELIVER_SENT'
    w2 = copy.deepcopy(w)
    w2.commit(CW._restore(w2, delivery_question={'run': w2.state['current'], 'prepared_seq': w2.state['seq']}))
    assert P.next_action(view(w2, {a.context['mark']: 'x'})).context['action'] == 'ASK_USER'
    drive(w2, 'ACK_yes')
    assert P.next_action(view(w2)).info == {'delivery_sent': True}
    drive(w2, 'ARRIVED_FREEZE')
    assert P.next_action(view(w2)).context['action'] == 'IDLE'


@test
def test_next_action_resolution_chains_and_rerun():
    w = q_world()
    drive(w, 'PREPARE_GENERATE')
    a = {'ended': True, 'files_found': False, 'transcript': 'exported', 'outcome': 'NOTHING_WRITTEN',
         'list_shows_none': False}
    w.commit(CW._restore(w, resolve=CW.open_role(w.state), ans=a))
    st = P.next_action(view(w))
    assert st.first == 'interrupt' and st.info['role'] == 'G1'
    w.commit(CW._restore(w, rerun_expected={'run': 'A/case01', 'stage': 'interrupt'}))
    st = P.next_action(view(w))
    assert st.first == 'interrupt' and st.info['rerun']['after_seq'] == w.state['seq']


@test
def test_next_run_order_and_final():
    w = CW.World('Q1', jobs=[['c1', 1, None], ['c2', 2, 'NA']])
    w.commit(CW.genesis(w))
    assert P.next_action(view(w)).run == 'NA-A/c2'
    drive(w, 'NA')
    assert P.next_action(view(w)).run == 'NA-B/c2'
    drive(w, 'NA')
    assert P.next_action(view(w)).run == 'A/c1'
    drive(w, 'PREPARE_STOP', 'ACK')
    st = P.next_action(view(w))
    assert (st.run, st.info['place_frozen']) == ('A-restart1/c1', ['A/c1'])
    drive(w, 'PREPARE_STOP', 'ACK')
    st = P.next_action(view(w))
    assert (st.run, st.info['place_frozen']) == ('B/c1', ['A-restart1/c1'])
    drive(w, 'PREPARE_STOP', 'ACK', 'PREPARE_STOP', 'ACK')
    assert P.next_action(view(w)) == Commit({'kind': 'FINAL', 'body': None})
    drive(w, 'FINAL')
    assert P.next_action(view(w)) == Stop('FINAL', 'B')


# ============================================================ names (§3.2, §6.3)
CFG = {'drive_id_re': N.DEFAULT_DRIVE_ID_RE, 'conversation_re': r'conv-[a-z0-9]{8}', 'doc_samples': ['conv-abcd1234',
       'gpt-example'], 'home': '/home/agent', 'case': 'case01'}


@test
def test_names_patterns():
    good = [('ID', 'abcdefghij0123456789_-'), ('SIZE', '12'), ('UTC', '2026-11-10T01:02:03Z'),
            ('MODEL', 'gpt-5.1'), ('EFFORT', 'high'), ('YES', 'yes'), ('YESNO', 'no'), ('TOOLS', 'inventory'),
            ('TOOLS', 'file:/home/agent/tools.txt'), ('APPROVAL', 'none'), ('APPROVAL', 'pending'), ('OUTCOME', 'UNSURE'), ('TRANSCRIPT', 'not_available'), ('CASE_ID', 'case01'),
            ('CONV', 'conv-0a1b2c3d'),
            ('COPYPATH', '/home/agent/cps-deliveries/case01/u1/20261110T010203Z/PERSONAL_COPY.xlsx')]
    for pat, v in good:
        assert N.check_value('k', pat, v, CFG) is None, (pat, v)
    bad = [('ID', 'short', 'VALUE_PATTERN'), ('SIZE', '012', 'VALUE_PATTERN'), ('TOOLS', 'none', 'VALUE_PATTERN'),
           ('TOOLS', 'web', 'VALUE_PATTERN'), ('TOOLS', 'file:relative.txt', 'VALUE_PATTERN'),
           ('APPROVAL', 'yes', 'VALUE_PATTERN'),
           ('UTC', '2026-02-30T01:02:03Z', 'VALUE_PATTERN'), ('YES', 'Yes', 'VALUE_PATTERN'),
           ('CASE_ID', 'case01\n', 'VALUE_FORBIDDEN'), ('CASE_ID', 'ca se', 'VALUE_FORBIDDEN'),
           ('CASE_ID', 'case\x00', 'VALUE_FORBIDDEN'), ('SIZE', '１２', 'VALUE_FORBIDDEN'),
           ('CONV', '{CONVERSATION_ID}', 'VALUE_FORBIDDEN'), ('ID', '<id>', 'VALUE_FORBIDDEN'),
           ('CONV', 'CONV', 'VALUE_PLACEHOLDER'), ('MODEL', 'model', 'VALUE_PLACEHOLDER'),
           ('MODEL', 'gpt-example', 'VALUE_PLACEHOLDER'), ('CONV', 'conv-abcd1234', 'VALUE_PLACEHOLDER'),
           ('CASE_ID', '', 'VALUE_FORBIDDEN'),
           ('COPYPATH', '/home/agent/cps-deliveries/case02/u1/20261110T010203Z/PERSONAL_COPY.xlsx', 'VALUE_PATTERN'),
           ('CONV', 'xconv-0a1b2c3d', 'VALUE_PATTERN'), ('CONV', 'conv-0a1b2c3dx', 'VALUE_PATTERN')]
    for pat, v, code in bad:
        assert N.check_value('k', pat, v, CFG) == (code, 'k'), (pat, v, N.check_value('k', pat, v, CFG))
    assert N.check_value('t', 'UTC', '2026-11-10T01:02:03Z', CFG, ['2026-11-10T01:02:04Z', '2026-11-11T00:00:00Z']) \
        == ('UTC_OUT_OF_WINDOW', 't')
    assert N.fm(N.ENTRY, 'CPSJ_Q1_000001.tgz') and not N.fm(N.ENTRY, 'CPSJ_Q1_000001.tgz\n')
    assert N.parse_part('CPSJ_Q1_000002_PNG01.part') == ('Q1', 2, 'PNG', 1)
    assert N.parse_part('CPSJ_Q1_000002_PNG01.json') is None and N.parse_part('CPSJ_Q1_000002_PNG00.part') is None
    assert N.fm(N.TAG, 'E20261110T010203Z') and not N.fm(N.TAG, 'C')
    assert N.check_config_patterns(r'.*', []) == 'CONFIG_INVALID'
    assert N.check_config_patterns(CFG['conversation_re'], CFG['doc_samples']) == 'CONFIG_INVALID'
    assert N.check_config_patterns(CFG['conversation_re'], []) is None


@test
def test_names_answers_and_at():
    keys = {'ended': 'YES', 'conversation': 'CONV'}
    assert N.check_answers(keys, [('ended', 'yes'), ('conversation', 'conv-0a1b2c3d')], CFG)[0] is None
    assert N.check_answers(keys, [('ended', 'yes')], CFG)[0] == ('ARG_MISSING_KEY', 'conversation')
    assert N.check_answers(keys, [('ended', 'yes'), ('ended', 'yes'), ('conversation', 'c')], CFG)[0][0] == \
        'ARG_DUPLICATE_KEY'
    assert N.check_answers(keys, [('ended', 'yes'), ('conversation', 'conv-0a1b2c3d'), ('x', 'y')], CFG)[0] == \
        ('ARG_EXTRA_KEY', 'x')
    assert N.check_answers(keys, [('ended', 'yes '), ('x', 'y')], CFG)[0] == ('VALUE_FORBIDDEN', 'ended')
    a = N.at_string(124, 7, 'a' * 64, None, ['UPLOAD x', 'DO: RUN go'])
    assert N.fm(r'000124-0007-[0-9a-f]{6}', a) and a == N.at_string(124, 7, 'a' * 64, None, ['UPLOAD x', 'DO: RUN go'])
    assert a != N.at_string(124, 7, 'a' * 64, 'b' * 64, ['UPLOAD x', 'DO: RUN go'])
    for c in ('FORK', 'HALTED_RUNNER_REFUSED', 'OWNER_CHECKS_INVALID'):
        assert N.is_code(c)
    assert not N.is_code('HALTED_NOPE')


@test
def test_validate_entry_full():
    w = q_world()
    drive(w, 'PREPARE_GENERATE')
    e = copy.deepcopy(w.entries[-1])
    e['state'] = w.state
    e['state_sha256'] = EN.state_sha256(w.state)
    assert EN.validate_entry(e) == []
    assert EN.validate_entry(e, cfg={'series': 'Q1', 'accepted_helper_tree_sha256': [CW.TREE]}) == []
    assert EN.validate_entry(e, cfg={'series': 'Q1', 'accepted_helper_tree_sha256': []})
    e['state_sha256'] = 'f' * 64
    assert 'state_sha256' in EN.validate_entry(e)
    e = copy.deepcopy(w.entries[-1])
    assert EN.validate_entry(e) and EN.validate_entry(e, draft=True) == []
    e['parts'] = [{'name': 'CPSJ_Q1_000002_DELIV01.xlsx', 'kind': 'DELIV', 'k': 1, 'folder': 'x', 'sha256': 'a' * 64,
                   'md5': 'b' * 32, 'bytes': 1}]
    assert EN.validate_entry(e, draft=True)


# ============================================================ head_search (§8.4)
class Drive:
    """A model of exact-name search: present names (with copies), names that lag (missing for their first n finds),
    and a clock that WAIT advances."""

    def __init__(self, series, n, lag=None, dup=False, foreign=None, gates=None):
        self.series, self.n, self.lag, self.t = series, n, dict(lag or {}), CW.T0
        self.dup, self.foreign, self.lookups, self.calls = dup, foreign, [], 0
        self.gates = dict(CW.GATES, **(gates or {}))

    def copies(self, k):
        if k > self.n:
            return []
        cp = [['ID%06d' % k, CW.md5ish('e%d' % k), 100]]
        if self.dup:
            cp.append(['IX%06d' % k, CW.md5ish('e%d' % k), 100])
        if self.foreign == k:
            cp.append(['IF%06d' % k, CW.md5ish('foreign'), 100])
        return cp

    def search(self, hint=None, newest=False, limit=200):
        for _ in range(limit):
            r = SE.head_search(self.series, hint, self.lookups, self.gates, CW.utc(self.t))
            if 'verdict' in r:
                return r
            self.calls += 1
            if r['need'] == 'wait':
                self.t += r['seconds']
            else:
                k = int(r['name'][-10:-4])
                cp = self.copies(k)
                if self.lag.get(k, 0) > 0:
                    self.lag[k] -= 1
                    cp = []
                self.lookups.append({'name': r['name'], 'result': 'present' if cp else 'absent', 'copies': cp,
                                     'utc': CW.utc(self.t)})
                self.t += 5
        raise AssertionError('no verdict')


@test
def test_head_search_paths():
    for n in (1, 2, 3, 7, 8, 100, 1500):
        for hint in (None, 1, max(1, n - 3), n):
            d = Drive('Q1', n)
            r = d.search(hint)
            assert (r['verdict'], r['seq']) == ('head', n), (n, hint, r)
    assert Drive('Q1', 0).search()['verdict'] == 'fresh'
    assert Drive('Q1', 5).search(hint=9)['code'] == 'HINT_AHEAD'
    d = Drive('Q1', 30, dup=True)
    r = d.search(hint=28)
    assert r['seq'] == 30 and len(r['copies']) == 2
    r = Drive('Q1', 30, foreign=30).search(hint=28)          # v2.1: copies are compared only by their downloads
    assert (r['verdict'], r['seq'], len(r['copies'])) == ('head', 30, 2), r
    d = Drive('Q1', 12, lag={12: 1})                     # N lags once: the second absence check finds it
    assert d.search(hint=10)['seq'] == 12
    d = Drive('Q1', 12, lag={13: 0})
    assert d.search(hint=12)['seq'] == 12
    d = Drive('Q1', 20, lag={k: 1 for k in range(5, 20)})
    assert d.search()['code'] == 'HEAD_UNSTABLE'


@test
def test_head_search_wait_between_absences():
    """G3: a single absence of N+1 is never accepted; the second comes at least w_abs later."""
    d = Drive('Q1', 5)
    r = d.search(hint=5)
    ab = [x for x in d.lookups if x['name'] == N.entry_name('Q1', 6)]
    assert r['seq'] == 5 and len(ab) == 2
    assert N.utc_epoch(ab[1]['utc']) - N.utc_epoch(ab[0]['utc']) >= F.w_abs(d.gates)


@test
def test_int05_single_part_absence_is_not_missing():
    lk = [{'name': 'p1', 'result': 'absent', 'copies': [], 'utc': CW.utc(CW.T0)}]
    assert SE.absent_twice(['p1'], lk, 60, CW.utc(CW.T0 + 10)) == ('wait', 50)
    assert SE.absent_twice(['p1'], lk, 60, CW.utc(CW.T0 + 70)) == ('find', ['p1'])
    lk.append({'name': 'p1', 'result': 'absent', 'copies': [], 'utc': CW.utc(CW.T0 + 70)})
    assert SE.absent_twice(['p1'], lk, 60, CW.utc(CW.T0 + 70))[1] == {'p1': 'missing'}
    lk.append({'name': 'p1', 'result': 'present', 'copies': [['i', 'a' * 32, 1]], 'utc': CW.utc(CW.T0 + 90)})
    assert SE.absent_twice(['p1'], lk, 60, CW.utc(CW.T0 + 90))[1] == {'p1': 'present'}


# ============================================================ classify (§8.5)
@test
def test_classify_rows():
    g = CW.GATES
    w = q_world()
    head = w.entries[-1]
    assert SE.classify(head, w.state, [], None, True, g)[0] == 'C9'
    drive(w, 'PREPARE_GENERATE')
    assert SE.classify(w.entries[-1], w.state, [], None, True, g) == ('C6', {'run': 'A/case01', 'role': 'G1'})
    drive(w, 'AI')
    assert SE.classify(w.entries[-1], w.state, [], None, True, g)[0] == 'C8'
    drive(w, 'FINISH')
    h = w.entries[-1]
    miss = [h['parts'][0]['name']]
    assert SE.classify(h, w.state, miss, None, True, g) == ('C5', {'rebase': True, 'ask_list': h['body']['start'][
        'utc']})
    w2 = copy.deepcopy(w)
    w2.commit(CW._restore(w2, rebase=True))
    assert SE.classify(w2.entries[-1], w2.state, [], None, True, g)[0] == 'C5b'
    drive(w, 'HALT')
    assert SE.classify(w.entries[-1], w.state, [], None, True, g) == ('C2', {'stop': 'HALTED_UNCLASSIFIED'})
    cl = {'series': 'Q1', 'seq': w.state['seq'], 'code': 'UNCLASSIFIED'}
    assert SE.classify(w.entries[-1], w.state, [], cl, True, g) == ('C2', {'clear': True})
    assert SE.classify(w.entries[-1], w.state, [], cl, False, g)[1] == {'stop': 'HALTED_UNCLASSIFIED'}


@test
def test_classify_c7_before_c8_and_c8b():
    w = CW.World('E1')
    w.commit(CW.genesis(w))
    drive(w, 'INPUTS')
    assert SE.classify(w.entries[-1], w.state, [], None, True, CW.GATES)[1]['reprepare'] is True
    drive(w, 'PREPARE_E', 'AI', 'FINISH', 'AI', 'DELIVER_CHECK', 'DELIVERY')
    assert SE.classify(w.entries[-1], w.state, [], None, True, CW.GATES)[0] == 'C7'
    assert SE.classify(w.entries[-1], w.state, [w.entries[-1]['parts'][0]['name']], None, True, CW.GATES)[0] == 'C4'


# ============================================================ session_next (§8.1-8.7): drafts that fold
def work(**kw):
    w = {'done': ['LAYOUT', 'SETUP', 'KIT', 'CONFIG', 'FINGERPRINT', 'PASS', 'CLOCK'],
         'operator': {'model': 'gpt-x', 'platform': 'chat'}, 'hint': {'seq': None, 'kit': None}, 'lookups': [],
         'approval': 'none', 'head': None, 'head_error': None, 'identity': {'home': '/home/agent', 'uid': 1000},
         'kit': {'sha256': CW.KIT, 'members': CW.MEMBERS, 'config': {'gates': None}, 'release_sha256': CW.REL},
         'head_kit': None, 'list_shows_none': None, 'resolve': {}, 'placed': False, 'reuploaded': False,
         'committed': None}
    w.update(kw)
    return w


def run_session(cw, wk, answers=None, files_found=False, limit=300):
    """Drive session_next against the World's entries as the Drive; returns the final (phase, step) and the work."""
    t = cw.t + 100
    names = {e['name']: e for e in cw.entries}
    for p in [p for e in cw.entries for p in e['parts']]:
        names[p['name']] = p
    for _ in range(limit):
        v = {'work': wk, 'series': cw.series, 'gates': cw.gates, 'clear': None, 'now': CW.utc(t), 'base': CW.BASE,
             'transcript_ext': 'json'}
        ph, st = SE.session_next(v)
        if isinstance(st, PrintBlock) and st.do[0] == 'WAIT':
            t += st.do[1]['seconds']
        elif isinstance(st, PrintBlock) and st.do[0] == 'ATTEST_FOUND':
            for f in st.finds:
                x = names.get(f[2])
                cid = None if x is None else 'ID' + (CW.md5ish('e%d' % x['seq']) if 'parts' in x else x['md5'])
                size = None if x is None else 1000 if 'parts' in x else x['bytes']      # the sizes confirms record
                if f[2] in wk.get('_fresh_ids', ()):                                    # an id never recorded
                    cid = 'IDN%019d' % len(wk['lookups'])
                cp = [] if x is None or f[2] in wk.get('_deleted', ()) else [[cid, size]]
                wk['lookups'].append({'name': f[2], 'result': 'present' if cp else 'absent', 'copies': cp,
                                      'utc': CW.utc(t)})
                if wk.get('committed'):                    # as the glue flags a step-6 re-check FIND
                    wk['lookups'][-1]['post'] = True
            t += 5
        elif isinstance(st, PrintBlock) and st.downloads:              # rule V: every download hashed (§2.1)
            for _f, cid, path in st.downloads:
                x = names[path.rsplit('/', 1)[1].rsplit('.', 1)[0]]
                if x is cw.entries[-1] and not wk.get('head'):
                    wk['head'] = {'entry': dict(x, state=cw.state, state_sha256=EN.state_sha256(cw.state)),
                                  'md5': CW.md5ish('e%d' % x['seq']), 'sha256': CW.hx('entry', x['seq']),
                                  'bytes': 1000}
                    continue
                real = x['sha256'] if 'parts' not in x else CW.hx('entry', x['seq'])
                wk.setdefault('verified', {})[cid] = ['0' * 64 if cid.startswith('IDX') else real, 1000]
        elif isinstance(st, PrintBlock) and st.do[0] in ('END_CONVERSATION', 'EXPORT_TRANSCRIPT'):
            wk['resolve']['end' if st.do[0] == 'END_CONVERSATION' else 'export'] = True
        elif isinstance(st, Place):
            if ph == 'RESOLVE_PLACE':
                wk['resolve'].update(placed=True, files_found=files_found)
            else:
                wk['placed'] = True
        elif isinstance(st, Ask) and st.context['action'] == 'RESTORE_ROLE':
            wk['resolve']['answers'] = answers
        elif isinstance(st, Ask) and st.context['action'] == 'APPROVAL':
            wk['approval'] = 'none'
        elif isinstance(st, Ask) and st.context['action'] == 'LIST_SHOWS_NONE':
            wk['list_shows_none'] = True
        elif ph in ('KIT_ACCEPT',) and st is None:
            wk['head_kit'] = {'sha256': cw.state['kit_sha256'], 'members': CW.MEMBERS,
                              'config': wk['kit']['config']}
        else:
            cw.t = max(cw.t, t)                  # the World's clock follows the session's (lookups before a commit)
            return ph, st, wk
    raise AssertionError('session did not finish')


def complete_restore(cw, st):
    """Fill the glue's I/O fields of a RESTORE draft and fold it."""
    b = dict(st.entry['body'], fingerprint_sha256=CW.FP, pass_={}, placed=[])
    b['pass'] = {'name': 'FINGERPRINT_PASS_%s.json' % CW.FP, 'md5': CW.md5ish('pass')}
    b.pop('pass_')
    cw.reset()
    members = []
    for it in b['resolutions']:
        if it['transcript'] == 'exported':
            members = [['transcript', 'dir', 0o755, None, None],
                       ['transcript/%s%d_%d.json' % (it['role'], it['attempt'], it['start_no']), 'file', 0o644, 5,
                        CW.hx('t')]]
    confirms = None
    if b['rebase']:
        s = cw.state
        confirms = [{'name': N.entry_name(cw.series, s['seq']), 'copies': [
            {'id': 'I' * 20, 'md5': CW.md5ish('e%d' % s['seq']), 'size': 1000}]}] + [
            {'name': p[0], 'copies': [] if p[0] in b['rebase']['missing_parts'] else
             [{'id': 'I' * 20, 'md5': p[1], 'size': p[2]}]} for p in s['undo']['parts']]
    e = cw.entry('RESTORE', b, members=members, confirms=confirms, kit=b['kit_sha256'])
    if b['start']:
        b['start'].update(utc=e['utc'], boot_id=e['boot_id'])
    return cw.commit(e)


@test
def test_session_restore_open_role_draft_folds():
    for ans, act in (({'ended': 'yes', 'outcome': 'NOTHING_WRITTEN', 'transcript': 'exported',
                       'list_shows_none': 'no'}, 'INTERRUPT'),
                     ({'ended': 'yes', 'outcome': 'NO_CONVERSATION', 'transcript': 'exported',
                       'list_shows_none': 'yes'}, 'SUPERSEDE'),
                     ({'ended': 'no', 'outcome': 'NOTHING_WRITTEN', 'transcript': 'not_available',
                       'list_shows_none': 'no'}, 'FREEZE_LOST')):
        cw = q_world()
        drive(cw, 'PREPARE_GENERATE')
        wk = work(hint={'seq': cw.state['seq'], 'kit': None})
        wk['kit']['config']['gates'] = cw.gates
        ph, st, wk = run_session(cw, wk, ans)
        assert ph == 'COMMIT' and isinstance(st, Commit), (ph, st)
        assert st.entry['body']['resolutions'][0]['action'] == act
        rows = complete_restore(cw, st)
        assert rows[0] == 'T42', rows
        wk['committed'] = {'seq': cw.state['seq'], 'md5': 'x', 'utc': CW.utc(cw.t), 'bytes': 1000,
                           'sha256': CW.hx('entry', cw.state['seq']), 'ids': []}
        assert run_session(cw, wk, ans)[:2] == ('DONE', None)


@test
def test_session_rebase_and_recheck_fork():
    cw = q_world()
    drive(cw, 'PREPARE_GENERATE', 'AI', 'FINISH')
    wk = work()
    wk['kit']['config']['gates'] = cw.gates
    wk['_deleted'] = [cw.entries[-1]['parts'][0]['name']]
    ph, st, wk = run_session(cw, wk)
    assert ph == 'COMMIT' and st.entry['body']['rebase']['missing_parts'] == wk['_deleted']
    assert complete_restore(cw, st) == ['T42', 'T49']
    wk['committed'] = {'seq': cw.state['seq'], 'md5': 'not-ours', 'utc': CW.utc(cw.t), 'bytes': 1000,
                       'sha256': 'x' * 64, 'ids': []}
    ph, st, wk = run_session(cw, wk)                   # found by gallop in Q: the re-check runs; N+1's md5 differs
    assert (ph, st) == ('RECHECK', Stop('FORK', 'C')), (ph, st)


@test
def test_session_fresh_q_genesis_and_series_exists():
    cw = CW.World('Q2')
    ph, st, wk = run_session(cw, work())
    assert ph == 'DONE' and st.entry['kind'] == 'GENESIS' and len(st.entry['body']['other_series_absent']) == 8
    other = CW.World('Q1')
    other.commit(CW.genesis(other))
    cw.entries = other.entries
    ph, st, wk = run_session(cw, work())
    assert (ph, st) == ('HEAD', Stop('QUALIFICATION_SERIES_EXISTS', 'C')), (ph, st)
    assert SE.session_next({'work': work(operator=None), 'series': 'Q1', 'gates': CW.GATES, 'clear': None,
                            'now': CW.utc(CW.T0), 'base': CW.BASE})[0] == 'OPERATOR'
    assert SE.session_next({'work': work(done=['LAYOUT']), 'series': 'Q1', 'gates': CW.GATES, 'clear': None,
                            'now': CW.utc(CW.T0), 'base': CW.BASE}) == ('SETUP', None)


@test
def test_session_restore_drafts_fold_over_generated_states():
    """For heads reached by random legal walks, the session's RESTORE draft (completed with the glue's I/O fields)
    is accepted by the fold: session and fold agree on C6-C9, T41 and T42."""
    folded, stops = 0, {}
    for seed in range(120):
        rng = random.Random(seed)
        cw = CW.World(rng.choice(['Q1', 'E1']), gates=rng.choice(GATE_SETS), rng=rng)
        cw.commit(CW.genesis(cw))
        for _ in range(rng.randint(1, 40)):
            mv = [m for m in CW.moves(cw) if not m[0].startswith(('RESTORE', 'HALT'))]
            if not mv:
                break
            cw.commit(rng.choice(mv)[1]())
        if cw.state['phase'] == 'FINAL':
            continue
        op = CW.open_role(cw.state)
        ans = None
        if op:
            a = rng.choice(CW.answer_variants(cw.state, op[2]))
            yn = {True: 'yes', False: 'no', None: None}
            ans = {'ended': yn[a['ended']], 'transcript': a['transcript'], 'outcome': a['outcome'],
                   'list_shows_none': yn[a['list_shows_none']]}
        wk = work(hint={'seq': cw.state['seq'], 'kit': None})
        wk['kit']['config']['gates'] = cw.gates
        ph, st, wk = run_session(cw, wk, ans, files_found=op is not None and rng.random() < 0.2)
        if isinstance(st, Stop):
            stops[st.code] = stops.get(st.code, 0) + 1
            continue
        assert ph == 'COMMIT', (seed, ph, st)
        rows = complete_restore(cw, st)
        assert rows[0] in ('T41', 'T42'), rows
        folded += 1
    assert folded > 80 and set(stops) <= {'HALTED_UNCLASSIFIED', 'HALTED_RUNNER_REFUSED'}, (folded, stops)


@test
def test_session_c5b_after_rebase_restore():
    cw = _rebase_world()
    wk = work()
    wk['kit']['config']['gates'] = cw.gates
    wk['_deleted'] = [cw.entries[-1]['parts'][0]['name']]
    ph, st, wk = run_session(cw, wk)
    complete_restore(cw, st)                          # rebase RESTORE committed; a reset before its re-run
    for appeared in (False, True):
        c = copy.deepcopy(cw)
        wk = work(hint={'seq': c.state['seq'], 'kit': None})
        wk['kit']['config']['gates'] = c.gates
        if not appeared:
            wk['_deleted'] = list(c.entries[-1]['body']['rebase']['missing_parts'])
        ph, st, wk = run_session(c, wk)
        if appeared:
            assert (ph, st) == ('CLASSIFY', Stop('REBASE_PART_APPEARED', 'C')), (ph, st)
        else:
            assert ph == 'COMMIT' and st.entry['body']['rerun_expected'] is None
            assert complete_restore(c, st) == ['T42']
            assert c.state['runs']['A/case01']['rebase_bind'] is not None


@test
def test_session_c2_clear_rebase_conflict_head_error():
    cw = q_world()
    drive(cw, 'PREPARE_GENERATE', 'AI', 'HALT')
    wk = work(hint={'seq': cw.state['seq'], 'kit': None})
    wk['kit']['config']['gates'] = cw.gates
    assert run_session(cw, copy.deepcopy(wk))[:2] == ('CLASSIFY', Stop('HALTED_UNCLASSIFIED', 'C'))
    v = {'series': 'Q1', 'seq': cw.state['seq'], 'code': 'UNCLASSIFIED'}
    t = cw.t + 100
    w2 = copy.deepcopy(wk)
    w2['kit'] = {'sha256': CW.KIT2, 'members': [CW.MEMBERS[0], [CW.MEMBERS[1][0], CW.hx('c2')], CW.MEMBERS[2]],
                 'release_sha256': CW.REL, 'config': {'gates': cw.gates, 'clear': v}}
    w2['head_kit'] = {'sha256': CW.KIT, 'members': CW.MEMBERS, 'config': {'gates': cw.gates, 'clear': None}}
    orig = SE.session_next

    def with_clear(view):
        return orig(dict(view, clear=v))
    SE.session_next = with_clear
    try:
        ph, st, w2 = run_session(cw, w2)
    finally:
        SE.session_next = orig
    assert ph == 'COMMIT' and st.entry['body']['kit_change'] is None, (ph, st)       # SD-51: the halted kit kept
    assert st.entry['body']['kit_sha256'] == CW.KIT == cw.state['kit_sha256']
    assert complete_restore(cw, st) == ['T42'] and cw.state['kit_sha256'] == CW.KIT
    assert P.next_action(view(cw, cfg={'clear': v})).entry['kind'] == 'CLEAR'
    cw = _rebase_world()
    wk = work()
    wk['kit']['config']['gates'] = cw.gates
    wk['_deleted'] = [cw.entries[-1]['parts'][0]['name']]
    ph, st, _ = run_session(cw, dict(wk, list_shows_none=False))
    assert (ph, st) == ('CLASSIFY', Stop('REBASE_CONFLICT', 'C')), (ph, st)
    assert run_session(cw, work(head_error='HEAD_CORRUPT'))[:2] == ('HEAD', Stop('HEAD_CORRUPT', 'C'))


@test
def test_plan_helpers():
    assert P.frozen_notify('qualification', 'STOP_X', [], False) == 'NOTIFY_OWNER'
    assert P.frozen_notify('qualification', 'DONE', [], False) is None
    assert P.frozen_notify('everyday', 'DONE', [], True) is None
    assert P.frozen_notify('everyday', 'GENERATE', ['AI_OUTPUT_LOST'], False) == 'ASK_USER'
    assert P.frozen_notify('everyday', 'OWNER_DECISION', [], False) == 'NOTIFY_OWNER'
    w = q_world()
    drive(w, 'PREPARE_GENERATE', 'AI')
    R = w.state['runs']['A/case01']
    assert P.consumer_role(R) == 'G1' and P.v_review_incomplete(R) == 0
    e = [m for m in CW.moves(w) if m[0] == 'FINISH_STOP'][0][1]()
    assert F.expected_frozen_flags(w.state, R, e['body']) == set()


@test
def test_session_c3_final_part_reupload_then_handback_b():
    cw = CW.World('Q1', jobs=[['c1', 1, 'NA']])
    cw.commit(CW.genesis(cw))
    drive(cw, 'NA', 'NA', 'FINAL')
    wk = work(hint={'seq': cw.state['seq'], 'kit': None})
    wk['kit']['config']['gates'] = cw.gates
    wk['_deleted'] = [cw.entries[-1]['parts'][1]['name']]
    ph, st, wk = run_session(cw, wk)
    assert ph == 'CLASSIFY' and st == Reupload((wk['_deleted'][0],), cw.state['seq']), (ph, st)
    wk['reuploaded'] = True
    assert run_session(cw, wk)[:2] == ('DONE', Stop('FINAL', 'B'))


@test
def test_session_link_identity_kit():
    cw = q_world()
    drive(cw, 'PREPARE_GENERATE', 'AI')
    wk = work(hint={'seq': cw.state['seq'], 'kit': None})
    wk['kit']['config']['gates'] = cw.gates
    wk['lookups'].append({'name': N.entry_name('Q1', cw.state['seq'] - 1), 'result': 'present',
                          'copies': [['IDX' * 7, 'f' * 32, 9]], 'utc': CW.utc(cw.t)})
    assert run_session(cw, wk)[:2] == ('HEAD', Stop('LINK_MISMATCH', 'C'))
    wk = work(hint={'seq': cw.state['seq'], 'kit': None}, identity={'home': '/home/other', 'uid': 1})
    wk['kit']['config']['gates'] = cw.gates
    assert run_session(cw, wk)[:2] == ('IDENTITY', Stop('HOME_CHANGED', 'C'))
    wk = work(hint={'seq': cw.state['seq'], 'kit': None})
    wk['kit'] = {'sha256': CW.KIT2, 'members': [m[:] for m in CW.MEMBERS], 'release_sha256': CW.REL2,
                 'config': {'gates': cw.gates, 'accepts_release_sha256': [CW.REL2]}}
    wk['kit']['members'][0][1] = CW.hx('other release')
    assert run_session(cw, wk)[:2] == ('KIT_ACCEPT', Stop('KIT_CHANGE_WITH_RUN_IN_FLIGHT', 'C'))
    wk = work(hint={'seq': cw.state['seq'], 'kit': None})
    wk['kit']['config']['gates'] = dict(cw.gates, p2_lag_seconds=99)
    assert run_session(cw, wk)[:2] == ('KIT_ACCEPT', Stop('GATES_CHANGED', 'C'))


@test
def test_kit_change_rules():
    w = q_world()
    s = w.state
    hk = {'sha256': CW.KIT, 'members': CW.MEMBERS, 'config': {'gates': w.gates, 'clear': None, 'doc_samples': ['a']}}
    cfg_only = [m[:] for m in CW.MEMBERS]
    cfg_only[1][1] = CW.hx('c2')
    k = {'sha256': CW.KIT2, 'members': cfg_only, 'release_sha256': CW.REL,
         'config': {'gates': w.gates, 'clear': {'x': 1}, 'doc_samples': ['a', 'b']}}
    code, kc = SE.kit_change(s, k, hk)
    assert code is None and kc['config_only'] and kc['config_keys_changed'] == ['clear', 'doc_samples']
    assert SE.kit_change(s, dict(k, config=dict(k['config'], doc_samples=[])), hk)[0] == 'CONFIG_CHANGE_NOT_ALLOWED'
    assert SE.kit_change(s, dict(k, config=dict(k['config'], drive_id_re='x')), hk)[0] == 'CONFIG_CHANGE_NOT_ALLOWED'
    rel = [m[:] for m in CW.MEMBERS]
    rel[0][1] = CW.hx('r2')
    k2 = {'sha256': CW.KIT2, 'members': rel, 'release_sha256': CW.REL2, 'config': dict(hk['config'])}
    assert SE.kit_change(s, k2, hk)[0] == 'RELEASE_NOT_ACCEPTED'
    k2['config']['accepts_release_sha256'] = [CW.REL2]
    assert SE.kit_change(s, k2, hk)[0] is None
    assert SE.kit_change(s, k2, dict(hk, sha256=CW.hx('x')))[0] == 'KIT_NOT_VERIFIED'


# ============================================================ outcomes (§9)
def frozen_run(key, final_next='DONE', carrier=True, flags=(), restart_of=None, interrupts=(), roles=None,
               visual='PASS'):
    tag, case = key.split('/')
    return {'key': key, 'tag': tag, 'case': case, 'reader': F.reader_of(tag), 'job_dir': '/j/' + key,
            'restart_of': restart_of, 'status': 'FROZEN', 'flags': list(flags), 'interrupts': list(interrupts),
            'roles': roles or {}, 'reruns': [], 'rebases': [],
            'frozen': {'seq': 9, 'frozen_sha256': 'f' * 64, 'final_next': final_next, 'final_codes': [],
                       'carrier_sha256': 'c' * 64 if carrier else None, 'restart_eligible': False, 'visual': visual}}


def ostate(runs, jobs):
    return {'series': 'Q1', 'seq': 10, 'mode': 'qualification', 'genesis': {'jobs': jobs},
            'runs': {r['key']: r for r in runs}, 'order': [r['key'] for r in runs]}


@test
def test_f4_outcomes_total_over_frozen_shapes():
    res_int = {'seq': 5, 'outcome': 'NOTHING_WRITTEN', 'forced': None, 'action': 'INTERRUPT',
               'transcript': 'not_available', 'owner_check': True}
    g1 = {'role': 'G', 'attempt': 1, 'status': 'RESOLVED', 'starts': [{'role': 'G', 'attempt': 1, 'start_no': 1,
                                                                        'reason': 'STAGE', 'utc': 'u', 'boot_id': 'b',
                                                                        'superseded_by': None}],
          'opened': None, 'archives': [], 'resolution': res_int, 'supersedes': 0}
    cases = [
        (frozen_run('NA-A/c'), ['c', 1, 'WHY'], ('NONATTEMPT', 'WHY')),
        (frozen_run('NA-A/c'), ['c', 1, True], ('NONATTEMPT', 'NONATTEMPT_SOURCE_UNAVAILABLE')),
        (dict(frozen_run('A/c'), status='ACTIVE'), ['c', 1, None], ('EMPTY', 'NOT_RUN')),
        (frozen_run('A/c', flags=['AI_OUTPUT_LOST', 'RESET_DIVERGED']), ['c', 1, None], ('EMPTY', 'AI_OUTPUT_LOST')),
        (frozen_run('A/c', flags=['RESET_DIVERGED']), ['c', 1, None], ('EMPTY', 'RESET_DIVERGED')),
        (frozen_run('A/c', flags=['RESTART_EXHAUSTED_BY_RESET']), ['c', 1, None],
         ('EMPTY', 'RESTART_EXHAUSTED_BY_RESET')),
        (frozen_run('A/c', 'GENERATE'), ['c', 1, None], ('EMPTY', 'FROZEN_AT_AI_STEP_WITHOUT_INTERRUPT')),
        (frozen_run('A/c', 'GENERATE', roles={'G1': g1}), ['c', 1, None], ('SCORE', 'CARRIER')),
        (frozen_run('A-restart1/c', 'STOP_X', carrier=False, restart_of='A/c'), ['c', 1, None],
         ('EMPTY', 'TECHNICAL_STOP_AFTER_RESTART')),
        (frozen_run('A/c', 'STOP_X', carrier=False, interrupts=[{'seq': 3}]), ['c', 1, None],
         ('EMPTY', 'TECHNICAL_STOP_AFTER_RESTART')),
        (frozen_run('A/c', 'OWNER_DECISION'), ['c', 1, None], ('EMPTY', 'OWNER_DECISION')),
        (frozen_run('A/c', 'STOP_ROUTE_CHECK_FAILED', carrier=False), ['c', 1, None], ('EMPTY', 'NO_CARRIER')),
        (frozen_run('A/c', visual='FAILED_BY_RESET', flags=['VISUAL_QA_FAILED_BY_RESET']), ['c', 1, None],
         ('SCORE', 'CARRIER')),
    ]
    for R, job, want in cases:
        o = O.outcomes(ostate([R], [job]))
        p = [x for x in o['pairs'] if x['reader'] == R['reader']][0]
        assert (p['disposition'], p['reason']) == want, (R['key'], want, p)
    o = O.outcomes(ostate([frozen_run('A/c', 'STOP_X', carrier=False), frozen_run('A-restart1/c', restart_of='A/c')],
                          [['c', 1, None]]))
    assert o['pairs'][0]['run'] == 'A-restart1/c' and o['pairs'][0]['runs'] == ['A/c', 'A-restart1/c']
    assert o['pairs'][1]['reason'] == 'NOT_RUN'
    o = O.outcomes(ostate([frozen_run('A/c', roles={'G1': g1})], [['c', 1, None]]))
    assert [i['kind'] for i in o['owner_items']] == ['OWNER_CHECK', 'O52_SHEET']


@test
def test_outcomes_total_over_generated_states():
    n = 0
    for seed in range(60):
        rng = random.Random(seed)
        w = CW.World(rng.choice(['Q1', 'E1']), rng=rng)
        for _ in range(rng.randint(1, 120)):
            mv = CW.moves(w)
            if not mv:
                break
            w.commit(rng.choice(mv)[1]())
            o = O.outcomes(w.state)
            n += 1
            assert len(o['pairs']) == 2 * len(w.state['genesis']['jobs'] or [])
            assert sum(1 for i in o['owner_items'] if i['kind'] == 'O52_SHEET') == 1
    assert n > 1000


@test
def test_o52_sheet_windows_widened():
    """§X.9 rule 5 (SD-33): a superseded START's O52 window is [START1 utc - tol, START2 utc + tol], tol the genesis
    gate p3_clock_tolerance_seconds, recorded in the outcomes; without the gate the window is exact."""
    for tol in (300, None):
        w = q_world(**({'p3_clock_tolerance_seconds': tol} if tol else {}))
        drive(w, 'PREPARE_GENERATE')
        a = {'ended': True, 'files_found': False, 'transcript': 'not_available', 'outcome': 'NO_CONVERSATION',
             'list_shows_none': True}
        w.commit(CW._restore(w, resolve=CW.open_role(w.state), ans=a))
        o = O.outcomes(w.state)
        row = [r for r in o['o52_sheet'] if r['superseded_by'] is not None][0]
        nxt = [r for r in o['o52_sheet'] if r['start_no'] == row['superseded_by']][0]
        t = tol or 0
        assert row['window'] == [N.utc_minus(row['start_utc'], t), N.utc_minus(nxt['start_utc'], -t)], row
        assert o['clock_tolerance_seconds'] == t
        it = [i for i in o['owner_items'] if i['kind'] == 'SUPERSEDED_WINDOW'][0]
        assert it['window'] == row['window']


@test
def test_int03_final_dispositions():
    w = q_world()
    drive(w, 'PREPARE_GENERATE')
    a = {'ended': True, 'files_found': False, 'transcript': 'not_available', 'outcome': 'NO_CONVERSATION',
         'list_shows_none': True}
    w.commit(CW._restore(w, resolve=CW.open_role(w.state), ans=a))
    drive(w, 'AI', 'FINISH')
    a = {'ended': True, 'files_found': False, 'transcript': 'not_available', 'outcome': 'NOTHING_WRITTEN',
         'list_shows_none': False}
    w.commit(CW._restore(w, resolve=CW.open_role(w.state), ans=a))       # V1 replaced, OWNER_CHECK (Q)
    drive(w, 'AI', 'VISUAL_PASS')
    o = O.outcomes(w.state)
    kinds = sorted(i['kind'] for i in o['owner_items'])
    assert kinds == ['O52_SHEET', 'OWNER_CHECK', 'SUPERSEDED_WINDOW'], kinds
    assert o['pairs'][0]['disposition'] == 'SCORE'
    ids = {i['kind']: i['id'] for i in o['owner_items']}
    ok = {'outcomes_sha256': N.sha(N.cjson(o)), 'verdicts': [], 'unlogged': []}
    assert sorted(O.final_dispositions(o, ok)['missing']) == sorted(ids.values())
    v = dict(ok, verdicts=[{'id': ids['SUPERSEDED_WINDOW'], 'verdict': 'CONVERSATION_FOUND'},
                           {'id': ids['OWNER_CHECK'], 'verdict': 'WRITE_FOUND'},
                           {'id': ids['O52_SHEET'], 'verdict': 'SHEET_CHECKED'}],
             unlogged=[{'case': 'case01', 'reader': 'A', 'conversation_utc': 'u', 'note': ''}])
    fd = O.final_dispositions(o, v)
    p = fd['pairs'][0]
    assert (p['disposition'], p['reason'], p['visual']) == ('EMPTY', 'SUPERSEDED_WINDOW_CONVERSATION',
                                                            'FAILED_BY_RESET')
    assert p['also'] == ['UNLOGGED_CONVERSATION'] and fd['qualification_flagged'] and not fd['missing']
    assert o['pairs'][0]['disposition'] == 'SCORE'                       # the input is not modified
    for bad in (dict(ok, outcomes_sha256='0' * 64), dict(ok, verdicts=[{'id': 'nope', 'verdict': 'SHEET_CHECKED'}]),
                dict(ok, verdicts=[{'id': ids['O52_SHEET'], 'verdict': 'WRITE_FOUND'}]),
                dict(ok, verdicts=[{'id': ids['O52_SHEET'], 'verdict': 'SHEET_CHECKED'}] * 2)):
        try:
            O.final_dispositions(o, bad)
            raise AssertionError('accepted')
        except O.OwnerChecksInvalid as x:
            assert x.code == 'OWNER_CHECKS_INVALID'


# ============================================================ lint L2 for core/ (§1.3) and the codes registry
CORE = os.path.join(os.path.dirname(HERE), 'cpsvm2', 'core')
BANNED_MODULES = {'os', 'subprocess', 'shutil', 'tempfile', 'time', 'fcntl', 'pathlib', 'io', 'socket', 'sys'}
BANNED_CALLS = {'open', 'print', 'input', 'exec', 'eval', '__import__'}


@test
def test_core_import_lint():
    for fn in sorted(os.listdir(CORE)):
        if not fn.endswith('.py'):
            continue
        tree = ast.parse(open(os.path.join(CORE, fn)).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name.split('.')[0] not in BANNED_MODULES, (fn, a.name)
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 1 or node.module.split('.')[0] not in BANNED_MODULES | {'cpsvm2'}, (fn, node.module)
                if node.level == 1:
                    mods = [node.module] if node.module else [a.name for a in node.names]
                    assert set(mods) <= {'names', 'entry', 'fold', 'plan', 'step', 'session', 'outcome'}, (fn, mods)
                assert node.level <= 1, fn
            elif isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                assert name not in BANNED_CALLS, (fn, name)
                if isinstance(f, ast.Attribute) and f.attr in ('now', 'time', 'utcnow', 'today'):
                    raise AssertionError('%s calls %s' % (fn, f.attr))


@test
def test_core_codes_registered():
    """Every literal code core passes to Stop/Halt is in the §13 registry (lint L1, the source half)."""
    seen = 0
    for fn in sorted(os.listdir(CORE)):
        if not fn.endswith('.py'):
            continue
        for node in ast.walk(ast.parse(open(os.path.join(CORE, fn)).read())):
            if isinstance(node, ast.Call) and getattr(node.func, 'id', None) in ('Stop', 'Halt') and node.args \
                    and isinstance(node.args[0], ast.Constant):
                seen += 1
                assert N.is_code(node.args[0].value), (fn, node.args[0].value)
            if isinstance(node, ast.Dict) and any(isinstance(k, ast.Constant) and k.value in ('verdict', 'stop')
                                                  for k in node.keys):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value in ('code', 'stop') and isinstance(v, ast.Constant) \
                            and isinstance(v.value, str):
                        seen += 1
                        assert N.is_code(v.value), (fn, v.value)
    for v in ('FORK', 'HINT_AHEAD', 'HEAD_UNSTABLE', 'LINK_MISMATCH', 'HOME_CHANGED', 'GATES_CHANGED',
              'KIT_NOT_VERIFIED', 'CONFIG_CHANGE_NOT_ALLOWED', 'KIT_CHANGE_WITH_RUN_IN_FLIGHT', 'RELEASE_NOT_ACCEPTED',
              'REBASE_LIMIT', 'REBASE_CONFLICT', 'REBASE_PART_APPEARED', 'QUALIFICATION_SERIES_EXISTS',
              'RUNNER_REFUSED', 'FREEZE_INCOMPLETE', 'FROZEN_FOLDER_CHANGED', 'INTERNAL_CHAIN_TOO_LONG',
              'QUALIFICATION_DIVERGED_RESTART_CONFLICT', 'RELEASE_GATE_OPEN'):
        assert N.is_code(v), v
    assert seen >= 10


# ============================================================ v2.1 (delta §1.2, §2.15.5): ct rows
def code_of(state, e):
    try:
        F.apply(state, e)
        return 'OK'
    except F.ChainInvalid as x:
        return x.code


def legal(w, lab):
    return dict(CW.moves(w))[lab]


def two_case_world():
    w = CW.World('Q1', jobs=[['case01', 1, None], ['case02', 2, None]])
    w.commit(CW.genesis(w))
    return w


@test
def test_maint1_new_run_job_dir_must_be_the_layout_path():
    """MAINT-1 (_virtual): a new run whose job_dir is not job_dir_of(genesis base, tag, case) is T14, for T10 (A),
    T11 (A-restart1), T12 (NA-A), T13 (everyday): absolute elsewhere, '..', another run's folder, the ledger, a jobs
    path for a Q run."""
    base = CW.BASE

    def hostile(e):
        c = e['body']['new_run']['case']
        return ['/root/.config/git', base + '/qual/A/../../x', base + '/qual/B/' + c, base + '/ledger',
                base + '/qual/A/other_case', base + '/jobs/A/' + c, e['body']['new_run']['job_dir'] + '/']
    w = two_case_world()
    cases = [(w, legal(w, 'PREPARE_GENERATE')(), 'T10')]
    w11 = q_world()
    drive(w11, 'PREPARE_STOP', 'ACK')
    e11 = [m for m in CW.moves(w11) if m[0] == 'PREPARE_STOP_SOURCE_UNREADABLE'][0][1]()
    e11['body']['restart_eligible'] = False
    cases.append((w11, e11, 'T11'))
    w12 = CW.World('Q1', jobs=[['case01', 1, 'NA_REASON']])
    w12.commit(CW.genesis(w12))
    cases.append((w12, [m for m in CW.moves(w12) if m[0].startswith('NA')][0][1](), 'T12'))
    ew = CW.World('E1')
    ew.commit(CW.genesis(ew))
    drive(ew, 'INPUTS')
    cases.append((ew, legal(ew, 'PREPARE_E')(), 'T13'))
    for cw, e, row in cases:
        assert F.apply_traced(cw.state, e)[1][0] == row, (row, F.apply_traced(cw.state, e)[1])
        for jd in hostile(e):
            bad = copy.deepcopy(e)
            bad['body']['new_run']['job_dir'] = jd
            assert code_of(cw.state, bad) == 'T14', (row, jd)
    other = copy.deepcopy(cases[-1][1])                 # everyday: a layout path, but no INPUTS run of that tag
    nr = other['body']['new_run']
    nr['tag'] = 'E20990101T000000Z'
    nr['job_dir'] = F.job_dir_of(ew.state['genesis']['base'], nr['tag'], nr['case'])
    other['body']['run'] = nr['tag'] + '/' + nr['case']
    assert code_of(ew.state, other) == 'T14'



@test
def test_new_run_while_a_run_is_current_t14():
    """D11a (g10, g12: `s['current'] is None`): with A/case01 ACTIVE, a new run of another case (an attempt: T10's
    rule; a nonattempt: T12's) is T14, although its job folder is the layout path and the case is in the jobs."""
    w = CW.World('Q1', jobs=[['case01', 1, None], ['case02', 2, None], ['case03', 3, 'NA_REASON']])
    w.commit(CW.genesis(w))
    e0 = legal(w, 'PREPARE_GENERATE')()
    drive(w, 'PREPARE_GENERATE')
    assert w.state['current'] == 'A/case01'
    for case, tag in (('case02', 'A'), ('case03', 'NA-A')):
        t = w.entry('HALT', {'code': 'X', 'detail': {}, 'head_seq': 0})
        e = dict(copy.deepcopy(e0), **{f: t[f] for f in ('seq', 'name', 'prev_sha256', 'confirms', 'utc')})
        nr = e['body']['new_run']
        nr.update(case=case, tag=tag, reader=F.reader_of(tag), job_dir=F.job_dir_of(CW.BASE, tag, case))
        e['body']['run'] = tag + '/' + case
        assert code_of(w.state, e) == 'T14', (case, code_of(w.state, e))

@test
def test_maint1_genesis_layout_base_relative():
    """MAINT-1 (t01): the GENESIS layout is layout_of(base) with a plain absolute base (no '.', '..', relative or
    trailing parts), and the conversation-list gate is yes."""
    g = CW.genesis(CW.World('Q1'))
    assert code_of(None, g) == 'OK'
    for mut in (lambda b: b['layout'].update(ledger='/elsewhere/LEDGER.jsonl'),
                lambda b: b['layout'].update(qual=b['layout']['base'] + '/other'),
                lambda b: b['layout'].update(base='/a/../b'), lambda b: b['layout'].update(base='/a/./b'),
                lambda b: b['layout'].update(base='relative/base'), lambda b: b['layout'].update(base='/a/b/'),
                lambda b: b['layout'].pop('runtime'), lambda b: b['gates'].update(p1_conversation_list='no')):
        bad = copy.deepcopy(g)
        mut(bad['body'])
        assert code_of(None, bad) == 'SCHEMA_INVALID', bad['body']['layout']


@test
def test_maint3_clear_with_unchanged_kit_t60():
    """MAINT-3 (g59): a CLEAR whose kit change keeps the kit (from == to) is T60."""
    w = q_world()
    w.commit(w.entry('HALT', {'code': 'UNCLASSIFIED', 'detail': {}, 'head_seq': w.state['seq']}))
    s0 = copy.deepcopy(w.state)
    e = CW._clear(w, w.state['halt'])
    assert code_of(s0, e) == 'OK'
    same = copy.deepcopy(e)
    same['kit_sha256'] = same['body']['kit_sha256'] = same['body']['kit_change']['to_kit_sha256'] = s0['kit_sha256']
    same['body']['kit_change']['to_members'] = same['body']['kit_change']['from_members']
    assert code_of(s0, same) == 'T60'


@test
def test_session_c2_clear_restore_keeps_kit_then_clear_takes_it():
    """SD-51: the RESTORE while HALTED keeps the halted kit and carries no kit_change; the CLEAR then takes the new
    config-only kit (T59) and the state's kit becomes it."""
    cw = q_world()
    cw.commit(cw.entry('HALT', {'code': 'UNCLASSIFIED', 'detail': {}, 'head_seq': cw.state['seq']}))
    st = cw.state
    head = dict(cw.entries[-1], state=st)
    clear = {'series': 'Q1', 'seq': st['seq'], 'code': 'UNCLASSIFIED'}
    kit = {'sha256': CW.KIT2, 'members': [CW.MEMBERS[0], [CW.MEMBERS[1][0], CW.hx('c2')], CW.MEMBERS[2]],
           'release_sha256': CW.REL, 'config': {'gates': cw.gates, 'clear': clear}}
    hk = {'sha256': st['kit_sha256'], 'members': CW.MEMBERS, 'config': {'gates': cw.gates, 'clear': None}}
    code, kc = SE.kit_change(st, kit, hk)
    assert code is None and kc['config_only']
    w = {'operator': {'model': 'm', 'platform': 'p'}, 'kit': kit, 'head': {'entry': head, 'md5': '0' * 32},
         'lookups': [], 'approval': 'none', 'placed': True}
    view_ = {'gates': cw.gates, 'clear': clear, 'now': CW.utc(cw.t + 100), 'series': 'Q1', 'base': CW.BASE}
    ph, step = SE._after_classify(view_, w, head, st, [], kc, {'seq': st['seq'], 'copies': []})
    assert ph == 'COMMIT', (ph, step)
    b = step.entry['body']
    assert b['kit_sha256'] == st['kit_sha256'] and b['kit_change'] is None, b
    complete_restore(cw, Commit({'kind': 'RESTORE', 'body': dict(b, lookups=[])}))
    assert cw.state['phase'] == 'HALTED' and cw.state['kit_sha256'] == CW.KIT
    e = CW._clear(cw, cw.state['halt'])
    assert cw.commit(e) == ['T59'] and cw.state['kit_sha256'] == e['kit_sha256'] != CW.KIT


@test
def test_int_r2_04_consumer_stage_without_consumed_is_t25():
    """INT-R2-04: a chain whose first command is a consumer must name exactly the ARCHIVED unconsumed role of that
    letter in body.consumed; an empty or wrong consumed list is T25."""
    w = q_world()
    drive(w, 'PREPARE_GENERATE', 'AI')
    e = legal(w, 'FINISH')()
    assert code_of(w.state, e) == 'OK'
    for cons in ([], [dict(e['body']['consumed'][0], role='S')], e['body']['consumed'] * 2):
        bad = copy.deepcopy(e)
        bad['body']['consumed'] = copy.deepcopy(cons)
        assert code_of(w.state, bad) == 'T25', cons


@test
def test_d6_entry_approval_must_be_none():
    """D6 (S1): GENESIS and RESTORE record approval, which must be "none"."""
    g = CW.genesis(CW.World('Q1'))
    assert not EN.validate_body('GENESIS', g['body'])
    for v in ('pending', 'yes', None):
        assert EN.validate_body('GENESIS', dict(g['body'], approval=v)), v
        assert code_of(None, dict(g, body=dict(g['body'], approval=v))) == 'SCHEMA_INVALID', v
    r = CW._restore(q_world())
    assert not EN.validate_body('RESTORE', r['body'])
    assert EN.validate_body('RESTORE', dict(r['body'], approval='pending')) == ['body.approval']
    nb = dict(r['body'])
    nb.pop('approval')
    assert EN.validate_body('RESTORE', nb)


@test
def test_d5_cleared_local_only_on_restore_and_genesis():
    """D5 (S1, SD-53): cleared_local is {code, head_seq, kit_sha256} and only on a RESTORE or a GENESIS."""
    w = q_world()
    cl = {'code': 'FORK', 'head_seq': 1, 'kit_sha256': CW.KIT}
    e = legal(w, 'PREPARE_GENERATE')()
    assert not EN.validate_entry(dict(e, cleared_local=None), draft=True)
    assert 'cleared_local' in EN.validate_entry(dict(e, cleared_local=cl), draft=True)
    r = CW._restore(q_world())
    assert not EN.validate_entry(dict(r, cleared_local=cl), draft=True)
    assert 'cleared_local' in EN.validate_entry(dict(r, cleared_local=dict(cl, extra=1)), draft=True)
    g = CW.genesis(CW.World('Q1'))
    assert not EN.validate_entry(dict(g, cleared_local=cl), draft=True)


@test
def test_maint10_jobs_of():
    """MAINT-10 (a): GENESIS body.jobs from a JOBS.json document."""
    doc = {'cases': [{'case_id': 'c1', 'order': 1, 'nonattempt': False},
                     {'case_id': 'c2', 'order': 2, 'nonattempt': True, 'reason': 'R'},
                     {'case_id': 'c3', 'order': 3, 'nonattempt': True}]}
    assert F.jobs_of(doc) == [['c1', 1, None], ['c2', 2, 'R'], ['c3', 3, True]]


def _start_like(lt, e, **kw):
    st = {k: v for k, v in lt.items() if k not in ('seq', 'superseded_by')}
    st.update(utc=e['utc'], boot_id=e['boot_id'], **kw)
    return st


@test
def test_t1_continued_v_other_outcomes_t48():
    """T1 (N06): the fold (not build_item) gets a RESTORE whose item is the CONTINUED V with outcome NOTHING_WRITTEN,
    WRITTEN, UNSURE or NO_CONVERSATION, each with and without a START (and every action the other rows would give):
    all CHAIN_INVALID (T48). The control, outcome CONTINUED with FREEZE_VISUAL_FAILED, is T46."""
    w = q_world()
    drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH', 'AI', 'REVIEW_INCOMPLETE')
    ro = w.state['runs']['A/case01']['roles']['V1']
    assert ro['status'] == 'CONTINUED'
    op = CW.open_role(w.state)
    e = CW._restore(w, resolve=op, ans={'ended': True, 'files_found': False, 'transcript': 'not_available',
                                        'outcome': 'CONTINUED', 'list_shows_none': None})
    assert e['body']['resolutions'][0]['outcome'] == 'CONTINUED'
    lt = F.latest(ro)
    starts = [None, _start_like(lt, e, attempt=2, start_no=1, reason='REPLACEMENT'),
              _start_like(lt, e, start_no=lt['start_no'] + 1, reason='NO_CONVERSATION')]
    tried = 0
    for oc in ('NOTHING_WRITTEN', 'WRITTEN', 'UNSURE', 'NO_CONVERSATION'):
        for start in starts:
            for act in ('FREEZE_VISUAL_FAILED', 'REPLACE', 'SUPERSEDE'):
                for och in (False, True):
                    bad = copy.deepcopy(e)
                    bad['body']['resolutions'][0].update(outcome=oc, action=act, owner_check=och)
                    bad['body']['start'] = copy.deepcopy(start)
                    assert code_of(w.state, bad) == 'T48', (oc, start and start['reason'], act, och,
                                                            code_of(w.state, bad))
                    tried += 1
    assert tried == 72
    assert w.commit(e) == ['T42', 'T46']


def _b_entry(w):
    return w.entry('STAGE', CW.stage_body('B/case01', [CW.cmd('prepare', 'GENERATE')], 'GENERATE',
                                          new_run=CW.new_run('B', 'case01'),
                                          start=CW.start(CW.job_dir('B', 'case01'), 'G', 1, 1, 'STAGE')),
                   members=CW.ledger_members(w.state['seq'] + 1))


@test
def test_t2_reader_b_waits_while_a_owes_restart():
    """T2 (N07, g10): A is FROZEN, restart-eligible, not diverged and not a restart run: a B new run is T14. Controls:
    with RESET_DIVERGED on A, or after A-restart1 is frozen, the same B entry folds as T10."""
    w = q_world()
    drive(w, 'PREPARE_STOP', 'ACK')
    A = w.state['runs']['A/case01']
    assert A['status'] == 'FROZEN' and A['frozen']['restart_eligible'] and not A['flags'] and A['tag'] == 'A'
    assert code_of(w.state, _b_entry(w)) == 'T14'
    s = copy.deepcopy(w.state)
    s['runs']['A/case01']['flags'].append('RESET_DIVERGED')
    assert F.apply_traced(s, _b_entry(w))[1][0] == 'T10'
    e = [m for m in CW.moves(w) if m[0] == 'PREPARE_STOP_SOURCE_UNREADABLE'][0][1]()
    e['body']['restart_eligible'] = False
    w.commit(e)
    drive(w, 'ACK')
    assert w.state['runs']['A-restart1/case01']['status'] == 'FROZEN'
    assert F.apply_traced(w.state, _b_entry(w))[1][0] == 'T10'


@test
def test_t3_recheck_second_writer_at_n2_n3_forks():
    """T3 (N18, the step-6 RECHECK): after the RESTORE commit at N+1 (ours, by its recorded id), a copy at N+2 or N+3
    is a second writer: FORK. Without them the re-check is DONE; N+1 absent is FORK."""
    st = q_world().state
    N_, c0 = 4, CW.T0 + 1000
    com = {'seq': N_ + 1, 'utc': CW.utc(c0), 'sha256': 'a' * 64, 'ids': ['IDOURS0000000000000000'], 'md5': 'b' * 32,
           'bytes': 5}
    view_ = {'now': CW.utc(c0 + 500), 'gates': CW.GATES, 'series': 'Q1', 'base': CW.BASE}

    def recheck(present):
        lk = [{'name': N.entry_name('Q1', N_ + k), 'utc': CW.utc(c0 + 400), 'post': True,
               'result': 'present' if k in present else 'absent',
               'copies': [[com['ids'][0], 5]] if k == 1 else [['IDOTHER%015d' % k, 5]] if k in present else []}
              for k in (1, 2, 3)]
        return SE._commit({'committed': com, 'lookups': lk}, st, {}, {'seq': N_, 'copies': []}, view_)
    assert recheck({1}) == ('DONE', None)
    for present in ({1, 2}, {1, 3}, {1, 2, 3}, {2}, set()):
        assert recheck(present) == ('RECHECK', Stop('FORK', 'C')), present


@test
def test_t3_recheck_forks_2015773_form():
    """T3 (N18, GAP-4) in a form that also runs at 2015773: head_search's verdict carries `via` (2015773 re-checked
    only a non-hint head, copies were [id, md5, size]) and the re-check FINDs are later than the commit by W_abs.
    N+2 or N+3 present is FORK. Its 2015773 runs are recorded in INTEGRATION.json reviewer_proof_table."""
    import inspect
    cp = (lambda i: [i, 'b' * 32, 5]) if 'md5' in inspect.signature(SE.rule_v).parameters else (lambda i: [i, 5])
    st = q_world().state
    N_, c0, wa = 4, CW.T0 + 1000, F.w_abs(CW.GATES)
    com = {'seq': N_ + 1, 'utc': CW.utc(c0), 'sha256': 'a' * 64, 'ids': ['IDOURS0000000000000000'], 'md5': 'b' * 32,
           'bytes': 5}
    view_ = {'now': CW.utc(c0 + wa + 200), 'gates': CW.GATES, 'series': 'Q1', 'base': CW.BASE}

    def recheck(present):
        lk = [{'name': N.entry_name('Q1', N_ + k), 'utc': CW.utc(c0 + wa + 100), 'post': True,
               'result': 'present' if k in present else 'absent',
               'copies': [cp(com['ids'][0])] if k == 1 else [cp('IDOTHER%015d' % k)] if k in present else []}
              for k in (1, 2, 3)]
        return SE._commit({'committed': com, 'lookups': lk}, st, {}, {'seq': N_, 'copies': [], 'via': 'gallop'}, view_)
    assert recheck({1}) == ('DONE', None)
    for present in ({1, 2}, {1, 3}, {1, 2, 3}):
        assert recheck(present) == ('RECHECK', Stop('FORK', 'C')), present


@test
def test_t4_continued_v_answer_of_another_boot_t39():
    """T4 (N05, g38): the continued V's AI entry (revision 2) from a boot other than continued_boot is T39."""
    w = q_world()
    drive(w, 'PREPARE_GENERATE', 'AI', 'FINISH', 'AI', 'REVIEW_INCOMPLETE')
    e = legal(w, 'AI_CONT')()
    assert F.apply_traced(w.state, e)[1] == ['T38']
    bad = copy.deepcopy(e)
    bad['boot_id'] = CW.boot(7)
    assert code_of(w.state, bad) == 'T39'


@test
def test_t4_ai_start_boot_must_be_the_start_boot_t39():
    """T4 (N04, g37): an AI entry whose start_boot_id equals its own boot but not the START's boot is T39."""
    w = q_world()
    drive(w, 'PREPARE_GENERATE')
    e = legal(w, 'AI')()
    assert F.apply_traced(w.state, e)[1] == ['T37']
    bad = copy.deepcopy(e)
    bad['boot_id'] = bad['body']['start_boot_id'] = CW.boot(7)
    assert code_of(w.state, bad) == 'T39'


@test
def test_t5_restart_after_in_place_interrupt_t14():
    """T5 (N52, g11): a run frozen restart-eligible but with an in-place interrupt gets no A-restart1 (T14)."""
    w = q_world()
    drive(w, 'PREPARE_STOP', 'ACK')
    e = [m for m in CW.moves(w) if m[0] == 'PREPARE_STOP_SOURCE_UNREADABLE'][0][1]()
    e['body']['restart_eligible'] = False
    assert F.apply_traced(w.state, e)[1][0] == 'T11'
    s = copy.deepcopy(w.state)
    s['runs']['A/case01']['interrupts'] = [{'seq': 2, 'role': 'G1'}]
    assert code_of(s, e) == 'T14'


@test
def test_t10_config_only_change_of_other_key_release_not_accepted():
    """T10 (N50, S5): a config-only kit change whose changed keys leave CHANGEABLE_KEYS is RELEASE_NOT_ACCEPTED."""
    w = q_world()
    w.commit(w.entry('HALT', {'code': 'UNCLASSIFIED', 'detail': {}, 'head_seq': w.state['seq']}))
    s0 = copy.deepcopy(w.state)
    e = CW._clear(w, w.state['halt'])
    assert code_of(s0, e) == 'OK' and e['body']['kit_change']['config_only']
    for keys in (['series'], ['gates'], ['clear', 'drive_id_re'], ['accepted_helper_tree_sha256']):
        bad = copy.deepcopy(e)
        bad['body']['kit_change']['config_keys_changed'] = keys
        assert code_of(s0, bad) == 'RELEASE_NOT_ACCEPTED', keys


@test
def test_v21_entry_and_fold_edges():
    """v2.1 S1 and row edges: an AI revision 1 without tools_present, a RESTORE placed item with a bad aside, a
    resolution whose conversation is not a string; a consumed item whose tree is not the archive's (T25); an item whose
    forced value is not the fold's (T48); an everyday STAGE for a run with no INPUTS (T14); C5 for a head without a
    START; the tool list format (names.tool_list)."""
    w = q_world()
    drive(w, 'PREPARE_GENERATE')
    ai = legal(w, 'AI')()
    b = copy.deepcopy(ai['body'])
    b['attested'].pop('tools_present')
    assert 'attested.tools_present' in EN.validate_body('AI', b)
    b['attested']['tools_present'] = {'source': 'none', 'sha256': CW.hx('x')}
    assert 'attested.tools_present' in EN.validate_body('AI', b)
    r = CW._restore(q_world())
    assert 'placed: aside' in EN.validate_body('RESTORE', dict(r['body'], placed=[
        {'what': 'job', 'path': '/x', 'tree_sha256': CW.hx('t'), 'aside': 5}]))
    w.commit(ai)
    fin = legal(w, 'FINISH')()
    bad = copy.deepcopy(fin)
    bad['body']['consumed'][0]['tree_sha256'] = CW.hx('other')
    assert code_of(w.state, bad) == 'T25'
    w2 = q_world()
    drive(w2, 'PREPARE_GENERATE')
    e = CW._restore(w2, resolve=CW.open_role(w2.state), ans={'ended': True, 'files_found': False,
                                                            'transcript': 'not_available', 'outcome': 'WRITTEN',
                                                            'list_shows_none': None})
    assert 'resolution: conversation' in EN.validate_body('RESTORE', dict(e['body'], resolutions=[
        dict(e['body']['resolutions'][0], conversation=7)]))
    bad = copy.deepcopy(e)
    bad['body']['resolutions'][0]['forced'] = 'NOT_ENDED'
    assert code_of(w2.state, bad) == 'T48'
    ew = CW.World('E1')
    ew.commit(CW.genesis(ew))
    drive(ew, 'INPUTS')
    pe = legal(ew, 'PREPARE_E')()
    bad = copy.deepcopy(pe)
    tag = 'E20991231T000000Z'
    bad['body']['run'] = tag + '/' + bad['body']['new_run']['case']
    bad['body']['new_run'].update(tag=tag, job_dir=F.job_dir_of(CW.BASE, tag, bad['body']['new_run']['case']))
    assert code_of(ew.state, bad) == 'T14'
    w3 = q_world()
    st = copy.deepcopy(w3.state)
    h = dict(w3.entries[-1], kind='STAGE', body={'start': None, 'run': 'A/case01'})
    assert SE.classify(h, st, ['p1'], None, True, CW.GATES) == ('C5', {'rebase': True})
    assert N.tool_list(b'a\nb\n') == ['a', 'b'] and N.tool_list(b'a') is None and N.tool_list(b'\xff\n') is None
    assert N.tool_list(b'a\na\n') is None and N.tool_list(('x' * 201 + '\n').encode()) is None



def _steps(cw, wk, answers=None, files_found=False):
    """run_session, also returning every (phase, step) that session_next gave on the way."""
    seen, orig = [], SE.session_next

    def rec(v):
        r = orig(v)
        seen.append(r)
        return r
    SE.session_next = rec
    try:
        ph, st, wk = run_session(cw, wk, answers, files_found)
    finally:
        SE.session_next = orig
    return ph, st, wk, seen


def _asks(seen, action):
    return [st for _, st in seen if isinstance(st, Ask) and st.context['action'] == action]


@test
def test_d11_session_guard_cases():
    """D11a (session_next, _after_classify, _resolve): HOME_CHANGED only with a run in flight; a clearing restore
    accepts a config-only kit change; C5 without a START asks no list question; a non-C2 restore records its kit
    change; END and EXPORT name the archived conversation only for a CONTINUED V; the RESTORE_ROLE question carries
    `after` exactly when it asks list_shows_none or conversation."""
    cw = q_world()                                                     # GENESIS only: nothing in flight
    wk = work(hint={'seq': cw.state['seq'], 'kit': None}, identity={'home': '/home/other', 'uid': 1})
    wk['kit']['config']['gates'] = cw.gates
    assert run_session(cw, wk)[0] != 'IDENTITY'
    cfg = [m[:] for m in CW.MEMBERS]
    cfg[1][1] = CW.hx('c2')
    for cleared in (None, {'code': 'SETUP_FAILED', 'head_seq': cw.state['seq'], 'kit_sha256': CW.KIT}):
        wk = work(hint={'seq': cw.state['seq'], 'kit': None}, cleared_local=cleared)
        wk['kit'] = {'sha256': CW.KIT2, 'members': cfg, 'release_sha256': CW.REL, 'config': {'gates': cw.gates}}
        ph, st, _ = run_session(copy.deepcopy(cw), wk)
        assert ph == 'COMMIT' and st.entry['body']['kit_change']['config_only'] is True, (cleared, ph, st)
    c8 = q_world()
    drive(c8, 'PREPARE_GENERATE', 'AI')                                # C8: a run in flight, no open role
    wk = work(hint={'seq': c8.state['seq'], 'kit': None})
    wk['kit'] = {'sha256': CW.KIT2, 'members': cfg, 'release_sha256': CW.REL, 'config': {'gates': c8.gates}}
    ph, st, _ = run_session(c8, wk)
    assert ph == 'COMMIT' and st.entry['body']['kit_change'] is not None and st.entry['body']['kit_sha256'] == CW.KIT2
    rb = _rebase_world()
    rb.entries[-1] = copy.deepcopy(rb.entries[-1])
    rb.entries[-1]['body']['start'] = None                             # C5 without a START: no list question
    wk = work()
    wk['kit']['config']['gates'] = rb.gates
    wk['_deleted'] = [rb.entries[-1]['parts'][0]['name']]
    ph, st, _, seen = _steps(rb, wk)
    assert ph == 'COMMIT' and not _asks(seen, 'LIST_SHOWS_NONE'), (ph, st)
    assert st.entry['body']['rebase']['list_shows_none'] is None
    wk = work(list_shows_none=False)                                   # a stale no is never a conflict without a START
    wk['kit']['config']['gates'] = rb.gates
    wk['_deleted'] = [rb.entries[-1]['parts'][0]['name']]
    assert run_session(copy.deepcopy(rb), wk)[0] == 'COMMIT'
    cv = q_world()
    drive(cv, 'PREPARE_GENERATE', 'AI', 'FINISH', 'AI', 'REVIEW_INCOMPLETE')
    V = cv.state['runs']['A/case01']['roles']['V1']
    wk = work(hint={'seq': cv.state['seq'], 'kit': None})
    wk['kit']['config']['gates'] = cv.gates
    ph, st, _, seen = _steps(cv, wk, {'ended': 'yes', 'outcome': 'CONTINUED', 'transcript': 'not_available'})
    dos = {s.do[0]: s.do[1] for _, s in seen if isinstance(s, PrintBlock) and s.do and s.do[0] in (
        'END_CONVERSATION', 'EXPORT_TRANSCRIPT')}
    assert dos['END_CONVERSATION']['conversation'] == V['archives'][0]['conversation'] == \
        dos['EXPORT_TRANSCRIPT']['conversation'], dos
    assert 'after' not in _asks(seen, 'RESTORE_ROLE')[0].context            # neither list nor conversation asked
    cg = q_world()
    drive(cg, 'PREPARE_GENERATE')                                      # an open G: list and conversation asked
    for ff, after in ((False, True), (True, False)):
        wk = work(hint={'seq': cg.state['seq'], 'kit': None})
        wk['kit']['config']['gates'] = cg.gates
        ans = {'ended': 'yes', 'outcome': 'NOTHING_WRITTEN', 'transcript': 'exported', 'list_shows_none': 'no'}
        ph, st, _, seen = _steps(copy.deepcopy(cg), wk, ans, files_found=ff)
        dos = {s.do[0]: s.do[1] for _, s in seen if isinstance(s, PrintBlock) and s.do and s.do[0] in (
            'END_CONVERSATION', 'EXPORT_TRANSCRIPT')}
        assert 'conversation' not in dos['END_CONVERSATION'] and 'conversation' not in dos['EXPORT_TRANSCRIPT'], dos
        assert ('after' in _asks(seen, 'RESTORE_ROLE')[0].context) is after, ff
    ch = q_world()                                                     # C2 with an open role: it is resolved
    drive(ch, 'PREPARE_GENERATE')
    ch.commit(ch.entry('HALT', {'code': 'UNCLASSIFIED', 'detail': {}, 'head_seq': ch.state['seq']}))
    st2 = ch.state
    head = dict(ch.entries[-1], state=st2)
    wc = {'operator': {'model': 'm', 'platform': 'p'}, 'kit': work()['kit'], 'head': {'entry': head, 'md5': '0' * 32},
          'lookups': [], 'approval': 'none', 'placed': True}
    vw = {'gates': ch.gates, 'clear': {'series': 'Q1', 'seq': st2['halt']['seq'], 'code': 'UNCLASSIFIED'},
          'now': CW.utc(ch.t + 100), 'series': 'Q1', 'base': CW.BASE}
    ph, step = SE._after_classify(vw, wc, head, st2, [], None, {'seq': st2['seq'], 'copies': []})
    assert ph.startswith('RESOLVE'), (ph, step)
    rs = q_world()
    drive(rs, 'PREPARE_GENERATE')
    e = CW._restore(rs, resolve=CW.open_role(rs.state), ans={'ended': True, 'files_found': False,
                    'transcript': 'not_available', 'outcome': 'NO_CONVERSATION', 'list_shows_none': True})
    rs.commit(e)                                                       # superseded once: no list question
    ro = rs.state['runs']['A/case01']['roles']['G1']
    assert ro['status'] == 'STARTED' and ro['supersedes'] == 1, ro
    wk = work(hint={'seq': rs.state['seq'], 'kit': None})
    wk['kit']['config']['gates'] = rs.gates
    ans = {'ended': 'yes', 'outcome': 'NOTHING_WRITTEN', 'transcript': 'exported'}
    ph, st, _, seen = _steps(rs, wk, ans)
    a = _asks(seen, 'RESTORE_ROLE')[0]
    assert 'list_shows_none' not in a.keys and 'conversation' in a.keys and 'after' in a.context, a



@test
def test_d11_fold_structural_and_genesis_cases():
    """D11a (structural, t01): a GENESIS whose seq is not 1 on an empty series is SEQ_GAP; a GENESIS whose base is
    relative, has a space, or has a '.' or '..' segment is SCHEMA_INVALID even when its layout is that base's layout;
    so is one whose jobs or other_series_absent do not fit its series letter."""
    for ser in ('Q1', 'E1'):
        w = CW.World(ser, jobs=[['case01', 1, None]])
        g = CW.genesis(w)
        assert code_of(None, g) == 'OK'
        g2 = copy.deepcopy(g)
        g2['seq'], g2['prev_sha256'], g2['name'] = 2, CW.hx('p'), N.entry_name(ser, 2)
        assert code_of(None, g2) == 'SEQ_GAP'
        for bad in ('rel/x', '/a b', '/a/../b', '/a/./b'):
            g2 = copy.deepcopy(g)
            g2['body']['layout'] = F.layout_of(bad)
            assert code_of(None, g2) == 'SCHEMA_INVALID', (ser, bad)
    for ser, key, v in (('Q1', 'jobs', None), ('D1', 'jobs', None), ('E1', 'jobs', [['case01', 1, None]]),
                        ('Q1', 'other_series_absent', None), ('D1', 'other_series_absent', []),
                        ('E1', 'other_series_absent', [])):       # jobs iff Q or D; other_series_absent iff Q
        g2 = copy.deepcopy(CW.genesis(CW.World(ser, jobs=[['case01', 1, None]])))
        g2['body'][key] = v
        assert code_of(None, g2) == 'SCHEMA_INVALID', (ser, key, v)


@test
def test_d11_final_ready_nonattempt_restart_flag():
    """D11a (final_ready): a nonattempt job's frozen chains never owe a restart, whatever restart_eligible says; an
    attempt run that is eligible and not a restart does owe one."""
    w = CW.World('Q1', jobs=[['case01', 1, 'NA_REASON']])
    w.commit(CW.genesis(w))
    drive(w, 'NA', 'NA')
    s = copy.deepcopy(w.state)
    assert F.final_ready(s)
    for R in s['runs'].values():
        R['frozen']['restart_eligible'] = True
    assert F.final_ready(s)
    s['genesis']['jobs'][0][2] = None                  # the same runs as an attempt job: a restart is owed
    assert not F.final_ready(s)

def _cr(mode='qualification', status='ACTIVE', delivery=None, cur='A/c'):
    return {'mode': mode, 'current': cur, 'order': ['A/c'] if cur else [], 'runs': {'A/c': {'status': status, 'delivery': delivery, 'reprepares': 0,
                                                          'roles': {}}} if cur else {}}


@test
def test_d11_classify_rest_rows():
    """D11a (_classify_rest): C7 only for an everyday ACTIVE run whose personal copy is prepared and not yet sent;
    C8b only for an everyday INPUTS run; each conjunct alone."""
    prep = {'prepared_seq': 5, 'sent': False}
    assert SE._classify_rest(_cr('everyday', delivery=prep))[0] == 'C7'
    assert SE._classify_rest(_cr('qualification', delivery=prep))[0] == 'C8'
    assert SE._classify_rest(_cr('everyday', delivery=dict(prep, sent=True)))[0] == 'C8'
    assert SE._classify_rest(_cr('everyday', status='INPUTS', delivery=prep))[0] == 'C8b'
    assert SE._classify_rest(_cr('everyday', status='INPUTS'))[0] == 'C8b'
    assert SE._classify_rest(_cr('qualification', status='INPUTS'))[0] == 'C10'
    assert SE._classify_rest(_cr('everyday', status='FROZEN'))[0] == 'C10'
    assert SE._classify_rest(_cr(cur=None))[0] == 'C9'


HEAD_ORDER = {1: [1, 2, 3, 5, 9, 17, 13, 15, 14, 14], None: [1, 2, 3, 5, 9, 17, 13, 15, 14, 14]}   # gallop, then bisect


@test
def test_d11_head_search_lookup_order():
    """D11a (head_search): the gallop doubles from the hint and the bisection halves; the exact sequence of FIND
    names for a head at 13 from hint 1 and from no hint (a mutant of either loop asks other names)."""
    def names(N, hint):
        lk, t, asked = [], CW.T0, []
        for _ in range(200):
            r = SE.head_search('Q1', hint, lk, CW.GATES, CW.utc(t))
            if 'verdict' in r:
                return r, asked
            if r['need'] == 'wait':
                t += r['seconds']
                continue
            k = int(r['name'].split('_')[-1].split('.')[0])
            asked.append(k)
            lk.append({'name': r['name'], 'result': 'present' if k <= N else 'absent',
                       'copies': [['ID%d' % k, 100]] if k <= N else [], 'utc': CW.utc(t)})
            t += 5
        raise AssertionError('no verdict')
    for hint in (1, None):
        r, asked = names(13, hint)
        assert r['verdict'] == 'head' and r['seq'] == 13, r
        assert asked == HEAD_ORDER[hint], (hint, asked)


# ============================================================ D11a: direct guard tests (delta v2.1 §2.15.3)
# key: a fold TABLE row, a core/session.py function with a guard site, or a commit/restore glue function (§2.15.2);
# value: the tests that feed it the case its guard decides. Lint L15 checks the keys and that every test exists; the
# generated guard mutants are the measure (tests/mutants.py).
_ENUM = ['test_enumeration_rows_match_spec', 'test_enumeration_golden']
GUARD_TESTS = dict({r: list(_ENUM) for r in ('T01', 'T02', 'T03', 'T04', 'T05', 'T06', 'T12', 'T13', 'T15', 'T16',
                                             'T20', 'T21', 'T22', 'T23', 'T24', 'T30', 'T31', 'T32', 'T41', 'T43',
                                             'T44', 'T45', 'T47', 'T49', 'T50', 'T52', 'T53', 'T55', 'T56', 'T58',
                                             'T62', 'T63')}, **{
    'T10': ['test_t2_reader_b_waits_while_a_owes_restart', 'test_t10_reader_b_needs_a_frozen'],
    'T11': ['test_t5_restart_after_in_place_interrupt_t14', 'test_imp06_restart_run_frozen_at_prepare_stop_reaches_final'],
    'T14': ['test_maint1_new_run_job_dir_must_be_the_layout_path', 'test_t2_reader_b_waits_while_a_owes_restart'],
    'T25': ['test_int_r2_04_consumer_stage_without_consumed_is_t25'],
    'T37': ['test_t4_ai_start_boot_must_be_the_start_boot_t39'], 'T38': ['test_t4_continued_v_answer_of_another_boot_t39'],
    'T39': ['test_t4_ai_start_boot_must_be_the_start_boot_t39', 'test_t4_continued_v_answer_of_another_boot_t39'],
    'T42': ['test_t1_continued_v_other_outcomes_t48', 'test_int_r2_03_restore_conversation_recorded'],
    'T46': ['test_t1_continued_v_other_outcomes_t48'], 'T48': ['test_t1_continued_v_other_outcomes_t48'],
    'T59': ['test_maint3_clear_with_unchanged_kit_t60', 'test_session_c2_clear_restore_keeps_kit_then_clear_takes_it',
            'test_t10_config_only_change_of_other_key_release_not_accepted'],
    'T60': ['test_maint3_clear_with_unchanged_kit_t60'],
    # core/session.py
    '_after_classify': ['test_classify_rows', 'test_session_c2_clear_restore_keeps_kit_then_clear_takes_it',
                        'test_session_c5b_after_rebase_restore', 'test_session_c2_clear_rebase_conflict_head_error'],
    '_classify_rest': ['test_classify_c7_before_c8_and_c8b', 'test_gap13_c8b_after_second_restore_abandons'],
    '_commit': ['test_t3_recheck_second_writer_at_n2_n3_forks', 'test_op05_recheck_after_every_q_restore'],
    '_facts': ['test_d3_head_search_ignores_void_lookups'], '_fresh': ['test_session_fresh_q_genesis_and_series_exists'],
    '_place_commit': ['test_session_restore_drafts_fold_over_generated_states'],
    '_resolve': ['test_session_restore_open_role_draft_folds', 'test_int_r2_03_restore_conversation_recorded'],
    '_search_step': ['test_head_search_wait_between_absences'], '_status': ['test_head_search_paths'],
    'absent_twice': ['test_int05_single_part_absence_is_not_missing'],
    'build_item': ['test_int_r2_03_restore_conversation_recorded'],
    'classify': ['test_classify_rows', 'test_session_branches'],
    'clear_ok': ['test_d5_clear_verdict_exact_clear_and_config_only'],
    'clear_verdict': ['test_d5_clear_verdict_exact_clear_and_config_only'],
    'config_only_ok': ['test_kit_change_rules', 'test_d5_clear_verdict_exact_clear_and_config_only'],
    'head_search': ['test_head_search_paths', 'test_head_search_unstable_and_hint_ahead'],
    'kit_change': ['test_kit_change_rules', 'test_session_branches', 'test_d5_clearing_restore_refuses_release_change'],
    'place_plan': ['test_session_restore_drafts_fold_over_generated_states'],
    'pre_commit': ['test_session_rebase_and_recheck_fork'], 'present_copies': ['test_d3_head_search_ignores_void_lookups'],
    'restore_keys': ['test_session_restore_open_role_draft_folds'], 'rule_v': ['test_session_branches'],
    'session_next': ['test_d6_approval_asked_before_restore_and_genesis', 'test_d6_approval_before_head',
                     'test_session_link_identity_kit', 'test_d5_clearing_restore_refuses_release_change'],
    # glue (savepoint, cli, place, drive)
    'block': ['t_op02_reprint_has_no_upload_lines', 't_commit_bounded_reupload'],
    'on_found': ['t_d11_on_found_handback_and_absent', 't_commit_refused_upload_find_before_reupload', 't_commit_rebase_absence_third_check'],
    'on_verify': ['t_s03_short_download_refinds_real_fork_keeps_bytes', 't_commit_identical_parts_confirmed'],
    'finish': ['t_t6_finish_refuses_entry_that_is_not_pending'], 'slip': ['t_d3_fourth_slip_stops_slip_limit'],
    'go_checks': ['t_d11_local_download_checked_at_go', 't_t8_session_download_missing_refinds', 't_cli_md5_hidden_download_back'],
    'do_found': ['t_d11_head_download_slips_and_no_block', 'test_stale_at_refused', 't_d11_found_raw_path_rules', 't_d4_raw_invalid_reasked', 't_op03_raw_file_consumed', 't_cli_idle_reprint_and_refusals'],
    'do_answer': ['t_d11_head_download_slips_and_no_block', 'test_stale_at_refused', 't_cli_idle_reprint_and_refusals', 't_d3_refused_count_resets_per_block'],
    'session_slip': ['t_d11_session_slip_voids_only_its_name', 't_t8_session_download_missing_refinds'],
    'session_downloads': ['t_d11_session_download_names_kept', 't_d11_head_download_slips_and_no_block', 't_d11_link_copy_download_keeps_the_head', 't_t8_session_download_missing_refinds'],
    'clear_check': ['t_d11_clear_check_routes_found_only_to_its_find', 't_d5_refused_clear_kit_keeps_cache', 't_d5_clear_check_found_accepted', 't_d5_clear_check_bounded',
                    't_d5_damaged_halt_stops_unclassified', 't_d5_found_answer_while_halted_print_stop'],
    'stop_block': ['t_d3_refusals_bounded_then_slip_limit', 't_opx07_stage_death_stop_names_real_head_and_kit',
                   't_d11_stop_block_sticky_only_for_handback_c'],
    'settle': ['t_d5_placement_accepts_equal_or_moves_aside', 't_d16_settle_moves_readonly_target_aside',
               't_d5_settle_root_mode_link_and_file_targets'],
    'parse_raw': ['t_d4_parse_raw_rules', 't_d4_found_raw_search_and_listing_objects',
                  't_d4_swapped_elements_assigned_by_title', 't_d11_parse_raw_edges']})
for _k in GUARD_TESTS:                     # every fold row: the broad goldens and the reviewed direct cases
    if re.fullmatch(r'T[0-9]{2}', _k):
        GUARD_TESTS[_k] += ['test_guard_perturbations_golden', 'test_guard_rows_golden', 'test_d11_fold_guard_witnesses']
GUARD_TESTS['T01'].append('test_d11_fold_structural_and_genesis_cases')
GUARD_TESTS['T62'].append('test_d11_final_ready_nonattempt_restart_flag')
for _k, _t in (('session_next', 'test_d11_session_guard_cases'), ('_after_classify', 'test_d11_session_guard_cases'),
               ('_resolve', 'test_d11_session_guard_cases'), ('_classify_rest', 'test_d11_classify_rest_rows'),
               ('head_search', 'test_d11_head_search_lookup_order')):
    GUARD_TESTS[_k] = GUARD_TESTS[_k] + [_t, 'test_session_functions_golden']
# The glue functions also take the 15 fastest vio and codes tests that call them (tests/glue_callers.json, all callers
# fastest first, from sys.setprofile over one run of both suites): the cap keeps a glue guard pass under 50 minutes.
with open(os.path.join(HERE, 'glue_callers.json')) as _f:
    for _k, _v in json.load(_f).items():
        GUARD_TESTS[_k] = GUARD_TESTS.get(_k, []) + [t for t in _v if t not in GUARD_TESTS.get(_k, [])][:15]


def _alarm(*a):
    raise TimeoutError('the test ran past its alarm (a loop that never ends)')


signal.signal(signal.SIGALRM, _alarm)
SLOW = (test_guard_perturbations_golden, test_guard_rows_golden, test_session_functions_golden)


def run(only=None):
    passed, failed = 0, []
    for fn in sorted(TESTS, key=lambda f: f in SLOW):    # the two broad goldens last
        if only and fn.__name__ not in only:
            continue
        if failed and os.environ.get('CPSVM2_FAILFAST'):     # run_tests.py --failfast (the mutation harness)
            break
        signal.alarm(600 if fn in SLOW else 60)   # a guard mutant can loop for ever: that test fails (D11)
        try:
            fn()
            passed += 1
        except Exception as x:                                            # noqa: BLE001 - the report names it
            failed.append({'test': fn.__name__, 'error': '%s: %s' % (type(x).__name__, str(x)[:600]),
                           'trace': traceback.format_exc()[-1500:]})
        finally:
            signal.alarm(0)
    return {'name': 'test_core_table', 'tests': passed + len(failed), 'passed': passed,
            'failed': [f['test'] for f in failed], 'detail': failed,
            'counts': {'abstract_states': len(ENUM.get('reps', {})), 'golden_entries': len(ENUM.get('golden', {})),
                       'rows_hit': len(ENUM.get('hits', set()) & set(F.ROWS)), 'rows': len(F.ROWS)}}


if __name__ == '__main__':
    r = run([a for a in sys.argv[1:] if not a.startswith('--')] or None)
    print(json.dumps(r, indent=1))
    sys.exit(0 if not r['failed'] else 1)
