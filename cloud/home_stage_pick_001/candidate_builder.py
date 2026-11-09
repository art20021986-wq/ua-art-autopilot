"""Build the candidate files from the exact installed sources."""
import hashlib
from pathlib import Path

import build_cars_ui
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {'cars_ui.py': build_cars_ui.EXPECTED_SHA256}
# Read-only collaborators the new modules rely on; any drift stops the plan.
DEPENDENCY_SHA256 = {
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',                 # get_card, get_staff, ROLE_OWNER
    'master_card.py': '546ce4290f191ff67adc56e112dfbbe100633806a2d67e0e63a0e78874ac165e',        # podgotovit_vitrinu
    'publication_fence.py': 'c739a1017c53c6391dbf875621d6c860216fe8a132b738eef47b8f8019594a21',  # publication_fence
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    candidate = {'cars_ui.py': build_cars_ui.build(source['cars_ui.py'])}
    candidate.update({name: (HERE / name).read_bytes() for name in NEW_MODULES})
    return candidate
