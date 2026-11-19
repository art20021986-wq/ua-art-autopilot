"""ua_seo_metadata: a new SEO_REVISION, so the CRM public sync republishes every card once with the generators'
new delivery block (KYIV-NO-TRACK-001). Nothing else changes; the revision line must occur exactly once."""
import re

NAME = 'ua_seo_metadata.py'
REVISION = 'KYIV-NO-TRACK-001'
LINE = re.compile(r"^SEO_REVISION = '([A-Z0-9-]+)'\n", re.M)


def build(source):
    text = source.decode('utf-8')
    found = LINE.findall(text)
    if len(found) != 1 or found[0] == REVISION:
        raise ValueError('METADATA_REVISION')
    return LINE.sub("SEO_REVISION = '%s'\n" % REVISION, text, count=1).encode('utf-8')
