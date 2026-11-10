"""The single test entry point (§14): python3 -I -B deploy/vm2/tests/run_tests.py --work /abs/NEW_DIR [--jobs 4]
[--only SUITES]. Runs the core tests (§14.1), the reuse check, the vio and maintainer tests, the probe tests, the
lints and the reset enumeration with the real runner v4 (§14.3). Writes <work>/TEST_RESULTS.json (cps.vm2-tests.v1).
Exit 0 all passed, 1 a failure, 2 usage or preflight (less than 1.5 GiB free: the reset worlds need room)."""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
VM2 = os.path.dirname(HERE)
RUNNER = os.path.join(os.path.dirname(VM2), 'run', 'cps_job.py')
MIN_FREE = 3 << 29
SUITES = ('test_core_table', 'test_core_props', 'test_reuse', 'test_vio', 'test_maint', 'test_probe_p5', 'test_lints',
          'test_resets')


def tree_sha():
    """§3.4 helper tree sha: every regular file under deploy/vm2/ except tests/ (and bytecode caches)."""
    rows = []
    for dp, dns, fns in os.walk(VM2):
        dns[:] = sorted(d for d in dns if d not in ('tests', '__pycache__'))
        for n in sorted(fns):
            p = os.path.join(dp, n)
            with open(p, 'rb') as f:
                rows.append([os.path.relpath(p, VM2), hashlib.sha256(f.read()).hexdigest()])
    return hashlib.sha256(json.dumps(sorted(rows), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--only', default='')
    a = ap.parse_args(argv)
    if not os.path.isabs(a.work):
        print('usage: --work must be absolute')
        return 2
    os.makedirs(a.work, exist_ok=True)
    free = shutil.disk_usage(a.work).free
    if free < MIN_FREE:
        print('REFUSED PREFLIGHT_FREE_SPACE free=%d' % free)
        return 2
    only = [x for x in a.only.split(',') if x]
    results, t0 = [], time.time()
    for name in SUITES:
        if only and name not in only:
            continue
        t = time.time()
        mod = __import__(name)
        wd = os.path.join(a.work, name)
        os.makedirs(wd, exist_ok=True)
        if name == 'test_core_props':
            r = mod.run(a.jobs)
        elif name in ('test_core_table', 'test_reuse'):
            r = mod.run()
        elif name == 'test_resets':
            r = mod.run(None, wd, a.jobs)
        else:
            r = mod.run(None, wd)
        r['seconds'] = round(time.time() - t, 1)
        results.append(r)
    runner_sha = None
    if os.path.exists(RUNNER):
        with open(RUNNER, 'rb') as f:
            runner_sha = hashlib.sha256(f.read()).hexdigest()
    doc = {'schema': 'cps.vm2-tests.v1', 'tests': sum(r['tests'] for r in results),
           'passed': sum(r['passed'] for r in results),
           'failed': [{'suite': r['name'], 'tests': r['failed'], 'detail': r['detail']} for r in results if r['failed']],
           'suites': [{k: r.get(k) for k in ('name', 'tests', 'passed', 'seconds', 'counts')} for r in results],
           'seconds': round(time.time() - t0, 1), 'free_bytes_at_start': free, 'helper_tree_sha256': tree_sha(),
           'runner_sha256': runner_sha}
    with open(os.path.join(a.work, 'TEST_RESULTS.json'), 'w') as f:
        json.dump(doc, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({k: doc[k] for k in ('tests', 'passed', 'seconds')}))
    for x in doc['failed']:
        print('FAILED', x['suite'], x['tests'])
    return 0 if not doc['failed'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
