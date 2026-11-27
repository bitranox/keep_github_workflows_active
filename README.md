# keep_github_workflows_active

<!-- Badges -->
[![CI](https://github.com/bitranox/keep_github_workflows_active/actions/workflows/default_cicd_public.yml/badge.svg)](https://github.com/bitranox/keep_github_workflows_active/actions/workflows/default_cicd_public.yml)
[![CodeQL](https://github.com/bitranox/keep_github_workflows_active/actions/workflows/codeql.yml/badge.svg)](https://github.com/bitranox/keep_github_workflows_active/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Open in Codespaces](https://img.shields.io/badge/Codespaces-Open-blue?logo=github&logoColor=white&style=flat-square)](https://codespaces.new/bitranox/keep_github_workflows_active?quickstart=1)
[![PyPI](https://img.shields.io/pypi/v/keep_github_workflows_active.svg)](https://pypi.org/project/keep_github_workflows_active/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/keep_github_workflows_active.svg)](https://pypi.org/project/keep_github_workflows_active/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-46A3FF?logo=ruff&labelColor=000)](https://docs.astral.sh/ruff/)
[![codecov](https://codecov.io/gh/bitranox/keep_github_workflows_active/graph/badge.svg?token=UFBaUDIgRk)](https://codecov.io/gh/bitranox/keep_github_workflows_active)
[![Maintainability](https://qlty.sh/badges/041ba2c1-37d6-40bb-85a0-ec5a8a0aca0c/maintainability.svg)](https://qlty.sh/gh/bitranox/projects/keep_github_workflows_active)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

> **CI cadence:** the `CI` workflow runs on every push and pull request to `main`/`master` and
> daily at 03:17 UTC; `CodeQL` runs on push, pull request and Mondays at 08:00 UTC.


## Overview

`keep_github_workflows_active` keeps the GitHub Actions workflows of an owner's repositories
enabled and prunes their old workflow runs. GitHub disables scheduled workflows in repositories
without recent activity (per GitHub's Actions docs); running this tool on a schedule re-enables
them.

It has two jobs, one CLI command each:

1. **`enable-all-workflows`** - for every repository of the owner, send the "enable workflow"
   request for each of its workflow files. Workflow files whose names start with
   `pages-build-deployment` (cannot be enabled), `dependabot` (managed by Dependabot) or
   `update-graph` (managed by the dependency graph) are skipped.
2. **`delete-old-workflow-runs`** - for every repository of the owner, keep the newest runs (the
   highest run ids across all of the repository's workflows; 50 by default, `--keep` to change)
   and delete the rest.

Repositories are listed from `/orgs/<owner>/repos`; when GitHub answers 404 (the owner is not an
organisation), from `/users/<owner>/repos` instead. Per GitHub's REST docs, the user endpoint
lists the user's public repositories.

This repository runs both commands from `.github/workflows/activate_workflows.yml`, whose
`activate` job runs only on the weekly schedule (Fridays at 03:47 UTC); push and pull request
runs of that workflow only run the tests.


## Prerequisites

### Generate an access token

The commands authenticate with a personal access token, sent as `Authorization: Bearer <token>`.
You can create one on the GitHub settings page:

- [Personal access tokens](https://github.com/settings/personal-access-tokens)

Give the token the permissions GitHub's REST docs list for the endpoints the tool calls:

| Endpoint                                                    | Used by                    |
|-------------------------------------------------------------|----------------------------|
| `GET /orgs/<owner>/repos`, then `GET /users/<owner>/repos`  | both commands              |
| `GET /repos/<owner>/<repo>/actions/workflows`               | `enable-all-workflows`     |
| `PUT /repos/<owner>/<repo>/actions/workflows/<file>/enable` | `enable-all-workflows`     |
| `GET /repos/<owner>/<repo>/actions/runs`                    | `delete-old-workflow-runs` |
| `DELETE /repos/<owner>/<repo>/actions/runs/<run_id>`        | `delete-old-workflow-runs` |

Tokens can expire; renew yours before its expiry date to keep the scheduled runs working.

### Store the token as a repository secret

Add the token to the repository's secrets so GitHub Actions can inject it at
runtime:

- [Repository secrets](https://github.com/bitranox/keep_github_workflows_active/settings/secrets/actions)

Define the following secrets:

- `SECRET_GITHUB_OWNER` - the user or organisation whose repositories should be scanned.
- `SECRET_GITHUB_TOKEN` - the personal access token you generated.

### Where the commands look for the owner and token

`--owner` and `--token` on the command line win. Without them, each value is looked up in this
order, and the first non-empty value is used:

1. the environment variable (`SECRET_GITHUB_OWNER` / `SECRET_GITHUB_TOKEN`);
2. the file named by `KEEP_GITHUB_WORKFLOWS_ACTIVE_DOTENV_PATH`, if that variable is set;
3. `.env` in the current working directory;
4. `.env` in the installed package directory;
5. `.env` two levels above the package directory (the repository root when running from a
   source checkout or an editable install).

A `.env` file holds `KEY=value` lines; blank lines and lines starting with `#` are skipped, and
surrounding quotes are removed from the value. When no value is found the command stops with
`Missing required configuration: SECRET_GITHUB_OWNER` (or `..._TOKEN`).

### Which tests call the live GitHub API

`make test` and CI never call the live API: the tests that do are marked `integration` and
`local_only` (`tests/test_github_integration.py`), which `make test` excludes, and they skip
whenever the `CI` environment variable is set. `make testintegration` runs them locally against
the configured account; they list repositories, workflows and runs and call
`enable_all_workflows` and `enable_workflow`, which re-enable that account's workflows. No test
deletes workflow runs.


## Installation

Install the package from PyPI:

```bash
pip install keep_github_workflows_active
```

Installing from a checkout, from a built wheel, with pipx or with uv is described in
[INSTALL.md](INSTALL.md). Every install puts two console scripts on your `PATH`,
`keep_github_workflows_active` and `keep-github-workflows-active`, which run the same CLI.

### Supported platform: Python 3.14 on Linux

- The package requires **Python 3.14 or newer** (`requires-python = ">=3.14"`)
  and is built and tested for **Linux** only.
- Continuous integration runs on GitHub's `ubuntu-latest` runner with CPython
  3.14; the CI matrix comes from the `Programming Language :: Python :: 3.14`
  classifier and `[tool.ci].os` in `pyproject.toml`.
- Runtime dependencies: `rich-click` (CLI), `lib_cli_exit_tools` (exit codes and traceback
  output), `requests` (GitHub API calls) and `pydantic` (parsing GitHub's replies).

### Why we recommend uv: supply-chain protection

This repository commits a `uv.lock`. It pins every package the project needs, transitive
dependencies included, to an exact version and to the hashes of that version's files. The
`exclude-newer` setting under `[tool.uv]` in `pyproject.toml` adds a cooldown: uv leaves any
release younger than that out of the lock. CI installs from the lock, so a hijacked release that
gets pulled again within the cooldown never reaches our builds, and a file whose hash does not
match is refused.

That protection stays in this repository. The installable package declares only lower bounds
(`>=`) for its dependencies, so a plain `pip install` takes the newest release of every transitive
dependency at the moment you run it. If one of them was hijacked an hour earlier, you get the
hijacked version. `pipx install` and `uv tool install` without options do the same.

To install the command line tool with a cooldown of your own (uv then skips any release younger
than 7 days, transitive ones included), or to run the exact tree our CI tests:

```bash
uv tool install --exclude-newer "7 days" keep_github_workflows_active
git clone https://github.com/bitranox/keep_github_workflows_active.git && cd keep_github_workflows_active && uv sync --locked && uv run keep_github_workflows_active --help
```

If you depend on keep_github_workflows_active in your own project, give that project the same cooldown (7 days here, as
an example) and commit the `uv.lock` that `uv add keep_github_workflows_active` writes:

```toml
[tool.uv]
exclude-newer = "7 days"
```

## Usage

Run the two maintenance commands from a scheduled GitHub Actions workflow, as
`.github/workflows/activate_workflows.yml` does, or by hand:

```bash
keep-github-workflows-active enable-all-workflows [--owner <owner>] [--token <token>]
keep-github-workflows-active delete-old-workflow-runs [--owner <owner>] [--token <token>] [--keep <n>]
```

| Option    | Commands                   | Meaning                                                                 |
|-----------|----------------------------|-------------------------------------------------------------------------|
| `--owner` | both                       | user or organisation; defaults to `SECRET_GITHUB_OWNER` (lookup above)  |
| `--token` | both                       | personal access token; defaults to `SECRET_GITHUB_TOKEN` (lookup above) |
| `--keep`  | `delete-old-workflow-runs` | runs to keep per repository, default `50`                               |

Each command opens one HTTPS session for the whole run and reuses its connection for every API
call. Lists are read 100 entries per page, following GitHub's pagination links.

A command stops with a non-zero exit code when:

- GitHub answers an error status while listing repositories, workflows or runs, or while enabling
  a workflow (`ERROR reading ...` / `ERROR enabling ...`);
- a reply does not have the shape the tool acts on, for example a run without `id` or a listing
  that is not a list (`Unexpected GitHub reply for <what>: <field>: <reason>`, or
  `... the body is not JSON`);
- a delete request fails at the network level (`ERROR deleting workflow run ID ...`).

The other commands are diagnostics:

```bash
keep-github-workflows-active --version
keep-github-workflows-active info               # print package metadata
keep-github-workflows-active hello              # print "Hello World"
keep-github-workflows-active fail               # raise a RuntimeError (short error output)
keep-github-workflows-active --traceback fail   # the same with the full traceback
python -m keep_github_workflows_active --help   # same CLI as the console scripts
```

Without a subcommand the CLI prints its help.

### Python API

The functions behind the commands live in `keep_github_workflows_active.keep_github_workflow_active`:

```python
from keep_github_workflows_active import keep_github_workflow_active as kgwa

token = kgwa.get_github_token()  # same lookup as the CLI
kgwa.enable_all_workflows(owner="example-org", github_token=token)
kgwa.delete_old_workflow_runs(owner="example-org", github_token=token, number_of_workflow_runs_to_keep=50)

# The single-step functions take a session from github_session():
with kgwa.github_session(token) as session:
    for repository in kgwa.get_repositories(owner="example-org", session=session):
        run_ids = kgwa.get_workflow_runs(owner="example-org", repository=repository, session=session)
```

The package root exports only the diagnostic helpers (`emit_greeting`,
`raise_intentional_failure`, `noop_main`, `print_info`, `CANONICAL_GREETING`).


## Security

The token travels only in the `Authorization` header of the session that `github_session()`
builds; no log message contains it. Every log message of the GitHub module passes through
`sanitization.sanitize_message()`, which replaces token-like text with `[REDACTED]`:

- GitHub tokens (`ghp_...`, `gho_...`, `ghs_...` and the other `gh?_` prefixes)
- hexadecimal strings of 40 or more characters
- base64-like strings of 40 or more characters

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
