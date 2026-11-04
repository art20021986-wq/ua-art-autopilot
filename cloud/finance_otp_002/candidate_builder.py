"""Build the FINANCE-OTP-002 candidate: the finance page's data and renderer with the bank card's own button.

The two modules are replaced whole by this package's versions, but only over the exact FINANCE-OTP-001 files (the
live ones must still be what FINANCE-OTP-001 installed, so no later edit is overwritten unseen).
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ('ua_finance_partners.py', 'ua_seo_finance.py')
# The FINANCE-OTP-001 versions (cloud/finance_otp_001), as installed and verified on 2026-11-04.
LIVE_SHA256 = {'ua_finance_partners.py': '10190326a7ab71d72f8f478a71b89a6a30d96766598a09c914cc26bac5bf7f73',
               'ua_seo_finance.py': 'e2ae13806e514c38b42668e634b31079b697ecaeedeea5bac73a12ad718cc750'}
SOURCE_FILES = MODULES
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name in MODULES:
        if hashlib.sha256(source[name]).hexdigest() != LIVE_SHA256[name]:
            raise ValueError('LIVE_MODULE_CHANGED:' + name)
    return {name: (HERE / name).read_bytes() for name in MODULES}
