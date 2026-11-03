"""Build a cps.source-inventory.cells.v2 packet from a pinned original XLSX (cached values).

Source-preparation role only. Reads the pinned original with the bundled openpyxl twice
(formulas and saved caches); never recalculates, never updates links, never executes
content. Writes SOURCE_INVENTORY.json + PACKET_SUMMARY.json into a new directory; views
are rendered separately (render_views.py). No values are printed.
Usage: python3 -I -S -B build_inventory_xlsx_v2.py --bundle DIR --config CASE.json --out NEWDIR
CASE.json: case_id, family_id, original{bundle_path,bytes,sha256}, carrier_path, views[{id,sheet,range}],
adoption_status, adoption_basis, context_facts.
"""
import argparse, datetime, hashlib, json, math, sys
from decimal import Decimal
from pathlib import Path

PROFILE = 'cached-cell-raw-scalar-text.v2'
CTRL = set(range(0, 9)) | {11, 12} | set(range(14, 32))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def letters(n):
    s = ''
    while n:
        n, k = divmod(n - 1, 26)
        s = chr(65 + k) + s
    return s


def a1(a):
    i = 0
    while a[i].isalpha():
        i += 1
    col = 0
    for ch in a[:i]:
        col = col * 26 + ord(ch) - 64
    return col, int(a[i:])


