"""The session and restore machine (§8): session_next, head_search (§8.4), classify (§8.5), the resolution of an open
role (§8.6), kit acceptance (§8.1 step 11, §8.2 KIT_CHANGE). Pure: every observation comes in RESTORE_WORK.

session_next(view) -> (phase, Step or None). The phase is the first unfinished §8.1 step (RESTORE_WORK phases, §2.3);
the glue writes it into RESTORE_WORK (forward only) and carries out the Step. Step None means "an I/O phase: the glue
does it itself and records it in work['done']": LAYOUT, SETUP, KIT, CONFIG, FINGERPRINT, PASS, CLOCK, and KIT_ACCEPT
when the head's kit must be fetched (§8.2: it fills work['head_kit']).
view = {'work': RESTORE_WORK, 'series', 'gates' (config gates), 'clear' (config clear), 'now' (UTC_S), 'base',
        'transcript_ext' (config)}.
RESTORE_WORK keys read here (the glue records each observation before calling again):
  done [phase], operator {model, platform}|None, hint {'seq': int|None, 'kit': hex12|None},
  lookups [{'name', 'result': 'present'|'absent', 'copies': [[id, md5, size]], 'utc'}] (every FIND, in order),
  listing None|[[name, id, md5, size]] (newest-first LIST answer), head None|{'entry': the downloaded ENTRY, verified by
  the glue (§8.4 step 3)}, head_error None|code, identity {'home', 'uid'}, kit {'sha256', 'members', 'config',
  'release_sha256'}, head_kit None|{'sha256', 'members', 'config'}, list_shows_none None|bool (C5),
  resolve {'end': bool, 'placed': bool, 'files_found': bool|None, 'export': bool, 'answers': dict|None},
  placed bool, reuploaded bool, committed None|{'seq', 'md5', 'utc'} (the RESTORE commit, for RECHECK).
Blocks that END or EXPORT set work['resolve']['end'|'export'] before printing (the RESTORE_WORK analogue of a mark)."""
from . import fold as F
from .names import FOLDERS, cjson, entry_name, series_folder, sha, utc_epoch
from .plan import pending_chain
from .step import Ask, Commit, Halt, Place, PrintBlock, Reupload, Stop

PHASES = ('LAYOUT', 'SETUP', 'OPERATOR', 'KIT', 'CONFIG', 'FINGERPRINT', 'HEAD', 'IDENTITY', 'PASS', 'CLOCK',
          'KIT_ACCEPT', 'CLASSIFY', 'RESOLVE_END', 'RESOLVE_PLACE', 'RESOLVE_EXPORT', 'RESOLVE_ATTEST', 'PLACE',
          'COMMIT', 'RECHECK', 'DONE')
MAX_FLIPS = 3


class _Out(Exception):
    def __init__(self, r):
        super().__init__(r)
        self.r = r


def _facts(lookups, names):
    f = {}
    for lk in lookups:
        if lk['name'] in names:
            x = f.setdefault(lk['name'], {'present': [], 'absent': [], 'seq': []})
            x['present' if lk['result'] == 'present' else 'absent'].append(lk)
            x['seq'].append((utc_epoch(lk['utc']), lk['result']))
    return f


def _status(f, name, twice, w, now):
    """'P' or 'A' for one name, or raise _Out with the lookup/wait needed (§8.4: a second absence counts only w apart;
    a copy at any observation is present; two md5s is FORK)."""
    x = f.get(name)
    if x and x['present']:
        if len({c[1] for lk in x['present'] for c in lk['copies']}) > 1:
            raise _Out({'verdict': 'stop', 'code': 'FORK'})
        return 'P'
    ab = sorted(utc_epoch(lk['utc']) for lk in (x['absent'] if x else []))
    if not ab:
        raise _Out({'need': 'find', 'name': name})
    if not twice or ab[-1] - ab[0] >= w:
        return 'A'
    if now - ab[0] < w:
        raise _Out({'need': 'wait', 'seconds': w - (now - ab[0])})
    raise _Out({'need': 'find', 'name': name})


