"""
grid/plan.py — Phase 0 data classes

Philosophy: engine only computes truth and provides menus, never silently mutates AI declarations.
allow_shrink / allow_wrap default False — forces round 1 to always produce diagnostics,
forcing round 2, closing the loop.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from .types import ContentType, ElementPayload


@dataclass
class LayoutDiagnostic:
    """Engine->AI 'problem+suggestion'. severity=error blocks, warning does not.
    options is a menu with numeric costs — which to pick is the AI's semantic decision."""
    kind: str = ""                  # region_out_of_page | inline_overflow | text_wrap | deco_out_of_page
    severity: str = "error"
    region_id: str = ""
    elem_id: str = ""
    demand_pt: float = 0.0
    usable_pt: float = 0.0
    over_by_pt: float = 0.0
    message: str = ""
    options: list[str] = field(default_factory=list)


@dataclass
class Region:
    """AI-declared layout zone. content_inset is the internal safe margin. allow_auto_shrink is zone-level scale authorization."""
    region_id: str = ""
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    purpose: str = ""
    reading_order: int = 0
    content_inset: float = 12.0
    allow_auto_shrink: bool = False  # zone-level uniform shrink auth, takes priority over element-level
    elements: list[str] = field(default_factory=list)

    @property
    def usable_rect(self):
        i = self.content_inset
        return (self.x + i, self.y + i, max(1.0, self.w - 2 * i), max(1.0, self.h - 2 * i))


@dataclass
class Phase1Element:
    """AI's intent declaration for an information-layer element. allow_shrink/allow_wrap default False.
    ARROW_SLOT is the visual gap the engine reserves for decorations (arrow+label width total)."""
    elem_id: str = ""
    region_id: str = ""
    content_type: ContentType = field(default=ContentType.UNKNOWN)
    payload: ElementPayload | None = None
    align_h: str = "left"
    fill_mode: str = "stack"          # inline | stack
    margin_above: float = 6.0
    preferred_width: float | None = None
    preferred_height: float | None = None
    allow_shrink: bool = False        # True -> engine may proportionally shrink this element (same ratio for whole block)
    allow_wrap: bool = False          # True -> text wrapping is acceptable, engine won't warn on line wrap
    ARROW_SLOT: float = 48.0          # horizontal slot reserved by engine for inline decor (arrow+label)

    @classmethod
    def arrow_gap(cls, elems):
        """Take the ARROW_SLOT of the first inline element as gap."""
        if not elems:
            return 48.0
        try:
            return max(24.0, getattr(elems[0], 'ARROW_SLOT', 48.0))
        except (TypeError, IndexError):
            return 48.0


@dataclass
class DecoIntent:
    """AI's intent for a decoration element — references+rules, no coordinates passed."""
    deco_id: str = ""
    deco_type: str = "arrow"
    relative_to: list[str] = field(default_factory=list)
    direction: str = "right_of"
    margin_pt: float = 8.0
    style: dict = field(default_factory=dict)
    text: str = ""
    text_font_size: float = 12.0
    text_color: tuple[int, int, int] = (0, 0, 0)
    occlusion_check: bool = True


@dataclass
class DecorationSpec:
    """Phase 2 resolved decoration coordinates — all values locked in pt."""
    deco_id: str = ""
    deco_type: str = ""
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    anchor_from: str = ""
    anchor_to: str = ""
    style: dict = field(default_factory=dict)
    text: str = ""
    text_font_size: float = 12.0
    text_color: tuple[int, int, int] = (0, 0, 0)
    occlusion_warnings: list[str] = field(default_factory=list)


@dataclass
class PageElement:
    """Phase 1 locked information-layer element — coordinates immutable, downstream read-only."""
    elem_id: str = ""
    region_id: str = ""
    content_type: ContentType = ContentType.UNKNOWN
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    payload: ElementPayload | None = None
    allow_overlap: bool = False
    allow_wrap: bool = False
    z_order: int = 100
    # P0-口①: layout lock flags — when True, SHAPE_TO_FIT_TEXT does NOT excuse overflow
    # because the layout system has fixed this dimension (stack/inline allocation).
    height_is_locked: bool = False
    width_is_locked: bool = False

    @property
    def rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)


@dataclass
class LayoutPlan:
    """Complete plan for one slide. diagnostics is the engine->AI feedback channel."""
    page_w: float = 960.0
    page_h: float = 540.0
    page_safe_inset: float = 12.0
    title: str = ""
    regions: list[Region] = field(default_factory=list)
    phase1_elements: list[Phase1Element] = field(default_factory=list)
    deco_intents: list[DecoIntent] = field(default_factory=list)
    elements: list[PageElement] = field(default_factory=list)
    decorations: list[DecorationSpec] = field(default_factory=list)
    diagnostics: list[LayoutDiagnostic] = field(default_factory=list)

    def has_blocking(self) -> bool:
        return any(d.severity == "error" for d in self.diagnostics)

    def sorted_regions(self) -> list[Region]:
        return sorted(self.regions, key=lambda r: r.reading_order)

    def region_by_id(self, rid: str) -> Region | None:
        for r in self.regions:
            if r.region_id == rid:
                return r
        return None

    def element_by_id(self, eid: str) -> PageElement | None:
        for e in self.elements:
            if e.elem_id == eid:
                return e
        return None

    def validate(self, *, verbose: bool = True) -> list[str]:
        """Measure and report only, never mutate region. Out-of-bounds -> diagnostic (with suggested coordinate menu)."""
        issues: list[str] = []
        inset = self.page_safe_inset
        for r in self.regions:
            right, bottom = r.x + r.w, r.y + r.h
            probs = []
            if r.x < -0.5:
                probs.append(f"x={r.x:.1f}<0")
            if r.y < -0.5:
                probs.append(f"y={r.y:.1f}<0")
            if right > self.page_w + 0.5:
                probs.append(f"right={right:.1f}>page_w={self.page_w:.1f}")
            if bottom > self.page_h + 0.5:
                probs.append(f"bottom={bottom:.1f}>page_h={self.page_h:.1f}")
            if r.w < 1 or r.h < 1:
                probs.append(f"size w={r.w:.1f} h={r.h:.1f}")
            if not probs:
                continue
            nx = max(inset, r.x)
            ny = max(inset, r.y)
            nw = max(1.0, min(r.w - (nx - r.x), self.page_w - inset - nx))
            nh = max(1.0, min(r.h - (ny - r.y), self.page_h - inset - ny))
            msg = f"region out of page: {'; '.join(probs)}"
            issues.append(f"{r.region_id}: {msg}")
            self.diagnostics.append(LayoutDiagnostic(
                kind="region_out_of_page", severity="error", region_id=r.region_id,
                demand_pt=right, usable_pt=self.page_w,
                over_by_pt=max(0.0, right - self.page_w),
                message=msg,
                options=[
                    f"set region to x={nx:.0f} y={ny:.0f} w={nw:.0f} h={nh:.0f} (clamp into page)",
                    f"or shift left/shrink width so right edge <= {self.page_w - inset:.0f}",
                    "if this region should be this wide -> check page_w matches actual render width",
                ],
            ))
            if verbose:
                print(f"[VALIDATE][{r.region_id}] {msg} -> suggest x={nx:.0f} y={ny:.0f} w={nw:.0f} h={nh:.0f}")
        return issues
