"""Il registro della sessione: una riga JSON per giro e per evento dei box.

Dopo una prova in pista chi sviluppa deve poter ricostruire cosa ha fatto
l'Ingegnere senza chiederlo al pilota. Il motore scrive qui, in un file al
giorno (``ingegnere-AAAAMMGG.jsonl``) nella cartella dei log dell'app.

Il registro e' un di piu': scrivere non solleva mai verso chi chiama, cosi' una
cartella piena o non scrivibile non rompe un giro.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from ..logging_setup import get_logger

_log = get_logger(__name__)


class SessionLog:
    def __init__(self, folder: Path | str,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self.folder = Path(folder)
        self._clock = clock

    def path_for(self, day: date) -> Path:
        return self.folder / f"ingegnere-{day:%Y%m%d}.jsonl"

    def write(self, kind: str, /, **fields) -> None:
        """Aggiunge una riga ``{"t": ..., "kind": kind, ...}``; mai un'eccezione."""
        try:
            now = self._clock()
            row = {"t": now.isoformat(timespec="milliseconds"), "kind": kind}
            row.update({k: v for k, v in fields.items() if k != "kind"})
            line = json.dumps(row, ensure_ascii=False, default=str)
            self.folder.mkdir(parents=True, exist_ok=True)
            with open(self.path_for(now.date()), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:  # noqa: BLE001 - il registro non rompe mai un giro
            _log.debug("session log write failed", exc_info=True)
