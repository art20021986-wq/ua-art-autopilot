"""Build the CARD-CANONICAL-FIX-001 candidate: the live master_card.py whose publication check accepts the
card's language-version canonical."""
import edit_guard

SOURCE_FILES = (edit_guard.NAME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {edit_guard.NAME: edit_guard.build(edit_guard.NAME, source[edit_guard.NAME])}
