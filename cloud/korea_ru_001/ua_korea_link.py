"""The «Авто з Кореї» hub pages link the Korea auctions page under their model list (SEO item 5, owner «Да»
2026-11-12, text approved). ua_seo_landings.pages runs it on every landing build, so the link stays."""
from html import escape
import re

HUBS = {'seo/ua/avto-z-korei-do-kyieva-pid-kluch.html': ('/video/korea.html', 'Аукціони Кореї онлайн — дивитися лоти →'),
        'seo/ru/avto-iz-korei-v-kiev-pod-kluch.html': ('/video/ru/korea.html', 'Аукционы Кореи онлайн — смотреть лоты →')}
MODELS = re.compile(r'<h2>(?:Моделі з Кореї|Модели из Кореи)</h2>(?:<ul class="models">.*?</ul>)?', re.S)


def apply(name, html):
    """The hub page with the link right after the model list; other pages and pages already linking unchanged."""
    hub = HUBS.get(name)
    if not hub or 'href="%s"' % hub[0] in html:
        return html
    return MODELS.sub(lambda m: m[0] + '<p><a href="%s">%s</a></p>' % (hub[0], escape(hub[1], quote=False)), html, count=1)
