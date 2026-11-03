"""Build the CARD-FINANCE-001 candidate: card post-processing adds the finance link; the Ukrainian card
version follows the link's data-uk-href. The new module reads ua_finance_partners (installed by FINANCE-001)."""
from pathlib import Path

import edit_card_lang
import edit_metadata

HERE = Path(__file__).resolve().parent
EDITS = {edit_metadata.NAME: edit_metadata.build, edit_card_lang.NAME: edit_card_lang.build}
SOURCE_FILES = tuple(EDITS)
DEPENDENCY_SHA256 = {}
NEW_MODULES = {'ua_card_finance.py': 'ua_card_finance.py'}


def build(source, dependencies):
    result = {name: edit(source[name]) for name, edit in EDITS.items()}
    result.update({target: (HERE / name).read_bytes() for target, name in NEW_MODULES.items()})
    return result
