"""Official NBU exchange rates (bank.gov.ua open API): KRW -> USD cross rate."""
import json
import urllib.request

NBU_URL = 'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json'


def parse_rates(payload):
    """NBU JSON list -> {'USD': uah_per_usd, 'KRW': uah_per_krw, 'date': 'dd.mm.yyyy'}."""
    rates = {row['cc']: float(row['rate']) for row in payload if row.get('cc') in ('USD', 'KRW')}
    if set(rates) != {'USD', 'KRW'} or min(rates.values()) <= 0:
        raise ValueError('NBU_RATES_INCOMPLETE')
    rates['date'] = next(row['exchangedate'] for row in payload if row.get('cc') == 'USD')
    return rates


def fetch_rates(timeout=30):
    req = urllib.request.Request(NBU_URL, headers={'User-Agent': 'UA-ART-korea-auction/1'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_rates(json.load(r))


def krw_to_usd(krw, rates):
    """KRW amount -> whole USD by NBU cross rate (UAH per KRW / UAH per USD)."""
    return round(krw * rates['KRW'] / rates['USD'])
