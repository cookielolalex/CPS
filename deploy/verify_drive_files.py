"""Check files downloaded from the CPS Drive folder against its FOLDER_MANIFEST.md, and repair the maintainer's
upload copy-errors.

Why this exists: the maintainer can put a file into Drive only by writing its content into the upload call, so a
binary file travels as base64 text. A slip in that text changes one base64 character: the file keeps its size, but
2 bytes or fewer differ (found on 2026-11-09: 8 of 27 example workbooks had one or two such slips). Drive and the
operator's downloads and uploads move bytes faithfully, so files that users, the operator or Drive move are not
affected.

Usage:
  python3 verify_drive_files.py MANIFEST.md ROOT [--repair-to OUTDIR] [PATH ...]
ROOT holds the downloaded files at their manifest paths (for example ROOT/03_interview/examples/X.xlsx). With PATHs,
only those manifest paths are checked. Every checked file is reported as one of:
  ok            its sha256 equals the manifest's;
  MISSING       not found under ROOT;
  MISMATCH      differs, and --repair-to was not given;
  REPAIRED      a repaired copy was written to OUTDIR/<path>, with the base64 characters that were changed;
  NOT REPAIRED  differs, and no repair matched the manifest.
A repaired copy is written only when its sha256 equals the manifest's, so it is byte for byte the file the maintainer
released. The downloaded file is never changed.

How a repair is found. A binary file is modelled as the base64 text of the released file with a few characters
substituted. For a zip file (.xlsx, .docx, .zip), each part whose compressed data fails to inflate to its recorded
size and CRC-32 is searched separately: every single-character substitution over that part's data is tried until
the part checks out. Then the whole file must match the manifest's sha256; if it still does not, one more
substitution is searched outside the parts' data (headers, central directory). A file that is not a zip, or whose
parts cannot be read, gets a search for one substitution anywhere, if it is at most 64 KB. Text files (valid UTF-8)
are not searched: they are uploaded as text, not base64, so a slip there needs a new upload.
Exit 0 when every checked file is ok or repaired, 1 otherwise, 2 for usage errors.
"""
import argparse
import hashlib
import io
import itertools
import os
import re
import struct
import sys
import zipfile
import zlib

B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
WHOLE_FILE_LIMIT = 64 * 1024
MAX_CANDIDATES_PER_PART = 20
ROW = re.compile(r'^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*`([0-9a-f]{64})`\s*\|', re.M)


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def nchars(n):
    """Base64 characters whose bits fall inside n bytes (padding characters excluded)."""
    return (8 * n + 5) // 6


def get6(buf, i):
    bit = 6 * i
    b0 = bit >> 3
    w = buf[b0] << 8 | (buf[b0 + 1] if b0 + 1 < len(buf) else 0)
    return (w >> (10 - (bit & 7))) & 0x3f


def set6(buf, i, v):
    bit = 6 * i
    b0 = bit >> 3
    shift = 10 - (bit & 7)
    w = buf[b0] << 8 | (buf[b0 + 1] if b0 + 1 < len(buf) else 0)
    w = (w & ~(0x3f << shift) & 0xffff) | (v << shift)
    buf[b0] = w >> 8
    if b0 + 1 < len(buf):
        buf[b0 + 1] = w & 0xff


