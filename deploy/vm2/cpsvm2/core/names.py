"""Names, value patterns and codes (spec §3.1, §3.2, §6.3, §13). Pure: no I/O. Every match is re.fullmatch with
re.ASCII on a str; nothing here ever uses re.match or re.search on an attested value."""
import calendar
import hashlib
import json
import re

RUNNER_SHA256 = '7505e98ac88bc09a5e0507124e4cb381a5491c1112f418bcf5ca6553ab14f431'
HELPER_VERSION = 'cps-vm-helper.v2'

FOLDERS = {'Q': 'CPS/qualification', 'E': 'Dots Folder/CPS_JOB_RECORDS', 'D': 'CPS/reports',
           'setup': 'CPS/setup', 'reports': 'CPS/reports', 'static': 'CPS'}
MODES = {'Q': 'qualification', 'E': 'everyday', 'D': 'drill'}

SERIES = r'Q[1-9]|E[1-9]|D[1-9][0-9]?'
SEQ6 = r'[0-9]{6}'
HEX64 = r'[0-9a-f]{64}'
HEX12 = r'[0-9a-f]{12}'
ENTRY = r'CPSJ_(' + SERIES + r')_(' + SEQ6 + r')\.tgz'
PART = r'CPSJ_(' + SERIES + r')_(' + SEQ6 + r')_(PNG|DELIV|DLOG|LEDGER|ALLFZ)([0-9]{2})\.(part|xlsx|json|jsonl)'
PART_EXT = {'PNG': 'part', 'DELIV': 'xlsx', 'DLOG': 'json', 'LEDGER': 'jsonl', 'ALLFZ': 'json'}
PASS = r'FINGERPRINT_PASS_([0-9a-f]{64})\.json'
SELFTEST = r'SELFTEST_([0-9a-f]{64})\.json'
KIT = r'SESSION_KIT_([0-9a-f]{12})\.zip'
TAG = r'A|B|A-restart1|B-restart1|NA-A|NA-B|E[0-9]{8}T[0-9]{6}Z'
CASE_ID = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}'
RUN_KEY = r'(' + TAG + r')/(' + CASE_ID + r')'
UTC_S = r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'
BOOT_ID = r'[0-9a-f-]{36}'

# §6.3 attested-value patterns; ID and CONV come from the kit config (drive_id_re, conversation_re).
PATTERNS = {
    'ID': None, 'CONV': None,
    'MD5': r'[0-9a-f]{32}', 'SIZE': r'[1-9][0-9]{0,11}', 'UTC': UTC_S,
    'MODEL': r'[A-Za-z0-9._:-]{2,64}', 'PLATFORM': r'[A-Za-z0-9._:-]{2,64}', 'EFFORT': r'[a-z0-9_-]{1,32}',
    'YES': r'yes', 'YESNO': r'yes|no', 'TOOLS': r'none|[a-z0-9_-]{1,32}(,[a-z0-9_-]{1,32}){0,31}',
    'OUTCOME': r'NOTHING_WRITTEN|WRITTEN|UNSURE|NO_CONVERSATION', 'TRANSCRIPT': r'exported|not_available',
    'CASE_ID': CASE_ID, 'COPYPATH': None,
}
FREE_TEXT = frozenset({'CONV', 'MODEL', 'PLATFORM', 'EFFORT', 'ID', 'CASE_ID', 'COPYPATH'})
DEFAULT_DRIVE_ID_RE = r'[A-Za-z0-9_-]{20,80}'
FORBIDDEN_CHARS = set('{}<>\'"`$\\')
# Every key the helper ever asks (§6.5); a free-text value equal to one of them is a placeholder (§6.3).
KEY_NAMES = frozenset({'operator_model', 'platform', 'ended', 'conversation', 'started_utc', 'ended_utc', 'model',
                       'effort', 'single_user_message', 'memory', 'custom_instructions', 'web', 'connectors',
                       'file_uploads', 'other_agents', 'tools', 'transcript', 'prompt_pasted', 'opened_utc', 'outcome',
                       'list_shows_none', 'notified', 'case', 'copy', 'log', 'sent', 'arrived', 'asked'})
FEATURES = ('memory', 'custom_instructions', 'web', 'connectors', 'file_uploads', 'other_agents')

