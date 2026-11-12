"""vm2.py audit (spec §10.1, delta v2.1 §2.5-§2.10): the maintainer's re-check of a series from a Drive listing.

    audit --series Q1 --listing LISTING.json --dir DOWNLOADS --setup-listing SETUP.json --setup-dir SETUP_DOWNLOADS
          --out AUDIT.json [--tolerance 600]

A listing is a JSON list (or {"files": [...]}) of Drive rows; DOWNLOADS holds each at <dir>/<id>/<name>. Exit 0 iff no
anomaly, 1 otherwise, 2 usage. AUD_REBASE_OVER_PRESENT_PART and o63 are owner or score_check items, not anomalies.
Reads nothing but its arguments and the pinned runner; writes only --out."""
import argparse
import os
import re
import sys

from ..core import entry as E
from ..core import fold as F
from ..core import outcome as O
from ..core import session as S
from ..core.names import (ENTRY, O63_NOTE, cjson, entry_name, fm, parse_part, series_folder, sha, tool_list,
                          utc_epoch, utc_minus)
from ..vio.runner import load_runner
from ..vio.v1compat import Halt
from ..vio.v1reuse import Archive, kit_members, sjson

SCHEMA = 'cps.vm2-audit.v1'
KEEP = ('ledger/LEDGER.jsonl', 'final/ALL_FROZEN.json', 'final/LEDGER_FINAL.jsonl', 'attest/tools.txt',
        'job/run/GENERATION_RECORD.json')
ROOTS = ('MANIFEST.json', 'job', 'ledger', 'ai', 'transcript', 'attest', 'delivery', 'final')
FOLDER_MIME = 'application/vnd.google-apps.folder'


def doc_bytes(x):
    import json
    return (json.dumps(x, sort_keys=True, ensure_ascii=True, indent=1, allow_nan=False) + '\n').encode('ascii')


def read_bytes(p):
    with open(p, 'rb') as f:
        return f.read()


def load_listing(path):
    """([{'id', 'name', 'md5', 'size', 'created'}], folder rows skipped); ValueError when malformed. md5 hidden (§X.10)
    gives md5 None: download() takes the downloaded bytes' md5."""
    d = sjson(read_bytes(path))
    out, folders = [], 0
    for r in d['files'] if isinstance(d, dict) else d:
        if r.get('mimeType') == FOLDER_MIME:
            folders += 1
            continue
        size, ct = r['size'], r['createdTime']
        size = int(size) if isinstance(size, str) and size.isdigit() else size
        m5 = r.get('md5Checksum')
        if not (fm(r'[A-Za-z0-9_-]{1,200}', r['id']) and isinstance(r['name'], str)
                and (m5 is None or fm(r'[0-9a-f]{32}', m5))
                and isinstance(size, int) and isinstance(ct, str) and utc_epoch(ct[:19] + 'Z') is not None):
            raise ValueError('listing row')
        out.append({'id': r['id'], 'name': r['name'], 'md5': m5, 'size': size, 'created': utc_epoch(ct[:19] + 'Z')})
    return out, folders


def download(ddir, r):
    """sha256 of row r's file <ddir>/<id>/<name>, or None when absent, a link, or not the listed md5 and size."""
    import hashlib
    p = os.path.join(ddir, r['id'], r['name'])
    if '/' in r['name'] or r['name'] in ('', '.', '..') or not os.path.isfile(p) or os.path.islink(p):
        return None
    h, m, n = hashlib.sha256(), hashlib.md5(), 0
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
            m.update(b)
            n += len(b)
    if r['md5'] is None and n == r['size']:
        r['md5'] = m.hexdigest()                    # md5 hidden: the downloaded bytes' md5 (§X.10)
    return h.hexdigest() if n == r['size'] and m.hexdigest() == r['md5'] else None


