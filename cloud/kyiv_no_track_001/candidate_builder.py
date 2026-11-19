"""Build the KYIV-NO-TRACK-001 candidate from the live sources: every card generator with the tracking hook
(edit_generators) and ua_seo_metadata (edit_metadata, so the CRM public sync republishes the cards once)."""
import edit_generators
import edit_metadata

DEPENDENCY_SHA256 = {}


def targets(root):
    """The generators that carry the installed tracking hook (stranica.py and master_card.py must), plus metadata."""
    names = [n for n in edit_generators.GENERATORS if (root / n).is_file()
             and edit_generators.has_hook((root / n).read_bytes())]
    if not set(edit_generators.REQUIRED) <= set(names):
        raise ValueError('TRACKING_HOOK_MISSING')
    return tuple(names) + (edit_metadata.NAME,)


def build(source, dependencies=None):
    result = {}
    for name, value in source.items():
        if name == edit_metadata.NAME:
            result[name] = edit_metadata.build(value)
        else:
            result[name] = edit_generators.build(name, value)
    return result
