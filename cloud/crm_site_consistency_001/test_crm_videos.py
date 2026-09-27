import json
from pathlib import Path
import tempfile
import unittest

from crm_videos import select_video_names, verify_video_structure, video_paths


def player(name):
    return ('<video controls><source src="%s" type="video/mp4">'
            '<a href="%s">Open video</a></video>') % (name, name)


class VideoTests(unittest.TestCase):
    def setUp(self):
        self.card = {'auto_number': 'UA-0005', 'videos': [
            {'file_id': 'video-b', 'tag': 'walkaround'},
            {'file_id': 'video-a', 'tag': 'interior'}]}
        self.ledger = {'UA-0005': {
            'UA-0005.mp4': 'video-a', 'UA-0005-02.mp4': 'video-b',
            'UA-0005-03.mp4': 'removed-video'}}
        self.expected = ['UA-0005-02.mp4', 'UA-0005.mp4']

    def test_crm_order_wins_and_removed_file_is_excluded(self):
        self.assertEqual(select_video_names(self.card, self.ledger), self.expected)

    def test_delete_all_does_not_restore_files_from_old_ledger(self):
        self.card['videos'] = []
        self.assertEqual(select_video_names(self.card, self.ledger), [])
        verify_video_structure('<p>No video</p>', self.card, [])
        with self.assertRaisesRegex(RuntimeError, 'CRM order'):
            verify_video_structure(player('UA-0005.mp4'), self.card, [])

    def test_hidden_video_is_excluded_when_visibility_field_exists(self):
        self.card['hidden_videos'] = ['video-b']
        self.assertEqual(select_video_names(self.card, self.ledger), ['UA-0005.mp4'])

    def test_unmapped_original_blocks_success(self):
        del self.ledger['UA-0005']['UA-0005.mp4']
        with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
            select_video_names(self.card, self.ledger)

    def test_missing_ledger_is_not_inferred_from_file_order(self):
        with self.assertRaisesRegex(RuntimeError, 'missing'):
            select_video_names(self.card, {})

    def test_ambiguous_mapping_is_rejected(self):
        self.ledger['UA-0005']['UA-0005-04.mp4'] = 'video-a'
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous'):
            select_video_names(self.card, self.ledger)

    def test_foreign_or_traversal_filename_rejected(self):
        for name in ('../UA-0005.mp4', 'UA-0006.mp4'):
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'filename'):
                select_video_names(self.card, {'UA-0005': {name: 'video-a'}})

    def test_duplicate_crm_ids_rejected(self):
        self.card['videos'] = ['video-a', 'video-a']
        with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
            select_video_names(self.card, self.ledger)

    def test_legacy_json_list_supported(self):
        self.card['videos'] = json.dumps(['video-b', 'video-a'])
        self.assertEqual(select_video_names(self.card, self.ledger), self.expected)

    def test_valid_structure_does_not_claim_byte_identity_or_playback(self):
        html = ''.join(player(x) for x in self.expected)
        result = verify_video_structure(html, self.card, self.expected)
        self.assertTrue(result['structure_verified'])
        self.assertFalse(result['content_identity_verified'])
        self.assertFalse(result['playback_verified'])
        self.assertFalse(result['full_consistency_accepted'])

    def test_reordering_with_equal_count_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'CRM order'):
            verify_video_structure(''.join(player(x) for x in reversed(self.expected)),
                                   self.card, self.expected)

    def test_stale_fallback_link_rejected(self):
        html = ''.join(player(x) for x in self.expected).replace(
            'href="UA-0005.mp4"', 'href="UA-0005-03.mp4"')
        with self.assertRaisesRegex(RuntimeError, 'fallback'):
            verify_video_structure(html, self.card, self.expected)

    def test_ambiguous_incomplete_or_foreign_player_rejected(self):
        html = ''.join(player(x) for x in self.expected)
        variants = [html.replace('</video>', '', 1),
                    html.replace('<source', '<source src="old.mp4"><source', 1),
                    html.replace('UA-0005-02.mp4', 'UA-0006.mp4'),
                    html.replace('video/mp4', 'text/html')]
        for bad in variants:
            with self.subTest(html=bad), self.assertRaises(RuntimeError):
                verify_video_structure(bad, self.card, self.expected)

    def test_paths_require_available_local_file_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'video').mkdir()
            journal = root/'.video_sinhron.json'
            journal.write_text(json.dumps(self.ledger))
            before = journal.read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                video_paths(self.card, root)
            for name in self.expected:
                (root/'video'/name).write_bytes(b'fixture-not-a-decoded-mp4')
            self.assertEqual(video_paths(self.card, root), self.expected)
            self.assertEqual(journal.read_bytes(), before)
            (root/'video'/self.expected[0]).unlink()
            (root/'video'/self.expected[0]).symlink_to(root/'video'/self.expected[1])
            with self.assertRaisesRegex(RuntimeError, 'escapes'):
                video_paths(self.card, root)


if __name__ == '__main__':
    unittest.main()
