"""PAY-LABELS-001 (owner 2026-11-17, SEO-AUDIT-20261116 step 3 «Да»): which deal each payment sum belongs to.

600 $ service + 1 000 $ prepayment — buying at a Korean auction; 500 $ prepayment — a car in stock or on the way.
The sums do not change; only the deal is named. One place for the approved texts and the exact edits per file.
Every old fragment must occur exactly once and no new one may be there yet; nothing else in a file changes.
"""
import json

# The owner-approved wording (ru / uk); Georgian follows the site's existing Georgian for the same lines.
HOME_NOTE = {
    'ru': ('Предоплата 1 000 $ засчитывается в стоимость авто.',
           ' Эти суммы — для покупки с аукциона. Для авто в наличии или в пути предоплата — 500 $.'),
    'uk': ('Передоплата 1 000 $ зараховується у вартість авто.',
           ' Ці суми — для купівлі з аукціону. Для авто в наявності чи в дорозі передоплата — 500 $.'),
    'ka': ('წინასწარი გადახდა 1 000 $ ჩაითვლება ავტომობილის ღირებულებაში.',
           ' ეს თანხები აუქციონზე ყიდვისთვისაა. მარაგში არსებული ან გზაში მყოფი ავტომობილისთვის წინასწარი გადახდა — 500 $.'),
}
KOREA_FAQ = {
    'uk': ('Передоплата — від 1 000 $. Вона зараховується у вартість авто.',
           'При купівлі з аукціону передоплата — від 1 000 $. Вона зараховується у вартість авто. '
           'Окремо — послуга супроводу 600 $.'),
    'ru': ('Предоплата — от 1 000 $. Она засчитывается в стоимость авто.',
           'При покупке с аукциона предоплата — от 1 000 $. Она засчитывается в стоимость авто. '
           'Отдельно — услуга сопровождения 600 $.'),
}
# Conditions page (stranica.sobrat_info, Russian; Ukrainian and Georgian from the site dictionary): ru, uk, ka.
INFO = (
    (('Предоплата 500 $ входит в стоимость автомобиля',
      'Предоплата 500 $ за автомобиль в наличии или в пути входит в его стоимость'),
     ('Передоплата 500 $ входить у вартість автомобіля',
      'Передоплата 500 $ за авто в наявності чи в дорозі входить у його вартість'),
     ('500 $ წინასწარი გადახდა შედის ავტომობილის ღირებულებაში',
      '500 $ წინასწარი გადახდა მარაგში არსებული ან გზაში მყოფი ავტომობილისთვის შედის მის ღირებულებაში')),
    (('Заключаем официальный договор. Предоплата — 500 $, она входит в общую стоимость автомобиля. Цена автомобиля '
      'фиксируется в договоре по курсу НБУ на дату его заключения.',
      'Заключаем официальный договор. Предоплата за автомобиль в наличии или в пути — 500 $, она входит в общую '
      'стоимость автомобиля. Цена автомобиля фиксируется в договоре по курсу НБУ на дату его заключения.'),
     ('Укладаємо офіційний договір. Передоплата — 500 $, вона входить у загальну вартість автомобіля. Ціна автомобіля '
      'фіксується в договорі за курсом НБУ на дату його укладення.',
      'Укладаємо офіційний договір. Передоплата за авто в наявності чи в дорозі — 500 $, вона входить у загальну '
      'вартість автомобіля. Ціна автомобіля фіксується в договорі за курсом НБУ на дату його укладення.'),
     ('ვაფორმებთ ოფიციალურ ხელშეკრულებას. წინასწარი გადახდა — 500 $, რომელიც შედის ავტომობილის მთლიან ღირებულებაში. '
      'ავტომობილის ფასი ფიქსირდება ხელშეკრულებაში უკრაინის ეროვნული ბანკის კურსით, ხელშეკრულების გაფორმების თარიღისთვის.',
      'ვაფორმებთ ოფიციალურ ხელშეკრულებას. წინასწარი გადახდა მარაგში არსებული ან გზაში მყოფი ავტომობილისთვის — 500 $, '
      'რომელიც შედის ავტომობილის მთლიან ღირებულებაში. ავტომობილის ფასი ფიქსირდება ხელშეკრულებაში უკრაინის ეროვნული '
      'ბანკის კურსით, ხელშეკრულების გაფორმების თარიღისთვის.')),
    (('Предоплата 500 $ при бронировании — входит в цену. Остальное по договору, до выдачи в Киеве.',
      'Предоплата 500 $ при бронировании — входит в цену. Остальное по договору, до выдачи в Киеве. При покупке с '
      'аукциона Кореи — услуга 600 $ и предоплата 1 000 $, она засчитывается в стоимость авто.'),
     ('Передоплата 500 $ під час бронювання — входить у ціну. Решта за договором, до видачі в Києві.',
      'Передоплата 500 $ під час бронювання — входить у ціну. Решта за договором, до видачі в Києві. При купівлі з '
      'аукціону Кореї — послуга 600 $ і передоплата 1 000 $, вона зараховується у вартість авто.'),
     ('დაჯავშნისას წინასწარი გადახდა 500 $ — შედის ფასში. დარჩენილი თანხა გადაიხდება ხელშეკრულების მიხედვით, კიევში '
      'ჩაბარებამდე.',
      'დაჯავშნისას წინასწარი გადახდა 500 $ — შედის ფასში. დარჩენილი თანხა გადაიხდება ხელშეკრულების მიხედვით, კიევში '
      'ჩაბარებამდე. კორეის აუქციონიდან შესყიდვისას — მომსახურება 600 $ და წინასწარი გადახდა 1 000 $, რომელიც '
      'ჩაითვლება ავტომობილის ღირებულებაში.')),
)


