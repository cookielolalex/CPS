<!-- Status: PLAN (spec delta r5) for cps-vm-helper.v2.1; not built, not reviewed, not admitted. Written 2026-11-11 from deploy/vm2/ADMISSION_VM_HELPER_V2.json (admission review 2 of 1d31801: DO_NOT_ADMIT, 47 findings), the reviewers' findings and probes, and the maintainer decisions D1-D16 for v2.1. Revised the same day (r4) after three critic lenses (integrity, operator, tests); section 7 answers each of their 35 gaps. Amended the same day (r5) by maintainer decision D16, which carries the operator's answers to probe M007 (facts F1-F8, invented data) into the plan; section 7.4 says what r5 changed and where. Applies on top of docs/handoff/VM_HELPER_V2_SPEC.md r2 and docs/handoff/VM_HELPER_V2_SPEC_DELTA_PROBES.md. -->

# cps-vm-helper.v2.1: delta r5 to SPEC_V2 r2 and the probe delta

Status: this is a plan for the builders. It is not built, reviewed or admitted. It starts from HEAD `2015773`, which is the v2
candidate `1d31801` plus its admission record. Each statement here changes `docs/handoff/VM_HELPER_V2_SPEC.md` r2
(cited as "r2 §n") or `docs/handoff/VM_HELPER_V2_SPEC_DELTA_PROBES.md` (cited as "§X.n"). Text this delta does not
mention stays as r2 and the probe delta have it. **Supersedes** marks the places where this delta replaces earlier text.
r4 replaced r3 of this file in full; §7.1-§7.3 say, gap by gap, what changed. r5 keeps every r4 decision and adds
only what D16 needs (§2.16, §5.4 and the rows, gates, tests and risks they touch); §7.4 lists each change.

Authority, in this order:
1. The owner's decisions O43-O63 in `docs/handoff/DEPLOYMENT_MODEL.md`.
2. The maintainer decisions D1-D16 for v2.1. They are fixed: this plan details them and does not reopen them. D16
   (2026-11-11, the M007 amendment) carries the facts F1-F8 that the operator reported for probe M007 on its own VM,
   with invented data, and that the maintainer verified against the operator's uploaded files (§2.16).
3. The admission record `deploy/vm2/ADMISSION_VM_HELPER_V2.json`.
4. r2 and the probe delta.

Decisions this plan makes beyond D1-D16 are numbered **SD-35** to **SD-71** and listed again in §6.1.

Notation:
- `C`, `M` and `T` are the build tracks (§1.1).
- "Fails on 2015773" is shown by the paired mutant (§1.1, §2.15.1).
- `BASE` is `/home/agent/cps` on the Dot's VM.
- Every example value is invented.

---

## 0. What v2.1 is

- **Version.** The version id is `cps-vm-helper.v2.1`. It is set in `HELPER_VERSION` in `core/names.py`, `VERSION` in
  `cpsvm2/__init__.py` and `host.pass_doc`. The fold's S6 refuses an entry whose `helper.version` differs
  (`HELPER_UNKNOWN`).
- **Schemas.** The schema names (`cps.vm2-entry.v1`, `cps.vm2-state.v1` and the cache schemas) stay. Their key sets
  change as §2.12 lists. No v2 journal exists, because v2 was never admitted and never ran on the operator VM, so
  nothing has to read both versions.
- **v2.1 shrinks.** It keeps one confirmation rule (download-back, §2.1), one re-ask rule for every operator slip
  (§2.2) and one clear mechanism for every stop, decided before anything moves (§2.4). It deletes the three variants
  that are dead on this platform: md5-visible mode, the listing head hint and the OPENED entry (§2.13). The non-test
  helper total goes down (§5.1).
- **The operator's platform (D16).** Probe M007 measured the Dot's VM and its tools (§2.16): DOWNLOADs go through a
  raw-file download and a `cp`, saved search results are the M004 envelope, an upload outside the owner's standing
  approval is refused, the Dot runs as uid 1000 without root, a long finish stage may not fit the proven 1,200 s hold,
  the disk has about 2.5 GB free, and resets are frequent. v2.1 adds two small rules for this (SD-69, SD-70), a
  non-root test pass (SD-71), README text, tests and gates; it designs nothing in the runner.
- **What stays unchanged.** Runner v4 `deploy/run/cps_job.py` stays byte-identical, at sha256
  `7505e98ac88bc09a5e0507124e4cb381a5491c1112f418bcf5ca6553ab14f431`. Helper v1 `deploy/vm/` stays rejected and
  unchanged.

---

## 1. Finding and condition table

### 1.1 Tracks, suites and how a row is proven

| track | owns |
|---|---|
| **M** (maint) | `deploy/vm2/cpsvm2/maint/*`, `deploy/vm2/tests/test_maint.py`, `deploy/make_kit.py`, `deploy/test_make_kit.py` |
| **C** (core) | everything else under `deploy/vm2/` except `tests/`: `cpsvm2/core/*`, `cpsvm2/vio/*`, `cli.py`, `worker.py`, `vm2.py`, `session_start.sh`, `probe_p5.py`, `README.md`, `REUSE_MANIFEST.json`. Under the shared-file protocol (§4), C also owns `tests/fakes.py` and `tests/core_world.py` |
| **T** (tests) | `deploy/vm2/tests/*` except `test_maint.py`, `fakes.py` and `core_world.py`. This covers the suites, `run_tests.py`, `seen.py`, `table_golden.json`, `budget_golden.json`, and the mutation harness `mutants.py` with the guard mutants |

**Suites and name prefixes.** Each new test follows the convention of its suite:

| abbreviation | file | test names |
|---|---|---|
| `ct` | `test_core_table.py` | `test_*` |
| `cm` | `test_core_more.py` | `test_*` |
| `vio` | `test_vio.py` | `t_*` |
| `cod` | `test_codes.py` | `test_*` |
| `v1r` | `test_v1_regressions.py` | `test_*`; a World extra is `x_*` |
| `rs` | `test_resets.py` | scenario names, and `special` methods |
| `lint` | `test_lints.py` | `t_*` |
| `p5` | `test_probe_p5.py` | `test_*` |
| `mt` | `test_maint.py` | `test_*` |
| `mk` | `deploy/test_make_kit.py` | unittest `MakeKitTest.test_*` |

**How a row is proven.** Every row's test must fail on the 2015773 behaviour. Its mutant (§2.15.1) shows this:
- A `W` mutant puts the 2015773 behaviour back into the v2.1 code, or removes one v2.1 rule. A test that kills it fails
  without that rule.
- An `N` mutant is one of the reviewers' mutants that survived at 2015773.
- For the test-gap findings T1-T10, HEAD behaves correctly. There, "fails on 2015773" means "fails on 2015773 with the
  reviewers' mutant applied". §2.15.6 gives the three-column proof table the build report must fill.
- T also runs the new tests that use no interface new in v2.1 once in a 2015773 clone, and records each failure in the
  build report. §2.15.6 lists them by name.
- A test or mutant marked **(non-root)** decides only in the non-root pass (SD-71, §2.16.4): root ignores permission
  bits, so there its mutant survives by construction. The D16 rows whose behaviour is correct at 2015773 (the non-root
  evict test, the disk-retention test) are proven like T1-T10, by their mutants.

### 1.2 One row per finding (all 47), per blocking item and per D16 item

| id | sev | change (files: functions) | regression test | mutant | track |
|---|---|---|---|---|---|
| INT-R2-01 | major | D6 (§2.5). `core/session.py`: phase APPROVAL right after FINGERPRINT, on both paths, before any FIND (SD-58); the step-6 RECHECK runs on every qualification and drill restore (SD-59). `cli.py` `apply_answer` action APPROVAL: `none` is recorded; `pending` prints `STOP WAIT_APPROVAL HANDBACK A` and changes nothing. `core/entry.py`: BODY GENESIS and RESTORE get `approval`, which must be `"none"`. M: AUDIT.json lists every approval and every same-boot RESTORE. README §3, §3.1, §4 | rs `D_refuse_reset_approval_pending`, `D_refuse_reset_approval_wrong_none`, `D_hint_restore_late_copy_at_n1_forks_at_recheck`; cm `test_d6_approval_asked_before_restore_and_genesis`, `test_d6_approval_before_head`, `test_op05_recheck_after_every_q_restore`; ct `test_d6_entry_approval_must_be_none`; mt `test_gap06_audit_lists_approvals_and_same_boot_restores`; lint `t_l14_readme_rules` | W01, W48, W74, W78, W89, W94, W95 | C (session, cli, entry, README, FakeDot approval policy); M (audit); T |
| INT-R2-02 = S-02 = OPX-03 (LOCAL-CLEAR) | major | D5 (§2.4). `cli.py`: `clear_check` replaces `sticky_halt` and decides the clear before anything moves (SD-56); `stop_block` (HALT.json for every HANDBACK C STOP including `HALTED_<code>`, the journal's head and kit, which the STOP header shows, `tried`, `halt_local`; an older HALT.json is kept; a damaged one becomes UNCLASSIFIED); `invalidate` (SD-68: both prefixes move the cache files, BASE/attest and BASE/inbox except `.boot`; `cleared_` also moves HALT.json); `load_cache` (a BLOCK.json behind STATE moves alone, one ahead invalidates; `halt_local` without HALT.json invalidates); the post resume after `clear_check`; `foreground_check` (`dead_<utc14>.json`). `core/session.py`: `clear_ok`, `config_only_ok`, `clear_verdict`; KIT_ACCEPT refuses a non-config-only change in a clearing restore; the moved-PENDING rule; the RECHECK condition; a RESTORE while HALTED keeps the halted kit and carries no `cleared_local` (SD-51, SD-57). `worker.py`: `files_found` before `settle`. `vio/place.py`: `settle`. `vio/v1mod.py`: `place_frozen` | rs `D_clear_same_boot_setup_failed`, `D_clear_same_boot_foreground_died`, `D_clear_same_boot_fork`, `D_clear_same_boot_fork_foreign_only`, `D_clear_same_boot_open_generator`, `D_clear_committed_halt_same_boot`, `D_sameboot_damaged_cache_restores`, special `test_foreground_died_same_boot_stops`; cm `test_d5_clear_verdict_exact_clear_and_config_only`, `test_d5_clearing_restore_refuses_release_change`; ct `test_session_c2_clear_restore_keeps_kit_then_clear_takes_it`, `test_d5_cleared_local_only_on_restore_and_genesis`; vio the `t_d5_*` tests of §2.15.5, `t_gap02_files_found_before_settle`, `t_gap04_moved_pending_foreign_copy_forks`, `t_gap08_clear_moves_attest_and_inbox`, `t_gap08_render_removes_stale_download_target`, `t_gap12_halt_removed_out_of_procedure_restores` | W02, W03, W51, W58-W67, W75-W77, W80-W82, W85, W91, W92, W97, W100-W103 | C; T |
| INT-R2-03 | minor | `core/entry.py`: RESOLUTION_KEYS gets `conversation`. `core/session.py`: `build_item` fills it from the answer, else the archived conversation, else null. `core/fold.py`: `e42` copies it into ROLE.resolution. `core/outcome.py`: the OWNER_CHECK item and the O52 sheet row show it. `worker.py`: `Chain.argv` passes it as interrupt `--conversation-id` | cm `test_int_r2_03_restore_conversation_recorded`; vio `t_int_r2_03_interrupt_gets_conversation_id` | W04, W53 | C; T |
| INT-R2-04 | minor | `core/fold.py` `_consumed_ok(R, b, sub)`: when the chain's first command is a consumer (`CONSUMER`), `body.consumed` must name exactly the ARCHIVED, unconsumed role of that letter (g20, g21, g23, g24). Other chains keep today's per-item check. `CONSUMER` moves from plan.py to fold.py | ct `test_int_r2_04_consumer_stage_without_consumed_is_t25` | W05 | C; T |
| S-01 | major | `vio/savepoint.py`: `_Env1`, `setup_block`, `setup_found` and `setup_verify` are deleted. `block`, `on_found` and `on_verify` take the loop dict and an explicit `cap`, `lag` and `folder`. `cli.py` passes `env.upload_cfg['max_upload_bytes']` | vio `t_s01_setup_failed_log_uploaded_without_kit_config` (World with an empty BASE/runtime) | W06 | C; T |
| S-02 | major | = INT-R2-02 | (INT-R2-02 tests) | W02, W03 | C; T |
| S-03 | minor | D3 (§2.2). In `savepoint.on_verify` and the merged download check, a download whose size is not the attested size is a slip, `DOWNLOAD_INCOMPLETE`. A FORK comes only from downloaded bytes. `cli.stop_block` moves the fork evidence to `outbox/v2/fork_<utc14>/`, also for the moved-PENDING FORK of a clearing restore | vio `t_s03_short_download_refinds_real_fork_keeps_bytes`; rs `D_slip_short_download_refinds` | W07 | C; T |
| S-04 | minor | `cli.run_command` runs any remaining `STATE.post` after `clear_check`, and only when no HALT.json exists; a clear moves STATE with its post. `savepoint.finish` carries the remaining `cache.post` ahead of the new actions | vio `t_s04_pending_post_resumed_before_next_commit`, `t_d5_post_action_halt_cleared_same_boot` | W08, W60 | C; T |
| S-05 | minor | `savepoint.write_commit`: the PartWriter whole sha256 and the per-file sha256 of the tar stream must equal `draft.payload_png` before PENDING is written, else `HALT PNG_MANIFEST_UNSAFE` | vio `t_s05_png_changed_before_part_write_halts` | W09 | C; T |
| S-06 | minor | `cli.delivery_commit`: the profile folder must print (`drive.prints(pf + '/deliveries')`, which is `drive.q` plus the `check_grammar` character set), else `REFUSED COPY_LOG_MISMATCH` before anything is committed | cod `test_s06_profile_folder_with_brace_refused_before_commit` | W10 | C; T |
| S-07 | minor | The `session_start.sh` launcher becomes `exec python3 -I -B -X pycache_prefix=/dev/null ...`. `vio/runner.py` `load_runner` compiles the hashed bytes into a fresh module. `session_start.sh` removes every `__pycache__` folder under the checkout before it writes the launcher (SD-63). M: `maint/audit.py` deletes its own loader and calls `vio.runner.load_runner` (one loader) | lint `t_l13_launcher_ignores_bytecode`; vio `t_s07_runner_loaded_from_hashed_bytes` (planted valid-header .pyc files, §2.10.3); v1r `test_gap11_session_start_removes_pycache` | W11, W12, W84 | C (launcher, runner, session_start.sh); M (audit call); T |
| S-08 | minor | `session_start.sh`: the HEAD == `--commit` check (step 6) moves before steps 5 and 4. The `CPSV-REPO` line and the final block stay last | v1r `test_s08_wrong_head_stops_before_setup` | W13 | C; T |
| S-09 | plausible | `cli.render` creates the parent folder of every DOWNLOAD target and removes any file already at that path, before BLOCK.json is written. The `mkdir` calls in `fetch`, `pass_phase` and `ensure_local` are deleted. FakeDot no longer creates parents and asserts that they exist. D16 (F3, §2.16.1): README §2 describes the DOWNLOAD route (raw-file download, then `cp` of the downloaded file to the target); FakeDot downloads into its own attachment folder and copies | vio `t_s09_download_parent_exists_when_printed`, `t_gap08_render_removes_stale_download_target`; lint `t_l14_readme_rules` (the DOWNLOAD sentence) | W14, W82, W104 | C (cli, README, fakes.py); T |
| S-10 | minor | = OPX-02 (the slip rule, §2.2.1) | vio `t_opx02_mistyped_id_refinds_then_commits` | W18 | C; T |
| S-11 | minor | `cli.run_command` catches `OSError` after `durable.DurableError` and prints `safe_stop(env, durable.DurableError(e.errno).code)` | cod `test_s11_oserror_outside_stage_prints_stop_block` | W15 | C; T |
| S-12 | minor | no new code (the OPX-07 fix) | rs special `test_foreground_died_same_boot_stops` as §2.15.5 specifies it: a real subprocess in its own process group, SIGKILL after the RUNNING line, returncode -9, the leftovers removed, then the clear | W16, W49, W58 | T |
| OPX-01 | minor | `vio/durable.py` `write_doc` sets `self_sha256` in place and returns the same dict. `save_cache` and `save_work` never rebind, so no alias goes stale | vio `t_opx01_restore_work_writes_kept` (after a reset during G, END is printed once; classify forced to C10 commits exactly one HALT entry); rs oracle "one END_CONVERSATION per open role per boot" | W17 | C; T |
| OPX-02 | major | D3 slip rule (§2.2.1) and D4 (§2.3): `savepoint.on_verify`, the merged download check, `cli.go_checks`, `cli.session_slip`, the `void` lookups in the session. Reprints never carry UPLOAD lines (SD-60). A raw file is consumed when it is accepted, and copies are taken by exact title (SD-61) | vio `t_opx02_mistyped_id_refinds_then_commits`, `t_d3_fourth_slip_stops_slip_limit`, `t_op02_reprint_has_no_upload_lines`, `t_op03_raw_file_consumed`, `t_d4_parse_raw_rules`, `t_d4_found_raw_search_and_listing_objects`, `t_d4_swapped_elements_assigned_by_title`; cm `test_d3_head_search_ignores_void_lookups`; rs `D_slip_wrong_id_refinds`, `D_slip_limit_then_clear`, `D_slip_stale_raw_head_search`. D16 (F4, §2.16.2): the first fixture of `t_d4_parse_raw_rules` and `t_d4_found_raw_search_and_listing_objects` is the envelope the Dot saved in M007 (every key, compact `JSON.stringify` text) plus an empty search envelope; lint `t_l14_readme_rules` (the raw-save sentence) | W18, W23, W46, W54, W69, W70, W86, W87, W88 | C; T |
| OPX-03 | major | D3: the download decides a size (§2.2.2, SD-38). Also D5 | vio `t_opx03_size_slip_refinds`; rs `D_slip_size_refinds` | W19 | C; T |
| OPX-04 | major | README §4 outcome rule (D10, §3); the spec side is §2.9 (SD-62) | lint `t_l14_readme_rules` | W20 | C (README); T |
| OPX-05 | major | D3c (§2.2.4): `cli.ai_commit` stores the final message of S, G and V as data. An empty file is accepted; an over-size one is `STOP AI_OUTPUT_TOO_LARGE` (SD-65) | vio `t_opx05_final_message_any_characters_verbatim`, `t_opx05_empty_final_message_accepted`, `t_opx05_oversize_final_message_stops` | W21, W90, W98 | C; T |
| OPX-06 | major | D3d (§2.2.5): `cli.start_chain` uses the counted refusal; a clear after its SLIP_LIMIT abandons the job (C8b); README §2.3 | cod `test_opx06_inputs_changed_bounded_then_slip_limit`; vio `t_d3_refusals_bounded_then_slip_limit`, `t_d3_refused_count_resets_per_block`, `t_d4_raw_invalid_reasked`; rs `E_inputs_lost_after_reset_bounded` (it also asserts the abandon after the clear); cm `test_gap13_c8b_after_second_restore_abandons` | W22, W68, W96 | C; T |
| OPX-07 | minor | In `cli.load_cache`, a BLOCK.json behind the valid STATE's head moves alone to `invalid_<utc14>/` and the cache stays valid; a BLOCK.json ahead of it invalidates the cache. HALT.json takes the head and the kit from the journal (§2.4.1) | vio `t_opx07_stage_death_stop_names_real_head_and_kit`, `t_gap05_block_ahead_invalidates_cache` | W16, W50, W79 | C; T |
| OPX-08 | minor | `session_start.sh`: `--kit none` (with any `--hint`) means no hint, and a no-hint bootstrap removes an older HINT.json. `cli.render`: a session block's header shows the head this session verified. README §1 | v1r `test_opx08_kit_none_bootstraps_without_hint` | W24, W73 | C; T |
| OPX-09 | minor | (a) README run order (all nonattempts for A, then for B; all A runs; all B runs). (b) `STOP IDLE` leaves the README. (c) `drive.do_text` prints `STOP UPLOAD_REFUSED HANDBACK A name=<N>`. (d) The tools answer is redefined (D9). (e) Attested times are `date -u` readings, answered as printed. (f) NO_BLOCK also applies when there is no CPSV line. (g) A refused upload leaves the Dot's notes only when the owner says it was approved or denied. (h) D16 (F5, §2.16.3): README §3.1 says that the Dot never works around a refused upload and waits for the owner; every UPLOAD the helper prints must be inside the owner's standing approval (G-10) | vio `t_opx09_refused_stop_names_the_file`; lint `t_l14_readme_rules` (with the never-work-around sentence) | W25, W95, W105 | C; T; gate G-10 |
| OPX-10 | plausible | README §7 budget (D15, SD-67): helper commands, Drive calls and saved results from `tests/budget_golden.json`, polls and conversation checks from G-3, restores without notes, the RECHECK, refused uploads (zero under G-10). FakeDot counts helper commands, Drive calls, saved results and waits (fakes.py) | v1r `test_opx10_tool_calls_match_budget_golden` (World extras `x_opx10` on the D baseline and on Q_baseline, `x_op07_restore`); lint `t_l14_readme_rules` (the README table equals the golden) | W26, W99 | C (README, fakes.py); T; gates G-3 (with M008, D16), G-10 |
| T1 | major | tests only; the vacuous `test_f1_core_continued_v_is_t46` loop is replaced by fold-level items (§2.15.6) | ct `test_t1_continued_v_other_outcomes_t48` | N06 | T |
| T2 | major | tests only | ct `test_t2_reader_b_waits_while_a_owes_restart`, with RESET_DIVERGED and A-restart1 controls | N07 | T |
| T3 | major | tests only; `test_session_rebase_and_recheck_fork` is rebuilt so that it FORKs through the sha branch | ct `test_t3_recheck_second_writer_at_n2_n3_forks` | N18 | T |
| T4 | major | tests only | ct `test_t4_continued_v_answer_of_another_boot_t39` (N05), `test_t4_ai_start_boot_must_be_the_start_boot_t39` (N04) | N05, N04 | T |
| T5 | minor | tests only | ct `test_t5_restart_after_in_place_interrupt_t14` | N52 | T |
| T6 | minor | tests only | vio `t_t6_finish_refuses_entry_that_is_not_pending` | N37 | T |
| T7 | minor | `started_utc <= ended_utc` moves into `names.check_answers`, which is pure (`UTC_OUT_OF_WINDOW started_utc`) | cm `test_t7_started_after_ended_refused` | N40 | C; T |
| T8 | minor | the session DOWNLOAD check becomes the slip rule | vio `t_t8_session_download_missing_refinds` | N42 | C; T |
| T9 | minor | tests only | vio `t_t9_empty_transcript_refused` | N44 | T |
| T10 | minor | tests only | ct `test_t10_config_only_change_of_other_key_release_not_accepted` | N50 | T |
| T11 | minor | `run_tests.py`: an `--only` name that matches no suite, test, scenario, special or `CONFIGS` key exits 2 and lists the names | lint `t_only_unknown_name_exits_2` | W27 | T |
| MAINT-1 | critical | D7 (§2.6). C: `core/fold.py` `job_dir_of` and `layout_of`. `_virtual` (T10-T13) requires `new_run.job_dir == job_dir_of(genesis.base, tag, case)`, else T14. `t01` requires `layout == layout_of(base)`, else SCHEMA_INVALID. M: `maint/assemble.py` requires `--root`, an existing empty directory that is not `/`; it takes the base from the GENESIS entry and refuses an ALL_FROZEN that names another; every job and ledger target comes from `job_dir_of` and that base; every write is confined under `realpath(root)`. The audit refuses through its fold (T14) and its ALL_FROZEN compare (AUD_OUTCOMES_DIFF) | ct `test_maint1_new_run_job_dir_must_be_the_layout_path` (one case per row T10-T13 and the everyday branch), `test_maint1_genesis_layout_base_relative`; mt `test_maint1_audit_refuses_hostile_new_run`, `test_maint1_forged_all_frozen_job_dir`, `test_maint1_assemble_base_from_genesis`, `test_maint1_wrong_mapping_refused`, `test_maint1_self_consistent_hostile_base_confined`, `test_maint1_symlink_after_begin_refused`, `test_maint1_assemble_root_required_empty_dedicated` | W28, W52 (C); W29a, W29b, W30, W93 (M) | C (fold); M (assemble, audit tests); T |
| MAINT-2 | major | D9 (§2.8). C: in `names`, TOOLS, O63_NOTE, O63_NOTE_RE, O63_REPORT and `tool_list`. `host` gets config key `tool_inventory_sha256` and kit member TOOL_INVENTORY.txt. Also `plan.end_keys`; `cli.ai_commit` (tools_present, `attest/tools.txt`, the final message of S and V); `entry` (S1 shape of `tools_present`); `worker.generation_record` (tools_enabled, notes); the O52 sheet row; README §4. M: `audit` writes the report `o63` and ties each GENERATION_RECORD.json to its consumed G entry. `score_check build` refuses `O63_ATTESTATION_MISSING` and writes `isolation_statement` | vio `t_maint2_tools_none_refused_inventory_file_accepted`, `t_maint2_generation_record_tools_and_o63_note`, `t_maint2_s_v_entries_archive_message_and_tools`, `t_maint2_inventory_sha_checked`, `t_maint2_tools_file_link_refused`; mt `test_maint2_score_check_requires_tools_attestation_and_states_isolation`, `test_gap10_generation_record_tied_to_g_entry` | W31, W32, W47, W71, W72 (C); W33, W83 (M) | C; M; T; gates G-2, G-6 |
| MAINT-3 | major | D8 (§2.7). M: `Audit.kit_change` re-derives with `session.kit_change`. For a CLEAR it also requires `session.clear_ok(to config clear, series, body.halt_seq, body.code)`. Every entry with `cleared_local` meets the four rules of SD-53. C: `fold.g59` requires `from_kit_sha256 != to_kit_sha256`; S1 allows `cleared_local` only on RESTORE and GENESIS; a RESTORE while HALTED keeps the halted kit, so the CLEAR carries the change (SD-51) | mt `test_maint3_audit_refuses_unauthorized_clear` (real kit zips: another halt, a null clear; from = to is AUD_CHAIN_INVALID T60); mt `test_maint3_audit_checks_cleared_local` (real kit zips, including a release change: AUD_KIT_CHANGE detail cleared_local); ct `test_maint3_clear_with_unchanged_kit_t60`, `test_d5_cleared_local_only_on_restore_and_genesis` | W34, W55 (M); W35, W75 (C) | M; C; T |
| MAINT-4 | minor | D8: `Audit.kit_change` reports `session.kit_change`'s code as `AUD_KIT_CHANGE` for every RESTORE and CLEAR. The audit-only verdicts are GATES_CHANGED, a series change in a non-config-only change, and doc_samples removed in a config-only change; the other codes reach the audit only as AUD_CHAIN_INVALID (§2.7) | mt `test_maint4_audit_only_kit_change_verdicts` (three real-zip cases) | W36 | M |
| MAINT-5 | minor | `maint/assemble.py` records `verify_frozen`. `score_check build` refuses `ASSEMBLE_NOT_VERIFIED` unless it is true and every run's verify is `DONE` | mt `test_maint5_score_check_refuses_unverified_assembly` | W37 | M |
| MAINT-6 | minor | `deploy/make_kit.py`: `cmd_pack` refuses two binary members with one file name (MK-2). `cmd_assemble` keys candidates by content and chooses each path by majority, then by `--expect` (MK-1, §2.10.9). T: v1r `test_mk1_header_slip_in_one_copy_recovers` and `test_mk2_duplicate_binary_names_refused` run the new make_kit tests; W38 and W39 live in `tests/mutants.py` with the path `deploy/make_kit.py` | mk `MakeKitTest.test_member_path_slip_in_one_copy_recovers` (`NOTE.mx` and `NOT~.md` variants), `MakeKitTest.test_pack_refuses_duplicate_binary_names` | W38, W39 | M; T (v1r hooks, mutants.py) |
| MAINT-7 | minor | C: `names.series_folder` gives a D series `CPS/drills/<series>`. M: `audit` uses `series_folder`, and `load_listing` skips folder rows and counts them | cm `test_maint7_drill_series_own_folder`; mt `test_maint7_drill_listing_with_folder_rows_clean` | W40 (C), W56 (M) | C; M; T; gate G-7 |
| MAINT-8 | minor | `score_check check` takes the four build inputs, checks their sha256 against the plan and re-runs `plan()`. Any difference is `PLAN_MISMATCH` | mt `test_maint8_check_detects_edited_plan` | W41 | M |
| MAINT-9 | minor | `Audit.review` widens its window by the genesis gate `p3_clock_tolerance_seconds`, as `core/outcome.outcomes` does | mt `test_maint9_review_window_widened` | W42 | M |
| MAINT-10 | minor | (a) C: `fold.jobs_of(jobs_doc)`, used by `cli.genesis`. M: the audit compares GENESIS `body.jobs` with `jobs_of` of the genesis kit's jobs file (`AUD_KIT` detail `jobs`). (b) C: `probe_p5.py start` refuses `--seconds` below `--min-gap` | mt `test_maint10_genesis_jobs_differ_from_kit_unclean`; p5 `test_maint10_probe_start_refuses_seconds_below_min_gap` | W43 (M), W44 (C) | C; M; T |
| TST-MUT (blocking item) | major | `tests/mutants.py`: for each mutant, a local clone, the substitutions, a commit, the clean-HEAD check, then the run (§2.15.4). The copytree is deleted. The guard mutants are generated for fold, session and the commit and restore glue (§2.15.2) | `run_tests.py --mutants --selftest`: W45a gives HARNESS_ERROR; W45b's reset failures carry `bootstrap_stop` and are not KILLED; W13 is KILLED; the generated set holds the reviewer and v2.1 sites. D16: a mutant marked `nonroot` runs its killing set only in the non-root pass (§2.15.4, SD-71) | W45a, W45b | T |
| D16-F2 (stage time) | D16 | no helper code. The release gate's hold check stays (`host.gates_problem`: every `stage_max_seconds` value + 60 <= `foreground_hold_seconds` <= `gates.p5_foreground_hold_seconds`, else RELEASE_GATE_OPEN). G-3 sets the values only after probe M008, by the rule of §5.4; OQ-25 holds the owner's choice if a stage does not fit. README's hold value is the release kit's (§3 notes) | none new: the existing gate tests stay; the values are kit data | none | gates G-3, G-9; OQ-25 |
| D16-F6 (non-root) | D16 | SD-70: `place.settle` sets the owner write bit on a target directory before it moves the target aside to another parent. SD-71: T builds the non-root pass (`run_tests.py --require-nonroot`, the `nonroot` group, `nonroot` mutants); the integrator runs it and records its counts in TEST_RESULTS.json and INTEGRATION.json (§2.16.4) | vio `t_d16_settle_moves_readonly_target_aside` (non-root); v1r `test_d16_evict_runner_frozen_folder_nonroot` (non-root); the non-root pass of the `nonroot` group | W106 (non-root), W107 (non-root) | C (place); T; integrator |
| D16-F7 (disk) | D16 | SD-69: `cli.run_stage` calls `require_space(env.lay, N.STAGE_FREE_BYTES, 'stage')` for every chain, before FOREGROUND.json is written; `names.STAGE_FREE_BYTES = 1000000000`. FakeDot records the job folders and journal files present at every block (§2.16.5, §5.4) | vio `t_d16_stage_refuses_low_space_before_runner`; v1r `test_d16_disk_bounded_over_runs` (World extra `x_d16_disk` on D_baseline) | W108, W109, W110 | C (cli, names, fakes.py); T |

### 1.3 Conditions before release and gates

| # | condition (`conditions_before_release` in the record) | where met | track |
|---|---|---|---|
| CBR-1 | a new candidate fixes every blocking item and gets a fresh independent admission review at its own commit (core/ in full, the fixed paths, the new tests) | this delta, then gate G-1 | GATE |
| CBR-2 | MAINT-1 (fold, audit, assemble; `--root` required, empty and dedicated; tests with a hostile job_dir) | row MAINT-1 | C, M, T |
| CBR-3 | LOCAL-CLEAR is built and tested in the same boot for SETUP_FAILED, FOREGROUND_DIED (also after a real SIGKILL) and FORK; a same-boot restore accepts or moves aside; HALT.json has the real head | row INT-R2-02; §2.4 | C, T |
| CBR-4 | MAINT-3 and MAINT-4, with real kit zips | rows MAINT-3, MAINT-4 | M, C, T |
| CBR-5 | INT-R2-01: the pending approval survives a reset as an attested answer, asked before any FIND of a session; a test_resets scenario calls FakeDrive.approve after a reset; the platform's late landing is measured on the operator VM | row INT-R2-01; gate G-5 | C, T, GATE |
| CBR-6 | direct tests for T1-T4; test_f1 replaced; the mutation harness fixed (committed clones, the clean-HEAD check); T11; the real SIGKILL test; an independent reviewer reproduces the full suite and the full mutant run at the release commit | rows T1-T4, T11, S-12, TST-MUT; gate G-1 | T, GATE |
| CBR-7 | operator path fixes OPX-02, OPX-05, OPX-06, S-01, OPX-04 | those rows | C, T |
| CBR-8 | the O63 helper layer is implemented; the owner records a dated prompt-clause decision before any qualification run | row MAINT-2; gate G-2 | C, M, T, GATE |
| CBR-9 | stage times measured on the operator VM (the 1,200 s hold against the longest stage); a reset drill on invented data on the operator VM, with a refused upload then a reset, and a same-boot local clear; the operator budget restated (OPX-10) | the budget: row OPX-10 and §5.3 (C, T); the measurements and the drill: gates G-3 (with probe M008 and the rule of §5.4, D16), G-4, G-10; the disk and non-root rows D16-F6 and D16-F7 | C, T, GATE |
| CBR-10 | score_check's own admission; MAINT-5 and MAINT-8 fixed | rows MAINT-5, MAINT-8; gate G-8 | M, GATE |
| CBR-11 | owner approval of the release kit and of the README; runner v4 byte-identical unless the owner chooses runner re-admission under O63 | gates G-9, G-2; lint L8 keeps the runner pin | GATE, T |

Gates need the Dot, the owner or a reviewer. They are not built.

| gate | what | who |
|---|---|---|
| G-1 | Independent admission review 3 at the v2.1 commit. It reproduces the full suite, the non-root pass (D16, SD-71) and the full mutant runs (hand, reviewer, builder, guard and `nonroot` mutants), and reviews every `EQUIVALENT` entry (§2.15.2). | reviewers |
| G-2 | The owner's dated decision on the O63 prompt layer, one of two options. (a) An owner-approved O63 suffix in the three templates. That needs an O42 ruling on the harness change, and runner re-admission v5 for the visual template's pin. (b) An O63 amendment that accepts the frozen prompts' restrictions plus the helper's attested tools-present lists and the fixed isolation statement. **Inconsistency for the owner:** the record's CBR-11 ties runner re-admission to option (b), but its `o63_implementation` text ties it to option (a). | owner |
| G-3 | On the operator VM: (a) **probe M008** (D16), a separate invented-data probe: the finish stage of an invented job whose visual QA renders 336 A3 pages at 150 dpi, the size of the longest real finish measured so far, with its single `pdftoppm` call also timed alone against the writer's 900 s per-subprocess timeout; (b) the longest run of every other `stage_max_seconds` key, the self-test included; (c) the interval at which the command tool returns while a long command runs (OQ-24); (d) the duration of the generator, scope-reader and visual-reviewer conversations of a dev-trial run. No `stage_max_seconds` value is set before (a) is measured. The kit's values are 1.5 times the measured stage values, each with +60 <= `foreground_hold_seconds`. If any value does not fit 1,200 s, the rule of §5.4 applies: G-3 also probes a 1,800 s hold, and OQ-25 goes to the owner if that does not settle it. README §7's poll and check counts and its totals, and README §2's hold value, are written from these values before G-9. | Dot, maintainer |
| G-4 | A drill on the operator VM: series D1 in `CPS/drills/D1`, invented jobs. It covers a reset at a commit boundary, a reset during an open generator (the Dot answers by the README rule: UNSURE unless the conversation never ran), a reset during a V continuation, one that forces a rebase, a refused upload followed by a reset (approval=pending), and a same-boot local clear. It also measures, on an invented file: whether an exact-name search returns a copy after it was moved to the Drive trash, and whether it returns a copy of the same name in another folder (OQ-23). It ends with `assemble --verify-frozen` into a dedicated root, a clean audit and score_check CONSISTENT. Because G-10 comes first, the drill's refused upload is provoked on purpose and named in the drill plan: the owner's pre-approval leaves out one named invented drill file, or the owner denies it at the platform's prompt (D16, F5). | Dot, maintainer |
| G-5 | On invented data on the operator VM: an upload is refused by the approval review, the VM is reset while the approval is pending, then the owner approves. The Dot records whether the approved upload lands after the VM is gone. The refused upload is one that the standing approval of G-10 does not cover, named in advance (D16, F5). | Dot, owner |
| G-6 | TOOL_INVENTORY.txt is the union of the tool names that two probe conversations report. Both are created the documented way with invented content. The Dot saves the list, one name per line; the maintainer puts it in the kit, pinned by `tool_inventory_sha256`. M006 saw 386 to 419 tools, so a single conversation is not enough. | Dot, maintainer |
| G-7 | The Drive folder `CPS/drills/D<n>` exists before a drill series starts. | maintainer |
| G-8 | score_check gets its own admission (MAINT-5, MAINT-8, the O63 checks) before any scoring. | reviewers |
| G-9 | The owner approves the release kit (including `clear: null`, `doc_samples` from README §8 and TOOL_INVENTORY.txt) and README v2.1, with the §7 numbers measured (G-3, `tests/budget_golden.json`). | owner |
| G-10 | **Required before G-4 and before qualification** (OQ-18, SD-67, D16). **Precondition: the owner's standing pre-approval covers every UPLOAD the helper can print** (§2.16.3). M007 showed that the platform's review refuses an upload that the owner's authorization does not name, even when the message's steps ask for it, and that it succeeds after the owner approves. The helper uploads only new files: into `CPS/qualification/` (Q journal and parts), `CPS/drills/D<n>` (D journal and parts, MAINT-7), `CPS/reports/` (a setup log after SETUP_FAILED) and `CPS/setup/` (the SELFTEST and FINGERPRINT_PASS files of a new fingerprint); everyday adds its records folder and the profile's deliveries folder. The owner's pending decision (new files only, into `CPS/qualification/` and `CPS/reports/` and their subfolders; the Synology document limits do not apply to these Drive uploads) covers the first and third of these; `CPS/drills/` and `CPS/setup/` must be named too (OQ-26). A qualification uploads about 330 files. | owner |
| G-11 | Only if G-4 shows that an exact-name search returns copies from another folder: the parent filter of §2.3 is built, with its test and mutant, and reviewed within G-1 before release. If G-4 shows it does not, README §6's removal text stands and nothing is built. | maintainer, reviewers |

---

## 2. Design (normative)

### 2.1 One confirmation rule (rule V restated)

**Supersedes** r2 §5.1 step 6 (the md5 branch), r2 §5.5, §X.5.5 steps 1, 5 and 7, the "share one size" rule of §X.8.2,
and the "two sizes: FORK" step of §X.8.4 step 1.

> **Rule V (v2.1).** A copy of name X that a FIND reported is *ours* if and only if:
> - (a) its Drive id is already recorded for X (PENDING copies, `STATE.head`, `state.files`, or RESTORE_WORK
>   `verified` for X); or
> - (b) its download-back has exactly the size the FIND reported for that id, and the sha256 of the expected bytes.
>
> A copy whose id is not recorded is always downloaded back, whatever size the FIND reported. No size is compared at
> `found`.

- **md5.** md5 is never read from Drive and never attested. The md5 in `confirms`, `files` and `parts` stays: it is the
  helper's own md5 of the verified local bytes. So the entry schema, S4 and the audit are unchanged.
- **`found`.** It takes `ID:SIZE` only. The md5-visible form and the gate key `p2_md5_visible` are deleted (§2.13).
- **Head search.** Each step treats copies as follows:
  - **Intermediate lookups** (gallop, binary search, N+1, N+2) use presence only. Copies are not compared.
  - **The head N.** Every copy is downloaded, and each must have its attested size, else it is a slip (§2.2.1). Copies
    whose bytes differ from each other are `FORK`. In a clearing restore whose moved PENDING has seq N, each copy must
    also have that PENDING's sha256, else `FORK` (§2.4.4).
  - **N-1.** Copies whose id is in `N.confirms[0].copies` need no download. Any other copy is downloaded; bytes other
    than `N.prev_sha256`, at the attested size, are `LINK_MISMATCH`.
  - **Head parts.** Ids in `state.files` are known. Others are downloaded, and other bytes are `FORK`.
  - **The RESTORE's own commit and the step-6 RECHECK** follow the commit rule. RECHECK runs on every qualification and
    drill restore (SD-59).

### 2.2 D3: operator slips are re-asked, bounded

#### 2.2.1 Slips (re-FIND)

A **slip** is an observation that the helper can show is neither ours nor anybody's. At the `go` after a DOWNLOAD
block, three things are slips:
- the target file is missing: `DOWNLOAD_MISSING`;
- the file's size differs from the size attested for that id: `DOWNLOAD_INCOMPLETE`. This covers a short file, a long
  file, and an attested size that was mistyped;
- (in commit and setup-file loops only) the file's sha256 equals another file of the same loop, because a copied id
  belongs to another part: `COPY_MISMATCH`.

On a slip the helper does four things, in this order:
1. It deletes that downloaded file.
2. It forgets the observation of that name:
   - in a loop (PENDING, or a setup-file loop), the name gets `copies = None` and `need = 'find'`, and loses its verify
     items;
   - in RESTORE_WORK, every lookup of that name gets `"void": true` (`session._facts` ignores void lookups) and its ids
     leave `verified`;
   - in `fetched`, the name is deleted;
   - in a clear check, `HALT.json check.copies` becomes null.
3. It counts the slip in the loop it belongs to, which is D3's "commit step". The counters are `PENDING.slips` (one
   commit, its entry and parts), the setup-file loop's `slips`, `RESTORE_WORK.slips` (one restore) and
   `HALT.json check.slips` (one clear check). Each is written durably.
   - Three re-asks are allowed per loop (`SLIP_ASKS = 3`).
   - The fourth slip is `STOP SLIP_LIMIT HANDBACK C`. It is local sticky, and HALT.json `detail` is
     `{"name": <name>, "last": <code>}`. In a clear check the fourth slip ends the check instead (§2.4.3).
