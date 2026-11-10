"""Test support for the core tests (§14.1): a World that builds ENTRY drafts with invented values, a generator of
legal next entries written from the spec's row texts (§4.3, §7.1, §7.3, §8.6), illegal-entry mutations, and the §4.7
invariant checks. The generator does not call the fold's guards; it only reads the fold state as data."""
import copy
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cpsvm2.core import fold as F                                    # noqa: E402
from cpsvm2.core.names import RUNNER_SHA256, cjson, entry_name, part_name, sha  # noqa: E402

T0 = 1793000000          # 2026-10-26
REL, REL2 = sha(b'release-1'), sha(b'release-2')
KIT, KIT2 = sha(b'kit-1'), sha(b'kit-2')
TREE = sha(b'helper-tree')
FP = sha(b'fingerprint')
MEMBERS = [['RELEASE.json', sha(b'r')], ['VM_HELPER_CONFIG.json', sha(b'c1')], ['tables/t.json', sha(b't')]]
GATES = {'p1_vm_files': 'PASS', 'p1_transcript_export': 'yes', 'p1_conversation_list': 'yes',
         'p1_end_after_reset': 'yes', 'p2_exact_search': 'PASS', 'p2_md5_visible': 'yes', 'p2_prefix_search': 'no',
         'p2_newest_first': 'no', 'p2_lag_seconds': 20, 'p2_max_upload_bytes': 300000000, 'p2_tgz_kept': 'PASS',
         'p2_failed_upload_can_appear': 'no', 'p3_identity_stable': 'yes', 'p5_detached': 'PASS',
         'p5_tool_call_seconds': 600, 'p5_setup_seconds': 300}
JOBS = [['case01', 1, None], ['case02', 2, None], ['case03', 3, 'NONATTEMPT_SOURCE_UNAVAILABLE']]
BASE = '/home/agent/cps'


def md5ish(x):
    return hashlib.md5(x.encode('ascii')).hexdigest()


def utc(t):
    import time
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t))


def boot(n):
    h = hashlib.sha256(b'boot%d' % n).hexdigest()
    return '%s-%s-%s-%s-%s' % (h[:8], h[8:12], h[12:16], h[16:20], h[20:32])


def hx(*a):
    return sha(repr(a).encode())


class World:
    """One series. commit(e) folds e with fold.apply_traced and keeps it; the World never edits the state."""

    def __init__(self, series='Q1', gates=None, jobs=None, rng=None):
        self.series, self.gates = series, dict(GATES, **(gates or {}))
        self.jobs = copy.deepcopy(JOBS if jobs is None else jobs)
        self.state, self.entries, self.rows = None, [], []
        self.t, self.nboot, self.rng, self.kit = T0, 1, rng, KIT
        self.boot = boot(1)

    def now(self):
        self.t += 61
        return utc(self.t)

    def reset(self):
        self.nboot += 1
        self.boot = boot(self.nboot)

    def entry(self, kind, body, parts=(), members=(), kit=None, release=None, boot_id=None, confirms=None):
        s = self.state
        seq = 1 if s is None else s['seq'] + 1
        if confirms is None:
            confirms = [] if s is None else [{'name': entry_name(self.series, s['seq']), 'copies': [
                {'id': 'ID' + md5ish('e%d' % s['seq']), 'md5': md5ish('e%d' % s['seq']), 'size': 1000}]}] + [
                {'name': p[0], 'copies': [{'id': 'ID' + p[1], 'md5': p[1], 'size': p[2]}]} for p in s['undo']['parts']]
        ps = [{'name': part_name(self.series, seq, k, i), 'kind': k, 'k': i, 'folder': 'CPS/qualification',
               'sha256': hx('part', seq, k, i), 'md5': md5ish('p%d%s%d' % (seq, k, i)), 'bytes': 2000 + i}
              for k, i in parts]
        e = {'schema': 'cps.vm2-entry.v1', 'series': self.series, 'seq': seq, 'name': entry_name(self.series, seq),
             'prev_sha256': None if seq == 1 else hx('entry', seq - 1), 'kind': kind, 'body': body,
             'utc': self.now(), 'boot_id': boot_id or self.boot, 'uid': 1000, 'home': '/home/agent',
             'fingerprint_sha256': FP, 'helper': {'version': 'cps-vm-helper.v2', 'tree_sha256': TREE},
             'runner_sha256': RUNNER_SHA256, 'kit_sha256': kit or (s['kit_sha256'] if s else self.kit),
             'release_sha256': release or (s['release_sha256'] if s else REL), 'confirms': confirms, 'parts': ps,
             'payload': {'members': sorted(members, key=lambda m: m[0]), 'png': None}, 'cleared_local': None}
        if body is not None and isinstance(body.get('start'), dict) and body['start'].get('utc') is None:
            body['start'].update(utc=e['utc'], boot_id=e['boot_id'])
        return e

    def commit(self, e):
        self.state, rows = F.apply_traced(self.state, e)
        self.entries.append(e)
        self.rows.append(rows)
        return rows


# ------------------------------------------------------------------ body builders
def ledger_members(seq):
    return [['ledger', 'dir', 0o755, None, None], ['ledger/LEDGER.jsonl', 'file', 0o644, 100 + seq, hx('ledger', seq)]]


