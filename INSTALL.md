# Installation Guide

`keep_github_workflows_active` requires **Python 3.15 or newer on Linux**
(`requires-python = ">=3.15"`, classifier `Operating System :: POSIX :: Linux`).

Every method below installs two console scripts that run the same CLI:
`keep_github_workflows_active` and `keep-github-workflows-active`.

## 1. From PyPI

```bash
pip install keep_github_workflows_active
```

To install with a supply-chain cooldown, see "Why we recommend uv" in [README.md](README.md).

## 2. From a checkout (editable)

These are the commands behind `make install` and `make dev`:

```bash
uv pip install -e .            # runtime dependencies only (make install)
uv pip install -e ".[dev]"     # plus the test and lint tools (make dev)
```

To install exactly the locked dependency tree CI uses:

```bash
uv sync --locked
```

## 3. From a built wheel

```bash
uv build                       # writes dist/*.whl and dist/*.tar.gz
uv pip install dist/*.whl
```

## 4. As an isolated command-line tool

```bash
pipx install dist/*.whl        # after uv build
uv tool install .              # from a checkout
```

The `pipx/uv verification` job in `.github/workflows/activate_workflows.yml` runs `uv build`,
`pipx install dist/*.whl` and `uv tool install .` and then calls the installed CLI with
`--version`.
