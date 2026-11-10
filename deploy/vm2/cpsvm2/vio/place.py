"""Strict walk, job-folder snapshot (§3.8), placement from journal entries (§8.5.1), evict after FROZEN (§7.6) and the
placed-FROZEN.json removal (§7.7, §5.4 UNPLACE_FROZEN). Every walk is the strict v1mod.tree_list; JobLock is held only
for a walk, never while a runner command runs (IMP-12)."""
import hashlib
import json
import os
from pathlib import Path

from .v1compat import Halt, stop
from .v1mod import tree_list
from .v1reuse import (Archive, JobLock, Staging, check_ledger_identity, png_manifest_problem, png_set, remove_tree,
                      sha_bytes, sha_file)


def _cjson_sha(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                                     allow_nan=False).encode('ascii')).hexdigest()


def walk(path):
    """The strict tree of a folder that must exist (WALK_UNSUPPORTED_ENTRY otherwise)."""
    return tree_list(path)


def walk_output(path):
    """The strict tree of an AI output folder; [] when the folder does not exist."""
    return [] if not os.path.lexists(path) else tree_list(path)


def tree_sha(rows):
    return _cjson_sha(rows)


def snapshot(lay, job_dir):
    """§3.8 under JobLock: (job members as archive members, payload rows under job/, png files [[job/rel, mode, bytes,
    sha256]], png rels, snapshot tree sha256). Raises Halt PNG_MANIFEST_UNSAFE / WALK_UNSUPPORTED_ENTRY."""
    with JobLock(lay, job_dir):
        rows = walk(job_dir)
        rels = set(png_set(job_dir))
        root_mode = os.lstat(job_dir).st_mode & 0o777
    png = [['job/' + r[0], r[2], r[3], r[4]] for r in rows if r[0] in rels]
    if any(r[1] != 'file' for r in rows if r[0] in rels):
        raise Halt('STOP', 'PNG_MANIFEST_UNSAFE', 'a PNG entry is not a file')
    job = [['job', 'dir', root_mode, None, None]] + [['job/' + r[0]] + r[1:] for r in rows if r[0] not in rels]
    man = {'members': [{'path': r[0], 'mode': r[2]} for r in job if r[0] != 'job'],
           'png': {'files': [{'path': p[0], 'mode': p[1]} for p in png]} if png else None}
    if png_manifest_problem(man):
        raise Halt('STOP', 'PNG_MANIFEST_UNSAFE', 'the PNG set is not safe')
    members = [(r[0], r[1], r[2], None if r[1] == 'dir' else os.path.join(job_dir, r[0][4:])) for r in job]
    return members, job, png, sorted(rels), tree_sha(job + png)


def ai_members(output_dir, max_bytes):
    """§7.5 step 1: the role's output folder walked strictly as ai/ members; (members, files [[rel, bytes, sha]],
    tree sha256). AI_OUTPUT_TOO_LARGE over max_bytes. The helper hashes the files and never opens their content."""
    rows = walk_output(output_dir)
    if sum(r[3] or 0 for r in rows) > max_bytes:
        raise Halt('STOP', 'AI_OUTPUT_TOO_LARGE', 'the AI output folder is too large')
    mode = os.lstat(output_dir).st_mode & 0o777 if os.path.lexists(output_dir) else 0o755
    members = [('ai', 'dir', mode, None)] + [('ai/' + r[0], r[1], r[2], None if r[1] == 'dir'
                                              else os.path.join(output_dir, r[0])) for r in rows]
    return members, [[r[0], r[3], r[4]] for r in rows if r[1] == 'file'], tree_sha(rows)


# ---------------------------------------------------------------- placement (§8.5.1)
def _entry_reader(path):
    from .savepoint import read_entry
    return read_entry(path)


