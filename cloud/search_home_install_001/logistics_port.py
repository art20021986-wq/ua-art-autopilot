"""Korea logistics prices file: port costs in Georgia 250 -> 400 $ (SEARCH-HOME-001, owner «Да» 2026-11-26 12:33 UTC).

Only the 'port' of every month in video/korea/logistics.json; written in the same format as the prices bot
(ua_kr_prices_store.save_month), so the bot keeps reading and editing it.
"""
import json

PORT = 400
KEYS = ('fob', 'container', 'port', 'truck', 'broker', 'cert')


def build(value):
    data = json.loads(value.decode('utf-8'))
    months = data.get('months') if isinstance(data, dict) and data.get('version') == 1 else None
    if not isinstance(months, dict) or not months or any(set(p) != set(KEYS) for p in months.values()):
        raise ValueError('KOREA_LOGISTICS_LAYOUT')
    for prices in months.values():
        prices['port'] = PORT
    return json.dumps({'version': 1, 'months': dict(sorted(months.items()))}, ensure_ascii=False,
                      sort_keys=True, indent=1).encode('utf-8')
