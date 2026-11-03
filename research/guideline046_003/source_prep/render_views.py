"""Render reconstructed inspection views from a v2 inventory and bind their PNG pins.

Reads <packet>/SOURCE_INVENTORY.unbound.json, writes view_NN.html/png and the final
SOURCE_INVENTORY.json (identical except views[].image pins). Views show saved caches only:
canonical text for usable cells, a bracketed type tag otherwise. Inspection aid, not authority.
Usage: python3 -I -B render_views.py --packet DIR
"""
import argparse, hashlib, html, json, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


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


def shown(c):
    if c['canonical_raw'] is not None:
        return c['canonical_raw']
    if c['state'] in ('true_blank', 'explicit_empty') or (c['state'] == 'covered' and not c['conflicts']):
        return ''
    return f"[{c['saved_type']}:{c['state']}] {'' if c['saved_value'] is None else c['saved_value']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--packet', required=True, type=Path)
    a = ap.parse_args()
    pk = a.packet.resolve()
    raw = (pk / 'SOURCE_INVENTORY.unbound.json').read_text(encoding='utf-8')
    inv = json.loads(raw)
    cells = {(c['sheet'], c['row'], c['col']): c for c in inv['cells']}
    merges = {}
    for s in inv['sheets']:
        for m in s['merges']:
            (c0, r0), (c1, r1) = a1(m.split(':')[0]), a1(m.split(':')[-1])
            merges[(s['name'], r0, c0)] = (r1 - r0 + 1, c1 - c0 + 1)
    names = []
    for v in inv['views']:
        (c0, r0), (c1, r1) = a1(v['range'].split(':')[0]), a1(v['range'].split(':')[-1])
        rows = []
        head = ''.join(f'<th>{letters(c)}</th>' for c in range(c0, c1 + 1))
        for r in range(r0, r1 + 1):
            tds = []
            for c in range(c0, c1 + 1):
                cell = cells.get((v['sheet'], r, c))
                if cell is None:
                    tds.append('<td></td>')
                    continue
                if cell['state'] == 'covered' and not cell['conflicts']:
                    anc = cell['merge_anchor_ref']
                    # skip if the anchor is inside this view (spanned); else render an empty covered marker
                    ar = anc.split('!')[1]
                    ac, arow = a1(ar)
                    if c0 <= ac <= c1 and r0 <= arow <= r1:
                        continue
                    tds.append('<td class="cov"></td>')
                    continue
                span = merges.get((v['sheet'], r, c))
                attrs = ''
                if span:
                    rs = min(span[0], r1 - r + 1)
                    cs = min(span[1], c1 - c + 1)
                    attrs = f' rowspan="{rs}" colspan="{cs}"'
                tds.append(f'<td{attrs}>{html.escape(shown(cell))}</td>')
            rows.append(f'<tr><th>{r}</th>{"".join(tds)}</tr>')
        doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:8px;font-family:'WenQuanYi Zen Hei',sans-serif;font-size:13px;background:#fff;color:#111}}
h1{{font-size:13px;margin:0 0 6px}} table{{border-collapse:collapse}}
th{{background:#e9eef3;font-weight:normal;color:#334;padding:2px 4px;border:1px solid #9aa}}
td{{border:1px solid #9aa;padding:2px 4px;vertical-align:top;white-space:pre-wrap;max-width:360px}}
td.cov{{background:#f4f4f4}}</style></head><body>
<h1>Reconstructed saved-cache view {v['id']}: {html.escape(v['sheet'])} {v['range']} (inspection aid; inventory is authoritative)</h1>
<table><tr><th></th>{head}</tr>{''.join(rows)}</table></body></html>"""
        name = f"view_{v['id']:02d}.html"
        (pk / name).write_text(doc, encoding='utf-8')
        names.append(name)
    subprocess.run(['node', str(HERE / 'screenshot_views.cjs'), str(pk), *names], check=True)
    for v in inv['views']:
        b = (pk / f"view_{v['id']:02d}.png").read_bytes()
        v['image'] = {'file': f"view_{v['id']:02d}.png", 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
    # rewrite only the views line block, keeping the builder's serialization
    import importlib.util
    spec = importlib.util.spec_from_file_location('bx', HERE / 'build_inventory_xlsx_v2.py')
    bx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bx)
    out = bx.serialize(inv)
    (pk / 'SOURCE_INVENTORY.json').write_text(out, encoding='utf-8')
    for n in names:
        (pk / n).unlink()
    print(json.dumps({'views': len(inv['views']), 'inventory_sha256': hashlib.sha256(out.encode('utf-8')).hexdigest()}))


if __name__ == '__main__':
    main()
