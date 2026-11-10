"""Durable writes and the local cache self-hashes (spec §2.3, §2.4, SAFE-04). write() never leaves a partial file under
the final name; any OSError becomes DurableError(errno); the glue maps ENOSPC/EDQUOT to HALT DISK_FULL and everything
else to HALT WRITE_FAILED before anything of the block is printed."""
import errno
import hashlib
import json
import os
import secrets

from .v1compat import Halt


class DurableError(Exception):
    def __init__(self, err):
        super().__init__(err)
        self.errno = err

    @property
    def code(self):
        return 'DISK_FULL' if self.errno in (errno.ENOSPC, errno.EDQUOT) else 'WRITE_FAILED'


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(path, data, mode=0o644):
    """§2.4 steps 1-6. Returns sha256(data)."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise Halt('STOP', 'INTERNAL_EMPTY_OUTPUT', 'an output file would be empty')
    path = str(path)
    d, n = os.path.split(path)
    tmp = os.path.join(d, '.tmp_%d_%s_%s' % (os.getpid(), secrets.token_hex(4), n))[:4000]
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        try:
            view = memoryview(bytes(data))
            while len(view):
                k = os.write(fd, view)
                if k <= 0:
                    raise OSError(errno.EIO, 'short write')
                view = view[k:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        fsync_dir(d or '.')
        with open(path, 'rb') as f:
            back = f.read()
    except OSError as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise DurableError(e.errno or errno.EIO)
    if len(back) != len(data) or _sha(back) != _sha(bytes(data)):
        raise Halt('STOP', 'WRITE_READBACK_MISMATCH', 'a file read back differs from what was written')
    return _sha(back)


def seal(path, check=None):
    """§2.4: fsync the folder of a file written by write_tgz/PartWriter, then re-read it: check(path) re-reads an
    archive (Archive + check); without one, the file must be non-empty. Returns (bytes, sha256, md5)."""
    try:
        fsync_dir(os.path.dirname(str(path)) or '.')
        h, m, n = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
        with open(str(path), 'rb') as f:
            for c in iter(lambda: f.read(1 << 20), b''):
                h.update(c)
                m.update(c)
                n += len(c)
    except OSError as e:
        raise DurableError(e.errno or errno.EIO)
    if n == 0:
        raise Halt('STOP', 'INTERNAL_EMPTY_OUTPUT', 'an output file is empty')
    if check is not None:
        check(path)
    return n, h.hexdigest(), m.hexdigest()


def cjson(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def doc_bytes(x):
    """§0 doc_bytes: every JSON file the helper writes."""
    return (json.dumps(x, sort_keys=True, ensure_ascii=True, indent=1, allow_nan=False) + '\n').encode('ascii')


def write_doc(path, doc, mode=0o644):
    """A cache file (§2.3): doc_bytes with self_sha256 = sha(cjson(doc without self_sha256))."""
    d = {k: v for k, v in doc.items() if k != 'self_sha256'}
    d['self_sha256'] = _sha(cjson(d))
    write(path, doc_bytes(d), mode)
    return d


def write_plain(path, doc, mode=0o644):
    """A plain JSON document (no self hash): the self-test RUN.json."""
    return write(path, doc_bytes(doc), mode)


def read_doc(path, schema, sjson):
    """A cache file: (doc, None) when it parses strictly, has `schema` and a correct self_sha256; (None, why)
    otherwise; (None, None) when the file does not exist."""
    if not os.path.lexists(str(path)):
        return None, None
    try:
        with open(str(path), 'rb') as f:
            d = sjson(f.read())
    except (OSError, ValueError, UnicodeDecodeError):
        return None, 'unreadable'
    if not isinstance(d, dict) or d.get('schema') != schema:
        return None, 'schema'
    if d.get('self_sha256') != _sha(cjson({k: v for k, v in d.items() if k != 'self_sha256'})):
        return None, 'self_sha256'
    return d, None


def remove(path):
    """Remove a file and fsync its folder (PENDING removal, §5.1 step 8)."""
    try:
        os.unlink(str(path))
        fsync_dir(os.path.dirname(str(path)) or '.')
    except FileNotFoundError:
        pass
    except OSError as e:
        raise DurableError(e.errno or errno.EIO)
