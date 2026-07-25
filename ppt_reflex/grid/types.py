"""
grid/types.py — 所有类型定义集中，零依赖。

GridConfig / SemanticRole / ContentType / Verdict / InfoCell / Conflict / PlacementResult
LayoutProfile / ENTITY_ROLES / OVERLAY_ROLES
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Literal


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


class SemanticRole(Enum):
    """AI 对元素意图的理解——"我读懂了它在这张图里干什么"。

    role 是 AI 理解的唯一外化。架构据此做确定性的表分配：
      ENTITY    → entity_table（不重叠表：排他碰撞）
      其余      → overlay_table（重叠表：不跑碰撞，按 z 层序叠加）
    """
    ENTITY     = "entity"      # 占地内容——能级条、正文段、表格、代码块
    CONNECTOR  = "connector"   # 连接/指向——跃迁箭头、流程边、引线
    ANNOTATION = "annotation"  # 依附标签——能级标签 v'=2、单位、批注
    EMPHASIS   = "emphasis"    # 高亮/框选/阴影——圈注、选区框
    BACKDROP   = "backdrop"    # 衬底/坐标轴底——网格线、底纹


class ContentType(Enum):
    """渲染提示——告诉 serializer 用什么方式画。

    注意：ContentType 不参与碰撞判定。碰撞由 SemanticRole → 表 决定。
    RECT 可以是 ENTITY（能级条）也可以是 EMPHASIS（高亮框）——区分靠 role。
    """
    TEXT        = "text"
    TEXTBOX     = "textbox"
    IMAGE       = "image"
    BACKGROUND  = "background"
    TABLE       = "table"
    CHART       = "chart"
    SHAPE       = "shape"
    ANNOTATION  = "annotation"
    CONNECTOR   = "connector"
    FOOTER      = "footer"
    TITLE       = "title"
    UNKNOWN     = "unknown"


# ═══════════════════════════════════════════════════════════
# FAMILY / STRENGTH — 三层架构之"常识层"
# ═══════════════════════════════════════════════════════════


class Family(Enum):
    """内容族——比 ContentType 粗，承载引擎领域常识。"""
    TEXT      = "text"       # 文本块（TEXT, TITLE, FOOTER）
    BAND      = "band"       # 实体形状（TEXTBOX, TABLE, CHART, IMAGE）
    CONNECTOR = "connector"  # 连线/箭头
    EMPHASIS  = "emphasis"   # 高亮/框选/阴影
    BACKDROP  = "backdrop"   # 衬底


class Strength(Enum):
    """先验强度。STRONG = 违反物理事实（字叠字不可读）；WEAK = 偏好。"""
    STRONG = "strong"
    WEAK   = "weak"


class OverlapVerdict(Enum):
    """重叠判定（不同于 Verdict.ALLOW/WARN/BLOCK——这是先验，不是结果）。"""
    FORBID = "forbid"
    WARN   = "warn"
    ALLOW  = "allow"


# ContentType → Family 映射（架构决定，不是配置）
CONTENT_FAMILY: dict[ContentType, Family] = {
    ContentType.TEXT:       Family.TEXT,
    ContentType.TITLE:      Family.TEXT,
    ContentType.FOOTER:     Family.TEXT,
    ContentType.ANNOTATION: Family.TEXT,  # 小字标注→文本族
    ContentType.TEXTBOX:    Family.BAND,
    ContentType.TABLE:      Family.BAND,
    ContentType.CHART:      Family.BAND,
    ContentType.IMAGE:      Family.BAND,
    ContentType.SHAPE:      Family.BAND,
    ContentType.CONNECTOR:  Family.CONNECTOR,
    ContentType.BACKGROUND: Family.BACKDROP,
    ContentType.UNKNOWN:    Family.BAND,
}


@dataclass
class OverlapPolicy:
    """引擎对一族元素的领域常识——建议而非判决。

    default_role:   AI 没填 role 时的扶手建议
    self_overlap:   同族元素互叠 → Verdict
    over_entity:    叠在异族 ENTITY 上 → Verdict
    strength:       违背此先验时引擎的反应强度
    """
    family: Family
    default_role: SemanticRole
    self_overlap: OverlapVerdict = OverlapVerdict.WARN
    over_entity:  OverlapVerdict = OverlapVerdict.WARN
    strength:     Strength = Strength.WEAK


# ✦ 引擎内置领域常识（单一事实源）
POLICIES: dict[Family, OverlapPolicy] = {
    Family.TEXT: OverlapPolicy(
        Family.TEXT, SemanticRole.ENTITY,
        self_overlap=OverlapVerdict.FORBID,   # "文本一定不重叠" — 可读性是物理事实
        over_entity=OverlapVerdict.WARN,       # 文本叠实体→疑似错标 role
        strength=Strength.STRONG,
    ),
    Family.BAND: OverlapPolicy(
        Family.BAND, SemanticRole.ENTITY,
        self_overlap=OverlapVerdict.WARN,      # 实体互叠→可相切但不可大面积覆
        over_entity=OverlapVerdict.FORBID,     # BAND 叠 BAND = 实体冲突
        strength=Strength.WEAK,
    ),
    Family.CONNECTOR: OverlapPolicy(
        Family.CONNECTOR, SemanticRole.CONNECTOR,
        self_overlap=OverlapVerdict.ALLOW,     # "形状可以重叠" — 箭头穿箭头 OK
        over_entity=OverlapVerdict.ALLOW,      # 箭头穿实体 OK
        strength=Strength.WEAK,
    ),
    Family.EMPHASIS: OverlapPolicy(
        Family.EMPHASIS, SemanticRole.EMPHASIS,
        self_overlap=OverlapVerdict.ALLOW,
        over_entity=OverlapVerdict.ALLOW,      # 高亮框本就压在内容上
        strength=Strength.WEAK,
    ),
    Family.BACKDROP: OverlapPolicy(
        Family.BACKDROP, SemanticRole.BACKDROP,
        self_overlap=OverlapVerdict.ALLOW,
        over_entity=OverlapVerdict.ALLOW,      # 衬底被一切压制
        strength=Strength.WEAK,
    ),
}


def family_of(ct: ContentType) -> Family:
    """ContentType → Family（引擎的粗粒度常识映射）。"""
    return CONTENT_FAMILY.get(ct, Family.BAND)


def _verdict_to_level(v: OverlapVerdict, s: Strength) -> str:
    """OverlapVerdict × Strength → advisory level."""
    if v is OverlapVerdict.FORBID:
        return "error" if s is Strength.STRONG else "warn"
    if v is OverlapVerdict.WARN:
        return "warn"
    return "info"


@dataclass
class Advisory:
    """引擎主动产出的建议——一等公民，不依赖发生碰撞才存在。

    level:    "info"（常识记录）| "warn"（偏离先验）| "error"（违反物理事实）
    message:  常识依据（人话）
    suggest:  语义级修法（人话）
    """
    level: str
    family: Family
    element_id: str
    message: str = ""
    suggest: str = ""


# ═══════════════════════════════════════════════════════════
# ROLE → TABLE mapping（架构唯一事实源——AI 手滑也归不错表）
# ═══════════════════════════════════════════════════════════

ENTITY_ROLES: set[SemanticRole] = {SemanticRole.ENTITY}
OVERLAY_ROLES: set[SemanticRole] = set(SemanticRole) - ENTITY_ROLES

# 渲染 z-order: BACKDROP < ENTITY < CONNECTOR < ANNOTATION < EMPHASIS
ROLE_Z_BASE: dict[SemanticRole, int] = {
    SemanticRole.BACKDROP:      0,
    SemanticRole.ENTITY:      100,
    SemanticRole.CONNECTOR:   200,
    SemanticRole.ANNOTATION:  300,
    SemanticRole.EMPHASIS:    400,
}


def table_of(role: SemanticRole) -> Literal["entity", "overlay"]:
    return "entity" if role in ENTITY_ROLES else "overlay"


# ═══════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════

@dataclass
class GridConfig:
    coarse_cols: int = 16
    coarse_rows: int = 9
    coarse_cell_pt: float = 60.0

    fine_cols: int = 32
    fine_rows: int = 18
    fine_cell_pt: float = 30.0

    overlap_tolerance_pt: float = 5.0
    default_policy: Verdict = Verdict.ALLOW

    canvas_w_pt: float = 960.0
    canvas_h_pt: float = 540.0
    safe_margin_pt: float = 36.0

    density_warn_pct: float = 70.0
    density_critical_pct: float = 85.0

    max_level0_tokens: int = 50
    max_level1_tokens: int = 100
    max_level2_tokens: int = 60


@dataclass
class InfoCell:
    owner_id: str | None = None
    content_type: ContentType | None = None
    role: SemanticRole | None = None  # None = AI 未指定；引擎用族扶手补
    z_order: int = 0
    locked: bool = False
    source: str = "unknown"
    payload: ElementPayload | None = None

    @property
    def is_entity(self) -> bool:
        return self.role in ENTITY_ROLES

    @property
    def has_payload(self) -> bool:
        return self.payload is not None


@dataclass
class ElementPayload:
    """AI 填的渲染负载。role 是语义理解的外化——引擎据此决定碰撞规则。"""
    role: SemanticRole | None = None  # None = AI 未指定；引擎用族扶手补

    # ── 文本 ──
    text: str = ""
    font_size: float = 14.0
    font_color: tuple[int,int,int] = (0x22, 0x22, 0x44)
    font_bold: bool = False
    font_name: str = "Calibri"
    alignment: str = "LEFT"
    fill_color: tuple[int,int,int] | None = None
    line_spacing: float = 1.15
    line_count: int = 1

    # ── 图片 ──
    image_path: str = ""
    fit_mode: str = "fit"

    # ── 形状 ──
    shape_id: str = ""

    # ── 连线 ──
    connector_from: str = ""
    connector_to: str = ""
    connector_anchor_from: str = "center"
    connector_anchor_to: str = "center"
    line_color: tuple[int,int,int] = (0x66, 0x66, 0x66)
    line_width_pt: float = 1.5
    # Phase 2 直传（pt 坐标，绕过 cell 离散化精度损失）
    _abs_x1: float = 0.0
    _abs_y1: float = 0.0
    _abs_x2: float = 0.0
    _abs_y2: float = 0.0


@dataclass
class Conflict:
    cell_addr: str = ""
    existing_id: str = ""
    new_id: str = ""
    existing_type: ContentType = ContentType.UNKNOWN
    new_type: ContentType = ContentType.UNKNOWN
    existing_role: SemanticRole = SemanticRole.ENTITY
    new_role: SemanticRole = SemanticRole.ENTITY
    verdict: Verdict = Verdict.BLOCK
    overlap_pt: float = 0.0
    detail: str = ""


@dataclass
class PlacementResult:
    verdict: Verdict
    conflicts: list[Conflict] = field(default_factory=list)
    warnings: list[Conflict] = field(default_factory=list)
    advisories: list[Advisory] = field(default_factory=list)
    z_hint: str | None = None
    free_suggestion: list[list[str]] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.verdict == Verdict.ALLOW

    @property
    def blocked(self) -> bool:
        return self.verdict == Verdict.BLOCK


@dataclass
class LayoutProfile:
    name: str
    zones: dict[str, list[str]] = field(default_factory=dict)
    locked_zones: set[str] = field(default_factory=set)
    decorative_elements: set[str] = field(default_factory=set)
    page_constraints: dict = field(default_factory=dict)

    def cells_for_role(self, role: str) -> list[str]:
        return self.zones.get(role, [])

    def is_locked_cell(self, cell_addr: str) -> bool:
        return cell_addr in self.locked_zones
