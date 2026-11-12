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
    files = list(sources()) + [os.path.join(VM2, 'vm2.py')]      # probe_p5.py's codes are not helper codes (§X.13)
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
    """L1: every code raised in the source is in the CODES registry (the union of §13 and the delta §X.13); every
    registry code is asserted by name in some test file; and, in a full run (run_tests.py without --only, this suite
    last), every registry code was raised or printed at least once while the other suites ran (tests/seen.py records
    them in every process)."""
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
    if os.environ.get('CPSVM2_SEEN_FULL') != '1':
        REPORT['codes_runtime'] = 'not checked (a partial run)'
        return
    import seen
    got = seen.collect(os.environ['CPSVM2_SEEN_DIR']) | seen.CODES
    REPORT['codes_seen_at_runtime'] = len(got & N.CODES)
    maint = set()                                   # the maintainer tools' own result codes (§10.2, §10.3; not §13)
    for n in ('assemble.py', 'score_check.py'):
        maint |= set(re.findall(r"(?:Refused|Bad)\('([A-Z][A-Z0-9_]+)'", open(os.path.join(VM2, 'cpsvm2/maint', n)).read()))
    REPORT['maintainer_codes_seen'] = sorted(c for c in got if not N.is_code(c) and c in maint)
    REPORT['codes_seen_not_registered'] = sorted(c for c in got if not N.is_code(c) and c not in maint)
    never = sorted(N.CODES - got)
    REPORT['codes_never_raised'] = never
    assert not never, 'L1: registry codes no test raised: %s' % never
    assert not REPORT['codes_seen_not_registered'], 'L1: unregistered codes printed: %s' % REPORT[
        'codes_seen_not_registered']


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
    import test_core_more
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
    test_core_table.ENUM.clear()                   # the enumeration is cached per process: run it again here
    try:
        for p in sorted(files):                    # module-level lines ran at import, before monitoring: run them again
            exec_module_body(p)
        test_core_table.run()
        test_core_props.run(1, 300)
        test_core_more.run()
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


def exec_module_body(p):
    """Execute a core module's top level once more, in a throwaway module of the same package (its module-level
    statements are covered by import; the monitor starts after the import)."""
    import types
    name = 'cpsvm2.core._cov_' + os.path.basename(p)[:-3]
    mod = types.ModuleType(name)
    mod.__package__, mod.__file__ = 'cpsvm2.core', p
    exec(compile(open(p, encoding='utf-8').read(), p, 'exec'), mod.__dict__)


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
    v21 = {'deploy/make_kit.py', 'deploy/test_make_kit.py'}        # changed on purpose by v2.1 (MAINT-6, MK-1, MK-2)
    for p, want in files.items():
        if p in v21:
            continue
        q = p if os.path.isabs(p) else os.path.join(REPO, p)
        if os.path.exists(q):
            assert sha_file(q) == want, 'L8: %s differs from the v1 record' % p


def t_l9_print_rules():
    """L9: printed values round-trip through shlex and are ASCII; a value that would not is INTERNAL_PRINT."""
    from cpsvm2.vio import drive
    from cpsvm2.vio.v1compat import Halt
    assert shlex_ok(drive.q('Dots Folder/CPS_JOB_RECORDS')), 'a folder name with a space is printed quoted (§6.1)'
    for bad in ('/aé', '', '/a\nb'):
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


def shlex_ok(printed):
    import shlex
    return len(shlex.split(printed)) == 1


