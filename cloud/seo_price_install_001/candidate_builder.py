"""Build the SEO-PRICE-001 candidate from the installed sources: the new ua_seo_price.py and a tail on
ua_seo_metadata.card_facts (metadata_tail.py). The installed ua_seo_metadata.py must be the one read by
SEO-PRICE-PROBE-20261128 (any other version is refused). No page, catalog or other module changes here; the cards
are rebuilt after the install by the existing publisher."""
import hashlib
from pathlib import Path

import metadata_tail
from release_constants import NEW_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_FILES = (metadata_tail.NAME,)
# The live ua_seo_metadata.py read by SEO-PRICE-PROBE-20261128 (installed 2026-11-26 09:07Z).
LIVE_SHA256 = {metadata_tail.NAME: '5910529284faf3fcf2ab1ae3951dd42199bc07738f76003cd65d528bf6f87eca'}
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name, digest in LIVE_SHA256.items():
        if hashlib.sha256(source[name]).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    candidate = {metadata_tail.NAME: metadata_tail.build(source[metadata_tail.NAME])}
    candidate.update({name: (HERE / name).read_bytes() for name in NEW_MODULES})
    return candidate
