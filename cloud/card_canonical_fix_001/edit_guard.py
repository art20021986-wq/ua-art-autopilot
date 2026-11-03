"""master_card.py (CARD-CANONICAL-FIX-001): the publication check accepts a card's language-version canonical.

The write-time check (SEO068, proverit) requires a card's canonical to be exactly /video/UA-XXXX.html, while
CARD-LANG-001 (owner «Да» 2026-10-30) made the canonical of a card with language versions its Ukrainian version
/video/ua/UA-XXXX.html (ua_seo_metadata via ua_card_lang.canonical). Every card publication is refused with
«SEO068 canonical». The check now accepts exactly one canonical that is one of these two addresses; every
other part of the check (one canonical, no noindex, the deposit button, the diagnostics link) is unchanged.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'master_card.py'
OLD = ("        expected = _UA_SEO068_ORIGIN + '/video/' + file_name\n"
       "        canonicals = _ua_seo068_re.findall(")
NEW = ("        expected = _UA_SEO068_ORIGIN + '/video/' + file_name\n"
       "        # CARD-CANONICAL-FIX-001: a card with language versions names its Ukrainian version (CARD-LANG-001).\n"
       "        allowed = [expected, _UA_SEO068_ORIGIN + '/video/ua/' + file_name] if kod else [expected]\n"
       "        canonicals = _ua_seo068_re.findall(")
OLD_CHECK = "        if canonicals != [expected]:\n            errors.append('SEO068 canonical')\n"
NEW_CHECK = "        if len(canonicals) != 1 or canonicals[0] not in allowed:\n            errors.append('SEO068 canonical')\n"


def build(name, source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or text.count(OLD_CHECK) != 1 or 'CARD-CANONICAL-FIX-001' in text:
        raise ValueError('GUARD_FRAGMENT:' + name)
    text = text.replace(OLD, NEW).replace(OLD_CHECK, NEW_CHECK)
    compile(text, name, 'exec')
    return text.encode('utf-8')
