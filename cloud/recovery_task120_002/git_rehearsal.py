"""Real Git plumbing proof in a newly created, local-only fixture repository.

This module is deliberately not a production runner. Its approval documents say
LOCAL_REHEARSAL_ONLY and are not evidence of owner authorization. It has no API
to open an existing repository, add a remote, fetch, push, or change production.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Mapping


CONTRACT = "UA-ART-RECOVERY-TASK120-002"
REPOSITORY = "art20021986-wq/ua-art-autopilot"
TASK_ID = "TASK120-PUBLISH-UA-0017-UA-0018"
RUN_ID = "34134692609"
MODE_EPOCH = "auto-20260904T174904Z-global-guard-04"
REQUEST_PATH = "tasks/requests/TASK120-PUBLISH-UA-0017-UA-0018.json"
REQUEST_SHA256 = "a4662a876b037595742a31e34394b27d3e40bcbb75e2915df1ecdc0cb01b4442"
HALT = "state/AUTOPILOT_HALT.json"
ARCHIVE = f"state/halt_history/{CONTRACT}/halt.json"
RECEIPT = f"state/halt_history/{CONTRACT}/receipt.json"
REF = "refs/heads/rehearsal"
AUTHORIZATION_KIND = "LOCAL_REHEARSAL_ONLY"
RECEIPT_SCHEMA = "UA-ART-LOCAL-RECOVERY-RECEIPT-1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_OID = re.compile(r"[0-9a-f]{40}\Z")


class RehearsalError(RuntimeError):
    """A bounded proof failed; no live recovery is attempted."""


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan_sha256(plan: Mapping) -> str:
    return sha256(canonical_bytes({key: value for key, value in plan.items()
                                   if key != "plan_sha256"}))


def _valid_path(value: str) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and path.as_posix() == value
            and all(part not in ("", ".", "..", ".git") for part in path.parts)
            and all(ord(char) >= 32 and ord(char) != 127 for char in value))


def _snapshot_hash(files: Mapping[str, bytes]) -> str:
    return sha256(canonical_bytes({path: sha256(data)
                                   for path, data in sorted(files.items())}))


@dataclass(frozen=True)
class PreparedTransition:
    parent_commit: str
    candidate_commit: str
    candidate_tree: str
    plan_sha256: str
    approval_sha256: str
    receipt_bytes: bytes


class GitRehearsal:
    """Owned fixture only. Construct using create(), never an existing repo."""

    def __init__(self, *args, **kwargs):
        raise RehearsalError("USE_CREATE_WITH_NEW_OUTPUT_ONLY")

    @classmethod
    def create(cls, initial_files: dict[str, bytes], output: Path) -> "GitRehearsal":
        if not isinstance(initial_files, dict) or not initial_files:
            raise RehearsalError("INITIAL_FILES_REQUIRED")
        if any(not _valid_path(path) or not isinstance(data, bytes)
               for path, data in initial_files.items()):
            raise RehearsalError("INVALID_INITIAL_FILE")
        paths = sorted(initial_files)
        if any(str(parent) in initial_files
               for path in paths for parent in PurePosixPath(path).parents
               if str(parent) != "."):
            raise RehearsalError("INITIAL_FILE_DIRECTORY_COLLISION")
        output = Path(output).absolute()
        if output.name in ("", ".", ".."):
            raise RehearsalError("NEW_OUTPUT_REQUIRED")
        # Refuse pre-existing output and symlink ancestry. Never run git in cwd.
        for ancestor in reversed(output.parent.parents):
            if stat.S_ISLNK(ancestor.lstat().st_mode):
                raise RehearsalError("SYMLINK_OUTPUT_ANCESTRY")
        if not stat.S_ISDIR(output.parent.lstat().st_mode):
            raise RehearsalError("OUTPUT_PARENT_NOT_DIRECTORY")
        try:
            output.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise RehearsalError("OUTPUT_ALREADY_EXISTS") from exc
        self = object.__new__(cls)
        self.output = output
        self.repo = output / "fixture.git"
        self._initial_files = dict(initial_files)
        self._prepared = {}
        self._output_identity = (output.stat().st_dev, output.stat().st_ino)
        self._repo_identity = None
        self._config_identity = None
        self._config_bytes = None
        self._initializing_allowed = True
        self._directory_identities = {}
        for name in ("home", "empty-hooks", "empty-template", "indexes"):
            (output / name).mkdir(mode=0o700)
            directory_stat = (output / name).lstat()
            self._directory_identities[name] = (directory_stat.st_dev, directory_stat.st_ino)
        self._env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(output / "home"),
            "XDG_CONFIG_HOME": str(output / "home"),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_ATTR_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C",
            "GIT_AUTHOR_NAME": "Local recovery rehearsal",
            "GIT_AUTHOR_EMAIL": "rehearsal@invalid",
            "GIT_COMMITTER_NAME": "Local recovery rehearsal",
            "GIT_COMMITTER_EMAIL": "rehearsal@invalid",
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
        }
        self._git("init", "--bare", "--object-format=sha1",
                  "--initial-branch=rehearsal",
                  "--template=" + str(output / "empty-template"), str(self.repo),
                  initializing=True)
        repo_stat = self.repo.lstat()
        self._repo_identity = (repo_stat.st_dev, repo_stat.st_ino)
        config_stat = (self.repo / "config").lstat()
        self._config_identity = (config_stat.st_dev, config_stat.st_ino)
        self._config_bytes = (self.repo / "config").read_bytes()
        tree = self._tree(None, self._initial_files)
        self.initial_commit = self._commit_tree(tree, None, b"Local initial fixture\n")
        self._git("update-ref", REF, self.initial_commit, "0" * 40)
        self._assert_local()
        return self

    def _assert_safe_paths(self, *, initializing: bool = False,
                           index: Path | None = None) -> None:
        """Check destinations without Git recursion or following symlinks.

        The fixture is private (0700), created by us, and never accepts another
        repository. These checks also refuse later local path redirection.
        """
        for ancestor in reversed(self.output.parents):
            if not stat.S_ISDIR(ancestor.lstat().st_mode):
                raise RehearsalError("OWNED_OUTPUT_ANCESTRY_CHANGED")
        st = self.output.lstat()
        if (not stat.S_ISDIR(st.st_mode)
                or (st.st_dev, st.st_ino) != self._output_identity):
            raise RehearsalError("OWNED_OUTPUT_CHANGED")
        for name, identity in self._directory_identities.items():
            directory_stat = (self.output / name).lstat()
            if (not stat.S_ISDIR(directory_stat.st_mode)
                    or (directory_stat.st_dev, directory_stat.st_ino) != identity):
                raise RehearsalError("OWNED_DIRECTORY_CHANGED")
        if initializing:
            if not self._initializing_allowed or os.path.lexists(self.repo):
                raise RehearsalError("INIT_REQUIRES_NEW_OWNED_REPOSITORY")
        else:
            repo_stat = self.repo.lstat()
            if (not stat.S_ISDIR(repo_stat.st_mode)
                    or (repo_stat.st_dev, repo_stat.st_ino) != self._repo_identity):
                raise RehearsalError("OWNED_REPOSITORY_CHANGED")
            for relative in ("commondir", "objects/info/alternates",
                             "objects/info/http-alternates"):
                if os.path.lexists(self.repo / relative):
                    raise RehearsalError("REPOSITORY_REDIRECTION_FORBIDDEN")
        # Inspect all descendants, including index/lock/ref/object paths. A
        # hardlinked regular file could otherwise modify an external pathname.
        for directory, dirs, files in os.walk(self.output, followlinks=False):
            for name in dirs + files:
                entry = (Path(directory) / name).lstat()
                if stat.S_ISLNK(entry.st_mode):
                    raise RehearsalError("OWNED_TREE_SYMLINK_FORBIDDEN")
                if stat.S_ISREG(entry.st_mode):
                    if entry.st_nlink != 1:
                        raise RehearsalError("OWNED_TREE_HARDLINK_FORBIDDEN")
                elif not stat.S_ISDIR(entry.st_mode):
                    raise RehearsalError("OWNED_TREE_SPECIAL_FILE_FORBIDDEN")
        if not initializing:
            config = self.repo / "config"
            config_stat = config.lstat()
            if ((config_stat.st_dev, config_stat.st_ino) != self._config_identity
                    or config.read_bytes() != self._config_bytes):
                raise RehearsalError("OWNED_REPOSITORY_CONFIG_CHANGED")
        if index is not None:
            path = Path(index)
            if (not path.is_absolute() or path.name != "index"
                    or path.parent.parent != self.output / "indexes"
                    or not stat.S_ISDIR(path.parent.lstat().st_mode)):
                raise RehearsalError("INDEX_OUTSIDE_OWNED_DIRECTORY")

    def _assert_local(self) -> None:
        self._assert_safe_paths()
        if self._git("remote").strip():
            raise RehearsalError("LOCAL_REHEARSAL_REMOTE_FORBIDDEN")
        if self._git("rev-parse", "--is-bare-repository").strip() != b"true":
            raise RehearsalError("BARE_REHEARSAL_REQUIRED")

    def _git(self, *args: str, data: bytes | None = None,
             index: Path | None = None, initializing: bool = False) -> bytes:
        mutations = {"init", "read-tree", "hash-object", "update-index", "write-tree",
                     "commit-tree", "update-ref"}
        reads = {"rev-parse", "ls-tree", "cat-file", "remote", "rev-list", "diff-tree"}
        if not args or args[0] not in mutations | reads:
            raise RehearsalError("GIT_COMMAND_NOT_ALLOWED_IN_REHEARSAL")
        if args[0] == "remote" and args != ("remote",):
            raise RehearsalError("LOCAL_REHEARSAL_REMOTE_FORBIDDEN")
        if initializing:
            exact_init = ("init", "--bare", "--object-format=sha1",
                          "--initial-branch=rehearsal",
                          "--template=" + str(self.output / "empty-template"), str(self.repo))
            if args != exact_init or index is not None:
                raise RehearsalError("INIT_REQUIRES_EXACT_LOCAL_ARGUMENTS")
            self._assert_safe_paths(initializing=True)
            try:
                return self._invoke_git(*args, data=data, initializing=True)
            finally:
                self._initializing_allowed = False
        if args[0] == "init":
            raise RehearsalError("INITIALIZATION_ALREADY_COMPLETED")
        self._assert_safe_paths(index=index)
        if args[0] in mutations:
            # Direct read-only invocation prevents recursion through _git.
            common_dir = self._invoke_git("rev-parse", "--path-format=absolute",
                                          "--git-common-dir").decode("utf-8").strip()
            if common_dir != str(self.repo):
                raise RehearsalError("GIT_COMMON_DIRECTORY_NOT_OWNED")
            self._assert_safe_paths(index=index)
        return self._invoke_git(*args, data=data, index=index)

    def _invoke_git(self, *args: str, data: bytes | None = None,
                    index: Path | None = None, initializing: bool = False) -> bytes:
        # Fixed executable and fresh environment prevent inherited credentials,
        # Git aliases, global/system configuration, index, hooks, and remotes.
        command = ["/usr/bin/git", "-c", "core.hooksPath=" + str(self.output / "empty-hooks"),
                   "-c", "core.fsmonitor=false", "-c", "protocol.allow=never",
                   "-c", "commit.gpgsign=false", "-c", "core.attributesFile=" + os.devnull]
        if not initializing:
            command += ["--git-dir=" + str(self.repo)]
        env = dict(self._env)
        if index is not None:
            env["GIT_INDEX_FILE"] = str(index)
        completed = subprocess.run(command + list(args), input=data, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, cwd=self.output, env=env,
                                   timeout=20, check=False)
        if completed.returncode:
            # Do not forward arbitrary Git output or supplied file bytes.
            raise RehearsalError("GIT_COMMAND_FAILED:" + args[0])
        return completed.stdout

    @property
    def current_commit(self) -> str:
        return self._git("rev-parse", "--verify", REF).decode("ascii").strip()

    def files(self, commit: str | None = None) -> dict[str, bytes]:
        oid = self.current_commit if commit is None else commit
        if not _OID.fullmatch(oid):
            raise RehearsalError("INVALID_COMMIT_OID")
        result = {}
        for entry in self._git("ls-tree", "-rz", "--full-tree", oid).split(b"\0"):
            if not entry:
                continue
            metadata, path = entry.split(b"\t", 1)
            mode, kind, blob = metadata.split(b" ")
            if mode != b"100644" or kind != b"blob":
                raise RehearsalError("UNEXPECTED_TREE_ENTRY")
            result[path.decode("utf-8")] = self._git("cat-file", "blob", blob.decode("ascii"))
        return result

    def _tree(self, parent: str | None, additions: Mapping[str, bytes],
              deletions: tuple[str, ...] = ()) -> str:
        self._assert_safe_paths()
        index_dir = Path(tempfile.mkdtemp(prefix="tree-", dir=self.output / "indexes"))
        index_dir_stat = index_dir.lstat()
        index_identity = (index_dir_stat.st_dev, index_dir_stat.st_ino)
        index = index_dir / "index"
        try:
            if parent is None:
                self._git("read-tree", "--empty", index=index)
            else:
                self._git("read-tree", parent, index=index)
            entries = []
            for path in deletions:
                entries.append(b"0 " + b"0" * 40 + b"\t" + path.encode("utf-8") + b"\0")
            for path, payload in sorted(additions.items()):
                blob = self._git("hash-object", "-w", "--stdin", data=payload).strip()
                entries.append(b"100644 " + blob + b"\t" + path.encode("utf-8") + b"\0")
            if entries:
                self._git("update-index", "-z", "--index-info", data=b"".join(entries), index=index)
            return self._git("write-tree", index=index).decode("ascii").strip()
        finally:
            self._assert_safe_paths(index=index)
            cleanup_stat = index_dir.lstat()
            if (cleanup_stat.st_dev, cleanup_stat.st_ino) != index_identity:
                raise RehearsalError("OWNED_INDEX_DIRECTORY_CHANGED")
            shutil.rmtree(index_dir)

    def _commit_tree(self, tree: str, parent: str | None, message: bytes) -> str:
        args = ("commit-tree", tree) + (("-p", parent) if parent else ())
        return self._git(*args, data=message).decode("ascii").strip()

    def _identity(self) -> dict:
        try:
            halt = json.loads(self._initial_files[HALT])
        except (KeyError, ValueError, TypeError) as exc:
            raise RehearsalError("VALID_HALT_REQUIRED") from exc
        expected = {"task_id": TASK_ID, "run_id": RUN_ID, "mode_epoch": MODE_EPOCH,
                    "request_path": REQUEST_PATH, "request_sha256": REQUEST_SHA256,
                    "status": "EMERGENCY_HALT"}
        if not isinstance(halt, dict) or any(halt.get(k) != v for k, v in expected.items()):
            raise RehearsalError("FOREIGN_HALT_IDENTITY")
        if ARCHIVE in self._initial_files or RECEIPT in self._initial_files:
            raise RehearsalError("ARCHIVE_OR_RECEIPT_ALREADY_EXISTS")
        return expected

    def make_plan(self, controller_sha256: str,
                  production_parent_sha: str | None = None) -> dict:
        self._identity()
        if not isinstance(controller_sha256, str) or not _SHA256.fullmatch(controller_sha256):
            raise RehearsalError("INVALID_CONTROLLER_SHA256")
        if production_parent_sha is not None and (not isinstance(production_parent_sha, str)
                                                  or not _OID.fullmatch(production_parent_sha)):
            raise RehearsalError("INVALID_PRODUCTION_PARENT_OID")
        halt_sha = sha256(self._initial_files[HALT])
        plan = {
            "schema_version": "UA-ART-LOCAL-GIT-REHEARSAL-1",
            "contract": CONTRACT, "repository": REPOSITORY,
            "authorization_kind": AUTHORIZATION_KIND,
            "production_parent_sha": production_parent_sha,
            "rehearsal_parent_sha": self.initial_commit,
            "task_id": TASK_ID, "run_id": RUN_ID, "mode_epoch": MODE_EPOCH,
            "request_path": REQUEST_PATH, "request_sha256": REQUEST_SHA256,
            "controller_sha256": controller_sha256,
            "halt_sha256": halt_sha, "initial_files_sha256": _snapshot_hash(self._initial_files),
            "changes": {
                HALT: {"action": "delete", "sha256": halt_sha},
                ARCHIVE: {"action": "add", "sha256": halt_sha},
                RECEIPT: {"action": "add", "schema_version": RECEIPT_SCHEMA},
            },
        }
        plan["plan_sha256"] = plan_sha256(plan)
        return plan

    @staticmethod
    def rehearsal_approval(plan: Mapping) -> dict:
        """Synthetic test input, never an owner-approval generator."""
        return {"authorization_kind": AUTHORIZATION_KIND,
                "contract": CONTRACT, "repository": REPOSITORY,
                "task_id": TASK_ID, "run_id": RUN_ID,
                "mode_epoch": MODE_EPOCH, "plan_sha256": plan["plan_sha256"],
                "controller_sha256": plan["controller_sha256"],
                "rehearsal_parent_sha": plan["rehearsal_parent_sha"],
                "production_parent_sha": plan["production_parent_sha"],
                "halt_sha256": plan["halt_sha256"]}

    def prepare(self, plan: dict, approval: dict | None,
                controller_sha256: str) -> PreparedTransition:
        self._assert_local()
        if not isinstance(plan, dict) or plan.get("plan_sha256") != plan_sha256(plan):
            raise RehearsalError("PLAN_SHA256_MISMATCH")
        expected = self.make_plan(controller_sha256, plan.get("production_parent_sha"))
        if plan != expected:
            raise RehearsalError("PLAN_BINDING_MISMATCH")
        if not isinstance(approval, dict):
            raise RehearsalError("REHEARSAL_APPROVAL_REQUIRED")
        if approval != self.rehearsal_approval(expected):
            raise RehearsalError("REHEARSAL_APPROVAL_BINDING_MISMATCH")
        receipt = canonical_bytes({
            "schema_version": RECEIPT_SCHEMA, "contract": CONTRACT,
            "repository": REPOSITORY, "authorization_kind": AUTHORIZATION_KIND,
            "production_touched": False, "owner_authorization_proven": False,
            "status": "LOCAL_REHEARSAL_CONTROL_HALT_CLEARED",
            "task_id": TASK_ID, "run_id": RUN_ID, "mode_epoch": MODE_EPOCH,
            "request_sha256": REQUEST_SHA256,
            "parent_main_sha": plan["production_parent_sha"],
            "rehearsal_parent_sha": self.initial_commit,
            "halt_sha256": plan["halt_sha256"],
            "plan_sha256": plan["plan_sha256"],
            "controller_sha256": controller_sha256,
            "approval_sha256": sha256(canonical_bytes(approval)),
        })
        current = self.current_commit
        if current != self.initial_commit:
            self._verify_transition(current, receipt)
            tree = self._git("rev-parse", current + "^{tree}").decode("ascii").strip()
            prepared = PreparedTransition(self.initial_commit, current, tree, plan["plan_sha256"],
                                          sha256(canonical_bytes(approval)), receipt)
            self._prepared[prepared.candidate_commit] = prepared
            return prepared
        if self.files(self.initial_commit) != self._initial_files:
            raise RehearsalError("INITIAL_SNAPSHOT_MISMATCH")
        tree = self._tree(self.initial_commit,
                          {ARCHIVE: self._initial_files[HALT], RECEIPT: receipt}, (HALT,))
        commit = self._commit_tree(tree, self.initial_commit, b"Local atomic recovery rehearsal\n")
        self._verify_transition(commit, receipt)
        prepared = PreparedTransition(self.initial_commit, commit, tree, plan["plan_sha256"],
                                      sha256(canonical_bytes(approval)), receipt)
        self._prepared[prepared.candidate_commit] = prepared
        return prepared

    def _verify_transition(self, commit: str, receipt: bytes) -> None:
        parent_line = self._git("rev-list", "--parents", "-n", "1", commit).decode("ascii").split()
        if parent_line != [commit, self.initial_commit]:
            raise RehearsalError("REF_DRIFT_OR_WRONG_PARENT")
        files = self.files(commit)
        expected = dict(self._initial_files)
        expected.pop(HALT, None)
        expected[ARCHIVE] = self._initial_files[HALT]
        expected[RECEIPT] = receipt
        if files != expected:
            raise RehearsalError("REF_DRIFT_OR_TRANSITION_CONTENT_MISMATCH")
        changes = self._git("diff-tree", "--no-commit-id", "--name-status", "-r", "-z",
                            "--no-renames", self.initial_commit, commit).split(b"\0")
        actual = {changes[i + 1].decode("utf-8"): changes[i].decode("ascii")
                  for i in range(0, len(changes) - 1, 2)}
        if actual != {HALT: "D", ARCHIVE: "A", RECEIPT: "A"}:
            raise RehearsalError("EXACT_THREE_PATH_TRANSITION_REQUIRED")

    def commit(self, prepared: PreparedTransition, *, fault: str | None = None) -> dict:
        """One ref CAS; named faults exist only to prove fixture crash behavior."""
        self._assert_local()
        if fault not in (None, "before_cas", "after_cas"):
            raise RehearsalError("UNKNOWN_REHEARSAL_FAULT")
        if (not isinstance(prepared, PreparedTransition)
                or self._prepared.get(prepared.candidate_commit) != prepared):
            raise RehearsalError("TRANSITION_NOT_PREPARED_WITH_APPROVAL")
        if prepared.parent_commit != self.initial_commit:
            raise RehearsalError("PREPARED_PARENT_MISMATCH")
        self._verify_transition(prepared.candidate_commit, prepared.receipt_bytes)
        current = self.current_commit
        if current == prepared.candidate_commit:
            return self._result(prepared, "ALREADY_APPLIED", 0)
        if current != prepared.parent_commit:
            raise RehearsalError("REF_DRIFT")
        if fault == "before_cas":
            raise RehearsalError("INJECTED_CRASH_BEFORE_CAS")
        try:
            self._git("update-ref", REF, prepared.candidate_commit, prepared.parent_commit)
        except RehearsalError as exc:
            raise RehearsalError("REF_CAS_FAILED") from exc
        if fault == "after_cas":
            raise RehearsalError("INJECTED_ACK_LOSS_AFTER_CAS")
        if self.current_commit != prepared.candidate_commit:
            raise RehearsalError("POST_CAS_REF_DRIFT")
        self._verify_transition(self.current_commit, prepared.receipt_bytes)
        return self._result(prepared, "APPLIED_LOCAL_REHEARSAL", 1)

    def _result(self, prepared: PreparedTransition, status: str, writes: int) -> dict:
        return {"status": status, "production_touched": False,
                "authorization_kind": AUTHORIZATION_KIND,
                "parent_commit": prepared.parent_commit,
                "candidate_commit": prepared.candidate_commit,
                "candidate_tree": prepared.candidate_tree,
                "plan_sha256": prepared.plan_sha256,
                "receipt_sha256": sha256(prepared.receipt_bytes),
                "ref_writes_this_call": writes, "changed_paths": [HALT, ARCHIVE, RECEIPT],
                "exact_archive_bytes_verified": True, "other_files_unchanged": True,
                "remote_count": 0, "execution_ready": False,
                "live_blocker": "NOT_READY_RUNNER_NOT_REGISTERED"}


def rehearse(initial_files: dict[str, bytes], approved_plan: dict, approval: dict,
             output: Path, controller_sha256: str) -> dict:
    """Convenience entrypoint; initial commit is deterministic for the same files."""
    repository = GitRehearsal.create(initial_files, output)
    prepared = repository.prepare(approved_plan, approval, controller_sha256)
    return repository.commit(prepared)
