"""La suite non scrive nella cartella dati del pilota.

Scoperto il 19/09 **mentre il pilota girava a Suzuka**: nel suo log dal vivo
comparivano righe «=== ACCoach starting ===» e avvisi sui giri che non erano
dell'app — erano le mie esecuzioni della suite. `setup_logging()` apre un
handler su `logs_dir()`, cioe' `~/Documents/ACCoach/logs`, la stessa cartella
che l'app vera sta scrivendo e che `logs --zip` impacchetta per una
segnalazione.

Il danno peggiore non e' il disordine: e' che la traccia di una sessione in
pista — l'unica prova che abbiamo di cosa ha fatto il coach — si sporca con
righe che *sembrano* l'app. Dieci minuti passati a chiedersi perche' il coach si
riavviasse.

Il test guarda l'**effetto** (il file vero non cresce), non la causa (quale
handler e' stato montato): una cura che spostasse il log in un terzo posto
passerebbe un controllo sulla causa e fallirebbe questo.
"""
import logging
from pathlib import Path

from accoach import logging_setup
from accoach.logging_setup import setup_logging


def _log_vero() -> Path:
    """Il percorso reale, calcolato senza passare da `paths` (che il conftest
    rimpiazza apposta): se lo chiedessimo a `paths` ci sentiremmo rispondere la
    sandbox, e il test proverebbe se stesso."""
    return Path.home() / "Documents" / "ACCoach" / "logs" / "accoach.log"


def test_la_suite_non_tocca_il_log_del_pilota():
    vero = _log_vero()
    prima = vero.stat().st_size if vero.exists() else None

    root = logging.getLogger()
    quanti = len(root.handlers)
    # `setup_logging` stacca il logger «accoach» dalla radice (`propagate =
    # False`). Se non lo si rimette, da qui in poi `caplog` non vede piu' niente
    # e i test che ci contano falliscono **altrove**, per ordine di esecuzione:
    # e' successo, cinque test rossi che passavano da soli.
    accoach_log = logging.getLogger("accoach")
    propagava = accoach_log.propagate
    try:
        # `setup_logging` si configura una volta sola per processo (`_configured`),
        # quindi senza questo il secondo test della suite che lo chiama non
        # eseguirebbe niente e passerebbe a vuoto.
        logging_setup._configured = False
        setup_logging()
        logging.getLogger("accoach").info("riga di prova della suite")
        for h in root.handlers:
            h.flush()
    finally:
        for h in root.handlers[quanti:]:
            root.removeHandler(h)
            h.close()
        for h in accoach_log.handlers[:]:
            accoach_log.removeHandler(h)
            h.close()
        accoach_log.propagate = propagava
        logging_setup._configured = False

    dopo = vero.stat().st_size if vero.exists() else None
    assert dopo == prima, (
        f"la suite ha scritto nel log del pilota: {prima} -> {dopo} byte. "
        f"E' la cartella che l'app usa dal vivo e che `logs --zip` spedisce")


def test_il_log_della_suite_finisce_davvero_da_qualche_parte():
    """L'altra meta': isolare non deve voler dire perdere.

    Un `setup_logging` che non scrive piu' da nessuna parte passerebbe il test
    qui sopra e toglierebbe alla suite la diagnostica quando serve.
    """
    root = logging.getLogger()
    quanti = len(root.handlers)
    # `setup_logging` stacca il logger «accoach» dalla radice (`propagate =
    # False`). Se non lo si rimette, da qui in poi `caplog` non vede piu' niente
    # e i test che ci contano falliscono **altrove**, per ordine di esecuzione:
    # e' successo, cinque test rossi che passavano da soli.
    accoach_log = logging.getLogger("accoach")
    propagava = accoach_log.propagate
    try:
        # `setup_logging` si configura una volta sola per processo (`_configured`),
        # quindi senza questo il secondo test della suite che lo chiama non
        # eseguirebbe niente e passerebbe a vuoto.
        logging_setup._configured = False
        setup_logging()
        logging.getLogger("accoach").info("riga di prova della suite")
        for h in root.handlers:
            h.flush()
        scritto = logging_setup.logs_dir() / "accoach.log"
        assert scritto.exists() and scritto.stat().st_size > 0
        assert "riga di prova" in scritto.read_text(encoding="utf-8")
    finally:
        for h in root.handlers[quanti:]:
            root.removeHandler(h)
            h.close()
        for h in accoach_log.handlers[:]:
            accoach_log.removeHandler(h)
            h.close()
        accoach_log.propagate = propagava
        logging_setup._configured = False
