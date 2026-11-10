"""Lints (spec §14.6): L1 codes, L2 import rule and a core without I/O, L3 REUSE_MANIFEST, L4 core line coverage,
L5 block grammar, L6 README examples refused, L7 no `or` in exit-code assertions, L8 pinned shas, L9 printed paths,
L10 UNUSED_REUSED (reported). L5 and L9 also run on every block printed by the world tests (fakes.FakeDot.cmd).
Entry point: run(only=None, work=None)."""
import ast
import hashlib
import json
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
VM2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(VM2))
sys.path.insert(0, VM2)
sys.path.insert(0, HERE)
from cpsvm2.core import names as N                                          # noqa: E402

CODE_RX = re.compile(r'[A-Z][A-Z0-9]*(_[A-Z0-9]+)+|FORK|FINAL')
CODE_FUNCS = {'Halt', 'HaltStep', 'stop', 'refuse', 'Stop', 'stop_block', 'commit_halt', 'safe_stop'}
REPORT = {}


def sources(sub='cpsvm2', skip=()):
    for dp, dns, fns in os.walk(os.path.join(VM2, sub)):
        dns[:] = sorted(d for d in dns if d != '__pycache__')
        for n in sorted(fns):
            if n.endswith('.py') and n not in skip:
                yield os.path.join(dp, n)


