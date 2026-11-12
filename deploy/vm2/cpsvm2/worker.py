"""The foreground stage body (spec §7.3, §7.5, §7.7, §8.5.1; delta §X.7.2), called in-process by cli.run_stage while
`go` holds the helper lock. It runs the runner chain, the snapshot and the entry build up to PENDING (commit steps
1-4), the self-test, and placement; it prints nothing. Its result is returned in memory: {'status': 'pending' |
'done' | 'fingerprint', ...}; a Halt or OSError propagates to cli.run_stage, which makes it a 'halt' result."""
import os
import time
from pathlib import Path

from . import cli
from .core import fold as F
from .core import names as N
from .core import plan as P
from .core import session as S
from .vio import durable, host, place, runner, savepoint
from .vio.v1compat import Halt
from .vio.v1mod import place_frozen
from .vio.v1reuse import (JobLock, fingerprint, read_json_file, require_space, selftest_work, sha_file, tree_bytes,
                          write_new)

OUTPUT = {'S': 'scope/reader/output', 'V': 'qa/visual_review'}


def dispatch(kind, info, env):
    """The stage of `kind` ('selftest', 'place', 'chain') with the command's own Env (cache loaded, lock held)."""
    if kind == 'selftest':
        selftest_work(env.ctx2(), info)
        return {'status': 'done'}
    if kind == 'place':
        return do_place(env, info)
    return Chain(env, info).run()


def sleep(seconds):
    time.sleep(seconds)


def probe_lock(env, job_dir):
    """§X.7.2: acquire and release JobLock at once, up to JOB_BUSY_TRIES tries JOB_BUSY_GAP_SECONDS apart (only a
    process of this boot that outlived a dead stage can hold it, R6); then JOB_BUSY_TOO_LONG."""
    for i in range(N.JOB_BUSY_TRIES):
        try:
            with JobLock(env.lay, job_dir):
                return
        except Halt as h:
            if h.code != 'JOB_BUSY':
                raise
        if i + 1 < N.JOB_BUSY_TRIES:
            sleep(N.JOB_BUSY_GAP_SECONDS)
    raise Halt('STOP', 'JOB_BUSY_TOO_LONG', 'the job folder stayed locked')


def stat_sig(job_dir):
    """A cheap identity of the job folder (path, type, mode, size, mtime) for "the command changed nothing" (§7.2)."""
    if not os.path.isdir(job_dir):
        return None
    out = []
    for dp, dns, fns in os.walk(job_dir):
        dns.sort()
        for n in sorted(dns + fns):
            st = os.lstat(os.path.join(dp, n))
            out.append([os.path.relpath(os.path.join(dp, n), job_dir), st.st_mode, st.st_size, st.st_mtime_ns])
    return N.sha(N.cjson(out))


def fsha(p):
    return sha_file(p) if os.path.isfile(p) else None


