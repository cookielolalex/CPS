"""Tests of the maintainer side (§10, §9.5; §14.4 rows F5, FLAGS-1..3, INT-03, INT-04, INT-05, INT-08, INT-09,
IMP-16; delta v2.1 MAINT-1 to MAINT-10, GAP-06, GAP-10): audit, assemble and score_check on invented journals. A Journal drives core_world.World (the core tests'
entry builders and legal-move generator) and materializes every entry for real: tgz archives with the reused
write_tgz, job snapshots, PNG part streams, a runner-format ledger, kit zips, a Drive listing and the downloads, so the
maintainer tools read bytes exactly as they would from Drive. No runner command runs except verify-frozen in
assemble's test (on invented, non-qualification frozen folders). Entry point: run(only, work)."""
import copy
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import core_world as CW                                                  # noqa: E402
from cpsvm2.core import fold as F, session as S                          # noqa: E402
from cpsvm2.core.names import cjson, entry_name, series_folder, sha, utc_epoch, utc_minus  # noqa: E402
from cpsvm2.maint import assemble as AS, audit as AU, score_check as SC  # noqa: E402
from cpsvm2.vio.runner import load_runner                                 # noqa: E402
from cpsvm2.vio.v1reuse import kit_members, remove_tree, write_tar_stream, write_tgz  # noqa: E402

RN = vars(load_runner())
JOBS2 = [['case01', 1, None], ['case02', 2, 'NONATTEMPT_SOURCE_UNAVAILABLE']]
FULL = ['PREPARE_GENERATE', 'AI', 'FINISH', 'AI', 'VISUAL_PASS']
WORK = None
# The O63 texts as the delta pins them (§2.8); the tests hold their own copy, so a changed sentence is caught.
O63_NOTE = ('O63: generator isolation by instruction only, not enforced or audited; tools present: %s; any tools-used '
            'statement is in final_message.')
O63_REPORT = ('Isolation of the generator, scope-reader and visual-reviewer conversations was by instruction only (owner '
              'decision O63): neither enforced nor audited. The tools present in each conversation are recorded in its '
              'AI entry and, for generators, in GENERATION_RECORD.json.')
TOOLS = b'invented_tool_a\ninvented_tool_b\n'
FMSG = 'an invented final message {with} <any> characters'.encode()
FOLDER_ROW = 'application/vnd.google-apps.folder'


def md5(b):
    return hashlib.md5(b).hexdigest()


def jbytes(x):
    return AU.doc_bytes(x)


def ctime(t):
    return time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(t))


def jobs_doc(jobs):
    return jbytes({'cases': [{'case_id': c, 'order': o, 'nonattempt': bool(r), 'reason': r or None}
                             for c, o, r in jobs]})


def release_for(base, tag=b'invented-1'):
    return jbytes({'release': tag.decode(), 'qualification': {'jobs_file': base + '/runtime/qualification/JOBS.json'}})


def kit_zip(release, config, extra=b't1', jobs=JOBS2):
    files = {'RELEASE.json': release, 'VM_HELPER_CONFIG.json': jbytes(config), 'tables/t.json': extra,
             'qualification/JOBS.json': jobs_doc(jobs)}
    sums = ''.join('%s  %s\n' % (sha(v), k) for k, v in sorted(files.items())).encode()
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w') as z:
        for k, v in sorted(dict(files, SHA256SUMS=sums).items()):
            z.writestr(zipfile.ZipInfo(k, (2026, 1, 1, 0, 0, 0)), v)
    return bio.getvalue()


def config(series, gates=None, **kw):
    c = {'schema': 'cps.vm2-config.v1', 'series': series, 'accepted_helper_tree_sha256': [CW.TREE],
         'accepts_release_sha256': [], 'selftest_expected_tests': 1, 'clock_wait_max_seconds': 60,
         'foreground_hold_seconds': 1200, 'stage_max_seconds': {}, 'max_upload_bytes': 50000000,
         'png_part_bytes': 1000000, 'max_entry_bytes': 1000000,
         'max_transcript_bytes': 1000, 'max_ai_output_bytes': 1000, 'conversation_re': 'conv-[A-Z0-9]+',
         'transcript_ext': 'json', 'drive_id_re': '[A-Za-z0-9_-]{20,80}', 'gates': gates or CW.GATES, 'clear': None,
         'doc_samples': []}
    c.update(kw)
    return c


