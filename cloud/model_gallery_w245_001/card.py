"""One gallery card of the order page (MODEL-GALLERY-W245, owner 2026-10-30).

In the live video/order/model-gallery.json only the Mercedes-Benz B-Class entry (the Japan card) is replaced:
generation line and photos of the W245 of 2010–2011. Every other entry stays exactly as it is; the data version
follows the page asset version.
"""
import json

from asset_version import VERSION

DATA = 'video/order/model-gallery.json'
KEY = 'mercedes-benz-b-class'


def dump(value):
    # The form of the installed file (MODEL-GALLERY-001 make_assets.py).
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1) + '\n').encode('utf-8')


def build(source, entry):
    value = json.loads(source)
    models = value.get('models', {})
    if KEY not in models or models[KEY] == entry or value.get('version') == VERSION:
        raise ValueError('GALLERY_ENTRY_STATE:' + KEY)
    return dump({**value, 'version': VERSION, 'models': {**models, KEY: entry}})
