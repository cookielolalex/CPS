"""The 8 modified v1 functions (spec §1.6), each reviewed as a diff against its v1 segment (REUSE_MANIFEST.json
`modified` names the v1 lines and segment hash). The FOLDER_MANIFEST row helpers below them (MANIFEST_ROW, KIT_NAME,
KIT_SHA_LINE, kit_rows, kit_parts_plan) are copied unchanged from v1 (lines 2679, 2760-2795) because the modified
session_kit and rebuild_kit read them; they are not in §1.4's reuse list."""
import errno
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

from .v1compat import HELPER_REPO, Halt, need, stop, under
from .v1reuse import (HelperLock, current_boot_id, kit_members, parse_utc, now_dt, read_json_file, remove_tree,
                      sha_file, sjson, unsafe_name, worker_alive)


def tree_list(root):
    """Strict (SAFE-01): sorted [rel, 'dir'|'file', mode, bytes|None, sha256|None] of every entry below root. Any
    walk error, unreadable entry, link, device, socket, FIFO, setuid/setgid/sticky bit, unsafe or non-UTF-8 name
    raises Halt('STOP', 'WALK_UNSUPPORTED_ENTRY') naming the path class, never the path (no lenient mode)."""
    def bad(why):
        raise Halt('STOP', 'WALK_UNSUPPORTED_ENTRY', 'an entry the archive format does not keep', detail={'class': why})

    def raise_(e):
        bad('unreadable')
    root = str(root)
    try:
        st0 = os.lstat(root)
    except OSError:
        bad('unreadable')
    if not stat.S_ISDIR(st0.st_mode) or stat.S_IMODE(st0.st_mode) & 0o7000:
        bad('root')
    out = []
    for dp, dns, fns in os.walk(root, followlinks=False, onerror=raise_):
        dns.sort()
        for n in dns + fns:
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, root).replace(os.sep, '/')
            try:
                rel.encode('utf-8')
                if unsafe_name(rel):
                    bad('name')
            except UnicodeEncodeError:
                bad('name')
            try:
                st = os.lstat(p)
            except OSError:
                bad('unreadable')
            m = stat.S_IMODE(st.st_mode)
            if m & 0o7000:
                bad('mode')
            if stat.S_ISDIR(st.st_mode):
                if not os.access(p, os.R_OK | os.X_OK):
                    bad('unreadable')
                out.append([rel, 'dir', m, None, None])
            elif stat.S_ISREG(st.st_mode):
                try:
                    out.append([rel, 'file', m, st.st_size, sha_file(p)])
                except OSError:
                    bad('unreadable')
            else:
                bad('symlink' if stat.S_ISLNK(st.st_mode) else 'special')
    return sorted(out, key=lambda e: e[0])


def check_layout_release(lay, rel, helper_tree_sha256, commit):
    """2.2 (v2): the release names exactly this layout's paths, pins the helper tree (deploy/vm2/**, by the §3.4 tree
    sha in RELEASE.json vm_helper.tree_sha256) and the runner; repository.commit is the checked-out commit."""
    mode = {'RELEASED_FOR_QUALIFICATION': 'qualification', 'RELEASED_FOR_USE': 'everyday'}.get(
        (rel or {}).get('status'), 'setup')
    bad = []
    repo = rel.get('repository') or {}
    root = repo.get('root')
    if not isinstance(root, str) or os.path.realpath(root) != os.path.realpath(lay.repo):
        bad.append('repository.root')
    if repo.get('commit') != commit:
        bad.append('repository.commit')
    qd = rel.get('qualification') if isinstance(rel.get('qualification'), dict) else {}
    if mode == 'qualification':
        if qd.get('ledger') != str(lay.ledger):
            bad.append('qualification.ledger')
        if not isinstance(qd.get('jobs_file'), str) or not under(qd['jobs_file'], lay.runtime):
            bad.append('qualification.jobs_file')
        for a in qd.get('admissions') or []:
            if not isinstance(a, dict) or not isinstance(a.get('path'), str) or not under(a['path'], lay.runtime):
                bad.append('qualification.admissions')
    for k, t in (rel.get('tables') or {}).items():
        if isinstance(t, dict) and isinstance(t.get('path'), str) and not under(t['path'], lay.runtime):
            bad.append('tables.' + k)
    sp = rel.get('source_prep') or {}
    if sp.get('deps_bundle') != str(lay.tools / 'builder-deps'):
        bad.append('source_prep.deps_bundle')
    if sp.get('node_path') is not None and sp.get('node_path') != str(lay.tools / 'playwright' / 'node_modules'):
        bad.append('source_prep.node_path')
    cn = rel.get('checker_node') or {}
    if cn.get('path') is not None and not under(cn['path'], lay.tools):
        bad.append('checker_node.path')
    if bad:
        stop('LAYOUT_RELEASE_MISMATCH', 'the release does not name this layout', detail={'fields': sorted(set(bad))})
    if (rel.get('vm_helper') or {}).get('tree_sha256') != helper_tree_sha256:
        stop('LAYOUT_HELPER_NOT_PINNED', 'the release must pin deploy/vm2/** by its tree sha256')
    pins = rel.get('pinned_files_sha256') or {}
    rp = HELPER_REPO / 'deploy/run/cps_job.py'
    if not rp.is_file() or pins.get('deploy/run/cps_job.py') != sha_file(rp):
        stop('LAYOUT_RUNNER_NOT_PINNED', 'the release must pin deploy/run/cps_job.py')
    return mode


