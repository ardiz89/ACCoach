"""ctypes definitions for the Assetto Corsa / ACC shared memory layout.

Both Assetto Corsa (AC) and Assetto Corsa Competizione (ACC) publish live
telemetry through three Windows memory-mapped files:

    Local\\acpmf_physics   -> SPageFilePhysics   (per-frame car physics)
    Local\\acpmf_graphics  -> SPageFileGraphics  (timing / session / HUD state)
    Local\\acpmf_static    -> SPageFileStatic    (constant data for the session)

The two games share the same base layout. ACC extends the structs with extra
fields at the end; AC simply allocates a shorter region. We map the full ACC
layout and only ever *rely* on the common prefix, so the same code reads both
games. Fields past the AC region read as zero/garbage on AC and must not be
trusted there (see ``AC_EXTRA`` markers).

Notes
-----
* Wide-char (``wchar``) fields are UTF-16; ctypes ``c_wchar`` is 2 bytes on
  Windows, which matches the game layout exactly.
* Array fields of size 4 are wheel-indexed: [FL, FR, RL, RR].
* All structs are packed to 4-byte alignment, matching the C# SDK structs.
"""

from __future__ import annotations

import ctypes

# Shared-memory tag names (Windows). The "Local\\" prefix is implicit for
# mmap tagname on Windows; the bare names below are what the games create.
PHYSICS_MAP = "Local\\acpmf_physics"
GRAPHICS_MAP = "Local\\acpmf_graphics"
STATIC_MAP = "Local\\acpmf_static"

_FLOAT = ctypes.c_float
_INT = ctypes.c_int32


class SPageFilePhysics(ctypes.Structure):
    """Per-frame physics page. Updated every simulation tick (~333 Hz internal,
    readable as fast as you poll). ``packetId`` increments each update."""

    _pack_ = 4
    _fields_ = [
        ("packetId", _INT),
        ("gas", _FLOAT),                       # 0..1 throttle
        ("brake", _FLOAT),                     # 0..1 brake
        ("fuel", _FLOAT),                      # litres
        ("gear", _INT),                        # 0 = reverse, 1 = neutral, 2 = 1st...
        ("rpms", _INT),
        ("steerAngle", _FLOAT),                # radians, +left
        ("speedKmh", _FLOAT),
        ("velocity", _FLOAT * 3),              # world m/s
        ("accG", _FLOAT * 3),                  # G force [x, y, z]
        ("wheelSlip", _FLOAT * 4),
        ("wheelLoad", _FLOAT * 4),             # unused in ACC
        ("wheelsPressure", _FLOAT * 4),        # psi
        ("wheelAngularSpeed", _FLOAT * 4),
        ("tyreWear", _FLOAT * 4),
        ("tyreDirtyLevel", _FLOAT * 4),
        ("tyreCoreTemperature", _FLOAT * 4),   # deg C
        ("camberRAD", _FLOAT * 4),
        ("suspensionTravel", _FLOAT * 4),
        ("drs", _FLOAT),
        ("tc", _FLOAT),                        # TC intervention 0..1
        ("heading", _FLOAT),
        ("pitch", _FLOAT),
        ("roll", _FLOAT),
        ("cgHeight", _FLOAT),
        ("carDamage", _FLOAT * 5),
        ("numberOfTyresOut", _INT),
        ("pitLimiterOn", _INT),
        ("abs", _FLOAT),                       # ABS intervention 0..1
        ("kersCharge", _FLOAT),
        ("kersInput", _FLOAT),
        ("autoShifterOn", _INT),
        ("rideHeight", _FLOAT * 2),
        ("turboBoost", _FLOAT),
        ("ballast", _FLOAT),
        ("airDensity", _FLOAT),
        ("airTemp", _FLOAT),
        ("roadTemp", _FLOAT),
        ("localAngularVel", _FLOAT * 3),
        ("finalFF", _FLOAT),                   # force feedback
        ("performanceMeter", _FLOAT),
        ("engineBrake", _INT),
        ("ersRecoveryLevel", _INT),
        ("ersPowerLevel", _INT),
        ("ersHeatCharging", _INT),
        ("ersIsCharging", _INT),
        ("kersCurrentKJ", _FLOAT),
        ("drsAvailable", _INT),
        ("drsEnabled", _INT),
        # ---- ACC_EXTRA below: present on ACC, untrustworthy on plain AC ----
        ("brakeTemp", _FLOAT * 4),             # deg C
        ("clutch", _FLOAT),
        ("tyreTempI", _FLOAT * 4),             # inner
        ("tyreTempM", _FLOAT * 4),             # middle
        ("tyreTempO", _FLOAT * 4),             # outer
        ("isAIControlled", _INT),
        ("tyreContactPoint", (_FLOAT * 3) * 4),
        ("tyreContactNormal", (_FLOAT * 3) * 4),
        ("tyreContactHeading", (_FLOAT * 3) * 4),
        ("brakeBias", _FLOAT),
        ("localVelocity", _FLOAT * 3),
    ]


