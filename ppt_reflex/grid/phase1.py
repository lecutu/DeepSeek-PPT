"""
grid/phase1.py — Phase 1: 信息层 first-fit + 坐标锁定

铁律：引擎只算真相+出诊断+给菜单，绝不静默修改 AI 声明。
allow_shrink=False 时，装不下的元素直接停，不画，只出 error 诊断。
"""

from __future__ import annotations
from .types import ContentType, ElementPayload, SemanticRole
from .text_metrics import estimate_text_size
from .positioning import bbox_to_fine_cells
from .plan import (
    LayoutPlan, LayoutDiagnostic, PageElement, Region, Phase1Element,
)


def _estimate_width(elem, uw: float) -> float:
    if elem.preferred_width is not None:
        return elem.preferred_width
    payload = elem.payload
    if payload and payload.text.strip():
        from .text_metrics import _line_width
        lw = _line_width(payload.text.replace("\n", ""), payload.font_size)
        return min(lw + 12, uw)
    return uw


def _estimate_height(elem, ew: float) -> float:
    payload = elem.payload
    # 图片是锚点元素——若无显式 preferred_height，占据整个区域高度
    # contain-fit 渲染层再等比缩放到不会溢出
    if elem.content_type == ContentType.IMAGE:
        return 9999.0  # 会被 _place_stack() 的 min(eh, page_h - ey) 夹回区域高
    # 先算文字实际需要的高度
    text_h = 30.0
    if payload and payload.text.strip():
        _, _, _, rh = estimate_text_size(
            payload.text, font_pt=payload.font_size,
            line_spacing=payload.line_spacing,
            box_width_pt=ew, box_height_pt=9999.0, word_wrap=True,
        )
        text_h = max(rh, payload.font_size * 1.5)
    # preferred_height 作为最小高度，不是固定高度
    # 有填充色的 box 文字多行时需要空间撑高，否则白字溢出到浅色背景
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
# PUBLIC
# ═══════════════════════════════════════════════════════════════

def execute_phase1(plan: LayoutPlan, canvas, *, preview_clamp: bool = True) -> list[PageElement]:
    locked: list[PageElement] = []
    PAGE_W = canvas.config.canvas_w_pt
    PAGE_H = canvas.config.canvas_h_pt
    canvas._phase1_rects = {}
    canvas._phase1_payloads = {}

    plan.validate(verbose=True)

    by_region: dict[str, list] = {}
    for elem in plan.phase1_elements:
        by_region.setdefault(elem.region_id, []).append(elem)

    for region in plan.sorted_regions():
        ux, uy, uw, uh, _clamped = _effective_usable(region, PAGE_W, PAGE_H, preview_clamp)
        region_elems = by_region.get(region.region_id, [])
        if not region_elems:
            continue

        mode = region_elems[0].fill_mode
        if mode == "inline":
            _place_inline(region_elems, ux, uy, uw, uh, PAGE_W, PAGE_H,
                          24.0, plan, canvas, locked, region, _clamped)
        else:
            _place_stack(region_elems, ux, uy, uw, uh, PAGE_W, PAGE_H,
                         plan, canvas, locked, region)

    return locked


def _effective_usable(region, page_w, page_h, preview_clamp):
    ux, uy, uw, uh = region.usable_rect
    if not preview_clamp:
        return ux, uy, uw, uh, False
    rx2, ry2 = ux + uw, uy + uh
    clamped = ux < -0.5 or uy < -0.5 or rx2 > page_w + 0.5 or ry2 > page_h + 0.5
    if not clamped:
        return ux, uy, uw, uh, False
    nux = max(0.0, ux)
    nuy = max(0.0, uy)
    nuw = max(1.0, min(uw - (nux - ux), page_w - nux))
    nuh = max(1.0, min(uh - (nuy - uy), page_h - nuy))
    return nux, nuy, nuw, nuh, True


# ═══════════════════════════════════════════════════════════════
# INLINE
# ═══════════════════════════════════════════════════════════════

