#!/usr/bin/env python3
"""Pinned final17 CRM callbacks over real synthetic SQLite and publisher.

Only Telegram transport, media presentation and unused AI interfaces are fake.
All candidate callback, schema, storage, publication and lifecycle functions
remain actual code. No background worker, network, live chat or production IO.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import sysconfig
import traceback
import types
from datetime import datetime, timezone

COMBINED_HARNESS_SHA = "fa9c104aeeb3f00d7d25ed7cc54e3bad247caac7b069333f486e86a7f0638fd0"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_pinned(path, expected):
    if path.is_symlink() or path.resolve() != path.absolute():
        raise RuntimeError("NONCANONICAL_HELPER")
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise RuntimeError("HELPER_PIN_MISMATCH")
    module = types.ModuleType(path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


class Stop(Exception):
    pass


class Button:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text, self.callback_data = text, callback_data
        self.__dict__.update(kwargs)


class Markup:
    def __init__(self, inline_keyboard, api_kwargs=None):
        self.inline_keyboard, self.api_kwargs = inline_keyboard, api_kwargs


class Filter:
    def __and__(self, other):
        return self

    def __invert__(self):
        return self


class Handler:
    def __init__(self, callback, pattern=None):
        self.callback, self.pattern = callback, pattern


class MessageHandler(Handler):
    def __init__(self, filter_value, callback):
        super().__init__(callback)


class App:
    def __init__(self):
        self.handlers, self.job_queue = {}, None

    def add_handler(self, handler, group=0):
        self.handlers.setdefault(group, []).append(handler)

    async def dispatch(self, event, context):
        # Match documented Telegram group order and first matching handler.
        # This deliberately is not a test of the actual Telegram dispatcher.
        called = []
        for group in sorted(self.handlers):
            for handler in self.handlers[group]:
                if isinstance(handler, MessageHandler):
                    matched = event.callback_query is None and bool(event.effective_message.text)
                else:
                    matched = event.callback_query is not None and re.search(handler.pattern, event.callback_query.data)
                if matched:
                    called.append({"group": group, "callback": handler.callback.__name__})
                    try:
                        await handler.callback(event, context)
                    except Stop:
                        return called
                    break
        return called


class Message:
    def __init__(self, text=None):
        self.text, self.replies = text, []
        self.message_id, self.chat_id = 123, 1
        self.photo = []
        self.video = self.voice = self.audio = self.video_note = self.document = None

    async def reply_text(self, text, **kwargs):
        self.replies.append({"text": str(text), **kwargs})
        return self

    async def edit_text(self, text, **kwargs):
        return await self.reply_text(text, **kwargs)


def update(data=None, text=None):
    message, user = Message(text), types.SimpleNamespace(id=1)
    async def answer(*args, **kwargs):
        return None
    query = types.SimpleNamespace(data=data, message=message, from_user=user, answer=answer)
    return types.SimpleNamespace(callback_query=query if data else None, effective_message=message,
                                 effective_user=user, effective_chat=types.SimpleNamespace(id=1))


def fake_transports():
    telegram = types.ModuleType("telegram")
    telegram.InlineKeyboardButton, telegram.InlineKeyboardMarkup = Button, Markup
    telegram.Update = object
    extension = types.ModuleType("telegram.ext")
    extension.ApplicationHandlerStop, extension.CallbackQueryHandler = Stop, Handler
    extension.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
    extension.MessageHandler = MessageHandler
    extension.filters = types.SimpleNamespace(TEXT=Filter(), COMMAND=Filter(), ALL=Filter())
    render = types.ModuleType("card_render")
    async def no_media(*args, **kwargs):
        return None
    render.send_photos = render.send_videos = no_media
    render.owner_money = lambda card: []
    sys.modules.update({"telegram": telegram, "telegram.ext": extension, "card_render": render})
    # catch_message imports these before reaching its ordinary text-field path.
    # Any attribute use fails: these are not substitutes for AI recognition.
    for name in ("ai", "ai_fast_schema", "ai_filter", "local_ocr"):
        sys.modules[name] = types.ModuleType(name)


async def call(handler, context, *, data=None, text=None):
    event = update(data, text)
    try:
        await handler(event, context)
    except Stop:
        pass
    return event.effective_message


def page_contract(root, code):
    import card_shell
    import spec_publication as specification
    facts = specification.load_facts(code)
    result = []
    for folder in ("video", "site"):
        page = (root / folder / (code + ".html")).read_text()
        audit = specification.validate_page(page, code, facts)
        assets = card_shell.validate_shell_assets(page, page)
        if audit.get("status") != "PASS" or assets["ordered_static_assets_sha256"] != specification.PINNED_SHELL_ASSETS_SHA256:
            raise RuntimeError("CRM_CALLBACK_PUBLIC_CONTRACT_FAILED")
        result.append({"root": folder, "audit": audit, "shell_sha256": assets["ordered_static_assets_sha256"]})
    return result


async def scenario(root, old, *, expect_cancel_fixed):
    import db
    import cars_schema
    import publikaciya as publisher
    import vin_spec_service as service
    import ua_additional_spec as specification
    ids = old.seed_runtime(root)
    db.ensure_owner(1, "Synthetic operator", "synthetic")
    for cid in ids:
        with db.connect() as connection:
            connection.execute("UPDATE cars SET photos='[\"synthetic-local-image\"]',gearbox='automatic',condition_text='Synthetic inspection' WHERE id=?", (cid,))
    fake_transports()
    import cars_ui as ui
    ui.ensure_columns()
    app, worker_registration = App(), []
    start_worker = service.start_worker
    try:
        # Real register body and actual callback references; no worker thread.
        service.start_worker = lambda: worker_registration.append("start_worker requested")
        ui.register(app)
    finally:
        service.start_worker = start_worker
    if worker_registration != ["start_worker requested"]:
        raise RuntimeError("CRM_REGISTRATION_LOST_AUTOMATIC_WORKER")
    context = types.SimpleNamespace(user_data={}, chat_data={})
    report = {"callbacks": [], "fake_scope": ["Telegram transport and keyboard objects", "card_render media and owner-money presentation", "unused AI imports"],
              "not_run": ["Telegram API and real dispatcher", "background worker startup and timing", "AI/voice/media recognition", "new-card creation handlers outside cars_ui", "Public HTTP: test reader reads the actual generated local page"]}
    report["actual_registration"] = {"groups": {str(group): len(handlers) for group, handlers in app.handlers.items()},
                                      "worker_start_requested_once": True,
                                      "external_registrar_modules": "NOT_RUN"}
    import publish_transaction_guard as transaction
    ok, detail, proof = transaction.publish_batch(publisher._UA083_BASE_PUBLISH, ["UA-0001", "UA-0002"])
    if ok is not True:
        raise RuntimeError("SEED_PUBLICATION_FAILED:" + str(detail))
    opened = await call(ui.open_card, context, data="car_open:1")
    keyboard = opened.replies[0]["reply_markup"]
    if any(re.fullmatch(r"car_spec:\d+", str(button.callback_data or "")) for row in keyboard.inline_keyboard for button in row):
        raise RuntimeError("MANUAL_SPEC_BUTTON_STILL_PRESENT")
    if "ДОПОЛНИТЕЛЬНАЯ СПЕЦИФИКАЦИЯ" not in opened.replies[0]["text"]:
        raise RuntimeError("AUTOMATIC_SPEC_STATUS_MISSING")
    report["callbacks"].append("open_card: automatic status present, manual collection button absent")
    await call(ui.edit_ask, context, data="car_setf:1:condition_text")
    await call(ui.catch_message, context, text="Changed by actual CRM text handler")
    if db.get_card("cars", 1)["condition_text"] != "Changed by actual CRM text handler" or "car_wait" in context.user_data:
        raise RuntimeError("ACTUAL_CRM_TEXT_EDIT_FAILED")
    report["callbacks"].append("edit_ask -> catch_message -> actual db.update_card_field")
    # Publication and withdrawal use actual decorated publisher, SQLite and files.
    await call(ui.toggle_publish, context, data="car_pub:2")
    if db.get_card("cars", 2)["published"]:
        raise RuntimeError("ACTUAL_CALLBACK_HIDE_FAILED")
    for folder in ("video", "site"):
        if (root / folder / "UA-0002.html").exists() or (root / folder / "UA-0002-diag.html").exists():
            raise RuntimeError("HIDDEN_DIRECT_URL_REMAINS")
    report["callbacks"].append("toggle_publish: hide removes primary and diagnostic URLs in both roots")
    await call(ui.toggle_publish, context, data="car_pub:2")
    if not db.get_card("cars", 2)["published"]:
        raise RuntimeError("ACTUAL_CALLBACK_REPUBLISH_FAILED")
    report["republished_contract"] = page_contract(root, "UA-0002")
    report["callbacks"].append("toggle_publish: real publication preserves one VIN, specification and pinned shell")
    # A missing required field is rejected by the actual visible callback.
    await call(ui.toggle_publish, context, data="car_pub:2")
    db.update_card_field("cars", 2, "gearbox", "", 1)
    refused = await call(ui.toggle_publish, context, data="car_pub:2")
    if db.get_card("cars", 2)["published"] or not any("не хватает" in row["text"] for row in refused.replies):
        raise RuntimeError("MISSING_REQUIRED_CARD_WAS_PUBLISHED")
    db.update_card_field("cars", 2, "gearbox", "automatic", 1)
    await call(ui.toggle_publish, context, data="car_pub:2")
    report["callbacks"].append("toggle_publish: incomplete card refused without publication")
    first_spec = specification.fetch_specs("UA-0001", include_hidden=True)[0]
    spec_id, original_value = first_spec["id"], first_spec["field_value"]
    await call(ui.additional_spec_edit, context, data="car_spec_edit:1:%d" % spec_id)
    await call(ui.additional_spec_screen, context, data="car_spec:1")  # exact existing Cancel callback
    await call(ui.edit_ask, context, data="car_setf:1:year")
    incoming = update(text="2018")
    dispatch = await app.dispatch(incoming, context)
    intercepted = dispatch[-1]["callback"] == "additional_spec_edit_message"
    actual_value = specification.get_spec(spec_id, "UA-0001")["field_value"]
    actual_year = str(db.get_card("cars", 1)["year"])
    bug = intercepted and actual_value == "2018" and actual_year == "2017"
    report["cancel_manual_edit"] = {"reproduced_wrong_field_write": bug, "manual_spec_value_before": original_value,
                                     "manual_spec_value_after": actual_value, "crm_year_after": actual_year,
                                     "earlier_group_intercepted": intercepted, "actual_registered_callbacks": dispatch}
    if expect_cancel_fixed and (bug or actual_value != original_value or actual_year != "2018"):
        raise RuntimeError("CANCELLED_SPEC_EDIT_INTERCEPTED_CRM_EDIT")
    if not expect_cancel_fixed and not bug:
        raise RuntimeError("EXPECTED_FROZEN_UI_BUG_NOT_REPRODUCED")
    if expect_cancel_fixed:
        # Also exercise cancellation through a different card and direct new
        # field editor; these must never leave two message consumers active.
        for cancel in ("car_open:2", "car_setf:2:condition_text"):
            await app.dispatch(update(data="car_spec_edit:1:%d" % spec_id), context)
            await app.dispatch(update(data=cancel), context)
            if "ua099_spec_edit" in context.user_data:
                raise RuntimeError("SPEC_EDIT_SURVIVED_NAVIGATION:" + cancel)
        await app.dispatch(update(data="car_spec_edit:1:%d" % spec_id), context)
        if "car_wait" in context.user_data:
            raise RuntimeError("LEGACY_SPEC_EDITOR_LEFT_OTHER_TEXT_CONSUMER")
        changed = await app.dispatch(update(text="4860"), context)
        if changed != [{"group": -3, "callback": "additional_spec_edit_message"}] or specification.get_spec(spec_id, "UA-0001")["field_value"] != "4860":
            raise RuntimeError("LEGITIMATE_MANUAL_EDIT_BROKEN")
        # Restore VIN-consistent year via actual field handler before testing
        # the automatic synchronization path on the synthetic published car.
        await app.dispatch(update(data="car_setf:1:year"), context)
        await app.dispatch(update(text="2017"), context)
        scan = service.scan_new_vins()
        import spec_publication as publication
        sync = service.sync_one(reconciler=lambda card, facts: publication.reconcile_published(
            card, facts, public_reader=lambda code: (root / "video" / (code + ".html")).read_text()))
        if not sync or sync["car_uid"] != "UA-0001" or sync["status"] != "PASS":
            raise RuntimeError("CRM_MANUAL_FACT_AUTOMATIC_SYNC_FAILED:" + str(sync))
        report["automatic_spec_after_manual_edit"] = {"scan": scan, "sync": sync, "public_contract": page_contract(root, "UA-0001"),
                                                       "manual_publish_callback_called": False, "manual_refresh_callback_called": False}
        report["callbacks"].append("registered legacy manual edit: Cancel-to-list, card navigation and another field editor clear pending edit; valid edit syncs without publish/refresh buttons")
    # Keep the independent removal scenario on the other card, so the known
    # old UI failure cannot influence this actual callback result.
    facts_before = specification.fetch_specs("UA-0002", include_hidden=True)
    asked = await call(ui.delete_ask, context, data="car_del:2")
    if not any("Удалить карточку" in reply["text"] for reply in asked.replies):
        raise RuntimeError("DELETE_CONFIRMATION_MISSING")
    await call(ui.delete_ok, context, data="car_delok:2")
    if db.get_card("cars", 2) is not None or specification.fetch_specs("UA-0002", include_hidden=True) != facts_before:
        raise RuntimeError("ACTUAL_DELETE_CALLBACK_DAMAGED_RETAINED_FACTS")
    for folder in ("video", "site"):
        if (root / folder / "UA-0002.html").exists() or (root / folder / "UA-0002-diag.html").exists():
            raise RuntimeError("DELETED_DIRECT_URL_REMAINS")
    report["callbacks"].append("delete_ask -> delete_ok: actual removal, original specification facts retained")
    report["status"] = "PASS" if expect_cancel_fixed else "KNOWN_UI_BUG_REPRODUCED"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ui-patch", type=Path)
    parser.add_argument("--ui-patch-sha")
    args = parser.parse_args(argv)
    parent = Path(__file__).absolute().parent
    harness_sha = digest(Path(__file__).read_bytes())
    combined = load_pinned(parent / "complete17_cycle.py", COMBINED_HARNESS_SHA)
    output = args.output.absolute()
    root, old, harness, inputs = combined.prepare(args.candidate.absolute(), args.dependencies.absolute(), args.golden.absolute(), output)
    patch_record = None
    if args.ui_patch:
        patcher = load_pinned(args.ui_patch.absolute(), args.ui_patch_sha)
        target = root / "cars_ui.py"
        source = (args.candidate / "cars_ui.py").read_bytes()
        patched = patcher.patch_source(source)
        translated, relocations = harness.relocated(patched.decode(), root)
        target.write_text(translated)
        patch_record = {"patcher_sha256": args.ui_patch_sha, "before_sha256": digest(source), "after_sha256": digest(patched),
                        "staged_sha256": digest(translated.encode()), "relocations": relocations}
    # asyncio uses an in-process socketpair for its wakeup channel. Construct
    # that standard event loop before the runtime IO guard; no remote socket.
    loop = asyncio.new_event_loop()
    os.environ.clear()
    os.environ.update({"UA_ART_ROOT": str(root), "UA_ART_MAIN_DB": str(root / "crm.db"),
                       "UA_ART_SPEC_DB": str(root / "vin_specs_task111_v3.db"), "TMPDIR": str(root / "tmp")})
    os.chdir(root)
    libraries = list({Path(sysconfig.get_path(key)).resolve() for key in ("stdlib", "platstdlib", "purelib", "platlib")})
    sys.path[:] = [str(root)] + [entry for entry in sys.path if entry and any(Path(entry).resolve() == lib or lib in Path(entry).resolve().parents for lib in libraries)]
    guard, counts = harness.make_guard(output, libraries)
    sys.addaudithook(guard)
    report = {"scope": "ISOLATED_ACTUAL_CRM_CALLBACKS", "status": "FAIL", "inputs": inputs, "ui_patch": patch_record,
              "harness_sha256": harness_sha,
              "production_changed": False, "gate_b": "NOT_EVALUATED", "started_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        report["cycle"] = loop.run_until_complete(scenario(root, old, expect_cancel_fixed=bool(args.ui_patch)))
        for name, entry in inputs["modules"].items():
            expected = patch_record["staged_sha256"] if name == "cars_ui.py" and patch_record else entry["staged_sha256"]
            if digest((root / name).read_bytes()) != expected:
                raise RuntimeError("STAGED_EXECUTION_SOURCE_CHANGED:" + name)
        report["status"] = report["cycle"]["status"]
    except BaseException as exc:
        report["error"] = type(exc).__name__ + ":" + str(exc)
        report["trace"] = [{"file": Path(frame.f_code.co_filename).name, "line": line, "function": frame.f_code.co_name}
                           for frame, line in traceback.walk_tb(exc.__traceback__)]
    finally:
        loop.run_until_complete(loop.shutdown_default_executor())
        loop.close()
    report["io_guard"] = counts
    if any(counts.values()):
        report["status"] = "FAIL"
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "result": str(output / "result.json"), "error": report.get("error"), "io_guard": counts}))
    return 0 if report["status"] in {"PASS", "KNOWN_UI_BUG_REPRODUCED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
