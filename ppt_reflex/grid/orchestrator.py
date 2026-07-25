"""
grid/orchestrator.py — AI→引擎→诊断→AI 重排→引擎 回路

引擎只报、不算、不改。allow_shrink 等缩放请求由 AI 在 build_plan 里自己落实
为新的 preferred_width，引擎不替 AI 做任何数学。

僵持检测: 连续 2 轮诊断不减少 → 上报人工。
"""

from __future__ import annotations
from .plan import LayoutPlan, LayoutDiagnostic, FeedbackBundle


def build_feedback(plan: LayoutPlan, rnd: int, prev_count: int,
                   force_relayout: bool) -> FeedbackBundle:
    """引擎→AI 的反馈。force_relayout 意味着不允许微调，必须全新布局。"""
    diags = plan.diagnostics
    blocking = [d for d in diags if d.severity == "error"]
    warnings = [d for d in diags if d.severity == "warning"]

    message = _format_message(rnd, blocking, warnings, force_relayout)
    detail = [
        {"kind": d.kind, "severity": d.severity, "region_id": d.region_id,
         "elem_id": d.elem_id, "demand_pt": d.demand_pt, "usable_pt": d.usable_pt,
         "over_by_pt": d.over_by_pt, "message": d.message, "options": d.options}
        for d in diags
    ]

    return FeedbackBundle(
        round=rnd, blocked=len(blocking) > 0,
        blocking_count=len(blocking), warning_count=len(warnings),
        force_full_relayout=force_relayout,
        message=message, diagnostics=detail,
    )


def _format_message(rnd, blocking, warnings, force):
    lines = [f"== 第 {rnd} 轮引擎反馈 =="]
    if force:
        lines.append("**本轮必须完全重构布局**——微调已失效。")
    lines.append(f"阻塞项: {len(blocking)}，警告项: {len(warnings)}")
    for i, b in enumerate(blocking):
        lines.append(f"[E{i+1}] {b.kind}: {b.message}")
        if b.options:
            lines.append(f"  可选方案: {' | '.join(b.options[:3])}")
    for i, w in enumerate(warnings):
        lines.append(f"[W{i+1}] {w.kind}: {w.message}")
    lines.append("\n请 build_plan(feedback) 返回全新或修改后的 LayoutPlan。")
    return "\n".join(lines)


def layout_loop(build_plan, render, canvas, *, max_rounds: int = 4):
    """
    build_plan(feedback: FeedbackBundle | None) -> LayoutPlan
    render(plan, locked, deco) -> None

    返回值: (plan, locked, deco, diagnostics, stalemated)
      stalemated=True → 引擎解决不了，提示用户
    """
    from .phase1 import execute_phase1, audit_plan
    from .phase2 import execute_phase2

    feedback_bundle = None
    plan = locked = deco = None
    prev_error_count = 999
    stale_count = 0

    for rnd in range(1, max_rounds + 1):
        plan = build_plan(feedback_bundle)
        plan.diagnostics.clear()

        locked = execute_phase1(plan, canvas)
        audit_plan(plan, canvas)
        deco = execute_phase2(plan, canvas)

        blocking = [d for d in plan.diagnostics if d.severity == "error"]
        cur_error_count = len(blocking)
        print(f"[LOOP] r={rnd} diags={len(plan.diagnostics)} "
              f"blocking={cur_error_count}")

        if cur_error_count == 0:
            render(plan, locked, deco)
            return plan, locked, deco, plan.diagnostics, False

        # ── 僵持检测 ──
        if cur_error_count >= prev_error_count:
            stale_count += 1
        else:
            stale_count = 0
        prev_error_count = cur_error_count

        force = stale_count >= 2  # 两轮不改善 → 强制重构

        feedback_bundle = build_feedback(plan, rnd, prev_error_count, force)
        print(feedback_bundle.message)

        # 预览
        render(plan, locked, deco)

        if force:
            print("[LOOP] STALEMATE — 连续两轮引擎诊断未减少，强制要求完全重构布局")
        if rnd == max_rounds:
            print("[LOOP] MAX ROUNDS — 引擎无法自动解决，需人工介入")

    return plan, locked, deco, plan.diagnostics, True  # stalemated
