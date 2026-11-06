"""La pista vista dall'alto dai file grafici di AC.

Due parti. La prima decide *quali* file: dalla linea dell'IA di una pista si
risale alla sua cartella, al suo `models.ini` (o `models_<layout>.ini`) e ai
kn5 che elenca, con posizione e rotazione. La seconda disegna un tassello di
TILE_PX pixel, visto dall'alto, dai triangoli gia' letti da `kn5visual`. Sola
lettura: niente viene mai scritto nella cartella del gioco.
"""
from __future__ import annotations

import configparser
import hashlib
import io
import math
import os
import re
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from . import kn5visual, paths


@dataclass(frozen=True)
class ArtFile:
    """Un kn5 grafico e dove l'ini lo mette.

    `rotation_deg` e' come sta scritta nell'ini: (yaw/Y, pitch/X, roll/Z) in
    gradi. Applicarla non spetta a questo modulo di lettura.
    """

    path: Path
    position: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]


_ZERO = (0.0, 0.0, 0.0)


def _triple(text: str | None) -> tuple[float, float, float]:
    try:
        v = [float(p) for p in (text or "").replace(";", ",").split(",")]
    except ValueError:
        return _ZERO
    return (v[0], v[1], v[2]) if len(v) == 3 else _ZERO


def _inside(folder: Path, name: str) -> Path | None:
    """Il file, solo se sta davvero dentro la cartella della pista."""
    name = name.strip().strip('"').replace("\\", "/")
    if not name:
        return None
    try:
        root = folder.resolve()
        got = (folder / name).resolve()
        got.relative_to(root)
    except (ValueError, OSError):
        return None
    return got if got.is_file() else None


def art_files(spline: Path) -> list[ArtFile]:
    """I kn5 grafici della pista a cui appartiene `spline` (la sua fast_lane.ai)."""
    layout_dir = spline.parent.parent
    ini = layout_dir.parent / f"models_{layout_dir.name}.ini"
    if ini.is_file():
        folder = layout_dir.parent
    elif any(layout_dir.glob("*.kn5")) or (layout_dir / "models.ini").is_file():
        folder, ini = layout_dir, layout_dir / "models.ini"
    else:
        folder, ini = layout_dir.parent, layout_dir.parent / "models.ini"
    if not ini.is_file():
        try:
            return [ArtFile(p, _ZERO, _ZERO)
                    for p in sorted(folder.glob("*.kn5")) if p.is_file()]
        except OSError:
            return []
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        cp.read_string(ini.read_text(encoding="utf-8-sig", errors="replace"))
    except (configparser.Error, OSError):
        return []
    out: list[ArtFile] = []
    for section in cp.sections():
        got = _inside(folder, cp.get(section, "file", fallback=""))
        if got is not None:
            out.append(ArtFile(got, _triple(cp.get(section, "position", fallback=None)),
                               _triple(cp.get(section, "rotation", fallback=None))))
    return out


# --- un tassello vista dall'alto ---------------------------------------------
# Decisioni 3, 4 e 5 del piano. Un tassello e' un quadrato di TILE_PX pixel in
# coordinate del modello: (L, tx, tz) copre x in [tx*lato, (tx+1)*lato) e z in
# [tz*lato, (tz+1)*lato). Il pixel (0, 0) e' in alto a sinistra, x minima e z
# massima. Niente specchio: lo fa la pagina.
#
# Il disegno e' tutto vettoriale. Ogni triangolo diventa i pixel del suo
# ingombro, si tengono quelli col centro dentro, e la quota decide chi vince:
# un ordinamento, non un ciclo per triangolo. Lo spike che girava un ciclo
# Python per triangolo impiegava 118 s per il Monza a 1 m per pixel.

