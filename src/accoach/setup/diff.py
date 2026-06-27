"""Compute a human-readable diff between two ACC setups.

Used to show "old -> new" before writing, both in clicks (authoritative) and in
best-effort physical units, so the driver can confirm a change knowingly.
"""

from __future__ import annotations

from dataclasses import dataclass

from .acc_format import slot_labels


@dataclass(frozen=True)
class Change:
    group: str
    label: str          # parameter label
    slot: str           # slot label ("Post-Dx", "Ant", or "" for scalars)
    old_click: int
    new_click: int
    old_phys: str
    new_phys: str

    @property
    def delta(self) -> int:
        return self.new_click - self.old_click

    def __str__(self) -> str:
        where = f" [{self.slot}]" if self.slot else ""
        sign = f"{self.delta:+d}"
        return (
            f"{self.label}{where}: {self.old_click} → {self.new_click} "
            f"({sign} click)  {self.old_phys} → {self.new_phys}"
        )


def diff(before, after) -> list[Change]:
    """All per-slot differences between two setups (same car/format assumed)."""
    changes: list[Change] = []
    for spec in before.specs():
        if not (before.present(spec) and after.present(spec)):
            continue
        n = before.slots(spec)
        if after.slots(spec) != n:
            continue
        labels = slot_labels(n) if n > 1 else ("",)
        for slot in range(n):
            old_c = before.click(spec, slot)
            new_c = after.click(spec, slot)
            if old_c == new_c:
                continue
            changes.append(Change(
                group=spec.group,
                label=spec.label,
                slot=labels[slot],
                old_click=old_c,
                new_click=new_c,
                old_phys=before.physical(spec, slot),
                new_phys=after.physical(spec, slot),
            ))
    return changes


def format_diff(changes: list[Change]) -> str:
    """Render a diff as grouped, indented text."""
    if not changes:
        return "(nessuna modifica)"
    out: list[str] = []
    current = None
    for c in changes:
        if c.group != current:
            out.append(f"{c.group}:")
            current = c.group
        out.append(f"  {c}")
    return "\n".join(out)
