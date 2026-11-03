"""Finance partners of UA ART and the texts of the finance page (FINANCE-001). Pure data, no logic.

Installed as ua_finance_partners.py. The finance landing page (ua_seo_finance), the order page and car card
buttons and the CRM bot screen (ua_finance_crm) all read this one list: a new lender or credit offer is a
new PARTNERS entry, no code change. Partner facts come from the partner (owner 2026-11-03) and its official
site hapai.kiev.ua; exact terms are always the partner's own calculation.
"""
# The page: /video/seo/<ua|ru>/<slug>.html, made by ua_seo_landings like the other landing pages.
SLUG = {'uk': 'kredyt-lizynh-avto', 'ru': 'kredit-lizing-avto'}
DIRS = {'uk': 'ua', 'ru': 'ru'}
# The button on the order page and on every car card (uk/ru/ka; ka opens the Ukrainian page).
BUTTON = {'uk': 'Кредити та лізинг', 'ru': 'Кредиты и лизинг', 'ka': 'კრედიტი და ლიზინგი'}
KINDS = {'leasing': {'uk': 'Лізинг', 'ru': 'Лизинг'}, 'credit': {'uk': 'Кредит', 'ru': 'Кредит'}}

PARTNERS = (
    dict(id='hapai-leasing', kind='leasing', name='ХАПАЙ Авто', site='https://hapai.kiev.ua/',
         lender={'uk': 'ТОВ «УЛФ-Фінанс»', 'ru': 'ООО «УЛФ-Финанс»'},
         # The partner's link for UA ART (its Telegram bot counts visits for the partner's CRM): never change it.
         href='https://t.me/ulf_agent_bot?start=387da37d-92d7-4a21-8c69-13c14030906d=site',
         logo='/video/finance/hapai-lizing.png', logo_size=(480, 66), logo_alt='ХАПАЙ лізинг',
         uk=dict(terms=('Аванс від 20%', 'Паспорт та ІПН', 'Розрахунок у Telegram'), cta='Розрахувати лізинг'),
         ru=dict(terms=('Аванс от 20%', 'Паспорт и ИНН', 'Расчёт в Telegram'), cta='Рассчитать лизинг')),
)

PAGE = {
    'uk': dict(
        title='Кредит і лізинг авто в Києві — аванс від 20% | UA ART',
        desc='Авто з каталогу UA ART або під замовлення в лізинг: аванс від 20%, розрахунок платежу онлайн у '
             'партнера ХАПАЙ Авто (лізингодавець ТОВ «УЛФ-Фінанс»). Паспорт та ІПН.',
        h1='Кредит і лізинг авто',
        intro='Купуйте авто з каталогу UA ART або під замовлення частинами. Розрахунок робить партнер напряму: '
              'натисніть «Розрахувати лізинг» — відкриється бот партнера в Telegram.',
        partners='Партнери', crumb='Кредит і лізинг',
        lender='Лізингодавець', how='Як це працює',
        steps=('Оберіть авто в каталозі UA ART або під замовлення.',
               'Натисніть «Розрахувати лізинг» — бот партнера в Telegram розрахує платіж.',
               'Партнер погоджує умови й укладає з вами договір.'),
        faq=(('Хто надає лізинг?',
              'Лізинг надає партнер ХАПАЙ Авто, лізингодавець — ТОВ «УЛФ-Фінанс». Договір лізингу ви укладаєте з лізингодавцем.'),
             ('Який мінімальний аванс?', 'Від 20% вартості авто. Точний платіж і строк розраховує партнер.'),
             ('Які документи потрібні?', 'Для розрахунку — паспорт та ІПН. Партнер може попросити додаткові документи.'),
             ('Як розрахувати платіж?',
              'Натисніть «Розрахувати лізинг»: бот партнера в Telegram розрахує платіж для вашого авто.')),
        note='Умови лізингу визначає й розраховує партнер; UA ART не є фінансовою установою.',
        catalog='Каталог авто', order='Авто під замовлення'),
    'ru': dict(
        title='Кредит и лизинг авто в Киеве — аванс от 20% | UA ART',
        desc='Авто из каталога UA ART или под заказ в лизинг: аванс от 20%, расчёт платежа онлайн у партнёра '
             'ХАПАЙ Авто (лизингодатель ООО «УЛФ-Финанс»). Паспорт и ИНН.',
        h1='Кредит и лизинг авто',
        intro='Покупайте авто из каталога UA ART или под заказ частями. Расчёт делает партнёр напрямую: '
              'нажмите «Рассчитать лизинг» — откроется бот партнёра в Telegram.',
        partners='Партнёры', crumb='Кредит и лизинг',
        lender='Лизингодатель', how='Как это работает',
        steps=('Выберите авто в каталоге UA ART или под заказ.',
               'Нажмите «Рассчитать лизинг» — бот партнёра в Telegram рассчитает платёж.',
               'Партнёр согласует условия и заключает с вами договор.'),
        faq=(('Кто предоставляет лизинг?',
              'Лизинг предоставляет партнёр ХАПАЙ Авто, лизингодатель — ООО «УЛФ-Финанс». Договор лизинга вы заключаете с лизингодателем.'),
             ('Какой минимальный аванс?', 'От 20% стоимости авто. Точный платёж и срок рассчитывает партнёр.'),
             ('Какие документы нужны?', 'Для расчёта — паспорт и ИНН. Партнёр может попросить дополнительные документы.'),
             ('Как рассчитать платёж?',
              'Нажмите «Рассчитать лизинг»: бот партнёра в Telegram рассчитает платёж для вашего авто.')),
        note='Условия лизинга определяет и рассчитывает партнёр; UA ART не является финансовым учреждением.',
        catalog='Каталог авто', order='Авто под заказ'),
}


def page_path(lang):
    """Site path of the finance page; Georgian visitors get the Ukrainian page."""
    lang = lang if lang in SLUG else 'uk'
    return '/video/seo/%s/%s.html' % (DIRS[lang], SLUG[lang])


def partner(partner_id):
    return next((p for p in PARTNERS if p['id'] == partner_id), None)
