"""Mutation set (spec §14.7 with the probe-results delta §X.14): run_tests.py --mutants [--only IDS] [--jobs N].

Each mutant is one or more exact (old, new) substitutions in one file of deploy/vm2/ (each old text must occur exactly
once). It is applied to a fresh copy (a local `git clone` of this checkout plus a copy of deploy/vm2/; the original is
never touched), compiled, and its killing tests run there with run_tests.py --only; the mutant is killed when those
tests fail (exit 1). A baseline run of the union of the killing tests on the unmutated copy must pass first. Every
mutant must be killed. V1 maps each of the 39 mutants of admission review 1 (deploy/vm/review1/MUTANTS_V1.py) to a v2
mutant of the same rule, or says why the v1 path has no v2 counterpart (it is then not run).
Writes <work>/MUTANTS_RESULTS.json (cps.vm2-mutants.v1)."""
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


def M(mid, path, subs, kill, what, v1=()):
    return {'id': mid, 'path': path, 'subs': subs, 'kill': kill, 'what': what, 'v1': list(v1)}


SP, CLI, FOLD, SESS, PLAN, OUT, WRK = ('cpsvm2/vio/savepoint.py', 'cpsvm2/cli.py', 'cpsvm2/core/fold.py',
                                       'cpsvm2/core/session.py', 'cpsvm2/core/plan.py', 'cpsvm2/core/outcome.py',
                                       'cpsvm2/worker.py')