class Journal:
    """One invented series, materialized under `root`: dl/<id>/<name> (the series folder), setup/<id>/<name>."""

    def __init__(self, root, series='D1', jobs=JOBS2, gates=None, kit_jobs=None, **cfg):
        self.root, self.series, self.slip = root, series, None
        self.w = CW.World(series, gates=gates, jobs=copy.deepcopy(jobs))
        self.rows, self.srows, self.data, self.ledger, self.trees, self.pngs = [], [], {}, {}, {}, {}
        self.release, self.jobs = release_for(CW.BASE), kit_jobs or jobs
        self.kit = self.add_kit(self.release, config(series, self.w.gates, **cfg))
        self.w.kit = self.kit
        pb = b'{"pass": "invented"}\n'
        self.passref = {'name': 'FINGERPRINT_PASS_%s.json' % CW.FP, 'md5': md5(pb)}
        self.upload(self.srows, 'setup', self.passref['name'], pb, CW.T0)
        self.fork_ledger_at = None

    # ---------------------------------------------------------------- files on "Drive"
    def upload(self, rows, folder, name, data, t):
        fid = 'id' + sha(name.encode() + data)[:28]
        d = os.path.join(self.root, folder, fid)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), 'wb') as f:
            f.write(data)
        rows.append({'id': fid, 'name': name, 'md5Checksum': md5(data), 'size': len(data), 'createdTime': ctime(t)})
        return rows[-1]

    def add_kit(self, release, cfg, extra=b't1'):
        z = kit_zip(release, cfg, extra, self.jobs)
        if 'SESSION_KIT_%s.zip' % sha(z)[:12] not in [r['name'] for r in self.srows]:
            self.upload(self.srows, 'setup', 'SESSION_KIT_%s.zip' % sha(z)[:12], z, CW.T0)
        return sha(z)

    def kit_dict(self, k):
        """The session's kit dict of an uploaded kit zip (as cli builds it)."""
        r = [r for r in self.srows if r['name'] == 'SESSION_KIT_%s.zip' % k[:12]][0]
        m = kit_members(os.path.join(self.root, 'setup', r['id'], r['name']))
        return {'sha256': k, 'members': sorted([p, sha(v)] for p, v in m.items()),
                'config': json.loads(m['VM_HELPER_CONFIG.json']), 'release_sha256': sha(m['RELEASE.json'])}

    def row(self, name):
        return [r for r in self.rows if r['name'] == name][0]

    def copy_of(self, name):
        r = self.row(name)
        return {'id': r['id'], 'md5': r['md5Checksum'], 'size': r['size']}

    def drop(self, name):
        self.rows = [r for r in self.rows if r['name'] != name]

    # ---------------------------------------------------------------- materialize one draft
    def content(self, run, seq, e):
        """The run's job tree after this STAGE/FROZEN: {rel: bytes}, png {rel: bytes}; updates the draft body."""
        b, s = e['body'], self.w.state
        R = s['runs'].get(run)
        nr = b['new_run'] or R
        t = self.trees.setdefault(run, {})
        t['RUN_RECORD.json'] = RN['dumps']({'schema': 'cps.job-run-record.v2', 'qualification': False,
                                            'case_id': nr['case'], 'reader': nr['reader'], 'stages': [],
                                            'note': 'invented seq %d' % seq})
        if b['carrier_sha256'] is not None:
            t['carrier/convert/carrier.json'] = jbytes({'items': [{'row': 1, 'run': run}]})
            b['carrier_sha256'] = sha(t['carrier/convert/carrier.json'])
        if any(c['role'] == 'G' for c in b['consumed']):         # the finish stage writes the generation record
            sl = self.slip
            t['run/GENERATION_RECORD.json'] = jbytes({
                'schema': 'cps.generation-record.v1', 'case_id': nr['case'],
                'tools_enabled': TOOLS.decode().splitlines() + (['other_tool'] if sl == 'tools' else []),
                'notes': O63_NOTE % ('0' * 64 if sl == 'notes' else sha(TOOLS)),
                'final_message': 'another message' if sl == 'final' else FMSG.decode()})
        if b['png'] is not None and b['png']['parts_seq'] == seq:
            t['qa/visual_deliverable/VISUAL_QA_MANIFEST.json'] = jbytes({'images': [{'file': 'p1.png'}]})
            self.pngs[run] = {'qa/visual_deliverable/p1.png': b'\x89PNG invented ' + run.encode() * 50}
        return t, self.pngs.get(run, {})

    def job(self, e, members):
        b, seq, run = e['body'], e['seq'], e['body']['run']
        frozen = e['kind'] == 'FROZEN'
        t, pngs = self.content(run, seq, e)
        fm, dm = (0o444, 0o555) if frozen else (0o644, 0o755)
        if frozen:
            allf = dict(t, **pngs)
            allf.pop('FROZEN.json', None)
            dirs = sorted({'/'.join(k.split('/')[:i]) for k in allf for i in range(1, k.count('/') + 1)})
            nr = b['new_run'] or self.w.state['runs'][run]
            t['FROZEN.json'] = RN['dumps']({
                'schema': 'cps.job-frozen.v2', 'case_id': nr['case'], 'reader': nr['reader'], 'qualification': False,
                'ledger': None, 'frozen_utc': e['utc'], 'freeze_seq': 1,
                'run_record_sha256': sha(t['RUN_RECORD.json']),
                'files': [{'path': k, 'bytes': len(v), 'sha256': sha(v)} for k, v in sorted(allf.items())],
                'directories': dirs, 'other_entries': [], 'retry_permitted': False, 'repair_permitted': False})
            b['frozen_sha256'] = sha(t['FROZEN.json'])
        dirs = {'/'.join(k.split('/')[:i]) for k in list(t) + list(pngs) for i in range(1, k.count('/') + 1)}
        members['job'] = ('dir', dm, None)
        for d in dirs:
            members['job/' + d] = ('dir', dm, None)
        for k, v in t.items():
            members['job/' + k] = ('file', fm, v)
        R = self.w.state['runs'].get(run)
        if pngs and (b['png'] is None or b['png']['parts_seq'] != seq):
            old = R['png']
            b['png'] = {'files': [[f[0], fm, f[2], f[3]] for f in old['files']], 'whole_sha256': old['whole_sha256'],
                        'parts_seq': old['parts_seq']}
        parts = []
        if b['png'] is not None and b['png']['parts_seq'] == seq:
            files = [['job/' + k, fm, len(v), sha(v)] for k, v in sorted(pngs.items())]
            bio = io.BytesIO()
            write_tar_stream(bio, [('MANIFEST.json', 'file', 0o444, 0, jbytes(
                {'schema': 'cps.vm2-png.v1', 'run': run, 'files': files}))] +
                [('job/' + k, 'file', fm, 0, v) for k, v in sorted(pngs.items())])
            stream = bio.getvalue()
            cut = len(stream) // 2
            parts = [('PNG', 1, stream[:cut]), ('PNG', 2, stream[cut:])]
            b['png'] = {'files': files, 'whole_sha256': sha(stream), 'parts_seq': seq}
        jm = sorted([k, v[0], v[1], len(v[2]) if v[2] is not None else None, sha(v[2]) if v[2] is not None else None]
                    for k, v in members.items() if k == 'job' or k.startswith('job/'))
        b['snapshot'] = {'members': len(jm), 'tree_sha256': sha(cjson(jm + (b['png'] or {}).get('files', [])))}
        e['payload']['png'] = b['png']
        return parts

    def materialize(self, e, final_pass=None):
        s, seq, ser = self.w.state, e['seq'], self.series
        if seq == 1:
            e['release_sha256'], e['kit_sha256'] = sha(self.release), self.kit
        if e['kind'] in ('GENESIS', 'RESTORE'):
            e['body']['pass'] = dict(self.passref)
        if seq > 1:
            e['prev_sha256'] = sha(self.data[seq - 1])
            empty = {c['name'] for c in e['confirms'] if not c['copies']}
            e['confirms'] = [{'name': entry_name(ser, seq - 1), 'copies': [self.copy_of(entry_name(ser, seq - 1))]}] + [
                {'name': p[0], 'copies': [] if p[0] in empty else [self.copy_of(p[0])]} for p in s['undo']['parts']]
        members = {}
        for m in e['payload']['members']:
            members[m[0]] = ('dir', m[2], None) if m[1] == 'dir' else \
                ('file', m[2], ('invented %s %d\n' % (m[0], seq)).encode())
        if e['kind'] == 'AI':                   # O63 (§2.8): the tools present and the final message, archived
            members.update({'attest': ('dir', 0o755, None), 'attest/final_message.txt': ('file', 0o644, FMSG)})
            if self.slip != 'no_tools' or e['body']['role'] != 'G':
                members['attest/tools.txt'] = ('file', 0o644, TOOLS)
            if e['body']['revision'] == 1:
                e['body']['attested']['tools_present'] = {'source': 'inventory', 'sha256': sha(TOOLS)}
            e['body']['final_message_sha256'] = sha(FMSG)
        parts = []
        if 'ledger/LEDGER.jsonl' in members:
            base = b'' if self.fork_ledger_at == seq else self.ledger.get((s['ledger'] or {}).get('seq'), b'') \
                if s else b''
            n = base.count(b'\n') + 1
            le = {'type': 'record', 'stage': e['kind'], 'n': seq, 'ledger': RN['LEDGER_SCHEMA'], 'seq': n,
                  'previous_ledger_sha256': sha(base), 'utc': e['utc']}
            le['entry_sha256'] = RN['self_sha'](le, RN['ledger_line'])
            lb = base + RN['ledger_line'](le)
            self.ledger[seq] = lb
            members['ledger/LEDGER.jsonl'] = ('file', 0o644, lb)
            for c in (e['body'] or {}).get('commands') or []:
                if c['ledger_sha256_after'] is not None:
                    c['ledger_sha256_after'] = sha(lb)
        if e['kind'] in ('STAGE', 'FROZEN'):
            parts = self.job(e, members)
        if e['kind'] == 'FINAL':
            lf = self.ledger[s['ledger']['seq']]
            af_raw = final_pass if final_pass is not None else b'{}'
            members.update({'final': ('dir', 0o755, None), 'final/ALL_FROZEN.json': ('file', 0o644, af_raw),
                            'final/LEDGER_FINAL.jsonl': ('file', 0o644, lf)})
            parts = [('LEDGER', 1, lf), ('ALLFZ', 1, af_raw)]
            if final_pass is not None:
                af = json.loads(af_raw)
                e['body'].update(all_frozen_sha256=sha(af_raw), ledger_final_sha256=sha(lf), runs=len(af['runs']),
                                 outcomes_sha256=af['outcomes_sha256'])
        e['payload']['members'] = sorted([k, v[0], v[1], len(v[2]) if v[2] is not None else None,
                                          sha(v[2]) if v[2] is not None else None] for k, v in members.items())
        folder = series_folder(ser)
        e['parts'] = [{'name': CW.part_name(ser, seq, k, i), 'kind': k, 'k': i, 'folder': folder, 'sha256': sha(d),
                       'md5': md5(d), 'bytes': len(d)} for k, i, d in parts]
        return members, parts

    def write(self, e, members):
        tmp = os.path.join(self.root, 'tmp.tgz')
        write_tgz(tmp, [('MANIFEST.json', 'file', 0o444, 0, jbytes(e))] +
                  [(k, v[0], v[1], 0, v[2]) for k, v in sorted(members.items())])
        with open(tmp, 'rb') as f:
            data = f.read()
        os.unlink(tmp)
        return data

    def commit(self, e):
        if e['kind'] == 'FINAL':
            probe = copy.deepcopy(e)
            self.materialize(probe)
            s1 = F.apply(self.w.state, probe)
            af_raw = jbytes(AU.all_frozen_doc(s1, self.ledger[self.w.state['ledger']['seq']]))
            members, parts = self.materialize(e, final_pass=af_raw)
        else:
            members, parts = self.materialize(e)
        self.w.commit(e)
        e['state'], e['state_sha256'] = self.w.state, sha(cjson(self.w.state))
        data = self.write(e, members)
        self.data[e['seq']] = data
        t = utc_epoch(e['utc'])
        self.upload(self.rows, 'dl', e['name'], data, t + 2)
        for k, i, d in parts:
            self.upload(self.rows, 'dl', CW.part_name(self.series, e['seq'], k, i), d, t + 3)
        return e

    def step(self, label):
        for lab, th in CW.moves(self.w):
            if lab == label:
                return self.commit(th())
        raise AssertionError('no move %s; have %s' % (label, [m[0] for m in CW.moves(self.w)]))

    def play(self, *labels):
        for lab in labels:
            self.step(lab)

    def restore(self, ans=None, **kw):
        op = CW.open_role(self.w.state) if ans else None
        return self.commit(CW._restore(self.w, resolve=op, ans=ans, **kw))

    # ---------------------------------------------------------------- the maintainer tools
    def audit(self, extra_rows=(), setup_rows=None):
        d = tempfile.mkdtemp(dir=self.root, prefix='audit_')
        lp, sp, out = os.path.join(d, 'L.json'), os.path.join(d, 'S.json'), os.path.join(d, 'AUDIT.json')
        with open(lp, 'w') as f:
            json.dump(self.rows + list(extra_rows), f)
        with open(sp, 'w') as f:
            json.dump(self.srows if setup_rows is None else setup_rows, f)
        rc, _ = capture(AU.main, ['--series', self.series, '--listing', lp, '--dir', os.path.join(self.root, 'dl'),
                      '--setup-listing', sp, '--setup-dir', os.path.join(self.root, 'setup'), '--out', out])
        with open(out) as f:
            rep = json.load(f)
        rep['_rc'], rep['_path'] = rc, out
        return rep

    def assemble(self, verify=True):
        d = tempfile.mkdtemp(dir=self.root, prefix='asm_')
        out = os.path.join(d, 'ASSEMBLE.json')
        os.mkdir(os.path.join(d, 'root'))
        rc, _ = capture(AS.main, ['--series', self.series, '--dir', os.path.join(self.root, 'dl'), '--out', out,
                      '--root', os.path.join(d, 'root')] + (['--verify-frozen'] if verify else []))
        with open(out) as f:
            rep = json.load(f)
        rep['_rc'], rep['_path'] = rc, out
        return rep


