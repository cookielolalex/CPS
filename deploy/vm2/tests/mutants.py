"""Mutation set (delta v2.1 §2.15): run_tests.py --mutants [--only IDS|GROUP] [--jobs N] [--selftest].

Each mutant is exact (old, new) substitutions in one file (path relative to deploy/vm2/; each old text exactly once) or
an AST guard mutation (§2.15.2). one(m) (§2.15.4): `git clone --local` of this checkout, the mutation, py_compile, a
commit with an invented identity, the clean-HEAD check (else HARNESS_ERROR, nothing runs), then run_tests.py --only
<killing names> with a timeout of 3 times the baseline time of that set. KILLED: exit 1 with a failure that carries no
`bootstrap_stop` (the World's own bootstrap stopping says nothing about the mutant). A `nonroot` mutant runs its set
under setpriv as uid 1000 with --require-nonroot (§2.16.4). The harness refuses a dirty checkout.
Groups for --only: hand, reviewer, legacy, guard_core (or guard_fold, guard_session), guard_glue, nonroot. Writes <work>/MUTANTS_RESULTS.json
(cps.vm2-mutants.v2) with the survivors and their EQUIVALENT arguments."""
import ast
import json
import os
import py_compile
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
VM2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(VM2))
IDENT = ['-c', 'user.name=v21-mutant', '-c', 'user.email=mutant@invalid']
NONROOT_UID = 1000


def M(mid, path, subs, kill, what, v1=(), nonroot=False):
    return {'id': mid, 'path': path, 'subs': subs, 'kill': kill, 'what': what, 'v1': list(v1), 'nonroot': nonroot}


SP, CLI, FOLD, SESS, PLAN, OUT, WRK = ('cpsvm2/vio/savepoint.py', 'cpsvm2/cli.py', 'cpsvm2/core/fold.py',
                                       'cpsvm2/core/session.py', 'cpsvm2/core/plan.py', 'cpsvm2/core/outcome.py',
                                       'cpsvm2/worker.py')
NAMES, ENTRY, DRV, PLACE, HOST, DUR, RUN = ('cpsvm2/core/names.py', 'cpsvm2/core/entry.py', 'cpsvm2/vio/drive.py',
                                            'cpsvm2/vio/place.py', 'cpsvm2/vio/host.py', 'cpsvm2/vio/durable.py',
                                            'cpsvm2/vio/runner.py')
MK = '../make_kit.py'
# The 11 reviewer mutants that survived at 2015773 (admission_r2 my_mutants.py), ported to the v2.1 text of the same
# rule (D11c, §2.15.1); killed by the rows of §1.2.
REVIEWER = [
    M('N04', FOLD, [("and b['start_boot_id'] == lt['boot_id'] == e['boot_id']", "and b['start_boot_id'] == e['boot_id']")],
      ['test_t4_ai_start_boot_must_be_the_start_boot_t39'], 'T37 does not bind the attested start boot to the START'),
    M('N05', FOLD, [("and b['revision'] == len(ro['archives']) + 1 and e['boot_id'] == ro['continued_boot'] \\",
                     "and b['revision'] == len(ro['archives']) + 1 \\")],
      ['test_t4_continued_v_answer_of_another_boot_t39'], 'T38 accepts a continued V answer from another boot'),
    M('N06', FOLD, [("    if ro['status'] == 'CONTINUED':\n        return ('T46', 'FREEZE_VISUAL_FAILED', False) if item['outcome'] == "
                     "'CONTINUED' else ('T48', None, False)",
                     "    if ro['status'] == 'CONTINUED' and item['outcome'] == 'CONTINUED':\n        return ('T46', "
                     "'FREEZE_VISUAL_FAILED', False)")],
      ['test_t1_continued_v_other_outcomes_t48'], 'a CONTINUED V item with another outcome falls through'),
    M('N07', FOLD, [("        if L is None or L['status'] != 'FROZEN' or not (\n                not L['frozen']['restart_eligible'] or "
                     "L['tag'] == 'A-restart1' or 'RESET_DIVERGED' in L['flags']):",
                     "        if L is None or L['status'] != 'FROZEN':")],
      ['test_t2_reader_b_waits_while_a_owes_restart'], 'B may start while A still owes its restart'),
    M('N18', SESS, [("    if not f[names[0]]['present'] or any(f[n]['present'] for n in names[1:]):",
                     "    if not f[names[0]]['present']:")],
      ['test_t3_recheck_second_writer_at_n2_n3_forks', 'test_t3_recheck_forks_2015773_form'],
      'the step-6 re-check ignores N+2/N+3'),
    M('N37', SP, [("    if man['state_sha256'] != pend['state_after_sha256']:\n        stop(", "    if False:\n        stop(")],
      ['t_t6_finish_refuses_entry_that_is_not_pending'], 'finish installs a local entry that is not the pending one'),
    M('N40', NAMES, [("    if 'started_utc' in got and 'ended_utc' in got and got['started_utc'] > got['ended_utc']:",
                      "    if False:")],
      ['test_t7_started_after_ended_refused'], 'started_utc after ended_utc is accepted'),
    M('N42', CLI, [("            code = 'DOWNLOAD_MISSING' if not os.path.isfile(p) else 'DOWNLOAD_INCOMPLETE' \\\n"
                    "                if os.lstat(p).st_size != size else None",
                    "            code = None if not os.path.isfile(p) else 'DOWNLOAD_INCOMPLETE' \\\n"
                    "                if os.lstat(p).st_size != size else None")],
      ['t_t8_session_download_missing_refinds'], 'a session download answered without the file is not a slip'),
    M('N44', CLI, [("    if not path or not os.path.isfile(path) or os.lstat(path).st_size == 0:",
                    "    if not path or not os.path.isfile(path):")],
      ['t_t9_empty_transcript_refused'], 'an empty transcript file is accepted'),
    M('N50', FOLD, [(" and set(kc['config_keys_changed']) <= CHANGEABLE_KEYS", "")],
      ['test_t10_config_only_change_of_other_key_release_not_accepted'], 'S5 accepts a config-only change of any key'),
    M('N52', FOLD, [("            or L['interrupts'] or L['tag'] not in ('A', 'B'):", "            or L['tag'] not in ('A', 'B'):")],
      ['test_t5_restart_after_in_place_interrupt_t14'], 'T11 accepts a restart after an in-place interrupt'),
]

