"""commit(): the save-point mechanics (spec §5). The glue (cli.py, worker.py) gives a draft, the archive members, the
part sources and a `complete` function that folds the draft (core.fold, §5.1 step 2); this module writes the parts,
the entry and PENDING durably (steps 3-4), prints nothing itself, and runs the upload-FIND-attest loop (steps 5-7,
§5.2, §5.5) on PENDING. Every PENDING change is written durably before the caller prints the block it implies.

PENDING.tries[name] = {'uploads', 'finds_since_upload', 'need'} where need is upload | find | wait | verify | done.
The entry is confirmed first; parts only after (their number reveals the outcome). PENDING.absent lists names that must
be absent at the entry's FIND (a rebase RESTORE's missing parts, §5.1 step 5)."""
import os
import re

from . import durable
from .v1compat import Halt, stop
from .v1reuse import (Archive, PartWriter, md5_file, png_tar_members, require_space, sha_bytes, sha_file, sjson,
                      write_tar_stream, write_tgz)

PENDING_SCHEMA = 'cps.vm2-pending.v1'
STATE_SCHEMA = 'cps.vm2-cache.v1'
ROOTS = ('job', 'ledger', 'ai', 'transcript', 'attest', 'delivery', 'final')
PREFIXES = ('MANIFEST.json',) + ROOTS
MAX_MANIFEST = 32 * 1024 * 1024


def _manifest_order(m):
    return (ROOTS.index(m[0].split('/')[0]), m[0])


def payload_rows(members):
    """members: [(arcname, 'dir'|'file', mode, src bytes|path|None)] -> sorted payload rows [path, kind, mode, bytes,
    sha256] (§3.8)."""
    rows = []
    for name, kind, mode, src in members:
        if kind == 'dir':
            rows.append([name, 'dir', mode, None, None])
        elif isinstance(src, (bytes, bytearray)):
            rows.append([name, 'file', mode, len(src), sha_bytes(bytes(src))])
        else:
            rows.append([name, 'file', mode, os.lstat(src).st_size, sha_file(src)])
    return sorted(rows, key=lambda r: r[0])


def expected_of(rows):
    return {r[0]: ('dir', r[2]) if r[1] == 'dir' else ('file', r[2], r[3], r[4]) for r in rows}


def read_entry(path):
    """The MANIFEST.json (ENTRY document) of an entry tgz, after Archive + check against its own payload.members."""
    a = Archive(path, PREFIXES)
    try:
        man = a.manifest
        a.check(expected_of(man['payload']['members']))
        return man
    except (KeyError, TypeError):
        stop('ARCHIVE_MANIFEST_MISMATCH', 'the entry manifest has no payload')
    finally:
        a.close()


def member_bytes(path, name):
    a = Archive(path, PREFIXES)
    try:
        return a.read(name)
    finally:
        a.close()


def _png_parts(env, series, seq, src):
    """Write the PNG tar stream (MANIFEST.json + job/qa/... files) cut into parts at png_part_bytes (§3.7)."""
    jd, rels = src['job_dir'], src['rels']
    man = {'schema': 'cps.vm2-png.v1', 'run': src['run'], 'files': src['files']}
    pw = PartWriter(env.journal, env.cfg['png_part_bytes'], '.tmp_png_%d_' % os.getpid())
    try:
        write_tar_stream(pw, [('MANIFEST.json', 'file', 0o444, 0, durable.doc_bytes(man))] + png_tar_members(jd, rels))
        parts, whole = pw.finish()
    except BaseException:
        pw.discard()
        raise
    if len(parts) > 99:
        for p_, *_ in parts:
            os.unlink(p_)
        raise Halt('STOP', 'PART_TOO_LARGE', 'more than 99 PNG parts')
    out = []
    for k, (tmp, n, sh, m5) in enumerate(parts, 1):
        name = 'CPSJ_%s_%06d_PNG%02d.part' % (series, seq, k)
        os.replace(tmp, env.journal / name)
        out.append({'name': name, 'kind': 'PNG', 'k': k, 'folder': env.series_folder, 'sha256': sh, 'md5': m5,
                    'bytes': n})
    return out, whole


