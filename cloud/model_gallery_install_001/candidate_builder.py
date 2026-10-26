"""Build the model gallery candidate: three live order-page files edited, the new page files and photos added."""
import base64
import importlib

import edit_order
import gallery_assets

# Live files are pinned by the plan.
SOURCE_FILES = tuple(edit_order.EDITS)
DEPENDENCY_SHA256 = {}


def photos():
    """The new photos of every photos_<letter>.py module of this package."""
    found = {}
    for name in gallery_assets.PHOTO_MODULES:
        found.update({path: base64.b64decode(text) for path, text in importlib.import_module(name).FILES.items()})
    return found


def build(source, dependencies):
    result = {name: edit_order.build(name, source[name]) for name in SOURCE_FILES}
    result.update({name: text.encode('utf-8') for name, text in gallery_assets.FILES.items()})
    result.update(photos())
    return result
