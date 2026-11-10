"""The module-level names the reused v1 segments load that are not themselves reused (spec §1.5). New code, reviewed
in full. Values copied from deploy/vm/cps_vm.py at 95df270 where the table says so; `Halt` keeps v1's attributes
without `to_block` (vio maps every Halt to a v2 block, §13.4); `Block` is an inert record that stores and never prints."""
import json
import os
from pathlib import Path

CHUNK = 1 << 20
BOOT_ID_DEFAULT = '/proc/sys/kernel/random/boot_id'
_VIO = Path(os.path.realpath(os.path.dirname(os.path.abspath(__file__))))      # deploy/vm2/cpsvm2/vio
HELPER_REPO = _VIO.parents[3]                                                   # the repository root
HELPER_FILE = Path(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'vm2.py')))
EXIT_OK, EXIT_USAGE, EXIT_STOP, EXIT_REFUSED, EXIT_NEED, EXIT_BUSY = 0, 2, 3, 4, 10, 11
ARCHIVE_EXACT = {'MANIFEST.json': ('MANIFEST.json',), 'ledger': ('ledger', 'ledger/LEDGER.jsonl')}
PNG_SUBS = ('job/qa/visual_deliverable/', 'job/qa/visual_internal/')
SPACE_MARGIN = 64 * 1024 * 1024
QUAL_ROOTS = {'A': 'A', 'B': 'B', 'A-restart1': 'A_restart1', 'B-restart1': 'B_restart1', 'NA-A': 'nonattempts_A',
              'NA-B': 'nonattempts_B'}
ROOT_TAGS = {v: k for k, v in QUAL_ROOTS.items()}
CJ = None                                   # set by vio/runner.load_runner() after the pin check


def is_qual_tag(tag):
    return tag in QUAL_ROOTS


def under(p, root):
    try:
        Path(os.path.abspath(p)).relative_to(os.path.abspath(root))
        return True
    except ValueError:
        return False


def note_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


def parse_name(name):
    """Stub (§1.5): v2 never passes a png.parts list, so a manifest that carries one is refused ('png part name')."""
    return None


def runner_path():
    return HELPER_REPO / 'deploy/run/cps_job.py'


def wait_block(ctx, seconds):
    """The modified wait_block of v1mod.py (§1.6), imported late (v1mod imports v1reuse, which imports this module)."""
    from .v1mod import wait_block as w
    return w(ctx, seconds)


class Halt(Exception):
    """kind: REFUSED (exit 4, nothing changed, no UPLOAD), STOP (exit 3), NEED (exit 10), BUSY (exit 11)."""
    def __init__(self, kind, code, hint='', block=None, exit_code=None, detail=None):
        super().__init__(code)
        self.kind, self.code, self.hint, self.block, self.detail = kind, code, hint, block, detail
        self.exit_code = exit_code if exit_code is not None else {'REFUSED': EXIT_REFUSED, 'STOP': EXIT_STOP,
                                                                    'NEED': EXIT_NEED, 'BUSY': EXIT_BUSY}[kind]


def refuse(code, hint='', detail=None, block=None):
    raise Halt('REFUSED', code, hint, block=block, detail=detail)


def stop(code, hint='', block=None, detail=None):
    raise Halt('STOP', code, hint, block=block, detail=detail)


def need(block, code='NEED_DOWNLOADS', detail=None):
    raise Halt('NEED', code, block=block, detail=detail)


class Block:
    """Inert record with v1's attribute and method names; it stores and never prints (§1.5)."""
    def __init__(self):
        self.uploads, self.fetch, self.tail, self.result, self.code, self.raw_text = [], [], [], {}, 0, None

    def upload(self, path, folder):
        self.uploads.append(('UPLOAD', str(path), folder))

    def listing(self, folder, path):
        self.fetch.append(('LISTING', folder, str(path)))

    def download(self, did, name, path):
        self.fetch.append(('DOWNLOAD', did, name, str(path)))

    def next(self, s):
        self.tail.append('NEXT: ' + s)

    def then(self, s):
        self.tail.append('THEN: ' + s)

    def option(self, code, s):
        self.tail.append('OPTION: %s %s' % (code, s))
