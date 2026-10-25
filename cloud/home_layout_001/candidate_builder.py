"""Build the home layout candidate from the live home page and the owner's photo."""
import base64

import build_home
import home_photos
from release_constants import HOME, PHOTOS

# The home page changes with every catalog publication; it is pinned by the plan instead.
SOURCE_FILES = (HOME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    result = {name: base64.b64decode(home_photos.PHOTOS[name]) for name in PHOTOS}
    result[HOME] = build_home.build(source[HOME])
    return result
