"""Read and write Assetto Corsa / ACC car setups (the ``setup/`` foundation).

This package is the class-agnostic base of the "race engineer" feature (see
``ENGINEER.md``): it loads a real setup file (ACC ``.json`` or AC ``.ini``), lets
us adjust parameters and write the result back safely (backup + atomic write +
undo). The state-machine that *decides* what to change lives in
``accoach.engineer``; this layer only reads and writes the file.

Design note — we operate in **clicks**, not physical units. ACC stores every
adjustable value as an integer index ("click"), not as psi/degrees, and the
index->physical mapping is per-car and easy to get wrong. Writing a click delta
("rear pressure +2 clicks") is always correct, and it is exactly the method the
setup tutorials teach ("2 click alla volta"). Physical values (psi, %, mm) are
layered on top as best-effort *display* annotations only.
"""

from .ac_format import AcSetup
from .acc_format import (
    AccSetup,
    ParamSpec,
    SETUP_PARAMS,
    load,
    slot_labels,
)
from .diff import Change, diff, format_diff
from .loader import load_any
from .store import (
    AC_SETUPS_ROOT,
    DEFAULT_ROOTS,
    SETUPS_ROOT,
    backup,
    list_setups,
    save,
    undo,
)

__all__ = [
    "AccSetup",
    "AcSetup",
    "ParamSpec",
    "SETUP_PARAMS",
    "load",
    "load_any",
    "slot_labels",
    "Change",
    "diff",
    "format_diff",
    "SETUPS_ROOT",
    "AC_SETUPS_ROOT",
    "DEFAULT_ROOTS",
    "backup",
    "list_setups",
    "save",
    "undo",
]
