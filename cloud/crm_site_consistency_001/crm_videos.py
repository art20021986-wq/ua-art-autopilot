"""Read-only video selection and HTML checks for the observed CRM schema.

The existing downloader ledger maps car code -> {MP4 filename: Telegram ID}.
This proves a recorded association, not identity of downloaded video bytes.
Never scan the directory, infer missing associations, or delete unmatched files.
"""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from public_media import _list


def _code(card):
    code = card.get('auto_number')
    if not isinstance(code, str) or not re.fullmatch(r'UA-\d{4,}', code):
        raise RuntimeError('Invalid car code')
    return code


def visible_video_ids(card):
    values = _list(card.get('videos'))
    ids = [v.get('file_id') if isinstance(v, dict) else v for v in values]
    hidden = _list(card.get('hidden_videos'))
    if any(not isinstance(v, str) or not v.strip() for v in ids + hidden):
        raise RuntimeError('Invalid CRM video identity')
    if len(ids) != len(set(ids)):
        raise RuntimeError('Duplicate CRM video identity')
    hidden = set(hidden)
    return [v for v in ids if v not in hidden]


def select_video_names(card, ledger):
    code = _code(card)
    ids = visible_video_ids(card)
    if not isinstance(ledger, dict):
        raise RuntimeError('Invalid video ledger')
    if not ids:
        return []
    mapping = ledger.get(code)
    if not isinstance(mapping, dict):
        raise RuntimeError('Video download ledger missing')
    reverse = {}
    for name, fid in mapping.items():
        if not isinstance(name, str) or not re.fullmatch(
                re.escape(code) + r'(?:-\d{2,})?\.mp4', name):
            raise RuntimeError('Invalid or foreign video filename')
        if not isinstance(fid, str) or not fid.strip() or fid in reverse:
            raise RuntimeError('Ambiguous ledger video identity')
        reverse[fid] = name
    if any(fid not in reverse for fid in ids):
        raise RuntimeError('CRM video download not confirmed')
    return [reverse[fid] for fid in ids]


def video_paths(card, root='/home/Carix'):
    root = Path(root)
    journal = root / '.video_sinhron.json'
    raw = journal.read_bytes()
    names = select_video_names(card, json.loads(raw))
    folder = root / 'video'
    for name in names:
        path = folder / name
        if path.is_symlink() or path.resolve().parent != folder.resolve():
            raise RuntimeError('Video path escapes media folder')
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError('Video file unavailable')
    if journal.read_bytes() != raw:
        raise RuntimeError('Video ledger changed during rendering')
    return names


class VideoHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.videos = []
        self.current = None
        self.invalid = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'video':
            if self.current is not None:
                self.invalid = True
            self.current = {'sources': [], 'links': []}
            if attrs.get('src'):
                self.current['sources'].append(attrs['src'])
        elif tag == 'source' and self.current is not None:
            if attrs.get('type') not in (None, 'video/mp4'):
                self.invalid = True
            self.current['sources'].append(attrs.get('src', ''))
        elif tag == 'a' and self.current is not None:
            self.current['links'].append(attrs.get('href', ''))

    def handle_endtag(self, tag):
        if tag == 'video':
            if self.current is None:
                self.invalid = True
            else:
                self.videos.append(self.current)
                self.current = None


def verify_video_structure(html, card, expected_paths):
    code = _code(card)
    ids = visible_video_ids(card)
    if not isinstance(expected_paths, list) or len(expected_paths) != len(ids):
        raise RuntimeError('CRM video count differs from expected paths')
    if any(not isinstance(p, str) or not re.fullmatch(
            re.escape(code) + r'(?:-\d{2,})?\.mp4', p) for p in expected_paths):
        raise RuntimeError('Unsupported or foreign video path')
    if len(set(expected_paths)) != len(expected_paths):
        raise RuntimeError('Duplicate expected video path')
    doc = VideoHTML()
    doc.feed(html)
    doc.close()
    if doc.invalid or doc.current is not None:
        raise RuntimeError('Malformed video player')
    actual = []
    for player in doc.videos:
        if len(player['sources']) != 1:
            raise RuntimeError('Missing or ambiguous video source')
        source = player['sources'][0]
        if any(link != source for link in player['links']):
            raise RuntimeError('Video fallback link differs from player')
        actual.append(source)
    if actual != expected_paths:
        raise RuntimeError('Video players differ from CRM order')
    return {'video_count': len(actual), 'structure_verified': True,
            'content_identity_verified': False, 'playback_verified': False,
            'full_consistency_accepted': False}
