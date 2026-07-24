"""
L3 布局引擎：8 种固定页面类型模板

每个模板定义：
  - 安全区
  - 网格区域分区
  - 元素角色约束
  - 默认 spacing
  - 溢出处理策略

Agent 选择模板名，引擎计算坐标。
"""

from __future__ import annotations
from engine import (
    SlideElement, BBox, ContentRole, CollisionRole,
    COARSE_CELL_PT, DEFAULT_SLIDE_W, DEFAULT_SLIDE_H, SAFE_MARGIN_PT,
)
from dataclasses import dataclass, field
from typing import Optional


# ── template definition ────────────────────────────────────
@dataclass
class Region:
    """A named rectangle region within a template, specified in grid cells."""
    name: str
    col_start: int    # 0-indexed coarse grid column
    col_end: int      # inclusive
    row_start: int
    row_end: int      # inclusive
    allowed_roles: list[str]  # ContentRole values allowed here
    min_font_pt: float = 12

    def to_bbox_pt(self, grid_cell_pt: float = COARSE_CELL_PT) -> BBox:
        return BBox(
            x=self.col_start * grid_cell_pt,
            y=self.row_start * grid_cell_pt,
            w=(self.col_end - self.col_start + 1) * grid_cell_pt,
            h=(self.row_end - self.row_start + 1) * grid_cell_pt,
        )

    @property
    def grid_range(self) -> str:
        """e.g. 'A1:D2'"""
        from engine import _cell_name
        return f"{_cell_name(self.col_start, self.row_start)}:{_cell_name(self.col_end, self.row_end)}"


@dataclass
class LayoutTemplate:
    name: str
    description: str
    regions: list[Region]

    def region_for_role(self, role: str) -> Optional[Region]:
        for r in self.regions:
            if role in r.allowed_roles:
                return r
        return None

    def all_regions(self) -> list[Region]:
        return self.regions


# ═══════════════════════════════════════════════════════════
# 8 BUILT-IN TEMPLATES
# ═══════════════════════════════════════════════════════════

TEMPLATES: dict[str, LayoutTemplate] = {
    # ── 1. title only ──────────────────────────────────────
    "title_only": LayoutTemplate(
        name="title_only",
        description="Title + subtitle centered",
        regions=[
            Region("title",    0, 15, 2, 3, ["title"], min_font_pt=28),
            Region("subtitle", 0, 15, 4, 5, ["subtitle"], min_font_pt=18),
        ],
    ),

    # ── 2. title + body ────────────────────────────────────
    "title_body": LayoutTemplate(
        name="title_body",
        description="Title top, body fills remainder",
        regions=[
            Region("title", 0, 15, 1, 2, ["title"], min_font_pt=24),
            Region("body",  0, 15, 3, 8, ["body", "citation"], min_font_pt=14),
        ],
    ),

    # ── 3. text left, figure right ─────────────────────────
    "text_left_figure_right": LayoutTemplate(
        name="text_left_figure_right",
        description="60/40 split: body left, figure right",
        regions=[
            Region("title",  0, 15, 1, 2, ["title"], min_font_pt=24),
            Region("body",   0, 9,  3, 8, ["body", "key_metric", "citation"], min_font_pt=14),
            Region("figure", 10, 15, 3, 7, ["figure"], min_font_pt=11),
            Region("caption",10, 15, 8, 8, ["caption"], min_font_pt=11),
        ],
    ),

    # ── 4. figure left, text right ─────────────────────────
    "figure_left_text_right": LayoutTemplate(
        name="figure_left_text_right",
        description="40/60 split: figure left, body right",
        regions=[
            Region("title",  0, 15, 1, 2, ["title"], min_font_pt=24),
            Region("figure", 0, 5,  3, 7, ["figure"], min_font_pt=11),
            Region("caption",0, 5,  8, 8, ["caption"], min_font_pt=11),
            Region("body",   6, 15, 3, 8, ["body", "key_metric", "citation"], min_font_pt=14),
        ],
    ),

    # ── 5. two column compare ──────────────────────────────
    "two_column_compare": LayoutTemplate(
        name="two_column_compare",
        description="Title + two equal body columns for comparison",
        regions=[
            Region("title",   0, 15, 1, 2, ["title"], min_font_pt=24),
            Region("body_left", 0, 7,  3, 8, ["body", "key_metric"], min_font_pt=14),
            Region("body_right",8, 15, 3, 8, ["body", "key_metric"], min_font_pt=14),
        ],
    ),

    # ── 6. three metrics ───────────────────────────────────
    "three_metrics": LayoutTemplate(
        name="three_metrics",
        description="Title + three key metrics side by side",
        regions=[
            Region("title", 0, 15, 1, 2, ["title"], min_font_pt=24),
            Region("metric_1", 0, 4,  3, 6, ["key_metric"], min_font_pt=20),
            Region("metric_2", 5, 9,  3, 6, ["key_metric"], min_font_pt=20),
            Region("metric_3", 10, 15,3, 6, ["key_metric"], min_font_pt=20),
            Region("body",   0, 15, 7, 8, ["body", "caption"], min_font_pt=14),
        ],
    ),

    # ── 7. process flow ────────────────────────────────────
    "process_flow": LayoutTemplate(
        name="process_flow",
        description="Title + horizontal process steps + body below",
        regions=[
            Region("title",  0, 15, 1, 2, ["title"], min_font_pt=24),
            Region("step_1", 0, 3,  3, 4, ["key_metric", "body"], min_font_pt=14),
            Region("step_2", 4, 7,  3, 4, ["key_metric", "body"], min_font_pt=14),
            Region("step_3", 8, 11, 3, 4, ["key_metric", "body"], min_font_pt=14),
            Region("step_4", 12,15, 3, 4, ["key_metric", "body"], min_font_pt=14),
            Region("body",   0, 15, 5, 8, ["body", "caption", "citation"], min_font_pt=14),
        ],
    ),

    # ── 8. full bleed (image background + overlay text) ────
    "full_bleed_image": LayoutTemplate(
        name="full_bleed_image",
        description="Background image full-bleed with overlaid text box",
        regions=[
            Region("background", 0, 15, 0, 8, ["figure"], min_font_pt=0),
            Region("overlay",    2, 13, 4, 6, ["body", "key_metric", "title"], min_font_pt=18),
        ],
    ),
}


