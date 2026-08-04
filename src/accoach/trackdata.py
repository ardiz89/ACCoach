"""Friendly corner names per track.

The coach detects corners geometrically (see :mod:`accoach.track`) and numbers
them T1, T2…  A driver, though, thinks in *names* — "you lost time at Tosa", not
"at corner 3". This module maps detected corners to real names.

Names are assigned by **apex position**, not by index, so the mapping is robust
to the detector finding a slightly different number of corners than the official
count: each detected corner takes the nearest curated name within a tolerance,
and anything unmatched falls back to ``Curva N``.

The curated positions are this sim's ``normalizedCarPosition`` (0..1 from the
start/finish line). The oldest tables were anchored to a real recorded reference
lap; from 2026-08-03 they can also be read off the bundled centrelines, which
start at the start/finish line and reproduce the lap-anchored positions to 12-33 m
(``tools/corner_atlas.py``). Unknown tracks just get numbers.

**A circuit is not a layout, and this table is about layouts.** Barcelona has
fourteen corners since 2021 and sixteen before that, with a chicane where the
last third of the lap now runs free; Spa's 1998 version is a different track
wearing the same name. A table applied across that boundary does not degrade
gracefully — it puts a name in the middle of a straight. So the alias map only
ever joins spellings of *one* layout, and a circuit whose trace describes a
different one is left out rather than approximated.

**But a different corner COUNT is not a different layout**, and reading it as
one cost seven circuits until 2026-08-04. Official numbering merges complexes —
Sepang's own guide calls Turns 7 and 8 "a long double-apex right hander" — so a
detector finding eighteen apexes where the FIA counts fifteen is the same road
counted two ways. What settles it is the **sequence of directions**: fifteen
lefts and rights in order, agreeing all the way down, is evidence no coincidence
supplies. The count is a hint; the sequence is the proof.
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


# The same circuit, spelled the way each sim spells it. Kunos prefixes its own
# Assetto Corsa tracks with ``ks-``; ACC drops the prefix and renames outright
# (``cota`` for Austin, ``barcelona`` for Catalunya, ``indianapolis`` for the
# Speedway's road course). A table keyed on one spelling is invisible to the
# other game — which is the exact bug ``trackedges._by_shape`` was written to
# kill for the track drawings, and it would have shipped here too.
#
# Only aliases for the *same layout* belong here. ``spa1998`` is deliberately
# absent: it is a different circuit that happens to share a name, and giving it
# the modern corner positions would put Les Combes in the middle of a straight.
_ALIASES: dict[str, str] = {
    "ksnurburgring": "nurburgring", "nurburgringgp": "nurburgring",
    "ksredbullring": "redbullring", "spielberg": "redbullring",
    "cota": "austin", "circuitoftheamericas": "austin",
    "barcelona": "catalunya", "kscatalunya": "catalunya",
    "hungaroring": "budapest", "kshungaroring": "budapest",
    "ksbrandshatch": "brandshatch",
    "ksmonza": "monza", "monza66": "monza",
    "kssilverstone": "silverstone",
    "interlagos": "saopaulo", "ksinterlagos": "saopaulo",
    "autodromohermanosrodriguez": "mexicocity",
    "albertpark": "melbourne",
    "gillesvilleneuve": "montreal", "ksmontreal": "montreal",
    "bahrain": "sakhir", "ksbahrain": "sakhir",
    "sepanginternational": "sepang",
    "yasmarinacircuit": "yasmarina",
    "bathurst": "mountpanorama", "rtbathurst": "mountpanorama",
    "kszandvoort": "zandvoort", "circuitzandvoort": "zandvoort",
    "indianapolis": "ims", "indianapolisroad": "ims",
    "ksnorisring": "norisring",
    "kshockenheim": "hockenheim", "hockenheimring": "hockenheim",
    "kssuzuka": "suzuka",
    "ksimola": "imola",
    "ksspa": "spa",
}


def _key(track: str) -> str:
    """The circuit a sim's track string refers to."""
    s = _slug(track)
    return _ALIASES.get(s, s)


