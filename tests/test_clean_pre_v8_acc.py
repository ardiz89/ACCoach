"""A pre-v8 ACC lap says it's clean because nothing checked, not because it was.

The measurement behind this, from 2026-08-02: the elected reference at Monza was
a 1:53.712 recorded on 21 July — two seconds clear of anything since, marked
clean, and with **49% of its points off the asphalt** through the Variante della
Roggia when checked against the track surface. It was fastest because it cut,
and eligible because it claimed to be clean. Everything downstream had been
measured against it.
"""
from accoach.recording.catalog import LapCatalog, _clean_to_int
from accoach.recording.storage import _catalog_path, save_lap

import synth


# --- the rule itself -------------------------------------------------------

def test_a_pre_v8_acc_lap_that_claims_clean_is_demoted_to_unknown():
    assert _clean_to_int(True, 7, "dry_compound") == -1


def test_the_same_lap_from_v8_onwards_is_believed():
    """v8 is the line: from there the flag comes from ACC's own `isValidLap`."""
    assert _clean_to_int(True, 8, "dry_compound") == 1
    assert _clean_to_int(True, 11, "dry_compound") == 1


def test_an_old_ac_lap_keeps_its_verdict():
    """On AC `numberOfTyresOut` works — it was validated live at Spa. Demoting
    those too would throw away years of good history to fix ACC's problem."""
    assert _clean_to_int(True, 7, "Soft (S)") == 1
    assert _clean_to_int(True, 7, "Semislicks (SM)") == 1


def test_a_dirty_verdict_from_that_era_still_counts():
    """The inert path can only ever say "clean". A False therefore came from
    somewhere real, and discarding it would be throwing away the one finding the
    broken instrument did produce."""
    assert _clean_to_int(False, 7, "dry_compound") == 0


def test_never_recorded_stays_never_recorded():
    assert _clean_to_int(None, 7, "dry_compound") == -1
    assert _clean_to_int(None, 2, "") == -1


def test_wet_is_recognised_as_acc_too():
    """ACC writes one of two canonical strings; a rule that only knew the dry
    one would trust every wet lap of that era."""
    assert _clean_to_int(True, 7, "wet_compound") == -1


# --- what it changes for the driver ---------------------------------------

def _lap(tmp_path, *, ms, schema, clean, compound, when):
    """A lap on disk claiming to have been written by ``schema``.

    The schema has to be forced into the file after saving: `Lap.to_dict` always
    stamps the *current* version, which is right for a recorder and useless for a
    test about old files. Setting `lap.schema_version` alone silently changes
    nothing — the first version of this test did exactly that and passed for the
    wrong reason.
    """
    import gzip
    import json

    lap = synth.build_lap()
    synth.retime(lap, ms)
    lap.clean = clean
    lap.tyre_compound = compound
    lap.recorded_utc = when
    path = save_lap(lap, tmp_path)
    d = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    d["schema"] = schema
    path.write_bytes(gzip.compress(json.dumps(d).encode("utf-8")))
    return path


def _reference(tmp_path):
    with LapCatalog(_catalog_path(tmp_path)) as cat:
        # `upsert`, not `sync`: save_lap already indexed these paths (with the
        # current schema, before `_lap` forced the old one into the file), and
        # `sync` deliberately skips files it already knows. This re-reads them.
        for p in tmp_path.glob("*.lap.json.gz"):
            cat.upsert(p)
        car, track = synth.build_lap().car_model, synth.build_lap().track
        return cat.best_reference_path(car, track)


def test_a_judged_lap_now_outranks_a_faster_unjudged_one(tmp_path):
    """The whole point. The old lap is still the fastest and still eligible —
    it just stops being the benchmark while a lap someone actually judged
    exists."""
    old = _lap(tmp_path, ms=113712, schema=7, clean=True,
               compound="dry_compound", when="2026-07-21T14:26:00+00:00")
    new = _lap(tmp_path, ms=115902, schema=11, clean=True,
               compound="dry_compound", when="2026-08-02T15:52:00+00:00")
    elected = _reference(tmp_path)
    assert elected == str(new), "the confirmed-clean lap wins on 2.2 s slower"
    assert elected != str(old)


def test_with_nothing_better_the_old_lap_is_still_used(tmp_path):
    """Demoted to unknown, not discarded: a doubtful benchmark still beats
    telling the driver there is no reference at all. This is the same deliberate
    choice `best_reference_path` makes about conditions."""
    old = _lap(tmp_path, ms=113712, schema=7, clean=True,
               compound="dry_compound", when="2026-07-21T14:26:00+00:00")
    assert _reference(tmp_path) == str(old)


def test_a_lap_the_old_rule_called_dirty_is_still_excluded(tmp_path):
    """It stays out of the election entirely, exactly as before."""
    _lap(tmp_path, ms=100000, schema=7, clean=False,
         compound="dry_compound", when="2026-07-21T14:00:00+00:00")
    keep = _lap(tmp_path, ms=115902, schema=11, clean=True,
                compound="dry_compound", when="2026-08-02T15:52:00+00:00")
    assert _reference(tmp_path) == str(keep)
