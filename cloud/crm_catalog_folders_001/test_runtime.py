"""Execute the integration fragment against in-memory Telegram/CRM stubs only."""
import copy
from dataclasses import dataclass
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import catalog_core


class StopHandler(Exception):
    pass


@dataclass
class Button:
    text: str
    callback_data: str = None
    url: str = None


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = tuple(tuple(row) for row in rows)


class Handler:
    def __init__(self, callback, pattern):
        self.callback = callback
        self.pattern = re.compile(pattern)


def full_catalog(numbers=()):
    items = ''.join('<article data-ua-card="%s"></article>' % n for n in numbers)
    return ('<!doctype html><html><head><title>'
            'Каталог автомобилей — UA ART COMPANY'
            '</title></head><body>%s</body></html>' % items)


def cars(count):
    return [{"id": n, "auto_number": "UA-%04d" % n, "published": 1,
             "status": "kr_bought", "brand": "Kia", "model": "K5",
             "year": 2020, "vin": "VIN1234", "photos": ["keep.jpg"],
             "additional_spec": {"fuel": "LPG"}}
            for n in range(count, 0, -1)]


class MemoryCatalog:
    def __init__(self, source):
        self.source = source
        self.reads = 0
        self.mutate_on_read = False
        self.version = 1

    def stat(self):
        return SimpleNamespace(st_ino=1, st_size=len(self.source), st_mtime_ns=self.version)

    def read_text(self, encoding):
        assert encoding == "utf-8"
        self.reads += 1
        if self.mutate_on_read:
            self.version += 1
        return self.source


class MemoryDB:
    def __init__(self, records):
        self.records = records
        self.list_calls = []
        self.staff = {"id": 10, "role": "admin"}

    def get_staff(self, actor_id):
        return self.staff

    def list_cards(self, table, limit):
        self.list_calls.append((table, limit))
        return list(self.records) if limit == -1 else list(self.records[:limit])


class Message:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append({"text": text, **kwargs})


class RuntimeHarness:
    def __init__(self, records, source):
        self.db = MemoryDB(records)
        self.catalog = MemoryCatalog(source)
        self.acks = []
        self.errors = []
        self.base_keyboard_calls = []
        self.existing_open = object()
        self.existing_other = object()
        self.base_back = Button("← Автомобили", "cards_cars")
        self.base_edit = Button("Изменить", "car_edit:1")
        self.base_link = Button("Дополнительная спецификация", url="https://example.invalid/spec")
        self.base_markup = Markup([[self.base_edit], [self.base_link], [self.base_back]])

        async def ack(query):
            self.acks.append(query)

        def old_list(update, context):
            raise AssertionError("Original flat list must not be called")

        def base_card_kb(card, staff):
            self.base_keyboard_calls.append((card, staff))
            return self.base_markup

        # This models the observed existing register contract: it resolves the
        # module-global cars_list when registration occurs after fragment load.
        def base_register(app):
            app.add_handler(Handler(self.ns["cars_list"], r"^(?:cards_cars|cars_cards)$"), group=0)
            app.add_handler(Handler(self.existing_open, r"^car_open:[0-9]+$"), group=0)
            app.add_handler(Handler(self.existing_other, r"^car_edit:[0-9]+$"), group=1)

        self.ns = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "ApplicationHandlerStop": StopHandler,
            "InlineKeyboardButton": Button,
            "InlineKeyboardMarkup": Markup,
            "CallbackQueryHandler": Handler,
            "db": self.db,
            "_v168_ack": ack,
            "drop_wait": lambda context: context.user_data.pop("waiting", None),
            "card_of": lambda cid: next((c for c in self.db.records if c["id"] == cid), None),
            "S": SimpleNamespace(missing_required=lambda card: [], status_label=lambda value: value),
            "_ua082_title_html": lambda card: "<b>%s · VIN 1234</b>" % card["auto_number"],
            "_ua082_title_button": lambda card: "%s · Kia K5 2020 · VIN 1234" % card["auto_number"],
            "log": SimpleNamespace(exception=self.errors.append),
            "cars_list": old_list,
            "card_kb": base_card_kb,
            "register": base_register,
        }
        fragment = Path(__file__).with_name("runtime_fragment.py").read_text(encoding="utf-8")
        with patch.dict("sys.modules", {"ua_crm_catalog_folders": catalog_core}):
            exec(compile(fragment, "runtime_fragment.py", "exec"), self.ns)
        self.ns["_UA122_CATALOG"] = self.catalog

    async def invoke(self, data, context=None):
        message = Message()
        query = SimpleNamespace(data=data, from_user=SimpleNamespace(id=10), message=message)
        update = SimpleNamespace(callback_query=query)
        context = context or SimpleNamespace(user_data={})
        try:
            await self.ns["cars_list"](update, context)
        except StopHandler:
            pass
        else:
            raise AssertionError("Callback did not stop later Telegram handlers")
        return message, context