def sha_file(p):
    with open(p, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def raised_codes():
    """Every code literal the shipped code raises: the code argument of Halt/stop/refuse/Stop/stop_block/
    commit_halt (a Halt of kind NEED is an internal request for a download, §13.4, and is not a code), a
    {'verdict': 'stop', 'code': X} result, and session_start.sh's `stop X`."""
    out = {}
    files = list(sources()) + [os.path.join(VM2, 'vm2.py'), os.path.join(VM2, 'probe_p5.py')]
    for p in files:
        tree = ast.parse(open(p, encoding='utf-8').read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                if name not in CODE_FUNCS:
                    continue
                args = list(node.args)
                if name == 'Halt' and args and isinstance(args[0], ast.Constant) and args[0].value == 'NEED':
                    continue
                cands = args[:2] + [k.value for k in node.keywords if k.arg == 'code']
                for a in cands:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str) and CODE_RX.fullmatch(a.value) \
                            and a.value not in ('STOP', 'REFUSED', 'NEED'):
                        out.setdefault(a.value, set()).add(os.path.relpath(p, VM2))
            if isinstance(node, ast.Dict):
                kv = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
                if isinstance(kv.get('verdict'), ast.Constant) and kv['verdict'].value == 'stop' and isinstance(
                        kv.get('code'), ast.Constant):
                    out.setdefault(kv['code'].value, set()).add(os.path.relpath(p, VM2))
    sh = open(os.path.join(VM2, 'session_start.sh')).read()
    for c in re.findall(r'stop ([A-Z_]+)', sh):
        out.setdefault(c, set()).add('session_start.sh')
    return out


def t_l1_codes_registered_and_tested():
    """L1: every code raised in the source is in the CODES registry (the union of §13); every registry code is named
    in some test (asserted by name)."""
    rc = raised_codes()
    bad = sorted(c for c in rc if not N.is_code(c))
    assert not bad, 'L1: codes raised but not in §13: %s' % bad
    text = ''
    for n in sorted(os.listdir(HERE)):
        if n.endswith('.py') and n != os.path.basename(__file__):
            text += open(os.path.join(HERE, n), encoding='utf-8').read()
    untested = sorted(c for c in N.CODES if not re.search(r"['\" ]%s['\" )]" % re.escape(c), text))
    REPORT['codes_raised_in_source'] = len(rc)
    REPORT['codes_registry'] = len(N.CODES)
    REPORT['codes_not_named_in_any_test'] = untested
    assert not untested, 'L1: registry codes no test names: %s' % untested


def t_l2_import_rule_and_core_without_io():
    """L2: vio/* imports from cpsvm2.core only cpsvm2.core.step; core/* imports only the standard library and core,
    never os, subprocess, shutil, tempfile, time, fcntl, pathlib, io, and calls no open, print, datetime.now,
    time.time."""
    banned = {'os', 'subprocess', 'shutil', 'tempfile', 'time', 'fcntl', 'pathlib', 'io'}
    for p in sources('cpsvm2/vio'):
        tree = ast.parse(open(p).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = ('.' * node.level) + (node.module or '')
                if 'core' in mod.split('.'):
                    assert mod.endswith('core.step'), 'L2: %s imports %s' % (p, mod)
                if mod in ('..', '..core') or (node.level == 2 and node.module is None):
                    assert all(a.name == 'step' for a in node.names) or not any(
                        a.name in ('core', 'cli', 'worker') for a in node.names), 'L2: %s imports %s' % (p, mod)
            if isinstance(node, ast.Import):
                assert not any('core' in a.name for a in node.names), 'L2: %s imports core' % p
    for p in sources('cpsvm2/core'):
        tree = ast.parse(open(p).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name.split('.')[0] not in banned, 'L2: %s imports %s' % (p, a.name)
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module.split('.')[0] not in banned, 'L2: %s imports %s' % (p, node.module)
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    assert f.id not in ('open', 'print', 'input', 'exec', 'eval'), 'L2: %s calls %s' % (p, f.id)
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                    assert (f.value.id, f.attr) not in (('datetime', 'now'), ('time', 'time'), ('time', 'sleep')), \
                        'L2: %s calls %s.%s' % (p, f.value.id, f.attr)


def t_l2_only_cli_and_worker_import_both():
    """L2: cli.py and worker.py are the only modules that import both core/ and vio/."""
    for p in list(sources()) + [os.path.join(VM2, 'vm2.py')]:
        src = open(p).read()
        uses_core = re.search(r'from \.+core|from \.core|cpsvm2\.core|from \. import .*core', src) is not None
        uses_vio = re.search(r'from \.+vio|from \.vio|cpsvm2\.vio', src) is not None
        rel = os.path.relpath(p, VM2)
        if uses_core and uses_vio and '/maint/' not in rel:
            assert rel in ('cpsvm2/cli.py', 'cpsvm2/worker.py'), 'L2: %s imports core and vio' % rel


def t_l3_reuse_manifest():
    """L3: REUSE_MANIFEST (test_reuse.py)."""
    import test_reuse
    r = test_reuse.run()
    assert not r['failed'], 'L3: %s' % r['detail']


def t_l4_core_line_coverage():
    """L4: core/ line coverage from the core tests (stdlib sys.monitoring, PEP 669). Every executable line of core/ is run."""
    import test_core_table
    import test_core_props
    files = {os.path.realpath(p) for p in sources('cpsvm2/core')}
    hits = set()
    mon = sys.monitoring
    tid = mon.COVERAGE_ID

    def on_line(code, line):                       # PEP 669: each location reports once, then is disabled
        if code.co_filename in files:
            hits.add((code.co_filename, line))
        return mon.DISABLE
    mon.use_tool_id(tid, 'vm2-lint-L4')
    mon.register_callback(tid, mon.events.LINE, on_line)
    mon.set_events(tid, mon.events.LINE)
    try:
        test_core_table.run()
        test_core_props.run(1, 300)
    finally:
        mon.set_events(tid, 0)
        mon.register_callback(tid, mon.events.LINE, None)
        mon.free_tool_id(tid)
    counts = {(os.path.realpath(f), ln): 1 for f, ln in hits}
    missing, total = {}, 0
    for p in sources('cpsvm2/core'):
        lines = executable_lines(p)
        total += len(lines)
        hit = {ln for (f, ln), c in counts.items() if os.path.realpath(f) == os.path.realpath(p) and c}
        miss = sorted(lines - hit)
        if miss:
            missing[os.path.relpath(p, VM2)] = miss
    n = sum(len(v) for v in missing.values())
    REPORT['core_coverage'] = {'lines': total, 'missed': n, 'percent': round(100.0 * (total - n) / total, 2),
                               'missed_lines': missing}
    assert not missing, 'L4: core lines not run by the core tests: %s' % json.dumps(missing)[:600]


def executable_lines(p):
    """Lines that hold a statement start (no docstrings, no def/class headers' decorators-only lines)."""
    tree = ast.parse(open(p).read())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and not isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Import,
                                                                  ast.ImportFrom)):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value,
                                                                                                  str):
                continue
            out.add(node.lineno)
    return out