def head_search(series, hint, lookups, gates, now, listing=None):
    """§8.4 steps 1-2 as a pure function of the observations so far. Returns {'need': 'find', 'name'} |
    {'need': 'wait', 'seconds'} | {'need': 'list'} | {'verdict': 'head', 'seq', 'copies', 'via': 'hint'|'list'|'gallop'}
    | {'verdict': 'fresh'} | {'verdict': 'stop', 'code': FORK|HINT_AHEAD|HEAD_UNSTABLE}."""
    w, t = F.w_abs(gates), utc_epoch(now)
    lk = list(lookups)
    for row in listing or []:
        lk.append({'name': row[0], 'result': 'present', 'copies': [row[1:4]], 'utc': now})
    names = {x['name'] for x in lk}
    f = _facts(lk, names)
    flips = sum(1 for x in f.values() if any(r == 'absent' for _, r in sorted(x['seq'])[:1])
                and any(r == 'present' for _, r in x['seq']))
    if flips > MAX_FLIPS:
        return {'verdict': 'stop', 'code': 'HEAD_UNSTABLE'}
    nm = lambda k: entry_name(series, k)                                            # noqa: E731
    st = lambda k, tw: 'A' if k > 999999 else _status(f, nm(k), tw, w, t)           # noqa: E731
    try:
        if gates.get('p2_newest_first') == 'yes':
            via = 'list'
            if listing is None:
                return {'need': 'list'}
            seqs = [int(r[0][-10:-4]) for r in listing if r[0].startswith('CPSJ_%s_' % series)
                    and r[0] == nm(int(r[0][-10:-4]))]
            lo = max(seqs) if seqs else (None if st(1, True) == 'A' else 1)
        elif hint:
            via = 'hint'
            if st(hint, True) == 'A':
                return {'verdict': 'stop', 'code': 'HINT_AHEAD'}
            lo = hint
        else:
            via = 'gallop'
            lo = None if st(1, True) == 'A' else 1
        if lo is None:
            return {'verdict': 'fresh'}
        for _ in range(MAX_FLIPS + 1):
            base, i = lo, 0
            while st(base + 2 ** i, False) == 'P':
                lo, i = base + 2 ** i, i + 1
            hi = base + 2 ** i
            while hi - lo > 1:
                mid = (lo + hi) // 2
                lo, hi = (mid, hi) if st(mid, False) == 'P' else (lo, mid)
            if st(lo + 1, True) == 'A' and st(lo + 2, False) == 'A':
                copies = {c[0]: c for x in f[nm(lo)]['present'] for c in x['copies']}
                return {'verdict': 'head', 'seq': lo, 'copies': [copies[k] for k in sorted(copies)], 'via': via}
            lo = lo + 2
        return {'verdict': 'stop', 'code': 'HEAD_UNSTABLE'}
    except _Out as o:
        return o.r


def absent_twice(names, lookups, w, now):
    """Batch form of the double-absence check (§7.12 g, §8.4 step 5). Returns ('find', [names]) | ('wait', s) |
    ('done', {name: 'present'|'missing'}, [{'name', 'utc': [first, second]}]) (missing = absent twice, w apart)."""
    f, t = _facts(lookups, set(names)), utc_epoch(now)
    finds, waits, out, obs = [], [], {}, []
    for n in names:
        try:
            out[n] = 'present' if _status(f, n, True, w, t) == 'P' else 'missing'
            if out[n] == 'missing':
                ab = sorted(f[n]['absent'], key=lambda x: utc_epoch(x['utc']))
                obs.append({'name': n, 'utc': [ab[0]['utc'], ab[-1]['utc']]})
        except _Out as o:
            if o.r.get('need') == 'find':
                finds.append(n)
            elif o.r.get('need') == 'wait':
                waits.append(o.r['seconds'])
            else:
                out[n] = 'fork'
    if finds:
        return ('find', finds)
    if waits:
        return ('wait', max(waits))
    return ('done', out, obs)


