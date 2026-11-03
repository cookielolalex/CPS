# Retrieving project files from the owner's Drive (2026-11-03)

The year folders (113, 114 and 115年度工作) are each over 1 GB, too large to attach to a session. Files are therefore fetched one at a time:

1. A retrieval subagent locates the exact contract file named in the cohort registry. It downloads only that file with the Drive connector. The connector returns base64 inside the tool result.
2. `extract_drive_download.py` reads that subagent's transcript, decodes the bytes and **verifies the SHA-256 recorded in the cohort registry**. A mismatch is rejected.
3. Source-only development needs contracts only. No historical 未填/已填 target is downloaded for source-only work.
4. Reserved projects (38 IDs in the cohort registry) and excluded cases are never fetched.

Verified so far: 1141001, 27,676 bytes, SHA-256 equal to the registry value.
