"""Build the CLIENT-TERMS candidate from the exact installed vitrina.py (after LEAD-DESK-FIX-INSTALL-20261107)."""
import hashlib

import edit_vitrina

SOURCE_SHA256 = {'vitrina.py': '935ce5f0e3aab08c7e842e330f2561115c84530c6e61e3773c64c46212481f02'}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name, digest in SOURCE_SHA256.items():
        value = source.get(name)
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {edit_vitrina.NAME: edit_vitrina.build(source[edit_vitrina.NAME])}