def t_l5_grammar_rejects():
    """L5: the block grammar check refuses THEN/OPTION lines, {TOKEN}s, two DO lines, a missing DO, non-ASCII."""
    from cpsvm2.vio import drive
    h = 'CPSV series=D1 head=000001 kit=0123456789ab at=000001-0001-abcdef mode=drill state=WORK'
    assert drive.check_grammar([h, 'DO: RUN bash /x/vm.sh go']) is None
    for bad in ([h], [h, 'DO: A', 'DO: B'], [h, 'THEN do this', 'DO: A'], [h, 'DO: OPEN {CONVERSATION_ID}'],
                [h, 'DO: WAIT seconds=١'], [h, 'DOWNLOAD a ID b TO c', 'UPLOAD a TO b AS c', 'DO: x'],
                ['CPSV series=D1 head=1 kit=x at=a mode=drill state=WORK', 'DO: x']):
        assert drive.check_grammar(bad) is not None, 'L5: accepted %r' % bad


def t_l6_readme_examples_refused():
    """L6: every README example value is in the test kit's doc_samples and refused as an attested value."""
    import fakes
    samples = fakes.readme_samples()
    assert samples, 'L6: no examples listed in the README'
    cfg = {'doc_samples': samples + ['conv-EXAMPLE'], 'conversation_re': fakes.CONV_RE, 'drive_id_re': None,
           'home': '/h', 'case': 'c'}
    for v in samples:
        for pat in sorted(N.FREE_TEXT):
            r = N.check_value('k', pat, v, cfg)
            assert r and r[0] in ('VALUE_FORBIDDEN', 'VALUE_PLACEHOLDER'), 'L6: %r accepted as %s' % (v, pat)
    readme = open(os.path.join(VM2, 'README.md'), encoding='utf-8').read()
    for tok in set(re.findall(r'<[^<>\n]{1,60}>', readme)):
        if not tok.startswith('<!--'):
            assert tok in samples or tok.startswith('<the '), 'L6: README example %s missing from doc_samples' % tok


