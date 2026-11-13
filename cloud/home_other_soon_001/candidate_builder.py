"""Build the «coming soon» candidate for the other 7 countries from the live home page; only the home page changes."""
import edit_home
from release_constants import HOME

# The home page changes with other publications; it is pinned by the plan instead.
SOURCE_FILES = (HOME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {HOME: edit_home.build(source[HOME])}
