from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from cloud.recovery_task120_002.git_rehearsal import (
    ARCHIVE, AUTHORIZATION_KIND, CONTRACT, HALT, MODE_EPOCH, RECEIPT,
    REF, REQUEST_PATH, REQUEST_SHA256, RUN_ID, TASK_ID,
    GitRehearsal, RehearsalError, canonical_bytes, plan_sha256, rehearse,
)


CODE_SHA = "a" * 64
MAIN_SHA = "b" * 40


def fixture_files():
    halt = {
        "status": "EMERGENCY_HALT", "task_id": TASK_ID, "run_id": RUN_ID,
        "mode_epoch": MODE_EPOCH, "request_path": REQUEST_PATH,
        "request_sha256": REQUEST_SHA256,
        "reason": "failed; rollback reserved false; rollback performed false",
        "halted_at": "2026-09-07T14:48:16Z",
    }
    return {HALT: (json.dumps(halt, indent=3) + "\n\n").encode(),
            "state/EXECUTION_MODE.json": b'{"mode":"AUTOMATIC"}\n',
            "tasks/launch/AUTO-OLDER.json": b'{"do_not_replay": true}\n',
            "site/car.html": b"<html>original shell</html>\x00\n",
            "media/photo.bin": bytes(range(256)),
            "unchanged.txt": b"outside transition\n"}


class GitRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.initial = fixture_files()

    def tearDown(self):
        self.temp.cleanup()

    def repo(self, initial=None, name="fixture"):
        return GitRehearsal.create(self.initial if initial is None else initial,
                                   self.root / name)

    def prepared(self, repo):
        plan = repo.make_plan(CODE_SHA, MAIN_SHA)
        approval = repo.rehearsal_approval(plan)
        return plan, approval, repo.prepare(plan, approval, CODE_SHA)

    def assert_original(self, repo):
        self.assertEqual(repo.current_commit, repo.initial_commit)
        self.assertEqual(repo.files(), self.initial)

    def test_actual_git_atomic_three_path_transition_and_binary_preservation(self):
        repo = self.repo()
        plan, approval, prepared = self.prepared(repo)
        self.assert_original(repo)  # Preparation writes only unreachable objects.
        result = repo.commit(prepared)
        self.assertEqual(result["status"], "APPLIED_LOCAL_REHEARSAL")
        self.assertEqual(result["ref_writes_this_call"], 1)
        self.assertFalse(result["production_touched"])
        self.assertFalse(result["execution_ready"])
        after = repo.files()
        self.assertNotIn(HALT, after)
        self.assertEqual(after[ARCHIVE], self.initial[HALT])
        self.assertEqual(after[RECEIPT], prepared.receipt_bytes)
        self.assertEqual({p: b for p, b in after.items() if p not in (ARCHIVE, RECEIPT)},
                         {p: b for p, b in self.initial.items() if p != HALT})
        self.assertEqual(repo._git("rev-list", "--count", REF).strip(), b"2")
        self.assertEqual(repo._git("remote").strip(), b"")
        self.assertEqual(repo._git("rev-parse", "--is-bare-repository").strip(), b"true")
        self.assertFalse((repo.output / "state").exists())
        receipt = json.loads(after[RECEIPT])
        self.assertEqual(receipt["parent_main_sha"], MAIN_SHA)
        self.assertFalse(receipt["owner_authorization_proven"])
        self.assertEqual(receipt["authorization_kind"], AUTHORIZATION_KIND)
        self.assertNotIn("commit_sha", receipt)

    def test_missing_approval_keeps_original_halt(self):
        repo = self.repo()
        plan = repo.make_plan(CODE_SHA)
        with self.assertRaisesRegex(RehearsalError, "APPROVAL_REQUIRED"):
            repo.prepare(plan, None, CODE_SHA)
        self.assert_original(repo)

    def test_bad_plan_hash_rejected(self):
        repo = self.repo()
        plan = repo.make_plan(CODE_SHA)
        approval = repo.rehearsal_approval(plan)
        plan["halt_sha256"] = "c" * 64
        with self.assertRaisesRegex(RehearsalError, "PLAN_SHA256_MISMATCH"):
            repo.prepare(plan, approval, CODE_SHA)
        self.assert_original(repo)

    def test_changed_controller_sha_rejected(self):
        repo = self.repo()
        plan = repo.make_plan(CODE_SHA)
        with self.assertRaisesRegex(RehearsalError, "PLAN_BINDING_MISMATCH"):
            repo.prepare(plan, repo.rehearsal_approval(plan), "d" * 64)
        self.assert_original(repo)

    def test_foreign_identity_rejected_even_with_matching_plan_hash(self):
        for field in ("repository", "contract", "task_id", "run_id", "mode_epoch",
                      "request_sha256", "halt_sha256", "rehearsal_parent_sha"):
            with self.subTest(field=field):
                repo = self.repo(name=field)
                plan = repo.make_plan(CODE_SHA)
                plan[field] = "foreign"
                plan["plan_sha256"] = plan_sha256(plan)
                with self.assertRaisesRegex(RehearsalError, "PLAN_BINDING_MISMATCH"):
                    repo.prepare(plan, repo.rehearsal_approval(plan), CODE_SHA)
                self.assert_original(repo)

    def test_foreign_halt_task_or_epoch_rejected(self):
        for field in ("task_id", "run_id", "mode_epoch", "request_sha256", "status"):
            with self.subTest(field=field):
                initial = dict(self.initial)
                halt = json.loads(initial[HALT])
                halt[field] = "foreign"
                initial[HALT] = canonical_bytes(halt)
                repo = self.repo(initial, name=field)
                with self.assertRaisesRegex(RehearsalError, "FOREIGN_HALT_IDENTITY"):
                    repo.make_plan(CODE_SHA)
                self.assertEqual(repo.files(), initial)

    def test_mismatched_or_live_approval_rejected(self):
        repo = self.repo()
        plan = repo.make_plan(CODE_SHA)
        for field in ("plan_sha256", "controller_sha256", "rehearsal_parent_sha",
                      "halt_sha256", "authorization_kind", "contract"):
            with self.subTest(field=field):
                approval = repo.rehearsal_approval(plan)
                approval[field] = "OWNER_APPROVED_LIVE"
                with self.assertRaisesRegex(RehearsalError, "APPROVAL_BINDING_MISMATCH"):
                    repo.prepare(plan, approval, CODE_SHA)
        self.assert_original(repo)

    def test_conflicting_archive_and_receipt_refuse_overwrite(self):
        for path in (ARCHIVE, RECEIPT):
            with self.subTest(path=path):
                initial = dict(self.initial)
                initial[path] = b"existing immutable history"
                repo = self.repo(initial, name=Path(path).name)
                with self.assertRaisesRegex(RehearsalError, "ALREADY_EXISTS"):
                    repo.make_plan(CODE_SHA)
                self.assertEqual(repo.files(), initial)

    def test_same_bytes_existing_archive_is_still_exclusive(self):
        initial = dict(self.initial)
        initial[ARCHIVE] = initial[HALT]
        repo = self.repo(initial)
        with self.assertRaisesRegex(RehearsalError, "ALREADY_EXISTS"):
            repo.make_plan(CODE_SHA)
        self.assertEqual(repo.files(), initial)

    def test_only_new_output_accepted_without_touching_existing_content(self):
        output = self.root / "existing"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_bytes(b"do not overwrite")
        with self.assertRaisesRegex(RehearsalError, "OUTPUT_ALREADY_EXISTS"):
            GitRehearsal.create(self.initial, output)
        self.assertEqual(marker.read_bytes(), b"do not overwrite")
        self.assertEqual(list(output.iterdir()), [marker])

    def test_symlink_output_or_parent_refused(self):
        target = self.root / "target"
        target.mkdir()
        link = self.root / "link"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(RehearsalError):
            GitRehearsal.create(self.initial, link)
        with self.assertRaisesRegex(RehearsalError, "OUTPUT_PARENT_NOT_DIRECTORY"):
            GitRehearsal.create(self.initial, link / "child")
        self.assertEqual(list(target.iterdir()), [])

    def test_invalid_paths_and_file_directory_collisions_rejected_before_output(self):
        for path in ("../escape", "/absolute", ".git/config", "a/../x", "a//b", "a\nb"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(RehearsalError, "INVALID_INITIAL_FILE"):
                    self.repo({path: b"bad"})
                self.assertFalse((self.root / "fixture").exists())
        with self.assertRaisesRegex(RehearsalError, "DIRECTORY_COLLISION"):
            self.repo({"a": b"file", "a-b": b"between", "a/c": b"nested"})

    def test_crash_before_cas_keeps_halt_and_retry_applies_once(self):
        repo = self.repo()
        _, _, prepared = self.prepared(repo)
        with self.assertRaisesRegex(RehearsalError, "CRASH_BEFORE_CAS"):
            repo.commit(prepared, fault="before_cas")
        self.assert_original(repo)
        self.assertEqual(repo.commit(prepared)["ref_writes_this_call"], 1)
        self.assertEqual(repo.commit(prepared)["ref_writes_this_call"], 0)

    def test_ack_loss_retry_is_read_only_no_second_commit(self):
        repo = self.repo()
        plan, approval, prepared = self.prepared(repo)
        with self.assertRaisesRegex(RehearsalError, "ACK_LOSS_AFTER_CAS"):
            repo.commit(prepared, fault="after_cas")
        with mock.patch.object(repo, "_git", wraps=repo._git) as calls:
            prepared_retry = repo.prepare(plan, approval, CODE_SHA)
            result = repo.commit(prepared_retry)
        self.assertEqual(result["status"], "ALREADY_APPLIED")
        self.assertEqual(result["ref_writes_this_call"], 0)
        forbidden = {"hash-object", "write-tree", "read-tree", "update-index", "commit-tree", "update-ref"}
        self.assertFalse(forbidden.intersection(call.args[0] for call in calls.call_args_list))
        self.assertEqual(repo._git("rev-list", "--count", REF).strip(), b"2")

    def test_concurrent_ref_drift_refused_without_rebase(self):
        repo = self.repo()
        _, _, prepared = self.prepared(repo)
        tree = repo._tree(repo.initial_commit, {"unchanged.txt": b"concurrent writer"})
        concurrent = repo._commit_tree(tree, repo.initial_commit, b"Other local writer\n")
        repo._git("update-ref", REF, concurrent, repo.initial_commit)
        with self.assertRaisesRegex(RehearsalError, "REF_DRIFT"):
            repo.commit(prepared)
        self.assertEqual(repo.current_commit, concurrent)
        self.assertEqual(repo.files()[HALT], self.initial[HALT])
        self.assertNotIn(ARCHIVE, repo.files())
        self.assertEqual(repo.files()["unchanged.txt"], b"concurrent writer")

    def test_actual_cas_rejects_race_after_precheck(self):
        repo = self.repo()
        _, _, prepared = self.prepared(repo)
        tree = repo._tree(repo.initial_commit, {"other.txt": b"parallel"})
        concurrent = repo._commit_tree(tree, repo.initial_commit, b"Racing writer\n")
        original_git = repo._git
        raced = False

        def race(*args, **kwargs):
            nonlocal raced
            if args[0] == "update-ref" and not raced:
                raced = True
                original_git("update-ref", REF, concurrent, repo.initial_commit)
            return original_git(*args, **kwargs)

        with mock.patch.object(repo, "_git", side_effect=race):
            with self.assertRaisesRegex(RehearsalError, "REF_CAS_FAILED"):
                repo.commit(prepared)
        self.assertTrue(raced)
        self.assertEqual(repo.current_commit, concurrent)
        self.assertIn(HALT, repo.files())
        self.assertNotIn(ARCHIVE, repo.files())

    def test_unrelated_forged_transition_cannot_skip_prepare_approval(self):
        repo = self.repo()
        _, _, prepared = self.prepared(repo)
        forged = replace(prepared, plan_sha256="f" * 64)
        with self.assertRaisesRegex(RehearsalError, "NOT_PREPARED_WITH_APPROVAL"):
            repo.commit(forged)
        self.assert_original(repo)

    def test_extra_planned_mutation_rejected_even_if_rehashed(self):
        repo = self.repo()
        plan = repo.make_plan(CODE_SHA)
        plan["changes"]["state/EXECUTION_MODE.json"] = {"action": "delete"}
        plan["plan_sha256"] = plan_sha256(plan)
        with self.assertRaisesRegex(RehearsalError, "PLAN_BINDING_MISMATCH"):
            repo.prepare(plan, repo.rehearsal_approval(plan), CODE_SHA)
        self.assert_original(repo)

    def test_foreign_env_configuration_and_hook_are_not_used(self):
        forbidden = self.root / "foreign.gitconfig"
        forbidden.write_text("[core]\n hooksPath = /never/use/foreign/hooks\n"
                             "[credential]\n helper = fail-this-should-not-run\n")
        with mock.patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": str(forbidden), "GIT_DIR": "/foreign/repository",
            "GIT_INDEX_FILE": "/foreign/index", "GIT_AUTHOR_NAME": "FOREIGN",
            "GIT_OBJECT_DIRECTORY": "/foreign/objects", "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": "/foreign/hooks",
        }):
            repo = self.repo()
            _, _, prepared = self.prepared(repo)
            repo.commit(prepared)
        raw_commit = repo._git("cat-file", "commit", repo.current_commit)
        self.assertIn(b"author Local recovery rehearsal <rehearsal@invalid>", raw_commit)
        self.assertNotIn(b"FOREIGN", raw_commit)
        self.assertEqual(repo._git("remote").strip(), b"")

    def test_deterministic_initial_oid_and_convenience_api(self):
        repo = self.repo(name="first")
        plan = repo.make_plan(CODE_SHA, MAIN_SHA)
        result = rehearse(self.initial, plan, repo.rehearsal_approval(plan),
                          self.root / "second", CODE_SHA)
        self.assertEqual(result["parent_commit"], repo.initial_commit)
        self.assertEqual(result["status"], "APPLIED_LOCAL_REHEARSAL")

    def test_constructor_cannot_open_any_existing_repository(self):
        with self.assertRaisesRegex(RehearsalError, "USE_CREATE_WITH_NEW_OUTPUT_ONLY"):
            GitRehearsal(self.root)

    @staticmethod
    def physical_files(root):
        return {str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*") if path.is_file()}

    def test_commondir_and_alternates_refused_before_any_git_mutation(self):
        foreign = self.repo(name="foreign")
        foreign_before = self.physical_files(foreign.output)
        mutations = [
            ("hash-object", "-w", "--stdin"),
            ("update-ref", REF, foreign.initial_commit, foreign.initial_commit),
            ("commit-tree", "0" * 40), ("write-tree",),
            ("read-tree", "--empty"), ("update-index", "--refresh"),
        ]
        for number, relative in enumerate(("commondir", "objects/info/alternates",
                                           "objects/info/http-alternates")):
            with self.subTest(relative=relative):
                repo = self.repo(name=f"redirect-{number}")
                (repo.repo / relative).write_text(str(foreign.repo) + "\n")
                for args in mutations:
                    with mock.patch.object(repo, "_invoke_git", wraps=repo._invoke_git) as invoke:
                        with self.assertRaisesRegex(RehearsalError, "REDIRECTION_FORBIDDEN"):
                            repo._git(*args, data=b"must never be written outside")
                    invoke.assert_not_called()
                self.assertEqual(self.physical_files(foreign.output), foreign_before)
                self.assertEqual((repo.repo / "refs/heads/rehearsal").read_text().strip(),
                                 repo.initial_commit)

    def test_objects_and_refs_symlinks_cannot_write_into_foreign_repo(self):
        foreign = self.repo(name="foreign")
        foreign_before = self.physical_files(foreign.output)
        for relative in ("objects", "refs", "refs/heads"):
            with self.subTest(relative=relative):
                repo = self.repo(name=relative.replace("/", "-"))
                _, _, prepared = self.prepared(repo)
                path = repo.repo / relative
                shutil.rmtree(path)
                path.symlink_to(foreign.repo / relative, target_is_directory=True)
                with self.assertRaisesRegex(RehearsalError, "SYMLINK_FORBIDDEN"):
                    repo._git("hash-object", "-w", "--stdin", data=b"foreign forbidden write")
                with self.assertRaisesRegex(RehearsalError, "SYMLINK_FORBIDDEN"):
                    repo.commit(prepared)
                self.assertEqual(self.physical_files(foreign.output), foreign_before)

    def test_repository_inode_replacement_refused(self):
        repo = self.repo()
        _, _, prepared = self.prepared(repo)
        foreign = self.repo(name="foreign")
        repo.repo.rename(repo.output / "original.git")
        shutil.copytree(foreign.repo, repo.repo)
        replaced_before = self.physical_files(repo.repo)
        with self.assertRaisesRegex(RehearsalError, "OWNED_REPOSITORY_CHANGED"):
            repo.commit(prepared)
        with self.assertRaisesRegex(RehearsalError, "OWNED_REPOSITORY_CHANGED"):
            repo._git("hash-object", "-w", "--stdin", data=b"blocked replacement")
        self.assertEqual(self.physical_files(repo.repo), replaced_before)

    def test_ref_hardlink_to_external_file_refused(self):
        repo = self.repo()
        external = self.root / "external-ref"
        external.write_text(repo.initial_commit + "\n")
        ref_file = repo.repo / "refs/heads/rehearsal"
        ref_file.unlink()
        os.link(external, ref_file)
        with self.assertRaisesRegex(RehearsalError, "HARDLINK_FORBIDDEN"):
            repo._git("update-ref", REF, "0" * 40, repo.initial_commit)
        self.assertEqual(external.read_text(), repo.initial_commit + "\n")

    def test_local_configuration_include_and_worktree_redirect_refused(self):
        repo = self.repo()
        before_ref = (repo.repo / "refs/heads/rehearsal").read_bytes()
        with (repo.repo / "config").open("a") as stream:
            stream.write("\n[include]\n path = /foreign/config\n"
                         "[core]\n worktree = /foreign/worktree\n")
        with self.assertRaisesRegex(RehearsalError, "CONFIG_CHANGED"):
            repo._git("hash-object", "-w", "--stdin", data=b"blocked config")
        self.assertEqual((repo.repo / "refs/heads/rehearsal").read_bytes(), before_ref)

    def test_common_dir_is_checked_as_absolute_path_before_mutation(self):
        repo = self.repo()
        with mock.patch.object(repo, "_invoke_git", wraps=repo._invoke_git) as invoke:
            repo._git("hash-object", "-w", "--stdin", data=b"owned object")
        self.assertEqual(invoke.call_args_list[0].args,
                         ("rev-parse", "--path-format=absolute", "--git-common-dir"))
        self.assertEqual(invoke.call_args_list[1].args,
                         ("hash-object", "-w", "--stdin"))
        original = repo._invoke_git

        def wrong_common_dir(*args, **kwargs):
            if args == ("rev-parse", "--path-format=absolute", "--git-common-dir"):
                return b"/foreign/common\n"
            return original(*args, **kwargs)

        with mock.patch.object(repo, "_invoke_git", side_effect=wrong_common_dir) as invoke:
            with self.assertRaisesRegex(RehearsalError, "COMMON_DIRECTORY_NOT_OWNED"):
                repo._git("hash-object", "-w", "--stdin", data=b"must be blocked")
        self.assertEqual(invoke.call_count, 1)

    def test_init_exception_cannot_reinitialize_or_open_existing_repo(self):
        repo = self.repo()
        before = self.physical_files(repo.output)
        with self.assertRaisesRegex(RehearsalError, "INIT_REQUIRES_NEW"):
            repo._git("init", "--bare", "--object-format=sha1",
                      "--initial-branch=rehearsal",
                      "--template=" + str(repo.output / "empty-template"),
                      str(repo.repo), initializing=True)
        with self.assertRaisesRegex(RehearsalError, "INITIALIZATION_ALREADY_COMPLETED"):
            repo._git("init", "--bare", str(repo.repo))
        with self.assertRaisesRegex(RehearsalError, "COMMAND_NOT_ALLOWED"):
            repo._git("push", "/foreign/repo", REF)
        with self.assertRaisesRegex(RehearsalError, "REMOTE_FORBIDDEN"):
            repo._git("remote", "add", "origin", "/foreign/repo")
        self.assertEqual(self.physical_files(repo.output), before)


if __name__ == "__main__":
    unittest.main()
