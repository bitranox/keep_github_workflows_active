# Security Documentation

## Overview

This document describes the security measures implemented in `keep_github_workflows_active` to protect sensitive credentials and prevent secret leakage.

## Credential Sanitization

### Problem Statement

GitHub API interactions require authentication tokens that must never appear in log files, monitoring systems, or error messages. Prior to v2.1, logging calls could inadvertently expose:

- Personal access tokens in HTTP headers
- Tokens embedded in error messages
- API keys in structured logs

### Solution

The `sanitization` module provides comprehensive protection against credential leakage through automatic redaction of sensitive data before it reaches logging systems.

## Sanitization Module

**Location**: `src/keep_github_workflows_active/sanitization.py`

### Core Functions

#### `sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]`

Redacts authentication headers while preserving safe metadata.

**Protected Headers**:
- Authorization
- X-API-Key / API-Key
- X-Auth-Token / Auth-Token
- Cookie / Set-Cookie

**Example**:
```python
headers = {
    "Authorization": "Bearer ghp_ExampleToken123456",
    "Accept": "application/json"
}
sanitized = sanitize_headers(headers)
# Result: {"Authorization": "[REDACTED]", "Accept": "application/json"}
```

#### `sanitize_message(text: str) -> str`

Scrubs token-like patterns from text using regex detection.

**Protected Patterns**:
- GitHub tokens (ghp_, gho_, ghs_, etc.)
- Long hexadecimal strings (40+ characters)
- Base64-encoded sequences (40+ characters)

**Example**:
```python
msg = "Error: token ghp_1234567890abcdefABCDEF1234567890abcdefAB invalid"
sanitized = sanitize_message(msg)
# Result: "Error: token [REDACTED] invalid"
```

#### `sanitize_dict(data: Mapping[str, Any]) -> dict[str, Any]`

Recursively sanitizes dictionary structures, protecting both sensitive keys and token patterns in values.

**Protected Keys**:
- authorization, api_key, token, secret
- password, passwd, pwd
- credential, credentials
- access_token, auth_token

**Example**:
```python
data = {
    "user": "alice",
    "token": "ghp_secret123",
    "meta": {"api_key": "xyz789"}
}
sanitized = sanitize_dict(data)
# Result: {
#     "user": "alice",
#     "token": "[REDACTED]",
#     "meta": {"api_key": "[REDACTED]"}
# }
```

#### `sanitize_for_logging(value: Any) -> Any`

Convenience wrapper that auto-detects the input type and applies appropriate sanitization.

## Usage in Codebase

All logging calls in `keep_github_workflow_active.py` wrap their messages with `sanitization.sanitize_message()`:

```python
# Before (unsafe)
logger.info(f"Found {count} repositories for user {owner}")
logger.error(f"ERROR: {error_message}")

# After (safe)
logger.info(sanitization.sanitize_message(
    f"Found {count} repositories for user {owner}"
))
logger.error(sanitization.sanitize_message(f"ERROR: {error_message}"))
```

## Testing

**Test Coverage**: 100% of sanitization module
**Test Suite**: `tests/test_sanitization.py`

### Test Categories

1. **Header Sanitization** (7 tests)
   - Authorization headers
   - API keys
   - Cookies
   - Case-insensitive matching
   - Edge cases (empty dicts)

2. **Message Sanitization** (6 tests)
   - GitHub token patterns
   - Base64 sequences
   - Multiple tokens
   - Short strings (preserved)
   - Normal text (unchanged)

3. **Dictionary Sanitization** (5 tests)
   - Sensitive key detection
   - Nested structures
   - Token patterns in values
   - Non-string values (pass-through)

4. **Integration Tests** (3 tests)
   - Real GitHub headers
   - Error message scenarios
   - Consistency checks

5. **Doctests** (9 tests)
   - Inline examples in docstrings

## Configuration

### Sensitive Headers (Frozenset)

