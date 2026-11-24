"""Build the HOME-PHOTO-FIX candidate: ua_home_photo_site.py is replaced; the installed one must be the known version
(HOME-PHOTO-INSTALL-20261028-R2)."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_home_photo_site.py': '02f8ac0d083a914b133354fca29346c9794c09ec8c5ff66f04982e69fccbd4c9',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {}
PACKAGED = {'ua_home_photo_site.py': 'ua_home_photo_site.py'}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / packaged).read_bytes() for name, packaged in PACKAGED.items()}
