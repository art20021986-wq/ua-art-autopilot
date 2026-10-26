"""Build the home reviews candidate from the live home page and the AUTO.RIA logo."""
import autoria_logo
import edit_home
from release_constants import HOME, LOGO

# The home page changes with every catalog publication; it is pinned by the plan instead.
SOURCE_FILES = (HOME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {HOME: edit_home.build(source[HOME]), LOGO: autoria_logo.SVG.encode('utf-8')}
