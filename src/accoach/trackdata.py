"""Friendly corner names per track.

The coach detects corners geometrically (see :mod:`accoach.track`) and numbers
them T1, T2…  A driver, though, thinks in *names* — "you lost time at Tosa", not
"at corner 3". This module maps detected corners to real names.

Names are assigned by **apex position**, not by index, so the mapping is robust
to the detector finding a slightly different number of corners than the official
count: each detected corner takes the nearest curated name within a tolerance,
and anything unmatched falls back to ``Curva N``.

The curated positions are this sim's ``normalizedCarPosition`` (0..1 from the
start/finish line). They were anchored to a real recorded reference lap; once the
track map exists they can be refined visually. Unknown tracks just get T-numbers.
"""

from __future__ import annotations

import re

# Max distance (in normalized position) between a detected apex and a curated
# apex for the name to apply.
#
# 0.05 was chosen when the only curated track was Imola, whose corners are far
# apart. Monza's Lesmo 1 and Lesmo 2 sit 0.053 apart, i.e. barely more than the
# tolerance itself: a detected apex three thousandths off the midpoint flips
# which name it takes. `name_corners` handles that ambiguity where it belongs,
# by assigning each curated name once, nearest first.
#
# Tightening it was tried on 2026-07-30, when Spa and Suzuka arrived, and was
# wrong: a real Monza lap that went off at Ascari was detected 0.029 from the
# curated apex, so anything under that orphans corners that genuinely exist. The
# distance alone cannot separate "the same corner, detected a little off" from
# "the corner next door" — so it isn't asked to. See ``_DIRECTIONS``.
_NAME_TOL = 0.05


