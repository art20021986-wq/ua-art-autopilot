"""ua_seo_metadata.normalize (SEO-CONTENT-001): a card's diagnostics page stays out of search on its own.

UA-XXXX-diag.html gets <meta name="robots" content="noindex,follow">: visitors still open it from the card, links
are followed, but Google does not list the thin photo page next to the card. SEO_REVISION is raised, so the CRM
public sync republishes the cards (and their diagnostics pages) with it.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'ua_seo_metadata.py'
EDITS = (
    ("SEO_REVISION = 'CARD-LANG-001'\n", "SEO_REVISION = 'SEO-CONTENT-001'\n"),
    ("    if name not in CORE and not is_card:\n        return source\n",
     "    if name not in CORE and not is_card:\n"
     "        # SEO-CONTENT-001: a card's diagnostics page stays for visitors, out of search on its own.\n"
     "        if re.fullmatch(r'UA-[0-9]{4,}-diag\\.html', name, re.I) and 'name=\"robots\"' not in source:\n"
     "            return re.sub(r'</head\\s*>', '<meta name=\"robots\" content=\"noindex,follow\"></head>', source,\n"
     "                          count=1, flags=re.I)\n"
     "        return source\n"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('METADATA_FRAGMENT_NOT_UNIQUE:' + old[:40])
        text = text.replace(old, new)
    return text.encode('utf-8')
