"""Scope stage, step 1 (candidate 046g, FIELD_ROLES R59): deterministic scope proposal and scope digest.

Source-preparation role only. Reads one FULL source inventory (every sheet in scope, as the builders write it) and the
package's FIELD_ROLES.md (to excerpt R47b and R49-R51 for the scope reader). It never reads targets, outputs, evaluator
files or anything else, and it prints hashes, indexes, roles and counts only, never cell text or sheet names.

Empty sheets (v3, BUGFIX_EMPTY_SHEETS.md). The builders write a sheet with rows x columns = 0 as in_scope false, so a
full inventory has every NON-EMPTY sheet in scope. A sheet that is out of scope is accepted only when it is empty: rows x
columns = 0 and no cell or view on it. Any other out-of-scope sheet still refuses the inventory (FULL_INVENTORY_REQUIRED,
an already-scoped inventory). An empty sheet keeps role other and in_scope false in the proposal (whether or not the
stage applies), with its own reason, and gets no flag; it is listed in the digest like any other sheet. Every computed
value of the other sheets is the one the same workbook gives without the empty sheets.

Usage: python3 -I -B scope_tool.py --inventory /abs/FULL/SOURCE_INVENTORY.json --out-dir /abs/NEW_SCOPE_DIR

Writes into the new directory:
  SCOPE_PROPOSAL.json      cps.scope-proposal.v1: threshold, BILL1 result, R51 conditions, per-sheet role, in_scope flag
                           and reason, tool flags, hashes. Status PROPOSED, NOT_APPLIED or HOLD.
  SCOPE_DIGEST.json        cps.scope-digest.v1 (only when the stage applies): the excerpt the scope reader sees.
  SCOPE_RULES_EXCERPT.md   R47b and R49-R51 copied verbatim from the package FIELD_ROLES.md (only when the stage applies).
Exit 0: PROPOSED or NOT_APPLIED. Exit 4: HOLD (written; the case goes to the owner). Exit 1: refused, nothing written.

Threshold (R59). The stage applies when the full inventory has more than 2,500 content cells that are literal or
cached-formula cells with a saved value that is not null and not "". Below that every non-empty sheet stays in scope
and no context:scope is written (status NOT_APPLIED), exactly as in 046f.

BILL1.v1 (from the 046f structure study, as the study spells it). Every sheet is considered, hidden ones included. Cell
text is normalised by removing every whitespace character (str.isspace, which includes U+3000); only text cells
(saved_type text, literal or cached formula) are header or total text. A sheet is a candidate when
  (a) exactly one row has text cells equal to all of: 項次; a name word (項目及說明, 名稱, 品名 or 材料名稱); 單位; 數量;
      單價; and 複價 or 金額 (no other row on the sheet has this header set);
  (b) below that row, a cell in a price column has normalised text exactly 合計 or 總計; the first such row is the R49
      end row. The price columns are the header row's 單價 columns and its 複價 columns (its 金額 columns when the
      header row has no 複價, the amount label that (a) accepts);
  (c) at least one price-column cell strictly between the header row and the end row is a number above zero
      (saved_type number, literal or cached formula; booleans excluded).
Exactly one candidate is the bill sheet. Zero or several candidates: HOLD.

R51 conditions, computed on the full inventory (the route cannot see scoped-out cells):
  Lines. The quoted range runs from the first item-like row below the bill header to the row before the end row. A row
  is item-like when its name cell has content and its quantity cell has content or its unit cell (normalised) is
  neither empty nor 全. A later row with no item number that is not item-like and not priced continues the line (its
  name text is appended unless it holds 小計 or 合計). A line is priced when its unit-price or amount cell holds a
  number above zero or text stating a positive amount (1,200元); not estimated when either contains 不含估價; it has
  other price text when either holds other nonblank text that is not a zero; otherwise it is unpriced with no status.
  Lines with other price text count as unpriced with no status for the R51 conditions and are flagged.
  Analysis blocks. On an analysis sheet (a row with 工料名稱 and at least one heading cell starting with 工作項目 that is
  not the bare word), a block runs from a heading row to the next heading row. Its name is the heading text after
  工作項目 and an optional colon, its code the text after the last colon of a heading-row cell containing 計價代碼, its
  reference the first content cell left of the heading. A block with neither name nor code is an empty frame.
  Links (R46: shared reference code or item name; plus outline path). A block links to an in-range line when its code
  (also without a leading M) equals a code token of the line (a run of 8+ characters of [0-9A-Za-z#] with 4+ digits,
  also without a leading M, from the line's non-name text cells), when its name equals the line's normalised text, or
  when its reference is an outline path (1.2.3) equal to the line's item number. A name-prefix match (both 8+
  characters) is reported as a flag only.
  An analysis sheet is in scope only when (i) every in-range line is unpriced with no status: R51 then takes the rows
  from the analysis blocks, and every analysis sheet is in scope. Otherwise every analysis sheet is out of scope. The
  first draft's condition (ii) (some unpriced, no-status in-range line has a linked block on the sheet) is dropped
  (046g pass 2): under R51 a block on a separate analysis sheet lies outside the quoted range (SYNTHETIC_ALLOCATION_CASES A26), so
  that line is excluded_supply and (ii) added census cells but never rows. The study's option (iii) (any linked block)
  is not adopted either: components under priced or not-estimated parents are not 未填 rows and are not scored, so on
  scoped packets they are not written (R59). Linked blocks on an out-of-scope sheet, whatever their parent's state, are
  counted per sheet as linked_analysis_blocks, which the route warns about (R59_LINKED_ANALYSIS_OUT_OF_SCOPE); the
  sheet's reason and the LINKED_BLOCKS_OUT_OF_SCOPE flag split them by parent state.
Roles: bill (the BILL1 sheet), resource_statistics (a row with 工項代碼, 人工, 機具 and 材料), analysis (above), summary
(a row with 項次, a name word, an amount word and no 單價), other. Summary, resource-statistics and other sheets are out
of scope; an analysis sheet is in scope only under (i).
"""
import argparse, hashlib, importlib.util, json, re, sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PKG = HERE.parent / 'package'
ROUTE = PKG / 'tools' / 'cps046b_route.py'
FIELD_ROLES = PKG / 'resources' / 'FIELD_ROLES.md'
TOOL_VERSION = 'cps046g-scope-tool.v3'      # v2 (046g pass 2): R51 condition (ii) dropped; v3 (2026-11-13): empty sheets
PROPOSAL_SCHEMA = 'cps.scope-proposal.v1'
DIGEST_SCHEMA = 'cps.scope-digest.v1'
NAME_WORDS = ('項目及說明', '名稱', '品名', '材料名稱')
TOTAL_WORDS = ('合計', '總計')
SUMMARY_NAME_WORDS = ('項目及說明', '工作項目', '名稱', '品名', '項目', '材料名稱')
SUMMARY_AMOUNT_WORDS = ('複價', '金額', '金額(元)', '總價')
RESOURCE_WORDS = ('工項代碼', '人工', '機具', '材料')
STATUS_TEXT = '不含估價'
CODE_RE = re.compile(r'[0-9A-Za-z#]{8,}', re.ASCII)
PATH_RE = re.compile(r'[0-9]+(?:\.[0-9]+)+', re.ASCII)
POSITIVE_TEXT_RE = re.compile(r'[$＄]?([0-9][0-9,]*(?:\.[0-9]+)?)元?')
ZERO_TEXT_RE = re.compile(r'[+-]?0+(?:\.0+)?', re.ASCII)
# digest: generic header vocabulary used only to find each sheet's first header row (>= 4 categories on one row)
VOCAB = [('項次', r'項次[:：]?'), ('名稱', r'項目及說明|工作項目|工料名稱|工項名稱|名稱|品名|項目|材料名稱'), ('規格', r'規格'),
         ('單位', r'單位'), ('數量', r'數量|工程用量'), ('單價', r'單價'), ('複價', r'複價|金額|金額\(元\)|總價'),
         ('備註', r'備註|編碼\(備註\)'), ('廠牌', r'廠牌'), ('型號', r'型號'), ('工項代碼', r'工項代碼'), ('人工', r'人工'),
         ('機具', r'機具'), ('材料', r'材料'), ('雜項', r'雜項')]
