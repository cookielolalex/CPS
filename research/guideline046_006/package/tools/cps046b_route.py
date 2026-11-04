"""CPS source-reference checker and carrier adapter, route v4 for candidate 046f (stdlib only).
v4 implements owner decision O13 (FIELD_ROLES R48, job inputs): L, M and N may be proven by
context references alone (context:case_identity, context:customer_name, context:project_name);
such proofs become selection_evidence in the carrier, and the Python writer port accepts
selection_evidence for L, M and N only. This is the one documented divergence from the archived
writer004 validateCarrier, which accepts selection_evidence for L only: a carrier with M/N
selection evidence is exported through research/export/writer_portable.py --mode v2. Every
other field proven only by context is still CONTEXT_ONLY_PROOF_UNREPRESENTABLE, and every other
check is unchanged from v3 (census roles excluded_supply/analysis_unlinked, R45/R46/R25 checks).

check-inventory : validate a source inventory before generation (writer source rules,
                  completeness, canonical text, unavoidable holds).
check           : validate a semantic response against its pinned inventory, then build the
                  carrier exactly as convert would and run a Python port of writer004
                  validateCarrier/prepareMatrices on it. Prints every violation.
convert         : same checks; if clean, write carrier.json for writer004 plus a complete
                  positional CENSUS_LEDGER.json. If not clean, still write the ledger and a
                  rejection receipt (the response and census are retained).

The adapter only validates and copies. It never selects references, edits a value,
shortens a name, repairs a response or reads anything except the files it is given.
Violation categories: invalid (correct the response from the source), field_must_be_null
(the cited source cannot be carried for this field: leave the field/raw selection empty
with a specific reason; never alter the source meaning), unrepresentable_hold (a true
answer cannot be carried by the admitted writer: keep it; the export is held).
"""
import argparse, copy, hashlib, json, math, re, sys
from decimal import Decimal
from pathlib import Path

VERSION = 'cps046f-route.v4'
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
         'financial_summary', 'commercial_note', 'document_reference', 'footer', 'unresolved',
         'excluded_supply', 'analysis_unlinked')
CENSUS_ROLES = ('item_identifier', 'header', 'section', 'financial_summary', 'commercial_note',
                'document_reference', 'footer', 'unresolved', 'excluded_supply', 'analysis_unlinked')
CONTENT_ROLES = ('demand_content', 'analysis_content')
GROUP_RELATIONS = ('contractual_group', 'physical_enclosure', 'contractual_and_physical', 'unresolved')
LIMIT = 20 * 1024 * 1024
# O13 / FIELD_ROLES R48: job-input fields that may be proven by context alone (selection_evidence).
# writer004 validateCarrier allows only L; the M/N relaxation is the route v4 divergence.
SELECTION_COLS = ('L', 'M', 'N')
MAX_SAFE = 9007199254740991
ID_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', re.ASCII)
CELL_REF_RE = re.compile(r'cell:S([1-9][0-9]{0,3})!([A-Z]{1,3})([1-9][0-9]{0,6})', re.ASCII)
CONTEXT_REF_RE = re.compile(r'context:[a-z0-9_]{1,64}', re.ASCII)
ADDR_RE = re.compile(r'([A-Z]{1,3})([1-9][0-9]{0,6})', re.ASCII)
# JavaScript String.prototype.trim / \s whitespace (writer004 runs in Node).
JS_WS = '\t\n\x0b\x0c\r                  　﻿'
CTRL_RE = re.compile('[\u0000-\u0008\u000b\u000c\u000e-\u001f]')
FORMULA_RE = re.compile('^[' + re.escape(JS_WS) + ']*[=+@-]')
# JS \d is ASCII-only: Unicode digits must not pass (re.ASCII).
NUMERIC_TEXT_RE = re.compile(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', re.ASCII)
PATHLIKE_RE = re.compile(r'(?:[A-Za-z]:[\\/]|\\\\|file://|https?://)', re.I)
META_KEY_RE = re.compile(r'^(?:paths?|files?|uris?|urls?|callbacks?|scripts?|formulas?|sources?|source_path|source_file|source_url|source_uri|annex|annexes|attachments?)$', re.I)
FORBIDDEN_PATH_RE = re.compile(r'(?:未填|已填|電機圖|板金|鈑金|歷史|(?:^|[\\/_. -])(?:ok|targets?|reserved|drawings?|histor(?:y|ical|ies))(?=[\\/_. -]|$))', re.I)
DEVICE_RE = re.compile(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)


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

    def parse_float(t):
        f = float(t)
        if not math.isfinite(f):
            raise Rejected('NONFINITE_NUMBER')
        return f

    def parse_int(t):
        n = int(t)
        if abs(n) > MAX_SAFE:
            raise Rejected('UNSAFE_INTEGER')
        return n
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=bad_constant,
                          parse_float=parse_float, parse_int=parse_int)
    except UnicodeDecodeError:
        raise Rejected('UTF8_REQUIRED')
    except (json.JSONDecodeError, RecursionError, ValueError) as e:
        if isinstance(e, Rejected):
            raise
        raise Rejected('INVALID_JSON:' + str(e)[:120])


def js_len(s):
    return len(s.encode('utf-16-le', 'surrogatepass')) // 2


def js_blank(s):
    return s.strip(JS_WS) == ''


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x)) and abs(x) <= MAX_SAFE


def canonical_number(v):
    """R2: plain base-10 text of a finite binary64 value; no exponent/grouping."""
    f = float(v)
    if not math.isfinite(f):
        return None
    s = format(Decimal(repr(f)), 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def writer_numeric_raw(text):
    """Port of writer004 numericRaw: float, or None where the writer rejects."""
    if not isinstance(text, str) or js_len(text) > 30000 or CTRL_RE.search(text) or js_blank(text):
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


def parse_addr(a):
    m = ADDR_RE.fullmatch(a) if isinstance(a, str) else None
    if not m:
        return None
    c, r = col_number(m[1]), int(m[2])
    if c > 16384 or r > 1048576:
        return None
    return c, r


def parse_range(r):
    if not isinstance(r, str):
        return None
    a = r.split(':')
    if len(a) not in (1, 2):
        return None
    lo, hi = parse_addr(a[0]), parse_addr(a[-1])
    if not lo or not hi or lo[0] > hi[0] or lo[1] > hi[1]:
        return None
    return lo, hi


class Report:
    def __init__(self):
        self.violations = []
        self.warnings = []

    def add(self, code, where, detail, category):
        v = {'code': code, 'where': where, 'category': category}
        if detail is not None:
            v['detail'] = detail
        self.violations.append(v)

    def bad(self, code, where, detail=None):
        self.add(code, where, detail, 'invalid')

    def null(self, code, where, detail=None):
        self.add(code, where, detail, 'field_must_be_null')

    def hold(self, code, where, detail=None):
        self.add(code, where, detail, 'unrepresentable_hold')

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


def writer_text(v, where, rep, allow_blank=False, check_formula=True):
    if not isinstance(v, str):
        rep.bad('STRING_REQUIRED', where)
        return False
    ok = True
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in v):
        rep.bad('LONE_SURROGATE', where)
        ok = False
    if not allow_blank and js_blank(v):
        rep.bad('NONBLANK_STRING_REQUIRED', where)
        ok = False
    if js_len(v) > 30000:
        rep.hold('STRING_TOO_LONG_FOR_WRITER', where)
        ok = False
    if CTRL_RE.search(v):
        rep.hold('CONTROL_CHARACTER_UNREPRESENTABLE', where)
        ok = False
    if check_formula and FORMULA_RE.match(v):
        rep.hold('FORMULA_LIKE_STRING_WHOLE_OUTPUT_HELD', where, {'retained_value': v})
        ok = False
    return ok


