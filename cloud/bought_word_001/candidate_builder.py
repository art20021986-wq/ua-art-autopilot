"""Build the BOUGHT-WORD-001 candidate from the installed sources: one exact edit each in catalog_design_guard.py and
ua_country_site.py (the catalog status of stage 1). The home title (edit_home) is a text edit made by the installer under
the publication locks. Inputs are the files installed by JAPAN-SITE-INSTALL-20261126 (run 45762368794).
"""
import hashlib

import edit_labels

SOURCE_SHA256 = {
    'catalog_design_guard.py': 'd511d54faffa5036f341b90016192745d4abf7c5547c34d23665b4043a31b2d1',
    'ua_country_site.py': 'e6975fbe4a02de17ff600320e1b1feb8a7d9249bdb59b0c0d108be68479fe457',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {
    'catalog_design_golden.html': 'e91566bb7ecfff708473fb17d4958742d89bbff77eff94db6b8435c814d0ff6a',
    'ua_stage_catalog_sync.py': '75ee56376927604198d60970e03a78dc1fc318c74bb718580f9c79657b80fa64',
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: edit_labels.build(name, source[name]) for name in SOURCE_FILES}
