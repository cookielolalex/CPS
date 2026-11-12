"""The ENTRY document (spec §3.4, §3.5): exact key sets, body validators, the state hash. Pure: no I/O.

validate_entry(doc, draft=False, cfg=None) -> [problem str]; empty means valid. With draft=True (the fold's S1 check,
§5.1 step 2) the keys `state` and `state_sha256` may be absent (when present they are still checked), and the runner pin and helper
version are left to the fold's S6 (HELPER_UNKNOWN). With cfg
({'series', 'accepted_helper_tree_sha256'}) the series and helper-tree acceptance of §3.4 are checked too."""
from .names import (BOOT_ID, CASE_ID, HELPER_VERSION, HEX64, PART_EXT, RUN_KEY, RUNNER_SHA256, SERIES, TAG, UTC_S,
                    cjson, entry_name, fm, parse_part, sha)

SCHEMA = 'cps.vm2-entry.v1'
KINDS = ('GENESIS', 'INPUTS', 'STAGE', 'FROZEN', 'AI', 'RESTORE', 'ACK', 'DELIVERY', 'HALT', 'CLEAR', 'FINAL')
ENTRY_KEYS = frozenset({'schema', 'series', 'seq', 'name', 'prev_sha256', 'kind', 'body', 'utc', 'boot_id', 'uid',
                        'home', 'fingerprint_sha256', 'helper', 'runner_sha256', 'kit_sha256', 'release_sha256',
                        'confirms', 'parts', 'payload', 'state', 'state_sha256', 'cleared_local'})
_STAGE = {'run': 'run', 'new_run': 'dict?', 'prepare_inputs_sha256': 'hex?', 'commands': 'list', 'next': 'str?',
          'next_args': 'dict?', 'codes': 'list', 'consumed': 'list', 'start': 'dict?', 'review_incomplete': 'bool',
          'continue_problems': 'int?', 'refused': 'str?', 'rerun': 'dict?', 'rebase': 'dict?', 'snapshot': 'dict',
          'png': 'dict?', 'saved_qa': 'dict?', 'carrier_sha256': 'hex?', 'generation_record_sha256': 'hex?',
          'fingerprint_checked': 'bool'}
BODY = {
    'INPUTS': {'tag': 'tag', 'case': 'case', 'inputs': 'dict', 'request_utc': 'utc'},
    'GENESIS': {'mode': 'str', 'operator': 'dict', 'jobs': 'list?', 'ledger': 'dict?', 'layout': 'dict',
                'gates': 'dict', 'pass': 'dict', 'other_series_absent': 'list?', 'approval': 'str'},
    'STAGE': _STAGE,
    'FROZEN': dict(_STAGE, frozen_sha256='hex', final_next='str', final_codes='list', restart_eligible='bool',
                   flags_added='list', notify='str?', delivery_sent='bool'),
    'AI': {'run': 'run', 'role': 'role', 'attempt': 'pos', 'revision': 'pos', 'start_no': 'pos',
           'start_boot_id': 'str', 'ended': 'bool', 'conversation': 'str', 'attested': 'dict', 'tree_sha256': 'hex',
           'files': 'list', 'transcript': 'dict?', 'final_message_sha256': 'hex'},
    'RESTORE': {'prev_boot_id': 'str?', 'operator': 'dict', 'fingerprint_sha256': 'hex', 'pass': 'dict',
                'head': 'dict', 'lookups': 'list', 'kit_sha256': 'hex', 'kit_change': 'dict?', 'resolutions': 'list',
                'start': 'dict?', 'rebase': 'dict?', 'rerun_expected': 'dict?', 'reprepare': 'dict?',
                'abandon': 'dict?', 'delivery_question': 'dict?', 'placed': 'list', 'approval': 'str'},
    'ACK': {'for_seq': 'pos', 'what': 'str', 'answer': 'dict'},
    'DELIVERY': {'run': 'run', 'standard_sha256': 'hex', 'copy': 'dict', 'log': 'dict', 'profile_folder': 'str'},
    'HALT': {'code': 'str', 'detail': 'dict', 'head_seq': 'int'},
    'CLEAR': {'halt_seq': 'pos', 'code': 'str', 'kit_sha256': 'hex', 'kit_change': 'dict'},
    'FINAL': {'all_frozen_sha256': 'hex', 'ledger_final_sha256': 'hex', 'runs': 'int', 'outcomes_sha256': 'hex'},
}
# Exact keys of nested records the fold reads (§3.5, §4.4, §8.2, §8.6).
START_KEYS = frozenset({'role', 'attempt', 'start_no', 'reason', 'prompt', 'prompt_sha256', 'folder', 'output', 'utc',
                        'boot_id'})
