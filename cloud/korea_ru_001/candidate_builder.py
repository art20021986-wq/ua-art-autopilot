"""Build the KOREA-RU-001 candidate (owner «Да» 2026-11-12: Korea page in the sitemap and in Russian).

1. /video/ru/korea.html: the Russian version of the Korea auctions page (ua_korea_ru.py, new); written now from the
   live page and kept in step by the existing card version job (ua_card_lang_job.py, once a minute).
2. /video/korea.html: the hreflang pair first in <head> (its only change), so search engines and the language
   scripts know both versions.
3. video/i18n-home-ge.js: a page with language versions opens in its own language (as ua-site-languages.js).
4. ua_seo_sitemap.py: both Korea pages in the sitemap.
Texts, lots, photos, CRM data and every other byte stay as they are.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEW_MODULES = ('ua_korea_ru.py',)
KOREA = 'video/korea.html'
RUSSIAN = 'video/ru/korea.html'
MARK = 'KOREA-RU-001'
EDITS = {
    'ua_seo_sitemap.py': [
        ("CORE = ('index.html', 'katalog.html', 'podbor.html', 'info.html')",
         "CORE = ('index.html', 'katalog.html', 'podbor.html', 'info.html', 'korea.html', 'ru/korea.html')"
         "  # KOREA-RU-001"),
    ],
    'ua_card_lang_job.py': [
        ("        result = ua_card_lang.reconcile(root, published)\n",
         "        result = ua_card_lang.reconcile(root, published)\n"
         "        try:  # KOREA-RU-001: the Russian Korea page follows korea.html\n"
         "            import ua_korea_ru\n"
         "            result['written'] += ua_korea_ru.reconcile(root)['written']\n"
         "        except Exception as error:\n"
         "            result['failed']['korea.html'] = type(error).__name__ + ':' + str(error)[:160]\n"),
    ],
    # The home language script chose ?lang=, the saved home choice or Ukrainian: the Russian page turned Ukrainian.
    'video/i18n-home-ge.js': [
        ("  var yaz=zapros||savedHomeLang()||'uk';\n",
         "  // KOREA-RU-001: a page with language versions (hreflang uk and ru) opens in its own language.\n"
         "  var ownLang=(document.querySelector('link[rel=\"alternate\"][hreflang=\"uk\"]')&&"
         "document.querySelector('link[rel=\"alternate\"][hreflang=\"ru\"]'))?"
         "validLang(document.documentElement.getAttribute('lang')):null;\n"
         "  var yaz=zapros||ownLang||savedHomeLang()||'uk';\n"),
    ],
}
DEPENDENCY_SHA256 = {}


def targets(root):
    """Existing files the candidate replaces (the new module and the Russian page are added beside them)."""
    return tuple(EDITS) + (KOREA,)


def edit(name, value):
    text = value.decode('utf-8')
    if MARK in text:
        raise ValueError('KOREA_RU_ALREADY_APPLIED:' + name)
    for old, new in EDITS[name]:
        if text.count(old) != 1:
            raise ValueError('KOREA_RU_EDIT:%s:%d' % (name, text.count(old)))
        text = text.replace(old, new)
    return text.encode('utf-8')


def korea(value):
    """korea.html with the hreflang pair first in <head>; refused when the page already has language links."""
    import ua_korea_ru
    text = value.decode('utf-8')
    if 'hreflang=' in text or text.count('<head>') != 1:
        raise ValueError('KOREA_RU_PAGE_HEAD')
    return text.replace('<head>', '<head>' + ua_korea_ru.links(), 1).encode('utf-8')


def build(source, dependencies, read_original=None):
    import ua_korea_ru
    result = {name: (HERE/name).read_bytes() for name in NEW_MODULES}
    for name, value in source.items():
        result[name] = korea(value) if name == KOREA else edit(name, value)
    result[RUSSIAN] = ua_korea_ru.page(result[KOREA].decode('utf-8')).encode('utf-8')
    return result