#: Oltre questo scarto (95-esimo percentile, in metri) fra la linea del giro e
#: quella dell'IA, lo sfondo non si posa. Riconoscere il circuito ne tollera 35
#: (`trackedges._FIT_P95_M`), ma sotto una foto la linea deve stare
#: sull'asfalto. Misurato il 2026-11-06 sui giri del pilota: Spa, Suzuka, Monza
#: e Brands Hatch stanno fra 2,4 e 5,7 m, col 98,8-100 % della linea sulla
#: strada del modello di collisione. Il Nurburgring di ACC su ks_nurburgring da'
#: 18,8 e 25,9 m, col 77 % sulla strada; spa_1998 14,5 m.
BG_FIT_P95_M = 10.0
#: Metri per pixel dei sei livelli, dal piu' fitto al piu' largo.
LEVELS_M = (0.1, 0.2, 0.4, 0.8, 1.6, 3.2)
TILE_PX = 512
#: Sopra la strada del modello di collisione, oltre questa altezza c'e' un
#: ponte, un portale o una passerella: non si disegna, si vede la strada.
#: Misurato sul Monza installato il 2026-11-06, sui triangoli disegnati sopra
#: strada e cordoli. Quello che sta *sulla* strada resta sotto 2,0 m
#: (guardrail 0,3-1,0, new jersey 0,4-0,7, dettagli dei box 1,4-1,9); solo la
#: cima delle teste della gente ai box arriva a 2,1. Quello che le passa
#: *sopra* parte da 2,1: posti di segnalazione 2,1-5,0, cartello sul muretto
#: 5,1-5,6, le due passerelle 4,7-8,7. A 2,0 le passerelle spariscono e sotto
#: si vede l'asfalto.
OVERHEAD_M = 2.0
#: Texel piu' trasparenti di cosi' si scartano, per gli shader con alpha test
#: o blend 1 (foglie, reti, ombre finte).
ALPHA_CUT = 100

#: Lato massimo di una texture decodificata, per livello.
_TEX_SIDE = (4096, 4096, 2048, 2048, 1024, 1024)
#: Le texture decodificate restano in memoria fino a questo peso.
_TEX_BUDGET = 512 * 1024 * 1024
#: Un triangolo che sullo schermo sta sotto questo lato e' un punto.
_SPLAT_PX = 1.5
#: Cella dell'indice spaziale, in metri.
_CELL_M = 64.0
#: Pixel candidati elaborati in un colpo: tiene la memoria sotto il centinaio di MB.
_CHUNK = 1 << 20
_GREY = np.array([128, 128, 128, 255], np.float32)
#: Il fondo dove non c'e' niente: il colore dei pannelli della reportistica.
_EMPTY = (21, 26, 33)


class _Index:
    """Caselle di _CELL_M metri: quali triangoli toccano un rettangolo.

    Un triangolo piu' piccolo di una casella sta nella casella del centro del
    suo ingombro; quelli piu' grandi (prati, piazzali) si provano sempre.
    """

    def __init__(self, tris: np.ndarray):
        xz = tris[:, :, (0, 2)]
        self.lo = xz.min(axis=1)
        self.hi = xz.max(axis=1)
        small = (self.hi - self.lo).max(axis=1) <= _CELL_M
        self.big = np.nonzero(~small)[0]
        ids = np.nonzero(small)[0]
        # Al massimo cento milioni di caselle per lato: con un vertice assurdo le
        # chiavi restano interi sani.
        mid = np.clip((self.lo[ids] + self.hi[ids]) * (0.5 / _CELL_M), -1e8, 1e8)
        c = np.floor(mid).astype(np.int64)
        if len(ids):
            self.c0 = c.min(axis=0)
            self.n = c.max(axis=0) - self.c0 + 1
        else:
            self.c0 = np.zeros(2, np.int64)
            self.n = np.zeros(2, np.int64)
        keys = (c[:, 0] - self.c0[0]) * self.n[1] + (c[:, 1] - self.c0[1])
        order = np.argsort(keys, kind="stable")
        self.keys = keys[order]
        self.ids = ids[order]

    def query(self, x0: float, x1: float, z0: float, z1: float) -> np.ndarray:
        parts = [self.big]
        if len(self.ids):
            # il centro di un triangolo piccolo sta entro mezza casella dal bordo
            cx0, cz0 = (math.floor((v - _CELL_M) / _CELL_M) for v in (x0, z0))
            cx1, cz1 = (math.floor((v + _CELL_M) / _CELL_M) for v in (x1, z1))
            cx0, cx1 = max(cx0, self.c0[0]), min(cx1, self.c0[0] + self.n[0] - 1)
            cz0, cz1 = max(cz0, self.c0[1]), min(cz1, self.c0[1] + self.n[1] - 1)
            for cx in range(int(cx0), int(cx1) + 1):
                row = (cx - self.c0[0]) * self.n[1] - self.c0[1]
                a, b = np.searchsorted(self.keys, (row + cz0, row + cz1 + 1))
                if b > a:
                    parts.append(self.ids[a:b])
        got = np.concatenate(parts) if len(parts) > 1 else self.big
        lo, hi = self.lo[got], self.hi[got]
        keep = (hi[:, 0] >= x0) & (lo[:, 0] < x1) & (hi[:, 1] >= z0) & (lo[:, 1] < z1)
        return got[keep]


