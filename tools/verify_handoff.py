"""Read-only publication verification; does not import or execute CPS."""
from pathlib import Path
import hashlib
import json
import re
import sys
from urllib.parse import unquote


def verify(root):
    root = root.resolve()
    manifest = json.loads((root / "PUBLICATION_MANIFEST.json").read_text(encoding="utf-8"))
    failures = []
    for item in manifest["files"]:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root):
            failures.append(f"Outside repository: {item['path']}")
            continue
        if not path.is_file():
            failures.append(f"Missing: {item['path']}")
            continue
        data = path.read_bytes()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            failures.append(f"Changed: {item['path']}")
        if path.suffix == ".json":
            try:
                json.loads(data)
            except (ValueError, UnicodeError) as exc:
                failures.append(f"JSON {item['path']}: {exc}")
        if path.suffix == ".md":
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", data.decode("utf-8-sig")):
                target = target.strip().strip("<>").split("#", 1)[0]
                if not target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                    continue
                local = (path.parent / unquote(target)).resolve()
                if not local.is_relative_to(root) or not local.exists():
                    failures.append(f"Unresolved local link in {item['path']}: {target}")
    state = json.loads((root / "CURRENT_STATE.json").read_text(encoding="utf-8"))
    if state["status"] not in ("IDLE_HANDOFF_REQUESTED_REVIEW_INCOMPLETE", "IDLE_HANDOFF_AFTER_046B_SOURCE_TRIALS") or state["development_allowed"]:
        failures.append("This snapshot must preserve the handoff-only execution boundary")
    if state["reserved_answers_opened"]:
        failures.append("This snapshot must preserve reserved-answer closure")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"Verified {len(manifest['files'])} publication files. CPS was not executed.")
    print("This verifies this snapshot's bytes and links, not source correctness or deployment readiness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(verify(Path(__file__).resolve().parents[1]))
