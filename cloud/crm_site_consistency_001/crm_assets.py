"""Content-addressed cover assets: old pages keep their original images on rollback."""
import hashlib
import io
import os
from pathlib import Path
import re
import tempfile


def save_immutable(image, folder, code, extension, **options):
    if not re.fullmatch(r'UA-\d{4,}', code) or extension not in ('jpg','webp'):
        raise ValueError('Invalid asset identity')
    buffer = io.BytesIO()
    image.save(buffer, format={'jpg':'JPEG','webp':'WEBP'}[extension], **options)
    data = buffer.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (code + '-' + digest + '.' + extension)
    if target.is_symlink():
        raise RuntimeError('Asset symlink is not permitted')
    if target.exists():
        if target.read_bytes() != data:
            raise RuntimeError('Immutable asset content mismatch')
        return str(target)
    handle = tempfile.NamedTemporaryFile(dir=folder, prefix='.crm-asset-', delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, target)
        except FileExistsError:
            pass
        if target.is_symlink() or target.read_bytes() != data:
            raise RuntimeError('Concurrent immutable asset mismatch')
    finally:
        temporary.unlink(missing_ok=True)
    return str(target)
