"""Build the CPS session kit (SESSION_KIT_<v>.zip) byte for byte reproducibly, without the maintainer uploading a binary.

Why: the maintainer can put a file into Drive only by writing its content into the upload call. Binary files travel
as base64 text and pick up slips (see verify_drive_files.py). Drive copies files faithfully, and so do the operator's
downloads and uploads. So:
  - the kit's text members (JSON, Markdown) travel as plain-text bundle parts, each uploaded twice (copies A and B);
  - its binary members (the qualification source workbooks) are copied inside Drive by the maintainer;
  - the operator rebuilds the zip on its VM with this script, which takes each text member from whichever copy matches
    its sha256, checks every binary member's sha256, and writes the zip deterministically. The maintainer built the same
    zip first, so the expected sha256 is known in advance and is checked here.

Zip format: stored (no compression), members sorted by path after SHA256SUMS, every timestamp 1980-01-01 00:00:00,
mode 0644, Unix creator, no directory entries, no comment. SHA256SUMS holds "<sha256>  <path>" for every other
member, sorted by path. The same members give the same bytes on any Python 3.8 or later.

Bundle part (UTF-8 text):
  CPS-KIT-BUNDLE v1 kit=<kit name> sha256=<kit sha256> part=<i>/<n> copy=<A|B>
  @@ text <path> <bytes> <sha256>
  <the member's exact bytes>
  @@ binary <path> <bytes> <sha256> <file name in the binaries folder>
  @@ end
A member's content runs from the line after its header to the newline before the next line that starts with "@@ ";
that one newline is the separator. No member may contain a line starting with "@@ " (pack refuses it).

Usage:
  python3 -I -B make_kit.py build TREE OUT.zip
      zip every regular file under TREE (TREE must not hold SHA256SUMS, symlinks or special files)
  python3 -I -B make_kit.py pack TREE OUTDIR --kit-name NAME [--part-bytes 30000] [--binary-name PATH=NAME ...]
      maintainer side: build OUTDIR/NAME, then write OUTDIR/<stem>_part<i>of<n>_<A|B>.txt; files that are not UTF-8
      text, or are listed with --binary-name, become binary entries (named by --binary-name, default the path's basename)
  python3 -I -B make_kit.py assemble OUT.zip --binaries DIR --expect SHA256 PART [PART ...]
      operator side: rebuild the kit from the parts (both copies) and the binaries folder; the zip is written only when
      its sha256 equals --expect
Exit codes: 0 done; 1 a check failed (the output names the member or file); 2 usage error.
Only names, sizes and hashes are printed, never member content.
"""
import argparse
import hashlib
import io
import os
import re
import stat
import sys
import zipfile

SUMS = 'SHA256SUMS'
EPOCH = (1980, 1, 1, 0, 0, 0)
HEAD = re.compile(r'CPS-KIT-BUNDLE v1 kit=(\S+) sha256=([0-9a-f]{64}) part=(\d+)/(\d+) copy=([AB])')
MEMBER = re.compile(r'@@ (text|binary) (\S+) (\d+) ([0-9a-f]{64})(?: (\S+))?')
NAME = re.compile(r'[A-Za-z0-9._-]+')


class Fail(Exception):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


def safe_path(p):
    parts = p.split('/')
    return bool(p) and not p.startswith('/') and '\\' not in p and '\0' not in p and \
        all(x not in ('', '.', '..') for x in parts) and all(re.fullmatch(r'[A-Za-z0-9._-]+', x) for x in parts)


def zip_bytes(members):
    """The deterministic zip of {path: bytes} (SHA256SUMS added here)."""
    if SUMS in members:
        raise Fail(f'{SUMS} must not be given as a member')
    for p in members:
        if not safe_path(p):
            raise Fail(f'unsafe member path {p!r}')
    sums = ''.join(f'{sha(members[p])}  {p}\n' for p in sorted(members)).encode('ascii')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as z:
        for p, data in [(SUMS, sums)] + [(p, members[p]) for p in sorted(members)]:
            zi = zipfile.ZipInfo(p, date_time=EPOCH)
            zi.compress_type = zipfile.ZIP_STORED
            zi.create_system = 3
            zi.create_version = 20
            zi.extract_version = 20
            zi.external_attr = (stat.S_IFREG | 0o644) << 16
            z.writestr(zi, data)
    return buf.getvalue()


