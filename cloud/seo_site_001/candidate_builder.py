"""Build the SEO-SITE-001 candidate from the live sources: ua_seo_metadata (Ukrainian catalogue and terms at later
publications), korea.html share tags, the catalogue and terms heads now, and the removal of the old pages of four
cars no longer in the CRM (value None)."""
import edit_metadata
import korea_tags
import old_cards
import uk_head

DEPENDENCY_SHA256 = {}


def targets(root):
    return (edit_metadata.NAME, korea_tags.NAME) + uk_head.NAMES + old_cards.find(root)


def build(source, dependencies=None):
    result = {}
    for name, value in source.items():
        if name == edit_metadata.NAME:
            result[name] = edit_metadata.build(value)
        elif name == korea_tags.NAME:
            result[name] = korea_tags.build(value)
        elif name in uk_head.NAMES:
            result[name] = uk_head.build(value)
        elif old_cards.planned(name):
            result[name] = None
        else:
            raise ValueError('UNPLANNED:' + name)
    return result
