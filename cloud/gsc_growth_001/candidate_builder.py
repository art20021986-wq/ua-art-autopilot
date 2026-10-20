"""Build the GSC growth candidate from the exact installed sources (after AI-SEARCH-001)."""
import hashlib
from pathlib import Path

from release_constants import NEW_MODULES, REPLACED_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_seo_landings.py': '0ae86f24f954536bcd2963036d6ca5880618968f285753a789041e026cb2fd55',
    'ua_seo_index.py': '3550406560ede2d536fce4b6ef4d4f67918d57eae84c1482a4b9104bf8540e61',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# Installed modules the candidate imports unchanged.
DEPENDENCY_SHA256 = {
    'ua_seo_schema.py': '050c90e5717dfcbed228fb486764423f1e578329d4ba8909b44e3b9ebfa50b62',
    'ua_indexnow.py': '0faa75073d7fabc2bacf68e53cf5f4811857c206fb1ea4f05b9ff0ea3210407f',
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in NEW_MODULES + REPLACED_MODULES}
