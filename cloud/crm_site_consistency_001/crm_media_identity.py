"""Stable source bindings and immutable public copies of mapped local media.

The ledger records identity; this module verifies/copies local bytes. It does
not claim that an old ledger entry proves equality with a Telegram original.
Unreferenced files are retained for rollback and never selected automatically.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


def valid_name(code, kind, name):
    if not isinstance(name, str):
        return False
    pattern = (r'(?:\d+|m-[0-9a-f]{64})\.jpg' if kind == 'photo' else
               re.escape(code) + r'(?:-\d{2,}|-m-[0-9a-f]{64})?\.mp4')
    return re.fullmatch(pattern, name) is not None


def stable_names(code, kind, ids, mapping):
    """Changing CRM order must never overwrite another file_id's filename."""
    if not re.fullmatch(r'UA-\d{4,}', code) or kind not in ('photo', 'video'):
        raise RuntimeError('Invalid media owner or kind')
    if not isinstance(mapping, dict):
        raise RuntimeError('Invalid media mapping')
    reverse = {}
    for name, fid in mapping.items():
        if not valid_name(code, kind, name) or not isinstance(fid, str) or not fid:
            raise RuntimeError('Invalid media binding')
        if fid in reverse:
            raise RuntimeError('Ambiguous media binding')
        reverse[fid] = name
    result = {}
    for fid in ids:
        if not isinstance(fid, str) or not fid or fid in result.values():
            raise RuntimeError('Invalid or duplicate CRM media identity')
        name = reverse.get(fid)
        if name is None:
            digest = hashlib.sha256(fid.encode()).hexdigest()
            name = ('m-' + digest + '.jpg' if kind == 'photo' else
                    code + '-m-' + digest + '.mp4')
        if name in mapping and mapping[name] != fid:
            raise RuntimeError('Media identity collision')
        result[name] = fid
    return result


def _stamp(path):
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def immutable_copy(path, root):
    """Atomic content-addressed copy; reject changed bytes under an old binding.

    Installed with the stable-name downloader. The signature cache avoids
    reading every large video on each publication. Changed signatures always
    trigger a full digest comparison; targets are never overwritten.
    """
    path, root = Path(path), Path(root)
    public = (root / 'video').resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(public):
        raise RuntimeError('Unsafe mapped media path')
    before = _stamp(path)
    if before[2] == 0:
        raise RuntimeError('Empty mapped media')
    cache = root / '.crm_media_index'
    if cache.is_symlink():
        raise RuntimeError('Unsafe media index')
    cache.mkdir(mode=0o700, exist_ok=True)
    key = hashlib.sha256(str(path.relative_to(root / 'video')).encode()).hexdigest()
    index = cache / (key + '.json')
    saved = json.loads(index.read_text()) if index.exists() else None
    if saved:
        if not re.fullmatch(r'[0-9a-f]{64}', str(saved.get('sha256', ''))):
            raise RuntimeError('Invalid media content index')
        target = path.parent / (path.stem + '-' + saved['sha256'] + path.suffix)
        if (saved['source_stat'] == before and not target.is_symlink()
                and target.is_file() and saved['target_stat'] == _stamp(target)):
            return target
    if shutil.disk_usage(path.parent).free < before[2] + 64 * 1024 * 1024:
        raise RuntimeError('Insufficient space for immutable media; retry pending')
    fd, temporary = tempfile.mkstemp(prefix='.crm-copy-', dir=path.parent)
    temporary = Path(temporary)
    try:
        digest = hashlib.sha256()
        with os.fdopen(fd, 'wb') as dst, path.open('rb') as src:
            while chunk := src.read(1024 * 1024):
                digest.update(chunk)
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        if _stamp(path) != before:
            raise RuntimeError('Mapped media changed while copying')
        digest = digest.hexdigest()
        if saved and saved['sha256'] != digest:
            raise RuntimeError('Bytes changed under an existing CRM binding')
        target = path.parent / (path.stem + '-' + digest + path.suffix)
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.is_symlink() or _hash(target) != digest:
                raise RuntimeError('Immutable public media corrupted')
        # Unlink changes the target inode's ctime/link count; cache only after it.
        temporary.unlink()
        record = {'sha256': digest, 'size': before[2], 'source_stat': before,
                  'target_stat': _stamp(target), 'telegram_original_verified': False}
        handle = tempfile.NamedTemporaryFile(mode='w', dir=cache, delete=False)
        staged = Path(handle.name)
        try:
            with handle:
                json.dump(record, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staged, index)
        finally:
            staged.unlink(missing_ok=True)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def poster_path(video_path, root='/home/Carix'):
    """Bind a poster to the same immutable video version, without a disk scan."""
    if not isinstance(video_path, str) or Path(video_path).name != video_path:
        raise RuntimeError('Invalid video poster source')
    source_name = re.sub(r'-[0-9a-f]{64}\.mp4$', '.mp4', video_path)
    folder = Path(root) / 'video'
    candidates = [folder / (source_name + '.poster.jpg'),
                  folder / (Path(source_name).stem + '.poster.jpg')]
    source = next((p for p in candidates if p.is_file()), None)
    if source is None:
        return ''
    return str(immutable_copy(source, root).relative_to(Path(root) / 'video'))


def poster_attribute(video_path):
    path = poster_path(video_path)
    return " poster='%s'" % path if path else ''


def source_unchanged(path, root):
    """A modified mapped file must be downloaded again, not silently accepted."""
    path, root = Path(path), Path(root)
    key = hashlib.sha256(str(path.relative_to(root / 'video')).encode()).hexdigest()
    index = root / '.crm_media_index' / (key + '.json')
    if not index.exists():
        return True
    if path.is_symlink() or not path.is_file():
        return False
    record = json.loads(index.read_text())
    return record['source_stat'] == _stamp(path) or _hash(path) == record['sha256']
