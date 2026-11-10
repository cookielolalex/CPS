"""Focused tests of the VM-side I/O layer (builder A): commit() steps of §5 (entry first, parts after, duplicates, FORK,
the bounded re-upload, md5-hidden download-back, the prefix variant, the rebase absence check, size limits), durable
writes (§2.4: short write, zero write, ENOSPC and EIO halt before anything is printed), the strict walk, snapshot,
placement and evict (§3.8, §7.6, §8.5.1, SAFE-01), runner result parsing (§7.2), and the printed-line grammar (§6.1,
L5, L9) on every block the cli prints here. A small FakeDrive/FakeDot of its own; invented data only.
Entry point: run(only=None, work=None); standalone: python3 -I -B tests/test_vio.py --work /abs/dir."""
import contextlib
import errno
import hashlib
import io
import json
import os
import shlex
import shutil
import stat
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
VM2 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, VM2)
import core_world as CW                                                     # noqa: E402
from cpsvm2 import cli                                                      # noqa: E402
from cpsvm2.core import names as N                                          # noqa: E402
from cpsvm2.vio import drive, durable, host, place, runner, savepoint       # noqa: E402
from cpsvm2.vio.v1compat import Halt                                        # noqa: E402
from cpsvm2.vio.v1mod import tree_list                                      # noqa: E402
from cpsvm2.vio.v1reuse import Archive, Layout                              # noqa: E402

WORK = None
BOOT = '0f0e0d0c-0b0a-4908-8706-050403020100'
GATES = {'p1_vm_files': 'PASS', 'p1_transcript_export': 'yes', 'p1_conversation_list': 'yes',
         'p1_end_after_reset': 'yes', 'p2_exact_search': 'PASS', 'p2_md5_visible': 'yes', 'p2_newest_first': 'no',
         'p2_lag_seconds': 20, 'p2_max_upload_bytes': 50000000, 'p2_tgz_kept': 'PASS',
         'p2_failed_upload_can_appear': 'yes', 'p3_identity_stable': 'yes', 'p3_clock_tolerance_seconds': 300,
         'p5_foreground_hold_seconds': 1200, 'p5_setup_seconds': 130}
STAGE_MAX = {k: 600 for k in N.STAGE_KEYS}
PRINTED = []                       # every block printed by the cli in this suite (grammar lint at the end)


def md5(b):
    return hashlib.md5(b).hexdigest()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def tmpdir(tag):
    d = tempfile.mkdtemp(prefix=tag + '_', dir=WORK)
    return Path(d)


def expect_halt(code, fn, *a, **k):
    try:
        fn(*a, **k)
    except Halt as h:
        assert h.code == code, 'got %s, want %s' % (h.code, code)
        return h
    raise AssertionError('no Halt %s' % code)


# ================================================================ FakeDrive and FakeDot
class FakeDrive:
    """Folders of name -> [copies {id, bytes, md5}]; exact-name FIND (the only search, §X.5), download by id; no
    listing."""
    def __init__(self):
        self.files, self.n, self.drop, self.calls = {}, 0, set(), 0

    def upload(self, path, folder, name):
        self.calls += 1
        k = sum(1 for _ in self.uploads_of(name)) + 1
        self.log = getattr(self, 'log', []) + [name]
        if (name, k) in self.drop:
            return
        self.put(folder, name, Path(path).read_bytes())

    def uploads_of(self, name):
        return [x for x in getattr(self, 'log', []) if x == name]

    def put(self, folder, name, data):
        self.n += 1
        self.files.setdefault(folder, {}).setdefault(name, []).append(
            {'id': 'id%020d' % self.n, 'bytes': data, 'md5': md5(data)})

    def find(self, folder, name):
        self.calls += 1
        return list(self.files.get(folder, {}).get(name, []))

    def download(self, did):
        self.calls += 1
        for fo in self.files.values():
            for cs in fo.values():
                for c in cs:
                    if c['id'] == did:
                        return c['bytes']
        raise KeyError(did)


def parse_block(text):
    lines = [ln for ln in text.splitlines() if ln]
    assert drive.check_grammar(lines) is None, 'grammar: %s %s' % (drive.check_grammar(lines), lines)
    PRINTED.append(lines)
    return lines


def at_of(lines):
    return lines[0].split(' at=')[1].split(' ')[0]


def dot_do(drv, lines, hidden=False, skip_upload=False):
    """Carry out a SAVE block on the FakeDrive and return the found arguments (None when it is not an ATTEST found)."""
    folder_of = {}
    for ln in lines[1:]:
        t = shlex.split(ln)
        if t[0] == 'UPLOAD' and not skip_upload:
            drv.upload(t[1], t[3], t[5])
        elif t[0] == 'FIND':
            assert t[2] == 'NAME', 'only exact-name FIND exists (X.5)'
            folder_of[t[3]] = t[1]
        elif t[0] == 'DOWNLOAD':
            Path(t[5]).parent.mkdir(parents=True, exist_ok=True)
            Path(t[5]).write_bytes(drv.download(t[3]))
    do = lines[-1]
    if ' found --at ' not in do:
        return None
    hidden = hidden or '(--file ID:SIZE' in do                  # the block names the form (§X.6.2)
    names = [w for i, w in enumerate(shlex.split(do)) if i and shlex.split(do)[i - 1] == '--name']
    args = ['--at', at_of(lines)]
    found = {}
    for n in names:
        if n in folder_of:
            found[n] = drv.find(folder_of[n], n)
        found.setdefault(n, [])
    for n, cs in found.items():
        args += ['--name', n]
        if not cs:
            args.append('--none')
        for c in cs:
            args += ['--file', '%s:%d' % (c['id'], len(c['bytes'])) if hidden else
                     '%s:%s:%d' % (c['id'], c['md5'], len(c['bytes']))]
    return args


# ================================================================ a savepoint Env without the cli
class SPEnv:
    def __init__(self, root, gates=None, part_bytes=4096, max_entry=10 ** 8, series='Q1'):
        os.environ['CPS_VM_BASE'] = str(root / 'base')
        os.environ['HOME'] = str(root)
        self.lay = Layout()
        self.v2, self.journal = root / 'base/outbox/v2', root / 'base/outbox/journal'
        self.v2.mkdir(parents=True, exist_ok=True)
        (root / 'base/inbox').mkdir(parents=True, exist_ok=True)
        self.gates = dict(CW.GATES, **(gates or {}))
        self.cfg = {'png_part_bytes': part_bytes, 'max_entry_bytes': max_entry, 'max_upload_bytes': N.UPLOAD_CAP_BYTES}
        self.series_folder = N.series_folder(series)
        self.series = series

    def now(self):
        return '2026-11-10T00:00:00Z'


def fake_complete(entry):
    entry['confirms'], entry['prev_sha256'] = [], None
    entry['state'] = {'seq': entry['seq'], 'note': 'invented'}
    entry['state_sha256'] = N.sha(N.cjson(entry['state']))
    return entry


def sp_draft(seq=1, kind='STAGE', body=None, series='Q1'):
    return {'schema': 'cps.vm2-entry.v1', 'series': series, 'seq': seq, 'name': N.entry_name(series, seq),
            'kind': kind, 'body': body or {}, 'utc': '2026-11-10T00:00:00Z', 'boot_id': BOOT, 'uid': 0,
            'home': '/h', 'fingerprint_sha256': '0' * 64, 'helper': {'version': N.HELPER_VERSION, 'tree_sha256': '1' * 64},
            'runner_sha256': N.RUNNER_SHA256, 'kit_sha256': '2' * 64, 'release_sha256': '3' * 64,
            'cleared_local': None}


def make_job(root, pngs=3, png_size=3000):
    """An invented job folder with a VISUAL_QA manifest listing PNG pages (§3.8 png_set)."""
    jd = root / 'base/qual/A/case01'
    (jd / 'qa/visual_deliverable').mkdir(parents=True)
    (jd / 'run/A/output').mkdir(parents=True)
    (jd / 'RUN_RECORD.json').write_bytes(b'{"invented": true}\n')
    (jd / 'run/A/output/response.json').write_bytes(b'{"rows": []}\n')
    imgs = []
    for i in range(pngs):
        n = 'page_%02d.png' % i
        (jd / 'qa/visual_deliverable' / n).write_bytes(os.urandom(png_size))
        imgs.append({'file': n, 'tiles': []})
    (jd / 'qa/visual_deliverable/VISUAL_QA_MANIFEST.json').write_bytes(json.dumps({'images': imgs}).encode())
    return jd


def write_png_commit(env, jd, seq=1, body=None, kind='STAGE'):
    members, job_rows, pf, rels, tsha = place.snapshot(env.lay, str(jd))
    d = dict(sp_draft(seq, kind, body), payload_png={'files': pf, 'whole_sha256': None, 'parts_seq': seq})
    src = [{'kind': 'PNG', 'job_dir': str(jd), 'rels': rels, 'files': pf, 'run': 'A/case01'}] if pf else []
    pend, entry, whole = savepoint.write_commit(env, d, members, src, [], fake_complete)
    return pend, entry, whole, pf


