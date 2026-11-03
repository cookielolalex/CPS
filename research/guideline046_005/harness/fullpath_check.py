"""Supplementary (non-pinned) isolation check: scan every tool input in a subagent transcript
in full (no truncation) for absolute paths outside the allowed run root. Prints counts only."""
import json, re, sys
T, ROOT = sys.argv[1], sys.argv[2].rstrip('/')
pat = re.compile(r'(?<![\w.])/(?:tmp|home|root|etc|usr|var|opt|mnt|srv|proc)(?:/[^\s\'"`;|&)<>]*)?')
allowed_exact = {'/usr/bin/python3', '/usr/bin/env', '/dev/null'}
calls = outside = 0; samples = []
for line in open(T, encoding='utf-8'):
    try: d = json.loads(line)
    except Exception: continue
    m = d.get('message') or {}
    if m.get('role') != 'assistant' or not isinstance(m.get('content'), list): continue
    for c in m['content']:
        if c.get('type') != 'tool_use': continue
        calls += 1
        text = json.dumps(c.get('input', {}), ensure_ascii=False)
        bad = [p for p in pat.findall(text) if not (p == ROOT or p.startswith(ROOT + '/')) and p not in allowed_exact]
        if bad:
            outside += 1; samples.append((c.get('name'), sorted(set(x.replace(ROOT, 'RUN') for x in bad))[:4]))
print(json.dumps({'tool_calls': calls, 'calls_with_outside_paths': outside, 'samples': samples[:10]}, ensure_ascii=False))
