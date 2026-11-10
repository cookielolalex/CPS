"""Lint L1's runtime half (spec §14.6): record every code the shipped code raises or prints while the tests run.

install() wraps, in this process: v1compat.Halt, core.step.Halt and core.step.Stop (constructed = raised), the
durable, outcome and score_check refusal exceptions, cli.emit (a REFUSED line or a DO: STOP block) and cli.bare (any
printed REFUSED or STOP line). scan(lines) records codes from lines printed by another process (session_start.sh).
dump() writes this process's set to $CPSVM2_SEEN_DIR/seen_<pid>.json (run_tests.py sets the folder; every suite and
every worker process calls dump() when it ends). Nothing here changes what the wrapped code does."""
import json
import os
import re

CODES = set()
_DONE = []
LINE_RX = re.compile(r'^(?:REFUSED ([A-Z][A-Z0-9_]+)$|DO: STOP ([A-Z][A-Z0-9_]+) HANDBACK [ABC]$)')


def add(code):
    if isinstance(code, str) and code and code != 'IDLE':           # STOP IDLE is §6.4's idle block, not a code
        CODES.add(code[7:] if code.startswith('HALTED_') else code)


def scan(lines):
    for ln in lines or ():
        m = LINE_RX.match(ln)
        if m:
            add(m.group(1) or m.group(2))


def _wrap_init(cls, get):
    orig = cls.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        add(get(self))
    cls.__init__ = init


def install():
    if _DONE:
        return
    _DONE.append(True)
    import sys
    vm2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if vm2 not in sys.path:
        sys.path.insert(0, vm2)
    from cpsvm2 import cli
    from cpsvm2.core import outcome, step
    from cpsvm2.maint import assemble, score_check
    from cpsvm2.vio import durable, v1compat
    _wrap_init(v1compat.Halt, lambda h: h.code if h.kind in ('REFUSED', 'STOP') else None)
    _wrap_init(step.Halt, lambda h: h.code)
    _wrap_init(step.Stop, lambda h: h.code)
    _wrap_init(durable.DurableError, lambda e: e.code)
    _wrap_init(outcome.OwnerChecksInvalid, lambda e: e.code)
    _wrap_init(score_check.Refused, lambda e: e.code)
    _wrap_init(assemble.Bad, lambda e: e.args[0] if e.args else None)
    emit0, bare0 = cli.emit, cli.bare

    def emit(env, state_code, blk, expect, refused=None):
        if refused is not None:
            add(refused)
        if blk.do and blk.do[0] == 'STOP':
            add(blk.do[1].get('code'))
        return emit0(env, state_code, blk, expect, refused)

    def bare(lines, code):
        scan(lines)
        return bare0(lines, code)
    cli.emit, cli.bare = emit, bare


def dump():
    d = os.environ.get('CPSVM2_SEEN_DIR')
    if not d:
        return
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, 'seen_%d.json' % os.getpid())
    old = set()
    if os.path.isfile(p):
        with open(p) as f:
            old = set(json.load(f))
    with open(p + '.tmp', 'w') as f:
        json.dump(sorted(old | CODES), f)
    os.replace(p + '.tmp', p)


def collect(d):
    out = set()
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else ():
        if n.startswith('seen_') and n.endswith('.json'):
            with open(os.path.join(d, n)) as f:
                out |= set(json.load(f))
    return out
