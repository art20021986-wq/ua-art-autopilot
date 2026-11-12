"""Build the SEO-UKRAINE-PAGE-001 candidate: the all-Ukraine topic page (new data module, registered in
ua_seo_order_models) and its links from the Korea hub and the custom-order page (ua_seo_hub_texts, ua_seo_landings)."""
from pathlib import Path

import edit_landings
import edit_models
from release_constants import REPLACED_FILES

HERE = Path(__file__).resolve().parent
SOURCE_FILES = (edit_landings.NAME, edit_models.NAME, 'ua_seo_hub_texts.py')  # the last is replaced whole
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    result = {target: (HERE / name).read_bytes() for target, name in REPLACED_FILES.items()}
    result[edit_landings.NAME] = edit_landings.build(source[edit_landings.NAME])
    result[edit_models.NAME] = edit_models.build(source[edit_models.NAME])
    return result
