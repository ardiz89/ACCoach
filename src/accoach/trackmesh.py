"""La strada, presa dal modello di collisione di Assetto Corsa.

`trackedges.py` legge la linea dell'IA e le sue distanze dai bordi. Serve, ma
per **disegnare** la pista non basta, e il 2026-07-31 si è visto perché: quelle
distanze sono misurate **perpendicolarmente alla linea dell'IA**, e dove l'IA
taglia una variante il piede della perpendicolare non cade sul punto giusto del
bordo. Quello che ne esce è il *corridoio attorno alla traiettoria dell'IA*, non
la strada — e la Variante del Rettifilo si disegnava come una esse morbida
invece che come il flick secco che è.

Qui la strada arriva da dove è davvero: le **mesh delle superfici**. Ogni pezzo
di pista è una mesh nominata con la convenzione di `surfaces.ini` —
``<cifre><CHIAVE>_<resto>``, con CHIAVE fra ASPH, ROAD, CURB, KERB, GRASS, SAND,
CONCRETE, WALL. A Monza sono 329 mesh e oltre 400.000 triangoli d'asfalto.

**Dove stiano non è una regola**, ed è l'errore che questa prima versione ha
fatto: su Monza, Spa, il Nürburgring e Bathurst c'è un modello a parte, piccolo,
di sola geometria; su Imola e Suzuka le stesse mesh vivono dentro il modello
visivo da centinaia di MB, in mezzo a ``Object112`` e ``bush767``. Quindi il file
non si indovina dal nome né dalla dimensione: si aprono in ordine di peso e si
tiene il primo che **contiene** superfici.

Misurato prima di costruirci sopra: posando il modello con lo stesso fit di
`trackedges`, **la linea guidata sta a 0.34 m dal vertice d'asfalto più vicino**
(p95 1.26 m). Il dato satellitare impacchettato, sullo stesso giro, ne dava 7-14:
è un altro campionato, perché queste sono le coordinate del gioco — le stesse in
cui è stato registrato il giro.

Cosa NON fa, per scelta:

* non prova a indovinare quale file contenga le superfici: lo **riconosce**,
  contando quante mesh seguono la convenzione — chi ne ha, ne ha decine; chi non
  ne ha, ne ha zero;
* non manda triangoli al browser. Attorno a una sola curva ce ne sono ventimila.
  Manda il **contorno** della superficie, ricavato per rasterizzazione — che
  risolve gratis anche le cuciture fra mesh adiacenti, perché due pezzi
  affiancati non condividono i vertici ma coprono celle contigue.
"""

from __future__ import annotations

import math
import re
import struct
from array import array
from pathlib import Path

# --- il formato ---------------------------------------------------------------
# kn5: magia "sc6969", versione, [extra], texture, materiali, poi l'albero dei
# nodi. Vertice = posizione(12) + normale(12) + uv(8) + tangente(12).
_MAGIC = b"sc6969"
_VERTEX = 44

#: Le chiavi di `surfaces.ini` che ci interessano, raggruppate per come si
#: disegnano. Tutto il resto (erba, sabbia, muri) resta fuori: e' terreno che
#: non stiamo ancora dicendo di conoscere.
_CLASSES = {
    "road": ("ASPH", "ROAD", "TARMAC"),
    "kerb": ("CURB", "KERB"),
}

#: Quante mesh nominate come superfici servono perche' il file sia quello buono.
#:
#: In PROPORZIONE non funziona, e la prima versione sbagliava proprio li': non
#: tutte le piste tengono le superfici in un file a parte. Misurato:
#:
#:   monza/2.kn5           329 mesh, 328 di superficie   modello dedicato
#:   spa/3.kn5             456 mesh,  33                 modello dedicato
#:   bathurst_mesh.kn5     166 mesh,  74                 modello dedicato
#:   imola.kn5            1239 mesh, 375                 dentro quello VISIVO
#:   suzuka.kn5            870 mesh, 162                 dentro quello VISIVO
#:   tutti gli altri                    0
#:
#: Chi ne ha, ne ha decine; chi non ne ha, ne ha zero. Fra 0 e 74 non c'e'
#: niente, quindi la soglia serve solo a dire "questo no".
_PHYS_MESHES = 12


