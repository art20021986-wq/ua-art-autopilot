"""Build the PHOTO-ADD-001 candidate from the installed sources: two exact edits in cars_ui.py and crm_online_guard.py.

The installed files change with other releases, so they are pinned by the preview plan (before/after hashes), not
here; each edit refuses a file whose edited lines are not exactly as expected.
"""
import edit_cars_ui
import edit_crm_online_guard

EDITS = (edit_cars_ui, edit_crm_online_guard)
SOURCE_FILES = tuple(edit.NAME for edit in EDITS)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {edit.NAME: edit.build(source[edit.NAME]) for edit in EDITS}
