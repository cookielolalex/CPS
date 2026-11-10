<!-- Status: spec delta for cps-vm-helper.v2 (applies to docs/handoff/VM_HELPER_V2_SPEC.md r2), written 2026-11-10 from the Dot probe results (docs/handoff/PROBE_RESULTS_20261110.md): foreground stages only, md5-hidden confirmation by download-back, 90 MiB upload cap, refused/timed-out uploads, listing as head hint only, attachedAt windows, clock tolerance. Applied in deploy/vm2 at the commit that adds this file. -->

# SPEC_V2 delta for the probe results (P1, P2/M004, P3, P5/M003), 2026-11-10

Status: DELTA to `docs/handoff/VM_HELPER_V2_SPEC.md` r2. It is not reviewed and not admitted. Sources: `docs/handoff/PROBE_RESULTS_20261110.md` (cited as PR), owner decisions O43-O61, and the r2 text. A builder applies the sections below in order. Each item names the r2 section it changes. Text this delta does not mention stays as r2 has it. Where the delta decides something the probes leave open, it says **SPEC DECISION** and §X.17 lists it again.

Notation: "r2 §n" is the spec section. "→" means "replace with". `UPLOAD_CAP_BYTES`, `JOB_BUSY_TRIES` and similar names are new constants in `core/names.py`.

---

## X.0 What the probe facts change (summary)

