"""Hash every 046b package member (manifest self-excluded)."""
import hashlib, json, sys
from pathlib import Path
PKG = Path(__file__).resolve().parents[1] / 'package'
status = sys.argv[1] if len(sys.argv) > 1 else 'DRAFT_UNDER_INDEPENDENT_REVIEW'
files = sorted(p for p in PKG.rglob('*') if p.is_file() and p.name != 'PACKAGE_MANIFEST.json' and '__pycache__' not in p.parts)
entries = [{'path': p.relative_to(PKG).as_posix(), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
m = {'schema': 'cps.guideline-package.manifest.v2', 'candidate': '046b', 'parent_candidate': '046a',
     'parent_manifest_sha256': '6448cd3dab2d061cdd52ee1f9c26c41376b05ec7daf9339a686b6dca2344e60d', 'status': status,
     'target_runtime': 'User-proposed sol6.1/xhigh is not selectable from Claude Code; every run records the actual model, effort and tools.',
     'files': entries, 'utf8_bytes': sum(e['bytes'] for e in entries), 'manifest_self_excluded': True,
     'deployment_approved': False}
(PKG / 'PACKAGE_MANIFEST.json').write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'files': len(entries), 'bytes': m['utf8_bytes'], 'status': status}))
