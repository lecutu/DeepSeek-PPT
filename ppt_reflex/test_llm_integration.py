"""
LLM Agent End-to-End Integration Test

Since no API key is available, this script provides hand-crafted
"LLM responses" for each slide and runs the full execute→re-audit loop.

This validates:
  - DecisionPack builds correctly
  - execute_strategy translates LLM output to MCP calls
  - Post-strategy audit detects improvement/regression
  - Revision tracking works across deterministic + LLM phases
  - score_issues + score_delta metrics are consistent
"""

import json, sys
sys.path.insert(0, '.')
from mcp_server import PPTReflexMCPServer
from repair_planner import RepairPlanner, score_issues
from llm_agent import (
    build_decision_pack, execute_strategy, call_llm,
    check_layout_infeasible,
)

# ═══════════════════════════════════════════════════════════
# Hand-crafted LLM responses (what the model WOULD return)
# ═══════════════════════════════════════════════════════════

# Slide 1: Two elements OOB — move them back inside
SLIDE_1_RESPONSE = {
    "strategy": "resize_element",
    "reason": "Both elements overflow canvas. Move shape-00 left into safe area and shift shape-01 up.",
    "plan": [
        {"action": "nudge_element", "targets": ["shape-00"]},  # snap left
        {"action": "nudge_element", "targets": ["shape-01"]},  # snap up
    ],
    "requires_human_confirmation": False,
}

# Slide 2: Title-body overlap — already fixed by deterministic nudge,
# remaining FONT_BELOW_THRESHOLD
SLIDE_2_RESPONSE = {
    "strategy": "increase_font",
    "reason": "Body text at 11pt is below 14pt minimum. Enlarge text box or increase font.",
    "plan": [
        {"action": "enlarge_textbox", "targets": ["shape-01"]},  # not yet implemented
    ],
    "requires_human_confirmation": False,
}

# Slide 3: Two bodies overlapping — move shape-01 to right edge
SLIDE_3_RESPONSE = {
    "strategy": "nudge_element",
    "reason": "Two body text boxes overlap. Move the second one to the right side of the canvas.",
    "plan": [
        {"action": "nudge_element", "targets": ["shape-01"]},
    ],
    "requires_human_confirmation": False,
}

# Slide 12: Dense page — LAYOUT_INFEASIBLE, split or remove
SLIDE_12_RESPONSE = {
    "strategy": "split_slide",
    "reason": "12 elements at 100% density cannot fit. Split into two 6-element pages.",
    "plan": [
        {"action": "keep_on_current_slide", "targets": [f"shape-{i:02d}" for i in range(6)]},
        {"action": "move_to_new_slide", "targets": [f"shape-{i:02d}" for i in range(6, 12)]},
    ],
    "requires_human_confirmation": True,  # Destructive — marked for human
}


MOCK_RESPONSES = {
    0: SLIDE_1_RESPONSE,
    1: SLIDE_2_RESPONSE,
    2: SLIDE_3_RESPONSE,
    11: SLIDE_12_RESPONSE,
}


# ═══════════════════════════════════════════════════════════
# TEST RUNNER
# ═══════════════════════════════════════════════════════════