VOCAB_RE = [(k, re.compile(p)) for k, p in VOCAB]
DIGEST_COLS = 10
REASONS = {
    'bill': 'bill: the single BILL1 candidate; rows come from this sheet (R49)',
    'analysis_i': 'analysis: every in-range bill line has no price and no status, so rows come from the analysis blocks (R51)',
    'analysis_out': ('analysis: not every in-range bill line has no price and no status, so R51 takes no rows from this sheet; '
                     'a separate analysis sheet lies outside the quoted range (R49, R51, A26)'),
    'summary': 'summary: never yields rows (R49)',
    'resource_statistics': 'resource statistics: source check only, never yields rows (guideline section 3)',
    'other': 'other: neither the bill sheet nor an analysis sheet that R51 needs; never yields rows (R49)',
    'empty': 'other: an empty sheet (rows x columns = 0, no cell), which the builders write out of scope; never yields rows (R49)',
}


class Refused(Exception):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_route():
    spec = importlib.util.spec_from_file_location('cps046g_route_for_scope_tool', ROUTE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def compact(x):
    return json.dumps(x, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def norm(s):
    return ''.join(ch for ch in str(s) if not ch.isspace())


def letters(n):
    s = ''
    while n:
        n, k = divmod(n - 1, 26)
        s = chr(65 + k) + s
    return s


def empty_sheets(d):
    """v3: indexes of the empty sheets, rows x columns = 0 with no cell and no view (the builders write them in_scope false)."""
    used = {c['sheet_index'] for c in d['cells']}
    viewed = {v['sheet'] for v in d['views']}
    return {s['index'] for s in d['sheets'] if s['rows'] * s['columns'] == 0 and s['index'] not in used and s['name'] not in viewed}


class Sheet:
    def __init__(self, meta, cells, has_content):
        self.meta = meta
        self.index = meta['index']
        self.grid = {(c['row'], c['col']): c for c in cells}
        self.content = {k: c for k, c in self.grid.items() if has_content(c)}
        self.rows = sorted({r for r, _ in self.content})
        self.byrow = {}
        for (r, col), c in sorted(self.content.items()):
            self.byrow.setdefault(r, []).append(c)

    def text(self, r, col):
        c = self.content.get((r, col))
        if c is None or c['saved_type'] != 'text' or c['state'] not in ('literal', 'cached_formula') or not isinstance(c['saved_value'], str):
            return None
        return c['saved_value']

    def value(self, r, col):
        c = self.content.get((r, col)) if col else None
        return None if c is None else c['saved_value']

    def number(self, r, col):
        c = self.content.get((r, col))
        if c is None or c['saved_type'] != 'number' or c['state'] not in ('literal', 'cached_formula'):
            return None
        v = c['saved_value']
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def words(self, r):
        """normalised text -> sorted columns, for the text cells of row r"""
        out = {}
        for c in self.byrow.get(r, []):
            t = self.text(r, c['col'])
            if t is not None:
                out.setdefault(norm(t), []).append(c['col'])
        return out


# ------------------------------------------------------------------ BILL1
def bill_categories(words):
    return {'項次': '項次' in words, 'name': any(w in words for w in NAME_WORDS), '單位': '單位' in words,
            '數量': '數量' in words, '單價': '單價' in words, 'amount': '複價' in words or '金額' in words}


def bill1(sh):
    """BILL1.v1 on one sheet. Returns a dict with the three conditions and, when (a) holds, the header geometry."""
    full, near = [], []
    for r in sh.rows:
        cats = bill_categories(sh.words(r))
        n = sum(cats.values())
        if n == 6:
            full.append(r)
        elif n == 5:
            near.append(r)
    res = {'header_rows_all_six': full, 'header_rows_five_of_six': near[:20], 'a': len(full) == 1, 'b': False, 'c': False,
           'candidate': False}
    if len(full) != 1:
        return res
    hr = full[0]
    w = sh.words(hr)
    name_cols = sorted(col for x in NAME_WORDS for col in w.get(x, []))
    amount_cols = w.get('複價') or w.get('金額')
    cols = {'item': min(w['項次']), 'name': name_cols[0], 'unit': min(w['單位']), 'quantity': min(w['數量']),
            'unit_price': min(w['單價']), 'amount': min(amount_cols)}
    price_cols = sorted(set(w['單價']) | set(amount_cols))
    res.update(header_row=hr, columns=cols, price_columns=[letters(c) for c in price_cols])
    end = None
    for r in sh.rows:
        if r > hr and any(sh.text(r, col) is not None and norm(sh.text(r, col)) in TOTAL_WORDS for col in price_cols):
            end = r
            break
    if end is None:
        return res
    res['b'] = True
    res['end_row'] = end
    res['end_cell'] = next(letters(col) + str(end) for col in price_cols if sh.text(end, col) is not None and norm(sh.text(end, col)) in TOTAL_WORDS)
    res['c'] = any((sh.number(r, col) or 0) > 0 for r in sh.rows if hr < r < end for col in price_cols)
    res['candidate'] = res['c']
    return res


# ------------------------------------------------------------------ bill lines
def positive_text(t):
    m = POSITIVE_TEXT_RE.fullmatch(norm(t))
    return bool(m) and float(m.group(1).replace(',', '')) > 0


def line_state(sh, r, cols):
    p, t = sh.value(r, cols['unit_price']), sh.value(r, cols['amount'])
    vals = [x for x in (p, t) if x is not None]
    if any((isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0) or (isinstance(x, str) and positive_text(x)) for x in vals):
        return 'priced'
    if any(isinstance(x, str) and STATUS_TEXT in x for x in vals):
        return 'not_estimated'
    if any(isinstance(x, str) and norm(x) and not ZERO_TEXT_RE.fullmatch(norm(x)) for x in vals):
        return 'other_price_text'
    return 'unpriced_no_status'


def item_like(sh, r, cols):
    n, q, u = sh.value(r, cols['name']), sh.value(r, cols['quantity']), sh.value(r, cols['unit'])
    un = norm(u) if u is not None else ''
    return n is not None and (q is not None or un not in ('', '全'))


def code_tokens(text):
    out = set()
    for tok in CODE_RE.findall(str(text)):
        if sum(ch.isdigit() for ch in tok) >= 4:
            out.add(tok.upper())
            if tok[0] in 'Mm':
                out.add(tok[1:].upper())
    return out


def bill_lines(sh, b):
    cols, hr, end = b['columns'], b['header_row'], b['end_row']
    first = next((r for r in sh.rows if hr < r < end and item_like(sh, r, cols)), None)
    lines, cur = [], None
    if first is None:
        return first, lines
    for r in sh.rows:
        if not first <= r < end:
            continue
        state = line_state(sh, r, cols)
        if item_like(sh, r, cols):
            cur = {'row': r, 'rows': [r], 'state': state, 'numbered': sh.value(r, cols['item']) is not None,
                   'item_no': norm(sh.value(r, cols['item'])) if sh.value(r, cols['item']) is not None else '',
                   'text': norm(sh.value(r, cols['name'])), 'codes': set()}
            lines.append(cur)
        elif cur is not None and sh.value(r, cols['item']) is None and state != 'priced':
            n = sh.value(r, cols['name'])
            if isinstance(n, str) and '小計' not in norm(n) and '合計' not in norm(n):
                cur['text'] += norm(n)
            cur['rows'].append(r)
        else:
            cur = None
            continue
        for c in sh.byrow.get(r, []):
            if c['col'] != cols['name'] and isinstance(c['saved_value'], str):
                cur['codes'] |= code_tokens(c['saved_value'])
    return first, lines


# ------------------------------------------------------------------ other sheet roles and analysis blocks
def is_heading(t):
    n = norm(t)
    return n.startswith('工作項目') and n != '工作項目'


def heading_rows(sh):
    return [r for r in sh.rows if any(sh.text(r, c['col']) is not None and is_heading(sh.text(r, c['col'])) for c in sh.byrow[r])]


def sheet_role(sh, bill_candidate):
    if bill_candidate:
        return 'bill'
    rows_words = [sh.words(r) for r in sh.rows]
    if any(all(x in w for x in RESOURCE_WORDS) for w in rows_words):
        return 'resource_statistics'
    if any('工料名稱' in w for w in rows_words) and heading_rows(sh):
        return 'analysis'
    if any('項次' in w and any(x in w for x in SUMMARY_NAME_WORDS) and any(x in w for x in SUMMARY_AMOUNT_WORDS) and '單價' not in w
           for w in rows_words):
        return 'summary'
    return 'other'


def blocks(sh):
    heads = heading_rows(sh)
    last = sh.meta['rows']
    out = []
    for i, r in enumerate(heads):
        nxt = heads[i + 1] if i + 1 < len(heads) else last + 1
        hcell = next(c for c in sh.byrow[r] if sh.text(r, c['col']) is not None and is_heading(sh.text(r, c['col'])))
        name = re.sub(r'^工作項目[:：]?', '', norm(hcell['saved_value']))
        code = ''
        for c in sh.byrow[r]:
            t = sh.text(r, c['col'])
            if t is not None and '計價代碼' in t:
                code = re.split(r'[:：]', norm(t))[-1].upper()
        left = [c for c in sh.byrow[r] if c['col'] < hcell['col'] and c['saved_value'] is not None]
        ref = norm(left[0]['saved_value']) if left else ''
        comps, hdr = 0, None
        for rr in [x for x in sh.rows if r <= x < nxt]:
            w = sh.words(rr)
            if hdr is None:
                if '工料名稱' in w:
                    hdr = {'name': min(w['工料名稱']), 'unit': min(w['單位']) if '單位' in w else None,
                           'quantity': min(w['數量']) if '數量' in w else None}
                continue
            nm = sh.value(rr, hdr['name'])
            nt = norm(nm) if nm is not None else ''
            if nt in ('合計', '計', '小計') or nt.startswith('合計'):
                break
            if nt and (sh.value(rr, hdr['quantity']) is not None or sh.value(rr, hdr['unit']) is not None):
                comps += 1
        out.append({'row': r, 'name': name, 'code': code, 'ref': ref, 'components': comps, 'frame': not name and not code})
    return out


def links(bk, lines):
    keys = {bk['code']} | ({bk['code'][1:]} if bk['code'].startswith('M') else set()) if bk['code'] else set()
    found, prefix = [], []
    for ln in lines:
        by = []
        if keys & ln['codes']:
            by.append('code')
        if bk['name'] and bk['name'] == ln['text']:
            by.append('name')
        if PATH_RE.fullmatch(bk['ref']) and bk['ref'] == ln['item_no']:
            by.append('outline_path')
        if by:
            found.append((ln, by))
        elif (len(bk['name']) >= 8 and len(ln['text']) >= 8 and (bk['name'].startswith(ln['text']) or ln['text'].startswith(bk['name']))):
            prefix.append(ln)
    return found, prefix


# ------------------------------------------------------------------ digest
def first_header_row(sh):
    for r in sh.rows:
        cats = set()
        for c in sh.byrow[r]:
            t = sh.text(r, c['col'])
            if t is None:
                continue
            n = norm(t)
            for k, p in VOCAB_RE:
                if p.fullmatch(n):
                    cats.add(k)
                    break
        if len(cats) >= 4:
            return r
    return None


def render(sh, r):
    cells, more = [], 0
    for c in sh.byrow.get(r, []):
        if c['col'] > DIGEST_COLS:
            more += 1
            continue
        x = {'a': c['address'], 't': c['saved_type'], 'v': c['saved_value']}
        if c['state'] != 'literal':
            x['s'] = c['state']
        cells.append(x)
    return {'row': r, 'cells': cells, **({'more_cells_beyond_column_J': more} if more else {})}


def price_like_cols(sh, hr):
    if hr is None:
        return []
    out = []
    for c in sh.byrow[hr]:
        t = sh.text(hr, c['col'])
        if t is not None and (norm(t).startswith(('單價', '複價', '金額')) or norm(t) == '總價'):
            out.append(c['col'])
    return sorted(set(out))


def digest_sheet(sh, role_counts):
    m = sh.meta
    states = {}
    for c in sh.content.values():
        k = c['state'] if c['state'] in ('literal', 'cached_formula') else 'other'
        states[k] = states.get(k, 0) + 1
    hr = first_header_row(sh)
    rows = sh.rows
    d = {'index': m['index'], 'name': m['name'], 'visibility': m['visibility'], 'rows': m['rows'], 'columns': m['columns'],
         'merges': len(m['merges']), 'formula_records': m['formula_records'],
         'content_cells': {'total': len(sh.content), 'literal': states.get('literal', 0), 'cached_formula': states.get('cached_formula', 0),
                           'other_states': states.get('other', 0)}}
    if hr is None:
        d['first_header_row'] = None
        d['first_rows'] = [render(sh, r) for r in rows[:8]]
    else:
        title = [r for r in rows if r < hr]
        d['title_rows'] = [render(sh, r) for r in title[:10]]
        if len(title) > 10:
            d['title_rows_omitted'] = len(title) - 10
        sig = tuple(norm(sh.text(hr, c['col']) or '') for c in sh.byrow[hr])
        reps = [r for r in rows if r != hr and tuple(norm(sh.text(r, c['col']) or '') for c in sh.byrow[r]) == sig]
        d['first_header_row'] = render(sh, hr)
        d['header_repeats'] = {'count': len(reps), 'rows': reps[:20]}
        d['rows_below_header'] = [render(sh, r) for r in [x for x in rows if x > hr][:5]]
    pcols = price_like_cols(sh, hr)
    tot = []
    for r in rows:
        if hr is not None and r > hr:
            for col in pcols:
                t = sh.text(r, col)
                if t is not None and any(x in norm(t) for x in TOTAL_WORDS) and '小計' not in norm(t):
                    tot.append((r, norm(t) in TOTAL_WORDS))
                    break
    pick = tot[:3]
    first_exact = next((x for x in tot if x[1]), None)
    if first_exact and first_exact not in pick:
        pick = pick[:2] + [first_exact]
    d['price_column_total_rows'] = []
    for r, _ in pick:
        i = rows.index(r)
        d['price_column_total_rows'].append({'row': r, 'context': [render(sh, x) for x in rows[max(0, i - 2): i + 3]]})
    d['price_column_total_rows_count'] = len(tot)
    shown = {r for r, _ in pick}
    other = [r for r in rows if r not in shown and any(sh.text(r, c['col']) is not None and re.search('合計|總計|總價', norm(sh.text(r, c['col'])))
                                                         for c in sh.byrow[r])]
    d['other_total_rows'] = [render(sh, r) for r in other[:3]]
    d['other_total_rows_count'] = len(other)
    heads = heading_rows(sh)
    d['block_headings'] = {'count': len(heads), 'first': [render(sh, r) for r in heads[:2]]}
    d['last_rows'] = [render(sh, r) for r in rows[-3:]]
    nonzero = sum(1 for (r, col) in sh.content if col in pcols and hr is not None and r > hr and (sh.number(r, col) or 0) > 0)
    status_all = sum(1 for c in sh.content.values() if isinstance(c['saved_value'], str) and STATUS_TEXT in c['saved_value'])
    status_price = sum(1 for (r, col), c in sh.content.items() if col in pcols and isinstance(c['saved_value'], str) and STATUS_TEXT in c['saved_value'])
    d['counts'] = {'price_like_columns': [letters(c) for c in pcols], 'nonzero_numbers_in_price_like_columns': nonzero,
                   'not_estimated_cells': status_all, 'not_estimated_cells_in_price_like_columns': status_price, **role_counts}
    return d


def digest_size(x):
    """(rendered rows, rendered cells) in a digest; a row shown twice (for example as context and as a last row) counts twice."""
    if isinstance(x, dict):
        own = (1, len(x['cells'])) if set(x) >= {'row', 'cells'} else (0, 0)
        subs = [digest_size(v) for v in x.values()]
        return own[0] + sum(r for r, _ in subs), own[1] + sum(c for _, c in subs)
    if isinstance(x, list):
        subs = [digest_size(v) for v in x]
        return sum(r for r, _ in subs), sum(c for _, c in subs)
    return 0, 0


def extract_rules(text):
    """R47b and R49-R51 paragraphs, verbatim, from FIELD_ROLES.md."""
    lines = text.split('\n')
    out = []
    for key in ('**R47b ', '**R49 ', '**R50 ', '**R51 '):
        start = next((i for i, x in enumerate(lines) if x.startswith(key)), None)
        if start is None:
            raise Refused('FIELD_ROLES_RULE_NOT_FOUND', key.strip('* '))
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('**R') or lines[i].startswith('## ')), len(lines))
        out.append('\n'.join(lines[start:end]).rstrip())
    return out