_ARROW_SLOT = 48.0


def _place_inline(elems, ux, uy, uw, uh, page_w, page_h, min_w,
                  plan, canvas, locked, region, was_clamped):
    n = len(elems)
    gap = max(_ARROW_SLOT, elems[0].margin_above)
    widths = [max(min_w, e.preferred_width or _estimate_width(e, uw)) for e in elems]
    total_demand = sum(widths) + gap * (n - 1)

    print(f"[INLINE][{region.region_id}] demand={total_demand:.0f} > usable={uw:.0f}? "
          f"{total_demand > uw + 0.5}")

    if total_demand > uw + 0.5:
        over_by = total_demand - uw
        plan.diagnostics.append(LayoutDiagnostic(
            kind="inline_overflow", severity="error",
            region_id=region.region_id,
            demand_pt=total_demand, usable_pt=uw, over_by_pt=over_by,
            message=f"inline 装不下: {n} 块 demand={total_demand:.0f} > usable={uw:.0f} (超 {over_by:.0f}pt)",
            options=_inline_options(elems, uw, total_demand, region, plan, page_w),
        ))
        return

    cursor_x = ux
    for i, elem in enumerate(elems):
        ex, ew = cursor_x, widths[i]
        h = _estimate_height(elem, ew)
        ey = max(0.0, min(uy, page_h - 1))
        eh = max(1.0, min(h, page_h - ey))
        _commit_element(elem, ex, ey, ew, eh, plan, canvas, locked, region)
        if i < n - 1:
            cursor_x = ex + ew + gap


def _inline_options(elems, uw, demand, region, plan, page_w):
    n = len(elems)
    gap = _ARROW_SLOT
    target_w = max(24, (uw - gap * (n - 1)) / max(n, 1))
    need_rw = demand + 24
    free_r = page_w - region.x - 12
    return [
        f"等比缩: preferred_width -> {target_w:.0f}pt ({target_w / max(elems[0].preferred_width or 120, 1) * 100:.0f}%)",
        f"拆行: {n} 块分两行 ({n // 2 + n % 2}+{n // 2})，需加行高",
        f"转垂直: fill_mode=stack，region 高需 >= {n * 60:.0f}pt",
        f"加宽 region: w -> {need_rw:.0f}pt (右侧可用 {free_r:.0f}pt)",
        f"减步: 合并 {n} 步为更少步（语义调整）",
    ]


# ══════════════════════════════════════════════════
# AUDIT
# ══════════════════════════════════════════════════

def _text_one_line_width(text: str, font_size: float) -> float:
    from .text_metrics import _line_width
    return float(_line_width(text, font_size))


def audit_plan(plan: LayoutPlan, canvas) -> list[LayoutDiagnostic]:
    rects = getattr(canvas, "_phase1_rects", {})
    for e in plan.elements:
        text = ""; fs = 14.0
        if e.payload:
            text = e.payload.text; fs = e.payload.font_size
        if not text.strip() or "\n" in text:
            continue
        r = rects.get(e.elem_id)
        box_w = r[2] if r else e.w
        if box_w <= 0:
            continue
        one_line = _text_one_line_width(text, fs)
        if one_line > box_w + 1.0:
            if getattr(e, "allow_wrap", False):
                continue
            plan.diagnostics.append(LayoutDiagnostic(
                kind="text_wrap", severity="warning",
                elem_id=e.elem_id, region_id=getattr(e, "region_id", ""),
                demand_pt=one_line, usable_pt=box_w, over_by_pt=one_line - box_w,
                message=f"文本单行需 {one_line:.0f}pt > 框宽 {box_w:.0f}pt -> 会掉行",
                options=[
                    f"加宽元素到 >= {one_line + 8:.0f}pt",
                    f"缩字号到 <= {fs * box_w / one_line:.0f}pt",
                    "设 allow_wrap=true",
                ],
            ))
    return plan.diagnostics
