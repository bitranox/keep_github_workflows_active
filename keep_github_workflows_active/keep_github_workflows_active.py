# STDLIB
import os
import pathlib
import sys
from typing import Any, Dict, List

# EXT
import requests

# OWN
import lib_log_utils
import lib_detect_testenv

# CONFIG

rotek_config_directory = str(pathlib.Path("/rotek/scripts/credentials").absolute())


def enable_all_workflows(owner: str, github_token: str) -> None:
    """
    :param owner: the repo owner
    :param github_token:
    :return:

    >>> # Setup
    >>> my_owner = get_owner()
    >>> my_github_token = get_github_token()

    >>> # Test OK
    >>> enable_all_workflows(owner=my_owner, github_token=my_github_token)
     Activating and maintaining all workflows for owner ...

    >>> # unknown owner
    >>> enable_all_workflows(owner='unknown_owner', github_token=my_github_token)
    Traceback (most recent call last):
        ...
    RuntimeError: ERROR reading repositories for user unknown_owner: Not Found


    >>> # wrong credentials
    >>> enable_all_workflows(owner=my_owner, github_token='invalid_credentials')
    Traceback (most recent call last):
        ...
    RuntimeError: ERROR reading repositories for user bitranox: Bad credentials

    """
    print(f'Activating and maintaining all workflows for owner {owner}:')
    repositories = get_repositories(owner=owner, github_token=github_token)
    for repository in repositories:
        workflows = get_workflows(owner=owner, repository=repository, github_token=github_token)
        for workflow_filename in workflows:
            print(f'activate workflow {repository}/{workflow_filename}')
            enable_workflow(owner=owner, repository=repository, workflow_filename=workflow_filename, github_token=github_token)


def delete_old_workflow_runs(owner: str, github_token: str, number_of_workflow_runs_to_keep: int = 50) -> None:
    """
    :param owner:
    :param github_token:
    :param number_of_workflow_runs_to_keep:
    :return:

    >>> # Setup
    >>> my_owner = get_owner()
    >>> my_github_token = get_github_token()

    >>> # Test
    >>> delete_old_workflow_runs(owner=my_owner, github_token=my_github_token, number_of_workflow_runs_to_keep=50)
    Removing outdated workflow executions for owner ..., while retaining a maximum of ... workflow runs per repository...

    """
    print(f'Removing outdated workflow executions for owner {owner}, while retaining a maximum of '
          f'{number_of_workflow_runs_to_keep} workflow runs per repository:')
    l_repositories = get_repositories(owner=owner, github_token=github_token)
    for repository in l_repositories:
        workflow_run_ids = get_workflow_runs(owner=owner, repository=repository, github_token=github_token)
        workflow_run_ids_sorted = sorted(workflow_run_ids, reverse=True)
        workflow_run_ids_to_delete = workflow_run_ids_sorted[number_of_workflow_runs_to_keep:]
        lib_log_utils.log_info(f'repository: {repository}, {len(workflow_run_ids)} workflow runs found, {len(workflow_run_ids_to_delete)} to delete.')
        for run_id_to_delete in workflow_run_ids_to_delete:
            print(f'remove workflow run {repository}/{run_id_to_delete}')
            delete_workflow_run(owner=owner, repository=repository, github_token=github_token, run_id_to_delete=run_id_to_delete)


def get_owner() -> str:
    if lib_detect_testenv.is_testenv_active():
        if os.getenv('GITHUB_ACTION'):
            owner = os.environ.get('SECRET_GITHUB_OWNER')
        else:
            owner, github_token = read_github_credentials(config_directory=rotek_config_directory)
    else:
        owner, github_token = read_github_credentials(config_directory=rotek_config_directory)
    return owner


def get_github_token() -> str:
    if lib_detect_testenv.is_testenv_active():
        if os.getenv('GITHUB_ACTION'):
            github_token = os.environ.get('SECRET_GITHUB_TOKEN')
        else:
            owner, github_token = read_github_credentials(config_directory=rotek_config_directory)
    else:
        owner, github_token = read_github_credentials(config_directory=rotek_config_directory)
    return github_token


def read_github_credentials(config_directory: str) -> tuple[str, str]:
    """
    Reads GitHub credentials from a Python file and returns them.

    :param config_directory: The path to the directory containing the 'github_credentials.py' file.
    :return: A tuple containing (owner, github_token).
    """
    credentials_path = pathlib.Path(config_directory) / "github_credentials.py"
    namespace: Dict[str, Any] = {}
    owner = ""
    github_token = ""
    try:
        with open(credentials_path, 'r') as file:
            exec(file.read(), {}, namespace)
        # Access the variables 'github_token' and 'owner' in the namespace dictionary
        github_token = namespace.get('github_token')
        owner = namespace.get('owner')
        if github_token is None or owner is None:
            raise ValueError("Required variables 'github_token' or 'owner' were not found.")

    except FileNotFoundError:
        print(f"File could not be found. Check the path: {credentials_path}")
    except Exception as e:
        print(f"An error occurred: {e}")
    return owner, github_token


