"""Build a cps.source-inventory.cells.v2 packet from a pinned original cached XLS.

Source-preparation role only. Reads the pinned original bytes, the archived BIFF helper
and the bundled xlrd from the extracted portable bundle; writes a new packet directory.
It never reads targets, expectations, prior outputs or evaluator files. No values are
printed. Usage (all paths explicit):
  python3 -I -S -B build_inventory_v2.py --bundle DIR --case 1140908 --config CASE.json --out NEWDIR
CASE.json supplies: case_id, family_id, original (bundle_path/bytes/sha256),
carrier_path (original Windows path, provenance only), views [{id,sheet,range,
bundle_path,bytes,sha256}], adoption_status, adoption_basis, context_facts.
"""
import argparse, hashlib, importlib.util, json, math, shutil, sys
from decimal import Decimal
from pathlib import Path

PROFILE = 'cached-cell-raw-scalar-text.v2'
TYPES = {0: 'empty', 1: 'text', 2: 'number', 3: 'date', 4: 'boolean', 5: 'error', 6: 'blank'}
CTRL = set(range(0, 9)) | {11, 12} | set(range(14, 32))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def letters(n):
    s = ''
    n += 1
    while n:
        n, k = divmod(n - 1, 26)
        s = chr(65 + k) + s
    return s


def pinned(root, pin):
    p = (root / pin['bundle_path']).resolve()
    if not p.is_relative_to(root):
        raise ValueError('BUNDLE_PATH_ESCAPE')
    b = p.read_bytes()
    if len(b) != pin['bytes'] or sha(b) != pin['sha256']:
        raise ValueError('PIN_MISMATCH:' + pin['bundle_path'])
    return p, b


