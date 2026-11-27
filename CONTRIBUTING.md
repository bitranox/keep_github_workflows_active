# Contributing Guide

Thanks for helping improve **keep_github_workflows_active**. The sections below summarise the
day-to-day workflow and list the checks that must pass before a change is merged.

## 1. Workflow Overview

1. Fork and branch - use short, imperative branch names (`feature/cli-extension`, `fix/codecov-token`).
2. Make focused commits - keep unrelated refactors out of the same change.
3. Run `make test` locally before pushing (see below).
4. Update the documentation and add a changelog entry under `## [Unreleased]` in `CHANGELOG.md`.
5. Open a pull request referencing any relevant issues.

## 2. Commits & Pushes

- Commit messages should be imperative (`Add rich handler`, `Fix CLI exit codes`).
- `make test` can change files: it updates dependencies, re-locks `uv.lock` and applies ruff's
  formatting and autofixes before it checks. Review `git status` afterwards.
- `make push` runs the build and the full test pipeline, then commits and pushes. Give the
  message as `make push MSG="..."`; without one it prompts on a terminal. When nothing is staged
  it creates an empty commit.

## 3. Coding Standards

- Ruff enforces the rule set in `[tool.ruff.lint].select` in `pyproject.toml`, including a
  cyclomatic complexity limit of 10 per function (`C90`).
- Pyright runs in strict mode; import-linter enforces the layer contract in `[tool.importlinter]`
  (`cli` may import `behaviors`, not the other way round).
- Data from GitHub is parsed into the Pydantic models in `keep_github_workflow_active.py` at the
  point it arrives; code past that point works with the models, not with dicts.
- Free functions and modules use `snake_case`; classes are `PascalCase`.
- Keep runtime dependencies minimal. Use the standard library where practical.

## 4. Tests & Tooling

- `make test` runs ruff (format and lint), pyright, pytest with coverage, bandit, import-linter
  and pip-audit; [DEVELOPMENT.md](DEVELOPMENT.md) lists the stages.
- Tests that call the live GitHub API carry both `@pytest.mark.integration` and
  `@pytest.mark.local_only`; `make test` and CI exclude them, `make testintegration` runs them.
- Tests follow a narrative style: prefer names like `test_when_<condition>_<outcome>()` and keep
  each case focused.
- Whenever you add a CLI behaviour or change metadata, update the relevant story in
  `tests/test_cli.py` or `tests/test_metadata.py`.

## 5. Documentation Checklist

Before opening a PR, confirm the following:

- [ ] `make test` passes locally.
- [ ] Relevant documentation (`README.md`, `DEVELOPMENT.md`, `docs/systemdesign/*`) is updated.
- [ ] No generated artefacts or virtual environments are committed.
- [ ] Version bumps go through `make bump-patch` / `bump-minor` / `bump-major`, which update
      `pyproject.toml` and `src/keep_github_workflows_active/__init__conf__.py` together.

## 6. Security & Configuration

- Never commit secrets. `SECRET_GITHUB_OWNER`, `SECRET_GITHUB_TOKEN` and `CODECOV_TOKEN` belong in
  `.env` (ignored by git) or in CI secrets.
- Pass every log message through `sanitization.sanitize_message()`; see
  [SECURITY.md](docs/systemdesign/SECURITY.md).
