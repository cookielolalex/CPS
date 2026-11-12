"""next_action (§7.1), the chain table chain_next (§7.3), the run order (§7.11). Pure: no I/O, no clock.
next_action(view) is total (its last row is Stop UNCLASSIFIED); view = {'state', 'marks', 'local', 'now',
'boot_id', 'base', 'cfg'}. A row that writes a mark returns a block whose `mark` the glue writes first."""
from .fold import (CONSUMER, QUAL_ROOT as ROOT, ROLE_OF_NEXT, chain, final_ready, is_q, latest, newest,
                   nonattempt, open_roles, pending_resolution)
from .names import REVIEW_CONTINUABLE, run8
from .step import Ask, Commit, PrintBlock, RunChain, Stop

G_KEYS = ('ended', 'conversation', 'started_utc', 'ended_utc', 'platform', 'model', 'effort', 'single_user_message',
          'memory', 'custom_instructions', 'web', 'connectors', 'file_uploads', 'other_agents', 'tools', 'transcript')
G_PAT = {'ended': 'YES', 'conversation': 'CONV', 'started_utc': 'UTC', 'ended_utc': 'UTC', 'platform': 'PLATFORM',
         'model': 'MODEL', 'effort': 'EFFORT', 'tools': 'TOOLS', 'transcript': 'TRANSCRIPT'}
MAX_CHAIN = 6


def mark_key(kind, run, rkey, st):
    """§2.3 mark key OPEN/EXPORT:<run>:<role key>:<start_no>:<start seq>."""
    return '%s:%s:%s:%d:%d' % (kind, run, rkey, st['start_no'], st['seq'])


def end_keys(ro):
    """§6.5 keys asked when an S, G or V (revision 1) conversation ended; every one attests its tools (D9)."""
    if ro['role'] == 'G':
        return {k: G_PAT.get(k, 'YESNO') for k in G_KEYS}
    if ro['role'] == 'S':
        return {'ended': 'YES', 'conversation': 'CONV', 'prompt_pasted': 'YES', 'tools': 'TOOLS'}
    return {'ended': 'YES', 'conversation': 'CONV', 'tools': 'TOOLS'}


def transcript_path(base, run, ro, st, ext):
    """§7.1 row 8: BASE/transcripts/<run8>_G<a>_<k>.<ext> (k = the start_no)."""
    return '%s/transcripts/%s_%s%d_%d.%s' % (base, run8(run), ro['role'], ro['attempt'], st['start_no'], ext)


def pending_chain(state):
    """The RunChain rows 12-15, 19 and 20 of §7.1 for the current run, as (first sub, info), or None."""
    cur = state['current']
    R = state['runs'].get(cur) if cur else None
    if R is None or open_roles(state):
        return None
    out = None
    pr = pending_resolution(R) if R['status'] == 'ACTIVE' else None
    if pr and pr['action'] == 'INTERRUPT':
        out = ('interrupt', {'resolution': pr, 'role': _role_of_res(R, pr)})
    elif pr and pr['action'] in ('FREEZE_LOST', 'FREEZE_EXHAUSTED', 'FREEZE_VISUAL_FAILED'):
        out = ('freeze', {'resolution': pr, 'role': _role_of_res(R, pr)})
    elif R['rebase_bind']:
        out = (R['rebase_bind']['bound']['commands'][0][0], {'bind': R['rebase_bind']})
    else:
        arch = sorted(k for k, r in R['roles'].items() if r['status'] == 'ARCHIVED' and not r['consumed'])
        d = R['delivery'] or {}
        if arch and R['status'] == 'ACTIVE':
            out = (CONSUMER[R['roles'][arch[0]]['role']], {'consume': arch[0]})
        elif d.get('prepared_seq') and d.get('sent'):
            out = ('freeze', {'delivery_sent': True})
        elif R['status'] == 'INPUTS':
            out = ('prepare', {'inputs_seq': R['inputs']['seq'], 'tag': R['tag'], 'case': R['case']})
    if out and R.get('rerun_expected'):
        out[1]['rerun'] = {'after_seq': R['rerun_expected']['seq'], 'unbound': True}
    return out


def _role_of_res(R, pr):
    return [k for k, r in sorted(R['roles'].items()) if r['resolution'] is pr][0]