# Delta (probe results): the platform's upload cap with a margin, the head-hint listing size, the JobLock retry
# bound inside a foreground stage, and the exact stage_max_seconds keys (§X.2, §X.3, §X.7.2, §X.8.4).
UPLOAD_CAP_BYTES = 94_371_840
LIST_NEWEST_K = 10
JOB_BUSY_TRIES, JOB_BUSY_GAP_SECONDS = 5, 30
STAGE_KEYS = ('selftest', 'place', 'prepare', 'nonattempt', 'scope-finish', 'finish', 'visual-record', 'interrupt',
              'freeze')

REVIEW_CONTINUABLE = frozenset({'REVIEW_INCOMPLETE', 'REVIEW_NOT_FRESH_CONTEXT', 'REVIEWER_CONVERSATION_ID_REQUIRED'})

# §13: every REFUSED, STOP and HALT code the helper may raise (lint L1). STOP HALTED_<code> is HALTED_ + a member.
CODES_REFUSED = frozenset('''COMMAND_NOT_EXPECTED STALE_AT ARG_MISSING_KEY ARG_EXTRA_KEY ARG_DUPLICATE_KEY VALUE_FORBIDDEN
VALUE_PLACEHOLDER VALUE_PATTERN UTC_OUT_OF_WINDOW FOUND_NAMES_INCOMPLETE FOUND_FILE_AND_NONE FOUND_SYNTAX DOWNLOAD_MISSING
FINAL_MESSAGE_INVALID TRANSCRIPT_FILE_MISSING TRANSCRIPT_TOO_LARGE INPUTS_INVALID INPUTS_CHANGED COPY_LOG_MISMATCH
COPY_INVALID HELPER_BUSY JOB_BUSY'''.split())
CODES_STOP = frozenset('''FORK UPLOAD_FAILED HINT_AHEAD HEAD_UNSTABLE HEAD_CORRUPT SCHEMA_INVALID STATE_SHA_MISMATCH
CHAIN_INVALID LINK_MISMATCH HELPER_UNKNOWN RELEASE_NOT_ACCEPTED DISK_FULL WRITE_FAILED WRITE_READBACK_MISMATCH
ENTRY_TOO_LARGE PART_TOO_LARGE INTERNAL_EMPTY_OUTPUT INTERNAL_PENDING_EXISTS INTERNAL_ILLEGAL_TRANSITION INTERNAL_PRINT
INTERNAL_CHAIN_TOO_LONG FOREGROUND_DIED SELFTEST_DIED PLACE_TARGET_NOT_EMPTY PLACE_SHA_MISMATCH KIT_NOT_VERIFIED
KIT_SUMS_MISMATCH KIT_NOT_IN_MANIFEST KIT_PARTS_NOT_IN_MANIFEST KIT_NOT_REBUILT ARCHIVE_UNSAFE_MEMBER ARCHIVE_UNREADABLE
ARCHIVE_MANIFEST_MISMATCH ARCHIVE_MEMBER_SHA_MISMATCH KIT_CHANGE_WITH_RUN_IN_FLIGHT CONFIG_INVALID RELEASE_GATE_OPEN
LAYOUT_HOME LAYOUT_BASE LAYOUT_HELPER_NOT_IN_BASE_REPO LAYOUT_PATH LAYOUT_RELEASE_MISMATCH LAYOUT_HELPER_NOT_PINNED
LAYOUT_RUNNER_NOT_PINNED LEDGER_MISSING LEDGER_NO_IDENTITY CLOCK_BEHIND HOME_CHANGED SELFTEST_FAILED SETUP_FAILED
SESSION_LAYOUT SESSION_GIT_ERROR SESSION_REPO_DIRTY JOB_BUSY_TOO_LONG QUALIFICATION_DIVERGED_RESTART_CONFLICT
REBASE_PART_APPEARED REBASE_LIMIT REBASE_CONFLICT CONFIG_CHANGE_NOT_ALLOWED GATES_CHANGED QUALIFICATION_SERIES_EXISTS
SESSION_COMMIT_MISMATCH SESSION_NO_COMMIT INTERNAL_STEP_OVERFLOW UPLOAD_REFUSED UPLOAD_TOO_LARGE FINAL
UNCLASSIFIED'''.split())
CODES_HALT = frozenset('''RUNNER_REFUSED RUNNER_OUTPUT_UNPARSEABLE UNCLASSIFIED AI_OUTPUT_CHANGED WALK_UNSUPPORTED_ENTRY
EVICT_MISMATCH EVICT_FAILED POST_ACTION_FAILED FROZEN_FOLDER_CHANGED FREEZE_INCOMPLETE PNG_MANIFEST_UNSAFE PROMPT_CHANGED
GENERATION_RECORD_EXISTS AI_OUTPUT_TOO_LARGE PLACED_FROZEN_CHANGED'''.split())
# Not in §13 (reported to the spec owner): §9.5 final_dispositions' refusal, and §10.3's.
CODES_EXTRA = frozenset({'OWNER_CHECKS_INVALID', 'OWNER_CHECKS_INCOMPLETE'})
CODES = CODES_REFUSED | CODES_STOP | CODES_HALT | CODES_EXTRA


