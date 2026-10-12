"""Diagnostics media a card's diag page is built from: /home/Carix/video/diag/<code>/.

Mirrors stranica.kadry_diagnostiki (photos jpg/jpeg/JPG/png over 1000 bytes, first 50;
videos *.mp4, first 10). Generated posters are excluded so a publication never changes
its own input. Names only: re-encoding a file in place must not trigger republication.
"""
import fnmatch
from pathlib import Path

DIAG = Path('/home/Carix/video/diag')
PHOTO_PATTERNS = ('*.jpg', '*.jpeg', '*.JPG', '*.png')
PHOTO_LIMIT, VIDEO_LIMIT, MIN_PHOTO_BYTES = 50, 10, 1000


def names(code, root=None):
    """Sorted file names that the diag page shows; [] when there are none."""
    try:
        entries = [p for p in (Path(root or DIAG) / code).iterdir() if p.is_file() and '.poster.' not in p.name]
    except (FileNotFoundError, NotADirectoryError):
        return []
    photos = sorted(p.name for p in entries
                    if any(fnmatch.fnmatchcase(p.name, x) for x in PHOTO_PATTERNS)
                    and p.stat().st_size > MIN_PHOTO_BYTES)[:PHOTO_LIMIT]
    videos = sorted(p.name for p in entries if fnmatch.fnmatchcase(p.name, '*.mp4'))[:VIDEO_LIMIT]
    return sorted(photos + videos)
