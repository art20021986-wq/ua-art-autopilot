"""Pure, bounded patches for a reviewed UA099/UA110/UA111 runtime snapshot.

Inputs and outputs are source strings. This module never imports, installs or
executes runtime modules. Matching anchors prove structural compatibility only;
current process bindings and every publication/rollback route remain Gate B work.
Unknown signatures, missing legacy anchors and altered patch blocks fail closed.
"""
from __future__ import annotations

import ast
import re


class IntegrationError(RuntimeError):
    pass


def _compiled(source: str, name: str) -> ast.Module:
    if not isinstance(source, str) or len(source.encode("utf-8")) > 4 * 1024 * 1024:
        raise IntegrationError("SOURCE_TYPE_OR_SIZE:" + name)
    try:
        tree = ast.parse(source, filename=name)
        compile(tree, name, "exec")
    except (SyntaxError, ValueError, TypeError) as exc:
        raise IntegrationError("SOURCE_NOT_COMPILABLE:" + name) from exc
    return tree


def _markers(source: str, start: str, end: str) -> tuple[int, int] | None:
    starts = list(re.finditer(r"^" + re.escape(start) + r"$", source, re.M))
    ends = list(re.finditer(r"^" + re.escape(end) + r"$", source, re.M))
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or starts[0].start() >= ends[0].start():
        raise IntegrationError("AMBIGUOUS_PATCH_MARKERS:" + start)
    return starts[0].start(), ends[0].end()


def _base(source: str, block: str, name: str) -> str:
    _compiled(source, name)
    lines = block.splitlines()
    span = _markers(source, lines[0], lines[-1])
    if span:
        if source[span[0]:span[1]] != block or source[span[1]:].strip():
            raise IntegrationError("PATCH_BLOCK_CHANGED_OR_NOT_FINAL:" + name)
        source = source[:span[0]].rstrip() + "\n"
    elif any("UA SPEC AUTO10 RESTORE" in line for line in source.splitlines()):
        raise IntegrationError("UNKNOWN_RESTORE_PATCH_VERSION:" + name)
    return source


def _require_legacy_block(source: str, start: str, end: str) -> None:
    if _markers(source, start, end) is None:
        raise IntegrationError("LEGACY_CONTRACT_MISSING:" + start)


def _function(tree: ast.Module, name: str, positional: tuple[str, ...]) -> ast.FunctionDef:
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if not nodes or not isinstance(nodes[-1], ast.FunctionDef):
        raise IntegrationError("FUNCTION_MISSING_OR_ASYNC:" + name)
    node = nodes[-1]
    args = node.args
    actual = tuple(a.arg for a in args.posonlyargs + args.args)
    if actual != positional or args.vararg or args.kwarg or args.kwonlyargs or node.decorator_list:
        raise IntegrationError("FUNCTION_SIGNATURE_UNRECOGNIZED:" + name)
    return node


def _append(source: str, block: str, name: str) -> str:
    output = source.rstrip() + "\n\n" + block + "\n"
    _compiled(output, name)
    return output


SPEC_BLOCK = r'''
# >>> UA SPEC AUTO10 RESTORE SPEC V1
# Preserve manual CRM helpers, the existing sidecar connection and VIN data.
# Public reads always use the same canonical UA_ART_SPEC_DB as the worker.
import spec_publication as _ua_auto10_publication


def render_public_block(value):
    code = canonical_uid(value)
    if not code:
        raise _ua_auto10_publication.SpecError("INVALID_CARD_ID")
    return _ua_auto10_publication.render_block(
        code, _ua_auto10_publication.load_facts(code)
    )


def inject_public_spec(source, value):
    code = canonical_uid(value)
    if not code:
        raise _ua_auto10_publication.SpecError("INVALID_CARD_ID")
    # The canonical injector changes the spec block and reviewed duplicate VIN
    # spans, and validates that all remaining content and shell assets survive.
    facts = _ua_auto10_publication.load_facts(code)
    return _ua_auto10_publication.inject(source, code, facts)


def crm_summary(value):
    base = _UA110_BASE_CRM_SUMMARY(value)
    try:
        import vin_spec_service as _ua_auto10_service
        state = _ua_auto10_service.card_state(value)
        collection = {
            "NOT_QUEUED": "VIN ещё не поставлен в очередь",
            "PENDING": "сбор в очереди", "RUNNING": "идёт сбор характеристик",
            "READY": "характеристики собраны", "NEEDS_REVIEW": "нужна проверка данных",
            "FAILED": "сбор не выполнен",
        }
        publication = {
            "NOT_REQUIRED": "обновление сайта не требуется",
            "PENDING": "обновление сайта в очереди", "RUNNING": "идёт обновление сайта",
            "PASS": "страница проверена и обновлена", "UNCHANGED": "страница проверена, данные актуальны",
            "FAIL": "обновление сайта не прошло", "FAILED": "обновление сайта не прошло",
            "SUPERSEDED": "ожидается обработка более новых данных",
            "NEEDS_REVIEW": "публикация заблокирована до проверки данных автомобиля",
        }
        collected = collection.get(str(state.get("status")), "состояние сбора неизвестно")
        published = publication.get(str(state.get("site_sync_status")), "состояние сайта неизвестно")
        return base + "\nАвтосбор: " + collected + " · Сайт: " + published
    except Exception:
        return base + "\nАвтосбор и обновление сайта: состояние временно недоступно"
# <<< UA SPEC AUTO10 RESTORE SPEC V1
'''.strip()


