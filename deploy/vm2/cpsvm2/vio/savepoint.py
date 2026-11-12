"""commit(): the save-point mechanics (spec §5). The glue (cli.py, worker.py) gives a draft, the archive members, the
part sources and a `complete` function that folds the draft (core.fold, §5.1 step 2); this module writes the parts,
the entry and PENDING durably (steps 3-4), prints nothing itself, and runs the upload-FIND-attest loop (steps 5-7,
rule V by download-back, §X.5.6 refused uploads, the slip rule of delta v2.1 §2.2.1) on one loop dict: PENDING, or a
setup-file loop kept in RESTORE_WORK (no entry). Every loop change is written durably before the caller prints.

loop.tries[name] = {'uploads', 'finds_since_upload', 'refused', 'need'} where need is upload | find | wait | verify
| done. The entry is confirmed first; parts only after (their number reveals the outcome). loop.absent lists names that
must be absent at the entry's FIND (a rebase RESTORE's missing parts, §5.1 step 5)."""
import itertools
import os

from . import durable
from .v1compat import Halt, stop
from .v1reuse import (Archive, PartWriter, md5_file, png_tar_members, require_space, sha_bytes, sha_file,
                      write_tar_stream, write_tgz)

SLIP_ASKS = 3
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


def _png_parts(env, series, seq, src, want_whole):
    """Write the PNG tar stream (MANIFEST.json + job/qa/... files) cut into parts at png_part_bytes (§3.7). Each file's
    streamed bytes and the whole stream must be the ones the entry names (S-05), else HALT PNG_MANIFEST_UNSAFE."""
    jd, rels = src['job_dir'], src['rels']
    man = {'schema': 'cps.vm2-png.v1', 'run': src['run'], 'files': src['files']}
    want = {f[0]: f[3] for f in src['files']}

    def checked():
        for name, kind, mode, mt, path in png_tar_members(jd, rels):
            with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as f:
                b = f.read()
            if sha_bytes(b) != want.get(name):
                raise Halt('STOP', 'PNG_MANIFEST_UNSAFE', 'a PNG changed before its part was written')
            yield name, kind, mode, mt, b
    pw = PartWriter(env.journal, env.cfg['png_part_bytes'], '.tmp_png_%d_' % os.getpid())
    try:
        write_tar_stream(pw, itertools.chain([('MANIFEST.json', 'file', 0o444, 0, durable.doc_bytes(man))], checked()))
        parts, whole = pw.finish()
        if whole != want_whole:
            raise Halt('STOP', 'PNG_MANIFEST_UNSAFE', 'the PNG stream is not the one the entry names')
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
                ps, whole = _png_parts(env, series, seq, src, (draft.get('payload_png') or {}).get('whole_sha256'))
            else:
                k = 1 + sum(1 for p in parts if p['kind'] == src['kind'])
                ext = {'DELIV': 'xlsx', 'DLOG': 'json', 'LEDGER': 'jsonl', 'ALLFZ': 'json'}[src['kind']]
                name = 'CPSJ_%s_%06d_%s%02d.%s' % (series, seq, src['kind'], k, ext)
                if len(src['data']) > min(env.cfg['png_part_bytes'], env.cfg['max_upload_bytes']):
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
        if any(p['bytes'] > env.cfg['max_upload_bytes'] for p in parts):
            raise Halt('STOP', 'PART_TOO_LARGE', 'a part over max_upload_bytes')
        if n > min(env.cfg['max_entry_bytes'], env.cfg['max_upload_bytes']):
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
            'tries': _tries(names), 'verify': [], 'slips': 0,
            'absent': list(((draft.get('body') or {}).get('rebase') or {}).get('missing_parts') or [])
            if draft['kind'] == 'RESTORE' else [],
            'state_after_sha256': entry['state_sha256'], 'post': post, 'created_utc': env.now()}


def _tries(names):
    return {nm: {'uploads': 0, 'finds_since_upload': 0, 'refused': 0, 'need': 'upload'} for nm in names}


