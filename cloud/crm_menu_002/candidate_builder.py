"""Build the candidate files from the exact installed sources."""
import hashlib
from pathlib import Path

import candidate
from release_constants import NEW_MODULES, REPLACED_MODULES

HERE = Path(__file__).resolve().parent
# Installed by CRM-MENU-INSTALL-20261105 (plan 1eef855a, owner-observed live); any drift stops the plan.
SOURCE_SHA256 = {'cars_ui.py': '9d330d03c783d918cb498f124c2604dc5ae2c588944a2ce7d6ea9210747785ec', 'ua_menu_extra.py': '90ac94f064b1895fb4bc708f32bf9e7d529b2fb9047b20ba49940f982681808d'}
# Read-only collaborator: the menu caller (main_menu builds «Клиенты» for staff, «Сотрудники» for the owner).
DEPENDENCY_SHA256 = {
    'team_bot.py': 'bfd2ada58521c3d5a3fc37f4ef7b0883c99b85dcaf2eb43597c99d2c07814c03',
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {'cars_ui.py': candidate.cars_ui(source['cars_ui.py'].decode('utf-8')).encode('utf-8')}
    result.update({name: (HERE / name).read_bytes() for name in NEW_MODULES + REPLACED_MODULES})
    return result
