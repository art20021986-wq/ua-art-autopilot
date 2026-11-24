"""ua_seo_metadata.py (SEO-FIX-20261121, answer 3): normalize treats katalog.html and info.html as Ukrainian, as it does
the order page: lang="uk" on <html> and the Ukrainian title, description and og texts at every later publication.
The two original fragments must occur exactly once; an applied edit is refused."""
NAME = 'ua_seo_metadata.py'
PAIRS = (
    ("    if name == 'podbor.html' and 'id=\"ua-order\"' in source:\n"
     "        lang = 'uk'  # The server-rendered order form is Ukrainian.\n",
     "    if name == 'podbor.html' and 'id=\"ua-order\"' in source:\n"
     "        lang = 'uk'  # The server-rendered order form is Ukrainian.\n"
     "    if name in ('katalog.html', 'info.html'):\n"
     "        lang = 'uk'  # SEO-FIX-20261121: shown in Ukrainian by default; the switcher keeps the Russian text.\n"),
    ("    if name == 'podbor.html' and html and lang == 'uk':\n",
     "    if name in ('podbor.html', 'katalog.html', 'info.html') and html and lang == 'uk':\n"),
)


def build(source):
    text = source.decode('utf-8')
    if 'SEO-FIX-20261121' in text or any(text.count(old) != 1 for old, _ in PAIRS):
        raise ValueError('METADATA_FRAGMENT')
    for old, new in PAIRS:
        text = text.replace(old, new)
    return text.encode('utf-8')