def kit_change(state, kit, head_kit):
    """§8.1 step 11 / §8.2 KIT_CHANGE for a kit that differs from state.kit_sha256: (code or None, kit_change dict).
    kit/head_kit: {'sha256', 'members': [[path, sha256]], 'config': dict, 'release_sha256'}."""
    a, b = head_kit['config'], kit['config']
    keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    co, rif = F.config_only(head_kit['members'], kit['members']), F.run_in_flight(state)
    kc = {'from_kit_sha256': head_kit['sha256'], 'to_kit_sha256': kit['sha256'],
          'from_members': head_kit['members'], 'to_members': kit['members'], 'config_only': co,
          'config_keys_changed': keys, 'run_in_flight': rif,
          'to_accepts_release_sha256': list(b.get('accepts_release_sha256') or [])}
    if head_kit['sha256'] != state['kit_sha256']:
        return 'KIT_NOT_VERIFIED', kc
    if b.get('gates') != state['genesis']['gates']:
        return 'GATES_CHANGED', kc
    if co:
        bad = set(keys) - F.CHANGEABLE_KEYS or not set(a.get('doc_samples') or []) <= set(b.get('doc_samples') or [])
        return ('CONFIG_CHANGE_NOT_ALLOWED' if bad else None), kc
    if rif:
        return 'KIT_CHANGE_WITH_RUN_IN_FLIGHT', kc
    if b.get('series') != a.get('series'):
        return 'CONFIG_CHANGE_NOT_ALLOWED', kc
    if kit['release_sha256'] != state['genesis']['release_sha256'] \
            and kit['release_sha256'] not in kc['to_accepts_release_sha256']:
        return 'RELEASE_NOT_ACCEPTED', kc
    return None, kc


def classify(head, state, missing_parts, clear, kit_config_only, gates):
    """§8.5 C2-C10 (C1 is the glue's step-3/4 failure). head: the head ENTRY; missing_parts: names of its parts absent
    twice. Returns (row id, detail dict)."""
    kind, body = head['kind'], head['body']
    if state['phase'] == 'HALTED':
        h = state['halt']
        ok = clear == {'series': state['series'], 'seq': h['seq'], 'code': h['code']} and kit_config_only
        return ('C2', {'clear': True}) if ok else ('C2', {'stop': 'HALTED_' + h['code']})
    if state['phase'] == 'FINAL':
        return 'C3', {'reupload': sorted(missing_parts)}
    if kind == 'DELIVERY' and missing_parts:
        return 'C4', {'reupload': sorted(missing_parts)}
    if kind in ('STAGE', 'FROZEN') and missing_parts:
        st = body['start']
        if st is not None:
            ro = state['runs'][body['run']]['roles'][st['role'] + str(st['attempt'])]
            if ro['supersedes'] == 1:
                return 'C5', {'stop': 'REBASE_LIMIT'}
            if gates.get('p1_conversation_list') == 'yes':
                return 'C5', {'rebase': True, 'ask_list': st['utc']}
        return 'C5', {'rebase': True}
    if kind == 'RESTORE' and body['rebase'] is not None:
        return 'C5b', {'check': list(body['rebase']['missing_parts'])}
    return _classify_rest(state)


def _classify_rest(state):
    op, cur = F.open_roles(state), state['current']
    R = state['runs'].get(cur) if cur else None
    if op:
        return 'C6', {'run': op[0][0], 'role': op[0][1]}
    if R is not None and state['mode'] == 'everyday' and R['status'] == 'ACTIVE' \
            and (R['delivery'] or {}).get('prepared_seq') and not R['delivery']['sent']:
        return 'C7', {'run': cur}
    if R is not None and R['status'] == 'ACTIVE':
        return 'C8', {'run': cur}
    if R is not None and state['mode'] == 'everyday' and R['status'] == 'INPUTS':
        return 'C8b', {'run': cur, 'reprepare': R['reprepares'] == 0}
    if cur is None:
        return 'C9', {}
    return 'C10', {}


