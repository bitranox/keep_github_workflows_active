# Changelog

## [2.1.1] - 2025-12-08

### Changed
- **Data Architecture Enforcement**: Refactored to follow strict Pydantic/Enum architecture rules.
  - `EnvConfig` now uses `__getattr__` for typed attribute access instead of dict-style `.get()` method
  - Added `PaginationLink` Pydantic model for typed pagination header handling
  - Replaced dict key access (`response.links.get("next")`) with typed model access (`link.url`)
  - Added `get_value()` method to `EnvConfig` for explicit key lookup

### Dependencies
- Added `pydantic>=2.10.0` as a runtime dependency for typed data models

### Documentation
- Updated `CLAUDE.md` with Data Architecture Rules section documenting:
  - Core principles (Pydantic at boundaries, no internal dicts, Enums for constants)
  - Key Pydantic models and Enums used in the project
  - Framework exceptions where dict usage is required
- Fixed incorrect path reference in Versioning section (`lib_cli_exit_tools` → `keep_github_workflows_active`)

## [2.1.0] - 2025-10-29
### Security
- **Added comprehensive credential sanitization** to prevent token leakage in logs.
  - New `sanitization` module with functions to redact sensitive data
  - All logging calls now sanitize messages before output
  - Protects GitHub tokens (ghp_*, gho_*, etc.), API keys, and authorization headers
  - Token pattern detection using regex for various formats (hex, base64, GitHub-specific)
  - Dictionary and nested structure sanitization for structured logging
  - 100% test coverage with 31 dedicated tests
  - Comprehensive security documentation in `docs/systemdesign/SECURITY.md`

## [2.0.0] - 2025-10-23
### Changed
- Removed pre-3.13 compatibility shims and migrated internal modules to native
  Python 3.13 type syntax (e.g., ``list[str]`` and ``Sequence[str] | None``).
- Hardened GitHub token discovery by falling back to project ``.env`` files
  when environment variables are unset.
- Surfaced workflow maintenance helpers as CLI commands
  (``enable-all-workflows`` and ``delete-old-workflow-runs``) with optional
  override parameters.
- Added explicit HTTP timeouts to GitHub workflow maintenance calls to avoid
  hanging requests.
- Simplified CI matrix to run only on ``ubuntu-latest`` with the rolling
  ``3.x`` CPython release.
- Updated CI packaging checks to execute the CLI from the pipx binary directory
  and via ``uv tool install --from dist/*.whl`` to confirm the built wheel
  exposes the console entry point correctly.
- Refined packaging verification to leverage the pipx binary directory and
  install the local wheel via ``uv tool install --from dist/*.whl``.
- Corrected the CI pipeline to use the current ``astral-sh/setup-uv@v6`` action
  tag.

### Dependencies
- Bumped ``ruff`` to ``>=0.14.1`` and ``textual`` to ``>=6.4.0``.
- Declared ``requests`` as a runtime dependency to support GitHub API calls when
  the package is installed.