class Chain:
    """One chain (§7.3): first sub-command, then chain_next after each command, at most 6; one entry at the end."""
    def __init__(self, env, info):
        self.env, self.lay, self.run_key, self.first = env, env.lay, info['run'], info['first']
        self.ci = info.get('info') or {}
        self.s = env.state
        self.R = self.s['runs'].get(self.run_key)
        nr = self.ci.get('new_run')
        if nr:
            self.job_dir = str(self.lay.job_dir(nr['tag'], nr['case']))
        elif self.R is not None and self.R['job_dir']:
            self.job_dir = self.R['job_dir']
        else:
            tag, case = self.run_key.split('/', 1)
            self.job_dir = str(self.lay.job_dir(tag, case))
        self.commands, self.parsed, self.log, self.post = [], [], None, []
        rk = self.ci.get('consume')
        if rk is None and self.ci.get('bind') and self.first in P.CONSUMER.values():
            rk = P.consumer_role(self.R)                      # a rebase re-run of a consumer chain (§7.10)
        self.rk = rk

    # ---------------------------------------------------------- facts
    def ledger_sha(self):
        return fsha(self.lay.ledger) if self.env.mode != 'everyday' else None

    def record_sha(self):
        return fsha(os.path.join(self.job_dir, 'RUN_RECORD.json'))

    def argv(self, sub):
        R, ci, st = self.R, self.ci, self.s
        nr = ci.get('new_run') or {}
        tag, case = self.run_key.split('/', 1)
        a = {'base': str(self.lay.base), 'model': self.env.cache['operator']['model'], 'job_dir': self.job_dir,
             'case': case, 'reader': nr.get('reader') or (R or {}).get('reader'), 'root': nr.get('root'),
             'qualification': self.env.mode != 'everyday', 'utc14': tag[1:],
             'admission': ((self.env.release.get('qualification') or {}).get('admissions') or [{}])[0].get('path')}
        rk = self.rk
        if rk:
            ro = R['roles'][rk]
            a['conversation'] = ro['archives'][0]['conversation']
            a['prompt_sha256'] = F.latest(ro)['prompt_sha256']
            if ro['role'] == 'G':
                ai = self.ai_entry(ro)
                a['generator_model'] = ai['body']['attested']['model']
                a['run_dir'] = os.path.relpath(F.latest(ro)['folder'], self.job_dir)
                tr = ai['body']['transcript'] or {}
                if tr.get('status') == 'exported':
                    a['transcript'] = self.transcript(ro, ai)
        if sub == 'interrupt':
            ro = R['roles'][ci['role']]
            a['started_utc'] = F.latest(ro)['utc']
            a['ended_utc'] = self.interrupt_end(ci['resolution'])
            if ci['resolution'].get('conversation'):                                 # INT-R2-03
                a['conversation'] = ci['resolution']['conversation']
        return runner.argv_for(sub, a)

    def interrupt_end(self, res):
        """§7.4: min(RESTORE.utc, now - 1 s); the RESTORE entry is read from inbox/journal when it is there (it is
        kept there after its commit in this boot), else now - 1 s."""
        t = N.utc_epoch(host.now()) - 1
        p = self.lay.inbox / 'journal' / N.entry_name(self.env.series, res['seq'])
        if p.is_file():
            t = min(t, N.utc_epoch(savepoint.read_entry(p)['utc']))
        return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t))

    def ai_entry(self, ro):
        n = N.entry_name(self.env.series, ro['archives'][-1]['seq'])
        return savepoint.read_entry(self.lay.inbox / 'journal' / n)

    def transcript(self, ro, ai):
        """The G transcript at its BASE/transcripts path, put back from the AI entry after a restore (§7.5)."""
        lt = F.latest(ro)
        p = P.transcript_path(str(self.lay.base), self.run_key, ro, lt, ai['body']['transcript']['ext'])
        if not os.path.isfile(p):
            n = N.entry_name(self.env.series, ro['archives'][-1]['seq'])
            place.place_member(self.lay.inbox / 'journal' / n, 'transcript/G%d_%d.%s' % (
                ro['attempt'], lt['start_no'], ai['body']['transcript']['ext']), p)
        return p

    # ---------------------------------------------------------- before the chain
    def prologue(self):
        """Fingerprint (O47), §7.7 FROZEN.json placement, JobLock probe, consumer measurement (I11), G record."""
        fp = fingerprint(self.lay)[0]
        if fp != self.env.cache['fingerprint_sha256']:
            return {'status': 'fingerprint', 'fingerprint': fp}
        placed = []
        for rk in self.ci.get('place_frozen') or []:
            E = self.s['runs'][rk]
            keep = self.lay.frozen_json / ('%s_%s_FROZEN.json' % (E['tag'], E['case']))
            if keep.is_file():
                b = keep.read_bytes()
            else:
                n = N.entry_name(self.env.series, E['frozen']['seq'])
                b = savepoint.member_bytes(self.lay.inbox / 'journal' / n, 'job/FROZEN.json')
            place_frozen(self.lay, E['job_dir'], b, E['frozen']['frozen_sha256'])
            placed.append(['UNPLACE_FROZEN', E['job_dir'], E['frozen']['frozen_sha256']])
        self.post = placed
        probe_lock(self.env, self.job_dir)
        self.consumed = []
        rk = self.rk
        if rk:
            ro = self.R['roles'][rk]
            with JobLock(self.lay, self.job_dir):
                rows = place.walk_output(F.latest(ro)['output'])
            tsha = place.tree_sha(rows)
            if tsha != ro['archives'][-1]['tree_sha256']:
                raise Halt('STOP', 'AI_OUTPUT_CHANGED', 'the archived output changed before its consumer')
            self.consumed = [{'role': ro['role'], 'attempt': ro['attempt'], 'revision': ro['archives'][-1]['revision'],
                              'tree_sha256': tsha}]
            if ro['role'] == 'G':
                self.generation_record(ro)
        return None

    def generation_record(self, ro):
        """§7.5: D/run/GENERATION_RECORD.json from the AI entry's attested values and members (write_new; an existing
        file halts). tools_enabled is the entry's tool list; notes is the fixed O63 sentence (D9)."""
        ai = self.ai_entry(ro)
        lt, at, b = F.latest(ro), ai['body']['attested'], ai['body']
        if sha_file(lt['prompt']) != lt['prompt_sha256']:
            raise Halt('STOP', 'PROMPT_CHANGED', 'the generator prompt changed')
        p = Path(self.job_dir) / 'run' / 'GENERATION_RECORD.json'
        if os.path.lexists(p):
            raise Halt('STOP', 'GENERATION_RECORD_EXISTS', 'the generation record exists')
        ent = self.lay.inbox / 'journal' / N.entry_name(self.env.series, ro['archives'][-1]['seq'])
        fm = savepoint.member_bytes(ent, 'attest/final_message.txt').decode('utf-8')
        tr = b['transcript'] or {}
        rec = {'schema': 'cps.generation-record.v1', 'case_id': self.R['case'], 'reader': self.R['reader'] or 'A',
               'platform': at['platform'], 'model': at['model'], 'effort': at['effort'],
               'conversation_id': b['conversation'], 'started_utc': at['started_utc'], 'ended_utc': at['ended_utc'],
               'prompt_sha256': lt['prompt_sha256'], 'single_user_message': at['single_user_message'],
               'features': at['features'], 'tools_enabled': N.tool_list(savepoint.member_bytes(ent, 'attest/tools.txt')),
               'final_message': fm, 'transcript_status': at['transcript_status'],
               'notes': N.O63_NOTE % at['tools_present']['sha256']}
        if tr.get('status') == 'exported':
            rec['transcript_sha256'] = tr['sha256']
        else:
            rec['transcript_not_available_reason'] = "the operator's platform did not export the transcript (attested)"
        write_new(p, durable.doc_bytes(rec), 0o644)

    # ---------------------------------------------------------- the chain
    def run(self):
        r = self.prologue()
        if r:
            return r
        self.log = str(self.lay.outbox / ('chain_%s.log' % host.utc14(host.now())))       # never printed (§X.2)
        R, mode = self.R, self.env.mode
        bind = (R or {}).get('rebase_bind')
        cn = {'n': 0, 'freeze_retries': 0, 'v_review_incomplete': P.v_review_incomplete(R) if R else 0,
              'diverged': False}
        sub, busy, out = self.first, 0, None
        while True:
            before = (self.record_sha(), self.ledger_sha(), stat_sig(self.job_dir))
            t0 = host.now()
            res, code, osha = runner.run(self.env.ctx2(), sub, self.argv(sub), str(self.log))
            after = (self.record_sha(), self.ledger_sha(), stat_sig(self.job_dir))
            cn['n'] += 1
            kind = 'REFUSED' if res['result'] != 'NEXT' else 'NEXT'
            cmd = {'sub': sub, 'exit': code, 'result': kind, 'next': res['next'], 'codes': res['codes'],
                   'record_sha256_after': after[0], 'ledger_sha256_after': after[1], 'stdout_sha256': osha,
                   'started_utc': t0, 'ended_utc': host.now()}
            res2 = dict(res, record_changed=before[0] != after[0], ledger_changed=before[1] != after[1],
                        tree_changed=before[2] != after[2], bound=None)
            if bind and cn['n'] == len(bind['bound']['commands']):
                res2['bound'] = self.bound_now(res)
            out = P.chain_next(sub, res2, cn, mode, bind['bound'] if bind else None)
            if out['action'] == 'retry':
                cn['n'] -= 1
                busy += 1
                if busy >= N.JOB_BUSY_TRIES:
                    raise Halt('STOP', 'JOB_BUSY_TOO_LONG', 'JOB_BUSY')
                sleep(N.JOB_BUSY_GAP_SECONDS)
                continue
            self.commands.append(cmd)
            self.parsed.append(res)
            cn['diverged'] = cn['diverged'] or out['diverged']
            if sub == 'freeze' and out['row'] == 'X10':
                cn['freeze_retries'] += 1
            if out['action'] == 'stop':
                raise Halt('STOP', out['code'], 'chain')
            if out['action'] == 'run':
                sub = out['sub']
                continue
            break
        self.diverged = cn['diverged']
        return self.commit_end(out)

    def bound_now(self, res):
        sq, car, png = self.saved_qa(), fsha(os.path.join(self.job_dir, 'carrier/convert/carrier.json')), None
        if os.path.isdir(self.job_dir):
            _, _, pf, rels, _ = place.snapshot(self.lay, self.job_dir)
            png = {'whole_sha256': png_whole(self.job_dir, rels, pf, self.run_key)} if pf else None
        return S.bound_values(res['next'], res['codes'], sq, car, png)

    def saved_qa(self):
        p = os.path.join(self.job_dir, 'qa/SAVED_QA.json')
        d = read_json_file(p) if os.path.isfile(p) else None
        if not isinstance(d, dict):
            return None
        return {'sha256': sha_file(p), 'deliverable_sha256': (d.get('deliverable_xlsx') or {}).get('sha256')}

    # ---------------------------------------------------------- the entry
    def commit_end(self, out):
        env = self.env
        if out['entry'] == 'HALT':
            cli.commit(env, cli.draft(env, 'HALT', {'code': out['code'], 'detail': {
                'code': self.commands[-1]['next']}, 'head_seq': env.head_seq()}))
            return {'status': 'pending'}
        if not os.path.isdir(self.job_dir):
            raise Halt('STOP', 'UNCLASSIFIED', 'no job folder after the chain')
        require_space(self.lay, int(tree_bytes(self.job_dir) * 1.1) + 1, 'snapshot')
        members, job_rows, pf, rels, tsha = place.snapshot(self.lay, self.job_dir)
        seq = env.head_seq() + 1
        last = [p for p in self.parsed if p['result'] == 'NEXT']
        lp = last[-1] if last else None
        b = {'run': self.run_key, 'new_run': None, 'prepare_inputs_sha256': None, 'commands': self.commands,
             'next': lp['next'] if lp else (self.R or {}).get('next'),
             'next_args': None, 'codes': lp['codes'] if lp else [], 'consumed': self.consumed, 'start': None,
             'review_incomplete': out['review_incomplete'], 'continue_problems': None,
             'refused': out['code'] if out['entry'] == 'STAGE' and out['code'] else None,
             'rerun': self.ci.get('rerun'), 'rebase': None, 'snapshot': {'members': job_rows, 'tree_sha256': tsha},
             'png': None, 'saved_qa': self.saved_qa(),
             'carrier_sha256': fsha(os.path.join(self.job_dir, 'carrier/convert/carrier.json')),
             'generation_record_sha256': fsha(os.path.join(self.job_dir, 'response/GENERATION_RECORD.json')),
             'fingerprint_checked': True}
        nr = self.ci.get('new_run')
        if nr:
            b['new_run'] = {'tag': nr['tag'], 'case': nr['case'], 'reader': nr['reader'], 'job_dir': self.job_dir,
                            'restart_of': nr['restart_of']}
        if self.R is not None and self.R['status'] == 'INPUTS':
            tag, case = self.run_key.split('/', 1)
            b['new_run'] = {'tag': tag, 'case': case, 'reader': None, 'job_dir': self.job_dir, 'restart_of': None}
            b['prepare_inputs_sha256'] = self.R['inputs']['sha256']
        if lp and lp['args'].get('prompt'):
            b['next_args'] = {'prompt': lp['args'].get('prompt'), 'folder': lp['args'].get('folder')}
        bind = (self.R or {}).get('rebase_bind')
        if bind:
            b['rebase'] = {'head_seq': bind['head_seq'], 'base_seq': bind['base_seq'], 'bound': bind['bound'],
                           'diverged': self.diverged}
        members_extra, parts, post = [], [], list(self.post)
        if pf:
            have = {(f[0], f[3]) for f in ((self.R or {}).get('png') or {}).get('files', [])}
            if all((f[0], f[3]) in have for f in pf):
                b['png'] = {'files': pf, 'whole_sha256': self.R['png']['whole_sha256'],
                            'parts_seq': self.R['png']['parts_seq']}
            else:
                b['png'] = {'files': pf, 'whole_sha256': png_whole(self.job_dir, rels, pf, self.run_key),
                            'parts_seq': seq}
                parts.append({'kind': 'PNG', 'job_dir': self.job_dir, 'rels': rels, 'files': pf,
                              'run': self.run_key})
        if out['start'] and out['entry'] == 'STAGE':
            b['start'] = self.start(out['start'], lp)
        if out['review_incomplete']:
            txt, n = continue_text(self.job_dir, out['code'], self.parsed[-1])
            b['continue_problems'] = n
            V = F.newest(self.R, 'V')
            msg = env.p.attest / ('continue_%s_V%d_%d.txt' % (N.run8(self.run_key), V['attempt'],
                                                              V['continuations'] + 1))
            env.p.attest.mkdir(parents=True, exist_ok=True)
            durable.write(msg, txt.encode('utf-8'))
            members_extra.append(cli.tmember('attest/continue.txt', txt))
        kind = out['entry']
        if kind == 'FROZEN':
            kind = self.frozen_body(b, members_extra, post, seq)
        if out['entry'] == 'STAGE' and out['row'] == 'X18':
            self.standard_copy(lp, b)
        ledger = []
        if env.mode != 'everyday' and os.path.isfile(self.lay.ledger):
            ledger = [('ledger', 'dir', 0o755, None), ('ledger/LEDGER.jsonl', 'file', 0o644,
                                                       self.lay.ledger.read_bytes())]
        mem = members + ledger + cli.roots_of(members_extra) + members_extra
        d = cli.draft(env, kind, b, seq=seq)
        if b['start'] is not None:                      # the START's utc is its entry's utc (§4.4, T20)
            b['start']['utc'] = d['utc']
        cli.commit(env, d, mem, parts, post,
                   png={'files': pf, 'whole_sha256': b['png']['whole_sha256'], 'parts_seq': b['png']['parts_seq']}
                   if b['png'] else None)
        return {'status': 'pending'}

    def start(self, letter, lp):
        """The START of the NEXT role (§4.4): STAGE (attempt 1, or G2 after an in-place interrupt) or REBASE."""
        prompt, folder = lp['args'].get('prompt'), lp['args'].get('folder')
        out = {'S': os.path.join(self.job_dir, OUTPUT['S']), 'V': os.path.join(self.job_dir, OUTPUT['V']),
               'G': os.path.join(folder or '', 'output')}[letter]
        attempt, start_no, reason = 1, 1, 'STAGE'
        if letter == 'G' and any(c['sub'] == 'interrupt' for c in self.commands):
            attempt = 2
        bind = (self.R or {}).get('rebase_bind')
        if bind and not self.diverged and self.R['rebases'] and self.R['rebases'][-1].get('start'):
            old = self.R['rebases'][-1]['start']
            attempt, start_no, reason = old['attempt'], old['start_no'] + 1, 'REBASE'
        u = host.now()
        return {'role': letter, 'attempt': attempt, 'start_no': start_no, 'reason': reason, 'prompt': prompt,
                'prompt_sha256': sha_file(prompt), 'folder': folder, 'output': out, 'utc': u,
                'boot_id': self.env.boot}

    def frozen_body(self, b, members_extra, post, seq):
        env, R = self.env, self.R
        fz = os.path.join(self.job_dir, 'FROZEN.json')
        nexts = [(c['sub'], c['next']) for c in self.commands if c['result'] == 'NEXT']
        pre = [n for s_, n in nexts if s_ not in ('freeze', 'verify-frozen')]
        b['frozen_sha256'] = sha_file(fz)
        b['final_next'] = pre[-1] if pre else ((R or {}).get('next') or nexts[0][1])
        b['final_codes'] = b['codes']
        b['delivery_sent'] = bool(self.ci.get('delivery_sent'))
        b['restart_eligible'] = False
        if env.mode != 'everyday' and (R is None or R['restart_of'] is None) and not (b['new_run'] or {}).get(
                'restart_of'):
            cj = runner.load_runner()
            with cj.Ledger(self.lay.ledger, create=False, readonly=True) as led:
                b['restart_eligible'] = cj.restart_problem(led, self.job_dir) is None
        v = R if R is not None else {'roles': {}, 'snapshot': None}
        b['flags_added'] = sorted(F.expected_frozen_flags(env.state, v, b))
        b['notify'] = P.frozen_notify(env.mode, b['final_next'], b['flags_added'], b['delivery_sent'])
        tag, case = self.run_key.split('/', 1)
        env.p.attest.mkdir(parents=True, exist_ok=True)
        if b['notify'] == 'NOTIFY_OWNER':
            txt = 'CPS run %s stopped: %s; codes: %s. The run is frozen (%s). Entry %s.\n' % (
                self.run_key, b['final_next'], ', '.join(b['final_codes']) or 'none', b['frozen_sha256'][:12],
                N.entry_name(env.series, seq))
            members_extra.append(cli.tmember('attest/notice.txt', txt))
            durable.write(env.p.attest / ('notice_%06d.txt' % seq), txt.encode('utf-8'))
        elif b['notify'] == 'ASK_USER':
            txt = 'The job failed after a reset; a new job only at your request.\n'
            members_extra.append(cli.tmember('attest/ask.txt', txt))
            durable.write(env.p.attest / ('ask_%06d.txt' % seq), txt.encode('utf-8'))
        post.insert(0, ['EVICT', self.job_dir, str(env.journal / N.entry_name(env.series, seq)), b['frozen_sha256'],
                        '%s_%s_FROZEN.json' % (tag, case)])
        return 'FROZEN'

    def standard_copy(self, lp, b):
        """§11.3: BASE/deliver/<run8>/STANDARD.xlsx, a byte copy of the runner's deliver-check file (sha checked)."""
        src = (lp['args'] or {}).get('file')
        want = (b['saved_qa'] or {}).get('deliverable_sha256')
        if not src or not os.path.isfile(src) or sha_file(src) != want:
            raise Halt('STOP', 'UNCLASSIFIED', 'the deliverable differs from SAVED_QA')
        d = self.env.p.deliver / N.run8(self.run_key)
        d.mkdir(parents=True, exist_ok=True)
        durable.write(d / 'STANDARD.xlsx', Path(src).read_bytes())


