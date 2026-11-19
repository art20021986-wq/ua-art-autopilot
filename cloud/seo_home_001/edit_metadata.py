"""ua_seo_metadata.py (SEO-HOME-001): the home page title in core_metadata, so every later catalogue publication
(normalize rewrites the title, og:title) keeps the approved title. Nothing else changes; no SEO_REVISION change
(the cards' output does not change). The old pair must occur exactly once."""
from titles import NEW, OLD

NAME = 'ua_seo_metadata.py'
BEFORE = "        'index.html': (\n            ('%s',\n             '%s'),\n" % (OLD['ru'], OLD['uk'])
AFTER = "        'index.html': (\n            ('%s',\n             '%s'),\n" % (NEW['ru'], NEW['uk'])


def build(source):
    text = source.decode('utf-8')
    if text.count(BEFORE) != 1 or NEW['uk'] in text:
        raise ValueError('METADATA_HOME_TITLE')
    return text.replace(BEFORE, AFTER).encode('utf-8')
