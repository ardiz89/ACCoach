"""Lo script del firewall si prova solo leggendone il testo.

Non si esegue mai, nemmeno con -WhatIf: cambia il firewall e la rete di Windows.
Qui si controlla la struttura: il profilo della rete non lo cambia lo script da
solo, e un profilo Public non fa chiedere l'elevazione a ogni avvio.
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "setup_firewall.ps1"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _code() -> str:
    """Il testo senza commenti di riga e senza il blocco di aiuto iniziale."""
    t = re.sub(r"<#.*?#>", "", _text(), count=1, flags=re.S)
    return "\n".join(re.sub(r"(^|\s)#.*$", "", ln) for ln in t.splitlines())


def _block_after(code: str, header: str) -> str:
    """Il corpo `{ ... }` che segue la prima occorrenza di `header`, con le graffe bilanciate."""
    i = code.index(header)
    j = code.index("{", i)
    depth = 0
    for k in range(j, len(code)):
        if code[k] == "{":
            depth += 1
        elif code[k] == "}":
            depth -= 1
            if depth == 0:
                return code[j + 1:k]
    raise AssertionError("graffe non bilanciate")


def test_il_profilo_si_cambia_solo_a_mano_e_dopo_un_si():
    code = _code()
    assert len(re.findall(r"Set-NetConnectionProfile", code)) == 1
    # risalendo, almeno uno degli if che lo racchiudono ha -not $Auto
    before = code[:code.index("Set-NetConnectionProfile")]
    enclosing = before[before.rindex("$profilePublic"):]
    assert re.search(r"-not\s+\$Auto", enclosing)
    # domanda con Read-Host, risposta sì solo con y/Y; vuoto = no
    assert re.search(r"Read-Host[^\n]*\[y/N\]", enclosing)
    assert re.search(r"-match\s+'\^\[yY\]\$'|-cmatch\s+'\^y\$'|-ieq\s+'y'|-eq\s+'y'", enclosing)
    assert "Read-Host" in enclosing   # prima del cmdlet, che sta dopo `enclosing`


def test_in_auto_una_rete_public_non_chiede_l_elevazione():
    code = _code()
    gate = _block_after(code, "if ($Auto -and -not $Undo)")
    # il controllo «c'è già tutto?» non guarda più il profilo
    assert re.search(r"if\s*\(\s*Test-RuleReady\s*\)\s*\{\s*exit 0", gate)
    assert "profilePublic" not in gate


def test_in_auto_una_rete_public_lo_dice_dopo_aver_creato_la_regola():
    code = _code()
    created = code.index("New-NetFirewallRule")
    after = code[created:]
    m = re.search(r"if\s*\(\s*\$profilePublic\s+-and\s+\$Auto\s*\)", after)
    assert m, "manca l'avviso in -Auto dopo la creazione della regola"
    body = _block_after(after, m.group(0))
    assert len(re.findall(r"Write-Host", body)) == 2


def test_la_regola_resta_private_domain_localsubnet():
    code = _code()
    assert re.search(r"-Profile\s+Private,\s*Domain\b", code)
    assert re.search(r"-RemoteAddress\s+LocalSubnet", code)
    assert not re.search(r"-Profile[^\n]*Public", code)


def test_la_descrizione_dice_il_comportamento_nuovo():
    head = re.search(r"<#.*?#>", _text(), flags=re.S).group(0)
    assert "moves the active network" not in head
    assert re.search(r"never changes the network profile", head)
