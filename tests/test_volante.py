"""Le marce come risposta, ad auto ferma (`tools/voce/volante.py`).

Strumento da sviluppo, fuori dal pacchetto — ma la funzione che decide «questa
e' una risposta» sta nella suite lo stesso: se fraintende, il pilota risponde e
io leggo un'altra cosa, e una sessione in pista non si rifa'.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "voce"))

from volante import FERMO_DA_S, FERMO_KMH, leggi_risposta  # noqa: E402


def test_una_marcia_inserita_da_fermo_e_una_risposta():
    assert leggi_risposta("N", "1", 0.0) == "1"
    assert leggi_risposta("N", "5", 0.0) == "5"
    assert leggi_risposta("N", "R", 0.0) == "R"


def test_la_stessa_marcia_non_si_rilegge():
    """Sessanta frame al secondo sulla stessa marcia sono una risposta sola."""
    assert leggi_risposta("3", "3", 0.0) is None


def test_guidando_le_marce_sono_guida():
    """Il difetto peggiore possibile qui: scalare in staccata e vedermi
    registrare un «no» che il pilota non ha mai dato."""
    assert leggi_risposta("4", "3", 180.0) is None
    assert leggi_risposta("N", "1", FERMO_KMH + 0.1) is None


def test_il_folle_e_riposo_non_una_risposta():
    assert leggi_risposta("1", "N", 0.0) is None


def test_le_marce_alte_non_dicono_niente():
    """Oltre la 5a si scala guidando: leggerle vorrebbe dire sentire cose mai
    dette. Fermo in 6a non e' una risposta, e' un'auto in 6a."""
    assert leggi_risposta("N", "6", 0.0) is None


def test_ai_box_fermi_con_qualche_decimo_di_deriva_si_risponde_lo_stesso():
    """La velocita' in sosta non e' zero secco: a zero la risposta si perde."""
    assert leggi_risposta("N", "2", 0.4) == "2"


def test_senza_un_prima_non_c_e_un_cambio_da_leggere():
    """Trovato in pista la sera del 23/08, col pilota gia' in macchina: uscendo
    dal menu il gioco passa da PAUSE a LIVE e la marcia riparte da R, quindi
    ogni rientro in pista arrivava come un «ripeti». Tre in un minuto, nessuno
    detto da lui. Un canale di risposta che inventa risposte e' peggio di uno
    che non c'e'."""
    assert leggi_risposta(None, "R", 0.0) is None
    assert leggi_risposta(None, "1", 0.0) is None


def test_senza_una_domanda_non_ci_sono_risposte():
    """Il secondo difetto della stessa sera, e il peggiore: innestare la prima
    per uscire dal box e' arrivato come «si'», due volte, e nessuno aveva
    chiesto niente. Un canale sempre in ascolto trasforma ogni gesto di guida in
    una parola — ed era una risposta *plausibile* a una domanda inesistente,
    cioe' la forma di errore che non si riconosce leggendo il risultato."""
    assert leggi_risposta("N", "1", 0.0, domanda_aperta=False) is None


def test_l_istante_in_cui_ti_fermi_non_e_una_risposta():
    """Fermarsi e ripartire sono pieni di cambiate che sono guida."""
    assert leggi_risposta("N", "1", 0.0, fermo_da_s=FERMO_DA_S / 2) is None
    assert leggi_risposta("N", "1", 0.0, fermo_da_s=FERMO_DA_S + 0.1) == "1"
