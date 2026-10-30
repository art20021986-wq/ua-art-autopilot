"""Site language script (video/ua-site-languages.js), CARD-LANG-001.

1. Three gallery phrases of the car card that had no translation: «Повторить», «На весь экран», «Вперёд»
   (uk, ka; and back to ru), so the Ukrainian card version is complete.
2. A page with language versions (both hreflang uk and ru links, the card versions in /video/ua/ and
   /video/ru/) opens in its own language, and UA/RU go to the other version's address; GE stays on the page.
   Pages without such links behave exactly as before.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'video/ua-site-languages.js'
WORDS = {'uk': {'Повторить': 'Повторити', 'На весь экран': 'На весь екран', 'Вперёд': 'Вперед'},
         'ka': {'Повторить': 'გამეორება', 'На весь экран': 'სრულ ეკრანზე', 'Вперёд': 'წინ'},
         'ru': {'Повторити': 'Повторить', 'На весь екран': 'На весь экран', 'Вперед': 'Вперёд'}}


def _entries(lang):
    return ''.join('"%s":"%s",' % item for item in WORDS[lang].items())


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
