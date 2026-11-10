# Dot probe results (M001–M005, 2026-11-09/10)

What the operator ("the Dot", a ChatGPT agent with its own cloud VM) reported in its replies in the Drive folder `CPS/reports/M00n_*`. The replies themselves are the evidence; this file summarizes them without Drive file ids, conversation ids or business content. Recorded 2026-11-10.

## Phase 1 setup: complete

- M001: the full-folder check of the 45 files in `FOLDER_MANIFEST.md` found 37 ok and 8 workbooks damaged by the maintainer's base64 upload slips; `verify_drive_files.py` repaired 6 to the exact released bytes. The other 2 had too many slips and were re-sent as slip-proof text with `deploy/textcarry.py` (M005); the Dot rebuilt both to the manifest sha256 and the verifier marked them ok. All 45 files are now in place in Drive with their released bytes (the maintainer placed them by server-side copies), and the damaged copies and the PNGs made from them are in `_superseded/`.
- Light setup on the Dot's VM: setup 119–130 s, `check_env` all_met true, node v22.23.4 sha256 `94efd062…9a90`, the VM's own LibreOffice (LibreOfficeDev 26.8), Chinese render checks pass. The export self-test passed earlier (setup evidence `setup/eafe9b2/`).
- A real VM reset happened during M005 (while an approval was pending): all of `~/cps*` was gone; the Dot re-ran the light setup (130 s) and continued correctly.

## P1: new conversations (M002, M004)

- The Dot creates a new conversation with its platform's "Create Thread" feature, in the same cloud environment, without the parent's history. The test conversation read and wrote files on the same VM (same `$HOME`, uid and boot id). **P1 file access: PASS.**
- **Not isolated by the platform:** the new conversation has the same app tools as the Dot, including Google Drive, GitHub, web search and message-reading tools. A generator is kept to its prompt's files only by its instructions. Whether a conversation can be created without these tools is asked in M006.
- A model selector is optional at creation; the probe used the platform default, and no verified model identifier was exposed.
- The Dot can list its conversations (with an `attachedAt` time) and read their recorded messages and turn status; a full transcript including every tool execution and the files written is **not** available. So the transcript policy is O55 (attested reading, owner check before scoring), not export.
- A completed conversation can be resumed; an archive action stops one.

## P2 and M004: Drive

- Upload limit of the Dot's Drive tool: **100 MiB per file** (a 200 MB upload failed with HTTP 413 before any write; nothing appeared). A 50 MB random file round-tripped byte for byte (upload about 12 s, download about 8 s).
- Upload responses give the file id but **no md5 and no size**; search and metadata give id, size and creation time, but **no md5 or sha256**. Confirming an upload therefore needs a download-back and a sha256 compare.
- Exact-name search returns **every copy** of a name with distinct ids (no renaming); all 20 test files were found immediately after upload (no indexing lag seen).
- `name contains` search is not a prefix filter (it returned `P10_c` for `P1_`); client-side filtering works. Folder listing can be limited to the newest N by modified time; search pages carry a page token.
- The Dot can save raw tool results into a VM file programmatically, without retyping.
- Uploads are raw files (no Office conversion); a timed-out upload can still appear, so the destination must be checked before any retry.
- The Dot's platform sometimes **refuses uploads through an automatic approval review** (with wrong reasons); the uploads went through after the owner approved. Uploads must be verified absent before a retry, and some steps may wait for the owner.

## P3: machine

`$HOME` `/home/agent`, uid 1000, 9 CPUs, about 9 GB RAM, `/home/agent` and `/tmp` tmpfs of 4.9 GB each. Clock synchronisation could not be confirmed (no NTP information); the shell time agreed with Drive's creation times within about a minute.

## P5: background processes (M003)

- **A detached background process does not survive the end of the tool call that started it** (zero heartbeats; verdict FAIL). The tool runs each command in its own process namespace.
- **Foreground processes do survive across tool calls**: the Dot's command tool returns a resumable session, and polling it continued the same process; holds of 60, 240, 600 and 1,200 s all completed. A 1,200 s hold is a completed process, not proof of one uninterrupted tool call.
- Consequence for the VM helper: every stage must run in the foreground with the Dot polling the same session until it exits; nothing may rely on a detached worker.

## M006: isolation, audit, models, approvals

- Two ways start a conversation that can use the VM ("Create Thread" and a native worker). Neither offers any switch for tools, apps/connectors or internet access; both test conversations reported the same Drive, GitHub, web search, message-reading, Library, Calendar and Contacts tools. **Technical isolation: not available.** The owner accepted isolation by instruction with attestation (O63).
- Reading a conversation back gives its messages and turn status, **not** its tool calls or their arguments: there is no tool-call audit.
- A model can be chosen when a conversation is created (the native worker lists five model ids); the resolved model is not returned, so the generation record must state the requested model.
- The owner can approve a bounded class of actions in advance (for example uploads into `CPS/qualification/`); some actions (running new software outside the sandbox's writable paths, permission changes, deletion) still need approval each time. Writing outside the sandbox's writable paths used the platform's elevated route.

## Not yet known

- Behaviour of a conversation whose VM resets mid-run (not testable without forcing a reset).
- Which VM a scheduled mailbox run receives (the Dot could not yet confirm it).
