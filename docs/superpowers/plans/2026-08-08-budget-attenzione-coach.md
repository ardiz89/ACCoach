# Budget di attenzione del coach vocale — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** quando il `FocusCoach` ha eletto una debolezza, il coach vocale in pista parla solo di
quel tema, con una parola-innesco invece di una frase.

**Architecture:** il filtro vive in `CueScheduler`, che è già il cancello fra ciò che si potrebbe
dire e ciò che si dice. Il tema attivo gli arriva dal `FocusCoach`, che lo elegge già oggi ma non lo
dice a nessuno. Il tema di una categoria si sposta in `cue.py`, dove vive la categoria, così
`scheduler.py` non deve importare `focus.py` (che tira dentro `debrief.py`: rischio di ciclo).

**Tech Stack:** Python 3.14, pytest, nessuna dipendenza nuova.

Spec: `docs/superpowers/specs/2026-08-08-budget-attenzione-coach-design.md`.

## Global Constraints

- Codice e commenti in inglese; **solo le stringhe rivolte al pilota** sono localizzate (it/en).
- Nessun numero inventato. La soppressione dei ripetuti resta `_DEFAULT_REPEAT_SUPPRESS_S = 20.0`.
- Il tema che viaggia fra i moduli è **la chiave inglese**, mai la stringa tradotta.
  `Focus.theme` è tradotta (`focus.py:131`): non usarla per confronti.
- Con `focus_theme = None` il comportamento dev'essere **identico a oggi**, byte per byte nei test
  esistenti. `tests/test_scheduler.py` (12 test) non va modificato: deve passare così com'è.
- Un consiglio fuori tema **non parla ma resta nel debrief**, che è calcolato dal giro e non sa cosa
  è stato pronunciato. Non toccare `debrief.py` se non per l'import spostato nel Task 1.
- Test con `pytest`; eseguire sempre la suite intera prima di un commit
  (`python -m pytest -q`), perché `_THEME` ha due lettori.

## Deviazione dalla spec, decisa in fase di piano

La spec prevedeva di spostare `_SAFETY_CATEGORIES` da `engine.py` a `cue.py` per definire «chi parla
sempre». **Non serve**: i livelli di urgenza esistenti dicono già la stessa cosa meglio. Il filtro si
applica **solo ai consigli di livello `TECHNIQUE`**; gli acuti (bloccaggio, pattinamento, sotto e
sovrasterzo, benzina, chiamate box) e gli avvisi (pressioni, temperature, aiuti) passano sempre,
perché non sono temi di guida da allenare. Una regola sola invece di un elenco da mantenere.

`engine.py:66-74` resta dov'è e non si tocca.

---

### Task 1: Il tema di una categoria si sposta in `cue.py` e diventa completo

**Files:**
- Modify: `src/accoach/coaching/cue.py` (in fondo, dopo `tier_of`)
- Modify: `src/accoach/coaching/focus.py:52-65` (rimuove `_THEME`/`_THEME_DEFAULT`, delega)
- Modify: `src/accoach/coaching/debrief.py:473-477` (importa da `cue`)
- Test: `tests/test_cue_theme.py` (nuovo)

**Interfaces:**
- Produces: `accoach.coaching.cue.THEME: dict[CueCategory, dict[str, str]]`,
  `accoach.coaching.cue.THEME_DEFAULT: dict[str, str]`,
  `accoach.coaching.cue.theme_key(cat: CueCategory) -> str` (chiave inglese),
  `accoach.coaching.cue.theme_label(cat: CueCategory, lang: str) -> str` (etichetta tradotta).

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_cue_theme.py`:

```python
"""Il tema di una categoria: chiave inglese per i confronti, etichetta per il pilota.

Il test di completezza esiste perche' questo progetto ha gia' preso questa famiglia
di difetti: una categoria con titolo, grafico ed esercizio e nessun produttore. Una
categoria di tecnica senza tema non verrebbe mai pronunciata con un focus attivo, e
il difetto sarebbe invisibile.
"""
from accoach.coaching.cue import (
    THEME, CueCategory, CueTier, theme_key, theme_label, tier_of,
)


def test_theme_key_is_english_regardless_of_language():
    assert theme_key(CueCategory.BRAKE_LATER) == "braking"
    assert theme_key(CueCategory.MORE_THROTTLE) == "traction"
    assert theme_key(CueCategory.CARRY_SPEED) == "cornering"
    assert theme_key(CueCategory.TIME_LOSS) == "line"


