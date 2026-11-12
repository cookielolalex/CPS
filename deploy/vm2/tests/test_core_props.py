"""§14.1 property tests: random legal entry sequences (core_world's generator, written from the row texts) with
injected illegal entries; the §4.7 invariants after every apply; fold determinism; apply never mutates its input;
random cuts followed by a RESTORE (F2, TST-01: no attempt ever gets a second START except through T31 or T43, at most
once, and a new attempt only through T30 in place, T44 everyday or T45). Fixed seeds; stdlib only."""
import copy
import multiprocessing
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core_world as CW                                              # noqa: E402
from cpsvm2.core import fold as F                                    # noqa: E402
from cpsvm2.core.names import cjson                                  # noqa: E402

N_SEQUENCES = 2000
MAX_LEN = 200
CUT_EVERY = 10          # random cuts at every index for every 10th sequence


def check_starts(s):
    """F2/TST-01 on a state: per attempt at most one superseding START (T31 REBASE or T43 NO_CONVERSATION); a second
    attempt only by T30 in place (G2 after an INTERRUPT), T44 everyday (EVERYDAY_RETRY) or T45 (REPLACEMENT)."""
    for k, R in s['runs'].items():
        for rk, ro in R['roles'].items():
            reasons = [x['reason'] for x in ro['starts']]
            assert len(reasons) <= 2, 'TST-01 %s %s' % (k, rk)
            if len(reasons) == 2:
                assert reasons[1] in ('REBASE', 'NO_CONVERSATION'), 'TST-01 second START %s' % reasons
            if ro['attempt'] >= 2:
                first = reasons[0]
                if first in ('STAGE', 'REBASE'):
                    assert ro['role'] == 'G' and ro['attempt'] == 2 and (R['interrupts'] or first == 'REBASE'), \
                        'T30 in place only %s %s' % (k, rk)
                else:
                    assert (first, ro['role']) in (('EVERYDAY_RETRY', 'S'), ('EVERYDAY_RETRY', 'G'),
                                                   ('REPLACEMENT', 'V')), 'new attempt %s %s' % (k, rk)
                    if first == 'EVERYDAY_RETRY':
                        assert s['mode'] == 'everyday'


MUTATIONS = ('seq_gap', 'series', 'confirms', 'release', 'runner', 'body_key', 'kind', 'genesis_again', 'ack_wrong',
             'final_early', 'ai_unknown_role', 'start_reason', 'restore_drop_items', 'restore_wrong_action')


