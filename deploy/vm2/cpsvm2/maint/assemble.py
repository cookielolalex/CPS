"""vm2.py assemble (spec §10.2): rebuild every frozen run folder of a FINAL series, and the ledger, at their original
absolute paths under --root, from the downloaded journal; optionally run the runner's verify-frozen on each.

    assemble --series Q1 --dir DOWNLOADS --out ASSEMBLE.json [--root /] [--verify-frozen]

DOWNLOADS has the layout of audit.py (<dir>/<id>/<name>); copies of one name must be byte-identical (else FORK). The
run list is the FINAL entry's ALL_FROZEN (the audit, the scoring pre-gate, re-derives it from its own fold). Each run:
the FROZEN entry's job/ members plus the PNG stream of its parts, through the reused Staging into an empty target
(§8.5.1 steps 2-5), then a strict walk must equal exactly what was placed. Writes ASSEMBLE.json
(cps.vm2-assemble.v1); exit 0 iff every run was placed (and, with --verify-frozen, gave NEXT: DONE), 1 otherwise."""
import argparse
import hashlib
import os
import re
import stat
import subprocess
import sys

from ..core.names import ENTRY, cjson, entry_name, fm, sha
from ..vio.v1compat import Halt
from ..vio.v1reuse import Archive, Staging, remove_tree, sjson
from .audit import RUNNER, RUNNER_SHA256, doc_bytes, open_entry, read_bytes

SCHEMA = 'cps.vm2-assemble.v1'
CARRIER = 'carrier/convert/carrier.json'


class Bad(Exception):
    def __init__(self, code, name):
        super().__init__(code)
        self.code, self.name = code, name


def file_sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def walk(top):
    """{rel: ('dir', mode) | ('file', mode, bytes, sha256)} of everything under top, never following a link."""
    out = {}
    for dp, dns, fns in os.walk(top):
        for n in dns + fns:
            p = os.path.join(dp, n)
            st = os.lstat(p)
            rel = os.path.relpath(p, top)
            if stat.S_ISDIR(st.st_mode):
                out[rel] = ('dir', stat.S_IMODE(st.st_mode))
            elif stat.S_ISREG(st.st_mode):
                out[rel] = ('file', stat.S_IMODE(st.st_mode), st.st_size, file_sha(p))
            else:
                out[rel] = ('other',)
    return out


