"""ua_card_lang.py (CARD-CANONICAL-RU-001): the old card page /video/UA-XXXX.html names its Russian version
/video/ru/UA-XXXX.html as canonical, not the Ukrainian one.

The old page is Russian and the Russian version is the same text; Google ignores a canonical to a page in another
language (Search Central: localized versions, consolidate duplicate URLs), chose the old page and marked the
versions «copy, Google chose another canonical» (GSC 2026-11-06/09). Without both versions the card stays its own
canonical, as now. The original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'ua_card_lang.py'
OLD = ('    """The canonical URL of a card: its Ukrainian version once it exists, else the card itself."""\n'
       "    if (Path(root)/DIRS['uk']/name).is_file() and (Path(root)/DIRS['ru']/name).is_file():\n"
       "        return '%s/video/%s/%s' % (ORIGIN, DIRS['uk'], name)\n")
NEW = ('    """The canonical URL of a card: its Russian version (the same language and text) once both versions\n'
       '    exist, else the card itself (CARD-CANONICAL-RU-001)."""\n'
       "    if (Path(root)/DIRS['uk']/name).is_file() and (Path(root)/DIRS['ru']/name).is_file():\n"
       "        return '%s/video/%s/%s' % (ORIGIN, DIRS['ru'], name)\n")


def build(source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or 'CARD-CANONICAL-RU-001' in text:
        raise ValueError('CARD_LANG_FRAGMENT')
    return text.replace(OLD, NEW).encode('utf-8')
