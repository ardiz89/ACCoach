"""Reader for the AC / ACC shared memory.

Opens the three memory-mapped pages, polls them, and converts each read into a
clean :class:`TelemetrySnapshot`. Designed to be polled in a loop:

    reader = SharedMemoryReader()
    while True:
        snap = reader.read()
        ...

Why the raw Win32 API instead of the ``mmap`` module
----------------------------------------------------
On Windows, ``mmap.mmap(-1, size, tagname)`` *creates* a fresh anonymous
mapping when the named one doesn't exist instead of failing — so it would
silently report "connected" (reading zeros) while the game is closed, and it
could collide with the section the game later creates. We therefore use
``OpenFileMapping`` directly, which returns NULL when the game isn't running,
giving us honest connect/disconnect detection.

We also ``VirtualQuery`` the mapped view to learn its real size: plain Assetto
Corsa allocates a shorter region than ACC, so we read only the bytes that
actually exist and zero-pad the ACC-only tail. The mapping is opened and closed
on every read so that when the game exits we notice immediately (the kernel
keeps a section alive only while a handle is open).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from .snapshot import ACStatus, SessionType, TelemetrySnapshot, gear_label
from .structs import (
    GRAPHICS_MAP,
    PHYSICS_MAP,
    STATIC_MAP,
    SPageFileGraphics,
    SPageFilePhysics,
    SPageFileStatic,
)

# --- Win32 bindings --------------------------------------------------------
_FILE_MAP_READ = 0x0004

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_OpenFileMapping = _k32.OpenFileMappingW
_OpenFileMapping.restype = wintypes.HANDLE
_OpenFileMapping.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]

_MapViewOfFile = _k32.MapViewOfFile
_MapViewOfFile.restype = ctypes.c_void_p
_MapViewOfFile.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t,
]

_UnmapViewOfFile = _k32.UnmapViewOfFile
_UnmapViewOfFile.restype = wintypes.BOOL
_UnmapViewOfFile.argtypes = [ctypes.c_void_p]

_CloseHandle = _k32.CloseHandle
_CloseHandle.restype = wintypes.BOOL
_CloseHandle.argtypes = [wintypes.HANDLE]

_VirtualQuery = _k32.VirtualQuery
_VirtualQuery.restype = ctypes.c_size_t


class _MEMORY_BASIC_INFORMATION(ctypes.Structure):
    # Classic layout (no PartitionId); explicit padding keeps RegionSize at the
    # correct 8-byte-aligned offset on 64-bit Python.
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("__align", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("__align2", wintypes.DWORD),
    ]


_VirtualQuery.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(_MEMORY_BASIC_INFORMATION), ctypes.c_size_t,
]


class _Page:
    """A single named shared-memory page bound to a ctypes Structure type.

    Opened and closed per read for honest connection detection."""

    def __init__(self, tagname: str, struct_type: type[ctypes.Structure]) -> None:
        self._tagname = tagname
        self._struct_type = struct_type
        self._size = ctypes.sizeof(struct_type)

    def read(self) -> ctypes.Structure | None:
        handle = _OpenFileMapping(_FILE_MAP_READ, False, self._tagname)
        if not handle:
            return None  # game not running / page not published yet
        view = _MapViewOfFile(handle, _FILE_MAP_READ, 0, 0, 0)  # whole section
        if not view:
            _CloseHandle(handle)
            return None
        try:
            # How many bytes are actually mapped (AC < ACC).
            mbi = _MEMORY_BASIC_INFORMATION()
            _VirtualQuery(ctypes.c_void_p(view), ctypes.byref(mbi), ctypes.sizeof(mbi))
            available = int(mbi.RegionSize) if mbi.RegionSize else self._size
            n = min(self._size, available)
            raw = ctypes.string_at(view, n)
            if n < self._size:
                raw += b"\x00" * (self._size - n)  # zero-pad ACC-only tail on AC
            return self._struct_type.from_buffer_copy(raw)
        except OSError:
            return None
        finally:
            _UnmapViewOfFile(ctypes.c_void_p(view))
            _CloseHandle(handle)

    def close(self) -> None:  # nothing persistent to release
        pass


class SharedMemoryReader:
    """Polls all three AC/ACC pages and yields normalized snapshots."""

    def __init__(self) -> None:
        self._physics = _Page(PHYSICS_MAP, SPageFilePhysics)
        self._graphics = _Page(GRAPHICS_MAP, SPageFileGraphics)
        self._static = _Page(STATIC_MAP, SPageFileStatic)

    def read(self) -> TelemetrySnapshot:
        phys = self._physics.read()
        graph = self._graphics.read()
        stat = self._static.read()

        if phys is None or graph is None or stat is None:
            return TelemetrySnapshot.disconnected()

        return self._to_snapshot(phys, graph, stat)

    @staticmethod
    def _to_snapshot(
        p: SPageFilePhysics,
        g: SPageFileGraphics,
        s: SPageFileStatic,
    ) -> TelemetrySnapshot:
        try:
            status = ACStatus(g.status)
        except ValueError:
            status = ACStatus.OFF
        try:
            session = SessionType(g.session)
        except ValueError:
            session = SessionType.UNKNOWN

        return TelemetrySnapshot(
            connected=True,
            status=status,
            session=session,
            car_model=s.carModel,
            track=s.track,
            throttle=p.gas,
            brake=p.brake,
            clutch=p.clutch,
            steer_angle=p.steerAngle,
            gear=gear_label(p.gear),
            rpm=p.rpms,
            max_rpm=s.maxRpm,
            speed_kmh=p.speedKmh,
            accel_g=(p.accG[0], p.accG[1], p.accG[2]),
            yaw_rate=p.localAngularVel[1],
            wheel_slip=(p.wheelSlip[0], p.wheelSlip[1], p.wheelSlip[2], p.wheelSlip[3]),
            slip_ratio=SharedMemoryReader._slip_ratio(p, s),
            tyre_core_temp=(
                p.tyreCoreTemperature[0],
                p.tyreCoreTemperature[1],
                p.tyreCoreTemperature[2],
                p.tyreCoreTemperature[3],
            ),
            tyre_pressure=(
                p.wheelsPressure[0],
                p.wheelsPressure[1],
                p.wheelsPressure[2],
                p.wheelsPressure[3],
            ),
            brake_temp=(p.brakeTemp[0], p.brakeTemp[1], p.brakeTemp[2], p.brakeTemp[3]),
            abs_active=p.abs,
            tc_active=p.tc,
            tc_level=SharedMemoryReader._aid_level(g.TC),
            abs_level=SharedMemoryReader._aid_level(g.ABS),
            engine_map=SharedMemoryReader._aid_level(g.EngineMap),
            brake_bias=SharedMemoryReader._brake_bias(p.brakeBias),
            current_lap_ms=g.iCurrentTime,
            last_lap_ms=g.iLastTime,
            best_lap_ms=g.iBestTime,
            completed_laps=g.completedLaps,
            lap_position=g.normalizedCarPosition,
            fuel=p.fuel,
            in_pit=bool(g.isInPit),
            current_sector=SharedMemoryReader._sector_index(g.currentSectorIndex),
            sector_count=s.sectorCount if 0 < s.sectorCount <= 30 else 0,
            **SharedMemoryReader._car_xz(g),
        )

    # A track has at most a handful of sectors; reject garbage indices (cold
    # frames / AC content without sectors) as "unknown" so they don't fake a
    # sector boundary.
    @staticmethod
    def _sector_index(raw: int) -> int:
        return raw if 0 <= raw < 30 else -1

    @staticmethod
    def _car_xz(g: SPageFileGraphics) -> dict:
        """Player's world ground-plane position (X, Z) for the track map.

        The two games lay the graphics page out differently right here:

        * **ACC** has ``activeCars`` (int) followed by ``carCoordinates[60][3]``
          indexed by ``playerCarID`` — exactly what our struct declares. The
          player's position is ``carCoordinates[playerCarID] = (x, y, z)``.
        * **AC1** has *no* ``activeCars`` and ``carCoordinates`` is just the
          player's own ``float[3]``, so the whole triple sits 4 bytes earlier:
          x at the ``activeCars`` offset, then y, then z. Reading it ACC-style
          gives ``(y, z, garbage)`` — i.e. car_x became the elevation and car_z
          read a zero (validated live 2026-06-28 on a Ferrari SF25 @ Nürburgring:
          the real X/Z were at offsets 252/260, not 256/264).

        We tell them apart by ``activeCars``: ACC fills it with a real car count
        (1..60); on AC1 that slot holds the X coordinate as a float, whose int
        reinterpretation is always far outside that range.
        """
        if 0 < g.activeCars <= 60:                       # ACC layout
            idx = g.playerCarID if 0 <= g.playerCarID < 60 else 0
            c = g.carCoordinates[idx]
            return {"car_x": float(c[0]), "car_z": float(c[2])}

        # AC1 layout: the player's (x, y, z) starts at the activeCars offset.
        base = ctypes.addressof(g) + SPageFileGraphics.activeCars.offset
        car_x = ctypes.c_float.from_address(base + 0).value     # offset 252
        car_z = ctypes.c_float.from_address(base + 8).value     # offset 260 (skip y)
        return {"car_x": float(car_x), "car_z": float(car_z)}

    # Adjustable-aid levels come from the ACC-only graphics tail; on plain AC
    # that region is zero-padded and the raw struct can also carry garbage on a
    # cold first frame. Accept only a sane range and otherwise report "unknown"
    # (-1) so the coach degrades to directional advice instead of nonsense.
    _AID_LEVEL_MAX = 20

    @staticmethod
    def _aid_level(raw: int) -> int:
        return raw if 0 <= raw <= SharedMemoryReader._AID_LEVEL_MAX else -1

    @staticmethod
    def _brake_bias(raw: float) -> float:
        # ACC reports front bias as a fraction; values outside a plausible band
        # mean we're on AC (tail garbage) or it's otherwise untrustworthy.
        return raw if 0.1 <= raw <= 0.9 else -1.0

    # Below this car speed (m/s) the slip ratio isn't meaningful (division blows
    # up at a crawl), so we report zero. ~11 km/h.
    _SLIP_MIN_SPEED_MS = 3.0

    @staticmethod
    def _slip_ratio(
        p: SPageFilePhysics, s: SPageFileStatic,
    ) -> tuple[float, float, float, float]:
        """Physical per-wheel slip ratio: (wheel surface speed - car speed) / car speed.

        Negative => wheel turning slower than the ground (locking under braking);
        positive => faster (wheelspin). Car-agnostic, so no per-car calibration.
        """
        v = p.speedKmh / 3.6
        if v < SharedMemoryReader._SLIP_MIN_SPEED_MS:
            return (0.0, 0.0, 0.0, 0.0)
        out = []
        for i in range(4):
            radius = s.tyreRadius[i]
            if radius <= 0.0:
                out.append(0.0)
                continue
            wheel_v = p.wheelAngularSpeed[i] * radius
            out.append((wheel_v - v) / v)
        return (out[0], out[1], out[2], out[3])

    def close(self) -> None:
        self._physics.close()
        self._graphics.close()
        self._static.close()

    def __enter__(self) -> "SharedMemoryReader":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
