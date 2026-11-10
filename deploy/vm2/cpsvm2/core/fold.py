"""Section T (spec §4): TABLE as data, and apply(state, entry) -> state'. Pure: no I/O, no clock.

apply(state, entry): `state` is the fold state (cps.vm2-state.v1, §3.11) or None before GENESIS; `entry` an ENTRY
document or draft (its `state`/`state_sha256` keys are ignored). Returns a NEW state; the input is never modified.
Raises ChainInvalid(code) where code is a structural code of §4.2 (SCHEMA_INVALID, SEQ_GAP, SERIES_MISMATCH,
CONFIRMS_MISMATCH, RELEASE_NOT_ACCEPTED, HELPER_UNKNOWN), a row id of §4.3 (a series guard T02-T06, a negative row
T22/T32/T48, or the kind's fallback T14/T16/T25/T36/T39/T50/T53/T56/T60/T63), or AMBIGUOUS_ROWS (a bug).
apply_traced(state, entry) -> (state', [row ids]) also returns the rows used (top row, then T30/T31, T43-T47, T49).

State keys beyond §3.11 (documented for the review): RUN.visual_record (PASS/FAIL from the last visual-record command
with a NEXT result, for frozen.visual), RUN.rerun_expected (set by a RESTORE's rerun_expected, cleared by the run's next
STAGE/FROZEN, which must then carry body.rerun), RUN.delivery.ack_seq (the seq of the last delivery ACK, for the
DELIVER_USER mark, §7.1 row 17), archives[i].utc/.transcript (the AI entry's utc and transcript status, for the O52
sheet and the O40 counts), undo.kind/undo.start (the head's kind and START, for T49) and undo.parts as
[[name, md5, bytes]] (S4 checks the attested copies against them), rebases[i].start (the START a rebase superseded)."""
from collections import namedtuple

from . import entry as E
from .names import (REVIEW_CONTINUABLE, RUNNER_SHA256, HELPER_VERSION, cjson, entry_name, mode_of, sha, utc_epoch)

OPEN = ('STARTED', 'OPENED', 'CONTINUED')
ROLE_OF_NEXT = {'SCOPE_READER': 'S', 'GENERATE': 'G', 'VISUAL_REVIEW': 'V'}
FROZEN_FLAGS = ('AI_OUTPUT_LOST', 'VISUAL_QA_FAILED_BY_RESET', 'RESTART_EXHAUSTED_BY_RESET', 'REVIEW_INCOMPLETE_LIMIT',
                'RESET_DIVERGED')
START_ACTIONS = {'SUPERSEDE': 'NO_CONVERSATION', 'EVERYDAY_RETRY': 'EVERYDAY_RETRY', 'REPLACE': 'REPLACEMENT'}
CONFIG_MEMBER = 'VM_HELPER_CONFIG.json'
CHANGEABLE_KEYS = frozenset({'clear', 'wrap_foreground_seconds', 'clock_wait_max_seconds', 'png_part_bytes',
                             'max_entry_bytes', 'max_transcript_bytes', 'max_ai_output_bytes', 'doc_samples'})


def clone(x):
    """A deep copy of JSON data (dict, list, scalars): the fold state and entries hold nothing else."""
    if type(x) is dict:
        return {k: clone(v) for k, v in x.items()}
    if type(x) is list:
        return [clone(v) for v in x]
    return x


