"""Una modifica bocciata resta da ripristinare finche' il pilota non lo dice.

Il difetto, riprodotto il 13/10 su un assetto vero in copia: l'Ingegnere boccia
una modifica (REVERTED, con dentro i click che la riportano indietro) e **al
giro dopo se ne dimentica**. Tre pezzi, ognuno a posto da solo:

* `RaceEngineer.observe` non guardava se c'era un ripristino in sospeso: con la
  finestra appena svuotata rispondeva COLLECT, e tre giri dopo `_propose`
  metteva in attesa il rimedio successivo al posto del ripristino;
* il motore tiene **una** decisione, l'ultima: il REVERTED restava sullo schermo
  per un giro, quello di rientro;
* la pagina offriva «Prepara la modifica nell'editor» solo per una proposta, e
  quindi per quell'unico giro il pilota leggeva «ripristino» senza un bottone
  per farlo.

Risultato: il secondo rimedio scritto SOPRA il primo, che era stato bocciato, e
giudicato contro una base guidata con il primo ancora montato.

Qui sta la proprieta' intera, dal nucleo allo schermo, perche' e' una catena e
ogni anello provato da solo non l'avrebbe vista.
"""
import dataclasses
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import synth
from accoach.engine import CoachEngine
from accoach.engineer import (
    Balance,
    DecisionKind,
    LapStats,
    Phase,
    RaceEngineer,
    Speed,
    Symptom,
)
from accoach.engineer.profiles import GT3_PROFILE
from accoach.telemetry.snapshot import TelemetrySnapshot

_WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"

#: Sottosterzo in percorrenza nel veloce: sulla GT3 il primo rimedio e' l'ala
#: posteriore, che si cambia solo ai box. E' il caso del difetto — una modifica
#: «al volo» ha la sua strada (il motore guarda la manopola).
SYM = Symptom(Balance.UNDERSTEER, Phase.APEX, Speed.HIGH)


def _lap(time_ms=100000, score=0.6):
    return LapStats(lap_time_ms=time_ms, stable=True,
                    symptom_scores={SYM: score}, symptom_corners={SYM: 4},
                    pressures_hot={"front": 26.9, "rear": 26.9})


def _bocciata(eng=None):
    """Un Ingegnere che ha appena bocciato la sua prima modifica.

    Proposta, scritta, tre giri in cui il sintomo non si muove: REVERTED.
    """
    eng = eng or RaceEngineer(GT3_PROFILE, min_stable=3)
    for _ in range(8):
        proposta = eng.observe(_lap())
        if proposta.kind is DecisionKind.PROPOSE:
            break
    else:
        raise AssertionError("il fixture non arriva a una proposta")
    eng.mark_applied()
    verdetto = None
    for _ in range(3):
        verdetto = eng.observe(_lap(time_ms=101000))
    assert verdetto.kind is DecisionKind.REVERTED
    # Il fixture deve essere il caso del difetto, o i test sotto passano per il
    # motivo sbagliato: una modifica da box, e un ripristino di segno opposto.
    assert proposta.change.tag == "BOX"
    assert (verdetto.change.changes[0].delta_clicks
            == -proposta.change.changes[0].delta_clicks)
    return eng, proposta, verdetto


# --- il nucleo ---------------------------------------------------------------

def test_a_restore_nobody_made_is_still_the_answer_laps_later():
    """Il pilota non rientra subito: finisce il giro, magari ne fa altri tre.
    A ognuno la risposta e' ancora «rimetti com'era», con gli stessi click."""
    eng, _, verdetto = _bocciata()
    for _ in range(6):
        d = eng.observe(_lap())
        assert d.kind is DecisionKind.REVERTED
        assert d.change.as_setup_payload() == verdetto.change.as_setup_payload()
        assert d.message == verdetto.message
    assert eng._pending_is_revert, "il ripristino e' ancora quello in attesa"


def test_nothing_is_proposed_on_top_of_a_rejected_change():
    """Il danno vero: sei giri puliti bastano e avanzano per una proposta nuova
    (ne servono tre), e quella proposta sarebbe un click in piu' su una macchina
    che ha ancora addosso quello bocciato."""
    eng, _, _ = _bocciata()
    kinds = {eng.observe(_lap()).kind for _ in range(6)}
    assert DecisionKind.PROPOSE not in kinds
    assert DecisionKind.EVALUATING not in kinds
    assert eng.active is None, "niente e' sotto misura sopra una modifica bocciata"


