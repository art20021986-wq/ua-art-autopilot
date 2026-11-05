"""Build the candidate: ua_staff_invite.py replaced whole (no time limit); the guard stays as installed."""
import hashlib
from pathlib import Path

from release_constants import NEW_MODULES, REPLACED_MODULES

HERE = Path(__file__).resolve().parent
# Installed by CRM-INVITE-INSTALL-20261105; any drift stops the plan.
SOURCE_SHA256 = {'ua_staff_invite.py': '801bebeaa1c621ec2c22ce619adaddf08aa74484ad09a9132e4ba5306c175589'}
# Read-only collaborator: the guard calls ua_staff_invite.valid(tekst, DB) with two arguments.
DEPENDENCY_SHA256 = {'bezopasnost.py': '2d59ef2e441a5d48039836a3cfacea024f547d573de94946abc138cf941a79d5'}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in NEW_MODULES + REPLACED_MODULES}
