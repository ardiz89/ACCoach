"""Cross-lap analysis: systematic vs sporadic losses + the benchmark ladder."""
from accoach.coaching.cue import CueCategory
from accoach.coaching.debrief import CornerLoss, LapDebrief
from accoach.coaching.trends import (
    benchmark_levels,
    classify_losses,
)


def _loss(index: int, ms: float, category: CueCategory = CueCategory.BRAKE_LATER) -> CornerLoss:
    return CornerLoss(index=index, entry_pos=0.2, apex_pos=0.3, exit_pos=0.4,
                      lost_ms=ms, category=category, message="m")


def _debrief(*losses: CornerLoss) -> LapDebrief:
    return LapDebrief("car", "track", 101000, 100000, losses=list(losses))


# --- systematic vs sporadic ------------------------------------------------

def test_recurring_loss_is_systematic():
    debriefs = [_debrief(_loss(0, 300)) for _ in range(4)]
    trends = classify_losses(debriefs)
    assert len(trends) == 1
    assert trends[0].corner_index == 0
    assert trends[0].systematic is True
    assert trends[0].kind == "systematic"
    assert trends[0].occurrences == 4


def test_one_off_loss_is_sporadic():
    # Big loss, but only once in four laps → not a weakness to train.
    debriefs = [_debrief(_loss(0, 900)), _debrief(), _debrief(), _debrief()]
    trends = classify_losses(debriefs)
    assert trends[0].systematic is False
    assert trends[0].kind == "sporadic"


def test_small_recurring_loss_is_not_systematic():
    debriefs = [_debrief(_loss(0, 50)) for _ in range(4)]   # recurs but trivial
    trends = classify_losses(debriefs)
    assert trends[0].systematic is False


def test_trends_sorted_by_total_cost():
    debriefs = [
        _debrief(_loss(0, 150), _loss(1, 400)),
        _debrief(_loss(0, 150), _loss(1, 400)),
        _debrief(_loss(0, 150), _loss(1, 400)),
    ]
    trends = classify_losses(debriefs)
    assert [t.corner_index for t in trends] == [1, 0]       # corner 1 costs more
    assert all(t.systematic for t in trends)


def test_dominant_category_wins():
    debriefs = [
        _debrief(_loss(0, 300, CueCategory.BRAKE_LATER)),
        _debrief(_loss(0, 300, CueCategory.BRAKE_LATER)),
        _debrief(_loss(0, 300, CueCategory.CARRY_SPEED)),
    ]
    assert classify_losses(debriefs)[0].category is CueCategory.BRAKE_LATER


def test_empty_debriefs():
    assert classify_losses([]) == []


# --- benchmark levels ------------------------------------------------------

def test_levels_best_only():
    levels = benchmark_levels(90000)
    assert [lv.key for lv in levels] == ["best"]
    assert levels[0].gain_ms == 0


def test_levels_with_ideal_and_pro():
    levels = benchmark_levels(90000, ideal_ms=89000, pro_ms=88000)
    keys = {lv.key: lv for lv in levels}
    assert set(keys) == {"best", "ideal", "pro"}
    assert keys["ideal"].gain_ms == 1000        # 1.0s of consistency available
    assert keys["pro"].gain_ms == 2000          # 2.0s to the PRO ceiling


def test_levels_pro_slower_than_you_is_negative_gain():
    levels = benchmark_levels(88000, pro_ms=90000)   # you beat the imported PRO
    pro = next(lv for lv in levels if lv.key == "pro")
    assert pro.gain_ms == -2000


def test_levels_empty_without_best():
    assert benchmark_levels(0) == []


def test_level_labels_translate():
    en = {lv.key: lv.label for lv in benchmark_levels(90000, ideal_ms=89000, lang="en")}
    it = {lv.key: lv.label for lv in benchmark_levels(90000, ideal_ms=89000, lang="it")}
    assert en["best"] == "Your best lap" and it["best"] == "Tuo miglior giro"
    assert it["ideal"] == "Ideale teorico"
