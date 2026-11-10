"""outcomes(state) (§9.1-9.3) and final_dispositions(outcomes, verdicts) (§9.5). Pure: they read only their
arguments. No other code derives a disposition (F4, F5)."""
from .fold import chain, latest
from .names import cjson, sha, utc_minus

ALLOWED = {'OWNER_CHECK': ('NOTHING_WRITTEN_CONFIRMED', 'WRITE_FOUND'),
           'SUPERSEDED_WINDOW': ('NO_CONVERSATION_IN_WINDOW', 'CONVERSATION_FOUND'), 'O52_SHEET': ('SHEET_CHECKED',)}


class OwnerChecksInvalid(Exception):
    """final_dispositions' refusal: code OWNER_CHECKS_INVALID with a detail string."""
    def __init__(self, detail):
        super().__init__(detail)
        self.code, self.detail = 'OWNER_CHECKS_INVALID', detail


def _disposition(L, job):
    """§9.2 D1-D10 on the last run L of a chain: (disposition, reason)."""
    if L is not None and L['tag'].startswith('NA-'):
        return 'NONATTEMPT', job[2] if isinstance(job[2], str) else 'NONATTEMPT_SOURCE_UNAVAILABLE'
    if L is None or L['status'] != 'FROZEN':
        return 'EMPTY', 'NOT_RUN'
    for f in ('AI_OUTPUT_LOST', 'RESET_DIVERGED', 'RESTART_EXHAUSTED_BY_RESET'):
        if f in L['flags']:
            return 'EMPTY', f
    fz = L['frozen']
    interrupted = bool(L['interrupts']) or any((r['resolution'] or {}).get('action') == 'INTERRUPT'
                                                for r in L['roles'].values())
    if fz['final_next'] in ('GENERATE', 'SCOPE_READER') and not interrupted:
        return 'EMPTY', 'FROZEN_AT_AI_STEP_WITHOUT_INTERRUPT'
    if fz['final_next'].startswith('STOP_') and (L['restart_of'] is not None or L['interrupts']) \
            and fz['carrier_sha256'] is None:
        return 'EMPTY', 'TECHNICAL_STOP_AFTER_RESTART'
    if fz['final_next'] == 'OWNER_DECISION':
        return 'EMPTY', 'OWNER_DECISION'
    if fz['carrier_sha256'] is None:
        return 'EMPTY', 'NO_CARRIER'
    return 'SCORE', 'CARRIER'


def _generator_transcript(L):
    gs = sorted((r['attempt'], k) for k, r in L['roles'].items() if r['role'] == 'G') if L else []
    if not gs:
        return None
    g = L['roles'][gs[-1][1]]
    if g['archives']:
        return g['archives'][-1].get('transcript')
    return (g['resolution'] or {}).get('transcript')


def _starts(R):
    """Every START of run R: role starts, plus a rebase-superseded head START the re-run did not re-create."""
    out = []
    for k, ro in sorted(R['roles'].items()):
        for st in ro['starts']:
            out.append((ro, st))
    have = {(st['role'], st['attempt'], st['start_no']) for _, st in out}
    for rb in R['rebases']:
        st = rb.get('start')
        if st and (st['role'], st['attempt'], st['start_no']) not in have:
            out.append((None, dict(st, superseded_by=st.get('superseded_by') or st['start_no'] + 1)))
    return out


def _item(kind, R, role, attempt, start_no, window):
    it = {'kind': kind, 'case': R['case'] if R else None, 'reader': R['reader'] if R else None,
          'run': R['key'] if R else None, 'role': role, 'attempt': attempt, 'start_no': start_no, 'window': window}
    return dict(it, id=sha(cjson(it))[:12])


