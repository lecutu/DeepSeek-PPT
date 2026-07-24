"""
有限自动修复器 (Nudge Engine)

约束：
  边界吸附 ≤ 5pt
  对齐吸附 ≤ 3pt
  微调避碰 ≤ 3 次
  单次操作最多修改 3 个元素

超出限制 → 停止，不继续挣扎。
所有修复记录到 journal。
"""

from __future__ import annotations
from engine import (
    SlideElement, BBox, Issue, IssueCode, Severity,
    GeometryEngine, EMU_PER_PT, DEFAULT_SLIDE_W, DEFAULT_SLIDE_H,
    SAFE_MARGIN_PT,
)
from dataclasses import dataclass, field
from typing import Optional, Callable

# ── limits ─────────────────────────────────────────────────
MAX_BOUNDARY_SNAP_PT = 5
MAX_ALIGNMENT_SNAP_PT = 3
MAX_NUDGE_ATTEMPTS = 3
MAX_ELEMENTS_MODIFIED = 3


@dataclass
class NudgeRecord:
    element_id: str
    source: str         # "boundary_reflex" | "alignment_reflex" | "collision_nudge"
    before: dict        # {x, y, w, h}
    after: dict
    reason: str
    success: bool = True


class NudgeEngine:
    """Attempts automatic fixes. Records everything."""

    def __init__(self, geometry: GeometryEngine):
        self.geo = geometry
        self.records: list[NudgeRecord] = []
        self.modified_count = 0

    def reset(self):
        self.records.clear()
        self.modified_count = 0

    # ── boundary snap ──────────────────────────────────────
    def snap_to_safe_area(self, elem: SlideElement) -> Optional[NudgeRecord]:
        overflow = elem.bbox.is_outside(self.geo.canvas_w, self.geo.canvas_h,
                                        self.geo.safe_margin)
        if not overflow:
            return None

        x, y, w, h = elem.bbox.x, elem.bbox.y, elem.bbox.w, elem.bbox.h
        original = {"x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1)}

        total_overflow = sum(overflow.values())
        if total_overflow > MAX_BOUNDARY_SNAP_PT:
            return None  # Too much to snap automatically

        m = self.geo.safe_margin
        cw = self.geo.canvas_w
        ch = self.geo.canvas_h

        if "left" in overflow and overflow["left"] <= MAX_BOUNDARY_SNAP_PT:
            x += overflow["left"]
        if "top" in overflow and overflow["top"] <= MAX_BOUNDARY_SNAP_PT:
            y += overflow["top"]
        if "right" in overflow and overflow["right"] <= MAX_BOUNDARY_SNAP_PT:
            x -= overflow["right"]
        if "bottom" in overflow and overflow["bottom"] <= MAX_BOUNDARY_SNAP_PT:
            y -= overflow["bottom"]

        return self._apply(elem, x, y, w, h, original, "boundary_reflex",
                           f"snap_to_safe: overflow {overflow}")

    # ── alignment snap ─────────────────────────────────────
    def snap_alignment(self, elem: SlideElement, target_x: float) -> Optional[NudgeRecord]:
        drift = abs(elem.bbox.x - target_x)
        if drift == 0 or drift > MAX_ALIGNMENT_SNAP_PT:
            return None
        original = {"x": round(elem.bbox.x, 1), "y": round(elem.bbox.y, 1),
                    "w": round(elem.bbox.w, 1), "h": round(elem.bbox.h, 1)}
        return self._apply(elem, target_x, elem.bbox.y, elem.bbox.w, elem.bbox.h,
                           original, "alignment_reflex",
                           f"snap left edge from {elem.bbox.x:.1f} to {target_x:.1f}")

    # ── collision nudge ────────────────────────────────────
    def nudge_to_resolve_collision(self, a: SlideElement, b: SlideElement,
                                   overlap_pct: float) -> list[NudgeRecord]:
        """
        Try up to MAX_NUDGE_ATTEMPTS small moves to resolve collision.
        Prefers moving the lower-priority element.
        Returns list of successful nudges (empty if all attempts failed).
        """
        # Determine which element to move
        # Priority: move the smaller element, or non-title over title
        mover = b if b.bbox.area <= a.bbox.area else a
        stationary = a if mover is b else b

        records = []
        tried = 0

        while tried < MAX_NUDGE_ATTEMPTS and self.modified_count < MAX_ELEMENTS_MODIFIED:
            # Try: shift mover right, then down, then right+down
            strategies = [
                ("shift_right", mover.bbox.x + 5, mover.bbox.y),
                ("shift_down", mover.bbox.x, mover.bbox.y + 5),
                ("shift_diagonal", mover.bbox.x + 5, mover.bbox.y + 5),
            ]

            resolved = False
            for reason, new_x, new_y in strategies[tried:tried+1]:
                # check new position is in bounds
                new_bbox = BBox(new_x, new_y, mover.bbox.w, mover.bbox.h)
                if new_bbox.is_outside(self.geo.canvas_w, self.geo.canvas_h, self.geo.safe_margin):
                    continue

                new_overlap = new_bbox.overlap_pct(stationary.bbox)
                if new_overlap == 0:
                    original = {"x": round(mover.bbox.x, 1), "y": round(mover.bbox.y, 1),
                                "w": round(mover.bbox.w, 1), "h": round(mover.bbox.h, 1)}
                    rec = self._apply(mover, new_x, new_y, mover.bbox.w, mover.bbox.h,
                                      original, "collision_nudge",
                                      reason + f" to resolve collision with {stationary.id}")
                    if rec:
                        records.append(rec)
                        resolved = True
                        break

            if resolved:
                break
            tried += 1

        return records

    # ── internal apply ─────────────────────────────────────
    def _apply(self, elem: SlideElement, x: float, y: float, w: float, h: float,
               original: dict, source: str, reason: str) -> Optional[NudgeRecord]:
        """Actually move the element and re-register in geometry engine."""
        if self.modified_count >= MAX_ELEMENTS_MODIFIED:
            return None
        if elem.locked:
            return None

        self.geo.remove(elem)
        elem.bbox = BBox(x, y, w, h)
        self.geo.register(elem)
        self.modified_count += 1

        rec = NudgeRecord(
            element_id=elem.id,
            source=source,
            before=original,
            after={"x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1)},
            reason=reason,
        )
        self.records.append(rec)
        return rec

    def flush_records(self) -> list[NudgeRecord]:
        r = self.records.copy()
        self.records.clear()
        return r