def test_laps_driven_on_the_rejected_setup_are_not_the_next_baseline():
    """La base del rimedio dopo si misura sull'assetto ripristinato. I giri fatti
    mentre il ripristino aspetta sono guidati con la modifica bocciata: se
    entrassero nella finestra sarebbero loro la base."""
    eng, _, _ = _bocciata()
    for _ in range(6):
        eng.observe(_lap())
    assert eng.window == []
    eng.mark_applied()
    assert eng.observe(_lap()).kind is DecisionKind.COLLECT


def test_once_the_driver_confirms_the_loop_moves_on_to_another_lever():
    """Il blocco si scioglie con la conferma e solo con quella — e scioglie
    davvero: tre giri puliti dopo c'e' una proposta, ed e' un'altra leva."""
    eng, proposta, _ = _bocciata()
    for _ in range(4):
        eng.observe(_lap())
    eng.mark_applied()
    assert not eng._pending_is_revert and eng._pending is None
    d = None
    for _ in range(3):
        d = eng.observe(_lap())
    assert d.kind is DecisionKind.PROPOSE
    assert d.change.rationale != proposta.change.rationale


def test_a_shower_does_not_cancel_a_restore_that_is_still_due():
    """Il ripristino e' un fatto sulla macchina, non una misura: la pioggia
    invalida le misure, non toglie l'ala che abbiamo appena bocciato. «Sul
    bagnato non consiglio» qui sarebbe il modo di dimenticarsela."""
    eng, _, verdetto = _bocciata()
    d = eng.observe(dataclasses.replace(_lap(), wet=True))
    assert d.kind is DecisionKind.REVERTED
    assert d.change.as_setup_payload() == verdetto.change.as_setup_payload()
    # …e nemmeno il ritorno all'asciutto, che e' un cambio di condizioni.
    eng.observe(dataclasses.replace(_lap(), wet=False))
    assert eng.observe(_lap()).kind is DecisionKind.REVERTED


def test_the_numbers_of_the_verdict_stay_with_the_restore():
    """Perche' rimetterla com'era: il pilota deve poterlo rileggere finche' non
    l'ha fatto, non solo nel giro di rientro."""
    eng, _, verdetto = _bocciata()
    assert verdetto.outcome is not None and verdetto.outcome.kept is False
    assert eng.observe(_lap()).outcome == verdetto.outcome


# --- il motore: quello che arriva alla pagina, alla voce e al registro ---------

class _Dead:
    def read(self):
        return TelemetrySnapshot.disconnected()

    def close(self):
        pass


@pytest.fixture
def motore(tmp_path, monkeypatch):
    """Un `CoachEngine` il cui Ingegnere ha appena bocciato una modifica.

    I giri sono `LapStats` scritti a mano (la diagnosi di un giro sintetico non
    produce un sintomo diffuso), ma passano per la strada vera: `_observe_lap`.
    Il registro e' sostituito da una lista — quello vero sta nella cartella dati
    del pilota, e un test non ci scrive.
    """
    from accoach import engine as engine_mod
    from accoach.engineer import ledger

    scritti = []
    monkeypatch.setattr(ledger, "append", lambda rec, path=None: scritti.append(rec))
    coda = []
    monkeypatch.setattr(engine_mod, "build_lap_stats",
                        lambda lap, *a, **kw: coda.pop(0))

    eng = CoachEngine(reader=_Dead(), laps_dir=tmp_path, engineer_voice=False)
    eng._engineer = RaceEngineer(GT3_PROFILE, min_stable=3)

    def giro(stats=None):
        coda.append(stats or _lap())
        eng._observe_lap(synth.build_lap())
        return eng._engineer_block()

    for _ in range(8):
        if giro()["kind"] == "propose":
            break
    eng.mark_setup_applied()
    eng.tick(0.0)
    blocco = None
    for _ in range(3):
        blocco = giro(_lap(time_ms=101000))
    assert blocco["kind"] == "reverted" and blocco["tag"] == "BOX"
    eng.giro, eng.scritti, eng.ripristino = giro, scritti, blocco
    yield eng
    eng.close()


