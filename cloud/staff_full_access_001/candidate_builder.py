"""Build the STAFF-FULL-ACCESS candidate from the exact installed sources (LEAD-DESK-PROBE-20261112-R2/R3).

New ua_owners.py (who the client bot's owners are); exact fragment edits make every client bot screen, command and
notification use it instead of one owner chat. Any drift of an installed file stops the plan.
"""
import hashlib
from pathlib import Path

import edit_client_ui
import edit_lead_bot
import edit_lead_desk
import edit_order_bindings
import edit_order_host
import edit_vitrina
import edits

HERE = Path(__file__).resolve().parent
EDITORS = (edit_lead_bot, edit_client_ui, edit_vitrina, edit_order_bindings, edit_order_host, edit_lead_desk)
SOURCE_SHA256 = {
    'lead_bot.py': '4f5441f70411c292a2be3b14db8a1c030f8d82328759ee194d3ed6be3c084b73',
    'client_ui.py': '64c813bc1f6e9eaf4276f76ddffc567091bc9b98bc06e06eb085265373ce271c',
    'vitrina.py': 'PENDING_R3',
    'ua_order/bindings.py': 'e07cce08a7b55d16a41a6d1b904c30e928476c012846d9a6eead51dcefc50f9f',
    'ua_order/host.py': '5541bdb455213a13af47e12697afcbb7dd148f88e0a6885812051e377a5b221a',
    'ua_lead_desk.py': '98f2e1f85a7cb8a23d48d5159bf3aee885c5aca946345293a7889892b8dd693e',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# ua_owners reads db.staff_ids_by_role(db.ROLE_OWNER); the smoke check imports it with the live db.py.
DEPENDENCY_SHA256 = {}
NEW = ('ua_owners.py',)


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {module.NAME: edits.apply(source[module.NAME], module.EDITS) for module in EDITORS}
    result.update({name: (HERE / name).read_bytes() for name in NEW})
    return result
