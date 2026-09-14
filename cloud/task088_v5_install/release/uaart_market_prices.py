"""Pure Stage 3 price component. No CRM/file/network writes or currency conversion."""

from decimal import Decimal, InvalidOperation
from html import escape
import re

VERSION = "task088-market-prices-final-v5"
START = "<!-- UA-ART-MARKET-PRICES-V1:START -->"
END = "<!-- UA-ART-MARKET-PRICES-V1:END -->"

COUNTRIES = {
    "ukraine": {"ru": "Украина", "uk": "Україна", "ka": "უკრაინა"},
    "georgia": {"ru": "Грузия", "uk": "Грузія", "ka": "საქართველო"},
}
FLAGS = {"ukraine": "🇺🇦", "georgia": "🇬🇪"}
CAPTIONS = {
    "ukraine": {
        "ru": "Цена с доставкой в Киев с растаможкой и сертификацией",
        "uk": "Ціна з доставкою до Києва з розмитненням і сертифікацією",
        "ka": "ფასი კიევში მიწოდებით, განბაჟებითა და სერტიფიცირებით",
    },
    "georgia": {
        "ru": "Цена автомобиля с доставкой до авторынка Рустави 🅿️ №16",
        "uk": "Ціна автомобіля з доставкою до авторинку Руставі 🅿️ №16",
        "ka": "ავტომობილის ფასი რუსთავის ავტობაზრობამდე მიწოდებით 🅿️ №16",
    },
}
MISSING = {"ru": "Цена уточняется", "uk": "Ціна уточнюється", "ka": "ფასი ზუსტდება"}


def georgia_price_visible(row):
    """Kyiv cars show UA only; stored GE stays independent and untouched.

    Match the inspected CRM stage resolver: ua_* and sold/archive are stage 4.
    Missing/unknown status preserves the existing two-market presentation.
    """
    status = str(row.get("status") or "").strip().lower()
    return not (status.startswith("ua_") or status in ("sold", "archive"))


