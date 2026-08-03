"""L'assistente vocale da sviluppo: parola di attivazione, poi la domanda.

Serve a una cosa sola: **sviluppare HONE mentre si guida**. Il pilota dice la
parola di attivazione, fa la domanda, e la conversazione arriva a me senza che
nessuno tocchi il telefono. Nasce dalla stessa regola dell'incidente del
2026-08-02 (vedi `istruttore.py`): a voce quello che serve in movimento.

## Come mi arriva la voce

Questo processo **non esce** a ogni frase, al contrario di `ascolta.py`. Resta
in ascolto e stampa **una riga per domanda** su stdout; e' il tool `Monitor` a
girarmi ogni riga come notifica. La differenza non e' cosmetica: un processo
che esce e va rilanciato e' sordo nel frattempo, e il buco cade proprio mentre
il pilota parla. Qui il microfono non si chiude mai.

Contratto delle righe (nient'altro va su stdout):

    PRONTO <microfono>          armato, la parola di attivazione e' viva
    DOMANDA <testo>             il pilota ha parlato — questa e' la sua frase
    VUOTO                       svegliato ma non ha detto niente
    ERRORE <cosa>               guasto: la riga esiste perche' il silenzio di
                                un monitor non deve poter significare "va tutto
                                bene" (vedi la nota sulla copertura in Monitor)

## Perche' il riconoscimento gira sempre, e non solo dopo la parola

vosk sa fare da rilevatore di parola chiave con una **grammatica**, che sarebbe
piu' economico. Ma la grammatica accetta solo parole **presenti nel vocabolario
del modello**, e questo e' il modello italiano: «dev» non e' una parola
italiana. Una parola di attivazione fuori vocabolario dentro una grammatica non
da' errore: semplicemente **non scatta mai**, e il guasto e' silenzioso. Quindi
si trascrive tutto e si cerca la parola nel testo, accettando le forme che il
modello produce davvero — **misurate**, vedi `_VARIANTI` e
`taratura_sveglia.py`. Costa qualche punto di CPU e non ha modi silenziosi di
rompersi.

Limite noto, misurato nella stessa prova: i **nomi propri di curva** si
storpiano («roggia» → «loggia»). Le domande passano, i nomi vanno letti con
indulgenza.

Prezzo dichiarato, e va detto per intero. Il microfono e' aperto per tutta la
sessione. L'**audio** non lascia questa macchina — vosk gira in locale, niente
viene registrato su file — e su stdout finisce solo cio' che segue la parola di
attivazione. Ma il **testo** e' un'altra cosa: con `--tutto` il diario raccoglie
ogni trascrizione, comprese le telefonate e chi passa di la', e quel file esiste
apposta perche' lo legga io per tarare le varianti. In quel momento due ore di
parlato altrui entrano nel mio contesto, e nessuno di quegli altri ha acconsentito.
Per questo `--tutto` **non e' il default**: di norma il diario tiene solo le
domande, e la registrazione completa e' un'operazione dichiarata, che si accende
per una taratura e si spegne dopo.

## Il ritorno di voce

Quando io rispondo, a parlare e' `di.py`, che crea `parla.lock` mentre parla.
Finche' quel file esiste questo processo **butta via l'audio**: senza, la mia
risposta rientra dal microfono e il turno dopo ascolta se stesso.

Uso:
    python assistente.py                       # parola: «hey dev»
    python assistente.py --parola "ehi coach"  # un'altra
    python assistente.py --silenzio 2.5        # fine domanda dopo 2.5 s di quiete
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
MODEL = HERE / "vosk-model-small-it-0.22"
LOCK = HERE / "parla.lock"
DIARIO = HERE / "assistente-udito.jsonl"

RATE = 16000
BLOCK = 4000                   # ~0.25 s per blocco a 16 kHz

# Le storpiature che il modello italiano piccolo puo' restituire per «hey dev».
# Questa lista e' una **previsione**, non una misura: al primo uso in pista si
# guarda `assistente-udito.jsonl` e si aggiunge quello che ha davvero scritto.
# Meglio accettare troppo che troppo poco — un falso risveglio costa un «vuoto»,
# un mancato risveglio costa una domanda persa mentre si guida.
# --- la parola di attivazione, MISURATA ------------------------------------
#
# La prima versione di questa lista era indovinata. `taratura_sveglia.py` (2026-
# 08-03) l'ha sottoposta al modello con dizione perfetta e zero rumore, e
# **nessuna delle 18 varianti ha funzionato**. Cosa esce davvero:
#
#     detto «hey dev»          -> scritto «egli deve»
#     detto «ehi dev»          -> scritto «è il deve»
#     detto «ehi ingegnere»    -> scritto «e ingegneri»
#     detto «ehi hone»         -> scritto «ehi non»
#     detto «ehi copilota»     -> scritto «ehi copilota»       <-- esatto
#     detto «ehi tecnico»      -> scritto «ehi tecnico»        <-- esatto
#
# La regola che ne esce, ed e' la cosa da ricordare: **la parola di attivazione
# dev'essere fatta di parole italiane vere**. Quelle nel vocabolario del modello
# tornano indietro identiche, anche con una domanda intera attaccata dietro
# («ehi copilota perché il coach tace alla roggia» → tutto giusto). Quelle fuori
# vocabolario — «dev», «hone» — vengono rifuse ogni volta in qualcosa di
# diverso, e non c'e' lista di varianti che regga.
#
# Per questo il default non e' piu' «hey dev»: resta accettato, nelle **forme
# misurate**, ma la parola buona e' «ehi copilota».
_SVEGLIA_DEFAULT = "ehi copilota"
_VARIANTI = {
    # Misurate esatte. Le declinazioni accanto sono estrapolate dalla deriva
    # osservata altrove (singolare→plurale: «ingegnere»→«ingegneri»,
    # «sviluppatore»→«sviluppatori»), non misurate.
    "ehi copilota": ["ehi copilota", "e copilota", "hey copilota",
                     "il copilota", "ehi copiloti"],
    "ehi tecnico": ["ehi tecnico", "e tecnico", "hey tecnico", "il tecnico"],
    # Misurate: e' cosi' che il modello scrive «hey dev».
    "hey dev": ["egli deve", "e il deve", "ehi deve", "hey deve", "egli dev"],
}

# La riserva, sempre attiva accanto alla parola scelta, perche' se la prima non
# scattasse il pilota si ritroverebbe a ripeterla **mentre guida** — cioe'
# esattamente la distrazione che tutto questo doveva togliere.
_RISERVA = "ehi tecnico"

# Frasi che annullano un risveglio: un falso scatto (o un ripensamento) si
# chiude dicendolo, invece di lasciarmi rispondere a una domanda mai fatta.
_ANNULLA = ("niente", "nulla", "lascia stare", "lascia perdere", "scusa",
            "annulla", "non importa", "fa niente", "fa nulla", "no niente")

# Parola di chiusura: chiude la domanda subito invece di aspettare il silenzio.
# Vale 2.5 secondi di latenza su ogni domanda, ed e' parola italiana vera —
# quindi nel vocabolario del modello, quindi affidabile, al contrario di «dev».
_CHIUDI = ("chiudo", "passo e chiudo", "stop")

# Ogni quanto il processo dichiara di essere vivo. Il silenzio di un monitor non
# deve poter significare due cose diverse.
_BATTITO_S = 300.0

# Dopo quanto un lucchetto della voce e' da considerarsi orfano. Una risposta
# parlata non dura mai cosi' tanto; un processo ucciso a meta' frase si'.
_LOCK_MAX_S = 30.0


def varianti_attive(parola: str) -> list[str]:
    """Le forme accettate per ``parola``, piu' quelle della riserva."""
    scelte = _VARIANTI.get(_piatto(parola), [_piatto(parola)])
    return list(dict.fromkeys([*scelte, *_VARIANTI[_RISERVA]]))


