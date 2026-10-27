"""Build the home reviews candidate from the live home page and the Roboto font file; only changed files."""
import edit_home
from release_constants import FONT, HOME
import roboto_font

# The home page changes with every catalog publication; it is pinned by the plan instead.
# The font file is new in release 4: add FONT here once it is live, as was done for the logo in release 2.
SOURCE_FILES = (HOME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    result = {HOME: edit_home.build(source[HOME])}
    if source.get(FONT) != roboto_font.WOFF2:
        result[FONT] = roboto_font.WOFF2
    return result