# Hand mutants W01-W110 (§2.15.1): each puts back the 2015773 behaviour or removes one v2.1 rule. Those marked in
# HAND_OPEN have no substitution yet (reported, never counted as killed).
HAND = [
    M('W01', SESS, [("    if w.get('approval') is None:                                                   # D6: before any FIND\n"
                     "        return 'APPROVAL'", "    if False:\n        return 'APPROVAL'")],
      ['test_d6_approval_asked_before_restore_and_genesis', 'test_d6_approval_before_head'], 'APPROVAL skipped'),
    M('W02', SESS, [("    if not clear_ok(cand['config'].get('clear'), halt['series'] or cand['config'].get('series'), "
                     "halt['head_seq'],\n                    code):",
                     "    if (cand['config'].get('clear') or {}).get('code') != code:")],
      ['test_d5_clear_verdict_exact_clear_and_config_only'], 'the clear verdict compares only the code'),
    M('W03', PLACE, [("            if same:\n                remove_tree(stage)\n                return None",
                      "            if True:\n                raise Halt('STOP', 'PLACE_TARGET_NOT_EMPTY', 'exists')")],
      ['t_d5_placement_accepts_equal_or_moves_aside', 't_snapshot_place_roundtrip_and_evict'],
      'settle refuses an existing target'),
    M('W04', FOLD, [(", 'conversation': it['conversation']}", "}")],
      ['test_int_r2_03_restore_conversation_recorded'], 'e42 drops conversation'),
    M('W05', FOLD, [("        if sorted(c['role'] + str(c['attempt']) for c in b['consumed']) != want or not want:\n"
                     "            return False", "        pass")],
      ['test_int_r2_04_consumer_stage_without_consumed_is_t25'], '_consumed_ok checks only the listed items'),
    M('W06', CLI, [("    b = savepoint.block(loop, env.upload_cfg['max_upload_bytes'],",
                    "    b = savepoint.block(loop, env.cfg['max_upload_bytes'],")],
      ['t_s01_setup_failed_log_uploaded_without_kit_config'], 'the loop reads the kit config cap'),
    M('W07', SP, [("        if os.lstat(v['path']).st_size != v['size']:\n            return 'slip', 'DOWNLOAD_INCOMPLETE', v['name']",
                   "        if os.lstat(v['path']).st_size != v['size']:\n            return 'stop', 'FORK', None")],
      ['t_s03_short_download_refinds_real_fork_keeps_bytes', 't_commit_fork_foreign_md5'],
      'a download of another size is FORK'),
    M('C1', CLI, [(" and env.cache.get('post') and env.pending is None:", " and env.cache.get('post'):")],
      ['t_c1_post_failure_finishes_pending_halt_first'], 'OPEN-C1: the owed post runs before a pending commit'),
    M('W08', CLI, [("        if env.cache is not None and env.cache.get('post') and env.pending is None:\n            run_post(env)",
                    "        if False:\n            run_post(env)")],
      ['t_s04_pending_post_resumed_before_next_commit'], 'STATE.post is not resumed'),
    M('W09', SP, [("            if sha_bytes(b) != want.get(name):", "            if False:"),
                  ("        if whole != want_whole:", "        if False:")],
      ['t_s05_png_changed_before_part_write_halts'], 'the PNG whole and per-file compare removed'),
    M('W10', CLI, [("and drive.prints(pf.rstrip('/') + '/deliveries')", "and True")],
      ['test_s06_profile_folder_with_brace_refused_before_commit'], 'the profile-folder print check removed'),
    M('W12', RUN, [("    mod = types.ModuleType('cps_job_v4')\n    mod.__file__ = str(p)\n"
                     "    exec(compile(raw, str(p), 'exec'), mod.__dict__)",
                    "    import importlib.util as iu\n    sp = iu.spec_from_file_location('cps_job_v4', str(p))\n"
                    "    mod = iu.module_from_spec(sp)\n    sp.loader.exec_module(mod)")],
      ['t_s07_runner_loaded_from_hashed_bytes'], 'load_runner goes through the file loader (bytecode cache)'),
    M('W15', CLI, [("    except OSError as e:                                    # S-11\n        return safe_stop(env, durable.DurableError(e.errno).code)\n",
                    "")],
      ['test_s11_oserror_outside_stage_prints_stop_block'], 'run_command does not catch OSError'),
    M('W16', CLI, [("        elif bl.get('head_seq') != hs:\n            d = fresh(env, 'invalid_')\n            d.mkdir(parents=True)\n"
                    "            os.replace(env.p.block, d / 'BLOCK.json')\n            bl = None",
                    "        elif bl.get('head_seq') != hs:\n            bad = True")],
      ['t_gap05_block_ahead_invalidates_cache'],                  # GAP-5: t_opx07 does not fail on W16
      'a BLOCK.json behind STATE invalidates the whole cache'),
    M('W17', DUR, [("    write(path, doc_bytes(doc), mode)\n    return doc", "    write(path, doc_bytes(doc), mode)\n    return dict(doc)")],
      ['t_opx01_restore_work_writes_kept'], 'write_doc returns a new dict'),
    M('W18', CLI, [("    if r[0] == 'slip':\n        lim = savepoint.slip(loop, r[2], r[1])",
                    "    if r[0] == 'slip' and r[1] == 'DOWNLOAD_MISSING':\n        env.refusal = 'REFUSED %s %s' % (r[1], r[2])\n"
                    "        return\n    if r[0] == 'slip':\n        lim = savepoint.slip(loop, r[2], r[1])")],
      ['t_opx02_mistyped_id_refinds_then_commits', 'D_slip_wrong_id_refinds'],
      'DOWNLOAD_MISSING keeps the download and reprints the DOWNLOAD block (2015773), no re-FIND'),
    M('W22', CLI, [("    if code.split()[0] not in ('HELPER_BUSY', 'JOB_BUSY'):\n        count(env, code.split()[0])",
                    "    pass")],
      ['test_opx06_inputs_changed_bounded_then_slip_limit', 't_d3_refusals_bounded_then_slip_limit',
       't_d4_raw_invalid_reasked'], 'refusals are not counted'),
    M('W23', SP, [("    loop['slips'] = loop.get('slips', 0) + 1", "    loop['slips'] = loop.get('slips', 0)")],
      ['t_d3_fourth_slip_stops_slip_limit'], 'the slip counter is not incremented'),
    M('W25', DRV, [("            ' name=%s' % word(args['name']) if args.get('name') else '')", "            '')")],
      ['t_opx09_refused_stop_names_the_file'], 'the UPLOAD_REFUSED STOP has no name='),
    M('W28', FOLD, [(" or nr['job_dir'] != job_dir_of(s['genesis']['base'], nr['tag'], nr['case'])", "")],
      ['test_maint1_new_run_job_dir_must_be_the_layout_path', 'test_maint1_audit_refuses_hostile_new_run'],
      'the fold _virtual job_dir check removed'),
    M('W35', FOLD, [("        and kc['from_kit_sha256'] != kc['to_kit_sha256'] \\\n", "")],
      ['test_maint3_clear_with_unchanged_kit_t60'], 'g59 has no from != to'),
    M('W40', NAMES, [("    return FOLDERS['D'] + '/' + series if series[0] == 'D' else FOLDERS[series[0]]",
                      "    return 'CPS/reports' if series[0] == 'D' else FOLDERS[series[0]]")],
      ['test_maint7_drill_series_own_folder'], 'the D folder is back to CPS/reports'),
    M('W44', 'probe_p5.py', [("        if a.seconds < a.min_gap:", "        if False:")],
      ['test_maint10_probe_start_refuses_seconds_below_min_gap'], 'probe start accepts seconds below min-gap'),
    M('W46', DRV, [("r.get('title') not in cps or", "not any(n in str(r.get('title')) for n in cps) or")],
      ['t_d4_parse_raw_rules'], 'parse_raw matches a title that contains the name'),
    M('W52', FOLD, [("            or b['layout'] != layout_of(base) or", "            or")],
      ['test_maint1_genesis_layout_base_relative'], 'the t01 layout check removed'),
    M('W54', SESS, [("        if lk['name'] in names and not lk.get('void'):", "        if lk['name'] in names:")],
      ['test_d3_head_search_ignores_void_lookups'], '_facts ignores the void flag'),
    M('W59', CLI, [("    invalidate(env, 'cleared_')\n", ""), ("    if S.clear_verdict(h, cand,", "    invalidate(env, 'cleared_')\n    if S.clear_verdict(h, cand,")],
      ['t_d5_refused_clear_kit_keeps_cache'], 'the cache is invalidated before the verdict'),
    M('W61', CLI, [(", hint_kit(env)) if x}", ") if x}")],
      ['t_d5_stale_hint_never_checks'], 'tried lacks the HINT.json kit of the moment of the stop'),
    M('W62', CLI, [("    elif env.command != 'go' or k is None or k in h['tried']:", "    elif env.command != 'go' or k is None:")],
      ['t_d5_refused_clear_kit_keeps_cache'], 'the check ignores tried'),
    M('W64', CLI, [("    elif env.command != 'go' or k is None or k in h['tried']:", "    elif k is None or k in h['tried']:")],
      ['t_d5_found_answer_while_halted_print_stop'], 'found or answer start the check'),
    M('W66', CLI, [("    cl = None if h['code'].startswith('HALTED_') else {'code': h['code'], 'head_seq': h['head_seq'],\n"
                    "                                                       'kit_sha256': h['kit_sha256']}", "    cl = None")],
      ['t_d5_clear_check_found_accepted', 'D_clear_same_boot_setup_failed'], 'the clear records no cleared_local'),
    M('W67', PLACE, [("(os.lstat(target).st_mode & 0o777) == root_mode and {r[0]: r[1:] for r in walk(target)} == want",
                      "{r[0]: (r[1], r[3]) for r in walk(target)} == {k: (v[0], v[2]) for k, v in want.items()}")],
      ['t_d5_placement_accepts_equal_or_moves_aside'], 'settle compares paths, types and sizes only'),
    M('W68', CLI, [("old['step'], old.get('refused', 0)) if old.get('template') == body else (old['step'] + 1, 0)",
                    "old['step'], old.get('refused', 0)) if old.get('template') == body else (old['step'] + 1, "
                    "old.get('refused', 0))")],
      ['t_d3_refused_count_resets_per_block'], 'the refused count never resets'),
    M('W69', DRV, [("    if listing and not all(cps.values()):\n        return 'listing', None\n", "")],
      ['t_d4_parse_raw_rules'], 'a files element without the name counts as absence'),
    M('W70', DRV, [("            if i == len(objs) - 1 and (_token(env) or _token(sc)):", "            if False:")],
      ['t_d4_parse_raw_rules'], 'the next-page token is ignored'),
    M('W71', CLI, [("        if sha_bytes(b) != env.cfg['tool_inventory_sha256'] or N.tool_list(b) is None:",
                    "        if N.tool_list(b) is None:")],
      ['t_maint2_inventory_rehashed_at_attest'], 'TOOL_INVENTORY.txt not checked against its pin (tools=inventory)'),
    M('W72', CLI, [("or os.path.islink(p) or not os.path.isfile(p) \\\n            or os.path.realpath(p) != p or",
                    "or not os.path.isfile(p) \\\n            or")],
      ['t_maint2_tools_file_link_refused'], 'tools=file accepts a link (both link checks removed)'),
    M('W74', ENTRY, [("    if kind in ('GENESIS', 'RESTORE') and body['approval'] != 'none':",
                      "    if kind in ('GENESIS', 'RESTORE') and body['approval'] not in ('none', 'pending'):")],
      ['test_d6_entry_approval_must_be_none'], 'S1 accepts approval pending'),
    M('W75', ENTRY, [("\n                           or kind not in ('RESTORE', 'GENESIS')):", "):")],
      ['test_d5_cleared_local_only_on_restore_and_genesis'], 'S1 accepts cleared_local on any kind'),
    M('W79', CLI, [("        if bl.get('head_seq', -1) > hs:\n            bad = True\n        elif bl.get('head_seq') != hs:",
                    "        if bl.get('head_seq') != hs:")],
      ['t_gap05_block_ahead_invalidates_cache'], 'a BLOCK.json ahead of STATE moves alone'),
    M('W80', SESS, [("        if code or (w.get('cleared_local') and not kc['config_only']):", "        if code:")],
      ['test_d5_clearing_restore_refuses_release_change'], 'the clearing KIT_ACCEPT accepts a release change'),
    M('W81', CLI, [("    for root in (env.p.attest, env.lay.inbox):", "    for root in ():")],
      ['t_gap08_clear_moves_attest_and_inbox'], 'the clear leaves attest and inbox in place'),
    M('W82', CLI, [("        if os.path.lexists(p):\n            remove_tree(p)\n    body = drive.body_lines",
                    "        pass\n    body = drive.body_lines")],
      ['t_gap08_render_removes_stale_download_target'], 'render keeps an existing file at a DOWNLOAD target'),
    M('W85', CLI, [("    if ((st or {}).get('halt_local') or (wk or {}).get('halt_local')) and not os.path.lexists(env.p.halt):\n"
                    "        bad = True\n", "")],
      ['t_gap12_halt_removed_out_of_procedure_restores'], 'load_cache accepts halt_local without HALT.json'),
    M('W86', SP, [("        if t['need'] == 'upload' and not reprint:", "        if t['need'] == 'upload':")],
      ['t_op02_reprint_has_no_upload_lines'], 'a reprint keeps the UPLOAD lines'),
    M('W87', CLI, [("        os.replace(raw, fresh(env, 'raw/' + at + '_', '.json'))", "        pass")],
      ['t_op03_raw_file_consumed'], 'an accepted raw file stays where it was'),
    M('W89', SESS, [("    if w.get('approval') is None:                                                   # D6: before any FIND\n"
                     "        return 'APPROVAL', Ask({'approval': 'APPROVAL'}, {'action': 'APPROVAL', 'state_code': 'RESTORE'})\n"
                     "    hs = head_search(series, (w.get('hint') or {}).get('seq'), pre_commit(w, g), g, now)\n"
                     "    if 'need' in hs:\n        return 'HEAD', _search_step(hs, series, sf)",
                     "    hs = head_search(series, (w.get('hint') or {}).get('seq'), pre_commit(w, g), g, now)\n"
                     "    if 'need' in hs:\n        return 'HEAD', _search_step(hs, series, sf)\n"
                     "    if w.get('approval') is None:\n"
                     "        return 'APPROVAL', Ask({'approval': 'APPROVAL'}, {'action': 'APPROVAL', 'state_code': 'RESTORE'})")],
      ['test_d6_approval_before_head'], 'APPROVAL comes after HEAD'),
    M('W91', CLI, [("    cl = None if h['code'].startswith('HALTED_') else {", "    cl = {")],
      ['t_d5_halted_restore_no_cleared_local'], 'a RESTORE while HALTED records cleared_local'),
    M('W97', CLI, [("    tried = {x[:12] for x in (kit, c.get(", "    tried = {x[:12] for x in (c.get(")],
      ['t_d5_halted_kit_never_checks'], 'tried does not take the halted kit'),
    M('W100', CLI, [("            if x.name != '.boot':", "            if True:")],
      ['t_d5_clear_check_found_accepted', 't_d5_wait_approval_in_clearing_restore'], 'invalidate moves the boot mark'),
    M('W101', CLI, [("    if h is None:\n        stop_block(env, 'UNCLASSIFIED')", "    if h is None:\n        return")],
      ['t_d5_damaged_halt_stops_unclassified'], 'clear_check returns when HALT.json is not valid'),
    M('W103', CLI, [("        c.update(copies=None, dl=False, slips=c['slips'] + 1)", "        c.update(copies=None, dl=False, slips=0)")],
      ['t_d5_clear_check_bounded'], 'a re-FIND of the clear check resets its slips'),
    M('W106', 'cpsvm2/vio/v1reuse.py', [("        make_writable_tree(root)", "        pass")],
      ['test_d16_evict_runner_frozen_folder_nonroot', 't_d16_settle_moves_readonly_target_aside'],
      'remove_tree does not make the tree writable', nonroot=True),
    M('W107', PLACE, [("                os.chmod(target, (os.lstat(target).st_mode & 0o777) | 0o200)", "                pass")],
      ['t_d16_settle_moves_readonly_target_aside'], 'settle moves a target aside without its write bit', nonroot=True),
    M('W108', CLI, [("        require_space(env.lay, N.STAGE_FREE_BYTES, 'stage')", "        pass")],
      ['t_d16_stage_refuses_low_space_before_runner'], 'run_stage has no require_space before a chain'),
    M('BUG1', SP, [("        if shas[v['path']] != by[v['name']]['sha256'] and shas[v['path']] in ours:",
                    "        if shas[v['path']] in ours and {f['sha256']: f['name'] for f in by.values()}[shas[v['path']]] "
                    "!= v['name']:")],
      ['t_commit_identical_parts_confirmed', 't_commit_entry_then_parts'],
      'T found this: identical files of one loop gave COPY_MISMATCH (the r5 on_verify form)'),
]
W13 = M('W13', 'session_start.sh', [('# 6. the checked-out commit is the one named, before anything runs from it (S-08)\nHEAD=$(git -C "$BASE/repo" rev-parse HEAD 2>/dev/null) || stop SESSION_GIT_ERROR\n[ "$HEAD" = "$COMMIT" ] || stop SESSION_COMMIT_MISMATCH\n\n', ''), ('# 4. setup once per boot', '# 6. the checked-out commit is the one named, before anything runs from it (S-08)\nHEAD=$(git -C "$BASE/repo" rev-parse HEAD 2>/dev/null) || stop SESSION_GIT_ERROR\n[ "$HEAD" = "$COMMIT" ] || stop SESSION_COMMIT_MISMATCH\n\n' + '# 4. setup once per boot')],
        ['test_s08_wrong_head_stops_before_setup'], 'the HEAD check comes after the launcher and hint steps')