def genesis(w):
    q = w.series[0] in 'QD'
    b = {'mode': F.mode_of(w.series), 'operator': {'model': 'gpt-x', 'platform': 'chat'},
         'jobs': w.jobs if q else None, 'ledger': {'identity_line_sha256': hx('id'), 'ledger_id': 'L1'} if q else None,
         'layout': {'base': BASE, 'qual': BASE + '/qual', 'jobs': BASE + '/jobs', 'ledger': BASE + '/ledger',
                    'runtime': BASE + '/runtime'},
         'gates': w.gates, 'pass': {'name': 'FINGERPRINT_PASS_%s.json' % FP, 'md5': md5ish('pass')},
         'other_series_absent': [] if w.series[0] == 'Q' else None}
    return w.entry('GENESIS', b, members=ledger_members(1) if q else [])


def cmd(sub, nxt, result='NEXT', codes=(), rec=None, led=None):
    return {'sub': sub, 'exit': 4 if result == 'REFUSED' else (3 if nxt.startswith('STOP_') else 0), 'result': result,
            'next': nxt, 'codes': list(codes), 'record_sha256_after': rec or hx('rec', sub, nxt, os.urandom(4)),
            'ledger_sha256_after': led, 'stdout_sha256': hx('out'), 'started_utc': None, 'ended_utc': None}


PROMPT = {'S': 'scope/reader/SCOPE_READER_PROMPT.md', 'G': 'run/GENERATOR_PROMPT.md', 'V': 'qa/VISUAL_REVIEW_PROMPT.md'}
OUTPUT = {'S': 'scope/reader/output', 'G': 'run/A/output', 'V': 'qa/visual_review'}


def start(job_dir, role, attempt, start_no, reason):
    return {'role': role, 'attempt': attempt, 'start_no': start_no, 'reason': reason,
            'prompt': job_dir + '/' + PROMPT[role], 'prompt_sha256': hx('prompt', job_dir, role),
            'folder': job_dir + '/' + PROMPT[role].rsplit('/', 1)[0], 'output': job_dir + '/' + OUTPUT[role],
            'utc': None, 'boot_id': None}


def stage_body(run, commands, nxt, **kw):
    b = {'run': run, 'new_run': None, 'prepare_inputs_sha256': None, 'commands': commands, 'next': nxt,
         'next_args': None, 'codes': [], 'consumed': [], 'start': None, 'review_incomplete': False,
         'continue_problems': None, 'refused': None, 'rerun': None, 'rebase': None,
         'snapshot': {'members': 3, 'tree_sha256': hx('snap', run, nxt, os.urandom(4))}, 'png': None,
         'saved_qa': None, 'carrier_sha256': None, 'generation_record_sha256': None, 'fingerprint_checked': True}
    b.update(kw)
    return b


def frozen_body(run, commands, final_next, flags=(), notify=None, **kw):
    b = stage_body(run, commands, 'DONE', **kw)
    b.update(frozen_sha256=hx('frozen', run), final_next=final_next, final_codes=[], restart_eligible=False,
             flags_added=list(flags), notify=notify, delivery_sent=False)
    for k in ('restart_eligible', 'delivery_sent'):
        if k in kw:
            b[k] = kw[k]
    return b


def job_dir(tag, case):
    root = {'A': 'A', 'B': 'B', 'A-restart1': 'A_restart1', 'B-restart1': 'B_restart1', 'NA-A': 'nonattempts_A',
            'NA-B': 'nonattempts_B'}.get(tag)
    return '%s/qual/%s/%s' % (BASE, root, case) if root else '%s/jobs/%s/%s' % (BASE, tag[1:], case)


def new_run(tag, case, restart_of=None):
    return {'tag': tag, 'case': case, 'reader': F.reader_of(tag), 'job_dir': job_dir(tag, case),
            'restart_of': restart_of}


def run_in_flight(s):
    return s['current'] is not None or any(r['status'] in ('STARTED', 'OPENED', 'CONTINUED')
                                           for R in s['runs'].values() for r in R['roles'].values())


def restore_body(w, resolutions=(), start_=None, **kw):
    s = w.state
    b = {'prev_boot_id': s['boots'][-1][0], 'operator': {'model': 'gpt-x', 'platform': 'chat'},
         'fingerprint_sha256': FP, 'pass': {'name': 'FINGERPRINT_PASS_%s.json' % FP, 'md5': md5ish('pass')},
         'head': {'seq': s['seq'], 'md5': md5ish('e%d' % s['seq']), 'copies': []}, 'lookups': [],
         'kit_sha256': w.kit, 'kit_change': None, 'resolutions': list(resolutions), 'start': start_, 'rebase': None,
         'rerun_expected': None, 'reprepare': None, 'abandon': None, 'delivery_question': None, 'placed': []}
    b.update(kw)
    return b


def kit_change(s, to_kit, rif=None, config_only=True):
    to = [m[:] for m in MEMBERS]
    to[1][1] = hx('cfg', to_kit) if config_only else to[1][1]
    if not config_only:
        to[0][1] = hx('rel', to_kit)
    return {'from_kit_sha256': s['kit_sha256'], 'to_kit_sha256': to_kit, 'from_members': MEMBERS, 'to_members': to,
            'config_only': config_only, 'config_keys_changed': ['clear'] if config_only else [],
            'run_in_flight': run_in_flight(s) if rif is None else rif, 'to_accepts_release_sha256': []}