def read_tree(tree):
    members = {}
    for dp, dns, fns in os.walk(tree, followlinks=False):
        dns.sort()
        for n in dns:
            if os.path.islink(os.path.join(dp, n)):
                raise Fail(f'symlink {os.path.relpath(os.path.join(dp, n), tree)}')
        for n in sorted(fns):
            full = os.path.join(dp, n)
            st = os.lstat(full)
            rel = os.path.relpath(full, tree).replace(os.sep, '/')
            if not stat.S_ISREG(st.st_mode):
                raise Fail(f'not a regular file: {rel}')
            with open(full, 'rb') as f:
                members[rel] = f.read()
    if not members:
        raise Fail('the tree holds no files')
    return members


def write_new(path, data):
    with open(path, 'xb') as f:
        f.write(data)


def is_text(b):
    try:
        t = b.decode('utf-8')
    except UnicodeDecodeError:
        return False
    return '\0' not in t and '\r' not in t


def cmd_build(a):
    z = zip_bytes(read_tree(a.tree))
    write_new(a.out, z)
    print(f'kit {os.path.basename(a.out)}: {len(z)} bytes, sha256 {sha(z)}')
    return 0


def cmd_pack(a):
    if not NAME.fullmatch(a.kit_name) or not a.kit_name.endswith('.zip'):
        raise Fail('--kit-name must be a plain file name ending in .zip')
    members = read_tree(a.tree)
    names = {}
    for spec in a.binary_name or []:
        p, _, n = spec.partition('=')
        if p not in members or not NAME.fullmatch(n):
            raise Fail(f'--binary-name {spec!r}: no such member, or not a plain file name')
        names[p] = n
    z = zip_bytes(members)
    kit_sha = sha(z)
    os.makedirs(a.outdir, exist_ok=True)
    write_new(os.path.join(a.outdir, a.kit_name), z)
    entries = []
    for p in sorted(members):
        b = members[p]
        if p in names or not is_text(b):
            n = names.get(p, p.rsplit('/', 1)[-1])
            entries.append((f'@@ binary {p} {len(b)} {sha(b)} {n}\n'.encode('ascii'), b''))
        else:
            if re.search(rb'(^|\n)@@ ', b):
                raise Fail(f'{p}: a line starts with "@@ "')
            entries.append((f'@@ text {p} {len(b)} {sha(b)}\n'.encode('ascii'), b + b'\n'))
    bins = [e for e in entries if e[0].startswith(b'@@ binary')]
    texts = [e for e in entries if e[0].startswith(b'@@ text')]
    parts, cur = [], []
    for e in texts:
        size = sum(len(h) + len(c) for h, c in cur)
        if cur and size + len(e[0]) + len(e[1]) > a.part_bytes:
            parts.append(cur)
            cur = []
        cur.append(e)
    parts.append(cur)
    parts[-1] = parts[-1] + bins
    stem = a.kit_name[:-4]
    n = len(parts)
    for i, part in enumerate(parts, 1):
        body = b''.join(h + c for h, c in part) + b'@@ end\n'
        for copy in 'AB':
            head = f'CPS-KIT-BUNDLE v1 kit={a.kit_name} sha256={kit_sha} part={i}/{n} copy={copy}\n'.encode('ascii')
            name = f'{stem}_part{i}of{n}_{copy}.txt'
            write_new(os.path.join(a.outdir, name), head + body)
            print(f'part {name}: {len(head) + len(body)} bytes, sha256 {sha(head + body)}')
    print(f'kit {a.kit_name}: {len(z)} bytes, sha256 {kit_sha}; {len(texts)} text and {len(bins)} binary members in {n} part(s)')
    return 0


