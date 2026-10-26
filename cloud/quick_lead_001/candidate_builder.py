"""Build the quick lead candidate from the exact installed sources (after SEO-LANDINGS-002 R3 and GA4-TAG-001)."""
import hashlib
from pathlib import Path

import edit_intake
import quick_assets
from release_constants import ASSETS, NEW_FILES, REPLACED_FILES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_seo_landings.py': 'b0c5d5ee6e26833c732aedf715073787c8675e8b831284e3ef1d25e18f3d10a7',
    'ua_order/contract.py': '717bd987500aebc3ff187635078fabe24bdc6446aac6a7d632c632933dcc201b',
    'ua_order/crm.py': 'f3d04a0814ab23aebd228e83bd44cf5c96eba8a1f8c4775d7d6c7744be074566',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# Installed modules the candidate imports unchanged.
DEPENDENCY_SHA256 = {
    'ua_seo_order_models.py': '755eab6240ff671911f82afdef20e4e0880ba8f3391bc7956b05152f9500a9d7',
    'ua_seo_schema.py': '050c90e5717dfcbed228fb486764423f1e578329d4ba8909b44e3b9ebfa50b62',
    'ua_indexnow.py': '0faa75073d7fabc2bacf68e53cf5f4811857c206fb1ea4f05b9ff0ea3210407f',
    'ua_seo_index.py': '757adb13af4af7b397934fa48cb619df5a46e31a4de331db6bac25df1dde88a7',
    'ua_google_sitemap.py': '0b99b8ee4d36a0790ef065d8fdf6f75f955242af4cd7a93b5d22de3d95f2d38a',
    'ua_google_tag.py': 'f5f0a30489d20d7f7d973c27bd31e583e9827fb5a6d1e24a97fb35d1e6a3b6d4',
    'ua_order/web.py': '0ce58b36a3d2d3e12af19775624a15d1c401b36a44652848011b2c2d17c0edab',
    'ua_order/service.py': 'f43edb3a72657b70ceecea7a35e70b917e5b804c6d54a2aa2ef6d20a5c5df12a',
    'ua_order/repository.py': '6b8d3e76b8603c1813d75ee22a9af5da2a8da61dd5662dddfb4c06f6b9237b6e',
    'ua_order/preferences.py': 'f06fbf7356d6a8f286c283b63155f6ddbd16461af99109fd088df16e2b298ef9',
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {target: (HERE / name).read_bytes() for target, name in {**NEW_FILES, **REPLACED_FILES}.items()}
    result.update({name: edit_intake.build(name, source[name]) for name in edit_intake.EDITS})
    result.update({name: getattr(quick_assets, attribute).encode('utf-8') for name, attribute in ASSETS.items()})
    return result