def drive_pending(env, drv, pend, hidden=False, max_rounds=40):
    """The §5 loop between savepoint and a FakeDot until every file is confirmed; returns the printed (do) actions."""
    seen = []
    for _ in range(max_rounds):
        b = savepoint.block(env, pend)
        if b is None:
            return seen
        ups, finds, dls, do, names = b
        seen.append((do[0], [u[2] for u in ups], [f[2] for f in finds]))
        if do[0] == 'WAIT':
            continue
        if do[0] == 'RUN':
            for f, did, p in dls:
                Path(p).parent.mkdir(parents=True, exist_ok=True)
                Path(p).write_bytes(drv.download(did))
            r = savepoint.on_verify(env, pend)
            assert r[0] == 'ok', r
            continue
        for p, f, n in ups:
            drv.upload(p, f, n)
        got = {}
        for f, how, v in finds:
            cs = drv.find(f, v)
            got[v] = ['%s:%d' % (c['id'], len(c['bytes'])) if hidden else '%s:%s:%d' % (
                c['id'], c['md5'], len(c['bytes'])) for c in cs] or None
        for n in names:
            got.setdefault(n, None)
        r = savepoint.on_found(env, pend, got, lambda v: None)
        if r[0] != 'ok':
            return seen + [r]
    raise AssertionError('commit loop did not end')


# ================================================================ commit() (§5)
def t_commit_entry_then_parts():
    root = tmpdir('commit')
    env, drv = SPEnv(root), FakeDrive()
    jd = make_job(root)
    pend, entry, whole, pf = write_png_commit(env, jd)
    assert pend['phase'] == 'ENTRY' and len(pend['parts']) >= 2, pend['parts']
    assert all(os.path.isfile(p['path']) for p in pend['parts']) and os.path.isfile(pend['entry']['path'])
    assert os.path.isfile(env.v2 / 'PENDING.json')
    for p, ep in zip(pend['parts'], entry['parts']):
        b = Path(p['path']).read_bytes()
        assert (sha(b), md5(b), len(b)) == (ep['sha256'], ep['md5'], ep['bytes'])
    stream = b''.join(Path(p['path']).read_bytes() for p in pend['parts'])
    assert sha(stream) == whole
    sp = root / 'stream.tar'
    sp.write_bytes(stream)
    a = Archive(sp, ('MANIFEST.json', 'job'), gz=False)
    assert sorted(m.name for m in a.members if m.isfile()) == sorted(['MANIFEST.json'] + [f[0] for f in pf])
    a.close()
    b = savepoint.block(env, pend)
    ups, finds, dls, do, names = b
    assert [u[2] for u in ups] == [entry['name']] and names == [entry['name']], 'the entry alone first'
    assert pend['tries'][entry['name']]['uploads'] == 1
    for p, f, n in ups:
        drv.upload(p, f, n)
    c = drv.find(env.series_folder, entry['name'])
    got = {entry['name']: ['%s:%s:%d' % (x['id'], x['md5'], len(x['bytes'])) for x in c]}
    assert savepoint.on_found(env, pend, got, lambda v: None) == ('ok', None)
    ups, finds, dls, do, names = savepoint.block(env, pend)
    assert [u[2] for u in ups] == [p['name'] for p in pend['parts']], 'every part after the entry, in order'
    assert names == [p['name'] for p in pend['parts']] and do[0] == 'ATTEST_FOUND'
    for p, f, n in ups[1:]:
        drv.upload(p, f, n)                                 # the first part's upload never lands
    got = {}
    for f, how, n in finds:
        got[n] = ['%s:%s:%d' % (x['id'], x['md5'], len(x['bytes'])) for x in drv.find(f, n)] or None
    assert savepoint.on_found(env, pend, got, lambda v: None)[0] == 'ok'
    ups, finds, dls, do, names = savepoint.block(env, pend)
    assert do[0] == 'WAIT' and not ups and not finds, 'one --none: wait first'
    ups, finds, dls, do, names = savepoint.block(env, pend)
    assert names == [pend['parts'][0]['name']] and not ups, 'after the wait: FIND again, no UPLOAD, only the missing part'
    assert savepoint.on_found(env, pend, {names[0]: None}, lambda v: None) == ('ok', None)
    rest = drive_pending(env, drv, pend)
    assert rest and rest[0][1] == [pend['parts'][0]['name']], 're-upload of the missing part only'
    cache = {'marks': {'OPEN:x': 'utc'}}
    st = savepoint.finish(env, cache, pend)
    assert not os.path.exists(env.v2 / 'PENDING.json') and st['head']['seq'] == 1 and st['marks'] == cache['marks']
    assert [c['name'] for c in st['confirms']] == [entry['name']] + [p['name'] for p in entry['parts']]
    assert st['post'][-1][0] == 'DROP_LOCAL'


def t_commit_duplicates_same_md5_kept():
    root = tmpdir('dup')
    env, drv = SPEnv(root), FakeDrive()
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0))
    ups, finds, dls, do, names = savepoint.block(env, pend)
    for p, f, n in ups:
        drv.upload(p, f, n)
        drv.upload(p, f, n)                                 # the same bytes twice
    cs = drv.find(env.series_folder, entry['name'])
    assert len(cs) == 2
    got = {entry['name']: ['%s:%s:%d' % (c['id'], c['md5'], len(c['bytes'])) for c in cs]}
    assert savepoint.on_found(env, pend, got, lambda v: None) == ('ok', None)
    assert savepoint.block(env, pend) is None
    st = savepoint.finish(env, {}, pend)
    assert [c['id'] for c in st['confirms'][0]['copies']] == [c['id'] for c in cs], 'every id is kept'


def t_commit_fork_foreign_md5():
    root = tmpdir('fork')
    env, drv = SPEnv(root), FakeDrive()
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0))
    drv.put(env.series_folder, entry['name'], b'another commit with the same name')
    r = drive_pending(env, drv, pend)
    assert r[-1] == ('stop', 'FORK'), r
    size_only = {entry['name']: ['%s:%s:%d' % ('id%020d' % 99, pend['entry']['md5'], pend['entry']['bytes'] + 1)]}
    assert savepoint.on_found(env, pend, size_only, lambda v: None) == ('stop', 'FORK'), 'a size difference is a fork'


def t_commit_bounded_reupload():
    root = tmpdir('upfail')
    env, drv = SPEnv(root), FakeDrive()
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0))
    drv.drop = {(entry['name'], k) for k in (1, 2, 3)}
    r = drive_pending(env, drv, pend)
    assert r[-1] == ('stop', 'UPLOAD_FAILED'), r
    acts = [x[0] for x in r[:-1]]
    assert acts.count('WAIT') == 3 and sum(1 for x in r[:-1] if x[1]) == 3, r
    assert pend['tries'][entry['name']]['uploads'] == 3


def t_commit_late_appearing_copy_is_harmless():
    root = tmpdir('late')
    env, drv = SPEnv(root), FakeDrive()
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0))
    drv.drop = {(entry['name'], 1)}
    r = drive_pending(env, drv, pend)
    assert r[-1][0] == 'ATTEST_FOUND' and savepoint.block(env, pend) is None
    drv.put(env.series_folder, entry['name'], Path(pend['entry']['path']).read_bytes())
    assert len(drv.find(env.series_folder, entry['name'])) == 2


def t_commit_md5_hidden_download_back():
    root = tmpdir('hidden')
    env, drv = SPEnv(root, gates={'p2_md5_visible': 'no'}), FakeDrive()
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0))
    ups, finds, dls, do, names = savepoint.block(env, pend)
    assert do[1]['md5_hidden'] is True
    for p, f, n in ups:
        drv.upload(p, f, n)
    cs = drv.find(env.series_folder, entry['name'])
    got = {entry['name']: ['%s:%d' % (c['id'], len(c['bytes'])) for c in cs]}
    assert savepoint.on_found(env, pend, got, lambda v: None) == ('ok', None)
    ups, finds, dls, do, names = savepoint.block(env, pend)
    assert do[0] == 'RUN' and len(dls) == 1 and pend['phase'] == 'VERIFY'
    assert savepoint.on_verify(env, pend) == ('refused', 'DOWNLOAD_MISSING')
    Path(dls[0][2]).parent.mkdir(parents=True, exist_ok=True)
    good = Path(pend['entry']['path']).read_bytes()
    Path(dls[0][2]).write_bytes(good[:-1] + bytes([good[-1] ^ 1]))       # same size, other bytes
    pend2 = json.loads(json.dumps(pend))
    assert savepoint.on_verify(env, pend) == ('stop', 'FORK')
    assert not os.path.exists(dls[0][2]), 'downloads are deleted after the comparison'
    Path(dls[0][2]).write_bytes(good)
    assert savepoint.on_verify(env, pend2) == ('ok', None)
    assert pend2['entry']['copies'] == [[cs[0]['id'], pend['entry']['md5'], len(good)]], 'local md5 recorded'


