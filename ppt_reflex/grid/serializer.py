"""
grid/serializer.py — Grid 状态 ↔ PPT 文件（唯一碰 python-pptx 的地方）

读:  PPT 文件 → InformationGrid（重建信息层）
写:  InformationGrid → PPT 文件（原子写入）
分类: python-pptx shape → ContentType
"""

from __future__ import annotations
import copy

from .types import GridConfig, ContentType, InfoCell
from .info_grid import InformationGrid
from .positioning import bbox_to_fine_cells


# ═══════════════════════════════════════════════════════════
# READ: PPT → InformationGrid
# ═══════════════════════════════════════════════════════════

def ppt_to_grid(ppt_path: str, slide_index: int,
                config: GridConfig | None = None) -> InformationGrid:
    """从 PPT 文件读取指定幻灯片，重建信息层。

    Args:
        ppt_path: .pptx 文件路径
        slide_index: 0-indexed 幻灯片序号
        config: 网格配置

    Returns:
        填充好的 InformationGrid
    """
    from pptx import Presentation

    cfg = config or GridConfig()
    grid = InformationGrid(cfg)
    prs = Presentation(ppt_path)
    slides = list(prs.slides)

    if slide_index >= len(slides):
        raise IndexError(f"Slide {slide_index} not found (total: {len(slides)})")

    slide = slides[slide_index]
    slide_w_emu = prs.slide_width    # EMU
    slide_h_emu = prs.slide_height

    for shape in slide.shapes:
        try:
            left_pt = shape.left / 12700   # EMU → pt (python-pptx)
            top_pt = shape.top / 12700
            width_pt = shape.width / 12700
            height_pt = shape.height / 12700
        except Exception:
            continue

        content_type = classify_shape(shape)
        shape_id = _shape_id(shape)
        fine_cells = bbox_to_fine_cells(left_pt, top_pt, width_pt, height_pt, cfg)
        if not fine_cells:
            continue

        is_template = _is_template_element(shape)

        grid.occupy(
            fine_cells,
            owner_id=shape_id,
            content_type=content_type,
            z_order=_z_order(shape),
            locked=is_template,
            source="template" if is_template else "human",
        )

    return grid


# ═══════════════════════════════════════════════════════════
# WRITE: InformationGrid → PPT
# ═══════════════════════════════════════════════════════════

def grid_to_ppt(grid: InformationGrid, config: GridConfig, ppt_path: str) -> None:
    """将信息层状态写入 PPT 文件。

    遍历所有被占用的元素 → 按 owner_id 聚合 bbox → 写入 pptx。
    locked 元素坐标不变（模板装饰）。
    """
    from pptx import Presentation
    from pptx.util import Pt

    occ = grid.all_occupied()
    if not occ:
        return

    prs = Presentation()
    slide_layout = prs.slide_layouts[6]  # blank
    slide = prs.slides.add_slide(slide_layout)

    for owner_id, fine_cells in occ.items():
        # 聚合 fine_cells 为 bbox
        bbox = _cells_union(fine_cells, grid.config)
        if bbox is None:
            continue
        x, y, w, h = bbox

        content_type = _get_type_for_id(owner_id, fine_cells, grid)
        cell_sample = grid.get_cell(next(iter(fine_cells)))
        locked = cell_sample.locked if cell_sample else False

        if content_type == ContentType.TEXT:
            box = slide.shapes.add_textbox(Pt(x), Pt(y), Pt(w), Pt(h))
            box.text_frame.text = ""
        elif content_type == ContentType.TEXTBOX:
            box = slide.shapes.add_shape(
                1, Pt(x), Pt(y), Pt(w), Pt(h)  # MSO_SHAPE.RECTANGLE
            )
            box.text_frame.text = ""
        elif content_type == ContentType.IMAGE:
            box = slide.shapes.add_picture(
                _placeholder_png(), Pt(x), Pt(y), Pt(w), Pt(h)
            )
        elif content_type == ContentType.SHAPE:
            box = slide.shapes.add_shape(
                1, Pt(x), Pt(y), Pt(w), Pt(h)
            )
        else:
            box = slide.shapes.add_textbox(Pt(x), Pt(y), Pt(w), Pt(h))

    prs.save(ppt_path)


# ═══════════════════════════════════════════════════════════
# CLASSIFY: shape → ContentType
# ═══════════════════════════════════════════════════════════