def open_entry(path):
    """(doc, Archive) of an entry tgz checked against its own payload.members (§3.3); raises Halt on any refusal."""
    a = Archive(path, ROOTS)
    try:
        doc = a.manifest
        a.check({m[0]: ('dir', m[2]) if m[1] == 'dir' else ('file', *m[2:5]) for m in doc['payload']['members']})
        return doc, a
    except (KeyError, TypeError, IndexError, AttributeError):
        a.close()
        raise Halt('STOP', 'ARCHIVE_MANIFEST_MISMATCH')
    except Halt:
        a.close()
        raise


def kit_info(path, kit_sha):
    """The session's kit dict (sha256, members, config, release_sha256) plus files {path: bytes} of a kit zip."""
    files = kit_members(path)
    return {'sha256': kit_sha, 'members': sorted([k, sha(v)] for k, v in files.items()), 'files': files,
            'config': sjson(files['VM_HELPER_CONFIG.json']), 'release_sha256': sha(files['RELEASE.json'])}


def ledger_problem(cj, raw):
    led = cj.Ledger('/nonexistent/LEDGER.jsonl', create=False, readonly=True)
    led.raw = raw
    return led.chain_problem()


def all_frozen_doc(state, ledger_final):
    """The ALL_FROZEN document (§9.4) for the state after FINAL; the audit compares the Dot's with it."""
    outs = O.outcomes(state)
    runs = [{'run': k, 'job_dir': R['job_dir'], 'frozen_sha256': R['frozen']['frozen_sha256'],
             'frozen_seq': R['frozen']['seq'], 'frozen_entry': entry_name(state['series'], R['frozen']['seq']),
             'png_parts': list((R['png'] or {}).get('parts') or []), 'flags': list(R['flags']),
             'visual': R['frozen']['visual']}
            for k in state['order'] for R in [state['runs'][k]] if R['status'] == 'FROZEN']
    return {'schema': 'cps.vm2-all-frozen.v1', 'series': state['series'], 'final_seq': state['seq'],
            'genesis': state['genesis'], 'release_sha256': state['release_sha256'], 'kit_sha256': state['kit_sha256'],
            'ledger_final': {'sha256': sha(ledger_final), 'bytes': len(ledger_final)}, 'runs': runs,
            'outcomes': outs, 'outcomes_sha256': sha(cjson(outs))}