def place_plan(state, run, rebase=False):
    """§8.5.1: what to place for `run` (None: the ledger only). With rebase, the base before the head (T49)."""
    u = state['undo']
    R = u['before'] if rebase else (state['runs'][run] if run else None)
    led = (u['ledger_before'] if rebase else state['ledger']) if F.is_q(state) else None
    plan = {'ledger': led, 'run': run, 'files': state['files']}
    if R is not None:
        plan.update(job_dir=R['job_dir'], snapshot_seq=R['snapshot']['seq'] if R['snapshot'] else None, png=R['png'])
        plan['ai'] = [{'role': k, 'seq': r['archives'][-1]['seq'], 'output': F.latest(r)['output']}
                      for k, r in sorted(R['roles'].items()) if r['status'] == 'ARCHIVED' and not r['consumed']]
        plan['transcripts'] = [{'role': k, 'seq': r['archives'][-1]['seq']} for k, r in sorted(R['roles'].items())
                               if r['role'] == 'G' and r['status'] == 'ARCHIVED' and not r['consumed']]
    return plan


def restore_keys(state, run, rkey, files_found, conversation_known):
    """§6.5 restore rows: the keys asked for an open role."""
    ro = state['runs'][run]['roles'][rkey]
    if ro['status'] == 'CONTINUED' or files_found:
        return {'ended': 'YESNO', 'transcript': 'TRANSCRIPT'}
    keys = {'ended': 'YESNO', 'outcome': 'OUTCOME', 'transcript': 'TRANSCRIPT'}
    if F.no_conversation_admissible(state, ro):
        keys['list_shows_none'] = 'YESNO'
    if not conversation_known:
        keys['conversation'] = 'CONV'
    return keys


def build_item(state, run, rkey, answers, files_found):
    """The RESTORE resolution item (§8.6 steps 5-6) and the START draft it needs (or None). answers are the validated
    §6.5 values ('yes'/'no' strings). The action comes from fold.resolution_action, so the fold accepts it."""
    ro = state['runs'][run]['roles'][rkey]
    item = {'run': run, 'role': ro['role'], 'attempt': ro['attempt'], 'start_no': F.latest(ro)['start_no'],
            'ended': answers['ended'] == 'yes', 'files_found': bool(files_found),
            'outcome': 'CONTINUED' if ro['status'] == 'CONTINUED' else answers.get('outcome', 'WRITTEN'),
            'forced': None, 'transcript': answers['transcript'],
            'list_shows_none': {'yes': True, 'no': False}.get(answers.get('list_shows_none')),
            'action': None, 'owner_check': False}
    item['forced'] = F.forced_for(state, state['runs'][run], ro, item)
    _, act, oc = F.resolution_action(state, item, item['transcript'] == 'exported')
    item['action'], item['owner_check'] = act, oc
    sf = F.start_for(act, ro)
    if sf is None:
        return item, None
    lt = F.latest(ro)
    start = {'role': sf[0], 'attempt': sf[1], 'start_no': sf[2], 'reason': sf[3], 'prompt': lt['prompt'],
             'prompt_sha256': lt['prompt_sha256'], 'folder': lt['folder'], 'output': lt['output'],
             'utc': None, 'boot_id': None}
    return item, start


def bound_of(head):
    """§7.10 rebase binding from the head STAGE/FROZEN: its commands and the bound values (the worker measures the
    same values with bound_values after the re-run's last command)."""
    b = head['body']
    return {'commands': [[c['sub'], c['next'], sorted(c['codes'])] for c in b['commands']],
            'values': bound_values(b['next'], b['codes'], b['saved_qa'], b['carrier_sha256'], b['png'])}


def bound_values(nxt, codes, saved_qa, carrier_sha256, png):
    return {'next': nxt, 'codes': sorted(codes), 'deliverable_sha256': (saved_qa or {}).get('deliverable_sha256'),
            'saved_qa_sha256': (saved_qa or {}).get('sha256'), 'carrier_sha256': carrier_sha256,
            'png_whole_sha256': (png or {}).get('whole_sha256')}


def _find_block(names, folder_of):
    return PrintBlock('HEAD', finds=tuple((folder_of(n), 'NAME', n) for n in names),
                      do=('ATTEST_FOUND', {'names': list(names)}))


