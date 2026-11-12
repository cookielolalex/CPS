"""Focused tests of the VM-side I/O layer (builder A): commit() steps of §5 (entry first, parts after, duplicates, FORK,
the bounded re-upload, md5-hidden download-back, the prefix variant, the rebase absence check, size limits), durable
writes (§2.4: short write, zero write, ENOSPC and EIO halt before anything is printed), the strict walk, snapshot,
placement and evict (§3.8, §7.6, §8.5.1, SAFE-01), runner result parsing (§7.2), and the printed-line grammar (§6.1,
L5, L9) on every block the cli prints here. A small FakeDrive/FakeDot of its own; invented data only.
Entry point: run(only=None, work=None); standalone: python3 -I -B tests/test_vio.py --work /abs/dir."""
import contextlib
import copy
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
import time
import zipfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
VM2 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, VM2)
import core_world as CW                                                     # noqa: E402
from cpsvm2 import cli                                                      # noqa: E402
from cpsvm2.core import fold as F, names as N                               # noqa: E402
from cpsvm2.vio import drive, durable, host, place, runner, savepoint       # noqa: E402
from cpsvm2.vio.v1compat import Halt                                        # noqa: E402
from cpsvm2.vio.v1mod import tree_list                                      # noqa: E402
from cpsvm2.vio.v1reuse import Archive, Layout                              # noqa: E402

WORK = None
BOOT = '0f0e0d0c-0b0a-4908-8706-050403020100'
GATES = {'p1_vm_files': 'PASS', 'p1_transcript_export': 'yes', 'p1_conversation_list': 'yes',
         'p1_end_after_reset': 'yes', 'p2_exact_search': 'PASS', 'p2_lag_seconds': 20, 'p2_max_upload_bytes': 50000000, 'p2_tgz_kept': 'PASS',
         'p2_failed_upload_can_appear': 'yes', 'p3_identity_stable': 'yes', 'p3_clock_tolerance_seconds': 300,
         'p5_foreground_hold_seconds': 1200, 'p5_setup_seconds': 130}
STAGE_MAX = {k: 600 for k in N.STAGE_KEYS}
TOOLS = b'file_search\nweb_search\n'                  # an invented TOOL_INVENTORY.txt (D9)
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


def dot_do(drv, lines, skip_upload=False):
    """Carry out a block on the FakeDrive and return the found arguments (manual form, v2.1 §2.3: one --name per FIND
    line, in order), or None when the block does not end in `found`."""
    names = []
    for ln in lines[1:]:
        t = shlex.split(ln)
        if t[0] == 'UPLOAD' and not skip_upload:
            drv.upload(t[1], t[3], t[5])
        elif t[0] == 'FIND':
            assert t[2] == 'NAME', 'only exact-name FIND exists (X.5)'
            names.append((t[1], t[3]))
        elif t[0] == 'DOWNLOAD':
            assert Path(t[5]).parent.is_dir() and not os.path.lexists(t[5]), 'S-09: render prepared the target'
            Path(t[5]).write_bytes(drv.download(t[3]))
    if ' found --at ' not in lines[-1]:
        return None
    args = ['--at', at_of(lines)]
    for folder, n in names:
        cs = drv.find(folder, n)
        args += ['--name', n] + (['--none'] if not cs else [])
        for c in cs:
            args += ['--file', '%s:%d' % (c['id'], len(c['bytes']))]
    return args


def dot_until(w, lines, stop, limit=30):
    """Answer go/found blocks until a block whose header or DO line contains `stop`."""
    for _ in range(limit):
        if not lines or stop in lines[0] or stop in lines[-1]:
            return lines
        args = dot_do(w.drive, lines)
        code, lines = w.cmd('found', *args) if args else w.cmd('go')
    raise AssertionError('no %s: %s' % (stop, lines))


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
    from cpsvm2.worker import png_whole
    members, job_rows, pf, rels, tsha = place.snapshot(env.lay, str(jd))
    whole = png_whole(str(jd), rels, pf, 'A/case01') if pf else None
    d = dict(sp_draft(seq, kind, body), payload_png={'files': pf, 'whole_sha256': whole, 'parts_seq': seq})
    src = [{'kind': 'PNG', 'job_dir': str(jd), 'rels': rels, 'files': pf, 'run': 'A/case01'}] if pf else []
    pend, entry, whole = savepoint.write_commit(env, d, members, src, [], fake_complete)
    return pend, entry, whole, pf


def sp_block(env, loop, reprint=False):
    return savepoint.block(loop, env.cfg['max_upload_bytes'], env.gates.get('p2_lag_seconds'), env.series_folder,
                           reprint)


def found_of(drv, finds, names):
    """The FakeDot's attested copies {name: [[id, size]]} for one ATTEST_FOUND block."""
    got = {n: [[c['id'], len(c['bytes'])] for c in drv.find(f, n)] for f, how, n in finds}
    for n in names:
        got.setdefault(n, [])
    return got


def sp_found(env, loop, got, refused=(), known=lambda n: ()):
    return savepoint.on_found(loop, got, set(refused), known, str(env.lay.inbox / 'verify'))


def drive_pending(env, drv, pend, max_rounds=40):
    """The §5 loop between savepoint and a FakeDot until every file is confirmed; returns the printed (do) actions."""
    seen = []
    for _ in range(max_rounds):
        b = sp_block(env, pend)
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
            r = savepoint.on_verify(pend)
            if r[0] != 'ok':
                return seen + [r[:2]]
            continue
        for p, f, n in ups:
            drv.upload(p, f, n)
        r = sp_found(env, pend, found_of(drv, finds, names))
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
    ups, finds, dls, do, names = sp_block(env, pend)
    assert [u[2] for u in ups] == [entry['name']] and names == [entry['name']], 'the entry alone first'
    assert pend['tries'][entry['name']]['uploads'] == 1
    for p, f, n in ups:
        drv.upload(p, f, n)
    assert sp_found(env, pend, found_of(drv, finds, names)) == ('ok', None)
    ups, finds, dls, do, names = sp_block(env, pend)
    assert do[0] == 'RUN' and len(dls) == 1 and not ups, 'rule V: the entry is downloaded back (v2.1 §2.1)'
    for f, did, p in dls:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_bytes(drv.download(did))
    assert savepoint.on_verify(pend) == ('ok', None) and not os.path.exists(dls[0][2])
    ups, finds, dls, do, names = sp_block(env, pend)
    assert [u[2] for u in ups] == [p['name'] for p in pend['parts']], 'every part after the entry, in order'
    assert names == [p['name'] for p in pend['parts']] and do[0] == 'ATTEST_FOUND'
    for p, f, n in ups[1:]:
        drv.upload(p, f, n)                                 # the first part's upload never lands
    assert sp_found(env, pend, found_of(drv, finds, names))[0] == 'ok'
    ups, finds, dls, do, names = sp_block(env, pend)
    assert do[0] == 'RUN' and len(dls) == len(pend['parts']) - 1
    for f, did, p in dls:
        Path(p).write_bytes(drv.download(did))
    assert savepoint.on_verify(pend) == ('ok', None)
    ups, finds, dls, do, names = sp_block(env, pend)
    assert do[0] == 'WAIT' and not ups and not finds, 'one --none: wait first'
    ups, finds, dls, do, names = sp_block(env, pend)
    assert names == [pend['parts'][0]['name']] and not ups, 'after the wait: FIND again, no UPLOAD, only the missing part'
    assert sp_found(env, pend, {names[0]: []}) == ('ok', None)
    rest = drive_pending(env, drv, pend)
    assert rest and rest[0][1] == [pend['parts'][0]['name']], 're-upload of the missing part only'
    cache = {'marks': {'OPEN:x': 'utc'}}
    st = savepoint.finish(env, cache, pend)
    assert not os.path.exists(env.v2 / 'PENDING.json') and st['head']['seq'] == 1 and st['marks'] == cache['marks']
    assert [c['name'] for c in st['confirms']] == [entry['name']] + [p['name'] for p in entry['parts']]
    assert st['post'][-1][0] == 'DROP_LOCAL'


def t_commit_duplicates_same_md5_kept():
    """Two copies with our bytes: both downloaded back and both ids kept (v2.1 §2.2.2: not a FORK)."""
    root = tmpdir('dup')
    env, drv = SPEnv(root), FakeDrive()
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0))
    ups, finds, dls, do, names = sp_block(env, pend)
    for p, f, n in ups:
        drv.upload(p, f, n)
        drv.upload(p, f, n)                                 # the same bytes twice
    cs = drv.find(env.series_folder, entry['name'])
    assert len(cs) == 2
    assert [x[0] for x in drive_pending(env, drv, pend)] == ['ATTEST_FOUND', 'RUN']
    assert sp_block(env, pend) is None
    st = savepoint.finish(env, {}, pend)
    assert [c['id'] for c in st['confirms'][0]['copies']] == [c['id'] for c in cs], 'every id is kept'


def t_commit_fork_foreign_md5():
    """A copy at our name with other bytes is a FORK (only downloaded bytes decide, S-03); a copy attested at a size
    that its download does not have is a slip, DOWNLOAD_INCOMPLETE, never a FORK (OPX-03)."""
    root = tmpdir('fork')
    env, drv = SPEnv(root), FakeDrive()
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0))
    pend0 = json.loads(json.dumps(pend))
    drv.put(env.series_folder, entry['name'], b'another commit with the same name')
    r = drive_pending(env, drv, pend)
    assert r[-1] == ('stop', 'FORK'), r
    ups, finds, dls, do, names = sp_block(env, pend0)
    for p, f, n in ups:
        drv.upload(p, f, n)
    ours = [c for c in drv.find(env.series_folder, entry['name']) if c['bytes'] == Path(pend0['entry']['path'])
            .read_bytes()][0]
    assert sp_found(env, pend0, {entry['name']: [[ours['id'], len(ours['bytes']) + 1]]}) == ('ok', None)
    ups, finds, dls, do, names = sp_block(env, pend0)
    Path(dls[0][2]).parent.mkdir(parents=True, exist_ok=True)
    Path(dls[0][2]).write_bytes(ours['bytes'])
    assert savepoint.on_verify(pend0) == ('slip', 'DOWNLOAD_INCOMPLETE', entry['name']), 'a size slip is re-asked'


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
    assert r[-1][0] == 'RUN' and sp_block(env, pend) is None
    drv.put(env.series_folder, entry['name'], Path(pend['entry']['path']).read_bytes())
    assert len(drv.find(env.series_folder, entry['name'])) == 2


def t_commit_md5_hidden_download_back():
    """Rule V by download-back (v2.1 has no md5-visible mode): a missing download is a slip (DOWNLOAD_MISSING), the
    same size with other bytes is a FORK, our bytes confirm the copy with the local md5; downloads are deleted."""
    root = tmpdir('hidden')
    env, drv = SPEnv(root), FakeDrive()
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0))
    ups, finds, dls, do, names = sp_block(env, pend)
    assert do[0] == 'ATTEST_FOUND' and 'md5_hidden' not in do[1]
    for p, f, n in ups:
        drv.upload(p, f, n)
    cs = drv.find(env.series_folder, entry['name'])
    assert sp_found(env, pend, {entry['name']: [[cs[0]['id'], len(cs[0]['bytes'])]]}) == ('ok', None)
    ups, finds, dls, do, names = sp_block(env, pend)
    assert do[0] == 'RUN' and len(dls) == 1
    pend1 = json.loads(json.dumps(pend))
    assert savepoint.on_verify(pend) == ('slip', 'DOWNLOAD_MISSING', entry['name'])
    Path(dls[0][2]).parent.mkdir(parents=True, exist_ok=True)
    good = Path(pend['entry']['path']).read_bytes()
    Path(dls[0][2]).write_bytes(good[:-1] + bytes([good[-1] ^ 1]))       # same size, other bytes
    pend2 = json.loads(json.dumps(pend1))
    assert savepoint.on_verify(pend1) == ('stop', 'FORK', None)
    assert os.path.exists(dls[0][2]), 'a FORK keeps its download for stop_block (S-03)'
    Path(dls[0][2]).write_bytes(good)
    assert savepoint.on_verify(pend2) == ('ok', None) and not os.path.exists(dls[0][2])
    assert pend2['entry']['copies'] == [[cs[0]['id'], pend['entry']['md5'], len(good)]], 'local md5 recorded'


def t_commit_refused_upload_find_before_reupload():
    """§X.5.6: a --refused name found absent hands back (UPLOAD_REFUSED HANDBACK A, PENDING written); the next block
    FINDs and never UPLOADs; two absences then re-upload; a third refused upload's two absences are UPLOAD_FAILED;
    --refused with copies only counts. Setup files over max_upload_bytes are UPLOAD_TOO_LARGE before printing (§X.3)."""
    root = tmpdir('refused')
    env, drv = SPEnv(root), FakeDrive()
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0))
    n = entry['name']
    for k in range(1, 4):
        ups, finds, dls, do, names = sp_block(env, pend)
        assert [u[2] for u in ups] == [n] and do[1]['uploaded'] == [n], (k, ups)
        r = sp_found(env, pend, {n: []}, {n})
        assert r == ('handback', n) and pend['tries'][n]['refused'] == k
        ups, finds, dls, do, names = sp_block(env, pend)
        assert not ups and finds == ((env.series_folder, 'NAME', n),), 'FIND first after a refusal'
        r = sp_found(env, pend, {n: []})
        assert r == ('ok', None) and sp_block(env, pend)[3][0] == 'WAIT'
        ups, finds, dls, do, names = sp_block(env, pend)
        assert not ups
        r = sp_found(env, pend, {n: []})
        if k < 3:
            assert r == ('ok', None) and pend['tries'][n]['need'] == 'upload'
    assert r == ('stop', 'UPLOAD_FAILED') and pend['tries'][n]['uploads'] == 3
    root2 = tmpdir('refused2')
    env2, drv2 = SPEnv(root2), FakeDrive()
    pend2, e2, _, _ = write_png_commit(env2, make_job(root2, pngs=0))
    ups, finds, dls, do, names = sp_block(env2, pend2)
    for p_, f, n_ in ups:
        drv2.upload(p_, f, n_)
    assert sp_found(env2, pend2, found_of(drv2, finds, names), {e2['name']}) == ('ok', None)
    assert pend2['verify'] and pend2['tries'][e2['name']]['refused'] == 1
    big = root2 / 'big.json'
    big.write_bytes(b'x' * 2000)
    lp = savepoint.setup_loop([(big, 'CPS/setup', 'big.json')])
    expect_halt('UPLOAD_TOO_LARGE', savepoint.block, lp, 1000, 20, 'CPS/setup')
    assert drive.parse_found(['--at', 'A', '--name', 'N', '--refused', 'N', '--none'])[3] == ['N']


