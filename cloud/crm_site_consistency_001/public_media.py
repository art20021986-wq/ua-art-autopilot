"""Structural photo gate, not proof of image identity or binary freshness.

Full acceptance additionally requires a verified CRM file_id -> content manifest.
Never infer that mapping from an ordinal filename or an equal photo count.
"""
import json
import re
from html.parser import HTMLParser


def _list(value):
    value = json.loads(value) if isinstance(value, str) and value else (value or [])
    if not isinstance(value, list):
        raise RuntimeError('Invalid CRM photo list')
    return value


def visible_photo_ids(card):
    photos = _list(card.get('photos'))
    ids = [p.get('file_id') if isinstance(p, dict) else p for p in photos]
    hidden = _list(card.get('hidden_photos'))
    if any(not isinstance(x, str) or not x.strip() for x in ids + hidden):
        raise RuntimeError('Invalid CRM photo identity')
    if len(ids) != len(set(ids)):
        raise RuntimeError('Duplicate CRM photo identity')
    return [x for x in ids if x not in set(hidden)]


class PhotoHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.scripts = []
        self.script = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'img':
            self.images.append(attrs.get('src', ''))
        if tag == 'script':
            self.script = []

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.scripts.append(''.join(self.script))
            self.script = None


def verify_photo_structure(html, card):
    code = card.get('auto_number', '')
    if not re.fullmatch(r'UA-\d{4,}', code):
        raise RuntimeError('Invalid car code')
    expected_ids = visible_photo_ids(card)
    doc = PhotoHTML()
    doc.feed(html)
    groups = []
    for script in doc.scripts:
        groups.extend(re.findall(r'\bvar\s+kadry\s*=\s*(\[.*?\])\s*;', script, re.S))
    if len(groups) != 1:
        raise RuntimeError('Missing or ambiguous gallery')
    gallery = json.loads(groups[0])
    pattern = r'foto/' + re.escape(code) + r'/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)'
    if not isinstance(gallery, list) or any(not isinstance(x, str) or not re.fullmatch(pattern, x) for x in gallery):
        raise RuntimeError('Unsupported or foreign gallery path')
    if len(gallery) != len(set(gallery)):
        raise RuntimeError('Duplicate gallery image')
    if len(gallery) != len(expected_ids):
        raise RuntimeError('CRM visible photo count differs from gallery')
    prefix = 'foto/' + code + '/'
    rendered = [x.replace(prefix + 'm/', prefix, 1) for x in doc.images if x.startswith(prefix)]
    if rendered != gallery:
        raise RuntimeError('Visible photo order differs from lightbox')
    cover = card.get('cover_photo')
    if cover:
        if not isinstance(cover, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)', cover):
            raise RuntimeError('Unverified CRM cover path')
        if not gallery or gallery[0] != prefix + cover:
            raise RuntimeError('CRM cover differs from first gallery photo')
    return {'photo_count': len(gallery), 'structure_verified': True,
            'content_identity_verified': False, 'full_consistency_accepted': False}
