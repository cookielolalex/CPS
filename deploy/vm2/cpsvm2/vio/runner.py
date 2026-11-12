"""Runner v4 argv (spec §7.4), one command through the reused run_runner, and result parsing (§7.2, R2, R3). The runner
module is compiled from its pinned bytes (for its Ledger class and restart_problem, §3.5 FROZEN); the helper and the
maintainer tools use this one loader."""
import hashlib
import json
import re
import types

from . import v1compat, v1reuse
from .v1compat import Halt, runner_path
from .v1reuse import run_runner

PIN = '7505e98ac88bc09a5e0507124e4cb381a5491c1112f418bcf5ca6553ab14f431'
CONTINUE_STEPS = ('SCOPE_READER', 'GENERATE', 'VISUAL_REVIEW', 'DELIVER_CHECK', 'FREEZE', 'DELIVER', 'DONE')
WORD = re.compile(r'[\x21-\x7e]+')
MODEL = re.compile(r'[A-Za-z0-9._:-]{2,64}')


def load_runner():
    """The runner module (cps_job.py) compiled from the bytes whose sha256 is the pin, never from bytecode (S-07);
    sets v1compat.CJ and v1reuse.CJ."""
    if v1compat.CJ is not None:
        return v1compat.CJ
    p = runner_path()
    raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PIN:
        raise Halt('STOP', 'LAYOUT_RUNNER_NOT_PINNED', 'the runner is not the pinned v4')
    mod = types.ModuleType('cps_job_v4')
    mod.__file__ = str(p)
    exec(compile(raw, str(p), 'exec'), mod.__dict__)
    v1compat.CJ = v1reuse.CJ = mod
    return mod


def argv_for(sub, a):
    """§7.4. a: {'base', 'model', 'job_dir', 'case', 'reader', 'root', 'admission', 'utc14', 'qualification' (bool),
    'prompt_sha256', 'conversation', 'run_dir', 'generator_model', 'transcript', 'started_utc', 'ended_utc'}."""
    B, M, D = a['base'], a['model'], a.get('job_dir')
    rel = B + '/runtime/RELEASE.json'
    if sub == 'prepare' and a['qualification']:
        j = '%s/runtime/qualification/jobs/%s' % (B, a['case'])
        v = ['prepare', '--release', rel, '--job', j + '/JOB.json', '--job-title-file', j + '/JOB_TITLE.json',
             '--jobs-root', '%s/qual/%s' % (B, a['root']), '--reader', a['reader'], '--qualification',
             '--admission', a['admission'], '--operator-model', M]
    elif sub == 'prepare':
        j = '%s/everyday_inputs/%s' % (B, a['case'])
        v = ['prepare', '--release', rel, '--job', j + '/JOB.json', '--job-title-file', j + '/JOB_TITLE.json',
             '--jobs-root', '%s/jobs/%s' % (B, a['utc14']), '--operator-model', M]
    elif sub == 'nonattempt':
        v = ['nonattempt', '--release', rel, '--admission', a['admission'], '--case', a['case'], '--reader',
             a['reader'], '--jobs-root', '%s/qual/nonattempts_%s' % (B, a['reader']), '--operator-model', M]
    elif sub == 'scope-finish':
        v = ['scope-finish', '--job-dir', D, '--reader-response', D + '/scope/reader/output/SCOPE_READER_RESPONSE.json',
             '--reader-prompt-sha256', a['prompt_sha256'], '--reader-conversation-id', a['conversation'],
             '--operator-model', M]
    elif sub == 'finish':
        v = ['finish', '--job-dir', D, '--response', '%s/%s/output/response.json' % (D, a['run_dir']),
             '--generator-model', a['generator_model'], '--generation-record', D + '/run/GENERATION_RECORD.json']
        if a.get('transcript'):
            v += ['--transcript', a['transcript']]
        v += ['--operator-model', M]
    elif sub == 'visual-record':
        v = ['visual-record', '--job-dir', D, '--review', D + '/qa/visual_review/VISUAL_REVIEW.json',
             '--reviewer-conversation-id', a['conversation'], '--operator-model', M]
    elif sub == 'deliver-check':
        v = ['deliver-check', '--job-dir', D, '--operator-model', M]
    elif sub == 'interrupt':
        v = ['interrupt', '--job-dir', D, '--reason', 'TECHNICAL_VM_RESET', '--started-utc', a['started_utc'],
             '--ended-utc', a['ended_utc']]
        if a.get('conversation'):
            v += ['--conversation-id', a['conversation']]
        v += ['--operator-model', M]
    elif sub == 'freeze':
        v = ['freeze', '--job-dir', D, '--operator-model', M]
    elif sub == 'verify-frozen':
        v = ['verify-frozen', '--job-dir', D]
    else:
        raise Halt('STOP', 'UNCLASSIFIED', 'unknown runner sub-command')
    for i, x in enumerate(v):
        ok = MODEL.fullmatch(x) if i > 0 and v[i - 1] in ('--operator-model', '--generator-model') else WORD.fullmatch(x)
        if not isinstance(x, str) or not ok:
            raise Halt('STOP', 'INTERNAL_PRINT', 'a runner argument is not ASCII without whitespace')
    return v


def parse(sub, code, lines):
    """R2/R3: the last two non-empty stdout lines must be one JSON object then `NEXT: <step>` or `REFUSED: <code>`,
    and the exit must agree (0 CONTINUE_STEPS, 3 STOP_/OWNER_DECISION, 4 REFUSED). Returns {'result': 'NEXT' |
    'REFUSED' | 'UNPARSEABLE', 'next', 'codes', 'args', 'json'} (args: the NEXT line's key=value words)."""
    bad = {'result': 'UNPARSEABLE', 'next': 'RUNNER_OUTPUT_UNPARSEABLE', 'codes': [], 'args': {}, 'json': None}
    if len(lines) < 2:
        return bad
    try:
        j = json.loads(lines[-2])
    except ValueError:
        return bad
    if not isinstance(j, dict):
        return bad
    last = lines[-1].strip()
    if last.startswith('REFUSED: '):
        tok = last[len('REFUSED: '):].strip()
        if code != 4 or not re.fullmatch(r'[A-Z][A-Z0-9_]*', tok):
            return bad
        return {'result': 'REFUSED', 'next': tok, 'codes': [], 'args': {}, 'json': j}
    if not last.startswith('NEXT: '):
        return bad
    words = last[len('NEXT: '):].split(' ')
    tok = words[0]
    want = 0 if tok in CONTINUE_STEPS else 3 if (tok.startswith('STOP_') or tok == 'OWNER_DECISION') else None
    if want is None or code != want or not re.fullmatch(r'[A-Z][A-Z0-9_]*', tok):
        return bad
    rest = last[len('NEXT: ') + len(tok):].strip()
    if tok == 'DELIVER':                    # the standard file's path holds the title (R32): never split, never printed
        args = {'file': rest[len('file='):]} if rest.startswith('file=') else {}
    else:
        args = dict(w.split('=', 1) for w in words[1:] if '=' in w)
    codes = j.get('codes') if isinstance(j.get('codes'), list) else []
    return {'result': 'NEXT', 'next': tok, 'codes': [str(c) for c in codes], 'args': args, 'json': j}


def run(ctx2, sub, argv, log):
    """One runner command (argv only, -I -B; stdout and stderr appended to the worker log, never printed).
    Returns (parsed result, exit code, stdout sha256)."""
    code, lines, _, _, out_sha = run_runner(ctx2, argv, log)
    return parse(sub, code, lines), code, out_sha
