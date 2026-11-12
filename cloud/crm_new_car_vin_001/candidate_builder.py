"""Build the NEW-CAR-VIN candidate from the installed sources: cars_ui.py gets one line and one block; one new module.

cars_ui.py changes with other releases, so it is pinned by the preview plan (before/after hashes), not here; the
edit itself refuses an unexpected file. db.py (get_staff) and photo_card.py (extract, create_card) are only read
and must be the known versions.
"""
import hashlib
from pathlib import Path

import edit_cars_ui
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_FILES = (edit_cars_ui.NAME,)
DEPENDENCY_SHA256 = {
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',  # get_staff
    'photo_card.py': '9e0b629680e25e125e69280f1d3f08d042319714567743ac55d12715f5b5a002',  # extract, create_card
}


def build(source, dependencies):
    for name, digest in DEPENDENCY_SHA256.items():
        if dependencies.get(name) is None or hashlib.sha256(dependencies[name]).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {edit_cars_ui.NAME: edit_cars_ui.build(source[edit_cars_ui.NAME])}
    result.update({name: (HERE / name).read_bytes() for name in NEW_MODULES})
    return result
