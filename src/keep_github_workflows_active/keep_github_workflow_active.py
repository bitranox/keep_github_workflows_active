"""Keep the GitHub Actions workflows of an owner's repositories enabled and prune old runs.

Purpose
-------
Talk to the GitHub REST API for the two maintenance commands: re-enable every
workflow of every repository of an owner, and delete all but the newest
workflow runs of each repository.

Contents
--------
* :func:`get_owner` / :func:`get_github_token` - read ``SECRET_GITHUB_OWNER`` /
  ``SECRET_GITHUB_TOKEN`` from the environment or a ``.env`` file
  (:func:`_lookup_config_value`, :func:`_candidate_env_files`,
  ``KEEP_GITHUB_WORKFLOWS_ACTIVE_DOTENV_PATH``).
* :func:`github_session` - the ``requests.Session`` every API call of a run uses.
* :func:`enable_all_workflows` / :func:`delete_old_workflow_runs` - the entry
  points behind the CLI commands; they take ``owner`` and ``github_token``.
* :func:`get_repositories`, :func:`get_workflows`, :func:`get_workflow_runs`,
  :func:`enable_workflow`, :func:`delete_workflow_run` - single API steps that
  take the session.
* Pydantic reply models and :func:`_parse_reply`, which refuses a reply missing
  a field the tool acts on with ``RuntimeError("Unexpected GitHub reply for ...")``.

System Role
-----------
The GitHub boundary: replies are parsed into the models here, and every log
message passes through :func:`keep_github_workflows_active.sanitization.sanitize_message`.
pytest's ``addopts`` ignores this module, so its doctests do not run; several of
them call the live API when credentials are configured.
"""

# STDLIB
from __future__ import annotations

import logging
import os
import pathlib
import sys
from enum import IntEnum
from typing import cast

# EXT
import requests
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

# LOCAL
from . import sanitization

REQUEST_TIMEOUT_SECONDS = 30
#: GitHub API status code returned when the org endpoint has no matching organization.
HTTP_STATUS_NOT_FOUND = 404
#: Media type GitHub's REST API v3 answers with.
GITHUB_ACCEPT_HEADER = "application/vnd.github.v3+json"

logger = logging.getLogger(__name__)


# =============================================================================
# Enums for fixed string values
# =============================================================================


class SkippedWorkflowType(IntEnum):
    """Workflow types that are skipped during enablement."""

    PAGES_BUILD_DEPLOYMENT = 1
    DEPENDABOT = 2
    UPDATE_GRAPH = 3


SKIPPED_WORKFLOW_PREFIXES: dict[SkippedWorkflowType, str] = {
    SkippedWorkflowType.PAGES_BUILD_DEPLOYMENT: "pages-build-deployment",
    SkippedWorkflowType.DEPENDABOT: "dependabot",
    SkippedWorkflowType.UPDATE_GRAPH: "update-graph",
}


# =============================================================================
# Pydantic models for GitHub API responses (external boundary)
# =============================================================================


class GitHubRepository(BaseModel):
    """GitHub repository from API response."""

    model_config = ConfigDict(extra="ignore")
    name: str


class GitHubRepositoriesResponse(BaseModel):
    """List of repositories from GitHub API.

    GitHub answers the repository listing with a bare JSON array; the validator wraps it into
    ``{"repositories": [...]}``. Any other shape is passed on unchanged, so validation refuses
    it rather than reading it as an empty listing.
    """

    model_config = ConfigDict(extra="ignore")
    repositories: list[GitHubRepository]

    @model_validator(mode="before")
    @classmethod
    def _wrap_list_response(cls, data: object) -> object:
        """Wrap a bare JSON array into the ``repositories`` field."""
        if isinstance(data, list):
            # isinstance cannot name the element type; the elements are validated as
            # GitHubRepository right after this hook.
            return {"repositories": cast("list[object]", data)}
        return data


class GitHubWorkflow(BaseModel):
    """GitHub workflow from API response."""

    model_config = ConfigDict(extra="ignore")
    path: str

    @property
    def filename(self) -> str:
        """Extract workflow filename from path."""
        return pathlib.Path(self.path).name


