"""Scope stage, step 4 (candidate 046i, FIELD_ROLES R59): build or verify the scoped inventory.

Source-preparation role only. The scoped inventory is a projection of the FULL inventory under a frozen
SCOPE_DECISION.json (scope_agree.py). Prints hashes and counts only.

Build:  python3 -I -B make_scoped_inventory.py --full /abs/FULL/SOURCE_INVENTORY.json --decision /abs/SCOPE_DECISION.json
                                               --out-dir /abs/NEW_PACKET_DIR [--views-dir /abs/DIR]
Verify: python3 -I -B make_scoped_inventory.py --verify --full /abs/FULL/SOURCE_INVENTORY.json
                                               --decision /abs/SCOPE_DECISION.json --scoped /abs/PACKET/SOURCE_INVENTORY.json
                                               [--expect-scoped-sha256 HEX]   (the hash pinned in the admission)

The projection changes exactly these records and keeps every other record byte-identical:
  - sheets[]: in_scope set from the decision (the full inventory has every sheet in scope, except an empty sheet,
    rows x columns = 0 with no cell or view, which the builders write out of scope and the decision keeps out of scope);
  - cells[]: the cells of out-of-scope sheets are removed; kept cells are unchanged except their `views` list, which is
    renumbered with the view-id map below (a kept cell whose views keep their ids is byte-identical);
  - views[] and source.carrier_source.views: the views of out-of-scope sheets are removed and the kept views renumbered
    1..n in their original order (the route and writer004 require consecutive view ids); each kept view is unchanged
    except `id`, and its image record (file name and pins) is kept;
  - context_facts[]: one fact context:scope is appended; every existing fact is unchanged.
The census invariant still holds (rows x columns of the in-scope sheets equals the number of cells). The file uses the
builders' serialization (one record per line), so a kept record's line is byte-identical to its line in the full file.
The full inventory must already be in that serialization (re-serializing it must reproduce its bytes).

Build writes <out-dir>/SOURCE_INVENTORY.json, copies the in-scope view images named by views[].image.file from
--views-dir (default: the full inventory's directory) after checking their pinned bytes and sha256 (an inventory whose
images are not bound yet, such as SOURCE_INVENTORY.unbound.json, has none and the receipt says so), runs the
independent verification below and the route's check-inventory, and writes SCOPED_INVENTORY_RECEIPT.json with both
inventory hashes, the decision hash and the view-id map. Refuses (exit 1, nothing written) a decision that is not
FROZEN_AGREED, a full-inventory hash that differs from the decision, an inventory that already carries context:scope,
a sheet list that differs from the decision, or an existing output directory.

--verify compares the scoped inventory with the full one record by record, written independently of the build code:
top-level members and order, every sheet (only in_scope may differ, and it must equal the decision), the kept views
(only id may differ, renumbered in order), every kept cell (only views may differ, through the view-id map), the
removed cells and views (exactly those of out-of-scope sheets), the existing context facts (byte-identical) and the
appended context:scope (equal to the decision's payload plus decision_sha256), the census invariant, both
serializations, the full-inventory hash against the decision and, with --expect-scoped-sha256, the scoped hash against
the pinned value. Exit 0 PASS, 2 FAIL.

046i (owner decision O72, FIELD_ROLES R59 items 2 and 9): only the fact's basis text depends on the decision's bill rule
(BILL1.v1, BILL1.NOTOTAL.v1 or BILL1.NOHEADER.v1). Under BILL1.NOHEADER.v1 every non-empty sheet is in scope, so the
projection removes no cell or view, the view-id map is the identity and the scoped inventory equals the full inventory
record by record except the appended context:scope.
"""
import argparse, hashlib, importlib.util, json, shutil, sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROUTE = HERE.parent / 'package' / 'tools' / 'cps046b_route.py'
RECEIPT_SCHEMA = 'cps.scoped-inventory-receipt.v1'
FACT_NAMESPACE = 'cps.source_prep.scope'
LIST_KEYS = ('cells', 'sheets', 'views', 'context_facts', 'limitations')