def codes(rep):
    return sorted({a['code'] for a in rep['anomalies']})


def series(name, build, root=None):
    j = Journal(tempfile.mkdtemp(dir=root or WORK, prefix=name + '_'))
    build(j)
    return j


def full_series(j):
    j.play('GENESIS', *FULL, *FULL, 'NA', 'NA', 'FINAL')


def owner_checks(j, rep, verdicts, unlogged=(), sha_=None):
    doc = {'schema': 'cps.vm2-owner-checks.v1', 'series': j.series, 'outcomes_sha256': sha_ or rep['outcomes_sha256'],
           'checked_by': 'owner', 'checked_utc': '2026-11-10T00:00:00Z',
           'verdicts': [{'id': i, 'verdict': v, 'note': ''} for i, v in verdicts],
           'unlogged': [{'case': c, 'reader': r, 'conversation_utc': '2026-11-10T00:00:00Z', 'note': ''}
                        for c, r in unlogged]}
    p = tempfile.mktemp(dir=j.root, prefix='oc_')
    with open(p, 'w') as f:
        json.dump(doc, f)
    return p


def all_verdicts(rep, special=None):
    special = special or {}
    out = []
    for it in rep['owner_items']:
        v = {'OWNER_CHECK': 'NOTHING_WRITTEN_CONFIRMED', 'SUPERSEDED_WINDOW': 'NO_CONVERSATION_IN_WINDOW',
             'O52_SHEET': 'SHEET_CHECKED'}[it['kind']]
        out.append((it['id'], special.get((it['kind'], it['reader'], it['role']), v)))
    return out


def build_plan(j, rep, asm, oc_path, pool=('case01', 'case02')):
    pp = tempfile.mktemp(dir=j.root, prefix='pool_')
    with open(pp, 'w') as f:
        json.dump({'pool': list(pool)}, f)
    out = tempfile.mktemp(dir=j.root, prefix='plan_')
    ins = ['--audit', rep['_path'], '--assembled', asm['_path'], '--pool', pp, '--owner-checks', oc_path]
    rc = SC.main(['build'] + ins + ['--out', out])
    j.plan_inputs = getattr(j, 'plan_inputs', {})
    j.plan_inputs[out] = ins
    pl = None
    if os.path.exists(os.path.join(out, 'SCORE_PLAN.json')):
        with open(os.path.join(out, 'SCORE_PLAN.json')) as f:
            pl = json.load(f)
    return rc, pl, out


def capture(fn, *a):
    old, buf = sys.stdout, io.StringIO()
    sys.stdout = buf
    try:
        rc = fn(*a)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


# ====================================================================== audit
def test_audit_clean_series():
    j = series('clean', full_series)
    rep = j.audit()
    assert rep['_rc'] == 0 and rep['clean'] and not rep['anomalies'], rep['anomalies']
    assert rep['outcomes_sha256'] == rep['all_frozen_outcomes_sha256']
    assert [p['disposition'] for p in rep['outcomes']['pairs']] == ['SCORE', 'SCORE', 'NONATTEMPT', 'NONATTEMPT']
    assert [i['kind'] for i in rep['owner_items']] == ['O52_SHEET'] and rep['final_seq'] == len(j.data)
    assert rep['counts']['folded'] == len(j.data)


def test_f5_audit_planted_restore_unknown_to_final():
    """A RESTORE the FINAL never folded: a second copy of an entry name (another md5), and an entry after FINAL."""
    j = series('f5', full_series)
    k = 4
    w2 = CW.World(j.series, jobs=copy.deepcopy(JOBS2))
    w2.state = j.w.entries[k - 2]['state']
    w2.entries = j.w.entries[:k - 1]
    planted = CW._restore(w2)
    planted['kit_sha256'], planted['body']['pass'] = j.kit, dict(j.passref)
    data = j.write(dict(planted, state=w2.state, state_sha256=sha(cjson(w2.state))), {})
    extra = [j.upload([], 'dl', entry_name(j.series, k), data, CW.T0 + 10 ** 5),
             j.upload([], 'dl', entry_name(j.series, len(j.data) + 1), data, CW.T0 + 10 ** 5)]
    rep = j.audit(extra_rows=extra)
    assert rep['_rc'] == 1 and not rep['clean']
    cs = codes(rep)
    assert {'AUD_DUPLICATE_SEQ', 'AUD_UNFOLDED_ENTRY', 'AUD_AFTER_FINAL'} <= set(cs), cs
    unf = [a['name'] for a in rep['anomalies'] if a['code'] == 'AUD_UNFOLDED_ENTRY']
    assert unf == [entry_name(j.series, k)], unf
    assert rep['outcomes_sha256'] == rep['all_frozen_outcomes_sha256']      # the chain the FINAL closed is intact


def _repack(j, seq, mutate, keep_state=True):
    """Replace entry `seq` on "Drive" by a variant: the same members, its document changed by mutate(doc)."""
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(j.data[seq]), mode='r:gz') as tf:
        members = {}
        for m in tf.getmembers()[1:]:
            members[m.name] = ('dir', m.mode, None) if m.isdir() else ('file', m.mode, tf.extractfile(m).read())
    doc = copy.deepcopy(j.w.entries[seq - 1])
    mutate(doc, members)
    if not keep_state:
        doc['state_sha256'] = sha(cjson(doc['state']))
    data = j.write(doc, members)
    j.drop(doc['name'])
    j.upload(j.rows, 'dl', doc['name'], data, utc_epoch(doc['utc']) + 2)
    return data


def test_audit_planted_foreign_release_entry():
    """IMP-16 / G12: the audit's own re-fold refuses an entry with a foreign release (S5), not only the link."""
    j = series('rel', full_series)

    def m(doc, members):
        doc['release_sha256'] = sha(b'foreign release')
    _repack(j, 3, m)
    rep = j.audit()
    ci = [a for a in rep['anomalies'] if a['code'] == 'AUD_CHAIN_INVALID']
    assert ci and ci[0]['detail'] == 'RELEASE_NOT_ACCEPTED' and ci[0]['name'] == entry_name(j.series, 3), rep['anomalies']
    assert rep['_rc'] == 1 and rep['counts']['folded'] == 2


def test_audit_state_ledger_outcomes_tamper():
    j = series('tamper', full_series)

    def bad_state(doc, members):
        doc['state']['restores'] = 7
    _repack(j, 2, bad_state, keep_state=False)
    assert 'AUD_STATE_MISMATCH' in codes(j.audit())
    j2 = series('tamper2', full_series)
    n = len(j2.data)

    def bad_af(doc, members):
        af = json.loads(members['final/ALL_FROZEN.json'][2])
        af['outcomes']['pairs'][0]['disposition'] = 'EMPTY'
        members['final/ALL_FROZEN.json'] = ('file', 0o644, jbytes(af))
        doc['payload']['members'] = sorted([k, v[0], v[1], len(v[2]) if v[2] is not None else None,
                                            sha(v[2]) if v[2] is not None else None] for k, v in members.items())
    _repack(j2, n, bad_af)
    rep = j2.audit()
    assert any(a['code'] == 'AUD_OUTCOMES_DIFF' and a['detail'] == 'outcomes' for a in rep['anomalies']), rep['anomalies']
    j3 = Journal(tempfile.mkdtemp(dir=WORK, prefix='fork_'))
    j3.fork_ledger_at = 4                       # the FINISH stage (entry 3 is an AI entry, no ledger)
    full_series(j3)
    assert 'AUD_LEDGER_FORK' in codes(j3.audit())