def mutate(w, rng, e):
    """An illegal variant of a legal entry `e` for w.state (or None when the mutation does not apply here)."""
    s = w.state
    m = rng.choice(MUTATIONS)
    e = copy.deepcopy(e)
    if m == 'seq_gap':
        e['seq'] += 1
        e['name'] = CW.entry_name(e['series'], e['seq'])
        e['prev_sha256'] = e['prev_sha256'] or CW.hx('x')
        e['confirms'] = e['confirms'] or [{'name': 'x', 'copies': []}]
    elif m == 'series' and s is not None:
        e['series'] = 'Q9' if e['series'] != 'Q9' else 'Q8'
        e['name'] = CW.entry_name(e['series'], e['seq'])
    elif m == 'confirms' and s is not None:
        e['confirms'] = e['confirms'][:-1] if len(e['confirms']) > 1 else [dict(e['confirms'][0], copies=[])]
    elif m == 'release' and s is not None:
        e['release_sha256'] = CW.hx('foreign release')
    elif m == 'runner':
        e['runner_sha256'] = CW.hx('other runner')
    elif m == 'body_key' and isinstance(e['body'], dict) and e['body']:
        e['body'].pop(rng.choice(sorted(e['body'])))
    elif m == 'kind':
        e['kind'] = rng.choice([k for k in ('STAGE', 'AI', 'ACK', 'FINAL', 'CLEAR') if k != e['kind']])
    elif m == 'genesis_again' and s is not None:
        g = CW.genesis(w)
        g.update(seq=e['seq'], name=e['name'], prev_sha256=e['prev_sha256'], confirms=e['confirms'])
        return g
    elif m == 'ack_wrong' and s is not None:
        return w.entry('ACK', {'for_seq': s['seq'] + 7, 'what': 'NOTIFY_OWNER', 'answer': {'notified': 'yes'}})
    elif m == 'final_early' and s is not None and not CW._final_ready(s):
        return w.entry('FINAL', {'all_frozen_sha256': CW.hx('a'), 'ledger_final_sha256': CW.hx('l'), 'runs': 0,
                                 'outcomes_sha256': CW.hx('o')}, parts=[('LEDGER', 1), ('ALLFZ', 1)])
    elif m == 'ai_unknown_role' and s is not None and s['current']:
        return w.entry('AI', {'run': s['current'], 'role': 'S', 'attempt': 9, 'revision': 1, 'start_no': 1,
                              'start_boot_id': w.boot, 'ended': True, 'conversation': 'c', 'attested': {},
                              'tree_sha256': CW.hx('t'), 'files': [], 'transcript': None,
                              'final_message_sha256': None})
    elif m == 'start_reason' and e['kind'] == 'STAGE' and e['body'].get('start'):
        e['body']['start']['reason'] = rng.choice(['NO_CONVERSATION', 'REPLACEMENT', 'EVERYDAY_RETRY'])
    elif m == 'restore_drop_items' and e['kind'] == 'RESTORE' and e['body']['resolutions']:
        e['body']['resolutions'] = []
        e['body']['start'] = None
    elif m == 'restore_wrong_action' and e['kind'] == 'RESTORE' and e['body']['resolutions']:
        it = e['body']['resolutions'][0]
        it['action'] = rng.choice([a for a in ('INTERRUPT', 'FREEZE_LOST', 'REPLACE', 'FREEZE_VISUAL_FAILED',
                                               'SUPERSEDE', 'EVERYDAY_RETRY', 'FREEZE_EXHAUSTED') if a != it['action']])
    else:
        return None
    return e


def pick(rng, mv):
    weights = [0.12 if lab.startswith(('RESTORE', 'HALT')) else 1.0 for lab, _ in mv]
    return rng.choices(mv, weights)[0]


def new_world(seed):
    rng = random.Random(seed)
    series = rng.choice(['Q1', 'Q1', 'D2', 'E1'])
    gates = {'p1_conversation_list': 'yes', 'p1_transcript_export': rng.choice(['yes', 'no']),
             'p1_end_after_reset': rng.choice(['yes', 'yes', 'no']), 'p2_lag_seconds': rng.choice([0, 20, 90])}
    return CW.World(series, gates=gates, rng=rng), rng


def run_sequence(seed):
    """One sequence. Returns (applies, illegal_checked, cuts, rows set, failures [str])."""
    w, rng = new_world(seed)
    length = rng.randint(1, MAX_LEN)
    states, fails, rows, illegal, applies = [None], [], set(), 0, 0
    for i in range(length):
        mv = CW.moves(w)
        if not mv:
            break
        lab, th = pick(rng, mv)
        e = th()
        if rng.random() < 0.2:
            bad = mutate(w, rng, e)
            if bad is not None:
                before = cjson(w.state) if w.state is not None else b'null'
                try:
                    F.apply(w.state, bad)
                    fails.append('seed %d step %d: illegal %s accepted' % (seed, i, lab))
                except F.ChainInvalid:
                    illegal += 1
                if (cjson(w.state) if w.state is not None else b'null') != before:
                    fails.append('seed %d step %d: illegal entry changed the state' % (seed, i))
        before = cjson(w.state) if w.state is not None else b'null'
        try:
            r = w.commit(e)
            applies += 1
        except F.ChainInvalid as c:
            fails.append('seed %d step %d: legal %s refused %s' % (seed, i, lab, c.code))
            break
        rows.update(r)
        if (cjson(states[-1]) if states[-1] is not None else b'null') != before:
            fails.append('seed %d step %d: apply mutated its input' % (seed, i))
        states.append(w.state)
        try:
            CW.check_invariants(w.state)
            check_starts(w.state)
        except AssertionError as a:
            fails.append('seed %d step %d after %s: %s' % (seed, i, lab, a))
            break
    s2 = None
    for e in w.entries:                                                # determinism: fold again from nothing
        s2 = F.apply(s2, e)
    if w.entries and cjson(s2) != cjson(w.state):
        fails.append('seed %d: second fold differs' % seed)
    cuts = 0
    if seed % CUT_EVERY == 0:
        for k in range(1, len(states)):
            cuts += 1
            fails += cut_at(seed, w, states, k)
    return applies, illegal, cuts, rows, fails


