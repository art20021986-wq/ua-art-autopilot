"""The KOREA-TERMS candidate from the live Korea page."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402


class CandidateTests(unittest.TestCase):
    def test_only_the_two_blocks_go(self):
        page = (HERE / 'fixtures' / 'korea_live.html').read_text()
        new = candidate_builder.build({'video/korea.html': page.encode()}, {})['video/korea.html'].decode()
        for gone in ('class="kr-deposit"', 'Як це працює', 'Договір і депозит 2000 $', 'Купуємо, веземо, розмитнюємо'):
            self.assertNotIn(gone, new)
        start = page.index(candidate_builder.DEPOSIT)
        removed = page[start:start + len(page) - len(new)]
        self.assertEqual(page[:start] + page[start + len(removed):], new)
        self.assertEqual(removed.count('<section'), 2)
        self.assertEqual(new.count('<section'), page.count('<section') - 2)
        for kept in ('kr-hero', 'Два способи купити авто з UA ART', 'Аукціони, до яких ви отримуєте доступ'):
            self.assertIn(kept, new)
        with self.assertRaises(ValueError):
            candidate_builder.build({'video/korea.html': new.encode()}, {})


if __name__ == '__main__':
    unittest.main()