def _files(loop):
    return ([loop['entry']] if loop.get('entry') else []) + loop['parts']


def _group(loop):
    """The files of the current phase: the entry until it is confirmed, then the parts (a setup loop has no entry)."""
    if loop.get('entry') and loop['entry']['copies'] is None:
        return [loop['entry']]
    return [p for p in loop['parts'] if p['copies'] is None]


def block(loop, cap, lag, folder, reprint=False):
    """§5.1 steps 5-7 for one loop (PENDING, or a setup-file loop kept in RESTORE_WORK): the next block as (uploads,
    finds, downloads, do, expect names), after updating the loop's tries in place (the caller writes it durably before
    printing). None when every file is confirmed. cap: max_upload_bytes (a setup file over it is UPLOAD_TOO_LARGE, a
    journal file ENTRY_TOO_LARGE or PART_TOO_LARGE); lag: p2_lag_seconds; folder: the series folder of the absent names.
    A reprint (after a slip) has no UPLOAD lines (SD-60)."""
    if loop['verify']:
        return (), (), tuple((v['folder'], v['id'], v['path']) for v in loop['verify']), ('RUN', {}), None
    grp = _group(loop)
    if not grp:
        return None
    if loop.get('entry'):
        loop['phase'] = 'ENTRY' if loop['entry']['copies'] is None else 'PARTS'
    tr = loop['tries']
    if not reprint and any(tr[f['name']]['need'] == 'wait' for f in grp):
        for f in grp:
            if tr[f['name']]['need'] == 'wait':
                tr[f['name']]['need'] = 'find'
        return (), (), (), ('WAIT', {'seconds': max(30, 2 * (lag or 0))}), None
    ups, names = [], []
    for f in grp:
        t = tr[f['name']]
        if t['need'] == 'upload' and not reprint:
            if os.lstat(f['path']).st_size > cap:
                code = 'UPLOAD_TOO_LARGE' if not loop.get('entry') else (
                    'ENTRY_TOO_LARGE' if f['name'].endswith('.tgz') else 'PART_TOO_LARGE')
                raise Halt('STOP', code, 'a file over max_upload_bytes')
            ups.append((f['path'], f['folder'], f['name']))
            t['uploads'] += 1
            t['finds_since_upload'] = 0
            t['need'] = 'find'
        names.append(f['name'])
    absent = loop['absent'] if loop.get('entry') and loop['entry']['copies'] is None else []
    finds = [(f['folder'], 'NAME', f['name']) for f in grp] + [(folder, 'NAME', n) for n in absent]
    return tuple(ups), tuple(finds), (), ('ATTEST_FOUND', {'names': names + list(absent),
                                                           'uploaded': [u[2] for u in ups]}), names + list(absent)


def on_found(loop, got, refused, known, verify_dir):
    """§5.1 step 6 with rule V (delta v2.1 §2.1) for every name of the current block. got: {name: [[id, size]]};
    refused: the names attested --refused; known(name) -> the Drive ids already recorded for that name. A copy with an
    unknown id is downloaded back (verify), whatever size was attested. Returns ('stop', code), ('handback', the first
    refused name not found) or ('ok', None), with the loop updated in place."""
    grp = {f['name']: f for f in _group(loop)}
    absent = set(loop['absent']) if loop.get('entry') and loop['entry']['copies'] is None else set()
    if any(got.get(n) for n in absent):
        return 'stop', 'REBASE_PART_APPEARED'
    vf, handback = [], None
    for name, f in grp.items():
        cps, t = got.get(name) or [], loop['tries'][name]
        if name in refused:
            t['refused'] += 1
        ids = set(known(name))
        unknown = [c for c in cps if c[0] not in ids]
        if cps:
            vf += [{'name': name, 'id': c[0], 'size': c[1], 'folder': f['folder'],
                    'path': '%s/%s.%d' % (verify_dir, name, k)} for k, c in enumerate(cps, 1) if c[0] not in ids]
            f['copies'] = [[c[0], f['md5'], f['bytes']] for c in cps if c[0] in ids] or None
            t['need'] = 'verify' if unknown else 'done'
        elif name in refused:
            t['need'], t['finds_since_upload'] = 'find', 0
            handback = handback or name
        elif t['finds_since_upload'] == 0:
            t['finds_since_upload'], t['need'] = 1, 'wait'
        elif t['uploads'] < 3:
            t['need'] = 'upload'
        else:
            return 'stop', 'UPLOAD_FAILED'
    loop['verify'] = vf
    loop['absent'] = [] if absent else loop['absent']
    return ('handback', handback) if handback else ('ok', None)


