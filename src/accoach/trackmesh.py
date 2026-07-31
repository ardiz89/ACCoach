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
  Manda il **contorno** della superficie: i lati usati da un solo triangolo,
  cuciti in anelli.
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

#: Le chiavi di `surfaces.ini` raggruppate per come si disegnano. I nomi veri
#: portano prefissi numerici e suffissi (``07GRASS001``), quindi il confronto e'
#: per sottostringa. Censite sui sei modelli installati: ASPH-SPA, MONZA-ASPH,
#: TARMAC-IMA, ROAD, GRASS001, SAND002, CONCRETE, CARPET, KERB003, CURB006...
#:
#: Le vie di fuga servono a rispondere alla domanda che il nastro da solo non
#: chiudeva: **dove finisce la pista e comincia il resto**. Nei dati del gioco e'
#: una distinzione esplicita — l'asfalto di fuga di La Source e' `ASPH` come la
#: pista, ma l'erba e la ghiaia che lo circondano no.
#:
#: Fuori restano i muri (geometria verticale: in pianta sono un filo) e `OUT` /
#: `OFFTRACK`, che non sono materiali ma verdetti, e si sovrappongono agli altri.
_CLASSES = {
    "road": ("ASPH", "ROAD", "TARMAC"),
    "kerb": ("CURB", "KERB"),
    "grass": ("GRASS", "CARPET"),
    "gravel": ("SAND", "GRAVEL", "DIRT"),
    "concrete": ("CONCRETE", "ILLCONC", "CNC"),
}

#: L'ordine in cui vanno disegnate: quello in cui stanno per terra. La pista
#: sopra le sue vie di fuga, i cordoli sopra la pista.
DRAW_ORDER = ("grass", "gravel", "concrete", "road", "kerb")

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


# Una sola voce per pista, con dentro TUTTO quello che si e' ricavato dal file:
# i triangoli e l'indice per trovarli. Tenerli in due cache separate e' costato
# subito un IndexError — svuotarne una lasciava l'altra a indicare offset di una
# geometria che non c'era piu'.
_cache: dict[str, dict | None] = {}

#: Lato delle caselle dell'indice. Una curva ne tocca una manciata, e ogni
#: casella tiene qualche centinaio di triangoli. Senza, ogni curva scorreva tutti
#: e quattrocentomila: cinque secondi a pista, e li' dentro non c'era niente di
#: difficile — solo il novantacinque per cento di lavoro buttato.
_BUCKET_M = 40.0