def test_audit_names_gap_foreign_second_series_time_pass():
    """INT-09 (AUD_SECOND_QUALIFICATION_SERIES), AUD_FOREIGN_FILE, AUD_GAP, AUD_TIME_ORDER, AUD_PASS_MISSING,
    AUD_DOWNLOAD_MISMATCH and AUD_KIT (the kit missing from the setup listing)."""
    j = Journal(tempfile.mkdtemp(dir=WORK, prefix='names_'), series='Q1')
    full_series(j)
    extra = [j.upload([], 'dl', 'CPSJ_Q2_000001.tgz', b'other series', CW.T0),
             j.upload([], 'dl', 'notes.txt', b'hello', CW.T0)]
    rep = j.audit(extra_rows=extra)
    assert codes(rep) == ['AUD_FOREIGN_FILE', 'AUD_SECOND_QUALIFICATION_SERIES'], codes(rep)
    j.audit_rows = list(j.rows)
    j.drop(entry_name(j.series, 3))
    assert {'AUD_GAP'} <= set(codes(j.audit()))
    j.rows = [dict(r) for r in j.audit_rows]
    j.row(entry_name(j.series, 5))['createdTime'] = ctime(CW.T0 - 5000)
    assert 'AUD_TIME_ORDER' in codes(j.audit())
    j.rows = [dict(r) for r in j.audit_rows]
    j.row(entry_name(j.series, 2))['md5Checksum'] = md5(b'not the bytes')
    assert 'AUD_DOWNLOAD_MISMATCH' in codes(j.audit())
    j.rows = [dict(r) for r in j.audit_rows]
    rep = j.audit(setup_rows=[r for r in j.srows if not r['name'].startswith('FINGERPRINT_PASS_')])
    assert codes(rep) == ['AUD_PASS_MISSING'], codes(rep)
    rep = j.audit(setup_rows=[r for r in j.srows if not r['name'].startswith('SESSION_KIT_')])
    assert codes(rep) == ['AUD_KIT'], codes(rep)


def rebase_series(j):
    """A drill with a rebase (INT-04): the FINISH stage's first PNG part never reached Drive."""
    j.play('GENESIS', 'PREPARE_GENERATE', 'AI', 'FINISH')
    j.lost = [p['name'] for p in j.w.entries[-1]['parts']][0]
    j.step('RESTORE_REBASE')
    j.play('REBASE_SAME', 'AI', 'VISUAL_PASS', *FULL, 'NA', 'NA', 'FINAL')


def test_int04_drill_rebase_audit_clean():
    j = series('rebase', rebase_series)
    j.drop(j.lost)
    rep = j.audit()
    assert rep['_rc'] == 0 and rep['clean'], rep['anomalies']
    assert not rep['owner_review']
    sw = [i for i in rep['owner_items'] if i['kind'] == 'SUPERSEDED_WINDOW']
    assert len(sw) == 1 and sw[0]['role'] == 'V' and sw[0]['start_no'] == 1, sw


def test_audit_rebase_over_present_part_owner_review():
    """INT-05: the part a rebase declared missing is present in the listing: owner review, not an anomaly."""
    j = series('rebase_present', rebase_series)
    rep = j.audit()
    assert rep['_rc'] == 0 and rep['clean'], rep['anomalies']
    assert [x['code'] for x in rep['owner_review']] == ['AUD_REBASE_OVER_PRESENT_PART']
    assert rep['owner_review'][0]['name'] == j.lost
    ids = [i['id'] for i in rep['owner_items'] if i['kind'] == 'SUPERSEDED_WINDOW']
    assert len(ids) == 2 and rep['owner_review'][0]['item'] in ids


def test_int04_rebase_missing_part_not_declared():
    j = series('undeclared', full_series)
    lost = [p['name'] for p in j.w.entries[3]['parts']][0]
    j.drop(lost)
    rep = j.audit()
    assert codes(rep) == ['AUD_CONFIRMS', 'AUD_PART_MISSING'], codes(rep)      # entry 5 confirms the lost copy
    assert [a['name'] for a in rep['anomalies'] if a['code'] == 'AUD_PART_MISSING'] == [lost]


def kit_change_series(j, lie=False):
    """A non-config-only kit change at a RESTORE with nothing in flight (KIT-1, INT-08), with real kit zips."""
    j.play('GENESIS', *FULL)
    rel2 = b'{"release": "invented-2"}\n'
    c1 = config(j.series)
    c2 = config(j.series, accepts_release_sha256=[sha(rel2)], clock_wait_max_seconds=90)
    k2 = j.add_kit(rel2, c2, extra=b't2')
    m1, m2 = j.kit_dict(j.kit)['members'], j.kit_dict(k2)['members']
    kc = {'from_kit_sha256': j.kit, 'to_kit_sha256': k2, 'from_members': m1, 'to_members': m2, 'config_only': False,
          'config_keys_changed': sorted(k for k in c1 if c1[k] != c2[k]), 'run_in_flight': False,
          'to_accepts_release_sha256': [sha(rel2)]}
    rel = sha(rel2)
    if lie == 'members':     # still not config-only, but the body's member list is not the new kit's
        kc['to_members'] = [[p, sha(b'other') if p == 'tables/t.json' else h] for p, h in m2]
    elif lie:        # the body claims a config-only change; the zips differ in tables/t.json and RELEASE.json
        kc['to_members'] = [[p, dict(m2)['VM_HELPER_CONFIG.json'] if p == 'VM_HELPER_CONFIG.json' else h]
                            for p, h in m1]
        kc['config_only'], kc['config_keys_changed'], rel = True, ['clock_wait_max_seconds'], sha(j.release)
    j.w.reset()
    j.w.kit = k2
    e = j.w.entry('RESTORE', CW.restore_body(j.w, kit_change=kc, kit_sha256=k2), kit=k2, release=rel)
    j.commit(e)
    j.play(*FULL, 'NA', 'NA', 'FINAL')


def test_audit_kit_change_recomputed():
    j = series('kit', kit_change_series)
    rep = j.audit()
    assert rep['_rc'] == 0 and rep['clean'], rep['anomalies']
    j2 = series('kit_lie', lambda x: kit_change_series(x, lie=True))
    rep = j2.audit()
    assert 'AUD_KIT_CHANGE' in codes(rep), codes(rep)
    j3 = series('kit_members', lambda x: kit_change_series(x, lie='members'))
    rep = j3.audit()
    assert codes(rep) == ['AUD_KIT_CHANGE'], codes(rep)


# ====================================================================== assemble
def test_assemble_verify_frozen_every_run():
    """O5: assemble rebuilds every frozen run (job members + PNG parts, modes as recorded) and the ledger; the real
    runner's verify-frozen gives NEXT: DONE for each (invented non-qualification frozen folders)."""
    j = series('asm', rebase_series)
    j.drop(j.lost)
    asm = j.assemble(verify=True)
    assert asm['_rc'] == 0 and asm['clean'], asm
    assert [x['verify'] for x in asm['runs']] == ['DONE'] * 4, [x['verify'] for x in asm['runs']]
    a = [x for x in asm['runs'] if x['run'] == 'A/case01'][0]
    assert a['png_files'] == 1 and a['carrier_sha256'] == a['carrier_listed_sha256'] is not None
    p = os.path.join(a['path'], 'qa/visual_deliverable/p1.png')
    assert oct(os.lstat(p).st_mode & 0o777) == oct(0o444) and oct(os.lstat(a['path']).st_mode & 0o777) == oct(0o555)
    with open(asm['ledger']['path'], 'rb') as f:
        assert sha(f.read()) == asm['ledger']['sha256']
    rep = j.audit()
    assert asm['outcomes_sha256'] == rep['outcomes_sha256'] == asm['outcomes_check_sha256']


def test_assemble_refusals():
    j = series('asm_bad', full_series)
    part = [p['name'] for p in j.w.entries[3]['parts']][0]
    r = j.row(part)
    with open(os.path.join(j.root, 'dl', r['id'], part), 'ab') as f:
        f.write(b'x')
    asm = j.assemble()
    assert asm['_rc'] == 1 and asm['problems'] == [{'code': 'PLACE_SHA_MISMATCH', 'name': part}], asm['problems']


# ====================================================================== score_check
def scenario_owner(j):
    """case01 A: G1 superseded (NO_CONVERSATION, T43); case01 B: G1 NOTHING_WRITTEN not_available (owner check)."""
    j.play('GENESIS', 'PREPARE_GENERATE')
    j.restore({'ended': True, 'files_found': False, 'transcript': 'exported', 'outcome': 'NO_CONVERSATION',
               'list_shows_none': True})
    j.play('AI', 'FINISH', 'AI', 'VISUAL_PASS', 'PREPARE_GENERATE')
    j.restore({'ended': True, 'files_found': False, 'transcript': 'not_available', 'outcome': 'NOTHING_WRITTEN',
               'list_shows_none': True})
    j.play('INTERRUPT_IN_PLACE', 'AI', 'FINISH', 'AI', 'VISUAL_PASS', 'NA', 'NA', 'FINAL')


