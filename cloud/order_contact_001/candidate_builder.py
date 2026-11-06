"""Build the candidate from the live files: order page, order script, form module, order strings."""
import edit_contact_form
import edit_order_page
from release_constants import FORM, PAGE, SCRIPT, STRINGS

# These files change with publications; they are pinned by the plan instead.
SOURCE_FILES = (PAGE, SCRIPT, FORM, STRINGS)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {PAGE: edit_order_page.build(PAGE, source[PAGE]),
            SCRIPT: edit_order_page.build(SCRIPT, source[SCRIPT]),
            FORM: edit_contact_form.build(source[FORM]),
            STRINGS: edit_order_page.build(STRINGS, source[STRINGS])}
