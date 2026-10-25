"""Build the SEO landings candidate from the exact installed sources (after SEO-MODELS-001)."""
import hashlib
from pathlib import Path

from release_constants import NEW_MODULES, REPLACED_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_seo_landings.py': '0eaf3b2e3a3ab8148e026b5b4b16a818aca63ad5dd56fb10da54c7721a94ae4a',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# Installed modules the candidate imports unchanged.
DEPENDENCY_SHA256 = {
    'ua_seo_order_models.py': '755eab6240ff671911f82afdef20e4e0880ba8f3391bc7956b05152f9500a9d7',
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