def owner_world(name):
    j = series(name, scenario_owner)
    rep, asm = j.audit(), j.assemble()
    assert rep['_rc'] == 0 and asm['_rc'] == 0, (rep['anomalies'], asm['problems'])
    return j, rep, asm


def test_int03_score_check_refuses_pending_owner_items():
    j, rep, asm = owner_world('pending')
    kinds = sorted(i['kind'] for i in rep['owner_items'])
    assert kinds == ['O52_SHEET', 'OWNER_CHECK', 'SUPERSEDED_WINDOW'], kinds
    v = all_verdicts(rep)
    for drop in range(len(v)):
        oc = owner_checks(j, rep, v[:drop] + v[drop + 1:])
        rc, out = capture(build_plan, j, rep, asm, oc)
        assert rc[0] == 4 and rc[1] is None and 'REFUSED OWNER_CHECKS_INCOMPLETE' in out, out
        assert not os.listdir(rc[2]) if os.path.exists(rc[2]) else True
    (rc, pl, _), _ = capture(build_plan, j, rep, asm, owner_checks(j, rep, v))
    assert rc == 0 and pl['readers']['A']['case01']['disposition'] == 'SCORE'
    assert pl['readers']['B']['case01']['disposition'] == 'SCORE' and pl['qualification_flagged'] is False


def test_owner_checks_invalid_refused():
    j, rep, asm = owner_world('invalid')
    v = all_verdicts(rep)
    bad = [owner_checks(j, rep, v + [('ffffffffffff', 'SHEET_CHECKED')]),            # unknown id
           owner_checks(j, rep, v + v[:1]),                                         # duplicate id
           owner_checks(j, rep, [(i, 'WRITE_FOUND' if k == 'O52_SHEET' else x)      # verdict not allowed
                                 for (i, x), k in zip(v, [it['kind'] for it in rep['owner_items']])]),
           owner_checks(j, rep, v, sha_=sha(b'other outcomes'))]                    # another outcomes sha
    for p in bad:
        (rc, pl, _), out = capture(build_plan, j, rep, asm, p)
        assert rc == 4 and pl is None and 'REFUSED OWNER_CHECKS_INVALID' in out, out


def test_int03_write_found_and_window_conversation_make_pairs_empty():
    j, rep, asm = owner_world('verdicts')
    v = all_verdicts(rep, {('OWNER_CHECK', 'B', 'G'): 'WRITE_FOUND',
                           ('SUPERSEDED_WINDOW', 'A', 'G'): 'CONVERSATION_FOUND'})
    (rc, pl, out), _ = capture(build_plan, j, rep, asm, owner_checks(j, rep, v))
    assert rc == 0
    a, b = pl['readers']['A']['case01'], pl['readers']['B']['case01']
    assert (a['disposition'], a['reason']) == ('EMPTY', 'SUPERSEDED_WINDOW_CONVERSATION'), a
    assert (b['disposition'], b['reason']) == ('EMPTY', 'OWNER_CHECK_FAILED'), b
    for row in (a, b):
        with open(row['carrier_path'], 'rb') as f:
            doc = json.loads(f.read())
        assert doc['items'] == [] and doc['cps_failed_run']['reason'] == row['reason']
        assert sha(open(row['carrier_path'], 'rb').read()) == row['carrier_sha256']


def test_int03_unlogged_conversation_empty_and_flagged():
    j, rep, asm = owner_world('unlogged')
    (rc, pl, _), _ = capture(build_plan, j, rep, asm, owner_checks(j, rep, all_verdicts(rep), [('case01', 'A')]))
    assert rc == 0 and pl['qualification_flagged'] is True
    a = pl['readers']['A']['case01']
    assert (a['disposition'], a['reason']) == ('EMPTY', 'UNLOGGED_CONVERSATION')
    na = pl['readers']['A']['case02']
    assert na['disposition'] == 'NONATTEMPT' and na['also'] == [], na


def test_audit_owner_review_needs_verdict_in_score_check():
    """§10.1: an AUD_REBASE_OVER_PRESENT_PART item is a SUPERSEDED_WINDOW owner item score_check requires."""
    j = series('review_sc', rebase_series)
    rep, asm = j.audit(), j.assemble()
    extra = rep['owner_review'][0]['item']
    v = all_verdicts(rep)
    (rc, pl, _), out = capture(build_plan, j, rep, asm, owner_checks(j, rep, [x for x in v if x[0] != extra]))
    assert rc == 4 and extra in out, out
    v2 = [(i, 'CONVERSATION_FOUND' if i == extra else x) for i, x in v]
    (rc, pl, _), _ = capture(build_plan, j, rep, asm, owner_checks(j, rep, v2))
    assert rc == 0 and pl['readers']['A']['case01']['visual'] == 'FAILED_BY_RESET', pl['readers']['A']['case01']


def manifest(pl, swap=None):
    m = {'pool': pl['pool'], 'readers': {rd: {c: {'path': 'x', 'sha256': '0' * 64, 'carrier_sha256': r['carrier_sha256']}
                                              for c, r in pl['readers'][rd].items()} for rd in 'AB'}}
    if swap:
        swap(m)
    return m


def check(j, plan_dir, m, ins=None):
    mp, out = tempfile.mktemp(dir=j.root), tempfile.mktemp(dir=j.root)
    with open(mp, 'w') as f:
        json.dump(m, f)
    rc, txt = capture(SC.main, ['check', '--plan', os.path.join(plan_dir, 'SCORE_PLAN.json'), '--manifest', mp,
                                '--out', out] + (ins or j.plan_inputs[plan_dir]))
    if not os.path.exists(out):
        return rc, txt
    with open(out) as f:
        return rc, json.load(f)


def test_flags2_empty_carriers_distinct_per_reader():
    j = series('flags2', full_series)
    rep, asm = j.audit(), j.assemble()
    (rc, pl, d), _ = capture(build_plan, j, rep, asm, owner_checks(j, rep, all_verdicts(rep)))
    assert rc == 0
    a, b = pl['readers']['A']['case02'], pl['readers']['B']['case02']
    assert a['disposition'] == b['disposition'] == 'NONATTEMPT'
    assert a['carrier_sha256'] != b['carrier_sha256'] and a['carrier_path'] != b['carrier_path']
    for rd, row in (('A', a), ('B', b)):
        doc = json.loads(open(row['carrier_path'], 'rb').read())
        assert doc['items'] == [] and doc['cps_failed_run']['reader'] == rd
        assert doc['cps_failed_run']['schema'] == 'cps.vm2-failed-run.v1'
    rc, chk = check(j, d, manifest(pl))
    assert rc == 0 and chk['verdict'] == 'CONSISTENT', chk


def test_flags1_wrong_shared_or_real_carrier_inconsistent():
    j = series('flags1', full_series)
    rep, asm = j.audit(), j.assemble()
    (rc, pl, d), _ = capture(build_plan, j, rep, asm, owner_checks(j, rep, all_verdicts(rep)))
    real = pl['readers']['A']['case01']['carrier_sha256']

    def wrong(m):
        m['readers']['A']['case01']['carrier_sha256'] = sha(b'wrong')

    def shared(m):
        m['readers']['B']['case01']['carrier_sha256'] = real

    def real_for_empty(m):
        m['readers']['A']['case02']['carrier_sha256'] = real

    def missing(m):
        del m['readers']['B']['case02']
    for f in (wrong, shared, real_for_empty, missing):
        rc, chk = check(j, d, manifest(pl, f))
        assert rc == 1 and chk['verdict'] == 'INCONSISTENT', (f.__name__, chk)


def scenario_flags3(j):
    """A stops before convert, its restart stops too: EMPTY TECHNICAL_STOP_AFTER_RESTART (D7), no carrier."""
    j.play('GENESIS', 'PREPARE_GENERATE', 'AI', 'FINISH_STOP', 'ACK', 'PREPARE_GENERATE', 'AI', 'FINISH_STOP', 'ACK',
           *FULL, 'NA', 'NA', 'FINAL')


def test_flags3_runner_failed_runs_get_empty_carriers():
    j = series('flags3', scenario_flags3)
    rep, asm = j.audit(), j.assemble()
    assert rep['_rc'] == 0 and asm['_rc'] == 0, (rep['anomalies'], asm['problems'])
    (rc, pl, d), _ = capture(build_plan, j, rep, asm, owner_checks(j, rep, all_verdicts(rep)))
    a = pl['readers']['A']['case01']
    assert rc == 0 and (a['disposition'], a['reason']) == ('EMPTY', 'TECHNICAL_STOP_AFTER_RESTART'), a
    doc = json.loads(open(a['carrier_path'], 'rb').read())
    assert doc['items'] == [] and doc['cps_failed_run']['job_dir'].endswith('/qual/A_restart1/case01')


