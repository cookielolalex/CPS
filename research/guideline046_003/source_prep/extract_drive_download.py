"""Recover exact bytes of Google Drive connector downloads from a Claude Code transcript.

The Drive connector returns file bytes as base64 inside a tool result. This script scans a
transcript JSONL (main session or subagent), finds download_file_content results for the given
Drive file ids, decodes them and writes the bytes, verifying an expected SHA-256 when given.
It never prints file content. Usage:
  python3 -I -B extract_drive_download.py --transcript T.jsonl --file-id ID --out PATH [--sha256 HEX]
"""
import argparse, base64, hashlib, json, sys
from pathlib import Path


def iter_results(transcript):
    for line in Path(transcript).read_text(encoding='utf-8').splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = d.get('message') or {}
        content = msg.get('content')
        if not isinstance(content, list):
            continue
        for c in content:
            if c.get('type') != 'tool_result':
                continue
            parts = c.get('content')
            texts = [parts] if isinstance(parts, str) else [p.get('text', '') for p in (parts or []) if isinstance(p, dict)]
            for t in texts:
                if '"content"' in t and '"id"' in t:
                    try:
                        yield json.loads(t)
                    except json.JSONDecodeError:
                        continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--transcript', required=True)
    ap.add_argument('--file-id', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--sha256')
    a = ap.parse_args()
    hits = [r for r in iter_results(a.transcript) if isinstance(r, dict) and r.get('id') == a.file_id and isinstance(r.get('content'), str)]
    if not hits:
        print(json.dumps({'status': 'NOT_FOUND', 'file_id': a.file_id}))
        return 1
    data = base64.b64decode(hits[-1]['content'], validate=True)
    digest = hashlib.sha256(data).hexdigest()
    if a.sha256 and digest != a.sha256:
        print(json.dumps({'status': 'SHA256_MISMATCH', 'file_id': a.file_id, 'sha256': digest, 'bytes': len(data)}))
        return 2
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(json.dumps({'status': 'WRITTEN', 'file_id': a.file_id, 'title': hits[-1].get('title'), 'bytes': len(data), 'sha256': digest,
                      'expected_match': (digest == a.sha256) if a.sha256 else None}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
