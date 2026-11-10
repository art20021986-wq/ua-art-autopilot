"""ua_additional_spec.py (CARD-SYNC-FIX-002): the card builder's external-host guard knows the company's social profiles.

Since SOCIAL-LINKS-001 (owner «Да» 2026-11-10) every page carries the company's Instagram, Telegram, YouTube and
TikTok icons (ua_social_links); the UA115 guard, which refuses a card page with a link to an unapproved external
site, lists t.me but not the other three, so every card publication fails with
UA115_UNAPPROVED_EXTERNAL_HOST:...:www.instagram.com,www.tiktok.com,www.youtube.com (SOCIAL-PROBE-20261110-R3) and
CRM edits stop reaching the site. Three hosts are added to the approved set; the guard itself and every other host
stay as they are. The original fragment must occur exactly once and an applied fragment is refused.
"""
import ast

NAME = 'ua_additional_spec.py'
HOSTS = ('www.instagram.com', 'www.youtube.com', 'www.tiktok.com')
OLD = '    "www.googletagmanager.com",  # CARD-SYNC-FIX-001: the site\'s Google tag (GA4-TAG-001)\n}\n'
NEW = ('    "www.googletagmanager.com",  # CARD-SYNC-FIX-001: the site\'s Google tag (GA4-TAG-001)\n'
       + ''.join('    "%s",  # CARD-SYNC-FIX-002: company social profile (SOCIAL-LINKS-001)\n' % h for h in HOSTS) + '}\n')


def approved_hosts(text):
    """The _UA115_APPROVED_HOSTS literal of the module text."""
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == '_UA115_APPROVED_HOSTS' for t in node.targets):
            return set(ast.literal_eval(node.value))
    raise ValueError('APPROVED_HOSTS_MISSING')


def build(name, source):
    text = source.decode('utf-8')
    before = approved_hosts(text)
    if text.count(OLD) != 1 or before & set(HOSTS):
        raise ValueError('SPEC_FRAGMENT:' + name)
    text = text.replace(OLD, NEW)
    if approved_hosts(text) != before | set(HOSTS):
        raise ValueError('SPEC_HOSTS:' + name)
    return text.encode('utf-8')