| fact (PR) | consequence | sections |
|---|---|---|
| P5: a detached process dies when its tool call ends. A foreground process keeps running across tool calls because the command tool gives back a session the Dot can poll (holds of 1,200 s completed, M003) | no detached worker anywhere. `go` runs every stage in the foreground and the Dot polls until it exits. A second helper command is refused with `HELPER_BUSY`. A same-boot death is `FOREGROUND_DIED`. A reset falls into the existing restore rows. The P5 gate becomes a foreground-hold gate with a stage-time budget | X.1, X.2, X.6, X.7, X.8, X.12, X.13, X.14 |
| P2: no md5 anywhere. FIND returns id, size and createdTime | md5-hidden mode is the default. A copy counts as ours if its size matches and either its id is already recorded or a download-back has the expected sha256 (rule V). This covers commits and also restore, kit, PASS, GENESIS and FINAL. The call budget is restated | X.5, X.8, X.10, X.12 |
| P2: the upload limit is 100 MiB per file, and a 50 MB round trip is proven | hard cap of 90 MiB for any uploaded file, refused before printing. Parts are bounded by the proven round-trip size | X.2, X.3, X.5, X.12 |
| P2: the platform's approval review sometimes refuses uploads. A timed-out upload can still appear | `found --refused`. A refusal never counts as absent until FIND shows the file absent. `STOP UPLOAD_REFUSED HANDBACK A` asks the owner to approve, and the series then resumes. Uploads per file stay bounded at 3. A late copy is a duplicate checked by rule V | X.5, X.6, X.13 |
| P2: `name contains` is not a prefix filter. A folder listing can be newest first by modified time, limited to N | exact-name FIND only. r2 §5.2 is deleted. LIST gives a head hint only | X.5, X.8, X.12 |
| P1: transcripts export only in part. The conversation list carries `attachedAt` | `p1_transcript_export = no` by the owner's O55. `attachedAt` with a clock tolerance decides `list_shows_none` (O58) | X.6, X.8, X.9, X.12 |
| P3: clock sync is unknown. Shell time agreed with Drive within about 1 minute | the helper uses one clock (the VM's). Platform times are compared only through `p3_clock_tolerance_seconds`, and always in the fail-closed direction | X.6, X.8, X.9, X.12 |
| P1: new conversations carry app tools (M006 pending) | no code change. The G attestation reports `web`, `connectors` and `tools=` as observed (the runner records them and does not refuse them: `cps_job.py` FEATURES :88, :1939) | — |
| P2: the Dot can save raw tool results to a VM file | not used by the helper (no format evidence). README advice only: save the raw FIND result before copying ids into `found` | X.6 |

---

## X.1 §0, §1.1, §1.2, §1.3: wording and files

- r2 §0: add "**HANDBACK A**: a STOP that is not sticky. The Dot asks the owner to approve the refused platform action named in the block. When the owner says it is done, the Dot runs `go` (§X.6)." `STOP IDLE` and `STOP ... HANDBACK A` are the only non-sticky STOPs.
- r2 §1.1, bullet 1: "in a detached worker" → "in the foreground of `go` (§X.7.2)". Bullet 2: "md5-confirmed" → "confirmed: md5 and size when `p2_md5_visible == yes`, otherwise size plus a download-back sha256 compare (§X.5.5)". **SPEC DECISION** SD-28 reads O54's "md5-confirmed" as "byte-confirmed". Under P2 the sha256 of the downloaded bytes is the only content check available, and it is stronger than an md5 match.
- r2 §1.2: add `cps.vm2-foreground.v1` (`outbox/v2/FOREGROUND.json`, §X.7.2). The schema `cps.vm2-probe-p5.v1` stays, for the retained `probe_p5.py` (§X.12.5).
- r2 §1.3 file list:
  - `vm2.py`: subcommands `<go|found|answer|audit|assemble|score_check>`. `_worker` is deleted.
  - `cpsvm2/vio/runner.py`: "detached chain execution" → "chain execution in the calling process".
  - `cpsvm2/worker.py`: → "the foreground stage body (chain, snapshot, entry build, PENDING), called in-process by `cli.go`". It still imports core/ and vio/.
- r2 §1.4, §1.5, §1.6 (**SPEC DECISION** SD-34): `spawn` and `worker_alive` leave the reuse list, which goes from 54 to 52 names. REUSE_MANIFEST.json is regenerated and `test_reuse.py` is updated. In `v1compat.py`, `HELPER_FILE` and `wait_block` are deleted. In `v1mod.py`, `cmd_worker` and `wait_block` are deleted, so 6 modified functions remain. In the "Deleted" paragraph, add "spawn, worker_alive, cmd_worker, wait_block: no detached process exists (P5 FAIL)". The modified `cleanup_leftovers` drops its `DETACHED.json`/`worker_alive` check: it runs under the helper lock, after the FOREGROUND check (§X.6.7). The reused `HelperLock.hand_off` stays verbatim and unused (L10 report). The reused `HelperLock`'s inert busy `Block` still names `DETACHED.json` and is never printed.

## X.2 §2.1, §2.2: paths and config

- r2 §2.1 `BASE/outbox/` row: "`.lock` (HelperLock), `DETACHED.json` (spawn), worker logs and results" → "`.lock` (HelperLock); stage logs `outbox/<kind>_<utc14>.log` (runner stdout and stderr appended, never printed)". v2 additions table: add `outbox/v2/FOREGROUND.json` (§X.7.2) and `outbox/v2/dead_<utc14>.json` (a dead self-test's record).
- r2 §2.2 config keys:
  - delete `wrap_foreground_seconds`.
  - add `foreground_hold_seconds` (int, default 1200): the hold the helper relies on. It must be at most `gates.p5_foreground_hold_seconds`, otherwise `RELEASE_GATE_OPEN` (§X.12.1).
  - add `stage_max_seconds` (dict, exact keys `selftest`, `place`, `prepare`, `nonattempt`, `scope-finish`, `finish`, `visual-record`, `interrupt`, `freeze`; int values ≥ 1): the expected upper bound of one foreground stage, keyed by stage kind or by the chain's `first` subcommand. Each value includes the bounded JobLock wait, the snapshot, the entry and part writes, and the sha computations. The builder sets each to 1.5 × the largest time measured on the invented jobs, and the D drill confirms them (§X.15). A missing or extra key is `CONFIG_INVALID`.
  - add `max_upload_bytes` (int, default 94,371,840): the largest file the helper names in an UPLOAD line. `CONFIG_INVALID` if it exceeds `UPLOAD_CAP_BYTES = 94_371_840` (90 MiB, a constant in `core/names.py`; the platform limit is 104,857,600, PR P2).
  - `png_part_bytes`: "1,000,000..`gates.p2_max_upload_bytes`" → "1,000,000..`max_upload_bytes`". `max_entry_bytes`: "at most `gates.p2_max_upload_bytes`" → "at most `max_upload_bytes`".
  - `max_ai_output_bytes` default 100,000,000 → 40,000,000. `max_transcript_bytes` default 50,000,000 → 40,000,000. New rule: `max_ai_output_bytes + max_transcript_bytes + 1,000,000 <= max_entry_bytes`, otherwise `CONFIG_INVALID`. An AI or RESTORE entry carries both inside one upload.
  - Config-only changeable keys: remove `wrap_foreground_seconds`. The new keys `foreground_hold_seconds`, `stage_max_seconds` and `max_upload_bytes` are **not** changeable (a change gives `CONFIG_CHANGE_NOT_ALLOWED`).
  - Default `drive_id_re` stays until the maintainer narrows it from the M004 ids. No other change.

## X.3 §2.3, §2.5, §3.9: cache, validation, size limits

- r2 §2.3 PENDING: `tries` → `{"<name>": {"uploads": int, "finds_since_upload": int, "refused": int, "need": "upload"|"find"|"wait"|"verify"|"done"}}`. The built code already has `need`; `refused` is new. `verify` items get `folder`, as the built code has. BLOCK.json `expect` gets `"uploaded": [names printed in UPLOAD lines of this block]`, which `--refused` validation uses (§X.6.2).
- r2 §2.5: before step 1, under the lock: a `FOREGROUND.json` of this boot → §X.7.2 step 4. A `FOREGROUND.json` of another boot is an invalid cache file: it is moved with the cache to `invalid_<utc14>/` and the restore path follows.
- r2 §3.9 table, new first row: "any file named in an UPLOAD line | `max_upload_bytes` | entry: `HALT ENTRY_TOO_LARGE`; DELIV, DLOG, LEDGER or ALLFZ part: `HALT PART_TOO_LARGE`; a setup or report file (PASS, SELFTEST, kit zip, setup or self-test log or results): `STOP UPLOAD_TOO_LARGE HANDBACK C` (local sticky). The check runs before PENDING is written (journal files) and before the block naming the file is printed." The "one part" row: `png_part_bytes` (≤ `max_upload_bytes`); PNG parts are cut by PartWriter. Lint L12 (§X.14) checks that no UPLOAD line ever names a larger file.

## X.4 §4 (table T)

No row changes. The fold reads only `p1_conversation_list`, `p1_end_after_reset`, `p1_transcript_export` and `p2_lag_seconds` from the genesis gates, and it does not check the gate key set, so deleting and adding gate keys does not touch TABLE. The table golden is regenerated only because the genesis fixtures' `gates` dicts change (a reviewed golden update, r2 §4.8). `confirms` keeps `[id, md5, size]`, where with md5 hidden the md5 is the helper's local md5 of the verified bytes (§X.5.5).

## X.5 §5: commit() under P2

- r2 §5.1 step 5: the ATTEST forms are `--name N (--file ID:SIZE ... | --none) [--refused]` when md5 is hidden, and `(--file ID:MD5:SIZE ... | --none) [--refused]` when md5 is visible. The `--refused` rule is in §X.5.6.
- r2 §5.1 step 6, first bullet ("one or more copies, every copy with the local md5 and size") → "one or more copies: every copy must have the local size (and, if md5 is visible, the local md5), otherwise `STOP FORK`. With md5 hidden the copies then go to §X.5.5 (VERIFY)." The `--none` bullets stay as r2 has them, plus the refused rule of §X.5.6.
- r2 §5.1 step 8: "compute `core.plan.next_action` and print its block" → add "except that `found` and `answer` never start a stage: when the next Step is `RunChain`, `Place` or the self-test, they print `CPSV ... state=WORK` with `DO: RUN bash /home/agent/cps/vm.sh go` (exit 0), and the `go` that follows starts the stage (§X.7.2)". Post actions (evict, unplace, drops) stay in the confirming command. They take seconds.
- **r2 §5.2 (prefix variant) is deleted** (PR P2: `name contains` is not a prefix filter). Every FIND is `FIND <folder> NAME <name>`. Delete every `p2_prefix_search` branch (`savepoint.block`, `savepoint.on_found`), and delete `FakeDrive.find_prefix`.
- r2 §5.3: "DOWNLOAD (md5-hidden variant)" stays allowed before step 8. Add "and the `STOP UPLOAD_REFUSED HANDBACK A` block (§X.5.6)".

### X.5.5 (replaces r2 §5.5) md5 hidden (`gates.p2_md5_visible == 'no'`, the recorded value)

1. found takes `ID:SIZE`. A copy whose SIZE differs from the local bytes is `STOP FORK` at once, with no download.
2. Every other copy whose id is not already recorded for that name (in PENDING `copies`, `STATE.head` or `state.files`) is downloaded back. Phase `VERIFY`. `require_space(sum of their sizes × 1.1)` runs before printing (`HALT DISK_FULL`). The block:
```
CPSV series=Q1 head=000124 kit=0a1b2c3d4e5f at=000124-0009-5e01aa mode=qualification state=SAVE
DOWNLOAD CPS/qualification ID <id> TO /home/agent/cps/inbox/verify/CPSJ_Q1_000125.tgz.1
DOWNLOAD CPS/qualification ID <id2> TO /home/agent/cps/inbox/verify/CPSJ_Q1_000125.tgz.2
DO: RUN bash /home/agent/cps/vm.sh go
```
   (one DOWNLOAD per copy; `.k` numbers the copies in the order they were attested)
3. `go` compares each download's size and sha256 with the local file. All equal: each copy is recorded as `[id, local md5, size]`, and `confirms` keeps r2's shape. Any difference is `STOP FORK`. A missing download is `REFUSED DOWNLOAD_MISSING` (the block is reprinted). Downloads are deleted after the comparison.
4. The entry is verified before its parts are uploaded (r2 §5.1 step 7). Then each part follows steps 1-3.
5. **Rule V** (used everywhere a copy found by name must be checked, §X.8): a copy of name X is *ours* iff its size equals the expected bytes and (its id is recorded for X in the journal or the cache, or its downloaded bytes have the expected sha256). A size difference is `FORK`. A downloaded sha difference is `FORK`, or `LINK_MISMATCH` for N−1 (§X.8.4). The id shortcut trusts that a recorded Drive id still holds the bytes verified when it was recorded. The audit's full download checks that (§X.10).
6. Residual risk, stated: the Dot could copy the local file into `inbox/verify/` instead of downloading. The README forbids it, and the audit's independent full download catches the result. This is the same class of risk as a Dot computing an md5 locally in the md5-visible design.
7. The md5-visible path (r2 §5.1 step 6 with `ID:MD5:SIZE`, no download) stays in the code only behind `gates.p2_md5_visible == 'yes'` and is tested as a variant (§X.14).

**Drive calls (md5 hidden; p = PNG parts, 1-3; one copy per file).** This replaces design §D's numbers for this platform. Each file costs UPLOAD 1 + FIND 1 + DOWNLOAD 1 = 3.

| item | calls |
|---|---|
| normal Q run (prepare STAGE, AI-G, finish STAGE + p, AI-V, FROZEN) | 15 + 3p = 18-24 |
| OPENED commits | 0 (`p1_conversation_list = yes`, OPENED unused) |
| scope run (AI-S, scope-finish STAGE) | +6 |
| REVIEW_INCOMPLETE (STAGE, AI) | +6 |
| everyday (INPUTS, prepare, AI-G, finish + p, AI-V, deliver STAGE, DELIVERY + 2 profile parts, FROZEN) | 30 + 3p = 33-39 |
| restore with a Dot hint: kit 2, PASS 2, FIND N 1, DOWNLOAD N 1, FIND N+1 ×2, FIND N+2 1, FIND N−1 1, head parts FIND 0-3 + DOWNLOAD 0-3, earlier FROZEN 0-1, RESTORE commit 3 | 13-20 |
| restore with a listing hint (§X.8.4) | the row above + LIST 1 + re-check 3 (+0-2 gallop) |
| restore with neither | about 2·log2(N) + 16 |
| each further copy of a name not known by id | +1 DOWNLOAD |
| each refused upload (§X.5.6) | +3 (FIND, FIND, UPLOAD) plus the owner's approval time |

Qualification overall: about 1,650-2,250 calls (r2's 1,100-1,500 × 1.5), about 9-12.5 h at 20 s per call. Downloading back about 19 GB at the measured rate (50 MB in about 8 s, PR P2) adds about 1 h. OP-07's test numbers become: normal run ≤ 24 with 3 PNG parts, scope +6, REVIEW_INCOMPLETE +6, restore with a hint ≤ 20. The md5-visible variant keeps r2's numbers.

### X.5.6 (new) Refused, failed and timed-out uploads (PR P2)

1. The Dot carries out every UPLOAD line once and never retries one itself. It then carries out every FIND line of the block, whatever the upload returned (success, timeout, error or refusal).
2. `--refused` may follow `--name N` only when N is in `BLOCK.expect.uploaded`, otherwise `REFUSED FOUND_SYNTAX`. It means that the platform refused that upload (its approval review, or any refusal message). The Dot does not use it for a timeout or an error.
3. `--refused` with copies: the copies are checked as in step 6 and §X.5.5. The refusal is only counted.
4. `--refused` with `--none`: `refused += 1`, `need = find`, `finds_since_upload = 0`. PENDING is written durably, then the block prints `DO: STOP UPLOAD_REFUSED HANDBACK A` (exit 3, not written to HALT.json). The Dot tells the owner the code, the file name and the CPSV line, and asks the owner to approve the refused upload in the platform. It runs `go` when the owner says the upload is approved, or tells it to continue.
5. The next `go` prints **FIND first, never UPLOAD**: an approved call may have landed. The r2 loop then applies. If the FIND shows none, the helper prints `WAIT w`. If the second FIND, `w` later, also shows none, the file is uploaded again (`uploads += 1`). After the third upload's two absences, refused or not, the result is `STOP UPLOAD_FAILED HANDBACK C` (sticky). So a name causes at most 3 uploads and 3 `UPLOAD_REFUSED` stops.
6. A timed-out or refused upload that lands later is one more copy with our bytes. During the commit it is checked by §X.5.5. After the commit, every later exact-name FIND of that name meets it as an unknown id and checks it by rule V. The audit treats same-sha duplicates as harmless (§X.10). `p2_failed_upload_can_appear = yes` therefore changes nothing in r2 §12.2 beyond this section.
7. The same loop serves the setup files (PASS, SELFTEST, kit zip) and report uploads.
8. A DOWNLOAD that the platform refuses is not reported. The block is reprinted after `REFUSED DOWNLOAD_MISSING`. The README tells the Dot to get the owner's approval and then download again. No code change.

## X.6 §6: operator surface

### X.6.1 r2 §6.1 (the rule for the Dot), additions
- "Run every helper command in the foreground. If the command tool returns a session before the command has exited, poll **that same session** until the process exits. Start no other helper command meanwhile. A helper command may run up to `foreground_hold_seconds` (1,200 s)."
- "A command's result is its last block: from the last line that starts with `CPSV ` through the `DO:` line, which is always the last line. If the process exited and no `DO:` line follows the last `CPSV ` line (or there is no `CPSV ` line), run `go` once. If that happens again, hand back case C with the code `NO_BLOCK`." (`NO_BLOCK` is an operator handback word, not a helper code, as with `SESSION_NO_COMMIT`.)
- Start line: a `go` that starts a stage prints one line before anything else, flushed at once:
  `CPSV-RUNNING kind=<selftest|place|chain|setup> since=<UTC_S> max=<seconds>`
  It names no run, case or result (O54). `session_start.sh` prints the same line with `kind=setup max=600` before setup.
- Block grammar (r2 §6.1): delete the forms `FIND <folder> PREFIX <prefix>` and `LIST <folder> PREFIX <prefix> NEWEST <k>`. The allowed forms are `FIND <folder> NAME <name>` and `LIST <folder> NEWEST <k>` (§X.8.4).
- "Exact-name search: report every copy over every result page (follow page tokens). Report SIZE exactly as the search shows it, in bytes."
- "Times you attest (`started_utc`, `ended_utc`, `opened_utc`) are VM clock readings: run `date -u +%Y-%m-%dT%H:%M:%SZ` on the VM just before you send the prompt, and again right after you see the conversation end. Never copy a time from the conversation list or from Drive." (§X.9)
- "To avoid copying slips, save the raw FIND result to a file first, then copy the ids from that file."

### X.6.2 r2 §6.2
- `found --at <at> (--name <N> [--refused] (--file <F> ... | --none))+`, where `<F>` is `ID:SIZE` (md5 hidden) or `ID:MD5:SIZE` (md5 visible). The LIST answer is `found --at <at> (--file <name>:ID:SIZE ... | --none)` (md5 hidden), with every file the listing returned.
- **Busy (P5).** HelperLock not acquired within 10 s (another helper command holds it): the command reads `outbox/v2/FOREGROUND.json` without the lock (an unreadable or absent file gives `none`), changes nothing, and prints exactly:
```
CPSV-BUSY kind=<kind|none> since=<UTC_S|none>
REFUSED HELPER_BUSY
DO: POLL
```
  Exit 4. This applies to `go`, `found` and `answer` alike.

### X.6.4 r2 §6.4, terminal actions
- add `POLL`: the Dot goes back to the command session that runs the helper, polls it until the process exits, then follows that command's block. If the Dot no longer has that session, it uses `WAIT seconds=60`, then `RUN go`. That `go` either prints the current block or stops with `FOREGROUND_DIED`. A lost SAVE block heals itself: its UPLOAD was counted, so the next block FINDs, waits and re-uploads within r2's bound.
- add `STOP UPLOAD_REFUSED HANDBACK A`: §X.5.6 step 4. Then `RUN go`.
- `ATTEST` gets an optional qualifier: `ATTEST after=<UTC_S> bash /home/agent/cps/vm.sh answer --at A k=P ...`. With it, `list_shows_none=yes` means that the conversation list shows **no** conversation with `attachedAt` at or after that time, and `conversation=` is the id of the conversation with `attachedAt` at or after that time that was opened for this role. The qualifier is printed on every restore ATTEST whose keys include `list_shows_none` or `conversation` (r2 §6.5 restore rows and the C5 rebase question). Its value is `T = latest(role).utc − gates.p3_clock_tolerance_seconds` (§X.9).
- `END_CONVERSATION role=R after=UTC`: `after` is the same `T`.
- `WAIT seconds=60` while setup runs is gone (§X.6.6).

### X.6.5 r2 §6.5
No change of keys. With `p1_transcript_export = no` the answer `transcript=` is always `not_available` (§X.9). The restore rows that ask `list_shows_none` or `conversation` carry `after=T` (§X.6.4).

### X.6.6 r2 §6.6 (session_start.sh): setup in the foreground
- Order: steps 1, 2, 3, **5** (write `vm.sh` and the hint), then 4, then 6. `vm.sh` already sources `TOOLS/env.sh` only if it exists.
- Step 4 → "Setup: if `TOOLS/var/cps_vm2_setup_ok` does not hold `<boot_id> <commit>`, print `CPSV-RUNNING kind=setup since=<UTC_S> max=600`, then run `setup_vm_user.sh` (with `CPS_WITH_LIBREOFFICE=host`) and `check_env.py` **in the foreground**, with output to `outbox/setup_<utc14>.log`. On success (all_met true), write the ok marker. Otherwise write `TOOLS/var/cps_vm2_setup_failed` (`<boot_id> <commit>`). Either way continue to step 6 (`DO: RUN ... go`)." `setsid`, `nohup`, `&` and `SETUP.json` are deleted (SAFE-07: setup takes 119-130 s, PR Phase 1, well inside the hold).
- r2 §6.6 last paragraph and §8.1 step 2 → "`go` step 2: ok marker for this boot and commit → continue. Failed marker → the existing log upload (setup-file loop) to `CPS/reports`, then `STOP SETUP_FAILED HANDBACK C`. Neither marker → `STOP SETUP_FAILED HANDBACK C` with detail `not_done` (the Dot's rule in §X.6.1 re-runs a killed `session_start.sh`, so `go` never waits for setup)."

### X.6.7 r2 §6.7 (the `go` dispatcher) →
```
go():
  lay = Layout(); check_layout_basic(lay)
  with HelperLock(lay, wait=10):                 # busy -> the CPSV-BUSY block, exit 4 (§X.6.2)
    if FOREGROUND.json: §X.7.2 step 4            # dead stage of this boot: STOP, or self-test retry
    cleanup_leftovers(lay)                       # modified; no DETACHED check
    if HALT.json: clear per §13.5 or print its STOP block
    validate cache (§2.5) -> invalid: session/restore machine (§8)
    if not session ready for this boot: session machine (§8.1-8.3)
    if PENDING: continue the commit (§5.1 steps 5-7, §X.5.5, §X.5.6)
    step = core.plan.next_action(view(STATE, local facts, now))
    carry out step: print block | commit | run the stage in the foreground (§X.7.2), then print its block
```
`found` and `answer` run the same prologue, apply their values, and end with a block. They never run a stage (§X.5 step 8).

### X.6.8 r2 §6.8 README
Add the rules of §X.6.1, POLL, HANDBACK A, the `after=` meaning, the `--refused` rule, and the VM-clock rule for attested times. Add every new example value to `doc_samples`.

## X.7 §7: stages

- r2 §7.1 `view.local`: "worker state" → "foreground state (FOREGROUND.json present or not)". Rows 12-15 and 20-21 return `RunChain`. Executed from `found` or `answer`, they become the `RUN go` block (§X.5 step 8).

### X.7.2 (replaces r2 §7.2 "The detached worker") The foreground stage
1. Only `go` starts a stage. Kinds: `chain` (runner commands, then snapshot, entry draft and commit steps 1-4), `selftest` (reused `selftest_work`), `place` (§8.5.1). GENESIS and FINAL builds run inline in `go`, take seconds, and print no RUNNING line.
2. `go` keeps HelperLock for the whole stage. It writes `outbox/v2/FOREGROUND.json` with `durable.write` (`{"schema": "cps.vm2-foreground.v1", "kind", "run" | null, "first" | null, "attempt": 1 | 2, "boot_id", "pid", "started_utc", "max_seconds", "self_sha256"}`, where `max_seconds = stage_max_seconds[first or kind]`). It then prints the RUNNING line (§X.6.1) and runs the body in-process. The body is r2 §7.2 step 3 unchanged: fingerprint re-check, JobLock probe, consumer measurement, chain through the reused `run_runner` with the log `outbox/<kind>_<utc14>.log`, snapshot, entry draft, commit steps 1-4. Two exceptions:
   - JobLock probe and chain row X2 (runner `JOB_BUSY`): up to `JOB_BUSY_TRIES = 5` tries `JOB_BUSY_GAP_SECONDS = 30` apart (instead of 60 × 60 s), then `STOP JOB_BUSY_TOO_LONG HANDBACK C`. A lock holder can only be a process of this boot that outlived a dead stage, which already stops (step 4).
   - The result `{"status": "pending" | "halt" | "done" | "fingerprint", "code", "detail"}` is returned in memory. There is no `out` file.
3. On return, of any status: unlink `FOREGROUND.json` and fsync `outbox/v2/`. Then absorb the result as r2 §7.2 step 4 and print the block (for `pending`, the SAVE block of commit step 5). FOREGROUND.json is removed only on this path, never in a `finally`. The body catches `Halt` and `OSError` only, never `BaseException`.
4. A FOREGROUND.json found under the lock means its writer is dead (the lock is free) in this boot. Kind `selftest` with `attempt` 1: move the file to `outbox/v2/dead_<utc14>.json` and run the self-test again with `attempt` 2. Otherwise: local sticky `STOP FOREGROUND_DIED HANDBACK C`, or `STOP SELFTEST_DIED HANDBACK C` for a self-test at attempt 2. The job folder is left untouched for the maintainer. (Renames r2's `WORKER_DIED`, `SELFTEST_WORKER_DIED`.) A stage killed by the platform for exceeding the hold ends here.
5. The reused `run_runner`'s 7,200 s timeout is not the bound. The hold is. A runner command that outlives the hold either completes (the hold is not proven to be a hard limit) or ends in step 4.

**What a VM reset during a foreground stage leaves, and how the existing restore path classifies it** (no new row). r2's worker points WP1-WP4 become FP1-FP4. Nothing of the stage is on Drive, because the SAVE block is printed only after the stage, and the header is outcome-neutral:

| stage | after the reset | r2 row |
|---|---|---|
| setup (session_start.sh) | `~/cps*` empty; the Dot runs the bootstrap again (PR: reset recovery 130 s) | §6.1 |
| self-test | no PASS on Drive for the fingerprint | §8.3: self-test again |
| place (in a restore) | nothing committed (the RESTORE follows placement) | §8: the session starts again from the top |
| GENESIS build | head search finds nothing | §7.12 again (`BASE/ledger` is gone) |
| chain creating a new Q run (prepare, nonattempt) | the run is absent from the head state | C9: the plan picks the same next run; nothing was shown, so the re-run is unbound |
| everyday prepare | run in status `INPUTS` | C8b: `reprepare` once, then `abandon` (O49, O60) |
| chain of an existing run (scope-finish, finish, visual-record (+freeze, verify-frozen, or deliver-check), freeze, rebase re-run) | head is the last committed entry of the run, ACTIVE, nothing open | C8: PLACE, unbound re-run, `rerun_expected`, flag `RERUN_UNBOUND` (O44, O54); a rebase head goes through C5b first |
| interrupt, or a FREEZE_* action of a committed RESTORE | head is that RESTORE, action not run | C8, then §7.1 rows 12-13 run it |
| FINAL build | head is the last FROZEN, no run left | C9, then FINAL again |
| after the stage, during its commit | — | CP1-CP10 as in r2 |

### X.7.3 r2 §7.3
Row X2: "bounded with the JobLock probe" → "up to 5 tries 30 s apart (§X.7.2)".

### X.7.4 r2 §7.4
No change. The `interrupt --started-utc` and `--ended-utc` values are VM-clock times (§X.9).

### X.7.5 r2 §7.5
With `p1_transcript_export = no`, the record always has `transcript_status = not_available` and the fixed reason, and `finish` never gets `--transcript`.

## X.8 §8: session and restore under P2

- r2 §8.1 step 2: as in §X.6.6. Step 7's codes are unchanged. Step 9 follows §X.8.3.
- r2 §8.2 (kit intake): "Several copies: they must share one md5 (else STOP FORK)" → "they must share one size (else `STOP FORK`). The first attested copy is downloaded. Its full sha256 must start with kit12 and, after step 7, equal `head.kit_sha256` or pass step 11 (`STOP KIT_NOT_VERIFIED` otherwise). Other copies are not downloaded: they cannot change which bytes are used." The same applies to the head-kit fetch (KIT_CHANGE) and to `FOLDER_MANIFEST.md`.
- **r2 §8.3 (PASS):** with md5 hidden there is no shortcut. Every copy of `FINGERPRINT_PASS_<fp64>.json` (normally one) is downloaded and validated (`validate_pass`). The accepted copy is recorded with its local md5 and size (+1 call per restore). r2 SD-16's "accepted by known md5 without download" holds only when md5 is visible.

### X.8.4 r2 §8.4 head search
- Step 1 →
  - with a Dot hint h > 0: as r2.
  - else with `gates.p2_newest_first == 'yes'`: `LIST <series folder> NEWEST 10` (`LIST_NEWEST_K = 10`). The Dot answers with every returned file (§X.6.2). The helper keeps the names that match ENTRY for this series. Candidate h = their largest seq; none matching means no candidate. **The candidate is a hint only.** Listed rows are never lookups: presence and absence come only from exact-name FINDs (the built `session.head_search` adds listing rows as present lookups; this is removed). FIND h. Present: gallop up from h as with a Dot hint. Absent twice (`w_abs` apart): gallop from 1. (This is not `HINT_AHEAD`: a listing by modified time is not the Dot's record.)
  - else: gallop from 1, as r2.
- Step 1, "present(k) ... all one md5; two md5s: FORK" → "all one size; two sizes: `FORK`". A copy of an intermediate k is never downloaded.
- Step 3 (download N): one `DOWNLOAD ... TO BASE/inbox/journal/<name>.<k>` per copy of N. All copies must be byte-identical (else `STOP FORK`). Copy 1 is the head. Its local md5 goes into `RESTORE.body.head.md5`.
- Step 4 (link) → "every copy of N−1 must be ours by rule V (§X.5.5), with expected bytes = `N.confirms[0].copies[*].size` and expected sha256 = `N.prev_sha256`. Copies whose id is in `N.confirms[0].copies` need no download. Any other copy is downloaded to `inbox/verify/`. A failure is `STOP LINK_MISMATCH`." The built code compares md5s, and every md5 is `None` when md5 is hidden, which gives `LINK_MISMATCH` every time. This bug is fixed by this rule.
- Step 5 (head parts): a present copy must have the size `N.parts[].bytes` (else `FORK`). It is downloaded to `BASE/inbox/journal/<name>.<k>` and its sha256 compared with `N.parts[].sha256` (else `FORK`). The download is kept and reused by placement (§8.5.1 step 3) with no second download. The two-absence rule is unchanged.
- Step 6 (re-check): "when the head was found neither from a hint nor from a newest-first listing" → "when the head was not found from a Dot hint (a listing hint does not exempt it)". "must show exactly the RESTORE's own md5" → "every copy must be ours by rule V (the RESTORE's ids are known; an unknown id is downloaded and compared with the RESTORE's sha256)".
- The RESTORE commit's own FIND of N+1 (end of r2 §8.4) and the GENESIS commit's FIND (r2 §7.12, "exactly one md5") → "every copy is ours by rule V". A foreign copy is `FORK`.
- r2 §8.5: C3 and C4 decide "part present" by rule V (recorded id in `state.files` means present without download). C5 decides "missing" by two absences (as r2) and "present" by §X.8.4 step 5. The C5 `list_shows_none` question carries `after=T` (§X.6.4).
- r2 §8.5.1: "(in a worker of kind `place`)" → "(a foreground stage of kind `place`, §X.7.2)". Step 3 reuses the step-5 downloads.
- r2 §8.6 step 1: "Without OPENED the Dot finds the conversation in its list after the START's utc" → "... with `attachedAt` at or after `T` (§X.6.4)". Step 4 (EXPORT_TRANSCRIPT) never fires (`p1_transcript_export = no`). Step 5's ATTEST carries `after=T`. T43 SUPERSEDE requires `list_shows_none=yes` read against T (O58).

## X.9 Clocks (P3: synchronisation unknown) and transcripts (P1)

**Clock tolerance rules (SPEC DECISION SD-33).**
1. One clock decides: the VM clock. Every UTC the helper writes (entries, START `utc`, interrupt times, windows) and every attested UTC (`started_utc`, `ended_utc`, `opened_utc`, taken by the Dot from the VM's `date -u`, §X.6.1) is a VM-clock time. The r2 §6.3 windows stay exact, with no tolerance. So the runner's R21 window holds, because both sides are on the VM clock.
2. Platform times (conversation `attachedAt`, Drive `createdTime`) are never attested as times and never stored in state. They meet a VM time only through the gate `p3_clock_tolerance_seconds` (int, default 300, which is 5 × the agreement of about 1 minute seen in P3). They are always used in the fail-closed direction: `T = latest(role).utc − tolerance`, so a conversation started near the START counts as "after" it, `list_shows_none` becomes harder to answer `yes`, and NO_CONVERSATION and a REBASE supersede become harder to obtain.
3. Drive `createdTime` is read only by the audit (r2 §10.1 step 6, `audit_clock_tolerance_seconds` default 600, reported). The helper never reads it.
4. Across VMs, the reused `clock_check(floor=head.utc)` is unchanged (`CLOCK_WAIT` up to `clock_wait_max_seconds`, then `CLOCK_BEHIND`).
5. r2 §9.3 O52 sheet: each row's `window` widens to `[start_utc − tol, end + tol]`. The sheet records `clock_tolerance_seconds` (from `state.genesis.gates`). The owner compares the list's `attachedAt` values with the widened windows.
6. The tolerance is a gate, recorded in GENESIS (`GATES_CHANGED` if a kit changes it within a series).

**Transcripts.** O55 is the owner's decision for this platform. PR P1 says the Dot can read a conversation's recorded messages and turn status, but not every tool execution and file written. That is not "a transcript, with its file writes" (r2 §12.1), so `p1_transcript_export = no`. r2 §12.2's "P1 transcript export no" row applies exactly as written:
- no EXPORT_TRANSCRIPT block (r2 §7.1 row 8 and §8.6 step 4 never fire);
- in Q, S/G NOTHING_WRITTEN gives INTERRUPT with OWNER_CHECK (T44, O55), and V NOTHING_WRITTEN gives REPLACE with OWNER_CHECK (SD-22, OQ-11);
- in E, FREEZE_LOST and FREEZE_VISUAL_FAILED;
- scoring waits for OWNER_CHECKS.json (r2 §9.5).

The README says the Dot's NOTHING_WRITTEN reading is made from the conversation's recorded messages and turn status. O56's `transcript/` members are absent because nothing is exported. Whether the Dot should also save the recorded messages as failure evidence is OQ-16. No code path depends on the answer. If M006 shows a full tool-call log, a gate value of `yes` needs a new series (`GATES_CHANGED`).

## X.10 §10 maintainer side

r2 §10.1, the audit: when the maintainer's listing has no `md5Checksum`, step 1 (duplicates), step 2 (`confirms`, parts present) and the rebase rules compare size and the sha256 of the downloaded bytes. `--dir` holds every copy, keyed by id. Copies of one name with one sha256 are harmless duplicates. Two sha256s for one name is `AUD_DUPLICATE_SEQ`. The audit's full download is the independent check behind rule V's id shortcut and §X.5.5 step 6. No new audit code.

## X.11 §11 everyday

No change beyond what applies everywhere. The DELIV and DLOG parts follow §X.5.5 and §X.5.6 in the profile folder. The DELIVER copy limit stays at `png_part_bytes` (≤ `max_upload_bytes`). An interrupted everyday S, G or V fails under `transcript=not_available`, as r2 §11.4 already says.

## X.12 §12: probe dependencies and release gates

### X.12.1 r2 §12.1 gates
- Deleted: `p2_prefix_search`, `p5_detached`, `p5_tool_call_seconds`.
- Added: `p5_foreground_hold_seconds` (int or null: the longest polled foreground hold that completed, M003), and `p3_clock_tolerance_seconds` (int or null, §X.9).
- Redefined: `p2_exact_search` "returns every copy with id and size, and md5 if visible". `p2_newest_first` "a folder listing newest first by **modified** time, limited to k; a head hint only". `p2_max_upload_bytes` keeps r2's meaning, "the largest file that uploaded and downloaded back with equal sha256", and is never above 104,857,600.
- Values for the kit, from PR. The maintainer records the exact numbers from the M00n replies:

| key | value | evidence |
|---|---|---|
| p1_vm_files | PASS | M002 |
| p1_transcript_export | no | P1 partial; O55 (owner) |
| p1_conversation_list | yes | list with `attachedAt` |
| p1_end_after_reset | yes | turn status readable, archive stops a conversation; behaviour across a forced reset untested (PR "not yet known") |
| p2_exact_search | PASS | every copy, distinct ids, immediate |
| p2_md5_visible | no | M004 |
| p2_newest_first | yes | listing limited to newest N by modified time |
| p2_lag_seconds | 0 | 20/20 found at once |
| p2_max_upload_bytes | the 50 MB round trip's exact byte count | M004 (a 200 MB upload failed with 413) |
| p2_tgz_kept | PASS only if the M004 round trips included `.tgz`/`.part`/`.jsonl`; otherwise OPEN until shown | "raw files, no conversion, names kept" |
| p2_failed_upload_can_appear | yes | M004 |
| p3_identity_stable | yes | M005 real reset, same `/home/agent`, uid 1000 (confirm from M005) |
| p3_clock_tolerance_seconds | 300 | P3 about 1 minute |
| p5_foreground_hold_seconds | 1200 | M003 |
| p5_setup_seconds | 130 | Phase 1 / M005 |

- **Release gates** (r2 §12.1 paragraph). Replace `p5_detached == PASS` and `wrap_foreground_seconds + 60 <= p5_tool_call_seconds` with:
  - `foreground_hold_seconds <= p5_foreground_hold_seconds`;
  - `p5_setup_seconds + 60 <= foreground_hold_seconds`;
  - `stage_max_seconds[k] + 60 <= foreground_hold_seconds` for every key k.

  Replace `png_part_bytes <= p2_max_upload_bytes` and `max_entry_bytes <= p2_max_upload_bytes` with:
  - `max_upload_bytes <= min(UPLOAD_CAP_BYTES, p2_max_upload_bytes)`;
  - `png_part_bytes <= max_upload_bytes`;
  - `max_entry_bytes <= max_upload_bytes`.

  A failure is `STOP RELEASE_GATE_OPEN HANDBACK C` naming the keys (for example `p5_foreground_hold_seconds`, `stage_max_seconds.finish`). The stages that must fit the hold are: setup, self-test (r2 measured 12 min 57 s, CURRENT_STATUS.md:38, about 780 s), place, prepare, nonattempt (+freeze, verify-frozen), scope-finish, finish (saved QA and two LibreOffice renders, "minutes", RUN_JOB_COMMANDS.md), visual-record (+freeze and verify-frozen in Q/D, or +deliver-check in E), interrupt (+freeze, verify-frozen), freeze (up to 2 retries, then verify-frozen), and a rebase re-run (the same key as the head chain's `first`).

### X.12.2 r2 §12.2 rows
- delete "P2 prefix search yes/no" and "P5 detached PASS/FAIL".
- add "P5 foreground hold H | every stage runs in the foreground of `go` (§X.7.2). The release gate requires every stage budget + 60 ≤ `foreground_hold_seconds` ≤ H. A stage that is killed is `FOREGROUND_DIED` (C)".
- "P2 md5 visible no" → "found takes `ID:SIZE`, rule V everywhere (§X.5.5, §X.8). This is the recorded value."
- "P2 newest-first yes" → "a head hint from `LIST <folder> NEWEST 10`, then the hint gallop and the step-6 re-check (§X.8.4)".
- "P2 failed upload can appear yes" → "§X.5.6".
- "P2 max upload B" → "§X.3. Every UPLOAD ≤ `max_upload_bytes` ≤ min(90 MiB, B)".
- P1 rows: as §X.9 (`after=T`).

### X.12.4 r2 §12.4
Measured: 50 MB up in about 12 s and down in about 8 s. A round trip at `max_upload_bytes` (90 MiB) is not yet shown (OQ-17).

### X.12.5 r2 §12.5
`probe_p5.py` stays as built. It is admitted separately and is now the record of how P5 is re-measured on another platform: `hold` measures `p5_foreground_hold_seconds`. Its verdict gates nothing.

## X.13 §13 codes (every change; `core/names.py` CODES follows)

| change | code | class | raised in |
|---|---|---|---|
| renamed from `WORKER_DIED` | `FOREGROUND_DIED` | STOP, local sticky, C | §X.7.2 step 4 |
| renamed from `SELFTEST_WORKER_DIED` | `SELFTEST_DIED` | STOP, local sticky, C | §X.7.2 step 4 |
| added | `UPLOAD_REFUSED` | STOP, **not sticky**, HANDBACK A | §X.5.6 step 4 |
| added | `UPLOAD_TOO_LARGE` | STOP, local sticky, C | §X.3 (setup or report file over `max_upload_bytes`) |
| changed behaviour | `HELPER_BUSY` | REFUSED (exit 4, the CPSV-BUSY block) | §X.6.2; r2 §13.1's "printed as WAIT" no longer holds for it |
| changed detail | `RELEASE_GATE_OPEN` | STOP | names the new gate keys (§X.12.1) |
| changed bound | `JOB_BUSY_TOO_LONG` | STOP | after 5 × 30 s (§X.7.2) |
| deleted | none | — | — |

`JOB_BUSY` (reused JobLock) is never printed. It is retried inside the stage. r2 §13.1's last paragraph becomes "`JOB_BUSY` is retried inside the foreground stage (§X.7.2); `HELPER_BUSY` prints the CPSV-BUSY block". The r2 §13.2 row "`WORKER_DIED`, `SELFTEST_WORKER_DIED` | §7.2, §8.3" becomes "`FOREGROUND_DIED`, `SELFTEST_DIED` | §X.7.2". Add the rows `UPLOAD_REFUSED` (§X.5.6, non-sticky) and `UPLOAD_TOO_LARGE` (§X.3). `NO_BLOCK` (§X.6.1) and the probe's `SAME_CALL`/`TOO_EARLY`/`OTHER_BOOT` are not helper codes. The `names.py` edit: in `CODES_STOP`, replace `WORKER_DIED SELFTEST_WORKER_DIED` with `FOREGROUND_DIED SELFTEST_DIED` and add `UPLOAD_REFUSED UPLOAD_TOO_LARGE`. Add the constants `UPLOAD_CAP_BYTES`, `LIST_NEWEST_K`, `JOB_BUSY_TRIES` and `JOB_BUSY_GAP_SECONDS`. In `host.GATE_VALUES`, delete the three gate keys and add the two new int keys.

## X.14 §14 tests

- r2 §14.2 World: "the worker is a real detached subprocess (spawn)" → "stages run in-process in `go`. A reset inside a stage is injected through test seams: `fakes.py` replaces `vio.runner.run_runner`, the placement steps and `vio.durable.write` in-process (as for `vio/host.now`) with wrappers that raise `fakes.Reset(BaseException)` at the chosen call. FakeDot catches it and calls `reset()`. The shipped code has no switch." FakeDot runs each helper command to completion (the poll model) and never starts a second one, except in the busy test. FakeDrive: remove `find_prefix`; `list_newest(folder, k)` by modified time; md5 hidden by default (`hide_md5` on); new knobs `refuse_upload(k)` (the k-th upload is refused and lands after `approve()` or never) and `late_appear` after a timeout (already present).
- r2 §14.3 Tier A: WP1-WP4 → FP1-FP4 (same points). The visibility outcomes are: lag within the waits, lag beyond both waits, duplicate with the same bytes, foreign bytes with the same size, foreign size, missing part, refused upload, late appearance after a timeout. That gives 8 × 4 × 6 = 192 (instead of 144), about 570 scenarios. The md5-visible variant runs on one representative stage kind across all outcomes.
- r2 §14.4: `test_safe07_setup_runs_detached_and_gate_uses_tool_call_limit` → `test_safe07_setup_runs_foreground_and_gate_uses_hold`. OP-07 uses the numbers of §X.5.5. New tests, Tier A unless marked:
  `test_p5_no_detached_process` (L11);
  `test_helper_busy_second_command_refused` (real subprocess: a `go` held in a slow stage; a second `go`, `found` and `answer` each exit 4 with the CPSV-BUSY block, and every cache file is byte-identical);
  `test_foreground_died_same_boot_stops` (real subprocess SIGKILL mid-chain: the next `go` gives `STOP FOREGROUND_DIED`, job folder untouched);
  `test_selftest_died_retried_once_then_stops`;
  `test_found_and_answer_never_run_a_stage`;
  `test_running_line_then_block_grammar`;
  `test_reset_in_foreground_stage_classified` (each §X.7.2 table row);
  `test_md5_hidden_link_by_id_or_download` (including an unknown-id N−1 copy with foreign bytes: LINK_MISMATCH);
  `test_md5_hidden_head_copies_all_downloaded_fork_on_difference`;
  `test_md5_hidden_head_part_download_reused_by_placement`;
  `test_md5_hidden_pass_downloaded_and_validated`;
  `test_upload_cap_refused_before_print` (entry, DELIV part, setup file);
  `test_config_upload_and_stage_budget_invalid`;
  `test_gate1_foreground_hold_gate`;
  `test_refused_upload_stops_then_find_before_reupload`;
  `test_refused_three_uploads_then_upload_failed`;
  `test_refused_flag_on_name_not_uploaded_is_found_syntax`;
  `test_timed_out_upload_lands_late_duplicate_verified`;
  `test_listing_is_hint_only_recheck_runs`;
  `test_listing_candidate_absent_gallops_from_one`;
  `test_attest_after_threshold_includes_tolerance`;
  `test_o52_sheet_windows_widened`.
- r2 §14.6 lints:
  - L1: the code changes of §X.13.
  - L5: the RUNNING line and the CPSV-BUSY block are grammar forms; no `PREFIX` form exists.
  - new L11: AST scan of `deploy/vm2/**/*.py` except `probe_p5.py` and `tests/`. Forbidden: `subprocess.Popen`, `os.fork`, `os.setsid`, `os.spawn*`, `os.daemon`, `start_new_session`, `preexec_fn`, `multiprocessing`, and any `threading` use. A text scan of `session_start.sh` forbids `setsid`, `nohup`, `disown`, and any line ending in a bare `&`.
  - new L12: every UPLOAD line of the suite names a file of at most `max_upload_bytes` (the harness records sizes).
- r2 §14.7 mutants, new:
  G24 a chain started with `start_new_session=True` and the WAIT block printed (killed by L11 and `test_foreground_died_same_boot_stops`);
  G25 HELPER_BUSY turned into a WAIT that then takes the lock (`test_helper_busy_second_command_refused`);
  G26 md5-hidden copy accepted on size alone (TST-04, `test_md5_hidden_link_by_id_or_download`);
  G27 `--refused --none` re-uploads at once (`test_refused_upload_stops_then_find_before_reupload`);
  G28 upload cap check removed (`test_upload_cap_refused_before_print`, L12);
  G29 listing rows taken as present lookups, step 6 skipped (`test_listing_is_hint_only_recheck_runs`);
  G30 `after=` without the tolerance (`test_attest_after_threshold_includes_tolerance`);
  G31 FOREGROUND.json removed in a `finally` (`test_foreground_died_same_boot_stops`).

## X.15 §15, §17: budgets, admission, decisions, questions

- r2 §15.1: `worker.py` loses the spawn and result-file handshake. `v1mod.py` drops `cmd_worker` and `wait_block` (about −90 lines). `savepoint.py` drops the prefix branches. `session.py` gains rule V (about +40). Tests gain about +350 lines.
- r2 §15.2 step 2: P1, P2/M004, P3 and P5/M003 are answered (PR). M006 (isolation, tool-call log, models, approvals) is pending and no gate depends on it. Step 8 (drill): the drill also records the longest time of every `stage_max_seconds` key on the Dot's VM, round-trips one file of `max_upload_bytes`, and exercises one refused upload if the platform produces one.
- r2 §17.1, new SPEC DECISIONS:
  - SD-27: foreground stages; `found`/`answer` never run a stage; `HELPER_BUSY` refusal block; `FOREGROUND_DIED`; the hold gate with stage budgets.
  - SD-28: O54's "md5-confirmed" is read as byte-confirmed by a download-back sha256 when md5 is hidden; rule V with the recorded-id shortcut.
  - SD-29: 90 MiB cap on every upload, bounded by the proven round trip.
  - SD-30: refused uploads give `--refused` and a non-sticky `STOP UPLOAD_REFUSED HANDBACK A`, FIND before any re-upload, and at most 3 uploads.
  - SD-31: prefix search deleted; the listing is a head hint only and the step-6 re-check applies.
  - SD-32: `attachedAt` against `T = START utc − tolerance`, printed as `ATTEST after=T`.
  - SD-33: one clock (VM); attested times from the VM's `date -u`; the tolerance gate in the fail-closed direction.
  - SD-34: `spawn` and `worker_alive` leave the reuse list; `cmd_worker` and `wait_block` deleted.
  - SD-16 gets the qualifier "md5 visible only".
  - The design's statements "go runs the next stage in a detached worker" (design §A/B) and "P5: detached stages and setup" (design §F) are superseded by P5 FAIL. This is reported to the admission review.
- r2 §17.2: OQ-3 is closed (P5 answered: detached FAIL, a foreground hold of 1,200 s). OQ-10 is closed (lag 0; the waits stay). New:
  - OQ-16 (owner, O56): should the Dot save a resolved conversation's recorded messages and turn status (the partial record) into the RESTORE entry as failure evidence? Default: no; no decision uses it.
  - OQ-17 (maintainer): a 90 MiB round trip is not yet shown. Until it is, `p2_max_upload_bytes` is the proven 50 MB size, so `max_upload_bytes`, `png_part_bytes` and `max_entry_bytes` stay at or below it. Add a 90 MiB round trip to M006 or to the drill.
  - OQ-18 (owner): `UPLOAD_REFUSED` pauses a commit, and so the series, until the owner approves in the platform. Is the owner available for that during qualification? The alternative is none: a refusal never counts as absent.
