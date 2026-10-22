"""Build the price page candidate from the exact installed sources (after GSC-GROWTH-001)."""
import hashlib
from pathlib import Path

from release_constants import NEW_MODULES, REPLACED_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_seo_landings.py': 'fa59c25af19134d83b0f9ce6fe08f2e3ff097c2794eddcc70a5c38ae2be876e6',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# Installed modules the candidate imports unchanged.
DEPENDENCY_SHA256 = {
    'ua_seo_schema.py': '050c90e5717dfcbed228fb486764423f1e578329d4ba8909b44e3b9ebfa50b62',
    'ua_indexnow.py': '0faa75073d7fabc2bacf68e53cf5f4811857c206fb1ea4f05b9ff0ea3210407f',
    'ua_seo_index.py': 'd44febac96a86e2e53434f482732be6fdabd70128d6856288805d01d2451b805',
    'ua_google_sitemap.py': '0b99b8ee4d36a0790ef065d8fdf6f75f955242af4cd7a93b5d22de3d95f2d38a',
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in NEW_MODULES + REPLACED_MODULES}