HAND.append(W13)
# Track M mutants (built by M, ported by T): maint/*, killed by test_maint.
HAND.append(M('W29a', 'cpsvm2/maint/assemble.py', [("            if tag not in F.QUAL_ROOT or r['job_dir'] != F.job_dir_of(base, tag, case):\n                raise Bad('LAYOUT_PATH', r['job_dir'])\n", '')], ['test_maint1_forged_all_frozen_job_dir', 'test_maint1_wrong_mapping_refused'], 'track M: W29a'))
HAND.append(M('W29b', 'cpsvm2/maint/assemble.py', [("        if r != self.real and not r.startswith(self.real + '/'):\n            raise Bad('LAYOUT_PATH', d)\n", '')], ['test_maint1_symlink_after_begin_refused'], 'track M: W29b (GAP-3: a self-consistent base cannot leave the root without a link)'))
HAND.append(M('W30', 'cpsvm2/maint/assemble.py', [("    ap.add_argument('--root')\n", "    ap.add_argument('--root', default='/')\n"), ("    if not (a.root and os.path.isabs(a.root) and os.path.isdir(a.root) and not os.listdir(a.root)\n            and os.path.realpath(a.root) != '/'):\n", '    if not os.path.isabs(a.root):\n')], ['test_maint1_assemble_root_required_empty_dedicated'], 'track M: W30'))
HAND.append(M('W93', 'cpsvm2/maint/assemble.py', [("        base = lay.get('base') if isinstance(lay, dict) else None\n", "        base = af['genesis']['base']\n"), (" and lay == F.layout_of(base)\n                and af['genesis']['base'] == base):", '):')], ['test_maint1_assemble_base_from_genesis'], 'track M: W93'))
HAND.append(M('W33', 'cpsvm2/maint/score_check.py', [("    if not isinstance(au.get('o63'), dict) or au['o63'].get('missing') != []:\n", '    if False:\n')], ['test_maint2_score_check_requires_tools_attestation_and_states_isolation'], 'track M: W33'))
HAND.append(M('W34', 'cpsvm2/maint/audit.py', [("        if doc['kind'] == 'CLEAR' and not S.clear_ok(", '        if False and not S.clear_ok(')], ['test_maint3_audit_refuses_unauthorized_clear'], 'track M: W34'))
HAND.append(M('W36', 'cpsvm2/maint/audit.py', [("        if code:\n            self.add('AUD_KIT_CHANGE', name, code)\n", '')], ['test_maint4_audit_only_kit_change_verdicts'], 'track M: W36'))
HAND.append(M('W37', 'cpsvm2/maint/score_check.py', [("    if asm.get('verify_frozen') is not True or any(x.get('verify') != 'DONE' for x in asm['runs']):\n", '    if False:\n')], ['test_maint5_score_check_refuses_unverified_assembly'], 'track M: W37'))
HAND.append(M('W41', 'cpsvm2/maint/score_check.py', [("    pl = placed(*plan(a.audit, a.assembled, a.pool, a.owner_checks), os.path.dirname(os.path.abspath(a.plan)))\n    if doc_bytes(pl) != pl_raw:\n        raise Refused('PLAN_MISMATCH')\n", '    pl = sjson(pl_raw)\n')], ['test_maint8_check_detects_edited_plan'], 'track M: W41'))
HAND.append(M('W42', 'cpsvm2/maint/audit.py', [("'window': [utc_minus(head['utc'], tol), utc_minus(restore['utc'], -tol)]", "'window': [head['utc'], restore['utc']]")], ['test_maint9_review_window_widened'], 'track M: W42'))
HAND.append(M('W43', 'cpsvm2/maint/audit.py', [("            elif doc['kind'] == 'GENESIS' and doc['body']['jobs'] not in (None, self.kit_jobs(doc, ki)):\n                self.add('AUD_KIT', name, 'jobs')\n", '')], ['test_maint10_genesis_jobs_differ_from_kit_unclean'], 'track M: W43'))
HAND.append(M('W55', 'cpsvm2/maint/audit.py', [("            if doc['cleared_local'] is not None:\n                self.cleared_local(doc)\n", '')], ['test_maint3_audit_checks_cleared_local'], 'track M: W55'))
HAND.append(M('W56', 'cpsvm2/maint/audit.py', [("        if r.get('mimeType') == FOLDER_MIME:\n", '        if False:\n')], ['test_maint7_drill_listing_with_folder_rows_clean'], 'track M: W56'))
HAND.append(M('W83', 'cpsvm2/maint/audit.py', [("            if doc['kind'] == 'FROZEN':\n                self.o63_frozen(doc, files, s2['runs'][doc['body']['run']], ai)\n", '')], ['test_gap10_generation_record_tied_to_g_entry'], 'track M: W83'))
HAND.append(M('W94', 'cpsvm2/maint/audit.py', [("for d in ch if d['kind'] in ('GENESIS', 'RESTORE')]", 'for d in ch if False]'), ("if d['kind'] == 'RESTORE' and i and ch[i - 1]['boot_id'] == d['boot_id']]", 'if False]')], ['test_gap06_audit_lists_approvals_and_same_boot_restores'], 'track M: W94'))
# appended to mutants.py HAND (T, batch 2): each the 2015773 behaviour or one v2.1 rule removed
W2 = [
    M('W19', SP, [("        unknown = [c for c in cps if c[0] not in ids]\n",
                   "        unknown = [c for c in cps if c[0] not in ids]\n        if any(c[1] != f['bytes'] for c in unknown):\n"
                   "            return 'stop', 'FORK'\n")],
      ['t_opx03_size_slip_refinds'], 'a size other than ours at found is STOP FORK'),
    M('W21', CLI, [("        return 'FINAL_MESSAGE_INVALID utf8'\n",
                    "        return 'FINAL_MESSAGE_INVALID utf8'\n    if any(ch in raw for ch in b'{}<>'):\n"
                    "        return 'FINAL_MESSAGE_INVALID characters'\n")],
      ['t_opx05_final_message_any_characters_verbatim'], 'the brace and angle-bracket rule is back'),
    M('W90', CLI, [("    if os.path.islink(fmp) or not fmp.is_file():\n        return 'FINAL_MESSAGE_INVALID missing'",
                    "    if os.path.islink(fmp) or not fmp.is_file() or os.lstat(fmp).st_size == 0:\n"
                    "        return 'FINAL_MESSAGE_INVALID missing'")],
      ['t_opx05_empty_final_message_accepted'], 'the non-empty final-message check is back'),
    M('W98', CLI, [("        raise Halt('STOP', 'AI_OUTPUT_TOO_LARGE', 'the final message is over max_ai_output_bytes')",
                    "        return 'FINAL_MESSAGE_INVALID size'")],
      ['t_opx05_oversize_final_message_stops'], 'an over-size final message is a counted refusal'),
    M('W47', CLI, [("    members.append(('attest/final_message.txt', 'file', 0o644, raw))\n",
                    "    if ro['role'] == 'G':\n        members.append(('attest/final_message.txt', 'file', 0o644, raw))\n"),
                   ("    if ctx['revision'] == 1:\n        tl = tools_of(env, got['tools'])",
                    "    if ctx['revision'] == 1 and ro['role'] == 'G':\n        tl = tools_of(env, got['tools'])")],
      ['t_maint2_s_v_entries_archive_message_and_tools'], 'S and V entries without the final message or tools'),
    M('W31', NAMES, [("'TOOLS': r'inventory|file:", "'TOOLS': r'none|inventory|file:")],
      ['t_maint2_tools_none_refused_inventory_file_accepted'], 'tools=none is accepted', ),
    M('W32', WRK, [(",\n               'notes': N.O63_NOTE % at['tools_present']['sha256']}", "}")],
      ['t_maint2_generation_record_tools_and_o63_note'], 'the generation record has no notes'),
    M('W49', CLI, [("    return 'SELFTEST_DIED' if fg['kind'] == 'selftest' else 'FOREGROUND_DIED'",
                    "    return 'SELFTEST_DIED' if fg['kind'] == 'selftest' else None")],
      ['test_foreground_died_same_boot_stops'], 'foreground_check drops this boot FOREGROUND.json without a STOP'),
    M('W50', CLI, [("'head_seq': seq or 0,\n                                       'kit_sha256': kit,",
                    "'head_seq': 0 if code == 'FOREGROUND_DIED' else seq or 0,\n"
                    "                                       'kit_sha256': None if code == 'FOREGROUND_DIED' else kit,")],
      ['t_opx07_stage_death_stop_names_real_head_and_kit'], 'HALT.json records head 0 and no kit after a stage death'),
    M('W51', SESS, [("    if row == 'C2':                         # SD-51: a RESTORE while HALTED keeps the halted kit; the CLEAR takes it\n"
                     "        kc = None\n", ""),
                    ("'kit_sha256': st['kit_sha256'] if row == 'C2' else w['kit']['sha256'],", "'kit_sha256': w['kit']['sha256'],")],
      ['test_session_c2_clear_restore_keeps_kit_then_clear_takes_it'], 'the RESTORE while HALTED takes the new kit'),
    M('W53', WRK, [("            if ci['resolution'].get('conversation'):                                 # INT-R2-03\n"
                    "                a['conversation'] = ci['resolution']['conversation']\n", "")],
      ['t_int_r2_03_interrupt_gets_conversation_id'], 'the interrupt argv ignores the resolution conversation'),
    M('W58', 'cpsvm2/vio/v1mod.py', [("    for g in globs:\n        for p in list(g):", "    for g in []:\n        for p in list(g):")],
      ['test_foreground_died_same_boot_stops'], 'cleanup_leftovers is a no-op'),
    M('W60', CLI, [("        clear_check(env)\n        if env.cache is not None and env.cache.get('post') and env.pending is None:\n"
                    "            run_post(env)                   # S-04: owed by an earlier command; a pending commit finishes first\n",
                    "        if env.cache is not None and env.cache.get('post') and env.pending is None:\n"
                    "            run_post(env)\n        clear_check(env)\n")],
      ['t_d5_post_action_halt_cleared_same_boot'], 'the post resume runs before clear_check'),
    M('W63', CLI, [("for x in (kit, c.get('kit_sha256') or (w.get('kit') or {}).get('sha256'), hint_kit(env))",
                    "for x in (kit, hint_kit(env))")],
      ['t_d5_kit_in_use_never_checks'], 'tried does not take the kit in use'),
    M('W65', CLI, [("    h['tried'], h['check'] = sorted(set(h['tried']) | {h['check']['kit12']}), None\n    durable.write_doc(env.p.halt, h)",
                    "    h['tried'], h['check'] = sorted(set(h['tried']) | {h['check']['kit12']}), None\n    os.unlink(env.p.halt)")],
      ['t_d5_refused_clear_kit_keeps_cache'], 'a refused candidate removes HALT.json'),
    M('W76', WRK, [("        before = info.get('rewalk') and os.path.lexists(info['job_dir']) and rewalk(env, info, snap)  # GAP-02",
                    "        before = False")],
      ['t_gap02_files_found_before_settle', 'D_clear_same_boot_open_generator'], 'files_found is computed after settle only'),
    M('W77', CLI, [("    if len(shas) > 1 or (mp.get('name') == os.path.basename(path) and shas != {mp['sha256']}):",
                    "    if len(shas) > 1:")],
      ['t_gap04_moved_pending_foreign_copy_forks', 'D_clear_same_boot_fork_foreign_only'], 'the clearing restore adopts a single copy at the moved PENDING seq'),
    M('W78', SESS, [("    if not (F.is_q(st) or (w.get('moved_pending') or {}).get('uploaded')):        # SD-59",
                     "    if not (F.is_q(st) and hs['via'] != 'hint'):")],
      ['test_op05_recheck_after_every_q_restore'], 'RECHECK is skipped on the hint path'),
    M('W88', DRV, [("                if cps[r['title']].setdefault(r['id'], int(sz)) != int(sz):",
                    "                if cps[names[els.index(el)]].setdefault(r['id'], int(sz)) != int(sz):")],
      ['t_d4_swapped_elements_assigned_by_title'], 'copies are assigned by element position'),
    M('W92', CLI, [("    if env.command == 'found' and h['check'] and b and b['expect'].get('kind') == 'clear':",
                    "    if False:")],
      ['t_d5_clear_check_found_accepted'], 'found for the check own block prints the STOP'),
    M('W96', SESS, [("        return 'C8b', {'run': cur, 'reprepare': R['reprepares'] == 0}",
                     "        return 'C8b', {'run': cur, 'reprepare': True}")],
      ['test_gap13_c8b_after_second_restore_abandons'], 'C8b re-prepares whatever reprepares says'),
    M('W102', CLI, [("    emit(env, 'STOP', PrintBlock('STOP', do=('STOP', {'code': h['code'], 'handback': 'C'})), {'command': 'none'},\n"
                     "         (h['head_seq'], h['kit_sha256']))",
                     "    emit(env, 'STOP', PrintBlock('STOP', do=('STOP', {'code': h['code'], 'handback': 'C'})), {'command': 'none'},\n"
                     "         (h['head_seq'], (env.cache or {}).get('kit_sha256') or ((env.work or {}).get('kit') or {}).get('sha256')))")],
      ['t_d5_halted_kit_never_checks'], 'a STOP header shows the kit in use instead of HALT.json'),
    M('W109', CLI, [("            elif act[0] == 'DROP_LOCAL':\n", "            elif act[0] == 'DROP_LOCAL' and False:\n")],
      ['test_d16_disk_bounded_over_runs'], 'the DROP_LOCAL post action removes nothing'),
    M('W110', CLI, [("                place.evict(env.lay, act[1], act[2], act[3], act[4])", "                pass")],
      ['test_d16_disk_bounded_over_runs'], 'the EVICT post action leaves the job folder'),
    M('W24', 'session_start.sh', [('[ "$KIT" = none ] && HINT="" KIT=""\n', '')],
      ['test_opx08_kit_none_bootstraps_without_hint'], '--kit none is a usage error'),
    M('W73', 'session_start.sh', [('  rm -f "$BASE/outbox/v2/HINT.json" || stop SESSION_LAYOUT\n', '  true\n')],
      ['test_opx08_kit_none_bootstraps_without_hint'], 'a no-hint bootstrap keeps an older HINT.json'),
    M('W84', 'session_start.sh', [('find "$REPO" -name __pycache__ -type d -prune -exec rm -rf {} + || stop SESSION_LAYOUT\n', '')],
      ['test_gap11_session_start_removes_pycache'], 'session_start.sh keeps __pycache__ folders'),
    M('W11', 'session_start.sh', [('exec python3 -I -B -X pycache_prefix=/dev/null %q', 'exec python3 -I -B %q')],
      ['t_l13_launcher_ignores_bytecode'], 'the launcher has no -X pycache_prefix'),
    M('W27', 'tests/run_tests.py', [("    if unknown:\n        print(", "    if False:\n        print(")],
      ['t_only_unknown_name_exits_2'], 'unknown --only names are ignored'),
    M('W20', 'README.md', [('When in doubt, answer `UNSURE`.', 'When in doubt, answer `NOTHING_WRITTEN`.')],
      ['t_l14_readme_rules'], 'the README outcome rule is removed'),
    M('W95', 'README.md', [('If you are not sure whether the platform refused an upload or failed, treat it as refused.',
                            'If you are not sure whether the platform refused an upload, continue.')],
      ['t_l14_readme_rules'], 'the UPLOAD_REFUSED row says or tells you to continue again'),
    M('W104', 'README.md', [('`include_base64` false', '`include_base64` true')],
      ['t_l14_readme_rules'], 'the DOWNLOAD sentence is the r4 one'),
    M('W105', 'README.md', [('Never work around a refused upload', 'Work around a refused upload')],
      ['t_l14_readme_rules'], 'the never-work-around sentence is removed'),
    M('W38', MK, [("        top = max(g[p][0] for p in safe)\n", "        if len(g) > 1:\n            problems.append(f'{sorted(g)[0]}: the copies disagree')\n        top = max(g[p][0] for p in safe)\n")], ['test_mk1_header_slip_in_one_copy_recovers'],
      'make_kit path disputes are not settled'),
    M('W39', MK, [("            if n in binnames:\n                raise Fail(f'{n}: two binary members would share one file name')\n", "")], ['test_mk2_duplicate_binary_names_refused'],
      'pack accepts duplicate binary names'),
    M('W14', CLI, [("        os.makedirs(os.path.dirname(p), exist_ok=True)\n        if os.path.lexists(p):\n            remove_tree(p)",
                    "        if os.path.lexists(p):\n            remove_tree(p)")],
      ['t_s09_download_parent_exists_when_printed'], 'render does not create DOWNLOAD parents'),
]
HAND.append(M('W48', 'cpsvm2/maint/audit.py', [("                self.add('AUD_DUPLICATE_SEQ', next(iter(groups.values()))[0]['name'])",
                                               "                pass")],
               ['D_refuse_reset_approval_wrong_none'], 'the audit treats two sha256 values of one name as harmless'))
