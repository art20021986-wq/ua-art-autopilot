"""Build the KOREA-META candidate: the Korea page description names the 1 000 $ prepayment (owner 2026-11-12, «А»).

The deposit block left the page (KOREA-TERMS-001); its search description still said «Депозит 2000 $ входить у
вартість авто». That sentence becomes «Передоплата 1 000 $ зараховується у вартість авто» in the Ukrainian, Russian
and Georgian description values of the <meta name="description"> tag (the wording of SERVICE-WORDS-001).
Nothing else in video/korea.html changes.
"""
import re

PAGE = 'video/korea.html'
SOURCE_FILES = (PAGE,)
DEPENDENCY_SHA256 = {}
META = re.compile(r'<meta name="description"[^>]*>')
REPLACE = (('Депозит 2000 $ входить у вартість авто.', 'Передоплата 1 000 $ зараховується у вартість авто.'),
           ('Депозит 2000 $ входит в стоимость авто.', 'Предоплата 1 000 $ засчитывается в стоимость авто.'),
           ('დეპოზიტი 2000 $ შედის ავტომობილის ღირებულებაში.',
            'წინასწარი გადახდა 1 000 $ ჩაითვლება ავტომობილის ღირებულებაში.'))
SENTENCES = tuple(old for old, new in REPLACE)


def apply(page):
    tags = META.findall(page)
    if len(tags) != 1 or not any(s in tags[0] for s in SENTENCES):
        raise ValueError('KOREA_META_PAGE_UNEXPECTED')
    tag = tags[0]
    for old, new in REPLACE:
        tag = tag.replace(old, new)
    return page.replace(tags[0], tag, 1)


def build(source, dependencies):
    return {PAGE: apply(source[PAGE].decode('utf-8')).encode('utf-8')}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