PUBLISH_BLOCK = r'''
# >>> UA SPEC AUTO10 RESTORE PUBLISHER V1
import pathlib as _ua_auto10_pathlib
import os as _ua_auto10_os
import re as _ua_auto10_re
import spec_publication as _ua_auto10_publication

_UA_AUTO10_BASE_MASTER = _master
_UA_AUTO10_BASE_PRIMARY_WRITE = _zapisat_atomarno


def _master(kod):
    output = _UA_AUTO10_BASE_MASTER(kod)
    if not isinstance(output, (tuple, list)) or len(output) != 3:
        raise _ua_auto10_publication.SpecError("PUBLISH_MASTER_RESULT_UNRECOGNIZED")
    source, diag, card = output
    if not isinstance(source, str) or not source:
        raise _ua_auto10_publication.SpecError("PUBLISH_PRIMARY_HTML_MISSING")
    import ua_additional_spec as _ua_auto10_spec
    code = _ua_auto10_spec.canonical_uid(kod)
    facts = _ua_auto10_publication.load_facts(code)
    source = _ua_auto10_publication.inject(source, code, facts)
    _ua_auto10_publication.validate_page(source, code, facts)
    return source, diag, card


def _zapisat_atomarno(put, tekst):
    path = _ua_auto10_pathlib.Path(put)
    root = _ua_auto10_pathlib.Path(
        _ua_auto10_os.environ.get("UA_ART_ROOT", "/home/Carix")
    ).resolve()
    # Only primary files at the reviewed public roots are publication writes.
    # Diagnostic/catalog rendering and immutable backup files retain behavior.
    if (_ua_auto10_re.fullmatch(r"UA-[0-9]{4,6}\.html", path.name)
            and path.absolute().parent in (root / "video", root / "site")):
        if path.is_symlink() or path.parent.is_symlink():
            raise _ua_auto10_publication.SpecError("PUBLIC_WRITE_SYMLINK")
        if not isinstance(tekst, (str, bytes)):
            raise _ua_auto10_publication.SpecError("PUBLIC_WRITE_DATA_TYPE")
        data = tekst.encode("utf-8") if isinstance(tekst, str) else tekst
        _ua_auto10_publication.guard_write(path, data)
    return _UA_AUTO10_BASE_PRIMARY_WRITE(put, tekst)
# <<< UA SPEC AUTO10 RESTORE PUBLISHER V1
'''.strip()


