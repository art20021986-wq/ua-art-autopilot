"""Build the TELEGRAM-KEY-FIX candidate: ua_telegram_key.py is replaced by this package's copy (key-attempt pattern
narrowed so ordinary work messages such as a price and a VIN are no longer taken for a key).

The installed file must be exactly the one STAFF-FULL-ACCESS-001 (CRM-FULL-ACCESS-INSTALL-20261124-R2) left; anything else
is refused.
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = 'ua_telegram_key.py'
INSTALLED_SHA256 = 'd45dd4cdb3be21847e1b5b24a65dc706c4aaca18c2da376c5fc99d1ded1f7d92'
SOURCE_FILES = (NAME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    if hashlib.sha256(source[NAME]).hexdigest() != INSTALLED_SHA256:
        raise ValueError('UA_TELEGRAM_KEY_UNEXPECTED')
    return {NAME: (HERE / NAME).read_bytes()}
