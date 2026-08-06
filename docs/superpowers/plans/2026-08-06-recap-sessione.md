# Recap della sessione — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** una scheda «Com'è andata» che, aperto il report, dice in tre secondi dove sono finiti i secondi di quell'uscita — in decimi misurati che sommano al gap, non in un voto.

**Architettura:** una funzione pura taglia ogni giro in tratti che *condividono gli estremi* (traguardo → entrata → apice− → apice+ → uscita → entrata successiva → … → fine giro) e ne misura il ritardo agli indici di taglio: le differenze telescopiano esatte. Una seconda funzione pura media quei tagli sui giri validi di una sessione, contro il miglior giro della sessione stessa. `/api/sessions` porta il blocco; il frontend disegna la scheda e diventa quella d'ingresso.

**Tech Stack:** Python 3.11+ (dataclass, bisect, pytest), FastAPI (`/api/sessions`), JS ES5-ish senza toolchain (`web/app.js`, `web/i18n.js`), CSS con le variabili di `:root`.

**Spec:** `docs/superpowers/specs/2026-08-06-recap-sessione-design.md`

## Global Constraints

- **Niente voto, niente scala tarata.** Le famiglie portano decimi misurati. L'unica cosa che si sceglie è l'ordine di disegno.
- **La somma torna, ed è la promessa centrale.** `entrata + apice + uscita + dopo + lancio = gap`, esatto, con gli estremi condivisi. Un test lo pinna con tolleranza da arrotondamento (0,1 ms), non con un `approx` largo.
- **Il filtro del debrief non si tocca.** `build_lap_debrief` continua a scartare le curve prese bene: risponde a un'altra domanda. Se un test di `tests/test_debrief.py` cambia, la modifica è sbagliata.
- **La voce non cambia.** Nessun cue nuovo, tolto o spostato. Questo lavoro non tocca il percorso del coaching dal vivo.
- **Assente, non un trattino.** Una sessione senza abbastanza dati non produce un blocco: `null`, e la scheda scrive perché. Mai uno zero al posto di un dato che non c'è.
- **Un solo modo di chiamare le curve:** i nomi vengono da `trackdata.name_corners` con la mappa imparata, come ogni altra vista.
- **Segno:** nel payload **positivo = tempo perso** (come `lost_ms` ovunque). Il frontend gira il segno per il pilota (`−1.18s`), in un posto solo.
- **Lingua:** commenti e docstring seguono la convenzione del file toccato — `phases.py` e `trends.py` sono **in inglese**, `api.py` è inglese con l'italiano solo dove si registra una lezione. Le stringhe a schermo passano da `i18n.js` in **entrambe** le lingue.
- **Suite:** `python -m pytest -q` è verde a **1774** su `main`. Deve restare verde.

---

## Struttura dei file

| File | Cosa cambia | Perché lì |
|---|---|---|
| `src/accoach/coaching/phases.py` | + `CornerSplit`, `LapSplit`, `lap_time_split()` | è già il modulo che sa tagliare una curva in quattro; qui il taglio si estende al giro intero |
| `src/accoach/coaching/trends.py` | + `SessionRecap`, `session_recap()` | è già il modulo dell'analisi fra più giri (`classify_losses`, `session_series`) |
| `src/accoach/api.py` | blocco `recap` in `/api/sessions` | la sessione è già selezionata lì; una seconda selezione sarebbe una seconda definizione di «quale uscita» |
| `src/accoach/web/index.html` | + vista `#view-recap`, + scheda, ordine delle schede | |
| `src/accoach/web/app.js` | + `renderRecap()`, vista d'ingresso | |
| `src/accoach/web/i18n.js`, `style.css` | chiavi e stile della scheda | |
| `GUIDA.md` | cosa misura e contro cosa | è dove il pilota legge |

---

### Task 1: Il taglio del giro, con gli estremi condivisi

**Files:**
- Modify: `src/accoach/coaching/phases.py` (in fondo, dopo `phase_note`)
- Test: `tests/test_phases.py`

**Interfaces:**
- Consumes: `PHASES`, `_APEX_HALF` (già importato in `phases.py`), `Reference.time_at`, `Corner`
- Produces:
  - `CornerSplit(index: int, lost_ms: float, phases: list[PhaseLoss])`
  - `LapSplit(launch_ms: float, corners: list[CornerSplit], gap_ms: float)` con `by_phase() -> dict[str, float]`
  - `lap_time_split(lap, reference, corners) -> LapSplit | None`