def _slug(text: str) -> str:
    text = (text or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


# track-slug -> ordered list of (name, approx apex pos). Anchored to a real
# Imola reference lap (BMW M4 GT3, 1:43.7) whose detected apexes were
# 0.143 / 0.291 / 0.351 / 0.484 / 0.585 / 0.693 / 0.844 — matched here to the
# known Imola corner sequence.
_CORNERS: dict[str, list[tuple[str, float]]] = {
    "imola": [
        ("Tamburello", 0.143),       # 1st chicane after the straight
        ("Villeneuve", 0.291),       # 2nd chicane
        ("Tosa", 0.351),             # left hairpin
        ("Piratella", 0.484),        # left, uphill
        ("Acque Minerali", 0.585),   # right-left, downhill
        ("Variante Alta", 0.693),    # chicane
        ("Rivazza", 0.844),          # double left before the line
    ],
    # Spa. Anchored to a real lap in the archive (Formula mod SF25, 1:43.642),
    # whose driven length measures 6933 m against the circuit's published 7004 —
    # the 1% is the polyline plus the missing closing chord, which is the check
    # that the positions below really are distances round this track.
    #
    # Each name was matched on THREE independent readings agreeing, not on a
    # guess at where a corner "should" be: the distance along the lap, the
    # direction the corner turns (measured from the driven line, see
    # track._classify) and its character (apex speed + radius). Where any of the
    # three disagreed, no name was given — which is why Eau Rouge and
    # Blanchimont are absent: in a Formula car neither crosses the steering
    # threshold that makes a corner, so there is nothing here to name. Naming
    # the nearest thing instead is how "Eau Rouge" ends up printed on Raidillon.
    "spa": [
        ("La Source", 0.058),      # right hairpin, 70 km/h, 403 m — the slowest
        ("Raidillon", 0.171),      # right at the top of the climb, 309 km/h
        ("Les Combes", 0.351),     # right, 145 km/h, 2434 m
        ("Rivage", 0.443),         # right hairpin, 131 km/h, 3072 m
        ("Pouhon", 0.567),         # long LEFT, 262 km/h — the direction settles it
        ("Fagnes", 0.657),         # right, 196 km/h, 4556 m
        ("Stavelot", 0.712),       # right, 154 km/h, 4936 m
        ("Bus Stop", 0.973),       # chicane before the line, 74 km/h
    ],
    # Suzuka. Same method, anchored to a real lap (BMW M3 E92, 2:36.079) that
    # measures 5759 m against the published 5807. The two Degners are 0.031 of a
    # lap apart — closer than _NAME_TOL — so the table's positions are the
    # MEASURED apexes: an anchor at the true apex wins the nearest-corner match
    # by a distance of zero, and neither name can be stolen by its neighbour.
    #
    # Turns 1-2, 10 and 12 are left numbered on purpose: they have no name in
    # any published map of this circuit, and inventing one to fill the row would
    # make the report authoritative about something it made up.
    "suzuka": [
        ("Esses", 0.301),          # the S curves, detected as one merged run
        ("Dunlop", 0.343),         # left, 148 km/h, 1977 m
        ("Degner 1", 0.394),       # right, 110 km/h
        ("Degner 2", 0.425),       # right and much tighter, 72 km/h
        ("Hairpin", 0.505),        # LEFT hairpin, 50 km/h — the slowest of the lap
        ("Spoon", 0.683),          # double left, 90 km/h, 3935 m
        ("130R", 0.857),           # fast left, 4934 m
        ("Casio Triangle", 0.931), # final chicane, 61 km/h
    ],
    # Anchored the same way, to a real Monza lap (Ferrari 488 GT3 Evo, 2:03.7)
    # whose detected apexes were 0.169 / 0.247 / 0.378 / 0.447 / 0.500 / 0.686 /
    # 0.888. The minimum speeds identify them beyond doubt: 49 km/h at the first
    # chicane, 205 through Curva Grande, 119 in the Parabolica.
    "monza": [
        ("Variante del Rettifilo", 0.169),   # 1st chicane, slowest point of the lap
        ("Curva Grande", 0.247),             # long right, taken near flat
        ("Variante della Roggia", 0.378),    # 2nd chicane
        ("Lesmo 1", 0.447),
        ("Lesmo 2", 0.500),
        ("Variante Ascari", 0.686),          # triple, detected as one corner
        ("Parabolica", 0.888),               # onto the main straight
    ],
}


# track-slug -> ordered list of (it description, en description, approx pos).
# A *visual* braking reference: a fixed feature at a braking point — a kerb, a
# board, a fence — that a driver aims at out the window. It beats a distance in
# metres because the kerb doesn't move: metres from a marker shift 10-20 m with
# car and track temperature, the white-red kerb stays where it is. Anchored to
# normalizedCarPosition like _CORNERS, and used against the *reference lap's*
# braking onset, so it says "where the reference brakes" in terms you can see.
#
# We do NOT guess where kerbs are. A confidently wrong landmark is the worst
# failure mode a coach has, so a track only appears here once its landmarks are
# verified against a trusted source (a recorded reference lap, a braking chart).
# Until then the list stays empty and the debrief falls back to metres — the
# mechanism is live, the words are not.
_LANDMARKS: dict[str, list[tuple[str, str, float]]] = {
    # Monza. Positions MEASURED from the anchor reference lap (Ferrari 488 GT3
    # Evo, 2:03.7) — the same lap the corner names are anchored to — by finding
    # where its brake trace crosses onset (see comparison/delta.py _BRAKE_ONSET).
    # Visual descriptions taken from published ACC/GT3 track guides, not invented:
    #   - Full Grip Motorsport ACC guide (GT3, same class as the reference):
    #     T1 150 m board, Roggia 50 m board, Lesmo 1 50 m board, Ascari 100 m board.
    #   - si.com / general Monza guides corroborate the physical features used
    #     where they beat a distance board: Roggia's orange barrier on the left,
    #     the orange block on the armco at Ascari, Parabolica's green run-off end.
    # Lesmo 2 is left out on purpose: a light brake with no clean visual marker in
    # any source — better silent than guessing. These are a first sourced draft;
    # each stays anchored to the metres in the debrief, so an imperfect one is
    # bounded, not misleading.
    "monza": [
        ("al cartello dei 150 m", "at the 150 m board", 0.122),                 # Variante del Rettifilo
        ("alla barriera arancione sulla sinistra", "at the orange barrier on the left", 0.337),  # Roggia
        ("al cartello dei 50 m", "at the 50 m board", 0.418),                   # Lesmo 1
        ("al cartello dei 100 m", "at the 100 m board", 0.650),                 # Variante Ascari
        ("alla fine del verde sulla sinistra", "at the end of the green run-off on the left", 0.860),  # Parabolica
    ],
    # Imola: CERCATA il 2026-07-31, e resta vuota apposta. Le posizioni ci sono —
    # misurate sul giro di riferimento (McLaren 720S GT3 Evo, 1:46.097, stessa
    # classe del metodo di Monza), distanza stacco->apex:
    #
    #   Tamburello 147 m · Villeneuve 38 m · Tosa 111 m · Piratella 126 m
    #   Acque Minerali 84 m · Variante Alta 137 m · Rivazza 139 m
    #
    # Manca l'altra metà: *quale oggetto* si vede lì. Due fonti indipendenti
    # consultate, e si contraddicono su quasi ogni curva —
    #
    #   curva          guida ACC/GT3                wiki Le Mans Ultimate
    #   Tamburello     nessun marker                flag-light sulla destra
    #   Villeneuve     dopo il cartello dei 200     secondo cartello a destra
    #   Tosa           intorno ai 50                nessun marker
    #   Piratella      cartello dei 50              flag-light sulla destra
    #   Rivazza        dopo il cartello dei 50      flag-light sulla destra
    #
    # (e la seconda descrive prototipi, che staccano da tutt'altra parte). La
    # distanza stacco->apex non arbitra: non dice dov'è il punto di corda, quindi
    # non distingue un cartello dei 50 da uno dei 100.
    #
    # A Monza le fonti concordavano; qui no, e una staccata sbagliata detta con
    # sicurezza è il difetto peggiore che un coach possa avere. Lista vuota =
    # resta ai metri, che sono misurati.
    "imola": [],
}

# Spa e Suzuka non compaiono qui, e non è per pigrizia: i loro giri di
# riferimento in archivio sono una monoposto (SF25) e una stradale (BMW M3 E92).
# I cartelli di staccata delle guide sono tarati sulle GT3, che staccano decine
# di metri più tardi — copiarli lì darebbe un riferimento visivo giusto per
# un'auto che nessuno sta guidando. Serve prima un giro GT3 su quelle piste.

# How close (normalized position) a braking point must sit to a curated landmark
# for the landmark to describe it. Tighter than _NAME_TOL on purpose: a corner
# name labels a whole corner, a landmark pins one spot on the track.
_LANDMARK_TOL = 0.02


def landmark_at(track: str, pos: float, lang: str | None = None) -> str | None:
    """Visual description of the braking landmark nearest ``pos``, or ``None`` if
    the track has no verified landmark within tolerance.

    ``pos`` is a normalizedCarPosition — pass the reference lap's braking onset,
    so the phrase describes where the *reference* brakes ("al cordolo
    bianco-rosso") rather than an abstract distance. The returned string carries
    its own preposition, ready to drop after a verb ("il riferimento frena …").
    """
    table = _LANDMARKS.get(_slug(track))
    if not table:
        return None
    it, en, p = min(table, key=lambda t: abs(t[2] - pos))
    if abs(p - pos) > _LANDMARK_TOL:
        return None
    from .i18n import current_language
    return it if (lang or current_language()) == "it" else en


def corner_name(track: str, index: int, apex_pos: float,
                lang: str | None = None, direction: str = "") -> str:
    """Name for a detected corner, by nearest curated apex, else ``Corner N`` /
    ``Curva N`` per language (curated names are proper nouns, kept as-is).

    ``direction`` is the way this corner actually turns, when the lap carries
    the coordinates to know. Passing it is what stops a name from reaching the
    corner next door — this function names one corner at a time and has none of
    the once-each protection ``name_corners`` uses.
    """
    table = _CORNERS.get(_slug(track))
    if table:
        usable = [t for t in table if _direction_ok(track, t[0], direction)]
        if usable:
            name, pos = min(usable, key=lambda t: abs(t[1] - apex_pos))
            if abs(pos - apex_pos) <= _NAME_TOL:
                return name
    from .i18n import current_language
    word = "Curva" if (lang or current_language()) == "it" else "Corner"
    return f"{word} {index + 1}"


# Which way each curated corner turns, where we have measured it. A name only
# applies to a corner turning the same way — the one check that separates "the
# same corner, detected a little off" from "the corner next door", using a
# signal that cannot be half-right: a left is never a right.
#
# It exists because of two real misreadings found on 2026-07-30, both inside the
# position tolerance: a corner detected at the bottom of Eau Rouge answered "La
# Source" (300 m down the hill, and a right where Eau Rouge is a left), and the
# right-hand kink before Suzuka's hairpin answered "Hairpin" (which is a left).
#
# Absent or empty = don't check: Imola's and Monza's tables predate this and
# their directions were never measured, and a chicane has no single direction to
# match anyway (Bus Stop is right-left, Casio Triangle right-left). Absence of a
# measurement is not a reason to reject a name — it's a reason not to ask.
_DIRECTIONS: dict[str, dict[str, str]] = {
    "spa": {
        "La Source": "right", "Raidillon": "right", "Les Combes": "right",
        "Rivage": "right", "Pouhon": "left", "Fagnes": "right",
        "Stavelot": "right",           # Bus Stop is a chicane: not checked
    },
    "suzuka": {
        "Esses": "left", "Dunlop": "left", "Degner 1": "right",
        "Degner 2": "right", "Hairpin": "left", "Spoon": "left",
        "130R": "left",                # Casio Triangle is a chicane: not checked
    },
}


def _direction_ok(track: str, name: str, direction: str) -> bool:
    """Does this corner turn the way the curated one does?

    True whenever either side has nothing to say — a lap with no coordinates
    can't classify a corner, and most curated corners have no measured direction
    yet. Unknown must not mean "no".
    """
    want = _DIRECTIONS.get(_slug(track), {}).get(name, "")
    return not want or not direction or want == direction


def name_corners(track: str, corners, lang: str | None = None) -> list[str]:
    """Names for a list of detected corners (objects with ``index``/``apex_pos``).

    Each curated name is handed out **once**. Naming corner-by-corner is fine in
    isolation but wrong for a set: the detector's corner count is not fixed, and
    with a different car or a slower line a multi-part complex splits — Ascari
    into three, say. Every part is then nearest to the same curated apex and the
    report grows three rows called "Variante Ascari", in the losses, in the
    corner speeds, and in what the coach says out loud. Whichever part is nearest
    to the real apex keeps the name; the others fall back to a number, which is
    vague but at least tells them apart.
    """
    named: list[str | None] = [None] * len(corners)
    table = _CORNERS.get(_slug(track))
    if table:
        for name, pos in table:
            best, best_d = None, _NAME_TOL
            for i, c in enumerate(corners):
                if named[i] is not None:
                    continue
                if not _direction_ok(track, name, getattr(c, "direction", "")):
                    continue
                d = abs(c.apex_pos - pos)
                if d <= best_d:
                    best, best_d = i, d
            if best is not None:
                named[best] = name
    return [named[i] if named[i] is not None
            else corner_name("", c.index, c.apex_pos, lang)
            for i, c in enumerate(corners)]


def has_names(track: str) -> bool:
    return _slug(track) in _CORNERS
