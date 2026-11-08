"""SPEED-002: the home page stage pictures get a 600 px copy for phones (srcset); computers keep the originals.

Each stage card shows two half-width pictures (stage illustration and a live car photo), about 180 px wide on a
phone, but loads 880–1320 px files. A copy is written once to video/opt/s/ beside the existing opt/ copies, and
renewed when its original changes. The markup, its order and every other byte stay as they are.
"""
from io import BytesIO
from pathlib import Path
import os
import re

VIDEO = Path(__file__).resolve().parent / 'video'
WIDTH = 600
QUALITY = 78
SIZES = '(max-width: 700px) 50vw, 660px'
STAGE_CARD = re.compile(r'<a\b[^>]*\bclass="stage-card\b.*?</a>', re.S)
PICTURE_SOURCE = re.compile(r'<source srcset="(/video/[^"\s,]+\.webp)" type="image/webp">')
LIVE_IMAGE = re.compile(r'(<img\b(?=[^>]*\bclass="stage-live")[^>]*?\bsrc="(/video/stage/[^"?]+\.webp)(?:\?[^"]*)?")')


def copy_url(url):
    return '/video/opt/s/' + url[len('/video/'):].replace('/', '_')


def small(original_bytes):
    """(copy bytes, original width) or None when the original is already small or not readable."""
    from PIL import Image
    with Image.open(BytesIO(original_bytes)) as image:
        if image.width <= WIDTH:
            return None
        height = max(1, round(image.height * WIDTH / image.width))
        out = BytesIO()
        image.convert('RGB').resize((WIDTH, height), Image.LANCZOS).save(out, 'WEBP', quality=QUALITY, method=6)
        return out.getvalue(), image.width


def width(path):
    from PIL import Image
    with Image.open(path) as image:
        return image.width


def ensure(url):
    """The copy's URL and the original's width, writing the copy if missing or older; None if not needed."""
    original = VIDEO / url[len('/video/'):]
    target = VIDEO / copy_url(url)[len('/video/'):]
    try:
        if not original.is_file():
            return None
        if not target.is_file() or target.stat().st_mtime < original.stat().st_mtime:
            made = small(original.read_bytes())
            if made is None:
                return None
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name('.' + target.name + '.tmp')
            temporary.write_bytes(made[0])
            os.replace(temporary, target)
        return copy_url(url), width(original)
    except Exception:
        return None  # never block a page write; the page keeps the original picture


def apply(html, find=ensure):
    """Add srcset/sizes to the stage pictures; find(url) gives (copy url, original width) or None."""
    if not isinstance(html, str) or 'stage-card' not in html:
        return html

    def source(match):
        found = find(match[1])
        if not found:
            return match[0]
        return '<source srcset="%s %dw, %s %dw" sizes="%s" type="image/webp">' % (
            found[0], WIDTH, match[1], found[1], SIZES)

    def live(match):
        found = find(match[2])
        if not found:
            return match[0]
        src = re.search(r'\bsrc="([^"]+)"', match[1])[1]
        return '%s srcset="%s %dw, %s %dw" sizes="%s"' % (match[1], found[0], WIDTH, src, found[1], SIZES)

    def card(match):
        if 'srcset="/video/opt/s/' in match[0]:
            return match[0]  # already done
        block = PICTURE_SOURCE.sub(source, match[0])
        return LIVE_IMAGE.sub(live, block)

    return STAGE_CARD.sub(card, html)