- [ ] **Step 1: Scrivi i test che falliscono**

In fondo a `tests/test_phases.py`. Le helper del file esistono già: guardale e riusale invece di scriverne altre.

```python
# --- il taglio del giro intero ---------------------------------------------

from accoach.coaching.phases import lap_time_split          # in cima, coi suoi
from accoach.comparison import Reference
from accoach.track import detect_corners

import synth


def _split(review=None):
    ref_lap = synth.build_lap()
    reference = Reference(ref_lap)
    corners = detect_corners(ref_lap.samples)
    return lap_time_split(review or synth.build_lap(), reference, corners), corners


def test_the_parts_add_back_up_to_the_gap_exactly():
    """La promessa centrale: se questa somma non torna, la scheda mente."""
    split, _ = _split(synth.build_lap(slow_corner=0, amt=30))
    total = split.launch_ms + sum(c.lost_ms for c in split.corners)
    assert abs(total - split.gap_ms) < 0.1          # solo arrotondamento


def test_each_corner_is_the_sum_of_its_four_phases():
    split, _ = _split(synth.build_lap(slow_corner=0, amt=30))
    for c in split.corners:
        assert abs(sum(p.lost_ms for p in c.phases) - c.lost_ms) < 0.1


def test_every_corner_is_there_even_the_ones_taken_well():
    """Il caso che il debrief scarta: senza queste, la somma non tornerebbe."""
    split, corners = _split()
    assert len(split.corners) == len(corners)
    assert [c.index for c in split.corners] == [c.index for c in corners]


def test_a_phase_you_were_quicker_in_reads_negative():
    split, _ = _split(synth.build_lap(slow_corner=0, amt=30))
    values = [p.lost_ms for c in split.corners for p in c.phases]
    assert any(v < 0 for v in values), "un giro diverso guadagna da qualche parte"


def test_the_launch_is_the_stretch_before_the_first_corner():
    split, corners = _split()
    first = min(c.entry_pos for c in corners)
    assert first > 0.0                      # c'è davvero un tratto scoperto
    assert isinstance(split.launch_ms, float)


def test_by_phase_totals_the_same_number():
    split, _ = _split(synth.build_lap(slow_corner=0, amt=30))
    by = split.by_phase()
    assert set(by) == {"entry", "apex", "exit", "after"}
    assert abs(sum(by.values()) + split.launch_ms - split.gap_ms) < 0.1


def test_the_gap_is_close_to_lap_time_minus_reference():
    """Non identico: primo e ultimo campione non cadono sul traguardo. Il test
    misura quella differenza invece di assumerla."""
    review = synth.build_lap(slow_corner=0, amt=30)
    ref_lap = synth.build_lap()
    split = lap_time_split(review, Reference(ref_lap), detect_corners(ref_lap.samples))
    published = review.lap_time_ms - ref_lap.lap_time_ms
    assert abs(split.gap_ms - published) < 50.0


def test_no_corners_no_split():
    ref_lap = synth.build_lap()
    assert lap_time_split(synth.build_lap(), Reference(ref_lap), []) is None
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_phases.py -q -k "split or launch or phase_totals"`
Expected: FAIL con `ImportError: cannot import name 'lap_time_split'`

- [ ] **Step 3: Implementa**

In fondo a `src/accoach/coaching/phases.py`:

