"""La voce non deve riusare lo stesso motore per sintetizzare su file.

Trovato in pista il 2026-08-12, ed e' il difetto peggiore visto finora: non una
caduta, ma un **silenzio**. Riusando un solo motore `pyttsx3`, la seconda o la
terza `save_to_file` + `runAndWait` non torna piu'. Il thread della voce resta
*vivo* — quindi niente eccezione, niente riga di ripiego, niente da vedere nei
log — ma fermo dentro la chiamata; e siccome la coda e' una sola, da quel
momento **muore anche tutto il resto**, compresi i suoni pre-registrati.

In pista e' successo dopo pochi minuti: il coach ha continuato a decidere cosa
dire, a scriverlo sullo schermo e a segnarlo nel registro, e il pilota non ha
piu' sentito niente — nemmeno «Bloccaggio».

Misurato su questa macchina, cinque frasi di fila:

* stesso motore + `save_to_file` → si pianta alla seconda;
* stesso motore + `say`          → cinque su cinque;
* motore nuovo ogni volta        → cinque su cinque.

Da qui la regola provata qui sotto: **la via che scrive su file prende un motore
nuovo ogni volta**. Con un'insidia che il primo test copre, perche' e' il modo
in cui la cura fallirebbe restando identica a leggersi: `pyttsx3.init()` tiene i
motori in cache e, con uno gia' appeso a `Voice`, ne restituirebbe *lo stesso*.
"""
import sys

import pytest

from accoach.coaching.voice import Voice


class _MotoreFinto:
    """Un motore che registra cosa gli e' stato chiesto e scrive un WAV finto."""

    def __init__(self, marca: bytes = b"RIFF-finto") -> None:
        self.marca = marca
        self.frasi: list[str] = []
        self.giri = 0

    def save_to_file(self, text, path):
        self.frasi.append(text)
        from pathlib import Path
        Path(path).write_bytes(self.marca)

    def runAndWait(self):
        self.giri += 1

    def setProperty(self, *a):
        pass

    def getProperty(self, *a):
        return []

    def say(self, text):                      # non deve mai servire, qui
        self.frasi.append(f"say:{text}")


def _voce_muta() -> Voice:
    """Una `Voice` senza audio ne' thread: qui si prova la scelta, non il suono."""
    return Voice(enabled=False)


def test_la_sintesi_su_file_non_tocca_il_motore_tenuto():
    """Il cuore del difetto: e' il RIUSO che pianta, non la sintesi."""
    v = _voce_muta()
    tenuto = _MotoreFinto(b"TENUTO")
    v._engine = tenuto

    nuovi = []

    def _fabbrica():
        m = _MotoreFinto(b"NUOVO")
        nuovi.append(m)
        return m

    v._new_engine = _fabbrica

    assert v._render_wav_bytes("prima") == b"NUOVO"
    assert v._render_wav_bytes("seconda") == b"NUOVO"

    assert len(nuovi) == 2, "ogni frase vuole un motore suo"
    assert [m.frasi for m in nuovi] == [["prima"], ["seconda"]]
    assert tenuto.frasi == [], "il motore tenuto non deve sintetizzare su file"


def test_ogni_frase_gira_il_suo_motore_una_volta_sola():
    """`runAndWait` una volta per motore: due giri sullo stesso sono il difetto."""
    v = _voce_muta()
    nuovi = []
    v._new_engine = lambda: nuovi.append(_MotoreFinto()) or nuovi[-1]

    for frase in ("una", "due", "tre"):
        v._render_wav_bytes(frase)

    assert len(nuovi) == 3
    assert [m.giri for m in nuovi] == [1, 1, 1]


def test_il_wav_temporaneo_non_resta_in_giro():
    """Una frase per giro per tutta una sessione: i file non si accumulano."""
    import tempfile
    from pathlib import Path

    v = _voce_muta()
    visti = []

    class _Spia(_MotoreFinto):
        def save_to_file(self, text, path):
            visti.append(Path(path))
            super().save_to_file(text, path)

    v._new_engine = _Spia
    v._render_wav_bytes("una")

    assert visti, "il test non ha osservato niente"
    assert not visti[0].exists(), f"{visti[0]} e' rimasto in {tempfile.gettempdir()}"


@pytest.mark.skipif(sys.platform != "win32", reason="SAPI5 esiste solo su Windows")
def test_il_motore_nuovo_scavalca_davvero_la_cache_di_pyttsx3():
    """La cura fallirebbe in silenzio se tornasse il motore gia' in cache.

    `pyttsx3.init()` tiene i motori in una cache per nome di driver: con uno
    gia' vivo restituisce **quello**, e il riuso — cioe' il difetto — tornerebbe
    intatto sotto un nome nuovo.
    """
    pyttsx3 = pytest.importorskip("pyttsx3")
    v = _voce_muta()
    try:
        v._engine = pyttsx3.init()
    except Exception as e:                      # niente audio su questa macchina
        pytest.skip(f"SAPI non disponibile: {e}")

    assert pyttsx3.init() is v._engine, "premessa: init() e' in cache"

    a = v._new_engine()
    b = v._new_engine()
    assert a is not v._engine
    assert b is not v._engine
    assert a is not b
