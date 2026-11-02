"""Narrow preflight for the data-only workbook writer; not semantic approval.

No spreadsheet export, source discovery, target access, or runtime installation.
Actual verification reads the selected canonical allowlisted XLS/XLSX only.
"""
from source_verify import canonical_path, verify_source
import argparse
import hashlib
import json
import math
import ntpath
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

class Rejected(ValueError):
    pass

def reject(code):
    raise Rejected(code)

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            reject('DUPLICATE_JSON_KEY')
        result[key] = value
    return result

def numeric_token(token):
    """Require decimal value to survive a binary64 shortest-decimal round trip.

    Ordinary decimals such as 0.1 are supported. This is not a claim that every
    decimal has an exact binary representation. Large/overprecise values hold.
    """
    try:
        decimal = Decimal(token)
        value = float(decimal)
    except (InvalidOperation, ValueError, OverflowError):
        reject('INVALID_NUMBER')
    if not decimal.is_finite() or not math.isfinite(value):
        reject('NONFINITE_NUMBER')
    if abs(decimal) > 9007199254740991:
        reject('UNSAFE_NUMBER')
    if Decimal(str(value)) != decimal:
        reject('NUMERIC_DECIMAL_ROUNDTRIP_LOSS')
    return int(decimal) if decimal == decimal.to_integral() else value

def strict_load(raw, limit):
    if len(raw) > limit:
        reject('INPUT_SIZE_LIMIT')
    try:
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_pairs,
                           parse_int=numeric_token, parse_float=numeric_token,
                           parse_constant=lambda _: reject('NONFINITE_NUMBER'))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        reject('INVALID_JSON')
    return value

def exact_keys(value, keys, code):
    if type(value) is not dict or set(value) != set(keys):
        reject(code)

FORBIDDEN = re.compile(
    r'未填|已填|電機圖|板金|鈑金|歷史|(?:^|[\\/_. -])'
    r'(?:ok|targets?|reserved|drawings?|histor(?:y|ical|ies))(?=[\\/_. -]|$)',
    re.I)
DEVICE = re.compile(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)

def canonical_xlsx_path(value):
    if type(value) is not str or len(value) > 2048:
        reject('PATH_REQUIRED')
    if unicodedata.normalize('NFC', value) != value:
        reject('NONCANONICAL_UNICODE_PATH')
    if not re.match(r'^[A-Z]:\\', value) or '/' in value:
        reject('CANONICAL_LOCAL_ABSOLUTE_PATH_REQUIRED')
    parts = value[3:].split('\\')
    if not parts or any(not p or p in ('.', '..') or p[-1] in ' .'
                        or re.search(r'[<>:"|?*\x00-\x1f]', p)
                        or DEVICE.match(p) for p in parts):
        reject('NONCANONICAL_PATH_COMPONENT')
    if ntpath.normpath(value) != value or not value.lower().endswith('.xlsx'):
        reject('CANONICAL_XLSX_PATH_REQUIRED')
    if FORBIDDEN.search(value):
        reject('FORBIDDEN_SOURCE_PATH')
    return value

def source_shape(source):
    exact_keys(source, ('kind','path','sha256','views'), 'SOURCE_SHAPE')
    if source['kind'] not in ('cached_xlsx','cached_xls'):reject('SOURCE_KIND')
    canonical_path(source['path'],source['kind'])
    if type(source['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',source['sha256']):reject('SOURCE_HASH_SHAPE')
    if type(source['views']) is not list or not 1<=len(source['views'])<=1000:reject('VIEWS_REQUIRED')
    for i,v in enumerate(source['views']):
        exact_keys(v,('id','sheet','range'),'VIEW_SHAPE')
        if type(v['id']) is not int or v['id']!=i+1 or type(v['sheet']) is not str or not v['sheet'].strip():reject('VIEW_IDENTITY')
        bounds(v['range'])

def address(a):
    if type(a) is not str or not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,6}',a):reject('CELL_ADDRESS')
    m=re.fullmatch(r'([A-Z]+)([0-9]+)',a);col=0
    for x in m[1]:col=col*26+ord(x)-64
    row=int(m[2])
    if col>16384 or row>1048576:reject('CELL_BOUNDS')
    return col,row

def bounds(s):
    if type(s) is not str:reject('RANGE_REQUIRED')
    a=s.split(':')
    if len(a) not in (1,2):reject('RANGE_REQUIRED')
    lo=address(a[0]);hi=address(a[-1])
    if lo[0]>hi[0] or lo[1]>hi[1]:reject('RANGE_ORDER')
    return lo,hi

