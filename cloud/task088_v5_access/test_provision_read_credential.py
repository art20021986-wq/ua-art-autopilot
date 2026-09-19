import contextlib
import importlib.util
import io
import os
from pathlib import Path
import pty
import select
import stat
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest import mock
import warnings


SOURCE = Path(__file__).with_name("provision_read_credential.py")
SPEC = importlib.util.spec_from_file_location("credential_receiver", SOURCE)
receiver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(receiver)
TOKEN = "github_pat_" + "TEST_ONLY_NOT_A_REAL_CREDENTIAL_" * 2


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.home = Path(self.scratch.name) / "home"
        self.home.mkdir(mode=0o700)

    def parent(self):
        descriptor = receiver.open_token_directory(self.home)
        self.addCleanup(os.close, descriptor)
        return descriptor

    def target(self):
        return self.home / ".config" / "uaart-price-control" / receiver.TOKEN_NAME

    def test_exact_bytes_private_permissions_and_read_back(self):
        descriptor = self.parent()
        receiver.store_token(descriptor, TOKEN)
        self.assertEqual(self.target().read_bytes(), (TOKEN + "\n").encode())
        self.assertEqual(stat.S_IMODE(self.target().stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.target().parent.stat().st_mode), 0o700)

    def test_existing_token_is_never_overwritten(self):
        descriptor = self.parent()
        self.target().write_text("previous")
        with self.assertRaisesRegex(receiver.ProvisionError, "^E_ALREADY_EXISTS$"):
            receiver.store_token(descriptor, TOKEN)
        self.assertEqual(self.target().read_text(), "previous")

    def test_target_symlink_is_rejected_without_touching_destination(self):
        descriptor = self.parent()
        outside = self.home / "outside"
        outside.write_text("protected")
        self.target().symlink_to(outside)
        with self.assertRaisesRegex(receiver.ProvisionError, "^E_ALREADY_EXISTS$"):
            receiver.store_token(descriptor, TOKEN)
        self.assertEqual(outside.read_text(), "protected")

    def test_each_directory_symlink_is_rejected(self):
        outside = Path(self.scratch.name) / "outside"
        outside.mkdir(mode=0o700)
        for relative in (".config", ".config/uaart-price-control"):
            with self.subTest(relative=relative):
                link = self.home / relative
                link.parent.mkdir(exist_ok=True, mode=0o700)
                link.symlink_to(outside, target_is_directory=True)
                with self.assertRaises(OSError):
                    receiver.open_token_directory(self.home)
                link.unlink()
        self.assertEqual(list(outside.iterdir()), [])
        linked_home = Path(self.scratch.name) / "linked-home"
        linked_home.symlink_to(self.home, target_is_directory=True)
        with self.assertRaises(OSError):
            receiver.open_token_directory(linked_home)

    def test_existing_shared_config_is_preserved_but_private_directory_is_strict(self):
        config = self.home / ".config"
        config.mkdir(mode=0o755)
        config.chmod(0o755)
        self.parent()
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o755)
        self.target().parent.chmod(0o750)
        with self.assertRaisesRegex(receiver.ProvisionError, "^E_DIRECTORY_PERMISSIONS$"):
            receiver.open_token_directory(self.home)
        self.assertEqual(stat.S_IMODE(self.target().parent.stat().st_mode), 0o750)

    def test_group_writable_home_and_config_fail_closed(self):
        self.home.chmod(0o770)
        with self.assertRaisesRegex(receiver.ProvisionError, "^E_HOME_PERMISSIONS$"):
            receiver.open_token_directory(self.home)
        self.home.chmod(0o700)
        config = self.home / ".config"
        config.mkdir(mode=0o700)
        config.chmod(0o777)
        with self.assertRaisesRegex(receiver.ProvisionError, "^E_DIRECTORY_PERMISSIONS$"):
            receiver.open_token_directory(self.home)

    def test_empty_multiline_whitespace_and_other_token_types_are_rejected(self):
        descriptor = self.parent()
        for token in ("", " ", TOKEN + "\n", " " + TOKEN, "ghp_" + "x" * 40,
                      "github_pat_short", "github_pat_" + "x" * 241, None):
            with self.subTest(token_kind=type(token).__name__):
                with self.assertRaisesRegex(receiver.ProvisionError, "^E_TOKEN_FORMAT$"):
                    receiver.store_token(descriptor, token)
                self.assertFalse(self.target().exists())

    def test_partial_write_is_completed(self):
        descriptor = self.parent()
        original_write = os.write
        with mock.patch.object(receiver.os, "write", side_effect=lambda fd, data: original_write(fd, data[:7])):
            receiver.store_token(descriptor, TOKEN)
        self.assertEqual(self.target().read_text(), TOKEN + "\n")

    def test_final_path_is_absent_until_complete_read_back(self):
        descriptor = self.parent()
        original_write = os.write
        def write_private(fd, data):
            self.assertFalse(self.target().exists())
            self.assertEqual(stat.S_IMODE(os.fstat(fd).st_mode), 0o600)
            return original_write(fd, data[:7])
        with mock.patch.object(receiver.os, "write", side_effect=write_private):
            receiver.store_token(descriptor, TOKEN)
        self.assertEqual([item.name for item in self.target().parent.iterdir()], [receiver.TOKEN_NAME])

    def test_interrupt_or_write_failure_removes_own_partial_file(self):
        descriptor = self.parent()
        for failure in (KeyboardInterrupt(), OSError("must not be printed")):
            with self.subTest(failure=type(failure).__name__):
                with mock.patch.object(receiver.os, "write", side_effect=failure):
                    with self.assertRaises(type(failure)):
                        receiver.store_token(descriptor, TOKEN)
                self.assertFalse(self.target().exists())
                self.assertEqual(list(self.target().parent.iterdir()), [])

    def test_read_back_failure_removes_partial_file(self):
        descriptor = self.parent()
        with mock.patch.object(receiver.os, "read", return_value=b"wrong"):
            with self.assertRaisesRegex(receiver.ProvisionError, "^E_READ_BACK$"):
                receiver.store_token(descriptor, TOKEN)
        self.assertFalse(self.target().exists())

    def test_creation_race_preserves_competing_file(self):
        descriptor = self.parent()
        with mock.patch.object(receiver, "require_absent", side_effect=lambda fd: self.target().write_text("competitor")):
            with self.assertRaisesRegex(receiver.ProvisionError, "^E_ALREADY_EXISTS$"):
                receiver.store_token(descriptor, TOKEN)
        self.assertEqual(self.target().read_text(), "competitor")

    def test_partial_cleanup_does_not_delete_replacement_inode(self):
        descriptor = self.parent()
        self.target().write_text("original")
        info = self.target().stat()
        replacement = self.target().with_name("replacement")
        replacement.write_text("replacement")
        replacement.replace(self.target())
        receiver._remove_owned_partial(descriptor, (info.st_dev, info.st_ino))
        self.assertEqual(self.target().read_text(), "replacement")

    def test_non_tty_never_attempts_getpass_or_creates_directories(self):
        with mock.patch.object(receiver.sys, "stdin", io.StringIO(TOKEN)), mock.patch.object(receiver.getpass, "getpass") as hidden:
            with self.assertRaisesRegex(receiver.ProvisionError, "^E_TTY_REQUIRED$"):
                receiver.read_hidden_token()
            with mock.patch.object(receiver.sys, "argv", ["receiver"]), mock.patch.object(receiver, "open_token_directory") as create, contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(receiver.main(), 1)
            self.assertEqual(error.getvalue(), "E_TTY_REQUIRED\n")
            create.assert_not_called()
            hidden.assert_not_called()

    def test_getpass_echo_fallback_warning_is_fatal(self):
        fake_terminal = mock.MagicMock()
        fake_terminal.__enter__.return_value = fake_terminal
        fake_terminal.isatty.return_value = True
        def fallback(**kwargs):
            warnings.warn("secret-containing warning must stay hidden", receiver.getpass.GetPassWarning)
            self.fail("echo fallback was allowed")
        with mock.patch.object(receiver.sys.stdin, "isatty", return_value=True), mock.patch.object(receiver.os, "open", return_value=99), mock.patch.object(receiver.os, "fdopen", return_value=fake_terminal), mock.patch.object(receiver.getpass, "getpass", side_effect=lambda *args, **kwargs: fallback(**kwargs)):
            with self.assertRaisesRegex(receiver.ProvisionError, "^E_HIDDEN_INPUT_UNAVAILABLE$"):
                receiver.read_hidden_token()

    def test_cli_never_prints_unexpected_exception_or_secret(self):
        with mock.patch.object(receiver.sys, "argv", ["receiver"]), mock.patch.object(receiver.sys.stdin, "isatty", return_value=True), mock.patch.object(receiver, "open_token_directory", side_effect=OSError(TOKEN)), contextlib.redirect_stderr(io.StringIO()) as error, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(receiver.main(), 1)
        self.assertEqual(error.getvalue(), "E_PROVISION\n")
        self.assertEqual(output.getvalue(), "")

    def test_cli_rejects_existing_file_before_prompt(self):
        self.parent()
        self.target().write_text("previous")
        with mock.patch.object(receiver.sys, "argv", ["receiver"]), mock.patch.object(receiver.sys.stdin, "isatty", return_value=True), mock.patch.object(receiver, "open_token_directory", side_effect=lambda: os.open(self.target().parent, receiver._flags())), mock.patch.object(receiver, "read_hidden_token") as prompt, contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(receiver.main(), 1)
        prompt.assert_not_called()
        self.assertEqual(error.getvalue(), "E_ALREADY_EXISTS\n")

    def test_aborted_input_has_fixed_error_and_no_token_file(self):
        for interruption in (KeyboardInterrupt(), EOFError()):
            with self.subTest(interruption=type(interruption).__name__):
                opener = receiver.open_token_directory
                with mock.patch.object(receiver.sys, "argv", ["receiver"]), mock.patch.object(receiver.sys.stdin, "isatty", return_value=True), mock.patch.object(receiver, "open_token_directory", side_effect=lambda: opener(self.home)), mock.patch.object(receiver, "read_hidden_token", side_effect=interruption), contextlib.redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(receiver.main(), 1)
                self.assertEqual(error.getvalue(), "E_INPUT_ABORTED\n")
                self.assertFalse(self.target().exists())

    def test_cli_rejects_token_argument_before_any_processing(self):
        with mock.patch.object(receiver.sys, "argv", ["receiver", TOKEN]), contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(receiver.main(), 1)
        self.assertEqual(error.getvalue(), "E_ARGUMENTS\n")

    def test_real_controlling_tty_hides_token_and_restores_echo(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        child_code = (
            "import os,fcntl,termios,importlib.util; os.setsid(); "
            "fcntl.ioctl(0,termios.TIOCSCTTY,0); "
            f"s=importlib.util.spec_from_file_location('r',{str(SOURCE)!r}); "
            "r=importlib.util.module_from_spec(s); s.loader.exec_module(r); "
            "r.read_hidden_token(); print('HIDDEN_INPUT_ACCEPTED')"
        )
        child = subprocess.Popen([sys.executable, "-I", "-B", "-c", child_code],
                                 stdin=slave, stdout=slave, stderr=slave)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        output = b""
        deadline = time.monotonic() + 10
        while b"(hidden): " not in output and time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                output += os.read(master, 4096)
        self.assertIn(b"(hidden): ", output)
        self.assertFalse(termios.tcgetattr(slave)[3] & termios.ECHO)
        os.write(master, (TOKEN + "\n").encode())
        while b"HIDDEN_INPUT_ACCEPTED" not in output and time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                output += os.read(master, 4096)
        self.assertEqual(child.wait(timeout=2), 0)
        self.assertIn(b"HIDDEN_INPUT_ACCEPTED", output)
        self.assertNotIn(TOKEN.encode(), output)
        self.assertTrue(termios.tcgetattr(slave)[3] & termios.ECHO)


if __name__ == "__main__":
    unittest.main()
