"""Source-pinned, inert build; does not import the live bot or write production."""
import ast
import hashlib
from pathlib import Path

SOURCE_SHA256 = {'team_bot.py': 'aebe2c091fdf1f19a8a011784dd70e2d648dc04607ec64374e4ff9f402e995af'}
DEPENDENCY_SHA256 = {
    'ai_filter.py': '7dfd84497c6d3823cd7df54834cb18aecdbc645544ca9709a88c6363a2d35cb6',
    'local_ocr.py': 'd236fe3c30792217370e403061c2cb532f4cab2cc3198e29146dd588a1317b45',
    'db.py': 'af7624cbcf227b865ac98c68462ad6da8d18223881bba836f2f9a8669cf1dab7',
    'cars_schema.py': '16d53277834ecfad1eabc10f75e5cabb1060b35416b61b6f534ec024ce9dbc07',
}
MODULES = ('crm_explicit_fields.py', 'crm_intake_store.py', 'crm_photo_intake.py')


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('SOURCE_DRIFT:' + name)
    original = source['team_bot.py'].decode()
    anchor = '    cars_ui.register(app)\n'
    if original.count(anchor) != 1:
        raise ValueError('REGISTRATION_ANCHOR')
    insertion = ('    import crm_photo_intake\n    import local_ocr\n'
                 '    crm_photo_intake.register(app, db, ai_filter, local_ocr, ai)\n')
    candidate = {'team_bot.py': original.replace(anchor, anchor + insertion).encode()}
    candidate.update({name: (Path(__file__).parent / name).read_bytes() for name in MODULES})
    for name, value in candidate.items():
        ast.parse(value, filename=name)
        compile(value, name, 'exec')
    return candidate
