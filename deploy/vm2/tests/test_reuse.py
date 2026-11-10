"""REUSE_MANIFEST check (spec §1.4 steps 1-5, lint L3, IMP-10, IMP-11). No git needed. Entry point: run()."""
import ast
import builtins
import hashlib
import importlib
import json
import os
import re
import sys
import symtable

HERE = os.path.dirname(os.path.abspath(__file__))
VM2 = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(VM2))
sys.path.insert(0, VM2)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def segments(src):
    """{name: segment text} of the top-level FunctionDef/ClassDef nodes (§1.4 segment definition)."""
    lines, out = src.splitlines(keepends=True), {}
    for n in ast.parse(src).body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            first = min([n.lineno] + [d.lineno for d in n.decorator_list])
            out[n.name] = ''.join(lines[first - 1:n.end_lineno - 1]) + lines[n.end_lineno - 1][:n.end_col_offset]
    return out


def free_names(seg):
    """Names a segment loads that it does not bind itself (globals of its function and class scopes)."""
    out = set()

    def walk(t):
        for s in t.get_symbols():
            if s.is_referenced() and (s.is_global() or (t.get_type() == 'module' and not s.is_assigned()
                                                         and not s.is_imported())):
                out.add(s.get_name())
        for c in t.get_children():
            walk(c)
    walk(symtable.symtable(seg, '<seg>', 'exec'))
    return out - set(dir(builtins))


def load():
    man = json.load(open(os.path.join(VM2, 'REUSE_MANIFEST.json')))
    v1 = open(os.path.join(ROOT, man['source']), encoding='utf-8').read()
    tgt = open(os.path.join(ROOT, man['target']), encoding='utf-8').read()
    return man, v1, tgt


def t1_source_sha():
    man, _, _ = load()
    with open(os.path.join(ROOT, man['source']), 'rb') as f:
        assert sha(f.read()) == man['source_sha256'], 'deploy/vm/cps_vm.py changed'


def t2_segments_identical():
    man, v1, tgt = load()
    a, b = segments(v1), segments(tgt)
    for r in man['reused']:
        assert sha(a[r['name']].encode('utf-8')) == r['segment_sha256'], r['name'] + ' (v1)'
        assert sha(b[r['name']].encode('utf-8')) == r['segment_sha256'], r['name'] + ' (v1reuse)'


def t3_exact_names_in_order():
    man, _, tgt = load()
    defs = []
    for n in ast.parse(tgt).body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            defs.append(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            continue
        elif isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and n is ast.parse(tgt).body[0]:
            continue
        elif isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
            continue
        else:
            raise AssertionError('v1reuse.py holds a statement that is neither an import nor a reused definition')
    assert defs == [r['name'] for r in man['reused']], 'names or order differ from the manifest'
    assert len(defs) == len(man['reused'])


def t4_modified_differ():
    man, v1, _ = load()
    a = segments(v1)
    mod = segments(open(os.path.join(VM2, 'cpsvm2/vio/v1mod.py'), encoding='utf-8').read())
    for r in man['modified']:
        assert sha(a[r['name']].encode('utf-8')) == r['v1_segment_sha256'], r['name'] + ' (v1)'
        assert r['name'] in mod, r['name'] + ' missing in v1mod.py'
        assert sha(mod[r['name']].encode('utf-8')) != r['v1_segment_sha256'], r['name'] + ' equals v1'


def t5_free_names_resolve():
    man, _, tgt = load()
    reuse = importlib.import_module('cpsvm2.vio.v1reuse')
    segs = segments(tgt)
    for r in man['reused']:
        for n in free_names(segs[r['name']]):
            assert hasattr(reuse, n), '%s loads %s, which v1reuse does not define' % (r['name'], n)
    compat = importlib.import_module('cpsvm2.vio.v1compat')
    src = open(os.path.join(VM2, 'cpsvm2/vio/v1compat.py'), encoding='utf-8').read()
    for name, seg in segments(src).items():
        for n in free_names(seg):
            assert hasattr(compat, n), 'v1compat.%s loads %s, which v1compat does not define' % (name, n)


def t6_manifest_shape():
    man, _, _ = load()
    assert man['schema'] == 'cps.vm2-reuse-manifest.v1' and man['source_commit'] == \
        '95df27099c275ba1a8442df5087cb87b97434dae'
    assert man['source_sha256'] == '7524987159f579d426eb99a22983a414bbcfa9c5ba99ea655611b7d77d43e14a'
    assert sum(r['v1_lines'][1] - r['v1_lines'][0] + 1 for r in man['reused']) == 852
    assert sum(r['v1_lines'][1] - r['v1_lines'][0] + 1 for r in man['modified']) == 239


def t7_unused_reused_report():
    """L10: reused names no v2 module calls are reported (join_slices, scrub), not failing."""
    man, _, _ = load()
    text = ''
    for dp, _, fns in os.walk(os.path.join(VM2, 'cpsvm2')):
        for f in fns:
            if f.endswith('.py') and f != 'v1reuse.py':
                text += open(os.path.join(dp, f), encoding='utf-8').read()
    tgt = open(os.path.join(VM2, 'cpsvm2/vio/v1reuse.py'), encoding='utf-8').read()
    inner = set()
    for name, seg in segments(tgt).items():
        inner |= free_names(seg) - {name}
    unused = [r['name'] for r in man['reused'] if r['name'] not in inner
              and not any(tok == r['name'] for tok in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text))]
    REPORT['UNUSED_REUSED'] = unused


REPORT = {}
TESTS = [t1_source_sha, t2_segments_identical, t3_exact_names_in_order, t4_modified_differ, t5_free_names_resolve,
         t6_manifest_shape, t7_unused_reused_report]


def run(only=None):
    passed, failed = 0, []
    for fn in TESTS:
        if only and fn.__name__ not in only:
            continue
        try:
            fn()
            passed += 1
        except Exception as e:                      # noqa: BLE001 - recorded per test
            failed.append({'test': fn.__name__, 'error': '%s: %s' % (type(e).__name__, e)})
    return {'name': 'test_reuse', 'tests': passed + len(failed), 'passed': passed, 'failed': [f['test'] for f in failed],
            'detail': failed, 'counts': dict(REPORT)}


if __name__ == '__main__':
    r = run()
    print(json.dumps(r, indent=1))
    sys.exit(0 if not r['failed'] else 1)