def cleanup_leftovers(lay):
    """T-23 (v2): leftovers of a killed earlier helper, removed under the helper lock and only when no detached worker
    of this boot is alive: staging folders, temporary files of durable writes, and inbox downloads of an earlier boot.
    Never a job folder."""
    dp = lay.outbox / 'DETACHED.json'
    d = read_json_file(dp) if dp.is_file() else None
    if isinstance(d, dict) and worker_alive(d):
        return
    if isinstance(d, dict) and d.get('boot_id') != current_boot_id():
        dp.unlink()
    globs = [lay.base.glob('.cps_vm_stage_*'), lay.outbox.glob('.tmp_*'), (lay.outbox / 'journal').glob('.tmp_*'),
             (lay.outbox / 'v2').glob('.tmp_*')]
    for root in (lay.qual, lay.jobs):
        if root.is_dir():
            globs.append(root.glob('*/.cps_vm_stage_*'))
            globs.append(root.glob('*/.cps_vm_evict_*'))
    for g in globs:
        for p in list(g):
            try:
                remove_tree(p)
            except OSError:
                pass
    mark, boot = lay.inbox / '.boot', current_boot_id()
    try:
        old = mark.read_text().strip() if mark.is_file() else None
    except OSError:
        old = None
    if old != boot and lay.inbox.is_dir():
        for p in list(lay.inbox.iterdir()):
            try:
                remove_tree(p)
            except OSError:
                pass
    if old != boot:
        lay.inbox.mkdir(parents=True, exist_ok=True)
        mark.write_text(boot + '\n')


def place_frozen(lay, job_dir, frozen_bytes, frozen_sha256):
    """§7.7 (v2): put an earlier run's FROZEN.json back at its job folder for a reader-B or restart prepare. The bytes
    come from outbox/frozen_json/ or the run's FROZEN entry (the caller reads them); sha(bytes) must be the state's
    frozen_sha256 and the ledger's last freeze entry of that folder. Returns the placed folder."""
    from .v1reuse import sha_bytes, write_new
    jd = Path(job_dir)
    if os.path.lexists(jd):
        stop('PLACE_TARGET_NOT_EMPTY', 'the earlier job folder exists')
    if sha_bytes(frozen_bytes) != frozen_sha256:
        stop('PLACE_SHA_MISMATCH', 'the kept FROZEN.json is not the frozen one')
    led = []
    raw = lay.ledger.read_bytes() if lay.ledger.is_file() else b''
    for ln in raw.splitlines():
        try:
            e = sjson(ln) if ln.strip() else None
        except (ValueError, UnicodeDecodeError):
            e = None
        if isinstance(e, dict) and e.get('type') == 'freeze' and e.get('job_dir') == str(jd):
            led.append(e)
    if not led or led[-1].get('frozen_sha256') != frozen_sha256:
        stop('PLACE_SHA_MISMATCH', 'the ledger does not record this FROZEN.json for that folder')
    jd.mkdir(parents=True, mode=0o755)
    os.chmod(jd, 0o755)
    write_new(jd / 'FROZEN.json', frozen_bytes, 0o444)
    return str(jd)


def wait_block(ctx, seconds):
    """§7.2 (v2): ('done', result dict), ('running', None) or ('died', None). No plan call, no printing; the caller
    absorbs the result under the helper lock."""
    p = ctx.lay.outbox / 'DETACHED.json'
    deadline = time.time() + seconds
    while True:
        d = read_json_file(p) if p.is_file() else None
        if not isinstance(d, dict):
            return 'died', None
        out = Path(d['out'])
        if out.is_file() and d.get('exit') is not None:
            res = read_json_file(out)
            return ('done', res) if isinstance(res, dict) else ('died', None)
        young = d.get('pid') is None and time.time() - (parse_utc(d['started_utc']) or now_dt()).timestamp() < 30
        if not worker_alive(d) and not young:
            time.sleep(0.5)
            d2 = read_json_file(p) or {}
            if Path(d['out']).is_file() and d2.get('exit') is not None:
                continue
            return 'died', None
        if time.time() >= deadline:
            return 'running', None
        time.sleep(0.5)


