"""
ppt_reflex/diff_log.py — snapshot-based mutation trace
Tracks per-slide changes between snap_before and snap_after for incremental builds.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class DiffReport:
    entries: list = field(default_factory=list)
    changed_elem_ids: set = field(default_factory=set)


class DiffLog:
    """Per-deck-session mutation trace. snap_before/after → diff() → clear()."""

    def __init__(self):
        self._before: dict = {}
        self._after: dict = {}
        self._intent_scope: dict = {}

    def set_intent_scope(self, scope: dict):
        self._intent_scope = scope

    def snap_before(self, plan, slide_idx: int):
        elem_ids = {pe.elem_id for pe in getattr(plan, 'phase1_elements', [])}
        self._before[slide_idx] = elem_ids

    def snap_after(self, plan, slide_idx: int):
        elem_ids = {pe.elem_id for pe in getattr(plan, 'phase1_elements', [])}
        self._after[slide_idx] = elem_ids

    def diff(self) -> DiffReport:
        changed = set()
        for idx in set(self._before.keys()) | set(self._after.keys()):
            before = self._before.get(idx, set())
            after = self._after.get(idx, set())
            changed |= (before ^ after)
        return DiffReport(
            entries=[{"before": self._before, "after": self._after}],
            changed_elem_ids=changed,
        )

    def scope_alert(self) -> dict | None:
        """Check say-vs-do mismatch: intent_scope vs actual changed elements."""
        if not self._intent_scope:
            return None
        report = self.diff()
        declared = set(self._intent_scope.get("elem_ids", []))
        if report.changed_elem_ids != declared:
            return {
                "declared": list(declared),
                "actual": list(report.changed_elem_ids),
                "extra": list(report.changed_elem_ids - declared),
                "missing": list(declared - report.changed_elem_ids),
            }
        return None

    def clear(self):
        self._before.clear()
        self._after.clear()
        self._intent_scope.clear()
