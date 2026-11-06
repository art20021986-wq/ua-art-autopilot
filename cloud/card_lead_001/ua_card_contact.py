"""One «Связаться с менеджером» button on every car card (LEAD-FOLDERS-001, owner 2026-11-06).

The card's «Купить» / «Задаток 500 $» and «Задать вопрос по этой машине» become one button that opens the same
short dialog as the order page (name + phone, /video/order/quick-lead.js); the enquiry carries the card's code
and lands in the CRM enquiry desk. The single source of the card's primary action: the card generators'
primary-action step (stranica.py, master_card.py) takes the label and markup from here and calls finish().

Texts are Russian with data-uk/data-ka (the site's language script and ua_card_lang translate by them). The
button keeps the bot link as its address, so a browser without JavaScript still reaches the manager.
Pure functions; finish() is idempotent.
"""
from html import escape
import re

ASSET_VERSION = '20261106.1'
LABEL = {'ru': 'Связаться с менеджером', 'uk': "Зв'язатися з менеджером", 'ka': 'მენეჯერთან დაკავშირება'}
# The order page dialog's texts (video/order/order-strings.json quick_*), one in one.
TEXT = {
    'name': {'ru': 'Имя', 'uk': "Ім'я", 'ka': 'სახელი'},
    'phone': {'ru': 'Телефон', 'uk': 'Телефон', 'ka': 'ტელეფონი'},
    'submit': {'ru': 'Получить предложение от UA ART в мессенджере', 'uk': 'Отримати пропозицію від UA ART в месенджері',
               'ka': 'UA ART-ისგან შეთავაზების მიღება მესენჯერში'},
    'note': {'ru': 'Менеджер напишет вам в Viber или Telegram.', 'uk': 'Менеджер напише вам у Viber або Telegram.',
             'ka': 'მენეჯერი მოგწერთ Viber-ში ან Telegram-ში.'},
    'consent': {'ru': 'Нажимая кнопку, вы соглашаетесь на обработку персональных данных.',
                'uk': 'Натискаючи кнопку, ви погоджуєтесь на обробку персональних даних.',
                'ka': 'ღილაკზე დაჭერით თქვენ ეთანხმებით პერსონალური მონაცემების დამუშავებას.'},
    'privacy': {'ru': 'Политика конфиденциальности', 'uk': 'Політика конфіденційності',
                'ka': 'კონფიდენციალურობის პოლიტიკა'},
    'close': {'ru': 'Закрыть', 'uk': 'Закрити', 'ka': 'დახურვა'},
    'ok': {'ru': 'Спасибо! Заявка {number} принята. Менеджер напишет вам в Viber или Telegram.',
           'uk': 'Дякуємо! Заявку {number} прийнято. Менеджер напише вам у Viber або Telegram.',
           'ka': 'გმადლობთ! განაცხადი {number} მიღებულია. მენეჯერი მოგწერთ Viber-ში ან Telegram-ში.'},
    'error': {'ru': 'Не удалось отправить заявку. Позвоните нам: +380 99 222 20 02.',
              'uk': 'Не вдалося надіслати заявку. Зателефонуйте нам: +380 99 222 20 02.',
              'ka': 'განაცხადის გაგზავნა ვერ მოხერხდა. დაგვირეკეთ: +380 99 222 20 02.'},
    'bad_phone': {'ru': 'Проверьте номер телефона.', 'uk': 'Перевірте номер телефону.',
                  'ka': 'შეამოწმეთ ტელეფონის ნომერი.'},
    'bad_name': {'ru': 'Укажите имя.', 'uk': "Вкажіть ім'я.", 'ka': 'მიუთითეთ სახელი.'},
}
MARK = 'ua-card-contact-v1'
DIALOG_ID = 'quick-lead-dialog'
OWN = re.compile(r'<!--%s-->.*?<!--/%s-->' % (MARK, MARK), re.S)
# What the single button replaces: the question link, the deposit note and the old click script of the
# purchase/question links (it sent the visitor to the bot without the car).
QUESTION = re.compile(r'<a\b[^>]*\bid=["\']vopros["\'][^>]*>.*?</a\s*>', re.S | re.I)
NOTE = re.compile(r'<(?:div|p)\b[^>]*class=["\'][^"\']*\bcta-note\b[^"\']*["\'][^>]*>.*?</(?:div|p)\s*>', re.S | re.I)
OLD_SCRIPT = re.compile(r"<script>\(function\(\)\{document\.querySelectorAll\('\.kn_kupit'\).*?\}\)\(\);</script>", re.S)
PRIMARY = re.compile(r'<a\b[^>]*class=["\'][^"\']*\bua-primary-action-v1\b[^"\']*["\'][^>]*>.*?</a\s*>', re.S | re.I)


