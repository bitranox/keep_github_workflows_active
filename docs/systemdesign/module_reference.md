# Module Reference

## Scope

What each module in `src/keep_github_workflows_active/` does, its public functions with their
signatures, and how the CLI reaches them.

**Related files:**

* src/keep_github_workflows_active/keep_github_workflow_active.py
* src/keep_github_workflows_active/sanitization.py
* src/keep_github_workflows_active/cli.py
* src/keep_github_workflows_active/typed_click.py
* src/keep_github_workflows_active/behaviors.py
* src/keep_github_workflows_active/__main__.py
* src/keep_github_workflows_active/__init__.py
* src/keep_github_workflows_active/__init__conf__.py
* tests/ (test_github_api.py, test_github_integration.py, test_sanitization.py, test_cli.py,
  test_module_entry.py, test_behaviors.py, test_metadata.py, test_packaging.py,
  test_platform_markers.py, conftest.py)

---

## Architecture Integration

**Layering:** `cli.py` is the transport adapter. It calls `keep_github_workflow_active` for the
two maintenance commands and `behaviors` for the diagnostic commands. import-linter enforces the
contract "CLI depends on behaviors only" (`[tool.importlinter]`): `cli` sits above `behaviors`.
GitHub's replies enter as Pydantic models at the boundary in `keep_github_workflow_active`; every
log message from that module passes through `sanitization.sanitize_message()`.

**Data flow of a maintenance command:**

1. rich-click parses the options (`--owner`, `--token`, `--keep`).
2. `_fallback_owner` / `_fallback_token` fill a missing option from `get_owner()` /
   `get_github_token()`; a missing value becomes a `click.ClickException`
   (`Missing required configuration: <KEY>`).
3. `enable_all_workflows` or `delete_old_workflow_runs` opens one `requests.Session` with
   `github_session()` and passes it to the listing, enable and delete functions.
4. Every reply is parsed by `_parse_reply` into a model; a reply that does not fit raises
   `RuntimeError`.
5. `lib_cli_exit_tools` renders any exception and maps it to the exit code.

**Runtime dependencies:** `rich-click`, `lib_cli_exit_tools`, `requests`, `pydantic`.

---

## keep_github_workflow_active.py

### Configuration

| Name                                       | Meaning                                                              |
|--------------------------------------------|----------------------------------------------------------------------|
| `SECRET_GITHUB_OWNER`                      | user or organisation whose repositories are processed                |
| `SECRET_GITHUB_TOKEN`                      | personal access token, sent as `Authorization: Bearer <token>`       |
| `KEEP_GITHUB_WORKFLOWS_ACTIVE_DOTENV_PATH` | optional path of a `.env` file searched before the default locations |

* `get_owner() -> str` and `get_github_token() -> str` return
  `_lookup_config_value("SECRET_GITHUB_OWNER")` / `("SECRET_GITHUB_TOKEN")`.
* `_lookup_config_value(key: str) -> str`: the stripped environment variable if non-empty,
  otherwise the first non-empty value in the files from `_candidate_env_files()`; raises
  `RuntimeError("Missing required configuration: <key>")`.
* `_candidate_env_files() -> list[pathlib.Path]`: existing files, de-duplicated, in this order:
  `$KEEP_GITHUB_WORKFLOWS_ACTIVE_DOTENV_PATH`, `<cwd>/.env`, `<package dir>/.env`,
  `<package dir>/../../.env`.
* `_read_env_file(path: pathlib.Path) -> EnvConfig`: `KEY=value` lines; skips blank lines, lines
  starting with `#` and lines without `=`; strips surrounding quotes from values.
* `EnvConfig` (Pydantic, `extra="allow"`, frozen): attribute access and `get_value(key) -> str | None`
  return the value as `str`, or `None` when absent.

### Session

* `github_session(github_token: str) -> requests.Session`: a session whose headers carry
  `Authorization: Bearer <token>` and `Accept: application/vnd.github.v3+json`
  (`GITHUB_ACCEPT_HEADER`). Use it as a `with` block; the two entry points do.

### Entry points

* `enable_all_workflows(owner: str, github_token: str) -> None`: writes
  `Activating and maintaining all workflows for owner <owner>:` to stdout, then for every
  repository and every workflow file writes `activate workflow <repo>/<file>` and calls
  `enable_workflow`.
* `delete_old_workflow_runs(owner: str, github_token: str, number_of_workflow_runs_to_keep: int = 50) -> None`:
  for every repository, sorts all run ids descending, keeps the first
  `number_of_workflow_runs_to_keep` and calls `delete_workflow_run` for the rest, writing
  `remove workflow run <repo>/<run_id>` to stdout for each.