def test_theme_label_is_translated():
    assert theme_label(CueCategory.BRAKE_LATER, "it") == "frenata"
    assert theme_label(CueCategory.BRAKE_LATER, "en") == "braking"
    # Lingua sconosciuta: si ripiega sull'inglese, non si esplode.
    assert theme_label(CueCategory.BRAKE_LATER, "de") == "braking"


def test_every_technique_category_has_an_explicit_theme():
    """Fallisce quando si aggiunge una categoria di tecnica senza darle un tema."""
    missing = [
        c.name for c in CueCategory
        if tier_of(c) == CueTier.TECHNIQUE
        and c is not CueCategory.GOOD          # la lode non ha tema: vedi Task 3
        and c not in THEME
    ]
    assert not missing, f"categorie di tecnica senza tema in THEME: {missing}"


def test_every_theme_entry_has_both_languages():
    for cat, entry in THEME.items():
        assert entry.get("it"), f"{cat.name}: manca l'italiano"
        assert entry.get("en"), f"{cat.name}: manca l'inglese"
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_cue_theme.py -v`
Expected: FAIL con `ImportError: cannot import name 'THEME' from 'accoach.coaching.cue'`

- [ ] **Step 3: Implementa in `cue.py`**

Aggiungi in fondo a `src/accoach/coaching/cue.py`, dopo `tier_of`:

```python
# The theme a cue belongs to — the unit a coaching session is organised around.
# It lives here, next to the category, because two readers need it (the debrief
# headline and the voice gate) and a second copy would be free to disagree.
#
# The English key is the one that travels between modules; the localized label is
# only ever shown. A comparison that changed outcome with the interface language
# would be a defect invisible in Italian and visible only in English.
THEME: dict[CueCategory, dict[str, str]] = {
    CueCategory.BRAKE_LATER: {"en": "braking", "it": "frenata"},
    CueCategory.BRAKE_EARLIER: {"en": "braking", "it": "frenata"},
    CueCategory.LESS_BRAKE: {"en": "braking", "it": "frenata"},
    CueCategory.TRAIL_BRAKE: {"en": "braking", "it": "frenata"},
    CueCategory.MORE_THROTTLE: {"en": "traction", "it": "trazione"},
    CueCategory.PARTIAL_THROTTLE: {"en": "traction", "it": "trazione"},
    CueCategory.COASTING: {"en": "traction", "it": "trazione"},
    CueCategory.CARRY_SPEED: {"en": "cornering", "it": "percorrenza"},
    CueCategory.TIME_LOSS: {"en": "line", "it": "linea"},
    CueCategory.LIMITER: {"en": "gears", "it": "marce"},
    CueCategory.GEAR_TOO_TALL: {"en": "gears", "it": "marce"},
}
THEME_DEFAULT: dict[str, str] = {"en": "driving", "it": "guida"}


def theme_key(category: CueCategory) -> str:
    """The English theme key, for aggregation and comparison across modules."""
    return THEME.get(category, THEME_DEFAULT)["en"]


def theme_label(category: CueCategory, lang: str) -> str:
    """The theme as shown to the driver, in ``lang`` (falls back to English)."""
    entry = THEME.get(category, THEME_DEFAULT)
    return entry.get(lang) or entry["en"]
```

- [ ] **Step 4: Fai delegare `focus.py`**

In `src/accoach/coaching/focus.py` **cancella** il blocco `_THEME = {...}` /
`_THEME_DEFAULT = {...}` (righe 52-60) e la funzione `_theme` (righe 63-65), e mettici:

```python
# The theme table moved to cue.py, next to the category it describes: the voice
# gate needs it too, and scheduler.py cannot import this module without pulling
# debrief.py in behind it.
from .cue import THEME as _THEME            # noqa: F401 - re-export for debrief
from .cue import THEME_DEFAULT as _THEME_DEFAULT   # noqa: F401
from .cue import theme_label as _theme_label


def _theme(cat: CueCategory, lang: str) -> str:
    return _theme_label(cat, lang)
```

L'import di `CueCategory` in cima a `focus.py` c'è già (riga 30): non duplicarlo.

- [ ] **Step 5: Fai delegare `debrief.py`**

In `src/accoach/coaching/debrief.py`, sostituisci il corpo di `_theme_key` (righe 473-477) con:

```python
def _theme_key(cat: CueCategory) -> str:
    """The English theme key regardless of language, for aggregation."""
    from .cue import theme_key

    return theme_key(cat)
