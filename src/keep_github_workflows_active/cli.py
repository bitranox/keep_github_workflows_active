"""CLI adapter wiring the GitHub maintenance functions into a rich-click interface.

Purpose
-------
Expose the two maintenance commands (``enable-all-workflows`` and
``delete-old-workflow-runs``, backed by
:mod:`keep_github_workflows_active.keep_github_workflow_active`) and the
diagnostic commands (``info``, ``hello``, ``fail``, backed by
:mod:`keep_github_workflows_active.behaviors` and ``__init__conf__``) behind one
command group, with exit codes and traceback output handled by
``lib_cli_exit_tools``. ``docs/systemdesign/module_reference.md`` describes the
wiring.

Contents
--------
* :class:`CliContextObject` - typed ``ctx.obj`` holding the traceback flag.
* :data:`CLICK_CONTEXT_SETTINGS` - shared Click settings ensuring consistent
  ``--help`` behavior across commands.
* :func:`apply_traceback_preferences` - helper that synchronises the shared
  traceback configuration flags.
* :func:`snapshot_traceback_state` / :func:`restore_traceback_state` - utilities
  for preserving and reapplying the global traceback preference
  (:class:`TracebackState`).
* :func:`cli` - root command group wiring the global options.
* :func:`cli_main` - default action when only ``--traceback`` /
  ``--no-traceback`` is given without a subcommand.
* :func:`cli_enable_all_workflows`, :func:`cli_delete_old_workflow_runs` - the
  maintenance subcommands; :func:`_fallback_owner` / :func:`_fallback_token`
  fill a missing ``--owner`` / ``--token`` from the environment or ``.env``.
* :func:`cli_info`, :func:`cli_hello`, :func:`cli_fail` - subcommands covering
  metadata printing, success path, and failure path.
* :func:`_no_subcommand_requested`, :func:`_traceback_option_requested`,
  :func:`_show_help` - decide between the help screen and :func:`cli_main`.
* :func:`_record_traceback_choice`, :func:`_announce_traceback_choice` - persist
  traceback preferences across context and shared tooling.
* :func:`_invoke_cli`, :func:`_current_traceback_mode`, :func:`_traceback_limit`,
  :func:`_print_exception`, :func:`_run_cli_via_exit_tools` - isolate the error
  handling and delegation path.
* :func:`_restore_when_requested` - restores tracebacks when ``main`` finishes.
* :func:`main` - composition helper delegating to ``lib_cli_exit_tools`` while
  honouring the shared traceback preferences.

System Role
-----------
The CLI is the package's entry point: both console scripts declared in
``[project.scripts]`` and ``python -m keep_github_workflows_active`` run
:func:`main`, so behaviour is identical regardless of entry point. The program
name shown in help and ``--version`` comes from
:mod:`keep_github_workflows_active.__init__conf__`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, NamedTuple

import lib_cli_exit_tools
import rich_click as click
from click.core import ParameterSource

from . import __init__conf__
from . import keep_github_workflow_active as keep_active
from .behaviors import emit_greeting, noop_main, raise_intentional_failure
from .typed_click import option, version_option

if TYPE_CHECKING:
    from collections.abc import Sequence

# =============================================================================
# Dataclass for typed Click context object
# =============================================================================


@dataclass(slots=True)
class CliContextObject:
    """Typed context object for Click commands."""

    traceback: bool = False


#: Shared Click context flags so help output stays consistent across commands.
CLICK_CONTEXT_SETTINGS: dict[str, list[str]] = {"help_option_names": ["-h", "--help"]}
#: Character budget used when printing truncated tracebacks.
TRACEBACK_SUMMARY_LIMIT: Final[int] = 500
#: Character budget used when verbose tracebacks are enabled.
TRACEBACK_VERBOSE_LIMIT: Final[int] = 10_000


class TracebackState(NamedTuple):
    """Typed state for traceback configuration."""

    traceback_enabled: bool
    force_color: bool


def _fallback_owner(owner: str | None) -> str:
    try:
        return owner or keep_active.get_owner()
    except RuntimeError as exc:  # pragma: no cover - handled by Click
        raise click.ClickException(str(exc)) from exc


def _fallback_token(token: str | None) -> str:
    try:
        return token or keep_active.get_github_token()
    except RuntimeError as exc:  # pragma: no cover - handled by Click
        raise click.ClickException(str(exc)) from exc


def apply_traceback_preferences(*, enabled: bool) -> None:
    """Synchronise shared traceback flags with the requested preference.

    Why
        ``lib_cli_exit_tools`` inspects global flags to decide whether tracebacks
        should be truncated and whether colour should be forced. Updating both
        attributes together ensures the ``--traceback`` flag behaves the same for
        console scripts and ``python -m`` execution.

    Parameters
    ----------
    enabled:
        ``True`` enables full tracebacks with colour. ``False`` restores the
        compact summary mode.

    Examples
    --------
    >>> apply_traceback_preferences(enabled=True)
    >>> bool(lib_cli_exit_tools.config.traceback)
    True
    >>> bool(lib_cli_exit_tools.config.traceback_force_color)
    True
    """

    lib_cli_exit_tools.config.traceback = bool(enabled)
    lib_cli_exit_tools.config.traceback_force_color = bool(enabled)


def snapshot_traceback_state() -> TracebackState:
    """Capture the current traceback configuration for later restoration.

    Returns
    -------
    TracebackState
        NamedTuple with ``traceback_enabled`` and ``force_color`` fields.

    Examples
    --------
    >>> snapshot = snapshot_traceback_state()
    >>> isinstance(snapshot, tuple)
    True
    """

    return TracebackState(
        traceback_enabled=bool(getattr(lib_cli_exit_tools.config, "traceback", False)),
        force_color=bool(getattr(lib_cli_exit_tools.config, "traceback_force_color", False)),
    )


def restore_traceback_state(state: TracebackState) -> None:
    """Reapply a previously captured traceback configuration.

    Parameters
    ----------
    state:
        NamedTuple returned by :func:`snapshot_traceback_state`.

    Examples
    --------
    >>> prev = snapshot_traceback_state()
    >>> apply_traceback_preferences(enabled=True)
    >>> restore_traceback_state(prev)
    >>> snapshot_traceback_state() == prev
    True
    """

    lib_cli_exit_tools.config.traceback = state.traceback_enabled
    lib_cli_exit_tools.config.traceback_force_color = state.force_color


def _record_traceback_choice(ctx: click.Context, *, enabled: bool) -> None:
    """Remember the chosen traceback mode inside the Click context.

    Why
        Downstream commands need to know whether verbose tracebacks were
        requested so they can honour the user's preference without re-parsing
        flags.

    What
        Ensures the context has a typed CliContextObject and persists the boolean
        in the ``traceback`` attribute.

    Inputs
        ctx:
            Click context associated with the current invocation.
        enabled:
            ``True`` when verbose tracebacks were requested; ``False`` otherwise.

    Side Effects
        Mutates ``ctx.obj``.
    """

    if ctx.obj is None or not isinstance(ctx.obj, CliContextObject):
        ctx.obj = CliContextObject()
    ctx.obj.traceback = enabled


def _announce_traceback_choice(*, enabled: bool) -> None:
    """Keep ``lib_cli_exit_tools`` in sync with the selected traceback mode.

    Why
        ``lib_cli_exit_tools`` reads global configuration to decide how to print
        tracebacks; we mirror the user's choice into that configuration.

    Inputs
        enabled:
            ``True`` when verbose tracebacks should be shown; ``False`` when the
            summary view is desired.

    Side Effects
        Mutates ``lib_cli_exit_tools.config``.
    """

    apply_traceback_preferences(enabled=enabled)


def _no_subcommand_requested(ctx: click.Context) -> bool:
    """Return ``True`` when the invocation did not name a subcommand.

    Why
        Without a subcommand the CLI prints its help or, with an explicit
        traceback flag, calls ``noop_main``; we need a readable predicate to
        capture that branch.

    Inputs
        ctx:
            Click context describing the current CLI invocation.

    Outputs
        bool:
            ``True`` when no subcommand was invoked; ``False`` otherwise.
    """

    return ctx.invoked_subcommand is None


def _invoke_cli(argv: Sequence[str] | None) -> int:
    """Ask ``lib_cli_exit_tools`` to execute the Click command.

    Why
        ``lib_cli_exit_tools`` normalises exit codes and exception handling; we
        centralise the call so tests can stub it cleanly.

    Inputs
        argv:
            Sequence of command-line arguments. ``None`` delegates to
            ``sys.argv`` inside ``lib_cli_exit_tools``.

    Outputs
        int:
            Exit code returned by the CLI execution.
    """

    return lib_cli_exit_tools.run_cli(
        cli,
        argv=list(argv) if argv is not None else None,
        prog_name=__init__conf__.shell_command,
    )


def _current_traceback_mode() -> bool:
    """Return the global traceback preference as a boolean.

    Why
        Error handling logic needs to know whether verbose tracebacks are active
        so it can pick the right character budget and ensure colouring is
        consistent.

    Outputs
        bool:
            ``True`` when verbose tracebacks are enabled; ``False`` otherwise.
    """

    return bool(getattr(lib_cli_exit_tools.config, "traceback", False))


def _traceback_limit(*, tracebacks_enabled: bool, summary_limit: int, verbose_limit: int) -> int:
    """Return the character budget that matches the current traceback mode.

    Why
        Verbose tracebacks should show the full story while compact ones keep the
        terminal tidy. This helper makes that decision explicit.

    Inputs
        tracebacks_enabled:
            ``True`` when verbose tracebacks are active.
        summary_limit:
            Character budget for truncated output.
        verbose_limit:
            Character budget for the full traceback.

    Outputs
        int:
            The applicable character limit.
    """

    return verbose_limit if tracebacks_enabled else summary_limit


def _print_exception(exc: BaseException, *, tracebacks_enabled: bool, length_limit: int) -> int:
    """Render the exception through ``lib_cli_exit_tools`` and return its exit code.

    Why
        All transports funnel errors through ``lib_cli_exit_tools`` so that exit
        codes and formatting stay consistent; this helper keeps the plumbing in
        one place.

    Inputs
        exc:
            Exception raised by the CLI.
        tracebacks_enabled:
            ``True`` when verbose tracebacks should be shown.
        length_limit:
            Maximum number of characters to print.

    Outputs
        int:
            Exit code to surface to the shell.

    Side Effects
        Writes the formatted exception to stderr via ``lib_cli_exit_tools``.
    """

    lib_cli_exit_tools.print_exception_message(
        trace_back=tracebacks_enabled,
        length_limit=length_limit,
    )
    return lib_cli_exit_tools.get_system_exit_code(exc)


def _traceback_option_requested(ctx: click.Context) -> bool:
    """Return ``True`` when the user explicitly requested ``--traceback``.

    Why
        Determines whether a no-command invocation should run the default
        behaviour or display the help screen.

    Inputs
        ctx:
            Click context associated with the current invocation.

    Outputs
        bool:
            ``True`` when the user provided ``--traceback`` or ``--no-traceback``;
            ``False`` when the default value is in effect.
    """

    source = ctx.get_parameter_source("traceback")
    return source not in (ParameterSource.DEFAULT, None)


def _show_help(ctx: click.Context) -> None:
    """Render the command help to stdout."""

    click.echo(ctx.get_help())


def _run_cli_via_exit_tools(
    argv: Sequence[str] | None,
    *,
    summary_limit: int,
    verbose_limit: int,
) -> int:
    """Run the command while narrating the failure path with care.

    Why
        Consolidates the call to ``lib_cli_exit_tools`` so happy paths and error
        handling remain consistent across the application and tests.

    Inputs
        argv:
            Sequence of CLI arguments when provided.
        summary_limit / verbose_limit:
            Character budgets steering exception output length.

    Outputs
        int:
            Exit code produced by the command.

    Side Effects
        Delegates to ``lib_cli_exit_tools`` which may write to stderr.
    """

    try:
        return _invoke_cli(argv)
    except BaseException as exc:
        tracebacks_enabled = _current_traceback_mode()
        apply_traceback_preferences(enabled=tracebacks_enabled)
        return _print_exception(
            exc,
            tracebacks_enabled=tracebacks_enabled,
            length_limit=_traceback_limit(
                tracebacks_enabled=tracebacks_enabled,
                summary_limit=summary_limit,
                verbose_limit=verbose_limit,
            ),
        )


@click.group(
    help=__init__conf__.title,
    context_settings=CLICK_CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@version_option(
    version=__init__conf__.version,
    prog_name=__init__conf__.shell_command,
    message=f"{__init__conf__.shell_command} version {__init__conf__.version}",
)
@option(
    "--traceback/--no-traceback",
    is_flag=True,
    default=False,
    help="Show full Python traceback on errors",
)
@click.pass_context
def cli(ctx: click.Context, *, traceback: bool) -> None:
    """Root command storing global flags and syncing shared traceback state.

    Why
        The CLI must provide a switch for verbose tracebacks so developers can
        toggle diagnostic depth without editing configuration files.

    What
        Ensures a :class:`CliContextObject` context, stores the ``traceback`` flag, and mirrors
        the value into ``lib_cli_exit_tools.config`` so downstream helpers observe
        the preference. Without a subcommand the command prints its help; when
        ``--traceback`` or ``--no-traceback`` is given without a subcommand it
        runs :func:`cli_main` instead.

    Side Effects
        Mutates :mod:`lib_cli_exit_tools.config` to reflect the requested
        traceback mode, including ``traceback_force_color`` when tracebacks are
        enabled.

    Examples
    --------
    >>> from click.testing import CliRunner
    >>> runner = CliRunner()
    >>> result = runner.invoke(cli, ["hello"])
    >>> result.exit_code
    0
    >>> "Hello World" in result.output
    True
    """

    _record_traceback_choice(ctx, enabled=traceback)
    _announce_traceback_choice(enabled=traceback)
    if _no_subcommand_requested(ctx):
        if _traceback_option_requested(ctx):
            cli_main()
        else:
            _show_help(ctx)


def cli_main() -> None:
    """Run the default action when no subcommand is given but a traceback flag is.

    Why
        ``--traceback`` or ``--no-traceback`` without a subcommand is a valid
        invocation; it runs this no-op instead of printing the help.

    Side Effects
        Delegates to :func:`noop_main`.

    Examples
    --------
    >>> cli_main()
    """

    noop_main()


@cli.command("info", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_info() -> None:
    """Print resolved metadata so users can inspect installation details."""

    __init__conf__.print_info()


@cli.command("hello", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_hello() -> None:
    """Demonstrate the success path by emitting the canonical greeting."""

    emit_greeting()


@cli.command("fail", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_fail() -> None:
    """Trigger the intentional failure helper to test error handling."""

    raise_intentional_failure()


@cli.command("enable-all-workflows", context_settings=CLICK_CONTEXT_SETTINGS)
@option(
    "--owner",
    metavar="OWNER",
    help="GitHub username owning the repositories (defaults to environment/.env)",
)
@option(
    "--token",
    metavar="TOKEN",
    help="Fine-grained personal access token (defaults to environment/.env)",
)
def cli_enable_all_workflows(owner: str | None, token: str | None) -> None:
    """Ensure every workflow in the configured account stays enabled."""

    resolved_owner = _fallback_owner(owner)
    resolved_token = _fallback_token(token)
    keep_active.enable_all_workflows(owner=resolved_owner, github_token=resolved_token)


@cli.command("delete-old-workflow-runs", context_settings=CLICK_CONTEXT_SETTINGS)
@option(
    "--owner",
    metavar="OWNER",
    help="GitHub username owning the repositories (defaults to environment/.env)",
)
@option(
    "--token",
    metavar="TOKEN",
    help="Fine-grained personal access token (defaults to environment/.env)",
)
@option(
    "--keep",
    metavar="COUNT",
    type=int,
    default=50,
    show_default=True,
    help="Number of recent workflow runs to retain per repository",
)
def cli_delete_old_workflow_runs(owner: str | None, token: str | None, keep: int) -> None:
    """Prune historic workflow runs while keeping the freshest executions."""

    resolved_owner = _fallback_owner(owner)
    resolved_token = _fallback_token(token)
    keep_active.delete_old_workflow_runs(
        owner=resolved_owner,
        github_token=resolved_token,
        number_of_workflow_runs_to_keep=keep,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    restore_traceback: bool = True,
    summary_limit: int = TRACEBACK_SUMMARY_LIMIT,
    verbose_limit: int = TRACEBACK_VERBOSE_LIMIT,
) -> int:
    """Execute the CLI with deliberate error handling and return the exit code.

    Why
        Provides the single entry point used by console scripts and
        ``python -m`` execution so that behaviour stays identical across
        transports.

    Inputs
        argv:
            Sequence of CLI arguments. ``None`` lets Click consume ``sys.argv``
            directly.
        restore_traceback:
            ``True`` to restore the prior ``lib_cli_exit_tools`` traceback
            configuration after execution.
        summary_limit / verbose_limit:
            Character budgets used when formatting exceptions.

    Outputs
        int:
            Exit code reported by the CLI run.

    Side Effects
        Mutates the global traceback configuration while the CLI runs.
    """

    previous_state = snapshot_traceback_state()
    try:
        return _run_cli_via_exit_tools(
            argv,
            summary_limit=summary_limit,
            verbose_limit=verbose_limit,
        )
    finally:
        _restore_when_requested(previous_state, should_restore=restore_traceback)


def _restore_when_requested(state: TracebackState, *, should_restore: bool) -> None:
    """Restore the prior traceback configuration when requested.

    Why
        CLI execution may toggle verbose tracebacks for the duration of the run.
        Once the command ends we restore the previous configuration so other
        code paths continue with their expected defaults.

    Inputs
        state:
            Tuple captured by :func:`snapshot_traceback_state` describing the
            prior configuration.
        should_restore:
            ``True`` to reapply the stored configuration; ``False`` to keep the
            current settings.

    Side Effects
        May mutate ``lib_cli_exit_tools.config``.
    """

    if should_restore:
        restore_traceback_state(state)