def test_score_check_refuses_unclean_inputs():
    j = series('unclean', full_series)
    rep, asm = j.audit(), j.assemble()
    oc = owner_checks(j, rep, all_verdicts(rep))
    car = os.path.join([x for x in asm['runs'] if x['run'] == 'A/case01'][0]['path'], 'carrier/convert/carrier.json')
    os.chmod(os.path.dirname(car), 0o755)
    os.chmod(car, 0o644)
    with open(car, 'ab') as f:
        f.write(b' ')
    (rc, pl, _), out = capture(build_plan, j, rep, asm, oc)
    assert rc == 4 and 'REFUSED CARRIER_MISMATCH' in out, out
    j.drop(entry_name(j.series, 3))
    rep2 = j.audit()
    (rc, pl, _), out = capture(build_plan, j, rep2, asm, oc)
    assert rc == 4 and 'REFUSED AUDIT_NOT_CLEAN' in out, out
    (rc, pl, _), out = capture(build_plan, j, rep, asm, oc, ('case01', 'nosuchcase'))
    assert rc == 4 and 'REFUSED' in out, out


# ====================================================================== delta v2.1 (track M)
def members_of(members):
    return sorted([k, v[0], v[1], len(v[2]) if v[2] is not None else None, sha(v[2]) if v[2] is not None else None]
                  for k, v in members.items())


def commit_outside(j, e):
    """Upload entry e as the Dot would, built outside core_world.commit (whose fold would refuse it); its state is the
    fold's when the fold accepts it (2015773), else the state before it."""
    members, parts = j.materialize(e)
    try:
        st = F.apply(j.w.state, e)
    except F.ChainInvalid:
        st = j.w.state
    e['state'], e['state_sha256'] = st, sha(cjson(st))
    t = utc_epoch(e['utc'])
    j.upload(j.rows, 'dl', e['name'], j.write(e, members), t + 2)
    for k, i, d in parts:
        j.upload(j.rows, 'dl', CW.part_name(j.series, e['seq'], k, i), d, t + 3)
    return e['name']


def move(j, label, run=None):
    for lab, th in CW.moves(j.w):
        if lab == label:
            e = th()
            if run is None or e['body']['run'] == run:
                return e
    raise AssertionError('no move %s %s' % (label, run))


def forge_final(j, edit):
    """MAINT-1: only the FINAL entry is rebuilt, with an edited final/ALL_FROZEN.json and a matching body."""
    def m(doc, members):
        af = json.loads(members['final/ALL_FROZEN.json'][2])
        edit(af)
        raw = jbytes(af)
        members['final/ALL_FROZEN.json'] = ('file', 0o644, raw)
        doc['body']['all_frozen_sha256'] = sha(raw)
        doc['payload']['members'] = members_of(members)
    old = j.row(entry_name(j.series, len(j.data)))['id']
    _repack(j, len(j.data), m)
    shutil.rmtree(os.path.join(j.root, 'dl', old))            # assemble reads the downloads folder, not the listing


def assemble_into(j, root, dl=None):
    out = tempfile.mktemp(dir=j.root, prefix='asm_')
    rc, txt = capture(AS.main, ['--series', j.series, '--dir', dl or os.path.join(j.root, 'dl'), '--out', out] +
                      (['--root', root] if root is not None else []))
    if not os.path.exists(out):
        return rc, None, txt
    with open(out) as f:
        return rc, json.load(f), txt


def empty_root(j):
    return tempfile.mkdtemp(dir=j.root, prefix='root_')


def test_maint1_audit_refuses_hostile_new_run():
    """D7: an entry that starts a run (rows T10-T13) at a job_dir other than the layout path is T14 in the audit."""
    b, stop = CW.BASE, ('PREPARE_GENERATE', 'AI', 'FINISH_STOP', 'ACK')
    cases = [('E1', ('INPUTS',), 'PREPARE_E', None, '/root/.config/git'),                      # T13, everyday
             ('D1', stop, 'PREPARE_GENERATE', 'A-restart1/case01', b + '/qual/A/case01'),     # T11, restart
             ((), 'PREPARE_GENERATE', 'A/case01', '/root/.config/git'),
             ((), 'PREPARE_GENERATE', 'A/case01', b + '/qual/A/../../x'),
             ((), 'PREPARE_GENERATE', 'A/case01', b + '/qual/B/case01'),
             ((), 'PREPARE_GENERATE', 'A/case01', b + '/ledger'),
             ((), 'NA', 'NA-A/case02', '/root/.config/git'),
             (tuple(FULL), 'PREPARE_GENERATE', 'B/case01', b + '/qual/A/case01')]
    for c in cases:
        ser, pre, label, run, jd = c if len(c) == 5 else ('D1',) + c
        j = Journal(tempfile.mkdtemp(dir=WORK, prefix='hostile_'), series=ser)
        j.play('GENESIS', *pre)
        e = move(j, label, run)
        old = e['body']['new_run']['job_dir']
        e['body']['new_run']['job_dir'] = jd
        for k in ('prompt', 'folder', 'output'):
            if e['body']['start']:
                e['body']['start'][k] = jd + e['body']['start'][k][len(old):]
        name = commit_outside(j, e)
        rep = j.audit()
        assert {'code': 'AUD_CHAIN_INVALID', 'name': name, 'detail': 'T14'} in rep['anomalies'], (jd, rep['anomalies'])


def test_maint1_forged_all_frozen_job_dir():
    j = series('forged', full_series)

    def edit(af):
        af['runs'][0]['job_dir'] = '/root/.config/git'
    forge_final(j, edit)
    rep = j.audit()
    assert 'AUD_OUTCOMES_DIFF' in codes(rep), rep['anomalies']
    root = empty_root(j)
    rc, asm, _ = assemble_into(j, root)
    assert rc == 1 and asm['problems'] == [{'code': 'LAYOUT_PATH', 'name': '/root/.config/git'}], asm['problems']
    assert os.listdir(root) == []


def test_maint1_assemble_base_from_genesis():
    """W93: an ALL_FROZEN whose genesis base (and every path) is another base than the GENESIS entry's."""
    j = series('base', full_series)
    other = '/home/agent/other'

    def edit(af):
        af['genesis']['base'] = other
        for r in af['runs']:
            r['job_dir'] = other + r['job_dir'][len(CW.BASE):]
    forge_final(j, edit)
    root = empty_root(j)
    rc, asm, _ = assemble_into(j, root)
    assert rc == 1 and asm['problems'] == [{'code': 'LAYOUT_PATH', 'name': 'genesis'}], asm['problems']
    assert os.listdir(root) == []


def test_maint1_wrong_mapping_refused():
    j = series('mapping', full_series)
    for bad in (CW.BASE + '/qual/B/case01', CW.BASE + '/ledger', CW.BASE + '/qual/nonattempts_A/case02'):
        def edit(af, bad=bad):
            [r for r in af['runs'] if r['run'] == 'A/case01'][0]['job_dir'] = bad
        forge_final(j, edit)
        root = empty_root(j)
        rc, asm, _ = assemble_into(j, root)
        assert rc == 1 and asm['problems'] == [{'code': 'LAYOUT_PATH', 'name': bad}], (bad, asm['problems'])
        assert os.listdir(root) == []


def test_maint1_self_consistent_hostile_base_confined():
    """A series whose base is /root/.config, every path consistent with it: the fold and the audit accept it, and
    assemble writes only under realpath(root); nothing outside changes."""
    old, CW.BASE = CW.BASE, '/root/.config'
    try:
        j = series('selfbase', full_series)
    finally:
        CW.BASE = old
    sent = os.path.join(j.root, 'sentinel')
    os.makedirs(os.path.join(sent, 'qual'))
    with open(os.path.join(sent, 'qual', 'keep.txt'), 'wb') as f:
        f.write(b'invented sentinel\n')
    before, outside = AS.walk(sent), os.path.lexists('/root/.config/qual')
    rep = j.audit()
    assert rep['_rc'] == 0 and rep['clean'], rep['anomalies']
    root = empty_root(j)
    rc, asm, _ = assemble_into(j, root)
    real = os.path.realpath(root) + '/'
    assert rc == 0 and asm['clean'] and asm['root'] == root, asm['problems']
    assert all(x['path'].startswith(real + 'root/.config/') for x in asm['runs']) and asm['ledger']['path'].startswith(real)
    assert AS.walk(sent) == before and os.path.lexists('/root/.config/qual') == outside


def test_maint1_symlink_after_begin_refused():
    """A link planted between Staging.begin and the first write (the stage folder now points outside)."""
    j = series('link', full_series)
    sent = os.path.join(j.root, 'sentinel')
    os.mkdir(sent)
    with open(os.path.join(sent, 'keep.txt'), 'wb') as f:
        f.write(b'invented sentinel\n')
    before = AS.walk(sent)

    class Hook(AS.Staging):
        def begin(self, mode):
            r = super().begin(mode)
            os.rmdir(self.stage)
            os.symlink(sent, self.stage)
            return r
    keep, AS.Staging = AS.Staging, Hook
    try:
        rc, asm, _ = assemble_into(j, empty_root(j))
    finally:
        AS.Staging = keep
    assert rc == 1 and [p['code'] for p in asm['problems']] == ['LAYOUT_PATH'], asm['problems']
    assert AS.walk(sent) == before


