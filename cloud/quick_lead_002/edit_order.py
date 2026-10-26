"""Order page: «get an offer in a messenger» above «calculate» on every model card (QUICK-LEAD-002).

Owner request 2026-10-26. order.js adds the card button (model, country and title as data attributes);
the short enquiry itself is the shared quick-lead.js / quick-lead.css form, here in a <dialog> inside
the order root, so the page's own language switch translates its [data-label] texts from
order-strings.json. Asset versions are raised so browsers load the new files. Each original fragment
must occur exactly once and an applied fragment is refused. The page edit does not depend on the
order.js version a parallel release (MODEL-GALLERY) may set: the version is replaced whatever it is.
"""
import re

PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
STRINGS = 'video/order/order-strings.json'
VERSION = '20261026.5'  # distinct from MODEL-GALLERY-001 (20261026.1)
ASSET_VERSION = '20261026.2'  # quick-lead.js / quick-lead.css, as ua_seo_quick_form.ASSET_VERSION

DIALOG = ('      <dialog class="ua-quick-dialog" id="quick-lead-dialog">'
          '<form class="ua-quick" data-ua-quick-lead><h2><span data-label="quick_title">Отримати пропозицію на</span> '
          '<span data-quick-model-title></span></h2><div data-fields>'
          '<label><span data-label="quick_name">Ім\'я</span>'
          '<input name="customer_name" autocomplete="name" required minlength="2" maxlength="80"></label>'
          '<label><span data-label="quick_phone">Телефон</span>'
          '<input name="phone" type="tel" autocomplete="tel" inputmode="tel" required maxlength="30"></label>'
          '<button type="submit" data-label="quick_offer">Отримати пропозицію в месенджері</button>'
          '<p class="note" data-label="quick_note">Менеджер напише вам у Viber або Telegram.</p>'
          '<p class="consent" data-consent>Натискаючи кнопку, ви погоджуєтесь на обробку персональних даних.</p></div>'
          '<p class="status" data-status role="status" hidden></p>'
          '<span data-msg="ok" data-label="quick_ok" hidden></span><span data-msg="error" data-label="quick_error" hidden></span>'
          '<span data-msg="bad_phone" data-label="quick_bad_phone" hidden></span>'
          '<span data-msg="bad_name" data-label="quick_bad_name" hidden></span>'
          '<button type="button" class="ua-quick-close" data-quick-close data-label="quick_close">Закрити</button>'
          '</form></dialog>\n')
TEXTS = {
    'uk': {'quick_offer': 'Отримати пропозицію в месенджері', 'quick_title': 'Отримати пропозицію на',
           'quick_name': "Ім'я", 'quick_phone': 'Телефон', 'quick_note': 'Менеджер напише вам у Viber або Telegram.',
           'quick_ok': 'Дякуємо! Заявку {number} прийнято. Менеджер напише вам у Viber або Telegram.',
           'quick_error': 'Не вдалося надіслати заявку. Зателефонуйте нам: +380 99 222 20 02.',
           'quick_bad_phone': 'Перевірте номер телефону.', 'quick_bad_name': "Вкажіть ім'я.", 'quick_close': 'Закрити'},
    'ru': {'quick_offer': 'Получить предложение в мессенджере', 'quick_title': 'Получить предложение на',
           'quick_name': 'Имя', 'quick_phone': 'Телефон', 'quick_note': 'Менеджер напишет вам в Viber или Telegram.',
           'quick_ok': 'Спасибо! Заявка {number} принята. Менеджер напишет вам в Viber или Telegram.',
           'quick_error': 'Не удалось отправить заявку. Позвоните нам: +380 99 222 20 02.',
           'quick_bad_phone': 'Проверьте номер телефона.', 'quick_bad_name': 'Укажите имя.', 'quick_close': 'Закрыть'},
    'ka': {'quick_offer': 'შეთავაზების მიღება მესენჯერში', 'quick_title': 'შეთავაზების მიღება:',
           'quick_name': 'სახელი', 'quick_phone': 'ტელეფონი', 'quick_note': 'მენეჯერი მოგწერთ Viber-ში ან Telegram-ში.',
           'quick_ok': 'გმადლობთ! განაცხადი {number} მიღებულია. მენეჯერი მოგწერთ Viber-ში ან Telegram-ში.',
           'quick_error': 'განაცხადის გაგზავნა ვერ მოხერხდა. დაგვირეკეთ: +380 99 222 20 02.',
           'quick_bad_phone': 'შეამოწმეთ ტელეფონის ნომერი.', 'quick_bad_name': 'მიუთითეთ სახელი.', 'quick_close': 'დახურვა'},
}
OTHER_CHOOSE = {'uk': 'Обрати інше авто', 'ru': 'Выбрать другой автомобиль', 'ka': 'სხვა ავტომობილის არჩევა'}


def _strings(lang):
    line = '    "other_choose": "%s",\n' % OTHER_CHOOSE[lang]
    added = ''.join('    "%s": "%s",\n' % item for item in TEXTS[lang].items())
    return line, line + added


EDITS = {
    PAGE: (
        ('<link rel="stylesheet" href="order/order.css?v=20261025.2">',
         '<link rel="stylesheet" href="order/order.css?v=20261025.2">'
         '<link rel="stylesheet" href="order/quick-lead.css?v=%s">'
         '<script src="order/quick-lead.js?v=%s" defer></script>' % (ASSET_VERSION, ASSET_VERSION)),
        ('      <div id="models" class="models"></div>\n',
         '      <div id="models" class="models"></div>\n' + DIALOG),
    ),
    SCRIPT: (
        ("    info.append(button);article.append(media,info);return article;\n",
         "    const offer=node('button',t('quick_offer'),'quick-offer');offer.type='button';\n"
         "    Object.assign(offer.dataset,{quickLeadModel:model.key,quickLeadCountry:state.country,"
         "quickLeadTitle:model.labels[state.lang]});\n"
         "    info.append(offer,button);article.append(media,info);return article;\n"),
    ),
    STRINGS: tuple(_strings(lang) for lang in ('uk', 'ru', 'ka')),
}
SCRIPT_VERSION = re.compile(r'order/order\.js\?v=[0-9.]+')
# Public proof that each file is live.
CHECK_PAGE = 'id="quick-lead-dialog"'
CHECK_SCRIPT = "quickLeadModel:model.key"
CHECK_STRINGS = '"quick_offer": "Отримати пропозицію в месенджері"'


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    if name == PAGE:
        current = SCRIPT_VERSION.findall(text)
        if len(current) != 1 or current[0] == 'order/order.js?v=' + VERSION:
            raise ValueError('ORDER_SCRIPT_VERSION:' + name)
        text = SCRIPT_VERSION.sub('order/order.js?v=' + VERSION, text)
    return text.encode('utf-8')
