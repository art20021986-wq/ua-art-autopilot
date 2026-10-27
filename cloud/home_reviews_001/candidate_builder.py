"""Build the home reviews candidate from the live home page and the Roboto font file; only changed files."""
import edit_home
from release_constants import FONT, HOME
import roboto_font

# The home page changes with every catalog publication; it is pinned by the plan instead.
# The font file is live since HOME-REVIEWS-FONT-INSTALL-20261027 and is written again only if it differs.
SOURCE_FILES = (HOME, FONT)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    result = {HOME: edit_home.build(source[HOME])}
    if source.get(FONT) != roboto_font.WOFF2:
        result[FONT] = roboto_font.WOFF2
    return result