def session_next(view):
    """§8.1 steps 1-13 (see the module docstring)."""
    w, g, series, now = view['work'], view['gates'], view['series'], view['now']
    done, sf = set(w.get('done') or ()), series_folder(series)
    folder = lambda n: sf                                                          # noqa: E731
    for ph in ('LAYOUT', 'SETUP'):
        if ph not in done:
            return ph, None
    if w.get('operator') is None:
        return 'OPERATOR', Ask({'operator_model': 'MODEL', 'platform': 'PLATFORM'},
                               {'action': 'OPERATOR', 'state_code': 'SETUP'})
    for ph in ('KIT', 'CONFIG', 'FINGERPRINT'):
        if ph not in done:
            return ph, None
    hs = head_search(series, (w.get('hint') or {}).get('seq'), w['lookups'], g, now, w.get('listing'))
    if 'need' in hs:
        return 'HEAD', _search_step(hs, series, sf)
    if hs['verdict'] == 'stop':
        return 'HEAD', Stop(hs['code'], 'C')
    if hs['verdict'] == 'fresh':
        return _fresh(w, g, series, now, done)
    N = hs['seq']
    if w.get('head_error'):
        return 'HEAD', Stop(w['head_error'], 'C')                                   # C1
    if not w.get('head'):
        cp = hs['copies'][0]
        return 'HEAD', PrintBlock('HEAD', downloads=((sf, cp[0], '%s/inbox/journal/%s' % (view['base'], entry_name(
            series, N))),), do=('RUN', {}))
    head = w['head']['entry']
    st = head['state']
    if N > 1:                                                                       # step 4: link
        f = _facts(w['lookups'], {entry_name(series, N - 1)})
        prev = f.get(entry_name(series, N - 1))
        if not prev:
            return 'HEAD', _find_block([entry_name(series, N - 1)], folder)
        want = {c['md5'] for c in head['confirms'][0]['copies']}
        if not prev['present'] or any(c[1] not in want for lk in prev['present'] for c in lk['copies']):
            return 'HEAD', Stop('LINK_MISMATCH', 'C')
    pf = {p['name']: p['folder'] for p in head['parts']}
    at = absent_twice(list(pf), w['lookups'], F.w_abs(g), now)                      # step 5: head parts
    if at[0] == 'find':
        return 'HEAD', PrintBlock('HEAD', finds=tuple((pf[n], 'NAME', n) for n in at[1]),
                                  do=('ATTEST_FOUND', {'names': at[1]}))
    if at[0] == 'wait':
        return 'HEAD', PrintBlock('HEAD', do=('WAIT', {'seconds': at[1]}))
    if 'fork' in at[1].values():
        return 'HEAD', Stop('FORK', 'C')
    missing = sorted(n for n, v in at[1].items() if v == 'missing')
    ident = w.get('identity') or {}
    if (ident.get('home'), ident.get('uid')) != (head['home'], head['uid']) and F.run_in_flight(st):
        return 'IDENTITY', Stop('HOME_CHANGED', 'C')
    for ph in ('PASS', 'CLOCK'):
        if ph not in done:
            return ph, None
    kc = None
    if w['kit']['sha256'] != st['kit_sha256']:                                      # step 11
        if not w.get('head_kit'):
            return 'KIT_ACCEPT', None
        code, kc = kit_change(st, w['kit'], w['head_kit'])
        if code:
            return 'KIT_ACCEPT', Stop(code, 'C')
    elif w['kit']['config'].get('gates') != st['genesis']['gates']:
        return 'KIT_ACCEPT', Stop('GATES_CHANGED', 'C')
    return _after_classify(view, w, head, st, missing, kc, hs)


def _search_step(hs, series, sf):
    if hs['need'] == 'list':
        return PrintBlock('HEAD', lists=((sf, 'CPSJ_%s_' % series, 5),), do=('ATTEST_FOUND', {'list': True}))
    if hs['need'] == 'wait':
        return PrintBlock('HEAD', do=('WAIT', {'seconds': hs['seconds']}))
    return PrintBlock('HEAD', finds=((sf, 'NAME', hs['name']),), do=('ATTEST_FOUND', {'names': [hs['name']]}))