# ═══════════════════════════════════════════════════════════
# LAYOUT ENGINE (template resolver)
# ═══════════════════════════════════════════════════════════
class LayoutEngine:
    """Given a template name + role→element mapping, computes coordinates."""

    def __init__(self, canvas_w_pt: float = DEFAULT_SLIDE_W,
                 canvas_h_pt: float = DEFAULT_SLIDE_H):
        self.templates = TEMPLATES
        self.canvas_w = canvas_w_pt
        self.canvas_h = canvas_h_pt

    def get_template(self, name: str) -> LayoutTemplate:
        if name not in self.templates:
            raise KeyError(f"Unknown template '{name}'. Available: {list(self.templates)}")
        return self.templates[name]

    def list_templates(self) -> list[dict]:
        return [{"name": k, "desc": v.description, "regions": [r.name for r in v.regions]}
                for k, v in self.templates.items()]

    def resolve_positions(self, template_name: str, role_mapping: dict[str, str]) -> dict[str, BBox]:
        """
        template_name: e.g. 'text_left_figure_right'
        role_mapping: {"body": "shape-05", "figure": "shape-07", "title": "shape-01", "caption": "shape-12"}
        Returns: {element_id: BBox} for elements to be moved into template regions.
        """
        template = self.get_template(template_name)
        positions: dict[str, BBox] = {}
        for region in template.regions:
            # find which mapped role goes here
            for role in region.allowed_roles:
                if role in role_mapping:
                    eid = role_mapping[role]
                    if eid not in positions:  # first match wins
                        positions[eid] = region.to_bbox_pt()
                        break
        return positions

    def resolve_single(self, template_name: str, role: str) -> Optional[BBox]:
        """Get the bbox for a single role within a template."""
        template = self.get_template(template_name)
        region = template.region_for_role(role)
        return region.to_bbox_pt() if region else None

    def get_region_grid(self, template_name: str, role: str) -> Optional[str]:
        template = self.get_template(template_name)
        region = template.region_for_role(role)
        return region.grid_range if region else None
