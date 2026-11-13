"""Build the SEO-PREPAY-001 candidate: ua_seo_landings with the auction-order terms (600 $ + 1 000 $)."""
import edit_landings

SOURCE_FILES = (edit_landings.NAME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {edit_landings.NAME: edit_landings.build(source[edit_landings.NAME])}
