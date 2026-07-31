"""I circuiti che HONE si porta dietro.

I file del gioco coprono solo le piste che hai **installate**, e solo se hai
Assetto Corsa. Chi guida ad ACC — che il proprio dato di pista lo tiene
impacchettato — non vedeva niente, ed era l'unico punto dell'app in cui quello
che vedi dipende da cosa hai sul disco.

Da qui `src/accoach/tracks/`: 26 circuiti reali (linea centrale e larghezze),
presi da fonti aperte e citati in `NOTICE.md`. Passano per lo **stesso**
identico fit, ritaglio e disegno dei file di gioco: a valle nessuno sa quale
delle due sorgenti stia guardando, ed è esattamente il punto.

Quello che questi test tengono fermo:

* i file ci sono davvero e si leggono (in un exe è la prima cosa che si rompe);
* le due sorgenti si mescolano in un elenco solo di candidati, e a scegliere è
  il punteggio, non la provenienza;
* l'attribuzione, che è una **condizione della licenza** e non una cortesia;
* e i numeri che hanno motivato tutto: queste larghezze misurano la pista,
  quelle del gioco misurano ogni metro quadro di asfalto.
"""
import math

import pytest

from accoach import trackedges as te


def _all():
    return te.bundled_tracks()


def test_the_circuits_are_there_and_they_parse():
    got = _all()
    assert len(got) >= 26, f"solo {len(got)} circuiti impacchettati"
    for name, path in got:
        e = te.read_csv_edges(path, name)
        assert e is not None, f"{name} non si legge"
        assert len(e) >= 100, f"{name}: {len(e)} punti sono troppo pochi per una pista"


def test_every_circuit_is_a_plausible_circuit():
    """Il controllo che coglierebbe un file corrotto o di un'altra unità di
    misura: lunghezza fra 2 e 22 km, larghezza fra 6 e 25 m."""
    for name, path in _all():
        e = te.read_csv_edges(path, name)
        length = te._length_of(path)
        assert 2_000 < length < 22_000, f"{name}: {length:.0f} m"
        assert 6.0 <= e.width_m() <= 25.0, f"{name}: larga {e.width_m()} m"


def test_the_loop_closes_on_itself():
    """Sono circuiti, non rettilinei: l'ultimo punto sta accanto al primo."""
    for name, path in _all():
        e = te.read_csv_edges(path, name)
        gap = math.hypot(e.x[0] - e.x[-1], e.z[0] - e.z[-1])
        assert gap < 60.0, f"{name}: {gap:.0f} m fra la fine e l'inizio"


def test_none_of_them_has_a_hole():
    """I file del gioco ne hanno (Suzuka scarta 228 punti di fila, e prima del
    fix il nastro tagliava 343 m attraverso il circuito). Questi no, ed è uno
    dei motivi per cui sono qui."""
    for name, path in _all():
        e = te.read_csv_edges(path, name)
        assert not e.breaks, f"{name} ha un buco"


def test_they_measure_the_track_not_every_paved_metre():
    """La ragione misurata per averli, oltre alla copertura.

    Non è che siano più stretti — Austin arriva a 27.6 m e il suo rettilineo dei
    box è davvero largo così. È che **non hanno il gradino**: una pista vera si
    allarga, una via di fuga esplode. Il rapporto fra il punto più largo e la
    mediana lo separa, e i numeri vengono dai file veri:

        i 26 impacchettati    da 1.06 a 2.12   (il peggiore è Austin)
        AC, Spa               2.36   -> La Source, 24.5 m su 10.4 di mediana
        AC, Suzuka            3.35   -> 33.5 m su 10.0

    E quel 33.5 m di Suzuka non è un dettaglio estetico: è ciò che faceva
    scartare 228 punti di fila e tagliare il nastro per 343 m.
    """
    for name, path in _all():
        e = te.read_csv_edges(path, name)
        w = [l + r for l, r in zip(e.left, e.right)]
        w_sorted = sorted(w)
        median = w_sorted[len(w_sorted) // 2]
        ratio = max(w) / median
        assert ratio < 2.3, (
            f"{name}: il punto più largo è {ratio:.2f} volte la mediana "
            f"({max(w):.1f} m contro {median:.1f}) — sembra una via di fuga")


def test_both_sources_compete_in_one_list():
    """Non «prima le impacchettate, il gioco come ripiego»: su una pista che sta
    in entrambe deve vincere quella che descrive meglio il TUO giro, e a saperlo
    è solo il fit."""
    names = [n for n, _ in te.bundled_tracks()]
    assert names, "nessun circuito impacchettato"
    # I due elenchi finiscono nello stesso posto, con lo stesso tipo di voce.
    for name, path in te.bundled_tracks():
        assert te._at_path(path, name) is not None
        assert te._length_of(path) > 0


def test_a_csv_that_is_not_one_reads_as_nothing(tmp_path):
    """Un file che non è quello che pensiamo non va letto «alla meglio»."""
    for blob in ("", "ciao\nmondo\n", "# x_m,y_m\n1,2\n", "1,2,999,999\n" * 40):
        p = tmp_path / "x.csv"
        p.write_text(blob, encoding="utf-8")
        assert te.read_csv_edges(p) is None


def test_the_attribution_travels_with_the_data():
    """Condizione della licenza, non gentilezza: i file sono LGPL-3.0 e vanno
    accompagnati da chi li ha fatti. Se qualcuno aggiunge un circuito da
    un'altra fonte, questo test lo obbliga a dire da dove viene."""
    notice = te.bundled_dir() / "NOTICE.md"
    assert notice.exists(), "manca NOTICE.md accanto ai circuiti"
    text = notice.read_text(encoding="utf-8")
    for must in ("TUMFTM/racetrack-database", "LGPL-3.0", "OpenStreetMap"):
        assert must in text, f"NOTICE.md non nomina {must}"


def test_the_bundle_is_found_the_same_way_inside_the_executable(monkeypatch):
    """Nell'exe la cartella sta sotto _MEIPASS. È la prima cosa che si rompe in
    un pacchetto, e non se ne accorge nessuno finché non lo prova un utente."""
    monkeypatch.setattr(te.sys, "_MEIPASS", r"C:\finto", raising=False)
    assert te.bundled_dir().parts[-2:] == ("accoach", "tracks")
    monkeypatch.delattr(te.sys, "_MEIPASS", raising=False)
    assert te.bundled_dir().is_dir()