# ------------------------------------------------------------------ independent oracles (from the spec text)
def latest(ro):
    return [x for x in ro['starts'] if x['superseded_by'] is None][-1]


def open_role(s):
    for k in s['order']:
        for rk, ro in sorted(s['runs'][k]['roles'].items()):
            if ro['status'] in ('STARTED', 'OPENED', 'CONTINUED'):
                return k, rk, ro
    return None


def oracle_item(s, run, rk, ans):
    """§8.6 steps 5-6 and T43-T47 restated: forced, action, owner_check for answers `ans`."""
    g, q = s['genesis']['gates'], s['mode'] != 'everyday'
    R = s['runs'][run]
    ro = R['roles'][rk]
    cont = ro['status'] == 'CONTINUED'
    adm = ro['status'] == 'STARTED' and ro['opened'] is None and ro['supersedes'] == 0 \
        and g['p1_conversation_list'] == 'yes'
    out = ans.get('outcome', 'CONTINUED') if not cont else 'CONTINUED'
    forced = None
    if g['p1_end_after_reset'] == 'no':
        forced = 'NOT_ENDABLE'
    elif ans['files_found']:
        forced = 'FILES_FOUND'
    elif not ans['ended']:
        forced = 'NOT_ENDED'
    elif out == 'NO_CONVERSATION':
        if g['p1_conversation_list'] == 'no' and ro['status'] == 'STARTED' and ro['opened'] is None:
            forced = 'NO_LIST'
        elif not (adm and ans.get('list_shows_none') is True):
            forced = 'NO_CONVERSATION_NOT_ALLOWED'
    oc = False
    if cont:
        act = 'FREEZE_VISUAL_FAILED'
    elif forced or out in ('WRITTEN', 'UNSURE'):
        act = 'FREEZE_VISUAL_FAILED' if ro['role'] == 'V' else 'FREEZE_LOST'
    elif out == 'NO_CONVERSATION':
        act = 'SUPERSEDE'
    elif ro['role'] in 'SG':
        oc = q and ans['transcript'] == 'not_available'
        if q:
            act = 'INTERRUPT'
        elif ans['transcript'] == 'not_available':
            act = 'FREEZE_LOST'
        else:
            act = 'EVERYDAY_RETRY' if ro['attempt'] == 1 else 'FREEZE_EXHAUSTED'
    else:
        oc = q and ans['transcript'] == 'not_available'
        act = 'REPLACE' if R['replacements'] == 0 and (q or ans['transcript'] == 'exported') \
            else 'FREEZE_VISUAL_FAILED'
    item = {'run': run, 'role': ro['role'], 'attempt': ro['attempt'], 'start_no': latest(ro)['start_no'],
            'ended': ans['ended'], 'files_found': ans['files_found'], 'outcome': out, 'forced': forced,
            'transcript': ans['transcript'], 'list_shows_none': ans.get('list_shows_none'), 'action': act,
            'owner_check': oc}
    st = None
    lt = latest(ro)
    if act == 'SUPERSEDE':
        st = dict(lt, start_no=lt['start_no'] + 1, reason='NO_CONVERSATION', utc=None, boot_id=None)
    elif act == 'EVERYDAY_RETRY':
        st = dict(lt, attempt=ro['attempt'] + 1, start_no=1, reason='EVERYDAY_RETRY', utc=None, boot_id=None)
    elif act == 'REPLACE':
        st = dict(lt, attempt=ro['attempt'] + 1, start_no=1, reason='REPLACEMENT', utc=None, boot_id=None)
    if st:
        for k in ('seq', 'superseded_by'):
            st.pop(k, None)
    return item, st


def pending(R):
    """The resolution whose action still has to run (§7.1 rows 12-13): INTERRUPT or a FREEZE_* after the snapshot."""
    rs = sorted((r['resolution'] for r in R['roles'].values() if r['resolution']), key=lambda r: r['seq'])
    snap = (R['snapshot'] or {}).get('seq') or 0
    p = rs[-1] if rs and rs[-1]['seq'] > snap else None
    return p if p and p['action'] in ('INTERRUPT', 'FREEZE_LOST', 'FREEZE_EXHAUSTED', 'FREEZE_VISUAL_FAILED') else None


def newest_v(R):
    vs = sorted((r['attempt'], k) for k, r in R['roles'].items() if r['role'] == 'V')
    return R['roles'][vs[-1][1]] if vs else None


def oracle_flags(R, cmds, diverged):
    """§4.6 restated."""
    fl, p = [], pending(R)
    a = p['action'] if p else None
    if a == 'FREEZE_LOST':
        fl.append('AI_OUTPUT_LOST')
    if a == 'FREEZE_VISUAL_FAILED':
        fl.append('VISUAL_QA_FAILED_BY_RESET')
    if a == 'FREEZE_EXHAUSTED' or (a == 'INTERRUPT' and any(c['next'] == 'INTERRUPT_RESTART_USED' for c in cmds)):
        fl.append('RESTART_EXHAUSTED_BY_RESET')
    V = newest_v(R)
    if V and V['review_incomplete'] == 2 and any(c['sub'] == 'visual-record' and c['result'] == 'REFUSED'
                                                 for c in cmds):
        fl.append('REVIEW_INCOMPLETE_LIMIT')
    if diverged:
        fl.append('RESET_DIVERGED')
    return fl


# ------------------------------------------------------------------ the legal-move generator
def _led(w):
    return w.series[0] in 'QD'


