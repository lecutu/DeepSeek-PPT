"""
L1 几何引擎：双层网格 + 精确 bbox + 七类检测

DEPRECATED — grid/ 模块已替代核心功能。
  - BBox / SlideElement / Issue → grid/types.py
  - 坐标计算 / 网格地址 → grid/positioning.py
  - 碰撞检测 / 对齐 / 间距 → grid/canvas.py + grid/matrix.py
  - Agent 操作流 → grid/canvas.py (GridCanvas.try_place / commit)

此文件保留为旧 audit() 兼容层。新代码应使用 grid/ 模块。

内部使用 EMU（python-pptx 原生单位），对外转换为 pt 或网格地址。
1 EMU = 1/914400 inch; 1 pt = 12700 EMU.
"""

from __future__ import annotations
import math
import warnings
from dataclasses import dataclass, field
from enum import Enum, auto
from itertools import combinations
from collections import defaultdict
from typing import Optional

# ── constants ──────────────────────────────────────────────
EMU_PER_PT = 12700
PT_PER_CM = 28.346
EMU_PER_CM = int(EMU_PER_PT * PT_PER_CM)

DEFAULT_SLIDE_W = 960  # pt (16:9 standard)
DEFAULT_SLIDE_H = 540
SAFE_MARGIN_PT = 36

COARSE_CELL_PT = 60   # 16×9 grid for Agent semantic layer
FINE_CELL_PT = 30     # 32×18 grid for internal indexing


# ── enums ──────────────────────────────────────────────────
class IssueCode(Enum):
    OUT_OF_BOUNDS = auto()
    UNEXPECTED_OVERLAP = auto()
    ALIGNMENT_DRIFT = auto()
    SPACING_DEVIATION = auto()
    FONT_BELOW_THRESHOLD = auto()
    ASPECT_DISTORTED = auto()
    DENSITY_HIGH = auto()
    READING_ORDER_VIOLATION = auto()
    TEXT_OVERFLOW_SUSPECTED = auto()