def normalized_usd(value):
    """Return an exact USD decimal string; no truncation, rounding, or FX conversion.

    Existing nullable/empty/zero fields mean no price. Invalid data blocks rendering
    instead of silently publishing an invented amount. Existing numeric CRM values
    are accepted; input parsing and persistence remain the CRM's responsibility.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError("PRICE_VALUE_TYPE_INVALID")
    text = str(value).strip()
    if not text:
        return ""
    if len(text) > 48 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
        raise ValueError("PRICE_VALUE_FORMAT_INVALID")
    try:
        amount = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("PRICE_VALUE_INVALID") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError("PRICE_VALUE_INVALID")
    if amount == 0:
        return ""
    canonical = format(amount, "f").rstrip("0").rstrip(".") if "." in text else str(amount)
    if "." in canonical and len(canonical.split(".", 1)[1]) > 2:
        raise ValueError("PRICE_VALUE_FRACTION_INVALID")
    return canonical


def _translated(texts):
    """Use existing site language attributes; this component changes no language JS."""
    return ('<span style="font:inherit;color:inherit;letter-spacing:normal" data-ru="%s" data-ua="%s" data-uk="%s" data-ge="%s" data-ka="%s">%s</span>'
            % tuple(escape(texts[key], quote=True) for key in ("ru", "uk", "uk", "ka", "ka", "ru")))


def _amount(canonical):
    if not canonical:
        return _translated(MISSING)
    integer, separator, fraction = canonical.partition(".")
    chunks = []
    while integer:
        chunks.append(integer[-3:])
        integer = integer[:-3]
    return " ".join(reversed(chunks)) + (separator + fraction if separator else "") + " $"


def render_market_prices(row, compact=False, require_car_id=False):
    """Return stage-appropriate price blocks from independent CRM fields.

    Only the returned fragment changes. No global CSS, scripts, links, selectors,
    shared state, or data mutation. GE is omitted for Kyiv cars; otherwise empty
    Georgia stays visible with a placeholder. Both stored amounts are validated.
    """
    if not hasattr(row, "get") or type(compact) is not bool or type(require_car_id) is not bool:
        raise ValueError("PRICE_COMPONENT_INPUT_INVALID")
    car_id = row.get("auto_number")
    if car_id in (None, "") and not require_car_id:
        car_id = ""
    elif type(car_id) is not str or not re.fullmatch(r"UA-[0-9]{4}", car_id):
        raise ValueError("PRICE_COMPONENT_CAR_ID_INVALID")
    prices = [(market, field, normalized_usd(row.get(field))) for market, field in (
        ("ukraine", "price_uah"), ("georgia", "price_georgia"))]
    if not prices[0][2] and normalized_usd(row.get("price_total")):
        # The inspected stranica.cena historically falls back to price_total.
        # Do not conceal, copy or migrate an existing public price silently.
        raise ValueError("LEGACY_UA_PRICE_FALLBACK_REQUIRES_RECONCILIATION")
    out = [START, '<div class="ua-market-prices-v1" data-ua-price-version="%s" data-ua-car="%s" '
           'style="display:flex;flex-direction:column;gap:9px;min-width:0;max-width:100%%;overflow-wrap:anywhere">' % (VERSION, car_id)]
    for index, (market, field, value) in enumerate(prices):
        if market == "georgia" and not georgia_price_visible(row):
            continue
        border = "" if compact or index == 0 else "border-top:1px solid rgba(147,166,189,.35);padding-top:9px;"
        out.append('<div data-ua-market="%s" data-ua-field="%s" data-ua-value="%s" '
                   'data-ua-currency="USD" style="%smin-width:0">'
                   % (market, field, escape(value, quote=True), border))
        amount = _amount(value)
        if value:
            # Country names and nullable text may wrap inside the existing
            # narrow tile. Keep a real amount and its USD sign together.
            amount = '<span class="ua-market-value-v1" style="font:inherit;color:inherit;letter-spacing:normal;white-space:nowrap">%s</span>' % amount
        out.append('<div class="ua-market-amount-v1" style="font-size:%spx;font-weight:800;line-height:1.35;color:var(--zoloto,#f0a63c)">%s %s — %s</div>'
                   % ("16" if compact else "25", FLAGS[market], _translated(COUNTRIES[market]), amount))
        if not compact:
            out.append('<div class="ua-market-caption-v1" style="font-size:14px;line-height:1.4;opacity:.85;margin-top:4px">%s</div>'
                       % _translated(CAPTIONS[market]))
        out.append("</div>")
    out.extend(["</div>", END])
    return "".join(out)


def replace_catalog_price_slot(article, row):
    """Replace only the price node in the approved modern catalog-top element.

    Called after the golden renderer has bound every article identifier to its
    current CRM row. The immutable catalog shell and all non-price nodes remain
    untouched. Already marked prototypes are supported without duplicate blocks.
    """
    component = render_market_prices(row, compact=True, require_car_id=True)
    code = row["auto_number"]
    if not isinstance(article, str) or set(re.findall(r"UA-[0-9]{4,}", article)) != {code}:
        raise ValueError("CATALOG_PRICE_CAR_ID_MISMATCH")
    # The old golden builder preferred these aliases before price_uah. A
    # disagreement is explicit reconciliation work, not permission to alter price.
    canonical = normalized_usd(row.get("price_uah"))
    for key in ("price", "price_usd", "price_uah", "sale_price", "price_final"):
        value = row.get(key)
        if value in (None, "", 0, "0"):
            continue
        try:
            old = normalized_usd(value)
        except ValueError as error:
            # Legacy _money uses float(), accepting scientific/negative/bool
            # aliases our canonical parser rejects. Never skip such an alias
            # and silently change the previously selected public amount.
            raise ValueError("LEGACY_CATALOG_UA_PRICE_REQUIRES_RECONCILIATION") from error
        if old != canonical:
            raise ValueError("LEGACY_CATALOG_UA_PRICE_REQUIRES_RECONCILIATION")
        break
    tops = list(re.finditer(r'<div\b[^>]*\bclass=["\'][^"\']*\bcatalog-top\b[^"\']*["\'][^>]*>', article, re.I))
    if len(tops) != 1:
        raise ValueError("CATALOG_PRICE_CONTAINER_COUNT")
    top = tops[0]
    depth, top_end = 0, None
    for token in re.finditer(r"<div\b[^>]*>|</div\s*>", article[top.start():], re.I):
        depth += -1 if token.group(0).lower().startswith("</") else 1
        if depth == 0:
            top_end = top.start() + token.start()
            break
    if top_end is None:
        raise ValueError("CATALOG_PRICE_CONTAINER_UNBALANCED")
    inside = article[top.end():top_end]
    if START in article or END in article:
        if article.count(START) != 1 or article.count(END) != 1 or START not in inside or END not in inside:
            raise ValueError("CATALOG_PRICE_MARKER_LOCATION")
        start = article.index(START)
        end = article.index(END, start) + len(END)
    else:
        prices = list(re.finditer(r"<b\b[^>]*>[^<]*</b\s*>", inside, re.I))
        if len(prices) != 1:
            raise ValueError("CATALOG_PRICE_NODE_COUNT")
        start, end = top.end() + prices[0].start(), top.end() + prices[0].end()
    return article[:start] + component + article[end:]
