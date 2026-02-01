"""GitHub API integration tests requiring real credentials.

These tests exercise the actual GitHub API and require:
- SECRET_GITHUB_OWNER environment variable or .env entry
- SECRET_GITHUB_TOKEN environment variable or .env entry

Marked with local_only to exclude from CI runs.
"""

from __future__ import annotations

import pytest

from keep_github_workflows_active import keep_github_workflow_active as keep_active


def _has_github_credentials() -> bool:
    """Check if GitHub credentials are available."""
    try:
        keep_active.get_owner()
        keep_active.get_github_token()
        return True
    except RuntimeError:
        return False


pytestmark = [pytest.mark.local_only]


@pytest.mark.skipif(not _has_github_credentials(), reason="GitHub credentials not available")
def test_get_repositories_returns_list() -> None:
    """Verify get_repositories returns a list of repository names."""
    owner = keep_active.get_owner()
    token = keep_active.get_github_token()

    repos = keep_active.get_repositories(owner=owner, github_token=token)

    assert isinstance(repos, list)


@pytest.mark.skipif(not _has_github_credentials(), reason="GitHub credentials not available")
def test_get_workflows_returns_list_for_each_repository() -> None:
    """Verify get_workflows returns workflow filenames for repositories."""
    owner = keep_active.get_owner()
    token = keep_active.get_github_token()
    repos = keep_active.get_repositories(owner=owner, github_token=token)

    for repo in repos[:3]:  # Limit to first 3 repos to avoid rate limits
        workflows = keep_active.get_workflows(owner=owner, repository=repo, github_token=token)
        assert isinstance(workflows, list)


@pytest.mark.skipif(not _has_github_credentials(), reason="GitHub credentials not available")
def test_get_workflow_runs_returns_list_for_each_repository() -> None:
    """Verify get_workflow_runs returns run IDs for repositories."""
    owner = keep_active.get_owner()
    token = keep_active.get_github_token()
    repos = keep_active.get_repositories(owner=owner, github_token=token)

    for repo in repos[:3]:  # Limit to first 3 repos to avoid rate limits
        run_ids = keep_active.get_workflow_runs(owner=owner, repository=repo, github_token=token)
        assert isinstance(run_ids, list)


@pytest.mark.skipif(not _has_github_credentials(), reason="GitHub credentials not available")
def test_enable_all_workflows_completes_without_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify enable_all_workflows runs successfully."""
    owner = keep_active.get_owner()
    token = keep_active.get_github_token()

    keep_active.enable_all_workflows(owner=owner, github_token=token)

    captured = capsys.readouterr()
    assert f"Activating and maintaining all workflows for owner {owner}" in captured.out


@pytest.mark.skipif(not _has_github_credentials(), reason="GitHub credentials not available")
def test_enable_workflow_handles_known_repository() -> None:
    """Verify enable_workflow returns success message for a known workflow."""
    owner = keep_active.get_owner()
    token = keep_active.get_github_token()

    result = keep_active.enable_workflow(
        owner=owner,
        repository="lib_path",
        workflow_filename="python-package.yml",
        github_token=token,
    )

    assert result  # Non-empty result message