def t_commit_refused_upload_find_before_reupload():
    """§X.5.6: --refused with --none stops with UPLOAD_REFUSED HANDBACK A (PENDING written); the next block FINDs and
    never UPLOADs; two absences then re-upload; a third refused upload's two absences are UPLOAD_FAILED; --refused
    with copies only counts. setup files over max_upload_bytes are UPLOAD_TOO_LARGE before printing (§X.3)."""
    root = tmpdir('refused')
    env, drv = SPEnv(root), FakeDrive()
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0))
    n = entry['name']
    for k in range(1, 4):
        ups, finds, dls, do, names = savepoint.block(env, pend)
        assert [u[2] for u in ups] == [n] and do[1]['uploaded'] == [n], (k, ups)
        r = savepoint.on_found(env, pend, {n: None}, lambda v: None, {n})
        assert r == ('handback', 'UPLOAD_REFUSED') and pend['tries'][n]['refused'] == k
        ups, finds, dls, do, names = savepoint.block(env, pend)
        assert not ups and finds == ((env.series_folder, 'NAME', n),), 'FIND first after a refusal'
        r = savepoint.on_found(env, pend, {n: None}, lambda v: None)
        assert r == ('ok', None) and savepoint.block(env, pend)[3][0] == 'WAIT'
        ups, finds, dls, do, names = savepoint.block(env, pend)
        assert not ups
        r = savepoint.on_found(env, pend, {n: None}, lambda v: None)
        if k < 3:
            assert r == ('ok', None) and pend['tries'][n]['need'] == 'upload'
    assert r == ('stop', 'UPLOAD_FAILED') and pend['tries'][n]['uploads'] == 3
    root2 = tmpdir('refused2')
    env2, drv2 = SPEnv(root2), FakeDrive()
    pend2, e2, _, _ = write_png_commit(env2, make_job(root2, pngs=0))
    ups, finds, dls, do, names = savepoint.block(env2, pend2)
    for p_, f, n_ in ups:
        drv2.upload(p_, f, n_)
    cs = drv2.find(env2.series_folder, e2['name'])
    got = {e2['name']: ['%s:%s:%d' % (c['id'], c['md5'], len(c['bytes'])) for c in cs]}
    assert savepoint.on_found(env2, pend2, got, lambda v: None, {e2['name']}) == ('ok', None)
    assert pend2['entry']['copies'] and pend2['tries'][e2['name']]['refused'] == 1
    big = root2 / 'big.json'
    big.write_bytes(b'x' * 2000)
    env2.cfg = dict(env2.cfg, max_upload_bytes=1000)
    lp = savepoint.setup_loop([(big, 'CPS/setup', 'big.json')])
    expect_halt('UPLOAD_TOO_LARGE', savepoint.setup_block, env2, lp)
    at, items = drive.parse_found(['--at', 'A', '--name', 'N', '--refused', '--none'])
    assert drive.check_found(items, ['N'], False, ['N'])[0] is None
    assert drive.check_found(items, ['N'], False, [])[0] == 'FOUND_SYNTAX', '--refused only on an uploaded name'


def t_commit_rebase_absence_third_check():
    root = tmpdir('rebase')
    env, drv = SPEnv(root), FakeDrive()
    miss = 'CPSJ_Q1_000004_PNG01.part'
    body = {'rebase': {'missing_parts': [miss]}}
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0), seq=5, body=body, kind='RESTORE')
    ups, finds, dls, do, names = savepoint.block(env, pend)
    assert (env.series_folder, 'NAME', miss) in finds and miss in names
    for p, f, n in ups:
        drv.upload(p, f, n)
    drv.put(env.series_folder, miss, b'it came back')
    got = {entry['name']: ['%s:%s:%d' % (c['id'], c['md5'], len(c['bytes']))
                           for c in drv.find(env.series_folder, entry['name'])],
           miss: ['%s:%s:%d' % (c['id'], c['md5'], len(c['bytes'])) for c in drv.find(env.series_folder, miss)]}
    assert savepoint.on_found(env, pend, got, lambda v: None) == ('stop', 'REBASE_PART_APPEARED')


def t_commit_refuses_second_and_limits():
    root = tmpdir('limits')
    env = SPEnv(root)
    write_png_commit(env, make_job(root, pngs=0))
    h = expect_halt('INTERNAL_PENDING_EXISTS', write_png_commit, env, root / 'base/qual/A/case01')
    root2 = tmpdir('limits2')
    env2 = SPEnv(root2, max_entry=100)
    expect_halt('ENTRY_TOO_LARGE', write_png_commit, env2, make_job(root2, pngs=0))
    assert not os.path.exists(env2.v2 / 'PENDING.json') and not list(env2.journal.iterdir()), 'nothing left behind'
    root3 = tmpdir('limits3')
    env3 = SPEnv(root3, part_bytes=10)
    d = sp_draft(1, 'DELIVERY', {})
    expect_halt('PART_TOO_LARGE', savepoint.write_commit, env3, d, [], [{'kind': 'DELIV', 'data': b'x' * 11,
                                                                         'folder': 'P/deliveries'}], [], fake_complete)
    assert not os.path.exists(env3.v2 / 'PENDING.json')
    assert h.kind == 'STOP'


def t_commit_illegal_transition_leaves_nothing():
    root = tmpdir('illegal')
    env = SPEnv(root)

    def bad(entry):
        raise Halt('STOP', 'INTERNAL_ILLEGAL_TRANSITION', 'x')
    members, rows, pf, rels, _ = place.snapshot(env.lay, str(make_job(root)))
    d = dict(sp_draft(1), payload_png={'files': pf, 'whole_sha256': None, 'parts_seq': 1})
    expect_halt('INTERNAL_ILLEGAL_TRANSITION', savepoint.write_commit, env, d, members,
                [{'kind': 'PNG', 'job_dir': str(root / 'base/qual/A/case01'), 'rels': rels, 'files': pf,
                  'run': 'A/case01'}], [], bad)
    assert not os.path.exists(env.v2 / 'PENDING.json') and not list(env.journal.iterdir())


# ================================================================ durable writes (§2.4)
@contextlib.contextmanager
def patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


def t_durable_write_ok_and_short_write():
    d = tmpdir('durable')
    p = d / 'f.json'
    real = os.write
    with patched(durable.os, 'write', lambda fd, b: real(fd, bytes(b[:3]))):
        durable.write(p, b'0123456789' * 10, 0o640)
    assert p.read_bytes() == b'0123456789' * 10 and stat.S_IMODE(os.lstat(p).st_mode) == 0o640
    assert [x.name for x in d.iterdir()] == ['f.json'], 'no temporary file left'


def t_durable_zero_write_is_eio():
    d = tmpdir('durable0')
    p = d / 'f'
    p.write_bytes(b'old')
    with patched(durable.os, 'write', lambda fd, b: 0):
        try:
            durable.write(p, b'new bytes')
            raise AssertionError('no error')
        except durable.DurableError as e:
            assert e.errno == errno.EIO and e.code == 'WRITE_FAILED'
    assert p.read_bytes() == b'old' and [x.name for x in d.iterdir()] == ['f']


def t_durable_enospc_and_fsync_eio():
    d = tmpdir('durable1')

    def full(fd, b):
        raise OSError(errno.ENOSPC, 'No space left on device')
    with patched(durable.os, 'write', full):
        try:
            durable.write(d / 'g', b'x')
            raise AssertionError('no error')
        except durable.DurableError as e:
            assert e.code == 'DISK_FULL'

    def bad_fsync(fd):
        raise OSError(errno.EIO, 'I/O error')
    with patched(durable.os, 'fsync', bad_fsync):
        try:
            durable.write(d / 'h', b'x')
            raise AssertionError('no error')
        except durable.DurableError as e:
            assert e.code == 'WRITE_FAILED'
    assert list(d.iterdir()) == []
    expect_halt('INTERNAL_EMPTY_OUTPUT', durable.write, d / 'e', b'')


def t_durable_doc_self_hash():
    d = tmpdir('doc')
    durable.write_doc(d / 'S.json', {'schema': 'x.v1', 'a': 1})
    doc, why = durable.read_doc(d / 'S.json', 'x.v1', json.loads)
    assert why is None and doc['a'] == 1
    raw = json.loads((d / 'S.json').read_text())
    raw['a'] = 2
    (d / 'S.json').write_text(json.dumps(raw))
    assert durable.read_doc(d / 'S.json', 'x.v1', json.loads) == (None, 'self_sha256')
    assert durable.read_doc(d / 'none.json', 'x.v1', json.loads) == (None, None)


def t_commit_enospc_at_every_write():
    """SAFE-04 at each durable write of commit steps 3-4 (parts, entry seal, PENDING): a DurableError, no PENDING."""
    for target in ('PNG', 'PENDING', 'tgz'):
        root = tmpdir('enospc_' + target)
        env = SPEnv(root)
        jd = make_job(root)
        real_w, real_tgz = durable.write, savepoint.write_tgz

        def w(path, data, mode=0o644):
            if target == 'PENDING' and str(path).endswith('PENDING.json'):
                raise durable.DurableError(errno.ENOSPC)
            return real_w(path, data, mode)

        def tg(dest, members):
            raise OSError(errno.ENOSPC, 'full')
        ctx = patched(savepoint, 'write_tgz', tg) if target == 'tgz' else contextlib.nullcontext()
        pw = savepoint.PartWriter

        class FullPW(pw):
            def write(self, b):
                raise OSError(errno.ENOSPC, 'full')
        ctx2 = patched(savepoint, 'PartWriter', FullPW) if target == 'PNG' else contextlib.nullcontext()
        with patched(durable, 'write', w), ctx, ctx2:
            try:
                write_png_commit(env, jd)
                raise AssertionError('no error at ' + target)
            except durable.DurableError as e:
                assert e.code == 'DISK_FULL', target
            except OSError as e:
                assert e.errno == errno.ENOSPC, target
        assert not os.path.exists(env.v2 / 'PENDING.json'), target
        assert not [x for x in env.journal.iterdir() if not x.name.startswith('.tmp')], target


