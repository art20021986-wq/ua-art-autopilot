"""Resolve public gallery from CRM order and the downloader's file-id ledger.

No writes, downloads, deletion, ordinal guessing, or directory-based fallback.
"""
import json
import re
from pathlib import Path
from public_media import visible_photo_ids, _list


def select_names(card, ledger):
    code = card.get('auto_number', '')
    if not re.fullmatch(r'UA-\d{4,}', code):
        raise RuntimeError('Invalid car code')
    mapping = ledger.get('foto:' + code)
    ids = visible_photo_ids(card)
    if mapping is None and not ids:
        return []
    if not isinstance(mapping, dict):
        raise RuntimeError('Photo download ledger missing')
    reverse = {}
    for name, fid in mapping.items():
        if not isinstance(name, str) or not re.fullmatch(r'\d+\.jpg', name):
            raise RuntimeError('Invalid ledger photo filename')
        if not isinstance(fid, str) or not fid or fid in reverse:
            raise RuntimeError('Ambiguous ledger photo identity')
        reverse[fid] = name
    if any(fid not in reverse for fid in ids):
        raise RuntimeError('CRM photo download not confirmed')
    names = [reverse[fid] for fid in ids]
    cover = card.get('cover_photo')
    if cover:
        if cover not in mapping:
            raise RuntimeError('CRM cover is not in download ledger')
        if cover in names:
            names = [cover] + [x for x in names if x != cover]
        elif mapping[cover] not in set(_list(card.get('hidden_photos'))):
            raise RuntimeError('CRM cover is not a current photo')
        # A deliberately hidden cover must not be exposed. Use first visible.
    return names


def gallery_paths(card, root='/home/Carix'):
    root = Path(root)
    journal = root / '.video_sinhron.json'
    raw = journal.read_bytes()
    names = select_names(card, json.loads(raw))
    folder = root / 'video' / 'foto' / card['auto_number']
    for name in names:
        path = folder / name
        if path.is_symlink() or path.resolve().parent != folder.resolve():
            raise RuntimeError('Photo path escapes car folder')
        with path.open('rb') as f:
            if f.read(2) != b'\xff\xd8' or path.stat().st_size <= 1000:
                raise RuntimeError('Photo missing or invalid')
    if journal.read_bytes() != raw:
        raise RuntimeError('Photo ledger changed during rendering')
    return ['foto/' + card['auto_number'] + '/' + name for name in names]