def next_run(state):
    """§7.11: the next Q/D run as a RunChain, the FINAL Commit draft, or a Stop."""
    jobs = sorted(state['genesis']['jobs'] or [], key=lambda j: j[1])
    for rd in ('A', 'B'):
        for job in jobs:
            if nonattempt(job) and not chain(state, job[0], rd):
                return _run_chain('NA-' + rd, job[0], rd, 'nonattempt', None, [])
    for rd in ('A', 'B'):
        for job in jobs:
            if nonattempt(job):
                continue
            ch, case = chain(state, job[0], rd), job[0]
            if not ch:
                place = []
                if rd == 'B':
                    ac = chain(state, case, 'A')
                    L = state['runs'][ac[-1]]
                    if L['restart_of'] is None and L['frozen']['restart_eligible'] and 'RESET_DIVERGED' in L['flags']:
                        return Stop('QUALIFICATION_DIVERGED_RESTART_CONFLICT', 'C')
                    place = [ac[-1]]
                return _run_chain(rd, case, rd, 'prepare', None, place)
            L = state['runs'][ch[-1]]
            if len(ch) == 1 and L['status'] == 'FROZEN' and L['frozen']['restart_eligible'] \
                    and 'RESET_DIVERGED' not in L['flags']:
                return _run_chain(rd + '-restart1', case, rd, 'prepare', ch[0], [ch[0]])
    if final_ready(state):
        return Commit({'kind': 'FINAL', 'body': None})
    return Stop('UNCLASSIFIED', 'C')


def _run_chain(tag, case, reader, first, restart_of, place):
    return RunChain(tag + '/' + case, first, {'new_run': {'tag': tag, 'case': case, 'reader': reader,
                                                          'root': ROOT[tag], 'restart_of': restart_of},
                                              'place_frozen': place})


def next_action(view):
    """§7.1, rows 1-23 in order (see the module docstring for `view`)."""
    s, marks, base, cfg = view['state'], view['marks'], view['base'], view['cfg']
    if s is None:
        return Commit({'kind': 'GENESIS', 'body': None})                                       # row 1
    if s['phase'] == 'FINAL':
        return Stop('FINAL', 'B')                                                               # row 2
    if s['phase'] == 'HALTED':                                                                  # row 3
        h, cl = s['halt'], cfg.get('clear')
        if cl == {'series': s['series'], 'seq': h['seq'], 'code': h['code']}:
            return Commit({'kind': 'CLEAR', 'body': {'halt_seq': h['seq'], 'code': h['code']}})
        return Stop('HALTED_' + h['code'], 'C')
    if not view['local'].get('gates_ok'):
        return Stop('RELEASE_GATE_OPEN', 'C')
    if s['notify'] is not None:                                                                 # row 4
        return _notify(s, base)
    gates = s['genesis']['gates']
    cur = s['current']
    R = s['runs'].get(cur) if cur else None
    op = open_roles(s)
    if op:
        if R is None or any(k != cur for k, _ in op):
            return Stop('UNCLASSIFIED', 'C')
        return _open_role(s, R, op[0][1], marks, view, gates)                                   # rows 5-11
    pc = pending_chain(s)
    if pc:
        return RunChain(cur, pc[0], pc[1])                                                      # rows 12-15, 19, 20
    if R is not None and not is_q(s) and R['status'] == 'ACTIVE':
        d = R['delivery'] or {}
        if R['next'] == 'DELIVER' and d.get('prepared_seq') is None:                            # row 16
            return Ask({'copy': 'COPYPATH', 'log': 'COPYPATH'},
                       {'action': 'DELIVER_COPY', 'state_code': 'DELIVER', 'run': cur, 'case': R['case'],
                        'file': '%s/deliver/%s/STANDARD.xlsx' % (base, run8(cur))})
        if d.get('prepared_seq') and not d['sent'] and d['resend_ok']:                         # rows 17, 18
            key = 'DELIVER_USER:%s:%d:%d' % (cur, d['prepared_seq'], d.get('ack_seq') or 0)
            ctx = {'state_code': 'DELIVER', 'run': cur, 'prepared_seq': d['prepared_seq']}
            if sent_mark(cur, d['prepared_seq'], d) in marks:                                # §X.5 step 8
                return RunChain(cur, 'freeze', {'delivery_sent': True})
            if key not in marks:
                return Ask({'sent': 'YES'}, dict(ctx, action='DELIVER_USER', mark=key))
            return Ask({'sent': 'YES'}, dict(ctx, action='DELIVER_SENT'))
    if cur is None and is_q(s):
        return next_run(s)                                                                      # row 21
    if cur is None:
        return Ask({'case': 'CASE_ID'}, {'action': 'IDLE', 'state_code': 'IDLE'})               # row 22
    return Stop('UNCLASSIFIED', 'C')                                                            # row 23