def is_code(code):
    """True iff `code` is a registered §13 code, or HALTED_<registered code> (§7.1 row 3)."""
    return code in CODES or (code.startswith('HALTED_') and code[7:] in CODES)


def fm(pattern, value):
    """re.fullmatch(pattern, value, re.ASCII) on a str; anything that is not a str never matches."""
    return isinstance(value, str) and re.fullmatch(pattern, value, re.ASCII) is not None


def cjson(x):
    """Canonical JSON bytes (§0): every hash over a JSON value is sha(cjson(x))."""
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def run8(run_key):
    """§0: first 8 hex of sha256(run_key) — names a run's helper files without its case id."""
    return sha(run_key.encode('ascii'))[:8]


def utc_minus(s, seconds):
    """The UTC_S time `seconds` before UTC_S s (the fail-closed clock tolerance of §X.9: T = utc - tolerance)."""
    t = utc_epoch(s) - int(seconds or 0)
    y, rem = 1970, t
    while True:
        n = 366 * 86400 if calendar.isleap(y) else 365 * 86400
        if rem < n:
            break
        rem, y = rem - n, y + 1
    mo = 1
    while rem >= calendar.monthrange(y, mo)[1] * 86400:
        rem, mo = rem - calendar.monthrange(y, mo)[1] * 86400, mo + 1
    d, rem = divmod(rem, 86400)
    return '%04d-%02d-%02dT%02d:%02d:%02dZ' % (y, mo, d + 1, rem // 3600, rem % 3600 // 60, rem % 60)


def mode_of(series):
    """'qualification' | 'everyday' | 'drill' from the series letter."""
    return MODES[series[0]]


def series_folder(series):
    return FOLDERS[series[0]]


def entry_name(series, seq):
    return 'CPSJ_%s_%06d.tgz' % (series, seq)


def part_name(series, seq, kind, k):
    return 'CPSJ_%s_%06d_%s%02d.%s' % (series, seq, kind, k, PART_EXT[kind])


def parse_part(name):
    """(series, seq, kind, k) for a PART name with the kind/extension binding, else None."""
    m = re.fullmatch(PART, name, re.ASCII) if isinstance(name, str) else None
    if not m or PART_EXT[m.group(3)] != m.group(5) or int(m.group(4)) < 1:
        return None
    return m.group(1), int(m.group(2)), m.group(3), int(m.group(4))


def utc_epoch(s):
    """Seconds since the epoch for a UTC_S string; None when it is not a valid UTC_S time."""
    if not fm(UTC_S, s):
        return None
    try:
        return calendar.timegm((int(s[0:4]), int(s[5:7]), int(s[8:10]), int(s[11:13]), int(s[14:16]), int(s[17:19])))\
            if _valid_date(s) else None
    except (ValueError, OverflowError):
        return None


def _valid_date(s):
    y, mo, d, h, mi, se = int(s[0:4]), int(s[5:7]), int(s[8:10]), int(s[11:13]), int(s[14:16]), int(s[17:19])
    return 1 <= mo <= 12 and 1 <= d <= calendar.monthrange(y, mo)[1] and h < 24 and mi < 60 and se < 60


def check_config_patterns(conversation_re, doc_samples):
    """§2.2: the kit is CONFIG_INVALID if conversation_re matches a doc sample, a key name or a pattern name.
    Returns None or 'CONFIG_INVALID'."""
    for v in list(doc_samples) + sorted(KEY_NAMES) + sorted(PATTERNS):
        if fm(conversation_re, v):
            return 'CONFIG_INVALID'
    return None


def copypath(value, home, case):
    """§6.3 COPYPATH structure: (user, utc14, file) for $HOME/cps-deliveries/<case>/<user>/<utc14>/<file>, else None.
    The cross-checks (same user and utc14 in both answers, realpath, regular file, size) are the glue's."""
    pre = home.rstrip('/') + '/cps-deliveries/' + case + '/'
    if not isinstance(value, str) or not value.startswith(pre):
        return None
    m = re.fullmatch(r'([a-z0-9_-]{1,40})/([0-9]{8}T[0-9]{6}Z)/(PERSONAL_COPY\.xlsx|PERSONALIZATION_LOG\.json)',
                     value[len(pre):], re.ASCII)
    return (m.group(1), m.group(2), m.group(3)) if m else None


def forbidden(value):
    """§6.3 global refusal: not a str, empty, a forbidden character, any whitespace (a trailing newline included),
    a control or non-ASCII character."""
    return not isinstance(value, str) or value == '' or any(
        c in FORBIDDEN_CHARS or c.isspace() or not 32 <= ord(c) <= 126 for c in value)


def check_value(key, pattern, value, cfg, window=None):
    """One attested value (§6.3). Returns None or (code, key). Order: global refusals, placeholder (free-text patterns
    only), the pattern, the window. cfg: {'drive_id_re', 'conversation_re', 'doc_samples', 'home', 'case'}."""
    if forbidden(value):
        return ('VALUE_FORBIDDEN', key)
    samples = set(cfg.get('doc_samples') or ())
    if pattern in FREE_TEXT:
        low = value.lower()
        if low in {k.lower() for k in KEY_NAMES} or low in {p.lower() for p in PATTERNS} or low in {
                s.lower() for s in samples}:
            return ('VALUE_PLACEHOLDER', key)
    if pattern == 'TOOLS' and any(t in samples for t in value.split(',')):
        return ('VALUE_PLACEHOLDER', key)
    if pattern == 'ID':
        rx = cfg.get('drive_id_re') or DEFAULT_DRIVE_ID_RE
    elif pattern == 'CONV':
        rx = cfg.get('conversation_re')
    elif pattern == 'COPYPATH':
        return None if copypath(value, cfg.get('home', ''), cfg.get('case', '')) else ('VALUE_PATTERN', key)
    else:
        rx = PATTERNS.get(pattern)
    if rx is None or not fm(rx, value):
        return ('VALUE_PATTERN', key)
    if pattern == 'UTC':
        if utc_epoch(value) is None:
            return ('VALUE_PATTERN', key)
        if window is not None and not (window[0] <= value <= window[1]):
            return ('UTC_OUT_OF_WINDOW', key)
    return None


def check_answers(expect_keys, pairs, cfg, windows=None):
    """`answer` key=value pairs against BLOCK.expect.keys (§6.3). pairs: list of (key, value) in the order given.
    Returns (None, {key: value}) or ((code, detail), None). Order: global refusals on every value, then the key set,
    then each value's placeholder/pattern/window check in the expected order."""
    for k, v in pairs:
        if forbidden(v):
            return ('VALUE_FORBIDDEN', k), None
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        return ('ARG_DUPLICATE_KEY', sorted(k for k in set(keys) if keys.count(k) > 1)[0]), None
    missing, extra = [k for k in expect_keys if k not in keys], [k for k in keys if k not in expect_keys]
    if missing:
        return ('ARG_MISSING_KEY', missing[0]), None
    if extra:
        return ('ARG_EXTRA_KEY', extra[0]), None
    got = dict(pairs)
    for k, pat in expect_keys.items():
        r = check_value(k, pat, got[k], cfg, (windows or {}).get(k))
        if r:
            return r, None
    return None, got


def at_string(head_seq, step, state_sha256, pending_sha256, lines):
    """§6.3 `--at` = '%06d-%04d-%s' % (head_seq, step, hex6) over the block lines without the header."""
    lines_sha = sha('\n'.join(lines).encode('ascii'))
    hx = sha(cjson({'state_sha256': state_sha256, 'pending_sha256': pending_sha256, 'step': step,
                    'lines_sha256': lines_sha}))[:6]
    return '%06d-%04d-%s' % (head_seq, step, hx)