# ================================================================ strict walk, snapshot, placement, evict
def t_walk_strict_unsupported_entries():
    for kind in ('fifo', 'symlink', 'setuid', 'sticky_dir', 'backslash', 'non_utf8', 'unreadable', 'socketlike_root'):
        d = tmpdir('walk_' + kind)
        (d / 'ok.txt').write_bytes(b'ok')
        if kind == 'fifo':
            os.mkfifo(d / 'pipe')
        elif kind == 'symlink':
            os.symlink('/etc/hostname', d / 'link')
        elif kind == 'setuid':
            (d / 'x').write_bytes(b'x')
            os.chmod(d / 'x', 0o4755)
        elif kind == 'sticky_dir':
            (d / 'sub').mkdir()
            os.chmod(d / 'sub', 0o1777)
        elif kind == 'backslash':
            (d / 'a\\b').write_bytes(b'x')
        elif kind == 'non_utf8':
            fd = os.open(os.fsencode(str(d)) + b'/\xff\xfe', os.O_WRONLY | os.O_CREAT, 0o644)
            os.close(fd)
        if kind == 'unreadable':
            import cpsvm2.vio.v1mod as M

            def boom(p):
                raise PermissionError(errno.EACCES, 'denied')
            with patched(M, 'sha_file', boom):
                expect_halt('WALK_UNSUPPORTED_ENTRY', tree_list, d)
            continue
        if kind == 'socketlike_root':
            expect_halt('WALK_UNSUPPORTED_ENTRY', tree_list, d / 'ok.txt')
            continue
        h = expect_halt('WALK_UNSUPPORTED_ENTRY', tree_list, d)
        assert 'path' not in (h.detail or {}), 'the path class is named, never the path'
        assert (d / 'ok.txt').exists(), 'nothing deleted'


def t_snapshot_place_roundtrip_and_evict():
    root = tmpdir('place')
    env = SPEnv(root)
    jd = make_job(root, pngs=3, png_size=2500)
    os.chmod(jd / 'RUN_RECORD.json', 0o444)
    before = tree_list(jd)
    pend, entry, whole, pf = write_png_commit(env, jd)
    (jd / 'FROZEN.json').write_bytes(b'{"frozen": 1}\n')
    expect_halt('EVICT_MISMATCH', place.evict, env.lay, str(jd), pend['entry']['path'], sha(b'{"frozen": 1}\n'),
                'A_case01_FROZEN.json')
    assert (jd / 'FROZEN.json').exists(), 'nothing deleted on a mismatch'
    os.unlink(jd / 'FROZEN.json')
    shutil.copytree(jd, root / 'saved_job')
    shutil.rmtree(jd)
    expect_halt('PLACE_SHA_MISMATCH', place.place_job, env.lay, str(jd), pend['entry']['path'],
                {'whole_sha256': '0' * 64, 'files': pf}, [p['path'] for p in pend['parts']])
    for st in jd.parent.glob('.cps_vm_stage_*'):
        shutil.rmtree(st)
    t = place.place_job(env.lay, str(jd), pend['entry']['path'], {'whole_sha256': whole, 'files': pf},
                        [p['path'] for p in pend['parts']])
    assert tree_list(jd) == before and t == place.tree_sha(before), 'placement restores the snapshot exactly'
    expect_halt('PLACE_TARGET_NOT_EMPTY', place.place_job, env.lay, str(jd), pend['entry']['path'])


def t_evict_frozen_folder():
    root = tmpdir('evict')
    env = SPEnv(root)
    jd = make_job(root, pngs=2)
    fz = b'{"frozen": "invented"}\n'
    (jd / 'FROZEN.json').write_bytes(fz)
    pend, entry, _, _ = write_png_commit(env, jd, kind='FROZEN')
    place.evict(env.lay, str(jd), pend['entry']['path'], sha(fz), 'A_case01_FROZEN.json')
    assert not jd.exists() and (env.lay.frozen_json / 'A_case01_FROZEN.json').read_bytes() == fz
    assert not jd.parent.exists(), 'the empty jobs root is removed'


def t_evict_changed_file_and_unplace():
    root = tmpdir('evict2')
    env = SPEnv(root)
    jd = make_job(root, pngs=1)
    fz = b'{"frozen": 2}\n'
    (jd / 'FROZEN.json').write_bytes(fz)
    pend, entry, _, _ = write_png_commit(env, jd, kind='FROZEN')
    (jd / 'qa/visual_deliverable/page_00.png').write_bytes(b'changed after the snapshot')
    h = expect_halt('EVICT_MISMATCH', place.evict, env.lay, str(jd), pend['entry']['path'], sha(fz), 'x.json')
    assert h.detail['changed'] == 1 and jd.exists()
    pf = root / 'base/qual/A_restart1_probe/case01'
    pf.mkdir(parents=True)
    (pf / 'FROZEN.json').write_bytes(fz)
    (pf / 'extra').write_bytes(b'x')
    expect_halt('PLACED_FROZEN_CHANGED', place.unplace_frozen, str(pf), sha(fz))
    os.unlink(pf / 'extra')
    place.unplace_frozen(str(pf), sha(fz))
    assert not pf.exists()


# ================================================================ runner result parsing (§7.2, R2, R3)
def t_runner_parse():
    ok = runner.parse('finish', 0, ['x', json.dumps({'codes': ['A1']}), 'NEXT: VISUAL_REVIEW prompt=/p/q folder=/p'])
    assert ok['result'] == 'NEXT' and ok['next'] == 'VISUAL_REVIEW' and ok['codes'] == ['A1']
    assert ok['args'] == {'prompt': '/p/q', 'folder': '/p'}
    rf = runner.parse('finish', 4, [json.dumps({'status': 'REFUSED'}), 'REFUSED: JOB_BUSY'])
    assert (rf['result'], rf['next']) == ('REFUSED', 'JOB_BUSY')
    for code, lines in ((0, [json.dumps({}), 'NEXT: STOP_X']), (3, [json.dumps({}), 'NEXT: FREEZE']),
                        (0, ['not json', 'NEXT: FREEZE']), (0, ['NEXT: FREEZE']), (0, [json.dumps([]), 'NEXT: DONE']),
                        (4, [json.dumps({}), 'REFUSED: lower']), (0, [json.dumps({}), 'DONE'])):
        assert runner.parse('freeze', code, lines)['result'] == 'UNPARSEABLE', (code, lines)
    dl = runner.parse('deliver-check', 0, [json.dumps({}), 'NEXT: DELIVER file=/a b/T(未填).xlsx'])
    assert dl['args'] == {'file': '/a b/T(未填).xlsx'}, 'a title path is never split'
    st = runner.parse('visual-record', 3, [json.dumps({'codes': []}), 'NEXT: STOP_VISUAL_FAIL'])
    assert st['result'] == 'NEXT' and st['next'] == 'STOP_VISUAL_FAIL'


def t_runner_argv_refuses_unsafe_values():
    a = {'base': '/home/agent/cps', 'model': 'gpt-x', 'job_dir': '/home/agent/cps/qual/A/c1'}
    v = runner.argv_for('freeze', a)
    assert v == ['freeze', '--job-dir', '/home/agent/cps/qual/A/c1', '--operator-model', 'gpt-x']
    expect_halt('INTERNAL_PRINT', runner.argv_for, 'freeze', dict(a, job_dir='/home/agent/cps/a b'))
    expect_halt('INTERNAL_PRINT', runner.argv_for, 'freeze', dict(a, model='gpt x'))


# ================================================================ printed-line grammar (§6.1, L5, L9)
def t_grammar_and_quoting():
    hdr = 'CPSV series=Q1 head=000124 kit=0a1b2c3d4e5f at=000124-0007-3c9a1e mode=qualification state=SAVE'
    good = [hdr, 'UPLOAD /a/b TO CPS/qualification AS N.tgz', 'FIND CPS/qualification NAME N.tgz',
            'DO: ATTEST bash /v found --at 000124-0007-3c9a1e --name N.tgz (--file ID:MD5:SIZE ... | --none)']
    assert drive.check_grammar(good) is None
    assert drive.check_grammar(good + ['DO: RUN bash /v go']) == 'order', 'two DO lines'
    assert drive.check_grammar([hdr, 'DO: RUN bash /v go', 'FIND a NAME b']) == 'order'
    assert drive.check_grammar([hdr, 'THEN: x', 'DO: RUN x']) == 'token'
    assert drive.check_grammar([hdr, 'DO: OPEN {CONVERSATION_ID}']) == 'token'
    assert drive.check_grammar([hdr, 'DO: RUN /hé']) == 'token'
    assert drive.check_grammar([hdr.replace('head=000124', 'head=124'), 'DO: RUN x']) == 'header'
    assert drive.check_grammar([hdr, 'FIND a NAME b']) == 'order', 'no DO line'
    assert drive.check_grammar([hdr, 'REFUSED STALE_AT', 'DO: RUN bash /v go']) is None
    assert drive.q('Dots Folder/CPS_JOB_RECORDS') == "'Dots Folder/CPS_JOB_RECORDS'"
    for bad in ('/a/未.xlsx', 'a\nb', ''):
        expect_halt('INTERNAL_PRINT', drive.q, bad)
    for bad in ("it's", 'a b', '{X}', '<id>'):
        expect_halt('INTERNAL_PRINT', drive.word, bad)
    blk = type('B', (), {'uploads': (('/x/y.tgz', 'Dots Folder/CPS_JOB_RECORDS', 'CPSJ_E1_000002.tgz'),),
                         'finds': (('Dots Folder/CPS_JOB_RECORDS', 'NAME', 'CPSJ_E1_000002.tgz'),), 'lists': (),
                         'downloads': (), 'do': ('ATTEST_FOUND', {'names': ['CPSJ_E1_000002.tgz']})})()
    lines = drive.body_lines(blk, '/home/agent/cps/vm.sh')
    assert shlex.split(lines[0]) == ['UPLOAD', '/x/y.tgz', 'TO', 'Dots Folder/CPS_JOB_RECORDS', 'AS',
                                     'CPSJ_E1_000002.tgz']


