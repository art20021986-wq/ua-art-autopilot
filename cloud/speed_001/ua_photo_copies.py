"""SPEED-001: the lighter copies of a car photo that the card generator already made, when they exist.

The generator keeps each card photo foto/UA-XXXX/NNN.jpg with copies m/ (1000 px wide) and s/ (440 px).
Pages that show a photo small can use a copy instead of the large file. Nothing is created here.
"""
from pathlib import Path
import re

VIDEO = Path(__file__).resolve().parent / 'video'
PHOTO = re.compile(r'(?P<prefix>(?:/video/)?)(?P<card>foto/UA-[0-9]{4,})/(?:[ms]/)?(?P<name>[^/?#]+\.jpe?g)')
WIDTHS = {'s': 440, 'm': 1000}


def copy(url, folder):
    """The URL of the copy in folder ('s' or 'm') in the same form as url, or None if there is none."""
    match = PHOTO.fullmatch(url) if isinstance(url, str) else None
    if not match or folder not in WIDTHS:
        return None
    relative = '%s/%s/%s' % (match['card'], folder, match['name'])
    return match['prefix'] + relative if (VIDEO / relative).is_file() else None


def srcset(url):
    """'s-url 440w, m-url 1000w' when both copies exist, else ''."""
    copies = [(copy(url, folder), width) for folder, width in sorted(WIDTHS.items(), key=lambda item: item[1])]
    return ', '.join('%s %dw' % pair for pair in copies) if all(url for url, _ in copies) else ''
