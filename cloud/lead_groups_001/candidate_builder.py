"""Build the LEAD-GROUPS candidate from the exact installed sources (after LEAD-FOLDERS-INSTALL-20261106 and
LEAD-DESK-FIX-INSTALL-20261107).

«📥 Лиды» (client bot) and «👤 Клиенты» (CRM bot) open with two groups: «🧾 Индивидуальный заказ» (the folders as
before) and «🔨 Аукционы онлайн» (auction access requests by country). ua_lead_folders adds the groups and the
auction folder; the desk and orders views and routers add the group screen. Existing leads and orders stay put.
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Installed versions this package was written against; any other version stops the build.
SOURCE_SHA256 = {
    'ua_lead_folders.py': '4fa1146df200efbc7ca3d2cb59422168d88eceaf2284f1c6f2981b0a4750dc5b',
    'ua_lead_desk.py': '68d82b14eb6022fab179886ac91c631d160c04b263b9db4219fce9344d93af11',
    'ua_lead_desk_view.py': '81fb0c2547d00234b5921d7e087f43da7ad1769a192306635ae7c6147a2e28aa',
    'ua_crm_orders.py': 'ecfa6a1ecf5d632eeaee27b97a80afc9833e8545d0b76a58046214634c75a389',
    'ua_crm_orders_view.py': '3cf1e08853ac3543dcc363ef1a66962c96ddc69a45ce1fd2685387401a50f013',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# Installed modules the candidate relies on unchanged.
DEPENDENCY_SHA256 = {
    'ua_lead_desk_store.py': '943a9cac09f51155419a9e9bc040e6c1cee4751f5eb648b108fb0d098bc89026',
    'ua_lead_sources.py': 'c56398e8ba140dfd88ea9341e96b523deb3db66aa8bef1aa97d05fd21e4a22fa',
    'ua_order_book.py': '06a3b4a5f2e20eedbf0254a1dfc5c7f59f03f4915fc83ac0dd98f562707f18cb',
    'ua_contract_files.py': '57f1d6b0681b6134ce17cc1455fcebf37fec41778f133766f0847e359e37060a',
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in SOURCE_FILES}
