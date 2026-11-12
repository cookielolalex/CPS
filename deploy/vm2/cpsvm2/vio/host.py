"""Host glue (spec §2.1, §2.2, §8.2, §8.3, §12.1): paths, the clock, the kit config and gates, the PASS."""
import datetime
import hashlib
import json
import os
import re
import subprocess

from .v1compat import HELPER_REPO, stop
from .v1reuse import current_boot_id, sha_bytes, sha_file, sjson

CONFIG_SCHEMA = 'cps.vm2-config.v1'
CONFIG_KEYS = {'schema': str, 'series': str, 'accepted_helper_tree_sha256': list, 'accepts_release_sha256': list,
               'selftest_expected_tests': int, 'clock_wait_max_seconds': int, 'foreground_hold_seconds': int,
               'stage_max_seconds': dict, 'max_upload_bytes': int, 'png_part_bytes': int, 'max_entry_bytes': int,
               'max_transcript_bytes': int, 'max_ai_output_bytes': int, 'conversation_re': str, 'transcript_ext': str,
               'drive_id_re': str, 'gates': dict, 'clear': (dict, type(None)), 'doc_samples': list,
               'tool_inventory_sha256': str}
GATE_VALUES = {'p1_vm_files': ('PASS', 'FAIL', 'OPEN'), 'p1_transcript_export': ('yes', 'no', 'OPEN'),
               'p1_conversation_list': ('yes', 'no', 'OPEN'), 'p1_end_after_reset': ('yes', 'no', 'OPEN'),
               'p2_exact_search': ('PASS', 'FAIL', 'OPEN'), 'p2_lag_seconds': int, 'p2_max_upload_bytes': int,
               'p2_tgz_kept': ('PASS', 'FAIL', 'OPEN'), 'p2_failed_upload_can_appear': ('yes', 'no', 'OPEN'),
               'p3_identity_stable': ('yes', 'no', 'OPEN'), 'p3_clock_tolerance_seconds': int,
               'p5_foreground_hold_seconds': int, 'p5_setup_seconds': int}
PLATFORM_UPLOAD_LIMIT = 104857600


def now():
    """The one clock (§2.1): UTC_S of this moment, rounded up to the second. Tests replace this function."""
    t = datetime.datetime.now(datetime.timezone.utc)
    if t.microsecond:
        t = t.replace(microsecond=0) + datetime.timedelta(seconds=1)
    return t.strftime('%Y-%m-%dT%H:%M:%SZ')


def utc14(s):
    return s.replace('-', '').replace(':', '')


class Paths:
    """v2 additions under BASE (§2.1)."""
    def __init__(self, lay):
        b = lay.base
        self.v2, self.journal, self.attest, self.deliver = b / 'outbox/v2', b / 'outbox/journal', b / 'attest', \
            b / 'deliver'
        self.state, self.pending, self.block, self.halt, self.work = (self.v2 / n for n in (
            'STATE.json', 'PENDING.json', 'BLOCK.json', 'HALT.json', 'RESTORE_WORK.json'))
        self.hint, self.foreground = self.v2 / 'HINT.json', self.v2 / 'FOREGROUND.json'


class Ctx2:
    """What the reused segments read (§1.5): lay, cfg, V."""
    def __init__(self, lay, cfg):
        self.lay, self.cfg, self.V = lay, cfg, str(lay.vm)


def layout_paths_ok(lay):
    """§2.1: every helper-chosen path is ASCII without whitespace (else STOP LAYOUT_PATH)."""
    for p in (lay.base, lay.tools, lay.home or ''):
        s = str(p)
        if not s.isascii() or any(c.isspace() or c in '\'"\\$`' for c in s):
            stop('LAYOUT_PATH', 'BASE, TOOLS and HOME must be ASCII without whitespace')


