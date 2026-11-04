"""Tests for the CPS portable export route (NOT ADMITTED). Invented fixtures only.

Proves on invented carriers:
  (a) writer_portable matrices == archived writer004 prepareMatrices (node + stub), byte-exact
      EXPECTED_SAVED_VALUES.json text and structural equality; JSON.stringify fuzz parity;
  (b) write -> saved_qa round trip has 0 mismatches (plus the original checkpoint045 saved QA);
      saved_qa detects injected defects; repeated builds are byte-identical;
  (c) invalid carriers are refused (writer004 gate codes, prepareMatrices review-cell code,
      documented portable-only refusals) and leave no output;
  (d) visual_qa produces PNGs reproducibly;
  (e) mode v2 (candidate 046f, owner decision O13): carriers with M/N job-input selection evidence
      pass writer004 on the documented placeholder copy plus the route v4 port, and the saved values
      equal writer004 prepareMatrices on that copy except the M/N evidence cells; carriers without
      it take the v1 route unchanged; v2 refusals come from writer004 or the route port as documented.
Usage: python3 -I -B run_export_tests.py --writer-dir /abs/archived/writer --work /abs/new-dir [--skip-visual]
Prints a JSON summary with passed and failed lists; exit 0 only if nothing failed.
"""
import argparse, copy, hashlib, importlib.util, json, math, random, shutil, struct, subprocess, sys, zipfile
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


def sha(b):
    return hashlib.sha256(b).hexdigest()


def record(name, ok, detail=None):
    results.append({'test': name, 'pass': bool(ok), **({'detail': detail} if detail is not None and not ok else {})})
    return ok


def run(cmd, timeout=900):
    p = subprocess.run([str(x) for x in cmd], capture_output=True, timeout=timeout)
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


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


def placeholder_copy_independent(c):
    """Test-side implementation of the documented O13 placeholder method (README, mode v2)."""
    c = copy.deepcopy(c)
    for r in c['items'] + c['components']:
        for k in ('M', 'N'):
            e = r['evidence'].get(k)
            if isinstance(e, dict) and 'selection_evidence' in e:
                rest = {x: y for x, y in e.items() if x != 'selection_evidence'}
                r['evidence'][k] = dict(rest, location=copy.deepcopy(r['location']), anchor=r['anchor'], raw_text=e['selection_evidence'])
    return c


