"""Source-pinned repair for stage edits; writes candidates only to a new directory."""

import argparse
import ast
import hashlib
import json
from pathlib import Path


SOURCE_SHA256 = {
    "cars_ui.py": "c17a45d64f17fbab2e2f032061f6037a48bb5fa038b3f02e20995b5e50fbca7b",
    "publikaciya.py": "296c389b477472032bad714e41f12bfa4b7e47ad784ac6900ba55f136d939c72",
}
POLICY_SHA256 = "c544bc121b7b3b66d45519d5b63ed3687567af7e9d5f7011ae2fb53cc372bdd0"
DEPENDENCY_SHA256 = {
    "ua_delivery_status.py": POLICY_SHA256,
    "ua_crm_public_sync.py": "2b5f6a2473b263fddd6ab3266a3ba76cc9738da15178f865862098821cabcc41",
    "ua_stage_catalog_sync.py": "a8d2784e73d005b5a02328f63c9233d78da665547266276df69291383616a255",
    "publish_transaction_guard.py": "9b41f15e8455ec7e579bea1e194e6c855cc50b7b0e060ee2a010301d28c981e8",
}


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("SOURCE_ANCHOR_COUNT")
    return source.replace(old, new, 1)


def replace_function(source, name, transform):
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name == name]
    if len(nodes) != 1:
        raise ValueError("FUNCTION_COUNT:" + name)
    node = nodes[0]
    old = ast.get_source_segment(source, node)
    lines = source.splitlines(keepends=True)
    offset = sum(map(len, lines[:node.lineno - 1]))
    return source[:offset] + transform(old) + source[offset + len(old):]


def patch_catalog_builder(source):
    return once(source,
                "    spisok = _ua9_s.mashiny()",
                "    from ua_delivery_status import stage_number\n"
                "    spisok = [row for row in _ua9_s.mashiny()\n"
                "              if row.get('published') == 1 and stage_number(row.get('status'))]")


def patch_stage_handler(source):
    # Older Telegram messages carry the four established storage codes.
    # Keep public input validation strict; adapt those codes only in this CRM route.
    source = once(source, "from ua_delivery_status import crm_status_from_input",
                  "from ua_delivery_status import storage_status")
    return once(source, "code = crm_status_from_input(requested)",
                "code = storage_status(requested)")


SYNC_HANDLER = '''async def _ua004_sync_current_stage(card):
    if card.get('published') != 1:
        return 'Карточка не опубликована. Этап сохранён; он будет использован при публикации.'
    try:
        from ua_crm_public_sync import start, notify
        start()
        notify()
        return 'Этап сохранён в CRM. Обновление сайта поставлено в очередь с проверкой результата.'
    except Exception:
        log.exception('UA004: cannot start the persistent publication worker')
        return 'Этап сохранён в CRM. Обновление сайта пока не запущено: ошибка очереди.'
'''


SYNC_JOB = '''async def _ua004_stage_reconcile_job(context):
    # One existing durable worker owns full publication and its retry ledger.
    # A stage-only patch cannot add a reactivated or newly published car.
    try:
        from ua_crm_public_sync import start, notify
        start()
        notify()
    except Exception:
        log.exception('UA004: publication worker unavailable; next scheduled check will retry')
'''


def patch_ui(source):
    source = replace_function(source, "stage_set", patch_stage_handler)
    source = once(source,
                  'pattern=r"^car_setstage:\\d+:(?:sea_loaded|sea_transit|ua_handed)$"',
                  'pattern=r"^car_setstage:"')
    source = replace_function(source, "_ua004_sync_current_stage", lambda _: SYNC_HANDLER.rstrip())
    return replace_function(source, "_ua004_stage_reconcile_job", lambda _: SYNC_JOB.rstrip())


def build(sources, dependencies):
    if set(sources) != set(SOURCE_SHA256):
        raise ValueError("SOURCE_SET")
    if set(dependencies) != set(DEPENDENCY_SHA256):
        raise ValueError("DEPENDENCY_SET")
    for name, digest in DEPENDENCY_SHA256.items():
        if hashlib.sha256(dependencies[name]).hexdigest() != digest:
            raise ValueError("DEPENDENCY_CHANGED:" + name)
    result = {}
    for name, content in sources.items():
        if hashlib.sha256(content).hexdigest() != SOURCE_SHA256[name]:
            raise ValueError("SOURCE_CHANGED:" + name)
        source = content.decode("utf-8")
        if name == "cars_ui.py":
            candidate = patch_ui(source)
        else:
            candidate = replace_function(source, "_ua9_sobrat_katalog", patch_catalog_builder)
        compile(candidate, name, "exec")
        result[name] = candidate.encode("utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, target = args.source.resolve(), args.output.resolve()
    if target == source or target.exists():
        raise ValueError("OUTPUT_MUST_BE_NEW")
    candidate = build({name: (source/name).read_bytes() for name in SOURCE_SHA256},
                      {name: (source/name).read_bytes() for name in DEPENDENCY_SHA256})
    target.mkdir(parents=True, exist_ok=False)
    for name, content in candidate.items():
        (target/name).write_bytes(content)
    print(json.dumps({"candidate_only": True, "production_installed": False,
                      "sha256": {name: hashlib.sha256(data).hexdigest()
                                 for name, data in candidate.items()}}, sort_keys=True))


if __name__ == "__main__":
    main()