class Assembler:
    def __init__(self, series, ddir, root):
        self.series, self.root, self.idx = series, root, {}
        for i in sorted(os.listdir(ddir)):
            d = os.path.join(ddir, i)
            for n in sorted(os.listdir(d)) if os.path.isdir(d) and not os.path.islink(d) else []:
                self.idx.setdefault(n, []).append(os.path.join(d, n))

    def path(self, name):
        ps = self.idx.get(name)
        if not ps:
            raise Bad('DOWNLOAD_MISSING', name)
        if len({file_sha(p) for p in ps}) != 1:
            raise Bad('FORK', name)
        return ps[0]

    def entry(self, name):
        try:
            return open_entry(self.path(name))
        except Halt as h:
            raise Bad(h.code, name)

    def target(self, abs_path):
        if not (isinstance(abs_path, str) and abs_path.startswith('/') and os.path.normpath(abs_path) == abs_path
                and fm(r'[A-Za-z0-9_./-]+', abs_path)):
            raise Bad('LAYOUT_PATH', abs_path)
        t = os.path.join(self.root, abs_path.lstrip('/'))
        if os.path.lexists(t):
            raise Bad('PLACE_TARGET_NOT_EMPTY', abs_path)
        return t

    def png(self, doc, r, tmp):
        """[(rel, mode, bytes)] of the run's PNGs: the parts of png.parts_seq joined, sha-checked, read as a tar."""
        png = doc['payload']['png']
        pdoc = doc if png['parts_seq'] == doc['seq'] else self.entry(entry_name(self.series, png['parts_seq']))[0]
        parts = [p for p in pdoc['parts'] if p['kind'] == 'PNG']
        if [p['name'] for p in parts] != r['png_parts']:
            raise Bad('PLACE_SHA_MISMATCH', doc['name'])
        whole = hashlib.sha256()
        with open(tmp, 'xb') as out:
            for p in parts:
                b = read_bytes(self.path(p['name']))
                if sha(b) != p['sha256']:
                    raise Bad('PLACE_SHA_MISMATCH', p['name'])
                whole.update(b)
                out.write(b)
        if whole.hexdigest() != png['whole_sha256']:
            raise Bad('PLACE_SHA_MISMATCH', doc['name'])
        sent = pdoc['payload']['png']['files']          # the stream holds the files as that entry recorded them
        try:
            a = Archive(tmp, ('MANIFEST.json', 'job'), gz=False)
            if a.manifest != {'schema': 'cps.vm2-png.v1', 'run': r['run'], 'files': sent}:
                raise Bad('ARCHIVE_MANIFEST_MISMATCH', doc['name'])
            a.check({f[0]: ('file', f[1], f[2], f[3]) for f in sent})
            have = {f[0]: f[3] for f in sent}
            if any(have.get(f[0]) != f[3] for f in png['files']):
                raise Bad('PLACE_SHA_MISMATCH', doc['name'])
            out = [(f[0][4:], f[1], a.read(f[0])) for f in png['files']]       # placed with this snapshot's modes
            a.close()
            return out
        except Halt as h:
            raise Bad(h.code, doc['name'])

    def place(self, r):
        doc, a = self.entry(r['frozen_entry'])
        b = doc['body']
        if doc['kind'] != 'FROZEN' or doc['series'] != self.series or b['run'] != r['run'] \
                or b['frozen_sha256'] != r['frozen_sha256'] or doc['seq'] != r['frozen_seq']:
            raise Bad('PLACE_SHA_MISMATCH', r['frozen_entry'])
        target = self.target(r['job_dir'])
        mem = [m for m in doc['payload']['members'] if m[0] == 'job' or m[0].startswith('job/')]
        if not mem or mem[0][:2] != ['job', 'dir']:
            raise Bad('ARCHIVE_MANIFEST_MISMATCH', r['frozen_entry'])
        want = {}
        st = Staging(target).begin(mem[0][2])
        try:
            for m in mem[1:]:
                rel = m[0][4:]
                if m[1] == 'dir':
                    st.add_dir(rel, m[2])
                    want[rel] = ('dir', m[2])
                else:
                    st.add_file(rel, a.read(m[0]), m[2])
                    want[rel] = ('file', m[2], m[3], m[4])
            if doc['payload']['png']:
                tmp = os.path.join(os.path.dirname(target), '.cps_vm2_png_%d' % os.getpid())
                try:
                    for rel, mode, data in self.png(doc, r, tmp):
                        st.add_file(rel, data, mode)
                        want[rel] = ('file', mode, len(data), sha(data))
                finally:
                    if os.path.lexists(tmp):
                        os.unlink(tmp)
            st.finish()
        except Halt as h:
            remove_tree(st.stage)
            raise Bad(h.code, r['frozen_entry'])
        except BaseException:
            remove_tree(st.stage)
            raise
        finally:
            a.close()
        if walk(target) != want or stat.S_IMODE(os.lstat(target).st_mode) != mem[0][2]:
            raise Bad('PLACE_SHA_MISMATCH', r['job_dir'])
        fz = os.path.join(target, 'FROZEN.json')
        if not os.path.isfile(fz) or file_sha(fz) != r['frozen_sha256']:
            raise Bad('PLACE_SHA_MISMATCH', r['job_dir'])
        listed = {f.get('path'): f.get('sha256') for f in sjson(read_bytes(fz)).get('files') or []}
        car = os.path.join(target, CARRIER)
        return {'run': r['run'], 'job_dir': r['job_dir'], 'path': target, 'frozen_sha256': r['frozen_sha256'],
                'files': sum(1 for v in want.values() if v[0] == 'file'),
                'dirs': sum(1 for v in want.values() if v[0] == 'dir'),
                'png_files': len((doc['payload']['png'] or {}).get('files') or []),
                'carrier_sha256': file_sha(car) if os.path.isfile(car) else None,
                'carrier_listed_sha256': listed.get(CARRIER), 'verify': None}

    def run(self, verify):
        seqs = sorted(int(m.group(2)) for n in self.idx for m in [re.fullmatch(ENTRY, n, re.ASCII)]
                      if m and m.group(1) == self.series)
        if not seqs:
            raise Bad('CHAIN_INVALID', self.series)
        fdoc, fa = self.entry(entry_name(self.series, seqs[-1]))
        try:
            if fdoc['kind'] != 'FINAL':
                raise Bad('CHAIN_INVALID', fdoc['name'])
            af_raw, lf = fa.read('final/ALL_FROZEN.json'), fa.read('final/LEDGER_FINAL.jsonl')
        finally:
            fa.close()
        af = sjson(af_raw)
        if sha(af_raw) != fdoc['body']['all_frozen_sha256'] or sha(lf) != fdoc['body']['ledger_final_sha256'] \
                or af['ledger_final'] != {'sha256': sha(lf), 'bytes': len(lf)}:
            raise Bad('PLACE_SHA_MISMATCH', fdoc['name'])
        led = self.target(af['genesis']['base'].rstrip('/') + '/ledger')
        for r in af['runs']:
            self.target(r['job_dir'])
        runs = [self.place(r) for r in af['runs']]
        os.makedirs(os.path.dirname(led), exist_ok=True)
        os.mkdir(led, 0o755)
        with open(os.path.join(led, 'LEDGER.jsonl'), 'xb') as f:
            f.write(lf)
        os.chmod(os.path.join(led, 'LEDGER.jsonl'), 0o644)
        os.chmod(led, 0o755)
        if verify:
            if file_sha(RUNNER) != RUNNER_SHA256:
                raise Bad('LAYOUT_RUNNER_NOT_PINNED', 'cps_job.py')
            for x in runs:
                p = subprocess.run([sys.executable, '-I', '-B', os.path.abspath(RUNNER), 'verify-frozen', '--job-dir',
                                    x['path']], stdin=subprocess.DEVNULL, capture_output=True, timeout=600)
                last = ([ln for ln in p.stdout.decode('utf-8', 'replace').splitlines() if ln.strip()] or [''])[-1]
                x['verify'] = last[6:] if last.startswith('NEXT: ') else 'EXIT_%d' % p.returncode
        return {'schema': SCHEMA, 'series': self.series, 'root': self.root, 'final_seq': fdoc['seq'],
                'all_frozen_sha256': sha(af_raw), 'outcomes_sha256': af['outcomes_sha256'],
                'outcomes_check_sha256': sha(cjson(af['outcomes'])),
                'ledger': {'path': os.path.join(led, 'LEDGER.jsonl'), 'sha256': sha(lf)}, 'runs': runs}


