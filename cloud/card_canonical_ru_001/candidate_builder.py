"""Build the CARD-CANONICAL-RU-001 candidate: the old card page's canonical is its Russian version
(ua_card_lang), the publication check accepts it (master_card), and the cards republish once (ua_seo_metadata)."""
import edit_card_lang
import edit_guard
import edit_metadata

EDITS = (edit_card_lang, edit_guard, edit_metadata)
SOURCE_FILES = tuple(edit.NAME for edit in EDITS)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {edit.NAME: edit.build(source[edit.NAME]) for edit in EDITS}