def _loaded(track: str) -> dict | None:
    key = (track or "").lower()
    if key not in _cache:
        path = physics_model(track)
        got = _walk(path, collect=True) if path else None
        if not got:
            _cache[key] = None
        else:
            tris = got["tris"]
            grid = {}
            for cls, flat in tris.items():
                g: dict[tuple, list] = {}
                for t in range(0, len(flat) - 5, 6):
                    xs = (flat[t], flat[t + 2], flat[t + 4])
                    zs = (flat[t + 1], flat[t + 3], flat[t + 5])
                    for i in range(int(min(xs) // _BUCKET_M), int(max(xs) // _BUCKET_M) + 1):
                        for j in range(int(min(zs) // _BUCKET_M), int(max(zs) // _BUCKET_M) + 1):
                            g.setdefault((i, j), []).append(t)
                grid[cls] = g
            _cache[key] = {"tris": tris, "grid": grid}
    return _cache[key]


def surfaces(track: str) -> dict[str, array] | None:
    """{"road": [x,z,x,z,...], "kerb": [...]} — tre vertici per triangolo."""
    got = _loaded(track)
    return got["tris"] if got else None


# --- dal mucchio di triangoli al contorno --------------------------------------
#
# Il bordo di una superficie sono i lati che appartengono a **un solo**
# triangolo. Detta cosi' e' ovvia; il dubbio era un altro, e cioe' se i pezzi di
# pista si tocchino davvero — se due mesh affiancate avessero vertici diversi
# sul confine, ogni giunzione diventerebbe un finto bordo in mezzo alla strada.
#
# Misurato attorno alla Variante del Rettifilo: **18.473 triangoli, 28.168 lati,
# 917 di bordo — il 3%**. E arrotondare i vertici a 1 o a 5 cm non cambia
# nemmeno un lato: le mesh combaciano esattamente. Il timore era infondato.
#
# La prima versione rasterizzava a mezzo metro per aggirare quel problema che
# non c'era, e si vedeva: a un decimo di millimetro per pixel un gradino da 50 cm
# e' spesso quattro pixel, e la pista usciva scalettata.

#: Quanto semplificare l'anello prima di mandarlo. 12 cm e' sotto lo spessore
#: della linea con cui viene disegnato: toglie i vertici che il modello mette
#: per ragioni sue senza spostare un bordo di quanto si veda.
_SIMPLIFY_M = 0.12

#: Un anello piu' corto di cosi' e' un ritaglio, non un pezzo di pista.
_MIN_RING = 4


def _boundary(tris: array, offsets, keep) -> list[list]:
    """Gli anelli di bordo dei triangoli indicati che passano ``keep``."""
    edges: dict[tuple, int] = {}
    for t in offsets:
        a = (round(tris[t], 3), round(tris[t + 1], 3))
        b = (round(tris[t + 2], 3), round(tris[t + 3], 3))
        c = (round(tris[t + 4], 3), round(tris[t + 5], 3))
        if not keep(a, b, c):
            continue
        for p, q in ((a, b), (b, c), (c, a)):
            key = (p, q) if p <= q else (q, p)
            edges[key] = edges.get(key, 0) + 1

    # Da ogni vertice partono i lati di bordo che lo toccano. Un vertice puo'
    # averne piu' di due (due pezzi che si sfiorano in un punto), quindi la
    # cucitura consuma i lati invece di seguire un "prossimo" fisso.
    at: dict[tuple, list] = {}
    for (p, q), n in edges.items():
        if n != 1:
            continue
        at.setdefault(p, []).append(q)
        at.setdefault(q, []).append(p)

    rings = []
    while at:
        start = next(iter(at))
        ring = [start]
        cur, prev = start, None
        while True:
            opts = at.get(cur)
            if not opts:
                break
            nxt = next((o for o in opts if o != prev), opts[0])
            opts.remove(nxt)
            if not opts:
                at.pop(cur, None)
            back = at.get(nxt)
            if back and cur in back:
                back.remove(cur)
                if not back:
                    at.pop(nxt, None)
            if nxt == start:
                break
            ring.append(nxt)
            prev, cur = cur, nxt
        if len(ring) >= _MIN_RING:
            rings.append([list(p) for p in ring])
    return rings


def _clip(ring: list, x0: float, z0: float, x1: float, z1: float) -> list:
    """Taglia un anello sul rettangolo della finestra (Sutherland-Hodgman).

    Serve perche' i triangoli si tengono per intero: senza, il bordo del disegno
    seguirebbe i denti dei triangoli tagliati invece di una riga dritta.
    """
    def half(pts, inside, cross):
        out = []
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            ia, ib = inside(a), inside(b)
            if ia:
                out.append(a)
            if ia != ib:
                out.append(cross(a, b))
        return out

    def cx(v):
        return lambda a, b: [v, a[1] + (b[1] - a[1]) * (v - a[0]) / (b[0] - a[0])]             if b[0] != a[0] else [v, a[1]]

    def cz(v):
        return lambda a, b: [a[0] + (b[0] - a[0]) * (v - a[1]) / (b[1] - a[1]), v]             if b[1] != a[1] else [a[0], v]

    pts = ring
    for inside, cross in ((lambda p: p[0] >= x0, cx(x0)), (lambda p: p[0] <= x1, cx(x1)),
                          (lambda p: p[1] >= z0, cz(z0)), (lambda p: p[1] <= z1, cz(z1))):
        if not pts:
            return []
        pts = half(pts, inside, cross)
    return pts


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
    stanno i quattrocentomila triangoli, e trasformarli tutti per poi buttarne il
    novantanove per cento sarebbe lavoro pagato due volte.
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
    # andato storto, e nessun disegno utile ne uscirebbe.
    if (x1 - x0) > max_span or (z1 - z0) > max_span:
        return None

    def keep(a, b, c):
        # Il triangolo si tiene INTERO se tocca la finestra: tagliarlo qui
        # lascerebbe denti, e il taglio dritto lo fa `_clip` sull'anello.
        return (max(a[0], b[0], c[0]) >= x0 and min(a[0], b[0], c[0]) <= x1 and
                max(a[1], b[1], c[1]) >= z0 and min(a[1], b[1], c[1]) <= z1)

    grids = _loaded(track)["grid"]
    out = {}
    for cls, flat in tris.items():
        grid = grids.get(cls, {})
        offs = set()
        for i in range(int(x0 // _BUCKET_M), int(x1 // _BUCKET_M) + 1):
            for j in range(int(z0 // _BUCKET_M), int(z1 // _BUCKET_M) + 1):
                offs.update(grid.get((i, j), ()))
        if not offs:
            continue
        shapes = []
        for ring in _boundary(flat, sorted(offs), keep):
            ring = _clip(ring, x0, z0, x1, z1)
            ring = _simplify(ring, _SIMPLIFY_M)
            if len(ring) < _MIN_RING:
                continue
            if at is not None:
                ring = [list(at.apply(p[0], p[1])) for p in ring]
            shapes.append([[round(p[0], 2), round(p[1], 2)] for p in ring])
        if shapes:
            out[cls] = shapes
    return out or None
