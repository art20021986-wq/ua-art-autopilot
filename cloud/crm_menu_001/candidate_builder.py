"""Build the candidate files from the exact installed sources."""
import hashlib
from pathlib import Path

import candidate
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
# Installed source read by LEAD-DESK-PROBE-20261105-R4; any drift stops the plan.
SOURCE_SHA256 = {'cars_ui.py': '8affadf1495a13f70a4902e175560f1e7e2a8b31f83caa91e5734451d4077299'}
# Read-only collaborators: the menu caller and the enquiry desk entry.
DEPENDENCY_SHA256 = {
    'team_bot.py': 'bfd2ada58521c3d5a3fc37f4ef7b0883c99b85dcaf2eb43597c99d2c07814c03',
    'ua_site_leads.py': '072c7f92d28db0543b100d3a7776c668dcc4a78216d873dab7ef19d4be3151cc',
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {'cars_ui.py': candidate.cars_ui(source['cars_ui.py'].decode('utf-8')).encode('utf-8')}
    result.update({name: (HERE / name).read_bytes() for name in NEW_MODULES})
    return result