class _Reader:
    def __init__(self, f):
        self.f = f

    def i(self) -> int:
        return struct.unpack("<i", self.f.read(4))[0]

    def s(self) -> str:
        n = self.i()
        if n < 0 or n > 1 << 20:
            raise ValueError(f"stringa di {n} byte: non e' un kn5")
        return self.f.read(n).decode("utf-8", "replace")


def _surface_key(name: str) -> str:
    m = re.match(r"^\d*([A-Za-z][A-Za-z0-9\-]*)", name or "")
    return m.group(1).upper() if m else ""


def _class_of(name: str) -> str | None:
    key = _surface_key(name)
    for cls, words in _CLASSES.items():
        if any(w in key for w in words):
            return cls
    return None


def _walk(path: Path, collect: bool):
    """Percorre un kn5. Con ``collect`` raccoglie i triangoli, altrimenti conta.

    Un solo percorso per due domande, perche' saltare i vertici richiede
    comunque di leggere tutto il resto: chiedere "e' il modello fisico?" e
    "dammi la strada" con due funzioni diverse vorrebbe dire due parser.
    """
    with path.open("rb") as f:
        r = _Reader(f)
        if f.read(6) != _MAGIC:
            return None
        ver = r.i()
        if ver > 5:
            r.i()
        for _ in range(r.i()):                      # texture
            r.i(); r.s()
            f.seek(r.i(), 1)
        for _ in range(r.i()):                      # materiali
            r.s(); r.s(); f.read(2)
            if ver > 4:
                r.i()
            for _ in range(r.i()):
                r.s(); f.read(4 + 8 + 12 + 16)
            for _ in range(r.i()):
                r.s(); r.i(); r.s()

        named = total = 0
        out = {cls: array("f") for cls in _CLASSES}
        todo = [None]
        while todo:
            todo.pop()
            ntype = r.i()
            name = r.s()
            nchild = r.i()
            f.read(1)
            if ntype == 1:
                f.read(64)
            elif ntype in (2, 3):
                f.read(3)
                if ntype == 3:
                    for _ in range(r.i()):
                        r.s(); f.read(64)
                nv = r.i()
                total += 1
                cls = _class_of(name)
                if cls:
                    named += 1
                if collect and cls:
                    blob = f.read(nv * _VERTEX)
                    ni = r.i()
                    idx = struct.unpack(f"<{ni}H", f.read(ni * 2))
                    # Solo pianta: la terza dimensione e' la quota, e la strada
                    # si guarda da sopra.
                    vs = [struct.unpack_from("<3f", blob, k * _VERTEX) for k in range(nv)]
                    dst = out[cls]
                    for a in range(0, ni - 2, 3):
                        for k in (idx[a], idx[a + 1], idx[a + 2]):
                            dst.append(vs[k][0]); dst.append(vs[k][2])
                else:
                    f.seek(nv * _VERTEX, 1)
                    ni = r.i()
                    f.seek(ni * 2, 1)
                r.i(); f.read(12)
                if ntype == 2:
                    f.read(16)
                    f.read(1)
            else:
                raise ValueError(f"nodo di tipo {ntype} a {name!r}")
            todo.extend([None] * nchild)
        return {"named": named, "total": total, "tris": out}


def is_physics_model(path: Path) -> bool:
    """Questo kn5 descrive superfici, o e' quello che si guarda?"""
    try:
        got = _walk(path, collect=False)
    except (OSError, ValueError, struct.error):
        return False
    return bool(got) and got["named"] >= _PHYS_MESHES