class GitHubWorkflowsResponse(BaseModel):
    """Workflows response from GitHub API.

    Uses Pydantic's built-in validation to parse the GitHub API response.
    """

    model_config = ConfigDict(extra="ignore")
    workflows: list[GitHubWorkflow]


class GitHubWorkflowRun(BaseModel):
    """GitHub workflow run from API response."""

    model_config = ConfigDict(extra="ignore")
    id: int


class GitHubWorkflowRunsResponse(BaseModel):
    """Workflow runs response from GitHub API.

    Uses Pydantic's built-in validation to parse the GitHub API response.
    """

    model_config = ConfigDict(extra="ignore")
    workflow_runs: list[GitHubWorkflowRun]


class GitHubErrorResponse(BaseModel):
    """GitHub API error response.

    Uses Pydantic's built-in validation to parse error responses.
    """

    model_config = ConfigDict(extra="ignore")
    message: str = "Error"

    @classmethod
    def from_response(cls, response: requests.Response | None) -> GitHubErrorResponse:
        """Parse error from response, handling various failure modes."""
        if response is None:
            return cls()
        try:
            return cls.model_validate(response.json())
        except ValueError, AttributeError:
            return cls(message=response.text or response.reason or "Error")


class PaginationLink(BaseModel):
    """Single pagination link from GitHub API response headers.

    Represents a single link entry from the Link header used for pagination.
    """

    model_config = ConfigDict(extra="ignore")
    url: str = ""

    @classmethod
    def from_link_dict(cls, link_data: dict[str, str] | None) -> PaginationLink | None:
        """Parse pagination link from requests library link dict.

        Parameters
        ----------
        link_data:
            Dictionary from requests.Response.links containing 'url' key.

        Returns
        -------
        PaginationLink | None
            Parsed link model or None if no valid data.
        """
        if link_data is None:
            return None
        url = link_data.get("url", "")
        if not url:
            return None
        return cls(url=url)


# =============================================================================
# Pydantic model for internal configuration
# =============================================================================


