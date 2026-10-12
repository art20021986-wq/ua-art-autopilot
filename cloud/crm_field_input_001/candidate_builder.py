"""Build the one-file candidate from the exact installed source."""
import hashlib

import build_cars_ui

SOURCE_SHA256 = {'cars_ui.py': build_cars_ui.EXPECTED_SHA256}
# Read-only collaborator whose pending-input key (cont_wait) the helper clears; drift stops the plan.
DEPENDENCY_SHA256 = {
    'konteyner.py': 'cb09e8cfac57f05a004f7dae73d57f76c422132a8e0d6a16f28f0a949647760e',
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {'cars_ui.py': build_cars_ui.build(source['cars_ui.py'])}
