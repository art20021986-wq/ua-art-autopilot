"""The Korea page offer line (KOREA-OFFER block) gets the new text (SEARCH-HOME-001, owner «Да» 2026-11-26 12:30 UTC).

Only this line changes: its three language twins and the visible Ukrainian text; the button and every other byte stay.
"""
from html import escape

OLD = {'uk': 'Авто з Кореї під ключ · послуга 600 $ · договір',
       'ru': 'Авто из Кореи под ключ · услуга 600 $ · договор',
       'ka': 'ავტომობილი კორეიდან სრული მომსახურებით · მომსახურება 600 $ · ხელშეკრულება'}
NEW = {'uk': 'Авто з усіх країн під ключ · послуга 600 $ за договором · інші витрати — за рахунками аукціонів і перевізників',
       'ru': 'Авто из всех стран под ключ · услуга 600 $ по договору · остальные расходы — по счетам аукционов и перевозчиков',
       'ka': 'ავტომობილები ყველა ქვეყნიდან სრული მომსახურებით · მომსახურება 600 $ ხელშეკრულებით · დანარჩენი ხარჯები — აუქციონებისა და გადამზიდავების ანგარიშებით'}


def _line(texts):
    return 'data-uk="%s" data-ru="%s" data-ka="%s">%s</div>' % (
        escape(texts['uk']), escape(texts['ru']), escape(texts['ka']), escape(texts['uk']))


def build(value):
    """korea.html bytes -> the same with the new offer line."""
    source = value.decode('utf-8')
    old = _line(OLD)
    if source.count(old) != 1 or source.count('id="ua-korea-offer"') != 1:
        raise ValueError('KOREA_OFFER_LAYOUT')
    return source.replace(old, _line(NEW), 1).encode('utf-8')
