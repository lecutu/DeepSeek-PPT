"""
PPT Reflex Engine — Agent Repair Loop

补完 Pipeline 最后一块：Agent 读取 audit → 决策 → 修复 → 重新审计 → 循环。

Day 1 验证了"检测层可信"。
这里验证"纯文本模型能否根据结构化 space summary 做修复"。

运行方式：
  python agent_loop.py                                # 交互式：每页暂停，等人工输入策略
  python agent_loop.py --auto                         # 全自动：用简单策略自动修复
  python agent_loop.py --auto --max-rounds 3          # 最多3轮

策略表（automated）：
  OUT_OF_BOUNDS        → snap_to_safe_area（引擎已做，这里做大的越界修正）
  UNEXPECTED_OVERLAP   → 选模板重排 (apply_layout) 或 微调
  ALIGNMENT_DRIFT      → 对齐到模态线
  FONT_BELOW_THRESHOLD → bump到最小值
  SPACING_DEVIATION    → 均匀化间距
  DENSITY_HIGH         → 标记warning（需要人/AI决定删什么）
"""

import sys
import json
import time
from pathlib import Path
from collections import defaultdict

# Import MCP Server session (direct, not via pipe)
from mcp_server import PPTReflexMCPServer

# ═══════════════════════════════════════════════════════════
# AUTO-FIX STRATEGIES
# ═══════════════════════════════════════════════════════════

AUTO_STRATEGIES = {
    "OUT_OF_BOUNDS": "snap_to_safe",
    "UNEXPECTED_OVERLAP": "apply_template_or_nudge",
    "ALIGNMENT_DRIFT": "align_to_modal",
    "FONT_BELOW_THRESHOLD": "bump_font",
    "SPACING_DEVIATION": "equalize_spacing",
    "DENSITY_HIGH": "warn_only",       # 语义决策，不自动删内容
    "ASPECT_DISTORTED": "warn_only",
    "READING_ORDER_VIOLATION": "warn_only",
    "TEXT_OVERFLOW_SUSPECTED": "warn_only",
}


def auto_fix(session: PPTReflexMCPServer, issue: dict, slide_elements: list,
             fix_history: dict | None = None) -> dict:
    """Apply deterministic fix with strategy rotation on retry."""
    if fix_history is None:
        fix_history = {}

    code = issue["code"]
    targets = iss.get("targets", [])
    key = f"{code}:{':'.join(sorted(targets))}"
    attempt = fix_history.get(key, 0)
    fix_history[key] = attempt + 1

    if code == "OUT_OF_BOUNDS":
        # Get the element, snap it inside safe area
        for eid in targets:
            ctx = session.call_tool("local_context", {"element_ids": [eid]})
            for t in ctx.get("targets", []):
                bbox = t.get("bbox_pt", [0, 0, 100, 100])
                x, y, w, h = bbox
                canvas_w = ctx.get("canvas", {}).get("width_pt", 960)
                canvas_h = ctx.get("canvas", {}).get("height_pt", 540)
                margin = 36
                new_x = max(margin, min(x, canvas_w - margin - w))
                new_y = max(margin, min(y, canvas_h - margin - h))
                if new_x != x or new_y != y:
                    return session.call_tool("move_element", {
                        "element_id": eid, "x": new_x, "y": new_y, "w": w, "h": h,
                    })

    elif code == "UNEXPECTED_OVERLAP":
        if len(targets) == 2:
            roles = iss.get("roles", [])
            a_id, b_id = targets

            # Strategy table — try different things based on retry count
            strategy_idx = attempt % 4

            # Get both elements' positions
            ctx = session.call_tool("local_context", {"element_ids": targets})
            target_bboxes = {}
            for t in ctx.get("targets", []):
                target_bboxes[t["id"]] = t.get("bbox_pt", [0, 0, 100, 100])

            if strategy_idx == 0:
                # Try: apply body→body_right layout
                if "body" in roles and "figure" in roles:
                    body_id = targets[roles.index("body")] if "body" in roles else targets[0]
                    fig_id = targets[roles.index("figure")] if "figure" in roles else targets[1]
                    return session.call_tool("apply_layout", {
                        "template": "text_left_figure_right",
                        "role_mapping": {"body": body_id, "figure": fig_id},
                    })
                # body+body → assign roles + apply template
                elif any(r in roles for r in ("body", "unknown", "footer")):
                    return session.call_tool("apply_layout", {
                        "template": "text_left_figure_right",
                        "role_mapping": {"body": targets[0], "figure": targets[1]},
                    })

            elif strategy_idx == 1:
                # Move target[1] right by overlap amount
                bbox = target_bboxes.get(targets[1], [0, 0, 100, 100])
                overlap_pct = iss.get("overlap_pct", 30)
                shift = max(80, int(bbox[2] * overlap_pct / 100))
                return session.call_tool("move_element", {
                    "element_id": targets[1],
                    "x": bbox[0] + shift, "y": bbox[1],
                    "w": min(bbox[2], 960 - 36 - bbox[0] - shift),
                    "h": bbox[3],
                })

            elif strategy_idx == 2:
                # Move target[1] down
                bbox = target_bboxes.get(targets[1], [0, 0, 100, 100])
                overlap_pct = iss.get("overlap_pct", 30)
                shift = max(60, int(bbox[3] * overlap_pct / 100))
                return session.call_tool("move_element", {
                    "element_id": targets[1],
                    "x": bbox[0], "y": bbox[1] + shift,
                    "w": bbox[2],
                    "h": min(bbox[3], 540 - 36 - bbox[1] - shift),
                })

            else:
                # Last resort: move target[1] to bottom of canvas
                bbox = target_bboxes.get(targets[1], [0, 0, 100, 100])
                return session.call_tool("move_element", {
                    "element_id": targets[1],
                    "x": 36, "y": 540 - 36 - bbox[3],
                    "w": bbox[2], "h": bbox[3],
                })

    elif code == "ALIGNMENT_DRIFT":
        modal = iss.get("modal_left_pt")
        if modal and targets:
            ctx = session.call_tool("local_context", {"element_ids": targets})
            for t in ctx.get("targets", []):
                bbox = t.get("bbox_pt", [0, 0, 100, 100])
                return session.call_tool("move_element", {
                    "element_id": targets[0],
                    "x": modal,
                    "y": bbox[1],
                    "w": bbox[2],
                    "h": bbox[3],
                })

    elif code == "FONT_BELOW_THRESHOLD":
        # Can't change font size via MCP yet — mark for Agent
        return {"status": "skipped", "reason": "Font changes require text manipulation, not yet implemented"}

    return {"status": "skipped", "reason": f"No auto-strategy for {code}"}