def ident(v, where, rep):
    if not isinstance(v, str) or not ID_RE.fullmatch(v):
        rep.bad('ID_REQUIRED', where, {'pattern': ID_RE.pattern})
        return False
    return True


# ---------------------------------------------------------------- writer004 port
class WriterReject(Exception):
    def __init__(self, code, where):
        super().__init__(f'{code}: {where}')
        self.code, self.where = code, where


def _fail(code, where):
    raise WriterReject(code, where)


def _obj(v, p):
    if not isinstance(v, dict):
        _fail('OBJECT_REQUIRED', p)


def _keys(v, ks, p):
    _obj(v, p)
    if sorted(v) != sorted(ks):
        _fail('EXACT_KEYS_REQUIRED', p)


def _str(v, p, empty=False):
    if not isinstance(v, str) or (not empty and js_blank(v)) or js_len(v) > 30000 or CTRL_RE.search(v):
        _fail('STRING_REQUIRED', p)


def _maybe(v, p):
    if v is not None:
        _str(v, p, True)


def _strings(v, p):
    if not isinstance(v, list) or len(v) > 500:
        _fail('STRING_ARRAY_REQUIRED', p)
    for i, s in enumerate(v):
        _str(s, f'{p}[{i}]')


def _id(v, p):
    _str(v, p)
    if not ID_RE.fullmatch(v):
        _fail('ID_REQUIRED', p)


def _numeric(v, p):
    if not is_num(v):
        _fail('FINITE_SAFE_NUMBER_REQUIRED', p)


def _numeric_raw(v, p):
    _str(v, p)
    t = v.strip(JS_WS)
    if not NUMERIC_TEXT_RE.fullmatch(t):
        _fail('UNSUPPORTED_NUMERIC_TEXT', p)
    n = float(t.replace(',', ''))
    _numeric(n, p)
    return n


def _locator(v, source, p):
    _keys(v, ['sheet', 'cells', 'views'], p)
    _str(v['sheet'], p)
    cells, views = v['cells'], v['views']
    if (not isinstance(cells, list) or not cells or len(cells) > 1000 or not isinstance(views, list) or not views
            or len(views) > 1000 or len(set(map(str, cells))) != len(cells) or len(set(map(str, views))) != len(views)):
        _fail('LOCATION_SHAPE', p)
    bb = []
    for n in views:
        if not isinstance(n, int) or isinstance(n, bool) or n < 1 or n > len(source['views']):
            _fail('VIEW_BOUNDS', p)
        view = source['views'][n - 1]
        if view['sheet'] != v['sheet']:
            _fail('SHEET_VIEW_MISMATCH', p)
        bb.append(parse_range(view['range']))
    cc = []
    for a in cells:
        x = parse_addr(a)
        if x is None:
            _fail('CELL_ADDRESS', 'location')
        cc.append(x)
    for c, r in cc:
        if not any(lo[0] <= c <= hi[0] and lo[1] <= r <= hi[1] for lo, hi in bb):
            _fail('CELL_OUTSIDE_VIEWS', p)
    for lo, hi in bb:
        if not any(lo[0] <= c <= hi[0] and lo[1] <= r <= hi[1] for c, r in cc):
            _fail('UNRELATED_VIEW', p)


