"""master_card.py (CARD-CANONICAL-RU-001): the publication check also accepts the card's Russian version
/video/ru/UA-XXXX.html as its canonical (ua_card_lang.canonical now names it). Exactly one canonical is still
required, and only the card's own addresses are accepted; the rest of the check is unchanged. The original
fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'master_card.py'
OLD = "        allowed = [expected, _UA_SEO068_ORIGIN + '/video/ua/' + file_name] if kod else [expected]\n"
NEW = ("        # CARD-CANONICAL-RU-001: or its Russian version, the same language as the card page.\n"
       "        allowed = [expected, _UA_SEO068_ORIGIN + '/video/ua/' + file_name,\n"
       "                   _UA_SEO068_ORIGIN + '/video/ru/' + file_name] if kod else [expected]\n")


def build(source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or 'CARD-CANONICAL-RU-001' in text:
        raise ValueError('GUARD_FRAGMENT')
    text = text.replace(OLD, NEW)
    compile(text, NAME, 'exec')
    return text.encode('utf-8')
