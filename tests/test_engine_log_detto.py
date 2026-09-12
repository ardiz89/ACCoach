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
    assert _focus_log_line(None).startswith("focus | nessuno")
    assert _focus_log_line(FocusReport(kind=FocusKind.ASSESS,
                                       message="")).startswith("focus | nessuno")


def test_e_dice_quale_dei_due_nessuno_e():
    """«Nessun focus» vale due stati opposti: *sto ancora guardando* (non ho
    abbastanza giri per eleggere) e *sei pulito, non ho niente da eleggere*. La
    riga di log serve a interpretare le righe `detto |` che le stanno attorno, e
    quelle due portano a letture opposte: nel primo caso il coach tace perche'
    non sa ancora, nel secondo perche' non c'e' niente da dire."""
    assesso = _focus_log_line(FocusReport(kind=FocusKind.ASSESS, message=""))
    pulito = _focus_log_line(FocusReport(kind=FocusKind.CLEAN, message=""))
    assert assesso != pulito
    assert "assess" in assesso and "clean" in pulito


def test_e_un_giro_mai_giudicato_non_si_confonde_con_un_giro_pulito():
    """Senza riferimento o senza curve il giro non passa nemmeno dal coach: e'
    un terzo stato, e finiva anche lui in «nessuno»."""
    assert _focus_log_line(None) != _focus_log_line(
        FocusReport(kind=FocusKind.CLEAN, message=""))


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


# --- il quarto «nessuno»: il giro che non e' stato contato -------------------

def test_un_giro_scartato_non_si_legge_come_uno_contato():
    """Il 01/09, su 14 giri 6 erano sporchi e il focus non e' mai stato eletto.

    Il coach li scarta apposta — un'escursione gonfia la perdita di ogni curva e
    inventerebbe una debolezza — ma nel log un giro scartato ripeteva parola per
    parola la riga del giro prima, perche' `observe` restituisce l'ultimo
    rapporto. Da fuori «valuto 2/3» per dieci giri di fila era indistinguibile da
    un coach rotto.
    """
    fermo = _focus_log_line(FocusReport(kind=FocusKind.ASSESS, message=""))
    scartato = _focus_log_line(FocusReport(kind=FocusKind.ASSESS, message=""),
                               counted=False, discarded=1)
    assert fermo != scartato
    assert "non contato" in scartato
    assert "non pulito" in scartato


def test_la_riga_dice_quanti_giri_ha_buttato_in_questa_finestra():
    """Un giro solo e' sfortuna, sei su quattordici sono la sessione."""
    riga = _focus_log_line(FocusReport(kind=FocusKind.ASSESS, message=""),
                           counted=False, discarded=6)
    assert "scartati=6" in riga


def test_anche_sotto_un_focus_aperto_si_vede_che_il_giro_non_conta():
    """Qui l'equivoco e' peggiore: la riga porta nome, tema e perdita del focus,
    quindi sembra un giro di esercizio come gli altri — e invece il progresso
    che mostra e' quello del giro prima."""
    riga = _focus_log_line(_report("trazione", CueCategory.MORE_THROTTLE),
                           counted=False, discarded=3)
    assert "Variante Ascari" in riga        # il contesto resta
    assert "non contato" in riga
    assert "scartati=3" in riga


def test_un_giro_contato_non_porta_la_coda():
    """La riga normale non cambia: e' quella che si legge nove volte su dieci."""
    riga = _focus_log_line(_report("trazione", CueCategory.MORE_THROTTLE))
    assert "non contato" not in riga
    assert "scartati" not in riga


def test_la_riga_resta_una_riga_sola_nel_formato_delle_altre():
    riga = _focus_log_line(FocusReport(kind=FocusKind.ASSESS, message=""),
                           counted=False, discarded=2)
    assert "\n" not in riga
    assert riga.startswith("focus | ")
    assert riga.count(" | ") >= 3


def test_il_giro_scartato_finisce_nel_log_per_davvero(tmp_path, caplog):
    """L'effetto, non la forma: un giro sporco vero, dentro il motore.

    Il fixture deve *separare* cio' che la cura separa, altrimenti passa per il
    motivo sbagliato: i giri sporchi qui perdono in una curva diversa e molto di
    piu' dei puliti, cosi' se venissero contati la finestra e la debolezza eletta
    sarebbero visibilmente altre.
    """
    import logging

    from accoach.comparison import Reference
    from accoach.coaching.debrief import build_lap_debrief
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
        eng._focus = FocusCoach(min_laps=3)

        pulito = synth.build_lap(slow_corner=0, amt=30, n=300, clean=True)
        sporco = synth.build_lap(slow_corner=1, amt=60, n=300, clean=False)

        # Il fixture fa davvero quello che credo: due giri diversi, e uno solo
        # dei due e' "stabile" per il coach.
        assert pulito.clean is True and pulito.valid
        assert sporco.clean is False
        d_pulito = build_lap_debrief(pulito, eng._reference, eng._corners)
        d_sporco = build_lap_debrief(sporco, eng._reference, eng._corners)
        perse_pulito = {loss.index for loss in d_pulito.losses}
        perse_sporco = {loss.index for loss in d_sporco.losses}
        print("pulito perde in", perse_pulito, "sporco perde in", perse_sporco)
        assert perse_pulito != perse_sporco, (
            "fixture inerte: i due giri perdono nelle stesse curve, quindi il "
            "test passerebbe anche se i giri sporchi venissero contati")

        with caplog.at_level(logging.INFO, logger="accoach.coach"):
            for lap in (pulito, sporco, pulito, sporco, pulito):
                eng._observe_lap(lap)

        righe = [r.getMessage() for r in caplog.records
                 if r.getMessage().startswith("focus |")]
        print("\n".join(righe))
        assert len(righe) == 5
        scartate = [r for r in righe if "non contato" in r]
        assert len(scartate) == 2, righe
        assert "scartati=1" in scartate[0]
        assert "scartati=2" in scartate[1]
        # e i giri puliti restano puliti da leggere
        assert not any("non contato" in righe[i] for i in (0, 2, 4))
        # il comportamento non e' cambiato: solo i tre puliti sono in finestra
        assert len(eng._focus.window) == 3
    finally:
        eng.close()
