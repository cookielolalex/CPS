# Dot probe results (M001–M009, 2026-11-09/11)

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

## M007: timing, raw downloads, upload approvals (2026-11-11)

Recorded 2026-11-11 from the Dot's reply files, checked by the maintainer against what the message asked: the runner summary log, the stage-time output and both saved search objects were downloaded and decoded, and the probe file's sha256 was recomputed.

- **Another real VM reset** (the first recorded one was during M005). At the claim both `~/cps/.git` and `~/cps-tools/env.sh` were gone. The Dot waited about two hours for the owner's approval before re-running the light setup (161 s; `check_env` all_met; node sha256 `94efd062…9a90` unchanged). Resets are frequent: the restore path will run often, and each reset may wait for an owner approval unless that is approved in advance.
- **Runner suite on the Dot** at the setup commit `eafe9b2`: 249/249 passed, exit 0, 585.9 s. The maintainer's rehearsal of the same command took 250.1 s, so the Dot is about 2.3 times slower on the suite.
- **Stage times** (max over the suite's 25 invented jobs, 134 stages), Dot against the maintainer's rehearsal: `finish` 72.5 s against 16.2 s (about 4.5 times), `prepare` 5.0 s against 3.2 s, `scope-finish` 1.9 s against 1.1 s; every other stage 0.0 s.
- **Consequence for real jobs (projection, not a measurement).** The longest real `finish` stage on the maintainer machine (046g dev trial) was 190 s, dominated by one step: the internal visual QA, whose single `pdftoppm` call renders 336 A3 pages at 150 dpi (about 193 s alone; the LibreOffice PDF export takes about 7 s). At about 4.5 times, that stage would take roughly 850 s on the Dot. That is under the longest proven foreground hold (1,200 s, M003) and under `visual_qa.render`'s 900 s per-call timeout, but with little margin. An invented-data render of the same size on the Dot (M008) measures it before the helper's stage limits are set.
- **Raw downloads work byte-exact without base64.** The Drive fetch tool with `download_raw_file=true` and `include_base64=false` returns a file reference; the platform's download tool then writes the original bytes to a local attachment file and returns its path and size; the Dot copies that file with `cp`. The downloaded probe's sha256 equalled the original (`1442d97c…8982`, 11 bytes).
- **Saved tool results.** The Dot serializes the returned object with `JSON.stringify` in its orchestration code and writes it to the VM with a Python heredoc; it states that the same works for upload and folder-listing results. The saved search object has exactly the M004 envelope (`content`, `structuredContent.results[]`, `isError`), sizes as strings; an empty search is `{"results": []}`.
- **Upload review is literal.** The automatic review refused the probe upload that step 3 asked for, because the message's final list of files to upload did not name it ("outside the authorized payload"). After the owner approved it, it went through. Messages must list every upload in one place. The standing rules the Dot quoted come from owner messages: the 5-at-once and 20-a-day document limits were written for a different storage service (Synology Drive/File Station) and, by their scope, are not Google Drive quotas; the CPS mailbox rules forbid deleting, replacing, renaming or moving Drive files. The Dot confirms that the owner can approve in advance a bounded class of new-file uploads into `CPS/qualification/` and `CPS/reports/` and their subfolders, in the owner's conversation with the Dot or through the platform's custom-rules confirmation; such an approval does not authorize qualification itself.
- **Read-only job folders.** As uid 1000 (not root), `rm -rf` of the suite's work folder failed with "Permission denied" on read-only frozen fixture directories; it worked after `chmod u+w` on the directories only (no symlink followed), with the owner's approval. Every helper and runner test so far ran as root, which ignores these permission bits; the helper's v2.1 suite adds a non-root run (plan decision D16).

## M008: large invented render and a 30-minute hold (2026-11-11)

Recorded 2026-11-11 from the Dot's REPLY.md, checked against the message.

- Steps 1 and 2 matched: the setup commit, `visual_qa.py` sha256 `68814f14…8ac0`, and the invented workbook's cell hash `27d563a0…a0e2` (3,100 rows; 335 pages and 332 s on the maintainer's busy machine).
- **The render was killed by an interruption, not by the renderer.** The command was started once in the foreground; after its first return, a poll of that session was interrupted. On resumption the Dot's tool reported `cell belongs to a stale code-mode host generation`, and polling the process gave `Unknown process id`. No visual QA, LibreOffice or pdftoppm process remained; `render.out` and `render.err` were empty and the render folder had no files (no PDF); `/tmp` held about 16 MB more than before, consistent with a LibreOffice start that was cut off. Files on the VM were otherwise intact (`~/cps-tools`, the probe folder): this was not a VM reset. The render time on the Dot is still unmeasured.
- **The 30-minute hold completed** in one uninterrupted run: 1,800 s, 31 beats, exit 0, with five polls of about 300 s each and a sixth that completed. So a foreground command longer than 1,200 s can complete, as long as nothing interrupts the Dot's work.
- Consequence: a running command dies when the Dot's command host is replaced, which happens on an interruption, even without a VM reset. Runner stages last minutes, so the operating rules must keep anything from interrupting the Dot while a command runs. For the helper, `FOREGROUND_DIED` in the same boot is a real, expected event, not only a theoretical one. What caused the interruption is asked in M009.
- Cleanup passed; nothing was uploaded besides CLAIM.md and REPLY.md.