def t_l11_no_detached_process():
    """L11 (§X.14, P5 FAIL): no detached or background process anywhere in the helper. AST scan of deploy/vm2/**/*.py
    except probe_p5.py and tests/: no subprocess.Popen, os.fork, os.setsid, os.spawn*, os.daemon, start_new_session,
    preexec_fn, multiprocessing or threading; session_start.sh has no setsid, nohup, disown or line ending in a bare &."""
    files = list(sources()) + [os.path.join(VM2, 'vm2.py')]
    for p in files:
        tree = ast.parse(open(p, encoding='utf-8').read())
        rel = os.path.relpath(p, VM2)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) and
                                                       node.module else [])
                assert not any(m.split('.')[0] in ('multiprocessing', 'threading') for m in mods), 'L11: %s' % rel
            if isinstance(node, ast.Attribute):
                assert not (node.attr == 'Popen' or node.attr in ('fork', 'setsid', 'daemon')
                            or node.attr.startswith('spawn')), 'L11: %s uses %s' % (rel, node.attr)
            if isinstance(node, ast.keyword):
                assert node.arg not in ('start_new_session', 'preexec_fn'), 'L11: %s passes %s' % (rel, node.arg)
    for ln in open(os.path.join(VM2, 'session_start.sh')).read().splitlines():
        code = ln.split('#', 1)[0].rstrip()
        assert not re.search(r'\b(setsid|nohup|disown)\b', code), 'L11: session_start.sh: %s' % ln
        assert not (code.endswith('&') and not code.endswith('&&')), 'L11: a background job: %s' % ln


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


def t_l13_launcher_ignores_bytecode():
    """L13 (S-07, W11, W84): the launcher session_start.sh writes runs python3 -I -B -X pycache_prefix=/dev/null, and
    session_start.sh removes every __pycache__ folder under the checkout before it writes the launcher."""
    t = open(os.path.join(VM2, 'session_start.sh')).read()
    assert 'exec python3 -I -B -X pycache_prefix=/dev/null' in t
    rm = t.find('-name __pycache__')
    assert rm >= 0 and 'rm -rf' in t[rm:rm + 120], 'session_start.sh removes __pycache__ folders'
    assert rm < t.find('exec python3 -I -B -X pycache_prefix=/dev/null'), 'before the launcher is written'


README_RULES = (                                # D10, OPX-04, OPX-09, D3, D4, D16 (§2.15.5 L14): exact README text
    'When in doubt, answer `UNSURE`.',
    'If you are not sure whether the platform refused an upload or failed, treat it as refused.',
    'Never work around a refused upload',
    'never repeat an upload',
    'NO_BLOCK',
    'RAW_INVALID',
    '`REFUSED INPUTS_CHANGED`',
    'date -u +%Y-%m-%dT%H:%M:%SZ',
    '`include_base64` false',
    'not_available',
    "any characters, up to the kit's max_ai_output_bytes, larger: `STOP AI_OUTPUT_TOO_LARGE HANDBACK C`",   # GAP-9
    'for everyday jobs into the everyday records folder `Dots Folder/CPS_JOB_RECORDS` and the profile\'s `deliveries` folder',
    'both must be inside the owner\'s standing pre-approval of uploads (section 7)',
    'With `tools=inventory` the record holds the kit\'s list (by its sha256), the platform\'s usual set, not a list read',
    # amendment A1-A3 (W130, W131): the base under /tmp, the two routes, the operating rules and their codes
    'export CPS_VM_BASE=/tmp/cps',
    'Run `bash /tmp/cps/vm.sh go`, then do the block it prints, exactly.',
    'through the elevated route (`sandbox_permissions` set to `require_escalated`)',
    'Run everything else for the helper through the standard route (`use_default`)',
    'Never move a helper command to the elevated route because it failed',
    'leave `prefix_rule` empty',
    'run no helper command',
    'never end your turn and never set a wait or a wake-up',
    '`CPS paused while a helper command or a CPS conversation ran: reply continue to resume.`',
    'Never use `ps`, `kill` or a process id to judge whether a helper command runs',
    'never start that command again yourself. Run `go` once and do the block it prints.',
    'Retry it once through the same route. If the review stops it again, stop and tell the owner `REVIEW_STOPPED`',
    'Never run it again through the elevated route or in another folder (the bootstrap is the exception, section 1). '
    'Stop and tell the owner `READ_ONLY_FS`',
    '`go` stops with `STOP SETUP_MISSING HANDBACK C` before the stage',
    # the amendment's fix round (delta v2.1 §9.8; W139-W143): the clear bootstrap, waits, the 6-hour claim, the exceptions
    'run exactly that, as one command through the elevated route, then run `go`. Never run `session_start.sh` alone',
    'The maintainer\'s message gives you the bootstrap of section 1 with its values filled in',
    'It holds nothing of the series, so it is the one command you start again yourself',
    'This is the one HANDBACK C stop you clear yourself: tell the owner, run the bootstrap once (with your notes)',
    'Between two checks of such a conversation run `sleep 300` in the foreground through the standard route',
    'Check it once every 5 minutes, with `sleep 300` in the foreground between checks',
    'A worker or a scheduled check (for example a mailbox check run by a worker) never runs the bootstrap or a helper '
    'command',
    'Uploads are never retried: an upload the review refused follows section 3.1.',
    'One inside the runner\'s tools shows as another stop of the helper',
    'the claim is younger than 6 hours',
    'If it does not say, tell the owner `MAILBOX_UNSETTLED` (case C) and do not run `go`.',
    'the polls and checks are estimates until the stage times and conversation lengths are measured on this VM',
    'A runner stage needs 2 GB free there',
)
README_ABSENT = ('STOP IDLE', 'then=', 'AWAIT_CONVERSATION', 'OPENED', 'LIST ', '/home/agent/cps', '~/cps/',
                 '~/cps-deliveries', 'Run that line exactly', 'bootstrap line', 'come from the stage times')


