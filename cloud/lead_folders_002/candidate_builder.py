"""Build the LEAD-DESK-FIX candidate from the exact installed sources (after LEAD-FOLDERS-INSTALL-20261106).

vitrina.py (the client bot's screens) shows the owner «📥 Лиды» instead of the old flat «📁 Авто под заказ» and passes
a message the lead desk waits for; ua_lead_desk drops its /start summary (vitrina answers /start) and offers
BUTTON, CALLBACK and pending(); ua_lead_desk_view drops the summary screen.
"""
import hashlib
from pathlib import Path

import edit_vitrina

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'vitrina.py': 'bbd990b532e8a05126bedf82775d14393d8b884bb80c7b30496b9937125bbd76',
    'ua_lead_desk.py': '76fd10d11202e393bcf17b0bbce433bb99bcbb2121dc23faddd88c620e08743c',
    'ua_lead_desk_view.py': 'a570b098e74468ea8a6d0129a49a37420e168f9fd0e77431f0f028bb2558047d',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# Installed modules the candidate relies on unchanged.
DEPENDENCY_SHA256 = {
    'ua_lead_desk_store.py': '943a9cac09f51155419a9e9bc040e6c1cee4751f5eb648b108fb0d098bc89026',
    'ua_lead_sources.py': 'c56398e8ba140dfd88ea9341e96b523deb3db66aa8bef1aa97d05fd21e4a22fa',
    'ua_lead_folders.py': '4fa1146df200efbc7ca3d2cb59422168d88eceaf2284f1c6f2981b0a4750dc5b',
    'ua_order_book.py': '06a3b4a5f2e20eedbf0254a1dfc5c7f59f03f4915fc83ac0dd98f562707f18cb',
    'ua_contract_files.py': '57f1d6b0681b6134ce17cc1455fcebf37fec41778f133766f0847e359e37060a',
    'lead_bot.py': '4f5441f70411c292a2be3b14db8a1c030f8d82328759ee194d3ed6be3c084b73',
}
REPLACED = ('ua_lead_desk.py', 'ua_lead_desk_view.py')


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {edit_vitrina.NAME: edit_vitrina.build(source[edit_vitrina.NAME])}
    result.update({name: (HERE / name).read_bytes() for name in REPLACED})
    return result