def get_repositories(owner: str, github_token: str) -> List[str]:
    """
    Fetch all repositories for a given GitHub user, handling pagination and setting the page size to 100.

    :param owner: The username of the repository owner.
    :param github_token: A personal access token for GitHub API authentication.
    :return: A list of repository names.

        >>> # Setup
    >>> my_owner = get_owner()
    >>> my_github_token = get_github_token()

    >>> # Test Ok
    >>> get_repositories(my_owner, my_github_token)
    ['...', ..., '...']

    >>> # Test user not existing
    >>> get_repositories('user_does_not_exist', my_github_token)
    Traceback (most recent call last):
        ...
    RuntimeError: ERROR reading repositories for user user_does_not_exist: Not Found

    >>> # Test token not valid
    >>> get_repositories(my_owner, 'invalid_token')
    Traceback (most recent call last):
        ...
    RuntimeError: ERROR reading repositories for user bitranox: Bad credentials


    """
    repositories = []
    url = f"https://api.github.com/users/{owner}/repos?per_page=100"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    while url:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raises HTTPError for bad responses
            data = response.json()
            repositories.extend([repo['name'] for repo in data])

            # Get the URL for the next page from the response headers, if present
            url = response.links.get('next', {}).get('url', None)

        except requests.exceptions.HTTPError as exc:
            error_message = exc.response.json().get("message", "Error")
            result = f'ERROR reading repositories for user {owner}: {error_message}'
            lib_log_utils.log_error(result)
            raise RuntimeError(result) from exc

    result = f'Found {len(repositories)} repositories for user {owner}'
    lib_log_utils.log_info(result)
    return repositories


def get_workflows(owner: str, repository: str, github_token: str) -> List[str]:
    """
    Fetch all workflows for a given GitHub repository, handling pagination and setting the page size to 100.

    :param owner: The username of the repository owner.
    :param repository: The name of the repository.
    :param github_token: A personal access token for GitHub API authentication.
    :return: A list of workflow names.


    >>> # Setup
    >>> my_owner = get_owner()
    >>> my_github_token = get_github_token()
    >>> l_repositories = get_repositories(owner=my_owner, github_token=my_github_token)

    >>> # Test OK
    >>> for my_repository in l_repositories:
    ...     get_workflows(owner=my_owner, repository=my_repository, github_token=my_github_token)
    [...]
    ...

    >>> # wrong owner
    >>> get_workflows(owner='does_not_exist', repository=l_repositories[0], github_token=my_github_token)
    Traceback (most recent call last):
        ...
    RuntimeError: ERROR reading workflows for user: ..., repository: ..., Not Found

    >>> # wrong repository
    >>> get_workflows(owner='bitranox', repository='unknown_repository', github_token=my_github_token)
    Traceback (most recent call last):
        ...
    RuntimeError: ERROR reading workflows for user: ..., repository: unknown_repository, Not Found

    >>> # token not valid
    >>> get_workflows(owner='bitranox', repository=l_repositories[0], github_token='invalid_token')
    Traceback (most recent call last):
        ...
    RuntimeError: ERROR reading workflows for user: ..., repository: ..., Bad credentials


    """
    workflows = []
    url = f"https://api.github.com/repos/{owner}/{repository}/actions/workflows?per_page=100"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    while url:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raises HTTPError for bad responses
            data = response.json()
            workflows.extend([pathlib.Path(workflow['path']).name for workflow in data.get('workflows', [])])

            # Get the URL for the next page from the response headers, if present
            url = response.links.get('next', {}).get('url', None)

        except requests.exceptions.HTTPError as exc:
            error_message = exc.response.json().get("message", "Error")
            result = f'ERROR reading workflows for user: {owner}, repository: {repository}, {error_message}'
            lib_log_utils.log_error(result)
            raise RuntimeError(result) from exc

    result = f'Found {len(workflows)} workflows for user: {owner}, repository: {repository}'
    lib_log_utils.log_info(result)
    return workflows


