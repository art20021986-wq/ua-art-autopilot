# UA ART Autopilot Runner — Installation and Operation (PythonAnywhere)

Runner: `cloud/autopilot_runner.py` (stdlib only, Python 3.7+).
Target host: PythonAnywhere account `Carix`, working root `/home/Carix/autopilot`.

This runner does **not** change the UA ART production project by itself.
Out of the box `whitelist_roots` is empty, which makes SAFE_PATCH impossible
until the owner explicitly declares the writable areas (step 4).

---

## 1. Layout

```
/home/Carix/autopilot/
└── ua-art-autopilot/            # git clone of art20021986-wq/ua-art-autopilot
    ├── tasks/task_NNN.md        # written by ChatGPT
    ├── cloud/                   # written by Cloud (runner + patches)
    └── python/report_NNN.txt    # written by this runner, committed and pushed

/home/Carix/.autopilot/          # NEVER inside the repository
    ├── runner_config.json       # configuration
    ├── pa_api.json              # PythonAnywhere API token (CPU quota)
    ├── protected_inventory.json # UA-0001..UA-0008 baseline SHA256
    ├── crm_baseline.json        # crm.db journal_mode baseline
    ├── rounds.json              # round counter per task
    └── approvals/task_NNN.approval   # owner CRITICAL approvals

/home/Carix/autopilot_backups/   # NEVER inside the repository
    └── task_NNN/roundNN-<utc>/  # backup_manifest.json + files/
```

The runner refuses to start a backup if `backup_root` resolves inside the
git repository, so backups can never be pushed to GitHub.

## 2. Clone

Bash console on PythonAnywhere:

```bash
mkdir -p /home/Carix/autopilot
cd /home/Carix/autopilot
git clone https://github.com/art20021986-wq/ua-art-autopilot.git
cd ua-art-autopilot
git config user.name  "ua-art-autopilot-runner"
git config user.email "art20021986@ukr.net"
```

Use an SSH remote or a credential helper for pushing. **Never** put a token
into the repository, into `runner_config.json`, or into a task/report file.

## 3. Self test first

```bash
cd /home/Carix/autopilot/ua-art-autopilot
python3 cloud/autopilot_runner.py --self-test
```

Expected tail: `54 passed, 0 failed, 54 total`. The self test builds
throwaway trees under `/tmp` and never touches `/home/Carix/ua_art`.

## 4. Configure

```bash
mkdir -p /home/Carix/.autopilot/approvals
chmod 700 /home/Carix/.autopilot
nano /home/Carix/.autopilot/runner_config.json
```

```json
{
  "repo_root": "/home/Carix/autopilot/ua-art-autopilot",
  "production_root": "/home/Carix/ua_art",
  "backup_root": "/home/Carix/autopilot_backups",
  "whitelist_roots": [],
  "site_roots": [],
  "crm_db_path": "",
  "pa_username": "Carix",
  "git_sync": true,
  "git_push": true,
  "git_remote": "origin",
  "git_branch": "main",
  "max_rounds": 10
}
```

| Key | Meaning |
| --- | --- |
| `production_root` | Root of the real UA ART tree. Correct this to the real path. |
| `whitelist_roots` | Paths **relative to `production_root`** that SAFE_PATCH may write. Leave `[]` until the real card/template directories are confirmed. |
| `site_roots` | Reserved for site-integrity reporting. |
| `crm_db_path` | Absolute path to `crm.db`. Used **read-only** (`PRAGMA quick_check`, `journal_mode`). Leave `""` to skip. |
| `protected_globs` | Defaults to `**/UA-0001*` … `**/UA-0008*`. Override only if card filenames differ. |

Check what the runner actually resolved:

```bash
python3 cloud/autopilot_runner.py --print-config
```

## 5. CPU quota token (optional but recommended)

```bash
cat > /home/Carix/.autopilot/pa_api.json <<'EOF'
{"username": "Carix", "token": "<PythonAnywhere API token>"}
EOF
chmod 600 /home/Carix/.autopilot/pa_api.json
```

With the token the runner reads real quota usage and stops at
`DEFERRED_CPU_LIMIT` when usage is `>= 85%`. Without it, it falls back to the
local load average (defer at `>= 2.00` per CPU) and refuses heavy work when no
safeguard signal is available at all. The token is read from
`/home/Carix/.autopilot/pa_api.json` or the `PA_API_TOKEN` environment
variable — never from the repository, and it is never written to a report.

## 6. Record the protected baseline

Run once, after `production_root` is correct:

```bash
python3 cloud/autopilot_runner.py --init-inventory
```

This writes SHA256 for every UA-0001…UA-0008 file to
`/home/Carix/.autopilot/protected_inventory.json`. Every later run compares
against it before and after any patch. If a run finds the baseline missing it
bootstraps it and reports `UA_0001_0008_UNCHANGED: NOT_APPLICABLE` for that
round only.

## 7. Normal run

```bash
cd /home/Carix/autopilot/ua-art-autopilot
python3 cloud/autopilot_runner.py
```

Sequence: fetch + fast-forward → read newest `tasks/task_NNN.md` → inventory
`cloud/` → CPU guard → validate manifest → read-only integrity checks →
(patch modes only) whitelist → target SHA256 → backup → sandbox → tests →
apply or stop → write `python/report_NNN.txt` → commit and push that one file.

Useful flags:

