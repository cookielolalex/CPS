"""Block printing (spec §6.1, §6.4) and the parsing of `found` and `answer` arguments (§6.2, delta v2.1 §2.3). A block
is the header, UPLOAD, FIND and DOWNLOAD lines and exactly one `DO:` line. Every path and folder is printed
shlex-quoted and round-trips through shlex.split (else INTERNAL_PRINT); nothing printed is non-ASCII. The `--at` value
is computed by the glue over the lines rendered with the placeholder AT_MARK, then substituted."""
import re
import shlex

from .v1compat import Halt

AT_MARK = '@AT@'
SIZE = r'[1-9][0-9]{0,11}'
DRIVE_TIME = r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z'


def q(value):
    """shlex-quoted value; INTERNAL_PRINT when it would not round-trip or is not ASCII."""
    s = str(value)
    out = shlex.quote(s)
    if not s or not s.isascii() or '\n' in s or shlex.split(out) != [s]:
        raise Halt('STOP', 'INTERNAL_PRINT', 'a printed value does not round-trip')
    return out


def prints(value):
    """True when `value` can be printed in a block line (q round-trips and the grammar's character set holds)."""
    try:
        q(value)
    except Halt:
        return False
    return '{' not in value and '}' not in value


def word(value):
    """A key=value argument value: ASCII, no whitespace, no quote, printed bare."""
    s = str(value)
    if not s or not s.isascii() or any(c.isspace() or c in '\'"\\$`{}<>' for c in s) or shlex.split(s) != [s]:
        raise Halt('STOP', 'INTERNAL_PRINT', 'a printed argument is not a plain word')
    return s


def header(series, head_seq, kit_sha256, at, mode, state_code):
    return 'CPSV series=%s head=%06d kit=%s at=%s mode=%s state=%s' % (
        series, head_seq or 0, kit_sha256[:12] if kit_sha256 else 'none', at, mode, state_code)


def body_lines(block, vm):
    """The lines after the header for a PrintBlock-like object (uploads, finds, downloads, do)."""
    out = ['UPLOAD %s TO %s AS %s' % (q(p), q(f), word(n)) for p, f, n in block.uploads]
    out += ['FIND %s %s %s' % (q(f), how, word(v)) for f, how, v in block.finds]
    out += ['DOWNLOAD %s ID %s TO %s' % (q(f), word(did), q(p)) for f, did, p in block.downloads]
    return out + ['DO: ' + do_text(block.do, vm)]


def do_text(do, vm):
    act, args = do
    if act == 'RUN':
        return 'RUN bash %s go' % q(vm)
    if act == 'WAIT':
        return 'WAIT seconds=%d' % int(args['seconds'])
    if act == 'STOP':
        return 'STOP %s HANDBACK %s' % (word(args['code']), args['handback']) + (
            ' name=%s' % word(args['name']) if args.get('name') else '')
    if act == 'ATTEST_FOUND':
        return 'ATTEST bash %s found --at %s --raw FILE' % (q(vm), AT_MARK) + (
            ' [--refused NAME]' if args.get('uploaded') else '')
    if act == 'ATTEST_ANSWER':
        pre = ''
        if args.get('prefix'):
            pre = args['prefix'][0] + ''.join(' %s=%s' % (k, word(v)) for k, v in args['prefix'][1].items()) + ' '
        if args.get('after'):
            pre += 'ATTEST after=%s bash %s answer --at %s ' % (word(args['after']), q(vm), AT_MARK)
        else:
            pre += 'ATTEST bash %s answer --at %s ' % (q(vm), AT_MARK)
        return pre + ' '.join('%s=%s' % (k, p) for k, p in args['keys'].items())
    return act + ''.join(' %s=%s' % (k, word(v)) for k, v in args.items())


def check_grammar(lines):
    """§6.1 block grammar (lint L5): header, then UPLOAD*, FIND*, DOWNLOAD*, exactly one DO: line last; no THEN/OPTION,
    no {TOKEN}, ASCII only. Returns None or a reason."""
    if not lines or not re.fullmatch(r'CPSV series=\S+ head=[0-9]{6} kit=(none|[0-9a-f]{12}) at=\S+ mode='
                                     r'(qualification|everyday|drill|setup) state=[A-Z]+', lines[0]):
        return 'header'
    body = lines[1:]
    if body and body[0].startswith('REFUSED '):
        body = body[1:]
    order = {'UPLOAD': 0, 'FIND': 1, 'DOWNLOAD': 2, 'DO:': 3}
    last = -1
    for i, ln in enumerate(body):
        if not ln.isascii() or '{' in ln or '}' in ln or ln.startswith(('THEN', 'OPTION')):
            return 'token'
        k = order.get(ln.split(' ', 1)[0])
        if k is None or k < last or (k == 3) != (i == len(body) - 1):
            return 'order'
        if k < 3 and not _line_form(ln):
            return 'form'
        last = k
    return None if body and body[-1].startswith('DO: ') else 'do'


