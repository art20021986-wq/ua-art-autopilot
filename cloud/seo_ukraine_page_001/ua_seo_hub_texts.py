"""Owner-approved text sections of the Korea hub and the custom-order page (SEO-PLAN-003 item 2, 2026-11-08).

Data and plain rendering only: ua_seo_landings places the sections and passes `link(key)` for a page's address,
so this module knows nothing about paths. Texts: cloud/seo_plan_003/texts_hubs.md, approved by the owner.
"""
from html import escape

import ua_seo_ukraine_page  # SEO-UKRAINE-PAGE-001: the all-Ukraine page link text

LPI = 'lpi'  # ua_seo_order_models.TOPICS key of the factory-gas page
UKRAINE = 'ukraine'  # ua_seo_order_models.TOPICS key of the all-Ukraine page
K5, SONATA = ('Kia', 'K5'), ('Hyundai', 'Sonata')
CROSSOVERS = (('Hyundai', 'Tucson'), ('Kia', 'Sportage'), ('Hyundai', 'Santa Fe'))

TEXTS = {
    'uk': dict(
        why_title='Чому обирають UA ART',
        why=('Понад 5 років возимо авто з Кореї. На AUTO.RIA — 132 продані авто і 18 відгуків.',
             'У кожного авто є своя сторінка: фото, відео, VIN і етап доставки.',
             'Ціна під ключ фіксується в договорі й не змінюється: викуп, доставка, розмитнення, сертифікація та всі платежі.',
             'Можна купити в кредит (ОТП Банк) або в лізинг (ХАПАЙ Авто).',
             'Авто, що вже в Києві, можна оглянути в офісі: вул. Перемоги, 20.'),
        models_title='Які авто найчастіше замовляють з Кореї',
        sedans='{k5} і {sonata} — є версії на {lpi}: економні на щодень.', lpi='заводському газу (LPi)',
        crossovers='{models} — кросовери, часто з дизелем.', other='Будь-яку іншу модель підберемо під ваш бюджет.',
        check_title='Як ми перевіряємо авто до покупки',
        check=('Дивимося звіт аукціону: оцінка кузова, салону й технічного стану.',
               "За потреби перевіряємо лакофарбове покриття, робимо комп'ютерну діагностику й технічний огляд."),
        steps_title='Як проходить замовлення',
        steps=('Безкоштовна консультація: модель, бюджет, країна.',
               'Підбираємо варіанти й перевіряємо історію та звіт аукціону.',
               'Договір: ціна під ключ фіксується, депозит 500 $ входить у вартість.',
               'Викуп, доставка, розмитнення та сертифікація — все робимо ми.',
               'Видача авто в Києві.'),
        faq=(('Чи можна купити авто під замовлення в кредит?',
              'Так: кредит від ОТП Банку або лізинг від ХАПАЙ Авто — деталі на сторінці «Кредит і лізинг».'),
             ('Чи будуть доплати після договору?',
              'Ні. Ціна під ключ фіксується в договорі й включає всі платежі.'),
             ('Скільки коштує консультація?', 'Безкоштовно.'))),
    'ru': dict(
        why_title='Почему выбирают UA ART',
        why=('Более 5 лет возим авто из Кореи. На AUTO.RIA — 132 проданных авто и 18 отзывов.',
             'У каждого авто есть своя страница: фото, видео, VIN и этап доставки.',
             'Цена под ключ фиксируется в договоре и не меняется: выкуп, доставка, растаможка, сертификация и все платежи.',
             'Можно купить в кредит (ОТП Банк) или в лизинг (ХАПАЙ Авто).',
             'Авто, которые уже в Киеве, можно осмотреть в офисе: ул. Победы, 20.'),
        models_title='Какие авто чаще всего заказывают из Кореи',
        sedans='{k5} и {sonata} — есть версии на {lpi}: экономичные на каждый день.', lpi='заводском газе (LPi)',
        crossovers='{models} — кроссоверы, часто с дизелем.', other='Любую другую модель подберём под ваш бюджет.',
        check_title='Как мы проверяем авто до покупки',
        check=('Смотрим отчёт аукциона: оценка кузова, салона и технического состояния.',
               'При необходимости проверяем лакокрасочное покрытие, делаем компьютерную диагностику и технический осмотр.'),
        steps_title='Как проходит заказ',
        steps=('Бесплатная консультация: модель, бюджет, страна.',
               'Подбираем варианты и проверяем историю и отчёт аукциона.',
               'Договор: цена под ключ фиксируется, депозит 500 $ входит в стоимость.',
               'Выкуп, доставка, растаможка и сертификация — всё делаем мы.',
               'Выдача авто в Киеве.'),
        faq=(('Можно ли купить авто под заказ в кредит?',
              'Да: кредит от ОТП Банка или лизинг от ХАПАЙ Авто — подробности на странице «Кредит и лизинг».'),
             ('Будут ли доплаты после договора?',
              'Нет. Цена под ключ фиксируется в договоре и включает все платежи.'),
             ('Сколько стоит консультация?', 'Бесплатно.'))),
}
ORDER_FAQ = {lang: t['faq'] for lang, t in TEXTS.items()}


def _a(href, text):
    return '<a href="%s">%s</a>' % (escape(href), escape(text))


def _ukraine(lang, link):
    return '<p>%s</p>' % _a(link(UKRAINE), ua_seo_ukraine_page.TOPIC[lang]['link'])


def _list(title, items, tag='ul'):
    return '<h2>%s</h2><%s>%s</%s>' % (escape(title), tag, ''.join('<li>%s</li>' % i for i in items), tag)


def hub(lang, link):
    """«Why UA ART», «most ordered models» (linked) and «how we check» for the Korea hub."""
    t = TEXTS[lang]
    name = lambda key: _a(link(key), '%s %s' % key)
    models = (t['sedans'].format(k5=name(K5), sonata=name(SONATA), lpi=_a(link(LPI), t['lpi'])),
              t['crossovers'].format(models=', '.join(name(k) for k in CROSSOVERS)), escape(t['other']))
    return (_list(t['why_title'], [escape(x) for x in t['why']]) + _list(t['models_title'], models)
            + _list(t['check_title'], [escape(x) for x in t['check']]) + _ukraine(lang, link))


def order_steps(lang, link=None):
    """«How ordering works» for the custom-order page, and the link to the all-Ukraine page when link is given."""
    t = TEXTS[lang]
    return _list(t['steps_title'], [escape(x) for x in t['steps']], 'ol') + (_ukraine(lang, link) if link else '')
