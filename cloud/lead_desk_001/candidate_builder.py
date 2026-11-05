"""Build the candidate files from the exact installed sources.

ua_site_leads.py is replaced whole by this package's version (the CRM button and registration hook stay the
same names, see cloud/ads_ready_001/edit_cars_ui.py); the desk modules are new.
"""
import hashlib
from pathlib import Path

from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
# Installed source read by LEAD-DESK-PROBE-20261105; any drift stops the plan.
SOURCE_SHA256 = {
    'ua_site_leads.py': 'ed6aca7dd8fdb8f6dbb47051453e083b14282a2102996a2bcebe992a01b994b4',
}
# Read-only collaborators the desk relies on.
DEPENDENCY_SHA256 = {
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',  # connect, roles, create_card
    'ua_order/storage.py': 'a51d2e5bbc8cc1c25f686bfefb88490f0569b3e8996c8df1943614608ff79b33',  # NotFound, row view
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in tuple(SOURCE_SHA256) + NEW_MODULES}