def _line_form(ln):
    """§6.1 line forms: UPLOAD <path> TO <folder> AS <name>, FIND <folder> NAME <name>, DOWNLOAD <folder> ID <id> TO
    <path>."""
    try:
        t = shlex.split(ln)
    except ValueError:
        return False
    want = {'UPLOAD': (6, {2: 'TO', 4: 'AS'}), 'FIND': (4, {2: 'NAME'}), 'DOWNLOAD': (6, {2: 'ID', 4: 'TO'})}[t[0]]
    return len(t) == want[0] and all(t[j] == v for j, v in want[1].items())


# ---------------------------------------------------------------- argument parsing (§6.2, §6.3)
class Usage(Exception):
    """Argument syntax: exit 2, the current block printed again."""


def parse_found(argv):
    """`found --at A --raw F [--refused N ...]` or `found --at A (--name N (--file ID:SIZE ... | --none))+
    [--refused N ...]`. Returns (at, raw path or None, [[name, [ID:SIZE strings], none]], [refused names])."""
    if len(argv) < 3 or argv[0] != '--at':
        raise Usage('found --at')
    at, rest, raw, items, refused, i = argv[1], argv[2:], None, [], [], 0
    while i < len(rest):
        a, v = rest[i], rest[i + 1] if i + 1 < len(rest) else None
        if a == '--refused' and v is not None:
            refused.append(v)
        elif a == '--raw' and v is not None and raw is None and not items:
            raw = v
        elif a == '--name' and v is not None and raw is None:
            items.append([v, [], False])
        elif a == '--file' and v is not None and items:
            items[-1][1].append(v)
        elif a == '--none' and items:
            items[-1][2] = True
            i += 1
            continue
        else:
            raise Usage(a)
        i += 2
    if raw is None and not items:
        raise Usage('found')
    return at, raw, items, refused


def manual_copies(items, names, id_ok):
    """The manual form's answer {name: [[id, size]]}, or the REFUSED code (FOUND_SYNTAX, FOUND_FILE_AND_NONE,
    FOUND_NAMES_INCOMPLETE, VALUE_PATTERN)."""
    got = {}
    for name, files, none in items:
        if name in got or (not files and not none):
            return 'FOUND_SYNTAX', None
        if files and none:
            return 'FOUND_FILE_AND_NONE', None
        cps = []
        for f in files:
            p = f.split(':')
            if len(p) != 2 or not id_ok(p[0]) or not re.fullmatch(SIZE, p[1], re.ASCII):
                return 'VALUE_PATTERN', None
            cps.append([p[0], int(p[1])])
        got[name] = cps
    if not set(names) <= set(got):
        return 'FOUND_NAMES_INCOMPLETE', None
    return None, got


def _token(o):
    return any(isinstance(k, str) and k.lower().endswith(('page_token', 'pagetoken')) and v not in (None, '')
               for k, v in o.items())


def parse_raw(doc, names, id_ok):
    """A saved tool result (delta v2.1 §2.3, D4): (detail, None) or (None, {name: [[id, size]]}). Pure. The copies of a
    name are the entries of any element whose title equals it exactly; a name is absent only when every element is an
    exact-name search (`results`)."""
    els = [doc] if len(names) == 1 and isinstance(doc, dict) else doc
    if not isinstance(els, list) or len(els) != len(names):
        return 'count', None
    cps, listing = {n: {} for n in names}, False
    for el in els:
        objs = el if isinstance(el, list) else [el]
        for i, o in enumerate(objs):
            if not isinstance(o, dict):
                return 'shape', None
            env, sc = o, o
            if 'content' in o:
                if o.get('isError') is True:
                    return 'error', None
                sc = o.get('structuredContent')
            if not isinstance(sc, dict) or len([k for k in ('results', 'files') if k in sc]) != 1:
                return 'shape', None
            key = 'results' if 'results' in sc else 'files'
            if not isinstance(sc[key], list):
                return 'shape', None
            if i == len(objs) - 1 and (_token(env) or _token(sc)):
                return 'pages', None
            listing = listing or key == 'files'
            for r in sc[key]:
                if not isinstance(r, dict) or r.get('title') not in cps or r.get('file_or_folder') == 'folder':
                    continue
                sz, ct = r.get('size'), r.get('created_at' if key == 'results' else 'created_time')
                if not (id_ok(r.get('id')) and ((type(sz) is int and sz >= 1) or (
                        isinstance(sz, str) and re.fullmatch(SIZE, sz, re.ASCII))) and isinstance(ct, str)
                        and re.fullmatch(DRIVE_TIME, ct, re.ASCII)):
                    return 'entry', None
                if cps[r['title']].setdefault(r['id'], int(sz)) != int(sz):
                    return 'duplicate', None
        if not objs:
            return 'shape', None
    if listing and not all(cps.values()):
        return 'listing', None
    return None, {n: sorted([k, v] for k, v in c.items()) for n, c in cps.items()}


def parse_answer(argv):
    """`answer --at A key=value ...` -> (at, [(key, value)]) in the order given."""
    if len(argv) < 2 or argv[0] != '--at':
        raise Usage('answer --at')
    pairs = []
    for a in argv[2:]:
        if '=' not in a or a.startswith('='):
            raise Usage('key=value')
        k, v = a.split('=', 1)
        pairs.append((k, v))
    return argv[1], pairs
