import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import patcher_v3  # noqa: E402


class TestGdeMashinaTransform(unittest.TestCase):
    def test_excludes_outer_sea_codes_only(self):
        source = (
            "def gde_mashina(cid, nomer_etapa):\n"
            "    rows = []\n"
            "    for stage_no, code, label in S.STATUSES.items():\n"
            "        if stage_no == nomer_etapa:\n"
            "            rows.append(build_button(code, label, cid))\n"
            "    return rows\n"
        )
        result = patcher_v3.transform_gde_mashina_exclude_outer(source)
        self.assertTrue(result.changed)
        self.assertIn('code not in ("sea_loaded", "sea_transit")', result.source)
        self.assertIn("if stage_no == nomer_etapa and code not in", result.source)

    def test_missing_anchor_fails_closed(self):
        with self.assertRaises(patcher_v3.Task073TransformError):
            patcher_v3.transform_gde_mashina_exclude_outer("def gde_mashina(): pass\n")

    def test_double_apply_guard(self):
        source = (
            'if stage_no == nomer_etapa and code not in ("sea_loaded", "sea_transit"):\n'
            "    pass\n"
        )
        with self.assertRaises(patcher_v3.Task073TransformError):
            patcher_v3.transform_gde_mashina_exclude_outer(source)


class TestStageMenuTransform(unittest.TestCase):
    def test_excludes_outer_sea_codes_only(self):
        source = (
            "def stage_menu(cid, number):\n"
            "    rows = []\n"
            "    for stage_no, code, label in S.STATUSES.items():\n"
            "        if stage_no == number:\n"
            "            rows.append(build_button(code, label, cid))\n"
            "    return rows\n"
        )
        result = patcher_v3.transform_stage_menu_exclude_outer(source)
        self.assertTrue(result.changed)
        self.assertIn('code not in ("sea_loaded", "sea_transit")', result.source)


class TestEkranTransform(unittest.TestCase):
    def test_adds_exactly_two_inner_actions(self):
        anchor = "    rows.append(build_days_row(cid, dni))"
        source = (
            "def _ekran(cid):\n"
            "    rows = []\n"
            "    rows.append(build_number_row(cid))\n"
            "    rows.append(build_date_row(cid))\n"
            "{}\n"
            "    rows.append(build_nav_row(cid))\n"
            "    return rows\n"
        ).format(anchor)
        result = patcher_v3.transform_ekran_add_inner_actions(source, anchor)
        self.assertTrue(result.changed)
        self.assertEqual(result.source.count("car_setstage:{cid}:sea_loaded"), 1)
        self.assertEqual(result.source.count("car_setstage:{cid}:sea_transit"), 1)

    def test_double_apply_guard(self):
        anchor = "    rows.append(build_days_row(cid, dni))"
        source = anchor + "\n    # TASK073_INNER_CONTAINER_ACTIONS\n"
        with self.assertRaises(patcher_v3.Task073TransformError):
            patcher_v3.transform_ekran_add_inner_actions(source, anchor)


class TestSeo068Transform(unittest.TestCase):
    def test_drops_only_stale_precondition(self):
        source = (
            "def _ua_seo068_normalize(identifier):\n"
            "    _assert_canonical(identifier)\n"
            "    if not any(_ua_seo068_os.path.isfile(_ua_seo068_os.path.join(root, target)) "
            "for root in ('/home/Carix/video', '/home/Carix/site')):\n"
            "        raise RuntimeError('SEO068_DIAGNOSTIC_TARGET_MISSING:' + identifier)\n"
            "    _assert_robots_ok(identifier)\n"
            "    _assert_exact_href(identifier)\n"
            "    _assert_cta(identifier)\n"
            "    return True\n"
        )
        result = patcher_v3.transform_seo068_drop_stale_precondition(source)
        self.assertTrue(result.changed)
        self.assertNotIn("SEO068_DIAGNOSTIC_TARGET_MISSING", result.source)
        self.assertIn("_assert_canonical", result.source)
        self.assertIn("_assert_robots_ok", result.source)
        self.assertIn("_assert_exact_href", result.source)
        self.assertIn("_assert_cta", result.source)


class TestTogglePublishTransform(unittest.TestCase):
    def test_replaces_exact_block(self):
        old_block = (
            "_ok_rem2, _txt_rem2 = await _aio_rem2.to_thread(_pub_rem2.opublikovat, cid)\n"
            "await update.message.reply_text('Машина видна клиентам в каталоге.')\n"
        )
        new_block = (
            "_ok_rem2, _txt_rem2 = await _aio_rem2.to_thread(_pub_rem2.opublikovat, cid)\n"
            "if _ok_rem2 is True:\n"
            "    await update.message.reply_text('Машина видна клиентам в каталоге.')\n"
            "else:\n"
            "    await update.message.reply_text(_txt_rem2 or 'Публикация отменена.')\n"
        )
        source = "async def toggle_publish():\n" + old_block
        result = patcher_v3.transform_toggle_publish_respect_ok(source, old_block, new_block)
        self.assertTrue(result.changed)
        self.assertIn("if _ok_rem2 is True:", result.source)

    def test_missing_anchor_fails_closed(self):
        with self.assertRaises(patcher_v3.Task073TransformError):
            patcher_v3.transform_toggle_publish_respect_ok("def toggle_publish(): pass\n", "x", "y")


class TestCompileCheck(unittest.TestCase):
    def test_valid_source_passes(self):
        patcher_v3.compile_check("x = 1\n", "sample.py")

    def test_invalid_source_fails_closed(self):
        with self.assertRaises(patcher_v3.Task073TransformError):
            patcher_v3.compile_check("def f(:\n", "broken.py")


if __name__ == "__main__":
    unittest.main()