4. It prints the next block with the line `REFUSED <code> <name>` right after the header, and exits 4. That block is
   the FIND block for the name, plus every other name of the group that is still unconfirmed. It has no UPLOAD line
   (SD-60).

Only these three observations are slips. A slip never changes STATE.json and never commits anything. One function does
the loop counting (`savepoint.slip(loop, name, code)`). The session glue (`cli.session_slip(env, name, code)`) uses the
same shape in RESTORE_WORK.

Example: an id with one wrong character, copied by hand.
```
CPSV series=Q1 head=000124 kit=0a1b2c3d4e5f at=000124-0010-5e01aa mode=qualification state=SAVE
REFUSED DOWNLOAD_MISSING CPSJ_Q1_000125.tgz
FIND CPS/qualification NAME CPSJ_Q1_000125.tgz
DO: ATTEST bash /home/agent/cps/vm.sh found --at 000124-0010-5e01aa --raw FILE
```

#### 2.2.2 What a FORK is

Only downloaded bytes decide (D3a). `FORK` is one of:
- a copy downloaded with exactly its attested size, whose bytes differ from the expected bytes. The expected bytes are
  our file in a commit or setup loop, a head part's sha256, the moved PENDING's sha256 in a clearing restore (§2.4.4),
  or the RESTORE's bytes in RECHECK;
- two downloaded copies of the head N that differ from each other.

For N-1 the same case is `LINK_MISMATCH`.

Before a FORK or LINK_MISMATCH block is printed, `cli.stop_block` moves the downloaded copies of that name
(`BASE/inbox/verify/<name>.<k>`, `BASE/inbox/journal/<name>.<k>`) into `BASE/outbox/v2/fork_<utc14>/`. They are never
deleted (S-03).

**Reading of D3a (SD-38).** D3a's case "a size that differs from our bytes" is decided by the download. A typed size
that does not match the real file shows as a download of another size, which is a slip and a re-FIND. A real copy of
another size downloads at that size with other bytes, which is a FORK, and its bytes are kept. D3a's three cases thus
all re-FIND, and a real fork is never mistaken for a slip. The cost is one DOWNLOAD for a size typo.

#### 2.2.3 Refusals are counted (D3b)

**What is counted.** Every REFUSED code except HELPER_BUSY, JOB_BUSY and the three slip codes. Examples are the
argument and value checks of `found` and `answer`, `STALE_AT`, `COMMAND_NOT_EXPECTED`, `RAW_INVALID`,
`FINAL_MESSAGE_INVALID`, `TOOLS_FILE_INVALID`, `TRANSCRIPT_*`, `COPY_*`, `INPUTS_INVALID`, `INPUTS_CHANGED` and
`UTC_OUT_OF_WINDOW`. Every usage error (exit 2) is counted too.

**What happens.**
1. BLOCK.json `refused` is incremented and written durably, before anything is printed.
2. The block is reprinted without its UPLOAD lines (SD-60), after the line `REFUSED <code>[ <key or name or detail>]`,
   with exit 4. A usage error keeps exit 2 and prints no REFUSED line.
3. The fourth consecutive refusal of one block is `STOP SLIP_LIMIT HANDBACK C`, with HALT.json `detail` set to
   `{"last": <code>}`. In a clear check it ends the check instead (§2.4.3).

**When the count resets.** A newly rendered block starts at `refused = 0`. A reprint of the same template at the same
head keeps the count. HELPER_BUSY is never counted: it means another command holds the lock, which is not a slip. The
test is vio `t_d3_refused_count_resets_per_block`: three refusals on one block, a new block, three more, and no
SLIP_LIMIT (W68).

**Reprints never upload (SD-60).** Every reprint of a block drops its UPLOAD lines: the counted refusal's reprint, the
`go` reprint in `go_checks` of a block that expects `found` or `answer`, and the slip's re-FIND. A reprint keeps the
FIND lines, the ATTEST line and the `--at`. `--refused` stays allowed for the names in `BLOCK.expect.uploaded`. A name
that is really absent is uploaded again only by the loop's own next attempt, as today. FakeDot asserts that no UPLOAD
line follows a REFUSED line (vio `t_op02_reprint_has_no_upload_lines`: a RAW_INVALID refusal on a commit block with
UPLOAD lines prints none, and FakeDrive shows one upload per name; W86).

#### 2.2.4 The final message is data (D3c)

**Supersedes** the `attest/final_message.txt` row of r2 §3.9, the final message under "Files the Dot writes" in r2
§6.3, and the FINAL_MESSAGE_INVALID text of r2 §13.1.

**The file.** Every AI attestation needs `BASE/attest/final_message.txt`: S, G, V revision 1 and every V continuation.
It holds the conversation's final message, verbatim.

**The check** (SD-65). It is read as bytes:
- it must exist as a regular file, else `REFUSED FINAL_MESSAGE_INVALID missing` (counted);
- it must be valid UTF-8, else `REFUSED FINAL_MESSAGE_INVALID utf8` (counted);
- 0 bytes is accepted: a conversation that stopped or failed without a final message gives an empty file. Runner R13
  accepts any str, `''` included (`cps_job.py` `generation_record_problems`);
- over `max_ai_output_bytes` it is `STOP AI_OUTPUT_TOO_LARGE`, the existing code of an over-size output folder, never a
  counted refusal: the Dot cannot shorten a message.

No character is refused: braces, angle brackets, quotes and newlines are all kept. The doc-sample comparison is not
applied to this file (SD-54).

**Where it is stored.** It is always the member `attest/final_message.txt` of the AI entry, whatever its size (this
plan's reading of D3c's "file member"). The body records `final_message_sha256` for every role. It is never inline in
an entry body and never printed. The G generation record's `final_message` is the decoded text, because runner R13
needs a str. DROP_ATTEST removes the file after the commit, as today, and a clear or a damaged cache moves it away
(§2.4.3, SD-68), so a message is never taken from an earlier conversation.

#### 2.2.5 Everyday INPUTS_CHANGED is bounded (D3d)

**Supersedes** the special render in `cli.start_chain` and FakeDot's silent `restore_inputs`.

**What the helper does.** At a (re-)prepare from committed inputs (r2 §11.2 row 1), a missing or changed input prints
the WORK block (`DO: RUN bash /home/agent/cps/vm.sh go`) with `REFUSED INPUTS_CHANGED`. This goes through the counted
refusal of §2.2.3, so the fourth one is `STOP SLIP_LIMIT HANDBACK C`.

**What the Dot does.** README §2.3 gives the action. Before it answers `case=`, the Dot keeps the exact text of
JOB.json and JOB_TITLE.json and the place of the user's workbook in its notes, so it can put the same three files back
after a reset. If it cannot, it tells the owner and runs `go` until the helper prints `STOP SLIP_LIMIT HANDBACK C`: the
end state is always a helper STOP, never the Dot's own judgement.

**After the STOP.** INPUTS_CHANGED after a reset arises only after the RESTORE that set the one re-prepare (fold e41).
So a maintainer clear of that SLIP_LIMIT runs a restore that classifies C8b with `reprepare` false: it **abandons the
everyday job** (O49's "prepared again once", O60). A reset abandons it the same way. A new job starts only at the
user's request. OQ-22 stays open for the owner. The rs scenario `E_inputs_lost_after_reset_bounded` runs to the clear
and asserts the abandon, and cm `test_gap13_c8b_after_second_restore_abandons` checks the C8b row (W96).

#### 2.2.6 O7 restated

**Supersedes** r2 §0 "Refused means exit 4 and no state change", and oracle O7 (r2 §14.3).

Exit 4 means: the last answer was not used; do the block that follows the REFUSED line. STATE.json and the journal are
unchanged. A slip changes only the slipped name's record and its loop's count (§2.2.1). A counted refusal changes only
BLOCK.json `refused`. FakeDot's O7 assertion checks exactly this.

### 2.3 D4: `found --raw`

**Supersedes** r2 §6.2 item 2 and the `found` forms of §X.6.2. The LIST answer form is deleted (§2.13).

**Grammar.** Exactly one of the two forms. `--refused` is now an option that takes the file name.
```
found --at <at> --raw <abs file> [--refused <name> ...]
found --at <at> (--name <name> (--file <id>:<size> [--file <id>:<size> ...] | --none))+ [--refused <name> ...]
```
- `--refused <name>` is allowed only for a name in `BLOCK.expect.uploaded`, else `FOUND_SYNTAX`. It means what §X.5.6
  says.
- The printed ATTEST line is `DO: ATTEST bash /home/agent/cps/vm.sh found --at <at> --raw FILE`, plus
  ` [--refused NAME]` when the block has UPLOAD lines (SD-48). The manual form is documented in the README only.

**Parsing the raw file** (`drive.parse_raw(doc, names, id_re)`: pure, called by `cli.do_found`):
- **The file.** It must be an absolute path to a regular file (not a link), else `RAW_INVALID missing`. It must be at
  most 1,048,576 bytes (`RAW_MAX_BYTES`) and strict JSON (the reused `sjson`), else `RAW_INVALID json`. `names` is
  `BLOCK.expect.names`, the block's FIND names in printed order.
- **Consumed (SD-61).** When `found --raw F` is accepted, the helper moves F to `BASE/outbox/v2/raw/<at>.json`. A path
  used again is then missing and is refused as `RAW_INVALID missing` (counted). A stale file from an earlier block can
  therefore never attest an absence.
- **Elements.** When the block has one FIND line and `doc` is a dict, `elements = [doc]`. Otherwise `doc` must be a
  list with one element per FIND line (`RAW_INVALID count`).
- **Objects.** An element is one returned object, or a list of returned objects (the pages of one search, in order).
  - An object is either the platform envelope `{"content", "structuredContent", "isError"}`, in which case `isError`
    must not be true (`RAW_INVALID error`), or the structuredContent alone (a dict without `content`).
  - The structuredContent holds exactly one of `results` (exact-name search) and `files` (folder listing), as a list
    (`RAW_INVALID shape`).
  - The last object of an element carries no next-page token, meaning no non-empty value under a key whose lowercase
    form ends in `page_token` or `pagetoken` (`RAW_INVALID pages`).
- **Copies, by title (SD-61).** The copies of a name are the entries of **any** element whose `title` equals that name
  exactly. Elements are not matched to names by position, so two results saved in swapped order still give the right
  copies. Entries with `file_or_folder == "folder"` and other titles are ignored. Each copy needs:
  - `id`: a str matching the config's `drive_id_re`;
  - `size`: an int >= 1 that is not a bool, or a str matching `[1-9][0-9]{0,11}`;
  - `created_at` (search) or `created_time` (listing): matching
    `[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z`.

  A copy that fails any of these is `RAW_INVALID entry`. The created time is only checked for shape. It is never stored
  or compared, so §X.9 rule 3 stands: the helper never uses a Drive time (SD-50). One id given twice with one size is
  one copy; one id with two sizes is `RAW_INVALID duplicate`.
- **Absence.** A name with no copy is absent only when every element of the file is an exact-name search (`results`).
  If any element is in the `files` form, a name with no copy is `RAW_INVALID listing` (SD-49), because a listing can be
  cut at its `top_k` without saying so.
- **The parent filter (only after G-11).** If G-4 shows that an exact-name search returns copies from another folder,
  the parser also ignores an entry whose `parent_ids` does not contain the folder id that the kit config pins for that
  folder (one comparison), and the manual form lists only copies in the folder. Until then nothing of this is built.
- **Refusals.** Malformed or unrecognised content is `REFUSED RAW_INVALID <detail>`, counted (§2.2.3). The details are
  `missing`, `json`, `count`, `shape`, `pages`, `error`, `entry`, `duplicate` and `listing`; README §3.2 gives the
  Dot one action for each. Nothing is guessed.
- **One internal answer.** Both forms produce the same answer, `{name: [[id, size], ...]}`. An attested copy is
  `[id, size]`; a confirmed copy stays `[id, local md5, size]`. Every later rule is shared.

**M007 confirms the envelope (D16, F4).** The Dot saved a real search result by serializing the returned object with
`JSON.stringify` in its orchestration code and writing the text to the VM file with a Python heredoc. The file holds
exactly the M004 envelope, and each result has the keys `url`, `title`, `id`, `mime_type`, `size` (a decimal string),
`file_or_folder`, `created_at`, `updated_at`, `viewedByMeTime`, `display_title`, `display_url`, `parent_ids` and
`shared`. An empty search is `{"results": []}`. The rules above already take both; §2.16.2 changes the test fixtures
only.

Example raw file for a block with two FIND lines (the entries are shortened; the platform adds more keys, which are
ignored):
```
[{"content": [{"type": "text", "text": "Action completed."}], "isError": false,
  "structuredContent": {"results": [{"title": "CPSJ_Q1_000125_PNG01.part", "id": "fakedriveid00000000000000000001",
                                     "size": "1000000", "created_at": "2026-11-10T01:16:17.040Z", "file_or_folder": "file"}]}},
 {"content": [{"type": "text", "text": "Action completed."}], "isError": false,
  "structuredContent": {"results": []}}]
```

### 2.4 D5: one clear mechanism for every stop

**Supersedes** the last paragraph of r2 §2.5 ("ends in PLACE_TARGET_NOT_EMPTY"), the second bullet of r2 §13.5, the
same-boot sentence of r2 §13.5, SD-7, and the `sticky_halt` docstring ("not built"). It also replaces r3's restart
rule and its session phase CLEAR, which were never built.

**One mechanism.** A stopped helper that is given a new kit first checks that kit against its stop, before anything
moves. Only a kit that names exactly this stop and changes only settings is accepted. Then the stop and the cache move
aside, and the helper runs the restore of a reset in the same boot. That restore accepts the job folders already on
the VM and records the clear in its commit.

#### 2.4.1 HALT.json

The schema `cps.vm2-halt.v1` is
`{schema, series, code, head_seq, kit_sha256, tried, check, detail, created_utc, self_sha256}`.

- **Which STOPs write it (SD-56).** Every STOP with HANDBACK C except RELEASE_GATE_OPEN. This includes the
  `HALTED_<code>` STOP that the plan or the session prints for a committed HALT. Not written: FINAL (B), UPLOAD_REFUSED
  and WAIT_APPROVAL (A), RELEASE_GATE_OPEN, and the SESSION_* codes of `session_start.sh`.
- **The fields.**
  - `code` is the printed code.
  - `head_seq` is the seq a clear names. For `HALTED_<code>` it is the halt seq of the journal's state
    (`STATE.state.halt.seq`, else the verified head's `state.halt.seq`). Otherwise it is `STATE.head.seq` of a valid
    cache, else the head this session verified (`RESTORE_WORK.head.entry.seq`), else 0.
  - `kit_sha256` is the journal's kit (SD-57): `STATE.state.kit_sha256`, else the verified head's `state.kit_sha256`,
    else the kit this session read (`RESTORE_WORK.kit.sha256`; a fresh series has no journal kit), else null. It is
    null only when the stop came before the session read a kit or verified a head (SETUP_FAILED, for example).
  - `series` is the series in use, or null before a kit was read.
  - `tried` lists the 12-hex kits that never start a clear check. At creation it holds the first 12 hex of
    `kit_sha256`, of the kit in use (`STATE.kit_sha256`, else `RESTORE_WORK.kit.sha256`) and of the HINT.json kit at
    that moment. So neither the halted kit nor a HINT.json written before the stop ever starts a check. Each refused
    candidate is added.
  - `check` is null, or the clear check in progress: `{kit12, copies, slips}`.
- **The cache stays valid.** A stop never invalidates a valid cache. The STOP block's header shows HALT.json's
  `head_seq` and the first 12 hex of its `kit_sha256` (`none` when null): the values a clear names (§2.4.2, OPX-07,
  SD-68). `stop_block` also writes `halt_local: {code, head_seq}` into STATE.json and RESTORE_WORK when they exist
  (SD-64).
- **A damaged HALT.json** (present, not valid) is never ignored: `clear_check` replaces it through
  `stop_block('UNCLASSIFIED')`, which moves the old file as below. So a clear check always reads a valid HALT.json.
- **An earlier stop.** When a new stop comes while HALT.json exists, the old file first moves to
  `outbox/v2/halt_<utc14>.json`.
- **A dead stage** (`foreground_check`). A FOREGROUND.json of this boot is moved to `outbox/v2/dead_<utc14>.json` (a
  self-test at attempt 1 is the exception). Then `STOP FOREGROUND_DIED`, or SELFTEST_DIED, is written to HALT.json.
- **BLOCK.json against STATE** (OPX-07, the INT-R2-02 probe). In `load_cache`:
  - a BLOCK.json whose `head_seq` is **below** the valid STATE's head moves alone to
    `outbox/v2/invalid_<utc14>/BLOCK.json`, and STATE, PENDING and RESTORE_WORK stay valid. This is a stage run right
    after a commit. The next `found` or `answer` is `STALE_AT`; `go` prints a fresh block;
  - a BLOCK.json **above** STATE's head invalidates the whole cache, as at 2015773. STATE.json was rolled back or
    replaced, and keeping it could commit a second entry at a seq already on Drive;
  - at equal seq BLOCK.json stays valid, as at 2015773.
- **HALT.json removed out of procedure** (SD-64). In `load_cache`, a STATE.json or RESTORE_WORK that holds `halt_local`
  while no HALT.json exists is invalid. The cache files move to `invalid_<utc14>/`, and the next `go` restores from
  Drive. The journal then shows a RESTORE in the same boot as the entry before it, which the audit lists for the O52
  sheet (§2.7).

#### 2.4.2 The clear request (O59)

The maintainer publishes `CPS/setup/SESSION_KIT_<k12'>.zip`. It is the kit that HALT.json `kit_sha256` names, with only
`VM_HELPER_CONFIG.json` changed: the changed keys are within `CHANGEABLE_KEYS`, `doc_samples` are only added, and
`clear` is `{"series": S, "seq": <HALT.json head_seq>, "code": <HALT.json code without HALTED_>}`. For a committed
HALT, `seq` and `code` are the HALT entry's, as r2 §13.5 says.

The maintainer never sees HALT.json. The Dot reports the STOP line and its last CPSV line, whose `head` and `kit` are
HALT.json's (§2.4.1). With `kit=none` no kit was read before the stop: the maintainer builds the clear kit from the kit
of the journal's head on Drive, or from the release kit on a fresh series, and the clearing restore's KIT_ACCEPT checks
it (§2.4.4).

The message to the Dot gives one exact line,
`bash ~/cps/repo/deploy/vm2/session_start.sh --commit <C> --hint <seq6> --kit <k12'>`, and then `go`.

#### 2.4.3 The clear check (`cli.clear_check`, which replaces `sticky_halt`)

**Order in `run_command`.** First `load_cache`, `foreground_check`, `cleanup_leftovers` and the kit adoption of an
intake in progress, as today. Then `clear_check`. Then, only when no HALT.json exists, the post resume (S-04). Then
the command. A stop raised by a post action can therefore be cleared in the same boot.

```
H = HALT.json; absent: return; present but not valid: stop_block('UNCLASSIFIED') (§2.4.1)
k = the HINT.json kit (12 hex), or None
if command == 'found' and BLOCK is the check's FIND block:
    record the copies in H.check.copies (the found rules of §2.3), then take the next step below
elif command != 'go' or k is None or k in H.tried:
    print H's STOP block                                                                            (exit 3)
the next step for k:
    H.check null, or for another kit:  H.check = {kit12: k, copies: null, slips: 0}
                                       print FIND CPS/setup NAME SESSION_KIT_<k>.zip, state KIT      (exit 0)
    H.check.copies null:               print that FIND block again (a go before found)              (exit 0)
    H.check.copies empty:              H.check = null; print H's STOP; k is not added to tried      (exit 3)
    no DOWNLOAD block printed yet:     print DOWNLOAD of copy 1 TO BASE/outbox/v2/clear/SESSION_KIT_<k>.zip (exit 0)
    a go after that DOWNLOAD block:    the slip rule (§2.2.1) with H.check as its loop; with no slip,
                                       why = session.clear_verdict(H, candidate, kits)
        why is not None:               H.tried += [k]; H.check = null; print H's STOP               (exit 3)
        why is None:                   the clear (below); the session then runs in this same command
```
H.check is reset only when it is null or names another kit, so a re-FIND after a slip keeps its `slips`.

- `kits` are the kit dicts the helper holds: `STATE.kit`, `RESTORE_WORK.kit` and `RESTORE_WORK.head_kit`.
- **Bounds.** The check's slips and counted refusals follow §2.2, but the fourth one ends the check: k goes into
  `tried`, `H.check` becomes null and H's STOP prints. H's code never changes during a check. A kit that is not on
  Drive yet is not marked tried, so the Dot's `go` after the maintainer's next message checks it again.
- **The verdict.** `session.clear_verdict(H, cand, kits)` is pure. It returns None or the reason:
  - `sha`: the candidate's sha256 does not start with k;
  - `members`: RELEASE.json or VM_HELPER_CONFIG.json is missing, or the config is not valid;
  - `clear`: `clear_ok(cand.config.clear, H.series or cand.config.series, H.head_seq, <H.code without HALTED_>)`
    fails. `clear_ok(clear, series, seq, code)` is `clear == {"series": series, "seq": seq, "code": code}`. It is the
    one comparison used by classify C2, plan row 3, this check and the audit;
  - `config`: a kit K in `kits` has `K.sha256 == H.kit_sha256`, and `config_only_ok(K, cand)` is not None.
    `config_only_ok(from_kit, to_kit)` is the config-only branch of `kit_change`, extracted: the member lists differ
    only at VM_HELPER_CONFIG.json, the changed keys are within CHANGEABLE_KEYS, and doc_samples are only added.
    Otherwise it returns `CONFIG_CHANGE_NOT_ALLOWED`. When no kit in `kits` is the halted one, this test is left to
    the clearing restore's KIT_ACCEPT (§2.4.4), which compares against the head's kit. That happens only when the stop
    came before the session held the halted kit: before any kit was read, or in a restore that took a kit change and
    had not reached KIT_ACCEPT. No STATE.json exists then, so a kit that KIT_ACCEPT refuses after the move (a new
    `STOP CONFIG_CHANGE_NOT_ALLOWED`) costs no valid cache.
- **The clear**, when the verdict is None:
  1. `cli.invalidate(env, 'cleared_')` moves HALT.json, STATE.json, PENDING.json, BLOCK.json, RESTORE_WORK.json, every
     file under `BASE/attest/` and every entry of `BASE/inbox/` except the boot mark `inbox/.boot` into
     `outbox/v2/cleared_<utc14>/`. Stale final messages, tool lists, raw files and downloads of the stopped attempt
     thus never reach the restore. The boot mark stays: without it `cleanup_leftovers` would empty the whole inbox at
     the next command, the kit of step 2 included. `load_cache` uses the same helper with the prefix `invalid_`, which
     moves the same files except HALT.json, so a stop outlives a damaged cache and a same-boot restore never sees the
     files of the attempt before it (SD-68). `foreground_check` still moves another boot's FOREGROUND.json alone, as
     today.
  2. The candidate moves to `BASE/inbox/kit/SESSION_KIT_<k>.zip`, so the session's KIT phase takes it without a second
     download.
  3. A new RESTORE_WORK gets the hint from HINT.json, the `operator` of the old STATE or RESTORE_WORK (null when
     neither has one; OPERATOR then asks), `cleared_local` = H's `{code, head_seq, kit_sha256}` when H is a local stop
     (a code without `HALTED_`), else null, and `moved_pending` = `{seq, name, sha256, uploaded}` of the moved PENDING
     (`uploaded` lists the names uploaded at least once), else null.
  4. The session runs from the top, in the same `go`, as after a reset. No phase is blocked, because HALT.json is
     gone. A stop in this restore is an ordinary new stop.
- `answer`, and `found` for any other block, print H's STOP. A refused candidate leaves STATE.json, PENDING.json and
  RESTORE_WORK byte-identical; HALT.json changes only in `tried` and `check`.
- The same-boot restore of r2 §13.5 that commits nothing is not built. A clear always restores.

#### 2.4.4 The clearing restore

The session has no CLEAR phase. A clearing restore is an ordinary restore with four rules that matter here. The first
two apply only when RESTORE_WORK carries `cleared_local` or `moved_pending`; the last two apply to every restore and
matter most in the same boot:
- **KIT_ACCEPT (O59).** With `cleared_local` set, a kit change must be config-only, else
  `STOP CONFIG_CHANGE_NOT_ALLOWED`; a code that `kit_change` returns stops as today. The comparison is with the head's
  kit, which is HALT.json's kit unless the journal moved after the stop (a landed copy of the moved PENDING that took a
  kit change, or another writer). Then the clear kit must also be config-only against the kit the journal moved to,
  and the audit's rule 3 (§2.7) still checks the change from the halted kit. A committed HALT's C2 path already
  requires `kit_config_only`.
- **The head (GAP-04).** With `moved_pending` set, when the head N that the search found is `moved_pending.seq`, every
  downloaded copy of N must have `moved_pending.sha256`, else `FORK` (the copies go to `fork_<utc14>/`). This holds
  whether or not our own copy landed. The moved PENDING's parts need no rule: savepoint uploads the parts only after
  its entry is confirmed (`savepoint._group`), so they exist only when that entry is the head, and rule V checks them
  against that entry's recorded sha256.
- **RESOLVE_PLACE (GAP-02).** `files_found` is computed before `settle` moves anything (§2.4.6).
- **RECHECK.** It runs on every qualification and drill restore (SD-59) and, in an everyday series, when
  `moved_pending.uploaded` is not empty.

**The commit.** The RESTORE, or GENESIS on a fresh series, records `cleared_local` (r2 §3.4). The exception is a
RESTORE while HALTED: there the CLEAR that follows records the clear (§2.4.5), and the RESTORE carries null (SD-57).
`cli.build_state` takes `cleared_local` from RESTORE_WORK, because the old cache was moved away, and `cli.commit`
resets it after that commit, as today. The RESTORE takes the new kit (its `kit_change` is the config-only change).

#### 2.4.5 A committed HALT, in the same boot or after a reset (SD-51)

HALT.json holds the `HALTED_<code>` STOP too, so the clear check of §2.4.3 also starts the clear of a committed HALT
in the same boot. After a reset the session reaches the same STOP from the journal (C2) and writes HALT.json, so the
next clear works the same way. The session runs with the hinted kit:
1. KIT_ACCEPT computes `kit_change` against the head's kit.
2. Classify C2 with `clear_ok` commits a RESTORE, with the open-role resolutions (INT-14).
3. **That RESTORE keeps the halted kit.** Its body has `kit_change: null`, its entry's `cleared_local` is null, and
   its entry and body `kit_sha256` are `STATE.kit_sha256` (`session._after_classify` for C2 with a clear;
   `cli.session_commit` sets the entry kit from the body).
4. Plan row 3 then commits CLEAR. The CLEAR carries the kit change from the halted kit to the new kit, and it is the
   entry that takes the new kit (T59 with from != to, e59).

At 2015773 that RESTORE took the new kit, which broke the next step in two ways:
- the CLEAR glue stopped with `KIT_NOT_VERIFIED`, because `kit_change` was asked about a head kit that was no longer
  the state's;
- the only CLEAR the fold accepted was one from the new kit to itself, which MAINT-3 forbids.

The test is ct `test_session_c2_clear_restore_keeps_kit_then_clear_takes_it`, together with rs
`D_clear_committed_halt_same_boot`. The mutants are W51 and W91.

#### 2.4.6 Same-boot placement (`place.settle`)

**Supersedes** the "empty targets" of r2 §8.5.1, and the PLACE_TARGET_NOT_EMPTY of §8.5.1 steps 1-2 and §7.7.

Placement always builds into its staging folder. Then `place.settle(staged, target, aside)` runs under JobLock of the
target:
- **Target absent.** The staged tree is renamed into place, as today.
- **Target present, with a strict walk equal to the staged tree's.** The walk compares, for every entry, its path,
  type, mode, size and sha256. The target is kept and the staging is removed.
- **Otherwise.** The target moves to `outbox/v2/aside_<utc14>/<n>/`, where it is never deleted, and the staged tree is
  renamed into place.

`place_job`, `place_ledger` and `v1mod.place_frozen` use `settle`. `PLACE_TARGET_NOT_EMPTY` stays only for GENESIS (a
hint, or BASE/ledger present) and for a snapshot whose AI output folder is not empty.

**The open role (GAP-02).** When the placement serves RESOLVE_PLACE, `worker.do_place` walks the open role's output
folder in the existing target before `settle`, and in the placed tree after it. `files_found` is true when either holds
a file outside the snapshot. The RESTORE's `placed` item gets `aside`: the aside path, or null. Without this order a
same-boot clear would move the conversation's files aside and then find none.

The test vio `t_d5_placement_accepts_equal_or_moves_aside` covers an equal target (kept), a same-size file with other
bytes and a mode change (both moved aside), and an absent target (W03, W67).

#### 2.4.7 Every local sticky code, after a reset or a same-boot clear

Every code in `CODES_STOP` and `CODES_HALT` is listed below exactly once. A clear in the same boot runs the restore of
a reset while the VM's files are still present (§2.4.3-2.4.6). After a real reset, HALT.json and the cache are gone,
and the same restore runs.

**Commit loop.** Codes: FORK, SLIP_LIMIT, UPLOAD_FAILED, UPLOAD_TOO_LARGE, ENTRY_TOO_LARGE, PART_TOO_LARGE,
REBASE_PART_APPEARED, INTERNAL_PENDING_EXISTS.
- What happens: the unconfirmed entry was never shown. The head search finds the last confirmed entry, or our entry
  if a copy landed; then it is verified by download and its state binds. After a same-boot clear the moved PENDING's
  bytes are known (§2.4.4): any copy at that seq with other bytes is FORK again, whether or not our copy landed too,
  and RECHECK runs. After a reset they are not known: a lone foreign copy at N+1 that is a valid entry then becomes the
  head, as our own copy would. A second writer that keeps writing is found by the RECHECK, and two copies of one seq by
  the head search (FORK) or the audit's duplicate check (r2 §12.2).
- Why it is safe: under O54, nothing shown depends on an unconfirmed entry, the evidence of a fork is on Drive and in
  `fork_<utc14>/`, and FORK recurs until the owner removes the foreign copy (README §6).

**Journal, Drive and kit (deterministic).** Codes: ARCHIVE_MANIFEST_MISMATCH, ARCHIVE_MEMBER_SHA_MISMATCH,
ARCHIVE_UNREADABLE, ARCHIVE_UNSAFE_MEMBER, CHAIN_INVALID, CONFIG_CHANGE_NOT_ALLOWED, GATES_CHANGED, HEAD_CORRUPT,
HEAD_UNSTABLE, HELPER_UNKNOWN, HINT_AHEAD, HOME_CHANGED, KIT_CHANGE_WITH_RUN_IN_FLIGHT, KIT_NOT_IN_MANIFEST,
KIT_NOT_REBUILT, KIT_NOT_VERIFIED, KIT_PARTS_NOT_IN_MANIFEST, KIT_SUMS_MISMATCH, LINK_MISMATCH,
QUALIFICATION_DIVERGED_RESTART_CONFLICT, QUALIFICATION_SERIES_EXISTS, REBASE_CONFLICT, REBASE_LIMIT,
RELEASE_NOT_ACCEPTED, SCHEMA_INVALID, STATE_SHA_MISMATCH, UNCLASSIFIED.
- What happens: the session or the plan derives the same verdict from the same Drive, journal and kit evidence. It
  stops again until the evidence or the kit changes.
- Why it is safe: the session commits nothing before its verdict, and the plan's stops are functions of the journal.
  UNCLASSIFIED also marks a damaged HALT.json (§2.4.1); that cause is local, so a reset or a clear simply restores.

**VM environment.** Codes: CLOCK_BEHIND, CONFIG_INVALID, DISK_FULL, INTERNAL_EMPTY_OUTPUT, LAYOUT_BASE,
LAYOUT_HELPER_NOT_IN_BASE_REPO, LAYOUT_HELPER_NOT_PINNED, LAYOUT_HOME, LAYOUT_PATH, LAYOUT_RELEASE_MISMATCH,
LAYOUT_RUNNER_NOT_PINNED, LEDGER_MISSING, LEDGER_NO_IDENTITY, SELFTEST_DIED, SELFTEST_FAILED, SETUP_FAILED,
WRITE_FAILED, WRITE_READBACK_MISMATCH.
- What happens: after a reset the VM is new and the condition is checked again from scratch. A clear re-runs the check
  on this VM. On a fresh VM a SETUP_FAILED HALT.json has no kit, and `tried` holds the hinted release kit, so the
  release kit never starts a check: only a kit whose `clear` names this stop does.
- Why it is safe: no result depends on the VM's local state, and the PASS is per fingerprint (O47).

**Stage and glue.** Codes: FOREGROUND_DIED, INTERNAL_CHAIN_TOO_LONG, INTERNAL_ILLEGAL_TRANSITION, INTERNAL_PRINT,
INTERNAL_STEP_OVERFLOW, JOB_BUSY_TOO_LONG, PLACE_SHA_MISMATCH, PLACE_TARGET_NOT_EMPTY. This class also takes every
CODES_HALT code whose HALT entry could not be committed: AI_OUTPUT_CHANGED, AI_OUTPUT_TOO_LARGE, EVICT_FAILED,
EVICT_MISMATCH, FREEZE_INCOMPLETE, FROZEN_FOLDER_CHANGED, GENERATION_RECORD_EXISTS, PLACED_FROZEN_CHANGED,
PNG_MANIFEST_UNSAFE, POST_ACTION_FAILED, PROMPT_CHANGED, RUNNER_OUTPUT_UNPARSEABLE, RUNNER_REFUSED,
WALK_UNSUPPORTED_ENTRY.
- What happens: nothing of the stage reached Drive, since its SAVE block comes after the stage and the STOP reveals no
  result. The restore resumes from the last confirmed entry:
  - the stage re-runs unbound and logged (C8, RERUN_UNBOUND), or
  - the open role is resolved (C6). In a same-boot clear the files in its output folder force WRITTEN (O46, §2.4.6);
    after a reset the Dot's README answer decides (§2.9).

  `settle` moves aside a killed runner's leftovers in the job folder or ledger. Deterministic causes recur. A stop
  from a post action (POST_ACTION_FAILED, EVICT_FAILED, EVICT_MISMATCH, PLACED_FROZEN_CHANGED) is cleared in the same
  boot, because the clear check runs before the post resume; the clear moves STATE with its post into
  `cleared_<utc14>/`, and the restore's placement and `settle` decide what stays on the VM.
- Why it is safe: O44 and O54 cover the re-run, O46 covers an open role, and post actions are local clean-ups after a
  confirmed commit.

**An open role costs its output.** Any stop while an AI role is open, local or committed, costs that role's output
when it is cleared. This includes SLIP_LIMIT from refused answers about that conversation, and STOP
AI_OUTPUT_TOO_LARGE for an over-size final message. The clear's restore resolves the open role as a reset would (C2,
C6), and the files in its folder force WRITTEN (T47: FREEZE_LOST, or FREEZE_VISUAL_FAILED for V). A reset at that
moment costs the same.