def t_commit_rebase_absence_third_check():
    root = tmpdir('rebase')
    env, drv = SPEnv(root), FakeDrive()
    miss = 'CPSJ_Q1_000004_PNG01.part'
    body = {'rebase': {'missing_parts': [miss]}}
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0), seq=5, body=body, kind='RESTORE')
    ups, finds, dls, do, names = sp_block(env, pend)
    assert (env.series_folder, 'NAME', miss) in finds and miss in names
    for p, f, n in ups:
        drv.upload(p, f, n)
    drv.put(env.series_folder, miss, b'it came back')
    assert sp_found(env, pend, found_of(drv, finds, names)) == ('stop', 'REBASE_PART_APPEARED')


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
    from cpsvm2.worker import png_whole
    jd = make_job(root)
    members, rows, pf, rels, _ = place.snapshot(env.lay, str(jd))
    d = dict(sp_draft(1), payload_png={'files': pf, 'whole_sha256': png_whole(str(jd), rels, pf, 'A/case01'),
                                       'parts_seq': 1})
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
    t, aside = place.place_job(env.lay, str(jd), pend['entry']['path'], {'whole_sha256': whole, 'files': pf},
                               [p['path'] for p in pend['parts']])
    assert tree_list(jd) == before and t == place.tree_sha(before) and aside is None, 'the snapshot exactly'
    t2, aside = place.place_job(env.lay, str(jd), pend['entry']['path'], {'whole_sha256': whole, 'files': pf},
                                [p['path'] for p in pend['parts']])
    assert (t2, aside) == (t, None) and tree_list(jd) == before, 'an equal target is kept (v2.1 §2.4.6)'
    assert not list(jd.parent.glob('.cps_vm_stage_*')), 'the staging is removed'


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
    a = {'base': '/tmp/cps', 'model': 'gpt-x', 'job_dir': '/tmp/cps/qual/A/c1'}
    v = runner.argv_for('freeze', a)
    assert v == ['freeze', '--job-dir', '/tmp/cps/qual/A/c1', '--operator-model', 'gpt-x']
    expect_halt('INTERNAL_PRINT', runner.argv_for, 'freeze', dict(a, job_dir='/tmp/cps/a b'))
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
    lines = drive.body_lines(blk, '/tmp/cps/vm.sh')
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
    ok = lambda v: N.check_value('id', 'ID', v, {}) is None                       # noqa: E731
    at, raw, items, ref = drive.parse_found(['--at', 'A', '--name', 'N', '--file', 'i' * 20 + ':1', '--none'])
    assert raw is None and drive.manual_copies(items, ['N'], ok)[0] == 'FOUND_FILE_AND_NONE'
    at, raw, items, ref = drive.parse_found(['--at', 'A', '--name', 'N'])
    assert drive.manual_copies(items, ['N'], ok)[0] == 'FOUND_SYNTAX'
    at, raw, items, ref = drive.parse_found(['--at', 'A', '--name', 'N', '--none'])
    assert drive.manual_copies(items, ['N', 'M'], ok)[0] == 'FOUND_NAMES_INCOMPLETE'
    at, raw, items, ref = drive.parse_found(['--at', 'A', '--name', 'N', '--file', 'i' * 20 + ':m:1'])
    assert drive.manual_copies(items, ['N'], ok)[0] == 'VALUE_PATTERN', 'the md5 form is gone (v2.1)'
    assert drive.manual_copies(items[:0] + [['N', ['i' * 20 + ':12'], False]], ['N'], ok) == (None, {
        'N': [['i' * 20, 12]]})
    assert drive.parse_found(['--at', 'A', '--raw', '/x.json', '--refused', 'N']) == ('A', '/x.json', [], ['N'])
    for bad in (['--at', 'A', '--raw', '/x', '--name', 'N'], ['--at', 'A', '--name', 'N', '--raw', '/x'],
                ['--at', 'A', '--raw', '/x', '--raw', '/y']):
        try:
            drive.parse_found(bad)
            raise AssertionError('accepted %s' % bad)
        except U:
            pass


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
            'drive_id_re': r'[A-Za-z0-9_-]{20,80}', 'gates': dict(GATES), 'clear': None, 'doc_samples': [],
            'tool_inventory_sha256': 'c' * 64}

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
                 {'gates': {k: v for k, v in GATES.items() if k != 'p3_clock_tolerance_seconds'}},
                 {'gates': dict(GATES, p2_md5_visible='yes')}, {'gates': dict(GATES, p2_newest_first='no')},
                 {'tool_inventory_sha256': None}, {'tool_inventory_sha256': 'C' * 64}):
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
        os.environ.update({'HOME': str(r / 'home'), 'CPS_VM_BASE': str(r / 'tmp/cps'),           # A1: BASE outside HOME
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
               'gates': self.gates, 'clear': None, 'doc_samples': ['conv-EXAMPLE', 'case-example'],
               'tool_inventory_sha256': sha(TOOLS)}
        (self.lay.runtime / 'RELEASE.json').write_bytes(rel)
        (self.lay.runtime / 'TOOL_INVENTORY.txt').write_bytes(TOOLS)
        (self.lay.runtime / 'VM_HELPER_CONFIG.json').write_bytes(json.dumps(cfg).encode())
        w = CW.World('E1', gates=self.gates)
        w.boot = BOOT
        self.cw = w
        gb = {'mode': 'everyday', 'operator': {'model': 'gpt-x', 'platform': 'chat'}, 'jobs': None, 'ledger': None,
              'layout': F.layout_of(str(b)), 'gates': self.gates, 'pass': {'name': 'P', 'md5': '0' * 32},
              'other_series_absent': None, 'approval': 'none'}
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
        with patched(CW, 'BASE', str(self.lay.base)):                # MAINT-1: the genesis layout's job folder
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
    """The same block again with the same --at; each refusal changes only BLOCK.json's refusal count (D3b), never the
    cache (each case runs in a World of its own: the fourth refusal of one block is SLIP_LIMIT)."""
    w = World()
    code, a = w.cmd('go')
    assert code == 0 and a[-1].endswith('answer --at %s case=CASE_ID' % at_of(a)) and 'state=IDLE' in a[0], a
    code, b = w.cmd('go')
    assert (code, b) == (0, a), 'the same block again, the same --at'
    for args, want in ((['answer', '--at', '000001-0001-ffffff', 'case=case01'], 'STALE_AT'),
                       (['found', '--at', None, '--name', 'x', '--none'], 'COMMAND_NOT_EXPECTED'),
                       (['answer', '--at', None, 'case=case 01'], 'VALUE_FORBIDDEN'),
                       (['answer', '--at', None, 'case=case01\n'], 'VALUE_FORBIDDEN'),
                       (['answer', '--at', None, 'case={CASE_ID}'], 'VALUE_FORBIDDEN'),
                       (['answer', '--at', None, 'case=CASE_ID'], 'VALUE_PLACEHOLDER'),
                       (['answer', '--at', None, 'case=case-example'], 'VALUE_PLACEHOLDER'),
                       (['answer', '--at', None, 'case=１２'], 'VALUE_FORBIDDEN'),
                       (['answer', '--at', None, 'case=c1', 'case=c2'], 'ARG_DUPLICATE_KEY'),
                       (['answer', '--at', None, 'case=c1', 'x=y'], 'ARG_EXTRA_KEY'),
                       (['answer', '--at', None], 'ARG_MISSING_KEY'),
                       (['answer', '--at', None, 'case=case01'], 'INPUTS_INVALID')):
        w = World()
        code, a = w.cmd('go')
        snap = {k: v for k, v in w.cache_bytes().items() if k != 'BLOCK.json'}
        code, out = w.cmd(*[x or at_of(a) for x in args])
        assert code == 4 and out[1].split()[:2] == ['REFUSED', want] and out[2:] == a[1:], (args, out)
        assert {k: v for k, v in w.cache_bytes().items() if k != 'BLOCK.json'} == snap, 'cache unchanged (%s)' % want
        assert json.loads(w.cache_bytes()['BLOCK.json'])['refused'] == 1, 'the refusal is counted (D3b)'
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
    assert s2 == [ln for ln in s if not ln.startswith('UPLOAD ')], 'a reprint has no UPLOAD line (SD-60)'
    pend = json.loads((w.lay.base / 'outbox/v2/PENDING.json').read_text())
    assert pend['tries']['CPSJ_E1_000002.tgz']['uploads'] == 1
    code, out = w.cmd('found', *dot_do(w.drive, s))
    assert code == 0 and [ln for ln in out if ln.startswith('DOWNLOAD ')], 'rule V: the copy is downloaded back'
    assert dot_do(w.drive, out) is None and not w.started, 'X.5: found never starts the stage'
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
    out = dot_until(w, s, 'STOP')
    assert out[-1] == 'DO: STOP FORK HANDBACK C', out
    code, out2 = w.cmd('go')
    assert code == 3 and out2[-1] == 'DO: STOP FORK HANDBACK C', 'a local sticky STOP'
    forks = list((w.lay.base / 'outbox/v2').glob('fork_*/verify/*'))
    assert forks and any(p.read_bytes() == b'a foreign commit' for p in forks), 'the fork bytes are kept (S-03)'


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
    """Rule V in the cli: a missing download is a slip that re-FINDs (D3a, T8), then a same-size download with other
    bytes is FORK."""
    w = World()
    code, a = w.cmd('go')
    w.inputs()
    code, s = w.cmd('answer', '--at', at_of(a), 'case=case01')
    assert '--raw FILE' in s[-1]
    code, v = w.cmd('found', *dot_do(w.drive, s))
    dl = [ln for ln in v if ln.startswith('DOWNLOAD ')]
    assert code == 0 and len(dl) == 1 and v[-1].startswith('DO: RUN '), v
    code, r = w.cmd('go')
    assert code == 4 and r[1] == 'REFUSED DOWNLOAD_MISSING CPSJ_E1_000002.tgz' and r[2].startswith('FIND '), r
    assert not any(ln.startswith('UPLOAD ') for ln in r), 'the re-FIND never uploads'
    code, v = w.cmd('found', *dot_do(w.drive, r))
    dl = [ln for ln in v if ln.startswith('DOWNLOAD ')]
    target = shlex.split(dl[0])[5]
    Path(target).write_bytes(b'x' * len(w.drive.find(N.FOLDERS['E'], 'CPSJ_E1_000002.tgz')[0]['bytes']))
    code, f = w.cmd('go')
    assert code == 3 and f[-1] == 'DO: STOP FORK HANDBACK C', f


def at_generator_question(w):
    """A World at the G end question (one OPEN, one EXPORT); returns (run, the question block, transcript path)."""
    run = w.advance_to_generate()
    code, o = w.cmd('go')
    assert code == 0 and o[-1].startswith('DO: OPEN_CONVERSATION role=G prompt=') and 'then=' not in o[-1], o
    code, x = w.cmd('go')
    assert x[-1].startswith('DO: EXPORT_TRANSCRIPT role=G to=') and 'OPEN_CONVERSATION' not in ' '.join(x)
    code, a = w.cmd('go')
    return run, a, x[-1].split(' to=')[1]


G_GOOD = {'ended': 'yes', 'conversation': 'conv-0a1b2c3d', 'platform': 'chat', 'model': 'gpt-x', 'effort': 'high',
          'single_user_message': 'yes', 'memory': 'no', 'custom_instructions': 'no', 'web': 'no', 'connectors': 'no',
          'file_uploads': 'no', 'other_agents': 'no', 'tools': 'inventory', 'transcript': 'exported'}


def g_answer(w, a, run, **kw):
    st = json.loads((w.lay.base / 'outbox/v2/STATE.json').read_text())
    lt = st['state']['runs'][run]['roles']['G1']['starts'][-1]
    g = dict(dict(G_GOOD, started_utc=lt['utc'], ended_utc=lt['utc']), **kw)
    return w.cmd('answer', '--at', at_of(a), *['%s=%s' % (k, g[k]) for k in cli.P.G_KEYS])


def t_cli_generator_open_export_ask_ai_commit():
    """§7.1 rows 5, 8, 9 and §7.5: one OPEN per START (the mark), the EXPORT once, the G end keys with the final
    message and transcript checks (each refusal counted, so at most three per World), the AI entry through the §5
    loop, then the consumer chain (finish)."""
    for group in ((({}, 'FINAL_MESSAGE_INVALID'), ({'started_utc': '2001-01-01T00:00:00Z'}, 'UTC_OUT_OF_WINDOW'),
                   ({'conversation': 'conv-EXAMPLE'}, 'VALUE_PLACEHOLDER')),
                  (({'tools': 'web,x y'}, 'VALUE_FORBIDDEN'), ({'conversation': 'CONV'}, 'VALUE_PLACEHOLDER'),
                   ({'tools': 'none'}, 'VALUE_PATTERN'))):
        w = World()
        run, a, tpath = at_generator_question(w)
        code, a2 = w.cmd('go')
        assert a2 == a, 'no second OPEN or EXPORT: the same question again'
        keys = a[-1].split(' answer --at ')[1].split(' ')[1:]
        assert [k.split('=')[0] for k in keys] == list(cli.P.G_KEYS), keys
        snap = {k: v for k, v in w.cache_bytes().items() if k != 'BLOCK.json'}
        for kw, want in group:
            code, r = g_answer(w, a, run, **kw)
            assert code == 4 and r[1].split()[:2] == ['REFUSED', want], (kw, r[:2])
            assert {k: v for k, v in w.cache_bytes().items() if k != 'BLOCK.json'} == snap
    w = World()
    run, a, tpath = at_generator_question(w)
    (w.lay.base / 'attest/final_message.txt').write_text('Done: the invented response is in run/A/output.\n')
    code, r = g_answer(w, a, run)
    assert code == 4 and r[1].startswith('REFUSED TRANSCRIPT_FILE_MISSING')
    (w.lay.base / 'attest/final_message.txt').write_text('see {placeholder} <and> "quotes"')      # data (D3c)
    Path(tpath).parent.mkdir(parents=True, exist_ok=True)
    Path(tpath).write_text('{"invented": "transcript"}')
    code, s_ = g_answer(w, a, run)
    assert code == 0 and 'state=SAVE' in s_[0], s_
    code, out = w.cmd('found', *dot_do(w.drive, s_))
    assert dot_do(w.drive, out) is None and not w.started, 'X.5: found never starts the stage'
    code, out = w.cmd('go')
    assert w.started and w.started[-1][1]['first'] == 'finish' and w.started[-1][1]['info']['consume'] == 'G1'
    st = json.loads((w.lay.base / 'outbox/v2/STATE.json').read_text())
    g1 = st['state']['runs'][run]['roles']['G1']
    assert g1['status'] == 'ARCHIVED' and g1['archives'][0]['conversation'] == 'conv-0a1b2c3d'
    ent = savepoint.read_entry(w.lay.inbox / 'journal' / st['head']['name'])
    assert ent['body']['attested']['features'] == {k: False for k in N.FEATURES}
    assert ent['body']['attested']['tools_present'] == {'source': 'inventory', 'sha256': sha(TOOLS)}
    assert [m[0] for m in ent['payload']['members']] == ['ai', 'attest', 'attest/final_message.txt',
                                                         'attest/tools.txt', 'transcript', 'transcript/G1_1.json']
    assert savepoint.member_bytes(w.lay.inbox / 'journal' / st['head']['name'], 'attest/final_message.txt') == \
        b'see {placeholder} <and> "quotes"', 'the final message verbatim'
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
            assert '[--refused NAME]' in a[-1], a[-1]
            a = dot_until(w, w.cmd('found', *dot_do(w.drive, a))[1], 'STOP')
            code = 3
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
                                 'doc_samples': [], 'tool_inventory_sha256': sha(TOOLS)}))
    mem = {'RELEASE.json': json.dumps(rel).encode(), 'VM_HELPER_CONFIG.json': json.dumps(cfg).encode(),
           'TOOL_INVENTORY.txt': TOOLS}
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
    seen, answers = [], {'operator_model': 'gpt-x', 'platform': 'chat', 'approval': 'none'}
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
    assert any(ln.startswith('DOWNLOAD') and 'FINGERPRINT_PASS' in ln for ls in seen for ln in ls), \
        'v2.1 has no md5 shortcut: every PASS copy is downloaded and validated (§2.1)'


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


# ================================================================ v2.1 (delta §1.2, §2.15.5): vio rows
# Unit rows first, then rows on fakes.World (E1: no runner stage before IDLE; the stage rows use the real runner).
M007 = {'content': [{'type': 'text', 'text': 'Action completed.'}], 'isError': False, 'structuredContent': {
    'results': [{'url': 'https://drive.invalid/file/d/fakedriveid00000000000000000001/view', 'title': 'NAME_A',
                 'id': 'fakedriveid00000000000000000001', 'mime_type': 'application/octet-stream', 'size': '1000000',
                 'file_or_folder': 'file', 'created_at': '2026-11-10T01:16:17.040Z',
                 'updated_at': '2026-11-10T01:16:17.040Z', 'viewedByMeTime': None, 'display_title': 'NAME_A',
                 'display_url': 'https://drive.invalid/x', 'parent_ids': ['fakefolder01'], 'shared': False}]}}
EMPTY = {'content': [{'type': 'text', 'text': 'Action completed.'}], 'isError': False,
         'structuredContent': {'results': []}}
IDA = 'fakedriveid00000000000000000001'


def raw_parse(doc, names):
    """The M007 envelope as the Dot saves it (compact JSON.stringify), then parse_raw."""
    return drive.parse_raw(json.loads(json.dumps(doc, separators=(',', ':'))), names,
                           lambda v: N.fm(N.DEFAULT_DRIVE_ID_RE, v))


def t_d4_parse_raw_rules():
    """D4 (§2.3): every RAW_INVALID detail (count, error, shape, pages, entry, duplicate, listing), the next-page token
    (refused on the last object only), the exact title, a folder row, a `files` element without the name (absence is
    never inferred from a listing), one id with two sizes."""
    assert raw_parse(M007, ['NAME_A']) == (None, {'NAME_A': [[IDA, 1000000]]})
    assert raw_parse([M007, EMPTY], ['NAME_A', 'NAME_B']) == (None, {'NAME_A': [[IDA, 1000000]], 'NAME_B': []})
    assert raw_parse([EMPTY['structuredContent']], ['NAME_B']) == (None, {'NAME_B': []})
    assert raw_parse([M007], ['NAME_A', 'NAME_B'])[0] == 'count'
    assert raw_parse(dict(M007, isError=True), ['NAME_A'])[0] == 'error'
    for bad in ({'content': [], 'structuredContent': {'results': [], 'files': []}}, {'content': []},
                {'content': [], 'structuredContent': {'results': {}}}, ['x'], [[]], 'text'):
        assert raw_parse(bad, ['NAME_A'])[0] in ('shape', 'count'), bad
    assert raw_parse({'content': [], 'structuredContent': {'results': [], 'next_page_token': 'x'}}, ['NAME_A'])[0] \
        == 'pages'
    assert raw_parse(dict(M007, nextPageToken='x'), ['NAME_A'])[0] == 'pages'
    assert raw_parse([[{'results': [], 'nextPageToken': 'x'}, {'results': []}]], ['NAME_A']) == (None, {'NAME_A': []})
    assert raw_parse([[{'results': [], 'next_page_token': None}]], ['NAME_A']) == (None, {'NAME_A': []})
    contains = copy.deepcopy(M007)
    contains['structuredContent']['results'][0]['title'] = 'NAME_A.bak'
    assert raw_parse(contains, ['NAME_A']) == (None, {'NAME_A': []})                 # the exact title only (W46)
    for k, v in (('size', '0'), ('size', '01'), ('size', 1.5), ('id', 'short'), ('created_at', 'yesterday'),
                 ('size', None)):
        bad = copy.deepcopy(M007)
        bad['structuredContent']['results'][0][k] = v
        assert raw_parse(bad, ['NAME_A'])[0] == 'entry', (k, v)
    num = copy.deepcopy(M007)
    num['structuredContent']['results'][0]['size'] = 1000000
    assert raw_parse(num, ['NAME_A']) == (None, {'NAME_A': [[IDA, 1000000]]}), 'an integer size'
    two = copy.deepcopy(M007)
    two['structuredContent']['results'].append(dict(two['structuredContent']['results'][0], size='5'))
    assert raw_parse(two, ['NAME_A'])[0] == 'duplicate'
    two['structuredContent']['results'][1]['size'] = '1000000'
    assert raw_parse(two, ['NAME_A']) == (None, {'NAME_A': [[IDA, 1000000]]}), 'one id reported twice: one copy'
    listing = {'structuredContent': {'files': [{'title': 'NAME_X', 'id': IDA, 'size': '1',
                                                'created_time': '2026-11-10T01:16:17Z'}]}, 'content': []}
    assert raw_parse(listing, ['NAME_A'])[0] == 'listing'                            # W69
    folder = copy.deepcopy(M007)
    folder['structuredContent']['results'][0]['file_or_folder'] = 'folder'
    assert raw_parse(folder, ['NAME_A']) == (None, {'NAME_A': []})



