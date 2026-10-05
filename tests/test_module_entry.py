"""Module entry stories ensuring `python -m` mirrors the CLI."""

from __future__ import annotations

import importlib
import runpy
import sys
from typing import TYPE_CHECKING

import lib_cli_exit_tools
import pytest

from keep_github_workflows_active import cli as cli_mod

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    "argv",
    [["--bad-flag"], ["no-such-command"], ["info", "--bad-flag"], ["--help"], ["info"]],
    ids=["bad-flag", "unknown-command", "bad-subcommand-flag", "help", "info"],
)
def test_module_entry_exits_with_the_code_the_console_script_gives(monkeypatch: pytest.MonkeyPatch, isolated_traceback_config: None, argv: list[str]) -> None:
    script_code = cli_mod.main(argv)
    monkeypatch.setattr(sys, "argv", ["keep_github_workflows_active", *argv])

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("keep_github_workflows_active.__main__", run_name="__main__")

    assert exc.value.code == script_code


@pytest.mark.os_agnostic
def test_a_usage_error_exits_with_the_click_usage_code_via_module_entry(monkeypatch: pytest.MonkeyPatch, isolated_traceback_config: None) -> None:
    monkeypatch.setattr(sys, "argv", ["keep_github_workflows_active", "--bad-flag"])

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("keep_github_workflows_active.__main__", run_name="__main__")

    assert exc.value.code == 2


@pytest.mark.os_agnostic
def test_when_traceback_flag_is_used_via_module_entry_the_full_poem_is_printed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    strip_ansi: Callable[[str], str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["keep_github_workflows_active", "--traceback", "fail"])
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False, raising=False)
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback_force_color", False, raising=False)

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("keep_github_workflows_active.__main__", run_name="__main__")

    plain_err = strip_ansi(capsys.readouterr().err)

    assert exc.value.code != 0
    assert "Traceback (most recent call last)" in plain_err
    assert "RuntimeError: I should fail" in plain_err
    assert "[TRUNCATED" not in plain_err
    assert lib_cli_exit_tools.config.traceback is False
    assert lib_cli_exit_tools.config.traceback_force_color is False


@pytest.mark.os_agnostic
def test_when_the_module_is_imported_it_runs_nothing() -> None:
    # Left imported, every later runpy of the module warns that it is already loaded.
    previous = sys.modules.pop("keep_github_workflows_active.__main__", None)
    try:
        module = importlib.import_module("keep_github_workflows_active.__main__")

        assert module.cli is cli_mod
    finally:
        sys.modules.pop("keep_github_workflows_active.__main__", None)
        if previous is not None:
            sys.modules["keep_github_workflows_active.__main__"] = previous
