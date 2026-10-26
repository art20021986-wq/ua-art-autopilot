"""Build the home reviews candidate from the live home page and the AUTO.RIA logo; only changed files."""
import autoria_logo
import edit_home
from release_constants import HOME, LOGO

# The home page changes with every catalog publication; it is pinned by the plan instead.
# The logo is live since HOME-REVIEWS-INSTALL-20261026 and is written again only if it differs.
SOURCE_FILES = (HOME, LOGO)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    result = {HOME: edit_home.build(source[HOME])}
    logo = autoria_logo.SVG.encode('utf-8')
    if source.get(LOGO) != logo:
        result[LOGO] = logo
    return result
