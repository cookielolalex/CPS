"""Tests of deploy/vm2/probe_p5.py (spec §12.5; §14.4 SAFE-03, OP-05). Real processes: start spawns a real detached
worker; check runs as a child of this process (same call), of a shell in this session (same session), or of a shell in
a new session (a different call). The boot id comes from a file named by CPS_VM_BOOT_ID_PATH. Entry: run(only, work)."""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(os.path.dirname(HERE), 'probe_p5.py')
WORK = None
BOOT = '0123abcd-0000-4000-8000-00000000beef'


def env(d):
    bp = os.path.join(d, 'boot_id')
    if not os.path.exists(bp):
        with open(bp, 'w') as f:
            f.write(BOOT + '\n')
    return dict(os.environ, CPS_VM_BOOT_ID_PATH=bp)


def probe(d, *args, how='child'):
    """Run probe_p5.py: 'child' (same parent and session as start from this process), 'shell' (a shell child of
    this process: another parent, same session), 'new' (a shell in a new session: another call)."""
    pd = os.path.join(d, 'probe')
    cmd = [sys.executable, '-I', '-B', PROBE] + list(args) + ['--dir', pd]
    if how == 'child':
        p = subprocess.run(cmd, env=env(d), capture_output=True, text=True, timeout=60)
    else:
        p = subprocess.run(['sh', '-c', '"$@"', 'sh'] + cmd, env=env(d), capture_output=True, text=True, timeout=60,
                           start_new_session=(how == 'new'))
    return p.returncode, p.stdout.strip()


def listing(d):
    pd = os.path.join(d, 'probe')
    return sorted(n for n in os.listdir(pd) if n not in ('HEARTBEAT.jsonl', 'DONE.json'))


def wait_done(d, limit=30):
    t = time.time() + limit
    while time.time() < t:
        if os.path.exists(os.path.join(d, 'probe', 'DONE.json')):
            return True
        time.sleep(0.2)
    return False


def report(out):
    with open(out.splitlines()[-1]) as f:
        return json.load(f)


def test_safe03_probe_p5_same_call_check_refused():
    d = tempfile.mkdtemp(dir=WORK)
    rc, out = probe(d, 'start', '--seconds', '3', '--min-gap', '0')
    assert rc == 0 and out.startswith('NEXT: end this tool call now'), out
    before = listing(d)
    rc, out = probe(d, 'check', '--min-gap', '0')
    assert (rc, out) == (4, 'REFUSED SAME_CALL'), (rc, out)
    assert listing(d) == before and not any(n.startswith('PROBE_P5_') for n in before)
    assert wait_done(d)


def test_op05_probe_same_session_refused():
    d = tempfile.mkdtemp(dir=WORK)
    probe(d, 'start', '--seconds', '2', '--min-gap', '0')
    before = listing(d)
    rc, out = probe(d, 'check', '--min-gap', '0', how='shell')
    assert (rc, out) == (4, 'REFUSED SAME_CALL'), (rc, out)
    assert listing(d) == before
    assert wait_done(d)


def test_probe_too_early_other_boot_not_started():
    d = tempfile.mkdtemp(dir=WORK)
    rc, out = probe(d, 'check', how='new')
    assert (rc, out) == (4, 'REFUSED NOT_STARTED'), out
    probe(d, 'start', '--seconds', '2', '--min-gap', '0')
    rc, out = probe(d, 'check', how='new')
    assert (rc, out) == (4, 'REFUSED TOO_EARLY'), out
    with open(os.path.join(d, 'boot_id'), 'w') as f:
        f.write('99999999-0000-4000-8000-000000000000\n')
    rc, out = probe(d, 'check', '--min-gap', '0', how='new')
    assert (rc, out) == (4, 'REFUSED OTHER_BOOT'), out
    assert not any(n.startswith('PROBE_P5_') for n in listing(d))
    assert wait_done(d)


def test_probe_detached_worker_outlives_start():
    """The worker keeps writing after start exited; a check from another session reports it (FAIL: min-gap < 480)."""
    d = tempfile.mkdtemp(dir=WORK)
    rc, _ = probe(d, 'start', '--seconds', '4', '--min-gap', '0')
    assert rc == 0
    st = json.load(open(os.path.join(d, 'probe', 'START.json')))
    assert st['caller_ppid'] == os.getpid() and st['caller_sid'] == os.getsid(0) and st['start_exited_utc']
    time.sleep(3)
    rc, out = probe(d, 'check', '--min-gap', '2', how='new')
    assert rc == 0, out
    r = report(out)
    assert r['heartbeats'] >= 2 and r['worker_lived_after_start_exit_seconds'] >= 1 and r['verdict'] == 'FAIL', r
    assert r['worker_alive'] or r['done']
    assert wait_done(d)
    time.sleep(1.1)
    rc, out = probe(d, 'check', '--min-gap', '2', how='new')
    r = report(out)
    assert rc == 0 and r['done'] is True and r['heartbeats'] == 4, r
    assert os.path.basename(out).startswith('PROBE_P5_%s_' % BOOT[:8])


