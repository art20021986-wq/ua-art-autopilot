"""Build the ADS-KEYS-002 candidate: ua_google_ads_key.py is replaced by this package's copy (the keys may come one
by one; each answer names the value taken or the one with the wrong shape). The installed file must be exactly the
one ADS-KEYS-001 installed; anything else is refused.
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = 'ua_google_ads_key.py'
INSTALLED_SHA256 = '61a68a5739db1fc3892aa13bcd5b156686d7bd733808fdebbfe89e43c41cd950'
SOURCE_FILES = (NAME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies=None):
    if hashlib.sha256(source[NAME]).hexdigest() != INSTALLED_SHA256:
        raise ValueError('UA_GOOGLE_ADS_KEY_UNEXPECTED')
    return {NAME: (HERE / NAME).read_bytes()}