class Scene:
    """I modelli grafici di una pista e la strada del modello di collisione.

    Tiene l'indice spaziale e le texture gia' decodificate, quindi va creata
    una volta per pista e riusata per tutti i suoi tasselli.
    """

    def __init__(self, models, road=None):
        from .trackmesh import _class_of

        self.models = list(models)
        self.road = road
        # Solo le mesh che il gioco disegna: il modello di collisione sta in
        # `models.ini` come gli altri, con `isRenderable` a 0.
        self._drawn: list[np.ndarray] = []
        for m in self.models:
            vis = np.ones(len(m.mesh_names), bool)
            vis[:len(m.mesh_visible)] = m.mesh_visible
            self._drawn.append(np.flatnonzero(vis[m.mesh]))
        self._index = [_Index(m.tris[d]) for m, d in zip(self.models, self._drawn)]
        # Per ogni modello: materiale -> texture della scena (-1 grigio) e alpha.
        self._tex_names: list[tuple[int, str]] = []
        self._mat_tex: list[np.ndarray] = []
        self._mat_alpha: list[np.ndarray] = []
        seen: dict[tuple[int, str], int] = {}
        for i, m in enumerate(self.models):
            tex = np.full(len(m.materials) + 1, -1, np.int32)       # l'ultimo e' mat -1
            alpha = np.zeros(len(m.materials) + 1, bool)
            for k, mt in enumerate(m.materials):
                if mt.diffuse:
                    tex[k] = seen.setdefault((i, mt.diffuse), len(seen))
                alpha[k] = mt.alpha_test or mt.blend == 1
            self._mat_tex.append(tex)
            self._mat_alpha.append(alpha)
        self._tex_names = sorted(seen, key=seen.get)
        self._tex: OrderedDict = OrderedDict()
        self._tex_bytes = 0
        self._road_tris = np.zeros((0, 3, 3), np.float32)
        if road is not None and len(road.tris):
            cls = np.array([_class_of(n) in ("road", "kerb") for n in road.mesh_names]
                           + [False])
            self._road_tris = road.tris[cls[road.mesh]]
        self._road_index = _Index(self._road_tris)

    def texture(self, tid: int, level: int) -> np.ndarray | None:
        """La texture `tid` in RGBA uint8, ridotta per il livello; None se non si apre."""
        side = _TEX_SIDE[level]
        key = (tid, side)
        if key in self._tex:
            self._tex.move_to_end(key)
            return self._tex[key]
        i, name = self._tex_names[tid]
        arr = None
        data = kn5visual.texture_bytes(self.models[i], name)
        if data is not None:
            try:
                arr = _decode(data, side)
            except Exception:       # noqa: BLE001 - BC7, DDS strani, byte rotti: grigio
                arr = None
        self._tex[key] = arr
        self._tex_bytes += 0 if arr is None else arr.nbytes
        while self._tex_bytes > _TEX_BUDGET and len(self._tex) > 1:
            _, old = self._tex.popitem(last=False)
            self._tex_bytes -= 0 if old is None else old.nbytes
        return arr


def _decode(data: bytes, side: int) -> np.ndarray:
    """Una texture in RGBA uint8, col lato al massimo `side`.

    Si riduce prima di convertire: a piena risoluzione in memoria c'e' solo la
    copia decodificata, mai anche quella convertita. Una 8192 x 8192 sono
    256 MB; convertirla prima di ridurla ne chiedeva altri 256.
    """
    with Image.open(io.BytesIO(data)) as im:
        im.draft("RGBA", (side, side))          # solo JPEG: decodifica gia' ridotta
        im.load()
        cur = im
        if max(cur.size) > side:
            if cur.mode not in ("RGB", "RGBA", "L", "LA"):
                cur = cur.convert("RGBA")
            f = side / max(cur.size)
            cur = cur.resize((max(1, round(cur.width * f)), max(1, round(cur.height * f))),
                             Image.Resampling.BOX)
        if cur.mode != "RGBA":
            cur = cur.convert("RGBA")
        return np.asarray(cur, dtype=np.uint8)


