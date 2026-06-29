"""The Focus/Lesson layer — the *driver*'s twin of the race engineer.

The race engineer (:mod:`accoach.engineer`) fixes the *car*: it acts on a symptom
spread across several corners, because that's a setup problem. This layer fixes
the *driver*: it picks the single recurring place you lose the most time and
coaches it to the ground before moving on — one weakness at a time, the way a
real coach runs a session, instead of dumping every fault at once.

It consumes a :class:`~accoach.coaching.debrief.LapDebrief` per completed lap
(where you lost time vs the reference, and why) and runs a turn-based loop:

    assess  → gather a few clean laps so the weakness is *recurring*, not a fluke
    brief   → name the focus (corner + theme + the fix to try)
    drill   → keep working it; report progress lap by lap
    improved→ measured praise ("Curva 4: da 0.30s a 0.07s") → next focus
    stuck   → it won't budge after some laps → park it (maybe it's setup) → next
    clean   → nothing recurring worth a focus: just fine-tuning left

Like the engineer it is deterministic and side-effect free (one report per lap),
rebuilt per car/track, and it only counts *stable* laps (complete, no off) so an
excursion can't invent a weakness. It never touches telemetry — the coaching
layer feeds it debriefs, this only decides *what to work on next*.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum

from ..i18n import current_language
from .cue import CueCategory
from .debrief import CornerLoss, LapDebrief
from .thresholds import RECUR_FRAC as _RECUR_FRAC
from .thresholds import SIGNIF_LOSS_MS as _SIGNIF_MS

# --- tuning constants ------------------------------------------------------

_MIN_LAPS = 3            # clean laps needed to pick a focus / to judge a verdict
_WINDOW = 6              # rolling debrief buffer used to spot a recurring loss
# _RECUR_FRAC / _SIGNIF_MS are shared with trends.py (see coaching/thresholds.py)
# so the live coach and the analysis tab can't disagree on what's recurring.
_IMPROVED_FRAC = 0.5     # focus loss must fall to ≤ 50% of baseline…
_SOLVED_MS = 80.0        # …and below this absolute, to count as solved
_PATIENCE = 6            # laps spent on a focus with no win → park it, move on


# A short, driver-facing label for what to work on, by loss category. The live
# coach already says the "what"; this names the *theme* so a session has a spine.
# Per-language; the theme is shown in the message AND in the payload (overlay /
# engineer page), so it follows the active app language.
_THEME = {
    CueCategory.BRAKE_LATER: {"en": "braking", "it": "frenata"},
    CueCategory.BRAKE_EARLIER: {"en": "braking", "it": "frenata"},
    CueCategory.LESS_BRAKE: {"en": "braking", "it": "frenata"},
    CueCategory.MORE_THROTTLE: {"en": "traction", "it": "trazione"},
    CueCategory.CARRY_SPEED: {"en": "cornering", "it": "percorrenza"},
    CueCategory.TIME_LOSS: {"en": "line", "it": "linea"},
}
_THEME_DEFAULT = {"en": "driving", "it": "guida"}


def _theme(cat: CueCategory, lang: str) -> str:
    entry = _THEME.get(cat, _THEME_DEFAULT)
    return entry.get(lang) or entry["en"]


# Per-lap report messages, per language; resolved with the active language at the
# moment the report is built (FocusCoach runs in the engine = config.language).
_MSG = {
    "assess": {
        "en": "Assessing your weak points… ({n}/{total} clean laps).",
        "it": "Valuto i punti deboli… ({n}/{total} giri puliti).",
    },
    "clean": {
        "en": "No recurring weak point: steady driving. Just fine-tuning left.",
        "it": "Nessun punto debole ricorrente: guida costante. Si lima il dettaglio.",
    },
    "brief": {
        "en": "New focus — {name}: let's work on {theme}. "
              "You lose ~{base} here on average.{cause} {drill}",
        "it": "Nuovo focus — {name}: lavoriamo la {theme}. "
              "Qui perdi ~{base} di media.{cause} {drill}",
    },
    "drill_start": {
        "en": "{name}: work on {theme}. {drill}",
        "it": "{name}: lavora la {theme}. {drill}",
    },
    "improved": {
        "en": "{name} improved: from {base} to {cur}. Nice work — a new focus shortly.",
        "it": "{name} migliorata: da {base} a {cur}. Bel lavoro — nuovo focus a breve.",
    },
    "stuck": {
        "en": "{name}: {theme} isn't dropping ({cur} vs {base}).{setup} "
              "Parking it and moving on.",
        "it": "{name}: la {theme} non scende ({cur} vs {base}).{setup} "
              "La parcheggio e passo oltre.",
    },
    "stuck_setup": {
        "en": " Possible setup cause: {cause}",
        "it": " Possibile causa setup: {cause}",
    },
    "drill_progress": {
        "en": "{name}: keep working {theme}. Now ~{cur} (started at {base}).",
        "it": "{name}: continua sulla {theme}. Ora ~{cur} (partenza {base}).",
    },
    "default_drill": {
        "en": "Clean up the line and build consistency.",
        "it": "Pulisci la traiettoria e cerca costanza.",
    },
}


def _m(key: str, lang: str, **kw) -> str:
    entry = _MSG[key]
    return (entry.get(lang) or entry["en"]).format(**kw)


def _secs(ms: float) -> str:
    return f"{ms / 1000.0:.2f}s"


# --- the focus and the per-lap report --------------------------------------

@dataclass(frozen=True)
class Focus:
    """The one weakness being worked right now."""

    corner_index: int
    name: str               # friendly corner name ("Curva 4", or a real name)
    theme: str              # "frenata" / "trazione" / "percorrenza" / "linea"
    category: CueCategory   # the dominant loss type that defined the focus
    baseline_ms: float      # median loss at this corner when the focus was chosen
    drill: str              # the concrete thing to try (reused from the debrief fix)
    cause: str = ""         # handling "why", if the loss had one (may be "")


class FocusKind(Enum):
    ASSESS = "assess"        # still gathering laps to pick a focus
    BRIEF = "brief"          # a new focus was just chosen — here's the briefing
    DRILL = "drill"          # keep working the current focus
    IMPROVED = "improved"    # the focus improved — measured praise, next focus next lap
    STUCK = "stuck"          # the focus won't improve — parked, move on
    CLEAN = "clean"          # no recurring weakness worth a focus


@dataclass(frozen=True)
class FocusReport:
    """One lap's coaching report — what the UI shows about the lesson plan."""

    kind: FocusKind
    message: str
    focus: Focus | None = None
    drill: str = ""              # the actionable instruction for the active focus
    progress_ms: float = 0.0     # current (median) loss at the focus corner


