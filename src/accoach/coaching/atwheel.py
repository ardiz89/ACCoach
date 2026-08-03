"""Did the driver actually turn the knob? Read it off the car, don't ask.

The race engineer splits its proposals in two: ``BOX`` needs the garage, ``AV``
(*al volo*) is a dial on the steering wheel you change on the straight. The
second kind is the most valuable thing it produces, because it costs no lap —
and until now it was the only kind that could never be **finished**.

The reason was structural: ``RaceEngineer.mark_applied()`` is what turns a
proposal into a change under test, and the only thing that called it was the
setup-file writer, which only exists for ``BOX`` changes. So an ``AV`` proposal
was announced, never marked applied, and re-emitted every lap forever; its phase
never closed and the engineer never moved on. On the GT3 profile that is **two
phases out of five** — brake bias and electronics — so a session could spend
itself hearing "move the brake bias one click" at every finish line.

The fix is not a button (there is one too, for the cases below, but a button is
the wrong primary answer for something you do at 250 km/h). It's to **watch the
car**: the aid levels and the brake bias are live channels, so when the engineer
asks for one more click of TC we can see the TC go up. That is also the honest
version — the same distinction this whole app is built on, between a change that
was requested and a change that was measured.

Limits, declared:

* **ACC only.** AC leaves these fields at -1, so nothing can be observed there
  and the page's manual confirmation is the only route. :meth:`arm` says so by
  returning ``False`` rather than arming a watch that can never fire.
* Only the parameters below are readable. Anything else ``AV`` would need its
  own channel, and there is no point guessing.
"""

from __future__ import annotations

from ..telemetry.snapshot import ACStatus, TelemetrySnapshot

# Setup parameter -> (snapshot field, size of one click in that field's units).
#
# The brake-bias step is MEASURED, not read off the spec: 0.750 → 0.760 → 0.746
# over ten and seven clicks on a 720S at Monza (2026-08-02), i.e. 0.002 of front
# fraction per click. The setup format declares it as 0.2 **%**, which is the
# same number in the other unit — they agree, and the measurement is what this
# code trusts because it is what the channel actually reports.
_WATCHED: dict[str, tuple[str, float]] = {
    "brakeBias": ("brake_bias", 0.002),
    "tC1": ("tc_level", 1.0),
    "abs": ("abs_level", 1.0),
}

# How much of the asked-for movement counts as "done". Deliberately lenient:
# the question is whether the driver turned the dial, not whether they landed on
# our exact number — they may click twice, or the car's step may not be quite
# ours. Anything less than this in the right direction is noise or a misread.
_ENOUGH = 0.5


def _reading(s: TelemetrySnapshot, param: str) -> float | None:
    """The live value of ``param``, or ``None`` when this car doesn't report it."""
    field = _WATCHED.get(param)
    if field is None:
        return None
    value = getattr(s, field[0], -1)
    # -1 is the reader's "no data" for every one of these (AC, or a cold frame).
    # Zero is a real level, so it must not be lumped in with it.
    return None if value is None or value < 0 else float(value)


class WheelWatch:
    """Stateful: armed with a proposal, then fed frames until the knob moves."""

    def __init__(self) -> None:
        self._param = ""
        self._want = 0.0          # signed movement expected, in field units
        self._baseline = 0.0

    @property
    def armed(self) -> bool:
        return bool(self._param)

    @property
    def param(self) -> str:
        return self._param

    def arm(self, param: str, delta_clicks: int, s: TelemetrySnapshot) -> bool:
        """Start watching ``param``; ``False`` if this car can't be watched.

        The baseline is read now, from the frame on which the proposal was made.
        A driver who turns the dial *before* we arm would go unnoticed — but the
        proposal is armed on the same tick the engineer emits it, which is the
        tick before the voice has finished saying it.
        """
        self.disarm()
        if not delta_clicks:
            return False
        step = _WATCHED.get(param)
        now = _reading(s, param)
        if step is None or now is None:
            return False
        self._param, self._baseline = param, now
        self._want = delta_clicks * step[1]
        return True

    def disarm(self) -> None:
        self._param, self._want, self._baseline = "", 0.0, 0.0

    def update(self, s: TelemetrySnapshot) -> bool:
        """Has the knob moved as asked? Disarms itself once it has."""
        if not self._param:
            return False
        if not (s.connected and s.status == ACStatus.LIVE):
            return False
        now = _reading(s, self._param)
        if now is None:
            return False
        moved = now - self._baseline
        # Same direction, and far enough. A move the other way is the driver
        # doing something else with the dial, and is not an answer to us.
        if self._want > 0:
            done = moved >= self._want * _ENOUGH
        else:
            done = moved <= self._want * _ENOUGH
        if done:
            self.disarm()
        return done
