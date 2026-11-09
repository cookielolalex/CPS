"""CPS: `soffice --convert-to pdf` through LibreOfficeKit, inside this process, without LibreOffice's IPC socket.

Why: `soffice` starts by binding a Unix socket in /tmp (OSL_PIPE_<uid>_SingleOfficeIPC_<hash>) so that a second
start can hand its arguments to the first one. Some agent sandboxes refuse that. LibreOffice then exits 1 at once,
silently, before it opens any file (the Dot's VM, 2026-11-09). LibreOfficeKit loads the same LibreOffice libraries
in-process and saves through the same PDF export filter, without that socket.

When it is used: the no-root setup (deploy/setup_vm_user.sh) installs this file as <prefix>/share/cps/lok_convert.py.
It first tries a PDF conversion with `soffice` itself. Only if that fails does it switch the prefix's `soffice`
wrapper to run every `--convert-to pdf` call through this file, after the same check passes this way. The setup
summary records which route the host uses. Every other call (--version, --convert-to png) always goes to
LibreOffice's own launcher.

Differences from `soffice --convert-to pdf`, on the LibreOfficeKit route:
- Default paper. LibreOfficeKit runs with an en-US configuration, so a sheet without its own page setup prints on
  Letter, where soffice under LC_ALL=C.UTF-8 uses A4. The CPS visual QA (fit-width mode, the one the job runner
  uses) sets the page setup itself, so its renders of the delivered workbook are unchanged. Unpatched renders, such
  as the interview example images, may break pages differently.
- Row heights. Automatic row heights of long wrapped text can come out slightly smaller, which can move later page
  breaks. This was seen in the internal QA workbook's review sheet.
- Exit codes. A file that cannot be loaded or saved gives exit 1 (soffice may still exit 0).
- PNG. Refused: LibreOfficeKit's PNG export does not work for spreadsheets in this build.

Usage (the wrapper adds the program directory first):
  lok_convert.py PROGRAM_DIR [--headless] [--norestore] [--nolockcheck] [--nologo] [--nodefault] [--invisible]
                 [--nofirststartwizard] [-env:UserInstallation=FILE_URL] --convert-to pdf [--outdir DIR] FILE...
Options take one or two leading dashes, as with soffice. Anything else is refused with exit 2 before LibreOffice
starts. Each FILE is written to DIR/<FILE stem>.pdf (DIR is created if needed; default the current directory), and
an existing output is replaced. Each output line ends with "(LibreOfficeKit)". Exit 0 only when every PDF was
written; 1 otherwise.
"""
import ctypes
import locale
import os
import shutil
import sys
import tempfile
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
    # soffice names the output after the path as given (a symlink's own name), so no resolve() here
    return profile, fmt, Path(os.path.abspath(outdir or os.curdir)), [Path(os.path.abspath(f)) for f in files]


def convert(argv):
    if len(argv) < 2:
        print('usage: lok_convert.py PROGRAM_DIR SOFFICE_ARGS...', file=sys.stderr)
        return 2
    prog = Path(argv[1])
    try:
        profile, fmt, outdir, files = parse(argv[2:])
    except UsageError as e:
        print('lok_convert: ' + str(e), file=sys.stderr)
        return 2
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f'lok_convert: cannot create the output directory {outdir}: {e}', file=sys.stderr)
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
        dst = outdir / (src.stem + '.' + fmt)
        try:
            if not src.is_file():
                raise RuntimeError(f'Error: source file could not be loaded: {src} (no such file)')
            doc = load(kit, src.as_uri().encode())
            if not doc:
                err = get_error(kit)
                raise RuntimeError(f'Error: source file could not be loaded: {src} '
                                   f'({err.decode("utf-8", "replace") if err else "no detail"})')
            dc = doc.contents.pClass.contents
            save = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(_Doc), ctypes.c_char_p, ctypes.c_char_p,
                                    ctypes.c_char_p)(dc.saveAs)
            doc_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(_Doc))(dc.getDocumentType)(doc)
            try:
                if dst.exists() or dst.is_symlink():
                    dst.unlink()
                ok = save(doc, dst.as_uri().encode(), fmt.encode(), None)
            finally:
                ctypes.CFUNCTYPE(None, ctypes.POINTER(_Doc))(dc.destroy)(doc)
            if not ok or not dst.is_file() or dst.stat().st_size == 0:
                raise RuntimeError(f'Error: could not write {dst}')
            print(f'convert {src} as a {DOC_TYPES.get(doc_type, "LibreOffice")} document -> {dst} (LibreOfficeKit)')
        except Exception as e:  # one file's failure must not stop the others, nor skip os._exit
            print(str(e) if isinstance(e, RuntimeError) else f'Error: {src}: {type(e).__name__}: {e}', file=sys.stderr)
            failed += 1
    return 1 if failed else 0


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='backslashreplace')
        except (AttributeError, ValueError):
            pass
    # LibreOfficeKit maps file URLs to paths in the process's character encoding: under an ASCII locale (LC_ALL=C) a
    # file whose path holds Chinese characters would not load, while soffice loads it. So use UTF-8 when it is not
    try:
        if locale.nl_langinfo(locale.CODESET).upper().replace('-', '') != 'UTF8':
            locale.setlocale(locale.LC_CTYPE, 'C.UTF-8')
            for var in ('LC_ALL', 'LC_CTYPE'):
                if os.environ.get(var):
                    os.environ[var] = 'C.UTF-8'
    except (locale.Error, AttributeError):
        pass
    # LibreOffice's own temporary files (lu*.tmp) go to a private folder, removed below: os._exit skips its cleanup
    private_tmp = tempfile.mkdtemp(prefix='cps_lok_')
    os.environ['TMPDIR'] = private_tmp
    code = 1
    try:
        code = convert(sys.argv)
    except BaseException as e:  # never fall through to interpreter shutdown with LibreOfficeKit's threads alive
        print(f'lok_convert: {type(e).__name__}: {e}', file=sys.stderr)
        code = 1
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        shutil.rmtree(private_tmp, ignore_errors=True)
        # LibreOfficeKit's own shutdown can wait on threads it started; every output is complete and closed by now
        os._exit(code)


if __name__ == '__main__':
    main()