def parse_part(raw, label):
    """(header fields, [(kind, path, size, sha, binname, content-or-None)]); damaged entries are skipped, not trusted."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        text = raw.decode('utf-8', 'replace')
    lines = text.split('\n')
    m = HEAD.fullmatch(lines[0]) if lines else None
    head = m.groups() if m else None
    entries = []
    idx = [i for i, ln in enumerate(lines) if ln.startswith('@@ ')]
    for k, i in enumerate(idx):
        ln = lines[i]
        if ln == '@@ end':
            continue
        mm = MEMBER.fullmatch(ln)
        if not mm:
            print(f'  {label}: line {i + 1} is a damaged member header (skipped)', flush=True)
            continue
        kind, path, size, want, binname = mm.group(1), mm.group(2), int(mm.group(3)), mm.group(4), mm.group(5)
        if kind == 'text':
            end = idx[k + 1] if k + 1 < len(idx) else len(lines)
            content = '\n'.join(lines[i + 1:end]).encode('utf-8')
            entries.append((kind, path, size, want, None, content))
        elif binname:
            entries.append((kind, path, size, want, binname, None))
    return head, entries


def cmd_assemble(a):
    if not re.fullmatch(r'[0-9a-f]{64}', a.expect):
        raise Fail('--expect must be 64 lowercase hex digits')
    heads, cands = [], {}
    for pp in a.parts:
        with open(pp, 'rb') as f:
            raw = f.read()
        head, entries = parse_part(raw, os.path.basename(pp))
        print(f'part {os.path.basename(pp)}: {len(raw)} bytes, sha256 {sha(raw)}, header {"ok" if head else "DAMAGED"}, '
              f'{len(entries)} member entries', flush=True)
        if head:
            heads.append(head)
        for e in entries:
            cands.setdefault(e[1], []).append(e)
    if not heads:
        raise Fail('no part has a readable header')

    def most_common(values):
        return max(sorted(set(values)), key=values.count)
    # A slip can damage one header; the headers only name the kit and the part count. The guarantee is --expect.
    kit_name = most_common([h[0] for h in heads])
    nparts = int(most_common([h[3] for h in heads]))
    declared = sorted({h[1] for h in heads})
    if declared != [a.expect]:
        print(f'  note: the part headers declare kit sha256 {", ".join(declared)}; --expect is {a.expect}', flush=True)
    seen_parts = {int(h[2]) for h in heads if int(h[3]) == nparts}
    if not seen_parts >= set(range(1, nparts + 1)):
        raise Fail(f'parts missing: have {sorted(seen_parts)} of {nparts}')
    members, problems = {}, []
    for path in sorted(cands):
        if not safe_path(path):
            problems.append(f'{path[:80]!r}: unsafe path (a damaged header?)')
            continue
        good = {}
        for kind, _, size, want, binname, content in cands[path]:
            if kind == 'text':
                if content is not None and len(content) == size and sha(content) == want:
                    good.setdefault(want, content)
            else:
                if not NAME.fullmatch(binname):
                    continue
                fp = os.path.join(a.binaries, binname)
                if os.path.isfile(fp):
                    with open(fp, 'rb') as f:
                        b = f.read()
                    if len(b) == size and sha(b) == want:
                        good.setdefault(want, b)
        if len(good) == 1:
            members[path] = next(iter(good.values()))
        elif not good:
            kinds = {c[0] for c in cands[path]}
            what = 'binary file missing or its sha256 differs' if kinds == {'binary'} else 'no copy matches its sha256'
            problems.append(f'{path}: {what}')
        else:
            problems.append(f'{path}: the copies disagree')
    for p in problems:
        print(f'  FAILED {p}', flush=True)
    if problems:
        raise Fail(f'{len(problems)} member(s) could not be rebuilt; the kit was not written')
    z = zip_bytes(members)
    got = sha(z)
    print(f'kit {kit_name}: {len(members) + 1} members, {len(z)} bytes, sha256 {got}', flush=True)
    if got != a.expect:
        raise Fail(f'the rebuilt kit sha256 {got} differs from --expect {a.expect}; the kit was not written')
    write_new(a.out, z)
    print(f'written {a.out}')
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    b.add_argument('tree')
    b.add_argument('out')
    p = sub.add_parser('pack')
    p.add_argument('tree')
    p.add_argument('outdir')
    p.add_argument('--kit-name', required=True)
    p.add_argument('--part-bytes', type=int, default=30000)
    p.add_argument('--binary-name', action='append')
    s = sub.add_parser('assemble')
    s.add_argument('out')
    s.add_argument('--binaries', required=True)
    s.add_argument('--expect', required=True)
    s.add_argument('parts', nargs='+')
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        return {'build': cmd_build, 'pack': cmd_pack, 'assemble': cmd_assemble}[a.cmd](a)
    except FileExistsError as e:
        print(f'FAILED: {e.filename} already exists', file=sys.stderr)
        return 1
    except (Fail, OSError) as e:
        print(f'FAILED: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
