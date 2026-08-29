import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from installer import AtomicInstaller, install_bundle  # noqa: E402


def test_atomic_install_success(tmp_path):
    backup_dir = tmp_path / "backups"
    installer = AtomicInstaller(backup_dir)
    target = tmp_path / "katalog.html"
    target.write_text("<html>old</html>", encoding="utf-8")

    new_content = b"<html>new-one-card-added</html>"
    result = install_bundle(installer, {str(target): new_content})
    assert result["ok"] is True
    assert target.read_bytes() == new_content


def test_atomic_install_rollback_on_readback_mismatch(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    installer = AtomicInstaller(backup_dir)
    target = tmp_path / "katalog.html"
    original = b"<html>old</html>"
    target.write_bytes(original)

    def fake_verify_readback(self, path, expected_sha256):
        return False  # force mismatch

    monkeypatch.setattr(AtomicInstaller, "verify_readback", fake_verify_readback)

    result = install_bundle(installer, {str(target): b"<html>new</html>"})
    assert result["ok"] is False
    assert target.read_bytes() == original  # rolled back exactly


def test_rollback_removes_file_with_no_prior_backup(tmp_path):
    backup_dir = tmp_path / "backups"
    installer = AtomicInstaller(backup_dir)
    target = tmp_path / "UA-0013-diag.html"

    installer.backup(target)
    installer.atomic_write(target, b"placeholder")
    assert target.exists()
    installer.rollback(target)
    assert not target.exists()
