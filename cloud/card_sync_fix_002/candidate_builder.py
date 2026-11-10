"""Build the CARD-SYNC-FIX-002 candidate: the live ua_additional_spec.py with the social profile hosts approved."""
import edit_spec

SOURCE_FILES = (edit_spec.NAME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {edit_spec.NAME: edit_spec.build(edit_spec.NAME, source[edit_spec.NAME])}
