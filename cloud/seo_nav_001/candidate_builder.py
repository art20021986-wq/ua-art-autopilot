"""Build the SEO-NAV-001 candidate: the live landing generator whose navigation line keeps only «Умови»."""
import edit_landings

SOURCE_FILES = (edit_landings.NAME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {edit_landings.NAME: edit_landings.build(source[edit_landings.NAME])}
