"""Il modello grafico di una pista di AC, letto in array.

`trackmesh.py` legge del kn5 solo le mesh delle superfici, in pianta. Per
disegnare la pista come la si vede nel gioco serve di piu', e lo spike del
2026-11-06 sul Monza ha detto cosa:

* le **matrici dei nodi** di tipo 1 vanno applicate. Il modello fisico non ne
  aveva bisogno, quello visivo si'. Convenzione a vettore riga:
  ``pos_mondo = [x, y, z, 1] @ M_nodo @ M_padre``;
* le **texture** si indicizzano per offset e non si leggono: `monza.kn5` pesa
  316 MB, quasi tutti di immagini. `texture_bytes` le prende una alla volta;
* i **triangoli verticali** (muri, alberi a sagoma, facce delle tribune) in
  pianta non coprono niente. Sul Monza intero erano 409.000 su circa 487.000:
  si scartano subito, prima di tenerli in memoria;
* le mesh con le ossa (tipo 3) si saltano. Il loro vertice pesa 76 byte, non
  44: pesi e indici delle ossa dopo la tangente. Misurato su
  `content/driver/driver.kn5`, che con 76 si percorre fino all'ultimo byte e
  con 44 no.

Sola lettura. Un file che non torna e' un ``ValueError`` (o un ``OSError`` se
non si apre), mai un'eccezione d'altro tipo: chi chiama lascia la mappa com'e'.
"""
from __future__ import annotations

import math
import os
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .trackmesh import _MAGIC, _VERTEX, _Reader

#: Vertice di una mesh con le ossa: i 44 byte normali, piu' 4 pesi e 4 indici.
_SKIN_VERTEX = 76

#: Sotto questa frazione fra area in pianta e area vera un triangolo e' un
#: muro: a 0,02 la faccia e' entro un grado e poco dalla verticale.
_FLAT_MIN = 0.02


@dataclass(frozen=True)
class Material:
    name: str
    shader: str
    blend: int
    alpha_test: bool
    #: La texture dello slot `txDiffuse`, se c'e'.
    diffuse: str | None


@dataclass
class Model:
    path: Path
    tris: np.ndarray            # float32 (N, 3, 3), xyz nel mondo
    uv: np.ndarray              # float32 (N, 3, 2)
    mat: np.ndarray             # int32 (N,), indice in `materials` o -1
    mesh: np.ndarray            # int32 (N,), indice in `mesh_names`
    mesh_names: list[str] = field(default_factory=list)
    materials: list[Material] = field(default_factory=list)
    #: nome -> (offset, lunghezza) dei byte della texture nel file
    textures: dict[str, tuple[int, int]] = field(default_factory=dict)


def _placement(position, rotation_deg) -> np.ndarray:
    """La matrice (vettore riga) di `position` e `rotation` di `models.ini`.

    Rotazione in gradi attorno a Y, poi X, poi Z (yaw, pitch, roll), col segno
    per cui (90, 0, 0) porta (1, 0, 0) in (0, 0, -1). E' la regola decisa nel
    piano: sul Monza tutte le rotazioni sono zero, quindi la' non si puo'
    misurare. Poi la traslazione.
    """
    yaw, pitch, roll = (math.radians(float(a)) for a in rotation_deg)

    def rot(axis, a):
        c, s = math.cos(a), math.sin(a)
        m = np.eye(4)
        i, j = {"y": (2, 0), "x": (1, 2), "z": (0, 1)}[axis]
        # La rotazione destrorsa a colonna, trasposta per il vettore riga
        # (p' = p @ m): attorno a Y, x' = x cos + z sin e z' = z cos - x sin.
        m[i, i] = c; m[i, j] = s
        m[j, i] = -s; m[j, j] = c
        return m

    out = rot("y", yaw) @ rot("x", pitch) @ rot("z", roll)
    out[3, :3] = [float(v) for v in position]
    return out


def read(path: Path, position=(0, 0, 0), rotation_deg=(0, 0, 0)) -> Model:
    """Legge un kn5 grafico (o di collisione) coi nodi gia' messi al loro posto."""
    path = Path(path)
    try:
        return _read(path, _placement(position, rotation_deg))
    except (struct.error, MemoryError) as e:
        # Un file tronco o che mente sulle misure: per chi chiama e' un file rotto.
        raise ValueError(f"{path.name}: non e' un kn5 leggibile ({e})") from e


