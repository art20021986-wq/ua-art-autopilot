"""ua_seo_metadata (CARD-FINANCE-002): a new SEO_REVISION, so the CRM public sync republishes every card once with
the yellow finance link (ua_card_finance). Nothing else changes. The edit refuses an unexpected revision.
"""
NAME = 'ua_seo_metadata.py'
OLD = "SEO_REVISION = 'CARD-FINANCE-001'\n"
NEW = "SEO_REVISION = 'CARD-FINANCE-002'\n"


def build(source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1:
        raise ValueError('METADATA_REVISION')
    return text.replace(OLD, NEW).encode('utf-8')