## M009: render timing, progress notes, the M008 readback (2026-11-11)

Recorded 2026-11-11 from the Dot's REPLY.md, checked against the message: the setup commit, `visual_qa.py` sha256 `68814f14…8ac0` and the invented workbook's cell hash `27d563a0…a0e2` matched; the reply folder holds only CLAIM.md and REPLY.md.

- **The render completed on the Dot.** `visual_qa.py` exit 0, status `RENDERED_AWAITING_VISUAL_INSPECTION`, `complete_render` true, **619 s** for **403 pages** (550 MB). The same workbook gives 335 pages on the maintainer's machine (332 s there), so the Dot's LibreOffice paginates it into about 20% more pages. Per page that is 1.54 s against 0.99 s, about 1.55 times slower.
- **`pdftoppm` alone** on the same PDF: exit 0, **706 s** for 403 pictures (530 MB), against 287 s for 335 here: 1.75 s against 0.86 s per page, about 2 times slower. It took longer than the whole render step, which runs the same `pdftoppm -r 150 -png` call after the LibreOffice export, so the same call took at least 14% longer when run alone: single timings on the Dot are not precise.
- **Consequence for real jobs (projection, not a measurement).** M007's 4.5 times came from the suite's small jobs, where fixed start-up costs probably weigh more; on this large render the Dot was about 1.55 to 2 times slower per page. Applied to the largest real `finish` stage (190 s here; one `pdftoppm` call over 336 real pages, about 193 s alone, lighter per page than the invented ones), and assuming the Dot again paginates about 20% more pages, that projects to roughly 350 to 480 s on the Dot (190 to 193 s times 1.55 to 2 times 1.2), or up to about 550 s allowing for the 14% spread between M009's two timings of the same call. Even 550 s leaves about 1.6 times margin under the 900 s timeout that `visual_qa.render` applies to each LibreOffice and `pdftoppm` call, and more under the longest proven hold (1,800 s). The standalone `pdftoppm` run on the denser invented pages took 706 s, 78% of the 900 s the same call is allowed inside `visual_qa.render`, so a real job about 1.6 to 1.9 times the largest seen so far, or an unusually slow run, could reach the timeout.
- **No interruption in M009.** Every command block ran once in the foreground, and the Dot polled the same session until it exited (300 s polls in steps 3 to 5); no `stale code-mode host generation` or `Unknown process id` error.
- **A progress note did not stop a running command (as tested).** The requested one-line note was sent while the 6-minute hold ran, and the hold completed (360 s, 7 beats). The owner also asked two questions, one during step 4 and one during step 5; the Dot answered with four short replies besides the note (the two during step 4 broke M009's quiet rule, which the Dot reported as a deviation), and the running commands completed. In M009, an owner message and the Dot's own messages during a running command did not end the Dot's turn or stop the command; this does not show that other interruptions are harmless.
- **The cause of M008's interruption is still unknown.** The readback exposes only the latest turn of the conversation that ran M008 (completed), not the turn in which the render started. New facts: M008 ran in a separate conversation that the Dot's coordinating conversation created; the coordinating conversation sent its progress note, then waited, and a clock-triggered turn at 04:13 found the render dead. No owner message appears in the owner's conversation in that interval (the separate conversation's own messages are not visible). M009's claim names the coordinating conversation itself, but the reply speaks of a "command worker" and does not say plainly whether M009's commands ran in the coordinating conversation or in a worker it started; M010 asks. M010 (posted 2026-11-11) tests the two remaining suspects with invented holds: a command left running when the turn ends, and a command run in a separate conversation while the coordinating one waits.
- **Approval wait.** The Dot paused M009's commands for the owner's explicit confirmation, which came 36 minutes after the claim.
- Cleanup passed; nothing was uploaded besides CLAIM.md and REPLY.md.

## Not yet known

- Behaviour of a conversation whose VM resets mid-run (not testable without forcing a reset).
- Which VM a scheduled mailbox run receives (the Dot could not yet confirm it).
- The Dot's time for a real job's `finish` stage (projected at roughly 350 to 550 s from M009's invented render, not measured).
- What killed M008's render: the end of the turn while the command ran, running it in a separate conversation while the coordinating one waited, or the platform (tested by M010).