def cmd_worker(wid, lock_fd, dispatch, write_doc):
    """§7.2 (v2): the detached worker's entry. dispatch(kind, info, lay) -> result dict ({'status': 'pending' |
    'halt' | 'done', 'code', 'detail'}); the result is written durably (write_doc) to spawn's `out` path, then
    DETACHED.json gets `exit`. Never prints."""
    from .v1reuse import Layout
    lay = Layout()
    p = lay.outbox / 'DETACHED.json'
    d = None
    for _ in range(100):
        d = read_json_file(p)
        if isinstance(d, dict) and d.get('id') == wid:
            break
        time.sleep(0.1)
    if not isinstance(d, dict) or d.get('id') != wid or d.get('kind') not in ('chain', 'selftest', 'place'):
        return 2
    lock = HelperLock.adopt(lay, lock_fd) if lock_fd is not None else None
    try:
        if lock is None:
            lock = HelperLock(lay, wait=10)
            lock.__enter__()
    except Halt as h:
        _finish(p, d, {'status': 'halt', 'code': h.code, 'detail': {}}, 4, write_doc)
        return 0
    try:
        try:
            res = dispatch(d['kind'], d['info'], lay)
        except Halt as h:
            res = {'status': 'halt', 'code': h.code, 'detail': _small(h.detail)}
        except OSError as e:
            res = {'status': 'halt', 'code': 'DISK_FULL' if e.errno in (errno.ENOSPC, errno.EDQUOT) else 'WRITE_FAILED',
                   'detail': {'errno': e.errno}}
        _finish(p, d, res, 0, write_doc)
    finally:
        lock.release()
    return 0


def _small(x):
    """A bounded detail: codes and counts only (ints, bools, short ASCII strings)."""
    if not isinstance(x, dict):
        return {}
    return {str(k)[:40]: v if isinstance(v, (int, bool)) or v is None else str(v)[:80]
            for k, v in list(x.items())[:10] if isinstance(v, (int, bool, str)) or v is None}


def _finish(p, d, res, code, write_doc):
    write_doc(Path(d['out']), res)
    cur = read_json_file(p) or d
    cur['exit'] = code
    write_doc(p, cur)


# ---------------------------------------------------------------- kit intake (§8.2): FOLDER_MANIFEST route
MANIFEST_ROW = re.compile(r'^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*`([0-9a-f]{64})`\s*\|', re.M)
KIT_NAME = r'SESSION_KIT_[A-Za-z0-9._-]+\.zip'
KIT_SHA_LINE = re.compile(r'^kit-sha256:[ \t]+(' + KIT_NAME + r')[ \t]+(\d+)[ \t]+([0-9a-f]{64})[ \t]*$', re.M)


def kit_rows(text):
    """(zip rows, kit-sha256 lines, all table rows) of FOLDER_MANIFEST.md."""
    rows = [(p, int(n), h) for p, n, h in MANIFEST_ROW.findall(text)]
    zips = [r for r in rows if re.fullmatch('cps_runtime/' + KIT_NAME, r[0])]
    lines = [(m.group(1), int(m.group(2)), m.group(3)) for m in KIT_SHA_LINE.finditer(text)]
    return zips, lines, rows


def kit_parts_plan(rows, kname):
    """r4 F1: the manifest rows of the parts route for kit kname: (parts [(path, i, n, copy)], binaries [path], bin dir)."""
    stem = kname[:-4]
    pre = f'cps_runtime/kit/{stem}/'
    prx = re.compile(re.escape(pre + stem) + r'_part(\d+)of(\d+)_([AB])\.txt')
    parts, bins = [], []
    for path, _, _ in rows:
        m = prx.fullmatch(path)
        if m:
            parts.append((path, int(m.group(1)), int(m.group(2)), m.group(3)))
        elif re.fullmatch(re.escape(pre) + r'bin/[A-Za-z0-9._-]+', path):
            bins.append(path)
    ns = {n for _, _, n, _ in parts}
    if len(ns) != 1 or {(i, c) for _, i, _, c in parts} != {(i, c) for i in range(1, next(iter(ns)) + 1) for c in 'AB'}:
        stop('KIT_PARTS_NOT_IN_MANIFEST', 'FOLDER_MANIFEST.md must list both copies (A and B) of every bundle part of the kit '
             'under cps_runtime/kit/<stem>/: tell the maintainer', detail={'kit': kname, 'parts_listed': len(parts)})
    return sorted(parts, key=lambda x: (x[1], x[3])), sorted(bins), pre + 'bin'


