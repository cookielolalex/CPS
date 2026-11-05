"""Scope stage, step 3 (candidate 046g, FIELD_ROLES R59): agreement of the scope tool and the scope reader.

Source-preparation role only. Reads the tool's SCOPE_PROPOSAL.json, the SCOPE_DIGEST.json it pinned and the scope
reader's response (SCOPE_READER_PROMPT_TEMPLATE.md, schema cps.scope-reader-response.v1). Prints hashes, indexes and
codes only.

Usage: python3 -I -B scope_agree.py --proposal /abs/SCOPE_PROPOSAL.json --digest /abs/SCOPE_DIGEST.json
                                    --reader /abs/SCOPE_READER_RESPONSE.json --out-dir /abs/NEW_DIR

The tool and the reader must agree on the bill sheet, the R49 end row and the in_scope flag of every sheet. Roles may
differ between out-of-scope roles (for example other and resource_statistics); every difference is recorded.
  - Agreement: writes SCOPE_DECISION.json (cps.scope-decision.v1, status FROZEN_AGREED), which carries the payload of the
    context:scope fact that make_scoped_inventory.py writes. Exit 0.
  - Disagreement, or a reader that leaves the bill sheet or the end row open: writes SCOPE_HOLD.json (status
    HELD_FOR_OWNER) with every difference. There is no tie-break run. Exit 3.
  - A proposal that is not PROPOSED (NOT_APPLIED or HOLD), a hash mismatch or a malformed reader response: refused,
    nothing written. Exit 1.
A decision is admissible for a generation admission only when the reader is a fresh-context scope reader
(reader.kind fresh_context_scope_reader with a nonblank observed model); any other reader kind (for example an
engineering stand-in) gives admissible false.
"""
import argparse, hashlib, importlib.util, json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROUTE = HERE.parent / 'package' / 'tools' / 'cps046b_route.py'
READER_SCHEMA = 'cps.scope-reader-response.v1'
DECISION_SCHEMA = 'cps.scope-decision.v1'
READER_KIND = 'fresh_context_scope_reader'
ROLES = ('bill', 'summary', 'analysis', 'resource_statistics', 'other')
READER_KEYS = ('schema', 'case_id', 'digest_sha256', 'reader', 'bill_sheet_index', 'end_row', 'sheets', 'doubts')
READER_SHEET_KEYS = ('index', 'role', 'in_scope', 'reason')


