"""Site language script (video/ua-site-languages.js), CARD-LANG-001.

1. The card phrases that had no Ukrainian (card_texts.UK: gallery buttons, a delivery stage, colours, three CRM
   descriptions), and the gallery buttons in Georgian and back to Russian, so the Ukrainian card versions are complete.
2. A page with language versions (both hreflang uk and ru links, the card versions in /video/ua/ and
   /video/ru/) opens in its own language, and UA/RU go to the other version's address; GE stays on the page.
   Pages without such links behave exactly as before.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
import json

import card_texts

NAME = 'video/ua-site-languages.js'
# Gallery buttons back to Russian, and in Georgian; the Ukrainian additions are card_texts.UK.
WORDS = {'uk': card_texts.UK,
         'ka': {'Повторить': 'გამეორება', 'На весь экран': 'სრულ ეკრანზე', 'Вперёд': 'წინ'},
         'ru': {'Повторити': 'Повторить', 'На весь екран': 'На весь экран', 'Вперед': 'Вперёд'}}


def _entries(lang):
    return ''.join('%s:%s,' % (json.dumps(k, ensure_ascii=False), json.dumps(v, ensure_ascii=False))
                   for k, v in WORDS[lang].items())


EDITS = tuple(('"%s":{' % lang, '"%s":{%s' % (lang, _entries(lang))) for lang in ('ru', 'uk', 'ka')) + (
    ("    choose(request || saved || 'uk',!!request);",
     "    // CARD-LANG-001: a page with language versions opens in its own language.\n"
     "    var versions = {};\n"
     "    document.querySelectorAll('link[rel=\"alternate\"][hreflang]').forEach(function (link) {\n"
     "      var lang = valid(link.getAttribute('hreflang')); if (lang) versions[lang] = link.href;\n"
     "    });\n"
     "    var own = versions.uk && versions.ru ? valid(document.documentElement.getAttribute('lang')) : null;\n"
     "    choose(request || own || saved || 'uk',!!request);"),
    ("event.preventDefault();event.stopImmediatePropagation();choose(lang,true);",
     "event.preventDefault();event.stopImmediatePropagation();"
     "if(own && lang !== own && versions[lang]){try{localStorage.setItem(key,lang);}catch(e){}location.href=versions[lang];return;}"
     "choose(lang,true);"),
    ("choose(valid(new URLSearchParams(location.search).get('lang')) || valid(saved) || current,false);",
     "choose(valid(new URLSearchParams(location.search).get('lang')) || own || valid(saved) || current,false);"),
)
CHECK = "var own = versions.uk && versions.ru"


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('LANGUAGES_FRAGMENT_NOT_UNIQUE:' + old[:40])
        text = text.replace(old, new)
    return text.encode('utf-8')