HAND.append(M('W26', 'README.md', [('(prepare, generator, finish with p PNG parts, visual reviewer, freeze; p is 1 to 3) | 16 |',
                                     '(prepare, generator, finish with p PNG parts, visual reviewer, freeze; p is 1 to 3) | 17 |')],
               ['t_l14_readme_rules'], 'one count of README section 7 is off by one'))
HAND.append(M('W99', 'tests/fakes.py', [("        self.tally.append({'argv0': argv[0], 'drive': len(self.w.drive.calls) - d0, 'boot': self.w.boot})\n",
                                         "")],
               ['test_opx10_tool_calls_match_budget_golden'], 'FakeDot counts Drive calls only (no helper commands)'))
HAND += W2
ASM = 'cpsvm2/maint/assemble.py'
HAND.append(M('W111', ASM, [("            argv, ns = view(base, self.real, rn)\n", "            argv, ns = [], None\n"),
                            ("'verify-frozen', '--job-dir', x['job_dir']]", "'verify-frozen', '--job-dir', x['path']]")],
               ['D_baseline'], 'GAP-2: verify-frozen runs at the assembled path without the namespace view (746ea98)'))
HAND.append(M(
    'W113', NAMES, [("'(owner decision O63): neither enforced nor audited. The tools of each conversation are recorded in its AI '\n"
                     "              'entry (for generators also in GENERATION_RECORD.json) as the operator attested them: the kit inventory '\n"
                     "              \"TOOL_INVENTORY.txt by sha256 (the platform's usual set, not that conversation's own list) or a list the \"\n"
                     "              'operator saved.')",
                     "'(owner decision O63): neither enforced nor audited. The tools present in each conversation are recorded '\n"
                     "              'in its AI entry and, for generators, in GENERATION_RECORD.json.')")],
    ['test_gap8_isolation_statement_matches_inventory_attestation'], 'GAP-8: the 746ea98 isolation statement'))
HAND.append(M('W114', 'README.md', [('| 18 | 15 | 8 | 0 to 2 | 3 (2 waits) | about 45 |', '| 23 | 16 | 9 | 0 to 2 | 3 (2 waits) | about 45 |')],
               ['t_l14_readme_rules'], 'GAP-7: the README restore row is not the measured golden'))
HAND.append(M('W115', 'README.md', [("any characters, up to the kit's max_ai_output_bytes, larger: `STOP AI_OUTPUT_TOO_LARGE HANDBACK C`;",
                                     'any characters, any length;')],
               ['t_l14_readme_rules'], 'GAP-9: the README final-message sentence of 746ea98'))
HAND.append(M('W112', ASM, [('mount -c --bind "$2" "$1"; ', '')], ['D_baseline'],
               'GAP-2: the namespace has its tmpfs but no bind of <root><base> onto <base>'))
# Amendment from probes M008-M012 (delta v2.1 §9): W116-W131.
SS, V1M = 'session_start.sh', 'cpsvm2/vio/v1mod.py'
A1T = ['test_a1_base_required_outside_home_and_carried_by_launcher']
G5L = 'B=$(cd "$BASE" 2>/dev/null && pwd -P)/ H=$(cd "$HOME" 2>/dev/null && pwd -P)/; case "$B" in "$H"*|/) stop SESSION_LAYOUT ;; esac'
HAND += [
    M('W116', SS, [('BASE="${CPS_VM_BASE:-}"', 'BASE="${CPS_VM_BASE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)}"')],
      A1T, 'A1: a missing CPS_VM_BASE silently takes the base from the script\'s location'),
    M('W117', SS, [(G5L + '\n', '')], A1T,
      'A1: a base inside HOME (the old ~/cps) is accepted'),
    M('W118', SS, [('\\nexport CPS_VM_BASE=', '\\nCPS_VM_BASE=')], A1T,
      'A1: vm.sh sets BASE and TOOLS without exporting them, so the helper does not see them'),
    M('W119', ASM, [('(\'cd "$1"; mount -t tmpfs cps_vm2 "$1"; shift; ', '(\'mount -t tmpfs cps_vm2 "$1"; cd "$1"; shift; ')],
      ['test_a1_verify_view_root_under_tmpfs_ancestor'], 'A1: the tmpfs is mounted before cd, so a root under it is hidden'),
    M('W120', CLI, [('    except OSError as e:                            # A3: an OSError (EROFS) anywhere ends in a block, '
                     'never a traceback\n', '    except KeyboardInterrupt as e:\n'),
                    ('    except OSError as e:                            # A3: also one raised while a STOP is being handled\n',
                     '    except KeyboardInterrupt as e:\n')],
      ['test_a3_erofs_ends_in_stop_block'], 'A3: an OSError outside run_command\'s own handler is a traceback'),
    M('W121', DUR, [("else 'READ_ONLY_FS' if e == errno.EROFS else 'WRITE_FAILED'", "else 'WRITE_FAILED'")],
      ['test_a3_erofs_ends_in_stop_block'], 'A3: EROFS is reported as WRITE_FAILED'),
    M('W122', V1M, [("lay.runtime.glob('.tmp_[0-9]*_*'), ", '')],
      ['t_a4_stale_temp_names_in_runtime_ignored', 'D_sameboot_damaged_cache_restores'],
      'A4a: a killed write_atomic\'s temp name in runtime/ stays and changes the kit check'),
    M('W123', V1M, [(", (lay.inbox / 'journal').glob('.*')]", ']')], ['t_a4_stale_png_stream_and_validate_removed'],
      'A4b: a killed placement\'s .png_stream_<pid> stays in inbox/journal for the rest of the boot'),
    M('W124', V1M, [("            globs.append(root.glob('*/.validate_*'))\n", '')],
      ['t_a4_stale_png_stream_and_validate_removed'], 'A4c: the runner\'s stale .validate_ folders stay'),
    M('W125', CLI, [("    remove_tree(env.lay.base / 'tmp')               # A6: a killed stage's temporary files go; the "
                     "runner's TMPDIR\n    (env.lay.base / 'tmp').mkdir()\n", "    (env.lay.base / 'tmp').mkdir(exist_ok=True)\n")],
      ['t_a6_stage_empties_tmp_and_sets_tmpdir'], 'A6: BASE/tmp is not emptied before a stage'),
    M('W126', CLI, [("    os.environ['TMPDIR'] = str(env.lay.base / 'tmp')\n", '')], ['t_a6_stage_empties_tmp_and_sets_tmpdir'],
      'A6: the stage\'s tools keep the inherited TMPDIR'),
    M('W127', CLI, [("    if marker(env.lay.tools / SETUP_DONE) != [env.boot, host.repo_commit(env.lay) or '']:", "    if False:")],
      ['t_a5_stage_stops_setup_missing', 'D_tools_wiped_same_boot_continues'],
      'A5: a stage runs without the setup of this boot and commit'),
    M('W128', NAMES, [('STAGE_FREE_BYTES = 1048576, 2000, 2000000000', 'STAGE_FREE_BYTES = 1048576, 2000, 1000000000')],
      ['t_d16_stage_refuses_low_space_before_runner'], 'A7: the stage check of r5 (1 GB), under the M009 peak on /tmp'),
    M('W129', NAMES, [("pre = base.rstrip('/') + '/deliveries/' + case + '/'", "pre = base.rstrip('/') + '/cps-deliveries/' + case + '/'")],
      ['test_transcript_and_copy_codes', 'test_names_patterns'], 'A1: the personal copy is not taken from BASE/deliveries'),
    M('W130', 'README.md', [('through the elevated route (`sandbox_permissions` set to\n`require_escalated`)',
                             'through the standard route (`sandbox_permissions` set to\n`use_default`)')],
      ['t_l14_readme_rules'], 'A2: the README sends the bootstrap through the standard route'),
    M('W131', 'README.md', [('never start that command again yourself. Run\n   `go` once', 'run that command again. Run\n   `go` once')],
      ['t_l14_readme_rules'], 'A3: the README lets the Dot re-run a command that died'),
]
# The amendment's fix round (delta v2.1 §9.8): W132-W143.
HAND += [
    M('W132', CLI, [("    remove_tree(env.lay.base / 'tmp')               # A6: a killed stage's temporary files go; the "
                     "runner's TMPDIR\n    (env.lay.base / 'tmp').mkdir()\n    os.environ['TMPDIR'] = str(env.lay.base / 'tmp')\n"
                     "    if kind == 'chain':\n        require_space(env.lay, N.STAGE_FREE_BYTES, 'stage')\n",
                     "    if kind == 'chain':\n        require_space(env.lay, N.STAGE_FREE_BYTES, 'stage')\n"
                     "    remove_tree(env.lay.base / 'tmp')\n    (env.lay.base / 'tmp').mkdir()\n"
                     "    os.environ['TMPDIR'] = str(env.lay.base / 'tmp')\n")],
      ['t_g2_tmp_emptied_before_space_check'], 'G2: the space check runs before BASE/tmp is emptied'),
    M('W133', V1M, [("lay.runtime.glob('.tmp_[0-9]*_*')", "lay.runtime.glob('.tmp_[0-9]_*')")],
      ['t_a4_stale_temp_names_in_runtime_ignored'], 'G4: only one-digit pids are removed from runtime/'),
    M('W134', SS, [(G5L, 'case "$BASE/" in "$HOME"/*) stop SESSION_LAYOUT ;; esac')], A1T,
      'G5: the HOME check compares the paths as written (2cfaac5)'),
    M('W135', SS, [('case "$B" in "$H"*|/)', 'case "$B" in "$H"?*|/)')], A1T, 'G5: a base equal to HOME is accepted'),
    M('W136', CLI, [("        res = {'status': 'halt', 'code': durable.DurableError(e.errno).code}",
                     "        res = {'status': 'halt', 'code': 'DISK_FULL' if e.errno == 28 else 'WRITE_FAILED'}")],
      ['test_g3_erofs_inside_a_stage_stops_read_only_fs'], 'G3: an EROFS inside a stage is WRITE_FAILED'),
    M('W137', NAMES, [('STAGE_FREE_BYTES = 1048576, 2000, 2000000000', 'STAGE_FREE_BYTES = 1048576, 2000, 1500000000')],
      ['t_d16_stage_refuses_low_space_before_runner'],
      'CC-2: the amendment\'s 1.5 GB stage check, under the finish stage\'s peak with its save'),
    M('W138', 'probe_p5.py', [("    ap.add_argument('--dir', required=True)                     # G8: never a default under HOME "
                               "(read-only on the Dot)",
                               "    ap.add_argument('--dir', default=os.path.join(os.environ.get('HOME', '/nonexistent'), "
                               "'cps_probe_p5'))")],
      ['test_g8_dir_required_never_under_home'], 'G8: probe_p5.py defaults its folder under HOME'),
    M('W139', 'README.md', [('export CPS_VM_BASE=/tmp/cps\n[ -d /tmp/cps/repo/.git ]', '[ -d /tmp/cps/repo/.git ]')],
      ['test_pf2_clear_bootstrap_runs_in_a_fresh_shell', 't_l14_readme_rules'],
      'CC-3/PF-2: the bootstrap block (and so every clear message) without its export line'),
    M('W140', 'README.md', [("The maintainer's message gives you the bootstrap of\nsection 1 with its values filled in (`COMMIT`, "
                             "`--hint` and a new `--kit` value). Run it exactly, as one command\nthrough the elevated route, then "
                             "`go`.", "The maintainer's message gives you a bootstrap line\nwith a new `--kit` value. Run that line "
                             "exactly, then `go`.")],
      ['t_l14_readme_rules'], 'PF-2: README section 6 asks for the one-line clear of 2cfaac5'),
    M('W141', 'README.md', [("Between two checks of\n   such a conversation run `sleep 300` in the foreground through the standard "
                             "route. ", '')],
      ['t_l14_readme_rules'], 'PF-3: the README gives no waiting method between conversation checks'),
    M('W142', 'README.md', [(' and the claim is younger than 6\n   hours', '')],
      ['t_l14_readme_rules'], 'PF-1: the README omits the 6-hour claim rule'),
    M('W143', 'README.md', [('This is the one HANDBACK C stop you clear yourself: tell the owner, run the bootstrap\n  once '
                             '(with your notes), then `go`.', 'Tell the owner and wait for a maintainer message.')],
      ['t_l14_readme_rules'], 'PF-8: SETUP_MISSING waits for a maintainer message although the bootstrap cures it'),
]
HAND_OPEN = {'W57': 'retired in r4 (APPROVAL comes before HEAD): no mutant'}
# Builder mutants whose path v2.1 deleted (§2.13, §2.15.1): no substitution, recorded with the reason.
DELETED = {'G2': 'md5-visible mode is deleted: every copy with an unknown id is downloaded back (rule V, §2.1); G26 and '
                 'G32 are the download-back mutants',
           'G29': 'the listing route of the head search is deleted (OPENED and the listing, §2.13); a lookup is a FIND',
           'G4': 'the OPENED status is deleted (§2.13): no START is OPENED, so T43 has no OPENED case',
           'W57': 'retired in r4 (APPROVAL comes before HEAD)'}