def write_commit(env, draft, members, part_sources, post, complete):
    """§5.1 steps 1-4. draft: the entry without confirms/prev_sha256/parts/payload/state (seq and name set by the
    caller). members: archive members after MANIFEST.json. part_sources: [{'kind': 'PNG', 'job_dir', 'rels', 'files',
    'run'} | {'kind': K, 'data': bytes, 'folder'}]. complete(entry) -> entry with state and state_sha256 (the fold; it
    raises for an illegal transition). Returns (PENDING doc, entry, png whole sha or None)."""
    if os.path.lexists(env.v2 / 'PENDING.json'):
        stop('INTERNAL_PENDING_EXISTS', 'a commit is pending')
    env.journal.mkdir(parents=True, exist_ok=True)
    est = sum(len(s) if isinstance(s, (bytes, bytearray)) else (os.lstat(s).st_size if s else 0)
              for _, k, _, s in members) + sum(len(p.get('data') or b'') for p in part_sources)
    for p in part_sources:
        if p['kind'] == 'PNG':
            est += sum(f[2] for f in p['files'])
    require_space(env.lay, int(est * 1.1) + 1, 'commit')
    seq, series = draft['seq'], draft['series']
    parts, whole, written = [], None, []
    try:
        for src in part_sources:
            if src['kind'] == 'PNG':
                ps, whole = _png_parts(env, series, seq, src)
            else:
                k = 1 + sum(1 for p in parts if p['kind'] == src['kind'])
                ext = {'DELIV': 'xlsx', 'DLOG': 'json', 'LEDGER': 'jsonl', 'ALLFZ': 'json'}[src['kind']]
                name = 'CPSJ_%s_%06d_%s%02d.%s' % (series, seq, src['kind'], k, ext)
                if len(src['data']) > env.cfg['png_part_bytes']:
                    raise Halt('STOP', 'PART_TOO_LARGE', 'a part over the part limit')
                durable.write(env.journal / name, src['data'])
                ps = [{'name': name, 'kind': src['kind'], 'k': k, 'folder': src['folder'], 'sha256': None,
                       'md5': None, 'bytes': None}]
            for p in ps:
                written.append(env.journal / p['name'])
                p['bytes'], p['sha256'], p['md5'] = durable.seal(env.journal / p['name'])
            parts += ps
        rows = payload_rows(members)
        entry = dict(draft, parts=parts, payload={'members': rows, 'png': draft.get('payload_png')})
        entry.pop('payload_png', None)
        entry = complete(entry)
        man = durable.doc_bytes(entry)
        if len(man) > MAX_MANIFEST:
            raise Halt('STOP', 'ENTRY_TOO_LARGE', 'the entry manifest is too large')
        path = env.journal / entry['name']
        if os.path.lexists(path):
            os.unlink(path)
        written.append(path)
        tm = [('MANIFEST.json', 'file', 0o444, 0, man)] + [
            (m[0], m[1], m[2], 0, m[3]) for m in sorted(members, key=_manifest_order)]
        try:
            write_tgz(path, tm)
        except OSError as e:
            raise durable.DurableError(e.errno)
        n, sh, m5 = durable.seal(path, lambda p_: read_entry(p_))
        if n > env.cfg['max_entry_bytes']:
            raise Halt('STOP', 'ENTRY_TOO_LARGE', 'the entry is over max_entry_bytes')
        return durable.write_doc(env.v2 / 'PENDING.json', _pending(env, draft, entry, path, parts, n, sh, m5,
                                                                   post)), entry, whole
    except BaseException:
        for p_ in written:
            try:
                os.unlink(p_)
            except OSError:
                pass
        raise


def _pending(env, draft, entry, path, parts, n, sh, m5, post):
    seq, series = draft['seq'], draft['series']
    names = [entry['name']] + [p['name'] for p in parts]
    return {'schema': PENDING_SCHEMA, 'series': series, 'seq': seq, 'phase': 'ENTRY',
            'entry': {'name': entry['name'], 'path': str(path), 'folder': env.series_folder, 'sha256': sh, 'md5': m5,
                      'bytes': n, 'copies': None},
            'parts': [{'name': p['name'], 'path': str(env.journal / p['name']), 'folder': p['folder'],
                       'sha256': p['sha256'], 'md5': p['md5'], 'bytes': p['bytes'], 'copies': None} for p in parts],
            'tries': {nm: {'uploads': 0, 'finds_since_upload': 0, 'need': 'upload'} for nm in names},
            'verify': [], 'absent': list(((draft.get('body') or {}).get('rebase') or {}).get('missing_parts') or [])
            if draft['kind'] == 'RESTORE' else [],
            'state_after_sha256': entry['state_sha256'], 'post': post, 'created_utc': env.now()}


def _files(pend):
    return [pend['entry']] + pend['parts']


def _group(pend):
    """The files of the current phase: the entry until it is confirmed, then the parts."""
    if pend['entry']['copies'] is None:
        return [pend['entry']]
    return [p for p in pend['parts'] if p['copies'] is None]


