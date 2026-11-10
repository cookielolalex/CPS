"""Carry a small binary file into the CPS Drive folder as plain text that survives the maintainer's copy slips.

Why: the maintainer can put a file into Drive only by writing its content into the upload call. Binary files travel
as base64 text, and that text sometimes comes out with a character changed (2026-11-09: 8 of 27 workbooks; two had
more slips than deploy/verify_drive_files.py can repair). This tool makes such slips recoverable:
- the file is written as base64 in short lines, and each line carries the CRC-32 of its own text;
- the whole file is written twice, as copies A and B, normally in two uploads;
- decode takes, for each line, a copy whose CRC matches; if none matches, a line on which both copies agree; and
  otherwise searches every single-character change of each copy's line for one that matches either copy's CRC;
- the rebuilt file is written only when its sha256 equals the expected one (given directly, or read from the
  FOLDER_MANIFEST.md row of its path), so a written file is byte for byte the released file.

Usage:
  python3 textcarry.py encode FILE OUTDIR [--width 48]
      writes OUTDIR/<name>.carry_A.txt and OUTDIR/<name>.carry_B.txt
  python3 textcarry.py decode OUT (--expect SHA256 | --manifest FOLDER_MANIFEST.md --path MANIFEST_PATH) CARRY ...
      rebuilds the file from one or more carry files of the same file; never overwrites OUT
Exit 0 on success, 1 when the file cannot be rebuilt or does not match, 2 for usage errors.
"""
import argparse
import base64
import binascii
import hashlib
import os
import re
import sys
import zlib

B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='
HEAD = re.compile(r'^CPS-TEXTCARRY v1 name=(\S+) bytes=(\d+) sha256=([0-9a-f]{64}) lines=(\d+) copy=([AB])$')
ROW = re.compile(r'^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*`([0-9a-f]{64})`\s*\|', re.M)
SAFE_NAME = re.compile(r'^[A-Za-z0-9._-]+$')


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def crc(text):
    return '%08x' % (zlib.crc32(text.encode('ascii')) & 0xffffffff)