# ------------------------------------------------------------------ main computation
def propose(inv_raw, route):
    try:
        inv = route.Inventory(inv_raw)
    except (route.Rejected, KeyError, TypeError, ValueError) as e:
        raise Refused('INVENTORY_REJECTED_BY_ROUTE', repr(e)[:300])
    d = inv.d
    empty = empty_sheets(d)
    if not all(s['in_scope'] or s['index'] in empty for s in d['sheets']):
        raise Refused('FULL_INVENTORY_REQUIRED', 'every sheet of the full inventory is in scope (build it with every sheet in scope); '
                                                 'only an empty sheet (rows x columns = 0, no cell or view) may be out of scope')
    if route.SCOPE_REF in inv.context:
        raise Refused('ALREADY_SCOPED', 'the inventory already carries context:scope')
    has = route.Inventory.has_content
    per = {}
    for c in d['cells']:
        per.setdefault(c['sheet_index'], []).append(c)
    sheets = [Sheet(s, per.get(s['index'], []), has) for s in d['sheets']]
    litcf = sum(1 for c in d['cells'] if c['state'] in ('literal', 'cached_formula') and c['saved_value'] is not None and c['saved_value'] != '')
    applies = litcf > route.SCOPE_THRESHOLD
    b1 = {sh.index: bill1(sh) for sh in sheets}
    cands = [i for i, r in b1.items() if r['candidate']]
    near = [i for i, r in b1.items() if not r['candidate'] and (r['header_rows_all_six'] or r['header_rows_five_of_six'])]
    holds, flags = [], []

    def flag(si, code, **detail):
        flags.append({'id': f'F{len(flags) + 1}', 'sheet_index': si, 'code': code, **({'detail': detail} if detail else {})})
    bill = sheets[[sh.index for sh in sheets].index(cands[0])] if len(cands) == 1 else None
    if len(cands) != 1:
        holds.append({'code': 'BILL1_CANDIDATES_NOT_ONE', 'candidates': cands,
                      'note': 'zero or several BILL1 candidates: the case is held for the owner (R59)'})
    lines, first = [], None
    if bill is not None:
        first, lines = bill_lines(bill, b1[bill.index])
        if not lines:
            holds.append({'code': 'NO_IN_RANGE_LINES', 'note': 'the BILL1 range holds no item-like line'})
    states = {}
    for ln in lines:
        states[ln['state']] = states.get(ln['state'], 0) + 1
    unpriced = ('unpriced_no_status', 'other_price_text')
    cond_i = bool(lines) and all(ln['state'] in unpriced for ln in lines)
    if states.get('other_price_text'):
        flag(bill.index, 'OTHER_PRICE_TEXT_LINES', lines=states['other_price_text'],
             note='lines whose price cells hold other text count as unpriced with no status for the R51 conditions')
    roles, per_sheet, analysis_info = {}, [], {}
    for sh in sheets:
        roles[sh.index] = sheet_role(sh, sh.index in cands)
    for sh in sheets:
        if roles[sh.index] != 'analysis':
            continue
        bks = blocks(sh)
        real = [x for x in bks if not x['frame']]
        info = {'blocks': len(real), 'empty_frames': len(bks) - len(real), 'components': sum(x['components'] for x in real),
                'links_by': {'code': 0, 'name': 0, 'outline_path': 0}, 'linked_blocks': 0,
                'linked_blocks_by_parent_state': {k: 0 for k in ('priced', 'not_estimated', 'other_price_text', 'unpriced_no_status')},
                'name_prefix_only_blocks': 0, 'linked_blocks_of_unpriced_lines': 0}
        prefix_unpriced = 0
        for bk in real:
            found, prefix = links(bk, lines)
            if found:
                info['linked_blocks'] += 1
                for st in sorted({ln['state'] for ln, _ in found}):
                    info['linked_blocks_by_parent_state'][st] += 1
                for m in sorted({x for _, by in found for x in by}):
                    info['links_by'][m] += 1
                if any(ln['state'] in unpriced for ln, _ in found):
                    info['linked_blocks_of_unpriced_lines'] += 1
            elif prefix:
                info['name_prefix_only_blocks'] += 1
                if any(ln['state'] in unpriced for ln in prefix):
                    prefix_unpriced += 1
        if prefix_unpriced:
            flag(sh.index, 'NAME_PREFIX_ONLY_LINK_TO_UNPRICED_LINE', blocks=prefix_unpriced,
                 note='blocks share only a name prefix with an unpriced, no-status line; R46 needs a shared code or name')
        analysis_info[sh.index] = info
    if cond_i and bill is not None and not analysis_info:
        holds.append({'code': 'R51_ALL_UNPRICED_WITHOUT_ANALYSIS_SHEET',
                      'note': 'every in-range line has no price and no status, but no analysis sheet was found'})
    out_sheets = []
    for sh in sheets:
        role = roles[sh.index]
        info = analysis_info.get(sh.index)
        if role == 'bill':
            in_scope, reason = True, REASONS['bill']
        elif role == 'analysis' and cond_i:
            in_scope, reason = True, REASONS['analysis_i']
        elif role == 'analysis':
            in_scope, reason = False, REASONS['analysis_out']
            if info['linked_blocks']:
                nu = info['linked_blocks_of_unpriced_lines']
                reason += (f"; {info['linked_blocks']} linked block(s): {info['linked_blocks'] - nu} of priced or not-estimated parents "
                           f"(not 未填 rows, not written on a scoped packet), {nu} of parents with no price and no status "
                           '(those lines are excluded_supply); none gives rows (R51, R59)')
        else:
            in_scope, reason = False, REASONS['empty' if sh.index in empty else role]
        linked = info['linked_blocks'] if (info and not in_scope) else 0
        out_sheets.append({'index': sh.index, 'name': sh.meta['name'], 'role': role, 'visibility': sh.meta['visibility'],
                           'rows': sh.meta['rows'], 'columns': sh.meta['columns'], 'content_cells': len(sh.content),
                           'content_cells_literal_or_cached': sum(1 for c in sh.content.values() if c['state'] in ('literal', 'cached_formula')),
                           'in_scope': in_scope, 'reason': reason, 'linked_analysis_blocks': linked})
        if sh.index in empty:           # v3: an empty sheet (role other, no cell) gets no flag
            continue
        if sh.meta['visibility'] != 'visible':
            flag(sh.index, 'HIDDEN_SHEET', visibility=sh.meta['visibility'])
        if role == 'other':
            flag(sh.index, 'OTHER_ROLE_SHEET')
        if sh.index in near:
            flag(sh.index, 'NEAR_BILL1_CANDIDATE', a=b1[sh.index]['a'], b=b1[sh.index]['b'], c=b1[sh.index]['c'],
                 rows_all_six=len(b1[sh.index]['header_rows_all_six']), rows_five_of_six=len(b1[sh.index]['header_rows_five_of_six']))
        if not in_scope:
            hr = first_header_row(sh)
            pc = price_like_cols(sh, hr)
            nz = sum(1 for (r, col) in sh.content if col in pc and r > hr and (sh.number(r, col) or 0) > 0) if hr else 0
            st = sum(1 for c in sh.content.values() if isinstance(c['saved_value'], str) and STATUS_TEXT in c['saved_value'])
            if nz:
                flag(sh.index, 'OUT_OF_SCOPE_NONZERO_PRICES', cells=nz)
            if st:
                flag(sh.index, 'OUT_OF_SCOPE_NOT_ESTIMATED_TEXT', cells=st)
            if linked:
                nu = info['linked_blocks_of_unpriced_lines']
                flag(sh.index, 'LINKED_BLOCKS_OUT_OF_SCOPE', blocks=linked, of_priced_or_not_estimated_parents=linked - nu,
                     of_parents_with_no_price_and_no_status=nu)
    b = b1[bill.index] if bill is not None else None
    proposal = {
        'schema': PROPOSAL_SCHEMA, 'tool': {'name': 'scope_tool.py', 'version': TOOL_VERSION},
        'rule': {'scope': route.SCOPE_RULE, 'bill': route.SCOPE_BILL_RULE, 'threshold': route.SCOPE_THRESHOLD},
        'case_id': inv.case_id, 'family_id': inv.family_id, 'full_inventory_sha256': inv.sha256,
        'content_cells_literal_or_cached': litcf, 'content_cells_census': sum(len(sh.content) for sh in sheets), 'applies': applies,
        'status': 'NOT_APPLIED' if not applies else ('HOLD' if holds else 'PROPOSED'),
        'holds': holds if applies else [],
        'bill': {'rule': route.SCOPE_BILL_RULE, 'candidates': cands, 'near_candidates': near,
                 'per_sheet': {str(i): {k: r[k] for k in ('a', 'b', 'c', 'candidate')} for i, r in b1.items()},
                 'sheet_index': bill.index if bill is not None else None,
                 'header_row': b['header_row'] if b else None, 'price_columns': b['price_columns'] if b else None,
                 'end_row': b['end_row'] if b else None, 'end_cell': b['end_cell'] if b else None, 'first_item_row': first},
        'r51': {'in_range_lines': len(lines), 'by_state': {k: states.get(k, 0) for k in ('priced', 'not_estimated', 'other_price_text', 'unpriced_no_status')},
                'condition_i_all_unpriced_no_status': cond_i,
                'analysis_sheets': {str(i): x for i, x in analysis_info.items()}, 'condition_ii_adopted': False, 'option_iii_adopted': False},
        'sheets': out_sheets, 'flags': flags,
        'in_scope_content_cells': sum(s['content_cells'] for s in out_sheets if s['in_scope']) if applies else sum(s['content_cells'] for s in out_sheets),
    }
    if not applies:
        for s, sh in zip(out_sheets, sheets):
            s['in_scope'] = sh.index not in empty or bool(sh.meta['in_scope'])   # v3: an empty sheet keeps the packet's flag
            s['reason'] = (f'scope stage not applied: {litcf} literal or cached-formula content cells, not more than {route.SCOPE_THRESHOLD} (R59)'
                           if s['in_scope'] else REASONS['empty'])
            s['linked_analysis_blocks'] = 0
        proposal['flags'] = []
        return proposal, None
    dsheets = []
    for sh in sheets:
        rc = {}
        bb = b1[sh.index]
        if bb['a'] and bb['b']:
            f2, ls = bill_lines(sh, bb)
            st2 = {}
            for ln in ls:
                st2[ln['state']] = st2.get(ln['state'], 0) + 1
            rc['lines_from_first_item_below_header_to_first_exact_price_column_total'] = {
                'lines': len(ls), **{k: st2.get(k, 0) for k in ('priced', 'not_estimated', 'other_price_text', 'unpriced_no_status')}}
        if sh.index in analysis_info:
            x = analysis_info[sh.index]
            rc['analysis_blocks'] = {k: x[k] for k in ('blocks', 'empty_frames', 'components', 'linked_blocks', 'links_by',
                                                       'linked_blocks_by_parent_state', 'linked_blocks_of_unpriced_lines',
                                                       'name_prefix_only_blocks')}
        dsheets.append(digest_sheet(sh, rc))
    digest = {'schema': DIGEST_SCHEMA, 'case_id': inv.case_id, 'full_inventory_sha256': inv.sha256,
              'tool': {'name': 'scope_tool.py', 'version': TOOL_VERSION},
              'note': ('Excerpt of the full source inventory for the scope reader (FIELD_ROLES R59). Cells are shown with their address, '
                       'saved type, saved value and, when not literal, state; rows are capped at column J. The counts were computed '
                       'by the scope tool on the full inventory; links are blocks sharing a code, name or outline path with a line '
                       'between the first item-like row below the first header and the first exact 合計/總計 price-column row.'),
              'sheets': dsheets}
    return proposal, digest