def outcomes(state):
    """{'series', 'seq', 'pairs', 'o52_sheet', 'owner_items', 'reruns', 'rebases', 'counts'} (§9.1-9.3). Total:
    any fold state gives a result (an everyday state has no pairs)."""
    jobs = sorted(state['genesis']['jobs'] or [], key=lambda j: j[1])
    pairs, sheet, items, reruns, rebases = [], [], [], [], []
    tol = (state['genesis'].get('gates') or {}).get('p3_clock_tolerance_seconds') or 0     # §X.9 rule 5
    for job in jobs:
        for rd in ('A', 'B'):
            ch = chain(state, job[0], rd)
            L = state['runs'][ch[-1]] if ch else None
            disp, why = _disposition(L, job)
            fz = (L or {}).get('frozen') or {}
            pairs.append({'case': job[0], 'reader': rd, 'run': L['key'] if L else None,
                          'job_dir': L['job_dir'] if L else None, 'frozen_seq': fz.get('seq'),
                          'frozen_sha256': fz.get('frozen_sha256'), 'disposition': disp, 'reason': why,
                          'carrier_sha256': fz.get('carrier_sha256'), 'visual': fz.get('visual', 'NOT_REACHED'),
                          'flags': list(L['flags']) if L else [], 'runs': ch,
                          'transcripts': {'generator': _generator_transcript(L)}, 'also': []})
    for k in state['order']:
        R = state['runs'][k]
        reruns += [dict(x, run=k) for x in R['reruns']]
        rebases += [{'run': k, 'seq': x['seq'], 'head_seq': x['head_seq'], 'base_seq': x['base_seq'],
                     'diverged': x['diverged']} for x in R['rebases']]
        for ro, st in _starts(R):
            nxt = [s2 for s2 in (ro['starts'] if ro else []) if s2['start_no'] == st['superseded_by']]
            window = [utc_minus(st['utc'], tol), utc_minus(nxt[0]['utc'], -tol) if nxt else None] \
                if st['superseded_by'] is not None else None
            sheet.append({'run': k, 'case': R['case'], 'reader': R['reader'], 'role': st['role'],
                          'attempt': st['attempt'], 'start_no': st['start_no'], 'reason': st['reason'],
                          'start_utc': st['utc'], 'boot_id': st['boot_id'],
                          'opened': {'conversation': ro['opened']['conversation'], 'utc': ro['opened']['utc']}
                          if ro and ro['opened'] and latest(ro) is st else None,
                          'archived': [{'revision': a['revision'], 'conversation': a['conversation'],
                                        'utc': a.get('utc')} for a in (ro['archives'] if ro else [])],
                          'resolution': ro['resolution'] if ro else None, 'superseded_by': st['superseded_by'],
                          'window': window})
            if window is not None:
                items.append(_item('SUPERSEDED_WINDOW', R, st['role'], st['attempt'], st['start_no'], window))
        for key, ro in sorted(R['roles'].items()):
            if (ro['resolution'] or {}).get('owner_check'):
                items.append(_item('OWNER_CHECK', R, ro['role'], ro['attempt'], latest(ro)['start_no'], None))
    items.append(_item('O52_SHEET', None, None, None, None, None))
    tr = [p['transcripts']['generator'] for p in pairs]
    counts = {'pairs': len(pairs), 'score': sum(p['disposition'] == 'SCORE' for p in pairs),
              'empty': sum(p['disposition'] == 'EMPTY' for p in pairs),
              'nonattempt': sum(p['disposition'] == 'NONATTEMPT' for p in pairs),
              'transcripts_exported': tr.count('exported'), 'transcripts_not_available': tr.count('not_available'),
              'superseded_starts': sum(1 for i in items if i['kind'] == 'SUPERSEDED_WINDOW'),
              'owner_checks': sum(1 for i in items if i['kind'] == 'OWNER_CHECK'),
              'reruns': len(reruns), 'rebases': len(rebases)}
    return {'series': state['series'], 'seq': state['seq'], 'pairs': pairs, 'o52_sheet': sheet,
            'clock_tolerance_seconds': tol, 'owner_items': items, 'reruns': reruns, 'rebases': rebases,
            'counts': counts}


def final_dispositions(outs, checks):
    """§9.5: apply OWNER_CHECKS.json (`checks`) to `outs` = outcomes(state). Returns {'pairs', 'qualification_flagged',
    'missing'}; raises OwnerChecksInvalid for a wrong outcomes_sha256, an unknown or duplicate id, or a verdict not
    allowed for the item's kind. The input is not modified."""
    if checks.get('outcomes_sha256') != sha(cjson(outs)):
        raise OwnerChecksInvalid('outcomes_sha256')
    byid = {i['id']: i for i in outs['owner_items']}
    seen = {}
    for v in checks.get('verdicts') or []:
        it = byid.get(v.get('id'))
        if it is None or v['id'] in seen or v.get('verdict') not in ALLOWED[it['kind']]:
            raise OwnerChecksInvalid('verdict %s' % str(v.get('id'))[:12])
        seen[v['id']] = v['verdict']
    pairs = [dict(p, also=list(p['also'])) for p in outs['pairs']]
    find = {(p['case'], p['reader']): p for p in pairs}

    def empty(p, reason):
        if p['disposition'] == 'SCORE':
            p['disposition'], p['reason'] = 'EMPTY', reason
        else:
            p['also'].append(reason)
    for iid, verdict in sorted(seen.items()):
        it = byid[iid]
        p = find.get((it['case'], it['reader']))
        if p is None:
            continue
        if verdict in ('WRITE_FOUND', 'CONVERSATION_FOUND'):
            if it['role'] == 'V':
                p['visual'] = 'FAILED_BY_RESET'
            else:
                empty(p, 'OWNER_CHECK_FAILED' if verdict == 'WRITE_FOUND' else 'SUPERSEDED_WINDOW_CONVERSATION')
    flagged = False
    for u in checks.get('unlogged') or []:
        p = find.get((u.get('case'), u.get('reader')))
        if p is None:
            raise OwnerChecksInvalid('unlogged pair')
        empty(p, 'UNLOGGED_CONVERSATION')
        flagged = True
    return {'pairs': pairs, 'qualification_flagged': flagged,
            'missing': [i['id'] for i in outs['owner_items'] if i['id'] not in seen]}