def _fresh(w, g, series, now, done):
    """A fresh series (§8.1: skip 8, 10, 11): PASS, then for Q the other-series double absence (§7.12 g), GENESIS."""
    if 'PASS' not in done:
        return 'PASS', None
    obs = None
    if series[0] == 'Q':
        names = ['CPSJ_Q%d_000001.tgz' % k for k in range(1, 10) if 'Q%d' % k != series]
        at = absent_twice(names, w['lookups'], F.w_abs(g), now)
        if at[0] == 'find':
            return 'HEAD', PrintBlock('HEAD', finds=tuple((FOLDERS['Q'], 'NAME', n) for n in at[1]),
                                      do=('ATTEST_FOUND', {'names': at[1]}))
        if at[0] == 'wait':
            return 'HEAD', PrintBlock('HEAD', do=('WAIT', {'seconds': at[1]}))
        if any(v != 'missing' for v in at[1].values()):
            return 'HEAD', Stop('QUALIFICATION_SERIES_EXISTS', 'C')
        obs = at[2]
    return 'DONE', Commit({'kind': 'GENESIS', 'body': {'other_series_absent': obs, 'operator': w['operator']}})


def _after_classify(view, w, head, st, missing, kc, hs):
    g, base, N = view['gates'], view['base'], head['seq']
    row, d = classify(head, st, missing, view.get('clear'), kc is None or kc['config_only'], g)
    if 'stop' in d:
        return 'CLASSIFY', Stop(d['stop'], 'C')
    if row in ('C3', 'C4') and d['reupload'] and not w.get('reuploaded'):
        return 'CLASSIFY', Reupload(tuple(d['reupload']), N)
    if row == 'C3':
        return 'DONE', Stop('FINAL', 'B')
    if row == 'C4':
        row, d = _classify_rest(st)
    draft = {'prev_boot_id': st['boots'][-1][0] if st['boots'] else None, 'operator': w['operator'],
             'head': {'seq': N, 'md5': hs['copies'][0][1], 'copies': hs['copies']}, 'lookups': w['lookups'],
             'kit_sha256': w['kit']['sha256'], 'kit_change': kc, 'resolutions': [], 'start': None, 'rebase': None,
             'rerun_expected': None, 'reprepare': None, 'abandon': None, 'delivery_question': None}
    if row == 'C5':
        if 'ask_list' in d and w.get('list_shows_none') is None:
            return 'CLASSIFY', Ask({'list_shows_none': 'YESNO'}, {'action': 'LIST_SHOWS_NONE', 'state_code': 'RESTORE',
                                                                  'after': d['ask_list']})
        if 'ask_list' in d and w['list_shows_none'] is False:
            return 'CLASSIFY', Stop('REBASE_CONFLICT', 'C')
        absn = absent_twice(missing, w['lookups'], F.w_abs(g), view['now'])[2]
        draft['rebase'] = {'head_seq': N, 'base_seq': st['undo']['before']['snapshot']['seq'],
                           'missing_parts': missing, 'absence': absn,
                           'list_shows_none': w.get('list_shows_none') if 'ask_list' in d else None,
                           'bound': bound_of(head)}
        return _place_commit(w, st, st['undo']['run'], True, draft, hs, view)
    if row == 'C5b':
        seen = _facts(w['lookups'], set(d['check']))
        need = [n for n in d['check'] if n not in seen]
        if need:
            return 'CLASSIFY', _find_block(need, lambda n: series_folder(view['series']))
        if any(seen[n]['present'] for n in d['check']):
            return 'CLASSIFY', Stop('REBASE_PART_APPEARED', 'C')
        row, d = _classify_rest(st)
    if row == 'C10':
        return 'CLASSIFY', Halt('UNCLASSIFIED', True)
    if row == 'C2' or row == 'C6':
        op = F.open_roles(st)
        if op:
            return _resolve(view, w, st, op[0][0], op[0][1], draft, hs)
        return _place_commit(w, st, st['current'], False, draft, hs, view)
    if row == 'C7':
        draft['delivery_question'] = {'run': d['run'], 'prepared_seq': st['runs'][d['run']]['delivery']['prepared_seq']}
    elif row == 'C8':
        pc = pending_chain(st)
        bound = st['runs'][d['run']]['rebase_bind'] is not None
        draft['rerun_expected'] = {'run': d['run'], 'stage': pc[0]} if pc and not bound else None
    elif row == 'C8b':
        R = st['runs'][d['run']]
        draft['reprepare' if d['reprepare'] else 'abandon'] = (
            {'run': d['run'], 'inputs_seq': R['inputs']['seq']} if d['reprepare'] else {'run': d['run']})
        return _place_commit(w, st, None, False, draft, hs, view)
    return _place_commit(w, st, d.get('run'), False, draft, hs, view)