def _read(path: Path, place: np.ndarray) -> Model:
    textures: dict[str, tuple[int, int]] = {}
    materials: list[Material] = []
    tris, uvs, mats, meshes = [], [], [], []
    mesh_names: list[str] = []
    with path.open("rb") as f:
        r = _Reader(f, os.fstat(f.fileno()).st_size)
        if f.read(6) != _MAGIC:
            raise ValueError(f"{path.name}: non e' un kn5")
        ver = r.i()
        if ver > 5:
            r.i()
        for _ in range(r.need(r.i(), 12)):          # texture: si indicizzano
            r.i()
            name = r.s()
            n = r.need(r.i(), 1)
            textures[name] = (f.tell(), n)
            f.seek(n, 1)
        for _ in range(r.need(r.i(), 14)):          # materiali
            name, shader = r.s(), r.s()
            flags = f.read(2)
            if len(flags) != 2:
                raise ValueError("materiale tronco: non e' un kn5")
            if ver > 4:
                r.i()
            for _ in range(r.need(r.i(), 44)):      # proprieta': nome, float, 36 byte
                r.s(); f.seek(40, 1)
            diffuse = None
            for _ in range(r.need(r.i(), 12)):      # mappe: slot, int, texture
                slot = r.s(); r.i(); tex = r.s()
                if slot == "txDiffuse":
                    diffuse = tex
            materials.append(Material(name, shader, flags[0], bool(flags[1]), diffuse))

        # L'albero dei nodi senza ricorsione: una pila di (matrice, figli che
        # restano). Ogni livello costa byte del file, quindi la pila non cresce
        # piu' di quanto il file sia lungo.
        stack = [[place, 1]]
        while stack:
            top = stack[-1]
            if top[1] == 0:
                stack.pop()
                continue
            top[1] -= 1
            parent = top[0]
            ntype = r.i()
            name = r.s()
            nchild = r.need(r.i(), 13)              # un nodo pesa almeno 13 byte
            f.seek(1, 1)
            if ntype == 1:
                raw = f.read(64)
                if len(raw) != 64:
                    raise ValueError("matrice tronca: non e' un kn5")
                m = np.array(struct.unpack("<16f", raw), dtype=np.float64).reshape(4, 4)
                if not np.isfinite(m).all():
                    raise ValueError(f"matrice non finita in {name!r}")
                if nchild:
                    stack.append([m @ parent, nchild])
                continue
            if ntype not in (2, 3):
                raise ValueError(f"nodo di tipo {ntype} a {name!r}")
            f.seek(3, 1)
            if ntype == 3:
                for _ in range(r.need(r.i(), 68)):  # ossa: nome + matrice
                    r.s(); f.seek(64, 1)
                nv = r.need(r.i(), _SKIN_VERTEX)
                f.seek(nv * _SKIN_VERTEX, 1)
                f.seek(r.need(r.i(), 2) * 2, 1)
                r.i(); f.seek(12, 1)
            else:
                nv = r.need(r.i(), _VERTEX)
                blob = f.read(nv * _VERTEX)
                ni = r.need(r.i(), 2)
                rawi = f.read(ni * 2)
                mat = r.i()
                tail = f.read(12 + 17)
                if len(blob) != nv * _VERTEX or len(rawi) != ni * 2 or len(tail) != 29:
                    raise ValueError("mesh tronca: non e' un kn5")
                kept = _flat_triangles(blob, nv, rawi, ni, parent)
                if kept is not None:
                    pos, uv = kept
                    k = len(mesh_names)
                    mesh_names.append(name)
                    tris.append(pos); uvs.append(uv)
                    mats.append(np.full(len(pos), mat if 0 <= mat < len(materials) else -1,
                                        np.int32))
                    meshes.append(np.full(len(pos), k, np.int32))
            if nchild:
                stack.append([parent, nchild])
        # Tutto quello che il file dichiara e' stato letto; se non torna, si e'
        # gia' fermato su need() o su un pezzo tronco.

    if tris:
        return Model(path, np.concatenate(tris), np.concatenate(uvs),
                     np.concatenate(mats), np.concatenate(meshes),
                     mesh_names, materials, textures)
    return Model(path, np.zeros((0, 3, 3), np.float32), np.zeros((0, 3, 2), np.float32),
                 np.zeros(0, np.int32), np.zeros(0, np.int32), mesh_names, materials, textures)


def _flat_triangles(blob: bytes, nv: int, rawi: bytes, ni: int, M: np.ndarray):
    """I triangoli di una mesh che in pianta coprono qualcosa, gia' nel mondo."""
    if nv == 0 or ni < 3:
        return None
    idx = np.frombuffer(rawi, dtype="<u2")[: ni - ni % 3].reshape(-1, 3)
    if int(idx.max()) >= nv:
        raise ValueError("indice di vertice fuori misura: non e' un kn5")
    v = np.frombuffer(blob, dtype="<f4").reshape(nv, 11)
    pos = v[:, 0:3].astype(np.float64) @ M[:3, :3] + M[3, :3]
    t = pos[idx]                                    # (n, 3, 3)
    e1 = t[:, 1] - t[:, 0]
    e2 = t[:, 2] - t[:, 0]
    cross = np.cross(e1, e2)
    full = np.linalg.norm(cross, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        keep = (full > 0) & (np.abs(cross[:, 1]) >= _FLAT_MIN * full)
    keep &= np.isfinite(t).all(axis=(1, 2))
    if not keep.any():
        return None
    return t[keep].astype(np.float32), v[:, 6:8][idx[keep]].astype(np.float32)


def texture_bytes(model: Model, name: str) -> bytes | None:
    """I byte di una texture del modello (DDS o PNG), o None se non ci sono."""
    where = model.textures.get(name)
    if where is None:
        return None
    off, n = where
    try:
        with Path(model.path).open("rb") as f:
            f.seek(off)
            data = f.read(n)
    except OSError:
        return None
    return data if len(data) == n else None
