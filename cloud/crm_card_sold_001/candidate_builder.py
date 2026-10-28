"""Build the two-file candidate from exact installed sources."""
from pathlib import Path

import build_cars_ui
from release_constants import NEW_MODULE

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {'cars_ui.py': build_cars_ui.EXPECTED_SHA256}
# Read-only collaborators the new handler relies on; any drift stops the plan.
DEPENDENCY_SHA256 = {
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',
    'publikaciya.py': '1771351a32f33f02a8bd6dd51f58f87525e1f8243f0dd3441f4c3e52dfa75ef5',
    'publish_transaction_guard.py': '4b36b2f06f2b3582705b341e67f8361818890922133f3cf2e2a3ace935ec9b95',
}


def build(source, dependencies):
    import hashlib
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {'cars_ui.py': build_cars_ui.build(source['cars_ui.py']),
            NEW_MODULE: (HERE / NEW_MODULE).read_bytes()}