def sent_mark(run, prepared_seq, delivery):
    """The mark `answer sent=yes` writes (§X.5 step 8); the next `go` runs row 17's freeze chain."""
    return 'DELIVER_SENT:%s:%d:%d' % (run, prepared_seq, (delivery or {}).get('ack_seq') or 0)


def _notify(s, base):
    n = s['notify']
    if n['what'] == 'NOTIFY_OWNER':
        return Ask({'notified': 'YES'}, {'action': 'NOTIFY_OWNER', 'state_code': 'NOTIFY', 'for_seq': n['seq'],
                                         'file': '%s/attest/notice_%06d.txt' % (base, n['seq'])})
    key = {'arrived': 'YESNO'} if n['about'] == 'DELIVERY' else {'asked': 'YES'}
    return Ask(key, {'action': 'ASK_USER', 'state_code': 'NOTIFY', 'for_seq': n['seq'], 'about': n['about'],
                     'file': '%s/attest/ask_%06d.txt' % (base, n['seq'])})


def _open_role(s, R, rkey, marks, view, gates):
    ro, run, base, now = R['roles'][rkey], R['key'], view['base'], view['now']
    st = latest(ro)
    ids = {'run': run, 'role': ro['role'], 'attempt': ro['attempt'], 'start_no': st['start_no']}
    om, em = mark_key('OPEN', run, rkey, st), mark_key('EXPORT', run, rkey, st)
    if ro['status'] == 'CONTINUED':                                                             # rows 10, 11
        n = ro['continuations']
        ck = 'CONTINUE:%s:%s:%d' % (run, rkey, n)
        if ck not in marks:
            msg = '%s/attest/continue_%s_V%d_%d.txt' % (base, run8(run), ro['attempt'], n)
            return PrintBlock('AI', do=('CONTINUE_CONVERSATION', {'role': 'V', 'conversation':
                                        ro['archives'][0]['conversation'], 'message': msg}), mark=ck)
        return Ask({'ended': 'YES'}, dict(ids, action='AI', state_code='ATTEST', revision=len(ro['archives']) + 1))
    if om not in marks:                                                                         # row 5
        if st['boot_id'] != view['boot_id']:
            return Stop('UNCLASSIFIED', 'C')
        return PrintBlock('AI', do=('OPEN_CONVERSATION', {'role': ro['role'], 'prompt': st['prompt'],
                                                           'folder': st['folder']}), mark=om)
    tpath = transcript_path(base, run, ro, st, view['cfg'].get('transcript_ext', 'json'))
    if ro['role'] == 'G' and gates.get('p1_transcript_export') == 'yes' and em not in marks:   # row 8
        return PrintBlock('AI', do=('EXPORT_TRANSCRIPT', {'role': 'G', 'to': tpath}), mark=em)
    keys = end_keys(ro)                                                                         # row 9
    win = {k: [st['utc'], now] for k in ('started_utc', 'ended_utc') if k in keys}
    return Ask(keys, dict(ids, action='AI', state_code='ATTEST', revision=1, window=win,
                          transcript_path=tpath if ro['role'] == 'G' else None))


def chain_next(sub, result, counters, mode, bind):
    """§7.3, first match wins, for the result of `sub`: {'row', 'action': run|retry|end|stop, 'sub', 'entry',
    'code', 'flags', 'diverged', 'review_incomplete', 'start'}."""
    r = _chain_row(sub, result, counters, mode, bind)
    if r['action'] == 'run' and counters['n'] >= MAX_CHAIN:
        return dict(r, row='LIMIT', action='stop', sub=None, entry=None, code='INTERNAL_CHAIN_TOO_LONG')
    return r


def _out(row, action, sub=None, entry=None, code=None, flags=(), start=None, ri=False, diverged=False):
    return {'row': row, 'action': action, 'sub': sub, 'entry': entry, 'code': code, 'flags': list(flags),
            'diverged': diverged, 'review_incomplete': ri, 'start': start}


