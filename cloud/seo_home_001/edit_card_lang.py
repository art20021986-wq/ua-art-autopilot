"""ua_card_lang.py (SEO-HOME-001): the logo and «← Назад» of a card language version go to the home page.

The card goes home by script, location.href='index.html'. absolute() makes the /video/ page's attribute links
absolute for a page one folder deeper but not this script address, so /video/ua|ru/UA-XXXX.html leads to
/video/ua|ru/index.html — «Сторінку не знайдено» (checked in a browser 2026-11-19). The fragment must occur
exactly once; an applied fragment is refused.
"""
NAME = 'ua_card_lang.py'
OLD = ("    # The card gallery keeps its photo list in a script: 'foto/UA-XXXX/001.jpg'.\n"
       "    return re.sub(r'([\"\\'])foto/', r'\\1/video/foto/', source)\n")
NEW = ("    # SEO-HOME-001: the logo and «Назад» go home by script; the home page is one folder up.\n"
       "    source = source.replace(\"location.href='index.html'\", \"location.href='/video/index.html'\")\n" + OLD)


def build(source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or 'SEO-HOME-001' in text:
        raise ValueError('CARD_LANG_FRAGMENT')
    return text.replace(OLD, NEW).encode('utf-8')