def t_found_argument_rules():
    U = drive.Usage
    for bad in ([], ['--at'], ['--at', 'A', '--name'], ['--at', 'A', '--bogus'], ['--at', 'A', '--name', 'N', '--file']):
        try:
            drive.parse_found(bad)
            if len(bad) >= 3 and bad[2] == '--name' and len(bad) == 3:
                raise AssertionError('accepted')
        except U:
            pass
    at, items = drive.parse_found(['--at', 'A', '--name', 'N', '--file', 'i:m:1', '--none'])
    assert drive.check_found(items, ['N'], False)[0] == 'FOUND_FILE_AND_NONE'
    at, items = drive.parse_found(['--at', 'A', '--name', 'N'])
    assert drive.check_found(items, ['N'], False)[0] == 'FOUND_SYNTAX'
    at, items = drive.parse_found(['--at', 'A', '--name', 'N', '--none'])
    assert drive.check_found(items, ['N', 'M'], False)[0] == 'FOUND_NAMES_INCOMPLETE'
    at, items = drive.parse_found(['--at', 'A', '--file', 'n:i:m:1'])
    assert drive.check_found(items, [], True) == (None, {None: ['n:i:m:1']}, set())
    assert drive.parse_copy('i:m:1', False) == ('i', 'm', '1') and drive.parse_copy('i:1', False) is None
    assert drive.parse_copy('i:1', True) == ('i', '1') and drive.parse_copy('n:i:m:1', False, True)


def t_config_upload_and_stage_budget_invalid():
    """§X.2: stage_max_seconds has exactly the STAGE_KEYS with int values >= 1; max_upload_bytes <= UPLOAD_CAP_BYTES;
    png_part_bytes and max_entry_bytes <= max_upload_bytes; max_ai_output + max_transcript + 1e6 <= max_entry; the
    deleted keys are refused (exact key set)."""
    rel = {'status': 'RELEASED_FOR_USE'}
    base = {'schema': 'cps.vm2-config.v1', 'series': 'E1', 'accepted_helper_tree_sha256': ['a' * 64],
            'accepts_release_sha256': [], 'selftest_expected_tests': 1, 'clock_wait_max_seconds': 60,
            'foreground_hold_seconds': 1200, 'stage_max_seconds': dict(STAGE_MAX), 'max_upload_bytes': 50000000,
            'png_part_bytes': 1000000, 'max_entry_bytes': 50000000, 'max_transcript_bytes': 20000000,
            'max_ai_output_bytes': 20000000, 'conversation_re': r'conv-[0-9a-f]{8}', 'transcript_ext': 'json',
            'drive_id_re': r'[A-Za-z0-9_-]{20,80}', 'gates': dict(GATES), 'clear': None, 'doc_samples': []}

    def load(**over):
        c = dict(base, **over)
        for k in [k for k, v in over.items() if v is None and k not in ('clear',)]:
            c.pop(k)
        return host.load_config(json.dumps(c).encode(), rel, N.check_config_patterns, N.UPLOAD_CAP_BYTES,
                                N.STAGE_KEYS)
    assert load()['max_upload_bytes'] == 50000000
    sm_missing = {k: v for k, v in STAGE_MAX.items() if k != 'finish'}
    for over in ({'stage_max_seconds': sm_missing}, {'stage_max_seconds': dict(STAGE_MAX, deliver=5)},
                 {'stage_max_seconds': dict(STAGE_MAX, finish=0)}, {'stage_max_seconds': dict(STAGE_MAX, finish=True)},
                 {'max_upload_bytes': N.UPLOAD_CAP_BYTES + 1, 'max_entry_bytes': 50000000},
                 {'png_part_bytes': 60000000}, {'max_entry_bytes': 60000000},
                 {'max_ai_output_bytes': 30000000}, {'wrap_foreground_seconds': 240}, {'foreground_hold_seconds': None},
                 {'gates': dict(GATES, p5_detached='PASS')}, {'gates': dict(GATES, p2_prefix_search='no')},
                 {'gates': {k: v for k, v in GATES.items() if k != 'p3_clock_tolerance_seconds'}}):
        expect_halt('CONFIG_INVALID', load, **over)


def t_gate1_foreground_hold_gate():
    """§X.12.1 release gates: foreground_hold_seconds <= p5_foreground_hold_seconds; p5_setup_seconds + 60 and every
    stage budget + 60 within the hold; max_upload_bytes <= min(cap, p2_max_upload_bytes); parts and entries within
    max_upload_bytes; an OPEN or null gate is open."""
    cfg = {'gates': dict(GATES), 'foreground_hold_seconds': 1200, 'stage_max_seconds': dict(STAGE_MAX),
           'max_upload_bytes': 50000000, 'png_part_bytes': 1000000, 'max_entry_bytes': 50000000}
    gp = lambda c: host.gates_problem(c, 'qualification', N.UPLOAD_CAP_BYTES)          # noqa: E731
    assert gp(cfg) is None and host.gates_problem(cfg, 'setup', N.UPLOAD_CAP_BYTES) is None
    assert 'p5_foreground_hold_seconds' in gp(dict(cfg, gates=dict(GATES, p5_foreground_hold_seconds=600)))
    assert gp(dict(cfg, gates=dict(GATES, p5_foreground_hold_seconds=None))) == ['p5_foreground_hold_seconds']
    assert gp(dict(cfg, stage_max_seconds=dict(STAGE_MAX, finish=1150))) == ['stage_max_seconds.finish']
    assert gp(dict(cfg, gates=dict(GATES, p5_setup_seconds=1150))) == ['p5_setup_seconds']
    assert gp(dict(cfg, gates=dict(GATES, p2_max_upload_bytes=40000000))) == ['p2_max_upload_bytes']
    assert gp(dict(cfg, gates=dict(GATES, p3_clock_tolerance_seconds='OPEN'))) == ['p3_clock_tolerance_seconds']
    assert gp(dict(cfg, gates=dict(GATES, p2_tgz_kept='OPEN'))) == ['p2_tgz_kept']


