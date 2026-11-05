"""Build the FINANCE-OTP-004 candidate: the finance page's renderer with the partner logos marked translate="no".

Only the renderer is replaced, and only while both finance modules are still exactly what FINANCE-OTP-003 left
live (no later edit is overwritten unseen; the texts stay as they are).
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ('ua_finance_partners.py', 'ua_seo_finance.py')
CHANGED = ('ua_seo_finance.py',)
# Live since FINANCE-OTP-003 (texts, cloud/finance_otp_003) and FINANCE-OTP-002 (renderer, cloud/finance_otp_002).
LIVE_SHA256 = {'ua_finance_partners.py': '7d3ef729bb90c7c1093d32f3128e3dfc4d6baac7688bd2d49f2518cd3bd8756d',
               'ua_seo_finance.py': 'f7fe58d9677089912c544d1e980058fee1c5f16ed759d27a156cf4d9aa65f640'}
SOURCE_FILES = MODULES
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name in MODULES:
        if hashlib.sha256(source[name]).hexdigest() != LIVE_SHA256[name]:
            raise ValueError('LIVE_MODULE_CHANGED:' + name)
    return {name: (HERE / name).read_bytes() for name in CHANGED}