def canonical_number(v):
    f = float(v)
    if not math.isfinite(f):
        return None
    s = format(Decimal(repr(f)), 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def in_range(r, c, rng):
    (lo_c, lo_r), (hi_c, hi_r) = rng
    return lo_c <= c <= hi_c and lo_r <= r <= hi_r


def parse_a1(a):
    i = 0
    while a[i].isalpha():
        i += 1
    col = 0
    for ch in a[:i]:
        col = col * 26 + ord(ch) - 64
    return col, int(a[i:])


def serialize(inv):
    """Readable but compact: top-level members pretty-printed, one cell/context per line."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bundle', required=True, type=Path)
    ap.add_argument('--config', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    root = a.bundle.resolve(strict=True)
    cfg = json.loads(a.config.read_text(encoding='utf-8'))
    sources = json.loads((root / 'private/PORTABLE_SOURCE_INPUTS.json').read_text(encoding='utf-8-sig'))
    helper, _ = pinned(root, sources['legacy_helper'])
    for pin in sources['xlrd_members']:
        pinned(root, pin)
    if 'path' in cfg['original']:
        data = Path(cfg['original']['path']).read_bytes()
        if len(data) != cfg['original']['bytes'] or sha(data) != cfg['original']['sha256']:
            raise ValueError('PIN_MISMATCH:original')
    else:
        _, data = pinned(root, cfg['original'])
    dep = (root / 'private/deps').resolve()
    sys.path.insert(0, str(dep))
    import xlrd
    assert xlrd.__version__ == '2.0.2' and Path(xlrd.__file__).resolve() == dep / 'xlrd/__init__.py'
    spec = importlib.util.spec_from_file_location('cps_archived_biff_reader', helper)
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    reader.load_xlrd = lambda: xlrd       # rebind dependency lookup only
    book, formulas, fmt = reader.parse_legacy(data)

    views = []
    a.out.mkdir(parents=True, exist_ok=False)
    auto = cfg['views'] == 'auto'
    for v in ([] if auto else cfg['views']):
        _, img = pinned(root, v)
        name = f"view_{v['id']:02d}.png"
        (a.out / name).write_bytes(img)
        views.append({'id': v['id'], 'sheet': v['sheet'], 'range': v['range'],
                      'image': {'file': name, 'bytes': len(img), 'sha256': sha(img)}})
    vranges = [(v['id'], v['sheet'], (parse_a1(v['range'].split(':')[0]), parse_a1(v['range'].split(':')[-1]))) for v in views]
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    sheets, cells = [], []
    vis = {0: 'visible', 1: 'hidden', 2: 'very_hidden'}
    for si, s in enumerate(book.sheets(), start=1):
        fset = {(r, c) for r, c, _ in formulas[si - 1]}
        merges = []
        covered = {}
        for rlo, rhi, clo, chi in s.merged_cells:
            merges.append(f'{letters(clo)}{rlo + 1}:{letters(chi - 1)}{rhi}')
            anchor = f'cell:S{si}!{letters(clo)}{rlo + 1}'
            for r in range(rlo, rhi):
                for c in range(clo, chi):
                    if (r, c) != (rlo, clo):
                        covered[(r, c)] = anchor
        in_scope = s.nrows * s.ncols > 0
        sheets.append({'index': si, 'name': s.name, 'visibility': vis.get(s.visibility, str(s.visibility)),
                       'rows': s.nrows, 'columns': s.ncols, 'merges': merges, 'formula_records': len(fset),
                       'in_scope': in_scope})
        for r in range(s.nrows):
            for c in range(s.ncols):
                typ = s.cell_type(r, c)
                val = None if typ in (0, 6) else s.cell_value(r, c)
                addr = f'{letters(c)}{r + 1}'
                ref = f'cell:S{si}!{addr}'
                frm = (r, c) in fset
                stype = TYPES[typ]
                conflicts, anchor = [], covered.get((r, c))
                canonical, usable, reason = None, False, None
                if anchor is not None:
                    state = 'covered'
                    if val not in (None, ''):
                        conflicts.append('covered merge position holds saved content')
                    reason = 'covered merge position; use the merge anchor'
                elif typ in (0, 6):
                    state, reason = 'true_blank', 'empty cell has no raw text'
                elif typ == 1 and val == '':
                    state, reason = 'explicit_empty', 'explicit empty string has no raw text'
                elif typ == 5:
                    state, reason = 'error', 'saved error value is not raw text'
                    val = xlrd.error_text_from_code.get(val, f'#ERR{val}')
                else:
                    state = 'cached_formula' if frm else 'literal'
                    if typ == 1:
                        if any(ord(ch) in CTRL for ch in val):
                            reason = 'text contains control characters the admitted writer cannot carry'
                        else:
                            canonical, usable = val, True
                    elif typ == 2:
                        canonical = canonical_number(val)
                        usable = canonical is not None
                        reason = None if usable else 'nonfinite number'
                    elif typ == 3:
                        reason = 'date-typed serial; display format is not reproduced by this profile'
                    elif typ == 4:
                        val = bool(val)
                        reason = 'boolean saved value is not material raw text in this profile'
                cv = [vid for vid, sh, rng in vranges if sh == s.name and in_range(r + 1, c + 1, rng)]
                cells.append({'ref': ref, 'sheet_index': si, 'sheet': s.name, 'address': addr, 'row': r + 1,
                              'col': c + 1, 'saved_type': stype, 'state': state, 'saved_value': val,
                              'native_literal': None, 'formula_record_present': frm, 'formula': None,
                              'merge_anchor_ref': anchor, 'conflicts': conflicts, 'canonical_raw': canonical,
                              'usable_for_raw': usable, 'raw_limit_reason': reason, 'views': cv})
    book.release_resources()
    if auto:
        import auto_views
        views = [dict(v, image={'file': f"view_{v['id']:02d}.png", 'bytes': 1, 'sha256': '0' * 64}) for v in auto_views.auto_views(sheets, cells)]
        auto_views.assign(cells, views)
    inv = {
        'schema': 'cps.source-inventory.cells.v2', 'case_id': cfg['case_id'], 'family_id': cfg['family_id'],
        'representation_profile': PROFILE,
        'source': {'source_id': 'S', 'format': 'cached_xls', 'bytes': len(data), 'sha256': sha(data),
                   'adoption_status': cfg['adoption_status'], 'adoption_basis': cfg['adoption_basis'],
                   'reader': {'name': 'xlrd', 'version': xlrd.__version__, 'biff_format': fmt.get('format') if isinstance(fmt, dict) else str(fmt),
                              'formula_expressions_available': False},
                   'carrier_source': {'kind': 'cached_xls', 'path': cfg['carrier_path'], 'sha256': sha(data),
                                      'views': [{k: v[k] for k in ('id', 'sheet', 'range')} for v in views]}},
        'sheets': sheets, 'views': views, 'external_links': [],
        'cells': cells, 'context_facts': cfg['context_facts'],
        'limitations': [
            'Legacy BIFF reader exposes saved caches and formula-record flags only; formula expressions are not decompiled (formula is null).',
            'BIFF stores binary64 numbers; no native decimal literal is available (native_literal is null).',
            'External-link records are not decoded by this reader; external_links lists none observed, which is a reader limitation, not proof of absence.',
            'Views are reconstructed inspection images of saved caches, not native Excel displays; image wrapping adds no characters.',
            'Source adoption, contract stage and version are unverified unless adoption_status says verified.'],
    }
    raw = serialize(inv).encode('utf-8')
    (a.out / ('SOURCE_INVENTORY.unbound.json' if auto else 'SOURCE_INVENTORY.json')).write_bytes(raw)
    summary = {'case_id': cfg['case_id'], 'inventory_sha256': sha(raw), 'inventory_bytes': len(raw),
               'sheets': len(sheets), 'positions': len(cells),
               'content_states': {k: sum(1 for c in cells if c['state'] == k) for k in sorted({c['state'] for c in cells})},
               'views': len(views), 'formula_records': sum(s['formula_records'] for s in sheets),
               'values_printed': False}
    (a.out / 'PACKET_SUMMARY.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
