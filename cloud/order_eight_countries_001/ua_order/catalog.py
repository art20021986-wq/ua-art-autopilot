"""One immutable, versioned catalogue shared by all adapters."""
import copy
import json
from pathlib import Path

COUNTRIES = ('korea', 'japan', 'usa', 'europe', 'china', 'canada', 'uae', 'georgia')
LANGUAGES = ('uk', 'ru', 'ka')


class Catalog:
    def __init__(self, path):
        self._data = json.loads(Path(path).read_text(encoding='utf-8'))
        if tuple(self._data['countries']) != COUNTRIES:
            raise ValueError('Invalid country order')
        self.version = self._data['version']
        for code, country in self._data['countries'].items():
            models = country['models']
            if country['code'] != code or len(models) != 5:
                raise ValueError('Invalid country catalogue')
            if len({m['key'] for m in models}) != 5:
                raise ValueError('Duplicate model key')
            for model in models:
                if set(model['labels']) != set(LANGUAGES):
                    raise ValueError('Missing model translation')

    def export(self):
        return copy.deepcopy(self._data)

    def country(self, code):
        return copy.deepcopy(self._data['countries'][code])

    def model(self, country, key):
        return next((copy.deepcopy(m) for m in self._data['countries'][country]['models']
                     if m['key'] == key), None)

    def choices(self, field):
        return copy.deepcopy(self._data[field])

    def media_gaps(self):
        return [f'{c}/{m["key"]}' for c in COUNTRIES
                for m in self._data['countries'][c]['models']
                if not m['media']['path'] or not m['media']['source']
                or m['media']['approval'] != 'approved']
