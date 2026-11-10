"""Reset enumeration (spec §14.3) on invented worlds with the real runner v4 (no memoization: a job costs about 30 s).

A scenario is (world config, target commit, point, variant). The point is where the VM is wiped:
  a  the commit's SAVE block is printed, nothing uploaded (also CP1-CP3 and WP1-WP4: after a reset nothing local
     survives, so a reset anywhere before the first UPLOAD of a commit leaves Drive exactly as here)
  b  the entry is uploaded, `found` not run (CP4)
  c  the entry is confirmed, its parts not uploaded (CP7)          (commits with parts only)
  d  the parts are uploaded, `found` not run (CP8)                (commits with parts only)
  e  the commit is complete and the next block is printed, not done (CP9, CP10: the local STATE and post actions
     are lost with the VM)
Variants: Drive visibility (lag within the waits, lag beyond both waits, duplicate, foreign md5, a lagging foreign
N+1 at restore, md5 hidden) and the Dot's answers for an open role (NOTHING_WRITTEN exported / not_available, WRITTEN,
UNSURE, NO_CONVERSATION with the list showing none / one, ended=no). Every scenario runs to the end of the series (or
its expected STOP) and checks the oracles: O1, O2, O7 on every block (fakes.FakeDot), O3 (dispositions re-derived here
from O44-O46, O55-O58 and the flags the answers require), O4 (audit over FakeDrive's table) and O5 (assemble
--verify-frozen) at FINAL.

Worlds are forked at the target block (fakes.World.snapshot/restore: the same absolute paths), so a group of
scenarios on one config runs its baseline once. Entry point: run(only=None, work=None, jobs=4)."""
import json
import os
import shutil
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CONFIGS = {
    'D': {'series': 'D1'},
    'DL': {'series': 'D1', 'gates': {'p1_conversation_list': 'no'}},
    'DX': {'series': 'D1', 'gates': {'p1_transcript_export': 'no'}},
    'DH': {'series': 'D1', 'gates': {'p2_md5_visible': 'no'}},
    'DRI': {'series': 'D1', 'policy': {'v': 'incomplete', 'v_cont': 'pass'}},
    'E': {'series': 'E1', 'cases': (), 'jobs': 1},
    'Q': {'series': 'Q1'},
}
ANSWERS = {
    'nw_exported': {'outcome': 'NOTHING_WRITTEN', 'transcript': 'exported'},
    'nw_not_available': {'outcome': 'NOTHING_WRITTEN', 'transcript': 'not_available'},
    'written': {'outcome': 'WRITTEN'},
    'unsure': {'outcome': 'UNSURE'},
    'no_conv_none': {'outcome': 'NO_CONVERSATION', 'list_shows_none': 'yes'},
    'no_conv_one': {'outcome': 'NO_CONVERSATION', 'list_shows_none': 'no'},
    'not_ended': {'ended': 'no'},
}


