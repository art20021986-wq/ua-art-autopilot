"""Build the FINANCE-OTP-003 candidate: the finance page's texts with the first step worded without brackets.

Only the texts module is replaced, and only while both finance modules are still exactly what FINANCE-OTP-002
installed (no later edit is overwritten unseen; the renderer stays as it is).
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ('ua_finance_partners.py', 'ua_seo_finance.py')
CHANGED = ('ua_finance_partners.py',)
# The FINANCE-OTP-002 versions (cloud/finance_otp_002), as installed and verified on 2026-11-04.
LIVE_SHA256 = {'ua_finance_partners.py': 'fd701a91cf68d988cd20ece3df00dce2efd58b75c51e92eee91b24b7a5e8c748',
               'ua_seo_finance.py': 'f7fe58d9677089912c544d1e980058fee1c5f16ed759d27a156cf4d9aa65f640'}
SOURCE_FILES = MODULES
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name in MODULES:
        if hashlib.sha256(source[name]).hexdigest() != LIVE_SHA256[name]:
            raise ValueError('LIVE_MODULE_CHANGED:' + name)
    return {name: (HERE / name).read_bytes() for name in CHANGED}
