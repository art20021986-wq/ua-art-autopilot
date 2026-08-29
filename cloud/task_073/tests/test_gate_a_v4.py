import gate_a_v4 as gav4


class FakeResp:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8", "ignore")

    def json(self):
        return {}


class FakeSession:
    def __init__(self, contents):
        self.contents = contents

    def get(self, url, headers=None, timeout=None):
        for filename, content in self.contents.items():
            if filename in url:
                return FakeResp(200, content.encode("utf-8"))
        return FakeResp(404, b"")


def test_missing_credentials_blocks():
    result = gav4.run_gate_a(session=object(), username=None, token=None)
    assert result["status"] == "BLOCKED_NO_LIVE_CREDENTIALS"


def test_sha_drift_fails_closed():
    fake_contents = {name: "not the real file: %s" % name for name in gav4.pv4.FULL_FILE_ANCHORS}
    session = FakeSession(fake_contents)
    result = gav4.run_gate_a(session=session, username="Carix", token="x")
    assert result["status"] == "FAIL_SHA_DRIFT"
    assert result["production_writes"] == 0
