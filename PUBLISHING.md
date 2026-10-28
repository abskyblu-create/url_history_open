# Publishing and maintenance

This guide records the safeguards used for the first publication and the steps to preserve them on later updates.

## 1. Keep the publication boundary explicit

Publish source code, setup/launch scripts, documentation, tests, health-check configuration, and the synthetic `sample.csv` only.

Keep `.python`, `.venv`, `.tools`, `.reviews`, `.semantic`, real CSV/Excel inputs, reports, backups, local settings, and credentials outside Git. The public-file allowlist in `scripts/check_publish.py` is an additional safeguard if an ignore rule is bypassed. Update that allowlist only when adding reviewed public source files.

## 2. Prepare each clone

```powershell
.\setup.bat
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
git config core.hooksPath .githooks
```

The hook configuration is not transferred by cloning. Enable it explicitly on every new checkout. The application itself needs only `requirements.txt`; lint/audit/secret-scanning tools are development dependencies.

## 3. Check changes before staging

```powershell
git status --short --ignored
git diff
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p ui_check.py -v
.\.venv\Scripts\python.exe -m pip_audit -r requirements-dev.txt
```

Run the optional `excel_check.py` and `semantic_check.py` integration tests when changing those integrations and the required local services are available. No live spreadsheet or model service is required by the normal GitHub workflow.

## 4. Stage only the intended public files

Prefer explicit paths, for example:

```powershell
git add app.py review.py README.md tests
git diff --cached --stat
git diff --cached
.\.venv\Scripts\python.exe scripts/check_publish.py --staged
.\.venv\Scripts\python.exe scripts/check_secrets.py --staged
```

The secret scanner reads the actual staged versions, so a secret cannot be hidden from it simply by editing the working copy after staging. Scanner failures block publication; resolve them rather than disabling a check. Never use `git add -f` for private files.

## 5. Commit and push

```powershell
git commit -m "Describe the change"
git push
```

The pre-commit hook runs the file-inventory and secret checks. After pushing, open the repository's **Actions → Health checks** page and verify all jobs pass. These jobs test Python 3.11 and 3.13 on Windows and separately audit dependencies.

Checks run only after GitHub receives the commit. Before-push protection comes from the local review, tests, and hook. A failed GitHub check does not remove an already-pushed commit.

## 6. Require healthy changes before merging

Configure a GitHub branch rule or ruleset for `main` to require pull requests and successful checks before merging. Use the check names actually produced by the workflow:

- `Python 3.11 checks`
- `Python 3.13 checks`
- `Dependency vulnerability audit`

Rulesets and branch protection are repository settings, not effects of adding a workflow file. Verify they are enabled separately. Enable GitHub secret scanning, push protection, and private vulnerability reporting in repository settings where available. Those GitHub features supplement the included local and CI scans.

## 7. Maintain dependencies

Review weekly Dependabot pull requests and the scheduled health-check run. Test dependency changes before merging. The repository currently uses bounded dependency ranges, not a fully hashed lockfile, so installed transitive versions can change between fresh setups.

Do not publish the current environment with `pip freeze`: it may contain unrelated old packages and machine-specific paths. The application dependency list is intentionally separate from the local environment inventory.

## 8. Inspect the public file inventory periodically

```powershell
git ls-files
.\.venv\Scripts\python.exe scripts/check_publish.py
.\.venv\Scripts\python.exe scripts/check_secrets.py
```

Without `--staged`, the secret scanner checks the current committed snapshot. Use `--staged` before a new commit. Neither mode replaces an audit of historical commits if sensitive material was previously published.

## What the first-publication preparation does

1. Initializes a `main` branch.
2. Excludes private inputs, credentials, local state, environments, caches, and backups.
3. Removes personal search examples from public-facing source/tests.
4. Adds a public-source allowlist and a secret scanner.
5. Enables a local commit hook in the current checkout.
6. Adds repeatable lint, test, consistency, vulnerability, and secret checks in GitHub Actions.
7. Pins third-party actions to reviewed commit IDs and gives workflows read-only permissions.
8. Adds weekly dependency-update proposals.
9. Uses a GitHub no-reply commit address for the initial public commit.
10. Creates/pushes the public repository only after local checks pass, then verifies the remote file inventory and workflow status.

Actual publication and repository-setting outcomes are reported when publishing completes. These instructions alone do not assert that a push or a remote check has succeeded.
