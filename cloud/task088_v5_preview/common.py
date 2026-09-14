"""Bounded reads and exact manifest paths shared by the protected Preview tools."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import stat

CONTRACT = 'UA-ART-V5-PROTECTED-PREVIEW-1'
MAX_FILE_BYTES = 32 * 1024 * 1024
ASSET_TYPES = {'.css':'text/css; charset=utf-8', '.js':'application/javascript; charset=utf-8',
    '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.gif':'image/gif',
    '.webp':'image/webp', '.avif':'image/avif', '.svg':'image/svg+xml', '.ico':'image/x-icon',
    '.woff':'font/woff', '.woff2':'font/woff2', '.ttf':'font/ttf',
    '.mp4':'video/mp4', '.webm':'video/webm', '.mp3':'audio/mpeg', '.ogg':'audio/ogg'}


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(value):
    if (type(value) is not str or not value or '\\' in value or '%' in value or '\x00' in value
            or value.startswith('/') or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('EXACT_RELATIVE_MANIFEST_PATH_REQUIRED')
    if str(PurePosixPath(value)) != value:
        raise ValueError('NON_CANONICAL_MANIFEST_PATH')
    return value


def read(root, name, *, private=False):
    root = Path(root).resolve(strict=True)
    path = root / relative(name)
    path.resolve(strict=True).relative_to(root)
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('SYMLINK_IN_PREVIEW_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            raise ValueError('REGULAR_BOUNDED_PUBLIC_FILE_REQUIRED')
        if private and stat.S_IMODE(before.st_mode) & 0o077:
            raise ValueError('PRIVATE_CONFIG_MODE_REQUIRED')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        after = os.fstat(fd)
        if len(raw) > MAX_FILE_BYTES or (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
            raise ValueError('FILE_CHANGED_DURING_READ')
        return raw
    finally:
        os.close(fd)


def write_new(root, name, raw):
    root = Path(root).resolve(strict=True)
    path = root / relative(name)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('SYMLINK_IN_PREVIEW_PATH')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
