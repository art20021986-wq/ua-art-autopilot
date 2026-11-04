"""Build the CARD-TEXT-UK-001 candidate: the live site language script with one more Ukrainian phrase."""
import edit_languages

SOURCE_FILES = (edit_languages.NAME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {edit_languages.NAME: edit_languages.build(source[edit_languages.NAME])}