```

- [ ] **Step 6: Esegui i test nuovi e poi la suite intera**

Run: `python -m pytest tests/test_cue_theme.py -v`
Expected: PASS (4 test)

Run: `python -m pytest -q`
Expected: PASS. Se `tests/test_debrief.py` o `tests/test_focus.py` falliscono, il titolo del debrief
è cambiato: **è un errore di questo task**, non un test da aggiornare. Le categorie che raggiungono
`CornerLoss` sono solo le sei di `classify_corner` (`BRAKE_LATER`, `CARRY_SPEED`, `GOOD`,
`LESS_BRAKE`, `MORE_THROTTLE`, `TIME_LOSS`) e i loro temi non devono cambiare.

- [ ] **Step 7: Commit**

```bash
git add src/accoach/coaching/cue.py src/accoach/coaching/focus.py src/accoach/coaching/debrief.py tests/test_cue_theme.py
git commit -m "Il tema di un consiglio vive accanto alla categoria, e li' li copre tutti"
```

---

### Task 2: Le parole-innesco

**Files:**
- Modify: `src/accoach/coaching/cue.py` (in fondo, dopo `theme_label`)
- Test: `tests/test_cue_trigger.py` (nuovo)

**Interfaces:**
- Consumes: `CueCategory`, `CueTier`, `tier_of` (Task 1 non serve a questo task).
- Produces: `accoach.coaching.cue.TRIGGER: dict[CueCategory, dict[str, str]]`,
  `accoach.coaching.cue.trigger_text(cat: CueCategory, lang: str) -> str | None`
  (`None` per le categorie che non sono di tecnica o che non hanno innesco).

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_cue_trigger.py`:

```python
"""Le parole-innesco: quello che il coach dice in pista quando c'e' un focus.

Tre coach professionisti indipendenti usano lo stesso strumento e lo stesso nome
(«trigger words»), per un motivo dichiarato: la banda passante del pilota che guida
e' finita. Una-tre parole, sempre le stesse.

Il test sulle due lingue non e' pedanteria: l'audit del 2026-08-08 ha trovato due
messaggi che escono in italiano quando l'interfaccia e' in inglese.
"""
from accoach.coaching.cue import (
    TRIGGER, CueCategory, CueTier, tier_of, trigger_text,
)


def test_trigger_is_one_to_three_words():
    for cat, entry in TRIGGER.items():
        for lang, phrase in entry.items():
            n = len(phrase.split())
            assert 1 <= n <= 3, f"{cat.name}/{lang}: {n} parole in {phrase!r}"


def test_every_technique_category_has_a_trigger_in_both_languages():
    missing = [
        c.name for c in CueCategory
        if tier_of(c) == CueTier.TECHNIQUE
        and c is not CueCategory.GOOD
        and not (TRIGGER.get(c, {}).get("it") and TRIGGER.get(c, {}).get("en"))
    ]
    assert not missing, f"categorie di tecnica senza innesco in due lingue: {missing}"


def test_trigger_text_returns_none_outside_technique():
    assert trigger_text(CueCategory.LOCKED, "it") is None
    assert trigger_text(CueCategory.TYRE_PRESSURE, "it") is None
    assert trigger_text(CueCategory.GOOD, "it") is None


def test_trigger_text_falls_back_to_english():
    assert trigger_text(CueCategory.MORE_THROTTLE, "it") == "gas"
    assert trigger_text(CueCategory.MORE_THROTTLE, "en") == "throttle"
    assert trigger_text(CueCategory.MORE_THROTTLE, "de") == "throttle"
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_cue_trigger.py -v`
Expected: FAIL con `ImportError: cannot import name 'TRIGGER'`

- [ ] **Step 3: Implementa in `cue.py`**

Aggiungi in fondo a `src/accoach/coaching/cue.py`:

