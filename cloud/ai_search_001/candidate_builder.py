"""Build the AI search candidate from the exact installed sources and the live home page."""
import hashlib
from pathlib import Path

import build_home
import ua_indexnow
from release_constants import HOME, NEW_MODULES, REPLACED_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_seo_landings.py': 'b66dbdb7fa5c1421bec7f4ba917845ae38e8cceb22b0943259bae35187e19129',
    'ua_seo_schema.py': 'a569865c836146f8a42720e36b0431770c2757e7170e250ee7ad42d9d6697557',
    'ua_seo_index.py': 'ba6f6a4e6c2c0dc95a1dab995ff50de98368ed81b432bfe93f9773e6421fb19a',
}
# The home page changes with every catalog publication; it is pinned by the plan instead.
SOURCE_FILES = tuple(SOURCE_SHA256) + (HOME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {name: (HERE / name).read_bytes() for name in NEW_MODULES + REPLACED_MODULES}
    result[ua_indexnow.KEY_FILE] = ua_indexnow.KEY.encode()
    result[HOME] = build_home.build(source[HOME])
    return result
