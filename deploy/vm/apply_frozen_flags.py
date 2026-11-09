#!/usr/bin/env python3
"""Apply the ALL_FROZEN.json v2 run flags to an O31 gate manifest before the frozen aggregator runs (G3 candidate, r4 F4).

STATUS: candidate, NOT ADMITTED. Until a reviewed and admitted version of this check (or an admitted aggregator change
that does the same) exists, qualification scoring is blocked: the frozen O31 aggregators
(research/evaluation/aggregate_qualification.py and aggregate_qualification050.py) do not read ALL_FROZEN.json, so
without this check a run that failed by reset would be scored like any other run.

What it checks (it never scores and never changes a file it reads):
  O44 / O46: a run flagged RESET_DIVERGED or AI_OUTPUT_LOST is a failed run. Its (case, reader) entry in the gate
             manifest must be the comparison of the empty carrier (--empty-carrier-sha, the carrier a nonattempt is
             evaluated as: `items: []`), so the frozen aggregator counts it in that reader's denominators and it scores 0;
  nonattempts: the same empty carrier;
  every other run: its entry must not be the empty carrier;
  FROZEN_UNVERIFIED: the frozen folder failed verify-frozen; the run is not scored until the owner rules on it
             (--owner-rulings {"schema": "cps.frozen-flags-owner-rulings.v1", "rulings": {"<job_dir>": "score"|"fail"}}):
             "fail" means the empty carrier, "score" means a normal entry;
  VISUAL_QA_FAILED_BY_RESET (O46, design E4): failed visual QA. It does not change the historical-match entry; it is
             listed in the output for the visual-QA obligation;
  ALL_FROZEN.json's runs_failed_by_reset and runs_visual_qa_failed_by_reset lists must equal what the flags say;
  every (case, reader) the manifest scores must have exactly one run in ALL_FROZEN.json (the newest run of a case and
             reader is the one scored; an earlier run of the same case and reader that failed fails the pair).

Usage:
  python3 -I -B deploy/vm/apply_frozen_flags.py --all-frozen ALL_FROZEN.json --manifest GATE_MANIFEST.json \\
      --empty-carrier-sha HEX [--owner-rulings RULINGS.json] --out FLAGS_CHECK.json
Exit 0: consistent (the frozen aggregator may run on the manifest unchanged); 1: inconsistent (OUT names every
problem); 2: usage or unreadable input. OUT must not exist. Prints only codes, counts, case ids and readers.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA = 'cps.frozen-flags-check.v1'
FAILED = ('RESET_DIVERGED', 'AI_OUTPUT_LOST')
VISUAL = 'VISUAL_QA_FAILED_BY_RESET'
UNVERIFIED = 'FROZEN_UNVERIFIED'
QUAL_TAGS = {'A': 'A', 'B': 'B', 'A-restart1': 'A', 'B-restart1': 'B', 'NA-A': 'A', 'NA-B': 'B'}
HEX64 = re.compile(r'[0-9a-f]{64}')


def strict(raw):
    def hook(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValueError('duplicate key ' + k)
            d[k] = v
        return d
    return json.loads(raw, object_pairs_hook=hook)


def load(path, what):
    try:
        return strict(Path(path).read_bytes().decode('utf-8'))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        raise SystemExit(f'{what}: {type(e).__name__}')


def check(af, man, empty, rulings):
    problems, visual, scored = [], [], {}
    if not isinstance(af, dict) or af.get('schema') != 'cps.all-frozen.v2' or not isinstance(af.get('runs'), list):
        return [{'code': 'ALL_FROZEN_SCHEMA'}], [], {}
    readers = (man or {}).get('readers') if isinstance(man, dict) else None
    if not isinstance(readers, dict) or set(readers) != {'A', 'B'} or not all(isinstance(v, dict) for v in readers.values()):
        return [{'code': 'MANIFEST_READERS'}], [], {}
    groups = {}
    for r in af['runs']:
        if not isinstance(r, dict) or r.get('tag') not in QUAL_TAGS or not isinstance(r.get('flags'), list):
            problems.append({'code': 'ALL_FROZEN_RUN_INVALID', 'job_dir': (r or {}).get('job_dir') if isinstance(r, dict) else None})
            continue
        reader = QUAL_TAGS[r['tag']]
        if r.get('reader') not in (None, reader):
            problems.append({'code': 'ALL_FROZEN_RUN_INVALID', 'job_dir': r.get('job_dir'), 'why': 'reader'})
            continue
        groups.setdefault((r.get('case_id'), reader), []).append(r)
    want_failed = sorted(r['job_dir'] for rs in groups.values() for r in rs if set(FAILED) & set(r['flags']))
    want_visual = sorted(r['job_dir'] for rs in groups.values() for r in rs if VISUAL in r['flags'])
    if sorted(af.get('runs_failed_by_reset') or []) != want_failed:
        problems.append({'code': 'ALL_FROZEN_FAILED_LIST_INCONSISTENT'})
    if sorted(af.get('runs_visual_qa_failed_by_reset') or []) != want_visual:
        problems.append({'code': 'ALL_FROZEN_VISUAL_LIST_INCONSISTENT'})
    for reader, cases in readers.items():
        for case, ent in cases.items():
            rs = groups.get((case, reader), [])
            if not rs:
                problems.append({'code': 'RUN_MISSING', 'case_id': case, 'reader': reader})
                continue
            carrier = ent.get('carrier_sha256') if isinstance(ent, dict) else None
            if not isinstance(carrier, str) or not HEX64.fullmatch(carrier):
                problems.append({'code': 'MANIFEST_ENTRY_INVALID', 'case_id': case, 'reader': reader})
                continue
            flags = set(f for r in rs for f in r['flags'])
            nonattempt = any(r.get('kind') == 'nonattempt' for r in rs) and all(r.get('kind') == 'nonattempt' for r in rs)
            must_empty = bool(set(FAILED) & flags) or nonattempt
            why = 'failed run' if set(FAILED) & flags else ('nonattempt' if nonattempt else 'run')
            if UNVERIFIED in flags:
                ru = (rulings or {}).get('rulings', {}) if isinstance(rulings, dict) else {}
                decided = [ru.get(r['job_dir']) for r in rs if UNVERIFIED in r['flags']]
                if any(x not in ('score', 'fail') for x in decided):
                    problems.append({'code': 'OWNER_RULING_REQUIRED', 'case_id': case, 'reader': reader})
                    continue
                if 'fail' in decided:
                    must_empty, why = True, 'owner ruled the unverified run failed'
            if must_empty and carrier != empty:
                problems.append({'code': 'FLAG_NOT_APPLIED', 'case_id': case, 'reader': reader, 'why': why})
            elif not must_empty and carrier == empty:
                problems.append({'code': 'EMPTY_CARRIER_FOR_SCORED_RUN', 'case_id': case, 'reader': reader})
            scored[f'{reader}/{case}'] = {'failed_by_reset': bool(set(FAILED) & flags), 'nonattempt': nonattempt,
                                          'empty_carrier': carrier == empty}
            if VISUAL in flags:
                visual.append({'case_id': case, 'reader': reader})
    return problems, visual, scored


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--all-frozen', required=True)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--empty-carrier-sha', required=True)
    ap.add_argument('--owner-rulings')
    ap.add_argument('--out', required=True)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if not HEX64.fullmatch(a.empty_carrier_sha):
        print('usage: --empty-carrier-sha must be 64 lowercase hex digits', file=sys.stderr)
        return 2
    out = Path(a.out)
    if out.exists():
        print('usage: --out exists', file=sys.stderr)
        return 2
    try:
        af = load(a.all_frozen, 'ALL_FROZEN.json')
        man = load(a.manifest, 'manifest')
        rulings = load(a.owner_rulings, 'owner rulings') if a.owner_rulings else None
    except SystemExit as e:
        print(f'unreadable input: {e}', file=sys.stderr)
        return 2
    if rulings is not None and (not isinstance(rulings, dict) or rulings.get('schema') != 'cps.frozen-flags-owner-rulings.v1'
                                or not isinstance(rulings.get('rulings'), dict)):
        print('unreadable input: owner rulings schema', file=sys.stderr)
        return 2
    problems, visual, scored = check(af, man, a.empty_carrier_sha, rulings)
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    rep = {'schema': SCHEMA, 'status': 'CANDIDATE_NOT_ADMITTED', 'consistent': not problems,
           'inputs': {'all_frozen_sha256': sha(a.all_frozen), 'manifest_sha256': sha(a.manifest),
                      'owner_rulings_sha256': sha(a.owner_rulings) if a.owner_rulings else None,
                      'empty_carrier_sha256': a.empty_carrier_sha, 'tool_sha256': sha(__file__)},
           'problems': problems, 'visual_qa_failed_by_reset': visual, 'scored': scored}
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'consistent': not problems, 'problems': len(problems), 'codes': sorted({p['code'] for p in problems}),
                      'visual_qa_failed_by_reset': len(visual)}))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