def scenarios():
    """The enumeration (names are stable; TEST_RESULTS.json records the count per tier)."""
    out = []
    # every commit of the D1 baseline x points a, b, e (+ c, d for commits with parts)
    d_commits = [('GENESIS', 1), ('FROZEN', 1), ('FROZEN', 2), ('STAGE', 1), ('AI', 1), ('STAGE', 2), ('AI', 2),
                 ('FROZEN', 3), ('STAGE', 3), ('AI', 3), ('STAGE', 4), ('AI', 4), ('FROZEN', 4), ('FINAL', 1)]
    parts = {('STAGE', 2), ('STAGE', 4), ('FINAL', 1)}
    for k in d_commits:
        for pt in ('a', 'b', 'e') + (('c', 'd') if k in parts else ()):
            out.append({'name': 'D_%s%d_%s' % (k[0], k[1], pt), 'cfg': 'D', 'target': k, 'point': pt})
    # everyday: every commit x points
    e_commits = [('GENESIS', 1), ('INPUTS', 1), ('STAGE', 1), ('AI', 1), ('STAGE', 2), ('AI', 2), ('STAGE', 3),
                 ('DELIVERY', 1), ('FROZEN', 1)]
    eparts = {('STAGE', 2), ('DELIVERY', 1)}
    for k in e_commits:
        for pt in ('a', 'b', 'e') + (('c', 'd') if k in eparts else ()):
            out.append({'name': 'E_%s%d_%s' % (k[0], k[1], pt), 'cfg': 'E', 'target': k, 'point': pt})
    # the 7 Dot answers at the open-role points: G never opened (STAGE1 e), G opened and wrote (AI1 a),
    # V opened and wrote (AI2 a)
    for tgt, pt, tag in ((('STAGE', 1), 'e', 'G0'), (('AI', 1), 'a', 'G'), (('AI', 2), 'a', 'V')):
        for an in ANSWERS:
            out.append({'name': 'D_ans_%s_%s' % (tag, an), 'cfg': 'D', 'target': tgt, 'point': pt, 'answer': an})
    # Drive visibility during a commit and at the head search
    out += [
        {'name': 'D_vis_lag1_commit', 'cfg': 'D', 'target': ('STAGE', 2), 'point': None, 'vis': 'lag1'},
        {'name': 'D_vis_lag2_commit', 'cfg': 'D', 'target': ('STAGE', 2), 'point': None, 'vis': 'lag2'},
        {'name': 'D_vis_dup_commit', 'cfg': 'D', 'target': ('AI', 1), 'point': None, 'vis': 'dup'},
        {'name': 'D_vis_foreign_commit', 'cfg': 'D', 'target': ('AI', 1), 'point': None, 'vis': 'foreign',
         'stop': 'FORK'},
        {'name': 'D_vis_part_lag1', 'cfg': 'D', 'target': ('STAGE', 2), 'point': None, 'vis': 'part_lag1'},
        {'name': 'D_vis_head_lag1', 'cfg': 'D', 'target': ('AI', 1), 'point': 'e', 'vis': 'head_lag1'},
        {'name': 'D_vis_head_dup', 'cfg': 'D', 'target': ('AI', 1), 'point': 'e', 'vis': 'head_dup'},
        {'name': 'D_vis_head_foreign_next', 'cfg': 'D', 'target': ('AI', 1), 'point': 'e', 'vis': 'foreign_next',
         'stop': 'FORK'},
        {'name': 'D_vis_rebase_missing_part', 'cfg': 'D', 'target': ('STAGE', 2), 'point': 'd', 'vis': 'lose_part'},
        {'name': 'D_notes_lost', 'cfg': 'D', 'target': ('AI', 1), 'point': 'e', 'notes': 'none'},
        {'name': 'D_notes_commit_only', 'cfg': 'D', 'target': ('AI', 1), 'point': 'e', 'notes': 'commit'},
        {'name': 'D_two_resets', 'cfg': 'D', 'target': ('STAGE', 2), 'point': 'e', 'again': True},
    ]
    # gates variants: OPENED (no conversation list), no transcript export, md5 hidden
    for k, pt in ((('OPENED', 1), 'a'), (('OPENED', 1), 'e'), (('AI', 1), 'a'), (('STAGE', 1), 'e')):
        out.append({'name': 'DL_%s%d_%s' % (k[0], k[1], pt), 'cfg': 'DL', 'target': k, 'point': pt})
    for k, pt in ((('STAGE', 1), 'e'), (('AI', 1), 'a'), (('STAGE', 2), 'e')):
        out.append({'name': 'DX_%s%d_%s' % (k[0], k[1], pt), 'cfg': 'DX', 'target': k, 'point': pt})
    for k, pt in ((('AI', 1), 'b'), (('STAGE', 2), 'd'), (('FINAL', 1), 'c')):
        out.append({'name': 'DH_%s%d_%s' % (k[0], k[1], pt), 'cfg': 'DH', 'target': k, 'point': pt})
    # REVIEW_INCOMPLETE: the continuation committed, then a reset (F1); and before the continuation is printed
    for k, pt in ((('STAGE', 3), 'e'), (('STAGE', 3), 'a'), (('AI', 3), 'a'), (('AI', 3), 'e')):
        out.append({'name': 'DRI_%s%d_%s' % (k[0], k[1], pt), 'cfg': 'DRI', 'target': k, 'point': pt})
    out += [{'name': 'DRI_baseline', 'cfg': 'DRI', 'target': None, 'point': None},
            {'name': 'Q_baseline', 'cfg': 'Q', 'target': None, 'point': None},
            {'name': 'Q_AI1_a', 'cfg': 'Q', 'target': ('AI', 1), 'point': 'a'},
            {'name': 'D_baseline', 'cfg': 'D', 'target': None, 'point': None},
            {'name': 'E_baseline', 'cfg': 'E', 'target': None, 'point': None}]
    return out


