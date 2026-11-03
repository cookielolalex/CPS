"""Audit a Claude Code subagent transcript (JSONL) for a bounded generator run.

Prints only metadata: models observed, tool names, file paths and command strings, and
flags any path outside the allowed run directory. Never prints message or tool-result text.
Usage: python3 -I -B audit_transcript.py --transcript T.jsonl --allowed-root RUN_DIR [--out AUDIT.json]
"""
import argparse, json, re, sys
from collections import Counter
from pathlib import Path

PATH_RE = re.compile(r'(/(?:[^\s\'"`;|&<>(){}]+))')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--transcript', required=True)
    ap.add_argument('--allowed-root', required=True)
    ap.add_argument('--out')
    a = ap.parse_args()
    root = str(Path(a.allowed_root).resolve())
    models, requested, tools, calls, outside, attach = Counter(), Counter(), Counter(), [], [], Counter()
    usage = Counter()
    first = last = None
    for line in Path(a.transcript).read_text(encoding='utf-8').splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = d.get('timestamp')
        if ts:
            first = first or ts
            last = ts
        if d.get('type') == 'attachment':
            att = d.get('attachment') or {}
            attach[str(att.get('type'))] += 1
        if d.get('type') != 'assistant':
            continue
        msg = d.get('message') or {}
        if msg.get('model'):
            models[msg['model']] += 1
        if d.get('requestedModel'):
            requested[d['requestedModel']] += 1
        for k, v in (msg.get('usage') or {}).items():
            if isinstance(v, int):
                usage[k] += v
        for c in msg.get('content') or []:
            if c.get('type') != 'tool_use':
                continue
            name, inp = c.get('name'), c.get('input') or {}
            tools[name] += 1
            rec = {'tool': name}
            for key in ('file_path', 'path', 'notebook_path'):
                if key in inp:
                    rec[key] = inp[key]
            for key in ('pattern', 'glob'):
                if key in inp:
                    rec[key] = str(inp[key])[:200]
            if 'command' in inp:
                rec['command'] = str(inp['command'])[:600]
            if name in ('WebFetch', 'WebSearch', 'Agent', 'Task'):
                rec['flag'] = 'NETWORK_OR_DELEGATION_TOOL'
                outside.append(rec)
            paths = [rec[k] for k in ('file_path', 'path', 'notebook_path') if k in rec]
            if 'command' in rec:
                paths += PATH_RE.findall(rec['command'])
            bad = [p for p in paths if not str(Path(p).resolve() if p.startswith('/') else p).startswith(root)
                   and not p.startswith(('/usr/bin', '/usr/local/bin', '/bin/', '/dev/null', '/opt/node22/bin'))]
            if bad:
                rec['outside_paths'] = bad
                outside.append(rec)
            calls.append(rec)
    report = {'transcript': a.transcript, 'allowed_root': root, 'first_timestamp': first, 'last_timestamp': last,
              'observed_models': dict(models), 'requested_models': dict(requested), 'tool_counts': dict(tools),
              'attachment_types': dict(attach), 'usage_totals': dict(usage), 'tool_calls': calls,
              'outside_or_flagged_calls': outside, 'outside_count': len(outside)}
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(text + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('observed_models', 'requested_models', 'tool_counts', 'attachment_types',
                                             'outside_count', 'first_timestamp', 'last_timestamp')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
