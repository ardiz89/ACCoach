"""La traccia di cio' che il coach dice, che il 10/08 non c'era.

In pista due prove sono rimaste **indecidibili**, e non per un difetto del
coach: perche' non restava traccia di niente.

* prova 16 — «in pista senti parole, non frasi»: il pilota non ricordava cosa
  avesse sentito, ed e' giusto cosi'. Non e' un compito da pilota.
* prova 21 — «il coach e' assillante?»: e' una domanda sui *tempi* fra due
  ripetizioni. A memoria non si cronometra, mentre si frena men che meno.

Qui si prova la forma della riga, non il fatto che il logger scriva: la forma e'
la parte che si puo' sbagliare, ed e' quella che rende la riga leggibile fra un
mese.
"""
from accoach.coaching.cue import CueCategory
from accoach.coaching.focus import Focus, FocusKind, FocusReport
from accoach.engine import _focus_log_line, _spoken_log_line


def _report(theme: str, category) -> FocusReport:
    return FocusReport(
        kind=FocusKind.DRILL,
        message="",
        focus=Focus(corner_index=7, name="Variante Ascari", theme=theme,
                    category=category, baseline_ms=5810.0, drill=""),
    )


def test_la_riga_dice_voce_e_schermo_separati():
    """Il punto della prova 16 e' proprio che le due NON coincidono."""
    riga = _spoken_log_line(CueCategory.MORE_THROTTLE, "traction",
                            "gas", "Piu' gas qui")
    assert "voce='gas'" in riga
    assert 'schermo="Piu\' gas qui"' in riga or "schermo=\"Piu' gas qui\"" in riga
    assert "tema=traction" in riga


def test_senza_focus_il_tema_e_un_trattino_non_none():
    """`None` scritto in un log si legge come un difetto; il trattino no."""
    riga = _spoken_log_line(CueCategory.LOCKED, None,
                            "Bloccaggio, alleggerisci il freno",
                            "Bloccaggio, alleggerisci il freno")
    assert "tema=-" in riga
    assert "None" not in riga


def test_la_categoria_compare_per_nome_leggibile():
    """Serve a distinguere una parola di tecnica da un allarme di sicurezza.

    E' la distinzione su cui la prova 17 si gioca: sicurezza e box parlano per
    intero anche quando il filtro e' attivo, e senza la categoria nel log non si
    puo' dire se una frase intera fosse legittima.
    """
    riga = _spoken_log_line(CueCategory.LOCKED, "traction", "x", "y")
    assert CueCategory.LOCKED.value in riga


def test_il_focus_eletto_si_legge_con_curva_tema_e_perdita():
    riga = _focus_log_line(_report("trazione", CueCategory.MORE_THROTTLE))
    assert "Variante Ascari" in riga
    assert "tema=traction" in riga      # la chiave inglese, non l'etichetta
    assert "5810 ms" in riga


def test_nessun_focus_lo_dice_invece_di_tacere():
    """Il silenzio nel log sarebbe indistinguibile da un log non scritto."""
    assert _focus_log_line(None) == "focus | nessuno"
    assert _focus_log_line(FocusReport(kind=FocusKind.ASSESS,
                                       message="")) == "focus | nessuno"


# --- e che la riga esca davvero, non solo che sia formattata bene ------------

def test_il_focus_eletto_finisce_nel_log_per_davvero(tmp_path, caplog):
    """Fin qui si e' provata la forma; questo prova l'**effetto**.

    Un formattatore giusto chiamato da nessuno e' esattamente il difetto che
    questa traccia esiste per non avere: il 10/08 il log c'era, e non conteneva
    niente di cio' che serviva.
    """
    import logging

    from accoach.comparison import Reference
    from accoach.coaching.focus import FocusCoach
    from accoach.engine import CoachEngine
    from accoach.track import detect_corners

    import synth

    class _Dummy:
        def read(self): ...
        def close(self): ...

    eng = CoachEngine(reader=_Dummy(), voice=None, laps_dir=tmp_path)
    try:
        ref = synth.build_lap(n=300, clean=True)
        eng._reference = Reference(ref)
        eng._corners = detect_corners(ref.samples)
        eng._focus = FocusCoach()
        slow = synth.build_lap(slow_corner=0, amt=30, n=300, clean=True)

        with caplog.at_level(logging.INFO, logger="accoach.coach"):
            for _ in range(3):
                eng._observe_lap(slow)

        righe = [r.getMessage() for r in caplog.records
                 if r.getMessage().startswith("focus |")]
        assert righe, "il focus e' stato eletto ma il log non lo dice"
        assert any("tema=" in r and "nessuno" not in r for r in righe), righe
    finally:
        eng.close()