def physics_model(track: str) -> Path | None:
    """Il modello di collisione della pista installata, o None."""
    from .trackedges import spline_path

    spline = spline_path(track)
    if spline is None:
        return None
    folder = spline.parent.parent            # .../<pista>[/<layout>]/ai/..
    seen: list[Path] = []
    for d in (folder, folder.parent):
        seen += sorted(d.glob("*.kn5"))
        if d == folder.parent:
            break
    # I piccoli per primi: il modello fisico e' geometria e basta, quello visivo
    # porta centinaia di MB di texture. Provare prima i grandi vuol dire leggere
    # mezzo giga per scoprire che non era quello.
    for p in sorted(dict.fromkeys(seen), key=lambda p: p.stat().st_size):
        if is_physics_model(p):
            return p
    return None


_cache: dict[str, dict[str, array] | None] = {}


def surfaces(track: str) -> dict[str, array] | None:
    """{"road": [x,z,x,z,...], "kerb": [...]} — tre vertici per triangolo."""
    key = (track or "").lower()
    if key not in _cache:
        path = physics_model(track)
        got = _walk(path, collect=True) if path else None
        _cache[key] = got["tris"] if got else None
    return _cache[key]


# --- dal mucchio di triangoli al contorno --------------------------------------

#: Lato della cella, in metri. A 0.5 m il contorno di un cordolo largo 1.5 m ha
#: comunque tre celle di spessore, e una curva intera sta in poche decine di
#: migliaia di celle — il conto si fa in millisecondi.
_CELL = 0.5

#: Quanto semplificare il contorno prima di mandarlo. 0.35 m e' sotto la
#: risoluzione della griglia: toglie i gradini della rasterizzazione senza
#: spostare un bordo di quanto si veda.
_SIMPLIFY_M = 0.35


def _raster(tris: array, x0: float, z0: float, nx: int, nz: int) -> bytearray:
    """Segna le celle coperte dai triangoli. Scanline, un triangolo alla volta."""
    grid = bytearray(nx * nz)
    n = len(tris)
    for t in range(0, n - 5, 6):
        ax, az = tris[t], tris[t + 1]
        bx, bz = tris[t + 2], tris[t + 3]
        cx, cz = tris[t + 4], tris[t + 5]
        lo_j = int((min(az, bz, cz) - z0) / _CELL)
        hi_j = int((max(az, bz, cz) - z0) / _CELL)
        if hi_j < 0 or lo_j >= nz:
            continue
        lo_i = int((min(ax, bx, cx) - x0) / _CELL)
        hi_i = int((max(ax, bx, cx) - x0) / _CELL)
        if hi_i < 0 or lo_i >= nx:
            continue
        d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
        if d == 0.0:
            continue
        for j in range(max(0, lo_j), min(nz - 1, hi_j) + 1):
            pz = z0 + (j + 0.5) * _CELL
            row = j * nx
            for i in range(max(0, lo_i), min(nx - 1, hi_i) + 1):
                px = x0 + (i + 0.5) * _CELL
                w1 = ((bz - cz) * (px - cx) + (cx - bx) * (pz - cz)) / d
                if w1 < 0.0 or w1 > 1.0:
                    continue
                w2 = ((cz - az) * (px - cx) + (ax - cx) * (pz - cz)) / d
                if w2 < 0.0 or w1 + w2 > 1.0:
                    continue
                grid[row + i] = 1
    return grid


