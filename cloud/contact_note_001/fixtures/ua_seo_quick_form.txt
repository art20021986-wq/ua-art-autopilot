"""Short enquiry form for the advertised model pages; pure: (lang, model key) in, an HTML block out.

The fields use the browser's standard autofill tokens (autocomplete="name", autocomplete="tel"),
so a phone offers its owner's name and number in one tap. Sending is done by
/video/order/quick-lead.js; its look by /video/order/quick-lead.css (both linked from the block).
Result and error texts sit in hidden [data-msg] elements, the contract shared with the order page.
"""
from html import escape

ASSET_VERSION = '20261026.2'
COUNTRY = 'korea'
# Advertised landing model -> order page catalogue key.
MODELS = {('Kia', 'K5'): 'kia-k5', ('Hyundai', 'Sonata'): 'hyundai-sonata', ('Hyundai', 'Tucson'): 'hyundai-tucson',
          ('Kia', 'Sportage'): 'kia-sportage', ('Hyundai', 'Santa Fe'): 'hyundai-santa-fe'}
T = {
    'uk': dict(title='Отримати пропозицію на {model}', name="Ім'я", phone='Телефон',
               button='Отримати пропозицію в месенджері', note='Менеджер напише вам у Viber або Telegram.',
               consent='Натискаючи кнопку, ви погоджуєтесь на обробку персональних даних.',
               ok='Дякуємо! Заявку {number} прийнято. Менеджер напише вам у Viber або Telegram.',
               error='Не вдалося надіслати заявку. Зателефонуйте нам: +380 99 222 20 02.',
               bad_phone='Перевірте номер телефону.', bad_name="Вкажіть ім'я."),
    'ru': dict(title='Получить предложение на {model}', name='Имя', phone='Телефон',
               button='Получить предложение в мессенджере', note='Менеджер напишет вам в Viber или Telegram.',
               consent='Нажимая кнопку, вы соглашаетесь на обработку персональных данных.',
               ok='Спасибо! Заявка {number} принята. Менеджер напишет вам в Viber или Telegram.',
               error='Не удалось отправить заявку. Позвоните нам: +380 99 222 20 02.',
               bad_phone='Проверьте номер телефона.', bad_name='Укажите имя.'),
}


def block(lang, key):
    """The form for an advertised model, or '' for any other page."""
    if key not in MODELS:
        return ''
    t = T[lang]
    messages = ''.join('<span data-msg="%s" hidden>%s</span>' % (name, escape(t[name]))
                       for name in ('ok', 'error', 'bad_phone', 'bad_name'))
    return ('<link rel="stylesheet" href="/video/order/quick-lead.css?v={v}">'
            '<form class="ua-quick" data-ua-quick-lead data-lang="{lang}" data-country="{country}" data-model="{model}">'
            '<h2>{title}</h2><div data-fields>'
            '<label>{name}<input name="customer_name" autocomplete="name" required minlength="2" maxlength="80"></label>'
            '<label>{phone}<input name="phone" type="tel" autocomplete="tel" inputmode="tel" required maxlength="30"></label>'
            '<button type="submit">{button}</button><p class="note">{note}</p>'
            '<p class="consent" data-consent>{consent}</p></div>'
            '<p class="status" data-status role="status" hidden></p>{messages}</form>'
            '<script src="/video/order/quick-lead.js?v={v}" defer></script>').format(
        v=ASSET_VERSION, lang=lang, country=COUNTRY, model=MODELS[key], title=escape(t['title'].format(model='%s %s' % key)),
        name=escape(t['name']), phone=escape(t['phone']), button=escape(t['button']), note=escape(t['note']),
        consent=escape(t['consent']), messages=messages)
