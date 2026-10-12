#!/usr/bin/env python3
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

PAGE = ("<div class='lenta'><div class='kadr'><img src='foto/UA-0001/d/m/001.jpg' loading='eager'></div></div>"
        "<video controls><source src='video/UA-0001-d1.mp4' type='video/mp4'></video><div class='schet'>1 видео</div>")
SOURCE = ("def kadry_diagnostiki(m):\n    return [], []\n"
          "def other():\n    return 'x'\n"
          "def leak():\n    password = 'diag_video'\n")


def database():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'x.db'
        con = sqlite3.connect(path)
        con.executescript(
            "CREATE TABLE media(id INTEGER PRIMARY KEY, car_id INT, auto_number TEXT, vid TEXT, file_id TEXT,"
            " put TEXT, status TEXT, poryadok INT);"
            "INSERT INTO media VALUES (1, 7, 'UA-0001', 'diag_video', 'SECRET-FILE-ID', 'v.mp4', 'ready', 1);"
            "INSERT INTO media VALUES (2, 7, 'UA-0001', 'foto', 'X', 'f.jpg', 'ready', 1);"
            "CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, published INT, status TEXT,"
            " diag_text TEXT, diag_link TEXT, condition_videos TEXT);"
            "INSERT INTO cars VALUES (7, 'UA-0001', 1, 'ge_waiting', 'ok', '', '[\"a\",\"b\"]');")
        con.commit()
        con.close()
        return path.read_bytes()


class Fake:
    def server(self, path):
        return {'stranica.py': SOURCE.encode(), 'crm.db': database(),
                'video/': json.dumps({'UA-0001-diag.html': {'type': 'file'}, 'foto': {'type': 'directory'}}).encode(),
                'video/UA-0001-diag.html': PAGE.encode()}.get(path)


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object())
        for bad in ('cars_ui.py', 'video/../crm.db', 'video/UA-0001.mp4', '.env'):
            with self.assertRaises(c.ProbeError):
                reader.server(bad)

    def test_excerpts_select_and_skip_secrets(self):
        text = c.excerpts(SOURCE)
        self.assertIn('kadry_diagnostiki', text)
        self.assertNotIn('other', text)
        self.assertNotIn('password', text)

    def test_execute(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / c.REQUEST).parent.mkdir(parents=True)
            (root / c.REQUEST).write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': c.TASK_ID, 'UAART_RECEIPT_PATH': c.RECEIPT, 'UAART_REQUEST_PATH': c.REQUEST,
                   'UAART_REQUEST_SHA256': c.sha((root / c.REQUEST).read_bytes()), 'UAART_RUN_ID': '1'}
            c.execute(env, root=root, reader=Fake())
            evidence = json.loads((root / c.EVIDENCE).read_text())
        self.assertEqual([m['vid'] for m in evidence['crm']['diag_media']], ['diag_video'])
        self.assertNotIn('SECRET-FILE-ID', json.dumps(evidence))
        self.assertEqual(evidence['crm']['cars']['UA-0001']['condition_videos_count'], 2)
        self.assertEqual(evidence['diag_pages']['UA-0001']['videos'], ['video/UA-0001-d1.mp4'])
        self.assertEqual(evidence['video_directories'], ['foto'])


if __name__ == '__main__':
    unittest.main()
