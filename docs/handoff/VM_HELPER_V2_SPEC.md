<!-- Status: SPECIFICATION r2 for cps-vm-helper.v2; not built, not admitted. Written 2026-11-10 from docs/handoff/VM_HELPER_V2_DESIGN.md and owner decisions O43-O61, reviewed by an independent integrity reviewer and an implementability/runner-claims reviewer (31 findings, 30 accepted, 1 partly), revised. OQ-1 is answered by deploy/vm/review1/MUTANTS_V1.py (all 39 v1 mutant definitions). Open questions OQ-3, OQ-5, OQ-7..OQ-15 wait for the probe answers (M002-M004) before any is put to the owner. -->

# cps-vm-helper.v2: implementation specification (SPEC_V2)

Status: SPECIFICATION, not built, not admitted. Written 2026-11-10 for branch `claude/cool-ptolemy-vsfpr5`. Revision r2 (2026-11-10) resolves the 31 findings of the spec review (integrity INT-01..INT-14, build IMP-01..IMP-17); §18 lists each finding with its resolution and the sections changed. The previous text is kept as `SPEC_V2.r1.md`.

Governing sources, in order of authority:
1. the owner's decisions O43-O53 (`CURRENT_STATE.json` `owner_decisions_2026_11_09`) and O54-O61 (`owner_decisions_2026_11_10`, the approved Q1-Q8);
2. the approved design `docs/handoff/VM_HELPER_V2_DESIGN.md` (cited as "design §X");
3. the rejected v1 record `deploy/vm/ADMISSION_VM_HELPER_V1.json` (finding ids F1-F8, SAFE-, OP-, TST-, KIT-, FLAGS-, MK-, GATE-, TEST-);
4. runner v4 `deploy/run/cps_job.py` (sha256 `7505e98ac88bc09a5e0507124e4cb381a5491c1112f418bcf5ca6553ab14f431`), whose behaviour this spec relies on only as listed in §16 (R-claims, each with file:line evidence).

Where this spec decides something the design leaves open, the text says **SPEC DECISION** and §17 lists it again for the admission review. Probe answers P1, P2/M004, P3 and P5 are pending; §12 gives the behaviour for each outcome. **Exact-name search on Drive (P2) is a hard prerequisite: without it nothing in this spec runs.**

An engineer builds from this document plus the repository. No private data, no reserved answer and no Drive access is needed to build or test it.

---

## 0. Conventions

