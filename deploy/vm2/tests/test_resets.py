"""Reset enumeration (spec §14.3 with the probe-results delta §X.14) on invented worlds with the real runner v4 (no
memoization: every runner command runs for real; a world forks at its target block with fakes.World.snapshot/restore,
so a group of scenarios on one config runs its baseline once).

A scenario is (world config, target commit, point, variant). The point is where the VM is wiped:
  a   the commit's SAVE block is printed, nothing uploaded (also CP1-CP3: after a reset nothing local survives, so a
      reset anywhere before the first UPLOAD of a commit leaves Drive exactly as here)
  b   the entry is uploaded, `found` not run (CP4)
  c   the entry is confirmed, its parts not uploaded (CP7)          (commits with parts only)
  d   the parts are uploaded, `found` not run (CP8)                (commits with parts only)
  e   the commit is complete and the next block is printed, not done (CP9, CP10)
  FP  inside the foreground stage that follows the target commit (§X.7.2): fakes.Seams raises fakes.Reset before
      the stage's first runner command (FP1), after a named runner command (FP2), after the snapshot (FP3), while the
      PNG parts are written (FP4), or inside a restore's placement stage; `Kill` is the same-boot death
      (FOREGROUND_DIED, the job folder untouched).
Variants: Drive visibility (lag within the waits, lag beyond both waits, duplicate with the same bytes, foreign bytes
with the same size, foreign size, missing part, refused upload approved / never landing / three times, late
appearance after a timeout; at the head search: a lagging head, a duplicate head, a lagging foreign N+1, a listing
row FIND never shows), the Dot's notes (hint, commit only, none), and the Dot's answers for an open role. Every
scenario runs to the end of the series (or its expected STOP) and checks the oracles: O1, O2, O7, L5, L9, L12 on every
block (fakes.FakeDot), O3 (dispositions re-derived here from O44-O46, O55-O58), O4 (audit over FakeDrive's table:
clean) and O5 (assemble --verify-frozen at the original absolute paths after BASE is wiped) at FINAL.

Entry point: run(only=None, work=None, jobs=4)."""
import json
import os
import shlex
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CONFIGS = {
    'D': {'series': 'D1'},
    'DV': {'series': 'D1', 'gates': {'p1_transcript_export': 'yes'}, 'policy': {'export': True}},
    'DRI': {'series': 'D1', 'policy': {'v': 'incomplete', 'v_cont': 'pass'}},
    'Q': {'series': 'Q1', 'cases': (('9990101', 'small'), ('9990103', 'large'), ('9990102', 'nonattempt'))},
    'E': {'series': 'E1', 'cases': (), 'jobs': 1},
    'X': {'series': 'E1', 'cases': (), 'jobs': 1},
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
# the commits of each baseline, in order, and those with parts
COMMITS = {
    'D': [('GENESIS', 1), ('FROZEN', 1), ('FROZEN', 2), ('STAGE', 1), ('AI', 1), ('STAGE', 2), ('AI', 2),
          ('FROZEN', 3), ('STAGE', 3), ('AI', 3), ('STAGE', 4), ('AI', 4), ('FROZEN', 4), ('FINAL', 1)],
    'E': [('GENESIS', 1), ('INPUTS', 1), ('STAGE', 1), ('AI', 1), ('STAGE', 2), ('AI', 2), ('STAGE', 3),
          ('DELIVERY', 1), ('FROZEN', 1)],
}
PARTS = {'D': {('STAGE', 2), ('STAGE', 4), ('FINAL', 1)}, 'E': {('STAGE', 2), ('DELIVERY', 1)}}
VIS = ('lag1', 'lag2', 'dup', 'foreign_same', 'foreign_size', 'refuse', 'refuse_never', 'timeout_late')
VIS_STOP = {'foreign_same': 'FORK', 'foreign_size': 'FORK'}


def scenarios():
    """The bounded enumeration (names are stable; TEST_RESULTS.json records the count per group)."""
    out = []

    def add(name, cfg, target, point, **kw):
        out.append(dict(name=name, cfg=cfg, target=target, point=point, **kw))
    # every commit of the D1 and E1 baselines x points a, b, e (+ c, d for commits with parts)
    for cfg in ('D', 'E'):
        for k in COMMITS[cfg]:
            for pt in ('a', 'b', 'e') + (('c', 'd') if k in PARTS[cfg] else ()):
                add('%s_%s%d_%s' % (cfg, k[0], k[1], pt), cfg, k, pt)
    # inside a foreground stage (FP1-FP4) for every chain kind of the drill, and a restore's placement stage
    fp = [(('GENESIS', 1), 'runner_before', 'nonattempt', 'FP1_nonattempt'),
          (('GENESIS', 1), 'runner_after', 'verify-frozen', 'FP2_nonattempt_verify'),
          (('GENESIS', 1), 'snapshot', 'nonattempt', 'FP3_nonattempt'),
          (('FROZEN', 2), 'runner_before', 'prepare', 'FP1_prepare'),
          (('FROZEN', 2), 'runner_after', 'prepare', 'FP2_prepare'),
          (('FROZEN', 2), 'snapshot', 'prepare', 'FP3_prepare'),
          (('AI', 1), 'runner_before', 'finish', 'FP1_finish'),
          (('AI', 1), 'runner_after', 'finish', 'FP2_finish'),
          (('AI', 1), 'snapshot', 'finish', 'FP3_finish'),
          (('AI', 1), 'png_parts', 'finish', 'FP4_finish'),
          (('AI', 2), 'runner_before', 'visual-record', 'FP1_visual'),
          (('AI', 2), 'runner_after', 'visual-record', 'FP2_visual'),
          (('AI', 2), 'runner_after', 'freeze', 'FP2_visual_freeze'),
          (('AI', 2), 'runner_after', 'verify-frozen', 'FP2_visual_verify'),
          (('AI', 2), 'snapshot', 'visual-record', 'FP3_visual'),
          (('FROZEN', 3), 'runner_after', 'prepare', 'FP2_prepare_B')]
    for tgt, where, sub, tag in fp:                    # armed at the target commit's first SAVE block: the stage that
        add('D_%s' % tag, 'D', tgt, 'a', seam=(where, sub, 'reset'))   # follows that commit is the one interrupted
    add('D_FP_place_ledger', 'D', ('AI', 1), 'e', seam=('place_ledger', None, 'reset_after_reset'))
    add('D_FP_place_job', 'D', ('AI', 1), 'e', seam=('place_job', None, 'reset_after_reset'))
    add('D_kill_finish_same_boot', 'D', ('AI', 1), 'a', seam=('runner_after', 'finish', 'kill'),
        stop='FOREGROUND_DIED')
    add('D_kill_prepare_same_boot', 'D', ('FROZEN', 2), 'a', seam=('runner_before', 'prepare', 'kill'),
        stop='FOREGROUND_DIED')
    for tgt, where, sub, tag in (fp[3], fp[7], fp[11]):
        add('E_%s' % tag, 'E', {('FROZEN', 2): ('INPUTS', 1), ('AI', 1): ('AI', 1), ('AI', 2): ('AI', 2)}[tgt],
            'a', seam=(where, sub, 'reset'))
    # the Dot's answers at the open-role points: G never opened (STAGE1 e), G opened and wrote (AI1 a), V opened and
    # wrote (AI2 a); transcript export is `no` (O55), so NOTHING_WRITTEN is always not_available here
    for tgt, pt, tag in ((('STAGE', 1), 'e', 'G0'), (('AI', 1), 'a', 'G'), (('AI', 2), 'a', 'V')):
        for an in ANSWERS:
            if an != 'nw_exported':
                add('D_ans_%s_%s' % (tag, an), 'D', tgt, pt, answer=an)
    for an in ('nw_exported', 'written', 'no_conv_none'):
        add('DV_ans_G0_%s' % an, 'DV', ('STAGE', 1), 'e', answer=an)
    add('DV_ans_V_nw_exported', 'DV', ('AI', 2), 'a', answer='nw_exported')
    for tgt, pt, tag in ((('STAGE', 1), 'e', 'G0'), (('AI', 2), 'a', 'V')):
        for an in ('nw_not_available', 'written', 'not_ended'):
            add('E_ans_%s_%s' % (tag, an), 'E', tgt, pt, answer=an)
    # Drive visibility during a commit: an entry (AI1), an entry with parts and its parts (STAGE2)
    for v in VIS:
        add('D_vis_%s_entry' % v, 'D', ('AI', 1), None, vis=v, stop=VIS_STOP.get(v))
        add('D_vis_%s_parts' % v, 'D', ('STAGE', 2), 'c', vis=v, stop=VIS_STOP.get(v))
    add('D_vis_refuse_three_times', 'D', ('AI', 1), None, vis='refuse3', stop='UPLOAD_FAILED')
    add('E_vis_refuse_deliv_parts', 'E', ('DELIVERY', 1), 'c', vis='refuse')
    add('E_vis_foreign_same_entry', 'E', ('AI', 1), None, vis='foreign_same', stop='FORK')
    # Drive visibility at the head search, the notes the Dot kept, and the rebase on a missing part
    add('D_head_lag1', 'D', ('AI', 1), 'e', vis='head_lag1')
    add('D_head_dup', 'D', ('AI', 1), 'e', vis='head_dup')
    add('D_head_foreign_next', 'D', ('AI', 1), 'e', vis='foreign_next', stop='FORK')
    add('D_head_foreign_prev_link', 'D', ('AI', 1), 'e', vis='foreign_prev', stop='LINK_MISMATCH')
    add('D_notes_commit_only_gallop', 'D', ('STAGE', 2), 'e', notes='commit')
    add('D_notes_none_step0', 'D', ('AI', 1), 'e', notes='none')
    add('D_rebase_missing_part', 'D', ('STAGE', 2), 'd', vis='lose_part')
    add('D_two_resets', 'D', ('STAGE', 2), 'e', again=True)
    # REVIEW_INCOMPLETE (O61, F1), qualification with a scope stage (v2.1 deleted OPENED and the DL config, §5.2)
    for k, pt in ((('STAGE', 3), 'e'), (('STAGE', 3), 'a'), (('AI', 3), 'a'), (('AI', 3), 'e')):
        add('DRI_%s%d_%s' % (k[0], k[1], pt), 'DRI', k, pt)
    add('Q_ans_S_nw_not_available', 'Q', ('STAGE', 3), 'e', answer='nw_not_available')
    add('Q_ans_G_after_scope_nw', 'Q', ('STAGE', 4), 'e', answer='nw_not_available')
    add('Q_FP2_scope_finish', 'Q', ('AI', 3), 'a', seam=('runner_after', 'scope-finish', 'reset'))
    for c in ('D', 'DV', 'DRI', 'Q', 'E'):
        add('%s_baseline' % c, c, None, None)
    for fn in ('test_helper_busy_second_command_refused', 'test_selftest_died_retried_once_then_stops'):
        add(fn, 'X', None, None, special=fn)
    import rs_v21                                  # delta v2.1 §2.15.5: worlds of their own
    for fn, (series, cases) in sorted(rs_v21.SPEC.items()):
        add(fn, 'X', None, None, special=fn, module='rs_v21', series=series, cases=cases)
    import test_codes
    import test_v1_regressions                     # the v1 regressions that need the real runner (§14.4)
    for x in test_v1_regressions.WORLD + test_codes.WORLD:
        out.append(dict(x))
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
        """Everyday: stop at IDLE once a job is frozen (a request lost to a reset before its INPUTS commit is asked
        again: the user asks once more), or after a second request."""
        n = self.cfg.get('jobs')

        def h(dot, lines):
            if n is None or not lines or 'state=IDLE' not in lines[0]:
                return None
            runs = (w.state() or {}).get('runs') or {}
            if any(R['status'] == 'FROZEN' for R in runs.values()) or len(w.everyday) > n:
                return 'stop'
            return None
        return h

    def run_group(self, scs):
        """Run the baseline once; fork at each scenario's target block. Special tests run on their own worlds."""
        if scs and all(s.get('special') for s in scs):
            return [self.special(s) for s in scs]
        results, done = [], set()
        w = self.world()
        counts = {}
        snaps = self.work / ('snap_' + self.cfg_name)
        base_hook = self.stop_hook(w)
        todo = [s for s in scs if s.get('target') is not None]

        def hook(dot, lines):
            hit = [s for s in todo if s['name'] not in done and self.matches(w, s, lines, counts)]
            if hit:
                snap = w.snapshot(snaps)
                for s in hit:
                    done.add(s['name'])
                    results.append(self.fork(w, s, snap, lines))
                w.restore(snap)
                w.dot.hook = hook2
            return base_hook(dot, lines)
        t0 = time.time()
        early = all(s.get('target') is not None for s in scs)

        def hook2(dot, lines):
            r = hook(dot, lines)
            if early and len(done) == len(todo):         # every fork is done and no scenario needs the baseline's end
                return 'stop'
            return r
        try:
            w.dot.hook = hook2
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
                            'seconds': round(time.time() - t0, 1),
                            'trail': trail(w), 'bootstrap_stop': w.dot.bootstrap_stop})
            for s in scs:
                if s['name'] not in done and not any(r['name'] == s['name'] for r in results):
                    results.append({'name': s['name'], 'ok': False, 'error': 'baseline failed', 'seconds': 0,
                                    'bootstrap_stop': w.dot.bootstrap_stop})
        finally:
            w.destroy()
            self.F.force_rmtree(snaps)
        return results

    def matches(self, w, s, lines, counts):
        """Is `lines` the block at which scenario s forks? (target commit identified by kind and ordinal)."""
        if not lines or not lines[0].startswith('CPSV '):
            return False
        kind, ordn = s['target']
        hdr = dict(x.split('=', 1) for x in lines[0].split()[1:])
        seq_of = self.commit_seq(w, kind, ordn)
        pt = s.get('point')
        if seq_of is None:
            return False
        name = self.F.N.entry_name(w.series, seq_of)
        if pt in ('a', 'b') or (pt is None and s.get('vis')):
            return hdr['state'] == 'SAVE' and any(ln.startswith('UPLOAD ') and ln.endswith(' AS ' + name)
                                                  for ln in lines)
        if pt in ('c', 'd'):
            return hdr['state'] == 'SAVE' and any(ln.startswith('UPLOAD ') and (' AS CPSJ_%s_%06d_' % (
                w.series, seq_of)) in ln for ln in lines)
        if pt == 'e':
            return int(hdr['head']) == seq_of
        return False

    def commit_seq(self, w, kind, ordn):
        """The seq of the ordn-th commit of `kind` in this world so far, or of the commit now pending."""
        st = w.cache()
        pend = w.base / 'outbox/v2/PENDING.json'
        head = (st or {}).get('head') or {}
        kinds = w.kinds
        from cpsvm2.vio import savepoint
        if pend.is_file():
            try:
                pd = json.loads(pend.read_text())
                if pd['seq'] not in kinds:
                    kinds[pd['seq']] = savepoint.read_entry(Path(pd['entry']['path']))['kind']
            except (OSError, ValueError, KeyError):
                pass
        if head.get('seq') and head['seq'] not in kinds:
            p = w.base / 'inbox/journal' / head['name']
            if p.is_file():
                kinds[head['seq']] = savepoint.read_entry(p)['kind']
        seqs = sorted(q for q, k in kinds.items() if k == kind)
        return seqs[ordn - 1] if len(seqs) >= ordn else None

    # ---- one fork
    def fork(self, w, s, snap, lines):
        t0 = time.time()
        try:
            w.restore(snap)
            w.seams.hits = []
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
                    'trail': trail(w), 'bootstrap_stop': w.dot.bootstrap_stop}
        finally:
            w.seams.disarm()

    def inject(self, w, s, lines):
        """Carry out the fault at the fork block, then reset (or continue for a visibility or seam variant)."""
        d, dot, pt, vis = w.drive, w.dot, s.get('point'), s.get('vis')
        F = self.F
        ups = [shlex.split(ln) for ln in lines if ln.startswith('UPLOAD ')]
        names = [t[5] for t in ups]
        folder = F.N.series_folder(w.series)
        if s.get('seam'):
            where, sub, how = s['seam']
            if how == 'reset_after_reset':             # a reset now, then another inside the restore's placement
                w.seams.arm(where, 1, F.Reset, None)
                return dot.reset(notes=s.get('notes', 'hint'))
            w.seams.arm(where, 1, F.Kill if how == 'kill' else F.Reset, sub)
            return 0, lines
        if vis == 'gen_record':                        # the generation record exists before the G consumer runs
            R = w.state()['runs'][w.state()['current']]
            p = Path(R['job_dir']) / 'run' / 'GENERATION_RECORD.json'
            p.write_bytes(b'{"invented": "a record that must not exist yet"}\n')
            return 0, lines
        if vis == 'head_state_sha':                    # the head on Drive is a valid archive whose state sha is wrong
            hn = w.cache()['head']['name']
            for c in d.folders[folder][hn]:
                raw = restate(d.blobs[c['id']])
                d.blobs[c['id']] = raw
                c.update(size=len(raw), md5=F.md5(raw), sha256=F.sha(raw))
            return dot.reset(notes=s.get('notes', 'hint'))
        if vis in ('change_prompt', 'change_output'):  # a file the next stage reads changes (no reset)
            R = w.state()['runs'][w.state()['current']]
            lt = [x for x in R['roles']['G1']['starts'] if x['superseded_by'] is None][-1]
            p = Path(lt['prompt']) if vis == 'change_prompt' else Path(lt['output']) / 'response.json'
            os.chmod(p, 0o644)
            with open(p, 'ab') as fh:
                fh.write(b'\n')
            return 0, lines
        if vis == 'drop_restore':                      # every upload of the RESTORE entry is lost
            d.drop[F.N.entry_name(w.series, w.cache()['head']['seq'] + 1)] = {1, 2, 3}
            return dot.reset(notes=s.get('notes', 'hint'))
        if vis in ('lag1', 'lag2'):
            for n in names:
                d.lag[n] = 1 if vis == 'lag1' else 2
            return 0, lines
        if vis == 'dup':
            d.dup.update(names)
            return 0, lines
        if vis in ('foreign_same', 'foreign_size'):
            t = ups[0]
            size = os.path.getsize(t[1])
            data = (b'a foreign copy with the same name (invented) ' * (size // 40 + 2))[:size]
            if vis == 'foreign_size':
                data = data + b'x'
            d.plant(t[3], t[5], data)
            return 0, lines
        if vis in ('refuse', 'refuse_never', 'refuse3'):
            for n in names:
                d.refuse[n] = {1, 2, 3} if vis == 'refuse3' else {1}
            dot.policy['approve'] = vis == 'refuse'
            return 0, lines
        if vis == 'timeout_late':
            for n in names:
                d.timeout[n], d.late[n] = {1}, 2
            return 0, lines
        if pt in ('b', 'd'):
            for t in ups:
                d.upload(t[1], t[3], t[5])
            if vis in ('lose_part', 'lose_allfz'):
                for n in names:
                    if ('_PNG' if vis == 'lose_part' else '_ALLFZ') in n:
                        d.remove(folder, n)
                        break
        if vis in ('head_lag1', 'head_dup', 'foreign_next', 'foreign_prev', 'ghost'):
            st = w.cache()
            hn, hs = st['head']['name'], st['head']['seq']
            if vis == 'head_lag1':
                for c in d.folders[folder][hn]:
                    c['hidden'] = 1
            elif vis == 'head_dup':
                d.plant(folder, hn, d.bytes_of(folder, hn))
            elif vis == 'foreign_next':
                c = d.plant(folder, F.N.entry_name(w.series, hs + 1), b'a lagging foreign entry (invented)')
                c['hidden'] = 2
            elif vis == 'foreign_prev':
                pn = F.N.entry_name(w.series, hs - 1)
                raw = d.bytes_of(folder, pn)
                d.plant(folder, pn, (b'a foreign earlier entry (invented)' * (len(raw) // 30 + 2))[:len(raw)])
            else:
                d.ghosts.append((folder, F.N.entry_name(w.series, hs + 5),
                                 {'id': 'fakedriveghost00000000001', 'size': 1000, 'created': 0}))
        return dot.reset(notes=s.get('notes', 'hint'))

    # ---- oracles at the end
    def check(self, w, s, code, lines, t0):
        res = {'name': s['name'], 'ok': True, 'seconds': None, 'blocks': len(w.dot.blocks),
               'last': lines[-1][:120] if lines else None, 'bootstrap_stop': w.dot.bootstrap_stop}
        try:
            if s.get('seam'):
                assert w.seams.hits, 'the armed seam %s never fired: the scenario tested nothing' % (s['seam'],)
            want_stop = s.get('stop')
            if want_stop:
                assert lines and lines[-1].startswith('DO: STOP %s ' % want_stop), \
                    'O7: expected STOP %s, got %s' % (want_stop, lines[-1:] or lines)
                self.no_progress_after_stop(w, lines)
                self.extra(w, s)
                if s.get('seam') and s['seam'][2] == 'kill':
                    assert w.jobs_tree() == w.dot.killed_tree, 'X.7.2: the dead stage\'s job folder was touched'
                if s.get('vis') == 'refuse3':
                    assert len(w.dot.stops_a) == 3, 'X.5.6: three UPLOAD_REFUSED stops, got %d' % len(w.dot.stops_a)
            elif w.series[0] == 'E':
                assert lines and 'state=IDLE' in lines[0], 'everyday did not return to IDLE: %s' % lines[-1:]
                self.common_checks(w, s)
                self.extra(w, s)
                self.everyday_checks(w, s)
            else:
                assert lines and lines[-1] == 'DO: STOP FINAL HANDBACK B', 'not FINAL: %s' % lines[-1:]
                self.common_checks(w, s)
                self.extra(w, s)
                self.final_checks(w, s)
        except AssertionError as e:
            res['ok'], res['error'] = False, str(e)[:800]
            res['trail'] = trail(w)
        res['seconds'] = round(time.time() - t0, 1)
        res['answers'] = w.dot.answered
        res['running'] = w.dot.running
        res['uploads_max'] = w.drive.max_upload
        res['refused_stops'] = len(w.dot.stops_a)
        return res

    def extra(self, w, s):
        """The scenario's own oracle (a v1 regression of test_v1_regressions.WORLD), before BASE is wiped."""
        if s.get('extra'):
            getattr(__import__(s.get('module', 'test_v1_regressions')), s['extra'])(w, s)

    def common_checks(self, w, s):
        """§X.6.4/§X.9: every `after=T` is a START's VM-clock utc minus the gate tolerance (fail-closed); §X.5.6: a
        refused upload is FOUND before any re-upload (one UPLOAD_REFUSED stop per refusal that never landed)."""
        tol = w.gates['p3_clock_tolerance_seconds']
        st = w.state() or w.drive_state() or {}
        starts = {x['utc'] for R in (st.get('runs') or {}).values() for ro in R['roles'].values() for x in ro['starts']}
        starts |= {rb['start']['utc'] for R in (st.get('runs') or {}).values() for rb in R['rebases']
                   if rb.get('start')}
        for t, keys in w.dot.attests_after:
            assert self.F.N.utc_minus(t, -tol) in starts, 'X.9: after=%s is not a START utc - %d' % (t, tol)
        seen = {}
        for boot, did, path, sess in w.dot.downloads:  # X.8.4 step 5: a head part's download is reused by placement
            if not sess:                               # (after the RESTORE, DROP_DOWNLOADS empties the inbox, §5.4)
                continue
            assert (boot, did) not in seen or seen[(boot, did)] == path, \
                'X.8.4: %s downloaded twice in one boot (%s, %s)' % (did, seen.get((boot, did)), path)
            seen[(boot, did)] = path
        if s.get('vis') == 'refuse':
            assert w.dot.stops_a, 'X.5.6: a refused upload gives STOP UPLOAD_REFUSED HANDBACK A'
            calls = w.drive.calls
            for n, ks in w.drive.refuse.items():
                ups = [i for i, c in enumerate(calls) if c[0] == 'UPLOAD' and c[2] == n]
                finds = [i for i, c in enumerate(calls) if c[0] == 'FIND' and c[2] == n]
                assert len(ups) == 1 and len([i for i in finds if i > ups[0]]) >= 2, \
                    'X.5.6: after an approved refusal the next block FINDs, never re-uploads'

    def no_progress_after_stop(self, w, lines):
        code, again = w.dot.cmd('go')
        assert again[-1] == lines[-1], 'O7: the series continued past a STOP'

    def final_checks(self, w, s):
        F = self.F
        af = w.all_frozen()
        assert af is not None, 'no ALL_FROZEN part on Drive'
        oc = af['outcomes']
        st = w.state() or w.drive_state()       # a restore that ends in STOP FINAL B builds no local STATE
        check_dispositions(oc, st)
        check_answers_reflected(w, s, oc, st)
        d = self.work / ('aud_' + self.cfg_name)
        code, rep, out = w.audit(d)
        assert code == 0 and rep['clean'], 'O4: audit not clean: %s %s' % (out.strip()[:300], json.dumps(
            (rep or {}).get('anomalies'))[:500])
        assert rep['outcomes_sha256'] == af['outcomes_sha256'], 'O4: audit outcomes differ from ALL_FROZEN'
        F.force_rmtree(w.base)                         # O5 at the original absolute paths (R25)
        code, arep, out = w.assemble(d)
        # O5 (MAINT-1): every run is placed inside the dedicated root. Runner v4 (pinned) verifies a qualification-mode
        # run only at its original absolute path, so under a dedicated root a Q or D run's verify-frozen is
        # STOP_FROZEN_FOLDER_CHANGED and the assembly is UNCLEAN (fail-closed, score_check ASSEMBLE_NOT_VERIFIED): the
        # open MAINT-1/MAINT-5 decision of track M. Everyday runs verify DONE.
        ok = ('DONE',) if st['mode'] == 'everyday' else ('DONE', 'STOP_FROZEN_FOLDER_CHANGED')
        assert arep and not arep['problems'] and arep['runs'] and all(
            r['verify'] in ok and r['path'].startswith(os.path.realpath(arep['root']) + '/') for r in arep['runs']) \
            and (code == 0) == all(r['verify'] == 'DONE' for r in arep['runs']), \
            'O5: assemble --verify-frozen: %s' % out.strip()[:300]
        F.force_rmtree(d)

    def everyday_checks(self, w, s):
        st = w.state()
        frozen = [R for R in st['runs'].values() if R['status'] == 'FROZEN']
        assert frozen, 'no everyday run frozen'
        for R in frozen:
            if 'AI_OUTPUT_LOST' in R['flags'] or 'RESTART_EXHAUSTED_BY_RESET' in R['flags'] \
                    or 'VISUAL_QA_FAILED_BY_RESET' in R['flags']:
                assert R['frozen'] is not None and not R['frozen'].get('delivery_sent')
        code, rep, out = w.audit(self.work / ('aud_' + self.cfg_name))
        anomalies = [a for a in (rep or {}).get('anomalies', []) if a.get('code') != 'AUD_NO_FINAL']
        assert rep is not None and not anomalies, 'O4: everyday audit: %s' % json.dumps(anomalies)[:500]
        self.F.force_rmtree(self.work / ('aud_' + self.cfg_name))


    # ---- the foreground tests that need no baseline (§X.14)
    def special(self, s):
        t0 = time.time()
        root = self.work / ('x_' + s['name'][-20:])
        w = None
        try:
            kw = {} if s.get('series') == 'D1' and s.get('cases') is None else {'cases': s.get('cases') or ()}
            w = self.F.World(root, series=s.get('series') or 'E1', plant_pass=not s.get('no_pass') and s['special'] != (
                'test_selftest_died_retried_once_then_stops'), **kw)
            fn = getattr(self, s['special'], None) or getattr(__import__(s.get('module', 'test_v1_regressions')),
                                                              s['special'])
            fn(w)
            return {'name': s['name'], 'ok': True, 'seconds': round(time.time() - t0, 1)}
        except Exception as e:                                     # noqa: BLE001 - recorded
            return {'name': s['name'], 'ok': False, 'error': '%s: %s' % (type(e).__name__, str(e)[:600]),
                    'trace': traceback.format_exc()[-2500:], 'seconds': round(time.time() - t0, 1),
                    'trail': trail(w) if w else [], 'bootstrap_stop': w.dot.bootstrap_stop if w else None}
        finally:
            if w is not None:
                w.destroy()

    def test_helper_busy_second_command_refused(self, w):
        """§X.6.2: while another process holds the helper lock (a `go` in a foreground stage), `go`, `found` and
        `answer` each print exactly the CPSV-BUSY block and exit 4, and every cache file stays byte-identical (O7);
        once the holder ends its stage (FOREGROUND.json removed, lock released) the next `go` prints the block again."""
        import subprocess
        from cpsvm2.vio import durable
        w.dot.hook = lambda dot, lines: 'stop' if lines and 'state=IDLE' in lines[0] else None
        code, lines = w.dot.run(*w.start())
        assert 'state=IDLE' in lines[0], lines
        w.dot.hook = None
        v2 = w.base / 'outbox/v2'
        fg = durable.write_doc(v2 / 'FOREGROUND.json', {'schema': 'cps.vm2-foreground.v1', 'kind': 'chain',
                                                        'run': None, 'first': 'prepare', 'attempt': 1,
                                                        'boot_id': w.boot, 'pid': 1, 'started_utc': w.clock.now(),
                                                        'max_seconds': 600})
        before = self.F.cache_files(v2)
        holder = subprocess.Popen([sys.executable, '-I', '-B', '-c',
                                   'import fcntl, os, sys, time\n'
                                   'fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)\n'
                                   'fcntl.flock(fd, fcntl.LOCK_EX)\nprint("held", flush=True)\ntime.sleep(120)\n',
                                   str(w.base / 'outbox/.lock')], stdout=subprocess.PIPE, text=True)
        try:
            assert holder.stdout.readline().strip() == 'held'
            at = lines[0].split(' at=')[1].split()[0]
            for argv in (('go',), ('found', '--at', at, '--name', 'CPSJ_E1_000002.tgz', '--none'),
                         ('answer', '--at', at, 'case=9990299')):
                code, out = w.dot.cmd(*argv)
                assert code == 4 and out == ['CPSV-BUSY kind=chain since=%s' % fg['started_utc'],
                                             'REFUSED HELPER_BUSY', 'DO: POLL'], (code, out)
                assert self.F.cache_files(v2) == before, 'O7: a busy command changed a cache file'
        finally:
            holder.kill()
            holder.wait()
        os.unlink(v2 / 'FOREGROUND.json')
        code, again = w.dot.cmd('go')
        assert code == 0 and again == lines, (code, again)

    def test_selftest_died_retried_once_then_stops(self, w):
        """§X.7.2 step 4: no PASS on Drive, so the session runs the self-test as a foreground stage of `go` (found
        prints RUN go). The process dies in it twice in one boot (fakes.Kill): the first dead FOREGROUND.json is moved
        to outbox/v2/dead_<utc14>.json and the self-test runs again at attempt 2; the second death is the local sticky
        STOP SELFTEST_DIED HANDBACK C."""
        w.seams.arm('selftest', 1, self.F.Kill, None, times=2)
        code, lines = w.dot.run(*w.start())
        assert lines[-1] == 'DO: STOP SELFTEST_DIED HANDBACK C', lines
        assert [r['kind'] for r in w.dot.running] == [], 'a killed stage prints only its RUNNING line'
        runs = [b for b in w.dot.blocks if b.get('kill')]
        assert len(runs) == 2 and all(b['lines'][0].startswith('CPSV-RUNNING kind=selftest ') for b in runs), runs
        assert list((w.base / 'outbox/v2').glob('dead_*.json')), 'the first dead self-test record is kept'
        self.no_progress_after_stop(w, lines)


def restate(raw):
    """An entry archive with the same members whose MANIFEST.json claims another state_sha256."""
    import io
    import tarfile
    out = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as src, \
            tarfile.open(fileobj=out, mode='w:gz', format=tarfile.PAX_FORMAT) as dst:
        for ti in src.getmembers():
            data = src.extractfile(ti).read() if ti.isfile() else None
            if ti.name == 'MANIFEST.json':
                m = json.loads(data)
                m['state_sha256'] = '0' * 64
                data = (json.dumps(m, sort_keys=True, ensure_ascii=True, indent=1) + '\n').encode()
                ti.size = len(data)
            dst.addfile(ti, io.BytesIO(data) if data is not None else None)
    return out.getvalue()


def trail(w):
    return [' | '.join(x[:110] for x in b['lines'][:2] + b['lines'][-1:]) for b in w.dot.blocks[-6:] if b['lines']]


# ================================================================ O3: an oracle written from the owner decisions
def check_dispositions(oc, st):
    """Each pair's disposition re-derived here (O44-O46, O55-O58): a chain's last run counts; nonattempt; a reset
    loss (AI_OUTPUT_LOST, RESET_DIVERGED, RESTART_EXHAUSTED_BY_RESET) is EMPTY; a run frozen at GENERATE or
    SCOPE_READER without an interrupt is EMPTY; a technical stop after a restart with no carrier is EMPTY; no carrier
    is EMPTY; visual QA failed by reset is reported as FAILED_BY_RESET, never as PASS."""
    for p in oc['pairs']:
        L = st['runs'][p['run']] if p['run'] else None
        if L is None:
            assert p['disposition'] == 'EMPTY'
            continue
        interrupted = bool(L['interrupts']) or any((r['resolution'] or {}).get('action') == 'INTERRUPT'
                                                    for r in L['roles'].values())
        if L['tag'].startswith('NA-'):
            want = 'NONATTEMPT'
        elif any(f in L['flags'] for f in ('AI_OUTPUT_LOST', 'RESET_DIVERGED', 'RESTART_EXHAUSTED_BY_RESET')):
            want = 'EMPTY'
        elif L['frozen']['final_next'] in ('GENERATE', 'SCOPE_READER') and not interrupted:
            want = 'EMPTY'
        elif L['frozen']['final_next'] == 'OWNER_DECISION' or L['frozen']['carrier_sha256'] is None:
            want = 'EMPTY'
        else:
            want = 'SCORE'
        assert p['disposition'] == want, 'O3: pair %s/%s is %s, the oracle says %s' % (
            p['case'], p['reader'], p['disposition'], want)
        if 'VISUAL_QA_FAILED_BY_RESET' in L['flags']:
            assert p['visual'] == 'FAILED_BY_RESET', 'O3: visual QA failed by reset reported as %s' % p['visual']
        chain_ = [k for k in st['order'] if st['runs'][k]['case'] == p['case']
                  and st['runs'][k]['reader'] == p['reader']]
        assert p['run'] == chain_[-1], 'O3: the last run of the chain counts'


def check_answers_reflected(w, s, oc, st):
    """The flag or action each restore answer requires is on the run it resolved (T43-T47)."""
    flags = {f for R in st['runs'].values() for f in R['flags']}
    acts = [r['resolution']['action'] for R in st['runs'].values() for r in R['roles'].values() if r['resolution']]
    for a in w.dot.answered:
        o, role = a.get('outcome'), a.get('role')
        if a.get('ended') == 'no' or o in ('WRITTEN', 'UNSURE') or (o == 'NO_CONVERSATION'
                                                                      and a.get('list_shows_none') == 'no'):
            want = 'VISUAL_QA_FAILED_BY_RESET' if role == 'V' else 'AI_OUTPUT_LOST'
            assert want in flags, 'O3: answer %s for %s needs flag %s (flags %s)' % (o, role, want, sorted(flags))
        elif o == 'NO_CONVERSATION' and a.get('list_shows_none') is None:      # no list (or not asked): forced
            want = 'VISUAL_QA_FAILED_BY_RESET' if role == 'V' else 'AI_OUTPUT_LOST'
            assert want in flags, 'O3: NO_CONVERSATION without the list needs flag %s' % want
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
    import seen
    seen.install()
    scs = [s for s in scenarios() if s['name'] in names]
    try:
        return Runner(cfg, Path(work) / ('g_%s_%d' % (cfg, os.getpid()))).run_group(scs)
    finally:
        seen.dump()


def plan_groups(only, jobs):
    scs = [s for s in scenarios() if not only or s['name'] in only or s['cfg'] in only]
    by = {}
    for s in scs:
        by.setdefault(s['cfg'], []).append(s['name'])
    groups = []
    for cfg, names in by.items():                           # split a long group across processes
        k = max(1, min(jobs, len(names) // 12))
        for i in range(k):
            groups.append((cfg, names[i::k]))
    groups.sort(key=lambda g: -len(g[1]))                    # longest first
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
    stage = {}
    for r in results:
        for x in r.get('running') or []:
            k = x['first'] or x['kind']
            stage[k] = max(stage.get(k, 0), x['seconds'])
    return {'name': 'test_resets', 'tests': len(results), 'passed': len(results) - len(failed),
            'failed': [r['name'] for r in failed], 'detail': failed,
            'counts': {'scenarios': n, 'groups': len(groups), 'seconds_wall': round(time.time() - t0, 1),
                       'per_config': {c: sum(1 for s in scenarios() if s['cfg'] == c and (not only or s['name'] in only
                                                                                         or c in only))
                                      for c in CONFIGS},
                       'stage_seconds_max': stage,
                       'max_upload_bytes_seen': max([r.get('uploads_max') or 0 for r in results] or [0]),
                       'seconds_per_scenario': {r['name']: r['seconds'] for r in results}}}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--only', default='')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    r = run([x for x in a.only.split(',') if x] or None, a.work, a.jobs)
    for f in r['detail']:
        print('FAILED', f['name'], f.get('error'))
        if f.get('trace'):
            print(f['trace'])
        if f.get('trail'):
            print('   ', '\n    '.join(f['trail']))
    if a.out:
        with open(a.out, 'w') as fh:
            json.dump(r, fh, indent=1, default=str)
    print(json.dumps({k: r[k] for k in ('tests', 'passed')}), r['counts']['seconds_wall'],
          json.dumps(r['counts']['stage_seconds_max']))
    sys.exit(0 if not r['failed'] else 1)