def block(env, pend):
    """§5.1 steps 5-7: the next SAVE block for PENDING, as (uploads, finds, downloads, do, expect_names), after
    updating PENDING's tries in place (the caller writes PENDING durably before printing). None when every file is
    confirmed (step 8)."""
    if pend['verify']:
        pend['phase'] = 'VERIFY'
        dl = tuple((v['folder'], v['id'], v['path']) for v in pend['verify'])
        return (), (), dl, ('RUN', {}), None
    grp = _group(pend)
    if not grp:
        return None
    pend['phase'] = 'ENTRY' if pend['entry']['copies'] is None else 'PARTS'
    tr = pend['tries']
    if any(tr[f['name']]['need'] == 'wait' for f in grp):
        for f in grp:
            if tr[f['name']]['need'] == 'wait':
                tr[f['name']]['need'] = 'find'
        return (), (), (), ('WAIT', {'seconds': max(30, 2 * (env.gates.get('p2_lag_seconds') or 0))}), None
    ups, finds, names = [], [], []
    for f in grp:
        t = tr[f['name']]
        if t['need'] == 'upload':
            ups.append((f['path'], f['folder'], f['name']))
            t['uploads'] += 1
            t['finds_since_upload'] = 0
            t['need'] = 'find'
        names.append(f['name'])
    absent = pend['absent'] if pend['phase'] == 'ENTRY' else []
    prefix = 'CPSJ_%s_%06d' % (pend['series'], pend['seq'])
    if env.gates.get('p2_prefix_search') == 'yes':
        if any(f['folder'] == env.series_folder for f in grp) or absent:
            finds.append((env.series_folder, 'PREFIX', prefix))
        finds += [(f['folder'], 'NAME', f['name']) for f in grp if f['folder'] != env.series_folder]
    else:
        finds += [(f['folder'], 'NAME', f['name']) for f in grp] + [(env.series_folder, 'NAME', n) for n in absent]
    return tuple(ups), tuple(finds), (), ('ATTEST_FOUND', {'names': names + list(absent),
                                                            'md5_hidden': env.gates.get('p2_md5_visible') == 'no'}), \
        names + list(absent)


def on_found(env, pend, got, check_id):
    """§5.1 step 6 for every name of the current block. got: {name: [copy strings] | None}. check_id(value) -> None or
    a REFUSED code for an ID value. Returns ('refused', code) with PENDING unchanged, ('stop', code), or ('ok', None)
    with PENDING updated in place."""
    from .drive import parse_copy
    hidden = env.gates.get('p2_md5_visible') == 'no'
    grp = {f['name']: f for f in _group(pend)}
    absent = set(pend['absent']) if pend['entry']['copies'] is None else set()
    parsed = {}
    for name, files in got.items():
        cps = []
        for s in files or []:
            c = parse_copy(s, hidden)
            if c is None:
                return 'refused', 'FOUND_SYNTAX'
            code = check_id(c[0])
            if code:
                return 'refused', code
            if not re.fullmatch(r'[1-9][0-9]{0,11}', c[-1]) or (
                    not hidden and not re.fullmatch(r'[0-9a-f]{32}', c[1])):
                return 'refused', 'VALUE_PATTERN'
            cps.append(c)
        parsed[name] = cps
    for name, cps in parsed.items():
        if name in absent and cps:
            return 'stop', 'REBASE_PART_APPEARED'
        if name not in grp and name not in absent and cps and env.gates.get('p2_prefix_search') == 'yes':
            return 'stop', 'FORK'
    for name, f in grp.items():
        cps = parsed.get(name) or []
        if any(int(c[-1]) != f['bytes'] or (not hidden and c[1] != f['md5']) for c in cps):
            return 'stop', 'FORK'
    vf = []
    for name, f in grp.items():
        cps, t = parsed.get(name) or [], pend['tries'][name]
        if cps and hidden:
            vf += [{'name': name, 'id': c[0], 'folder': f['folder'],
                    'path': str(env.lay.inbox / 'verify' / ('%s.%d' % (name, k)))} for k, c in enumerate(cps, 1)]
            t['need'] = 'verify'
        elif cps:
            f['copies'] = [[c[0], c[1], int(c[2])] for c in cps]
            t['need'] = 'done'
        elif t['finds_since_upload'] == 0:
            t['finds_since_upload'], t['need'] = 1, 'wait'
        elif t['uploads'] < 3:
            t['need'] = 'upload'
        else:
            return 'stop', 'UPLOAD_FAILED'
    pend['verify'] = vf
    pend['absent'] = [] if absent else pend['absent']
    return 'ok', None


