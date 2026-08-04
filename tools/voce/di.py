"""La mia voce: dice una frase, e mentre la dice tappa l'orecchio.

Meta' del canale a due vie. `assistente.py` ascolta, questo risponde.

**Voce neurale (Piper), non SAPI5.** La sintesi e' la stessa con cui sono
renderizzati i cue del coach — voce italiana `it_IT-paola-medium` — e costa
**561 ms misurati** per una frase intera, abbassamento di tono compreso, in
locale e senza rete. SAPI5 resta come
ripiego dove Piper non c'e', cosi' su una macchina appena clonata lo strumento
parla lo stesso, solo peggio.

Ma **abbassata**, e non per gusto: Paola e' la voce con cui sono renderizzati
i cue del coach, quindi usarla tale e quale vorrebbe dire che in pista io e lui
siamo la stessa persona. Piper ha due voci italiane e l'altra (`riccardo-x_low`)
e' x_low, si sente, e costa 1.8 s contro 0.5. Quindi si ricampiona: stessa
qualita', stesso mezzo secondo, un'altra persona.

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

Niente effetto radio, e non e' una dimenticanza: il filtro pit-to-car e' la
persona del *coach*, e questo non e' il coach — e' una conversazione con chi
sta scrivendo il programma.

Uso:
    python di.py "il riferimento e' il giro del ventuno luglio"
    echo "testo lungo" | python di.py
"""

from __future__ import annotations

import array
import re
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

HERE = Path(__file__).parent
LOCK = HERE / "parla.lock"
REPO = HERE.parent.parent          # tools/voce -> la radice del repo
sys.path.insert(0, str(REPO / "src"))

#: Piper, la stessa sintesi neurale con cui sono renderizzati i cue del coach.
#: Vive in `tools/piper/` ed e' roba da build, non spedita — e va benissimo,
#: perche' anche questo e' uno strumento di `tools/` e non entra nel pacchetto.
PIPER = REPO / "tools" / "piper" / "piper.exe"
MODELLO = REPO / "tools" / "piper" / "voices" / "it_IT-paola-medium.onnx"


def _piper(testo: str) -> Path | None:
    """La frase come WAV, o None se Piper non c'e' o non ce la fa.

    Misurato su questa macchina: **524 ms** di sintesi, **561 ms** col tono
    abbassato. SAPI5 e' istantaneo e sembra un navigatore del 2005; questo
    costa mezzo secondo e sembra una persona. Su un canale dove si fa una
    domanda e si aspetta la risposta, mezzo secondo non lo nota nessuno.

    **Chatterbox no, e il numero e' quello che decide.** E' la voce di marca
    scelta il 02/07 e resta giusta per i cue del coach, che si renderizzano in
    *build*: li' venti secondi a frase si pagano una volta sola. Qui si
    sintetizza mentre l'altro aspetta, e misurato il 04/08 su questa macchina
    fa 7 s di caricamento modello piu' 13.6 s per tre secondi di parlato —
    3-5 volte il tempo reale. Una risposta breve arriverebbe dopo venti
    secondi di silenzio.
    """
    if not (PIPER.exists() and MODELLO.exists()):
        return None
    out = Path(tempfile.gettempdir()) / "hone_di.wav"
    try:
        subprocess.run(
            [str(PIPER), "-m", str(MODELLO), "-f", str(out)],
            input=testo.encode("utf-8"),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if not (out.exists() and out.stat().st_size > 44):
        return None
    _abbassa(out)
    return out


#: Di quanto abbassare il tono rispetto a Paola. Non e' un gusto: le voci
#: italiane di Piper sono due, e Paola e' **quella con cui sono renderizzati i
#: cue del coach** — usarla tale e quale vuol dire che in pista io e lui siamo
#: la stessa persona. L'altra (`riccardo-x_low`) e' x_low, si sente, e costa
#: 1.8 s contro 0.5.
#:
#: Scelto ascoltando: a -10% si distingue troppo poco per un abitacolo col
#: motore acceso, a -15% e' un'altra persona e la voce regge ancora.
TONO = 0.85


def _abbassa(wav: Path, fattore: float = TONO) -> None:
    """Abbassa il tono ricampionando, sul posto.

    Ricampionamento lineare più sample rate riscritto: sposta tono **e** durata
    insieme, che è il trucco più vecchio del mondo e qui basta — non serve
    preservare le formanti, serve che non sembri la stessa persona. Su una
    frase da 3 secondi costa qualche millisecondo, quindi non tocca i 500 ms.

    Solo `wave` e `array`: uno strumento di `tools/` non deve tirarsi dietro
    numpy per abbassare una voce di tre semitoni.
    """
    try:
        with wave.open(str(wav)) as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                return                      # non è il PCM che scrive Piper
            sr, n = w.getframerate(), w.getnframes()
            a = array.array("h")
            a.frombytes(w.readframes(n))
        m = int(len(a) / fattore)
        out = array.array("h", bytes(2 * m))
        for i in range(m):
            p = i * fattore
            k = int(p)
            s0 = a[k] if k < len(a) else 0
            s1 = a[k + 1] if k + 1 < len(a) else s0
            out[i] = int(s0 + (s1 - s0) * (p - k))
        with wave.open(str(wav), "wb") as o:
            o.setnchannels(1)
            o.setsampwidth(2)
            o.setframerate(int(sr / fattore))
            o.writeframes(out.tobytes())
    except (OSError, wave.Error, ValueError):
        return                              # meglio la voce alta che nessuna


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
        wav = _piper(testo)
        if wav is not None:
            # winsound e' nella libreria standard, quindi la voce neurale non
            # aggiunge una dipendenza: la stessa scelta gia' fatta da
            # `coaching/voice.py` per i cue pre-renderizzati.
            import winsound
            winsound.PlaySound(str(wav), winsound.SND_FILENAME)
        else:
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
