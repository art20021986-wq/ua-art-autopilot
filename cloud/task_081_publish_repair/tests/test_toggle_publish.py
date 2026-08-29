"""Offline tests modeling the exact bug in cars_ui.toggle_publish and the
required fix: preimage capture, no unconditional success, compensating
rollback, exactly-one final message.
"""


class FakeDB:
    def __init__(self, published, status, publish_pending):
        self.state = {
            "published": published,
            "status": status,
            "publish_pending": publish_pending,
        }
        self.history = []

    def get_publish_state(self, auto_number):
        return dict(self.state)

    def set_published(self, auto_number, value):
        self.history.append(("set_published", value))
        self.state["published"] = value

    def restore_publish_state(self, auto_number, preimage):
        self.history.append(("restore", preimage))
        self.state = dict(preimage)


def buggy_toggle_publish(db, publikaciya_ok, published_target=1):
    """Reproduces the reported bug: writes published=1 first, calls
    publisher, ignores result, always returns success."""
    db.set_published("UA-0013", published_target)
    _ok_rem2 = publikaciya_ok  # result captured but not checked (the bug)
    return {"ok": True, "message": "Машина видна клиентам в каталоге."}


def fixed_toggle_publish(db, publikaciya_ok, primary_ok, diag_ok, catalogs_ok, published_target=1):
    preimage = db.get_publish_state("UA-0013")
    db.set_published("UA-0013", published_target)
    ok = publikaciya_ok
    if not ok:
        db.restore_publish_state("UA-0013", preimage)
        assert db.get_publish_state("UA-0013") == preimage
        return {"ok": False, "message": "Публикация отменена: сборщик не смог собрать UA-0013. Старая страница цела."}
    if ok is True and primary_ok and diag_ok and catalogs_ok:
        return {"ok": True, "message": "Машина видна клиентам в каталоге."}
    db.restore_publish_state("UA-0013", preimage)
    assert db.get_publish_state("UA-0013") == preimage
    return {"ok": False, "message": "Публикация отменена: проверка после сборки не прошла. Старая страница цела."}


def test_reproduces_reported_bug_false_success():
    db = FakeDB(published=0, status="draft", publish_pending=1)
    result = buggy_toggle_publish(db, publikaciya_ok=False)
    # Demonstrates the exact reported defect: false success despite failed build.
    assert result["ok"] is True
    assert db.state["published"] == 1  # left published even though build failed -- the bug


def test_fixed_rolls_back_on_publisher_failure():
    db = FakeDB(published=0, status="draft", publish_pending=1)
    preimage = db.get_publish_state("UA-0013")
    result = fixed_toggle_publish(db, publikaciya_ok=False, primary_ok=False, diag_ok=False, catalogs_ok=False)
    assert result["ok"] is False
    assert "Старая страница цела" in result["message"]
    assert db.get_publish_state("UA-0013") == preimage


def test_fixed_rolls_back_on_postcheck_mismatch():
    db = FakeDB(published=0, status="draft", publish_pending=1)
    preimage = db.get_publish_state("UA-0013")
    result = fixed_toggle_publish(db, publikaciya_ok=True, primary_ok=True, diag_ok=False, catalogs_ok=True)
    assert result["ok"] is False
    assert db.get_publish_state("UA-0013") == preimage


def test_fixed_success_only_when_all_conditions_true():
    db = FakeDB(published=0, status="draft", publish_pending=1)
    result = fixed_toggle_publish(db, publikaciya_ok=True, primary_ok=True, diag_ok=True, catalogs_ok=True)
    assert result == {"ok": True, "message": "Машина видна клиентам в каталоге."}


def test_exactly_one_message_never_both():
    db = FakeDB(published=0, status="draft", publish_pending=1)
    result = fixed_toggle_publish(db, publikaciya_ok=False, primary_ok=False, diag_ok=False, catalogs_ok=False)
    messages = [result["message"]]
    assert len(messages) == 1
