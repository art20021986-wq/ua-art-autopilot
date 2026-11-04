"""Build the CARD-FINANCE-002 candidate: the installed ua_card_finance.py replaced by the yellow-link version (the
live file is read, so the plan pins and backs it up) and the new SEO revision (republish once)."""
from pathlib import Path

import edit_metadata

HERE = Path(__file__).resolve().parent
MODULE = 'ua_card_finance.py'
SOURCE_FILES = (edit_metadata.NAME, MODULE)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    if b"LINK_ID = 'ua-finance-link'" not in source[MODULE]:
        raise ValueError('LIVE_MODULE:' + MODULE)
    return {edit_metadata.NAME: edit_metadata.build(source[edit_metadata.NAME]), MODULE: (HERE / MODULE).read_bytes()}
