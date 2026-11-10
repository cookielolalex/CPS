"""Tests of deploy/textcarry.py on invented data only. Run: python3 -I -B deploy/test_textcarry.py"""
import hashlib
import os
import random
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, 'textcarry.py')
sys.path.insert(0, HERE)
import textcarry as tc  # noqa: E402


def rb(p):
    with open(p, 'rb') as f:
        return f.read()


def rt(p):
    with open(p, encoding='ascii') as f:
        return f.read()


def wt(p, s):
    with open(p, 'w', encoding='ascii', newline='\n') as f:
        f.write(s)


def slip(text, line_no, col, ch):
    """Change one character of a given line (line_no counts the header as 0)."""
    lines = text.split('\n')
    s = lines[line_no]
    assert s[col] != ch
    lines[line_no] = s[:col] + ch + s[col + 1:]
    return '\n'.join(lines)


def chunk_col(text, line_no, k=0):
    """Column of the k-th character of the base64 chunk on a line."""
    s = text.split('\n')[line_no]
    return len(' '.join(s.split(' ')[:3])) + 1 + k


def other(c):
    return 'A' if c != 'A' else 'B'


class TextCarryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        rnd = random.Random(20261110)
        self.data = bytes(rnd.randrange(256) for _ in range(7491))
        self.src = os.path.join(self.d, 'invented_example.xlsx')
        with open(self.src, 'wb') as f:
            f.write(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()
        (self.a, self.b), _, self.n = tc.encode(self.src, os.path.join(self.d, 'carry'))
        self.ta, self.tb = rt(self.a), rt(self.b)

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args):
        return subprocess.run([sys.executable, '-I', '-B', TOOL, *args], capture_output=True, text=True)

    def decode(self, ta, tb, expect=None):
        return tc.decode([x for x in (ta, tb) if x is not None], expect or self.sha)

    def test_round_trip_both_copies(self):
        data, notes = self.decode(self.ta, self.tb)
        self.assertEqual(data, self.data)
        self.assertEqual(notes, [])

    def test_one_copy_suffices(self):
        self.assertEqual(self.decode(self.ta, None)[0], self.data)
        self.assertEqual(self.decode(None, self.tb)[0], self.data)

    def test_slip_in_one_copy_uses_the_other(self):
        ta = slip(self.ta, 5, chunk_col(self.ta, 5, 3), other(self.ta.split('\n')[5][chunk_col(self.ta, 5, 3)]))
        data, notes = self.decode(ta, self.tb)
        self.assertEqual(data, self.data)
        self.assertIn('line 4: one copy damaged, the other used', notes)

    def test_slips_in_both_copies_on_different_lines(self):
        ta = slip(self.ta, 3, chunk_col(self.ta, 3, 1), other(self.ta.split('\n')[3][chunk_col(self.ta, 3, 1)]))
        tb = slip(self.tb, 9, chunk_col(self.tb, 9, 7), other(self.tb.split('\n')[9][chunk_col(self.tb, 9, 7)]))
        self.assertEqual(self.decode(ta, tb)[0], self.data)

    def test_same_line_slipped_in_both_copies_is_repaired(self):
        line = 12
        ta = slip(self.ta, line, chunk_col(self.ta, line, 2), other(self.ta.split('\n')[line][chunk_col(self.ta, line, 2)]))
        tb = slip(self.tb, line, chunk_col(self.tb, line, 30), other(self.tb.split('\n')[line][chunk_col(self.tb, line, 30)]))
        data, notes = self.decode(ta, tb)
        self.assertEqual(data, self.data)
        self.assertIn(f'line {line - 1}: repaired one character', notes)

    def test_single_copy_with_one_slip_is_repaired(self):
        ta = slip(self.ta, 7, chunk_col(self.ta, 7, 10), other(self.ta.split('\n')[7][chunk_col(self.ta, 7, 10)]))
        self.assertEqual(self.decode(ta, None)[0], self.data)

    def test_slips_on_many_lines_of_one_copy(self):
        ta = self.ta
        for line in range(1, self.n + 1, 4):
            col = chunk_col(ta, line, 0)
            ta = slip(ta, line, col, other(ta.split('\n')[line][col]))
        data, _ = self.decode(ta, self.tb)
        self.assertEqual(data, self.data)
        data, _ = self.decode(ta, None)
        self.assertEqual(data, self.data)

    def test_crc_field_slip_in_both_copies_with_agreeing_chunks(self):
        line = 6
        ta = slip(self.ta, line, 8, 'f' if self.ta.split('\n')[line][8] != 'f' else 'e')
        tb = slip(self.tb, line, 9, 'f' if self.tb.split('\n')[line][9] != 'f' else 'e')
        data, notes = self.decode(ta, tb)
        self.assertEqual(data, self.data)
        self.assertIn(f'line {line - 1}: copies agree, CRC fields damaged', notes)

    def test_header_slip_in_one_copy(self):
        ta = slip(self.ta, 0, 4, 'X')
        self.assertEqual(self.decode(ta, self.tb)[0], self.data)

    def test_both_headers_damaged_still_rebuilds_from_expected_sha(self):
        ta = slip(self.ta, 0, 4, 'X')
        tb = slip(self.tb, 0, 5, 'Y')
        data, notes = self.decode(ta, tb)
        self.assertEqual(data, self.data)
        self.assertTrue(any('no readable header' in n for n in notes))

    def test_index_field_slip(self):
        ta = slip(self.ta, 4, 2, '9')
        self.assertEqual(self.decode(ta, None)[0], self.data)

    def test_two_slips_on_one_line_in_the_only_copy_fails(self):
        line = 5
        c1, c2 = chunk_col(self.ta, line, 1), chunk_col(self.ta, line, 20)
        ta = slip(self.ta, line, c1, other(self.ta.split('\n')[line][c1]))
        ta = slip(ta, line, c2, other(ta.split('\n')[line][c2]))
        data, notes = self.decode(ta, None)
        self.assertIsNone(data)
        self.assertIn(f'line {line - 1}: no copy and no single-character repair matches its CRC', notes)

    def test_wrong_expected_sha_writes_nothing(self):
        out = os.path.join(self.d, 'out', 'x.xlsx')
        r = self.run_tool('decode', out, self.a, self.b, '--expect', '0' * 64)
        self.assertEqual(r.returncode, 1)
        self.assertIn('NOT REBUILT', r.stdout)
        self.assertFalse(os.path.exists(out))

    def test_cli_round_trip_with_manifest_and_no_overwrite(self):
        man = os.path.join(self.d, 'FOLDER_MANIFEST.md')
        wt(man, '| Path | Bytes | sha256 |\n|---|---:|---|\n'
                f'| `03_interview/examples/invented_example.xlsx` | {len(self.data)} | `{self.sha}` |\n')
        out = os.path.join(self.d, 'out', 'invented_example.xlsx')
        args = ('decode', out, self.a, self.b, '--manifest', man, '--path', '03_interview/examples/invented_example.xlsx')
        r = self.run_tool(*args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rb(out), self.data)
        r = self.run_tool(*args)
        self.assertEqual(r.returncode, 2)
        self.assertIn('not overwritten', r.stderr)
        self.assertEqual(rb(out), self.data)

    def test_cli_usage_errors(self):
        out = os.path.join(self.d, 'o.bin')
        self.assertEqual(self.run_tool('decode', out, self.a).returncode, 2)
        self.assertEqual(self.run_tool('decode', out, self.a, '--expect', 'XYZ').returncode, 2)
        man = os.path.join(self.d, 'M.md')
        wt(man, 'no rows\n')
        self.assertEqual(self.run_tool('decode', out, self.a, '--manifest', man, '--path', 'p').returncode, 2)

    def test_encode_format(self):
        rows = self.ta.rstrip('\n').split('\n')
        self.assertTrue(rows[0].startswith('CPS-TEXTCARRY v1 name=invented_example.xlsx bytes=7491 sha256='))
        self.assertEqual(rows[-1], 'END')
        self.assertEqual(len(rows), self.n + 2)
        for i, r in enumerate(rows[1:-1]):
            cp, idx, cr, ch = r.split(' ')
            self.assertEqual((cp, int(idx), cr), ('A', i, tc.crc(ch)))
            self.assertLessEqual(len(ch), 64)
        self.assertEqual(self.tb.replace('\nB ', '\nA ').replace('copy=B', 'copy=A'), self.ta)

    def test_random_single_slips_per_copy(self):
        rnd = random.Random(7)
        for _ in range(25):
            ta, tb = self.ta, self.tb
            for which in ('a', 'b'):
                t = ta if which == 'a' else tb
                line = rnd.randrange(1, self.n + 1)
                s = t.split('\n')[line]
                col = rnd.randrange(len(s))
                ch = rnd.choice([c for c in tc.B64 + '0123456789abcdef' if c != s[col]])
                t = slip(t, line, col, ch)
                if which == 'a':
                    ta = t
                else:
                    tb = t
            data, notes = self.decode(ta, tb)
            self.assertEqual(data, self.data, notes)


if __name__ == '__main__':
    unittest.main(verbosity=1)