# ================================================================ one config: a baseline and its forks
class Runner:
    def __init__(self, cfg_name, work):
        import fakes
        self.F = fakes
        self.cfg = CONFIGS[cfg_name]
        self.cfg_name, self.work = cfg_name, Path(work)
        self.root = self.work / ('w_' + cfg_name)

    def world(self):
        c = self.cfg
        kw = {'series': c['series'], 'gates': c.get('gates')}
        if 'cases' in c:
            kw['cases'] = c['cases']
        w = self.F.World(self.root, **kw)
        w.dot.policy.update(c.get('policy') or {})
        return w

    def stop_hook(self, w):
        """Everyday: stop at IDLE once the configured number of jobs is done."""
        n = self.cfg.get('jobs')

        def h(dot, lines):
            if n is not None and 'state=IDLE' in lines[0] and len(w.everyday) >= n:
                return 'stop'
            return None
        return h

    def run_group(self, scs):
        """Run the baseline once; fork at each scenario's target block."""
        results, done = [], set()
        w = self.world()
        counts, pending = {}, {}
        snaps = self.work / ('snap_' + self.cfg_name)
        base_hook = self.stop_hook(w)
        todo = [s for s in scs if s.get('target') is not None]
        state = {'seen_e': set()}

        def hook(dot, lines):
            r = base_hook(dot, lines)
            if r:
                return r
            hit = [s for s in todo if s['name'] not in done and self.matches(w, s, lines, counts, state)]
            if hit:
                snap = w.snapshot(snaps)
                for s in hit:
                    done.add(s['name'])
                    results.append(self.fork(w, s, snap, lines))
                w.restore(snap)
                w.dot.hook = hook
            return None
        t0 = time.time()
        try:
            w.dot.hook = hook
            code, lines = w.start()
            code, lines = w.dot.run(code, lines)
            for s in scs:
                if s.get('target') is None:
                    results.append(self.check(w, s, code, lines, t0))
            for s in todo:
                if s['name'] not in done:
                    results.append({'name': s['name'], 'ok': False, 'error': 'target never reached', 'seconds': 0})
        except Exception as e:                                     # noqa: BLE001 - recorded
            results.append({'name': 'baseline_' + self.cfg_name, 'ok': False,
                            'error': '%s: %s' % (type(e).__name__, e), 'trace': traceback.format_exc()[-2500:],
                            'seconds': round(time.time() - t0, 1)})
            for s in scs:
                if s['name'] not in done and not any(r['name'] == s['name'] for r in results):
                    results.append({'name': s['name'], 'ok': False, 'error': 'baseline failed', 'seconds': 0})
        finally:
            w.destroy()
            self.F.force_rmtree(snaps)
        return results

    def matches(self, w, s, lines, counts, state):
        """Is `lines` the block at which scenario s forks? (target commit identified by kind and ordinal)."""
        kind, ordn = s['target']
        hdr = dict(x.split('=', 1) for x in lines[0].split()[1:])
        seq_of = self.commit_seq(w, kind, ordn)
        pt = s.get('point')
        if seq_of is None:
            return False
        name = self.F.N.entry_name(w.series, seq_of)
        if pt in ('a', 'b') or (pt is None and s.get('vis') in ('lag1', 'lag2', 'dup', 'foreign')):
            return hdr['state'] == 'SAVE' and any(ln.startswith('UPLOAD ') and ln.endswith(' AS ' + name)
                                                  for ln in lines)
        if pt in ('c', 'd') or s.get('vis') == 'part_lag1':
            return hdr['state'] == 'SAVE' and any(ln.startswith('UPLOAD ') and (' AS ' + name[:-4] + '_') in ln
                                                  for ln in lines)
        if pt == 'e':
            return int(hdr['head']) == seq_of
        return False

    def commit_seq(self, w, kind, ordn):
        """The seq of the ordn-th commit of `kind` in this world so far, or of the commit now pending."""
        seqs = []
        st = w.cache()
        pend = w.base / 'outbox/v2/PENDING.json'
        head = (st or {}).get('head') or {}
        kinds = w.kinds
        if pend.is_file():
            try:
                pd = json.loads(pend.read_text())
                if pd['seq'] not in kinds:
                    from cpsvm2.vio import savepoint
                    kinds[pd['seq']] = savepoint.read_entry(Path(pd['entry']['path']))['kind']
            except (OSError, ValueError, KeyError):
                pass
        if head.get('seq') and head['seq'] not in kinds:
            p = w.base / 'inbox/journal' / head['name']
            if p.is_file():
                from cpsvm2.vio import savepoint
                kinds[head['seq']] = savepoint.read_entry(p)['kind']
        seqs = sorted(q for q, k in kinds.items() if k == kind)
        return seqs[ordn - 1] if len(seqs) >= ordn else None

    # ---- one fork
    def fork(self, w, s, snap, lines):
        t0 = time.time()
        try:
            w.restore(snap)
            dot = w.dot
            dot.hook = self.stop_hook(w)
            if s.get('answer'):
                dot.policy['restore'] = dict(ANSWERS[s['answer']])
            code, lines = self.inject(w, s, lines)
            code, lines = dot.run(code, lines)
            if s.get('again'):                         # a second reset at the first block of the new boot's work
                code, lines = dot.reset()
                code, lines = dot.run(code, lines)
            return self.check(w, s, code, lines, t0)
        except Exception as e:                         # noqa: BLE001 - recorded per scenario
            return {'name': s['name'], 'ok': False, 'error': '%s: %s' % (type(e).__name__, str(e)[:600]),
                    'trace': traceback.format_exc()[-2500:], 'seconds': round(time.time() - t0, 1),
                    'last': [b['lines'][-1][:200] for b in w.dot.blocks[-4:] if b['lines']]}

    def inject(self, w, s, lines):
        """Carry out the fault at the fork block, then reset (or continue for a pure visibility variant)."""
        d, dot, pt, vis = w.drive, w.dot, s.get('point'), s.get('vis')
        name_of = [ln.split(' AS ')[1] for ln in lines if ln.startswith('UPLOAD ')]
        if vis in ('lag1', 'lag2', 'part_lag1'):
            for n in name_of:
                d.lag[n] = 1 if vis in ('lag1', 'part_lag1') else 2
            return 0, lines
        if vis == 'dup':
            d.dup.update(name_of)
            return 0, lines
        if vis == 'foreign':
            folder = self.F.N.series_folder(w.series)
            d.plant(folder, name_of[0], b'a foreign commit with the same name (invented)')
            return 0, lines
        if pt in ('b', 'd'):
            for ln in lines:
                if ln.startswith('UPLOAD '):
                    t = self.F.shlex.split(ln)
                    d.upload(t[1], t[3], t[5])
            if vis == 'lose_part':
                for n in name_of:
                    if '_PNG' in n:
                        d.remove(self.F.N.series_folder(w.series), n)
                        break
        if vis in ('head_lag1', 'head_dup', 'foreign_next'):
            st = w.cache()
            folder = self.F.N.series_folder(w.series)
            hn = st['head']['name']
            if vis == 'head_lag1':
                for c in d.folders[folder][hn]:
                    c['hidden'] = 1
            elif vis == 'head_dup':
                d.plant(folder, hn, d.bytes_of(folder, hn))
            else:
                nn = self.F.N.entry_name(w.series, st['head']['seq'] + 1)
                c = d.plant(folder, nn, b'a lagging foreign entry (invented)')
                c['hidden'] = 2
        return dot.reset(notes=s.get('notes', 'hint'))

    # ---- oracles at the end
    def check(self, w, s, code, lines, t0):
        res = {'name': s['name'], 'ok': True, 'seconds': None, 'blocks': len(w.dot.blocks),
               'last': lines[-1][:120] if lines else None}
        try:
            want_stop = s.get('stop')
            if want_stop:
                assert lines and lines[-1].startswith('DO: STOP %s ' % want_stop), \
                    'O7: expected STOP %s, got %s' % (want_stop, lines[-1:] or lines)
                self.no_progress_after_stop(w, lines)
            elif w.series[0] == 'E':
                assert 'state=IDLE' in lines[0], 'everyday did not return to IDLE: %s' % lines[-1:]
                self.everyday_checks(w, s)
            else:
                assert lines and lines[-1] == 'DO: STOP FINAL HANDBACK B', 'not FINAL: %s' % lines[-1:]
                self.final_checks(w, s)
        except AssertionError as e:
            res['ok'], res['error'] = False, str(e)[:800]
            res['trail'] = [' | '.join(x[:110] for x in b['lines'][:2] + b['lines'][-1:]) for b in w.dot.blocks[-6:]
                            if b['lines']]
        res['seconds'] = round(time.time() - t0, 1)
        res['answers'] = w.dot.answered
        return res

    def no_progress_after_stop(self, w, lines):
        code, again = w.dot.cmd('go')
        assert again[-1] == lines[-1], 'O7: the series continued past a STOP'

    def final_checks(self, w, s):
        F = self.F
        af = w.all_frozen()
        assert af is not None, 'no ALL_FROZEN part on Drive'
        oc = af['outcomes']
        st = w.state()
        check_dispositions(oc, st)
        check_answers_reflected(w, s, oc, st)
        code, rep, out = w.audit(self.work / ('aud_' + self.cfg_name))
        assert code == 0 and rep['clean'], 'O4: audit not clean: %s %s' % (out.strip()[:300], json.dumps(
            (rep or {}).get('anomalies'))[:500])
        assert rep['outcomes_sha256'] == af['outcomes_sha256'], 'O4: audit outcomes differ from ALL_FROZEN'
        code, arep, out = w.assemble(self.work / ('aud_' + self.cfg_name))
        assert code == 0, 'O5: assemble --verify-frozen: %s' % out.strip()[:300]
        F.force_rmtree(self.work / ('aud_' + self.cfg_name))

    def everyday_checks(self, w, s):
        st = w.state()
        frozen = [R for R in st['runs'].values() if R['status'] == 'FROZEN']
        assert frozen, 'no everyday run frozen'
        for R in frozen:
            if 'AI_OUTPUT_LOST' in R['flags'] or 'RESTART_EXHAUSTED_BY_RESET' in R['flags'] \
                    or 'VISUAL_QA_FAILED_BY_RESET' in R['flags']:
                assert R['frozen'] is not None
        code, rep, out = w.audit(self.work / ('aud_' + self.cfg_name))
        anomalies = [a for a in (rep or {}).get('anomalies', []) if a.get('code') != 'AUD_NOT_FINAL']
        assert rep is not None and not anomalies, 'O4: everyday audit: %s' % json.dumps(anomalies)[:500]
        self.F.force_rmtree(self.work / ('aud_' + self.cfg_name))


