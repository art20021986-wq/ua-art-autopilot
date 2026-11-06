"""ua_seo_metadata (LEAD-FOLDERS-001): a new SEO_REVISION, so the CRM public sync republishes every card once with
the one «Связаться с менеджером» button (ua_card_contact via the generators). Nothing else changes. The edit
refuses an unexpected revision.
"""
NAME = 'ua_seo_metadata.py'
OLD = "SEO_REVISION = 'CARD-FINANCE-002'\n"
NEW = "SEO_REVISION = 'CARD-CONTACT-001'\n"


def build(source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1:
        raise ValueError('METADATA_REVISION')
    return text.replace(OLD, NEW).encode('utf-8')
