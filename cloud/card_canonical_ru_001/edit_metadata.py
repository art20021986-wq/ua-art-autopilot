"""ua_seo_metadata.py (CARD-CANONICAL-RU-001): a new SEO_REVISION, so the CRM public sync republishes every card
once with the new canonical. Nothing else changes; the line must occur exactly once."""
import re

NAME = 'ua_seo_metadata.py'
REVISION = re.compile(r"^SEO_REVISION = '[A-Z0-9-]+'$", re.M)
NEW = "SEO_REVISION = 'CARD-CANONICAL-RU-001'"


def build(source):
    text = source.decode('utf-8')
    text, count = REVISION.subn(NEW, text)
    if count != 1 or text.count(NEW) != 1:
        raise ValueError('METADATA_REVISION')
    return text.encode('utf-8')