# ================================================================ O3: an oracle written from the owner decisions
def check_dispositions(oc, st):
    """Each pair's disposition re-derived here (O44-O46, O55-O58): a chain's last run counts; nonattempt; a reset
    loss (AI_OUTPUT_LOST, RESET_DIVERGED, RESTART_EXHAUSTED_BY_RESET) is EMPTY; a run frozen at GENERATE or
    SCOPE_READER without an interrupt is EMPTY; no carrier is EMPTY; visual QA failed by reset is reported as
    FAILED_BY_RESET, never as PASS."""
    for p in oc['pairs']:
        L = st['runs'][p['run']] if p['run'] else None
        if L is None:
            assert p['disposition'] == 'EMPTY'
            continue
        if L['tag'].startswith('NA-'):
            want = 'NONATTEMPT'
        elif any(f in L['flags'] for f in ('AI_OUTPUT_LOST', 'RESET_DIVERGED', 'RESTART_EXHAUSTED_BY_RESET')):
            want = 'EMPTY'
        elif L['frozen']['carrier_sha256'] is None:
            want = 'EMPTY'
        else:
            want = 'SCORE' if L['frozen']['final_next'] not in ('GENERATE', 'SCOPE_READER', 'OWNER_DECISION') \
                else 'EMPTY'
        assert p['disposition'] == want, 'O3: pair %s/%s is %s, the oracle says %s' % (
            p['case'], p['reader'], p['disposition'], want)
        if 'VISUAL_QA_FAILED_BY_RESET' in L['flags']:
            assert p['visual'] == 'FAILED_BY_RESET', 'O3: visual QA failed by reset reported as %s' % p['visual']
        chain_ = [k for k in st['order'] if st['runs'][k]['case'] == p['case']
                  and st['runs'][k]['reader'] == p['reader']]
        assert p['run'] == chain_[-1], 'O3: the last run of the chain counts'


