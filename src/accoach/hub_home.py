"""The hub's Home = your last session, diagnosed.

This reads the same saved laps the web report reads and produces the *native*
headline "you lost 0.4s in T4: braking late → understeer", without a webview.
It's a direct port of the CLI :mod:`accoach.debrief_app` flow (catalog → latest
car/track → latest valid lap vs reference → detect corners → build_lap_debrief),
rendered into PySide6 widgets and computed off the UI thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import brand
from .coaching.debrief import CornerLoss
from .i18n import t
from .telemetry.snapshot import format_lap_time


@dataclass(slots=True)
class HomeData:
    """Everything the Home needs about the most recent session.

    ``status`` drives which layout is shown:
      ok            — a slower lap with rankable per-corner losses (common case)
      clean         — slower than the reference but no single corner stands out
      is_reference  — the latest lap *is* the fastest; nothing to beat
      no_reference  — laps exist but no usable reference yet
      empty         — no recorded laps at all
    """

    status: str
    car: str = ""
    track: str = ""
    lap_time_ms: int = 0
    reference_lap_ms: int = 0
    total_gap_ms: int = 0
    laps_count: int = 0
    best_ms: int = 0
    consistency: dict | None = None
    top: CornerLoss | None = None
    debrief_text: str = ""


def load_home_data(laps_dir: Path | str | None = None,
                   lang: str | None = None) -> HomeData:
    """Assemble the last-session diagnosis. Never raises — returns ``empty`` on any
    failure so the Home degrades gracefully instead of crashing the hub."""
    # Imported lazily so importing the launcher (e.g. in tests) doesn't drag in the
    # whole coaching/recording stack until the Home actually loads.
    from .coaching import build_lap_debrief, format_debrief, lap_time_consistency
    from .comparison import Reference
    from .recording import (
        DEFAULT_LAPS_DIR,
        find_reference_lap,
        list_lap_files,
        load_lap,
    )
    from .recording.catalog import LapCatalog
    from .recording.storage import _catalog_path
    from .track import detect_corners
    from .trackdata import name_corners

    laps_dir = Path(laps_dir) if laps_dir else DEFAULT_LAPS_DIR
    try:
        with LapCatalog(_catalog_path(laps_dir)) as cat:
            cat.sync(list_lap_files(laps_dir))
            row = cat._conn.execute(
                "SELECT car_model, track FROM lap ORDER BY recorded_utc DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return HomeData(status="empty")
            car, track = row["car_model"], row["track"]

            laps = cat.laps_for(car, track)
            valid_ms = [r["lap_time_ms"] for r in laps
                        if r["valid"] and r["lap_time_ms"] > 0]
            laps_count = len(valid_ms)
            best_ms = min(valid_ms, default=0)
            consistency = lap_time_consistency(valid_ms)

            reference_lap = find_reference_lap(car, track, laps_dir)
            review_path = next((r["path"] for r in laps if r["valid"]), None)
            if reference_lap is None or review_path is None:
                return HomeData(status="no_reference", car=car, track=track,
                                laps_count=laps_count, best_ms=best_ms,
                                consistency=consistency)
            reference = Reference(reference_lap)
            if not reference.usable:
                return HomeData(status="no_reference", car=car, track=track,
                                laps_count=laps_count, best_ms=best_ms,
                                consistency=consistency)

            review_lap = load_lap(review_path)
            corners = detect_corners(reference_lap.samples)
            debrief = build_lap_debrief(review_lap, reference, corners, lang)
            # Friendly corner names — set on the losses exactly like the API does.
            names = {c.index: n
                     for c, n in zip(corners, name_corners(track, corners, lang))}
            for loss in debrief.losses:
                loss.name = names.get(loss.index, loss.name)

            if debrief.is_reference:
                status = "is_reference"
            elif not debrief.losses:
                status = "clean"
            else:
                status = "ok"
            text = format_debrief(debrief, top=3, consistency=consistency, lang=lang)
            return HomeData(
                status=status,
                car=car, track=track,
                lap_time_ms=debrief.lap_time_ms,
                reference_lap_ms=debrief.reference_lap_ms,
                total_gap_ms=debrief.total_gap_ms,
                laps_count=laps_count, best_ms=best_ms,
                consistency=consistency,
                top=debrief.losses[0] if debrief.losses else None,
                debrief_text=text,
            )
    except Exception:  # pragma: no cover - defensive: never break the hub
        return HomeData(status="empty")


class _HomeWorker(QThread):
    """Computes :func:`load_home_data` off the UI thread (samples can be heavy)."""

    done = Signal(object)

    def __init__(self, laps_dir, lang, parent=None) -> None:
        super().__init__(parent)
        self._laps_dir = laps_dir
        self._lang = lang

    def run(self) -> None:  # noqa: D102
        self.done.emit(load_home_data(self._laps_dir, self._lang))


def _card(*widgets: QWidget) -> QFrame:
    frame = QFrame()
    frame.setProperty("role", "card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(6)
    for w in widgets:
        lay.addWidget(w)
    return frame


def _muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "muted")
    lbl.setWordWrap(True)
    return lbl


class HomePanel(QWidget):
    """The Home section: last-session headline + stats + contextual CTAs.

    The CTAs delegate to callbacks (usually the hub's process-spawn helpers) so
    this panel stays ignorant of how modes are launched.
    """

    def __init__(self, on_analysis, on_setup, laps_dir=None, parent=None) -> None:
        super().__init__(parent)
        self._on_analysis = on_analysis
        self._on_setup = on_setup
        self._laps_dir = laps_dir
        self._data: HomeData | None = None
        self._worker: _HomeWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        self._title = QLabel(brand.NAME)
        self._title.setProperty("role", "title")
        self._subtitle = QLabel(brand.TAGLINE)
        self._subtitle.setProperty("role", "muted")
        root.addWidget(self._title)
        root.addWidget(self._subtitle)

        self._session = QLabel("")
        self._session.setProperty("role", "muted")
        root.addWidget(self._session)

        # Headline card — the causal "why you were slow".
        self._headline = QLabel("")
        self._headline.setProperty("role", "headline")
        self._headline.setWordWrap(True)
        self._cause = _muted("")
        self._fix = _muted("")
        root.addWidget(_card(self._headline, self._cause, self._fix))

        # Stat cards.
        self._stats = QGridLayout()
        self._stats.setSpacing(12)
        self._stat_widgets: dict[str, tuple[QLabel, QLabel]] = {}
        for col, key in enumerate(("best", "gap", "laps", "consistency")):
            value = QLabel("—")
            value.setProperty("role", "stat")
            label = QLabel("")
            label.setProperty("role", "muted")
            self._stats.addWidget(_card(value, label), 0, col)
            self._stat_widgets[key] = (value, label)
        root.addLayout(self._stats)

        # Contextual CTAs.
        cta = QHBoxLayout()
        cta.setSpacing(10)
        self._cta_analysis = QPushButton("")
        self._cta_analysis.setProperty("accent", True)
        self._cta_analysis.clicked.connect(lambda: self._on_analysis())
        self._cta_debrief = QPushButton("")
        self._cta_debrief.clicked.connect(self._show_debrief)
        self._cta_setup = QPushButton("")
        self._cta_setup.clicked.connect(lambda: self._on_setup())
        for b in (self._cta_analysis, self._cta_debrief, self._cta_setup):
            b.setMinimumHeight(40)
            cta.addWidget(b)
        root.addLayout(cta)
        root.addStretch(1)

        self.retranslate()
        self.refresh()

    # --- data ------------------------------------------------------------
    def refresh(self) -> None:
        """(Re)load the last session in the background. Cheap to call on show."""
        if self._worker is not None and self._worker.isRunning():
            return
        from .i18n import current_language
        self._headline.setText(t("home.loading"))
        self._cause.setText("")
        self._fix.setText("")
        self._worker = _HomeWorker(self._laps_dir, current_language(), self)
        self._worker.done.connect(self._apply)
        self._worker.start()

    def _apply(self, data: HomeData) -> None:
        self._data = data
        self._session.setText(
            f"{data.car} · {data.track}" if data.car else "")

        has_debrief = bool(data.debrief_text)
        self._cta_debrief.setEnabled(has_debrief)
        self._cta_debrief.setToolTip("" if has_debrief else t("home.empty_body"))

        if data.status == "empty":
            self._headline.setText(t("home.empty_title"))
            self._cause.setText(t("home.empty_body"))
            self._fix.setText("")
        elif data.status == "no_reference":
            self._headline.setText(t("home.no_ref_title"))
            self._cause.setText(t("home.no_ref_body"))
            self._fix.setText("")
        elif data.status == "is_reference":
            self._headline.setText(t("home.is_reference"))
            self._cause.setText("")
            self._fix.setText("")
        elif data.status == "clean" or data.top is None:
            self._headline.setText(t("home.clean_title"))
            self._cause.setText(t("home.clean_body"))
            self._fix.setText("")
        else:
            loss = data.top
            secs = loss.lost_ms / 1000.0
            self._headline.setText(
                f"{loss.label}  ·  −{secs:.1f}s  ·  {loss.message}")
            self._cause.setText(loss.cause or loss.detail)
            self._fix.setText(loss.fix)

        self._fill_stats(data)

    def _fill_stats(self, data: HomeData) -> None:
        best = format_lap_time(data.best_ms) if data.best_ms else "—"
        gap = (f"+{data.total_gap_ms / 1000.0:.2f}s"
               if data.status in ("ok", "clean") else "—")
        laps = str(data.laps_count) if data.laps_count else "—"
        spread = data.consistency.get("spread_ms", 0) if data.consistency else 0
        cons = f"{spread / 1000.0:.2f}s" if data.laps_count >= 2 else "—"
        values = {"best": best, "gap": gap, "laps": laps, "consistency": cons}
        for key, (value_lbl, _label) in self._stat_widgets.items():
            value_lbl.setText(values[key])

    # --- full debrief ----------------------------------------------------
    def _show_debrief(self) -> None:
        if not self._data or not self._data.debrief_text:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(t("home.cta_debrief"))
        dlg.resize(560, 420)
        lay = QVBoxLayout(dlg)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(self._data.debrief_text)
        text.setStyleSheet("font-family: 'Cascadia Mono', 'Consolas', monospace;")
        lay.addWidget(text)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton(t("btn.close"))
        close.clicked.connect(dlg.accept)
        row.addWidget(close)
        lay.addLayout(row)
        dlg.exec()

    # --- i18n ------------------------------------------------------------
    def retranslate(self) -> None:
        self._subtitle.setText(brand.TAGLINE)
        self._cta_analysis.setText(t("home.cta_analysis"))
        self._cta_debrief.setText(t("home.cta_debrief"))
        self._cta_setup.setText(t("home.cta_setup"))
        labels = {"best": t("home.stat_best"), "gap": t("home.stat_gap"),
                  "laps": t("home.stat_laps"),
                  "consistency": t("home.stat_consistency")}
        for key, (_value, label_lbl) in self._stat_widgets.items():
            label_lbl.setText(labels[key])
        if self._data is not None:
            self._apply(self._data)