```python
# What the coach says on track when a focus is active: one to three words, always
# the same ones for that mistake. The full sentence still goes to the screen and
# to the debrief — the eye gets the detail, the ear gets the word.
#
# Only technique cues have one. An acute call is already short and must stay
# literal ("Bloccaggio!"), and an advisory is spoken at the finish line, where
# there is room for a sentence.
TRIGGER: dict[CueCategory, dict[str, str]] = {
    CueCategory.BRAKE_LATER: {"it": "più tardi", "en": "later"},
    CueCategory.BRAKE_EARLIER: {"it": "prima", "en": "earlier"},
    CueCategory.LESS_BRAKE: {"it": "meno freno", "en": "less brake"},
    CueCategory.TRAIL_BRAKE: {"it": "rilascia", "en": "release"},
    CueCategory.MORE_THROTTLE: {"it": "gas", "en": "throttle"},
    CueCategory.PARTIAL_THROTTLE: {"it": "tutto gas", "en": "full throttle"},
    CueCategory.COASTING: {"it": "veleggi", "en": "coasting"},
    CueCategory.CARRY_SPEED: {"it": "porta velocità", "en": "carry speed"},
    CueCategory.TIME_LOSS: {"it": "qui perdi", "en": "losing here"},
    CueCategory.LIMITER: {"it": "cambia", "en": "shift"},
    CueCategory.GEAR_TOO_TALL: {"it": "scala", "en": "downshift"},
}


def trigger_text(category: CueCategory, lang: str) -> str | None:
    """The on-track trigger word for ``category``, or ``None`` if it has none."""
    entry = TRIGGER.get(category)
    if entry is None:
        return None
    return entry.get(lang) or entry["en"]
```

- [ ] **Step 4: Esegui i test**

Run: `python -m pytest tests/test_cue_trigger.py -v`
Expected: PASS (4 test)

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/accoach/coaching/cue.py tests/test_cue_trigger.py
git commit -m "Le parole-innesco: una-tre parole, sempre le stesse, nelle due lingue"
```

---

### Task 3: Il filtro nello scheduler

**Files:**
- Modify: `src/accoach/coaching/scheduler.py` (import, `__init__`, nuovo `set_focus`, `poll`)
- Test: `tests/test_scheduler_focus.py` (nuovo — `tests/test_scheduler.py` non si tocca)

**Interfaces:**
- Consumes: `accoach.coaching.cue.theme_key` (Task 1), `CueTier`, `tier_of`.
- Produces: `CueScheduler.set_focus(theme: str | None) -> None` e l'attributo
  `CueScheduler._focus_theme: str | None` (default `None`).

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_scheduler_focus.py`:

```python
"""Il budget di attenzione: con un focus attivo si parla di un tema solo.

Massimo due o tre temi per sessione e' la regola su cui concordano coach
professionisti indipendenti, per un motivo dichiarato: la banda passante del pilota
in movimento e' finita. Qui il tetto e' uno, perche' il FocusCoach elegge un focus
per volta.

Restano fuori dal filtro gli acuti (sono eventi, non temi da allenare) e gli avvisi
(si dicono al traguardo, dove c'e' spazio per una frase).
"""
from accoach.coaching.cue import Cue, CueCategory
from accoach.coaching.scheduler import CueScheduler


def _cue(category, priority, segment=0):
    return Cue(category=category, message=category.value, priority=priority,
               segment=segment, pos=0.0)


def test_no_focus_behaves_exactly_as_today():
    sch = CueScheduler()
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 300.0, segment=4))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.MORE_THROTTLE


def test_cue_in_the_focus_theme_speaks():
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.LESS_BRAKE, 300.0, segment=4))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.LESS_BRAKE


def test_cue_outside_the_focus_theme_stays_silent():
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 900.0, segment=4))   # costa di piu'
    assert sch.poll(now=100.0) is None


def test_the_focus_theme_holds_everywhere_on_the_lap():
    """I coach lavorano il pattern, non una curva sola."""
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.LESS_BRAKE, 100.0, segment=11))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.segment == 11


def test_acute_and_advisory_ignore_the_focus():
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.WHEELSPIN, 250.0, segment=2))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.WHEELSPIN

    sch2 = CueScheduler()
    sch2.set_focus("braking")
    sch2.submit(_cue(CueCategory.TYRE_PRESSURE, 240.0, segment=0))
    chosen2 = sch2.poll(now=100.0)
    assert chosen2 is not None and chosen2.category is CueCategory.TYRE_PRESSURE


def test_praise_ignores_the_focus():
    """Aprire con qualcosa di vero che il pilota fa bene e' meta' del mestiere."""
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.GOOD, 50.0, segment=6))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.GOOD


def test_clearing_the_focus_restores_everything():
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.set_focus(None)
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 300.0, segment=4))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.MORE_THROTTLE


def test_an_off_theme_cue_does_not_consume_the_speaking_slot():
    """Scartato nella scelta, non alla submit: se parla qualcos'altro, parla."""
    sch = CueScheduler()
    sch.set_focus("braking")
    sch.submit(_cue(CueCategory.MORE_THROTTLE, 900.0, segment=4))
    sch.submit(_cue(CueCategory.LESS_BRAKE, 100.0, segment=5))
    chosen = sch.poll(now=100.0)
    assert chosen is not None and chosen.category is CueCategory.LESS_BRAKE
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_scheduler_focus.py -v`
Expected: FAIL con `AttributeError: 'CueScheduler' object has no attribute 'set_focus'`