def _stage(w, b, parts=()):
    s = w.state
    seq = s['seq'] + 1
    if _led(w):
        for c in b['commands']:
            c['ledger_sha256_after'] = hx('ledger', seq)
    elif s['ledger']:
        for c in b['commands']:
            c['ledger_sha256_after'] = s['ledger']['sha256']
    return w.entry('FROZEN' if 'frozen_sha256' in b else 'STAGE', b, parts=parts,
                   members=ledger_members(seq) if _led(w) else [])


def _freeze_cmds(*first):
    return list(first) + [cmd('freeze', 'DONE'), cmd('verify-frozen', 'DONE')]


def _png(w, R):
    seq = w.state['seq'] + 1
    files = [['job/qa/visual_deliverable/p1.png', 0o444, 500, hx('png', R['key'], seq)]]
    return {'files': files, 'whole_sha256': hx('whole', R['key'], seq), 'parts_seq': seq}


def _consumed(R, rk):
    ro = R['roles'][rk]
    return [{'role': ro['role'], 'attempt': ro['attempt'], 'revision': ro['archives'][-1]['revision'],
             'tree_sha256': ro['archives'][-1]['tree_sha256']}]


def _notify_for(w, final_next, flags, delivered):
    stop = final_next.startswith('STOP_') or final_next == 'OWNER_DECISION'
    if w.series[0] != 'E':
        return 'NOTIFY_OWNER' if stop else None
    return None if delivered else ('NOTIFY_OWNER' if stop else 'ASK_USER')


def moves(w):
    """[(label, thunk)] of legal next entries from w.state (thunk() builds the entry with the World's clock)."""
    s, out = w.state, []
    if s is None:
        return [('GENESIS', lambda: genesis(w))]
    if s['phase'] == 'FINAL':
        return []
    out.append(('HALT', lambda: w.entry('HALT', {'code': 'UNCLASSIFIED', 'detail': {}, 'head_seq': s['seq']},
                                        boot_id='unknown-boot'))) if s['phase'] == 'OPEN' else None
    out += _restore_moves(w)
    if s['phase'] == 'HALTED':
        h = s['halt']
        out.append(('CLEAR', lambda: _clear(w, h)))
        return out
    if s['notify'] is not None:
        n = s['notify']
        if n['about'] == 'DELIVERY':
            for a in ('yes', 'no'):
                out.append(('ACK_' + a, lambda a=a: w.entry('ACK', {'for_seq': n['seq'], 'what': n['what'],
                                                                    'answer': {'arrived': a}})))
        else:
            key = 'notified' if n['what'] == 'NOTIFY_OWNER' else 'asked'
            out.append(('ACK', lambda: w.entry('ACK', {'for_seq': n['seq'], 'what': n['what'],
                                                       'answer': {key: 'yes'}})))
        return out
    cur = s['current']
    R = s['runs'].get(cur) if cur else None
    op = open_role(s)
    if op:
        out += _open_moves(w, *op)
        return out
    if R is None:
        out += _new_run_moves(w)
        return out
    if R['status'] == 'INPUTS':
        out.append(('PREPARE_E', lambda: _prepare(w, R['tag'], R['case'], 'GENERATE')))
        return out
    out += _progress_moves(w, R)
    return out


def _clear(w, h):
    nk = hx('kit', w.state['seq'])
    w.kit = nk
    return w.entry('CLEAR', {'halt_seq': h['seq'], 'code': h['code'], 'kit_sha256': nk,
                             'kit_change': kit_change(w.state, nk)}, kit=nk)


def _prepare(w, tag, case, nxt, restart_of=None):
    s = w.state
    nr = new_run(tag, case, restart_of)
    run = tag + '/' + case
    role = {'GENERATE': 'G', 'SCOPE_READER': 'S'}.get(nxt)
    kw = {'new_run': nr, 'start': start(nr['job_dir'], role, 1, 1, 'STAGE') if role else None}
    if s['mode'] == 'everyday':
        kw['prepare_inputs_sha256'] = s['runs'][s['current']]['inputs']['sha256']
    if role:
        return _stage(w, stage_body(run, [cmd('prepare', nxt)], nxt, **kw))
    kw['restart_eligible'] = tag in ('A', 'B')
    fz = frozen_body(run, _freeze_cmds(cmd('prepare', nxt)), nxt, notify=_notify_for(w, nxt, [], False), **kw)
    return _stage(w, fz)