# Builder mutants G1-G34 and M2-nn of the 2015773 build: kept as written; a substitution whose old text is gone in
# v2.1 is re-targeted to the v2.1 text of the same rule; a mutant whose path is deleted is in DELETED.
LEGACY = [
    M('G1', SP, [("    grp = _group(loop)\n    if not grp:\n        return None",
                  "    grp = _group(loop)\n    if not grp or loop.get('entry') and loop['entry']['copies'] is not None:\n        return None"),
                 ("[{'id': c[0], 'md5': c[1], 'size': c[2]} for c in f['copies']]",
                  "[{'id': c[0], 'md5': c[1], 'size': c[2]} for c in f['copies'] or []]")],
      ['t_commit_entry_then_parts', 'test_op03_truncated_all_frozen_part_reuploaded_before_handback_b'],
      'savepoint finishes the commit (and prints the next block) once the entry is confirmed, parts unconfirmed',
      ['M28']),
    M('G3', SESS, [("    if not twice or ab[-1] - ab[0] >= w:\n        return 'A'", "    if True:\n        return 'A'")],
      ['test_fork_at_restore_lagging_n_plus_1', 'test_head_search_wait_between_absences'],
      'the head search accepts a single absence of N+1'),
    M('G5', FOLD, [("    if ro['status'] == 'CONTINUED':\n        return ('T46'", "    if False:\n        return ('T46'")],
      ['test_f1_core_continued_v_is_t46'], 'a continued V is resolved like a started one (T46 removed)'),
    M('G6', WRK, [("    return any(r[1] == 'file' and ('job/%s/%s' % (rel, r[0]), r[4]) not in snap",
                   "    return False and any(r[1] == 'file' and ('job/%s/%s' % (rel, r[0]), r[4]) not in snap")],
      ['test_rewalk_reports_a_file_not_in_the_snapshot', 'test_rewalk_forces_written'],
      'the re-walk (§8.6 step 3) never reports a file', ['M07', 'M29', 'M32']),
    M('G7', 'cpsvm2/vio/v1mod.py',
      [("        raise Halt('STOP', 'WALK_UNSUPPORTED_ENTRY', 'an entry the archive format does not keep', "
        "detail={'class': why})", "        return None")],
      ['t_walk_strict_unsupported_entries', 'test_safe01_unsupported_entries_halt_nothing_deleted'],
      'tree_list ignores unsupported entries', ['M17', 'M37']),
    M('G8', CLI, [("    if b is None or at != b['at']:\n        refuse(env, 'STALE_AT')\n    ex = b['expect']\n"
                   "    if ex.get('command') != 'found':",
                   "    if b is None:\n        refuse(env, 'STALE_AT')\n    ex = b['expect']\n"
                   "    if ex.get('command') != 'found':"),
                  ("    if b is None or at != b['at']:\n        refuse(env, 'STALE_AT')\n    ex = b['expect']\n"
                   "    if ex.get('command') != 'answer':",
                   "    if b is None:\n        refuse(env, 'STALE_AT')\n    ex = b['expect']\n"
                   "    if ex.get('command') != 'answer':")],
      ['test_stale_at_refused'], 'the --at check is removed'),
    M('G9', PLAN, [("    if bind is not None and not div:", "    if False:")],
      ['test_imp07_chain_rows_first_match_none_shadowed', 'test_next_action_resolution_chains_and_rerun'],
      'rebase_bind is ignored by the chain table (an unbound rebase re-run)', ['M09']),
    M('G10', OUT, [("    if fz['final_next'] in ('GENERATE', 'SCOPE_READER') and not interrupted:\n        return 'EMPTY'",
                    "    if False:\n        return 'EMPTY'")],
      ['test_f4_outcomes_total_over_frozen_shapes'], 'outcomes D6 removed (SCORE for a run frozen at GENERATE)'),
    M('G11', 'cpsvm2/maint/score_check.py',
      [("'case_id': c,\n                    'reader': rd,", "'case_id': c,\n                    'reader': 'A',"),
       ("path, got = os.path.join('carriers', rd, c, 'EMPTY_CARRIER.json'), sha(data)",
        "path, got = os.path.join('carriers', c, 'EMPTY_CARRIER.json'), sha(data)")],
      ['test_flags2_empty_carriers_distinct_per_reader'], 'score_check writes one empty carrier per case'),
    M('G12', FOLD, [("        if e['release_sha256'] != state['release_sha256'] or e['kit_sha256'] != state['kit_sha256']:\n"
                     "            raise ChainInvalid('RELEASE_NOT_ACCEPTED')",
                     "        if False:\n            raise ChainInvalid('RELEASE_NOT_ACCEPTED')")],
      ['test_fold_foreign_release_sha_chain_invalid', 'test_audit_planted_foreign_release_entry'],
      'S5 release check removed'),
    M('G13', 'cpsvm2/core/names.py', [("re.fullmatch(pattern, value, re.ASCII) is not None",
                                       "re.match(pattern, value, re.ASCII) is not None")],
      ['test_safe05_trailing_newline_and_bad_id_refused'], 're.match instead of re.fullmatch in names'),
    M('G14', FOLD, [("    if st['reason'] == 'STAGE' and _t30(s, R, e, st):", "    if _t30(s, R, e, st):")],
      ['test_tst01_second_start_same_attempt_chain_invalid'], 'T32 accepts any START reason', ['M27']),
    M('G15', CLI, [("    if loop_block(env, env.pending, 'SAVE'):", "    if loop_block(env, env.pending, 'WORK'):")],
      ['t_cli_inputs_commit_found_and_next_stage', 'test_op01_start_on_drive_before_first_open'],
      'a commit block is not in state SAVE (the header reveals that work goes on)'),
    M('G16', SP, [("marks=dict((cache or {}).get('marks') or {}), written_utc=env.now())",
                   "marks={}, written_utc=env.now())")],
      ['test_marks_survive_every_commit'], 'marks cleared at every commit (r1 behaviour)'),
    M('G17', WRK, [("            tsha = place.tree_sha(rows)\n", "            tsha = ro['archives'][-1]['tree_sha256']\n")],
      ['test_int07_output_changed_after_archive_halts_before_consumer'],
      'the worker copies the archive tree sha into consumed instead of measuring', ['M12', 'M16']),
    M('G18', SESS, [("        return 'C6', {'run': op[0][0], 'role': op[0][1]}\n",
                     "        return 'C6', {'run': op[0][0], 'role': op[0][1]}\n"
                     "    if R is not None and R['status'] == 'ACTIVE':\n        return 'C8', {'run': cur}\n")],
      ['test_classify_c7_before_c8_and_c8b'], 'C8 (unbound re-run) evaluated before C7 (delivery question)'),
    M('G19', FOLD, [("    if R['replacements'] == 0 and (q or exported):", "    if R['replacements'] == 0:")],
      ['test_int02_v_not_available_everyday_freezes_visual'], 'T45 without the transcript guard'),
    M('G20', SESS, [("            out[n] = 'present' if _status(f, n, True, w, t) == 'P' else 'missing'",
                     "            out[n] = 'present' if _status(f, n, False, w, t) == 'P' else 'missing'")],
      ['test_int05_single_part_absence_is_not_missing'], 'a single part absence accepted as missing'),
    M('G21', 'cpsvm2/maint/score_check.py', [("    if fd['missing']:\n        raise Refused('OWNER_CHECKS_INCOMPLETE'",
                                              "    if False:\n        raise Refused('OWNER_CHECKS_INCOMPLETE'")],
      ['test_int03_score_check_refuses_pending_owner_items'], 'score_check build ignores pending owner items'),
    M('G22', SESS, [("kc is None or kc['config_only'], g)", "True, g)")],
      ['test_g22_non_config_kit_does_not_clear_a_halt'],
      'a HALT is cleared by a kit that is not config-only (v2 never uses unpack_kit\'s return value)'),
    M('G23', SESS, [("        if any(v != 'missing' for v in at[1].values()):\n            return 'HEAD', "
                     "Stop('QUALIFICATION_SERIES_EXISTS', 'C')",
                     "        if False:\n            return 'HEAD', Stop('QUALIFICATION_SERIES_EXISTS', 'C')")],
      ['test_session_fresh_q_genesis_and_series_exists'], 'GENESIS without the other-Q-series check'),
    M('G24', CLI, [("        res = worker.dispatch(kind, info, env)",
                    "        __import__('subprocess').run(['true'], start_new_session=True)\n"
                    "        res = worker.dispatch(kind, info, env)")],
      ['t_l11_no_detached_process'], 'a stage starts a process in a new session (detached)'),
    M('G25', CLI, [("    except Halt:\n        return busy(lay)",
                    "    except Halt:\n        print(BARE_HDR + 'WORK\\nDO: WAIT seconds=30', flush=True)\n"
                    "        return 0")],
      ['test_helper_busy_second_command_refused'], 'HELPER_BUSY turned into a WAIT block'),
    M('G26', SP, [("'path': '%s/%s.%d' % (verify_dir, name, k)} for k, c in enumerate(cps, 1) if c[0] not in ids]",
                   "'path': '%s/%s.%d' % (verify_dir, name, k)} for k, c in enumerate(cps, 1) if False]"),
                  ("for c in cps if c[0] in ids] or None\n            t['need'] = 'verify' if unknown else 'done'",
                   "for c in cps] or None\n            t['need'] = 'done'")],
      ['t_commit_md5_hidden_download_back', 'test_tst04_md5_hidden_download_back_mismatch_is_fork'],
      'a copy with an unknown id is accepted without the download-back (rule V)', ['M22']),
    M('G27', SP, [("        elif name in refused:\n            t['need'], t['finds_since_upload'] = 'find', 0\n"
                   "            handback = handback or name",
                   "        elif name in refused:\n            t['need'] = 'upload'")],
      ['t_commit_refused_upload_find_before_reupload'], '--refused --none re-uploads at once'),
    M('G28', SP, [("            if os.lstat(f['path']).st_size > cap:", "            if False:")],
      ['t_commit_refused_upload_find_before_reupload'], 'the upload cap check before an UPLOAD line is removed'),
    M('G30', SESS, [("    after = utc_minus(lt['utc'], g.get('p3_clock_tolerance_seconds') or 0)",
                     "    after = lt['utc']")],
      ['D_ans_G0_no_conv_none'], 'after= without the clock tolerance'),
    M('G31', CLI, [("    try:\n        res = worker.dispatch(kind, info, env)\n    except Halt as h:",
                    "    try:\n        try:\n            res = worker.dispatch(kind, info, env)\n        finally:\n"
                    "            durable.remove(env.p.foreground)\n    except Halt as h:")],
      ['D_kill_finish_same_boot'], 'FOREGROUND.json removed in a finally'),
    M('G32', SP, [("    if any(shas[v['path']] != by[v['name']]['sha256'] for v in loop['verify']):\n        return 'stop', 'FORK', None",
                   "    if False:\n        return 'stop', 'FORK', None")],
      ['t_commit_md5_hidden_download_back', 'test_tst04_md5_hidden_download_back_mismatch_is_fork'],
      'the download-back compare is skipped', ['M14']),
    M('G33', SP, [("        elif name in refused:\n", "        elif False:\n")],
      ['t_commit_refused_upload_find_before_reupload'], 'a refused upload is treated as absent (no HANDBACK A)'),
    M('G34', CLI, [("    except Halt:\n        return busy(lay)",
                    "    except Halt:\n        lock = type('NoLock', (), {'release': lambda self: None})()")],
      ['test_helper_busy_second_command_refused'],
      'a second helper command runs while another holds the lock (a foreground stage)'),
    # ---- v2 mutants of v1 rules (M2-nn)
    M('M2-01', 'cpsvm2/vio/v1reuse.py', [("    if any(p in ('', '.', '..') for p in parts):",
                                          "    if any(p in ('', '.') for p in parts):")],
      ['test_archive_codes'], 'a .. member name is not unsafe (reused archive rules)', ['M01']),
    M('M2-02', 'cpsvm2/vio/v1reuse.py', [("if m.size != e[2] or sha_bytes(self.read(n)) != e[3]:",
                                          "if m.size != e[2]:")],
      ['test_archive_codes'], 'Archive.check skips the member sha256 (reused)', ['M02']),
    M('M2-03', SESS, [("    if op:\n        return 'C6', {'run': op[0][0], 'role': op[0][1]}",
                       "    if False:\n        return 'C6', {'run': op[0][0], 'role': op[0][1]}")],
      ['test_classify_rows'], 'an open role is not resolved before anything else (C6 removed)', ['M03']),
    M('M2-04', WRK, [("        if fp != self.env.cache['fingerprint_sha256']:\n            return {'status': 'fingerprint'",
                      "        if False:\n            return {'status': 'fingerprint'")],
      ['test_fingerprint_change_stops_the_chain'], 'the stage body does not re-check the fingerprint', ['M04']),
    M('M2-05', FOLD, [("    if act == 'FREEZE_VISUAL_FAILED':\n        out.add('VISUAL_QA_FAILED_BY_RESET')",
                       "    if act == 'FREEZE_VISUAL_FAILED':\n        pass")],
      ['test_f1_core_continued_v_is_t46', 'test_m21_frozen_without_required_flag_refused'],
      'the FROZEN after a T46/T47 V resolution needs no VISUAL_QA_FAILED_BY_RESET', ['M05']),
    M('M2-06', FOLD, [("('EVERYDAY_RETRY' if ro['attempt'] == 1 else 'FREEZE_EXHAUSTED')", "'EVERYDAY_RETRY'")],
      ['test_m06_everyday_retry_once'], 'an everyday S/G is retried more than once', ['M06']),
    M('M2-08', PLAN, [("                    if L['restart_of'] is None and L['frozen']['restart_eligible'] and "
                       "'RESET_DIVERGED' in L['flags']:", "                    if False:")],
      ['test_m08_diverged_restart_conflict_stops'], 'B starts while a diverged A is restart-eligible', ['M08']),
    M('M2-10', FOLD, [("    if nr['reader'] == 'B':\n        ac = chain(s, nr['case'], 'A')",
                       "    if False:\n        ac = chain(s, nr['case'], 'A')")],
      ['test_t10_reader_b_needs_a_frozen', 'test_tst07_b_before_a_frozen_chain_invalid_and_runner_refuses'],
      'reader B may start before A is frozen', ['M10']),
    M('M2-11', FOLD, [("and b['start_boot_id'] == lt['boot_id'] == e['boot_id']",
                       "and b['start_boot_id'] == lt['boot_id']")],
      ['test_m11_ai_entry_of_another_boot_refused'], 'an AI entry of another boot archives a lost output', ['M11']),
    M('M2-13', WRK, [("            if tsha != ro['archives'][-1]['tree_sha256']:\n                raise Halt('STOP', "
                      "'AI_OUTPUT_CHANGED'", "            if False:\n                raise Halt('STOP', "
                      "'AI_OUTPUT_CHANGED'")],
      ['test_int07_output_changed_after_archive_halts_before_consumer'],
      'the consumer does not compare the measured output with the archive', ['M13']),
    M('M2-15', 'cpsvm2/vio/place.py', [("    if sha_bytes(raw) != want_sha256:\n        stop('PLACE_SHA_MISMATCH'",
                                        "    if False:\n        stop('PLACE_SHA_MISMATCH'")],
      ['test_place_ledger_sha_checked'], 'the placed ledger is not checked against the state', ['M15']),
    M('M2-18', FOLD, [("ro['status'] != 'ARCHIVED' or ro['consumed'] or", "ro['status'] != 'ARCHIVED' or")],
      ['test_m18_role_consumed_once', 'test_d11_fold_guard_witnesses'], 'a consumed role may be consumed again', ['M18']),
    M('M2-19', 'cpsvm2/vio/v1reuse.py', [("    return parent == root or parent.startswith(root + os.sep)",
                                          "    return True")],
      ['test_tst08_under_stage_direct'], 'under_stage accepts any path (reused)', ['M19']),
    M('M2-20', CLI, [("        if got is None or N.sha(N.cjson(got)) != R['inputs']['sha256']:", "        if got is None:")],
      ['test_inputs_changed_refused'], 'changed everyday inputs are prepared', ['M20']),
    M('M2-21', FOLD, [("and len(set(fl)) == len(fl) and set(fl) == expected_frozen_flags(s, R, b) \\",
                       "and len(set(fl)) == len(fl) \\")],
      ['test_m21_frozen_without_required_flag_refused'], 'a FROZEN may add any flags', ['M21']),
    M('M2-23', FOLD, [("and not V['consumed'] and V['review_incomplete'] < 2", "and not V['consumed'] and "
                       "V['review_incomplete'] < 3")],
      ['test_t21_t22_review_incomplete_limit'], 'a third REVIEW_INCOMPLETE continuation', ['M23']),
    M('M2-24', OUT, [("    for f in ('AI_OUTPUT_LOST', 'RESET_DIVERGED', 'RESTART_EXHAUSTED_BY_RESET'):",
                      "    for f in ('AI_OUTPUT_LOST', 'RESTART_EXHAUSTED_BY_RESET'):")],
      ['test_f4_outcomes_total_over_frozen_shapes'], 'a diverged run is scored', ['M24']),
    M('M2-25', 'cpsvm2/vio/place.py', [("    if sha_bytes(b) != frozen_sha256:\n        raise Halt('STOP', 'EVICT_MISMATCH'",
                                        "    if False:\n        raise Halt('STOP', 'EVICT_MISMATCH'")],
      ['test_evict_frozen_sha_checked'], 'evict keeps a FROZEN.json that is not the frozen one', ['M25']),
    M('M2-26', FOLD, [("    if R['replacements'] == 0 and (q or exported):", "    if R['replacements'] <= 1 and (q or exported):")],
      ['test_m26_visual_reviewer_replaced_once'], 'the visual reviewer is replaced twice', ['M26']),
    M('M2-30', WRK, [("        if sha_file(lt['prompt']) != lt['prompt_sha256']:", "        if False:")],
      ['test_tst06_prompt_changed_halts'], 'a changed generator prompt is not detected', ['M30']),
    M('M2-31', FOLD, [("    if item['files_found']:\n        return 'FILES_FOUND'", "    if False:\n        return 'FILES_FOUND'")],
      ['test_tst02_nothing_written_with_file_found_is_written'], 'files found do not force WRITTEN', ['M31']),
    M('M2-34', FOLD, [("    if item['ended'] is False:\n        return 'NOT_ENDED'", "    if False:\n        return 'NOT_ENDED'")],
      ['test_tst03_not_ended_is_written'], 'a conversation not ended is not forced WRITTEN', ['M34']),
    M('M2-35', FOLD, [("    if ro is None or ro['status'] not in OPEN or item['start_no'] != latest(ro)['start_no'] \\",
                       "    if ro is None or item['start_no'] != latest(ro)['start_no'] \\")],
      ['test_m35_resolved_role_not_resolved_again'], 'a resolved role is resolved again', ['M35']),
    M('M2-36', FOLD, [("    return ro['status'] == 'STARTED' and ro['supersedes'] == 0",
                       "    return ro['status'] == 'STARTED'")],
      ['test_t43_supersede_once_then_written', 'test_f2_second_start_only_after_no_conversation'],
      'NO_CONVERSATION supersedes a START twice', ['M36']),
    M('M2-38', SESS, [("    if 'PASS' not in done:\n        return 'PASS', None\n    obs = None",
                       "    if False:\n        return 'PASS', None\n    obs = None")],
      ['test_selftest_failed_stops'], 'a fresh series starts without a PASS for this VM', ['M38']),
    M('M2-39', FOLD, [("        return 'T47', ('FREEZE_VISUAL_FAILED' if ro['role'] == 'V' else 'FREEZE_LOST'), False",
                       "        return 'T47', ('FREEZE_VISUAL_FAILED' if ro['role'] == 'V' else 'INTERRUPT'), False")],
      ['test_tst02_nothing_written_with_file_found_is_written', 'test_f7_core_transcript_member_required'],
      'a written-and-lost S/G output is interrupted (a new conversation)', ['M39']),
]

