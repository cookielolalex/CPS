"""Freeze a generator run's actual outcome (including failure/nonattempt) before any evaluation.
Usage: python3 -I -B freeze_outputs.py --run DIR --agent-report FILE --audit FILE --started ISO --ended ISO
"""
import argparse, hashlib, json, shutil, stat
from datetime import datetime, timezone
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    for k in ('run', 'agent_report', 'audit', 'started', 'ended'):
        ap.add_argument('--' + k.replace('_', '-'), dest=k, required=True)
    a = ap.parse_args()
    run = Path(a.run)
    fz = run / 'frozen'
    fz.mkdir(exist_ok=False)
    out = run / 'output' / 'response.json'
    rec = {'schema': 'cps.generator-outcome-freeze.v1', 'frozen_utc': datetime.now(timezone.utc).isoformat(),
           'invocation_started_utc': a.started, 'invocation_ended_utc': a.ended,
           'input_pins_sha256': sha(run / 'RUN_INPUT_PINS.json')}
    if out.is_file():
        shutil.copy2(out, fz / 'response.json')
        rec['outcome'] = 'RESPONSE_RETURNED'
        rec['response'] = {'path': 'frozen/response.json', 'bytes': out.stat().st_size, 'sha256': sha(out)}
    else:
        rec['outcome'] = 'NO_RESPONSE_FILE'
    for src, name in ((a.agent_report, 'AGENT_FINAL_REPORT.txt'), (a.audit, 'TRANSCRIPT_AUDIT.json')):
        shutil.copy2(src, fz / name)
        rec[name] = sha(fz / name)
    rec['scored_output_repair_permitted'] = False
    rec['retry_permitted'] = False
    (fz / 'FREEZE.json').write_text(json.dumps(rec, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for p in fz.iterdir():
        p.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    print(json.dumps({'outcome': rec['outcome'], 'response_sha256': rec.get('response', {}).get('sha256'),
                      'freeze_sha256': sha(fz / 'FREEZE.json')}))


if __name__ == '__main__':
    main()
