"""The Kyiv Search campaign as data (R2: Google flagged CAPITALIZATION — «LPi» and «AUTO.RIA» removed from ad texts) (owner 2026-11-25: Kyiv city and oblast first, «минимальная стоимость лида»;
«Да»: 1 lead in 10 becomes a contract, ads 9:00–20:00, prepayment 1 000 $). Pure: no network.

One campaign, PAUSED; Kyiv city + Kyiv Oblast, people located there only; Ukrainian and Russian; every day 9:00–20:00;
Google Search only; Maximize clicks with a 25 UAH click ceiling; 500 UAH a day budget (spends nothing while paused).
Each ad group = one search intent → its own landing page (uk or ru), phrase + exact match.
"""
SITE = 'https://www.uaart.com.ua/video/'
NAME = 'Пошук — Київ — Корея (UA ART)'
BUDGET_UAH = 500
CPC_CEILING_UAH = 25
LOCATIONS = ('geoTargetConstants/21118', 'geoTargetConstants/21580')  # Kyiv city, Kyiv Oblast
LANGUAGES = ('languageConstants/1036', 'languageConstants/1031')  # Ukrainian, Russian
DAYS = ('MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY')
HOURS = (9, 20)
NEGATIVE = ['запчастини', 'запчасти', 'розборка', 'разборка', 'ремонт', 'шини', 'шины', 'оренда', 'аренда', 'вакансія',
            'вакансия', 'робота', 'работа', 'огляд', 'обзор', 'відгуки власників', 'отзывы владельцев', 'olx', 'auto ria',
            'авторіа', 'автория', 'безкоштовно', 'бесплатно', 'своїми руками', 'своими руками', 'росія', 'россия',
            'бу в києві', 'бу в киеве', 'характеристики', 'розмір', 'размер', 'тюнінг', 'тюнинг', 'іграшка', 'игрушка',
            'фото', 'картинки', 'малюнок', 'рисунок', 'інструкція', 'инструкция', 'форум', 'wiki', 'вікі', 'вики']

UK_HEAD = ['Пригон авто з Кореї', 'Послуга — 600 $', 'Ціна фіксується в договорі', 'Офіс у Києві, Перемоги 20',
           'VIN, фото, відео, діагностика', 'Передоплата в ціні авто', 'Понад 5 років досвіду',
           'Понад 130 проданих авто', 'Етап доставки онлайн', 'Кредит і лізинг', 'Отримайте пропозицію',
           'Офіційний договір']
UK_DESC = ['Купуємо на аукціоні Кореї, перевіряємо й робимо пригон під ключ до Києва.',
           'Фіксована послуга 600 $. Ціна під ключ у договорі: викуп, доставка, розмитнення.',
           'Фото, відео, VIN і етап доставки кожного авто. Огляд в офісі на Перемоги, 20.',
           'Залиште заявку — менеджер напише у Viber або Telegram.']
RU_HEAD = ['Пригон авто из Кореи', 'Услуга — 600 $', 'Цена фиксируется в договоре', 'Офис в Киеве, Победы 20',
           'VIN, фото, видео, диагностика', 'Предоплата в цене авто', 'Более 5 лет опыта', 'Более 130 проданных авто',
           'Этап доставки онлайн', 'Кредит и лизинг', 'Получите предложение', 'Официальный договор']
RU_DESC = ['Покупаем на аукционе Кореи, проверяем и делаем пригон под ключ в Киев.',
           'Фиксированная услуга 600 $. Цена под ключ в договоре: выкуп, доставка, растаможка.',
           'Фото, видео, VIN и этап доставки каждого авто. Осмотр в офисе на Победы, 20.',
           'Оставьте заявку — менеджер напишет в Viber или Telegram.']

# (key, lang, first headlines, keywords, landing page, path1, path2)
MODELS = [
    ('kia-k5', 'Kia K5', ['kia k5', 'кіа к5'], ['kia k5', 'киа к5'], 'kia-k5-koreya-kyiv', 'kia-k5-koreya-kiev', 'K5 на заводському газу',
     'K5 на заводском газе', 'від 10 500 $', 'от 10 500 $'),
    ('hyundai-sonata', 'Hyundai Sonata', ['hyundai sonata', 'хюндай соната'], ['hyundai sonata', 'хендай соната',
     'хюндай соната'], 'hyundai-sonata-koreya-kyiv', 'hyundai-sonata-koreya-kiev', 'Sonata на заводському газу',
     'Sonata на заводском газе', 'від 10 000 $', 'от 10 000 $'),
    ('hyundai-tucson', 'Hyundai Tucson', ['hyundai tucson', 'хюндай туксон'], ['hyundai tucson', 'хендай туксон',
     'туссан'], 'hyundai-tucson-koreya-kyiv', 'hyundai-tucson-koreya-kiev', 'Tucson дизель', 'Tucson дизель', '', ''),
    ('kia-sportage', 'Kia Sportage', ['kia sportage', 'кіа спортейдж'], ['kia sportage', 'киа спортейдж'],
     'kia-sportage-koreya-kyiv', 'kia-sportage-koreya-kiev', 'Sportage дизель', 'Sportage дизель', '', ''),
    ('hyundai-santa-fe', 'Hyundai Santa Fe', ['hyundai santa fe', 'хюндай санта фе'], ['hyundai santa fe',
     'хендай санта фе', 'санта фе'], 'hyundai-santa-fe-koreya-kyiv', 'hyundai-santa-fe-koreya-kiev',
     'Santa Fe дизель', 'Santa Fe дизель', '', ''),
]


