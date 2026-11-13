"""The AUTO.RIA button wording AUTO.RIA asked for (their message to the owner, 2026-11-13; owner via the coordinator).

The home page reviews button (a.ua-reviews-button, AUTORIA-REVIEWS-001) says «Усі відгуки та продані авто». AUTO.RIA
asked for «Дивіться всі авто та відгуки від UA ART COMPANY на AUTO.RIA». apply(html) replaces the old wording (the
visible text and the data-uk/data-ru/data-ka strings the language switch uses) with the new one; revert(html) does the
opposite (rollback of a page another writer rewrote). Nothing else on the page changes.
"""

# (old, new) for each language; the uk text is AUTO.RIA's own, ru/ka say the same.
TEXTS = (
    ('Усі відгуки та продані авто', 'Дивіться всі авто та відгуки від UA ART COMPANY на AUTO.RIA'),
    ('Все отзывы и проданные авто', 'Смотрите все авто и отзывы UA ART COMPANY на AUTO.RIA'),
    ('ყველა შეფასება და გაყიდული ავტომობილი', 'ნახეთ UA ART COMPANY-ის ყველა ავტომობილი და შეფასება AUTO.RIA-ზე'),
)


def _swap(html, pairs):
    if not isinstance(html, str):
        return html
    for old, new in pairs:
        html = html.replace('"%s"' % old, '"%s"' % new).replace('>%s<' % old, '>%s<' % new)
    return html


def apply(html):
    """The page with AUTO.RIA's wording (attribute values and element text only); unchanged if it has none of it."""
    return _swap(html, TEXTS)


def revert(html):
    """The page with the previous wording back."""
    return _swap(html, tuple((new, old) for old, new in TEXTS))