def _contours(grid: bytearray, nx: int, nz: int, x0: float, z0: float) -> list[list]:
    """Il bordo delle celle segnate, come anelli chiusi (marching squares).

    Prende i lati fra una cella piena e una vuota e li cuce. Cosi' due mesh
    affiancate — che NON condividono i vertici, e il cui bordo geometrico
    avrebbe una cucitura in mezzo alla strada — danno un contorno solo.
    """
    edges: dict[tuple, tuple] = {}

    def add(a, b):
        edges[a] = b

    for j in range(nz):
        row = j * nx
        for i in range(nx):
            if not grid[row + i]:
                continue
            # Lati verso un vicino vuoto, orientati in senso antiorario.
            if i == 0 or not grid[row + i - 1]:
                add((i, j + 1), (i, j))
            if i == nx - 1 or not grid[row + i + 1]:
                add((i + 1, j), (i + 1, j + 1))
            if j == 0 or not grid[row - nx + i]:
                add((i, j), (i + 1, j))
            if j == nz - 1 or not grid[row + nx + i]:
                add((i + 1, j + 1), (i, j + 1))

    rings = []
    while edges:
        start = next(iter(edges))
        ring = [start]
        cur = start
        while True:
            nxt = edges.pop(cur, None)
            if nxt is None or nxt == start:
                break
            ring.append(nxt)
            cur = nxt
        if len(ring) >= 8:
            rings.append([[x0 + p[0] * _CELL, z0 + p[1] * _CELL] for p in ring])
    return rings


def _simplify(pts: list, tol: float) -> list:
    """Douglas-Peucker, iterativo: una curva puo' avere migliaia di punti e la
    ricorsione su una pila di quelle dimensioni non e' un rischio da correre."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, az = pts[a]
        bx, bz = pts[b]
        dx, dz = bx - ax, bz - az
        norm = math.hypot(dx, dz) or 1.0
        worst, at = -1.0, -1
        for k in range(a + 1, b):
            px, pz = pts[k]
            d = abs(dz * (px - ax) - dx * (pz - az)) / norm
            if d > worst:
                worst, at = d, k
        if worst > tol:
            keep[at] = True
            stack.append((a, at))
            stack.append((at, b))
    return [p for p, k in zip(pts, keep) if k]


def road_shapes(track: str, xz, at=None, pad: float = 22.0,
                max_span: float = 700.0) -> dict | None:
    """Asfalto e cordoli attorno a un tratto guidato, come anelli da riempire.

    ``xz`` e' il tratto in coordinate del **giro**; ``at`` e' il fit che porta il
    modello in quelle coordinate (da `trackedges.fit`). Il ritaglio si fa nelle
    coordinate del modello — ci si va con l'inverso del fit — perche' e' li' che
    stanno i quattrocentomila triangoli, e trasformarli tutti per poi buttarne
    il 99% sarebbe lavoro pagato due volte.
    """
    tris = surfaces(track)
    if not tris or not xz:
        return None
    inv = at.inverse() if at is not None else None
    pts = [inv.apply(x, z) for x, z in xz] if inv else list(xz)
    x0 = min(p[0] for p in pts) - pad
    x1 = max(p[0] for p in pts) + pad
    z0 = min(p[1] for p in pts) - pad
    z1 = max(p[1] for p in pts) + pad
    # Una finestra grande come mezzo circuito non e' una curva: e' un ritaglio
    # andato storto, e rasterizzarla costerebbe secondi per un disegno inutile.
    if (x1 - x0) > max_span or (z1 - z0) > max_span:
        return None
    nx = max(4, int((x1 - x0) / _CELL) + 1)
    nz = max(4, int((z1 - z0) / _CELL) + 1)

    out = {}
    for cls, flat in tris.items():
        near = array("f")
        for t in range(0, len(flat) - 5, 6):
            if (x0 <= flat[t] <= x1 and z0 <= flat[t + 1] <= z1) or \
               (x0 <= flat[t + 2] <= x1 and z0 <= flat[t + 3] <= z1) or \
               (x0 <= flat[t + 4] <= x1 and z0 <= flat[t + 5] <= z1):
                near.extend(flat[t:t + 6])
        if not near:
            continue
        rings = _contours(_raster(near, x0, z0, nx, nz), nx, nz, x0, z0)
        shapes = []
        for ring in rings:
            ring = _simplify(ring, _SIMPLIFY_M)
            if len(ring) < 4:
                continue
            if at is not None:
                ring = [list(at.apply(p[0], p[1])) for p in ring]
            shapes.append([[round(p[0], 2), round(p[1], 2)] for p in ring])
        if shapes:
            out[cls] = shapes
    return out or None
