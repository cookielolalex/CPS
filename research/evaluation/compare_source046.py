"""Case-parameterized entry point for the frozen 043 source comparator.

evaluate() and check_interface() are imported unchanged from compare_source043.py, pinned by
SHA-256. Only the CLI release checks are generalized: the release must name the expectations'
own case_id (043's main() hard-coded 1140908). No fuzzy matching, recalculation, target
reading, row deletion or post-output alternatives are added.
"""
import argparse, datetime, hashlib, importlib.util, json, sys
from pathlib import Path

FROZEN = Path(__file__).with_name('compare_source043.py')
FROZEN_SHA256 = '1ececf30b034495bff049a629a15ccfa430f76a769d8f651d122be00aa069cb1'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_frozen():
    if sha(FROZEN) != FROZEN_SHA256:
        raise SystemExit('FROZEN_COMPARATOR_CHANGED')
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('compare_source043_frozen', FROZEN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--expectations', required=True); p.add_argument('--expectations-sha', required=True)
    p.add_argument('--carrier', required=True); p.add_argument('--carrier-sha', required=True)
    p.add_argument('--release', required=True); p.add_argument('--release-sha', required=True)
    p.add_argument('--run', required=True); p.add_argument('--output', required=True)
    a = p.parse_args()
    m = load_frozen()
    assert sha(a.expectations) == a.expectations_sha and sha(a.release) == a.release_sha
    expected = m.load(a.expectations)
    assert expected['status'] == 'FROZEN_BEFORE_MODEL_INVOCATION'
    assert expected['case_id'] == expected['carrier_contract']['case_id']
    release = m.load(a.release)
    assert release['both_outcomes_frozen'] is True and expected['case_id'] in release['case_ids'] and a.run in release['allowed_runs']
    assert release['reserved_answers_opened'] is False
    dt = datetime.datetime.fromisoformat(release['generated_access_released_utc'].replace('Z', '+00:00'))
    assert dt.utcoffset() == datetime.timedelta(0)
    frozen = Path(release['generated_output_freeze_path'])
    assert sha(frozen) == release['generated_output_freeze_sha256']
    pins = m.load(frozen)['pins']
    hits = [x for x in pins if Path(x['path']).resolve() == Path(a.carrier).resolve()]
    assert len(hits) == 1 and hits[0]['sha256'] == a.carrier_sha and sha(a.carrier) == a.carrier_sha
    carrier = m.load(a.carrier)
    m.check_interface(expected, carrier)
    result = m.evaluate(expected, carrier)
    result['bindings'] = {'expectations_sha256': a.expectations_sha, 'carrier_sha256': a.carrier_sha,
                          'release_sha256': a.release_sha, 'run': a.run, 'evaluator_sha256': sha(__file__),
                          'frozen_comparator_sha256': FROZEN_SHA256}
    with Path(a.output).open('x', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'run': a.run, 'case_id': expected['case_id'],
                      'core': result['metrics']['overall']['modes']['canonical']['core'],
                      'gates': result['numeric_99_percent_gates']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
