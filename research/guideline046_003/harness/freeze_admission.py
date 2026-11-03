"""Freeze the exact candidate, route, evaluator, expectations, packets and invocation plan
before any 046b generation. Writes ADMISSION_046b.json (hash-only; no case content).
Usage: python3 -I -B freeze_admission.py --config ADMISSION_CONFIG.json --out ADMISSION_046b.json
The config lists label -> absolute path for every pinned file plus the plain-text plan fields.
"""
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text(encoding='utf-8'))
    pins = {}
    for label, path in cfg['files'].items():
        p = Path(path)
        pins[label] = {'file': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p)}
    for label, want in cfg.get('expected_sha256', {}).items():
        if pins[label]['sha256'] != want:
            raise SystemExit(f'PIN_MISMATCH:{label}')
    out = {'schema': 'cps.admission.046b.v1', 'frozen_utc': datetime.now(timezone.utc).isoformat(),
           'pins': pins, **cfg['plan']}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'pins': len(pins), 'admission_sha256': sha(a.out)}))


if __name__ == '__main__':
    main()
