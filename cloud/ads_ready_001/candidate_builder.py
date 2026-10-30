"""Build the ADS-READY-001 candidate: ad source in every site enquiry, privacy policy page, model texts.

Server modules and form assets are pinned to their installed hashes (after QUICK-LEAD-002). The three
order-page files are read live and pinned by the preview plan: a parallel gallery release may change
them, and the edits here do not depend on its versions.
"""
import hashlib
import importlib
from pathlib import Path

import edit_intake
import edit_landings
import edit_order
import privacy_page
from release_constants import ASSETS, REPLACED_FILES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_order/contract.py': '28eb9060de326e548a29bf7ffea23dda6d19226cba8f739040caa7ae64e8269a',
    'ua_order/crm.py': '2c5892de68bb71eeb9852228d4fdfaa253e6e6cf0ed148e9f344d5414033dd9b',
    'ua_seo_landings.py': '77d6ace0241f22eecaed9eb51a7f8a7fa5ce27803afa4413c1ac5f0a40877071',
    'ua_seo_order_models.py': '755eab6240ff671911f82afdef20e4e0880ba8f3391bc7956b05152f9500a9d7',
    'ua_seo_quick_form.py': '79931a94f9a72d3af43c8e5858d2a1eb981ae518f4fcd95b593097f8f55690b6',
    'video/order/quick-lead.js': 'ced73fc6d1b9e11ac31cac488614a7e3cd4171f9761fcceb9f13cc8cf7314f74',
    'video/order/quick-lead.css': '301c3ab4e38d8086b25f9105e041d3fa877312c0e60d72202a4c8aa9de8aaa45',
}
PAGE_FILES = tuple(edit_order.EDITS)
SOURCE_FILES = tuple(SOURCE_SHA256) + PAGE_FILES
# Installed modules the candidate imports or serves with unchanged.
DEPENDENCY_SHA256 = {
    'ua_seo_schema.py': '050c90e5717dfcbed228fb486764423f1e578329d4ba8909b44e3b9ebfa50b62',
    'ua_indexnow.py': '0faa75073d7fabc2bacf68e53cf5f4811857c206fb1ea4f05b9ff0ea3210407f',
    'ua_seo_index.py': '757adb13af4af7b397934fa48cb619df5a46e31a4de331db6bac25df1dde88a7',
    'ua_google_sitemap.py': '0b99b8ee4d36a0790ef065d8fdf6f75f955242af4cd7a93b5d22de3d95f2d38a',
    'ua_google_tag.py': 'f5f0a30489d20d7f7d973c27bd31e583e9827fb5a6d1e24a97fb35d1e6a3b6d4',
    'ua_order/quick.py': '6848e71a06eb3c97da72e0cdda20e0f77c5b5e87e3300c11e31ed3146857856b',
    'ua_order/web.py': '0ce58b36a3d2d3e12af19775624a15d1c401b36a44652848011b2c2d17c0edab',
    'ua_order/service.py': 'f43edb3a72657b70ceecea7a35e70b917e5b804c6d54a2aa2ef6d20a5c5df12a',
    'ua_order/repository.py': '6b8d3e76b8603c1813d75ee22a9af5da2a8da61dd5662dddfb4c06f6b9237b6e',
    'ua_order/preferences.py': 'f06fbf7356d6a8f286c283b63155f6ddbd16461af99109fd088df16e2b298ef9',
}
PRIVACY = 'video/privacy.html'


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {target: (HERE / name).read_bytes() for target, name in REPLACED_FILES.items()}
    result.update({name: getattr(importlib.import_module(module), attribute).encode('utf-8')
                   for name, (module, attribute) in ASSETS.items()})
    result[PRIVACY] = privacy_page.html().encode('utf-8')
    result.update({name: edit_intake.build(name, source[name]) for name in edit_intake.EDITS})
    result.update({name: edit_landings.build(name, source[name]) for name in edit_landings.EDITS})
    result.update({name: edit_order.build(name, source[name]) for name in edit_order.EDITS})
    return result