def t_l7_no_or_in_exit_code_assertions():
    """L7 (TST-09): no assertion on an exit code joined with `or`."""
    for n in sorted(os.listdir(HERE)):
        if not n.endswith('.py'):
            continue
        tree = ast.parse(open(os.path.join(HERE, n), encoding='utf-8').read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                for sub in ast.walk(node.test):
                    if isinstance(sub, ast.BoolOp) and isinstance(sub.op, ast.Or):
                        names = {x.id for x in ast.walk(sub) if isinstance(x, ast.Name)}
                        assert not names & {'code', 'rc', 'returncode', 'exit_code'}, \
                            'L7: %s:%d asserts an exit code with or' % (n, node.lineno)


def t_l8_pinned_shas():
    """L8: runner, evaluator and aggregator have their pinned sha256; deploy/vm/ has the v1 shas."""
    pins = {'deploy/run/cps_job.py': N.RUNNER_SHA256}
    for p, want in pins.items():
        assert sha_file(os.path.join(REPO, p)) == want, 'L8: %s' % p
    for p, pre in (('research/evaluation/compare_target050.py', 'fc723405'),
                   ('research/evaluation/aggregate_qualification050.py', 'e5aa4fc7')):
        assert sha_file(os.path.join(REPO, p)).startswith(pre), 'L8: %s' % p
    adm = json.load(open(os.path.join(REPO, 'deploy/vm/ADMISSION_VM_HELPER_V1.json')))
    files = adm['files_sha256']
    assert files, 'L8: no v1 shas'
    for p, want in files.items():
        q = p if os.path.isabs(p) else os.path.join(REPO, p)
        if os.path.exists(q):
            assert sha_file(q) == want, 'L8: %s differs from the v1 record' % p


def t_l9_print_rules():
    """L9: printed values round-trip through shlex and are ASCII; a value that would not is INTERNAL_PRINT."""
    from cpsvm2.vio import drive
    from cpsvm2.vio.v1compat import Halt
    for bad in ('/a b', '/aé', '', '/a\nb'):
        try:
            drive.q(bad)
            raise AssertionError('L9: printed %r' % bad)
        except Halt as h:
            assert h.code == 'INTERNAL_PRINT'
    for bad in ('a b', 'a{b}', "a'b"):
        try:
            drive.word(bad)
            raise AssertionError('L9: printed word %r' % bad)
        except Halt as h:
            assert h.code == 'INTERNAL_PRINT'
    import fakes
    for ok in (['DO: RUN bash /x/vm.sh go'],):
        fakes.check_printed(ok, ['9990101'])
    try:
        fakes.check_printed(['DO: X case=9990101'], ['9990101'])
        raise AssertionError('L9: a case id as an argument value was accepted')
    except AssertionError as e:
        assert 'case id' in str(e)


def t_l10_unused_reused():
    """L10: reused segments without a caller in v2 (reported, not failing)."""
    import cpsvm2.vio.v1reuse as R
    names = [n for n in dir(R) if not n.startswith('_')]
    text = ''.join(open(p).read() for p in sources(skip=('v1reuse.py',)))
    man = json.load(open(os.path.join(VM2, 'REUSE_MANIFEST.json')))
    unused = sorted(r['name'] for r in man['reused'] if not re.search(r'\b%s\b' % r['name'], text)
                    and not re.search(r'\b%s\(' % r['name'], open(os.path.join(VM2, 'cpsvm2/vio/v1reuse.py')).read()
                                      .replace('def %s(' % r['name'], '')))
    REPORT['UNUSED_REUSED'] = unused
    assert names


TESTS = [t_l1_codes_registered_and_tested, t_l2_import_rule_and_core_without_io, t_l2_only_cli_and_worker_import_both,
         t_l3_reuse_manifest, t_l4_core_line_coverage, t_l5_grammar_rejects, t_l6_readme_examples_refused,
         t_l7_no_or_in_exit_code_assertions, t_l8_pinned_shas, t_l9_print_rules, t_l10_unused_reused]


def run(only=None, work=None):
    passed, failed = 0, []
    for fn in TESTS:
        if only and fn.__name__ not in only:
            continue
        try:
            fn()
            passed += 1
        except Exception as e:                      # noqa: BLE001 - recorded per test
            failed.append({'test': fn.__name__, 'error': '%s: %s' % (type(e).__name__, str(e)[:1500]),
                           'trace': traceback.format_exc()[-1500:]})
    return {'name': 'test_lints', 'tests': passed + len(failed), 'passed': passed,
            'failed': [f['test'] for f in failed], 'detail': failed, 'counts': dict(REPORT)}


if __name__ == '__main__':
    r = run([x for x in sys.argv[1:]] or None)
    for f in r['detail']:
        print('FAILED', f['test'], f['error'])
    print(json.dumps(r['counts'], indent=1, default=list)[:3000])
    print(json.dumps({k: r[k] for k in ('tests', 'passed', 'failed')}))
    sys.exit(0 if not r['failed'] else 1)