def _home():
    (ru, ru_add), (uk, uk_add), (ka, ka_add) = HOME_NOTE['ru'], HOME_NOTE['uk'], HOME_NOTE['ka']
    old = 'data-ru="%s" data-uk="%s" data-ka="%s">%s</p>' % (ru, uk, ka, uk)
    new = 'data-ru="%s" data-uk="%s" data-ka="%s">%s</p>' % (ru + ru_add, uk + uk_add, ka + ka_add, uk + uk_add)
    return ((old, new),)


def _korea():
    (uk, uk_new), (ru, ru_new) = KOREA_FAQ['uk'], KOREA_FAQ['ru']
    return (('<span data-uk="%s" data-ru="%s">%s</span>' % (uk, ru, uk),
             '<span data-uk="%s" data-ru="%s">%s</span>' % (uk_new, ru_new, uk_new)),)


def _source(text):
    """The Russian line as stranica.py writes it: the 500 $ comes from BRON_USD."""
    return text.replace('500 $', '%d $')


def _stranica():
    (first, second, third) = INFO
    return (('"%s" %% BRON_USD' % _source(first[0][0]), '"%s" %% BRON_USD' % _source(first[0][1])),
            ('"%s" %% BRON_USD' % _source(second[0][0]), '"%s" %% BRON_USD' % _source(second[0][1])),
            ('"%s" %% BRON_USD' % _source(third[0][0]), '"%s" %% BRON_USD' % _source(third[0][1])))


def _info():
    return tuple((line[0][0], line[0][1]) for line in INFO)


def _pair(key, value):
    return '%s:%s' % (json.dumps(key, ensure_ascii=False), json.dumps(value, ensure_ascii=False))


def _languages():
    edits = []
    for (ru_old, ru_new), uk, ka in INFO:
        for old, new in (uk, ka):
            edits.append((_pair(ru_old, old), _pair(ru_new, new)))
    return tuple(edits)


EDITS = {
    'video/index.html': _home(),
    'video/korea.html': _korea(),
    'video/info.html': _info(),
    'stranica.py': _stranica(),
    'video/ua-site-languages.js': _languages(),
}
FILES = tuple(EDITS)
# Pages a site writer may rewrite after the install; they keep the new texts when it does.
PAGES = ('video/index.html', 'video/korea.html', 'video/info.html')


def apply(name, text):
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('PAY_LABELS_FRAGMENT:%s:%d:%s' % (name, text.count(old), old[:50]))
        text = text.replace(old, new)
    return text


def has_labels(name, text):
    """The new texts are there (an old line may be the start of its longer new line)."""
    return all(new in text for _, new in EDITS[name])
