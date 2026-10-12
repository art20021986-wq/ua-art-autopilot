"""Build the two-file candidate from the exact installed source."""
import hashlib
from pathlib import Path

import build_public_sync
from release_constants import NEW_MODULE

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {'ua_crm_public_sync.py': build_public_sync.EXPECTED_SHA256}
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {'ua_crm_public_sync.py': build_public_sync.build(source['ua_crm_public_sync.py']),
            NEW_MODULE: (HERE / NEW_MODULE).read_bytes()}
