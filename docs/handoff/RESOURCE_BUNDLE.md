# Private resource ZIP

The separately delivered `CPS_handoff_20261103_portable.zip` includes a copy of this repository plus private selected-case evidence and local working files. It contains contract/workbook values and should be shared as private project data. Credentials/authentication files and reserved-project documents are excluded.

Start with [offline verification](PORTABILITY.md). The revised ZIP includes portable source/evaluator binding files, the complete1141208saved-cache inventory and two views, and offline workbook-reading libraries.

## Layout

- `public_repo/`: this public technical snapshot.
- `private/refinement/`: complete selected039/041/045run folders,045source/evaluator/audit evidence,046candidate and partial1141208preparation, current plans/state, source manifests/cohort metadata and source reader code.
- `private/projects/`: original permitted sources and existing evaluation-only actual未填for1140908,1141210,1131207;1141208has only its original source and partial preparation. No new1141208historical target was opened.
- `private/naming_study/`: full source/target-informed naming study and inventories. Evaluation-only.
- `private/comparisons/`: latest comparison data/workbook and exposure receipt.
- `private/CPS/`, `private/policies/`, `private/deps/`: local policies/baseline and existingxlrdwith licensing metadata.
- `RESOURCE_MAP.json`: original absolute paths mapped to bundled files, sizes and SHA256. Frozen records retain their original paths/bytes; use the map instead of silently rewriting them.
- `tools/verify_bundle.py` and `tools/locate_resource.py`: read-only integrity/location helpers. No CPS/model invocation.
- `START_HERE.md`, `HANDOFF_PROMPT.md`, `BUNDLE_MANIFEST.json`: entrypoint, reusable continuation prompt and complete bundled file inventory.

## Same computer and portability

On the original computer use `D:\STMS Price Quote\CPS\LOCAL_DIRECTION_LATEST.md` and the current handoff record to locate authoritative files. The ZIP is a portable evidence snapshot, not a fully installed model service. On another computer extract to a short path, verify the bundle, map required originals through `RESOURCE_MAP.json` and declare a new exact input manifest/adapter. Do not edit frozen evidence or replay hardcoded historical runners: their clocks are expired and some dependencies use original absolute paths.

Use a configured Codex/AI session with authorized account access; no API key or auth store is included. The existing runtime uses Python, Node and `@oai/artifact-tool`; source reads also usexlrd. Bundled software runtimes/node_modules are omitted. Same-computer runtime paths and dependency provenance are in the private handoff environment note. Missing capabilities must be installed/located explicitly, not inferred from a successful import elsewhere.

This ZIP covers four selected projects, the original1140608backlog workbook, and the immediate continuation. It does not duplicate the entire Data Center, all153development projects, mailbox archives or38reserved projects. Those remain external future data requirements. Case inventory metadata is retained to preserve cohort/exclusion rules. The user-provided prompt is continuation authority; opening this ZIP alone is not.
