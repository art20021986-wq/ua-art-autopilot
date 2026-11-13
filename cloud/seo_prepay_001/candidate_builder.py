"""Build the SEO-PREPAY-001 candidate: auction/custom-order terms (600 $ + 1 000 $) in ua_seo_landings (Korea pages)
and ua_seo_order_models (the Japan page)."""
import edit_landings
import edit_models

SOURCE_FILES = (edit_landings.NAME, edit_models.NAME)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {edit_landings.NAME: edit_landings.build(source[edit_landings.NAME]),
            edit_models.NAME: edit_models.build(source[edit_models.NAME])}
