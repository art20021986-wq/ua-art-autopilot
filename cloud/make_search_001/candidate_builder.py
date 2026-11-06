"""Build the candidate from the live files: order page, order script, form module; two new list files."""
import edit_order_page
import edit_preferences_form
import picker_assets
from release_constants import FORM, PAGE, PICKER_CSS, PICKER_JS, SCRIPT

# These files change with publications; they are pinned by the plan instead.
SOURCE_FILES = (PAGE, SCRIPT, FORM)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {PAGE: edit_order_page.build(PAGE, source[PAGE]),
            SCRIPT: edit_order_page.build(SCRIPT, source[SCRIPT]),
            FORM: edit_preferences_form.build(source[FORM]),
            PICKER_JS: picker_assets.JS.encode('utf-8'),
            PICKER_CSS: picker_assets.CSS.encode('utf-8')}