```python
@dataclass(slots=True)
class CornerSplit:
    """One corner's loss and the four stretches it is made of."""

    index: int
    lost_ms: float
    phases: list[PhaseLoss]


@dataclass(slots=True)
class LapSplit:
    """Where a whole lap's gap went, in parts that add back up to it."""

    launch_ms: float                 # start line to the first braking zone
    corners: list[CornerSplit]
    gap_ms: float                    # delta at the last sample minus the first

    def by_phase(self) -> dict[str, float]:
        """Totals per phase across every corner of the lap."""
        out = {p: 0.0 for p in PHASES}
        for c in self.corners:
            for p in c.phases:
                out[p.phase] += p.lost_ms
        return {k: round(v, 1) for k, v in out.items()}


def lap_time_split(lap, reference, corners) -> LapSplit | None:
    """Cut a whole lap into stretches whose losses add back up to its gap.

    The debrief measures a corner over ``entry <= pos < next entry``, so two
    consecutive windows do NOT share a sample: telescoping across them leaves
    one sampling interval out per corner. Close enough to look right and not
    close enough to be true, which is the worst kind of number.

    So the cuts are computed once for the whole lap — start, then entry /
    apex- / apex+ / exit for every corner, then the lap's end — mapped to
    sample indices that only ever move forward, and every stretch ENDS on the
    index the next one STARTS from. Then the sum telescopes to
    ``delta(last) - delta(first)`` by construction, and that is what ``gap_ms``
    is: measured the same way as its own parts, not borrowed from the lap time.

    Unlike the debrief this keeps **every** corner, including the ones taken
    well. A corner that cost nothing contributes 0.0 — leaving it out is what
    would make the sum stop adding up.
    """
    samples = lap.samples
    if len(samples) < 4 or not corners:
        return None
    positions = [s.pos for s in samples]
    ordered = sorted(corners, key=lambda c: (c.entry_pos, c.exit_pos, c.apex_pos))

    cuts = [positions[0]]
    for c in ordered:
        cuts += [c.entry_pos, c.apex_pos - _APEX_HALF,
                 c.apex_pos + _APEX_HALF, c.exit_pos]
    cuts.append(positions[-1])

    edges: list[int] = []
    for p in cuts:
        p = min(max(p, positions[0]), positions[-1])
        i = min(len(samples) - 1, max(0, bisect.bisect_left(positions, p)))
        edges.append(i if not edges else max(i, edges[-1]))

    delta = [samples[i].t_ms - reference.time_at(samples[i].pos) for i in edges]

    out: list[CornerSplit] = []
    for k, c in enumerate(ordered):
        base = 1 + 4 * k                     # entry / apex- / apex+ / exit
        # "after" runs to the NEXT corner's entry, or to the lap's end for the
        # last one — the same rule the debrief uses, so a poor exit is charged
        # to the corner that caused it.
        end = base + 4 if k + 1 < len(ordered) else len(edges) - 1
        bounds = [base, base + 1, base + 2, base + 3, end]
        phases = [PhaseLoss(phase=name,
                            lost_ms=round(delta[b] - delta[a], 1))
                  for name, a, b in zip(PHASES, bounds, bounds[1:])]
        out.append(CornerSplit(index=c.index,
                               lost_ms=round(delta[end] - delta[base], 1),
                               phases=phases))

    return LapSplit(launch_ms=round(delta[1] - delta[0], 1),
                    corners=out,
                    gap_ms=round(delta[-1] - delta[0], 1))
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_phases.py tests/test_debrief.py -q`
Expected: PASS — `test_debrief.py` intatto è la prova che il filtro del debrief non è stato toccato

- [ ] **Step 5: Misura il costo, non stimarlo**

Scrivi uno script usa-e-getta nello scratchpad che carica i giri veri di una combinazione dal catalogo (`accoach.recording.laps_root()`), costruisce il riferimento dal più veloce e cronometra `lap_time_split` su ognuno. Riporta i **ms per giro** nel report: lo spec dice che deve costare una frazione dei 7,4 ms di un debrief, e quel numero va verificato, non ripetuto.

- [ ] **Step 6: Commit**

```bash
git add src/accoach/coaching/phases.py tests/test_phases.py
git commit -m "Il giro tagliato in parti che tornano: gli estremi si condividono"
```

---

### Task 2: Il recap di una sessione

**Files:**
- Modify: `src/accoach/coaching/trends.py` (in fondo)
- Test: `tests/test_trends.py`

**Interfaces:**
- Consumes: `lap_time_split`, `LapSplit` (Task 1)
- Produces:
  - `RecapLap(lap_time_ms: int, gap_ms: float, worst_index: int, worst_ms: float)`
  - `SessionRecap(gain_avg_ms: float, by_phase: dict[str, float], launch_ms: float, laps: list[RecapLap], reference_ms: int)`
  - `session_recap(laps, reference, corners) -> SessionRecap | None`

`laps` sono gli oggetti `Lap` **validi** della sessione, riferimento **escluso**; `reference` è il `Reference` costruito sul miglior giro di quella sessione. La funzione è pura: nessun I/O, nessun catalogo.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# --- il recap di una sessione ----------------------------------------------