class Audit:
    def __init__(self, series, rows, ddir, srows, sdir, tol, folders=0):
        self.series, self.rows, self.ddir, self.srows, self.sdir, self.tol = series, rows, ddir, srows, sdir, tol
        self.anomalies, self.owner_review, self.extra_items, self.kits, self.cj = [], [], [], {}, None
        self.ent, self.prt, self.docs, self.folders, self.o63 = {}, {}, {}, folders, {'checked': 0, 'missing': []}

    def add(self, code, name, detail=None):
        a = {'code': code, 'name': name, 'detail': detail}
        if a not in self.anomalies:
            self.anomalies.append(a)

    def names(self):
        """Step 1: names, series, downloads, duplicates, gaps."""
        for r in self.rows:
            n, m, p = r['name'], re.fullmatch(ENTRY, r['name'], re.ASCII), parse_part(r['name'])
            ser = m.group(1) if m else (p[0] if p else None)
            if ser != self.series:
                q = ser is not None and ser[0] == 'Q' == self.series[0]
                self.add('AUD_SECOND_QUALIFICATION_SERIES' if q else 'AUD_FOREIGN_FILE', n)
                continue
            r['sha'] = download(self.ddir, r)
            if r['sha'] is None:
                self.add('AUD_DOWNLOAD_MISMATCH', n)
                continue
            key = int(m.group(2)) if m else n
            (self.ent if m else self.prt).setdefault(key, {}).setdefault(r['md5'], []).append(r)
        for groups in list(self.ent.values()) + list(self.prt.values()):
            if len(groups) > 1:
                self.add('AUD_DUPLICATE_SEQ', next(iter(groups.values()))[0]['name'])
        self.top = max(self.ent, default=0)
        for k in range(1, self.top + 1):
            if k not in self.ent:
                self.add('AUD_GAP', entry_name(self.series, k))

    def read(self, k, md5):
        if (k, md5) not in self.docs:
            r = self.ent[k][md5][0]
            try:
                doc, a = open_entry(os.path.join(self.ddir, r['id'], r['name']))
                files = {n: a.read(n) for n in KEEP if n in a.by and a.by[n].isreg()}
                a.close()
                self.docs[k, md5] = (doc, files, r['sha'], None)
            except Halt as h:
                self.docs[k, md5] = (None, None, r['sha'], h.code)
        return self.docs[k, md5]

    def pick(self, k):
        g = self.ent.get(k, {})
        if len(g) == 1:
            return next(iter(g))
        conf = set()
        for md in self.ent.get(k + 1, {}):
            doc = self.read(k + 1, md)[0]
            if doc and isinstance(doc.get('confirms'), list) and doc['confirms']:
                conf |= {cp.get('md5') for cp in doc['confirms'][0].get('copies') or []}
        c = [md for md in g if md in conf]
        return c[0] if len(c) == 1 else None

    def kit(self, kit_sha):
        if kit_sha not in self.kits:
            rs = [r for r in self.srows if r['name'] == 'SESSION_KIT_%s.zip' % kit_sha[:12]
                  and download(self.sdir, r) == kit_sha]
            try:
                self.kits[kit_sha] = kit_info(os.path.join(self.sdir, rs[0]['id'], rs[0]['name']), kit_sha)
            except (IndexError, Halt, KeyError, ValueError, UnicodeDecodeError):
                self.kits[kit_sha] = None
        return self.kits[kit_sha]

    def kit_change(self, doc, before):
        """§2.7: the session's kit_change on the two zips; a CLEAR's kit also names its halt (O59)."""
        b, name = doc['body'], doc['name']
        a, k = self.kit(b['kit_change']['from_kit_sha256']), self.kit(b['kit_change']['to_kit_sha256'])
        if a is None or k is None:
            return self.add('AUD_KIT', name, 'kit_change')
        code, kc = S.kit_change(before, k, a)
        if kc != b['kit_change']:
            self.add('AUD_KIT_CHANGE', name, 'recompute')
        if code:
            self.add('AUD_KIT_CHANGE', name, code)
        if doc['kind'] == 'CLEAR' and not S.clear_ok(k['config'].get('clear'), self.series, b['halt_seq'], b['code']):
            self.add('AUD_KIT_CHANGE', name, 'clear')

    def cleared_local(self, doc):
        """SD-53: the entry's kit names the local clear, is not the halted kit, and is a config-only change of it."""
        cl, k, kc = doc['cleared_local'], self.kit(doc['kit_sha256']), doc['body'].get('kit_change')
        old = self.kit(cl['kit_sha256']) if cl['kit_sha256'] is not None else None
        if not (k is not None and S.clear_ok(k['config'].get('clear'), self.series, cl['head_seq'], cl['code'])
                and cl['kit_sha256'] != doc['kit_sha256'] and (kc is None or kc['config_only'] is True)
                and (cl['kit_sha256'] is None or (old is not None and S.config_only_ok(old, k) is None))):
            self.add('AUD_KIT_CHANGE', doc['name'], 'cleared_local')

    def kit_jobs(self, doc, ki):
        """MAINT-10: jobs_of the kit's release qualification.jobs_file (a kit member under the layout's runtime)."""
        try:
            jf, rt = sjson(ki['files']['RELEASE.json'])['qualification']['jobs_file'], doc['body']['layout']['runtime']
            return F.jobs_of(sjson(ki['files'][jf[len(rt) + 1:]])) if jf.startswith(rt + '/') else None
        except (KeyError, TypeError, AttributeError, ValueError, UnicodeDecodeError):
            return None

    def o63_check(self, doc, ok):
        self.o63['checked'] += 1
        if not ok:
            self.o63['missing'].append(doc['name'])

    def o63_frozen(self, doc, files, R, ai):
        """GAP-10: a FROZEN GENERATION_RECORD.json holds its consumed G entry's tools, O63 note and final message."""
        gs = [ro for ro in R['roles'].values() if ro['role'] == 'G' and ro['consumed']]
        if gs:
            try:
                g, gf = ai[max(gs, key=lambda r: r['consumed']['seq'])['archives'][-1]['seq']]
                gr, gb = sjson(files['job/run/GENERATION_RECORD.json']), g['body']
                ok = gr['tools_enabled'] == tool_list(gf['attest/tools.txt']) \
                    and gr['notes'] == O63_NOTE % gb['attested']['tools_present']['sha256'] \
                    and sha(gr['final_message'].encode('utf-8')) == gb['final_message_sha256']
            except (KeyError, TypeError, AttributeError, ValueError, UnicodeDecodeError):
                ok = False
            self.o63_check(doc, ok)

    def refold(self):
        """Steps 2, 3, 5, 6, 7 along the chain from GENESIS; returns [(doc, files, created, state_before)]."""
        state, chain, prev, ledgers, ai = None, [], None, {}, {}
        for k in range(1, self.top + 1):
            md = self.pick(k) if k in self.ent else None
            if md is None:
                break
            name = entry_name(self.series, k)
            for other in self.ent[k]:
                if other != md:
                    self.add('AUD_UNFOLDED_ENTRY', name)
            doc, files, data, err = self.read(k, md)
            if err or E.validate_entry(doc) or doc['name'] != name:
                self.add('AUD_ENTRY_CORRUPT', name, err or 'schema')
                break
            if prev is not None:
                c0 = doc['confirms'][0] if doc['confirms'] else {'copies': []}
                if doc['prev_sha256'] != prev[0] or {cp['md5'] for cp in c0['copies']} != {prev[1]}:
                    self.add('AUD_LINK', name)
                for c in doc['confirms']:
                    for cp in c['copies']:
                        if not any(r['id'] == cp['id'] and r['name'] == c['name'] and r['md5'] == cp['md5']
                                   and r['size'] == cp['size'] for r in self.rows):
                            self.add('AUD_CONFIRMS', name)
            try:
                s2 = F.apply(state, doc)
            except F.ChainInvalid as x:
                self.add('AUD_CHAIN_INVALID', name, x.code)
                break
            if cjson(s2) != cjson(doc['state']):
                self.add('AUD_STATE_MISMATCH', name)
            lb = files.get('ledger/LEDGER.jsonl')
            if lb is not None:
                base = ledgers.get(((state or {}).get('ledger') or {}).get('seq'))
                if (base is not None and not lb.startswith(base)) or ledger_problem(self.cj, lb):
                    self.add('AUD_LEDGER_FORK', name)
                ledgers[k] = lb
            ki = self.kit(doc['kit_sha256'])
            if ki is None:
                self.add('AUD_KIT', name)
            elif ki['release_sha256'] != doc['release_sha256']:
                self.add('AUD_KIT', name, 'release')
            elif doc['kind'] == 'GENESIS' and doc['body']['jobs'] not in (None, self.kit_jobs(doc, ki)):
                self.add('AUD_KIT', name, 'jobs')
            if doc['kind'] in ('RESTORE', 'CLEAR') and doc['body']['kit_change'] is not None:
                self.kit_change(doc, state)
            if doc['cleared_local'] is not None:
                self.cleared_local(doc)
            if doc['kind'] == 'AI' and doc['body']['revision'] == 1:        # O63 (§2.8): tools and final message
                ai[k], tp = (doc, files), doc['body']['attested'].get('tools_present')
                mem = {m[0]: m[4] for m in doc['payload']['members']}
                self.o63_check(doc, isinstance(tp, dict) and tp.get('source') in ('inventory', 'file') and
                               mem.get('attest/tools.txt') == tp.get('sha256') and 'attest/final_message.txt' in mem)
            if doc['kind'] == 'FROZEN':
                self.o63_frozen(doc, files, s2['runs'][doc['body']['run']], ai)
            if doc['kind'] in ('GENESIS', 'RESTORE'):
                ps = doc['body']['pass']
                if not any(r['name'] == ps.get('name') and r['md5'] == ps.get('md5') for r in self.srows):
                    self.add('AUD_PASS_MISSING', name)
            created = min(r['created'] for r in self.ent[k][md])
            if created < utc_epoch(doc['utc']) - self.tol or (chain and chain[-1][2] > created + self.tol):
                self.add('AUD_TIME_ORDER', name)
            chain.append((doc, files, created, state))
            state, prev = s2, (data, md)
            if doc['kind'] == 'FINAL':
                break
        self.state, self.chain, self.ledgers = state, chain, ledgers
        return chain

    def parts(self):
        """Step 1 (unreachable, after FINAL) and step 2 (parts, declared rebase)."""
        sfold, named = series_folder(self.series), set()
        final = self.state['seq'] if self.state and self.state['phase'] == 'FINAL' else None
        for i, (doc, _, _, _) in enumerate(self.chain):
            nxt = self.chain[i + 1][0] if i + 1 < len(self.chain) else None
            rb = nxt['body'].get('rebase') if nxt and nxt['kind'] == 'RESTORE' else None
            declared = set(rb['missing_parts']) if rb and rb['head_seq'] == doc['seq'] else set()
            for p in doc['parts']:
                named.add(p['name'])
                have = self.prt.get(p['name'], {})
                if p['name'] in declared:
                    if have:
                        self.review(doc, nxt, p['name'])
                    continue
                if p['folder'] != sfold:
                    continue
                rs = have.get(p['md5'], [])
                if not rs or rs[0]['sha'] != p['sha256'] or rs[0]['size'] != p['bytes']:
                    self.add('AUD_PART_MISSING', p['name'])
        for k in self.ent:
            if final is not None and k > final:
                self.add('AUD_AFTER_FINAL', entry_name(self.series, k))
        for n in self.prt:
            if final is not None and parse_part(n)[1] > final:
                self.add('AUD_AFTER_FINAL', n)
            elif n not in named:
                self.add('AUD_UNREACHABLE_PART', n)

    def review(self, head, restore, part):
        """AUD_REBASE_OVER_PRESENT_PART: an owner-review item plus a SUPERSEDED_WINDOW owner item (§10.1)."""
        b, tol = head['body'], self.state['genesis']['gates'].get('p3_clock_tolerance_seconds') or 0
        st = b.get('start') if head['kind'] in ('STAGE', 'FROZEN') else None
        R = self.state['runs'].get(b.get('run'))
        it = {'kind': 'SUPERSEDED_WINDOW', 'case': R and R['case'], 'reader': R and R['reader'],
              'run': b.get('run'), 'role': st and st['role'], 'attempt': st and st['attempt'],
              'start_no': st and st['start_no'],
              'window': [utc_minus(head['utc'], tol), utc_minus(restore['utc'], -tol)]}
        it['id'] = sha(cjson(it))[:12]
        if it not in self.extra_items:
            self.extra_items.append(it)
        self.owner_review.append({'code': 'AUD_REBASE_OVER_PRESENT_PART', 'name': part, 'item': it['id']})

    def final(self):
        """Step 4: outcomes, ALL_FROZEN and LEDGER_FINAL against the audit's own fold."""
        s = self.state
        if s is None or s['phase'] != 'FINAL':
            if self.series[0] in 'QD':
                self.add('AUD_NO_FINAL', entry_name(self.series, s['seq'] if s else 0))
            return None
        doc, files = self.chain[-1][0], self.chain[-1][1]
        b, name = doc['body'], doc['name']
        af_raw, lf = files.get('final/ALL_FROZEN.json'), files.get('final/LEDGER_FINAL.jsonl')
        led = self.ledgers.get((s['ledger'] or {}).get('seq'))
        if af_raw is None or lf is None:
            return self.add('AUD_OUTCOMES_DIFF', name, 'members')
        if lf != led or sha(lf) != b['ledger_final_sha256'] or sha(lf) != (s['ledger'] or {}).get('sha256'):
            self.add('AUD_LEDGER_FORK', name, 'ledger_final')
        want = all_frozen_doc(s, lf)
        try:
            af = sjson(af_raw)
        except (ValueError, UnicodeDecodeError):
            af = None
        if not isinstance(af, dict) or af.get('outcomes') != want['outcomes'] \
                or af.get('outcomes_sha256') != want['outcomes_sha256'] or b['outcomes_sha256'] != want['outcomes_sha256']:
            self.add('AUD_OUTCOMES_DIFF', name, 'outcomes')
        elif af != want or sha(af_raw) != b['all_frozen_sha256'] or b['runs'] != len(want['runs']):
            self.add('AUD_OUTCOMES_DIFF', name, 'all_frozen')
        shas = {p['kind']: p['sha256'] for p in doc['parts']}
        if shas != {'ALLFZ': sha(af_raw), 'LEDGER': sha(lf)}:
            self.add('AUD_OUTCOMES_DIFF', name, 'parts')
        return af

    def run(self):
        self.cj = load_runner()
        self.names()
        self.refold()
        self.parts()
        af = self.final()
        outs = O.outcomes(self.state) if self.state else None
        ch = [d for d, _, _, _ in self.chain]
        clears = [{'seq': d['seq'], 'halt_seq': d['body']['halt_seq'], 'code': d['body']['code']}
                  for d in ch if d['kind'] == 'CLEAR']
        return {'schema': SCHEMA, 'series': self.series, 'clean': not self.anomalies,
                'counts': {'listed': len(self.rows), 'entries': len(self.ent), 'parts': len(self.prt),
                           'folded': len(self.chain), 'anomalies': len(self.anomalies), 'folders': self.folders,
                           'owner_review': len(self.owner_review), 'setup_listed': len(self.srows)},
                'o63': self.o63, 'approvals': [{'seq': d['seq'], 'kind': d['kind'], 'value': d['body'].get('approval')}
                                               for d in ch if d['kind'] in ('GENESIS', 'RESTORE')],
                'same_boot_restores': [d['seq'] for i, d in enumerate(ch)
                                       if d['kind'] == 'RESTORE' and i and ch[i - 1]['boot_id'] == d['boot_id']],
                'anomalies': self.anomalies, 'owner_review': self.owner_review,
                'final_seq': self.state['final']['seq'] if self.state and self.state['final'] else None,
                'outcomes': outs, 'outcomes_sha256': sha(cjson(outs)) if outs else None,
                'all_frozen_outcomes_sha256': af.get('outcomes_sha256') if isinstance(af, dict) else None,
                'o52_sheet': outs['o52_sheet'] if outs else [],
                'owner_items': (outs['owner_items'] if outs else []) + self.extra_items,
                'clears': clears, 'cleared_local': [{'seq': d['seq'], 'cleared_local': d['cleared_local']}
                                                    for d in ch if d['cleared_local'] is not None]}


