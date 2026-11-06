"""Build the LEAD-FOLDERS candidate from the exact installed sources (after CARD-CONTACT-INSTALL).

Client bot: the lead desk (leads by folder, «Оформить договор») replaces the CRM bot's site enquiry desk; CRM bot:
«👤 Клиенты» shows orders by folder; the owner's new-enquiry message opens the lead card. ua_site_leads.py (the CRM
bot's old desk entry) is removed: nothing imports it after this release.
"""
import hashlib
from pathlib import Path

import edit_bots

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'cars_ui.py': 'e4576e5b80ddf1435a71f0c1be1c4a78d8a96c27e55da6caa2a928ccdae06934',
    'lead_bot.py': 'e45cec0e4359831928029f30804f3b9c2d629ffa920654250ae8a85de04c05e8',
    'ua_order/bindings.py': '569aeea5bb9bcee08bff79855ca9217aa5db1c574c1c10ab3d2703a31c838490',
    'ua_lead_desk.py': '824861e2cce2414be56a41cc4a9876f504b9e8f793e4152317945b4bade131b3',
    'ua_lead_desk_view.py': '264619d44214ffbfb1de1bc8a57a2b6636d464c63b139be6acd15dc5b877fa1c',
    'ua_lead_desk_store.py': '16ec680c27ec10486a78018635c1c45ec2fe3cc55406549419aa1eca2e67ac85',
    'ua_site_leads.py': '072c7f92d28db0543b100d3a7776c668dcc4a78216d873dab7ef19d4be3151cc',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# Installed modules the candidate relies on unchanged (ua_order/crm.py as CARD-CONTACT-INSTALL leaves it).
DEPENDENCY_SHA256 = {
    'ua_lead_calendar.py': '903775eddd75aa86b11a3e5242600f205d1b9d7e2bcdfbecf851a0da9035de69',
    'visits.py': '69de9e99f0e5c2cd07166f122e72d91275931d3746a18298cca6fd5b4fad9468',
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',
    'ua_order/crm.py': '42079bb516e6501f4b71814779c7a3bdb8dcc628f38a70c859afd03c8f906308',
}
REPLACED = ('ua_lead_desk.py', 'ua_lead_desk_view.py', 'ua_lead_desk_store.py')
NEW = ('ua_lead_folders.py', 'ua_lead_sources.py', 'ua_order_book.py', 'ua_contract_files.py', 'ua_crm_orders.py',
       'ua_crm_orders_view.py')
REMOVED = ('ua_site_leads.py',)


def build(source, dependencies):
    """{installed path: new bytes, or None to remove the file}."""
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {name: edit_bots.build(name, source[name]) for name in edit_bots.EDITS}
    result.update({name: (HERE / name).read_bytes() for name in REPLACED + NEW})
    result.update({name: None for name in REMOVED})
    return result