**Not sticky** (never in HALT.json):
- FINAL (B);
- RELEASE_GATE_OPEN. A kit whose release gate is open cannot be cleared by a settings change (O59); the maintainer's
  released kit is taken in by the next session, after a reset;
- UPLOAD_REFUSED and WAIT_APPROVAL (A);
- the SESSION_* codes of `session_start.sh`: SESSION_COMMIT_MISMATCH, SESSION_GIT_ERROR, SESSION_LAYOUT,
  SESSION_NO_COMMIT, SESSION_REPO_DIRTY. The Dot runs the bootstrap again; no helper command ran.

### 2.5 D6: a pending upload approval across a reset

**Where it runs (SD-58).** There is a new session phase `APPROVAL`, right after FINGERPRINT and before HEAD, on both
paths. Every session asks it: after a reset, after a maintainer clear, and at the start of a series. Only the operator
question and the kit intake come before it. So it comes before any FIND of the head search and before every session
commit: the RESTORE, the GENESIS and the C10 HALT. It never runs with a valid cache of this boot.
```
CPSV series=Q1 head=000000 kit=0a1b2c3d4e5f at=000000-0003-5d2c11 mode=qualification state=RESTORE
DO: ATTEST bash /home/agent/cps/vm.sh answer --at 000000-0003-5d2c11 approval=APPROVAL
```

**The answer.** The pattern is `APPROVAL = none|pending`, enumerated, and `approval` joins KEY_NAMES.
- **`approval=none`** is recorded in RESTORE_WORK. The RESTORE or GENESIS body records `"approval": "none"`, and S1
  requires exactly that value (GAP-06, W74). The C10 HALT's body is the plain HALT body; the question still came first.
- **`approval=pending`** prints `DO: STOP WAIT_APPROVAL HANDBACK A`. This is exit 3; it is not sticky and not in
  HALT.json. RESTORE_WORK `approval` stays null and nothing else changes. The owner resolves the prompt, the Dot runs
  `go`, the question is asked again, and the head search then starts from nothing. An approved upload that landed is
  thus found. There are no observations to clear.

**The audit stays fail-closed.** Two sha256 values for one name are still `AUD_DUPLICATE_SEQ`; the wrong-`none`
scenario proves it (W48). AUDIT.json lists `approvals` (seq, kind and value of every RESTORE and GENESIS) and
`same_boot_restores` (every RESTORE whose `boot_id` equals the previous entry's: a same-boot clear, a damaged cache, or
a HALT.json removed out of procedure) for the owner's O52 sheet (W94).

**Residual risk (stated).** A timed-out upload (not a refused one) that lands after both absences and after the
RESTORE's own FIND is no longer caught only by the audit: the RECHECK now runs on every qualification and drill
restore (SD-59) and stops `FORK` before any later commit when the copy lands within `w_abs`. A later landing is caught
by the audit (r2 §12.2). README §3.1 makes the Dot treat an upload it cannot classify as refused.

**The scenarios.** rs `D_refuse_reset_approval_pending`: a refused upload, a reset, the approval block printed before
the first FIND, `pending`, then `FakeDrive.approve` lands the upload, `go`, `none`, and the head search finds the
landed entry. rs `D_refuse_reset_approval_wrong_none`: FakeDot answers `none` against its notes, the RESTORE takes the
seq, `FakeDrive.approve` runs after the RESTORE's RECHECK, the series runs to the end, and the audit is unclean
(AUD_DUPLICATE_SEQ). rs `D_hint_restore_late_copy_at_n1_forks_at_recheck`: a different copy lands at N+1 during the
RECHECK wait of a hint restore, and the restore stops FORK before any later commit.

### 2.6 D7: job_dir is the layout path; assemble writes only inside its root

**The fold (C).**
- `fold.layout_of(base)` is `{"base": base, "qual": base + "/qual", "jobs": base + "/jobs", "ledger": base +
  "/ledger/LEDGER.jsonl", "runtime": base + "/runtime"}`.
- `t01` requires:
  - `body.layout == layout_of(body.layout.base)`;
  - the base matches `BASE_RE = /[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*`, with no `.` or `..` segment;
  - `gates.p1_conversation_list == 'yes'` (§2.10.14).

  Otherwise it is `SCHEMA_INVALID`.
- `fold.job_dir_of(base, tag, case)` is `base/qual/<QUAL_ROOT[tag]>/<case>` for A, B, A-restart1, B-restart1, NA-A and
  NA-B, and `base/jobs/<tag[1:]>/<case>` for an E tag. `QUAL_ROOT` (plan's ROOT) moves to fold.py, and plan imports
  it.
- `_virtual` (used by T10-T13) returns None unless
  `new_run.job_dir == job_dir_of(state.genesis.base, tag, case)`. The entry then falls to T14. The worker keeps
  deriving job_dir from `Layout.job_dir`, which is the same path.
- These are pure string checks: they never touch the file system.

**The audit (M).** It refuses through its re-fold (`AUD_CHAIN_INVALID` detail T14 or SCHEMA_INVALID), and through its
ALL_FROZEN compare with its own fold (`AUD_OUTCOMES_DIFF`) when only the FINAL member is forged. Nothing else is added
there.

**`assemble` (M).**
- `--root` is required. It must be an absolute path to an existing, empty directory with `realpath(root) != "/"`.
  Otherwise the result is `REFUSED ROOT_INVALID`: exit 2, printed by `main` as VALUE_PATTERN is today, and nothing is
  written.
- **The base comes from GENESIS.** Assemble does not fold, and ALL_FROZEN.json is a member of the FINAL entry, so its
  `genesis.base` is data from Drive like any other. Assemble therefore reads the GENESIS entry (seq 1): its
  `body.layout` must be `layout_of(body.layout.base)` with a base matching `BASE_RE`, and `af.genesis.base` must equal
  that base. Otherwise every run is `Bad LAYOUT_PATH`.
- Each run's `job_dir` must equal `job_dir_of(base, tag, case)`, with tag and case from the run key. The ledger folder
  is `base + "/ledger"`. Otherwise the run is `Bad LAYOUT_PATH`.
- Before every write, `realpath` of the parent must be `realpath(root)` or start with `realpath(root) + "/"`, else
  `Bad LAYOUT_PATH`. The writes are the reused `Staging.begin`, the PNG temporary file, and the ledger folder and file.
  This confinement is the defence against a base that is hostile but self-consistent, which the string checks accept.
- ASSEMBLE.json records `root`.

**Tests (TG-06).** None of them builds a hostile series through `core_world.commit`, which folds every entry:
- ct `test_maint1_new_run_job_dir_must_be_the_layout_path`: one fold case per row T10, T11, T12 and T13 and one for the
  everyday branch of `_virtual`, each with an absolute job_dir elsewhere (`/root/.config/git`), a `..` path
  (`<base>/qual/A/../../x`), and the wrong mappings: A/case01 at `<base>/qual/B/case01`, `<base>/ledger`, and another
  run's job_dir. Each gives T14.
- mt `test_maint1_audit_refuses_hostile_new_run`: a normal series prefix, then an entry that starts a new run (rows
  T10-T13), built outside `core_world.commit`, with each hostile job_dir above. The audit is unclean with
  `AUD_CHAIN_INVALID` detail T14 at that entry. With the ct test and the assemble tests below, the fold, the audit and
  assemble each refuse a hostile job_dir (D7, CBR-2).
- mt `test_maint1_forged_all_frozen_job_dir`: a normal series, then only the FINAL entry is rebuilt with a forged
  `final/ALL_FROZEN.json` job_dir and a matching FINAL body (the fold ignores members). The audit is unclean with
  AUD_OUTCOMES_DIFF, and assemble refuses with `Bad LAYOUT_PATH` from its own check.
- mt `test_maint1_assemble_base_from_genesis`: ALL_FROZEN's `genesis.base` differs from the GENESIS entry's: `Bad
  LAYOUT_PATH`, nothing written.
- mt `test_maint1_wrong_mapping_refused`: the three wrong mappings above, forged in ALL_FROZEN: `Bad LAYOUT_PATH`.
- mt `test_maint1_self_consistent_hostile_base_confined`: a series whose base is `/root/.config`, with every layout path
  and job_dir consistent with it. The fold and the audit accept it; assemble writes only under `realpath(root)`, and a
  sentinel folder outside the root stays byte-identical.
- mt `test_maint1_symlink_after_begin_refused`: a monkeypatch hook in test_maint.py plants a symlink to an outside
  sentinel between `Staging.begin` and the first write. Assemble refuses with `Bad LAYOUT_PATH`, and the sentinel is
  unchanged.
- mt `test_maint1_assemble_root_required_empty_dedicated`: no `--root`, `/`, a non-empty root (including one that holds
  only a symlink): `REFUSED ROOT_INVALID`.

The mutants are split so that one surviving check cannot hide the removal of the other: W29a removes assemble's layout
check (killed by the forged, base and wrong-mapping tests), W29b removes the realpath confinement (killed by the
self-consistent base and the symlink tests), W30 restores the `/` default, W93 makes assemble trust `af.genesis.base`.

### 2.7 D8: the audit re-derives kit changes, CLEAR and local clears

**Supersedes** the audit's own rule set in `Audit.kit_change`, which is deleted, so that there is one rule set: the
session's.

`Audit.kit_change(doc, state_before)` runs for every RESTORE and CLEAR with a `kit_change`:
1. Both zips come from `--setup-dir` (`kit_info`). A missing zip is `AUD_KIT kit_change`, as today.
2. It computes `code, kc = session.kit_change(state_before, to_kit, from_kit)`. The kit dicts are built from the zips
   exactly as the session builds them (`sha256`, `members`, `config`, `release_sha256`). Then:
   - `kc` must equal the body's `kit_change` field by field, else `AUD_KIT_CHANGE detail recompute`;
   - a non-null `code` is `AUD_KIT_CHANGE detail <code>` (MAINT-4).
3. For a CLEAR only: `session.clear_ok(to_config.clear, series, body.halt_seq, body.code)`, else
   `AUD_KIT_CHANGE detail clear`. A CLEAR with from = to never reaches this step: the re-fold refuses it first
   (`AUD_CHAIN_INVALID` T60, because g59 requires from != to).

**Which kit_change codes the audit can see (TG-07).** The fold's S5 already refuses a wrong from kit
(KIT_NOT_VERIFIED), a non-config-only change with a run in flight, a release that is not accepted, and a config-only
change of a key outside CHANGEABLE_KEYS. Those reach the audit only as AUD_CHAIN_INVALID. The audit-only verdicts are:
- GATES_CHANGED (a kit change whose gates differ from the genesis gates);
- CONFIG_CHANGE_NOT_ALLOWED for a series change in a non-config-only change;
- CONFIG_CHANGE_NOT_ALLOWED for doc_samples removed in a config-only change.

mt `test_maint4_audit_only_kit_change_verdicts` has one real-zip case for each, and each kills W36.

**Local clears (SD-53, r4).** S1 allows a non-null `cleared_local` only on RESTORE and GENESIS (W75). For every such
entry the audit requires, else `AUD_KIT_CHANGE detail cleared_local`:
1. `clear_ok(<that entry's kit config>.clear, series, cleared_local.head_seq, cleared_local.code)`;
2. `cleared_local.kit_sha256 != <the entry's kit>`;
3. `config_only_ok(kit_info(cleared_local.kit_sha256), kit_info(<the entry's kit>))` is None, when
   `cleared_local.kit_sha256` is not null;
4. the entry's `kit_change` is null or `config_only`.

mt `test_maint3_audit_checks_cleared_local` uses real zips: a clean local clear, a kit whose `clear` names another
seq, and a cleared_local entry whose kit is a release change (rule 3 and rule 4). Each unclean case is detail
`cleared_local` (W55).

**The fold (C).** T59 also requires `from_kit_sha256 != to_kit_sha256` (MAINT-3). SD-51 (§2.4.5) makes this compatible
with the C2 path.

**Tests** use real kit zips, built by `fakes.zip_kit` (read-only use) or by helpers inside test_maint.py.

### 2.8 D9: O63, the helper layer

The helper layer works for either owner choice of the prompt layer (gate G-2). The helper cannot change the prompts.

**The kit.**
- It carries the member `TOOL_INVENTORY.txt` and the config key `tool_inventory_sha256` (hex64, not changeable).
- In `ph_config`, the member must exist, its sha256 must equal the key, and `names.tool_list(raw)` must accept it.
  Otherwise `STOP CONFIG_INVALID` (vio `t_maint2_inventory_sha_checked`, W71).
- `tool_list(raw) -> [str] | None` accepts UTF-8 that ends with a newline: 1 to 2,000 lines (`MAX_TOOL_LINES`), each
  1 to 200 characters, with no control character, no leading or trailing space, and no duplicates.

**The answer.** The pattern is `TOOLS = inventory|file:/[A-Za-z0-9._/-]{1,240}`.
- `tools=inventory` means the conversation was created the documented way (README §3), so its tools are the
  platform's default set that the kit lists. The list is BASE/runtime/TOOL_INVENTORY.txt, with its sha256 re-checked
  against the config.
- `tools=file:<abs path>` names a regular file (not a link) that the Dot saved under `BASE/attest/`, accepted by
  `tool_list`. Otherwise `REFUSED TOOLS_FILE_INVALID`, counted (vio `t_maint2_tools_file_link_refused`, W72).
- `tools=none` no longer matches (`VALUE_PATTERN tools`; M006).

**Where it is asked.**

| conversation | end keys |
|---|---|
| G | as today, with the new pattern |
| S | `ended=YES conversation=CONV prompt_pasted=YES tools=TOOLS` |
| V revision 1 | `ended=YES conversation=CONV tools=TOOLS` |
| V continuation | `ended=YES` only (it is the same conversation) |

Every AI attestation needs the final message file (§2.2.4).

**The AI entry.**
- The list's bytes become the member `attest/tools.txt`.
- `attested.tools_present` is `{"source": "inventory" | "file", "sha256": <sha256 of those bytes>}`, for S, G and V
  revision 1. G's `attested.tools` list is replaced by `tools_present`.
- S1 (`entry.validate_body`) checks the shape of `tools_present` for every AI body with `revision == 1`.
- The O52 sheet row of each AI conversation shows its `tools_present.sha256`.

**The generation record** (`worker.generation_record`).
- `tools_enabled` holds the lines of the G entry's `attest/tools.txt`, read like the final message member.
- `notes` is `O63_NOTE % <that sha256>`, where the sentence pinned in `core/names.py` is:
  `O63: generator isolation by instruction only, not enforced or audited; tools present: %s; any tools-used statement is in final_message.`
  Here `%s` is the 64-hex sha256.
- Runner R13 accepts both fields: `GEN_OPTIONAL` includes `notes`, and `tools_enabled` is a list of str whose length
  it records.

**The README.** The Dot never sends a follow-up message and never edits a final message. The tools answer is described
in §3.

**The audit (M).**
- For every AI entry with `revision == 1`, it checks three things: `attested.tools_present` is well formed; a member
  `attest/tools.txt` has a payload sha256 equal to it; and a member `attest/final_message.txt` exists.
- For every FROZEN entry of a run whose G role was consumed, the member `job/run/GENERATION_RECORD.json` (added to
  KEEP) must be tied to the G entry it consumed (GAP-10), found through the audit's fold
  (`runs[run].roles[G<k>].archives[-1].seq`):
  - `tools_enabled` equals the lines of that G entry's `attest/tools.txt`;
  - `notes` equals `O63_NOTE % <that entry's tools_present.sha256>`;
  - the sha256 of `final_message` (UTF-8) equals that entry's `final_message_sha256`.
- A miss in any of these goes into `"o63": {"checked": n, "missing": [entry names]}` of AUDIT.json. This does not make
  the audit unclean; score_check refuses it (mt `test_gap10_generation_record_tied_to_g_entry`, W83).

**score_check (M).**
- `build` refuses `O63_ATTESTATION_MISSING`, naming the entries, while `audit.o63.missing` is not empty.
- SCORE_PLAN.json gets `isolation_statement`, set to `O63_REPORT` (pinned in `core/names.py`), and `build` prints it:
  `Isolation of the generator, scope-reader and visual-reviewer conversations was by instruction only (owner decision O63): neither enforced nor audited. The tools present in each conversation are recorded in its AI entry and, for generators, in GENERATION_RECORD.json.`

### 2.9 D10: the restore outcome (spec side)

The keys stay as r2 §6.5 has them. README §4 (§3 below) gives the decision rule. The rule rests only on what the Dot can
see:
- the conversation list, with attachedAt;
- the conversation's recorded messages and turn status. M006: the readback never shows tool calls, so a file written
  through a tool is invisible in it;
- the output folder's files, when the VM was not reset.

A conversation is a role's only when its first message is the full text of that role's prompt file. Other
conversations, such as the Dot's own mailbox checks (O62), do not count; two candidates are UNSURE (SD-62).

`UNSURE` is the default. `transcript` is always `not_available` on this platform (`p1_transcript_export = no`, O55).
The helper keeps the key so that the gate's other value stays expressible (SD-47).

| value | when (README rule) | what the fold then does | owner decision |
|---|---|---|---|
| NO_CONVERSATION | the list shows no conversation of the role with attachedAt at or after `after=`; answered with `list_shows_none=yes` | T43 SUPERSEDE, once per attempt, only from a START never answered | O58 (with O45) |
| NOTHING_WRITTEN | exactly one conversation is the role's; no message from it after the prompt; its turn status shows that it failed or was cancelled before it began to run. A turn that ran is UNSURE | Q: T44 INTERRUPT with OWNER_CHECK (S, G), T45 REPLACE with OWNER_CHECK (V). E: FREEZE_LOST or FREEZE_VISUAL_FAILED, never a restart | O45 (a conversation that provably wrote nothing), O55 (the Dot's reading, checked by the owner before scoring) |
| WRITTEN | any message from it, or a completed turn status, or (no reset) any file in its output folder | T47 freeze with AI_OUTPUT_LOST, or FREEZE_VISUAL_FAILED | O46 |
| UNSURE (default) | anything else: a turn that ran, whatever its status now (one the Dot stopped itself included), more than one candidate, an unreadable status, or doubt | as WRITTEN (T47) | O46 (a doubtful output counts as written), O55 |
| transcript=not_available | always, on this platform | NOTHING_WRITTEN needs OWNER_CHECK in Q, and never buys a retry in E | O55 |

### 2.10 Other fixes (spec text)

1. **S-04 post actions.**
   - `cli.run_command` runs the remaining `STATE.post` (`run_post`) after `clear_check`, and only when no HALT.json
     exists (§2.4.3).
   - `savepoint.finish` builds `post` as the remaining cache post, then the PENDING post, then `[DROP_LOCAL ...]`.
2. **S-05.** In `savepoint.write_commit`, after the PNG parts are written, the PartWriter whole sha256 and the
   per-file sha256 values must equal `draft.payload_png`. A difference is `HALT PNG_MANIFEST_UNSAFE`, raised before the
   entry and PENDING are written; the written parts are removed.