def t_d11_parse_raw_edges():
    """D11a (parse_raw): a dict for two names is `count` (never iterated); a non-dict row is skipped; a non-string
    created time and a size of integer 0 are `entry`; a listing element before a search element still forbids
    absence (`listing`)."""
    two_keys = {'a': M007, 'b': EMPTY}
    assert raw_parse(two_keys, ['NAME_A', 'NAME_B'])[0] == 'count'
    junk = copy.deepcopy(M007)
    junk['structuredContent']['results'].insert(0, 'not a row')
    assert raw_parse(junk, ['NAME_A']) == (None, {'NAME_A': [[IDA, 1000000]]})
    for k, v in (('created_at', 5), ('size', 0)):
        bad = copy.deepcopy(M007)
        bad['structuredContent']['results'][0][k] = v
        assert raw_parse(bad, ['NAME_A'])[0] == 'entry', (k, v)
    listing = {'structuredContent': {'files': [{'title': 'NAME_A', 'id': IDA, 'size': '1000000',
                                                'created_time': '2026-11-10T01:16:17Z'}]}, 'content': []}
    assert raw_parse([listing, EMPTY], ['NAME_A', 'NAME_B'])[0] == 'listing'
    assert raw_parse([EMPTY, listing], ['NAME_B', 'NAME_A'])[0] == 'listing'

def t_d4_found_raw_search_and_listing_objects():
    """D4 (F4): the M007 search envelope and a listing object (structuredContent.files, created_time) both give the
    copies of an exact title; a listing proves presence only."""
    lst = {'content': [], 'structuredContent': {'files': [
        {'title': 'NAME_A', 'id': IDA, 'size': '7', 'created_time': '2026-11-10T01:16:17Z', 'file_or_folder': 'file'},
        {'title': 'NAME_B', 'id': IDA[:-1] + '2', 'size': 9, 'created_time': '2026-11-10T01:16:18.5Z'}]}}
    assert raw_parse(lst, ['NAME_A']) == (None, {'NAME_A': [[IDA, 7]]})
    assert raw_parse([M007, lst], ['NAME_A', 'NAME_B'])[0] == 'duplicate'      # one id, two sizes across elements
    lst2 = copy.deepcopy(lst)
    lst2['structuredContent']['files'][0]['id'] = IDA[:-1] + '3'
    r = raw_parse([M007, lst2], ['NAME_A', 'NAME_B'])
    assert r == (None, {'NAME_A': sorted([[IDA, 1000000], [IDA[:-1] + '3', 7]]), 'NAME_B': [[IDA[:-1] + '2', 9]]}), r


def t_d4_swapped_elements_assigned_by_title():
    """D4 (SD-61, W88): copies are assigned by exact title, never by the element's position."""
    b = copy.deepcopy(M007)
    b['structuredContent']['results'][0].update(title='NAME_B', id=IDA[:-1] + '9', size='5')
    assert raw_parse([b, M007], ['NAME_A', 'NAME_B']) == (None, {'NAME_A': [[IDA, 1000000]],
                                                                 'NAME_B': [[IDA[:-1] + '9', 5]]})
    assert raw_parse([EMPTY, M007], ['NAME_A', 'NAME_B'])[1]['NAME_A'] == [[IDA, 1000000]]


def _loop(root, n=2):
    files = []
    for i in range(n):
        p = root / ('f%d' % i)
        p.write_bytes(b'invented bytes %d' % i * 50)
        files.append((p, 'CPS/setup', 'NAME_%d' % i))
    return savepoint.setup_loop(files)



def t_d11_on_found_handback_and_absent():
    """D11a (on_found): with two refused names absent, the UPLOAD_REFUSED handback names the first; the rebase absence
    list is emptied by the first on_found of the entry, so a later block never FINDs those names again."""
    root = tmpdir('onfound')
    lp = _loop(root, 2)
    savepoint.block(lp, 1 << 20, 20, 'CPS/setup')
    r = savepoint.on_found(lp, {'NAME_0': [], 'NAME_1': []}, {'NAME_0', 'NAME_1'}, lambda n: (), str(root))
    assert r == ('handback', 'NAME_0'), r
    (root / 'e').write_bytes(b'entry')
    loop = {'entry': {'name': 'E', 'path': str(root / 'e'), 'folder': 'CPS/drills/D1', 'sha256': 'a' * 64,
                      'md5': 'b' * 32, 'bytes': 5, 'copies': None}, 'parts': [], 'tries': savepoint._tries(['E']),
            'verify': [], 'absent': ['P_GONE'], 'slips': 0}
    savepoint.block(loop, 1 << 20, 20, 'CPS/drills/D1')
    assert savepoint.on_found(loop, {'E': [], 'P_GONE': []}, set(), lambda n: (), str(root)) == ('ok', None)
    assert loop['absent'] == [], loop['absent']

def t_d3_fourth_slip_stops_slip_limit():
    """D3a (W23): the slips of one loop are counted; the fourth is SLIP_LIMIT; a slip forgets the pending downloads
    and FINDs again."""
    root = tmpdir('slips')
    lp, vd = _loop(root), root / 'verify'
    vd.mkdir()
    a = lp['parts'][0]
    savepoint.block(lp, 10 ** 9, 0, None)
    assert savepoint.on_found(lp, {'NAME_0': [['idA', a['bytes']]], 'NAME_1': [['idB', 9]]}, set(), lambda n: (),
                              str(vd))[0] == 'ok'
    assert savepoint.on_verify(lp) == ('slip', 'DOWNLOAD_MISSING', 'NAME_0')
    for k in range(3):
        assert savepoint.slip(lp, 'NAME_0', 'DOWNLOAD_MISSING') is None and lp['slips'] == k + 1
        assert not lp['verify'] and all(t['need'] == 'find' for t in lp['tries'].values())
    assert savepoint.slip(lp, 'NAME_0', 'DOWNLOAD_MISSING') == 'SLIP_LIMIT'


def t_s03_short_download_refinds_real_fork_keeps_bytes():
    """S-03: a download shorter than the attested size is a slip (DOWNLOAD_INCOMPLETE); a download of the attested
    size with other bytes is FORK and its file is kept; our other file's bytes at this name are COPY_MISMATCH."""
    root = tmpdir('s03')
    lp, vd = _loop(root), root / 'verify'
    vd.mkdir()
    a = lp['parts'][0]
    savepoint.block(lp, 10 ** 9, 0, None)
    savepoint.on_found(lp, {'NAME_0': [['idA', a['bytes']]], 'NAME_1': []}, set(), lambda n: (), str(vd))
    Path(lp['verify'][0]['path']).write_bytes(b'x' * (a['bytes'] - 1))
    assert savepoint.on_verify(lp) == ('slip', 'DOWNLOAD_INCOMPLETE', 'NAME_0')
    Path(lp['verify'][0]['path']).write_bytes(b'x' * (a['bytes'] + 1))
    assert savepoint.on_verify(lp) == ('slip', 'DOWNLOAD_INCOMPLETE', 'NAME_0'), 'longer is a slip too'
    Path(lp['verify'][0]['path']).write_bytes(b'y' * a['bytes'])
    assert savepoint.on_verify(lp) == ('stop', 'FORK', None) and os.path.isfile(lp['verify'][0]['path'])
    lp2 = _loop(root)
    savepoint.block(lp2, 10 ** 9, 0, None)
    savepoint.on_found(lp2, {'NAME_0': [['idA', lp2['parts'][1]['bytes']]], 'NAME_1': []}, set(), lambda n: (),
                       str(vd))
    shutil.copyfile(lp2['parts'][1]['path'], lp2['verify'][0]['path'])
    assert savepoint.on_verify(lp2) == ('slip', 'COPY_MISMATCH', 'NAME_0')


def t_commit_identical_parts_confirmed():
    """BUG found by T (v2.1 build): two files of one loop with identical bytes (two all-zero tar padding parts) are each
    confirmed by their own download; COPY_MISMATCH needs a download that is not its own file's bytes."""
    root = tmpdir('ident')
    files = []
    for i in range(2):
        p = root / ('z%d' % i)
        p.write_bytes(b'\0' * 4096)
        files.append((p, 'CPS/setup', 'Z_%d' % i))
    lp, vd = savepoint.setup_loop(files), root / 'verify'
    vd.mkdir()
    savepoint.block(lp, 10 ** 9, 0, None)
    savepoint.on_found(lp, {'Z_0': [['idZ0', 4096]], 'Z_1': [['idZ1', 4096]]}, set(), lambda n: (), str(vd))
    for v in lp['verify']:
        Path(v['path']).write_bytes(b'\0' * 4096)
    assert savepoint.on_verify(lp) == ('ok', None) and savepoint.block(lp, 10 ** 9, 0, None) is None


def t_op02_reprint_has_no_upload_lines():
    """SD-60 (W86): a reprinted block carries no UPLOAD line and changes no try."""
    lp = _loop(tmpdir('op02'))
    ups = savepoint.block(lp, 10 ** 9, 0, None, reprint=True)[0]
    assert ups == () and all(t['need'] == 'upload' and t['uploads'] == 0 for t in lp['tries'].values())
    assert len(savepoint.block(lp, 10 ** 9, 0, None)[0]) == 2
    assert all(t['uploads'] == 1 for t in lp['tries'].values())
    t0 = sorted(lp['tries'])[0]                                     # a name waiting for its second FIND (lag)
    lp['tries'][t0]['need'] = 'wait'
    assert savepoint.block(lp, 10 ** 9, 0, None, reprint=True)[3][0] == 'ATTEST_FOUND'   # GM-savepoint-block-4
    assert lp['tries'][t0]['need'] == 'wait' and savepoint.block(lp, 10 ** 9, 0, None)[3][0] == 'WAIT'


def t_opx01_restore_work_writes_kept():
    """OPX-01 (W17): write_doc sets self_sha256 in place and returns the same dict, so no alias goes stale."""
    d = {'schema': 'x', 'a': 1}
    p = tmpdir('opx01') / 'D.json'
    r = durable.write_doc(p, d)
    assert r is d and 'self_sha256' in d
    alias = d
    alias['a'] = 2
    durable.write_doc(p, d)
    assert json.loads(p.read_text())['a'] == 2 and durable.read_doc(p, 'x', json.loads)[1] is None


def t_s05_png_changed_before_part_write_halts():
    """S-05 (W09): a PNG whose bytes changed after the snapshot, or a stream whose whole sha256 is not the entry's,
    halts PNG_MANIFEST_UNSAFE before PENDING, and the written parts are removed."""
    root = tmpdir('s05')
    jd = root / 'job'
    (jd / 'qa').mkdir(parents=True)
    (jd / 'qa/p.png').write_bytes(b'png-bytes' * 100)

    class Env:
        journal = root / 'journal'
        cfg = {'png_part_bytes': 10 ** 6}
        series_folder = 'CPS/drills/D1'
    Env.journal.mkdir()
    for files, whole in (([['job/qa/p.png', 0o644, 900, sha(b'other' * 180)]], 'f' * 64),
                         ([['job/qa/p.png', 0o644, 900, sha(b'png-bytes' * 100)]], 'f' * 64)):
        expect_halt('PNG_MANIFEST_UNSAFE', savepoint._png_parts, Env, 'D1', 2,
                    {'job_dir': str(jd), 'rels': ['qa/p.png'], 'files': files, 'run': 'A/c'}, whole)
        assert not list(Env.journal.iterdir()), 'the written parts are removed'


def t_t6_finish_refuses_entry_that_is_not_pending():
    """T6 (N37): finish() installs nothing when the local entry file is not the pending one (another valid entry put
    in its place): INTERNAL_ILLEGAL_TRANSITION, PENDING kept, no STATE written."""
    root = tmpdir('t6')
    env, drv = SPEnv(root), FakeDrive()
    pend, entry, _, _ = write_png_commit(env, make_job(root, pngs=0))
    r2 = tmpdir('t6b')
    env2 = SPEnv(r2)
    def other(e):
        fake_complete(e)
        e['state']['note'] = 'another entry'
        e['state_sha256'] = N.sha(N.cjson(e['state']))
        return e
    members = place.snapshot(env2.lay, str(make_job(r2, pngs=0)))[0]
    p2 = savepoint.write_commit(env2, dict(sp_draft(1), payload_png=None), members, [], [], other)[0]
    os.environ['CPS_VM_BASE'] = str(root / 'base')
    drive_pending(env, drv, pend)
    shutil.copyfile(p2['entry']['path'], pend['entry']['path'])
    expect_halt('INTERNAL_ILLEGAL_TRANSITION', savepoint.finish, env, {}, pend)
    assert (env.v2 / 'PENDING.json').exists() and not (env.v2 / 'STATE.json').exists()


def t_t9_empty_transcript_refused():
    """T9 (N44): an exported transcript of 0 bytes is TRANSCRIPT_FILE_MISSING; over the limit TRANSCRIPT_TOO_LARGE."""
    from types import SimpleNamespace
    d = tmpdir('t9')
    env = SimpleNamespace(cfg={'max_transcript_bytes': 10})
    (d / 'e.json').write_bytes(b'')
    (d / 'ok.json').write_bytes(b'{}')
    (d / 'big.json').write_bytes(b'x' * 11)
    assert cli.transcript_problem(env, str(d / 'e.json')) == 'TRANSCRIPT_FILE_MISSING'
    assert cli.transcript_problem(env, str(d / 'none.json')) == 'TRANSCRIPT_FILE_MISSING'
    assert cli.transcript_problem(env, str(d / 'big.json')) == 'TRANSCRIPT_TOO_LARGE'
    assert cli.transcript_problem(env, str(d / 'ok.json')) is None


def t_opx09_refused_stop_names_the_file():
    """OPX-09 (c) (W25): STOP UPLOAD_REFUSED HANDBACK A names the refused file."""
    t = drive.do_text(('STOP', {'code': 'UPLOAD_REFUSED', 'handback': 'A', 'name': 'CPSJ_D1_000002.tgz'}), '/x/vm.sh')
    assert t == 'STOP UPLOAD_REFUSED HANDBACK A name=CPSJ_D1_000002.tgz'
    assert drive.check_grammar(['CPSV series=D1 head=000001 kit=0123456789ab at=000001-0001-abcdef mode=drill '
                                'state=STOP', 'DO: ' + t]) is None


def t_maint2_tools_none_refused_inventory_file_accepted():
    """MAINT-2 (W31): tools= takes inventory or file:<abs path>; none (M006: tools are always present) and a list are
    refused; the tool list format is checked."""
    cfg = {'doc_samples': []}
    assert N.check_value('tools', 'TOOLS', 'none', cfg) == ('VALUE_PATTERN', 'tools')
    assert N.check_value('tools', 'TOOLS', 'web,files', cfg) == ('VALUE_PATTERN', 'tools')
    assert N.check_value('tools', 'TOOLS', 'inventory', cfg) is None
    assert N.check_value('tools', 'TOOLS', 'file:/tmp/cps/attest/tools.txt', cfg) is None
    assert N.check_value('tools', 'TOOLS', 'file:attest/tools.txt', cfg) == ('VALUE_PATTERN', 'tools')
    assert N.tool_list(b'a\nb\n') == ['a', 'b']
    for bad in (b'', b'a', b'a\na\n', b' a\n', b'a\x01\n', b'\xff\n', b'\n', b'a\n\nb\n', ('x' * 201 + '\n').encode()):
        assert N.tool_list(bad) is None, bad
    assert N.tool_list(('x\n' * 1) .encode()) == ['x']
    assert '%s' in N.O63_NOTE and N.O63_REPORT.startswith('Isolation of the generator')
    assert N.fm(N.O63_NOTE_RE, N.O63_NOTE % ('a' * 64)) and not N.fm(N.O63_NOTE_RE, N.O63_NOTE % 'x')


def t_int_r2_03_interrupt_gets_conversation_id():
    """INT-R2-03 (W53): the interrupt command gets the resolution's conversation as --conversation-id."""
    from types import SimpleNamespace
    from cpsvm2 import worker
    from cpsvm2.core import plan as P
    w = CW.World('Q1', jobs=[['case01', 1, None]])
    w.commit(CW.genesis(w))
    w.commit(dict(CW.moves(w))['PREPARE_GENERATE']())
    run, rk, ro = CW.open_role(w.state)
    w.commit(CW._restore(w, resolve=(run, rk, ro), ans={'ended': True, 'files_found': False,
                                                         'transcript': 'not_available', 'outcome': 'NOTHING_WRITTEN',
                                                         'list_shows_none': None, 'conversation': 'conv-1234abcd'}))
    first, info = P.pending_chain(w.state)
    assert first == 'interrupt'
    root = tmpdir('int03')
    lay = SimpleNamespace(base=root, inbox=root / 'inbox', ledger=root / 'ledger/LEDGER.jsonl')
    env = SimpleNamespace(state=w.state, lay=lay, cache={'operator': {'model': 'gpt-x'}}, release={},
                          mode='qualification', series='Q1')
    argv = worker.Chain(env, {'run': run, 'first': first, 'info': info}).argv('interrupt')
    assert argv[argv.index('--conversation-id') + 1] == 'conv-1234abcd', argv


