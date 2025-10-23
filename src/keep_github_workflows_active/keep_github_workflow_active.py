# STDLIB
from __future__ import annotations

import logging
import os
import pathlib
import sys

# EXT
import requests

REQUEST_TIMEOUT_SECONDS = 30

logger = logging.getLogger(__name__)


def _candidate_env_files() -> list[pathlib.Path]:
    """Return existing ``.env`` files to inspect in priority order.

    Why
        Developers often run the script from varying working directories. We
        probe common locations (current working directory, the package folder,
        and the repository root) so local and CI workflows can share the same
        fallback behaviour.

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
    repo_root = script_dir.parent
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


def _read_env_file(path: pathlib.Path) -> dict[str, str]:
    """Parse ``key=value`` pairs from a ``.env`` file.

    Parameters
    ----------
    path:
        Path to the ``.env`` file that should be parsed.

    Returns
    -------
    dict[str, str]
        Mapping of keys to values discovered in the file.

    Examples
    --------
    >>> from tempfile import NamedTemporaryFile
    >>> with NamedTemporaryFile(mode="w+", suffix=".env", delete=True) as tmp:
    ...     _ = tmp.write("FOO=bar\\n# comment\\nBAZ = qux\\n")
    ...     _ = tmp.flush()
    ...     parsed = _read_env_file(pathlib.Path(tmp.name))
    >>> parsed == {"FOO": "bar", "BAZ": "qux"}
    True
    """

    values: dict[str, str] = {}
    with path.open(encoding="utf-8") as stream:
        for raw_line in stream:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key, separator, remainder = stripped.partition("=")
            if not separator:
                continue
            values[key.strip()] = remainder.strip().strip('"').strip("'")
    return values


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

    env_value = os.environ.get(key)
    if env_value:
        return env_value

    for env_file in _candidate_env_files():
        config = _read_env_file(env_file)
        file_value = config.get(key)
        if file_value:
            return file_value

    raise RuntimeError(f"Missing required configuration: {key}")


def enable_all_workflows(owner: str, github_token: str) -> None:
    """
    :param owner: the repo owner
    :param github_token:
    :return:

    >>> try:
    ...     my_owner = get_owner()
    ...     my_github_token = get_github_token()
    ... except RuntimeError:
    ...     my_owner = my_github_token = None
    >>> if my_owner and my_github_token:
    ...     from contextlib import redirect_stdout
    ...     from io import StringIO
    ...     stdout = StringIO()
    ...     with redirect_stdout(stdout):
    ...         enable_all_workflows(owner=my_owner, github_token=my_github_token)
    ...     assert stdout.getvalue()

    """
    print(f"Activating and maintaining all workflows for owner {owner}:")
    repositories = get_repositories(owner=owner, github_token=github_token)
    for repository in repositories:
        workflows = get_workflows(owner=owner, repository=repository, github_token=github_token)
        for workflow_filename in workflows:
            print(f"activate workflow {repository}/{workflow_filename}")
            enable_workflow(owner=owner, repository=repository, workflow_filename=workflow_filename, github_token=github_token)


def delete_old_workflow_runs(owner: str, github_token: str, number_of_workflow_runs_to_keep: int = 50) -> None:
    """
    :param owner:
    :param github_token:
    :param number_of_workflow_runs_to_keep:
    :return:

    >>> try:
    ...     owner = get_owner()
    ...     token = get_github_token()
    ... except RuntimeError:
    ...     owner = token = None
    >>> if owner and token:
    ...     from contextlib import redirect_stdout
    ...     from io import StringIO
    ...     stdout = StringIO()
    ...     with redirect_stdout(stdout):
    ...         delete_old_workflow_runs(owner=owner, github_token=token, number_of_workflow_runs_to_keep=50)
    ...     assert stdout.getvalue()

    """
    print(
        f"Removing outdated workflow executions for owner {owner}, while retaining a maximum of {number_of_workflow_runs_to_keep} workflow runs per repository:"
    )
    l_repositories = get_repositories(owner=owner, github_token=github_token)
    for repository in l_repositories:
        workflow_run_ids = get_workflow_runs(owner=owner, repository=repository, github_token=github_token)
        workflow_run_ids_sorted = sorted(workflow_run_ids, reverse=True)
        workflow_run_ids_to_delete = workflow_run_ids_sorted[number_of_workflow_runs_to_keep:]
        logger.info(f"repository: {repository}, {len(workflow_run_ids)} workflow runs found, {len(workflow_run_ids_to_delete)} to delete.")
        for run_id_to_delete in workflow_run_ids_to_delete:
            print(f"remove workflow run {repository}/{run_id_to_delete}")
            delete_workflow_run(owner=owner, repository=repository, github_token=github_token, run_id_to_delete=run_id_to_delete)


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

    Examples
    --------
    >>> os.environ["SECRET_GITHUB_OWNER"] = "demo-user"
    >>> get_owner()
    'demo-user'
    >>> _ = os.environ.pop("SECRET_GITHUB_OWNER")
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

    Examples
    --------
    >>> os.environ["SECRET_GITHUB_TOKEN"] = "abc123"
    >>> get_github_token()
    'abc123'
    >>> _ = os.environ.pop("SECRET_GITHUB_TOKEN")
    """

    return _lookup_config_value("SECRET_GITHUB_TOKEN")


