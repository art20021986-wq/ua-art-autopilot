"""Build the NEW-CAR-VIN-SPEC candidate: ua_new_car_bot.py is replaced (pinned installed version), ua_vin_decode.py
is new. db.py, photo_card.py, ai_fast_schema.py and ai_filter.py are only read and must be the known versions.
"""
import hashlib
from pathlib import Path

from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_new_car_bot.py': '06ab57a0d0c9bec33784baafd2c241f5bcdd4aa777bcb5464362d75e5f372474',  # NEW-CAR-VIN-INSTALL-20261112
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',  # get_staff
    'photo_card.py': '9e0b629680e25e125e69280f1d3f08d042319714567743ac55d12715f5b5a002',  # extract, create_card
    'ai_fast_schema.py': 'd2ac2104b2293e3c5cb38930fac6f4de87b9d1d3f35783b1b4e892433fcfd64e',  # clean_car
    'ai_filter.py': '6a4a7199d9593645aaf634d27d3234c282342a1e20faca2cbb1206478af13a8f',  # CRM vocabulary
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in SOURCE_FILES + NEW_MODULES}