def t_d5_placement_accepts_equal_or_moves_aside():
    """D5 (§2.4.6, W03, W67): settle keeps a target whose strict walk equals the plan (staging removed), and moves any
    other target aside (a same-size changed file, a mode change), never deleting it."""
    root = tmpdir('settle')
    os.environ.update(HOME=str(root), CPS_VM_BASE=str(root / 'base'))
    lay = Layout()
    (lay.outbox / 'v2').mkdir(parents=True)

    def staged(data, mode=0o644):
        sd = root / ('stage_%d' % len(list(root.glob('stage_*'))))
        sd.mkdir()
        (sd / 'f').write_bytes(data)
        os.chmod(sd / 'f', mode)
        os.chmod(sd, 0o755)
        return sd
    want = {'f': ['file', 0o644, 3, sha(b'abc')]}
    tgt = root / 'target'
    sd = staged(b'abc')
    assert place.settle(lay, tgt, want, 0o755, sd, lambda: os.rename(sd, tgt)) is None and (tgt / 'f').is_file()
    sd = staged(b'abc')
    assert place.settle(lay, tgt, want, 0o755, sd, lambda: os.rename(sd, tgt)) is None and not sd.exists()
    (tgt / 'f').write_bytes(b'abd')                                        # same size, other bytes
    sd = staged(b'abc')
    a1 = place.settle(lay, tgt, want, 0o755, sd, lambda: os.rename(sd, tgt))
    assert a1 and (Path(a1) / 'f').read_bytes() == b'abd' and (tgt / 'f').read_bytes() == b'abc'
    os.chmod(tgt / 'f', 0o600)                                             # a mode change
    sd = staged(b'abc')
    a2 = place.settle(lay, tgt, want, 0o755, sd, lambda: os.rename(sd, tgt))
    assert a2 and a2 != a1 and (tgt / 'f').read_bytes() == b'abc' and os.lstat(tgt / 'f').st_mode & 0o777 == 0o644


def t_d5_settle_root_mode_link_and_file_targets():
    """D5 (§2.4.6, SD-70; GM-place-settle-3/6/7): a target folder whose walk equals the plan but whose own mode differs
    moves aside; a symlink target moves aside without a chmod through the link; a file target moves aside unchanged."""
    root = tmpdir('settle2')
    os.environ.update(HOME=str(root), CPS_VM_BASE=str(root / 'base'))
    lay = Layout()
    (lay.outbox / 'v2').mkdir(parents=True)
    want = {'f': ['file', 0o644, 3, sha(b'abc')]}

    def staged():
        sd = root / ('stage_%d' % len(list(root.glob('stage_*'))))
        sd.mkdir()
        (sd / 'f').write_bytes(b'abc')
        os.chmod(sd / 'f', 0o644)
        os.chmod(sd, 0o755)
        return sd
    tgt = root / 'target'
    sd = staged()
    os.rename(sd, tgt)
    os.chmod(tgt, 0o700)                                                   # equal walk, another root mode
    sd = staged()
    a1 = place.settle(lay, tgt, want, 0o755, sd, lambda: os.rename(sd, tgt))
    assert a1 and os.lstat(a1).st_mode & 0o777 == 0o700 and os.lstat(tgt).st_mode & 0o777 == 0o755
    shutil.rmtree(tgt)
    far = root / 'far'
    far.mkdir()
    os.chmod(far, 0o555)
    os.symlink(far, tgt)                                                   # a link to a read-only folder
    sd = staged()
    a2 = place.settle(lay, tgt, want, 0o755, sd, lambda: os.rename(sd, tgt))
    assert a2 and os.path.islink(a2) and os.lstat(far).st_mode & 0o777 == 0o555 and (tgt / 'f').is_file()
    shutil.rmtree(tgt)
    tgt.write_bytes(b'abc')
    os.chmod(tgt, 0o444)                                                   # a file where the folder belongs
    sd = staged()
    a3 = place.settle(lay, tgt, want, 0o755, sd, lambda: os.rename(sd, tgt))
    assert a3 and os.lstat(a3).st_mode & 0o777 == 0o444 and (tgt / 'f').is_file()


def t_d16_settle_moves_readonly_target_aside():
    """D16 (SD-70, W107; decides in the non-root pass): a target with 0555 folders and 0444 files whose walk differs
    from the staged tree is moved aside to another parent and the staged tree is placed; remove_tree of a 0555 tree
    leaves nothing (W106)."""
    from cpsvm2.vio.v1reuse import remove_tree
    root = tmpdir('d16s')
    os.environ.update(HOME=str(root), CPS_VM_BASE=str(root / 'base'))
    lay = Layout()
    (lay.outbox / 'v2').mkdir(parents=True)
    tgt = root / 'jobs/A/c1'
    (tgt / 'sub').mkdir(parents=True)
    (tgt / 'sub/old.txt').write_bytes(b'old')
    for p in (tgt / 'sub/old.txt',):
        os.chmod(p, 0o444)
    for p in (tgt / 'sub', tgt):
        os.chmod(p, 0o555)
    sd = root / 'jobs/A/.stage'
    sd.mkdir()
    (sd / 'new.txt').write_bytes(b'new')
    os.chmod(sd / 'new.txt', 0o644)
    os.chmod(sd, 0o755)
    a = place.settle(lay, tgt, {'new.txt': ['file', 0o644, 3, sha(b'new')]}, 0o755, sd, lambda: os.rename(sd, tgt))
    assert a and (Path(a) / 'sub/old.txt').read_bytes() == b'old' and (tgt / 'new.txt').read_bytes() == b'new'
    ro = root / 'ro'
    (ro / 'd').mkdir(parents=True)
    (ro / 'd/f').write_bytes(b'x')
    os.chmod(ro / 'd/f', 0o444)
    os.chmod(ro / 'd', 0o555)
    os.chmod(ro, 0o555)
    remove_tree(ro)
    assert not os.path.lexists(ro)
    remove_tree(a)
    assert not os.path.lexists(a)


def t_s07_runner_loaded_from_hashed_bytes():
    """S-07 (W12): load_runner compiles the hashed bytes of deploy/run/cps_job.py into a fresh module; a planted .pyc
    with a valid header for that source (in deploy/run/__pycache__) is never used."""
    import importlib.util
    import importlib._bootstrap_external as be
    from cpsvm2.vio import v1compat
    src = Path(VM2).parent / 'run' / 'cps_job.py'
    pyc = Path(importlib.util.cache_from_source(str(src)))
    planted = not pyc.exists()
    st = os.stat(src)
    code = compile('PLANTED_BYTECODE = True\n', str(src), 'exec')
    try:
        pyc.parent.mkdir(exist_ok=True)
        pyc.write_bytes(bytes(be._code_to_timestamp_pyc(code, st.st_mtime, st.st_size)))
        v1compat.CJ = None
        m = runner.load_runner()
        assert not hasattr(m, 'PLANTED_BYTECODE') and hasattr(m, 'Ledger'), 'the planted bytecode was used'
        assert m.__file__ == str(src) and getattr(m, '__spec__', None) is None or m.__spec__.origin is None
    finally:
        if planted:
            os.unlink(pyc)
            try:
                pyc.parent.rmdir()
            except OSError:
                pass
        v1compat.CJ = None


# ---------------------------------------------------------------- v2.1 rows on fakes.World (FakeDot, FakeDrive)
def fworld(**kw):
    import fakes
    kw.setdefault('series', 'E1')
    kw.setdefault('cases', ())
    return fakes.World(tempfile.mkdtemp(prefix='fw_', dir=WORK), **kw)


@contextlib.contextmanager
def fw(**kw):
    w = fworld(**kw)
    try:
        yield w
    finally:
        w.destroy()


def until(w, code, lines, pred):
    w.dot.hook = lambda dot, ls: 'stop' if ls and pred(ls) else None
    try:
        return w.dot.run(code, lines)
    finally:
        w.dot.hook = None


def to_idle(w):
    """Bootstrap, then the blocks to the first IDLE question (GENESIS committed)."""
    w.start()
    code, lines = until(w, *w.dot.cmd('go'), lambda ls: 'case=CASE_ID' in ls[-1])
    assert 'case=CASE_ID' in lines[-1], lines
    return code, lines


def fat(lines):
    return lines[0].split(' at=')[1].split(' ')[0]


def fv2(w):
    return w.base / 'outbox/v2'


def fdoc(w, name):
    return json.loads((fv2(w) / name).read_text())


def fcache(w):
    return {p.name: p.read_bytes() for p in fv2(w).glob('*.json')}


def fentry(w, seq):
    n = N.entry_name(w.series, seq)
    p = w.fixed / ('.e_' + n)
    p.write_bytes(w.drive.bytes_of(N.series_folder(w.series), n))
    try:
        return savepoint.read_entry(p)
    finally:
        os.unlink(p)


def slip_world(kind, pick):
    """A World to IDLE whose FakeDot slips once (kind) at the found/download of the block `pick(lines)` selects."""
    w = fworld()
    w.start()
    seen = {'done': False}

    def hook(dot, ls):
        if ls and not seen['done'] and pick(ls):
            seen['done'] = True
            n = dot.n_download + 1 if kind in ('short_download', 'missing') else dot.n_found + 1
            dot.policy['slips'].append([kind, n])
        return 'stop' if ls and 'case=CASE_ID' in ls[-1] else None
    w.dot.hook = hook
    code, lines = w.dot.run(*w.dot.cmd('go'))
    w.dot.hook = None
    return w, code, lines


def genesis_save(ls):
    return any(x.startswith('FIND ') and N.entry_name('E1', 1) in x for x in ls) and 'state=SAVE' in ls[0]


def refused_then_find(w, code):
    """The REFUSED <slip> line, then the same name's FIND block without UPLOAD lines (re-FIND, D3a)."""
    hits = [b for b in w.dot.blocks if len(b['lines']) > 1 and b['lines'][1].startswith('REFUSED ' + code)]
    assert hits, [b['lines'][1:2] for b in w.dot.blocks]
    ls = hits[0]['lines']
    assert hits[0]['code'] == 4 and ls[2].startswith('FIND ') and not any(x.startswith('UPLOAD ') for x in ls), ls
    return hits


def t_opx02_mistyped_id_refinds_then_commits():
    """OPX-02 / S-10 (W18): a found id that downloads as missing is a slip: REFUSED DOWNLOAD_MISSING, the name is FOUND
    again (no DOWNLOAD reprint, no UPLOAD), and the commit completes."""
    w, code, lines = slip_world('wrong_id', genesis_save)
    try:
        assert 'case=CASE_ID' in lines[-1], lines
        refused_then_find(w, 'DOWNLOAD_MISSING')
        assert fdoc(w, 'STATE.json')['head']['seq'] == 1
    finally:
        w.destroy()


def t_opx03_size_slip_refinds():
    """OPX-03 (W19): a found size other than ours is not FORK: the download decides (DOWNLOAD_INCOMPLETE), then the
    name is FOUND again and the commit completes."""
    w, code, lines = slip_world('size', genesis_save)
    try:
        assert 'case=CASE_ID' in lines[-1], lines
        refused_then_find(w, 'DOWNLOAD_INCOMPLETE')
    finally:
        w.destroy()


def t_t8_session_download_missing_refinds():
    """T8 (N42): a session DOWNLOAD (here the kit) answered `go` without the file is a slip: REFUSED DOWNLOAD_MISSING
    and a re-FIND of that name; the restore then goes on."""
    w, code, lines = slip_world('missing', lambda ls: any(x.startswith('DOWNLOAD ') and 'SESSION_KIT_' in x
                                                          for x in ls))
    try:
        assert 'case=CASE_ID' in lines[-1], lines
        hits = refused_then_find(w, 'DOWNLOAD_MISSING')
        assert 'SESSION_KIT_' in hits[0]['lines'][1] and 'SESSION_KIT_' in hits[0]['lines'][2]
    finally:
        w.destroy()


def t_d11_session_slip_voids_only_its_name():
    """D3a (§2.2.1; GM-cli-session_slip-1/2): a restore's slip at a fetch DOWNLOAD (the FINGERPRINT_PASS) voids only
    that name: the journal lookups stay as they were and `verified` keeps every other id; `fetched` forgets the name."""
    with fw() as w:
        to_idle(w)
        w.dot.reset()
        seen = {}

        def hook(dot, ls):
            if not ls:
                return None
            if 'before' not in seen and any(x.startswith('DOWNLOAD ') and 'FINGERPRINT_PASS_' in x for x in ls):
                seen['before'] = fdoc(w, 'RESTORE_WORK.json')
                seen['name'] = [x for x in ls if x.startswith('DOWNLOAD ')][0].split('/')[-1].rsplit('.', 1)[0]
                dot.policy['slips'].append(['missing', dot.n_download + 1])
            return 'stop' if len(ls) > 1 and ls[1].startswith('REFUSED DOWNLOAD_MISSING') else None
        w.dot.hook = hook
        try:
            code, lines = w.dot.run(*w.dot.cmd('go'))
        finally:
            w.dot.hook = None
        assert code == 4 and lines[1].startswith('REFUSED DOWNLOAD_MISSING FINGERPRINT_PASS_'), lines
        b, a = seen['before'], fdoc(w, 'RESTORE_WORK.json')
        assert b['verified'] and b['lookups'] and a['verified'] == b['verified'], (b['verified'], a['verified'])
        assert a['lookups'] == b['lookups'] and not any(lk.get('void') for lk in a['lookups']), a['lookups']
        assert a['slips'] == b['slips'] + 1 and not any(k.startswith('FINGERPRINT_PASS_') for k in a['fetched'])


def t_d11_head_download_slips_and_no_block():
    """D3a (§2.2.1; GM-cli-session_downloads-0/1/2, GM-cli-do_found-0, GM-cli-do_answer-0): a restore's HEAD download
    of entry N that is missing is REFUSED DOWNLOAD_MISSING, a short one DOWNLOAD_INCOMPLETE, each followed by the
    name's FIND; a `found` or `answer` with no BLOCK.json is a bare REFUSED STALE_AT."""
    name = N.entry_name('E1', 1)
    for kind, code in (('missing', 'DOWNLOAD_MISSING'), ('short_download', 'DOWNLOAD_INCOMPLETE')):
        with fw() as w:
            to_idle(w)
            w.dot.reset()
            seen = {}

            def hook(dot, ls):
                if ls and 'slip' not in seen and any(x.startswith('DOWNLOAD ') and name in x for x in ls):
                    seen['slip'] = True
                    dot.policy['slips'].append([kind, dot.n_download + 1])
                done = 'slip' in seen and ls and ('case=CASE_ID' in ls[-1] or ls[-1].startswith('DO: STOP'))
                return 'stop' if len(ls) > 1 and ls[1].startswith('REFUSED ') or done else None
            w.dot.hook = hook
            try:
                c, lines = w.dot.run(*w.dot.cmd('go'))
            finally:
                w.dot.hook = None
            assert c == 4 and lines[1] == 'REFUSED %s %s' % (code, name) and lines[2].startswith('FIND ') and \
                name in lines[2], lines
    with fw() as w:
        to_idle(w)
        os.unlink(fv2(w) / 'BLOCK.json')
        for argv in (('found', '--at', '000001-0001-000000', '--name', name, '--none'),
                     ('answer', '--at', '000001-0001-000000', 'case=case01')):
            c, out = w.dot.cmd(*argv)
            assert c == 4 and out == ['REFUSED STALE_AT'], (argv, out)


def t_d11_link_copy_download_keeps_the_head():
    """§8.4 step 4, rule V (GM-cli-session_downloads-4/5): a restore whose N-1 has a second copy with our bytes
    downloads that copy into inbox/verify, keeps entry N as the head and goes on (here to the committed HALT's stop);
    the downloaded copy stays under its numbered name."""
    from cpsvm2.vio.v1compat import Halt as H
    with fw() as w:
        to_idle(w)
        real = cli.go_checks

        def boom(env):
            raise H('STOP', 'UNCLASSIFIED', 'invented')
        cli.go_checks = boom
        try:
            code, out = w.dot.cmd('go')
        finally:
            cli.go_checks = real
        code, out = w.dot.run(code, out)
        assert fentry(w, 2)['kind'] == 'HALT', out
        folder, n1 = N.series_folder('E1'), N.entry_name('E1', 1)
        w.drive.plant(folder, n1, w.drive.bytes_of(folder, n1))
        w.dot.reset()
        seen = {}

        def hook(dot, ls):
            if ls and any(x.startswith('DOWNLOAD ') and '/inbox/verify/' + n1 in x for x in ls):
                seen['dl'] = [x.split(' TO ')[1] for x in ls if x.startswith('DOWNLOAD ')]
            if ls and any(x.startswith('FIND ') and 'FINGERPRINT_PASS_' in x for x in ls):
                seen['files'] = sorted(p.name for p in (w.base / 'inbox/verify').iterdir())
                seen['head'] = fdoc(w, 'RESTORE_WORK.json')['head']['entry']['seq']
            return None
        w.dot.hook = hook
        try:
            code, out = w.dot.run(*w.dot.cmd('go'))
        finally:
            w.dot.hook = None
        assert out[-1] == 'DO: STOP HALTED_UNCLASSIFIED HANDBACK C', out
        assert seen.get('dl') and seen['head'] == 2 and seen['files'] == sorted(os.path.basename(p) for p in
                                                                                 seen['dl']), seen


