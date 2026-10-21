"""Old URLs and sendData become editable drafts, never false saved receipts."""
import re
from uuid import uuid4

from .catalog import COUNTRIES
from .contract import Invalid, SCHEMA, text


def deep_link(value):
    match = re.fullmatch(r'z_([a-z]+)(?:_(b[1-4]))?(?:_(k[1-4]))?', value)
    if not match or match[1] not in COUNTRIES:
        return None
    return dict(purchase_country_code=match[1], budget={'code': match[2] or 'undecided', 'currency': 'USD'},
                vehicle_type=match[3] or 'any')


def draft(payload, catalog):
    if not isinstance(payload, dict) or set(payload) - {'t', 's', 'b', 'k', 'm', 'mo', 'txt'}:
        raise Invalid('legacy_fields')
    if payload.get('t') != 'podbor' or payload.get('s') not in COUNTRIES:
        raise Invalid('legacy_country')
    comment = text(payload.get('txt', ''), 'comment', maximum=2000)
    m = text(payload.get('m', ''), 'model', maximum=2200)
    mo = text(payload.get('mo', ''), 'model', maximum=2200)
    # The observed old site duplicates txt as a suffix in mo. Remove that exact
    # suffix only, preserving arbitrary free text and all other occurrences.
    if comment:
        suffix = ' · хочет: ' + comment
        if mo.endswith(suffix):
            mo = mo[:-len(suffix)]
        elif mo == 'хочет: ' + comment:
            mo = ''
    if m and mo and m != mo:
        raise Invalid('legacy_model_conflict')
    label = m or mo
    country = payload['s']
    matched = next((model for model in catalog.country(country)['models']
                    if label in (model['name'], *model['labels'].values())), None)
    budget = payload.get('b') or 'undecided'
    kind = payload.get('k') or 'any'
    if not isinstance(budget, str) or budget not in catalog.choices('budgets'):
        raise Invalid('budget')
    if not isinstance(kind, str) or kind not in catalog.choices('vehicle_types'):
        raise Invalid('vehicle_type')
    return dict(schema_version=SCHEMA, request_id=str(uuid4()), config_version=catalog.version,
                purchase_country_code=country, model=matched['key'] if matched else '',
                other_model='' if matched else text(label, 'other_model', maximum=120),
                budget={'code': budget, 'currency': 'USD'}, vehicle_type=kind,
                comment=comment, lang='uk', source_path='/telegram')
