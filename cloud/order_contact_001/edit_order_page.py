"""Order page, script and strings: contact block after the consent box, messenger choice opens the review, thank-you.

podbor.html: an empty container for the contact block after the consent box and the privacy link; the receipt reads
«Дякуємо! Вашу заявку отримано», «№ N» and when we reply (owner's step 1 terms). order.js: passes the container and,
when a messenger is chosen, submits the form — the usual checks run and «Перевірте заявку» opens. order-strings.json:
the two receipt texts uk/ru/ka. Versions are raised so browsers load the new files. Each original fragment must occur
exactly once and an applied fragment is refused.
"""
PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
STRINGS = 'video/order/order-strings.json'
REPLY = {
    'uk': "Ми зв'яжемося з вами найближчим часом — можливо, того ж дня, максимум протягом 3 робочих днів "
          "(усі дні, крім неділі та свят). Заявки обробляємо строго по черзі.",
    'ru': 'Мы свяжемся с вами в ближайшее время — возможно, в тот же день, максимум в течение 3 рабочих дней '
          '(все дни, кроме воскресенья и праздников). Заявки обрабатываем строго по очереди.',
    'ka': 'დაგიკავშირდებით უახლოეს დროში — შესაძლოა იმავე დღეს, მაქსიმუმ 3 სამუშაო დღეში '
          '(ყველა დღე, კვირისა და დღესასწაულების გარდა). განაცხადებს ვამუშავებთ მკაცრად რიგის მიხედვით.',
}
THANKS = {'uk': 'Дякуємо! Вашу заявку отримано', 'ru': 'Спасибо! Ваша заявка получена',
          'ka': 'გმადლობთ! თქვენი განაცხადი მიღებულია'}
SAVED = {'uk': 'Заявку збережено', 'ru': 'Заявка сохранена', 'ka': 'განაცხადი შენახულია'}
EDITS = {
    PAGE: (
        ('order/order.js?v=20261106.1', 'order/order.js?v=20261106.2'),
        ('<p class="privacy"><a class="privacy" href="/video/privacy.html" data-label="privacy">Політика конфіденційності</a></p>\n',
         '<p class="privacy"><a class="privacy" href="/video/privacy.html" data-label="privacy">Політика конфіденційності</a></p>\n'
         '      <div class="form-grid" id="contact-fields"></div>\n'),
        ('<h2 data-label="saved">Заявку збережено</h2>\n      <p id="number"></p>',
         '<h2 data-label="thanks">%s</h2>\n      <p>№ <span id="number"></span></p>\n      <p data-label="reply_time">%s</p>'
         % (THANKS['uk'], REPLY['uk'])),
    ),
    SCRIPT: (
        ("import {PreferenceForm} from './preferences-form.js?v=20261106.1';",
         "import {PreferenceForm} from './preferences-form.js?v=20261106.2';"),
        ("state.bootstrap.preferences,state.catalog,state.preferences,persist);",
         "state.bootstrap.preferences,state.catalog,state.preferences,persist,$('contact-fields'));"),
        ("$('other-model').addEventListener('click',()=>selectModel(''));\n",
         "$('other-model').addEventListener('click',()=>selectModel(''));\n"
         "// Choosing the messenger is the last step: it opens «Перевірте заявку» after the usual checks.\n"
         "form.addEventListener('change',event=>{if(event.target.name==='contact_method'&&event.target.value)form.requestSubmit();});\n"),
    ),
    STRINGS: tuple(('    "saved": "%s",\n' % SAVED[lang],
                    '    "saved": "%s",\n    "thanks": "%s",\n    "reply_time": "%s",\n' % (SAVED[lang], THANKS[lang], REPLY[lang]))
                   for lang in ('uk', 'ru', 'ka')),
}
# Public proof that each file is live.
CHECK_PAGE = 'id="contact-fields"'
CHECK_SCRIPT = "form.requestSubmit();"
CHECK_STRINGS = '"thanks": "Дякуємо! Вашу заявку отримано"'


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new, 1)
    return text.encode('utf-8')