# ================================================================ the cli on an everyday series (in-process)
class World:
    """BASE, TOOLS, HOME under a temp folder; an E1 series whose GENESIS was confirmed; the kit config in runtime."""
    def __init__(self, gates=None):
        self.root = tmpdir('cli')
        r = self.root
        os.environ.update({'HOME': str(r / 'home'), 'CPS_VM_BASE': str(r / 'home/cps'),
                           'CPS_TOOLS': str(r / 'home/cps-tools'), 'CPS_VM_BOOT_ID_PATH': str(r / 'boot_id')})
        (r / 'boot_id').write_text(BOOT + '\n')
        self.lay = Layout()
        b = self.lay.base
        for d in ('runtime', 'outbox/v2', 'everyday_inputs', 'attest', 'inbox'):
            (b / d).mkdir(parents=True, exist_ok=True)
        os.symlink(cli.Path(cli.host.HELPER_REPO), b / 'repo')
        self.gates = dict(GATES, **(gates or {}))
        rel = json.dumps({'status': 'RELEASED_FOR_USE', 'invented': True}).encode()
        cfg = {'schema': 'cps.vm2-config.v1', 'series': 'E1', 'accepted_helper_tree_sha256': [host.helper_tree_sha256()],
               'accepts_release_sha256': [], 'selftest_expected_tests': 1, 'clock_wait_max_seconds': 60,
               'foreground_hold_seconds': 1200, 'stage_max_seconds': dict(STAGE_MAX), 'max_upload_bytes': 50000000,
               'png_part_bytes': 1000000, 'max_entry_bytes': 50000000,
               'max_transcript_bytes': 20000000, 'max_ai_output_bytes': 20000000,
               'conversation_re': r'conv-[0-9a-f]{8}', 'transcript_ext': 'json', 'drive_id_re': r'[A-Za-z0-9_-]{20,80}',
               'gates': self.gates, 'clear': None, 'doc_samples': ['conv-EXAMPLE', 'case-example']}
        (self.lay.runtime / 'RELEASE.json').write_bytes(rel)
        (self.lay.runtime / 'VM_HELPER_CONFIG.json').write_bytes(json.dumps(cfg).encode())
        w = CW.World('E1', gates=self.gates)
        w.boot = BOOT
        self.cw = w
        gb = {'mode': 'everyday', 'operator': {'model': 'gpt-x', 'platform': 'chat'}, 'jobs': None, 'ledger': None,
              'layout': {'base': str(b)}, 'gates': self.gates, 'pass': {'name': 'P', 'md5': '0' * 32},
              'other_series_absent': None}
        g = w.entry('GENESIS', gb, kit='4' * 64, release=sha(rel))
        g['fingerprint_sha256'] = '5' * 64
        w.commit(g)
        st = w.state
        self.drive = FakeDrive()
        gname = N.entry_name('E1', 1)
        self.drive.put(N.FOLDERS['E'], gname, b'genesis entry bytes (invented)')
        c = self.drive.find(N.FOLDERS['E'], gname)[0]
        cache = {'schema': savepoint.STATE_SCHEMA, 'series': 'E1', 'boot_id': BOOT, 'uid': os.getuid(),
                 'home': str(r / 'home'), 'operator': {'model': 'gpt-x', 'platform': 'chat'}, 'marks': {},
                 'kit_sha256': '4' * 64, 'kit': None, 'fingerprint_sha256': '5' * 64,
                 'pass': {'name': 'P', 'md5': '0' * 32, 'size': 1}, 'gates_ok': True,
                 'head': {'seq': 1, 'name': gname, 'id': c['id'], 'md5': c['md5'], 'bytes': len(c['bytes']),
                          'sha256': sha(c['bytes'])},
                 'state': st, 'state_sha256': N.sha(N.cjson(st)), 'post': [],
                 'confirms': [{'name': gname, 'copies': [{'id': c['id'], 'md5': c['md5'], 'size': len(c['bytes'])}]}],
                 'cleared_local': None, 'written_utc': '2026-11-10T00:00:00Z'}
        self.cache = cache
        durable.write_doc(b / 'outbox/v2/STATE.json', cache)
        durable.write_doc(b / 'outbox/v2/RESTORE_WORK.json', {'schema': cli.WORK_SCHEMA, 'boot_id': BOOT,
                                                              'phase': 'DONE', 'done': []})
        self.started = []

    def advance_to_generate(self, case='case01'):
        """Fold INPUTS and a prepare STAGE that STARTs G (core_world builders) and make that the confirmed head."""
        w, tag = self.cw, 'E20261110T000000Z'
        w.commit(w.entry('INPUTS', {'tag': tag, 'case': case, 'inputs': {'job_sha256': '6' * 64}, 'request_utc':
                                    w.now()}))
        w.commit(CW._prepare(w, tag, case, 'GENERATE'))
        st, name = w.state, N.entry_name('E1', w.state['seq'])
        self.cache.update(state=st, state_sha256=N.sha(N.cjson(st)),
                          head=dict(self.cache['head'], seq=st['seq'], name=name),
                          confirms=[{'name': name, 'copies': [{'id': 'id%020d' % 77, 'md5': '7' * 32, 'size': 9}]}])
        durable.write_doc(self.lay.base / 'outbox/v2/STATE.json', self.cache)
        return tag + '/' + case

    def cmd(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patched(cli, 'run_stage', self._spawn):
            code = cli.main(list(argv))
        text = out.getvalue()
        lines = [ln for ln in text.splitlines() if ln]
        if lines and lines[0].startswith('CPSV ') and code != 2:
            parse_block(text)
        return code, lines

    def _spawn(self, env, kind, info):
        """The foreground stage replaced (§X.7.2: only `go` reaches it)."""
        assert env.command == 'go', 'X.5: %s started a stage' % env.command
        self.started.append((kind, info))
        raise cli.Out(0)

    def cache_bytes(self):
        v2 = self.lay.base / 'outbox/v2'
        return {p.name: p.read_bytes() for p in v2.iterdir() if p.is_file()}

    def inputs(self, case='case01'):
        d = self.lay.everyday_inputs / case
        d.mkdir(parents=True, exist_ok=True)
        (d / 'source.xlsx').write_bytes(b'invented workbook bytes')
        (d / 'JOB.json').write_text(json.dumps({'case_id': case, 'source_path': str(d / 'source.xlsx')}))
        (d / 'JOB_TITLE.json').write_text(json.dumps({'case_id': case, 'job_title': 'invented'}))


def t_cli_idle_reprint_and_refusals():
    w = World()
    code, a = w.cmd('go')
    assert code == 0 and a[-1].endswith('answer --at %s case=CASE_ID' % at_of(a)) and 'state=IDLE' in a[0], a
    code, b = w.cmd('go')
    assert (code, b) == (0, a), 'the same block again, the same --at'
    snap = w.cache_bytes()
    for args, want in ((['answer', '--at', '000001-0001-ffffff', 'case=case01'], 'STALE_AT'),
                       (['found', '--at', at_of(a), '--name', 'x', '--none'], 'COMMAND_NOT_EXPECTED'),
                       (['answer', '--at', at_of(a), 'case=case 01'], 'VALUE_FORBIDDEN'),
                       (['answer', '--at', at_of(a), 'case=case01\n'], 'VALUE_FORBIDDEN'),
                       (['answer', '--at', at_of(a), 'case={CASE_ID}'], 'VALUE_FORBIDDEN'),
                       (['answer', '--at', at_of(a), 'case=CASE_ID'], 'VALUE_PLACEHOLDER'),
                       (['answer', '--at', at_of(a), 'case=case-example'], 'VALUE_PLACEHOLDER'),
                       (['answer', '--at', at_of(a), 'case=１２'], 'VALUE_FORBIDDEN'),
                       (['answer', '--at', at_of(a), 'case=c1', 'case=c2'], 'ARG_DUPLICATE_KEY'),
                       (['answer', '--at', at_of(a), 'case=c1', 'x=y'], 'ARG_EXTRA_KEY'),
                       (['answer', '--at', at_of(a)], 'ARG_MISSING_KEY'),
                       (['answer', '--at', at_of(a), 'case=case01'], 'INPUTS_INVALID')):
        code, out = w.cmd(*args)
        assert code == 4 and out[1] == 'REFUSED ' + want and out[2:] == a[1:], (args, out)
        assert w.cache_bytes() == snap, 'a refusal leaves every cache file byte-identical (%s)' % want
    code, out = w.cmd('go', 'extra')
    assert code == 2


def t_cli_inputs_commit_found_and_next_stage():
    w = World()
    code, a = w.cmd('go')
    w.inputs()
    code, s = w.cmd('answer', '--at', at_of(a), 'case=case01')
    assert code == 0 and 'state=SAVE' in s[0] and s[1].startswith('UPLOAD ') and s[2].startswith('FIND ')
    assert s[-1].startswith('DO: ATTEST ') and 'INPUTS' not in '\n'.join(s), 'nothing reveals the outcome'
    code, s2 = w.cmd('go')
    assert s2 == s, 'a second go does not re-count the upload'
    pend = json.loads((w.lay.base / 'outbox/v2/PENDING.json').read_text())
    assert pend['tries']['CPSJ_E1_000002.tgz']['uploads'] == 1
    args = dot_do(w.drive, s)
    code, out = w.cmd('found', *args)
    assert code == 0 and not w.started and 'state=WORK' in out[0] and out[-1].startswith('DO: RUN '), out
    code, out2 = w.cmd('go')
    assert code == 0 and w.started and w.started[0][1]['first'] == 'prepare', (out2, w.started)
    st = json.loads((w.lay.base / 'outbox/v2/STATE.json').read_text())
    assert st['head']['seq'] == 2 and not (w.lay.base / 'outbox/v2/PENDING.json').exists()
    assert (w.lay.inbox / 'journal/CPSJ_E1_000002.tgz').is_file(), 'the confirmed entry is kept for this boot'
    assert st['state']['runs']['%s/case01' % st['state']['current'].split('/')[0]]['status'] == 'INPUTS'


def t_cli_fork_is_sticky():
    w = World()
    code, a = w.cmd('go')
    w.inputs()
    code, s = w.cmd('answer', '--at', at_of(a), 'case=case01')
    w.drive.put(N.FOLDERS['E'], 'CPSJ_E1_000002.tgz', b'a foreign commit')
    code, out = w.cmd('found', *dot_do(w.drive, s))
    assert code == 3 and out[-1] == 'DO: STOP FORK HANDBACK C', out
    code, out2 = w.cmd('go')
    assert code == 3 and out2[-1] == 'DO: STOP FORK HANDBACK C', 'a local sticky STOP'


def t_cli_upload_failed_after_three_tries():
    w = World()
    code, a = w.cmd('go')
    w.inputs()
    code, s = w.cmd('answer', '--at', at_of(a), 'case=case01')
    w.drive.drop = {('CPSJ_E1_000002.tgz', k) for k in (1, 2, 3)}
    blocks, ups = [s], 0
    for _ in range(20):
        cur = blocks[-1]
        ups += sum(1 for ln in cur if ln.startswith('UPLOAD '))
        if cur[-1].startswith('DO: WAIT'):
            code, nxt = w.cmd('go')
        elif ' found ' in cur[-1]:
            code, nxt = w.cmd('found', *dot_do(w.drive, cur))
        else:
            break
        blocks.append(nxt)
    assert blocks[-1][-1] == 'DO: STOP UPLOAD_FAILED HANDBACK C' and ups == 3, (ups, blocks[-1])


def t_cli_enospc_halts_before_printing():
    """SAFE-04: ENOSPC at the PENDING write of an answer's commit: only the STOP block is printed, no UPLOAD."""
    w = World()
    code, a = w.cmd('go')
    w.inputs()
    real = durable.write

    def full(path, data, mode=0o644):
        if str(path).endswith('PENDING.json'):
            raise durable.DurableError(errno.ENOSPC)
        return real(path, data, mode)
    with patched(durable, 'write', full):
        code, out = w.cmd('answer', '--at', at_of(a), 'case=case01')
    assert code == 3 and out[-1] == 'DO: STOP DISK_FULL HANDBACK C' and not any(x.startswith('UPLOAD') for x in out)
    assert not (w.lay.base / 'outbox/v2/PENDING.json').exists()
    assert not [p for p in (w.lay.base / 'outbox/journal').iterdir() if p.name.endswith(('.tgz', '.part'))]


def t_cli_md5_hidden_download_back():
    w = World(gates={'p2_md5_visible': 'no'})
    code, a = w.cmd('go')
    w.inputs()
    code, s = w.cmd('answer', '--at', at_of(a), 'case=case01')
    assert '(--file ID:SIZE ... | --none)' in s[-1]
    code, v = w.cmd('found', *dot_do(w.drive, s, hidden=True))
    dl = [ln for ln in v if ln.startswith('DOWNLOAD ')]
    assert code == 0 and len(dl) == 1 and v[-1].startswith('DO: RUN '), v
    code, r = w.cmd('go')
    assert code == 4 and r[1] == 'REFUSED DOWNLOAD_MISSING'
    target = shlex.split(dl[0])[5]
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_bytes(b'x' * len(w.drive.find(N.FOLDERS['E'], 'CPSJ_E1_000002.tgz')[0]['bytes']))
    code, f = w.cmd('go')
    assert code == 3 and f[-1] == 'DO: STOP FORK HANDBACK C', f


def t_cli_generator_open_export_ask_ai_commit():
    """§7.1 rows 5, 8, 9 and §7.5: one OPEN per START (the mark), the EXPORT once, the G end keys with the final
    message and transcript checks, the AI entry through the §5 loop, then the consumer chain (finish)."""
    w = World()
    run = w.advance_to_generate()
    code, o = w.cmd('go')
    assert code == 0 and o[-1].startswith('DO: OPEN_CONVERSATION role=G prompt=') and o[-1].endswith('then=when_ended')
    code, x = w.cmd('go')
    assert x[-1].startswith('DO: EXPORT_TRANSCRIPT role=G to=') and 'OPEN_CONVERSATION' not in ' '.join(x)
    tpath = x[-1].split(' to=')[1]
    code, a = w.cmd('go')
    keys = a[-1].split(' answer --at ')[1].split(' ')[1:]
    assert [k.split('=')[0] for k in keys] == list(cli.P.G_KEYS), keys
    code, a2 = w.cmd('go')
    assert a2 == a, 'no second OPEN or EXPORT: the same question again'
    st = json.loads((w.lay.base / 'outbox/v2/STATE.json').read_text())
    lt = st['state']['runs'][run]['roles']['G1']['starts'][-1]
    good = {'ended': 'yes', 'conversation': 'conv-0a1b2c3d', 'started_utc': lt['utc'], 'ended_utc': lt['utc'],
            'platform': 'chat', 'model': 'gpt-x', 'effort': 'high', 'single_user_message': 'yes', 'memory': 'no',
            'custom_instructions': 'no', 'web': 'no', 'connectors': 'no', 'file_uploads': 'no', 'other_agents': 'no',
            'tools': 'none', 'transcript': 'exported'}

    def ans(**kw):
        g = dict(good, **kw)
        return w.cmd('answer', '--at', at_of(a), *['%s=%s' % (k, g[k]) for k in cli.P.G_KEYS])
    snap = w.cache_bytes()
    for kw, want in (({}, 'FINAL_MESSAGE_INVALID'), ({'started_utc': '2001-01-01T00:00:00Z'}, 'UTC_OUT_OF_WINDOW'),
                     ({'conversation': 'conv-EXAMPLE'}, 'VALUE_PLACEHOLDER'), ({'tools': 'web,x y'}, 'VALUE_FORBIDDEN'),
                     ({'conversation': 'CONV'}, 'VALUE_PLACEHOLDER')):
        code, r = ans(**kw)
        assert code == 4 and r[1] == 'REFUSED ' + want, (kw, r[:2])
        assert w.cache_bytes() == snap
    (w.lay.base / 'attest/final_message.txt').write_text('Done: the invented response is in run/A/output.\n')
    code, r = ans()
    assert code == 4 and r[1] == 'REFUSED TRANSCRIPT_FILE_MISSING'
    (w.lay.base / 'attest/final_message.txt').write_text('see {placeholder}')
    Path(tpath).parent.mkdir(parents=True, exist_ok=True)
    Path(tpath).write_text('{"invented": "transcript"}')
    code, r = ans()
    assert code == 4 and r[1] == 'REFUSED FINAL_MESSAGE_INVALID'
    (w.lay.base / 'attest/final_message.txt').write_text('Done: the invented response is in run/A/output.\n')
    code, s_ = ans()
    assert code == 0 and 'state=SAVE' in s_[0], s_
    code, out = w.cmd('found', *dot_do(w.drive, s_))
    assert not w.started and 'state=WORK' in out[0], 'X.5: found never starts the stage'
    code, out = w.cmd('go')
    assert w.started and w.started[-1][1]['first'] == 'finish' and w.started[-1][1]['info']['consume'] == 'G1'
    st = json.loads((w.lay.base / 'outbox/v2/STATE.json').read_text())
    g1 = st['state']['runs'][run]['roles']['G1']
    assert g1['status'] == 'ARCHIVED' and g1['archives'][0]['conversation'] == 'conv-0a1b2c3d'
    ent = savepoint.read_entry(w.lay.inbox / 'journal' / st['head']['name'])
    assert ent['body']['attested']['features'] == {k: False for k in N.FEATURES}
    assert [m[0] for m in ent['payload']['members']] == ['ai', 'attest', 'attest/final_message.txt', 'transcript',
                                                         'transcript/G1_1.json']
    assert not (w.lay.base / 'attest/final_message.txt').exists(), 'DROP_ATTEST after the commit'


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        import time
        return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(self.t))


