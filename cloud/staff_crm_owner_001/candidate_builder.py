"""Build the BOT CRM candidate from the exact installed sources (LEAD-DESK-PROBE-20261112-R4 / 20261124).

New ua_owners.py (who the owners are: vladelec.txt first, then every active CRM «Владелец»); exact fragment edits
send the alerts of the CRM guard (bezopasnost.py) and of svyaz.py to every owner and let every owner use /dostup and
/kopiya. Any drift of an installed file stops the plan.
"""
import hashlib
from pathlib import Path

import edit_bezopasnost
import edit_svyaz
import edits

HERE = Path(__file__).resolve().parent
EDITORS = (edit_bezopasnost, edit_svyaz)
SOURCE_SHA256 = {
    'bezopasnost.py': '2d59ef2e441a5d48039836a3cfacea024f547d573de94946abc138cf941a79d5',
    'svyaz.py': '6493b4acd1d3d037ae774677d74a6ed0ad1292b8d25f39172dbd267cfa5ac3db',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
# ua_owners reads db.staff_ids_by_role(db.ROLE_OWNER); the smoke check imports it with the live db.py.
DEPENDENCY_SHA256 = {}
NEW = ('ua_owners.py',)


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {module.NAME: edits.apply(source[module.NAME], module.EDITS) for module in EDITORS}
    result.update({name: (HERE / name).read_bytes() for name in NEW})
    return result
