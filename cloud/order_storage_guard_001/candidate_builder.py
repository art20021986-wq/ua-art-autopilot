"""Build the ORDER-GUARD candidate: ua_order/bindings.py is replaced (pinned installed version), ua_order/outbox_guard.py
is new, ua_order/mysql_repository.py gets one log line with the MySQL error code. notifications.py and storage.py are
only read and must be the known versions.
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_order/bindings.py': 'e07cce08a7b55d16a41a6d1b904c30e928476c012846d9a6eead51dcefc50f9f',
    'ua_order/mysql_repository.py': '21419a04be798df84f6ec210a9086cc1b01d9fa0d76b7e6811d707ec14d6fe9a',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {
    'ua_order/notifications.py': '1ccd8c1a9d864dd5dc00b320b66569872f1b224d26f4eaae0adce7b5a95ac2bc',  # dispatch_once
    'ua_order/storage.py': 'a51d2e5bbc8cc1c25f686bfefb88490f0569b3e8996c8df1943614608ff79b33',  # StorageUnavailable
}
# Packaged copies (flat names: the bundle holds no folders).
PACKAGED = {'ua_order/bindings.py': 'ua_order_bindings.py', 'ua_order/outbox_guard.py': 'ua_order_outbox_guard.py'}
# mysql_repository.py: the MySQL error code goes to the bot log before the error is hidden.
RAISE = b"                    raise StorageUnavailable('Order storage unavailable') from None\n"
LOGGED = (b"                    logging.getLogger(__name__).warning(\n"
          b"                        'MySQL error %s', error.args[0] if error.args else type(error).__name__)\n") + RAISE
IMPORT = b'import json\n'


def patch_repository(value):
    if value.count(RAISE) != 1 or value.count(IMPORT) != 1 or b'import logging' in value:
        raise ValueError('REPOSITORY_ANCHOR')
    return value.replace(IMPORT, IMPORT + b'import logging\n').replace(RAISE, LOGGED)


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    candidate = {name: (HERE / packaged).read_bytes() for name, packaged in PACKAGED.items()}
    candidate['ua_order/mysql_repository.py'] = patch_repository(source['ua_order/mysql_repository.py'])
    return candidate