def png_whole(job_dir, rels, pf, run_key):
    """The sha256 of the PNG tar stream (§3.7) without writing it."""
    from .vio.v1reuse import png_tar_members, write_tar_stream
    import hashlib

    class H:
        def __init__(self):
            self.h = hashlib.sha256()

        def write(self, b):
            self.h.update(b)

        def tell(self):
            return 0

        def flush(self):
            pass
    sink = H()
    man = {'schema': 'cps.vm2-png.v1', 'run': run_key, 'files': pf}
    write_tar_stream(sink, [('MANIFEST.json', 'file', 0o444, 0, durable.doc_bytes(man))] + png_tar_members(job_dir, rels))
    return sink.h.hexdigest()


TEXTS = {
    'REVIEW_INCOMPLETE': 'REVIEW_INCOMPLETE: The visual review at %s/qa/visual_review/VISUAL_REVIEW.json is incomplete '
                         '(%d problems). Complete it in the same file:\n',
    'REVIEW_NOT_FRESH_CONTEXT': 'REVIEW_NOT_FRESH_CONTEXT: In %s/qa/visual_review/VISUAL_REVIEW.json, reviewer.kind must '
                                'be fresh_context_visual_reviewer and reviewer.model and reviewer.effort must be your '
                                'observed model id and reasoning setting (or unknown). Correct only the reviewer block.\n',
    'REVIEWER_CONVERSATION_ID_REQUIRED': 'REVIEWER_CONVERSATION_ID_REQUIRED: In %s/qa/visual_review/VISUAL_REVIEW.json, '
                                         'reviewer.conversation_id must be exactly this conversation\'s id as your '
                                         'platform shows it; if your platform does not show it, remove the key. '
                                         'Correct only the reviewer block.\n'}


