"""Build the VIN-KOREA candidate: ua_vin_decode.py and ua_new_car_bot.py are replaced (pinned installed versions),
ua_vin_lots.py is new.
ai_fast_schema.py and ai_filter.py are only read and must be the known versions.
"""
import hashlib
from pathlib import Path

from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_vin_decode.py': '9df929afadc026bf7e722e1bf8d42dcbd84c4f879c9308d8ac0b71169242c7b0',  # NEW-CAR-VIN-SPEC-INSTALL-20261114-B
    'ua_new_car_bot.py': '03f3aff0099d2b0e4c6016f67d97ab04791aa887cc374b00966f198db01ac5dd',  # NEW-CAR-VIN-SPEC-INSTALL-20261114-B
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {
    'ai_fast_schema.py': 'd2ac2104b2293e3c5cb38930fac6f4de87b9d1d3f35783b1b4e892433fcfd64e',  # clean_car
    'ai_filter.py': '6a4a7199d9593645aaf634d27d3234c282342a1e20faca2cbb1206478af13a8f',  # CRM vocabulary
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in SOURCE_FILES + NEW_MODULES}