- [ ] **Step 3: Implementa in `scheduler.py`**

Cambia l'import in cima al file:

```python
from .cue import Cue, CueCategory, CueTier, theme_key, tier_of
```

Aggiungi in fondo a `__init__` (dopo `self._recent`):

```python
        # The theme the session is working on, as an English key, or None while
        # no focus has been elected. See `set_focus`.
        self._focus_theme: str | None = None
```

Aggiungi il metodo, subito prima di `submit`:

```python
    def set_focus(self, theme: str | None) -> None:
        """Limit on-track technique advice to one theme — the attention budget.

        Coaches cap a session at two or three themes and give the reason out
        loud: the driver's bandwidth while driving is finite. The FocusCoach
        already elects one weakness at a time; this is how the voice gets told.

        ``theme`` is the **English** key from :func:`accoach.coaching.cue.theme_key`,
        never the translated label — a comparison that changed outcome with the
        interface language would be invisible in Italian.

        ``None`` (no focus elected yet) restores the previous behaviour exactly:
        the coach speaks about everything, as it did before this existed.
        """
        self._focus_theme = theme

    @property
    def focus_theme(self) -> str | None:
        """The theme currently being worked, or None. Read-only for callers."""
        return self._focus_theme

    def _off_theme(self, cue: Cue) -> bool:
        """True when this cue belongs to a theme the session isn't working on.

        Only technique cues are filtered. An acute call is an event, not a theme
        to train, and an advisory is car information spoken at the finish line.
        Praise is exempt too: naming something the driver did well is half the
        job, and it is never the thing that overloads them.
        """
        if self._focus_theme is None:
            return False
        if tier_of(cue.category) != CueTier.TECHNIQUE:
            return False
        if cue.category is CueCategory.GOOD:
            return False
        return theme_key(cue.category) != self._focus_theme
```

E dentro il ciclo di eleggibilità in `poll`, subito dopo `if acute_only and cue.tier != CueTier.ACUTE: continue`, aggiungi:

```python
            if self._off_theme(cue):
                continue
```

- [ ] **Step 4: Esegui i test**

Run: `python -m pytest tests/test_scheduler_focus.py tests/test_scheduler.py -v`
Expected: PASS (8 nuovi + 12 esistenti). I 12 esistenti devono passare **senza modifiche**.

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/accoach/coaching/scheduler.py tests/test_scheduler_focus.py
git commit -m "Il coach in pista parla di un tema solo, quando un focus c'e'"
```

---

### Task 4: Il motore dice allo scheduler qual e' il tema

**Files:**
- Modify: `src/accoach/engine.py:338` (subito dopo `self._focus_report = self._focus.observe(...)`)
- Test: `tests/test_engine_focus_gate.py` (nuovo)

**Interfaces:**
- Consumes: `CueScheduler.set_focus` (Task 3), `cue.theme_key` (Task 1),
  `FocusReport.focus: Focus | None` con `Focus.category: CueCategory` (`focus.py:126-135`).
- Produces: niente per i task successivi.

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_engine_focus_gate.py`:

```python
"""Il tema attivo arriva allo scheduler dal FocusCoach, come chiave inglese.

`Focus.theme` e' la stringa tradotta ("frenata"): usarla per il confronto
funzionerebbe in italiano e romperebbe il filtro in inglese. Questo test esiste per
inchiodare quel punto.
"""
from accoach.coaching.cue import CueCategory
from accoach.coaching.focus import Focus, FocusKind, FocusReport
from accoach.engine import _focus_theme_key


def _focus(category, theme):
    return Focus(corner_index=3, name="Curva 4", theme=theme, category=category,
                 baseline_ms=300.0, drill="")


def test_active_focus_yields_the_english_key():
    rep = FocusReport(kind=FocusKind.DRILL,
                      message="",
                      focus=_focus(CueCategory.LESS_BRAKE, "frenata"))
    assert _focus_theme_key(rep) == "braking"


def test_the_translated_label_is_not_used():
    """Anche con l'etichetta in italiano, la chiave resta inglese."""
    rep = FocusReport(kind=FocusKind.DRILL,
                      message="",
                      focus=_focus(CueCategory.MORE_THROTTLE, "trazione"))
    assert _focus_theme_key(rep) == "traction"


def test_no_focus_yields_none():
    assert _focus_theme_key(None) is None
    assert _focus_theme_key(FocusReport(kind=FocusKind.ASSESS, message="")) is None
    assert _focus_theme_key(FocusReport(kind=FocusKind.CLEAN, message="")) is None
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_engine_focus_gate.py -v`
Expected: FAIL con `ImportError: cannot import name '_focus_theme_key' from 'accoach.engine'`