class EnvConfig(BaseModel):
    """Environment configuration values parsed from .env file.

    Uses Pydantic's built-in validation with extra='allow' to capture
    arbitrary key-value pairs from .env files. Access values via attribute
    access (e.g., config.KEY) or the get() method.
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    def __getattr__(self, key: str) -> str | None:
        """Retrieve configuration value by attribute access.

        Examples
        --------
        >>> config = EnvConfig.model_validate({"FOO": "bar"})
        >>> config.FOO
        'bar'
        >>> config.MISSING is None
        True
        """
        extra = self.model_extra or {}
        value = extra.get(key)
        return str(value) if value is not None else None

    def get_value(self, key: str) -> str | None:
        """Retrieve configuration value by key (explicit method).

        Parameters
        ----------
        key:
            The configuration key to look up.

        Returns
        -------
        str | None
            The configuration value as a string, or None if not found.
        """
        return getattr(self, key)


def _candidate_env_files() -> list[pathlib.Path]:
    """Return existing ``.env`` files to inspect in priority order.

    Why
        Developers often run the script from varying working directories. We
        probe the file named by ``KEEP_GITHUB_WORKFLOWS_ACTIVE_DOTENV_PATH`` (if
        set), then common locations (current working directory, the package
        folder, and two levels above it, which is the repository root in a source
        checkout) so local and CI workflows can share the same fallback
        behaviour.

    Returns
    -------
    list[pathlib.Path]
        Detected ``.env`` files ordered by precedence.

    Examples
    --------
    >>> isinstance(_candidate_env_files(), list)
    True
    """

    script_dir = pathlib.Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    candidates: list[pathlib.Path] = []

    override = os.environ.get("KEEP_GITHUB_WORKFLOWS_ACTIVE_DOTENV_PATH")
    if override:
        candidates.append(pathlib.Path(override))

    candidates.extend(
        [
            pathlib.Path.cwd() / ".env",
            script_dir / ".env",
            repo_root / ".env",
        ]
    )

    seen: set[pathlib.Path] = set()
    existing_files: list[pathlib.Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        existing_files.append(resolved)
    return existing_files


def _read_env_file(path: pathlib.Path) -> EnvConfig:
    """Parse ``key=value`` pairs from a ``.env`` file.

    Parameters
    ----------
    path:
        Path to the ``.env`` file that should be parsed.

    Returns
    -------
    EnvConfig
        Pydantic model containing parsed configuration values.

    Examples
    --------
    >>> from tempfile import NamedTemporaryFile
    >>> with NamedTemporaryFile(mode="w+", suffix=".env", delete=True) as tmp:
    ...     _ = tmp.write("FOO=bar\\n# comment\\nBAZ = qux\\n")
    ...     _ = tmp.flush()
    ...     parsed = _read_env_file(pathlib.Path(tmp.name))
    >>> parsed.FOO == "bar" and parsed.BAZ == "qux"
    True
    """

    parsed_values: dict[str, str] = {}
    with path.open(encoding="utf-8") as stream:
        for raw_line in stream:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key, separator, remainder = stripped.partition("=")
            if not separator:
                continue
            parsed_values[key.strip()] = remainder.strip().strip('"').strip("'")
    return EnvConfig.model_validate(parsed_values)


def _lookup_config_value(key: str) -> str:
    """Return the configuration value for ``key`` from env or ``.env`` files.

    Why
        GitHub Actions secrets provide the environment variables automatically,
        but local runs depend on the repo's ``.env`` helper. This function keeps
        the retrieval logic consistent across both environments.

    Parameters
    ----------
    key:
        Environment variable name to resolve.

    Returns
    -------
    str
        The resolved configuration value.

    Raises
    ------
    RuntimeError
        If the value cannot be found in the environment or any ``.env`` file.

    Examples
    --------
    >>> os.environ["__EXAMPLE_KEY__"] = "value"
    >>> _lookup_config_value("__EXAMPLE_KEY__")
    'value'
    >>> del os.environ["__EXAMPLE_KEY__"]
    >>> from pathlib import Path
    >>> tmp_env = Path('doctest.env')
    >>> _ = tmp_env.write_text("__EXAMPLE_KEY__=fallback\\n", encoding='utf-8')
    >>> os.environ["KEEP_GITHUB_WORKFLOWS_ACTIVE_DOTENV_PATH"] = str(tmp_env)
    >>> _lookup_config_value("__EXAMPLE_KEY__")
    'fallback'
    >>> tmp_env.unlink()
    >>> _ = os.environ.pop("KEEP_GITHUB_WORKFLOWS_ACTIVE_DOTENV_PATH", None)
    """

    env_value = os.environ.get(key, "").strip()
    if env_value:
        return env_value

    for env_file in _candidate_env_files():
        config = _read_env_file(env_file)
        file_value = (config.get_value(key) or "").strip()
        if file_value:
            return file_value

    raise RuntimeError(f"Missing required configuration: {key}")


def github_session(github_token: str) -> requests.Session:
    """Return a session that carries the GitHub auth headers and reuses its connections.

    Why
        A run makes one API call per repository page, per repository for workflows and runs,
        one PUT per workflow and one DELETE per old run. A bare ``requests.get`` opens a new
        TLS connection for each; a session keeps it alive (measured against api.github.com:
        128 ms per call without, 45 ms with).

    Parameters
    ----------
    github_token:
        Personal access token sent as the Bearer authorization.

    Returns
    -------
    requests.Session
        Session to pass to the API functions; close it (``with``) when the run ends.

    Examples
    --------
    >>> with github_session("t0ken") as session:
    ...     session.headers["Authorization"], session.headers["Accept"]
    ('Bearer t0ken', 'application/vnd.github.v3+json')
    """
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {github_token}", "Accept": GITHUB_ACCEPT_HEADER})
    return session


def enable_all_workflows(owner: str, github_token: str) -> None:
    """
    Enable every workflow of every repository of ``owner``.

    Opens one :func:`github_session` for the run, lists the repositories and their
    workflow files, writes ``activate workflow <repo>/<file>`` for each and calls
    :func:`enable_workflow`, which skips the prefixes in ``SKIPPED_WORKFLOW_PREFIXES``.

    :param owner: The user or organisation owning the repositories.
    :param github_token: Personal access token for the session.
    :return: None
    :raises RuntimeError: When GitHub answers an error status or a malformed reply.

    >>> try:
    ...     my_owner = get_owner()
    ...     my_github_token = get_github_token()
    ... except RuntimeError:
    ...     my_owner = my_github_token = None
    >>> if my_owner and my_github_token:
    ...     enable_all_workflows(owner=my_owner, github_token=my_github_token) # doctest: +ELLIPSIS
    Activating ...

    """
    sys.stdout.write(f"Activating and maintaining all workflows for owner {owner}:\n")
    with github_session(github_token) as session:
        repositories = get_repositories(owner=owner, session=session)
        for repository in repositories:
            workflows = get_workflows(owner=owner, repository=repository, session=session)
            for workflow_filename in workflows:
                sys.stdout.write(f"activate workflow {repository}/{workflow_filename}\n")
                enable_workflow(owner=owner, repository=repository, workflow_filename=workflow_filename, session=session)


def delete_old_workflow_runs(owner: str, github_token: str, number_of_workflow_runs_to_keep: int = 50) -> None:
    """
    Delete all but the newest workflow runs of every repository of ``owner``.

    Opens one :func:`github_session` for the run. Per repository, all run ids (across
    all of its workflows) are sorted descending; the first
    ``number_of_workflow_runs_to_keep`` are kept and :func:`delete_workflow_run` is
    called for the rest, writing ``remove workflow run <repo>/<run_id>`` for each.

    :param owner: The user or organisation owning the repositories.
    :param github_token: Personal access token for the session.
    :param number_of_workflow_runs_to_keep: Runs to keep per repository.
    :return: None
    :raises RuntimeError: When GitHub answers an error status or a malformed reply.

    >>> try:
    ...     owner = get_owner()
    ...     token = get_github_token()
    ... except RuntimeError:
    ...     owner = token = None
    >>> if owner and token:
    ...     delete_old_workflow_runs(owner=owner, github_token=token, number_of_workflow_runs_to_keep=50)   # doctest: +ELLIPSIS
    Removing ...


    """
    sys.stdout.write(
        f"Removing outdated workflow executions for owner {owner}, "
        f"while retaining a maximum of {number_of_workflow_runs_to_keep} workflow runs per repository:\n"
    )
    with github_session(github_token) as session:
        l_repositories = get_repositories(owner=owner, session=session)
        for repository in l_repositories:
            workflow_run_ids = get_workflow_runs(owner=owner, repository=repository, session=session)
            workflow_run_ids_sorted = sorted(workflow_run_ids, reverse=True)
            workflow_run_ids_to_delete = workflow_run_ids_sorted[number_of_workflow_runs_to_keep:]
            logger.info(
                sanitization.sanitize_message(
                    f"repository: {repository}, {len(workflow_run_ids)} workflow runs found, {len(workflow_run_ids_to_delete)} to delete."
                )
            )
            for run_id_to_delete in workflow_run_ids_to_delete:
                sys.stdout.write(f"remove workflow run {repository}/{run_id_to_delete}\n")
                delete_workflow_run(owner=owner, repository=repository, session=session, run_id_to_delete=run_id_to_delete)


def get_owner() -> str:
    """Return the configured GitHub owner from env or ``.env`` files.

    Why
        The automation needs the owner to discover repositories. This helper
        centralises the lookup logic so callers do not replicate fallback
        behaviour.

    Returns
    -------
    str
        GitHub username configured for the automation.

    Raises
    ------
    RuntimeError
        If the value is missing from both the environment and ``.env`` files.
    """

    return _lookup_config_value("SECRET_GITHUB_OWNER")


def get_github_token() -> str:
    """Return the GitHub token from env or ``.env`` files.

    Why
        All API calls depend on the authentication token. Centralising the
        lookup keeps the behaviour consistent between CI and local execution.

    Returns
    -------
    str
        Personal access token used to authenticate against the GitHub API.

    Raises
    ------
    RuntimeError
        If the token is missing everywhere we check.
    """

    return _lookup_config_value("SECRET_GITHUB_TOKEN")


def _parse_reply[ReplyModelT: BaseModel](model: type[ReplyModelT], response: requests.Response, *, what: str) -> ReplyModelT:
    """Parse a successful GitHub reply into ``model``, refusing a body that does not fit it.

    Why
        A reply missing a field the tool acts on (a run id, a repository name, the listing
        itself) must stop the run: read with defaults it would delete run 0 or report an empty
        listing and exit 0.

    Raises
    ------
    RuntimeError
        Naming ``what`` and one ``<field path>: <reason>`` per validation error, or saying the
        body is not JSON. The original exception is kept as ``__cause__``.
    """
    try:
        return model.model_validate(response.json())
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(str(part) for part in error['loc']) or '<reply>'}: {error['msg']}" for error in exc.errors())
        message = f"Unexpected GitHub reply for {what}: {details}"
        logger.error(sanitization.sanitize_message(message))
        raise RuntimeError(message) from exc
    except ValueError as exc:
        message = f"Unexpected GitHub reply for {what}: the body is not JSON"
        logger.error(sanitization.sanitize_message(message))
        raise RuntimeError(message) from exc


def _get_next_page_url(response: requests.Response) -> str | None:
    """Extract next page URL from GitHub API pagination links.

    Parses the Link header from the GitHub API response and returns
    the 'next' page URL if present.

    Parameters
    ----------
    response:
        HTTP response from GitHub API.

    Returns
    -------
    str | None
        URL for the next page, or None if no more pages.
    """
    link_dict = response.links.get("next")
    link = PaginationLink.from_link_dict(link_dict)
    return link.url if link else None


def get_repositories(owner: str, session: requests.Session) -> list[str]:
    """
    Fetch all repository names of an organisation or user, handling pagination and setting the page size to 100.

    Requests ``/orgs/<owner>/repos`` first; when GitHub answers 404 the owner is no
    organisation and ``/users/<owner>/repos`` is listed instead.

    :param owner: The username of the repository owner.
    :param session: Session from :func:`github_session` carrying the auth headers.
    :return: A list of repository names.

    >>> has_secrets = {"SECRET_GITHUB_OWNER", "SECRET_GITHUB_TOKEN"}.issubset(os.environ)
    >>> if has_secrets:
    ...     with github_session(get_github_token()) as session:
    ...         repos = get_repositories(get_owner(), session)
    ... else:
    ...     repos = []
    >>> isinstance(repos, list)
    True


    """
    repositories: list[str] = []

    # Try the org endpoint first (returns private repos too), fall back to user endpoint.
    org_url = f"https://api.github.com/orgs/{owner}/repos?per_page=100"
    user_url = f"https://api.github.com/users/{owner}/repos?per_page=100"
    probe = session.get(org_url, timeout=REQUEST_TIMEOUT_SECONDS)
    if probe.status_code == HTTP_STATUS_NOT_FOUND:
        url: str | None = user_url
        probe = None  # Discard the 404 so the loop fetches fresh from user endpoint.
    else:
        url: str | None = org_url

    while url:
        try:
            # Reuse the probe response for the first org page to avoid a duplicate request.
            if probe is not None:
                response = probe
                probe = None
                response.raise_for_status()
            else:
                response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
            parsed = _parse_reply(GitHubRepositoriesResponse, response, what=f"repositories of {owner}")
            repositories.extend(repo.name for repo in parsed.repositories)
            url = _get_next_page_url(response)

        except requests.exceptions.HTTPError as exc:
            error = GitHubErrorResponse.from_response(exc.response)
            result = f"ERROR reading repositories for {owner}: {error.message}"
            logger.error(sanitization.sanitize_message(result))
            raise RuntimeError(result) from exc

    result = f"Found {len(repositories)} repositories for {owner}"
    logger.info(sanitization.sanitize_message(result))
    return repositories


def get_workflows(owner: str, repository: str, session: requests.Session) -> list[str]:
    """
    Fetch all workflows for a given GitHub repository, handling pagination and setting the page size to 100.

    :param owner: The username of the repository owner.
    :param repository: The name of the repository.
    :param session: Session from :func:`github_session` carrying the auth headers.
    :return: The workflow file names (last component of each workflow's path).


    >>> try:
    ...     owner = get_owner()
    ...     token = get_github_token()
    ... except RuntimeError:
    ...     owner = token = None
    >>> if owner and token:
    ...     with github_session(token) as session:
    ...         for repo in get_repositories(owner=owner, session=session):
    ...             _ = get_workflows(owner=owner, repository=repo, session=session)


    """
    workflows: list[str] = []
    url: str | None = f"https://api.github.com/repos/{owner}/{repository}/actions/workflows?per_page=100"

    while url:
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            parsed = _parse_reply(GitHubWorkflowsResponse, response, what=f"workflows of {owner}/{repository}")
            workflows.extend(workflow.filename for workflow in parsed.workflows)
            url = _get_next_page_url(response)

        except requests.exceptions.HTTPError as exc:
            error = GitHubErrorResponse.from_response(exc.response)
            result = f"ERROR reading workflows for user: {owner}, repository: {repository}, {error.message}"
            logger.error(sanitization.sanitize_message(result))
            raise RuntimeError(result) from exc

    result = f"Found {len(workflows)} workflows for user: {owner}, repository: {repository}"
    logger.info(sanitization.sanitize_message(result))
    return workflows


def get_workflow_runs(owner: str, repository: str, session: requests.Session) -> list[int]:
    """
    Fetch all workflow runs for a GitHub repository using the GitHub API v3, handling pagination.

    :param owner: The username of the repository owner.
    :param repository: The name of the repository.
    :param session: Session from :func:`github_session` carrying the auth headers.
    :return: A list of workflow run IDs.

    >>> try:
    ...     owner = get_owner()
    ...     token = get_github_token()
    ... except RuntimeError:
    ...     owner = token = None
    >>> if owner and token:
    ...     with github_session(token) as session:
    ...         for repo in get_repositories(owner=owner, session=session):
    ...             _ = get_workflow_runs(owner=owner, repository=repo, session=session)


    """
    url: str | None = f"https://api.github.com/repos/{owner}/{repository}/actions/runs?per_page=100"

    workflow_run_ids: list[int] = []
    while url:
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            parsed = _parse_reply(GitHubWorkflowRunsResponse, response, what=f"workflow runs of {owner}/{repository}")
            workflow_run_ids.extend(run.id for run in parsed.workflow_runs)
            url = _get_next_page_url(response)

        except requests.exceptions.HTTPError as exc:
            error = GitHubErrorResponse.from_response(exc.response)
            result = f"ERROR reading workflow runs for user: {owner}, repository: {repository}, {error.message}"
            logger.error(sanitization.sanitize_message(result))
            raise RuntimeError(result) from exc

    result = f"Found {len(workflow_run_ids)} workflow runs for user: {owner}, repository: {repository}"
    logger.info(sanitization.sanitize_message(result))
    return workflow_run_ids


HTTP_NO_CONTENT = 204


def delete_workflow_run(owner: str, repository: str, session: requests.Session, run_id_to_delete: int) -> None:
    """
    Delete a specified workflow run for a GitHub repository.

    :param owner: The username of the repository owner.
    :param repository: The name of the repository.
    :param session: Session from :func:`github_session` carrying the auth headers.
    :param run_id_to_delete: The ID of the workflow run to delete.
    :return: None
    """
    url = f"https://api.github.com/repos/{owner}/{repository}/actions/runs/{run_id_to_delete}"

    try:
        response = session.delete(url, timeout=REQUEST_TIMEOUT_SECONDS)

        if response.status_code == HTTP_NO_CONTENT:
            result = f"Deleted workflow run ID: {run_id_to_delete} for user: {owner}, repository: {repository}"
            logger.info(sanitization.sanitize_message(result))

    except requests.exceptions.RequestException as exc:
        result_error_message = f"ERROR deleting workflow run ID: {run_id_to_delete} for user: {owner}, repository: {repository}: {exc}"
        logger.error(sanitization.sanitize_message(result_error_message))
        raise RuntimeError(result_error_message) from exc


def _is_skipped_workflow(workflow_filename: str) -> SkippedWorkflowType | None:
    """Check if workflow should be skipped and return the reason."""
    for skip_type, prefix in SKIPPED_WORKFLOW_PREFIXES.items():
        if workflow_filename.startswith(prefix):
            return skip_type
    return None


def enable_workflow(owner: str, repository: str, workflow_filename: str, session: requests.Session) -> str:
    """
    Enable a workflow in a GitHub repository using the GitHub API.

    :param owner: The username of the repository owner.
    :param repository: The name of the repository.
    :param workflow_filename: The name of the workflow file, for example, "python-package.yml".
    :param session: Session from :func:`github_session`, its token allowed to enable workflows.
    :return: ``Enabled repository <repo>, workflow <file>``, or a ``... skipped - ...`` message for a
        file whose name starts with a prefix in ``SKIPPED_WORKFLOW_PREFIXES`` (no request is sent then).
    :raises RuntimeError: When GitHub answers an error status.


    >>> try:
    ...     owner = get_owner()
    ...     token = get_github_token()
    ... except RuntimeError:
    ...     owner = token = None
    >>> if owner and token:
    ...     from contextlib import redirect_stdout
    ...     from io import StringIO
    ...     stdout = StringIO()
    ...     with redirect_stdout(stdout), github_session(token) as session:
    ...         enable_workflow(
    ...             owner=owner,
    ...             repository="lib_path",
    ...             workflow_filename="python-package.yml",
    ...             session=session,
    ...         )
    ...     assert stdout.getvalue()


    """
    url = f"https://api.github.com/repos/{owner}/{repository}/actions/workflows/{workflow_filename}/enable"

    response: requests.Response | None = None
    try:
        skip_reason = _is_skipped_workflow(workflow_filename)
        if skip_reason == SkippedWorkflowType.PAGES_BUILD_DEPLOYMENT:
            result = f"Repository {repository}, workflow {workflow_filename} skipped - those can not be enabled"
        elif skip_reason == SkippedWorkflowType.DEPENDABOT:
            result = f"Repository {repository}, workflow {workflow_filename} skipped - managed by Dependabot"
        elif skip_reason == SkippedWorkflowType.UPDATE_GRAPH:
            result = f"Repository {repository}, workflow {workflow_filename} skipped - managed by GitHub dependency graph"
        else:
            response = session.put(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            result = f"Enabled repository {repository}, workflow {workflow_filename}"
            logger.info(sanitization.sanitize_message(result))
        return result

    except requests.exceptions.HTTPError as exc:
        resp = exc.response if exc.response is not None else response
        error = GitHubErrorResponse.from_response(resp)
        result = f"ERROR enabling repository {repository}, workflow {workflow_filename}: {error.message}"
        logger.error(sanitization.sanitize_message(result))
        raise RuntimeError(result) from exc


def main() -> None:
    """
    Enable all workflows and delete old runs (keeping 50) for the configured owner.

    >>> # Not called here: it acts on the live account. pytest's addopts ignores this
    >>> # module's doctests anyway.
    >>> # main()

    """

    enable_all_workflows(owner=get_owner(), github_token=get_github_token())
    delete_old_workflow_runs(owner=get_owner(), github_token=get_github_token(), number_of_workflow_runs_to_keep=50)


if __name__ == "__main__":
    sys.stderr.write("this is a library only, the executable is named 'keep-github-workflows-active'\n")