def cut_at(seed, w, states, k):
    """Discard the tail after entry k, fold a random legal RESTORE, continue up to 4 entries; check F2."""
    rng = random.Random(seed * 1000 + k)
    c = CW.World(w.series, gates=w.gates, jobs=w.jobs, rng=rng)
    c.state, c.entries = states[k], list(w.entries[:k])
    c.t, c.nboot, c.kit = w.t + 10000, w.nboot + 100, states[k]['kit_sha256']
    c.boot = CW.boot(c.nboot)
    rm = CW._restore_moves(c) if states[k]['phase'] != 'FINAL' else []
    if not rm:
        return []
    out = []
    lab, th = rng.choice(rm)
    try:
        c.commit(th())
        for _ in range(4):
            CW.check_invariants(c.state)
            check_starts(c.state)
            mv = CW.moves(c)
            if not mv:
                break
            lab, th = pick(rng, mv)
            c.commit(th())
    except F.ChainInvalid as x:
        out.append('seed %d cut %d: legal %s refused %s' % (seed, k, lab, x.code))
    except AssertionError as a:
        out.append('seed %d cut %d after %s: %s' % (seed, k, lab, a))
    return out


def run(jobs=4, n=N_SEQUENCES):
    """Runs the property suite; returns a result dict (tests, passed, failures)."""
    seeds = list(range(n))
    if jobs > 1:
        with multiprocessing.get_context('fork').Pool(jobs) as pool:
            res = pool.map(run_sequence, seeds, chunksize=25)
    else:
        res = [run_sequence(x) for x in seeds]
    applies = sum(r[0] for r in res)
    illegal = sum(r[1] for r in res)
    cuts = sum(r[2] for r in res)
    rows = set().union(*(r[3] for r in res))
    fails = [f for r in res for f in r[4]]
    tests = [('props_sequences', not [f for f in fails if 'cut' not in f]),
             ('props_cuts', not [f for f in fails if 'cut' in f])]
    want = {'T01', 'T10', 'T11', 'T12', 'T13', 'T15', 'T20', 'T21', 'T23', 'T24', 'T30', 'T31', 'T37',
            'T38', 'T41', 'T42', 'T43', 'T44', 'T45', 'T46', 'T47', 'T49', 'T52', 'T55', 'T58', 'T59', 'T62'}
    tests.append(('props_every_positive_row_reached', want <= rows))
    return {'name': 'test_core_props', 'tests': len(tests), 'passed': sum(ok for _, ok in tests),
            'failed': [t for t, ok in tests if not ok], 'detail': fails[:40] + sorted(want - rows),
            'counts': {'sequences': n, 'applies': applies, 'illegal_injected': illegal, 'cuts': cuts}}


if __name__ == '__main__':
    import json
    r = run(int(sys.argv[1]) if len(sys.argv) > 1 else 4, int(sys.argv[2]) if len(sys.argv) > 2 else N_SEQUENCES)
    print(json.dumps(r, indent=1))
    sys.exit(0 if not r['failed'] else 1)