def test_maint1_assemble_root_required_empty_dedicated():
    """No --root, '/', a relative or missing path, a non-empty root (also one holding only a link): ROOT_INVALID and
    nothing written. The downloads folder is empty, so no variant could write anything."""
    j = Journal(tempfile.mkdtemp(dir=WORK, prefix='root_'))
    dl = tempfile.mkdtemp(dir=j.root, prefix='dl_')
    full, link = empty_root(j), empty_root(j)
    with open(os.path.join(full, 'x'), 'wb') as f:
        f.write(b'x')
    os.symlink(full, os.path.join(link, 'l'))
    for root in (None, '/', 'relative/root', os.path.join(j.root, 'missing'), full, link):
        rc, asm, txt = assemble_into(j, root, dl)
        assert rc == 2 and asm is None and 'REFUSED ROOT_INVALID' in txt, (root, rc, txt)
    rc, asm, _ = assemble_into(j, empty_root(j), dl)
    assert rc == 1 and asm['problems'] == [{'code': 'CHAIN_INVALID', 'name': j.series}]          # the control


def slipped(name, slip, build=full_series):
    j = Journal(tempfile.mkdtemp(dir=WORK, prefix=name + '_'))
    j.slip = slip
    build(j)
    return j


def frozen_with_g(j):
    return [e['name'] for e in j.w.entries if e['kind'] == 'FROZEN' and e['body']['run'] in ('A/case01', 'B/case01')]


def test_gap10_generation_record_tied_to_g_entry():
    j = series('o63', full_series)
    rep = j.audit()
    n_ai = len([e for e in j.w.entries if e['kind'] == 'AI' and e['body']['revision'] == 1])
    assert rep['clean'] and rep['o63'] == {'checked': n_ai + 2, 'missing': []}, rep['o63']
    for slip in ('tools', 'notes', 'final', 'no_tools'):
        j = slipped('o63_' + slip, slip)
        rep = j.audit()
        want = frozen_with_g(j)
        if slip == 'no_tools':
            want = sorted(want + [e['name'] for e in j.w.entries if e['kind'] == 'AI' and e['body']['role'] == 'G'])
        assert rep['_rc'] == 0 and sorted(rep['o63']['missing']) == sorted(want), (slip, rep['o63'], want)


def test_maint2_score_check_requires_tools_attestation_and_states_isolation():
    j = series('o63sc', full_series)
    rep, asm = j.audit(), j.assemble()
    (rc, pl, _), out = capture(build_plan, j, rep, asm, owner_checks(j, rep, all_verdicts(rep)))
    assert rc == 0 and pl['isolation_statement'] == O63_REPORT and O63_REPORT in out, out
    old = dict(rep)
    del old['o63']
    p = tempfile.mktemp(dir=j.root, prefix='audit_old_')
    with open(p, 'wb') as f:
        f.write(jbytes({k: v for k, v in old.items() if not k.startswith('_')}))
    (rc, pl, _), out = capture(build_plan, j, dict(old, _path=p), asm, owner_checks(j, rep, all_verdicts(rep)))
    assert rc == 4 and pl is None and 'REFUSED O63_ATTESTATION_MISSING' in out, out
    j2 = slipped('o63sc_notes', 'notes')
    rep2, asm2 = j2.audit(), j2.assemble()
    (rc, pl, _), out = capture(build_plan, j2, rep2, asm2, owner_checks(j2, rep2, all_verdicts(rep2)))
    assert rc == 4 and pl is None and 'REFUSED O63_ATTESTATION_MISSING' in out, out
    assert all(n in out for n in frozen_with_g(j2)), out


def restore_kit(j, rel, cfg, extra=b't1', cleared=None):
    """A RESTORE that takes another real kit zip, its kit_change as the session derives it."""
    s = j.w.state
    k2 = j.add_kit(rel, cfg, extra)
    kc = S.kit_change(s, j.kit_dict(k2), j.kit_dict(s['kit_sha256']))[1]
    j.w.reset()
    j.w.kit = k2
    e = j.w.entry('RESTORE', CW.restore_body(j.w, kit_change=kc, kit_sha256=k2), kit=k2, release=sha(rel))
    e['cleared_local'] = cleared
    return j.commit(e)


def halt_clear_series(j, clear=None, same=False, **cfg):
    """A HALT, then a CLEAR with a real config-only kit whose clear is `clear` (same: the halted kit itself)."""
    j.play('GENESIS', *FULL, 'HALT')
    h = j.w.state['halt']
    clear = {'series': j.series, 'seq': h['seq'], 'code': h['code']} if clear == 'right' else clear
    k2 = j.kit if same else j.add_kit(j.release, config(j.series, j.w.gates, clear=clear, **cfg))
    kc = S.kit_change(j.w.state, j.kit_dict(k2), j.kit_dict(j.w.state['kit_sha256']))[1]
    j.w.kit = k2
    e = j.w.entry('CLEAR', {'halt_seq': h['seq'], 'code': h['code'], 'kit_sha256': k2, 'kit_change': kc}, kit=k2)
    if same:
        return commit_outside(j, e)
    j.commit(e)
    j.play(*FULL, 'NA', 'NA', 'FINAL')
    return e['name']


def test_maint3_audit_refuses_unauthorized_clear():
    """O59 with real kit zips: only a kit whose clear names {series, halt seq, code} authorizes the CLEAR."""
    j = Journal(tempfile.mkdtemp(dir=WORK, prefix='clear_'))
    halt_clear_series(j, 'right')
    rep = j.audit()
    assert rep['_rc'] == 0 and rep['clean'] and len(rep['clears']) == 1, rep['anomalies']
    for clear, cfg in (({'series': 'D1', 'seq': 999, 'code': 'OTHER'}, {}), (None, {'clock_wait_max_seconds': 90})):
        j = Journal(tempfile.mkdtemp(dir=WORK, prefix='clear_'))
        name = halt_clear_series(j, clear, **cfg)
        rep = j.audit()
        assert rep['anomalies'] == [{'code': 'AUD_KIT_CHANGE', 'name': name, 'detail': 'clear'}], rep['anomalies']
    j = Journal(tempfile.mkdtemp(dir=WORK, prefix='clear_'))
    name = halt_clear_series(j, same=True)
    rep = j.audit()
    assert {'code': 'AUD_CHAIN_INVALID', 'name': name, 'detail': 'T60'} in rep['anomalies'], rep['anomalies']


def local_clear_series(j, seq_off=0, release=False):
    """A same-kit-lineage local clear (SD-53): a RESTORE with cleared_local, its kit's clear naming the stop."""
    j.play('GENESIS', *FULL)
    s = j.w.state
    clear = {'series': j.series, 'seq': s['seq'] + seq_off, 'code': 'SETUP_FAILED'}
    rel = release_for(CW.BASE, b'invented-2') if release else j.release
    cfg = config(j.series, j.w.gates, clear=clear, **({'accepts_release_sha256': [sha(rel)]} if release else {}))
    e = restore_kit(j, rel, cfg, cleared={'code': 'SETUP_FAILED', 'head_seq': s['seq'], 'kit_sha256': j.kit})
    j.play(*FULL, 'NA', 'NA', 'FINAL')
    return e['name']


def test_maint3_audit_checks_cleared_local():
    j = Journal(tempfile.mkdtemp(dir=WORK, prefix='local_'))
    local_clear_series(j)
    rep = j.audit()
    assert rep['_rc'] == 0 and rep['clean'] and len(rep['cleared_local']) == 1, rep['anomalies']
    for kw in ({'seq_off': 1}, {'release': True}):
        j = Journal(tempfile.mkdtemp(dir=WORK, prefix='local_'))
        name = local_clear_series(j, **kw)
        rep = j.audit()
        assert rep['anomalies'] == [{'code': 'AUD_KIT_CHANGE', 'name': name, 'detail': 'cleared_local'}], \
            (kw, rep['anomalies'])