# ---------------------------------------------------------------- generated guard mutants (D11b, §2.15.2, SD-66)
CORE_TARGETS = {'cpsvm2/core/fold.py': None, 'cpsvm2/core/session.py': None}          # None: every function
GLUE_TARGETS = {'cpsvm2/vio/savepoint.py': ('block', 'on_found', 'on_verify', 'finish', 'slip'),
                'cpsvm2/cli.py': ('go_checks', 'do_found', 'do_answer', 'session_slip', 'clear_check', 'stop_block',
                                  'session_downloads'),
                'cpsvm2/vio/place.py': ('settle',), 'cpsvm2/vio/drive.py': ('parse_raw',)}
STAGE1 = ['test_core_table', 'test_core_more']
STAGE2 = ['test_core_props', 'test_codes', 'test_vio', 'test_maint', 'test_v1_regressions']
STAGE2_FAST = ['test_core_props', 'test_maint', 'test_v1_regressions']     # the core set's stage 2: no worlds (§5.2)


def ALL_GUARDS():
    return guard_mutants(dict(CORE_TARGETS, **GLUE_TARGETS))
PRED_CALLS = ('any', 'all', 'bool', 'isinstance')
# Survivors argued equivalent (TG-04): id -> the guaranteeing check (function and condition). Reviewed at G-1.
EQUIVALENT = {
    # fold.py: an earlier conjunct, the row dispatch, S1-S6, or an invariant that every fold effect keeps (the state a
    # guard reads is always a fold output: t01 or an effect after its guard held)
    'GM-fold-g12-1-r': "g12 `e['kind'] == 'FROZEN'`: the row dispatch calls T12's guard only for kinds {'FROZEN'}",
    'GM-fold-_new_run_progress-4-r': "`rid == 'T23' and e['kind'] == 'STAGE'`: _progress returns T23 only through the "
                                     "PROGRESS pair ('T23', 'STAGE', ...), i.e. only for a STAGE",
    'GM-fold-resolution_action-14-r': "`oc = q and forced is None and ...`: oc is returned only by T44/T45, reached only "
                                      "after `if forced is not None ...: return 'T47'`, so forced is None there",
    'GM-fold-resolution_action-16-r': "`oc = ... and item['outcome'] == 'NOTHING_WRITTEN'`: oc is returned only by "
                                      "T44/T45, reached only past `if item['outcome'] != 'NOTHING_WRITTEN' ...: T48`",
    'GM-fold-resolution_action-22-r': "`not item['ended']` in the T48 line: ended is a bool (checked first) and "
                                      "ended False makes forced_for return NOT_ENDED, which returned T47 above",
    'GM-fold-resolution_action-23-r': "`item['files_found']` in the T48 line: files_found True makes forced_for "
                                      "return FILES_FOUND, which returned T47 above",
    'GM-fold-forced_for-4-r': "`ro['status'] != 'CONTINUED'` for NO_CONVERSATION: for a CONTINUED role "
                              "resolution_action returns T48 for every outcome but CONTINUED, whatever forced is "
                              "(the forced compare and the CONTINUED branch both give T48)",
    'GM-fold-no_conversation_admissible-0-r': "`ro['status'] == 'STARTED'`: both callers pass an open role that is not "
                                              "CONTINUED (forced_for tests status != CONTINUED first and "
                                              "resolution_action requires an OPEN role; session.restore_keys returns "
                                              "for CONTINUED first), and OPEN is {STARTED, CONTINUED}",
    'GM-fold-g42-23-r': "`b['rebase'] is None` in the rerun clause: with a rebase, _restore_state is undo49, which sets "
                        "R['rebase_bind'], so the later conjunct `R['rebase_bind'] is None` of the same pure and is false",
    'GM-fold-g10-12-r': "`L['status'] != 'FROZEN'` for B's A chain: g10 requires s['current'] is None (an earlier "
                        "conjunct) and a Q run that is not FROZEN is the current run (ACTIVE from e_new until e24)",
    'GM-fold-g10-15-r': "`L['tag'] == 'A-restart1'`: A-restart1 is a restart run (g11 requires restart_of) and g24 "
                        "refuses restart_eligible true when restart_of is set, so the first operand `not "
                        "restart_eligible` already holds",
    'GM-fold-g24-2-r': "`s['mode'] == 'everyday'` in dl: R['delivery'] is set only by e55, whose g55 requires not "
                       "c['Q'], so a qualification run has no prepared_seq",
    'GM-fold-g42-9-r': "`not c['Q']` before the INPUTS test: status INPUTS is set only by e15, whose g15 requires not "
                       "c['Q'], so a qualification run is never INPUTS",
    'GM-fold-_items_check-5-r': "`len(need) > 1`: invariant: at most one role is open (a START opens a role only when "
                                "the run has none open: g20 requires not run_open(R), and only the current run has "
                                "roles), and the items must equal open(s2)",
    # session.py: the callers
    'GM-session-_facts-0-r': "`lk['name'] in names`: every caller reads the result only at names it passed "
                             "(head_search passes all looked-up names; absent_twice, session_next step 4, "
                             "_after_classify C5b and _commit index the names they passed)",
    'GM-session-classify-7-r': "`kind in ('STAGE', 'FROZEN')`: the head passed validate_entry in cli.verify_head; "
                               "entry.PART_KINDS_OF allows parts only on STAGE, FROZEN, DELIVERY and FINAL; a FINAL head "
                               "is phase FINAL (C3 returns first) and DELIVERY returns C4 first",
    'GM-session-_resolve-9-r': "`'list_shows_none' in keys`: restore_keys adds list_shows_none only for a STARTED role "
                               "without files found, and then always conversation too (conversation_known is true only "
                               "for a CONTINUED role, the archived conversation), so the other operand already holds",
    # glue
    'GM-savepoint-block-3-n': "loop['phase'] is an informational field of PENDING.json (spec §5.1 step 3) that no code "
                              "reads (savepoint, cli and maint never read it back)",
    'GM-savepoint-block-11-n': "ENTRY_TOO_LARGE vs PART_TOO_LARGE in block: write_commit refuses an entry or a part "
                               "over max_upload_bytes before PENDING.json exists, with the same cap (the kit config), so "
                               "a PENDING loop never reaches this test; a setup loop takes the UPLOAD_TOO_LARGE branch",
    'GM-savepoint-block-13-r': "`loop['entry']['copies'] is None` for the absent names: on_found empties "
                               "loop['absent'] in the first call of the loop (the entry is the first group, still "
                               "unconfirmed then; t_d11_on_found_handback_and_absent), and the entry is confirmed only "
                               "in that call or in on_verify after it, so a confirmed entry always has absent == []",
    'GM-savepoint-on_found-1-r': "the same test in on_found: once the entry is confirmed loop['absent'] is [] (see "
                                 "GM-savepoint-block-13-r), so set(loop['absent']) is the empty set either way",
    'GM-savepoint-on_found-4-n': "`unknown` decides only t['need'] ('verify' or 'done'): while loop['verify'] holds the "
                                 "name's downloads, block prints the DOWNLOAD block without reading need, and on_verify "
                                 "or slip then sets need; with only known ids f['copies'] is set and the name leaves "
                                 "the group, so need is never read",
    'GM-savepoint-on_found-8-n': "`'verify' if unknown else 'done'`: as GM-savepoint-on_found-4-n, need is not read "
                                 "before on_verify or slip overwrites it",
    'GM-drive-parse_raw-0-r': "`len(names) == 1`: for two or more names a dict doc is 'count' either way (els=doc is "
                              "not a list; els=[doc] has length 1)",
    'GM-drive-parse_raw-10-n': "len([k not in sc]) over the two keys is 2 - len([k in sc]); both differ from 1 "
                               "exactly when the count is not 1",
    'GM-cli-go_checks-3-r': "`ex.get('command') != 'go'`: a found/answer block whose basis is the current one was "
                            "reprinted by the line above (reprint raises Out), and one with another basis returns by "
                            "the second operand, so the first operand never decides",
    'GM-cli-go_checks-4-r': "`b.get('basis') != basis(env)` for a go block: a go block is stale only if a command died "
                            "after it saved a loop or RESTORE_WORK and before render wrote the next BLOCK.json. A stale "
                            "pending/setup block meets an empty verify (on_verify cleared it before the save; see -7-r); "
                            "a stale fetch block's files stay in inbox/kit and inbox/pass until invalidate, which also "
                            "moves BLOCK.json; a local block's inbox/journal files are dropped only by a later commit's "
                            "post actions, and that commit prints its SAVE blocks (a new BLOCK.json) first. So every "
                            "file a stale block names is present with its size and the mutant's check finds no code",
    'GM-cli-go_checks-5-r': "`ex.get('kind') == 'pending'`: while PENDING.json exists advance runs pending_step first, "
                            "so every go block of another kind was printed with env.pending None; basis covers "
                            "PENDING's self_sha256, so with the current basis env.pending is still None and the "
                            "remaining conjunct is false",
    'GM-cli-go_checks-6-r': "`env.pending`: a pending block is printed only while PENDING.json exists and its basis "
                            "holds PENDING's self_sha256; with PENDING gone the basis differs and go_checks returned "
                            "above",
    'GM-cli-go_checks-7-r': "`env.pending['verify']`: with verify empty, on_verify returns ('ok', None) and changes "
                            "nothing, and persist rewrites the same document (write_doc's self_sha256 is a function of "
                            "the content), so the next block is the same",
    'GM-cli-go_checks-9-r': "`(env.work or {}).get(ex['loop'])`: a setup block is printed only while RESTORE_WORK holds "
                            "that loop, and basis covers RESTORE_WORK's self_sha256; with the loop gone the basis "
                            "differs and go_checks returned above",
    'GM-cli-go_checks-10-r': "`env.work[ex['loop']]['verify']`: as GM-cli-go_checks-7-r for a setup loop (save_work "
                             "rewrites the same RESTORE_WORK)",
    'GM-cli-session_downloads-3-r': "`phase == 'HEAD'`: the only other session download block is RECHECK's, reached "
                                    "through _commit, which session_next calls only past `if not w.get('head')` (the "
                                    "HEAD download of N), so w['head'] is set and the second conjunct is false there",
    'GM-place-settle-1-r': "`os.path.isdir(target)` in `same`: walk (v1mod.tree_list) lstats the root and raises "
                           "WALK_UNSUPPORTED_ENTRY ('root') unless it is a directory, which settle catches as same=False",
    'GM-place-settle-2-r': "`not os.path.islink(target)` in `same`: tree_list's lstat of a symlink root is not "
                           "S_ISDIR, so walk raises and settle catches it as same=False",
}


