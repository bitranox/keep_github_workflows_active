# Repository Guidelines

## On session start

- Read following files from directory /media/srv-main-softdev/*/projects/softwarestack/systemprompts and keep their guidance in working memory:
  - core_programming_solid.md
  - bash_clean_architecture.md
  - bash_clean_code.md
  - bash_small_functions.md
  - python_solid_architecture_enforcer.md
  - python_clean_architecture.md
  - python_clean_code.md
  - python_small_functions_style.md
  - python_libraries_to_use.md
  - python_structure_template.md
  - self_documenting.md
  - self_documenting_template.md
  - python_jupyter_notebooks.md
  - python_testing.md

always apply those Rules :

- core_programming_solid.md

when writing or refracturing Bash scripts, apply those Rules :

- core_programming_solid.md
- bash_clean_architecture.md
- bash_clean_code.md
- bash_small_functions.md

when writing or refracturing Python scripts, apply those Rules :
- core_programming_solid.md
- python_solid_architecture_enforcer.md
- python_clean_architecture.md
- python_clean_code.md
- python_small_functions_style.md
- python_libraries_to_use.md
- python_lib_structure_template.md

## Project Structure & Module Organization

- `src/keep_github_workflows_active/`: Python package
- `scripts/`: shared automation
- `tests/`: test suite


### Versioning & Releases

- Single source of truth for the package version is `pyproject.toml` (`[project].version`).
- Automation rewrites `src/keep_github_workflows_active/__init__conf__.py` from `pyproject.toml`, so runtime code imports generated constants instead of querying `importlib.metadata`.
- After updating project metadata (version, summary, URLs, authors) run `make test` (or `python -m scripts.test`) to regenerate the metadata module before committing.
- Tag releases `vX.Y.Z` and push tags; CI will build artifacts and publish when configured.

### Common Make Targets (Alphabetical)


| Target            | One-line description                                                           |
|-------------------|--------------------------------------------------------------------------------|
| `build`           | Build wheel/sdist artifacts.                                                    |
| `bump`            | Bump version (VERSION=X.Y.Z or PART=major\|minor\|patch) and update changelog. |
| `bump-major`      | Increment major version ((X+1).0.0).                                           |
| `bump-minor`      | Increment minor version (X.Y.Z → X.(Y+1).0).                                   |
| `bump-patch`      | Increment patch version (X.Y.Z → X.Y.(Z+1)).                                   |
| `clean`           | Remove caches, coverage, and build artifacts (includes `dist/` and `build/`).  |
| `dev`             | Install package with dev extras.                                               |
| `help`            | Show this table.                                                               |
| `install`         | Editable install.                                                              |
| `menu`            | Interactive TUI menu (make menu).                                              |
| `push`            | Commit changes once and push to GitHub (no CI monitoring).                     |
| `release`         | Tag vX.Y.Z, push, sync packaging, run gh release if available.                 |
| `run`             | Run module entry (`python -m ... --help`).                                     |
| `test`            | Lint, format, type-check, run tests with coverage, upload to Codecov.          |
| `version-current` | Print current version from `pyproject.toml`.                                   |


## Coding Style & Naming Conventions
  - apply python_clean_code.md


## Commit & Pull Request Guidelines

## Architecture Overview
  - apply python_clean_architecture.md

## Data Architecture Rules

This project follows strict data architecture rules using Pydantic models and Enums:

### Core Principles
1. **Pydantic at Boundaries**: All external data (API requests, file reads, env vars) is parsed into Pydantic models immediately upon entry
2. **Pydantic for Export**: All outputs use Pydantic's `.model_dump()` or `.model_dump_json()`
3. **No Internal Dicts**: Inside the application, never use raw dicts for structured data - use typed models
4. **Enums for Constants**: All string literals representing categories, statuses, or modes use Enums (prefer `IntEnum` for performance)
5. **Minimize Conversions**: Ideal flow is ONE parse at input, ONE dump at output

### Key Pydantic Models
- `GitHubRepository`, `GitHubWorkflow`, `GitHubWorkflowRun` - GitHub API responses
- `GitHubErrorResponse` - Error parsing with `from_response()` factory
- `PaginationLink` - Typed wrapper for pagination headers with `from_link_dict()` factory
- `EnvConfig` - Dynamic configuration with `__getattr__` for typed attribute access

### Enums
- `SkippedWorkflowType` (IntEnum) - Workflow types to skip during enablement

### Exceptions to Rules (Framework Requirements)
- `CLICK_CONTEXT_SETTINGS` dict - Required by Click framework API
- Pydantic `model_validator(mode="before")` returning dict - Required by Pydantic
- `sanitization.py` dict handling - Security utility designed for arbitrary dict sanitization

## Security & Configuration Tips
- `.env` is only for local tooling (CodeCov tokens, etc.); do not commit secrets.
- Rich logging should sanitize payloads before rendering once implemented.
- All logging calls use `sanitization.sanitize_message()` to prevent credential leakage.

## Translations (Docs)

## Translations (App UI Strings)

## Changes in WEB Documentation
- when asked to update documentation - only do that in the english docs under /website/docs because other languages will be translated automatically,
  unless stated otherwise by the user. In doubt - ask the user

## Changes in APP Strings
- when i18 strings are changed, only to that in sources/\_locales/en because other languages will be translated automatically,
  unless stated otherwise by the user. In doubt - ask the user

## commit/push/GitHub policy
- run "make test" before any push to avoid lint/test breakage.
- after push, monitor errors in the github actions and try to correct the errors
