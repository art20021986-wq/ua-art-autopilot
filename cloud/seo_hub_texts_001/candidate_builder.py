"""Build the SEO-HUB-TEXTS-001 candidate: the new texts module and the live landing generator that places them."""
from pathlib import Path

import edit_landings
from release_constants import REPLACED_FILES

HERE = Path(__file__).resolve().parent
SOURCE_FILES = (edit_landings.NAME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    result = {target: (HERE / name).read_bytes() for target, name in REPLACED_FILES.items()}
    result[edit_landings.NAME] = edit_landings.build(source[edit_landings.NAME])
    return result
