"""Tell IndexNow search engines (Bing, which feeds ChatGPT and Copilot) which public URLs changed.

Best effort: one POST with a short timeout. A failure is returned, never raised, so
publication never waits on or fails because of a search engine. The key is public
by design: search engines read it from KEY_LOCATION to confirm site ownership.
"""
import json
import urllib.request

HOST = 'www.uaart.com.ua'
KEY = '2276049735fd4daeaf42574afb0c29a3'
KEY_FILE = 'video/%s.txt' % KEY
KEY_LOCATION = 'https://%s/%s' % (HOST, KEY_FILE)
# A key file in /video/ covers only URLs under /video/.
SCOPE = 'https://%s/video/' % HOST
ENDPOINT = 'https://api.indexnow.org/indexnow'


def submit(urls, opener=urllib.request.urlopen, timeout=5):
    urls = sorted({url for url in urls if url.startswith(SCOPE)})[:10000]
    if not urls:
        return {'status': 'SKIP'}
    body = json.dumps({'host': HOST, 'key': KEY, 'keyLocation': KEY_LOCATION, 'urlList': urls}).encode()
    request = urllib.request.Request(ENDPOINT, data=body, method='POST', headers={
        'Content-Type': 'application/json; charset=utf-8', 'User-Agent': 'uaart-indexnow/1'})
    try:
        with opener(request, timeout=timeout) as response:
            return {'status': 'PASS', 'http': response.status, 'urls': len(urls)}
    except Exception as error:
        return {'status': 'FAIL', 'error': (type(error).__name__ + ':' + str(error))[:160], 'urls': len(urls)}