# ═══════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════

def run_loop(input_path: str, auto: bool = False, max_rounds: int = 3,
             interactive: bool = False):
    """
    Agent repair loop:
      1. Open presentation
      2. For each slide:
         a. Audit → get issues
         b. Decide fix strategy (auto or human)
         c. Apply fix
         d. Re-audit
         e. Repeat until clean or max rounds
      3. Save
    """

    if not Path(input_path).exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    # Copy input to temp working file
    import shutil
    work_path = input_path.replace(".pptx", "_work.pptx")
    shutil.copy2(input_path, work_path)

    session = PPTReflexMCPServer()

    # Open
    r = session.call_tool("open_presentation", {"path": work_path})
    total_slides = r.get("slides", 0)
    templates = session.call_tool("list_templates", {})
    template_names = [t["name"] for t in templates.get("templates", [])]

    print(f"\n{'='*70}")
    print(f"PPT Reflex Agent Loop")
    print(f"Input: {input_path}")
    print(f"Slides: {total_slides}")
    print(f"Mode: {'auto' if auto else 'interactive'}")
    print(f"Max rounds: {max_rounds}")
    print(f"Templates: {', '.join(template_names)}")
    print(f"{'='*70}")

    stats = {
        "total_issues_found": 0,
        "total_issues_fixed": 0,
        "slides_fixed": 0,
        "rounds": [],
    }

    for slide_idx in range(total_slides):
        session.call_tool("select_slide", {"index": slide_idx})

        # Assign roles heuristically (Day 1 validated)
        summary = session.call_tool("element_summary", {})
        elements = summary.get("elements", [])
        for el in elements:
            if el["role"] == "unknown":
                # Try to infer
                eid = el["id"]
                text = el.get("text_preview", "")
                if "标题" in text or "title" in text.lower():
                    session.call_tool("set_element_role", {"element_id": eid, "role": "title"})
                elif "正文" in text or "body" in text.lower() or "内容" in text:
                    session.call_tool("set_element_role", {"element_id": eid, "role": "body"})
                elif "图片" in text or "figure" in text.lower():
                    session.call_tool("set_element_role", {"element_id": eid, "role": "figure"})

        print(f"\n{'─'*60}")
        print(f"Slide {slide_idx + 1}/{total_slides}")
        sys.stdout.flush()

        for round_num in range(1, max_rounds + 1):
            # Track fix history per round to rotate strategies
            fix_history: dict = {}

            # Audit
            rev_r = session.call_tool("get_revision", {})
            rev = rev_r.get("revision", 0)
            audit = session.call_tool("audit_slide", {})

            issues = audit.get("issues", [])
            status = audit["status"]
            auto_adj = audit.get("auto_adjusted", [])

            print(f"  Round {round_num}: rev={rev} status={status} issues={len(issues)} auto_fixes={len(auto_adj)}")

            if auto_adj:
                for adj in auto_adj:
                    print(f"    [auto] {adj['element_id']}: {adj['reason']}")

            if not issues:
                print(f"  ✓ Slide clean after {round_num} round(s)")
                stats["slides_fixed"] += 1
                break

            for iss in issues:
                code = iss["code"]
                targets = iss.get("targets", [])
                severity = iss.get("severity", "?")
                stats["total_issues_found"] += 1

                strategy = AUTO_STRATEGIES.get(code, "warn_only")
                print(f"    [{severity}] {code} {targets} → strategy: {strategy}")

                if strategy == "warn_only":
                    print(f"           ⚠ needs human/AI decision (skipped)")
                    continue

                if auto:
                    # Apply automatic fix
                    result = auto_fix(session, iss, elements, fix_history)
                    print(f"           → {result.get('status', '?')} {result.get('applied_template', '')}")
                    if result.get("status") in ("ok", "needs_decision"):
                        stats["total_issues_fixed"] += 1
                elif interactive:
                    # Show issue + context, ask human
                    ctx = session.call_tool("local_context", {"element_ids": targets})
                    targets_info = ctx.get("targets", [])
                    for t in targets_info:
                        print(f"           {t['id']}: role={t['role']} grid={t.get('grid','?')} "
                              f"bbox={t.get('bbox_pt','?')} locked={t.get('locked',False)}")

                    choice = input(f"           Fix? [y=auto / m=manual / s=skip / q=quit]: ").strip().lower()
                    if choice == 'y':
                        result = auto_fix(session, iss, elements, fix_history)
                        print(f"           → {result.get('status', '?')}")
                        if result.get("status") in ("ok", "needs_decision"):
                            stats["total_issues_fixed"] += 1
                    elif choice == 'm':
                        # Manual: prompt for x,y,w,h
                        try:
                            eid = targets[0]
                            x = float(input(f"             new x (pt): "))
                            y = float(input(f"             new y (pt): "))
                            w = float(input(f"             new w (pt): "))
                            h = float(input(f"             new h (pt): "))
                            session.call_tool("move_element", {
                                "element_id": eid, "x": x, "y": y, "w": w, "h": h,
                            })
                            stats["total_issues_fixed"] += 1
                        except (ValueError, EOFError):
                            print("             skipped")
                    elif choice == 'q':
                        print("  Quitting.")
                        session.call_tool("save_presentation", {})
                        return stats
                    else:
                        print("             skipped")

        else:
            # Max rounds reached, issues remain
            print(f"  ⚠ Max rounds reached. Remaining issues:")
            final = session.call_tool("audit_slide", {})
            for iss in final.get("issues", []):
                print(f"    {iss['code']} {iss.get('targets', [])}")

        stats["rounds"].append(round_num)

    # Save
    session.call_tool("save_presentation", {})
    print(f"\n{'='*70}")
    print(f"DONE")
    print(f"  Slides checked: {total_slides}")
    print(f"  Slides fixed:   {stats['slides_fixed']}")
    print(f"  Issues found:   {stats['total_issues_found']}")
    print(f"  Issues fixed:   {stats['total_issues_fixed']}")
    if stats['total_issues_found'] > 0:
        print(f"  Fix rate:       {stats['total_issues_fixed']/stats['total_issues_found']*100:.1f}%")
    print(f"  Output:         {work_path}")
    print(f"{'='*70}")

    return stats


# ═══════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="PPT Reflex Agent Repair Loop")
    ap.add_argument("input", nargs="?", default="cases/broken.pptx",
                    help="Path to broken .pptx file")
    ap.add_argument("--auto", action="store_true",
                    help="Apply automatic fix strategies without prompting")
    ap.add_argument("--interactive", action="store_true",
                    help="Interactive mode: pause for human input per issue")
    ap.add_argument("--max-rounds", type=int, default=3,
                    help="Maximum repair rounds per slide (default: 3)")
    args = ap.parse_args()

    run_loop(args.input, auto=args.auto, max_rounds=args.max_rounds,
             interactive=args.interactive or not args.auto)
