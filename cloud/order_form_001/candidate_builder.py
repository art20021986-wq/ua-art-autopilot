"""Build the application-view candidate from the live files: home link, order page, order strings."""
import edit_home_link
import edit_order_page
from release_constants import HOME, PAGE, STRINGS

# These files change with publications; they are pinned by the plan instead.
SOURCE_FILES = (HOME, PAGE, STRINGS)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {HOME: edit_home_link.build(source[HOME]),
            PAGE: edit_order_page.build(PAGE, source[PAGE]),
            STRINGS: edit_order_page.build(STRINGS, source[STRINGS])}
