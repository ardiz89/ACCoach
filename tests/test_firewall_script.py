"""Lo script del firewall si prova solo leggendone il testo.

Non si esegue mai, nemmeno con -WhatIf: cambia il firewall e la rete di Windows.
Qui si controlla la struttura: il profilo della rete non lo cambia lo script da
solo, e un profilo Public non fa chiedere l'elevazione a ogni avvio.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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


_INSPECT = r"""
param([string]$Path)
$e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$null, [ref]$e)
$cmds = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Set-NetConnectionProfile' }, $true))
$conds = @()
foreach ($cmd in $cmds) {
    $c = $cmd
    while ($c.Parent) {
        $p = $c.Parent
        if ($p -is [System.Management.Automation.Language.IfStatementAst]) {
            foreach ($cl in $p.Clauses) {
                if ($cl.Item2.Extent.StartOffset -le $cmd.Extent.StartOffset -and $cl.Item2.Extent.EndOffset -ge $cmd.Extent.EndOffset) {
                    $conds += $cl.Item1.Extent.Text
                }
            }
        }
        $c = $p
    }
}
$assign = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq '$answer' }, $true) |
    ForEach-Object { $_.Right.Extent.Text })
$gateIf = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.IfStatementAst] -and $n.Clauses[0].Item1.Extent.Text -eq '$Auto -and -not $Undo' }, $true) | Select-Object -First 1
$before = @(); $ready = @()
if ($gateIf) {
    foreach ($st in $gateIf.Clauses[0].Item2.Statements) {
        if ($st -is [System.Management.Automation.Language.IfStatementAst] -and $st.Clauses[0].Item1.Extent.Text -eq 'Test-RuleReady') {
            $ready = @($st.Clauses[0].Item2.Statements | ForEach-Object { $_.Extent.Text })
            break
        }
        $before += $st.Extent.Text
    }
}
[pscustomobject]@{
    count = $cmds.Count; conds = @($conds); assign = @($assign)
    gate_found = [bool]$gateIf; before = @($before); ready = @($ready); errors = @($e).Count
} | ConvertTo-Json -Compress -Depth 4
"""

_POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(_POWERSHELL is None, reason="powershell non disponibile")


def _inspect(path: Path, tmp_path: Path) -> dict:
    """Legge l'albero sintattico dello script con il parser di PowerShell, SENZA eseguirlo."""
    helper = tmp_path / "inspect.ps1"
    helper.write_text(_INSPECT, encoding="utf-8")
    out = subprocess.run(
        [_POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper), "-Path", str(path)],
        capture_output=True, text=True, timeout=60, check=True,
    ).stdout
    return json.loads(out)


def _mutant(tmp_path: Path, old: str, new: str) -> Path:
    """Una copia dello script con una modifica; mai il file vero."""
    text = _text().replace("\r\n", "\n")
    p = tmp_path / "mutant.ps1"
    p.write_text(text.replace(old, new), encoding="utf-8")
    return p


EXPECTED_CONDS = ["\"$answer\".Trim() -match '^(y|yes)$'", "-not $Auto", "$profilePublic"]


def _assert_profile_guarded(info: dict):
    assert info["errors"] == 0
    assert info["count"] == 1
    assert info["conds"] == EXPECTED_CONDS
    assert any("Read-Host" in a for a in info["assign"])


def _assert_gate_safe(info: dict):
    assert info["gate_found"]
    # prima del controllo «c'e' gia' tutto?» si puo' solo uscire
    for st in info["before"]:
        assert re.fullmatch(r"if \([^()]*\) \{ exit 0 \}", st), st
        assert "NetworkCategory" not in st and "profilePublic" not in st
    # dentro, solo l'avviso e l'uscita
    assert [s.replace("\r", "") for s in info["ready"]] == ["if ($profilePublic) { Write-PublicNotice }", "exit 0"]


@needs_ps
def test_il_profilo_si_cambia_solo_a_mano_e_dopo_un_si(tmp_path):
    _assert_profile_guarded(_inspect(SCRIPT, tmp_path))


@needs_ps
def test_in_auto_una_rete_public_non_chiede_l_elevazione(tmp_path):
    _assert_gate_safe(_inspect(SCRIPT, tmp_path))


@needs_ps
@pytest.mark.parametrize("old,new", [
    # (a) il cmdlet dopo un `if (-not $Auto) { }` chiuso
    ("    if (-not $Auto) {\n        Write-Host (\"'{0}' is set",
     "    if (-not $Auto) { }\n    if ($true) {\n        Write-Host (\"'{0}' is set"),
    # (b) un `if` vuoto sulla risposta, poi il cmdlet
    ("        if (\"$answer\".Trim() -match '^(y|yes)$') {\n",
     "        if (\"$answer\".Trim() -match '^(y|yes)$') { }\n        if ($true) {\n"),
    # (c) la risposta vuota vale si'
    ("-match '^(y|yes)$') {", "-match '^(y|yes)$' -or $answer -eq '') {"),
    # (d) il cmdlet nel ramo else
    ("            Write-Host 'Leaving the network on Public.'",
     "            Set-NetConnectionProfile -InterfaceIndex $route.ifIndex -NetworkCategory Private"),
])
def test_i_mutanti_del_profilo_falliscono(tmp_path, old, new):
    info = _inspect(_mutant(tmp_path, old, new), tmp_path)
    assert info["errors"] == 0, "il mutante deve essere sintatticamente valido"
    with pytest.raises(AssertionError):
        _assert_profile_guarded(info)


@needs_ps
def test_un_controllo_public_prima_del_gate_e_rilevato(tmp_path):
    # (e) un controllo sul profilo che prosegue verso l'elevazione prima di Test-RuleReady
    mutant = _mutant(
        tmp_path,
        "    if (Test-RuleReady) {",
        "    if ($profilePublic) { Write-Step 'x' }\n    if (Test-RuleReady) {",
    )
    info = _inspect(mutant, tmp_path)
    assert info["errors"] == 0
    with pytest.raises(AssertionError):
        _assert_gate_safe(info)



def test_in_auto_una_rete_public_lo_dice_dopo_aver_creato_la_regola():
    code = _code()
    created = code.index("New-NetFirewallRule")
    after = code[created:]
    m = re.search(r"if\s*\(\s*\$profilePublic\s+-and\s+\$Auto\s*\)", after)
    assert m, "manca l'avviso in -Auto dopo la creazione della regola"
    body = _block_after(after, m.group(0))
    assert "Write-PublicNotice" in body
    # il testo vive in una sola funzione, di due righe, usata anche al gate
    fn = _block_after(code, "function Write-PublicNotice")
    assert len(re.findall(r"Write-Host", fn)) == 2
    assert len(re.findall(r"Write-PublicNotice", code)) == 3   # definizione + gate + dopo la regola


def test_la_regola_resta_private_domain_localsubnet():
    code = _code()
    assert re.search(r"-Profile\s+Private,\s*Domain\b", code)
    assert re.search(r"-RemoteAddress\s+LocalSubnet", code)
    assert not re.search(r"-Profile[^\n]*Public", code)


def test_la_descrizione_dice_il_comportamento_nuovo():
    head = re.search(r"<#.*?#>", _text(), flags=re.S).group(0)
    assert "moves the active network" not in head
    assert re.search(r"never changes the network profile", head)
