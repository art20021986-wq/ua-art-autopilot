"""Build the JAPAN-STOCK-001 step 2 (site) candidate from the installed sources.

Exact text edits (each refuses a file whose anchors are not exactly as expected) in the page builders, the catalog
guard, counters and stage sync and the catalog golden page, plus the new module ua_country_site.py.
The preview plan pins every before/after hash; the install refuses any drift from it. The home page titles
(edit_home) are a text edit made by the installer under the publication locks: the page counters rewrite that file.
"""
import hashlib
from pathlib import Path

import edit_card_stage
import edit_catalog_guard
import edit_golden
import edit_site_counters
import edit_stage_sync
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
SINGLE = (edit_catalog_guard, edit_site_counters, edit_stage_sync, edit_golden)
SOURCE_FILES = ('stranica.py', 'master_card.py') + tuple(edit.NAME for edit in SINGLE)
# Installed by JAPAN-BOT-INSTALL-20261126 (verify run 45749721491); the new texts rely on them.
DEPENDENCY_SHA256 = {
    'ua_car_country.py': '4658f6ba820d81cdf0f9c486680aa660c39eeafb0cc32f53894631d9d531ec06',
    'ua_delivery_status.py': 'eb73c6e82f96fca88e5ee2ac2e206383aa7aeaf4d345ba44a8dcd0859d222692',
}


def build(source, dependencies):
    for name, digest in DEPENDENCY_SHA256.items():
        value = dependencies.get(name)
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    candidate = {name: edit_card_stage.build(name, source[name]) for name in ('stranica.py', 'master_card.py')}
    candidate.update({edit.NAME: edit.build(source[edit.NAME]) for edit in SINGLE})
    candidate.update({name: (HERE / name).read_bytes() for name in NEW_MODULES})
    return candidate