* `main() -> None`: runs both entry points for the configured owner and token (keeping 50 runs).

### Single-step API functions

All take a session from `github_session()`, read lists with `per_page=100` and follow the `next`
link of the `Link` header (`_get_next_page_url(response) -> str | None`). Requests time out after
`REQUEST_TIMEOUT_SECONDS` (30).

* `get_repositories(owner: str, session: requests.Session) -> list[str]`: repository names.
  Requests `/orgs/<owner>/repos` first; on 404 lists `/users/<owner>/repos` instead.
* `get_workflows(owner: str, repository: str, session: requests.Session) -> list[str]`: the file
  names (last path component) of the repository's workflows.
* `get_workflow_runs(owner: str, repository: str, session: requests.Session) -> list[int]`: the
  run ids of all the repository's workflow runs.
* `enable_workflow(owner: str, repository: str, workflow_filename: str, session: requests.Session) -> str`:
  sends `PUT .../actions/workflows/<file>/enable` and returns `Enabled repository <repo>, workflow <file>`.
  File names starting with a prefix in `SKIPPED_WORKFLOWS` (`pages-build-deployment`,
  `dependabot`, `update-graph`; enum `SkippedWorkflowType`) send no request and return a
  `... skipped - ...` message.
* `delete_workflow_run(owner: str, repository: str, session: requests.Session, run_id_to_delete: int) -> None`:
  sends `DELETE .../actions/runs/<run_id>` and logs `Deleted workflow run ID ...` on 204.

**Errors:** an HTTP error status in the listing functions or `enable_workflow` raises
`RuntimeError("ERROR reading ...")` / `RuntimeError("ERROR enabling ...")`, with GitHub's error
`message` parsed by `GitHubErrorResponse.from_response`. A `requests.RequestException` in
`delete_workflow_run` raises `RuntimeError("ERROR deleting workflow run ID ...")`.

### Reply models (Pydantic, `extra="ignore"`)

| Model                        | Required fields                                                                           |
|------------------------------|-------------------------------------------------------------------------------------------|
| `GitHubRepository`           | `name: str`                                                                               |
| `GitHubRepositoriesResponse` | `repositories: list[GitHubRepository]`; a bare JSON array is wrapped into this field      |
| `GitHubWorkflow`             | `path: str` (property `filename`)                                                         |
| `GitHubWorkflowsResponse`    | `workflows: list[GitHubWorkflow]`                                                         |
| `GitHubWorkflowRun`          | `id: int`                                                                                 |
| `GitHubWorkflowRunsResponse` | `workflow_runs: list[GitHubWorkflowRun]`                                                  |
| `GitHubErrorResponse`        | `message: str = "Error"`; `from_response(response)` falls back to the body text or reason |
| `PaginationLink`             | `url: str = ""`; `from_link_dict(link_data)` returns `None` without a URL                 |

`_parse_reply(model, response, *, what: str)` validates a successful reply against `model`. A
reply that does not fit raises `RuntimeError("Unexpected GitHub reply for <what>: <field path>: <reason>")`
(one `<field path>: <reason>` per validation error, joined with `; `), or
`RuntimeError("Unexpected GitHub reply for <what>: the body is not JSON")`; the message is also
logged, and the original exception is kept as `__cause__`.

---

## sanitization.py

Pure functions; each returns a sanitized copy and leaves its input unchanged.

* `sanitize_message(text: str) -> str`: replaces every match of `TOKEN_PATTERN` with
  `REDACTED_PLACEHOLDER` (`"[REDACTED]"`).
* `sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]`: redacts the value of every
  header whose lower-cased name is in `SENSITIVE_HEADERS`.
* `sanitize_dict(data: Mapping[str, Any]) -> dict[str, Any]`: redacts values whose lower-cased key
  is in `SENSITIVE_KEYS` or `SENSITIVE_HEADERS`, recurses into nested mappings and scrubs other
  string values with `sanitize_message`.
* `sanitize_for_logging(value: Any) -> Any`: `sanitize_dict` for mappings, `sanitize_message` for
  strings, other values unchanged.

Details and the pattern: [SECURITY.md](SECURITY.md).

---

## cli.py

Root group `cli` (rich-click) with `--version`, `--traceback/--no-traceback` and `-h/--help`.
Without a subcommand it prints the help; with only `--traceback`/`--no-traceback` it runs
`cli_main()` (which calls `behaviors.noop_main`).