- [ ] **Step 3: Implementa in `engine.py`**

Aggiungi la funzione a livello di modulo, subito dopo il blocco `_SAFETY_CATEGORIES`
(che finisce a riga 74) — è pura e testabile senza costruire un motore:

```python
def _focus_theme_key(report: "FocusReport | None") -> str | None:
    """The English theme key of the active focus, or None if there isn't one.

    Deliberately not `report.focus.theme`: that one is translated for the driver
    ("frenata"), and comparing it against the scheduler's key would work in
    Italian and silently stop filtering in English.
    """
    from .coaching.cue import theme_key

    if report is None or report.focus is None:
        return None
    return theme_key(report.focus.category)
```

E subito dopo la riga 338 (`self._focus_report = self._focus.observe(debrief, stable=stable)`)
aggiungi:

```python
                # Tell the voice which theme the session is on. The FocusCoach has
                # elected one weakness at a time since it was written; until now
                # nobody downstream was listening.
                self.scheduler.set_focus(_focus_theme_key(self._focus_report))
```

Attenzione all'indentazione: la riga 338 è dentro un blocco annidato — allinea la nuova riga
esattamente a quella.

- [ ] **Step 4: Esegui i test**

Run: `python -m pytest tests/test_engine_focus_gate.py -v`
Expected: PASS (3 test)

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/accoach/engine.py tests/test_engine_focus_gate.py
git commit -m "Il motore dice allo scheduler su che tema si sta lavorando"
```

---

### Task 5: L'orecchio prende la parola, l'occhio la frase

**Files:**
- Modify: `src/accoach/engine.py:788-794` (il blocco `if spoken is not None:`)
- Test: `tests/test_engine_trigger_voice.py` (nuovo)

**Interfaces:**
- Consumes: `cue.trigger_text` (Task 2), `CueScheduler._focus_theme` (Task 3).
- Produces: niente.

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_engine_trigger_voice.py`:

```python
"""Con un focus attivo la voce dice la parola, lo schermo tiene la frase.

I coach parlano in pista con una-tre parole e spiegano a monitor fermo. Qui:
`voice.say` riceve l'innesco, mentre lo storico e lo stato del motore conservano
il messaggio intero — l'overlay e il debrief non perdono niente.
"""
from accoach.coaching.cue import Cue, CueCategory
from accoach.engine import _spoken_forms


def _cue(category, message):
    return Cue(category=category, message=message, priority=100.0,
               segment=3, pos=0.5)


def test_without_a_focus_voice_and_screen_say_the_same_thing():
    cue = _cue(CueCategory.LESS_BRAKE, "Freni troppo in curva 4")
    voice, screen = _spoken_forms(cue, focus_theme=None, lang="it")
    assert voice == "Freni troppo in curva 4"
    assert screen == "Freni troppo in curva 4"


def test_with_a_focus_the_voice_gets_the_trigger_word():
    cue = _cue(CueCategory.LESS_BRAKE, "Freni troppo in curva 4")
    voice, screen = _spoken_forms(cue, focus_theme="braking", lang="it")
    assert voice == "meno freno"
    assert screen == "Freni troppo in curva 4"


def test_a_cue_without_a_trigger_keeps_its_sentence():
    cue = _cue(CueCategory.LOCKED, "Bloccaggio!")
    voice, screen = _spoken_forms(cue, focus_theme="braking", lang="it")
    assert voice == "Bloccaggio!"
    assert screen == "Bloccaggio!"


def test_the_trigger_follows_the_language():
    cue = _cue(CueCategory.MORE_THROTTLE, "Poco gas in uscita")
    voice, _ = _spoken_forms(cue, focus_theme="traction", lang="en")
    assert voice == "throttle"
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_engine_trigger_voice.py -v`
Expected: FAIL con `ImportError: cannot import name '_spoken_forms'`

