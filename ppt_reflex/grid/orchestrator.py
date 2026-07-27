"""
grid/orchestrator.py — AI->engine->diagnostics->AI re-plan->engine loop

Engine only reports, computes, never edits. Scaling requests like allow_shrink are
implemented by the AI in build_plan as new preferred_width. Engine does zero math for the AI.

Stalemate detection: 2 consecutive rounds with no diagnostic reduction -> escalate to human.
"""

from __future__ import annotations
from .plan import LayoutPlan, LayoutDiagnostic, FeedbackBundle


def build_feedback(plan: LayoutPlan, rnd: int, prev_count: int,
                   force_relayout: bool) -> FeedbackBundle:
    """Engine->AI feedback. force_relayout means no micro-fixes allowed, must fully re-layout."""
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
    lines = [f"== Round {rnd} engine feedback =="]
    if force:
        lines.append("**This round requires full re-layout** — micro-fixes exhausted.")
    lines.append(f"Blocking: {len(blocking)}, warnings: {len(warnings)}")
    for i, b in enumerate(blocking):
        lines.append(f"[E{i+1}] {b.kind}: {b.message}")
        if b.options:
            lines.append(f"  Options: {' | '.join(b.options[:3])}")
    for i, w in enumerate(warnings):
        lines.append(f"[W{i+1}] {w.kind}: {w.message}")
    lines.append("\nCall build_plan(feedback) with a new or modified LayoutPlan.")
    return "\n".join(lines)


def layout_loop(build_plan, render, canvas, *, max_rounds: int = 4):
    """
    build_plan(feedback: FeedbackBundle | None) -> LayoutPlan
    render(plan, locked, deco) -> None

    Returns: (plan, locked, deco, diagnostics, stalemated)
      stalemated=True -> engine cannot resolve, prompt user
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

        # ── Stalemate detection ──
        if cur_error_count >= prev_error_count:
            stale_count += 1
        else:
            stale_count = 0
        prev_error_count = cur_error_count

        force = stale_count >= 2  # two rounds no improvement -> force full re-layout

        feedback_bundle = build_feedback(plan, rnd, prev_error_count, force)
        print(feedback_bundle.message)

        # Preview
        render(plan, locked, deco)

        if force:
            print("[LOOP] STALEMATE — two consecutive rounds with no diagnostic reduction, forcing full re-layout")
        if rnd == max_rounds:
            print("[LOOP] MAX ROUNDS — engine cannot resolve automatically, human intervention needed")

    return plan, locked, deco, plan.diagnostics, True  # stalemated