def location(loc,source):
    exact_keys(loc,('sheet','cells','views'),'LOCATION_SHAPE')
    if type(loc['sheet']) is not str or type(loc['cells']) is not list or not 1<=len(loc['cells'])<=1000 or type(loc['views']) is not list or not 1<=len(loc['views'])<=1000:reject('LOCATION_REQUIRED')
    if any(type(v) is not int for v in loc['views']) or len(set(loc['views']))!=len(loc['views']) or any(type(c) is not str for c in loc['cells']) or len(set(loc['cells']))!=len(loc['cells']):reject('LOCATION_UNIQUE_TYPES')
    vv=[]
    for n in loc['views']:
        if not 1<=n<=len(source['views']):reject('VIEW_OUT_OF_RANGE')
        v=source['views'][n-1]
        if v['sheet']!=loc['sheet']:reject('SHEET_VIEW_MISMATCH')
        vv.append(bounds(v['range']))
    for a in loc['cells']:
        c,r=address(a)
        if not any(lo[0]<=c<=hi[0] and lo[1]<=r<=hi[1] for lo,hi in vv):reject('CELL_OUTSIDE_VIEWS')
    for lo,hi in vv:
        if not any(lo[0]<=address(a)[0]<=hi[0] and lo[1]<=address(a)[1]<=hi[1] for a in loc['cells']):reject('UNRELATED_VIEW')

def raw_number(value):
    if type(value) is not str or not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', value.strip(), flags=re.ASCII):
        reject('UNSUPPORTED_NUMERIC_TEXT')
    return numeric_token(value.strip().replace(',', ''))

def preflight(carrier_raw, allowlist_raw):
    carrier = strict_load(carrier_raw, 20 * 1024 * 1024)
    allowlist = strict_load(allowlist_raw, 256 * 1024)
    if type(carrier) is not dict or type(carrier.get('source')) is not dict:
        reject('CARRIER_SOURCE_REQUIRED')
    source_shape(carrier['source'])
    expected='cps.cached-xls-research-carrier.v1' if carrier['source']['kind']=='cached_xls' else 'cps.cached-xlsx-research-carrier.v1'
    if carrier.get('schema')!=expected:reject('CARRIER_SOURCE_SCHEMA_MISMATCH')
    exact_keys(allowlist, ('schema', 'sources'), 'ALLOWLIST_SHAPE')
    if allowlist['schema'] not in ('cps.source-allowlist.v1','cps.source-allowlist.v2'):
        reject('ALLOWLIST_SCHEMA')
    sources = allowlist['sources']
    if type(sources) is not list or not 1 <= len(sources) <= 20:
        reject('ALLOWLIST_COUNT')
    seen = set()
    for source in sources:
        source_shape(source)
        if allowlist['schema']=='cps.source-allowlist.v1' and source['kind']!='cached_xlsx':reject('LEGACY_REQUIRES_ALLOWLIST_V2')
        key = source['path'].casefold()
        if key in seen:
            reject('DUPLICATE_SOURCE_PIN')
        seen.add(key)
    if carrier['source'] not in sources:
        reject('SOURCE_NOT_PINNED')
    items = carrier.get('items',[]) + carrier.get('components',[])
    if type(items) is not list or not 1 <= len(items) <= 2000:
        reject('ITEMS_REQUIRED')
    for item in items:
        if type(item) is not dict or type(item.get('values')) is not list or len(item['values']) != 17:
            reject('VALUES_SHAPE')
        for index, col in ((5, 'F'), (15, 'P'), (16, 'Q')):
            value = item['values'][index]
            if value is None:
                continue
            if type(value) not in (int, float):
                reject('NUMERIC_VALUE_TYPE')
            evidence = item.get('evidence', {}).get(col)
            if type(evidence) is not dict or raw_number(evidence.get('raw_text')) != value:
                reject('NUMERIC_EVIDENCE_MISMATCH')
            if col in ('F', 'Q'):
                key = 'quantity' if col == 'F' else 'unit_price'
                if raw_number(item.get('raw', {}).get(key)) != value:
                    reject('RAW_NUMBER_MISMATCH')
    return carrier, allowlist

def read_bounded(path, limit):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        reject('INPUT_SIZE_LIMIT')
    return raw

def verify_selected_workbook(source):
    source_shape(source)
    return verify_source(source)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--carrier', required=True)
    parser.add_argument('--allowlist', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--verify-source', action='store_true')
    args = parser.parse_args()
    raw = read_bounded(args.carrier, 20 * 1024 * 1024)
    allow = read_bounded(args.allowlist, 256 * 1024)
    carrier, _ = preflight(raw, allow)
    selected = verify_selected_workbook(carrier['source']) if args.verify_source else None
    report = {'status': 'STRICT_INPUT_PREFLIGHT_ONLY',
              'carrier_sha256': hashlib.sha256(raw).hexdigest(),
              'allowlist_sha256': hashlib.sha256(allow).hexdigest(),
              'items': len(carrier['items']), 'selected_workbook': selected,
              'writer_structural_validation': 'REQUIRED_SEPARATELY',
              'sheet_cell_census_and_semantic_review': 'REQUIRED_SEPARATELY',
              'export_authorized': False}
    with Path(args.report).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__':
    main()