def t_cli_setup_failed_log_uploaded_then_stop():
    """§X.6.6: session_start.sh ran the setup in the foreground and wrote the failed marker for this boot and commit:
    `go` uploads the setup log to CPS/reports through the setup-file loop, then STOP SETUP_FAILED (local sticky).
    Neither marker: STOP SETUP_FAILED at once (`go` never waits for setup)."""
    for failed in (True, False):
        w = World()
        b = w.lay.base
        for f in ('outbox/v2/STATE.json', 'outbox/v2/RESTORE_WORK.json'):
            os.unlink(b / f)
        (w.lay.tools / 'var').mkdir(parents=True, exist_ok=True)
        if failed:
            (w.lay.tools / 'var/cps_vm2_setup_failed').write_text('%s %s\n' % (BOOT, host.repo_commit(w.lay)))
            (b / 'outbox/setup_20261110T000000Z.log').write_text('invented setup log: check_env all_met false\n')
        code, a = w.cmd('go')
        if failed:
            assert code == 0 and a[1].startswith('UPLOAD ') and ' TO CPS/reports AS setup_20261110T000000Z.log' in a[1]
            assert '[--refused]' in a[-1], a[-1]
            code, a = w.cmd('found', *dot_do(w.drive, a))
            assert w.drive.find('CPS/reports', 'setup_20261110T000000Z.log')
        assert code == 3 and a[-1] == 'DO: STOP SETUP_FAILED HANDBACK C', (code, a)
        code, again = w.cmd('go')
        assert code == 3 and again[-1] == a[-1], 'the STOP is local sticky'