def mn_fields(c):
    return [f"{r['id']}.{k}" for r in c['items'] + c['components'] for k in ('M', 'N') if 'selection_evidence' in r['evidence'].get(k, {})]


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

    # ------------------------------------------------ (e) mode v2: O13 relaxation for 046f carriers
    r46 = load(ROUTE46F, 'cps046f_route_reference')
    record('e_route_v4_version_matches_writer', r46.VERSION == wp.ROUTE_V4_VERSION == 'cps046f-route.v4'
           and wp.ROUTE_V4_TOOL.resolve() == ROUTE46F.resolve())
    fx6 = work / 'route046f_fixtures'
    code, out, err = run(PY + [ROUTE46F_FIXTURES, fx6])
    record('e_route046f_make_fixtures', code == 0, err[-300:])
    carriers6 = {}
    for tag, resp in (('jobs', 'valid_response_job_inputs.json'), ('plain', 'valid_response.json')):
        code, out, err = run(PY + [ROUTE46F, 'convert', '--inventory', fx6 / 'fixture_inventory.json', '--response', fx6 / resp,
                                   '--out-dir', work / f'route046f_{tag}'])
        carriers6[tag] = work / f'route046f_{tag}' / 'carrier.json'
        record(f'e_route046f_convert_{tag}', code == 0 and carriers6[tag].is_file(), (out + err)[-300:])
    ef2 = work / 'export_fixtures_v2'
    code, out, err = run(PY + [HERE / 'make_export_fixtures_v2.py', carriers6['jobs'], carriers6['plain'], ef2])
    record('e_make_export_fixtures_v2', code == 0, err[-300:])
    index2 = json.loads((ef2 / 'FIXTURES_V2.json').read_text(encoding='utf-8'))['fixtures']
    valid2 = [x for x in index2 if x['valid']]
    invalid2 = [x for x in index2 if not x['valid']]
    record('e_fixture_counts_v2', len(valid2) >= 6 and len(invalid2) >= 9, {'valid': len(valid2), 'invalid': len(invalid2)})
    jobs_obj = json.loads(carriers6['jobs'].read_text(encoding='utf-8'))
    record('e_writer_placeholder_method_equals_test_implementation',
           same_value(wp.o13_placeholder_copy(jobs_obj), placeholder_copy_independent(jobs_obj)) and len(mn_fields(jobs_obj)) == 18)
    # writer004 itself still refuses the original 046f carrier (documented divergence), in v1 mode too
    c2, o2, e2 = run(['node', wd / 'validate_carrier_v4.mjs', '--carrier', carriers6['jobs']])
    record('e_writer004_refuses_original_mn_selection', c2 == 1 and json.loads(e2).get('code') == 'SELECTION_ONLY_ENGINEERING_ID')
    code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', carriers6['jobs'], '--out', outs / 'v1mode_jobs', '--writer-dir', wd])
    ref = json.loads(err.strip().splitlines()[-1]) if err.strip() else {}
    record('e_v1_mode_refuses_mn_selection_unchanged', code == 1 and ref.get('code') == 'SELECTION_ONLY_ENGINEERING_ID'
           and ref.get('stage') == 'gate:validate_carrier_v4' and not (outs / 'v1mode_jobs').exists(), ref)
    # independent copies for the node parity probe
    probe = []
    for x in valid2:
        text = Path(x['file']).read_bytes().decode('utf-8')
        obj = json.loads(text[1:] if text.startswith('\ufeff') else text)
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
        fields = mn_fields(obj)
        if x['o13_expected']:
            ok = (rc['mode'] == 'v2' and rc['o13']['applied'] is True and rc['o13']['fields'] == fields
                  and rc['o13']['route_v4_port']['result'] == 'PASS' and rc['o13']['route_v4_port']['version'] == 'cps046f-route.v4'
                  and rc['o13']['route_v4_port']['sha256'] == sha(ROUTE46F.read_bytes())
                  and rc['o13']['writer004_cross_check_on_placeholder_copy']['result'] == 'BYTE_IDENTICAL'
                  and rc['gate']['result']['status'] == 'WRITER_STRUCTURAL_VALIDATION_ONLY'
                  and rc['expected_saved_values']['identical_to_writer004_prepareMatrices_output'] is False
                  and any(l.startswith('O13 relaxation') for l in rc['limitations']) and rc['admitted'] is False)
            record(f"e_receipt_v2_{x['name']}", ok, {k: rc.get(k) for k in ('mode', 'o13')})
            # independent check: saved values == writer004 prepareMatrices on the copy, except M/N evidence cells
            mine = json.loads(exp.decode('utf-8'))['sheets']
            theirs = json.loads(nr['text'])['sheets'] if nr.get('ok') else []
            diffs, outside = [], []
            for sa, sb in zip(mine, theirs):
                if sa['name'] != sb['name'] or len(sa['values']) != len(sb['values']):
                    outside.append(sa['name'])
                    continue
                for i, (ra, rb) in enumerate(zip(sa['values'], sb['values'])):
                    for j, (va, vb) in enumerate(zip(ra, rb)):
                        if not same_value(va, vb):
                            if sa['name'] == '來源與審查' and ra[0] == '欄位依據' and ra[1] in fields and j in (2, 3, 4):
                                diffs.append((ra[1], j))
                            else:
                                outside.append((sa['name'], i + 1, j + 1))
            sel_rows = [ra for s_ in mine if s_['name'] == '來源與審查' for ra in s_['values'] if ra[0] == '欄位依據' and ra[1] in fields]
            record(f"e_saved_values_equal_writer004_on_copy_except_mn_evidence_{x['name']}",
                   len(mine) == len(theirs) == 4 and not outside and {d[0] for d in diffs} == set(fields)
                   and len(diffs) == len(rc['o13']['saved_matrices_differ_from_placeholder_copy_only_in']['cells'])
                   and all(ra[2] is None and ra[3] == '"已核對工程選取"' for ra in sel_rows) and len(sel_rows) == len(fields),
                   {'outside': outside[:5], 'diff_fields': len({d[0] for d in diffs}), 'fields': len(fields)})
        else:
            record(f"e_receipt_v2_{x['name']}", rc['mode'] == 'v2' and rc['o13'] == {'applied': False}
                   and rc['cross_check']['result'] == 'BYTE_IDENTICAL' and exp == nr['text'].encode('utf-8'), rc.get('o13'))
            code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', x['file'], '--out', outs / ('v1_' + x['name']), '--writer-dir', wd])
            record(f"e_v2_without_mn_equals_v1_bytes_{x['name']}", code == 0
                   and (outs / ('v1_' + x['name']) / 'research-draft.xlsx').read_bytes() == (od / 'research-draft.xlsx').read_bytes()
                   and (outs / ('v1_' + x['name']) / 'EXPECTED_SAVED_VALUES.json').read_bytes() == exp)
        code, out, err = run(PY + [EXPORT / 'saved_qa.py', '--output-dir', od])
        qa = json.loads((od / 'SAVED_QA.json').read_text(encoding='utf-8')) if (od / 'SAVED_QA.json').is_file() else {}
        t = qa.get('totals', {})
        record(f"e_saved_qa_round_trip_v2_{x['name']}", code == 0 and qa.get('status') == 'SAVED_ALL_CELL_VALUE_TYPE_PASS'
               and t.get('value_type_mismatches') == 0 and t.get('formulas') == 0 and t.get('formatting_failures') == 0, t)
        code, out, err = run(PY + [QA045, '--output', od, '--report', work / f"qa045_v2_{x['name']}.json"])
        record(f"e_checkpoint045_saved_qa_v2_{x['name']}", code == 0 and json.loads(out)['status'] == 'SAVED_ALL_CELL_VALUE_TYPE_PASS', (out + err)[-300:])
    code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', valid2[0]['file'], '--out', work / 'repeat_v2', '--writer-dir', wd, '--mode', 'v2'])
    record('e_repeat_build_v2_byte_identical', code == 0 and (work / 'repeat_v2' / 'research-draft.xlsx').read_bytes() == (outs / ('v2_' + valid2[0]['name']) / 'research-draft.xlsx').read_bytes()
           and (work / 'repeat_v2' / 'EXPECTED_SAVED_VALUES.json').read_bytes() == (outs / ('v2_' + valid2[0]['name']) / 'EXPECTED_SAVED_VALUES.json').read_bytes())
    for x in invalid2:
        od = outs / ('v2_' + x['name'])
        code, out, err = run(PY + [EXPORT / 'writer_portable.py', '--carrier', x['file'], '--out', od, '--writer-dir', wd, '--mode', 'v2'])
        try:
            ref = json.loads(err.strip().splitlines()[-1])
        except (ValueError, IndexError):
            ref = {}
        record(f"e_refused_v2_{x['name']}", code == 1 and not od.exists() and ref.get('status') == 'REFUSED'
               and ref.get('code') == x['expected_code'] and ref.get('stage') == x['expected_stage'], ref)

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
        keep = ['未填研究草稿', '組成參考', '組成連結']
        code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', outs / 'v08_many_items' / 'research-draft.xlsx', '--dest', vis / 'v08_filtered',
                                   '--sheets', ','.join(keep), '--dpi', '100'])
        mf = json.loads((vis / 'v08_filtered' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
        mapping = mf.get('page_sheet_mapping') or {}
        want_pages = sorted(int(n) for n, s_ in mapping.items() if s_ in keep)
        record('d_visual_qa_sheet_filter_large_fixture', code == 0 and [i['page'] for i in mf['images']] == want_pages and len(want_pages) >= 3
               and {i['sheet'] for i in mf['images']} == set(keep) and mf['pdf']['pages'] > len(want_pages) and mf['complete_render'] is False,
               {'stderr': err[-300:], 'rendered': len(mf.get('images', [])), 'pdf_pages': mf.get('pdf', {}).get('pages')})
        code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', outs / 'v2_w01_job_inputs' / 'research-draft.xlsx', '--dest', vis / 'v2_w01'])
        mv = json.loads((vis / 'v2_w01' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
        record('d_visual_qa_v2_o13_output', code == 0 and {i['sheet'] for i in mv.get('images', [])} >= set(wp.SHEET_ORDER) and mv.get('complete_render'), err[-300:])
        code, out, err = run(PY + [EXPORT / 'visual_qa.py', '--xlsx', outs / 'v04_text_edges' / 'research-draft.xlsx', '--dest', vis / 'v04_exact', '--mode', 'exact'])
        me = json.loads((vis / 'v04_exact' / 'VISUAL_QA_MANIFEST.json').read_text(encoding='utf-8')) if code == 0 else {}
        record('d_visual_qa_exact_mode', code == 0 and me.get('pages', 0) >= 1 and me['render_copy']['identical_to_saved'], err[-300:])

    failed = [r for r in results if not r['pass']]
    summary = {'suite': 'cps-export-portable-writer-tests.v1', 'tests': len(results), 'passed_count': len(results) - len(failed),
               'failed_count': len(failed), 'passed': [r['test'] for r in results if r['pass']], 'failed': failed,
               'fixtures_invented': True, 'valid_fixtures': len(valid), 'invalid_fixtures': len(invalid),
               'valid_fixtures_v2': len(valid2), 'invalid_fixtures_v2': len(invalid2),
               'writer_portable_sha256': sha((EXPORT / 'writer_portable.py').read_bytes()),
               'saved_qa_sha256': sha((EXPORT / 'saved_qa.py').read_bytes()), 'visual_qa_sha256': sha((EXPORT / 'visual_qa.py').read_bytes()),
               'writer004_matrices_sha256': sha((EXPORT / 'writer004_matrices.mjs').read_bytes()), 'visual_skipped': a.skip_visual,
               'admitted': False}
    (work / 'EXPORT_TEST_RESULTS.json').write_text(json.dumps({'summary': summary, 'results': results}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
