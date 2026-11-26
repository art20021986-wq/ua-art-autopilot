"""catalog_design_guard.py: catalog cards and counters with the car country (JAPAN-STOCK-001 step 2).

- each catalog card gets data-country="korea|japan" (the country row of the golden page filters by it);
- a stage-1 card of a Japanese car says «В Японии · выкуплен и проверен»;
- the stage-1 filter button is «Выкуплены · N» / «Викуплені · N»: its number is recounted and normalized for the
  shell fingerprint like the other stage buttons.
"""
from edits import replace_once

NAME = 'catalog_design_guard.py'
PAIRS = (
    ('''    block = _patch_opening(block, stage)
''', '''    block = _patch_opening(block, stage)
    block = _set_attribute(block[:block.index(">") + 1], "data-country", row.get("_ua_country") or "korea") \\
        + block[block.index(">") + 1:]  # JAPAN-STOCK-001
'''),
    ('''    label_ru, label_uk = PUBLIC_LABELS[stage]
''', '''    label_ru, label_uk = PUBLIC_LABELS[stage]
    if stage == 1 and row.get("_ua_country") == "japan":  # JAPAN-STOCK-001
        import ua_country_site
        label_ru, label_uk = ua_country_site.CATALOG_JAPAN_LABEL
'''),
    ('''        (r"(?i)(В Корее|У Кореї)\\s*·\\s*\\d+", r"\\1 · #"),
''', '''        (r"(?i)(В Корее|У Кореї)\\s*·\\s*\\d+", r"\\1 · #"),
        (r"(?i)(Выкуплены|Викуплені)\\s*·\\s*\\d+", r"\\1 · #"),
'''),
    ('''        (r"У Кореї\\s*·\\s*\\d+", "У Кореї · %d" % counts["korea"]),
''', '''        (r"У Кореї\\s*·\\s*\\d+", "У Кореї · %d" % counts["korea"]),
        (r"Выкуплены\\s*·\\s*\\d+", "Выкуплены · %d" % counts["korea"]),
        (r"Викуплені\\s*·\\s*\\d+", "Викуплені · %d" % counts["korea"]),
'''),
    ('''    row_map = _rows_by_id(rows)
    baseline_order''', '''    row_map = _rows_by_id(rows)
    import ua_country_site  # JAPAN-STOCK-001: the country of each card
    japan = ua_country_site.japan_ids()
    for row in row_map.values():
        row["_ua_country"] = "japan" if row.get("id") in japan else "korea"
    baseline_order'''),
)


def build(source):
    text = replace_once(source.decode('utf-8'), PAIRS, NAME)
    compile(text, NAME, 'exec')
    return text.encode('utf-8')
