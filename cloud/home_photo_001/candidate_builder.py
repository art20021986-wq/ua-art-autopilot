"""Build the candidate files from the exact installed sources (the model is fetched by deployment_remote)."""
import hashlib
from pathlib import Path

import build_cars_ui
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {'cars_ui.py': build_cars_ui.EXPECTED_SHA256}
# Read-only collaborators the new modules rely on; any drift stops the plan.
DEPENDENCY_SHA256 = {
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',          # get_staff, ROLE_OWNER
    'team_bot.py': 'aebe2c091fdf1f19a8a011784dd70e2d648dc04607ec64374e4ff9f402e995af',    # main_menu «Сотрудники» = owner
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    candidate = {'cars_ui.py': build_cars_ui.build(source['cars_ui.py'])}
    candidate.update({name: (HERE / name).read_bytes() for name in NEW_MODULES})
    return candidate
