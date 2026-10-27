"""Importare un giro di riferimento PRO: una regola sola per l'hub e per la riga
di comando.

Il bottone e `import-reference` avevano ciascuno la sua copia, e nessuna delle
due diceva cosa succedeva dopo. Lo stesso file importato due volte diventava due
giri, e un giro PRO più lento del tuo veniva salvato senza una parola, mentre
il coach continuava a usare il tuo (27/10). Qui si importa e si risponde con
l'esito: diventa il riferimento, resta il tuo, oppure c'era già.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..telemetry.snapshot import format_lap_time
from .lap import Lap, prefer_pro
from .storage import (_catalog_path, _slug, laps_root, list_lap_files, load_lap,
                      save_lap)

REFERENCE = "reference"       # più veloce del tuo migliore: il coach usa questo
FIRST = "first"               # nessun giro tuo qui: il coach usa questo
SLOWER = "slower"             # il tuo migliore è più veloce e resta il riferimento
DUPLICATE = "duplicate"       # lo stesso giro PRO c'era già: niente di scritto


@dataclass
class Imported:
    status: str
    lap: Lap
    own_ms: int | None = None
    dest: Path | None = None


def import_pro(src: Path | str, laps_dir: Path | str | None = None) -> Imported:
    """Importa ``src`` come giro PRO. Solleva ``OSError``/``ValueError`` se il
    file non si legge o non è un giro completo."""
    lap = load_lap(Path(src))
    if lap.lap_time_ms <= 0 or not lap.samples:
        raise ValueError("no lap time or no samples")
    laps_dir = Path(laps_dir) if laps_dir else laps_root()

    own_ms: int | None = None
    try:
        from .catalog import LapCatalog

        with LapCatalog(_catalog_path(laps_dir)) as cat:
            cat.sync(list_lap_files(laps_dir))
            # Stessa auto, stessa pista, stesso tempo al millesimo: è lo stesso
            # giro. Il nome del file cambia a ogni import (porta l'ora), quindi
            # non basta guardare quello.
            dup = cat._conn.execute(
                """SELECT 1 FROM lap WHERE car_key = ? AND track_key = ?
                   AND source = 'pro' AND lap_time_ms = ? LIMIT 1""",
                (_slug(lap.car_model), _slug(lap.track), lap.lap_time_ms),
            ).fetchone()
            if dup:
                return Imported(DUPLICATE, lap)
            own = cat._own_reference(lap.car_model, lap.track, None, None, None)
            own_ms = own["lap_time_ms"] if own else None
    except Exception:            # noqa: BLE001 - il catalogo è una cache
        own_ms = None

    lap.valid = True             # un riferimento è un giro completo
    lap.clean = True             # importato come riferimento pulito
    lap.source = "pro"           # un livello a sé, non uno dei tuoi giri
    lap.recorded_utc = ""        # lo timbra save_lap
    dest = save_lap(lap, laps_dir)
    if own_ms is None:
        status = FIRST
    elif prefer_pro(own_ms, lap.lap_time_ms):
        status = REFERENCE
    else:
        status = SLOWER
    return Imported(status, lap, own_ms, dest)


def describe(result: Imported, t) -> str:
    """La frase per il pilota, nella lingua di ``t``."""
    lap = result.lap
    done = t("import.done").format(car=lap.car_model, track=lap.track,
                                   time=format_lap_time(lap.lap_time_ms))
    if result.status == DUPLICATE:
        return t("import.duplicate")
    own = format_lap_time(result.own_ms) if result.own_ms else ""
    return f"{done} {t('import.' + result.status).format(own=own)}"
