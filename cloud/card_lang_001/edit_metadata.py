"""ua_seo_metadata.normalize (the last SEO step of every card write), CARD-LANG-001.

A card's canonical points to its Ukrainian version (/video/ua/UA-XXXX.html) once both language versions
exist (ua_card_lang.canonical); until then it stays the card itself, as now. SEO_REVISION is raised, which
is how this module asks the CRM public sync to republish every card with the new output.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'ua_seo_metadata.py'
ANCHOR = "    if is_card:\n        edits += replace_or_insert(doc, 'script', schema.SCRIPT_ID, 'head', card_schema(facts))\n"
EDITS = (
    ("SEO_REVISION = 'SEO-GROWTH-001'\n", "SEO_REVISION = 'CARD-LANG-001'\n"),
    (ANCHOR,
     "    if is_card:\n"
     "        # CARD-LANG-001: the canonical of a card with language versions is its Ukrainian version.\n"
     "        from ua_card_lang import canonical as card_canonical, root_of\n"
     "        href = card_canonical(name, root_of(file_name))\n"
     "        for node in doc.select('link'):\n"
     "            if 'canonical' in (node['attrs'].get('rel') or '').lower().split():\n"
     "                edits.append((node['start'], node['end'], '<link rel=\"canonical\" href=\"%s\">' % href))\n"
     + ANCHOR),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('METADATA_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
