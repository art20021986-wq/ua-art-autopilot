"""video/korea.html share tags (SEO-FIX-20261121, answer 3): og:title, og:description and og:url were copied from the
home page when the page was built from its layout; they become the page's own title, description and address
(each language from the page's own data-uk/ru/ka texts). ru/korea.html is rebuilt from it by the installed
ua_korea_ru job (Russian texts, its own og:url)."""
import tags

NAME = 'video/korea.html'
URL = 'https://www.uaart.com.ua/video/korea.html'
OG_TITLE = r'<meta\s+property="og:title"[^>]*>'
OG_DESCRIPTION = r'<meta\s+property="og:description"[^>]*>'
OG_URL = r'<meta\s+property="og:url"[^>]*>'


def own(source):
    """(title texts, description texts) by language, raw as on the page."""
    title = tags.attributes(tags.find(source, r'<title\b[^>]*>'))
    description = tags.attributes(tags.find(source, r'<meta\s+name="description"[^>]*>'))
    titles = {lang: title['data-' + lang] for lang in ('uk', 'ru', 'ka')}
    descriptions = {lang: description['data-%s-content' % lang] for lang in ('uk', 'ru', 'ka')}
    return titles, descriptions


def share(pattern, source, texts):
    old = tags.find(source, pattern)
    new = tags.with_attribute(old, 'content', texts['uk'])
    for lang in ('ru', 'uk', 'ka'):
        new = tags.with_attribute(new, 'data-%s-content' % lang, texts[lang])
    return tags.replace_once(source, old, new)


def build(value):
    source = value.decode('utf-8')
    titles, descriptions = own(source)
    result = share(OG_TITLE, source, titles)
    result = share(OG_DESCRIPTION, result, descriptions)
    old = tags.find(result, OG_URL)
    result = tags.replace_once(result, old, tags.with_attribute(old, 'content', URL))
    if result == source:
        raise ValueError('KOREA_TAGS_ALREADY_OWN')
    return result.encode('utf-8')