MUTANTS = [
    M('G1', SP, [("    grp = _group(pend)\n    if not grp:\n        return None",
                  "    grp = _group(pend)\n    if not grp or pend['entry']['copies'] is not None:\n        return None"),
                 ("[{'id': c[0], 'md5': c[1], 'size': c[2]} for c in f['copies']]",
                  "[{'id': c[0], 'md5': c[1], 'size': c[2]} for c in f['copies'] or []]")],
      ['t_commit_entry_then_parts', 'test_op03_truncated_all_frozen_part_reuploaded_before_handback_b'],
      'savepoint finishes the commit (and prints the next block) once the entry is confirmed, parts unconfirmed',
      ['M28']),
    M('G2', SP, [("if any(int(c[-1]) != f['bytes'] or (not hidden and c[1] != f['md5']) for c in cps):",
                  "if any(int(c[-1]) != f['bytes'] for c in cps):")],
      ['t_commit_fork_foreign_md5', 'test_foreign_md5_same_size_is_fork'],
      'a copy with another md5 is accepted (md5 visible)'),
    M('G3', SESS, [("    if not twice or ab[-1] - ab[0] >= w:\n        return 'A'", "    if True:\n        return 'A'")],
      ['test_fork_at_restore_lagging_n_plus_1', 'test_head_search_wait_between_absences'],
      'the head search accepts a single absence of N+1'),
    M('G4', FOLD, [("        if not (no_conversation_admissible(state, ro) and item['list_shows_none'] is True):",
                    "        if ro['status'] != 'OPENED' and not (no_conversation_admissible(state, ro) and "
                    "item['list_shows_none'] is True):")],
      ['test_g4_no_conversation_from_opened_is_not_t43'], 'T43 accepts NO_CONVERSATION from OPENED'),
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
    M('G15', CLI, [("    emit(env, 'SAVE', PrintBlock('SAVE', uploads=ups,",
                    "    emit(env, 'WORK', PrintBlock('WORK', uploads=ups,")],
      ['t_cli_inputs_commit_found_and_next_stage', 'test_op01_start_on_drive_before_first_open'],
      'a commit block is not in state SAVE (the header reveals that work goes on)'),
    M('G16', SP, [("marks=dict((cache or {}).get('marks') or {}), written_utc=env.now())",
                   "marks={}, written_utc=env.now())")],
      ['test_marks_survive_every_commit', 'DL_OPENED1_e'], 'marks cleared at every commit (r1 behaviour)'),
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
    M('G26', SP, [("        if cps and hidden and unknown:", "        if False:")],
      ['t_commit_md5_hidden_download_back', 'test_tst04_md5_hidden_download_back_mismatch_is_fork'],
      'an md5-hidden copy accepted on size alone (no download-back)', ['M22']),
    M('G27', SP, [("        elif name in refused:\n            t['need'], t['finds_since_upload'] = 'find', 0\n"
                   "            handback = True",
                   "        elif name in refused:\n            t['need'] = 'upload'")],
      ['t_commit_refused_upload_find_before_reupload'], '--refused --none re-uploads at once'),
    M('G28', SP, [("            if os.lstat(f['path']).st_size > env.cfg['max_upload_bytes']:", "            if False:")],
      ['t_commit_refused_upload_find_before_reupload'], 'the upload cap check before an UPLOAD line is removed'),
    M('G29', SESS, [("            if seqs and st(max(seqs), True) == 'P':", "            if seqs:")],
      ['D_head_listing_ghost'], 'a listing row is taken as a present lookup'),
    M('G30', SESS, [("    after = utc_minus(lt['utc'], g.get('p3_clock_tolerance_seconds') or 0)",
                     "    after = lt['utc']")],
      ['D_ans_G0_no_conv_none'], 'after= without the clock tolerance'),
    M('G31', CLI, [("    try:\n        res = worker.dispatch(kind, info, env)\n    except Halt as h:",
                    "    try:\n        try:\n            res = worker.dispatch(kind, info, env)\n        finally:\n"
                    "            durable.remove(env.p.foreground)\n    except Halt as h:")],
      ['D_kill_finish_same_boot'], 'FOREGROUND.json removed in a finally'),
    M('G32', SP, [("        if os.lstat(v['path']).st_size != f['bytes'] or sha_file(v['path']) != f['sha256']:\n"
                   "            fork = True", "        if False:\n            fork = True")],
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
    M('M2-11', FOLD, [("        and b['start_boot_id'] == lt['boot_id'] == e['boot_id']",
                       "        and b['start_boot_id'] == lt['boot_id']")],
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
      ['test_m18_role_consumed_once'], 'a consumed role may be consumed again', ['M18']),
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
    M('M2-36', FOLD, [("    return ro['status'] == 'STARTED' and ro['opened'] is None and ro['supersedes'] == 0 \\",
                       "    return ro['status'] == 'STARTED' and ro['opened'] is None \\")],
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
# v1 id -> (status, v2 mutant or reason)
DELETED = {
    'M33': 'v1 classified an incident against an archive (AI_ARCHIVED); v2 has no incident notes and a RESTORE never '
           'archives: AI entries come only from the boot of their START (M2-11), and an open role is resolved once '
           '(M2-35).',
}


def v1_table():
    """Every v1 mutant id of deploy/vm/review1/MUTANTS_V1.py with its v2 status."""
    ns = {}
    with open(os.path.join(REPO, 'deploy/vm/review1/MUTANTS_V1.py'), encoding='utf-8') as f:
        exec(compile(f.read(), 'MUTANTS_V1.py', 'exec'), ns)
    out = {}
    for k in sorted(ns['M']):
        vid = k.split('_')[0]
        hit = [m['id'] for m in MUTANTS if vid in m['v1']]
        if hit:
            out[k] = {'status': 'mapped', 'v2': hit}
        elif vid in DELETED:
            out[k] = {'status': 'path deleted', 'reason': DELETED[vid]}
        else:
            out[k] = {'status': 'UNMAPPED'}
    return out


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


def copy_tree(dest):
    """A clean checkout of this commit (local clone) with this deploy/vm2/ copied in (no bytecode)."""
    subprocess.run(['git', 'clone', '-q', '--local', REPO, dest], check=True, capture_output=True)
    shutil.copytree(VM2, os.path.join(dest, 'deploy/vm2'), ignore=shutil.ignore_patterns('__pycache__'))


def run_kill(repo, work, names, jobs):
    t0 = time.time()
    p = subprocess.run([sys.executable, '-I', '-B', os.path.join(repo, 'deploy/vm2/tests/run_tests.py'), '--work',
                        work, '--jobs', str(jobs), '--only', ','.join(names)], capture_output=True, text=True,
                       timeout=5400)
    res = {}
    rp = os.path.join(work, 'TEST_RESULTS.json')
    if os.path.isfile(rp):
        with open(rp) as f:
            res = json.load(f)
    failed = [t for x in res.get('failed', []) for t in x['tests']]
    return {'exit': p.returncode, 'tests': res.get('tests'), 'failed': failed, 'seconds': round(time.time() - t0, 1),
            'tail': (p.stdout + p.stderr)[-600:]}


def one(m, root):
    d = os.path.join(root, m['id'])
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    try:
        repo = os.path.join(d, 'repo')
        copy_tree(repo)
        s = check_subs(os.path.join(repo, 'deploy/vm2'), m)
        if s.startswith('old text occurs'):
            return dict(id=m['id'], result='PATCH_FAILED', detail=s)
        p = os.path.join(repo, 'deploy/vm2', m['path'])
        with open(p, 'w', encoding='utf-8') as f:
            f.write(s)
        try:
            py_compile.compile(p, cfile=os.path.join(d, 'c.pyc'), doraise=True)
        except py_compile.PyCompileError as e:
            return dict(id=m['id'], result='DOES_NOT_COMPILE', detail=str(e)[:300])
        r = run_kill(repo, os.path.join(d, 'work'), m['kill'], 1)
        killed = r['exit'] == 1 and bool(r['failed'])
        return dict(id=m['id'], result='KILLED' if killed else 'SURVIVED' if r['exit'] == 0 else 'ERROR',
                    killed_by=r['failed'], run=r)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main(work, jobs, only=()):
    root = os.path.join(work, 'mutants')
    os.makedirs(root, exist_ok=True)
    sel = [m for m in MUTANTS if not only or m['id'] in only]
    t0 = time.time()
    bad = [(m['id'], check_subs(VM2, m)) for m in sel]
    bad = [(i, s) for i, s in bad if s.startswith('old text occurs')]
    names = sorted({n for m in sel for n in m['kill']})
    bd = os.path.join(root, 'BASELINE')
    shutil.rmtree(bd, ignore_errors=True)
    copy_tree(os.path.join(bd, 'repo'))
    base = run_kill(os.path.join(bd, 'repo'), os.path.join(bd, 'work'), names, jobs)
    shutil.rmtree(bd, ignore_errors=True)
    results = []
    if base['exit'] == 0 and not bad:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            results = list(ex.map(lambda m: one(m, root), sel))
    v1 = v1_table()
    doc = {'schema': 'cps.vm2-mutants.v1', 'mutants': len(sel), 'killed': sum(r['result'] == 'KILLED' for r in results),
           'baseline': base, 'patch_problems': bad, 'results': results, 'v1_table': v1,
           'v1_unmapped': sorted(k for k, v in v1.items() if v['status'] == 'UNMAPPED'),
           'table': [{'id': m['id'], 'file': m['path'], 'what': m['what'], 'kill_tests': m['kill'], 'v1': m['v1']}
                     for m in MUTANTS], 'seconds': round(time.time() - t0, 1)}
    with open(os.path.join(work, 'MUTANTS_RESULTS.json'), 'w') as f:
        json.dump(doc, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({k: doc[k] for k in ('mutants', 'killed', 'seconds', 'v1_unmapped')}))
    if base['exit'] != 0:
        print('BASELINE FAILED', base['failed'], base['tail'][-300:])
    for i, s in bad:
        print('PATCH', i, s)
    for r in results:
        if r['result'] != 'KILLED':
            print(r['result'], r['id'], r.get('detail') or r['run']['tail'][-300:])
    ok = base['exit'] == 0 and not bad and doc['killed'] == len(sel) and not doc['v1_unmapped']
    return 0 if ok else 1
