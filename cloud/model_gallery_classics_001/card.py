"""One gallery card of the order page (MODEL-GALLERY-CLASSICS, owner 2026-10-30).

The live video/order/model-gallery.json gets a new entry for the Japan rare-car card (it had one catalogue photo,
no gallery): 8 photos of different left-hand-drive cars of 2000–2003. The card name comes from the catalogue, so
the generation line is empty. Every other entry stays exactly as it is; the data version follows the page asset
version.
"""
import json

from asset_version import VERSION

DATA = 'video/order/model-gallery.json'
KEY = 'classics-1980-1990'


def dump(value):
    # The form of the installed file (MODEL-GALLERY-001 make_assets.py).
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1) + '\n').encode('utf-8')


def build(source, entry):
    value = json.loads(source)
    models = value.get('models', {})
    if KEY in models or value.get('version') == VERSION:
        raise ValueError('GALLERY_ENTRY_STATE:' + KEY)
    return dump({**value, 'version': VERSION, 'models': {**models, KEY: entry}})