def _new_run_moves(w):
    s, out = w.state, []
    if s['mode'] == 'everyday':
        tag = 'E' + utc(w.t + 61).replace('-', '').replace(':', '')
        tag = tag[:9] + 'T' + tag[10:16] + 'Z'
        case = 'job%d' % (len(s['runs']) + 1)
        inputs = {'job_sha256': hx('j', case), 'title_sha256': hx('t', case), 'source_name': 'src.xlsx',
                  'source_sha256': hx('s', case)}
        out.append(('INPUTS', lambda: w.entry('INPUTS', {'tag': tag, 'case': case, 'inputs': inputs,
                                                         'request_utc': utc(w.t)})))
        return out
    jobs = sorted(s['genesis']['jobs'], key=lambda j: j[1])
    ch = lambda c, r: [k for k in s['order'] if s['runs'][k]['case'] == c and s['runs'][k]['reader'] == r]  # noqa
    for rd in 'AB':
        for j in jobs:
            if j[2] and not ch(j[0], rd) and (rd == 'A' or ch(j[0], 'A')):
                run = 'NA-%s/%s' % (rd, j[0])
                out.append(('NA', lambda rd=rd, j=j, run=run: _stage(w, frozen_body(
                    run, [cmd('nonattempt', 'DONE'), cmd('verify-frozen', 'DONE')], 'DONE',
                    new_run=new_run('NA-' + rd, j[0])))))
    for j in jobs:
        if j[2]:
            continue
        a, b = ch(j[0], 'A'), ch(j[0], 'B')
        LA = s['runs'][a[-1]] if a else None
        cand = []
        if not a:
            cand.append(('A', None))
        elif len(a) == 1 and LA['status'] == 'FROZEN' and LA['frozen']['restart_eligible'] \
                and 'RESET_DIVERGED' not in LA['flags'] and not LA['interrupts'] and not b:
            cand.append(('A-restart1', a[0]))
        if not b and LA and LA['status'] == 'FROZEN' and (not LA['frozen']['restart_eligible']
                                                          or LA['tag'] == 'A-restart1'
                                                          or 'RESET_DIVERGED' in LA['flags']):
            cand.append(('B', None))
        if b:
            LB = s['runs'][b[-1]]
            if len(b) == 1 and LB['status'] == 'FROZEN' and LB['frozen']['restart_eligible'] \
                    and 'RESET_DIVERGED' not in LB['flags'] and not LB['interrupts']:
                cand.append(('B-restart1', b[0]))
        for tag, ro in cand:
            for nxt in ('SCOPE_READER', 'GENERATE', 'STOP_SOURCE_UNREADABLE'):
                out.append(('PREPARE_' + nxt, lambda tag=tag, ro=ro, nxt=nxt, c=j[0]: _prepare(w, tag, c, nxt, ro)))
    if _final_ready(s):
        out.append(('FINAL', lambda: w.entry('FINAL', {'all_frozen_sha256': hx('af'), 'ledger_final_sha256': hx('lf'),
                                                       'runs': len(s['runs']), 'outcomes_sha256': hx('o')},
                                             parts=[('LEDGER', 1), ('ALLFZ', 1)])))
    return out


def _final_ready(s):
    if s['mode'] == 'everyday' or s['current'] or s['notify'] or open_role(s):
        return False
    for j in s['genesis']['jobs']:
        for rd in 'AB':
            ch = [k for k in s['order'] if s['runs'][k]['case'] == j[0] and s['runs'][k]['reader'] == rd]
            if not ch or s['runs'][ch[-1]]['status'] != 'FROZEN':
                return False
            L = s['runs'][ch[-1]]
            if not j[2] and L['restart_of'] is None and L['frozen']['restart_eligible'] \
                    and 'RESET_DIVERGED' not in L['flags']:
                return False
    return True


def _open_moves(w, run, rk, ro):
    s, out = w.state, []
    g = s['genesis']['gates']
    lt = latest(ro)
    if ro['status'] == 'STARTED' and g['p1_conversation_list'] == 'no' and ro['opened'] is None:
        out.append(('OPENED', lambda: w.entry('OPENED', {'run': run, 'role': ro['role'], 'attempt': ro['attempt'],
                                                         'start_no': lt['start_no'], 'conversation': 'conv-%s' % rk,
                                                         'opened_utc': utc(w.t)})))
    if (ro['status'] == 'OPENED' or (ro['status'] == 'STARTED' and g['p1_conversation_list'] == 'yes')) \
            and lt['boot_id'] == w.boot:
        out.append(('AI', lambda: _ai(w, run, ro, 1, lt)))
    if ro['status'] == 'CONTINUED' and ro['continued_boot'] == w.boot:
        out.append(('AI_CONT', lambda: _ai(w, run, ro, len(ro['archives']) + 1, lt)))
    return out


def _ai(w, run, ro, rev, lt):
    tr = {'status': 'exported', 'sha256': hx('tr'), 'ext': 'json'} if ro['role'] == 'G' else None
    att = {'G': {'platform': 'chat', 'model': 'm', 'effort': 'high', 'started_utc': lt['utc'], 'ended_utc': lt['utc'],
                 'single_user_message': True, 'features': {}, 'tools': [], 'transcript_status': 'exported'},
           'S': {'prompt_pasted': True}, 'V': {}}[ro['role']]
    b = {'run': run, 'role': ro['role'], 'attempt': ro['attempt'], 'revision': rev, 'start_no': lt['start_no'],
         'start_boot_id': lt['boot_id'], 'ended': True, 'conversation': 'conv-%s%d' % (ro['role'], ro['attempt']),
         'attested': att, 'tree_sha256': hx('tree', run, ro['role'], ro['attempt'], rev), 'files': [],
         'transcript': tr, 'final_message_sha256': hx('fm') if ro['role'] == 'G' else None}
    return w.entry('AI', b, members=[['ai', 'dir', 0o755, None, None]])


