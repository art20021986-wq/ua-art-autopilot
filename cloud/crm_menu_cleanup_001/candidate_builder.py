"""Build the one-file candidate from the exact installed source."""
import hashlib

import build_cars_ui

SOURCE_SHA256 = {'cars_ui.py': build_cars_ui.EXPECTED_SHA256}
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {'cars_ui.py': build_cars_ui.build(source['cars_ui.py'])}