def rebuild_kit(lay, inbox, block, kname, size, sha, rows):
    """§8.2 (v2): the parts route. A missing part copy or binary is asked for by exact name (block.download(None,
    'CPS/<folder>/<name>', path): the glue prints FIND then DOWNLOAD by id); make_kit.py assemble rebuilds the zip, and
    the rebuilt zip is re-hashed before it is returned (KIT-2)."""
    parts, bins, bdir = kit_parts_plan(rows, kname)
    out = inbox / 'cps' / 'rebuilt' / kname
    if not (out.is_file() and os.lstat(out).st_size == size and sha_file(out) == sha):
        missing = [p for p in [x[0] for x in parts] + bins if not (inbox / 'cps' / p).is_file()]
        for p in missing:
            block.download(None, 'CPS/' + p, inbox / 'cps' / p)
        if missing:
            need(block, 'NEED_KIT_PARTS')
        (inbox / 'cps' / bdir).mkdir(parents=True, exist_ok=True)
        if os.path.lexists(out):
            os.unlink(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        mk = HELPER_REPO / 'deploy' / 'make_kit.py'
        p = subprocess.run([sys.executable, '-I', '-B', str(mk), 'assemble', str(out), '--binaries',
                            str(inbox / 'cps' / bdir), '--expect', sha, *[str(inbox / 'cps' / x[0]) for x in parts]],
                           capture_output=True, text=True, timeout=3600)
        if p.returncode != 0 and os.path.lexists(out):
            os.unlink(out)
    if not out.is_file() or os.lstat(out).st_size != size or sha_file(out) != sha:
        stop('KIT_NOT_REBUILT', 'make_kit.py assemble could not rebuild the kit from the parts: tell the maintainer',
             detail={'kit': kname})
    return out


def session_kit(lay, inbox, block):
    """§8.2 (v2), the FOLDER_MANIFEST route (KIT-2). Zip route: the cps_runtime/SESSION_KIT_<v>.zip row, downloaded by
    exact name and checked with verify_drive_files.py; parts route: rebuild_kit. Either way the zip used is re-hashed
    (sha256 and size equal to the manifest's) and read with kit_members before it is returned. Returns
    ({'name', 'sha256', 'route', 'path'}, members); installing it is the caller's (unpack_kit after acceptance)."""
    man = inbox / 'cps' / 'FOLDER_MANIFEST.md'
    if not man.is_file():
        block.download(None, 'CPS/FOLDER_MANIFEST.md', man)
        need(block, 'NEED_FOLDER_MANIFEST')
    zips, lines, rows = kit_rows(man.read_text(encoding='utf-8', errors='replace'))
    if len(zips) > 1 or len(lines) > 1 or (not zips and not lines):
        stop('KIT_NOT_IN_MANIFEST', 'FOLDER_MANIFEST.md must list exactly one kit: tell the maintainer')
    if zips and lines and (zips[0][0].split('/')[-1], zips[0][1], zips[0][2]) != lines[0]:
        stop('KIT_NOT_IN_MANIFEST', 'the kit row and the kit-sha256 line of FOLDER_MANIFEST.md disagree')
    if zips:
        path, size, sha = zips[0]
        kname = path.split('/')[-1]
        zp = inbox / 'cps' / path
        if not zp.is_file():
            block.download(None, 'CPS/' + path, zp)
            need(block, 'NEED_KIT')
        vd = HELPER_REPO / 'deploy' / 'verify_drive_files.py'
        rep = inbox / 'repaired'
        p = subprocess.run([sys.executable, '-I', '-B', str(vd), str(man), str(inbox / 'cps'), '--repair-to', str(rep),
                            path], capture_output=True, text=True, timeout=3600)
        status = None
        for ln in p.stdout.splitlines():
            m = re.match(r'^(ok|MISSING|MISMATCH|REPAIRED|NOT REPAIRED)\s+(\S+)$', ln.strip())
            if m and m.group(2) == path:
                status = m.group(1)
        use = zp if status == 'ok' else rep / path if status == 'REPAIRED' and (rep / path).is_file() else None
        route = 'zip'
    else:
        kname, size, sha = lines[0]
        use, route = rebuild_kit(lay, inbox, block, kname, size, sha, rows), 'parts'
    if use is None or not use.is_file() or os.lstat(use).st_size != size or sha_file(use) != sha:
        stop('KIT_NOT_VERIFIED', 'the kit does not match FOLDER_MANIFEST.md: tell the maintainer')
    members = kit_members(use)
    return {'name': kname, 'sha256': sha, 'route': route, 'path': str(use)}, members
