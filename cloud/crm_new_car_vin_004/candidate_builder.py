"""Build the VIN-PATTERN candidate: ua_vin_decode.py is replaced (pinned installed version), ua_vin_pattern.py is
new. ua_vin_lots.py (archive, raw_fields), ai_fast_schema.py and ai_filter.py are only read and must be the known
versions.
"""
import hashlib
from pathlib import Path

from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_vin_decode.py': '88093e8782c79451d5ce3ffd14c1c136e36dc73c56e46c2ba36b66e0aa079113',  # VIN-KOREA-INSTALL-20261115
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {
    'ua_vin_lots.py': 'c7ddd2224d6ede0afe578a792e952620c02012bedda6de85b18491f02cef9159',  # VIN-KOREA-INSTALL-20261115
    'ai_fast_schema.py': 'd2ac2104b2293e3c5cb38930fac6f4de87b9d1d3f35783b1b4e892433fcfd64e',  # clean_car
    'ai_filter.py': '6a4a7199d9593645aaf634d27d3234c282342a1e20faca2cbb1206478af13a8f',  # CRM vocabulary
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in SOURCE_FILES + NEW_MODULES}