def check_answers_reflected(w, s, oc, st):
    """The flag each restore answer requires is on the run it resolved (T43-T47)."""
    flags = {f for R in st['runs'].values() for f in R['flags']}
    acts = [r['resolution']['action'] for R in st['runs'].values() for r in R['roles'].values() if r['resolution']]
    for a in w.dot.answered:
        o, role = a.get('outcome'), a.get('role')
        if a.get('ended') == 'no' or o in ('WRITTEN', 'UNSURE') or (o == 'NO_CONVERSATION'
                                                                      and a.get('list_shows_none') == 'no'):
            want = 'VISUAL_QA_FAILED_BY_RESET' if role == 'V' else 'AI_OUTPUT_LOST'
            assert want in flags, 'O3: answer %s for %s needs flag %s (flags %s)' % (o, role, want, sorted(flags))
        elif o == 'NO_CONVERSATION':
            assert 'START_SUPERSEDED' in flags, 'O3: NO_CONVERSATION with the list showing none supersedes the START'
        elif o == 'NOTHING_WRITTEN':
            if role == 'V':
                assert 'REPLACE' in acts, 'O3: V NOTHING_WRITTEN is replaced once (O45)'
            else:
                assert 'INTERRUPT' in acts, 'O3: S/G NOTHING_WRITTEN interrupts (O45)'
            if a.get('transcript') == 'not_available':
                assert 'OWNER_CHECK' in flags and any(i['kind'] == 'OWNER_CHECK' for i in oc['owner_items']), \
                    'O3: not_available needs the owner check (O55)'
        elif o is None and role == 'V':
            assert 'VISUAL_QA_FAILED_BY_RESET' in flags, 'O3: a continued V fails visual QA (O57)'