def run_integration_test(input_path: str, max_slides: int = 15):
    import shutil
    from pathlib import Path

    work_path = input_path.replace(".pptx", "_inttest.pptx")
    shutil.copy2(input_path, work_path)

    session = PPTReflexMCPServer()
    r = session.call_tool("open_presentation", {"path": work_path})
    total_slides = min(r["slides"], max_slides)

    print(f"PPT Reflex + LLM Integration Test")
    print(f"Slides: {total_slides} | Using mock LLM responses")
    print(f"{'='*60}")

    results = []

    for si in range(total_slides):
        session.call_tool("select_slide", {"index": si})

        # Role inference
        summary = session.call_tool("element_summary", {})
        for el in summary.get("elements", []):
            if el["role"] == "unknown":
                text = el.get("text_preview", "")
                if "标题" in text:
                    session.call_tool("set_element_role", {"element_id": el["id"], "role": "title"})
                elif "正文" in text or "内容" in text:
                    session.call_tool("set_element_role", {"element_id": el["id"], "role": "body"})
                elif "图片" in text:
                    session.call_tool("set_element_role", {"element_id": el["id"], "role": "figure"})

        # Initial
        initial = session.call_tool("audit_slide", {})
        initial_score = score_issues(initial.get("issues", []))

        # Deterministic phase
        planner = RepairPlanner(session)
        det_fixed = 0
        for rnd in range(2):
            r = planner.plan()
            if r["status"] == "clean":
                break
            elif r["status"] == "fixed":
                det_fixed += 1
            else:
                break

        det_audit = session.call_tool("audit_slide", {})
        det_issues = det_audit.get("issues", [])
        det_score = score_issues(det_issues)

        # LLM phase
        if det_issues and si in MOCK_RESPONSES:
            mock = MOCK_RESPONSES[si]
            pack = build_decision_pack(session, det_issues, None, [])
            rev = session.call_tool("get_revision", {}).get("revision", 0)

            print(f"\n  Slide {si+1}: deterministic Δ={det_score-initial_score:+d}, "
                  f"remaining issues={len(det_issues)}")
            print(f"  LLM strategy: {mock['strategy']}")
            print(f"  Plan: {[s['action'] + ':' + ','.join(s.get('targets',[])) for s in mock['plan']]}")

            exec_result = execute_strategy(session, mock, pack, rev)
            print(f"  Execute: {exec_result.get('status')} "
                  f"({len(exec_result.get('results',[]))} steps)")

            for step in exec_result.get("results", []):
                print(f"    {step['step']}: {step.get('result', '?')}")

            # Re-audit
            post_llm = session.call_tool("audit_slide", {})
            post_score = score_issues(post_llm.get("issues", []))
            delta = post_score - det_score
            status = "✓ improved" if delta < 0 else ("— no change" if delta == 0 else "✗ regression")

            results.append({
                "slide": si + 1,
                "initial_score": initial_score,
                "det_score": det_score,
                "llm_score": post_score,
                "delta": delta,
                "strategy": mock["strategy"],
                "status": status,
            })

            print(f"  Post-LLM score: {post_score} ({delta:+d}) {status}")

        elif det_issues:
            print(f"\n  Slide {si+1}: {len(det_issues)} issues remain (no mock response defined)")

        else:
            print(f"\n  Slide {si+1}: ✓ clean (det phase fixed all)")

    # Summary
    print(f"\n{'='*60}")
    print(f"INTEGRATION TEST RESULTS")
    print(f"  Slides with LLM:  {len(results)}")
    improved = sum(1 for r in results if r["delta"] < 0)
    unchanged = sum(1 for r in results if r["delta"] == 0)
    regressed = sum(1 for r in results if r["delta"] > 0)
    total_delta = sum(r["delta"] for r in results)

    print(f"  Improved:         {improved}")
    print(f"  Unchanged:        {unchanged}")
    print(f"  Regressed:        {regressed}")
    print(f"  Total score Δ:    {total_delta:+d}")
    for r in results:
        print(f"    Slide {r['slide']}: {r['initial_score']} → det {r['det_score']} → LLM {r['llm_score']} "
              f"({r['delta']:+d}) [{r['strategy']}] {r['status']}")

    session.call_tool("save_presentation", {})
    print(f"  Output:           {work_path}")
    print(f"{'='*60}")

    return results


# ═══════════════════════════════════════════════════════════
# TOKEN BUDGET ANALYSIS
# ═══════════════════════════════════════════════════════════

def analyze_token_budget(input_path: str):
    """Analyze how many tokens each decision pack would consume."""
    import shutil
    work_path = input_path.replace(".pptx", "_token.pptx")
    shutil.copy2(input_path, work_path)

    session = PPTReflexMCPServer()
    session.call_tool("open_presentation", {"path": work_path})

    print(f"\n{'='*60}")
    print(f"TOKEN BUDGET ANALYSIS")
    print(f"{'='*60}")

    total_tokens = 0
    for si in range(15):
        session.call_tool("select_slide", {"index": si})
        summary = session.call_tool("element_summary", {})
        for el in summary.get("elements", []):
            if el["role"] == "unknown":
                session.call_tool("set_element_role", {"element_id": el["id"], "role": "body"})

        audit = session.call_tool("audit_slide", {})
        issues = audit.get("issues", [])
        if not issues:
            continue

        pack = build_decision_pack(session, issues, None, [])
        # Count actual JSON size
        payload = json.dumps({
            "issue_summary": pack.issue_summary,
            "elements": pack.elements,
            "relationships": pack.relationships,
            "constraints": pack.constraints,
            "allowed_strategies": pack.allowed_strategies,
        }, ensure_ascii=False)
        char_count = len(payload)
        # Rough token estimate: 1 token ≈ 4 chars for CJK, 3.5 for English
        token_est = char_count // 4
        total_tokens += token_est
        print(f"  Slide {si+1:2d}: {len(issues):2d} issues, {len(pack.elements):2d} elements, "
              f"{char_count:4d} chars, ~{token_est:3d} input tokens")

    print(f"  {'─'*50}")
    print(f"  Total: ~{total_tokens} input tokens for all slides with issues")
    print(f"  Average: ~{total_tokens // max(1, sum(1 for si in range(15) if session.call_tool('audit_slide', {}) != None))} tokens/slide")
    print(f"{'='*60}")


# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", default="cases/broken.pptx")
    ap.add_argument("--token-analysis", action="store_true")
    args = ap.parse_args()

    if args.token_analysis:
        analyze_token_budget(args.input)
    else:
        run_integration_test(args.input)
