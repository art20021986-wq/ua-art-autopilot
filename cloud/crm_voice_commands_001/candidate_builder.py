"""Build the candidate files from the exact installed sources."""
import hashlib
from pathlib import Path

import candidate
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
# Installed source read by CRM-VOICE-PROBE-20261101; any drift stops the plan.
SOURCE_SHA256 = {'cars_ui.py': 'cc5cf2e053781f51cfd5b0c85dea4b23f031912c7e8c99ae66c00bd528819b1f'}
# Read-only collaborator voice_stage relies on (storage_status), installed by DELIVERY-STATUS.
DEPENDENCY_SHA256 = {'ua_delivery_status.py': 'c544bc121b7b3b66d45519d5b63ed3687567af7e9d5f7011ae2fb53cc372bdd0'}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {'cars_ui.py': candidate.cars_ui(source['cars_ui.py'].decode('utf-8')).encode('utf-8')}
    result.update({name: (HERE / name).read_bytes() for name in NEW_MODULES})
    return result
