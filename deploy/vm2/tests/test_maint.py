"""Tests of the maintainer side (§10, §9.5; §14.4 rows F5, FLAGS-1..3, INT-03, INT-04, INT-05, INT-08, INT-09,
IMP-16): audit, assemble and score_check on invented journals. A Journal drives core_world.World (the core tests'
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
from cpsvm2.core import fold as F                                        # noqa: E402
from cpsvm2.core.names import FOLDERS, cjson, entry_name, sha, utc_epoch  # noqa: E402
from cpsvm2.maint import assemble as AS, audit as AU, score_check as SC  # noqa: E402
from cpsvm2.vio.v1reuse import remove_tree, write_tar_stream, write_tgz  # noqa: E402

RN = AU.load_runner()
JOBS2 = [['case01', 1, None], ['case02', 2, 'NONATTEMPT_SOURCE_UNAVAILABLE']]
FULL = ['PREPARE_GENERATE', 'AI', 'FINISH', 'AI', 'VISUAL_PASS']
WORK = None


def md5(b):
    return hashlib.md5(b).hexdigest()


def jbytes(x):
    return AU.doc_bytes(x)


def ctime(t):
    return time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(t))


def kit_zip(release, config, extra=b't1'):
    files = {'RELEASE.json': release, 'VM_HELPER_CONFIG.json': jbytes(config), 'tables/t.json': extra}
    sums = ''.join('%s  %s\n' % (sha(v), k) for k, v in sorted(files.items())).encode()
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w') as z:
        for k, v in sorted(dict(files, SHA256SUMS=sums).items()):
            z.writestr(zipfile.ZipInfo(k, (2026, 1, 1, 0, 0, 0)), v)
    return bio.getvalue()


def config(series, **kw):
    c = {'schema': 'cps.vm2-config.v1', 'series': series, 'accepted_helper_tree_sha256': [CW.TREE],
         'accepts_release_sha256': [], 'selftest_expected_tests': 1, 'clock_wait_max_seconds': 60,
         'wrap_foreground_seconds': 60, 'png_part_bytes': 1000000, 'max_entry_bytes': 1000000,
         'max_transcript_bytes': 1000, 'max_ai_output_bytes': 1000, 'conversation_re': 'conv-[A-Z0-9]+',
         'transcript_ext': 'json', 'drive_id_re': '[A-Za-z0-9_-]{20,80}', 'gates': CW.GATES, 'clear': None,
         'doc_samples': []}
    c.update(kw)
    return c


class Journal:
    """One invented series, materialized under `root`: dl/<id>/<name> (the series folder), setup/<id>/<name>."""

    def __init__(self, root, series='D1', jobs=JOBS2):
        self.root, self.series = root, series
        self.w = CW.World(series, jobs=copy.deepcopy(jobs))
        self.rows, self.srows, self.data, self.ledger, self.trees, self.pngs = [], [], {}, {}, {}, {}
        self.release = b'{"release": "invented-1"}\n'
        self.kit = self.add_kit(self.release, config(series))
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
        z = kit_zip(release, cfg, extra)
        self.upload(self.srows, 'setup', 'SESSION_KIT_%s.zip' % sha(z)[:12], z, CW.T0)
        return sha(z)

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
        folder = FOLDERS[ser[0]]
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

    def assemble(self, verify=False):
        d = tempfile.mkdtemp(dir=self.root, prefix='asm_')
        out = os.path.join(d, 'ASSEMBLE.json')
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
    rc = SC.main(['build', '--audit', rep['_path'], '--assembled', asm['_path'], '--pool', pp, '--owner-checks',
                  oc_path, '--out', out])
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
    c2 = config(j.series, accepts_release_sha256=[sha(rel2)], wrap_foreground_seconds=90)
    k2 = j.add_kit(rel2, c2, extra=b't2')
    kz = {r['name']: os.path.join(j.root, 'setup', r['id'], r['name']) for r in j.srows}
    m1 = AU.kit_info(kz['SESSION_KIT_%s.zip' % j.kit[:12]])['members']
    m2 = AU.kit_info(kz['SESSION_KIT_%s.zip' % k2[:12]])['members']
    kc = {'from_kit_sha256': j.kit, 'to_kit_sha256': k2, 'from_members': m1, 'to_members': m2, 'config_only': False,
          'config_keys_changed': sorted(k for k in c1 if c1[k] != c2[k]), 'run_in_flight': False,
          'to_accepts_release_sha256': [sha(rel2)]}
    rel = sha(rel2)
    if lie == 'members':     # still not config-only, but the body's member list is not the new kit's
        kc['to_members'] = [[p, sha(b'other') if p == 'tables/t.json' else h] for p, h in m2]
    elif lie:        # the body claims a config-only change; the zips differ in tables/t.json and RELEASE.json
        kc['to_members'] = [[p, dict(m2)['VM_HELPER_CONFIG.json'] if p == 'VM_HELPER_CONFIG.json' else h]
                            for p, h in m1]
        kc['config_only'], kc['config_keys_changed'], rel = True, ['wrap_foreground_seconds'], sha(j.release)
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
    root = tempfile.mkdtemp(dir=j.root, prefix='asm_')
    os.makedirs(os.path.join(root, 'root', 'home/agent/cps/qual/A/case01'))
    out = os.path.join(root, 'A.json')
    rc, _ = capture(AS.main, ['--series', j.series, '--dir', os.path.join(j.root, 'dl'), '--out', out,
                              '--root', os.path.join(root, 'root')])
    with open(out) as f:
        rep = json.load(f)
    assert rc == 1 and rep['problems'] == [{'code': 'PLACE_TARGET_NOT_EMPTY', 'name': '/home/agent/cps/qual/A/case01'}]
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


def check(j, plan_dir, m):
    mp, out = tempfile.mktemp(dir=j.root), tempfile.mktemp(dir=j.root)
    with open(mp, 'w') as f:
        json.dump(m, f)
    rc, _ = capture(SC.main, ['check', '--plan', os.path.join(plan_dir, 'SCORE_PLAN.json'), '--manifest', mp,
                              '--out', out])
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


TESTS = [test_audit_clean_series, test_f5_audit_planted_restore_unknown_to_final,
         test_audit_planted_foreign_release_entry, test_audit_state_ledger_outcomes_tamper,
         test_audit_names_gap_foreign_second_series_time_pass, test_int04_drill_rebase_audit_clean,
         test_audit_rebase_over_present_part_owner_review, test_int04_rebase_missing_part_not_declared,
         test_audit_kit_change_recomputed, test_assemble_verify_frozen_every_run, test_assemble_refusals,
         test_int03_score_check_refuses_pending_owner_items, test_owner_checks_invalid_refused,
         test_int03_write_found_and_window_conversation_make_pairs_empty,
         test_int03_unlogged_conversation_empty_and_flagged, test_audit_owner_review_needs_verdict_in_score_check,
         test_flags2_empty_carriers_distinct_per_reader, test_flags1_wrong_shared_or_real_carrier_inconsistent,
         test_flags3_runner_failed_runs_get_empty_carriers, test_score_check_refuses_unclean_inputs]


def run(only=None, work=None):
    global WORK
    base = work or tempfile.mkdtemp(prefix='vm2_maint_')
    passed, failed = 0, []
    for fn in TESTS:
        if only and fn.__name__ not in only:
            continue
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