- "MUST", "never", "only" are requirements. "Refused" means exit 4 and no state change. "STOP" means exit 3 with a `DO: STOP` line. "HALT" means a STOP that persists (§13.3).
- `sha(b)`: lowercase hex sha256. `md5`: lowercase hex md5 (only to compare with Drive's `md5Checksum`). `h12(x)`: first 12 hex characters.
- `cjson(x)`: `json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')`. Every hash over a JSON value in this spec is `sha(cjson(x))`.
- `doc_bytes(x)`: `(json.dumps(x, sort_keys=True, ensure_ascii=True, indent=1, allow_nan=False) + '\n').encode('ascii')`. Every JSON file the helper writes uses `doc_bytes`; files read back are parsed with v1 `sjson` (strict: no duplicate key, no NaN).
- Times: `UTC_S` is `YYYY-MM-DDTHH:MM:SSZ` (seconds). Entries carry `UTC_S`. v1 `utc()` (milliseconds) is used only inside local files.
- Words. **Series**: one journal (`Q1`, `E1`, `D1`...). **Entry**: one journal file `CPSJ_<series>_<seq6>.tgz`. **Part**: a file belonging to an entry, uploaded after it. **Commit**: writing, uploading and confirming one entry and its parts (§5). **Head**: the highest-seq entry on Drive. **Run**: one runner job folder (`<tag>/<case>`). **Role**: `S` scope reader, `G` generator, `V` visual reviewer. **Attempt**: per run and role, 1 or 2 (§4). **start_no**: per attempt, 1 or 2 (a superseding START). **Block**: everything one command prints. **Step**: a pure instruction object that `core/` returns and the I/O layer carries out (§1.3). **run8**: `h8(sha(run_key.encode('ascii')))`, the first 8 hex of the sha256 of the run key (r2, IMP-15); it names helper files of a run without its case id.
- The Dot is the operator (a ChatGPT agent with a shell on a Debian 13 VM; `/home/agent` and `/tmp` are 4.9 GB tmpfs; only Drive survives a reset; each AI stage is a new conversation).

---

## 1. Scope, version ids, files, reuse

### 1.1 Scope

v2 replaces the rejected `deploy/vm/` helper. It:
- runs runner v4 commands for the Dot in a detached worker, never printing runner output (§7);
- keeps one hash-chained, add-only journal per series on Drive, and prints nothing that depends on a result until that result's entry is md5-confirmed on Drive (O54, §5);
- restores after a VM reset from the journal head, fail-closed (§8);
- resolves every interrupted AI conversation under O45, O46, O55-O58 (§8.6);
- derives every run's disposition in one pure function (§9);
- gives the maintainer `audit`, `assemble` and `score_check` (§10).

v2 does not change runner v4, the frozen evaluator v4 (`research/evaluation/compare_target050.py`, sha `fc723405...`), the aggregator v2 (`research/evaluation/aggregate_qualification050.py`, sha `e5aa4fc7...`), the writer admission, the package, or `deploy/vm/` (kept unchanged as the rejected record). It never opens a reserved answer.

### 1.2 Version ids and schemas

| Thing | Id |
|---|---|
| helper | `cps-vm-helper.v2` (constant `VERSION` in `deploy/vm2/cpsvm2/__init__.py`) |
| journal entry document | `cps.vm2-entry.v1` |
| fold state | `cps.vm2-state.v1` |
| local cache files | `cps.vm2-cache.v1` (STATE), `cps.vm2-pending.v1`, `cps.vm2-block.v1`, `cps.vm2-halt.v1`, `cps.vm2-restore-work.v1` |
| helper config in the kit | `cps.vm2-config.v1` (file name `VM_HELPER_CONFIG.json`, kept because the reused `unpack_kit` treats a kit that differs only in that file as config-only) |
| ALL_FROZEN part | `cps.vm2-all-frozen.v1` |
| empty carrier marker | `cps.vm2-failed-run.v1` (inside `cps_failed_run`) |
| score plan | `cps.vm2-score-plan.v1` |
| owner verdicts (r2, INT-03) | `cps.vm2-owner-checks.v1` (`OWNER_CHECKS.json`, §9.5) |
| audit report | `cps.vm2-audit.v1` |
| reuse manifest | `cps.vm2-reuse-manifest.v1` |
| probe P5 report | `cps.vm2-probe-p5.v1` |
| fingerprint PASS | `cps.vm-fingerprint-pass.v1` (unchanged from v1, so the reused `validate_pass` reads it) |

### 1.3 Files to create

All new code lives in `deploy/vm2/`. **SPEC DECISION:** the design's `io/` package is named `vio/`: a package named `io` inside a directory on `sys.path` cannot be imported as `io.savepoint`, because the standard-library `io` module is already in `sys.modules` at interpreter start.

```
deploy/vm2/
  vm2.py                      entry point: python3 -I -B deploy/vm2/vm2.py <go|found|answer|_worker|audit|assemble|score_check>
  session_start.sh            bootstrap after a reset (§6.6)
  probe_p5.py                 probe P5, standalone (§12.5)
  README.md                   the Dot's procedure (generated sections listed in §6.8)
  REUSE_MANIFEST.json         §1.4
  cpsvm2/__init__.py          VERSION, package paths
  cpsvm2/core/__init__.py     empty
  cpsvm2/core/step.py         Step classes (the only names vio/ may import from core/)
  cpsvm2/core/names.py        name and value patterns, PATTERNS registry, DOC_SAMPLES check
  cpsvm2/core/entry.py        ENTRY schema, body validators, cjson/state hash
  cpsvm2/core/fold.py         TABLE (section T as data), apply(state, entry) -> state | ChainInvalid
  cpsvm2/core/plan.py         next_action(view) -> Step (total), chain_next
  cpsvm2/core/session.py      session_next(view) -> Step: the §8 session and restore machine, classify, head_search (r2, IMP-15)
  cpsvm2/core/outcome.py      outcomes(state) (§9)
  cpsvm2/vio/__init__.py      empty
  cpsvm2/vio/v1reuse.py       the 54 reused v1 segments, byte-identical (§1.4)
  cpsvm2/vio/v1compat.py      the free names the reused segments need (§1.5)
  cpsvm2/vio/v1mod.py         the 8 modified v1 functions (§1.6)
  cpsvm2/vio/durable.py       durable writes and cache self-hashes (§2.4)
  cpsvm2/vio/savepoint.py     commit() mechanics (§5)
  cpsvm2/vio/drive.py         block printing, FIND/found bookkeeping, download-back
  cpsvm2/vio/runner.py        runner argv, detached chain execution, result parsing (§7)
  cpsvm2/vio/place.py         strict walk, snapshot, placement, evict (§7.6, §8.5)
  cpsvm2/vio/host.py          layout, fingerprint, PASS, self-test, kit intake (§8.2-8.3)
  cpsvm2/cli.py               go / found / answer, the glue that imports core/ and vio/
  cpsvm2/worker.py            the detached worker (chain, snapshot, entry build, PENDING); imports core/ and vio/
  cpsvm2/maint/__init__.py    empty
  cpsvm2/maint/audit.py       §10.1
  cpsvm2/maint/assemble.py    §10.2
  cpsvm2/maint/score_check.py §10.3
  tests/run_tests.py          the single test entry point (§14)
  tests/fakes.py              FakeDrive, FakeDot, the world builder
  tests/test_core_table.py, tests/test_core_props.py, tests/test_resets.py, tests/test_v1_regressions.py,
  tests/test_reuse.py, tests/test_lints.py, tests/test_maint.py, tests/test_probe_p5.py, tests/mutants.py
```

Also changed outside `deploy/vm2/` (admitted separately, §15.2): `deploy/make_kit.py` (MK-1, MK-2) with `deploy/test_make_kit.py`.

Not changed: `deploy/run/*`, `deploy/vm/*`, `deploy/verify_drive_files.py`, `deploy/textcarry.py`, `research/**`.

Import rule (lint, §14.6): `cpsvm2/vio/*` may import from `cpsvm2.core` only the module `cpsvm2.core.step` (and from it only Step classes). `cpsvm2/core/*` imports only the standard library and other `core` modules; it does no I/O (no `open`, `os.*` file calls, `subprocess`, `time.sleep`, `datetime.now`); the current time and every observation come in as arguments. `cli.py` and `worker.py` are the only modules that import both.

Step classes (`core/step.py`, frozen dataclasses): `PrintBlock(state_code, uploads, finds, lists, downloads, do)`, `RunChain(run, first, info)`, `Place(plan)`, `Ask(keys, context)`, `Stop(code, handback)`, `Halt(code, commit)`, `Commit(entry, parts)`, `Evict(run)`, `Wait(seconds)`. `vio/` receives Steps and performs them; it never decides.

### 1.4 What is reused verbatim, and REUSE_MANIFEST

`cpsvm2/vio/v1reuse.py` holds, in the v1 order, the source segments of these 54 names from `deploy/vm/cps_vm.py` at `95df27099c275ba1a8442df5087cb87b97434dae` (file sha256 `7524987159f579d426eb99a22983a414bbcfa9c5ba99ea655611b7d77d43e14a`, the value `ADMISSION_VM_HELPER_V1.json` `files_sha256` records), each copied byte for byte, separated by two blank lines, after a header that imports the standard-library modules the v1 file imports and `from .v1compat import *`.

**Segment definition.** For a top-level `FunctionDef` or `ClassDef` node of `ast.parse(source)`: the source text from column 0 of the first line of the node (its first decorator if any) through `end_lineno:end_col_offset`, as UTF-8, with no normalisation. Its hash is `sha(segment.encode('utf-8'))`.

`REUSE_MANIFEST.json`:
```
{"schema": "cps.vm2-reuse-manifest.v1", "source": "deploy/vm/cps_vm.py", "source_commit": "95df27099c275ba1a8442df5087cb87b97434dae",
 "source_sha256": "7524987159f579d426eb99a22983a414bbcfa9c5ba99ea655611b7d77d43e14a", "target": "deploy/vm2/cpsvm2/vio/v1reuse.py",
 "reused": [{"name": "...", "kind": "function|class", "v1_lines": [a, b], "segment_sha256": "..."}, ...],
 "modified": [{"name": "...", "v1_lines": [a, b], "v1_segment_sha256": "...", "target": "deploy/vm2/cpsvm2/vio/v1mod.py"}, ...]}
```

`tests/test_reuse.py` (no git needed):
1. `sha_file('deploy/vm/cps_vm.py') == source_sha256`, else FAIL (v1 must stay unchanged).
2. For each `reused` row: the segment of that name in `deploy/vm/cps_vm.py` and the segment of that name in `v1reuse.py` both hash to `segment_sha256`.
3. `v1reuse.py` defines at top level exactly the names of the manifest's `reused` list (54 at 95df270; the test takes the count from `REUSE_MANIFEST.json`, never from a literal), plus nothing but imports; its top-level order equals the manifest order.
4. For each `modified` row: the v1 segment hashes to `v1_segment_sha256`, and the name in `v1mod.py` hashes to something else (a modified function that equals v1 is listed under `reused` instead).
5. Every free name each reused segment loads (computed with `ast`, as in `reuse_scan.py` delivered beside this spec) resolves in `v1reuse`'s namespace after import; and every free name each top-level definition of `v1compat.py` loads resolves in `v1compat`'s own namespace (stdlib or v1compat), so a missing constant such as `EXIT_REFUSED` fails the test, not the first `Halt` (r2, IMP-11).

The values, computed from the v1 file (an implementation MUST recompute them in the test, not copy them):

| name | v1 lines | segment sha256 |
|---|---|---|
| sha_bytes | 197-198 | 3e699aa4d547eb48e2efb061177916f546d94a7374c828baa296f48639ab7124 |
| sha_file | 201-206 | a42563b601126d2c74f272d2f0d9ce4721ff389d58181b96bc21ac6636ec2b23 |
| md5_file | 209-214 | 89174225391867dfa49a137b1cba50e547e42be3b4c8c7047373eaf25c2894e2 |
| h8 | 217-218 | 2f2a60192818874f9c337a3429e97e1bed2f2568642f47d18173ab63fbf01c16 |
| canon | 221-222 | df2675b85c78d0a40b2a053b35bc783b5b41bd469a5791d8e562234876570d38 |
| sjson | 229-241 | 64e3a806a74d27c25cf71122a20bcaeac0378ca6b7006b99ae2561fdc5a2de54 |
| read_json_file | 244-248 | d64b24c5c49b638280814e045e7074aa18f19d72ae9529af063e56d1af082056 |
| write_atomic | 251-261 | f5e6a77ea804dda29fc5ecb07bdd93c51e0669ce8caa8cc985a4ffa09e70335d |
| write_new | 264-287 | 4e3d56aaaaedf6f8113f27d52c72d54e4fc799f2bc5a5a9074dce826836dfb94 |
| make_writable_tree | 300-312 | ce85f7f113ad0f51cc186d16a0c496d96ff24cac5165468fbfdb36c0d22c0c9f |
| remove_tree | 315-322 | 43bf3dc7f35e92bf05c00fb18f70cb8386df5394b25b1e2d1c6d3a8e9a30b79c |
| q | 325-326 | fd1c7bca5675fd333375c19cfc23d2b791866f95d001aa23f07157f1d5884438 |
| parse_utc | 187-194 | f6f18dca1ac99b7cf49311b233f809e89544d76142f9b03efd9844bfe4c98d36 |
| now_dt | 171-172 | 1f7cc6f6949f79e811ad269e7c7e6bd1bebd212db1ea2bc21bd58cfaedb78a23 |
| iso | 175-176 | d016e32d4c2a76e1391f5cbb074e805ec958400ea3845c23b7edda90075201a2 |
| utc | 179-180 | 97afadbb2429ffab96d7f71b06b618e4b2deec67b2602c5c472140679214e2da |
| utc14 | 183-184 | 48baa80bfd770fa91f94456b1b8ab0b38e04879e129e459b95fad8407169f58d |
| boot_id_path | 329-330 | f54d38df17168792b236112664b71ac3820d3a1946f64fc0ab43e1cf1ad27997 |
| current_boot_id | 333-337 | 1997b31cc4354c57bda4f7c41bcca3ea5205fc9044d6b7d1d85ee957512c677b |
| HelperLock | 736-786 | 26f94da0f858102060ea954f0ba6a12bec0d6567123a119cf084013766db012b |
| JobLock | 789-813 | b84cf733b2a1d64204b1d70380f1afb13ba8f8c97ce9ee6cfb38756d4cf1f9dc |
| _tarinfo | 906-913 | 22c7e4e5b44879f9b99bd29be9bbd023cecd865df08773ffcf178c970078464e |
| write_tgz | 916-922 | 455ac88f4cf280087aead7dfe23431aa42eb4c0749e92dc3eefe8d46cad08ac5 |
| write_tar_stream | 925-939 | b6115f5feee88b243bb148f29a42b02cbdf3fdc15b55d02de5c2be17a2a9ee38 |
| unsafe_name | 942-948 | 688c45727548e53f1626ec83a9e8386615d095f7ba9131328d50fb98d1cbfe24 |
| under_stage | 954-960 | 66de53a5121ed509f1b49e106ec210154782f01f18c1fcf2bf7227b46feff4cd |
| png_manifest_problem | 966-990 | c54e7505c37f17a18292d6e46289863944097473d4cc5a702bb18ffe36ecca95 |
| pkg_manifest_problem | 993-1001 | fa8559396901336f4a6a2f50a6a62e2fa482d99ae1ae71a420d0f1951da8e395 |
| check_pkg_manifest | 1004-1007 | 5134127d98280fdd81f01c4740324d5de5eb9f3dcf059f86e91b1869174fe5c7 |
| Archive | 1010-1073 | cbc7f5a3391845c3d3b924c6b8a5f8e260477ad2370836246b676b398b5e912c |
| zlib_error | 1076-1078 | 25eaa338abe5654c9570cd4bbdcabf07631f38e3d3daae9c9f995bdf6324b95d |
| Staging | 1081-1122 | 9384485cfab669a78a09f006acc02d1887f9e3ab808ecc20dde001922479d6b5 |
| png_set | 1125-1141 | c6be08782ed6da431b42bf67cdabf66bd11be0a4810f6a9edd3188b58beba35a |
| png_tar_members | 1144-1149 | 280e957a38c5d7b90f5db4d87015578245ceda42ae8b8c1c7099a3ce421a2dbe |
| PartWriter | 1152-1211 | b91ebb6f1c977d9286465e4204aa63172193bb8003825503c37d67de7f74609c |
| tree_bytes | 1214-1225 | a8856d9827b2478c4531afe50a95b8e85667fc3e77af96326689b5f347109362 |
| join_slices | 1482-1493 | 987c55cc611858f8ed9f81026ac14323ab12faaab7a87fb1a155ef02cdf14b6e |
| require_space | 1253-1260 | 3d3aed91b994be4fd64e0f69a0a27a63522bd3e92fa255819f496e735eb21c81 |
| disk_full_halt | 1231-1250 | 01fb6e8ec8b6db903c9e38812828ccf34224f328c53eee5ff0232c2c573d9980 |
| FP | 1497-1527 | 3451c0618e741f3585750d16061b6d8ff374b31d6e2a8c1d13b23082f48d5b74 |
| first_line | 1530-1536 | a7f760d619e04b5da073b49e3111c83de941545bc810f2b1639a09623026e13d |
| fingerprint | 1539-1634 | c54c8db792d155e69cd2247f4fa8a1d02fc3d0a6ea0d32b0be5861dd2c9f1869 |
| kit_members | 2688-2725 | 9ff313e98b99f1dbb83752a33832c8e1c33f8be12ff07cc108caa6faa1f5cfca |
| unpack_kit | 2728-2757 | 0c0a6dc606d5c37845f6c7577513808603262ae576a844dc05d98830ba5c2142 |
| validate_pass | 2936-2947 | e781dcd471da24684aba01895c23bc03115f812178b5f608db44d39c3f54eb73 |
| spawn | 4898-4916 | 9c39e37ba70f1e26bf5bbacba57429d0a39bb427811a311b854e23ed068c1915 |
| worker_alive | 4919-4927 | 6c4e99ef47f3c866e861bb50a51dffcda39408b2c92f61649574b550cdea4704 |
| run_runner | 5048-5061 | 16f358358df3531b3a87b43400152247a841f3daebd2822760262e43094e8f8f |
| scrub | 5064-5069 | 39658ee629497ad5fa306f7da09d48bb9e1d352e5bc53cc39d30a100eb7fc34e |
| clock_check | 3317-3329 | bc22ebedd33dc59fc8decab73b251a1c998b29d86473079147a48ae268586743 |
| check_layout_basic | 503-509 | 57a7e34e79b869a34d8a034e16135d88aaa33ed7f71f15c5b4c0737a1a82abe0 |
| Layout | 448-500 | 43e8d5371f15374ca1e932ffb19ac94c42dd4fa4814bbe6c650f355631d515f1 |
| check_ledger_identity | 3214-3224 | bf7ae532cd3dbf901ae7ae68340dd2480ee44ba6aa1fb3a346e43c0bb297959b |
| selftest_work | 5934-5948 | b717e6176752d35b667d287729958e4593e065952c573e599ec90dd6be466465 |

Total reused: 880 lines (matches design §G).

Two of the 54 have no caller in v2: `join_slices` (v1's SPLIT_ slices; v2 has no split files) and `scrub` (v2 never prints runner stdout). They stay for manifest fidelity; the lint in §14.6 lists them as `UNUSED_REUSED` (reported, not failing). §17 asks the admission review whether to drop them.

### 1.5 v1compat.py: the free names the reused segments need

The reused segments load these module-level names that are not in the reuse list. `v1compat.py` defines each; the review checks this file in full (it is new code).

| name | used by | v2 definition |
|---|---|---|
| `CHUNK` | sha_file, md5_file | `1 << 20` (v1 value) |
| `BOOT_ID_DEFAULT` | boot_id_path | `'/proc/sys/kernel/random/boot_id'` |
| `HELPER_FILE` | spawn | absolute path of `deploy/vm2/vm2.py` (so `spawn` starts `vm2.py _worker <wid> --lock-fd N`) |
| `HELPER_REPO` | fingerprint, check_layout_basic, selftest_work | `Path(realpath(<deploy/vm2/cpsvm2/vio>)).parents[3]`, the repository root |
| `under` | fingerprint | v1 lines 512-517, copied (pure) |
| `note_bytes` | spawn, selftest_work | v1 lines 225-226, copied |
| `ARCHIVE_EXACT` | Archive | v1 value `{'MANIFEST.json': ('MANIFEST.json',), 'ledger': ('ledger', 'ledger/LEDGER.jsonl')}` |
| `PNG_SUBS` | png_manifest_problem | v1 value `('job/qa/visual_deliverable/', 'job/qa/visual_internal/')` |
| `parse_name` | png_manifest_problem, join_slices | **stub returning `None`**: v2 never passes a `png.parts` list to `png_manifest_problem` (parts live at entry level, §3.7), so a manifest that carries one is refused (`'png part name'`), fail-closed |
| `SPACE_MARGIN` | require_space | `64 * 1024 * 1024` |
| `QUAL_ROOTS`, `ROOT_TAGS`, `is_qual_tag` | Layout | v1 values (lines 63-65, 161-162), copied |
| `Halt`, `refuse`, `stop`, `need` | many | v1 class and functions (lines 404-445) copied, with `to_block` removed; `vio` catches `Halt` and maps `(kind, code)` to a v2 block (§13.4). `Halt` text is never printed |
| `Block` | HelperLock, JobLock, selftest_work, wait_block | an inert record with the v1 attribute and method names (`upload`, `listing`, `download`, `next`, `then`, `option`, `result`, `tail`, `code`); it stores, never prints |
| `EXIT_OK`, `EXIT_USAGE`, `EXIT_STOP`, `EXIT_REFUSED`, `EXIT_NEED`, `EXIT_BUSY` | `Halt.__init__` (v1 :404-411 reads EXIT_REFUSED, EXIT_STOP, EXIT_NEED, EXIT_BUSY), wait_block | the v1 values of line 49: `0, 2, 3, 4, 10, 11` (internal only; v2 maps every `Halt` per §13.4 and never exits 10 or 11) (r2, IMP-11) |
| `runner_path` | run_runner | a function, as in v1 (:567-568): `def runner_path(): return HELPER_REPO / 'deploy/run/cps_job.py'` (the reused `run_runner` calls `str(runner_path())`, cps_vm.py:5049) (r2, IMP-11) |
| `CJ` | scrub | the runner module loaded once by `vio/runner.load_runner()` after its sha256 equals the pin |
| `wait_block` | spawn | the modified `wait_block` from `v1mod.py` (§1.6) |

`spawn(ctx, kind, info, lock)` takes a `ctx` with `.lay` (a `Layout`) and `.cfg` (a dict with `wrap_foreground_seconds`). `validate_pass(ctx, raw, fp)` needs `ctx.cfg['selftest_expected_tests']`. `clock_check(ctx, floor, block, model)` needs `ctx.cfg['clock_wait_max_seconds']` and `ctx.lay`. `check_ledger_identity(ctx)` needs `ctx.lay`. `selftest_work(ctx, info)` needs `ctx.V` (stored in the inert Block, never printed). v2 passes a `Ctx2` object with exactly `lay`, `cfg` and `V`.

### 1.6 The 8 modified functions (`v1mod.py`, each reviewed as a diff against its v1 segment)

| name | v1 lines | v1 segment sha256 | required change |
|---|---|---|---|
| tree_list | 843-886 | 23b44d804efe0ff23642d2b0df3703f6f6e190b81df2fb27bd265f61e46cc056 | strict only: `os.walk(..., onerror=raise_)`; any `OSError`, unreadable directory or file, symlink, device, socket, FIFO, mode bit `0o7000`, unsafe or non-UTF-8 name raises `Halt('STOP', 'WALK_UNSUPPORTED_ENTRY')` naming the path class (no `lenient` mode) (SAFE-01) |
| rebuild_kit | 2797-2825 | 23ea04aab5466fcb4375586043c2b213341bfbf95ec99e8d6f27e3de4aa35d60 | v2 download lines (`FIND`/`DOWNLOAD` by exact name, §8.2) instead of `CPS_FOLDER_PATH`; re-hash the rebuilt zip before returning |
| session_kit | 2828-2892 | 6144ac3696065b8d72fa6f0b87ad1525a6a9fee016218be4b35e090bb36f4ffe | re-hash the chosen zip (`sha_file(use) == sha` and size) before `kit_members` on both routes (KIT-2); exact names only; returns the kit sha256 for the journal |
| place_frozen | 4837-4879 | cd52c082840843c3a873ff9fe8569eb0fc9fa92690eff171e116b1f5a1306b8c | source of the bytes is `BASE/outbox/frozen_json/<tag>_<case>_FROZEN.json` or the run's FROZEN entry (§7.7); check `sha(bytes) == state.runs[k].frozen.frozen_sha256` and the ledger's freeze entry; no `parse_name` |
| cmd_worker | 5002-5045 | db59c5f217e27a0e986ea92e1b91af43a065cbafa16a85cffb88af4b27f2c4b5 | dispatch `kind` in `{chain, selftest, place}` to `worker.py`; the result is a JSON document written durably to the `out` path the reused `spawn` recorded in `DETACHED.json` (`outbox/<kind>_<wid>.out`), the log is spawn's `log` path (`outbox/<kind>_<wid>.log`) (cps_vm.py:4902; r2, IMP-11); never printed text; bounded (§7.2) |
| wait_block | 4930-4975 | dc5f59a7b58635dbc8b980b6757be2da31c6e18aa81caa4e82542fb08a3cae39 | returns `('done', result)`, `('running', None)` or `('died', None)`; no plan call, no printing; the chain table lives in `core/plan.chain_next` |
| cleanup_leftovers | 2956-2975 | a800f44e91a88b357bb5d590c17d747efeb5753053a12e7383b9e6d29f96df58 | also removes `outbox/journal/.tmp_*` and `inbox/*` downloads of an earlier boot; never touches a job folder |
| check_layout_release | 525-562 | e65b25b9f32332ad845c433c1f28e2a75cda00273ddd35fa845412610a6733aa | pins `deploy/vm2/**` (every git-tracked file under `deploy/vm2/`, by the helper tree sha of §3.4) and `deploy/run/cps_job.py`; drops the `deploy/vm/` pins |

Total modified: 329 lines in v1.

Deleted (no v2 counterpart): INDEX and listings, `situation` and every `*_plan`, tokens and binding, `find_fork`, `resolve_forks`, `local_floor`, `Fetcher`, `rerender`, `restore_png`, the recheck, start-note, link-note, ai-archive, incident, rebuild-parts and probe-p5 commands, `run_flags`, and `deploy/vm/apply_frozen_flags.py` (design §G).

---

## 2. Layout on the VM, and the local cache

### 2.1 Paths

`Layout` is reused verbatim (v1 lines 448-500), so every v1 path keeps its meaning. `BASE = $CPS_VM_BASE or $HOME/cps`, `TOOLS = $CPS_TOOLS or $HOME/cps-tools`. On the Dot's VM, `HOME=/home/agent`.

| Path | Layout attribute | Use in v2 |
|---|---|---|
| `BASE/repo` | `repo` | the clone at the release commit; must be the repository holding `deploy/vm2/` (check_layout_basic: `realpath(BASE/repo) == HELPER_REPO`) |
| `BASE/vm.sh` | `vm` | launcher written by session_start.sh: sources `TOOLS/env.sh`, `exec python3 -I -B BASE/repo/deploy/vm2/vm2.py "$@"` |
| `BASE/runtime/` | `runtime` | the unpacked kit (read-only 0444 files): `RELEASE.json`, `VM_HELPER_CONFIG.json`, `qualification/ADMISSION*.json`, `qualification/JOBS.json`, `qualification/jobs/<case>/{JOB.json,JOB_TITLE.json,source.*}`, `tables/` |
| `BASE/ledger/LEDGER.jsonl` | `ledger` | the runner's qualification ledger; the folder holds nothing else (§8.5) |
| `BASE/qual/<root>/<case>/` | `qual`, `job_dir(tag, case)` | qualification and drill job folders; roots `A`, `B`, `A_restart1`, `B_restart1`, `nonattempts_A`, `nonattempts_B` (QUAL_ROOTS) |
| `BASE/jobs/<utc14>/<case>/` | `jobs` | everyday job folders (tag `E<utc14>`) |
| `BASE/everyday_inputs/<case>/` | `everyday_inputs` | everyday JOB.json, JOB_TITLE.json and the source, written by the Dot |
| `BASE/transcripts/` | `transcripts` | exported transcripts the helper names (§6.4) |
| `BASE/outbox/` | `outbox` | `.lock` (HelperLock), `DETACHED.json` (spawn), worker logs and results |
| `BASE/outbox/frozen_json/` | `frozen_json` | `<tag>_<case>_FROZEN.json` copies kept after evict (§7.7) |
| `BASE/inbox/` | `inbox` | downloads: `inbox/kit/`, `inbox/journal/`, `inbox/verify/`, `inbox/cps/FOLDER_MANIFEST.md` |

v2 additions (`vio/host.paths(lay)`, all under BASE):

| Path | Use |
|---|---|
| `outbox/v2/STATE.json`, `PENDING.json`, `BLOCK.json`, `HALT.json`, `RESTORE_WORK.json` | the local cache (§2.3) |
| `outbox/journal/` | entries and parts being committed |
| `attest/` | files the Dot writes for the helper: `final_message.txt`; files the helper writes for the Dot: `notice_<seq6>.txt`, `continue_<run8>_V<a>_<n>.txt`, `ask_<seq6>.txt` |
| `deliver/<run8>/STANDARD.xlsx` | everyday: an ASCII-named copy of the runner's standard file, made by the worker after `deliver-check` (sha256 equal to `saved_qa.deliverable_sha256`); the DELIVER block names this copy, never the title-bearing runner path (r2, IMP-14) |
| `$HOME/cps-deliveries/` | everyday personal copies (DEPLOYMENT_MODEL); the only allowed parent of `copy=` and `log=` answers; layout in §11.3 |

Test overrides: `CPS_VM_BASE`, `CPS_TOOLS`, `CPS_VM_BOOT_ID_PATH` (all from the reused `Layout`/`boot_id_path`), and `HOME`. Nothing else is overridable from the environment. The clock is read only through `vio/host.now()`; the tests replace that one function in-process to skip `WAIT` blocks (§14.2). No test-only switch exists in the shipped code path.

`$HOME` must be absolute, without whitespace (check_layout_basic). Every helper-chosen path is ASCII without whitespace; the helper refuses to start (`STOP LAYOUT_PATH`) otherwise, so every printed path round-trips through `shlex`.

### 2.2 The kit's helper config `runtime/VM_HELPER_CONFIG.json` (`cps.vm2-config.v1`)

Exact keys (unknown or missing key: `STOP CONFIG_INVALID`):

| key | type | meaning |
|---|---|---|
| `schema` | str | `cps.vm2-config.v1` |
| `series` | str | `Q[1-9]`, `E[1-9]` or `D[1-9][0-9]?`; mode follows the letter (Q qualification, E everyday, D drill) and must agree with RELEASE.json status (Q, D: RELEASED_FOR_QUALIFICATION; E: RELEASED_FOR_USE). r2 (INT-09): in Q and D mode it must equal RELEASE.json `vm_helper.series` (an extra key the runner ignores, R42), so the series of a qualification is fixed by the release, not by the config; otherwise `CONFIG_INVALID series` |
| (no `folders` key) | — | r2 (INT-09): the Drive folders are constants in `core/names.py` `FOLDERS`, not configuration: series folder Q `CPS/qualification`, E `Dots Folder/CPS_JOB_RECORDS`, D `CPS/reports`; setup `CPS/setup`; reports `CPS/reports`; static `CPS`. A config that has a `folders` key is `CONFIG_INVALID` |
| `accepted_helper_tree_sha256` | list[hex64] | helper trees this kit accepts in journal entries (§3.4) |
| `accepts_release_sha256` | list[hex64] | earlier releases whose journal this kit continues (KIT-1); the genesis release is always accepted |
| `selftest_expected_tests` | int | for the reused `validate_pass` |
| `clock_wait_max_seconds` | int | for the reused `clock_check` |
| `wrap_foreground_seconds` | int | how long `go` waits for the worker in the foreground; must be at most `gates.p5_tool_call_seconds - 60` |
| `png_part_bytes` | int | 1,000,000..`gates.p2_max_upload_bytes` |
| `max_entry_bytes` | int | at most `gates.p2_max_upload_bytes` |
| `max_transcript_bytes` | int | default 50,000,000 |
| `max_ai_output_bytes` | int | default 100,000,000 |
| `conversation_re` | str | fullmatch regex for conversation ids or links (P1); the kit is refused (`CONFIG_INVALID conversation_re`) if it matches any `DOC_SAMPLES` string or any key or pattern name (§6.3) |
| `transcript_ext` | str | `[a-z0-9]{1,10}` |
| `drive_id_re` | str | default `[A-Za-z0-9_-]{20,80}`, narrowed after P2 |
| `gates` | dict | the probe answers, §12.1 |
| `clear` | null or dict | O59 clearing: `{"series", "seq", "code"}` (§13.5) |
| `doc_samples` | list[str] | every example value printed in `deploy/vm2/README.md` (refused as attested values) |

**What a config-only kit may change** (r2, INT-08, INT-09). A kit is *config-only* relative to another kit when their member sets (path and bytes, as `kit_members` returns them) differ only in `VM_HELPER_CONFIG.json` (§8.2 defines how the two member sets are obtained after a reset). Between the two configs only these keys may differ: `clear`, `wrap_foreground_seconds`, `clock_wait_max_seconds`, `png_part_bytes`, `max_entry_bytes`, `max_transcript_bytes`, `max_ai_output_bytes`, and `doc_samples` (additions only). A difference in any other key (`schema`, `series`, `accepted_helper_tree_sha256`, `accepts_release_sha256`, `selftest_expected_tests`, `conversation_re`, `transcript_ext`, `drive_id_re`, `gates`) makes the kit not config-only for every purpose (CLEAR, §8.1 step 11): `STOP CONFIG_CHANGE_NOT_ALLOWED HANDBACK C`. In addition, after GENESIS every command requires the config's `gates` to equal `state.genesis.gates` (`STOP GATES_CHANGED HANDBACK C`): a probe answer that changes needs a new series.

### 2.3 Local cache files

All are written with `durable.write` (§2.4), are ASCII JSON via `doc_bytes`, and carry `self_sha256 = sha(cjson(doc without self_sha256))`.

**STATE.json** (`cps.vm2-cache.v1`):
```
{"schema", "series", "boot_id", "uid", "home", "operator": {"model", "platform"} | null, "marks": {<mark key>: <utc>},
 "kit_sha256", "fingerprint_sha256", "pass": {"name", "md5"} | null, "gates_ok": bool,
 "head": {"seq", "name", "id", "md5", "bytes", "sha256"} | null,
 "state": <fold state> | null, "state_sha256": hex | null,
 "post": [<post-commit actions not yet done>], "written_utc", "self_sha256"}
```
`marks` (r2, INT-01, IMP-01): boot-local records of non-repeatable instructions printed in this boot, keyed by the identity of what they belong to, never by position: `OPEN:<run>:<role key>:<start_no>:<start seq>`, `AWAIT:...` (same key), `EXPORT:...`, `END:...`, `CONTINUE:<run>:<role key>:<continuation n>`, `DELIVER_USER:<run>:<prepared_seq>:<ack seq or 0>`. A commit never removes a mark: step 8 of §5.1 copies `marks` unchanged into the new STATE.json; a mark simply stops mattering when the start, continuation or delivery it names is no longer the current one. Marks are lost only with the cache (a reset or an invalid cache), and that path resolves every open role from Drive (§8.6) before anything is printed.

**PENDING.json** (`cps.vm2-pending.v1`): one commit in progress.
```
{"schema", "series", "seq", "phase": "ENTRY" | "PARTS" | "VERIFY",
 "entry": {"name", "path", "folder", "sha256", "md5", "bytes"},
 "parts": [{"name", "path", "folder", "sha256", "md5", "bytes", "copies": [[id, md5, size]] | null}],
 "tries": {"<name>": {"uploads": int, "finds_since_upload": int}},
 "verify": [{"name", "id", "path"}],           # md5-hidden download-back (§5.5)
 "state_after_sha256", "post": [...], "created_utc", "self_sha256"}
```
**BLOCK.json** (`cps.vm2-block.v1`): the last printed block.
```
{"schema", "at", "step", "head_seq", "state_code", "lines": [str], "expect": {"command": "go" | "found" | "answer" | "none",
 "names": [str], "keys": {"<key>": "<PATTERN>"}, "window": {"<key>": [lo_utc, hi_utc]}}, "printed_utc", "self_sha256"}
```
**HALT.json** (`cps.vm2-halt.v1`): a local sticky halt (§13.3): `{"schema", "series", "code", "head_seq", "detail", "created_utc", "self_sha256"}`.

**RESTORE_WORK.json** (`cps.vm2-restore-work.v1`): the restore state machine's observations in this boot (§8): `{"schema", "boot_id", "phase", "hint", "kit": {...}, "head_kit": {...} | null, "lookups": [{"name", "result": "present"|"absent", "copies", "utc"}], "head": {...} | null, "resolution": {...} | null, "placed": bool, "self_sha256"}`. `phase` is one of (r2, IMP-15), in this order, one per §8.1 step: `LAYOUT`, `SETUP`, `OPERATOR`, `KIT`, `CONFIG`, `FINGERPRINT`, `HEAD`, `IDENTITY`, `PASS`, `CLOCK`, `KIT_ACCEPT`, `CLASSIFY`, `RESOLVE_END`, `RESOLVE_PLACE`, `RESOLVE_EXPORT`, `RESOLVE_ATTEST`, `PLACE`, `COMMIT`, `RECHECK` (§8.4 step 6), `DONE`. A phase only moves forward; a reset discards the file.

### 2.4 Durable-write rules (SAFE-04)

`vio/durable.write(path, data, mode)`:
1. `data` must be non-empty bytes (`HALT INTERNAL_EMPTY_OUTPUT`; Drive rejects zero-byte files).
2. Open `path.parent/.tmp_<pid>_<8 hex>_<name>` with `O_WRONLY|O_CREAT|O_EXCL`, `mode`.
3. Full-write loop: `n = os.write(fd, view)`; repeat on the remainder until empty; `n == 0` raises `OSError(EIO)`.
4. `os.fsync(fd)`, close, `os.replace(tmp, path)`, then `os.fsync` of the folder's descriptor.
5. Read back: size and sha256 must equal `data`'s (`HALT WRITE_READBACK_MISMATCH`).
6. Any `OSError` (step 2-5): remove the temporary file if possible and raise `DurableError(errno)`.

Entry tgz files are written by the reused `write_tgz` (`'xb'`, gzip mtime 0, fsync), then `durable.seal(path)` fsyncs the folder and re-reads the archive with the reused `Archive` (every member and the MANIFEST sha checked). Parts are written by the reused `PartWriter` (fsync per part) or `durable.write`, then sealed the same way.

`DurableError` with `ENOSPC` or `EDQUOT` becomes `HALT DISK_FULL`; any other becomes `HALT WRITE_FAILED`. Either is raised **before anything of the block is printed**: the command prints only the HALT block (§13.3), and no UPLOAD line names a file that is not durably on disk. The reused `require_space(lay, need, what)` is called before every snapshot, entry and part write with `need` = the estimated bytes (tree bytes of the job folder plus 10%), giving `HALT DISK_FULL` before work starts.

### 2.5 Cache validation on every command

Every `go`, `found` and `answer` first (under `HelperLock`):
1. parses each cache file that exists; checks schema and `self_sha256`;
2. checks `STATE.boot_id == current_boot_id()`, `STATE.state_sha256 == sha(cjson(STATE.state))`, `STATE.head.seq == STATE.state.seq`, `PENDING.seq == STATE.head.seq + 1` (when PENDING exists), `BLOCK.head_seq == STATE.head.seq`;
3. checks `HALT.json` (if present: §13.3).

Any failure in 1-2 takes the restore path (§8): the cache files are moved to `outbox/v2/invalid_<utc14>/` (never deleted), and `go` starts the session phase. Placement requires empty targets (§8.5), so in the same boot, with job folders still present, the restore path ends in `STOP PLACE_TARGET_NOT_EMPTY` (fail-closed; the maintainer looks at it).

---

## 3. The journal

### 3.1 Series and folders

| Series | Mode | Drive folder (`core/names.py` `FOLDERS`, a constant, r2 INT-09) |
|---|---|---|
| `Q1` (`Q[1-9]`) | qualification | `CPS/qualification` |
| `E1` (`E[1-9]`) | everyday | `Dots Folder/CPS_JOB_RECORDS` (owner-only, O49) |
| `D<n>` | drill (qualification rules on invented jobs) | `CPS/reports` |

One series per kit. A series is contiguous: entries `000001..N`, entry `k+1` is built only after entry `k` and all its parts are confirmed (§5), so the head is the unique `N` present with `N+1` absent.

### 3.2 Names (`core/names.py`, all `re.fullmatch`, `re.ASCII`)

```
SERIES   = r'Q[1-9]|E[1-9]|D[1-9][0-9]?'
SEQ6     = r'[0-9]{6}'                                       (000001..999999)
ENTRY    = r'CPSJ_(SERIES)_(SEQ6)\.tgz'
PART     = r'CPSJ_(SERIES)_(SEQ6)_(PNG|DELIV|DLOG|LEDGER|ALLFZ)([0-9]{2})\.(part|xlsx|json|jsonl)'
           with the kind/extension binding PNG->part, DELIV->xlsx, DLOG->json, LEDGER->jsonl, ALLFZ->json; kk from 01
PASS     = r'FINGERPRINT_PASS_([0-9a-f]{64})\.json'
SELFTEST = r'SELFTEST_([0-9a-f]{64})\.json'
KIT      = r'SESSION_KIT_([0-9a-f]{12})\.zip'                (12 hex of the kit zip's sha256; SPEC DECISION, §17)
TAG      = r'A|B|A-restart1|B-restart1|NA-A|NA-B|E[0-9]{8}T[0-9]{6}Z'
CASE_ID  = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}'                 (the runner's CASE_ID_RE, R-claim R16)
RUN_KEY  = TAG + '/' + CASE_ID
```
Entry and part names reveal no case, reader or outcome. `DELIV` and `DLOG` parts go to the user's profile folder (§11.3), all others to the series folder.

### 3.3 Entry archive

`CPSJ_<S>_<seq6>.tgz` is written by the reused `write_tgz`: gzip level 6, mtime 0, PAX, members in this order, every member mtime 0, uid/gid 0:

| # | member | when | mode |
|---|---|---|---|
| 1 | `MANIFEST.json` | always: the ENTRY document (§3.4). **SPEC DECISION:** the design calls it ENTRY.json; the member is named `MANIFEST.json` because the reused `Archive` requires that first member | 0444 |
| 2 | `job/`, `job/...` | STAGE, FROZEN: the job-folder snapshot without page PNGs (§3.8) | as on disk (`& 0o777`) |
| 3 | `ledger/`, `ledger/LEDGER.jsonl` | GENESIS (Q, D), and every STAGE or FROZEN in Q/D: the ledger bytes after the chain | 0755 / 0644 |
| 4 | `ai/`, `ai/...` | AI: the role's output folder, walked strictly, tarred unopened | as on disk |
| 5 | `transcript/`, `transcript/<role><attempt>_<start_no>.<ext>` | AI-G with `transcript=exported`; RESTORE: every exported transcript (O56) | 0644 |
| 6 | `attest/`, `attest/final_message.txt` (AI-G), `attest/notice.txt` (FROZEN with notify), `attest/continue.txt` (REVIEW_INCOMPLETE), `attest/ask.txt` (entries that ask the user) | as listed | 0644 |
| 7 | `delivery/`, `delivery/copy.xlsx`, `delivery/log.json` | DELIVERY: the personal copy and its log (so a missing profile part is re-uploaded from the entry) | 0644 |
| 8 | `final/`, `final/LEDGER_FINAL.jsonl`, `final/ALL_FROZEN.json` | FINAL (the same bytes as its parts) | 0644 |

Reading always uses `Archive(path, ('MANIFEST.json', 'job', 'ledger', 'ai', 'transcript', 'attest', 'delivery', 'final'))` followed by `Archive.check(expected)` where `expected` is built from `payload.members` (§3.8): exactly those members, types, modes, sizes and sha256s. Any refusal is `HEAD_CORRUPT` at restore and `AUD_ENTRY_CORRUPT` in the audit.

### 3.4 ENTRY document (`cps.vm2-entry.v1`)

Exact key set; `core/entry.validate_entry(doc) -> [problem]` returns every violation; an entry with any problem is never written (local) and is `SCHEMA_INVALID` when read.

| key | type | validation |
|---|---|---|
| `schema` | str | `cps.vm2-entry.v1` |
| `series` | str | SERIES; equals config series |
| `seq` | int | `1 <= seq <= 999999`, not bool |
| `name` | str | equals `CPSJ_<series>_<seq:06d>.tgz` |
| `prev_sha256` | hex64 or null | null iff `seq == 1`; else the sha256 of entry `seq-1`'s tgz bytes |
| `kind` | str | one of `GENESIS INPUTS STAGE FROZEN OPENED AI RESTORE ACK DELIVERY HALT CLEAR FINAL` (INPUTS: everyday only, r2 INT-10) |
| `body` | dict | exact keys per kind (§3.5) |
| `utc` | str | UTC_S; the ceiling to the second of the build time (so it is never earlier than any runner `ended_utc` of the chain it records) |
| `boot_id` | str | `[0-9a-f-]{36}` or `unknown-boot` (refused for every kind but HALT) |
| `uid` | int | `os.getuid()` |
| `home` | str | `$HOME` |
| `fingerprint_sha256` | hex64 | the fingerprint at build time |
| `helper` | dict | `{"version": "cps-vm-helper.v2", "tree_sha256": hex64}`; `tree_sha256 = sha(cjson(sorted([relpath, sha_file]) for every regular file under deploy/vm2/ except tests/)))`; must be in config `accepted_helper_tree_sha256` |
| `runner_sha256` | hex64 | `7505e98ac88bc09a5e0507124e4cb381a5491c1112f418bcf5ca6553ab14f431` |
| `kit_sha256` | hex64 | the kit zip sha256 in use |
| `release_sha256` | hex64 | sha256 of `runtime/RELEASE.json`; equals genesis release or is in `accepts_release_sha256` |
| `confirms` | list | for `seq > 1`: exactly the previous commit's files, entry first then parts in order: `[{"name", "copies": [{"id", "md5", "size"}]}]`; every md5 and size equals the values that commit recorded (the copies the Dot attested, §5). Every item has at least one copy, with one exception (r2, INT-04): in a RESTORE with `body.rebase`, each head part listed in `body.rebase.missing_parts` appears with `copies: []` (§4.2 S4) |
| `parts` | list | `[{"name", "kind", "k", "folder", "sha256", "md5", "bytes"}]`, names per PART with this series and seq, `k` = 1.. contiguous per kind, each `bytes >= 1` |
| `payload` | dict | `{"members": [[path, "dir" or "file", mode, bytes or null, sha256 or null], ...], "png": null or {...}}` (§3.8) |
| `state` | dict | the fold after this entry (§3.11) |
| `state_sha256` | hex64 | `sha(cjson(state))` |
| `cleared_local` | null or dict | `{"code", "head_seq", "kit_sha256"}`: a local sticky HALT (§13.3) that a config-only kit cleared since the previous commit (O59); null otherwise |

### 3.5 Bodies

`RunRef = {"run": RUN_KEY}`. All UTC values are UTC_S. `conv` values match config `conversation_re`.

| kind | exact body keys |
|---|---|
| INPUTS | (E only, r2 INT-10) `tag` (`E<utc14>`), `case`, `inputs` {`job_sha256`, `title_sha256`, `source_name`, `source_sha256`} of the three files in `everyday_inputs/<case>/`, `request_utc` |
| GENESIS | `mode`, `operator` {model, platform}, `jobs` (Q/D: `[[case, order, nonattempt], ...]` from the pinned JOBS.json; E: null), `ledger` (Q/D: `{"identity_line_sha256", "ledger_id"}`; E: null), `layout` {base, qual, jobs, ledger, runtime}, `gates` (a copy of config `gates`), `pass` {name, md5}, `other_series_absent` (Q: the double-absence observations of `CPSJ_Q<k>_000001.tgz` for every other k, §7.12; else null) |
| STAGE | `run`, `new_run` (null or `{"tag", "case", "reader", "job_dir", "restart_of"}`), `prepare_inputs_sha256` (E new run: `sha(cjson(INPUTS.inputs))` of the inputs the prepare read, r2 INT-10; else null), `commands` (list of `{"sub", "exit", "result", "next", "codes", "record_sha256_after", "ledger_sha256_after", "stdout_sha256", "started_utc", "ended_utc"}`), `next` (the runner's last NEXT, first token), `next_args` (`{"prompt", "folder"}` paths or nulls), `codes`, `consumed` (`[{"role", "attempt", "revision", "tree_sha256"}]`, where `tree_sha256` is the worker's own strict walk of the role's output folder immediately before the consumer command, §7.2 step 3, r2 INT-07), `start` (null or §4.4 START), `review_incomplete` (bool), `continue_problems` (int or null), `refused` (null or code), `rerun` (null or `{"after_seq", "unbound": true}`), `rebase` (null or `{"head_seq", "base_seq", "bound", "diverged"}`), `snapshot` {members, tree_sha256}, `png` (null or §3.8), `saved_qa` (null or `{"sha256", "deliverable_sha256"}`), `carrier_sha256` (null or hex), `generation_record_sha256` (null or hex), `fingerprint_checked` (bool) |
| FROZEN | every STAGE key, plus `frozen_sha256`, `final_next`, `final_codes`, `restart_eligible` (bool: `restart_problem(...) is None` computed with the runner's own function on the ledger after freeze, R14, **and** the run's `restart_of` is null: the runner's function does not look at `restart_of`, R44, so a restart run is never restart-eligible; r2 IMP-06), `flags_added` (list), `notify` (null or `"NOTIFY_OWNER"` or `"ASK_USER"`), `delivery_sent` (bool) |
| OPENED | `run`, `role`, `attempt`, `start_no`, `conversation`, `opened_utc` |
| AI | `run`, `role`, `attempt`, `revision`, `start_no`, `start_boot_id`, `ended` (true), `conversation`, `attested` (G: `{"platform", "model", "effort", "started_utc", "ended_utc", "single_user_message", "features" {6 bools}, "tools" [str], "transcript_status"}`; S: `{"prompt_pasted": true}`; V: `{}`), `tree_sha256`, `files` (`[[rel, bytes, sha256]]`), `transcript` (null or `{"status", "sha256", "ext"}`), `final_message_sha256` (G: hex; else null) |
| RESTORE | `prev_boot_id`, `operator`, `fingerprint_sha256`, `pass`, `head` {seq, md5, copies}, `lookups` (the absence observations of §8.4), `kit_sha256`, `kit_change` (null when the kit equals `head.kit_sha256`; else §8.2 KIT_CHANGE), `resolutions` (list, §8.6), `start` (null or START), `rebase` (null or `{"head_seq", "base_seq", "missing_parts", "absence": [{"name", "utc": [first, second]}], "list_shows_none": true or null, "bound"}`), `rerun_expected` (null or `{"run", "stage"}`), `reprepare` (null or `{"run", "inputs_seq"}`, r2 INT-10), `abandon` (null or `{"run"}`, r2 INT-10), `delivery_question` (null or `{"run", "prepared_seq"}`, r2 INT-06), `placed` (list of `{"what", "path", "tree_sha256"}`) |
| ACK | `for_seq`, `what` (`NOTIFY_OWNER`, `ASK_USER`), `answer` (dict of validated values) |
| DELIVERY | `run`, `standard_sha256`, `copy` {sha256, bytes}, `log` {sha256, bytes}, `profile_folder` |
| HALT | `code`, `detail` (dict of codes and counts, no values), `head_seq` |
| CLEAR | `halt_seq`, `code`, `kit_sha256`, `kit_change` (KIT_CHANGE, §8.2; required, since a CLEAR kit always differs from the halted one) |
| FINAL | `all_frozen_sha256`, `ledger_final_sha256`, `runs` (int), `outcomes_sha256` |

### 3.6 Confirms

`confirms` of entry N lists the files of commit N-1 (its entry, then its parts in `parts` order) with every copy the Dot attested (`id`, `md5`, `size`). The fold copies them into `state.files[name]`. So the state at the head names every confirmed journal file and its Drive ids, except the head's own (known from the restore lookup). The audit checks each against its own listing (§10.1).

### 3.7 Parts

Parts are built with the entry, written durably before PENDING, uploaded only after the entry is confirmed (§5.4), and confirmed in the same PENDING. Their `name`, `sha256`, `md5`, `bytes` are in the entry's `parts`. Kinds:
- `PNG01..PNGnn`: the PNG tar stream of the run's page images and tiles, cut by the reused `PartWriter` at `png_part_bytes`. The stream is a plain tar (PAX) whose first member is `MANIFEST.json` (`{"schema": "cps.vm2-png.v1", "run", "files": [[path, mode, bytes, sha256]]}`, mode 0444) followed by `png_tar_members(job_dir, rels)` (members `job/qa/...`), so the reused `Archive(..., gz=False)` reads it. Only the commit in which a PNG first appears carries it (normally the `finish` STAGE); later entries reference it (§3.8).
- `DELIV01` (`.xlsx`), `DLOG01` (`.json`): DELIVERY only, to `<profile folder>/deliveries/`.
- `LEDGER01` (`.jsonl`), `ALLFZ01` (`.json`): FINAL only.

### 3.8 Payload members, PNG handling, snapshot

`payload.members` lists, for every member after `MANIFEST.json`, `[path, kind, mode, bytes, sha256]` (dirs: bytes and sha null), sorted by path, exactly as written. The job snapshot is taken by the modified strict `tree_list(job_dir)` (§1.6) under `JobLock(job_dir)` (no runner may run), minus the PNG set:

`png_files = png_set(job_dir)` (reused: exactly the page images and tiles the two `VISUAL_QA_MANIFEST.json` list). These are excluded from `job/` and recorded as `payload.png = {"files": [[path, mode, bytes, sha256]], "whole_sha256": <PNG tar stream sha>, "parts_seq": <seq of the entry whose parts hold them>}`. If every `(path, sha256)` is already in `state.runs[run].png.files`, `parts_seq` is that earlier seq and this entry has no PNG parts; otherwise this entry carries new PNG parts for the whole current set and `parts_seq` is this seq. `png_manifest_problem({'members': [...job members as dicts...], 'png': {'files': [...]}})` (reused, no `parts` key) must return None, else `HALT PNG_MANIFEST_UNSAFE`.

`snapshot.tree_sha256 = sha(cjson(members_of_job + png.files))`, the identity used by bindings and the audit.

### 3.9 Size limits

| item | limit | over the limit |
|---|---|---|
| entry tgz | `max_entry_bytes` (at most `gates.p2_max_upload_bytes`) | `HALT ENTRY_TOO_LARGE` (case C, before anything is printed) |
| one part | `png_part_bytes` (at most `p2_max_upload_bytes`) | cannot happen (PartWriter cuts); a DELIV copy over the limit is `HALT PART_TOO_LARGE` |
| parts per kind | 99 | `HALT PART_TOO_LARGE` |
| MANIFEST.json | 32 MB | `HALT ENTRY_TOO_LARGE` |
| AI output folder | `max_ai_output_bytes` | `HALT AI_OUTPUT_TOO_LARGE` |
| transcript | `max_transcript_bytes` | REFUSED `TRANSCRIPT_TOO_LARGE` (the Dot exports again or answers not_available; with not_available the O55 rule applies) |
| `attest/final_message.txt` | 1..8192 bytes UTF-8 | REFUSED `FINAL_MESSAGE_INVALID` |
| every file in any archive | at least 1 byte only for uploaded files (entries, parts); members may be empty | — |

### 3.10 Hash chain and verification levels

- **Link**: `prev_sha256` of N is the sha256 of entry N-1's bytes; `confirms[0]` of N names N-1 with md5 and size.
- **State**: `state_sha256 = sha(cjson(state))`, and `state == apply(state_{N-1}, entry_N)` where `apply` ignores the `state` and `state_sha256` keys of its input.
- **Restore** (reads only the head, F3): downloads N; checks the archive (§3.3), schema, `state_sha256`, helper/runner/release acceptance; checks that the copies of N-1 found by name all have `confirms[0].md5` (LINK_MISMATCH otherwise). It does not download N-1.
- **Audit**: downloads every entry, re-folds from genesis with `core.fold.apply`, compares every `prev_sha256`, every `state` and every `confirms` (§10.1).

### 3.11 The fold state (`cps.vm2-state.v1`)

```
{"schema", "series", "mode", "seq", "phase": "OPEN" | "HALTED" | "FINAL",
 "genesis": {"seq": 1, "utc", "release_sha256", "kit_sha256", "jobs", "ledger", "home", "uid", "base", "gates"},
 "release_sha256", "kit_sha256",
 "halt": null | {"seq", "code"}, "clears": [{"seq", "halt_seq", "code"}],
 "current": RUN_KEY | null, "runs": {RUN_KEY: RUN}, "order": [RUN_KEY],
 "files": {name: [[id, md5, size]]}, "passes": {fp64: {"name", "md5", "size"}},
 "boots": [[boot_id, first_seq]], "notify": null | {"seq", "what", "about": null | "DELIVERY"},
 "ledger": null | {"seq", "sha256", "bytes"},
 "undo": null | {"seq", "run": RUN_KEY, "before": RUN | null, "current_before", "ledger_before", "notify_before"},
 "final": null | {"seq"}, "restores": int}

RUN = {"key", "tag", "case", "reader", "job_dir", "restart_of", "status": "INPUTS" | "ACTIVE" | "FROZEN" | "ABANDONED",
 "inputs": null | {"seq", "sha256"}, "reprepares": 0 | 1,
 "next", "next_args", "codes", "record_sha256", "snapshot": {"seq", "tree_sha256"},
 "png": null | {"parts_seq", "files", "whole_sha256", "parts"},
 "saved_qa": null | {"sha256", "deliverable_sha256"}, "carrier_sha256": null | hex,
 "response_frozen": bool, "interrupts": [{"seq", "form"}],
 "roles": {"<R><attempt>": ROLE}, "replacements": int, "flags": [str],
 "frozen": null | {"seq", "frozen_sha256", "final_next", "final_codes", "carrier_sha256", "restart_eligible", "visual"},
 "reruns": [{"seq", "stage"}], "rebases": [{"seq", "head_seq", "base_seq", "diverged"}],
 "delivery": null | {"checked_seq", "prepared_seq", "sent": bool, "resend_ok": bool},
 "rebase_bind": null | {"head_seq", "base_seq", "bound"}}

ROLE = {"role", "attempt", "status": "STARTED" | "OPENED" | "ARCHIVED" | "CONTINUED" | "RESOLVED",
 "starts": [{"start_no", "seq", "utc", "boot_id", "prompt_sha256", "prompt", "folder", "output", "reason", "superseded_by"}],
 "supersedes": 0 | 1,
 "opened": null | {"seq", "conversation", "utc"},
 "archives": [{"seq", "revision", "tree_sha256", "conversation", "boot_id"}],
 "continuations": int, "review_incomplete": int, "continued_boot": null | str,
 "consumed": null | {"seq", "revision"},
 "resolution": null | {"seq", "outcome", "forced", "action", "transcript", "owner_check"}}
```
`visual` is `PASS` (visual-record PASS), `FAIL` (runner FAIL), `FAILED_BY_RESET`, `REVIEW_INCOMPLETE_LIMIT` or `NOT_REACHED`. `RUN.status` `INPUTS` is an everyday run whose INPUTS entry is committed and whose prepare STAGE is not (r2, INT-10); `ABANDONED` is such a run that a second lost prepare ended (§11.4). `ROLE.supersedes` counts superseding STARTs of the attempt of any reason (T31 REBASE, T43 NO_CONVERSATION); at most 1 (r2, INT-05, O58). Flags are drawn from: `AI_OUTPUT_LOST`, `RESET_DIVERGED`, `RESTART_EXHAUSTED_BY_RESET`, `VISUAL_QA_FAILED_BY_RESET`, `REVIEW_INCOMPLETE_LIMIT`, `OWNER_CHECK`, `START_SUPERSEDED`, `REBASED`, `RERUN_UNBOUND`.

---

## 4. Section T: the transition table

### 4.1 How the table is used

`core/fold.py` holds `TABLE`, a tuple of `Row(id, kind, guard, effect, doc)` where `guard(state, entry, ctx) -> bool` and `effect(state, entry, ctx) -> state'` are pure functions named in the row. `ctx` carries only constants from the genesis (mode, `gates`) and nothing observed later.

```
apply(state, entry):
    structural checks S1-S6 (§4.2); failure -> ChainInvalid(code)
    1. series guards, in order T01..T06: T01 (GENESIS on None) is the only positive one; the first of T02-T06 whose
       kind and guard match -> ChainInvalid(that row id). No other row is consulted.
    2. positive rows: rows = [r for r in TABLE if r.positive and r.kind == entry.kind and r.guard(state, entry, ctx)]
       len(rows) == 1 -> s = rows[0].effect(deepcopy(state), entry, ctx)
       len(rows) > 1  -> ChainInvalid('AMBIGUOUS_ROWS')   (a bug; the enumeration of §4.8 makes it unreachable)
       len(rows) == 0 -> ChainInvalid(<the fallback row of that kind>)   (T14, T25, T36, T39, T48/T50, T53, T56, T60, T63)
    s.seq = entry.seq; s.files |= entry.confirms (copies [] are not recorded); s.boots += [boot] if new
    return s
```
r2 (IMP-08): the series guards T02-T06 take precedence over every other row, and the rows marked "otherwise" are *fallbacks*: they are never evaluated as guards, they only name the ChainInvalid code when no positive row of that kind matches. So RESTORE or FINAL at phase FINAL is T05 (never T50 or T63), a STAGE in HALTED with `notify` set is T04, and an OPENED or AI entry in HALTED is T04. Mutual exclusion is required, and tested, only among positive rows.
`ChainInvalid` written locally (commit step 1) is `STOP INTERNAL_ILLEGAL_TRANSITION` (a helper bug; nothing is written). Read from Drive (restore, audit) it is `CHAIN_INVALID`.

The open roles of a state: `open(state) = [(run, key) for every ROLE with status in {STARTED, OPENED, CONTINUED}]`.

### 4.2 Structural checks (before any row)

| id | check | code |
|---|---|---|
| S1 | `validate_entry(entry)` returns no problem | `SCHEMA_INVALID` |
| S2 | `state is None` iff `entry.seq == 1`; else `entry.seq == state.seq + 1` | `SEQ_GAP` |
| S3 | `entry.series == state.series` | `SERIES_MISMATCH` |
| S4 | `entry.confirms` names exactly the previous commit's entry and parts (`state.seq`'s name, then the parts listed in that entry, which the fold keeps in `state.undo.parts`), every item with at least one copy; except (r2, INT-04) in a RESTORE with `body.rebase`: the head entry has at least one copy, and the set of head parts with `copies: []` equals `body.rebase.missing_parts` exactly (each of them with two absence observations in `body.rebase.absence`, §8.4 step 5) | `CONFIRMS_MISMATCH` |
| S5 | `entry.release_sha256 == state.release_sha256` and `entry.kit_sha256 == state.kit_sha256`, except in RESTORE and CLEAR entries, which may change them, and then only with `body.kit_change` present, its `from_kit_sha256 == state.kit_sha256`, its `to_kit_sha256 == entry.kit_sha256`, and either `config_only` true (the member lists in `kit_change` differ only in `VM_HELPER_CONFIG.json`, recomputed by the fold from the lists) and `entry.release_sha256 == state.release_sha256`, or (RESTORE only) `config_only` false with `run_in_flight` false and the new release equal to the genesis release or in `kit_change.to_accepts_release_sha256` (KIT-1). The audit re-checks the member lists against the kit zips themselves (§10.1 step 5) | `RELEASE_NOT_ACCEPTED` |
| S6 | `entry.runner_sha256` equals the pin; `entry.helper.version == 'cps-vm-helper.v2'` | `HELPER_UNKNOWN` |

### 4.3 Rows

Notation: `R` = `state.runs[body.run]`; `Q` = mode qualification or drill; `E` = everyday; `open(R)` = R has an open role; `role(R, x, a)` = `R.roles[x+a]`; `latest(role)` = its last start with `superseded_by == null`.

**Series**

| id | kind | guard | effect |
|---|---|---|---|
| T01 | GENESIS | `state is None` | new state: `phase OPEN`, mode from config letter, `genesis` from body, `files {}`, `passes {fp: body.pass}` |
| T02 | GENESIS | `state is not None` | CHAIN_INVALID |
| T03 | any but GENESIS | `state is None` | CHAIN_INVALID |
| T04 | any but RESTORE, CLEAR | `phase == HALTED` | CHAIN_INVALID |
| T05 | any | `phase == FINAL` | CHAIN_INVALID |
| T06 | INPUTS, STAGE, FROZEN, DELIVERY, OPENED, AI | `state.notify is not None` | CHAIN_INVALID (an owner notice or user question is answered first) |

**New runs**

| id | kind | guard | effect |
|---|---|---|---|
| T10 | STAGE | Q; `body.new_run` with `tag in {A, B}`; `current is None`; case in `genesis.jobs` and not nonattempt; no run of (case, reader) exists; reader B: the A chain of the case has a last run that is FROZEN and (that run is not `restart_eligible`, or it is itself `A-restart1`, or it has flag `RESET_DIVERGED`) | new RUN `ACTIVE`, `current = key`; fields from body (§4.5) |
| T11 | STAGE | Q; `body.new_run` with `tag in {A-restart1, B-restart1}`; `current is None`; `restart_of` = the only run of (case, reader), FROZEN with `restart_eligible`, without `RESET_DIVERGED`, with no in-place interrupt; reader A: no B run of the case exists | new RUN `ACTIVE`, `current = key` |
| T12 | FROZEN | Q; `body.new_run` with `tag in {NA-A, NA-B}`, `commands` = [nonattempt, verify-frozen]; `current is None`; case marked nonattempt in `genesis.jobs`; no NA run of (case, reader); NA-B only after NA-A of the case | new RUN `FROZEN` (`frozen.visual = NOT_REACHED`) |
| T13 | STAGE | E; `body.new_run` with the tag of `current`; `R.status == INPUTS`; `body.prepare_inputs_sha256 == R.inputs.sha256` (r2, INT-10) | R `ACTIVE`, fields from body (§4.5) |
| T14 | STAGE, FROZEN | fallback: `body.new_run` and none of T10-T13 holds | CHAIN_INVALID |
| T15 | INPUTS | E; `current is None`; `body.tag` not used before in the series (r2, INT-10) | new RUN `INPUTS` with `inputs = {seq, sha256: sha(cjson(body.inputs))}`, `reprepares = 0`, `current = key` |
| T16 | INPUTS | fallback (Q or D mode, a run in flight, a reused tag) | CHAIN_INVALID |

**Run progress** (all require `body.run == current`, `R.status == ACTIVE`, `body.new_run == null`)

| id | kind | guard | effect |
|---|---|---|---|
| T20 | STAGE | not `open(R)`; every `body.consumed` item names an ARCHIVED role whose last archive has that `revision` and `tree_sha256` (the consumed value is the worker's own walk of the output folder just before the consumer command, §7.2 step 3; r2 INT-07); `body.refused` null; `body.review_incomplete` false; if `body.next` in {SCOPE_READER, GENERATE, VISUAL_REVIEW} then `body.start` is present and its role is that step's role (S, G, V), else `body.start` is null | update R from body (§4.5); consumed roles get `consumed`; START per T30-T32 |
| T21 | STAGE | not `open(R)`; `body.review_incomplete`; `body.refused` in `REVIEW_CONTINUABLE = {REVIEW_INCOMPLETE, REVIEW_NOT_FRESH_CONTEXT, REVIEWER_CONVERSATION_ID_REQUIRED}` (r2, IMP-17; all three are refusals of the review's content raised before consumption, R43); the newest V role is ARCHIVED, not consumed; its `review_incomplete < 2` | V role `CONTINUED`, `continuations += 1`, `review_incomplete += 1`, `continued_boot = entry.boot_id`; R snapshot/record updated (the runner wrote the attempt file and a refused entry, R17) |
| T22 | STAGE | `body.review_incomplete` and the V role's `review_incomplete >= 2` | CHAIN_INVALID (the third refusal freezes, T24 with `REVIEW_INCOMPLETE_LIMIT`, O61) |
| T23 | STAGE | not `open(R)`; `body.refused` not null and not in `REVIEW_CONTINUABLE`; the record or ledger changed (`commands[-1].record_sha256_after != R.record_sha256` or the ledger sha changed) | R updated from body; `phase = HALTED`, `halt = {seq, code: 'RUNNER_REFUSED'}` |
| T24 | FROZEN | not `open(R)`; consumed as in T20; `commands[-1]` is verify-frozen with next DONE; every flag in `body.flags_added` is justified (§4.6); `body.restart_eligible` is false when `R.restart_of` is not null (r2, IMP-06) | R `FROZEN`, `frozen` from body, `flags += flags_added`, `current = null`; `notify = {seq, what}` when `body.notify` |
| T25 | STAGE, FROZEN | fallback: `body.run != current`, or `R.status != ACTIVE`, or `open(R)`, and no other row holds | CHAIN_INVALID |

**START** (applied inside T20, T42; never alone)

| id | START `reason` | guard | effect |
|---|---|---|---|
| T30 | `STAGE` | the role has no attempt yet in R (`attempt = 1`), or (role G, attempt 2) after an in-place interrupt recorded by the same STAGE (`commands` holds interrupt with next GENERATE, `R.roles.G1.resolution.action == INTERRUPT`, `R.interrupts` empty and `R.restart_of` null: at most one rule-3 restart) | new ROLE `STARTED`, `starts = [start_no 1]`; for the in-place case `R.interrupts += [{seq, form: in_place}]` |
| T31 | `REBASE` | `body.rebase` (STAGE) re-runs from `R.rebase_bind`; the superseded START is the head entry's START, never OPENED and never ARCHIVED; the role's `supersedes == 0` (one superseding START per attempt of any reason, shared with T43, O58; r2 INT-05); with `genesis.gates.p1_conversation_list == 'yes'`, `R.rebase_bind.list_shows_none == true` | old start `superseded_by = k+1`; new start `start_no k+1`, status `STARTED`; `supersedes = 1`; flag `REBASED` |
| T32 | any other reason in a STAGE | — | CHAIN_INVALID (TST-01, F2: a second START for an attempt only via T31, T43, T44, T45) |

**OPENED and AI**

| id | kind | guard | effect |
|---|---|---|---|
| T35 | OPENED | `body.run == current`; the role is `STARTED`; `body.start_no == latest(role).start_no` | role `OPENED`, `opened = {seq, conversation, utc}` |
| T36 | OPENED | fallback | CHAIN_INVALID |
| T37 | AI | `body.run == current`; `body.revision == 1`; role `STARTED` (allowed only when `genesis.gates.p1_conversation_list == 'yes'`) or `OPENED`; `body.start_no == latest(role).start_no`; `body.start_boot_id == latest(role).boot_id == entry.boot_id`; `body.ended` | role `ARCHIVED`, `archives = [{seq, 1, tree, conversation, boot}]` |
| T38 | AI | role V `CONTINUED`; `body.revision == len(archives) + 1`; `entry.boot_id == role.continued_boot`; `body.ended` | role `ARCHIVED`, archive appended |
| T39 | AI | fallback (no START, already ARCHIVED or RESOLVED, a START or continuation of another boot, OPENED missing where required) | CHAIN_INVALID |

**RESTORE** (`body.resolutions` lists one item per open role: `{"run", "role", "attempt", "start_no", "ended", "files_found", "outcome", "forced", "transcript", "list_shows_none", "action", "owner_check"}`)

| id | guard (per resolution, after the series guard `phase in {OPEN, HALTED}`) | action and effect |
|---|---|---|
| T41 | (r2, INT-10) E; `current` run R has status `INPUTS`: exactly one of `body.reprepare` (allowed only when `R.reprepares == 0`) and `body.abandon` is present, naming R; `body.resolutions` empty | `reprepare`: `R.reprepares = 1` (logged; the plan prepares again, §11.4); `abandon`: `R.status = ABANDONED`, `current = null`, `notify = {seq, ASK_USER}` |
| T42 | when `body.rebase` is present, T49's undo is applied first and `state'` is the result; otherwise `state' = state` (r2, INT-04). The set of (run, role, attempt) in `body.resolutions` equals `open(state')` exactly; at most one item has an action that needs `body.start`, and `body.start` is present iff one does; `body.rebase` only per T49; `body.reprepare`/`body.abandon` only per T41; `body.delivery_question` is present iff mode E and the current run has `delivery.prepared_seq` set and `delivery.sent` false (r2, INT-06) | each item per T43-T47; with `delivery_question`: `notify = {seq, ASK_USER, about: DELIVERY}`, `R.delivery.resend_ok = false`; `restores += 1`; `release_sha256`, `kit_sha256` updated from the entry (KIT-1: S5 already checked acceptance) |
| T43 | `outcome == NO_CONVERSATION`: role `STARTED` (never OPENED), the role's `supersedes == 0` (no superseding START of any reason in this attempt, r2 INT-05), `genesis.gates.p1_conversation_list == 'yes'`, `list_shows_none == true`, `files_found == false`, `forced == null` | action `SUPERSEDE`: `body.start` with reason `NO_CONVERSATION`, `start_no = k+1`; old start `superseded_by`; `supersedes = 1`; role stays `STARTED`; flag `START_SUPERSEDED` (O58) |
| T44 | `outcome == NOTHING_WRITTEN`, role S or G, status `STARTED` or `OPENED`, `ended == true`, `files_found == false`, `forced == null`, and (`transcript == exported` with a `transcript/` member, or `transcript == not_available`) | Q: action `INTERRUPT` (role `RESOLVED`; next stage is the runner's interrupt, §7.4); with `not_available`, `owner_check = true` and flag `OWNER_CHECK` (O55). E (r2, INT-10, INT-13): attempt 1 with `exported`: action `EVERYDAY_RETRY` with `body.start` (attempt 2, reason `EVERYDAY_RETRY`); attempt 1 or 2 with `not_available`: action `FREEZE_LOST` (an unchecked reading never buys a second conversation in everyday mode, where no owner check precedes delivery); attempt 2 with `exported`: action `FREEZE_EXHAUSTED` |
| T45 | `outcome == NOTHING_WRITTEN`, role V, status `STARTED` or `OPENED`, `ended`, `files_found == false`, `forced == null`, and (`transcript == exported` with a `transcript/` member, or `transcript == not_available` with `owner_check == true`) (r2, INT-02: the same guard as T44, O45, O55) | `R.replacements == 0` and (Q, or E with `exported`): action `REPLACE`, `body.start` = V attempt+1 reason `REPLACEMENT`, `R.replacements = 1`; with `not_available` (Q only), flag `OWNER_CHECK` (the owner's verdict is required before scoring, §10.3; a write found makes the run's visual `FAILED_BY_RESET`); otherwise (replacement used, or E with `not_available`) action `FREEZE_VISUAL_FAILED`, flag `VISUAL_QA_FAILED_BY_RESET` |
| T46 | role V `CONTINUED` (outcome recorded as `CONTINUED`, not asked) | action `FREEZE_VISUAL_FAILED`, flag `VISUAL_QA_FAILED_BY_RESET` (O57, F1) |
| T47 | `outcome in {WRITTEN, UNSURE}`, or `forced != null` (`FILES_FOUND`, `NOT_ENDED`, `NOT_ENDABLE`, `NO_CONVERSATION_NOT_ALLOWED`, `NO_LIST`) | S/G: action `FREEZE_LOST`, flag `AI_OUTPUT_LOST` (O46); V: action `FREEZE_VISUAL_FAILED`, flag `VISUAL_QA_FAILED_BY_RESET` |
| T48 | fallback: an item matching none of T43-T47 (for example NO_CONVERSATION from OPENED, a second superseding START, NOTHING_WRITTEN with files found, V NOTHING_WRITTEN with `not_available` and no `owner_check`, REPLACE twice) | CHAIN_INVALID |
| T49 | `body.rebase`: `rebase.head_seq == state.seq`; `state.undo.seq == state.seq`; the head entry was a STAGE or FROZEN of `undo.run` that had parts; `rebase.missing_parts` is non-empty, names only parts of the head, and each has two absence observations at least `w_abs` apart (§8.4 step 5; r2, INT-05); if the head carries a START, its role's `supersedes == 0` (counted against O58's one superseding START per attempt) and, with `p1_conversation_list == 'yes'`, `rebase.list_shows_none == true`; no open role besides the head's own START, which disappears with the undo (so T42 compares with `open` after the undo, r2 INT-04) | `runs[undo.run] = undo.before` (or removed if `before` is null, a new run), `current = undo.current_before`, `ledger = undo.ledger_before`, `notify = undo.notify_before`; `R.rebase_bind = {head_seq, base_seq: R.snapshot.seq, bound: body.rebase.bound, list_shows_none: body.rebase.list_shows_none}`; the head's START (if any) is kept as a superseded record in `R.rebases` (with its utc, for the O52 window) |
| T50 | fallback: RESTORE where T41/T42 fail | CHAIN_INVALID |

**Acknowledgements, delivery, halts, final**

| id | kind | guard | effect |
|---|---|---|---|
| T52 | ACK | `state.notify.seq == body.for_seq` and `what` matches; with `about == DELIVERY` the answer is `arrived` | `notify = null`; with `about == DELIVERY` (r2, INT-06): `arrived == yes`: `R.delivery.sent = true` (the plan runs the freeze chain with `delivery_sent`); `arrived == no`: `R.delivery.resend_ok = true` (the plan prints DELIVER `to=user` once more, §11.4) |
| T53 | ACK | fallback | CHAIN_INVALID |
| T55 | DELIVERY | E; `body.run == current`; `R.next == DELIVER`; `R.delivery.prepared_seq` null (or reverted by T49); `body.standard_sha256 == R.saved_qa.deliverable_sha256`; parts are exactly `DELIV01`, `DLOG01` | `R.delivery.prepared_seq = seq`, `sent = false`, `resend_ok = true` |
| T56 | DELIVERY | fallback | CHAIN_INVALID |
| T58 | HALT | `phase == OPEN` | `phase = HALTED`, `halt = {seq, code}` |
| T59 | CLEAR | `phase == HALTED`, `body.halt_seq == halt.seq`, `body.code == halt.code`, `body.kit_sha256 == entry.kit_sha256`, and `body.kit_change` names the halted kit (`from_kit_sha256 == state.kit_sha256`) and this one, with `config_only == true` recomputed from its two member lists (r2, INT-08, IMP-05: the session builds those lists from the two kit zips, §8.2, never from `unpack_kit`'s return value) | `phase = OPEN`, `halt = null`, `clears += [...]` |
| T60 | HALT, CLEAR | fallback | CHAIN_INVALID |
| T62 | FINAL | Q; `current is None`; `open(state)` empty; `notify is None`; for every (case, reader) of `genesis.jobs`: the last run of its chain is FROZEN; no FROZEN last run with `restart_of == null` is `restart_eligible` without a restart run (unless `RESET_DIVERGED`); a restart run is never restart-eligible (T24, r2 IMP-06) | `phase = FINAL`, `final = {seq}` |
| T63 | FINAL | fallback (T62 fails, or E) | CHAIN_INVALID |

Undo record: every STAGE, FROZEN and DELIVERY effect first sets `state.undo = {seq, run, before: deepcopy(R or null), current_before, ledger_before, notify_before, parts: [names]}`; every other kind sets `state.undo = {seq, run: null, ..., parts: [names]}` (only `parts` used, for S4). Only T49 reads `before`.

### 4.4 START record

`{"role", "attempt", "start_no", "reason": "STAGE" | "REBASE" | "NO_CONVERSATION" | "REPLACEMENT" | "EVERYDAY_RETRY", "prompt": abs path, "prompt_sha256", "folder": abs path, "output": abs path, "utc": entry.utc, "boot_id": entry.boot_id}`. `prompt`/`folder` are the runner's NEXT arguments for every role (S, G; for V `prompt = qa/VISUAL_REVIEW_PROMPT.md`, `folder = qa/`, R45); `folder` is what OPEN_CONVERSATION prints as the conversation's access scope. `output` is the one folder the role writes and the helper walks for its AI entry (r2, IMP-03): S `scope/reader/output/`, G `<run_dir>/output/`, V `qa/visual_review/`. `prompt_sha256 = sha_file(prompt)` at build time. For REPLACEMENT the V prompt is the same file (its sha must be unchanged, else `HALT PROMPT_CHANGED`, TST-06).

### 4.5 Effect of a STAGE or FROZEN on R (T10-T13, T20, T24)

`R.next, R.next_args, R.codes` from body; `R.record_sha256 = commands[-1].record_sha256_after`; `R.snapshot = {seq, tree_sha256}`; `R.png` from `body.png` (unchanged when null); `R.saved_qa`, `R.carrier_sha256`, `R.response_frozen` (true once a `finish` command ran past `freeze_response`, i.e. `generation_record_sha256` non-null or `next` after finish); `state.ledger = {seq, sha256, bytes}` when the entry has a `ledger/` member; `R.reruns += [{seq, stage}]` when `body.rerun`; `R.rebases += [...]`, `R.rebase_bind = null` and flag `RESET_DIVERGED` when `body.rebase.diverged`.

### 4.6 Flags a FROZEN may add (`flags_added`), and their justification

| flag | allowed only when |
|---|---|
| `AI_OUTPUT_LOST` | the run's last resolution has action `FREEZE_LOST` (T44 E with `not_available`, T47) and no other |
| `VISUAL_QA_FAILED_BY_RESET` | the run's last resolution has action `FREEZE_VISUAL_FAILED` |
| `RESTART_EXHAUSTED_BY_RESET` | the last resolution has action `INTERRUPT` and `commands` holds the interrupt refused with `INTERRUPT_RESTART_USED` (R9), or the last resolution has action `FREEZE_EXHAUSTED` (E attempt 2, T44); r2 (INT-13): the two flags are keyed to distinct actions, so exactly one of them is justified |
| `REVIEW_INCOMPLETE_LIMIT` | `commands` holds a third visual-record refused with a code in `REVIEW_CONTINUABLE` and the V role's `review_incomplete == 2` |
| `RESET_DIVERGED` | `body.rebase.diverged` |

Any other flag, or a justified flag missing from `flags_added`, is CHAIN_INVALID (the fold recomputes the expected set and compares).

### 4.7 Invariants the table enforces

| id | invariant | rows |
|---|---|---|
| I1 | at most one open role in the series; one open conversation per role | T20/T24/T25 refuse progress while a role is open; T35-T38 act only on the current run; T42 resolves all open roles at once |
| I2 | START before OPEN: OPEN or CONTINUE is printed only for a role whose START (or REVIEW_INCOMPLETE) is in a confirmed entry | T20 (an AI NEXT needs a START in the same entry), T21; plan prints OPEN only from a confirmed state (§6.1) |
| I3 | reader A's chain frozen before reader B prepares | T10 |
| I4 | at most one rule-3 restart per (case, reader) | T11, T30 (in place), T44 (Q: INTERRUPT; the runner's limit R9 backs it) |
| I5 | O55: NOTHING_WRITTEN without a transcript allowed only with OWNER_CHECK (Q), for S, G and V; in E never (S/G FREEZE_LOST, V FREEZE_VISUAL_FAILED) | T44, T45 (r2, INT-02, INT-10) |
| I6 | O56: every resolution with `transcript == exported` carries the transcript member | T42 (payload check) |
| I7 | O57: a continued V resolves only as visual failure, no replacement | T46 |
| I8 | O58: at most one superseding START per attempt of any reason (NO_CONVERSATION or REBASE), only from a never-opened START; with a conversation list, only when it shows none | T31, T43, T49 (r2, INT-05) |
| I9 | O61: at most 2 REVIEW_INCOMPLETE continuations per V role; the third freezes | T21, T22, §4.6 |
| I10 | one run in flight | T10-T12 and T15 need `current is None`; T13 continues the INPUTS run in `current` |
| I11 | a consumer stage consumes exactly the archived output: the tree sha the worker measures just before the consumer command equals the last archive's (§7.2 step 3) | T20, T24 |
| I12 | at most one replacement reviewer per run | T45 |
| I13 | an AI entry belongs to the boot of its START (or continuation); anything crossing a reset is resolved by RESTORE | T37, T38 |
| I14 | nothing after FINAL; only RESTORE or CLEAR while HALTED | T04, T05 |
| I15 | contiguous seq, linked hashes, exact confirms | S2, S4, §3.10 |
| I16 | owner notices and user questions are acknowledged before work continues | T06 |
| I17 | at most one OPEN per START and one CONTINUE per continuation, across every commit of a boot (keyed marks, §2.3) and across resets (RESTORE resolves the role first) | §7.1 rows 5-11 (plan, not fold; tested by oracle O2, r2 INT-01) |
| I18 | an everyday job is prepared again at most once, logged | T13, T41 (r2, INT-10) |

### 4.8 Test enumeration contract

`TABLE` is data. `tests/test_core_table.py` (§14.1):
1. builds abstract states from the product `phase {OPEN, HALTED, FINAL} x run {none, ACTIVE at next in {GENERATE, SCOPE_READER, VISUAL_REVIEW, FREEZE, DELIVER_CHECK, DELIVER, STOP_X, OWNER_DECISION}, FROZEN} x role status of each of S1, G1, G2, V1, V2 in {absent, STARTED, OPENED, ARCHIVED, CONTINUED, RESOLVED}` (pruned to states reachable by some entry sequence, computed by a breadth-first search over generated entries, depth 12);
2. for every entry kind and every reachable abstract state, generates the canonical entries of that kind (one per body variant listed in §3.5 and per resolution outcome) and asserts that `apply` either matches exactly the rows the spec lists for that (kind, state) or raises ChainInvalid with the expected row id (a series guard, or the kind's fallback);
3. asserts every row id is hit at least once, and no (state, entry) pair matches two positive rows (series guards and fallbacks are not guards in this sense, §4.1); the golden file includes (r2, INT-04) a RESTORE with `rebase` over a head STAGE carrying START-V and PNG parts, its S4 variant with `copies: []` for the missing part, and the same RESTORE with a missing part not in `missing_parts` (CONFIRMS_MISMATCH);
4. stores the enumeration as `tests/table_golden.json` (row id per (kind, state class)); a change of the table needs a reviewed golden update.

---

## 5. commit(): the save-point primitive

Every Drive write of the journal goes through commit. `cli.py`/`worker.py` call it with an entry draft (all keys but `state`, `state_sha256`, `confirms`, `prev_sha256`) and the part sources; `vio/savepoint.py` does the I/O. The setup files (`FINGERPRINT_PASS_*`, `SELFTEST_*`, the kit zip) use the same upload-FIND-attest loop (steps 5-7) without a chain.

### 5.1 Steps

1. **Refuse a second commit.** If `PENDING.json` exists, `commit` is not called: `go` resumes the pending one (step 5). Calling it anyway is `STOP INTERNAL_PENDING_EXISTS`.
2. **Fold.** `confirms` = the previous commit's files from `STATE` (head entry and parts, with the copies attested); `prev_sha256 = STATE.head.sha256`; `state' = core.fold.apply(state, draft)`. ChainInvalid: `STOP INTERNAL_ILLEGAL_TRANSITION` (nothing written, sticky local HALT). The entry is completed with `state'` and `state_sha256`.
3. **Write.** `require_space`; parts first (PNG via `PartWriter` from the PNG tar stream; DELIV/DLOG/LEDGER/ALLFZ via `durable.write`), each non-empty and sealed; then the entry tgz (`write_tgz` + `durable.seal`, re-read with `Archive` and `check`); then `PENDING.json` (`phase ENTRY`, every name/path/sha/md5/bytes, `tries` zero, `state_after_sha256`, the post-commit actions). Any DurableError: HALT DISK_FULL/WRITE_FAILED, nothing printed but the HALT block.
4. **Size.** Entry over `max_entry_bytes`: `HALT ENTRY_TOO_LARGE` before PENDING.
5. **Print the entry upload** (state code `SAVE`; nothing in the block reveals the outcome):
```
CPSV series=Q1 head=000124 kit=0a1b2c3d4e5f at=000124-0007-3c9a1e mode=qualification state=SAVE
UPLOAD /home/agent/cps/outbox/journal/CPSJ_Q1_000125.tgz TO CPS/qualification AS CPSJ_Q1_000125.tgz
FIND CPS/qualification NAME CPSJ_Q1_000125.tgz
DO: ATTEST bash /home/agent/cps/vm.sh found --at 000124-0007-3c9a1e --name CPSJ_Q1_000125.tgz (--file ID:MD5:SIZE ... | --none)
```
   `tries[name].uploads = 1`, `finds_since_upload = 0`.
   A RESTORE with `body.rebase` (r2, INT-05) also prints `FIND <series folder> NAME <part>` for every name in `rebase.missing_parts`, and its ATTEST asks `--name <part> --none` for each: that is the third absence check. Any copy of a missing part is `STOP REBASE_PART_APPEARED HANDBACK C` (local sticky); nothing after it is printed or run. The RESTORE entry itself may already be on Drive: a later session whose head is a rebase RESTORE checks its missing parts again before anything runs (§8.5 C5b), so the stop recurs after a reset, and the audit reports the RESTORE (§10.1 step 2).
6. **Attest found** (`vm.sh found`, §6.2). Validation first (REFUSED leaves everything unchanged and reprints the block). Then, for the entry name:
   - one or more copies, **every** copy with the local md5 and size: accepted. Same-md5 duplicates are fine (all ids are kept). The Dot never sees an md5 from the helper, so a match proves a real lookup;
   - any copy with another md5 or size: `STOP FORK HANDBACK C` (local sticky HALT; nothing more is uploaded);
   - `--none`, `finds_since_upload == 0`: print `DO: WAIT seconds=<w>` (`w = max(30, 2 * gates.p2_lag_seconds)`), `finds_since_upload = 1`; the next `go` prints FIND and the ATTEST line again (no UPLOAD);
   - `--none`, `finds_since_upload == 1`, `uploads < 3`: print the UPLOAD, FIND and ATTEST lines again; `uploads += 1`, `finds_since_upload = 0`;
   - `--none`, `finds_since_upload == 1`, `uploads == 3`: `STOP UPLOAD_FAILED HANDBACK C` (local sticky HALT, OP-02).
   The PENDING file is rewritten durably after each of these transitions, before printing.
7. **Parts** (only after the entry is confirmed; their number reveals the outcome): `phase PARTS`; print every part's UPLOAD (to its folder, in order), then every FIND, then one ATTEST:
```
CPSV series=Q1 head=000124 kit=0a1b2c3d4e5f at=000124-0008-77d2b0 mode=qualification state=SAVE
UPLOAD /home/agent/cps/outbox/journal/CPSJ_Q1_000125_PNG01.part TO CPS/qualification AS CPSJ_Q1_000125_PNG01.part
UPLOAD /home/agent/cps/outbox/journal/CPSJ_Q1_000125_PNG02.part TO CPS/qualification AS CPSJ_Q1_000125_PNG02.part
FIND CPS/qualification NAME CPSJ_Q1_000125_PNG01.part
FIND CPS/qualification NAME CPSJ_Q1_000125_PNG02.part
DO: ATTEST bash /home/agent/cps/vm.sh found --at 000124-0008-77d2b0 --name CPSJ_Q1_000125_PNG01.part (--file ID:MD5:SIZE ... | --none) --name CPSJ_Q1_000125_PNG02.part (--file ID:MD5:SIZE ... | --none)
```
   Each part follows the step-6 loop independently; the reprinted block lists only the parts still unconfirmed (and re-UPLOADs only those whose wait has passed).
8. **Done.** Record every copy in `STATE` (`head` = this entry with its first id, md5, bytes, sha256; `state = state'`), write `STATE.json` durably with `post` = PENDING's post actions and `marks` copied unchanged (a commit never clears a mark, §2.3; r2 INT-01), then remove `PENDING.json` and fsync the folder, then run each post action (removing it from `STATE.post` durably as it completes), then compute `core.plan.next_action` and print its block in the same output.

### 5.2 Prefix variant (only when `gates.p2_prefix_search == 'yes'`)

Steps 5 and 7 print one `FIND <folder> PREFIX CPSJ_<S>_<seq6>` instead of per-name FINDs for files in the series folder. `found` must then list every name the lookup returned that starts with the prefix; a name not in this commit is a foreign file: `STOP FORK`. DELIV/DLOG parts (another folder) keep per-name FINDs.

### 5.3 What a commit never does

- It never prints a runner result, an OPEN or CONTINUE line, a NOTIFY_OWNER, an ASK_USER, a DELIVER or a HANDBACK before step 8 (O54, OP-01). The only lines before step 8 are the header with `state=SAVE`, UPLOAD, FIND, WAIT, DOWNLOAD (md5-hidden variant) and the found ATTEST.
- It never builds entry N+1 while N or one of N's parts is unconfirmed (contiguity, §3.1).
- It never deletes a local file named in PENDING before step 8.

### 5.4 Post-commit actions (`post`, executed in order after step 8)

| action | after | does |
|---|---|---|
| `EVICT run` | FROZEN (Q, D, E) | §7.6 |
| `UNPLACE_FROZEN path sha` | the STAGE that prepared a B run or a restart run | removes a placed `FROZEN.json` folder (§7.7) after checking it holds only that file with that sha |
| `DROP_ATTEST files` | AI, RESTORE, DELIVERY, ACK | deletes the committed attest files and transcripts (they are in the entry) |
| `DROP_LOCAL names` | every commit | deletes the local entry and part files of this commit (their bytes are on Drive and their sha256 in STATE) |
| `DROP_DOWNLOADS` | RESTORE | empties `inbox/journal/`, `inbox/verify/`, `inbox/kit/` |

A failing post action (OSError) is `HALT POST_ACTION_FAILED` (the commit itself is complete; the halt stops further work until cleared).

### 5.5 md5 hidden (`gates.p2_md5_visible == 'no'`)

The ATTEST line reads `(--file ID:SIZE ... | --none)`. After a `found` with copies, `phase VERIFY`: print, for every copy,
```
DOWNLOAD CPS/qualification ID <id> TO /home/agent/cps/inbox/verify/<name>.<k>
DO: RUN bash /home/agent/cps/vm.sh go
```
`go` compares each download's size and sha256 with the local file: all equal is accepted (the entry's md5 is computed locally and recorded with each id); any difference is `STOP FORK`; a missing download is REFUSED `DOWNLOAD_MISSING` (the block is printed again). Downloads are deleted after the comparison. (+1 call per file, design §D.)

---

## 6. Operator surface

### 6.1 The rule for the Dot

After a reset (or in a new operator chat) the VM's `/home/agent` is empty, so the Dot first restores the repository at the release commit, then runs `session_start.sh` (r2, IMP-04). The bootstrap lines, printed verbatim in the README (§6.8):
```
COMMIT=<the 40-hex commit of your last CPSV-REPO line>       # from your notes; if your notes are gone: step 0 below
[ -d ~/cps/repo/.git ] || git clone -q https://github.com/cookielolalex/CPS.git ~/cps/repo
git -C ~/cps/repo fetch -q origin "$COMMIT"; git -C ~/cps/repo checkout -q --detach "$COMMIT"
bash ~/cps/repo/deploy/vm2/session_start.sh --commit "$COMMIT" [--hint <seq6> --kit <hex12>]
```
- Step 0, when the Dot's notes did not survive the reset (OQ-9): `FIND CPS NAME VM2_RELEASE.md` and download it; the maintainer keeps this file in the static folder (O53), and its one line `commit: <40 hex>` gives COMMIT. Without it the Dot stops and tells the owner (`SESSION_NO_COMMIT`, case C); it never guesses a commit.
- A failed checkout after a partial clone: remove `~/cps/repo` (it holds no state) and repeat the three git lines once; a second failure is `SESSION_GIT_ERROR` (case C).
- `session_start.sh` checks `git -C BASE/repo rev-parse HEAD` equals `--commit` (`STOP SESSION_COMMIT_MISMATCH`), and the session (§8.1 step 5, modified `check_layout_release`) checks it equals RELEASE.json `repository.commit` (`LAYOUT_RELEASE_MISMATCH`). It prints `CPSV-REPO commit=<40 hex>` once per session, which the Dot keeps in its notes with the last `CPSV` line.

Otherwise: run `bash /home/agent/cps/vm.sh go`, then do the block it prints, exactly. Every block is:

```
CPSV series=<S> head=<seq6|000000> kit=<hex12|none> at=<seq6>-<nnnn>-<hex6> mode=<qualification|everyday|drill|setup> state=<STATE>
UPLOAD <abs> TO <folder> AS <name>        (0..n, do them in order)
FIND <folder> NAME <name>                 (0..n)    or    FIND <folder> PREFIX <prefix>    or    LIST <folder> PREFIX <prefix> NEWEST <k>
DOWNLOAD <folder> ID <id> TO <abs>        (0..n)
DO: <exactly one terminal action>
```
plus, for a refusal, one line `REFUSED <CODE>` right after the header, before the reprinted lines. There are no THEN chains, OPTION lists or `{TOKEN}`s (F6, OP-04). The Dot keeps the last `CPSV` line in its notes: its `series`, `head` and `kit` are the hint after a reset.

Exit codes: 0 follow the block; 3 the block ends in `DO: STOP`; 4 refused (state unchanged; the current block is printed again after the REFUSED line); 2 usage (argument syntax; the current block is printed again).

`STATE` codes in the header (outcome-neutral during a commit): `SETUP`, `KIT`, `SELFTEST`, `HEAD`, `RESTORE`, `PLACE`, `SAVE`, `WORK`, `AI`, `ATTEST`, `NOTIFY`, `IDLE`, `DELIVER`, `FINAL`, `STOP`, `HALT`.

Printing rules: every `<abs>` and `<folder>` is printed `shlex.quote`d, and the helper checks `shlex.split(printed) == [value]` before printing (a failure is `STOP INTERNAL_PRINT`). Helper-chosen paths are ASCII without whitespace; folder names are the `FOLDERS` constants and may contain a space (`'Dots Folder/CPS_JOB_RECORDS'`). r2 (IMP-14): a case id appears only as a component of a helper-built absolute path (job folders under `BASE/qual/<root>/<case>/` and `BASE/jobs/<utc14>/<case>/`, the runner's NEXT `prompt=`/`folder=` paths, and `everyday_inputs/<case>/`), after the case id passed `CASE_ID_RE` (R16) and is therefore ASCII without whitespace or quote; it is never a free token or a command argument value. No line contains a title, a cell value, any runner output, or a non-ASCII character: where the runner's path holds the title (the standard `<name>(未填).xlsx`, R32), the helper prints its ASCII copy `BASE/deliver/<run8>/STANDARD.xlsx` instead (§2.1, §11.3).

### 6.2 The three commands

1. `bash /home/agent/cps/vm.sh go` (no arguments; any argument is exit 2).
2. `bash /home/agent/cps/vm.sh found --at <at> (--name <N> (--file <F> [--file <F> ...] | --none))+` where `<F>` is `ID:MD5:SIZE` (or `ID:SIZE` when md5 is hidden) or `<N>:ID:MD5:SIZE` under the LIST variant (§8.4).
3. `bash /home/agent/cps/vm.sh answer --at <at> key=value [key=value ...]`.

`found` and `answer` are accepted only when `BLOCK.expect.command` is that command; otherwise `REFUSED COMMAND_NOT_EXPECTED`.

### 6.3 Validation of attested values (`core/names.py`)

Order: argument syntax (exit 2), then `--at` (STALE_AT), then the global refusals, then each value's pattern, then cross-checks. All on `str`, `re.fullmatch`, `re.ASCII`.

**`--at`.** `at = '%06d-%04d-%s' % (head_seq, step, hex6)`, `hex6 = sha(cjson({"state_sha256", "pending_sha256" (or null), "step", "lines_sha256": sha of the block lines without the header}))[:6]`. `step` increments by 1 for every block printed that differs from `BLOCK.lines`, and is reset to 1 whenever the head seq changes (r2, IMP-15); a reprint of the same block keeps the same `at`. A step above 9999 at one head is `STOP INTERNAL_STEP_OVERFLOW` (the restore's longest path, a gallop from 1 with waits at N = 999,999, prints under 200 blocks). `--at` must equal `BLOCK.at`: otherwise `REFUSED STALE_AT` (an answer to an older block, or from before a reset, never applies). After a reset `BLOCK.json` is gone, so every old `--at` is STALE_AT.

**Global refusals** (any value, any key; code `VALUE_FORBIDDEN`): any of the characters `{`, `}`, `<`, `>`, `'`, `"`, backtick, `$`, `\`; any whitespace or newline (including a trailing `\n`, SAFE-05), any non-ASCII character, an empty value. **Placeholder refusal** (`VALUE_PLACEHOLDER`, r2 IMP-02), applied only to values of the free-text patterns `FREE_TEXT = {CONV, MODEL, PLATFORM, EFFORT, ID, CASE_ID, COPYPATH}` (the set is a constant in `core/names.py`): a value equal (case-insensitive) to any key name, any pattern name (`CONV`, `UTC`, `CASE_ID`, `ID`, `MD5`, `SIZE`, ...), or any string in config `doc_samples` (README examples). Enumerated patterns (`YES`, `YESNO`, `OUTCOME`, `TRANSCRIPT`) admit only their listed values, so `ended=yes` is never a placeholder; `TOOLS` items are checked only against `doc_samples`, so `tools=web` is accepted although `web` is also a key; `UTC`, `MD5`, `SIZE` cannot spell a name. Keys must be exactly the set `BLOCK.expect.keys` lists (`ARG_MISSING_KEY`, `ARG_EXTRA_KEY`, `ARG_DUPLICATE_KEY`).

**Patterns:**

| pattern | regex / rule |
|---|---|
| `ID` | config `drive_id_re` (default `[A-Za-z0-9_-]{20,80}`) |
| `MD5` | `[0-9a-f]{32}`, must equal the local md5 for the copy to count (otherwise that copy is foreign: FORK, §5.1) |
| `SIZE` | `[1-9][0-9]{0,11}`, must equal the local bytes (same rule) |
| `CONV` | config `conversation_re` (P1) |
| `UTC` | `[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z`, parseable, and within `BLOCK.expect.window[key]` (`UTC_OUT_OF_WINDOW`) |
| `MODEL`, `PLATFORM` | `[A-Za-z0-9._:-]{2,64}` |
| `EFFORT` | `[a-z0-9_-]{1,32}` |
| `YES` | `yes` |
| `YESNO` | `yes` or `no` |
| `TOOLS` | `none` or `[a-z0-9_-]{1,32}(,[a-z0-9_-]{1,32}){0,31}` |
| `OUTCOME` | `NOTHING_WRITTEN`, `WRITTEN`, `UNSURE` or `NO_CONVERSATION` |
| `TRANSCRIPT` | `exported` or `not_available` |
| `CASE_ID` | the runner's `CASE_ID_RE` (R16); checked before anything is written (SAFE-02) |
| `COPYPATH` | r2 (IMP-14): exactly `$HOME/cps-deliveries/<case>/<user>/<utc14>/PERSONAL_COPY.xlsx` (key `copy`) or `.../PERSONALIZATION_LOG.json` (key `log`), with `<case>` the run's case id, `<user>` `[a-z0-9_-]{1,40}` (the user's ASCII profile key, the same in both answers) and `<utc14>` the same in both and not earlier than the DELIVER block; realpath equal to the path, a regular file with one link, 1 byte..`png_part_bytes` (§11.3) |

Windows: `started_utc`, `ended_utc`, `opened_utc` lie in `[latest(role).utc, now]`, and `started_utc <= ended_utc`; for the generator this is inside the runner's window (R21), because a START's `utc` is never earlier than the end of the stage that printed NEXT (§3.4 `utc`).

**Files the Dot writes** (checked when the block asks for them): `attest/final_message.txt` (UTF-8, 1..8192 bytes, no `<...>` or `{...}` span, `FINAL_MESSAGE_INVALID`); an exported transcript at the exact printed path (non-empty, at most `max_transcript_bytes`, `TRANSCRIPT_FILE_MISSING`/`TRANSCRIPT_TOO_LARGE`).

### 6.4 Terminal actions (exact forms)

| action | the Dot does | then |
|---|---|---|
| `RUN bash /home/agent/cps/vm.sh go` | runs it | follows the new block |
| `ATTEST bash /home/agent/cps/vm.sh found --at A --name N (--file ID:MD5:SIZE ... \| --none) [--name N2 (...)]` | does the block's UPLOAD/FIND lines, then runs `found` with what each FIND returned: one `--file` per copy, or `--none` | follows the output |
| `ATTEST bash /home/agent/cps/vm.sh answer --at A k1=PATTERN1 k2=PATTERN2 ...` | runs `answer` with a value for each key, matching the pattern named | follows the output |
| `OPEN_CONVERSATION role=R prompt=P folder=F then=when_ended` | opens a new conversation, gives it the full text of file P as its only message. For `role=S` or `role=G` it may use only folder F. For `role=V` (r2, IMP-03, as RUN_JOB_COMMANDS Stage 5) it may open only the PNG files the prompt P lists (under F) and write only `F/visual_review/VISUAL_REVIEW.json` | when it has ended: RUN go |
| `OPEN_CONVERSATION role=R prompt=P folder=F then=now` (when `p1_conversation_list == no`, OPENED mandatory) | the same | as soon as the prompt is sent: RUN go (which asks for `conversation` and `opened_utc`, commits OPENED, then prints AWAIT_CONVERSATION) |
| `AWAIT_CONVERSATION role=R conversation=C` | waits for that conversation to end | RUN go |
| `CONTINUE_CONVERSATION role=V conversation=C message=M` | sends the text of file M in conversation C | when it has ended: RUN go |
| `END_CONVERSATION role=R after=UTC [conversation=C]` | ends (stops) the CPS conversation of that role opened after UTC (named C when given), if it is still running | RUN go |
| `EXPORT_TRANSCRIPT role=R to=P [conversation=C] [after=UTC]` | exports that conversation's transcript to P; if the platform cannot, does nothing | RUN go |
| `NOTIFY_OWNER file=P ATTEST bash ... answer --at A notified=YES` | tells the owner the content of P | runs the answer |
| `ASK_USER file=P ATTEST bash ... answer --at A k=PATTERN` | asks the user the question in P | runs the answer |
| `DELIVER file=P to=copy ATTEST bash ... answer --at A copy=COPYPATH log=COPYPATH` | everyday: makes the user's personal copy of P (the ASCII copy of the standard file) with that user's preferences, saved as `PERSONAL_COPY.xlsx` with its `PERSONALIZATION_LOG.json` in `~/cps-deliveries/<case>/<user>/<utc14>/` (§11.3) | runs the answer |
| `DELIVER file=P to=user ATTEST bash ... answer --at A sent=YES` | everyday: sends file P to the requesting user, under the standard file's name `<name>(未填).xlsx` from the `JOB_TITLE.json` the Dot wrote (the helper never prints the title, §11.3) | runs the answer |
| `WAIT seconds=N` | waits N seconds | RUN go |
| `STOP <CODE> HANDBACK C` / `STOP <CODE> HANDBACK B` / `STOP IDLE` | stops; for C uploads nothing more and tells the owner the code (case C), for B tells the owner qualification generation is complete | nothing |

### 6.5 Which answers are asked where

| situation | keys |
|---|---|
| first `go` of a boot (session) | `operator_model=MODEL platform=PLATFORM` |
| G conversation ended | `ended=YES conversation=CONV started_utc=UTC ended_utc=UTC platform=PLATFORM model=MODEL effort=EFFORT single_user_message=YESNO memory=YESNO custom_instructions=YESNO web=YESNO connectors=YESNO file_uploads=YESNO other_agents=YESNO tools=TOOLS transcript=TRANSCRIPT`, plus `attest/final_message.txt` |
| S conversation ended | `ended=YES conversation=CONV prompt_pasted=YES` |
| V conversation ended (revision 1) | `ended=YES conversation=CONV` |
| V continuation ended | `ended=YES` |
| OPENED (then=now) | `conversation=CONV opened_utc=UTC` |
| restore, open role, not continued, no file found | `ended=YESNO outcome=OUTCOME transcript=TRANSCRIPT` + `list_shows_none=YESNO` only when NO_CONVERSATION is admissible (T43) + `conversation=CONV` when not yet known (every role, V included: the transcript decides NOTHING_WRITTEN for V too, T45) |
| restore, rebase over a head carrying a START, `p1_conversation_list == yes` | `list_shows_none=YESNO` ("does your conversation list show a conversation opened after <START utc>?"; r2 INT-05) |
| restore, continued V, or files found | `ended=YESNO transcript=TRANSCRIPT` (outcome not asked) |
| owner notice | `notified=YES` |
| everyday idle (`state=IDLE`) | `case=CASE_ID` (the README: only when a user asked for a job and the inputs are in `everyday_inputs/<case>/`); the answer commits INPUTS before anything runs (r2, INT-10) |
| everyday delivery | `copy=COPYPATH log=COPYPATH`, then `sent=YES` |
| everyday after a reset with PREPARED not SENT | `arrived=YESNO` (ASK_USER committed by the RESTORE, T42; r2 INT-06) |
| everyday after AI_OUTPUT_LOST | `asked=YES` (the user was told the job failed; a new job starts only at the user's request, O49) |

### 6.6 session_start.sh (bootstrap; 80 lines)

`bash /home/agent/cps/repo/deploy/vm2/session_start.sh --commit <40hex> [--hint <seq6> --kit <hex12>]`:
1. `$HOME` absolute without whitespace, `BASE`, `TOOLS` likewise; `BASE/.git` must not exist; else prints a STOP block (`SESSION_LAYOUT`) and exits 3.
2. The script's repository must be `BASE/repo`, and `git -C BASE/repo status --porcelain --untracked-files=no` must **succeed** and print nothing: a git error is `STOP SESSION_GIT_ERROR` (SAFE-06, never fail-open); a dirty tree `STOP SESSION_REPO_DIRTY`. `set -euo pipefail` is not used; every failure path prints a full block.
3. Creates the BASE folders (never `BASE/ledger`).
4. Setup: if `TOOLS/var/cps_vm2_setup_ok` does not hold `<boot_id> <commit>`, starts `setup_vm_user.sh` and `check_env.py` **detached** (`setsid nohup`, logs in `outbox/setup_<utc14>.log`, marker written by the detached job on success, `setup_failed` marker on failure) and records it in `outbox/SETUP.json`; never in the foreground (SAFE-07).
5. Writes `BASE/vm.sh` atomically (0755), and `outbox/v2/HINT.json` from `--hint/--kit` when given (validated: SEQ6, hex12).
6. Checks `git -C BASE/repo rev-parse HEAD == --commit` (`STOP SESSION_COMMIT_MISMATCH`), then prints `CPSV-REPO commit=<40 hex>`, `CPSV ... state=SETUP` and `DO: RUN bash /home/agent/cps/vm.sh go`, exit 0.

`go` then waits for the setup (`DO: WAIT seconds=60` while `SETUP.json` names a live process of this boot; `STOP SETUP_FAILED HANDBACK C` with the log uploaded to `reports/` through the setup-file loop on failure).

### 6.7 The `go` dispatcher (cli.py, 150 lines)

```
go():
  lay = Layout(); check_layout_basic(lay)                      # reused
  with HelperLock(lay, wait=10):                               # reused; busy -> WAIT 30 block
    cleanup_leftovers(lay)                                     # modified
    if HALT.json: clear per §13.5 or print its STOP block
    if DETACHED.json: wait_block (modified) -> running: WAIT; died: STOP WORKER_DIED; done: absorb result
    validate cache (§2.5) -> invalid: session/restore machine (§8, core/session.session_next)
    if not session ready for this boot: session machine (§8.1-8.3, core/session.session_next)
    if PENDING: continue the commit (§5.1 step 5-7)
    step = core.plan.next_action(view(STATE, local facts, now))
    carry out step (print block, spawn worker, or commit)
```
`found` and `answer` run the same prologue, then apply their values to the pending commit, restore observation, or the plan's question, and end by printing the next block.

### 6.8 README.md

`deploy/vm2/README.md` holds the Dot's procedure: §6.1 (with the bootstrap lines and step 0), §6.4, §6.5 as text, the restore summary, and the list `doc_samples` (every example value in the README, copied into the kit config by `make_kit` tooling of the maintainer). A test (§14.6) checks that every example value in the README is in the test kit's `doc_samples` and refused.

---

## 7. Stages

### 7.1 next_action (core/plan.py, total)

`next_action(view)` where `view = {state, marks, local: {job_dirs present, pass ok, gates ok, setup state, worker state}, now}` returns one Step. Evaluated top to bottom; the first match wins; the last row is `Stop('UNCLASSIFIED', 'C')` (committed as a HALT entry when the journal is sound).

| # | condition | Step |
|---|---|---|
| 1 | `state is None` (head search found no entry, §8.4) | Q/D: GENESIS (§7.12); E: GENESIS without ledger |
| 2 | `phase == FINAL` | `Stop('FINAL', 'B')` after the FINAL parts are confirmed |
| 3 | `phase == HALTED` | CLEAR when config `clear` matches (§13.5), else `Stop('HALTED_' + halt.code, 'C')` |
| 4 | `notify` set | NOTIFY_OWNER or ASK_USER block for `notify.seq` (§7.9, §11) |
| 5 | current run R has a role with status `STARTED`, `opened == null`, and no mark `OPEN:<run>:<key>:<start_no>:<start seq>` for its latest start (r2, INT-01, IMP-01: an OPENED role never matches this row) | the latest start's `boot_id` must be this boot (else `Stop('UNCLASSIFIED', 'C')`: a valid cache never holds another boot's open START, I13); write the mark durably, then print OPEN_CONVERSATION (`then=now` if `p1_conversation_list == 'no'`, else `then=when_ended`) |
| 6 | that role is `STARTED`, its OPEN mark is set, `p1_conversation_list == 'no'` | Ask OPENED keys (§6.5); on valid answers commit OPENED (T35) |
| 7 | that role is `OPENED`, no AWAIT mark for its latest start | write the mark, print AWAIT_CONVERSATION |
| 8 | that role is (`STARTED` with its OPEN mark) or (`OPENED` with its AWAIT mark), role G, `p1_transcript_export == 'yes'`, no EXPORT mark | write the mark, print EXPORT_TRANSCRIPT to `BASE/transcripts/<run8>_G<a>_<k>.<ext>` |
| 9 | that role is (`STARTED` with its OPEN mark) or (`OPENED` with its AWAIT mark) | Ask the role's end keys (§6.5); on valid answers build and commit the AI entry (§7.5) |
| 10 | a V role `CONTINUED`, no CONTINUE mark for this continuation | write the mark, print CONTINUE_CONVERSATION with the message file (§7.8) |
| 11 | a V role `CONTINUED`, its CONTINUE mark set | Ask `ended=YES`; commit the AI entry (revision n+1) |
| 12 | R has a resolution with action `INTERRUPT` not yet run | RunChain(interrupt) (§7.4) |
| 13 | R has a resolution with action `FREEZE_LOST`, `FREEZE_EXHAUSTED` or `FREEZE_VISUAL_FAILED` not yet run | RunChain(freeze) |
| 14 | R has `rebase_bind` | RunChain(re-run of the head's chain from the base snapshot, bound, §7.10) |
| 15 | R has a role `ARCHIVED`, not consumed | RunChain(consumer: S scope-finish, G finish, V visual-record) |
| 16 | E: `R.next == DELIVER`, no `delivery.prepared_seq` | DELIVER `to=copy` block (§11.3) |
| 17 | E: `prepared_seq` set, `sent` false, `resend_ok` true, no mark `DELIVER_USER:<run>:<prepared_seq>:<seq of the last ACK of the run, or 0>` (r2, INT-06) | write the mark, print the DELIVER `to=user` block; on `sent=YES`: RunChain(freeze) with `delivery_sent` |
| 18 | E: `prepared_seq` set, `sent` false, `resend_ok` true, that mark set | print only `DO: ATTEST ... answer --at A sent=YES` (the send is never printed twice for one permission) |
| 19 | E: `prepared_seq` set, `sent` true (ACK `arrived=yes`, T52) | RunChain(freeze) with `delivery_sent` |
| 20 | E: R has status `INPUTS` | RunChain(prepare) from the committed inputs (first prepare, or the one logged re-prepare after T41) |
| 21 | `current is None`, Q/D | the next run in order (§7.11): RunChain(nonattempt or prepare), or FINAL when none is left |
| 22 | `current is None`, E | IDLE: Ask `case=CASE_ID` |
| 23 | otherwise | `Stop('UNCLASSIFIED', 'C')` |

E with `prepared_seq` set, `sent` false and `resend_ok` false (a RESTORE's `delivery_question`) never reaches rows 17-18: row 4 prints the ASK_USER first, and only its ACK sets `resend_ok` or `sent` (T52).

`marks` (in STATE.json, §2.3; durable before the block is printed) record which non-repeatable instruction was printed in this boot, keyed by the identity of the start, continuation or delivery permission they belong to. r2 (INT-01, IMP-01): no commit clears a mark (an OPENED, HALT, CLEAR, ACK or any other commit copies `marks` unchanged, §5.1 step 8); a mark stops mattering only because its key names a start, continuation or permission that is no longer the current one. Together with row 5 matching only a `STARTED` role without an OPENED record, this gives: one OPEN per START (also after the OPENED commit, and after a HALT and its CLEAR in the same boot while a role is open), one AWAIT per OPENED, one CONTINUE per continuation, one DELIVER `to=user` per permission. A lost `marks` means a lost cache, which takes the restore path, and that resolves every open role from Drive (§8.6) before anything is printed. So the helper never prints a second OPEN for one START (F2, OP-01; oracle O2 and `test_int01_*`, §14.4).

### 7.2 The detached worker

`go` runs every runner command, the snapshot and the entry build in a worker (reused `spawn`, `worker_alive`; modified `cmd_worker`, `wait_block`):
1. `go` holds `HelperLock`; refuses a second worker (`DETACHED.json` names a live worker: WAIT block); writes `DETACHED.json` through `spawn(ctx2, 'chain', info, lock)`. `info = {"run", "first": <sub>, "chain_ctx": {...}, "base_seq", "bind" | null, "resolution" | null}`. The worker inherits the lock (spawn hands the descriptor over, v1 r3 failure-R3-03).
2. `spawn` calls the modified `wait_block(ctx2, wrap_foreground_seconds)`; `running` prints `DO: WAIT seconds=30` (state `WORK`); the next `go` waits again. `died` (no result, process gone, same boot) is `STOP WORKER_DIED HANDBACK C` (sticky local HALT; the job folder is left untouched for the maintainer). A result of another boot never exists (the boot changed: restore path).
3. The worker (`worker.py`): recomputes the fingerprint and compares with `STATE.fingerprint_sha256` (O47; mismatch: no runner command runs, result `FINGERPRINT_CHANGED`, `go` prints the self-test path); probes the job lock with `JobLock` (a tool of a killed runner may still hold it, R6): up to 60 tries 60 s apart, each try acquiring and **releasing** it at once, then `JOB_BUSY_TOO_LONG` (STOP C). **JobLock scope** (r2, IMP-12): the worker holds `JobLock(job_dir)` only for that probe, for the consumer measurement below, for the snapshot (§3.8) and for the evict walk (§7.6), and releases it before every `run_runner`; it never holds it while a runner command runs (the runner takes its own non-blocking flock on the same folder, R6, and would refuse `JOB_BUSY`). **Consumer measurement** (r2, INT-07): before a consumer command (`scope-finish`, `finish`, `visual-record`), under JobLock, the worker walks the role's `output` folder (§4.4) with the strict `tree_list`, computes its tree sha256, and compares it with the role's last archive (`archives[-1].tree_sha256`); a difference is a committed `HALT AI_OUTPUT_CHANGED` with no runner command run; equal, the measured value (never the archive's copy) goes into `body.consumed[].tree_sha256`. It then releases JobLock and runs the chain (§7.3), each command through the reused `run_runner` (argv only, `-I -B`, stdout and stderr appended to spawn's log `outbox/<kind>_<wid>.log`, never printed); after the chain: snapshot (§3.8), entry draft, commit steps 1-4 (fold, durable writes, PENDING); writes the result `{"status": "pending" | "halt", "code", "detail"}` durably to spawn's `out` path `outbox/<kind>_<wid>.out` (r2, IMP-11); sets `exit` in DETACHED.json.
4. `go` absorbs the result: `pending` continues with commit step 5 (prints the SAVE block; for a HALT entry the block is the same `state=SAVE` upload); `halt` (a local sticky STOP, the commit itself impossible) prints the HALT block. r2 (INT-12, IMP-07): there is no `nothing` result. A runner refusal that changed nothing (other than `JOB_BUSY`) becomes a committed HALT entry `RUNNER_REFUSED` (§7.3); `JOB_BUSY` from the runner makes the worker wait and retry inside the same bounded loop as the JobLock probe; neither ever re-prints the same stage.

Before running each command the worker records `record_sha256_before` and `ledger_sha256_before`; after it, `_after`. A command "changed nothing" when both are equal and the job folder's tree sha is unchanged.

Parsing a runner result: the last two non-empty stdout lines must be one JSON object then `NEXT: <step>` or `REFUSED: <code>` (R3); `exit` must be 0, 3 or 4 and agree (0 with a CONTINUE_STEPS NEXT, 3 with STOP_/OWNER_DECISION or verify-frozen STOP, 4 with REFUSED) (R2). Anything else is `RUNNER_OUTPUT_UNPARSEABLE` (treated as a refusal: §7.3 last rows).

### 7.3 The chain table (core/plan.chain_next, bounded)

The worker starts with `first` and asks `chain_next(sub, result, counters, mode, bind)` after each command. At most 6 runner commands per chain; a seventh is `STOP INTERNAL_CHAIN_TOO_LONG`.

r2 (IMP-07, INT-12): `chain_next` evaluates the rows **in the order listed, first match wins**, and the order puts every specific row before any general one; `tests/test_core_table.py` checks that no row is shadowed (each row has a canonical (sub, result) that reaches it). "Changed" means the record sha, the ledger sha or the job folder's tree sha differs from before the command (§7.2).

| # | after | result | next | entry kind |
|---|---|---|---|---|
| X1 | any, while `bind` is set (a rebase re-run, §7.10) | the (sub, first NEXT token or REFUSED code, codes) of command i differs from the head's `commands[i]`, or at the head chain's last command a bound value differs | freeze (or, if the differing command is itself freeze/verify-frozen, as rows X8-X12) | FROZEN with flag `RESET_DIVERGED` |
| X2 | any | `REFUSED: JOB_BUSY` | wait and retry the same command (bounded with the JobLock probe, §7.2 step 3; then `STOP JOB_BUSY_TOO_LONG`) | — |
| X3 | visual-record | `REFUSED:` a code in `REVIEW_CONTINUABLE` (REVIEW_INCOMPLETE, REVIEW_NOT_FRESH_CONTEXT, REVIEWER_CONVERSATION_ID_REQUIRED; R17, R43), V `review_incomplete < 2` | end | STAGE `review_incomplete` (T21) |
| X4 | visual-record | the same codes, V `review_incomplete == 2` | freeze | flag `REVIEW_INCOMPLETE_LIMIT` (O61) |
| X5 | interrupt | `REFUSED: INTERRUPT_RESTART_USED` | freeze | flag `RESTART_EXHAUSTED_BY_RESET` |
| X6 | any | `REFUSED: <code>` (or unparseable output or exit, code `RUNNER_OUTPUT_UNPARSEABLE`) and the record or ledger changed (R5) | end | STAGE with `refused` (T23: HALTED) |
| X7 | any | `REFUSED: <code>` (or unparseable, as above) and nothing changed (R40, R8: e.g. RESPONSE_WRITTEN, or a refusal before the job folder exists) | end | HALT entry `RUNNER_REFUSED` (detail: the code; no STAGE, so no result is bound, design B4; the HALT survives a reset and the same command is never re-run silently) |
| X8 | verify-frozen | `NEXT: STOP_FROZEN_FOLDER_CHANGED` | end | HALT `FROZEN_FOLDER_CHANGED` (the folder is not evicted) |
| X9 | verify-frozen | `NEXT: DONE` | end | FROZEN (`restart_eligible` per §3.5, R14, R44; `notify` set when the run's final NEXT is `STOP_*` or `OWNER_DECISION`) |
| X10 | freeze | `NEXT: STOP_FREEZE_INCOMPLETE`, fewer than 2 retries | freeze | — |
| X11 | freeze | `NEXT: STOP_FREEZE_INCOMPLETE` after 2 retries | end | HALT `FREEZE_INCOMPLETE` |
| X12 | freeze, nonattempt | `NEXT: DONE` | verify-frozen | — |
| X13 | interrupt | `NEXT: STOP_TECHNICAL_INTERRUPTION` | freeze | — |
| X14 | interrupt | `NEXT: GENERATE ...` (in place) | end | STAGE with START G attempt 2 (T30) |
| X15 | prepare, scope-finish, finish | `NEXT: SCOPE_READER/GENERATE/VISUAL_REVIEW ...` | end | STAGE with START of that role (I2) |
| X16 | visual-record | `NEXT: FREEZE` (Q) | freeze | — |
| X17 | visual-record | `NEXT: DELIVER_CHECK` (E) | deliver-check | — |
| X18 | deliver-check | `NEXT: DELIVER file=...` | end | STAGE (`next DELIVER`; the worker writes `BASE/deliver/<run8>/STANDARD.xlsx`, sha-checked; the runner's path is not recorded in the body, only its sha via `saved_qa`) |
| X19 | any | `NEXT: STOP_*` (including STOP_RECORD_CONFLICT) or `NEXT: OWNER_DECISION` | freeze | — |
| X20 | any | anything else | end | HALT `UNCLASSIFIED` |

Runner v4 never prints `NEXT: STOP_INTERRUPTED` (r2, IMP-13; R7 corrected, R46): `reconcile` appends the INTERRUPTED entry to the record silently and the command goes on to print its own result. A reconciled interruption is therefore seen only as a record change, and the command's printed result decides the row (typically X6 with `STAGE_ALREADY_COMPLETED`, or X19). In v2 the case arises only if a killed runner's marker survives, i.e. after `WORKER_DIED` in the same boot, which is already a STOP.

The worker never runs `deliver-check` in Q (R35), never `interrupt` in E (R10), and never a command after `verify-frozen`.

### 7.4 Runner argv (vio/runner.py)

`M` is `STATE.operator.model`; `D` the run's `job_dir`; paths absolute. Every argv element is validated ASCII without whitespace except `M`, which matches `MODEL`.

| sub | argv after `cps_job.py` |
|---|---|
| prepare (Q, D) | `prepare --release BASE/runtime/RELEASE.json --job BASE/runtime/qualification/jobs/<case>/JOB.json --job-title-file BASE/runtime/qualification/jobs/<case>/JOB_TITLE.json --jobs-root BASE/qual/<root> --reader <A\|B> --qualification --admission <release.qualification.admissions[0].path> --operator-model M` |
| prepare (E) | `prepare --release BASE/runtime/RELEASE.json --job BASE/everyday_inputs/<case>/JOB.json --job-title-file BASE/everyday_inputs/<case>/JOB_TITLE.json --jobs-root BASE/jobs/<utc14> --operator-model M` |
| nonattempt | `nonattempt --release BASE/runtime/RELEASE.json --admission <...> --case <case> --reader <R> --jobs-root BASE/qual/nonattempts_<R> --operator-model M` |
| scope-finish | `scope-finish --job-dir D --reader-response D/scope/reader/output/SCOPE_READER_RESPONSE.json --reader-prompt-sha256 <START.prompt_sha256> --reader-conversation-id <AI.conversation> --operator-model M` |
| finish | `finish --job-dir D --response D/<run_dir>/output/response.json --generator-model <AI.attested.model> --generation-record D/run/GENERATION_RECORD.json [--transcript BASE/transcripts/<run8>_G<a>_<k>.<ext>] --operator-model M` |
| visual-record | `visual-record --job-dir D --review D/qa/visual_review/VISUAL_REVIEW.json --reviewer-conversation-id <the V conversation of revision 1> --operator-model M` |
| deliver-check | `deliver-check --job-dir D --operator-model M` |
| interrupt | `interrupt --job-dir D --reason TECHNICAL_VM_RESET --started-utc <latest(role).utc> --ended-utc <min(RESTORE.utc, now - 1 s)> [--conversation-id <conversation if known>] --operator-model M` |
| freeze | `freeze --job-dir D --operator-model M` |
| verify-frozen | `verify-frozen --job-dir D` |

`TECHNICAL_VM_RESET` matches the runner's `TECHNICAL_RE` (R10). `--started-utc` is the START's `utc` (whole seconds, never earlier than the end of the stage that printed NEXT, §3.4), so the runner's window `last.ended_utc <= t0 <= t1 <= command start` holds (R10). `<run_dir>` is the runner's `generation.run_dir` (`run/A` or `run/B`), read from the NEXT folder argument.

### 7.5 AI entries and GENERATION_RECORD.json

When the role's end answers are valid (§6.5):
1. Walk the role's output folder (the START's `output`, §4.4: S `D/scope/reader/output`, G `D/<run_dir>/output`, V `D/qa/visual_review`) with the strict `tree_list` (SAFE-01: any unsupported entry is `HALT WALK_UNSUPPORTED_ENTRY`); bytes over `max_ai_output_bytes`: `HALT AI_OUTPUT_TOO_LARGE`. The helper never opens the files' content (it hashes them).
2. G: read `attest/final_message.txt` (§6.3); with `transcript=exported` the file at the EXPORT path must exist (§6.3).
3. Build the AI entry (`ai/` = the walked tree; `transcript/`, `attest/final_message.txt` for G) and commit it (§5). The S, G entry needs `ended=yes` and the START's boot (T37).

After the AI entry is confirmed, the consumer chain starts in the worker, which first measures the output folder again and binds the consumed tree sha to that measurement (§7.2 step 3, I11; r2 INT-07). For G the worker then writes `D/run/GENERATION_RECORD.json` (`cps.generation-record.v1`, `write_new`, mode 0644; an existing file is `HALT GENERATION_RECORD_EXISTS`):

| field | value |
|---|---|
| `schema`, `case_id`, `reader` | `cps.generation-record.v1`, the run's case and reader |
| `platform`, `model`, `effort`, `conversation_id` | the AI entry's attested values |
| `started_utc`, `ended_utc` | attested (already checked inside the START window) |
| `prompt_sha256` | the START's `prompt_sha256` (sha of `run/GENERATOR_PROMPT.md` when OPEN was printed); the worker re-checks that the file still has it (`HALT PROMPT_CHANGED`) |
| `single_user_message` | `true` iff answer `yes` |
| `features` | the six YESNO answers as booleans |
| `tools_enabled` | `[]` for `none`, else the comma list |
| `final_message` | the committed final message text |
| `transcript_status` | the answer |
| `transcript_sha256` | with `exported`: sha256 of the committed transcript |
| `transcript_not_available_reason` | with `not_available`: `"the operator's platform did not export the transcript (attested)"` |

`finish` gets `--transcript` only when the status is `exported` (R21, R43); the transcript file is placed back at its BASE/transcripts path from the AI entry if a restore happened in between.

### 7.6 Evict after FROZEN (post action, SAFE-01)

1. Strict walk of `job_dir` (modified `tree_list`) under `JobLock`.
2. The walk must equal the FROZEN entry's `payload.members` under `job/` plus `payload.png.files`, path by path, type, mode and sha256 (`HALT EVICT_MISMATCH` naming counts only; nothing deleted).
3. Write `outbox/frozen_json/<tag>_<case>_FROZEN.json` (the FROZEN.json bytes; their sha256 must be `frozen.frozen_sha256`).
4. `remove_tree(job_dir)` (reused), then remove the empty jobs-root folder if it is empty. A failure mid-delete is `HALT EVICT_FAILED` (the next restore treats the run as FROZEN; its folder is not needed).

### 7.7 Placing an earlier run's FROZEN.json (runner restart and reader B)

The runner reads `<earlier job_dir>/FROZEN.json` when it prepares reader B (to decide whether A's restart is unused) and when it prepares a restart (R14). For those two prepares the worker first places it (modified `place_frozen`): the folder `job_dir` of that earlier run must not exist; it is created (0755) with only `FROZEN.json` (0444), whose sha256 must equal `state.runs[earlier].frozen.frozen_sha256` and the ledger's freeze entry. Source: `outbox/frozen_json/` or, after a reset, the earlier run's FROZEN entry (one download: the `job/FROZEN.json` member). The prepare STAGE's post action `UNPLACE_FROZEN` removes it after the commit (§5.4); a placed folder holding anything else is `HALT PLACED_FROZEN_CHANGED`.

### 7.8 REVIEW_INCOMPLETE (O61, F1)

The runner refuses `visual-record` with `REVIEW_INCOMPLETE`, writes `qa/visual_review_attempts/<seq>.json` and appends a refused record entry (R17). r2 (IMP-17): `REVIEW_NOT_FRESH_CONTEXT` (reviewer model or effort missing) and `REVIEWER_CONVERSATION_ID_REQUIRED` (missing, placeholder, or different from the `--reviewer-conversation-id` the helper passed) are raised at the same point, with the same attempt file and refused entry (R43), and are content slips of the reviewer of the same kind; together they form `REVIEW_CONTINUABLE` and share O61's limit of 2 continuations (**SPEC DECISION** SD-17, §17). The worker commits a STAGE with `review_incomplete` (T21, V role CONTINUED), with member `attest/continue.txt`, one of:
```
REVIEW_INCOMPLETE: The visual review at <D>/qa/visual_review/VISUAL_REVIEW.json is incomplete (<n> problems). Complete it in the same file:
<up to 20 of the runner's problem strings from its REFUSED detail: page and item names only>
REVIEW_NOT_FRESH_CONTEXT: In <D>/qa/visual_review/VISUAL_REVIEW.json, reviewer.kind must be fresh_context_visual_reviewer and reviewer.model and reviewer.effort must be your observed model id and reasoning setting (or unknown). Correct only the reviewer block.
REVIEWER_CONVERSATION_ID_REQUIRED: In <D>/qa/visual_review/VISUAL_REVIEW.json, reviewer.conversation_id must be exactly this conversation's id as your platform shows it; if your platform does not show it, remove the key. Correct only the reviewer block.
```
(fixed helper texts; no value the reviewer wrote is echoed).
The plan then prints `CONTINUE_CONVERSATION role=V conversation=<the V conversation> message=BASE/attest/continue_<run8>_V<a>_<n>.txt` (once), then asks `ended=YES`, commits AI revision n+1 (T38), then runs `visual-record` again. A third refusal freezes with `REVIEW_INCOMPLETE_LIMIT` (§7.3). A reset while CONTINUED is resolved by T46 (visual QA failed, no replacement, O57).

### 7.9 STOP_*, OWNER_DECISION and the owner notice

A chain that ends in a runner `STOP_*` or `OWNER_DECISION` freezes and commits FROZEN with `notify = NOTIFY_OWNER` and member `attest/notice.txt`:
```
CPS run <run key> stopped: <final NEXT code>; codes: <runner codes>. The run is frozen (<frozen_sha256[:12]>). Entry CPSJ_<S>_<seq6>.
```
(codes and names only). After the commit is confirmed the plan prints `NOTIFY_OWNER file=BASE/attest/notice_<seq6>.txt ATTEST ... notified=YES`; the answer commits ACK (T52); then the next run starts. The notice is never printed before its FROZEN commit is confirmed (O54).

### 7.10 Re-runs: unbound and bound (O44, O54)

- **Unbound**: after a restore with a run in flight and nothing open (§8.5 C8), the stage that would follow the head re-runs as normal; the STAGE body carries `rerun: {after_seq, unbound: true}` and the run gets flag `RERUN_UNBOUND`. It was never shown (its commit never landed), so nothing binds it (O54).
- **Bound (rebase)**: the head entry is visible but one of its parts is missing, so nothing after it was printed (the parts are printed only after the entry is confirmed, and OPEN only after the parts). The RESTORE (T49) reverts the run to the base snapshot (the entry before the head for that run) and sets `rebase_bind.bound = {next, codes (sorted), saved_qa.deliverable_sha256, saved_qa.sha256, carrier_sha256, png.whole_sha256}` from the head. The worker re-runs the head's chain from the placed base, command by command; r2 (IMP-07): after each command i its (sub, first NEXT token or REFUSED code, codes) must equal the head's `commands[i]`, and at the head chain's last command every bound value must be equal (chain row X1, the first row). If all are equal: the STAGE commits normally with `rebase: {diverged: false}`, the head's unopened START superseded (T31, at most one superseding START per attempt, O58). Otherwise: `diverged: true`, the chain continues to freeze, and the FROZEN carries flag `RESET_DIVERGED` (the run fails, O44).
  **Open item (§17 OQ-4):** if `SAVED_QA.json` or the PNG bytes embed a timestamp, every rebase diverges. The builder MUST test a rebase of `finish` on the invented job and, if `saved_qa.sha256` or `png.whole_sha256` differs between two runs on identical inputs, bind instead to `{next, codes, deliverable_sha256, carrier_sha256}` and record the change for the review.

### 7.11 Run order (qualification and drill)

Same order as v1's `qual_plan` (v1 lines 2271-2319), now read from `state` (never from Drive listings):
1. for reader A then B, for each JOBS case in `order`: a nonattempt case without its NA run: nonattempt;
2. for reader A then B, for each non-nonattempt case in `order`: no run of (case, reader): prepare (`BASE/qual/A` or `B`; reader B only when T10 allows, else the A restart first); a single run that is FROZEN with `restart_eligible` and not `RESET_DIVERGED` and without a restart: prepare the restart (`A_restart1`/`B_restart1`, with §7.7 placement). For reader B the A-chain's last FROZEN.json is placed first (§7.7);
3. none left: FINAL (§9.4).

A reader-A run frozen `RESET_DIVERGED` whose runner record would still allow a restart is `STOP QUALIFICATION_DIVERGED_RESTART_CONFLICT HANDBACK C` (as v1 T-18): the helper never restarts a diverged run and reader B cannot pass the runner's check.

### 7.12 GENESIS

Q, D: refused unless (a) the head search found no entry with double absence (§8.4), (b) no hint was given or the hint is `000000`, (c) `BASE/ledger` does not exist, (d) the released admission is listed with its sha256 and frozen before now, (e) a PASS exists for this fingerprint, (f) (r2, INT-09) the config series equals RELEASE.json `vm_helper.series` (§2.2), and (g) Q only: for every other k in 1..9, `CPSJ_Q<k>_000001.tgz` is absent twice, `w_abs` apart, from `CPS/qualification` (a fixed folder, §2.2); any copy is `STOP QUALIFICATION_SERIES_EXISTS HANDBACK C`. So a kit naming a new Q series or another folder cannot start a second qualification with a fresh runner ledger (the runner's `ADMISSION_FROZEN_AFTER_FIRST_PREPARE` is per ledger); the observations go into the GENESIS body (`other_series_absent`), and the audit checks every Q series in the folder (§10.1 step 1). Then the ledger is created exactly as v1 `cmd_genesis` (v1 lines 5844-5900): a genesis line `{type: genesis, ledger_id, helper, release_sha256, admission_sha256, jobs_sha256, boot_id, fingerprint_sha256, base}` appended through the runner's own `Ledger` class into a staging folder, then renamed to `BASE/ledger` (`check_ledger_identity` is the reused reader of that line). The GENESIS entry carries the ledger as a member. E: no ledger. The GENESIS commit's own FIND must show exactly one md5 (a lagging earlier genesis becomes FORK).

---

## 8. Session and restore after a reset

The session machine runs on the first `go` of a boot, and whenever the cache is invalid (§2.5). Its observations live in `RESTORE_WORK.json`; a reset during it starts it again from the top (nothing it did is on Drive until the RESTORE commit). Every step prints at most one block and ends in `RUN go` or an ATTEST; the order is fixed:

### 8.1 Steps

| # | step | blocks | stop codes |
|---|---|---|---|
| 1 | layout: `check_layout_basic` (reused); `$HOME`, uid recorded | — | `LAYOUT_*` (STOP C) |
| 2 | setup finished (§6.6) | WAIT | `SETUP_FAILED` |
| 3 | operator answer | `answer operator_model=MODEL platform=PLATFORM` | — |
| 4 | kit intake (§8.2) | FIND/DOWNLOAD, ATTEST found | `KIT_*`, `ARCHIVE_*` |
| 5 | config, gates (§12), `check_layout_release` (modified) | — | `CONFIG_INVALID`, `RELEASE_GATE_OPEN`, `LAYOUT_RELEASE_MISMATCH` |
| 6 | fingerprint: reused `fingerprint(lay)` | — | — |
| 7 | head search, download, verification (§8.4) | FIND/LIST, WAIT, DOWNLOAD, ATTEST found | `HEAD_CORRUPT`, `SCHEMA_INVALID`, `STATE_SHA_MISMATCH`, `CHAIN_INVALID`, `LINK_MISMATCH`, `HELPER_UNKNOWN`, `RELEASE_NOT_ACCEPTED`, `HINT_AHEAD`, `FORK` |
| 8 | identity: `head.home == $HOME` and `head.uid == uid` (P3) | — | `HOME_CHANGED` when a run is in flight or a role is open; otherwise allowed only if the kit's release names this layout (step 5 passed) |
| 9 | PASS (§8.3) | FIND, DOWNLOAD; or the self-test | `SELFTEST_FAILED` |
| 10 | clock: reused `clock_check(ctx, floor=head.utc, ...)` | WAIT (`CLOCK_WAIT`) | `CLOCK_BEHIND` |
| 11 | kit acceptance (r2, INT-08, IMP-05), decided against the kit the journal names, never against `BASE/runtime`: kit sha equals `head.kit_sha256`: accepted. Otherwise the session fetches the head's kit (§8.2 KIT_CHANGE) and compares member sets: config-only with only the changeable keys of §2.2 differing: accepted; otherwise accepted only when the new release is the genesis release or in the new kit's `accepts_release_sha256` and **no run is in flight**, where run in flight means `head.state.current is not None` or `open(head.state)` is non-empty (TEST-1, KIT-1). The comparison is recorded in the RESTORE (or CLEAR) body as `kit_change` | FIND, DOWNLOAD (2 calls, only when the kit changed) | `KIT_CHANGE_WITH_RUN_IN_FLIGHT`, `RELEASE_NOT_ACCEPTED`, `CONFIG_CHANGE_NOT_ALLOWED`, `GATES_CHANGED` |
| 12 | classify (§8.5) and carry out | per situation | per situation |
| 13 | commit RESTORE (§8.7) | SAVE | per §5 |

A fresh series (step 7 finds nothing) skips 8, 10, 11 and goes to GENESIS (§7.12) instead of 12-13.

### 8.2 Kit intake

The kit is `CPS/setup/SESSION_KIT_<kit12>.zip`, uploaded once by the Dot after it first rebuilt it (v1 parts route), FIND by exact name.
- With a hint `--kit <kit12>`: `FIND CPS/setup NAME SESSION_KIT_<kit12>.zip` then `DOWNLOAD CPS/setup ID <id> TO BASE/inbox/kit/SESSION_KIT_<kit12>.zip` (2 calls). Several copies: they must share one md5 (else `STOP FORK`). The zip's sha256 must start with `kit12`, its members pass `kit_members` (reused: archive rules and SHA256SUMS), and after step 7 its full sha256 must equal `head.kit_sha256` or pass step 11.
- Without a hint, or when the hinted kit is absent twice: the FOLDER_MANIFEST route. `FIND CPS NAME FOLDER_MANIFEST.md`, DOWNLOAD it to `BASE/inbox/cps/FOLDER_MANIFEST.md`; then the modified `session_kit` (v1 zip route or parts route through `deploy/make_kit.py assemble --expect <sha>`), which re-hashes the zip it uses (KIT-2). After a parts rebuild the zip is uploaded `TO CPS/setup AS SESSION_KIT_<kit12>.zip` through the setup-file loop (§5, no chain) so later restores take 2 calls.
- `unpack_kit(lay, members, run_in_flight)` (reused) is called only to install the accepted kit into `BASE/runtime`, with `run_in_flight` = the journal's value (step 11); its return value (`'same'`, `'config'`, `'unpacked'`) decides nothing, because after a reset `BASE/runtime` is empty and it always returns `'unpacked'` (cps_vm.py:2728-2757; r2 INT-08, IMP-05).
- **KIT_CHANGE** (r2, INT-08, IMP-05). When the kit's sha256 differs from `head.kit_sha256` (or, for a local sticky HALT cleared in the same boot, from `STATE.kit_sha256`), the session also fetches the kit the journal names: `FIND CPS/setup NAME SESSION_KIT_<head.kit12>.zip`, `DOWNLOAD` it to `BASE/inbox/kit/head/`, re-hash it (its sha256 must equal `head.kit_sha256`, else `STOP KIT_NOT_VERIFIED`) and read it with `kit_members`. It records `kit_change = {"from_kit_sha256", "to_kit_sha256", "from_members": [[path, sha256]], "to_members": [[path, sha256]], "config_only": bool, "config_keys_changed": [key], "run_in_flight": bool, "to_accepts_release_sha256": [hex]}` in the RESTORE or CLEAR body. `config_only` is true iff the two member lists differ only at `VM_HELPER_CONFIG.json`; the fold recomputes it from the lists (S5, T59), and the audit recomputes the lists from the two zips in the setup folder (§10.1 step 5).

### 8.3 PASS lookup (O47)

`FIND CPS/setup NAME FINGERPRINT_PASS_<fp64>.json`. A copy whose md5 equals `state.passes[fp64].md5` is accepted without download (1 call). Otherwise every copy is downloaded and the first that passes `validate_pass(ctx2, raw, fp64)` (reused) is accepted and recorded in the RESTORE body. None: the self-test runs (spawn `selftest`, reused `selftest_work`); on its result the helper writes `SELFTEST_<fp64>.json` (the suite's results file) and `FINGERPRINT_PASS_<fp64>.json` (v1 `cmd_fingerprint_pass` content, lines 5951-6012, including the checks on `tests == passed_count == selftest_expected_tests`, `visual_skipped false` and the tool shas), uploads both to `CPS/setup` and confirms them (§5 loop). A failed self-test is `STOP SELFTEST_FAILED HANDBACK C` with the results and log uploaded to `CPS/reports`. A self-test worker that died is retried once per boot; a second death is `STOP SELFTEST_WORKER_DIED` (OP-09). Until a PASS exists no runner command, OPEN or CONTINUE is printed (only the restore's END and EXPORT steps, which use no CPS tool).

### 8.4 Head search (design B6 step 4)

Pure state machine `core/plan.head_search(hint, observations, gates)` returning the next lookup or a verdict. `present(k)` means FIND `CPSJ_<S>_<k:06d>.tgz` returned copies (all one md5; two md5s: `FORK`); `absent(k)` means `--none`. A second absence of the same k counts only when observed at least `w_abs = max(60, 2 * p2_lag_seconds)` seconds after the first (the helper prints `WAIT seconds=w_abs` between them).

1. **Candidate N**:
   - with `gates.p2_newest_first == 'yes'`: `LIST <series folder> PREFIX CPSJ_<S>_ NEWEST 5`; the Dot answers `found --at A --file <name>:<id>:<md5>:<size> ...`; N = the largest seq listed (1 call);
   - else with a hint h > 0: FIND h. Present: gallop up from h (h+1, h+2, h+4, ...) until an absent k, then binary search between the last present and k. Absent (twice): `STOP HINT_AHEAD HANDBACK C` (the hint names an entry Drive does not have: a lost commit was shown, or the wrong series);
   - else: gallop from 1 (1, 2, 4, 8, ...) then binary search. `absent(1)` twice: a fresh series (GENESIS).
2. **Confirm N**: `present(N)`, `absent(N+1)` twice (with the wait), `absent(N+2)` once. A present N+1 or N+2 restarts step 1 with that candidate (at most 3 restarts, then `STOP HEAD_UNSTABLE`).
3. **Download N** to `BASE/inbox/journal/`: Archive and `check`, `validate_entry`, `state_sha256`, helper tree accepted, runner pin, release accepted (S5/S6); any failure: `STOP HEAD_CORRUPT` / the specific code (local sticky HALT).
4. **Link**: `FIND N-1`: every copy's md5 must equal `N.confirms[0]` md5 (`LINK_MISMATCH`). For N = 1 nothing.
5. **Head parts**: FIND each name in `N.parts`. r2 (INT-05): a part counts as missing only when it is absent twice, the two observations at least `w_abs` apart (the helper prints `WAIT seconds=w_abs` between them), exactly as for N+1; a part present at either observation is present. The RESTORE commit then checks every missing part a third time (§5.1 step 5): any copy is `STOP REBASE_PART_APPEARED`. The observations go into `RESTORE.body.rebase.absence`.
6. **Re-check without a hint** (r2, INT-11): in Q and D mode, when the head was found neither from a hint nor from a newest-first listing, the RESTORE commit is followed, before anything else is printed or run, by `WAIT seconds=w_abs`, then `FIND N+1` (must show exactly the RESTORE's own md5), `FIND N+2` and `FIND N+3` (must be absent); any other copy is `STOP FORK HANDBACK C`. This is a second look, minutes later, at the names a lost chat could hide; a search that misses the same names consistently for that long is not detected here but by the audit (`AUD_DUPLICATE_SEQ`, §10.1 step 1), and §12.2 records it as a residual risk.

Calls with a hint and md5 visible: FIND N, FIND N+1, FIND N+1, FIND N+2, FIND N-1, DOWNLOAD N, plus 0-3 part FINDs (design §D "lookups 5, head 1, parts 0-3"). Without a hint or newest-first listing: about 2 log2(N) + 5 lookups (about +20 at N = 1,500).

The RESTORE entry (seq N+1) itself is committed with §5, whose FIND of N+1 must show exactly one md5, ours: a lagging foreign N+1 that both absence checks missed becomes `FORK` before anything runs (the authenticated second absence check, design B6).

### 8.5 Classification (core/plan.classify, reads only the head, F3)

Input: `head.state`, `head.kind`, which head parts are present, the config `clear`, and the local facts (job folders present: always none after a reset). The first matching row wins; an unmatched situation is `UNCLASSIFIED` (committed as HALT when the journal is sound).

| # | situation | action |
|---|---|---|
| C1 | a step-3/4 failure | STOP with that code, HANDBACK C, local sticky HALT |
| C2 | `phase == HALTED` | config `clear` names this series, `halt.seq` and `halt.code` (and step 11 found the kit config-only): first, if `open(head.state)` is non-empty, the §8.6 resolution of the open role (END, place, re-walk, EXPORT, ATTEST; r2 INT-14, since T42 requires the RESTORE to resolve every open role); then RESTORE (with those resolutions), then CLEAR (§13.5), then the plan continues (the resolution's action runs after the CLEAR); else `STOP HALTED_<code> HANDBACK C` |
| C3 | `phase == FINAL` | every FINAL part present: `STOP FINAL HANDBACK B`; a part missing: re-upload it from the entry's `final/` member (§5 loop for that part only), then `STOP FINAL HANDBACK B` (OP-03) |
| C4 | head is DELIVERY and a DELIV/DLOG part is missing | re-upload it from the entry's `delivery/` member; then the rows below |
| C5 | head is STAGE or FROZEN with parts and one is missing (absent twice, `w_abs` apart, §8.4 step 5) | if the head carries a START whose role already used its superseding START (`supersedes == 1`): `STOP REBASE_LIMIT HANDBACK C` (local sticky; O58 allows one per attempt; r2 INT-05). With `p1_conversation_list == 'yes'` and a START in the head: ATTEST `list_shows_none` for a conversation opened after the START's utc; `no` is `STOP REBASE_CONFLICT HANDBACK C` (the OPEN was printed, so the part was confirmed once and its absence is false). Otherwise REBASE (T49): no END/EXPORT (the head's START was never printed), place the base, re-run bound (§7.10); the RESTORE's FIND checks the missing parts a third time (§5.1 step 5) |
| C5b | head is a RESTORE with `rebase` (its re-run STAGE not yet committed) | FIND every name in its `rebase.missing_parts` once: any copy is `STOP REBASE_PART_APPEARED HANDBACK C`; all absent: continue with the rows below (the rebase re-run is row 14 of §7.1) (r2, INT-05) |
| C6 | an open role | RESOLVE (§8.6) |
| C7 | E, current run with `delivery.prepared_seq` set and `delivery.sent` false (r2, INT-06: listed before the general C8 row, which in r1 came first and shadowed it) | PLACE the run (§8.5.1), RESTORE with `delivery_question` (T42 sets `notify = ASK_USER` "did the copy arrive?", `resend_ok = false`); never re-send blindly. The ACK decides (T52): `yes`: freeze chain with `delivery_sent`; `no`: DELIVER `to=user` once more |
| C8 | a current run with status ACTIVE, nothing open | PLACE the run (§8.5.1); the next stage re-runs unbound (§7.10), the RESTORE body records `rerun_expected` |
| C8b | E, current run with status `INPUTS` (INPUTS committed, no prepare STAGE) (r2, INT-10) | `R.reprepares == 0`: RESTORE with `reprepare` (logged; T41), then the plan prepares again from the committed inputs (their shas re-checked); `R.reprepares == 1`: RESTORE with `abandon` (the job fails; `notify = ASK_USER` "the job could not be prepared; a new job only at your request", O49) |
| C9 | no current run | RESTORE; then the plan's next run (Q: §7.11 with §7.7 placement; E: IDLE) |
| C10 | anything else | `UNCLASSIFIED` |

#### 8.5.1 Placement (vio/place.py, in a worker of kind `place`)

Into empty targets at the original absolute paths (R25: the runner keys the ledger by the resolved job folder path):
1. **Ledger** (Q, D): from the entry `state.ledger.seq` (downloaded by id from `state.files` unless it is the head): `BASE/ledger` must not exist; created 0755 holding only `LEDGER.jsonl` (0644); sha256 must equal `state.ledger.sha256`; `check_ledger_identity` (reused) must pass.
2. **Job snapshot**: from the entry `R.snapshot.seq` (the head, or downloaded by id). `R.job_dir` must not exist (`STOP PLACE_TARGET_NOT_EMPTY`). The reused `Staging(job_dir)` builds the tree from the `job/` members (modes as recorded), checking each file's size and sha256 against `payload.members` (`STOP PLACE_SHA_MISMATCH`).
3. **PNGs**: the parts of `R.png.parts_seq` (downloaded by id), concatenated in order; the stream's sha256 must equal `png.whole_sha256`; read with `Archive(stream, ('MANIFEST.json', 'job'), gz=False)`; files added to the staging tree with their modes.
4. **AI outputs** of roles ARCHIVED and not consumed (none for a C7 delivery run, whose roles are all consumed): the `ai/` members of their newest AI entry, into the role's output folder in the staging tree (that folder must be empty in the snapshot).
5. `Staging.finish()` renames the tree into place; then a strict walk of `job_dir` must equal snapshot + PNGs + AI outputs exactly.
6. **Transcripts** needed by a pending `finish --transcript`: from the AI-G entry to `BASE/transcripts/`.
7. Nothing else: no runner command runs during placement; the runner itself checks the record against the placed ledger on its next command (R27).

### 8.6 Resolving an open role (design B5; O45, O46, O55-O58)

At most one role is open (I1). Steps, in this order, before anything else of the run happens:

1. **END_CONVERSATION** (`END_CONVERSATION role=R after=<latest(role).utc> [conversation=<opened.conversation or the continued V conversation>]`, then RUN go), skipped when `gates.p1_end_after_reset == 'no'` (then `forced = NOT_ENDABLE`). Without OPENED the Dot finds the conversation in its list after the START's utc.
2. **Place** the run (§8.5.1; for a CONTINUED V the snapshot of the REVIEW_INCOMPLETE STAGE, whose `qa/visual_review/` holds revision 1).
3. **Re-walk** every AI output folder of the run (strict `tree_list`): any file in the open role's output folder (other than the placed revision for a CONTINUED V) sets `files_found` and `forced = FILES_FOUND`. (Runner v4's RESPONSE_WRITTEN check sees only files present on this VM, R8, so it is no safeguard against what the reset removed.)
4. **EXPORT_TRANSCRIPT** to `BASE/transcripts/restore_<seq6>_<R><a>_<k>.<ext>` when `gates.p1_transcript_export == 'yes'`, then RUN go.
5. **ATTEST** the keys of §6.5 (restore rows). The helper sets:
   - `ended == no`: `forced = NOT_ENDED`;
   - `outcome == NO_CONVERSATION` when T43 does not hold (OPENED, a second time, no conversation list, `list_shows_none == no`): `forced = NO_CONVERSATION_NOT_ALLOWED`;
   - `p1_conversation_list == 'no'` and the role is STARTED without OPENED and the outcome is NO_CONVERSATION: `forced = NO_LIST`;
   - a CONTINUED V: `outcome = CONTINUED` (not asked).
6. The resolution's `action` follows T43-T47 exactly (core computes it; the table checks it):

| role and status | outcome / forced | action | O |
|---|---|---|---|
| S or G, STARTED or OPENED | NOTHING_WRITTEN, transcript exported | Q: INTERRUPT (runner `interrupt --reason TECHNICAL_VM_RESET`; the runner picks new-folder or in-place, or refuses `INTERRUPT_RESTART_USED` and the run freezes with `RESTART_EXHAUSTED_BY_RESET`); E: attempt 1 EVERYDAY_RETRY, attempt 2 FREEZE_EXHAUSTED (`RESTART_EXHAUSTED_BY_RESET`) | O45, O49 |
| S or G | NOTHING_WRITTEN, transcript not_available | Q: INTERRUPT as above, plus `owner_check` (flag `OWNER_CHECK`: the owner checks that conversation before scoring, §10.3; a write found fails that reader's case). E: FREEZE_LOST (`AI_OUTPUT_LOST`, ASK_USER; r2 INT-10) | O55, O49 |
| V, STARTED or OPENED | NOTHING_WRITTEN, transcript exported, or (Q only) not_available with `owner_check` (r2, INT-02) | REPLACE (one replacement reviewer per run, a new V attempt with the same prompt); with not_available, flag `OWNER_CHECK` (a write found makes the run's visual `FAILED_BY_RESET`, §10.3); if the replacement is used, or E with not_available: FREEZE_VISUAL_FAILED | O45, O55 |
| V, CONTINUED | (not asked) | FREEZE_VISUAL_FAILED, no replacement | O57 |
| any | WRITTEN, UNSURE, or any `forced` | S/G: FREEZE_LOST at the restored NEXT without interrupt (AI_OUTPUT_LOST); V: FREEZE_VISUAL_FAILED | O46 |
| STARTED only, never OPENED | NO_CONVERSATION, list shows none, conversation list available, first time in the attempt | SUPERSEDE: a new START (start_no 2) in the RESTORE commit; the O52 sheet lists the START1-START2 window | O58 |

7. The RESTORE commit carries every exported transcript of a resolved conversation, written-and-lost included (`transcript/` members, O56), and the new START when the action needs one. Only after it is confirmed does the plan run the interrupt, print the OPEN of the replacement or superseding START, or run the freeze (design B5: "committed before any interrupt, replacement or freeze is printed").

### 8.7 The RESTORE entry

Committed after every session that found a head (§3.5 RESTORE body): the boot and previous boot, operator, fingerprint, PASS, head seq/md5/copies, the absence observations, the kit and `kit_change`, the resolutions with transcripts, the new START if any, the rebase if any (with its part-absence observations), `rerun_expected`, `reprepare`/`abandon`, `delivery_question`, and what was placed (`{"what": "ledger" | "job" | "png" | "ai", "path", "tree_sha256"}`). Its own FIND is the authenticated second absence check (§8.4). A local HALT.json from before the reset is gone with the VM; the condition is re-detected from Drive (C1, C2) or was never on Drive (nothing shown).

---

## 9. outcomes(): one pure function (design B7; O44-O46, O55-O57, O61)

### 9.1 Signature

`core/outcome.outcomes(state) -> {"series", "seq", "pairs": [PAIR], "o52_sheet": [ROW], "owner_items": [ITEM], "counts": {...}}`. It reads only `state` (no file, no Drive, no clock). `final` (FINAL entry), `audit` (§10.1, on its own re-fold) and `score_check` (§10.3) call the same function. The owner's verdicts are applied by the second pure function of the same module, `core/outcome.final_dispositions(outcomes, verdicts)` (§9.5, r2 INT-03); no other code derives a disposition (F4, F5).

### 9.2 Pairs

For each (case, reader) of `genesis.jobs` (both readers for every case), the chain is the original run plus its restart run (`restart_of`). **The last run of the chain counts.**

`PAIR = {"case", "reader", "run", "job_dir", "frozen_seq", "frozen_sha256", "disposition": "SCORE" | "EMPTY" | "NONATTEMPT", "reason", "carrier_sha256", "visual", "flags", "runs": [run keys of the chain], "transcripts": {"generator": "exported" | "not_available" | null}}`

Disposition, first match:
| # | condition (on the last run L) | disposition | reason |
|---|---|---|---|
| D1 | L's tag is `NA-A`/`NA-B` | NONATTEMPT | the JOBS.json reason (or `NONATTEMPT_SOURCE_UNAVAILABLE`) |
| D2 | L is not FROZEN, or the chain does not exist | EMPTY | `NOT_RUN` (cannot occur after a valid FINAL, T62; kept total) |
| D3 | `AI_OUTPUT_LOST` in L.flags | EMPTY | `AI_OUTPUT_LOST` |
| D4 | `RESET_DIVERGED` | EMPTY | `RESET_DIVERGED` |
| D5 | `RESTART_EXHAUSTED_BY_RESET` | EMPTY | `RESTART_EXHAUSTED_BY_RESET` |
| D6 | L.frozen.final_next in {`GENERATE`, `SCOPE_READER`} and L has no interrupt | EMPTY | `FROZEN_AT_AI_STEP_WITHOUT_INTERRUPT` |
| D7 | L.frozen.final_next starts with `STOP_` and the chain used its restart (L is a restart run, or L has an in-place interrupt) and L has no carrier | EMPTY | `TECHNICAL_STOP_AFTER_RESTART` |
| D8 | L.frozen.final_next == `OWNER_DECISION` | EMPTY | `OWNER_DECISION` |
| D9 | `L.frozen.carrier_sha256` is null (no `carrier/convert/carrier.json` in FROZEN.json) | EMPTY | `NO_CARRIER` (route check failed, not carried, and every other stop before convert) |
| D10 | otherwise | SCORE | `CARRIER` |

`visual` (reported, not part of the historical-match disposition): `PASS`, `FAIL`, `FAILED_BY_RESET` (flag `VISUAL_QA_FAILED_BY_RESET`, O45/O46/O57), `REVIEW_INCOMPLETE_LIMIT` (O61), `NOT_REACHED`.

Also listed: every superseded START (with START1 and START2 utc: the window), every re-run (`RERUN_UNBOUND`), every rebase (diverged or not), every `OWNER_CHECK` (O55: "pending owner checks"), and transcript counts (O40).

`owner_items` (r2, INT-03): one ITEM per thing the owner must decide before scoring, `{"id", "kind", "case", "reader", "run", "role", "attempt", "start_no", "window": [utc, utc] | null}` with `kind` one of `OWNER_CHECK` (each resolution with `owner_check`, S, G or V), `SUPERSEDED_WINDOW` (each superseded START, NO_CONVERSATION or REBASE: did a conversation run in that window?), and `O52_SHEET` (exactly one item for the whole sheet). `id` is `sha(cjson(item without id))[:12]`.

### 9.3 The O52 sheet

One row per START in the series (including the head START a rebase superseded, with its window): `{"run", "case", "reader", "role", "attempt", "start_no", "reason", "start_utc", "boot_id", "opened": {conversation, utc} | null, "archived": [{revision, conversation, utc}], "resolution": {...} | null, "superseded_by", "window": [start_utc, superseding start_utc] | null}`. The owner (or a person the owner names) compares the account's conversation list with it before scoring (O52); an unlogged CPS conversation fails that case. The verdict is the `O52_SHEET` item of OWNER_CHECKS.json (§9.5), so an unchecked sheet blocks scoring and an unlogged conversation reaches the dispositions.

### 9.4 FINAL, ALL_FROZEN_Q1.json and LEDGER_FINAL

When T62 holds, the helper builds:
- `LEDGER_FINAL` = the bytes of `BASE/ledger/LEDGER.jsonl`, whose sha256 must equal `state.ledger.sha256`;
- `ALL_FROZEN` (`cps.vm2-all-frozen.v1`): `{"schema", "series", "final_seq", "genesis": state.genesis, "release_sha256", "kit_sha256", "ledger_final": {"sha256", "bytes"}, "runs": [{"run", "job_dir", "frozen_sha256", "frozen_seq", "frozen_entry": name, "png_parts": [names], "flags", "visual"}], "outcomes": outcomes(state'), "outcomes_sha256"}` where `state'` is the state after FINAL (the FINAL row changes only `phase` and `final`, so the outcomes equal those of the state before).

Both go into the FINAL entry as members `final/` and as parts `LEDGER01`, `ALLFZ01` (md5-confirmed before `HANDBACK B`, OP-03). After a reset a missing part is re-uploaded from the entry (C3).

### 9.5 Owner verdicts: OWNER_CHECKS.json and final_dispositions (r2, INT-03)

O55 ("the owner checks that conversation before scoring, and a write found fails that reader's case") and O52 ("an unlogged CPS conversation fails that case and flags qualification") are enforced by a verdict file the owner (or the person the owner names, O52) writes after reading the O52 sheet and the conversations, on the maintainer side:

`OWNER_CHECKS.json` (`cps.vm2-owner-checks.v1`): `{"schema", "series", "outcomes_sha256", "checked_by", "checked_utc", "verdicts": [{"id", "verdict", "note"}], "unlogged": [{"case", "reader", "conversation_utc", "note"}]}`, where each `id` is an `owner_items` id; `verdict` is `NOTHING_WRITTEN_CONFIRMED` or `WRITE_FOUND` (OWNER_CHECK), `NO_CONVERSATION_IN_WINDOW` or `CONVERSATION_FOUND` (SUPERSEDED_WINDOW), `SHEET_CHECKED` (O52_SHEET; unlogged conversations go in `unlogged`). The file carries no sha of its own choosing: `score_check` records its sha256 in SCORE_PLAN.json and in its check record, and the admission or score record names who checked (the "signature" is that pinned sha plus `checked_by`, as for every other owner input in CPS).

`final_dispositions(outcomes, verdicts) -> {"pairs": [PAIR'], "qualification_flagged": bool, "missing": [id]}` (pure):
- `missing` = every `owner_items` id without a verdict, plus `O52_SHEET` when absent; a verdict for an unknown id, a duplicate id, an `outcomes_sha256` other than the audit's, or a verdict value not allowed for the item's kind is a refusal (`OWNER_CHECKS_INVALID`);
- an S or G `OWNER_CHECK` with `WRITE_FOUND`, or a `SUPERSEDED_WINDOW` with `CONVERSATION_FOUND` (an S, G or V start): that (case, reader) becomes EMPTY with reason `OWNER_CHECK_FAILED` or `SUPERSEDED_WINDOW_CONVERSATION` (a V window with a conversation instead sets the pair's `visual` to `FAILED_BY_RESET`, O46);
- a V `OWNER_CHECK` with `WRITE_FOUND`: the pair's `visual` becomes `FAILED_BY_RESET` (O46: failed visual QA; the disposition is unchanged);
- each `unlogged` row: that (case, reader) becomes EMPTY with reason `UNLOGGED_CONVERSATION`, and `qualification_flagged = true` (O52);
- a pair already EMPTY or NONATTEMPT keeps its first reason; the added reason is listed in `also`.


---

## 10. Maintainer side (`vm2.py audit | assemble | score_check`)

Run by the maintainer on their own machine, never on the Dot's VM, with the series folder downloaded in full by a separate maintainer tool (O53; the helper never talks to Drive). Each writes one report and exits 0 only when clean.

### 10.1 audit (`maint/audit.py`, 350 lines)

`vm2.py audit --series Q1 --listing LISTING.json --dir DOWNLOADS --setup-listing SETUP.json --setup-dir SETUP_DOWNLOADS --out AUDIT.json` (r2: `--setup-dir` holds every `SESSION_KIT_*.zip` the journal names, replacing the single `--kit`, so every `kit_change` can be recomputed)

`LISTING.json` is the maintainer tool's complete Drive API listing of the series folder (every file: id, name, md5Checksum, size, createdTime; every page). The audit:
1. **Names**: every file name is an ENTRY or PART of this series (else `AUD_FOREIGN_FILE`); duplicate copies of one name with different md5 (`AUD_DUPLICATE_SEQ`); seq gaps (`AUD_GAP`); parts whose entry is absent (`AUD_UNREACHABLE_PART`); entries above the FINAL seq (`AUD_AFTER_FINAL`). r2 (INT-09): for `--series Q<k>`, any file of another Q series in `CPS/qualification` is `AUD_SECOND_QUALIFICATION_SERIES` (the listing is of the whole folder).
2. **Re-fold from genesis**: for k = 1..N: read entry k (Archive + check), `validate_entry`, `apply(state_{k-1}, entry_k)` with the same `core.fold` and compare with `entry_k.state` (`AUD_STATE_MISMATCH`), `prev_sha256` with the bytes of k-1 (`AUD_LINK`), `confirms` with the listing's ids, md5s and sizes (`AUD_CONFIRMS`), parts present with their md5 (`AUD_PART_MISSING`). r2 (INT-04, INT-05): a part of entry k absent from the listing is not an anomaly when entry k+1 is a RESTORE whose `rebase.head_seq == k` lists it in `missing_parts` (a declared rebase). A part that a declared rebase called missing but that the listing shows present is `AUD_REBASE_OVER_PRESENT_PART`, an **owner-review** item (below): the rebase superseded a START on an absence that did not hold, and only the owner's O52 window verdict can say whether a conversation ran for it.
3. **Ledger prefix chain**: the `ledger/LEDGER.jsonl` member of each entry that carries one must extend the previous one byte for byte (runner chain verified with the runner's own `Ledger.chain_problem` logic, read-only), except across a declared rebase (T49), where it must extend the base (`AUD_LEDGER_FORK`).
4. **Outcomes diff**: `outcomes(state_N)` from the audit's own fold must equal `ALL_FROZEN.outcomes` and its sha (`AUD_OUTCOMES_DIFF`, F5). A RESTORE, START or resolution that the Dot's FINAL did not fold (an entry present on Drive and absent from the chain the FINAL closed) is `AUD_UNFOLDED_ENTRY` (the "planted RESTORE" test).
5. **Release and kit**: every entry's `release_sha256` is the genesis release or accepted by the kit in force (KIT-1); every `kit_sha256` is a kit the setup listing holds (`AUD_KIT`). r2 (INT-08): for every RESTORE and CLEAR with `kit_change`, the audit reads both zips from `--setup-dir` with `kit_members`, recomputes both member lists and `config_only`, and compares them with the body (`AUD_KIT_CHANGE`); a CLEAR whose kits differ in more than `VM_HELPER_CONFIG.json`, or whose configs differ in a key outside §2.2's changeable list, is `AUD_KIT_CHANGE`; a non-config-only change while the folded state had a run in flight or an open role is `AUD_KIT_CHANGE`.
6. **Times**: `createdTime` of each entry is not earlier than its `utc` minus `audit_clock_tolerance_seconds` (default 600) and entries are in seq order by createdTime within that tolerance (`AUD_TIME_ORDER`, reported).
7. **Setup**: every PASS named in a RESTORE or GENESIS exists in the setup listing with that md5 (`AUD_PASS_MISSING`).
Report `cps.vm2-audit.v1`: counts, anomalies (codes and names only), `owner_review` (the `AUD_REBASE_OVER_PRESENT_PART` items, each also emitted as a `SUPERSEDED_WINDOW` owner item that `score_check` requires a verdict for), `outcomes_sha256`, the O52 sheet and `owner_items`; exit 0 iff no anomaly (owner-review items do not make the audit unclean, but `score_check build` refuses until each has a verdict, §10.3). The audit is a mandatory pre-gate of scoring (design §G).

### 10.2 assemble (`maint/assemble.py`, 120 lines)

`vm2.py assemble --series Q1 --dir DOWNLOADS --root / --out ASSEMBLE.json [--verify-frozen]` rebuilds, at their original absolute paths under `--root` (default `/`, so `/home/agent/...` for the drill), every frozen run folder (the FROZEN entry's `job/` members plus its PNG parts, exactly as §8.5.1 steps 2-5) and the ledger (`LEDGER_FINAL`), with modes as recorded; then, with `--verify-frozen`, runs the runner's `verify-frozen --job-dir <dir>` on each (R29: it writes nothing) and requires `NEXT: DONE` for every run. Report: per run the paths, counts and verify result.

### 10.3 score_check (`maint/score_check.py`, 180 lines; admitted separately)

`vm2.py score_check build --audit AUDIT.json --assembled ASSEMBLE.json --pool POOL.json --owner-checks OWNER_CHECKS.json --out DIR` and `vm2.py score_check check --plan DIR/SCORE_PLAN.json --manifest AGG_MANIFEST.json --out CHECK.json`.

- **build**: refuses unless the audit is clean and its `outcomes_sha256` equals ALL_FROZEN's. r2 (INT-03): it then applies `final_dispositions(outcomes, OWNER_CHECKS.json)` (§9.5) and refuses (`OWNER_CHECKS_INCOMPLETE`, naming the ids) while any `OWNER_CHECK`, `SUPERSEDED_WINDOW` (including the audit's owner-review items) or the `O52_SHEET` item lacks a verdict, and (`OWNER_CHECKS_INVALID`) on an invalid file. For each pool case and reader A, B, from the **final** dispositions:
  - SCORE: the carrier is the assembled run's `carrier/convert/carrier.json`; its sha256 must equal `L.frozen.carrier_sha256` and the FROZEN.json listing;
  - EMPTY and NONATTEMPT: writes `DIR/carriers/<reader>/<case>/EMPTY_CARRIER.json` = `{"items": [], "cps_failed_run": {"schema": "cps.vm2-failed-run.v1", "series", "seq": frozen_seq, "case_id", "reader", "job_dir", "reason", "frozen_sha256"}}` (`doc_bytes`). It differs per reader (reader and job_dir differ), so the aggregator's `READERS_SHARE_CARRIER` check passes (FLAGS-2). The evaluator reads only `items`, and an empty `items` scores 0 against the full target count (R-E1, R-E2 in §16);
  - writes `SCORE_PLAN.json`: per (case, reader) `{"disposition", "reason", "also", "visual", "carrier_path", "carrier_sha256"}`, plus `owner_checks_sha256`, `checked_by` and `qualification_flagged` (O52). An EMPTY made by a verdict (`OWNER_CHECK_FAILED`, `SUPERSEDED_WINDOW_CONVERSATION`, `UNLOGGED_CONVERSATION`) gets its empty carrier exactly like any other EMPTY.
  It never runs the evaluator or the aggregator and never reads a target.
- **check**: given the aggregator manifest the scorer built (`readers.<R>.<case>.carrier_sha256`), every entry must equal SCORE_PLAN's carrier sha256 for that case and reader; a wrong, shared or real-instead-of-empty carrier is `INCONSISTENT` (exit 1, FLAGS-1); a pool case missing from either is `INCONSISTENT`. The scorer never supplies a carrier sha (FLAGS-1). Exit 0 only on `CONSISTENT`; scoring is blocked otherwise.

---

## 11. Everyday mode (O49, O60)

### 11.1 Series and folder

Series `E1` in `Dots Folder/CPS_JOB_RECORDS` (owner-only). Kit release `RELEASED_FOR_USE`. One job at a time (I10). Runs are tagged `E<utc14>` (UTC of the IDLE answer), jobs root `BASE/jobs/<utc14>`.

### 11.2 Flow and commits

| # | trigger | commit |
|---|---|---|
| 0 | IDLE answer `case=CASE_ID`: CASE_ID_RE checked first (SAFE-02), then `BASE/everyday_inputs/<case>/` must hold regular files `JOB.json` (case_id equal), `JOB_TITLE.json` and the source named by `source_path` (in that folder), each with one link (`INPUTS_INVALID`) | INPUTS (r2, INT-10: tag `E<utc14>`, case, the three files' sha256s; committed before anything runs, so a prepare lost to a reset is counted) |
| 1 | RunChain(prepare) from the committed inputs (their shas re-checked: a changed input is `REFUSED INPUTS_CHANGED`, nothing runs) | STAGE (new run per T13, START G or S) |
| 2 | S/G conversation ends | AI |
| 3 | consumer chain (scope-finish, or finish) | STAGE (+ START V and PNG parts) |
| 4 | V ends | AI |
| 5 | chain visual-record -> deliver-check; the worker writes `BASE/deliver/<run8>/STANDARD.xlsx` | STAGE (`next DELIVER`) |
| 6 | `DELIVER file=BASE/deliver/<run8>/STANDARD.xlsx to=copy`, answer `copy=... log=...` | DELIVERY (parts DELIV01, DLOG01 to `<profile folder>/deliveries/`) |
| 7 | `DELIVER file=<the copy> to=user`, answer `sent=YES`; chain freeze -> verify-frozen | FROZEN (`delivery_sent`) |

Commit count 8 (the design's budget row already counts "INPUTS+prepare"), about 21-25 Drive calls with 1-3 PNG parts (design §D).

### 11.3 The personal copy (DEPLOYMENT_MODEL)

r2 (IMP-14). The DELIVER `to=copy` block names `BASE/deliver/<run8>/STANDARD.xlsx`, the worker's byte copy of the runner's deliver-check file (its sha256 checked equal to `R.saved_qa.deliverable_sha256` when written, and again before the block is printed; never printed before the STAGE of row 5 is confirmed). The runner's own path holds the title (R32) and is never printed. The Dot makes the personal copy with the user's preferences, in the DEPLOYMENT_MODEL folder layout with ASCII names: `$HOME/cps-deliveries/<case>/<user>/<utc14>/PERSONAL_COPY.xlsx` and its `cps.personal-copy-log.v1` log `PERSONALIZATION_LOG.json` in the same folder, where `<user>` is the user's ASCII profile key (`[a-z0-9_-]{1,40}`; the user's display name stays inside the log) and `<utc14>` the time it made the copy. The helper checks: both answers are COPYPATH (§6.3, the exact layout); the log is strict JSON naming `standard_file.sha256 == R.saved_qa.deliverable_sha256` (`COPY_LOG_MISMATCH`); the copy is a regular file of 1 byte..`png_part_bytes`. The profile folder comes from the log's `profile_folder` field (ASCII printable, no quote, at most 200 characters; else `COPY_LOG_MISMATCH`). **SPEC DECISION** (SD-4): the parts go to the profile folder as `CPSJ_E1_<seq6>_DELIV01.xlsx` and `CPSJ_E1_<seq6>_DLOG01.json` (ASCII, exact-name searchable), not under the writer's (title-bearing) name. The user receives the personal copy by DELIVER `to=user`, sent under the standard file's name `<name>(未填).xlsx`, which the Dot takes from the `JOB_TITLE.json` it wrote (the helper never prints it). §17 OQ-5 asks the owner to confirm these names.

### 11.4 Resets in everyday

- Resume from the last committed entry without limit (O60): C6, C8, C9 as in qualification.
- r2 (INT-10). **Re-preparation, once, logged** (O49, O60): INPUTS is committed before prepare runs. A reset after INPUTS and before the prepare STAGE is confirmed leaves the run in status `INPUTS` (C8b): the first time, the RESTORE records `reprepare` and the plan prepares again from the same committed inputs; the second time, the RESTORE records `abandon`, the job fails, and `notify = ASK_USER` ("the job could not be prepared; a new job only at your request", `asked=YES`). A committed prepare is resumed, never re-prepared (O60). A new IDLE answer for the same inputs is a new job only after the earlier one ended and its notice or question was acknowledged (T06, T15), i.e. after the user was told; the README says `case=` is answered only for a user's request.
- An open S/G with NOTHING_WRITTEN and an **exported** transcript: one more conversation in the same folder (EVERYDAY_RETRY, T44; the runner has no interrupt for real jobs, R10); a second NOTHING_WRITTEN: FROZEN with `RESTART_EXHAUSTED_BY_RESET` (action FREEZE_EXHAUSTED, INT-13). r2 (INT-10): with `transcript=not_available` there is no retry (no owner check precedes an everyday delivery, so O55 cannot apply): FROZEN with `AI_OUTPUT_LOST`. WRITTEN or UNSURE: FROZEN with `AI_OUTPUT_LOST`. Each of these sets `notify = ASK_USER` ("the job failed; a new job only at your request", answer `asked=YES`, O49).
- V as in qualification (REPLACE once, with an exported transcript, T45; CONTINUED fails visual QA; the runner then never delivers: `deliver-check` needs a visual PASS, R-claim R35). In everyday a V `not_available` reading never buys a replacement (FREEZE_VISUAL_FAILED): a lost first review might have been a FAIL, and no owner check precedes the delivery a replacement PASS would allow (r2, INT-02, INT-10).
- Every everyday FROZEN without `delivery_sent` sets `notify`: `NOTIFY_OWNER` for a runner `STOP_*`/`OWNER_DECISION` (a stage failure on a normal job is handback case C material, DEPLOYMENT_MODEL), `ASK_USER` for a reset failure (AI output lost, restart exhausted, visual QA failed by reset).
- PREPARED without SENT: the RESTORE commits `delivery_question`, which sets `notify = ASK_USER` "did the copy arrive?" (`arrived=YESNO`) before anything else is printed; never re-send blindly (C7, T42, T52; r2 INT-06).

## 12. Probe dependencies and release gates

### 12.1 The gates in the kit config (`gates`, recorded in GENESIS)

| key | values | probe |
|---|---|---|
| `p1_vm_files` | `PASS` `FAIL` `OPEN` | P1: a new conversation can read and write the VM's files without Drive |
| `p1_transcript_export` | `yes` `no` `OPEN` | P1: a transcript, with its file writes, can be exported to a VM file |
| `p1_conversation_list` | `yes` `no` `OPEN` | P1: the Dot can list its conversations with creation times |
| `p1_end_after_reset` | `yes` `no` `OPEN` | P1: the Dot can see that a conversation ended, or stop it, after a VM reset |
| `p2_exact_search` | `PASS` `FAIL` `OPEN` | P2/M004: search by exact name returns every copy with id, md5 (or size) |
| `p2_md5_visible` | `yes` `no` `OPEN` | P2 |
| `p2_prefix_search` | `yes` `no` `OPEN` | P2: a "starts with" search returns exactly the matching names |
| `p2_newest_first` | `yes` `no` `OPEN` | P2: a newest-first listing limited to k |
| `p2_lag_seconds` | int or null | P2: the longest time an uploaded file was missing from search |
| `p2_max_upload_bytes` | int or null | P2: the largest upload and download that kept its sha256 |
| `p2_tgz_kept` | `PASS` `FAIL` `OPEN` | P2: `.tgz`, `.tar`, `.part`, `.jsonl` files are stored and returned unconverted and under their names |
| `p2_failed_upload_can_appear` | `yes` `no` `OPEN` | P2: a failed or timed-out upload may still appear |
| `p3_identity_stable` | `yes` `no` `OPEN` | P3: `$HOME` and uid are the same after a reset |
| `p5_detached` | `PASS` `FAIL` `OPEN` | P5: a detached process survives the end of the tool call that started it (probe_p5.py) |
| `p5_tool_call_seconds` | int or null | P5: the longest tool call that completed |
| `p5_setup_seconds` | int or null | SAFE-07: the measured cold setup duration |

**Release gates** (checked on every `go`, not only at session start, GATE-1): in mode qualification, drill or everyday, every key above must be answered (no `OPEN`, no null), and `p1_vm_files == PASS`, `p2_exact_search == PASS`, `p2_tgz_kept == PASS`, `p5_detached == PASS`, `wrap_foreground_seconds + 60 <= p5_tool_call_seconds`, `png_part_bytes <= p2_max_upload_bytes`, `max_entry_bytes <= p2_max_upload_bytes`. Otherwise `STOP RELEASE_GATE_OPEN HANDBACK C` naming the gates (no job runs; O50). The kit loader refuses a config whose gate values are not in the listed sets (`CONFIG_INVALID`). A setup-only kit (release status neither) runs only the session, the self-test and the PASS upload.

### 12.2 Behaviour per outcome

| probe answer | behaviour |
|---|---|
| P1 VM files PASS | as designed |
| P1 VM files FAIL | `RELEASE_GATE_OPEN`: all CPS jobs wait for a separately reviewed transfer design (O50) |
| P1 transcript export yes | EXPORT_TRANSCRIPT blocks are printed; NOTHING_WRITTEN rests on the exported transcript (T44); the generator transcript goes to `finish --transcript` |
| P1 transcript export no | no EXPORT blocks; answers `transcript=not_available`. Q: NOTHING_WRITTEN is accepted on the Dot's attested reading with `OWNER_CHECK` (O55), for S, G and V (r2, INT-02), and scoring waits for the owner's verdicts (§9.5). E: no retry and no replacement on an unchecked reading: every interrupted S/G fails `AI_OUTPUT_LOST`, every interrupted V fails visual QA (r2, INT-10); otherwise WRITTEN |
| P1 conversation list yes | OPENED not used (`then=when_ended`); NO_CONVERSATION admissible under T43 |
| P1 conversation list no | OPENED mandatory (`then=now`, AWAIT); NO_CONVERSATION is forced WRITTEN (`NO_LIST`). A rebase that supersedes a head START rests on the authenticated part absence (§8.4 step 5) alone, without a list check; its window goes on the O52 sheet as a `SUPERSEDED_WINDOW` item that the owner must clear before scoring (§9.5; r2 INT-05; §17 OQ-12) |
| P1 end after reset yes | END_CONVERSATION before the outcome |
| P1 end after reset no | every open role at a restore is forced WRITTEN (`NOT_ENDABLE`) |
| P2 exact search PASS | required |
| P2 exact search FAIL | **blocked**: `RELEASE_GATE_OPEN P2_EXACT_SEARCH`; nothing of v2 runs (the design has no fallback) |
| P2 md5 visible yes | found takes `ID:MD5:SIZE` |
| P2 md5 visible no | found takes `ID:SIZE`; every copy is downloaded back and its sha256 compared (§5.5; +1 call per file) |
| P2 prefix search yes | one `FIND ... PREFIX CPSJ_<S>_<seq6>` per commit (§5.2) |
| P2 prefix search no | one FIND per name |
| P2 newest-first yes | head candidate in one LIST call (§8.4) |
| P2 newest-first no | hint gallop, or gallop from 1 without a hint; without a hint the RESTORE is followed by the re-check of §8.4 step 6 (r2, INT-11). **Residual risk** (stated, not removed): an exact-name search that keeps missing the same confirmed entries for longer than both absence checks and the re-check lets the series continue from an older head; the shown results of the lost entries then bind nothing until the audit reports `AUD_DUPLICATE_SEQ` (which blocks scoring). P2's lag measurement sizes `w_abs` against this |
| P2 lag L seconds | `w = max(30, 2L)` between a none and the second FIND (§5.1); `w_abs = max(60, 2L)` between head absence checks (§8.4); a lag larger than the waits produces FORK STOPs at RESTORE (fail-closed, maintainer cycles) |
| P2 max upload B bytes | `png_part_bytes`, `max_entry_bytes` at most B; a larger file is `HALT ENTRY_TOO_LARGE`/`PART_TOO_LARGE`; if the evidence cannot fit, the question returns to the owner (O48) |
| P2 tgz kept FAIL | **blocked**: `RELEASE_GATE_OPEN P2_TGZ_KEPT` (owner decision needed) |
| P2 failed upload can appear yes | no change: the waits in §5.1 already let a slow copy appear before a re-upload; a copy that appears later with the same md5 is a harmless duplicate |
| P3 identity stable yes | as designed |
| P3 identity stable no | a `$HOME` or uid change is `STOP HOME_CHANGED` when a run is in flight or a role is open (that run is stranded; case C); with no run in flight a new kit naming the new layout is needed (the release names absolute paths, `LAYOUT_RELEASE_MISMATCH`) |
| P5 detached PASS, limit T | stages, self-test and setup run detached; `go` waits at most `wrap_foreground_seconds <= T - 60` |
| P5 detached FAIL | `RELEASE_GATE_OPEN P5`: a stage could exceed the tool-call limit or die with it |

### 12.3 Release gates outside the code

Before a qualification or everyday release names v2: the probe answers recorded in `CURRENT_STATE.json` and in the kit; the admission of §15; a drill (§15.3).

### 12.4 What the probes must also measure (for the budgets)

Upload and download speed at 25, 130 and 300 MB (design §F probe step 5), to size `png_part_bytes` and the call budget (OP-07).

### 12.5 probe_p5.py (standalone, 80 lines; admitted separately)

`python3 -I -B deploy/vm2/probe_p5.py start --dir D [--seconds 900]` | `hold --dir D --seconds S` | `check --dir D [--min-gap 480]`. Standard library only; writes only under D (default `$HOME/cps_probe_p5`); no kit, no Drive, no helper state.
- **start**: refuses if a worker of this boot is alive. Writes `D/START.json` = `{"schema": "cps.vm2-probe-p5.v1", "token", "boot_id", "started_utc", "seconds", "caller_ppid": os.getppid(), "caller_sid": os.getsid(0), "caller_pgid": os.getpgid(0), "start_pid": os.getpid(), "worker_pid", "start_exited_utc"}` (the last written just before exit), starts the worker with `start_new_session=True`, stdin/stdout/stderr detached; the worker appends `{"utc", "n", "token"}` lines to `D/HEARTBEAT.jsonl` once a second for `seconds`, then writes `D/DONE.json`. Prints: `NEXT: end this tool call now; in a NEW tool call at least <min-gap> s later run: python3 -I -B <path> check --dir D`.
- **check**: refuses (`REFUSED SAME_CALL`, exit 4, writes nothing) when `os.getppid() == caller_ppid` **or** `os.getsid(0) == caller_sid` (the check runs in the same shell or session as start, so no tool-call boundary is proven; SAFE-03, OP-05); refuses `TOO_EARLY` before `start_exited_utc + min_gap`; refuses `OTHER_BOOT` across a reset. Otherwise writes `D/PROBE_P5_<boot8>_<utc14>.json` with heartbeats count, last heartbeat, `worker_lived_after_start_exit_seconds = last_heartbeat - start_exited_utc`, `worker_alive`, `done`, holds, and `verdict`: `PASS` iff `worker_lived_after_start_exit_seconds >= min_gap - 5` and (alive or done) and `min_gap >= 480`; `FAIL` otherwise. Prints the report path; the Dot uploads it to `CPS/reports`.
- **hold**: sleeps S seconds in the foreground and records `HOLD_<S>_<utc14>.json` with `completed_utc` at the end, so a killed hold shows the tool-call limit (values 60, 240, 600, 1200, 2400).
A persistent shell shared by every tool call makes every check `SAME_CALL`: P5 then stays `OPEN` and the maintainer decides from the probe message's step 8 (`ps -o sid=`) evidence (§17 OQ-3).

---

## 13. Codes

Exit 4 = REFUSED (state unchanged; the current block is printed again after `REFUSED <CODE>`). Exit 3 = STOP. "Local sticky" = written to HALT.json and printed by every later command of this boot until cleared (§13.5). "HALT entry" = committed (T58), so it survives a reset (until a CLEAR). "C" = hand back case C: do nothing more, tell the owner the code and the CPSV line.

### 13.1 REFUSED (the Dot corrects the answer, or runs `go` to see the current block)

| code | raised in | the Dot does |
|---|---|---|
| `COMMAND_NOT_EXPECTED` | found/answer when BLOCK expects another command | runs `go`, follows the block |
| `STALE_AT` | `--at` differs from BLOCK.at (§6.3) | runs `go`, uses the new at |
| `ARG_MISSING_KEY`, `ARG_EXTRA_KEY`, `ARG_DUPLICATE_KEY` | answer keys differ from the block's | gives exactly the keys printed |
| `VALUE_FORBIDDEN` | a forbidden character, whitespace, newline, non-ASCII, empty | gives the real value |
| `VALUE_PLACEHOLDER` | a key name, pattern name or README example as a value (OP-04) | gives the real value |
| `VALUE_PATTERN` (detail: key) | value does not fullmatch its pattern | gives a matching value |
| `UTC_OUT_OF_WINDOW` (detail: key) | a time outside the START window or in the future | gives the conversation's real times (seconds, start rounded up, end rounded down) |
| `FOUND_NAMES_INCOMPLETE` | found names differ from the block's names | reports every name the block asked |
| `FOUND_FILE_AND_NONE`, `FOUND_SYNTAX` | both `--file` and `--none`, or a malformed triple | one `--file` per copy, or `--none` |
| `DOWNLOAD_MISSING` | a printed DOWNLOAD target is absent | downloads it, runs `go` |
| `FINAL_MESSAGE_INVALID` | `attest/final_message.txt` missing, empty, over 8 KB, not UTF-8, or with `<...>`/`{...}` | writes the generator's final message verbatim |
| `TRANSCRIPT_FILE_MISSING`, `TRANSCRIPT_TOO_LARGE` | `transcript=exported` without the file at the printed path, or too large | exports again, or answers `not_available` |
| `INPUTS_INVALID` | everyday inputs folder incomplete, case mismatch, a link | puts the three files in `everyday_inputs/<case>/` |
| `INPUTS_CHANGED` | an everyday input's sha differs from the committed INPUTS entry at (re-)prepare (r2, INT-10) | restores the inputs it committed, or tells the owner (the job is not prepared from other inputs) |
| `COPY_LOG_MISMATCH`, `COPY_INVALID` | everyday copy or log wrong (§11.3) | makes the copy from the named standard file |

`HELPER_BUSY` and `JOB_BUSY` (reused `HelperLock`, `JobLock`) are not shown as refusals: they print `DO: WAIT seconds=30` (exit 0).

### 13.2 STOP, local sticky (cannot be committed; C)

| code | raised in |
|---|---|
| `FORK` | §5.1 (a second md5 for a name), §8.2, §8.4, §5.2 (foreign prefix name) |
| `UPLOAD_FAILED` | §5.1 (3 uploads, each FIND twice) |
| `HINT_AHEAD`, `HEAD_UNSTABLE` | §8.4 |
| `HEAD_CORRUPT`, `SCHEMA_INVALID`, `STATE_SHA_MISMATCH`, `CHAIN_INVALID`, `LINK_MISMATCH`, `HELPER_UNKNOWN`, `RELEASE_NOT_ACCEPTED` | §8.4 steps 3-4, §4.2 |
| `DISK_FULL`, `WRITE_FAILED`, `WRITE_READBACK_MISMATCH` | §2.4 (before anything is printed) |
| `ENTRY_TOO_LARGE`, `PART_TOO_LARGE` | §3.9 |
| `INTERNAL_EMPTY_OUTPUT`, `INTERNAL_PENDING_EXISTS`, `INTERNAL_ILLEGAL_TRANSITION`, `INTERNAL_PRINT`, `INTERNAL_CHAIN_TOO_LONG` | helper bugs |
| `WORKER_DIED`, `SELFTEST_WORKER_DIED` | §7.2, §8.3 |
| `PLACE_TARGET_NOT_EMPTY`, `PLACE_SHA_MISMATCH` | §8.5.1 |
| `KIT_NOT_VERIFIED`, `KIT_SUMS_MISMATCH`, `KIT_NOT_IN_MANIFEST`, `KIT_PARTS_NOT_IN_MANIFEST`, `KIT_NOT_REBUILT`, `ARCHIVE_UNSAFE_MEMBER`, `ARCHIVE_UNREADABLE`, `ARCHIVE_MANIFEST_MISMATCH`, `ARCHIVE_MEMBER_SHA_MISMATCH` | reused kit and archive code (§8.2, §3.3) |
| `KIT_CHANGE_WITH_RUN_IN_FLIGHT` | reused `unpack_kit`, §8.1 step 11 |
| `CONFIG_INVALID`, `RELEASE_GATE_OPEN` | §2.2, §12.1 |
| `LAYOUT_HOME`, `LAYOUT_BASE`, `LAYOUT_HELPER_NOT_IN_BASE_REPO`, `LAYOUT_PATH`, `LAYOUT_RELEASE_MISMATCH`, `LAYOUT_HELPER_NOT_PINNED`, `LAYOUT_RUNNER_NOT_PINNED` | reused/modified layout checks |
| `LEDGER_MISSING`, `LEDGER_NO_IDENTITY` | reused `check_ledger_identity` |
| `CLOCK_BEHIND` | reused `clock_check` (a shorter lag prints `WAIT`) |
| `HOME_CHANGED` | §8.1 step 8 |
| `SELFTEST_FAILED`, `SETUP_FAILED`, `SESSION_LAYOUT`, `SESSION_GIT_ERROR`, `SESSION_REPO_DIRTY` | §8.3, §6.6 |
| `JOB_BUSY_TOO_LONG`, `QUALIFICATION_DIVERGED_RESTART_CONFLICT` | §7.2, §7.11 |
| `REBASE_PART_APPEARED`, `REBASE_LIMIT`, `REBASE_CONFLICT` | §5.1 step 5, §8.5 C5, C5b (r2, INT-05) |
| `CONFIG_CHANGE_NOT_ALLOWED`, `GATES_CHANGED`, `KIT_NOT_VERIFIED` (head kit) | §2.2, §8.1 step 11, §8.2 (r2, INT-08, INT-09) |
| `QUALIFICATION_SERIES_EXISTS` | §7.12 (r2, INT-09) |
| `SESSION_COMMIT_MISMATCH`, `SESSION_NO_COMMIT` | §6.1, §6.6 (r2, IMP-04) |
| `INTERNAL_STEP_OVERFLOW` | §6.3 (r2, IMP-15) |

### 13.3 HALT entries (committed; survive resets; C)

| code | raised in |
|---|---|
| `RUNNER_REFUSED` (detail: the runner code) | §7.3 rows X6, X7: a runner refusal other than `REVIEW_CONTINUABLE`, INTERRUPT_RESTART_USED and JOB_BUSY; with a changed record it is the STAGE of T23, otherwise a HALT entry (r2, INT-12: always committed; never a re-print of the same stage) |
| `RUNNER_OUTPUT_UNPARSEABLE` | §7.2, §7.3 X6, X7 |
| `UNCLASSIFIED` | §7.1 row 23, §7.3 X20, §8.5 C10 |
| `AI_OUTPUT_CHANGED` | §7.2 step 3: the consumer's measured output tree differs from the archive (r2, INT-07) |
| `WALK_UNSUPPORTED_ENTRY` | modified `tree_list` (snapshot, AI walk, evict, re-walk) |
| `EVICT_MISMATCH`, `EVICT_FAILED`, `POST_ACTION_FAILED` | §7.6, §5.4 |
| `FROZEN_FOLDER_CHANGED`, `FREEZE_INCOMPLETE` | §7.3 |
| `PNG_MANIFEST_UNSAFE` | §3.8 |
| `PROMPT_CHANGED`, `GENERATION_RECORD_EXISTS`, `AI_OUTPUT_TOO_LARGE` | §4.4, §7.5 |
| `PLACED_FROZEN_CHANGED` | §7.7 |
A HALT entry cannot be committed when the commit itself fails; then the code stays local sticky. After a reset, a committed HALT is `STOP HALTED_<code> HANDBACK C` (C2).

Runner outcomes (`STOP_*`, `OWNER_DECISION` printed by the runner) are not helper codes: the run is frozen and the owner is notified (§7.9); the Dot continues.

### 13.4 Mapping the reused code's `Halt`

`vio` catches every `v1compat.Halt` raised by a reused or modified function: `REFUSED HELPER_BUSY` and `REFUSED JOB_BUSY` become a WAIT block; `NEED CLOCK_WAIT` becomes `WAIT seconds=<until the floor + 2>`; every other `REFUSED` and every `STOP` becomes a local sticky STOP with the same code (C). The v1 `Block` text is never printed.

### 13.5 Clearing a HALT (O59)

Only a config-only kit clears: a kit whose members differ from the halted kit's only in `VM_HELPER_CONFIG.json`, and whose config differs only in the changeable keys of §2.2, with `clear = {"series": S, "seq": n, "code": c}`. r2 (INT-08, IMP-05): the halted kit is the one the journal names (`head.kit_sha256` for a committed HALT, `STATE.kit_sha256` for a local sticky one); after a reset the session downloads it from `CPS/setup` and compares member lists (§8.2 KIT_CHANGE), and the CLEAR body records both lists so the fold (T59) and the audit (§10.1 step 5) re-check the comparison. `unpack_kit`'s return value is not used. No code, rule, table or evaluator change is involved.
- Committed HALT (`phase HALTED`, `halt.seq == n`, `halt.code == c`): after the session (RESTORE when a reset happened, with the resolution of any open role first, §8.5 C2) the helper commits CLEAR (T59), and the plan resumes from the state as it was; a cleared condition that recurs halts again. In the same boot the `marks` survive the HALT and CLEAR commits (§2.3), so no OPEN, AWAIT, CONTINUE or DELIVER printed before the HALT is printed again (r2, INT-01).
- Local sticky HALT (`HALT.json.series == S`, `head_seq == n`, `code == c`): the Dot runs `session_start.sh` (the maintainer's message says so); the session machine takes the kit in, moves HALT.json to `outbox/v2/cleared_<utc14>/`, and the next commit records `cleared_local`.
A `clear` that names nothing current is ignored (and reported in the next commit's `cleared_local` as null). The audit lists every CLEAR and `cleared_local`.

When the cache is valid for this boot, `session_start.sh` re-runs only the session steps 1-6, 9 and 11 (kit, config, gates, layout, fingerprint, PASS, kit acceptance) and commits nothing by itself; open conversations are not disturbed.

---

## 14. Test plan (`deploy/vm2/tests/`, about 3,400 lines; budget in §14.8, measured)

Entry point: `python3 -I -B deploy/vm2/tests/run_tests.py --work /abs/NEW_DIR [--jobs 4] [--only NAMES] [--node ... --node-path ... --writer-dir ...] [--v1-driver] [--mutants]`. It needs what `deploy/run/test_cps_job.py` needs for the real runner (python3 with openpyxl 3.1.5, node 22, Playwright Chromium, LibreOffice, poppler, git, a clean checkout: the runner refuses a dirty tree), and writes `TEST_RESULTS.json` (`cps.vm2-tests.v1`: test count, passed, failed with detail, seconds per scenario, free bytes at start, helper tree sha, runner sha). No private data; every job is invented.

### 14.1 Core table and invariant property tests (`test_core_table.py`, `test_core_props.py`; 900 lines; no runner, under 1 minute)

- **Table enumeration** (§4.8): every (kind, reachable abstract state) pair; exactly the listed rows or ChainInvalid; every row hit; no two rows match; golden file.
- **Property tests** (stdlib `random`, fixed seeds, 2,000 sequences of up to 200 entries): a generator of legal next entries from any state (it uses only the public row guards' documentation, written independently of `fold.py`), interleaved with injected illegal entries (each must raise ChainInvalid and leave the state unchanged). After every apply: I1 (one open role), I3, I4 (count rule-3 restarts per (case, reader) <= 1), I8, I9, I10, I12, I13, I14, I16, and `state_sha256` determinism (two folds of one sequence give identical bytes).
- **Random cuts** (F2, TST-01): for each generated sequence, cut at every index, discard the tail, fold a RESTORE with a random legal resolution, continue; assert no attempt ever has a second START except through T31, T43 (at most once) or a new attempt (T30 in place, T45, T44 E).
- **outcomes() table** (F4, FLAGS-3): one hand-written state per frozen-run shape (every D1-D10 row, every flag, restart chains A then A-restart1, nonattempts, in-place interrupt, OWNER_DECISION, frozen at GENERATE without interrupt, technical stop after the restart, route-check failure, visual FAIL/FAILED_BY_RESET/REVIEW_INCOMPLETE_LIMIT) with its expected PAIR; outcomes() total over generated states (never raises).
- **names**: every pattern with positive and negative cases, including a trailing `\n`, NUL, fullwidth digits, `{CONVERSATION_ID}`, `<id>`, README examples.
- **head_search**: every hint/gallop/newest-first path against a model of Drive (present set, lag, duplicates).
- **classify**: every C1-C10 row from a hand-built head.

### 14.2 The world harness (`fakes.py`)

- **FakeDrive**: folders of `name -> [copies {id, bytes, md5, created}]`. Methods: `upload`, `find(folder, name)` (exact; all copies), `find_prefix` and `list_newest` (only when the world's gates say yes), `download(id)`. It has **no full listing** for the helper side (OP-06); the test oracle and the audit tests read its internal table directly. Knobs per name: `lag(n_finds)`, `drop_upload(k)` (the k-th upload never lands), `late_appear` (a failed upload appears later), `duplicate` (same bytes twice), `foreign(bytes)` (another copy with other content), `delete_part`, `hide_md5`.
- **FakeDot**: parses each block with the §6.1 grammar (a malformed block, a second DO line, a `{`/`<` token, or a path that does not round-trip fails the test: F6, OP-04); performs UPLOAD/FIND/LIST/DOWNLOAD on FakeDrive; answers with a scenario strategy; plays the AI roles: S writes the invented scope response, G the package's invented example response adapted to the job (as `test_cps_job.py` does), V a complete PASS review (or an incomplete one, or a FAIL); END/EXPORT write a transcript file; keeps the last CPSV line; `reset()` deletes BASE **including `BASE/repo`**, the cache, the tools marker, gives a new boot id, and forgets everything except what the scenario says survives (the hint and the CPSV-REPO line, or nothing); it then executes the README bootstrap lines of §6.1 verbatim, with only the clone URL replaced by a local bare mirror of the checkout under test, and, in the notes-lost variant, step 0 against FakeDrive's `CPS/VM2_RELEASE.md` (r2, IMP-04).
- **World**: BASE, TOOLS and HOME under the work folder (overrides of §2.1); a kit built from invented RELEASE, admission, JOBS (two cases, one large enough for the scope stage, one nonattempt) and config (gates as the scenario sets); real runner v4. `cli.main(argv)` runs in-process with `vio/host.now` patched to skip WAITs; the worker is a real detached subprocess (spawn).
- **Job-state cache**: each invented job's real stage sequence runs once per test process; the job folder, ledger and runner outputs are kept per stage boundary and copied into worlds that start from that boundary, so a reset scenario re-runs only the stages it examines.

### 14.3 Reset enumeration (`test_resets.py`, 1,100 lines)

r2 (IMP-09): the enumeration is bounded and tiered, and its size is part of the spec.

**Runner in the reset tiers.** A *memoized real runner*: each runner command is keyed by (sub, argv, sha of the job folder tree, record and ledger before it); the first execution in a test process runs runner v4 for real and stores the after-state and stdout; a later identical key restores exactly that after-state and stdout. Every byte a scenario sees was produced by runner v4 on an identical before-state. A key never seen runs the real runner. Tier B below runs without memoization.

A reset (`FakeDot.reset()`) at every point of:
- **commit points** CP1-CP10: parts written / entry written / PENDING written / UPLOAD done, before found / after a `--none` (WAIT state) / after a re-upload / entry confirmed, parts not uploaded / parts uploaded, not attested / STATE written, PENDING not removed / during post actions (evict half done);
- **worker points** WP1-WP4: before the first runner command / after each runner command of the chain / after the snapshot / while PNG parts are being written;

for every stage kind: genesis, prepare (A, B, restart), nonattempt, scope-finish, finish, visual-record PASS, REVIEW_INCOMPLETE (1st, 2nd, 3rd), interrupt (new folder, in place, RESTART_USED), freeze chain after STOP_*, OWNER_DECISION, AI entry S/G/V and V continuation, OPENED, RESTORE itself, ACK, DELIVERY, everyday SENT, FINAL;

crossed with every **Drive visibility** outcome where the point has a FIND (normal, lag within the waits, lag beyond both waits, duplicate same md5, foreign md5, missing part, md5 hidden), and with every **Dot answer** where the point leaves a role open (NOTHING_WRITTEN with transcript, NOTHING_WRITTEN not_available, WRITTEN, UNSURE, NO_CONVERSATION with the list showing none, NO_CONVERSATION with the list showing one, `ended=no`, a file found by the re-walk).

**Tiers and counts** (the builder records the exact numbers in TEST_RESULTS.json):
- **Tier A** (exhaustive, memoized runner, each scenario runs from its cached stage boundary to the **next stable point**: the first confirmed commit after the reset is resolved, or the expected STOP): CP1-CP10 x 26 stage kinds = 260; WP1-WP4 x 12 chain kinds = 48; the 6 non-normal visibility outcomes at the 3 FIND-bearing points (CP4, CP5, CP6) and at the head search, for 6 representative stage kinds = 6 x 4 x 6 = 144; the 8 Dot answers at the 5 open-role points (S, G, V, V continuation, OPENED) = 40; the r2 additions (OPENED then go, HALT/CLEAR with an open role, DELIVERY reset, INPUTS reset, rebase variants, kit change after reset) = about 30. About **520 scenarios**. Oracles O1, O2, O6, O7 always; O3 and O4 on the state reached.
- **Tier B** (end to end, real runner, no memoization): 24 scenarios to the end of the series (or the expected STOP), chosen to cover every stage kind, every resolution action, a rebase that holds and one that diverges, everyday delivery with a reset at DELIVERY, FINAL with a missing part, and the drill script of §15.2 step 8. All oracles O1-O7.

Each Tier B scenario runs to the end of the series (or to its expected STOP); each Tier A scenario to its next stable point. The oracles:
- **O1 no reveal** (G15, OP-01, O54): every printed OPEN, CONTINUE, NOTIFY_OWNER, ASK_USER, DELIVER, HANDBACK, and every block whose content depends on a runner result, is printed only when FakeDrive holds the entry and every part of the commit it depends on with the local md5; the header `state` during a commit is `SAVE`;
- **O2** at most one OPEN per START, at most one CONTINUE per continuation, at most one DELIVER `to=user` per permission; no second START per attempt outside T31/T43 (at most one of them per attempt); checked over the whole transcript of printed blocks, across commits (OPENED, HALT, CLEAR, ACK) and resets (r2, INT-01, INT-06);
- **O3** `outcomes()` of the final state equals the scenario's expected dispositions and flags (an oracle written from O44-O46, O55-O58, O61 directly: written-and-lost is EMPTY `AI_OUTPUT_LOST`, a continued V is `FAILED_BY_RESET`, and so on);
- **O4** the audit over FakeDrive's internal table is clean, or reports exactly the expected anomaly (FORK scenarios end in STOP, never in a silent re-run);
- **O5** `assemble --verify-frozen` gives `NEXT: DONE` for every frozen run;
- **O6** no file of a job folder is deleted before its FROZEN commit is confirmed;
- **O7** every REFUSED leaves the cache files byte-identical; every STOP has the expected code; the series never continues past a STOP.

### 14.4 One regression test per v1 finding (`test_v1_regressions.py`, 400 lines)

| v1 id | test |
|---|---|
| F1 (critical) | `test_f1_wipe_after_v_r2_written_before_ai_v_r2_confirmed`: REVIEW_INCOMPLETE committed, the reviewer writes r2, reset before the AI-V r2 commit: no OPEN or CONTINUE for V again; FROZEN with `VISUAL_QA_FAILED_BY_RESET`; ALL_FROZEN shows `FAILED_BY_RESET` |
| F2 | `test_f2_second_start_only_after_no_conversation` (+ the random-cut property, §14.1) |
| F3 | `test_f3_classify_reads_only_head_at_every_worker_point` (including a B prepare that needs A's FROZEN.json) |
| F4 | `test_f4_outcomes_total_over_frozen_shapes` |
| F5 | `test_f5_audit_planted_restore_unknown_to_final` |
| F6 | `test_f6_every_block_has_exactly_one_terminal_action` (grammar lint over every block printed in the suite) |
| F7 | `test_f7_written_lost_transcript_in_restore_entry` |
| F8 | `test_f8_dead_commit_plus_next_stage` (head entry visible without its PNG part, and the next stage never committed: rebase, then the next stage) |
| SAFE-01 | `test_safe01_unsupported_entries_halt_nothing_deleted` (FIFO, symlink, unreadable folder, mode 4755 in the job folder at snapshot, AI walk and evict) |
| SAFE-02 | `test_safe02_case_id_refused_before_any_write` (space, quote, newline, Unicode, fullwidth digit) |
| SAFE-03 | `test_safe03_probe_p5_same_call_check_refused` |
| SAFE-04 | `test_safe04_enospc_or_short_write_at_every_durable_write` (ENOSPC, EIO and a short write injected into `durable` at each call site: HALT, no UPLOAD line printed) |
| SAFE-05 | `test_safe05_trailing_newline_and_bad_id_refused` |
| SAFE-06 | `test_safe06_session_start_git_error_prints_stop_block` |
| SAFE-07 | `test_safe07_setup_runs_detached_and_gate_uses_tool_call_limit` |
| OP-01 | `test_op01_start_on_drive_before_first_open` |
| OP-02 | `test_op02_lost_restore_upload_three_tries_then_stop` |
| OP-03 | `test_op03_truncated_all_frozen_part_reuploaded_before_handback_b` |
| OP-04 | `test_op04_placeholders_refused_state_unchanged` (`'{CONVERSATION_ID}'`, `<id>`, `CONV`, a README example) |
| OP-05 | `test_op05_probe_same_session_refused` |
| OP-06 | `test_op06_helper_never_needs_a_listing` (FakeDrive has no listing method; the whole suite passes) |
| OP-07 | `test_op07_drive_calls_per_run_within_budget` (counts FakeDot's Drive calls per normal run: at most 16 with 3 PNG parts; scope run +6; REVIEW_INCOMPLETE +4; restore with hint at most 15) |
| OP-08 | `test_op08_every_file_uploaded_once_when_drive_is_normal` |
| OP-09 | `test_op09_selftest_worker_death_bounded`, `test_op09_opened_required_without_list`, `test_op09_everyday_asks_in_order` |
| TST-01 | `test_tst01_second_start_same_attempt_chain_invalid` |
| TST-02 | `test_tst02_nothing_written_with_file_found_is_written` |
| TST-03 | `test_tst03_not_ended_is_written` |
| TST-04 | `test_tst04_md5_hidden_download_back_mismatch_is_fork` |
| TST-05 | `test_tst05_consumer_tree_sha_mismatch_chain_invalid` |
| TST-06 | `test_tst06_prompt_changed_halts` |
| TST-07 | `test_tst07_b_before_a_frozen_chain_invalid_and_runner_refuses` |
| TST-08 | `test_tst08_under_stage_direct` |
| TST-09 | lint `test_tst09_no_catch_all_assertions` |
| TST-10 | `test_tst10_free_space_preflight` |
| KIT-1 | `test_kit1_release_swap_after_genesis_stops` |
| KIT-2 | `test_kit2_zip_route_rehashes_the_kit` |
| FLAGS-1 | `test_flags1_wrong_shared_or_real_carrier_inconsistent` |
| FLAGS-2 | `test_flags2_empty_carriers_distinct_per_reader` |
| FLAGS-3 | `test_flags3_runner_failed_runs_get_empty_carriers` |
| MK-1 | `deploy/test_make_kit.py::test_mk1_header_slip_in_one_copy_recovers` |
| MK-2 | `deploy/test_make_kit.py::test_mk2_duplicate_binary_names_refused` |
| GATE-1 | `test_gate1_gates_checked_on_every_go` |
| TEST-1 | `test_test1_kit_change_with_run_in_flight_stops` |

Also (design §E): `test_stale_at_refused`, `test_fork_at_restore_lagging_n_plus_1`, `test_rebase_diverged_flags_reset_diverged`, `test_rewalk_forces_written`, `test_no_conversation_without_list_is_written`, `test_consumer_tree_sha_mismatch`.

r2 regression tests for the spec-review findings (`test_r2_findings.py`, about 400 lines; each in Tier A unless marked B):

| finding | test |
|---|---|
| INT-01, IMP-01 | `test_int01_opened_commit_then_go_no_second_open` (list `no`: OPEN then=now, OPENED commit, `go` twice: zero further OPEN lines, AWAIT printed once); `test_int01_halt_clear_with_open_role_no_second_open` (WALK_UNSUPPORTED_ENTRY HALT during the AI walk, config-only CLEAR in the same boot: zero further OPEN lines); both also as table rows of `test_core_table` for the plan |
| INT-02 | `test_int02_v_nothing_written_not_available_without_owner_check_chain_invalid` (core); `test_int02_v_not_available_q_replace_flags_owner_check`; `test_int02_v_not_available_e_freezes_visual` |
| INT-03 | `test_int03_score_check_refuses_pending_owner_items`; `test_int03_write_found_makes_pair_empty`; `test_int03_superseded_window_conversation_makes_pair_empty`; `test_int03_unlogged_conversation_empty_and_flagged`; `test_int03_outcomes_owner_items_listed` (outcomes table) |
| INT-04 | `test_int04_rebase_restore_over_finish_stage_folds` (core: T49 then T42 on the undone state, S4 with `copies: []`); `test_int04_rebase_missing_part_not_declared_confirms_mismatch`; `test_int04_drill_rebase_audit_clean` (B: deleted PNG part, rebase, audit exit 0) |
| INT-05 | `test_int05_single_part_absence_is_not_missing`; `test_int05_part_appears_at_third_check_stops_and_recurs_after_reset`; `test_int05_second_superseding_start_rebase_limit`; `test_int05_list_shows_conversation_rebase_conflict`; `test_audit_rebase_over_present_part_owner_review` |
| INT-06 | `test_int06_reset_at_delivery_asks_before_any_resend` (reset after DELIVER to=user printed: the next blocks hold no DELIVER to=user before the ASK_USER answer; `arrived=no` gives exactly one); `test_classify_c7_before_c8` |
| INT-07 | `test_int07_output_changed_after_archive_halts_before_consumer`; mutant G17 |
| INT-08, IMP-05 | `test_test1_kit_change_with_run_in_flight_stops_after_reset`; `test_kit1_release_swap_after_genesis_stops_after_reset`; `test_imp05_committed_halt_with_run_in_flight_cleared_after_reset`; `test_int08_non_config_kit_cannot_clear_after_reset`; `test_audit_kit_change_recomputed` |
| INT-09 | `test_int09_second_q_series_genesis_refused`; `test_int09_config_only_kit_changing_series_or_gates_refused`; `test_int09_release_series_pin_mismatch_refused`; `test_audit_second_qualification_series` |
| INT-10 | `test_int10_inputs_committed_before_prepare`; `test_int10_reprepare_once_then_abandon_asks_user`; `test_int10_everyday_not_available_no_retry`; `test_int10_inputs_changed_refused` |
| INT-11 | `test_int11_hintless_restore_recheck_finds_lagging_entries_fork` |
| INT-12, IMP-07 | `test_int12_no_change_refusal_commits_halt_and_survives_reset`; `test_imp07_chain_rows_first_match_none_shadowed` (core) |
| INT-13 | `test_int13_everyday_second_nothing_written_only_restart_exhausted` (core flag justification) |
| INT-14 | `test_int14_halt_with_open_role_resolved_then_cleared_after_reset` |
| IMP-02 | `test_imp02_enumerated_yes_and_tools_web_accepted`; `test_imp02_free_text_key_name_refused` |
| IMP-03 | `test_imp03_v_open_names_runner_folder_and_png_rule` |
| IMP-04 | every Tier A/B reset runs the README bootstrap (§14.2); `test_imp04_notes_lost_step0_finds_commit`; `test_imp04_no_commit_file_stops` |
| IMP-06 | `test_imp06_restart_run_frozen_at_prepare_stop_reaches_final` (core and B) |
| IMP-08 | the §4.8 enumeration with series-guard precedence; `test_imp08_restore_at_final_is_t05` |
| IMP-10, IMP-11 | `test_reuse.py` steps 3 and 5 as revised |
| IMP-12 | `test_imp12_joblock_released_before_each_runner_command` |
| IMP-13 | `test_imp13_reconciled_interrupt_seen_as_record_change` (a marker left in a placed folder; the next command's result decides the row) |
| IMP-14 | lint L9 as revised; `test_imp14_deliver_blocks_ascii_alias` |
| IMP-15 | `test_imp15_step_resets_per_head`; `test_imp15_restore_phases_forward_only` |
| IMP-16 | `test_fold_foreign_release_sha_chain_invalid` (core); `test_audit_planted_foreign_release_entry` |
| IMP-17 | `test_imp17_review_not_fresh_context_continues`; `test_imp17_conversation_id_mismatch_continues_then_limit` |

### 14.5 v1 driver (`--v1-driver`, design §E)

`tests/v1_driver.py` replays the blocking scenarios (F1, F2, OP-01, SAFE-04, TST-01, F3, F4, F5, SAFE-01, FLAGS-1, FLAGS-3, OP-04, OP-02, OP-03, SAFE-02, SAFE-03, OP-06) against `deploy/vm/cps_vm.py` (unchanged, sha 7524987...) with the `deploy/vm/test_cps_vm.py` World and Dot (imported by path) and asserts that each fails on v1. Its result goes into the admission package; it is not part of the 15-minute budget.

### 14.6 Lints (`test_lints.py`)

| id | lint |
|---|---|
| L1 | every code in the `CODES` registry (`core/names.py`, the union of §13) is raised in at least one test run and asserted by name (the harness records raised codes); every code raised in the source is in the registry |
| L2 | `vio/*` imports from `cpsvm2.core` only `cpsvm2.core.step`; `core/*` imports no `os`, `subprocess`, `shutil`, `tempfile`, `time`, `fcntl`, `pathlib`, `io` and calls no `open`, `print`, `datetime.now`, `time.time` (AST scan) |
| L3 | REUSE_MANIFEST (§1.4, `test_reuse.py`) |
| L4 | `core/` line coverage 100% from the core tests (stdlib `trace`) |
| L5 | block grammar of every printed block (F6) |
| L6 | every README example is in the test kit's `doc_samples` and is refused (OP-04) |
| L7 | no assertion on an exit code with `or` (TST-09) |
| L8 | runner, evaluator and aggregator files have their pinned sha256; `deploy/vm/` has the v1 shas of `ADMISSION_VM_HELPER_V1.json` |
| L9 | (r2, IMP-14) every printed path round-trips through `shlex` and is ASCII; a case id occurs in a printed line only as a component of a helper-built absolute path (checked by parsing every path in every block of the suite and every case id of the test jobs); no printed line contains a title, a cell value, a runner stdout line or a non-ASCII character |
| L10 | `UNUSED_REUSED` report (join_slices, scrub), not failing |

### 14.7 Mutation set (`--mutants`)

`tests/mutants.py` applies each mutant as a text patch to a temporary copy of `deploy/vm2/` (the original is never touched), runs the named killing tests, and requires a failure. Every mutant must be killed.

New mutants:
| id | mutant | killed by |
|---|---|---|
| G1 | savepoint prints the next block before the parts are confirmed | O1 in `test_resets`, `test_op01_start_on_drive_before_first_open` |
| G2 | a copy with another md5 is accepted | `test_fork_foreign_md5` |
| G3 | the head search accepts a single absence of N+1 | `test_fork_at_restore_lagging_n_plus_1` |
| G4 | T43 accepts NO_CONVERSATION from OPENED | `test_core_table` (T43), `test_no_conversation_from_opened_is_written` |
| G5 | a continued V is resolved like a started one (T46 removed) | `test_f1_...` |
| G6 | the re-walk (§8.6 step 3) is skipped | `test_rewalk_forces_written` |
| G7 | `tree_list` ignores walk errors and unsupported entries | `test_safe01_...` |
| G8 | the `--at` check is removed | `test_stale_at_refused` |
| G9 | `rebase_bind` is ignored (unbound rebase) | `test_rebase_diverged_flags_reset_diverged` |
| G10 | outcomes D6 removed (SCORE for a run frozen at GENERATE) | `test_f4_...` |
| G11 | score_check writes one empty carrier per case | `test_flags2_...` |
| G12 | S5 release check removed | `test_fold_foreign_release_sha_chain_invalid` (core: a crafted entry with a foreign `release_sha256` folded directly) and `test_audit_planted_foreign_release_entry` (the audit's re-fold); the world test `test_kit1_...` stops earlier, at §8.1 step 11, and does not kill it (r2, IMP-16) |
| G13 | `re.match` instead of `re.fullmatch` in names | `test_safe05_...` |
| G14 | T32 accepts any START reason | `test_tst01_...` |
| G15 | a worker result shown before its commit (the WAIT or header carries the runner NEXT) | O1, `test_g15_no_reveal` |
| G16 | `marks` cleared at every commit (r1 behaviour) | `test_int01_*`, O2 |
| G17 | the worker copies the archive's tree sha into `consumed` instead of measuring | `test_int07_*`, `test_tst05_*` |
| G18 | C8 (unbound re-run) evaluated before C7 (delivery question) | `test_int06_*` |
| G19 | T45 without the transcript guard | `test_int02_*` |
| G20 | a single part absence accepted as missing | `test_int05_single_part_absence_is_not_missing` |
| G21 | `score_check build` ignores pending owner items | `test_int03_score_check_refuses_pending_owner_items` |
| G22 | config-only decided by `unpack_kit`'s return value | `test_imp05_*`, `test_int08_*` |
| G23 | GENESIS without the other-Q-series check | `test_int09_second_q_series_genesis_refused` |

v1 mutants (ADMISSION_VM_HELPER_V1.json conditions: M08, M10, M14, M16, M19, M24, M26, M27, M30-M32, M34, M37, M39):
| v1 id | status |
|---|---|
| M27 | mapped: "START_ALREADY_RECORDED removed, a second conversation opens silently" (TST-01) -> G14, killed by `test_tst01_...` |
| M08, M10, M14, M16, M19, M24, M26, M30, M31, M32, M34, M37, M39 | **definitions are not in the repository** (the record names the ids only). The builder MUST obtain the review-1 mutation list from the review workpapers and complete this table before the admission review: each row either "mapped to G<n> or a new v2 mutant M2-<n> of the same rule, killed by <test>", or "path deleted: <v1 function> has no v2 counterpart (§1.6)". The admission review refuses an incomplete table (§17 OQ-1). |

### 14.8 Preflight and budget

`run_tests.py` refuses to start (exit 2, `PREFLIGHT_FREE_SPACE`) when the work folder's file system has less than 1 GiB free (TST-10; the v1 review ran out of disk), and records the free bytes, the scenario counts per tier, the seconds per scenario and the final test count in TEST_RESULTS.json (the count is reconciled in the admission record). r2 (IMP-09), budget from the v1 measurement (749 s wall with `--jobs 4`, 2,768 s summed, ADMISSION_VM_HELPER_V1.json) and the counts of §14.3: core and lints about 1 minute; Tier A about 520 scenarios at an estimated 3 s each with the memoized runner (about 1,600 CPU-seconds); Tier B 24 scenarios at an estimated 100 s each with the real runner (`finish` alone takes minutes, RUN_JOB_COMMANDS.md:33; about 2,400 CPU-seconds); about 4,000 CPU-seconds, so **about 20 minutes wall with `--jobs 4` on 4 CPUs** (longest first, as v1's `run_parallel`). These are estimates: the first green run measures them, and the admission records the measured times; the budget is a measurement, not a gate. The v1 driver and the mutants are separate runs.

---

## 15. Line budgets and admission review

### 15.1 Line budgets (measured, not caps; design §G)

| module | lines | note |
|---|---|---|
| core/names.py | 120 | |
| core/entry.py | 160 | |
| core/fold.py (TABLE included) | 220 | |
| core/plan.py (next_action, chain_next) | 160 | r2: classify and head_search moved to core/session.py |
| core/session.py (session_next: the §8.1 steps, RESTORE_WORK phases, classify, head_search, kit-change comparison) | 220 | + r2 (IMP-15): the session and restore machine had no module |
| core/outcome.py (outcomes, final_dispositions) | 120 | r2: + owner verdicts (INT-03) |
| core/step.py | 40 | + (not in design) |
| vio/savepoint.py | 200 | |
| vio/drive.py | 150 | |
| vio/runner.py | 250 | |
| vio/place.py | 250 | |
| vio/host.py (kit intake, fingerprint/PASS/self-test glue) | 120 | + |
| vio/durable.py | 60 | + |
| vio/v1compat.py | 90 | + (mostly copied v1 definitions) |
| vio/v1reuse.py | 880 + header | verbatim |
| vio/v1mod.py | 330 | modified, reviewed as diffs |
| cli.py (go/found/answer, session glue: carries out session_next's Steps) | 200 | r2: + session glue |
| worker.py | 150 | + |
| vm2.py | 20 | + |
| session_start.sh | 80 | |
| maint/audit.py | 350 | |
| maint/assemble.py | 120 | |
| maint/score_check.py | 220 | admitted separately; r2: + OWNER_CHECKS.json |
| probe_p5.py | 80 | admitted separately |
| **total** | **about 4,600** | the design's rows sum to 3,820 (its "about 3,100" undercounts); +480 for the modules marked + in r1, about +300 in r2 (session module, owner verdicts, kit-change comparison, INPUTS) |

Tests about 3,400 lines (core 900, resets 1,100, reused-archive tests 400, v1 regressions 400, r2 findings 400, lints and maint 200).

### 15.2 Admission plan (design §G, in order)

1. Owner decisions Q1-Q8: done (O54-O61).
2. Probe answers P1, P2/M004, P3, P5 recorded in `CURRENT_STATE.json` and in the kit `gates`.
3. This specification reviewed (with §17 answered).
4. Build in `deploy/vm2/`; `deploy/make_kit.py` MK-1/MK-2 fixes.
5. One green full run of `run_tests.py` on a machine with at least 1 GiB free, all scenarios in one run, test count recorded; the v1 driver run (each blocking scenario fails on 95df270); the mutation run (every mutant killed, v1 table complete).
6. Independent five-lens admission review under the version id `cps-vm-helper.v2` (integrity, safety, operator executability, tests with adversarial verifiers and the mutants, kit route and pre-gate), reviewers given the code and the governing documents, not the build workflow's conclusions:
   - `core/` in full (about 1,040 lines with `session.py`), and `cli.py`, `worker.py` in full (they hold the commit order);
   - `vio/` only for "carries out the Step and decides nothing" (plus `durable.py` and `v1compat.py` in full);
   - `v1mod.py` as diffs against the v1 segments;
   - `v1reuse.py` by REUSE_MANIFEST (the test proves byte identity);
   - `maint/audit.py`, `assemble.py` in full;
   - `score_check.py`, `probe_p5.py` and `make_kit.py` admitted separately.
   Blocking rule as in review 1: any confirmed or plausible critical, or a confirmed major on an integrity rule, blocks.
7. Record `deploy/vm2/ADMISSION_VM_HELPER_V2.json` with every file's sha256.
8. Before qualification: a series-D drill on the Dot's VM with invented jobs: at least a reset at a commit boundary, one during an open generator (NOTHING_WRITTEN), one during a V continuation, one forcing a rebase (a deleted PNG part); it ends with `assemble --verify-frozen` at the `/home/agent` paths, a clean `audit`, and `score_check` CONSISTENT. The audit is the mandatory pre-gate of scoring. The 38 reserved answers stay closed throughout.

---

## 16. Runner v4 claims (R-claims), with evidence

All line numbers are `deploy/run/cps_job.py` at sha256 `7505e98ac88bc09a5e0507124e4cb381a5491c1112f418bcf5ca6553ab14f431` (verified for this spec with `sha256sum`), unless another file is named.

| id | claim the spec relies on | evidence |
|---|---|---|
| R1 | the runner is `cps-job-runner.v4`; the helper pins its sha | `VERSION` :44 |
| R2 | exit codes: 0 continue, 2 usage, 3 stop, 4 refused; continue steps are SCOPE_READER, GENERATE, VISUAL_REVIEW, DELIVER_CHECK, FREEZE, DELIVER, DONE | :102, :103, :3166, :3169-3173 |
| R3 | every command ends with one JSON line then `NEXT: <step>` or `REFUSED: <code>`; freeze prints `NEXT: DONE` or `NEXT: STOP_FREEZE_INCOMPLETE`; verify-frozen prints `NEXT: DONE` or `NEXT: STOP_FROZEN_FOLDER_CHANGED`; a failed record append prints `NEXT: STOP_RECORD_CONFLICT` | :3164-3165, :3171-3172, :2799-2800, :2807-2808, :2861-2866, :3156 |
| R4 | the record stores only the first token of NEXT, so the helper takes `prompt=`/`folder=` from stdout | :3152 |
| R5 | a refusal before the stage consumes still appends a not-completed REFUSED entry to the record (and so to the ledger) unless frozen: a runner REFUSED usually changes the record | `run_stage` :3108-3125 (:3122); ledger mirror in `Job.append` :1020-1042 (:1040) |
| R6 | each subcommand holds an flock on the job folder; tools it starts inherit it; a second command is refused JOB_BUSY before the record is read (nothing appended) | `Job.lock` :967-983 (JOB_BUSY :981), tool lock `Stage.run` :1176, `open_job` :1105-1112 |
| R7 | (r2, IMP-13, corrected; re-verified) a killed stage leaves a marker; the next command on that folder (`open_job` :1105-1112, unless frozen) silently appends an entry with result INTERRUPTED and `next` STOP_INTERRUPTED to the record (and so the ledger), removes the marker, and then carries on with its own work and prints **its own** result (for the same stage `REFUSED: STAGE_ALREADY_COMPLETED`, R37); no code path prints `NEXT: STOP_INTERRUPTED` (RUN_JOB_COMMANDS.md:34 says otherwise; the code governs). The interrupted stage never re-runs in that folder | `reconcile` :1115-1145 (append :1144), `mark` :1089-1096, `open_job` :1105-1112, `require_stage_open` :1074-1077 |
| R8 | `interrupt` refuses RESPONSE_WRITTEN, appending nothing, only if the response file exists on this VM (`os.path.lexists`): it cannot see a file a reset removed | :2873-2877, `written_response` :2881-2895 (:2895) |
| R9 | `interrupt` is refused INTERRUPT_RESTART_USED in a restart folder or after an in-place restart (inside preflight, so a refused entry is appended) | :2919-2921, `restart_used_here` :2898-2905 |
| R10 | `interrupt` is qualification only; needs the last completed NEXT to be GENERATE or SCOPE_READER and no frozen generator response; reason `TECHNICAL_<CODE>`; times within [end of that stage, start of this command] | :2918, :2923-2927, :2930, :2940, :2946, `TECHNICAL_RE` :62 |
| R11 | `interrupt` without a frozen scope response ends `NEXT: STOP_TECHNICAL_INTERRUPTION`; with an agreed scope it moves the output aside and prints `NEXT: GENERATE` again (in place) | :2932, :2976, :2988, :2994 |
| R12 | after STOP_TECHNICAL_INTERRUPTION only freeze runs in that folder | `require_not_interrupted` :1661-1665, used :1671, :1949 |
| R13 | `prepare --qualification`: one run per case and reader; a restart once; reader B only after reader A of the case is frozen, and not while A's one restart is unused | `ledger_admit_prepare` :867-906 (:886, :889, :897, :902, :903) |
| R14 | `restart_problem` reads `<earlier job_dir>/FROZEN.json`; when it is missing it returns a reason string (not None), so for reader B an evicted A folder would make the DN7 check pass silently: the helper must place A's FROZEN.json | :834-865 (:854, :857), used at :903 |
| R15 | a job folder is used once (JOB_DIR_EXISTS) and a ledger job_dir once (QUALIFICATION_JOB_DIR_REUSED) | :1506, :880-881 |
| R16 | case ids match `CASE_ID_RE`; a jobs root with whitespace is refused | :60, :1477 |
| R17 | `visual-record` refused REVIEW_INCOMPLETE saves the review to `qa/visual_review_attempts/<seq>.json` and appends the refused entry | :2447-2452 (`on_refused` :2451), `save_review_attempt` :2459-2468 (:2466), :2512 |
| R18 | a review with any failure, or `overall FAIL`, is never refused: it is recorded as FAIL | :2505 |
| R19 | `visual-record` PASS ends `NEXT: FREEZE` (qualification) or `NEXT: DELIVER_CHECK` (real jobs) | :2657 |
| R20 | the review path is fixed (`qa/visual_review/VISUAL_REVIEW.json`); a conversation id is required from the review or `--reviewer-conversation-id`; the runner's placeholder test only checks a leading `<` (so the helper's stricter validation is needed, OP-04) | :2483-2485, :2489, :2510, :2531, `placeholder` :289-291 |
| R21 | `finish` in qualification needs `--generator-model` and `--generation-record` at `run/GENERATION_RECORD.json`; the record's prompt sha must equal the generator prompt; its times must lie between the end of the last stage that printed GENERATE and the start of finish; `exported` needs `--transcript` with that sha | :1894, :1900, :1907, :1912, `generation_window_start` :1831-1836, :1920, :1930 |
| R22 | `finish` with no response file is refused RESPONSE_REQUIRED (nothing consumed) | :1964 |
| R23 | `finish` requires the generator output folder to hold only `response.json` and `scratch/` | :2016 |
| R24 | later stages re-read the live release at the path given at prepare (so restore must put RELEASE.json back at `BASE/runtime/RELEASE.json`) | `check_live_release` :678-697 (:694) |
| R25 | the job folder path is resolved, and the ledger keys every entry by that path (placement must use the original absolute paths) | :953, `ledger_record_entry` :794-797, `ledger_check_record` :800-817 |
| R26 | the ledger is one JSON line per entry, chained to the sha256 of all earlier bytes, fsynced; a missing ledger is refused for every command but prepare/nonattempt | `Ledger.chain_problem` :758-774 (:769), `Ledger.append` :776-788 (:785), :727 |
| R27 | every command checks the record against the ledger's last entry for that folder (record and ledger must be placed from the same commit) | :815 |
| R28 | freeze writes the ledger freeze entry, then FROZEN.json (deterministic), then removes write bits; a recorded freeze without FROZEN.json is completed by running freeze again | `finish_freeze` :2774-2809 (:2787, :2795, :2800, :2808), `cmd_freeze` :2734-2738 |
| R29 | verify-frozen opens the ledger read-only, writes nothing, and its verdict does not depend on write bits | :2838-2867 (:2844, :2860) |
| R30 | (r2, IMP-13, narrowed; re-verified) a frozen folder refuses `JOB_FROZEN` for every stage subcommand that calls `require_not_frozen` (scope-finish :1669, finish :1947, visual-record :2472, deliver-check :2668, freeze :2742, interrupt :2916); `verify-frozen` (:2838-2867) does not refuse a frozen folder, it verifies it; `freeze` completes a recorded freeze whose FROZEN.json is missing (:2736-2738, R28) | :1063-1072 and the call sites named |
| R31 | `nonattempt` freezes at once (FROZEN.json, ledger entry) | `cmd_nonattempt` :2998-3085 (:3084) |
| R32 | `deliver-check` prints `DELIVER file=<path>`, a path holding the title (the helper never prints runner output) | :2730 |
| R33 | FROZEN.json lists every file of the folder (so `carrier/convert/carrier.json` presence and sha come from it) | `frozen_doc` :2755-2763 (:2757, :2762); carrier written at :2102-2109 |
| R34 | `prepare` prints `NEXT: GENERATE prompt=<P> folder=<F>` or `NEXT: SCOPE_READER prompt=<P> folder=<F>`; a scope hold is `OWNER_DECISION` | :1459, :1651, :1633 |
| R35 | `deliver-check` refuses qualification jobs and requires a visual PASS | :2671, :2677 |
| R36 | `scope-finish` in qualification needs `--reader-prompt-sha256` equal to prepare's pin | :1690, :1692 |
| R37 | a completed stage never runs again in the folder (STAGE_ALREADY_COMPLETED) | :1077 |
| R38 | tool output goes to `logs/`, never to stdout | :1183 |
| R39 | the responses whose freezing forbids a restart, and the written files that forbid one | :93, :95 |
| R40 | a refusal raised before a job folder exists (or in `main`) appends nothing | `main` :3241-3242 |
| R41 | release status per mode | :59 |
| R42 | (r2, INT-09) the runner reads RELEASE.json only through named fields (`Release.__init__` :316-345 with `get` :268-278; other reads :361-362, :442, :541, :554) and has no key-set check, so an extra top-level key `vm_helper` (`{"series": ...}`) is ignored by the runner while its bytes stay pinned by the release sha | :268-278, :316-345 |
| R43 | (r2, IMP-17) `visual-record` refuses `REVIEW_NOT_FRESH_CONTEXT` (reviewer kind, model or effort) and `REVIEWER_CONVERSATION_ID_REQUIRED` (missing, placeholder, or different from `--reviewer-conversation-id`) in its preflight, before consuming, exactly like `REVIEW_INCOMPLETE`: the attempt file is saved (`on_refused`) and a refused entry is appended | `cmd_visual_record` :2445-2451, `visual_record_pre` :2470-2512 (:2505-2511), `check_review` :2515-2533, `run_stage` :3102-3125 (:3122) |
| R44 | (r2, IMP-06) `restart_problem` decides from the ledger and the earlier folder's FROZEN.json only; it does not look at whether that run is itself a restart run (`restart_of`), so a restart run frozen at a technical STOP_ before any response yields None | :834-865 |
| R45 | (r2, IMP-03) `finish` prints `NEXT: VISUAL_REVIEW prompt=<qa/VISUAL_REVIEW_PROMPT.md> folder=<job>/qa`, and the review prompt tells the reviewer to open the listed PNGs under `qa/visual_deliverable/` and `qa/visual_internal/` and to write only `{OUT}/VISUAL_REVIEW.json` | :2229; `deploy/run/VISUAL_REVIEW_PROMPT_TEMPLATE.md`:3-7; RUN_JOB_COMMANDS.md Stage 5 :162-172 |
| R46 | (r2, IMP-12) the runner's job-folder lock is a non-blocking exclusive flock of the folder itself, so any other holder of a flock on that folder (the helper's `JobLock`, the same mechanism, cps_vm.py:789-813) makes the command refuse `JOB_BUSY` | `Job.lock` :967-983 (:978, :981) |

Evaluator and aggregator claims (frozen files, not changed):
| id | claim | evidence |
|---|---|---|
| R-E1 | the evaluator v4 reads only `carrier['items']` (each item's `values` and `id`) | `research/evaluation/compare_target050.py` :408, :418-424, :445-446 |
| R-E2 | an empty `items` scores 0 matched against every non-null target value (unpaired target rows and panel sets are counted) | `compare_target050.py` `score` :328-360 |
| R-E3 | the aggregator refuses two readers bound to one carrier of a case (`READERS_SHARE_CARRIER`) and binds each comparison to its declared carrier sha | `research/evaluation/aggregate_qualification050.py` :139-153 |

---

## 17. Decisions this spec makes beyond the design, and open questions

### 17.1 SPEC DECISIONS (for the admission review)

| id | decision | where |
|---|---|---|
| SD-1 | the I/O package is `vio/`, not `io/` (stdlib name clash) | §1.3 |
| SD-2 | the ENTRY document is the tgz member `MANIFEST.json` (the reused `Archive` requires that first member) | §3.3 |
| SD-3 | kit name in setup is `SESSION_KIT_<12 hex of the zip sha256>.zip` (a config-only CLEAR kit changes the zip, not the release) | §3.2, §8.2 |
| SD-4 | everyday profile parts use ASCII journal names, not the writer's title-bearing name; the personal copy is `PERSONAL_COPY.xlsx` with `PERSONALIZATION_LOG.json` under `~/cps-deliveries/<case>/<user key>/<utc14>/`, and the user receives it under the standard title name (r2, IMP-14) | §11.3 |
| SD-5 | r2 (INT-10), replacing r1's "no INPUTS entry": an everyday job starts with an INPUTS entry committed before prepare; a prepare lost to a reset is redone once (RESTORE `reprepare`, logged), a second loss abandons the job and asks the user (O49, O60). This matches the design's own budget row "INPUTS+prepare" | §3.5, T13, T15, T41, §8.5 C8b, §11.2, §11.4 |
| SD-6 | everyday S/G NOTHING_WRITTEN: one more conversation in the same folder (the runner has no everyday interrupt), **only with an exported transcript** (r2, INT-10); attempt 2 freezes `FREEZE_EXHAUSTED` (INT-13) | T44, §11.4 |
| SD-7 | a cache mismatch in the same boot takes the restore path and stops at placement (`PLACE_TARGET_NOT_EMPTY`) | §2.5 |
| SD-8 | OPENED mandatory is realised by `OPEN_CONVERSATION ... then=now` plus a new terminal action `AWAIT_CONVERSATION` | §6.4, §7.1 |
| SD-9 | everyday chains visual-record into deliver-check (one commit), matching the design's commit count | §7.3, §11.2 |
| SD-10 | HALT and CLEAR are entry kinds; local sticky halts are cleared by a session with a config-only kit and logged in the next entry's `cleared_local` | §3.4, §13.5 |
| SD-11 | r2 (INT-05): a REBASE supersede (design B6: the head START was never printed) **counts against O58's one superseding START per attempt** (shared with NO_CONVERSATION); it needs an authenticated part absence (twice, `w_abs` apart, plus a third check in the RESTORE commit), and with a conversation list `list_shows_none`; a second need is `STOP REBASE_LIMIT`; its window is an owner item before scoring (§9.5). See OQ-12 | T31, T43, T49, §8.4, §8.5 C5 |
| SD-12 | r2 (INT-01): `marks` are keyed by the start, continuation or permission they belong to, written durably before the instruction is printed, and never cleared by a commit; row 5 matches only a STARTED role without an OPENED record; so an OPEN is never printed twice for one START, across OPENED, HALT, CLEAR and ACK commits | §2.3, §7.1 |
| SD-13 | r2 (IMP-13): a STOP_RECORD_CONFLICT from the runner is treated like any STOP_* (freeze, notify); STOP_INTERRUPTED is never printed by runner v4 (R7), and a reconciled interruption is seen only as a record change | §7.3 |
| SD-14 | interrupt times are the START utc and the RESTORE utc | §7.4 |
| SD-15 | header `state=SAVE` during every commit, so the header reveals nothing | §5.1, §6.1 |
| SD-16 | the PASS file is named by the full 64-hex fingerprint and accepted by known md5 without download | §3.2, §8.3 |
| SD-17 | r2 (IMP-17): `REVIEW_NOT_FRESH_CONTEXT` and `REVIEWER_CONVERSATION_ID_REQUIRED` are continued like `REVIEW_INCOMPLETE` (fixed helper texts) and share O61's limit of 2 continuations; see OQ-13 | T21, §7.3 X3-X4, §7.8 |
| SD-18 | r2 (INT-12, IMP-07): a runner refusal that changed nothing commits a HALT entry `RUNNER_REFUSED`; design B4's "a REFUSED that changed nothing commits nothing" is read as "commits no STAGE and binds no result" (a HALT reveals no result and is handback C); `JOB_BUSY` is retried inside the worker's bounded wait | §7.2, §7.3 X2, X7 |
| SD-19 | r2 (INT-09): the Drive folders are code constants; the qualification series is pinned in RELEASE.json `vm_helper.series` (ignored by the runner, R42); a Q GENESIS refuses when another Q series exists; a config-only kit cannot change series, helper trees, accepted releases, gates or validation patterns | §2.2, §7.12, §10.1 |
| SD-20 | r2 (INT-08, IMP-05): config-onlyness and "run in flight" are decided from the journal (the head's kit, downloaded from `CPS/setup`; `head.state.current` and open roles), recorded in `kit_change`, re-checked by the fold and the audit; `unpack_kit`'s return value decides nothing | §8.1 step 11, §8.2, S5, T59, §10.1 |
| SD-21 | r2 (INT-03): the owner's O52/O55 verdicts enter scoring as `OWNER_CHECKS.json`, applied by the pure `final_dispositions`; `score_check build` refuses while any item lacks a verdict; see OQ-15 | §9.5, §10.3 |
| SD-22 | r2 (INT-02, INT-10): the replacement reviewer needs the same transcript guard as the rule-3 restart (O45, O55): exported, or (Q only) not_available with OWNER_CHECK; in everyday a not_available reading never buys a retry or a replacement; see OQ-11 | T44, T45, §8.6, §11.4 |
| SD-23 | r2 (IMP-09): the reset tiers use a memoized real runner (every byte produced by runner v4 on an identical before-state) and stop at the next stable point; 24 end-to-end scenarios use the real runner unmemoized; the test budget is about 20 minutes wall, measured | §14.3, §14.8 |
| SD-24 | r2 (IMP-14): the everyday DELIVER blocks name an ASCII copy `BASE/deliver/<run8>/STANDARD.xlsx` of the runner's title-bearing standard file | §2.1, §11.3 |
| SD-25 | r2 (IMP-04): after a reset the Dot restores the repository at the commit of its last `CPSV-REPO` line, or from the maintainer's static `CPS/VM2_RELEASE.md`; see OQ-14 | §6.1, §6.6 |
| SD-26 | r2 (INT-11): without a hint or newest-first listing, the RESTORE is followed by a re-check of N+1..N+3 after `w_abs`; the remaining risk is stated in §12.2 | §8.4 step 6, §12.2 |

### 17.2 Open questions

| id | question | default if unanswered |
|---|---|---|
| OQ-1 | The definitions of v1 mutants M08, M10, M14, M16, M19, M24, M26, M30-M32, M34, M37, M39 are not in the repository (only M27 is described). Who supplies the review-1 mutation list? | admission blocked until the table in §14.7 is complete |
| OQ-2 | The design's line budget rows sum to 3,820, not "about 3,100"; this spec budgets about 4,300. Is the larger reviewable surface acceptable? | proceed; the review scope of §15.2 keeps full reading to core, cli, worker, durable, v1compat, audit, assemble |
| OQ-3 | P5 on a platform whose tool calls share one shell: `probe_p5.py check` refuses SAME_CALL and P5 stays OPEN. Does the owner accept the probe message's manual `ps -o sid=` evidence instead? | P5 stays OPEN; all jobs wait (O50 analogue) |
| OQ-4 | Do `SAVED_QA.json` and the PNG renders reproduce byte for byte on identical inputs? If not, the rebase binding falls back to `{next, codes, deliverable_sha256, carrier_sha256}` (§7.10) | the builder measures and records it before the review |
| OQ-5 | Everyday personal copy (r2, IMP-14): on the VM `~/cps-deliveries/<case>/<user key>/<utc14>/PERSONAL_COPY.xlsx` with `PERSONALIZATION_LOG.json` (ASCII user key; the display name inside the log), in the profile folder as `CPSJ_E1_<seq6>_DELIV01.xlsx` / `_DLOG01.json`, and sent to the user under the standard title name `<name>(未填).xlsx`. Acceptable to the owner (DEPLOYMENT_MODEL names the folder layout but not the file names)? | SD-4 |
| OQ-6 | Should the unused reused functions `join_slices` and `scrub` be dropped from the reuse list (manifest fidelity vs dead code)? | kept, reported by L10 |
| OQ-7 | The conversation id format (P1) determines `conversation_re`; the kit refuses a regex that matches a README example. | gate P1 stays OPEN until given |
| OQ-8 | Everyday: after the one EVERYDAY_RETRY (now only with an exported transcript), a second NOTHING_WRITTEN fails the job (SD-6); without transcript export every interrupted everyday conversation fails the job. Confirm this reading of O45/O49/O55/O60 for real jobs. | SD-6 |
| OQ-9 | If the Dot's chat does not survive a reset (probe 7), there is no hint: the kit comes through the FOLDER_MANIFEST route and the head by galloping from 1 (about +20 calls per reset). Acceptable? | as specified |
| OQ-10 | `p2_failed_upload_can_appear == yes` with a lag longer than the waits leads to FORK STOPs (fail-closed, maintainer cycles). Should the owner raise the waits instead (cost: time per commit)? | waits as in §5.1 |
| OQ-11 | (r2, INT-02) O55 speaks of "the one rule-3 restart" (S, G). This spec extends the same allowance to the one replacement reviewer in qualification: without transcript export, a V NOTHING_WRITTEN reading allows the replacement, flagged OWNER_CHECK, and a write found makes that run's visual QA `FAILED_BY_RESET`. The alternative is no replacement without an exported transcript (every interrupted reviewer fails visual QA). Which does the owner want? | the extension, as specified (SD-22) |
| OQ-12 | (r2, INT-05) The design's rebase (B6) supersedes a never-printed head START. This spec counts it against O58's "once per attempt" and, when the platform has a conversation list, requires it to show none; without a list (P1 no) the rebase rests on an authenticated part absence plus the owner's window verdict before scoring. Does the owner accept a REBASE supersede without a conversation list, given O58's "only when the Dot's conversation list shows no such conversation"? | accepted with the owner verdict (SD-11); if not, a rebase over a head START without a list is `STOP REBASE_CONFLICT` and the run waits for the maintainer |
| OQ-13 | (r2, IMP-17) May `REVIEW_NOT_FRESH_CONTEXT` and `REVIEWER_CONVERSATION_ID_REQUIRED` be continued within O61's limit of 2 (instead of halting the series with case C)? | yes, as specified (SD-17) |
| OQ-14 | (r2, IMP-04, INT-09) Two new maintainer-side artifacts: `CPS/VM2_RELEASE.md` in the static folder (the commit for the bootstrap when the Dot's notes are lost) and the `vm_helper.series` key in RELEASE.json. Acceptable? | as specified |
| OQ-15 | (r2, INT-03) Who writes OWNER_CHECKS.json (the owner, or the person the owner names under O52), and is a pinned sha plus `checked_by` sufficient as its signature? | the owner or the named person; sha pinned in SCORE_PLAN and the score record |

---

## 18. Review responses

Spec review of r1 (2026-11-10): 14 integrity findings (INT-01..INT-14) and 17 build findings (IMP-01..IMP-17). Result: **30 accepted, 1 partly accepted (IMP-09), 0 rejected**. Every runner claim touched was re-read in `deploy/run/cps_job.py` at sha256 `7505e98a...` (verified with `sha256sum` on 2026-11-10): R7 and R30 corrected, R42-R46 added; v1 claims re-read in `deploy/vm/cps_vm.py` at sha256 `7524987...` (unpack_kit :2728-2757, runner_path :567-568, Halt :404-411, EXIT_* :49, spawn :4898-4916, JobLock :789-813, run_runner :5048-5052) and `deploy/vm/README.md`:95-102. Owner questions raised by the resolutions: OQ-5 (extended), OQ-8 (revised), OQ-11..OQ-15.

| finding | verdict | resolution | sections changed |
|---|---|---|---|
| INT-01 (critical) | accepted | Marks are keyed by the start, continuation or delivery permission they belong to and are never cleared by a commit (§5.1 step 8 copies them); next_action row 5 matches only a STARTED role without an OPENED record, so an OPENED role goes to AWAIT; a HALT and its CLEAR in one boot keep the marks; after a reset the RESTORE resolves the role first (and C2 now resolves open roles before a CLEAR, INT-14). Tests `test_int01_opened_commit_then_go_no_second_open`, `test_int01_halt_clear_with_open_role_no_second_open`, oracle O2 across commits; mutant G16. SD-12 rewritten | §2.3, §5.1, §7.1, §4.7 I17, §8.5 C2, §13.5, §14.3, §14.4, §14.7, §17 SD-12 |
| INT-02 | accepted | T45 now has T44's transcript guard: exported with a `transcript/` member, or (Q only) not_available with `owner_check` and flag OWNER_CHECK; a V NOTHING_WRITTEN with not_available and no owner_check is CHAIN_INVALID (T48); in everyday a not_available V reading freezes visual QA (no replacement). I5 extended to V. A V owner check that finds a write makes the run's visual `FAILED_BY_RESET` (§9.5). O55 names the rule-3 restart only, so the extension to the reviewer is put to the owner (OQ-11) | T45, T48, §4.7 I5, §6.5, §8.6, §9.5, §11.4, §12.2, §14.4, §14.7 G19, §17 SD-22, OQ-11 |
| INT-03 | accepted | New owner input `OWNER_CHECKS.json` (`cps.vm2-owner-checks.v1`) with a verdict per `owner_items` entry (every OWNER_CHECK, every superseded-START window including rebase windows and the audit's owner-review items, and the O52 sheet) plus unlogged conversations; pure `final_dispositions` turns `WRITE_FOUND`, `CONVERSATION_FOUND` and unlogged rows into EMPTY (`OWNER_CHECK_FAILED`, `SUPERSEDED_WINDOW_CONVERSATION`, `UNLOGGED_CONVERSATION`) and sets `qualification_flagged`; `score_check build` refuses `OWNER_CHECKS_INCOMPLETE` while any item lacks a verdict. Signature = pinned sha + `checked_by` (OQ-15). Mutant G21 | §9.1, §9.2, §9.3, new §9.5, §10.1, §10.3, §14.4, §14.7, §15.1, §17 SD-21, OQ-15 |
| INT-04 | accepted | (a) T42 compares the resolutions with `open` of the state after T49's undo; (b) S4 has a rebase variant: the head's missing parts appear in `confirms` with `copies: []` and must equal `rebase.missing_parts`; (c) audit step 2 excuses a part missing from the listing only when the next entry is a RESTORE declaring that rebase with that part, so the §15.2 drill can end with a clean audit. Golden rows added for a rebase over a finish STAGE with START-V and PNG parts | §3.4 confirms, §4.2 S4, T42, T49, §4.8, §10.1 step 2, §14.4 |
| INT-05 | accepted | A missing head part needs two absences `w_abs` apart plus a third check in the RESTORE commit's FIND (`STOP REBASE_PART_APPEARED`, re-checked by C5b after a reset); with a conversation list the rebase over a head START needs `list_shows_none` (`STOP REBASE_CONFLICT` otherwise); a REBASE supersede counts against O58's one superseding START per attempt (`ROLE.supersedes`, `STOP REBASE_LIMIT`); audit rule `AUD_REBASE_OVER_PRESENT_PART` as an owner-review item; the window is an owner item before scoring (INT-03). SD-11 rewritten; the no-list case goes to the owner (OQ-12). Mutant G20 | §3.5 RESTORE, §3.11, T31, T43, T49, §4.7 I8, §5.1 step 5, §6.5, §8.4 step 5, §8.5 C5, C5b, §10.1, §12.2, §13.2, §14.4, §14.7, §17 SD-11, OQ-12 |
| INT-06 | accepted | The delivery row (now C7) precedes the general run-in-flight row (now C8); the RESTORE carries `delivery_question`, whose effect (T42) sets `notify = ASK_USER` (about DELIVERY) and `resend_ok = false`; next_action rows 17-18 print DELIVER `to=user` only with `resend_ok` (set by the DELIVERY commit for the first send and by an ACK `arrived=no`), once per permission (mark `DELIVER_USER`); `arrived=yes` sets `sent` (row 19 freezes). Test `test_int06_reset_at_delivery_asks_before_any_resend`; mutant G18 | §3.5 RESTORE, §3.11, T42, T52, T55, §7.1 rows 17-19, §8.5 C7, C8, §11.4, §14.4, §14.7 |
| INT-07 | accepted | The worker, under JobLock and before every consumer command, strictly walks the role's `output` folder, compares with the last archive (`HALT AI_OUTPUT_CHANGED`, nothing run) and records the **measured** value in `body.consumed[].tree_sha256`. Mutant G17 (copies the archive value) | §3.5 STAGE, T20, §4.7 I11, §7.2 step 3, §7.5, §13.3, §14.4, §14.7 |
| INT-08 | accepted | Config-onlyness and run-in-flight come from the journal: when the kit differs from `head.kit_sha256` the session downloads the head's kit from `CPS/setup`, compares member lists, and records `kit_change` (both member lists, `config_only`, changed config keys, `run_in_flight` from `head.state.current`/open roles) in the RESTORE or CLEAR body; S5 and T59 recompute `config_only` from the lists, the audit from the zips (`--setup-dir`, `AUD_KIT_CHANGE`); `unpack_kit`'s return value decides nothing. Reset variants of `test_test1`/`test_kit1` added. Mutant G22 | §2.2, §3.5, §4.2 S5, T59, §8.1 step 11, §8.2, §10.1 step 5, §13.5, §14.4, §17 SD-20 |
| INT-09 | accepted | Folders are code constants (`FOLDERS`); the config's `series` must equal RELEASE.json `vm_helper.series` in Q and D mode (runner ignores extra release keys, R42, verified); a config-only kit cannot change series, helper trees, accepted releases, gates or validation patterns (`CONFIG_CHANGE_NOT_ALLOWED`), and gates must equal the genesis gates (`GATES_CHANGED`); a Q GENESIS requires every other `CPSJ_Q<k>_000001.tgz` absent twice (`QUALIFICATION_SERIES_EXISTS`); the audit flags any other Q series in the folder (`AUD_SECOND_QUALIFICATION_SERIES`). Mutant G23 | §2.2, §3.1, §3.5 GENESIS, §7.12, §10.1 step 1, §13.2, §14.4, §16 R42, §17 SD-19, OQ-14 |
| INT-10 | accepted | Everyday EVERYDAY_RETRY only with an exported transcript; not_available gives FREEZE_LOST with ASK_USER (and a V reading gives FREEZE_VISUAL_FAILED). A new INPUTS entry (the design's own "INPUTS+prepare" budget row) is committed before prepare; a prepare lost to a reset is redone once (RESTORE `reprepare`, T41, logged) and a second loss abandons the job with ASK_USER (C8b); the prepare is bound to the committed input shas (`INPUTS_CHANGED`). SD-5 replaced, SD-6 revised, OQ-8 revised | §3.4, §3.5, §3.11, T06, T13-T16, T41, T44, §4.7 I18, §6.5, §7.1 row 20, §8.5 C8b, §8.6, §11.2, §11.4, §12.2, §13.1, §14.4, §17 SD-5, SD-6, OQ-8 |
| INT-11 | accepted | Without a hint or newest-first listing, the RESTORE commit is followed, before anything runs, by a wait of `w_abs` and FINDs of N+1 (own md5 only), N+2 and N+3 (absent), else `STOP FORK`; the remaining risk (a search that misses the same names consistently for longer) is stated in §12.2 and caught by the audit's `AUD_DUPLICATE_SEQ`. The "recover the hint from reports/" option was not taken: the Dot's notes are exactly what a lost chat loses, and the static folder route (step 0, IMP-04) gives the commit, not the head | §2.3 RESTORE_WORK phases, §8.4 step 6, §12.2, §14.4, §17 SD-26 |
| INT-12 | accepted | One behaviour: a runner refusal that changed nothing (except JOB_BUSY) commits a HALT entry `RUNNER_REFUSED`; the worker result has no `nothing` status; JOB_BUSY is retried inside the worker's bounded wait. Design B4's "commits nothing" is read as "commits no STAGE and binds no result" (SD-18) | §7.2 step 4, §7.3 X2, X7, §13.3, §17 SD-18 |
| INT-13 | accepted | New action `FREEZE_EXHAUSTED` for everyday attempt-2 NOTHING_WRITTEN, justifying only `RESTART_EXHAUSTED_BY_RESET`; `AI_OUTPUT_LOST` is keyed only to `FREEZE_LOST` | T44, §4.6, §7.1 row 13, §8.6, §11.4 |
| INT-14 | accepted | C2 with a matching clear first runs the §8.6 resolution of any open role, then commits RESTORE (with those resolutions) and CLEAR; the resolution's action runs after the CLEAR. Test `test_int14_halt_with_open_role_resolved_then_cleared_after_reset` | §8.5 C2, §13.5, §14.4 |
| IMP-01 | accepted | Same defect and fix as INT-01 (row 5 keyed on STARTED without OPENED record; marks never cleared by a commit); no-list scenario under O2 | as INT-01 |
| IMP-02 | accepted | The placeholder refusal (key names, pattern names, doc samples) applies only to the free-text patterns `{CONV, MODEL, PLATFORM, EFFORT, ID, CASE_ID, COPYPATH}`; enumerated patterns admit only their values; TOOLS items are checked only against `doc_samples`. Tests `ended=yes`, `tools=web` | §6.3, §14.4 |
| IMP-03 | accepted | START records `folder` (the runner's NEXT folder, `qa/` for V, R45) and `output` (the walked folder, `qa/visual_review/` for V); OPEN_CONVERSATION for V says it may open only the PNGs the prompt lists and write only `F/visual_review/VISUAL_REVIEW.json`, as RUN_JOB_COMMANDS Stage 5 | §3.11, §4.4, §6.4, §7.5, §16 R45, §14.4 |
| IMP-04 | accepted | Bootstrap lines in §6.1 and the README (clone, fetch, detached checkout of COMMIT, one retry after a partial clone); COMMIT from the Dot's last `CPSV-REPO` line or, with notes lost, from the maintainer's `CPS/VM2_RELEASE.md` (step 0; `SESSION_NO_COMMIT`); `session_start.sh --commit` checks HEAD (`SESSION_COMMIT_MISMATCH`). `FakeDot.reset` deletes `BASE/repo` and runs the README lines against a local bare mirror. OQ-14 | §6.1, §6.6, §6.8, §13.2, §14.2, §14.4, §17 SD-25, OQ-14 |
| IMP-05 | accepted | Same root as INT-08: config-only is decided from the halted kit's members (downloaded from `CPS/setup` by `head.kit_sha256`) and recorded in `kit_change`; test `test_imp05_committed_halt_with_run_in_flight_cleared_after_reset` | as INT-08 |
| IMP-06 | accepted | FROZEN `restart_eligible = restart_problem(...) is None and restart_of is None` (the runner function ignores `restart_of`, R44, re-verified at :834-865); T24 enforces false for restart runs; T62 only considers original runs. Test with a restart run frozen at a prepare STOP_ reaching FINAL | §3.5 FROZEN, T24, T62, §16 R44, §14.4 |
| IMP-07 | accepted | The chain table is now numbered X1-X20, first match wins, specific rows before general ones (rebase binding X1 first; JOB_BUSY, REVIEW_CONTINUABLE, INTERRUPT_RESTART_USED before the generic refusal rows; verify-frozen and freeze STOP rows before the generic STOP_* row X19); a test checks no row is shadowed. The no-change refusal is one behaviour (INT-12) | §7.2 step 4, §7.3, §14.4, §17 SD-18 |
| IMP-08 | accepted | `apply` evaluates the series guards T02-T06 first (a match is CHAIN_INVALID with that row id) and treats every "otherwise" row as a fallback that is never evaluated as a guard; mutual exclusion is required among positive rows only, and the §4.8 contract says so | §4.1, §4.3 (fallback rows), §4.8, §14.4 |
| IMP-09 | partly accepted | The enumeration is now bounded and counted (Tier A about 520 scenarios to the next stable point with a memoized real runner; Tier B 24 end-to-end with the real runner) and the budget raised to about 20 minutes wall with 4 jobs, derived from v1's measured 749 s / 2,768 s. Not done: the per-scenario times are estimates, since nothing is built; the spec makes the first green run measure them and the admission record the measured values, instead of fixing a number now | §14 header, §14.3, §14.8, §17 SD-23 |
| IMP-10 | accepted | 57 corrected to 54 everywhere (54 rows, 880 lines, matching `reuse_scan.py` output); test step 3 takes the count from REUSE_MANIFEST | §1.3, §1.4 |
| IMP-11 | accepted | `runner_path` is a function; `EXIT_OK`, `EXIT_USAGE`, `EXIT_STOP`, `EXIT_REFUSED`, `EXIT_NEED`, `EXIT_BUSY` copied with v1 values; reuse test 5 also resolves `v1compat`'s own free names; worker log and result paths are spawn's `outbox/<kind>_<wid>.log`/`.out` | §1.4, §1.5, §1.6, §7.2 |
| IMP-12 | accepted | JobLock is taken only to probe (and released at once), for the consumer measurement, the snapshot and the evict walk, and is never held while a runner command runs (R46) | §7.2 step 3, §16 R46, §14.4 |
| IMP-13 | accepted | R7 corrected (reconcile appends INTERRUPTED silently; no code prints `NEXT: STOP_INTERRUPTED`; re-verified :1105-1145, :1074-1077, :1017-1018), R30 narrowed (verify-frozen verifies a frozen folder; freeze completes a missing FROZEN.json); the STOP_INTERRUPTED chain row removed; SD-13 rewritten | §7.3, §16 R7, R30, §17 SD-13 |
| IMP-14 | accepted | L9 restated: a case id may appear only as a component of a helper-built path after CASE_ID_RE; no title, cell value, runner output or non-ASCII. Everyday DELIVER names an ASCII copy `BASE/deliver/<run8>/STANDARD.xlsx`; the personal copy's names are fixed ASCII (`PERSONAL_COPY.xlsx`, `PERSONALIZATION_LOG.json` under `<case>/<user key>/<utc14>/`), and the user receives it under the standard title name; owner confirmation asked (OQ-5) | §2.1, §6.1, §6.3 COPYPATH, §6.4, §7.3 X18, §11.2, §11.3, §14.6 L9, §17 SD-4, SD-24, OQ-5 |
| IMP-15 | accepted | (a) `run8` defined in §0; (b) RESTORE_WORK phases enumerated, forward-only; (c) `step` is 4 digits and resets at every new head (`INTERNAL_STEP_OVERFLOW` above 9999); (d) the session and restore machine lives in new `core/session.py` (220 lines) with glue in `cli.py` (200 lines) | §0, §1.3, §2.3, §6.1, §6.3, §5.1 examples, §6.7, §15.1 |
| IMP-16 | accepted | G12 is killed by a core test folding a crafted entry with a foreign `release_sha256` and by an audit re-fold of a planted entry; the world test is noted as not killing it | §14.4, §14.7 G12 |
| IMP-17 | accepted | `REVIEW_NOT_FRESH_CONTEXT` and `REVIEWER_CONVERSATION_ID_REQUIRED` (refused before consumption with the attempt file and a refused entry, R43, re-verified :2445-2451, :2505-2511, :3102-3125) join `REVIEW_INCOMPLETE` in `REVIEW_CONTINUABLE`: a continuation with a fixed helper text, counted in O61's limit of 2; owner confirmation asked (OQ-13) | T21, T23, §4.6, §7.3 X3-X4, §7.8, §13.3, §16 R43, §17 SD-17, OQ-13 |
