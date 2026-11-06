"""Tests for the CPS portable export route (NOT ADMITTED). Invented fixtures only.

Proves on invented carriers:
  (a) writer_portable matrices == archived writer004 prepareMatrices (node + stub), byte-exact
      EXPECTED_SAVED_VALUES.json text and structural equality; JSON.stringify fuzz parity;
  (b) write -> saved_qa round trip has 0 mismatches (plus the original checkpoint045 saved QA);
      saved_qa detects injected defects; repeated builds are byte-identical;
  (c) invalid carriers are refused (writer004 gate codes, prepareMatrices review-cell code,
      documented portable-only refusals) and leave no output;
  (d) visual_qa produces PNGs reproducibly;
  (e) mode v2 (candidate 046f, route v4.2 with the v4.1 relaxations): carriers with M/N job-input selection evidence
      (O13) and/or C null with status research_draft (R57) pass writer004 on the documented placeholder
      copy plus the sha256-pinned route v4.2 port, and the saved values equal writer004 prepareMatrices on that copy
      except the documented cells (checked here by an independent content-based alignment); carriers
      without those (including Q under unverified adoption, O16) take the v1 route unchanged; v2
      refusals come from writer004 or the route port as documented;
  (f) node environment (review S1): the reviewer's planted @oai/artifact-tool module, NODE_OPTIONS --import, NODE_PATH,
      conditional exports and symlinked writer files are each shown to change writer004's verdict when node runs them
      directly, and are each refused (or neutralized) by the writer;
  (g) saved_qa structure (review S2): the reviewer's 22 tampers, rebuilt from the reviewer's invented fidelity probe, plus
      extra structural tampers, are all caught; no input crashes saved_qa;
  (h) provenance of EXPECTED (review S3): with --carrier/--writer-dir, consistent EXPECTED+xlsx tampers (receipt stale,
      updated or deleted) are caught in v1 and v2, and every untampered output passes;
  (i) visual_qa helpers (review S4, N1): page mapping by the [[sheet name]] marker; possibly clipped cells;
  (j) second review (round 2): the round-2 tampers N01-N07, N10, N11 and the receipt-mode downgrade fail saved QA
      (provenance always reruns the writer and compares the xlsx); number text: every form the writer writes (JavaScript
      String(v): 1e-7, 5e-324, -0 written as 0, ...) matches the saved_qa pattern, and other texts do not; the node
      environment is an allowlist (OPENSSL_CONF, the reviewer's A3, LD_*, NODE_* removed);
  third review (round 3): G1 the reviewer's B01-B06 fail saved QA without provenance (pinned parts, worksheet element
      namespace), and the pinned parts are byte-constant in every writer output of the run; G2 the reviewer's p2 node
      wrapper: the writer records the wrapper's realpath and sha256, an unpinned saved QA shows it, and saved QA with
      --checker-node/--checker-node-sha256 refuses the wrapper's output (WRITER004_REFUSED) and never runs PATH's node;
      G3 the reviewer's p1 receipt edits, each compared receipt field edited on its own, fail with receipt_claim_mismatch
      naming the fields. Provenance runs use the pinned checker node (the node found in PATH, by realpath and sha256).
  (k) writer v2.6, owner decisions O33-O34: the deliverable name derivation (dash removal, no dash, the cut to 31 with (未填)
      kept, forbidden characters, NFKC and whitespace, refusals) gives the same record in the writer and in saved QA, also on
      4,000 random titles; titled outputs differ from untitled ones only in the file name and xl/workbook.xml, which equals the
      pinned template with the escaped derived name; saved QA passes them with provenance (the rerun gets --job-title); the
      naming tampers K01-K13 fail as listed (K12, a consistent re-titling, passes: the job title is the operator's check);
      G and H have the body style in every output (no #F1F3F5, also in the renders).
  (l) writer v2.7, owner decision O38: a titled output holds the one-sheet deliverable <name>.xlsx in the creator's format and
      the four-sheet INTERNAL_QA_WORKBOOK.xlsx (the v2.6 workbook, same bytes); the deliverable's cells equal the main sheet of
      EXPECTED_SAVED_VALUES.json; its 7 pinned parts and one-sheet template hold in every titled output; saved QA v6 checks it
      (structure, three readers, format) and the rerun byte-compares it; the deliverable tampers L01-L16 fail as listed (L15, a
      consistent change of all three files, passes without provenance and fails with it); visual QA v4 prints its gridlines
      and lists no-wrap cells whose text may be cut (possibly_cut_cells).
Usage: python3 -I -B run_export_tests.py --writer-dir /abs/archived/writer --work /abs/new-dir [--skip-visual]
Prints a JSON summary with passed and failed lists; exit 0 only if nothing failed.
"""
import argparse, copy, hashlib, importlib.util, json, math, os, random, re, shlex, shutil, struct, subprocess, sys, unicodedata, zipfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
EXPORT = HERE.parent
REPO = EXPORT.parents[1]
ROUTE_DIR = REPO / 'research' / 'guideline046_004'
ROUTE = ROUTE_DIR / 'package' / 'tools' / 'cps046b_route.py'
ROUTE_FIXTURES = ROUTE_DIR / 'route_tests' / 'make_fixtures.py'
QA045 = REPO / 'research' / 'checkpoint045' / 'postqa' / 'qa_saved_external.py'
ROUTE46F_DIR = REPO / 'research' / 'guideline046_006'
ROUTE46F = ROUTE46F_DIR / 'package' / 'tools' / 'cps046b_route.py'
ROUTE46F_FIXTURES = ROUTE46F_DIR / 'route_tests' / 'make_fixtures.py'
PY = [sys.executable, '-I', '-B']
results = []
# test-side node processes run without NODE_* variables too, so their results do not depend on the caller's environment
NODE_CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.upper().startswith('NODE_')}
# the reviewer's planted module (review S1 demo), verbatim
PLANTED_MODULE = """// Reviewer probe: an unpinned module resolved before the stub. Patches a builtin used by validateCarrier.
const orig = Array.prototype.includes;
Array.prototype.includes = function (x, ...r) { if (x === 'partial') return true; return orig.call(this, x, ...r); };
const unavailable = () => { throw new Error('EXPORT_RUNTIME_UNAVAILABLE'); };
export const Workbook = { create: unavailable };
export const SpreadsheetFile = { exportXlsx: unavailable };
"""
INCLUDES_PATCH = """const orig = Array.prototype.includes;
Array.prototype.includes = function (x, ...r) { if (x === 'partial') return true; return orig.call(this, x, ...r); };
"""


def sha(b):
    return hashlib.sha256(b).hexdigest()


def record(name, ok, detail=None):
    results.append({'test': name, 'pass': bool(ok), **({'detail': detail} if detail is not None and not ok else {})})
    return ok


