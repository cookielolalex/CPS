"""Tests for make_kit.py on invented data. Run: python3 -I -B deploy/test_make_kit.py"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, 'make_kit.py')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def rb(path):
    with open(path, 'rb') as f:
        return f.read()


def wb(path, data):
    with open(path, 'wb') as f:
        f.write(data)


def wt(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def run(*args, py=None):
    p = subprocess.run([py or sys.executable, '-I', '-B', TOOL] + list(args), capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def invented_tree(root):
    files = {
        'RELEASE.json': json.dumps({'schema': 'x', 'status': 'RELEASED_FOR_QUALIFICATION', 'note': '發明的測試資料'},
                                   ensure_ascii=False, indent=1) + '\n',
        'VM_HELPER_CONFIG.json': '{\n "schema": "cps.vm-helper-config.v1"\n}\n',
        'tables/glossary_X.json': json.dumps({'GL': ['接地', '漏電斷路器']}, ensure_ascii=False, indent=1) + '\n',
        'qualification/JOBS.json': '{"cases": []}',
        'qualification/jobs/9990001/JOB.json': json.dumps({'case_id': '9990001', 'project_name': '虛構工程'},
                                                          ensure_ascii=False, indent=1) + '\n',
        'qualification/jobs/9990001/JOB_TITLE.json': '\n\n{"job_title": "虛構"}\n\n',
        'sentinels/SENTINEL_x.json': '',
    }
    for p, t in files.items():
        os.makedirs(os.path.dirname(os.path.join(root, p)) or root, exist_ok=True)
        with open(os.path.join(root, p), 'w', encoding='utf-8', newline='') as f:
            f.write(t)
    blob = bytes(range(256)) * 300 + b'PK\x03\x04 not really a workbook'
    with open(os.path.join(root, 'qualification/jobs/9990001/source.xls'), 'wb') as f:
        f.write(blob)
    blob2 = b'\xd0\xcf\x11\xe0' + bytes(5000)
    os.makedirs(os.path.join(root, 'qualification/jobs/9990002'))
    with open(os.path.join(root, 'qualification/jobs/9990002/source.xlsx'), 'wb') as f:
        f.write(blob2)
    return {'qualification/jobs/9990001/source.xls': ('9990001_source.xls', blob),
            'qualification/jobs/9990002/source.xlsx': ('9990002_source.xlsx', blob2)}


class MakeKitTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='mk_')
        self.tree = os.path.join(self.d, 'tree')
        self.bins = invented_tree(self.tree)
        self.out = os.path.join(self.d, 'out')
        args = ['pack', self.tree, self.out, '--kit-name', 'SESSION_KIT_T1.zip', '--part-bytes', '300']
        for p, (n, _) in self.bins.items():
            args += ['--binary-name', f'{p}={n}']
        rc, o = run(*args)
        self.assertEqual(rc, 0, o)
        with open(os.path.join(self.out, 'SESSION_KIT_T1.zip'), 'rb') as f:
            self.kit = f.read()
        self.kit_sha = sha(self.kit)
        self.parts = sorted(os.path.join(self.out, n) for n in os.listdir(self.out) if n.endswith('.txt'))
        self.bindir = os.path.join(self.d, 'bins')
        os.makedirs(self.bindir)
        for p, (n, b) in self.bins.items():
            with open(os.path.join(self.bindir, n), 'wb') as f:
                f.write(b)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def assemble(self, parts=None, expect=None, name='rebuilt.zip'):
        dest = os.path.join(self.d, name)
        rc, o = run('assemble', dest, '--binaries', self.bindir, '--expect', expect or self.kit_sha, *(parts or self.parts))
        return rc, o, dest

    def slip(self, path, member_path, copy_to):
        """Change one character inside a member's text in one part (a transcription slip)."""
        with open(path, 'rb') as f:
            raw = f.read()
        i = raw.index(f'@@ text {member_path} '.encode())
        j = raw.index(b'\n', i) + 1
        k = j + 2
        new = raw[:k] + (b'Z' if raw[k:k + 1] != b'Z' else b'Y') + raw[k + 1:]
        with open(copy_to, 'wb') as f:
            f.write(new)

    def test_parts_written_in_two_copies(self):
        a = [p for p in self.parts if p.endswith('_A.txt')]
        b = [p for p in self.parts if p.endswith('_B.txt')]
        self.assertEqual(len(a), len(b))
        self.assertGreater(len(a), 1, 'the small --part-bytes should split the bundle')

    def test_round_trip(self):
        rc, o, dest = self.assemble()
        self.assertEqual(rc, 0, o)
        with open(dest, 'rb') as f:
            self.assertEqual(f.read(), self.kit)

    def test_build_equals_pack(self):
        dest = os.path.join(self.d, 'built.zip')
        rc, o = run('build', self.tree, dest)
        self.assertEqual(rc, 0, o)
        with open(dest, 'rb') as f:
            self.assertEqual(f.read(), self.kit)

    def test_one_copy_only_is_enough(self):
        rc, o, _ = self.assemble(parts=[p for p in self.parts if p.endswith('_B.txt')])
        self.assertEqual(rc, 0, o)

    def test_slip_in_one_copy_recovered(self):
        a = [p for p in self.parts if p.endswith('_A.txt')]
        target = next(p for p in a if b'@@ text RELEASE.json' in rb(p))
        self.slip(target, 'RELEASE.json', target)
        rc, o, dest = self.assemble()
        self.assertEqual(rc, 0, o)
        with open(dest, 'rb') as f:
            self.assertEqual(sha(f.read()), self.kit_sha)

    def test_slip_in_both_copies_fails_and_writes_nothing(self):
        for p in self.parts:
            if b'@@ text RELEASE.json' in rb(p):
                self.slip(p, 'RELEASE.json', p)
        rc, o, dest = self.assemble()
        self.assertEqual(rc, 1, o)
        self.assertIn('RELEASE.json: no copy matches its sha256', o)
        self.assertFalse(os.path.exists(dest))

    def test_damaged_header_line_in_one_copy(self):
        a = [p for p in self.parts if p.endswith('_A.txt')]
        raw = rb(a[0])
        raw = raw.replace(b'CPS-KIT-BUNDLE v1', b'CPS-KIT-BUNDLE v7', 1)
        wb(a[0], raw)
        rc, o, _ = self.assemble()
        self.assertEqual(rc, 0, o)

    def test_slipped_header_sha_in_one_copy(self):
        a = [p for p in self.parts if p.endswith('_A.txt')]
        raw = rb(a[0])
        raw = raw.replace(self.kit_sha.encode(), ('0' if self.kit_sha[0] != '0' else '1').encode() + self.kit_sha[1:].encode(), 1)
        wb(a[0], raw)
        rc, o, _ = self.assemble()
        self.assertEqual(rc, 0, o)
        self.assertIn('note: the part headers declare', o)

    def test_member_path_slip_in_one_copy_recovers(self):
        """MK-1 (MAINT-6): a slip in one copy's member path (NOTE.mx, or the unsafe NOT~.md) while copy B is intact;
        the member is rebuilt under its real path. Two members with one content (two empty files) stay two members."""
        wt(os.path.join(self.tree, 'NOTE.md'), 'an invented note\n')
        wt(os.path.join(self.tree, 'sentinels/SENTINEL_y.json'), '')
        out = os.path.join(self.d, 'mk1')
        rc, o = run('pack', self.tree, out, '--kit-name', 'K.zip', '--part-bytes', '300',
                    *['--binary-name=%s=%s' % (p, n) for p, (n, _) in self.bins.items()])
        self.assertEqual(rc, 0, o)
        kit = rb(os.path.join(out, 'K.zip'))
        parts = sorted(os.path.join(out, n) for n in os.listdir(out) if n.endswith('.txt'))
        a = next(p for p in parts if p.endswith('_A.txt') and b'@@ text NOTE.md ' in rb(p))
        clean = rb(a)
        for bad in ('NOTE.mx', 'NOT~.md'):
            wb(a, clean.replace(b'@@ text NOTE.md ', ('@@ text %s ' % bad).encode()))
            dest = os.path.join(self.d, bad + '.zip')
            rc, o = run('assemble', dest, '--binaries', self.bindir, '--expect', sha(kit), *parts)
            self.assertEqual(rc, 0, (bad, o))
            self.assertEqual(rb(dest), kit)

    def test_pack_refuses_duplicate_binary_names(self):
        """MK-2 (MAINT-6): a/src.xls and b/src.xls would share one binary file name; pack refuses and writes nothing."""
        t = os.path.join(self.d, 't2')
        for p in ('a', 'b'):
            os.makedirs(os.path.join(t, p))
            wb(os.path.join(t, p, 'src.xls'), b'\xd0\xcf' + p.encode() * 100)
        out = os.path.join(self.d, 'o2')
        rc, o = run('pack', t, out, '--kit-name', 'K.zip')
        self.assertEqual(rc, 1, o)
        self.assertIn('src.xls: two binary members would share one file name', o)
        self.assertFalse(os.path.exists(out) and os.listdir(out))

    def test_binary_mismatch_fails(self):
        n = self.bins['qualification/jobs/9990002/source.xlsx'][0]
        p = os.path.join(self.bindir, n)
        b = bytearray(rb(p))
        b[100] ^= 1
        wb(p, bytes(b))
        rc, o, dest = self.assemble()
        self.assertEqual(rc, 1, o)
        self.assertIn('source.xlsx: binary file missing or its sha256 differs', o)
        self.assertFalse(os.path.exists(dest))

    def test_binary_missing_fails(self):
        os.remove(os.path.join(self.bindir, self.bins['qualification/jobs/9990001/source.xls'][0]))
        rc, o, _ = self.assemble()
        self.assertEqual(rc, 1, o)

    def test_wrong_expect_fails_and_writes_nothing(self):
        wrong = ('f' if self.kit_sha[-1] != 'f' else 'e')
        rc, o, dest = self.assemble(expect=self.kit_sha[:-1] + wrong)
        self.assertEqual(rc, 1, o)
        self.assertFalse(os.path.exists(dest))

    def test_missing_part_fails(self):
        rc, o, _ = self.assemble(parts=[p for p in self.parts if 'part1of' not in p])
        self.assertEqual(rc, 1, o)

    def test_existing_output_not_overwritten(self):
        dest = os.path.join(self.d, 'exists.zip')
        wb(dest, b'keep')
        rc, o, _ = self.assemble(name='exists.zip')
        self.assertEqual(rc, 1, o)
        self.assertEqual(rb(dest), b'keep')

    def test_at_at_line_refused(self):
        p = os.path.join(self.tree, 'NOTE.md')
        wt(p, 'ok\n@@ text evil 1 ' + '0' * 64 + '\n')
        rc, o = run('pack', self.tree, os.path.join(self.d, 'o2'), '--kit-name', 'K.zip')
        self.assertEqual(rc, 1, o)

    def test_unsafe_names_refused(self):
        os.makedirs(os.path.join(self.tree, 'bad name'))
        wt(os.path.join(self.tree, 'bad name', 'x.json'), '{}')
        rc, o = run('build', self.tree, os.path.join(self.d, 'z.zip'))
        self.assertEqual(rc, 1, o)

    def test_symlink_refused(self):
        os.symlink('RELEASE.json', os.path.join(self.tree, 'link.json'))
        rc, o = run('build', self.tree, os.path.join(self.d, 'z.zip'))
        self.assertEqual(rc, 1, o)

    def test_zip_shape_matches_helper_rules(self):
        z = zipfile.ZipFile(io.BytesIO(self.kit))
        names = [i.filename for i in z.infolist()]
        self.assertEqual(names[0], 'SHA256SUMS')
        self.assertEqual(names[1:], sorted(names[1:]))
        for i in z.infolist():
            self.assertEqual(i.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(i.date_time, (1980, 1, 1, 0, 0, 0))
            self.assertEqual((i.external_attr >> 16) & 0o7777, 0o644)
            self.assertFalse(i.filename.endswith('/'))
        self.addCleanup(z.close)
        sums = z.read('SHA256SUMS').decode()
        listed = dict(reversed(re.fullmatch(r'([0-9a-f]{64})  (.+)', ln).groups()) for ln in sums.splitlines())
        self.assertEqual(set(listed), set(names[1:]))
        for n, h in listed.items():
            self.assertEqual(sha(z.read(n)), h)

    def test_helper_kit_reader_accepts(self):
        helper = os.path.join(HERE, 'vm', 'cps_vm.py')
        if not os.path.isfile(helper):
            self.skipTest('deploy/vm/cps_vm.py not present')
        with open(helper, encoding='utf-8') as f:
            src = f.read()
        m = re.search(r'\ndef kit_members\(zp\):.*?\n    return out\n', src, re.S)
        u = re.search(r'\ndef unsafe_name\(n\):.*?\n    return None\n', src, re.S)
        if not (m and u):
            self.skipTest('kit_members not found in the helper')
        ns = {}
        exec('import re, stat, zipfile, hashlib\n'
             'def sha_bytes(b): return hashlib.sha256(b).hexdigest()\n'
             'class H(Exception): pass\n'
             'def stop(code, *a, **k): raise H(code)\n' + u.group(0) + m.group(0), ns)
        kp = os.path.join(self.d, 'kit.zip')
        wb(kp, self.kit)
        members = ns['kit_members'](kp)
        self.assertIn('RELEASE.json', members)
        with zipfile.ZipFile(kp) as z:
            self.assertEqual(len(members), len(z.namelist()) - 1)

    def test_same_bytes_on_every_python(self):
        pys = [p for p in ('/usr/bin/python3.11', '/usr/bin/python3.12', '/usr/bin/python3.13', '/usr/local/bin/python3.13')
               if os.path.isfile(p)]
        if len(pys) < 2:
            self.skipTest('fewer than two Python versions here')
        got = set()
        for i, py in enumerate(pys):
            dest = os.path.join(self.d, f'py{i}.zip')
            rc, o = run('build', self.tree, dest, py=py)
            self.assertEqual(rc, 0, f'{py}: {o}')
            got.add(sha(rb(dest)))
        self.assertEqual(got, {self.kit_sha}, pys)


if __name__ == '__main__':
    unittest.main(verbosity=2)
