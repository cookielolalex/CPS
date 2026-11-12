"""Probe P5 (spec §12.5): does a detached process survive the end of the tool call that started it?
    python3 -I -B probe_p5.py start --dir D [--seconds 900] | hold --dir D --seconds S | check --dir D [--min-gap 480]
check refuses (exit 4): SAME_CALL, TOO_EARLY, OTHER_BOOT, NOT_STARTED; start refuses WORKER_ALIVE."""
import argparse, json, os, secrets, subprocess, sys, time

SCHEMA = 'cps.vm2-probe-p5.v1'


def utc(t=None):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() if t is None else t))


def epoch(s):
    return float(__import__('calendar').timegm(time.strptime(s, '%Y-%m-%dT%H:%M:%SZ')))


def boot_id():
    with open(os.environ.get('CPS_VM_BOOT_ID_PATH') or '/proc/sys/kernel/random/boot_id') as f:
        return f.read().strip()


def write(path, doc):
    tmp = path + '.tmp_%d' % os.getpid()
    with open(tmp, 'w') as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def alive(pid):
    try:
        os.kill(pid, 0)
    except (OSError, TypeError):
        return False
    try:
        with open('/proc/%d/stat' % pid) as f:
            return f.read().rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return True


def refuse(code):
    print('REFUSED %s' % code)
    return 4


def main(argv):
    ap = argparse.ArgumentParser(prog='probe_p5.py')
    ap.add_argument('cmd', choices=('start', 'hold', 'check', '_worker'))
    ap.add_argument('--dir', required=True)                     # G8: never a default under HOME (read-only on the Dot)
    ap.add_argument('--seconds', type=int, default=900)
    ap.add_argument('--min-gap', type=int, default=480)
    ap.add_argument('--token', default='')
    a = ap.parse_args(argv)
    d, now = os.path.abspath(a.dir), time.time()
    st = read(os.path.join(d, 'START.json'))
    if a.cmd == '_worker':
        for n in range(1, a.seconds + 1):
            with open(os.path.join(d, 'HEARTBEAT.jsonl'), 'a') as f:
                f.write(json.dumps({'utc': utc(), 'n': n, 'token': a.token}) + '\n')
            time.sleep(1)
        write(os.path.join(d, 'DONE.json'), {'schema': SCHEMA, 'token': a.token, 'utc': utc()})
        return 0
    if a.cmd in ('start', 'hold'):
        os.makedirs(d, exist_ok=True)
    if a.cmd == 'start':
        if a.seconds < a.min_gap:                       # MAINT-10: a worker that ends before the check proves nothing
            return refuse('SECONDS_BELOW_MIN_GAP')
        if st and st.get('boot_id') == boot_id() and alive(st.get('worker_pid')) \
                and (read(os.path.join(d, 'DONE.json')) or {}).get('token') != st.get('token'):
            return refuse('WORKER_ALIVE')
        tok = secrets.token_hex(8)
        doc = {'schema': SCHEMA, 'token': tok, 'boot_id': boot_id(), 'started_utc': utc(now), 'seconds': a.seconds,
               'caller_ppid': os.getppid(), 'caller_sid': os.getsid(0), 'caller_pgid': os.getpgid(0),
               'start_pid': os.getpid(), 'worker_pid': None, 'start_exited_utc': None}
        p = subprocess.Popen([sys.executable, '-I', '-B', os.path.abspath(__file__), '_worker', '--dir', d,
                              '--seconds', str(a.seconds), '--token', tok], start_new_session=True, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        doc.update(worker_pid=p.pid, start_exited_utc=utc())
        write(os.path.join(d, 'START.json'), doc)
        print('NEXT: end this tool call now; in a NEW tool call at least %d s later run: python3 -I -B %s check '
              '--dir %s' % (a.min_gap, os.path.abspath(__file__), d))
        return 0
    if a.cmd == 'hold':
        path = os.path.join(d, 'HOLD_%d_%s.json' % (a.seconds, utc(now).replace('-', '').replace(':', '')))
        write(path, {'schema': SCHEMA, 'seconds': a.seconds, 'started_utc': utc(now), 'completed_utc': None})
        time.sleep(a.seconds)
        write(path, {'schema': SCHEMA, 'seconds': a.seconds, 'started_utc': utc(now), 'completed_utc': utc()})
        print(path)
        return 0
    if not st or not st.get('start_exited_utc'):
        return refuse('NOT_STARTED')
    if os.getppid() == st['caller_ppid'] or os.getsid(0) == st['caller_sid']:
        return refuse('SAME_CALL')
    if st['boot_id'] != boot_id():
        return refuse('OTHER_BOOT')
    if now < epoch(st['start_exited_utc']) + a.min_gap:
        return refuse('TOO_EARLY')
    hb = []
    try:
        with open(os.path.join(d, 'HEARTBEAT.jsonl')) as f:
            hb = [x for x in (json.loads(ln) for ln in f if ln.strip()) if x.get('token') == st['token']]
    except (OSError, ValueError):
        pass
    last = hb[-1]['utc'] if hb else None
    lived = epoch(last) - epoch(st['start_exited_utc']) if last else None
    done = (read(os.path.join(d, 'DONE.json')) or {}).get('token') == st['token']
    live = alive(st['worker_pid'])
    holds = [read(os.path.join(d, n)) for n in sorted(os.listdir(d)) if n.startswith('HOLD_') and n.endswith('.json')]
    ok = lived is not None and lived >= a.min_gap - 5 and (live or done) and a.min_gap >= 480
    rep = dict(st, check_utc=utc(now), check_ppid=os.getppid(), check_sid=os.getsid(0), min_gap=a.min_gap,
               heartbeats=len(hb), last_heartbeat_utc=last, worker_lived_after_start_exit_seconds=lived,
               worker_alive=live, done=done, holds=holds, verdict='PASS' if ok else 'FAIL')
    path = os.path.join(d, 'PROBE_P5_%s_%s.json' % (st['boot_id'][:8], utc(now).replace('-', '').replace(':', '')))
    write(path, rep)
    print(path)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
