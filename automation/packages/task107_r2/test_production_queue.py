#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import pathlib
import sys
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse


ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "automation"))
import production_queue as PQ  # noqa: E402


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class ProductionQueueTests(unittest.TestCase):
    def test_fetch_runs_paginates_past_first_hundred(self):
        calls = []

        def open_request(request, timeout):
            self.assertEqual(timeout, 30)
            calls.append(request.full_url)
            query = parse_qs(urlparse(request.full_url).query)
            page = int(query["page"][0])
            status = query["status"][0]
            offset = sorted(PQ.ACTIVE_STATES).index(status) * 1000
            values = (
                [{"id": offset + index + 1} for index in range(100)]
                if page == 1 else [{"id": offset + 101}]
            )
            return Response(json.dumps({"workflow_runs": values}).encode("utf-8"))

        with mock.patch.object(PQ.urllib.request, "urlopen", side_effect=open_request):
            runs = PQ.fetch_runs("owner/repo", "token")
        self.assertEqual(len(runs), 101 * len(PQ.ACTIVE_STATES))
        self.assertEqual(len(calls), 2 * len(PQ.ACTIVE_STATES))
        self.assertTrue(all("status=" in url for url in calls))

    def test_central_critical_workflow_is_recognized_as_production(self):
        self.assertTrue(PQ.is_production_run({
            "name": "UA ART CRITICAL Pipeline",
            "path": ".github/workflows/uaart_critical.yml",
        }))


if __name__ == "__main__":
    unittest.main()
