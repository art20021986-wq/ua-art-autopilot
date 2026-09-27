"""Shipment identifiers and public tracking destinations; no network or storage."""
import re
from urllib.parse import quote, urlencode


def normalize(value):
    """Normalize human spacing only. Never truncate or guess a shipment number."""
    if not isinstance(value, str):
        return ''
    value = re.sub(r'\s+', '', value).upper()
    return value if re.fullmatch(r'[A-Z0-9][A-Z0-9/-]{3,63}', value, re.ASCII) else ''


def reference_kind(number):
    if re.fullmatch(r'[A-Z]{3}U[0-9]{7}', number):
        return 'container'
    # Existing CRM sea_container also contains ONE master bills of lading.
    if re.fullmatch(r'ONEY[A-Z0-9]{6,32}', number):
        return 'one_bl'
    return 'reference'


def tracking_links(value):
    number = normalize(value)
    if not number:
        return []
    kind = reference_kind(number)
    fragment = quote(number, safe='')
    links = []
    if kind == 'one_bl':
        links.append(('ONE', 'https://ecomm.one-line.com/one-ecom/manage-shipment/cargo-tracking?'
                      + urlencode({'trakNoParam': number[4:]}), 'direct'))
    if kind == 'container':
        links.append(('Track-Trace', 'https://track-trace.com/container#' + fragment, 'prefilled'))
    else:
        links.append(('Track-Trace · B/L', 'https://track-trace.com/bol#' + fragment, 'prefilled'))
        if kind == 'reference':
            links.append(('Track-Trace · Container', 'https://track-trace.com/container#' + fragment, 'prefilled'))
    links.extend((('SeaRates', 'https://www.searates.com/container/tracking/', 'manual'),
                  ('ShipsGo', 'https://shipsgo.com/ocean', 'manual')))
    return links