def _piatto(s: str) -> str:
    """Minuscolo, senza accenti, spazi singoli — per confrontare due testi."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.replace("'", " ").split())


def _dopo_la_sveglia(testo: str, varianti: list[str]) -> str | None:
    """La parte di frase che segue la parola di attivazione, o None se non c'e'.

    Restituisce "" quando la frase finisce con la parola: significa svegliato,
    domanda non ancora detta. Distinguere questo da None e' tutto il punto —
    None vuol dire «non era per me», "" vuol dire «sto aspettando».

    Confronto a **parole intere e solo in testa alla frase**, non per
    sottostringa. Con `find()` la variante «e tecnico» stava dentro «**che
    tecnico**» e «an**che tecnico**», e valeva in qualunque punto del discorso:
    «poi ho detto al copilota che...» svegliava a meta' frase e mi mandava la
    coda come se fosse una domanda. Al volante un falso risveglio non costa un
    beep, costa una risposta parlata in curva.
    """
    tok = _piatto(testo).split()
    # La variante piu' lunga per prima: «hey dev» prima di «e dev», altrimenti
    # la corta vince e si porta via una parola della domanda.
    for v in sorted(varianti, key=len, reverse=True):
        vt = v.split()
        # Le prime tre parole: giusto lo spazio per un'esitazione davanti
        # («allora... ehi copilota»), non abbastanza per pescare a caso.
        for i in range(min(3, max(0, len(tok) - len(vt) + 1))):
            if tok[i:i + len(vt)] == vt:
                return " ".join(tok[i + len(vt):])
    return None


def _device(match: str = "brio"):
    import sounddevice as sd
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and match.lower() in d["name"].lower():
            return i, d["name"]
    return None, "(predefinito di sistema)"


def _beep(sveglia: bool) -> None:
    """Due toni brevi: acuto = ti ascolto, grave = ho preso.

    Un tono e non una voce di proposito: e' istantaneo (una frase sintetizzata
    arriva mezzo secondo dopo, e il pilota nel frattempo ha gia' iniziato a
    parlare) e **non e' fatto di parole**, quindi non puo' rientrare dal
    microfono e finire dentro la domanda.
    """
    try:
        import winsound
        winsound.Beep(880 if sveglia else 440, 90)
    except Exception:                                   # noqa: BLE001
        pass


# Cosa finisce nel diario. Di default solo quello che il pilota ha detto **a
# me**; `--tutto` aggiunge ogni trascrizione, che serve per tarare le varianti e
# nient'altro. Vedi la nota sulla privacy in cima al file.
_DIARIO_SEMPRE = frozenset({"domanda", "annullato", "vuoto"})
_diario_tutto = False


def _annota(genere: str, testo: str) -> None:
    """Cosa il modello ha sentito, per tarare le varianti dopo."""
    if not (_diario_tutto or genere in _DIARIO_SEMPRE):
        return
    try:
        with DIARIO.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"quando": datetime.now().isoformat(timespec="seconds"),
                                 "genere": genere, "testo": testo},
                                ensure_ascii=False) + "\n")
    except Exception:                                   # noqa: BLE001
        pass


def ascolta(parola: str, silenzio_s: float, massimo_s: float, mic: str) -> None:
    import sounddevice as sd
    from vosk import KaldiRecognizer, Model, SetLogLevel

    SetLogLevel(-1)
    varianti = varianti_attive(parola)
    model = Model(str(MODEL))
    rec = KaldiRecognizer(model, RATE)
    rec.SetWords(False)

    dev, nome = _device(mic)
    q: "queue.Queue[bytes]" = queue.Queue()

    def cb(indata, frames, t, status):                  # noqa: ARG001
        q.put(bytes(indata))

    sveglio = False
    raccolto: list[str] = []          # pezzi gia' definitivi della domanda
    parziale = ""                     # l'ultimo parziale, per capire se tace
    t_sveglia = 0.0
    t_ultimo_suono = 0.0
    blocchi = 0                       # blocchi audio dall'ultimo battito
    domande = 0                       # domande mandate in tutta la sessione
    t_battito = time.monotonic()

    def chiudi() -> None:
        """Fine domanda: dilla su stdout e torna a dormire."""
        nonlocal sveglio, raccolto, parziale, domande
        testo = " ".join(x for x in (*raccolto, parziale) if x).strip()
        for fine in sorted(_CHIUDI, key=len, reverse=True):
            if testo.endswith(fine):
                testo = testo[: -len(fine)].strip()
                break
        # Chiudere il segmento di vosk, non solo il nostro stato. Senza, il
        # definitivo che arriva dopo contiene **tutta** la frase, parola di
        # attivazione compresa: `_dopo_la_sveglia` la ritrova, ci si risveglia
        # da soli, e due secondi dopo esce una seconda DOMANDA identica — cioe'
        # io che rispondo due volte mentre lui e' in curva. Succede ogni volta
        # che il timer di silenzio batte sul tempo l'endpointer di vosk, cosa
        # che col rumore di motore in stanza e' la norma.
        rec.Reset()
        _beep(False)
        if any(testo.startswith(a) for a in _ANNULLA):
            # Falso risveglio, o ripensamento. Va distinto da una domanda vera:
            # rispondere a «niente» e' peggio che tacere, perche' occupa
            # l'altoparlante mentre il pilota e' in curva.
            _annota("annullato", testo)
            print("ANNULLATO", flush=True)
        elif testo:
            _annota("domanda", testo)
            domande += 1
            print(f"DOMANDA {testo}", flush=True)
        else:
            _annota("vuoto", "")
            print("VUOTO", flush=True)
        sveglio, raccolto, parziale = False, [], ""

    with sd.RawInputStream(samplerate=RATE, blocksize=BLOCK, device=dev,
                           dtype="int16", channels=1, callback=cb):
        print(f"PRONTO {nome} — parola: «{parola}»", flush=True)
        while True:
            try:
                data = q.get(timeout=0.25)
            except queue.Empty:
                data = None

            if data is not None:
                blocchi += 1

            # Mentre parlo io, l'orecchio e' chiuso e la coda si svuota: cosi'
            # alla fine della mia risposta il riconoscitore non ha in pancia
            # mezza frase mia da attribuire al pilota.
            if LOCK.exists():
                # Un lucchetto orfano (processo della voce ucciso, sessione
                # chiusa, SAPI crashato) rende sordi **per sempre e in
                # silenzio**: niente beep, niente riga, nessun modo di
                # accorgersene se non riavviando. Ha una scadenza, e la sua
                # rimozione si dichiara.
                try:
                    vecchio = time.time() - LOCK.stat().st_mtime > _LOCK_MAX_S
                except OSError:
                    vecchio = False
                if vecchio:
                    LOCK.unlink(missing_ok=True)
                    print("ERRORE lucchetto orfano rimosso, riprendo ad ascoltare",
                          flush=True)
                else:
                    while not q.empty():
                        q.get_nowait()
                    rec.Reset()
                    parziale = ""
                    continue

            # Il polso. Il silenzio di un monitor non deve poter significare due
            # cose: «nessuna domanda» e «il microfono e' morto» si assomigliano
            # troppo. Se il BRIO va in sospensione USB o un'altra app prende
            # l'ingresso, il ciclo gira a vuoto e nessuno se ne accorge per due
            # ore.
            ora = time.monotonic()
            if ora - t_battito >= _BATTITO_S:
                if blocchi == 0:
                    print(f"ERRORE microfono muto da {_BATTITO_S:.0f} s", flush=True)
                else:
                    print(f"VIVO {blocchi} blocchi, {domande} domande", flush=True)
                blocchi, t_battito = 0, ora

            if data is not None:
                if rec.AcceptWaveform(data):
                    testo = json.loads(rec.Result()).get("text", "").strip()
                    if testo:
                        _annota("definitivo", testo)
                        t_ultimo_suono = time.monotonic()
                        if sveglio:
                            # Il definitivo vince sul parziale (e' la stessa
                            # frase, decodificata meglio), ma se il risveglio era
                            # scattato sul parziale il definitivo si porta dietro
                            # anche la parola di attivazione: va tolta di nuovo,
                            # o finisce dentro la domanda.
                            coda = _dopo_la_sveglia(testo, varianti)
                            pezzo = coda if coda is not None else _piatto(testo)
                            if pezzo:
                                raccolto.append(pezzo)
                            parziale = ""
                        else:
                            coda = _dopo_la_sveglia(testo, varianti)
                            if coda is not None:
                                sveglio = True
                                t_sveglia = t_ultimo_suono
                                raccolto = [coda] if coda else []
                                parziale = ""
                                _beep(True)
                else:
                    p = json.loads(rec.PartialResult()).get("partial", "").strip()
                    if p and p != parziale:
                        parziale = p
                        t_ultimo_suono = time.monotonic()
                        # Svegliarsi sul **parziale** e non solo sul definitivo:
                        # vosk chiude un risultato solo dopo una pausa vera, e
                        # aspettarla vuol dire far suonare il beep a domanda gia'
                        # finita. Cosi' il pilota sente «ti ascolto» mentre ancora
                        # sta dicendo la parola.
                        if not sveglio:
                            coda = _dopo_la_sveglia(p, varianti)
                            if coda is not None:
                                sveglio = True
                                t_sveglia = t_ultimo_suono
                                raccolto, parziale = [], coda
                                _beep(True)

            if sveglio:
                ora = time.monotonic()
                # La parola di chiusura prima del silenzio: chi la dice non
                # aspetta il timer, e il timer puo' quindi permettersi di essere
                # largo. Al volante si pensa a meta' frase — si comincia in
                # rettilineo, si tace nella staccata, si finisce dopo — e un
                # timer stretto manda mezza domanda e obbliga a un secondo giro
                # di parola mentre si guida.
                detto = " ".join(x for x in (*raccolto, parziale) if x).strip()
                if any(detto.endswith(f) for f in _CHIUDI):
                    chiudi()
                elif ora - t_ultimo_suono >= silenzio_s and (raccolto or parziale):
                    chiudi()
                elif ora - t_sveglia >= massimo_s:
                    # Tetto duro: sveglio da troppo senza chiudere. Chiude lo
                    # stesso — un assistente che resta appeso in ascolto e' peggio
                    # di uno che tronca, perche' il pilota non sa in che stato e'.
                    chiudi()
                elif not (raccolto or parziale) and ora - t_sveglia >= silenzio_s * 2:
                    chiudi()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                   # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--parola", default=_SVEGLIA_DEFAULT)
    ap.add_argument("--silenzio", type=float, default=6.0,
                    help="secondi di quiete che chiudono la domanda. Largo di "
                         "proposito: e' la rete di sicurezza, non il criterio — "
                         "per chiudere subito si dice «chiudo»")
    ap.add_argument("--massimo", type=float, default=30.0,
                    help="tetto di durata di una singola domanda")
    ap.add_argument("--mic", default="brio")
    ap.add_argument("--tutto", action="store_true",
                    help="registra nel diario OGNI trascrizione, non solo le "
                         "domande. Serve a tarare le varianti della parola di "
                         "attivazione; da spegnere subito dopo (vedi la nota "
                         "sulla privacy in cima al file)")
    a = ap.parse_args()
    global _diario_tutto
    _diario_tutto = a.tutto
    if a.tutto:
        print("VIVO diario completo acceso — registra anche chi non ha chiesto",
              flush=True)
    try:
        LOCK.unlink(missing_ok=True)      # lucchetto rimasto da una sessione morta
        ascolta(a.parola, a.silenzio, a.massimo, a.mic)
    except KeyboardInterrupt:
        print("ERRORE interrotto a mano", flush=True)
    except Exception as e:                              # noqa: BLE001
        print(f"ERRORE {type(e).__name__}: {e}", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
