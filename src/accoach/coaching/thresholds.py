"""Coaching thresholds shared by more than one module.

Keeping these in one place stops two surfaces from disagreeing after a tweak —
e.g. the live Focus coach saying "no recurring weakness" while the analysis
Trends tab lists the same corner as *systematic*, because each had its own copy
of the constant.
"""

from __future__ import annotations

# A per-corner time loss below this (≈1.2 tenths) isn't worth coaching or
# training — used to call a corner a real weakness vs noise.
SIGNIF_LOSS_MS = 120.0

# Fraction of the laps considered in which a significant loss must recur for the
# corner to count as *systematic* (a weakness to train) rather than *sporadic*.
RECUR_FRAC = 0.5