from accoach.coaching.trends import session_recap          # in cima, coi suoi
from accoach.comparison import Reference
from accoach.track import detect_corners

import synth


def _recap(amts):
    ref_lap = synth.build_lap()
    corners = detect_corners(ref_lap.samples)
    laps = [synth.build_lap(slow_corner=0, amt=a) for a in amts]
    return session_recap(laps, Reference(ref_lap), corners)


def test_the_families_add_up_to_the_average_gap():
    r = _recap([10, 20, 30])
    total = sum(r.by_phase.values()) + r.launch_ms
    assert abs(total - r.gain_avg_ms) < 0.5     # media di somme esatte


def test_one_row_per_lap_with_its_worst_corner():
    r = _recap([10, 20, 30])
    assert len(r.laps) == 3
    assert all(l.worst_index >= 0 for l in r.laps)
    assert r.laps[2].gap_ms > r.laps[0].gap_ms  # amt=30 perde più di amt=10


def test_the_worst_corner_is_the_one_that_cost_most():
    r = _recap([30])
    assert r.laps[0].worst_index == 0           # synth rallenta la curva 0


def test_no_laps_no_recap():
    ref_lap = synth.build_lap()
    assert session_recap([], Reference(ref_lap),
                         detect_corners(ref_lap.samples)) is None


def test_a_lap_the_split_cannot_read_is_skipped_not_faked():
    """Un giro senza abbastanza campioni non entra: meglio due righe vere che
    tre con una inventata."""
    ref_lap = synth.build_lap()
    corners = detect_corners(ref_lap.samples)
    short = synth.build_lap()
    short.samples = short.samples[:2]
    r = session_recap([synth.build_lap(slow_corner=0, amt=20), short],
                      Reference(ref_lap), corners)
    assert len(r.laps) == 1
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_trends.py -q -k recap`
Expected: FAIL con `ImportError: cannot import name 'session_recap'`

- [ ] **Step 3: Implementa**

In fondo a `src/accoach/coaching/trends.py`:

```python
@dataclass(slots=True)
class RecapLap:
    """One lap of the run, as the recap shows it."""

    lap_time_ms: int
    gap_ms: float
    worst_index: int          # -1 when no corner cost anything
    worst_ms: float


@dataclass(slots=True)
class SessionRecap:
    """Where a run's time went, averaged over its laps."""

    gain_avg_ms: float                 # average gap to the run's own best lap
    by_phase: dict[str, float]         # entry / apex / exit / after, averaged
    launch_ms: float                   # start line to the first braking zone
    laps: list[RecapLap]
    reference_ms: int                  # the run's best lap, the yardstick


