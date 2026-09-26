"""Build source-pinned candidates; never install or modify a live service."""

import ast
import hashlib


SOURCE_SHA256 = {
    "db.py": "cee4e2da897a136c4471e85a115d018a9ea94134e7ec187f50fa90e03e5d8a6d",
    "cars_ui.py": "63a926d752d1c0662c8700521db748d1dff98276df168e9ce693bd9e7c2a378b",
    "konteyner.py": "bdf6b953e95cf5ae78d3d640b9ba438202e9708d48cb1c7f4e1556bb59921824",
    "cars_schema.py": "1dd5d950eb4514901ca51911b4c5f89481263956ceea28f30e1fa2888cdd8d73",
    "stranica.py": "cdb532f36e6e8fd17c7f933ad347a8bb0bcd8c00644d9c8ea7d9e3ddbb6ae687",
    "master_card.py": "27e32420bbec9f1e0a25621e1c20dda20944537daa40c1ccac574689cd6c3f6e",
    "publish_transaction_guard.py": "b1e89bfcbe4af4890d1023293cb8290f34b6c59673b7a8e692ab64928f640159",
    "ua_stage_catalog_sync.py": "c349d44821f92950234705d41507587c3ca2780dd750abda0028c060569a5beb",
    "catalog_design_guard.py": "51127bbc2be949e1d37f7b6995c0e5a7a32a497c8436139322ce5b0fea308d60",
    "ua_crm_public_sync.py": "31e47106dc65ac1a2e013708bd58112fc1fffae06445351ea5f08246cf984e5c",
}


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("SOURCE_ANCHOR_COUNT")
    return source.replace(old, new, 1)


def replace_function(source, name, transform, *, final=False):
    nodes = [n for n in ast.parse(source).body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if not nodes or (not final and len(nodes) != 1):
        raise ValueError("FUNCTION_COUNT:" + name)
    node = nodes[-1]
    before = ast.get_source_segment(source, node)
    after = transform(before)
    lines = source.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1]))
    end = start + len(before)
    candidate = source[:start] + after + source[end:]
    compile(candidate, name, "exec")
    return candidate


def inject_function(source, statement):
    node = ast.parse(source).body[0]
    body = node.body
    docstring = (isinstance(body[0], ast.Expr)
                 and isinstance(body[0].value, ast.Constant)
                 and isinstance(body[0].value.value, str))
    if docstring and len(body) == 1:
        raise ValueError("EMPTY_FUNCTION")
    before = body[1] if docstring else body[0]
    lines = source.splitlines(keepends=True)
    offset = sum(map(len, lines[:before.lineno - 1]))
    return source[:offset] + statement + source[offset:]


def patch_menu(source):
    source = inject_function(source, "    from ua_delivery_status import CHOICES, public_status\n")
    source = once(source, 'stage = S.stage_of(card.get("status")) or 1',
                  'stage = S.stage_of(card.get("status"))')
    source = once(source, '("• " if card.get("status") == code else "")',
                  '("• " if public_status(card.get("status")) == code else "")')
    source = once(source, 'for code, (stage_no, label) in S.STATUSES.items() if stage_no == number and code not in _UA117_HIDDEN_STATUS_CODES',
                  'for code, _stored, stage_no, label in CHOICES if stage_no == number')
    return once(source, '"Этап %d из 4: %s" % (stage, dict(S.STAGES).get(stage, "—"))',
                '("Этап %d из 4: %s" % (stage, dict(S.STAGES).get(stage, "—")) if stage else "Скрыт из каталога")')


def patch_stage_set(source):
    source = inject_function(source, "    from ua_delivery_status import crm_status_from_input\n")
    start = source.index('    _, cid, code = q.data.split(":")')
    end = source.index('    card_before = card_of(cid)', start)
    source = source[:start] + '''    try:
        _, raw_id, requested = q.data.split(":", 2)
        cid = int(raw_id)
    except (AttributeError, TypeError, ValueError):
        await q.message.reply_text("Некорректная кнопка этапа. Откройте карточку заново.")
        raise ApplicationHandlerStop
    code = crm_status_from_input(requested)
''' + source[end:]
    source = once(source, '    card_before = card_of(cid)\n', '''    card_before = card_of(cid)
    if not card_before:
        await q.message.reply_text("Карточка не найдена.")
        raise ApplicationHandlerStop
''')
    start = source.index('    if code == "ge_to_kyiv":')
    end = source.index('    card = card_of(cid)', start)
    return source[:start] + source[end:]