class Refused(Exception):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_route():
    spec = importlib.util.spec_from_file_location('cps046i_route_for_scoped_inventory', ROUTE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def dump(x):
    return json.dumps(x, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def serialize(inv):
    """The builders' serialization (research/guideline046_003/source_prep/build_inventory_xlsx_v2.py serialize)."""
    parts = []
    for k, v in inv.items():
        if k in LIST_KEYS and isinstance(v, list):
            body = ',\n'.join('  ' + dump(x) for x in v)
            parts.append(f' {dump(k)}:[\n{body}\n ]' if v else f' {dump(k)}:[]')
        else:
            parts.append(f' {dump(k)}:{dump(v)}')
    return ('{\n' + ',\n'.join(parts) + '\n}\n').encode('utf-8')


def strict(route, raw, what):
    try:
        return route.strict_load(raw)
    except route.Rejected as e:
        raise Refused('INVALID_JSON', {'file': what, 'error': str(e)})


def fact_record(decision, decision_sha, route):
    payload = dict(decision['scope_fact'], decision_sha256=decision_sha)
    payload = {k: payload[k] for k in route.SCOPE_FACT_KEYS}
    reader = ('a fresh-context scope reader decided from the scope digest alone' if payload['agreement'] == route.SCOPE_AGREEMENT else
              'a reader that is not a fresh-context scope reader (an engineering stand-in: not admissible, and route v4.4 rejects '
              'this fact) decided from the scope digest alone')
    nototal_rule, noheader_rule = route.SCOPE_O72_RULES
    if payload['bill_rule'] == noheader_rule:          # 046i (O72, R59 item 9): the whole workbook
        basis = ('Scope decision for this packet (FIELD_ROLES R59 item 9, candidate 046i, owner decision O72). The source preparer '
                 'found no row with five or six of the six BILL1 header labels on any sheet of the full inventory (harness/scope_tool.py); '
                 + reader + '; the two agreed that no sheet has a bill header row, so the scope stage fixed no bill sheet and no end '
                 'row, and that every sheet except an empty one (rows x columns = 0) is in scope (harness/scope_agree.py), and the '
                 'decision was frozen before generation. This inventory holds the whole workbook; an empty sheet has no cell and stays '
                 'out of scope. Read it as an unscoped packet: R49-R51 decide the bill sheet, the quoted range and the rows from the '
                 'cells, and the sheet roles in this fact are labels, not R49 decisions. This fact is never field evidence.')
    else:
        agreed = ('the two agreed on the bill sheet, the R49 end row and every in_scope flag' if payload['bill_rule'] != nototal_rule else
                  'the two agreed on the bill sheet, that no cell below its header row in its 單價 or 複價 (or 金額) column reads exactly '
                  '合計 or 總計 (so end_row is its last row with content, not a total row, and R49 decides where the quoted range ends '
                  'inside it; owner decision O72), and every in_scope flag')
        basis = ('Scope decision for this scoped packet (FIELD_ROLES R59, candidate 046i). The source preparer computed BILL1 and the '
                 'R51 conditions on the full inventory (harness/scope_tool.py); ' + reader + '; ' + agreed + ' (harness/scope_agree.py), and the '
                 'decision was frozen before generation. This inventory holds only the cells and views of the in-scope sheets. '
                 'Scoped-out sheets are not missing or unreadable sources and are no reason to hold; no field, proof, raw selection, '
                 'link or review reason may cite or reconstruct them. This fact is never field evidence.')
    return {'ref': route.SCOPE_REF, 'namespace': FACT_NAMESPACE, 'value': dump(payload), 'basis': basis,
            'authority_pins': [{'label': 'frozen scope decision (SCOPE_DECISION.json)', 'sha256': decision_sha},
                               {'label': 'full source inventory (all sheets in scope)', 'sha256': payload['full_inventory_sha256']},
                               {'label': 'scope digest read by the scope reader', 'sha256': payload['digest_sha256']}]}


def load_inputs(full_raw, decision_raw, route):
    full = strict(route, full_raw, 'full inventory')
    if serialize(full) != full_raw:
        raise Refused('FULL_INVENTORY_LAYOUT', 'the full inventory is not in the builders\' one-record-per-line serialization')
    try:
        route.Inventory(full_raw)
    except (route.Rejected, KeyError, TypeError, ValueError) as e:
        raise Refused('FULL_INVENTORY_REJECTED_BY_ROUTE', repr(e)[:300])
    used, viewed = {c['sheet_index'] for c in full['cells']}, {v['sheet'] for v in full['views']}
    if not all(s['in_scope'] or (s['rows'] * s['columns'] == 0 and s['index'] not in used and s['name'] not in viewed)
               for s in full['sheets']):       # an empty sheet is out of scope as the builders write it (BUGFIX_EMPTY_SHEETS.md)
        raise Refused('FULL_INVENTORY_REQUIRED')
    if any(f['ref'] == route.SCOPE_REF for f in full['context_facts']):
        raise Refused('ALREADY_SCOPED')
    decision = strict(route, decision_raw, 'decision')
    if not isinstance(decision, dict) or decision.get('schema') != 'cps.scope-decision.v1' or decision.get('status') != 'FROZEN_AGREED':
        raise Refused('DECISION_NOT_FROZEN_AGREED')
    fact = decision['scope_fact']
    if decision['full_inventory_sha256'] != sha(full_raw) or fact['full_inventory_sha256'] != sha(full_raw):
        raise Refused('FULL_INVENTORY_SHA256_MISMATCH', 'the decision was made on another inventory')
    if [(s['index'], s['name'], s['visibility'], s['rows'], s['columns']) for s in fact['sheets']] != \
            [(s['index'], s['name'], s['visibility'], s['rows'], s['columns']) for s in full['sheets']]:
        raise Refused('DECISION_SHEETS_MISMATCH')
    if not any(s['in_scope'] for s in fact['sheets']):
        raise Refused('NO_SHEET_IN_SCOPE')
    return full, decision, fact


def project(full, decision, decision_sha, route):
    flags = {s['index']: s['in_scope'] for s in decision['scope_fact']['sheets']}
    names_in = {s['name'] for s in full['sheets'] if flags[s['index']]}
    kept_views = [v for v in full['views'] if v['sheet'] in names_in]
    vmap = {v['id']: i + 1 for i, v in enumerate(kept_views)}
    out = {}
    for k, v in full.items():
        if k == 'sheets':
            out[k] = [dict(s, in_scope=flags[s['index']]) for s in v]
        elif k == 'views':
            out[k] = [dict(x, id=vmap[x['id']]) for x in kept_views]
        elif k == 'source':
            src = json.loads(dump(v))
            src['carrier_source']['views'] = [dict(x, id=vmap[x['id']]) for x in v['carrier_source']['views'] if x['sheet'] in names_in]
            out[k] = src
        elif k == 'cells':
            out[k] = [c if all(vmap[x] == x for x in c['views']) else dict(c, views=[vmap[x] for x in c['views']])
                      for c in v if flags[c['sheet_index']]]
        elif k == 'context_facts':
            out[k] = list(v) + [fact_record(decision, decision_sha, route)]
        else:
            out[k] = v
    return out, vmap


def verify(full_raw, decision_raw, scoped_raw, route, expect_scoped=None):
    """Independent record-by-record comparison. Returns (ok, report)."""
    problems, stats = [], {}
    if expect_scoped is not None and sha(scoped_raw) != expect_scoped:
        problems.append('the scoped inventory sha256 differs from the pinned value')
    full, decision, fact = load_inputs(full_raw, decision_raw, route)
    scoped = strict(route, scoped_raw, 'scoped inventory')
    if serialize(scoped) != scoped_raw:
        problems.append('scoped inventory is not in the builders\' serialization')
    if list(scoped) != list(full):
        problems.append('top-level members differ')
    for k in full:
        if k not in ('sheets', 'views', 'cells', 'context_facts', 'source') and dump(full[k]) != dump(scoped.get(k)):
            problems.append(f'top-level member {k} differs')
    flags = {s['index']: s['in_scope'] for s in fact['sheets']}
    # sheets: only in_scope differs, and it equals the decision
    fs, ss = full['sheets'], scoped.get('sheets', [])
    if len(fs) != len(ss):
        problems.append('sheet count differs')
    sheet_flag_changes = 0
    for a, b in zip(fs, ss):
        if dump({k: v for k, v in a.items() if k != 'in_scope'}) != dump({k: v for k, v in b.items() if k != 'in_scope'}) or list(a) != list(b):
            problems.append(f"sheet {a['index']} differs outside in_scope")
        if b.get('in_scope') is not flags.get(a['index']):
            problems.append(f"sheet {a['index']} in_scope differs from the decision")
        sheet_flag_changes += a['in_scope'] != b.get('in_scope')
    names_in = {s['name'] for s in fs if flags.get(s['index'])}
    # views: kept = in-scope sheets in order, ids 1..n, otherwise identical
    exp_views = [v for v in full['views'] if v['sheet'] in names_in]
    vmap = {}
    sv = scoped.get('views', [])
    if len(sv) != len(exp_views):
        problems.append('view count differs from the in-scope views of the full inventory')
    for i, (a, b) in enumerate(zip(exp_views, sv)):
        vmap[a['id']] = b.get('id')
        if b.get('id') != i + 1 or list(a) != list(b) or dump({k: v for k, v in a.items() if k != 'id'}) != dump({k: v for k, v in b.items() if k != 'id'}):
            problems.append(f"view {a['id']} is not the renumbered full view")
    srcf, srcs = full['source'], scoped.get('source', {})
    if dump({k: v for k, v in srcf.items() if k != 'carrier_source'}) != dump({k: v for k, v in srcs.items() if k != 'carrier_source'}):
        problems.append('source differs outside carrier_source')
    csf, css = srcf['carrier_source'], srcs.get('carrier_source', {})
    if dump({k: v for k, v in csf.items() if k != 'views'}) != dump({k: v for k, v in css.items() if k != 'views'}):
        problems.append('carrier_source differs outside views')
    if css.get('views') != [{'id': v['id'], 'sheet': v['sheet'], 'range': v['range']} for v in sv]:
        problems.append('carrier_source.views differs from the scoped views')
    # cells
    fc = [c for c in full['cells']]
    exp_cells = [c for c in fc if flags.get(c['sheet_index'])]
    sc = scoped.get('cells', [])
    identical = remapped = 0
    if len(sc) != len(exp_cells):
        problems.append('cell count differs from the in-scope cells of the full inventory')
    for a, b in zip(exp_cells, sc):
        if dump(a) == dump(b):
            identical += 1
            if any(vmap.get(x) != x for x in a['views']):
                problems.append(f"cell {a['ref']} keeps view ids that were renumbered")
            continue
        if list(a) != list(b) or dump({k: v for k, v in a.items() if k != 'views'}) != dump({k: v for k, v in b.items() if k != 'views'}) \
                or b.get('views') != [vmap.get(x) for x in a['views']]:
            problems.append(f"cell {a['ref']} differs beyond the view renumbering")
        else:
            remapped += 1
    removed_cells = len(fc) - len(exp_cells)
    if any(not flags.get(c['sheet_index']) for c in sc):
        problems.append('a cell of an out-of-scope sheet is present')
    # context facts
    ff, sf = full['context_facts'], scoped.get('context_facts', [])
    if [dump(x) for x in ff] != [dump(x) for x in sf[:-1]] or len(sf) != len(ff) + 1:
        problems.append('existing context facts differ or the scope fact is not the single appended fact')
    want = fact_record(decision, sha(decision_raw), route)
    if not sf or dump(sf[-1]) != dump(want):
        problems.append('the appended context:scope differs from the decision payload')
    # census invariant and route acceptance
    if sum(s['rows'] * s['columns'] for s in ss if s.get('in_scope')) != len(sc):
        problems.append('census invariant fails')
    try:
        inv = route.Inventory(scoped_raw)
        rep = route.check_inventory(inv)
        route_result = {'status': 'PASS' if not rep.violations else 'REJECTED', 'route': route.VERSION, 'scope': route.scope_state(inv),
                        'policy_checks': route.policy_state(inv), 'violations': sorted({v['code'] for v in rep.violations}),
                        'warnings': sorted({w['code'] for w in rep.warnings})}
    except (route.Rejected, KeyError, TypeError, ValueError) as e:
        route_result = {'status': 'INVENTORY_REJECTED', 'error': repr(e)[:200]}
        problems.append('the route rejects the scoped inventory')
    stats = {'sheets': len(fs), 'sheet_in_scope_flags_changed': sheet_flag_changes,
             'views_full': len(full['views']), 'views_kept': len(sv), 'views_removed': len(full['views']) - len(exp_views),
             'views_renumbered': sum(1 for k, v in vmap.items() if k != v),
             'cells_full': len(fc), 'cells_kept_byte_identical': identical, 'cells_kept_views_renumbered_only': remapped,
             'cells_removed': removed_cells, 'context_facts_unchanged': len(ff), 'context_facts_appended': len(sf) - len(ff),
             'content_cells_scoped': sum(1 for c in sc if route.Inventory.has_content(c)),
             'content_cells_full': sum(1 for c in fc if route.Inventory.has_content(c))}
    report = {'status': 'PASS' if not problems else 'FAIL', 'problems': problems[:50], 'problem_count': len(problems),
              'full_inventory_sha256': sha(full_raw), 'scoped_inventory_sha256': sha(scoped_raw), 'decision_sha256': sha(decision_raw),
              'view_id_map': {str(k): v for k, v in vmap.items()}, 'stats': stats, 'route_check_inventory': route_result}
    return not problems, report


def build(full_path, decision_path, out_dir, views_dir, route):
    full_raw, decision_raw = full_path.read_bytes(), decision_path.read_bytes()
    full, decision, fact = load_inputs(full_raw, decision_raw, route)
    scoped, vmap = project(full, decision, sha(decision_raw), route)
    scoped_raw = serialize(scoped)
    ok, report = verify(full_raw, decision_raw, scoped_raw, route)
    if not ok:
        raise Refused('SELF_VERIFICATION_FAILED', report['problems'][:10])
    images = []
    for v in scoped['views']:
        img = v.get('image') or {}
        p = views_dir / img.get('file', '')
        images.append((p, img))
    present = [p.is_file() for p, _ in images]
    if any(present) and not all(present):
        raise Refused('VIEW_IMAGES_INCOMPLETE', {'missing': [img.get('file') for (p, img), ok_ in zip(images, present) if not ok_]})
    copied = []
    if all(present) and images:
        for p, img in images:
            b = p.read_bytes()
            if len(b) != img.get('bytes') or sha(b) != img.get('sha256'):
                raise Refused('VIEW_IMAGE_PIN_MISMATCH', img.get('file'))
            copied.append(img['file'])
    out_dir.mkdir(parents=True)
    with open(out_dir / 'SOURCE_INVENTORY.json', 'xb') as f:
        f.write(scoped_raw)
    for p, img in images if copied else []:
        shutil.copyfile(p, out_dir / img['file'])
    receipt = {'schema': RECEIPT_SCHEMA, 'tool_sha256': sha(Path(__file__).read_bytes()), 'route': route.VERSION,
               'route_sha256': sha(ROUTE.read_bytes()), 'case_id': full['case_id'],
               'full_inventory_sha256': sha(full_raw), 'scoped_inventory_sha256': sha(scoped_raw), 'decision_sha256': sha(decision_raw),
               'decision_admissible': decision.get('admissible'), 'view_id_map': report['view_id_map'],
               'view_images': {'copied': copied} if copied else {'copied': [], 'note': 'no view images next to the full inventory (image pins not bound); none copied'},
               'verify': {k: report[k] for k in ('status', 'problem_count', 'stats')}, 'route_check_inventory': report['route_check_inventory']}
    with open(out_dir / 'SCOPED_INVENTORY_RECEIPT.json', 'x', encoding='utf-8') as f:
        f.write(json.dumps(receipt, ensure_ascii=False, indent=1) + '\n')
    return receipt


def main(argv=None):
    ap = argparse.ArgumentParser(description='Scope stage step 4 (R59): build or verify the scoped inventory.')
    ap.add_argument('--full', required=True, type=Path)
    ap.add_argument('--decision', required=True, type=Path)
    ap.add_argument('--out-dir', type=Path)
    ap.add_argument('--views-dir', type=Path)
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--scoped', type=Path)
    ap.add_argument('--expect-scoped-sha256')
    a = ap.parse_args(argv)
    route = load_route()
    try:
        paths = [a.full, a.decision] + [p for p in (a.out_dir, a.views_dir, a.scoped) if p is not None]
        if not all(p.is_absolute() for p in paths):
            raise Refused('ABSOLUTE_PATH_REQUIRED')
        if a.verify:
            if a.scoped is None or a.out_dir is not None:
                raise Refused('USAGE', '--verify needs --scoped and no --out-dir')
            ok, report = verify(a.full.read_bytes(), a.decision.read_bytes(), a.scoped.read_bytes(), route, a.expect_scoped_sha256)
            print(json.dumps(report, ensure_ascii=False))
            return 0 if ok else 2
        if a.out_dir is None or a.scoped is not None:
            raise Refused('USAGE', 'build needs --out-dir and no --scoped')
        if a.out_dir.exists():
            raise Refused('OUTPUT_EXISTS')
        receipt = build(a.full, a.decision, a.out_dir, a.views_dir or a.full.parent, route)
    except Refused as e:
        sys.stderr.write(json.dumps({'status': 'REFUSED', 'code': e.code, 'detail': e.detail}, ensure_ascii=False) + '\n')
        return 1
    print(json.dumps({'status': 'WRITTEN', 'case_id': receipt['case_id'], 'full_inventory_sha256': receipt['full_inventory_sha256'],
                      'scoped_inventory_sha256': receipt['scoped_inventory_sha256'], 'decision_sha256': receipt['decision_sha256'],
                      'decision_admissible': receipt['decision_admissible'], 'verify': receipt['verify']['status'],
                      'stats': receipt['verify']['stats'], 'route_check_inventory': receipt['route_check_inventory'],
                      'values_printed': False}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