class Severity(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    FATAL = 3

class CollisionVerdict(Enum):
    ALLOW = auto()
    WARN = auto()
    BLOCK = auto()

class ContentRole(Enum):
    TITLE = "title"
    SUBTITLE = "subtitle"
    BODY = "body"
    KEY_METRIC = "key_metric"
    FIGURE = "figure"
    CAPTION = "caption"
    CITATION = "citation"
    FOOTER = "footer"
    PAGE_NUMBER = "page_number"
    BACKGROUND = "background"
    DECORATION = "decoration"
    UNKNOWN = "unknown"

class CollisionRole(Enum):
    FOREGROUND_CONTENT = "foreground_content"
    FOREGROUND_ANNOTATION = "foreground_annotation"
    BACKGROUND_FILL = "background_fill"
    DECORATIVE = "decorative"


# ── data types ─────────────────────────────────────────────
@dataclass
class BBox:
    """Bounding box in pt, origin top-left."""
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float: return self.x + self.w
    @property
    def bottom(self) -> float: return self.y + self.h

    @property
    def area(self) -> float: return self.w * self.h

    @classmethod
    def from_emu(cls, left: int, top: int, width: int, height: int):
        return cls(
            x=left / EMU_PER_PT,
            y=top / EMU_PER_PT,
            w=width / EMU_PER_PT,
            h=height / EMU_PER_PT,
        )

    def intersection_area(self, other: BBox) -> float:
        x_overlap = max(0.0, min(self.right, other.right) - max(self.x, other.x))
        y_overlap = max(0.0, min(self.bottom, other.bottom) - max(self.y, other.y))
        return x_overlap * y_overlap

    def overlap_pct(self, other: BBox) -> float:
        """Overlap area as % of smaller bbox."""
        inter = self.intersection_area(other)
        if inter == 0:
            return 0.0
        return inter / min(self.area, other.area) * 100

    def is_outside(self, canvas_w: float, canvas_h: float, margin: float = 0) -> dict:
        """Returns {edge: overflow_pt} for each edge that exceeds boundary."""
        overflow = {}
        if self.x < margin:
            overflow["left"] = margin - self.x
        if self.y < margin:
            overflow["top"] = margin - self.y
        if self.right > canvas_w - margin:
            overflow["right"] = self.right - (canvas_w - margin)
        if self.bottom > canvas_h - margin:
            overflow["bottom"] = self.bottom - (canvas_h - margin)
        return overflow


@dataclass
class SlideElement:
    id: str
    bbox: BBox
    content_role: ContentRole = ContentRole.UNKNOWN
    collision_role: CollisionRole = CollisionRole.FOREGROUND_CONTENT
    font_size_pt: float = 12.0
    font_explicit: bool = False   # Was font size explicitly set, or inherited?
    aspect_ratio_locked: bool = True
    text: str = ""
    z_order: int = 0
    locked: bool = False
    locked_by: str = ""  # "human" | "agent" | ""

    # ── computed by engine ──
    coarse_cells: set[str] = field(default_factory=set)
    fine_cells: set[str] = field(default_factory=set)

    def __hash__(self): return hash(self.id)
    def __eq__(self, other): return isinstance(other, SlideElement) and self.id == other.id


@dataclass
class Issue:
    code: IssueCode
    severity: Severity
    targets: list[str]                     # element IDs involved
    detail: dict                           # code-specific data
    auto_fixable: bool = False
    auto_fix_fn: Optional[str] = None      # name of fix function if auto_fixable


# ── grid utilities ─────────────────────────────────────────
def _cell_name(col: int, row: int) -> str:
    """0-indexed col,row → Excel-style cell name. Columns beyond Z wrap to AA etc."""
    if col < 26:
        c = chr(65 + col)
    else:
        c = chr(65 + (col // 26) - 1) + chr(65 + (col % 26))
    return f"{c}{row + 1}"

def _cells_for_bbox(bbox: BBox, cell_size_pt: int, max_cols: int, max_rows: int) -> set[str]:
    c0 = max(0, int(bbox.x / cell_size_pt))
    r0 = max(0, int(bbox.y / cell_size_pt))
    c1 = min(max_cols - 1, int((bbox.right - 1) / cell_size_pt))
    r1 = min(max_rows - 1, int((bbox.bottom - 1) / cell_size_pt))
    if c0 > c1 or r0 > r1:
        return set()
    return {_cell_name(c, r) for c in range(c0, c1 + 1) for r in range(r0, r1 + 1)}

def _grid_range(cells: set[str]) -> str:
    """Compact representation: {'A1','A2','B1','B2'} → 'A1:B2'"""
    if not cells:
        return ""
    cols = sorted(set(c[:-1] for c in cells), key=lambda x: (len(x), x))
    rows = sorted(set(int(c[1:]) for c in cells))
    return f"{cols[0]}{rows[0]}:{cols[-1]}{rows[-1]}" if len(cells) > 1 else f"{cols[0]}{rows[0]}"


# ═══════════════════════════════════════════════════════════
# L1  GEOMETRY ENGINE
# ═══════════════════════════════════════════════════════════
class GeometryEngine:
    """
    Double-layer grid spatial index.
    Coarse (60pt) = Agent semantics. Fine (30pt) = internal indexing.
    Actual collision judgement uses exact bbox (pt).
    """

    def __init__(self, canvas_w_pt: float = DEFAULT_SLIDE_W,
                 canvas_h_pt: float = DEFAULT_SLIDE_H,
                 safe_margin_pt: float = SAFE_MARGIN_PT):
        import warnings
        warnings.warn(
            "GeometryEngine is deprecated. Use ppt_reflex.grid.GridCanvas instead. "
            "See grid/canvas.py for try_place/commit API.",
            DeprecationWarning, stacklevel=2,
        )
        self.canvas_w = canvas_w_pt
        self.canvas_h = canvas_h_pt
        self.safe_margin = safe_margin_pt

        coarse_cols = int(canvas_w_pt / COARSE_CELL_PT)   # 16
        coarse_rows = int(canvas_h_pt / COARSE_CELL_PT)    # 9
        fine_cols = int(canvas_w_pt / FINE_CELL_PT)        # 32
        fine_rows = int(canvas_h_pt / FINE_CELL_PT)         # 18

        self.coarse_grid: dict[str, list[SlideElement]] = defaultdict(list)
        self.fine_grid: dict[str, list[SlideElement]] = defaultdict(list)
        self.coarse_max = (coarse_cols, coarse_rows)
        self.fine_max = (fine_cols, fine_rows)
        self.elements: dict[str, SlideElement] = {}

    # ── registration ───────────────────────────────────────
    def register(self, elem: SlideElement):
        self.remove(elem)
        elem.coarse_cells = _cells_for_bbox(elem.bbox, COARSE_CELL_PT, *self.coarse_max)
        elem.fine_cells = _cells_for_bbox(elem.bbox, FINE_CELL_PT, *self.fine_max)
        self.elements[elem.id] = elem
        self._place(elem, elem.coarse_cells, self.coarse_grid)
        self._place(elem, elem.fine_cells, self.fine_grid)

    def remove(self, elem: SlideElement):
        for c in elem.coarse_cells:
            self.coarse_grid[c] = [e for e in self.coarse_grid[c] if e.id != elem.id]
        for c in elem.fine_cells:
            self.fine_grid[c] = [e for e in self.fine_grid[c] if e.id != elem.id]
        self.elements.pop(elem.id, None)

    def _place(self, elem: SlideElement, cells: set[str], grid: dict):
        for c in cells:
            grid[c].append(elem)

    # ── L1a: bounds check ──────────────────────────────────
    def check_bounds(self, elem_id: str) -> list[Issue]:
        """Returns empty list if element is fully inside safe area."""
        elem = self.elements.get(elem_id)
        if not elem:
            return []
        # Background/decorative elements intentionally fill canvas — skip bounds
        if elem.content_role in (ContentRole.BACKGROUND, ContentRole.DECORATION):
            return []
        overflow = elem.bbox.is_outside(self.canvas_w, self.canvas_h, self.safe_margin)
        if not overflow:
            return []
        total = sum(overflow.values())
        severity = Severity.FATAL if total > 50 else (Severity.HIGH if total > 10 else Severity.MEDIUM)
        return [Issue(
            code=IssueCode.OUT_OF_BOUNDS,
            severity=severity,
            targets=[elem_id],
            detail={"overflow_pt": overflow, "total_overflow_pt": round(total, 1)},
            auto_fixable=total <= 5,
            auto_fix_fn="snap_to_safe_area" if total <= 5 else None,
        )]

    def check_bounds_all(self) -> list[Issue]:
        issues = []
        for eid in self.elements:
            issues.extend(self.check_bounds(eid))
        return issues

    # ── L1b: collision detection (four-stage) ──────────────
    def find_candidate_pairs(self) -> set[tuple[str, str]]:
        """
        Stage 1: fine-grid index → candidate pairs.
        Returns set of (id_a, id_b) where elements share at least one fine cell.
        """
        pairs: set[tuple[str, str]] = set()
        for cell, occupants in self.fine_grid.items():
            if len(occupants) < 2:
                continue
            for a, b in combinations(occupants, 2):
                pair = (a.id, b.id) if a.id < b.id else (b.id, a.id)
                pairs.add(pair)
        return pairs

    def exact_overlap_check(self, pairs: set[tuple[str, str]]) -> list[dict]:
        """
        Stage 2: precise bbox intersection.
        Returns [{"a": id, "b": id, "overlap_pct": float, "overlap_area_pt": float}, ...]
        Only returns pairs with actual overlap > 0.
        """
        results = []
        for id_a, id_b in pairs:
            a = self.elements[id_a]
            b = self.elements[id_b]
            overlap = a.bbox.overlap_pct(b.bbox)
            if overlap > 0:
                results.append({
                    "a": id_a, "b": id_b,
                    "overlap_pct": round(overlap, 1),
                    "overlap_area_pt": round(a.bbox.intersection_area(b.bbox), 1),
                })
        return results

    # ── L1c: alignment check ───────────────────────────────
    def check_alignment(self, elem_ids: list[str] | None = None) -> list[Issue]:
        """For elements sharing a column edge (coarse grid), check left-alignment drift."""
        if elem_ids is None:
            elem_ids = list(self.elements.keys())
        by_col: dict[str, list[SlideElement]] = defaultdict(list)
        for eid in elem_ids:
            e = self.elements.get(eid)
            if not e or e.content_role == ContentRole.BACKGROUND:
                continue
            for c in e.coarse_cells:
                by_col[c[:-1]].append(e)  # group by column letter
        issues = []
        for col, elems in by_col.items():
            if len(elems) < 2:
                continue
            # find the modal left edge
            edges = [e.bbox.x for e in elems]
            modal = _mode(edges, tolerance=2.0)
            for e in elems:
                drift = abs(e.bbox.x - modal)
                if 2 < drift <= 3:
                    issues.append(Issue(
                        code=IssueCode.ALIGNMENT_DRIFT,
                        severity=Severity.LOW,
                        targets=[e.id],
                        detail={"modal_left_pt": modal, "drift_pt": round(drift, 1)},
                        auto_fixable=True,
                        auto_fix_fn="snap_alignment_left",
                    ))
                elif drift > 3:
                    issues.append(Issue(
                        code=IssueCode.ALIGNMENT_DRIFT,
                        severity=Severity.MEDIUM,
                        targets=[e.id],
                        detail={"modal_left_pt": modal, "drift_pt": round(drift, 1)},
                        auto_fixable=False,
                    ))
        return issues

    # ── L1d: spacing check ─────────────────────────────────
    def check_spacing(self, elem_ids: list[str] | None = None) -> list[Issue]:
        """Check horizontal/vertical spacing uniformity.
        Sorts elements by X-coordinate (not grid column), measures gaps."""
        if elem_ids is None:
            elem_ids = list(self.elements.keys())
        # Group elements by Y-band (same row in coarse grid), then sort by X
        by_row: dict[int, list[SlideElement]] = defaultdict(list)
        for eid in elem_ids:
            e = self.elements.get(eid)
            if not e or e.content_role == ContentRole.BACKGROUND:
                continue
            for c in e.coarse_cells:
                by_row[int(c[1:])].append(e)
        issues = []
        seen_pairs: set[tuple[str, ...]] = set()
        for row, elems in by_row.items():
            unique = {e.id: e for e in elems}.values()
            if len(unique) < 3:
                continue
            sorted_elems = sorted(unique, key=lambda e: e.bbox.x)
            gaps = [sorted_elems[i+1].bbox.x - sorted_elems[i].bbox.right
                    for i in range(len(sorted_elems) - 1)]
            if not gaps or any(g <= 0 for g in gaps):
                continue
            mean_gap = sum(gaps) / len(gaps)
            if mean_gap == 0:
                continue
            deviations = [abs(g - mean_gap) / mean_gap for g in gaps]
            if max(deviations) > 0.5:  # >50% deviation from mean
                worst_idx = max(range(len(deviations)), key=lambda i: deviations[i])
                pair = (sorted_elems[worst_idx].id, sorted_elems[worst_idx + 1].id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                issues.append(Issue(
                    code=IssueCode.SPACING_DEVIATION,
                    severity=Severity.LOW,
                    targets=[sorted_elems[worst_idx].id, sorted_elems[worst_idx + 1].id],
                    detail={"gaps_pt": [round(g, 1) for g in gaps], "mean_gap_pt": round(mean_gap, 1)},
                    auto_fixable=False,
                ))
        return issues

    # ── L1e: font check ────────────────────────────────────
    def check_font_size(self, elem_id: str, min_font_pt: dict | None = None,
                        explicit_only: bool = True) -> list[Issue]:
        """Check if font is below role-specific minimum.
        If explicit_only=True, only flags elements where font was explicitly set
        (font_size_pt != default 12.0 AND element has text). Prevents false positives
        on shapes that inherit theme defaults.
        """
        elem = self.elements.get(elem_id)
        if not elem:
            return []
        if not elem.text.strip():
            return []  # No text content → skip
        if explicit_only and not elem.font_explicit:
            return []  # Inherited from theme, not explicitly set
        if min_font_pt is None:
            min_font_pt = {
                ContentRole.TITLE: 24, ContentRole.SUBTITLE: 18,
                ContentRole.BODY: 14, ContentRole.CAPTION: 11,
                ContentRole.CITATION: 10, ContentRole.FOOTER: 10,
            }
        min_val = min_font_pt.get(elem.content_role, 12)
        drift = min_val - elem.font_size_pt
        if drift <= 0:
            return []
        severity = Severity.LOW if drift <= 1 else Severity.MEDIUM
        return [Issue(
            code=IssueCode.FONT_BELOW_THRESHOLD,
            severity=severity,
            targets=[elem_id],
            detail={"current_pt": elem.font_size_pt, "min_pt": min_val, "deficit_pt": drift},
            auto_fixable=drift <= 1,
            auto_fix_fn="bump_font_size" if drift <= 1 else None,
        )]

    def check_font_all(self) -> list[Issue]:
        issues = []
        for eid in self.elements:
            issues.extend(self.check_font_size(eid))
        return issues

    # ── L1f: aspect ratio check ────────────────────────────
    def check_aspect_ratio(self, elem_id: str, original_w: float, original_h: float) -> list[Issue]:
        elem = self.elements.get(elem_id)
        if not elem:
            return []
        if original_h == 0:
            return []
        original_ratio = original_w / original_h
        current_ratio = elem.bbox.w / elem.bbox.h
        deviation = abs(current_ratio - original_ratio) / original_ratio
        if deviation < 0.03:
            return []
        return [Issue(
            code=IssueCode.ASPECT_DISTORTED,
            severity=Severity.HIGH,
            targets=[elem_id],
            detail={"original_ratio": round(original_ratio, 3), "current_ratio": round(current_ratio, 3),
                    "deviation_pct": round(deviation * 100, 1)},
            auto_fixable=False,
        )]

    # ── L1g: density check ─────────────────────────────────
    def check_density(self) -> list[Issue]:
        total_cells = self.coarse_max[0] * self.coarse_max[1]  # 144
        occupied = set()
        for e in self.elements.values():
            if e.content_role in (ContentRole.BACKGROUND, ContentRole.DECORATION):
                continue
            occupied.update(e.coarse_cells)
        density = len(occupied) / total_cells
        if density < 0.7:
            return []
        severity = Severity.HIGH if density > 0.85 else Severity.MEDIUM
        return [Issue(
            code=IssueCode.DENSITY_HIGH,
            severity=severity,
            targets=list(self.elements.keys()),
            detail={"density_pct": round(density * 100, 1), "occupied_cells": len(occupied)},
            auto_fixable=False,
        )]


# ── math helpers ───────────────────────────────────────────
def _mode(values: list[float], tolerance: float) -> float:
    """Find modal value by grouping within tolerance."""
    if not values:
        return 0.0
    clusters = []
    for v in sorted(values):
        placed = False
        for cluster in clusters:
            if abs(v - sum(cluster) / len(cluster)) <= tolerance:
                cluster.append(v)
                placed = True
                break
        if not placed:
            clusters.append([v])
    largest = max(clusters, key=len)
    return sum(largest) / len(largest)
