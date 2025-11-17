# keep_github_workflows_active

<!-- Badges -->
[![CI](https://github.com/bitranox/keep_github_workflows_active/actions/workflows/ci.yml/badge.svg)](https://github.com/bitranox/keep_github_workflows_active/actions/workflows/ci.yml)
[![CodeQL](https://github.com/bitranox/keep_github_workflows_active/actions/workflows/codeql.yml/badge.svg)](https://github.com/bitranox/keep_github_workflows_active/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Open in Codespaces](https://img.shields.io/badge/Codespaces-Open-blue?logo=github&logoColor=white&style=flat-square)](https://codespaces.new/bitranox/keep_github_workflows_active?quickstart=1)
[![PyPI](https://img.shields.io/pypi/v/keep_github_workflows_active.svg)](https://pypi.org/project/keep_github_workflows_active/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/keep_github_workflows_active.svg)](https://pypi.org/project/keep_github_workflows_active/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-46A3FF?logo=ruff&labelColor=000)](https://docs.astral.sh/ruff/)
[![codecov](https://codecov.io/gh/bitranox/keep_github_workflows_active/graph/badge.svg?token=UFBaUDIgRk)](https://codecov.io/gh/bitranox/keep_github_workflows_active)
[![Maintainability](https://qlty.sh/badges/041ba2c1-37d6-40bb-85a0-ec5a8a0aca0c/maintainability.svg)](https://qlty.sh/gh/bitranox/projects/keep_github_workflows_active)
[![Known Vulnerabilities](https://snyk.io/test/github/bitranox/keep_github_workflows_active/badge.svg)](https://snyk.io/test/github/bitranox/keep_github_workflows_active)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

> **CI cadence:** The GitHub Actions CI workflow runs automatically every Monday at 07:00 UTC, in addition to push and pull request triggers.


## Overview

`keep_github_workflows_active` is an automation helper that tends to every
GitHub Actions workflow in a user's repositories. It exists to remove the
routine maintenance burden that accrues when repositories go quiet and Actions
start to disable schedules automatically.

The automation focuses on two responsibilities:

1. **Keep all workflows active** – iterate every repository owned by the
   configured user and flip disabled workflows back to the active state so
   cron-based automation continues to run.
2. **Delete stale workflow runs** – retain an operator-defined number of the
   freshest runs per workflow and delete older artifacts so storage quotas and
   repository hygiene remain under control.

Both behaviors run as part of repository automation (for example on a nightly
schedule) once the required GitHub token is in place.


## Prerequisites

### Generate an access token

The automation requires a fine-grained personal access token with repository
scope. You can create one by visiting the GitHub self-service page:

- [Generate fine-grained personal access token](https://github.com/settings/personal-access-tokens)

When configuring the token, grant at least the following permissions:

- **Actions:** Read/Write (needed to toggle workflow states and delete runs).
- **Metadata:** Read (lets the script discover repositories you own).

Tokens expire automatically. Renew them before the expiry hits to keep the
automation alive. The previous test token that powered the repository expired on
**January 19, 2025**, so any current setup must already use a newer credential.

### Store the token as a repository secret

Add the token to the repository's secrets so GitHub Actions can inject it at
runtime:

- [Repository secrets](https://github.com/bitranox/keep_github_workflows_active/settings/secrets/actions)

Define the following secrets:

- `SECRET_GITHUB_OWNER` – GitHub username whose repositories should be scanned.
- `SECRET_GITHUB_TOKEN` – the fine-grained personal access token you generated.

Keeping the credentials inside secrets ensures the nightly cleanup workflow can
authenticate without hard-coding sensitive values in the repository.

For local development you can place the same keys inside a `.env` file at the
repository root. The automation reads from the environment first and falls back
to `.env` when running outside GitHub Actions.

> **Note:** the included tests and CLI commands exercise the live GitHub API.
> When `SECRET_GITHUB_OWNER` and `SECRET_GITHUB_TOKEN` point at a real account,
> running `make test` (or the workflow maintenance commands directly) will
> re-enable workflows and prune old workflow runs across the configured
> repositories.


## Installation

Install the package locally when you want to run the CLI helpers or contribute
changes:

```bash
pip install keep_github_workflows_active
```

Alternative flows (pipx, uv, editable installs, or source builds) are described
in [INSTALL.md](INSTALL.md). All supported options expose both the
`keep_github_workflows_active` and `keep-github-workflows-active` entry points on
your `PATH`.

### Python 3.13+ baseline

- The package targets **Python 3.13 and newer**. Older interpreters are no
  longer supported; the codebase relies on modern conveniences such as
  `Path.unlink(missing_ok=True)`.
- Runtime modules now use native Python 3.13 type syntax (e.g., `list[str]`,
  `Sequence[str] | None`) and drop legacy compatibility helpers.
- Runtime dependencies include `rich-click` for the CLI surface and
  `lib_cli_exit_tools` for consistent exit handling. Development extras pin the
  tooling stack (pytest, ruff, pyright, bandit, build, twine, codecov-cli,
  pip-audit, textual, import-linter) to their latest major releases.
- Development dependencies were refreshed to the latest stable releases
  (`ruff>=0.14.1`, `textual>=6.4.0`).
- Continuous integration runs across GitHub's hosted runners (`ubuntu-latest`,
  `macos-latest`, `windows-latest`) on CPython 3.13 in addition to the most
  recent 3.x release Actions makes available.


## Usage

Once installed and authenticated via repository secrets, schedule the automation
from a GitHub Actions workflow (see `docs/systemdesign/module_reference.md` for
the architectural wiring). The CLI remains available for local smoke-tests and
packaging checks while the richer workflow management helpers iterate:

```bash
keep_github_workflows_active info
keep_github_workflows_active hello
keep_github_workflows_active fail
keep_github_workflows_active --traceback fail
keep_github_workflows_active enable-all-workflows [--owner <user>] [--token <pat>]
keep_github_workflows_active delete-old-workflow-runs [--owner <user>] [--token <pat>] [--keep <n>]
keep-github-workflows-active info
python -m keep_github_workflows_active info
```

The workflow maintenance commands accept optional flags. When ``--owner`` or
``--token`` is omitted the CLI falls back to the values discovered via
environment variables or the project's ``.env`` file. ``--keep`` defaults to
``50`` workflow runs per repository.

Programmatic access is also exposed via the public helpers:

```python
import keep_github_workflows_active as kgwa

kgwa.emit_greeting()
try:
    kgwa.raise_intentional_failure()
except RuntimeError as exc:
    print(f"caught expected failure: {exc}")

kgwa.print_info()
```


## Security

All logging operations sanitize sensitive data before output to prevent credential
leakage. The automation redacts:

- GitHub personal access tokens (ghp_*, gho_*, etc.)
- Authorization headers and API keys
- Token-like patterns in error messages

For complete security documentation including incident response procedures, see
[SECURITY.md](docs/systemdesign/SECURITY.md).

## Further documentation

- [Install Guide](INSTALL.md)
- [Development Handbook](DEVELOPMENT.md)
- [Contributor Guide](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Module Reference](docs/systemdesign/module_reference.md)
- [Security Documentation](docs/systemdesign/SECURITY.md)
- [License](LICENSE)