def _records(d, exited_ago, beats_until_ago, done=True):
    pd = os.path.join(d, 'probe')
    os.makedirs(pd)
    now = time.time()
    u = lambda t: time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t))  # noqa: E731
    st = {'schema': 'cps.vm2-probe-p5.v1', 'token': 't1', 'boot_id': BOOT, 'started_utc': u(now - exited_ago - 1),
          'seconds': 900, 'caller_ppid': 1, 'caller_sid': 1, 'caller_pgid': 1, 'start_pid': 2, 'worker_pid': 2 ** 22 + 7,
          'start_exited_utc': u(now - exited_ago)}
    with open(os.path.join(pd, 'START.json'), 'w') as f:
        json.dump(st, f)
    with open(os.path.join(pd, 'HEARTBEAT.jsonl'), 'w') as f:
        for i, t in enumerate(range(int(now - exited_ago), int(now - beats_until_ago) + 1, 10)):
            f.write(json.dumps({'utc': u(t), 'n': i + 1, 'token': 't1'}) + '\n')
        f.write(json.dumps({'utc': u(now), 'n': 0, 'token': 'another run'}) + '\n')
    if done:
        with open(os.path.join(pd, 'DONE.json'), 'w') as f:
            json.dump({'token': 't1'}, f)


def test_probe_verdict_pass_and_fail_from_records():
    d = tempfile.mkdtemp(dir=WORK)
    _records(d, 600, 1)
    rc, out = probe(d, 'check', how='new')
    r = report(out)
    assert rc == 0 and r['verdict'] == 'PASS' and r['done'] and not r['worker_alive'], r
    d = tempfile.mkdtemp(dir=WORK)
    _records(d, 600, 400)                                   # the worker stopped 200 s after start exited
    rc, out = probe(d, 'check', how='new')
    assert rc == 0 and report(out)['verdict'] == 'FAIL'
    d = tempfile.mkdtemp(dir=WORK)
    _records(d, 600, 1, done=False)                         # neither alive nor done
    rc, out = probe(d, 'check', how='new')
    assert rc == 0 and report(out)['verdict'] == 'FAIL'


def test_probe_start_refuses_alive_worker_and_hold_records():
    d = tempfile.mkdtemp(dir=WORK)
    probe(d, 'start', '--seconds', '3', '--min-gap', '0')
    rc, out = probe(d, 'start', '--seconds', '3', '--min-gap', '0', how='new')
    assert (rc, out) == (4, 'REFUSED WORKER_ALIVE'), out
    rc, out = probe(d, 'hold', '--seconds', '1')
    h = json.load(open(out))
    assert rc == 0 and h['seconds'] == 1 and h['completed_utc'] is not None
    assert os.path.basename(out).startswith('HOLD_1_')
    assert wait_done(d)


def test_maint10_probe_start_refuses_seconds_below_min_gap():
    """MAINT-10 (b) (W44): `start` refuses --seconds below --min-gap (a worker that ends before the check proves
    nothing) and writes nothing."""
    d = tempfile.mkdtemp(dir=WORK)
    rc, out = probe(d, 'start', '--seconds', '10', '--min-gap', '480')
    assert rc == 4 and 'REFUSED SECONDS_BELOW_MIN_GAP' in out, (rc, out)
    assert not os.path.exists(os.path.join(d, 'probe', 'START.json'))


def test_g8_dir_required_never_under_home():
    """Fix round G8 (W138): probe_p5.py has no default folder under HOME, which the Dot's standard route cannot write:
    without --dir it exits 2 (usage) and writes nothing; G-3 runs it with --dir under /tmp."""
    home = os.path.join(WORK, 'g8home')
    os.makedirs(home)
    p = subprocess.run([sys.executable, '-I', '-B', PROBE, 'hold', '--seconds', '0'], env=dict(env(WORK), HOME=home),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and '--dir' in p.stderr, (p.returncode, p.stdout, p.stderr)
    assert os.listdir(home) == [], os.listdir(home)


TESTS = [test_safe03_probe_p5_same_call_check_refused, test_op05_probe_same_session_refused,
         test_probe_too_early_other_boot_not_started, test_probe_detached_worker_outlives_start,
         test_probe_verdict_pass_and_fail_from_records, test_probe_start_refuses_alive_worker_and_hold_records,
         test_maint10_probe_start_refuses_seconds_below_min_gap, test_g8_dir_required_never_under_home]


def run(only=None, work=None):
    global WORK
    import shutil
    WORK = tempfile.mkdtemp(dir=work, prefix='probe_p5_')
    passed, failed = 0, []
    for fn in TESTS:
        if only and fn.__name__ not in only:
            continue
        try:
            fn()
            passed += 1
        except Exception as x:                                            # noqa: BLE001 - the report names it
            failed.append({'test': fn.__name__, 'error': '%s: %s' % (type(x).__name__, str(x)[:600])})
    shutil.rmtree(WORK, ignore_errors=True)
    return {'name': 'test_probe_p5', 'tests': passed + len(failed), 'passed': passed,
            'failed': [f['test'] for f in failed], 'detail': failed, 'counts': {}}


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    wk = [a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--work=')]
    r = run(args or None, wk[0] if wk else None)
    print(json.dumps(r, indent=1))
    sys.exit(0 if not r['failed'] else 1)
