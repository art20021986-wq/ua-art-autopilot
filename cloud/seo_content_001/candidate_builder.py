"""Build the SEO-CONTENT-001 candidate from the exact installed sources (after CARD-LANG-001).

The page texts module is replaced (two topic pages and the custom-order page additions as data); the landing
generator and the metadata step get small edits.
"""
import hashlib
from pathlib import Path

import edit_landings
import edit_metadata
from release_constants import REPLACED_FILES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_seo_order_models.py': '43bb7499d70bdd8b18736ce2972a5fed007af9d73a048a9cfa90dae94e993903',
    'ua_seo_landings.py': '24549ecea765c635a765f87d10260e240f43c0a8a5bdf2e980ef8d87f99a980c',
    'ua_seo_metadata.py': 'daffce7aed6e2ad2fd2f5485d57b932ce95c40af6ff6370b92095c22919d825c',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# Installed modules the candidate imports or relies on unchanged.
DEPENDENCY_SHA256 = {
    'ua_seo_index.py': '757adb13af4af7b397934fa48cb619df5a46e31a4de331db6bac25df1dde88a7',
    'ua_seo_catalog.py': '5b66b369c97f914b302e9bc564dd139c617927fb64489d618d982fd0b5c8c0aa',
    'ua_seo_sitemap.py': '3dac54b6527d03c0b2e17bcba24f3d2e3d3dca757aa897ceca874a08a84c0cee',
    'ua_seo_quick_form.py': 'af9c53421409eca7b20f67471a8b14c192979ad6602c2587f6c49ce33cb54c75',
    'ua_seo_schema.py': '050c90e5717dfcbed228fb486764423f1e578329d4ba8909b44e3b9ebfa50b62',
    'ua_google_tag.py': 'f5f0a30489d20d7f7d973c27bd31e583e9827fb5a6d1e24a97fb35d1e6a3b6d4',
    'ua_indexnow.py': '0faa75073d7fabc2bacf68e53cf5f4811857c206fb1ea4f05b9ff0ea3210407f',
    'ua_google_sitemap.py': '0b99b8ee4d36a0790ef065d8fdf6f75f955242af4cd7a93b5d22de3d95f2d38a',
    'ua_card_lang.py': '7c393002aeff759332ef1c7921bf40c14afce3805d3fef1ebf66ba12df7731df',
}
EDITS = {'ua_seo_landings.py': edit_landings, 'ua_seo_metadata.py': edit_metadata}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {target: (HERE / name).read_bytes() for target, name in REPLACED_FILES.items()}
    result.update({name: module.build(source[name]) for name, module in EDITS.items()})
    return result
