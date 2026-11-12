"""vm2.py score_check (spec §10.3, §9.5, delta v2.1 §2.8, §2.10.13): the carriers the scorer must use and the
check of the scorer's manifest. build refuses (exit 4, writes nothing) unless the audit, the assembly (verified)
and the owner checks agree; check re-derives the plan and exits 0 only on CONSISTENT. Never reads a target.
    score_check build|check [--plan DIR/SCORE_PLAN.json] --audit A --assembled S --pool L --owner-checks O
        [--manifest M] --out DIR|C"""
import argparse
import os
import sys

from ..core import outcome as O
from ..core.names import O63_REPORT, cjson, sha
from ..vio.v1reuse import sjson
from .audit import doc_bytes, read_bytes

PLAN_SCHEMA, CHECK_SCHEMA = 'cps.vm2-score-plan.v1', 'cps.vm2-score-check.v1'
OC_KEYS = {'schema', 'series', 'outcomes_sha256', 'checked_by', 'checked_utc', 'verdicts', 'unlogged'}
CARRIER = 'carrier/convert/carrier.json'


class Refused(Exception):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


def load(p):
    return sjson(read_bytes(p))


def owner_checks_ok(oc, series):
    if not isinstance(oc, dict) or set(oc) != OC_KEYS or oc['schema'] != 'cps.vm2-owner-checks.v1' \
            or oc['series'] != series or not isinstance(oc['checked_by'], str) or not oc['checked_by'] \
            or not isinstance(oc['verdicts'], list) or not isinstance(oc['unlogged'], list):
        return False
    return all(isinstance(v, dict) and set(v) == {'id', 'verdict', 'note'} for v in oc['verdicts']) and all(
        isinstance(u, dict) and set(u) == {'case', 'reader', 'conversation_utc', 'note'} for u in oc['unlogged'])


def plan(audit_p, asm_p, pool_p, oc_p):
    """Every check of build, before anything is written: (plan doc, {path: bytes} of the empty carriers)."""
    au, asm, pool, oc_raw = load(audit_p), load(asm_p), load(pool_p), read_bytes(oc_p)
    if au.get('schema') != 'cps.vm2-audit.v1' or au.get('clean') is not True or au.get('outcomes') is None:
        raise Refused('AUDIT_NOT_CLEAN')
    outs = au['outcomes']
    osha = sha(cjson(outs))
    if osha != au['outcomes_sha256'] or osha != au['all_frozen_outcomes_sha256'] \
            or osha != asm.get('outcomes_sha256') or osha != asm.get('outcomes_check_sha256'):
        raise Refused('OUTCOMES_MISMATCH')
    if asm.get('clean') is not True or asm.get('series') != au['series'] or asm.get('problems'):
        raise Refused('ASSEMBLE_NOT_CLEAN')
    if asm.get('verify_frozen') is not True or any(x.get('verify') != 'DONE' for x in asm['runs']):
        raise Refused('ASSEMBLE_NOT_VERIFIED')
    if not isinstance(au.get('o63'), dict) or au['o63'].get('missing') != []:
        raise Refused('O63_ATTESTATION_MISSING', (au.get('o63') or {}).get('missing'))
    items = au['owner_items']
    if items[:len(outs['owner_items'])] != outs['owner_items']:
        raise Refused('OUTCOMES_MISMATCH', 'owner_items')
    try:
        oc = sjson(oc_raw)
    except (ValueError, UnicodeDecodeError):
        oc = None
    if not owner_checks_ok(oc, au['series']) or oc['outcomes_sha256'] != osha:
        raise Refused('OWNER_CHECKS_INVALID')
    outs2 = dict(outs, owner_items=items)
    try:
        fd = O.final_dispositions(outs2, dict(oc, outcomes_sha256=sha(cjson(outs2))))
    except O.OwnerChecksInvalid as x:
        raise Refused('OWNER_CHECKS_INVALID', x.detail)
    if fd['missing']:
        raise Refused('OWNER_CHECKS_INCOMPLETE', sorted(fd['missing']))
    cases = pool.get('pool') if isinstance(pool, dict) else pool
    pairs = {(p['case'], p['reader']): p for p in fd['pairs']}
    if not isinstance(cases, list) or not cases or len(set(cases)) != len(cases) \
            or any((c, r) not in pairs for c in cases for r in 'AB'):
        raise Refused('POOL_INVALID')
    runs = {x['run']: x for x in asm['runs']}
    readers, empties = {'A': {}, 'B': {}}, {}
    for c in cases:
        for rd in 'AB':
            p = pairs[c, rd]
            row = {'disposition': p['disposition'], 'reason': p['reason'], 'also': p['also'], 'visual': p['visual']}
            if p['disposition'] == 'SCORE':
                x = runs.get(p['run'])
                path = os.path.join(x['path'], CARRIER) if x else None
                got = sha(read_bytes(path)) if path and os.path.isfile(path) else None
                if got is None or got != p['carrier_sha256'] or got != x['carrier_listed_sha256'] \
                        or x['frozen_sha256'] != p['frozen_sha256']:
                    raise Refused('CARRIER_MISMATCH', '%s/%s' % (rd, c))
            else:
                data = doc_bytes({'items': [], 'cps_failed_run': {
                    'schema': 'cps.vm2-failed-run.v1', 'series': au['series'], 'seq': p['frozen_seq'], 'case_id': c,
                    'reader': rd, 'job_dir': p['job_dir'], 'reason': p['reason'], 'frozen_sha256': p['frozen_sha256']}})
                path, got = os.path.join('carriers', rd, c, 'EMPTY_CARRIER.json'), sha(data)
                empties[path] = data
            readers[rd][c] = dict(row, carrier_path=path, carrier_sha256=got)
    doc = {'schema': PLAN_SCHEMA, 'series': au['series'], 'outcomes_sha256': osha, 'audit_sha256': sha(read_bytes(audit_p)),
           'assemble_sha256': sha(read_bytes(asm_p)), 'owner_checks_sha256': sha(oc_raw), 'checked_by': oc['checked_by'],
           'pool_sha256': sha(read_bytes(pool_p)), 'isolation_statement': O63_REPORT,
           'qualification_flagged': fd['qualification_flagged'], 'pool': cases, 'readers': readers}
    return doc, empties


