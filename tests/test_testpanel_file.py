"""Le due letture che possono ingannare il pilota.

Un file letto mentre lo si sta scrivendo è un file rotto per una frazione di
secondo, e un file rimasto da ieri sera è un protocollo che non è più vero. Sono
i due modi in cui questo riquadro potrebbe mettere in pista una bugia
convincente, e sono l'unico motivo per cui `StepFile` esiste invece di una
`json.loads` in linea.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from accoach.testpanel import _STALE_S, StepFile


def _write(path, **step):
    path.write_text(json.dumps({"title": "X", **step}), encoding="utf-8")


def test_senza_file_non_c_e_passo(tmp_path):
    assert StepFile(tmp_path / "mai-scritto.json").read(now=1000.0) is None


def test_legge_il_passo(tmp_path):
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI")
    assert StepFile(p).read(now=os.path.getmtime(p))["title"] == "BLOCCAGGI"


def test_un_json_a_meta_lascia_sullo_schermo_quello_di_prima(tmp_path):
    """Il caso vero: si sta riscrivendo il file mentre il riquadro lo legge."""
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI")
    sf = StepFile(p)
    now = os.path.getmtime(p)
    assert sf.read(now)["title"] == "BLOCCAGGI"

    p.write_text('{"title": "STI', encoding="utf-8")   # scrittura a metà
    os.utime(p, (now + 1, now + 1))
    assert sf.read(now + 1)["title"] == "BLOCCAGGI"


def test_un_passo_senza_titolo_non_sostituisce_quello_buono(tmp_path):
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI")
    sf = StepFile(p)
    now = os.path.getmtime(p)
    sf.read(now)

    p.write_text('{"do": "solo il corpo"}', encoding="utf-8")
    os.utime(p, (now + 1, now + 1))
    assert sf.read(now + 1)["title"] == "BLOCCAGGI"


def test_il_fantasma_di_ieri_sera_vale_come_assente(tmp_path):
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI", done=True)
    # Date vere e non un epoch 0: su Windows le date agli albori del 1970 sono
    # un modo di far fallire il test per il filesystem invece che per la regola.
    now = time.time()
    os.utime(p, (now - _STALE_S - 1, now - _STALE_S - 1))
    assert StepFile(p).read(now) is None


def test_dentro_le_dodici_ore_il_passo_vale_ancora(tmp_path):
    """Un riavvio a metà serata deve ritrovare il passo in corso."""
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI")
    now = time.time()
    os.utime(p, (now - _STALE_S + 60, now - _STALE_S + 60))
    assert StepFile(p).read(now)["title"] == "BLOCCAGGI"


def test_il_file_cancellato_svuota_il_riquadro(tmp_path):
    """Cancellarlo è dirglielo, e va distinto da una lettura andata storta."""
    p = tmp_path / "s.json"
    _write(p, title="BLOCCAGGI")
    sf = StepFile(p)
    sf.read(os.path.getmtime(p))
    p.unlink()
    assert sf.read(now=2000.0) is None


def test_due_scritture_diverse_nello_stesso_istante_si_vedono_entrambe(tmp_path):
    """Su Windows due `write` ravvicinate possono condividere lo stesso mtime."""
    p = tmp_path / "s.json"
    _write(p, title="PRIMO")
    sf = StepFile(p)
    now = os.path.getmtime(p)
    assert sf.read(now)["title"] == "PRIMO"

    _write(p, title="SECONDO", do="una riga in più che cambia la dimensione")
    os.utime(p, (now, now))                     # stesso mtime, di proposito
    assert sf.read(now)["title"] == "SECONDO"


def test_il_riquadro_non_apre_la_telemetria():
    """La ragione per cui questo è un processo a sé, resa verificabile.

    Il 07/08 abbiamo sfiorato l'incidente di due `CoachEngine` accesi insieme,
    con ogni giro salvato due volte. Un `import accoach.testpanel` che non
    trascina dentro `accoach.engine` o `accoach.telemetry` è la prova che
    quell'incidente non si può ripetere da qui, qualunque cosa aggiunga in
    futuro chi ci lavora — senza questo test, un `from .engine import ...`
    aggiunto per «mostrare il giro corrente nel riquadro» non romperebbe
    niente finché non lo fa in pista.
    """
    # Il sottoprocesso non eredita il `pythonpath = ["src"]` di pytest: glielo
    # si dà a mano, o il subprocess trova (o non trova) un `accoach` a caso
    # invece del sorgente di questo worktree.
    src = str(Path(__file__).resolve().parent.parent / "src")
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys, accoach.testpanel; "
         "print([m for m in sys.modules if 'telemetry' in m or 'engine' in m])"],
        capture_output=True, text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": src})
    assert out.returncode == 0, out.stderr
    assert "[]" in out.stdout
