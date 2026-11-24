"""Published pages changed now (SEO-HOME-001): the home page title (<title>, its data-ru/uk, og:title) and the
script link home on the existing card language versions; later pages come from the edited modules."""
import re

from titles import NEW, OLD

HOME = 'video/index.html'
CARD = re.compile(r'video/(?:ua|ru)/UA-[0-9]{4,}\.html')
LINK_OLD = "location.href='index.html'"
LINK_NEW = "location.href='/video/index.html'"


def cards(root):
    """Card language versions that still carry the relative script link home."""
    found = []
    for folder in ('video/ua', 'video/ru'):
        for path in sorted((root / folder).glob('UA-*.html')):
            name = path.relative_to(root).as_posix()
            if CARD.fullmatch(name) and not path.is_symlink() and LINK_OLD in path.read_text(encoding='utf-8'):
                found.append(name)
    return tuple(found)


def home(source):
    text = source.decode('utf-8')
    if NEW['uk'] in text or NEW['ru'] in text or not all(OLD[lang] in text for lang in OLD):
        raise ValueError('HOME_TITLE_STATE')
    for lang in ('ru', 'uk'):
        text = text.replace(OLD[lang], NEW[lang])
    return text.encode('utf-8')


def card(source):
    text = source.decode('utf-8')
    if not 1 <= text.count(LINK_OLD) <= 4:
        raise ValueError('CARD_LINK_COUNT')
    return text.replace(LINK_OLD, LINK_NEW).encode('utf-8')
