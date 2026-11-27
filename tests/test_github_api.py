"""GitHub API functions exercised offline through the session seam.

The functions take a ``requests.Session``; these tests mount a transport adapter on the session
:func:`github_session` builds, so the real request building, header handling, pagination and
error parsing run while no byte leaves the machine.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
import requests
from requests.adapters import BaseAdapter, HTTPAdapter
from urllib3 import HTTPResponse

from keep_github_workflows_active import keep_github_workflow_active as keep_active

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

API = "https://api.github.com"


@dataclass(frozen=True)
class CannedReply:
    """One reply the fake GitHub serves for a method and URL."""

    status: int = 200
    body: object = None
    link_next: str | None = None


@dataclass
class FakeGitHub(BaseAdapter):
    """Transport adapter answering from a table and recording every request it was sent."""

    replies: Mapping[tuple[str, str], CannedReply]
    sent: list[requests.PreparedRequest] = field(default_factory=list[requests.PreparedRequest])

    def __post_init__(self) -> None:
        super().__init__()

    def send(self, request: requests.PreparedRequest, *args: object, **kwargs: object) -> requests.Response:
        self.sent.append(request)
        reply = self.replies.get((str(request.method), str(request.url)))
        if reply is None:
            reply = CannedReply(status=599, body={"message": f"no canned reply for {request.method} {request.url}"})
        headers = {"Content-Type": "application/json"}
        if reply.link_next:
            headers["Link"] = f'<{reply.link_next}>; rel="next"'
        payload = b"" if reply.body is None else json.dumps(reply.body).encode()
        raw = HTTPResponse(body=io.BytesIO(payload), headers=headers, status=reply.status, preload_content=False)
        return HTTPAdapter().build_response(request, raw)

    def close(self) -> None:
        """Nothing to release."""


def _session_with(replies: Mapping[tuple[str, str], CannedReply]) -> tuple[requests.Session, FakeGitHub]:
    session = keep_active.github_session("t0ken")
    fake = FakeGitHub(replies=replies)
    session.mount("https://", fake)
    return session, fake


def _urls(sent: Sequence[requests.PreparedRequest]) -> list[str]:
    return [f"{request.method} {request.url}" for request in sent]


@pytest.mark.os_agnostic
def test_when_a_session_is_built_every_request_carries_the_bearer_token_and_accept_header() -> None:
    url = f"{API}/repos/o/r/actions/workflows?per_page=100"
    session, fake = _session_with({("GET", url): CannedReply(body={"workflows": []})})

    keep_active.get_workflows(owner="o", repository="r", session=session)

    assert fake.sent[0].headers["Authorization"] == "Bearer t0ken"
    assert fake.sent[0].headers["Accept"] == "application/vnd.github.v3+json"


@pytest.mark.os_agnostic
def test_when_workflows_span_two_pages_both_are_read_through_the_same_session() -> None:
    first = f"{API}/repos/o/r/actions/workflows?per_page=100"
    second = f"{API}/repos/o/r/actions/workflows?per_page=100&page=2"
    session, fake = _session_with(
        {
            ("GET", first): CannedReply(body={"workflows": [{"path": ".github/workflows/a.yml"}]}, link_next=second),
            ("GET", second): CannedReply(body={"workflows": [{"path": ".github/workflows/b.yml"}]}),
        }
    )

    workflows = keep_active.get_workflows(owner="o", repository="r", session=session)

    assert workflows == ["a.yml", "b.yml"]
    assert _urls(fake.sent) == [f"GET {first}", f"GET {second}"]


@pytest.mark.os_agnostic
def test_when_the_owner_is_no_organisation_repositories_come_from_the_user_endpoint() -> None:
    org = f"{API}/orgs/someone/repos?per_page=100"
    user = f"{API}/users/someone/repos?per_page=100"
    session, fake = _session_with(
        {
            ("GET", org): CannedReply(status=404, body={"message": "Not Found"}),
            ("GET", user): CannedReply(body=[{"name": "alpha"}, {"name": "beta"}]),
        }
    )

    repositories = keep_active.get_repositories(owner="someone", session=session)

    assert repositories == ["alpha", "beta"]
    assert _urls(fake.sent) == [f"GET {org}", f"GET {user}"]


@pytest.mark.os_agnostic
def test_when_the_owner_is_an_organisation_its_first_page_is_fetched_once() -> None:
    org = f"{API}/orgs/acme/repos?per_page=100"
    session, fake = _session_with({("GET", org): CannedReply(body=[{"name": "tool"}])})

    repositories = keep_active.get_repositories(owner="acme", session=session)

    assert repositories == ["tool"]
    assert _urls(fake.sent) == [f"GET {org}"]


@pytest.mark.os_agnostic
def test_when_workflow_runs_are_listed_their_ids_come_back_in_api_order() -> None:
    url = f"{API}/repos/o/r/actions/runs?per_page=100"
    session, _ = _session_with({("GET", url): CannedReply(body={"workflow_runs": [{"id": 7}, {"id": 3}]})})

    assert keep_active.get_workflow_runs(owner="o", repository="r", session=session) == [7, 3]


@pytest.mark.os_agnostic
def test_when_a_workflow_is_enabled_the_put_goes_through_the_session() -> None:
    url = f"{API}/repos/o/r/actions/workflows/ci.yml/enable"
    session, fake = _session_with({("PUT", url): CannedReply(status=204)})

    result = keep_active.enable_workflow(owner="o", repository="r", workflow_filename="ci.yml", session=session)

    assert result == "Enabled repository r, workflow ci.yml"
    assert _urls(fake.sent) == [f"PUT {url}"]


@pytest.mark.os_agnostic
def test_when_a_workflow_is_skipped_no_request_is_sent() -> None:
    session, fake = _session_with({})

    result = keep_active.enable_workflow(owner="o", repository="r", workflow_filename="dependabot-updates", session=session)

    assert result.endswith("skipped - managed by Dependabot")
    assert fake.sent == []


@pytest.mark.os_agnostic
def test_when_a_run_is_deleted_the_delete_goes_through_the_session() -> None:
    url = f"{API}/repos/o/r/actions/runs/42"
    session, fake = _session_with({("DELETE", url): CannedReply(status=204)})

    keep_active.delete_workflow_run(owner="o", repository="r", session=session, run_id_to_delete=42)

    assert _urls(fake.sent) == [f"DELETE {url}"]


@pytest.mark.os_agnostic
def test_when_github_refuses_a_listing_the_error_names_its_message() -> None:
    url = f"{API}/repos/o/r/actions/runs?per_page=100"
    session, _ = _session_with({("GET", url): CannedReply(status=403, body={"message": "Resource not accessible"})})

    with pytest.raises(RuntimeError, match="Resource not accessible"):
        keep_active.get_workflow_runs(owner="o", repository="r", session=session)
