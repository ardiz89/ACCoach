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

import json
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

#: Da quanto dev'essere ferma l'auto perche' una marcia sia una risposta.
#: L'istante in cui ci si ferma e quello in cui si riparte sono pieni di
#: cambiate che sono guida, non parole.
FERMO_DA_S = 1.0

#: Quanto dev'essere ferma la MARCIA prima di leggerla. Il cambio e' sequenziale:
#: per dire «quattro» si passa da uno, due e tre. Leggere il cambio invece
#: dell'arrivo vuol dire leggere il primo scalino di un viaggio — misurato in
#: pista il 23/08, dove tutte e quattro le risposte della serata sono tornate
#: «1» e una era un 4.
ASSESTA_S = 1.2

#: La domanda aperta, scritta da Claude. La sua **esistenza** e' la domanda; il
#: contenuto serve solo a rileggerla. Stesso modo del riquadro guida-test: chi
#: sta fuori scrive un file, lo strumento lo legge e non decide niente.
DOMANDA = "domanda.json"


def leggi_risposta(marcia_prima: str | None, marcia: str,
                   velocita_kmh: float, *, domanda_aperta: bool = True,
                   fermo_da_s: float = 999.0,
                   marcia_da_s: float = 999.0) -> str | None:
    """La risposta appena data, o ``None``.

    **La risposta e' dove ti fermi, non il primo scalino.** Il cambio di una GT3
    e' sequenziale: per dire «quattro» si tira la paletta quattro volte e si
    passa da uno, due e tre. Un canale che scatta al primo cambio legge la
    partenza invece dell'arrivo. Misurato in pista il 23/08: quattro domande,
    quattro risposte «1», e nessuna delle quattro era un uno — una era il voto
    4 sulla leggibilita' del riquadro, un'altra una prova di controllo in cui
    avevo chiesto la terza e l'auto era **davvero** in terza. Il canale non
    sbagliava a leggere il cambio: sbagliava a credere che il primo cambio fosse
    la risposta.

    Da cui `marcia_da_s`: si legge la marcia che e' ancora li' dopo un attimo.

    **Senza una domanda non ci sono risposte.** Un canale sempre in ascolto
    trasforma ogni gesto di guida in una parola: misurato la sera del 23/08,
    innestare la prima per uscire dal box e' arrivato come «si'», due volte, e
    io non avevo chiesto niente. Non e' rumore da filtrare a valle — era una
    risposta plausibile a una domanda che non esisteva, cioe' la forma peggiore
    di errore che questo canale possa fare.

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
    if not domanda_aperta:
        return None
    if marcia_prima is None:
        return None
    if velocita_kmh > FERMO_KMH:
        return None
    if fermo_da_s < FERMO_DA_S:
        return None
    if marcia == marcia_prima:
        return None
    if marcia_da_s < ASSESTA_S:
        return None
    if marcia not in RISPOSTE:
        return None
    return marcia


#: ACC dice «nessun tempo» con il massimo di un intero con segno. Preso alla
#: lettera diventa un migliore di 35791:23.647, che e' un numero e sembra un
#: tempo — il modo peggiore di non avere un dato.
_NIENTE_MS = 2147483647


def _tempo(ms: int) -> str:
    if ms <= 0 or ms >= _NIENTE_MS:
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

    from accoach import paths
    domanda = paths.base_dir() / DOMANDA

    marcia_prima: str | None = None
    giri_prima = -1
    stato_prima = None
    fermo_da: float | None = None
    chiesto_prima = False
    marcia_vista = ""
    marcia_da = 0.0
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
            chiesto = domanda.exists()
            if chiesto and not chiesto_prima:
                try:
                    testo = json.loads(domanda.read_text(encoding="utf-8"))
                    print(f"DOMANDA {testo.get('testo', '')}", flush=True)
                except (OSError, ValueError):
                    print("DOMANDA (illeggibile)", flush=True)
            chiesto_prima = chiesto

            if vivo:
                ora = time.monotonic()
                if s.speed_kmh > FERMO_KMH:
                    fermo_da = None
                elif fermo_da is None:
                    fermo_da = ora
                if s.gear != marcia_vista:
                    marcia_vista, marcia_da = s.gear, ora
                risposta = leggi_risposta(
                    marcia_prima, s.gear, s.speed_kmh, domanda_aperta=chiesto,
                    fermo_da_s=(0.0 if fermo_da is None else ora - fermo_da),
                    marcia_da_s=ora - marcia_da)
                if risposta is not None:
                    etichetta = {"1": "si'", "2": "no", "R": "ripeti"}.get(
                        risposta, f"voto {risposta}")
                    print(f"RISPOSTA {risposta} ({etichetta})", flush=True)
                    # Una domanda, una risposta: chiudere qui il turno rende
                    # strutturalmente impossibile che una cambiata successiva
                    # risponda una seconda volta alla stessa domanda. E' l'unica
                    # cosa che questo strumento scrive, e scrive cancellando.
                    domanda.unlink(missing_ok=True)
                    chiesto_prima = False
                if s.speed_kmh > FERMO_KMH:
                    marcia_prima = None     # guidando non si tiene il conto
                elif marcia_prima is None or not chiesto:
                    # Fuori da una domanda si semina e basta. Durante una
                    # domanda NON si insegue ogni scalino: aggiornare qui
                    # farebbe sembrare l'arrivo «uguale a prima» e la risposta
                    # non uscirebbe mai.
                    marcia_prima = s.gear

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
