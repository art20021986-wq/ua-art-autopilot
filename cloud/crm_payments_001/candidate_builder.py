"""Build the CRM-PAYMENTS candidate from the installed sources: cars_ui.py gets one block at the end; ua_order_book.py
gets the 8 delivery stages; five new modules.

cars_ui.py changes with other releases, so it is pinned by the preview plan (before/after hashes), not here; the
edit itself refuses an unexpected file. db.py (get_staff, staff_ids_by_role, connect) is only read and must be the known version.
"""
import hashlib
from pathlib import Path

import edit_cars_ui
import edit_order_book
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_FILES = (edit_cars_ui.NAME, edit_order_book.NAME)
DEPENDENCY_SHA256 = {
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',  # get_staff, staff_ids_by_role, connect
}


def build(source, dependencies):
    for name, digest in DEPENDENCY_SHA256.items():
        if dependencies.get(name) is None or hashlib.sha256(dependencies[name]).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {edit_cars_ui.NAME: edit_cars_ui.build(source[edit_cars_ui.NAME]),
              edit_order_book.NAME: edit_order_book.build(source[edit_order_book.NAME])}
    result.update({name: (HERE / name).read_bytes() for name in NEW_MODULES})
    return result
