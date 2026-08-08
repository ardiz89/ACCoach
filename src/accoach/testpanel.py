"""Il riquadro che guida il protocollo di test in pista.

Nasce da una frase del pilota il 07/08: «non mi ricordo a memoria tutti questi
passaggi». Il protocollo glielo detta Claude a voce — la regola nata
dall'incidente del 02/08 vieta di chiedergli di leggere una chat mentre guida —
ma fra un passo e l'altro non aveva nessun posto dove guardare per ricordarsi
cosa stava facendo e con quali impostazioni.

**Questo riquadro è uno schermo, non un giudice.** Non sa cos'è un bloccaggio,
non conta giri, non decide quando un passo è finito: testo e avanzamento li
scrive Claude da fuori, in `~/Documents/ACCoach/test_step.json`. È quello che lo
rende buono anche per un test inventato lì per lì — ed è successo, il 07/08, con
la semantica di `verify-aids` su ACC.

Gira come processo a sé (`python -m accoach test-panel`) e **non apre la memoria
condivisa**: il 07/08 abbiamo sfiorato l'incidente di due `CoachEngine` accesi
insieme, con ogni giro salvato due volte e la copia indistinguibile da un giro
vero. Un processo che non legge telemetria non può ripeterlo, comunque venga
lanciato. Spegnerlo a fine test è chiuderlo: nessuna opzione da ricordare, quindi
nessuna opzione che resti accesa per sbaglio.

Limite dichiarato: le etichette (`PASSO`, `FATTO`, `in attesa`) sono in italiano
fisso, fuori dall'i18n. Il contenuto dei passi lo scrive Claude in italiano
durante la sessione, e tradurre solo la cornice darebbe un riquadro mezzo
tradotto.
"""

from __future__ import annotations

from dataclasses import dataclass

# Due righe e non tre. Il riquadro ha altezza fissa: il testo che non ci sta
# viene tagliato, perché un riquadro che si allunga sposta la riga dell'orologio
# a ogni cambio di passo — e l'orologio si cerca con la coda dell'occhio, in un
# punto che deve restare lo stesso.
_MAX_BODY_LINES = 2


@dataclass(frozen=True)
class Panel:
    """Le righe già decise, nella forma che il widget deve solo disegnare."""

    where: str = ""
    title: str = ""
    body: tuple[str, ...] = ()
    specs: str = ""
    countdown: str = ""
    note: str = ""
    done: bool = False
    done_msg: str = ""
    waiting: bool = False


def render_step(step: dict | None, now: float) -> Panel:
    """Da un passo letto dal file alle righe da disegnare.

    Pura: nessun file, nessun orologio di sistema, nessun Qt. Tutte le regole
    che si possono sbagliare stanno qui, dove un test le vede in memoria.
    """
    if not step:
        return Panel(waiting=True)

    title = str(step.get("title") or "")
    n, of = step.get("step"), step.get("of")
    where = f"PASSO {n} / {of}" if n and of else ""

    # La scadenza è un istante assoluto, non una durata: così il conto scorre
    # anche quando nessuno sta riscrivendo il file, e una finestra chiusa e
    # riaperta riprende dal punto giusto invece di ricominciare da capo.
    done = bool(step.get("done"))
    countdown = ""
    ends_at = step.get("ends_at")
    if ends_at:
        left = float(ends_at) - now
        if left <= 0:
            # Un contatore che si muove da solo deve sapersi fermare da solo: a
            # `00:00` in attesa di un aggiornamento, il riquadro sarebbe
            # indistinguibile da un'app morta.
            done = True
        else:
            countdown = f"{int(left) // 60:02d}:{int(left) % 60:02d}"

    if done:
        return Panel(where=where, title=title, done=True,
                     done_msg=str(step.get("done_msg") or ""))

    body = tuple(str(step.get("do") or "").splitlines()[:_MAX_BODY_LINES])
    # Orologio e ripetizioni sono due risposte alla stessa domanda — «quanto
    # manca» — e in staccata se ne legge una sola. Se il file le porta entrambe
    # vince l'orologio, perché è quello che si muove.
    note = "" if countdown else str(step.get("note") or "")
    return Panel(where=where, title=title, body=body,
                 specs=str(step.get("specs") or ""),
                 countdown=countdown, note=note)