def _progress_moves(w, R):
    s, out, run = w.state, [], R['key']
    q = s['mode'] != 'everyday'
    rx = R.get('rerun_expected')
    extra = {'rerun': {'after_seq': rx['seq'], 'unbound': True}} if rx else {}
    pr = pending(R)
    if R['rebase_bind']:
        return _rebase_rerun_moves(w, R)
    if pr and pr['action'] == 'INTERRUPT':
        g1 = R['roles'].get('G1')
        if g1 and g1['resolution'] is pr and not R['interrupts'] and R['restart_of'] is None and 'G2' not in R['roles']:
            out.append(('INTERRUPT_IN_PLACE', lambda: _stage(w, stage_body(
                run, [cmd('interrupt', 'GENERATE')], 'GENERATE', start=start(R['job_dir'], 'G', 2, 1, 'STAGE'),
                **extra))))
        for c in (cmd('interrupt', 'STOP_TECHNICAL_INTERRUPTION'),
                  cmd('interrupt', 'INTERRUPT_RESTART_USED', result='REFUSED')):
            out.append(('INTERRUPT_FREEZE', lambda c=c: _frz(w, R, [c], c['next'] if c['result'] == 'NEXT'
                                                             else R['next'], extra)))
        return out
    if pr:
        out.append(('FREEZE_' + pr['action'], lambda: _frz(w, R, [], R['next'], extra)))
        return out
    arch = sorted(k for k, r in R['roles'].items() if r['status'] == 'ARCHIVED' and not r['consumed'])
    if arch:
        rk = arch[0]
        role = R['roles'][rk]['role']
        cons = _consumed(R, rk)
        if role == 'S':
            out.append(('SCOPE_FINISH', lambda: _stage(w, stage_body(
                run, [cmd('scope-finish', 'GENERATE')], 'GENERATE', consumed=cons,
                start=start(R['job_dir'], 'G', 1, 1, 'STAGE'), **extra))))
        elif role == 'G':
            out.append(('FINISH', lambda: _stage(w, stage_body(
                run, [cmd('finish', 'VISUAL_REVIEW')], 'VISUAL_REVIEW', consumed=cons, png=_png(w, R),
                start=start(R['job_dir'], 'V', 1, 1, 'STAGE'), generation_record_sha256=hx('gr'),
                saved_qa={'sha256': hx('sq', run), 'deliverable_sha256': hx('dl', run)}, carrier_sha256=hx('car', run),
                **extra), parts=[('PNG', 1), ('PNG', 2)])))
            out.append(('FINISH_STOP', lambda: _frz(w, R, [cmd('finish', 'STOP_ROUTE_CHECK_FAILED')],
                                                    'STOP_ROUTE_CHECK_FAILED', extra, consumed=cons)))
        else:
            V = R['roles'][rk]
            if q:
                out.append(('VISUAL_PASS', lambda: _frz(w, R, [cmd('visual-record', 'FREEZE')], 'FREEZE', extra,
                                                        consumed=cons)))
                out.append(('VISUAL_FAIL', lambda: _frz(w, R, [cmd('visual-record', 'STOP_VISUAL_REVIEW_FAILED')],
                                                        'STOP_VISUAL_REVIEW_FAILED', extra, consumed=cons)))
            else:
                out.append(('DELIVER_CHECK', lambda: _stage(w, stage_body(
                    run, [cmd('visual-record', 'DELIVER_CHECK'), cmd('deliver-check', 'DELIVER')], 'DELIVER',
                    consumed=cons, **extra))))
            rc = cmd('visual-record', 'REVIEW_INCOMPLETE', result='REFUSED')
            if V['review_incomplete'] < 2:
                out.append(('REVIEW_INCOMPLETE', lambda: _stage(w, stage_body(
                    run, [rc], 'VISUAL_REVIEW', review_incomplete=True, refused='REVIEW_INCOMPLETE',
                    continue_problems=3, **extra))))
            else:
                out.append(('REVIEW_LIMIT', lambda: _frz(w, R, [rc], 'VISUAL_REVIEW', extra)))
        out.append(('REFUSED_HALT', lambda: _stage(w, stage_body(
            run, [cmd(CONS[role], 'RESPONSE_INVALID', result='REFUSED')], R['next'], refused='RESPONSE_INVALID',
            **extra))))
        return out
    d = R['delivery'] or {}
    if not q and R['next'] == 'DELIVER' and d.get('prepared_seq') is None:
        out.append(('DELIVERY', lambda: w.entry('DELIVERY', {
            'run': run, 'standard_sha256': R['saved_qa']['deliverable_sha256'], 'copy': {'sha256': hx('c'), 'bytes': 9},
            'log': {'sha256': hx('l'), 'bytes': 9}, 'profile_folder': 'Dots Folder/profiles/u1'},
            parts=[('DELIV', 1), ('DLOG', 1)])))
    if not q and d.get('prepared_seq') and not d['sent'] and d['resend_ok']:
        out.append(('SENT_FREEZE', lambda: _frz(w, R, [], 'DONE', extra, delivered=True)))
    if not q and d.get('prepared_seq') and d['sent']:
        out.append(('ARRIVED_FREEZE', lambda: _frz(w, R, [], 'DONE', extra, delivered=True)))
    return out


CONS = {'S': 'scope-finish', 'G': 'finish', 'V': 'visual-record'}


def _frz(w, R, first, final_next, extra, consumed=(), delivered=False, diverged=False, rebase=None):
    cmds = _freeze_cmds(*first)
    fl = oracle_flags(R, cmds, diverged)
    elig = final_next.startswith('STOP_') and R['restart_of'] is None and not R['interrupts'] \
        and R['tag'] in ('A', 'B')
    b = frozen_body(R['key'], cmds, final_next, flags=fl, notify=_notify_for(w, final_next, fl, delivered),
                    consumed=list(consumed), delivery_sent=delivered, rebase=rebase, restart_eligible=elig, **extra)
    return _stage(w, b)


