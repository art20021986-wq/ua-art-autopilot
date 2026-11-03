"""ua_card_lang (FINANCE-001 stage 4): a link may name its Ukrainian address with data-uk-href.

The Ukrainian card version already takes title/alt/aria-label/placeholder from data-uk-<attribute>; href joins
that list, so the card's finance link opens the Ukrainian finance page from the Ukrainian card and the
Russian one from the Russian card. Other links have no data-uk-href and stay as they are.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'ua_card_lang.py'
OLD = "ATTRIBUTES = {'title': 'title', 'aria-label': 'aria', 'placeholder': 'placeholder', 'alt': 'alt', 'content': 'content'}\n"
NEW = ("ATTRIBUTES = {'title': 'title', 'aria-label': 'aria', 'placeholder': 'placeholder', 'alt': 'alt', 'content': 'content',\n"
       "              'href': 'href'}  # FINANCE-001: data-uk-href\n")


def build(source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or NEW in text:
        raise ValueError('CARD_LANG_FRAGMENT')
    return text.replace(OLD, NEW).encode('utf-8')