def canonical_number(v):
    f = float(v)
    if not math.isfinite(f):
        return None
    s = format(Decimal(repr(f)), 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def serialize(inv):
    def dump(x):
        return json.dumps(x, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    parts = []
    for k, v in inv.items():
        if k in ('cells', 'sheets', 'views', 'context_facts', 'limitations') and isinstance(v, list):
            body = ',\n'.join('  ' + dump(x) for x in v)
            parts.append(f' {dump(k)}:[\n{body}\n ]' if v else f' {dump(k)}:[]')
        else:
            parts.append(f' {dump(k)}:{dump(v)}')
    return '{\n' + ',\n'.join(parts) + '\n}\n'


def classify(fcell, vcell):
    """Return (saved_type, state, saved_value, formula_flag, formula_text)."""
    is_formula = fcell.data_type == 'f'
    ftext = None
    if is_formula:
        ftext = fcell.value if isinstance(fcell.value, str) else getattr(fcell.value, 'text', str(fcell.value))
    val = vcell.value if is_formula else fcell.value
    dt = vcell.data_type if is_formula else fcell.data_type
    if is_formula and val is None:
        return 'empty', 'missing_cache', None, True, ftext
    if val is None:
        return 'empty', 'true_blank', None, False, None
    if dt == 'e':
        return 'error', 'error', str(val), is_formula, ftext
    if isinstance(val, bool):
        return 'boolean', ('cached_formula' if is_formula else 'literal'), val, is_formula, ftext
    if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
        return 'date', ('cached_formula' if is_formula else 'literal'), val.isoformat(), is_formula, ftext
    if isinstance(val, (int, float)):
        return 'number', ('cached_formula' if is_formula else 'literal'), float(val) if isinstance(val, float) else val, is_formula, ftext
    if isinstance(val, str):
        if val == '':
            return 'text', 'explicit_empty', '', is_formula, ftext
        return 'text', ('cached_formula' if is_formula else 'literal'), val, is_formula, ftext
    return 'text', 'unresolved', str(val), is_formula, ftext


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bundle', required=True, type=Path)
    ap.add_argument('--config', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    root = a.bundle.resolve(strict=True)
    cfg = json.loads(a.config.read_text(encoding='utf-8'))
    p = (root / cfg['original']['bundle_path']).resolve()
    assert p.is_relative_to(root)
    data = p.read_bytes()
    if len(data) != cfg['original']['bytes'] or sha(data) != cfg['original']['sha256']:
        raise SystemExit('PIN_MISMATCH')
    dep = (root / 'private/deps').resolve()
    sys.path.insert(0, str(dep))
    import openpyxl
    assert Path(openpyxl.__file__).resolve().is_relative_to(dep / 'openpyxl') and openpyxl.__version__ == '3.1.5'
    wf = openpyxl.load_workbook(p, data_only=False, keep_links=False)
    wv = openpyxl.load_workbook(p, data_only=True, keep_links=False)
    views = [{'id': v['id'], 'sheet': v['sheet'], 'range': v['range']} for v in cfg['views']]
    vr = [(v['id'], v['sheet'], (a1(v['range'].split(':')[0]), a1(v['range'].split(':')[-1]))) for v in views]
    sheets, cells = [], []
    state_map = {'visible': 'visible', 'hidden': 'hidden', 'veryHidden': 'very_hidden'}
    for si, ws in enumerate(wf.worksheets, start=1):
        wsv = wv[ws.title]
        rows, cols = ws.max_row, ws.max_column
        if rows == 1 and cols == 1 and ws.cell(1, 1).value is None:
            rows = cols = 0
        covered = {}
        merges = []
        for mr in ws.merged_cells.ranges:
            merges.append(str(mr))
            anchor = f'cell:S{si}!{letters(mr.min_col)}{mr.min_row}'
            for r in range(mr.min_row, mr.max_row + 1):
                for c in range(mr.min_col, mr.max_col + 1):
                    if (r, c) != (mr.min_row, mr.min_col):
                        covered[(r, c)] = anchor
        nform = 0
        for r in range(1, rows + 1):
            for c in range(1, cols + 1):
                fcell, vcell = ws.cell(r, c), wsv.cell(r, c)
                stype, state, val, frm, ftext = classify(fcell, vcell)
                nform += int(frm)
                addr = f'{letters(c)}{r}'
                anchor = covered.get((r, c))
                conflicts, canonical, usable, reason = [], None, False, None
                if anchor is not None:
                    if val not in (None, ''):
                        conflicts.append('covered merge position holds saved content')
                    state, reason = 'covered', 'covered merge position; use the merge anchor'
                elif state == 'true_blank':
                    reason = 'empty cell has no raw text'
                elif state == 'explicit_empty':
                    reason = 'explicit empty string has no raw text'
                elif state in ('error', 'missing_cache', 'unresolved'):
                    reason = f'{state} is not raw text'
                elif stype == 'text':
                    if any(ord(ch) in CTRL for ch in val):
                        reason = 'text contains control characters the admitted writer cannot carry'
                    else:
                        canonical, usable = val, True
                elif stype == 'number':
                    canonical = canonical_number(val)
                    usable = canonical is not None
                    reason = None if usable else 'nonfinite number'
                elif stype == 'date':
                    reason = 'date-typed value; display format is not reproduced by this profile'
                elif stype == 'boolean':
                    reason = 'boolean saved value is not material raw text in this profile'
                cv = [vid for vid, sh, ((c0, r0), (c1, r1)) in vr if sh == ws.title and c0 <= c <= c1 and r0 <= r <= r1]
                cells.append({'ref': f'cell:S{si}!{addr}', 'sheet_index': si, 'sheet': ws.title, 'address': addr, 'row': r, 'col': c,
                              'saved_type': stype, 'state': state, 'saved_value': val, 'native_literal': None,
                              'formula_record_present': frm, 'formula': ftext, 'merge_anchor_ref': anchor, 'conflicts': conflicts,
                              'canonical_raw': canonical, 'usable_for_raw': usable, 'raw_limit_reason': reason, 'views': cv})
        sheets.append({'index': si, 'name': ws.title, 'visibility': state_map.get(ws.sheet_state, ws.sheet_state), 'rows': rows,
                       'columns': cols, 'merges': merges, 'formula_records': nform, 'in_scope': rows * cols > 0})
    inv = {
        'schema': 'cps.source-inventory.cells.v2', 'case_id': cfg['case_id'], 'family_id': cfg['family_id'],
        'representation_profile': PROFILE,
        'source': {'source_id': 'S', 'format': 'cached_xlsx', 'bytes': len(data), 'sha256': sha(data),
                   'adoption_status': cfg['adoption_status'], 'adoption_basis': cfg['adoption_basis'],
                   'reader': {'name': 'openpyxl', 'version': openpyxl.__version__, 'biff_format': None, 'formula_expressions_available': True},
                   'carrier_source': {'kind': 'cached_xlsx', 'path': cfg['carrier_path'], 'sha256': sha(data), 'views': views}},
        'sheets': sheets,
        'views': [dict(v, image={'file': f"view_{v['id']:02d}.png", 'bytes': 1, 'sha256': '0' * 64}) for v in views],
        'external_links': [str(getattr(x, 'file_link', x)) for x in getattr(wf, '_external_links', [])],
        'cells': cells, 'context_facts': cfg['context_facts'],
        'limitations': [
            'XLSX saved caches read with openpyxl data_only=True; formulas read separately and never evaluated; links not updated.',
            'Numbers are the saved binary64 values; no native decimal literal is recorded (native_literal is null).',
            'openpyxl converts date-formatted numbers to dates; such cells are date-typed and unusable for raw text in this profile.',
            'Views are reconstructed inspection images of saved caches, not native Excel displays; image wrapping adds no characters.',
            'Source adoption, contract stage and version are unverified unless adoption_status says verified.'],
    }
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / 'SOURCE_INVENTORY.unbound.json').write_text(serialize(inv), encoding='utf-8')
    summary = {'case_id': cfg['case_id'], 'sheets': len(sheets), 'positions': len(cells),
               'content_states': {k: sum(1 for c in cells if c['state'] == k) for k in sorted({c['state'] for c in cells})},
               'formula_records': sum(s['formula_records'] for s in sheets), 'views': len(views), 'values_printed': False,
               'note': 'image pins are bound by render_views.py, which writes SOURCE_INVENTORY.json'}
    (a.out / 'PACKET_SUMMARY.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
