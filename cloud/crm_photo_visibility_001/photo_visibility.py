"""Apply CRM photo visibility to downloader filenames without changing order."""
import json
from pathlib import Path


def visible_names(card, names, root='/home/Carix'):
    """Keep original filenames; never guess an identity from its position."""
    hidden = card.get('hidden_photos') or []
    if isinstance(hidden, str):
        hidden = json.loads(hidden)
    if not isinstance(hidden, list) or any(not isinstance(x, str) or not x for x in hidden):
        raise ValueError('Invalid hidden photo identities')
    names = list(names)
    if not hidden:
        return names
    code = card.get('auto_number')
    ledger = json.loads((Path(root) / '.video_sinhron.json').read_text(encoding='utf-8'))
    mapping = ledger.get('foto:' + str(code)) if isinstance(ledger, dict) else None
    if not isinstance(mapping, dict):
        raise ValueError('Photo identity ledger missing')
    for name in names:
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError('Invalid photo filename')
        identity = mapping.get(name)
        if not isinstance(identity, str) or not identity:
            raise ValueError('Photo identity is not confirmed')
    hidden = set(hidden)
    return [name for name in names if mapping[name] not in hidden]
