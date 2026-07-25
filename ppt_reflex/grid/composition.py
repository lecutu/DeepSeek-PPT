"""
grid/composition.py — Phase 2.5: 全局构图检查

输入: LayoutPlan (Phase 1+2 已完成)
输出: list[dict] — 美学/平衡/留白问题列表
"""

from __future__ import annotations
from .plan import LayoutPlan


def global_composition_check(plan: LayoutPlan) -> list[dict]:
    """全局构图检查——留白率、视觉重心、密度、对齐。

    Returns:
        list of dicts with keys: level ("info"|"warn"), category, message
    """
    issues: list[dict] = []

    # 1. 留白率
    _check_whitespace(plan, issues)

    # 2. 视觉重心
    _check_balance(plan, issues)

    # 3. 区域密度
    _check_density(plan, issues)

    # 4. 对齐一致性
    _check_alignment(plan, issues)

    return issues


# ═══════════════════════════════════════════════════════════════
# 检查函数
# ═══════════════════════════════════════════════════════════════

def _check_whitespace(plan: LayoutPlan, issues: list[dict]) -> None:
    """留白率：元素总面积 / 页面面积。"""
    total_area = plan.page_w * plan.page_h
    if total_area <= 0:
        return

    elem_area = sum(e.w * e.h for e in plan.elements)
    deco_area = sum(
        abs(d.x2 - d.x1) * abs(d.y2 - d.y1) * 0.1  # 装饰面积 ≈ 路径的 10%
        for d in plan.decorations
        if d.deco_type == "arrow" and d.x2 != 0
    )
    occupied = elem_area + deco_area
    ratio = occupied / total_area

    if ratio < 0.1:
        issues.append({
            "level": "warn", "category": "whitespace",
            "message": f"Content occupies only {ratio:.0%} of page — too sparse.",
        })
    elif ratio > 0.80:
        issues.append({
            "level": "warn", "category": "whitespace",
            "message": f"Content occupies {ratio:.0%} of page — too dense, reduce element count or size.",
        })
    elif ratio > 0.65:
        issues.append({
            "level": "info", "category": "whitespace",
            "message": f"Content density {ratio:.0%} — acceptable but approaching limit.",
        })


def _check_balance(plan: LayoutPlan, issues: list[dict]) -> None:
    """视觉重心：元素的面积加权中心应在页面中心 1/3 区域内。"""
    elements = plan.elements
    if not elements:
        return

    total_area = sum(e.w * e.h for e in elements)
    if total_area <= 0:
        return

    cx = sum((e.x + e.w / 2) * e.w * e.h for e in elements) / total_area
    cy = sum((e.y + e.h / 2) * e.w * e.h for e in elements) / total_area

    page_cx = plan.page_w / 2
    page_cy = plan.page_h / 2
    third_w = plan.page_w / 3
    third_h = plan.page_h / 3

    dx = abs(cx - page_cx)
    dy = abs(cy - page_cy)

    if dx > third_w or dy > third_h:
        direction = ""
        if dx > third_w:
            direction += "偏右" if cx > page_cx else "偏左"
        if dy > third_h:
            direction += "偏下" if cy > page_cy else "偏上"
        issues.append({
            "level": "info", "category": "balance",
            "message": f"Visual center ({cx:.0f},{cy:.0f}) deviates from page center ({page_cx:.0f},{page_cy:.0f}) — {direction}.",
        })


def _check_density(plan: LayoutPlan, issues: list[dict]) -> None:
    """区域密度：每个 region 内元素面积 / region 面积。"""
    for region in plan.regions:
        region_area = region.w * region.h
        if region_area <= 0:
            continue

        elem_area = sum(
            e.w * e.h for e in plan.elements
            if e.elem_id in region.elements
        )
        ratio = elem_area / region_area

        if ratio > 0.90:
            issues.append({
                "level": "warn", "category": "density",
                "message": f"Region '{region.region_id}' ({region.purpose}) at {ratio:.0%} fill — "
                           f"no room for decoration or breathing space.",
            })


def _check_alignment(plan: LayoutPlan, issues: list[dict]) -> None:
    """对齐一致性：同列左边缘应在 10pt 内对齐。"""
    # Group by region
    for region in plan.regions:
        region_elems = [e for e in plan.elements if e.elem_id in region.elements]
        if len(region_elems) < 2:
            continue

        left_edges = sorted(e.x for e in region_elems)
        spread = left_edges[-1] - left_edges[0]
        if spread > 10:
            issues.append({
                "level": "info", "category": "alignment",
                "message": f"Region '{region.region_id}': left edges span {spread:.0f}pt "
                           f"(from {left_edges[0]:.0f} to {left_edges[-1]:.0f}) — "
                           f"consider uniform left alignment.",
            })