def _children(node):
    for f, v in ast.iter_fields(node):
        if isinstance(v, list):
            for i, x in enumerate(v):
                if isinstance(x, ast.AST):
                    yield f, i, x
        elif isinstance(v, ast.AST):
            yield f, None, v


def _is_default(b):
    last = b.values[-1]
    return isinstance(last, ast.Constant) or (isinstance(last, (ast.List, ast.Dict, ast.Tuple, ast.Set)) and not (
        getattr(last, 'elts', None) or getattr(last, 'keys', None)))


def _pred(v):
    return isinstance(v, (ast.Compare, ast.Name)) or (isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and
                                                       v.func.id in PRED_CALLS)


def sites(fn):
    """[(kind, parent, field, index)] of one function in a fixed walk: r (an and/or operand), n (a whole predicate)
    and l (one link of a chained comparison)."""
    read = set()
    for n in ast.walk(fn):
        if isinstance(n, (ast.If, ast.While, ast.Assert, ast.Return)):
            for x in ast.walk(n.test if not isinstance(n, ast.Return) else (n.value or ast.Constant(None))):
                if isinstance(x, ast.Name):
                    read.add(x.id)
    out = []

    def visit(node):
        if isinstance(node, ast.BoolOp) and not _is_default(node):
            out.extend(('r', node, 'values', i) for i in range(len(node.values)))
        if isinstance(node, (ast.If, ast.While, ast.Assert, ast.IfExp)) and not isinstance(node.test, ast.BoolOp):
            out.append(('n', node, 'test', None))
        if isinstance(node, ast.comprehension):
            out.extend(('n', node, 'ifs', i) for i, x in enumerate(node.ifs) if not isinstance(x, ast.BoolOp))
        if isinstance(node, ast.Return) and node.value is not None and _pred(node.value):
            out.append(('n', node, 'value', None))
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in read and _pred(node.value):
            out.append(('n', node, 'value', None))
        if isinstance(node, ast.Compare) and len(node.ops) > 1:
            out.extend(('l', node, None, j) for j in range(len(node.ops)))
        for f, i, ch in _children(node):
            visit(ch)
    for stmt in fn.body:
        visit(stmt)
    return out


def _functions(tree, names):
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and (names is None or n.name in names)]


def _replace(parent, field, index, new):
    if index is None:
        setattr(parent, field, new)
    else:
        getattr(parent, field)[index] = new


def guard_mutants(targets):
    out = []
    for path, names in targets.items():
        with open(os.path.join(VM2, path), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        mod = os.path.splitext(os.path.basename(path))[0]
        for fn in _functions(tree, names):
            for k, (kind, parent, field, idx) in enumerate(sites(fn)):
                out.append({'id': 'GM-%s-%s-%d-%s' % (mod, fn.name, k, kind), 'path': path, 'fn': fn.name, 'k': k,
                            'kind': kind, 'guard': True, 'nonroot': False, 'what': ast.unparse(
                                getattr(parent, field)[idx] if kind == 'r' or (kind == 'n' and idx is not None)
                                else parent if kind == 'l' else getattr(parent, field))[:160]})
    return out


def mutate_source(path, fn_name, k, unparse_only=False):
    """The module text with site k of fn_name mutated (or the unmutated ast.unparse form)."""
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    if unparse_only:
        return ast.unparse(tree) + '\n'
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn_name][0]
    kind, parent, field, idx = sites(fn)[k]
    if kind == 'r':
        neutral = isinstance(parent.op, ast.And)
        _replace(parent, field, idx, ast.Constant(neutral))
    elif kind == 'n':
        node = getattr(parent, field)[idx] if idx is not None else getattr(parent, field)
        _replace(parent, field, idx, ast.UnaryOp(ast.Not(), node))
    else:
        links = [ast.Compare(left=(parent.left if j == 0 else parent.comparators[j - 1]), ops=[op],
                             comparators=[parent.comparators[j]]) for j, op in enumerate(parent.ops)]
        links[idx] = ast.Constant(True)
        new = ast.BoolOp(ast.And(), links)
        for gp in ast.walk(fn):
            for f, i, ch in _children(gp):
                if ch is parent:
                    _replace(gp, f, i, new)
    return ast.unparse(ast.fix_missing_locations(tree)) + '\n'


# ---------------------------------------------------------------- the harness (D11d, §2.15.4)
def git(repo, *a):
    return subprocess.run(['git', '-C', repo] + IDENT + list(a), capture_output=True, text=True)


def clean(repo):
    return not git(repo, 'status', '--porcelain', '--untracked-files=no').stdout.strip()


def check_subs(src_vm2, m):
    p = os.path.join(src_vm2, m['path'])
    with open(p, encoding='utf-8') as f:
        s = f.read()
    for old, new in m['subs']:
        n = s.count(old)
        if n != 1:
            return 'old text occurs %d times: %r' % (n, old[:80])
        s = s.replace(old, new)
    return s


def prepare(m, d, commit=True, check=True, unparse_base=None):
    """Steps 1-5: clone, mutate, compile, commit, clean-HEAD check. Returns (repo, None) or (None, why)."""
    repo = os.path.join(d, 'repo')
    p = subprocess.run(['git', 'clone', '-q', '--local', REPO, repo], capture_output=True, text=True)
    if p.returncode:
        return None, 'clone: ' + p.stderr[-200:]
    vm2 = os.path.join(repo, 'deploy/vm2')
    if m is None:                                               # a baseline: optionally the unparse form of modules
        for path in unparse_base or ():
            t = mutate_source(os.path.join(vm2, path), None, None, unparse_only=True)
            with open(os.path.join(vm2, path), 'w', encoding='utf-8') as f:
                f.write(t)
        target = None
    elif m.get('guard'):
        target = os.path.join(vm2, m['path'])
        t = mutate_source(target, m['fn'], m['k'])
        with open(target, 'w', encoding='utf-8') as f:
            f.write(t)
    else:
        t = check_subs(vm2, m)
        if t.startswith('old text occurs'):
            return None, t
        target = os.path.join(vm2, m['path'])
        with open(target, 'w', encoding='utf-8') as f:
            f.write(t)
    if target and target.endswith('.py'):             # README.md and session_start.sh are not compiled
        try:
            py_compile.compile(target, cfile=os.path.join(d, 'c.pyc'), doraise=True)
        except py_compile.PyCompileError as e:
            return None, 'compile: ' + str(e)[:200]
    if commit and not clean(repo):
        git(repo, 'commit', '-qam', (m or {}).get('id', 'baseline'))
    head = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    if check and (not clean(repo) or (m is not None and head == git(REPO, 'rev-parse', 'HEAD').stdout.strip())):
        return None, 'clean-HEAD check failed (dirty: %s)' % (not clean(repo))
    return repo, None


def run_kill(repo, work, names, jobs, timeout, nonroot=False, failfast=True):
    t0 = time.time()
    cmd = [sys.executable, '-I', '-B', os.path.join(repo, 'deploy/vm2/tests/run_tests.py'), '--work', work, '--jobs',
           str(jobs)] + (['--failfast'] if failfast else []) + ['--only', ','.join(names)]
    if nonroot:
        subprocess.run(['chown', '-R', '%d:%d' % (NONROOT_UID, NONROOT_UID), os.path.dirname(repo)], check=False)
        cmd = ['setpriv', '--reuid=%d' % NONROOT_UID, '--regid=%d' % NONROOT_UID, '--clear-groups',
               '--inh-caps=-all', '--bounding-set=-all'] + cmd + ['--require-nonroot']
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        code, tail = p.returncode, (p.stdout + p.stderr)[-600:]
    except subprocess.TimeoutExpired:
        code, tail = 'TIMEOUT', ''
    res = {}
    rp = os.path.join(work, 'TEST_RESULTS.json')
    if os.path.isfile(rp):
        with open(rp) as f:
            res = json.load(f)
    failed, boot = [], []
    for x in res.get('failed', []):
        for t in x['tests']:
            det = [d for d in (x.get('detail') or []) if isinstance(d, dict) and d.get('name', d.get('test')) == t]
            (boot if det and all(d.get('bootstrap_stop') for d in det) else failed).append(t)
    return {'exit': code, 'tests': res.get('tests'), 'failed': failed, 'bootstrap_failed': boot,
            'seconds': round(time.time() - t0, 1), 'tail': tail, 'uid': res.get('uid'), 'cap_eff': res.get('cap_eff')}


