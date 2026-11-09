"""CPS: `soffice --convert-to` through LibreOfficeKit, inside this process, without LibreOffice's IPC socket.

Why: `soffice` starts by binding a Unix socket in /tmp (OSL_PIPE_<uid>_SingleOfficeIPC_<hash>) so that a second
start can hand its arguments to the first one. Some agent sandboxes refuse bind() for every process. LibreOffice then
exits 1 at once, silently, before it opens any file (seen on the Dot's VM on 2026-11-09). LibreOfficeKit loads the
same LibreOffice libraries in-process and saves through the same export filters, without that socket.

The no-root setup (deploy/setup_vm_user.sh) installs this file as <prefix>/share/cps/lok_convert.py. The prefix's
`soffice` wrapper runs it for every call with `--convert-to pdf`, the only conversion the CPS tools use (visual QA,
the example renderer, the setup check). Every other call (--version, or --convert-to png, which only visual QA's
no-pdftoppm fallback would use) goes to LibreOffice's own launcher, as before. LibreOfficeKit's PNG export does not
work for spreadsheets in this build, so this file refuses png.

Usage (the wrapper adds the program directory first):
  lok_convert.py PROGRAM_DIR [--headless] [--norestore] [--nolockcheck] [--nologo] [--nodefault] [--invisible]
                 [--nofirststartwizard] [-env:UserInstallation=FILE_URL] --convert-to pdf --outdir DIR FILE...
Accepted, as by soffice: one or two leading dashes. Anything else is refused with exit 2 before LibreOffice starts.
Each FILE is written to DIR/<FILE stem>.pdf; an existing output is replaced. Exit 0 only when every output was
written; 1 when LibreOfficeKit cannot start, a file cannot be loaded, or an output is missing.
"""
import ctypes
import os
import sys
from pathlib import Path

IGNORED_FLAGS = {'headless', 'norestore', 'nolockcheck', 'nologo', 'nodefault', 'invisible', 'nofirststartwizard'}
FORMATS = {'pdf'}
DOC_TYPES = {0: 'Writer', 1: 'Calc', 2: 'Impress', 3: 'Draw'}


class _DocClass(ctypes.Structure):
    _fields_ = [('nSize', ctypes.c_size_t), ('destroy', ctypes.c_void_p), ('saveAs', ctypes.c_void_p),
                ('getDocumentType', ctypes.c_void_p)]


class _Doc(ctypes.Structure):
    _fields_ = [('pClass', ctypes.POINTER(_DocClass))]


class _KitClass(ctypes.Structure):
    _fields_ = [('nSize', ctypes.c_size_t), ('destroy', ctypes.c_void_p), ('documentLoad', ctypes.c_void_p),
                ('getError', ctypes.c_void_p)]


class _Kit(ctypes.Structure):
    _fields_ = [('pClass', ctypes.POINTER(_KitClass))]


class UsageError(Exception):
    pass


def parse(argv):
    """Returns (profile_url or None, format, outdir, [files]) from soffice-style arguments."""
    profile, fmt, outdir, files = None, None, None, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith('-') and len(a) > 1:
            name = a.lstrip('-')
            if name.startswith('env:'):
                key, sep, value = name[4:].partition('=')
                if key != 'UserInstallation' or not sep or not value.startswith('file:///'):
                    raise UsageError(f'unsupported option {a!r} (only -env:UserInstallation=file:///...)')
                profile = value
            elif name in IGNORED_FLAGS:
                pass
            elif name in ('convert-to', 'outdir'):
                if i + 1 >= len(argv):
                    raise UsageError(f'{a} needs a value')
                i += 1
                if name == 'convert-to':
                    if argv[i] not in FORMATS:
                        raise UsageError(f'unsupported --convert-to {argv[i]!r} (only pdf, without a filter name)')
                    fmt = argv[i]
                else:
                    outdir = argv[i]
            else:
                raise UsageError(f'unsupported option {a!r}')
        else:
            files.append(a)
        i += 1
    if fmt is None:
        raise UsageError('--convert-to is required')
    if not files:
        raise UsageError('no input file')
    return profile, fmt, Path(outdir) if outdir else Path.cwd(), [Path(f) for f in files]


def main(argv):
    if len(argv) < 2:
        print('usage: lok_convert.py PROGRAM_DIR SOFFICE_ARGS...', file=sys.stderr)
        return 2
    prog = Path(argv[1])
    try:
        profile, fmt, outdir, files = parse(argv[2:])
    except UsageError as e:
        print('lok_convert: ' + str(e), file=sys.stderr)
        return 2
    if not outdir.is_dir():
        print(f'lok_convert: output directory {outdir} does not exist', file=sys.stderr)
        return 1
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        print('Error: source file could not be loaded: ' + ', '.join(missing), file=sys.stderr)
        return 1
    try:
        lib = ctypes.CDLL(str(prog / 'libmergedlo.so'), mode=ctypes.RTLD_GLOBAL)
    except OSError as e:
        print(f'lok_convert: cannot load {prog / "libmergedlo.so"}: {e}', file=sys.stderr)
        return 1
    hook = lib.libreofficekit_hook_2
    hook.restype = ctypes.POINTER(_Kit)
    hook.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    kit = hook(str(prog).encode(), profile.encode() if profile else None)
    if not kit:
        print('lok_convert: LibreOfficeKit did not start', file=sys.stderr)
        return 1
    kc = kit.contents.pClass.contents
    load = ctypes.CFUNCTYPE(ctypes.POINTER(_Doc), ctypes.POINTER(_Kit), ctypes.c_char_p)(kc.documentLoad)
    get_error = ctypes.CFUNCTYPE(ctypes.c_char_p, ctypes.POINTER(_Kit))(kc.getError)
    failed = 0
    for src in files:
        src = src.resolve()
        dst = (outdir / (src.stem + '.' + fmt)).resolve()
        doc = load(kit, src.as_uri().encode())
        if not doc:
            err = get_error(kit)
            print(f'Error: source file could not be loaded: {src} ({err.decode("utf-8", "replace") if err else "no detail"})',
                  file=sys.stderr)
            failed += 1
            continue
        dc = doc.contents.pClass.contents
        save = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(_Doc), ctypes.c_char_p, ctypes.c_char_p,
                                ctypes.c_char_p)(dc.saveAs)
        doc_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(_Doc))(dc.getDocumentType)(doc)
        if dst.exists():
            dst.unlink()
        ok = save(doc, dst.as_uri().encode(), fmt.encode(), None)
        destroy = ctypes.CFUNCTYPE(None, ctypes.POINTER(_Doc))(dc.destroy)
        destroy(doc)
        if not ok or not dst.is_file() or dst.stat().st_size == 0:
            print(f'Error: could not write {dst}', file=sys.stderr)
            failed += 1
            continue
        print(f'convert {src} as a {DOC_TYPES.get(doc_type, "LibreOffice")} document -> {dst} (LibreOfficeKit)')
    return 1 if failed else 0


if __name__ == '__main__':
    code = main(sys.argv)
    sys.stdout.flush()
    sys.stderr.flush()
    # LibreOfficeKit's own shutdown can wait on threads it started; every output is complete and closed by now
    os._exit(code)
