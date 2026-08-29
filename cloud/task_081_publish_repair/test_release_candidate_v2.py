from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import pathlib
import shutil
import sys
import tempfile
import types
import unittest

HERE = pathlib.Path(__file__).resolve().parent
_live_candidates = (
    HERE / "evidence" / "live_audit_v2" / "sources",
    HERE.parent / "task081_live_audit_v2" / "sources",
)
LIVE = next((path for path in _live_candidates if path.is_dir()), _live_candidates[0])
sys.path.insert(0, str(HERE))

import patcher_v2 as patcher  # noqa: E402


def sources():
    return {
        name: (LIVE / name).read_text(encoding="utf-8")
        for name in patcher.FULL_FILE_SHA256
    }


class CandidateTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = sources()
        cls.candidate = patcher.build_candidates(cls.original)

    def test_exact_fresh_live_anchors_and_compile(self):
        for name, source in self.original.items():
            self.assertEqual(
                hashlib.sha256(source.encode()).hexdigest(),
                patcher.FULL_FILE_SHA256[name],
            )
        for name, source in self.candidate.items():
            compile(source, name, "exec")
            self.assertNotEqual(source, self.original[name])

    def test_only_stale_existence_guard_is_removed(self):
        for name in ("stranica.py", "master_card.py", "yadro.py"):
            normalizer = next(patcher._function_spans(self.candidate[name], "_ua_seo068_normalize"))
            self.assertNotIn("SEO068_DIAGNOSTIC_TARGET_MISSING", normalizer.source)
            self.assertIn("SEO068_WRONG_DIAGNOSTIC", normalizer.source)
            helper = next(patcher._function_spans(self.candidate[name], "_ua068_ensure_diag_files"))
            self.assertIn('_UA081_STAGE_ONLY', helper.source)
            self.assertIn('return payload.decode("utf-8")', helper.source)

    def test_publisher_is_existing_real_master_path(self):
        publisher = next(patcher._function_spans(self.candidate["publikaciya.py"], "opublikovat"))
        for required in (
            "_master(kod)",
            "proverit(html, kod)",
            "_ua9_sobrat_katalog()",
            "_stage_only_begin()",
            "_zapisat_atomarno(path, material)",
            "_otkat(backup_dir, targets)",
        ):
            self.assertIn(required, publisher.source)
        for forbidden in ("render_primary_html", "_postroit_stranicu", "ua-catalog-cards"):
            self.assertNotIn(forbidden, publisher.source)

    def test_drift_fails_closed(self):
        changed = self.original["cars_ui.py"].replace(
            "Машина видна клиентам в каталоге.",
            "Машина видна клиентам в каталоге!",
            1,
        )
        with self.assertRaises(patcher.PatchError):
            patcher.patch_cars_ui(changed, check_full_sha=True)


class PublisherSandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidate = patcher.build_candidates(sources())["publikaciya.py"]
        cls.module_path = HERE / "_candidate_publikaciya.py"
        cls.module_path.write_text(candidate, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.module_path.unlink(missing_ok=True)

    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="task081-publisher-test-"))
        spec = importlib.util.spec_from_file_location(
            "task081_candidate_publikaciya", self.module_path
        )
        self.pub = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(self.pub)
        self.pub.BASE = str(self.temp)
        self.pub.VIDEO = str(self.temp / "video")
        self.pub.SITE = str(self.temp / "site")
        self.pub.LOG = str(self.temp / "publish.log")
        self.pub.REZERV_KORE = str(self.temp / "backups")
        pathlib.Path(self.pub.VIDEO).mkdir()
        pathlib.Path(self.pub.SITE).mkdir()
        self.number = "UA-0013"
        self.row = {"auto_number": self.number, "status": "sea_loaded"}
        self.pub.proverit = lambda html, kod: []
        self._set_fixture(self.number)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    @staticmethod
    def _html(number):
        return (
            "<html><body>" + number
            + '<a href="%s-diag.html">Диагностика</a>' % number
            + "<div>Купить Поделиться index.html wa.me</div><img>"
            + "<style>aspect-ratio:16/10</style>"
            + "x" * 6000
            + "</body></html>"
        )

    @staticmethod
    def _diag(number):
        return "<html><body>%s Материалы диагностики пока не добавлены.</body></html>" % number

    @staticmethod
    def _catalog(numbers, stage=2):
        return "<html><body>" + "".join(
            '<a href="%s.html?v=1"><div data-ua-card="%s" data-ua-stage="%d">%s</div></a>'
            % (number, number, stage, number)
            for number in numbers
        ) + "</body></html>"

    def _set_fixture(self, number, all_numbers=None):
        all_numbers = all_numbers or [number]
        row = {"auto_number": number, "status": "sea_loaded"}
        self.pub._master = lambda kod: (self._html(kod), self._diag(kod), dict(row))
        self.pub._ua9_sobrat_katalog = lambda: (
            self._catalog(all_numbers),
            [{"auto_number": value, "status": "sea_loaded"} for value in all_numbers],
        )
        fake_stranica = types.SimpleNamespace(nomer=lambda value: value["auto_number"])
        sys.modules["stranica"] = fake_stranica

    def test_probe_is_zero_write_and_real_install_is_complete(self):
        for folder in (pathlib.Path(self.pub.VIDEO), pathlib.Path(self.pub.SITE)):
            (folder / "katalog.html").write_text("PREIMAGE", encoding="utf-8")
        before = {
            str(path): path.read_bytes()
            for folder in (pathlib.Path(self.pub.VIDEO), pathlib.Path(self.pub.SITE))
            for path in folder.iterdir()
        }
        ok, message = self.pub.opublikovat(self.number, proba=True)
        self.assertTrue(ok, message)
        after_probe = {
            str(path): path.read_bytes()
            for folder in (pathlib.Path(self.pub.VIDEO), pathlib.Path(self.pub.SITE))
            for path in folder.iterdir()
        }
        self.assertEqual(after_probe, before)

        ok, message = self.pub.opublikovat(self.number, proba=False)
        self.assertTrue(ok, message)
        for folder in (pathlib.Path(self.pub.VIDEO), pathlib.Path(self.pub.SITE)):
            self.assertIn(self.number, (folder / (self.number + ".html")).read_text())
            self.assertIn("диагностики", (folder / (self.number + "-diag.html")).read_text())
            self.assertEqual((folder / "katalog.html").read_text().count(self.number + ".html"), 1)

    def test_future_ua9999_uses_same_path(self):
        number = "UA-9999"
        self._set_fixture(number)
        ok, message = self.pub.opublikovat(number, proba=False)
        self.assertTrue(ok, message)
        for folder in (pathlib.Path(self.pub.VIDEO), pathlib.Path(self.pub.SITE)):
            self.assertTrue((folder / (number + ".html")).is_file())
            self.assertTrue((folder / (number + "-diag.html")).is_file())

    def test_partial_write_rolls_back_every_target(self):
        targets = []
        for folder in (pathlib.Path(self.pub.VIDEO), pathlib.Path(self.pub.SITE)):
            for name in (self.number + ".html", self.number + "-diag.html", "katalog.html"):
                path = folder / name
                path.write_text("PREIMAGE:" + str(path), encoding="utf-8")
                targets.append(path)
        preimage = {str(path): path.read_bytes() for path in targets}
        original = self.pub._zapisat_atomarno
        calls = {"count": 0}

        def fail_third(path, material):
            calls["count"] += 1
            if calls["count"] == 3:
                raise RuntimeError("injected partial install")
            return original(path, material)

        self.pub._zapisat_atomarno = fail_third
        ok, message = self.pub.opublikovat(self.number, proba=False)
        self.assertFalse(ok)
        self.assertIn("откат", message.lower())
        self.assertEqual({str(path): path.read_bytes() for path in targets}, preimage)