def get_workflow_runs(owner: str, repository: str, github_token: str) -> List[str]:
    """
    Fetch all workflow runs for a GitHub repository using the GitHub API v3, handling pagination.

    :param owner: The username of the repository owner.
    :param repository: The name of the repository.
    :param github_token: A GitHub personal access token for authentication.
    :return: A list of workflow run IDs.

    >>> # Setup
    >>> my_owner = get_owner()
    >>> my_github_token = get_github_token()
    >>> l_repositories = get_repositories(owner=my_owner, github_token=my_github_token)

    >>> # Test OK
    >>> for my_repository in l_repositories:
    ...     get_workflow_runs(owner=my_owner, repository=my_repository, github_token=my_github_token)
    [...]
    ...


    """
    # set pagination to 100 (the maximum at GitHub), to have fewer requests
    url = f"https://api.github.com/repos/{owner}/{repository}/actions/runs?per_page=100"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    l_workflow_run_ids = []
    while url:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raises an HTTPError if the response was an error

            # Process response data
            data = response.json()
            l_workflow_run_ids.extend([run['id'] for run in data.get('workflow_runs', [])])

            # Check for the 'next' page link
            url = response.links.get('next', {}).get('url', None)

        except requests.exceptions.HTTPError as exc:
            result_error_message = exc.response.json().get("message", "Error")
            result = f'ERROR reading workflow runs for user: {owner}, repository: {repository}, {result_error_message}'
            lib_log_utils.log_error(result)
            raise RuntimeError(result) from exc

    result = f'Found {len(l_workflow_run_ids)} workflow runs for user: {owner}, repository: {repository}'
    lib_log_utils.log_info(result)
    return l_workflow_run_ids


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
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        response = requests.delete(url, headers=headers)

        if response.status_code == 204:
            result = f'Deleted workflow run ID: {run_id_to_delete} for user: {owner}, repository: {repository}'
            lib_log_utils.log_info(result)

    except requests.exceptions.RequestException as exc:
        # For HTTP errors, requests will raise a RequestException. Here we catch all errors derived from RequestException
        result_error_message = f'ERROR deleting workflow run ID: {run_id_to_delete} for user: {owner}, repository: {repository}: {exc}'
        lib_log_utils.log_error(result_error_message)
        raise RuntimeError(result_error_message) from exc


def enable_workflow(owner: str, repository: str, workflow_filename: str, github_token: str) -> str:
    """
    Enable a workflow in a GitHub repository using the GitHub API.

    :param owner: The username of the repository owner.
    :param repository: The name of the repository.
    :param workflow_filename: The name of the workflow file, for example, "python-package.yml".
    :param github_token: A GitHub access token with permissions to enable workflows.
    :return: A success message if the workflow is enabled.


    >>> # Setup
    >>> my_owner = get_owner()
    >>> my_github_token = get_github_token()

    >>> # Test OK
    >>> enable_workflow(owner=my_owner, repository="lib_path", workflow_filename="python-package.yml", github_token=my_github_token)
    'Enabled repository lib_path, workflow python-package.yml'

    >>> # wrong owner
    >>> enable_workflow(owner='owner_does_not_exist', repository="lib_path", workflow_filename="python-package.yml", github_token=my_github_token)
    Traceback (most recent call last):
        ...
    RuntimeError: ERROR enabling repository lib_path, workflow python-package.yml: Not Found

    >>> # wrong repo
    >>> enable_workflow(owner=my_owner, repository="repo_does_not_exist", workflow_filename="python-package.yml", github_token=my_github_token)
    Traceback (most recent call last):
        ...
    RuntimeError: ERROR enabling repository repo_does_not_exist, workflow python-package.yml: Not Found


    >>> # wrong credentials
    >>> enable_workflow(owner=my_owner, repository="lib_path", workflow_filename="python-package.yml", github_token="wrong_credentials")
    Traceback (most recent call last):
        ...
    RuntimeError: ERROR enabling repository lib_path, workflow python-package.yml: Bad credentials


    """
    url = f"https://api.github.com/repos/{owner}/{repository}/actions/workflows/{workflow_filename}/enable"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {github_token}"
    }

    try:
        if workflow_filename.startswith("pages-build-deployment"):
            result = f'Repository {repository}, workflow {workflow_filename} skipped - those can not be enabled'
        else:
            response = requests.put(url, headers=headers)
            response.raise_for_status()  # This will raise an exception for HTTP error codes
            result = f'Enabled repository {repository}, workflow {workflow_filename}'
            lib_log_utils.log_info(result)
        return result

    except requests.exceptions.HTTPError as exc:
        error_message = response.json().get("message", "Error")     # noqa
        result = f'ERROR enabling repository {repository}, workflow {workflow_filename}: {error_message}'
        lib_log_utils.log_error(result)
        raise RuntimeError(result) from exc


# main{{{
def main() -> None:
    """
    enable all workflows in all repositories for the given owner
    >>> # we actually don't do that here AGAIN because of GitHub Rate limits
    >>> # those functions are called anyway already by doctest
    >>> # main()

    """
    # main}}}

    enable_all_workflows(owner=get_owner(), github_token=get_github_token())
    delete_old_workflow_runs(owner=get_owner(), github_token=get_github_token(), number_of_workflow_runs_to_keep=50)


if __name__ == '__main__':
    print(b'this is a library only, the executable is named "keep_github_workflows_active_cli.py"', file=sys.stderr)