3. **S-07.**
   - `session_start.sh` writes the launcher
     `exec python3 -I -B -X pycache_prefix=/dev/null <repo>/deploy/vm2/vm2.py "$@"`. The helper process reads no
     bytecode: with the prefix, Python looks for `.pyc` files only under `/dev/null`, where none can exist, and `-B`
     writes none.
   - `vio/runner.load_runner` reads the bytes, checks the pin, runs `compile(raw, path, 'exec')` and `exec`s the result
     into a fresh `types.ModuleType('cps_job_v4')`. It sets `v1compat.CJ` and `v1reuse.CJ` as today. The audit uses this
     function.
   - The maintainer command lines of r2 §12 gain the same `-X` flag.
   - **The child processes (SD-63).** The reused segments start `sys.executable -I -B <script>`: the runner,
     `make_kit.py assemble`, `verify_drive_files.py` and the self-test suite. They do not inherit the `-X` option, and
     `-I` ignores `PYTHONPYCACHEPREFIX`, so they still read a valid `.pyc` of a module they import (the runner loads
     writer modules from the checkout). Therefore `session_start.sh`, after its clean-checkout check (step 2) and
     before it writes the launcher, removes every `__pycache__` folder under the checkout
     (`find "$REPO" -name __pycache__ -type d -prune -exec rm -rf {} +`, else `STOP SESSION_LAYOUT`). With `-B`
     everywhere, none is written afterwards. The remaining exposure is stated in §6.3.
   - **Tests.** vio `t_s07_runner_loaded_from_hashed_bytes` plants, after the bootstrap, a valid-header `.pyc` (the
     source's mtime and size in its header, other code) for `cps_job.py` and for one helper module whose code would
     change an observable result. It runs the launcher (the helper module's `.pyc`, W11) and calls `load_runner` in
     the test process, which has no pycache prefix (the `cps_job` `.pyc`, W12), and asserts each time that the hashed
     source ran. v1r `test_gap11_session_start_removes_pycache` plants `__pycache__` folders under `deploy/vm2/` and
     under the writer route before `session_start.sh`, and asserts that none remains (W84).
4. **S-08.** The `session_start.sh` order becomes steps 1, 2, 3 and 6 (HEAD == `--commit`, else
   `STOP SESSION_COMMIT_MISMATCH`), then 5 and 4, then the CPSV-REPO line and the final block.
5. **S-09 and stale downloads.** `cli.render`, before BLOCK.json is written, creates the parent of every DOWNLOAD
   target (`os.makedirs(..., exist_ok=True)`) and removes any file already at that target. A file at a printed path is
   thus always the Dot's new download. The `mkdir` calls in `fetch`, `pass_phase` and `ensure_local` are deleted.
6. **S-11.** `cli.run_command` catches `OSError` after `durable.DurableError` and prints
   `safe_stop(env, durable.DurableError(e.errno).code)`.
7. **OPX-08.**
   - `session_start.sh` adds `[ "$KIT" = none ] && HINT="" KIT=""` before the hint check. When no hint is given it
     removes `outbox/v2/HINT.json` (W73).
   - The header of a session block shows `STATE.head.seq`, else the head this session verified, else 000000. This is
     the same value HALT.json records.
8. **OPX-09 (c).** `drive.do_text` prints `STOP <CODE> HANDBACK A name=<name>` for UPLOAD_REFUSED, naming the first
   refused name. WAIT_APPROVAL prints no name.
9. **MAINT-6 (make_kit).**
   - **`cmd_pack`:** two members with equal binary file names fail with
     `FAILED <name>: two binary members would share one file name` (exit 1, nothing written).
   - **`cmd_assemble`:**
     - It groups the valid candidates by `(size, sha256)`. A valid candidate's content matches its header's size and
       sha256, and its binary file is present with that size and sha256.
     - Inside a group, it drops an unsafe path when another candidate of the group has a safe one.
     - It takes the path most copies give.
     - For a tie, it tries the tied paths and keeps the combination whose zip sha256 equals `--expect`. At most 64
       combinations are tried, else `FAILED path dispute`.
     - Two different contents for one path stay `the copies disagree`.
   - **Tests** reproduce the reviewer's slips: copy A's `@@ text NOTE.md` changed to `NOTE.mx`, and to `NOT~.md`, with
     copy B intact; and `a/src.xls` with `b/src.xls` at pack.
10. **MAINT-7.**
    - `FOLDERS['D']` becomes `'CPS/drills'`, and `series_folder('D<n>')` is `'CPS/drills/D<n>'`. Q and E are
      unchanged.
    - The audit uses `series_folder` instead of `FOLDERS[...]`. Its `load_listing` skips rows whose `mimeType` is
      `application/vnd.google-apps.folder` and counts them in `counts.folders`. Any other row without a field is
      refused, as today.
11. **MAINT-9.** `Audit.review` uses
    `window = [utc_minus(head.utc, tol), utc_minus(restore.utc, -tol)]`, with `tol` set to
    `genesis.gates.p3_clock_tolerance_seconds`.
12. **MAINT-10.**
    - `fold.jobs_of(doc)` is `[[c.case_id, c.order, (c.reason or True) if c.nonattempt else None] for c in doc.cases]`,
      and `cli.genesis` uses it.
    - The audit reads the genesis kit's RELEASE.json member, takes `qualification.jobs_file`, and reads the kit member
      at its path relative to `genesis.layout.runtime`. The release requires that path to be under runtime.
    - `probe_p5.py start` refuses `--seconds` below `--min-gap` with `REFUSED SECONDS_BELOW_MIN_GAP` (a probe code, not
      a helper code).
13. **MAINT-5, MAINT-8.**
    - ASSEMBLE.json gets `verify_frozen: bool`, and `score_check build` refuses `ASSEMBLE_NOT_VERIFIED`.
      SCORE_PLAN.json gets `pool_sha256`.
    - `score_check check` takes `--plan P --audit A --assembled S --pool L --owner-checks O --manifest M --out C`. Each
      input's sha256 must equal the plan's. Then `plan()` runs again, and its readers' dispositions, reasons and carrier
      sha256 must equal the plan file's, comparing paths relative to the plan's folder; otherwise `PLAN_MISMATCH`. The
      manifest is checked against the re-derived plan.
14. **OPENED is deleted (SD-37).** P1 shows that the conversation list with attachedAt exists, so the no-list path is
    dead on this platform.
    - The release gate (`host.gates_problem`) requires `('p1_conversation_list', 'yes')`, and so does `t01`.
    - Deleted:
      - in the entry: the kind OPENED;
      - in the fold: rows T35 and T36, `g35`, `e35`, the ROLE field `opened`, and the `p1_conversation_list == 'no'`
        branches (`forced_for`, `no_conversation_admissible`, `start_for`);
      - in the plan: plan rows 5-7's `then=now`, the OPENED question and AWAIT_CONVERSATION;
      - in the glue: `apply_answer` OPENED and the worker's `if ro['opened']`.
    - OPEN_CONVERSATION always waits for the end.
15. **The listing hint is deleted (SD-36), and RECHECK runs on every qualification restore (SD-59).** Deleted: `LIST
    <folder> NEWEST <k>`, the LIST answer, `p2_newest_first` and `LIST_NEWEST_K`. Without a Dot hint, the head search
    gallops from 1. The step-6 RECHECK (r2 §8.4 step 6) runs on every qualification and drill restore, with or without
    a hint, and in an everyday series when the clearing restore's `moved_pending.uploaded` is not empty. The condition
    `hs['via'] != 'hint'` (session.py `_commit`) is deleted, and with it the head verdict's `via` (cm
    `test_op05_recheck_after_every_q_restore`, rs `D_hint_restore_late_copy_at_n1_forks_at_recheck`, W78).

### 2.11 Codes (`core/names.py` CODES follows)

| change | code | class | raised in |
|---|---|---|---|
| added | `DOWNLOAD_INCOMPLETE` | REFUSED (slip, re-FIND, exit 4) | §2.2.1 |
| added | `COPY_MISMATCH` | REFUSED (slip, re-FIND) | §2.2.1, commit and setup loops |
| added | `RAW_INVALID` | REFUSED (counted); details `missing`, `json`, `count`, `shape`, `pages`, `error`, `entry`, `duplicate`, `listing` | §2.3 |
| added | `TOOLS_FILE_INVALID` | REFUSED (counted) | §2.8 |
| added | `SLIP_LIMIT` | STOP, local sticky, C | §2.2.1, §2.2.3, §2.2.5 |
| added | `WAIT_APPROVAL` | STOP, not sticky, HANDBACK A | §2.5 |
| changed | `DOWNLOAD_MISSING` | REFUSED: now a slip with a re-FIND block | §2.2.1 |
| changed | `FORK`, `LINK_MISMATCH` | only from downloaded bytes; the evidence is kept in `fork_<utc14>/`; also a copy at the moved PENDING's seq with other bytes | §2.2.2, §2.4.4 |
| changed | `FINAL_MESSAGE_INVALID` | missing or not UTF-8 (an empty file is accepted) | §2.2.4 |
| changed | `AI_OUTPUT_TOO_LARGE` | also a final message over `max_ai_output_bytes` | §2.2.4 |
| changed | `CONFIG_CHANGE_NOT_ALLOWED` | also a non-config-only kit change in a clearing restore | §2.4.4 |
| changed | `INPUTS_CHANGED` | counted refusal, bounded by SLIP_LIMIT | §2.2.5 |
| changed | `UPLOAD_REFUSED` | the STOP line names the file (`name=`) | §2.10.8 |
| changed | `PLACE_TARGET_NOT_EMPTY` | no longer raised when a placement target is equal or moved aside | §2.4.6 |
| changed | `VALUE_PATTERN` | `tools=none` | §2.8 |
| changed | `UTC_OUT_OF_WINDOW` | now from `check_answers` (started after ended) | T7 |
| removed | none | | |

**Constants.**
- Added: `O63_NOTE`, `O63_NOTE_RE`, `O63_REPORT`, `RAW_MAX_BYTES = 1048576`, `MAX_TOOL_LINES = 2000`,
  `SLIP_ASKS = 3`, `BASE_RE`, the pattern `APPROVAL`, and `STAGE_FREE_BYTES = 1000000000` (SD-69). No entry of CODES
  is added: a stage refused for space is the existing `STOP DISK_FULL`, with `step` `stage` in its detail.
- Changed: TOOLS is redefined, and `approval` joins KEY_NAMES.
- Removed: `LIST_NEWEST_K`, `PATTERNS['MD5']`, and `cli.DEFAULT_GATES`.

**Maintainer-tool codes** are not in CODES; L1 collects them from `maint/*.py` as today.
- assemble: `ROOT_INVALID`; `Bad LAYOUT_PATH` also for a base that differs from the GENESIS entry's.
- score_check: `ASSEMBLE_NOT_VERIFIED`, `PLAN_MISMATCH`, `O63_ATTESTATION_MISSING`.
- Audit details: `AUD_KIT_CHANGE` with details `recompute`, `clear`, `cleared_local` and the kit_change codes;
  `AUD_KIT` with detail `jobs`. There is no `from_equals_to` detail (§2.7).

### 2.12 Schemas, fold rows and session phases touched

| item | change |
|---|---|
| entry S1 (`core/entry.py`) | KINDS without OPENED. BODY GENESIS and RESTORE get `approval`, which must be `"none"`. RESOLUTION_KEYS gets `conversation` (str or null). The AI revision 1 `attested.tools_present` shape is checked. A non-null `cleared_local` is allowed only on RESTORE and GENESIS. The RESTORE's `placed` items get `aside` (str or null). `HELPER_VERSION` is `cps-vm-helper.v2.1` |
| fold rows | T01 (`t01`: layout and the list gate), T10-T13 (`_virtual` job_dir), T20, T21, T23 and T24 (`_consumed_ok`), T42 (`e42` records `conversation`), T59 (`g59` from != to). **T35 and T36 are removed** (SD-37). No row is added |
| AI body | `attested.tools_present` for S, G and V revision 1. G's `attested.tools` is removed. `final_message_sha256` is set for every role. Members `attest/final_message.txt` and `attest/tools.txt` |
| config | adds `tool_inventory_sha256`. The gates lose `p2_md5_visible` and `p2_newest_first`. The release gate adds `p1_conversation_list == 'yes'` |
| kit | adds the member `TOOL_INVENTORY.txt` |
| local files | HALT.json adds `kit_sha256`, `tried` and `check`, and is written for `HALTED_<code>` too. STATE.json adds `halt_local`. BLOCK.json adds `refused`. PENDING and the setup loops add `slips`. RESTORE_WORK adds `slips`, `approval`, `cleared_local`, `moved_pending`, `halt_local` and `lookups[].void`, and loses `listing`. New folders under `outbox/v2/`: `raw/`, `clear/`, `cleared_<utc14>/`, `aside_<utc14>/`, `fork_<utc14>/` |
| session phases (`PHASES`) | `LAYOUT, SETUP, OPERATOR, KIT, CONFIG, FINGERPRINT, APPROVAL, HEAD, IDENTITY, PASS, CLOCK, KIT_ACCEPT, CLASSIFY, RESOLVE_END, RESOLVE_PLACE, RESOLVE_EXPORT, RESOLVE_ATTEST, PLACE, COMMIT, RECHECK, DONE`. There is no CLEAR phase. The head verdict has no `via` |
| maintainer reports | AUDIT.json adds `o63`, `counts.folders`, `approvals` and `same_boot_restores`. ASSEMBLE.json adds `verify_frozen` and requires `root`. SCORE_PLAN.json adds `pool_sha256` and `isolation_statement` |
| Drive | a D series uses the folder `CPS/drills/D<n>` |

T regenerates the table golden (`tests/table_golden.json`) as a reviewed golden update (r2 §4.8). The rows T35 and T36
disappear, and generated entries change shape where §2.12 says.

### 2.13 Code deleted (one mechanism instead of special cases)

| what | where | why |
|---|---|---|
| md5-visible mode: `p2_md5_visible`, `ID:MD5:SIZE`, the md5 compares, the PASS known-md5 shortcut, `PATTERNS['MD5']`, `DEFAULT_GATES` | savepoint.on_found, session.rule_v and `_status`, cli.do_found, fetch, pass_phase, verify_head, drive.parse_copy and found_attest, host.GATE_VALUES, names | M004: there is no md5 anywhere. Rule V (§2.1) is the one confirmation |
| the size FORK at `found`, and rule_v's size branch | savepoint.on_found, session.rule_v | the download decides (§2.2.2) |
| the listing head hint: `LIST`, the LIST answer, `p2_newest_first`, `LIST_NEWEST_K`, PrintBlock.lists | session.head_search and `_search_step`, cli.do_found, drive.body_lines, found_attest, `_line_form`, check_found, step.PrintBlock | the hint and the gallop serve; a listing was only a hint (SD-36) |
| the head verdict's `via` and the hint-path RECHECK skip | session.head_search, `_commit` | RECHECK on every qualification restore (SD-59) |
| OPENED: the kind, T35, T36, ROLE.opened, plan rows 5-7 (`then=`, the OPENED question, AWAIT_CONVERSATION), the no-list branches | entry, fold, plan, cli.apply_answer, worker, outcome, README | P1: the list exists; the gate is required (SD-37) |
| `_Env1`, `setup_block`, `setup_found`, `setup_verify`, and the four copies of the loop-block emit code | savepoint; cli.pending_step, upload_files, pass_phase, reupload (one `cli.loop_block`) | one loop implementation (S-01) |
| `record_downloads` and `verify_head` merged into one download check | cli | one check, which also hosts the slip rule and the moved-PENDING rule |
| `sticky_halt`, its "not built" docstring, and `stop_block`'s exclusion of `HALTED_` codes | cli | replaced by `clear_check` (§2.4.3) |
| the special INPUTS_CHANGED render | cli.start_chain | counted refusal (§2.2.5) |
| the final-message character rule, its 8 KiB limit and its non-empty check | cli.ai_commit | D3c, SD-65 |
| scattered DOWNLOAD `mkdir` calls | cli.fetch, pass_phase, ensure_local | one in render (S-09) |
| `ensure_text` and `ensure_copy` as two functions | cli | one function that places a member from its entry (§5.1) |
| dead code | host.read_release, savepoint.drop_local and read_pending, step.Evict and Wait, session.work_sha, v1compat Block.option | no caller |
| the unused reused segments `canon`, `check_pkg_manifest`, `pkg_manifest_problem`, `join_slices` and `scrub`, plus any segment that L10 reports unused after the deletions above | vio/v1reuse.py; REUSE_MANIFEST.json goes from 52 to 47 names or fewer; test_reuse | L10 reported them unused (OQ-6) |
| the audit's own runner loader and its own kit-change rule set | maint/audit.py | vio.runner.load_runner and session.kit_change (§2.7) |
| the calendar loop of `utc_minus` | core/names.py | `datetime` arithmetic (pure: no clock read; L2 allows it) |
| tests | the DL config and its 5 scenarios, the DV md5 and listing variants, `D_head_listing_ghost`, FakeDrive `list_newest`, ghosts and the md5-visible switch, the T35/T36 core tests; builder mutants G2 and G29 become "path deleted" (md5-visible mode, the listing) | coverage argument in §5.2 |

### 2.14 Harness changes (C owns `tests/fakes.py` and `tests/core_world.py`)

**FakeDrive.**
- md5 is always hidden. `list_newest` and ghosts are deleted.
- `raw_find(folder, name)` returns the M004-shaped envelope: `title`, `id`, `size` as a decimal string, `created_at`,
  `file_or_folder: "file"`, `parent_ids` and `mime_type`.
- `download(id)` of an unknown id returns nothing, so the target stays missing.
- `approve(name)` lands a refused upload, also after a reset of the World (D6 scenarios).
- `raw_find` entries carry every key of the M007 result (§2.3), with invented values (D16).

**FakeDot.**
- **Found.** It answers `found --raw` by default, saving one JSON list per block under a new
  `BASE/attest/raw_<n>.json`. Policy `found` is `raw` or `manual`.
- **Slips.** Policy `slips` injects `wrong_id`, `size`, `short_download`, `missing`, `stale_raw` (it passes the
  previous block's raw path again) or `swapped_raw` (it saves two results in swapped order), each at the k-th found or
  download. On exit 4 with a slip code, FakeDot executes the block after the REFUSED line.
- **Uploads.** FakeDot uploads each UPLOAD line once, the first time it sees it, and asserts that no UPLOAD line
  follows a REFUSED line and that no reprint holds one (an oracle in every rs scenario).
- **Refused uploads and approval.** It keeps `notes['refused']`: the names it attested with `--refused`, cleared only
  when the owner reports them approved or denied. Policy `approval` is `notes` or `none`. It handles `HANDBACK A` for
  UPLOAD_REFUSED (with `name=`) and for WAIT_APPROVAL.
- **Tools and messages.** Policy `tools` is `inventory` or `file` (a file under `BASE/attest/`). It writes
  `final_message.txt` for S, G, V and V continuations, empty when the policy says the conversation gave none.
- **Inputs.** Policy `inputs` is `restore` or `lost`, for INPUTS_CHANGED; with `lost` it runs `go` until SLIP_LIMIT.
- **Checks.** It never creates a DOWNLOAD parent, and it asserts that the parent exists. Its O7 check follows §2.2.6.
- **The M007 routes (D16).** A DOWNLOAD writes the bytes into FakeDot's own attachment folder outside BASE, then copies
  that file to the target, as the Dot does (§2.16.1). A raw file is written as
  `json.dumps(obj, separators=(',', ':'), ensure_ascii=False)`, the compact text that `JSON.stringify` gives.
- **Disk records (D16).** At every block it records the run job folders under BASE/qual and BASE/jobs and the files
  in `outbox/journal` and `inbox/journal`, for the World extra `x_d16_disk` (§2.16.5).
- **Counts.** It counts helper commands (by argv[0]), Drive calls, raw files, waits and conversation events per block.
  `x_opx10` and `x_op07_restore` write them into `tests/budget_golden.json` format (§5.3).
- **`bootstrap_stop`.** When the World's own bootstrap (`session_start.sh`) stops with a SESSION_* code, the
  scenario's result carries `bootstrap_stop: <code>` (§2.15.4).

**World.**
- The kit gets TOOL_INVENTORY.txt (invented tool names) and `tool_inventory_sha256`.
- `clear_kit(code, seq)` builds and plants a config-only kit with `clear` and returns its k12.
- The D series uses `CPS/drills/D1`.
- `World.assemble` creates an empty dedicated root inside the world and passes it; the `root='/'` default is deleted.

**core_world.py.** Resolutions carry `conversation`. GENESIS and RESTORE carry `approval: "none"`. job_dir is
`job_dir_of`. The consumer rule applies. AI attestations carry `tools_present`. There is no OPENED move. A RESTORE
while HALTED keeps the kit and carries no `cleared_local`. Hostile entries for the MAINT-1 tests are built outside
`core_world.commit` (§2.6).

### 2.15 Tests and mutants (D11)

#### 2.15.1 Hand mutants W01-W110

T writes each mutant as exact substitutions against the v2.1 code once C lands it. Each one puts back the 2015773
behaviour, or removes one v2.1 rule, and names its killing tests.

| id | mutation | killed by |
|---|---|---|
| W01 | the APPROVAL phase is skipped | cm `test_d6_approval_asked_before_restore_and_genesis`, rs `D_refuse_reset_approval_pending` |
| W02 | the clear verdict compares only the code | cm `test_d5_clear_verdict_exact_clear_and_config_only`, rs `D_clear_same_boot_setup_failed`, `D_clear_same_boot_fork` |
| W03 | `settle` refuses an existing target (PLACE_TARGET_NOT_EMPTY) | vio `t_d5_placement_accepts_equal_or_moves_aside`, rs `D_sameboot_damaged_cache_restores`, `D_clear_same_boot_foreground_died` |
| W04 | e42 drops `conversation` | cm `test_int_r2_03_restore_conversation_recorded` |
| W05 | `_consumed_ok` loops over the listed items only | ct `test_int_r2_04_consumer_stage_without_consumed_is_t25` |
| W06 | the loop reads `env.cfg['max_upload_bytes']` | vio `t_s01_setup_failed_log_uploaded_without_kit_config` |
| W07 | a download of a size other than the attested one is FORK | vio `t_s03_short_download_refinds_real_fork_keeps_bytes`, rs `D_slip_short_download_refinds` |
| W08 | STATE.post is not resumed | vio `t_s04_pending_post_resumed_before_next_commit` |
| W09 | the PNG whole and per-file compare is removed | vio `t_s05_png_changed_before_part_write_halts` |
| W10 | the profile-folder print check is removed | cod `test_s06_profile_folder_with_brace_refused_before_commit` |
| W11 | the launcher has no `-X pycache_prefix=/dev/null` | lint `t_l13_launcher_ignores_bytecode`, vio `t_s07_runner_loaded_from_hashed_bytes` (the planted helper-module .pyc) |
| W12 | `load_runner` goes through `spec_from_file_location` | vio `t_s07_runner_loaded_from_hashed_bytes` (the planted cps_job .pyc) |
| W13 | the HEAD check comes after the setup step | v1r `test_s08_wrong_head_stops_before_setup` |
| W14 | `render` does not create DOWNLOAD parents | vio `t_s09_download_parent_exists_when_printed` |
| W15 | `run_command` does not catch OSError | cod `test_s11_oserror_outside_stage_prints_stop_block` |
| W16 | a BLOCK.json behind STATE invalidates the whole cache | vio `t_opx07_stage_death_stop_names_real_head_and_kit`, rs special `test_foreground_died_same_boot_stops` |
| W17 | `write_doc` returns a new dict | vio `t_opx01_restore_work_writes_kept`, rs oracle "one END_CONVERSATION per open role per boot" |
| W18 | DOWNLOAD_MISSING reprints the DOWNLOAD block | vio `t_opx02_mistyped_id_refinds_then_commits`, rs `D_slip_wrong_id_refinds` |
| W19 | a size other than ours at `found` is STOP FORK | vio `t_opx03_size_slip_refinds`, rs `D_slip_size_refinds` |
| W20 | the README outcome rule is removed | lint `t_l14_readme_rules` |
| W21 | the brace and angle-bracket rule is back | vio `t_opx05_final_message_any_characters_verbatim` |
| W22 | refusals are not counted | cod `test_opx06_inputs_changed_bounded_then_slip_limit`, vio `t_d3_refusals_bounded_then_slip_limit`, `t_d4_raw_invalid_reasked`, rs `E_inputs_lost_after_reset_bounded` |
| W23 | the slip counter is not incremented | vio `t_d3_fourth_slip_stops_slip_limit`, rs `D_slip_limit_then_clear` |
| W24 | `--kit none` is a usage error | v1r `test_opx08_kit_none_bootstraps_without_hint` |
| W25 | the UPLOAD_REFUSED STOP has no `name=` | vio `t_opx09_refused_stop_names_the_file` |
| W26 | one count of README §7 is off by one | lint `t_l14_readme_rules` (the README table against `tests/budget_golden.json`) |
| W27 | unknown `--only` names are ignored | lint `t_only_unknown_name_exits_2` |
| W28 | the fold's `_virtual` job_dir check is removed | ct `test_maint1_new_run_job_dir_must_be_the_layout_path`, mt `test_maint1_audit_refuses_hostile_new_run` |
| W29a | assemble's layout check is removed (realpath confinement kept) | mt `test_maint1_forged_all_frozen_job_dir`, `test_maint1_wrong_mapping_refused` |
| W29b | assemble's realpath confinement is removed (layout check kept) | mt `test_maint1_self_consistent_hostile_base_confined`, `test_maint1_symlink_after_begin_refused` |
| W30 | `--root` defaults to `/` | mt `test_maint1_assemble_root_required_empty_dedicated` |
| W31 | `tools=none` is accepted | vio `t_maint2_tools_none_refused_inventory_file_accepted` |
| W32 | the generation record has no `notes` | vio `t_maint2_generation_record_tools_and_o63_note` |
| W33 | score_check skips the O63 check | mt `test_maint2_score_check_requires_tools_attestation_and_states_isolation` |
| W34 | the audit's CLEAR checks are removed | mt `test_maint3_audit_refuses_unauthorized_clear` |
| W35 | g59 has no from != to | ct `test_maint3_clear_with_unchanged_kit_t60`, mt `test_maint3_audit_refuses_unauthorized_clear` (from = to) |
| W36 | the audit ignores kit_change's code | mt `test_maint4_audit_only_kit_change_verdicts` (each of its three cases) |
| W37 | build accepts `verify_frozen` false | mt `test_maint5_score_check_refuses_unverified_assembly` |
| W38 | make_kit path disputes are not settled (path `deploy/make_kit.py`) | mk `MakeKitTest.test_member_path_slip_in_one_copy_recovers`, through v1r `test_mk1_header_slip_in_one_copy_recovers` |
| W39 | pack accepts duplicate binary names (path `deploy/make_kit.py`) | mk `MakeKitTest.test_pack_refuses_duplicate_binary_names`, through v1r `test_mk2_duplicate_binary_names_refused` |
| W40 | the D folder is back to `CPS/reports` | cm `test_maint7_drill_series_own_folder` |
| W41 | check trusts the plan bytes | mt `test_maint8_check_detects_edited_plan` |
| W42 | the review window has no tolerance | mt `test_maint9_review_window_widened` |
| W43 | the audit skips the jobs compare | mt `test_maint10_genesis_jobs_differ_from_kit_unclean` |
| W44 | probe start accepts seconds below min-gap | p5 `test_maint10_probe_start_refuses_seconds_below_min_gap` |
| W45a | the harness does not commit the mutation | `run_tests.py --mutants --selftest`: the clean-HEAD check gives HARNESS_ERROR |
| W45b | the harness neither commits the mutation nor checks the clone | `run_tests.py --mutants --selftest`: G31's reset failures carry `bootstrap_stop: SESSION_REPO_DIRTY`, and G31 is not KILLED |
| W46 | `parse_raw` matches a title that only contains the name | vio `t_d4_parse_raw_rules`, `t_d4_found_raw_search_and_listing_objects` |
| W47 | S and V entries without the final message or tools | vio `t_maint2_s_v_entries_archive_message_and_tools` |
| W48 | the audit treats two sha256 values of one name as harmless | rs `D_refuse_reset_approval_wrong_none` (the audit must be unclean) |
| W49 | `foreground_check` drops this boot's FOREGROUND.json without a STOP | rs special `test_foreground_died_same_boot_stops` |
| W50 | HALT.json records head 0 and no kit after a stage death | vio `t_opx07_stage_death_stop_names_real_head_and_kit` |
| W51 | the RESTORE while HALTED takes the new kit (`kit_change` recorded) | ct `test_session_c2_clear_restore_keeps_kit_then_clear_takes_it`, rs `D_clear_committed_halt_same_boot` |
| W52 | the `t01` layout check is removed | ct `test_maint1_genesis_layout_base_relative` |
| W53 | the interrupt argv ignores the resolution's conversation | vio `t_int_r2_03_interrupt_gets_conversation_id` |
| W54 | `session._facts` ignores the `void` flag | cm `test_d3_head_search_ignores_void_lookups` |
| W55 | the audit's `cleared_local` check is removed | mt `test_maint3_audit_checks_cleared_local` |
| W56 | the audit refuses folder rows | mt `test_maint7_drill_listing_with_folder_rows_clean` |
| W57 | (retired in r4: `approval=pending` clears nothing, because APPROVAL comes before HEAD) | none |
| W58 | `cleanup_leftovers` is a no-op | rs special `test_foreground_died_same_boot_stops`; it survives every in-process Kill scenario, which MUTANTS_RESULTS.json records |
| W59 | the cache is invalidated before the verdict (r3's restart rule) | vio `t_d5_refused_clear_kit_keeps_cache` (STATE.json, PENDING.json and RESTORE_WORK byte-identical) |
| W60 | the post resume runs before `clear_check` | vio `t_d5_post_action_halt_cleared_same_boot` |
| W61 | `tried` does not take the HINT.json kit of the moment of the stop | vio `t_d5_stale_hint_never_checks` |
| W62 | the check ignores `tried` | vio `t_d5_refused_clear_kit_keeps_cache` (the next `go` prints the same STOP with zero Drive calls) |
| W63 | `tried` does not take the kit in use | vio `t_d5_kit_in_use_never_checks` |
| W64 | `found` or `answer` start the check | vio `t_d5_found_answer_while_halted_print_stop` |
| W65 | a refused candidate removes HALT.json | vio `t_d5_refused_clear_kit_keeps_cache` (HALT.json present, its code unchanged) |
| W66 | the clear leaves HALT.json in place and `cleared_local` null | rs `D_clear_same_boot_setup_failed` (the RESTORE entry's `cleared_local` equals HALT's `{code, head_seq, kit_sha256}`; HALT.json is under `cleared_<utc14>/`), vio `t_d5_wait_approval_in_clearing_restore` |
| W67 | `settle` compares paths, types and sizes only | vio `t_d5_placement_accepts_equal_or_moves_aside` (the same-size changed file, the mode change) |
| W68 | the refused count never resets | vio `t_d3_refused_count_resets_per_block` |
| W69 | a `files` element without the name counts as absence | vio `t_d4_parse_raw_rules` |
| W70 | the next-page token is ignored | vio `t_d4_parse_raw_rules` |
| W71 | TOOL_INVENTORY.txt is not checked against `tool_inventory_sha256` | vio `t_maint2_inventory_sha_checked` |
| W72 | `tools=file` accepts a link | vio `t_maint2_tools_file_link_refused` |
| W73 | a no-hint bootstrap keeps an older HINT.json | v1r `test_opx08_kit_none_bootstraps_without_hint` |
| W74 | S1 accepts an approval other than `"none"` | ct `test_d6_entry_approval_must_be_none` |
| W75 | S1 accepts `cleared_local` on any kind | ct `test_d5_cleared_local_only_on_restore_and_genesis` |
| W76 | `files_found` is computed after `settle` only | vio `t_gap02_files_found_before_settle`, rs `D_clear_same_boot_open_generator` |
| W77 | the clearing restore adopts a single copy at the moved PENDING's seq | vio `t_gap04_moved_pending_foreign_copy_forks`, rs `D_clear_same_boot_fork_foreign_only` |
| W78 | RECHECK is skipped on the hint path | cm `test_op05_recheck_after_every_q_restore`, rs `D_hint_restore_late_copy_at_n1_forks_at_recheck` |
| W79 | a BLOCK.json ahead of STATE moves alone | vio `t_gap05_block_ahead_invalidates_cache` |
| W80 | the clearing KIT_ACCEPT accepts a non-config-only change | cm `test_d5_clearing_restore_refuses_release_change` |
| W81 | the clear leaves BASE/attest and BASE/inbox in place | vio `t_gap08_clear_moves_attest_and_inbox` |
| W82 | `render` keeps an existing file at a DOWNLOAD target | vio `t_gap08_render_removes_stale_download_target` |
| W83 | the audit does not tie GENERATION_RECORD.json to its G entry | mt `test_gap10_generation_record_tied_to_g_entry` |
| W84 | `session_start.sh` keeps `__pycache__` folders | v1r `test_gap11_session_start_removes_pycache` |
| W85 | `load_cache` accepts `halt_local` without HALT.json | vio `t_gap12_halt_removed_out_of_procedure_restores` |
| W86 | a reprint keeps the UPLOAD lines | vio `t_op02_reprint_has_no_upload_lines` |
| W87 | an accepted raw file stays where it was | vio `t_op03_raw_file_consumed`, rs `D_slip_stale_raw_head_search` |
| W88 | copies are assigned by element position | vio `t_d4_swapped_elements_assigned_by_title` |
| W89 | APPROVAL comes after HEAD | cm `test_d6_approval_before_head`, rs `D_refuse_reset_approval_pending` |
| W90 | the non-empty final-message check is back | vio `t_opx05_empty_final_message_accepted` |
| W91 | a RESTORE while HALTED records `cleared_local` | vio `t_d5_halted_restore_no_cleared_local` |
| W92 | `found` for the check's own block prints the STOP | vio `t_d5_clear_check_found_accepted`, rs `D_clear_same_boot_setup_failed` |
| W93 | assemble trusts `af.genesis.base` | mt `test_maint1_assemble_base_from_genesis` |
| W94 | AUDIT.json lists no approvals and no same-boot RESTOREs | mt `test_gap06_audit_lists_approvals_and_same_boot_restores` |
| W95 | the README's UPLOAD_REFUSED row says "or tells you to continue" again | lint `t_l14_readme_rules` |
| W96 | C8b re-prepares whatever `reprepares` says | cm `test_gap13_c8b_after_second_restore_abandons`, rs `E_inputs_lost_after_reset_bounded` |
| W97 | `tried` does not take HALT.json's `kit_sha256` (the halted kit: r3's `k != stopped_kit12`) | vio `t_d5_halted_kit_never_checks` |
| W98 | a final message over `max_ai_output_bytes` is the counted refusal `FINAL_MESSAGE_INVALID`, as an over-8-KiB one was at 2015773 | vio `t_opx05_oversize_final_message_stops` |
| W99 | FakeDot counts Drive calls only, the basis of the 2015773 budget (repo-relative path `deploy/vm2/tests/fakes.py`) | v1r `test_opx10_tool_calls_match_budget_golden` (the measured counts against `tests/budget_golden.json`) |
| W100 | `invalidate` also moves the boot mark `inbox/.boot` | vio `t_d5_wait_approval_in_clearing_restore` (the command after the clear finds the clear kit deleted by `cleanup_leftovers`), rs `D_clear_same_boot_setup_failed` |
| W101 | `clear_check` returns when HALT.json is not valid | vio `t_d5_damaged_halt_stops_unclassified` |
| W102 | a STOP header shows the kit in use instead of HALT.json's | vio `t_d5_halted_kit_never_checks` (its STOP header names the journal's kit) |
| W103 | a re-FIND of the clear check resets `H.check.slips`, so the fourth slip never ends the check | vio `t_d5_clear_check_bounded` |
| W104 | (D16) README §2's DOWNLOAD sentence is r4's "saves the file from Drive at exactly the path given ... never copy a local file there instead" | lint `t_l14_readme_rules` |
| W105 | (D16) README §3.1's never-work-around sentence is removed | lint `t_l14_readme_rules` |
| W106 | (D16, non-root) `remove_tree` does not call `make_writable_tree` (repo-relative path `deploy/vm2/cpsvm2/vio/v1reuse.py`; the killing set leaves out `test_reuse` and the lints, which check the reused segments' hashes) | v1r `test_d16_evict_runner_frozen_folder_nonroot`, vio `t_d16_settle_moves_readonly_target_aside`, in the non-root pass |
| W107 | (D16, non-root) `settle` moves a target aside without first setting its owner write bit | vio `t_d16_settle_moves_readonly_target_aside`, in the non-root pass |
| W108 | (D16) `run_stage` has no `require_space` before a chain | vio `t_d16_stage_refuses_low_space_before_runner` |
| W109 | (D16) the DROP_LOCAL post action removes nothing | v1r `test_d16_disk_bounded_over_runs` |
| W110 | (D16) the EVICT post action leaves the job folder | v1r `test_d16_disk_bounded_over_runs` |

**Reviewer mutants (D11c).** T ports each to the v2.1 text of the same rule:
- N04: the START-boot half of g37.
- N05: `continued_boot` in g38.
- N06: the CONTINUED branch of `resolution_action`.
- N07: the restart-owed clause of g10.
- N18: RECHECK of N+2 and N+3.
- N37: finish's pending check.
- N40: started after ended, now in `names.check_answers`.
- N42: the session download check, now the slip.
- N44: the 0-byte transcript.
- N50: CHANGEABLE_KEYS in S5.
- N52: interrupts in g11.

Each is killed by the row of §1.2 that names it. §2.15.6 gives the proof table.

**Builder mutants.** G1-G34 and M2-nn are kept and re-targeted. G2 and G29 become `path deleted` (md5-visible mode,
the listing) and are recorded in the `DELETED` table with the reason. So is every builder mutant on the OPENED path.

#### 2.15.2 Generated guard mutants (D11b, SD-66)

`tests/mutants.py guard_mutants()` parses the target functions with `ast` and mutates every guard site in them.

**Targets.**
- **Core set:** every function of `core/fold.py` and `core/session.py`.
- **Glue set (TG-03):** the commit and restore glue that GUARD_TESTS keys name: `savepoint.block`, `on_found`,
  `on_verify`, `finish` and `slip`; `cli.go_checks`, `do_found`, `do_answer`, `session_slip`, `clear_check`, the
  merged download check and `stop_block`; `place.settle`; `drive.parse_raw`.

**Guard sites.** In every target function:
1. **and/or anywhere.** Every operand of every and/or in the body is a *remove* site: it is replaced by the neutral
   constant, `True` in an and, `False` in an or, recursively and through `not`. This includes an and/or inside call
   arguments, comprehension and generator elements, lambdas, assignments and return values. Excluded: a default, that
   is an and/or whose last operand is a literal or an empty container (`x or 0`, `x or []`, `x or {}`, `(r or True)`).
2. **Whole predicates.** A *negate* site wraps one of these in `not (...)`:
   - the test of an `if`, `elif`, `while`, `assert` or conditional expression, and each comprehension `if`, when it is
     not an and/or;
   - a Compare, a call of `any`, `all`, `bool` or `isinstance`, or a Name, that is the whole value of a `return`, or of
     an assignment whose target is read later by an `if`, `while`, `assert` or `return` in the same function.
3. **Chained comparisons.** Each link of a chained comparison (`a == b == c` has two) is a *link* site: the chain is
   rewritten as the and of its links, and that link is replaced by `True`.

There is one mutant per site. It is applied with `ast` and written back with `ast.unparse`, since formatting does not
affect execution. The id is `GM-<module>-<function>-<k>-<r|n|l>`, where k is the site's position in a fixed walk of that
function. An edit elsewhere never renames it; an edit to the function renames its sites, so its EQUIVALENT entries are
reviewed again.

**Counts.** At 2015773 this rule gives 543 sites in fold.py (405 remove, 134 negate, 4 link) and 200 in session.py
(74 remove, 126 negate), counted by the planner's read-only script
`scratchpad/vm_helper/v21/planner_r2/keep/count_sites_r2.py` (r3's narrower rule gave 466 and 186). v2.1 is expected
to have about 735 core sites. The 2015773 forms of the glue functions hold about 225 sites; v2.1 is expected to have
about 200.

**Killing set.**
- Core set, two stages: stage 1 runs `test_core_table,test_core_more`; the survivors run stage 2:
  `test_core_props,test_codes,test_vio,test_maint,test_v1_regressions`.
- Glue set: stage 2 only.

**Survivors and equivalence (TG-04).** A survivor is a failure unless `EQUIVALENT[id]`, a dict in mutants.py, records
why the mutant is equivalent, naming the guaranteeing check by function and condition. For fold.py, only a check that
runs earlier on `fold.apply`'s own path counts: the S1-S6 structural checks, the row dispatch, or an earlier conjunct
of the same guard. The writer (session, worker, cli) never counts as a guarantee for fold.py, because the fold verifies
downloaded content that the writer did not necessarily write. A session.py or glue equivalence may cite its callers.
The run writes the table of survivors and arguments into MUTANTS_RESULTS.json, and G-1 reviews every entry.

**Generator selftest** (`run_tests.py --mutants --selftest`). The generated set must hold a site for each reviewer
mutant on fold and session (N04: the boot link of g37's chain; N05: g38's `continued_boot` conjunct; N07: g10's
restart-owed clause; N18: the N+2 and N+3 presence operand of the RECHECK test; N50: `_s5`'s CHANGEABLE_KEYS conjunct;
N52: g11's `interrupts` operand) and for the v2.1 sites `clear_ok`, `clear_verdict`'s `config` test, g59's
from != to conjunct, `_virtual`'s job_dir comparison, `t01`'s layout comparison and `resolution_action`'s `oc`
assignment. A missing site fails the selftest.

#### 2.15.3 Direct guard tests (D11a)

`tests/test_core_table.py` holds `GUARD_TESTS = {key: [test names]}`. The keys are:
- every fold TABLE row id;
- every function of `core/session.py` that contains a guard site;
- the commit and restore glue of the glue set (§2.15.2).

The new lint `t_l15_every_guard_has_a_direct_test` checks that every key has at least one listed test and that every
listed test exists. A "direct" test feeds that row or function the case that its guard decides. The generated guard
mutants of both sets (§2.15.2) are the measure: a listed test that reaches none of its function's guards leaves that
function's mutants alive.

#### 2.15.4 The mutation harness (D11d)

**`one(m)`** runs each mutant through these steps:
1. `git clone -q --local <the checkout that runs the harness> <d>/repo`.
2. Apply the substitutions (each old text exactly once) or the AST mutation.
3. Run `py_compile`.
4. Run `git -C <d>/repo commit -qam <id>`, with a fixed invented committer identity given by `-c` options.
5. **The clean-HEAD check.** `git -C <d>/repo status --porcelain --untracked-files=no` must be empty and
   `git -C <d>/repo rev-parse HEAD` must be the commit of step 4. Otherwise the verdict is HARNESS_ERROR and nothing
   runs.
6. Run `run_tests.py --work <d>/work --jobs 1 --only <killing names>`, with a timeout of 3 times the baseline time of
   that killing set.

**The verdict.**
- KILLED: the run exits 1, the failed list is non-empty, and at least one failure carries no `bootstrap_stop` field.
  A failure with `bootstrap_stop` means the World's own bootstrap stopped, which says nothing about the mutant.
- TIMEOUT: the run passed its timeout. It is recorded with the test that was running, and counts as killed only when
  that test is named in the record.
- SURVIVED: the run exits 0, or every failure carries `bootstrap_stop`.
- HARNESS_ERROR: step 2, 3 or 5 failed.

There is no text filter on failure details. A test that asserts SESSION_COMMIT_MISMATCH or SESSION_REPO_DIRTY (the
v1r session_start tests, W13's and W24's tests) kills its mutant like any other.

**Other rules.**
- The harness refuses to start unless its own checkout is clean (`git status --porcelain --untracked-files=no` empty),
  which `bin/testclone.sh` guarantees. `shutil.copytree` is deleted.
- The baseline clone first runs the union of the killing tests, unmutated. For guard mutants the baseline runs on the
  `ast.unparse` form of the target modules, unmutated.
- Guard runs use a ThreadPool of `--jobs` workers (4 on the review machine).
- `--selftest` runs W45a (expects HARNESS_ERROR), W45b (expects G31's reset failures to carry
  `bootstrap_stop: SESSION_REPO_DIRTY` and G31 not KILLED), W13 (expects KILLED) and the generator selftest of
  §2.15.2.
- W38 and W39 are in mutants.py with the repo-relative path `deploy/make_kit.py`. Their killing names are the v1r hooks
  `test_mk1_header_slip_in_one_copy_recovers` and `test_mk2_duplicate_binary_names_refused`, which run the mk tests.
- `run_tests.py --only` with any unknown name exits 2 and lists it (T11). The known names are every suite, test,
  scenario and special, every `CONFIGS` key of test_resets (`plan_groups` accepts `--only D`), and the group `nonroot`
  (§2.16.4).
- **Non-root mutants (D16, SD-71).** A mutant marked `nonroot` (W106, W107) builds its clone in a folder that uid 1000
  can reach, gives the clone and the work folder to that uid after the clean-HEAD check of step 5, and runs step 6
  under the `setpriv` line of §2.16.4 with `--require-nonroot`. It never runs as root, where it would survive by
  construction. MUTANTS_RESULTS.json records the uid and the effective capabilities of the run.

#### 2.15.5 New and changed tests, by suite (names as in §1.2 and §2.15.1)

**ct**
- T1-T5 and T10.
- MAINT-1 (two; the job_dir test has one case per row T10-T13 and the everyday branch), MAINT-3 (fold).
- INT-R2-04.
- SD-51 (`test_session_c2_clear_restore_keeps_kit_then_clear_takes_it`).
- D5: `test_d5_cleared_local_only_on_restore_and_genesis`. D6: `test_d6_entry_approval_must_be_none`.
- GUARD_TESTS.
- The T35/T36 tests are removed.
- `test_session_c2_clear_rebase_conflict_head_error` asserts the kept kit.

**cm**
- T7.
- MAINT-7 (names).
- INT-R2-03 (fold).
- D5: `test_d5_clear_verdict_exact_clear_and_config_only` (each reason: sha, members, clear, config; a null clear; a
  halted kit that is not in `kits`), `test_d5_clearing_restore_refuses_release_change`.
- D6: `test_d6_approval_asked_before_restore_and_genesis`, `test_d6_approval_before_head`.
- D3 (`test_d3_head_search_ignores_void_lookups`).
- `test_op05_recheck_after_every_q_restore`, `test_gap13_c8b_after_second_restore_abandons`.

**vio**
- S-01, S-03, S-04, S-05, S-07 (the planted `.pyc` files), S-09.
- OPX-01, OPX-02, OPX-03, OPX-05 (three), OPX-07, OPX-09.
- T6, T8, T9.
- D3: `t_d3_fourth_slip_stops_slip_limit`, `t_d3_refusals_bounded_then_slip_limit`, `t_d3_refused_count_resets_per_block`.
- D4: `t_d4_parse_raw_rules` (pure cases for every RAW_INVALID detail, the next-page token, the exact title, a `files`
  element without the name, one id with two sizes), `t_d4_found_raw_search_and_listing_objects`,
  `t_d4_raw_invalid_reasked`, `t_d4_swapped_elements_assigned_by_title`, `t_op03_raw_file_consumed`.
- Reprints: `t_op02_reprint_has_no_upload_lines`.
- D5: `t_d5_placement_accepts_equal_or_moves_aside`; `t_d5_refused_clear_kit_keeps_cache` (a kit whose `clear` names
  another seq, a null clear, and the original kit after SETUP_FAILED: each gives the original STOP with STATE.json,
  PENDING.json and RESTORE_WORK byte-identical, HALT.json present with its code, and the next `go` prints the same STOP
  with zero Drive calls); `t_d5_post_action_halt_cleared_same_boot` (POST_ACTION_FAILED and EVICT_MISMATCH);
  `t_d5_stale_hint_never_checks`; `t_d5_kit_in_use_never_checks` (a restore whose hinted kit is not on Drive takes a
  release kit other than the journal's by the manifest route and stops after its head is verified; a bootstrap with that
  release kit then prints the STOP with no FIND); `t_d5_halted_kit_never_checks` (a restore that takes a kit change
  stops in its RESTORE's commit loop, and its STOP header names the journal's kit; a bootstrap with the journal's kit
  then prints the STOP with no FIND); `t_d5_damaged_halt_stops_unclassified` (a HALT.json with a wrong `self_sha256`:
  `STOP UNCLASSIFIED`, HALT.json rewritten with that code and the old file under `halt_<utc14>.json`);
  `t_d5_found_answer_while_halted_print_stop`; `t_d5_clear_check_found_accepted`; `t_d5_clear_check_bounded` (four
  DOWNLOAD_MISSING slips in one check: the fourth adds the kit to `tried` and prints H's STOP with its code unchanged,
  STATE.json byte-identical); `t_d5_halted_restore_no_cleared_local`; `t_d5_wait_approval_in_clearing_restore` (after
  the clear, `approval=pending` gives `STOP WAIT_APPROVAL HANDBACK A` with no HALT.json written, and the next `go` asks
  `approval=` again, then prints the head search's first FIND).
- D16: `t_d16_settle_moves_readonly_target_aside` (a target with 0555 directories and 0444 files whose walk differs
  from the staged tree is moved aside and the staged tree is placed; `remove_tree` of a 0555 tree leaves nothing;
  decides in the non-root pass); `t_d16_stage_refuses_low_space_before_runner` (with `shutil.disk_usage` patched to
  one byte below `STAGE_FREE_BYTES` plus the margin: `STOP DISK_FULL` with step `stage`, no FOREGROUND.json, and the
  runner is never called; at exactly that value the stage runs). The fixtures of `t_d4_parse_raw_rules` and
  `t_d4_found_raw_search_and_listing_objects` start with the M007 envelope (§2.16.2).
- Gaps: `t_gap02_files_found_before_settle`, `t_gap04_moved_pending_foreign_copy_forks`,
  `t_gap05_block_ahead_invalidates_cache` (a STATE rolled back one head behind BLOCK: `invalid_<utc14>/`, then a
  restore), `t_gap08_clear_moves_attest_and_inbox` (a final_message.txt left from before the clear is not accepted:
  `REFUSED FINAL_MESSAGE_INVALID missing`), `t_gap08_render_removes_stale_download_target` (a file planted at a
  DOWNLOAD target is not taken as the download), `t_gap12_halt_removed_out_of_procedure_restores`.
- MAINT-2 (five).
- INT-R2-03 (worker argv).

**cod**
- S-06, S-11, OPX-06.

**v1r**
- S-08, OPX-08.
- OPX-10: `test_opx10_tool_calls_match_budget_golden`, with World extras `x_opx10` (per run, on the D baseline; per
  item and per series, on Q_baseline) and `x_op07_restore`. Each measured count must equal `tests/budget_golden.json`,
  a reviewed golden like the table golden.
- `test_f1` replaced (T1).
- The MK-1 and MK-2 hooks run the new make_kit tests.
- `x_op07` and `x_op08` are kept.
- `test_gap11_session_start_removes_pycache`.
- D16: `test_d16_evict_runner_frozen_folder_nonroot` (a World runs one invented run to FROZEN with the real runner; the
  test asserts that the frozen folder holds a directory without the owner write bit, and if the runner left none it
  sets the folder's directories to 0555 itself and records that; the EVICT post action then removes the folder, and the
  test asserts it is gone; it decides in the non-root pass). `test_d16_disk_bounded_over_runs` (World extra
  `x_d16_disk` on D_baseline, which runs several runs in a row; §2.16.5).

**lint**
- L13 (launcher).
- L14 (README rules). It checks verbatim: the outcome rule of section 4 with its identification sentence, the
  run-order sentence of 2.2, the NO_BLOCK sentence of section 2, the "never repeat an upload" sentence, the transient
  tool error sentence, the notes sentences of the UPLOAD_REFUSED and WAIT_APPROVAL rows and of 3.1, the sentence "If
  you are not sure whether the platform refused an upload or failed, treat it as refused.", the RAW_INVALID table of
  3.2, the empty-final-message sentence, the attested-times sentence of section 4 (OPX-09 e), the INPUTS_CHANGED
  step of 2.3, and (D16) the DOWNLOAD sentence and the raw-save sentence of section 2 and the never-work-around
  sentence of 3.1. It checks that `STOP IDLE`, `then=` and `AWAIT_CONVERSATION` are absent, and that the section 7 columns
  for helper commands, Drive calls and saved search results equal `tests/budget_golden.json`.
- L15 (guards).
- `t_only_unknown_name_exits_2`.
- L1 updated for the new codes, and L6 for the new README tokens.

**rs**
- D6: `D_refuse_reset_approval_pending`, `D_refuse_reset_approval_wrong_none`,
  `D_hint_restore_late_copy_at_n1_forks_at_recheck` (§2.5).
- D5: `D_clear_same_boot_setup_failed`, `D_clear_same_boot_foreground_died`, `D_clear_same_boot_fork`,
  `D_clear_same_boot_fork_foreign_only` (only a foreign copy at the moved PENDING's seq: FORK again),
  `D_clear_same_boot_open_generator` (a G answer refused four times, SLIP_LIMIT, the clear; FakeDot's outcome policy
  is NOTHING_WRITTEN, but files_found is true, so `outcome` is never asked, `forced` is FILES_FOUND and the run freezes
  T47 FREEZE_LOST; under W76 the outcome would be asked and give T44 INTERRUPT), `D_clear_committed_halt_same_boot`,
  `D_sameboot_damaged_cache_restores`. Every `D_clear_same_boot_*` scenario drives the check's FIND and DOWNLOAD and
  then at least one `found` and one `answer` of the restore after the clear.
- Slips: `D_slip_wrong_id_refinds`, `D_slip_size_refinds`, `D_slip_short_download_refinds`,
  `D_slip_limit_then_clear`, `D_slip_stale_raw_head_search` (a stale raw path in a hint head search is refused; no
  RESTORE is committed at an existing seq).
- `E_inputs_lost_after_reset_bounded`: lost inputs, three refusals, SLIP_LIMIT, the clear, and the job abandoned (C8b).
- **The special `test_foreground_died_same_boot_stops`** (S-12, TG-05):
  1. `subprocess.Popen` of `vm2.py go` in the world's environment, with `start_new_session=True`.
  2. After the `CPSV-RUNNING kind=chain` line, the test asserts that FOREGROUND.json exists, then sends
     `os.killpg(pgid, SIGKILL)`. If the process exited before the kill, the test fails; it never passes on a race.
  3. It asserts `returncode == -9`.
  4. The next `go` prints `STOP FOREGROUND_DIED` with the real head and kit in the header; STATE.json is kept; the job
     folder is byte-identical to the moment of the kill; and no `.cps_vm_stage_*` or `.tmp_*` leftover remains where
     `cleanup_leftovers` removes them.
  5. The test continues on that real-kill state: the World plants a clear kit for `{series, head_seq, FOREGROUND_DIED}`,
     runs the bootstrap with it and `go`. The check prints the kit's FIND and DOWNLOAD blocks, the clear moves the
     cache, `settle` moves the killed job folder aside (`aside_<utc14>/`), and the RESTORE records `cleared_local`.
  W58 survives every in-process Kill scenario and is killed here.
- The oracles "one END_CONVERSATION per open role per boot" and "no UPLOAD line after a REFUSED line".

**mt and mk**
- MAINT-1 to MAINT-10, as in §1.2; `test_gap06_audit_lists_approvals_and_same_boot_restores`;
  `test_gap10_generation_record_tied_to_g_entry`.

#### 2.15.6 Proof tables for the build report (TG-09)

**1. The reviewer mutants.** One row each for N04, N05, N06, N07, N18, N37, N40, N42, N44, N50 and N52, with three
columns:
- the new test passes at 2015773;
- it fails at 2015773 with the original substitution of `admission_r2/tests/scripts/my_mutants.py` applied;
- it fails at v2.1 with T's port applied.

A row with any column not as stated means the port is not the same rule, and the build report says why.

**2. Tests run directly at 2015773,** each with its expected failure there:
- mt: `test_maint1_audit_refuses_hostile_new_run` (the audit is clean); `test_maint1_forged_all_frozen_job_dir`,
  `test_maint1_assemble_base_from_genesis`, `test_maint1_wrong_mapping_refused`,
  `test_maint1_self_consistent_hostile_base_confined` and `test_maint1_symlink_after_begin_refused` (assemble writes
  the hostile paths; the root is `/` by default);
  `test_maint1_assemble_root_required_empty_dedicated` (no `--root` is accepted); `test_maint3_*` (the audit is clean);
  `test_maint4_audit_only_kit_change_verdicts` (clean); `test_maint5_*` (build accepts); `test_maint7_*` (folder rows
  refused); `test_maint8_*` (check trusts the plan); `test_maint9_*` (the window has no tolerance); `test_maint10_*`
  (the jobs are not compared);
- mk: `test_member_path_slip_in_one_copy_recovers` (`the copies disagree`), `test_pack_refuses_duplicate_binary_names`
  (pack accepts);
- cod: `test_s06_*` (the brace folder is accepted), `test_s11_*` (no block is printed);
- v1r: `test_s08_*` (the setup marker is written before the HEAD check), `test_opx08_*` (`--kit none` is a usage
  error), `test_gap11_*` (the planted `__pycache__` remains);
- lint: `t_only_unknown_name_exits_2` (exit 0 with 0 tests);
- ct and cm: `test_t1_*` to `test_t10_*` where the 2015773 fixtures allow; these pass at 2015773 and appear in table 1.

**D16 rows correct at 2015773.** `test_d16_evict_runner_frozen_folder_nonroot` and `test_d16_disk_bounded_over_runs`
pass at 2015773, which evicts with `make_writable_tree` and drops its local files. Like T1-T10 they are proven by
their mutants (W106; W109, W110), in two columns: the test passes at 2015773 (as root, since 2015773 has no non-root
pass); it fails at v2.1 with its mutant applied (W106 in the non-root pass).

**3. T1's cases.** `test_t1_continued_v_other_outcomes_t48` feeds the fold (not `build_item`) a RESTORE whose item is
a CONTINUED V with outcome NOTHING_WRITTEN, WRITTEN, UNSURE and NO_CONVERSATION, each once with a START and once
without one. All eight are T48 (CHAIN_INVALID). The control, outcome CONTINUED, is T46.

### 2.16 D16: platform facts from probe M007

The operator answered probe M007 on its own VM on 2026-11-11, with invented data only. The maintainer verified the
facts F1-F8 against the files the operator uploaded. D16 carries them into this plan. Nothing in §2.1-§2.15 changes
except where this section, §3 and §5.4 say so. The runner's finish stage is not split or changed: the runner is
admitted and byte-identical.

#### 2.16.1 Downloads (F3)

The route the Dot used is byte-exact (sha256 equal). The Drive fetch tool, with `download_raw_file` true and
`include_base64` false, returns a file reference, not base64. The platform's download tool then saves the original
bytes as a local attachment file and returns its path and size. The Dot copies that file with `cp` to the target path.
Nothing is retyped or decoded.
- README §2 describes every DOWNLOAD this way, in plain words (§3). r4's sentence "never copy a local file there
  instead" is replaced, because copying the downloaded file is the route; the new sentence forbids any other file at
  that path.
- The check stays the helper's: at the `go` after a DOWNLOAD block it computes the size and sha256 of the file at the
  target (rule V, §2.1; slips, §2.2.1). `render` still removes any file at a target before it prints (§2.10.5), so a
  file there is the Dot's copy of this block's download.
- FakeDot follows the route (§2.14). Lint L14 checks the sentence (W104).

#### 2.16.2 Saved tool results (F4)

The Dot serializes a tool's returned object with `JSON.stringify` inside its orchestration code and writes the text to
the VM file with a Python heredoc. It reports that the same works for search, upload and folder-listing results. The
saved search object is exactly the M004 envelope (§2.3). D4's parse rules need no change; D16 changes the tests:
- the first fixture of `t_d4_parse_raw_rules` and of `t_d4_found_raw_search_and_listing_objects` is an envelope with
  the exact key set the Dot saved (§2.3), invented values, `size` a decimal string, `viewedByMeTime` null, serialized
  compactly as `JSON.stringify` writes it; next to it, an empty search envelope for an absent name
  (`"structuredContent": {"results": []}`), and the same empty search saved as the structuredContent alone;
- FakeDrive's `raw_find` entries carry every key, and FakeDot writes the compact form (§2.14);
- README §2 says how to save (serialize each returned object unchanged and write that text), checked by L14.

OQ-21 is narrowed: the route is known. Whether a save costs a tool call of its own depends on whether the Dot's
orchestration code runs the search and the save in one call; README §7 keeps one call per save until G-3 measures it.

#### 2.16.3 Uploads stay inside the owner's standing approval (F5)

M007: the platform's automatic review refused an upload that the message's step list asked for, because the message's
final list of files to upload did not name it ("outside the authorized payload"). After the owner approved it, it
succeeded. So every UPLOAD line the helper prints must be inside the owner's standing approval. The helper's uploads
(the code at 2015773 plus MAINT-7):

| what | folder | when |
|---|---|---|
| journal entries and PNG parts of a qualification series | `CPS/qualification` | every commit |
| journal entries and PNG parts of a drill series | `CPS/drills/D<n>` (MAINT-7, SD-45) | every drill commit |
| the setup log after SETUP_FAILED | `CPS/reports` | rare |
| `SELFTEST_<fp>.json` and `FINGERPRINT_PASS_<fp>.json` | `CPS/setup` | once per new fingerprint |
| everyday journal entries and parts; the personal copy's log | the everyday records folder (`FOLDERS['E']`); the profile's `deliveries` folder | everyday only |

Every one is a new file: a name is uploaded only at a new seq, or after its loop's FIND showed it absent (§X.5.6), and
never from a reprint (SD-60). The owner's pending decision (new files only, into `CPS/qualification/` and
`CPS/reports/` and their subfolders; the Synology document limits do not apply to these Drive uploads) covers the first
and third rows. It does not cover `CPS/drills/`, `CPS/setup/` or the everyday folders. G-10 names the full list as its
precondition, and OQ-26 asks the owner. This plan keeps SD-45 and moves no folder: the PASS files must stay in
`CPS/setup/`, where the session FINDs them, so the approval has to name a folder outside the pending pair anyway.

A refused upload takes the existing path, which D16 does not change: `--refused`, `STOP UPLOAD_REFUSED HANDBACK A
name=<name>`, the owner approves or denies, `go`, a FIND before any re-upload, at most three uploads, then
UPLOAD_FAILED (README §3.1). README §3.1 adds one sentence: the Dot never works around a refusal and waits for the
owner (L14, W105). G-4 and G-5 need a refusal although G-10 comes first, so each provokes one on purpose (§1.3).

#### 2.16.4 Read-only trees and the non-root pass (F6)

M007: the Dot runs as uid 1000, not root. A plain `rm -rf` of the runner suite's work folder failed with "Permission
denied" on read-only fixture directories (frozen job folders) and worked only after `chmod u+w` on the directories.
The helper removes trees only through `remove_tree`, which calls `make_writable_tree` first (EVICT, the staging
removal, every other removal), but every helper test so far ran as root, which ignores permission bits. A probe on the
maintainer machine as uid 1000 without capabilities, on invented files, shows two failures for a tree with 0555
directories: `shutil.rmtree` fails with EACCES, and so does `os.rename` of a 0555 directory to **another** parent
(Linux needs write permission on a moved directory to update its `..` entry); a rename within the same parent works.

- **SD-70.** `place.settle` moves a target aside by renaming it to another parent (`outbox/v2/aside_<utc14>/<n>/`), and
  the target can be a tree the runner froze. Before that rename, `settle` sets the owner write bit on the target's top
  directory (one `os.chmod`; the aside copy is evidence, and only its top directory's write bit changes). The staged
  tree's rename into place stays within one parent and needs nothing. Every other helper move (`invalidate`, the clear,
  `foreground_check`) moves files and folders the helper made itself, which are writable.
- **SD-71, the non-root pass.** T builds it; the integrator runs it.
  - `run_tests.py --require-nonroot` exits 2 unless `os.getuid() != 0` and the effective capability set in
    `/proc/self/status` (`CapEff`) is zero. TEST_RESULTS.json records `uid` and `cap_eff` for every run.
  - The group `nonroot` names: `test_core_table`, `test_core_more`, `test_core_props`, `test_codes`, `test_vio`; the
    v1r tests `test_d16_evict_runner_frozen_folder_nonroot` and `test_d16_disk_bounded_over_runs`; and the reset
    scenarios that freeze, evict, place or settle a job folder with the real runner: `D_baseline`, `E_baseline`,
    `D_clear_same_boot_foreground_died`, `D_sameboot_damaged_cache_restores` and the special
    `test_foreground_died_same_boot_stops`.
  - The integrator makes a folder that uid 1000 can reach (its parents must not be root-only), runs
    `bin/testclone.sh <folder>/tc` in it, gives the folder to the uid (`chown -R 1000:1000 <folder>`), and runs
    `setpriv --reuid=1000 --regid=1000 --clear-groups --inh-caps=-all --bounding-set=-all python3 -I -B
    <folder>/tc/deploy/vm2/tests/run_tests.py --work <folder>/work --jobs 4 --only nonroot --require-nonroot`.
    The clone belongs to the uid, so git in the clone accepts it. The folder is deleted afterwards.
  - The integrator records the pass's counts (passed, failed, names, uid, `cap_eff`) in INTEGRATION.json next to the
    root suite's, and keeps its TEST_RESULTS.json. The pass runs in wave 3 after the full suite; its time is outside the
    full suite's D14 budget (§5.2).
  - Tests and mutants: vio `t_d16_settle_moves_readonly_target_aside`, v1r
    `test_d16_evict_runner_frozen_folder_nonroot` (§2.15.5); W106 removes the `make_writable_tree` call from
    `remove_tree`, W107 the chmod of SD-70. Both are `nonroot` mutants (§2.15.4), killed in the non-root pass.

#### 2.16.5 Disk (F7)

§5.4 states the budget against the Dot's 2.5 GB free. Two changes follow from it:
- **SD-69.** At 2015773 three space checks run: before the snapshot (1.1 times the job tree), before the commit (1.1
  times the members plus the PNG files) and before the download-back (1.1 times the copies). Together they cover a
  finish stage's commit, the tree plus its PNG parts. Nothing checks before the runner writes the stage's PNG pages and
  PDF, so a full disk there would fail inside the runner and could be recorded as a failed stage. `cli.run_stage` now
  calls `require_space(env.lay, N.STAGE_FREE_BYTES, 'stage')` for every chain before it writes FOREGROUND.json, with
  `STAGE_FREE_BYTES = 1000000000`: one large run's tree (about 270 MB), its PNG parts in `outbox/journal` (about 230
  MB) and their download-back in `inbox/verify` (about 230 MB), with room to spare. A refusal is the existing local
  sticky `STOP DISK_FULL` (§2.4.7, VM environment) before the runner starts. Test vio
  `t_d16_stage_refuses_low_space_before_runner`; mutant W108.
- **The retention test.** No existing test asserts that earlier runs leave nothing behind: test_resets' final and
  common checks cover the dispositions, the audit and assemble, and vio `t_evict_frozen_folder` evicts one folder.
  v1r `test_d16_disk_bounded_over_runs` therefore runs the World extra `x_d16_disk` on D_baseline, which runs several
  runs in a row. From FakeDot's per-block records (§2.14) it asserts that at no block more than two run job folders
  exist; that a run's job folder is gone once its FROZEN entry is confirmed and its EVICT post action has run; that no
  entry or part file of a confirmed seq remains in `outbox/journal` or `inbox/journal` after its DROP_LOCAL; and that at
  FINAL, before BASE is wiped, none of these remains. Mutants W109 (DROP_LOCAL removes nothing) and W110 (EVICT leaves
  the folder).

#### 2.16.6 Stage time (F1, F2) and resets (F8)

No helper code changes. §5.4 gives the measurements, the projection and the rule that G-3 follows before
`stage_max_seconds` is set; §6.2 (OQ-25, OQ-27) and §6.3 give the open questions and risks.

---

## 3. README v2.1 (exact operator text)

C replaces `deploy/vm2/README.md` with the text between the `~~~~` lines. The bootstrap block keeps its markers and its
lines, which FakeDot executes. Every `<...>` token is in the doc_samples list (lint L6) or starts with `<the `.

~~~~markdown
# cps-vm-helper.v2.1: the Dot's procedure

This page is for the Dot, the operator of CPS jobs on the VM. The helper prints one block at a time. You do exactly
what the block says, then run what its last line says. You never decide anything about the journal yourself.

Specification: `docs/handoff/VM_HELPER_V2_SPEC.md`, changed by `docs/handoff/VM_HELPER_V2_SPEC_DELTA_PROBES.md` and
`docs/handoff/VM_HELPER_V21_DELTA.md`.

## 1. After a reset, or in a new operator chat

After a reset `/home/agent` is empty. Restore the repository at the release commit, then start the session. Run
these lines exactly. `COMMIT` is the 40-hex commit of your last `CPSV-REPO` line. With a hint, also pass the `head`
and `kit` values of your last `CPSV` line. When that `kit` value is `none`, leave out `--hint` and `--kit`
(`--kit none` also means no hint).

<!-- bootstrap:begin -->
```
COMMIT=<the 40-hex commit of your last CPSV-REPO line>
[ -d ~/cps/repo/.git ] || git clone -q https://github.com/cookielolalex/CPS.git ~/cps/repo
git -C ~/cps/repo fetch -q origin "$COMMIT"; git -C ~/cps/repo checkout -q --detach "$COMMIT"
bash ~/cps/repo/deploy/vm2/session_start.sh --commit "$COMMIT" [--hint <seq6> --kit <hex12>]
```
<!-- bootstrap:end -->

- **Step 0, when your notes are gone.** Find `VM2_RELEASE.md` in the folder `CPS` by exact name and download it.
  Its one line `commit: <40 hex>` gives `COMMIT`. If the file is not there, stop and tell the owner
  `SESSION_NO_COMMIT` (case C). Never guess a commit.
- If the checkout fails after a partial clone, remove `~/cps/repo` (it holds no state) and run the three git lines
  once more. A second failure: stop and tell the owner `SESSION_GIT_ERROR` (case C).
- `session_start.sh` prints `CPSV-REPO commit=<40 hex>`. Keep that line in your notes together with the last `CPSV`
  line you saw.
- When a maintainer message gives you a bootstrap line (for example with a new `--kit` value to clear a stop, section
  6), run exactly that line instead, then run `go`.

## 2. The rule

Run `bash /home/agent/cps/vm.sh go`, then do the block it prints, exactly. Every block is:

```
CPSV series=<S> head=<seq6> kit=<hex12|none> at=<at> mode=<mode> state=<STATE>
UPLOAD <abs> TO <folder> AS <name>        (0..n, in order)
FIND <folder> NAME <name>                 (0..n)
DOWNLOAD <folder> ID <id> TO <abs>        (0..n)
DO: <exactly one action>
```

**Run every helper command in the foreground.** If the command tool gives you back a session before the command has
exited, poll that same session each time the tool returns, until the process exits, and start no other helper command
meanwhile. A command may run up to 1,200 s (a `go` that runs a stage first prints one line
`CPSV-RUNNING kind=<kind> since=<UTC> max=<s>`). The result of a command is its last block: from the last line that
starts with `CPSV ` through the `DO:` line, which is always the last line. If the process exited and its output has no
`CPSV ` line, or no `DO:` line after the last `CPSV ` line, run `go` once; if that happens again, stop and tell the
owner `NO_BLOCK` (case C).

A refusal (exit 4) adds one line `REFUSED <CODE>` right after the header, sometimes followed by the key or the file
name it is about. Your last answer was not used. Do the block that follows the REFUSED line: usually it is the block
you had before (correct your answer and run it again); after a failed download it is a FIND block for that file
(section 3.2). After a REFUSED line, never repeat an upload: redo only the FIND lines (if your saved result was wrong)
and the command. Keep the last `CPSV` line in your notes. Exit codes: 0 follow the block, 3 the block ends in
`DO: STOP`, 4 refused, 2 usage.

Do the UPLOAD lines first, in order, each **once**, the first time you see them (never retry an upload yourself). A
block that the helper prints again, after a REFUSED line or because you ran `go` before the command it asks for, has
no UPLOAD lines. Then do every FIND line, whatever the upload returned, then every DOWNLOAD line. If a DOWNLOAD or FIND
returns a tool error or times out, run that line once more before you run the helper. A FIND by NAME is an exact-name
search in that folder; when a search says it has more pages, fetch them all.

**Save what the search tool returns, never retype it.** For each block, write what its FIND lines returned into a
**new** file, for example `/home/agent/cps/attest/raw_0001.json`, then run the block's
`found --at <at> --raw <the path of that file>`. Serialize each returned object unchanged (for example with
`JSON.stringify` in your orchestration code) and write that text to the file (for example with a Python heredoc).
The helper moves the file away once it has read it, so a path is used only once. The file holds:
- for a block with one FIND line: the object that search returned, `<the object>`, or a list of it, `[<the object>]`;
- for a block with two FIND lines: a list of the two objects, in the order of the FIND lines,
  `[<the object of the first FIND>, <the object of the second FIND>]`;
- for a FIND whose search had two pages: a list of its pages in place of its object, for example
  `[[<the first page>, <the second page>]]` for a block with that one FIND line.

When the platform refused an upload of the block, add `--refused <name>` for that file (section 3.1). Only if you
cannot save a returned object, use the manual form: `found --at <at>` followed by, for every FIND line in order,
`--name <name>` and either one `--file <id>:<size>` per copy the search showed (the size in bytes exactly as shown) or
`--none`. For each DOWNLOAD line, download the raw file with that id (the Drive fetch tool with `download_raw_file`
true and `include_base64` false, then the platform's download tool, which saves the original file and tells you its
path and size), then copy that downloaded file with `cp` to exactly the path the line names (its folder exists). Never
retype a file, never decode base64 by hand, and never put any other file at that path; the helper checks the size and
sha256 of what you copied. If the platform refuses a DOWNLOAD, do not run `go`: ask the owner to approve it, download
again, then run `go`. Never edit, rename or delete a file on Drive.

### 2.1 Two lines that are not blocks

- `CPSV-RUNNING kind=... since=... max=...` is printed first by a `go` that runs a stage (or by `session_start.sh`
  before the setup). It names no result. Keep polling the same command session until the process exits; the block
  follows it.
- A helper command that finds another one still running prints exactly three lines and exits 4, changing nothing:
  `CPSV-BUSY kind=... since=...`, `REFUSED HELPER_BUSY`, `DO: POLL`. Do what POLL says (section 3). Never start a
  second helper command while one runs.

### 2.2 Qualification and drill (series Q1, D1)

1. The maintainer gives you the commit and the kit (the `--hint 000000 --kit` value of the first session). Run the
   bootstrap of section 1, then `go`.
2. Follow every block. The helper runs the kit's job list in this order: first the cases without a source, as
   nonattempts, all of them for reader A and then all of them for reader B; then reader A for every other case in the
   list's order; then reader B for every case in the same order. A run that the helper restarts comes right after it.
   Each run goes through prepare, the generator conversation (and the scope reader for a large workbook), finish,
   the visual reviewer and freeze.
3. Every stage runs in the foreground of one `go` (up to 1,200 s; the finish stage takes minutes). Poll until it
   exits. Then the helper saves the result on Drive through its SAVE blocks (UPLOAD, FIND, `found`, DOWNLOAD, `go`);
   nothing that depends on a result is shown before it is saved.
4. When the owner must be told something (a stopped run), the block is `NOTIFY_OWNER`.
5. `STOP FINAL HANDBACK B` ends the series: tell the owner that qualification generation is complete.

### 2.3 Everyday jobs (series E1)

1. With no job running the block asks `case=CASE_ID`. Answer it only when a user asked for a job: first put the user's
   three files (`JOB.json`, `JOB_TITLE.json` and the source workbook it names) in
   `/home/agent/cps/everyday_inputs/<case>/`, then answer with that case id. Before you answer `case=`, keep the exact
   text of `JOB.json` and `JOB_TITLE.json` and the place of the user's workbook in your notes.
2. Follow the blocks through prepare, the generator, finish and the visual reviewer, exactly as in qualification.
3. Delivery: `DELIVER ... to=copy` (make the personal copy and its log, answer the two paths), then
   `DELIVER ... to=user` (send it, answer `sent=yes`). After a reset during a delivery you are asked whether the copy
   reached the user (`arrived=`); ask the user, never send a second copy on your own.
4. A failed job is never retried on your own: the block asks you to tell the user (`asked=yes`); a new job starts only
   at the user's request.
5. `REFUSED INPUTS_CHANGED`: the files in `everyday_inputs/<case>/` are not the ones the job saved (a reset empties
   that folder). Put the same three files back, unchanged, from your notes and the user's workbook, then run `go`. If
   you cannot (you no longer have them, or the user changed them), tell the owner the code and your last `CPSV` line,
   then run `go` until the helper stops with `STOP SLIP_LIMIT HANDBACK C` (it refuses at most 3 times). A maintainer
   clear of that stop abandons this job; a new job starts only at the user's request.

## 3. The actions (the `DO:` line)

| action | you do | then |
|---|---|---|
| `RUN bash /home/agent/cps/vm.sh go` | run it | follow the new block |
| `ATTEST ... found --at A --raw FILE [--refused NAME]` | do the block's UPLOAD and FIND lines, save the FIND results in one new file (section 2), run `found` with that file | follow the output |
| `ATTEST ... answer --at A k1=PATTERN1 ...` | run `answer` with a real value for each key, matching the pattern named | follow the output |
| `ATTEST after=T bash ... answer ...` | as above; `list_shows_none=yes` means your conversation list shows **no** conversation of that role (section 4) with `attachedAt` at or after T, and `conversation=` is the id of the conversation of that role with `attachedAt` at or after T | follow the output |
| `POLL` | another helper command still runs: go back to its session and poll it until it exits, then follow its block. If you no longer have that session, `WAIT seconds=60`, then run `go` | follow that block |
| `OPEN_CONVERSATION role=R prompt=P folder=F` | open a new conversation (Create Thread, same environment, no extra settings) and give it the full text of file P as its only message. Roles S and G may use only folder F. Role V may open only the PNG files the prompt lists (under F) and may write only `F/visual_review/VISUAL_REVIEW.json`. Never send it a follow-up message. Check it once every 5 minutes | when it has ended: write its final message to the file (section 4), run `go` |
| `CONTINUE_CONVERSATION role=V conversation=C message=M` | send the text of file M in conversation C (the only message you ever send into an existing conversation). Check it once every 5 minutes | when it has ended: write its final message to the file, run `go` |
| `END_CONVERSATION role=R after=UTC [conversation=C]` | stop the CPS conversation of that role opened after UTC, if it is still running | run `go` |
| `EXPORT_TRANSCRIPT role=R to=P [conversation=C] [after=UTC]` | export that conversation's transcript to P; if your platform cannot, do nothing | run `go` |
| `NOTIFY_OWNER file=P ATTEST ... notified=YES` | tell the owner the content of P | run the answer |
| `ASK_USER file=P ATTEST ... k=PATTERN` | ask the user the question in P | run the answer with the user's reply |
| `DELIVER file=P to=copy ATTEST ... copy=COPYPATH log=COPYPATH` | everyday: make the user's personal copy of P with that user's preferences, as `PERSONAL_COPY.xlsx` with its `PERSONALIZATION_LOG.json` in `~/cps-deliveries/<case>/<user>/<utc14>/` | run the answer with the two paths |
| `DELIVER file=P to=user ATTEST ... sent=YES` | everyday: send P to the requesting user, under the standard file name from the `JOB_TITLE.json` you wrote | run the answer |
| `WAIT seconds=N` | wait N seconds | run `go` |
| `STOP UPLOAD_REFUSED HANDBACK A name=N` | keep N in your notes as refused; tell the owner the code, the file name N and your last `CPSV` line, and ask the owner to approve or deny the upload in the platform | run `go` when the owner says so. Take N out of your notes only when the owner tells you the upload was approved or denied; if the owner only says to continue, keep N in your notes |
| `STOP WAIT_APPROVAL HANDBACK A` | an upload of this series still waits for the owner (you answered `approval=pending`): ask the owner to approve or deny it | run `go` when the owner says so. Take it out of your notes only when the owner tells you it was approved or denied; if the owner only says to continue, keep it and answer `approval=pending` again |
| `STOP <CODE> HANDBACK C` | stop; upload nothing more; tell the owner the code, your last `CPSV` line and, for `SLIP_LIMIT`, the last REFUSED line you saw | nothing until a maintainer message (section 6) |
| `STOP <CODE> HANDBACK B` | stop; tell the owner that qualification generation is complete | nothing |

Handback letters: **A** the owner must do something in the platform (approve or deny an upload), then you run `go`
and the series goes on; **B** the series is complete; **C** stop and wait for the maintainer (nothing more is
uploaded). `STOP ... HANDBACK A` is the only stop after which you run the helper again without a new message.

### 3.1 When the platform refuses an upload

The platform's automatic approval review sometimes refuses an upload, and a timed-out upload may still appear later.

1. Do every UPLOAD line once. Whatever an upload returned (success, timeout, error or refusal), do every FIND line of
   the block and save what the searches returned.
2. Add `--refused <name>` to `found` for an upload the platform refused (an approval review or any refusal message).
   If you are not sure whether the platform refused an upload or failed, treat it as refused. Never use `--refused`
   for a file the block did not ask you to upload (that is refused with `FOUND_SYNTAX`).
3. **Write every refused upload into your notes at once (the file name and the time), and keep it there until the
   owner tells you it was approved or denied.** Your notes survive a reset; the helper's files do not.
4. If the refused file is not found, the helper prints `DO: STOP UPLOAD_REFUSED HANDBACK A name=<name>`. Tell the
   owner the code, the file name and your last `CPSV` line, and ask the owner to approve or deny it in the platform.
   Do not upload it again yourself. Never work around a refused upload: do not upload the file under another name,
   into another folder, in pieces, with another tool or from another conversation; wait for the owner. Run `go` when
   the owner says so; take the name out of your notes only when the owner tells you the upload was approved or denied.
5. The next block FINDs the file first, never uploads at once (an approved upload may have landed). The helper
   uploads one file at most three times; after the third, it stops with `UPLOAD_FAILED HANDBACK C`.
6. A copy that appears late is a second copy; the helper downloads and checks it, and nothing else changes when it
   holds the same bytes.
7. **Every session asks `approval=`.** After a reset, after a maintainer clear and at the start of a series, the
   helper asks `approval=` before it searches the journal. Answer `approval=pending` if your notes still hold a
   refused upload of this series that the owner has not told you was approved or denied, otherwise `approval=none`.
   With `pending` it stops with `STOP WAIT_APPROVAL HANDBACK A`; when the owner has resolved it, run `go`: the helper
   asks again, then searches the journal.

### 3.2 When the helper asks again

- After `found` the helper downloads every copy it does not know yet. If a DOWNLOAD file is missing when you run `go`
  (`REFUSED DOWNLOAD_MISSING`), has another size than the one the search showed (`REFUSED DOWNLOAD_INCOMPLETE`), or is
  another file of the same save (`REFUSED COPY_MISMATCH`), the helper drops that answer and prints a FIND block for
  that file: search again, save the result to a new file, run `found` again.
- An answer it cannot use (a wrong key, a value that does not match its pattern, a missing final message file, a raw
  file it cannot read) is refused with the reason: correct it and run the command again. For a saved search result the
  reason is one word after `RAW_INVALID`:

  | after `RAW_INVALID` | what to do |
  |---|---|
  | `missing` | save the result to a new file and pass that path (the helper moves each file away once it has read it) |
  | `json` | the file is not one JSON value, or is over 1 MiB: save the returned objects again, unchanged |
  | `count` | put one element per FIND line, in the order of the FIND lines |
  | `shape` | save each object exactly as the search tool returned it |
  | `pages` | fetch every page of that search and put the pages in a list |
  | `error` | the tool returned an error: run that FIND again and save the new result |
  | `listing` | use the exact-name search of the FIND line, never a folder listing |
  | `entry` or `duplicate` | use the manual form of section 2 for this block |

- This happens at most 3 times for one save, one restore or one block. The fourth time is `STOP SLIP_LIMIT HANDBACK C`;
  while the helper checks a maintainer's kit (section 6), the fourth time prints your earlier STOP again instead.
- A copy with the size the search showed and other bytes than the helper's is a real second copy on Drive:
  `STOP FORK HANDBACK C`. The helper keeps the downloaded bytes for the maintainer.

## 4. What you are asked, and where

- **First `go` of a session:** `operator_model=MODEL platform=PLATFORM` (your own model id and platform).
- **In every session, before the helper searches the journal:** `approval=pending` or `approval=none`
  (section 3.1).
- **Times you attest** (`started_utc`, `ended_utc`) are VM clock readings: run `date -u +%Y-%m-%dT%H:%M:%SZ` on the VM
  just before you send the prompt, and again right after you see the conversation end, and answer the two readings
  exactly as printed. Never copy a time from the conversation list or from Drive.
- **Every conversation you open (S, G, V):** it gets the prompt file's text as its only message. Never send it a
  follow-up message, never answer its questions, never attach anything. When it has ended, write its final message
  exactly as it is (any characters, any length; never edit, shorten or summarize it) to
  `/home/agent/cps/attest/final_message.txt`, then run `go` and answer. If the conversation shows no final message,
  create the file empty. Write the message with your file-write tool; if you use the shell, use a quoted heredoc whose
  delimiter line does not occur in the message. After a review continuation, write its new final message the same way.
- **Tools** (`tools=` in the first answer about each conversation): answer `tools=inventory` when you created the
  conversation exactly as section 3 says (Create Thread, same environment, no extra settings); its tools are then the
  platform's usual set, which the kit lists. If you created it in any other way, or you know that its tools differ,
  save the list of tools you know it had, one name per line, to a file under `/home/agent/cps/attest/` and answer
  `tools=file:<the absolute path of that file>`. Never answer `none`: conversations on this platform always have tools.
- **A generator (G) conversation ended:** whether it ended, its conversation id, its start and end times, the
  generator's platform, model and effort, whether you sent a single message, the six features (memory, custom
  instructions, web, connectors, file uploads, other agents: `yes` or `no` as the platform shows them for that
  conversation; with the usual tools of this platform `web` and `connectors` are `yes`), the tools and the transcript
  status (always `not_available` on this platform).
- **A scope reader (S) conversation ended:** `ended=yes`, its conversation id, `prompt_pasted=yes`, the tools.
- **A visual reviewer (V) conversation ended:** `ended=yes`, its conversation id and the tools; after a continuation
  only `ended=yes`.
- **After a reset or a clear, for a conversation that was open:** whether it ended (`ended=yes` once you stopped it or
  saw it end), what it wrote (`outcome=`), the transcript status (always `not_available` on this platform: it cannot
  export a transcript with the files written), and sometimes whether your conversation list shows no conversation at or
  after the time given (`list_shows_none=`) and the conversation's id. Decide `outcome=` only from what you can see:
  your conversation list with each conversation's `attachedAt` time, that conversation's recorded messages and turn
  status, and, only if the VM was not reset, the files in its output folder. A conversation is this role's only when
  its first message is the full text of the role's prompt file; conversations whose first message is anything else
  (for example your mailbox checks) do not count. The readback never shows what a conversation wrote through its
  tools.
  - `NO_CONVERSATION`: your list shows no conversation of this role with `attachedAt` at or after the `after=` time.
    Answer `list_shows_none=yes` with it.
  - `NOTHING_WRITTEN`: exactly one conversation is this role's, its recorded messages hold your prompt and nothing from
    it, and its turn status shows that it failed or was cancelled before it began to run.
  - `WRITTEN`: it replied (any message from it after your prompt), or its turn status says it completed, or (the VM
    was not reset) its output folder holds any file.
  - `UNSURE`: anything else: a turn that ran, whatever its status now (also one you stopped yourself), more than one
    conversation that could be this role's, a status you cannot read, or doubt. When in doubt, answer `UNSURE`.

  A conversation that may have written something is never opened again: the run fails safely instead. In
  qualification, `NOTHING_WRITTEN` lets the helper restart that conversation once, and the owner checks it before
  scoring; in an everyday job it never restarts.
- **An owner notice:** `notified=yes` after you told the owner.
- **Everyday, idle:** `case=CASE_ID`, only when a user asked for a job and its three input files are in
  `/home/agent/cps/everyday_inputs/<case>/`.
- **Everyday delivery:** the two paths of the personal copy and its log, then `sent=yes` once you sent it.
- **Everyday, after a reset during a delivery:** `arrived=yes` or `arrived=no` (ask the user).
- **Everyday, after a failed job:** `asked=yes` once you told the user the job failed (a new job starts only at the
  user's request).

Give real values only. A value with a space, a quote, a brace, an angle bracket, `$`, a backslash or a non-ASCII
character is refused, and so is a key name, a pattern name or an example value from this page. The files you write for
the helper (the final message, a saved search result, a tool list) may hold any characters.

## 5. After a reset: what the helper does

The helper restores from the journal on Drive, never from your memory. It asks you `approval=` before it searches the
journal. Then it finds the newest journal entry by exact name (it asks you to FIND names one by one, waits, and FINDs some names twice),
downloads it, checks it, puts the job folders back, and asks you about any conversation that was open. It then saves a
RESTORE entry before anything else runs; in qualification and drills it then waits about a minute and FINDs the next
three names once more. A conversation that may have written something is never re-opened: the run fails safely
instead. Follow the blocks; never re-open a conversation on your own.

## 6. When the maintainer clears a stop

A `STOP <CODE> HANDBACK C` stays until the maintainer clears it. The maintainer's message gives you a bootstrap line
with a new `--kit` value. Run that line exactly, then `go`. The helper first finds and downloads the new kit (one FIND
block, one DOWNLOAD block) and checks that it names exactly your stop. If it does not, or if the kit cannot be found
or downloaded, it prints the same STOP again: tell the owner, and wait for the next message. If it does, it continues
from the journal as after a reset: answer its questions, `approval=` first. Do nothing else on the VM in between, and
never delete the helper's files. If the message asks the owner to remove a copy of a file from Drive, pass that on:
the owner deletes it for good in Drive (moves it to the trash, then deletes it from the trash) after the maintainer
has saved it; you never delete files on Drive.

## 7. How much work a run is

The helper's test harness counts the helper commands, Drive calls and saved search results on invented jobs; the
conversation steps are counted from this page (each is one tool call: `date -u`, creating the conversation, reading it
back, writing its final message to the file); the polls and checks come from the stage times and conversation lengths
measured on this VM. Poll a running helper command each time the command tool returns; check a running conversation
once every 5 minutes.

| item | helper commands | Drive calls | saved search results | conversation steps | polls and checks | tool calls in all |
|---|---|---|---|---|---|---|
| a normal run (prepare, generator, finish with p PNG parts, visual reviewer, freeze; p is 1 to 3) | 16 | 15 + 3p | 6 | about 10 | about 15 | about 65 to 71 |
| a scope reader in the run, or a review continuation | +6 | +6 | +2 | about +4 | about +3 | about +21 |
| a nonattempt | 2 | 3 | 1 | 0 | 0 | 6 |
| a restore after a reset, with your notes (with `approval=` and the re-check) | about 23 | 16 to 23 | about 9 | 0 to 2 | 1 | about 53 |
| a restore without your notes (about 400 journal entries) | about 50 | about 45 | about 23 | 0 to 2 | 1 | about 120 |
| a maintainer clear (the kit check, then a restore) | +2 | +2 | +1 | 0 | 0 | a restore + 5 |
| one refused upload | +2 | +3 | +1 | 0 | 0 | about +6, plus the owner's time |

A qualification (38 runs, 34 nonattempts, about 10 scope readers and continuations, about 10 restores, the start and
the end of the series) is about 3,600 tool calls: about 20 hours at 20 seconds per call, plus the conversations' own
time, the stages' running time and the owner's approval waits. This assumes that the owner has approved in advance
every upload the helper prints (new files into `CPS/qualification`, `CPS/drills`, `CPS/reports` and `CPS/setup`);
otherwise expect refused uploads on most days.

## 8. Example values (refused as answers)

Every example value printed on this page. The maintainer copies this list into the kit config (`doc_samples`); the
helper refuses each of them as an answer.

<!-- doc_samples:begin -->
```
<40 hex>
<S>
<at>
<exactly one action>
<hex12|none>
<the 40-hex commit of your last CPSV-REPO line>
<seq6>
<hex12>
<abs>
<folder>
<name>
<id>
<size>
<UTC>
<kind>
<s>
<mode>
<STATE>
<case>
<user>
<utc14>
<CODE>
```
<!-- doc_samples:end -->
~~~~

**Notes for C on the README.**
- **Section 7 numbers are estimates** (§5.3). Before review, C replaces the helper-command, Drive-call and
  saved-result counts with the values in `tests/budget_golden.json`, which `x_opx10` and `x_op07_restore` measure.
  The maintainer replaces the polls-and-checks column and the totals with the G-3 measurements before G-9. Lint L14
  compares the table with the golden file, never with constants in a test.
- **Paths that are not placeholders.** The example path `/home/agent/cps/attest/raw_0001.json` and the `tools=file:`
  paths may be used as written.
- **Absent text.** The page has no `then=`, no `AWAIT_CONVERSATION`, no `STOP IDLE`, no LIST line and no
  `opened_utc`.
- **The hold value (D16).** The two "1,200 s" in sections 2 and 2.2 are the release kit's `foreground_hold_seconds`.
  They stay 1,200 unless G-3 proves a longer hold (§5.4); C writes the kit's value before G-9.
- **Verbatim checks.** L14 checks the sentences that §2.15.5 lists.

---

## 4. Shared files and build order

1. **`core/names.py` CODES** is owned by C. M may add its own new names only by small `Edit` calls after re-reading
   the file, never by rewriting it. M's own result codes stay in `maint/*.py`, as today, where L1 collects them.
2. **`tests/fakes.py` and `tests/core_world.py`** are owned by C, which builds every harness feature of §2.14,
   including the `bootstrap_stop` field and the counts that feed the budget golden.
   - M adds its helpers inside `test_maint.py` (for example its kit-zip builders for MAINT-3 and MAINT-4, the hostile
     FINAL entries and the symlink hook of MAINT-1).
   - T adds helpers inside its own test files, as subclasses or wrappers.
   - Neither edits these two files. A missing feature is requested from C.
3. **`tests/table_golden.json` and `tests/budget_golden.json`** are owned by T. Each is regenerated after C's changes
   as a reviewed golden update, and the diff goes in the build report.
4. **`REUSE_MANIFEST.json`** is owned by C and regenerated for the remaining names. `test_reuse.py` is T's.
5. **`README.md`** is C's. L6 and L14 (T) read it, and T reports wording problems to C.
6. **This file** is the planner's; the builders do not edit it. Each track writes its own build report under
   `<scratch>/v21/<label>/keep/`.
7. **Interfaces C lands first** (wave 0), with the signatures given here, so that M and T can code against them:
   - fold: `fold.job_dir_of(base, tag, case)`, `fold.layout_of(base)`, `fold.jobs_of(jobs_doc)`, `fold.CONSUMER`,
     `fold.QUAL_ROOT`;
   - session: `session.clear_ok(clear, series, seq, code)`, `session.config_only_ok(from_kit, to_kit)`,
     `session.clear_verdict(halt, cand, kits)`, and `session.kit_change` with its signature unchanged;
   - names: `names.O63_NOTE`, `O63_NOTE_RE`, `O63_REPORT`, `names.tool_list(raw)`, `names.series_folder`, and the new
     CODES;
   - vio: `durable.write_doc` (in place), `vio.runner.load_runner` (compiled bytes) and `drive.parse_raw` (copies by
     title);
   - cli: `cli.invalidate(env, prefix)` and `cli.clear_check(env)` (names only; T's glue mutants target them).

   Until then M and T stub locally; nobody waits on a whole track.
8. **Order.**
   - Wave 0: C's interfaces.
   - Wave 1, in parallel: C (glue, savepoint, session phases, README, harness), M (maint, make_kit), T (core tests,
     GUARD_TESTS, the harness fix, T11).
   - After wave 1, T measures D_baseline and one E scenario under v2.1 and restates the test_resets estimate (§5.2)
     before the new scenarios are added.
   - Wave 2: T's world scenarios and mutants on C's code.
   - Wave 3: the full suite, then the non-root pass (D16, SD-71: T builds `--require-nonroot`, the `nonroot` group and
     the `nonroot` mutants; the integrator runs the pass as §2.16.4 says and records it), then the mutation runs.

   Every run uses a snapshot clone (`bin/testclone.sh`) and its own work folder, and each track deletes its clones
   afterwards.
9. **Edits.** No track edits a file another track owns. A shared file is re-read before every edit and edited by the
   smallest `Edit` that applies.

---

## 5. Budgets

### 5.1 Lines (D2)

**The measurement.** The baseline is `wc -l` at 2015773, per module, over `deploy/vm2/cpsvm2`, `vm2.py`,
`session_start.sh` and `probe_p5.py`: 8,396 in all. This plan reads D2 as follows: the total must not grow, and the
per-module counts are reported. MAINT-1, MAINT-5, MAINT-8 and O63 add code to fold and maint, so per-module
non-growth is not possible.

**The binding rules.**
1. The total must not exceed 8,396.
2. C's modules together must not exceed 7,500 (baseline 7,566).
3. M's modules together must not exceed 896 (baseline 830).
4. Every deletion of §2.13 is made.

The target total is at most 8,390. A module may exceed its expected value as long as its track total holds. The
builders report the after value of every module. r4 changes r3's expectations in a few modules: the clear check, the
moved-PENDING rule, `halt_local`, the BLOCK rule and the stale-download rule add to cli; the CLEAR phase, its 'fetch'
branch, the restart rule and the approval clearing, all planned in r3, are not built; `via` goes; assemble reads
GENESIS; the audit ties the generation record and lists approvals.

| module | track | baseline | expected v2.1 | main changes |
|---|---|---|---|---|
| cpsvm2/__init__.py | C | 6 | 6 | version |
| cpsvm2/cli.py | C | 1526 | 1513 | removes md5, LIST and OPENED answers, `sticky_halt`, the duplicate loops, the special renders and one of `ensure_text`/`ensure_copy`; adds `clear_check`, `invalidate` (with the boot-mark exception), slips, counted refusals, raw read and consumption, approval, tools, post resume, `halt_local`, the BLOCK rule, the moved-PENDING rule, the UNCLASSIFIED rewrite of a damaged HALT.json, HALT.json's head and kit in a STOP header |
| cpsvm2/core/entry.py | C | 248 | 251 | removes OPENED; adds approval, conversation, tools_present, the `cleared_local` kinds |
| cpsvm2/core/fold.py | C | 1073 | 1075 | removes OPENED (T35/T36, the no-list branches); adds job_dir_of, layout_of, jobs_of, the consumer rule, g59, e42, t01 |
| cpsvm2/core/names.py | C | 252 | 262 | adds codes, TOOLS, APPROVAL, the O63 texts, tool_list, BASE_RE; shortens utc_minus; removes LIST_NEWEST_K and MD5 |
| cpsvm2/core/outcome.py | C | 165 | 165 | adds conversation and tools on the sheet; removes OPENED windows |
| cpsvm2/core/plan.py | C | 316 | 306 | removes rows 5-7's `then=`, the OPENED question and AWAIT; adds tools keys; imports CONSUMER and ROOT |
| cpsvm2/core/session.py | C | 565 | 560 | removes listing, md5, `via` and work_sha; adds APPROVAL, clear_ok, config_only_ok, clear_verdict, void, the C2 kit, the clearing KIT_ACCEPT rule |
| cpsvm2/core/step.py | C | 86 | 77 | removes Evict, Wait and lists |
| cpsvm2/vio/drive.py | C | 197 | 210 | removes the md5 and LIST forms; adds parse_raw (by title), prints, `name=` |
| cpsvm2/vio/durable.py | C | 137 | 136 | write_doc in place |
| cpsvm2/vio/host.py | C | 202 | 195 | removes read_release and 2 gate keys; adds the tool inventory key and the list gate |
| cpsvm2/vio/place.py | C | 242 | 252 | settle |
| cpsvm2/vio/runner.py | C | 121 | 122 | compiled load |
| cpsvm2/vio/savepoint.py | C | 379 | 353 | removes `_Env1` and its wrappers, md5 and dead code; adds slip, the PNG compare, post carry |
| cpsvm2/vio/v1compat.py | C | 89 | 86 | removes Block.option |
| cpsvm2/vio/v1mod.py | C | 266 | 268 | place_frozen uses settle |
| cpsvm2/vio/v1reuse.py | C | 981 | 938 | removes 5 unused segments |
| cpsvm2/worker.py | C | 488 | 492 | tools, notes, the interrupt conversation, files_found before settle; removes OPENED |
| probe_p5.py | C | 134 | 136 | seconds >= min-gap |
| session_start.sh | C | 74 | 76 | S-08 order, kit none, the launcher flag, the `__pycache__` removal |
| vm2.py | C | 19 | 19 | |
| cpsvm2/maint/assemble.py | M | 243 | 264 | root, the GENESIS base, layout, confinement, verify_frozen |
| cpsvm2/maint/audit.py | M | 409 | 432 | removes its own loader and kit rules; adds clear, cleared_local, jobs, folders, tolerance, o63 and its ties, approvals |
| cpsvm2/maint/score_check.py | M | 178 | 196 | MAINT-5, MAINT-8, O63 |
| **C total** | | **7,566** | **7,498** | |
| **M total** | | **830** | **892** | |
| **total** | | **8,396** | **8,390** | |

**D16 (r5).** SD-69 and SD-70 add about three C lines: one in `cli.run_stage`, one constant in `names` and one chmod
in `place.settle`. They are paid from contingency deletion 2 below, so C's expected total stays 7,498 and its cap of
7,500 holds. The table above is r4's and is not restated.

**Contingency deletions**, pre-approved in this order if a track overruns:
1. any reused segment that L10 reports unused after the deletions;
2. module docstrings that restate r2 or the probe delta section by section (518 docstring lines exist at 2015773; the
   reused segments' docstrings are pinned and stay);
3. comments that name deleted features;
4. consolidating `cli.ensure_standard` with the merged `ensure_text`/`ensure_copy`.

No behaviour may be removed to meet a budget.

### 5.2 Test time (D14) and mutation runs

| run | budget (wall, `--jobs 4`, the review machine) | notes |
|---|---|---|
| non-reset suites (ct, cm, props, reuse, vio, maint, p5, cod, v1r) | <= 5 min | about 2.5 min at 2015773 |
| test_resets | <= 43 min | 197 scenarios took 47 min at 2015773 with `--jobs 3`; v2.1 removes 9 scenarios and adds 16 and a special (below); measured again after wave 1 (§4.8) |
| lints | <= 2 min | L4 coverage dominates |
| **full suite** | **<= 50 min, with a hard ceiling of 60 (D14)** | |
| hand, reviewer and builder mutants | <= 3 h | mutants that a reset scenario kills run only their named scenarios |
| guard mutants, core set (two stages) | <= 3.5 h | 743 sites at 2015773 under the r4 rule, about 735 expected; stage 1 took 22 s and stage 2 101 s per mutant at `--jobs 1` on the review machine; 4 workers |
| guard mutants, glue set (stage 2 only) | <= 1.5 h | about 200 sites expected (about 225 in the 2015773 forms of these functions) |
| the non-root pass (D16, SD-71) | <= 10 min | a second invocation after the full suite, outside its 50/60 min; the core suites, vio, two v1r tests and five reset runs (§2.16.4) |
| `nonroot` mutants W106, W107 | <= 15 min | each runs its killing set in the non-root pass |

**Per-mutant controls (TG-11).** Each mutant's timeout is 3 times the baseline time of its killing set; a timeout is
recorded with its test (§2.15.4). The specials already took 4,067 of 14,418 scenario-seconds at 2015773, so the
mutation runs list a special in a killing set only where §2.15.1 names it.

**Per-scenario costs that r4 adds.** Every session asks `approval=` (one answer). Every qualification and drill restore
runs the RECHECK: one WAIT, shortened in the harness to `W_ABS_TEST` = 2 s, and one FIND block. Every found saves a
raw file. After wave 1, T measures D_baseline and one E scenario under v2.1 and restates the test_resets estimate
before it adds the scenarios below.

**Reset scenarios removed (D14), with the coverage argument for each group:**
- `DL_OPENED1_a`, `DL_OPENED1_e`, `DL_AI1_a`, `DL_STAGE1_e`, `DL_baseline` and the DL config. OPENED is deleted
  (SD-37), so the plan rows and fold rows these scenarios exercised no longer exist.
- `DV_vis_foreign_md5_entry`, `DV_vis_lag2_parts`. md5-visible mode is deleted, and `D_vis_foreign_same_entry` and
  `D_vis_lag2_parts` run the same commit-loop code in the only mode left.
- `DV_notes_commit_only_gallop`, `D_head_listing_ghost`. The listing is deleted. `D_notes_commit_only_listing` is
  renamed `D_notes_commit_only_gallop`: without the listing it is the gallop plus RECHECK path.
  `test_t3_recheck_second_writer_at_n2_n3_forks` covers the RECHECK fork.

The DV config stays for the transcript-export variant: gates `{'p1_transcript_export': 'yes'}` only, with
`DV_ans_G0_*`, `DV_ans_V_nw_exported` and `DV_baseline`.

**Reset scenarios added** (about 80 CPU-s each):
- `D_refuse_reset_approval_pending`, `D_refuse_reset_approval_wrong_none`,
  `D_hint_restore_late_copy_at_n1_forks_at_recheck`;
- `D_clear_same_boot_setup_failed`, `D_clear_same_boot_foreground_died`, `D_clear_same_boot_fork`,
  `D_clear_same_boot_fork_foreign_only`, `D_clear_same_boot_open_generator`, `D_clear_committed_halt_same_boot`,
  `D_sameboot_damaged_cache_restores`;
- `D_slip_wrong_id_refinds`, `D_slip_size_refinds`, `D_slip_short_download_refinds`, `D_slip_limit_then_clear`,
  `D_slip_stale_raw_head_search`;
- `E_inputs_lost_after_reset_bounded`;
- the special `test_foreground_died_same_boot_stops` (new in v2.1), continued through the clear.

The net change is about +800 CPU-s before the per-scenario costs.

**Pruning.** If the first full run exceeds 50 min, T may prune only with a written coverage argument of the same kind.
The first candidates are the `_parts` twins of `D_vis_lag1`, `D_vis_dup` and `D_vis_timeout_late`: the entry and the
parts share `savepoint.block` and `on_found`, and the `t_commit_*` unit tests cover the parts.

### 5.3 Operator budget (D15, SD-67)

The README §7 table is the operator budget, in total tool calls.
- **How each column is counted.**
  - Helper commands, Drive calls, saved raw files and waits are counted by FakeDot: `x_opx10` per run over the D
    baseline, per item and per series over Q_baseline, and `x_op07_restore` per restore. The counts go into
    `tests/budget_golden.json`, a reviewed golden. `test_opx10_tool_calls_match_budget_golden` compares the measured
    counts with it, and L14 compares the README table with it.
  - Conversation steps are counted from the README actions.
  - Polls and checks: one tool call per return of the command tool while a stage runs, and one per 5 minutes while a
    conversation runs. G-3 measures the stage times, the tool's return interval (OQ-24) and the conversation lengths.
  - The qualification total sums the measured per-item counts over 38 runs, 34 nonattempts, about 10 scope readers
    and continuations, about 10 restores, and the start and end of the series.
- **The estimates until G-3.**
  - A normal run is about 65 to 71 tool calls: 16 helper commands, 15 + 3p Drive calls, 6 raw saves, about 10
    conversation steps and about 15 polls and checks.
  - A restore with the Dot's notes is about 53 (the approval answer and the RECHECK included); one without notes, over
    a journal of about 400 entries, is about 120 (about 24 gallop and binary-search lookups, each a FIND block).
  - A qualification is about 3,600 tool calls, or about 20 h at 20 s per call, before conversation, stage and approval
    time.
- **Refused uploads.** A qualification uploads about 330 files. Under the owner's 20-documents-a-day rule (M004) that
  is about 17 days of refusals, each an owner handback. G-10 is therefore required before G-4 and before qualification;
  with it, the expected refused uploads are zero.
- **Resets are frequent (D16, F8).** Two real VM resets came within two days (M005, M007). A qualification that
  takes days will run the restore path about once a day, so "about 10 restores" is a floor, not an estimate. Each
  reset also costs the light setup (130 s and 161 s observed) and, unless the owner pre-approves re-running it
  (OQ-27), the owner's approval wait (about two hours in M007). G-3 and G-4 restate the count.
- **What the counts assume.**
  - If saving a returned object costs no extra call on the platform (OQ-21, narrowed by M007, §2.16.2), each run
    saves about 6 calls.
  - The re-FIND after a slip costs one FIND, one raw save, one `found` and one DOWNLOAD, at most 3 times per save.

### 5.4 Platform time and disk (D16)

**Measured on the Dot (F1).** At the setup commit the runner suite passed 249/249 in 585.9 s on the Dot against
250.1 s on the maintainer machine, about 2.3 times. The stage maxima over the suite's invented jobs, Dot against
maintainer: finish 72.5 s against 16.2 s (about 4.5 times), prepare 5.0 s against 3.2 s, scope-finish 1.9 s against
1.1 s. The Dot has 9 CPUs, about 9.9 GB of RAM and `/home/agent` on a 4.9 GB tmpfs with 2.5 GB free after the light
setup; the toolchain takes about 2.3 GB, of which 541 MB are re-downloadable caches.

**The finish stage against the hold (F2).**
- The longest real finish stage measured on the maintainer machine (046g dev trial) took 190 s. One step dominates it:
  the internal visual QA, whose single `pdftoppm` call renders 336 A3 pages at 150 dpi (about 193 s when measured
  alone); the LibreOffice PDF export takes about 7 s.
- At about 4.5 times, that stage projects to about 850 s on the Dot. G-3's rule then needs 1.5 x 850 + 60 = 1,335 s,
  over the 1,200 s hold, which is the longest one proven (M003). The self-test is in the same position: the Dot's
  light trial measured 12 min 57 s (777 s, `docs/handoff/CURRENT_STATUS.md`), and 1.5 x 777 + 60 = 1,226 s.
- `visual_qa.render` has its own 900 s per-subprocess timeout, in the admitted writer package, outside the helper. At
  about 4.5 times, the `pdftoppm` call projects to about 870 s, near that timeout.

**What the helper does (built at 2015773, unchanged).**
- The release gate refuses a kit with any `stage_max_seconds` value + 60 > `foreground_hold_seconds`, or with
  `foreground_hold_seconds` > `gates.p5_foreground_hold_seconds`: `STOP RELEASE_GATE_OPEN` on every command. A stage
  budget that the proven hold does not cover therefore cannot be released.
- `stage_max_seconds` is a budget, not a timer. A stage that the platform kills at the hold ends as
  `FOREGROUND_DIED` (local sticky, HANDBACK C; `dead_<utc14>.json` keeps `started_utc` and `max_seconds`), never as a
  retry. A maintainer clear re-runs the stage unbound and logged (C8), and a deterministic over-long stage then stops
  the same way again. A stage that outlives its budget and completes is accepted, because the hold is not proven to be
  a hard limit (§X.7.2 step 5).

**The rule G-3 follows before `stage_max_seconds` is set.**
1. Probe M008 measures on the Dot, with invented data, the finish stage of a job whose visual QA renders 336 A3 pages
   at 150 dpi, and its `pdftoppm` call alone; G-3 measures the self-test and the other keys.
2. If 1.5 x each measured value + 60 <= 1,200 s, the values are set as G-3 says.
3. Otherwise G-3 also runs `probe_p5.py hold` for 1,800 s on the Dot. If that hold completes, the release kit sets
   `gates.p5_foreground_hold_seconds` to it and `foreground_hold_seconds` to 1,800 (neither is changeable; the owner
   approves the kit at G-9), the values must satisfy + 60 <= 1,800, and README sections 2 and 2.2 show 1,800.
4. If the 1,800 s hold does not complete, or a value still does not fit, there is no release until the owner decides
   (OQ-25).
5. If M008's `pdftoppm` call alone comes near or over 900 s, visual QA would fail inside the admitted writer on large
   cases whatever the hold. That goes to the owner with the measurement; it is outside the helper and outside this
   plan.

**Disk (F7).** `BASE` is on the 4.9 GB tmpfs with 2.5 GB free.

| item | size | how long it stays |
|---|---|---|
| one run's job folder | up to about 270 MB, 230 MB of it page PNGs | until EVICT after its FROZEN entry is confirmed |
| a commit's PNG parts in `outbox/journal` | up to about 230 MB | until DROP_LOCAL after the commit is confirmed |
| the download-back of those parts in `inbox/verify` | up to about 230 MB | deleted after the comparison |
| the entry archive | at most `max_entry_bytes` | until DROP_LOCAL |
| `aside_<utc14>/`, `fork_<utc14>/`, `cleared_<utc14>/`, `invalid_<utc14>/`, `outbox/v2/raw/` | an aside job folder up to about 270 MB; the rest small | never deleted by the helper; a reset frees them |

- **Peak.** EVICT and DROP_LOCAL are post actions, and the post resume runs before the next command (S-04). So at most
  two run job folders are on disk (the current run and one whose EVICT is still pending), plus one commit's parts and
  their download-back: about 2 x 270 + 230 + 230 = 1.0 GB, inside the 2.5 GB free.
- **The finish stage.** SD-69's check (`STAGE_FREE_BYTES`, 1,000,000,000 bytes plus the existing 64 MiB margin)
  runs before the runner writes anything; the snapshot, commit and verify checks then run with the real sizes.
- **Within one boot** every same-boot clear that moves a job folder aside keeps up to about 270 MB. After about five
  such clears in one boot, SD-69 or a later check stops `DISK_FULL` (local sticky, HANDBACK C); the owner decides what
  to free (the existing DISK_FULL text). A reset frees all of it.
- The test that runs several runs in a row and asserts the retention is v1r `test_d16_disk_bounded_over_runs`
  (§2.16.5); no earlier test asserts it.

---

## 6. Decisions beyond D1-D16, open questions, risks

### 6.1 Decisions this plan makes (for review 3)

| id | decision | where |
|---|---|---|
| SD-35 | md5-visible mode is deleted. Rule V by download-back is the only confirmation, and the confirms md5 is the local md5 | §2.1, §2.13 |
| SD-36 | the listing head hint is deleted. Without a hint the head search gallops; RECHECK follows SD-59 | §2.10.15 |
| SD-37 | OPENED is deleted in full: the kind, T35, T36, ROLE.opened, plan rows 5-7's no-list paths, the fold's no-list branches. The release gate and `t01` require `p1_conversation_list == 'yes'` | §2.10.14 |
| SD-38 | D3a's "a size that differs from our bytes" is decided by the download (a slip or a FORK), never at `found` | §2.2.2 |
| SD-39 | exit 4 now means "your answer was not used; do the block that follows". O7 is restated | §2.2.6 |
| SD-40 | a clear runs the restore of a reset in the same boot, after the clear check accepted the kit (SD-56). The HALT.json kit is the kit the journal names (SD-57) | §2.4 |
| SD-41 | placement accepts an equal target and moves any other aside (`settle`), everywhere | §2.4.6 |
| SD-42 | the approval question is recorded in every RESTORE and GENESIS body; where it is asked is SD-58 | §2.5 |
| SD-43 | the tool list is stored as an AI-entry member, and the generation record's `notes` carries the list's sha256 | §2.8 |
| SD-44 | the audit re-derives every kit change with the session's own `kit_change`, so there is one rule set | §2.7 |
| SD-45 | each D series gets its own folder, `CPS/drills/D<n>` | §2.10.10 |
| SD-46 | the unused reused segments are dropped (OQ-6 answered "drop") | §2.13 |
| SD-47 | `transcript=` stays asked although it is always `not_available` here (D10, and N44 must stay killable) | §2.9 |
| SD-48 | the found ATTEST line prints only the `--raw` form; the manual form is in the README | §2.3 |
| SD-49 | only an exact-name search can show a name absent. A file with a listing element gives an uncopied name `RAW_INVALID listing` | §2.3 |
| SD-50 | the Drive created time in a raw result is checked for shape only. It is never stored or compared (§X.9 rule 3 stands) | §2.3 |
| SD-51 | a RESTORE while HALTED keeps the halted kit, and the CLEAR that follows takes the new kit. This fixes a latent 2015773 defect (the CLEAR after such a RESTORE stopped with KIT_NOT_VERIFIED) and makes MAINT-3's from != to rule satisfiable | §2.4.5 |
| SD-52 | slips are counted per loop (a commit, a setup-file loop, a restore, a clear check): D3's "commit step". Refusals are counted per block | §2.2.1, §2.2.3 |
| SD-53 | the audit checks every entry with `cleared_local` by four rules: its kit's `clear` names it, its kit differs from the halted kit, the change from the halted kit is config-only, and its `kit_change` is null or config-only | §2.7 |
| SD-54 | the final message file gets no doc-sample comparison: it is data | §2.2.4 |
| SD-55 | D2 is read as "the total must not grow", with per-module counts reported | §5.1 |
| SD-56 | the clear check (`cli.clear_check`) decides a clear before anything moves, with a FIND and a DOWNLOAD of the candidate kit; HALT.json is written for every HANDBACK C STOP, `HALTED_<code>` included; `tried` starts with the halted, in-use and hinted kits; the session has no CLEAR phase | §2.4.1, §2.4.3 |
| SD-57 | HALT.json `kit_sha256` is the journal's kit; a clearing restore takes only a config-only kit change; a RESTORE while HALTED carries no `cleared_local` | §2.4.1, §2.4.4 |
| SD-58 | every session asks APPROVAL right after FINGERPRINT, before the head search; `pending` changes nothing | §2.5 |
| SD-59 | RECHECK runs on every qualification and drill restore, and on an everyday restore whose moved PENDING was uploaded; the head verdict's `via` is deleted | §2.10.15 |
| SD-60 | a reprinted block never carries UPLOAD lines | §2.2.3 |
| SD-61 | an accepted raw file is moved to `outbox/v2/raw/<at>.json`; copies are taken by exact title across all elements | §2.3 |
| SD-62 | NOTHING_WRITTEN only for a turn that never began to run (O45's "provably"); a conversation is a role's by its first message | §2.9, README §4 |
| SD-63 | `session_start.sh` removes every `__pycache__` under the checkout before it writes the launcher | §2.10.3 |
| SD-64 | `halt_local` in STATE.json and RESTORE_WORK makes a HALT.json removed out of procedure an invalid cache | §2.4.1 |
| SD-65 | a final message may be empty; an over-size one is `STOP AI_OUTPUT_TOO_LARGE` | §2.2.4 |
| SD-66 | guard sites are every and/or operand, every whole predicate and every chain link, over fold, session and the commit and restore glue; a fold.py equivalence may cite only checks on `fold.apply`'s own path | §2.15.2 |
| SD-67 | the operator budget comes from a measured golden (`tests/budget_golden.json`) and G-3's stage and conversation times; G-10 is required | §5.3 |
| SD-68 | `invalidate` moves the cache files, BASE/attest and BASE/inbox (the boot mark `.boot` excepted) for both prefixes, and only `cleared_` moves HALT.json; a damaged HALT.json is rewritten as UNCLASSIFIED; a STOP header shows HALT.json's head and kit, which the maintainer's clear names | §2.4.1, §2.4.2, §2.4.3 |
| SD-69 | (D16, F7) every chain stage first requires `STAGE_FREE_BYTES` (1,000,000,000) free, else the existing `STOP DISK_FULL` before the runner starts | §2.16.5, §5.4 |
| SD-70 | (D16, F6) `place.settle` sets the owner write bit on a target directory before it moves the target aside to another parent | §2.16.4 |
| SD-71 | (D16, F6) a non-root pass without capabilities (`--require-nonroot`, the `nonroot` group, `nonroot` mutants) is part of every integration and of G-1's reproduction; its counts are recorded in TEST_RESULTS.json and INTEGRATION.json | §2.16.4, §2.15.4 |

### 6.2 Open questions (none blocks the build)

- **OQ-19** (owner, G-2): option (a) or (b) for the O63 prompt layer, and which option carries runner re-admission.
  The record says both.
- **OQ-20** (Dot, G-5): does an upload the owner approves land after the VM that made it is gone? If it never does,
  D6's question is a second safeguard; if it always does, the question is required.
- **OQ-21** (Dot): can the platform write a Drive tool's returned object to a file in the same tool call? If it can,
  section 7's saved search results cost no extra call. Narrowed by M007 (D16, F4): the Dot serializes the object with
  `JSON.stringify` in its orchestration code and writes it with a Python heredoc; G-3 counts the calls this costs.
- **OQ-22** (owner): after `STOP SLIP_LIMIT` for INPUTS_CHANGED, a maintainer clear or a reset abandons the everyday
  job (§2.2.5). Is that the wanted behaviour, or should a later version let the owner order something else?
- **OQ-23** (Dot, G-4): does an exact-name search return a copy that was moved to the trash, or a copy of the same name
  in another folder? The second answer decides G-11.
- **OQ-24** (Dot, G-3): how often does the command tool return while a long command runs? It sets the poll count of
  README §7.
- **OQ-25** (owner, G-3; D16, F2): if probe M008 or the self-test projects a stage over the proven hold and a 1,800 s
  hold probe does not settle it (§5.4, rule steps 3-4), which of these applies? (a) No release until a longer hold is
  proven on the platform. (b) The kit value is capped at the hold minus 60 s, and the owner accepts that a stage longer
  than the hold ends as a recorded `FOREGROUND_DIED` stop (HANDBACK C, `dead_<utc14>.json`), never a silent retry. (c)
  A change outside this plan (for example in the admitted writer's render). The helper behaves the same under (a) and
  (b) and needs no code for either; the gate and the stop exist.
- **OQ-26** (owner, G-10; D16, F5): the pending standing approval names `CPS/qualification/` and `CPS/reports/`. Will
  it also name `CPS/drills/` (a drill series' journal, MAINT-7) and `CPS/setup/` (the SELFTEST and FINGERPRINT_PASS
  files of a new fingerprint), and, before everyday use, the everyday records folder and the profile's `deliveries`
  folder? Without them those uploads are refused every time (§2.16.3).
- **OQ-27** (owner; D16, F8): will the owner pre-approve re-running the light setup after a VM reset? In M007 the Dot
  waited about two hours for that approval. This plan does not decide it; §5.3 and §6.3 state the cost either way.

### 6.3 Risks

- **A clear while an AI role is open costs that output.** Any stop while a role is open, local or committed, including
  SLIP_LIMIT from refused answers about that conversation, costs that role's output when it is cleared: the clear's
  restore resolves the role as a reset would, and the files in its folder force WRITTEN (O46). That equals a reset at
  that moment. Making unfixable answers no refusal at all (an empty or over-size final message, SD-65) keeps this rare.
- **NOTHING_WRITTEN is now rare.** Only a turn that never began to run qualifies (SD-62), so most resets during a
  generator cost that run under O46. That is the fail-closed reading of O45's "provably wrote nothing", since the
  readback shows no tool calls (M006).
- **Persistent foreign copies end in FORK.** The owner must delete them for good before a clear; the helper never
  deletes on Drive. G-4 measures whether a trashed or out-of-folder copy is still returned (OQ-23, G-11).
- **The approval question relies on the Dot's notes.** A Dot that forgets a refusal answers `none`. The RECHECK catches
  a landing within `w_abs`, and the result stays fail-closed (`AUD_DUPLICATE_SEQ`, and score_check refuses), as the
  wrong-none scenario shows, but a whole series can become unscoreable. README §3.1 makes the Dot treat an unclear
  upload as refused.
- **The raw parser depends on the M004 shape.** A platform change of key names gives RAW_INVALID (a re-ask), and then
  the manual form. The parser never guesses. Swapped results no longer matter (copies by title), and a stale file is
  refused (consumed files). One slip remains: the same empty result saved twice in place of two different results
  hides a copy. The double absence, the RECHECK and the audit's full listing bound it.
- **Cache files replaced out of procedure.** The helper detects a removed HALT.json (`halt_local`, SD-64) and a
  STATE.json rolled back behind a printed block (a BLOCK.json ahead of STATE, §2.4.1). A STATE.json replaced by an
  older valid copy with no block printed after it is not detected on the VM. The next commit then uploads at a seq
  that is already on Drive, its FIND shows two copies with other bytes (FORK), and the audit is unclean
  (`AUD_DUPLICATE_SEQ`): fail-closed, but the series cannot be scored. It needs an actor with VM access outside the
  procedure, as removing HALT.json does (§7, GAP-05).
- **Bytecode planted after the bootstrap.** The helper process never reads bytecode, and `session_start.sh` removes
  every `__pycache__` before it starts. A valid `.pyc` written into the checkout after that by a process with VM
  access (the Dot, or a conversation's tools, whose isolation is by instruction under O63) would still be read by the
  runner's child processes. This is accepted, like O63's isolation; the helper's own checks of what it accepts from
  the children (the runner pin, the rebuilt kit against `--expect`, the runner records) stay.
- **The tool inventory is approximate.** M006 saw 386 to 419 tools in two conversations. The inventory records what
  was known to be present, and the isolation statement claims no more.
- **The fold changes touch the verifier.** These are job_dir, layout, the list gate, the consumer rule, T59, the
  resolution conversation and the OPENED deletion. The guard mutants and GUARD_TESTS are the control, and review 3
  reads core/ in full.
- **Guard-mutant survivors are unknown work.** About 935 sites (core and glue) will leave survivors that each need a
  test or an equivalence argument. This is the largest uncertain cost in T.
- **The line budget is tight.** The expected result is -6. Four new mechanisms (approval, clear, raw, O63) and the
  critical MAINT-1 fix are added. The deletions pay for them only if all of §2.13 is done, and the §5.1 contingency is
  pre-approved.
- **The restore path will run often (D16, F8).** Two real resets came within two days (M005, M007); the light setup
  took 130 s and 161 s, and in M007 the Dot waited about two hours for the owner's approval before it re-ran the setup.
  A qualification that spans several days will go through the restore path many times, each with the approval
  question, the head search, the RECHECK and possibly an open-role resolution, and each open generator at a reset
  costs that run under O46. The restore path is the most-used recovery path, so its tests (test_resets) and the drill
  (G-4) carry most of the operational risk. An owner pre-approval to re-run the light setup after a reset is an owner
  decision (OQ-27); without it every reset adds the owner's response time.
- **A long finish stage may not fit the hold (D16, F2).** Projected from the maintainer machine, the longest real
  finish stage is about 850 s on the Dot and the self-test 777 s measured; neither fits 1.5 x value + 60 <= 1,200 s.
  The release gate keeps such a kit from running (§5.4), so the risk is a release delayed until G-3, M008 and OQ-25
  settle it, not a silent failure. The writer's own 900 s render timeout may be the tighter limit; it is outside the
  helper.
- **Memory-backed disk (D16, F1).** `/home/agent` and `/tmp` are tmpfs of 4.9 GB each on a VM with about 9.9 GB of RAM,
  so files on them use the same memory as the runner, LibreOffice and `pdftoppm`. `require_space` sees only the free
  bytes of the file system. Keeping at most about 1 GB of run data on disk (§5.4) and deleting aside folders with a
  reset bounds this; G-4 watches for an out-of-memory kill, which would show as FOREGROUND_DIED.
- **The non-root pass is new (D16, F6).** The suite has only run as root so far. The first non-root pass may find other
  permission failures in the harness or the helper; each helper failure gets a fix, a test and a mutant under D16's
  rule, and a harness-only failure is fixed in the harness.
- **Test time.** The D group dominates, and every qualification restore now runs the RECHECK. If `--jobs 4` packing is
  poor, T may split the D group further; each split repeats the D baseline, about 5 min of CPU.

---

## 7. Critic gaps and responses

Three critic lenses read r3: integrity (13 gaps), operator (11) and tests (11). Each entry says what r4 does and where.
A part that r4 does not take as asked is marked **Rejected** with the reason. §7.4 records the r5 amendment (D16).

### 7.1 Integrity

- **GAP-01** (major; INT-R2-02, S-02, OPX-03, S-04). Accepted. r4 takes OP-01's design, which removes the deadlock's
  cause instead of adding an exception: `cli.clear_check` decides the clear before anything moves, and the session
  phase CLEAR is gone (§2.4.3, §2.4.4).
  - (a) No exception to the sticky STOP is needed. While HALT.json exists only the check's own `found` and `go` pass,
    and the restore starts after HALT.json has moved, so its found, answer and WAIT_APPROVAL are never blocked.
  - (b) Freshness. **Rejected as asked** (the clock comparison), with the same effect: HALT.json `tried` starts with the
    HINT.json kit of the moment of the stop (and the halted and in-use kits), so a HINT.json written before the stop
    never starts a check, and no clock reading is compared. A committed HALT's STOP also writes HALT.json, so the same
    rule covers it.
  - (c) The post resume runs after `clear_check` and only when no HALT.json exists; the clear moves STATE with its post.
  - (d) Moot: there is no CLEAR phase, and APPROVAL comes before HEAD on both paths.
  - Tests: rs `D_clear_same_boot_*` drive the check, then a found and an answer of the restore; vio
    `t_d5_wait_approval_in_clearing_restore` (a WAIT_APPROVAL in the clearing restore, then `go`, proceeds),
    `t_d5_post_action_halt_cleared_same_boot` (POST_ACTION_FAILED, EVICT_MISMATCH), `t_d5_stale_hint_never_checks`,
    `t_d5_clear_check_found_accepted`. Mutants: W92 (the check's own found printed as the STOP: the exception removed),
    W60 (order swapped), W61 (freshness dropped), W66 (HALT.json left in place, which blocks the restore again).
- **GAP-02** (major). Accepted. `files_found` comes from the existing target before `settle`, and from the placed tree
  after it; the `placed` item records `aside` (§2.4.4, §2.4.6). Test rs `D_clear_same_boot_open_generator` as required
  (FakeDot's outcome policy is NOTHING_WRITTEN, but with files_found true the outcome is never asked, §2.15.5), plus vio
  `t_gap02_files_found_before_settle`; mutant W76 (the rewalk only after settle). §2.4.7 ("An open role costs its
  output") and §6.3 now say that any stop while a role is open, SLIP_LIMIT from answer refusals included, costs that
  output.
- **GAP-03** (major). Accepted, with two parts rejected as asked.
  - HALT.json `kit_sha256` is the journal's kit (`STATE.state.kit_sha256`, else the verified head's, else the session's
    kit on a fresh series, else null only when the stop came before a kit was read or a head verified; §2.4.1). The gap
    asked for `STATE.kit_sha256` first: **rejected as asked**, because during a restore that takes a kit change,
    `STATE.kit_sha256` already names the incoming kit, while O59's "settings only" is relative to the kit the journal
    ran with, and the clearing restore compares with the head's kit.
  - A clearing restore's KIT_ACCEPT refuses any non-config-only change with CONFIG_CHANGE_NOT_ALLOWED (§2.4.4, W80,
    cm `test_d5_clearing_restore_refuses_release_change`).
  - `work.halted_kit` and the 'fetch' branch are gone with the CLEAR phase. **Rejected:** the separate "STOP with
    clearing.code when HALT.json's kit differs from the head kit". The clear check already tests the clear kit against
    the halted kit whenever the helper holds it, KIT_ACCEPT tests it against the head's kit, and the audit's rule 3
    tests the change from the halted kit. When the journal moved to another kit, the clear kit must therefore be
    config-only against both kits, or the restore stops; a third rule would add a branch and no protection
    (§2.4.3 `config`, §2.4.4).
  - S1 allows `cleared_local` only on RESTORE and GENESIS (W75); a RESTORE while HALTED carries none (W91). The audit's
    SD-53 has the four required rules (§2.7), with mt `test_maint3_audit_checks_cleared_local` covering a release
    change (W55).
- **GAP-04** (major). Accepted. The clear copies `{seq, name, sha256, uploaded}` of the moved PENDING into RESTORE_WORK
  `moved_pending`; a copy of that seq with other bytes is FORK, with its evidence kept (§2.4.4, §2.2.2). RECHECK runs
  on every qualification and drill restore (OP-05), and in an everyday series when `moved_pending.uploaded` is not
  empty. The parts need no rule of their own: savepoint uploads parts only after its entry is confirmed, so they exist
  only when that entry is the head, and rule V checks them. §2.4.7 is corrected. Tests rs
  `D_clear_same_boot_fork_foreign_only` and vio `t_gap04_moved_pending_foreign_copy_forks`; mutant W77.
- **GAP-05** (major). Accepted in part. A BLOCK.json behind STATE moves alone; one ahead invalidates the whole cache
  (§2.4.1). Test vio `t_gap05_block_ahead_invalidates_cache`; mutant W79 (`!=`). **Rejected:** invalidating at equal
  seq when BLOCK's basis does not match STATE. The basis is the sha of the `self_sha256` values of STATE, PENDING and
  RESTORE_WORK, so it changes at every durable write after a print (a mark, a post action, a crash between a write and
  the next render), and `go_checks` already treats a basis mismatch as "not the same block" and prints a fresh one.
  Invalidating there would turn routine writes into full restores. The rolled-back STATE that the gap names shows as a
  BLOCK ahead of STATE whenever a block was printed after the commit. A rollback with no later print needs an actor
  outside the procedure replacing STATE.json; it stays fail-closed at the next commit (FORK) and in the audit
  (`AUD_DUPLICATE_SEQ`), and §6.3 states it as a residual risk.
- **GAP-06** (major). Accepted.
  - README: the UPLOAD_REFUSED and WAIT_APPROVAL rows and §3.1 steps 3 and 4 say that a note is removed only when the
    owner says the upload was approved or denied, and that "continue" keeps it. L14 checks these sentences verbatim;
    mutant W95.
  - Every session asks APPROVAL right after FINGERPRINT, before the head search (OP-04, SD-58), so it precedes every
    session commit: the RESTORE, the GENESIS and the C10 HALT. The HALT body stays the plain HALT body.
  - S1 requires `approval == "none"` (W74, ct `test_d6_entry_approval_must_be_none`).
  - AUDIT.json lists `approvals` and `same_boot_restores` for the O52 sheet (W94, mt
    `test_gap06_audit_lists_approvals_and_same_boot_restores`).
- **GAP-07** (major). Accepted, merged with OP-06. README §4 and §2.9 say that tool writes do not appear in the readback;
  NOTHING_WRITTEN needs no message from the conversation and a turn status that shows it failed or was cancelled before
  it began to run; a turn that ran, then failed or was stopped, is UNSURE. L14 checks the sentences; §2.9 cites O45
  (provably) next to O55. Mutant W20.
- **GAP-08** (major). Accepted. The clear moves every file under BASE/attest and every entry of BASE/inbox into
  `cleared_<utc14>/` (§2.4.3), except the boot mark `inbox/.boot`, whose absence would make `cleanup_leftovers` empty
  the inbox at the next command; the verified candidate kit then moves from `outbox/v2/clear/` to `inbox/kit/`.
  `load_cache`'s `invalid_` path moves the same files (HALT.json excepted), so a same-boot restore after a damaged cache
  cannot take an old final message either. `render` removes any file at a DOWNLOAD target before BLOCK.json is written
  (§2.10.5). The README asks for tool files under BASE/attest, so they move too. Tests vio
  `t_gap08_clear_moves_attest_and_inbox` (REFUSED FINAL_MESSAGE_INVALID missing) and
  `t_gap08_render_removes_stale_download_target`; mutants W81, W82, and W100 (the boot mark moved too).
- **GAP-09** (major). Accepted. Hand mutants for each new integrity guard, mapped to the r4 design, each with a named
  non-reset test (§2.15.1): W62 (the check ignores `tried`, the old `k not in tried`), W97 (the halted kit missing from
  `tried`, the old `k != stopped_kit12`) and W63 (the kit in use missing from `tried`), W64 (the check starts on found
  or answer), W65 (a refused candidate removes HALT.json), W67 (settle compares paths, types and sizes only), W74
  (approval value not checked), W75 (`cleared_local` on any kind). The text filter on SESSION_COMMIT_MISMATCH is
  replaced by the clean-HEAD check and the structured `bootstrap_stop` field (TG-02, §2.15.4): a dirty clone is
  HARNESS_ERROR, and W13 is KILLED.
- **GAP-10** (minor). Accepted. For each FROZEN entry with GENERATION_RECORD.json, the audit requires `tools_enabled`,
  `notes` and the final message's sha256 to match the consumed G entry; a miss goes into `o63.missing`, so score_check
  refuses O63_ATTESTATION_MISSING (§2.8). Test mt `test_gap10_generation_record_tied_to_g_entry`; mutant W83.
- **GAP-11** (minor). Accepted in a different form; the SESSION_LAYOUT refusal is **rejected as asked**.
  `session_start.sh` **removes** every `__pycache__` under the checkout instead of refusing with SESSION_LAYOUT
  (§2.10.3, SD-63). A refusal would recur on every bootstrap until the Dot deleted the checkout, an action the README
  would have to add; removal reaches the same state (no bytecode when the helper starts, `-B` everywhere afterwards) in
  one line. The remaining exposure, a `.pyc` planted after the bootstrap, is stated in §6.3. Test v1r
  `test_gap11_session_start_removes_pycache`; mutant W84. The plan's earlier claim that the children compile what they
  import from source is withdrawn.
- **GAP-12** (minor). Accepted. `stop_block` writes `halt_local` into STATE.json and RESTORE_WORK; `load_cache`
  treats either one with `halt_local` and no HALT.json as invalid (§2.4.1, SD-64). The resulting same-boot RESTORE is
  listed by the audit (GAP-06). Test vio `t_gap12_halt_removed_out_of_procedure_restores`; mutant W85.
- **GAP-13** (minor). Accepted. §2.2.5 and README §2.3 say that a clear after INPUTS_CHANGED's SLIP_LIMIT abandons the
  everyday job (C8b, O49, O60), as a reset does; OQ-22 stays for the owner. rs `E_inputs_lost_after_reset_bounded`
  runs to the clear and asserts the abandon; cm `test_gap13_c8b_after_second_restore_abandons`; mutant W96.

### 7.2 Operator

- **OP-01** (critical). Accepted as written (§2.4.3): the verdict comes before any invalidation; the session phase
  CLEAR is deleted; a failure adds the kit to `tried` and prints the original STOP with STATE, PENDING and RESTORE_WORK
  unchanged; only success moves HALT.json and the cache into one `cleared_<utc14>/` folder and starts RESTORE_WORK with
  `cleared_local` and the hint; nothing in that restore is blocked by HALT.json. The config-only test uses the halted
  kit's dict when the helper holds it (`STATE.kit`, `RESTORE_WORK.kit` or `head_kit`), and is otherwise left to the
  clearing KIT_ACCEPT (GAP-03). Point (2): a SETUP_FAILED HALT.json on a fresh VM has `tried` holding the hinted
  release kit, so that kit never starts a check, and a kit that does not name the stop is refused before anything
  moves. Tests: the rs `D_clear_same_boot_{setup_failed,foreground_died,fork}` scenarios drive a found and an answer
  after the clear; vio `t_d5_refused_clear_kit_keeps_cache` (another seq, a null clear, the original kit after
  SETUP_FAILED: the original STOP, STATE.json byte-identical). Mutant W59 (the verdict moved back after the
  invalidation). Three details make the check usable and bounded: the STOP header shows HALT.json's head and kit,
  which the maintainer's clear must name (SD-68, W102); a damaged HALT.json is rewritten as UNCLASSIFIED, so it is
  cleared like any stop (W101); and a re-FIND keeps the check's slip count, so the fourth slip ends the check (W103,
  vio `t_d5_clear_check_bounded`).
- **OP-02** (major). Accepted (§2.2.3, SD-60). Every reprint drops its UPLOAD lines: the counted refusal's, the `go`
  reprint in `go_checks` and the slip's re-FIND; `--refused` stays allowed for `BLOCK.expect.uploaded`. README §2 has
  the required sentence, checked by L14; FakeDot asserts it in every scenario. Test vio
  `t_op02_reprint_has_no_upload_lines`; mutant W86.
- **OP-03** (major). Accepted (§2.3, SD-61). (a) An accepted raw file moves to `outbox/v2/raw/<at>.json`; a reused path
  is `RAW_INVALID missing`. (b) Copies are taken by exact title across all elements; the element-count check stays; a
  name is absent only when every element is a `results` search, else `RAW_INVALID listing`. (c) README §2 shows the
  three exact forms. FakeDot gets the slips `stale_raw` and `swapped_raw`. Tests rs `D_slip_stale_raw_head_search`, vio
  `t_d4_swapped_elements_assigned_by_title` and `t_op03_raw_file_consumed`; mutants W87 (not consumed), W88
  (positional).
- **OP-04** (major). Accepted (§2.5, SD-58). APPROVAL is the first session question after FINGERPRINT, before HEAD and
  before GENESIS; the observation clearing and W57 are deleted; `pending` gives STOP WAIT_APPROVAL before any FIND. The
  README rows and §3.1 carry the required sentences, including "If you are not sure whether the platform refused an
  upload or failed, treat it as refused.", all checked by L14. rs `D_refuse_reset_approval_pending` asserts that the
  approval block comes before the first FIND; mutant W89.
- **OP-05** (major). Accepted (§2.10.15, SD-59). RECHECK runs on every qualification and drill restore; the condition
  `hs['via'] != 'hint'` and the verdict's `via` are deleted, which shrinks session.py. Its cost is in README §7.
  Test rs `D_hint_restore_late_copy_at_n1_forks_at_recheck`, plus cm `test_op05_recheck_after_every_q_restore`;
  mutant W78.
- **OP-06** (major). Accepted, merged with GAP-07 (README §4, §2.9, SD-62): NOTHING_WRITTEN only for a turn that never
  began to run, so a conversation the Dot stopped while it ran is UNSURE; a conversation is the role's only when its
  first message is the full text of the role's prompt file, others (mailbox checks) do not count, and more than one
  candidate is UNSURE; the restart sentence says "in qualification ... in an everyday job it never restarts". §2.9
  cites O55, O45 and O46. L14 checks the sentences.
- **OP-07** (major). Accepted (§5.3, README §7, SD-67, G-3, G-10). README §7 adds the polls-and-checks column with a
  stated cadence (each return of the command tool; one check every 5 minutes), a restore without notes, the RECHECK in
  the restore row, the clear, and refused uploads (zero under G-10, which is now required before G-4 and before
  qualification). `x_opx10` and `x_op07_restore` write `tests/budget_golden.json`; the test and L14 compare with that
  golden, not with constants. The poll counts and the totals are written from G-3's measurements before G-9, since no
  stage time or conversation length is measured yet (OQ-24).
- **OP-08** (minor). Accepted (§2.2.4, SD-65). A present file of 0 bytes is accepted, the non-empty check is dropped,
  and an over-size message is `STOP AI_OUTPUT_TOO_LARGE`. README §4 has both required sentences. Test vio
  `t_opx05_empty_final_message_accepted` (the G record's `final_message` is `''`), plus
  `t_opx05_oversize_final_message_stops`; mutants W90 and W98 (an over-size message refused again).
- **OP-09** (minor). Accepted. README §3.2 has one action per RAW_INVALID detail (with `json` and `missing` added for
  the file checks of §2.3), and README §2 has the transient tool error sentence. L14 checks both.
- **OP-10** (minor). Accepted as a measurement with a pre-set rule. G-4 measures, on an invented file, whether a
  trashed copy and a copy in a second folder are returned by the exact-name search (OQ-23). If out-of-folder copies are
  returned, G-11 builds the parent filter of §2.3 (one comparison against the folder id pinned in the kit config) with
  its own test and mutant before release. A trashed copy keeps its folder, so the filter cannot help there; README §6
  therefore tells the owner to delete a foreign copy for good (trash, then delete from the trash) after the maintainer
  has saved it. Nothing is built before the measurement, because the rule would be dead code if search is
  folder-scoped.
- **OP-11** (minor). Accepted, with one change of wording (**rejected as asked** for the second sentence). README §2.3
  step 1 has the notes sentence. The requested text "otherwise tell the owner the code and your last CPSV line" alone
  would leave the series with no helper STOP, which no maintainer clear can reach. So step 5 says: tell the owner, then
  run `go` until the helper prints `STOP SLIP_LIMIT HANDBACK C` (at most 3 refusals). The end state is a helper STOP,
  and a clear of it abandons the job (GAP-13).

### 7.3 Tests

- **TG-01** (major). Accepted (§2.15.2, SD-66). The site rule now covers every and/or operand anywhere in a function
  (including assignments, call arguments, comprehensions and returns), every whole predicate of a return or of an
  assignment read later by a guard, and each link of a chained comparison. The generator selftest checks the reviewer
  sites (N04, N05, N07, N18, N50, N52) and the v2.1 sites. Recount at 2015773 with the planner's read-only script: fold
  543 (405 remove, 134 negate, 4 link), session 200 (74 remove, 126 negate). §5.2 restates the budget.
- **TG-02** (major). Accepted (§2.15.4). The string rule is dropped; the clean-HEAD check makes a dirty clone
  HARNESS_ERROR; `bootstrap_stop` is a structured field set by FakeDot.bootstrap; only failures that carry it are
  excluded. `--selftest` runs W45a, W45b and W13 with the stated verdicts.
- **TG-03** (major). Accepted (§2.15.2, §2.15.3). `guard_mutants()` also covers the glue functions that GUARD_TESTS
  keys name (savepoint, cli, `place.settle`, `drive.parse_raw`), with stage 2 as the killing set and the same
  EQUIVALENT table. Budget: <= 1.5 h at 4 workers (about 200 sites at about 101 s each). The line-tracer alternative is
  not used.
- **TG-04** (major). Accepted (§2.15.2): a fold.py equivalence may cite only a check on `fold.apply`'s own path (S1-S6,
  the row dispatch, an earlier conjunct of the same guard), named by function and condition; the writer never counts;
  G-1 reviews every entry.
- **TG-05** (major). Accepted (§2.15.5). The special runs in its own process group, is killed with `os.killpg`, checks
  `returncode == -9` and FOREGROUND.json at kill time, fails instead of passing if the process exited first, checks the
  leftovers after the next `go`, and continues through the clear kit so that `settle` moves the killed job folder aside
  and the RESTORE records `cleared_local`. W58 (`cleanup_leftovers` is a no-op) survives every in-process Kill scenario,
  recorded in MUTANTS_RESULTS.json, and is killed by the special.
- **TG-06** (major). Accepted (§2.6). (a) mt forges only the FINAL entry's ALL_FROZEN.json, outside `core_world.commit`,
  and expects AUD_OUTCOMES_DIFF and assemble's own `Bad LAYOUT_PATH`; `test_maint1_audit_refuses_hostile_new_run` also
  gives the audit a hostile new-run entry built the same way, so the fold, the audit and assemble each refuse (D7).
  (b) Assemble takes the base from the GENESIS entry and refuses an ALL_FROZEN that differs (W93). (c) The wrong mappings,
  the self-consistent hostile base with an outside sentinel, and one fold case per row T10-T13 and the everyday branch.
  (d) W29a and W29b, each with its own killing tests. (e) §2.6 states that the fold and audit checks are pure string
  checks; the symlink defence is tested through a monkeypatch hook between `Staging.begin` and the first write.
- **TG-07** (minor). Accepted (§2.7, §2.11). `from_equals_to` is deleted; the real-zip from = to case expects
  AUD_CHAIN_INVALID T60. `test_maint4_audit_only_kit_change_verdicts` has exactly the three audit-only cases, each
  killing W36, and §2.7 states that the other codes reach the audit only as AUD_CHAIN_INVALID.
- **TG-08** (minor). Accepted, each with a named killing test (§2.15.1): (1) W66, (2) W62, (3) W67, (4) W68, (5) W69 and
  W70, (6) W71 and W72, (7) W73.
- **TG-09** (minor). Accepted (§2.15.6): the three-column table for the eleven reviewer mutants, the named list of
  tests run directly at 2015773 with their expected failures, and T1's eight cases fed to the fold.
- **TG-10** (minor). Accepted. (a) `t_s07` plants valid-header `.pyc` files for `cps_job.py` and for one helper module
  after the bootstrap and asserts that the hashed source ran (§2.10.3). (b) W26 is now "one README §7 count off by
  one", killed by L14, which compares the README table with `tests/budget_golden.json`;
  `test_opx10_tool_calls_match_budget_golden` compares the measured counts with the same golden and kills W99 (FakeDot
  counting Drive calls only, the 2015773 basis). The per-qualification count is built from per-item counts measured
  over Q_baseline (§5.3), not from the D baseline multiplied. (c) W38 and W39 are in mutants.py with the path
  `deploy/make_kit.py` and killed through the v1r hooks.
- **TG-11** (minor). Accepted (§2.15.4, §5.2). The per-mutant timeout is 3 times the baseline of the killing set, with
  its own verdict; guard runs use `--jobs` workers; the guard baseline runs on the unparsed modules; GM ids are
  `module-function-ordinal`; the T11 known names include the `CONFIGS` keys; after wave 1, T measures D_baseline and an
  E scenario and restates the test_resets estimate before the new scenarios are added. The measured 22 s and 101 s per
  mutant set the guard budgets.

### 7.4 D16 (M007)

r5 adds maintainer decision D16, which carries the operator's M007 answers (F1-F8, invented data, verified by the
maintainer against the operator's uploaded files) into the plan. Every r4 decision stays. What changed, and where:
- **Header, status line and authority.** The status line and the title say r5; the authority list names D1-D16 and
  states D16; the plan's own decisions run to SD-71; §0 has one bullet on the operator's platform.
- **§1.1.** A test or mutant marked (non-root) decides only in the non-root pass; the D16 rows that are correct at
  2015773 are proven by their mutants.
- **§1.2.** Cells added to S-09 (F3: the DOWNLOAD route in the README, FakeDot's route, L14, W104), OPX-02 (F4: the
  M007 envelope as first fixture, the raw-save sentence), OPX-09 (F5: the never-work-around sentence, W105, gate G-10),
  OPX-10 (gate G-3 with M008) and TST-MUT (`nonroot` mutants). New rows D16-F2 (stage time: no code, gate G-3,
  OQ-25), D16-F6 (non-root: SD-70, SD-71, W106, W107) and D16-F7 (disk: SD-69, the retention test, W108-W110).
- **§1.3.** CBR-9 names M008, §5.4 and the D16 rows. G-1 reproduces the non-root pass and the `nonroot` mutants. G-3
  requires probe M008 (an invented 336-page A3 150 dpi render on the Dot, with the `pdftoppm` call timed alone against
  the writer's 900 s timeout) before any `stage_max_seconds` value is set, measures the self-test, follows §5.4's rule
  (a 1,800 s hold probe, then OQ-25) and writes README's hold value. G-4 and G-5 provoke their refused upload on
  purpose, because G-10 comes first. G-10 names as its precondition the owner's standing approval of every upload the
  helper can print, lists the folders, and states the pending owner decision and its gap (OQ-26).
- **§2.3.** M007 confirms the envelope and the empty search; the parse rules are unchanged.
- **§2.11.** The constant `STAGE_FREE_BYTES`; no new code in CODES.
- **§2.14.** FakeDrive's `raw_find` entries carry every M007 key; FakeDot downloads through an attachment file and
  `cp`, writes raw files in the compact `JSON.stringify` form, and records job folders and journal files per block.
- **§2.15.** Hand mutants W104-W110; the non-root mutant rule and the `nonroot` group name in §2.15.4; new tests
  `t_d16_settle_moves_readonly_target_aside`, `t_d16_stage_refuses_low_space_before_runner`,
  `test_d16_evict_runner_frozen_folder_nonroot` and `test_d16_disk_bounded_over_runs`; the M007 fixtures of the D4
  tests; three more L14 sentences; the proof note for the D16 rows that are correct at 2015773.
- **§2.16 (new).** The facts and what follows from each: downloads (F3), saved tool results (F4, OQ-21 narrowed),
  uploads inside the standing approval with the helper's upload inventory (F5), read-only trees with SD-70 and the
  non-root pass SD-71 (F6, with the maintainer's own probe of `rmtree` and cross-parent `rename` as uid 1000), disk
  with SD-69 and the retention test (F7), and pointers for stage time and resets (F1, F2, F8). No runner change.
- **§3 (README).** Section 2: the DOWNLOAD sentence describes the raw-file download and the `cp` of the downloaded file
  (r4's "never copy a local file there instead" is gone), and the raw-save sentence says how to serialize and write.
  Section 3.1 step 4: never work around a refused upload; wait for the owner. Section 7: the advance approval names
  the four folders. Notes for C: the hold value comes from the release kit.
- **§4.** Wave 3 runs the non-root pass after the full suite; T builds it, the integrator runs and records it.
- **§5.** §5.1 pays SD-69 and SD-70's three lines from contingency 2, so C's cap holds; §5.2 adds the non-root pass
  (<= 10 min, outside D14's 50/60 min) and the `nonroot` mutants; §5.3 says that restores are frequent; the new §5.4
  gives the Dot's measurements, the finish-stage and self-test projections against the hold, what the helper does,
  G-3's rule, and the disk budget against the 2.5 GB free.
- **§6.** SD-69 to SD-71; OQ-21 narrowed; OQ-25 (a stage over the hold), OQ-26 (the approval's folders) and OQ-27
  (re-running the light setup after a reset, left to the owner); risks for the frequent restore path, a finish stage
  over the hold, the memory-backed disk and the first non-root pass.

---

## 8. Build results (integration, 2026-11-12)

The three tracks (M, C, T) were integrated, the suites and the mutation set were run, and the result was committed on
branch `v21-build` as "cps-vm-helper.v2.1 candidate (not reviewed, not admitted)". **Nothing here is an admission.**
Review 3 (G-1) decides. The runner `deploy/run/cps_job.py` is byte-identical (sha256 `7505e98a…`). The numbers below
are in `scratchpad/vm_helper/v21/keep/INTEGRATION.json`.

### 8.1 What the integrator changed

- `cli.stop_block` lost its dead `name` parameter: no caller passed it, and its guard site could not be killed. This
  changes no behaviour.
- `vm2.py`'s docstring now names v2.1. Every printed or recorded version was already `cps-vm-helper.v2.1`.
- `tests/seen.py`, the runtime half of L1, now records:
  - a refusal line with a detail word, such as `REFUSED RAW_INVALID missing` or `REFUSED <slip> <name>`;
  - a STOP line with `name=`;
  - the slip refusal `emit` prints;
  - only the code word of a returned `CODE detail`;
  - from `on_found`, its stop codes only (not the file name of a handback).

  Before this change the first full run failed L1 on RAW_INVALID, FINAL_MESSAGE_INVALID and PLACE_TARGET_NOT_EMPTY,
  and the second on file names that were recorded as codes.
- New glue tests in `test_vio.py` close the 37 glue guard survivors that T left open. Each has a GUARD_TESTS entry:
  - `t_d11_stop_block_sticky_only_for_handback_c`
  - `t_d11_clear_check_routes_found_only_to_its_find`
  - `t_d11_session_slip_voids_only_its_name`
  - `t_d11_head_download_slips_and_no_block`
  - `t_d11_link_copy_download_keeps_the_head`
  - `t_d11_session_download_names_kept`
  - `t_d11_local_download_checked_at_go`
  - `t_d5_settle_root_mode_link_and_file_targets`
  - `t_d11_drill_genesis_refuses_existing_ledger`
  - the extended `t_op02_reprint_has_no_upload_lines`

  `t_maint2_inventory_rehashed_at_attest` now makes the read-only installed TOOL_INVENTORY.txt writable before it
  changes the file. Only the non-root pass found this fixture bug. `test_v1_regressions.py` map texts no longer name
  deleted features.
- `tests/mutants.py`:
  - The glue set now runs its direct tests, and its survivors run stage 2 (§2.15.2).
  - Ten EQUIVALENT entries were added: go_checks-3, -4, -5, -6, -7, -9 and -10, session_downloads-3, and settle-1
    and -2.

### 8.2 Test runs

Each run started from a `bin/testclone.sh` snapshot, with `--jobs 4`.

| run | tests | passed | wall | uid / CapEff |
|---|---|---|---|---|
| root, full suite (final, `full3`) | 557 | 557 | 3,135 s (52.2 min) | 0 / full root |
| root, full suite (first, `full1`, under load from two mutation runs) | 548 | 547 (L1) | 3,573 s | 0 |
| root, full suite (second, `full2`, idle machine) | 557 | 556 (L1: file names recorded as codes) | 3,099 s | 0 |
| non-root pass `--only nonroot` (final, `nr4`) | 245 | 245 | 875 s | 1000 / 0 |
| non-root pass (`nr2`, first valid run) | 245 | 244 (fixture bug, fixed) | 921 s | 1000 / 0 |

- Non-reset suites took 628 s in the final run. test_vio alone took 483 s, so the non-reset budget of §5.2
  (<= 5 min) is not met.
- test_resets took 2,457 s for 208 scenarios.
- The non-root pass ran `setpriv --reuid=1000 … --inh-caps=-all --bounding-set=-all` in a folder owned by uid 1000,
  with `--only nonroot --require-nonroot`. Its first valid run found the fixture bug above. Its time, 875 s, is over the
  10 min budget of §5.2.

### 8.3 Mutation runs

| set | mutants or sites | killed | survivors | survivors with an EQUIVALENT argument |
|---|---|---|---|---|
| hand W, reviewer N, legacy (G, M, B, C) | 179 | 179 | 0 | – |
| of which non-root W106, W107 (uid 1000, CapEff 0) | 2 | 2 | 0 | – |
| guard, core set (fold 545, session 202) | 747 | 730 | 17 | 17 |
| guard, glue set | 168 | 150 | 18 | 18 |
| selftest (W45a HARNESS_ERROR, W45b not KILLED, W13 KILLED, generator sites) | – | ok | – | – |

**Snapshots.** The mutation runs used earlier snapshots of the same helper code: hand, reviewer, legacy and core at
c196846, glue at d202d58. The test-only changes made after them are the seen.py recording, the faster stop of
`t_d11_head_download_slips_and_no_block`, and the TOOL_INVENTORY chmod. Only the second one touches a killing test,
and it makes that test fail sooner, not later. The final suites ran at full3 and nr4, which have the same helper tree
sha256.

**What G-1 has to rule on.** G-1 reviews every EQUIVALENT entry. Two kinds need particular attention:
- Five fold entries rest on state invariants that every fold effect keeps: g10-12, g10-15, g24-2, g42-9 and
  _items_check-5.
- `GM-cli-go_checks-4-r` rests on a crash window: a stale BLOCK.json whose files are all present.

**Reviewer proof table (TG-09 table 1).**
- All 11 N mutants are KILLED at v2.1 with T's ports.
- At 2015773, the "passes" and "fails with the original substitution" columns hold for N04, N05, N06, N07, N37, N44,
  N50 and N52 (T's `proof_n2.json`).
- N40 and N42 change code at their rows (T7, T8), so their test already fails on plain 2015773.
- N18's v2.1 fixture does not fit the 2015773 head_search, which has no `via` key.

### 8.4 Lines (D2)

C total 7,737 (baseline 7,566, cap 7,500), M total 896 (baseline 830, cap 896), all 8,633 (baseline 8,396).
**D2 is not met.** C is 237 over its cap and the total grew by 237 lines, almost all of it in `cli.py` (+179). The
§5.1 contingency deletions were not made at integration. No behaviour may be removed for a budget, and the docstrings
are already short. The per-module table is in INTEGRATION.json `lines_D2`.

### 8.5 Operator budget (D15)

The harness counts were measured on invented jobs with FakeDot.
- **Per run.** These counts equal `tests/budget_golden.json` and README §7:
  - a normal run: 16 helper commands, 15 + 3p Drive calls (54 with the harness's 13 PNG parts), 6 saved results;
  - a nonattempt: 2, 3 and 1.
- **Per series start and end.**
  - D baseline: 16 helper commands, 14 Drive calls, 7 saved results.
  - Q baseline: 25, 20 and 11.
- **Per restore.** Helper commands and saved results are counted to the end of the session, the RECHECK included.
  Drive calls are counted to the RESTORE's own download-back.
  - with the Dot's hint: 18 helper commands, 15 Drive calls, 8 saved results, 2 waits;
  - with only the commit line: 39, 46 and 14;
  - with no notes (step 0): 24, 23 and 13. This journal has 5 to 6 entries. README's "about 120" without notes
    assumes about 400 entries and was not measured.

README §7's qualification total (about 3,600 tool calls) still rests on these per-item counts plus G-3's polls and
conversation steps.

### 8.6 Open after integration

- **Plan defect: MAINT-1 and MAINT-5 together block Q/D scoring.** This was found by track M and is not resolved:
  - assemble writes only under a dedicated `--root`;
  - runner v4's verify-frozen finds a run only at its original absolute path;
  - so a Q/D assembly is ASSEMBLE UNCLEAN and score_check refuses ASSEMBLE_NOT_VERIFIED.

  This fails closed, but drill G-4 cannot end CONSISTENT until the planner decides how verify-frozen is run (for
  example, a mount namespace that shows the root at the original base, or an owner-approved exception). D_baseline
  asserts the fail-closed result.
- D2 is over its line caps (8.4).
- D14: the full suite took 52.2 min, which is over the 50 min target and under the 60 min ceiling. The non-reset
  suites and the non-root pass are over their §5.2 budgets.
- Every EQUIVALENT entry (17 core and 18 glue) waits for G-1.
- The release gates G-1 to G-11 belong to the Dot, the owner or the reviewers, and none of them was run.
