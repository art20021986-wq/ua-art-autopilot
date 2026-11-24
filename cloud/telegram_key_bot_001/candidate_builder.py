"""Build the TELEGRAM-KEY-BOT candidate from the installed sources: cars_ui.py gets one block at the end; one new module.

cars_ui.py changes with other releases, so it is pinned by the preview plan (before/after hashes), not here; the edit
itself refuses an unexpected file.
"""
from pathlib import Path

import edit_cars_ui
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_FILES = (edit_cars_ui.NAME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    result = {edit_cars_ui.NAME: edit_cars_ui.build(source[edit_cars_ui.NAME])}
    result.update({name: (HERE / name).read_bytes() for name in NEW_MODULES})
    return result