NEW_RUN_KEYS = frozenset({'tag', 'case', 'reader', 'job_dir', 'restart_of'})
COMMAND_KEYS = frozenset({'sub', 'exit', 'result', 'next', 'codes', 'record_sha256_after', 'ledger_sha256_after',
                          'stdout_sha256', 'started_utc', 'ended_utc'})
RESOLUTION_KEYS = frozenset({'run', 'role', 'attempt', 'start_no', 'ended', 'files_found', 'outcome', 'forced',
                             'transcript', 'list_shows_none', 'action', 'owner_check', 'conversation'})
PLACED_KEYS = frozenset({'what', 'path', 'tree_sha256', 'aside'})
KIT_CHANGE_KEYS = frozenset({'from_kit_sha256', 'to_kit_sha256', 'from_members', 'to_members', 'config_only',
                             'config_keys_changed', 'run_in_flight', 'to_accepts_release_sha256'})
REBASE_RESTORE_KEYS = frozenset({'head_seq', 'base_seq', 'missing_parts', 'absence', 'list_shows_none', 'bound'})
REBASE_STAGE_KEYS = frozenset({'head_seq', 'base_seq', 'bound', 'diverged'})
PART_KINDS_OF = {'STAGE': {'PNG'}, 'FROZEN': {'PNG'}, 'DELIVERY': {'DELIV', 'DLOG'}, 'FINAL': {'LEDGER', 'ALLFZ'}}
MEMBER_ROOTS = ('job', 'ledger', 'ai', 'transcript', 'attest', 'delivery', 'final')


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _ok(t, v):
    if t.endswith('?'):
        if v is None:
            return True
        t = t[:-1]
    return {'str': lambda: isinstance(v, str), 'int': lambda: _is_int(v), 'pos': lambda: _is_int(v) and v >= 1,
            'bool': lambda: isinstance(v, bool), 'dict': lambda: isinstance(v, dict),
            'list': lambda: isinstance(v, list), 'hex': lambda: fm(HEX64, v), 'utc': lambda: fm(UTC_S, v),
            'run': lambda: fm(RUN_KEY, v), 'tag': lambda: fm(TAG, v), 'case': lambda: fm(CASE_ID, v),
            'role': lambda: v in ('S', 'G', 'V')}[t]()


def _keys(d, want, where, out):
    if not isinstance(d, dict) or set(d) != set(want):
        out.append('%s: keys' % where)
        return False
    return True


def state_sha256(state):
    """sha(cjson(state)) (§3.4)."""
    return sha(cjson(state))