def session_recap(laps, reference, corners) -> SessionRecap | None:
    """How a run went, measured against its own best lap.

    The yardstick is deliberately the best lap of THIS run, not the reference
    elected for the conditions: the question is "how much was I leaving out
    there today", and a lap from a colder evening would answer it with weather.
    The best lap itself is not in ``laps`` — it would be a row of zeros.

    Returns None when nothing can be measured. A lap the split cannot read is
    dropped rather than counted as a zero: a row that says "no time lost here"
    where we simply could not look is the easiest lie on the screen.
    """
    from .phases import lap_time_split

    splits = [(lap, s) for lap in laps
              if (s := lap_time_split(lap, reference, corners)) is not None]
    if not splits:
        return None

    n = len(splits)
    by_phase = {p: 0.0 for p in PHASES}
    launch = 0.0
    rows: list[RecapLap] = []
    for lap, s in splits:
        for phase, value in s.by_phase().items():
            by_phase[phase] += value
        launch += s.launch_ms
        worst = max(s.corners, key=lambda c: c.lost_ms, default=None)
        rows.append(RecapLap(
            lap_time_ms=lap.lap_time_ms,
            gap_ms=s.gap_ms,
            worst_index=worst.index if worst and worst.lost_ms > 0 else -1,
            worst_ms=round(worst.lost_ms, 1) if worst and worst.lost_ms > 0 else 0.0,
        ))

    return SessionRecap(
        gain_avg_ms=round(sum(r.gap_ms for r in rows) / n, 1),
        by_phase={k: round(v / n, 1) for k, v in by_phase.items()},
        launch_ms=round(launch / n, 1),
        laps=rows,
        reference_ms=reference.lap_time_ms,
    )
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_trends.py tests/test_phases.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/accoach/coaching/trends.py tests/test_trends.py
git commit -m "Il recap di un'uscita: contro il tuo miglior giro di oggi"
```

---

### Task 3: `/api/sessions` porta il recap

**Files:**
- Modify: `src/accoach/api.py` (funzione `sessions`, righe ~1502-1580)
- Test: `tests/test_api_recap.py` (nuovo)

**Interfaces:**
- Consumes: `session_recap` (Task 2)
- Produces: chiave `recap` dentro `current`, oppure `null`

```json
"recap": {
  "gain_avg_s": 2.41,
  "reference": "1:53.712",
  "phases": [{"phase": "entry", "avg_s": 1.18}, {"phase": "apex", "avg_s": 0.62},
             {"phase": "exit", "avg_s": 0.41}, {"phase": "after", "avg_s": 0.20},
             {"phase": "launch", "avg_s": 0.00}],
  "laps": [{"path": "…", "lap_time": "1:55.204", "gap_s": 1.49,
            "corner_index": 3, "corner": "Curva Grande", "corner_s": 0.62}]
}
```

Positivo = perso, in secondi con tre decimali. `"launch"` è l'ultima riga di `phases` e non è una fase di guida: si chiama così, e non «altro», perché «altro» è dove si nascondono gli errori.

- [ ] **Step 1: Scrivi i test che falliscono**

Nuovo file `tests/test_api_recap.py`, sul modello di `tests/test_api_sessions.py` (leggilo prima: ha già le helper per salvare giri datati).

```python
"""/api/sessions: il recap di un'uscita, e cosa dice quando non può dire niente."""
from fastapi.testclient import TestClient

from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

CAR, TRACK = "ferrari_488_gt3", "monza"


def _lap(tmp_path, when, *, amt=0):
    lap = synth.build_lap(slow_corner=0, amt=amt) if amt else synth.build_lap()
    lap.recorded_utc = when
    save_lap(lap, tmp_path)


def _get(tmp_path, **kw):
    c = TestClient(create_api(tmp_path))
    return c.get("/api/sessions", params={"car": CAR, "track": TRACK, **kw}).json()


def test_the_key_is_always_there(tmp_path):
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")
    assert "recap" in _get(tmp_path)["current"]


def test_the_families_add_up_to_the_average(tmp_path):
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")            # il migliore
    _lap(tmp_path, "2026-08-01T18:02:00+00:00", amt=20)
    _lap(tmp_path, "2026-08-01T18:04:00+00:00", amt=30)
    r = _get(tmp_path)["current"]["recap"]
    assert r is not None
    total = sum(p["avg_s"] for p in r["phases"])
    assert abs(total - r["gain_avg_s"]) < 0.01
    assert [p["phase"] for p in r["phases"]] == \
        ["entry", "apex", "exit", "after", "launch"]


def test_every_lap_but_the_best_has_a_row_with_a_named_corner(tmp_path):
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")
    _lap(tmp_path, "2026-08-01T18:02:00+00:00", amt=20)
    _lap(tmp_path, "2026-08-01T18:04:00+00:00", amt=30)
    r = _get(tmp_path)["current"]["recap"]
    assert len(r["laps"]) == 2                    # il migliore è il metro
    assert all(l["corner"] for l in r["laps"])    # un nome c'è sempre


def test_a_single_lap_run_has_no_recap_not_a_zero(tmp_path):
    """Il migliore è l'unico: non c'è un gap da mostrare, e non se ne inventa uno."""
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")
    assert _get(tmp_path)["current"]["recap"] is None