| Command                    | Function                       | Options                                                            | Calls                                                  |
|----------------------------|--------------------------------|--------------------------------------------------------------------|--------------------------------------------------------|
| `enable-all-workflows`     | `cli_enable_all_workflows`     | `--owner OWNER`, `--token TOKEN`                                   | `keep_github_workflow_active.enable_all_workflows`     |
| `delete-old-workflow-runs` | `cli_delete_old_workflow_runs` | `--owner OWNER`, `--token TOKEN`, `--keep COUNT` (int, default 50) | `keep_github_workflow_active.delete_old_workflow_runs` |
| `info`                     | `cli_info`                     | none                                                               | `__init__conf__.print_info`                            |
| `hello`                    | `cli_hello`                    | none                                                               | `behaviors.emit_greeting`                              |
| `fail`                     | `cli_fail`                     | none                                                               | `behaviors.raise_intentional_failure`                  |

Other functions:

* `main(argv: Sequence[str] | None = None, *, restore_traceback: bool = True, summary_limit: int = 500, verbose_limit: int = 10_000) -> int`:
  the entry point of both console scripts and of `python -m`. Runs the group through
  `lib_cli_exit_tools.run_cli`, renders an exception with `lib_cli_exit_tools` (truncated to
  `summary_limit` characters, or `verbose_limit` with `--traceback`) and returns the exit code.
  With `restore_traceback` it restores the previous traceback configuration afterwards.
* `apply_traceback_preferences(*, enabled: bool) -> None`, `snapshot_traceback_state() -> TracebackState`,
  `restore_traceback_state(state: TracebackState) -> None`: read and set
  `lib_cli_exit_tools.config.traceback` and `traceback_force_color`.
* `_fallback_owner(owner: str | None) -> str`, `_fallback_token(token: str | None) -> str`: the
  option value, or the configured one; a `RuntimeError` from the lookup becomes a
  `click.ClickException`.
* `CliContextObject`: dataclass stored in `ctx.obj`, holding the `traceback` flag.
* `CLICK_CONTEXT_SETTINGS`: `{"help_option_names": ["-h", "--help"]}`.

---

## typed_click.py

* `option(*param_decls: str, **attrs: Any) -> _CommandDecorator` and
  `version_option(*param_decls: str, **attrs: Any) -> _CommandDecorator`: forward to
  `rich_click.option` / `rich_click.version_option` (so rich-click's option classes are used at
  runtime) through a typed `Protocol`, so pyright strict sees complete types at every call site.

---

## behaviors.py

Diagnostic helpers behind `hello`, `fail` and the no-subcommand path:

* `emit_greeting(*, stream: TextIO | None = None) -> None`: writes `CANONICAL_GREETING`
  (`"Hello World"`) and a newline to `stream` (default `sys.stdout`) and flushes it.
* `raise_intentional_failure() -> None`: raises `RuntimeError("I should fail")`.
* `noop_main() -> None`: does nothing.

---

## __main__.py

`python -m keep_github_workflows_active` runs `raise SystemExit(cli.main())`, so it behaves like
the console scripts.

---

## __init__.py

Re-exports `CANONICAL_GREETING`, `emit_greeting`, `noop_main`, `raise_intentional_failure` and
`print_info`. The GitHub functions are imported from
`keep_github_workflows_active.keep_github_workflow_active`.

---

## __init__conf__.py

Plain constants (`name`, `title`, `version`, `homepage`, `author`, `author_email`,
`shell_command`) that bmk rewrites from `pyproject.toml`, and `print_info() -> None`, which writes
them for the `info` command.

---

## Testing

* `tests/test_github_api.py`: the GitHub functions against stub replies, including the refusal
  of malformed replies.
* `tests/test_github_integration.py`: live GitHub API; marked `integration` and `local_only`, run
  by `make testintegration`, skipped when `CI` is set.
* `tests/test_sanitization.py`: the sanitization functions and constants.
* `tests/test_cli.py`, `tests/test_module_entry.py`: the CLI through `CliRunner`, `main()` and
  `python -m`, including traceback handling.
* `tests/test_behaviors.py`, `tests/test_metadata.py`: the diagnostic helpers and metadata.
* `tests/test_packaging.py`: builds the sdist and wheel and checks their contents.
* Doctests in the modules run with `--doctest-modules`, except those of
  `keep_github_workflow_active.py`: `addopts` ignores that module, and several of its doctests
  call the live API when credentials are configured.

**Manual checks:**

1. `keep-github-workflows-active` prints the help.
2. `keep-github-workflows-active hello` prints `Hello World`.
3. `keep-github-workflows-active fail` prints `RuntimeError: I should fail` and exits 1.
4. `keep-github-workflows-active --traceback fail` prints the full traceback.
5. `python -m keep_github_workflows_active --traceback fail` gives the same output.
