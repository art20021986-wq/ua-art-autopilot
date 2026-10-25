"""Build the order-page candidate from the three live files."""
import edit_order

# Live files are pinned by the plan.
SOURCE_FILES = tuple(edit_order.EDITS)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {name: edit_order.build(name, source[name]) for name in SOURCE_FILES}
