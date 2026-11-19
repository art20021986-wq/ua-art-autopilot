"""Build the SEO-HOME-001 candidate from the live sources: ua_card_lang (the card versions' link home, for the
future), ua_seo_metadata (the home title, for every later publication), the home page and the existing card
language versions (now)."""
import edit_card_lang
import edit_metadata
import page_edits

DEPENDENCY_SHA256 = {}


def targets(root):
    found = page_edits.cards(root)
    if not found:
        raise ValueError('NO_CARD_VERSIONS')
    return (edit_card_lang.NAME, edit_metadata.NAME, page_edits.HOME) + found


def build(source, dependencies=None):
    result = {}
    for name, value in source.items():
        if name == edit_card_lang.NAME:
            result[name] = edit_card_lang.build(value)
        elif name == edit_metadata.NAME:
            result[name] = edit_metadata.build(value)
        elif name == page_edits.HOME:
            result[name] = page_edits.home(value)
        else:
            result[name] = page_edits.card(value)
    return result
