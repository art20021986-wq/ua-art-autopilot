"""Build the VIN-MVS candidate: ua_vin_decode.py and ua_new_car_bot.py are replaced (pinned installed versions),
ua_vin_mvs.py is new. ua_vin_lots.py, ua_vin_pattern.py, ai_fast_schema.py and ai_filter.py are only read and must be
the known versions.
"""
import hashlib
from pathlib import Path

from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_vin_decode.py': '386c98d9083f1a89e41ef7adcebef1daab8c8d1bd1a43d91d44ace441351b25a',  # VIN-PATTERN-INSTALL-20261117
    'ua_new_car_bot.py': '6524057bebcb324bff386c4fa081e1357c0cdca4308ee351e628d0d44ebc8e28',  # VIN-KOREA-INSTALL-20261115
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {
    'ua_vin_lots.py': 'c7ddd2224d6ede0afe578a792e952620c02012bedda6de85b18491f02cef9159',  # VIN-KOREA-INSTALL-20261115
    'ua_vin_pattern.py': 'f4026a895cf39b477c034fa0f788969206d9472328a806c131cff56c391e348e',  # VIN-PATTERN-INSTALL-20261117
    'ai_fast_schema.py': 'd2ac2104b2293e3c5cb38930fac6f4de87b9d1d3f35783b1b4e892433fcfd64e',  # clean_car
    'ai_filter.py': '6a4a7199d9593645aaf634d27d3234c282342a1e20faca2cbb1206478af13a8f',  # CRM vocabulary
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in SOURCE_FILES + NEW_MODULES}
