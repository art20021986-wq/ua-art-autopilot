"""Build the PAGES-LAG-FIX-001 candidate from the installed sources: one exact edit each in the Python 3.10
usercustomize.py (the self-check only in the bot process) and samokontrol.py (error tail in the log, one retry).

The installed files are pinned by the preview plan (before/after hashes); each edit refuses a file whose edited lines
are not exactly as expected.
"""
import edit_samokontrol
import edit_usercustomize

EDITS = (edit_samokontrol, edit_usercustomize)
SOURCE_FILES = tuple(edit.NAME for edit in EDITS)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {edit.NAME: edit.build(source[edit.NAME]) for edit in EDITS}
