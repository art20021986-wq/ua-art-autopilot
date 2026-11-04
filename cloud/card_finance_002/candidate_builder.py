"""Build the CARD-FINANCE-002 candidate: the yellow finance link module and the new SEO revision (republish once)."""
from pathlib import Path

import edit_metadata

HERE = Path(__file__).resolve().parent
SOURCE_FILES = (edit_metadata.NAME,)
DEPENDENCY_SHA256 = {}
REPLACED = {'ua_card_finance.py': 'ua_card_finance.py'}


def build(source, dependencies):
    result = {edit_metadata.NAME: edit_metadata.build(source[edit_metadata.NAME])}
    result.update({target: (HERE / name).read_bytes() for target, name in REPLACED.items()})
    return result
