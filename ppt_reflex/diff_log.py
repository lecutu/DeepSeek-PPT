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
    """Per-deck-session mutation trace. roll() → snap_after() → diff() → clear().

    2026-08 审查修复：旧版 snap_before/snap_after 在同一次 build 内对同一个 plan
    拍两次照 → before/after 恒等 → diff 恒为空、scope_alert 恒误报 missing。
    新语义：build 开始 roll()（上次的 after 滚动为 before），build 结束 snap_after()，
    diff 比较的是**相邻两次 build**的元素集合净变化。
    """

    def __init__(self):
        self._before: dict = {}
        self._after: dict = {}
        self._intent_scope: dict = {}

    def set_intent_scope(self, scope: dict):
        self._intent_scope = scope

    def roll(self):
        """build 开始时调用：上一次 build 的 after 成为本次的 before。"""
        self._before = dict(self._after)
        self._after = {}

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

    # 向后兼容：旧调用点（builder 内的 snap_before）→ roll 语义
    def snap_before(self, plan, slide_idx: int):
        pass  # 已废弃：before 由 roll() 提供