def t_d11_local_download_checked_at_go():
    """§5.1, D3 (GM-cli-go_checks-12..15): a `local` DOWNLOAD block (ensure_local, a journal file the next step needs)
    answered with the file in place goes on; answered without it is REFUSED DOWNLOAD_MISSING with the same block again
    (no re-FIND: the id is a confirmed one)."""
    name = N.entry_name('E1', 1)
    for done in (True, False):
        with fw() as w:
            code, idle = to_idle(w)
            real = cli.go_checks

            def once(env):                          # as after DROP_LOCAL: the confirmed entry is not local
                cli.go_checks = real
                if (env.lay.inbox / 'journal' / name).exists():
                    os.unlink(env.lay.inbox / 'journal' / name)
                cli.ensure_local(env, [name], 'WORK')
            cli.go_checks = once
            try:
                code, lines = w.dot.cmd('go')
            finally:
                cli.go_checks = real
            dl = [x for x in lines if x.startswith('DOWNLOAD ')]
            assert code == 0 and len(dl) == 1 and dl[0].endswith('/inbox/journal/' + name), lines
            if done:
                code, out = w.dot.execute(lines)
                assert code == 0 and 'case=CASE_ID' in out[-1] and (w.base / 'inbox/journal' / name).is_file(), out
            else:
                code, out = w.dot.cmd('go')
                assert code == 4 and out[1] == 'REFUSED DOWNLOAD_MISSING' and [x for x in out if x.startswith(
                    'DOWNLOAD ')] == dl, out


def t_d11_session_download_names_kept():
    """§8.4 (session_downloads; GM-cli-session_downloads-5/6/7): after the HEAD phase's check, a journal copy 1 is kept
    as inbox/journal/<name> unless that file exists; any other copy, and every inbox/verify copy, keeps its numbered
    name (FORK evidence until DROP_DOWNLOADS). Each downloaded id is hashed into `verified`."""
    with fw() as w:
        to_idle(w)
        real, got = cli.go_checks, {}

        def direct(env):
            cli.go_checks = real
            env.work['head'] = env.work.get('head') or {'entry': None}          # the head N is verified already
            j, v = env.lay.inbox / 'journal', env.lay.inbox / 'verify'
            for d in (j, v):
                d.mkdir(parents=True, exist_ok=True)
            files = {j / 'P1.1': b'one', j / 'P2.2': b'two', j / 'P3.1': b'new', j / 'P3': b'old', v / 'P4.1': b'v'}
            for p, b in files.items():
                p.write_bytes(b)
            dls = [('F', 'id%d' % k, str(p)) for k, p in enumerate(files) if p.name != 'P3']
            cli.session_downloads(env, 'HEAD', dls, {d[2]: [os.path.basename(d[2])[:2], 3 if 'P4' not in d[2] else 1]
                                                     for d in dls})
            got['names'] = sorted('%s/%s' % (p.parent.name, p.name) for d in (j, v) for p in d.glob('P*'))
            got['old'] = (j / 'P3').read_bytes()
            got['verified'] = sorted(env.work['verified'])
            raise cli.Out(0)
        cli.go_checks = direct
        try:
            w.dot.cmd('go')
        finally:
            cli.go_checks = real
        assert got['names'] == ['journal/P1', 'journal/P2.2', 'journal/P3', 'journal/P3.1', 'verify/P4.1'], got
        assert got['old'] == b'old' and got['verified'] == ['id0', 'id1', 'id2', 'id4'], got


def t_d11_drill_genesis_refuses_existing_ledger():
    """§8.7 genesis (Q, D): a BASE/ledger that already exists is STOP PLACE_TARGET_NOT_EMPTY before the GENESIS is
    committed (nothing is written to Drive's journal folder)."""
    with fw(series='D1', cases=(('9990101', 'small'), ('9990102', 'nonattempt'))) as w:
        w.start()
        (w.base / 'ledger').mkdir(parents=True, exist_ok=True)
        code, out = w.dot.run(*w.dot.cmd('go'))
        assert code == 3 and out[-1] == 'DO: STOP PLACE_TARGET_NOT_EMPTY HANDBACK C', out
        assert not w.drive.has(N.series_folder('D1'), N.entry_name('D1', 1))


