"""Generate a private candidate from exact reviewed source pins; never install.

No candidate module is imported or run by this preparer. The generated hooks
require explicit verified RuntimeBindings and cannot select a production route.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PINS = {
    "db.py": "1d5073450b353b88f99944930ed34af0735784c3a580801bab694ecafb7f59a2",
    "cars_ui.py": "57ad5acc340d412aa9d95e1ef56c7de85d4346ad6bbc755fda311763f3637a42",
    "ua_additional_spec.py": "48a3f8e88bb214d6632513b6ee0b884a0d3bd95cb4bc2e786426fec42e4b2441",
    "spec_publication.py": "3e2ed470ebc06a9cbf03357858aeaf63cc6262045384867fca6b7b95bb181718",
}
MARKER = "UA_ART_SPEC_REBUILD10_CRM_V1"

DB_BLOCK = '''
# UA_ART_SPEC_REBUILD10_CRM_V1: post-commit events; bootstrap scan repairs gaps.
from spec_rebuild10 import crm_bridge as _ua_rb10_bridge
_ua_rb10_create_card = create_card
_ua_rb10_update_card_field = update_card_field
_ua_rb10_set_card_review = set_card_review

def create_card(table, data, created_by):
    card_id = _ua_rb10_create_card(table, data, created_by)
    if table == "cars":
        _ua_rb10_bridge.saved_after_commit(get_card(table, card_id))
    return card_id

def update_card_field(table, card_id, field, value, actor_id):
    result = _ua_rb10_update_card_field(table, card_id, field, value, actor_id)
    if table == "cars":
        _ua_rb10_bridge.saved_after_commit(get_card(table, card_id))
    return result

def set_card_review(table, card_id, status, actor_id, publish=None):
    result = _ua_rb10_set_card_review(table, card_id, status, actor_id, publish=publish)
    if table == "cars":
        _ua_rb10_bridge.saved_after_commit(get_card(table, card_id))
    return result
'''

UI_BLOCK = '''
# UA_ART_SPEC_REBUILD10_CRM_V1: owner actions use only the configured route.
from spec_rebuild10 import crm_bridge as _ua_rb10_bridge

def render(card, staff):
    return _UA099_BASE_RENDER(card, staff) + "\\n" + _ua_rb10_bridge.runtime_summary(card)

async def _ua_rb10_transition(update, context, action):
    q, staff = await _ua099_require_staff(update)
    drop_wait(context)
    cid = int(q.data.split(":")[-1])
    card = card_of(cid)
    if not card:
        await q.message.reply_text("Картку не знайдено.")
        raise ApplicationHandlerStop
    if action == "toggle":
        action = "hide" if card.get("published") else "publish"
    if action == "publish":
        missing = S.missing_required(card)
        if missing:
            await q.message.reply_text("Заповніть: " + ", ".join(missing))
            raise ApplicationHandlerStop
    import asyncio
    ok, detail = await asyncio.to_thread(
        _ua_rb10_bridge.runtime_transition, action, card, q.from_user.id)
    if ok and action == "delete":
        context.user_data.pop("car_last", None)
    await q.message.reply_text(detail, disable_web_page_preview=True)
    raise ApplicationHandlerStop

async def toggle_publish(update, context):
    return await _ua_rb10_transition(update, context, "toggle")

async def delete_ok(update, context):
    return await _ua_rb10_transition(update, context, "delete")

async def mark_sold_ok(update, context):
    return await _ua_rb10_transition(update, context, "sold")

async def _ua_rb10_old_spec_action(update, context):
    q, staff = await _ua099_require_staff(update)
    drop_wait(context)
    cid = int(q.data.split(":")[1])
    card = card_of(cid)
    await q.message.reply_text(_ua_rb10_bridge.runtime_summary(card or {}),
                              disable_web_page_preview=True)
    raise ApplicationHandlerStop

async def additional_spec_edit_message(update, context):
    # A stale pre-migration editor must not consume the next ordinary field.
    context.user_data.pop("ua099_spec_edit", None)

additional_spec_screen = _ua_rb10_old_spec_action
additional_spec_item = _ua_rb10_old_spec_action
additional_spec_visibility = _ua_rb10_old_spec_action
additional_spec_edit = _ua_rb10_old_spec_action
additional_spec_category = _ua_rb10_old_spec_action
additional_spec_set_category = _ua_rb10_old_spec_action
additional_spec_publish = _ua_rb10_old_spec_action
_ua110_refresh_spec = _ua_rb10_old_spec_action
'''

PUBLICATION_BLOCK = '''
# UA_ART_SPEC_REBUILD10_CRM_V1: all composers read the NEW canonical store.
from spec_rebuild10 import crm_bridge as _ua_rb10_bridge
from spec_rebuild10 import render as _ua_rb10_render

def load_facts(card_uid):
    try:
        return _ua_rb10_bridge.runtime_public_facts(card_uid)
    except Exception as exc:
        raise SpecError("REBUILD10_CANONICAL_FACTS_UNAVAILABLE:" + type(exc).__name__) from exc

def render_block(card_uid, facts):
    return _ua_rb10_render.render_block(card_uid, facts)

def inject(source, card_uid, facts):
    try:
        return _ua_rb10_render.compose_page(source, card_uid, facts)
    except _ua_rb10_render.SpecError as exc:
        raise SpecError(str(exc)) from exc

def validate_page(source, card_uid, facts, *, previous=None):
    try:
        return _ua_rb10_render.validate_page(source, card_uid, facts, previous=previous)
    except _ua_rb10_render.SpecError as exc:
        if previous is not None and str(exc) == "SHELL_UNAUTHORIZED_NON_SPEC_CHANGE":
            try:
                return _ua_rb10_bridge.validate_runtime_page_change(previous, source, card_uid, facts)
            except Exception as authorization_error:
                raise SpecError("REBUILD10_FULL_CARD_CHANGE_REJECTED") from authorization_error
        raise SpecError(str(exc)) from exc

def reconcile_published(*args, **kwargs):
    # Old workers cannot inject their historical source-policy payloads into
    # the new canonical renderer. The new worker uses its reviewed route.
    return {"status": "FAIL", "detail": "LEGACY_RECONCILER_DISABLED_REBUILD10"}
'''

ADDITIONAL_BLOCK = '''
# UA_ART_SPEC_REBUILD10_CRM_V1: remove old-marker checks, preserve exact new guard.
def public_contract_errors(source, value):
    code = canonical_uid(value)
    if not code:
        return ["INVALID_CARD_ID"]
    try:
        _ua_auto10_publication.validate_page(
            source, code, _ua_auto10_publication.load_facts(code))
        shell = _ua_auto10_publication.card_shell
        _, shown_vin = shell._main_vin(shell._Page(source), code)
        if shown_vin != str(_car_vin(code) or "").strip().upper():
            return ["primary VIN differs from operator CRM"]
    except Exception as exc:
        return ["REBUILD10_PUBLIC_CONTRACT:" + type(exc).__name__]
    return []
'''


def patch_sources(sources: dict[str, bytes]) -> dict[str, str]:
    result = {}
    blocks = {"db.py": DB_BLOCK, "cars_ui.py": UI_BLOCK,
              "spec_publication.py": PUBLICATION_BLOCK,
              "ua_additional_spec.py": ADDITIONAL_BLOCK}
    for name, expected in PINS.items():
        raw = sources.get(name, b"")
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("UNREVIEWED_RUNTIME_SOURCE:" + name)
        source = raw.decode("utf-8")
        if name == "cars_ui.py":
            anchor = "    _ua110_vin_service.start_worker()"
            if source.count(anchor) != 1:
                raise ValueError("LEGACY_WORKER_ANCHOR_MISMATCH")
            source = source.replace(anchor, "    _ua_rb10_bridge.start_configured_worker()")
        source = source.rstrip() + "\n\n" + blocks[name].strip() + "\n"
        compile(source, name, "exec")
        result[name] = source
    return result


def prepare(source_dir: Path, output_dir: Path) -> dict:
    if output_dir.exists() or source_dir.is_symlink() or output_dir.is_symlink():
        raise ValueError("NEW_PRIVATE_OUTPUT_DIRECTORY_REQUIRED")
    sources = {}
    for name in PINS:
        path = source_dir / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("REGULAR_REVIEWED_SOURCE_REQUIRED:" + name)
        sources[name] = path.read_bytes()
    result = patch_sources(sources)
    output_dir.mkdir(parents=True, mode=0o700)
    manifest = {"status": "PREPARED_NOT_INSTALLED", "automatic_first_publication": False,
                "runtime_bindings": "NOT_CONFIGURED", "source_pins": PINS, "files": {}}
    for name, source in result.items():
        path = output_dir / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o600)
        manifest["files"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output_dir / "crm-bridge-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_dir, args.output_dir), indent=2))
