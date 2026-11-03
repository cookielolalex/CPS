"""Create the generated-output pin file and release record consumed by compare_source046.py.

Run only after every run of the case has a frozen outcome. Usage:
  python3 -I -B make_release.py --case ID --carrier A=PATH --carrier B=PATH --out-dir NEWDIR
"""
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--carrier', action='append', default=[], help='RUN=PATH (only runs whose response was carried)')
    ap.add_argument('--not-carried', action='append', default=[], help='RUN=REASON for frozen outcomes without a carrier')
    ap.add_argument('--out-dir', required=True)
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    pins = []
    for spec in a.carrier:
        run, path = spec.split('=', 1)
        p = Path(path).resolve()
        pins.append({'run': run, 'path': str(p), 'sha256': sha(p)})
    nc = [dict(zip(('run', 'reason'), s.split('=', 1))) for s in a.not_carried]
    freeze = {'schema': 'cps.generated-output-freeze.v2', 'case_id': a.case, 'pins': pins, 'not_carried': nc,
              'frozen_utc': datetime.now(timezone.utc).isoformat()}
    fp = out / 'GENERATED_OUTPUT_FREEZE.json'
    fp.write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    release = {'schema': 'cps.evaluation-release.v2', 'case_ids': [a.case], 'both_outcomes_frozen': True,
               'allowed_runs': [p['run'] for p in pins], 'reserved_answers_opened': False,
               'generated_access_released_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
               'generated_output_freeze_path': str(fp.resolve()), 'generated_output_freeze_sha256': sha(fp)}
    rp = out / 'RELEASE.json'
    rp.write_text(json.dumps(release, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'release': str(rp), 'release_sha256': sha(rp), 'pins': len(pins), 'not_carried': len(nc)}))


if __name__ == '__main__':
    main()