def t_l14_readme_rules():
    """L14 (W20, W95, W104, W105, W130, W131, W139-W143): the README keeps its rules verbatim (the outcome rule with
    UNSURE as the default, the refused-upload notes, the never-work-around and never-repeat sentences, NO_BLOCK, the RAW_INVALID
    table, the INPUTS_CHANGED step, the attested times, the DOWNLOAD route; amendment A1-A3: the /tmp/cps base, the two
    routes, the operating rules with REVIEW_STOPPED, READ_ONLY_FS and SETUP_MISSING, the disk need) and none of the
    removed tokens (also no old ~/cps or /home/agent/cps path). Fix round (CC-3, W139): the bootstrap block itself
    exports the base before it runs session_start.sh."""
    readme = open(os.path.join(VM2, 'README.md'), encoding='utf-8').read()
    flat = ' '.join(readme.split())
    blk = readme.split('<!-- bootstrap:begin -->', 1)[1].split('<!-- bootstrap:end -->', 1)[0].splitlines()
    ex = [i for i, ln in enumerate(blk) if ln == 'export CPS_VM_BASE=/tmp/cps']
    ss = [i for i, ln in enumerate(blk) if 'session_start.sh' in ln]
    assert len(ex) == 1 and len(ss) == 1 and ex[0] < ss[0], 'L14: the bootstrap block exports CPS_VM_BASE first'
    missing = [r for r in README_RULES if ' '.join(r.split()) not in flat]
    assert not missing, 'L14: README lacks %s' % missing
    for o in ('NOTHING_WRITTEN', 'WRITTEN', 'UNSURE', 'NO_CONVERSATION'):
        assert '`%s`' % o in readme, 'L14: the outcome rule names %s' % o
    present = [t for t in README_ABSENT if t in readme]
    assert not present, 'L14: README still has %s' % present
    with open(os.path.join(HERE, 'budget_golden.json')) as f:                    # OPX-10 (W26): section 7 = golden
        g = json.load(f)['D_baseline']
    run = [v for k, v in g.items() if k.startswith('A/')][0]
    na = [v for k, v in g.items() if k.startswith('NA-A/')][0]
    rows = {ln.split('|')[1].strip().split(' (')[0]: [c.strip() for c in ln.split('|')[2:5]]
            for ln in readme.split('\n') if ln.startswith('| a normal run') or ln.startswith('| a nonattempt')}
    assert run['drive_calls'] == 15 + 3 * run.get('png_parts', 0), run
    assert rows.get('a normal run') == [str(run['helper_commands']), '15 + 3p', str(run['saved_results'])] and \
        rows.get('a nonattempt') == [str(na['helper_commands']), str(na['drive_calls']), str(na['saved_results'])], \
        ('L14: README section 7 differs from tests/budget_golden.json', rows, run, na)
    rest = json.load(open(os.path.join(HERE, 'budget_golden.json')))['restore']           # GAP-7: the restore rows
    lead = {'hint': '| a restore after a reset, with your notes', 'commit': '| a restore with only the commit line',
            'none': '| a restore without your notes (step 0), measured'}
    for k, pre in lead.items():
        row = [ln for ln in readme.split('\n') if ln.startswith(pre)]
        want = [str(rest[k][c]) for c in ('helper_commands', 'drive_calls', 'saved_results')]
        assert len(row) == 1 and [c.strip() for c in row[0].split('|')[2:5]] == want, ('L14 restore', k, row, want)


