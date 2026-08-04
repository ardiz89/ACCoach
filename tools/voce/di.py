"""La mia voce: dice una frase, e mentre la dice tappa l'orecchio.

Meta' del canale a due vie. `assistente.py` ascolta, questo risponde.

Il lucchetto (`parla.lock`) non e' un dettaglio: gli altoparlanti e il
microfono sono nella stessa stanza, quindi senza di lui la mia risposta rientra
dal microfono, viene trascritta, e il turno dopo l'assistente sta rispondendo a
se stesso. Il file esiste per tutta la durata della frase e viene tolto **in
`finally`**, cosi' un errore di sintesi non lascia l'assistente sordo per il
resto della sessione.

E viene **ritoccato mentre parlo**, il che sembra un dettaglio e non lo e'.
`assistente.py` considera orfano un lucchetto piu' vecchio di 30 secondi e lo
rimuove — regola giusta, perche' un lucchetto rimasto da un processo ucciso
renderebbe l'assistente sordo per sempre. Ma l'eta' si leggeva dalla data di
*creazione*, quindi una risposta lunga piu' di mezzo minuto veniva scambiata per
un lucchetto abbandonato: successo davvero il 2026-08-04, con l'assistente che
ha ripreso ad ascoltare a meta' della mia frase e ha sentito se stesso. Ora il
file dice «sto parlando **adesso**» e non «ho cominciato a parlare allora».

Voce maschile senza effetto radio, la stessa dell'istruttore: durante una
sessione parlano anche il coach e l'ingegnere, e vanno distinti a orecchio.

Uso:
    python di.py "il riferimento e' il giro del ventuno luglio"
    echo "testo lungo" | python di.py
"""

from __future__ import annotations

import re
import sys
import threading
from pathlib import Path

HERE = Path(__file__).parent
LOCK = HERE / "parla.lock"
REPO = HERE.parent.parent          # tools/voce -> la radice del repo
sys.path.insert(0, str(REPO / "src"))


def _voce():
    import pyttsx3
    from accoach.coaching.voice import _pick_voice_id

    eng = pyttsx3.init()
    eng.setProperty("rate", 170)
    eng.setProperty("volume", 1.0)
    try:
        vid = _pick_voice_id(eng.getProperty("voices"), "it", male=True)
        if vid is not None:
            eng.setProperty("voice", vid)
    except Exception:                                   # noqa: BLE001
        pass
    return eng


_SIGLE = [
    (re.compile(r"\bkm/h\b", re.I), "chilometri orari"),
    (re.compile(r"\bkm\b", re.I), "chilometri"),
    (re.compile(r"(\d)\s*°C?\b"), r"\1 gradi"),
    (re.compile(r"(\d)\s*%"), r"\1 per cento"),
    (re.compile(r"(\d)\s*m\b"), r"\1 metri"),
    (re.compile(r"(\d)\s*s\b"), r"\1 secondi"),
    (re.compile(r"\bpsi\b", re.I), "p s i"),
]


def _pronuncia(testo: str) -> str:
    """Il testo come va **detto**, non come va letto.

    SAPI in italiano legge «km/h» lettera per lettera, «0.15» col punto, e
    `un_nome_con_underscore` sillaba per sillaba. A monitor lo si rilegge; al
    volante no, e una frase capita a meta' costa una seconda domanda mentre si
    guida. Quindi la conversione sta qui, applicata sempre, invece di dipendere
    dalla disciplina di chi scrive la risposta.

    Un tempo sul giro diventa parlato («1:53.712» → «uno e cinquantatre e
    sette»): al volante i decimi che contano sono i primi.
    """
    t = (testo or "").strip()
    t = re.sub(r"[`*_#]", " ", t)                       # markdown, backtick
    t = re.sub(r"\b[A-Za-z]:\\[^\s]+", "un percorso di file", t)
    t = re.sub(r"\b(\d):(\d\d)\.(\d)\d*\b", r"\1 e \2 e \3", t)   # tempi sul giro
    for pat, rep in _SIGLE:
        t = pat.sub(rep, t)
    t = re.sub(r"(\d),(\d)", r"\1 virgola \2", t)
    t = re.sub(r"(\d)\.(\d)", r"\1 virgola \2", t)      # il punto decimale
    return re.sub(r"\s+", " ", t).strip()


def di(testo: str) -> None:
    testo = _pronuncia(testo)
    if not testo:
        return
    LOCK.write_text("", encoding="utf-8")
    # `runAndWait()` blocca fino all'ultima sillaba, quindi il rinfresco va su un
    # thread: e' l'unico modo di dire "sto ancora parlando" mentre si parla.
    # Daemon, cosi' non tiene in vita il processo se la sintesi muore male.
    fermo = threading.Event()
    threading.Thread(target=_tieni_vivo, args=(fermo,), daemon=True).start()
    try:
        eng = _voce()
        eng.say(testo)
        eng.runAndWait()
    except Exception as e:                              # noqa: BLE001
        print(f"(voce non disponibile: {e})", flush=True)
    finally:
        fermo.set()
        LOCK.unlink(missing_ok=True)


#: Ogni quanto ritoccare il lucchetto. Deve stare comodamente sotto i 30 s di
#: `assistente._LOCK_MAX_S` senza rasentarli: a 25 s un rallentamento della
#: sintesi basterebbe a far scadere il lucchetto un istante prima del ritocco,
#: che e' il difetto di oggi con un margine piu' stretto.
_RINFRESCO_S = 5.0


def _tieni_vivo(fermo: threading.Event) -> None:
    while not fermo.wait(_RINFRESCO_S):
        try:
            LOCK.touch()
        except OSError:
            return          # tolto da qualcun altro: non e' piu' affar nostro


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                   # noqa: BLE001
        pass
    di(" ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read())
