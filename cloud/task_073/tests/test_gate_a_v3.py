import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gate_a_v3 as ga  # noqa: E402


class TestCredentialsGate(unittest.TestCase):
    def test_blocked_without_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            report = ga.run_gate_a()
        self.assertEqual(report.blocked_reason, "GATE_A_V3_BLOCKED_NO_CREDENTIALS")
        self.assertEqual(report.checks, [])


class TestDryRunPublishMatrix(unittest.TestCase):
    def test_offline_dry_run_matrix_passes(self):
        report = ga.GateAReport()
        ga.dry_run_publish_matrix(report)
        for check in report.checks:
            self.assertTrue(check.passed, msg="{}: {}".format(check.name, check.detail))


class TestTransformStage(unittest.TestCase):
    def test_transform_stage_produces_compilable_sources(self):
        sources = {
            "konteyner.py": (
                "def gde_mashina(cid, nomer_etapa):\n"
                "    rows = []\n"
                "    for stage_no, code, label in S.STATUSES.items():\n"
                "        if stage_no == nomer_etapa:\n"
                "            rows.append(build_button(code, label, cid))\n"
                "    return rows\n"
                "\n"
                "def _ekran(cid):\n"
                "    rows = []\n"
                "    rows.append(build_number_row(cid))\n"
                "    rows.append(build_days_row(cid, dni))\n"
                "    rows.append(build_nav_row(cid))\n"
                "    return rows\n"
            ),
            "cars_ui.py": (
                "def stage_menu(cid, number):\n"
                "    rows = []\n"
                "    for stage_no, code, label in S.STATUSES.items():\n"
                "        if stage_no == number:\n"
                "            rows.append(build_button(code, label, cid))\n"
                "    return rows\n"
            ),
            "stranica.py": (
                "def _ua_seo068_normalize(identifier):\n"
                "    if not any(_ua_seo068_os.path.isfile(_ua_seo068_os.path.join(root, target)) "
                "for root in ('/home/Carix/video', '/home/Carix/site')):\n"
                "        raise RuntimeError('SEO068_DIAGNOSTIC_TARGET_MISSING:' + identifier)\n"
                "    return True\n"
            ),
            "master_card.py": (
                "def _ua_seo068_normalize(identifier):\n"
                "    if not any(_ua_seo068_os.path.isfile(_ua_seo068_os.path.join(root, target)) "
                "for root in ('/home/Carix/video', '/home/Carix/site')):\n"
                "        raise RuntimeError('SEO068_DIAGNOSTIC_TARGET_MISSING:' + identifier)\n"
                "    return True\n"
            ),
            "yadro.py": (
                "def _ua_seo068_normalize(identifier):\n"
                "    if not any(_ua_seo068_os.path.isfile(_ua_seo068_os.path.join(root, target)) "
                "for root in ('/home/Carix/video', '/home/Carix/site')):\n"
                "        raise RuntimeError('SEO068_DIAGNOSTIC_TARGET_MISSING:' + identifier)\n"
                "    return True\n"
            ),
            "_ekran_rows_anchor": "    rows.append(build_days_row(cid, dni))",
        }
        report = ga.GateAReport()
        patched = ga.run_transform_stage(sources, report)
        ga.compile_check_all(patched, report)
        for check in report.checks:
            self.assertTrue(check.passed, msg="{}: {}".format(check.name, check.detail))
        self.assertEqual(patched["konteyner.py"].count("sea_loaded"), 2)
        self.assertEqual(patched["konteyner.py"].count("sea_transit"), 2)


if __name__ == "__main__":
    unittest.main()
