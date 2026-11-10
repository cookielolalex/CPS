"""Block printing (spec §6.1, §6.4) and the parsing of `found` and `answer` arguments (§6.2). A block is the header,
UPLOAD, FIND/LIST, DOWNLOAD lines and exactly one `DO:` line. Every path and folder is printed shlex-quoted and
round-trips through shlex.split (else INTERNAL_PRINT); nothing printed is non-ASCII. The `--at` value is computed by
the glue over the lines rendered with the placeholder AT_MARK, then substituted."""
import re
import shlex

from .v1compat import Halt

AT_MARK = '@AT@'
FOUND_TRIPLE = r'([^:]+):([^:]+):([^:]+)'


def q(value):
    """shlex-quoted value; INTERNAL_PRINT when it would not round-trip or is not ASCII."""
    s = str(value)
    out = shlex.quote(s)
    if not s or not s.isascii() or '\n' in s or shlex.split(out) != [s]:
        raise Halt('STOP', 'INTERNAL_PRINT', 'a printed value does not round-trip')
    return out


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
    """The lines after the header for a PrintBlock-like object (uploads, finds, lists, downloads, do)."""
    out = ['UPLOAD %s TO %s AS %s' % (q(p), q(f), word(n)) for p, f, n in block.uploads]
    for f, how, v in block.finds:
        out.append('FIND %s %s %s' % (q(f), how, word(v)))
    for f, k in block.lists:
        out.append('LIST %s NEWEST %d' % (q(f), int(k)))
    for f, did, p in block.downloads:
        out.append('DOWNLOAD %s ID %s TO %s' % (q(f), word(did), q(p)))
    out.append('DO: ' + do_text(block.do, vm))
    return out


def do_text(do, vm):
    act, args = do
    if act == 'RUN':
        return 'RUN bash %s go' % q(vm)
    if act == 'WAIT':
        return 'WAIT seconds=%d' % int(args['seconds'])
    if act == 'STOP':
        if args.get('handback') is None:
            return 'STOP ' + word(args['code'])
        return 'STOP %s HANDBACK %s' % (word(args['code']), args['handback'])
    if act == 'ATTEST_FOUND':
        return found_attest(vm, args)
    if act == 'ATTEST_ANSWER':
        pre = ''
        if args.get('prefix'):
            pre = args['prefix'][0] + ''.join(' %s=%s' % (k, word(v)) for k, v in args['prefix'][1].items()) + ' '
        if args.get('after'):
            pre += 'ATTEST after=%s bash %s answer --at %s ' % (word(args['after']), q(vm), AT_MARK)
        else:
            pre += 'ATTEST bash %s answer --at %s ' % (q(vm), AT_MARK)
        return pre + '%s' % (' '.join(
            '%s=%s' % (k, p) for k, p in args['keys'].items()))
    return act + ''.join(' %s=%s' % (k, word(v)) for k, v in args.items())


def found_attest(vm, args):
    trip = 'ID:SIZE' if args.get('md5_hidden') else 'ID:MD5:SIZE'
    if args.get('list'):
        return 'ATTEST bash %s found --at %s (--file NAME:%s ... | --none)' % (q(vm), AT_MARK, trip)
    up = set(args.get('uploaded') or ())
    return 'ATTEST bash %s found --at %s %s' % (q(vm), AT_MARK, ' '.join(
        '--name %s%s (--file %s ... | --none)' % (word(n), ' [--refused]' if n in up else '', trip)
        for n in args['names']))


def check_grammar(lines):
    """§6.1 block grammar (lint L5): header, then UPLOAD*, FIND*/LIST*, DOWNLOAD*, exactly one DO: line last; no
    THEN/OPTION, no {TOKEN}, ASCII only. Returns None or a reason."""
    if not lines or not re.fullmatch(r'CPSV series=\S+ head=[0-9]{6} kit=(none|[0-9a-f]{12}) at=\S+ mode='
                                     r'(qualification|everyday|drill|setup) state=[A-Z]+', lines[0]):
        return 'header'
    body = lines[1:]
    if body and body[0].startswith('REFUSED '):
        body = body[1:]
    order = {'UPLOAD': 0, 'FIND': 1, 'LIST': 1, 'DOWNLOAD': 2, 'DO:': 3}
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
    """§6.1 (delta §X.6.1) line forms: UPLOAD <path> TO <folder> AS <name>, FIND <folder> NAME <name>, LIST <folder>
    NEWEST <k>, DOWNLOAD <folder> ID <id> TO <path>; the prefix forms are deleted."""
    try:
        t = shlex.split(ln)
    except ValueError:
        return False
    want = {'UPLOAD': (6, {2: 'TO', 4: 'AS'}), 'FIND': (4, {2: 'NAME'}), 'LIST': (4, {2: 'NEWEST'}),
            'DOWNLOAD': (6, {2: 'ID', 4: 'TO'})}[t[0]]
    return len(t) == want[0] and all(t[j] == v for j, v in want[1].items()) and (t[0] != 'LIST' or t[3].isdigit())


# ---------------------------------------------------------------- argument parsing (§6.2, §6.3)
class Usage(Exception):
    """Argument syntax: exit 2, the current block printed again."""


def parse_found(argv):
    """`found --at A (--name N [--refused] (--file F ... | --none))+` or, for a LIST answer, `found --at A (--file F
    ... | --none)`. Returns (at, [[name or None, [F], none, refused]]); a malformed F is checked later (parse_copy)."""
    if len(argv) < 3 or argv[0] != '--at':
        raise Usage('found --at')
    at, rest, out, cur = argv[1], argv[2:], [], None
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == '--name' and i + 1 < len(rest):
            cur = [rest[i + 1], [], False, False]
            out.append(cur)
            i += 2
            continue
        if a == '--refused':
            if cur is None or cur[0] is None or cur[3] or cur[1] or cur[2]:
                raise Usage(a)
            cur[3] = True
            i += 1
            continue
        if a in ('--file', '--none'):
            if cur is None:
                cur = [None, [], False, False]
                out.append(cur)
            if a == '--file':
                if i + 1 >= len(rest):
                    raise Usage('--file')
                cur[1].append(rest[i + 1])
                i += 2
            else:
                cur[2] = True
                i += 1
            continue
        raise Usage(a)
    return at, out


def check_found(items, names_expected, list_mode, uploaded=()):
    """REFUSED codes of the found syntax rules: (code or None, {name: [F] or None}, {names attested --refused}).
    `--refused` is allowed only on a name the block uploaded (§X.5.6 step 2)."""
    got, refused = {}, set()
    for name, files, none, ref in items:
        if (name is None) != list_mode or name in got or (ref and name not in uploaded):
            return 'FOUND_SYNTAX', None, None
        if ref:
            refused.add(name)
        if files and none:
            return 'FOUND_FILE_AND_NONE', None, None
        if not files and not none:
            return 'FOUND_SYNTAX', None, None
        got[name] = None if none else files
    if not list_mode and not set(names_expected) <= set(got):
        return 'FOUND_NAMES_INCOMPLETE', None, None
    return None, got, refused


def parse_copy(f, md5_hidden, with_name=False):
    """ID:MD5:SIZE (ID:SIZE when md5 is hidden; NAME:ID:MD5:SIZE for a LIST answer) -> tuple of str, or None."""
    parts = f.split(':')
    want = (3 if not md5_hidden else 2) + (1 if with_name else 0)
    return tuple(parts) if len(parts) == want and all(parts) else None


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
