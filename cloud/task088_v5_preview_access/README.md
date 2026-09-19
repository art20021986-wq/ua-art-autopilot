# One-time protected Preview provisioning

This package prepares only the newly created `Carix.pythonanywhere.com` app.
It does not reload an app, write Production, install the price autopilot, or
declare Stage 3 PASS. The current browser connection was unavailable while this
package was prepared; no deployment or owner-password entry has occurred.

The provisioner is pinned to this exact reviewed server state:

| Input | Binding |
| --- | --- |
| Private stage | `/home/Carix/autopilot_inbox/cloud/task088-v5-preview-stage-zlcw0vma` |
| Candidate manifest SHA256 | `083cd2de139f2f9e695f76c4e9873252c3291b4adb90af488c069315b37abdd6` |
| V2 package archive SHA256 | `4f64d00e55f419e50876770a18c0c336bc1e53704e468bbefc434237e5a5baad` |
| New app WSGI | `/var/www/carix_pythonanywhere_com_wsgi.py` |
| Current default WSGI SHA256 | `e6e40b1b3c329130935e95c60cf18d76fddedf7e8bf5be40f7e768d9a9e5b45e` |
| Preview HTTP origin | `https://carix.pythonanywhere.com` |
| Hosting API app label | `Carix.pythonanywhere.com` |

The existing provider-managed `API_TOKEN` is used only for GET requests to the
new app's configuration and static-mapping endpoints. HTTPS must be enabled and
static mappings must be empty. Raw hosting responses and credentials are never
printed or saved. Any input, source, routing, default-WSGI or package drift stops
provisioning; this package must not be repinned merely to suppress a failure.

After the package has been uploaded and its archive SHA256 checked, a read-only
readiness check is available:

```bash
python3.10 -I -B t088-preview-provision.zip --check-only
```

This performs no password input, file write, installation, or reload. Actual
provisioning uses the same package without that option:

```bash
python3.10 -I -B t088-preview-provision.zip
```

The owner enters a new Preview password twice directly into the interactive
terminal while echo is disabled. It must have at least 16 characters. Never
send the password in chat, a command argument, shell history, an environment
variable, or a screenshot. A missing terminal or a getpass echo fallback is an
error. The non-secret Preview username is `uaart-preview`.

For an already provisioned secret, `--secret-file` reads only the exact private
stage file `preview-password.txt`; it must be a regular non-symlink file owned
by the account with mode 0600. The tool does not create or print that file. The
interactive hidden input avoids creating a plaintext password file.

The password verifier uses PBKDF2-HMAC-SHA256, a random 32-byte salt, and 600,000
iterations. A new private app directory and its configuration are created with
modes 0700 and 0600. The five exact reviewed runtime files are copied there and
hash-checked before any import and again after the authentication self-test.
Every exposed route must reject missing authentication before the new WSGI is
written; wrong credentials, wrong origin, HTTP, private paths, and write methods
are also checked. These are local boundary checks, not browser acceptance.

A verified mode-0600 backup of the new app's default WSGI is saved before its
replacement. Because the platform-owned `/var/www` directory may forbid rename,
replacement uses a nonblocking file lock, byte comparison, write/fsync, and
read-back of that existing file. This is not an atomic rename. A write failure
restores that new app's default bytes; the tool never restores or edits
Production. If post-write observation fails, the output explicitly reports that
the new Preview WSGI was written and identifies its recovery copy.

No reload request is sent. Writing a WSGI file may still be observed by platform
processes independently; the candidate always has its authentication gate and
private configuration in place first. The next executor separately reloads only
the new Preview app, verifies unauthenticated denial and authenticated access,
then performs the 120 browser cases and remaining acceptance checks.

`TEST_RECEIPT.json` records 16 isolated tests with no failures or skips. Tests use
temporary fixtures and mocked hosting observations; they are not evidence of a
successful server installation. This one-time package is separate from the
frozen renderer/Preview regression source set.
