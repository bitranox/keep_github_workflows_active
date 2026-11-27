"""Diagnostic behaviors behind the CLI's ``hello`` and ``fail`` commands.

Purpose
-------
Provide a deterministic success path and a deterministic failure path, so
packaging checks, smoke tests and the traceback handling of the CLI can be
exercised without calling the GitHub API.

Contents
--------
* :func:`emit_greeting` - writes the canonical greeting (``hello``).
* :func:`raise_intentional_failure` - raises ``RuntimeError`` (``fail``) to
  exercise exit codes and traceback output.
* :func:`noop_main` - does nothing; the CLI runs it when only
  ``--traceback`` / ``--no-traceback`` is given without a subcommand.

System Role
-----------
The workflow maintenance logic lives in
:mod:`keep_github_workflows_active.keep_github_workflow_active`; this module
holds only the diagnostic helpers, which the package root re-exports.
"""

from __future__ import annotations

import sys
from typing import TextIO

CANONICAL_GREETING = "Hello World"


def _target_stream(preferred: TextIO | None) -> TextIO:
    """Return the stream that should hear the greeting."""

    return preferred if preferred is not None else sys.stdout


def _greeting_line() -> str:
    """Return the greeting exactly as it should appear."""

    return f"{CANONICAL_GREETING}\n"


def _flush_if_possible(stream: TextIO) -> None:
    """Flush the stream when the stream knows how to flush."""

    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()


def emit_greeting(*, stream: TextIO | None = None) -> None:
    """Write the canonical greeting to the provided text stream.

    Why
        Provide a deterministic success path that the documentation, smoke
        tests, and packaging checks can rely on without calling the GitHub API.

    What
        Writes :data:`CANONICAL_GREETING` followed by a newline to the target
        stream.

    Parameters
    ----------
    stream:
        Optional text stream receiving the greeting. Defaults to
        :data:`sys.stdout` when ``None``.

    Side Effects
        Writes to the target stream and flushes it when a ``flush`` attribute is
        available.

    Examples
    --------
    >>> from io import StringIO
    >>> buffer = StringIO()
    >>> emit_greeting(stream=buffer)
    >>> buffer.getvalue() == "Hello World\\n"
    True
    """

    target = _target_stream(stream)
    target.write(_greeting_line())
    _flush_if_possible(target)


def raise_intentional_failure() -> None:
    """Raise ``RuntimeError`` so transports can exercise failure flows.

    Why
        CLI commands and tests need a guaranteed failure scenario to ensure the
        shared exit-code helpers and traceback toggles remain correct.

    What
        Always raises ``RuntimeError`` with the message ``"I should fail"``.

    Side Effects
        None beyond raising the exception.

    Raises
        RuntimeError: Regardless of input.

    Examples
    --------
    >>> raise_intentional_failure()
    Traceback (most recent call last):
    ...
    RuntimeError: I should fail
    """

    raise RuntimeError("I should fail")


def noop_main() -> None:
    """Do nothing; the default action of the CLI root command.

    Why
        The CLI runs this when it is called with only ``--traceback`` or
        ``--no-traceback`` and no subcommand (see ``cli.cli_main``), so that
        invocation succeeds without side effects.

    What
        Performs no work and returns immediately.

    Side Effects
        None.

    Examples
    --------
    >>> noop_main()
    """

    return None


__all__ = [
    "CANONICAL_GREETING",
    "emit_greeting",
    "noop_main",
    "raise_intentional_failure",
]