def patch_stage_router(source):
    return once(source,
                'pattern=r"^car_setstage:\\d+:(?:sea_loaded|sea_transit|ua_handed)$"',
                'pattern=r"^car_setstage:"')


def patch_fallback_menu(source):
    source = inject_function(source, "    from ua_delivery_status import CHOICES, public_status\n")
    source = once(source, '("• " if card.get("status") == code else "")',
                  '("• " if public_status(card.get("status")) == code else "")')
    return once(source,
                'for code, (stage_no, label) in S.STATUSES.items()\n'
                '                if stage_no == nomer_etapa and code not in _UA117_HIDDEN_STATUS_CODES',
                'for code, _stored, stage_no, label in CHOICES\n'
                '                if stage_no == nomer_etapa')


def patch_sync(source):
    source = replace_function(source, "stage_of", lambda _: '''def stage_of(row):
    from ua_delivery_status import stage_number
    return stage_number(row.get('status'))''')
    source = once(source, '        result = _patch_article(block, stage_of(rows[code]))',
                  '        stage = stage_of(rows[code])\n        result = _patch_article(block, stage) if stage else ""')
    source = once(source, '    if seen != set(rows):',
                  '    visible = {code for code, row in rows.items() if stage_of(row)}\n    if seen & visible != visible:')
    source = once(source, '    candidate = ARTICLE.sub(replace, source)', '''    spans = list(ARTICLE.finditer(source))
    for left, right in zip(spans, spans[1:]):
        if source[left.end():right.start()].strip():
            raise StageSyncError("CATALOG_CARD_GAP")
    blocks = [replace(match) for match in spans]
    candidate = source
    if spans:
        rendered = "\\n".join(block for block in blocks if block)
        candidate = (source[:spans[0].start()]
                     + (rendered or "<!--UA090:CARD-REGION-->")
                     + source[spans[-1].end():])''')
    source = once(source, '        rows, digest = pub._row_map()',
                  '        all_rows, digest = pub._row_map(include_hidden=True)\n        rows = {code: row for code, row in all_rows.items() if stage_of(row)}')
    source = once(source, "patch_catalog_stages(before.decode('utf-8'), rows)",
                  "patch_catalog_stages(before.decode('utf-8'), all_rows)")
    return once(source, '        for code in changed_ids:\n',
                '        for code in changed_ids:\n            if code not in rows:\n                continue\n')


def patch_publisher_rows(source):
    source = once(source, 'def _rows()', 'def _rows(*, include_hidden=False)')
    source = inject_function(source, '    from ua_delivery_status import stage_number\n')
    return once(source, '    return rows, _sha(normalized)',
                '    visible = rows if include_hidden else [row for row in rows if stage_number(row.get("status"))]\n    return visible, _sha(normalized)')


def patch_catalog_design(source):
    source = replace_function(source, "stage_number", lambda _: '''def stage_number(row):
    from ua_delivery_status import stage_number as delivery_stage
    return delivery_stage(row.get("status"))''')
    source = replace_function(source, "_rows_by_id", lambda s: once(once(s,
        '        if published != 1:', '        if published != 1 or not stage_number(row):'),
        '    if not result:\n        raise CatalogDesignError("NO_PUBLISHED_ROWS")\n', ''))
    source = replace_function(source, "build_catalog", lambda s: once(s,
        '        + "\\n".join(cards)',
        '        + ("\\n".join(cards) if cards else "<!--UA090:CARD-REGION-->")'))
    return replace_function(source, "audit_catalog", lambda s: once(s,
        '    shell = shell_audit(source)',
        '    shell = shell_audit(source, require_cards=bool(row_map))'))


def patch_master_catalog(source):
    source = inject_function(source, '    from ua_delivery_status import stage_number\n')
    source = once(source, '        if _published != 1:',
                  '        if _published != 1 or not stage_number(_row.get("status")):')
    return once(source, '    if not _rows:\n        raise RuntimeError("TASK090_NO_PUBLISHED_ROWS")\n', '')