def _source_shape(s, p):
    _keys(s, ['kind', 'path', 'sha256', 'views'], p)
    if s['kind'] not in ('cached_xlsx', 'cached_xls'):
        _fail('SOURCE_KIND', p)
    _str(s['path'], p + '.path')
    path = s['path']
    import unicodedata
    if len(path) > 2048 or unicodedata.normalize('NFC', path) != path:
        _fail('NONCANONICAL_UNICODE_PATH', p)
    if not re.match(r'^[A-Z]:\\', path) or '/' in path:
        _fail('CANONICAL_LOCAL_ABSOLUTE_PATH_REQUIRED', p)
    parts = path[3:].split('\\')
    if not parts or any(not x or x in ('.', '..') or x[-1] in ' .' or re.search(r'[<>:"|?*\x00-\x1f]', x) or DEVICE_RE.match(x) for x in parts):
        _fail('NONCANONICAL_PATH_COMPONENT', p)
    import ntpath
    if ntpath.normpath(path) != path or ntpath.splitext(path)[1].lower() != ('.xls' if s['kind'] == 'cached_xls' else '.xlsx'):
        _fail('SOURCE_KIND_EXTENSION_MISMATCH', p)
    if FORBIDDEN_PATH_RE.search(path):
        _fail('FORBIDDEN_SOURCE_PATH', p)
    if not isinstance(s['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', s['sha256']):
        _fail('SHA256_REQUIRED', p)
    if not isinstance(s['views'], list) or not 1 <= len(s['views']) <= 1000:
        _fail('VIEWS_REQUIRED', p)
    for i, v in enumerate(s['views']):
        _keys(v, ['id', 'sheet', 'range'], p)
        if v['id'] != i + 1:
            _fail('VIEW_ID', p)
        _str(v['sheet'], p)
        if parse_range(v['range']) is None:
            _fail('RANGE_REQUIRED', 'source')


def _metadata(v, p='metadata', depth=0):
    if depth > 12:
        _fail('METADATA_TOO_DEEP', p)
    if v is None or isinstance(v, bool):
        return
    if isinstance(v, (int, float)):
        _numeric(v, p)
        return
    if isinstance(v, str):
        _str(v, p, True)
        if PATHLIKE_RE.search(v):
            _fail('EXTRA_SOURCE_REFERENCE', p)
        return
    if isinstance(v, list):
        if len(v) > 1000:
            _fail('METADATA_TOO_LARGE', p)
        for i, x in enumerate(v):
            _metadata(x, f'{p}[{i}]', depth + 1)
        return
    _obj(v, p)
    for k, x in v.items():
        if META_KEY_RE.match(k):
            _fail('EXTRA_SOURCE_REFERENCE', f'{p}.{k}')
        _metadata(x, f'{p}.{k}', depth + 1)


def _js(v):
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def validate_carrier_port(c):
    """Python port of writer004 validateCarrier + prepareMatrices review-cell checks."""
    _keys(c, ['schema', 'headers', 'case_id', 'family_id', 'source', 'metadata', 'groups', 'items', 'components', 'nonitems', 'limitations'], 'carrier')
    kind = c['source'].get('kind') if isinstance(c['source'], dict) else None
    if c['schema'] != ('cps.cached-xls-research-carrier.v1' if kind == 'cached_xls' else 'cps.cached-xlsx-research-carrier.v1'):
        _fail('SCHEMA_MISMATCH', 'schema')
    if c['headers'] != HEADERS:
        _fail('EXACT_HEADERS_REQUIRED', 'headers')
    _id(c['case_id'], 'case_id'); _id(c['family_id'], 'family_id'); _source_shape(c['source'], 'source')
    _obj(c['metadata'], 'metadata'); _metadata(c['metadata']); _strings(c['limitations'], 'limitations')
    if not isinstance(c['groups'], list) or len(c['groups']) > 2000:
        _fail('GROUPS_REQUIRED', 'groups')
    if not isinstance(c['items'], list) or not 1 <= len(c['items']) <= 2000:
        _fail('ITEMS_REQUIRED', 'items')
    if not isinstance(c['nonitems'], list) or len(c['nonitems']) > 5000:
        _fail('NONITEMS_REQUIRED', 'nonitems')
    if not isinstance(c['components'], list) or len(c['components']) > 2000:
        _fail('COMPONENTS_REQUIRED', 'components')
    src = c['source']
    groups, seen, covered = {}, set(), set()
    for i, g in enumerate(c['groups']):
        p = f'groups[{i}]'
        _keys(g, ['id', 'name', 'specification', 'location', 'anchor', 'quantity_basis', 'limitations'], p); _id(g['id'], p + '.id')
        if g['id'] in groups:
            _fail('DUPLICATE_GROUP_ID', g['id'])
        _maybe(g['name'], p + '.name'); _maybe(g['specification'], p + '.specification'); _locator(g['location'], src, p)
        covered.update(g['location']['views'])
        _str(g['anchor'], p + '.anchor'); _str(g['quantity_basis'], p + '.quantity_basis'); _strings(g['limitations'], p + '.limitations')
        if g['name'] is None and not g['limitations']:
            _fail('UNRESOLVED_GROUP_REASON_REQUIRED', p)
        groups[g['id']] = g
    alls = c['items'] + c['components']
    for i, r in enumerate(alls):
        p = f'items[{i}]'
        ks = ['id', 'group_id', 'location', 'anchor', 'raw', 'values', 'evidence', 'null_reasons', 'status', 'review_reasons'] + (['composition'] if i >= len(c['items']) else [])
        _keys(r, ks, p); _id(r['id'], p + '.id')
        if r['id'] in seen:
            _fail('DUPLICATE_ITEM_ID', r['id'])
        seen.add(r['id'])
        if r['group_id'] is not None and r['group_id'] not in groups:
            _fail('UNKNOWN_GROUP_ID', p)
        _locator(r['location'], src, p); covered.update(r['location']['views']); _str(r['anchor'], p + '.anchor')
        _keys(r['raw'], list(RAW), p + '.raw')
        for k, v in r['raw'].items():
            _maybe(v, f'{p}.raw.{k}')
        if not isinstance(r['values'], list) or len(r['values']) != 17:
            _fail('SEVENTEEN_VALUES_REQUIRED', p)
        if r['status'] not in ('research_draft', 'held'):
            _fail('REVIEW_STATUS_REQUIRED', p)
        _strings(r['review_reasons'], p + '.review_reasons')
        if r['status'] == 'held' and not r['review_reasons']:
            _fail('HELD_REASON_REQUIRED', p)
        if r['values'][2] is None and r['status'] != 'held':
            _fail('UNRESOLVED_ITEM_MUST_BE_HELD', p)
        _obj(r['evidence'], p + '.evidence'); _obj(r['null_reasons'], p + '.null_reasons')
        req_ev, req_null = [], []
        for j, v in enumerate(r['values']):
            col, vp = COLS[j], f'{p}.values.{COLS[j]}'
            if v is None:
                req_null.append(col)
                _str(r['null_reasons'].get(col), f'{p}.null_reasons.{col}')
                continue
            if j in BLANK_COLS:
                _fail('PURCHASE_PRICE_MUST_BE_BLANK', vp)
            if j in NUMERIC_COLS:
                _numeric(v, vp)
            else:
                _str(v, vp)
            if isinstance(v, str) and FORMULA_RE.match(v):
                _fail('FORMULA_STRING_FORBIDDEN', vp)
            req_ev.append(col)
            e = r['evidence'].get(col)
            _obj(e, f'{p}.evidence.{col}')
            if 'selection_evidence' in e:
                if col not in SELECTION_COLS:       # writer004: col !== 'L' (O13 relaxation adds M, N)
                    _fail('SELECTION_ONLY_ENGINEERING_ID', vp)
                _keys(e, ['selection_evidence', 'transformation'], f'{p}.evidence.{col}')
                _str(e['selection_evidence'], vp + '.selection_evidence'); _str(e['transformation'], vp + '.transformation')
                if PATHLIKE_RE.search(e['selection_evidence']):
                    _fail('EXTRA_SOURCE_REFERENCE', vp)
            else:
                _keys(e, ['location', 'anchor', 'raw_text', 'transformation'], f'{p}.evidence.{col}')
                _locator(e['location'], src, vp); _str(e['anchor'], vp + '.anchor'); _str(e['raw_text'], vp + '.raw_text'); _str(e['transformation'], vp + '.transformation')
                if j in NUMERIC_COLS and _numeric_raw(e['raw_text'], vp) != float(v):
                    _fail('NUMERIC_EVIDENCE_MISMATCH', vp)
        _keys(r['evidence'], req_ev, p + '.evidence'); _keys(r['null_reasons'], req_null, p + '.null_reasons')
        if r['group_id'] is None and (r['values'][0] is not None or r['values'][1] is not None):
            _fail('UNGROUPED_AB_MUST_BE_BLANK', p)
        if r['values'][5] is not None and _numeric_raw(r['raw']['quantity'], p + '.raw.quantity') != float(r['values'][5]):
            _fail('SOURCE_QUANTITY_MISMATCH', p)
        if r['values'][16] is not None and _numeric_raw(r['raw']['unit_price'], p + '.raw.unit_price') != float(r['values'][16]):
            _fail('SOURCE_UNIT_PRICE_MISMATCH', p)
        if r['values'][4] is not None and r['values'][4] != r['raw']['unit']:
            _fail('SOURCE_UNIT_MISMATCH', p)
    details = {r['id'] for r in c['items']}
    for r in c['components']:
        x = r['composition']
        _keys(x, ['parent_id', 'basis_quantity', 'basis_unit', 'basis_location', 'basis_raw'], 'composition'); _id(x['parent_id'], 'composition')
        if x['parent_id'] not in details or x['parent_id'] == r['id']:
            _fail('COMPONENT_PARENT_MUST_BE_DETAIL', r['id'])
        _numeric(x['basis_quantity'], r['id'])
        if x['basis_quantity'] <= 0 or _numeric_raw(x['basis_raw'], r['id']) != float(x['basis_quantity']):
            _fail('POSITIVE_LITERAL_BASIS_REQUIRED', r['id'])
        _str(x['basis_unit'], r['id'])
        if FORMULA_RE.match(x['basis_unit']):
            _fail('FORMULA_STRING_FORBIDDEN', r['id'])
        _locator(x['basis_location'], src, r['id'])
    for i, n in enumerate(c['nonitems']):
        p = f'nonitems[{i}]'
        _keys(n, ['location', 'kind', 'anchor', 'text', 'reason'], p); _locator(n['location'], src, p); covered.update(n['location']['views'])
        for k in ('kind', 'anchor', 'reason'):
            _str(n[k], f'{p}.{k}')
        _str(n['text'], p + '.text', True)
    for v in range(1, len(src['views']) + 1):
        if v not in covered:
            _fail('VIEW_SCOPE_UNACCOUNTED', str(v))
    # prepareMatrices review-sheet cells: <=32767 UTF-16 units and not formula-like
    cells = [_js(src)] + [x for k, v in c['metadata'].items() for x in (_js(k), _js(v))] + [_js(v) for v in c['limitations']]
    for g in c['groups']:
        cells += [g['id'], _js(g['location']), _js(g['anchor']), _js(g)]
    for i, r in enumerate(alls):
        loc, anc = _js(r['location']), _js(r['anchor'])
        comp = r.get('composition')
        rows = i + 2 if i < len(c['items']) else i - len(c['items']) + 2
        cells += [r['id'], loc, anc, _js({'group_id': r['group_id'], 'sheet': '未填研究草稿' if i < len(c['items']) else '組成參考',
                                          'saved_row': rows, 'composition': comp, 'values': r['values']}), _js(r['review_reasons'])]
        cells += [_js(v) for v in r['raw'].values()]
        for v in r['evidence'].values():
            cells += [_js(v.get('location')) if v.get('location') else '', _js(v.get('anchor', '已核對工程選取')), _js(v), _js(v['transformation'])]
        cells += [_js(v) for v in r['null_reasons'].values()] + [_js(v) for v in r['review_reasons']]
    for n in c['nonitems']:
        cells += [_js(n['location']), _js(n['anchor']), _js(n['text']), _js(n['reason'])]
    for k, v in enumerate(cells):
        if isinstance(v, str) and (js_len(v) > 32767 or FORMULA_RE.match(v)):
            _fail('REVIEW_CELL_UNSAFE_OR_TOO_LONG', str(k))
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
            rng = parse_range(v['range'])
            if v['id'] != i + 1 or rng is None:
                raise Rejected('INVENTORY_VIEW')
            self.views[v['id']] = (v['sheet'], rng)
        if [{k: v[k] for k in ('id', 'sheet', 'range')} for v in d['views']] != cs['views']:
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
        if sum(s['rows'] * s['columns'] for s in d['sheets'] if s['in_scope']) != len(self.cells):
            raise Rejected('INVENTORY_INCOMPLETE_CENSUS')
        self.context = {}
        for x in d['context_facts']:
            if x['ref'] in self.context or not CONTEXT_REF_RE.fullmatch(x['ref']):
                raise Rejected('INVENTORY_CONTEXT_REF')
            self.context[x['ref']] = x

    def cell_views(self, sheet, addr):
        c, r = parse_addr(addr)
        return [vid for vid, (s, (lo, hi)) in self.views.items()
                if s == sheet and lo[0] <= c <= hi[0] and lo[1] <= r <= hi[1]]

    def rc(self, ref):
        c = self.cells[ref]
        return c['row'], c['col']

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


def check_inventory(inv):
    rep = Report()
    ident(inv.case_id, 'case_id', rep)
    ident(inv.family_id, 'family_id', rep)
    try:
        _source_shape(inv.carrier_source, 'carrier_source')
    except WriterReject as e:
        rep.bad('WRITER_SOURCE_' + e.code, e.where)
    for ref, c in inv.cells.items():
        if c['saved_type'] == 'number' and c['state'] in ('literal', 'cached_formula'):
            if c['canonical_raw'] != canonical_number(c['saved_value']):
                rep.bad('CANONICAL_NUMBER_MISMATCH', ref)
        elif c['saved_type'] == 'text' and c['state'] in ('literal', 'cached_formula') and c['usable_for_raw']:
            if c['canonical_raw'] != c['saved_value']:
                rep.bad('CANONICAL_TEXT_MISMATCH', ref)
        if c['canonical_raw'] is not None and not c['usable_for_raw']:
            rep.bad('CANONICAL_ON_UNUSABLE_CELL', ref)
        if Inventory.has_content(c) and not inv.cell_views(c['sheet'], c['address']):
            rep.hold('CONTENT_CELL_OUTSIDE_VIEWS', ref)
    for vid, (sheet, (lo, hi)) in inv.views.items():
        if not any(Inventory.has_content(c) and c['sheet'] == sheet and lo[0] <= c['col'] <= hi[0] and lo[1] <= c['row'] <= hi[1] for c in inv.cells.values()):
            rep.hold('VIEW_WITHOUT_CONTENT', str(vid))
    formula_like = [ref for ref, c in inv.cells.items() if isinstance(c['canonical_raw'], str) and FORMULA_RE.match(c['canonical_raw'])]
    if formula_like:
        rep.warn('FORMULA_LIKE_SOURCE_TEXT', 'cells', {'count': len(formula_like),
                 'note': 'A value copied verbatim from these cells would hold the whole export.'})
    return rep


# ---------------------------------------------------------------- checks
def ref_list(v, where, rep, inv, allow_context=False, min_items=0):
    if not isinstance(v, list):
        rep.bad('ARRAY_REQUIRED', where)
        return []
    if len(v) < min_items:
        rep.bad('REFS_REQUIRED', where)
    strs = [x for x in v if isinstance(x, str)]
    if len(set(strs)) != len(v):
        rep.bad('DUPLICATE_OR_NONSTRING_REF', where)
    good = []
    for i, r in enumerate(strs):
        w = f'{where}[{i}]'
        if r.startswith('context:') and allow_context:
            if r not in inv.context:
                rep.bad('UNKNOWN_CONTEXT_REF', w, r)
                continue
        elif r not in inv.cells:
            rep.bad('UNKNOWN_CELL_REF', w, r)
            continue
        if r not in good:
            good.append(r)
    return good


def copy_text(inv, ref, where, rep, purpose):
    c = inv.cells[ref]
    if c['canonical_raw'] is None and not Inventory.has_content(c):
        rep.bad('EMPTY_CELL_CITED_IN_' + purpose, where, {'ref': ref, 'state': c['state']})
        return None
    if not c['usable_for_raw'] or c['canonical_raw'] is None:
        rep.null('SOURCE_CELL_NOT_CARRIABLE_IN_' + purpose, where,
                 {'ref': ref, 'state': c['state'], 'saved_type': c['saved_type'], 'reason': c['raw_limit_reason'],
                  'action': 'leave this field or raw selection empty with a specific reason; the cell stays in the census'})
        return None
    return c['canonical_raw']


def locator(inv, refs, where, rep):
    cells = [inv.cells[r] for r in refs if r in inv.cells]
    if len(cells) != len(refs) or not cells:
        return None
    if len({c['sheet'] for c in cells}) != 1:
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
        rep.hold('LOCATION_TOO_LARGE_FOR_WRITER', where)
        return None
    return {'sheet': sheet, 'cells': addrs, 'views': sorted(views)}


def check(inv, resp_raw):
    rep = Report()
    try:
        return _check(inv, resp_raw, rep)
    except Exception as e:      # never crash: report the failure as a violation
        rep.bad('CHECKER_COULD_NOT_EVALUATE', 'response', f'{type(e).__name__}: {str(e)[:200]}')
        return rep, None


def _check(inv, resp_raw, rep):
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
        rep.hold('TOO_MANY_LIMITATIONS_FOR_WRITER', 'limitations')
    for i, s in enumerate(r['limitations']):
        writer_text(s, f'limitations[{i}]', rep, check_formula=False)
    if not r['items']:
        rep.bad('ITEMS_REQUIRED', 'items')
    ids, covered, used = set(), set(), {}

    def cover(loc):
        if loc:
            covered.update(loc['views'])

    def use(ref, what):
        used.setdefault(ref, []).append(what)

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
        if (g['name'] is not None) != bool(names):
            rep.bad('GROUP_NAME_PROOF_MISMATCH', w, 'name and name_refs must be both present or both absent')
        if (g['specification'] is not None) != bool(specs):
            rep.bad('GROUP_SPEC_PROOF_MISMATCH', w, 'specification and specification_refs must be both present or both absent')
        for rr in names + specs:
            copy_text(inv, rr, w, rep, 'GROUP_PROOF')
        writer_text(g['quantity_basis'], w + '.quantity_basis', rep, check_formula=False)
        if not isinstance(g['limitations'], list):
            rep.bad('ARRAY_REQUIRED', w + '.limitations')
        else:
            if len(g['limitations']) > 500:
                rep.hold('TOO_MANY_GROUP_LIMITATIONS_FOR_WRITER', w)
            for j, s in enumerate(g['limitations']):
                writer_text(s, f'{w}.limitations[{j}]', rep, check_formula=False)
            if g['name'] is None and not g['limitations']:
                rep.bad('UNRESOLVED_GROUP_REASON_REQUIRED', w)
        for x in anchors + names + specs:
            use(x, 'group:' + str(g['id']))
        if anchors:
            cover(locator(inv, anchors + [x for x in names + specs if x not in anchors], w + '.location', rep))

    # items
    items, demand_ids, component_ids = {}, set(), set()
    ident_owner, raw_owner, desc_anchor = {}, {}, []
    o13 = []        # item.column of M/N proven by job-input context alone (selection_evidence)
    for i, it in enumerate(r['items']):
        w = f'items[{i}]'
        if not exact_keys(it, ('id', 'role', 'group_id', 'status', 'values', 'proofs', 'raw_refs',
                               'anchor_refs', 'review_reasons'), w, rep):
            continue
        iid = it['id']
        if ident(iid, w + '.id', rep):
            if iid in ids:
                rep.bad('DUPLICATE_ID', w + '.id', iid)
            ids.add(iid)
            items[iid] = it
        if it['role'] == 'demand':
            demand_ids.add(iid)
        elif it['role'] == 'analysis_component':
            component_ids.add(iid)
        else:
            rep.bad('ITEM_ROLE', w + '.role')
        if it['role'] == 'analysis_component' and (it['group_id'] is not None or (isinstance(it.get('values'), list)
                                                   and len(it['values']) == 17 and (it['values'][0] is not None or it['values'][1] is not None))):
            rep.bad('COMPONENT_GROUP_FORBIDDEN', w, 'analysis components never carry A, B or a group (FIELD_ROLES R25)')
        if it['group_id'] is not None and (not isinstance(it['group_id'], str) or it['group_id'] not in groups):
            rep.bad('UNKNOWN_GROUP_ID', w + '.group_id')
        if it['status'] not in ('research_draft', 'held'):
            rep.bad('ITEM_STATUS', w + '.status', ['research_draft', 'held'])
        if not isinstance(it['review_reasons'], list):
            rep.bad('ARRAY_REQUIRED', w + '.review_reasons')
        else:
            if len(it['review_reasons']) > 500:
                rep.hold('TOO_MANY_REVIEW_REASONS_FOR_WRITER', w)
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
        anchors = ref_list(it['anchor_refs'], w + '.anchor_refs', rep, inv, min_items=1)
        for x in anchors:
            use(x, f'{iid}.anchor')
            if x in ident_owner and ident_owner[x] != iid:
                rep.bad('ANCHOR_SHARED_ACROSS_ITEMS', w, x)
            ident_owner.setdefault(x, iid)
        if anchors and len({inv.rc(x)[0] for x in anchors}) != 1:
            rep.bad('ANCHORS_NOT_ON_ONE_ROW', w)
        raw_vals, loc_refs, raw_cells = {}, list(anchors), {}
        rawsel = it['raw_refs']
        if exact_keys(rawsel, RAW, w + '.raw_refs', rep):
            for k in RAW:
                sw = f'{w}.raw_refs.{k}'
                sel = rawsel[k]
                if not exact_keys(sel, ('refs', 'reason_if_empty'), sw, rep):
                    continue
                refs = ref_list(sel['refs'], sw + '.refs', rep, inv)
                raw_cells[k] = refs
                if k in SINGLE_RAW and len(sel['refs']) > 1:
                    rep.bad('SINGLE_CELL_RAW_FIELD', sw)
                if sel['refs'] and sel['reason_if_empty'] is not None:
                    rep.bad('REASON_ONLY_FOR_EMPTY_SELECTION', sw)
                if not sel['refs'] and (not isinstance(sel['reason_if_empty'], str) or js_blank(sel['reason_if_empty'])):
                    rep.bad('EMPTY_SELECTION_REASON_REQUIRED', sw)
                if k in ('description', 'remarks') and refs != sorted(refs, key=inv.rc):
                    rep.bad('RAW_STREAM_NOT_ROW_MAJOR', sw)
                parts = [copy_text(inv, x, sw, rep, 'RAW') for x in refs]
                if refs and all(t is not None for t in parts):
                    raw_vals[k] = '\n'.join(parts)
                    writer_text(raw_vals[k], sw + ':copied', rep, allow_blank=True, check_formula=False)
                elif not sel['refs']:
                    raw_vals[k] = None
                for x in refs:
                    use(x, f'{iid}.raw.{k}')
                    if x not in loc_refs:
                        loc_refs.append(x)
                    if k == 'description':
                        if x in ident_owner and ident_owner[x] != iid:
                            rep.bad('DESCRIPTION_CELL_SHARED_ACROSS_ITEMS', sw, x)
                        ident_owner.setdefault(x, iid)
                    elif x in raw_owner and raw_owner[x] != iid:
                        rep.warn('RAW_CELL_SHARED_ACROSS_ITEMS', sw, x)
                    raw_owner.setdefault(x, iid)
            others = {x for k in RAW if k != 'description' for x in raw_cells.get(k, [])}
            overlap = [x for x in raw_cells.get('description', []) if x in others]
            if overlap:
                rep.bad('DESCRIPTION_INCLUDES_EXCLUDED_CELL', w + '.raw_refs.description', overlap)
            # an anchor may be the first description cell only when it is not an item-number cell
            desc_anchor += [(w, x) for x in raw_cells.get('description', []) if x in anchors]
            item_rows = [inv.rc(x)[0] for x in loc_refs]
            if anchors and item_rows and inv.rc(anchors[0])[0] != min(item_rows):
                rep.bad('ANCHOR_NOT_ON_FIRST_ROW', w)
        if anchors:
            cover(locator(inv, loc_refs, w + '.location', rep))
        proofs = it['proofs']
        if not exact_keys(proofs, tuple(COLS), w + '.proofs', rep):
            continue
        for j, col in enumerate(COLS):
            v, p, vw, pw = vals[j], proofs[col], f'{w}.values.{col}', f'{w}.proofs.{col}'
            if v is None:
                if not (isinstance(p, dict) and set(p) == {'reason'}):
                    rep.bad('NULL_PROOF_REQUIRED', pw)
                else:
                    writer_text(p['reason'], pw + '.reason', rep, check_formula=False)
                continue
            if j in BLANK_COLS:
                rep.bad('PURCHASE_PRICE_MUST_BE_BLANK', vw)
                continue
            if j in NUMERIC_COLS:
                if not is_num(v):
                    rep.bad('FINITE_SAFE_NUMBER_REQUIRED', vw)
                    continue
            else:
                writer_text(v, vw, rep)
            if not (isinstance(p, dict) and set(p) == {'refs', 'transformation', 'role_basis'}):
                rep.bad('NONNULL_PROOF_REQUIRED', pw, 'keys refs, transformation, role_basis')
                continue
            writer_text(p['transformation'], pw + '.transformation', rep, check_formula=False)
            writer_text(p['role_basis'], pw + '.role_basis', rep, check_formula=False)
            prefs = ref_list(p['refs'], pw + '.refs', rep, inv, allow_context=True, min_items=1)
            cells = [x for x in prefs if x.startswith('cell:')]
            ctx = [x for x in prefs if x.startswith('context:')]
            for x in cells:
                use(x, f'{iid}.proof.{col}')
            if not cells and ctx and col not in SELECTION_COLS:
                rep.null('CONTEXT_ONLY_PROOF_UNREPRESENTABLE', pw, 'Only L, M and N (job inputs, FIELD_ROLES R48) can be proven by context alone; leave this field null with a reason.')
            elif not cells and ctx and col in ('M', 'N'):
                o13.append(f'{iid}.{col}')
            if cells:
                texts = [copy_text(inv, x, pw, rep, 'PROOF') for x in cells]
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
                        if n is None:
                            rep.null('NONNUMERIC_SOURCE_TEXT_FIELD_MUST_BE_NULL', pw,
                                     'The cited cell is not a plain ASCII numeric literal the writer accepts; leave the field null with a specific reason and keep the raw text.')
                        elif n != float(v):
                            rep.bad('NUMERIC_EVIDENCE_MISMATCH', pw, {'value': v})
        if it['group_id'] is None and (vals[0] is not None or vals[1] is not None):
            rep.bad('UNGROUPED_AB_MUST_BE_BLANK', w)
        g = groups.get(it['group_id']) if isinstance(it['group_id'], str) else None
        if g is not None:
            if vals[0] is not None and vals[0] != g['name']:
                rep.bad('A_MUST_EQUAL_GROUP_NAME', w)
            if vals[1] is not None and vals[1] != g['specification']:
                rep.bad('B_MUST_EQUAL_GROUP_SPECIFICATION', w)
        for j, key, code in ((5, 'quantity', 'SOURCE_QUANTITY_MISMATCH'), (16, 'unit_price', 'SOURCE_UNIT_PRICE_MISMATCH')):
            if vals[j] is None or not is_num(vals[j]):
                continue
            rawtext = raw_vals.get(key)
            n = writer_numeric_raw(rawtext)
            if rawtext is not None and n is None:
                rep.null('NONNUMERIC_RAW_' + key.upper() + '_FIELD_MUST_BE_NULL', w,
                         f'Raw {key} text is not a plain ASCII numeric literal; column {COLS[j]} must be null with a specific reason.')
            elif n is None or n != float(vals[j]):
                rep.bad(code, w)
        if vals[5] is not None and isinstance(proofs.get('F'), dict) and 'refs' in proofs['F']:
            if proofs['F'].get('refs') != raw_cells.get('quantity'):
                rep.bad('F_PROOF_MUST_BE_RAW_QUANTITY_CELL', w)
        if vals[16] is not None and inv.adoption != 'verified':
            rep.bad('Q_REQUIRES_VERIFIED_ADOPTION', w)
        if vals[4] is not None and vals[4] != raw_vals.get('unit'):
            rep.bad('SOURCE_UNIT_MISMATCH', w)
    if not demand_ids:
        rep.bad('DEMAND_ITEM_REQUIRED', 'items')
    if len(demand_ids) > 2000 or len(component_ids) > 2000:
        rep.hold('ITEM_LIMIT_FOR_WRITER', 'items')

    # component links
    linked = {}
    for i, lk in enumerate(r['component_links']):
        w = f'component_links[{i}]'
        if not exact_keys(lk, ('component_id', 'parent_id', 'status', 'basis_quantity', 'basis_raw_ref',
                               'basis_unit_ref', 'refs', 'reason'), w, rep):
            continue
        cid = lk['component_id']
        if not isinstance(cid, str) or cid not in component_ids:
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
        if not isinstance(lk['parent_id'], str) or lk['parent_id'] not in demand_ids or lk['parent_id'] == cid:
            rep.bad('COMPONENT_PARENT_MUST_BE_DEMAND', w)
        bq = lk['basis_quantity']
        if not is_num(bq) or bq <= 0:
            rep.bad('POSITIVE_BASIS_REQUIRED', w)
            bq = None
        refs = []
        for k in ('basis_raw_ref', 'basis_unit_ref'):
            x = lk[k]
            if not isinstance(x, str) or x not in inv.cells:
                rep.bad('BASIS_CELL_REF_REQUIRED', f'{w}.{k}')
            else:
                refs.append(x)
                use(x, f'{cid}.basis')
        for x in extra:
            use(x, f'{cid}.basis')
        if len(refs) == 2:
            sub = Report()
            t = copy_text(inv, refs[0], w + '.basis_raw_ref', sub, 'BASIS')
            u = copy_text(inv, refs[1], w + '.basis_unit_ref', sub, 'BASIS')
            for v in sub.violations:     # a link has no field to leave null: uncarriable basis holds the export
                rep.add(v['code'], v['where'], v.get('detail'), 'invalid' if v['category'] == 'invalid' else 'unrepresentable_hold')
            if t is not None and bq is not None:
                n = writer_numeric_raw(t)
                if n is None:
                    rep.hold('NONNUMERIC_BASIS_TEXT_UNREPRESENTABLE', w)
                elif n != float(bq):
                    rep.bad('BASIS_LITERAL_MISMATCH', w)
            if inv.cells[refs[1]]['saved_type'] != 'text':
                rep.bad('BASIS_UNIT_MUST_BE_TEXT_CELL', w + '.basis_unit_ref')
            elif u is not None:
                writer_text(u, w + '.basis_unit_ref:copied', rep)
            locator(inv, refs + [x for x in extra if x not in refs], w + '.basis_location', rep)
    for cid in sorted(component_ids - set(linked)):
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
        elif role in CONTENT_ROLES and rf not in used:
            rep.bad('CONTENT_CELL_NOT_USED_BY_ANY_ITEM', 'source_roles', {'ref': rf, 'role': role,
                    'action': 'cite it in the owning item (raw or proof) or classify it by its own nonitem role'})
    for rf in sorted(used):
        if assigned.get(rf, (None,))[0] in ('excluded_supply', 'analysis_unlinked'):
            rep.bad('CENSUS_ONLY_CELL_USED_BY_ITEM', 'source_roles', {'ref': rf, 'role': assigned[rf][0], 'uses': used[rf][:5],
                    'action': 'a line excluded under R45 or a block unlinked under R46 yields no item evidence; reclassify the cell or drop the citation'})
    for w, x in desc_anchor:
        if assigned.get(x, (None,))[0] == 'item_identifier':
            rep.bad('DESCRIPTION_INCLUDES_EXCLUDED_CELL', w + '.raw_refs.description', [x])
    for vid in inv.views:
        if vid not in covered:
            rep.hold('VIEW_SCOPE_UNACCOUNTED', 'views', vid)
    missing = [ref for ref, c in inv.cells.items() if Inventory.has_content(c) and ref not in assigned]
    if missing:
        rep.bad('UNCLASSIFIED_CONTENT_CELLS', 'source_roles', missing[:200] + (['...'] if len(missing) > 200 else []))
    if o13:
        rep.warn('O13_SELECTION_EVIDENCE_M_N', 'items', {'count': len(o13), 'first': o13[:10],
                 'note': 'M/N proven by job-input context alone become selection_evidence. The archived writer004 '
                         'validateCarrier accepts selection_evidence for L only (SELECTION_ONLY_ENGINEERING_ID); export '
                         'this carrier with research/export/writer_portable.py --mode v2.'})
    ctx = {'response': r, 'assigned': assigned, 'used': used, 'o13': o13}
    if not rep.violations:          # build exactly what convert writes and run the writer port on it
        carrier, _ = build_carrier(inv, resp_raw, ctx)
        try:
            validate_carrier_port(carrier)
        except WriterReject as e:
            rep.hold('WRITER_WOULD_REJECT_' + e.code, e.where)
        except Exception as e:
            rep.bad('CHECKER_COULD_NOT_EVALUATE', 'writer_port', f'{type(e).__name__}: {str(e)[:200]}')
    return rep, ctx


def selection_evidence(inv, ctx, proof):
    facts = [{'ref': x, 'namespace': inv.context[x]['namespace'], 'value': inv.context[x]['value'],
              'basis': inv.context[x]['basis']} for x in ctx]
    return json.dumps({'context': facts, 'role_basis': proof['role_basis']}, ensure_ascii=False, sort_keys=True)


def pack_transformation(proof, ctx):
    return json.dumps({'transformation': proof['transformation'], 'role_basis': proof['role_basis'],
                       'context_refs': ctx}, ensure_ascii=False, sort_keys=True)


def census_text(c):
    return json.dumps({'saved_type': c['saved_type'], 'state': c['state'], 'value': c['saved_value'],
                       'formula_record_present': c['formula_record_present'], 'conflicts': c['conflicts']},
                      ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def build_ledger(inv, resp_raw, ctx):
    assigned = ctx['assigned'] if ctx else {}
    used = ctx['used'] if ctx else {}
    entries = []
    for ref, c in inv.cells.items():
        role = assigned.get(ref, (None,))[0]
        entries.append({'ref': ref, 'sheet': c['sheet'], 'address': c['address'], 'state': c['state'],
                        'saved_type': c['saved_type'], 'saved_value': c['saved_value'],
                        'formula_record_present': c['formula_record_present'], 'conflicts': c['conflicts'],
                        'primary_role': role, 'uses': used.get(ref, []), 'census': role in CENSUS_ROLES,
                        'disposition': ('classified' if role else ('empty_or_covered' if not Inventory.has_content(c) else 'unclassified'))})
    ann = []
    if ctx:
        for it in ctx['response'].get('items', []):
            if isinstance(it, dict) and isinstance(it.get('raw_refs'), dict):
                for k, sel in it['raw_refs'].items():
                    if isinstance(sel, dict) and sel.get('reason_if_empty'):
                        ann.append({'item': it.get('id'), 'raw_field': k, 'reason_if_empty': sel['reason_if_empty']})
        for lk in ctx['response'].get('component_links', []):
            if isinstance(lk, dict):
                ann.append({'component': lk.get('component_id'), 'link_status': lk.get('status'), 'link_reason': lk.get('reason')})
    obj = {'schema': 'cps.census-ledger.v2', 'case_id': inv.case_id, 'inventory_sha256': inv.sha256,
           'response_sha256': sha256(resp_raw), 'positions': len(entries), 'entries': entries, 'response_annotations': ann}
    return (json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + '\n').encode('utf-8')


def build_carrier(inv, resp_raw, ctx):
    r, assigned = ctx['response'], ctx['assigned']
    ledger_bytes = build_ledger(inv, resp_raw, ctx)
    quiet = Report()
    groups = []
    for g in r['groups']:
        refs = g['anchor_refs'] + [x for x in g['name_refs'] + g['specification_refs'] if x not in g['anchor_refs']]
        anchor = json.dumps({'anchor_refs': g['anchor_refs'], 'name_refs': g['name_refs'],
                             'specification_refs': g['specification_refs'], 'relationship': g['relationship']},
                            ensure_ascii=False, sort_keys=True)
        groups.append({'id': g['id'], 'name': g['name'], 'specification': g['specification'],
                       'location': locator(inv, refs, 'group', quiet), 'anchor': anchor,
                       'quantity_basis': g['quantity_basis'], 'limitations': list(g['limitations'])})
    links = {lk['component_id']: lk for lk in r['component_links']}
    out_items, out_components = [], []
    for it in r['items']:
        anchor = json.dumps({'anchor_refs': it['anchor_refs']}, ensure_ascii=False)
        raw, loc_refs = {}, list(it['anchor_refs'])
        for k in RAW:
            refs = it['raw_refs'][k]['refs']
            raw[k] = '\n'.join(inv.cells[x]['canonical_raw'] for x in refs) if refs else None
            loc_refs += [x for x in refs if x not in loc_refs]
        evidence, nulls = {}, {}
        for j, col in enumerate(COLS):
            v, p = it['values'][j], it['proofs'][col]
            if v is None:
                nulls[col] = p['reason']
                continue
            cells = [x for x in p['refs'] if x.startswith('cell:')]
            cx = [x for x in p['refs'] if x.startswith('context:')]
            if not cells:
                evidence[col] = {'selection_evidence': selection_evidence(inv, cx, p), 'transformation': p['transformation']}
            else:
                evidence[col] = {'location': locator(inv, cells, 'proof', quiet), 'anchor': anchor,
                                 'raw_text': '\n'.join(inv.cells[x]['canonical_raw'] for x in cells),
                                 'transformation': pack_transformation(p, cx)}
        row = {'id': it['id'], 'group_id': it['group_id'], 'location': locator(inv, loc_refs, 'item', quiet),
               'anchor': anchor, 'raw': raw, 'values': copy.deepcopy(it['values']), 'evidence': evidence,
               'null_reasons': nulls, 'status': it['status'], 'review_reasons': list(it['review_reasons'])}
        if it['role'] == 'analysis_component':
            lk = links[it['id']]
            brefs = [lk['basis_raw_ref'], lk['basis_unit_ref']] + [x for x in lk['refs'] if x not in (lk['basis_raw_ref'], lk['basis_unit_ref'])]
            row['composition'] = {'parent_id': lk['parent_id'], 'basis_quantity': lk['basis_quantity'],
                                  'basis_unit': inv.cells[lk['basis_unit_ref']]['canonical_raw'],
                                  'basis_location': locator(inv, brefs, 'basis', quiet),
                                  'basis_raw': inv.cells[lk['basis_raw_ref']]['canonical_raw']}
            out_components.append(row)
        else:
            out_items.append(row)
    nonitems = []
    for ref, c in inv.cells.items():
        if ref in assigned and assigned[ref][0] in CENSUS_ROLES:
            role, reason = assigned[ref]
            nonitems.append({'location': locator(inv, [ref], 'census', quiet), 'kind': role, 'anchor': ref,
                             'text': census_text(c), 'reason': reason})
    # values-unchanged guard against an independent re-parse of the frozen response bytes
    fresh = strict_load(resp_raw)['items']
    order = [x for x in fresh if x['role'] == 'demand'] + [x for x in fresh if x['role'] == 'analysis_component']
    for src, dst in zip(order, out_items + out_components):
        if src['id'] != dst['id'] or _js(src['values']) != _js(dst['values']) or [type(x) for x in src['values']] != [type(x) for x in dst['values']]:
            raise Rejected('VALUE_CHANGED_DURING_COPY')
    limitations = list(r['limitations']) + list(inv.d['limitations'])
    limitations.append('Carrier produced by the 046b source-reference adapter: values copied from the frozen response; '
                       'raw/proof text copied from the pinned inventory; nonitem text is a typed JSON wrapper; '
                       'proof role_basis is packed in transformation JSON; empty-selection and link reasons are in the census ledger.')
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
    return carrier, ledger_bytes


def convert(inv, resp_raw):
    rep, ctx = check(inv, resp_raw)
    if rep.violations:
        ledger = build_ledger(inv, resp_raw, ctx) if ctx else build_ledger(inv, resp_raw, None)
        return rep, None, ledger
    carrier, ledger = build_carrier(inv, resp_raw, ctx)
    validate_carrier_port(carrier)
    return rep, carrier, ledger


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    pi = sub.add_parser('check-inventory')
    pi.add_argument('--inventory', required=True)
    for name in ('check', 'convert'):
        p = sub.add_parser(name)
        p.add_argument('--inventory', required=True)
        p.add_argument('--response', required=True)
        if name == 'convert':
            p.add_argument('--out-dir', required=True)
    a = ap.parse_args(argv)
    inv_raw = Path(a.inventory).read_bytes()
    try:
        inv = Inventory(inv_raw)
    except (Rejected, KeyError, TypeError, ValueError) as e:
        print(json.dumps({'status': 'INVENTORY_REJECTED', 'error': repr(e)}, ensure_ascii=False))
        return 2
    if a.cmd == 'check-inventory':
        rep = check_inventory(inv)
        print(json.dumps({'status': 'PASS' if not rep.violations else 'REJECTED', 'route': VERSION,
                          'inventory_sha256': inv.sha256, 'violations': rep.violations, 'warnings': rep.warnings},
                         ensure_ascii=False, indent=1))
        return 0 if not rep.violations else 1
    resp_raw = Path(a.response).read_bytes()
    if a.cmd == 'check':
        rep, _ = check(inv, resp_raw)
        status = 'PASS' if not rep.violations else 'REJECTED'
        print(json.dumps({'status': status, 'route': VERSION, 'inventory_sha256': inv.sha256,
                          'response_sha256': sha256(resp_raw), 'violations': rep.violations,
                          'warnings': rep.warnings}, ensure_ascii=False, indent=1))
        return 0 if status == 'PASS' else 1
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    try:
        rep, carrier, ledger = convert(inv, resp_raw)
    except (WriterReject, Rejected) as e:
        (out / 'ADAPTER_FAILURE.json').write_text(json.dumps({'status': 'ADAPTER_INTERNAL_REJECTION', 'error': str(e)}) + '\n', encoding='utf-8')
        print(json.dumps({'status': 'ADAPTER_INTERNAL_REJECTION', 'error': str(e)}))
        return 3
    (out / 'CENSUS_LEDGER.json').write_bytes(ledger)
    receipt = {'route': VERSION, 'inventory_sha256': inv.sha256, 'response_sha256': sha256(resp_raw),
               'census_ledger_sha256': sha256(ledger), 'violations': rep.violations, 'warnings': rep.warnings}
    if carrier is None:
        receipt['status'] = 'NOT_CARRIED'
        receipt['categories'] = sorted({v['category'] for v in rep.violations})
        (out / 'ADAPTER_REJECTION.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(json.dumps({'status': 'NOT_CARRIED', 'violations': len(rep.violations), 'categories': receipt['categories']}))
        return 1
    cb = (json.dumps(carrier, ensure_ascii=False, indent=1, allow_nan=False) + '\n').encode('utf-8')
    (out / 'carrier.json').write_bytes(cb)
    mn = sorted(f"{r['id']}.{k}" for r in carrier['items'] + carrier['components'] for k in ('M', 'N')
                if 'selection_evidence' in r['evidence'].get(k, {}))
    receipt.update(status='CARRIED_STRUCTURE_ONLY', carrier_sha256=sha256(cb), items=len(carrier['items']),
                   components=len(carrier['components']), groups=len(carrier['groups']),
                   nonitems=len(carrier['nonitems']), semantic_approval=False,
                   o13_m_n_selection_evidence={'count': len(mn), 'first': mn[:10],
                                               'writer004_validateCarrier_accepts': not mn,
                                               'export_mode_required': 'v2' if mn else 'v1'})
    (out / 'ADAPTER_RECEIPT.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: receipt[k] for k in ('status', 'carrier_sha256', 'items', 'components', 'nonitems')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