def on_verify(loop):
    """At the `go` after a DOWNLOAD block: the slips first (a missing file, a size other than the attested one, the
    bytes of another file of the same loop), then FORK for a copy of the attested size with other bytes (its download
    is kept for stop_block), then each copy is confirmed and deleted. Returns ('ok', None) | ('slip', code, name) |
    ('stop', 'FORK', None)."""
    by = {f['name']: f for f in _files(loop)}
    shas = {}
    for v in loop['verify']:
        if not os.path.isfile(v['path']):
            return 'slip', 'DOWNLOAD_MISSING', v['name']
        if os.lstat(v['path']).st_size != v['size']:
            return 'slip', 'DOWNLOAD_INCOMPLETE', v['name']
        shas[v['path']] = sha_file(v['path'])
    ours = {f['sha256'] for f in by.values()}
    for v in loop['verify']:
        if shas[v['path']] != by[v['name']]['sha256'] and shas[v['path']] in ours:
            return 'slip', 'COPY_MISMATCH', v['name']
    if any(shas[v['path']] != by[v['name']]['sha256'] for v in loop['verify']):
        return 'stop', 'FORK', None
    for v in loop['verify']:
        os.unlink(v['path'])
        f = by[v['name']]
        f['copies'] = (f['copies'] or []) + [[v['id'], f['md5'], f['bytes']]]
        loop['tries'][v['name']]['need'] = 'done'
    loop['verify'] = []
    return 'ok', None


def slip(loop, name, code):
    """The slip rule (delta v2.1 §2.2.1) in one loop: every pending download is deleted and forgotten, its names are
    FOUND again, and the slip is counted. Returns None or 'SLIP_LIMIT' (the fourth slip of the loop)."""
    for v in loop['verify']:
        if os.path.lexists(v['path']):
            os.unlink(v['path'])
        f = [x for x in _files(loop) if x['name'] == v['name']][0]
        f['copies'], loop['tries'][v['name']]['need'] = None, 'find'
    loop['verify'] = []
    loop['slips'] = loop.get('slips', 0) + 1
    return 'SLIP_LIMIT' if loop['slips'] > SLIP_ASKS else None


def finish(env, cache, pend):
    """§5.1 step 8: the new STATE.json (head, state, confirms for the next entry, post; marks copied unchanged),
    written durably, then PENDING removed. The post actions still owed by the earlier STATE run first (S-04)."""
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
              post=list((cache or {}).get('post') or []) + list(pend['post']) + [
                  ['DROP_LOCAL', [f['path'] for f in _files(pend)]]],
              marks=dict((cache or {}).get('marks') or {}), written_utc=env.now())
    st = durable.write_doc(env.v2 / 'STATE.json', st)
    durable.remove(env.v2 / 'PENDING.json')
    return st


def setup_loop(files):
    """A new setup-file loop for local files [(path, folder, name)] (PASS, SELFTEST, reports, re-uploaded parts)."""
    fs = [{'name': n, 'path': str(p), 'folder': f, 'md5': md5_file(p), 'bytes': os.lstat(p).st_size,
           'sha256': sha_file(p), 'copies': None} for p, f, n in files]
    return {'entry': None, 'parts': fs, 'tries': _tries([f['name'] for f in fs]), 'verify': [], 'absent': [],
            'slips': 0}
