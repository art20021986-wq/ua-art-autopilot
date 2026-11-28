"""Build the LOGO-CARD-001 candidate: the «Головна» / «Назад» buttons on the car cards too.

LOGO-001 (installed 2026-11-28, LOGO-INSTALL-20261128-R2) writes the buttons just before the header's RU / UA / GE
switch. A card is written by ua_mobile_comfort(ua_lang_bar(ua_layout_reserve(ua_brand_home(html)))): ua_brand_home runs
before ua_lang_bar has written the switch (just before .svyaz), so the cards got no buttons. The fixed ua_header_nav.py
puts them before .svyaz when there is no switch yet; ua_lang_bar then writes the switch right after them. Pages that
already have a switch get the buttons exactly as before. ua_seo_metadata SEO_REVISION: the CRM sync republishes every
card once. No page is written by the install; texts, links, photos, the switch, the logo and CRM data do not change.
"""
import hashlib
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
MODULE = 'ua_header_nav.py'
# The installed copy this release replaces (LOGO-001: LOGO-INSTALL-20261128-R2 plan, = cloud/logo_site_001 on main).
MODULE_SHA256 = '3ba992f49181278741fa369b4bfd6bfbfa8e294b0a80bf3e7d5998f6edc70a31'
# The installed ua_seo_metadata.py: the LOGO-001 revision (LOGO-INSTALL-20261128-R2 plan 135851f5 -> 7a07a19e).
# Only its SEO_REVISION line changes; the SEO-PRICE tail stays as it is.
METADATA_SHA256 = '7a07a19e549a1c410c4bc184ce29b2044b1b83a9d4eb5b7be7d518c76664051b'
METADATA = 'ua_seo_metadata.py'
TAG = 'LOGO-CARD-001'
OLD_REVISION = "SEO_REVISION = 'LOGO-001'"
NEW_REVISION = "SEO_REVISION = '%s'" % TAG
REVISION = re.compile(r"^SEO_REVISION = '[A-Z0-9-]+'$", re.M)
# A fresh card of 2026-11-28 as the writers have it when ua_brand_home runs (before ua_lang_bar): the preview runs it
# through the installed writer chain with the new module.
FIXTURE = 'card_no_switch_UA-0001.html'
FIXTURE_SHA256 = '8a919d429c7197a06ffdbc351d11e8dbf8885ae9e428ec9616ea55cb612bedf6'
DEPENDENCY_SHA256 = {}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def targets(root=None):
    """Existing files the candidate replaces."""
    return (MODULE, METADATA)


def edit(value):
    text = value.decode('utf-8')
    if NEW_REVISION in text:
        raise ValueError('LOGO_CARD_ALREADY_APPLIED:' + METADATA)
    if REVISION.findall(text) != [OLD_REVISION]:
        raise ValueError('LOGO_CARD_REVISION')
    return REVISION.sub(NEW_REVISION, text).encode('utf-8')


def build(source, dependencies):
    """{name: new bytes}; the live files must be the LOGO-001 ones."""
    if set(source) != set(targets()):
        raise ValueError('LOGO_CARD_SOURCE_SET')
    if sha(source[MODULE]) != MODULE_SHA256:
        raise ValueError('LOGO_CARD_LIVE_MODULE_UNEXPECTED:' + MODULE)
    if sha(source[METADATA]) != METADATA_SHA256:
        raise ValueError('LOGO_CARD_LIVE_MODULE_UNEXPECTED:' + METADATA)
    return {MODULE: (HERE/MODULE).read_bytes(), METADATA: edit(source[METADATA])}