GUARD_BLOCK = r'''
# >>> UA SPEC AUTO10 RESTORE TRANSACTION V1
import spec_publication as _ua_auto10_publication

_UA_AUTO10_BASE_ATOMIC = _atomic
_UA_AUTO10_BASE_VALIDATE_PRIMARY = _validate_primary
_UA_AUTO10_BASE_PUBLISH_LOCKED = _publish_locked


def _atomic(path, data, mode=None):
    path = pathlib.Path(path)
    if (re.fullmatch(r"UA-[0-9]{4,6}\.html", path.name)
            and path.absolute().parent in tuple(pathlib.Path(root).absolute() for root in ROOTS)):
        if path.is_symlink() or path.parent.is_symlink():
            raise _ua_auto10_publication.SpecError("PUBLIC_WRITE_SYMLINK")
        _ua_auto10_publication.guard_write(path, data)
    return _UA_AUTO10_BASE_ATOMIC(path, data, mode)


def _validate_primary(code, row, source):
    _ua_auto10_publication.validate_page(
        source, code, _ua_auto10_publication.load_facts(code)
    )
    return _UA_AUTO10_BASE_VALIDATE_PRIMARY(code, row, source)


def _publish_locked(base_publish, codes, proba=False):
    codes = list(codes)
    # Snapshot.restore uses the guarded writer too. Before the ordinary
    # transaction takes a snapshot, require healthy canonical preimages.
    # Existing damaged pages must first use the spec-only reconciler.
    for value in codes:
        code = _code(value)
        facts = _ua_auto10_publication.load_facts(code)
        for root in ROOTS:
            path = pathlib.Path(root) / (code + ".html")
            if path.is_symlink() or path.parent.is_symlink():
                raise _ua_auto10_publication.SpecError("PUBLIC_WRITE_SYMLINK")
            if path.is_file():
                _ua_auto10_publication.validate_page(
                    _read(path).decode("utf-8"), code, facts
                )
    return _UA_AUTO10_BASE_PUBLISH_LOCKED(base_publish, codes, proba=proba)
# <<< UA SPEC AUTO10 RESTORE TRANSACTION V1
'''.strip()


CRM_BLOCK = r'''
# >>> UA SPEC AUTO10 RESTORE CRM V1
import re as _ua_auto10_re

_UA_AUTO10_BASE_CARD_KB = card_kb


def card_kb(card, staff):
    markup = _UA_AUTO10_BASE_CARD_KB(card, staff)
    rows = []
    for row in markup.inline_keyboard:
        kept = [button for button in row if not _ua_auto10_re.fullmatch(
            r"car_spec:\d+", str(getattr(button, "callback_data", "") or "")
        )]
        if kept:
            rows.append(kept)
    # Preserve all remaining button objects, callbacks, row order and metadata.
    return type(markup)(rows, api_kwargs=getattr(markup, "api_kwargs", None))
# <<< UA SPEC AUTO10 RESTORE CRM V1
'''.strip()


def patch_additional_spec(source: str) -> str:
    source = _base(source, SPEC_BLOCK, "ua_additional_spec.py")
    _require_legacy_block(source, "# >>> UA110 SIDECAR SPEC STORAGE V1", "# <<< UA110 SIDECAR SPEC STORAGE V1")
    tree = _compiled(source, "ua_additional_spec.py")
    for name, args in {
        "canonical_uid": ("value",), "fetch_specs": ("value", "include_hidden"),
        "connect": ("readonly",), "render_public_block": ("value",), "crm_summary": ("value",),
        "inject_public_spec": ("source", "value"), "get_spec": ("spec_id", "car_uid"),
        "set_manual_value": ("spec_id", "car_uid", "value", "actor_id"),
        "set_visible": ("spec_id", "car_uid", "visible", "actor_id"),
        "_car_vin": ("uid",), "public_contract_errors": ("source", "value"),
    }.items():
        _function(tree, name, args)
    if not any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_UA110_BASE_CRM_SUMMARY" for t in n.targets) for n in tree.body):
        raise IntegrationError("LEGACY_SUMMARY_BASE_MISSING")
    path_assignments = [n for n in tree.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "_UA110_SPEC_DB_PATH" for t in n.targets)]
    expected = ast.parse('pathlib.Path(os.environ.get("UA_ART_SPEC_DB", "/home/Carix/vin_specs_task111_v3.db"))', mode="eval").body
    if len(path_assignments) != 1 or ast.dump(path_assignments[0].value) != ast.dump(expected):
        raise IntegrationError("CANONICAL_SIDECAR_PATH_UNRECOGNIZED")
    return _append(source, SPEC_BLOCK, "ua_additional_spec.py")