def helper_tree_sha256():
    """§3.4: sha(cjson(sorted([relpath, sha_file]) of every regular file under deploy/vm2/ except tests/))."""
    root = HELPER_REPO / 'deploy' / 'vm2'
    rows = []
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d not in ('tests', '__pycache__'))
        for n in sorted(fns):
            p = os.path.join(dp, n)
            rows.append([os.path.relpath(p, root).replace(os.sep, '/'), sha_file(p)])
    return hashlib.sha256(json.dumps(sorted(rows), sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode('ascii')).hexdigest()


def repo_commit(lay):
    p = subprocess.run(['git', '-C', str(lay.repo), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=60)
    s = (p.stdout or '').strip()
    return s if p.returncode == 0 and re.fullmatch(r'[0-9a-f]{40}', s) else None


def load_config(raw, release, check_patterns, cap, stage_keys):
    """§2.2 and §X.2: the kit config with exact keys and types, gate values and the series pin, or CONFIG_INVALID."""
    try:
        c = sjson(raw)
    except (ValueError, UnicodeDecodeError):
        stop('CONFIG_INVALID', 'not strict JSON')
    if not isinstance(c, dict) or set(c) != set(CONFIG_KEYS):
        stop('CONFIG_INVALID', 'keys', detail={'keys': 'mismatch'})
    for k, t in CONFIG_KEYS.items():
        if not isinstance(c[k], t) or (t is int and isinstance(c[k], bool)):
            stop('CONFIG_INVALID', k)
    if c['schema'] != CONFIG_SCHEMA or not re.fullmatch(r'Q[1-9]|E[1-9]|D[1-9][0-9]?', c['series'], re.ASCII):
        stop('CONFIG_INVALID', 'schema/series')
    status = (release or {}).get('status')
    want = 'RELEASED_FOR_USE' if c['series'][0] == 'E' else 'RELEASED_FOR_QUALIFICATION'
    if status in ('RELEASED_FOR_USE', 'RELEASED_FOR_QUALIFICATION') and status != want:
        stop('CONFIG_INVALID', 'series')
    if c['series'][0] in 'QD' and status == want and (release.get('vm_helper') or {}).get('series') != c['series']:
        stop('CONFIG_INVALID', 'series')
    g = c['gates']
    if set(g) != set(GATE_VALUES):
        stop('CONFIG_INVALID', 'gates')
    for k, v in GATE_VALUES.items():
        ok = (g[k] is None or (isinstance(g[k], int) and not isinstance(g[k], bool))) if v is int else g[k] in v
        if not ok:
            stop('CONFIG_INVALID', 'gates')
    if not re.fullmatch(r'[a-z0-9]{1,10}', c['transcript_ext']) or any(
            not re.fullmatch(r'[0-9a-f]{64}', x or '') for x in c['accepted_helper_tree_sha256']
            + c['accepts_release_sha256'] + [c['tool_inventory_sha256']]) \
            or not all(isinstance(x, str) for x in c['doc_samples']):
        stop('CONFIG_INVALID', 'values')
    for rx in (c['conversation_re'], c['drive_id_re']):
        try:
            re.compile(rx)
        except re.error:
            stop('CONFIG_INVALID', 'regex')
    if check_patterns(c['conversation_re'], c['doc_samples']):
        stop('CONFIG_INVALID', 'conversation_re')
    if c['clear'] is not None and set(c['clear']) != {'series', 'seq', 'code'}:
        stop('CONFIG_INVALID', 'values')
    sm = c['stage_max_seconds']
    if set(sm) != set(stage_keys) or any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in sm.values()):
        stop('CONFIG_INVALID', 'stage_max_seconds')
    if not 1 <= c['max_upload_bytes'] <= cap or not 1000000 <= c['png_part_bytes'] <= c['max_upload_bytes'] \
            or c['max_entry_bytes'] > c['max_upload_bytes'] or c['foreground_hold_seconds'] < 1 \
            or c['max_ai_output_bytes'] + c['max_transcript_bytes'] + 1000000 > c['max_entry_bytes']:
        stop('CONFIG_INVALID', 'sizes')
    return c


def gates_problem(cfg, mode, cap):
    """§12.1 (§X.12.1) on every command: None or the sorted open gates and failed budget keys."""
    if mode == 'setup':
        return None
    g, bad = cfg['gates'], []
    bad += [k for k, v in g.items() if v in ('OPEN', None)]
    bad += [k for k, want in (('p1_vm_files', 'PASS'), ('p2_exact_search', 'PASS'), ('p2_tgz_kept', 'PASS'),
                              ('p1_conversation_list', 'yes')) if g.get(k) != want]
    hold, fh = g.get('p5_foreground_hold_seconds') or 0, cfg['foreground_hold_seconds']
    if fh > hold:
        bad.append('p5_foreground_hold_seconds')
    if (g.get('p5_setup_seconds') or 0) + 60 > fh:
        bad.append('p5_setup_seconds')
    bad += ['stage_max_seconds.' + k for k, v in sorted(cfg['stage_max_seconds'].items()) if v + 60 > fh]
    mx = min(cap, g.get('p2_max_upload_bytes') or 0, PLATFORM_UPLOAD_LIMIT)
    if cfg['max_upload_bytes'] > mx:
        bad.append('p2_max_upload_bytes')
    if cfg['png_part_bytes'] > cfg['max_upload_bytes'] or cfg['max_entry_bytes'] > cfg['max_upload_bytes']:
        bad.append('max_upload_bytes')
    return sorted(set(bad)) or None


def pass_doc(fp_sha, full, commit, results_name, res_raw, s, run):
    """The FINGERPRINT_PASS content (v1 cmd_fingerprint_pass, lines 5951-6012)."""
    return {'schema': 'cps.vm-fingerprint-pass.v1', 'helper': {'version': 'cps-vm-helper.v2.1'},
            'boot_id': current_boot_id(), 'created_utc': now(), 'fingerprint_sha256': fp_sha, 'fingerprint': full,
            'commit': commit, 'selftest': {'results_name': results_name, 'sha256': sha_bytes(res_raw),
                                           'tests': s.get('tests'), 'passed_count': s.get('passed_count'),
                                           'failed_count': s.get('failed_count'), 'suite': s.get('suite')},
            'fingerprint_before_sha256': run.get('fingerprint_before_sha256'), 'fingerprint_after_sha256': fp_sha,
            'run': {k: run.get(k) for k in ('work_dir', 'started_utc', 'ended_utc', 'exit', 'pid')},
            'results_tools': {k: s.get(k) for k in ('writer_portable_sha256', 'saved_qa_sha256', 'visual_qa_sha256')}
            | {'checker_node_sha256': (s.get('checker_node') or {}).get('sha256')}}


def selftest_ok(cfg, run, s, node_sha):
    """v1 cmd_fingerprint_pass's checks: exit 0, failed 0, tests == passed == expected, visual not skipped, tool shas."""
    exp = HELPER_REPO / 'research' / 'export'
    n = cfg['selftest_expected_tests']
    return (run.get('exit') == 0 and s.get('failed_count') == 0 and s.get('tests') == n and s.get('passed_count') == n
            and s.get('visual_skipped') is False
            and s.get('writer_portable_sha256') == sha_file(exp / 'writer_portable.py')
            and s.get('saved_qa_sha256') == sha_file(exp / 'saved_qa.py')
            and s.get('visual_qa_sha256') == sha_file(exp / 'visual_qa.py')
            and (s.get('checker_node') or {}).get('sha256') == node_sha)


def halt_code(h):
    """§13.4: map a reused Halt to ('wait', seconds) | ('stop', code)."""
    if h.kind == 'REFUSED' and h.code == 'JOB_BUSY':
        return 'wait', 30
    if h.kind == 'NEED' and h.code == 'CLOCK_WAIT':
        return 'wait', None
    return 'stop', h.code

