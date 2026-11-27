# Security Documentation

## Overview

This document describes how `keep_github_workflows_active` keeps its GitHub token out of logs and
error output.

## Where the token goes

- The token is read from `--token`, `SECRET_GITHUB_TOKEN` or a `.env` file (lookup order in
  [README.md](../../README.md)).
- `github_session()` in `keep_github_workflow_active.py` puts it into the `Authorization: Bearer`
  header of the `requests.Session` that every API call of a run uses. The module never puts the
  token or the session headers into a log or exception message it builds.
- Every log message of `keep_github_workflow_active.py` passes through
  `sanitization.sanitize_message()` before it reaches the logger, so a token that appears in text
  from elsewhere (for example in GitHub's error message) is redacted there.

## Sanitization Module

**Location**: `src/keep_github_workflows_active/sanitization.py`

All functions are pure: they return a sanitized copy and leave the input unchanged.

### `sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]`

Replaces the value of every header whose lower-cased name is in `SENSITIVE_HEADERS` with
`[REDACTED]`; other headers are copied unchanged.

**Protected headers**: Authorization, X-API-Key, API-Key, X-Auth-Token, Auth-Token, Cookie,
Set-Cookie.

```python
headers = {"Authorization": "Bearer ghp_ExampleToken123456", "Accept": "application/json"}
sanitize_headers(headers)
# {'Authorization': '[REDACTED]', 'Accept': 'application/json'}
```

### `sanitize_message(text: str) -> str`

Replaces every match of `TOKEN_PATTERN` with `[REDACTED]`.

```python
sanitize_message("Error: token ghp_1234567890abcdefABCDEF1234567890abcdefAB invalid")
# 'Error: token [REDACTED] invalid'
```

### `sanitize_dict(data: Mapping[str, Any]) -> dict[str, Any]`

Redacts the value of every key whose lower-cased name is exactly one of `SENSITIVE_KEYS` or
`SENSITIVE_HEADERS`, recurses into nested mappings, and scrubs the remaining string values with
`sanitize_message`. Other values are copied unchanged.

```python
data = {"user": "alice", "token": "ghp_secret123", "meta": {"api_key": "xyz789"}}
sanitize_dict(data)
# {'user': 'alice', 'token': '[REDACTED]', 'meta': {'api_key': '[REDACTED]'}}
```

### `sanitize_for_logging(value: Any) -> Any`

`sanitize_dict` for mappings, `sanitize_message` for strings, any other value unchanged.

## Configuration

### Sensitive headers

```python
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
```

### Sensitive keys

```python
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
```

### Token pattern

```python
TOKEN_PATTERN = re.compile(
    r"\bgh[a-z]_[A-Za-z0-9._-]{36,}"
    r"|\b[a-f0-9]{40,}\b"
    r"|\b[A-Za-z0-9+/]{40,}={0,2}\b",
    re.IGNORECASE,
)
```

**Matches**:

- GitHub tokens with a `gh?_` prefix (`ghp_`, `gho_`, `ghs_`, ...) followed by 36 or more
  characters from `A-Z a-z 0-9 . _ -`. The body allows `.`, `_` and `-` and the branch has no
  trailing word boundary, so a long JWT-style `ghs_` installation token is redacted whole, even
  when it ends in `-`.
- Hexadecimal strings of 40 or more characters.
- Base64-like strings of 40 or more characters, with optional `=` padding.

## Testing

**Test suite**: `tests/test_sanitization.py`, plus the doctests in `sanitization.py`.

The tests cover:

1. **Headers**: Authorization, API keys and cookies redacted; case-insensitive names; every name
   in `SENSITIVE_HEADERS`; empty input; the constant is immutable.
2. **Messages**: GitHub tokens, a dotted `ghs_` JWT-style token redacted whole, base64 sequences,
   several tokens in one message; short hex strings and plain text unchanged.
3. **Dictionaries**: sensitive keys, nested mappings, token patterns in values, non-string values
   passed through, empty input.
4. **`sanitize_for_logging`**: mappings, strings and other types.
5. **Scenarios**: real GitHub headers, an error message carrying a token, one placeholder value
   for every call.

## Best Practices

### For Developers

1. **Sanitize before logging**:
   ```python
   logger.info(sanitization.sanitize_message(message))
   ```

2. **Sanitize structured data**:
   ```python
   logger.debug(sanitization.sanitize_dict(request_data))
   ```

3. **Sanitize HTTP headers**:
   ```python
   safe_headers = sanitization.sanitize_headers(headers)
   logger.debug("Request headers: %s", safe_headers)
   ```

4. **Never log raw tokens**: log that authentication happens, never the token value.

### For Operations

1. **Log Rotation**: rotate and purge logs according to your retention policy.
2. **Access Control**: restrict log file access to authorized personnel.
3. **Audit**: periodically scan logs for leaked credentials (automated scanning recommended).

## Security Considerations

### What is redacted in log messages

- Authorization and API-key headers (`sanitize_headers`, `sanitize_dict`)
- GitHub tokens with a `gh?_` prefix
- Hexadecimal strings of 40 or more characters
- Base64-like strings of 40 or more characters
- Values of the keys listed in `SENSITIVE_KEYS` (exact, case-insensitive key match)

### What is not covered

- Hexadecimal strings shorter than 40 characters (for example abbreviated commit SHAs)
- Token formats that match none of the patterns
- Text that does not go through the logger: the progress lines written to stdout
  (`activate workflow <repo>/<file>`, `remove workflow run <repo>/<run_id>`) and the messages of
  the `RuntimeError`s the GitHub functions raise. Both are built from the owner, repository,
  workflow file, run id and, for errors, GitHub's error message or the `requests` exception text.
- Secrets inside tracebacks of third-party libraries (shown with `--traceback`)
- Binary or non-text data

### Limitations

1. **Pattern Matching**: sanitization relies on regex patterns; novel token formats may not be
   detected.
2. **Performance**: large dictionaries or very long messages cost regex processing time.
3. **Copies**: original objects are never modified; only the returned copies are sanitized.
4. **Text only**: only strings and mappings are sanitized.

## Incident Response

If credentials are discovered in logs:

1. **Immediate**:
   - Revoke the exposed token
   - Generate a new token with the minimal permissions the endpoints need
   - Update the repository secrets

2. **Investigation**:
   - Identify the log entry source (module, function, line)
   - Determine whether sanitization was bypassed or the pattern did not match
   - Check whether the logs were accessed by unauthorized parties

3. **Remediation**:
   - Update the sanitization patterns if a new token format was involved
   - Add a regression test for the specific case
   - Purge logs containing the exposed credential
   - Document it in the incident log

4. **Prevention**:
   - Review new logging statements in code review
   - Add pre-commit hooks checking for common token patterns
   - Enable secret scanning in CI (gitleaks, detect-secrets)

## References

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [GitHub Token Formats](https://github.blog/2021-04-05-behind-githubs-new-authentication-token-formats/)
- [NIST SP 800-53 AU-9: Protection of Audit Information](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
