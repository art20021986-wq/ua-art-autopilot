"""Build the CARD-CONTACT candidate from the exact installed sources (LEAD-FOLDERS-001).

Card generators: the stage primary action becomes the one «Связаться с менеджером» button (ua_card_contact);
order package: the card enquiry schema (card_lead) and its hand-offs; the shared dialog script learns the card
opener; ua_seo_metadata: a new revision so every card is republished once.
"""
import hashlib
from pathlib import Path

import card_lead_assets
import edit_generators
import edit_metadata
import edit_order

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'stranica.py': '6d5afd1b72c6b53623996b231b4e2d4143ec6850e00cdd1c38beedf209d0794b',
    'master_card.py': 'f9d2d00d805a9171b78c7aa8424c2e26537f46c64d66047550218bb993338156',
    'ua_seo_metadata.py': '9d19ad268f9ef09521ec466b486d49223c49d29f2c658b840cfa9e76afefe488',
    'ua_order/contract.py': '64edc324a9ee3431af348e63474a5ff6242130886480ffa3df5fcf09a62d33b2',
    'ua_order/crm.py': '60f60431c6cf8a5b974abb091a4f747850dc4473c5f70cc4e1d9b685a4baeffb',
    'video/order/quick-lead.js': '1fe607494b5f36e8d28aba2024e5988758dd083309a301a2a8371ccfd627ee1d',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# Installed modules the candidate relies on unchanged.
DEPENDENCY_SHA256 = {
    'ua_order/quick.py': '6848e71a06eb3c97da72e0cdda20e0f77c5b5e87e3300c11e31ed3146857856b',
    'ua_order/catalog.py': 'c0c9751193e8a8542250f0c1f47d525ff60a77b6499bf694e281a16468af4db1',
    'ua_order/web.py': '0ce58b36a3d2d3e12af19775624a15d1c401b36a44652848011b2c2d17c0edab',
    'ua_card_lang.py': '0cf5267afa174c215064725181dae0112258de5152d5cbd0554db91cef619fa4',
    'ua_card_finance.py': 'c5f257f7c7f0e9cf4c23addf7dfd75217cf61ee78562b5156d67328a7bea5455',
}
NEW_FILES = {'ua_card_contact.py': 'ua_card_contact.py', 'ua_order/card_lead.py': 'card_lead.py'}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {name: edit_generators.build(name, source[name]) for name in edit_generators.NAMES}
    result.update({name: edit_order.build(name, source[name]) for name in edit_order.EDITS})
    result[edit_metadata.NAME] = edit_metadata.build(source[edit_metadata.NAME])
    result['video/order/quick-lead.js'] = card_lead_assets.JS.encode('utf-8')
    result.update({target: (HERE / name).read_bytes() for target, name in NEW_FILES.items()})
    return result