```python
SENSITIVE_HEADERS = frozenset([
    "authorization",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "auth-token",
    "cookie",
    "set-cookie",
])
```

### Sensitive Keys (Frozenset)

```python
SENSITIVE_KEYS = frozenset([
    "authorization", "api_key", "api-key", "apikey",
    "token", "auth_token", "auth-token",
    "access_token", "access-token",
    "secret", "password", "passwd", "pwd",
    "credential", "credentials",
])
```

### Token Pattern (Regex)

```python
TOKEN_PATTERN = re.compile(
    r"\b(gh[a-z]_[A-Za-z0-9]{36,}|[a-f0-9]{40,}|[A-Za-z0-9+/]{40,}={0,2})\b",
    re.IGNORECASE,
)
```

**Matches**:
- `ghp_`, `gho_`, `ghs_` (GitHub tokens)
- Long hex strings (40+ chars)
- Base64 sequences (40+ chars with optional padding)

## Best Practices

### For Developers

1. **Always sanitize before logging**:
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
   logger.debug(f"Request headers: {safe_headers}")
   ```

4. **Never log raw tokens**:
   ```python
   # WRONG
   logger.info(f"Using token: {github_token}")

   # RIGHT
   logger.info("Authenticating with GitHub API")
   ```

### For Operations

1. **Log Rotation**: Ensure existing logs are rotated and purged according to retention policies
2. **Access Control**: Restrict log file access to authorized personnel only
3. **Audit**: Periodically review logs for any leaked credentials (automated scanning recommended)

## Security Considerations

### What is Protected

- ✅ HTTP Authorization headers
- ✅ API keys and tokens
- ✅ GitHub personal access tokens (ghp_*, gho_*, etc.)
- ✅ Long hexadecimal strings (potential tokens)
- ✅ Base64-encoded secrets
- ✅ Dictionary keys containing "password", "secret", "token", etc.

### What is NOT Protected

- ⚠️ Short hexadecimal strings (<40 chars) - may be commit SHAs
- ⚠️ Custom token formats not matching known patterns
- ⚠️ Credentials in binary formats or non-text logs
- ⚠️ Secrets in stack traces from third-party libraries

### Limitations

1. **Pattern Matching**: Sanitization relies on regex patterns; novel token formats may not be detected
2. **Performance**: Large dictionaries or very long messages incur regex processing overhead
3. **Mutations**: Original objects are never modified; only copies are sanitized
4. **Binary Data**: Only text/string sanitization is supported

## Incident Response

If credentials are discovered in logs:

1. **Immediate**:
   - Revoke the exposed token immediately
   - Generate a new token with minimal required permissions
   - Update repository secrets

2. **Investigation**:
   - Identify the log entry source (module, function, line)
   - Determine if sanitization was bypassed or pattern not detected
   - Check if logs were accessed by unauthorized parties

3. **Remediation**:
   - Update sanitization patterns if new token format detected
   - Add regression test for the specific case
   - Purge logs containing the exposed credential
   - Document in incident log

4. **Prevention**:
   - Review all new logging statements in code reviews
   - Add pre-commit hooks checking for common token patterns
   - Enable secret scanning in CI (gitleaks, detect-secrets)

## Compliance

### GDPR / Privacy

While this module focuses on credential protection, the same patterns apply to PII:
- Email addresses
- API keys tied to individuals
- User authentication tokens

### SOC 2 / ISO 27001

Sanitization supports compliance requirements:
- Access control to sensitive data
- Logging without credential exposure
- Audit trail preservation without security risks

## Changelog

### v2.1.0 (2025-10-29)
- Initial sanitization module implementation
- Added comprehensive test suite (31 tests)
- Integrated into all logging calls in `keep_github_workflow_active.py`
- Documented security practices

## References

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [GitHub Token Formats](https://github.blog/2021-04-05-behind-githubs-new-authentication-token-formats/)
- [NIST SP 800-53 AU-9: Protection of Audit Information](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
