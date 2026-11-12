"""Build the step 2 fix candidate from the live pages; only the home page (and korea.html if it holds the line) change."""
import edit_home
from release_constants import HOME, KOREA

# These pages change with other publications; they are pinned by the plan instead.
SOURCE_FILES = (HOME, KOREA)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    result = {HOME: edit_home.build(source[HOME])}
    korea = edit_home.build(source[KOREA], required=False)
    if korea is not None:
        result[KOREA] = korea
    return result
