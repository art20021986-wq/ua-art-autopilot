"""Owner-approved customs captions, branch-only; not wired into the live renderer.

No price inputs, conversion, DB access, HTML writes or network operations.
Confirmation of customs clearance does not establish delivery/certification
inclusion or justify a new all-inclusive/no-extra-charges claim.
"""

_CAPTIONS = {
    "ru": {
        "ukraine": "Украина — с растаможкой в Украине",
        "georgia": "Грузия — без растаможки в Грузии",
    },
    "uk": {
        "ukraine": "Україна — з розмитненням в Україні",
        "georgia": "Грузія — без розмитнення в Грузії",
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
