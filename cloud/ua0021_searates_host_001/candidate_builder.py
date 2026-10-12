"""Build the one-line approved-host candidate from the exact installed source."""
import hashlib

import build_spec

SOURCE_SHA256 = {'ua_additional_spec.py': build_spec.EXPECTED_SHA256}
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {'ua_additional_spec.py': build_spec.build(source['ua_additional_spec.py'])}