def test_maint4_audit_only_kit_change_verdicts():
    """The three kit_change verdicts only the audit can see (§2.7), each with real kit zips."""
    rel2 = release_for(CW.BASE, b'invented-2')
    for case, want in (('gates', 'GATES_CHANGED'), ('series', 'CONFIG_CHANGE_NOT_ALLOWED'),
                       ('doc_samples', 'CONFIG_CHANGE_NOT_ALLOWED')):
        j = Journal(tempfile.mkdtemp(dir=WORK, prefix='kc_'), doc_samples=['invented-sample'])
        j.play('GENESIS', *FULL)
        g, acc = j.w.gates, {'accepts_release_sha256': [sha(rel2)], 'doc_samples': ['invented-sample']}
        cfg = {'gates': config(j.series, dict(g, p2_lag_seconds=99), **acc), 'series': config('D2', g, **acc),
               'doc_samples': config(j.series, g, doc_samples=[], clock_wait_max_seconds=90)}[case]
        name = restore_kit(j, j.release if case == 'doc_samples' else rel2, cfg)['name']
        j.play(*FULL, 'NA', 'NA', 'FINAL')
        rep = j.audit()
        assert rep['anomalies'] == [{'code': 'AUD_KIT_CHANGE', 'name': name, 'detail': want}], (case, rep['anomalies'])


def test_maint5_score_check_refuses_unverified_assembly():
    j = series('verify', full_series)
    rep = j.audit()
    oc = owner_checks(j, rep, all_verdicts(rep))
    asm = j.assemble(verify=False)
    assert asm['_rc'] == 0 and asm['verify_frozen'] is False, asm
    (rc, pl, _), out = capture(build_plan, j, rep, asm, oc)
    assert rc == 4 and pl is None and 'REFUSED ASSEMBLE_NOT_VERIFIED' in out, out
    asm = j.assemble()
    assert asm['verify_frozen'] is True and asm['clean']
    bad = {k: v for k, v in asm.items() if not k.startswith('_')}
    bad['runs'][0]['verify'] = 'EXIT_1'
    p = tempfile.mktemp(dir=j.root, prefix='asm_bad_')
    with open(p, 'wb') as f:
        f.write(jbytes(bad))
    (rc, pl, _), out = capture(build_plan, j, rep, dict(bad, _path=p), oc)
    assert rc == 4 and 'REFUSED ASSEMBLE_NOT_VERIFIED' in out, out
    (rc, pl, _), out = capture(build_plan, j, rep, asm, oc)
    assert rc == 0 and pl is not None, out


def test_maint7_drill_listing_with_folder_rows_clean():
    """A complete listing of the drill's own folder may hold folder rows (no size): skipped and counted."""
    j = series('folders', full_series)
    rows = [{'id': 'idfolder%d' % i, 'name': 'sub%d' % i, 'mimeType': FOLDER_ROW, 'createdTime': ctime(CW.T0)}
            for i in (1, 2)]
    rep = j.audit(extra_rows=rows)
    assert rep['_rc'] == 0 and rep['clean'] and rep['counts']['folders'] == 2, rep['anomalies']


def test_maint8_check_detects_edited_plan():
    j = series('plan8', full_series)
    rep, asm = j.audit(), j.assemble()
    (rc, pl, d), _ = capture(build_plan, j, rep, asm, owner_checks(j, rep, all_verdicts(rep)))
    rc, chk = check(j, d, manifest(pl))
    assert rc == 0 and chk['verdict'] == 'CONSISTENT', chk
    pp = os.path.join(d, 'SCORE_PLAN.json')
    with open(pp, 'rb') as f:
        raw = f.read()
    ed = json.loads(raw)
    ed['readers']['A']['case01']['carrier_sha256'] = sha(b'an edited carrier')
    with open(pp, 'wb') as f:
        f.write(jbytes(ed))
    rc, txt = check(j, d, manifest(ed))
    assert rc == 4 and 'REFUSED PLAN_MISMATCH' in txt, txt
    with open(pp, 'wb') as f:
        f.write(raw)
    ins = list(j.plan_inputs[d])
    i = ins.index('--pool') + 1
    p2 = tempfile.mktemp(dir=j.root, prefix='pool2_')
    with open(p2, 'w') as f:
        json.dump({'pool': ['case01', 'case02']}, f, indent=2)
    ins[i] = p2
    rc, txt = check(j, d, manifest(pl), ins)
    assert rc == 4 and 'REFUSED PLAN_MISMATCH' in txt, txt


def test_maint9_review_window_widened():
    j = Journal(tempfile.mkdtemp(dir=WORK, prefix='tol_'), gates={'p3_clock_tolerance_seconds': 120})
    rebase_series(j)
    rep = j.audit()
    it = [i for i in rep['owner_items'] if i['id'] == rep['owner_review'][0]['item']][0]
    head, restore = j.w.entries[3], j.w.entries[4]
    assert restore['kind'] == 'RESTORE' and it['window'] == [utc_minus(head['utc'], 120),
                                                            utc_minus(restore['utc'], -120)], it


def test_maint10_genesis_jobs_differ_from_kit_unclean():
    j = Journal(tempfile.mkdtemp(dir=WORK, prefix='jobs_'), kit_jobs=JOBS2 + [['case03', 3, None]])
    full_series(j)
    rep = j.audit()
    assert rep['anomalies'] == [{'code': 'AUD_KIT', 'name': entry_name(j.series, 1), 'detail': 'jobs'}], rep['anomalies']


def test_gap06_audit_lists_approvals_and_same_boot_restores():
    j = Journal(tempfile.mkdtemp(dir=WORK, prefix='appr_'))
    j.play('GENESIS', *FULL, 'RESTORE')
    e = CW._restore(j.w)                         # a same-boot RESTORE (a same-boot clear or a damaged cache)
    j.w.boot = e['boot_id'] = j.w.entries[-1]['boot_id']
    j.commit(e)
    j.play(*FULL, 'NA', 'NA', 'FINAL')
    rep = j.audit()
    want = [(x['seq'], x['kind'], x['body'].get('approval')) for x in j.w.entries if x['kind'] in ('GENESIS', 'RESTORE')]
    assert rep['clean'] and [(a['seq'], a['kind'], a['value']) for a in rep['approvals']] == want, rep
    assert len(want) == 3 and rep['same_boot_restores'] == [e['seq']], rep['same_boot_restores']


TESTS = [test_audit_clean_series, test_f5_audit_planted_restore_unknown_to_final,
         test_audit_planted_foreign_release_entry, test_audit_state_ledger_outcomes_tamper,
         test_audit_names_gap_foreign_second_series_time_pass, test_int04_drill_rebase_audit_clean,
         test_audit_rebase_over_present_part_owner_review, test_int04_rebase_missing_part_not_declared,
         test_audit_kit_change_recomputed, test_assemble_verify_frozen_every_run, test_assemble_refusals,
         test_int03_score_check_refuses_pending_owner_items, test_owner_checks_invalid_refused,
         test_int03_write_found_and_window_conversation_make_pairs_empty,
         test_int03_unlogged_conversation_empty_and_flagged, test_audit_owner_review_needs_verdict_in_score_check,
         test_flags2_empty_carriers_distinct_per_reader, test_flags1_wrong_shared_or_real_carrier_inconsistent,
         test_flags3_runner_failed_runs_get_empty_carriers, test_score_check_refuses_unclean_inputs,
         test_maint1_audit_refuses_hostile_new_run, test_maint1_forged_all_frozen_job_dir,
         test_maint1_assemble_base_from_genesis, test_maint1_wrong_mapping_refused,
         test_maint1_self_consistent_hostile_base_confined, test_maint1_symlink_after_begin_refused,
         test_maint1_assemble_root_required_empty_dedicated, test_gap10_generation_record_tied_to_g_entry,
         test_maint2_score_check_requires_tools_attestation_and_states_isolation,
         test_maint3_audit_refuses_unauthorized_clear, test_maint3_audit_checks_cleared_local,
         test_maint4_audit_only_kit_change_verdicts, test_maint5_score_check_refuses_unverified_assembly,
         test_maint7_drill_listing_with_folder_rows_clean, test_maint8_check_detects_edited_plan,
         test_maint9_review_window_widened, test_maint10_genesis_jobs_differ_from_kit_unclean,
         test_gap06_audit_lists_approvals_and_same_boot_restores]


def run(only=None, work=None):
    global WORK
    base = work or tempfile.mkdtemp(prefix='vm2_maint_')
    passed, failed = 0, []
    for fn in TESTS:
        if only and fn.__name__ not in only:
            continue
        if failed and os.environ.get('CPSVM2_FAILFAST'):     # run_tests.py --failfast (the mutation harness)
            break
        WORK = tempfile.mkdtemp(dir=base, prefix='t_')
        try:
            fn()
            passed += 1
        except Exception as x:                                            # noqa: BLE001 - the report names it
            import traceback
            failed.append({'test': fn.__name__, 'error': '%s: %s' % (type(x).__name__, str(x)[:600]),
                           'trace': traceback.format_exc()[-1500:]})
        finally:
            remove_tree(WORK)
    return {'name': 'test_maint', 'tests': passed + len(failed), 'passed': passed,
            'failed': [f['test'] for f in failed], 'detail': failed, 'counts': {}}


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    wk = [a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--work=')]
    r = run(args or None, wk[0] if wk else None)
    print(json.dumps(r, indent=1))
    sys.exit(0 if not r['failed'] else 1)
