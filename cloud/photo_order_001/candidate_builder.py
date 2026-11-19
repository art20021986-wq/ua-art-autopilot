"""Build the PHOTO-ORDER-001 candidate from the installed sources: two exact edits in cars_ui.py (queue drain).

cars_ui.py changes with other releases, so it is pinned by the preview plan (before/after hashes), not here; the edit
refuses a file whose edited lines are not exactly as expected.
"""
import edit_cars_ui

EDITS = (edit_cars_ui,)
SOURCE_FILES = tuple(edit.NAME for edit in EDITS)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {edit.NAME: edit.build(source[edit.NAME]) for edit in EDITS}