def get_repositories(owner: str, github_token: str) -> list[str]:
    """
    Fetch all repositories for a given GitHub user, handling pagination and setting the page size to 100.

    :param owner: The username of the repository owner.
    :param github_token: A personal access token for GitHub API authentication.
    :return: A list of repository names.

    >>> has_secrets = {"SECRET_GITHUB_OWNER", "SECRET_GITHUB_TOKEN"}.issubset(os.environ)
    >>> if has_secrets:
    ...     repos = get_repositories(get_owner(), get_github_token())
    ... else:
    ...     repos = []
    >>> isinstance(repos, list)
    True


    """
    repositories: list[str] = []
    url = f"https://api.github.com/users/{owner}/repos?per_page=100"
    headers = {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github.v3+json"}

    while url:
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()  # Raises HTTPError for bad responses
            data = response.json()
            repositories.extend([repo["name"] for repo in data])

            # Get the URL for the next page from the response headers, if present
            url = response.links.get("next", {}).get("url", None)

        except requests.exceptions.HTTPError as exc:
            error_message = exc.response.json().get("message", "Error")
            result = f"ERROR reading repositories for user {owner}: {error_message}"
            logger.error(result)
            raise RuntimeError(result) from exc

    result = f"Found {len(repositories)} repositories for user {owner}"
    logger.info(result)
    return repositories


def get_workflows(owner: str, repository: str, github_token: str) -> list[str]:
    """
    Fetch all workflows for a given GitHub repository, handling pagination and setting the page size to 100.

    :param owner: The username of the repository owner.
    :param repository: The name of the repository.
    :param github_token: A personal access token for GitHub API authentication.
    :return: A list of workflow names.


    >>> try:
    ...     owner = get_owner()
    ...     token = get_github_token()
    ... except RuntimeError:
    ...     owner = token = None
    >>> if owner and token:
    ...     repos = get_repositories(owner=owner, github_token=token)
    ...     for repo in repos:
    ...         _ = get_workflows(owner=owner, repository=repo, github_token=token)


    """
    workflows: list[str] = []
    url = f"https://api.github.com/repos/{owner}/{repository}/actions/workflows?per_page=100"
    headers = {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github.v3+json"}

    while url:
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()  # Raises HTTPError for bad responses
            data = response.json()
            workflows.extend([pathlib.Path(workflow["path"]).name for workflow in data.get("workflows", [])])

            # Get the URL for the next page from the response headers, if present
            url = response.links.get("next", {}).get("url", None)

        except requests.exceptions.HTTPError as exc:
            error_message = exc.response.json().get("message", "Error")
            result = f"ERROR reading workflows for user: {owner}, repository: {repository}, {error_message}"
            logger.error(result)
            raise RuntimeError(result) from exc

    result = f"Found {len(workflows)} workflows for user: {owner}, repository: {repository}"
    logger.info(result)
    return workflows


def get_workflow_runs(owner: str, repository: str, github_token: str) -> list[str]:
    """
    Fetch all workflow runs for a GitHub repository using the GitHub API v3, handling pagination.

    :param owner: The username of the repository owner.
    :param repository: The name of the repository.
    :param github_token: A GitHub personal access token for authentication.
    :return: A list of workflow run IDs.

    >>> try:
    ...     owner = get_owner()
    ...     token = get_github_token()
    ... except RuntimeError:
    ...     owner = token = None
    >>> if owner and token:
    ...     repos = get_repositories(owner=owner, github_token=token)
    ...     for repo in repos:
    ...         _ = get_workflow_runs(owner=owner, repository=repo, github_token=token)


    """
    # set pagination to 100 (the maximum at GitHub), to have fewer requests
    url = f"https://api.github.com/repos/{owner}/{repository}/actions/runs?per_page=100"
    headers = {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github.v3+json"}

    workflow_run_ids: list[str] = []
    while url:
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()  # Raises an HTTPError if the response was an error

            # Process response data
            data = response.json()
            workflow_run_ids.extend([run["id"] for run in data.get("workflow_runs", [])])

            # Check for the 'next' page link
            url = response.links.get("next", {}).get("url", None)

        except requests.exceptions.HTTPError as exc:
            result_error_message = exc.response.json().get("message", "Error")
            result = f"ERROR reading workflow runs for user: {owner}, repository: {repository}, {result_error_message}"
            logger.error(result)
            raise RuntimeError(result) from exc

    result = f"Found {len(workflow_run_ids)} workflow runs for user: {owner}, repository: {repository}"
    logger.info(result)
    return workflow_run_ids


def delete_workflow_run(owner: str, repository: str, github_token: str, run_id_to_delete: str) -> None:
    """
    Delete a specified workflow run for a GitHub repository.

    :param owner: The username of the repository owner.
    :param repository: The name of the repository.
    :param github_token: A personal access token for GitHub API authentication.
    :param run_id_to_delete: The ID of the workflow run to delete.
    :return: None
    """
    url = f"https://api.github.com/repos/{owner}/{repository}/actions/runs/{run_id_to_delete}"
    headers = {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github.v3+json"}

    try:
        response = requests.delete(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)

        if response.status_code == 204:
            result = f"Deleted workflow run ID: {run_id_to_delete} for user: {owner}, repository: {repository}"
            logger.info(result)

    except requests.exceptions.RequestException as exc:
        # For HTTP errors, requests will raise a RequestException. Here we catch all errors derived from RequestException
        result_error_message = f"ERROR deleting workflow run ID: {run_id_to_delete} for user: {owner}, repository: {repository}: {exc}"
        logger.error(result_error_message)
        raise RuntimeError(result_error_message) from exc


def enable_workflow(owner: str, repository: str, workflow_filename: str, github_token: str) -> str:
    """
    Enable a workflow in a GitHub repository using the GitHub API.

    :param owner: The username of the repository owner.
    :param repository: The name of the repository.
    :param workflow_filename: The name of the workflow file, for example, "python-package.yml".
    :param github_token: A GitHub access token with permissions to enable workflows.
    :return: A success message if the workflow is enabled.


    >>> try:
    ...     owner = get_owner()
    ...     token = get_github_token()
    ... except RuntimeError:
    ...     owner = token = None
    >>> if owner and token:
    ...     from contextlib import redirect_stdout
    ...     from io import StringIO
    ...     stdout = StringIO()
    ...     with redirect_stdout(stdout):
    ...         enable_workflow(
    ...             owner=owner,
    ...             repository="lib_path",
    ...             workflow_filename="python-package.yml",
    ...             github_token=token,
    ...         )
    ...     assert stdout.getvalue()


    """
    url = f"https://api.github.com/repos/{owner}/{repository}/actions/workflows/{workflow_filename}/enable"

    headers = {"Accept": "application/vnd.github.v3+json", "Authorization": f"Bearer {github_token}"}

    response: requests.Response | None = None
    try:
        if workflow_filename.startswith("pages-build-deployment"):
            result = f"Repository {repository}, workflow {workflow_filename} skipped - those can not be enabled"
        elif workflow_filename.startswith("dependabot"):
            result = f"Repository {repository}, workflow {workflow_filename} skipped - managed by Dependabot"
        else:
            response = requests.put(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()  # This will raise an exception for HTTP error codes
            result = f"Enabled repository {repository}, workflow {workflow_filename}"
            logger.info(result)
        return result

    except requests.exceptions.HTTPError as exc:
        resp = exc.response if exc.response is not None else response
        if resp is not None:
            try:
                error_message = resp.json().get("message", "Error")
            except ValueError:
                error_message = resp.text or resp.reason or "Error"
        else:
            error_message = str(exc)
        result = f"ERROR enabling repository {repository}, workflow {workflow_filename}: {error_message}"
        logger.error(result)
        raise RuntimeError(result) from exc


def main() -> None:
    """
    enable all workflows in all repositories for the given owner
    >>> # we actually don't do that here AGAIN because of GitHub Rate limits
    >>> # those functions are called anyway already by doctest
    >>> # main()

    """

    enable_all_workflows(owner=get_owner(), github_token=get_github_token())
    delete_old_workflow_runs(owner=get_owner(), github_token=get_github_token(), number_of_workflow_runs_to_keep=50)


if __name__ == "__main__":
    print("this is a library only, the executable is named 'keep_github_workflows_active_cli.py'", file=sys.stderr)