def run(cmd, timeout=900, env=None, cwd=None):
    if env is None and str(cmd[0]) == 'node':
        env = NODE_CLEAN_ENV
    p = subprocess.run([str(x) for x in cmd], capture_output=True, timeout=timeout, env=env, cwd=cwd)
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def refusal(err):
    try:
        return json.loads(err.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {}


def qa_report(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def same_value(a, b):
    """Type-aware equality: numbers by value (int/float are both JavaScript numbers), exact strings."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(same_value(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


# ---------------------------------------------------------------- fuzz values for JSON.stringify parity
def fuzz_values(n, seed=46):
    rnd = random.Random(seed)
    pool = ['a', 'Z', '0', ' ', '"', '\\', '/', '\b', '\f', '\n', '\r', '\t', '\x00', '\x01', '\x1f', '\x7f', '\x80', '\x85', '\xa0',
            '\u2028', '\u2029', '\ufeff', '\ufffe', '中', 'é', '\U0001F600', '\U00020000', '\ud800', '\udbff', '\udc00', '\udfff',
            '_x0041_', '<', '&', '=', '-']
    keys = ['a', 'b', '0', '1', '2', '10', '01', '-1', '4294967294', '4294967295', '9007199254740993', '__proto__', 'constructor',
            '', ' ', 'é', '中', '1.5', '١', '1e3', '007']
    specials = [0.0, -0.0, 5e-324, 2.2250738585072014e-308, 1e21, 1e-7, 1e-6, 123e-20, 2.0 ** 53, 2.0 ** 53 + 2,
                1.7976931348623157e308, 0.1, 0.30000000000000004, 1e20, 999999999999999999999.0, 1.5e-6, 123456789e3, -1e-7,
                100.0, 1234.5, -0.5, 9007199254740991.0, 4294967295.0, 1e16, 1.0000000000000002]

    def number():
        k = rnd.random()
        if k < 0.25:
            return rnd.choice(specials)
        if k < 0.45:
            return rnd.randint(-10 ** rnd.randint(1, 25), 10 ** rnd.randint(1, 25))
        if k < 0.7:
            return rnd.uniform(-1, 1) * 10 ** rnd.randint(-30, 30)
        while True:
            f = struct.unpack('<d', rnd.getrandbits(64).to_bytes(8, 'little'))[0]
            if math.isfinite(f):
                return f

    def value(depth):
        k = rnd.random()
        if depth > 3 or k < 0.35:
            return rnd.choice([None, True, False]) if rnd.random() < 0.15 else (number() if rnd.random() < 0.5 else
                                                                                  ''.join(rnd.choice(pool) for _ in range(rnd.randint(0, 12))))
        if k < 0.65:
            return [value(depth + 1) for _ in range(rnd.randint(0, 4))]
        return {rnd.choice(keys): value(depth + 1) for _ in range(rnd.randint(0, 5))}
    return [value(0) for _ in range(n)]


R57_PLACEHOLDER = ('R57 relaxation placeholder: C is null with status research_draft in the carrier; '
                   'status held and this reason exist only in the writer004 validation copy.')


def placeholder_copy_independent(c):
    """Test-side implementation of the documented neutralization (README, mode v2): O13 M/N selection evidence ->
    location evidence; R57 C-null research_draft -> held, plus the placeholder reason when review_reasons is empty."""
    c = copy.deepcopy(c)
    for r in c['items'] + c['components']:
        for k in ('M', 'N'):
            e = r['evidence'].get(k)
            if isinstance(e, dict) and 'selection_evidence' in e:
                rest = {x: y for x, y in e.items() if x != 'selection_evidence'}
                r['evidence'][k] = dict(rest, location=copy.deepcopy(r['location']), anchor=r['anchor'], raw_text=e['selection_evidence'])
        if r['values'][2] is None and r['status'] == 'research_draft':
            r['status'] = 'held'
            if r['review_reasons'] == []:
                r['review_reasons'] = [R57_PLACEHOLDER]
    return c


def mn_fields(c):
    return [f"{r['id']}.{k}" for r in c['items'] + c['components'] for k in ('M', 'N') if 'selection_evidence' in r['evidence'].get(k, {})]


def r57_ids(c):
    return [r['id'] for r in c['items'] + c['components'] if r['values'][2] is None and r['status'] == 'research_draft']


def q_ids(c):
    return [r['id'] for r in c['items'] + c['components'] if r['values'][16] is not None] if c['metadata'].get('source_adoption') != 'verified' else []


def documented_difference(mine, theirs, obj):
    """Independent, content-based check that the saved sheets (mine) equal writer004's sheets of the copy (theirs) except
    the documented cells. Returns (differing cells, cells outside the documented set, placeholder rows removed)."""
    fields, r57 = set(mn_fields(obj)), set(r57_ids(obj))
    added = {r['id'] for r in obj['items'] + obj['components'] if r['id'] in r57 and r['review_reasons'] == []}
    kinds = ('項目', '原文', '欄位依據', '空白原因', '待確認')
    diffs, outside, removed = [], [], 0
    for sa, sb in zip(mine, theirs):
        va, vb = sa['values'], sb['values']
        if sa['name'] == '來源與審查':
            keep = []
            for row in vb:          # drop the copy's placeholder 待確認 rows of items that had no review reason
                if row[0] == '待確認' and row[1].rsplit('.', 1)[0] in added and row[4] == json.dumps(R57_PLACEHOLDER, ensure_ascii=False):
                    removed += 1
                    continue
                keep.append(row)
            vb = keep
        if sa['name'] != sb['name'] or len(va) != len(vb):
            outside.append((sa['name'], 'rows', len(va), len(vb)))
            continue
        for i, (ra, rb) in enumerate(zip(va, vb)):
            for j, (x, y) in enumerate(zip(ra, rb)):
                if same_value(x, y):
                    continue
                owner = ra[1] if ra[0] == '項目' else (ra[1].rsplit('.', 1)[0] if ra[0] in kinds else None)
                ok = sa['name'] == '來源與審查' and (
                    (ra[0] == '欄位依據' and ra[1] in fields and j in (2, 3, 4)) or
                    (owner in r57 and j == 6 and x == 'research_draft' and y == 'held') or
                    (ra[0] == '項目' and ra[1] in added and j == 5 and x == '[]' and y == json.dumps([R57_PLACEHOLDER], ensure_ascii=False)))
                (diffs if ok else outside).append((sa['name'], i + 1, j + 1))
    return diffs, outside, removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--writer-dir', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--skip-visual', action='store_true')
    a = ap.parse_args()
    wd, work = Path(a.writer_dir).resolve(), Path(a.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    wp = load(EXPORT / 'writer_portable.py', 'writer_portable_under_test')
    route = load(ROUTE, 'cps046b_route_reference')
    # third review G2: the checker node of every provenance run is pinned by realpath and sha256 (here: the node PATH finds)
    node_found = shutil.which('node', path=NODE_CLEAN_ENV.get('PATH'))
    node_real = os.path.realpath(node_found) if node_found else None
    node_sha = sha(Path(node_real).read_bytes()) if node_real else None
    checker = ['--checker-node', node_real, '--checker-node-sha256', node_sha]
    c0, o0, e0 = run([node_real, '--version'], env=NODE_CLEAN_ENV) if node_real else (1, '', '')
    node_version = o0.strip()
    record('checker_node_resolved', node_real is not None and os.path.isabs(node_real) and c0 == 0 and node_version.startswith('v22.'),
           {'node': node_real, 'version': node_version})

    # ------------------------------------------------ pins and constants
    for f, allowed in wp.WRITER_PINS.items():
        h = sha((wd / f).read_bytes())
        record(f'writer_file_pinned_{f}', h in allowed, h)
    record('constants_headers_equal_route', wp.HEADERS == route.HEADERS)
    record('constants_js_whitespace_equal_route', set(wp.JS_WS) == set(route.JS_WS) and len(wp.JS_WS) == len(route.JS_WS))
    probes = ['=a', ' =a', '\u3000-a', '\ufeff+a', '\u00a0@a', '\u2028-a', '\u200b-a', '\u0085-a', 'a=b', '', '-', '\t\n@', '\u180e=a']
    record('constants_formula_like_equal_route', all(wp.formula_like(s) == bool(route.FORMULA_RE.match(s)) for s in probes))
    record('constants_js_len_equal_route', all(wp.js_len(s) == route.js_len(s) for s in ['', 'a', '中', '\U00020000', 'a\ud800']))

    # ------------------------------------------------ fixtures
    fx = work / 'route_fixtures'
    code, out, err = run(PY + [ROUTE_FIXTURES, fx])
    record('route_make_fixtures', code == 0, err[-300:])
    code, out, err = run(PY + [ROUTE, 'convert', '--inventory', fx / 'fixture_inventory.json', '--response', fx / 'valid_response.json',
                               '--out-dir', work / 'route_convert'])
    base = work / 'route_convert' / 'carrier.json'
    record('route_convert_base_carrier', code == 0 and base.is_file(), (out + err)[-300:])
    ef = work / 'export_fixtures'
    code, out, err = run(PY + [HERE / 'make_export_fixtures.py', base, ef])
    record('make_export_fixtures', code == 0, err[-300:])
    index = json.loads((ef / 'FIXTURES.json').read_text(encoding='utf-8'))['fixtures']
    valid = [x for x in index if x['valid']]
    invalid = [x for x in index if not x['valid']]
    record('fixture_counts', len(valid) >= 10 and len(invalid) >= 20, {'valid': len(valid), 'invalid': len(invalid)})

    # ------------------------------------------------ (a) JSON.stringify fuzz parity
    vals = fuzz_values(3000)
    vp = work / 'fuzz_values.json'
    vp.write_text(json.dumps(vals, ensure_ascii=True), encoding='ascii')
    code, out, err = run(['node', HERE / 'stringify_fuzz.mjs', vp])
    node_pairs = json.loads(out) if code == 0 else []
    parsed = wp.js_parse(vp.read_bytes())
    mism = [i for i, (v, pair) in enumerate(zip(parsed, node_pairs)) if [wp.js_stringify(v), wp.js_stringify(v, 2)] != pair]
    record('a_js_stringify_fuzz_parity_3000', code == 0 and len(node_pairs) == len(vals) and not mism,
           {'mismatches': len(mism), 'first': [{'python': wp.js_stringify(parsed[i]), 'node': node_pairs[i][0]} for i in mism[:3]], 'stderr': err[-200:]})

    # ------------------------------------------------ (a) matrices parity on every fixture
    parity_set = valid + [x for x in invalid if x['expected_stage'] == 'prepare_matrices']
    lp = work / 'parity_paths.json'
    lp.write_text(json.dumps([x['file'] for x in parity_set]), encoding='utf-8')
    code, out, err = run(['node', HERE / 'parity_matrices.mjs', wd / 'writer004.mjs', lp])
    node_res = json.loads(out) if code == 0 else []
    record('a_node_parity_probe_ran', code == 0 and len(node_res) == len(parity_set), err[-300:])
    node_text = {}
    for x, nr in zip(parity_set, node_res):
        raw = Path(x['file']).read_bytes()
        try:
            m = wp.prepare_matrices(wp.js_parse(raw))
            py = {'ok': True, 'text': wp.expected_saved_values(m)}
        except wp.Refused as e:
            py = {'ok': False, 'code': e.code}
        if x['valid']:
            node_text[x['name']] = nr.get('text', '').encode('utf-8')
            byte_eq = nr['ok'] and py['ok'] and py['text'] == node_text[x['name']]
            struct_eq = nr['ok'] and py['ok'] and same_value(json.loads(py['text'].decode('utf-8')), json.loads(nr['text']))
            mats = nr['ok'] and py['ok'] and same_value([s['values'] for s in json.loads(nr['text'])['sheets']],
                                                        [m['main'], m['review'], m['components'], m['links']])
            record(f"a_matrices_parity_{x['name']}", byte_eq and struct_eq and mats,
                   {'byte_equal': byte_eq, 'structural_equal': struct_eq, 'matrices_equal': mats, 'node': nr.get('code')})
        else:
            record(f"a_refusal_parity_{x['name']}", not nr['ok'] and not py['ok'] and nr['code'] == py['code'] == x['expected_code'],
                   {'node': nr.get('code'), 'python': py.get('code')})

    # ------------------------------------------------ (b) write -> saved QA round trip
    outs = work / 'outputs'
    outs.mkdir()
    for x in valid:
        od = outs / x['name']
        code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', x['file'], '--out', od, '--writer-dir', wd])
        if not record(f"b_write_{x['name']}", code == 0 and (od / 'research-draft.xlsx').is_file(), err[-400:]):
            continue
        exp = (od / 'EXPECTED_SAVED_VALUES.json').read_bytes()
        record(f"a_expected_file_equals_writer004_{x['name']}", exp == node_text.get(x['name']))
        rc = json.loads((od / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
        doc = json.loads(exp.decode('utf-8'))
        msha = {s['name']: sha(wp.js_stringify(s['values']).encode('utf-8')) for s in doc['sheets']}
        record(f"b_receipt_{x['name']}", rc['input_carrier']['sha256'] == sha(Path(x['file']).read_bytes())
               and rc['output_xlsx']['sha256'] == sha((od / 'research-draft.xlsx').read_bytes())
               and rc['expected_saved_values']['sha256'] == sha(exp) and rc['matrices_sha256'] == msha
               and rc['admitted'] is False and rc['limitations'] and rc['cross_check']['result'] == 'BYTE_IDENTICAL')
        code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', od])
        qa = json.loads((od / 'SAVED_QA.json').read_text(encoding='utf-8')) if (od / 'SAVED_QA.json').is_file() else {}
        t = qa.get('totals', {})
        record(f"b_saved_qa_round_trip_{x['name']}", code == 0 and qa.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS'
               and t.get('value_type_mismatches') == 0 and t.get('formulas') == 0 and t.get('value_check_failures') == 0
               and t.get('formatting_failures') == 0 and all(qa['header_checks'].values()),
               {'status': qa.get('status'), 'totals': t, 'findings': {k: v['first'][:2] for k, v in qa.get('findings', {}).items()}})
        code, out, err = run(PY + [QA045, '--output', od, '--report', work / f"qa045_{x['name']}.json"])
        record(f"b_checkpoint045_saved_qa_{x['name']}", code == 0 and json.loads(out)['status'] == 'SAVED_ALL_CELL_VALUE_TYPE_PASS', (out + err)[-300:])

    # repeatability
    first = outs / 'v01_base'
    code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', valid[0]['file'], '--out', work / 'repeat_v01', '--writer-dir', wd])
    record('b_repeat_build_byte_identical', code == 0 and (work / 'repeat_v01' / 'research-draft.xlsx').read_bytes() == (first / 'research-draft.xlsx').read_bytes()
           and (work / 'repeat_v01' / 'EXPECTED_SAVED_VALUES.json').read_bytes() == (first / 'EXPECTED_SAVED_VALUES.json').read_bytes())

    # saved_qa negative controls (it must not be vacuous)
    import openpyxl
    src = outs / 'v04_text_edges'

    def tampered(name, mutate):
        d = work / f'tamper_{name}'
        shutil.copytree(src, d)
        (d / 'SAVED_QA.json').unlink()
        wb = openpyxl.load_workbook(d / 'research-draft.xlsx')
        mutate(wb['未填研究草稿'])
        wb.save(d / 'research-draft.xlsx')
        code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d])
        return code, json.loads((d / 'SAVED_QA.json').read_text(encoding='utf-8'))
    code, qa = tampered('text_to_number', lambda ws: ws.__setitem__('J4', 123))
    cells = [f['cell'] for f in qa['findings'].get('value_type_mismatch', {}).get('first', [])]
    record('b_negative_text_to_number_detected', code == 1 and 'J4' in cells and qa['totals']['value_type_mismatches'] >= 3, cells[:6])
    code, qa = tampered('number_to_text', lambda ws: ws.__setitem__('F2', '2'))
    cells = [f['cell'] for f in qa['findings'].get('value_type_mismatch', {}).get('first', [])]
    record('b_negative_number_to_text_detected', code == 1 and 'F2' in cells, cells[:6])
    code, qa = tampered('formula', lambda ws: ws.__setitem__('R2', '=1+1'))
    record('b_negative_formula_detected', code == 1 and qa['totals']['formulas'] >= 1 and qa['totals']['unexpected_populated_cells'] >= 1, qa['totals'])
    code, qa = tampered('header', lambda ws: ws.__setitem__('Q1', '合約單價'))
    record('b_negative_header_detected', code == 1 and qa['findings'].get('header_row', {}).get('count', 0) >= 3, qa.get('header_checks'))

    # ------------------------------------------------ (c) refusals
    for x in invalid:
        od = outs / x['name']
        code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', x['file'], '--out', od, '--writer-dir', wd])
        try:
            ref = json.loads(err.strip().splitlines()[-1])
        except (ValueError, IndexError):
            ref = {}
        ok = code == 1 and not od.exists() and ref.get('status') == 'REFUSED' and ref.get('code') == x['expected_code'] and ref.get('stage') == x['expected_stage']
        c2, o2, e2 = run(['node', wd / 'validate_carrier_v4.mjs', '--carrier', x['file']])
        if x['expected_stage'].startswith('gate:'):
            direct = c2 == 1 and json.loads(e2).get('code') == x['expected_code']
        else:   # writer004's own gate accepts these; the refusal comes later (documented)
            direct = c2 == 0
        record(f"c_refused_{x['name']}", ok and direct, {'refusal': ref, 'validate_carrier_v4_exit': c2})
    code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', valid[0]['file'], '--out', first, '--writer-dir', wd])
    record('c_refused_existing_output', code == 1 and json.loads(err)['code'] == 'OUTPUT_EXISTS')
    code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', 'relative.json', '--out', work / 'rel_out', '--writer-dir', wd])
    record('c_refused_relative_path', code == 1 and json.loads(err)['code'] == 'ABSOLUTE_CLI_PATH_REQUIRED' and not (work / 'rel_out').exists())
    alt = work / 'tampered_writer' / 'writer'
    shutil.copytree(wd, alt)
    if (wd.parent / 'node_modules').is_dir():
        shutil.copytree(wd.parent / 'node_modules', alt.parent / 'node_modules')
    with open(alt / 'writer004.mjs', 'a', encoding='utf-8') as f:
        f.write('\n// changed\n')
    code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', valid[0]['file'], '--out', work / 'tampered_out', '--writer-dir', alt])
    record('c_refused_unpinned_writer', code == 1 and json.loads(err)['code'] == 'WRITER_FILE_NOT_PINNED' and not (work / 'tampered_out').exists())

    # ------------------------------------------------ (e) mode v2: route v4.1 relaxations for 046f carriers
    r46 = load(ROUTE46F, 'cps046f_route_reference')
    record('e_route_v4_version_matches_writer', r46.VERSION == wp.ROUTE_V4_VERSION == 'cps046f-route.v4.2'
           and wp.ROUTE_V4_TOOL.resolve() == ROUTE46F.resolve() and set(r46.PORT_RELAXATIONS) == set(wp.RELAXATION_CLASSES))
    record('e_route_port_pinned_by_sha256', wp.ROUTE_V4_SHA256 == sha(ROUTE46F.read_bytes()), {'pinned': wp.ROUTE_V4_SHA256})
    fx6 = work / 'route046f_fixtures'
    code, out, err = run(PY + [ROUTE46F_FIXTURES, fx6])
    record('e_route046f_make_fixtures', code == 0, err[-300:])
    carriers6 = {}
    res6 = ROUTE46F_DIR / 'package' / 'resources'
    for tag, inv_path, resp in (('jobs', fx6 / 'fixture_inventory_jobs.json', fx6 / 'valid_response_job_inputs.json'),
                                ('plain', fx6 / 'fixture_inventory.json', fx6 / 'valid_response.json'),
                                ('r57', fx6 / 'fixture_inventory.json', fx6 / 'valid_response_r57_null_c.json'),
                                ('q', fx6 / 'fixture_inventory.json', fx6 / 'valid_response_q_unverified.json'),
                                ('all', fx6 / 'fixture_inventory_jobs.json', fx6 / 'valid_response_relaxed_all.json'),
                                ('example', res6 / 'EXAMPLE_INVENTORY.json', res6 / 'EXAMPLE_RESPONSE.json')):
        code, out, err = run(PY + [ROUTE46F, 'convert', '--inventory', inv_path, '--response', resp, '--out-dir', work / f'route046f_{tag}'])
        carriers6[tag] = work / f'route046f_{tag}' / 'carrier.json'
        record(f'e_route046f_convert_{tag}', code == 0 and carriers6[tag].is_file(), (out + err)[-300:])
    ef2 = work / 'export_fixtures_v2'
    code, out, err = run(PY + [HERE / 'make_export_fixtures_v2.py'] + [carriers6[t] for t in ('jobs', 'plain', 'r57', 'q', 'all', 'example')] + [ef2])
    record('e_make_export_fixtures_v2', code == 0, err[-300:])
    index2 = json.loads((ef2 / 'FIXTURES_V2.json').read_text(encoding='utf-8'))['fixtures']
    valid2 = [x for x in index2 if x['valid']]
    invalid2 = [x for x in index2 if not x['valid']]
    record('e_fixture_counts_v2', len(valid2) >= 11 and len(invalid2) >= 17, {'valid': len(valid2), 'invalid': len(invalid2)})
    objs6 = {t: json.loads(carriers6[t].read_text(encoding='utf-8')) for t in carriers6}
    record('e_writer_placeholder_method_equals_test_implementation',
           all(same_value(wp.placeholder_copy(objs6[t]), placeholder_copy_independent(objs6[t])) for t in objs6)
           and len(mn_fields(objs6['jobs'])) == 18 and r57_ids(objs6['r57']) == ['R003', 'C001'] and q_ids(objs6['q']) == ['R006']
           and len(r57_ids(objs6['example'])) == 5 and len(q_ids(objs6['example'])) == 10 and mn_fields(objs6['example']))
    # writer004 itself still refuses the relaxed originals (documented divergences), and mode v1 is unchanged
    for tag, want in (('jobs', 'SELECTION_ONLY_ENGINEERING_ID'), ('r57', 'UNRESOLVED_ITEM_MUST_BE_HELD')):
        c2, o2, e2 = run(['node', wd / 'validate_carrier_v4.mjs', '--carrier', carriers6[tag]])
        record(f'e_writer004_refuses_original_{tag}', c2 == 1 and json.loads(e2).get('code') == want)
        code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', carriers6[tag], '--out', outs / f'v1mode_{tag}', '--writer-dir', wd])
        ref = json.loads(err.strip().splitlines()[-1]) if err.strip() else {}
        record(f'e_v1_mode_refuses_{tag}_unchanged', code == 1 and ref.get('code') == want
               and ref.get('stage') == 'gate:validate_carrier_v4' and not (outs / f'v1mode_{tag}').exists(), ref)
    c2, o2, e2 = run(['node', wd / 'validate_carrier_v4.mjs', '--carrier', carriers6['q']])
    record('e_writer004_accepts_q_unverified_original', c2 == 0 and json.loads(o2).get('status') == 'WRITER_STRUCTURAL_VALIDATION_ONLY')
    # independent copies for the node parity probe
    probe = []
    for x in valid2:
        text = Path(x['file']).read_bytes().decode('utf-8')
        obj = json.loads(text[1:] if text.startswith('﻿') else text)
        pc = work / f"v2_copy_{x['name']}.json"
        pc.write_text(json.dumps(placeholder_copy_independent(obj), ensure_ascii=True), encoding='ascii')
        probe.append((x, obj, pc))
    lp2 = work / 'parity_paths_v2.json'
    lp2.write_text(json.dumps([str(pc) for _, _, pc in probe]), encoding='utf-8')
    code, out, err = run(['node', HERE / 'parity_matrices.mjs', wd / 'writer004.mjs', lp2])
    node2 = json.loads(out) if code == 0 else []
    record('e_node_parity_probe_v2_ran', code == 0 and len(node2) == len(probe) and all(n['ok'] for n in node2), err[-300:])
    for (x, obj, pc), nr in zip(probe, node2):
        od = outs / ('v2_' + x['name'])
        code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', x['file'], '--out', od, '--writer-dir', wd, '--mode', 'v2'])
        if not record(f"e_write_v2_{x['name']}", code == 0 and (od / 'research-draft.xlsx').is_file(), err[-400:]):
            continue
        rc = json.loads((od / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
        exp = (od / 'EXPECTED_SAVED_VALUES.json').read_bytes()
        rx = rc.get('relaxations', {})
        cls = rx.get('classes', {})
        classes_ok = (rx.get('scanned') is True and cls.get('o13_m_n_selection_evidence', {}).get('fields') == mn_fields(obj)
                      and cls.get('r57_null_c_research_draft', {}).get('items') == r57_ids(obj)
                      and cls.get('r57_null_c_research_draft', {}).get('placeholder_reason_added_to')
                      == [i for i in r57_ids(obj) if next(r for r in obj['items'] + obj['components'] if r['id'] == i)['review_reasons'] == []]
                      and cls.get('o16_q_unverified_adoption', {}).get('items') == q_ids(obj)
                      and cls.get('o16_q_unverified_adoption', {}).get('source_adoption') == obj['metadata'].get('source_adoption'))
        if x['relaxed_expected']:
            ok = (rc['mode'] == 'v2' and rx.get('applied') is True and classes_ok
                  and rx['route_v4_port']['result'] == 'PASS' and rx['route_v4_port']['version'] == 'cps046f-route.v4.2'
                  and rx['route_v4_port']['sha256'] == sha(ROUTE46F.read_bytes()) == wp.ROUTE_V4_SHA256
                  and rx['route_v4_port']['sha256_pinned'] is True
                  and rx['writer004_cross_check_on_placeholder_copy']['result'] == 'BYTE_IDENTICAL'
                  and rc['gate']['result']['status'] == 'WRITER_STRUCTURAL_VALIDATION_ONLY'
                  and rc['expected_saved_values']['identical_to_writer004_prepareMatrices_output'] is False
                  and rc['expected_saved_values'].get('identical_to_writer004_prepareMatrices_on_placeholder_copy_except_documented_cells') is True
                  and any(l.startswith('Route v4.1 relaxations') for l in rc['limitations']) and rc['admitted'] is False)
            record(f"e_receipt_v2_{x['name']}", ok, {k: rc.get(k) for k in ('mode', 'relaxations')})
            # independent check: saved values == writer004 prepareMatrices on the copy, except the documented cells
            mine = json.loads(exp.decode('utf-8'))['sheets']
            theirs = json.loads(nr['text'])['sheets'] if nr.get('ok') else []
            diffs, outside, removed = documented_difference(mine, theirs, obj)
            n_added = len(cls['r57_null_c_research_draft']['placeholder_reason_added_to'])
            sel_rows = [ra for s_ in mine if s_['name'] == '來源與審查' for ra in s_['values'] if ra[0] == '欄位依據' and ra[1] in mn_fields(obj)]
            record(f"e_saved_values_equal_writer004_on_copy_except_documented_cells_{x['name']}",
                   len(mine) == len(theirs) == 4 and not outside and removed == n_added
                   and {d for d in diffs} == {tuple(['來源與審查'] + [int(v) for v in c_.split('!R')[1].split('C')]) for c_ in rx['saved_matrices_differ_from_placeholder_copy_only_in']['cells']}
                   and len(rx['saved_matrices_differ_from_placeholder_copy_only_in']['rows_added_in_copy']) == n_added
                   and all(ra[2] is None and ra[3] == '"已核對工程選取"' for ra in sel_rows) and len(sel_rows) == len(mn_fields(obj)),
                   {'outside': outside[:5], 'diffs': len(diffs), 'removed': removed, 'added': n_added})
        else:
            record(f"e_receipt_v2_{x['name']}", rc['mode'] == 'v2' and rx.get('applied') is False and classes_ok
                   and rc['cross_check']['result'] == 'BYTE_IDENTICAL' and exp == nr['text'].encode('utf-8'), rc.get('relaxations'))
            code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', x['file'], '--out', outs / ('v1_' + x['name']), '--writer-dir', wd])
            record(f"e_v2_without_copy_equals_v1_bytes_{x['name']}", code == 0
                   and (outs / ('v1_' + x['name']) / 'research-draft.xlsx').read_bytes() == (od / 'research-draft.xlsx').read_bytes()
                   and (outs / ('v1_' + x['name']) / 'EXPECTED_SAVED_VALUES.json').read_bytes() == exp)
        code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', od])
        qa = json.loads((od / 'SAVED_QA.json').read_text(encoding='utf-8')) if (od / 'SAVED_QA.json').is_file() else {}
        t = qa.get('totals', {})
        record(f"e_saved_qa_round_trip_v2_{x['name']}", code == 0 and qa.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS'
               and t.get('value_type_mismatches') == 0 and t.get('formulas') == 0 and t.get('formatting_failures') == 0, t)
        code, out, err = run(PY + [QA045, '--output', od, '--report', work / f"qa045_v2_{x['name']}.json"])
        record(f"e_checkpoint045_saved_qa_v2_{x['name']}", code == 0 and json.loads(out)['status'] == 'SAVED_ALL_CELL_VALUE_TYPE_PASS', (out + err)[-300:])
    for name in ('w01_job_inputs', 'w09_relaxed_all'):
        code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', ef2 / 'valid' / f'{name}.json', '--out', work / f'repeat_v2_{name}', '--writer-dir', wd, '--mode', 'v2'])
        record(f'e_repeat_build_v2_byte_identical_{name}', code == 0 and (work / f'repeat_v2_{name}' / 'research-draft.xlsx').read_bytes() == (outs / ('v2_' + name) / 'research-draft.xlsx').read_bytes()
               and (work / f'repeat_v2_{name}' / 'EXPECTED_SAVED_VALUES.json').read_bytes() == (outs / ('v2_' + name) / 'EXPECTED_SAVED_VALUES.json').read_bytes())
    for x in invalid2:
        od = outs / ('v2_' + x['name'])
        code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', x['file'], '--out', od, '--writer-dir', wd, '--mode', 'v2'])
        try:
            ref = json.loads(err.strip().splitlines()[-1])
        except (ValueError, IndexError):
            ref = {}
        record(f"e_refused_v2_{x['name']}", code == 1 and not od.exists() and ref.get('status') == 'REFUSED'
               and ref.get('code') == x['expected_code'] and ref.get('stage') == x['expected_stage'], ref)
    # the documented-difference guard is not vacuous: hidden changes to the copy's matrices are refused
    raw_all = carriers6['all'].read_bytes()
    scan_all = wp.relaxation_scan(raw_all)
    c_all = wp.js_parse(raw_all)
    cp_bytes = (json.dumps(wp.placeholder_copy(json.loads(raw_all.decode('utf-8'))), ensure_ascii=True, indent=1) + '\n').encode('ascii')
    c_cp = wp.js_parse(cp_bytes)
    m0, mc0 = wp.prepare_matrices(c_all), wp.prepare_matrices(c_cp)
    base_diff = wp.relaxation_matrix_difference(m0, mc0, c_all, c_cp, scan_all)
    record('e_diff_guard_baseline', base_diff['cells'] and len(base_diff['rows_added_in_copy']) == 1, base_diff['rows_added_in_copy'])
    def row_ix(mat, kind, ident):
        return next(i for i, r_ in enumerate(mat['review']) if r_[0] == kind and r_[1] == ident)
    def guard(name, mutate, want):
        mc = copy.deepcopy(mc0)
        mutate(mc)
        try:
            wp.relaxation_matrix_difference(m0, mc, c_all, c_cp, scan_all)
            got = None
        except wp.Refused as e:
            got = e.code
        record(f'e_diff_guard_{name}', got == want, got)
    guard('metadata_row_changed', lambda mc: mc['review'][row_ix(mc, '識別資料', '"adapter"')].__setitem__(4, '"x"'), 'RELAXATION_DIFF_OUTSIDE_DOCUMENTED_CELLS')
    guard('main_sheet_changed', lambda mc: mc['main'][1].__setitem__(2, 'x'), 'RELAXATION_DIFF_OUTSIDE_DOCUMENTED_CELLS')
    guard('status_of_item_without_r57', lambda mc: mc['review'][row_ix(mc, '項目', 'R001')].__setitem__(6, 'held'), 'RELAXATION_DIFF_OUTSIDE_DOCUMENTED_CELLS')
    guard('o13_row_status_column', lambda mc: mc['review'][row_ix(mc, '欄位依據', 'R001.M')].__setitem__(6, 'held'), 'RELAXATION_DIFF_OUTSIDE_DOCUMENTED_CELLS')
    guard('r57_raw_text_changed', lambda mc: mc['review'][row_ix(mc, '原文', 'R003.description')].__setitem__(4, '"x"'), 'RELAXATION_DIFF_OUTSIDE_DOCUMENTED_CELLS')
    guard('r57_status_not_held_in_copy', lambda mc: mc['review'][row_ix(mc, '項目', 'R003')].__setitem__(6, 'research_draft'), 'RELAXATION_DIFF_FORM')
    guard('placeholder_row_text', lambda mc: mc['review'][row_ix(mc, '待確認', 'C001.1')].__setitem__(4, '"other"'), 'RELAXATION_DIFF_FORM')
    guard('placeholder_row_removed', lambda mc: mc['review'].pop(row_ix(mc, '待確認', 'C001.1')), 'RELAXATION_DIFF_OUTSIDE_DOCUMENTED_CELLS')
    guard('nonitem_row_changed', lambda mc: mc['review'][-1].__setitem__(5, '"x"'), 'RELAXATION_DIFF_OUTSIDE_DOCUMENTED_CELLS')
    # the writer refuses a route tool whose bytes are not the pinned ones (046f review N3), before executing it,
    # and still checks VERSION and the documented relaxations of a tool whose bytes are pinned
    tool_dir = work / 'fake_route'
    tool_dir.mkdir()
    fake = tool_dir / 'cps046b_route.py'
    fake.write_text(ROUTE46F.read_text(encoding='utf-8') + '\n# one extra comment: same VERSION, different bytes\n', encoding='utf-8')
    def try_build(tool, out_name):
        try:
            wp.build(Path(carriers6['r57']), work / out_name, wd, mode='v2', route_tool=tool)
            return None
        except wp.Refused as e:
            return (e.code, e.stage)
    fr = try_build(fake, 'fake_route_out')
    record('e_v2_refuses_unpinned_route_bytes', fr == ('ROUTE_V4_TOOL_NOT_PINNED', 'gate:route_v4_port') and not (work / 'fake_route_out').exists(), fr)
    fake2 = tool_dir / 'cps046b_route_v4.py'
    fake2.write_text(ROUTE46F.read_text(encoding='utf-8').replace("VERSION = 'cps046f-route.v4.2'", "VERSION = 'cps046f-route.v4.1'", 1), encoding='utf-8')
    fr = try_build(fake2, 'fake_route2_out')
    pinned = wp.ROUTE_V4_SHA256
    try:
        wp.ROUTE_V4_SHA256 = sha(fake2.read_bytes())       # pin the fake: the VERSION check must still refuse it
        fr2 = try_build(fake2, 'fake_route3_out')
    finally:
        wp.ROUTE_V4_SHA256 = pinned
    record('e_v2_refuses_unpinned_route_version', fr == ('ROUTE_V4_TOOL_NOT_PINNED', 'gate:route_v4_port')
           and fr2 == ('ROUTE_V4_TOOL_VERSION', 'gate:route_v4_port') and not (work / 'fake_route2_out').exists()
           and not (work / 'fake_route3_out').exists(), [fr, fr2])

    # ------------------------------------------------ (f) node environment (review S1)
    sq = load(EXPORT / 'saved_qa.py', 'saved_qa_under_test')
    record('f_saved_qa_pins_equal_writer', {k: set(v) for k, v in sq.WRITER_PINS.items()} == {k: set(v) for k, v in wp.WRITER_PINS.items()}
           and sq.ARTIFACT_TOOL_STUB_SHA256 == wp.ARTIFACT_TOOL_STUB_SHA256 == '67134acad4326089bca7cd074c753bda88887a64c6a1499d15e1153d673796a4'
           and sq.ARTIFACT_TOOL_STUB_PACKAGE == wp.ARTIFACT_TOOL_STUB_PACKAGE and sq.RESOLVE_CJS == wp.RESOLVE_CJS and sq.RESOLVE_ESM == wp.RESOLVE_ESM
           and sq.NODE_ENV_KEEP == wp.NODE_ENV_KEEP == ('PATH', 'HOME', 'TMPDIR', 'LANG') and sq.NODE_ENV_KEEP_PREFIXES == wp.NODE_ENV_KEEP_PREFIXES == ('LC_',))
    # second review N-c: the node environment is an allowlist (writer and saved_qa give the same result)
    synthetic = {'PATH': '/bin', 'HOME': '/h', 'TMPDIR': '/t', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'LC_CTYPE': 'C.UTF-8',
                 'NODE_OPTIONS': '--import=x', 'NODE_PATH': '/x', 'NODE_EXTRA_CA_CERTS': '/x', 'OPENSSL_CONF': '/x', 'OPENSSL_MODULES': '/x',
                 'LD_PRELOAD': '/x.so', 'LD_LIBRARY_PATH': '/x', 'path': '/x', 'XLC_ALL': 'x', 'PYTHONPATH': '/x', 'SSL_CERT_FILE': '/x', 'CPS_ANY': '1'}
    want_kept = ['HOME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'PATH', 'TMPDIR']
    e_w, k_w, r_w = wp.node_env(synthetic)
    e_q, k_q, r_q = sq.node_env(synthetic)
    record('f_node_env_allowlist', k_w == k_q == want_kept and sorted(e_w) == want_kept and e_w == e_q
           and r_w == r_q == sorted(set(synthetic) - set(want_kept)), {'kept': k_w, 'removed': r_w})
    code, out, err = run(['node', '-e', wp.RESOLVE_CJS, wd.resolve() / 'writer004.mjs', wp.ARTIFACT_TOOL_SPECIFIER])
    stub_path = Path(json.loads(out)['resolved']) if code == 0 else None
    kept_now = sorted(k for k in os.environ if wp.node_env_allowed(k))
    removed_now = sorted(k for k in os.environ if not wp.node_env_allowed(k))
    for name in ('v01_base', 'v08_many_items'):
        ne = json.loads((outs / name / 'WRITER_RECEIPT.json').read_text(encoding='utf-8')).get('node_environment', {})
        at = ne.get('artifact_tool', {})
        record(f'f_receipt_node_environment_{name}', stub_path is not None and at.get('resolved_path') == str(stub_path)
               and at.get('esm_resolved_path') == str(stub_path) and at.get('sha256') == wp.ARTIFACT_TOOL_STUB_SHA256
               and ne.get('removed_variables') == removed_now and ne.get('kept_variables') == kept_now
               and set(kept_now) <= {'PATH', 'HOME', 'TMPDIR', 'LANG'} | {k for k in kept_now if k.startswith('LC_')}
               and ne.get('node', {}).get('realpath') == node_real and ne.get('node', {}).get('sha256') == node_sha
               and ne.get('node', {}).get('executable') == node_found and ne.get('node', {}).get('version') == node_version, ne)
    nev2 = json.loads((outs / 'v2_w09_relaxed_all' / 'WRITER_RECEIPT.json').read_text(encoding='utf-8')).get('node_environment', {})
    record('f_receipt_node_environment_v2', nev2.get('artifact_tool', {}).get('sha256') == wp.ARTIFACT_TOOL_STUB_SHA256
           and nev2.get('node', {}).get('realpath') == node_real and nev2.get('node', {}).get('sha256') == node_sha, nev2)
    base_obj = json.loads((ef / 'valid' / 'v01_base.json').read_text(encoding='utf-8'))
    part = copy.deepcopy(base_obj)
    part['items'][0]['status'] = 'partial'                  # writer004 refuses: REVIEW_STATUS_REQUIRED
    partial = work / 's1_partial_status.json'
    partial.write_text(json.dumps(part, ensure_ascii=False, indent=1), encoding='utf-8')
    c2, o2, e2 = run(['node', wd / 'validate_carrier_v4.mjs', '--carrier', partial])
    record('f_partial_status_refused_by_writer004', c2 == 1 and json.loads(e2).get('code') == 'REVIEW_STATUS_REQUIRED', e2[-200:])

    def writer_files_to(d):
        d.mkdir(parents=True)
        for f in wp.WRITER_PINS:
            shutil.copyfile(wd / f, d / f)

    def stub_to(d):
        d.mkdir(parents=True)
        shutil.copyfile(stub_path, d / 'index.mjs')
        shutil.copyfile(stub_path.parent / 'package.json', d / 'package.json')

    def attack(tag, writer_dir, carrier, want, env=None, stage='gate:node_environment'):
        """writer004 accepts the partial-status carrier when node runs the attack directly; the writer refuses."""
        c3, o3, e3 = run(['node', writer_dir / 'validate_carrier_v4.mjs', '--carrier', partial], env=env)
        record(f'f_{tag}_attack_effective_on_direct_node', c3 == 0 and json.loads(o3 or '{}').get('status') == 'WRITER_STRUCTURAL_VALIDATION_ONLY',
               (o3 + e3)[-200:])
        for cname, cpath in (('partial', partial), ('valid', ef / 'valid' / 'v01_base.json')):
            od = work / f's1_{tag}_{cname}_out'
            c4, o4, e4 = run(PY + [EXPORT / 'writer_portable.py', '--carrier', cpath, '--out', od, '--writer-dir', writer_dir], env=env)
            ref = refusal(e4)
            record(f'f_{tag}_refused_{cname}', c4 == 1 and not od.exists() and ref.get('code') == want and ref.get('stage') == stage, ref)
    # the reviewer's planted module under <writer-dir>/node_modules, resolved before the stub
    pl = work / 's1_planted'
    writer_files_to(pl / 'writer')
    stub_to(pl / 'node_modules' / '@oai' / 'artifact-tool')
    (pl / 'writer' / 'node_modules' / '@oai' / 'artifact-tool').mkdir(parents=True)
    (pl / 'writer' / 'node_modules' / '@oai' / 'artifact-tool' / 'index.mjs').write_text(PLANTED_MODULE, encoding='utf-8')
    shutil.copyfile(stub_path.parent / 'package.json', pl / 'writer' / 'node_modules' / '@oai' / 'artifact-tool' / 'package.json')
    attack('planted_module', pl / 'writer', partial, 'ARTIFACT_TOOL_NOT_PINNED')
    # conditional exports: require resolves the pinned stub, import loads another file
    ce = work / 's1_conditional_exports'
    writer_files_to(ce / 'writer')
    pkgd = ce / 'node_modules' / '@oai' / 'artifact-tool'
    stub_to(pkgd)
    (pkgd / 'evil.mjs').write_text(PLANTED_MODULE, encoding='utf-8')
    (pkgd / 'package.json').write_text(json.dumps(dict(wp.ARTIFACT_TOOL_STUB_PACKAGE, exports={'import': './evil.mjs', 'require': './index.mjs'})), encoding='utf-8')
    attack('conditional_exports', ce / 'writer', partial, 'ARTIFACT_TOOL_RESOLUTION_DIVERGES')
    # writer files symlinked to another directory whose node_modules holds the planted module
    sl = work / 's1_symlinked_writer'
    writer_files_to(sl / 'elsewhere')
    (sl / 'elsewhere' / 'node_modules' / '@oai' / 'artifact-tool').mkdir(parents=True)
    (sl / 'elsewhere' / 'node_modules' / '@oai' / 'artifact-tool' / 'index.mjs').write_text(PLANTED_MODULE, encoding='utf-8')
    shutil.copyfile(stub_path.parent / 'package.json', sl / 'elsewhere' / 'node_modules' / '@oai' / 'artifact-tool' / 'package.json')
    (sl / 'writer').mkdir()
    for f in wp.WRITER_PINS:
        (sl / 'writer' / f).symlink_to(sl / 'elsewhere' / f)
    stub_to(sl / 'node_modules' / '@oai' / 'artifact-tool')
    attack('symlinked_writer_files', sl / 'writer', partial, 'WRITER_FILE_OUTSIDE_WRITER_DIR', stage='gate')
    # a package.json other than the documented one, with the pinned index.mjs
    pj = work / 's1_package_json'
    writer_files_to(pj / 'writer')
    stub_to(pj / 'node_modules' / '@oai' / 'artifact-tool')
    (pj / 'node_modules' / '@oai' / 'artifact-tool' / 'package.json').write_text(
        json.dumps(dict(wp.ARTIFACT_TOOL_STUB_PACKAGE, version='9.9.9')), encoding='utf-8')
    c4, o4, e4 = run(PY + [EXPORT / 'writer_portable.py', '--carrier', ef / 'valid' / 'v01_base.json', '--out', work / 's1_pj_out', '--writer-dir', pj / 'writer'])
    record('f_package_json_not_documented_refused', c4 == 1 and refusal(e4).get('code') == 'ARTIFACT_TOOL_PACKAGE_UNEXPECTED' and not (work / 's1_pj_out').exists(), e4[-300:])
    # NODE_OPTIONS --import patch: effective on direct node, stripped by the writer
    evil = work / 's1_node_options' / 'evil_import.mjs'
    evil.parent.mkdir()
    evil.write_text(INCLUDES_PATCH, encoding='utf-8')
    env_opt = dict(os.environ, NODE_OPTIONS='--import=' + evil.as_uri())
    c3, o3, e3 = run(['node', wd / 'validate_carrier_v4.mjs', '--carrier', partial], env=env_opt)
    record('f_node_options_attack_effective_on_direct_node', c3 == 0, (o3 + e3)[-200:])
    od = work / 's1_node_options_partial_out'
    c4, o4, e4 = run(PY + [EXPORT / 'writer_portable.py', '--carrier', partial, '--out', od, '--writer-dir', wd], env=env_opt)
    record('f_node_options_stripped_partial_refused_by_writer004', c4 == 1 and refusal(e4).get('code') == 'REVIEW_STATUS_REQUIRED'
           and refusal(e4).get('stage') == 'gate:validate_carrier_v4' and not od.exists(), e4[-300:])
    # NODE_PATH: a stub reachable only through NODE_PATH is not used (node ESM ignores it; the writer removes it)
    np_dir = work / 's1_node_path'
    writer_files_to(np_dir / 'writer')
    stub_to(np_dir / 'global' / '@oai' / 'artifact-tool')
    env_np = dict(os.environ, NODE_PATH=str(np_dir / 'global'))
    c5, o5, e5 = run(['node', '-e', wp.RESOLVE_CJS, np_dir / 'writer' / 'writer004.mjs', wp.ARTIFACT_TOOL_SPECIFIER])
    c6, o6, e6 = run(['node', '-e', wp.RESOLVE_CJS, np_dir / 'writer' / 'writer004.mjs', wp.ARTIFACT_TOOL_SPECIFIER], env=env_np)
    od = work / 's1_node_path_out'
    c4, o4, e4 = run(PY + [EXPORT / 'writer_portable.py', '--carrier', ef / 'valid' / 'v01_base.json', '--out', od, '--writer-dir', np_dir / 'writer'], env=env_np)
    record('f_node_path_not_used', c5 != 0 and c6 == 0 and c4 == 1 and refusal(e4).get('code') == 'ARTIFACT_TOOL_UNRESOLVED' and not od.exists(),
           {'clean_resolve_exit': c5, 'node_path_resolve_exit': c6, 'refusal': refusal(e4)})
    # with NODE_OPTIONS and NODE_PATH set, a valid carrier gives the same bytes, and the receipt names the removed variables
    env_both = dict(os.environ, NODE_OPTIONS='--import=' + evil.as_uri(), NODE_PATH=str(np_dir / 'global'))
    od = work / 's1_env_valid_out'
    c4, o4, e4 = run(PY + [EXPORT / 'writer_portable.py', '--carrier', ef / 'valid' / 'v01_base.json', '--out', od, '--writer-dir', wd], env=env_both)
    rc = json.loads((od / 'WRITER_RECEIPT.json').read_text(encoding='utf-8')) if c4 == 0 else {}
    record('f_node_variables_removed_same_bytes', c4 == 0 and (od / 'research-draft.xlsx').read_bytes() == (outs / 'v01_base' / 'research-draft.xlsx').read_bytes()
           and (od / 'EXPECTED_SAVED_VALUES.json').read_bytes() == (outs / 'v01_base' / 'EXPECTED_SAVED_VALUES.json').read_bytes()
           and {'NODE_OPTIONS', 'NODE_PATH'} <= set(rc.get('node_environment', {}).get('removed_variables', [])), e4[-300:])
    # the second review's A3: OPENSSL_CONF naming a missing provider aborts node at startup (a real provider .so would run
    # native code inside node). Effective on direct node; the allowlist removes it (with LD_LIBRARY_PATH and any other
    # variable), so the writer gives the same bytes, and saved_qa's provenance check is unaffected too.
    cnf = work / 's1_openssl' / 'openssl.cnf'
    cnf.parent.mkdir()
    cnf.write_text('nodejs_conf = nc\n[nc]\nproviders = pv\n[pv]\nevil = evs\n[evs]\nmodule = /nonexistent/evil_provider.so\nactivate = 1\n', encoding='utf-8')
    env_ssl = dict(NODE_CLEAN_ENV, OPENSSL_CONF=str(cnf))
    c5, o5, e5 = run(['node', '-e', "require('node:crypto').createHash('sha256');process.stdout.write('ran')"], env=NODE_CLEAN_ENV)
    c6, o6, e6 = run(['node', '-e', "require('node:crypto').createHash('sha256');process.stdout.write('ran')"], env=env_ssl)
    record('f_openssl_conf_attack_effective_on_direct_node', c5 == 0 and o5 == 'ran' and c6 != 0 and o6 != 'ran', {'clean': c5, 'openssl_conf': c6, 'stderr': e6[-200:]})
    env_bad = dict(os.environ, OPENSSL_CONF=str(cnf), LD_LIBRARY_PATH=str(work / 's1_openssl' / 'nonexistent'), CPS_TEST_UNLISTED_VARIABLE='1')
    od = work / 's1_openssl_valid_out'
    c4, o4, e4 = run(PY + [EXPORT / 'writer_portable.py', '--carrier', ef / 'valid' / 'v01_base.json', '--out', od, '--writer-dir', wd], env=env_bad)
    ne = json.loads((od / 'WRITER_RECEIPT.json').read_text(encoding='utf-8')).get('node_environment', {}) if c4 == 0 else {}
    record('f_openssl_conf_removed_same_bytes', c4 == 0 and (od / 'research-draft.xlsx').read_bytes() == (outs / 'v01_base' / 'research-draft.xlsx').read_bytes()
           and (od / 'EXPECTED_SAVED_VALUES.json').read_bytes() == (outs / 'v01_base' / 'EXPECTED_SAVED_VALUES.json').read_bytes()
           and {'OPENSSL_CONF', 'LD_LIBRARY_PATH', 'CPS_TEST_UNLISTED_VARIABLE'} <= set(ne.get('removed_variables', []))
           and not {'OPENSSL_CONF', 'LD_LIBRARY_PATH', 'CPS_TEST_UNLISTED_VARIABLE'} & set(ne.get('kept_variables', ['?']))
           and ne.get('environment', '').startswith('allowlist'), {'stderr': e4[-300:], 'node_environment': ne})
    rp = work / 's1_openssl_saved_qa.json'
    c4, o4, e4 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', outs / 'v01_base', '--report', rp, '--carrier', ef / 'valid' / 'v01_base.json', '--writer-dir', wd], env=env_bad)
    pv = qa_report(rp).get('expected_provenance', {})
    record('f_openssl_conf_saved_qa_provenance_unaffected', c4 == 0 and pv.get('result') == 'PASS'
           and 'OPENSSL_CONF' in pv.get('node_environment', {}).get('removed_variables', [])
           and 'OPENSSL_CONF' not in pv.get('node_environment', {}).get('kept_variables', ['OPENSSL_CONF']), pv)

    # ------------------------------------------------ (g) saved_qa structure: the reviewer's 22 tampers (review S2)
    mt = load(HERE / 'make_tamper_fixtures.py', 'make_tamper_fixtures_under_test')
    fid = work / 'tamper_base_fidelity.json'
    code, out, err = run(PY + [HERE / 'make_tamper_fixtures.py', 'carrier', ef / 'valid' / 'v01_base.json', fid])
    fid_out = work / 'tamper_base_output'
    code2, out2, err2 = run(PY + [EXPORT / 'writer_portable.py', '--carrier', fid, '--out', fid_out, '--writer-dir', wd])
    record('g_fidelity_probe_written', code == 0 and code2 == 0, (err + err2)[-300:])
    code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', fid_out])
    code2, out2, err2 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', fid_out, '--report', work / 'tamper_base_prov.json', '--carrier', fid, '--writer-dir', wd])
    q1, q2 = qa_report(fid_out / 'SAVED_QA.json'), qa_report(work / 'tamper_base_prov.json')
    record('g_fidelity_probe_saved_qa_passes', code == 0 and code2 == 0 and q1.get('status') == q2.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS'
           and q1['expected_provenance']['checked'] is False and q2['expected_provenance'].get('result') == 'PASS',
           {'no_prov': q1.get('findings'), 'prov': q2.get('findings')})
    td = work / 'tampers'
    code, out, err = run(PY + [HERE / 'make_tamper_fixtures.py', 'tamper', fid_out, td])
    tampers = json.loads((td / 'TAMPERS.json').read_text(encoding='utf-8'))['tampers'] if code == 0 else []
    reviewer22 = [t for t in tampers if t['group'] == 'reviewer'] + [t for t in tampers if t['name'].endswith(('_T21', '_T22'))]
    record('g_tamper_counts', code == 0 and len(reviewer22) == 22 and len([t for t in tampers if t['group'] == 'extra']) >= 16
           and sorted(t['name'][:3] for t in tampers if t['group'] == 'review2') == ['N01', 'N02', 'N03', 'N04', 'N05', 'N06', 'N07', 'N10', 'N11']
           and sorted(t['name'][:3] for t in tampers if t['group'] == 'review3') == ['B01', 'B02', 'B03', 'B04', 'B05', 'B06']
           and sorted(t['name'][:4] for t in tampers if t['group'] == 'o34') == ['O34a', 'O34b'], err[-300:])
    for t in tampers:
        d = Path(t['dir'])
        c1, o1, e1 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d])
        q = qa_report(d / 'SAVED_QA.json')
        fnd = q.get('findings', {})
        crash = 'Traceback' in e1 or not q
        if t['passes_without_provenance']:
            ok = c1 == 0 and q.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' and q['expected_provenance']['checked'] is False
        else:
            ok = c1 == 1 and q.get('status') == 'SAVED_QA_FAILED' and (fnd if t['finding'] == 'any' else t['finding'] in fnd)
        record(f"g_saved_qa_catches_{t['name']}" if not t['passes_without_provenance'] else f"g_saved_qa_without_provenance_cannot_catch_{t['name']}",
               ok and not crash, {'status': q.get('status'), 'findings': {k: v['count'] for k, v in fnd.items()}, 'stderr': e1[-300:]})
        c2, o2, e2 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d, '--report', d / 'SAVED_QA_PROVENANCE.json', '--carrier', fid, '--writer-dir', wd] + checker)
        q = qa_report(d / 'SAVED_QA_PROVENANCE.json')
        fnd = q.get('findings', {})
        pv = q.get('expected_provenance', {})
        # v3 (second review F1(a)): every tamper changes the xlsx, and the rerun's xlsx is compared whatever the receipt mode
        record(f"h_provenance_catches_{t['name']}", c2 == 1 and q.get('status') == 'SAVED_QA_FAILED' and t.get('provenance_finding') in fnd
               and pv.get('xlsx_byte_identical') is False and (t['finding'] in (None, 'any') or t['finding'] in fnd)
               and 'Traceback' not in e2, {'status': q.get('status'), 'findings': {k: v['count'] for k, v in fnd.items()},
                                           'xlsx_byte_identical': pv.get('xlsx_byte_identical')})

    # ------------------------------------------------ (h) provenance of EXPECTED (review S3)
    def pinned_node_ok(q, writer004_check):
        """third review G2: every node call of the check ran the pinned checker node (realpath and sha256 recorded for the
        writer004 check and for the rerun), and the report says so."""
        pv, pre = q.get('expected_provenance', {}), q.get('cps_evidence_preconditions', {})
        cn, rn, wn = pv.get('checker_node') or {}, pv.get('rerun_node') or {}, pv.get('writer004_check_node')
        return (cn.get('pinned') is True and cn.get('sha256_verified') is True and cn.get('realpath') == node_real
                and cn.get('sha256') == cn.get('sha256_after_check') == node_sha and rn.get('realpath') == node_real
                and rn.get('sha256') == node_sha and (wn == {'realpath': node_real, 'sha256': node_sha, 'pinned': True} if writer004_check else wn is None)
                and pre.get('pinned_checker_node') is True and pre.get('all_checked_here_met') is True
                and pre.get('checker_node', {}).get('sha256') == node_sha)
    for x in valid:
        od = outs / x['name']
        rp = work / f"prov_{x['name']}.json"
        code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', od, '--report', rp, '--carrier', x['file'], '--writer-dir', wd] + checker)
        q = qa_report(rp)
        pv = q.get('expected_provenance', {})
        record(f"h_provenance_v1_pass_{x['name']}", code == 0 and q.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' and pv.get('result') == 'PASS'
               and pv.get('expected_byte_identical') is True and pv.get('xlsx_byte_identical') is True and pv.get('receipt_mode') == 'v1'
               and pv.get('writer004_expected_byte_identical') is True and pv.get('rerun_mode') == 'v2'
               and pv.get('node_environment', {}).get('artifact_tool_sha256') == wp.ARTIFACT_TOOL_STUB_SHA256
               and pinned_node_ok(q, writer004_check=True) and pv.get('receipt_claims', {}).get('match') is True
               and pv['receipt_claims'].get('compared_fields') == list(sq.RECEIPT_CLAIM_FIELDS), {'findings': q.get('findings'), 'provenance': pv})
    for x in valid2:
        od = outs / ('v2_' + x['name'])
        rp = work / f"prov_v2_{x['name']}.json"
        code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', od, '--report', rp, '--carrier', x['file'], '--writer-dir', wd] + checker)
        q = qa_report(rp)
        pv = q.get('expected_provenance', {})
        rx = json.loads((od / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))['relaxations']
        classes_from_rerun = pv.get('rerun_relaxation_classes') == {k: {kk: vv for kk, vv in v.items() if kk != 'neutralization'}
                                                                    for k, v in rx.get('classes', {}).items()}
        cells_from_rerun = pv.get('rerun_documented_cells') == rx.get('saved_matrices_differ_from_placeholder_copy_only_in')
        record(f"h_provenance_v2_pass_{x['name']}", code == 0 and q.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' and pv.get('result') == 'PASS'
               and pv.get('expected_byte_identical') is True and pv.get('xlsx_byte_identical') is True and pv.get('receipt_mode') == 'v2'
               and 'writer004_expected_byte_identical' not in pv and pinned_node_ok(q, writer004_check=False)
               and pv.get('receipt_claims', {}).get('match') is True and classes_from_rerun and cells_from_rerun
               and (pv.get('rerun_documented_cells') is not None) == (x['relaxed_expected'] is True),
               {'findings': q.get('findings'), 'provenance': pv})
    # consistent EXPECTED+xlsx tampers of a v2 output (full rerun), and a v2 view-only tamper with a consistent receipt
    v2src, v2car = outs / 'v2_w09_relaxed_all', ef2 / 'valid' / 'w09_relaxed_all.json'
    td2 = work / 'tampers_v2'
    code, out, err = run(PY + [HERE / 'make_tamper_fixtures.py', 'tamper', v2src, td2, '--consistent-only'])
    tampers2 = json.loads((td2 / 'TAMPERS.json').read_text(encoding='utf-8'))['tampers'] if code == 0 else []
    zd = td2 / 'V2_zoom_view_receipt_updated'
    zd.mkdir()
    for f in ('EXPECTED_SAVED_VALUES.json', 'WRITER_RECEIPT.json'):
        shutil.copyfile(v2src / f, zd / f)
    mt.write_tampered(v2src / 'research-draft.xlsx', zd / 'research-draft.xlsx', {mt.S1: mt.sub1(r'<sheetView ', '<sheetView zoomScale="10" ')})
    mt.update_receipt(zd)
    tampers2.append({'name': 'V2_zoom_view_receipt_updated', 'dir': str(zd), 'passes_without_provenance': False, 'finding': 'worksheet_structure'})
    record('h_v2_tamper_counts', len(tampers2) == 4, err[-300:])
    for t in tampers2:
        d = Path(t['dir'])
        c1, o1, e1 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d])
        q1 = qa_report(d / 'SAVED_QA.json')
        c2, o2, e2 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d, '--report', d / 'SAVED_QA_PROVENANCE.json', '--carrier', v2car, '--writer-dir', wd])
        q2 = qa_report(d / 'SAVED_QA_PROVENANCE.json')
        no_prov_ok = (q1.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS') if t['passes_without_provenance'] else (
            q1.get('status') == 'SAVED_QA_FAILED' and t['finding'] in q1.get('findings', {}))
        record(f"h_provenance_v2_catches_{t['name']}", no_prov_ok and c2 == 1 and 'provenance' in q2.get('findings', {}),
               {'no_prov': q1.get('status'), 'prov_findings': q2.get('findings', {}).get('provenance')})
    # the carrier must be the receipt's carrier
    rp = work / 'prov_wrong_carrier.json'
    code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', outs / 'v01_base', '--report', rp, '--carrier', ef / 'valid' / 'v03_numeric_edges.json', '--writer-dir', wd])
    fnd = qa_report(rp).get('findings', {}).get('provenance', {}).get('first', [])
    record('h_provenance_wrong_carrier', code == 1 and any('carrier sha256 differs' in f.get('check', '') for f in fnd), fnd[:3])
    # a relaxed v2 output whose receipt claims mode v1: writer004 refuses the original carrier
    md = work / 'prov_mode_claim'
    shutil.copytree(v2src, md)
    (md / 'SAVED_QA.json').unlink()
    rr = json.loads((md / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
    rr['mode'] = 'v1'
    (md / 'WRITER_RECEIPT.json').write_text(json.dumps(rr, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', md, '--carrier', v2car, '--writer-dir', wd] + checker)
    q = qa_report(md / 'SAVED_QA.json')
    record('h_provenance_receipt_mode_v1_on_relaxed_output', code == 1 and q.get('expected_provenance', {}).get('result') == 'WRITER004_REFUSED'
           and q['findings']['provenance']['first'][0].get('code') in ('SELECTION_ONLY_ENGINEERING_ID', 'UNRESOLVED_ITEM_MUST_BE_HELD')
           and q['expected_provenance'].get('xlsx_byte_identical') is True and q['expected_provenance'].get('rerun_relaxations_applied') is True
           and q['findings'].get('receipt_claim_mismatch', {}).get('first', [{}])[0].get('fields') == ['mode'],
           q.get('expected_provenance'))
    # the provenance rerun uses the pinned node environment: the planted writer directory is refused
    rp = work / 'prov_planted.json'
    code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', outs / 'v01_base', '--report', rp, '--carrier', ef / 'valid' / 'v01_base.json', '--writer-dir', pl / 'writer'])
    q = qa_report(rp)
    record('h_provenance_refuses_planted_writer_dir', code == 1 and q.get('expected_provenance', {}).get('result') == 'NODE_ENVIRONMENT_REFUSED', q.get('expected_provenance'))
    rp = work / 'prov_planted_v2.json'
    code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', v2src, '--report', rp, '--carrier', v2car, '--writer-dir', pl / 'writer'])
    q = qa_report(rp)
    record('h_provenance_v2_refuses_planted_writer_dir', code == 1 and q.get('expected_provenance', {}).get('result') == 'WRITER_RERUN_FAILED'
           and 'ARTIFACT_TOOL_NOT_PINNED' in json.dumps(q.get('findings', {})), q.get('expected_provenance'))
    code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', outs / 'v01_base', '--report', work / 'prov_usage.json', '--carrier', ef / 'valid' / 'v01_base.json'])
    record('h_provenance_usage_carrier_needs_writer_dir', code == 2 and not (work / 'prov_usage.json').exists(), err[-200:])
    # receipt-mode downgrade (second review F2): a --mode v2 output of the fidelity probe (no O13/R57: the v1 bytes), tampered,
    # with the receipt mode kept or edited to v1. The rerun's xlsx is compared whatever the mode says.
    fid_v2 = work / 'tamper_base_output_v2'
    code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', fid, '--out', fid_v2, '--writer-dir', wd, '--mode', 'v2'])
    rc2 = json.loads((fid_v2 / 'WRITER_RECEIPT.json').read_text(encoding='utf-8')) if code == 0 else {}
    record('h_fidelity_probe_v2_equals_v1_bytes', code == 0 and rc2.get('mode') == 'v2' and rc2['relaxations']['applied'] is False
           and (fid_v2 / 'research-draft.xlsx').read_bytes() == (fid_out / 'research-draft.xlsx').read_bytes()
           and (fid_v2 / 'EXPECTED_SAVED_VALUES.json').read_bytes() == (fid_out / 'EXPECTED_SAVED_VALUES.json').read_bytes(), err[-300:])
    tdd = work / 'tampers_downgrade'
    code, out, err = run(PY + [HERE / 'make_tamper_fixtures.py', 'downgrade', fid_v2, tdd])
    tamd = json.loads((tdd / 'TAMPERS.json').read_text(encoding='utf-8'))['tampers'] if code == 0 else []
    record('h_downgrade_tamper_counts', code == 0 and [t['name'][:2] for t in tamd] == ['D1', 'D2', 'D3'], err[-300:])
    for t in tamd:
        d = Path(t['dir'])
        c1, o1, e1 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d])
        q1 = qa_report(d / 'SAVED_QA.json')
        if t['passes_without_provenance']:
            no_prov_ok = c1 == 0 and q1.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS'
        else:
            no_prov_ok = c1 == 1 and t['finding'] in q1.get('findings', {})
        c2, o2, e2 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d, '--report', d / 'SAVED_QA_PROVENANCE.json', '--carrier', fid, '--writer-dir', wd] + checker)
        q2 = qa_report(d / 'SAVED_QA_PROVENANCE.json')
        pv, fnd = q2.get('expected_provenance', {}), q2.get('findings', {})
        claim_fields = [f for e in fnd.get('receipt_claim_mismatch', {}).get('first', []) for f in e.get('fields', [])]
        ok = (no_prov_ok and c2 == 1 and q2.get('status') == 'SAVED_QA_FAILED' and 'provenance' in fnd and pv.get('result') == 'FAILED'
              and pv.get('receipt_mode') == t['receipt_mode'] and pv.get('xlsx_byte_identical') is False and pv.get('expected_byte_identical') is True
              and claim_fields == t['receipt_claim_fields']          # v4 (third review G3): a v1 claim on a v2 receipt
              and (t['finding'] is None and set(fnd) == {'provenance'} | ({'receipt_claim_mismatch'} if t['receipt_claim_fields'] else set())
                   or t['finding'] in fnd)
              and (t['receipt_mode'] != 'v1' or pv.get('writer004_expected_byte_identical') is True)
              and 'Traceback' not in e1 + e2)
        record(f"h_provenance_catches_downgrade_{t['name']}", ok, {'no_prov': [q1.get('status'), list(q1.get('findings', {}))], 'claim_fields': claim_fields,
                                                                  'prov': [q2.get('status'), {k: v['count'] for k, v in fnd.items()}],
                                                                  'provenance': {k: pv.get(k) for k in ('receipt_mode', 'result', 'xlsx_byte_identical',
                                                                                                         'expected_byte_identical', 'writer004_expected_byte_identical')}})

    # ------------------------------------------------ third review G3: receipt claims (its p1/)
    # Receipt claims edited, xlsx and EXPECTED unchanged: without provenance they pass (the receipt claims are not checked);
    # with --carrier/--writer-dir each edit of a compared field is a receipt_claim_mismatch naming exactly that field.
    n_receipt_tampers = 0
    for src_dir, car, tag, n_want in ((v2src, v2car, 'relaxed', 16), (fid_out, fid, 'plain', 5)):
        trd = work / f'tampers_receipt_{tag}'
        code, out, err = run(PY + [HERE / 'make_tamper_fixtures.py', 'receipt', src_dir, trd])
        tr = json.loads((trd / 'TAMPERS.json').read_text(encoding='utf-8'))['tampers'] if code == 0 else []
        n_receipt_tampers += len(tr)
        record(f'h_receipt_tamper_counts_{tag}', code == 0 and len(tr) == n_want, err[-300:])
        base_rx = json.loads((src_dir / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))['relaxations']
        for t in tr:
            d = Path(t['dir'])
            c1, o1, e1 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d])
            q1 = qa_report(d / 'SAVED_QA.json')
            c2, o2, e2 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d, '--report', d / 'SAVED_QA_PROVENANCE.json', '--carrier', car,
                                   '--writer-dir', wd] + checker)
            q2 = qa_report(d / 'SAVED_QA_PROVENANCE.json')
            pv, fnd = q2.get('expected_provenance', {}), q2.get('findings', {})
            got = [f for e in fnd.get('receipt_claim_mismatch', {}).get('first', []) for f in e.get('fields', [])]
            common = (c1 == 0 and q1.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' and pv.get('xlsx_byte_identical') is True
                      and pv.get('expected_byte_identical') is True and 'Traceback' not in e1 + e2)
            if t['receipt_claim_fields']:
                want_result = 'WRITER004_REFUSED' if t['name'].startswith('P2_') else 'FAILED'
                ok = (common and c2 == 1 and q2.get('status') == 'SAVED_QA_FAILED' and got == t['receipt_claim_fields'] and pv.get('result') == want_result
                      and pv.get('receipt_claims', {}).get('match') is False and pv['receipt_claims'].get('mismatched_fields') == got
                      and q2.get('cps_evidence_preconditions', {}).get('all_checked_here_met') is False)
                name = f"h_receipt_claim_edit_fails_{t['name']}"
            else:          # not a compared field: shown, not evidence
                ok = (common and c2 == 0 and q2.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' and got == [] and pv.get('result') == 'PASS'
                      and pv.get('receipt_claims', {}).get('match') is True)
                name = f"h_receipt_uncompared_field_edit_passes_{t['name']}"
            if t['name'].startswith(('P1_', 'P1g_')):
                ok = ok and (pv.get('receipt_node') or {}).get('executable') == '/invented/node'       # the claim is visible
            if t['name'].startswith('P1_'):           # the relaxation classes and documented cells come from the rerun
                r57 = (pv.get('rerun_relaxation_classes') or {}).get('r57_null_c_research_draft', {})
                ok = (ok and r57.get('items') == base_rx['classes']['r57_null_c_research_draft']['items'] and r57.get('items')
                      and pv.get('rerun_documented_cells') == base_rx['saved_matrices_differ_from_placeholder_copy_only_in']
                      and len(pv['rerun_documented_cells']['cells']) > 0)
            record(name, ok, {'no_prov': q1.get('status'), 'prov': q2.get('status'), 'result': pv.get('result'), 'fields': got,
                              'want': t['receipt_claim_fields'], 'stderr': (e1 + e2)[-300:]})
    # the v1 claim mapping: a v1 run and a v2 run of a carrier without O13/R57 write the same compared fields except mode and
    # relaxations, and the v1 relaxations are exactly V1_RELAXATIONS
    pairs = [(fid_out, fid_v2)] + [(d, outs / ('v2_' + d.name[3:])) for d in sorted(outs.iterdir()) if d.name.startswith('v1_') and (d / 'WRITER_RECEIPT.json').is_file()]
    mapping = {}
    for a1, a2 in pairs:
        r1 = json.loads((a1 / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
        r2 = json.loads((a2 / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
        k1, k2 = sq.receipt_claims(r1), sq.receipt_claims(r2)
        mapping[a1.name] = (r1['mode'] == 'v1' and r2['mode'] == 'v2' and r1['relaxations'] == sq.V1_RELAXATIONS and r2['relaxations']['applied'] is False
                            and r2['relaxations']['scanned'] is True
                            and [k for k in sq.RECEIPT_CLAIM_FIELDS if sq.canonical(k1[k]) != sq.canonical(k2[k])] == ['mode', 'relaxations'])
    record('h_v1_receipt_claims_equal_v2_except_mode_and_relaxations', len(mapping) >= 3 and all(mapping.values()), mapping)
    # cps_evidence_preconditions in the four combinations, and with a pinned checker node
    combos = {}
    for tag, extra in (('no_provenance', []), ('provenance_unpinned', ['--carrier', ef / 'valid' / 'v01_base.json', '--writer-dir', wd]),
                       ('provenance_pinned_no_formatting', ['--carrier', ef / 'valid' / 'v01_base.json', '--writer-dir', wd, '--no-formatting'] + checker),
                       ('provenance_pinned', ['--carrier', ef / 'valid' / 'v01_base.json', '--writer-dir', wd] + checker)):
        rp = work / f'pre_{tag}.json'
        c, o, e = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', outs / 'v01_base', '--report', rp] + extra)
        q = qa_report(rp)
        pre = q.get('cps_evidence_preconditions', {})
        combos[tag] = [c, q.get('status'), pre.get('provenance_checked'), pre.get('formatting_checked'), pre.get('pinned_checker_node'),
                       pre.get('all_checked_here_met')]
    ps = 'SAVED_ALL_CELL_VALUE_TYPE_PASS'
    record('h_evidence_preconditions_combinations', combos == {'no_provenance': [0, ps, False, True, False, False],
                                                               'provenance_unpinned': [0, ps, True, True, False, False],
                                                               'provenance_pinned_no_formatting': [0, ps, True, False, True, False],
                                                               'provenance_pinned': [0, ps, True, True, True, True]}, combos)

    # ------------------------------------------------ third review G2: the node binary (its p2/ wrapper)
    # The reviewer's wrapper: a shell script that runs the real node with --import of the Array.prototype.includes patch
    # (here it also appends a line to a log, so the tests can see whether it ran).
    g2 = work / 'g2_node_wrapper'
    evilbin = g2 / 'evilbin'
    evilbin.mkdir(parents=True)
    (evilbin / 'patch.mjs').write_text(INCLUDES_PATCH, encoding='utf-8')
    marker = g2 / 'wrapper_ran.log'
    wnode = evilbin / 'node'
    wnode.write_text('#!/bin/sh\n' + f'echo ran >> {shlex.quote(str(marker))}\n'
                     + f'exec {shlex.quote(node_real)} --import={shlex.quote((evilbin / "patch.mjs").as_uri())} "$@"\n', encoding='utf-8')
    wnode.chmod(0o755)
    wsha, wreal = sha(wnode.read_bytes()), os.path.realpath(wnode)

    def wrapper_runs():
        return len(marker.read_text(encoding='utf-8').splitlines()) if marker.is_file() else 0
    env_path = dict(os.environ, PATH=str(evilbin) + os.pathsep + os.environ.get('PATH', ''))
    od0 = g2 / 'out_system_node'
    c, o, e = run(PY + [EXPORT / 'writer_portable.py', '--carrier', partial, '--out', od0, '--writer-dir', wd])
    record('f_g2_control_system_node_refuses_partial', c == 1 and refusal(e).get('code') == 'REVIEW_STATUS_REQUIRED' and not od0.exists(), e[-300:])
    outs_w = {}
    for tag, extra, env in (('flag', ['--node', wnode], None), ('path', [], env_path)):
        od = g2 / f'out_{tag}'
        before = wrapper_runs()
        c, o, e = run(PY + [EXPORT / 'writer_portable.py', '--carrier', partial, '--out', od, '--writer-dir', wd] + extra, env=env)
        ne = json.loads((od / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))['node_environment']['node'] if c == 0 else {}
        outs_w[tag] = od
        record(f'f_g2_wrapper_{tag}_writer_accepts_partial_identity_recorded', c == 0 and wrapper_runs() > before
               and ne.get('executable') == str(wnode) and ne.get('realpath') == wreal and ne.get('sha256') == wsha and wsha != node_sha
               and ne.get('version') == node_version, {'stderr': e[-300:], 'node': ne})
    for tag in ('flag', 'path'):
        rp = g2 / f'qa_unpinned_{tag}.json'
        extra, env = (['--node', wnode], None) if tag == 'flag' else ([], env_path)
        c, o, e = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', outs_w[tag], '--report', rp, '--carrier', partial, '--writer-dir', wd] + extra, env=env)
        q = qa_report(rp)
        pv, pre = q.get('expected_provenance', {}), q.get('cps_evidence_preconditions', {})
        cn = pv.get('checker_node') or {}
        record(f'h_g2_wrapper_{tag}_unpinned_saved_qa_passes_and_shows_the_wrapper', c == 0 and q.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS'
               and pv.get('result') == 'PASS' and cn.get('pinned') is False and cn.get('realpath') == wreal and cn.get('sha256') == wsha
               and (pv.get('writer004_check_node') or {}).get('sha256') == wsha and (pv.get('rerun_node') or {}).get('sha256') == wsha
               and (pv.get('receipt_node') or {}).get('sha256') == wsha and pre.get('pinned_checker_node') is False
               and pre.get('all_checked_here_met') is False and (pre.get('checker_node') or {}).get('sha256') == wsha,
               {'stderr': e[-300:], 'provenance': {k: pv.get(k) for k in ('result', 'checker_node', 'rerun_node', 'writer004_check_node')}})
    for tag in ('flag', 'path'):            # pinned checker node, with the wrapper first on PATH
        rp = g2 / f'qa_pinned_{tag}.json'
        before = wrapper_runs()
        c, o, e = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', outs_w[tag], '--report', rp, '--carrier', partial, '--writer-dir', wd] + checker, env=env_path)
        q = qa_report(rp)
        pv, pre = q.get('expected_provenance', {}), q.get('cps_evidence_preconditions', {})
        fp = q.get('findings', {}).get('provenance', {}).get('first', [])
        record(f'h_g2_wrapper_{tag}_output_fails_with_pinned_checker_node', c == 1 and q.get('status') == 'SAVED_QA_FAILED'
               and pv.get('result') == 'WRITER004_REFUSED' and any(f.get('code') == 'REVIEW_STATUS_REQUIRED' for f in fp)
               and any((f.get('refusal') or {}).get('code') == 'REVIEW_STATUS_REQUIRED' for f in fp) and wrapper_runs() == before
               and pre.get('pinned_checker_node') is True and (pv.get('checker_node') or {}).get('sha256') == node_sha
               and (pv.get('receipt_node') or {}).get('sha256') == wsha and pv.get('receipt_node_matches_checker_node') is False,
               {'stderr': e[-300:], 'result': pv.get('result'), 'wrapper_ran': wrapper_runs() - before, 'findings': fp[:3]})
    rp = g2 / 'qa_pinned_valid_path.json'
    before = wrapper_runs()
    c, o, e = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', outs / 'v01_base', '--report', rp, '--carrier', ef / 'valid' / 'v01_base.json',
                        '--writer-dir', wd] + checker, env=env_path)
    q = qa_report(rp)
    record('h_g2_pinned_checker_node_ignores_path', c == 0 and q.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' and pinned_node_ok(q, writer004_check=True)
           and wrapper_runs() == before, {'stderr': e[-300:], 'wrapper_ran': wrapper_runs() - before})
    rp = g2 / 'qa_checker_node_sha256_mismatch.json'
    before = wrapper_runs()
    c, o, e = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', outs / 'v01_base', '--report', rp, '--carrier', ef / 'valid' / 'v01_base.json',
                        '--writer-dir', wd, '--checker-node', wnode, '--checker-node-sha256', node_sha])
    q = qa_report(rp)
    pv = q.get('expected_provenance', {})
    record('h_g2_checker_node_sha256_mismatch_refused_before_any_node_call', c == 1 and q.get('status') == 'SAVED_QA_FAILED'
           and pv.get('result') == 'CHECKER_NODE_REFUSED' and wrapper_runs() == before and 'rerun_writer' not in pv
           and (pv.get('checker_node') or {}).get('sha256') == wsha and (pv.get('checker_node') or {}).get('sha256_verified') is False
           and q.get('cps_evidence_preconditions', {}).get('pinned_checker_node') is False, pv)
    usage = {'relative_path': ['--carrier', ef / 'valid' / 'v01_base.json', '--writer-dir', wd, '--checker-node', 'node', '--checker-node-sha256', node_sha],
             'path_without_sha256': ['--carrier', ef / 'valid' / 'v01_base.json', '--writer-dir', wd, '--checker-node', node_real],
             'sha256_without_path': ['--carrier', ef / 'valid' / 'v01_base.json', '--writer-dir', wd, '--checker-node-sha256', node_sha],
             'malformed_sha256': ['--carrier', ef / 'valid' / 'v01_base.json', '--writer-dir', wd, '--checker-node', node_real, '--checker-node-sha256', 'xyz'],
             'with_node': ['--carrier', ef / 'valid' / 'v01_base.json', '--writer-dir', wd, '--node', node_real] + checker,
             'without_carrier': checker}
    res = {}
    for tag, extra in usage.items():
        rp = g2 / f'usage_{tag}.json'
        c, o, e = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', outs / 'v01_base', '--report', rp] + extra)
        res[tag] = [c, rp.exists()]
    record('h_g2_checker_node_usage_errors', len(res) == 6 and all(v == [2, False] for v in res.values()), res)

    # ------------------------------------------------ (k) writer v2.6: owner decisions O33 (deliverable naming) and O34 (G/H)
    # The name derivation in the writer (deliverable_record) and saved QA's own (derive_deliverable) give the same record or the
    # same refusal reason on every case and on random titles; titled outputs differ from untitled ones only in the file name and
    # in xl/workbook.xml, which equals the pinned template with the escaped derived name; G and H have the body style everywhere.
    def derive_both(title):
        try:
            w = ['ok', wp.deliverable_record(title)]
        except wp.Refused as e:
            w = ['refused', e.code, e.stage, (e.detail or {}).get('reason')]
        try:
            q = ['ok', sq.derive_deliverable(title)]
        except sq.DeliverableNameError as e:
            q = ['refused', 'JOB_TITLE_INVALID', 'usage', e.reason]
        return w, q
    T1, T2 = '9990102甲公司-乙案丁戊', '9990103乙公司-甲案'
    T_LONG = '9990803甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥(1K+200~3K+450)'
    T_SPECIAL = '9990102甲公司-乙&<>"\'|案，丙'
    name_cases = {     # name: (title, xlsx file, main sheet, dash_removed_at, main_sheet_cut)
        'dash_removed': (T1, '9990102甲公司乙案丁戊(未填).xlsx', '9990102甲公司乙案丁戊(未填)', 10, False),
        'no_dash': ('9990204丙公司丁案', '9990204丙公司丁案(未填).xlsx', '9990204丙公司丁案(未填)', None, False),
        'dash_6th_character_after_case_id_removed': ('9990102甲乙丙丁戊-己案', '9990102甲乙丙丁戊己案(未填).xlsx', '9990102甲乙丙丁戊己案(未填)', 12, False),
        'dash_7th_character_after_case_id_kept': ('9990102甲乙丙丁戊己-庚案', '9990102甲乙丙丁戊己-庚案(未填).xlsx', '9990102甲乙丙丁戊己-庚案(未填)', None, False),
        'only_first_dash_removed': ('9990102甲公司-乙案-丙', '9990102甲公司乙案-丙(未填).xlsx', '9990102甲公司乙案-丙(未填)', 10, False),
        'dash_directly_after_case_id_removed': ('9990102-甲公司-乙案', '9990102甲公司-乙案(未填).xlsx', '9990102甲公司-乙案(未填)', 7, False),
        'long_cut_to_31_keeps_suffix': (T_LONG, T_LONG + '(未填).xlsx', '9990803甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉(未填)', None, True),
        'forbidden_characters': ('9990102甲-乙/丙:丁*?"<>|[]\\戊', '9990102甲乙-丙-丁------[]-戊(未填).xlsx', '9990102甲乙-丙-丁--"<>|---戊(未填)', 8, False),
        'forbidden_characters_and_cut': ('9990102甲公司-乙/丙:丁*戊?己"庚<辛>壬|癸[子]丑', '9990102甲公司乙-丙-丁-戊-己-庚-辛-壬-癸[子]丑(未填).xlsx',
                                         '9990102甲公司乙-丙-丁-戊-己"庚<辛>壬|癸(未填)', 10, True),
        'nfkc_and_whitespace': ('　９９９０１０２ 甲公司－ＡＢ案（一）\t丁戊 ，丙﻿\n', '9990102甲公司AB案(一)丁戊,丙(未填).xlsx',
                                '9990102甲公司AB案(一)丁戊,丙(未填)', 10, False),
        'special_characters': (T_SPECIAL, "9990102甲公司乙&---'-案,丙(未填).xlsx", '9990102甲公司乙&<>"\'|案,丙(未填)', 10, False),
        'astral_cut_whole_code_points': ('9990102' + '\U00020000' * 15, '9990102' + '\U00020000' * 15 + '(未填).xlsx',
                                         '9990102' + '\U00020000' * 10 + '(未填)', None, True),
        'file_name_254_bytes_accepted': ('9990102' + '甲' * 78, '9990102' + '甲' * 78 + '(未填).xlsx', '9990102' + '甲' * 20 + '(未填)', None, True),
    }
    for label, (title, want_file, want_sheet, want_k, want_cut) in name_cases.items():
        w, q = derive_both(title)
        d_ = w[1] if w[0] == 'ok' else {}
        record(f'k_derive_{label}', w[0] == q[0] == 'ok' and w[1] == q[1] and d_['xlsx_file'] == want_file and d_['main_sheet'] == want_sheet
               and d_['dash_removed_at'] == want_k and d_['main_sheet_cut'] is want_cut and wp.js_len(d_['main_sheet']) <= 31
               and d_['main_sheet'].endswith('(未填)') and d_['name'].endswith('(未填)') and d_['o33_naming_applied'] is True
               and d_['sheet_mapping'][0] == {'expected_saved_values_sheet': '未填研究草稿', 'workbook_sheet': want_sheet}
               and [m_['workbook_sheet'] for m_ in d_['sheet_mapping'][1:]] == wp.SHEET_ORDER[1:]
               and len(want_file.encode('utf-8')) <= 255, {'writer': w, 'saved_qa': q})
    refusal_cases = {'empty': ('', 'CASE_ID_REQUIRED'), 'whitespace_only': (' 　\t\n', 'CASE_ID_REQUIRED'),
                     'no_case_id': ('甲公司-乙案', 'CASE_ID_REQUIRED'), 'six_digit_case_id': ('114100甲公司', 'CASE_ID_REQUIRED'),
                     'arabic_indic_digits': ('١١٤١٠٠٢甲', 'CASE_ID_REQUIRED'),
                     'c0_control': ('9990102甲\x01乙', 'UNREPRESENTABLE_CHARACTER'), 'c1_control': ('9990102甲\x80乙', 'UNREPRESENTABLE_CHARACTER'),
                     'delete': ('9990102甲\x7f', 'UNREPRESENTABLE_CHARACTER'), 'lone_surrogate': ('9990102甲\ud800', 'UNREPRESENTABLE_CHARACTER'),
                     'noncharacter_fffe': ('9990102甲￾', 'UNREPRESENTABLE_CHARACTER'),
                     'ooxml_escape_in_sheet_name': ('9990102_x0041_甲', 'LITERAL_OOXML_ESCAPE_SEQUENCE'),
                     'file_name_257_bytes': ('9990102' + '甲' * 79, 'FILE_NAME_TOO_LONG'), 'not_a_string': (9990102, 'NOT_A_STRING')}
    for label, (title, reason) in refusal_cases.items():
        w, q = derive_both(title)
        record(f'k_derive_refuses_{label}', w == q == ['refused', 'JOB_TITLE_INVALID', 'usage', reason], {'writer': w, 'saved_qa': q})
    w, q = derive_both(None)
    record('k_derive_untitled_is_v25_names', w[0] == q[0] == 'ok' and w[1] == q[1] and w[1]['xlsx_file'] == 'research-draft.xlsx'
           and w[1]['main_sheet'] == '未填研究草稿' and w[1]['o33_naming_applied'] is False and w[1]['job_title'] is None
           and [m_['workbook_sheet'] for m_ in w[1]['sheet_mapping']] == wp.SHEET_ORDER and w[1]['profile'] == sq.PROFILE == 'owner_O33_O34_O38'
           and w[1]['qa_workbook_file'] == 'research-draft.xlsx' and w[1]['deliverable_workbook'] is False and w[1]['deliverable_format'] is None, [w, q])
    rnd_t = random.Random(3306)
    pool_t = list('0123456789０１２３') + ['-', '－', '‐', '甲', '乙', '公司', '案', 'A', 'z', '(', ')', '（', '，', ',', '~', '+', '_x0041_', '_x00'] \
        + list('\\/:*?"<>|[]&\'') + [' ', '\t', '\n', '　', ' ', '﻿', '​', '\x85', '\x1c', '\x01', '\U00020000', '\ud800', 'é', 'é']
    disagree, n_ok, n_ref = [], 0, 0
    for _ in range(4000):
        head = (''.join(rnd_t.choice('0123456789０１') for _ in range(7)) if rnd_t.random() < 0.85 else '')
        title = head + ''.join(rnd_t.choice(pool_t) for _ in range(rnd_t.randint(0, rnd_t.choice((8, 40, 120)))))
        w, q = derive_both(title)
        if w != q:
            disagree.append([title, w, q])
        n_ok += w[0] == 'ok'
        n_ref += w[0] == 'refused'
    record('k_derive_writer_and_saved_qa_agree_on_4000_random_titles', not disagree and n_ok > 1000 and n_ref > 200,
           {'disagree': disagree[:3], 'ok': n_ok, 'refused': n_ref})
    ws_diff = [c for c in range(0x110000) if wp.title_whitespace(chr(c)) != bool(sq.TITLE_WS_RE.fullmatch(chr(c)))]
    bad_diff = [c for c in range(0x110000) if (unicodedata.category(chr(c)) in ('Cc', 'Cs') or bool(wp.XML_ILLEGAL_RE.match(chr(c))))
                != bool(sq.TITLE_BAD_RE.fullmatch(chr(c)))]
    record('k_title_whitespace_and_refused_character_sets_equal_over_all_code_points', not ws_diff and not bad_diff,
           {'whitespace': ws_diff[:10], 'refused': bad_diff[:10]})
    record('k_template_pins', sha(sq.WORKBOOK_TEMPLATE.encode('utf-8')) == sq.PINNED_TEMPLATES['xl/workbook.xml']['template_sha256']
           == '3b831f50f102d38062f2c4abe30ef190f8a755daa20f48fe36363afd7b31f13a' and sq.WORKBOOK_TEMPLATE.count(sq.MAIN_SHEET_TOKEN) == 1
           and sha(sq.template_part('xl/workbook.xml', '未填研究草稿')) == 'cb9bc2217b38cc95ee8c68f2e4c40a2282a048b7cfe9f69b27bba3615bd2f3ce'
           and sq.PINNED_PARTS['xl/styles.xml'] == '1a5ff017aafeada8347ec417982f3decacce97bdab69cf504d588a61e863ea9c'
           and sq.PINNED_PARTS['docProps/app.xml'] == '209fca6b00afe72a5029754b94be5953d8f16d96f67130325566b9366ad4ccc5'
           and sq.xml_attribute_escape('a&b<c>d"e\'f') == 'a&amp;b&lt;c&gt;d&quot;e\'f')
    # titled writer outputs and their untitled counterparts
    tdir = work / 'titled'
    tdir.mkdir()
    titled_specs = {'v01_t1': (ef / 'valid' / 'v01_base.json', T1, 'v1', outs / 'v01_base'),
                    'v01_long': (ef / 'valid' / 'v01_base.json', T_LONG, 'v1', outs / 'v01_base'),
                    'fid_special': (fid, T_SPECIAL, 'v1', fid_out),
                    'fid_special_v2': (fid, T_SPECIAL, 'v2', fid_v2),
                    'v2_w09_t1': (ef2 / 'valid' / 'w09_relaxed_all.json', T1, 'v2', outs / 'v2_w09_relaxed_all')}
    titled = {}
    for tag, (car, title, mode_, plain) in titled_specs.items():
        od = tdir / tag
        c, o, e = run(PY + [EXPORT / 'writer_portable.py', '--carrier', car, '--out', od, '--writer-dir', wd, '--mode', mode_, '--job-title=' + title])
        dv = sq.derive_deliverable(title)
        rc = json.loads((od / 'WRITER_RECEIPT.json').read_text(encoding='utf-8')) if c == 0 else {}
        rp_ = json.loads((plain / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
        ok = c == 0 and sorted(x.name for x in od.iterdir()) == sorted([dv['xlsx_file'], dv['qa_workbook_file'], 'EXPECTED_SAVED_VALUES.json',
                                                                         'WRITER_RECEIPT.json']) and dv['qa_workbook_file'] == 'INTERNAL_QA_WORKBOOK.xlsx'
        if ok:
            titled[tag] = od
            with zipfile.ZipFile(od / dv['qa_workbook_file']) as zt, zipfile.ZipFile(plain / 'research-draft.xlsx') as zp:
                parts_t, parts_p = zt.namelist(), zp.namelist()
                differ_parts = [n_ for n_ in parts_p if zt.read(n_) != zp.read(n_)]
                wbx = zt.read('xl/workbook.xml')
                app_ok = zt.read('docProps/app.xml') == zp.read('docProps/app.xml') and dv['main_sheet'].encode('utf-8') not in zt.read('docProps/app.xml')
            names_t = openpyxl.load_workbook(od / dv['qa_workbook_file'], read_only=True).sheetnames
            ok = (parts_t == parts_p and differ_parts == ['xl/workbook.xml'] and wbx == sq.template_part('xl/workbook.xml', dv['main_sheet']) and app_ok
                  and names_t == [dv['main_sheet']] + wp.SHEET_ORDER[1:]
                  and (od / 'EXPECTED_SAVED_VALUES.json').read_bytes() == (plain / 'EXPECTED_SAVED_VALUES.json').read_bytes()
                  and rc['deliverable'] == dict(wp.deliverable_record(title), rules={'o33': wp.O33_RULE, 'o34': wp.O34_RULE, 'o38': wp.O38_RULE, 'o39': wp.O39_RULE})
                  and {k: rc['deliverable'][k] for k in sq.DELIVERABLE_FIELDS} == dv and rc['output_xlsx']['file'] == dv['qa_workbook_file']
                  and rc['deliverable_xlsx']['file'] == dv['xlsx_file'] and rc['deliverable_xlsx']['sheet'] == dv['main_sheet']
                  and rc['deliverable_xlsx']['format'] == sq.DELIVERY_FORMAT == wp.DELIVERY_FORMAT
                  and rc['deliverable_xlsx']['sha256'] == sha((od / dv['xlsx_file']).read_bytes()) and rp_.get('deliverable_xlsx') is None
                  and rc['deliverable']['job_title'] == title and rc['writer'] == 'cps-export-writer-portable.v2.8.2'
                  and wp.DELIVERABLE_LIMITATION in rc['limitations'] and wp.DELIVERABLE_LIMITATION not in rp_['limitations']
                  and all(rc[k] == rp_[k] for k in ('matrices_sha256', 'sheets', 'cross_check', 'expected_saved_values', 'relaxations', 'mode'))
                  and wp.NAMING_LIMITATION in rc['limitations'] and wp.NAMING_LIMITATION not in rp_['limitations'])
        record(f'k_titled_write_{tag}', ok, {'stderr': e[-300:], 'files': sorted(x.name for x in od.iterdir()) if od.is_dir() else None})
    for tag, od in titled.items():
        car, title = titled_specs[tag][0], titled_specs[tag][1]
        dv = sq.derive_deliverable(title)
        c1, o1, e1 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', od, '--report', tdir / f'qa_{tag}.json'])
        c2, o2, e2 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', od, '--report', tdir / f'qa_prov_{tag}.json', '--carrier', car, '--writer-dir', wd] + checker)
        q1, q2 = qa_report(tdir / f'qa_{tag}.json'), qa_report(tdir / f'qa_prov_{tag}.json')
        pv = q2.get('expected_provenance', {})
        dl1 = q1.get('deliverable', {})
        record(f'k_titled_saved_qa_passes_{tag}', c1 == 0 and c2 == 0 and q1.get('status') == q2.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS'
               and q1.get('sheet_order') == [dv['main_sheet']] + wp.SHEET_ORDER[1:] and dl1.get('xlsx_file') == dv['xlsx_file']
               and dl1.get('main_sheet') == dv['main_sheet'] and dl1.get('receipt_fields_equal_derivation') is True and dl1.get('job_title') == title
               and q1.get('xlsx', {}).get('file') == dv['qa_workbook_file'] and q1['totals']['formatting_failures'] == 0
               and q1.get('deliverable_xlsx', {}).get('checked') is True and q1['deliverable_xlsx'].get('file') == dv['xlsx_file']
               and q1['totals']['deliverable_workbook_findings'] == 0 and (q1['totals']['deliverable_formatting_cells_checked'] or 0) >= 17 * 2
               and pv.get('deliverable_xlsx_byte_identical') is True and pv.get('rerun_deliverable_file') == dv['xlsx_file']
               and 'deliverable_xlsx' in pv['receipt_claims'].get('compared_fields', [])
               and q2['cps_evidence_preconditions'].get('deliverable_checked') is True
               and q2['cps_evidence_preconditions'].get('all_checked_here_met') is True
               and q1['structure']['pinned_templates']['xl/workbook.xml']['main_sheet'] == dv['main_sheet']
               and pv.get('result') == 'PASS' and pv.get('rerun_job_title') == title and pv.get('rerun_xlsx_file') == dv['qa_workbook_file']
               and pv.get('xlsx_byte_identical') is True and pv.get('receipt_claims', {}).get('match') is True
               and 'deliverable' in pv['receipt_claims'].get('compared_fields', []) and pinned_node_ok(q2, writer004_check=titled_specs[tag][2] == 'v1')
               and q2['cps_evidence_preconditions'].get('job_title') == title,
               {'no_prov': [q1.get('status'), q1.get('findings')], 'prov': [q2.get('status'), q2.get('findings'), pv.get('result')]})
    record('k_titled_v2_without_relaxations_equals_v1_bytes', 'fid_special' in titled and 'fid_special_v2' in titled
           and all((titled['fid_special'] / sq.derive_deliverable(T_SPECIAL)[k]).read_bytes()
                   == (titled['fid_special_v2'] / sq.derive_deliverable(T_SPECIAL)[k]).read_bytes() for k in ('xlsx_file', 'qa_workbook_file')))
    for label, title, reason in (('no_case_id', '甲公司-乙案', 'CASE_ID_REQUIRED'), ('file_name_too_long', '9990102' + '甲' * 79, 'FILE_NAME_TOO_LONG'),
                                 ('control_character', '9990102甲\x01乙', 'UNREPRESENTABLE_CHARACTER'), ('empty', '', 'CASE_ID_REQUIRED')):
        od = tdir / f'refused_{label}'
        c, o, e = run(PY + [EXPORT / 'writer_portable.py', '--carrier', ef / 'valid' / 'v01_base.json', '--out', od, '--writer-dir', wd, '--job-title=' + title])
        ref = refusal(e)
        record(f'k_writer_refuses_title_{label}', c == 1 and not od.exists() and ref.get('code') == 'JOB_TITLE_INVALID' and ref.get('stage') == 'usage'
               and (ref.get('detail') or {}).get('reason') == reason, ref)
    # untitled outputs keep the v2.5 names; every output (untitled and titled) has the body style on G and H
    v25_named, gh_bad, gh_rows, n_gh = [], [], 0, 0
    all_out = sorted({d for d in outs.iterdir() if (d / 'WRITER_RECEIPT.json').is_file()} | {fid_out, fid_v2} | set(titled.values()))
    for d in all_out:
        rc = json.loads((d / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
        dv = sq.derive_deliverable(rc['deliverable']['job_title'])
        if rc['deliverable']['job_title'] is None:
            with zipfile.ZipFile(d / 'research-draft.xlsx') as z:
                if not (rc['deliverable'] == dict(wp.deliverable_record(None), rules={'o33': wp.O33_RULE, 'o34': wp.O34_RULE, 'o38': wp.O38_RULE, 'o39': wp.O39_RULE})
                        and rc['output_xlsx']['file'] == 'research-draft.xlsx' and rc.get('deliverable_xlsx', 'missing') is None
                        and sorted(q_.name for q_ in d.iterdir() if q_.name.endswith('.xlsx')) == ['research-draft.xlsx']
                        and sha(z.read('xl/workbook.xml')) == 'cb9bc2217b38cc95ee8c68f2e4c40a2282a048b7cfe9f69b27bba3615bd2f3ce'):
                    v25_named.append(d.name)
        n_gh += 1
        with zipfile.ZipFile(d / dv['qa_workbook_file']) as z:
            st_ = z.read('xl/styles.xml').decode('utf-8')
            s1 = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        styles_of = dict(re.findall(r'<c r="([A-Z]+[0-9]+)" s="([0-9]+)"', s1))
        rows_ = sorted({int(r_[1:]) for r_ in styles_of if r_[0] == 'G' and r_[1:] != '1'})
        gh_rows += len(rows_)
        if 'F1F3F5' in st_ or '<fills count="3">' not in st_ or not rows_ or any(
                not (styles_of.get(f'G{r_}') == styles_of.get(f'H{r_}') == styles_of.get(f'I{r_}') == styles_of.get(f'A{r_}')) for r_ in rows_):
            gh_bad.append(d.name)
    record('k_untitled_outputs_keep_v25_names', not v25_named and len(all_out) >= 30 and len(all_out) - len(titled) >= 25, v25_named[:5])
    record('k_gh_have_the_body_style_in_every_output', not gh_bad and n_gh >= 30 and gh_rows > 400, {'bad': gh_bad[:5], 'outputs': n_gh, 'rows': gh_rows})
    wb_gh = openpyxl.load_workbook(titled['v01_t1'] / sq.derive_deliverable(T1)['qa_workbook_file']) if 'v01_t1' in titled else None
    ws_gh = wb_gh[sq.derive_deliverable(T1)['main_sheet']] if wb_gh else None
    record('k_gh_no_fill_openpyxl', ws_gh is not None and all(ws_gh.cell(row=r_, column=c_).fill.fill_type is None for r_ in range(2, ws_gh.max_row + 1)
                                                              for c_ in (7, 8)) and ws_gh.max_row >= 3
           and all(ws_gh.cell(row=r_, column=c_)._style == ws_gh.cell(row=r_, column=9)._style == ws_gh.cell(row=r_, column=1)._style
                   for r_ in range(2, ws_gh.max_row + 1) for c_ in (7, 8)))
    # naming tampers (O33) from the titled fidelity output
    ntd = work / 'tampers_naming'
    code, out, err = run(PY + [HERE / 'make_tamper_fixtures.py', 'naming', titled.get('fid_special', work / 'missing'), ntd, T2])
    ntamp = json.loads((ntd / 'TAMPERS.json').read_text(encoding='utf-8'))['tampers'] if code == 0 else []
    record('k_naming_tamper_counts', code == 0 and [t['name'][:3] for t in ntamp] == [f'K{k:02d}' for k in range(1, 14)], err[-300:])
    for t in ntamp:
        d = Path(t['dir'])
        c1, o1, e1 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d])
        q1 = qa_report(d / 'SAVED_QA.json')
        f1 = set(q1.get('findings', {}))
        c2, o2, e2 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d, '--report', d / 'SAVED_QA_PROVENANCE.json', '--carrier', fid, '--writer-dir', wd] + checker)
        q2 = qa_report(d / 'SAVED_QA_PROVENANCE.json')
        f2, pv = set(q2.get('findings', {})), q2.get('expected_provenance', {})
        if t['findings']:
            no_prov = c1 == 1 and q1.get('status') == 'SAVED_QA_FAILED' and set(t['findings']) <= f1 and (not t['only'] or f1 == set(t['findings']))
        else:
            no_prov = c1 == 0 and q1.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' and not f1
        if t['provenance'] == 'passes':
            prov = c2 == 0 and q2.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' and pv.get('result') == 'PASS' and pv.get('rerun_job_title') == T2
        else:
            prov = (c2 == 1 and q2.get('status') == 'SAVED_QA_FAILED' and pv.get('result') == t['provenance_result'] and set(t['findings']) <= f2
                    and (t['provenance'] != 'provenance' or 'provenance' in f2)
                    and q2.get('cps_evidence_preconditions', {}).get('all_checked_here_met') is False)
        record(f"k_naming_tamper_{t['name']}", no_prov and prov and 'Traceback' not in e1 + e2,
               {'no_prov': [q1.get('status'), sorted(f1)], 'prov': [q2.get('status'), sorted(f2), pv.get('result')], 'stderr': (e1 + e2)[-300:]})

    # ------------------------------------------------ (l) writer v2.7: owner decision O38 (the one-sheet deliverable)
    vq_l = load(EXPORT / 'visual_qa.py', 'visual_qa_under_test_l')
    record('l_writer_and_saved_qa_format_constants_equal',
           wp.QA_WORKBOOK_NAME == sq.QA_WORKBOOK_NAME == 'INTERNAL_QA_WORKBOOK.xlsx' and wp.DELIVERY_FORMAT == sq.DELIVERY_FORMAT
           and wp.DELIVERY_WIDTHS == sq.DELIVERY['min_widths'] and len(wp.DELIVERY_WIDTHS) == 17 and wp.DELIVERY_FONT == sq.DELIVERY['font'] == '新細明體'
           and wp.DELIVERY_FONT_SIZE == sq.DELIVERY['size'] == 12 and 'FF' + wp.DELIVERY_HEADER_FILL == sq.DELIVERY['header_fill'] == 'FFC0C0C0'
           and 'FF' + wp.DELIVERY_BORDER_COLOR == sq.DELIVERY['border_color'] and wp.DELIVERY_CENTRED == sq.DELIVERY['centred'] == 'EFLMNQ'
           and wp.DELIVERY_LEFT == sq.DELIVERY['left'] == 'C' and wp.DELIVERY_HEADER_HEIGHT == sq.DELIVERY['header_height'] == 23.25
           and wp.DELIVERY_ROW_HEIGHT == sq.DELIVERY['row_height'] == 20.45 and str(wp.DELIVERY_HEADER_HEIGHT) == sq.DELIVERY_ROW_HT['header']
           and str(wp.DELIVERY_ROW_HEIGHT) == sq.DELIVERY_ROW_HT['body']
           and sha(sq.DELIVERABLE_WORKBOOK_TEMPLATE.encode('utf-8')) == sq.DELIVERABLE_PINNED_TEMPLATES['xl/workbook.xml']['template_sha256']
           and sq.DELIVERABLE_WORKBOOK_TEMPLATE.count(sq.MAIN_SHEET_TOKEN) == 1 and sq.WORKBOOK_TEMPLATE.count('<sheet ') == 4
           and sq.DELIVERABLE_WORKBOOK_TEMPLATE.count('<sheet ') == 1
           and all(x in wp.O38_RULE for x in ('16.1 23.1 21.3 81.9 6.9 8.3 12.9 13 12.3 13 21.4 11 24.1 34.1 10.3 13 8.1', '#C0C0C0', '新細明體 12',
                                              'E F L M N Q centred', '23.25', '20.45', 'A2', 'INTERNAL_QA_WORKBOOK.xlsx')))
    # v2.8 (O39): the width rule is the same in the writer, saved QA and visual QA
    record('l_o39_fit_constants_equal',
           (wp.FIT_TENTHS_NON_ASCII, wp.FIT_TENTHS_BROAD, wp.FIT_TENTHS_CAPITAL, wp.FIT_TENTHS_OTHER, wp.FIT_TENTHS_PAD, wp.FIT_BROAD)
           == (sq.FIT_TENTHS_NON_ASCII, sq.FIT_TENTHS_BROAD, sq.FIT_TENTHS_CAPITAL, sq.FIT_TENTHS_OTHER, sq.FIT_TENTHS_PAD, sq.FIT_BROAD)
           == (vq_l.FIT_TENTHS_NON_ASCII, vq_l.FIT_TENTHS_BROAD, vq_l.FIT_TENTHS_CAPITAL, vq_l.FIT_TENTHS_OTHER, vq_l.FIT_TENTHS_PAD, vq_l.FIT_BROAD)
           == (24, 22, 18, 15, 10, 'MWmw@%') and wp.DELIVERY_MAX_WIDTH_TENTHS == sq.DELIVERY_MAX_WIDTH_TENTHS == 2550
           and wp.FIT_TENTHS_NON_ASCII_OTHER == sq.FIT_TENTHS_NON_ASCII_OTHER == vq_l.FIT_TENTHS_NON_ASCII_OTHER == 27
           and (wp.DELIVERY_DEFAULT_FONT, wp.DELIVERY_DEFAULT_FONT_SIZE) == ('新細明體', 11)
           and all(x in wp.O39_RULE for x in ('24 per East Asian wide or full-width', '27 per other non-ASCII', '22 per M W m w @ %', '18 per other ASCII capital', '15 per other ASCII',
                                              'plus 10', '255', '新細明體 11')))
    o39_samples = ['', '中' * 10, 'W', 'A', 'a', '0', ' ', '\n', 'a\r\nb', 'NFB-3P 50A', '式' + ' ' * 8, 'Φ50', '１２', '\t', '𠀋', 'é', '～',
                   'm@%w', 'x' * 3000, 0, 1, -2.5, 12.5, 1e21, 1e-7, 123456789.25, 0.30000000000000004, None, True]
    fit_w = [wp.fit_tenths(v) for v in o39_samples]
    fit_s = [sq.fit_tenths(v) for v in o39_samples]
    fit_v = [vq_l.fit_tenths_text(v if isinstance(v, str) else wp.js_number(v)) for v in o39_samples if isinstance(v, (str, int, float)) and not isinstance(v, bool) and v is not None]
    fit_w2 = [wp.fit_tenths(v) for v in o39_samples if isinstance(v, (str, int, float)) and not isinstance(v, bool) and v is not None]
    record('l_o39_fit_rule_values', fit_w == fit_s and fit_v == fit_w2
           and fit_w[:9] == [0, 250, 32, 28, 25, 25, 25, 10, 40] and wp.fit_tenths(12.5) == 70 and wp.fit_tenths(1e21) == 10 + 15 * 5
           and wp.fit_tenths(None) == 0 and wp.fit_tenths(True) == 0 and sq.js_number(1e-7) == wp.js_number(1e-7) == '1e-7'
           and all(sq.js_number(v) == wp.js_number(v) for v in (0, 1, -2.5, 1e21, 1e-7, 123456789.25, 0.30000000000000004, 5e-324, 2 ** 53 + 1.0)),
           {'writer': fit_w, 'saved_qa': fit_s})
    # v2.8.2 (delta review F1): East Asian wide or full-width 24, other non-ASCII 27 (Ⅷ ① ‰ ℃ × é), the same in all three
    cls_samples = {'中': 34, '～': 34, '𠀋': 34, 'Ⅷ': 37, '①': 37, '‰': 37, '℃': 37, '×': 37, 'é': 37, 'ﾊ': 37, 'Ⅷ' * 9: 253}
    record('l_o39_fit_classes_v282', all(wp.fit_tenths(k) == sq.fit_tenths(k) == vq_l.fit_tenths_text(k) == v for k, v in cls_samples.items()),
           {k: [wp.fit_tenths(k), sq.fit_tenths(k), vq_l.fit_tenths_text(k), v] for k, v in cls_samples.items()})
    # visual_qa v4.4 (F3, F6): tile layout
    tb_ok = True
    for (tw_, th_) in ((1800, 1200), (1900, 1900), (1901, 1901), (3539, 2503), (9921, 7016), (4000, 100)):
        bx = vq_l.tile_boxes(tw_, th_)
        cover = all(any(x <= px < x + w and y <= py < y + h for (x, y, w, h) in bx)
                    for px in range(0, tw_, 97) for py in range(0, th_, 97))
        xs = sorted({x for (x, y, w, h) in bx}); ys = sorted({y for (x, y, w, h) in bx})
        ovx = all(xs[i] + 1900 - xs[i + 1] >= 120 for i in range(len(xs) - 1))
        ovy = all(ys[i] + 1900 - ys[i + 1] >= 120 for i in range(len(ys) - 1))
        tb_ok = tb_ok and cover and ovx and ovy and all(w <= 1900 and h <= 1900 and x >= 0 and y >= 0 and x + w <= tw_ and y + h <= th_
                                                          for (x, y, w, h) in bx)
    record('l_visual_tile_boxes_cover_overlap_and_bound', tb_ok and len(vq_l.tile_boxes(3539, 2503)) == 4 and len(vq_l.tile_boxes(1800, 1200)) == 1)
    hdr_row = list(wp.HEADERS)
    w_min = wp.delivery_widths([hdr_row])
    w_long = wp.delivery_widths([hdr_row, [None] * 13 + ['甲' * 30, None, None, None]])
    w_cap = wp.delivery_widths([hdr_row, ['乙' * 200] + [None] * 16])
    # v2.8.1: with 24 per CJK character the fixed headers 需要日期 (O) and 合約價 (Q) need 10.6 and 8.2, so every deliverable has them
    hdr_w = wp.DELIVERY_WIDTHS[:14] + [10.6, 13.0, 8.2]
    record('l_o39_widths_minimum_widen_and_cap', w_min == hdr_w and w_long[:13] == hdr_w[:13]
           and w_long[13] == 73.0 and w_long[14:] == hdr_w[14:] and w_cap[0] == 255.0 and w_cap[1:] == hdr_w[1:]
           and sq.deliverable_widths([hdr_row, [None] * 13 + ['甲' * 30, None, None, None]]) == w_long
           and all(abs(x * 10 - round(x * 10)) < 1e-9 for x in w_long), {'min': w_min, 'long': w_long, 'cap0': w_cap[0]})
    # two more titled outputs: long strings and 407 items
    for tag, car, title in (('v05_long', ef / 'valid' / 'v05_long_text.json', T1), ('v08_many', ef / 'valid' / 'v08_many_items.json', T2)):
        od = tdir / tag
        c, o, e = run(PY + [EXPORT / 'writer_portable.py', '--carrier', car, '--out', od, '--writer-dir', wd, '--job-title=' + title])
        c2, o2, e2 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', od, '--report', tdir / f'qa_prov_{tag}.json', '--carrier', car, '--writer-dir', wd] + checker)
        q2 = qa_report(tdir / f'qa_prov_{tag}.json')
        ok = (c == 0 and c2 == 0 and q2.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' and q2['expected_provenance'].get('deliverable_xlsx_byte_identical') is True
              and q2['cps_evidence_preconditions'].get('all_checked_here_met') is True and q2['totals']['deliverable_workbook_findings'] == 0)
        if c == 0:
            titled[tag] = od
            titled_specs[tag] = (car, title, 'v1', outs / car.stem)
        record(f'l_titled_saved_qa_passes_{tag}', ok, {'stderr': (e + e2)[-300:], 'findings': q2.get('findings')})
    # every titled output: the deliverable holds the main-sheet values and the O38 format (checked here independently of saved QA)
    from openpyxl.utils import get_column_letter as _gcl
    for tag, od in sorted(titled.items()):
        title = titled_specs[tag][1]
        dv = sq.derive_deliverable(title)
        main = json.loads((od / 'EXPECTED_SAVED_VALUES.json').read_text(encoding='utf-8'))['sheets'][0]['values']
        wbd = openpyxl.load_workbook(od / dv['xlsx_file'])
        wsd = wbd.worksheets[0]
        vals_bad, fmt_bad = [], []
        for r_ in range(1, len(main) + 1):
            for c_ in range(1, 18):
                cell = wsd.cell(row=r_, column=c_)
                want = main[r_ - 1][c_ - 1]
                got = cell.value
                if not (same_value(want, got) and (want is None) == (got is None) and isinstance(want, str) == isinstance(got, str)):
                    vals_bad.append([cell.coordinate, want, got])
                x = _gcl(c_)
                h_want = 'center' if r_ == 1 or x in 'EFLMNQ' else 'left' if x == 'C' else None
                if (cell.font.name, cell.font.sz, bool(cell.font.b), cell.alignment.horizontal, cell.alignment.vertical, bool(cell.alignment.wrap_text),
                        cell.fill.fill_type, cell.fill.fgColor.rgb if cell.fill.fill_type else None, cell.border.left.style, cell.border.bottom.style) != \
                        ('新細明體', 12, False, h_want, 'center', False, 'solid' if r_ == 1 else None, 'FFC0C0C0' if r_ == 1 else None,
                         'thin' if r_ == 1 else None, 'thin' if r_ == 1 else None):
                    fmt_bad.append(cell.coordinate)
        widths = [round(wsd.column_dimensions[_gcl(j)].width, 6) for j in range(1, 18)]
        heights = {wsd.row_dimensions[r_].height for r_ in range(2, len(main) + 1)}
        def _fit_indep(v):                       # review of v2.8, N9: the tests' own copy of the O39 counts
            if v is None or isinstance(v, bool):
                return 0
            t_ = v if isinstance(v, str) else wp.js_number(v)
            return 0 if t_ == '' else 10 + sum(0 if ch in '\r\n' else (24 if unicodedata.east_asian_width(ch) in 'WF' else 27)
                                               if ord(ch) > 0x7e else 22 if ch in 'MWmw@%' else 18 if 'A' <= ch <= 'Z' else 15 for ch in t_)
        need = [max([_fit_indep(row_[j]) for row_ in main if j < len(row_)] or [0]) for j in range(17)]
        o39_ok = all(abs(w_ - min(max(round(m_ * 10), n_), 2550) / 10) < 1e-9 for w_, m_, n_ in zip(widths, wp.DELIVERY_WIDTHS, need))
        with zipfile.ZipFile(od / dv['xlsx_file']) as z:
            st_xml = z.read('xl/styles.xml').decode('utf-8')
        font0 = re.search(r'<fonts[^>]*><font>(.*?)</font>', st_xml)
        record(f'l_deliverable_o39_widths_and_default_font_{tag}', o39_ok and widths == wp.delivery_widths(main) == sq.deliverable_widths(main)
               and all(w_ >= m_ for w_, m_ in zip(widths, wp.DELIVERY_WIDTHS)) and font0 is not None
               and font0.group(1) == '<name val="新細明體"/><sz val="11"/>' and 'Calibri' not in st_xml,
               {'widths': widths, 'need_tenths': need, 'font0': font0.group(1) if font0 else None})
        record(f'l_deliverable_values_and_format_{tag}', wbd.sheetnames == [dv['main_sheet']] and wsd.max_column == 17 and wsd.max_row == len(main)
               and not vals_bad and not fmt_bad and widths == wp.delivery_widths(main) and wsd.row_dimensions[1].height == 23.25 and heights == {20.45}
               and wsd.freeze_panes == 'A2' and wsd.sheet_view.showGridLines is not False and wsd.sheet_properties.tabColor is None
               and [wsd.cell(row=1, column=j).value for j in range(1, 18)] == wp.HEADERS,
               {'values': vals_bad[:5], 'format': fmt_bad[:5], 'widths': widths, 'sheets': wbd.sheetnames})
        with zipfile.ZipFile(od / dv['xlsx_file']) as z:
            sv = re.search(r'<sheetView[^>]*>.*?</sheetView>', z.read('xl/worksheets/sheet1.xml').decode('utf-8'))
        record(f'l_deliverable_view_gridlines_and_header_freeze_only_{tag}', sv is not None and 'showGridLines' not in sv.group(0)
               and '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>' in sv.group(0) and 'xSplit' not in sv.group(0),
               sv.group(0)[:300] if sv else None)
    # deliverable tampers (O38) from the titled fidelity output
    ldt = work / 'tampers_deliverable'
    code, out, err = run(PY + [HERE / 'make_tamper_fixtures.py', 'deliverable', titled.get('fid_special', work / 'missing'), ldt])
    ltamp = json.loads((ldt / 'TAMPERS.json').read_text(encoding='utf-8'))['tampers'] if code == 0 else []
    record('l_deliverable_tamper_counts', code == 0 and [t['name'][:3] for t in ltamp] == [f'L{k:02d}' for k in range(1, 20)], err[-300:])
    for t in ltamp:
        d = Path(t['dir'])
        c1, o1, e1 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d])
        q1 = qa_report(d / 'SAVED_QA.json')
        f1 = q1.get('findings', {})
        c2, o2, e2 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d, '--report', d / 'SAVED_QA_PROVENANCE.json', '--carrier', fid, '--writer-dir', wd] + checker)
        q2 = qa_report(d / 'SAVED_QA_PROVENANCE.json')
        f2, pv = q2.get('findings', {}), q2.get('expected_provenance', {})
        tagged_ok = all(any(isinstance(e_, dict) and e_.get('workbook') == 'deliverable' for e_ in f1.get(k, {}).get('first', []))
                        for k in t['deliverable_findings'])
        if t['passes_without_provenance']:
            no_prov = c1 == 0 and q1.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS' and not f1
        else:
            no_prov = (c1 == 1 and q1.get('status') == 'SAVED_QA_FAILED' and set(t['deliverable_findings']) | set(t['other_findings']) <= set(f1)
                       and tagged_ok)
        # L14, L19: the bytes are the writer's, so the rerun finds no byte difference; the edited deliverable_xlsx is a receipt claim
        prov = (c2 == 1 and q2.get('status') == 'SAVED_QA_FAILED'
                and (('receipt_claim_mismatch' in f2 and pv.get('deliverable_xlsx_byte_identical') is True
                      and 'deliverable_xlsx' in pv.get('receipt_claims', {}).get('mismatched_fields', []))
                     if t['name'][:3] in ('L14', 'L19') else 'provenance' in f2)
                and q2.get('cps_evidence_preconditions', {}).get('all_checked_here_met') is False
                and (t['name'][:3] in ('L07', 'L14', 'L19') or pv.get('deliverable_xlsx_byte_identical') is False or t['name'].startswith('L15')))
        record(f"l_deliverable_tamper_{t['name']}", no_prov and prov and 'Traceback' not in e1 + e2,
               {'no_prov': [q1.get('status'), sorted(f1)], 'prov': [q2.get('status'), sorted(f2), pv.get('result'),
                                                                    pv.get('deliverable_xlsx_byte_identical')], 'stderr': (e1 + e2)[-300:]})
    # review of v2.7, W1: column widths read as LibreOffice reads them (one <col> per column, first one wins), both workbooks;
    # N3: symbolic links refused
    if 'fid_special' in titled:
        src_t = titled['fid_special']
        dvs = sq.derive_deliverable(T_SPECIAL)
        wdir = work / 'tampers_cols'
        wdir.mkdir()

        def insert_first_col(x):
            k = x.index('<cols>') + len('<cols>')
            return x[:k] + '<col width="0.5" customWidth="1" min="1" max="17"/>' + x[k:]

        def drop_col(j):
            return mt.sub1(r'<col width="[0-9.]+" customWidth="1" min="%d" max="%d"/>' % (j, j), '')

        def no_width(j):
            return mt.sub1(r'<col width="[0-9.]+" customWidth="1" min="%d" max="%d"/>' % (j, j), '<col customWidth="1" min="%d" max="%d"/>' % (j, j))

        def dup_zero(j):
            return mt.sub1(r'(<col width="[0-9.]+" customWidth="1" min="%d" max="%d"/>)' % (j, j),
                           lambda m_: m_.group(1) + '<col width="0" customWidth="1" min="%d" max="%d"/>' % (j, j))
        col_tampers = {'W1a_deliverable_leading_wide_range_col': ('xlsx_file', mt.S1, insert_first_col),
                       'W1b_deliverable_col_H_dropped': ('xlsx_file', mt.S1, drop_col(8)),
                       'W1c_deliverable_col_J_width_removed': ('xlsx_file', mt.S1, no_width(10)),
                       'W1d_deliverable_col_J_duplicate_zero': ('xlsx_file', mt.S1, dup_zero(10)),
                       'W1e_deliverable_col_A_max_0': ('xlsx_file', mt.S1, mt.sub1(r'min="1" max="1"/>', 'min="1" max="0"/>')),
                       'W1f_internal_review_sheet_leading_wide_range_col': ('qa_workbook_file', 'xl/worksheets/sheet2.xml', insert_first_col),
                       'W1g_internal_main_sheet_col_P_dropped': ('qa_workbook_file', mt.S1, drop_col(16))}
        for name, (which, part, edit) in col_tampers.items():
            d = wdir / name
            shutil.copytree(src_t, d)
            fn = dvs[which]
            (d / fn).unlink()
            mt.write_tampered(src_t / fn, d / fn, {part: edit})
            mt.update_receipt(d)
            c1, o1, e1 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d])
            q1 = qa_report(d / 'SAVED_QA.json')
            ws_f = q1.get('findings', {}).get('worksheet_structure', {}).get('first', [])
            hit = any(isinstance(e_, dict) and str(e_.get('problem', '')).startswith('cols') for e_ in ws_f)
            tagged = any(isinstance(e_, dict) and e_.get('workbook') == 'deliverable' for e_ in ws_f)
            c2, o2, e2 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d, '--report', d / 'SAVED_QA_PROVENANCE.json', '--carrier', fid,
                                   '--writer-dir', wd] + checker)
            q2 = qa_report(d / 'SAVED_QA_PROVENANCE.json')
            record(f'l_cols_tamper_{name}', c1 == 1 and hit and tagged == (which == 'xlsx_file') and c2 == 1 and 'provenance' in q2.get('findings', {})
                   and 'Traceback' not in e1 + e2, {'no_prov': sorted(q1.get('findings', {})), 'prov': sorted(q2.get('findings', {}))})
        # N3: the deliverable replaced by a symbolic link to identical bytes outside the output directory
        d = wdir / 'N3_deliverable_symlink'
        shutil.copytree(src_t, d)
        outside = work / 'n3_outside_copy.xlsx'
        shutil.copyfile(src_t / dvs['xlsx_file'], outside)
        (d / dvs['xlsx_file']).unlink()
        os.symlink(outside, d / dvs['xlsx_file'])
        c1, o1, e1 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d])
        c2, o2, e2 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d, '--report', d / 'SAVED_QA_PROVENANCE.json', '--carrier', fid, '--writer-dir', wd] + checker)
        q1, q2 = qa_report(d / 'SAVED_QA.json'), qa_report(d / 'SAVED_QA_PROVENANCE.json')
        record('l_symlinked_deliverable_refused', c1 == 1 and c2 == 1 and 'integrity' in q1.get('findings', {}) and 'integrity' in q2.get('findings', {})
               and q2.get('cps_evidence_preconditions', {}).get('all_checked_here_met') is False, [sorted(q1.get('findings', {})), sorted(q2.get('findings', {}))])
        # visual_qa v4.4 (F5, F6): every branch of the automatic dpi rule, on copies of the writer's deliverable
        def _cols_copy(src_x, dst_x, width_of):
            with zipfile.ZipFile(src_x) as zi, zipfile.ZipFile(dst_x, 'w', zipfile.ZIP_DEFLATED) as zo:
                for info in zi.infolist():
                    data = zi.read(info.filename)
                    if info.filename == 'xl/worksheets/sheet1.xml':
                        data = re.sub(r'<col width="([^"]*)" customWidth="1" min="([0-9]+)" max="([0-9]+)"/>',
                                      lambda m_: '<col width="%s" customWidth="1" min="%s" max="%s"/>' % (width_of(int(m_.group(2)), m_.group(1)),
                                                                                                         m_.group(2), m_.group(3)),
                                      data.decode('utf-8')).encode('utf-8')
                    zo.writestr(info, data)
        dsrc = src_t / dvs['xlsx_file']
        x_inf, x_cap, x_wide = work / 'dpi_inf.xlsx', work / 'dpi_cap.xlsx', work / 'dpi_wide.xlsx'
        _cols_copy(dsrc, x_inf, lambda j, w: 'inf' if j == 1 else ('nan' if j == 2 else w))
        _cols_copy(dsrc, x_cap, lambda j, w: '255')
        _cols_copy(dsrc, x_wide, lambda j, w: '120' if j <= 4 else w)
        try:
            b_deliv, b_exact = vq_l.auto_dpi(dsrc, 'fit-width'), vq_l.auto_dpi(dsrc, 'exact')
            b_internal = vq_l.auto_dpi(src_t / dvs['qa_workbook_file'], 'fit-width')
            b_grid = vq_l.auto_dpi(ldt / 'L02_gridlines_hidden' / dvs['xlsx_file'], 'fit-width')
            b_inf, b_cap, b_wide = vq_l.auto_dpi(x_inf, 'fit-width'), vq_l.auto_dpi(x_cap, 'fit-width'), vq_l.auto_dpi(x_wide, 'fit-width')
            tot = vq_l.delivered_shape(dsrc, 'fit-width')[1]
            dpi_err = None
        except Exception as e_:                  # noqa: BLE001
            b_deliv = b_exact = b_internal = b_grid = b_inf = b_cap = b_wide = (None, None)
            tot, dpi_err = None, repr(e_)
        record('l_visual_auto_dpi_branches', dpi_err is None and b_deliv[0] == min(600, max(200, math.ceil(200 * tot / 330.8)))
               and b_deliv[1].startswith('auto: delivered') and b_exact == (150, 'auto: 150 (not fit-width)')
               and b_internal == (150, 'auto: 150 (not a one-sheet workbook)') and b_grid == (150, 'auto: 150 (gridlines off)')
               and b_cap[0] == 600 and b_wide[0] > b_deliv[0] and isinstance(b_inf[0], int) and 200 <= b_inf[0] <= 600,
               {'deliv': b_deliv, 'exact': b_exact, 'internal': b_internal, 'grid': b_grid, 'inf': b_inf, 'cap': b_cap, 'wide': b_wide,
                'error': dpi_err})
        # review of v2.8, N2: a main-sheet value of a type the writer never writes (an object) does not skip the deliverable checks
        d = wdir / 'N2_object_value_in_expected'
        shutil.copytree(src_t, d)
        ev = json.loads((d / 'EXPECTED_SAVED_VALUES.json').read_text(encoding='utf-8'))
        ev['sheets'][0]['values'][1][2] = {'x': 1}
        (d / 'EXPECTED_SAVED_VALUES.json').write_text(json.dumps(ev, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        mt.update_receipt(d)
        c1, o1, e1 = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', d])
        q1 = qa_report(d / 'SAVED_QA.json')
        dsec = q1.get('deliverable_xlsx') or {}
        record('l_o39_malformed_expected_value_keeps_deliverable_checks', c1 == 1 and q1.get('status') == 'SAVED_QA_FAILED'
               and dsec.get('checked') is True and isinstance(dsec.get('structure'), dict) and isinstance(dsec.get('expected_column_widths'), list)
               and 'Traceback' not in e1, {'findings': sorted(q1.get('findings', {})), 'section_keys': sorted(dsec)[:20]})
        # visual_qa v4.1: N1 numbers wider than the column are listed; N6 the first <col> covering a column gives its width.
        # v4.2 (O39): the writer's deliverable is widened, so nothing is listed; the W1a tamper (a leading 0.5-wide <col>) lists numbers.
        cut_f = vq_l.possibly_cut_cells(src_t / dvs['xlsx_file'])
        cut_w = vq_l.possibly_cut_cells(wdir / 'W1a_deliverable_leading_wide_range_col' / dvs['xlsx_file'])
        nums = {x['cell'] for x in cut_w['first'] if x['kind'] == 'number'}
        record('l_visual_numbers_wider_than_column_listed', {'F2', 'P7'} <= nums and cut_w['no_wrap_number_cells_checked'] > 10
               and all(x['kind'] in ('string', 'number') for x in cut_w['first']), sorted(nums)[:10])
        record('l_visual_o39_widened_deliverable_lists_only_line_feeds', cut_f['no_wrap_string_cells_checked'] > 10
               and cut_f['count'] >= 1 and cut_f['count'] == len(cut_f['first']) and all(x['kind'] == 'string' and x['line_feeds'] > 0 and x['estimated_width'] <= x['column_width']
                                                                 for x in cut_f['first']),
               {'count': cut_f['count'], 'first': cut_f['first'][:3]})
        record('l_visual_first_col_wins', cut_w['count'] > cut_f['count'] and all(x['column_width'] == 0.5 for x in cut_w['first']),
               {'tampered': cut_w['count'], 'writer': cut_f['count']})

    # visual-QA helpers on the deliverable (no LibreOffice): printed gridlines only where the view shows them; no-wrap cut cells
    if 'v05_long' in titled:
        dv5 = sq.derive_deliverable(T1)
        with zipfile.ZipFile(titled['v05_long'] / dv5['xlsx_file']) as z:
            s_d = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        with zipfile.ZipFile(titled['v05_long'] / dv5['qa_workbook_file']) as z:
            s_q = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        pd_, pq_ = vq_l.patch_sheet(s_d), vq_l.patch_sheet(s_q)
        record('l_visual_print_gridlines_only_where_shown', vq_l.shows_gridlines(s_d) and not vq_l.shows_gridlines(s_q)
               and pd_.count('<printOptions gridLines="1"/>') == 1 and '<printOptions' not in pq_
               and pd_.index('<printOptions') < pd_.index('<pageMargins') and vq_l.sheet_data(pd_) == vq_l.sheet_data(s_d))
        cut5 = vq_l.possibly_cut_cells(titled['v05_long'] / dv5['xlsx_file'])
        cutq = vq_l.possibly_cut_cells(titled['v05_long'] / dv5['qa_workbook_file'])
        clip5 = vq_l.possibly_clipped_cells(titled['v05_long'] / dv5['xlsx_file'])
        cut_cells = {(x['sheet'], x['cell']) for x in cut5['first']}
        record('l_visual_possibly_cut_cells_on_the_deliverable', cut5['count'] and {(dv5['main_sheet'], 'C3'), (dv5['main_sheet'], 'D2')} <= cut_cells
               and all('neighbours_filled' in x and x['estimated_width'] > 0 for x in cut5['first']) and cutq['count'] == 0
               and cutq['no_wrap_string_cells_checked'] == 0 and clip5['count'] == 0 and clip5['string_cells_checked'] == 0,
               {'cut': cut5['count'], 'first': cut5['first'][:3], 'internal': cutq['count'], 'clipped_on_deliverable': clip5['count']})
        base_cut = vq_l.possibly_cut_cells(titled['v01_t1'] / sq.derive_deliverable(T1)['xlsx_file']) if 'v01_t1' in titled else {'count': None}
        record('l_visual_line_feed_cells_listed', base_cut['count'] is not None and all(x['line_feeds'] >= 0 for x in base_cut['first']),
               base_cut.get('first', [])[:3])

    # ------------------------------------------------ third review G1: the pinned parts are byte-constant in every writer output
    # v5 (writer v2.6): 7 byte pins plus the xl/workbook.xml template with the derived main sheet name, titled outputs included
    pinned_dirs = sorted({d for d in outs.iterdir() if (d / 'WRITER_RECEIPT.json').is_file()}
                         | {work / n for n in ('repeat_v01', 'repeat_v2_w01_job_inputs', 'repeat_v2_w09_relaxed_all', 's1_env_valid_out', 's1_openssl_valid_out')}
                         | {fid_out, fid_v2} | set(outs_w.values()) | set(titled.values()))
    differ, n_pinned, n_titled_pinned, n_deliv_pinned = [], 0, 0, 0
    for d in pinned_dirs:
        if not (d / 'WRITER_RECEIPT.json').is_file():
            differ.append([d.name, 'missing'])
            continue
        rc = json.loads((d / 'WRITER_RECEIPT.json').read_text(encoding='utf-8'))
        dv = sq.derive_deliverable((rc.get('deliverable') or {}).get('job_title'))
        if rc['output_xlsx']['sha256'] != sha((d / dv['qa_workbook_file']).read_bytes()):
            differ.append([d.name, 'not the writer output'])
            continue
        n_pinned += 1
        n_titled_pinned += dv['o33_naming_applied']
        with zipfile.ZipFile(d / dv['qa_workbook_file']) as z:
            differ += [[d.name, part] for part, h in sq.PINNED_PARTS.items() if sha(z.read(part)) != h]
            differ += [[d.name, part] for part in sq.PINNED_TEMPLATES if z.read(part) != sq.template_part(part, dv['main_sheet'])]
        if dv['deliverable_workbook']:               # v6 (O38): the deliverable's own pins and template
            n_deliv_pinned += 1
            with zipfile.ZipFile(d / dv['xlsx_file']) as z:
                if sorted(z.namelist()) != sorted(sq.DELIVERABLE_PARTS):
                    differ.append([d.name, 'deliverable parts', sorted(z.namelist())])
                differ += [[d.name, 'deliverable ' + part] for part, h in sq.DELIVERABLE_PINNED_PARTS.items() if sha(z.read(part)) != h]
                differ += [[d.name, 'deliverable ' + part] for part in sq.DELIVERABLE_PINNED_TEMPLATES
                           if z.read(part) != sq.template_part(part, dv['main_sheet'], 'deliverable')]
    record('g_pinned_parts_constant_in_every_output', n_pinned >= 35 and n_titled_pinned >= 5 and n_deliv_pinned == n_titled_pinned and not differ
           and len(sq.PINNED_PARTS) == len(sq.DELIVERABLE_PINNED_PARTS) == 7 and set(sq.DELIVERABLE_PINNED_PARTS) == set(sq.PINNED_PARTS)
           and set(sq.DELIVERABLE_PINNED_PARTS) | set(sq.DELIVERABLE_PINNED_TEMPLATES) == set(sq.DELIVERABLE_PARTS) - {'xl/worksheets/sheet1.xml'}
           and set(sq.PINNED_TEMPLATES) == {'xl/workbook.xml'} and not set(sq.PINNED_PARTS) & set(sq.PINNED_TEMPLATES)
           and set(sq.PINNED_PARTS) | set(sq.PINNED_TEMPLATES) == set(sq.EXPECTED_PARTS) - {f'xl/worksheets/sheet{k}.xml' for k in (1, 2, 3, 4)},
           {'outputs': n_pinned, 'titled': n_titled_pinned, 'deliverables': n_deliv_pinned, 'differ': differ[:10]})

    # ------------------------------------------------ (j) number text (second review F1(b))
    # Every form the writer writes is JavaScript String(v) (writer_portable js_number); saved_qa's pattern accepts each one.
    # The fidelity output holds the first ten at the given main-sheet cells; the others are checked against node String(v).
    forms = [('seventeen_digit_double', 0.30000000000000004, '0.30000000000000004', 'F2'), ('exponent_negative_1e-7', 1e-7, '1e-7', 'F3'),
             ('integer_from_grouped_text', 1234567.0, '1234567', 'Q3'), ('integer_2_52_plus_1', 4503599627370497.0, '4503599627370497', 'F4'),
             ('fraction_1_0000000000000002', 1.0000000000000002, '1.0000000000000002', 'P4'), ('subnormal_5e-324', 5e-324, '5e-324', 'F5'),
             ('negative_zero_written_0', -0.0, '0', 'F6'), ('fraction_0_000001_no_exponent', 1e-6, '0.000001', 'Q6'),
             ('fraction_0_7999999999999999', 0.7999999999999999, '0.7999999999999999', 'F7'),
             ('fraction_123456789_12345678', 123456789.12345678, '123456789.12345678', 'P7'),
             ('negative_integer', -5.0, '-5', None), ('negative_fraction', -1234.5, '-1234.5', None), ('negative_exponent', -1e-7, '-1e-7', None),
             ('max_safe_integer', 9007199254740991.0, '9007199254740991', None), ('exponent_positive_1e21', 1e21, '1e+21', None),
             ('max_double', 1.7976931348623157e308, '1.7976931348623157e+308', None), ('min_normal', 2.2250738585072014e-308, '2.2250738585072014e-308', None)]
    vp2 = work / 'number_forms.json'
    vp2.write_text(json.dumps([f[1] for f in forms]), encoding='ascii')
    code, out, err = run(['node', '-e', "const v=JSON.parse(require('node:fs').readFileSync(process.argv[1],'utf8'));"
                                        "process.stdout.write(JSON.stringify(v.map(x=>String(x))))", vp2])
    node_str = json.loads(out) if code == 0 else []
    with zipfile.ZipFile(fid_out / 'research-draft.xlsx') as z:
        vtexts = dict(re.findall(r'<c r="([A-Z]+[0-9]+)"[^>]*><v>([^<]*)</v></c>', z.read('xl/worksheets/sheet1.xml').decode('utf-8')))
    fid_main = json.loads((fid_out / 'EXPECTED_SAVED_VALUES.json').read_text(encoding='utf-8'))['sheets'][0]['values']
    for k, (label, v, js, cell) in enumerate(forms):
        in_output = cell is None or (vtexts.get(cell) == js and same_value(fid_main[int(cell[1:]) - 1][ord(cell[0]) - 65], v))
        record(f'j_number_text_form_{label}', len(node_str) == len(forms) and node_str[k] == js == wp.js_number(v) and sq.number_text_ok(js) and in_output,
               {'node': node_str[k] if k < len(node_str) else None, 'python': wp.js_number(v), 'xlsx': vtexts.get(cell)})
    refused = ['1_234_567', '\uff11\uff12\uff13', '\u0661\u0662', ' 1', '1 ', '1\n', '+1', '1E-7', '1e5', '.5', '1.', '01', '00', '0x1F', 'NaN',
               'Infinity', '-Infinity', '', '-', '1e', '1e+', '\u00b2', '1,234', '1.2.3']
    record('j_number_text_refuses_other_forms', not [x for x in refused if sq.number_text_ok(x)], [x for x in refused if sq.number_text_ok(x)])
    # the pattern accepts js_number of every number of the 3,000-value fuzz (node equality: test a_js_stringify_fuzz_parity_3000)
    # and of 20,000 random finite binary64 values
    def numbers(v):
        if isinstance(v, bool) or v is None or isinstance(v, str):
            return []
        if isinstance(v, (int, float)):
            return [v]
        return [n for x in (v.values() if isinstance(v, dict) else v) for n in numbers(x)]
    rnd = random.Random(2404)
    pool = [n for x in parsed for n in numbers(x)]
    while len(pool) < len([n for x in parsed for n in numbers(x)]) + 20000:
        f = struct.unpack('<d', rnd.getrandbits(64).to_bytes(8, 'little'))[0]
        if math.isfinite(f):
            pool.append(f)
    bad_num = [wp.js_number(n) for n in pool if math.isfinite(float(n)) and not sq.number_text_ok(wp.js_number(n))]
    record('j_number_text_accepts_js_number_of_fuzz_and_random_doubles', len(pool) > 20000 and not bad_num, {'count': len(pool), 'refused': bad_num[:5]})
    # every number text in every writer output of this run matches (saved QA passed on each, so this is the same check made explicit)
    texts, bad_t = 0, []
    for od in sorted([d for d in outs.iterdir() if (d / 'research-draft.xlsx').is_file()] + [fid_out, fid_v2]):
        with zipfile.ZipFile(od / 'research-draft.xlsx') as z:
            for part in z.namelist():
                if part.startswith('xl/worksheets/'):
                    for t_ in re.findall(r'<v>([^<]*)</v>', z.read(part).decode('utf-8')):
                        texts += 1
                        if not sq.number_text_ok(t_):
                            bad_t.append([od.name, part, t_])
    record('j_every_number_text_in_every_output_matches', texts > 500 and not bad_t, {'texts': texts, 'refused': bad_t[:5]})

    # ------------------------------------------------ (i) visual_qa helpers (review S4, N1), without LibreOffice
    vq = load(EXPORT / 'visual_qa.py', 'visual_qa_under_test')
    names4 = list(wp.SHEET_ORDER)
    text = ('[[組成參考]]      Page 3 / 4\n未填研究草稿 盤體名稱\n組成連結\f'
            '[[來源與審查]]   Page 2 / 4\n"sheet":"未填研究草稿"\f'
            'no marker 未填研究草稿\f'
            '[[other]] 組成連結\f')
    record('i_map_pages_by_marker', vq.map_pages(text, names4) == {1: '組成參考', 2: '來源與審查', 3: None, 4: None, 5: None}
           and vq.map_pages(text, names4, 2) == {1: '組成參考', 2: '來源與審查'}, vq.map_pages(text, names4))
    xlsx_patch = vq.patch_sheet('<worksheet><sheetData/><pageMargins left="1"/></worksheet>')
    record('i_header_marker_in_print_patch', '&amp;L[[&amp;A]]' in xlsx_patch and vq.HEADER_MARKER == '[[{}]]', xlsx_patch)
    clip_long = vq.possibly_clipped_cells(outs / 'v05_long_text' / 'research-draft.xlsx')
    flagged = {(f['sheet'], f['cell']) for f in clip_long['first']}
    record('i_possibly_clipped_cells_long_text', {('未填研究草稿', 'C3'), ('未填研究草稿', 'D2')} <= flagged
           and all(f['estimated_height_pt'] > 409 for f in clip_long['first']), sorted(flagged)[:10])
    clip_base = vq.possibly_clipped_cells(outs / 'v01_base' / 'research-draft.xlsx')
    record('i_possibly_clipped_cells_none_in_base', clip_base['count'] == 0 and clip_base['string_cells_checked'] > 100, clip_base['first'][:3])
    record('i_estimated_lines', vq.estimated_lines('a' * 30, 10) == 3 and vq.estimated_lines('中' * 10, 10) == 2
           and vq.estimated_lines('a\nb\r\nc', 10) == 3 and vq.estimated_lines('', 10) == 1)

    # ------------------------------------------------ (d) visual QA
    if not a.skip_visual:
        vis = work / 'visual'
        vis.mkdir()
        manifests = []
        for tag in ('run1', 'run2'):
            code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', first / 'research-draft.xlsx', '--dest', vis / f'v01_{tag}'])
            mp = vis / f'v01_{tag}' / 'VISUAL_QA_MANIFEST.json'
            manifests.append(json.loads(mp.read_text(encoding='utf-8')) if mp.is_file() else None)
            record(f'd_visual_qa_ran_{tag}', code == 0 and manifests[-1] is not None, err[-400:])
        m1, m2 = manifests
        if m1 and m2:
            files_ok = all((vis / 'v01_run1' / i['file']).is_file() and sha((vis / 'v01_run1' / i['file']).read_bytes()) == i['sha256']
                           and (vis / 'v01_run1' / i['file']).read_bytes()[:8] == b'\x89PNG\r\n\x1a\n' for i in m1['images'])
            record('d_pngs_exist_and_hashes_match_manifest', m1['pages'] >= 4 and files_ok, {'pages': m1['pages']})
            record('d_png_renders_reproducible', [i['sha256'] for i in m1['images']] == [i['sha256'] for i in m2['images']])
            record('d_every_sheet_rendered', {i['sheet'] for i in m1['images']} >= set(wp.SHEET_ORDER), [i['sheet'] for i in m1['images']])
            record('d_saved_xlsx_unchanged_and_sheetdata_identical', m1['saved_xlsx']['unchanged_after_render'] and m1['render_copy']['sheetData_identical_to_saved']
                   and m1['saved_xlsx']['sha256'] == sha((first / 'research-draft.xlsx').read_bytes()))
            record('d_every_page_mapped_to_a_sheet', m1['page_sheet_mapping'] and all(m1['page_sheet_mapping'].values()) and m1['complete_render'])
            lim = ' '.join(m1.get('limitations', []))
            record('d_manifest_states_render_limits', 'General format' in lim and 'row taller than one printed page is clipped' in lim
                   and 'complete_render means that every PDF page was rendered' in lim and 'Never re-save' in lim
                   and m1.get('possibly_clipped_cells', {}).get('count') == 0 and '[[sheet name]] marker' in (m1.get('page_sheet_mapping_basis') or '')
                   and all('[[&A]]' in c['inserted'] for c in m1['render_copy']['modifications'] if 'sheet' in c) and m1['tool'] == 'cps-export-visual-qa.v4.4'
                   and not any('printOptions' in c['inserted'] for c in m1['render_copy']['modifications'] if 'sheet' in c)
                   and m1.get('main_sheet') == '未填研究草稿' and m1.get('sheet_order') == wp.SHEET_ORDER,
                   {'limitations': m1.get('limitations'), 'basis': m1.get('page_sheet_mapping_basis')})
        keep = ['未填研究草稿', '組成參考', '組成連結']
        code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', outs / 'v08_many_items' / 'research-draft.xlsx', '--dest', vis / 'v08_filtered',
                                   '--sheets', ','.join(keep), '--dpi', '100'])
        mf = json.loads((vis / 'v08_filtered' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
        mapping = mf.get('page_sheet_mapping') or {}
        want_pages = sorted(int(n) for n, s_ in mapping.items() if s_ in keep)
        record('d_visual_qa_sheet_filter_large_fixture', code == 0 and [i['page'] for i in mf['images']] == want_pages and len(want_pages) >= 3
               and {i['sheet'] for i in mf['images']} == set(keep) and mf['pdf']['pages'] > len(want_pages) and mf['complete_render'] is False,
               {'stderr': err[-300:], 'rendered': len(mf.get('images', [])), 'pdf_pages': mf.get('pdf', {}).get('pages')})
        for name in ('w01_job_inputs', 'w10_example046f'):
            code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', outs / f'v2_{name}' / 'research-draft.xlsx', '--dest', vis / f'v2_{name}'])
            mv = json.loads((vis / f'v2_{name}' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
            record(f'd_visual_qa_v2_output_{name}', code == 0 and {i['sheet'] for i in mv.get('images', [])} >= set(wp.SHEET_ORDER) and mv.get('complete_render'), err[-300:])
        code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', outs / 'v05_long_text' / 'research-draft.xlsx', '--dest', vis / 'v05_long_text', '--dpi', '50'])
        ml = json.loads((vis / 'v05_long_text' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
        fl = {(f['sheet'], f['cell']) for f in ml.get('possibly_clipped_cells', {}).get('first', [])}
        record('d_visual_qa_long_text_lists_possibly_clipped_cells', code == 0 and {('未填研究草稿', 'C3'), ('未填研究草稿', 'D2')} <= fl
               and ml.get('complete_render') is True and all(ml['page_sheet_mapping'].values()), {'stderr': err[-300:], 'flagged': sorted(fl)[:8]})
        code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', outs / 'v04_text_edges' / 'research-draft.xlsx', '--dest', vis / 'v04_exact', '--mode', 'exact'])
        me = json.loads((vis / 'v04_exact' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
        record('d_visual_qa_exact_mode', code == 0 and me.get('pages', 0) >= 1 and me['render_copy']['identical_to_saved']
               and me.get('main_sheet') == '未填研究草稿' and me.get('sheet_order') == wp.SHEET_ORDER, err[-300:])
        # v3 (writer v2.6, O33/O34): titled outputs map every page to its sheet and the manifest names the main sheet; --sheet
        # selects a sheet whose name holds a comma; main-sheet pages show no #F1F3F5 area, while the O34a tamper (G/H grey again),
        # rendered as a control, does
        def grey_pixels(png):
            from PIL import Image
            with Image.open(png) as im:
                return next((n_ for n_, col in im.convert('RGB').getcolors(1 << 24) if col == (0xF1, 0xF3, 0xF5)), 0)
        vis_titled = {}
        for tag, title in (('fid_special', T_SPECIAL), ('v01_long', T_LONG)):
            dv = sq.derive_deliverable(title)
            code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', titled.get(tag, work / 'missing') / dv['qa_workbook_file'], '--dest', vis / f't_{tag}', '--dpi', '100'])
            mt_ = json.loads((vis / f't_{tag}' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
            vis_titled[tag] = mt_
            mp_ = mt_.get('page_sheet_mapping') or {}
            record(f'd_visual_qa_titled_{tag}', code == 0 and mt_.get('complete_render') is True and mp_ and all(mp_.values())
                   and set(mp_.values()) == set(mt_.get('sheet_order') or []) and mt_.get('main_sheet') == dv['main_sheet']
                   and mt_.get('sheet_order') == [dv['main_sheet']] + wp.SHEET_ORDER[1:] and mt_.get('tool') == 'cps-export-visual-qa.v4.4'
                   and {i['sheet'] for i in mt_['images']} == set(mt_['sheet_order']) and mt_['saved_xlsx']['unchanged_after_render'],
                   {'stderr': err[-300:], 'mapping': list(mp_.values())[:6], 'main_sheet': mt_.get('main_sheet')})
        dv_s = sq.derive_deliverable(T_SPECIAL)
        code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', titled.get('fid_special', work / 'missing') / dv_s['qa_workbook_file'], '--dest', vis / 't_fid_special_filter',
                                   '--dpi', '50', '--sheet', dv_s['main_sheet'], '--sheet', '組成連結'])
        mf2 = json.loads((vis / 't_fid_special_filter' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
        record('d_visual_qa_sheet_option_selects_a_name_with_a_comma', code == 0 and ',' in dv_s['main_sheet']
               and {i['sheet'] for i in mf2.get('images', [])} == {dv_s['main_sheet'], '組成連結'} and mf2.get('complete_render') is False
               and mf2.get('sheet_filter') == [dv_s['main_sheet'], '組成連結'] and all((mf2.get('page_sheet_mapping') or {'x': None}).values()), err[-300:])
        code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', td / 'O34a_gh_grey_fill_restored' / 'research-draft.xlsx', '--dest', vis / 'o34a_control', '--dpi', '100'])
        mc_ = json.loads((vis / 'o34a_control' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
        grey = {}
        for tag, mf_, root in (('v01_untitled', m1 or {}, vis / 'v01_run1'), ('fid_special_titled', vis_titled.get('fid_special', {}), vis / 't_fid_special'),
                               ('v01_long_titled', vis_titled.get('v01_long', {}), vis / 't_v01_long'), ('o34a_control', mc_, vis / 'o34a_control')):
            grey[tag] = [grey_pixels(root / i['file']) for i in mf_.get('images', []) if i['sheet'] == mf_.get('main_sheet')]
        record('d_visual_gh_not_grey', all(grey[k] and max(grey[k]) <= 50 for k in ('v01_untitled', 'fid_special_titled', 'v01_long_titled'))
               and grey['o34a_control'] and min(grey['o34a_control']) >= 1000, grey)
        # v4 (O38): the deliverable renders as one sheet with printed gridlines, the #C0C0C0 header and no #29445D header;
        # the L05 tamper (dark-blue header fill) as a control
        def colour_pixels(png, rgb):
            from PIL import Image
            with Image.open(png) as im:
                return next((n_ for n_, col in im.convert('RGB').getcolors(1 << 24) if col == rgb), 0)
        dl_px = {}
        for tag, xl in (('v01_t1', titled.get('v01_t1', work / 'missing') / sq.derive_deliverable(T1)['xlsx_file']),
                        ('v05_long', titled.get('v05_long', work / 'missing') / sq.derive_deliverable(T1)['xlsx_file']),
                        ('L05_control', ldt / 'L05_header_fill_dark_blue' / sq.derive_deliverable(T_SPECIAL)['xlsx_file'])):
            code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', xl, '--dest', vis / f'dl_{tag}', '--dpi', '100'])
            md_ = json.loads((vis / f'dl_{tag}' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
            mods = [c['inserted'] for c in md_.get('render_copy', {}).get('modifications', []) if 'sheet' in c]
            dl_px[tag] = [(colour_pixels(vis / f'dl_{tag}' / i['file'], (0xC0, 0xC0, 0xC0)), colour_pixels(vis / f'dl_{tag}' / i['file'], (0x29, 0x44, 0x5D)))
                          for i in md_.get('images', [])]
            if tag != 'L05_control':
                record(f'd_visual_qa_deliverable_{tag}', code == 0 and md_.get('complete_render') is True and len(md_.get('sheet_order') or []) == 1
                       and md_['main_sheet'] == md_['sheet_order'][0] and all(md_.get('page_sheet_mapping', {}).values())
                       and len(mods) == 1 and 'printOptions gridLines=1' in mods[0] and 'possibly_cut_cells' in md_
                       and md_['saved_xlsx']['unchanged_after_render'] and dl_px[tag] and min(p_[0] for p_ in dl_px[tag]) >= 1000
                       and max(p_[1] for p_ in dl_px[tag]) <= 50 and (tag != 'v05_long' or md_['possibly_cut_cells']['count'] >= 2),
                       {'stderr': err[-300:], 'pixels': dl_px[tag], 'mods': mods, 'cut': (md_.get('possibly_cut_cells') or {}).get('count')})
        # v4.4 (F3): without --dpi the delivered workbook is rendered at the auto dpi and tiled; as the reviewer's viewer shows
        # them (at most 2000 px wide, so a tile of at most 1900 px at full size) the CJK body glyphs are at least 9.2 px
        for tag, xl in (('v05_long', titled.get('v05_long', work / 'missing') / sq.derive_deliverable(T1)['xlsx_file']),
                        ('wide', x_wide if 'x_wide' in dir() else work / 'missing')):
            code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', xl, '--dest', vis / f'tiles_{tag}'])
            md_ = json.loads((vis / f'tiles_{tag}' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
            tiles_ok, glyph_px = bool(md_.get('images')), None
            for im_ in md_.get('images', []):
                tl = im_.get('tiles') or []
                tiles_ok = tiles_ok and bool(tl) and all(
                    sha((vis / f'tiles_{tag}' / t_['file']).read_bytes()) == t_['sha256'] and t_['png_width_px'] <= 1900
                    and t_['png_height_px'] <= 1900 for t_ in tl)
            if code == 0:
                bb = subprocess.run(['pdftotext', '-bbox', '-f', '1', '-l', '1', str(vis / f'tiles_{tag}' / 'rendered.pdf'), '-'],
                                    capture_output=True, text=True).stdout
                hs = sorted(float(y1) - float(y0) for y0, y1, w_ in re.findall(r'<word xMin="[^"]*" yMin="([^"]*)" xMax="[^"]*" yMax="([^"]*)">([^<]*)</word>', bb)
                            if any(0x4e00 <= ord(c_) <= 0x9fff for c_ in w_))
                glyph_px = round(hs[len(hs) // 2] * md_['dpi'] / 72, 2) if hs else None
            record(f'd_visual_qa_deliverable_tiles_and_glyph_size_{tag}', code == 0 and tiles_ok and md_.get('tiles', {}).get('count', 0) >= len(md_.get('images', []))
                   and md_.get('dpi_rule', '').startswith('auto: delivered') and glyph_px is not None and glyph_px >= 9.2
                   and md_['tiles']['legibility_bound_exceeded'] is False,
                   {'stderr': err[-300:], 'dpi': md_.get('dpi'), 'tiles': (md_.get('tiles') or {}).get('count'), 'glyph_px': glyph_px})
        record('d_visual_qa_deliverable_header_colour_control', dl_px.get('L05_control') and max(p_[1] for p_ in dl_px['L05_control']) >= 1000, dl_px.get('L05_control'))

    failed = [r for r in results if not r['pass']]
    summary = {'suite': 'cps-export-portable-writer-tests.v6', 'tests': len(results), 'passed_count': len(results) - len(failed),
               'failed_count': len(failed), 'passed': [r['test'] for r in results if r['pass']], 'failed': failed,
               'fixtures_invented': True, 'valid_fixtures': len(valid), 'invalid_fixtures': len(invalid),
               'valid_fixtures_v2': len(valid2), 'invalid_fixtures_v2': len(invalid2),
               'saved_qa_tampers': len(tampers), 'saved_qa_tampers_v2': len(tampers2), 'saved_qa_tampers_downgrade': len(tamd),
               'receipt_claim_tampers': n_receipt_tampers, 'pinned_part_outputs_checked': n_pinned,
               'titled_outputs': len(titled), 'naming_tampers': len(ntamp), 'name_derivation_cases': len(name_cases) + len(refusal_cases) + 1,
               'deliverable_tampers': len(ltamp),
               'checker_node': {'realpath': node_real, 'sha256': node_sha, 'version': node_version},
               'make_tamper_fixtures_sha256': sha((HERE / 'make_tamper_fixtures.py').read_bytes()),
               'writer_portable_sha256': sha((EXPORT / 'writer_portable.py').read_bytes()),
               'saved_qa_sha256': sha((EXPORT / 'saved_qa.py').read_bytes()), 'visual_qa_sha256': sha((EXPORT / 'visual_qa.py').read_bytes()),
               'writer004_matrices_sha256': sha((EXPORT / 'writer004_matrices.mjs').read_bytes()), 'visual_skipped': a.skip_visual,
               'admitted': False}
    (work / 'EXPORT_TEST_RESULTS.json').write_text(json.dumps({'summary': summary, 'results': results}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