def _i18n(key):
    value = TEXT[key]
    return ' data-ru="%s" data-uk="%s" data-ka="%s"' % (escape(value['ru']), escape(value['uk']), escape(value['ka']))


def button(stage, href, code):
    """The card's one primary action (the generators' canonical markup with this label and the dialog opener)."""
    return ('<a class="dejstvie kn_kupit ua-primary-action-v1" data-ua-stage-action="%d" data-quick-lead-car="%s" '
            'href="%s" data-ru="%s" data-uk="%s" data-ka="%s">%s</a>'
            % (int(stage), escape(code), escape(href), escape(LABEL['ru']), escape(LABEL['uk']), escape(LABEL['ka']),
               escape(LABEL['ru'])))


def dialog():
    """The order page's short dialog, with the card's own translated texts and assets."""
    messages = ''.join('<span data-msg="%s"%s hidden>%s</span>' % (key, _i18n(key), escape(TEXT[key]['ru']))
                       for key in ('ok', 'error', 'bad_phone', 'bad_name'))
    return ('<!--{mark}--><link rel="stylesheet" href="/video/order/quick-lead.css?v={v}">'
            '<dialog class="ua-quick-dialog" id="{id}"><form class="ua-quick" data-ua-quick-lead>'
            '<h2><span{t_label}>{label}</span> <span data-quick-model-title></span></h2><div data-fields>'
            '<label><span{t_name}>{name}</span><input name="customer_name" autocomplete="name" required minlength="2" '
            'maxlength="80"></label><label><span{t_phone}>{phone}</span><input name="phone" type="tel" autocomplete="tel" '
            'inputmode="tel" required maxlength="30"></label><button type="submit"{t_submit}>{submit}</button>'
            '<p class="note"{t_note}>{note}</p><p class="consent" data-consent{t_consent}>{consent}</p>'
            '<a class="privacy" href="/video/privacy.html#ru" data-uk-href="/video/privacy.html"{t_privacy}>{privacy}</a>'
            '</div><p class="status" data-status role="status" hidden></p>{messages}'
            '<button type="button" class="ua-quick-close" data-quick-close{t_close}>{close}</button></form></dialog>'
            '<script src="/video/order/attribution.js?v={v}" defer></script>'
            '<script src="/video/order/quick-lead.js?v={v}" defer></script><!--/{mark}-->').format(
        mark=MARK, v=ASSET_VERSION, id=DIALOG_ID, label=escape(LABEL['ru']),
        t_label=' data-ru="%s" data-uk="%s" data-ka="%s"' % (escape(LABEL['ru']), escape(LABEL['uk']), escape(LABEL['ka'])),
        t_name=_i18n('name'), name=escape(TEXT['name']['ru']), t_phone=_i18n('phone'), phone=escape(TEXT['phone']['ru']),
        t_submit=_i18n('submit'), submit=escape(TEXT['submit']['ru']), t_note=_i18n('note'), note=escape(TEXT['note']['ru']),
        t_consent=_i18n('consent'), consent=escape(TEXT['consent']['ru']), t_privacy=_i18n('privacy'),
        privacy=escape(TEXT['privacy']['ru']), t_close=_i18n('close'), close=escape(TEXT['close']['ru']), messages=messages)


def finish(source):
    """The page around the one button: no question link, deposit note or old click script; the dialog once,
    before </body>. A page without the button is returned unchanged."""
    if not PRIMARY.search(source):
        return source
    source = QUESTION.sub('', source)
    source = NOTE.sub('', source)
    source = OLD_SCRIPT.sub('', source)
    source = OWN.sub('', source)
    end = source.lower().rfind('</body>')
    if end < 0:
        return source + dialog()
    return source[:end] + dialog() + source[end:]


def errors(source):
    """What the publication check refuses: anything but one button, one dialog and no old buttons."""
    found = []
    if len(PRIMARY.findall(source)) != 1:
        found.append('contact buttons != 1')
    if source.count('<!--%s-->' % MARK) != 1 or source.count('id="%s"' % DIALOG_ID) != 1:
        found.append('contact dialog != 1')
    if QUESTION.search(source) or OLD_SCRIPT.search(source):
        found.append('old card buttons left')
    return found