def chars_over(a, b, n):
    """Base64 character positions whose bits overlap bytes [a, b) of an n-byte file."""
    lo = max(0, (8 * a) // 6 - 1)
    hi = min(nchars(n), (8 * b) // 6 + 2)
    return [i for i in range(lo, hi) if (6 * i) // 8 < b and (6 * i + 5) // 8 >= a]


def zip_parts(buf):
    """(name, data_start, compressed_size, method, crc, size) of every part, or None if the zip cannot be read."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(bytes(buf)))
        parts = []
        for zi in zf.infolist():
            h = zi.header_offset
            if buf[h:h + 4] != b'PK\x03\x04':
                return None
            name_len, extra_len = struct.unpack('<HH', bytes(buf[h + 26:h + 30]))
            start = h + 30 + name_len + extra_len
            if start + zi.compress_size > len(buf) or zi.compress_type not in (0, 8):
                return None
            parts.append((zi.filename, start, zi.compress_size, zi.compress_type, zi.CRC, zi.file_size))
        return parts
    except Exception:
        return None


def part_ok(buf, part):
    _, start, csize, method, crc, size = part
    data = memoryview(buf)[start:start + csize]
    try:
        if method == 0:
            out = bytes(data)
        else:
            d = zlib.decompressobj(-15)
            out = d.decompress(data, size + 1)
            if not d.eof or d.unused_data or len(out) != size:
                return False
        return len(out) == size and zlib.crc32(out) & 0xffffffff == crc
    except zlib.error:
        return False


def part_candidates(buf, part):
    """Single substitutions (position, value) over the part's data that make the part check out."""
    _, start, csize, _, _, _ = part
    found = []
    for i in chars_over(start, start + csize, len(buf)):
        old = get6(buf, i)
        for v in range(64):
            if v == old:
                continue
            set6(buf, i, v)
            if part_ok(buf, part):
                found.append((i, v))
            set6(buf, i, old)
            if len(found) >= MAX_CANDIDATES_PER_PART:
                return found
    return found


def one_substitution(buf, want, positions):
    """A single substitution among positions that makes the sha256 equal want, or None. buf is left unchanged."""
    prefix = hashlib.sha256()
    done = 0
    for i in sorted(positions):
        b0 = (6 * i) >> 3
        if b0 > done:
            prefix.update(bytes(buf[done:b0]))
            done = b0
        old = get6(buf, i)
        tail = len(buf)
        for v in range(64):
            if v == old:
                continue
            set6(buf, i, v)
            h = prefix.copy()
            h.update(memoryview(buf)[b0:tail])
            hit = h.hexdigest() == want
            set6(buf, i, old)
            if hit:
                return (i, v)
    return None


def describe(fixes, original, parts):
    out = []
    for i, v in fixes:
        where = 'outside the parts\' data'
        for p in parts or []:
            if any(i == j for j in chars_over(p[1], p[1] + p[2], len(original))):
                where = 'part ' + p[0]
                break
        out.append(f'base64 character {i}: {B64[get6(original, i)]} -> {B64[v]} ({where})')
    return out


def repair(data, want):
    """(repaired bytes, list of changes) or (None, reason)."""
    buf = bytearray(data)
    try:
        data.decode('utf-8')
        return None, 'a text file (valid UTF-8): text is uploaded as text, not base64, so it needs a new upload'
    except UnicodeDecodeError:
        pass
    parts = zip_parts(buf) if data[:4] == b'PK\x03\x04' else None
    if parts is not None:
        bad = [p for p in parts if not part_ok(buf, p)]
        options = []
        for p in bad:
            c = part_candidates(buf, p)
            if not c:
                options = None
                break
            options.append(c)
        if options is not None:
            data_chars = set()
            for p in parts:
                data_chars.update(chars_over(p[1], p[1] + p[2], len(buf)))
            outside = [i for i in range(nchars(len(buf))) if i not in data_chars]
            for combo in itertools.product(*options):
                trial = bytearray(buf)
                for i, v in combo:
                    set6(trial, i, v)
                if sha256(trial) == want:
                    return bytes(trial), describe(combo, buf, parts)
                extra = one_substitution(trial, want, outside)
                if extra:
                    set6(trial, *extra)
                    return bytes(trial), describe(list(combo) + [extra], buf, parts)
    if len(buf) > WHOLE_FILE_LIMIT:
        return None, f'no repair found, and the file is larger than {WHOLE_FILE_LIMIT // 1024} KB for a full search'
    hit = one_substitution(buf, want, range(nchars(len(buf))))
    if hit:
        trial = bytearray(buf)
        set6(trial, *hit)
        return bytes(trial), describe([hit], buf, parts)
    return None, 'no repair matched the manifest (more slips than the search covers): needs a new upload'


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('manifest')
    ap.add_argument('root')
    ap.add_argument('--repair-to')
    ap.add_argument('paths', nargs='*')
    a = ap.parse_args(argv)
    try:
        text = open(a.manifest, 'rb').read()
    except OSError as e:
        print(f'cannot read the manifest: {e}', file=sys.stderr)
        return 2
    rows = ROW.findall(text.decode('utf-8', 'replace'))
    if not rows:
        print('no file rows found in the manifest', file=sys.stderr)
        return 2
    listed = {p: (int(n), h) for p, n, h in rows}
    unknown = [p for p in a.paths if p not in listed]
    if unknown:
        print('not in the manifest: ' + ', '.join(unknown), file=sys.stderr)
        return 2
    print(f'manifest {a.manifest}: sha256 {sha256(text)}, {len(rows)} files')
    counts = {}
    for path in (a.paths or [p for p, _, _ in rows]):
        size, want = listed[path]
        local = os.path.join(a.root, path)
        if not os.path.isfile(local):
            status, notes = 'MISSING', []
        else:
            data = open(local, 'rb').read()
            got = sha256(data)
            if got == want:
                status, notes = 'ok', []
            elif not a.repair_to:
                status, notes = 'MISMATCH', [f'sha256 {got}, expected {want}; size {len(data)}, expected {size}']
            elif len(data) != size:
                status, notes = 'NOT REPAIRED', [f'size {len(data)}, expected {size}: not a copying slip; needs a new upload']
            else:
                fixed, info = repair(data, want)
                if fixed is None:
                    status, notes = 'NOT REPAIRED', [f'sha256 {got}, expected {want}', info]
                else:
                    out = os.path.join(a.repair_to, path)
                    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
                    with open(out, 'wb') as f:
                        f.write(fixed)
                    status, notes = 'REPAIRED', [f'written to {out} (sha256 {sha256(fixed)})'] + info
        counts[status] = counts.get(status, 0) + 1
        print(f'{status:12} {path}', flush=True)
        for n in notes:
            print(f'             {n}', flush=True)
    print('summary: ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())))
    return 0 if set(counts) <= {'ok', 'REPAIRED'} else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
