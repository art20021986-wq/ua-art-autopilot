"""Order page (ADS-READY-001): the ad source travels with the request; the privacy policy is linked under both forms.

attribution.js is loaded next to quick-lead.js; order.js adds window.uaAttribution() to every request it
posts (the big form and its Telegram hand-off); the short enquiry dialog sends it from quick-lead.js.
The privacy link sits under the big form's consent and under the dialog's consent; its text comes from
order-strings.json through the page's own language switch. Asset versions are raised so browsers load
the new files; the order.js version is set by pattern, whatever another release made it.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
import re

PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
STRINGS = 'video/order/order-strings.json'
VERSION = '20261030.3'  # order.js; distinct from JAPAN-NOTE (20261030.1) and MODEL-GALLERY-W245 (20261030.2)
ASSET_VERSION = '20261030.1'  # quick-lead.js / quick-lead.css / attribution.js, as ua_seo_quick_form.ASSET_VERSION
PRIVACY = '/video/privacy.html'

LINK = '<a class="privacy" href="%s" data-label="privacy">Політика конфіденційності</a>' % PRIVACY
TEXTS = {'uk': 'Політика конфіденційності', 'ru': 'Политика конфиденциальности', 'ka': 'კონფიდენციალურობის პოლიტიკა'}
CLOSE = {'uk': 'Закрити', 'ru': 'Закрыть', 'ka': 'დახურვა'}


def _strings(lang):
    line = '    "quick_close": "%s",\n' % CLOSE[lang]
    return line, line + '    "privacy": "%s",\n' % TEXTS[lang]


EDITS = {
    PAGE: (
        ('<link rel="stylesheet" href="order/quick-lead.css?v=20261026.2">'
         '<script src="order/quick-lead.js?v=20261026.2" defer></script>',
         '<link rel="stylesheet" href="order/quick-lead.css?v=%s">'
         '<script src="order/attribution.js?v=%s" defer></script>'
         '<script src="order/quick-lead.js?v=%s" defer></script>' % ((ASSET_VERSION,) * 3)),
        ('<label class="consent"><input type="checkbox" name="consent" required><span id="consent-copy"></span></label>\n',
         '<label class="consent"><input type="checkbox" name="consent" required><span id="consent-copy"></span></label>\n'
         '      <p class="privacy">%s</p>\n' % LINK),
        ('<p class="consent" data-consent>Натискаючи кнопку, ви погоджуєтесь на обробку персональних даних.</p></div>',
         '<p class="consent" data-consent>Натискаючи кнопку, ви погоджуєтесь на обробку персональних даних.</p>%s</div>'
         % LINK),
    ),
    SCRIPT: (
        ("  const response=await fetch(`/api/orders/${path}`,{method:'POST',credentials:'same-origin',headers,"
         "body:JSON.stringify(payload)});\n",
         "  // The landing page's ad source (attribution.js), when it kept one.\n"
         "  const source=window.uaAttribution?.();\n"
         "  const response=await fetch(`/api/orders/${path}`,{method:'POST',credentials:'same-origin',headers,"
         "body:JSON.stringify(source?{...payload,attribution:source}:payload)});\n"),
    ),
    STRINGS: tuple(_strings(lang) for lang in ('uk', 'ru', 'ka')),
}
SCRIPT_VERSION = re.compile(r'order/order\.js\?v=[0-9.]+')
# Public proof that each file is live.
CHECK_PAGE = 'order/attribution.js?v=' + ASSET_VERSION
CHECK_SCRIPT = 'attribution:source'
CHECK_STRINGS = '"privacy": "Політика конфіденційності"'


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