class SPageFileGraphics(ctypes.Structure):
    """Timing, session and HUD state. Updated at HUD refresh rate."""

    _pack_ = 4
    _fields_ = [
        ("packetId", _INT),
        ("status", _INT),                      # AC_STATUS: 0 OFF,1 REPLAY,2 LIVE,3 PAUSE
        ("session", _INT),                     # AC_SESSION_TYPE
        ("currentTime", ctypes.c_wchar * 15),
        ("lastTime", ctypes.c_wchar * 15),
        ("bestTime", ctypes.c_wchar * 15),
        ("split", ctypes.c_wchar * 15),
        ("completedLaps", _INT),
        ("position", _INT),
        ("iCurrentTime", _INT),                # ms
        ("iLastTime", _INT),                   # ms
        ("iBestTime", _INT),                   # ms
        ("sessionTimeLeft", _FLOAT),
        ("distanceTraveled", _FLOAT),
        ("isInPit", _INT),
        ("currentSectorIndex", _INT),
        ("lastSectorTime", _INT),
        ("numberOfLaps", _INT),
        ("tyreCompound", ctypes.c_wchar * 33),
        ("replayTimeMultiplier", _FLOAT),
        ("normalizedCarPosition", _FLOAT),     # 0..1 around the lap (key for line analysis)
        ("activeCars", _INT),
        ("carCoordinates", (_FLOAT * 3) * 60),
        ("carID", _INT * 60),
        ("playerCarID", _INT),
        ("penaltyTime", _FLOAT),
        ("flag", _INT),
        ("penalty", _INT),
        ("idealLineOn", _INT),
        ("isInPitLane", _INT),
        ("surfaceGrip", _FLOAT),
        ("mandatoryPitDone", _INT),
        ("windSpeed", _FLOAT),
        ("windDirection", _FLOAT),
        # ---- ACC_EXTRA below: present on ACC, untrustworthy on plain AC ----
        # Current driver-selected aid levels (what the in-car HUD shows). These
        # are the dashboard knobs the coach can advise changing on the straight:
        # TC / ABS levels and engine map. Integers; ACC fills them, AC leaves the
        # tail zero-padded (reader clamps implausible values to "unknown").
        ("isSetupMenuVisible", _INT),
        ("mainDisplayIndex", _INT),
        ("secondaryDisplayIndex", _INT),
        ("TC", _INT),                          # current traction-control level
        ("TCCut", _INT),                       # current TC-cut (slip allowance) level
        ("EngineMap", _INT),                   # current engine map (0-based; HUD shows +1)
        ("ABS", _INT),                         # current ABS level
    ]


class SPageFileStatic(ctypes.Structure):
    """Constant for the duration of a session: car, track, limits."""

    _pack_ = 4
    _fields_ = [
        ("smVersion", ctypes.c_wchar * 15),
        ("acVersion", ctypes.c_wchar * 15),
        ("numberOfSessions", _INT),
        ("numCars", _INT),
        ("carModel", ctypes.c_wchar * 33),
        ("track", ctypes.c_wchar * 33),
        ("playerName", ctypes.c_wchar * 33),
        ("playerSurname", ctypes.c_wchar * 33),
        ("playerNick", ctypes.c_wchar * 33),
        ("sectorCount", _INT),
        ("maxTorque", _FLOAT),
        ("maxPower", _FLOAT),
        ("maxRpm", _INT),
        ("maxFuel", _FLOAT),
        ("suspensionMaxTravel", _FLOAT * 4),
        ("tyreRadius", _FLOAT * 4),
        ("maxTurboBoost", _FLOAT),
        ("deprecated_1", _FLOAT),
        ("deprecated_2", _FLOAT),
        ("penaltiesEnabled", _INT),
        ("aidFuelRate", _FLOAT),
        ("aidTireRate", _FLOAT),
        ("aidMechanicalDamage", _FLOAT),
        ("aidAllowTyreBlankets", _INT),
        ("aidStability", _FLOAT),
        ("aidAutoClutch", _INT),
        ("aidAutoBlip", _INT),
        # ---- ACC_EXTRA below ----
        ("hasDRS", _INT),
        ("hasERS", _INT),
        ("hasKERS", _INT),
        ("kersMaxJ", _FLOAT),
        ("engineBrakeSettingsCount", _INT),
        ("ersPowerControllerCount", _INT),
        ("trackSPlineLength", _FLOAT),
        ("trackConfiguration", ctypes.c_wchar * 33),
        ("ersMaxJ", _FLOAT),
        ("isTimedRace", _INT),
        ("hasExtraLap", _INT),
        ("carSkin", ctypes.c_wchar * 33),
        ("reversedGridPositions", _INT),
        ("pitWindowStart", _INT),
        ("pitWindowEnd", _INT),
        ("isOnline", _INT),
    ]