def verdict(r):
    if r['exit'] == 'TIMEOUT':
        return 'TIMEOUT'
    if r['exit'] == 1 and r['failed']:
        return 'KILLED'
    return 'SURVIVED' if r['exit'] in (0, 1) else 'ERROR'


def nonroot_root():
    """§2.16.4: the folder a nonroot mutant's clone lives in, CPSVM2_NONROOT_DIR, whose parents uid 1000 can traverse
    (the harness's own work folder usually sits under a root-only parent). None when it is not set or not reachable."""
    d = os.environ.get('CPSVM2_NONROOT_DIR', '')
    if not os.path.isabs(d) or not os.path.isdir(d):
        return None
    p = os.path.dirname(os.path.realpath(d))
    while p != '/':
        if not os.stat(p).st_mode & 0o001:
            return None
        p = os.path.dirname(p)
    return d


def one(m, root, names, timeout, jobs=1, failfast=True):
    if m.get('nonroot'):
        root = nonroot_root()
        if root is None:
            return dict(id=m['id'], result='HARNESS_ERROR', detail='CPSVM2_NONROOT_DIR unset or not reachable by uid %d'
                        % NONROOT_UID)
    d = os.path.join(root, m['id'])
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    try:
        repo, why = prepare(m, d, commit=not m.get('no_commit'), check=not m.get('no_check'))
        if repo is None:
            return dict(id=m['id'], result='HARNESS_ERROR', detail=why)
        r = run_kill(repo, os.path.join(d, 'work'), names, jobs, timeout, m.get('nonroot'), failfast)
        out = dict(id=m['id'], result=verdict(r), killed_by=r['failed'], run=r)
        if not failfast:                    # GAP-5: every named killer ran; one that did not fail is a weak oracle
            out['listed_not_failing'] = sorted(set(names) - set(r['failed']))
        with open(os.path.join(root, 'PROGRESS.jsonl'), 'a') as f:          # one line per mutant, as it ends
            f.write(json.dumps({k: out.get(k) for k in ('id', 'result', 'killed_by', 'listed_not_failing')}) + '\n')
        return out
    finally:
        subprocess.run(['chmod', '-R', 'u+w', d], capture_output=True)
        shutil.rmtree(d, ignore_errors=True)


def baseline(root, names, jobs, unparse=None, nonroot=False):
    root = nonroot_root() if nonroot else root
    if root is None:
        return {'exit': 'HARNESS_ERROR', 'failed': [], 'seconds': 0, 'tail': 'CPSVM2_NONROOT_DIR'}
    d = os.path.join(root, 'BASELINE_%d' % len(os.listdir(root)))
    os.makedirs(d)
    try:
        repo, why = prepare(None, d, unparse_base=unparse)
        if repo is None:
            return {'exit': 'HARNESS_ERROR', 'failed': [], 'seconds': 0, 'tail': why}
        return run_kill(repo, os.path.join(d, 'work'), names, jobs, 7200, nonroot)
    finally:
        subprocess.run(['chmod', '-R', 'u+w', d], capture_output=True)
        shutil.rmtree(d, ignore_errors=True)


def run_set(sel, root, jobs):
    """Hand, reviewer and legacy mutants: one baseline per killing set, then each mutant (3 x baseline timeout)."""
    results, bases = [], {}
    for nr in (False, True):
        group = [m for m in sel if bool(m.get('nonroot')) == nr]
        names = sorted({n for m in group for n in m['kill']})
        if not names:
            continue
        if nr and nonroot_root() is None:               # §2.16.4: the integrator's non-root pass runs these
            results += [dict(id=m['id'], result='NOT_RUN', detail='nonroot: CPSVM2_NONROOT_DIR unset') for m in group]
            continue
        b = baseline(root, names, jobs, nonroot=nr)
        bases['nonroot' if nr else 'root'] = b
        if b['exit'] != 0:
            results += [dict(id=m['id'], result='BASELINE_FAILED') for m in group]
            continue
        to = max(300, 3 * b['seconds'])
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            results += list(ex.map(lambda m: one(m, root, m['kill'], to, failfast=False), group))
    return results, bases


def direct_tests(m):
    """The GUARD_TESTS of a glue mutant's function (test_core_table, D11a): its killing set."""
    import test_core_table as TC
    return TC.GUARD_TESTS[m['fn']]


def run_guards(gms, root, jobs, stages, unparse):
    """Guard mutants in stages: stage k's survivors run stage k+1 (§2.15.2). A stage is a list of names, or
    direct_tests (each mutant runs its function's GUARD_TESTS). One baseline per stage, on the ast.unparse form."""
    results, alive, bases = {}, list(gms), {}
    for k, stage in enumerate(stages, 1):
        if not alive:
            break
        names_of = stage if callable(stage) else (lambda m, st=stage: st)
        union = sorted({n for m in alive for n in names_of(m)})
        b = baseline(root, union, jobs, unparse=unparse)
        bases['stage%d' % k] = dict(b, names=union)
        if b['exit'] != 0:
            for m in alive:
                results[m['id']] = dict(id=m['id'], result='BASELINE_FAILED', stage=k)
            break
        per = b['seconds'] / max(1, len(union))
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            rs = list(ex.map(lambda m: one(m, root, names_of(m), max(300, 3 * (b['seconds'] if not callable(stage)
                                                                                 else per * len(names_of(m)) + 30))),
                             alive))
        for m, r in zip(alive, rs):
            results[m['id']] = dict(r, stage=k, what=m['what'])
        alive = [m for m, r in zip(alive, rs) if r['result'] != 'KILLED']
    return [results[m['id']] for m in gms if m['id'] in results], bases


def run_selftest(root):
    """§2.15.4: W45a (no commit: HARNESS_ERROR), W45b (neither commit nor check: a reset scenario's failures carry
    bootstrap_stop SESSION_REPO_DIRTY, not KILLED), W13 KILLED, and the generator holds the reviewer and v2.1 sites."""
    out = {}
    w45 = dict(REVIEWER[0], id='W45a', no_commit=True)
    out['W45a'] = one(w45, root, ['test_t4_ai_start_boot_must_be_the_start_boot_t39'], 600)['result']
    w45b = dict(REVIEWER[0], id='W45b', no_commit=True, no_check=True)
    r = one(w45b, root, ['D_baseline'], 3600)
    out['W45b'] = {'result': r['result'], 'bootstrap_failed': (r.get('run') or {}).get('bootstrap_failed')}
    out['W13'] = one(W13, root, W13['kill'], 900)['result']
    gm = {m['id'].rsplit('-', 2)[0] + ':' + m['what'] for m in guard_mutants(CORE_TARGETS)}
    want = {'g37': "b['start_boot_id'] == lt['boot_id']", 'g38': "e['boot_id'] == ro['continued_boot']",
            'g10': "L['frozen']['restart_eligible']", '_commit': "f[n]['present'] for n in names[1:]",
            '_s5': 'CHANGEABLE_KEYS', 'g11': "L['interrupts']", 'clear_ok': 'clear ==', 'clear_verdict': 'config_only_ok',
            'g59': "kc['from_kit_sha256'] != kc['to_kit_sha256']", '_virtual': 'job_dir_of',
            't01': 'layout_of(base)', 'resolution_action': "item['outcome'] == 'CONTINUED'"}
    out['generator'] = {fn: any(('-%s:' % fn) in g and frag in g for g in gm) for fn, frag in want.items()}
    ok = out['W45a'] == 'HARNESS_ERROR' and out['W45b']['result'] != 'KILLED' and out['W13'] == 'KILLED' and all(
        out['generator'].values())
    return ok, out


def main(work, jobs, only=(), selftest=False):
    if not clean(REPO):
        print('REFUSED HARNESS_CHECKOUT_DIRTY (run it in a bin/testclone.sh snapshot)')
        return 2
    root = os.path.join(work, 'mutants')
    os.makedirs(root, exist_ok=True)
    t0 = time.time()
    if selftest:
        ok, out = run_selftest(root)
        doc = {'schema': 'cps.vm2-mutants.v2', 'selftest': out, 'ok': ok, 'seconds': round(time.time() - t0, 1)}
        with open(os.path.join(work, 'MUTANTS_RESULTS.json'), 'w') as f:
            json.dump(doc, f, indent=1, sort_keys=True, default=str)
        print(json.dumps(doc, default=str))
        return 0 if ok else 1
    groups = {'hand': HAND, 'reviewer': REVIEWER, 'legacy': LEGACY,
              'nonroot': [m for m in HAND if m.get('nonroot')]}
    sel, guards, ids = [], [], []
    fast2 = 'stage2_fast' in only                       # by-id guard mutants: stage 2 only (default: both stages)
    for name in [x for x in only if x != 'stage2_fast'] or ('hand', 'reviewer', 'guard_core', 'guard_glue'):
        if name in groups:
            sel += groups[name]
        elif name == 'guard_core':
            guards.append(('core', guard_mutants(CORE_TARGETS), [STAGE1, STAGE2_FAST], list(CORE_TARGETS)))
        elif name.replace('_s1', '') in ('guard_fold', 'guard_session'):  # the core set by module; _s1: stage 1 only
            t = {k: v for k, v in CORE_TARGETS.items() if name.split('_')[1] in k}
            guards.append((name, guard_mutants(t), [STAGE1] if name.endswith('_s1') else [STAGE1, STAGE2_FAST], list(t)))
        elif name == 'guard_glue':
            guards.append(('glue', guard_mutants(GLUE_TARGETS), [direct_tests, STAGE2], list(GLUE_TARGETS)))
        else:
            sel += [m for m in HAND + REVIEWER + LEGACY if m['id'] == name]
            gm = [m for m in ALL_GUARDS() if m['id'] == name]
            if gm:
                ids.extend(gm)
    core_ids = [m for m in ids if m['path'] in CORE_TARGETS]
    if core_ids:
        guards.append(('by_id', core_ids, [STAGE2_FAST] if fast2 else [STAGE1, STAGE2_FAST], list(CORE_TARGETS)))
    if len(core_ids) < len(ids):
        guards.append(('by_id_glue', [m for m in ids if m not in core_ids], [direct_tests, STAGE2], list(GLUE_TARGETS)))
    applicable = [m for m in sel if not check_subs(VM2, m).startswith('old text occurs')]
    not_applicable = [{'id': m['id'], 'why': check_subs(VM2, m)[:120]} for m in sel if m not in applicable]
    results, bases = run_set(applicable, root, jobs)
    gres = {}
    for name, gms, stages, unparse in guards:
        rs, b = run_guards(gms, root, jobs, stages, unparse)
        gres[name] = {'sites': len(gms), 'killed': sum(r['result'] == 'KILLED' for r in rs), 'baselines': b,
                      'survivors': [dict(id=r['id'], result=r['result'], what=r.get('what'),
                                         equivalent=EQUIVALENT.get(r['id'])) for r in rs if r['result'] != 'KILLED'],
                      'killed_by': {r['id']: r.get('killed_by', [])[:3] for r in rs if r['result'] == 'KILLED'}}
    import run_tests                                    # GAP-6: the helper tree and commit the counts belong to
    doc = {'schema': 'cps.vm2-mutants.v2', 'mutants': len(applicable), 'helper_tree_sha256': run_tests.tree_sha(),
           'commit': git(REPO, 'rev-parse', 'HEAD').stdout.strip(), **run_tests.git_record(),
           'killed': sum(r['result'] == 'KILLED' for r in results), 'results': results, 'baselines': bases,
           'not_applicable': not_applicable, 'hand_open': HAND_OPEN, 'deleted': DELETED, 'guards': gres,
           'table': [{'id': m['id'], 'file': m['path'], 'what': m['what'], 'kill_tests': m['kill']}
                     for m in HAND + REVIEWER], 'seconds': round(time.time() - t0, 1)}
    with open(os.path.join(work, 'MUTANTS_RESULTS.json'), 'w') as f:
        json.dump(doc, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({'mutants': doc['mutants'], 'killed': doc['killed'], 'not_applicable': len(not_applicable),
                      'guards': {k: [v['sites'], v['killed'], len(v['survivors'])] for k, v in gres.items()},
                      'seconds': doc['seconds']}))
    for r in results:
        if r['result'] != 'KILLED':
            print(r['result'], r['id'], (r.get('detail') or (r.get('run') or {}).get('tail', ''))[-200:])
    bad = [r for r in results if r['result'] != 'KILLED'] + [s for v in gres.values() for s in v['survivors']
                                                            if not s['equivalent']]
    return 0 if not bad else 1
