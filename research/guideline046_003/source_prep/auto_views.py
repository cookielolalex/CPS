"""Automatic reconstructed-view layout for v2 inventories (source preparation).

Groups each in-scope sheet's content columns into clusters (a gap of more than 6 empty columns
starts a new cluster) and splits each cluster into chunks of at most 30 rows from row 1 to the
cluster's last content row. Every content cell therefore lies in at least one view.
"""


def letters(n):
    s = ''
    while n:
        n, k = divmod(n - 1, 26)
        s = chr(65 + k) + s
    return s


def has_content(c):
    if c['state'] in ('error', 'missing_cache', 'unresolved'):
        return True
    if c['state'] in ('literal', 'cached_formula'):
        return c['saved_value'] is not None and c['saved_value'] != ''
    return c['state'] == 'covered' and bool(c['conflicts'])


def auto_views(sheets, cells, max_rows=30, gap=6):
    views = []
    for s in sheets:
        if not s['in_scope']:
            continue
        cc = [c for c in cells if c['sheet'] == s['name'] and has_content(c)]
        if not cc:
            continue
        cols = sorted({c['col'] for c in cc})
        clusters, start, prev = [], cols[0], cols[0]
        for col in cols[1:]:
            if col - prev > gap + 1:
                clusters.append((start, prev))
                start = col
            prev = col
        clusters.append((start, prev))
        for c0, c1 in clusters:
            c0 = 1 if c0 <= gap + 1 else c0
            last = max(c['row'] for c in cc if c0 <= c['col'] <= c1)
            for r0 in range(1, last + 1, max_rows):
                r1 = min(last, r0 + max_rows - 1)
                rng = f'{letters(c0)}{r0}:{letters(c1)}{r1}' if (c0, r0) != (c1, r1) else f'{letters(c0)}{r0}'
                views.append({'id': len(views) + 1, 'sheet': s['name'], 'range': rng})
    return views


def assign(cells, views):
    import re
    def a1(a):
        m = re.fullmatch(r'([A-Z]+)(\d+)', a)
        col = 0
        for ch in m[1]:
            col = col * 26 + ord(ch) - 64
        return col, int(m[2])
    vr = []
    for v in views:
        p = v['range'].split(':')
        vr.append((v['id'], v['sheet'], a1(p[0]), a1(p[-1])))
    for c in cells:
        c['views'] = [vid for vid, sh, (c0, r0), (c1, r1) in vr if sh == c['sheet'] and c0 <= c['col'] <= c1 and r0 <= c['row'] <= r1]