def test_the_page_is_still_told_to_restore_after_the_lap_that_follows(motore):
    """Quello che il pilota vede: fino al 13/10 al giro dopo il blocco diceva
    «servono 3 giri puliti, ne ho 1» e il ripristino non era piu' da nessuna
    parte."""
    for _ in range(5):
        blocco = motore.giro()
        assert blocco["kind"] == "reverted"
        assert blocco["change"] == motore.ripristino["change"]
        assert blocco["applied"] is False
        assert blocco["outcome"] == motore.ripristino["outcome"]


def test_the_driver_keeps_being_called_in_for_it(motore):
    """La chiamata ai box legge la decisione corrente: sparita quella, spariva
    anche l'unica voce che mandava il pilota a rimettere l'assetto."""
    # Guardato a OGNI giro e insieme a cosa c'e' da fare: al terzo, prima della
    # cura, la chiamata tornava — ma per il rimedio nuovo, quello sbagliato.
    for _ in range(4):
        blocco = motore.giro()
        assert motore._garage_change_pending()
        assert blocco["change"] == motore.ripristino["change"]


def test_one_rejected_test_is_one_line_in_the_record(motore):
    """Il verdetto si ripete sullo schermo, non nel registro: una prova e' una
    riga. Altrimenti ogni giro d'attesa conterebbe come un'altra bocciatura, e
    la riuscita dell'Ingegnere scenderebbe perche' il pilota ha fatto benzina."""
    assert len(motore.scritti) == 1 and motore.scritti[0].kept is False
    for _ in range(5):
        motore.giro()
    assert len(motore.scritti) == 1


def test_the_confirmation_from_the_page_is_what_lets_it_go(motore):
    """`POST /engineer/applied` arriva qui come `mark_setup_applied`. Il blocco
    dice subito «fatto» (smette di chiamare ai box) e dal giro dopo si torna a
    raccogliere giri, sull'assetto ripristinato."""
    motore.giro()
    motore.mark_setup_applied()
    motore.tick(0.0)
    assert motore._engineer_block()["applied"] is True
    assert not motore._garage_change_pending()
    assert motore.giro()["kind"] == "collect"


# --- la pagina ---------------------------------------------------------------
# Non si legge `engineer.js` cercando una stringa: si esegue la `renderEngineer`
# vera, con un DOM finto, e si guarda cosa lascia sullo schermo. Una ricerca nel
# testo avrebbe approvato anche `kind === "reverted"` scritto nel ramo sbagliato.

_NODE = shutil.which("node")

_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function grab(name) {
  const i = src.indexOf("function " + name + "(");
  if (i < 0) return "";
  let depth = 0;
  for (let k = src.indexOf("{", i); k < src.length; k++) {
    if (src[k] === "{") depth++;
    if (src[k] === "}") { depth--; if (!depth) return src.slice(i, k + 1); }
  }
}
const els = {};
// Ogni elemento nasce VISIBILE: quello che il test trova nascosto l'ha nascosto
// la pagina, non il DOM finto.
const $ = (id) => els[id] || (els[id] = {
  id, hidden: false, textContent: "", innerHTML: "", dataset: {}, onclick: null,
  classList: { add() {}, remove() {}, toggle() {} }, removeAttribute() {} });
