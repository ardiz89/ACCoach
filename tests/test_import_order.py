"""Il coach e il registratore si caricano in qualunque ordine.

Il 16/11 il registratore ha preso la soglia dello stacco da `coaching.analyzer`,
che importa il registratore: i test passavano perche' caricavano prima
`recording`, e uno strumento che caricava prima `coaching` non partiva. Un
interprete nuovo per ogni ordine, perche' dentro la suite i moduli sono gia'
in memoria e il giro non si vede.
"""
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.mark.parametrize("first", [
    "accoach.coaching.analyzer",
    "accoach.recording.recorder",
    "accoach.braking_points",
    "accoach.coaching.debrief",
])
def test_a_module_loads_first_in_a_fresh_interpreter(first):
    done = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(SRC)!r}); "
                               f"import {first}"],
        capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