def _rebase_rerun_moves(w, R):
    bind = R['rebase_bind']
    head = [e for e in w.entries if e['seq'] == bind['head_seq']][0]
    hb = copy.deepcopy(head['body'])
    rb = {'head_seq': bind['head_seq'], 'base_seq': bind['base_seq'], 'bound': bind['bound'], 'diverged': False}
    rx = R.get('rerun_expected')
    extra = {'rerun': {'after_seq': rx['seq'], 'unbound': True}} if rx else {}
    out = []

    def same():
        b = copy.deepcopy(hb)
        b['rebase'] = rb
        if b['start'] is not None:
            b['start'] = dict(b['start'], start_no=b['start']['start_no'] + 1, reason='REBASE', utc=None, boot_id=None)
        if b['png'] is not None:
            b['png'] = dict(b['png'], parts_seq=w.state['seq'] + 1)
        b['snapshot'] = dict(b['snapshot'])
        parts = [(p['kind'], p['k']) for p in head['parts']]
        return _stage(w, b, parts=parts)
    out.append(('REBASE_SAME', same))
    out.append(('REBASE_DIVERGED', lambda: _frz(w, R, [cmd(hb['commands'][0]['sub'], 'STOP_X')], 'STOP_X', extra,
                                                diverged=True, rebase=dict(rb, diverged=True))))
    return out


def _restore_moves(w):
    """RESTORE entries a session could commit from this state (a new boot each), plus a rebase when the head allows."""
    s, out = w.state, []
    op = open_role(s)
    cur = s['current']
    R = s['runs'].get(cur) if cur else None
    if R is not None and R['status'] == 'INPUTS':
        if R['reprepares'] == 0:
            out.append(('RESTORE_REPREPARE', lambda: _restore(w, reprepare={'run': cur, 'inputs_seq':
                                                                            R['inputs']['seq']})))
        out.append(('RESTORE_ABANDON', lambda: _restore(w, abandon={'run': cur})))
        return out
    if op is None:
        kw = {}
        if R is not None and s['mode'] == 'everyday' and (R['delivery'] or {}).get('prepared_seq') \
                and not R['delivery']['sent']:
            kw['delivery_question'] = {'run': cur, 'prepared_seq': R['delivery']['prepared_seq']}
        elif R is not None and R['status'] == 'ACTIVE' and not R['rebase_bind'] and _chain_pending(R):
            kw['rerun_expected'] = {'run': cur, 'stage': 'x'}
        out.append(('RESTORE', lambda: _restore(w, **kw)))
        if not s['runs'] or s['phase'] != 'OPEN':
            return out
        if not kw and not run_in_flight(s):
            out.append(('RESTORE_KIT', lambda: _restore(w, kit_change_=True)))
    else:
        out.append(('RESTORE_RESOLVE', lambda: _restore(w, resolve=op)))
    u = s['undo']
    if s['phase'] == 'OPEN' and u['kind'] in ('STAGE', 'FROZEN') and u['parts'] and u['before'] is not None:
        st = u['start']
        ok = True
        if st is not None:
            ro = s['runs'][u['run']]['roles'].get(st['role'] + str(st['attempt']))
            ok = ro is not None and ro['supersedes'] == 0
            ok = ok and (op is None or (op[0], op[1]) == (u['run'], st['role'] + str(st['attempt'])))
        elif op is not None:
            ok = False
        if ok:
            out.append(('RESTORE_REBASE', lambda: _restore(w, rebase=True)))
    return out


def _chain_pending(R):
    return bool(pending(R)) or any(
        r['status'] == 'ARCHIVED' and not r['consumed'] for r in R['roles'].values()) \
        or bool((R['delivery'] or {}).get('sent'))


def _restore(w, resolve=None, rebase=False, kit_change_=False, ans=None, **kw):
    s = w.state
    w.reset()
    rng = w.rng
    members, confirms, items, st = [], None, [], None
    if rebase:
        u = s['undo']
        miss = u['parts'][0][0]
        t1 = utc(w.t - 300)
        t2 = utc(w.t - 300 + F.w_abs(s['genesis']['gates']))
        head = w.entries[-1]
        kw['rebase'] = {'head_seq': s['seq'], 'base_seq': u['before']['snapshot']['seq'], 'missing_parts': [miss],
                        'absence': [{'name': miss, 'utc': [t1, t2]}],
                        'list_shows_none': True if u['start'] is not None else None,
                        'bound': {'commands': [[c['sub'], c['next'], sorted(c['codes'])] for c in
                                               head['body']['commands']], 'values': {}}}
        confirms = [{'name': entry_name(w.series, s['seq']), 'copies': [
            {'id': 'ID' + md5ish('e%d' % s['seq']), 'md5': md5ish('e%d' % s['seq']), 'size': 1000}]}] + [
            {'name': p[0], 'copies': [] if p[0] == miss else [{'id': 'ID' + p[1], 'md5': p[1], 'size': p[2]}]}
            for p in u['parts']]
        resolve = None
    if resolve:
        run, rk, ro = resolve
        ans = ans or _answers(s, ro, rng)
        item, st = oracle_item(s, run, rk, ans)
        items = [item]
        if item['transcript'] == 'exported':
            members = [['transcript', 'dir', 0o755, None, None],
                       ['transcript/%s%d_%d.json' % (ro['role'], ro['attempt'], item['start_no']), 'file', 0o644, 5,
                        hx('t')]]
    kit, rel = None, None
    if kit_change_:
        nk = hx('kit2', s['seq'])
        kw['kit_change'] = kit_change(s, nk, config_only=False)
        kw['kit_change']['to_accepts_release_sha256'] = [REL2]
        w.kit, kit, rel = nk, nk, REL2
    b = restore_body(w, items, st, **kw)
    return w.entry('RESTORE', b, members=members, confirms=confirms, kit=kit, release=rel)


