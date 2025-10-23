# Installation Guide

> The CLI stack uses `rich-click`, which bundles `rich` styling on top of click-style ergonomics.

This guide collects every supported method to install `keep_github_workflows_active`, including
isolated environments and system package managers. Pick the option that matches your workflow.

## 1. Standard Virtual Environment (pip)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]       # development install
# or for runtime only:
pip install .
```

## 2. Per-User Installation (No Virtualenv)

```bash
pip install --user .
```

> Note: This respects PEP 668. Avoid using it on system Python builds marked as
> "externally managed". Ensure `~/.local/bin` (POSIX) is on your PATH so the CLI is available.

## 3. pipx (Isolated CLI-Friendly Environment)

```bash
pipx install .
pipx upgrade keep_github_workflows_active
# From Git tag/commit:
pipx install "git+https://github.com/bitranox/keep_github_workflows_active"
```

## 4. uv (Fast Installer/Runner)

```bash
uv pip install -e .[dev]
uv tool install .
uvx keep_github_workflows_active --help
```

## 5. From Build Artifacts

```bash
python -m build
pip install dist/keep_github_workflows_active-*.whl
pip install dist/keep_github_workflows_active-*.tar.gz   # sdist
```

## 6. Poetry or PDM Managed Environments

```bash
# Poetry
poetry add keep_github_workflows_active     # as dependency
poetry install                          # for local dev

# PDM
pdm add keep_github_workflows_active
pdm install
```

## 7. Install Directly from Git

```bash
pip install "git+https://github.com/bitranox/keep_github_workflows_active#egg=keep_github_workflows_active"
```

## 8. System Package Managers (Optional Distribution Channels)

- Deb/RPM: Package with `fpm` for OS-native delivery

All methods register both the `keep_github_workflows_active` and
`keep-github-workflows-active` commands on your PATH.