def _fragments(P: np.ndarray, x0: float, z1: float, mpp: float, splat: bool):
    """I pixel che i triangoli `P` (n, 3, 3) coprono nel tassello.

    Restituisce (pixel, triangolo, pesi baricentrici (m, 3)). Con `splat` i
    triangoli sotto _SPLAT_PX di lato danno un pixel solo, al baricentro.
    """
    T = TILE_PX
    sx = (P[:, :, 0].astype(np.float64) - x0) / mpp
    sy = (z1 - P[:, :, 2].astype(np.float64)) / mpp
    out_pix, out_tri, out_w = [], [], []

    lo_x, hi_x = sx.min(axis=1), sx.max(axis=1)
    lo_y, hi_y = sy.min(axis=1), sy.max(axis=1)
    if splat:
        small = np.maximum(hi_x - lo_x, hi_y - lo_y) < _SPLAT_PX
        si = np.nonzero(small)[0]
        if len(si):
            px = np.floor(sx[si].mean(axis=1)).astype(np.int64)
            py = np.floor(sy[si].mean(axis=1)).astype(np.int64)
            ok = (px >= 0) & (px < T) & (py >= 0) & (py < T)
            out_pix.append(py[ok] * T + px[ok])
            out_tri.append(si[ok])
            out_w.append(np.full((int(ok.sum()), 3), 1.0 / 3.0))
        big = np.nonzero(~small)[0]
    else:
        big = np.arange(len(P))

    # I pixel il cui centro (j + 0,5) puo' cadere nel triangolo.
    bx0 = np.clip(np.ceil(lo_x[big] - 0.5), 0, T).astype(np.int64)
    bx1 = np.clip(np.floor(hi_x[big] - 0.5), -1, T - 1).astype(np.int64)
    by0 = np.clip(np.ceil(lo_y[big] - 0.5), 0, T).astype(np.int64)
    by1 = np.clip(np.floor(hi_y[big] - 0.5), -1, T - 1).astype(np.int64)
    nx = np.maximum(bx1 - bx0 + 1, 0)
    ny = np.maximum(by1 - by0 + 1, 0)
    count = nx * ny
    live = np.nonzero(count)[0]
    big, bx0, by0, nx, count = big[live], bx0[live], by0[live], nx[live], count[live]
    ax, bx_, cx = sx[big, 0], sx[big, 1], sx[big, 2]
    ay, by_, cy = sy[big, 0], sy[big, 1], sy[big, 2]
    den = (by_ - cy) * (ax - cx) + (cx - bx_) * (ay - cy)
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = np.where(den != 0, 1.0 / den, 0.0)

    ends = np.cumsum(count)
    start = 0
    while start < len(big):
        # quanti triangoli stanno in un blocco di _CHUNK pixel (almeno uno)
        base = ends[start - 1] if start else 0
        stop = max(int(np.searchsorted(ends, base + _CHUNK, side="right")), start + 1)
        sel = slice(start, stop)
        cnt = count[sel]
        rep = np.repeat(np.arange(start, stop), cnt)
        local = np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        jx = bx0[rep] + local % nx[rep]
        jy = by0[rep] + local // nx[rep]
        gx = jx + 0.5 - cx[rep]
        gy = jy + 0.5 - cy[rep]
        w0 = ((by_[rep] - cy[rep]) * gx + (cx[rep] - bx_[rep]) * gy) * inv[rep]
        w1 = ((cy[rep] - ay[rep]) * gx + (ax[rep] - cx[rep]) * gy) * inv[rep]
        w2 = 1.0 - w0 - w1
        eps = -1e-9
        inside = (w0 >= eps) & (w1 >= eps) & (w2 >= eps) & (inv[rep] != 0)
        out_pix.append(jy[inside] * T + jx[inside])
        out_tri.append(big[rep[inside]])
        out_w.append(np.stack((w0[inside], w1[inside], w2[inside]), axis=1))
        start = stop

    if not out_pix:
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros((0, 3))
    return np.concatenate(out_pix), np.concatenate(out_tri), np.concatenate(out_w)


