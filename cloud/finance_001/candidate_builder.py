"""Build the FINANCE-001 candidate from the live sources.

Edited live files (each edit anchored on exact fragments, so a later release elsewhere in a file does not
matter): the landing generator, the site analytics, the CRM bot's cars_ui and the three order-page files.
New: the partners data, the finance page renderer, the CRM bot screen, the order-page link style and the
partner logo. Live files are pinned by the preview plan.
"""
from pathlib import Path

import edit_analytics
import edit_cars_ui
import edit_landings
import edit_order
import logo_assets
import order_assets
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
EDITS = {edit_landings.NAME: lambda source: edit_landings.build(source),
         edit_analytics.NAME: lambda source: edit_analytics.build(edit_analytics.NAME, source),
         edit_cars_ui.NAME: lambda source: edit_cars_ui.build(edit_cars_ui.NAME, source),
         **{name: (lambda source, name=name: edit_order.build(name, source)) for name in edit_order.EDITS}}
SOURCE_FILES = tuple(EDITS)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    result = {name: edit(source[name]) for name, edit in EDITS.items()}
    result.update({target: (HERE / name).read_bytes() for target, name in NEW_MODULES.items()})
    result.update({name: text.encode('utf-8') for name, text in order_assets.FILES.items()})
    result.update(logo_assets.FILES)
    return result
