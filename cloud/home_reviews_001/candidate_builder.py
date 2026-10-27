"""Build the home reviews candidate from the live home page; only changed files."""
import edit_home
from release_constants import HOME

# The home page changes with every catalog publication; it is pinned by the plan instead.
SOURCE_FILES = (HOME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {HOME: edit_home.build(source[HOME])}
