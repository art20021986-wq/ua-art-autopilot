"""Official NBU exchange rates (bank.gov.ua open API, the Korea collector's source): JPY -> USD cross rate."""
import json
import urllib.request

from korea_auction.nbu import NBU_URL


def parse_rates(payload):
    """NBU JSON list -> {'USD': uah_per_usd, 'JPY': uah_per_jpy, 'date': 'dd.mm.yyyy'}."""
    rates = {row['cc']: float(row['rate']) for row in payload if row.get('cc') in ('USD', 'JPY')}
    if set(rates) != {'USD', 'JPY'} or min(rates.values()) <= 0:
        raise ValueError('NBU_RATES_INCOMPLETE')
    rates['date'] = next(row['exchangedate'] for row in payload if row.get('cc') == 'USD')
    return rates


def fetch_rates(timeout=30):
    request = urllib.request.Request(NBU_URL, headers={'User-Agent': 'UA-ART-japan-auction/1'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_rates(json.load(response))


def jpy_to_usd(jpy, rates):
    """JPY amount -> whole USD by the NBU cross rate (UAH per JPY / UAH per USD)."""
    return round(jpy * rates['JPY'] / rates['USD'])
