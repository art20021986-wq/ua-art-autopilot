"""Shipment identifiers and public tracking destinations; no network or storage."""
import re
from urllib.parse import urlencode


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
    """Start SeaRates search with the complete reference; results remain external."""
    number = normalize(value)
    if not number:
        return []
    return [('SeaRates', 'https://www.searates.com/container/tracking/?'
             + urlencode({'number': number, 'sealine': 'AUTO'}), 'direct')]
