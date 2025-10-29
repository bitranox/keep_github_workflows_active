"""Security sanitization stories: ensure secrets never leak into logs."""

from __future__ import annotations

import pytest

from keep_github_workflows_active import sanitization


@pytest.mark.os_agnostic
def test_when_authorization_header_is_sanitized_the_token_vanishes() -> None:
    headers = {
        "Authorization": "Bearer ghp_1234567890abcdefABCDEF1234567890abcdefAB",
        "Accept": "application/json",
    }

    sanitized = sanitization.sanitize_headers(headers)

    assert sanitized["Authorization"] == "[REDACTED]"
    assert sanitized["Accept"] == "application/json"
    assert headers["Authorization"] != "[REDACTED]"  # Original unchanged


@pytest.mark.os_agnostic
def test_when_api_key_header_is_sanitized_the_secret_is_hidden() -> None:
    headers = {"X-API-Key": "super-secret-key-12345", "Content-Type": "text/plain"}

    sanitized = sanitization.sanitize_headers(headers)

    assert sanitized["X-API-Key"] == "[REDACTED]"
    assert sanitized["Content-Type"] == "text/plain"


@pytest.mark.os_agnostic
def test_when_cookie_header_is_sanitized_the_session_is_masked() -> None:
    headers = {"Cookie": "session=abc123; token=xyz789", "User-Agent": "TestBot/1.0"}

    sanitized = sanitization.sanitize_headers(headers)

    assert sanitized["Cookie"] == "[REDACTED]"
    assert sanitized["User-Agent"] == "TestBot/1.0"


@pytest.mark.os_agnostic
def test_when_mixed_case_headers_are_sanitized_matching_is_case_insensitive() -> None:
    headers = {
        "authorization": "Bearer lowercase",
        "Authorization": "Bearer uppercase",
        "AUTHORIZATION": "Bearer allcaps",
    }

    sanitized = sanitization.sanitize_headers(headers)

    assert all(value == "[REDACTED]" for value in sanitized.values())


@pytest.mark.os_agnostic
def test_when_empty_headers_are_sanitized_empty_dict_returns() -> None:
    headers: dict[str, str] = {}

    sanitized = sanitization.sanitize_headers(headers)

    assert sanitized == {}


@pytest.mark.os_agnostic
def test_when_message_contains_token_pattern_the_secret_is_scrubbed() -> None:
    message = "Authentication failed: token=ghp_1234567890abcdefABCDEF1234567890abcdefAB was invalid"

    sanitized = sanitization.sanitize_message(message)

    assert "ghp_" not in sanitized
    assert "[REDACTED]" in sanitized
    assert "Authentication failed" in sanitized
    assert "was invalid" in sanitized


@pytest.mark.os_agnostic
def test_when_message_contains_base64_token_the_secret_is_redacted() -> None:
    message = "Upload token: dGhpc2lzYXZlcnlsb25nYmFzZTY0ZW5jb2RlZHRva2VudGhhdHNob3VsZGJlcmVkYWN0ZWQ="

    sanitized = sanitization.sanitize_message(message)

    assert "dGhpc2lz" not in sanitized
    assert "[REDACTED]" in sanitized
    assert "Upload token:" in sanitized


@pytest.mark.os_agnostic
def test_when_message_contains_multiple_tokens_all_are_redacted() -> None:
    message = "First: abc123def456abc123def456abc123def456abc123 and second: xyz789xyz789xyz789xyz789xyz789xyz789xyz789"

    sanitized = sanitization.sanitize_message(message)

    assert "abc123def456" not in sanitized
    assert "xyz789xyz789" not in sanitized
    assert sanitized.count("[REDACTED]") == 2


@pytest.mark.os_agnostic
def test_when_message_has_no_tokens_content_is_unchanged() -> None:
    message = "Normal log message without any secrets"

    sanitized = sanitization.sanitize_message(message)

    assert sanitized == message


@pytest.mark.os_agnostic
def test_when_message_contains_short_hex_strings_they_are_preserved() -> None:
    message = "Commit SHA: abc123 (too short to be a token)"

    sanitized = sanitization.sanitize_message(message)

    assert sanitized == message
    assert "abc123" in sanitized


