"""Build the candidate files from the exact installed sources."""
import hashlib
from pathlib import Path

import candidate
from release_constants import NEW_MODULES, REPLACED_MODULES

HERE = Path(__file__).resolve().parent
# Installed guard read by LEAD-DESK-PROBE-20261105-R9; any drift stops the plan.
SOURCE_SHA256 = {'bezopasnost.py': '0b10ec7458fa3cd6247a647c7d00cc76f4fa24407b91f9017124a57fabe36f2a'}
# Read-only collaborator: the CRM bot consumes the invite (team_bot.try_invite_code -> db.use_invite).
DEPENDENCY_SHA256 = {
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',
    'team_bot.py': 'bfd2ada58521c3d5a3fc37f4ef7b0883c99b85dcaf2eb43597c99d2c07814c03',
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {'bezopasnost.py': candidate.guard(source['bezopasnost.py'].decode('utf-8')).encode('utf-8')}
    result.update({name: (HERE / name).read_bytes() for name in NEW_MODULES + REPLACED_MODULES})
    return result