def main(argv):
    ap = argparse.ArgumentParser(prog='vm2.py audit')
    for k in ('series', 'listing', 'dir', 'setup-listing', 'setup-dir', 'out'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--tolerance', type=int, default=600)
    a = ap.parse_args(argv)
    if not fm(r'Q[1-9]|E[1-9]|D[1-9][0-9]?', a.series):
        print('REFUSED VALUE_PATTERN series')
        return 2
    try:
        (rows, folders), (srows, _) = load_listing(a.listing), load_listing(a.setup_listing)
        for r in srows:
            if r['md5'] is None:
                download(a.setup_dir, r)
    except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError):
        print('REFUSED VALUE_PATTERN listing')
        return 2
    try:
        rep = Audit(a.series, rows, a.dir, srows, a.setup_dir, a.tolerance, folders).run()
    except Halt as h:
        print('STOP %s' % h.code)
        return 2
    data = doc_bytes(rep)
    with open(a.out, 'xb') as f:
        f.write(data)
    print('AUDIT %s anomalies=%d owner_review=%d outcomes_sha256=%s' % (
        'CLEAN' if rep['clean'] else 'UNCLEAN', len(rep['anomalies']), len(rep['owner_review']), rep['outcomes_sha256']))
    return 0 if rep['clean'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
