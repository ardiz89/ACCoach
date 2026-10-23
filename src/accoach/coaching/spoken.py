"""L'elenco chiuso di quello che la voce dice in italiano.

Il pilota ha scelto (22/10) una voce registrata con ElevenLabs: ogni frase che
il coach e l'ingegnere dicono in pista diventa un WAV, registrato una volta e
messo nel pacchetto. Una frase detta che non e' in questo elenco non avra' il
suo WAV e uscira' dalla voce di Windows, in silenzio. Da qui partono sia la
generazione dei WAV sia il test che lo impedisce (`tests/test_spoken_catalogue.py`,
che fa girare i percorsi veri e pretende che ogni testo detto ci sia).

Le fonti sono cinque, e la scansione del sorgente ne vede una sola:

* le frasi fisse passate a una chiamata con una `CueCategory` (scansione AST
  dei moduli del coach, come faceva `tools/render_cues.py`) e le parole
  d'innesco italiane, che stanno in una tabella e non in una chiamata;
* le frasi col numero che sono gia' un insieme chiuso: «Qui perdi N decimi»
  (1-25) e «Benzina per circa N giri» (1-3). Il numero e' il consiglio stesso;
* le frasi generali di `Cue.voice` (pressioni, temperature, ABS e TC, i decimi
  oltre i 25): la scansione legge quelle scritte per intero; le quattro della
  pressione sono f-string sull'asse e sono copiate qui una per una;
* il prefisso dell'ingegnere, il ripristino e le leve senza click
  (`engineer/voice_levers.py`).

Resta fuori di proposito il «Self test completato.» di `diagnostics.py`: e' la
prova della voce di sistema, e deve uscire da li'.

Si usa al momento della build e nei test: legge i sorgenti `.py`, che l'EXE
impacchettato non ha.
"""

from __future__ import annotations

import ast
from pathlib import Path

_COACHING = Path(__file__).resolve().parent

#: Le frasi generali della pressione (`pressure.py`): f-string sull'asse, che
#: la scansione non puo' leggere, quindi copiate qui. Se una cambia la' e non
#: qui, il test di chiusura lo dice.
_PRESSURE_VOICE: tuple[str, ...] = tuple(
    f"Gomme {axle} troppo {state}. {action} pressione a freddo."
    for axle in ("anteriori", "posteriori")
    for state, action in (("gonfie", "Togli"), ("sgonfie", "Aggiungi"))
)


def _str_leaves(node: ast.AST) -> list[str]:
    """I testi letterali di un valore: una stringa, o i due rami di un
    `"a" if … else "b"` (il `None` dell'altro ramo non e' testo)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _str_leaves(node.body) + _str_leaves(node.orelse)
    return []


def _scan() -> tuple[set[str], set[str]]:
    """(frasi fisse, frasi `voice=`) delle chiamate che prendono una `CueCategory`.

    Prende i testi letterali di `Cue(CueCategory.X, "…")` e degli aiutanti come
    `self._make(s, CueCategory.X, "…")`, anche quando il testo e' scritto prima
    e passato per nome. Le f-string restano fuori. L'argomento `voice=` (la
    frase generale di `Cue.voice`) sta da parte: e' quello che la voce dice al
    posto del messaggio, e il messaggio di quell'avviso non si dice mai.
    """
    sources = sorted(_COACHING.glob("*.py"))
    if not sources:
        # Un elenco vuoto passerebbe per «niente da registrare»: meglio fermarsi.
        raise RuntimeError(f"nessun sorgente del coach in {_COACHING}")
    messages: set[str] = set()
    voices: set[str] = set()

    def has_cue_category(call: ast.Call) -> bool:
        for a in list(call.args) + [kw.value for kw in call.keywords]:
            if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name)                     and a.value.id == "CueCategory":
                return True
        return False

    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Un testo scritto prima e passato per nome: `msg = "…"` in fuel.py, le
        # costanti `_CALL`/`_APPROACH`/`_BRIEFING` di pitcall.py, `voice = "…"`
        # in tyretemp.py. Senza, il rientro ai box e l'ultimo giro di benzina
        # restavano fuori.
        assigned: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        assigned.setdefault(t.id, []).extend(_str_leaves(node.value))

        def texts(a: ast.AST) -> list[str]:
            if isinstance(a, ast.Name):
                return assigned.get(a.id, [])
            return _str_leaves(a)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and has_cue_category(node):
                for a in node.args:
                    messages.update(t for t in texts(a) if len(t) > 5)
                for kw in node.keywords:
                    into = voices if kw.arg == "voice" else messages
                    into.update(t for t in texts(kw.value) if len(t) > 5)
    return messages, voices


def static_cue_messages() -> set[str]:
    """Le frasi fisse dei moduli del coach e le parole d'innesco italiane
    (le frasi che hanno gia' un WAV di Piper)."""
    messages, _ = _scan()
    # Le parole d'innesco sono una tabella, non una chiamata, e sono le frasi
    # che il pilota sente piu' spesso quando c'e' un focus.
    from .cue import TRIGGER
    messages.update(e["it"] for e in TRIGGER.values())
    return messages


def cue_voice_messages() -> set[str]:
    """Le frasi generali di `Cue.voice`: quelle scritte per intero nel codice
    (temperature, ABS e TC, i decimi oltre i 25) e le quattro della pressione."""
    _, voices = _scan()
    return voices | set(_PRESSURE_VOICE)


def numeric_cue_messages() -> set[str]:
    """Le frasi col numero piccolo, sui loro valori veri.

    Copiano le f-string di `analyzer.py` e `fuel.py`; il runtime cerca la frase
    intera, quindi una differenza di una lettera la manda alla voce di Windows
    (`tests/test_voice_cues.py` le confronta con quello che i rilevatori dicono).
    """
    msgs: set[str] = set()
    # analyzer.py: «Qui perdi {n} decimi», «1 decimo» al singolare
    for n in range(1, 26):
        msgs.add(f"Qui perdi {n} {'decimo' if n == 1 else 'decimi'}")
    # fuel.py: da 1 a 3 giri (l'ultimo giro e' una frase fissa)
    for n in (1, 2, 3):
        msgs.add(f"Benzina per circa {n} {'giro' if n == 1 else 'giri'}.")
    return msgs


def engineer_phrases() -> set[str]:
    """Quello che dice l'ingegnere in italiano: il prefisso, la leva, il ripristino."""
    # Importati qui: `engine.py` importa il coach, e il coach non importa il motore.
    from ..engine import _ENG_VOICE_PREFIX, _ENG_VOICE_REVERT
    from ..engineer.voice_levers import all_voice_levers
    out = {by_lang["it"] for by_tag in _ENG_VOICE_PREFIX.values()
           for by_lang in by_tag.values()}
    out.add(_ENG_VOICE_REVERT["it"])
    out.update(all_voice_levers())
    return out


def spoken_phrases() -> list[str]:
    """Tutte le frasi italiane che `Voice.say` puo' ricevere dal motore, una
    volta sola ciascuna, in ordine."""
    return sorted(static_cue_messages() | numeric_cue_messages()
                  | cue_voice_messages() | engineer_phrases())
