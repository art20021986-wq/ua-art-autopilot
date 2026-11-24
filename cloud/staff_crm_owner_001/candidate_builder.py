"""Build the BOT CRM candidate (STAFF-FULL-ACCESS-001, owner 2026-11-24): the managing admin gets the owner's rights.

New ua_full_access.py (who has full rights: «Владелец» and «Управляющий администратор»); exact fragment edits make
every owner-only check, owner notification and owner money view of BOT CRM ask it. The roles stay as they are.

The files are shared with other sessions and change often, so the build is bound by exact context, not by whole-file
hashes: every original fragment must occur exactly once and an applied fragment is refused (edits.apply). The
preview records each file's before/after hash and the install applies only that previewed plan.
"""
from pathlib import Path

import edit_ai
import edit_bezopasnost
import edit_cars_schema
import edit_cars_ui
import edit_home_photo
import edit_home_stage
import edit_kr_prices
import edit_pay_bot
import edit_svyaz
import edit_team_bot
import edit_telegram_key
import edits

HERE = Path(__file__).resolve().parent
EDITORS = (edit_team_bot, edit_cars_ui, edit_cars_schema, edit_ai, edit_home_photo, edit_home_stage, edit_kr_prices,
           edit_telegram_key, edit_pay_bot, edit_bezopasnost, edit_svyaz)
SOURCE_FILES = tuple(module.NAME for module in EDITORS)
DEPENDENCY_SHA256 = {}
NEW = ('ua_full_access.py',)


def build(source, dependencies):
    result = {module.NAME: edits.apply(source[module.NAME], module.EDITS) for module in EDITORS}
    result.update({name: (HERE / name).read_bytes() for name in NEW})
    return result
