"""Build the QUICK-LEAD-002 candidate from the exact installed sources (after QUICK-LEAD-001, PODBOR-MODEL-001, GA4-TAG-001)."""
import hashlib
from pathlib import Path

import edit_order
import quick_assets
from release_constants import ASSETS, REPLACED_FILES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_order/quick.py': '69c88550517ff8a6a7e809b7141cabad8dfac1e4e545a00bcfbe63989167a978',
    'ua_seo_quick_form.py': 'c1c918410bd302efcd8f618e000de61afdb808321248d193b70ab060a6d47284',
    'video/order/quick-lead.js': 'f10803afd275e58d7403256e007809cb0fd91f17da61866efc2cbd8c2f647e2a',
    'video/order/quick-lead.css': '65d07fc3213330bbb6f8352dfe609d8e5311767da4d69f8379a8f500c8a19641',
    'video/podbor.html': '9576701c7eb9255c370698572172d52836ad89764713b57268357c419811af7b',
    'video/order/order.js': 'b650398b1d381c31d2cef9a83f6702ed7082da03b354c8ba12e8a851660ce893',
    'video/order/order-strings.json': 'f9a997d3a31b09a131973777bf005780724bc76d141687c1d0b7b21ea5a7a80d',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# Installed modules the candidate imports or serves with unchanged.
DEPENDENCY_SHA256 = {
    'ua_seo_landings.py': '77d6ace0241f22eecaed9eb51a7f8a7fa5ce27803afa4413c1ac5f0a40877071',
    'ua_seo_order_models.py': '755eab6240ff671911f82afdef20e4e0880ba8f3391bc7956b05152f9500a9d7',
    'ua_seo_schema.py': '050c90e5717dfcbed228fb486764423f1e578329d4ba8909b44e3b9ebfa50b62',
    'ua_indexnow.py': '0faa75073d7fabc2bacf68e53cf5f4811857c206fb1ea4f05b9ff0ea3210407f',
    'ua_seo_index.py': '757adb13af4af7b397934fa48cb619df5a46e31a4de331db6bac25df1dde88a7',
    'ua_google_sitemap.py': '0b99b8ee4d36a0790ef065d8fdf6f75f955242af4cd7a93b5d22de3d95f2d38a',
    'ua_google_tag.py': 'f5f0a30489d20d7f7d973c27bd31e583e9827fb5a6d1e24a97fb35d1e6a3b6d4',
    'ua_order/contract.py': '28eb9060de326e548a29bf7ffea23dda6d19226cba8f739040caa7ae64e8269a',
    'ua_order/crm.py': '2c5892de68bb71eeb9852228d4fdfaa253e6e6cf0ed148e9f344d5414033dd9b',
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
    result = {target: (HERE / name).read_bytes() for target, name in REPLACED_FILES.items()}
    result.update({name: getattr(quick_assets, attribute).encode('utf-8') for name, attribute in ASSETS.items()})
    result.update({name: edit_order.build(name, source[name]) for name in edit_order.EDITS})
    return result
