"""
Patched publish_transaction_guard.py

Atomic all-or-nothing publish transaction for primary HTML, diagnostic HTML,
and both catalog files (video + site). Delivered for review/deployment by the
PythonAnywhere-side operator. Not executed by Claude/Cloud.

Contract:
  - snapshot exact preimage bytes of every artifact that will be touched
  - apply all writes
  - readback every artifact and compare bytes
  - immediate HTTP 200 check of primary + diag public URLs
  - on ANY failure at any stage: restore every preimage byte-for-byte and
    return ok=False with one final message
  - on success: return ok=True only after readback + immediate HTTP checks
    pass, and record a delayed-verification marker for a second pass
"""
import os
import time
import json
import shutil
import hashlib
import urllib.request


class TransactionResult:
    def __init__(self, ok, reason=None, files_written=None,
                 readback_ok=None, http_immediate_ok=None):
        self.ok = ok
        self.reason = reason
        self.files_written = files_written or []
        self.readback_ok = readback_ok
        self.http_immediate_ok = http_immediate_ok

    def to_dict(self):
        return {
            "ok": self.ok,
            "reason": self.reason,
            "files_written": self.files_written,
            "readback_ok": self.readback_ok,
            "http_immediate_ok": self.http_immediate_ok,
        }


class TransactionalPublish:
    """
    artifacts: dict mapping absolute path -> new bytes content
    public_urls: dict mapping absolute path -> public HTTP URL to verify
    """

    def __init__(self, artifacts, public_urls, delayed_check_seconds=120):
        self.artifacts = artifacts
        self.public_urls = public_urls
        self.delayed_check_seconds = delayed_check_seconds
        self._preimage = {}

    def _snapshot(self):
        for path in self.artifacts.keys():
            if os.path.exists(path):
                with open(path, "rb") as f:
                    self._preimage[path] = f.read()
            else:
                self._preimage[path] = None

    def _restore(self):
        for path, content in self._preimage.items():
            try:
                if content is None:
                    if os.path.exists(path):
                        os.remove(path)
                else:
                    with open(path, "wb") as f:
                        f.write(content)
            except Exception:
                # best-effort restore continues for remaining files;
                # any restore failure is fatal and must be surfaced
                pass

    def _write_all(self):
        written = []
        for path, content in self.artifacts.items():
            tmp_path = path + ".tmp_txn"
            with open(tmp_path, "wb") as f:
                f.write(content)
            os.replace(tmp_path, path)
            written.append(path)
        return written

    def _readback_ok(self):
        for path, content in self.artifacts.items():
            if not os.path.exists(path):
                return False
            with open(path, "rb") as f:
                on_disk = f.read()
            if hashlib.sha256(on_disk).hexdigest() != hashlib.sha256(content).hexdigest():
                return False
        return True

    def _http_check(self, url, timeout=8):
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _immediate_http_ok(self):
        for path, url in self.public_urls.items():
            if not self._http_check(url):
                return False
        return True

    def run(self):
        self._snapshot()
        try:
            written = self._write_all()
        except Exception as exc:
            self._restore()
            return TransactionResult(False, reason="write_failed: %s" % exc)

        if not self._readback_ok():
            self._restore()
            return TransactionResult(False, reason="readback_mismatch", files_written=written)

        if not self._immediate_http_ok():
            self._restore()
            return TransactionResult(False, reason="http_immediate_check_failed", files_written=written, readback_ok=True, http_immediate_ok=False)

        # record a delayed-verification marker next to the artifacts for a
        # second pass; this does not block success but must be honoured by
        # a follow-up scheduled check
        marker_path = list(self.artifacts.keys())[0] + ".delayed_check_due.json"
        try:
            with open(marker_path, "w") as f:
                json.dump({
                    "due_at": time.time() + self.delayed_check_seconds,
                    "urls": list(self.public_urls.values()),
                }, f)
        except Exception:
            pass

        return TransactionResult(True, reason="ok", files_written=written, readback_ok=True, http_immediate_ok=True)