def on_verify(env, pend):
    """§5.5: compare every downloaded copy with the local file. ('refused', DOWNLOAD_MISSING) | ('stop', FORK) |
    ('ok', None); downloads are deleted after the comparison."""
    by = {f['name']: f for f in _files(pend)}
    for v in pend['verify']:
        if not os.path.isfile(v['path']):
            return 'refused', 'DOWNLOAD_MISSING'
    fork = False
    for v in pend['verify']:
        f = by[v['name']]
        if os.lstat(v['path']).st_size != f['bytes'] or sha_file(v['path']) != f['sha256']:
            fork = True
    for v in pend['verify']:
        os.unlink(v['path'])
    if fork:
        return 'stop', 'FORK'
    for v in pend['verify']:
        f = by[v['name']]
        f['copies'] = (f['copies'] or []) + [[v['id'], f['md5'], f['bytes']]]
        pend['tries'][v['name']]['need'] = 'done'
    pend['verify'] = []
    return 'ok', None


def finish(env, cache, pend):
    """§5.1 step 8: the new STATE.json (head, state, confirms for the next entry, post; marks copied unchanged),
    written durably, then PENDING removed. Returns the STATE doc."""
    man = read_entry(pend['entry']['path'])
    if man['state_sha256'] != pend['state_after_sha256']:
        stop('INTERNAL_ILLEGAL_TRANSITION', 'the local entry is not the pending one')
    e = pend['entry']
    st = dict(cache or {}, schema=STATE_SCHEMA, series=pend['series'],
              head={'seq': pend['seq'], 'name': e['name'], 'id': e['copies'][0][0], 'md5': e['md5'],
                    'bytes': e['bytes'], 'sha256': e['sha256']},
              confirms=[{'name': f['name'], 'copies': [{'id': c[0], 'md5': c[1], 'size': c[2]} for c in f['copies']]}
                        for f in _files(pend)],
              state=man['state'], state_sha256=man['state_sha256'], kit_sha256=man['kit_sha256'],
              post=list(pend['post']) + [['DROP_LOCAL', [f['path'] for f in _files(pend)]]],
              marks=dict((cache or {}).get('marks') or {}), written_utc=env.now())
    st = durable.write_doc(env.v2 / 'STATE.json', st)
    durable.remove(env.v2 / 'PENDING.json')
    return st


# ---------------------------------------------------------------- setup files (§5: the same loop without a chain)
def setup_block(env, loop):
    """The upload-FIND-attest loop for setup files (PASS, SELFTEST, kit zip, reports). loop: {'files': [{'name', 'path',
    'folder', 'md5', 'bytes', 'sha256', 'copies'}], 'tries': {...}, 'verify': []} kept by the caller (RESTORE_WORK).
    Same return shape as block()."""
    pend = {'entry': {'copies': True}, 'parts': loop['files'], 'tries': loop['tries'], 'verify': loop['verify'],
            'absent': [], 'series': None, 'seq': 0}
    env2 = _Env1(env)
    return block(env2, pend)


class _Env1:
    def __init__(self, env):
        self.gates, self.lay, self.series_folder = dict(env.gates, p2_prefix_search='no'), env.lay, None


def setup_found(env, loop, got, check_id):
    pend = {'entry': {'copies': True}, 'parts': loop['files'], 'tries': loop['tries'], 'verify': loop['verify'],
            'absent': [], 'series': None, 'seq': 0}
    r = on_found(_Env1(env), pend, got, check_id)
    loop['verify'] = pend['verify']
    return r


def setup_verify(env, loop):
    pend = {'entry': {'copies': True}, 'parts': loop['files'], 'tries': loop['tries'], 'verify': loop['verify']}
    r = on_verify(env, pend)
    loop['verify'] = pend['verify']
    return r


def setup_loop(files):
    """A new setup-file loop for local files [(path, folder, name)]."""
    fs = [{'name': n, 'path': str(p), 'folder': f, 'md5': md5_file(p), 'bytes': os.lstat(p).st_size,
           'sha256': sha_file(p), 'copies': None} for p, f, n in files]
    return {'files': fs, 'tries': {f['name']: {'uploads': 0, 'finds_since_upload': 0, 'need': 'upload'} for f in fs},
            'verify': []}


def drop_local(paths):
    """Post action DROP_LOCAL: remove this commit's local entry and part files."""
    for p in paths:
        if os.path.lexists(p):
            os.unlink(p)


def read_pending(env):
    return durable.read_doc(env.v2 / 'PENDING.json', PENDING_SCHEMA, sjson)