class ChainInvalid(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


Row = namedtuple('Row', 'id kinds kind_of guard effect doc')   # kind_of: positive | series | negative | fallback | sub


# ---------------------------------------------------------------- state helpers (also used by plan, session, outcome)
def is_q(state):
    return state['mode'] in ('qualification', 'drill')


def w_abs(gates):
    """max(60, 2 * p2_lag_seconds) (§8.4)."""
    return max(60, 2 * (gates.get('p2_lag_seconds') or 0))


def reader_of(tag):
    return {'A': 'A', 'A-restart1': 'A', 'NA-A': 'A', 'B': 'B', 'B-restart1': 'B', 'NA-B': 'B'}.get(tag)


def open_roles(state):
    """§4.1 open(state): [(run, role key)] of every role STARTED, OPENED or CONTINUED, in run order."""
    return [(k, rk) for k in state['order'] for rk in sorted(state['runs'][k]['roles'])
            if state['runs'][k]['roles'][rk]['status'] in OPEN]


def run_open(R):
    return any(r['status'] in OPEN for r in R['roles'].values())


def latest(role):
    """The role's last start with superseded_by == null (§4.3 latest(role))."""
    return [s for s in role['starts'] if s['superseded_by'] is None][-1]


def newest(R, letter):
    ks = sorted((r['attempt'], k) for k, r in R['roles'].items() if r['role'] == letter)
    return R['roles'][ks[-1][1]] if ks else None


def chain(state, case, reader):
    """Run keys of (case, reader) in creation order: the original run then its restart (or the NA run)."""
    return [k for k in state['order'] if state['runs'][k]['case'] == case and state['runs'][k]['reader'] == reader]


def jobs_map(state):
    return {j[0]: j for j in (state['genesis']['jobs'] or [])}


def nonattempt(job):
    return job[2] not in (None, False)


def pending_resolution(R):
    """The run's resolution (latest by seq) committed after its last snapshot, i.e. whose action has not run yet."""
    rs = [r['resolution'] for r in R['roles'].values() if r['resolution']]
    rs.sort(key=lambda r: r['seq'])
    snap = (R['snapshot'] or {}).get('seq') or 0
    return rs[-1] if rs and rs[-1]['seq'] > snap else None


def config_only(from_members, to_members):
    """§8.2: the two member lists [[path, sha256]] differ only at VM_HELPER_CONFIG.json."""
    a, b = {m[0]: m[1] for m in from_members}, {m[0]: m[1] for m in to_members}
    return {k for k in set(a) | set(b) if a.get(k) != b.get(k)} <= {CONFIG_MEMBER}


def run_in_flight(state):
    return state['current'] is not None or bool(open_roles(state))


def has_transcript(entry, role, attempt, start_no):
    pre = 'transcript/%s%d_%d.' % (role, attempt, start_no)
    return any(m[0].startswith(pre) and m[1] == 'file' for m in entry['payload']['members'])


# ---------------------------------------------------------------- structural checks S1-S6 (§4.2)
def structural(state, e):
    if E.validate_entry(e, draft=True):
        raise ChainInvalid('SCHEMA_INVALID')
    if (state is None) != (e['seq'] == 1) or (state is not None and e['seq'] != state['seq'] + 1):
        raise ChainInvalid('SEQ_GAP')
    if e['runner_sha256'] != RUNNER_SHA256 or e['helper']['version'] != HELPER_VERSION:
        raise ChainInvalid('HELPER_UNKNOWN')
    if state is None:
        return
    if e['series'] != state['series']:
        raise ChainInvalid('SERIES_MISMATCH')
    _s4(state, e)
    _s5(state, e)


def _s4(state, e):
    cf, u = e['confirms'], state['undo']
    if [c['name'] for c in cf] != [entry_name(state['series'], state['seq'])] + [p[0] for p in u['parts']] \
            or not cf[0]['copies']:
        raise ChainInvalid('CONFIRMS_MISMATCH')
    for c, p in zip(cf[1:], u['parts']):
        if any(cp['md5'] != p[1] or cp['size'] != p[2] for cp in c['copies']):
            raise ChainInvalid('CONFIRMS_MISMATCH')
    missing = {c['name'] for c in cf[1:] if not c['copies']}
    rb = e['body'].get('rebase') if e['kind'] == 'RESTORE' else None
    if missing != (set(rb['missing_parts']) if rb else set()) or (rb and len(rb['missing_parts']) != len(missing)):
        raise ChainInvalid('CONFIRMS_MISMATCH')


def _s5(state, e):
    kc = e['body'].get('kit_change') if e['kind'] in ('RESTORE', 'CLEAR') else None
    if kc is None:
        if e['release_sha256'] != state['release_sha256'] or e['kit_sha256'] != state['kit_sha256']:
            raise ChainInvalid('RELEASE_NOT_ACCEPTED')
        return
    co = config_only(kc['from_members'], kc['to_members'])
    ok = kc['from_kit_sha256'] == state['kit_sha256'] and kc['to_kit_sha256'] == e['kit_sha256'] \
        and kc['config_only'] is co and kc['run_in_flight'] is run_in_flight(state)
    if co:
        ok = ok and e['release_sha256'] == state['release_sha256'] and set(kc['config_keys_changed']) <= CHANGEABLE_KEYS
    else:
        ok = ok and e['kind'] == 'RESTORE' and not run_in_flight(state) and (
            e['release_sha256'] == state['genesis']['release_sha256']
            or e['release_sha256'] in kc['to_accepts_release_sha256'])
    if not ok:
        raise ChainInvalid('RELEASE_NOT_ACCEPTED')


# ---------------------------------------------------------------- run progress (T20-T25) and new runs (T10-T14)
def _pre(s, e):
    b = e['body']
    R = s['runs'].get(b['run'])
    return b['new_run'] is None and b['run'] == s['current'] and R is not None and R['status'] == 'ACTIVE'


def _consumed_ok(R, b):
    for c in b['consumed']:
        ro = R['roles'].get(c['role'] + str(c['attempt']))
        if not ro or ro['status'] != 'ARCHIVED' or ro['consumed'] or ro['archives'][-1]['revision'] != c['revision'] \
                or ro['archives'][-1]['tree_sha256'] != c['tree_sha256']:
            return False
    return True


def _common_ok(s, R, e):
    """rebase/rerun binding (§7.10) and the PNG reference rule (§3.8), shared by T20, T21, T23, T24."""
    b, bind, rx = e['body'], R['rebase_bind'], R.get('rerun_expected')
    if (b['rebase'] is None) != (bind is None) or (b['rerun'] is None) != (rx is None):
        return False
    if bind and (b['rebase']['head_seq'], b['rebase']['base_seq']) != (bind['head_seq'], bind['base_seq']):
        return False
    if rx and (b['rerun']['after_seq'] != rx['seq'] or b['rerun']['unbound'] is not True):
        return False
    png_parts = [p for p in e['parts'] if p['kind'] == 'PNG']
    if b['png'] is None:
        return not png_parts
    if b['png']['parts_seq'] == e['seq']:
        return bool(png_parts)
    have = {(f[0], f[3]) for f in (R['png'] or {}).get('files', [])}
    return not png_parts and R['png'] is not None and b['png']['parts_seq'] == R['png']['parts_seq'] \
        and all((f[0], f[3]) in have for f in b['png']['files'])


def start_problem(s, R, e):
    """None when the STAGE's START obeys T20 (present iff next is an AI step) and T30/T31; else the row id."""
    b = e['body']
    st, want = b['start'], ROLE_OF_NEXT.get(b['next'])
    if want is None or st is None:
        return None if (want is None and st is None) else 'T25'
    if st['role'] != want or st['utc'] != e['utc'] or st['boot_id'] != e['boot_id']:
        return 'T32'
    if st['reason'] == 'STAGE' and _t30(s, R, e, st):
        return None
    if st['reason'] == 'REBASE' and _t31(s, R, e, st):
        return None
    return 'T32'


def _t30(s, R, e, st):
    if st['start_no'] != 1:
        return False
    if st['attempt'] == 1 and not any(r['role'] == st['role'] for r in R['roles'].values()):
        return True
    g1 = R['roles'].get('G1')
    return (st['role'], st['attempt']) == ('G', 2) and 'G2' not in R['roles'] and g1 is not None \
        and (g1['resolution'] or {}).get('action') == 'INTERRUPT' and not R['interrupts'] and R['restart_of'] is None \
        and any(c['sub'] == 'interrupt' and c['result'] == 'NEXT' and c['next'] == 'GENERATE'
                for c in e['body']['commands'])


def _t31(s, R, e, st):
    bind = R['rebase_bind']
    old = R['rebases'][-1].get('start') if R['rebases'] else None
    return e['body']['rebase'] is not None and bind is not None and old is not None \
        and (old['role'], old['attempt']) == (st['role'], st['attempt']) and st['start_no'] == old['start_no'] + 1 \
        and old['supersedes'] == 0 and (st['role'] + str(st['attempt'])) not in R['roles'] \
        and (s['genesis']['gates'].get('p1_conversation_list') != 'yes' or bind['list_shows_none'] is True)


def g20(s, R, e, c):
    b = e['body']
    return not run_open(R) and _consumed_ok(R, b) and b['refused'] is None and not b['review_incomplete'] \
        and start_problem(s, R, e) is None and _common_ok(s, R, e) \
        and (b['rebase'] is None or b['rebase']['diverged'] is False)


def g21(s, R, e, c):
    b, V = e['body'], newest(R, 'V')
    return not run_open(R) and b['review_incomplete'] and b['refused'] in REVIEW_CONTINUABLE and b['start'] is None \
        and V is not None and V['status'] == 'ARCHIVED' and not V['consumed'] and V['review_incomplete'] < 2 \
        and _consumed_ok(R, b) and _common_ok(s, R, e)


def g22(s, R, e, c):
    V = newest(R, 'V')
    return e['body']['review_incomplete'] and V is not None and V['review_incomplete'] >= 2


def g23(s, R, e, c):
    b, last = e['body'], e['body']['commands'][-1]
    ledger_sha = (s['ledger'] or {}).get('sha256')
    return not run_open(R) and b['refused'] is not None and b['refused'] not in REVIEW_CONTINUABLE \
        and not b['review_incomplete'] and b['start'] is None and _consumed_ok(R, b) and _common_ok(s, R, e) \
        and (last['record_sha256_after'] != R['record_sha256'] or last['ledger_sha256_after'] != ledger_sha)


def expected_frozen_flags(s, R, b):
    """§4.6: the exact set of flags a FROZEN of run R with body b must add (the worker uses it to build flags_added)."""
    out, pr, cmds = set(), pending_resolution(R), b['commands']
    act = pr['action'] if pr else None
    if act == 'FREEZE_LOST':
        out.add('AI_OUTPUT_LOST')
    if act == 'FREEZE_VISUAL_FAILED':
        out.add('VISUAL_QA_FAILED_BY_RESET')
    if act == 'FREEZE_EXHAUSTED' or (act == 'INTERRUPT' and any(
            c['sub'] == 'interrupt' and c['result'] == 'REFUSED' and c['next'] == 'INTERRUPT_RESTART_USED'
            for c in cmds)):
        out.add('RESTART_EXHAUSTED_BY_RESET')
    V = newest(R, 'V')
    if V is not None and V['review_incomplete'] == 2 and any(
            c['sub'] == 'visual-record' and c['result'] == 'REFUSED' and c['next'] in REVIEW_CONTINUABLE for c in cmds):
        out.add('REVIEW_INCOMPLETE_LIMIT')
    if b['rebase'] is not None and b['rebase']['diverged']:
        out.add('RESET_DIVERGED')
    return out


def g24(s, R, e, c):
    b, last = e['body'], e['body']['commands'][-1]
    fl = b['flags_added']
    dl = b['delivery_sent'] is False or (s['mode'] == 'everyday' and (R['delivery'] or {}).get('prepared_seq'))
    return not run_open(R) and _consumed_ok(R, b) and b['start'] is None and not b['review_incomplete'] \
        and (last['sub'], last['result'], last['next']) == ('verify-frozen', 'NEXT', 'DONE') \
        and len(set(fl)) == len(fl) and set(fl) == expected_frozen_flags(s, R, b) \
        and not (R['restart_of'] is not None and b['restart_eligible']) and _common_ok(s, R, e) and bool(dl)


def _update(s, R, e):
    """§4.5: the effect of a STAGE or FROZEN on R."""
    b, seq = e['body'], e['seq']
    R['next'], R['next_args'], R['codes'] = b['next'], b['next_args'], b['codes']
    R['record_sha256'] = b['commands'][-1]['record_sha256_after']
    R['snapshot'] = {'seq': seq, 'tree_sha256': b['snapshot']['tree_sha256']}
    if b['png'] is not None:
        parts = [p['name'] for p in e['parts'] if p['kind'] == 'PNG'] if b['png']['parts_seq'] == seq \
            else R['png']['parts']
        R['png'] = {'parts_seq': b['png']['parts_seq'], 'files': b['png']['files'],
                    'whole_sha256': b['png']['whole_sha256'], 'parts': parts}
    if b['saved_qa'] is not None:
        R['saved_qa'] = b['saved_qa']
    if b['carrier_sha256'] is not None:
        R['carrier_sha256'] = b['carrier_sha256']
    R['response_frozen'] = R['response_frozen'] or b['generation_record_sha256'] is not None
    for cm in b['commands']:
        if cm['sub'] == 'visual-record' and cm['result'] == 'NEXT':
            R['visual_record'] = 'FAIL' if cm['next'].startswith('STOP_') else 'PASS'
    for cm in b['consumed']:
        ro = R['roles'][cm['role'] + str(cm['attempt'])]
        if e['kind'] == 'FROZEN' or b['refused'] is None:
            ro['consumed'] = {'seq': seq, 'revision': cm['revision']}
    if b['rerun'] is not None:
        R['reruns'].append({'seq': seq, 'stage': b['commands'][0]['sub']})
        _flag(R, 'RERUN_UNBOUND')
        R['rerun_expected'] = None
    if b['rebase'] is not None:
        R['rebases'][-1].update(diverged=b['rebase']['diverged'], rerun_seq=seq)
        R['rebase_bind'] = None


def _flag(R, f):
    if f not in R['flags']:
        R['flags'].append(f)


def _new_role(st, seq):
    return {'role': st['role'], 'attempt': st['attempt'], 'status': 'STARTED', 'starts': [_start_rec(st, seq)],
            'supersedes': 0, 'opened': None, 'archives': [], 'continuations': 0, 'review_incomplete': 0,
            'continued_boot': None, 'consumed': None, 'resolution': None}


def _start_rec(st, seq):
    return dict(st, seq=seq, superseded_by=None)


def e20(s, R, e, c):
    _update(s, R, e)
    st = e['body']['start']
    if st is not None and st['reason'] == 'STAGE':
        if st['attempt'] == 2:
            R['interrupts'].append({'seq': e['seq'], 'form': 'in_place'})
        R['roles'][st['role'] + str(st['attempt'])] = _new_role(st, e['seq'])
    elif st is not None:                                      # T31 REBASE
        old = dict(R['rebases'][-1]['start'], superseded_by=st['start_no'])
        old.pop('supersedes', None)
        ro = _new_role(st, e['seq'])
        ro['starts'], ro['supersedes'] = [old, _start_rec(st, e['seq'])], 1
        R['roles'][st['role'] + str(st['attempt'])] = ro
        _flag(R, 'REBASED')
    return s


def e21(s, R, e, c):
    _update(s, R, e)
    V = newest(R, 'V')
    V['status'], V['continued_boot'] = 'CONTINUED', e['boot_id']
    V['continuations'] += 1
    V['review_incomplete'] += 1
    return s


def e23(s, R, e, c):
    _update(s, R, e)
    s['phase'], s['halt'] = 'HALTED', {'seq': e['seq'], 'code': 'RUNNER_REFUSED'}
    return s


def e24(s, R, e, c):
    b = e['body']
    _update(s, R, e)
    for f in b['flags_added']:
        _flag(R, f)
    vis = 'FAILED_BY_RESET' if 'VISUAL_QA_FAILED_BY_RESET' in R['flags'] else 'REVIEW_INCOMPLETE_LIMIT' \
        if 'REVIEW_INCOMPLETE_LIMIT' in R['flags'] else R.get('visual_record') or 'NOT_REACHED'
    R['status'] = 'FROZEN'
    R['frozen'] = {'seq': e['seq'], 'frozen_sha256': b['frozen_sha256'], 'final_next': b['final_next'],
                   'final_codes': b['final_codes'], 'carrier_sha256': R['carrier_sha256'],
                   'restart_eligible': b['restart_eligible'], 'visual': vis}
    s['current'] = None
    if b['notify'] is not None:
        s['notify'] = {'seq': e['seq'], 'what': b['notify'], 'about': None}
    return s


PROGRESS = (('T20', 'STAGE', g20, e20), ('T21', 'STAGE', g21, e21), ('T23', 'STAGE', g23, e23),
            ('T24', 'FROZEN', g24, e24))


def _progress(s, R, e, c):
    for rid, kind, g, eff in PROGRESS:
        if kind == e['kind'] and g(s, R, e, c):
            return rid, eff
    return None, None


def _row_progress(rid):
    def guard(s, e, c):
        return _pre(s, e) and _progress(s, s['runs'][e['body']['run']], e, c)[0] == rid

    def effect(s, e, c):
        R = s['runs'][e['body']['run']]
        return _progress(s, R, e, c)[1](s, R, e, c)
    return guard, effect


def _blank_run(nr, key):
    return {'key': key, 'tag': nr['tag'], 'case': nr['case'], 'reader': nr['reader'], 'job_dir': nr['job_dir'],
            'restart_of': nr['restart_of'], 'status': 'ACTIVE', 'inputs': None, 'reprepares': 0, 'next': None,
            'next_args': None, 'codes': [], 'record_sha256': None, 'snapshot': None, 'png': None, 'saved_qa': None,
            'carrier_sha256': None, 'response_frozen': False, 'interrupts': [], 'roles': {}, 'replacements': 0,
            'flags': [], 'frozen': None, 'reruns': [], 'rebases': [], 'delivery': None, 'rebase_bind': None,
            'visual_record': None, 'rerun_expected': None}


def _virtual(s, e):
    """A copy of s with the entry's new run in place (ACTIVE, current), for the progress rows of a new-run entry."""
    b, v = e['body'], clone(s)
    nr = b['new_run']
    key = nr['tag'] + '/' + nr['case']
    if key != b['run']:
        return None
    if s['mode'] == 'everyday':
        R = v['runs'].get(key)
        if R is None:
            return None
        R.update(status='ACTIVE', reader=nr['reader'], job_dir=nr['job_dir'], restart_of=nr['restart_of'])
    else:
        if key in v['runs'] or reader_of(nr['tag']) != nr['reader']:
            return None
        v['runs'][key] = _blank_run(nr, key)
        v['order'].append(key)
    v['current'] = key
    return v


def _new_run_progress(s, e, c):
    v = _virtual(s, e)
    if v is None:
        return None, None
    rid = _progress(v, v['runs'][e['body']['run']], e, c)[0]
    return (v, rid) if rid in ('T20', 'T24') or (rid == 'T23' and e['kind'] == 'STAGE') else (None, None)


def g10(s, e, c):
    b = e['body']
    nr = b['new_run']
    if not (c['Q'] and nr and nr['tag'] in ('A', 'B') and s['current'] is None and nr['restart_of'] is None):
        return False
    job = jobs_map(s).get(nr['case'])
    if job is None or nonattempt(job) or chain(s, nr['case'], nr['reader']):
        return False
    if nr['reader'] == 'B':
        ac = chain(s, nr['case'], 'A')
        L = s['runs'][ac[-1]] if ac else None
        if L is None or L['status'] != 'FROZEN' or not (
                not L['frozen']['restart_eligible'] or L['tag'] == 'A-restart1' or 'RESET_DIVERGED' in L['flags']):
            return False
    return _new_run_progress(s, e, c)[0] is not None


def g11(s, e, c):
    nr = e['body']['new_run']
    if not (c['Q'] and nr and nr['tag'] in ('A-restart1', 'B-restart1') and s['current'] is None):
        return False
    ch = chain(s, nr['case'], reader_of(nr['tag']))
    if len(ch) != 1 or nr['restart_of'] != ch[0]:
        return False
    L = s['runs'][ch[0]]
    if L['status'] != 'FROZEN' or not L['frozen']['restart_eligible'] or 'RESET_DIVERGED' in L['flags'] \
            or L['interrupts'] or L['tag'] not in ('A', 'B'):
        return False
    if reader_of(nr['tag']) == 'A' and chain(s, nr['case'], 'B'):
        return False
    return _new_run_progress(s, e, c)[0] is not None


def g12(s, e, c):
    nr = e['body']['new_run']
    if not (e['kind'] == 'FROZEN' and c['Q'] and nr and nr['tag'] in ('NA-A', 'NA-B') and s['current'] is None
            and [x['sub'] for x in e['body']['commands']] == ['nonattempt', 'verify-frozen']):
        return False
    job = jobs_map(s).get(nr['case'])
    if job is None or not nonattempt(job) or chain(s, nr['case'], nr['reader']):
        return False
    if nr['tag'] == 'NA-B' and not chain(s, nr['case'], 'A'):
        return False
    return _new_run_progress(s, e, c)[1] == 'T24'


def g13(s, e, c):
    nr, cur = e['body']['new_run'], s['current']
    R = s['runs'].get(cur) if cur else None
    if not (not c['Q'] and nr and R is not None and R['status'] == 'INPUTS' and nr['tag'] == R['tag']
            and nr['case'] == R['case'] and nr['restart_of'] is None
            and e['body']['prepare_inputs_sha256'] == R['inputs']['sha256']):
        return False
    return _new_run_progress(s, e, c)[0] is not None


def e_new(s, e, c):
    v, rid = _new_run_progress(s, e, c)
    R = v['runs'][e['body']['run']]
    return dict(PROGRESS_EFFECT)[rid](v, R, e, c)


PROGRESS_EFFECT = tuple((rid, eff) for rid, _, _, eff in PROGRESS)


def g15(s, e, c):
    b = e['body']
    return not c['Q'] and s['current'] is None and b['tag'].startswith('E') \
        and not any(R['tag'] == b['tag'] for R in s['runs'].values())


def e15(s, e, c):
    b = e['body']
    key = b['tag'] + '/' + b['case']
    R = _blank_run({'tag': b['tag'], 'case': b['case'], 'reader': None, 'job_dir': None, 'restart_of': None}, key)
    R.update(status='INPUTS', inputs={'seq': e['seq'], 'sha256': sha(cjson(b['inputs']))})
    s['runs'][key] = R
    s['order'].append(key)
    s['current'] = key
    return s


# ---------------------------------------------------------------- OPENED, AI (T35-T39)
def _role(s, e):
    b = e['body']
    R = s['runs'].get(b['run'])
    if b['run'] != s['current'] or R is None or R['status'] != 'ACTIVE':
        return None, None
    return R, R['roles'].get(b['role'] + str(b['attempt']))


def g35(s, e, c):
    R, ro = _role(s, e)
    return ro is not None and ro['status'] == 'STARTED' and ro['opened'] is None \
        and e['body']['start_no'] == latest(ro)['start_no']


def e35(s, e, c):
    b = e['body']
    _role(s, e)[1].update(status='OPENED', opened={'seq': e['seq'], 'conversation': b['conversation'],
                                                    'utc': b['opened_utc']})
    return s


def g37(s, e, c):
    b = e['body']
    R, ro = _role(s, e)
    if ro is None:
        return False
    lt = latest(ro)
    return b['revision'] == 1 and not ro['archives'] and b['ended'] is True and b['start_no'] == lt['start_no'] \
        and (ro['status'] == 'OPENED' or (ro['status'] == 'STARTED' and c['gates'].get('p1_conversation_list') == 'yes')) \
        and b['start_boot_id'] == lt['boot_id'] == e['boot_id']


def g38(s, e, c):
    b = e['body']
    R, ro = _role(s, e)
    return ro is not None and ro['role'] == 'V' and ro['status'] == 'CONTINUED' and b['ended'] is True \
        and b['revision'] == len(ro['archives']) + 1 and e['boot_id'] == ro['continued_boot'] \
        and b['start_no'] == latest(ro)['start_no']


def e37(s, e, c):
    b = e['body']
    ro = _role(s, e)[1]
    ro['status'] = 'ARCHIVED'
    ro['archives'].append({'seq': e['seq'], 'revision': b['revision'], 'tree_sha256': b['tree_sha256'],
                           'conversation': b['conversation'], 'boot_id': e['boot_id'], 'utc': e['utc'],
                           'transcript': (b['transcript'] or {}).get('status')})
    return s


# ---------------------------------------------------------------- RESTORE (T41-T50)
def forced_for(state, R, ro, item):
    """§8.6 step 5: the `forced` value the helper sets for a restore item (first match), or None."""
    g = state['genesis']['gates']
    if g.get('p1_end_after_reset') == 'no':
        return 'NOT_ENDABLE'
    if item['files_found']:
        return 'FILES_FOUND'
    if item['ended'] is False:
        return 'NOT_ENDED'
    if item['outcome'] == 'NO_CONVERSATION' and ro['status'] != 'CONTINUED':
        if g.get('p1_conversation_list') == 'no' and ro['status'] == 'STARTED' and ro['opened'] is None:
            return 'NO_LIST'
        if not (no_conversation_admissible(state, ro) and item['list_shows_none'] is True):
            return 'NO_CONVERSATION_NOT_ALLOWED'
    return None


def no_conversation_admissible(state, ro):
    """T43's conditions that do not depend on the answer: STARTED never OPENED, no superseding START yet in the
    attempt, a conversation list on this platform (§6.5 asks list_shows_none only then)."""
    return ro['status'] == 'STARTED' and ro['opened'] is None and ro['supersedes'] == 0 \
        and state['genesis']['gates'].get('p1_conversation_list') == 'yes'


def resolution_action(state, item, transcript_member):
    """(row id, action, owner_check) for one restore item over `state` (§4.3 T43-T48, §8.6 step 6). The session uses
    it to compute the action; the fold re-computes it and requires equality. Row 'T48' (action None) is CHAIN_INVALID.
    transcript_member: the RESTORE payload holds transcript/<role><attempt>_<start_no>.<ext> (I6)."""
    R = state['runs'].get(item['run'])
    ro = R['roles'].get(item['role'] + str(item['attempt'])) if R else None
    if ro is None or ro['status'] not in OPEN or item['start_no'] != latest(ro)['start_no'] \
            or item['transcript'] not in ('exported', 'not_available') \
            or (item['transcript'] == 'exported' and not transcript_member) \
            or not isinstance(item['ended'], bool) or not isinstance(item['files_found'], bool):
        return 'T48', None, False
    forced, q = forced_for(state, R, ro, item), is_q(state)
    if item['forced'] != forced:
        return 'T48', None, False
    if ro['status'] == 'CONTINUED':
        return ('T46', 'FREEZE_VISUAL_FAILED', False) if item['outcome'] == 'CONTINUED' else ('T48', None, False)
    oc = q and forced is None and item['transcript'] == 'not_available' and item['outcome'] == 'NOTHING_WRITTEN'
    if forced is not None or item['outcome'] in ('WRITTEN', 'UNSURE'):
        return 'T47', ('FREEZE_VISUAL_FAILED' if ro['role'] == 'V' else 'FREEZE_LOST'), False
    if item['outcome'] == 'NO_CONVERSATION':
        return 'T43', 'SUPERSEDE', False
    if item['outcome'] != 'NOTHING_WRITTEN' or not item['ended'] or item['files_found']:
        return 'T48', None, False
    exported = item['transcript'] == 'exported'
    if ro['role'] in ('S', 'G'):
        if q:
            return 'T44', 'INTERRUPT', oc
        if not exported:
            return 'T44', 'FREEZE_LOST', False
        return 'T44', ('EVERYDAY_RETRY' if ro['attempt'] == 1 else 'FREEZE_EXHAUSTED'), False
    if R['replacements'] == 0 and (q or exported):
        return 'T45', 'REPLACE', oc
    return 'T45', 'FREEZE_VISUAL_FAILED', oc


def start_for(action, ro):
    """(role, attempt, start_no, reason) of the START a resolution action needs, or None."""
    lt = latest(ro)
    return {'SUPERSEDE': (ro['role'], ro['attempt'], lt['start_no'] + 1, 'NO_CONVERSATION'),
            'EVERYDAY_RETRY': (ro['role'], ro['attempt'] + 1, 1, 'EVERYDAY_RETRY'),
            'REPLACE': ('V', ro['attempt'] + 1, 1, 'REPLACEMENT')}.get(action)


def g49(s, e, c):
    rb, u = e['body']['rebase'], s['undo']
    if not (rb['head_seq'] == s['seq'] == u['seq'] and u['kind'] in ('STAGE', 'FROZEN') and u['run'] and u['parts']
            and u['before'] is not None and s['phase'] == 'OPEN' and rb['missing_parts']
            and isinstance(rb['bound'], dict) and rb['base_seq'] == (u['before']['snapshot'] or {}).get('seq')):
        return False
    names = {p[0] for p in u['parts']}
    ab = {a['name']: a['utc'] for a in rb['absence']}
    for n in rb['missing_parts']:
        t = [utc_epoch(x) for x in ab.get(n, [None, None])]
        if n not in names or None in t or t[1] - t[0] < w_abs(c['gates']):
            return False
    allowed = set()
    if u['start'] is not None:
        key = u['start']['role'] + str(u['start']['attempt'])
        ro = s['runs'][u['run']]['roles'].get(key)
        if ro is None or ro['supersedes'] != 0 or (
                c['gates'].get('p1_conversation_list') == 'yes' and rb['list_shows_none'] is not True):
            return False
        allowed.add((u['run'], key))
    return set(open_roles(s)) <= allowed


def undo49(s, e):
    """T49 effect: revert the head's run to its base, bind the re-run."""
    rb, u = e['body']['rebase'], s['undo']
    R = clone(u['before'])
    s['runs'][u['run']] = R
    s['current'], s['ledger'], s['notify'] = u['current_before'], u['ledger_before'], u['notify_before']
    R['rebase_bind'] = {'head_seq': rb['head_seq'], 'base_seq': rb['base_seq'], 'bound': rb['bound'],
                        'list_shows_none': rb['list_shows_none']}
    old = None
    if u['start'] is not None:
        old = dict(u['start'], seq=u['seq'], superseded_by=None, supersedes=0)
    R['rebases'].append({'seq': e['seq'], 'head_seq': rb['head_seq'], 'base_seq': rb['base_seq'], 'diverged': None,
                         'start': old})
    return s


def _restore_state(s, e, c):
    """The state T42 compares the resolutions with: T49's undo first when body.rebase is present."""
    if e['body']['rebase'] is None:
        return s
    return undo49(clone(s), e) if g49(s, e, c) else None


def g41(s, e, c):
    b, cur = e['body'], s['current']
    R = s['runs'].get(cur) if cur else None
    if c['Q'] or R is None or R['status'] != 'INPUTS' or b['resolutions'] or b['rebase'] or b['start'] \
            or b['delivery_question'] or b['rerun_expected'] or not _restore_ok(e):
        return False
    if (b['reprepare'] is None) == (b['abandon'] is None):
        return False
    if b['reprepare'] is not None:
        return b['reprepare'].get('run') == cur and R['reprepares'] == 0 \
            and b['reprepare'].get('inputs_seq') == R['inputs']['seq']
    return b['abandon'].get('run') == cur


def e41(s, e, c):
    b, R = e['body'], s['runs'][s['current']]
    if b['reprepare'] is not None:
        R['reprepares'] = 1
    else:
        R['status'], s['current'] = 'ABANDONED', None
        s['notify'] = {'seq': e['seq'], 'what': 'ASK_USER', 'about': None}
    return _restore_common(s, e)


def _restore_ok(e):
    b = e['body']
    return b['kit_sha256'] == e['kit_sha256'] and b['fingerprint_sha256'] == e['fingerprint_sha256']


def _restore_common(s, e):
    s['restores'] += 1
    s['release_sha256'], s['kit_sha256'] = e['release_sha256'], e['kit_sha256']
    s['passes'][e['fingerprint_sha256']] = e['body']['pass']
    return s


def _items_check(s2, e, c):
    """[(item, row, action, owner_check)] or None: every item resolves, the set equals open(s2), one START at most."""
    b = e['body']
    out = []
    for it in b['resolutions']:
        rid, act, oc = resolution_action(s2, it, has_transcript(e, it['role'], it['attempt'], it['start_no']))
        if act is None or it['action'] != act or it['owner_check'] is not oc:
            return None
        out.append((it, rid, act, oc))
    if sorted((it['run'], it['role'] + str(it['attempt'])) for it in b['resolutions']) != sorted(open_roles(s2)):
        return None
    need = [x for x in out if x[2] in START_ACTIONS]
    if len(need) > 1 or (b['start'] is not None) != bool(need):
        return None
    if need:
        it, _, act, _ = need[0]
        ro = s2['runs'][it['run']]['roles'][it['role'] + str(it['attempt'])]
        st = b['start']
        if (st['role'], st['attempt'], st['start_no'], st['reason']) != start_for(act, ro) \
                or st['utc'] != e['utc'] or st['boot_id'] != e['boot_id'] \
                or st['prompt_sha256'] != latest(ro)['prompt_sha256'] or st['prompt'] != latest(ro)['prompt']:
            return None
    return out


def g42(s, e, c):
    b, cur = e['body'], s['current']
    if b['reprepare'] is not None or b['abandon'] is not None or not _restore_ok(e):
        return False
    if not c['Q'] and cur and s['runs'][cur]['status'] == 'INPUTS':
        return False
    s2 = _restore_state(s, e, c)
    if s2 is None or _items_check(s2, e, c) is None:
        return False
    R = s2['runs'].get(s2['current']) if s2['current'] else None
    dq = not c['Q'] and R is not None and (R['delivery'] or {}).get('prepared_seq') is not None \
        and not R['delivery']['sent']
    if (b['delivery_question'] is not None) != dq or (dq and b['delivery_question'].get('run') != s2['current']):
        return False
    rx = b['rerun_expected']
    return rx is None or (R is not None and R['status'] == 'ACTIVE' and rx.get('run') == s2['current']
                          and not open_roles(s2) and b['rebase'] is None and R['rebase_bind'] is None and not dq)


def e42(s, e, c):
    b = e['body']
    s = _restore_state(s, e, c)
    for it, rid, act, oc in _items_check(s, e, c):
        R = s['runs'][it['run']]
        ro = R['roles'][it['role'] + str(it['attempt'])]
        ro['resolution'] = {'seq': e['seq'], 'outcome': it['outcome'], 'forced': it['forced'], 'action': act,
                            'transcript': it['transcript'], 'owner_check': oc}
        if oc:
            _flag(R, 'OWNER_CHECK')
        if act == 'SUPERSEDE':
            latest(ro)['superseded_by'] = b['start']['start_no']
            ro['starts'].append(_start_rec(b['start'], e['seq']))
            ro['supersedes'] = 1
            _flag(R, 'START_SUPERSEDED')
            continue
        ro['status'] = 'RESOLVED'
        if act in ('EVERYDAY_RETRY', 'REPLACE'):
            R['roles'][b['start']['role'] + str(b['start']['attempt'])] = _new_role(b['start'], e['seq'])
            if act == 'REPLACE':
                R['replacements'] = 1
    if b['delivery_question'] is not None:
        s['notify'] = {'seq': e['seq'], 'what': 'ASK_USER', 'about': 'DELIVERY'}
        s['runs'][s['current']]['delivery']['resend_ok'] = False
    if b['rerun_expected'] is not None:
        s['runs'][s['current']]['rerun_expected'] = {'seq': e['seq'], 'stage': b['rerun_expected'].get('stage')}
    return _restore_common(s, e)


# ---------------------------------------------------------------- ACK, DELIVERY, HALT, CLEAR, FINAL, GENESIS
ACK_KEYS = {('NOTIFY_OWNER', None): ('notified', ('yes',)), ('ASK_USER', None): ('asked', ('yes',)),
            ('ASK_USER', 'DELIVERY'): ('arrived', ('yes', 'no'))}


def g52(s, e, c):
    b, n = e['body'], s['notify']
    want = ACK_KEYS.get((n['what'], n['about'])) if n else None
    return want is not None and n['seq'] == b['for_seq'] and n['what'] == b['what'] \
        and list(b['answer']) == [want[0]] and b['answer'][want[0]] in want[1]


def e52(s, e, c):
    n, ans = s['notify'], e['body']['answer']
    s['notify'] = None
    if n['about'] == 'DELIVERY':
        d = s['runs'][s['current']]['delivery']
        d['ack_seq'] = e['seq']
        if ans['arrived'] == 'yes':
            d['sent'] = True
        else:
            d['resend_ok'] = True
    return s


def g55(s, e, c):
    b, cur = e['body'], s['current']
    R = s['runs'].get(cur) if cur else None
    return not c['Q'] and R is not None and b['run'] == cur and R['status'] == 'ACTIVE' and not run_open(R) \
        and R['next'] == 'DELIVER' and (R['delivery'] or {}).get('prepared_seq') is None \
        and R['saved_qa'] is not None and b['standard_sha256'] == R['saved_qa'].get('deliverable_sha256') \
        and sorted((p['kind'], p['k']) for p in e['parts']) == [('DELIV', 1), ('DLOG', 1)]


def e55(s, e, c):
    R = s['runs'][s['current']]
    R['delivery'] = {'checked_seq': R['snapshot']['seq'], 'prepared_seq': e['seq'], 'sent': False, 'resend_ok': True,
                     'ack_seq': None}
    return s


def g58(s, e, c):
    return s['phase'] == 'OPEN' and e['body']['head_seq'] == s['seq']


def e58(s, e, c):
    s['phase'], s['halt'] = 'HALTED', {'seq': e['seq'], 'code': e['body']['code']}
    return s


def g59(s, e, c):
    b, h = e['body'], s['halt']
    kc = b['kit_change']
    return s['phase'] == 'HALTED' and h is not None and b['halt_seq'] == h['seq'] and b['code'] == h['code'] \
        and b['kit_sha256'] == e['kit_sha256'] and kc['from_kit_sha256'] == s['kit_sha256'] \
        and kc['config_only'] is True and config_only(kc['from_members'], kc['to_members'])


def e59(s, e, c):
    s['clears'].append({'seq': e['seq'], 'halt_seq': s['halt']['seq'], 'code': s['halt']['code']})
    s['phase'], s['halt'], s['kit_sha256'] = 'OPEN', None, e['kit_sha256']
    return s


def final_ready(s):
    """T62's guard: every (case, reader) chain of genesis.jobs ends in a FROZEN run and no restart is owed."""
    if not is_q(s) or s['current'] is not None or open_roles(s) or s['notify'] is not None:
        return False
    for job in s['genesis']['jobs'] or []:
        for rd in ('A', 'B'):
            ch = chain(s, job[0], rd)
            L = s['runs'][ch[-1]] if ch else None
            if L is None or L['status'] != 'FROZEN':
                return False
            if not nonattempt(job) and L['restart_of'] is None and L['frozen']['restart_eligible'] \
                    and 'RESET_DIVERGED' not in L['flags']:
                return False
    return True


def g62(s, e, c):
    return final_ready(s)


def e62(s, e, c):
    s['phase'], s['final'] = 'FINAL', {'seq': e['seq']}
    return s


def t01(e):
    b = e['body']
    mode, q = mode_of(e['series']), e['series'][0] in 'QD'
    if b['mode'] != mode or q != (b['jobs'] is not None) or q != (b['ledger'] is not None) \
            or (e['series'][0] == 'Q') != (b['other_series_absent'] is not None):
        raise ChainInvalid('SCHEMA_INVALID')
    return {'schema': 'cps.vm2-state.v1', 'series': e['series'], 'mode': mode, 'seq': 1, 'phase': 'OPEN',
            'genesis': {'seq': 1, 'utc': e['utc'], 'release_sha256': e['release_sha256'],
                        'kit_sha256': e['kit_sha256'], 'jobs': b['jobs'], 'ledger': b['ledger'], 'home': e['home'],
                        'uid': e['uid'], 'base': b['layout'].get('base'), 'gates': b['gates']},
            'release_sha256': e['release_sha256'], 'kit_sha256': e['kit_sha256'], 'halt': None, 'clears': [],
            'current': None, 'runs': {}, 'order': [], 'files': {}, 'passes': {e['fingerprint_sha256']: b['pass']},
            'boots': [], 'notify': None, 'ledger': None, 'undo': None, 'final': None, 'restores': 0}


# ---------------------------------------------------------------- the table
def _neg(s, e, c):
    return False


g20t, e20t = _row_progress('T20')
g21t, e21t = _row_progress('T21')
g23t, e23t = _row_progress('T23')
g24t, e24t = _row_progress('T24')
_ALL = frozenset(E.KINDS)
_T06 = frozenset({'INPUTS', 'STAGE', 'FROZEN', 'DELIVERY', 'OPENED', 'AI'})
TABLE = (
    Row('T01', {'GENESIS'}, 'series', None, None, 'GENESIS on an empty series'),
    Row('T02', {'GENESIS'}, 'series', None, None, 'GENESIS on a non-empty series'),
    Row('T03', _ALL - {'GENESIS'}, 'series', None, None, 'any entry but GENESIS on an empty series'),
    Row('T04', _ALL - {'RESTORE', 'CLEAR'}, 'series', None, None, 'only RESTORE or CLEAR while HALTED'),
    Row('T05', _ALL, 'series', None, None, 'nothing after FINAL'),
    Row('T06', _T06, 'series', None, None, 'an owner notice or user question is answered first'),
    Row('T10', {'STAGE', 'FROZEN'}, 'positive', g10, e_new, 'Q new run A/B'),
    Row('T11', {'STAGE', 'FROZEN'}, 'positive', g11, e_new, 'Q restart run'),
    Row('T12', {'FROZEN'}, 'positive', g12, e_new, 'Q nonattempt run'),
    Row('T13', {'STAGE', 'FROZEN'}, 'positive', g13, e_new, 'E prepare of the INPUTS run'),
    Row('T14', {'STAGE', 'FROZEN'}, 'fallback', None, None, 'new_run and none of T10-T13'),
    Row('T15', {'INPUTS'}, 'positive', g15, e15, 'E inputs of a new job'),
    Row('T16', {'INPUTS'}, 'fallback', None, None, 'INPUTS otherwise'),
    Row('T20', {'STAGE'}, 'positive', g20t, e20t, 'stage progress'),
    Row('T21', {'STAGE'}, 'positive', g21t, e21t, 'REVIEW_CONTINUABLE refusal: V continued'),
    Row('T22', {'STAGE'}, 'negative', _neg, None, 'a third continuable refusal'),
    Row('T23', {'STAGE'}, 'positive', g23t, e23t, 'runner refusal that changed the record: HALTED'),
    Row('T24', {'FROZEN'}, 'positive', g24t, e24t, 'run frozen'),
    Row('T25', {'STAGE', 'FROZEN'}, 'fallback', None, None, 'progress otherwise'),
    Row('T30', {'STAGE'}, 'sub', None, None, 'START reason STAGE'),
    Row('T31', {'STAGE'}, 'sub', None, None, 'START reason REBASE'),
    Row('T32', {'STAGE'}, 'negative', None, None, 'any other START'),
    Row('T35', {'OPENED'}, 'positive', g35, e35, 'role opened'),
    Row('T36', {'OPENED'}, 'fallback', None, None, 'OPENED otherwise'),
    Row('T37', {'AI'}, 'positive', g37, e37, 'AI revision 1'),
    Row('T38', {'AI'}, 'positive', g38, e37, 'AI after a continuation'),
    Row('T39', {'AI'}, 'fallback', None, None, 'AI otherwise'),
    Row('T41', {'RESTORE'}, 'positive', g41, e41, 'E INPUTS run: reprepare or abandon'),
    Row('T42', {'RESTORE'}, 'positive', g42, e42, 'restore'),
    Row('T43', {'RESTORE'}, 'sub', None, None, 'NO_CONVERSATION: SUPERSEDE'),
    Row('T44', {'RESTORE'}, 'sub', None, None, 'S/G NOTHING_WRITTEN'),
    Row('T45', {'RESTORE'}, 'sub', None, None, 'V NOTHING_WRITTEN'),
    Row('T46', {'RESTORE'}, 'sub', None, None, 'V CONTINUED'),
    Row('T47', {'RESTORE'}, 'sub', None, None, 'WRITTEN, UNSURE or forced'),
    Row('T48', {'RESTORE'}, 'negative', None, None, 'an item matching none of T43-T47'),
    Row('T49', {'RESTORE'}, 'sub', None, None, 'rebase undo'),
    Row('T50', {'RESTORE'}, 'fallback', None, None, 'RESTORE otherwise'),
    Row('T52', {'ACK'}, 'positive', g52, e52, 'acknowledgement'),
    Row('T53', {'ACK'}, 'fallback', None, None, 'ACK otherwise'),
    Row('T55', {'DELIVERY'}, 'positive', g55, e55, 'everyday personal copy prepared'),
    Row('T56', {'DELIVERY'}, 'fallback', None, None, 'DELIVERY otherwise'),
    Row('T58', {'HALT'}, 'positive', g58, e58, 'halt'),
    Row('T59', {'CLEAR'}, 'positive', g59, e59, 'clear by a config-only kit'),
    Row('T60', {'HALT', 'CLEAR'}, 'fallback', None, None, 'HALT/CLEAR otherwise'),
    Row('T62', {'FINAL'}, 'positive', g62, e62, 'qualification complete'),
    Row('T63', {'FINAL'}, 'fallback', None, None, 'FINAL otherwise'),
)
ROWS = {r.id: r for r in TABLE}


def _fallback(s, e, c):
    """The ChainInvalid code when no positive row matches (§4.1: fallback rows are never guards)."""
    k, b = e['kind'], e['body']
    if k in ('STAGE', 'FROZEN'):
        if b['new_run'] is not None:
            return 'T14'
        if not _pre(s, e) or run_open(s['runs'][b['run']]):
            return 'T25'
        R = s['runs'][b['run']]
        if k == 'STAGE' and g22(s, R, e, c):
            return 'T22'
        if k == 'STAGE' and start_problem(s, R, e) == 'T32':
            return 'T32'
        return 'T25'
    if k == 'RESTORE':
        s2 = _restore_state(s, e, c)
        if s2 is not None and b['reprepare'] is None and b['abandon'] is None:
            for it in b['resolutions']:
                _, act, oc = resolution_action(s2, it, has_transcript(e, it['role'], it['attempt'], it['start_no']))
                if act is None or act != it['action'] or oc is not it['owner_check']:
                    return 'T48'
        return 'T50'
    return {'INPUTS': 'T16', 'OPENED': 'T36', 'AI': 'T39', 'ACK': 'T53', 'DELIVERY': 'T56', 'HALT': 'T60',
            'CLEAR': 'T60', 'FINAL': 'T63'}[k]


def _trace_subs(s, e, c, rid):
    b, out = e['body'], []
    if rid in ('T10', 'T11', 'T13', 'T20') and b.get('start'):
        out.append('T30' if b['start']['reason'] == 'STAGE' else 'T31')
    if rid == 'T42':
        if b['rebase'] is not None:
            out.append('T49')
        out += [x[1] for x in _items_check(_restore_state(s, e, c), e, c)]
    return out


def apply_traced(state, entry):
    """apply() that also returns the row ids used: [top row] + sub rows (T30/T31, T49, T43-T47)."""
    try:
        return _apply(state, entry)
    except ChainInvalid:
        raise
    except (KeyError, TypeError, AttributeError, ValueError, IndexError):
        raise ChainInvalid('SCHEMA_INVALID')


def apply(state, entry):
    """The fold (§4.1). See the module docstring for the contract."""
    return apply_traced(state, entry)[0]


def _apply(state, e):
    structural(state, e)
    kind = e['kind']
    if state is None:
        if kind != 'GENESIS':
            raise ChainInvalid('T03')
        s, rows = t01(e), ['T01']
    else:
        if kind == 'GENESIS':
            raise ChainInvalid('T02')
        if state['phase'] == 'HALTED' and kind not in ('RESTORE', 'CLEAR'):
            raise ChainInvalid('T04')
        if state['phase'] == 'FINAL':
            raise ChainInvalid('T05')
        if kind in _T06 and state['notify'] is not None:
            raise ChainInvalid('T06')
        c = {'Q': is_q(state), 'mode': state['mode'], 'gates': state['genesis']['gates']}
        hits = [r for r in TABLE if r.kind_of == 'positive' and kind in r.kinds and r.guard(state, e, c)]
        if len(hits) > 1:
            raise ChainInvalid('AMBIGUOUS_ROWS')
        if not hits:
            raise ChainInvalid(_fallback(state, e, c))
        rows = [hits[0].id] + _trace_subs(state, e, c, hits[0].id)
        s = hits[0].effect(clone(state), e, c)
    _finish(state, s, e)
    return s, rows


def _finish(state, s, e):
    b, seq = e['body'], e['seq']
    s['seq'] = seq
    for cf in e['confirms']:
        if cf['copies']:
            s['files'][cf['name']] = [[cp['id'], cp['md5'], cp['size']] for cp in cf['copies']]
    if not any(x[0] == e['boot_id'] for x in s['boots']):
        s['boots'].append([e['boot_id'], seq])
    lm = E.member(e, 'ledger/LEDGER.jsonl')
    if lm is not None:
        s['ledger'] = {'seq': seq, 'sha256': lm[4], 'bytes': lm[3]}
    parts = [[p['name'], p['md5'], p['bytes']] for p in e['parts']]
    if e['kind'] in ('STAGE', 'FROZEN', 'DELIVERY'):
        s['undo'] = {'seq': seq, 'kind': e['kind'], 'run': b['run'],
                     'before': clone(state['runs'].get(b['run'])), 'current_before': state['current'],
                     'ledger_before': clone(state['ledger']), 'notify_before': clone(state['notify']),
                     'start': clone(b.get('start')), 'parts': parts}
    else:
        s['undo'] = {'seq': seq, 'kind': e['kind'], 'run': None, 'before': None, 'current_before': None,
                     'ledger_before': None, 'notify_before': None, 'start': None, 'parts': parts}
