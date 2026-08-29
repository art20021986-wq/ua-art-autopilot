#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

from patcher import MARKER, patch_ai_filter, patch_local_ocr, validate_candidates


AI_FILTER_FIXTURE = '''\
from datetime import date

ALLOWED = {"year": (), "engine_cc": (), "mileage_km": (), "fuel": (), "vin": ()}
FALLBACK = []
def flatten(value): return dict(value)
def _all_text(flat): return " | ".join(str(v) for v in flat.values())
def _pick(flat, keys): return None
def _cc(raw): return int(raw)
def _km(raw): return int(raw)
def _year(raw): return int(raw)
def _map(raw, table): return raw
def _log_parsed(parsed, out): return None
FUEL = GEARBOX = DRIVE = COLOR = {}

def clean(parsed, extra_text=""):
    flat = flatten(parsed if isinstance(parsed, dict) else {})
    text_all = _all_text(flat)
    if extra_text:
        text_all = text_all + " | " + str(extra_text)
    out = dict(parsed)
    for field, keys in ALLOWED.items():
        raw = _pick(flat, keys)
        if raw in (None, "", "-", "—"):
            for f2, rx in FALLBACK:
                if f2 != field:
                    continue
                m = rx.search(text_all)
                if m:
                    raw = m.group(1) if m.groups() else m.group(0)
                    break
        if raw in (None, ""):
            continue
    _log_parsed(parsed, out)
    return out
'''

LOCAL_OCR_FIXTURE = '''\
import re
def fields_from_text(text: str, allowed_keys) -> dict:
    allowed = set(allowed_keys or ())
    data = {}
    raw = str(text or "")
    years = re.findall(r"(?<!\\d)((?:19|20)\\d{2})(?!\\d)", raw)
    if years and "year" in allowed:
        data["year"] = int(years[0])
    cc = re.search(r"(\\d[\\d,. ]*)\\s*cc", raw, re.I)
    if cc and "engine_cc" in allowed:
        data["engine_cc"] = int(re.sub(r"\\D", "", cc.group(1)))
    return data
'''


class PatcherTests(unittest.TestCase):
    def test_candidates_compile_and_are_idempotent(self):
        ai = patch_ai_filter(AI_FILTER_FIXTURE)
        ocr = patch_local_ocr(LOCAL_OCR_FIXTURE)
        self.assertTrue(all(validate_candidates(ai, ocr).values()))
        self.assertEqual(patch_ai_filter(ai), ai)
        self.assertEqual(patch_local_ocr(ocr), ocr)
        self.assertEqual(ai.count(MARKER), 1)
        self.assertEqual(ocr.count(MARKER), 1)

    def test_patched_ai_filter_removes_duplicate_year(self):
        candidate = patch_ai_filter(AI_FILTER_FIXTURE)
        namespace = {}
        exec(compile(candidate, "ai_filter.py", "exec"), namespace)
        parsed = {"year": 1999, "engine_cc": 1999, "mileage_km": 395459}
        result = namespace["clean"](
            parsed, "LPG\n1,999cc\n395,459km\nKMHE341DBJA475862")
        self.assertNotIn("year", result)
        self.assertEqual(result["engine_cc"], 1999)
        self.assertEqual(result["mileage_km"], 395459)

    def test_patched_local_ocr_does_not_claim_cc_as_year(self):
        candidate = patch_local_ocr(LOCAL_OCR_FIXTURE)
        namespace = {}
        exec(compile(candidate, "local_ocr.py", "exec"), namespace)
        result = namespace["fields_from_text"](
            "1,999cc", {"year", "engine_cc"})
        self.assertEqual(result, {"engine_cc": 1999})


if __name__ == "__main__":
    unittest.main()
