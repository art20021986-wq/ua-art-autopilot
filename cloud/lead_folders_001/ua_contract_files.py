"""Contract files of orders (LEAD-FOLDERS-001): kept on the server outside the published site folders.

The client bot receives the file (a Telegram file id belongs to one bot), saves it here, and the CRM bot sends it
from here. A stored name is '<lead>-<time>.<ext>' with a safe lead part; paths outside the folder are refused.
"""
from pathlib import Path
import os
import re
import tempfile
import time

ROOT = Path('/home/Carix/private/contracts')
EXTENSIONS = ('pdf', 'jpg', 'jpeg', 'png', 'heic', 'doc', 'docx')
MAX_BYTES = 20 * 1024 * 1024  # what a Telegram bot may download
NAME = re.compile(r'[a-z0-9-]{1,80}-[0-9]{10}\.(?:%s)' % '|'.join(EXTENSIONS))


def extension(file_name, mime_type=None):
    """The kept extension of an uploaded contract, or None for a file that is not a document or a picture."""
    found = re.search(r'\.([A-Za-z0-9]{2,5})$', file_name or '')
    value = found.group(1).lower() if found else {'application/pdf': 'pdf', 'image/jpeg': 'jpg',
                                                    'image/png': 'png'}.get(mime_type or '')
    return value if value in EXTENSIONS else None


def save(lead_key, data, ext, *, root=None, clock=time.time):
    root = Path(root or ROOT)
    if ext not in EXTENSIONS or not data or len(data) > MAX_BYTES:
        raise ValueError('contract_file')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = '%s-%d.%s' % (re.sub(r'[^a-z0-9]+', '-', lead_key.lower()).strip('-')[:80] or 'lead', int(clock()), ext)
    descriptor, temporary = tempfile.mkstemp(dir=root, prefix='.contract-')
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, root / name)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return name


def path(name, *, root=None):
    root = Path(root or ROOT)
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError('contract_file')
    return root / name