def t_cli_session_fresh_everyday_genesis():
    """§8.1 on a fresh E1 series after a reset: setup marker, operator answer, hinted kit by exact name, config and
    release checks, double absence of entry 1 (w_abs apart), PASS by exact name (downloaded and validated), GENESIS
    committed through the §5 loop, then the plan's IDLE question. A FakeDot answers every block."""
    w = World()
    lay, b = w.lay, w.lay.base
    for f in ('outbox/v2/STATE.json', 'outbox/v2/RESTORE_WORK.json', 'runtime/RELEASE.json',
              'runtime/VM_HELPER_CONFIG.json'):
        os.unlink(b / f)
    commit = host.repo_commit(lay)
    (lay.tools / 'var').mkdir(parents=True)
    (lay.tools / 'var/cps_vm2_setup_ok').write_text('%s %s\n' % (BOOT, commit))
    rp = cli.host.HELPER_REPO / 'deploy/run/cps_job.py'
    rel = {'status': 'RELEASED_FOR_USE', 'repository': {'root': str(b / 'repo'), 'commit': commit},
           'source_prep': {'deps_bundle': str(lay.tools / 'builder-deps')}, 'vm_helper': {'tree_sha256':
                                                                                         host.helper_tree_sha256()},
           'pinned_files_sha256': {'deploy/run/cps_job.py': sha(rp.read_bytes())}}
    cfg = json.loads(json.dumps({'schema': 'cps.vm2-config.v1', 'series': 'E1',
                                 'accepted_helper_tree_sha256': [host.helper_tree_sha256()], 'accepts_release_sha256': [],
                                 'selftest_expected_tests': 7, 'clock_wait_max_seconds': 60,
                                 'foreground_hold_seconds': 1200, 'stage_max_seconds': dict(STAGE_MAX),
                                 'max_upload_bytes': 50000000, 'png_part_bytes': 1000000, 'max_entry_bytes': 50000000,
                                 'max_transcript_bytes': 2 * 10 ** 7, 'max_ai_output_bytes': 2 * 10 ** 7,
                                 'conversation_re': r'conv-[0-9a-f]{8}', 'transcript_ext': 'json',
                                 'drive_id_re': r'[A-Za-z0-9_-]{20,80}', 'gates': w.gates, 'clear': None,
                                 'doc_samples': []}))
    mem = {'RELEASE.json': json.dumps(rel).encode(), 'VM_HELPER_CONFIG.json': json.dumps(cfg).encode()}
    zb = io.BytesIO()
    import zipfile
    with zipfile.ZipFile(zb, 'w') as z:
        for k, v in sorted(mem.items()):
            z.writestr(k, v)
        z.writestr('SHA256SUMS', ''.join('%s  %s\n' % (sha(v), k) for k, v in sorted(mem.items())))
    kit = zb.getvalue()
    w.drive = FakeDrive()                               # a fresh series: nothing in the journal folder
    w.drive.put(N.FOLDERS['setup'], 'SESSION_KIT_%s.zip' % sha(kit)[:12], kit)
    durable.write_plain(b / 'outbox/v2/HINT.json', {'seq': 0, 'kit': sha(kit)[:12]})
    fp = 'f' * 64
    pdoc = {'schema': 'cps.vm-fingerprint-pass.v1', 'fingerprint_sha256': fp,
            'selftest': {'failed_count': 0, 'tests': 7, 'passed_count': 7}}
    w.drive.put(N.FOLDERS['setup'], 'FINGERPRINT_PASS_%s.json' % fp, json.dumps(pdoc).encode())
    clock = Clock(1793000000)
    seen, answers = [], {'operator_model': 'gpt-x', 'platform': 'chat'}
    with patched(host, 'now', clock), patched(cli, 'fingerprint', lambda lay_: (fp, {'components': {}})):
        code, lines = w.cmd('go')
        for _ in range(60):
            seen.append(lines)
            do = lines[-1]
            if code != 0:
                break
            if do.startswith('DO: WAIT'):
                clock.t += int(do.split('=')[1])
                code, lines = w.cmd('go')
            elif ' found ' in do:
                code, lines = w.cmd('found', *dot_do(w.drive, lines))
            elif ' answer ' in do:
                keys = [t.split('=')[0] for t in do.split(' answer --at ')[1].split(' ')[1:]]
                if keys == ['case']:
                    break
                code, lines = w.cmd('answer', '--at', at_of(lines), *['%s=%s' % (k, answers[k]) for k in keys])
            else:
                dot_do(w.drive, lines)
                code, lines = w.cmd('go')
    assert lines[-1].endswith('case=CASE_ID') and 'state=IDLE' in lines[0], (code, [l for ls in seen for l in ls])
    st = json.loads((b / 'outbox/v2/STATE.json').read_text())
    assert st['head']['seq'] == 1 and st['state']['mode'] == 'everyday' and st['pass']['name'].endswith(fp + '.json')
    assert w.drive.find(N.FOLDERS['E'], 'CPSJ_E1_000001.tgz'), 'GENESIS is on the fake Drive'
    finds1 = [ln for ls in seen for ln in ls if ln.startswith('FIND ') and 'CPSJ_E1_000001.tgz' in ln]
    assert len(finds1) >= 3, 'two absence checks before GENESIS, then the GENESIS FIND'
    assert (lay.runtime / 'VM_HELPER_CONFIG.json').is_file(), 'the accepted kit is installed'
    assert not any('UPLOAD' in ln and 'FINGERPRINT_PASS' in ln for ls in seen for ln in ls)
    # a reset: new boot, BASE emptied but for the repository; the hint from the last CPSV line
    boot2 = '1f0e0d0c-0b0a-4908-8706-050403020100'
    (w.root / 'boot_id').write_text(boot2 + '\n')
    for d in ('outbox', 'inbox', 'runtime'):
        shutil.rmtree(b / d)
    (b / 'outbox/v2').mkdir(parents=True)
    (lay.tools / 'var/cps_vm2_setup_ok').write_text('%s %s\n' % (boot2, commit))
    durable.write_plain(b / 'outbox/v2/HINT.json', {'seq': 1, 'kit': sha(kit)[:12]})
    clock.t += 3600
    seen = []
    with patched(host, 'now', clock), patched(cli, 'fingerprint', lambda lay_: (fp, {'components': {}})):
        code, lines = w.cmd('go')
        for _ in range(60):
            seen.append(lines)
            do = lines[-1]
            if code != 0:
                break
            if do.startswith('DO: WAIT'):
                clock.t += int(do.split('=')[1])
                code, lines = w.cmd('go')
            elif ' found ' in do:
                code, lines = w.cmd('found', *dot_do(w.drive, lines))
            elif ' answer ' in do:
                keys = [t.split('=')[0] for t in do.split(' answer --at ')[1].split(' ')[1:]]
                if keys == ['case']:
                    break
                code, lines = w.cmd('answer', '--at', at_of(lines), *['%s=%s' % (k, answers[k]) for k in keys])
            else:
                dot_do(w.drive, lines)
                code, lines = w.cmd('go')
    assert lines[-1].endswith('case=CASE_ID'), (code, [ln for ls in seen for ln in ls])
    st = json.loads((b / 'outbox/v2/STATE.json').read_text())
    assert st['head']['seq'] == 2 and st['state']['restores'] == 1 and st['state']['boots'][-1] == [boot2, 2]
    assert w.drive.find(N.FOLDERS['E'], 'CPSJ_E1_000002.tgz'), 'the RESTORE is on the fake Drive'
    assert not any(ln.startswith('DOWNLOAD') and 'FINGERPRINT_PASS' in ln for ls in seen for ln in ls), \
        'a PASS with the journal md5 is accepted without a download'


def t_printed_blocks_grammar_and_paths():
    """L5/L9 over every block the cli printed in this suite: grammar, ASCII, and every path round-trips."""
    assert PRINTED, 'no block printed'
    for lines in PRINTED:
        assert drive.check_grammar(lines) is None
        for ln in lines[1:]:
            toks = shlex.split(ln)
            assert all(t.isascii() for t in toks)
            for t in toks:
                if t.startswith('/'):
                    assert shlex.split(shlex.quote(t)) == [t]


TESTS = [t_commit_entry_then_parts, t_commit_duplicates_same_md5_kept, t_commit_fork_foreign_md5,
         t_commit_bounded_reupload, t_commit_late_appearing_copy_is_harmless, t_commit_md5_hidden_download_back,
         t_commit_refused_upload_find_before_reupload, t_commit_rebase_absence_third_check,
         t_commit_refuses_second_and_limits, t_commit_illegal_transition_leaves_nothing,
         t_durable_write_ok_and_short_write, t_durable_zero_write_is_eio, t_durable_enospc_and_fsync_eio,
         t_durable_doc_self_hash, t_commit_enospc_at_every_write, t_walk_strict_unsupported_entries,
         t_snapshot_place_roundtrip_and_evict, t_evict_frozen_folder, t_evict_changed_file_and_unplace,
         t_runner_parse, t_runner_argv_refuses_unsafe_values, t_grammar_and_quoting, t_found_argument_rules,
         t_config_upload_and_stage_budget_invalid, t_gate1_foreground_hold_gate, t_cli_setup_failed_log_uploaded_then_stop,
         t_cli_idle_reprint_and_refusals, t_cli_inputs_commit_found_and_next_stage, t_cli_fork_is_sticky,
         t_cli_upload_failed_after_three_tries, t_cli_enospc_halts_before_printing, t_cli_md5_hidden_download_back,
         t_cli_session_fresh_everyday_genesis, t_cli_generator_open_export_ask_ai_commit,
         t_printed_blocks_grammar_and_paths]


def run(only=None, work=None):
    global WORK
    WORK = work or tempfile.mkdtemp(prefix='test_vio_')
    os.makedirs(WORK, exist_ok=True)
    env0 = dict(os.environ)
    passed, failed = 0, []
    for fn in TESTS:
        if only and fn.__name__ not in only:
            continue
        try:
            fn()
            passed += 1
        except Exception as e:                      # noqa: BLE001 - recorded per test
            import traceback
            failed.append({'test': fn.__name__, 'error': '%s: %s' % (type(e).__name__, e),
                           'trace': traceback.format_exc()[-1500:]})
        finally:
            os.environ.clear()
            os.environ.update(env0)
    return {'name': 'test_vio', 'tests': passed + len(failed), 'passed': passed, 'failed': [f['test'] for f in failed],
            'detail': failed, 'counts': {'blocks_printed': len(PRINTED)}}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', default=None)
    ap.add_argument('--only', default='')
    a = ap.parse_args()
    r = run([x for x in a.only.split(',') if x] or None, a.work)
    for f in r['detail']:
        print('FAILED', f['test'], f['error'])
        print(f['trace'])
    print(json.dumps({k: r[k] for k in ('tests', 'passed', 'failed')}))
    sys.exit(0 if not r['failed'] else 1)
