"""
grid/phase2.py — Phase 2: 装饰坐标解析 + 遮挡检测

箭头端点 100% 贴 Phase1 落定 rect（同源 lookup）。
出界只标注，不静默夹——越界诊断喂给 AI 走回路。
"""

from __future__ import annotations
from .plan import LayoutPlan, DecoIntent, DecorationSpec, LayoutDiagnostic


def execute_phase2(plan: LayoutPlan, canvas) -> list[DecorationSpec]:
    rects = getattr(canvas, "_phase1_rects", {})
    lookup: dict[str, tuple[float, float, float, float]] = {}
    for e in plan.elements:
        r = rects.get(e.elem_id)
        if r:
            lookup[e.elem_id] = r

    resolved: list[DecorationSpec] = []
    for intent in plan.deco_intents:
        spec = _resolve_deco(intent, lookup, plan)
        resolved.append(spec)
        plan.decorations.append(spec)
    return resolved


def _resolve_deco(intent, lookup, plan):
    refs = [lookup[rid] for rid in intent.relative_to if rid in lookup]
    if not refs:
        return DecorationSpec(
            deco_id=intent.deco_id, deco_type=intent.deco_type,
            occlusion_warnings=["no valid reference elements"],
        )
    if intent.deco_type == "arrow" and len(refs) >= 2:
        return _resolve_arrow(intent, refs[0], refs[-1], lookup, plan)
    ref_x, ref_y, ref_w, ref_h = refs[0]
    px, py = _resolve_position(ref_x, ref_y, ref_w, ref_h,
                               intent.direction, intent.margin_pt)
    return DecorationSpec(
        deco_id=intent.deco_id, deco_type=intent.deco_type,
        x1=px, y1=py, style=intent.style,
        text=intent.text, text_font_size=intent.text_font_size,
        text_color=intent.text_color,
    )


def _resolve_arrow(intent, src, dst, lookup, plan):
    sx, sy, sw, sh = src
    dx, dy, dw, dh = dst
    sx_c, sy_c = sx + sw / 2, sy + sh / 2
    dx_c, dy_c = dx + dw / 2, dy + dh / 2

    # 锚点：100% 贴 Phase 1 落定的 rect，不重新算
    if abs(dx_c - sx_c) > abs(dy_c - sy_c):
        if dx_c >= sx_c:
            x1, y1 = sx + sw, sy_c     # src 右边中点
            x2, y2 = dx, dy_c          # dst 左边中点
        else:
            x1, y1 = sx, sy_c          # src 左边中点
            x2, y2 = dx + dw, dy_c     # dst 右边中点
    else:
        if dy_c >= sy_c:
            x1, y1 = sx_c, sy + sh     # src 底部中点
            x2, y2 = dx_c, dy          # dst 顶部中点
        else:
            x1, y1 = sx_c, sy          # src 顶部中点
            x2, y2 = dx_c, dy + dh     # dst 底部中点

    # 不静默夹：检查并标注，不掩盖
    pw, ph = plan.page_w, plan.page_h
    if not (0 <= x1 <= pw and 0 <= y1 <= ph and 0 <= x2 <= pw and 0 <= y2 <= ph):
        plan.diagnostics.append(LayoutDiagnostic(
            kind="deco_out_of_page", severity="warning", elem_id=intent.deco_id,
            message=f"arrow 端点出界 ({x1:.0f},{y1:.0f})->({x2:.0f},{y2:.0f})",
            options=["先修上游相对元素的位置，勿在 phase2 夹坐标掩盖"],
        ))

    # 硬 clamp 仅保证渲染不崩（裁剪交渲染层），但不消除诊断
    x1 = max(0, min(x1, pw - 1))
    y1 = max(0, min(y1, ph - 1))
    x2 = max(0, min(x2, pw - 1))
    y2 = max(0, min(y2, ph - 1))

    warnings: list[str] = []
    if intent.occlusion_check:
        warnings = _check_path_vs_rects(x1, y1, x2, y2, intent, lookup)

    line_color = intent.style.get("line_color", (0x66, 0x66, 0x66))
    line_w = intent.style.get("line_width_pt", 1.5)

    return DecorationSpec(
        deco_id=intent.deco_id, deco_type="arrow",
        x1=x1, y1=y1, x2=x2, y2=y2,
        style={"line_color": line_color, "line_width_pt": line_w, **intent.style},
        text=intent.text, text_font_size=intent.text_font_size,
        text_color=intent.text_color,
        occlusion_warnings=warnings,
    )


def _check_path_vs_rects(x1, y1, x2, y2, intent, lookup):
    warnings: list[str] = []
    for eid, (rx, ry, rw, rh) in lookup.items():
        if eid in intent.relative_to:
            continue
        if _line_crosses_rect(x1, y1, x2, y2, rx, ry, rx + rw, ry + rh):
            warnings.append(
                f"'{intent.deco_id}' path crosses element '{eid}' "
                f"bbox ({rx:.0f},{ry:.0f})-({rx + rw:.0f},{ry + rh:.0f})"
            )
    return warnings


def _line_crosses_rect(lx1, ly1, lx2, ly2, rx, ry, rx2, ry2) -> bool:
    if max(lx1, lx2) < rx or min(lx1, lx2) > rx2:
        return False
    if max(ly1, ly2) < ry or min(ly1, ly2) > ry2:
        return False
    mx, my = (lx1 + lx2) / 2, (ly1 + ly2) / 2
    return rx <= mx <= rx2 and ry <= my <= ry2


def _resolve_position(x, y, w, h, direction, margin):
    if direction == "right_of":
        return (x + w + margin, y + h / 2)
    if direction == "left_of":
        return (x - margin, y + h / 2)
    if direction == "above":
        return (x + w / 2, y - margin)
    if direction == "below":
        return (x + w / 2, y + h + margin)
    return (x + w / 2, y + h / 2)
