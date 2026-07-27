"""
grid/phase1.py — Phase 1: information layer first-fit + coordinate lock

Iron law: engine only computes truth + produces diagnostics + gives menus, never silently mutates AI declarations.
When allow_shrink=False, elements that don't fit stop, don't render, only produce error diagnostics.
"""

from __future__ import annotations
from .types import ContentType, ElementPayload, Verdict
from .plan import LayoutPlan, Region, Phase1Element, PageElement, LayoutDiagnostic
from .canvas import GridCanvas
from .text_metrics import estimate_text_size


def _estimate_width(elem, uw):
    if elem.preferred_width is not None:
        return elem.preferred_width
    margin = getattr(elem, 'ARROW_SLOT', 48.0)
    if elem.fill_mode == "inline":
        return uw - margin
    return uw


def _estimate_height(elem, ew: float) -> float:
    payload = elem.payload
    # Images are anchor elements — if no explicit preferred_height, occupy full region height
    # contain-fit rendering layer scales proportionally to prevent overflow
    if elem.content_type == ContentType.IMAGE:
        return 9999.0  # clamped by _place_stack() min(eh, page_h - ey) to region height
    # Compute text demand height first
    text_h = 30.0
    if payload and payload.text.strip():
        _, _, _, rh = estimate_text_size(
            payload.text, font_pt=payload.font_size,
            line_spacing=payload.line_spacing,
            box_width_pt=ew, box_height_pt=9999.0, word_wrap=True,
        )
        text_h = max(rh, payload.font_size * 1.5)
    # preferred_height acts as minimum, not fixed
    # Boxes with fill need room for multi-line text; otherwise white text overflows onto light background
    if elem.preferred_height is not None:
        return max(elem.preferred_height, text_h)
    return text_h


def _commit_element(elem, ex, ey, ew, eh, plan, canvas, locked, region):
    pe = PageElement(
        elem_id=elem.elem_id, region_id=getattr(elem, "region_id", region.region_id),
        content_type=getattr(elem, "content_type", ContentType.UNKNOWN),
        payload=getattr(elem, "payload", None),
        x=ex, y=ey, w=ew, h=eh,
        allow_wrap=getattr(elem, "allow_wrap", False),
        z_order=100,
    )
    locked.append(pe)
    plan.elements.append(pe)
    region.elements.append(elem.elem_id)
    if not hasattr(canvas, '_phase1_rects'):
        canvas._phase1_rects = {}
    canvas._phase1_rects[elem.elem_id] = (ex, ey, ew, eh)
    if not hasattr(canvas, '_phase1_payloads'):
        canvas._phase1_payloads = {}
    canvas._phase1_payloads[elem.elem_id] = (
        getattr(elem, "content_type", ContentType.UNKNOWN),
        getattr(elem, "payload", None),
    )


def _place_stack(elems, ux, uy, uw, uh, page_w, page_h,
                 plan, canvas, locked, region):
    cy = uy
    for elem in elems:
        ew = min(_estimate_width(elem, uw), uw)
        eh = _estimate_height(elem, ew)
        ex = ux
        if ex + ew > ux + uw + 2:
            ew = max(1.0, ux + uw - ex)
        ey = max(0.0, min(cy, page_h - 1))
        h = max(1.0, min(eh, page_h - ey, uy + uh - ey))
        _commit_element(elem, ex, ey, ew, h, plan, canvas, locked, region)
        cy = ey + h + elem.margin_above


# ═══════════════════════════════════════════════════════════════

def execute_phase1(plan: LayoutPlan, canvas: GridCanvas) -> list[PageElement]:
    """Phase 1: first-fit layout. Returns locked elements with coordinates."""
    locked: list[PageElement] = []

    for region in plan.sorted_regions():
        if not hasattr(region, 'elements'):
            region.elements = []
        r_elems = [e for e in plan.phase1_elements if e.region_id == region.region_id]
        if not r_elems:
            continue

        ux, uy, uw, uh = region.usable_rect
        inline_elems = [e for e in r_elems if e.fill_mode == "inline"]
        stack_elems = [e for e in r_elems if e.fill_mode != "inline"]

        # Inline elements placed first at top
        if inline_elems:
            _place_inline(inline_elems, ux, uy, uw, uh, plan.page_w, plan.page_h,
                         plan, canvas, locked, region)

        # Stack elements fill remaining vertical space
        if stack_elems:
            # Find the bottom of inline row
            top = uy
            for eid in region.elements:
                rect = canvas._phase1_rects.get(eid)
                if rect:
                    bot = rect[1] + rect[3]
                    if bot > top:
                        top = bot + 4  # 4pt gap
            _place_stack(stack_elems, ux, top, uw, uy + uh - top, plan.page_w, plan.page_h,
                        plan, canvas, locked, region)

    return locked