def _resolve(view, w, st, run, rkey, draft, hs):
    """§8.6 steps 1-7 for the one open role."""
    g, base, rs = view['gates'], view['base'], w.get('resolve') or {}
    R = st['runs'][run]
    ro = R['roles'][rkey]
    lt = F.latest(ro)
    conv = ro['opened']['conversation'] if ro['opened'] else (
        ro['archives'][0]['conversation'] if ro['status'] == 'CONTINUED' else None)
    if g.get('p1_end_after_reset') == 'yes' and not rs.get('end'):
        args = {'role': ro['role'], 'after': lt['utc']}
        if conv:
            args['conversation'] = conv
        return 'RESOLVE_END', PrintBlock('RESTORE', do=('END_CONVERSATION', args))
    if not rs.get('placed'):
        return 'RESOLVE_PLACE', Place(dict(place_plan(st, run), rewalk=True, open_role=rkey))
    if g.get('p1_transcript_export') == 'yes' and not rs.get('export'):
        to = '%s/transcripts/restore_%06d_%s%d_%d.%s' % (base, st['seq'] + 1, ro['role'], ro['attempt'],
                                                        lt['start_no'], view.get('transcript_ext', 'json'))
        args = {'role': ro['role'], 'to': to}
        if conv:
            args['conversation'] = conv
        args['after'] = lt['utc']
        return 'RESOLVE_EXPORT', PrintBlock('RESTORE', do=('EXPORT_TRANSCRIPT', args))
    if rs.get('answers') is None:
        return 'RESOLVE_ATTEST', Ask(restore_keys(st, run, rkey, rs.get('files_found'), conv is not None),
                                     {'action': 'RESTORE_ROLE', 'state_code': 'RESTORE', 'run': run, 'role': rkey})
    item, start = build_item(st, run, rkey, rs['answers'], rs.get('files_found'))
    draft['resolutions'], draft['start'] = [item], start
    return _commit(w, st, draft, hs, view)


def _place_commit(w, st, run, rebase, draft, hs, view):
    if not w.get('placed'):
        return 'PLACE', Place(place_plan(st, run, rebase))
    return _commit(w, st, draft, hs, view)


def _commit(w, st, draft, hs, view):
    """COMMIT (§8.7) then RECHECK (§8.4 step 6). The glue adds fingerprint_sha256, pass, placed, and the START's
    utc/boot_id (the entry's)."""
    if not w.get('committed'):
        return 'COMMIT', Commit({'kind': 'RESTORE', 'body': draft})
    if not (F.is_q(st) and hs['via'] == 'gallop'):
        return 'DONE', None
    c, N, series = w['committed'], hs['seq'], view['series']
    elapsed = utc_epoch(view['now']) - utc_epoch(c['utc'])
    wa = F.w_abs(view['gates'])
    later = [x for x in w['lookups'] if utc_epoch(x['utc']) >= utc_epoch(c['utc']) + wa]
    if elapsed < wa:
        return 'RECHECK', PrintBlock('RESTORE', do=('WAIT', {'seconds': wa - elapsed}))
    names = [entry_name(series, N + k) for k in (1, 2, 3)]
    f = _facts(later, set(names))
    need = [n for n in names if n not in f]
    if need:
        return 'RECHECK', _find_block(need, lambda n: series_folder(series))
    own = f[names[0]]['present']
    if not own or any(cp[1] != c['md5'] for lk in own for cp in lk['copies']) \
            or any(f[n]['present'] for n in names[1:]):
        return 'RECHECK', Stop('FORK', 'C')
    return 'DONE', None


def phase_index(phase):
    """Position of a RESTORE_WORK phase (forward-only check, §2.3)."""
    return PHASES.index(phase)


def work_sha(work):
    return sha(cjson(work))