def t_l15_every_guard_has_a_direct_test():
    """L15 (D11a): every fold TABLE row, every core/session.py function with a guard site and every glue function of
    the generated guard set has a GUARD_TESTS key with at least one test, and every listed test exists."""
    import mutants
    import test_core_table as TC
    from cpsvm2.core import fold as F
    keys = {r.id for r in F.TABLE} | {m['fn'] for m in mutants.guard_mutants({'cpsvm2/core/session.py': None})} | {
        fn for fns in mutants.GLUE_TARGETS.values() for fn in fns}
    missing = sorted(keys - set(TC.GUARD_TESTS))
    assert not missing, 'L15: no direct test for %s' % missing
    names = set()
    for n in ('test_core_table', 'test_core_more', 'test_vio', 'test_codes', 'test_v1_regressions', 'test_maint'):
        mod = __import__(n)
        names |= {getattr(f, '__name__', '') for f in getattr(mod, 'TESTS', [])} | {
            f.__name__ for f in getattr(mod, 'DIRECT', [])}
    bad = sorted({t for v in TC.GUARD_TESTS.values() for t in v} - names)
    assert not bad and all(TC.GUARD_TESTS[k] for k in keys), 'L15: unknown tests %s' % bad


def t_only_unknown_name_exits_2():
    """T11 (W27): run_tests.py --only with a name that is no suite, test, scenario, special, CONFIGS key or group exits
    2 and lists it; a known name of each kind is accepted."""
    import subprocess
    import tempfile
    d = tempfile.mkdtemp(prefix='only_')
    p = subprocess.run([sys.executable, '-I', '-B', os.path.join(HERE, 'run_tests.py'), '--work', d, '--only',
                        'test_core_props,no_such_test_name'], capture_output=True, text=True, timeout=600)
    assert p.returncode == 2 and 'no_such_test_name' in p.stdout and 'test_core_props' not in p.stdout.split(
        'names:')[-1], (p.returncode, p.stdout[-300:])
    import run_tests
    known = run_tests.known_names()
    for n in ('test_core_props', 'test_t1_continued_v_other_outcomes_t48', 'D_baseline', 'D', 'nonroot',
              'test_foreground_died_same_boot_stops', 't_d4_parse_raw_rules'):
        assert n in known, n


TESTS = [t_l1_codes_registered_and_tested, t_l2_import_rule_and_core_without_io, t_l2_only_cli_and_worker_import_both,
         t_l3_reuse_manifest, t_l4_core_line_coverage, t_l5_grammar_rejects, t_l6_readme_examples_refused,
         t_l7_no_or_in_exit_code_assertions, t_l8_pinned_shas, t_l9_print_rules, t_l10_unused_reused,
         t_l11_no_detached_process, t_l13_launcher_ignores_bytecode, t_l14_readme_rules,
         t_l15_every_guard_has_a_direct_test, t_only_unknown_name_exits_2]


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