class _Stop(Exception):
    pass


class _Message:
    def __init__(self):
        self.messages = []

    async def reply_text(self, text, **kwargs):
        self.messages.append(text)


class _DB:
    def __init__(self, state):
        self.state = state

    def update_card_field(self, table, cid, field, value, actor):
        self.state[field] = value


class TogglePublishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidate = patcher.build_candidates(sources())["cars_ui.py"]
        cls.toggle_source = next(
            patcher._function_spans(candidate, "toggle_publish")
        ).source

    def run_toggle(self, publisher, published=0):
        state = {
            "id": 20,
            "auto_number": "UA-0013",
            "published": published,
            "status": "sea_loaded",
            "publish_pending": 0,
        }
        message = _Message()
        query = types.SimpleNamespace(
            data="car_publish:20",
            from_user=types.SimpleNamespace(id=7),
            message=message,
        )
        update = types.SimpleNamespace(callback_query=query)

        async def ack(q):
            return None

        class ContextTypes:
            DEFAULT_TYPE = object

        globals_ = {
            "Update": object,
            "ContextTypes": ContextTypes,
            "_v168_ack": ack,
            "card_of": lambda cid: dict(state),
            "db": _DB(state),
            "S": types.SimpleNamespace(missing_required=lambda card: []),
            "InlineKeyboardMarkup": lambda value: value,
            "InlineKeyboardButton": lambda *args, **kwargs: (args, kwargs),
            "ApplicationHandlerStop": _Stop,
            "log": types.SimpleNamespace(warning=lambda *args, **kwargs: None),
        }
        exec(self.toggle_source, globals_)
        old = sys.modules.get("publikaciya")
        sys.modules["publikaciya"] = types.SimpleNamespace(opublikovat=publisher)
        try:
            with self.assertRaises(_Stop):
                asyncio.run(globals_["toggle_publish"](update, object()))
        finally:
            if old is None:
                sys.modules.pop("publikaciya", None)
            else:
                sys.modules["publikaciya"] = old
        return state, message.messages

    def test_failure_rolls_back_and_sends_one_honest_message(self):
        state, messages = self.run_toggle(
            lambda number: (False, "Публикация отменена: тестовый сбой.")
        )
        self.assertEqual(state["published"], 0)
        self.assertEqual(state["status"], "sea_loaded")
        self.assertEqual(state["publish_pending"], 0)
        self.assertEqual(len(messages), 1)
        self.assertIn("отменена", messages[0].lower())
        self.assertNotIn("Машина видна клиентам", messages[0])

    def test_success_sends_exactly_one_success(self):
        state, messages = self.run_toggle(lambda number: (True, "internal success"))
        self.assertEqual(state["published"], 1)
        self.assertEqual(messages, ["Машина видна клиентам в каталоге."])

    def test_exception_rolls_back_without_false_success(self):
        def explode(number):
            raise RuntimeError("boom")

        state, messages = self.run_toggle(explode)
        self.assertEqual(state["published"], 0)
        self.assertEqual(len(messages), 1)
        self.assertIn("техническая ошибка", messages[0].lower())
        self.assertNotIn("Машина видна клиентам", messages[0])

    def test_hide_path_does_not_publish(self):
        called = []

        def publisher(number):
            called.append(number)
            return True, "unused"

        state, messages = self.run_toggle(publisher, published=1)
        self.assertEqual(state["published"], 0)
        self.assertEqual(called, [])
        self.assertEqual(messages, ["Машина скрыта от клиентов."])


if __name__ == "__main__":
    unittest.main(verbosity=2)
