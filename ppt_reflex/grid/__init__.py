"""grid/__init__.py - public API"""

from .types import (
    GridConfig, ContentType, Verdict, InfoCell,
    Conflict, PlacementResult, LayoutProfile,
    BLOCK_PAIRS, DEFAULT_POLICY, Z_ORDER_RULES,
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

__all__ = [
    # types
    "GridConfig", "ContentType", "Verdict", "InfoCell",
    "Conflict", "PlacementResult", "LayoutProfile",
    "BLOCK_PAIRS", "DEFAULT_POLICY", "Z_ORDER_RULES",
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
]
