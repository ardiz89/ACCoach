"""CLI front door: what a driver is shown, and what stays reachable.

The point of the split help is that a driver sees three commands. The point of
*this* test is that hiding the rest never turns into losing them: every command
the dispatcher accepts has to be documented in one of the two texts.
"""
import re
from pathlib import Path

import accoach.__main__ as cli

_DRIVER_COMMANDS = ("live", "web", "launcher")
_SOURCE = Path(cli.__file__).read_text(encoding="utf-8")


def _dispatched_commands() -> set[str]:
    """Every command string the dispatcher compares against, read from its source.

    Reflective on purpose: a hand-written list here would be one more thing to
    forget to update, which is exactly the failure this test is meant to catch.
    """
    body = _SOURCE.split("def main(")[1]
    single = re.findall(r'cmd == "([a-z-]+)"', body)
    grouped = re.findall(r"cmd in \(([^)]*)\)", body)
    return set(single) | {
        c for g in grouped for c in re.findall(r'"([a-z-]+)"', g)
    }


def test_default_help_shows_only_the_driver_commands():
    for c in _DRIVER_COMMANDS:
        assert re.search(rf"^  {c}\b", cli._HELP, re.M), c
    # The tools are not in the driver's way.
    assert "verify-g" not in cli._HELP
    assert "server" not in cli._HELP


def test_default_help_says_where_the_rest_are():
    assert "help --all" in cli._HELP


def test_every_dispatched_command_is_documented_somewhere():
    documented = cli._HELP + cli._HELP_TOOLS
    # Aliases and help flags are dispatch targets but not commands to advertise.
    aliases = {"gui", "help", "-h", "--help", "all", "tools", "gaxis", "yaw",
               "aids", "sectors", "diag", "import-ref", "dry", "stat"}
    for cmd in _dispatched_commands() - aliases:
        assert re.search(rf"^  {re.escape(cmd)}\b", documented, re.M), cmd


def test_help_all_prints_both_halves(capsys):
    cli.sys.argv = ["accoach", "help", "--all"]
    cli.main()
    out = capsys.readouterr().out
    assert "launcher" in out and "verify-sectors" in out


def test_plain_help_does_not_print_the_tools(capsys):
    cli.sys.argv = ["accoach", "help"]
    cli.main()
    out = capsys.readouterr().out
    assert "verify-sectors" not in out