def validate_body(kind, body):
    """Exact body keys and types per kind (§3.5), plus the nested records the fold reads. Returns [problem]."""
    out = []
    spec = BODY.get(kind)
    if spec is None or not _keys(body, spec, 'body', out):
        return out or ['kind']
    for k, t in spec.items():
        if not _ok(t, body[k]):
            out.append('body.%s' % k)
    if out:
        return out
    if kind in ('GENESIS', 'RESTORE') and body['approval'] != 'none':
        out.append('body.approval')
    if kind == 'AI' and body['revision'] == 1:
        tp = body['attested'].get('tools_present')
        if not (isinstance(tp, dict) and set(tp) == {'source', 'sha256'} and tp['source'] in ('inventory', 'file')
                and fm(HEX64, tp['sha256'])):
            out.append('attested.tools_present')
    if kind in ('STAGE', 'FROZEN'):
        if body['new_run'] is not None:
            _keys(body['new_run'], NEW_RUN_KEYS, 'new_run', out)
        if body['start'] is not None:
            _start(body['start'], out)
        for c in body['commands']:
            if _keys(c, COMMAND_KEYS, 'command', out) and (
                    not isinstance(c['sub'], str) or c['result'] not in ('NEXT', 'REFUSED')
                    or not isinstance(c['next'], str) or not isinstance(c['codes'], list)):
                out.append('command: values')
        if not body['commands']:
            out.append('commands: empty')
        for c in body['consumed']:
            if _keys(c, {'role', 'attempt', 'revision', 'tree_sha256'}, 'consumed', out) and not (
                    _ok('role', c['role']) and _ok('pos', c['attempt']) and _ok('pos', c['revision'])
                    and _ok('hex', c['tree_sha256'])):
                out.append('consumed: values')
        if body['rebase'] is not None:
            _keys(body['rebase'], REBASE_STAGE_KEYS, 'rebase', out)
        if body['rerun'] is not None:
            _keys(body['rerun'], {'after_seq', 'unbound'}, 'rerun', out)
        _keys(body['snapshot'], {'members', 'tree_sha256'}, 'snapshot', out)
        if body['png'] is not None:
            _keys(body['png'], {'files', 'whole_sha256', 'parts_seq'}, 'png', out)
    elif kind == 'RESTORE':
        if body['start'] is not None:
            _start(body['start'], out)
        for r in body['resolutions']:
            if _keys(r, RESOLUTION_KEYS, 'resolution', out) and not _ok('str?', r['conversation']):
                out.append('resolution: conversation')
        for p in body['placed']:
            if _keys(p, PLACED_KEYS, 'placed', out) and not _ok('str?', p['aside']):
                out.append('placed: aside')
        if body['kit_change'] is not None:
            _keys(body['kit_change'], KIT_CHANGE_KEYS, 'kit_change', out)
        if body['rebase'] is not None:
            _keys(body['rebase'], REBASE_RESTORE_KEYS, 'rebase', out)
    elif kind == 'CLEAR':
        _keys(body['kit_change'], KIT_CHANGE_KEYS, 'kit_change', out)
    return out


def _start(st, out):
    if _keys(st, START_KEYS, 'start', out) and not (
            _ok('role', st['role']) and _ok('pos', st['attempt']) and _ok('pos', st['start_no'])
            and st['reason'] in ('STAGE', 'REBASE', 'NO_CONVERSATION', 'REPLACEMENT', 'EVERYDAY_RETRY')
            and _ok('hex', st['prompt_sha256']) and _ok('utc', st['utc'])):
        out.append('start: values')


