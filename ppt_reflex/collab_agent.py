"""
Collaborative Agent Loop — Claude-in-the-loop
Each slide: build decision pack → show to Claude → Claude returns strategy → execute → re-audit
No external LLM needed.
"""
import json, sys, os
sys.path.insert(0, '.')
from mcp_server import PPTReflexMCPServer
from repair_planner import RepairPlanner, score_issues
from llm_agent import build_decision_pack, execute_strategy

def run_collab_loop(input_path: str, max_slides: int | None = None):
    import shutil

    work_path = input_path.replace(".pptx", "_collab.pptx")
    shutil.copy2(input_path, work_path)

    session = PPTReflexMCPServer()
    r = session.call_tool("open_presentation", {"path": work_path})
    total = min(r["slides"], max_slides or r["slides"])

    print(f"PPT Reflex + Human Collaborator")
    print(f"Slides: {total}")
    print(f"{'='*60}\n")

    for si in range(total):
        session.call_tool("select_slide", {"index": si})

        # Roles
        summary = session.call_tool("element_summary", {})
        for el in summary.get("elements", []):
            if el["role"] == "unknown":
                t = el.get("text_preview", "")
                if "标题" in t: session.call_tool("set_element_role", {"element_id": el["id"], "role": "title"})
                elif "正文" in t or "内容" in t: session.call_tool("set_element_role", {"element_id": el["id"], "role": "body"})
                elif "图片" in t: session.call_tool("set_element_role", {"element_id": el["id"], "role": "figure"})

        # Deterministic phase
        planner = RepairPlanner(session)
        for rnd in range(2):
            r = planner.plan()
            if r["status"] in ("clean",):
                break
            elif r["status"] == "fixed":
                print(f"  [det] {r['candidate']['strategy']} Δ={r['candidate']['delta']}")
            else:
                break

        audit = session.call_tool("audit_slide", {})
        issues = audit.get("issues", [])
        if not issues:
            print(f"  Slide {si+1}: clean")
            continue

        # Build decision pack
        pack = build_decision_pack(session, issues, None, [])
        payload = json.dumps({
            "slide_id": pack.slide_id,
            "page_type": pack.page_type,
            "goal": pack.goal_hint,
            "issue_summary": pack.issue_summary,
            "elements": pack.elements,
            "relationships": pack.relationships,
            "constraints": pack.constraints,
            "allowed_strategies": pack.allowed_strategies,
        }, ensure_ascii=False, indent=2)

        print(f"\n{'─'*60}")
        print(f"Slide {si+1} — DECISION PACK ({len(payload)} chars, ~{len(payload)//4} tokens)")
        print(f"{'─'*60}")
        print(payload)
        print(f"\nRespond with JSON: {{'strategy':..., 'plan':[...]}} or 'skip' to skip this slide.")
        print(f"Or paste 'auto' to use deterministic defaults.")

        response = input("\n> ").strip()

        if response.lower() == 'skip':
            print(f"  Skipped by operator")
            continue
        elif response.lower() == 'auto':
            # Fallback: nudge each overlapping element
            strategy_response = {
                "strategy": "nudge_element",
                "reason": "Auto fallback — attempt to nudge overlapping elements",
                "plan": [{"action": "nudge_element", "targets": [t["id"] for t in pack.elements[:2]]}],
                "requires_human_confirmation": False,
            }
        else:
            try:
                strategy_response = json.loads(response)
            except json.JSONDecodeError:
                print(f"  Invalid JSON, skipping")
                continue

        rev = session.call_tool("get_revision", {}).get("revision", 0)
        result = execute_strategy(session, strategy_response, pack, rev)
        print(f"  Execute: {result.get('status')} ({len(result.get('results',[]))} steps)")

        # Re-audit
        post = session.call_tool("audit_slide", {})
        post_score = score_issues(post.get("issues", []))
        pre_score = score_issues(issues)
        delta = post_score - pre_score
        status = "improved" if delta < 0 else ("no change" if delta == 0 else "regression")
        print(f"  Score: {pre_score} → {post_score} ({delta:+d}) — {status}")

    session.call_tool("save_presentation", {})
    print(f"\n{'='*60}")
    print(f"Done. Saved: {work_path}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", default="cases/broken.pptx")
    ap.add_argument("--max-slides", type=int, default=5)
    args = ap.parse_args()
    run_collab_loop(args.input, args.max_slides)
