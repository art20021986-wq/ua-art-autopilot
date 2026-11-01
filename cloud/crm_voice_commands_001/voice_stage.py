"""Delivery stage from an owner's voice note («Автомобиль находится в Киеве»).

Pure: exactly one stage place and a cue that the sentence is about where the car is (a verb such
as «находится», the word «этап», or a short phrase like «уже в Киеве»); anything else is None.
"""
import re

from ua_delivery_status import storage_status

# Public stage code -> where the car is (RU/UK, the forms used for location).
PLACES = {
    'korea': r'(?:в|у)\s+коре[еиї]',
    'ferry': r'на\s+(?:пароме|паромі|море|морі)',
    'georgia': r'(?:в|у)\s+(?:грузи[иії]|батуми|поти)',
    'kyiv': r'(?:в|у)\s+(?:киеве|києві|киев|київ)',
}
CUE = re.compile(r'наход|знаход|стоит|стоїть|прибыл|прибув|приехал|приїхав|доехал|доїхав|'
                 r'уже|вже|сейчас|зараз|этап|етап|статус')
SHORT = 4  # «уже в Киеве», «машина в Киеве»: short phrases need no verb
_PLACES = {code: re.compile(r'(?<![а-яіїєґa-z])' + pattern + r'(?![а-яіїєґa-z])') for code, pattern in PLACES.items()}


def stage_code(text):
    """CRM storage code of the one stage the sentence names, or None."""
    value = str(text or '').casefold().replace('ё', 'е')
    found = [code for code, pattern in _PLACES.items() if pattern.search(value)]
    words = re.findall(r'[а-яіїєґa-z]+', value)
    if len(found) != 1 or not (CUE.search(value) or len(words) <= SHORT):
        return None
    return storage_status(found[0])