def t_d3_refusals_bounded_then_slip_limit():
    """D3b (W22): three refusals of one block are re-asked with the reason; the fourth is STOP SLIP_LIMIT (local
    sticky), HALT.json with the journal's head and kit, which the STOP header shows (OPX-07)."""
    with fw() as w:
        code, idle = to_idle(w)
        for k in range(3):
            code, out = w.dot.cmd('answer', '--at', fat(idle), 'case=bad case')
            assert code == 4 and out[1] == 'REFUSED VALUE_FORBIDDEN case', out
        assert fdoc(w, 'BLOCK.json')['refused'] == 3
        code, out = w.dot.cmd('answer', '--at', fat(idle), 'case=bad case')
        assert code == 3 and out[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C', out
        h = fdoc(w, 'HALT.json')
        assert h['detail'] == {'last': 'VALUE_FORBIDDEN'} and h['head_seq'] == 1 and h['kit_sha256'], h
        hdr = dict(x.split('=', 1) for x in out[0].split()[1:])
        assert hdr['head'] == '000001' and hdr['kit'] == h['kit_sha256'][:12]
        assert fdoc(w, 'STATE.json')['halt_local'] == {'code': 'SLIP_LIMIT', 'head_seq': 1}
        code, out = w.dot.cmd('go')
        assert out[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C', 'sticky'


def t_d3_refused_count_resets_per_block():
    """D3b (W68): the count belongs to one block: three refusals, an accepted answer, and the next block's three
    refusals never reach SLIP_LIMIT."""
    with fw() as w:
        code, idle = to_idle(w)
        for k in range(3):
            assert w.dot.cmd('answer', '--at', fat(idle), 'case=bad case')[0] == 4
        w.everyday_request()
        code, save = w.dot.cmd('answer', '--at', fat(idle), 'case=%s' % w.everyday[-1])
        assert code == 0 and 'state=SAVE' in save[0], save
        assert fdoc(w, 'BLOCK.json')['refused'] == 0
        for k in range(3):
            code, out = w.dot.cmd('answer', '--at', fat(save), 'x=y')
            assert code == 4 and out[1] == 'REFUSED COMMAND_NOT_EXPECTED', out
        assert fdoc(w, 'BLOCK.json')['refused'] == 3 and not (fv2(w) / 'HALT.json').exists()


def t_d4_raw_invalid_reasked():
    """D4 + D3b: an invalid raw file is REFUSED RAW_INVALID <detail> and the block is asked again (counted); the
    manual form stays the fallback."""
    with fw() as w:
        w.start()
        code, lines = until(w, *w.dot.cmd('go'), lambda ls: ' found --at ' in ls[-1])
        bad = w.base / 'attest' / 'bad.json'
        bad.parent.mkdir(parents=True, exist_ok=True)
        for content, why in ((b'{not json', 'json'), (json.dumps([]).encode(), 'count')):
            bad.write_bytes(content)
            code, out = w.dot.cmd('found', '--at', fat(lines), '--raw', str(bad))
            assert code == 4 and out[1] == 'REFUSED RAW_INVALID ' + why and out[2:] == [
                x for x in lines[1:] if not x.startswith('UPLOAD ')], out
        code, out = w.dot.cmd('found', '--at', fat(lines), '--raw', 'relative.json')
        assert code == 4 and out[1] == 'REFUSED RAW_INVALID missing', out
        assert fdoc(w, 'BLOCK.json')['refused'] == 3
        w.dot.policy['found'] = 'manual'
        code, lines = until(w, *w.dot.execute(lines), lambda ls: 'case=CASE_ID' in ls[-1])
        assert 'case=CASE_ID' in lines[-1], lines



def t_d11_found_raw_path_rules():
    """D11a (do_found): --raw takes an absolute path of a regular file only: a symlink to a file, a directory and an
    existing file named by a relative path are each REFUSED RAW_INVALID missing (before the content is read)."""
    with fw() as w:
        w.start()
        code, lines = until(w, *w.dot.cmd('go'), lambda ls: ' found --at ' in ls[-1])
        d = w.base / 'attest'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'raw.json').write_text('{}')
        os.symlink(d / 'raw.json', d / 'raw_link.json')
        (d / 'raw_dir').mkdir()
        for arg in (str(d / 'raw_link.json'), str(d / 'raw_dir'), os.path.relpath(d / 'raw.json')):
            code, out = w.dot.cmd('found', '--at', fat(lines), '--raw', arg)
            assert code == 4 and out[1] == 'REFUSED RAW_INVALID missing', (arg, out)

def t_op03_raw_file_consumed():
    """SD-61 (W87): an accepted raw file is moved into outbox/v2/raw/ (never read twice)."""
    with fw() as w:
        to_idle(w)
        assert w.dot.n_raw > 0 and not list((w.base / 'attest').glob('raw_*.json'))
        assert len(list((fv2(w) / 'raw').glob('*.json'))) == w.dot.n_raw


def t_d4_found_raw_world_swapped():
    """D4 (W88) through the cli: a raw file whose elements are in the other order still gives every name its copies."""
    with fw() as w:
        w.dot.policy['slips'] = [['swapped_raw', k] for k in range(1, 40)]
        code, lines = to_idle(w)
        assert 'case=CASE_ID' in lines[-1]


def t_s09_download_parent_exists_when_printed():
    """S-09 (W14): render creates the folder of every DOWNLOAD target before the block is printed (FakeDot asserts it
    on every download; here the verify folder is removed first)."""
    with fw() as w:
        code, idle = to_idle(w)
        shutil.rmtree(w.base / 'inbox/verify', ignore_errors=True)
        w.everyday_request()
        code, save = w.dot.cmd('answer', '--at', fat(idle), 'case=%s' % w.everyday[-1])
        code, dl = until(w, code, save, lambda ls: any(x.startswith('DOWNLOAD ') for x in ls))
        t = Path(shlex.split([x for x in dl if x.startswith('DOWNLOAD ')][0])[5])
        assert t.parent.is_dir() and not t.exists()


def t_gap08_render_removes_stale_download_target():
    """GAP-08 (W82): a file already at a DOWNLOAD target is removed before the block is printed."""
    with fw() as w:
        code, idle = to_idle(w)
        target = w.base / 'inbox/verify' / (N.entry_name('E1', 2) + '.1')
        w.everyday_request()
        code, save = w.dot.cmd('answer', '--at', fat(idle), 'case=%s' % w.everyday[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'stale bytes from before')
        code, dl = until(w, code, save, lambda ls: any(x.startswith('DOWNLOAD ') for x in ls))
        assert any(str(target) in x for x in dl), dl
        assert not target.exists(), 'the stale file is not taken as the download'


def t_maint2_inventory_sha_checked():
    """MAINT-2 (W71): a kit whose TOOL_INVENTORY.txt is not the one its config pins is CONFIG_INVALID."""
    with fw(cfg={'tool_inventory_sha256': '0' * 64}) as w:
        w.start()
        code, lines = w.dot.run(*w.dot.cmd('go'))
        assert lines[-1] == 'DO: STOP CONFIG_INVALID HANDBACK C', lines


def t_maint2_inventory_rehashed_at_attest():
    """MAINT-2 (W71): tools=inventory hashes the installed TOOL_INVENTORY.txt again: a file changed after the kit was
    taken in is CONFIG_INVALID at the attestation."""
    with fw() as w:
        code, ask = to_g_end(w)
        (w.base / 'attest/final_message.txt').write_text('done')
        inv = w.base / 'runtime/TOOL_INVENTORY.txt'
        os.chmod(inv, 0o644)                        # installed read-only; the change stands for one made anyway
        inv.write_bytes(b'invented_other_tool\n')
        code, out = w.dot.cmd(*g_args(w, ask, tools='inventory'))
        assert out[-1] == 'DO: STOP CONFIG_INVALID HANDBACK C', out


def t_opx07_stage_death_stop_names_real_head_and_kit():
    """OPX-07 (W16, W50): this boot's FOREGROUND.json found by the next command (the stage died): FOREGROUND.json moves
    to dead_<utc14>.json, STOP FOREGROUND_DIED with the journal's head and kit in the header and in HALT.json, and the
    cache (STATE.json) is kept."""
    with fw() as w:
        code, idle = to_idle(w)
        st0 = (fv2(w) / 'STATE.json').read_bytes()
        durable.write_doc(fv2(w) / 'FOREGROUND.json', {'schema': cli.FG_SCHEMA, 'boot_id': w.boot, 'kind': 'chain',
                                                       'attempt': 1, 'pid': 1, 'started_utc': '2026-11-10T00:00:00Z'})
        code, out = w.dot.cmd('go')
        assert code == 3 and out[-1] == 'DO: STOP FOREGROUND_DIED HANDBACK C', out
        h = fdoc(w, 'HALT.json')
        hdr = dict(x.split('=', 1) for x in out[0].split()[1:])
        assert h['head_seq'] == 1 and hdr['head'] == '000001' and hdr['kit'] == h['kit_sha256'][:12] != 'none'
        assert list(fv2(w).glob('dead_*.json')) and not (fv2(w) / 'FOREGROUND.json').exists()
        st = json.loads((fv2(w) / 'STATE.json').read_bytes())
        assert st.pop('halt_local') and {k: v for k, v in json.loads(st0).items() if k != 'self_sha256'} == \
            {k: v for k, v in st.items() if k != 'self_sha256'}, 'the cache is kept'


def t_gap05_block_ahead_invalidates_cache():
    """OPX-07 / GAP-05 (W16, W79): a BLOCK.json behind STATE's head moves alone to invalid_<utc14>/ and the cache stays;
    one ahead of it invalidates the cache, and the session restores."""
    with fw() as w:
        code, idle = to_idle(w)
        b = fdoc(w, 'BLOCK.json')
        b.update(head_seq=0)
        durable.write_doc(fv2(w) / 'BLOCK.json', b)
        st0 = (fv2(w) / 'STATE.json').read_bytes()
        w.dot.cmd('go')
        assert (fv2(w) / 'STATE.json').read_bytes() == st0 and list(fv2(w).glob('invalid_*/BLOCK.json'))
        assert not list(fv2(w).glob('invalid_*/STATE.json'))
        b = fdoc(w, 'BLOCK.json')
        b.update(head_seq=5)
        durable.write_doc(fv2(w) / 'BLOCK.json', b)
        code, out = w.dot.cmd('go')
        assert list(fv2(w).glob('invalid_*/STATE.json')), 'ahead: the cache is invalidated'
        code, out = until(w, code, out, lambda ls: 'case=CASE_ID' in ls[-1])
        assert 'case=CASE_ID' in out[-1] and fentry(w, 2)['kind'] == 'RESTORE'


def t_gap12_halt_removed_out_of_procedure_restores():
    """GAP-12 (W85): halt_local in STATE.json without HALT.json (removed out of procedure) invalidates the cache."""
    with fw() as w:
        to_idle(w)
        st = fdoc(w, 'STATE.json')
        st['halt_local'] = {'code': 'FORK', 'head_seq': 1}
        durable.write_doc(fv2(w) / 'STATE.json', st)
        n = len(list(fv2(w).glob('invalid_*')))
        w.dot.cmd('go')
        assert len(list(fv2(w).glob('invalid_*'))) == n + 1


def t_d5_damaged_halt_stops_unclassified():
    """D5 (W101): a damaged HALT.json is never ignored: STOP UNCLASSIFIED, HALT.json rewritten with that code and the
    old file kept as halt_<utc14>.json."""
    with fw() as w:
        to_idle(w)
        (fv2(w) / 'HALT.json').write_text('{"schema": "cps.vm2-halt.v1"}')
        code, out = w.dot.cmd('go')
        assert out[-1] == 'DO: STOP UNCLASSIFIED HANDBACK C' and list(fv2(w).glob('halt_*.json')), out
        assert fdoc(w, 'HALT.json')['code'] == 'UNCLASSIFIED'


def slip_limit_world():
    """A World at IDLE stopped SLIP_LIMIT (four refused answers): (world, HALT.json)."""
    w = fworld()
    code, idle = to_idle(w)
    for k in range(4):
        code, out = w.dot.cmd('answer', '--at', fat(idle), 'case=bad case')
    assert out[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C', out
    return w, fdoc(w, 'HALT.json')


def boot_kit(w, kit12, seq='000001'):
    return w.dot.bootstrap(w.dot.notes['repo'], (seq, kit12))



def split_kit_world():
    """A World at IDLE whose kit in use (STATE.json kit_sha256) differs from the journal's kit (the state's), then
    stopped SLIP_LIMIT: (world, HALT.json, journal kit, kit in use). The fixture stands for a restore that took a kit
    change and stopped in its commit loop (delta v2.1 §2.15.5), without the release kits of that route."""
    w = fworld()
    code, idle = to_idle(w)
    st = fdoc(w, 'STATE.json')
    journal, use = st['state']['kit_sha256'], hashlib.sha256(b'invented kit in use').hexdigest()
    st['kit_sha256'] = use
    durable.write_doc(fv2(w) / 'STATE.json', st)
    (fv2(w) / 'HINT.json').write_text('{"kit": "%s", "seq": 1}\n' % hashlib.sha256(b'a third kit').hexdigest()[:12])
    for k in range(4):
        code, out = w.dot.cmd('answer', '--at', fat(idle), 'case=bad case')
    assert out[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C', out
    return w, fdoc(w, 'HALT.json'), journal, use, out


def t_d5_kit_in_use_never_checks():
    """D5 (W63): the kit in use at the moment of the stop is in `tried`: a bootstrap with it prints the STOP with no
    FIND."""
    w, h, journal, use, out = split_kit_world()
    try:
        assert use[:12] in h['tried'], h
        boot_kit(w, use[:12])
        code, lines = w.dot.cmd('go')
        assert lines[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C' and not any(x.startswith('FIND ') for x in lines), lines
    finally:
        w.destroy()


def t_d5_halted_kit_never_checks():
    """D5 (W97, W102): HALT.json's kit is the journal's (not the kit in use), the STOP header names it, and it is in
    `tried`: a bootstrap with the journal's kit prints the STOP with no FIND."""
    w, h, journal, use, out = split_kit_world()
    try:
        assert h['kit_sha256'] == journal and journal[:12] in h['tried'], h
        assert ' kit=%s ' % journal[:12] in out[0], out
        boot_kit(w, journal[:12])
        code, lines = w.dot.cmd('go')
        assert lines[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C' and not any(x.startswith('FIND ') for x in lines), lines
        assert ' kit=%s ' % journal[:12] in lines[0], lines
    finally:
        w.destroy()

def t_d5_refused_clear_kit_keeps_cache():
    """D5 (W59, W62, W65): a candidate that does not clear this stop (another seq; a null clear) is refused with
    nothing moved: STATE.json, PENDING.json and RESTORE_WORK byte-identical, HALT.json kept with its code and the kit in
    `tried`; the next `go` prints the same STOP with zero Drive calls."""
    w, h = slip_limit_world()
    try:
        bad = w.clear_kit('SLIP_LIMIT', 2)
        null = w.clear_kit('SLIP_LIMIT', 1)
        import fakes
        with zipfile.ZipFile(io.BytesIO(w.drive.bytes_of(N.FOLDERS['setup'], 'SESSION_KIT_%s.zip' % null))) as z:
            mem = {n: z.read(n) for n in z.namelist() if n != 'SHA256SUMS'}
        cfg = json.loads(mem['VM_HELPER_CONFIG.json'])
        cfg['clear'] = None
        cfg['doc_samples'] = cfg['doc_samples'] + ['conv-NULLCLEAR']
        mem['VM_HELPER_CONFIG.json'] = json.dumps(cfg).encode()
        nk = fakes.zip_kit(mem)
        w.drive.plant(N.FOLDERS['setup'], 'SESSION_KIT_%s.zip' % sha(nk)[:12], nk)
        for k12 in (bad, sha(nk)[:12]):
            keep = {k: v for k, v in fcache(w).items() if k in ('STATE.json', 'PENDING.json', 'RESTORE_WORK.json')}
            boot_kit(w, k12)
            code, lines = w.dot.cmd('go')
            assert 'FIND CPS/setup NAME SESSION_KIT_%s.zip' % k12 in lines, lines
            code, lines = w.dot.run(code, lines)
            assert lines[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C', lines
            assert {k: v for k, v in fcache(w).items() if k in keep} == keep, 'a refused kit moves nothing'
            h2 = fdoc(w, 'HALT.json')
            assert k12 in h2['tried'] and h2['code'] == 'SLIP_LIMIT' and h2['check'] is None
            n = len(w.drive.calls)
            code, lines = w.dot.cmd('go')
            assert lines[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C' and len(w.drive.calls) == n, 'zero Drive calls'
            assert not any(x.startswith('FIND ') for x in lines)
    finally:
        w.destroy()


def t_d5_found_answer_while_halted_print_stop():
    """D5 (W64): `found` and `answer` never start the clear check; they print the stop."""
    w, h = slip_limit_world()
    try:
        boot_kit(w, w.clear_kit('SLIP_LIMIT', 1))
        n = len(w.drive.calls)
        for argv in (('answer', '--at', '000001-0001-aaaaaa', 'x=y'), ('found', '--at', '000001-0001-aaaaaa', '--name',
                                                                        'x', '--none')):
            code, lines = w.dot.cmd(*argv)
            assert lines[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C' and not any(x.startswith('FIND ') for x in lines)
        assert fdoc(w, 'HALT.json')['check'] is None and len(w.drive.calls) == n
    finally:
        w.destroy()


def t_d5_stale_hint_never_checks():
    """D5 (W61): the kit HINT.json names at the moment of the stop is in `tried`: it never starts a check."""
    w = fworld()
    try:
        code, idle = to_idle(w)
        (fv2(w) / 'HINT.json').write_text('{"kit": "abcdef012345", "seq": 1}\n')    # session_start.sh's form; a kit
        for k in range(4):
            code, out = w.dot.cmd('answer', '--at', fat(idle), 'case=bad case')
        assert out[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C', out
        h = fdoc(w, 'HALT.json')
        assert 'abcdef012345' in h['tried'] and len(h['tried']) >= 2, h       # neither in use nor the journal's
        code, lines = w.dot.cmd('go')
        assert lines[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C' and not any(x.startswith('FIND ') for x in lines)
    finally:
        w.destroy()


def t_d5_clear_check_found_accepted():
    """D5 (W92): the check's own FIND block is answered by `found` (not the STOP), then its DOWNLOAD, then the clear:
    HALT.json under cleared_<utc14>/, the boot mark kept (W100), and the RESTORE records cleared_local (W66)."""
    w, h = slip_limit_world()
    try:
        good = w.clear_kit('SLIP_LIMIT', 1)
        boot_kit(w, good)
        code, lines = w.dot.cmd('go')
        assert any('SESSION_KIT_%s.zip' % good in x for x in lines) and ' found --at ' in lines[-1], lines
        code, nxt = w.dot.execute(lines)
        assert any(x.startswith('DOWNLOAD ') for x in nxt), nxt
        code, lines = until(w, code, nxt, lambda ls: 'case=CASE_ID' in ls[-1])
        assert 'case=CASE_ID' in lines[-1], lines
        assert not (fv2(w) / 'HALT.json').exists() and list(fv2(w).glob('cleared_*/HALT.json'))
        assert (w.base / 'inbox/.boot').is_file()
        r = fentry(w, 2)
        assert r['kind'] == 'RESTORE' and r['cleared_local'] == {'code': 'SLIP_LIMIT', 'head_seq': 1,
                                                                 'kit_sha256': h['kit_sha256']}
        assert r['kit_sha256'] != h['kit_sha256'] and r['body']['kit_change']['config_only']
        assert r['body']['approval'] == 'none'
    finally:
        w.destroy()


def t_d11_clear_check_routes_found_only_to_its_find():
    """D5 (§2.4.3; GM-cli-clear_check-4/5/6/11): a `found` reaches the clear check only while HALT.json holds a check
    and BLOCK.json is its own block; otherwise (after an `answer` printed the stop, with BLOCK.json gone, or with the
    check dropped) it prints the stop again. A new hint kit during a check starts its own FIND, never the old kit's
    DOWNLOAD."""
    def kit_find(w):
        good = w.clear_kit('SLIP_LIMIT', 1)
        boot_kit(w, good)
        code, lines = w.dot.cmd('go')
        assert any('SESSION_KIT_%s.zip' % good in x for x in lines) and ' found --at ' in lines[-1], lines
        return good, lines
    stop = 'DO: STOP SLIP_LIMIT HANDBACK C'
    for case in ('answer', 'no_block', 'no_check', 'new_kit'):
        w, h = slip_limit_world()
        try:
            good, lines = kit_find(w)
            name = 'SESSION_KIT_%s.zip' % good
            if case == 'answer':
                code, st = w.dot.cmd('answer', '--at', fat(lines), 'case=case01')
                assert code == 3 and st[-1] == stop, st
                code, out = w.dot.cmd('found', '--at', fat(st), '--name', name, '--none')
            elif case == 'new_kit':
                code, nxt = w.dot.execute(lines)
                assert any(x.startswith('DOWNLOAD ') for x in nxt), nxt
                other = w.clear_kit('SLIP_LIMIT', 2)
                boot_kit(w, other)
                code, out = w.dot.cmd('go')
                assert code == 0 and any(x.startswith('FIND ') and 'SESSION_KIT_%s.zip' % other in x for x in out) \
                    and not any(x.startswith(('DOWNLOAD ', 'REFUSED')) for x in out), out
                continue
            else:
                if case == 'no_block':
                    os.unlink(fv2(w) / 'BLOCK.json')
                else:
                    hd = fdoc(w, 'HALT.json')
                    hd['check'] = None
                    durable.write_doc(fv2(w) / 'HALT.json', hd)
                code, out = w.dot.cmd('found', '--at', fat(lines), '--name', name, '--none')
            assert code == 3 and out[-1] == stop and not any(x.startswith('REFUSED') for x in out), (case, out)
        finally:
            w.destroy()


def t_d5_clear_check_bounded():
    """D5 (W103): four DOWNLOAD_MISSING slips in one check: the fourth adds the kit to `tried` and prints the stop with
    its code unchanged; STATE.json byte-identical."""
    w, h = slip_limit_world()
    try:
        good = w.clear_kit('SLIP_LIMIT', 1)
        boot_kit(w, good)
        st0 = (fv2(w) / 'STATE.json').read_bytes()
        code, lines = w.dot.cmd('go')
        for k in range(4):
            assert ' found --at ' in lines[-1], (k, lines)
            code, lines = w.dot.execute(lines)                      # found: the DOWNLOAD block
            assert any(x.startswith('DOWNLOAD ') for x in lines), lines
            code, lines = w.dot.cmd('go')                            # the file was never downloaded
            if k < 3:
                assert code == 4 and lines[1].startswith('REFUSED DOWNLOAD_MISSING SESSION_KIT_'), lines
        assert lines[-1] == 'DO: STOP SLIP_LIMIT HANDBACK C', lines
        h2 = fdoc(w, 'HALT.json')
        assert good in h2['tried'] and h2['code'] == 'SLIP_LIMIT' and (fv2(w) / 'STATE.json').read_bytes() == st0
    finally:
        w.destroy()


def t_gap08_clear_moves_attest_and_inbox():
    """GAP-08 (W81): the clear moves BASE/attest and BASE/inbox (but the boot mark) under cleared_<utc14>/; a
    final_message.txt left from before the clear is gone from attest/."""
    w, h = slip_limit_world()
    try:
        (w.base / 'attest').mkdir(exist_ok=True)
        (w.base / 'attest/final_message.txt').write_text('left from before the clear')
        (w.base / 'inbox/verify').mkdir(parents=True, exist_ok=True)
        (w.base / 'inbox/verify/old.1').write_bytes(b'old download')
        boot_kit(w, w.clear_kit('SLIP_LIMIT', 1))
        code, lines = until(w, *w.dot.cmd('go'), lambda ls: 'case=CASE_ID' in ls[-1])
        d = list(fv2(w).glob('cleared_*'))[0]
        assert (d / 'attest/final_message.txt').is_file() and (d / 'inbox/verify/old.1').is_file()
        assert not (w.base / 'attest/final_message.txt').exists() and (w.base / 'inbox/.boot').is_file()
    finally:
        w.destroy()


def t_d5_wait_approval_in_clearing_restore():
    """D5 + D6 (W66, W100): after the clear, approval=pending gives STOP WAIT_APPROVAL HANDBACK A with no HALT.json
    written; the next `go` asks approval= again, then the head search's first FIND."""
    w, h = slip_limit_world()
    try:
        boot_kit(w, w.clear_kit('SLIP_LIMIT', 1))
        code, lines = until(w, *w.dot.cmd('go'), lambda ls: ' approval=APPROVAL' in ls[-1])
        assert ' approval=APPROVAL' in lines[-1] and list(fv2(w).glob('cleared_*/HALT.json')), lines
        code, out = w.dot.cmd('answer', '--at', fat(lines), 'approval=pending')
        assert code == 3 and out[-1] == 'DO: STOP WAIT_APPROVAL HANDBACK A', out
        assert not (fv2(w) / 'HALT.json').exists()
        code, again = w.dot.cmd('go')
        assert ' approval=APPROVAL' in again[-1], again
        code, nxt = w.dot.cmd('answer', '--at', fat(again), 'approval=none')
        assert any(x.startswith('FIND ') and N.entry_name('E1', 1) in x for x in nxt) or any(
            x.startswith('FIND ') for x in nxt), nxt
    finally:
        w.destroy()


def t_d11_stop_block_sticky_only_for_handback_c():
    """D5 (SD-56; GM-cli-stop_block-0/1/2/4): STOP FINAL HANDBACK B and RELEASE_GATE_OPEN write no HALT.json (FINAL's
    header is state=FINAL); any other HANDBACK C stop writes HALT.json under state=STOP; without the v2 folder the
    full STOP block is printed and nothing is written."""
    def stop_with(w, *a):
        real = cli.go_checks

        def fake(env):
            if a[0] == 'NO_V2':
                os.rename(env.v2, str(env.v2) + '_gone')
                cli.stop_block(env, 'UNCLASSIFIED')
            cli.stop_block(env, *a)
        cli.go_checks = fake
        try:
            return w.dot.cmd('go')
        finally:
            cli.go_checks = real
    with fw() as w:
        to_idle(w)
        for args, sticky in ((('FINAL', 'B'), False), (('RELEASE_GATE_OPEN',), False), (('UNCLASSIFIED',), True)):
            code, out = stop_with(w, *args)
            want = 'DO: STOP %s HANDBACK %s' % (args[0], args[1] if len(args) > 1 else 'C')
            assert code == 3 and out[-1] == want and (' state=FINAL' in out[0]) == (args[0] == 'FINAL'), out
            assert (fv2(w) / 'HALT.json').exists() == sticky, (args, out)
        os.unlink(fv2(w) / 'HALT.json')
        for doc in ('STATE.json', 'RESTORE_WORK.json'):
            if (fv2(w) / doc).exists():
                d = fdoc(w, doc)
                d.pop('halt_local', None)
                (fv2(w) / doc).write_text(json.dumps(d))
        code, out = stop_with(w, 'NO_V2')
        assert code == 3 and out[0].startswith('CPSV series=E1 ') and out[-1] == 'DO: STOP UNCLASSIFIED HANDBACK C', out
        assert not (Path(str(fv2(w)) + '_gone') / 'HALT.json').exists() and not fv2(w).exists()


def t_d5_halted_restore_no_cleared_local():
    """D5 (W91, SD-51): clearing a committed HALT (a HALTED_<code> STOP) by a kit whose clear names it: the RESTORE
    records no cleared_local and keeps the halted kit; the CLEAR carries the change."""
    with fw() as w:
        code, idle = to_idle(w)
        from cpsvm2.vio.v1compat import Halt as H
        real = cli.go_checks

        def boom(env):
            raise H('STOP', 'UNCLASSIFIED', 'invented')
        cli.go_checks = boom
        try:
            code, out = w.dot.cmd('go')
        finally:
            cli.go_checks = real
        code, out = w.dot.run(code, out)                  # the HALT entry's commit loop, then the stop
        assert fentry(w, 2)['kind'] == 'HALT', out
        assert out[-1] in ('DO: STOP UNCLASSIFIED HANDBACK C', 'DO: STOP HALTED_UNCLASSIFIED HANDBACK C'), out
        code, out = w.dot.cmd('go')
        assert out[-1] == 'DO: STOP HALTED_UNCLASSIFIED HANDBACK C', out
        k = w.clear_kit('UNCLASSIFIED', 2)
        boot_kit(w, k, '000002')
        code, lines = until(w, *w.dot.cmd('go'), lambda ls: 'case=CASE_ID' in ls[-1])
        assert 'case=CASE_ID' in lines[-1], lines
        kinds = [fentry(w, s)['kind'] for s in range(1, 5)]
        assert kinds == ['GENESIS', 'HALT', 'RESTORE', 'CLEAR'], kinds
        r, c = fentry(w, 3), fentry(w, 4)
        assert r['cleared_local'] is None and r['body']['kit_change'] is None and r['kit_sha256'] == fentry(w, 2)[
            'kit_sha256'] and c['body']['kit_change']['to_kit_sha256'].startswith(k)


def t_d16_stage_refuses_low_space_before_runner():
    """D16 (SD-69, W108): free space one byte below STAGE_FREE_BYTES plus the margin: STOP DISK_FULL step stage before
    FOREGROUND.json and before the runner; at exactly that value the stage runs. Amendment A7 (W128) and its fix round
    (CC-2, W137): the value covers the finish stage's peak on /tmp through the save that follows it, with M009's sizes:
    the job folder (about 590 MB), the commit's PNG parts and entry in outbox/journal (about 590 MB, written inside the
    stage by commit_end) and their download-back into inbox/verify (about 590 MB, which no later check covers). The
    render's own peak (550 MB twice in TMPDIR and the job folder, plus 16 MB) is below that."""
    from cpsvm2.vio import v1reuse
    assert N.STAGE_FREE_BYTES >= 3 * 590 * 10 ** 6 >= 2 * 550 * 10 ** 6 + 16 * 10 ** 6, N.STAGE_FREE_BYTES
    for short, want_stop in ((1, True), (0, False)):
        with fw() as w:
            code, idle = to_idle(w)
            w.everyday_request()
            code, save = w.dot.cmd('answer', '--at', fat(idle), 'case=%s' % w.everyday[-1])
            real = shutil.disk_usage
            need = N.STAGE_FREE_BYTES + 64 * 1024 * 1024

            def du(p):
                r = real(p)
                return type(r)(r.total, r.used, need - short)
            n = len(w.dot.running)
            v1reuse.shutil.disk_usage = du
            try:
                code, lines = until(w, code, save, lambda ls: bool(w.dot.running[n:]) or 'STOP' in ls[-1])
            finally:
                v1reuse.shutil.disk_usage = real
            if want_stop:
                assert lines[-1] == 'DO: STOP DISK_FULL HANDBACK C', lines
                assert fdoc(w, 'HALT.json')['detail']['step'] == 'stage' and not (fv2(w) / 'FOREGROUND.json').exists()
                assert len(w.dot.running) == n and not w.seams.subs, 'the runner never started'
            else:
                assert len(w.dot.running) > n and w.seams.subs, 'at exactly the limit the stage runs'


def stage_env(tag, marker=True):
    """Amendment A5/A6: an Env for cli.run_stage alone (BASE outside HOME, the setup marker of this boot and commit)."""
    r = tmpdir(tag)
    os.environ.update({'HOME': str(r / 'home'), 'CPS_VM_BASE': str(r / 'tmp/cps'), 'CPS_TOOLS': str(r / 'home/cps-tools'),
                       'CPS_VM_BOOT_ID_PATH': str(r / 'boot_id')})
    (r / 'boot_id').write_text(BOOT + '\n')
    lay = Layout()
    (lay.base / 'outbox/v2').mkdir(parents=True)
    os.symlink(host.HELPER_REPO, lay.base / 'repo')
    (lay.tools / 'var').mkdir(parents=True)
    if marker:
        (lay.tools / 'var/cps_vm2_setup_ok').write_text('%s %s\n' % (BOOT, host.repo_commit(lay)))
    env = cli.Env(lay, None)
    env.cfg = {'stage_max_seconds': {k: 60 for k in N.STAGE_KEYS}}
    return env


def run_stage_seen(env, kind='chain'):
    """cli.run_stage with worker.dispatch replaced: (exit or None, printed lines, what the stage saw when it started)."""
    from cpsvm2 import worker
    seen_at, out, tmp0 = {}, io.StringIO(), os.environ.get('TMPDIR')

    def fake(k, info, e):
        t = e.lay.base / 'tmp'
        seen_at.update(tmpdir=os.environ.get('TMPDIR'), left=sorted(os.listdir(t)) if t.is_dir() else None,
                       foreground=e.p.foreground.is_file())
        return {'status': 'done'}
    real, space = worker.dispatch, cli.require_space
    worker.dispatch, cli.require_space = fake, lambda *a: None
    code = None
    try:
        with contextlib.redirect_stdout(out):
            cli.run_stage(env, kind, {'run': 'E20261110T000000Z/c1', 'first': 'prepare'} if kind == 'chain' else {})
    except cli.Out as o:
        code = o.code
    finally:
        worker.dispatch, cli.require_space = real, space
        os.environ.pop('TMPDIR', None) if tmp0 is None else os.environ.update(TMPDIR=tmp0)
    return code, out.getvalue().splitlines(), seen_at


def t_a6_stage_empties_tmp_and_sets_tmpdir():
    """Amendment A6 (W125, W126): before every stage, under the lock, BASE/tmp is emptied (a killed render's files and
    a read-only folder go) and TMPDIR is BASE/tmp, which every runner command inherits (run_runner passes the
    environment); the stage starts with an empty BASE/tmp."""
    for kind in ('chain', 'place'):
        env = stage_env('a6' + kind)
        t = env.lay.base / 'tmp'
        (t / 'cps_visual_x/in').mkdir(parents=True)
        (t / 'cps_visual_x/in/page-1.png').write_bytes(b'invented page' * 100)
        (t / 'render-copy.pdf').write_bytes(b'%PDF invented')
        os.chmod(t / 'cps_visual_x/in', 0o555)
        code, lines, at = run_stage_seen(env, kind)
        assert code is None and lines[0].startswith('CPSV-RUNNING kind=%s ' % kind), lines
        assert at == {'tmpdir': str(t), 'left': [], 'foreground': True}, at


def t_g2_tmp_emptied_before_space_check():
    """Fix round G2 (W132): BASE/tmp is emptied before the stage's space check. A killed render's files there (here one
    planted file stands for them) never count against STAGE_FREE_BYTES: the free space reported is one byte short while
    the file exists and exactly enough once it is gone, and the stage runs instead of stopping DISK_FULL."""
    from cpsvm2 import worker
    from cpsvm2.vio import v1reuse
    env = stage_env('g2')
    t = env.lay.base / 'tmp'
    t.mkdir()
    (t / 'left_by_a_killed_render.png').write_bytes(b'invented page' * 1000)
    real, need = shutil.disk_usage, N.STAGE_FREE_BYTES + 64 * 1024 * 1024
    seen_at, out = {}, io.StringIO()

    def du(p):
        r = real(p)
        return type(r)(r.total, r.used, need - (1 if (t / 'left_by_a_killed_render.png').exists() else 0))

    def fake(k, info, e):
        seen_at['ran'] = True
        return {'status': 'done'}
    wd, v1reuse.shutil.disk_usage, worker.dispatch = worker.dispatch, du, fake
    code, tmp0 = None, os.environ.get('TMPDIR')
    try:
        with contextlib.redirect_stdout(out):
            cli.run_stage(env, 'chain', {'run': 'E20261110T000000Z/c1', 'first': 'prepare'})
    except cli.Out as o:
        code = o.code
    finally:
        v1reuse.shutil.disk_usage, worker.dispatch = real, wd
        os.environ.pop('TMPDIR', None) if tmp0 is None else os.environ.update(TMPDIR=tmp0)
    assert code is None and seen_at.get('ran') and not env.p.halt.exists(), out.getvalue()


def t_a5_stage_stops_setup_missing():
    """Amendment A5 (W127): a stage needs the setup marker of this boot and commit in TOOLS. Without it (TOOLS gone) or
    with another boot's, `go` prints STOP SETUP_MISSING before FOREGROUND.json and the runner, writes no HALT.json
    (nothing sticky) and leaves BASE/tmp as it was; with the marker the stage runs."""
    for case in ('gone', 'other_boot', 'other_commit'):
        env = stage_env('a5' + case)
        m = env.lay.tools / 'var/cps_vm2_setup_ok'
        if case == 'gone':
            fakes_rm(env.lay.tools)
        else:
            boot, commit = m.read_text().split()
            m.write_text('%s %s\n' % (('f' * 8 + boot[8:], commit) if case == 'other_boot' else (boot, 'f' * 40)))
        (env.lay.base / 'tmp').mkdir()
        (env.lay.base / 'tmp/kept').write_text('x')
        code, lines, at = run_stage_seen(env)
        assert code == 3 and lines[-1] == 'DO: STOP SETUP_MISSING HANDBACK C' and lines[0].startswith('CPSV '), lines
        assert not at and not env.p.halt.exists() and not env.p.foreground.exists(), case
        assert (env.lay.base / 'tmp/kept').is_file(), case
    env = stage_env('a5ok')
    code, lines, at = run_stage_seen(env)
    assert code is None and at['foreground'], lines


def fakes_rm(p):
    for dp, dns, fns in os.walk(p):
        for n in dns:
            os.chmod(os.path.join(dp, n), 0o755)
    shutil.rmtree(p)


def t_a4_stale_temp_names_in_runtime_ignored():
    """Amendment A4a (W122; fix round G4, W133): a killed write_atomic leaves .tmp_<pid>_<name> in runtime/ (one-digit
    pids on the Dot, any number of digits elsewhere). With a run in flight the kit
    check (unpack_kit) must not see it: cleanup_leftovers, which every command runs under the lock first, removes
    such names, and the verdict is the one without them ('same'; 'config' for a config-only change), never
    KIT_CHANGE_WITH_RUN_IN_FLIGHT. A kit member stays."""
    from cpsvm2.vio import v1mod, v1reuse
    env = SPEnv(tmpdir('a4rt'))
    lay = env.lay
    m = {'RELEASE.json': b'{"invented": 1}\n', 'VM_HELPER_CONFIG.json': b'{"invented": 2}\n', 'tables/T.json': b'{}\n'}
    assert v1reuse.unpack_kit(lay, m, False) == 'unpacked'
    for cfg, want in ((m['VM_HELPER_CONFIG.json'], 'same'), (b'{"invented": 3}\n', 'config')):
        for n in ('.tmp_2_VM_HELPER_CONFIG.json', '.tmp_3_x', '.tmp_48213_VM_HELPER_CONFIG.json'):   # G4 (W133): any pid
            (lay.runtime / n).write_bytes(b'left by a killed command')
        v1mod.cleanup_leftovers(lay)
        assert v1reuse.unpack_kit(lay, dict(m, **{'VM_HELPER_CONFIG.json': cfg}), True) == want
        assert sorted(os.listdir(lay.runtime)) == ['RELEASE.json', 'VM_HELPER_CONFIG.json', 'tables']


def t_a4_stale_png_stream_and_validate_removed():
    """Amendment A4b/A4c (W123, W124): in the same boot, cleanup_leftovers removes a killed placement's
    inbox/journal/.png_stream_<pid> (and any other hidden file there) and the runner's stale .validate_<case>_<pid>
    folders in every jobs root it is given (qual/<root>/, qual/nonattempts_<reader>/, jobs/<utc14>/); downloads, job
    folders and the boot mark stay."""
    from cpsvm2.vio import v1mod
    from cpsvm2.vio.v1reuse import current_boot_id
    env = SPEnv(tmpdir('a4pv'))
    lay = env.lay
    lay.inbox.mkdir(parents=True, exist_ok=True)
    (lay.inbox / '.boot').write_text(current_boot_id() + '\n')
    j = lay.inbox / 'journal'
    j.mkdir()
    for n in ('.png_stream_2', '.png_stream_7', '.tmp_2_ab12cd34_CPSJ_D1_000003.tgz', 'CPSJ_D1_000003.tgz'):
        (j / n).write_bytes(b'invented')
    keep = [lay.qual / 'A/9990101/run/x.txt', lay.jobs / '20261110T000000Z/c1/x.txt']
    for p in keep:
        p.parent.mkdir(parents=True)
        p.write_text('a job file')
    stale = [lay.qual / 'A/.validate_9990101_2', lay.qual / 'nonattempts_B/.validate_9990102_3',
             lay.jobs / '20261110T000000Z/.validate_c1_2']
    for d in stale:
        d.mkdir(parents=True)
        (d / 'JOB.json').write_text('{}')
        os.chmod(d, 0o555)
    v1mod.cleanup_leftovers(lay)
    assert sorted(os.listdir(j)) == ['CPSJ_D1_000003.tgz'] and (lay.inbox / '.boot').is_file()
    assert not any(os.path.lexists(d) for d in stale) and all(p.is_file() for p in keep)


def to_g_end(w):
    """IDLE, a request, its prepare (the real runner), the generator conversation; stops at the G end question."""
    code, idle = to_idle(w)
    w.everyday_request()
    code, lines = w.dot.cmd('answer', '--at', fat(idle), 'case=%s' % w.everyday[-1])
    code, lines = until(w, code, lines, lambda ls: ' model=MODEL ' in ls[-1])
    assert ' model=MODEL ' in lines[-1], lines
    return code, lines


def g_args(w, ask, **over):
    vals = w.dot.answer([tuple(x.split('=', 1)) for x in ask[-1].split(' --at ')[1].split()[1:]], None, ask)
    vals.update(over)
    return ['answer', '--at', fat(ask)] + ['%s=%s' % kv for kv in vals.items()]


def entry_member(w, e, member):
    p = w.fixed / ('m_' + e['name'])
    p.write_bytes(w.drive.bytes_of(N.series_folder(w.series), e['name']))
    try:
        return savepoint.member_bytes(p, member)
    finally:
        os.unlink(p)


def ai_entries(w):
    out, s = [], 1
    while w.drive.has(N.series_folder(w.series), N.entry_name(w.series, s)):
        out.append(fentry(w, s))
        s += 1
    return out


FM_ODD = '{"braces"} <angle> \'quote\' `tick` $dollar \\back and\nlines\n'


def t_opx05_final_message_any_characters_verbatim():
    """OPX-05 / D3c (W21): the final message is data: braces, angle brackets, quotes and newlines are stored verbatim
    as attest/final_message.txt; a missing file or non-UTF-8 bytes are refused with the reason (counted)."""
    with fw() as w:
        code, ask = to_g_end(w)
        fm, args = w.base / 'attest/final_message.txt', g_args(w, ask)
        fm.unlink()
        code, out = w.dot.cmd(*args)
        assert code == 4 and out[1] == 'REFUSED FINAL_MESSAGE_INVALID missing', out
        fm.write_bytes(b'\xff\xfe')
        code, out = w.dot.cmd(*args)
        assert out[1] == 'REFUSED FINAL_MESSAGE_INVALID utf8', out
        fm.write_bytes(FM_ODD.encode('utf-8'))
        code, out = w.dot.cmd(*args)
        assert code == 0, out
        code, out = until(w, code, out, lambda ls: 'state=DELIVER' in ls[0])
        g = [e for e in ai_entries(w) if e['kind'] == 'AI' and e['body']['role'] == 'G'][0]
        assert entry_member(w, g, 'attest/final_message.txt').decode() == FM_ODD
        assert g['body']['final_message_sha256'] == sha(FM_ODD.encode())


def t_opx05_empty_final_message_accepted():
    """OPX-05 (W90): an empty final message (a conversation without one) is accepted and archived as 0 bytes."""
    with fw() as w:
        code, ask = to_g_end(w)
        args = g_args(w, ask)                             # (the FakeDot writes its own message; then ours)
        (w.base / 'attest/final_message.txt').write_bytes(b'')
        code, out = w.dot.cmd(*args)
        assert code == 0, out
        code, out = until(w, code, out, lambda ls: 'state=DELIVER' in ls[0])
        g = [e for e in ai_entries(w) if e['kind'] == 'AI' and e['body']['role'] == 'G'][0]
        assert entry_member(w, g, 'attest/final_message.txt') == b'' and g['body']['final_message_sha256'] == sha(b'')


def t_opx05_oversize_final_message_stops():
    """OPX-05 (W98, SD-65): a final message over max_ai_output_bytes is STOP AI_OUTPUT_TOO_LARGE, never a refusal."""
    with fw(cfg={'max_ai_output_bytes': 2000000}) as w:
        code, ask = to_g_end(w)
        args = g_args(w, ask)
        (w.base / 'attest/final_message.txt').write_bytes(b'x' * 2000001)
        n = len(w.dot.refused)
        code, out = w.dot.run(*w.dot.cmd(*args))                # a committed HALT (CODES_HALT), then its STOP
        assert code == 3 and 'AI_OUTPUT_TOO_LARGE' in out[-1] and len(w.dot.refused) == n, out


def t_maint2_tools_file_link_refused():
    """MAINT-2 (W72): tools=file: takes a regular file under BASE/attest only: a link, a path elsewhere and a list in
    the wrong format are TOOLS_FILE_INVALID; a good file is archived as attest/tools.txt with source file."""
    with fw() as w:
        code, ask = to_g_end(w)
        (w.base / 'attest/final_message.txt').write_text('done')
        link = w.base / 'attest/tools_link.txt'
        os.symlink(w.base / 'runtime/TOOL_INVENTORY.txt', link)
        bad = w.base / 'attest/tools_bad.txt'
        bad.write_bytes(b'dup\ndup\n')
        for p in (link, bad):
            code, out = w.dot.cmd(*g_args(w, ask, tools='file:' + str(p)))
            assert code == 4 and out[1] == 'REFUSED TOOLS_FILE_INVALID', (p, out)
        good = w.base / 'attest/tools_saved.txt'
        good.write_bytes(b'invented_tool_a\ninvented_tool_b\n')
        code, out = w.dot.cmd(*g_args(w, ask, tools='file:' + str(good)))
        assert code == 0, out
        code, out = until(w, code, out, lambda ls: 'state=DELIVER' in ls[0])
        g = [e for e in ai_entries(w) if e['kind'] == 'AI' and e['body']['role'] == 'G'][0]
        assert g['body']['attested']['tools_present'] == {'source': 'file', 'sha256': sha(good.read_bytes() if
                                                                                      good.exists() else
                                                                                      b'invented_tool_a\ninvented_tool_b\n')}
        assert entry_member(w, g, 'attest/tools.txt') == b'invented_tool_a\ninvented_tool_b\n'


def t_maint2_generation_record_tools_and_o63_note():
    """MAINT-2 (W32): the GENERATION_RECORD.json of the consuming stage has tools_enabled = the attested list and the
    fixed O63 note naming its sha256; the G entry records tools_present (inventory) and no free `tools` answer."""
    import fakes
    with fw() as w:
        code, ask = to_g_end(w)
        code, out = until(w, code, ask, lambda ls: 'state=DELIVER' in ls[0])
        es = ai_entries(w)
        g = [e for e in es if e['kind'] == 'AI' and e['body']['role'] == 'G'][0]
        assert g['body']['attested']['tools_present'] == {'source': 'inventory', 'sha256': fakes.sha(fakes.TOOLS)}
        assert 'tools' not in g['body']['attested']
        st = [e for e in es if e['kind'] == 'STAGE' and e['body']['consumed']][0]
        rec = json.loads(entry_member(w, st, 'job/run/GENERATION_RECORD.json'))
        assert rec['tools_enabled'] == fakes.TOOLS.decode().splitlines(), rec['tools_enabled']
        assert rec['notes'] == N.O63_NOTE % fakes.sha(fakes.TOOLS) and N.fm(N.O63_NOTE_RE, rec['notes'])


def t_maint2_s_v_entries_archive_message_and_tools():
    """MAINT-2 (W47): S and V AI entries (revision 1) record tools_present and archive the final or closing message
    verbatim (attest/final_message.txt) with attest/tools.txt (a D1 run with the real runner: scope reader, G, V)."""
    with fw(series='D1', cases=(('9990101', 'large'), ('9990102', 'small'))) as w:
        w.start()
        k = [0]

        def enough(dot, lines):                  # GAP-10: stop once the first run's S, G and V entries are on Drive
            n = len(w.drive.folders.get(N.series_folder(w.series), {}))
            if n != k[0]:
                k[0] = n
                if {'S', 'G', 'V'} <= {e['body']['role'] for e in ai_entries(w) if e['kind'] == 'AI'}:
                    return 'stop'
        w.dot.hook = enough
        code, out = w.dot.run(*w.dot.cmd('go'))
        es = ai_entries(w)
        roles = {e['body']['role']: e for e in es if e['kind'] == 'AI' and e['body']['revision'] == 1}
        assert {'S', 'G', 'V'} <= set(roles), sorted(roles)
        for r in ('S', 'V'):
            e = roles[r]
            assert e['body']['attested']['tools_present']['source'] in ('inventory', 'file'), e['body']['attested']
            fm = entry_member(w, e, 'attest/final_message.txt')
            assert sha(fm) == e['body']['final_message_sha256']
            assert sha(entry_member(w, e, 'attest/tools.txt')) == e['body']['attested']['tools_present']['sha256']


def t_s01_setup_failed_log_uploaded_without_kit_config():
    """S-01 (W06): after SETUP_FAILED with an empty BASE/runtime (no kit config yet) the setup log is uploaded through
    the setup-file loop with the platform cap, then STOP SETUP_FAILED."""
    w = World()
    b = w.lay.base
    for f in ('outbox/v2/STATE.json', 'outbox/v2/RESTORE_WORK.json', 'runtime/VM_HELPER_CONFIG.json',
              'runtime/RELEASE.json', 'runtime/TOOL_INVENTORY.txt'):
        os.unlink(b / f)
    (w.lay.tools / 'var').mkdir(parents=True, exist_ok=True)
    (w.lay.tools / 'var/cps_vm2_setup_failed').write_text('%s %s\n' % (BOOT, host.repo_commit(w.lay)))
    (b / 'outbox/setup_20261110T000000Z.log').write_text('invented setup log\n')
    code, a = w.cmd('go')
    assert code == 0 and ' TO CPS/reports AS setup_20261110T000000Z.log' in a[1], a
    a = dot_until(w, w.cmd('found', *dot_do(w.drive, a))[1], 'STOP')
    assert a[-1] == 'DO: STOP SETUP_FAILED HANDBACK C' and w.drive.find('CPS/reports', 'setup_20261110T000000Z.log')


def t_s04_pending_post_resumed_before_next_commit():
    """S-04 (W08, W60): post actions still owed in STATE.post run at the next command, after the clear check and
    before anything else; each is removed as it completes."""
    with fw() as w:
        code, idle = to_idle(w)
        f = w.base / 'inbox/journal/left.part'
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b'owed')
        st = fdoc(w, 'STATE.json')
        st['post'] = [['DROP_LOCAL', [str(f)]]]
        durable.write_doc(fv2(w) / 'STATE.json', st)
        code, out = w.dot.cmd('go')
        assert not f.exists() and fdoc(w, 'STATE.json')['post'] == [] and 'case=CASE_ID' in out[-1], out


def t_d5_post_action_halt_cleared_same_boot():
    """D5 + S-04 (W60): a post action that fails is the committed HALT POST_ACTION_FAILED with the action still owed in
    STATE.post; the clear check comes before the post resume, so the clear kit clears it although the action would
    fail again (the cache with its post moves aside); the restore and the CLEAR follow and the series goes on."""
    with fw() as w:
        code, idle = to_idle(w)
        d = w.base / 'attest/owed'
        d.mkdir(parents=True, exist_ok=True)
        st = fdoc(w, 'STATE.json')
        st['post'] = [['DROP_ATTEST', [str(d)]]]
        durable.write_doc(fv2(w) / 'STATE.json', st)
        real = cli.remove_tree

        def bad(p):
            raise OSError(errno.EIO, 'invented')
        cli.remove_tree = bad
        try:
            code, out = w.dot.run(*w.dot.cmd('go'))
            assert 'POST_ACTION_FAILED' in out[-1] and fentry(w, 2)['kind'] == 'HALT', out
            h = fdoc(w, 'HALT.json')
            boot_kit(w, w.clear_kit(h['code'], h['head_seq']), '%06d' % h['head_seq'])
            code, out = w.dot.cmd('go')
            assert any(x.startswith('FIND CPS/setup NAME SESSION_KIT_') for x in out), ('the check first', out)
            code, out = until(w, code, out, lambda ls: 'state=HEAD' in ls[0])
            assert list(fv2(w).glob('cleared_*/STATE.json')) and not (fv2(w) / 'HALT.json').exists(), out
        finally:
            cli.remove_tree = real
        st = json.loads(list(fv2(w).glob('cleared_*/STATE.json'))[0].read_text())
        assert st['post'], 'the owed action moved aside with the cache, never run before the clear'



def t_c1_post_failure_finishes_pending_halt_first():
    """OPEN-C1 (S-04): an owed post action that keeps failing never runs while a commit is pending. The HALT
    POST_ACTION_FAILED that the first failure commits is finished first (PENDING.json gone), so the STOP and HALT.json
    name the HALT's own seq, and a single clear for that head is enough."""
    with fw() as w:
        code, idle = to_idle(w)
        d = w.base / 'attest/owed'
        d.mkdir(parents=True, exist_ok=True)
        st = fdoc(w, 'STATE.json')
        st['post'] = [['DROP_ATTEST', [str(d)]]]
        durable.write_doc(fv2(w) / 'STATE.json', st)
        real = cli.remove_tree

        def bad(p):
            raise OSError(errno.EIO, 'invented')
        cli.remove_tree = bad
        try:
            code, out = w.dot.run(*w.dot.cmd('go'))
        finally:
            cli.remove_tree = real
        assert out[-1] == 'DO: STOP POST_ACTION_FAILED HANDBACK C', out
        assert not (fv2(w) / 'PENDING.json').exists(), 'the HALT commit was left pending'
        assert ' head=000002 ' in out[0] and fdoc(w, 'HALT.json')['head_seq'] == 2, (out, fdoc(w, 'HALT.json'))
        assert fdoc(w, 'STATE.json')['post'], 'the failed action is still owed'


def t_gap02_files_found_before_settle():
    """GAP-02 (W76): worker.do_place walks the open role's output in the existing target before place_job (settle) moves
    it aside, and in the placed tree after it; files_found is true when either holds a file outside the snapshot. With
    no target there is no walk before the placement."""
    from cpsvm2 import worker
    root = tmpdir('gap02')
    jd = os.path.join(root, 'job')
    calls = []

    def fake_rewalk(env, info, snap):
        calls.append(('rewalk', os.path.lexists(os.path.join(jd, 'conv_file.txt'))))
        return os.path.lexists(os.path.join(jd, 'conv_file.txt'))

    def fake_place_job(lay, job_dir, snap, png, parts, ai):
        calls.append(('place', None))
        if os.path.lexists(job_dir):
            os.rename(job_dir, job_dir + '.aside')          # settle: the target differs, it is moved aside
        os.makedirs(job_dir)
        return 'H' * 64, job_dir + '.aside'
    env = type('E', (), {'lay': None, 'state': {'runs': {}}})()
    info = {'series': 'D1', 'inbox': root, 'job_dir': jd, 'snapshot_seq': 3, 'png': None, 'ai': [], 'rewalk': True,
            'run': 'A/9990101', 'open_role': 'G1'}
    with patched(worker, 'rewalk', fake_rewalk), patched(worker.place, 'place_job', fake_place_job):
        os.makedirs(jd)
        Path(jd, 'conv_file.txt').write_text('written by the open conversation\n')
        r = worker.do_place(env, info)
        assert calls == [('rewalk', True), ('place', None)], calls
        assert r['files_found'] is True and r['placed'][0]['aside'] == jd + '.aside', r
        shutil.rmtree(jd)
        shutil.rmtree(jd + '.aside')
        del calls[:]
        r = worker.do_place(env, info)
        assert calls == [('place', None), ('rewalk', False)] and r['files_found'] is False, (calls, r)


def t_gap04_moved_pending_foreign_copy_forks():
    """GAP-04 (W77): in a clearing restore, when the head found is the moved PENDING's seq, its copy must hold the moved
    PENDING's bytes: a single copy with other bytes is FORK (head_error), and two copies that disagree are FORK too.
    A copy with the moved PENDING's bytes goes on to the entry checks (here an invented non-entry: HEAD_CORRUPT)."""
    root = tmpdir('gap04')
    name = N.entry_name('D1', 7)
    saved = []
    env = type('E', (), {})()

    def one(payload, mp_sha, extra=None):
        p = os.path.join(root, name + '.1')
        Path(p).write_bytes(payload)
        paths, shas = [p], {sha(payload)}
        if extra is not None:
            Path(p[:-1] + '2').write_bytes(extra)
            paths.append(p[:-1] + '2')
            shas.add(sha(extra))
        env.work = {'moved_pending': {'seq': 7, 'name': name, 'sha256': mp_sha, 'uploaded': [name]},
                    'head_error': None, 'head': None}
        with patched(cli, 'save_work', lambda e: saved.append(dict(e.work))):
            cli.verify_head(env, paths, shas)
        return env.work['head_error']
    ours = b'the moved pending entry (invented)'
    assert one(b'a foreign copy at that seq', sha(ours)) == 'FORK'
    assert one(ours, sha(ours), extra=b'another copy') == 'FORK'
    env.series, env.cfg = 'D1', {'accepted_helper_tree_sha256': [], 'accepts_release_sha256': []}
    assert one(ours, sha(ours)) == 'HEAD_CORRUPT'
    env.work = None


TESTS = [t_a6_stage_empties_tmp_and_sets_tmpdir, t_g2_tmp_emptied_before_space_check, t_a5_stage_stops_setup_missing, t_a4_stale_temp_names_in_runtime_ignored,
         t_a4_stale_png_stream_and_validate_removed, t_d5_clear_check_found_accepted, t_d11_drill_genesis_refuses_existing_ledger, t_d11_session_download_names_kept, t_d11_local_download_checked_at_go, t_d11_link_copy_download_keeps_the_head, t_d11_head_download_slips_and_no_block, t_d11_session_slip_voids_only_its_name, t_d11_clear_check_routes_found_only_to_its_find, t_d5_settle_root_mode_link_and_file_targets, t_d11_stop_block_sticky_only_for_handback_c, t_d11_on_found_handback_and_absent, t_d11_found_raw_path_rules, t_maint2_inventory_rehashed_at_attest, t_d11_parse_raw_edges, t_gap02_files_found_before_settle, t_gap04_moved_pending_foreign_copy_forks, t_c1_post_failure_finishes_pending_halt_first, t_d5_kit_in_use_never_checks, t_d5_halted_kit_never_checks, t_commit_entry_then_parts, t_commit_duplicates_same_md5_kept, t_commit_fork_foreign_md5,
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
         t_d4_parse_raw_rules, t_d4_found_raw_search_and_listing_objects, t_d4_swapped_elements_assigned_by_title,
         t_d3_fourth_slip_stops_slip_limit, t_s03_short_download_refinds_real_fork_keeps_bytes,
         t_commit_identical_parts_confirmed, t_op02_reprint_has_no_upload_lines, t_opx01_restore_work_writes_kept,
         t_s05_png_changed_before_part_write_halts, t_t6_finish_refuses_entry_that_is_not_pending,
         t_t9_empty_transcript_refused, t_opx09_refused_stop_names_the_file,
         t_maint2_tools_none_refused_inventory_file_accepted, t_int_r2_03_interrupt_gets_conversation_id,
         t_d5_placement_accepts_equal_or_moves_aside, t_d16_settle_moves_readonly_target_aside,
         t_s07_runner_loaded_from_hashed_bytes, t_opx02_mistyped_id_refinds_then_commits, t_opx03_size_slip_refinds,
         t_t8_session_download_missing_refinds, t_d3_refusals_bounded_then_slip_limit,
         t_d3_refused_count_resets_per_block, t_d4_raw_invalid_reasked, t_op03_raw_file_consumed,
         t_d4_found_raw_world_swapped, t_s09_download_parent_exists_when_printed,
         t_gap08_render_removes_stale_download_target, t_maint2_inventory_sha_checked,
         t_opx07_stage_death_stop_names_real_head_and_kit, t_gap05_block_ahead_invalidates_cache,
         t_gap12_halt_removed_out_of_procedure_restores, t_d5_damaged_halt_stops_unclassified,
         t_d5_refused_clear_kit_keeps_cache, t_d5_found_answer_while_halted_print_stop, t_d5_stale_hint_never_checks,
         t_d5_clear_check_bounded, t_gap08_clear_moves_attest_and_inbox,
         t_d5_wait_approval_in_clearing_restore, t_d5_halted_restore_no_cleared_local,
         t_d16_stage_refuses_low_space_before_runner, t_opx05_final_message_any_characters_verbatim,
         t_opx05_empty_final_message_accepted, t_opx05_oversize_final_message_stops, t_maint2_tools_file_link_refused,
         t_maint2_generation_record_tools_and_o63_note, t_maint2_s_v_entries_archive_message_and_tools,
         t_s01_setup_failed_log_uploaded_without_kit_config, t_s04_pending_post_resumed_before_next_commit,
         t_d5_post_action_halt_cleared_same_boot,
         t_printed_blocks_grammar_and_paths]


SLOW = ('t_maint2_s_v_entries_archive_message_and_tools', 't_opx05_empty_final_message_accepted',   # run first
        't_opx05_final_message_any_characters_verbatim', 't_maint2_tools_file_link_refused',
        't_maint2_generation_record_tools_and_o63_note', 't_d11_head_download_slips_and_no_block',
        't_d11_clear_check_routes_found_only_to_its_find', 't_d16_stage_refuses_low_space_before_runner')


def one_test(arg):
    """Run one test by name (in a worker process when jobs > 1): (name, failure or None, the blocks it printed)."""
    global WORK
    name, WORK = arg
    env0, n0, t0 = dict(os.environ), len(PRINTED), time.time()
    fn = {f.__name__: f for f in TESTS}[name]
    try:
        fn()
        bad = None
    except Exception as e:                      # noqa: BLE001 - recorded per test
        import traceback
        bad = {'test': name, 'error': '%s: %s' % (type(e).__name__, e), 'trace': traceback.format_exc()[-1500:]}
    finally:
        os.environ.clear()
        os.environ.update(env0)
    if 'seen' in sys.modules:                   # the runtime half of L1 (a worker's codes are kept per pid)
        sys.modules['seen'].dump()
    return name, bad, PRINTED[n0:], round(time.time() - t0, 1)


def run(only=None, work=None, jobs=1):
    """GAP-10 (D14): with jobs > 1 the tests run in a process pool; the grammar test over every printed block last."""
    global WORK
    WORK = work or tempfile.mkdtemp(prefix='test_vio_')
    os.makedirs(WORK, exist_ok=True)
    last = [t_s07_runner_loaded_from_hashed_bytes, t_printed_blocks_grammar_and_paths]   # in this process, after
    names = sorted((f.__name__ for f in TESTS if f not in last and (not only or f.__name__ in only)),
                   key=lambda n: n not in SLOW)                         # the pool (a World removes __pycache__)
    ff = os.environ.get('CPSVM2_FAILFAST')     # run_tests.py --failfast (the mutation harness): serial, stop at one
    if jobs > 1 and not ff:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            res = list(ex.map(one_test, [(n, WORK) for n in names]))
        for r in res:
            PRINTED.extend(r[2])
    else:
        res = []
        for n in names:
            res.append(one_test((n, WORK)))
            if ff and res[-1][1]:
                break
    for f in last:
        if (not only or f.__name__ in only) and not (ff and any(r[1] for r in res)):
            res.append(one_test((f.__name__, WORK)))
    failed = [r[1] for r in res if r[1]]
    return {'name': 'test_vio', 'tests': len(res), 'passed': len(res) - len(failed), 'failed': [f['test'] for f in failed],
            'detail': failed, 'counts': {'blocks_printed': len(PRINTED),
                                         'slowest': sorted(([r[3], r[0]] for r in res), reverse=True)[:12]}}


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
