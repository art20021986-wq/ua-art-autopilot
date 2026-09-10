import html
import re

CARD_RE = re.compile(
    r'<a\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bstage-card\b[^"\']*["\'])'
    r'(?=[^>]*\bdata-stage\s*=\s*["\'](?:kiev|georgia|sea|korea)["\'])'
    r'[^>]*>.*?</a\s*>',
    re.I | re.S,
)

CTA_RE = re.compile(
    r'<i\b(?=[^>]*\bdata-ru\s*=\s*["\'][^"\']*Открыть все автомобили)'
    r'[^>]*>.*?</i\s*>',
    re.I | re.S,
)

class HomeCounterError(RuntimeError):
    pass

def _ru(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        word = "автомобиль"
    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        word = "автомобиля"
    else:
        word = "автомобилей"
    return "%d %s" % (count, word)

def _uk(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        word = "автомобіль"
    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        word = "автомобілі"
    else:
        word = "автомобілів"
    return "%d %s" % (count, word)

def _set_attr(tag: str, name: str, value: str) -> str:
    pattern = re.compile(
        r"\s+" + re.escape(name) + r'\s*=\s*(["\']).*?\1',
        re.I | re.S,
    )
    tag = pattern.sub("", tag)
    if not tag.endswith(">"):
        raise HomeCounterError("INVALID_TAG:" + name)
    return tag[:-1] + ' %s="%s">' % (name, html.escape(value, quote=True))

def _stage_of(block: str) -> str:
    opening = re.match(r"<a\b[^>]*>", block, re.I | re.S)
    if not opening:
        raise HomeCounterError("STAGE_OPENING_MISSING")
    match = re.search(
        r'\bdata-stage\s*=\s*["\'](kiev|georgia|sea|korea)["\']',
        opening.group(0),
        re.I,
    )
    if not match:
        raise HomeCounterError("STAGE_ATTRIBUTE_MISSING")
    return match.group(1).casefold()

def _patch_stage(block: str, stage: str, count: int) -> str:
    opening = re.match(r"<a\b[^>]*>", block, re.I | re.S)
    if not opening:
        raise HomeCounterError("STAGE_OPENING_MISSING:" + stage)
    tag = _set_attr(opening.group(0), "data-count", str(count))
    value = tag + block[opening.end():]
    em_matches = list(re.finditer(r"<em\b[^>]*>.*?</em\s*>", value, re.I | re.S))
    if len(em_matches) != 1:
        raise HomeCounterError("STAGE_COUNT_LABELS:%s:%d" % (stage, len(em_matches)))
    match = em_matches[0]
    old = match.group(0)
    em_open = re.match(r"<em\b[^>]*>", old, re.I | re.S)
    if not em_open:
        raise HomeCounterError("STAGE_EM_OPENING:" + stage)
    em_tag = _set_attr(_set_attr(em_open.group(0), "data-ru", _ru(count)), "data-uk", _uk(count))
    replacement = em_tag + html.escape(_ru(count)) + "</em>"
    return value[:match.start()] + replacement + value[match.end():]

def _patch_cta(source: str, total: int) -> str:
    matches = list(CTA_RE.finditer(source))
    if len(matches) != 1:
        raise HomeCounterError("TOTAL_CTA_COUNT:%d" % len(matches))
    match = matches[0]
    block = match.group(0)
    opening = re.match(r"<i\b[^>]*>", block, re.I | re.S)
    if not opening:
        raise HomeCounterError("TOTAL_CTA_OPENING")
    ru = "Открыть все автомобили · %d" % total
    uk = "Відкрити всі автомобілі · %d" % total
    tag = _set_attr(_set_attr(opening.group(0), "data-ru", ru), "data-uk", uk)
    replacement = tag + html.escape(ru) + "</i>"
    return source[:match.start()] + replacement + source[match.end():]