- [ ] **Step 3: Implementa in `engine.py`**

Aggiungi a livello di modulo, subito sotto `_focus_theme_key`:

```python
def _spoken_forms(cue: "Cue", focus_theme: str | None, lang: str) -> tuple[str, str]:
    """What the ear hears and what the eye reads: (voice, screen).

    They are the same string until a focus is active. From then on the voice gets
    the trigger word and the screen keeps the whole sentence — the driver in a
    corner has room for three words, the debrief afterwards has room for the rest.
    """
    from .coaching.cue import trigger_text

    if focus_theme is None:
        return cue.message, cue.message
    trigger = trigger_text(cue.category, lang)
    if trigger is None:
        return cue.message, cue.message
    return trigger, cue.message
```

Poi sostituisci il blocco alle righe 788-794 con:

```python
        if spoken is not None:
            # Cues are authored in Italian (so the neural WAVs match); render them
            # in the active language for both the voice and the on-screen text.
            spoken.message = cue_text(spoken.message)
            voice_text, spoken.message = _spoken_forms(
                spoken, self.scheduler.focus_theme, current_language())
            if self.voice is not None:
                self.voice.say(voice_text)
            self.history.append(spoken.message)
            del self.history[:-20]
```

`current_language` è già importato (`engine.py:45`, insieme a `cue_text`): non aggiungere import.

- [ ] **Step 4: Esegui i test**

Run: `python -m pytest tests/test_engine_trigger_voice.py -v`
Expected: PASS (4 test)

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/accoach/engine.py tests/test_engine_trigger_voice.py
git commit -m "In pista l'orecchio prende la parola, lo schermo tiene la frase"
```

---

### Task 6: Il patto — il briefing annuncia la parola

**Files:**
- Modify: `src/accoach/coaching/focus.py` (`_MSG["brief"]`, righe ~79-84, e il punto che lo formatta)
- Test: `tests/test_focus_trigger_pact.py` (nuovo)

**Interfaces:**
- Consumes: `cue.trigger_text` (Task 2).
- Produces: niente.

Senza il patto una parola sola non vuol dire niente: i coach le concordano **prima** di scendere in
pista, e lo dicono esplicitamente.

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `tests/test_focus_trigger_pact.py`:

```python
"""Il briefing dichiara la parola che sentirai in pista.

Le parole-innesco funzionano perche' sono concordate prima. Un coach che iniziasse a
gridare «gas» senza averlo detto starebbe solo gridando.
"""
from accoach.coaching.cue import CueCategory
from accoach.coaching.focus import _brief_pact


def test_the_pact_names_the_trigger_word():
    assert _brief_pact(CueCategory.LESS_BRAKE, "it") == " In pista ti dirò solo: «meno freno»."
    assert _brief_pact(CueCategory.LESS_BRAKE, "en") == " On track I'll only say: “less brake”."


def test_no_trigger_no_pact():
    """Le categorie senza innesco non promettono niente."""
    assert _brief_pact(CueCategory.LOCKED, "it") == ""
    assert _brief_pact(CueCategory.GOOD, "it") == ""
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python -m pytest tests/test_focus_trigger_pact.py -v`
Expected: FAIL con `ImportError: cannot import name '_brief_pact'`

- [ ] **Step 3: Implementa in `focus.py`**

Aggiungi accanto agli altri helper (dopo `_theme`):

```python
_PACT = {
    "it": " In pista ti dirò solo: «{word}».",
    "en": " On track I'll only say: “{word}”.",
}


def _brief_pact(cat: CueCategory, lang: str) -> str:
    """The sentence that agrees the trigger word with the driver, or "".

    A trigger word only works because it was agreed beforehand — that is how every
    coach observed introduces one. Said without the pact it is just a shout.
    """
    from .cue import trigger_text

    word = trigger_text(cat, lang)
    if not word:
        return ""
    tmpl = _PACT.get(lang) or _PACT["en"]
    return tmpl.format(word=word)
```

Poi accoda il patto al briefing. Il punto esatto è `focus.py:241-245`, che oggi è:

```python
        return FocusReport(
            FocusKind.BRIEF,
            _m("brief", lang, name=focus.name, theme=focus.theme,
               base=_secs(focus.baseline_ms), cause=cause, drill=focus.drill),
            focus=focus, drill=focus.drill, progress_ms=focus.baseline_ms)
