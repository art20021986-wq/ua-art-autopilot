"""Build the candidate files from the exact installed sources."""
import hashlib
from pathlib import Path

import candidate
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
# Installed sources read by CRM-PHOTO-PROBE-20261101-R2; any drift stops the plan.
SOURCE_SHA256 = {
    'local_ocr.py': 'd236fe3c30792217370e403061c2cb532f4cab2cc3198e29146dd588a1317b45',
    'team_bot.py': 'aebe2c091fdf1f19a8a011784dd70e2d648dc04607ec64374e4ff9f402e995af',
}
# Read-only collaborators photo_card relies on.
DEPENDENCY_SHA256 = {
    'ai_fast_schema.py': 'd2ac2104b2293e3c5cb38930fac6f4de87b9d1d3f35783b1b4e892433fcfd64e',  # fast_text_data, clean_car
    'ai_filter.py': '6a4a7199d9593645aaf634d27d3234c282342a1e20faca2cbb1206478af13a8f',      # find_by_vin, store, render
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',            # get_staff
}
BUILDERS = {'local_ocr.py': candidate.local_ocr, 'team_bot.py': candidate.team_bot}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {name: BUILDERS[name](source[name].decode('utf-8')).encode('utf-8') for name in SOURCE_SHA256}
    result.update({name: (HERE / name).read_bytes() for name in NEW_MODULES})
    return result
