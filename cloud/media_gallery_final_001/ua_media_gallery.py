"""Server-rendered photo/video galleries. Inputs are existing ordered media URLs."""
from html import escape
import json
from urllib.parse import urlsplit

from ua_media_styles import CSS
from ua_media_script import JS

MARKER = 'ua-media-gallery-v1'


def safe_url(value):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ValueError('MEDIA_URL')
    url = urlsplit(value)
    if url.scheme not in ('', 'http', 'https') or url.username or url.password or value.startswith('//'):
        raise ValueError('MEDIA_URL_SCHEME')
    return value


def photos(originals, previews, title=''):
    originals, previews = list(originals), list(previews)
    if len(originals) != len(previews):
        raise ValueError('MEDIA_PHOTO_COUNT')
    return render('photo', [{'src': safe_url(src), 'preview': safe_url(preview),
                             'alt': str(title)} for src, preview in zip(originals, previews)])


def videos(sources, posters, title=''):
    sources, posters = list(sources), list(posters)
    if len(sources) != len(posters):
        raise ValueError('MEDIA_VIDEO_COUNT')
    return render('video', [{'src': safe_url(src), 'preview': safe_url(poster) if poster else '',
                             'alt': str(title)} for src, poster in zip(sources, posters)])


def poster_url(attribute):
    """Read the generator's existing poster attribute without inventing an asset URL."""
    from html.parser import HTMLParser
    class Poster(HTMLParser):
        value = ''
        def handle_starttag(self, tag, attrs):
            self.value = dict(attrs).get('poster', '')
    parser = Poster()
    parser.feed('<video' + attribute + '>')
    return parser.value


def render(kind, items):
    if kind not in ('photo', 'video'):
        raise ValueError('MEDIA_KIND')
    if not items:
        return ''
    uid = 'um-' + kind
    is_photo = kind == 'photo'
    noun = 'Фото' if is_photo else 'Видео'
    label = 'Фотографии автомобиля' if is_photo else 'Видео автомобиля'
    first = items[0]
    esc = lambda x: escape(str(x), quote=True)
    for item in items:
        safe_url(item['src'])
        if item['preview']:
            safe_url(item['preview'])
    encoded = json.dumps(items, ensure_ascii=True, separators=(',', ':')).replace('<', '\\u003c')
    out = [f'<section class="um-gallery" data-ua-media="{kind}" aria-label="{label}">',
           f'<script type="application/json" class="um-data">{encoded}</script>',
           '<div class="um-mount"><div class="um-view">',
           '<div class="um-toolbar">',
           f'<span class="um-counter" role="status" aria-live="polite" aria-atomic="true">{noun} 1 / {len(items)}</span>',
           '<button type="button" class="um-tool um-expand" aria-label="Увеличить">⤢</button>',
           '<button type="button" class="um-tool um-fullscreen" aria-label="На весь экран">⛶</button>',
           '<button type="button" class="um-tool um-close" aria-label="Закрыть">×</button>',
           '<span class="um-message" role="status" hidden></span></div>',
           '<div class="um-stage">',
           f'<div id="{uid}-panel" class="um-panel" role="tabpanel" aria-labelledby="{uid}-tab-0">']
    if is_photo:
        out.append(f'<button type="button" class="um-image-button" aria-label="Увеличить фото">'
                   f'<img src="{esc(first["preview"])}" alt="{esc(first["alt"])} — фото 1" '
                   'loading="eager" fetchpriority="high" decoding="async" draggable="false"></button>')
    else:
        poster = f' poster="{esc(first["preview"])}"' if first['preview'] else ''
        out.append(f'<video controls playsinline preload="none"{poster} src="{esc(first["src"])}">'
                   f'<a href="{esc(first["src"])}">Открыть видео отдельно</a></video>')
    out.append('</div><div class="um-state" hidden><span></span>'
               '<button type="button" class="um-tool um-retry" hidden>Повторить</button></div>')
    hidden = ' hidden' if len(items) < 2 else ''
    out.extend([f'<button type="button" class="um-tool um-prev" aria-label="Назад" disabled{hidden}>‹</button>',
                f'<button type="button" class="um-tool um-next" aria-label="Вперёд"{hidden}>›</button></div>',
                f'<div class="um-thumbs" role="tablist" aria-label="{label}">'])
    for i, item in enumerate(items):
        out.append(f'<button type="button" id="{uid}-tab-{i}" class="um-thumb" role="tab" '
                   f'aria-controls="{uid}-panel" aria-selected="{str(i == 0).lower()}" '
                   f'aria-label="{noun} {i+1} из {len(items)}" tabindex="{0 if i == 0 else -1}" data-index="{i}">')
        if item['preview']:
            out.append(f'<img src="{esc(item["preview"])}" alt="" loading="lazy" decoding="async" fetchpriority="low" draggable="false">')
        if not is_photo:
            out.append('<span class="um-playmark" aria-hidden="true">▶</span>')
        out.append(f'<span class="um-number" aria-hidden="true">{i+1}</span></button>')
    out.extend(['</div></div></div>', f'<dialog class="um-dialog" aria-label="{label}"></dialog></section>'])
    return ''.join(out)


def assets():
    return '<!--' + MARKER + '--><style>' + CSS + '</style><script>' + JS + '</script>'