# --- helpers ---------------------------------------------------------------

def _loss_at(debrief: LapDebrief, idx: int) -> float:
    """Time lost at corner ``idx`` this lap (0.0 if it wasn't a loss = good)."""
    for loss in debrief.losses:
        if loss.index == idx:
            return loss.lost_ms
    return 0.0


@dataclass
class _Agg:
    """Aggregated per-corner loss across the window, with the richest instance."""

    losses: list[float] = field(default_factory=list)
    hits: int = 0                       # laps where the loss was significant
    rep: CornerLoss | None = None       # worst single instance (richest detail)

    @property
    def median(self) -> float:
        return statistics.median(self.losses) if self.losses else 0.0


# --- the coach -------------------------------------------------------------

class FocusCoach:
    """Deterministic, one-weakness-at-a-time driver coach over lap debriefs."""

    def __init__(self, *, min_laps: int = _MIN_LAPS) -> None:
        self.min_laps = min_laps
        self.window: list[LapDebrief] = []
        self.focus: Focus | None = None
        self._focus_losses: list[float] = []     # losses at the focus since BRIEF
        self.mastered: set[int] = set()          # corners coached to the ground
        self.parked: set[int] = set()            # corners that wouldn't improve
        self._last = FocusReport(
            FocusKind.ASSESS,
            _m("assess", current_language(), n=0, total=min_laps))

    # -- public API --------------------------------------------------------
    def observe(self, debrief: LapDebrief, *, stable: bool = True) -> FocusReport:
        """Feed one completed lap's debrief; return the next coaching report.

        Only *stable* laps (complete, no off) move the plan forward — an excursion
        bloats every corner's loss and would invent a weakness. On an unstable lap
        the last report stands.
        """
        if not stable:
            return self._last

        self.window.append(debrief)
        self.window = self.window[-_WINDOW:]

        report = self._step(debrief)
        self._last = report
        return report

    # -- internals ---------------------------------------------------------
    def _step(self, debrief: LapDebrief) -> FocusReport:
        if self.focus is None:
            return self._pick_or_wait()
        return self._drill(debrief)

    def _pick_or_wait(self) -> FocusReport:
        lang = current_language()
        if len(self.window) < self.min_laps:
            return FocusReport(
                FocusKind.ASSESS,
                _m("assess", lang, n=len(self.window), total=self.min_laps))

        focus = self._choose()
        if focus is None:
            return FocusReport(FocusKind.CLEAN, _m("clean", lang))

        self.focus = focus
        self._focus_losses = []
        cause = f" {focus.cause}" if focus.cause else ""
        return FocusReport(
            FocusKind.BRIEF,
            _m("brief", lang, name=focus.name, theme=focus.theme,
               base=_secs(focus.baseline_ms), cause=cause, drill=focus.drill),
            focus=focus, drill=focus.drill, progress_ms=focus.baseline_ms)

    def _drill(self, debrief: LapDebrief) -> FocusReport:
        focus = self.focus
        lang = current_language()
        theme = _theme(focus.category, lang)
        self._focus_losses.append(_loss_at(debrief, focus.corner_index))
        recent = self._focus_losses[-self.min_laps:]
        current = statistics.median(recent)

        # Need a few post-briefing laps before any verdict.
        if len(self._focus_losses) < self.min_laps:
            return FocusReport(
                FocusKind.DRILL,
                _m("drill_start", lang, name=focus.name, theme=theme,
                   drill=focus.drill),
                focus=focus, drill=focus.drill, progress_ms=current)

        if current <= focus.baseline_ms * _IMPROVED_FRAC and current <= _SOLVED_MS:
            self.mastered.add(focus.corner_index)
            self.focus = None
            return FocusReport(
                FocusKind.IMPROVED,
                _m("improved", lang, name=focus.name,
                   base=_secs(focus.baseline_ms), cur=_secs(current)),
                progress_ms=current)

        if len(self._focus_losses) >= _PATIENCE:
            self.parked.add(focus.corner_index)
            self.focus = None
            setup = (_m("stuck_setup", lang, cause=focus.cause)
                     if focus.cause else "")
            return FocusReport(
                FocusKind.STUCK,
                _m("stuck", lang, name=focus.name, theme=theme,
                   cur=_secs(current), base=_secs(focus.baseline_ms), setup=setup),
                progress_ms=current)

        return FocusReport(
            FocusKind.DRILL,
            _m("drill_progress", lang, name=focus.name, theme=theme,
               cur=_secs(current), base=_secs(focus.baseline_ms)),
            focus=focus, drill=focus.drill, progress_ms=current)

    def _choose(self) -> Focus | None:
        """Pick the worst recurring, significant corner not already handled."""
        lang = current_language()
        agg = self._aggregate()
        recur_min = max(2, round(_RECUR_FRAC * len(self.window)))

        best: tuple[float, int, _Agg] | None = None
        for idx, a in agg.items():
            if idx in self.mastered or idx in self.parked:
                continue
            if a.hits < recur_min or a.median < _SIGNIF_MS:
                continue
            if best is None or a.median > best[0]:
                best = (a.median, idx, a)
        if best is None:
            return None

        median, idx, a = best
        rep = a.rep
        # Measure the baseline with the SAME denominator the drill uses: the median
        # of the loss at this corner over the WHOLE window, counting good laps as
        # 0.0. (`a.median` is over loss-only laps, so it would read higher than the
        # drill's `current` and make IMPROVED fire without real progress.)
        baseline = statistics.median([_loss_at(d, idx) for d in self.window])
        return Focus(
            corner_index=idx,
            name=rep.label,
            theme=_theme(rep.category, lang),
            category=rep.category,
            baseline_ms=baseline,
            drill=rep.fix or _m("default_drill", lang),
            cause=rep.cause,
        )

    def _aggregate(self) -> dict[int, _Agg]:
        """Per-corner loss across the window; the worst instance is kept as rep."""
        out: dict[int, _Agg] = {}
        for d in self.window:
            for loss in d.losses:
                a = out.setdefault(loss.index, _Agg())
                a.losses.append(loss.lost_ms)
                if loss.lost_ms >= _SIGNIF_MS:
                    a.hits += 1
                if a.rep is None or loss.lost_ms > a.rep.lost_ms:
                    a.rep = loss            # richest detail = the worst instance
        return out


def format_focus(report: FocusReport) -> str:
    """One-line render of a focus report for the terminal coach / logs."""
    icon = {
        FocusKind.ASSESS: "…",
        FocusKind.BRIEF: "🎯",
        FocusKind.DRILL: "🎯",
        FocusKind.IMPROVED: "✅",
        FocusKind.STUCK: "⏸",
        FocusKind.CLEAN: "✨",
    }.get(report.kind, "•")
    return f"{icon} {report.message}"