def test_an_older_session_can_be_asked_for(tmp_path):
    _lap(tmp_path, "2026-07-20T18:00:00+00:00")
    _lap(tmp_path, "2026-07-20T18:02:00+00:00", amt=20)
    _lap(tmp_path, "2026-08-01T18:00:00+00:00")
    assert _get(tmp_path, index=1)["current"]["recap"] is not None
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_api_recap.py -q`
Expected: FAIL con `KeyError: 'recap'`

- [ ] **Step 3: Implementa**

In `src/accoach/api.py`, helper vicino a `_corner_moves` (che è già il vicino di casa: carica due giri e li confronta):

```python
    def _recap_of(cur, track: str, lg: str) -> dict | None:
        """The run's recap, or None when there is nothing measurable in it."""
        best = cur.best
        if best is None:
            return None
        others = [l for l in cur.valid_laps if l["path"] != best["path"]]
        if not others:
            return None                     # the best lap is the only lap
        try:
            best_lap = load_lap(best["path"])
            reference = Reference(best_lap)
            if not reference.usable:
                return None
            corners = detect_corners(best_lap.samples)
            names = {c.index: n for c, n in
                     zip(corners, name_corners(track, corners, lg,
                                               _corner_map(cur_car, track),
                                               _typed(track)))}
            laps = []
            for row in others:
                try:
                    laps.append(load_lap(row["path"]))
                except (OSError, ValueError):
                    continue
            recap = session_recap(laps, reference, corners)
        except (OSError, ValueError):
            return None
        if recap is None:
            return None
        return {
            "gain_avg_s": round(recap.gain_avg_ms / 1000.0, 3),
            "reference": format_lap_time(recap.reference_ms),
            "phases": [{"phase": p, "avg_s": round(recap.by_phase[p] / 1000.0, 3)}
                       for p in PHASES]
                      + [{"phase": "launch",
                          "avg_s": round(recap.launch_ms / 1000.0, 3)}],
            "laps": [{
                "path": row["path"],
                "lap_time": format_lap_time(r.lap_time_ms),
                "gap_s": round(r.gap_ms / 1000.0, 3),
                "corner_index": r.worst_index,
                "corner": names.get(r.worst_index, ""),
                "corner_s": round(r.worst_ms / 1000.0, 3),
            } for row, r in zip(others, recap.laps)],
        }
```

> **Attenzione, e va risolta scrivendo il codice, non ignorata:** `zip(others, recap.laps)` presuppone che `session_recap` abbia tenuto **tutti** i giri passati. Non è garantito: la funzione scarta i giri che non riesce a tagliare. Fai in modo che l'accoppiamento sia esplicito — per esempio facendo tornare a `session_recap` anche l'indice del giro, oppure filtrando `others` con lo stesso criterio prima di chiamarla. Un `zip` che si disallinea silenziosamente attribuisce il gap di un giro a un altro, ed è esattamente il tipo di difetto che nessun test di somma prende.

Nel `return` di `sessions`, dentro `current`, aggiungi `"recap": _recap_of(cur, track, lg),`. Serve anche il modello dell'auto per `_corner_map`: prendilo dal parametro `car` della richiesta.

Import da aggiungere in cima: `session_recap` da `.coaching.trends`, `PHASES` da `.coaching.phases` (`Reference`, `detect_corners`, `load_lap`, `name_corners`, `format_lap_time` ci sono già).

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_api_recap.py tests/test_api_sessions.py tests/test_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/accoach/api.py tests/test_api_recap.py
git commit -m "Il recap nel payload della sessione"
```

---

### Task 4: La scheda «Com'è andata», e diventa la porta

**Files:**
- Modify: `src/accoach/web/index.html`, `app.js`, `i18n.js`, `style.css`
- Test: `tests/test_web_views.py`

**Interfaces:**
- Consumes: `current.recap` (Task 3)

- [ ] **Step 1: Scrivi i test che falliscono**

