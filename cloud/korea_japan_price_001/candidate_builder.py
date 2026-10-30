"""Build the Korea/Japan price candidate: three live order-page files edited, the price style added."""
import edit_price
import price_assets

# Live files are pinned by the plan.
SOURCE_FILES = tuple(edit_price.EDITS)
# The page files of this package: a later release replaces them (backed up like the edited live files).
OWN_FILES = tuple(price_assets.FILES)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    result = {name: edit_price.build(name, source[name]) for name in SOURCE_FILES}
    result.update({name: text.encode('utf-8') for name, text in price_assets.FILES.items()})
    return result