def encode(path, outdir, width=48):
    data = read_bytes(path)
    name = os.path.basename(path)
    if not SAFE_NAME.match(name):
        raise SystemExit(f'unsafe file name: {name}')
    chunks = [base64.b64encode(data[i:i + width]).decode('ascii') for i in range(0, len(data), width)] or ['']
    sha = hashlib.sha256(data).hexdigest()
    os.makedirs(outdir, exist_ok=True)
    written = []
    for copy in 'AB':
        lines = [f'CPS-TEXTCARRY v1 name={name} bytes={len(data)} sha256={sha} lines={len(chunks)} copy={copy}']
        lines += [f'{copy} {i:05d} {crc(c)} {c}' for i, c in enumerate(chunks)]
        lines.append('END')
        out = os.path.join(outdir, f'{name}.carry_{copy}.txt')
        with open(out, 'w', encoding='ascii', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        written.append(out)
    return written, sha, len(chunks)


def parse(text):
    """(header fields or None, {index: (crc, chunk)}) of one carry file; damaged lines are kept by position."""
    rows = [r for r in text.replace('\r', '').split('\n') if r.strip()]
    head = None
    body = []
    for r in rows:
        m = HEAD.match(r)
        if m and head is None:
            head = {'name': m.group(1), 'bytes': int(m.group(2)), 'sha256': m.group(3), 'lines': int(m.group(4))}
            continue
        if r == 'END' or r.startswith('CPS-TEXTCARRY'):
            continue
        body.append(r)
    # Lines are placed by position when the copy has exactly the line count its header names (a slip cannot then
    # misplace a line); otherwise by their own index field. A line whose fields are damaged is still offered as a
    # candidate: its chunk can be repaired or matched against the other copy.
    by_position = head is not None and len(body) == head['lines']
    out = {}
    for pos, r in enumerate(body):
        parts = r.split(' ')
        if len(parts) != 4:
            continue
        _, sidx, cr, chunk = parts
        if by_position:
            idx = pos
        elif sidx.isdigit():
            idx = int(sidx)
        else:
            continue
        out.setdefault(idx, (cr.lower(), chunk))
    return head, out


def one_change(chunk, targets):
    """A single-character change of chunk whose CRC is in targets, or None."""
    for i, old in enumerate(chunk):
        for ch in B64:
            if ch == old:
                continue
            cand = chunk[:i] + ch + chunk[i + 1:]
            if crc(cand) in targets:
                return cand
    return None


def decode(carry_texts, expect):
    heads = []
    copies = []
    for t in carry_texts:
        h, rows = parse(t)
        if h:
            heads.append(h)
        copies.append(rows)
    notes = []
    if heads:
        n_lines = max(set(h['lines'] for h in heads), key=[h['lines'] for h in heads].count)
    else:
        # Both headers damaged: the line count comes from the highest index seen; the expected sha256 still decides.
        n_lines = 1 + max((i for c in copies for i in c), default=-1)
        notes.append('no readable header in any copy; line count taken from the line indexes')
    if n_lines <= 0:
        return None, notes + ['no lines found']
    chunks = []
    for i in range(n_lines):
        cands = [c[i] for c in copies if i in c]
        good = next((ch for cr, ch in cands if crc(ch) == cr), None)
        if good is None:
            texts = [ch for _, ch in cands]
            same = next((t for t in texts if texts.count(t) >= 2), None)
            if same is not None:
                good = same
                notes.append(f'line {i}: copies agree, CRC fields damaged')
            else:
                targets = set(cr for cr, _ in cands)
                for _, ch in cands:
                    fixed = one_change(ch, targets)
                    if fixed is not None:
                        good = fixed
                        notes.append(f'line {i}: repaired one character')
                        break
        else:
            if any(crc(ch) != cr for cr, ch in cands):
                notes.append(f'line {i}: one copy damaged, the other used')
        if good is None:
            return None, notes + [f'line {i}: no copy and no single-character repair matches its CRC']
        chunks.append(good)
    try:
        data = b''.join(base64.b64decode(c, validate=True) for c in chunks)
    except (binascii.Error, ValueError) as e:
        return None, notes + [f'base64 decode failed: {e}']
    got = hashlib.sha256(data).hexdigest()
    if got != expect:
        return None, notes + [f'rebuilt sha256 {got} does not equal the expected {expect}']
    return data, notes


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('encode')
    e.add_argument('file')
    e.add_argument('outdir')
    e.add_argument('--width', type=int, default=48)
    d = sub.add_parser('decode')
    d.add_argument('out')
    d.add_argument('carry', nargs='+')
    d.add_argument('--expect')
    d.add_argument('--manifest')
    d.add_argument('--path')
    a = ap.parse_args(argv)
    if a.cmd == 'encode':
        if a.width < 3 or a.width % 3:
            print('--width must be a positive multiple of 3', file=sys.stderr)
            return 2
        files, sha, n = encode(a.file, a.outdir, a.width)
        print(f'sha256 {sha}, {n} lines per copy')
        for f in files:
            print(f'wrote {f} ({os.path.getsize(f)} bytes)')
        return 0
    if bool(a.expect) == bool(a.manifest):
        print('give either --expect or --manifest with --path', file=sys.stderr)
        return 2
    expect = a.expect
    if a.manifest:
        if not a.path:
            print('--manifest needs --path', file=sys.stderr)
            return 2
        rows = {p: h for p, _, h in ROW.findall(read_bytes(a.manifest).decode('utf-8', 'replace'))}
        if a.path not in rows:
            print(f'{a.path} is not in the manifest', file=sys.stderr)
            return 2
        expect = rows[a.path]
    if not re.fullmatch(r'[0-9a-f]{64}', expect or ''):
        print('the expected sha256 must be 64 lowercase hex characters', file=sys.stderr)
        return 2
    if os.path.lexists(a.out):
        print(f'{a.out} already exists; not overwritten', file=sys.stderr)
        return 2
    texts = [read_bytes(p).decode('ascii', 'replace') for p in a.carry]
    data, notes = decode(texts, expect)
    for n in notes:
        print(n)
    if data is None:
        print('NOT REBUILT')
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'xb') as f:
        f.write(data)
    print(f'REBUILT {a.out} ({len(data)} bytes, sha256 {expect})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
