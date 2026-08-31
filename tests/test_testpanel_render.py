"""Da passo a righe: la funzione che decide cosa finisce sullo schermo.

Pura di proposito — niente Qt, niente file. Le regole che contano davvero
(l'orologio che scade da solo, le due risposte che non convivono, il testo che
viene tagliato invece di allungare il riquadro) si verificano qui in memoria, e
al widget resta da dimostrare solo che le disegna dove ha detto.
"""
import pytest

from accoach.testpanel import render_step


def test_senza_passo_il_riquadro_e_in_attesa():
    p = render_step(None, now=1000.0)
    assert p.waiting is True
    assert p.title == ""


def test_il_titolo_e_la_posizione_nel_protocollo():
    p = render_step({"title": "BLOCCAGGI", "step": 3, "of": 7}, now=1000.0)
    assert p.title == "BLOCCAGGI"
    assert p.where == "PASSO 3 / 7"


def test_senza_numerazione_non_si_inventa_una_posizione():
    p = render_step({"title": "BLOCCAGGI"}, now=1000.0)
    assert p.where == ""


def test_orologio_in_minuti_e_secondi():
    # 767 s = 12:47
    p = render_step({"title": "STINT", "ends_at": 1767.0}, now=1000.0)
    assert p.countdown == "12:47"
    assert p.done is False


def test_lo_zero_iniziale_c_e_sempre():
    """Un campo che cambia larghezza si sposta sotto l'occhio: 5:05 mai."""
    p = render_step({"title": "STINT", "ends_at": 1305.0}, now=1000.0)
    assert p.countdown == "05:05"


def test_scaduto_significa_fatto_senza_che_nessuno_lo_dica():
    p = render_step({"title": "STINT", "ends_at": 1000.0}, now=1000.0)
    assert p.done is True
    assert p.countdown == ""


def test_resta_fatto_anche_molto_dopo():
    """Il verde non scade a sua volta: mezz'ora dopo è ancora lì."""
    p = render_step({"title": "STINT", "ends_at": 1000.0}, now=2800.0)
    assert p.done is True


def test_un_passo_senza_orologio_si_dichiara_finito_a_mano():
    p = render_step({"title": "BLOCCAGGI", "done": True,
                     "done_msg": "Aspetta il prossimo passo"}, now=1000.0)
    assert p.done is True
    assert p.done_msg == "Aspetta il prossimo passo"


def test_il_verde_non_porta_con_se_il_corpo_del_passo():
    p = render_step({"title": "BLOCCAGGI", "do": "Frena forte",
                     "specs": "ABS 0", "done": True}, now=1000.0)
    assert p.body == ()
    assert p.specs == ""


def test_le_ripetizioni_quando_non_c_e_orologio():
    p = render_step({"title": "BLOCCAGGI", "note": "1 di 3"}, now=1000.0)
    assert p.note == "1 di 3"
    assert p.countdown == ""


def test_mai_due_risposte_alla_stessa_domanda():
    """Orologio e ripetizioni insieme: in staccata se ne legge una sola."""
    p = render_step({"title": "STINT", "ends_at": 1767.0, "note": "1 di 3"},
                    now=1000.0)
    assert p.countdown == "12:47"
    assert p.note == ""


def test_il_corpo_si_ferma_a_due_righe():
    p = render_step({"title": "X", "do": "una\ndue\ntre\nquattro"}, now=1000.0)
    assert p.body == ("una", "due")


def test_i_campi_che_mancano_non_diventano_stringhe_none():
    p = render_step({"title": "X"}, now=1000.0)
    assert (p.body, p.specs, p.note, p.countdown, p.done_msg) == ((), "", "", "", "")


def test_ends_at_come_stringa_iso_non_ha_countdown():
    """L'errore più probabile: `ends_at` scritto come data invece che epoch.

    Deve degradare a "nessun orologio", non a "fatto" — il resto del passo
    (titolo, corpo, specifiche) resta comunque in piedi.
    """
    p = render_step({"title": "STINT", "do": "Resta a 220 in curva 1",
                     "specs": "TC 4", "ends_at": "2026-08-08T12:00:00"},
                    now=1000.0)
    assert p.countdown == ""
    assert p.done is False
    assert p.title == "STINT"
    assert p.body == ("Resta a 220 in curva 1",)
    assert p.specs == "TC 4"


def test_ends_at_come_lista_non_ha_countdown():
    """Stesso caso, con un tipo che `float()` non converte affatto."""
    p = render_step({"title": "STINT", "do": "Resta a 220 in curva 1",
                     "ends_at": [1, 2, 3]}, now=1000.0)
    assert p.countdown == ""
    assert p.done is False
    assert p.title == "STINT"
    assert p.body == ("Resta a 220 in curva 1",)


@pytest.mark.parametrize("valore", ["NaN", "Infinity", "-Infinity", float("nan")])
def test_ends_at_non_finito_non_ha_countdown(valore):
    """I due valori che `float()` accetta ma l'aritmetica dell'orologio no.

    JSON li scrive come letterali senza virgolette e `json.load` li legge
    volentieri. NaN non è mai <= 0 e `int(inf)` solleva: senza guardia
    l'eccezione uscirebbe dalla `render_step` dentro il timer di Qt e il
    riquadro resterebbe fermo sul passo precedente — il congelamento è peggio
    di una caduta, perché non si vede.
    """
    p = render_step({"title": "STINT", "do": "Resta a 220 in curva 1",
                     "ends_at": valore}, now=1000.0)
    assert p.countdown == ""
    assert p.done is False
    assert p.title == "STINT"
    assert p.body == ("Resta a 220 in curva 1",)


# --- --top: convivere con l'HUD, che dal 10/08 sta nello stesso angolo --------

@pytest.mark.parametrize("argv, atteso", [
    ([], 24),
    (["--top", "378"], 378),
    (["--top", "0"], 0),
])
def test_parse_top_legge_il_numero(argv, atteso):
    from accoach.testpanel import parse_top
    assert parse_top(argv) == atteso


@pytest.mark.parametrize("argv", [["--top"], ["--top", "pippo"], ["--top", ""]])
def test_parse_top_torna_al_margine_se_non_e_un_numero(argv):
    """Un argomento sbagliato non deve impedire al riquadro di comparire.

    Si accende col pilota gia' seduto: una finestra che non c'e' e' peggio di
    una piazzata male, e chi la guarda non ha modo di leggere un traceback.
    """
    from accoach.testpanel import parse_top
    assert parse_top(argv) == 24
