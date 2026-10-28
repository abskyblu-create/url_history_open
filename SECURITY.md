# Security and private data

This repository contains application source and synthetic examples. It must not contain real browsing libraries, fetched page text, review decisions, model files, credentials, or source-file backups.

## What stays local

`.gitignore` excludes virtual environments, local Python, model/vector caches, saved reviews, imported spreadsheets, CSV reports, backups, logs, environment files, private keys, credential files, and machine-specific settings. `sample.csv` is the only CSV intentionally included and contains public example URLs.

Ignore rules do not protect files that were already tracked or force-added. `scripts/check_publish.py` independently checks the tracked file inventory against a public-source allowlist. `scripts/check_secrets.py` scans indexed/committed content using detect-secrets, without printing candidate values or sending them for online verification. Secret detection is heuristic and does not guarantee that every sensitive value will be recognized; review the staged diff as well.

## Local checks

Install `requirements-dev.txt` and enable the supplied hook:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
git config core.hooksPath .githooks
```

The hook blocks a normal commit if staged paths are outside the allowlist or a potential secret is found. Hooks are local configuration and must be enabled on each clone. They can be bypassed; CI repeats both checks independently.

## GitHub checks

The Health checks workflow runs on pushes, pull requests, manual requests, and a weekly schedule. It checks the public file inventory, scans committed content, lints source, runs unit/desktop tests, verifies dependency consistency, and audits dependency vulnerabilities. Windows tests use synthetic temporary inputs and mock browser launches. Live Ollama and installed-Excel tests remain manual because hosted runners do not have those local services.

Actions are pinned to verified commit IDs, repository permissions are read-only, checkout credentials are not persisted, and untrusted pull-request code is not executed through `pull_request_target`. Dependabot proposes Python and action updates weekly. A maintainer must review those updates and fix failures; an automated check is not a guarantee of security.

## If a credential is exposed

Revoke or rotate it immediately. Removing it from the current file does not remove it from Git history. Do not put the credential in an issue, screenshot, or public support request. Review history and coordinate any cleanup with repository collaborators.

## Reporting a concern

Use GitHub private vulnerability reporting if the repository has it enabled. Otherwise contact the repository owner privately. Do not post real tokens, private URLs, spreadsheets, or review files in a public issue.