# ================================================================ entry point
def _group_worker(args):
    cfg, names, work = args
    sys.path.insert(0, HERE)
    scs = [s for s in scenarios() if s['name'] in names]
    return Runner(cfg, Path(work) / ('g_%s_%d' % (cfg, os.getpid()))).run_group(scs)


def plan_groups(only, jobs):
    scs = [s for s in scenarios() if not only or s['name'] in only or s['cfg'] in only]
    by = {}
    for s in scs:
        by.setdefault(s['cfg'], []).append(s['name'])
    groups = []
    for cfg, names in by.items():                           # split a long group across processes
        k = max(1, min(jobs, len(names) // 8))
        for i in range(k):
            groups.append((cfg, names[i::k]))
    return groups, len(scs)


def run(only=None, work=None, jobs=4):
    work = Path(work or '/tmp/test_resets')
    work.mkdir(parents=True, exist_ok=True)
    groups, n = plan_groups(only, jobs)
    t0 = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for r in ex.map(_group_worker, [(c, names, str(work)) for c, names in groups]):
            results += r
    failed = [r for r in results if not r['ok']]
    return {'name': 'test_resets', 'tests': len(results), 'passed': len(results) - len(failed),
            'failed': [r['name'] for r in failed], 'detail': failed,
            'counts': {'scenarios': n, 'groups': len(groups), 'seconds_wall': round(time.time() - t0, 1),
                       'seconds_per_scenario': {r['name']: r['seconds'] for r in results}}}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--only', default='')
    ap.add_argument('--jobs', type=int, default=4)
    a = ap.parse_args()
    r = run([x for x in a.only.split(',') if x] or None, a.work, a.jobs)
    for f in r['detail']:
        print('FAILED', f['name'], f.get('error'))
        if f.get('trace'):
            print(f['trace'])
        if f.get('trail') or f.get('last'):
            print('   ', f.get('trail') or f.get('last'))
    print(json.dumps({k: r[k] for k in ('tests', 'passed')}), r['counts']['seconds_wall'])
    sys.exit(0 if not r['failed'] else 1)