def answer_variants(s, ro):
    """Every §6.5 restore answer combination for an open role (list_shows_none only where it is asked)."""
    g = s['genesis']['gates']
    asked = ro['status'] == 'STARTED' and ro['opened'] is None and ro['supersedes'] == 0 \
        and g['p1_conversation_list'] == 'yes'
    out = []
    for ended in (True, False):
        for ff in (False, True):
            for tr in ('exported', 'not_available'):
                for oc in (('CONTINUED',) if ro['status'] == 'CONTINUED' else
                           ('NOTHING_WRITTEN', 'WRITTEN', 'UNSURE', 'NO_CONVERSATION')):
                    for lsn in ((True, False) if asked else (None,)):
                        out.append({'ended': ended, 'files_found': ff, 'transcript': tr, 'outcome': oc,
                                    'list_shows_none': lsn})
    return out


def restore_variant_moves(w):
    """One RESTORE move per answer variant for the open role (§4.8 step 2: one per resolution outcome)."""
    op = open_role(w.state) if w.state and w.state['phase'] != 'FINAL' else None
    if op is None:
        return []
    return [('RESTORE_VARIANT_%d' % i, lambda a=a: _restore(w, resolve=op, ans=a))
            for i, a in enumerate(answer_variants(w.state, op[2]))]


def _answers(s, ro, rng):
    g = s['genesis']['gates']
    pick = (lambda xs: rng.choice(xs)) if rng else (lambda xs: xs[0])
    ans = {'ended': pick([True, True, True, False]), 'files_found': pick([False, False, False, True]),
           'transcript': pick(['exported', 'not_available'] if g['p1_transcript_export'] == 'yes'
                              else ['not_available']),
           'outcome': pick(['NOTHING_WRITTEN', 'NOTHING_WRITTEN', 'WRITTEN', 'UNSURE', 'NO_CONVERSATION'])}
    if ro['status'] == 'STARTED' and ro['opened'] is None and ro['supersedes'] == 0 \
            and g['p1_conversation_list'] == 'yes':
        ans['list_shows_none'] = pick([True, True, False])
    else:
        ans['list_shows_none'] = None
    return ans


# ------------------------------------------------------------------ invariants (§4.7)
def check_invariants(s):
    """Raises AssertionError naming the invariant."""
    if s is None:
        return
    opens = [(k, rk) for k in s['order'] for rk, ro in s['runs'][k]['roles'].items()
             if ro['status'] in ('STARTED', 'OPENED', 'CONTINUED')]
    assert len(opens) <= 1, 'I1 %s' % opens
    assert all(k == s['current'] for k, _ in opens), 'I1 open role outside the current run'
    inflight = [k for k, R in s['runs'].items() if R['status'] in ('ACTIVE', 'INPUTS')]
    assert inflight == ([s['current']] if s['current'] else []), 'I10 %s' % inflight
    for k, R in s['runs'].items():
        if R['tag'] in ('B', 'B-restart1'):
            a = [x for x in s['order'] if s['runs'][x]['case'] == R['case'] and s['runs'][x]['reader'] == 'A']
            assert a and all(s['runs'][x]['status'] == 'FROZEN' for x in a), 'I3 %s' % k
        if R['tag'] in ('A', 'B'):
            restarts = [x for x in s['order'] if s['runs'][x]['restart_of'] == k]
            assert len(restarts) + len(R['interrupts']) <= 1, 'I4 %s' % k
            for x in restarts:
                assert not s['runs'][x]['interrupts'], 'I4 restart run with an in-place interrupt'
        assert R['replacements'] <= 1 and sum(1 for r in R['roles'].values() if r['role'] == 'V') <= 2, 'I12 %s' % k
        for rk, ro in R['roles'].items():
            assert ro['supersedes'] <= 1 and len(ro['starts']) <= 2, 'I8 %s %s' % (k, rk)
            if len(ro['starts']) == 2:
                assert ro['starts'][1]['reason'] in ('NO_CONVERSATION', 'REBASE') and ro['supersedes'] == 1, 'I8'
                assert ro['starts'][0]['superseded_by'] == ro['starts'][1]['start_no'], 'I8 link'
            assert ro['review_incomplete'] <= 2, 'I9'
            if ro['archives']:
                assert ro['archives'][0]['boot_id'] == latest(ro)['boot_id'], 'I13 %s %s' % (k, rk)
            if ro['starts'][0]['reason'] in ('REPLACEMENT', 'EVERYDAY_RETRY'):
                assert ro['attempt'] >= 2, 'a new attempt'
    if s['phase'] == 'FINAL':
        assert s['current'] is None and not opens and s['notify'] is None, 'I14'


def state_bytes(s):
    return cjson(s)
