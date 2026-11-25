"""ua_order/host.py: the site application also answers GET /api/google-ads/oauth (module ua_google_ads_oauth_web).

The consent callback is put in front of the site, after the auction login, isolated: if it cannot load, everything
else works as before. Fragment edit; the original must occur once (ADS-KEYS-001).
"""
NAME = 'ua_order/host.py'
OLD = ("        log.error('Auction login unavailable (%s)', type(exc).__name__)\n"
       "    loaded = current()\n")
NEW = ("        log.error('Auction login unavailable (%s)', type(exc).__name__)\n"
       "    try:  # ADS-KEYS-001: the one-time Google Ads consent callback (/api/google-ads/oauth)\n"
       "        import ua_google_ads_oauth_web\n"
       "        application = ua_google_ads_oauth_web.mount(application)\n"
       "    except Exception as exc:\n"
       "        log.error('Google Ads consent callback unavailable (%s)', type(exc).__name__)\n"
       "    loaded = current()\n")


def build(source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or 'ua_google_ads_oauth_web' in text:
        raise ValueError('ORDER_HOST_FRAGMENT_NOT_UNIQUE')
    return text.replace(OLD, NEW).encode('utf-8')
