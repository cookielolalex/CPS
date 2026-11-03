"""CPS candidate 046b source-reference checker and carrier adapter (stdlib only).

check   : validate a semantic response against its pinned source inventory and the
          existing writer004 carrier rules; print every violation. No output files.
convert : run the same checks, then copy referenced source values into a
          cps.cached-xls(x)-research-carrier.v1 object for writer004.validateCarrier,
          plus a complete positional census ledger. Refuses on any violation.

The adapter only validates and copies. It never selects references, edits a value,
shortens a name, repairs a response or reads anything except the two given files.
"""
import argparse, copy, hashlib, json, math, re, sys
from decimal import Decimal
from pathlib import Path

VERSION = 'cps046b-route.v1'
RESPONSE_SCHEMA = 'cps.semantic-source-refs.v2'
INVENTORY_SCHEMA = 'cps.source-inventory.cells.v2'
PROFILE = 'cached-cell-raw-scalar-text.v2'
COLS = 'ABCDEFGHIJKLMNOPQ'
HEADERS = ['盤體名稱', '盤體規格', '材料名稱', '規格', '單位', '數量', '單價', '複價', '型號', '廠牌',
           '訂購廠商', '工程編號', '訂購客戶', '使用客戶', '需要日期', '需要數量', '合約價']
RAW = ('description', 'unit', 'quantity', 'unit_price', 'amount', 'remarks')
SINGLE_RAW = ('unit', 'quantity', 'unit_price', 'amount')
NUMERIC_COLS = (5, 15, 16)          # F, P, Q
BLANK_COLS = (6, 7)                 # G, H
ROLES = ('demand_content', 'analysis_content', 'item_identifier', 'header', 'section',
         'financial_summary', 'commercial_note', 'document_reference', 'footer', 'unresolved')
CENSUS_ROLES = ('item_identifier', 'header', 'section', 'financial_summary', 'commercial_note',
                'document_reference', 'footer', 'unresolved')
GROUP_RELATIONS = ('contractual_group', 'physical_enclosure', 'contractual_and_physical', 'unresolved')
LIMIT = 20 * 1024 * 1024
MAX_SAFE = 9007199254740991
ID_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}')
CELL_REF_RE = re.compile(r'cell:S([1-9][0-9]{0,3})!([A-Z]{1,3})([1-9][0-9]{0,6})')
CONTEXT_REF_RE = re.compile(r'context:[a-z0-9_]{1,64}')
ADDR_RE = re.compile(r'([A-Z]{1,3})([1-9][0-9]{0,6})')
# JavaScript String.prototype.trim / \s whitespace set (writer004 runs in Node).
JS_WS = '\t\n\x0b\x0c\r                  　﻿'
CTRL_RE = re.compile('[\u0000-\u0008\u000b\u000c\u000e-\u001f]')
FORMULA_RE = re.compile('^[' + re.escape(JS_WS) + ']*[=+@-]')
NUMERIC_TEXT_RE = re.compile(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?')
PATHLIKE_RE = re.compile(r'(?:[A-Za-z]:[\\/]|\\\\|file://|https?://)', re.I)


class Rejected(ValueError):
    pass


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def strict_load(raw):
    if len(raw) > LIMIT:
        raise Rejected('INPUT_SIZE_LIMIT')

    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise Rejected('DUPLICATE_JSON_KEY:' + k)
            out[k] = v
        return out

    def bad_constant(_):
        raise Rejected('NONFINITE_NUMBER')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=bad_constant)
    except UnicodeDecodeError:
        raise Rejected('UTF8_REQUIRED')
    except (json.JSONDecodeError, RecursionError) as e:
        raise Rejected('INVALID_JSON:' + str(e)[:120])


def js_len(s):
    return len(s.encode('utf-16-le', 'surrogatepass')) // 2


def js_blank(s):
    return s.strip(JS_WS) == ''


def lone_surrogate(s):
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in s)


