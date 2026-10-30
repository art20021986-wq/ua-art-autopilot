"""Build the CARD-LANG-001 candidate from the exact installed sources (after ADS-READY-001).

Two new modules (the language versions and their CRM bot job) and four small edits: the card canonical in
ua_seo_metadata, the sitemap entries in ua_seo_sitemap, the job in cars_ui.py, the site language script.
"""
import hashlib
from pathlib import Path

import edit_cars_ui
import edit_languages
import edit_metadata
import edit_sitemap
from release_constants import NEW_FILES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_seo_metadata.py': 'c313a17fc364c30b71c331ebb86734d476b54721033d347dca3847acf88090fa',
    'ua_seo_sitemap.py': '0a7e44f8b52d0f27355ab1475aeb62180baee2ced9c35412cb3ef4689eb36a09',
    'cars_ui.py': 'dfbd84d3c38ba61b11faba8e0eafe6d18f5056ae77fa1b83c8dad089fd8f4332',
    'video/ua-site-languages.js': '3feb887740d5f01017de69d9b541f0442249f1cfb5b26db4d33aa6e749708387',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# Installed modules the candidate imports or relies on unchanged.
DEPENDENCY_SHA256 = {
    'ua_seo_index.py': '757adb13af4af7b397934fa48cb619df5a46e31a4de331db6bac25df1dde88a7',
    'ua_seo_catalog.py': '5b66b369c97f914b302e9bc564dd139c617927fb64489d618d982fd0b5c8c0aa',
    'ua_seo_landings.py': '24549ecea765c635a765f87d10260e240f43c0a8a5bdf2e980ef8d87f99a980c',
    'ua_seo_order_models.py': '43bb7499d70bdd8b18736ce2972a5fed007af9d73a048a9cfa90dae94e993903',
    'ua_seo_quick_form.py': 'af9c53421409eca7b20f67471a8b14c192979ad6602c2587f6c49ce33cb54c75',
    'ua_seo_schema.py': '050c90e5717dfcbed228fb486764423f1e578329d4ba8909b44e3b9ebfa50b62',
    'ua_google_tag.py': 'f5f0a30489d20d7f7d973c27bd31e583e9827fb5a6d1e24a97fb35d1e6a3b6d4',
    'ua_indexnow.py': '0faa75073d7fabc2bacf68e53cf5f4811857c206fb1ea4f05b9ff0ea3210407f',
    'ua_google_sitemap.py': '0b99b8ee4d36a0790ef065d8fdf6f75f955242af4cd7a93b5d22de3d95f2d38a',
    'publikaciya.py': '1771351a32f33f02a8bd6dd51f58f87525e1f8243f0dd3441f4c3e52dfa75ef5',
}
EDITS = {'ua_seo_metadata.py': edit_metadata, 'ua_seo_sitemap.py': edit_sitemap, 'cars_ui.py': edit_cars_ui,
         'video/ua-site-languages.js': edit_languages}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {target: (HERE / name).read_bytes() for target, name in NEW_FILES.items()}
    result.update({name: module.build(source[name]) for name, module in EDITS.items()})
    return result
