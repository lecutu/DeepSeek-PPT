"""grid/__init__.py — 🔒 内部引擎。直接调用会被 Builder 绕过诊断回路，产生空白文字。
AI Agent 请一律使用:
    from ppt_reflex.builder import PPTBuilder
    builder = PPTBuilder(template="academic")
    builder.add_slide(...)
    builder.build("out.pptx")
"""

from .types import (
    GridConfig, ContentType, Verdict, InfoCell,
    Conflict, PlacementResult, LayoutProfile,
    SemanticRole, ElementPayload,
    Family, Strength, OverlapVerdict, OverlapPolicy, Advisory,
    ENTITY_ROLES, OVERLAY_ROLES, ROLE_Z_BASE, table_of,
    POLICIES, family_of,
)
from .positioning import (
    cell_name, parse_cell,
    cells_to_bbox, bbox_to_coarse_cells, bbox_to_fine_cells,
    cell_range, is_cell_in_bounds,
)
from .info_grid import InformationGrid
from .matrix import InteractionMatrix
from .canvas import GridCanvas
from .serializer import classify_shape, ppt_to_grid, grid_to_ppt
from .supply import Supply
from .spatial import SpatialIndex
from .profiles import infer_profile
from .text_metrics import estimate_text_size, expand_bbox, OverflowReport
from .aesthetics import AestheticsEngine, AestheticViolation, ElemStyle
from .templates import TEMPLATES, TemplateProfile, get_template, AGENT_PROMPT
from .plan import LayoutPlan, Region, Phase1Element, DecoIntent, DecorationSpec, PageElement, LayoutDiagnostic, FeedbackBundle
from .phase1 import execute_phase1, audit_plan
from .phase2 import execute_phase2
from .orchestrator import layout_loop
from .composition import global_composition_check

__all__ = [
    # types
    "GridConfig", "ContentType", "Verdict", "InfoCell",
    "Conflict", "PlacementResult", "LayoutProfile",
    "SemanticRole", "ElementPayload",
    "Family", "Strength", "OverlapVerdict", "OverlapPolicy", "Advisory",
    "ENTITY_ROLES", "OVERLAY_ROLES", "ROLE_Z_BASE", "table_of",
    "POLICIES", "family_of",
    # positioning
    "cell_name", "parse_cell",
    "cells_to_bbox", "bbox_to_coarse_cells", "bbox_to_fine_cells",
    "cell_range", "is_cell_in_bounds",
    # info_grid
    "InformationGrid",
    # matrix
    "InteractionMatrix",
    # canvas
    "GridCanvas",
    # serializer
    "classify_shape", "ppt_to_grid", "grid_to_ppt",
    # supply
    "Supply",
    # spatial
    "SpatialIndex",
    # profiles
    "infer_profile",
    # text_metrics
    "estimate_text_size", "expand_bbox", "OverflowReport",
    # aesthetics
    "AestheticsEngine", "AestheticViolation", "ElemStyle",
    # templates
    "TEMPLATES", "TemplateProfile", "get_template", "AGENT_PROMPT",
    # two-layer five-phase architecture
    "LayoutPlan", "Region", "Phase1Element", "DecoIntent",
    "DecorationSpec", "PageElement", "LayoutDiagnostic", "FeedbackBundle",
    "execute_phase1", "audit_plan", "execute_phase2",
    "layout_loop", "global_composition_check",
]