def placed(doc, empties, out):
    """The plan as build writes it into out: each empty carrier's path under out."""
    for rd in 'AB':
        for row in doc['readers'][rd].values():
            if row['carrier_path'] in empties:
                row['carrier_path'] = os.path.join(out, row['carrier_path'])
    return doc


def build(a):
    out = os.path.abspath(a.out)
    if os.path.lexists(out) and (not os.path.isdir(out) or os.listdir(out)):
        raise Refused('OUT_NOT_EMPTY')
    doc, empties = plan(a.audit, a.assembled, a.pool, a.owner_checks)
    for rel, data in sorted(empties.items()):
        os.makedirs(os.path.join(out, os.path.dirname(rel)), exist_ok=True)
        with open(os.path.join(out, rel), 'xb') as f:
            f.write(data)
    with open(os.path.join(out, 'SCORE_PLAN.json'), 'xb') as f:
        f.write(doc_bytes(placed(doc, empties, out)))
    print('SCORE_PLAN written: %d cases, flagged=%s' % (len(doc['pool']), doc['qualification_flagged']))
    print(O63_REPORT)
    return 0


def check(a):
    """MAINT-8: the plan re-derived from the four inputs (their sha256 are in it) must be the plan file's bytes."""
    pl_raw, man_raw = read_bytes(a.plan), read_bytes(a.manifest)
    pl = placed(*plan(a.audit, a.assembled, a.pool, a.owner_checks), os.path.dirname(os.path.abspath(a.plan)))
    if doc_bytes(pl) != pl_raw:
        raise Refused('PLAN_MISMATCH')
    man, problems = sjson(man_raw), []
    pool = pl['pool']
    mreaders = man.get('readers') if isinstance(man, dict) else None
    if not isinstance(mreaders, dict) or sorted(man.get('pool') or []) != sorted(pool):
        problems.append({'code': 'POOL', 'reader': None, 'case': None})
        mreaders = mreaders if isinstance(mreaders, dict) else {}
    for rd in 'AB':
        mr = mreaders.get(rd) if isinstance(mreaders.get(rd), dict) else {}
        for c in sorted(set(pool) | set(mr)):
            want, e = pl['readers'][rd].get(c), mr.get(c)
            got = e.get('carrier_sha256') if isinstance(e, dict) else None
            if want is None or got != want['carrier_sha256']:
                problems.append({'code': 'CARRIER', 'reader': rd, 'case': c})
            elif not os.path.isfile(want['carrier_path']) or sha(read_bytes(want['carrier_path'])) != got:
                problems.append({'code': 'CARRIER_FILE', 'reader': rd, 'case': c})
    for c in pool:
        ea, eb = (mreaders.get('A') or {}).get(c), (mreaders.get('B') or {}).get(c)
        if isinstance(ea, dict) and isinstance(eb, dict) and ea.get('carrier_sha256') == eb.get('carrier_sha256'):
            problems.append({'code': 'SHARED', 'reader': None, 'case': c})
    verdict = 'INCONSISTENT' if problems else 'CONSISTENT'
    with open(a.out, 'xb') as f:
        f.write(doc_bytes({'schema': CHECK_SCHEMA, 'verdict': verdict, 'problems': problems, 'plan_sha256': sha(pl_raw),
                           'manifest_sha256': sha(man_raw), 'owner_checks_sha256': pl['owner_checks_sha256'],
                           'checked_by': pl['checked_by']}))
    print(verdict)
    return 0 if verdict == 'CONSISTENT' else 1


def main(argv):
    ap = argparse.ArgumentParser(prog='vm2.py score_check')
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    for k in ('audit', 'assembled', 'pool', 'owner-checks', 'out'):
        b.add_argument('--' + k, required=True)
    c = sub.add_parser('check')
    for k in ('plan', 'audit', 'assembled', 'pool', 'owner-checks', 'manifest', 'out'):
        c.add_argument('--' + k, required=True)
    a = ap.parse_args(argv)
    try:
        return build(a) if a.cmd == 'build' else check(a)
    except Refused as r:
        print('REFUSED %s%s' % (r.code, '' if r.detail is None else ' %s' % (r.detail,)))
        return 4
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeDecodeError) as x:
        print('REFUSED INPUT_INVALID %s' % type(x).__name__)
        return 4


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