def groups():
    """[{name, url, keywords, headlines, descriptions, path}] — every ad group of the campaign."""
    found = [
        {'name': 'UA — Корея під ключ', 'url': SITE + 'seo/ua/avto-z-korei-do-kyieva-pid-kluch.html',
         'keywords': ['авто з кореї під ключ', 'авто з кореї', 'пригон авто з кореї', 'авто з кореї під замовлення',
                      'авто з кореї київ', 'купити авто з кореї', 'авто з кореї ціни', 'авто з кореї під ключ київ'],
         'headlines': ['Авто з Кореї під ключ', 'Авто з Кореї у Києві'] + UK_HEAD, 'descriptions': UK_DESC,
         'path': ('korea', 'kyiv')},
        {'name': 'RU — Корея под ключ', 'url': SITE + 'seo/ru/avto-iz-korei-v-kiev-pod-kluch.html',
         'keywords': ['авто из кореи под ключ', 'авто из кореи', 'пригон авто из кореи', 'авто из кореи под заказ',
                      'авто из кореи киев', 'купить авто из кореи', 'авто из кореи цены', 'авто из кореи под ключ киев'],
         'headlines': ['Авто из Кореи под ключ', 'Авто из Кореи в Киеве'] + RU_HEAD, 'descriptions': RU_DESC,
         'path': ('korea', 'kiev')},
        {'name': 'UA — Аукціони Кореї', 'url': SITE + 'korea.html',
         'keywords': ['аукціон авто корея', 'аукціони кореї', 'корейські автоаукціони', 'аукціон кореї авто онлайн'],
         'headlines': ['Аукціони Кореї онлайн', 'Нові лоти щодня'] + UK_HEAD, 'descriptions': UK_DESC,
         'path': ('korea', 'auction')},
        {'name': 'RU — Аукционы Кореи', 'url': SITE + 'ru/korea.html',
         'keywords': ['аукцион авто корея', 'аукционы кореи', 'корейские автоаукционы', 'аукцион кореи авто онлайн'],
         'headlines': ['Аукционы Кореи онлайн', 'Новые лоты каждый день'] + RU_HEAD, 'descriptions': RU_DESC,
         'path': ('korea', 'auction')},
    ]
    for key, model, uk_names, ru_names, uk_page, ru_page, uk_line, ru_line, uk_price, ru_price in MODELS:
        found.append({'name': 'UA — ' + model, 'url': SITE + 'seo/ua/%s.html' % uk_page,
                      'keywords': [k % n for n in uk_names for k in ('%s з кореї', '%s з кореї під ключ', 'купити %s з кореї')],
                      'headlines': [model + ' з Кореї', uk_line] + ([uk_price.capitalize()] if uk_price else [])
                      + UK_HEAD, 'descriptions': UK_DESC, 'path': (key.split('-', 1)[1], 'korea')})
        found.append({'name': 'RU — ' + model, 'url': SITE + 'seo/ru/%s.html' % ru_page,
                      'keywords': [k % n for n in ru_names for k in ('%s из кореи', '%s из кореи под ключ', 'купить %s из кореи')],
                      'headlines': [model + ' из Кореи', ru_line] + ([ru_price.capitalize()] if ru_price else [])
                      + RU_HEAD, 'descriptions': RU_DESC, 'path': (key.split('-', 1)[1], 'korea')})
    for group in found:
        group['headlines'] = group['headlines'][:15]
    return found


SITELINKS = [('Аукціони Кореї', 'Лоти й ціни щодня', 'Ставки онлайн разом з нами', SITE + 'korea.html'),
             ('Авто в наявності', 'Огляд в офісі в Києві', 'Фото, відео, VIN', SITE + 'katalog.html'),
             ('Скільки коштує під ключ', 'Реальні ціни з каталогу', 'Що входить у вартість',
              SITE + 'seo/ua/skilky-koshtuie-avto-z-korei-pid-kliuch.html'),
             ('Авто на заводському газу', 'Kia K5 і Sonata на газу', 'Економні на щодень',
              SITE + 'seo/ua/avto-z-korei-na-gazu-lpi.html')]
CALLOUTS = ['Офіційний договір', 'Фото й відео авто', 'Діагностика', 'Офіс у Києві', 'Послуга 600 $', 'Кредит і лізинг']
PHONE = '+380992222002'