class Refused(Exception):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_route():
    spec = importlib.util.spec_from_file_location('cps046g_route_for_scope_agree', ROUTE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def strict(route, raw, what):
    try:
        return route.strict_load(raw)
    except route.Rejected as e:
        raise Refused('INVALID_JSON', {'file': what, 'error': str(e)})


def posint(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def check_reader(r, proposal, digest_sha):
    if not isinstance(r, dict) or set(r) != set(READER_KEYS):
        raise Refused('READER_KEYS', {'expected': list(READER_KEYS)})
    if r['schema'] != READER_SCHEMA:
        raise Refused('READER_SCHEMA', {'expected': READER_SCHEMA})
    if r['case_id'] != proposal['case_id']:
        raise Refused('READER_CASE_ID')
    if r['digest_sha256'] != digest_sha:
        raise Refused('READER_DIGEST_SHA256', 'the reader must state the sha256 of the digest bytes it read')
    rd = r['reader']
    if not isinstance(rd, dict) or not all(isinstance(rd.get(k), str) for k in ('kind', 'model', 'effort')):
        raise Refused('READER_RECORD', 'reader: {kind, model, effort} strings')
    for k in ('bill_sheet_index', 'end_row'):
        if r[k] is not None and not posint(r[k]):
            raise Refused('READER_FIELD_TYPE', {'key': k})
    if not isinstance(r['doubts'], list) or not all(isinstance(x, str) for x in r['doubts']):
        raise Refused('READER_DOUBTS', 'doubts is a list of strings')
    want = [s['index'] for s in proposal['sheets']]
    if not isinstance(r['sheets'], list) or [s.get('index') if isinstance(s, dict) else None for s in r['sheets']] != want:
        raise Refused('READER_SHEETS', {'expected_indexes_in_order': want})
    for s in r['sheets']:
        if (set(s) != set(READER_SHEET_KEYS) or s['role'] not in ROLES or not isinstance(s['in_scope'], bool)
                or not isinstance(s['reason'], str) or not s['reason'].strip()):
            raise Refused('READER_SHEET_FIELDS', {'sheet': s.get('index'), 'roles': list(ROLES)})


def decide(proposal_raw, digest_raw, reader_raw, route):
    proposal = strict(route, proposal_raw, 'proposal')
    if not isinstance(proposal, dict) or proposal.get('schema') != 'cps.scope-proposal.v1':
        raise Refused('PROPOSAL_SCHEMA')
    if proposal['status'] != 'PROPOSED':
        raise Refused('PROPOSAL_NOT_PROPOSED', {'status': proposal['status'],
                      'note': 'NOT_APPLIED: the packet is the full inventory, no scope stage; HOLD: the case goes to the owner'})
    digest_sha = sha(digest_raw)
    if proposal['digest'] is None or proposal['digest']['sha256'] != digest_sha:
        raise Refused('DIGEST_SHA256_MISMATCH')
    digest = strict(route, digest_raw, 'digest')
    if digest.get('full_inventory_sha256') != proposal['full_inventory_sha256']:
        raise Refused('DIGEST_INVENTORY_MISMATCH')
    reader = strict(route, reader_raw, 'reader')
    check_reader(reader, proposal, digest_sha)
    tool_flags = {s['index']: s['in_scope'] for s in proposal['sheets']}
    diffs = []
    if reader['bill_sheet_index'] != proposal['bill']['sheet_index']:
        diffs.append({'what': 'bill_sheet_index', 'tool': proposal['bill']['sheet_index'], 'reader': reader['bill_sheet_index']})
    if reader['end_row'] != proposal['bill']['end_row']:
        diffs.append({'what': 'end_row', 'tool': proposal['bill']['end_row'], 'reader': reader['end_row']})
    for s in reader['sheets']:
        if s['in_scope'] != tool_flags[s['index']]:
            diffs.append({'what': 'in_scope', 'sheet': s['index'], 'tool': tool_flags[s['index']], 'reader': s['in_scope']})
    role_diffs = [{'sheet': s['index'], 'tool': t['role'], 'reader': s['role']} for s, t in zip(reader['sheets'], proposal['sheets'])
                  if s['role'] != t['role']]
    bill_role = [s['index'] for s in reader['sheets'] if s['role'] == 'bill']
    if bill_role != [reader['bill_sheet_index']]:
        diffs.append({'what': 'reader_bill_role', 'reader_bill_roles': bill_role, 'reader_bill_sheet_index': reader['bill_sheet_index'],
                      'note': 'the reader must give role bill to exactly the sheet it names'})
    hashes = {'full_inventory_sha256': proposal['full_inventory_sha256'], 'proposal_sha256': sha(proposal_raw),
              'digest_sha256': digest_sha, 'reader_response_sha256': sha(reader_raw),
              'rules_excerpt_sha256': proposal['rules_excerpt']['sha256'] if proposal.get('rules_excerpt') else None,
              'tool_sha256': proposal['tool'].get('sha256'), 'agree_tool_sha256': sha(Path(__file__).read_bytes())}
    common = {'case_id': proposal['case_id'], 'family_id': proposal['family_id'], 'frozen_utc': datetime.now(timezone.utc).isoformat(),
              **hashes, 'reader': reader['reader'],
              'reader_doubts_count': len(reader['doubts']), 'role_differences': role_diffs, 'tool_flags': proposal['flags']}
    if diffs:
        return 'SCOPE_HOLD.json', dict({'schema': 'cps.scope-hold.v1', 'status': 'HELD_FOR_OWNER',
                                        'note': 'the scope tool and the scope reader disagree; no tie-break run; the owner decides (R59)'},
                                       **common, differences=diffs)
    admissible = reader['reader']['kind'] == READER_KIND and bool(reader['reader']['model'].strip())
    fact = {'schema': route.SCOPE_FACT_SCHEMA, 'rule': route.SCOPE_RULE, 'bill_rule': route.SCOPE_BILL_RULE,
            'threshold': {'content_cells_literal_or_cached': proposal['content_cells_literal_or_cached'], 'limit': route.SCOPE_THRESHOLD},
            'bill_sheet_index': proposal['bill']['sheet_index'], 'bill_header_row': proposal['bill']['header_row'],
            'end_row': proposal['bill']['end_row'],
            'sheets': [{k: s[k] for k in route.SCOPE_SHEET_KEYS} for s in proposal['sheets']],
            'digest_sha256': digest_sha, 'full_inventory_sha256': proposal['full_inventory_sha256'],
            'agreement': route.SCOPE_AGREEMENT}
    return 'SCOPE_DECISION.json', dict({'schema': DECISION_SCHEMA, 'status': 'FROZEN_AGREED', 'admissible': admissible,
                                        'admissibility_note': ('fresh-context scope reader' if admissible else
                                                               'not admissible for a generation admission: the reader is not a fresh-context scope reader')},
                                       **common, agreement={'bill_sheet_index': True, 'end_row': True, 'in_scope_flags': True},
                                       reader_reasons=[{'index': s['index'], 'role': s['role'], 'reason': s['reason']} for s in reader['sheets']],
                                       scope_fact=fact)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Scope stage step 3 (R59): tool-reader agreement; freezes SCOPE_DECISION.json or holds.')
    for k in ('proposal', 'digest', 'reader', 'out-dir'):
        ap.add_argument('--' + k, required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        if not all(p.is_absolute() for p in (a.proposal, a.digest, a.reader, a.out_dir)):
            raise Refused('ABSOLUTE_PATH_REQUIRED')
        if a.out_dir.exists():
            raise Refused('OUTPUT_EXISTS')
        name, obj = decide(a.proposal.read_bytes(), a.digest.read_bytes(), a.reader.read_bytes(), load_route())
    except Refused as e:
        sys.stderr.write(json.dumps({'status': 'REFUSED', 'code': e.code, 'detail': e.detail}, ensure_ascii=False) + '\n')
        return 1
    raw = (json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + '\n').encode('utf-8')
    a.out_dir.mkdir(parents=True)
    with open(a.out_dir / name, 'xb') as f:
        f.write(raw)
    print(json.dumps({'status': obj['status'], 'file': name, 'sha256': sha(raw), 'case_id': obj['case_id'],
                      'admissible': obj.get('admissible'), 'differences': obj.get('differences', []),
                      'role_differences': len(obj['role_differences']), 'values_printed': False}, ensure_ascii=False))
    return 0 if obj['status'] == 'FROZEN_AGREED' else 3


if __name__ == '__main__':
    sys.exit(main())
