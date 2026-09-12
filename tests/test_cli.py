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
               "aids", "sectors", "diag", "import-ref", "dry", "stat", "rain"}
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


# --- l'invocazione che parte davvero -----------------------------------------
# `python -m accoach <cmd>` era annunciato come uso principale e da un checkout
# col venv del progetto NON parte: il pacchetto non e' installato in editable
# (`pythonpath = ["src"]` vale solo sotto pytest), quindi si prende
# "No module named accoach". E' la riga che un beta tester copia da `help --all`.
# Misurata in pista il 01/09. Ora l'aiuto la ricava da come e' partito *questo*
# processo, e i tre modi devono dare tre stringhe DIVERSE: se collassassero, il
# rilevamento sarebbe verde e non proverebbe niente.

def test_invocation_frozen_exe_uses_the_exe_name():
    assert cli.invocation(r"C:\HONE\HONE.exe", frozen=True) == "HONE.exe"


def test_invocation_from_a_source_checkout_uses_the_launcher_script():
    got = cli.invocation("/home/x/ACCoach/accoach_main.py", frozen=False)
    assert got == "python accoach_main.py"


def test_invocation_as_an_installed_module():
    # `python -m accoach` mette in argv[0] il percorso di __main__.py.
    got = cli.invocation("/usr/lib/python3.12/site-packages/accoach/__main__.py",
                         frozen=False)
    assert got == "python -m accoach"


def test_the_four_invocations_are_four_different_strings():
    four = {
        cli.invocation(r"C:\HONE\HONE.exe", frozen=True),
        cli.invocation(r"C:\src\ACCoach\accoach_main.py", frozen=False),
        cli.invocation(r"C:\src\ACCoach\src\accoach\__main__.py", frozen=False),
        cli.invocation(r"C:\w\src\accoach\__main__.py", frozen=False,
                       sibling_script=Path(r"C:\w\accoach_main.py")),
    }
    assert len(four) == 4, four


# Il ripiego era `python -m accoach`, e su questa macchina un `.pth` in
# user-site mette `progetti/ACCoach/src` in sys.path: da un worktree quel
# comando NON fallisce, gira sull'albero sbagliato e stampa l'aiuto di un altro
# checkout. E' peggio di un errore perche' e' silenzioso — la stessa trappola
# del 10/08. Se `accoach_main.py` e' accanto a noi, la risposta e' quello.

def test_il_ripiego_non_consiglia_mai_un_albero_diverso_da_questo():
    got = cli.invocation(r"C:\worktree\src\accoach\__main__.py", frozen=False,
                         sibling_script=Path(r"C:\worktree\accoach_main.py"))
    assert got == r"python C:\worktree\accoach_main.py"
    # Il punto non e' la forma della stringa: e' che NON puo' eseguire altro.
    assert "-m accoach" not in got


def test_il_ripiego_resta_il_modulo_solo_se_non_c_e_uno_script_accanto():
    got = cli.invocation("/usr/lib/python3.12/site-packages/accoach/__main__.py",
                         frozen=False, sibling_script=None)
    assert got == "python -m accoach"


def test_lo_script_accanto_e_quello_dell_albero_in_cui_giriamo():
    """La proprieta' vera: il comando consigliato deve stare nello stesso albero
    del modulo che lo stampa. Qui si misura sull'albero reale, non su un finto."""
    script = cli._checkout_script()
    assert script is not None, "questo checkout ha accoach_main.py, va trovato"
    assert script.is_file()
    # Stesso albero del modulo che sta girando, non un altro checkout.
    assert script.parent == Path(cli.__file__).resolve().parents[2]
    assert str(script) in cli.invocation(cli.__file__, frozen=False,
                                         sibling_script=script)


def test_invocation_without_an_argv0_falls_back_to_the_module_form():
    assert cli.invocation("", frozen=False) == "python -m accoach"


def test_help_texts_carry_the_invocation_of_this_process(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "argv",
                        [r"C:\src\ACCoach\accoach_main.py", "help", "--all"])
    cli.main()
    out = capsys.readouterr().out
    assert "python accoach_main.py <command>" in out
    # Entrambi i testi, non solo il primo: la riga si copia anche da `--all`.
    assert "python accoach_main.py setup bump --help" in out
    # E non annuncia piu' l'invocazione che da un checkout non parte.
    assert "python -m accoach" not in out


def test_help_texts_carry_the_exe_name_when_frozen(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "argv", [r"C:\Program Files\HONE\HONE.exe", "help"])
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    cli.main()
    out = capsys.readouterr().out
    assert "HONE.exe <command>" in out
    assert "python" not in out