def patch_public_sync(source):
    source = replace_function(source, "snapshot", lambda s: once(
        inject_function(s, '    from ua_delivery_status import public_status\n'),
        "        result[str(row['id'])] = {'code': code, 'sha256': hashlib.sha256(raw).hexdigest()}",
        "        result[str(row['id'])] = {'code': code, 'sha256': hashlib.sha256(raw).hexdigest(), 'delivery_status': public_status(row.get('status'))}"))
    source = once(source, "            if revision == state['revisions'].get(identity):",
                  "            if revision['sha256'] == state['revisions'].get(identity, {}).get('sha256'):")
    start = source.index('                if publish is None:')
    end = source.index('                if snapshot().get(identity) != revision:', start)
    active = source[start:end]
    replacement = '''                if revision['delivery_status'] == 'hidden':
                    from ua_stage_catalog_sync import reconcile
                    reconcile(apply=True)
                else:
''' + ''.join('    ' + line for line in active.splitlines(keepends=True))
    source = source[:start] + replacement + source[end:]
    return once(source, "                return 'published'",
                "                return 'hidden' if revision['delivery_status'] == 'hidden' else 'published'")


def build_candidate(sources, policy_source):
    if set(sources) != set(SOURCE_SHA256):
        raise ValueError("SOURCE_SET")
    for name, content in sources.items():
        if hashlib.sha256(content).hexdigest() != SOURCE_SHA256[name]:
            raise ValueError("SOURCE_CHANGED:" + name)
    output = {name: content.decode("utf-8") for name, content in sources.items()}
    schema = output["cars_schema.py"]
    for name, replacement in {
        "STAGES": 'STAGES = [(1, "В Корее"), (2, "На пароме"), (3, "В Грузии"), (4, "В Киеве")]',
        "STATUSES": 'STATUSES = {"kr_bought": (1, "В Корее"), "sea_loaded": (2, "На пароме"), "ge_waiting": (3, "В Грузии"), "ua_arrived": (4, "В Киеве")}',
    }.items():
        nodes = [n for n in ast.parse(schema).body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
        if len(nodes) != 1:
            raise ValueError("SCHEMA_ASSIGNMENT:" + name)
        schema = once(schema, ast.get_source_segment(schema, nodes[0]), replacement)
    schema = replace_function(schema, "stage_of", lambda _: '''def stage_of(status):
    from ua_delivery_status import stage_number
    return stage_number(status)''')
    schema = replace_function(schema, "status_label", lambda _: '''def status_label(status):
    from ua_delivery_status import public_label
    return public_label(status) or "Скрыт из каталога"''')
    output["cars_schema.py"] = schema
    ui = replace_function(output["cars_ui.py"], "stage_menu", patch_menu)
    ui = replace_function(ui, "stage_set", patch_stage_set)
    ui = replace_function(ui, "_ua117_block_removed_stage", lambda _: '''async def _ua117_block_removed_stage(update, context):
    await stage_set(update, context)''')
    output["cars_ui.py"] = patch_stage_router(ui)
    output["konteyner.py"] = replace_function(output["konteyner.py"], "gde_mashina", patch_fallback_menu)
    output["db.py"] = replace_function(output["db.py"], "update_card_field", lambda s: inject_function(s,
        '    from ua_delivery_status import storage_status\n    if table == "cars" and field == "status":\n        value = storage_status(value)\n'))
    output["stranica.py"] = replace_function(output["stranica.py"], "sobrat_katalog", lambda s: inject_function(s,
        '    from ua_delivery_status import stage_number\n    spisok = [row for row in spisok if stage_number(row.get("status"))]\n'), final=True)
    output["master_card.py"] = replace_function(output["master_card.py"], "obrabotat_obshuyu", patch_master_catalog, final=True)
    publisher = replace_function(output["publish_transaction_guard.py"], "_rows", patch_publisher_rows)
    publisher = replace_function(publisher, "_row_map", lambda s: once(once(s,
        'def _row_map()', 'def _row_map(*, include_hidden=False)'),
        '    rows, digest = _rows()', '    rows, digest = _rows(include_hidden=include_hidden)'))
    publisher = replace_function(publisher, "_stage", lambda _: '''def _stage(row):
    from ua_delivery_status import stage_number
    return stage_number(row.get("status"))''')
    output["publish_transaction_guard.py"] = publisher
    output["ua_stage_catalog_sync.py"] = patch_sync(output["ua_stage_catalog_sync.py"])
    output["catalog_design_guard.py"] = patch_catalog_design(output["catalog_design_guard.py"])
    output["ua_crm_public_sync.py"] = patch_public_sync(output["ua_crm_public_sync.py"])
    output["ua_delivery_status.py"] = policy_source
    for name, source in output.items():
        compile(source, name, "exec")
    return {name: source.encode("utf-8") for name, source in output.items()}
