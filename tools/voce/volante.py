"""Ascoltare il pilota dal volante, quando il pilota non puo' parlare.

L'altra meta' del canale a due vie, per le sere in cui il microfono non e'
un'opzione: i piccoli dormono, oppure il pilota ha il casco, oppure il motore
copre tutto. `assistente.py` ascolta la voce; questo ascolta **i comandi
dell'auto**.

Il pilota risponde con **le marce, ad auto ferma**:

    1a   si'                    R      ripeti, non ho capito
    2a   no                     folle  riposo, nessuna risposta in corso
    1a-5a un voto da 1 a 5

Perche' le marce e non il volante o il gas. Il volante torna al centro da solo,
quindi una risposta si cancellerebbe da sola mentre la leggo. Il gas ha mille
valori e li fai per guidare, quindi «risposta» e «guida» non si distinguono. La
marcia invece e' **un numero**, resta dov'e' finche' non lo cambi, si fa coi
paddle — nessun rumore in casa, niente occhi via dalla strada — e viene letta
**solo ad auto ferma**, dove nessuna delle due cose e' guida.

Legge la memoria condivisa **in sola lettura** e non scrive niente: nessun giro
salvato, nessun `CoachEngine`. Non e' un secondo coach, quindi non ricade nel
difetto per cui `live` e `server` non convivono (ogni giro salvato due volte, e
la copia indistinguibile da un giro vero).

    python tools/voce/volante.py

Stampa una riga **solo quando succede qualcosa**: una risposta, un giro chiuso,
un cambio di stato. Un flusso continuo a 60 Hz sarebbe illeggibile e, peggio,
seppellirebbe la riga che conta.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

#: Sotto questa velocita' l'auto e' ferma e una marcia e' una risposta. Non zero:
#: in corsia box con l'auto in sosta la velocita' oscilla di qualche decimo, e a
#: zero secco la risposta si perderebbe. Sopra, e' guida.
FERMO_KMH = 3.0

#: Le marce che dicono qualcosa. Oltre la 5a si scala guidando, e leggerle come
#: risposte vorrebbe dire sentire cose mai dette.
RISPOSTE = ("1", "2", "3", "4", "5", "R")


def leggi_risposta(marcia_prima: str | None, marcia: str,
                   velocita_kmh: float) -> str | None:
    """La risposta appena data, o ``None``.

    Vale il **cambio**, non lo stato: una marcia gia' inserita e' una risposta
    gia' letta, e rileggerla a ogni frame darebbe la stessa risposta sessanta
    volte al secondo. Per ripetere lo stesso numero si passa dal folle — che e'
    anche il motivo per cui il folle e' «riposo» e non una risposta.

    ``marcia_prima`` a ``None`` vuol dire *non lo so*, e allora non c'e' nessun
    cambio da leggere: si semina e basta. Non e' un dettaglio difensivo, e'
    l'unico modo di non inventare risposte. Misurato la sera del 23/08, con il
    pilota gia' in macchina: uscendo dal menu il gioco passa da PAUSE a LIVE e
    la marcia riparte da R, quindi ogni rientro in pista mi arrivava come un
    «ripeti» — tre in un minuto, e nessuno detto da lui.
    """
    if marcia_prima is None:
        return None
    if velocita_kmh > FERMO_KMH:
        return None
    if marcia == marcia_prima:
        return None
    if marcia not in RISPOSTE:
        return None
    return marcia


def _tempo(ms: int) -> str:
    if ms <= 0:
        return "--"
    return f"{ms // 60000}:{(ms % 60000) / 1000.0:06.3f}"


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                   # noqa: BLE001
        pass
    from accoach.telemetry.reader import SharedMemoryReader
    from accoach.telemetry.snapshot import ACStatus

    reader = SharedMemoryReader()
    print("VOLANTE pronto — 1=si' 2=no 1-5=voto R=ripeti folle=riposo",
          flush=True)

    marcia_prima: str | None = None
    giri_prima = -1
    stato_prima = None
    try:
        while True:
            s = reader.read()
            stato = (s.connected, s.status.name, s.in_pit_lane)
            if stato != stato_prima:
                print(f"STATO connesso={s.connected} {s.status.name}"
                      f" corsia_box={s.in_pit_lane} {s.car_model}@{s.track}",
                      flush=True)
                stato_prima = stato

            vivo = s.connected and s.status is ACStatus.LIVE
            if not vivo:
                # In pausa e nei menu i canali non descrivono un'auto guidata:
                # la marcia torna a R da sola. Dimenticare quel che c'era e'
                # cio' che impedisce al rientro in pista di sembrare una
                # risposta.
                marcia_prima = None
            if vivo:
                risposta = leggi_risposta(marcia_prima, s.gear, s.speed_kmh)
                if risposta is not None:
                    etichetta = {"1": "si'", "2": "no", "R": "ripeti"}.get(
                        risposta, f"voto {risposta}")
                    print(f"RISPOSTA {risposta} ({etichetta})", flush=True)
                if s.speed_kmh <= FERMO_KMH:
                    marcia_prima = s.gear
                else:
                    marcia_prima = None     # guidando non si tiene il conto

                if s.completed_laps != giri_prima:
                    if giri_prima >= 0:
                        print(f"GIRO {s.completed_laps}"
                              f" ultimo={_tempo(s.last_lap_ms)}"
                              f" migliore={_tempo(s.best_lap_ms)}", flush=True)
                    giri_prima = s.completed_laps
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()


if __name__ == "__main__":
    main()