def main(argv):
    ap = argparse.ArgumentParser(prog='vm2.py assemble')
    for k in ('series', 'dir', 'out'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--root', default='/')
    ap.add_argument('--verify-frozen', action='store_true')
    a = ap.parse_args(argv)
    if not fm(r'Q[1-9]|D[1-9][0-9]?', a.series) or not os.path.isabs(a.root):
        print('REFUSED VALUE_PATTERN series/root')
        return 2
    try:
        rep = dict(Assembler(a.series, a.dir, a.root).run(a.verify_frozen), problems=[])
    except Bad as b:
        rep = {'schema': SCHEMA, 'series': a.series, 'root': a.root, 'runs': [],
               'problems': [{'code': b.code, 'name': b.name}]}
    except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError) as x:
        rep = {'schema': SCHEMA, 'series': a.series, 'root': a.root, 'runs': [],
               'problems': [{'code': 'ARCHIVE_UNREADABLE', 'name': type(x).__name__}]}
    rep['clean'] = not rep['problems'] and all(x['verify'] in (None, 'DONE') for x in rep['runs']) \
        and (not a.verify_frozen or all(x['verify'] == 'DONE' for x in rep['runs']))
    with open(a.out, 'xb') as f:
        f.write(doc_bytes(rep))
    print('ASSEMBLE %s runs=%d %s' % ('CLEAN' if rep['clean'] else 'UNCLEAN', len(rep['runs']),
                                      ' '.join('%s:%s' % (p['code'], p['name']) for p in rep['problems'])))
    return 0 if rep['clean'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