```

e diventa:

```python
        return FocusReport(
            FocusKind.BRIEF,
            _m("brief", lang, name=focus.name, theme=focus.theme,
               base=_secs(focus.baseline_ms), cause=cause, drill=focus.drill)
            + _brief_pact(focus.category, lang),
            focus=focus, drill=focus.drill, progress_ms=focus.baseline_ms)
```

Il patto va **solo** sul briefing, non su `_drill`: si concorda una volta, poi si usa.

- [ ] **Step 4: Esegui i test**

Run: `python -m pytest tests/test_focus_trigger_pact.py tests/test_focus.py -v`
Expected: PASS. Se un test esistente di `test_focus.py` confronta il messaggio di briefing
carattere per carattere, va aggiornato: il patto è una **nuova frase voluta**, non una regressione.

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/accoach/coaching/focus.py tests/test_focus_trigger_pact.py tests/test_focus.py
git commit -m "Il briefing concorda la parola che sentirai in pista"
```

---

### Task 7 (bloccato qui): Dare voce neurale alle parole-innesco

**Files:**
- Modify: `tools/render_cues.py` (`static_cue_messages`)
- Create: `src/accoach/voice_cues/*.wav` + aggiornamento di `manifest.json`

**Perché è separato e ultimo.** `Voice` prova prima i WAV Piper e poi SAPI5, quindi dopo il Task 5
le parole-innesco **funzionano già**, ma con la voce robotica. Il test
`test_every_static_cue_has_a_neural_wav` non se ne accorge: `static_cue_messages()` raccoglie solo
stringhe **dentro chiamate che citano `CueCategory` e più lunghe di 5 caratteri**
(`tools/render_cues.py:37-61`), e una tabella non è una chiamata. Estendere lo scanner **senza**
poter rendere i WAV lascerebbe la suite rossa.

**Prerequisito non soddisfatto su questa macchina**: `tools/piper/piper.exe` non esiste (verificato
il 2026-08-08). Serve scaricare `piper_windows_amd64.zip` e la voce italiana in `tools/piper/`,
come dice `render_cues.py:98-100`. **Se manca, non eseguire questo task e non indebolire il test**:
il coach parla lo stesso.

- [ ] **Step 1: Verifica il prerequisito**

Run: `ls tools/piper/piper.exe`
Se non esiste: **fermati qui** e riferisci che il task è bloccato. Non modificare
`tools/render_cues.py`.

- [ ] **Step 2: Estendi lo scanner**

In `tools/render_cues.py`, dentro `static_cue_messages`, prima di `return messages`:

```python
    # The trigger words are a table, not a call, so the scanner above cannot see
    # them — and they are exactly the phrases the driver hears most often. Only
    # the Italian ones: the shipped WAVs are Italian by construction.
    from accoach.coaching.cue import TRIGGER
    messages.update(e["it"] for e in TRIGGER.values())
```

- [ ] **Step 3: Verifica che il test di copertura ora fallisca**

Run: `python -m pytest tests/test_voice_cues.py::test_every_static_cue_has_a_neural_wav -v`
Expected: FAIL, elencando le undici parole-innesco italiane.

- [ ] **Step 4: Rendi i WAV**

Run: `python tools/render_cues.py`
Expected: scrive i WAV mancanti in `src/accoach/voice_cues/` e aggiorna `manifest.json`.

- [ ] **Step 5: Verifica**

Run: `python -m pytest tests/test_voice_cues.py -v`
Expected: PASS (3 test).

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Ascolta almeno una parola**

Apri uno dei WAV nuovi e ascoltalo. Una parola sola pronunciata male è peggio della frase che
sostituisce, e nessun test lo sente.

- [ ] **Step 7: Commit**

```bash
git add tools/render_cues.py src/accoach/voice_cues/
git commit -m "Le parole-innesco hanno una voce neurale, non SAPI5"
```

---

## Verifica finale, prima di dire che è fatto

- [ ] `python -m pytest -q` — suite intera verde, e riporta il numero di test.
- [ ] Con `focus_theme = None` nessun test esistente è stato modificato per farlo passare
      (`tests/test_scheduler.py` in particolare, che non doveva essere toccato).
- [ ] Prova a mano: `python -m accoach` con la demo, elegge un focus, e verifica **a orecchio e a
      schermo** che in pista si senta la parola mentre l'overlay mostra la frase.
- [ ] Se il Task 7 è rimasto bloccato, dirlo esplicitamente: la funzione è completa ma la voce è
      SAPI5 finché Piper non c'è.
