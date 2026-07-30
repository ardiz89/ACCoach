"""Start recording by itself when the game appears.

The gap this closes is small and expensive: HONE has to be started by hand, so a
session you forgot to arm is a session that left no trace. Everything else in the
app — the debrief, the trends, the braking sheet, the training plan — is built on
laps that were recorded, and none of it can be recovered afterwards.

What starts is **the silent recorder, never the voice**. A coach that begins
talking because you opened the game is an intrusion; a recorder that makes no
sound can only prevent a loss. And it is **off unless you turn it on**: software
that records you without being asked is a different product from the one anyone
installed.

The interesting part is when it must *not* fire, which is why the rules live in a
class of their own with no Qt in sight:

* the driver hasn't asked for it;
* something is already recording — two recorders on one session write the same
  laps twice, and the second copy is indistinguishable from a real second lap;
* the game was already there a moment ago. Only the *appearance* of the game
  starts anything, so stopping the recorder by hand keeps it stopped: there is
  no second edge until you close the game and open it again.

The first tick counts as an appearance, deliberately. Opening the hub with the
game already running is the exact case the feature exists for — you were in the
car, you remembered the app afterwards. Turning the setting *on* mid-session
counts too, for the same reason.
"""

from __future__ import annotations

from typing import Callable

#: How often the hub asks. Three seconds is far below the time it takes to get
#: from the main menu to a lap, and the probe is opening a shared-memory handle
#: and closing it again — cheaper than the frame it happens inside.
POLL_MS = 3000


class GameWatcher:
    """Rising-edge detector over "the game is publishing telemetry"."""

    def __init__(self,
                 connected: Callable[[], bool],
                 busy: Callable[[], bool],
                 start: Callable[[], None],
                 enabled: Callable[[], bool]) -> None:
        self.connected = connected
        self.busy = busy
        self.start = start
        self.enabled = enabled
        # False, not None: see the module note — the first tick is an edge.
        self._was = False
        self.state = "off"

    def tick(self) -> bool:
        """Poll once. Returns True when this call started the recorder."""
        # Checked before anything else, and the edge is NOT consumed while off.
        # Otherwise ticking the box mid-session would do nothing until the next
        # time you launched the game — the driver asked for it *now*, and the
        # game is right there. It also means no shared-memory probe at all for
        # everyone who leaves this switched off.
        if not self.enabled():
            self.state = "off"
            return False
        try:
            here = bool(self.connected())
        except Exception:      # noqa: BLE001 - a watcher must never break the hub
            here = False
        appeared = here and not self._was
        self._was = here

        if self.busy():
            # Already recording (or coaching, which records too). Nothing to do,
            # and saying so is better than a silent no-op the driver can't read.
            self.state = "busy"
            return False
        self.state = "recording" if here else "waiting"
        if not appeared:
            return False
        try:
            self.start()
        except Exception:      # noqa: BLE001 - same reason
            return False
        self.state = "busy"
        return True


def game_is_running() -> bool:
    """True when AC/ACC is publishing telemetry right now.

    Uses the reader's own notion of "connected" rather than looking for a process
    name: the question is whether there is telemetry to record, and a game that
    is running but hasn't published its pages yet has nothing for us. One
    definition, shared with everything else that asks.
    """
    try:
        from .telemetry.reader import SharedMemoryReader

        return bool(SharedMemoryReader().read().connected)
    except Exception:          # noqa: BLE001
        return False
