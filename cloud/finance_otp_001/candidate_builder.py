"""Build the FINANCE-OTP-001 candidate: the finance page's data and renderer, and the OTP Bank logo.

The two modules are replaced whole by this package's versions, but only over the exact FINANCE-001 files (the
live ones must still be what FINANCE-001 installed, so no later edit is overwritten unseen). New: the logo.
"""
import hashlib
from pathlib import Path

import logo_assets

HERE = Path(__file__).resolve().parent
MODULES = ('ua_finance_partners.py', 'ua_seo_finance.py')
# The FINANCE-001 versions (cloud/finance_001), as installed on 2026-11-03.
LIVE_SHA256 = {'ua_finance_partners.py': 'f358794f60c52f018fd2984848ab87a603ca5f4d327615cd5983cc510d09b0da', 'ua_seo_finance.py': '3b4d514df9f61056ca8224047a3429115e448976a754478e588fcae6a71726e0'}
SOURCE_FILES = MODULES
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name in MODULES:
        if hashlib.sha256(source[name]).hexdigest() != LIVE_SHA256[name]:
            raise ValueError('LIVE_MODULE_CHANGED:' + name)
    result = {name: (HERE / name).read_bytes() for name in MODULES}
    result.update(logo_assets.FILES)
    return result
