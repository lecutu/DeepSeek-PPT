"""
grid/plan.py — Phase 0 数据类

哲学：引擎只算真相+给菜单，绝不静默改 AI 声明。
allow_shrink / allow_wrap 默认 False，逼第一轮必出诊断、必进第二轮，回路因此转起来。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from .types import ContentType, ElementPayload


@dataclass
class FeedbackBundle:
    """引擎→AI 的结构化反馈。用于 build_plan(feedback) 回调。"""
    round: int = 0
    blocked: bool = False
    blocking_count: int = 0
    warning_count: int = 0
    force_full_relayout: bool = False
    message: str = ""
    diagnostics: list[dict] = field(default_factory=list)


@dataclass
class LayoutDiagnostic:
    """引擎给 AI 的『问题+建议』。severity=error 阻塞，warning 不阻塞。
    options 是带数字代价的菜单，选哪条是 AI 的语义决策。"""
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
    """AI 声明的布局区。content_inset 是区内安全边距，allow_auto_shrink 是区域级缩放授权。"""
    region_id: str = ""
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    purpose: str = ""
    reading_order: int = 0
    content_inset: float = 12.0
    allow_auto_shrink: bool = False  # region 级授权等比缩，优先于元素级
    elements: list[str] = field(default_factory=list)

    @property
    def usable_rect(self):
        i = self.content_inset
        return (self.x + i, self.y + i, max(1.0, self.w - 2 * i), max(1.0, self.h - 2 * i))


@dataclass
class Phase1Element:
    """AI 对信息层元素的意图声明。allow_shrink/allow_wrap 默认 False。
    ARROW_SLOT 是引擎为装饰预留的视觉间隙（箭头+标签宽度总和）。"""
    elem_id: str = ""
    region_id: str = ""
    content_type: ContentType = field(default=ContentType.UNKNOWN)
    payload: ElementPayload | None = None
    align_h: str = "left"
    fill_mode: str = "stack"          # inline | stack
    margin_above: float = 6.0
    preferred_width: float | None = None
    preferred_height: float | None = None
    allow_shrink: bool = False        # True → 引擎可对此元素等比缩（全块同比例）
    allow_wrap: bool = False          # True → 文本换行可接受，引擎不报掉行 warning
    ARROW_SLOT: float = 48.0          # 引擎为内联装饰（箭头+标签）预留的水平槽位

    @classmethod
    def arrow_gap(cls, elems):
        """取一组 inline 元素中第一个的 ARROW_SLOT 作为间隙。"""
        if not elems:
            return 48.0
        try:
            return max(24.0, getattr(elems[0], 'ARROW_SLOT', 48.0))
        except (TypeError, IndexError):
            return 48.0


@dataclass
class DecoIntent:
    """AI 对装饰元素的意图——引用+规则，不传坐标。"""
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
    """Phase 2 解析后的装饰坐标——所有值已锁定为 pt。"""
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
    """Phase 1 锁定后的信息层元素——坐标不可变，下游只读。"""
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

    @property
    def rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)


@dataclass
class LayoutPlan:
    """一张幻灯片的完整规划。diagnostics 是引擎→AI 的反馈通道。"""
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
        """只量、只报，绝不 mutate region。越界 → 诊断（带建议坐标菜单）。"""
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
            msg = f"region 探出页面: {'; '.join(probs)}"
            issues.append(f"{r.region_id}: {msg}")
            self.diagnostics.append(LayoutDiagnostic(
                kind="region_out_of_page", severity="error", region_id=r.region_id,
                demand_pt=right, usable_pt=self.page_w,
                over_by_pt=max(0.0, right - self.page_w),
                message=msg,
                options=[
                    f"把 region 改为 x={nx:.0f} y={ny:.0f} w={nw:.0f} h={nh:.0f}（夹回页面内）",
                    f"或整体左移/缩宽，使右边缘 <= {self.page_w - inset:.0f}",
                    "若该 region 本就该这么宽 -> 检查 page_w 是否与真实渲染宽一致",
                ],
            ))
            if verbose:
                print(f"[VALIDATE][{r.region_id}] {msg} -> 建议 x={nx:.0f} y={ny:.0f} w={nw:.0f} h={nh:.0f}")
        return issues
