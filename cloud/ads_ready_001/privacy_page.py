"""The privacy policy page, published as /video/privacy.html (ADS-READY-001).

Kept as text in a Python module because the release pipeline ships only Python files. One page:
Ukrainian first, the Russian text at #ru. It describes what the site's enquiry forms and counters
actually do (order package, Google Analytics, attribution.js); the forms link here under their consent.
"""
SECTIONS = {
    'uk': ('Політика конфіденційності', 'Оновлено 30 жовтня 2026 року.', (
        ('Хто обробляє дані', 'UA ART COMPANY, Київ, вул. Перемоги, 20, телефон +380 99 222 20 02.'),
        ('Які дані', "Ім'я, номер телефону або контакт у месенджері, обрана модель і побажання до авто, які ви "
                     'вказуєте в заявці; технічні дані відвідування: сторінка та джерело переходу (рекламна мітка '
                     'Google Ads або utm).'),
        ('Навіщо', "Щоб відповісти на заявку, підготувати пропозицію та укласти договір; щоб розуміти, яка реклама "
                   'приводить клієнтів.'),
        ('Підстава', 'Ваша згода, яку ви даєте, надсилаючи заявку (Закон України «Про захист персональних даних»).'),
        ('Кому передаємо', 'Дані не продаємо. Заявки зберігаються на сервері хостингу сайту (PythonAnywhere), '
                           'повідомлення про заявку отримують наші менеджери в Telegram. Google Analytics і '
                           'Google Ads отримують дані відвідувань без імені й телефону.'),
        ('Скільки зберігаємо', 'Поки це потрібно для відповіді на заявку, договору та обліку, або доки ви не '
                               'попросите видалити дані.'),
        ('Cookie та сховище браузера', 'Сайт використовує cookie Google Analytics і власну статистику відвідувань, '
                                       'а також зберігає у вашому браузері рекламну мітку переходу на 90 днів, щоб '
                                       'заявка містила її джерело. Їх можна видалити в налаштуваннях браузера.'),
        ('Ваші права', 'Ви можете дізнатися, які ваші дані ми маємо, виправити чи видалити їх і відкликати згоду: '
                       'зателефонуйте або напишіть нам на +380 99 222 20 02. Скаргу можна подати Уповноваженому '
                       'Верховної Ради України з прав людини.'))),
    'ru': ('Политика конфиденциальности', 'Обновлено 30 октября 2026 года.', (
        ('Кто обрабатывает данные', 'UA ART COMPANY, Киев, ул. Победы, 20, телефон +380 99 222 20 02.'),
        ('Какие данные', 'Имя, номер телефона или контакт в мессенджере, выбранная модель и пожелания к авто, '
                         'которые вы указываете в заявке; технические данные посещения: страница и источник перехода '
                         '(рекламная метка Google Ads или utm).'),
        ('Зачем', 'Чтобы ответить на заявку, подготовить предложение и заключить договор; чтобы понимать, какая '
                  'реклама приводит клиентов.'),
        ('Основание', 'Ваше согласие, которое вы даёте, отправляя заявку (Закон Украины «О защите персональных данных»).'),
        ('Кому передаём', 'Данные не продаём. Заявки хранятся на сервере хостинга сайта (PythonAnywhere), '
                          'уведомление о заявке получают наши менеджеры в Telegram. Google Analytics и Google Ads '
                          'получают данные посещений без имени и телефона.'),
        ('Сколько храним', 'Пока это нужно для ответа на заявку, договора и учёта, или пока вы не попросите '
                           'удалить данные.'),
        ('Cookie и хранилище браузера', 'Сайт использует cookie Google Analytics и собственную статистику посещений, '
                                        'а также хранит в вашем браузере рекламную метку перехода 90 дней, чтобы '
                                        'заявка содержала её источник. Их можно удалить в настройках браузера.'),
        ('Ваши права', 'Вы можете узнать, какие ваши данные у нас есть, исправить или удалить их и отозвать согласие: '
                       'позвоните или напишите нам на +380 99 222 20 02. Жалобу можно подать Уполномоченному '
                       'Верховной Рады Украины по правам человека.'))),
}
STYLE = ('body{margin:0;background:#0b1c2d;color:#f4f5f7;font:16px/1.6 system-ui,sans-serif}'
         'main{max-width:760px;margin:auto;padding:24px 16px 48px}h1{font-size:26px;line-height:1.3}'
         'h2{font-size:18px;margin:24px 0 6px;color:#e8c87d}a{color:#e8c87d}nav{display:flex;gap:16px;flex-wrap:wrap}'
         'section+section{margin-top:40px;padding-top:24px;border-top:1px solid #3c5367}.updated{color:#aebed0}')


def html():
    from html import escape
    parts = []
    for lang, (title, updated, items) in SECTIONS.items():
        body = ''.join('<h2>%s</h2><p>%s</p>' % (escape(h), escape(p)) for h, p in items)
        parts.append('<section id="%s" lang="%s"><h1>%s</h1><p class="updated">%s</p>%s</section>'
                     % (lang, lang, escape(title), escape(updated), body))
    return ('<!doctype html><html lang="uk"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Політика конфіденційності — UA ART COMPANY</title>'
            '<link rel="canonical" href="https://www.uaart.com.ua/video/privacy.html">'
            '<style>%s</style></head><body><main><nav><a href="/video/index.html">UA ART COMPANY</a>'
            '<a href="/video/podbor.html">Підбір авто</a><a href="#ru">Русская версия</a></nav>%s</main></body></html>\n'
            % (STYLE, ''.join(parts)))