def main(argv=None):
    ap = argparse.ArgumentParser(description='Scope stage step 1 (R59): BILL1 and R51 proposal plus the scope digest.')
    ap.add_argument('--inventory', required=True, type=Path)
    ap.add_argument('--out-dir', required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        if not a.inventory.is_absolute() or not a.out_dir.is_absolute():
            raise Refused('ABSOLUTE_PATH_REQUIRED')
        if a.out_dir.exists():
            raise Refused('OUTPUT_EXISTS')
        route = load_route()
        raw = a.inventory.read_bytes()
        proposal, digest = propose(raw, route)
        files = {}
        if digest is not None:
            rules = extract_rules(FIELD_ROLES.read_text(encoding='utf-8'))
            excerpt = ('# Scope reader rules excerpt (candidate 046g)\n\nCopied verbatim from `package/resources/FIELD_ROLES.md` '
                       f'(sha256 {sha(FIELD_ROLES.read_bytes())}): R47b and R49-R51.\n\n' + '\n\n'.join(rules) + '\n').encode('utf-8')
            dbytes = (json.dumps(digest, ensure_ascii=False, indent=1, allow_nan=False) + '\n').encode('utf-8')
            files['SCOPE_DIGEST.json'] = dbytes
            files['SCOPE_RULES_EXCERPT.md'] = excerpt
            rows_, cells_ = digest_size(digest)
            proposal['digest'] = {'file': 'SCOPE_DIGEST.json', 'sha256': sha(dbytes), 'bytes': len(dbytes), 'rendered_rows': rows_,
                                  'rendered_cells': cells_}
            proposal['rules_excerpt'] = {'file': 'SCOPE_RULES_EXCERPT.md', 'sha256': sha(excerpt), 'field_roles_sha256': sha(FIELD_ROLES.read_bytes())}
        else:
            proposal['digest'] = None
            proposal['rules_excerpt'] = None
        proposal['tool']['sha256'] = sha(Path(__file__).read_bytes())
        proposal['tool']['route_sha256'] = sha(ROUTE.read_bytes())
        pbytes = (json.dumps(proposal, ensure_ascii=False, indent=1, allow_nan=False) + '\n').encode('utf-8')
        files['SCOPE_PROPOSAL.json'] = pbytes
    except Refused as e:
        sys.stderr.write(json.dumps({'status': 'REFUSED', 'code': e.code, 'detail': e.detail}, ensure_ascii=False) + '\n')
        return 1
    a.out_dir.mkdir(parents=True)
    for name, b in files.items():
        with open(a.out_dir / name, 'xb') as f:
            f.write(b)
    p = proposal
    print(json.dumps({'status': p['status'], 'case_id': p['case_id'], 'full_inventory_sha256': p['full_inventory_sha256'],
                      'content_cells_literal_or_cached': p['content_cells_literal_or_cached'], 'threshold': p['rule']['threshold'],
                      'bill_candidates': p['bill']['candidates'], 'bill_sheet_index': p['bill']['sheet_index'],
                      'end_row': p['bill']['end_row'], 'r51_condition_i': p['r51']['condition_i_all_unpriced_no_status'],
                      'sheets': [{'index': s['index'], 'role': s['role'], 'in_scope': s['in_scope'], 'content_cells': s['content_cells'],
                                  'linked_analysis_blocks': s['linked_analysis_blocks']} for s in p['sheets']],
                      'in_scope_content_cells': p['in_scope_content_cells'], 'flags': [f['code'] for f in p['flags']],
                      'holds': [h['code'] for h in p['holds']], 'proposal_sha256': sha(files['SCOPE_PROPOSAL.json']),
                      'digest_sha256': p['digest']['sha256'] if p['digest'] else None,
                      'digest_rendered_cells': p['digest']['rendered_cells'] if p['digest'] else None, 'values_printed': False}, ensure_ascii=False))
    return 4 if p['status'] == 'HOLD' else 0


if __name__ == '__main__':
    sys.exit(main())