def classify_shape(shape) -> ContentType:
    """python-pptx shape → ContentType 分类。

    逻辑:
      PICTURE       → IMAGE
      TABLE         → TABLE
      CHART         → CHART
      TEXT_BOX      → 有 fill 且无文字 → SHAPE
                     → 有 fill 且有文字 → TEXTBOX
                     → 无 fill 有文字 → TEXT
      其他          → UNKNOWN
    """
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    try:
        shape_type = shape.shape_type
    except Exception:
        return ContentType.UNKNOWN

    # Picture
    if shape_type == MSO_SHAPE_TYPE.PICTURE:
        return ContentType.IMAGE

    # Table
    if shape_type == MSO_SHAPE_TYPE.TABLE:
        return ContentType.TABLE

    # Chart
    if shape_type == MSO_SHAPE_TYPE.CHART:
        return ContentType.CHART

    # Placeholder / Text Box / Auto Shape
    if shape_type in (MSO_SHAPE_TYPE.TEXT_BOX, MSO_SHAPE_TYPE.PLACEHOLDER,
                      MSO_SHAPE_TYPE.AUTO_SHAPE):
        from pptx.enum.dml import MSO_FILL_TYPE
        has_text = False
        has_fill = False

        try:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text:
                    has_text = True
        except Exception:
            pass

        try:
            fill = shape.fill
            ft = fill.type
            # BACKGROUND/NONE → no explicit fill. SOLID/PATTERN/GRADIENT/etc → has fill.
            if ft is not None and ft not in (MSO_FILL_TYPE.BACKGROUND,):
                has_fill = True
        except Exception:
            pass

        if has_text and has_fill:
            return ContentType.TEXTBOX
        if has_text:
            return ContentType.TEXT
        if has_fill:
            return ContentType.SHAPE
        return ContentType.UNKNOWN

    if shape_type == MSO_SHAPE_TYPE.GROUP:
        # 不深入组内，整个组标记为 UNKNOWN
        return ContentType.UNKNOWN

    return ContentType.UNKNOWN


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _shape_id(shape) -> str:
    """提取 shape 的唯一稳定 ID。"""
    try:
        return f"shape-{shape.shape_id}"
    except Exception:
        try:
            return f"shape-{hash(shape.name)}"
        except Exception:
            return f"shape-{id(shape)}"


def _z_order(shape) -> int:
    """shape 的 z-order。"""
    try:
        return shape.z_order
    except Exception:
        return 0


def _is_template_element(shape) -> bool:
    """判断 shape 是否来自母版/版式（非用户添加）。"""
    try:
        if getattr(shape, 'is_placeholder', False):
            return True
    except Exception:
        pass
    try:
        # python-pptx: 检查是否在 slide layout 上
        if hasattr(shape, 'part') and 'slideLayout' in str(type(shape.part)):
            return True
    except Exception:
        pass
    return False


def _cells_union(fine_cells: set[str], config: GridConfig) -> tuple | None:
    """一组信息格地址 → 最小包围矩形 (x, y, w, h) pt。"""
    from .positioning import parse_cell, cell_name

    if not fine_cells:
        return None
    parsed = [parse_cell(c) for c in fine_cells]
    min_col = min(p[0] for p in parsed)
    max_col = max(p[0] for p in parsed)
    min_row = min(p[1] for p in parsed)
    max_row = max(p[1] for p in parsed)
    x = min_col * config.fine_cell_pt
    y = min_row * config.fine_cell_pt
    w = (max_col - min_col + 1) * config.fine_cell_pt
    h = (max_row - min_row + 1) * config.fine_cell_pt
    return (x, y, w, h)


def _get_type_for_id(owner_id: str, cells: set[str], grid: InformationGrid) -> ContentType:
    """从信息格中取该 owner 的类型（取第一个非空 cell 的 content_type）。"""
    for addr in sorted(cells):
        cell = grid.get_cell(addr)
        if cell and cell.content_type:
            return cell.content_type
    return ContentType.UNKNOWN


def _placeholder_png() -> str:
    """返回一个 1×1 透明的 PNG 作为占位图。"""
    import tempfile, base64, os
    # 最小的 1x1 透明 PNG
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "+P+/HgAFhAJ/qlOqBAAAAABJRU5ErkJggg=="
    )
    data = base64.b64decode(png_b64)
    tmp = os.path.join(tempfile.gettempdir(), "_ppt_reflex_placeholder.png")
    if not os.path.exists(tmp):
        with open(tmp, 'wb') as f:
            f.write(data)
    return tmp
