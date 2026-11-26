"""ua_stage_catalog_sync.py: the catalog status of a Japanese stage-1 car stays «В Японии» / «У Японії»
(JAPAN-STOCK-001 step 2). The stage sync rewrites only the stage word of the status; for a car saved as Japanese
the stage-1 word is the Japan one. Everything else is unchanged.
"""
from edits import replace_once

NAME = 'ua_stage_catalog_sync.py'
PAIRS = (
    ("""PHRASE = re.compile(r'^(\\s*)(В Корее|У Кореї|На пароме""",
     """PHRASE = re.compile(r'^(\\s*)(В Японии|У Японії|В Корее|У Кореї|На пароме"""),
    ('''def _phrase(value, stage, language=None):
    match = PHRASE.match(value)
    if not match:
        raise StageSyncError('STATUS_LABEL_SHAPE')
    ukrainian = language == 'uk' if language else match[2] in {s[3] for s in STAGES.values()}
    label = STAGES[stage][3 if ukrainian else 2]
''', '''def _phrase(value, stage, language=None, country='korea'):
    match = PHRASE.match(value)
    if not match:
        raise StageSyncError('STATUS_LABEL_SHAPE')
    ukrainian = language == 'uk' if language else match[2] in {s[3] for s in STAGES.values()} | {'У Японії'}
    label = STAGES[stage][3 if ukrainian else 2]
    if stage == 1 and country == 'japan':  # JAPAN-STOCK-001
        label = 'У Японії' if ukrainian else 'В Японии'
'''),
    ('''def _patch_article(block, stage):
''', '''def _patch_article(block, stage, country='korea'):
'''),
    ('''        tag = _put(tag, name, _phrase(_attribute(tag, name)[3], stage, language))
    return block[:match.start()] + tag + _phrase(match[2], stage) + match[3] + block[match.end():]
''', '''        tag = _put(tag, name, _phrase(_attribute(tag, name)[3], stage, language, country))
    return block[:match.start()] + tag + _phrase(match[2], stage, country=country) + match[3] + block[match.end():]
'''),
    ('''    seen, changed = set(), []
''', '''    seen, changed = set(), []
    import ua_country_site  # JAPAN-STOCK-001
    japan = ua_country_site.japan_ids()
'''),
    ('''        result = _patch_article(block, stage) if stage else ""
''', '''        country = 'japan' if rows[code].get('id') in japan else 'korea'
        result = _patch_article(block, stage, country) if stage else ""
'''),
)


def build(source):
    text = replace_once(source.decode('utf-8'), PAIRS, NAME)
    compile(text, NAME, 'exec')
    return text.encode('utf-8')