def canonical_number(v):
    """R2: plain base-10 text of a finite binary64 value; no exponent/grouping."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise Rejected('NUMBER_REQUIRED')
    f = float(v)
    if not math.isfinite(f):
        raise Rejected('NONFINITE_NUMBER')
    s = format(Decimal(repr(f)), 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    if s in ('-0', ''):
        s = '0'
    return s


def writer_numeric_raw(text):
    """Port of writer004 numericRaw: returns float or None if writer would reject."""
    if not isinstance(text, str):
        return None
    t = text.strip(JS_WS)
    if not NUMERIC_TEXT_RE.fullmatch(t):
        return None
    n = float(t.replace(',', ''))
    if not math.isfinite(n) or abs(n) > MAX_SAFE:
        return None
    return n


def col_number(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def parse_range(r):
    a = r.split(':')
    if len(a) not in (1, 2):
        raise Rejected('RANGE_REQUIRED')
    lo, hi = ADDR_RE.fullmatch(a[0]), ADDR_RE.fullmatch(a[-1])
    if not lo or not hi:
        raise Rejected('RANGE_REQUIRED')
    lo = (col_number(lo[1]), int(lo[2]))
    hi = (col_number(hi[1]), int(hi[2]))
    if lo[0] > hi[0] or lo[1] > hi[1]:
        raise Rejected('RANGE_ORDER')
    return lo, hi


class Report:
    def __init__(self):
        self.violations = []
        self.warnings = []

    def bad(self, code, where, detail=None, category='invalid'):
        v = {'code': code, 'where': where, 'category': category}
        if detail is not None:
            v['detail'] = detail
        self.violations.append(v)

    def hold(self, code, where, detail=None):
        self.bad(code, where, detail, 'unrepresentable_hold')

    def warn(self, code, where, detail=None):
        w = {'code': code, 'where': where}
        if detail is not None:
            w['detail'] = detail
        self.warnings.append(w)


def exact_keys(obj, keys, where, rep):
    if not isinstance(obj, dict):
        rep.bad('OBJECT_REQUIRED', where)
        return False
    missing = [k for k in keys if k not in obj]
    extra = [k for k in obj if k not in keys]
    if missing or extra:
        rep.bad('EXACT_KEYS_REQUIRED', where, {'missing': missing, 'unexpected': extra})
        return False
    return True


def writer_text(v, where, rep, allow_blank=False, check_formula=True, hold_formula=True):
    """Apply writer004 string rules; returns True if acceptable."""
    if not isinstance(v, str):
        rep.bad('STRING_REQUIRED', where)
        return False
    ok = True
    if lone_surrogate(v):
        rep.bad('LONE_SURROGATE', where)
        ok = False
    if not allow_blank and js_blank(v):
        rep.bad('NONBLANK_STRING_REQUIRED', where)
        ok = False
    if js_len(v) > 30000:
        rep.bad('STRING_TOO_LONG', where)
        ok = False
    if CTRL_RE.search(v):
        rep.hold('CONTROL_CHARACTER_UNREPRESENTABLE', where)
        ok = False
    if check_formula and FORMULA_RE.match(v):
        if hold_formula:
            rep.hold('FORMULA_LIKE_STRING_WHOLE_OUTPUT_HELD', where, {'retained_value': v})
        else:
            rep.bad('FORMULA_LIKE_STRING', where)
        ok = False
    return ok


def ident(v, where, rep):
    if not isinstance(v, str) or not ID_RE.fullmatch(v):
        rep.bad('ID_REQUIRED', where, {'pattern': ID_RE.pattern})
        return False
    return True


# ---------------------------------------------------------------- inventory
class Inventory:
    def __init__(self, raw):
        self.raw = raw
        self.sha256 = sha256(raw)
        d = strict_load(raw)
        self.d = d
        if not isinstance(d, dict) or d.get('schema') != INVENTORY_SCHEMA:
            raise Rejected('INVENTORY_SCHEMA')
        if d.get('representation_profile') != PROFILE:
            raise Rejected('INVENTORY_PROFILE')
        src = d['source']
        cs = src['carrier_source']
        self.kind = cs['kind']
        if self.kind not in ('cached_xls', 'cached_xlsx') or src['format'] != self.kind:
            raise Rejected('INVENTORY_SOURCE_KIND')
        if cs['sha256'] != src['sha256']:
            raise Rejected('INVENTORY_SOURCE_HASH_JOIN')
        self.carrier_source = cs
        self.adoption = src['adoption_status']
        self.case_id = d['case_id']
        self.family_id = d['family_id']
        self.views = {}
        for i, v in enumerate(cs['views']):
            if v['id'] != i + 1:
                raise Rejected('INVENTORY_VIEW_ID')
            self.views[v['id']] = (v['sheet'], parse_range(v['range']))
        inv_views = [{k: v[k] for k in ('id', 'sheet', 'range')} for v in d['views']]
        if inv_views != cs['views']:
            raise Rejected('INVENTORY_VIEWS_JOIN')
        self.sheets = {s['index']: s for s in d['sheets']}
        self.cells = {}
        for c in d['cells']:
            if c['ref'] in self.cells:
                raise Rejected('INVENTORY_DUPLICATE_REF')
            m = CELL_REF_RE.fullmatch(c['ref'])
            if not m or int(m[1]) != c['sheet_index'] or m[2] + m[3] != c['address']:
                raise Rejected('INVENTORY_REF_FORMAT:' + str(c.get('ref')))
            if self.sheets[c['sheet_index']]['name'] != c['sheet']:
                raise Rejected('INVENTORY_SHEET_JOIN')
            self.cells[c['ref']] = c
        expected = sum(s['rows'] * s['columns'] for s in d['sheets'] if s['in_scope'])
        if expected != len(self.cells):
            raise Rejected('INVENTORY_INCOMPLETE_CENSUS')
        self.context = {}
        for x in d['context_facts']:
            if x['ref'] in self.context or not CONTEXT_REF_RE.fullmatch(x['ref']):
                raise Rejected('INVENTORY_CONTEXT_REF')
            self.context[x['ref']] = x

    def cell_views(self, sheet, addr):
        m = ADDR_RE.fullmatch(addr)
        c, r = col_number(m[1]), int(m[2])
        return [vid for vid, (s, (lo, hi)) in self.views.items()
                if s == sheet and lo[0] <= c <= hi[0] and lo[1] <= r <= hi[1]]

    @staticmethod
    def has_content(c):
        s = c['state']
        if s in ('error', 'missing_cache', 'unresolved'):
            return True
        if s in ('literal', 'cached_formula'):
            return c['saved_value'] is not None and c['saved_value'] != ''
        if s == 'covered':
            return bool(c['conflicts'])
        return False


def locator(inv, refs, where, rep):
    """Build a writer locator from cell refs (single sheet, all inside views)."""
    cells = [inv.cells[r] for r in refs if r in inv.cells]
    if len(cells) != len(refs) or not cells:
        return None
    sheets = {c['sheet'] for c in cells}
    if len(sheets) != 1:
        rep.bad('LOCATION_SPANS_SHEETS', where)
        return None
    sheet = cells[0]['sheet']
    addrs, views = [], set()
    for c in cells:
        if c['address'] in addrs:
            continue
        vv = inv.cell_views(sheet, c['address'])
        if not vv:
            rep.hold('CELL_OUTSIDE_VIEWS', where, c['ref'])
            return None
        addrs.append(c['address'])
        views.update(vv)
    if len(addrs) > 1000:
        rep.bad('LOCATION_TOO_LARGE', where)
        return None
    return {'sheet': sheet, 'cells': addrs, 'views': sorted(views)}


# ---------------------------------------------------------------- checks
def ref_list(v, where, rep, inv, allow_context=False, min_items=0):
    if not isinstance(v, list):
        rep.bad('ARRAY_REQUIRED', where)
        return []
    if len(v) < min_items:
        rep.bad('REFS_REQUIRED', where)
    if len(set(x for x in v if isinstance(x, str))) != len(v):
        rep.bad('DUPLICATE_OR_NONSTRING_REF', where)
    good = []
    for i, r in enumerate(v):
        w = f'{where}[{i}]'
        if not isinstance(r, str):
            continue
        if r.startswith('context:') and allow_context:
            if r not in inv.context:
                rep.bad('UNKNOWN_CONTEXT_REF', w, r)
                continue
        elif r not in inv.cells:
            rep.bad('UNKNOWN_CELL_REF', w, r)
            continue
        good.append(r)
    return good


def cell_text_for_copy(inv, ref, where, rep, purpose):
    c = inv.cells[ref]
    if not c['usable_for_raw'] or c['canonical_raw'] is None:
        rep.bad('REF_NOT_USABLE_FOR_' + purpose, where, {'ref': ref, 'state': c['state'], 'reason': c['raw_limit_reason']})
        return None
    return c['canonical_raw']


def check(inv, resp_raw):
    rep = Report()
    try:
        r = strict_load(resp_raw)
    except Rejected as e:
        rep.bad(str(e), 'response')
        return rep, None
    top = ('schema', 'case_id', 'family_id', 'inventory_sha256', 'status', 'groups', 'items',
           'component_links', 'source_roles', 'limitations')
    if not exact_keys(r, top, 'response', rep):
        return rep, None
    if r['schema'] != RESPONSE_SCHEMA:
        rep.bad('RESPONSE_SCHEMA', 'schema')
    if r['case_id'] != inv.case_id:
        rep.bad('CASE_ID_MISMATCH', 'case_id')
    if r['family_id'] != inv.family_id:
        rep.bad('FAMILY_ID_MISMATCH', 'family_id')
    if r['inventory_sha256'] != inv.sha256:
        rep.bad('INVENTORY_HASH_MISMATCH', 'inventory_sha256')
    if r['status'] not in ('research_draft', 'partial', 'held'):
        rep.bad('RESPONSE_STATUS', 'status')
    for k in ('groups', 'items', 'component_links', 'source_roles', 'limitations'):
        if not isinstance(r[k], list):
            rep.bad('ARRAY_REQUIRED', k)
            return rep, None
    if len(r['limitations']) > 400:
        rep.bad('TOO_MANY_LIMITATIONS', 'limitations')
    for i, s in enumerate(r['limitations']):
        writer_text(s, f'limitations[{i}]', rep, check_formula=False)
    if not r['items']:
        rep.bad('ITEMS_REQUIRED', 'items')
    ids = set()

    covered = set()

    def cover(loc):
        if loc:
            covered.update(loc['views'])

    # groups
    groups = {}
    for i, g in enumerate(r['groups']):
        w = f'groups[{i}]'
        if not exact_keys(g, ('id', 'name', 'specification', 'relationship', 'anchor_refs', 'name_refs',
                              'specification_refs', 'quantity_basis', 'limitations'), w, rep):
            continue
        if ident(g['id'], w + '.id', rep):
            if g['id'] in ids:
                rep.bad('DUPLICATE_ID', w + '.id', g['id'])
            ids.add(g['id'])
            groups[g['id']] = g
        for k in ('name', 'specification'):
            if g[k] is not None:
                writer_text(g[k], f'{w}.{k}', rep, allow_blank=True, check_formula=False)
        if g['relationship'] not in GROUP_RELATIONS:
            rep.bad('GROUP_RELATIONSHIP', w + '.relationship', list(GROUP_RELATIONS))
        anchors = ref_list(g['anchor_refs'], w + '.anchor_refs', rep, inv, min_items=1)
        names = ref_list(g['name_refs'], w + '.name_refs', rep, inv)
        specs = ref_list(g['specification_refs'], w + '.specification_refs', rep, inv)
        if g['name'] is not None and not names:
            rep.bad('GROUP_NAME_PROOF_REQUIRED', w)
        if g['name'] is None and names:
            rep.bad('GROUP_NAME_REFS_WITHOUT_NAME', w)
        if g['specification'] is not None and not specs:
            rep.bad('GROUP_SPEC_PROOF_REQUIRED', w)
        if g['specification'] is None and specs:
            rep.bad('GROUP_SPEC_REFS_WITHOUT_SPEC', w)
        for rr in names + specs:
            if inv.cells[rr]['canonical_raw'] is None:
                rep.bad('GROUP_PROOF_CELL_EMPTY', w, rr)
        writer_text(g['quantity_basis'], w + '.quantity_basis', rep, check_formula=False)
        if not isinstance(g['limitations'], list):
            rep.bad('ARRAY_REQUIRED', w + '.limitations')
        else:
            for j, s in enumerate(g['limitations']):
                writer_text(s, f'{w}.limitations[{j}]', rep, check_formula=False)
            if g['name'] is None and not g['limitations']:
                rep.bad('UNRESOLVED_GROUP_REASON_REQUIRED', w)
        if anchors:
            cover(locator(inv, anchors + names + specs, w + '.location', rep))

    # items
    items = {}
    demand_ids, component_ids = set(), set()
    n_items = n_comp = 0
    for i, it in enumerate(r['items']):
        w = f'items[{i}]'
        if not exact_keys(it, ('id', 'role', 'group_id', 'status', 'values', 'proofs', 'raw_refs',
                               'anchor_refs', 'review_reasons'), w, rep):
            continue
        if ident(it['id'], w + '.id', rep):
            if it['id'] in ids:
                rep.bad('DUPLICATE_ID', w + '.id', it['id'])
            ids.add(it['id'])
            items[it['id']] = it
        if it['role'] == 'demand':
            demand_ids.add(it['id'])
            n_items += 1
        elif it['role'] == 'analysis_component':
            component_ids.add(it['id'])
            n_comp += 1
        else:
            rep.bad('ITEM_ROLE', w + '.role')
        if it['group_id'] is not None and it['group_id'] not in groups:
            rep.bad('UNKNOWN_GROUP_ID', w + '.group_id')
        if it['status'] not in ('research_draft', 'held'):
            rep.bad('ITEM_STATUS', w + '.status', ['research_draft', 'held'])
        rr_ok = isinstance(it['review_reasons'], list)
        if not rr_ok:
            rep.bad('ARRAY_REQUIRED', w + '.review_reasons')
        else:
            if len(it['review_reasons']) > 500:
                rep.bad('TOO_MANY_REVIEW_REASONS', w)
            for j, s in enumerate(it['review_reasons']):
                writer_text(s, f'{w}.review_reasons[{j}]', rep, check_formula=False)
            if it['status'] == 'held' and not it['review_reasons']:
                rep.bad('HELD_REASON_REQUIRED', w)
        vals = it['values']
        if not isinstance(vals, list) or len(vals) != 17:
            rep.bad('SEVENTEEN_VALUES_REQUIRED', w + '.values')
            continue
        if vals[2] is None and it['status'] != 'held':
            rep.bad('NULL_C_REQUIRES_HELD', w)
        # anchors and raw selections (item location: one sheet)
        anchors = ref_list(it['anchor_refs'], w + '.anchor_refs', rep, inv, min_items=1)
        raw_vals = {}
        loc_refs = list(anchors)
        rawsel = it['raw_refs']
        if exact_keys(rawsel, RAW, w + '.raw_refs', rep):
            for k in RAW:
                sw = f'{w}.raw_refs.{k}'
                sel = rawsel[k]
                if not exact_keys(sel, ('refs', 'reason_if_empty'), sw, rep):
                    continue
                refs = ref_list(sel['refs'], sw + '.refs', rep, inv)
                if k in SINGLE_RAW and len(sel['refs']) > 1:
                    rep.bad('SINGLE_CELL_RAW_FIELD', sw)
                if sel['refs']:
                    if sel['reason_if_empty'] is not None:
                        rep.bad('REASON_ONLY_FOR_EMPTY_SELECTION', sw)
                else:
                    if not isinstance(sel['reason_if_empty'], str) or js_blank(sel['reason_if_empty']):
                        rep.bad('EMPTY_SELECTION_REASON_REQUIRED', sw)
                parts = []
                for rf in refs:
                    t = cell_text_for_copy(inv, rf, sw, rep, 'RAW')
                    if t is not None:
                        parts.append(t)
                if refs and len(parts) == len(refs):
                    raw_vals[k] = '\n'.join(parts)
                    writer_text(raw_vals[k], sw + ':copied', rep, allow_blank=True, check_formula=False)
                elif not sel['refs']:
                    raw_vals[k] = None
                loc_refs += [x for x in refs if x not in loc_refs]
        if anchors:
            cover(locator(inv, loc_refs, w + '.location', rep))
        # values and proofs
        proofs = it['proofs']
        if not exact_keys(proofs, tuple(COLS), w + '.proofs', rep):
            continue
        for j, col in enumerate(COLS):
            v, p, vw = vals[j], proofs[col], f'{w}.values.{col}'
            if v is None:
                if not (isinstance(p, dict) and set(p) == {'reason'}):
                    rep.bad('NULL_PROOF_REQUIRED', f'{w}.proofs.{col}')
                else:
                    writer_text(p['reason'], f'{w}.proofs.{col}.reason', rep, check_formula=False)
                continue
            if j in BLANK_COLS:
                rep.bad('PURCHASE_PRICE_MUST_BE_BLANK', vw)
                continue
            if j in NUMERIC_COLS:
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) or abs(v) > MAX_SAFE:
                    rep.bad('FINITE_SAFE_NUMBER_REQUIRED', vw)
                    continue
            else:
                if not writer_text(v, vw, rep):
                    pass
            if not (isinstance(p, dict) and set(p) == {'refs', 'transformation', 'role_basis'}):
                rep.bad('NONNULL_PROOF_REQUIRED', f'{w}.proofs.{col}', 'keys refs, transformation, role_basis')
                continue
            pw = f'{w}.proofs.{col}'
            writer_text(p['transformation'], pw + '.transformation', rep, check_formula=False)
            writer_text(p['role_basis'], pw + '.role_basis', rep, check_formula=False)
            prefs = ref_list(p['refs'], pw + '.refs', rep, inv, allow_context=True, min_items=1)
            cells = [x for x in prefs if x.startswith('cell:')]
            ctx = [x for x in prefs if x.startswith('context:')]
            if not cells and ctx and col != 'L':
                rep.hold('CONTEXT_ONLY_PROOF_UNREPRESENTABLE', pw, 'Only L can be proven by context alone; hold this field.')
            if cells:
                texts = [cell_text_for_copy(inv, x, pw, rep, 'PROOF') for x in cells]
                if all(t is not None for t in texts):
                    joined = '\n'.join(texts)
                    if js_blank(joined):
                        rep.bad('PROOF_TEXT_BLANK', pw)
                    writer_text(joined, pw + ':copied', rep, check_formula=False)
                locator(inv, cells, pw + '.location', rep)
                if j in NUMERIC_COLS:
                    if len(cells) != 1 or ctx:
                        rep.bad('NUMERIC_PROOF_SINGLE_CELL', pw)
                    elif texts[0] is not None:
                        n = writer_numeric_raw(texts[0])
                        if n is None or n != float(v):
                            rep.bad('NUMERIC_EVIDENCE_MISMATCH', pw, {'value': v})
            if col == 'L' and ctx and not cells:
                sel = selection_evidence(inv, ctx, p)
                if PATHLIKE_RE.search(sel):
                    rep.bad('SELECTION_EVIDENCE_PATHLIKE', pw)
        # writer cross-field rules
        if it['group_id'] is None and (vals[0] is not None or vals[1] is not None):
            rep.bad('UNGROUPED_AB_MUST_BE_BLANK', w)
        g = groups.get(it['group_id'])
        if g is not None:
            if vals[0] is not None and vals[0] != g['name']:
                rep.bad('A_MUST_EQUAL_GROUP_NAME', w)
            if vals[1] is not None and vals[1] != g['specification']:
                rep.bad('B_MUST_EQUAL_GROUP_SPECIFICATION', w)
        def is_num(x):
            return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))
        if vals[5] is not None:
            qsel = rawsel.get('quantity') if isinstance(rawsel, dict) else None
            qref = qsel.get('refs') if isinstance(qsel, dict) else None
            n = writer_numeric_raw(raw_vals.get('quantity'))
            if n is None or not is_num(vals[5]) or n != float(vals[5]):
                rep.bad('SOURCE_QUANTITY_MISMATCH', w)
            elif isinstance(proofs.get('F'), dict) and proofs['F'].get('refs') != qref:
                rep.bad('F_PROOF_MUST_BE_RAW_QUANTITY_CELL', w)
        if vals[16] is not None:
            if inv.adoption != 'verified':
                rep.bad('Q_REQUIRES_VERIFIED_ADOPTION', w)
            n = writer_numeric_raw(raw_vals.get('unit_price'))
            if n is None or not is_num(vals[16]) or n != float(vals[16]):
                rep.bad('SOURCE_UNIT_PRICE_MISMATCH', w)
        if vals[4] is not None and vals[4] != raw_vals.get('unit'):
            rep.bad('SOURCE_UNIT_MISMATCH', w)
    if n_items < 1:
        rep.bad('DEMAND_ITEM_REQUIRED', 'items')
    if n_items > 2000 or n_comp > 2000 or n_items + n_comp > 2000:
        rep.bad('ITEM_LIMIT', 'items')

    # component links
    linked = {}
    for i, lk in enumerate(r['component_links']):
        w = f'component_links[{i}]'
        if not exact_keys(lk, ('component_id', 'parent_id', 'status', 'basis_quantity', 'basis_raw_ref',
                               'basis_unit_ref', 'refs', 'reason'), w, rep):
            continue
        cid = lk['component_id']
        if cid not in component_ids:
            rep.bad('LINK_COMPONENT_UNKNOWN', w)
            continue
        if cid in linked:
            rep.bad('DUPLICATE_COMPONENT_LINK', w)
        linked[cid] = lk
        writer_text(lk['reason'], w + '.reason', rep, check_formula=False)
        extra = ref_list(lk['refs'], w + '.refs', rep, inv)
        if lk['status'] == 'held':
            rep.hold('COMPONENT_LINK_HELD_WHOLE_EXPORT_HELD', w, 'A held link cannot be carried by the admitted writer.')
            continue
        if lk['status'] != 'supported':
            rep.bad('LINK_STATUS', w)
            continue
        if lk['parent_id'] not in demand_ids or lk['parent_id'] == cid:
            rep.bad('COMPONENT_PARENT_MUST_BE_DEMAND', w)
        bq = lk['basis_quantity']
        if isinstance(bq, bool) or not isinstance(bq, (int, float)) or not math.isfinite(float(bq)) or bq <= 0 or abs(bq) > MAX_SAFE:
            rep.bad('POSITIVE_BASIS_REQUIRED', w)
            bq = None
        refs = []
        for k in ('basis_raw_ref', 'basis_unit_ref'):
            x = lk[k]
            if not isinstance(x, str) or x not in inv.cells:
                rep.bad('BASIS_CELL_REF_REQUIRED', f'{w}.{k}')
            else:
                refs.append(x)
        if len(refs) == 2:
            t = cell_text_for_copy(inv, refs[0], w + '.basis_raw_ref', rep, 'BASIS')
            u = cell_text_for_copy(inv, refs[1], w + '.basis_unit_ref', rep, 'BASIS')
            if t is not None and bq is not None:
                n = writer_numeric_raw(t)
                if n is None or n != float(bq):
                    rep.bad('BASIS_LITERAL_MISMATCH', w)
            if u is not None:
                writer_text(u, w + '.basis_unit_ref:copied', rep, hold_formula=True)
            locator(inv, refs + [x for x in extra if x not in refs], w + '.basis_location', rep)
    for cid in component_ids - set(linked):
        rep.bad('COMPONENT_LINK_REQUIRED', cid)

    # source roles
    assigned = {}
    for i, sr in enumerate(r['source_roles']):
        w = f'source_roles[{i}]'
        if not exact_keys(sr, ('role', 'refs', 'reason'), w, rep):
            continue
        if sr['role'] not in ROLES:
            rep.bad('SOURCE_ROLE', w + '.role', list(ROLES))
        writer_text(sr['reason'], w + '.reason', rep, check_formula=False)
        for rf in ref_list(sr['refs'], w + '.refs', rep, inv, min_items=1):
            if rf in assigned:
                rep.bad('DUPLICATE_PRIMARY_ROLE', w, rf)
                continue
            if not Inventory.has_content(inv.cells[rf]):
                rep.bad('ROLE_FOR_EMPTY_CELL', w, rf)
                continue
            assigned[rf] = (sr['role'], sr['reason'])
    for rf, (role, _) in assigned.items():
        if role in CENSUS_ROLES:
            c = inv.cells[rf]
            vv = inv.cell_views(c['sheet'], c['address'])
            if not vv:
                rep.hold('CENSUS_CELL_OUTSIDE_VIEWS', 'source_roles', rf)
            covered.update(vv)
    for vid in inv.views:
        if vid not in covered:
            rep.hold('VIEW_SCOPE_UNACCOUNTED', 'views', vid)
    missing = [ref for ref, c in inv.cells.items() if Inventory.has_content(c) and ref not in assigned]
    if missing:
        rep.bad('UNCLASSIFIED_CONTENT_CELLS', 'source_roles', missing[:200] + (['...'] if len(missing) > 200 else []))
    return rep, {'response': r, 'assigned': assigned}


def selection_evidence(inv, ctx, proof):
    facts = [{'ref': x, 'namespace': inv.context[x]['namespace'], 'value': inv.context[x]['value'],
              'basis': inv.context[x]['basis']} for x in ctx]
    return json.dumps({'context': facts, 'role_basis': proof['role_basis']}, ensure_ascii=False, sort_keys=True)


def pack_transformation(proof, ctx):
    return json.dumps({'transformation': proof['transformation'], 'role_basis': proof['role_basis'],
                       'context_refs': ctx}, ensure_ascii=False, sort_keys=True)


def census_text(c):
    return json.dumps({'saved_type': c['saved_type'], 'state': c['state'], 'value': c['saved_value']},
                      ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


# ---------------------------------------------------------------- convert
def convert(inv, resp_raw):
    rep, ctx = check(inv, resp_raw)
    if rep.violations:
        return rep, None, None
    r = ctx['response']
    assigned = ctx['assigned']
    ledger = {ref: {'ref': ref, 'sheet': c['sheet'], 'address': c['address'], 'state': c['state'],
                    'saved_type': c['saved_type'], 'saved_value': c['saved_value'],
                    'primary_role': assigned.get(ref, (None,))[0], 'raw_uses': [], 'proof_uses': [],
                    'anchor_uses': [], 'group_uses': [], 'component_basis_uses': [], 'census': False,
                    'disposition': ('classified' if ref in assigned else
                                    ('empty_or_covered' if not Inventory.has_content(c) else 'unclassified'))}
              for ref, c in inv.cells.items()}
    groups = []
    for g in r['groups']:
        refs = g['anchor_refs'] + [x for x in g['name_refs'] + g['specification_refs'] if x not in g['anchor_refs']]
        for x in refs:
            ledger[x]['group_uses'].append(g['id'])
        anchor = json.dumps({'anchor_refs': g['anchor_refs'], 'name_refs': g['name_refs'],
                             'specification_refs': g['specification_refs'], 'relationship': g['relationship']},
                            ensure_ascii=False, sort_keys=True)
        groups.append({'id': g['id'], 'name': g['name'], 'specification': g['specification'],
                       'location': locator(inv, refs, 'group', Report()), 'anchor': anchor,
                       'quantity_basis': g['quantity_basis'], 'limitations': list(g['limitations'])})
    links = {lk['component_id']: lk for lk in r['component_links']}
    out_items, out_components = [], []
    for it in r['items']:
        anchor = json.dumps({'anchor_refs': it['anchor_refs']}, ensure_ascii=False)
        for x in it['anchor_refs']:
            ledger[x]['anchor_uses'].append(it['id'])
        raw, loc_refs = {}, list(it['anchor_refs'])
        for k in RAW:
            refs = it['raw_refs'][k]['refs']
            raw[k] = '\n'.join(inv.cells[x]['canonical_raw'] for x in refs) if refs else None
            for x in refs:
                ledger[x]['raw_uses'].append(f"{it['id']}.{k}")
                if x not in loc_refs:
                    loc_refs.append(x)
        evidence, nulls = {}, {}
        for j, col in enumerate(COLS):
            v, p = it['values'][j], it['proofs'][col]
            if v is None:
                nulls[col] = p['reason']
                continue
            cells = [x for x in p['refs'] if x.startswith('cell:')]
            cx = [x for x in p['refs'] if x.startswith('context:')]
            for x in cells:
                ledger[x]['proof_uses'].append(f"{it['id']}.{col}")
            if not cells:      # L by selection evidence only (checked)
                evidence[col] = {'selection_evidence': selection_evidence(inv, cx, p),
                                 'transformation': p['transformation']}
            else:
                evidence[col] = {'location': locator(inv, cells, 'proof', Report()), 'anchor': anchor,
                                 'raw_text': '\n'.join(inv.cells[x]['canonical_raw'] for x in cells),
                                 'transformation': pack_transformation(p, cx)}
        row = {'id': it['id'], 'group_id': it['group_id'], 'location': locator(inv, loc_refs, 'item', Report()),
               'anchor': anchor, 'raw': raw, 'values': copy.deepcopy(it['values']), 'evidence': evidence,
               'null_reasons': nulls, 'status': it['status'], 'review_reasons': list(it['review_reasons'])}
        if it['role'] == 'analysis_component':
            lk = links[it['id']]
            brefs = [lk['basis_raw_ref'], lk['basis_unit_ref']] + [x for x in lk['refs'] if x not in (lk['basis_raw_ref'], lk['basis_unit_ref'])]
            for x in brefs:
                ledger[x]['component_basis_uses'].append(it['id'])
            row['composition'] = {'parent_id': lk['parent_id'], 'basis_quantity': lk['basis_quantity'],
                                  'basis_unit': inv.cells[lk['basis_unit_ref']]['canonical_raw'],
                                  'basis_location': locator(inv, brefs, 'basis', Report()),
                                  'basis_raw': inv.cells[lk['basis_raw_ref']]['canonical_raw']}
            out_components.append(row)
        else:
            out_items.append(row)
    nonitems = []
    for ref, c in inv.cells.items():       # inventory order
        if ref in assigned and assigned[ref][0] in CENSUS_ROLES:
            role, reason = assigned[ref]
            nonitems.append({'location': locator(inv, [ref], 'census', Report()), 'kind': role, 'anchor': ref,
                             'text': census_text(c), 'reason': reason})
            ledger[ref]['census'] = True
    # values unchanged guard (type-exact)
    src_rows = [x for x in r['items'] if x['role'] == 'demand'] + [x for x in r['items'] if x['role'] == 'analysis_component']
    for src, dst in zip(src_rows, out_items + out_components):
        if src['id'] != dst['id'] or json.dumps(src['values'], ensure_ascii=False) != json.dumps(dst['values'], ensure_ascii=False) \
                or [type(x) for x in src['values']] != [type(x) for x in dst['values']]:
            raise Rejected('VALUE_CHANGED_DURING_COPY')
    ledger_obj = {'schema': 'cps.census-ledger.v1', 'case_id': inv.case_id, 'inventory_sha256': inv.sha256,
                  'response_sha256': sha256(resp_raw), 'positions': len(ledger), 'entries': list(ledger.values())}
    ledger_bytes = (json.dumps(ledger_obj, ensure_ascii=False, indent=1, allow_nan=False) + '\n').encode('utf-8')
    limitations = [s for s in r['limitations']]
    limitations += [s for s in inv.d['limitations']]
    limitations.append('Carrier produced by the 046b source-reference adapter: values copied from the frozen response; '
                       'raw/proof text copied from the pinned inventory; nonitem text is a typed JSON wrapper '
                       '{saved_type,state,value}; proof role_basis is packed in transformation JSON.')
    if len(limitations) > 500:
        raise Rejected('CARRIER_LIMITATION_COUNT')
    carrier = {
        'schema': 'cps.cached-xls-research-carrier.v1' if inv.kind == 'cached_xls' else 'cps.cached-xlsx-research-carrier.v1',
        'headers': list(HEADERS), 'case_id': inv.case_id, 'family_id': inv.family_id,
        'source': copy.deepcopy(inv.carrier_source),
        'metadata': {'response_schema': r['schema'], 'response_status': r['status'],
                     'inventory_sha256': inv.sha256, 'response_sha256': sha256(resp_raw),
                     'census_ledger_sha256': sha256(ledger_bytes), 'adapter': VERSION,
                     'representation_profile': PROFILE, 'source_adoption': inv.adoption},
        'groups': groups, 'items': out_items, 'components': out_components, 'nonitems': nonitems,
        'limitations': limitations}
    return rep, carrier, ledger_bytes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('check', 'convert'):
        p = sub.add_parser(name)
        p.add_argument('--inventory', required=True)
        p.add_argument('--response', required=True)
        if name == 'convert':
            p.add_argument('--out-dir', required=True)
    a = ap.parse_args(argv)
    inv_raw = Path(a.inventory).read_bytes()
    resp_raw = Path(a.response).read_bytes()
    try:
        inv = Inventory(inv_raw)
    except (Rejected, KeyError, TypeError) as e:
        print(json.dumps({'status': 'INVENTORY_REJECTED', 'error': repr(e)}, ensure_ascii=False))
        return 2
    if a.cmd == 'check':
        rep, _ = check(inv, resp_raw)
        status = 'PASS' if not rep.violations else 'REJECTED'
        print(json.dumps({'status': status, 'route': VERSION, 'inventory_sha256': inv.sha256,
                          'response_sha256': sha256(resp_raw), 'violations': rep.violations,
                          'warnings': rep.warnings}, ensure_ascii=False, indent=1))
        return 0 if status == 'PASS' else 1
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    rep, carrier, ledger = convert(inv, resp_raw)
    receipt = {'route': VERSION, 'inventory_sha256': inv.sha256, 'response_sha256': sha256(resp_raw),
               'violations': rep.violations, 'warnings': rep.warnings}
    if carrier is None:
        receipt['status'] = 'NOT_CARRIED'
        (out / 'ADAPTER_REJECTION.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(json.dumps({'status': 'NOT_CARRIED', 'violations': len(rep.violations)}))
        return 1
    cb = (json.dumps(carrier, ensure_ascii=False, indent=1, allow_nan=False) + '\n').encode('utf-8')
    (out / 'carrier.json').write_bytes(cb)
    (out / 'CENSUS_LEDGER.json').write_bytes(ledger)
    receipt.update(status='CARRIED_STRUCTURE_ONLY', carrier_sha256=sha256(cb), census_ledger_sha256=sha256(ledger),
                   items=len(carrier['items']), components=len(carrier['components']), groups=len(carrier['groups']),
                   nonitems=len(carrier['nonitems']), semantic_approval=False)
    (out / 'ADAPTER_RECEIPT.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: receipt[k] for k in ('status', 'carrier_sha256', 'items', 'components', 'nonitems')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
