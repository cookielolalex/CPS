"""Prepare one bounded generator run directory: exact package + exact contract packet only.
Usage: python3 -I -B prepare_run.py --package DIR --packet DIR --run NEWDIR --case ID --reader A|B
"""
import argparse, hashlib, json, shutil, stat
from datetime import datetime, timezone
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    for k in ('package', 'packet', 'run', 'case', 'reader'):
        ap.add_argument('--' + k, required=True)
    a = ap.parse_args()
    run = Path(a.run)
    run.mkdir(parents=True, exist_ok=False)
    inp = run / 'input'
    shutil.copytree(a.package, inp / 'package', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (inp / 'packet').mkdir(parents=True)
    pk = Path(a.packet)
    members = ['SOURCE_INVENTORY.json'] + sorted(p.name for p in pk.glob('view_*.png'))
    for name in members:
        shutil.copy2(pk / name, inp / 'packet' / name)
    (run / 'output').mkdir()
    pins = [{'path': p.relative_to(run).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
            for p in sorted(inp.rglob('*')) if p.is_file()]
    for p in inp.rglob('*'):
        if p.is_file():
            p.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    rec = {'schema': 'cps.bounded-run-inputs.v1', 'case_id': a.case, 'reader': a.reader,
           'prepared_utc': datetime.now(timezone.utc).isoformat(), 'inputs': pins,
           'package_manifest_sha256': sha(inp / 'package' / 'PACKAGE_MANIFEST.json'),
           'inventory_sha256': sha(inp / 'packet' / 'SOURCE_INVENTORY.json'),
           'excluded': 'historical worksheets, prior outputs, evaluator expectations, naming study, other bundle members'}
    (run / 'RUN_INPUT_PINS.json').write_text(json.dumps(rec, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'run': str(run), 'inputs': len(pins), 'inventory_sha256': rec['inventory_sha256'],
                      'package_manifest_sha256': rec['package_manifest_sha256']}))


if __name__ == '__main__':
    main()