def continue_text(job_dir, code, parsed):
    """§7.8 fixed helper texts; for REVIEW_INCOMPLETE up to 20 of the runner's problem strings (page and item names)."""
    det = (parsed.get('json') or {}).get('detail')
    probs = det.get('problems') if isinstance(det, dict) else det if isinstance(det, list) else []
    probs = [p for p in (probs or []) if isinstance(p, str) and p.isascii() and len(p) <= 200]
    if code == 'REVIEW_INCOMPLETE':
        return TEXTS[code] % (job_dir, len(probs)) + ''.join(p + '\n' for p in probs[:20]), len(probs)
    return TEXTS[code] % job_dir, 0


def do_place(env, info):
    """§8.5.1 steps 1-6 from local journal files (the cli downloaded them by id)."""
    lay, ser = env.lay, info['series']
    jr = Path(info['inbox'])
    placed = []
    if info.get('ledger'):
        sha, aside = place.place_ledger(lay, jr / N.entry_name(ser, info['ledger']['seq']), info['ledger']['sha256'])
        placed.append({'what': 'ledger', 'path': str(lay.ledger), 'tree_sha256': sha, 'aside': aside})
    ff = None
    if info.get('job_dir'):
        png, snap = info.get('png'), jr / N.entry_name(ser, info['snapshot_seq'])
        parts = [jr / n for n in (png or {}).get('parts') or []]
        ai = [(jr / N.entry_name(ser, a['seq']), a['output'], (a.get('revision') or 1) > 1) for a in info.get('ai') or []]
        before = info.get('rewalk') and os.path.lexists(info['job_dir']) and rewalk(env, info, snap)  # GAP-02
        t, aside = place.place_job(lay, info['job_dir'], snap, png, parts, ai)
        placed.append({'what': 'job', 'path': info['job_dir'], 'tree_sha256': t, 'aside': aside})
        for tr in info.get('transcripts') or []:
            ent = jr / N.entry_name(ser, tr['seq'])
            man = savepoint.read_entry(ent)
            for m in man['payload']['members']:
                if m[0].startswith('transcript/') and m[1] == 'file':
                    ro = env.state['runs'][info['run']]['roles'][tr['role']]
                    dest = P.transcript_path(str(lay.base), info['run'], ro, F.latest(ro), m[0].rsplit('.', 1)[1])
                    if not os.path.exists(dest):
                        place.place_member(ent, m[0], dest)
        if info.get('rewalk'):
            ff = bool(before) or rewalk(env, info, snap)
    return {'status': 'done', 'placed': placed, 'files_found': ff}


def rewalk(env, info, snap_entry):
    """§8.6 step 3: any file in the open role's output folder other than what the snapshot placed (a CONTINUED V's
    revision 1) is a file found; so is an entry the strict walk refuses."""
    ro = env.state['runs'][info['run']]['roles'][info['open_role']]
    out = F.latest(ro)['output']
    rel = os.path.relpath(out, info['job_dir']).replace(os.sep, '/')
    snap = {(m[0], m[4]) for m in savepoint.read_entry(snap_entry)['payload']['members']}
    try:
        rows = place.walk_output(out)
    except Halt:
        return True
    return any(r[1] == 'file' and ('job/%s/%s' % (rel, r[0]), r[4]) not in snap for r in rows)
