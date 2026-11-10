"""The single test entry point (§14): python3 -I -B deploy/vm2/tests/run_tests.py --work /abs/NEW_DIR [--jobs 4]
[--only NAMES] [--mutants]. NAMES is a comma list of suite names, test names or reset scenario names. Runs the core
tests (§14.1), the reuse check, the vio and maintainer tests, the probe tests, the v1 regressions (§14.4), the reset
enumeration with the real runner v4 (§14.3), then the lints (§14.6; L1 needs every other suite of the same run).
Writes <work>/TEST_RESULTS.json (cps.vm2-tests.v1). --mutants runs the mutation set instead (tests/mutants.py, §14.7)
and writes <work>/MUTANTS_RESULTS.json.
Exit 0 all passed (every mutant killed), 1 a failure, 2 usage or preflight (PREFLIGHT_FREE_SPACE: under 1 GiB free in
the work folder's file system, §14.8, TST-10)."""
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
MIN_FREE = 1 << 30
SUITES = ('test_core_table', 'test_core_props', 'test_core_more', 'test_reuse', 'test_vio', 'test_maint',
          'test_probe_p5', 'test_codes', 'test_v1_regressions', 'test_resets', 'test_lints')


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


def test_names(name, mod):
    """The test names a suite answers to in --only."""
    if name == 'test_resets':
        return {s['name'] for s in mod.scenarios()}
    if name == 'test_v1_regressions':
        return {f.__name__ for f in mod.DIRECT} | set(mod.DELEGATE)
    return {getattr(f, '__name__', '') for f in getattr(mod, 'TESTS', [])}


def run_suite(name, mod, only, work, jobs):
    wd = os.path.join(work, name)
    os.makedirs(wd, exist_ok=True)
    if name == 'test_core_props':
        return mod.run(jobs)
    if name in ('test_core_table', 'test_reuse', 'test_core_more'):
        return mod.run(only)
    if name == 'test_resets':
        return mod.run(only, wd, jobs)
    return mod.run(only, wd)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--only', default='')
    ap.add_argument('--mutants', action='store_true')
    a = ap.parse_args(argv)
    if not os.path.isabs(a.work) or a.jobs < 1:
        print('usage: --work must be absolute, --jobs at least 1')
        return 2
    os.makedirs(a.work, exist_ok=True)
    free = shutil.disk_usage(a.work).free
    if free < MIN_FREE:
        print('REFUSED PREFLIGHT_FREE_SPACE free=%d need=%d' % (free, MIN_FREE))
        return 2
    if a.mutants:
        import mutants
        return mutants.main(a.work, a.jobs, [x for x in a.only.split(',') if x])
    only = [x for x in a.only.split(',') if x]
    os.environ['CPSVM2_SEEN_DIR'] = os.path.join(a.work, 'seen')
    os.environ['CPSVM2_SEEN_FULL'] = '0' if only else '1'
    import seen
    seen.install()
    results, t0 = [], time.time()
    for name in SUITES:
        mod = __import__(name)
        if only and name not in only:
            mine = [x for x in only if x in test_names(name, mod)]
            if not mine:
                continue
            sel = mine
        else:
            sel = None
        t = time.time()
        r = run_suite(name, mod, sel, a.work, a.jobs)
        seen.dump()
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
           'seconds': round(time.time() - t0, 1), 'free_bytes_at_start': free, 'jobs': a.jobs, 'only': only,
           'helper_tree_sha256': tree_sha(), 'runner_sha256': runner_sha}
    with open(os.path.join(a.work, 'TEST_RESULTS.json'), 'w') as f:
        json.dump(doc, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({k: doc[k] for k in ('tests', 'passed', 'seconds')}))
    for x in doc['failed']:
        print('FAILED', x['suite'], x['tests'])
    return 0 if not doc['failed'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