# track-slug -> ordered list of (name, approx apex pos). Anchored to a real
# Imola reference lap (BMW M4 GT3, 1:43.7) whose detected apexes were
# 0.143 / 0.291 / 0.351 / 0.484 / 0.585 / 0.693 / 0.844 — matched here to the
# known Imola corner sequence.
_CORNERS: dict[str, list[tuple[str | int, float]]] = {
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
    # Silverstone. The FIRST table not anchored to a recorded lap: the positions
    # are read off the bundled centreline (`tools/corner_atlas.py`), whose arc
    # length reproduces the lap-anchored positions of Monza, Spa and Suzuka to
    # 12-33 m against a 290-350 m tolerance.
    #
    # What corroborates the naming is the **sequence of directions**. Written out
    # from the circuit's own corner list — Abbey right, Farm left, Village right,
    # The Loop left, Aintree left, Brooklands left, Luffield right, Woodcote
    # right, Copse right, Maggotts left, Becketts right-left-right, Chapel left,
    # Stowe right, Vale left, Club right — it reads
    #
    #     R L R L L L R R R L R L R L R L R R
    #
    # and the geometry, which knows nothing about any of those names, produces
    # the same eighteen symbols in the same order. An eighteen-symbol binary
    # sequence matching by accident is one chance in 260 000, so this is not
    # "the positions look about right": it is the circuit identifying itself.
    #
    # Becketts is a sequence of three and gets one row; the other two fall back
    # to numbers, which is what `name_corners`' once-each rule is for.
    "silverstone": [
        ("Abbey", 0.067),          # right, r=37 m
        ("Farm Curve", 0.109),     # left, r=98 m
        ("Village", 0.151),        # right, r=23 m
        ("The Loop", 0.178),       # left, the tightest of the lap at r=15 m
        ("Aintree", 0.212),        # left onto the Wellington straight
        ("Brooklands", 0.340),     # left
        ("Luffield", 0.371),       # right
        ("Woodcote", 0.432),       # right onto the old pit straight
        ("Copse", 0.533),          # right, r=52 m
        ("Maggotts", 0.612),       # left, r=173 m
        ("Becketts", 0.632),       # right — the complex's first named apex
        ("Chapel", 0.713),         # left onto the Hangar straight
        ("Stowe", 0.863),          # right
        ("Vale", 0.937),           # left, r=20 m
        ("Club", 0.958),           # right onto the pit straight
    ],
    # Mount Panorama. Names and directions from the circuit's own corner list
    # (Wikipedia, "Mount Panorama Circuit"); positions from the centreline. The
    # two were joined by `corner_atlas.py --fit`, which lays an ordered list of
    # corners onto the detected apexes keeping their order, and the result agrees
    # with the source on **15 directions out of 15**.
    #
    # Two physical anchors say the alignment is on the real circuit and not on a
    # plausible-looking shift of it: Hell Corner to Griffins Bend measures 1116 m
    # (Mountain Straight), and Forrest's Elbow to The Chase measures 1116 m
    # (Conrod). Both are straights you can find on any map of this track.
    #
    # The Chase is three corners (right-left-right) and gets one row, like
    # Becketts and Ascari — `name_corners` hands each name out once and the other
    # two elements fall back to numbers rather than printing "The Chase" thrice.
    "mountpanorama": [
        ("Hell Corner", 0.044),       # left, r=24 m
        ("Griffins Bend", 0.223),     # right, after Mountain Straight
        ("The Cutting", 0.305),       # left, r=30 m, uphill
        ("Quarry Corner", 0.328),     # right
        ("Reid Park", 0.361),         # right
        ("Sulman Park", 0.527),       # left
        ("McPhillamy Park", 0.550),   # left, r=23 m
        ("Skyline", 0.589),           # right, at the crest
        ("The Dipper", 0.610),        # left, r=30 m
        ("Forrest's Elbow", 0.649),   # left, onto Conrod
        ("The Chase", 0.828),         # right — first of right-left-right
        ("Murray's Corner", 0.964),   # left, r=21 m, onto the pit straight
    ],
    # Interlagos. Same method, same source shape (Wikipedia, "Interlagos
    # Circuit"): the automatic fit agreed on 14 directions out of 14 — and was
    # still **wrong by one step**, which is worth writing down because it is the
    # limit of the method.
    #
    # It slid Curva do Sol onto the left-hander at 1424 m. The geometry refuses
    # that: between 744 m and 1424 m there is no corner at all, which is 680 m of
    # Reta Oposta, and Curva do Sol is the corner that *leads onto* the back
    # straight, not the one after it. So the corners here are stepped back one
    # place from what the solver proposed. A direction-agreement score cannot see
    # a straight; a person reading the metres can.
    #
    # Junção is likewise pinned by physics rather than by the solver: it is the
    # last slow corner before the climb to the line, and everything after it is
    # taken flat — so it is the tight r=27 m left at 3271 m, not one of the open
    # left-handers before it.
    #
    # Café is left out: the source names it, and it sits inside the run of
    # flat-out left-handers where nothing distinguishes one apex from the next.
    "saopaulo": [
        ("S do Senna", 0.087),        # left, r=24 m — the chicane's first element
        ("Curva do Sol", 0.173),      # left, onto the Reta Oposta
        ("Descida do Lago", 0.365),   # left, r=69 m
        ("Ferradura", 0.504),         # right, r=61 m
        ("Laranjinha", 0.540),        # right, r=25 m
        ("Pinheirinho", 0.571),       # left, r=32 m
        ("Bico de Pato", 0.647),      # right, r=18 m — the tightest of the lap
        ("Mergulho", 0.701),          # left, r=63 m
        ("Junção", 0.761),            # left, r=27 m — last slow corner
        ("Subida dos Boxes", 0.811),  # left, taken flat
        ("Arquibancadas", 0.854),     # left, taken flat
    ],
    # Zandvoort, from the circuit's own corner page (circuitzandvoort.nl/en/corners)
    # rather than an encyclopaedia — it names the corners in order and says which
    # way several of them go, and **all eight it states agree with the geometry**.
    #
    # Turns 9, 10 and 13 are left numbered: the circuit itself does not name
    # them. The characters corroborate the rest — Hugenholtz is the tight left
    # the page calls a "whirling bowl bend" (r=29 m), Hunserug its "mild but
    # extremely fast curve to the right" (r=123 m), Hans Ernst comes out
    # right-then-left, which is what a chicane is, and Arie Luyendijk is last
    # before the line at 91% of the lap.
    "zandvoort": [
        ("Tarzanbocht", 0.086),        # right hairpin, r=30 m
        ("Gerlachbocht", 0.107),       # right
        ("Hugenholtzbocht", 0.202),    # LEFT, banked, r=29 m
        ("Hunserug", 0.358),           # right, fast
        ("Slotemakerbocht", 0.409),    # right
        ("Scheivlak", 0.430),          # right, downhill
        ("Mastersbocht", 0.545),       # right, r=26 m
        ("Hans Ernst", 0.738),         # chicane, right then left
        ("Arie Luyendijkbocht", 0.908),  # right, banked, onto the straight
    ],
    # Brands Hatch, GP loop. Two sources were needed and they **disagree**, which
    # is why this table records how the disagreement was settled rather than just
    # its outcome. A guide summary called Paddock Hill Bend a left-hander and
    # admitted the direction was "implied by positioning"; a prose description
    # calls it, in words, "the right-hander at Paddock Hill Bend". The geometry
    # says right. Explicit beats inferred, and measured beats both.
    #
    # Taking only the directions a source states in words, all ten agree with the
    # geometry. One correction on top of the automatic fit, on the same physical
    # grounds that corrected Interlagos: the solver put Hawthorn on an r=36 m
    # apex, and the source calls Hawthorn "by far the fastest corner on the
    # circuit" — so it is the r=151 m one, and Westfield and Sheene step back
    # with it.
    "brandshatch": [
        ("Paddock Hill Bend", 0.058),  # right, r=94 m, downhill
        ("Druids", 0.158),             # right hairpin, r=24 m
        ("Graham Hill Bend", 0.202),   # left, r=118 m
        ("Surtees", 0.318),            # left, r=37 m, uphill
        ("Hawthorn Bend", 0.388),      # right, r=151 m — the fastest of the lap
        ("Westfield Bend", 0.519),     # right, r=86 m
        ("Sheene Curve", 0.605),       # right, r=36 m
        ("Stirling's", 0.768),         # LEFT, r=33 m — the only left of the sector
        ("Clearways", 0.881),          # right, r=53 m
        ("Clark Curve", 0.933),        # right, r=157 m, onto the straight
    ],
    # Nürburgring GP-Strecke — the first circuit curated by NUMBER rather than by
    # name, and deliberately so: almost every corner here is named after whoever
    # is paying (Veedol became NGK, the Audi-S became the Michael-Schumacher-S),
    # so a name is a subscription and a number is a fact. The turn numbers are
    # what the guides, the marshals and the driver in the next car all use.
    #
    # Directions from a track guide, taken only where it writes them in words —
    # "a sharp downhill right-hand hairpin", "a very tricky, high-speed
    # left-right chicane", "a fast left into right chicane". All fifteen agree
    # with the geometry, and four characters corroborate independently: T1 comes
    # out at r=16 m (the tightest of the lap, and the guide calls it a hairpin),
    # T7 at r=31 m (its other hairpin), T12 at r=110 m (the guide's "easily
    # flat-out kink") and T13-T14 come out left-then-right, which is the chicane
    # the guide describes in that order.
    #
    # Numbered ALL the way round on purpose. A half-numbered circuit prints an
    # official "Corner 3" next to a detector-counted "Corner 4" and nothing on
    # screen says which is which — worse than no numbering at all.
    "nurburgring": [
        (1, 0.079),   # right hairpin, r=16 m
        (2, 0.108),   # left — Mercedes Arena begins
        (3, 0.165),   # left
        (4, 0.187),   # right — ends the Arena
        (5, 0.286),   # left sweep
        (6, 0.314),   # right
        (7, 0.428),   # right hairpin, r=31 m
        (8, 0.506),   # left — the S begins
        (9, 0.540),   # right
        (10, 0.623),  # left
        (11, 0.655),  # right
        (12, 0.747),  # right, r=110 m — flat out
        (13, 0.840),  # left — the chicane begins
        (14, 0.891),  # right
        (15, 0.911),  # right, onto the pit straight
    ],
    # Circuit of the Americas, by NUMBER: only Turn 1 has a name anybody uses,
    # and its twenty turns are what every guide and every driver counts in.
    #
    # Directions from a track guide written in prose — "the sharp left-hander",
    # "Turn 3 is a left-hand corner, Turn 4 is a right-hand corner", "the
    # right-hand, sweeping eighth turn", "the triple-apex Turns 16-18". All
    # fourteen it states agree with the geometry.
    #
    # It took a second read to get there, and the reason is worth keeping. At the
    # tool's default resolution the esses merged and T3/T4 came out swapped —
    # the only two of fourteen that fought the source. Read at 77 m of minimum
    # separation instead of 110 they resolve, all fourteen agree, and T6 appears
    # as two apexes of one corner, which is what the guide calls "a long,
    # sweeping right-hander". The conflict was our resolution, not a
    # disagreement about the circuit (see `corner_atlas.PARAMS`).
    #
    # Three anchors nobody could fake: T1 is the tightest corner of the lap at
    # r=13 m and the guide calls it sharp; T11 is followed by **1195 m with no
    # corner in it**, against a published back straight of 1016 m; and T16-T18
    # come out as three consecutive rights about 100 m apart, which is the
    # triple-apex the guide describes.
    "austin": [
        (1, 0.121),   # left, r=13 m — the tightest of the lap, uphill
        (2, 0.172),   # right
        (3, 0.212),   # left — the esses begin
        (4, 0.231),   # right
        (5, 0.248),   # left
        (6, 0.286),   # right, long
        (7, 0.313),   # left
        (8, 0.339),   # right
        (9, 0.360),   # left
        (10, 0.397),  # left
        (11, 0.471),  # left hairpin, r=15 m — onto the back straight
        (12, 0.688),  # left, after 1195 m of nothing
        (13, 0.730),  # right
        (14, 0.747),  # right
        (15, 0.781),  # left, r=13 m
        (16, 0.821),  # right — the triple apex begins
        (17, 0.838),  # right
        (18, 0.856),  # right
        (19, 0.917),  # left
        (20, 0.975),  # left, onto the pit straight
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
    # Hockenheimring, GP layout. Curated by NAME and not by number, and this is
    # the circuit that shows why the distinction pays: the one guide that laid
    # out all seventeen turns in order **invented most of them** — it calls the
    # Parabolika a "very long, constant-radius left" (it is a straight) and the
    # Spitzkehre an "extremely tight hairpin left". A prose source states the
    # Spitzkehre is "a 170-degree right-hander", and the geometry's tightest
    # apex of the lap (r=13 m) is a right, sitting exactly there. Two against
    # one, and the two are the ones that were not generated.
    #
    # So only corners whose name is tied to a distinctive feature went in, each
    # confirmed by where it falls rather than by a turn number:
    #   Nordkurve   first apex after the line (265 m), the only corner up there
    #   Spitzkehre  the tightest apex of the whole lap, at the end of the
    #               Parabolika straight
    #   Sachskurve  the only 180° left, which a source places "in front of the
    #               Mercedes Grandstand"; read as two peaks 174 m apart, so the
    #               position below is between them, where the apex actually is
    #   Elf-Kurve + Südkurve  the same source's "flowing right and right twin
    #               corner" that follows the Sachskurve — and the geometry has
    #               exactly two rights left before the line
    "hockenheim": [
        ("Nordkurve", 0.058),        # right, r=25 m, off the pit straight
        ("Spitzkehre", 0.462),       # RIGHT hairpin, r=13 m — tightest of the lap
        ("Sachskurve", 0.848),       # left, 180°, read as two apexes
        ("Elf-Kurve", 0.907),        # right, r=34 m
        ("Südkurve", 0.938),         # right, onto the start-finish straight
    ],
    # Circuit de Barcelona-Catalunya. Held back on 2026-08-03 because the
    # bundled trace has no chicane in the last third and the ACC guides describe
    # one — and that hold was **right about the numbers and wrong about the
    # names**. The chicane changed the turn count (14 against 16) and therefore
    # every number after Turn 13, but it changed no name: Campsa is Campsa in
    # both. Names are anchored to the corner, numbers to the layout.
    #
    # The last corner is left out anyway. New Holland is the one name that sits
    # *after* where the chicane was, so it is the one whose position genuinely
    # moves between the two layouts, and a driver on either one loses nothing by
    # its absence.
    #
    # Two independent guides, one written for each layout, agree on every
    # direction below. The alignment is pinned by three things a source cannot
    # fake: Repsol reads as an increasing-radius 180° right (r=45→81→138 m),
    # which is the phrase both sources use for it; La Caixa is the tightest left
    # of the lap (r=14 m) at the end of the longest straight after the pit
    # straight (558 m); and Seat is the first slow left after the long run of
    # rights. Where a corner is read as several apexes the name sits on the
    # tightest of them, which is where the driver is slowest.
    "catalunya": [
        ("Elf", 0.180),              # right, r=30 m — first corner off the straight
        ("Renault", 0.252),          # long right, r=78 m
        ("Repsol", 0.366),           # right, 180°, opening radius
        ("Seat", 0.463),             # LEFT, r=29 m, downhill
        ("Campsa", 0.634),           # right, fast, blind over the crest
        ("La Caixa", 0.754),         # LEFT, r=14 m — tightest of the lap
        ("Banc Sabadell", 0.804),    # right, long U
        ("Europcar", 0.865),         # right, r=24 m
    ],
    # Autódromo Hermanos Rodríguez, and it gets **one row**, which is the honest
    # size of what could be established. Everything else this circuit is famous
    # for is a *section* and not a corner — the Foro Sol is a stadium the track
    # runs through, the Esses are Turns 7 to 11 — and a section has no apex to
    # anchor. The rest of the lap keeps its numbers.
    #
    # The Peraltada is the banked 180° right that used to close the lap; since
    # the 2015 rebuild only its second half is driven, and the circuit renamed
    # that half after Nigel Mansell. The older name is kept here because it is
    # the one the sims, the guides and the drivers use, and because a corner
    # renamed once can be renamed again — the same reasoning that put the
    # Nürburgring in numbers.
    "mexicocity": [
        ("Peraltada", 0.936),        # right, r=169 m, banked, onto the straight
    ],
    # Sepang, e il circuito che ha mandato in pensione una nostra regola.
    #
    # Era fermo perché il rilevatore trova 18 apici e il circuito ha 15 curve, e
    # la regola diceva: conteggi diversi, niente tabella. Sbagliata — la
    # numerazione ufficiale **fonde i complessi**, e la fonte lo dice da sola
    # chiamando le T7-T8 «un lungo destro a doppio apex». Diciotto rilievi per
    # quindici curve non è un altro tracciato: è la stessa strada contata in due
    # modi. Il criterio buono era già qui e non lo stavo usando: la **sequenza
    # dei versi**, che una fonte non può azzeccare per caso quindici volte.
    #
    # Il verso di ogni curva è **forzato**, non dedotto: la fonte dichiara «5
    # sinistre e 10 destre» e ne nomina a parole esattamente cinque (T2, T6, T9,
    # T12, T15). Le restanti dieci sono destre per aritmetica, non per fiducia.
    # Sulla geometria l'allineamento dà **15 su 15**.
    #
    # E tre corroborazioni che nessuna guida può fabbricare: la traccia misura
    # 5535 m contro i 5543 pubblicati; il rettilineo principale esce 968 m; e
    # fra T14 e T15 ci sono 950 m di niente — che è il rettilineo posteriore in
    # cui la fonte dice che la T14 ti lancia.
    #
    # Per numero: i nomi di Sepang sono la KLIA curve (l'aeroporto), Berjaya
    # Tioman (un resort) e Sunway Lagoon (un parco). Sponsorizzazioni, come al
    # Nürburgring — e un numero è un fatto.
    "sepang": [(n, p) for n, p in enumerate([
        0.114, 0.144, 0.165, 0.201, 0.290, 0.347, 0.467, 0.488,
        0.571, 0.601, 0.637, 0.702, 0.725, 0.768, 0.939], start=1)],
    # Red Bull Ring. Anche questo era fermo per il conteggio (15 rilievi contro
    # 10 curve), e anche questo si scioglie con la sequenza dei versi: una guida
    # le dichiara tutte e dieci a parole — R L R R R L L R R R — e l'allineamento
    # dà **10 su 10**.
    #
    # La conferma più bella non viene da una fonte. È l'unico dei circuiti fermi
    # su cui esistono **giri veri in archivio**, e quei giri trovano **nove**
    # curve: manca la T2, che un'altra guida liquida in parole sue come «un kink
    # a sinistra tutto gas — non è una curva vera, ma la includiamo per far
    # contenti i signori in giacca». Il rilevatore, che non ha letto la guida, è
    # d'accordo. E la geometria le dà r=172 m, cioè la misura di quella frase.
    #
    # **Ancorata ai giri, non alla traccia**, e qui c'è la scoperta che vale
    # oltre questo circuito: le due sorgenti concordano sulla forma e non
    # sull'origine. Su tutte e otto le curve che i giri vedono, la traccia è
    # avanti di 0.019-0.043 (mediana **0.027**, cioè 116 m). È uno scarto
    # *costante*, quindi non è l'apex guidato che anticipa quello geometrico —
    # quello varierebbe col tipo di curva — è lo zero della traccia che non è il
    # traguardo del gioco. Sulle piste dove avevamo entrambi (Monza, Spa,
    # Suzuka) lo scarto era 12-33 m; qui è quattro volte tanto. Le tabelle
    # derivate dalla sola traccia restano dentro _NAME_TOL, ma questo è il
    # margine che consumano.
    #
    # T2 e T8 non hanno una posizione misurata dai giri (l'una non è una curva,
    # l'altra l'ha vista un giro solo) e sono la traccia meno quello scarto.
    "redbullring": [(n, p) for n, p in enumerate([
        0.076, 0.221, 0.297, 0.486, 0.532,
        0.616, 0.674, 0.719, 0.854, 0.895], start=1)],
    # Shanghai. Era fermo per «conteggio irraggiungibile», che era un modo
    # elegante di dire che il rilevatore ne trova 20 e il circuito ne ha 16. La
    # traccia però è la strada giusta — 5440 m contro 5451 pubblicati — e i
    # tredici versi che una fonte dichiara **a parole** tornano tutti e tredici.
    #
    # Il solutore automatico ha allungato, per la quarta volta e per il motivo
    # di sempre: fra la T12 e il tornante ci sono quattro destre e la prominenza
    # lo tira su quelle strette. L'ancoraggio giusto è il **buco**, come a COTA
    # e a Interlagos: la fonte dice che il lungo rettilineo sta fra T13 e T14, e
    # nella geometria c'è un solo vuoto da **1284 m**, fra 0.647 e 0.883. Quindi
    # T13 sta prima e T14 dopo, e il resto viene di conseguenza.
    #
    # Quattro conferme che nessuna guida può fabbricare:
    #   il tornante  è l'apice più stretto del giro (r=8 m) ed è **alla fine**
    #                di quel rettilineo, che è dove la fonte lo mette
    #   la T15       «parte del complesso del tornante» esce a 0.903, 109 m
    #                dopo, con r=143 m: l'apertura del tornante
    #   la lumaca    T1-T2, «una lunghissima curva a destra», si legge come tre
    #                apici a raggio **calante** (81→68→41 m)
    #   la T13       «diventa sempre meno stretta» → 78→86 m, e la posizione qui
    #                è il punto di mezzo fra i suoi due apici
    "shanghai": [(n, p) for n, p in enumerate([
        0.114, 0.137, 0.163, 0.193, 0.249, 0.296, 0.366, 0.434,
        0.473, 0.493, 0.578, 0.599, 0.633, 0.883, 0.903, 0.952], start=1)],
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


def landmark_at(track: str, pos: float, lang: str | None = None,
                typed=None) -> str | None:
    """Visual description of the braking landmark nearest ``pos``, or ``None`` if
    the track has no verified landmark within tolerance.

    ``pos`` is a normalizedCarPosition — pass the reference lap's braking onset,
    so the phrase describes where the *reference* brakes ("al cordolo
    bianco-rosso") rather than an abstract distance. The returned string carries
    its own preposition, ready to drop after a verb ("il riferimento frena …").
    """
    # What the driver typed wins, and here it wins harder than it does for a
    # corner name. Roadmap item 2 stalled because the *words* cannot be sourced
    # from a desk: two independent guides contradicted each other on almost
    # every Imola corner, and no measurement arbitrates between a 50 m board and
    # a 100 m one. The person looking out of the window settles it.
    #
    # Their phrase is returned in whichever language the page is in, unchanged.
    # It is not a string with a translation — it is what they see.
    if typed is not None:
        mine = typed.of(pos)
        if mine:
            return mine

    table = _LANDMARKS.get(_key(track))
    if not table:
        return None
    it, en, p = min(table, key=lambda t: abs(t[2] - pos))
    if abs(p - pos) > _LANDMARK_TOL:
        return None
    from .i18n import current_language
    return it if (lang or current_language()) == "it" else en


def _word(lang: str | None) -> str:
    from .i18n import current_language
    return "Curva" if (lang or current_language()) == "it" else "Corner"


def render(label: str | int, lang: str | None = None) -> str:
    """A curated entry as the driver reads it.

    A proper noun is kept as-is — "Parabolica" is "Parabolica" in every language.
    An **integer** is the circuit's own turn number, and is rendered in the
    reader's language. The distinction matters more than it looks: most modern
    circuits name nothing and number everything, and their numbers are facts
    published on the track map, not our count of what a detector found.
    """
    return label if isinstance(label, str) else f"{_word(lang)} {label}"


def corner_name(track: str, index: int, apex_pos: float,
                lang: str | None = None, direction: str = "", custom=None) -> str:
    """Name for a detected corner, by nearest curated apex, else ``Corner N`` /
    ``Curva N`` per language.

    The fallback number is **the detector's count**, not the circuit's: it says
    "the seventh corner I found", which on a track whose table we don't have is
    the only honest thing to say. Where a circuit's real numbering is curated it
    comes through the table above instead, and then the number on screen is the
    one painted on the track map.

    ``direction`` is the way this corner actually turns, when the lap carries
    the coordinates to know. Passing it is what stops a name from reaching the
    corner next door — this function names one corner at a time and has none of
    the once-each protection ``name_corners`` uses.
    """
    if custom is not None:
        typed = custom.of(apex_pos)
        if typed:
            return typed

    table = _CORNERS.get(_key(track))
    if table:
        usable = [t for t in table if _direction_ok(track, t[0], direction)]
        if usable:
            label, pos = min(usable, key=lambda t: abs(t[1] - apex_pos))
            if abs(pos - apex_pos) <= _NAME_TOL:
                return render(label, lang)
    return f"{_word(lang)} {index + 1}"


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
    # From here down the directions are measured off the centreline rather than
    # off a lap, and they are the whole reason these tables are trusted: each was
    # written from a published corner list and then had to survive the geometry
    # saying which way that corner actually turns. Recording them keeps the
    # evidence next to the claim.
    "silverstone": {
        "Abbey": "right", "Farm Curve": "left", "Village": "right",
        "The Loop": "left", "Aintree": "left", "Brooklands": "left",
        "Luffield": "right", "Woodcote": "right", "Copse": "right",
        "Maggotts": "left", "Becketts": "right", "Chapel": "left",
        "Stowe": "right", "Vale": "left", "Club": "right",
    },
    "mountpanorama": {
        "Hell Corner": "left", "Griffins Bend": "right", "The Cutting": "left",
        "Quarry Corner": "right", "Reid Park": "right", "Sulman Park": "left",
        "McPhillamy Park": "left", "Skyline": "right", "The Dipper": "left",
        "Forrest's Elbow": "left", "Murray's Corner": "left",
        # The Chase is right-left-right: a complex has no single direction, so
        # it is not checked — the same call already made for Bus Stop.
    },
    "brandshatch": {
        "Paddock Hill Bend": "right", "Druids": "right",
        "Graham Hill Bend": "left", "Surtees": "left", "Hawthorn Bend": "right",
        "Westfield Bend": "right", "Sheene Curve": "right", "Stirling's": "left",
        "Clearways": "right", "Clark Curve": "right",
    },
    "nurburgring": {
        1: "right", 2: "left", 3: "left", 4: "right", 5: "left", 6: "right",
        7: "right", 8: "left", 9: "right", 10: "left", 11: "right",
        12: "right", 13: "left", 14: "right", 15: "right",
    },
    "austin": {
        1: "left", 2: "right", 3: "left", 4: "right", 5: "left", 6: "right",
        7: "left", 8: "right", 9: "left", 10: "left", 11: "left", 12: "left",
        13: "right", 14: "right", 15: "left", 16: "right", 17: "right",
        18: "right", 19: "left", 20: "left",
    },
    "zandvoort": {
        "Tarzanbocht": "right", "Gerlachbocht": "right",
        "Hugenholtzbocht": "left", "Hunserug": "right",
        "Slotemakerbocht": "right", "Scheivlak": "right",
        "Mastersbocht": "right", "Arie Luyendijkbocht": "right",
        # Hans Ernst is a chicane: not checked.
    },
    "saopaulo": {
        "Curva do Sol": "left", "Descida do Lago": "left", "Ferradura": "right",
        "Laranjinha": "right", "Pinheirinho": "left", "Bico de Pato": "right",
        "Mergulho": "left", "Junção": "left", "Subida dos Boxes": "left",
        "Arquibancadas": "left",
        # S do Senna is a left-right chicane: not checked.
    },
    "hockenheim": {
        "Nordkurve": "right", "Spitzkehre": "right", "Sachskurve": "left",
        "Elf-Kurve": "right", "Südkurve": "right",
    },
    "catalunya": {
        "Elf": "right", "Renault": "right", "Repsol": "right", "Seat": "left",
        "Campsa": "right", "La Caixa": "left", "Banc Sabadell": "right",
        "Europcar": "right",
    },
    "mexicocity": {"Peraltada": "right"},
    "sepang": {
        1: "right", 2: "left", 3: "right", 4: "right", 5: "right", 6: "left",
        7: "right", 8: "right", 9: "left", 10: "right", 11: "right",
        12: "left", 13: "right", 14: "right", 15: "left",
    },
    "redbullring": {
        1: "right", 2: "left", 3: "right", 4: "right", 5: "right",
        6: "left", 7: "left", 8: "right", 9: "right", 10: "right",
    },
    # T5 non e' dichiarata da nessuna fonte trovata: resta fuori dal controllo
    # invece di essere dedotta. Un verso indovinato passerebbe il test e
    # sposterebbe un nome, che e' il modo peggiore di sbagliare qui.
    "shanghai": {
        1: "right", 2: "right", 3: "left", 4: "left", 6: "right",
        7: "left", 8: "right", 9: "left", 10: "left", 11: "left",
        12: "right", 13: "right", 14: "right", 15: "right", 16: "left",
    },
}


def _direction_ok(track: str, name: str | int, direction: str) -> bool:
    """Does this corner turn the way the curated one does?

    True whenever either side has nothing to say — a lap with no coordinates
    can't classify a corner, and most curated corners have no measured direction
    yet. Unknown must not mean "no".
    """
    want = _DIRECTIONS.get(_key(track), {}).get(name, "")
    return not want or not direction or want == direction


def name_corners(track: str, corners, lang: str | None = None,
                 learned=None, custom=None) -> list[str]:
    """Names for a list of detected corners (objects with ``index``/``apex_pos``).

    ``custom`` is what the driver typed (:mod:`accoach.cornernames`) and it wins
    outright — over the curated table, over the learned number, over everything.
    That is not politeness: on the twelve bundled circuits we could not curate
    and the ten ACC circuits with no geometry at all, the driver is the only
    source there is. And where a table *does* exist, being told the name is
    wrong is information, not vandalism — it is stored in a file they can read,
    and taking it back off is the same gesture as putting it on.

    Each curated name is handed out **once**. Naming corner-by-corner is fine in
    isolation but wrong for a set: the detector's corner count is not fixed, and
    with a different car or a slower line a multi-part complex splits — Ascari
    into three, say. Every part is then nearest to the same curated apex and the
    report grows three rows called "Variante Ascari", in the losses, in the
    corner speeds, and in what the coach says out loud. Whichever part is nearest
    to the real apex keeps the name; the others fall back to a number, which is
    vague but at least tells them apart.
    """
    named: list[str | int | None] = [None] * len(corners)

    # The driver's own names go on first, so the curated pass below — which
    # skips anything already named — cannot take a corner back off them. Each is
    # handed out once for the same reason a curated name is: a complex the
    # detector split into three parts would otherwise print one name three times.
    if custom is not None and len(custom):
        for pos, label in custom.names:
            best, best_d = None, custom.tol
            for i, c in enumerate(corners):
                if named[i] is not None:
                    continue
                d = abs(c.apex_pos - pos)
                if d <= best_d:
                    best, best_d = i, d
            if best is not None:
                named[best] = label

    table = _CORNERS.get(_key(track))
    if table:
        for label, pos in table:
            best, best_d = None, _NAME_TOL
            for i, c in enumerate(corners):
                if named[i] is not None:
                    continue
                if not _direction_ok(track, label, getattr(c, "direction", "")):
                    continue
                d = abs(c.apex_pos - pos)
                if d <= best_d:
                    best, best_d = i, d
            if best is not None:
                named[best] = label

    # What is left keeps a number, and *which* number is the point. The
    # detector's own index is the count of what it found on this lap, and that
    # count moves: sixteen Monza laps by one car produce five to nine corners,
    # so the corner at 0.371 answers to "Corner 4" on one lap and "Corner 5" on
    # the next, with everything after it sliding too. `learned` is the same
    # circuit's corners as the driver's own laps agree they exist
    # (:mod:`accoach.cornermap`), and numbering against that holds still.
    #
    # An apex the map does not recognise still falls back to the detector's
    # index: a kink that turned up on one odd lap has no number of its own, and
    # inventing one for it is where the sliding started.
    out: list[str] = []
    for i, c in enumerate(corners):
        if named[i] is not None:
            out.append(render(named[i], lang))
            continue
        n = learned.number_of(c.apex_pos) if learned is not None else None
        out.append(f"{_word(lang)} {n}" if n
                   else corner_name("", c.index, c.apex_pos, lang))
    return out


def has_names(track: str) -> bool:
    return _key(track) in _CORNERS