const t = (k) => k;
const WS_PORT = 8777, location = { hostname: "h" };
// La porta verso il motore vera: senza lankey.js lascia l'URL com'e'.
const window = {};
eval(src.split("\n").find((l) => l.startsWith("const liveUrl = ")).replace(/^const /, "var "));
let prepared = null, posted = [];
function renderPrediction() {} function renderOutcome() {} function renderRoad() {}
function prepareChange(c) { prepared = c; }
function fetch(url, opt) { posted.push([url, opt && opt.method]); return Promise.resolve(); }
// Nessun frame dal vivo: si scrive come sempre (la guardia sta in `inPista`).
const state = { lastLive: null };
eval(grab("inPista")); eval(grab("writeLocked"));
eval(grab("msgText"));
eval(grab("confirmRestored"));
eval(grab("renderEngineer"));
const out = [];
for (const eng of JSON.parse(fs.readFileSync(0, "utf8"))) {
  for (const k in els) delete els[k];
  prepared = null; posted = [];
  renderEngineer({ connected: true, engineer: eng });
  const row = { prepareHidden: $("es-prepare").hidden,
                doneHidden: $("es-restored").hidden,
                msg: $("es-msg").textContent, cat: $("es-cat").textContent,
                confHidden: $("es-conf").hidden };
  if ($("es-prepare").onclick) $("es-prepare").onclick();
  row.prepared = prepared;
  if ($("es-restored").onclick) $("es-restored").onclick();
  row.posted = posted;
  out.push(row);
}
console.log(JSON.stringify(out));
"""

_RIPRISTINO = [{"param": "rearWing", "slot": None, "delta_clicks": 1}]


def _blocco(kind, **kw):
    base = {"kind": kind, "message": "il verdetto", "change": None,
            "rationale": None, "tag": None, "applied": False, "watched": False,
            "confidence": "", "phase": None}
    base.update(kw)
    return base


def _render(tmp_path, *blocchi):
    script = tmp_path / "harness.js"
    script.write_text(_HARNESS, encoding="utf-8")
    run = subprocess.run(
        [_NODE, str(script), str(_WEB / "engineer.js")],
        input=json.dumps(blocchi), capture_output=True, text=True,
        encoding="utf-8", timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


pagina = pytest.mark.skipif(_NODE is None, reason="serve node per eseguire la pagina")


@pagina
def test_a_restore_can_be_prepared_in_the_editor_like_a_proposal(tmp_path):
    """Il bottone c'era solo per `propose`. Per un ripristino porta nell'editor
    i click del ripristino — quelli del blocco, non altri."""
    (r,) = _render(tmp_path, _blocco(
        "reverted", change=_RIPRISTINO, tag="BOX",
        rationale="Ripristino: ala posteriore giu' di un click"))
    assert r["prepareHidden"] is False
    assert r["prepared"] == _RIPRISTINO
    # Il perche' e il cosa, tutti e due: il verdetto e la riga del ripristino.
    assert r["msg"] == "il verdetto"
    assert "Ripristino" in r["cat"]
    # Un ripristino non ha un grado di fiducia: il badge «medium» sarebbe una
    # proprieta' inventata.
    assert r["confHidden"] is True


@pagina
def test_a_restore_made_in_the_garage_can_be_declared_from_the_page(tmp_path):
    """Il modo piu' naturale di ripristinare e' ricaricare in gioco il file di
    prima — e allora la pagina non scrive niente e nessuno avvisa il motore, che
    adesso aspetta davvero. Senza questo bottone l'attesa sarebbe una trappola."""
    (r,) = _render(tmp_path, _blocco("reverted", change=_RIPRISTINO, tag="BOX"))
    assert r["doneHidden"] is False
    assert r["posted"] == [["http://h:8777/engineer/applied", "POST"]]


@pagina
def test_a_restore_already_confirmed_asks_for_nothing_more(tmp_path):
    """Il blocco resta REVERTED fino al giro dopo anche a ripristino fatto: i
    due bottoni li' sarebbero un invito a ripristinare due volte."""
    (r,) = _render(tmp_path, _blocco(
        "reverted", change=_RIPRISTINO, tag="BOX", applied=True))
    assert r["prepareHidden"] is True and r["doneHidden"] is True
    assert r["msg"] == "il verdetto"


@pagina
def test_the_other_kinds_are_left_as_they_were(tmp_path):
    """Il controllo: la proposta tiene il suo bottone e non guadagna quello del
    ripristino; un messaggio senza modifica non ne ha nessuno; e un ripristino
    «al volo» non passa dall'editor (ha il suo riquadro)."""
    proposta, raccolta, al_volo = _render(
        tmp_path,
        _blocco("propose", change=_RIPRISTINO, tag="BOX", rationale="ala giu'",
                confidence="high"),
        _blocco("collect"),
        _blocco("reverted", change=_RIPRISTINO, tag="AV"))
    assert proposta["prepareHidden"] is False and proposta["doneHidden"] is True
    assert proposta["msg"] == "ala giu'" and proposta["confHidden"] is False
    assert raccolta["prepareHidden"] is True and raccolta["doneHidden"] is True
    assert al_volo["prepareHidden"] is True and al_volo["doneHidden"] is True


def test_the_button_exists_and_starts_hidden_in_both_languages():
    html = (_WEB / "engineer.html").read_text(encoding="utf-8")
    i18n = (_WEB / "i18n.js").read_text(encoding="utf-8")
    import re
    tag = re.search(r'<button id="es-restored"[^>]*>', html)
    assert tag and "hidden" in tag.group(0)
    assert 'data-i18n="eng.restoredByHand"' in tag.group(0)
    voce = i18n[i18n.index('"eng.restoredByHand"'):]
    voce = voce[:voce.index("}")]
    assert "en:" in voce and "it:" in voce
