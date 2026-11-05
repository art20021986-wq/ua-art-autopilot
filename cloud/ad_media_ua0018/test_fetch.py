import unittest
from fetch import media_paths


class MediaPathsTest(unittest.TestCase):
    def test_extracts_full_size_photos_and_video(self):
        html = ('<a href="foto/UA-0018/002.jpg"><img src="foto/UA-0018/m/001.jpg">'
                '"src":"foto/UA-0018/001.jpg" <video src="UA-0018.mp4" poster="UA-0018.mp4.poster.jpg">'
                'foto/UA-0017/001.jpg')
        photos, videos = media_paths(html, 'UA-0018')
        self.assertEqual(photos, ['foto/UA-0018/001.jpg', 'foto/UA-0018/002.jpg'])
        self.assertEqual(videos, ['UA-0018.mp4'])


if __name__ == '__main__':
    unittest.main()
