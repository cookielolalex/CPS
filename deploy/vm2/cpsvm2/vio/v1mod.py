"""The 6 modified v1 functions (spec §1.6, REUSE_MANIFEST `modified`), and the FOLDER_MANIFEST row helpers
copied unchanged from v1 (lines 2679, 2760-2795) that session_kit and rebuild_kit read."""
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

from .v1compat import HELPER_REPO, Halt, need, stop, under
from .v1reuse import current_boot_id, kit_members, remove_tree, sha_file, sjson, unsafe_name


def tree_list(root):
    """Strict (SAFE-01): sorted [rel, kind, mode, bytes, sha256] below root; anything else is WALK_UNSUPPORTED_ENTRY."""
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
    """2.2 (v2): the release names this layout's paths, pins the helper tree and runner, and the commit."""
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
    """T-23 (v2, §X.1): a killed helper's staging folders, temp files and older inbox downloads; never a job."""
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
    """§7.7 (v2.1): an earlier run's FROZEN.json back at its job folder (sha and ledger checked), settled."""
    from .place import settle
    from .v1reuse import sha_bytes, write_new
    jd = Path(job_dir)
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
    sd = jd.parent / ('.cps_vm_stage_%s_%d' % (jd.name, os.getpid()))
    if os.path.lexists(sd):
        remove_tree(sd)
    sd.mkdir(parents=True, mode=0o755)
    os.chmod(sd, 0o755)
    write_new(sd / 'FROZEN.json', frozen_bytes, 0o444)
    settle(lay, jd, {'FROZEN.json': ['file', 0o444, len(frozen_bytes), frozen_sha256]}, 0o755, sd,
           lambda: os.rename(sd, jd))
    return str(jd)


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
    """§8.2 (v2): the parts route; missing files asked by exact name, the rebuilt zip re-hashed (KIT-2)."""
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
    """§8.2 (v2), FOLDER_MANIFEST route (KIT-2): ({'name', 'sha256', 'route', 'path'}, members), re-hashed."""
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