@pytest.mark.os_agnostic
def test_when_dict_with_sensitive_keys_is_sanitized_values_are_redacted() -> None:
    data = {
        "username": "alice",
        "authorization": "Bearer secret",
        "api_key": "xyz123",
        "count": 42,
    }

    sanitized = sanitization.sanitize_dict(data)

    assert sanitized["username"] == "alice"
    assert sanitized["authorization"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["count"] == 42
    assert data["authorization"] == "Bearer secret"  # Original unchanged


@pytest.mark.os_agnostic
def test_when_nested_dict_is_sanitized_deep_secrets_are_redacted() -> None:
    data = {
        "request": {
            "headers": {"Authorization": "Bearer nested-secret"},
            "body": {"message": "Hello"},
        },
        "metadata": {"token": "outer-secret"},
    }

    sanitized = sanitization.sanitize_dict(data)

    assert sanitized["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert sanitized["request"]["body"]["message"] == "Hello"
    assert sanitized["metadata"]["token"] == "[REDACTED]"


@pytest.mark.os_agnostic
def test_when_dict_values_contain_token_patterns_strings_are_scrubbed() -> None:
    data = {
        "error": "Failed with token ghp_1234567890abcdefABCDEF1234567890abcdefAB",
        "status": "error",
    }

    sanitized = sanitization.sanitize_dict(data)

    assert "ghp_" not in sanitized["error"]
    assert "[REDACTED]" in sanitized["error"]
    assert "Failed with token" in sanitized["error"]
    assert sanitized["status"] == "error"


@pytest.mark.os_agnostic
def test_when_dict_contains_non_string_non_dict_values_they_pass_through() -> None:
    data = {
        "count": 42,
        "ratio": 3.14,
        "enabled": True,
        "items": [1, 2, 3],
        "none_value": None,
    }

    sanitized = sanitization.sanitize_dict(data)

    assert sanitized == data


@pytest.mark.os_agnostic
def test_when_empty_dict_is_sanitized_empty_dict_returns() -> None:
    data: dict[str, str] = {}

    sanitized = sanitization.sanitize_dict(data)

    assert sanitized == {}


@pytest.mark.os_agnostic
def test_when_sanitize_for_logging_receives_dict_it_sanitizes_deeply() -> None:
    value = {"api_key": "secret", "data": {"authorization": "Bearer token"}}

    sanitized = sanitization.sanitize_for_logging(value)

    assert isinstance(sanitized, dict)
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["data"]["authorization"] == "[REDACTED]"


@pytest.mark.os_agnostic
def test_when_sanitize_for_logging_receives_string_it_redacts_tokens() -> None:
    value = "Log message with token: ghp_1234567890abcdefABCDEF1234567890abcdefAB"

    sanitized = sanitization.sanitize_for_logging(value)

    assert isinstance(sanitized, str)
    assert "ghp_" not in sanitized
    assert "[REDACTED]" in sanitized


@pytest.mark.os_agnostic
def test_when_sanitize_for_logging_receives_other_types_they_pass_through() -> None:
    int_value = 42
    float_value = 3.14
    bool_value = True
    none_value = None

    assert sanitization.sanitize_for_logging(int_value) == 42
    assert sanitization.sanitize_for_logging(float_value) == 3.14
    assert sanitization.sanitize_for_logging(bool_value) is True
    assert sanitization.sanitize_for_logging(none_value) is None


@pytest.mark.os_agnostic
def test_when_all_sensitive_header_names_are_checked_matching_is_comprehensive() -> None:
    # Test all headers defined in SENSITIVE_HEADERS
    test_cases = [
        ("Authorization", "Bearer token"),
        ("X-API-Key", "key123"),
        ("API-Key", "key456"),
        ("X-Auth-Token", "token789"),
        ("Auth-Token", "tokenABC"),
        ("Cookie", "session=xyz"),
        ("Set-Cookie", "session=xyz"),
    ]

    for header_name, header_value in test_cases:
        headers = {header_name: header_value}
        sanitized = sanitization.sanitize_headers(headers)
        assert sanitized[header_name] == "[REDACTED]", f"Failed to redact {header_name}"


@pytest.mark.os_agnostic
def test_when_real_github_headers_are_sanitized_token_is_protected() -> None:
    """Simulate actual GitHub API headers used in the codebase."""
    headers = {
        "Authorization": "Bearer ghp_ExampleTokenThatShouldBeRedactedInLogs1234567890",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "keep-github-workflows-active/2.0.0",
    }

    sanitized = sanitization.sanitize_headers(headers)

    assert sanitized["Authorization"] == "[REDACTED]"
    assert sanitized["Accept"] == "application/vnd.github.v3+json"
    assert sanitized["User-Agent"] == "keep-github-workflows-active/2.0.0"


@pytest.mark.os_agnostic
def test_when_error_message_with_github_token_is_sanitized_secret_is_removed() -> None:
    """Simulate error message that might accidentally contain token."""
    error_msg = "ERROR enabling repository: HTTP 401 Unauthorized. Request headers: {'Authorization': 'Bearer ghp_1234567890abcdefABCDEF1234567890abcdefAB'}"

    sanitized = sanitization.sanitize_message(error_msg)

    assert "ghp_" not in sanitized
    assert "[REDACTED]" in sanitized
    assert "ERROR enabling repository" in sanitized


@pytest.mark.os_agnostic
def test_when_sensitive_headers_constant_is_immutable_it_cannot_be_modified() -> None:
    """Ensure SENSITIVE_HEADERS is a frozenset and cannot be changed."""
    assert isinstance(sanitization.SENSITIVE_HEADERS, frozenset)

    with pytest.raises(AttributeError):
        sanitization.SENSITIVE_HEADERS.add("new-header")  # type: ignore[attr-defined]


@pytest.mark.os_agnostic
def test_when_redacted_placeholder_is_consistent_all_calls_use_same_value() -> None:
    """Ensure consistent redaction marker across all sanitization functions."""
    assert sanitization.REDACTED_PLACEHOLDER == "[REDACTED]"

    headers_result = sanitization.sanitize_headers({"Authorization": "secret"})
    message_result = sanitization.sanitize_message("token: ghp_1234567890abcdefABCDEF1234567890abcdefAB")
    dict_result = sanitization.sanitize_dict({"api_key": "secret"})

    assert headers_result["Authorization"] == sanitization.REDACTED_PLACEHOLDER
    assert sanitization.REDACTED_PLACEHOLDER in message_result
    assert dict_result["api_key"] == sanitization.REDACTED_PLACEHOLDER
