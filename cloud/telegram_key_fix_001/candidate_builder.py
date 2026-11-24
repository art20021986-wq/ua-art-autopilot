"""Build the TELEGRAM-KEY-FIX candidate: ua_telegram_key.py is replaced by this package's copy (key-attempt pattern
narrowed so ordinary work messages such as a price and a VIN are no longer taken for a key).

The installed file must be exactly the one TELEGRAM-KEY-BOT installed; anything else is refused.
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = 'ua_telegram_key.py'
INSTALLED_SHA256 = 'f8dc61b412b2d3df40833b633a0eaa168967590a71046f5db0c8caf9bec9e408'
SOURCE_FILES = (NAME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    if hashlib.sha256(source[NAME]).hexdigest() != INSTALLED_SHA256:
        raise ValueError('UA_TELEGRAM_KEY_UNEXPECTED')
    return {NAME: (HERE / NAME).read_bytes()}
