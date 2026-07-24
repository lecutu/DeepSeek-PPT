"""
grid/types.py — 所有类型定义集中，零依赖。

GridConfig / ContentType / Verdict / InfoCell / Conflict / PlacementResult
LayoutProfile / BLOCK_PAIRS / DEFAULT_POLICY
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ═══════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════

class Verdict(Enum):
    ALLOW = "allow"
    WARN  = "warn"
    BLOCK = "block"

    def __gt__(self, other) -> bool:
        order = {Verdict.ALLOW: 0, Verdict.WARN: 1, Verdict.BLOCK: 2}
        return order[self] > order[other]


class ContentType(Enum):
    TEXT        = "text"         # 纯文本框，无背景填充
    TEXTBOX     = "textbox"      # 有背景填充的文本框（色块+文字）
    IMAGE       = "image"        # 图片
    BACKGROUND  = "background"   # 全幅背景
    TABLE       = "table"        # 表格
    CHART       = "chart"        # 图表
    SHAPE       = "shape"        # 装饰图形（无文字）
    ANNOTATION  = "annotation"   # 标注、批注
    FOOTER      = "footer"       # 页脚（跨页一致性用）
    TITLE       = "title"        # 标题（层级检测用）
    UNKNOWN     = "unknown"


# ═══════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════

@dataclass
class GridConfig:
    """定位层 + 信息层的所有可调参数。"""
    # 定位层 (Agent 可见)
    coarse_cols: int = 16
    coarse_rows: int = 9
    coarse_cell_pt: float = 60.0    # 960 / 16

    # 信息层 (引擎内部)
    fine_cols: int = 32
    fine_rows: int = 18
    fine_cell_pt: float = 30.0     # 960 / 32

    # 判定
    overlap_tolerance_pt: float = 5.0  # <5pt 重叠不算冲突
    default_policy: Verdict = Verdict.ALLOW

    # 画布
    canvas_w_pt: float = 960.0
    canvas_h_pt: float = 540.0
    safe_margin_pt: float = 36.0

    # 密度阈值
    density_warn_pct: float = 70.0
    density_critical_pct: float = 85.0

    # Token 预算
    max_level0_tokens: int = 50
    max_level1_tokens: int = 100
    max_level2_tokens: int = 60


@dataclass
class InfoCell:
    """信息层的最小单元。30pt×30pt。"""
    owner_id: str | None = None
    content_type: ContentType | None = None
    z_order: int = 0
    locked: bool = False
    source: str = "unknown"   # "template" | "agent" | "human"

    # 第二版: fill_color, font_color, font_size, border_style, ...


@dataclass
class Conflict:
    """单个冲突的详细信息。"""
    cell_addr: str                    # "C3"
    existing_id: str                  # "shape-02"
    new_id: str                       # "shape-04"
    existing_type: ContentType        # TEXT
    new_type: ContentType             # TEXT
    verdict: Verdict                  # BLOCK
    overlap_pt: float = 0.0           # 重叠量
    detail: str = ""                  # "文字叠文字"


@dataclass
class PlacementResult:
    """try_place 的返回值。"""
    verdict: Verdict
    conflicts: list[Conflict] = field(default_factory=list)
    warnings: list[Conflict] = field(default_factory=list)    # WARN 级，不进 conflicts
    z_hint: str | None = None         # "new_above" | "new_below" | None
    free_suggestion: list[list[str]] = field(default_factory=list)
    # free_suggestion: [["A8","A9","B8","B9"], ["E1","F1","G1","H1"]]
    # 每个元素是一组连续的可用格子区域

    @property
    def allowed(self) -> bool:
        return self.verdict == Verdict.ALLOW

    @property
    def blocked(self) -> bool:
        return self.verdict == Verdict.BLOCK


@dataclass
class LayoutProfile:
    """跨页一致的版式约束。"""
    name: str                                      # "title_body_figure_right"
    zones: dict[str, list[str]] = field(default_factory=dict)
    # {"title": ["A1","B1","C1"], "body": ["A2","B2","C2","D2","A3","B3","C3","D3"], ...}
    locked_zones: set[str] = field(default_factory=set)      # 装饰区 cell 地址
    decorative_elements: set[str] = field(default_factory=set)  # shape ID
    page_constraints: dict = field(default_factory=dict)
    # {"max_elements": 8, "allow_figure": True, "preferred_body_zone": "A2:D6"}

    def cells_for_role(self, role: str) -> list[str]:
        return self.zones.get(role, [])

    def is_locked_cell(self, cell_addr: str) -> bool:
        return cell_addr in self.locked_zones


# ═══════════════════════════════════════════════════════════
# INTERACTION MATRIX — 默认规则
# ═══════════════════════════════════════════════════════════

BLOCK_PAIRS: set[tuple[ContentType, ContentType]] = {
    (ContentType.TEXT,       ContentType.TEXT),
    (ContentType.TEXT,       ContentType.IMAGE),
    (ContentType.TEXT,       ContentType.TABLE),
    (ContentType.TEXT,       ContentType.CHART),
    (ContentType.IMAGE,      ContentType.TEXT),
    (ContentType.IMAGE,      ContentType.TABLE),
    (ContentType.IMAGE,      ContentType.CHART),
    (ContentType.TABLE,      ContentType.TEXT),
    (ContentType.TABLE,      ContentType.IMAGE),
    (ContentType.TABLE,      ContentType.TABLE),
    (ContentType.TABLE,      ContentType.CHART),
    (ContentType.CHART,      ContentType.TEXT),
    (ContentType.CHART,      ContentType.IMAGE),
    (ContentType.CHART,      ContentType.TABLE),
    (ContentType.CHART,      ContentType.CHART),
    (ContentType.TEXTBOX,    ContentType.TEXTBOX),
}
DEFAULT_POLICY: Verdict = Verdict.ALLOW

# ═══════════════════════════════════════════════════════════
# Z-ORDER HINTS — 谁浮在谁上面
# ═══════════════════════════════════════════════════════════

Z_ORDER_RULES: dict[tuple[ContentType, ContentType], str] = {
    (ContentType.TEXT,       ContentType.TEXTBOX):  "new_above",   # 文字浮在色块上
    (ContentType.ANNOTATION, ContentType.TEXT):      "new_above",   # 标注浮在文字上
    (ContentType.ANNOTATION, ContentType.IMAGE):     "new_above",
    (ContentType.TEXT,       ContentType.SHAPE):     "new_above",   # 文字浮在装饰上
    (ContentType.IMAGE,      ContentType.SHAPE):     "new_above",
    (ContentType.TEXTBOX,    ContentType.IMAGE):     "either",
    (ContentType.TEXTBOX,    ContentType.TEXT):      "new_below",   # 色块垫在文字下
    (ContentType.IMAGE,      ContentType.TEXTBOX):   "either",
}