def buttons(reply):
    return [button for row in reply["reply_markup"].inline_keyboard for button in row]


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def harness(self, count=19, published_count=18):
        source = cars(count)
        if count == 19:
            source[0]["id"] = 29
            source[0]["published"] = 0
        return RuntimeHarness(source, full_catalog("UA-%04d" % n for n in range(1, published_count + 1)))

    async def test_both_legacy_buttons_open_two_folders_eighteen_plus_one(self):
        harness = self.harness()
        for callback in ("cards_cars", "cars_cards"):
            message, _ = await harness.invoke(callback)
            self.assertEqual(len(message.replies), 1)
            reply = message.replies[0]
            self.assertEqual([(b.text, b.callback_data) for b in buttons(reply)], [
                ("В каталоге · 18", "ua122_cars:catalog:0"),
                ("Не опубликованные · 1", "ua122_cars:unpublished:0"),
                ("← Назад", "menu"),
            ])
        self.assertEqual(harness.db.list_calls, [("cars", -1), ("cars", -1)])
        self.assertEqual(len(harness.acks), 2)

    async def test_each_folder_contains_only_its_cards_with_existing_open_callback(self):
        harness = self.harness()
        expected = {"catalog": ["car_open:%d" % n for n in range(18, 0, -1)],
                    "unpublished": ["car_open:29"]}
        for folder in expected:
            message, _ = await harness.invoke("ua122_cars:%s:0" % folder)
            card_buttons = [b for b in buttons(message.replies[0])
                            if b.callback_data.startswith("car_open:")]
            self.assertEqual([b.callback_data for b in card_buttons], expected[folder])
            self.assertTrue(all("VIN 1234" in b.text for b in card_buttons))

    async def test_more_than_thirty_are_all_reachable_in_original_order(self):
        harness = self.harness(count=65, published_count=65)
        seen = []
        size = harness.ns["_UA122_PAGE_SIZE"]
        pages = (65 + size - 1) // size
        for page in range(pages):
            expected_count = min(size, 65 - page * size)
            message, _ = await harness.invoke("ua122_cars:catalog:%d" % page)
            reply = message.replies[0]
            cb = [b.callback_data for b in buttons(reply)]
            open_callbacks = [c for c in cb if c.startswith("car_open:")]
            self.assertEqual(len(open_callbacks), expected_count)
            seen.extend(open_callbacks)
            if page:
                self.assertIn("ua122_cars:catalog:%d" % (page - 1), cb)
            if page < pages - 1:
                self.assertIn("ua122_cars:catalog:%d" % (page + 1), cb)
            self.assertIn("Страница %d из %d" % (page + 1, pages), reply["text"])
        self.assertEqual(seen, ["car_open:%d" % n for n in range(65, 0, -1)])
        self.assertEqual(harness.db.list_calls, [("cars", -1)] * pages)

    async def test_unpublished_pages_keep_unpublished_namespace(self):
        harness = self.harness(count=35, published_count=0)
        message, _ = await harness.invoke("ua122_cars:unpublished:0")
        cb = [b.callback_data for b in buttons(message.replies[0])]
        self.assertIn("ua122_cars:unpublished:1", cb)
        self.assertNotIn("ua122_cars:catalog:1", cb)

    async def test_stale_last_page_is_clamped_after_catalog_shrinks(self):
        harness = self.harness(count=65, published_count=1)
        message, _ = await harness.invoke("ua122_cars:catalog:2")
        cb = [b.callback_data for b in buttons(message.replies[0])]
        self.assertEqual([c for c in cb if c.startswith("car_open:")], ["car_open:1"])
        self.assertNotIn("Страница 3", message.replies[0]["text"])

    async def test_return_button_tracks_completed_publication_and_unpublication(self):
        harness = self.harness()
        car = harness.db.records[0]
        staff = harness.db.staff

        def back():
            return harness.ns["card_kb"](car, staff).inline_keyboard[-1][0]

        self.assertEqual(back().callback_data, "ua122_cars:unpublished:0")
        car["published"] = 1  # An intent flag before publishing must not move it.
        self.assertEqual(back().callback_data, "ua122_cars:unpublished:0")
        harness.catalog.source = full_catalog("UA-%04d" % n for n in range(1, 20))
        self.assertEqual(back().callback_data, "ua122_cars:catalog:0")
        car["published"] = 0  # The catalog still contains it until committed removal.
        self.assertEqual(back().callback_data, "ua122_cars:catalog:0")
        harness.catalog.source = full_catalog("UA-%04d" % n for n in range(1, 19))
        self.assertEqual(back().callback_data, "ua122_cars:unpublished:0")

    async def test_keyboard_preserves_existing_actions_links_and_objects(self):
        harness = self.harness()
        car = harness.db.records[0]
        before = copy.deepcopy(car)
        result = harness.ns["card_kb"](car, harness.db.staff)
        self.assertIs(result.inline_keyboard[0][0], harness.base_edit)
        self.assertIs(result.inline_keyboard[1][0], harness.base_link)
        self.assertEqual(harness.base_markup.inline_keyboard[-1][0].callback_data, "cards_cars")
        self.assertEqual(car, before)
        self.assertIs(harness.base_keyboard_calls[0][0], car)
        self.assertIs(harness.base_keyboard_calls[0][1], harness.db.staff)

    async def test_catalog_failure_shows_retry_without_false_zero_counts(self):
        for data in ("cards_cars", "ua122_cars:catalog:0"):
            harness = self.harness()
            harness.catalog.source = full_catalog(["UA-0001"]).replace("</html>", "")
            message, _ = await harness.invoke(data)
            self.assertEqual(len(message.replies), 1)
            self.assertIn("Не удалось обновить список", message.replies[0]["text"])
            self.assertNotIn("· 0", message.replies[0]["text"])
            self.assertEqual([b.callback_data for b in buttons(message.replies[0])], ["cards_cars"])
            self.assertTrue(harness.errors)
            self.assertIs(harness.ns["card_kb"](harness.db.records[0], harness.db.staff),
                          harness.base_markup)

    async def test_concurrent_catalog_replace_returns_error_not_partial_groups(self):
        harness = self.harness()
        harness.catalog.mutate_on_read = True
        message, _ = await harness.invoke("cards_cars")
        self.assertIn("Не удалось обновить список", message.replies[0]["text"])
        self.assertEqual(len(buttons(message.replies[0])), 1)

    async def test_catalog_crm_mismatch_does_not_show_incomplete_counts(self):
        harness = self.harness()
        harness.catalog.source = full_catalog(["UA-9999"])
        message, _ = await harness.invoke("cards_cars")
        self.assertIn("Не удалось обновить список", message.replies[0]["text"])
        self.assertFalse(any("·" in b.text for b in buttons(message.replies[0])))

    async def test_unauthorized_callback_never_reads_cars_or_catalog(self):
        harness = self.harness()
        harness.db.staff = None
        message, _ = await harness.invoke("ua122_cars:catalog:0")
        self.assertEqual(message.replies[0]["text"], "Доступ только для сотрудников.")
        self.assertEqual(harness.db.list_calls, [])
        self.assertEqual(harness.catalog.reads, 0)

    async def test_render_preserves_crm_data_and_existing_context_cleanup(self):
        harness = self.harness()
        before = copy.deepcopy(harness.db.records)
        context = SimpleNamespace(user_data={"waiting": 1, "car_last": 29,
                                  "car_voice_active": True, "voice_undo": {}, "keep": "value"})
        await harness.invoke("ua122_cars:catalog:0", context)
        self.assertEqual(harness.db.records, before)
        self.assertEqual(context.user_data, {"keep": "value"})

    async def test_empty_folder_is_explicit_and_invalid_callback_is_safe(self):
        harness = self.harness(count=1, published_count=1)
        message, _ = await harness.invoke("ua122_cars:unpublished:0")
        self.assertIn("В этой папке пока нет автомобилей", message.replies[0]["text"])
        for value in ("ua122_cars:all:0", "ua122_cars:catalog:-1", "ua122_cars:catalog:١",
                      "ua122_cars:catalog:0:1", "ua122_cars:catalog:" + "9" * 10):
            message, _ = await harness.invoke(value)
            self.assertIn("Не удалось обновить список", message.replies[0]["text"])

    async def test_register_preserves_handlers_and_routes_both_existing_buttons(self):
        harness = self.harness()
        registrations = []
        app = SimpleNamespace(add_handler=lambda handler, group: registrations.append((handler, group)))
        harness.ns["register"](app)
        self.assertEqual(len(registrations), 4)
        base_list, base_open, base_edit, folders = [r[0] for r in registrations]
        self.assertEqual([r[1] for r in registrations], [0, 0, 1, -1])
        self.assertIs(base_open.callback, harness.existing_open)
        self.assertIs(base_edit.callback, harness.existing_other)
        self.assertIs(base_list.callback, harness.ns["cars_list"])
        self.assertIs(folders.callback, harness.ns["cars_list"])
        for callback in ("cards_cars", "cars_cards"):
            self.assertIsNotNone(base_list.pattern.match(callback))
            self.assertIsNone(folders.pattern.match(callback))
        for callback in ("ua122_cars:catalog:0", "ua122_cars:unpublished:999999999"):
            self.assertIsNotNone(folders.pattern.fullmatch(callback))
        for callback in ("car_open:29", "car_edit:29", "menu", "ua122_cars:all:0",
                         "ua122_cars:catalog:-1", "other_ua122_cars:catalog:0",
                         "ua122_cars:catalog:1234567890", "ua122_cars:catalog:١"):
            self.assertIsNone(folders.pattern.match(callback))


if __name__ == "__main__":
    unittest.main()
