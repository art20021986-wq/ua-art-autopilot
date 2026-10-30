"""Build the Japan note candidate: three live order-page files edited, the note style added."""
import edit_japan
import note_assets

# Live files are pinned by the plan.
SOURCE_FILES = tuple(edit_japan.EDITS)
# The page files of this package: a later release replaces them (backed up like the edited live files).
OWN_FILES = tuple(note_assets.FILES)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    result = {name: edit_japan.build(name, source[name]) for name in SOURCE_FILES}
    result.update({name: text.encode('utf-8') for name, text in note_assets.FILES.items()})
    return result