def _chain_row(sub, res, cn, mode, bind):
    kind, tok, q = res['result'], res['next'], mode in ('qualification', 'drill')
    div = cn.get('diverged', False)
    if bind is not None and not div:                                                            # X1
        i, head = cn['n'] - 1, bind['commands']
        if i >= len(head) or [sub, tok, sorted(res['codes'])] != list(head[i]) \
                or (i == len(head) - 1 and res.get('bound') != bind.get('values')):
            if sub not in ('freeze', 'verify-frozen'):
                return _out('X1', 'run', 'freeze', flags=['RESET_DIVERGED'], diverged=True)
            div = True
    refused = kind in ('REFUSED', 'UNPARSEABLE')
    if kind == 'REFUSED' and tok == 'JOB_BUSY':
        return _out('X2', 'retry', sub, diverged=div)
    if sub == 'visual-record' and kind == 'REFUSED' and tok in REVIEW_CONTINUABLE:
        if cn['v_review_incomplete'] < 2:
            return _out('X3', 'end', entry='STAGE', code=tok, ri=True, diverged=div)
        return _out('X4', 'run', 'freeze', flags=['REVIEW_INCOMPLETE_LIMIT'], diverged=div)
    if sub == 'interrupt' and kind == 'REFUSED' and tok == 'INTERRUPT_RESTART_USED':
        return _out('X5', 'run', 'freeze', flags=['RESTART_EXHAUSTED_BY_RESET'], diverged=div)
    if refused:
        code = tok if kind == 'REFUSED' else 'RUNNER_OUTPUT_UNPARSEABLE'
        if res['record_changed'] or res['ledger_changed']:
            return _out('X6', 'end', entry='STAGE', code=code, diverged=div)
        if not res['tree_changed']:
            return _out('X7', 'end', entry='HALT', code='RUNNER_REFUSED' if kind == 'REFUSED' else code,
                        diverged=div)
        return _out('X20', 'end', entry='HALT', code='UNCLASSIFIED', diverged=div)
    if sub == 'verify-frozen':
        if tok == 'STOP_FROZEN_FOLDER_CHANGED':
            return _out('X8', 'end', entry='HALT', code='FROZEN_FOLDER_CHANGED', diverged=div)
        if tok == 'DONE':
            return _out('X9', 'end', entry='FROZEN', diverged=div)
        return _out('X20', 'end', entry='HALT', code='UNCLASSIFIED', diverged=div)
    if sub == 'freeze' and tok == 'STOP_FREEZE_INCOMPLETE':
        if cn['freeze_retries'] < 2:
            return _out('X10', 'run', 'freeze', diverged=div)
        return _out('X11', 'end', entry='HALT', code='FREEZE_INCOMPLETE', diverged=div)
    if sub in ('freeze', 'nonattempt') and tok == 'DONE':
        return _out('X12', 'run', 'verify-frozen', diverged=div)
    if sub == 'interrupt' and tok == 'STOP_TECHNICAL_INTERRUPTION':
        return _out('X13', 'run', 'freeze', diverged=div)
    if sub == 'interrupt' and tok == 'GENERATE':
        return _out('X14', 'end', entry='STAGE', start='G', diverged=div)
    if sub in ('prepare', 'scope-finish', 'finish') and tok in ROLE_OF_NEXT:
        return _out('X15', 'end', entry='STAGE', start=ROLE_OF_NEXT[tok], diverged=div)
    if sub == 'visual-record' and tok == 'FREEZE' and q:
        return _out('X16', 'run', 'freeze', diverged=div)
    if sub == 'visual-record' and tok == 'DELIVER_CHECK' and not q:
        return _out('X17', 'run', 'deliver-check', diverged=div)
    if sub == 'deliver-check' and tok == 'DELIVER' and not q:
        return _out('X18', 'end', entry='STAGE', diverged=div)
    if sub != 'freeze' and (tok.startswith('STOP_') or tok == 'OWNER_DECISION'):
        return _out('X19', 'run', 'freeze', diverged=div)
    return _out('X20', 'end', entry='HALT', code='UNCLASSIFIED', diverged=div)


def frozen_notify(mode, final_next, flags, delivery_sent):
    """§7.9, §11.4: the FROZEN body's `notify` (NOTIFY_OWNER, ASK_USER or None)."""
    stop = final_next.startswith('STOP_') or final_next == 'OWNER_DECISION'
    if mode != 'everyday':
        return 'NOTIFY_OWNER' if stop else None
    if delivery_sent:
        return None
    return 'NOTIFY_OWNER' if stop else 'ASK_USER'


def consumer_role(R):
    """The role key a consumer chain of R consumes, or None."""
    arch = sorted(k for k, r in R['roles'].items() if r['status'] == 'ARCHIVED' and not r['consumed'])
    return arch[0] if arch else None


def v_review_incomplete(R):
    V = newest(R, 'V')
    return V['review_incomplete'] if V else 0