| Flag | Effect |
| --- | --- |
| `--dry-run` | Every gate runs, production is never written. |
| `--no-push` | Write the report locally, do not push. |
| `--no-sync` | Skip fetch/fast-forward. |
| `--round N` | Force the round number instead of auto-increment. |
| `--keep-sandbox` | Leave the sandbox directory for inspection. |
| `--manifest PATH` | Use an explicit manifest instead of discovery. |

Recommended first live run: `--dry-run --no-push`.

## 8. Scheduled task

PythonAnywhere → Tasks → daily task, at a low-traffic hour:

```
cd /home/Carix/autopilot/ua-art-autopilot && python3 cloud/autopilot_runner.py >> /home/Carix/.autopilot/cron.log 2>&1
```

The log file lives outside the repository on purpose. The CPU guard makes a
scheduled run safe: above 85% quota it exits with `DEFERRED_CPU_LIMIT` before
any sandbox, SHA walk, or copy.

## 9. Supplying a patch (Cloud side)

```
cloud/patches/task_002/
├── patch_manifest.json
└── files/
    └── site/cards/UA-0009.html      # payload mirrors the production path
```

`cloud/patch_manifest.example.json` is a valid template. Rules the validator
enforces — any violation stops the run with nothing executed:

* All five keys required: `task_id`, `mode`, `allowed_files`, `expected_tests`,
  `rollback_source`. Unknown keys are rejected.
* `task_id` must match the newest task in `tasks/`.
* `allowed_files` are relative, normalised, non-duplicated, traversal-free, and
  must not hit the denylist (`*.db`, `.env`, `*token*`, media, `backups/`, …).
* `expected_tests` must name entries of the internal registry. A shell string
  such as `"rm -rf /"` is rejected, never executed.
* `rollback_source` must be `auto_backup` or `backup:<absolute path outside the repo>`.
* Payload files are **copied**, never imported or executed.

Test registry: `sandbox_diff_matches_manifest`, `no_forbidden_patterns`,
`no_secrets_in_patch`, `file_size_guard`, `ua_baseline_unchanged`,
`crm_db_untouched`, `no_production_publication`, `python_compiles`,
`json_valid`, `html_wellformed`. The first seven run on every patch round
regardless of what the manifest asks for.

## 10. Modes

**READ_ONLY** — automatic, no production write. Runs when the task declares it
or when no valid manifest exists.

**SAFE_PATCH** — applied only when *all* of: CPU guard OK, whitelist PASS,
every target exists with SHA256 captured, backup PASS and verified, sandbox
PASS, every test PASS, UA-0001…UA-0008 unchanged, CRM integrity PASS or not
applicable, and unexpected changes `= 0` after apply. Any post-apply failure
triggers automatic rollback from the backup with SHA256 verification.

**CRITICAL** — never auto-applies. The runner performs the full read-only
preparation (backup, sandbox, tests) and stops at `WAITING_OWNER_APPROVAL`
with `PRODUCTION_CHANGED: NO`. The effective mode is always the **stricter**
of the task's `MODE:` and the manifest's `mode`, so a CRITICAL task cannot be
downgraded by a manifest.

To approve a CRITICAL change the owner writes, outside the repository:

```bash
echo "APPROVE task_002 <manifest sha256 from the report>" \
  > /home/Carix/.autopilot/approvals/task_002.approval
```

The approval is bound to that exact manifest SHA256; editing the manifest
invalidates it. Even then, runner v1 does **not** execute the CRITICAL change
automatically — `--apply-critical` deliberately exits with a notice. The
approved change is performed under explicit owner supervision.

## 11. What never reaches GitHub

Only `python/report_NNN.txt` is ever staged. Before committing, the runner
scans the report for secret shapes (GitHub/Telegram/AWS tokens, private keys,
`password=`, bearer headers) and refuses the push on a hit. It then verifies
that the staged set contains exactly that one file and nothing denylisted; a
mismatch resets the index and aborts the push. Backups, `crm.db`, media and
state all live outside the clone by configuration.

Recommended defence in depth — the owner adds a repository-root `.gitignore`
(this is a repository change, so it is left to the owner):

```
*.db
*.sqlite*
.env
*token*
*secret*
backups/
media/
*.log
```

## 12. Reading the report

`python/report_NNN.txt` ends with the block mandated by
`docs/UA_ART_AUTOPILOT_V1.md` (`TASK_ID:` … `STATUS:`). Above it sit the
execution log, per-test PASS/FAIL lines, and the CPU guard state. ChatGPT
reads that block to decide the next round.

`STATUS` values: `CONTINUE`, `WAITING_OWNER_APPROVAL`, `WAITING_VISUAL_CHECK`,
`TASK_CLOSED`, `STOPPED`. The runner stops with `STOPPED` once the round
counter passes `MAX_ROUNDS`.

## 13. Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `WHITELIST: FAIL … whitelist_roots is empty` | Expected until step 4 is completed with real paths. |
| `STATUS: STOPPED … DEFERRED_CPU_LIMIT` | CPU quota `>= 85%` or load `>= 2.00` per CPU. Re-run later. |
| `UA_0001_0008_UNCHANGED: FAIL` | A protected card changed outside the autopilot. Investigate before any patch; do not re-init the baseline to hide it. |
| `git fast-forward failed` | Local commits or a dirty tree in the clone. Resolve manually. |
| `PUSH REFUSED: unexpected staged files` | Something else was staged in the clone. The index is reset; clean the tree. |
| `payload file missing for <path>` | `cloud/patches/<task_id>/files/<path>` was not delivered. |
