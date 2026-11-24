"""Build the CLIENT-BOT-MENU candidate: ua_bot_profile.py is replaced; the installed one must be the known version
(CRM-BOT-PROFILE-INSTALL-20261115)."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_bot_profile.py': '4a8c2f3ab88f4d81284da756898342dc9ddc13914e5960fb66decccd887ac2c4',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name, digest in SOURCE_SHA256.items():
        if source.get(name) is None or hashlib.sha256(source[name]).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {'ua_bot_profile.py': (HERE / 'ua_bot_profile.py').read_bytes()}