def _bilinear(tex: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Campiona `tex` (h, w, 4) in (u, v) ripetuti, fra i quattro texel vicini."""
    th, tw = tex.shape[:2]
    fu = np.nan_to_num(u, posinf=0.0, neginf=0.0) * tw - 0.5
    fv = np.nan_to_num(v, posinf=0.0, neginf=0.0) * th - 0.5
    u0, v0 = np.floor(fu), np.floor(fv)
    du, dv = (fu - u0)[:, None], (fv - v0)[:, None]
    u0 = np.mod(u0.astype(np.int64), tw)
    v0 = np.mod(v0.astype(np.int64), th)
    u1, v1 = (u0 + 1) % tw, (v0 + 1) % th
    f = np.float32
    return (tex[v0, u0].astype(f) * ((1 - du) * (1 - dv))
            + tex[v0, u1].astype(f) * (du * (1 - dv))
            + tex[v1, u0].astype(f) * ((1 - du) * dv)
            + tex[v1, u1].astype(f) * (du * dv))


def _road_height(scene: Scene, x0, x1, z0, z1, mpp) -> np.ndarray:
    """La quota piu' alta della strada (o del cordolo) per pixel, -inf dove non c'e'.

    Senza punti al baricentro: la maschera deve coprire ogni pixel della
    strada, anche dove i suoi triangoli sono piu' piccoli di un pixel.
    """
    out = np.full(TILE_PX * TILE_PX, -np.inf, np.float32)
    ids = scene._road_index.query(x0, x1, z0, z1)
    if len(ids):
        P = scene._road_tris[ids]
        pix, tri, w = _fragments(P, x0, z1, mpp, splat=False)
        h = (w * P[tri, :, 1]).sum(axis=1).astype(np.float32)
        np.maximum.at(out, pix, h)
    return out


def render_tile(scene: Scene, level: int, tx: int, tz: int) -> Image.Image | None:
    """Il tassello (level, tx, tz) visto dall'alto, o None se non c'e' niente."""
    mpp = LEVELS_M[level]
    side = TILE_PX * mpp
    x0, z0 = tx * side, tz * side
    x1, z1 = x0 + side, z0 + side
    road = None

    pix_l, h_l, u_l, v_l, tid_l, al_l = [], [], [], [], [], []
    for i, m in enumerate(scene.models):
        ids = scene._drawn[i][scene._index[i].query(x0, x1, z0, z1)]
        if not len(ids):
            continue
        P = m.tris[ids]
        pix, tri, w = _fragments(P, x0, z1, mpp, splat=True)
        if not len(pix):
            continue
        h = (w * P[tri, :, 1]).sum(axis=1).astype(np.float32)
        if len(scene._road_tris):
            if road is None:
                road = _road_height(scene, x0, x1, z0, z1, mpp)
            r = road[pix]
            keep = ~(np.isfinite(r) & (h > r + OVERHEAD_M))
            pix, tri, w, h = pix[keep], tri[keep], w[keep], h[keep]
        UV = m.uv[ids[tri]]
        mat = m.mat[ids[tri]]                 # -1 cade sull'ultimo posto: grigio
        pix_l.append(pix); h_l.append(h)
        u_l.append((w * UV[:, :, 0]).sum(axis=1)); v_l.append((w * UV[:, :, 1]).sum(axis=1))
        tid_l.append(scene._mat_tex[i][mat]); al_l.append(scene._mat_alpha[i][mat])
    if not pix_l or not sum(len(p) for p in pix_l):
        return None
    pix, h = np.concatenate(pix_l), np.concatenate(h_l)
    u, v = np.concatenate(u_l), np.concatenate(v_l)
    tid, alpha = np.concatenate(tid_l), np.concatenate(al_l)

    # Sotto la superficie opaca piu' alta non si vede niente: si scarta prima
    # di campionare le texture, che e' la parte cara.
    top = np.full(TILE_PX * TILE_PX, -np.inf, np.float32)
    np.maximum.at(top, pix[~alpha], h[~alpha])
    keep = h >= top[pix]
    pix, h, u, v, tid, alpha = pix[keep], h[keep], u[keep], v[keep], tid[keep], alpha[keep]

    col = np.empty((len(pix), 4), np.float32)
    col[:] = _GREY
    order = np.argsort(tid, kind="stable")
    bounds = np.flatnonzero(np.diff(tid[order])) + 1
    for grp in np.split(order, bounds):
        t = int(tid[grp[0]])
        tex = scene.texture(t, level) if t >= 0 else None
        if tex is not None:
            col[grp] = _bilinear(tex, u[grp], v[grp])
    keep = ~alpha | (col[:, 3] >= ALPHA_CUT)
    pix, h, col = pix[keep], h[keep], col[keep]
    if not len(pix):
        return None

    # Per ogni pixel vince il frammento piu' alto: ordinati per pixel e quota,
    # l'ultimo di ogni pixel.
    order = np.lexsort((h, pix))
    ps = pix[order]
    last = np.ones(len(ps), bool)
    last[:-1] = ps[1:] != ps[:-1]
    win = order[last]
    img = np.empty((TILE_PX * TILE_PX, 3), np.uint8)
    img[:] = _EMPTY
    img[pix[win]] = np.clip(col[win, :3] + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(img.reshape(TILE_PX, TILE_PX, 3), "RGB")


# --- la cache dei tasselli ----------------------------------------------------
# Decisioni 3 (parte) e 7 del piano. Un tassello si disegna una volta e poi si
# legge da disco: <cache>/<chiave>/<livello>/<tx>/<tz>.jpg, oppure `.none` se non
# c'e' niente da disegnare. La cache si puo' cancellare e si ricostruisce.

#: Cambia quando cambia il modo di disegnare: i tasselli vecchi non valgono piu'.
ART_VERSION = 1
_JPEG_QUALITY = 85
_KEY_RE = re.compile(r"[0-9a-f]{16}")

#: Chiave -> linea IA da cui si e' calcolata: cosi' `scene_for` ritrova i file.
_known: dict[str, Path] = {}
#: Una sola scena in memoria. Il lock serve la lettura dei kn5, il disegno e la
#: cache delle texture della scena, che non e' thread-safe: i tasselli arrivano
#: dal pool di FastAPI. Disegnare uno alla volta tiene anche bassa la memoria
#: (ogni disegno ne usa un centinaio di MB), e chi aspetta trova il tassello
#: gia' su disco.
_lock = threading.RLock()
_scene_key: str | None = None
_scene: Scene | None = None
#: Dopo tanti secondi senza disegnare un tassello la scena si libera, texture
#: comprese: sul Monza sono 131 MB piu' fino a _TEX_BUDGET di texture. I
#: tasselli su disco si servono anche senza; il primo da disegnare la ricarica.
SCENE_IDLE_S = 300.0
_last_use = 0.0
_timer: threading.Timer | None = None


def _touch() -> None:
    """La scena e' appena servita: il conto alla rovescia riparte da qui."""
    global _last_use
    with _lock:
        _last_use = time.monotonic()
        if _timer is None:
            _arm(SCENE_IDLE_S)


def _arm(delay: float) -> None:
    global _timer
    _timer = threading.Timer(delay, _on_timer)
    _timer.daemon = True
    _timer.start()


def _on_timer() -> None:
    global _timer
    with _lock:
        _timer = None
        left = _release_if_idle()
        if left > 0:
            _arm(left)


def _release_if_idle(now: float | None = None) -> float:
    """Libera la scena se e' ferma da SCENE_IDLE_S; i secondi che mancano, o 0.

    Le chiavi gia' note restano: il tassello dopo ricarica la scena.
    """
    global _scene, _scene_key
    with _lock:
        if _scene is None:
            return 0.0
        left = SCENE_IDLE_S - ((time.monotonic() if now is None else now) - _last_use)
        if left > 0:
            return left
        _scene, _scene_key = None, None
        return 0.0


def cache_dir() -> Path:
    return paths.base_dir() / "cache" / "mapbg"


def _collision_path(spline: Path) -> Path | None:
    """Il modello di collisione nella cartella della pista, o None."""
    from .trackmesh import is_physics_model

    folder = spline.parent.parent
    seen: list[Path] = []
    try:
        for d in (folder, folder.parent):
            seen += sorted(d.glob("*.kn5"))
        # i piccoli per primi, come `trackmesh.physics_model`
        for p in sorted(dict.fromkeys(seen), key=lambda p: p.stat().st_size):
            if is_physics_model(p):
                return p
    except OSError:
        return None
    return None


def _files_of(spline: Path) -> tuple[list[ArtFile], ArtFile | None]:
    """I kn5 grafici e il modello di collisione, messo nello stesso sistema."""
    art = art_files(spline)
    col = _collision_path(spline)
    if col is None:
        return art, None
    for a in art:
        if a.path == col:
            return art, a
    return art, ArtFile(col, _ZERO, _ZERO)


def art_key(spline: Path) -> str | None:
    """La chiave dei tasselli di questa pista, o None se non ha file grafici.

    Dipende dai file usati, dalla loro dimensione e data, e da ART_VERSION: se
    la pista cambia, i tasselli si rifanno.
    """
    art, col = _files_of(Path(spline))
    if not art:
        return None
    files = list(dict.fromkeys([a.path for a in art] + ([col.path] if col else [])))
    h = hashlib.sha1()
    try:
        for p in files:
            st = p.stat()
            h.update(f"{p}|{st.st_size}|{st.st_mtime_ns}\n".encode("utf-8", "replace"))
    except OSError:
        return None
    h.update(f"v{ART_VERSION}".encode())
    key = h.hexdigest()[:16]
    with _lock:
        _known[key] = Path(spline)
    return key


def scene_for(key: str) -> Scene | None:
    """La scena della chiave, letta dai file (al massimo una in memoria).

    None se la chiave non e' nota o un file non si apre ora (AC lo sta
    caricando): non si ricorda come "pista senza sfondo", si riprova.
    """
    global _scene_key, _scene
    with _lock:
        if _scene_key == key and _scene is not None:
            return _scene
        spline = _known.get(key)
        if spline is None:
            return None
        art, col = _files_of(spline)
        loaded: dict[Path, kn5visual.Model | None] = {}
        for a in art + ([col] if col else []):
            if a.path in loaded:
                continue
            try:
                loaded[a.path] = kn5visual.read(a.path, a.position, a.rotation_deg)
            except OSError:
                return None
            except ValueError:
                loaded[a.path] = None       # non e' un kn5: non lo sara' piu' tardi
        models = [loaded[a.path] for a in art if loaded.get(a.path) is not None]
        road = loaded.get(col.path) if col else None
        _scene, _scene_key = None, None     # libera la vecchia prima di crearne una
        _scene = Scene(models, road)
        _scene_key = key
        return _scene


def _tile_path(key: str, level: int, tx: int, tz: int) -> Path:
    if not _KEY_RE.fullmatch(key):
        raise KeyError(key)
    for v in (level, tx, tz):
        if type(v) is not int:
            raise ValueError("coordinate del tassello non intere")
    if not 0 <= level < len(LEVELS_M):
        raise ValueError("livello fuori misura")
    return cache_dir() / key / str(level) / str(tx) / str(tz)


def _read_cached(base: Path) -> tuple[bool, bytes | None]:
    """(trovato, byte): `.none` e' trovato con None."""
    try:
        return True, base.with_suffix(".jpg").read_bytes()
    except OSError:
        pass
    if base.with_suffix(".none").exists():
        return True, None
    return False, None


def _store(base: Path, data: bytes | None) -> None:
    """Scrive in un file temporaneo e lo sostituisce: mai un file a meta'."""
    target = base.with_suffix(".none" if data is None else ".jpg")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data or b"")
            os.replace(tmp, target)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        pass            # senza disco il tassello si rifa': lo sfondo non manca


def tile(key: str, level: int, tx: int, tz: int) -> bytes | None:
    """I byte JPEG del tassello, o None se non c'e' niente da disegnare.

    Solleva KeyError se la chiave non e' nota (mai calcolata da `art_key` in
    questa sessione). Se i file non si leggono ora da' None senza ricordarlo.
    """
    base = _tile_path(key, level, tx, tz)
    found, data = _read_cached(base)
    if found:
        return data
    if key not in _known:
        raise KeyError(key)
    with _lock:
        found, data = _read_cached(base)        # un altro lo ha fatto mentre si aspettava
        if found:
            return data
        scene = scene_for(key)
        if scene is None:
            return None
        try:
            img = render_tile(scene, level, tx, tz)
        finally:
            _touch()
        if img is None:
            data = None
        else:
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=_JPEG_QUALITY)
            data = buf.getvalue()
        _store(base, data)
        return data