def validate_entry(doc, draft=False, cfg=None):
    """Every violation of §3.4/§3.5 in `doc` (a parsed ENTRY document). An entry with any problem is never written
    and is SCHEMA_INVALID when read."""
    if not isinstance(doc, dict):
        return ['not a dict']
    want = ENTRY_KEYS - ({'state', 'state_sha256'} - set(doc) if draft else set())
    if set(doc) != want:
        return ['keys: %s' % sorted(set(doc) ^ want)]
    out = []
    seq, kind = doc['seq'], doc['kind']
    if doc['schema'] != SCHEMA:
        out.append('schema')
    if not fm(SERIES, doc['series']) or (cfg and doc['series'] != cfg.get('series')):
        out.append('series')
    if not _is_int(seq) or not 1 <= seq <= 999999:
        return out + ['seq']
    if doc['name'] != entry_name(doc['series'], seq):
        out.append('name')
    if (seq == 1) != (doc['prev_sha256'] is None) or (seq > 1 and not fm(HEX64, doc['prev_sha256'])):
        out.append('prev_sha256')
    if kind not in KINDS:
        return out + ['kind']
    if not fm(UTC_S, doc['utc']):
        out.append('utc')
    if not (fm(BOOT_ID, doc['boot_id']) or (doc['boot_id'] == 'unknown-boot' and kind == 'HALT')):
        out.append('boot_id')
    if not _is_int(doc['uid']) or not isinstance(doc['home'], str):
        out.append('uid/home')
    for k in ('fingerprint_sha256', 'kit_sha256', 'release_sha256'):
        if not fm(HEX64, doc[k]):
            out.append(k)
    h = doc['helper']
    if not isinstance(h, dict) or set(h) != {'version', 'tree_sha256'} or not fm(HEX64, h.get('tree_sha256')):
        out.append('helper')
    elif cfg is not None and h['tree_sha256'] not in cfg.get('accepted_helper_tree_sha256', ()):
        out.append('helper.tree_sha256 not accepted')
    if not draft and (doc['runner_sha256'] != RUNNER_SHA256
                      or (isinstance(h, dict) and h.get('version') != HELPER_VERSION)):
        out.append('runner/helper version')
    out += _confirms(doc['confirms'], seq)
    out += _parts(doc, kind, seq)
    out += _payload(doc['payload'])
    cl = doc['cleared_local']
    if cl is not None and (not isinstance(cl, dict) or set(cl) != {'code', 'head_seq', 'kit_sha256'}
                           or kind not in ('RESTORE', 'GENESIS')):
        out.append('cleared_local')
    if 'state' in doc and (not isinstance(doc['state'], dict) or doc['state_sha256'] != state_sha256(doc['state'])):
        out.append('state_sha256')
    return out + validate_body(kind, doc['body'])


def _confirms(cf, seq):
    if not isinstance(cf, list) or (seq == 1 and cf):
        return ['confirms']
    for c in cf:
        if not isinstance(c, dict) or set(c) != {'name', 'copies'} or not isinstance(c['copies'], list):
            return ['confirms']
        for cp in c['copies']:
            if not isinstance(cp, dict) or set(cp) != {'id', 'md5', 'size'} or not isinstance(cp['id'], str) \
                    or not fm(r'[0-9a-f]{32}', cp['md5']) or not _is_int(cp['size']) or cp['size'] < 1:
                return ['confirms copy']
    return []


def _parts(doc, kind, seq):
    ps, out, ks = doc['parts'], [], {}
    if not isinstance(ps, list):
        return ['parts']
    for p in ps:
        if not isinstance(p, dict) or set(p) != {'name', 'kind', 'k', 'folder', 'sha256', 'md5', 'bytes'}:
            return ['parts keys']
        pp = parse_part(p['name'])
        if not pp or pp[0] != doc['series'] or pp[1] != seq or pp[2] != p['kind'] or pp[3] != p['k'] \
                or p['kind'] not in PART_KINDS_OF.get(kind, ()) or not fm(HEX64, p['sha256']) \
                or not fm(r'[0-9a-f]{32}', p['md5']) or not _is_int(p['bytes']) or p['bytes'] < 1 \
                or not isinstance(p['folder'], str) or p['kind'] not in PART_EXT:
            out.append('part %s' % p.get('name'))
            continue
        ks.setdefault(p['kind'], []).append(p['k'])
    for k, lst in ks.items():
        if lst != list(range(1, len(lst) + 1)) or len(lst) > 99:
            out.append('parts %s not contiguous' % k)
    return out


def _payload(pl):
    if not isinstance(pl, dict) or set(pl) != {'members', 'png'} or not isinstance(pl['members'], list):
        return ['payload']
    paths = []
    for m in pl['members']:
        if not (isinstance(m, list) and len(m) == 5 and isinstance(m[0], str) and m[1] in ('dir', 'file')
                and _is_int(m[2]) and m[0].split('/')[0] in MEMBER_ROOTS
                and ((m[1] == 'dir' and m[3] is None and m[4] is None)
                     or (m[1] == 'file' and _is_int(m[3]) and m[3] >= 0 and fm(HEX64, m[4])))):
            return ['payload member']
        paths.append(m[0])
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        return ['payload order']
    return []


def member(doc, path):
    """The payload.members row of `path`, or None."""
    for m in doc['payload']['members']:
        if m[0] == path:
            return m
    return None