def patch_publisher(source: str) -> str:
    source = _base(source, PUBLISH_BLOCK, "publikaciya.py")
    _require_legacy_block(source, "# >>> UA111 FINAL PUBLIC SPEC NORMALIZER V1", "# <<< UA111 FINAL PUBLIC SPEC NORMALIZER V1")
    _require_legacy_block(source, "# >>> UA099 PUBLICATION CONTRACT V1", "# <<< UA099 PUBLICATION CONTRACT V1")
    tree = _compiled(source, "publikaciya.py")
    for name, args in {"_master": ("kod",), "opublikovat": ("kod", "proba"),
                       "_zapisat_atomarno": ("put", "tekst")}.items():
        _function(tree, name, args)
    return _append(source, PUBLISH_BLOCK, "publikaciya.py")


def patch_publish_transaction_guard(source: str) -> str:
    source = _base(source, GUARD_BLOCK, "publish_transaction_guard.py")
    tree = _compiled(source, "publish_transaction_guard.py")
    for name, args in {"_atomic": ("path", "data", "mode"),
                       "_validate_primary": ("code", "row", "source"),
                       "_publish_locked": ("base_publish", "codes", "proba"),
                       "_code": ("value",), "_read": ("path",)}.items():
        _function(tree, name, args)
    if not any(isinstance(n, ast.ClassDef) and n.name == "Snapshot" for n in tree.body):
        raise IntegrationError("SNAPSHOT_CONTRACT_MISSING")
    if not any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ROOTS" for t in n.targets) for n in tree.body):
        raise IntegrationError("PUBLIC_ROOTS_MISSING")
    return _append(source, GUARD_BLOCK, "publish_transaction_guard.py")


def patch_cars_ui(source: str) -> str:
    source = _base(source, CRM_BLOCK, "cars_ui.py")
    _require_legacy_block(source, "# >>> UA099 ADDITIONAL SPEC CRM V1", "# <<< UA099 ADDITIONAL SPEC CRM V1")
    _require_legacy_block(source, "# >>> UA110 VIN SPEC AUTO QUEUE V1", "# <<< UA110 VIN SPEC AUTO QUEUE V1")
    tree = _compiled(source, "cars_ui.py")
    _function(tree, "card_kb", ("card", "staff"))
    register = _function(tree, "register", ("app",))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "start_worker"
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "_ua110_vin_service"]
    if len(calls) != 1 or calls[0].args or calls[0].keywords:
        raise IntegrationError("EXISTING_WORKER_HOOK_MISSING_DUPLICATE_OR_MOVED")
    if calls[0] not in list(ast.walk(register)):
        # The verified TASK117/TASK121 runtime wraps UA110's register once.
        # Accept only that exact wrapper and its immutable captured predecessor;
        # do not infer arbitrary call graphs or add another worker start.
        expected = ast.parse(r'''
def register(app):
    _UA117_BASE_REGISTER(app)
    app.add_handler(CallbackQueryHandler(
        _ua117_block_removed_stage,
        pattern=r"^car_setstage:\d+:(?:sea_loaded|sea_transit|ua_handed)$"),
        group=-100)
''').body[0]
        aliases = [n for n in tree.body if isinstance(n, ast.Assign)
                   and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                   and n.targets[0].id == "_UA117_BASE_REGISTER"]
        writes = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
                  and n.id == "_UA117_BASE_REGISTER" and isinstance(n.ctx, (ast.Store, ast.Del))]
        if len(aliases) != 1 or len(writes) != 1 or ast.dump(register) != ast.dump(expected):
            raise IntegrationError("EXISTING_WORKER_HOOK_UNRECOGNIZED_WRAPPER")
        alias = aliases[0]
        earlier = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name == "register" and n.lineno < alias.lineno]
        if (not isinstance(alias.value, ast.Name) or alias.value.id != "register"
                or not earlier or alias.lineno >= register.lineno
                or calls[0] not in list(ast.walk(earlier[-1]))
                or not any(isinstance(n, ast.Expr) and n.value is calls[0]
                           for n in earlier[-1].body)):
            raise IntegrationError("EXISTING_WORKER_HOOK_BROKEN_WRAPPER_CHAIN")
    return _append(source, CRM_BLOCK, "cars_ui.py")


# Compatibility alias for earlier patcher naming; both functions remain pure.
patch_publikaciya = patch_publisher

__all__ = ["IntegrationError", "patch_additional_spec", "patch_publisher",
           "patch_publikaciya", "patch_publish_transaction_guard", "patch_cars_ui"]
