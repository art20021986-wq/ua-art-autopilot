"""Owner-approved price captions, branch-only; not wired into the live renderer.

No price inputs, conversion, DB access, HTML writes or network operations.
Ukraine: customs included; delivery/certification inclusion not established.
Georgia: delivery to AUTOPAPA parking16 included; Georgian customs excluded.
No storage fees, parking duration or all-inclusive promise is inferred.
"""

_CAPTIONS = {
    "ru": {
        "ukraine": "Украина — с растаможкой в Украине",
        "georgia": "Грузия — с доставкой до авторынка AUTOPAPA, паркинг №16; без растаможки в Грузии",
    },
    "uk": {
        "ukraine": "Україна — з розмитненням в Україні",
        "georgia": "Грузія — з доставкою до авторинку AUTOPAPA, паркінг №16; без розмитнення в Грузії",
    },
}


def price_caption(market: str, language: str = "ru") -> str:
    """Return only the approved caption; reject unsupported labels/languages."""
    if type(language) is not str or type(market) is not str:
        raise ValueError("EXACT_STRING_MARKET_AND_LANGUAGE_REQUIRED")
    language = "uk" if language == "ua" else language
    if language not in _CAPTIONS or market not in _CAPTIONS[language]:
        raise ValueError("UNSUPPORTED_MARKET_OR_LANGUAGE")
    return _CAPTIONS[language][market]