def _place_inline(elems, ux, uy, uw, uh, page_w, page_h,
                  plan, canvas, locked, region):
    """Inline horizontal placement — elements placed side by side. Respect ARROW_SLOT gaps."""
    n = len(elems)
    if n == 0:
        return

    gap = Phase1Element.arrow_gap(elems)
    total_demand = sum(
        _estimate_width(e, uw) for e in elems
    ) + gap * (n - 1)

    # Check if inline fits horizontally
    if total_demand > uw + 2:
        over_by = total_demand - uw
        plan.diagnostics.append(LayoutDiagnostic(
            kind="inline_overflow", severity="warning", region_id=region.region_id,
            demand_pt=total_demand, usable_pt=uw, over_by_pt=over_by,
            message=f"inline does not fit: {n} blocks demand={total_demand:.0f} > usable={uw:.0f} (exceeds by {over_by:.0f}pt)",
            options=[
                "proportional shrink: preferred_width -> smaller (same ratio for whole block)",
                f"split rows: {n} blocks to two rows ({n // 2 + n % 2}+{n // 2}), needs extra row height",
                f"switch to vertical: fill_mode=stack, region height needs >= {n * 60:.0f}pt",
                f"widen region: w -> {total_demand:.0f}pt (right side has {page_w - ux - uw:.0f}pt free)",
                f"reduce steps: merge {n} steps into fewer (semantic adjustment)",
            ],
        ))

    # First-fit: place each inline element left to right
    cx = ux
    for e in elems:
        ew = min(_estimate_width(e, uw), uw)
        eh = _estimate_height(e, ew)
        if cx + ew > ux + uw + 2:
            ew = max(1.0, ux + uw - cx)
        ey = uy
        h = min(eh, page_h - ey)
        _commit_element(e, cx, ey, ew, h, plan, canvas, locked, region)
        cx += ew + gap


def audit_plan(plan: LayoutPlan, canvas: GridCanvas) -> None:
    """Post-Phase-1 audit: text-wrap width/drop-line checks per element."""
    if not hasattr(canvas, '_phase1_payloads'):
        return
    for eid, (ct, payload) in canvas._phase1_payloads.items():
        if ct not in (ContentType.TEXT, ContentType.TEXTBOX):
            continue
        if not payload or not payload.text.strip():
            continue
        rect = canvas._phase1_rects.get(eid)
        if not rect:
            continue
        _, _, w, _ = rect
        e = plan.element_by_id(eid)
        if not e or getattr(e, 'allow_wrap', False):
            continue

        _, _, rw, _ = estimate_text_size(
            payload.text, font_pt=payload.font_size,
            line_spacing=payload.line_spacing,
            box_width_pt=w, box_height_pt=9999.0, word_wrap=True,
        )
        box_w = rect[2] if rect else w
        if box_w <= 0:
            continue

        # Check if any single line exceeds box width
        first_line = payload.text.split("\n")[0]
        from .text_metrics import _line_width
        one_line = _line_width(first_line, payload.font_size)
        if one_line > box_w + 1.0:
            fs = payload.font_size
            plan.diagnostics.append(LayoutDiagnostic(
                kind="text_wrap", severity="warning", elem_id=eid,
                demand_pt=one_line, usable_pt=box_w, over_by_pt=one_line - box_w,
                message=f"single text line needs {one_line:.0f}pt > box width {box_w:.0f}pt -> will drop to next line",
                options=[
                    f"widen element to >= {one_line + 8:.0f}pt",
                    f"shrink font size to <= {fs * box_w / one_line:.0f}pt",
                    "set allow_wrap=true",
                ],
            ))