def place_ledger(lay, entry_path, want_sha256):
    """Step 1: BASE/ledger from the entry's ledger/LEDGER.jsonl member (sha checked), via a staging folder."""
    if os.path.lexists(lay.ledger_dir):
        stop('PLACE_TARGET_NOT_EMPTY', 'BASE/ledger exists')
    _entry_reader(entry_path)
    a = Archive(entry_path, ('MANIFEST.json', 'job', 'ledger', 'ai', 'transcript', 'attest', 'delivery', 'final'))
    try:
        raw = a.read('ledger/LEDGER.jsonl')
    finally:
        a.close()
    if sha_bytes(raw) != want_sha256:
        stop('PLACE_SHA_MISMATCH', 'the ledger bytes differ from the state')
    sd = lay.base / ('.cps_vm_stage_ledger_%d' % os.getpid())
    if os.path.lexists(sd):
        remove_tree(sd)
    os.mkdir(sd, 0o755)
    with open(sd / 'LEDGER.jsonl', 'xb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(sd / 'LEDGER.jsonl', 0o644)
    os.rename(sd, lay.ledger_dir)
    check_ledger_identity(type('C', (), {'lay': lay})())
    return sha_bytes(raw)


def place_job(lay, job_dir, snap_entry, png=None, png_part_paths=(), ai=()):
    """Steps 2-5: the job snapshot of `snap_entry` (a local tgz path), the PNG stream from its parts (concatenated in
    order; sha256 == png['whole_sha256']), and the ai/ members of AI entries [(entry path, output dir, replace)] into
    their output folders. The folder must be empty in the snapshot, except for a V revision >= 2 (replace): the
    REVIEW_INCOMPLETE snapshot holds revision 1 there, and the AI entry's tree is the whole folder after the
    continuation, so it takes the folder's place (§7.8, §8.5.1 step 4). A strict walk afterwards must equal snapshot +
    PNGs + AI outputs exactly. Returns the tree sha."""
    jd = Path(job_dir)
    if os.path.lexists(jd):
        stop('PLACE_TARGET_NOT_EMPTY', 'the job folder exists')
    man = _entry_reader(snap_entry)
    rows = [m for m in man['payload']['members'] if m[0] == 'job' or m[0].startswith('job/')]
    if not rows or rows[0][0] != 'job':
        stop('PLACE_SHA_MISMATCH', 'the entry holds no job snapshot')
    drop = tuple(os.path.relpath(x[1], jd).replace(os.sep, '/') + '/' for x in ai if x[2])
    rows = [r for r in rows if not r[0][4:].startswith(drop)] if drop else rows
    expect = {r[0][4:]: [r[1], r[2], r[3], r[4]] for r in rows[1:]}
    stg = Staging(jd).begin(rows[0][2])
    a = Archive(snap_entry, ('MANIFEST.json', 'job', 'ledger', 'ai', 'transcript', 'attest', 'delivery', 'final'))
    try:
        for r in rows[1:]:
            if r[1] == 'dir':
                stg.add_dir(r[0][4:], r[2])
            else:
                b = a.read(r[0])
                if len(b) != r[3] or sha_bytes(b) != r[4]:
                    stop('PLACE_SHA_MISMATCH', 'a snapshot member differs')
                stg.add_file(r[0][4:], b, r[2])
    finally:
        a.close()
    if png:
        stream = lay.inbox / 'journal' / ('.png_stream_%d' % os.getpid())
        stream.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        with open(stream, 'wb') as out:
            for p in png_part_paths:
                with open(p, 'rb') as f:
                    for c in iter(lambda: f.read(1 << 20), b''):
                        h.update(c)
                        out.write(c)
        try:
            if h.hexdigest() != png['whole_sha256']:
                stop('PLACE_SHA_MISMATCH', 'the PNG stream differs')
            pa = Archive(stream, ('MANIFEST.json', 'job'), gz=False)
            try:
                for f in png['files']:
                    b = pa.read(f[0])
                    if len(b) != f[2] or sha_bytes(b) != f[3]:
                        stop('PLACE_SHA_MISMATCH', 'a PNG differs')
                    _add_parents(stg, expect, f[0][4:])
                    stg.add_file(f[0][4:], b, f[1])
                    expect[f[0][4:]] = ['file', f[1], f[2], f[3]]
            finally:
                pa.close()
        finally:
            os.unlink(stream)
    for ent, out_dir, _ in ai:
        rel0 = os.path.relpath(out_dir, jd).replace(os.sep, '/')
        if any(k.startswith(rel0 + '/') for k in expect):
            stop('PLACE_TARGET_NOT_EMPTY', 'the output folder is not empty in the snapshot')
        am = _entry_reader(ent)
        aa = Archive(ent, ('MANIFEST.json', 'job', 'ledger', 'ai', 'transcript', 'attest', 'delivery', 'final'))
        try:
            for r in am['payload']['members']:
                if not r[0].startswith('ai/'):
                    continue
                rel = rel0 + '/' + r[0][3:]
                _add_parents(stg, expect, rel)
                if r[1] == 'dir':
                    stg.add_dir(rel, r[2])
                else:
                    stg.add_file(rel, aa.read(r[0]), r[2])
                expect[rel] = [r[1], r[2], r[3], r[4]]
        finally:
            aa.close()
    stg.finish()
    got = {r[0]: r[1:] for r in walk(jd)}
    if got != expect:
        stop('PLACE_SHA_MISMATCH', 'the placed folder differs from the entries')
    return tree_sha([[k] + v for k, v in sorted(got.items())])


def _add_parents(stg, expect, rel):
    parts = rel.split('/')[:-1]
    for i in range(1, len(parts) + 1):
        d = '/'.join(parts[:i])
        if d not in expect:
            stop('PLACE_SHA_MISMATCH', 'a placed file has no folder in the snapshot')


def place_member(entry_path, member, dest, mode=0o644):
    """A single member (a transcript, a delivery copy, FROZEN.json) written to dest (which must not exist)."""
    a = Archive(entry_path, ('MANIFEST.json', 'job', 'ledger', 'ai', 'transcript', 'attest', 'delivery', 'final'))
    try:
        b = a.read(member)
    finally:
        a.close()
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    with open(dest, 'xb') as f:
        f.write(b)
    os.chmod(dest, mode)
    return b


# ---------------------------------------------------------------- evict (§7.6) and placed FROZEN.json (§7.7)
def evict(lay, job_dir, entry_path, frozen_sha256, keep_name):
    """Post action EVICT: the strict walk must equal the FROZEN entry's job/ members plus its PNG files (EVICT_MISMATCH,
    nothing deleted); FROZEN.json is kept in outbox/frozen_json/ (its sha checked), then the folder is removed
    (EVICT_FAILED when that fails midway)."""
    man = _entry_reader(entry_path)
    want = {m[0][4:]: m[1:] for m in man['payload']['members'] if m[0].startswith('job/')}
    for f in (man['payload']['png'] or {}).get('files') or []:
        want[f[0][4:]] = ['file', f[1], f[2], f[3]]
    with JobLock(lay, job_dir):
        got = {r[0]: r[1:] for r in walk(job_dir)}
    if got != want:
        raise Halt('STOP', 'EVICT_MISMATCH', 'the job folder differs from its FROZEN entry',
                   detail={'extra': len(set(got) - set(want)), 'missing': len(set(want) - set(got)),
                           'changed': sum(1 for k in set(got) & set(want) if got[k] != want[k])})
    fz = Path(job_dir) / 'FROZEN.json'
    b = fz.read_bytes()
    if sha_bytes(b) != frozen_sha256:
        raise Halt('STOP', 'EVICT_MISMATCH', 'FROZEN.json is not the frozen one')
    from . import durable
    lay.frozen_json.mkdir(parents=True, exist_ok=True)
    durable.write(lay.frozen_json / keep_name, b, 0o444)
    try:
        remove_tree(job_dir)
        parent = Path(job_dir).parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        raise Halt('STOP', 'EVICT_FAILED', 'the job folder could not be removed')


def unplace_frozen(path, frozen_sha256):
    """Post action UNPLACE_FROZEN: a placed folder holding only that FROZEN.json is removed; anything else is
    PLACED_FROZEN_CHANGED."""
    jd = Path(path)
    if not os.path.lexists(jd):
        return
    names = sorted(os.listdir(jd))
    if names != ['FROZEN.json'] or sha_file(jd / 'FROZEN.json') != frozen_sha256:
        raise Halt('STOP', 'PLACED_FROZEN_CHANGED', 'a placed FROZEN.json folder holds something else')
    remove_tree(jd)