In `tests/test_web_views.py` (leggi come il file già asserisce: c'è una helper che sa dire in quale vista sta un id, usala):

```python
def test_the_recap_has_a_home_and_it_is_the_landing_view():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="view-recap"' in html
    assert 'data-view="recap"' in html
    # la vista d'ingresso è l'unica senza `hidden`
    assert 'id="view-recap" class="hidden"' not in html
    assert 'id="view-flow" class="hidden"' in html


def test_the_recap_is_rendered_when_the_session_loads():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "renderRecap(" in js
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_web_views.py -q -k recap`
Expected: FAIL

- [ ] **Step 3: Implementa — HTML**

Nuova vista **prima** di `#view-flow`, e `#view-flow` prende `class="hidden"`:

```html
  <div id="view-recap">
    <section id="recap-head" class="summary"></section>
    <section class="debrief">
      <h3 data-i18n-html="recap.where">Where the time went <small>(average per lap · the parts add up to the gap)</small></h3>
      <div id="recap-phases"></div>
    </section>
    <section class="debrief">
      <h3 data-i18n-html="recap.laps">Lap by lap <small>(against your best lap of this run)</small></h3>
      <div id="recap-laps"></div>
    </section>
  </div>
```

Nella barra delle schede, **come prima voce**:

```html
    <button class="tab" data-view="recap" data-i18n="tab.recap">How it went</button>
```

- [ ] **Step 4: Implementa — i18n**

Chiavi nuove in `src/accoach/web/i18n.js`, in **entrambe** le lingue (`tests/test_web_i18n_keys.py` lo verifica e deve restare verde):

```js
    "tab.recap":       { en: `How it went`, it: `Com'è andata` },
    "recap.where":     { en: `Where the time went <small>(average per lap · the parts add up to the gap)</small>`,
                         it: `Dove è finito il tempo <small>(media per giro · le parti sommano al gap)</small>` },
    "recap.laps":      { en: `Lap by lap <small>(against your best lap of this run)</small>`,
                         it: `Giro per giro <small>(contro il tuo miglior giro di questa uscita)</small>` },
    "recap.best":      { en: `Best lap of this run`, it: `Miglior giro di questa uscita` },
    "recap.gain":      { en: `To gain, on average`, it: `Da guadagnare, in media` },
    "recap.yardstick": { en: `your yardstick`, it: `il tuo metro` },
    "recap.none":      { en: `One valid lap in this run — nothing to compare it against yet.`,
                         it: `Un solo giro valido in questa uscita: non c'è ancora niente contro cui confrontarlo.` },
    "recap.phase.entry":  { en: `Entry`, it: `Entrata` },
    "recap.phase.apex":   { en: `Apex`, it: `Apice` },
    "recap.phase.exit":   { en: `Exit`, it: `Uscita` },
    "recap.phase.after":  { en: `After`, it: `Dopo` },
    "recap.phase.launch": { en: `Launch`, it: `Lancio` },
```

- [ ] **Step 5: Implementa — render**

In `app.js`, accanto agli altri renderer della sessione:

```js
// Dove è finito il tempo di un'uscita, in decimi che sommano al gap. Le barre
// sono in scala sulla fase peggiore di QUESTA sessione: non c'è nessuna soglia,
// e nessun colore che voglia dire "bravo".
function renderRecap(cur) {
  const head = $("recap-head"), ph = $("recap-phases"), lp = $("recap-laps");
  if (!head || !ph || !lp) return;
  const r = cur && cur.recap;
  if (!r) {
    head.innerHTML = "";
    ph.innerHTML = `<div class="clean">${t("recap.none")}</div>`;
    lp.innerHTML = "";
    return;
  }
  const item = (k, v) => `<div class="item"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  head.innerHTML = item(t("recap.best"), r.reference) +
                   item(t("recap.gain"), "+" + r.gain_avg_s.toFixed(3) + "s");

  let mx = 0.05;
  for (const p of r.phases) mx = Math.max(mx, p.avg_s);
  ph.innerHTML = r.phases.map((p) => {
    const w = (Math.min(Math.max(p.avg_s, 0) / mx, 1) * 100).toFixed(0);
    return `<div class="ses-row">` +
      `<span class="ses-when">${t("recap.phase." + p.phase)}</span>` +
      `<span class="ses-track"><span class="ses-fill" style="width:${w}%"></span></span>` +
      `<span class="ses-nums">${fmtLoss(p.avg_s)}</span></div>`;
  }).join("");

  lp.innerHTML = r.laps.map((l) =>
    `<div class="recap-lap" data-path="${l.path}">` +
    `<span class="lap-time">${l.lap_time}</span>` +
    `<span class="lap-gap">${fmtLoss(l.gap_s)}</span>` +
    `<span class="corner">${l.corner}</span></div>`).join("");
}

// Il segno dal punto di vista del pilota: perdere è meno tempo tuo. Meno
// tipografico, come il resto del report.
function fmtLoss(s) {
  return (s > 0 ? "−" : s < 0 ? "+" : "") + Math.abs(s).toFixed(3) + "s";
}
```

Chiama `renderRecap(j.current)` dove la sessione viene caricata (cerca la funzione che oggi disegna `#ses-numbers` e mettilo accanto, così una sola richiesta serve entrambe le schede), e svuota i tre contenitori nel ramo d'errore come fanno i pannelli vicini.

**Il clic su una riga giro** apre il Confronto con quel giro selezionato: guarda come `showView("compare")` viene già usato altrove e come si sceglie il giro da rivedere, e riusa quel meccanismo invece di inventarne uno.

- [ ] **Step 6: Implementa — CSS**

Le barre riusano le classi `.ses-row` / `.ses-track` / `.ses-fill` / `.ses-nums` già esistenti (e la loro media query stretta). Serve solo la riga giro:

```css
.recap-lap { display: grid; grid-template-columns: 96px 88px 1fr; align-items: center;
  gap: 12px; padding: 7px 12px; margin: 6px 0; background: var(--panel);
  border: 1px solid var(--line); border-radius: 10px; cursor: pointer; }
.recap-lap .lap-time { font-family: var(--font-mono); }
.recap-lap .lap-gap { font-family: var(--font-mono); color: var(--muted); }
.recap-lap .corner { font-weight: 600; }

@media (max-width: 640px) {
  .recap-lap { grid-template-columns: 1fr auto; }
  .recap-lap .corner { grid-column: 1 / -1; }
}
```

- [ ] **Step 7: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_web_views.py tests/test_web_i18n_keys.py tests/test_bundle_contents.py -q`
Expected: PASS

- [ ] **Step 8: Verifica a schermo**

Apri il report su una combinazione con più giri in una sessione. Controlla: la scheda si apre **per prima**; le cinque righe ci sono; **la somma delle fasi a schermo dà il numero grande**; un clic su un giro porta al Confronto; a larghezza stretta la pagina **non scorre di lato** (misuralo su `scrollWidth`, non a occhio); cambiando lingua non compare nessuna chiave non tradotta.

- [ ] **Step 9: Commit**

```bash
git add src/accoach/web/ tests/test_web_views.py
git commit -m "Com'è andata: la scheda che apre il report"
```

---

### Task 5: La guida

**Files:**
- Modify: `GUIDA.md` (§5, come prima sottosezione delle schede del report)
- Test: `tests/test_guide.py` (tienilo verde; se conta intestazioni o tabelle, aggiorna e dichiara)

- [ ] **Step 1: Scrivi la sezione**

In §5, prima delle altre schede, un `###` (non un `####`: `guide.py` non ha CSS per l'h4):

```markdown
### Com'è andata (la prima schermata)

Apri il report e la prima cosa che vedi è **l'ultima uscita**: quanto lasciavi
per strada in media, e dove.

Le cinque righe — **entrata, apice, uscita, dopo, lancio** — non sono un voto:
sono i **secondi** che quella parte del giro ti è costata, e **sommano al gap**.
Se le sommi a mano ti torna il numero grande in alto: è fatto apposta, ed è la
differenza fra un dato e una pagella.

Tre cose da sapere:

- **Il metro è il tuo miglior giro di quell'uscita**, non il tuo record. Quindi
  misura la **costanza** di quel pomeriggio: tutto verde non vuol dire che sei
  veloce, vuol dire che eri ripetibile. Ed è per questo che il tuo giro migliore
  compare senza gap: è lui il metro.
- **«Lancio» non è una fase di guida.** È il tratto dal traguardo alla prima
  staccata, che non appartiene a nessuna curva. Ha una riga sua perché senza di
  lui la somma non tornerebbe, e una somma che non torna è una somma che non
  puoi controllare.
- **Un'uscita con un solo giro valido non ha un recap**, e te lo dice: contro
  cosa dovrebbe confrontarlo?
```

- [ ] **Step 2: Verifica**

Run: `python -m pytest tests/test_guide.py tests/test_bundle_contents.py -q`
Expected: PASS. Apri anche `/guida` e guarda che la sezione si disegni.

- [ ] **Step 3: Commit**

```bash
git add GUIDA.md
git commit -m "La guida: cosa somma, contro cosa, e perché il tuo miglior giro è a zero"
```

---

## Chiusura

- [ ] **Suite intera verde**: `python -m pytest -q`
- [ ] **Verifica finale a schermo** su dati veri, con la somma controllata a mano
- [ ] **Chiudi il ramo** — REQUIRED SUB-SKILL: `superpowers:finishing-a-development-branch`
