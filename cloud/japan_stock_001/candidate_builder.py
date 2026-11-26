"""Build the JAPAN-STOCK-001 (CRM bot) candidate from the exact installed sources.

Exact edits in ua_delivery_status.py, cars_ui.py and konteyner.py (each refuses a file whose anchors are not exactly as
expected) and the new module ua_car_country.py. Hashes: JAPAN-STOCK-PROBE-20261126-R2 (run 45747488941).
"""
import hashlib
from pathlib import Path

import edit_cars_ui
import edit_delivery_status
import edit_konteyner
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
EDITS = (edit_delivery_status, edit_cars_ui, edit_konteyner)
SOURCE_FILES = tuple(edit.NAME for edit in EDITS)
SOURCE_SHA256 = {
    'ua_delivery_status.py': 'c544bc121b7b3b66d45519d5b63ed3687567af7e9d5f7011ae2fb53cc372bdd0',
    'cars_ui.py': '4fba086e17b6f58b11de6e34a656060de9e10a34df17092459bcc145e7ee555f',
    'konteyner.py': 'cb09e8cfac57f05a004f7dae73d57f76c422132a8e0d6a16f28f0a949647760e',
}
# Read-only collaborators the new code relies on; any drift stops the plan.
DEPENDENCY_SHA256 = {
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',           # connect, now, log_action
    'cars_schema.py': 'ad126b8dd5ff2446726f305bfb620809dea37505186e7bd83f0cb6e6d5c34555',  # status_label, STAGES
}


def build(source, dependencies, *, expected=None):
    expected = SOURCE_SHA256 if expected is None else expected
    for name, digest in {**expected, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    candidate = {edit.NAME: edit.build(source[edit.NAME]) for edit in EDITS}
    candidate.update({name: (HERE / name).read_bytes() for name in NEW_MODULES})
    return candidate
