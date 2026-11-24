"""Build the client bot candidate (STAFF-FULL-ACCESS-001, step 2, owner «Да» 2026-11-24): everyone with full rights
(ua_full_access, installed by CRM-FULL-ACCESS-INSTALL-20261124-R2: «Владелец» + «Управляющий администратор») gets the
client bot's owner screens, commands, analytics and notifications.

Bound by exact context, not by whole-file hashes: every original fragment must occur exactly once and an applied
fragment is refused (edits.apply). The preview records each file's before/after hash and the install applies only
that previewed plan. ua_full_access.py must be the installed one.
"""
import hashlib

import edit_analitika_bot
import edit_analitika_knopka
import edit_client_ui
import edit_karta_klienta
import edit_lead_bot
import edit_lead_desk
import edit_order_bindings
import edit_order_host
import edit_vitrina
import edits

EDITORS = (edit_lead_bot, edit_client_ui, edit_vitrina, edit_order_bindings, edit_order_host, edit_lead_desk,
           edit_analitika_bot, edit_analitika_knopka, edit_karta_klienta)
SOURCE_FILES = tuple(module.NAME for module in EDITORS)
# Installed by CRM-FULL-ACCESS-INSTALL-20261124-R2 (cloud/staff_crm_owner_001/ua_full_access.py).
DEPENDENCY_SHA256 = {'ua_full_access.py': 'b90f88cacc7193beb0757f0b1236f2daad4b28ac88eb0f20cc3c9b5580b1e781'}


def build(source, dependencies):
    for name, digest in DEPENDENCY_SHA256.items():
        if dependencies.get(name) is None or hashlib.sha256(dependencies[name]).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {module.NAME: edits.apply(source[module.NAME], module.EDITS) for module in EDITORS}
