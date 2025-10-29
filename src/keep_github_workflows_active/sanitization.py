"""Security helpers for sanitizing sensitive data from logs and outputs.

Purpose
-------
Prevent credential leakage by redacting sensitive values from headers, messages,
and data structures before they reach logging systems. All helpers are pure
functions returning sanitized copies without mutating inputs.

Contents
--------
* :func:`sanitize_headers` – redact Authorization and authentication headers.
* :func:`sanitize_message` – redact token-like patterns from text.
* :func:`sanitize_dict` – recursively sanitize dictionary values.
* :func:`sanitize_for_logging` – convenience wrapper for common logging scenarios.

System Role
-----------
Acts as the security boundary for all logging operations involving external API
interactions. Import these helpers wherever sensitive data might be logged to
ensure credentials never leak into log files or monitoring systems.
"""

from __future__ import annotations

import re
from collections.abc import Mapping as MappingABC
from typing import Any, Mapping

#: HTTP header names that contain sensitive authentication data.
SENSITIVE_HEADERS = frozenset(
    [
        "authorization",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "auth-token",
        "cookie",
        "set-cookie",
    ]
)

#: Dictionary keys that typically contain sensitive values.
SENSITIVE_KEYS = frozenset(
    [
        "authorization",
        "api_key",
        "api-key",
        "apikey",
        "token",
        "auth_token",
        "auth-token",
        "access_token",
        "access-token",
        "secret",
        "password",
        "passwd",
        "pwd",
        "credential",
        "credentials",
    ]
)

#: Replacement text for redacted values.
REDACTED_PLACEHOLDER = "[REDACTED]"

#: Pattern matching token-like strings:
#: - GitHub tokens (ghp_, gho_, ghs_, etc. followed by alphanumerics)
#: - Long hex strings (40+ chars)
#: - Base64-like sequences (40+ chars)
TOKEN_PATTERN = re.compile(
    r"\b(gh[a-z]_[A-Za-z0-9]{36,}|[a-f0-9]{40,}|[A-Za-z0-9+/]{40,}={0,2})\b",
    re.IGNORECASE,
)


def _is_sensitive_header(name: str) -> bool:
    """Return True when header name contains authentication data.

    Parameters
    ----------
    name:
        HTTP header name to check.

    Returns
    -------
    bool
        True when the header should be redacted.

    Examples
    --------
    >>> _is_sensitive_header("Authorization")
    True
    >>> _is_sensitive_header("Content-Type")
    False
    >>> _is_sensitive_header("X-API-Key")
    True
    """

    return name.lower() in SENSITIVE_HEADERS


def _redact_value() -> str:
    """Return the standard redaction placeholder.

    Returns
    -------
    str
        Placeholder text replacing sensitive values.

    Examples
    --------
    >>> _redact_value()
    '[REDACTED]'
    """

    return REDACTED_PLACEHOLDER


def _sanitize_header_value(name: str, value: str) -> str:
    """Return sanitized header value or placeholder when sensitive.

    Parameters
    ----------
    name:
        HTTP header name.
    value:
        Header value to potentially redact.

    Returns
    -------
    str
        Original value when safe, placeholder when sensitive.

    Examples
    --------
    >>> _sanitize_header_value("Content-Type", "application/json")
    'application/json'
    >>> _sanitize_header_value("Authorization", "Bearer ghp_secret123")
    '[REDACTED]'
    """

    return _redact_value() if _is_sensitive_header(name) else value


def sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return copy of headers with authentication values redacted.

    Why
        HTTP headers often contain tokens or API keys. Logging raw headers
        would leak credentials into monitoring systems and log files.

    What
        Creates a shallow copy with sensitive header values replaced by
        :data:`REDACTED_PLACEHOLDER`. Recognized headers include Authorization,
        X-API-Key, Cookie, and others defined in :data:`SENSITIVE_HEADERS`.

    Parameters
    ----------
    headers:
        HTTP headers dictionary potentially containing secrets.

    Returns
    -------
    dict[str, str]
        Sanitized copy safe for logging.

    Examples
    --------
    >>> headers = {"Authorization": "Bearer ghp_abc123", "Accept": "application/json"}
    >>> sanitized = sanitize_headers(headers)
    >>> sanitized["Authorization"]
    '[REDACTED]'
    >>> sanitized["Accept"]
    'application/json'
    >>> headers["Authorization"]  # Original unchanged
    'Bearer ghp_abc123'
    """

    return {name: _sanitize_header_value(name, value) for name, value in headers.items()}


def _redact_token_match(match: re.Match[str]) -> str:
    """Return redaction placeholder for regex token matches.

    Parameters
    ----------
    match:
        Regex match object containing a token-like string.

    Returns
    -------
    str
        Redaction placeholder.
    """

    return _redact_value()


def sanitize_message(text: str) -> str:
    """Return message with token-like patterns redacted.

    Why
        Error messages and log statements may inadvertently include tokens from
        URLs, JSON payloads, or API responses. This helper scrubs patterns that
        resemble authentication tokens.

    What
        Uses :data:`TOKEN_PATTERN` to detect long hexadecimal or base64-like
        sequences and replaces them with :data:`REDACTED_PLACEHOLDER`.

    Parameters
    ----------
    text:
        Message string potentially containing tokens.

    Returns
    -------
    str
        Sanitized message safe for logging.

    Examples
    --------
    >>> msg = "Request failed: token=ghp_1234567890abcdefABCDEF1234567890abcdefAB"
    >>> sanitize_message(msg)
    'Request failed: token=[REDACTED]'
    >>> sanitize_message("Normal log message")
    'Normal log message'
    """

    return TOKEN_PATTERN.sub(_redact_token_match, text)


def _is_sensitive_key(name: str) -> bool:
    """Return True when dictionary key contains sensitive data.

    Parameters
    ----------
    name:
        Dictionary key name to check.

    Returns
    -------
    bool
        True when the key should be redacted.

    Examples
    --------
    >>> _is_sensitive_key("token")
    True
    >>> _is_sensitive_key("api_key")
    True
    >>> _is_sensitive_key("count")
    False
    """

    return name.lower() in SENSITIVE_KEYS or name.lower() in SENSITIVE_HEADERS


def _sanitize_dict_value(key: str, value: Any) -> Any:  # noqa: ANN401
    """Return sanitized value for dictionary entry.

    Parameters
    ----------
    key:
        Dictionary key name.
    value:
        Value to potentially sanitize.

    Returns
    -------
    Any
        Sanitized value (redacted if key is sensitive, recursively sanitized
        if dict, original otherwise).

    Examples
    --------
    >>> _sanitize_dict_value("api_key", "secret123")
    '[REDACTED]'
    >>> _sanitize_dict_value("count", 42)
    42
    """

    if _is_sensitive_key(key):
        return _redact_value()
    if isinstance(value, (dict, MappingABC)):
        # Type narrowing: we know value is Mapping at this point
        return sanitize_dict(value)  # type: ignore[arg-type]
    if isinstance(value, str):
        return sanitize_message(value)
    return value


def sanitize_dict(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return deep copy of dictionary with sensitive values redacted.

    Why
        Structured logging often includes entire request/response dictionaries.
        Recursively sanitizing nested structures ensures credentials never leak.

    What
        Creates a deep copy where sensitive keys (matching
        :data:`SENSITIVE_HEADERS`) are redacted, nested dicts are recursively
        processed, and string values are scrubbed for token patterns.

    Parameters
    ----------
    data:
        Dictionary potentially containing sensitive data.

    Returns
    -------
    dict[str, Any]
        Sanitized copy safe for logging.

    Examples
    --------
    >>> data = {"user": "alice", "token": "ghp_secret", "meta": {"api_key": "xyz"}}
    >>> sanitized = sanitize_dict(data)
    >>> sanitized["user"]
    'alice'
    >>> sanitized["token"]
    '[REDACTED]'
    >>> sanitized["meta"]["api_key"]
    '[REDACTED]'
    """

    return {key: _sanitize_dict_value(key, value) for key, value in data.items()}


def sanitize_for_logging(value: Any) -> Any:  # noqa: ANN401
    """Return sanitized representation suitable for logging.

    Why
        Logging calls may receive various types (dicts, strings, objects).
        This convenience function dispatches to the appropriate sanitizer.

    What
        Detects the input type and applies the relevant sanitization strategy:
        dicts are recursively sanitized, strings are scrubbed for tokens,
        other types pass through unchanged.

    Parameters
    ----------
    value:
        Value to sanitize for logging.

    Returns
    -------
    Any
        Sanitized representation safe for logs.

    Examples
    --------
    >>> sanitize_for_logging({"Authorization": "Bearer secret"})
    {'Authorization': '[REDACTED]'}
    >>> sanitize_for_logging("Token: ghp_1234567890abcdefABCDEF1234567890abcdefAB")
    'Token: [REDACTED]'
    >>> sanitize_for_logging(42)
    42
    """

    if isinstance(value, (dict, MappingABC)):
        # Type narrowing: we know value is Mapping at this point
        return sanitize_dict(value)  # type: ignore[arg-type]
    if isinstance(value, str):
        return sanitize_message(value)
    return value


__all__ = [
    "SENSITIVE_HEADERS",
    "SENSITIVE_KEYS",
    "REDACTED_PLACEHOLDER",
    "TOKEN_PATTERN",
    "sanitize_headers",
    "sanitize_message",
    "sanitize_dict",
    "sanitize_for_logging",
]
