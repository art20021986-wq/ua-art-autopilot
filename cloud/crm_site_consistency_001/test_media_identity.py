import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import subprocess
import sys
from unittest.mock import Mock, patch

from crm_media_identity import stable_names, immutable_copy, poster_path, source_unchanged
from crm_gallery import gallery_paths
from build_media_patch import finish_media_patch


class IdentityTests(unittest.TestCase):
    def test_empty_gallery_allows_neutral_ui_but_rejects_retained_car_photo(self):
        from public_media import verify_photo_structure
        card = {'auto_number': 'UA-0001', 'photos': []}
        value = verify_photo_structure('<img src="/video/stage/UA-0001-empty.jpg">', card, [])
        self.assertEqual(value['photo_count'], 0)
        with self.assertRaises(RuntimeError):
            verify_photo_structure('<img src="foto/UA-0001/001.jpg">', card, [])

    def test_empty_cover_is_neutral_and_does_not_read_old_car_photos(self):
        from crm_assets import empty_cover
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / empty_cover(root, 'UA-0099').lstrip('/')
            with Image.open(path) as image:
                self.assertEqual(image.size, (620, 468))
                self.assertEqual(len(image.getcolors()), 1)
            self.assertEqual('/'+str(path.relative_to(root)), empty_cover(root, 'UA-0099'))

    def test_reorder_keeps_names_and_delete_cannot_rebind_ordinal(self):
        old = {'001.jpg': 'a', '002.jpg': 'b', '003.jpg': 'c'}
        got = stable_names('UA-0001', 'photo', ['c', 'b', 'd'], old)
        self.assertEqual(list(got)[:2], ['003.jpg', '002.jpg'])
        self.assertNotIn('001.jpg', got)
        self.assertTrue(list(got)[2].startswith('m-'))
        self.assertEqual(got, stable_names('UA-0001', 'photo', ['c', 'b', 'd'], got))

    def test_distinct_video_ids_keep_distinct_paths_and_empty_list_stays_empty(self):
        got = stable_names('UA-0040', 'video', ['a', 'b'], {})
        self.assertEqual(len(got), 2)
        self.assertEqual(stable_names('UA-0040', 'video', [], got), {})

    def test_bad_bindings_and_duplicate_ids_are_rejected(self):
        for mapping, ids in [({'../001.jpg': 'a'}, ['a']),
                             ({'001.jpg': 'a', '002.jpg': 'a'}, ['a']),
                             ({}, ['a', 'a'])]:
            with self.subTest(mapping=mapping), self.assertRaises(RuntimeError):
                stable_names('UA-0001', 'photo', ids, mapping)

    def test_immutable_copy_retains_original_and_rejects_later_wrong_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'video').mkdir()
            src = root/'video'/'UA-0001.mp4'; src.write_bytes(b'original')
            path = immutable_copy(src, root)
            self.assertEqual(src.read_bytes(), path.read_bytes())
            self.assertIn(hashlib.sha256(b'original').hexdigest(), path.name)
            with patch('crm_media_identity._hash', side_effect=AssertionError('cache miss')):
                self.assertEqual(immutable_copy(src, root), path)
            src.write_bytes(b'different')
            self.assertFalse(source_unchanged(src, root))
            with self.assertRaisesRegex(RuntimeError, 'existing CRM binding'):
                immutable_copy(src, root)
            self.assertEqual(path.read_bytes(), b'original')
            index = json.loads(next((root/'.crm_media_index').glob('*.json')).read_text())
            self.assertFalse(index['telegram_original_verified'])
            src.write_bytes(b'original')
            self.assertTrue(source_unchanged(src, root))

    def test_tampered_public_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'video').mkdir()
            src = root/'video'/'UA-0001.mp4'; src.write_bytes(b'original')
            path = immutable_copy(src, root); path.write_bytes(b'tampered')
            with self.assertRaisesRegex(RuntimeError, 'corrupted'):
                immutable_copy(src, root)

    def test_unsafe_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'video').mkdir()
            source = root/'outside.mp4'; source.write_bytes(b'original')
            link = root/'video'/'UA-0001.mp4'; link.symlink_to(source)
            for path in (source, link):
                with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
                    immutable_copy(path, root)

    def test_low_disk_space_leaves_original_and_public_files_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'video').mkdir()
            src = root/'video'/'UA-0001.mp4'; src.write_bytes(b'original')
            with patch('crm_media_identity.shutil.disk_usage', return_value=Mock(free=1)):
                with self.assertRaisesRegex(RuntimeError, 'Insufficient space'):
                    immutable_copy(src, root)
            self.assertEqual(list((root/'video').iterdir()), [src])
            self.assertEqual(src.read_bytes(), b'original')

    def test_crm_deletion_hiding_and_order_control_immutable_gallery(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); folder = root/'video'/'foto'/'UA-0001'; folder.mkdir(parents=True)
            for n in ('001.jpg', '002.jpg', '003.jpg'):
                (folder/n).write_bytes(b'\xff\xd8'+n.encode()+b'x'*1200)
            (root/'.video_sinhron.json').write_text(json.dumps({'foto:UA-0001':
                {'001.jpg': 'a', '002.jpg': 'b', '003.jpg': 'c'}}))
            card = {'auto_number': 'UA-0001', 'photos': ['c', 'a', 'b'], 'hidden_photos': ['a']}
            paths = gallery_paths(card, root)
            self.assertTrue(Path(paths[0]).name.startswith('003-'))
            self.assertTrue(Path(paths[1]).name.startswith('002-'))
            card['photos'] = []; card['cover_photo'] = '001.jpg'
            self.assertEqual(gallery_paths(card, root), [])
            self.assertTrue((folder/'001.jpg').exists())

    def test_poster_is_immutable_and_missing_poster_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'video').mkdir()
            src = root/'video'/'UA-0001.mp4'; src.write_bytes(b'video')
            canonical = immutable_copy(src, root).name
            self.assertEqual(poster_path(canonical, root), '')
            (root/'video'/'UA-0001.poster.jpg').write_bytes(b'poster')
            path = root/'video'/poster_path(canonical, root)
            self.assertEqual(path.read_bytes(), b'poster')
            (root/'video'/'UA-0001.mp4.poster.jpg').write_bytes(b'current-poster')
            self.assertEqual((root/'video'/poster_path(canonical, root)).read_bytes(), b'current-poster')


class ActualDownloaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.pub = self.root/'video'; self.pub.mkdir()
        from runtime_media_fixture import SOURCE
        source = finish_media_patch('video_sinhron.py', SOURCE)
        self.cards = {'UA-0001': {'video': [], 'foto': ['b', 'c']}}
        self.ledger = {'foto:UA-0001': {'001.jpg': 'a', '002.jpg': 'b'}}
        folder = self.pub/'foto'/'UA-0001'; folder.mkdir(parents=True)
        (folder/'001.jpg').write_bytes(b'retained-a'); (folder/'002.jpg').write_bytes(b'existing-b')
        self.source = source

    def run_candidate(self, scenario='normal'):
        # Use the project's existing isolated-interpreter test pattern. No exec,
        # inherited credentials, network adapter or running worker is available.
        data = {'root': str(self.root), 'cards': self.cards, 'ledger': self.ledger, 'scenario': scenario}
        prelude = 'import os,json,time,sys,copy,io,types,shutil\nfrom pathlib import Path\n'
        prelude += 'sys.path.insert(0,' + repr(str(Path(__file__).resolve().parent)) + ')\n'
        prelude += 'data=json.loads(' + repr(json.dumps(data)) + ')\n'
        setup = '''
DOM=Path(data['root']); PUB=str(DOM/'video'); STOP=str(DOM/'STOP')
PAMYAT=str(DOM/'ledger.json'); PREDEL_ZA_PROHOD=1; PREDEL_FOTO_ZA_PROHOD=6
POVTOR_MERTVYH=21600; ledger=data['ledger']; downloads=[]; queued=[]
mashiny=lambda:data['cards']
pamyat_chitat=lambda:copy.deepcopy(ledger)
svoi_fayly=lambda code:[]
svoi_foto=lambda code:[]
foto_papka=lambda code:str(DOM/'video'/'foto'/code)
vnutri_jpeg=lambda path:True
vnutri_mp4=lambda path:True
log=lambda message:None
def forbidden(*args):raise AssertionError('physical media or cache deletion')
ubrat=chistit_kesh=forbidden
def pamyat_pisat(value):
    global ledger
    if data['scenario']=='ledger-failure':return False
    ledger=copy.deepcopy(value);return True
original_download=skachat
def skachat(fid,path,check=None):
    if data['scenario']=='download-failure':return False,'temporary error'
    downloads.append(fid);Path(path).write_bytes(fid.encode());return True,'downloaded'
def peresobrat():
    queued.append(True);return True,'queued'
error='';result=''
try:
    if data['scenario']=='truncated-download':
        class Response(io.BytesIO):headers={'Content-Length':'1000'}
        urllib=types.SimpleNamespace(request=types.SimpleNamespace(urlopen=lambda *args,**kwargs:Response(b'partial')))
        tokeny=lambda:['synthetic-token']
        put_v_telegram=lambda *args:'synthetic.mp4'
        TAYMAUT_SKACHIVANIYA=1
        result=original_download('synthetic-id',str(DOM/'video'/'test.mp4'))
    elif data['scenario']=='large-list':
        result=len(_spisok_fid(json.dumps(['synthetic-%d'%n for n in range(140)]),100))
    else:
        result=prohod()
        if data['scenario']=='download-failure':result=prohod()
except Exception as exc:error=type(exc).__name__+': '+str(exc)
print(json.dumps({'ledger':ledger,'downloads':downloads,'queued':len(queued),'result':result,'error':error}))
'''
        script = self.root/'candidate_test.py'
        script.write_text(prelude+self.source+'\n'+setup)
        result = subprocess.run([sys.executable, '-I', '-B', str(script)], cwd=self.root,
                                env={}, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.ledger = value['ledger']
        return value

    def tearDown(self):
        self.temp.cleanup()

    def test_removal_and_addition_keep_old_files_and_do_not_renumber(self):
        result = self.run_candidate()
        self.assertEqual(result['error'], '')
        self.assertEqual(result['downloads'], ['c'])
        self.assertEqual((self.pub/'foto/UA-0001/001.jpg').read_bytes(), b'retained-a')
        self.assertEqual((self.pub/'foto/UA-0001/002.jpg').read_bytes(), b'existing-b')
        self.assertEqual(self.ledger['foto:UA-0001']['002.jpg'], 'b')
        self.assertNotIn('001.jpg', self.ledger['foto:UA-0001'])
        self.assertEqual(result['queued'], 1)
        self.assertIn('очередь', result['result'])

    def test_delete_all_persists_empty_mapping_without_deleting_originals(self):
        self.cards['UA-0001']['foto'] = []
        result = self.run_candidate()
        self.assertNotIn('foto:UA-0001', self.ledger)
        self.assertTrue((self.pub/'foto/UA-0001/001.jpg').exists())
        self.assertEqual(result['queued'], 1)

    def test_failed_ledger_commit_cannot_request_publication(self):
        result = self.run_candidate('ledger-failure')
        self.assertIn('not committed', result['error'])
        self.assertEqual(result['queued'], 0)

    def test_bad_card_does_not_stop_the_next_card(self):
        self.ledger['UA-0000'] = {'wrong-path.mp4': 'bad'}
        self.cards['UA-0000'] = {'video': ['bad'], 'foto': []}
        result = self.run_candidate()
        self.assertEqual(result['downloads'], ['c'])

    def test_failed_download_cannot_return_all_matches(self):
        self.cards['UA-0001']['foto'] = ['b', 'c']
        result = self.run_candidate('download-failure')
        self.assertIn('ожидают', result['result'])
        self.assertNotIn('c', self.ledger['foto:UA-0001'].values())

    def test_photo_count_is_not_silently_truncated(self):
        self.assertEqual(self.run_candidate('large-list')['result'], 140)

    def test_large_first_album_cannot_starve_next_card_across_passes(self):
        self.cards = {'UA-0001': {'video': [], 'foto': ['big-%d' % n for n in range(140)]},
                      'UA-0002': {'video': [], 'foto': ['next-card']}}
        first = self.run_candidate()
        self.assertNotIn('next-card', first['downloads'])
        second = self.run_candidate()
        self.assertIn('next-card', second['downloads'])
        self.assertEqual(second['error'], '')

    def test_cursor_only_change_does_not_enqueue_publication(self):
        self.cards = {'UA-0001': {'video': [], 'foto': []},
                      'UA-0002': {'video': [], 'foto': []}}
        self.ledger = {'_ne_kachaetsya': {}}
        first = self.run_candidate()
        second = self.run_candidate()
        self.assertEqual(first['queued'], 0)
        self.assertEqual(second['queued'], 0)
        self.assertEqual(self.ledger['_crm_media_cursor'], 'UA-0002')

    def test_truncated_response_never_replaces_a_complete_original(self):
        original=self.pub/'test.mp4'; original.write_bytes(b'previous-complete')
        result=self.run_candidate('truncated-download')
        self.assertEqual(result['error'], '')
        self.assertFalse(result['result'][0])
        self.assertEqual(original.read_bytes(), b'previous-complete')
        self.assertFalse((self.pub/'test.mp4.part').exists())


if __name__ == '__main__':
    unittest.main()
