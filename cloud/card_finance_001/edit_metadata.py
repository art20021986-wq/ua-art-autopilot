"""ua_seo_metadata (FINANCE-001 stage 4): every card page gets the «Кредити та лізинг» link at publication.

normalize() is the one step every card page passes through when it is written (the card builder and the
publisher both call it), so one call there reaches every card, present and future: ua_card_finance.add().
SEO_REVISION changes so the CRM public sync republishes every published card once with the link.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'ua_seo_metadata.py'
REVISION = 'CARD-FINANCE-001'
EDITS = (
    ('import ua_seo_schema as schema\n', 'import ua_seo_schema as schema\nimport ua_card_finance  # FINANCE-001\n'),
    ("SEO_REVISION = 'SEO-CONTENT-001'\n", "SEO_REVISION = '%s'\n" % REVISION),
    ('    doc = Document(source)\n    titles = doc.select(\'title\')\n',
     '    if is_card:\n        source = ua_card_finance.add(source, name)  # FINANCE-001: «Кредити та лізинг»\n'
     '    doc = Document(source)\n    titles = doc.select(\'title\')\n'),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('METADATA_FRAGMENT:' + old[:40])
        text = text.replace(old, new)
    return text.encode('utf-8')
