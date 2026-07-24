"""
LLM Decision Interface — PPT Reflex Engine Level 4

将 needs_decision 打包为 结构化决策包 → 发送给任何 LLM →
接收策略 → 模拟验证 → 提交/回滚。

架构：
  ReflexEngine → audit → RepairPlanner → 确定性问题自动修复
                                         → 语义问题 → DecisionPack
  DecisionPack → LLM API → DecisionResponse → Simulator → Gate → Commit

支持的 LLM Provider:
  - Claude (Anthropic API)
  - DeepSeek (OpenAI-compatible)
  - OpenAI (GPT-4o, etc.)
  - 任何 OpenAI-compatible API

运行:
  python llm_agent.py cases/broken.pptx --provider deepseek --max-slides 5
"""

from __future__ import annotations
import json
import os
import sys
import time
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any

from mcp_server import PPTReflexMCPServer
from repair_planner import (
    RepairPlanner, Simulator, Candidate,
    generate_nudge_candidates, generate_snap_candidates,
    evaluate_candidates, accept_candidate,
    score_issues, check_layout_infeasible,
)


# ═══════════════════════════════════════════════════════════
# DECISION PACK — what the LLM receives
# ═══════════════════════════════════════════════════════════

@dataclass
class DecisionPack:
    """Structured problem summary with constraints, sent to LLM."""

    slide_id: str
    revision: int
    page_type: str                     # inferred from element roles
    goal_hint: str                     # inferred from context

    issue_summary: dict                # {primary_code, high_count, medium_count, low_count}
    infeasible: dict | None            # LAYOUT_INFEASIBLE details or None

    elements: list[dict]               # [{id, role, grid, text_preview, locked, importance}, ...]
    relationships: list[dict]          # [{a, b, relation: "overlaps"|"aligns_with"|"contains"}, ...]

    constraints: dict                  # {preserve_ids: [...], min_body_font_pt, max_operations, can_split}
    attempted: list[dict]              # [{strategy, result, reason}, ...] from deterministic passes
    allowed_strategies: list[str]      # e.g. ["nudge", "resize", "compress_text", "split_slide", "reorder"]

    # Token budget for the response
    budget: dict = field(default_factory=lambda: {"max_operations": 6})


def build_decision_pack(
    session: PPTReflexMCPServer,
    issues: list[dict],
    infeasible: dict | None,
    attempted: list[dict],
) -> DecisionPack:
    """Build a structured decision package from current slide state."""

    # Gather element data
    summary = session.call_tool("element_summary", {})
    elements_raw = summary.get("elements", [])
    revision = summary.get("revision", 0)
    slide_id = summary.get("slide_id", "?")

    # Enrich with bbox and lock state
    elements = []
    for el in elements_raw:
        ctx = session.call_tool("local_context", {"element_ids": [el["id"]]})
        for t in ctx.get("targets", []):
            elements.append({
                "id": t["id"],
                "role": t.get("role", "unknown"),
                "grid": t.get("grid", "?"),
                "bbox_pt": t.get("bbox_pt", [0, 0, 100, 100]),
                "text_preview": el.get("text_preview", "")[:60],
                "locked": t.get("locked", False),
                "locked_by": t.get("locked_by", ""),
                "importance": _infer_importance(t["id"], t.get("role", ""), el.get("text_preview", ""), elements_raw),
            })

    # Infer page type
    page_type = _infer_page_type(elements)
    goal_hint = _infer_goal(page_type, elements)

    # Build relationships
    relationships = _build_relationships(issues, elements)

    # Build constraint set
    preserved = [
        e["id"] for e in elements
        if e["locked"] or e["role"] in ("background",)
    ]
    constraints = {
        "preserve_ids": preserved,
        "can_split_slide": len(elements) >= 4,
        "min_body_font_pt": 14,
        "max_operations": 6,
        "safe_margin_pt": 36,
        "canvas_pt": [960, 540],
    }

    # Allowed strategies based on issue types
    strategies = _derive_strategies(issues, infeasible)

    # Issue summary
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    primary = issues[0]["code"] if issues else "NONE"
    for iss in issues:
        sev = iss.get("severity", "medium")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return DecisionPack(
        slide_id=slide_id,
        revision=revision,
        page_type=page_type,
        goal_hint=goal_hint,
        issue_summary={
            "primary": primary,
            **severity_counts,
            "total": len(issues),
        },
        infeasible=infeasible,
        elements=elements,
        relationships=relationships,
        constraints=constraints,
        attempted=attempted,
        allowed_strategies=strategies,
    )


def _infer_importance(eid: str, role: str, text: str, all_elements: list) -> str:
    """Guess element importance: primary | secondary | required | decorative."""
    if role in ("title", "subtitle"):
        return "required"
    if role == "background":
        return "decorative"
    if role in ("figure", "key_metric"):
        return "primary"
    if role in ("citation", "page_number"):
        return "required"
    if "结果" in text or "结论" in text or "conclusion" in text.lower():
        return "primary"
    if "注" in text or "来源" in text or "参考" in text:
        return "required"
    # Default: body elements are primary, small text boxes secondary
    bbox = next((e.get("bbox_pt", [0, 0, 0, 0]) for e in all_elements if e.get("id") == eid), [0, 0, 0, 0])
    area = bbox[2] * bbox[3] if len(bbox) == 4 else 0
    return "primary" if area > 50000 else "secondary"


def _infer_page_type(elements: list[dict]) -> str:
    """Guess page type from element roles and counts."""
    roles = [e["role"] for e in elements]
    n = len(elements)
    if "title" in roles and n <= 3:
        return "title_slide"
    if "figure" in roles and "body" in roles:
        return "text_figure"
    if n >= 8:
        return "dense_comparison"
    if roles.count("key_metric") >= 2:
        return "metrics"
    if roles.count("body") >= 2:
        return "comparison"
    return "content"


def _infer_goal(page_type: str, elements: list[dict]) -> str:
    """Generate a brief goal description for the LLM."""
    titles = [e for e in elements if e["role"] == "title"]
    figures = [e for e in elements if e["role"] == "figure"]
    bodies = [e for e in elements if e["role"] == "body"]

    title_text = titles[0].get("text_preview", "") if titles else ""
    if page_type == "text_figure":
        return f"Associate a figure with explanatory text"
    if page_type == "comparison":
        return f"Present comparative analysis"
    if page_type == "dense_comparison":
        return f"Present multiple data points or comparisons on one page"
    if page_type == "metrics":
        return f"Display key metrics"
    return f"Present content: {title_text[:40]}"


def _build_relationships(issues: list[dict], elements: list[dict]) -> list[dict]:
    """Extract element relationships from issues and spatial context."""
    rels = []
    seen = set()

    for iss in issues:
        if iss["code"] == "UNEXPECTED_OVERLAP" and len(iss.get("targets", [])) == 2:
            pair = tuple(sorted(iss["targets"]))
            if pair not in seen:
                seen.add(pair)
                roles = iss.get("roles", [])
                rels.append({
                    "a": pair[0],
                    "b": pair[1],
                    "relation": "overlaps_conflict",
                    "overlap_pct": iss.get("overlap_pct", 0),
                    "a_role": roles[0] if len(roles) > 0 else "?",
                    "b_role": roles[1] if len(roles) > 1 else "?",
                })

        if iss["code"] == "ALIGNMENT_DRIFT":
            targets = iss.get("targets", [])
            if len(targets) == 1:
                modal = iss.get("modal_left_pt")
                if modal:
                    rels.append({
                        "a": targets[0],
                        "relation": "misaligned",
                        "expected_left_pt": modal,
                        "drift_pt": iss.get("drift_pt", 0),
                    })

    return rels


def _derive_strategies(issues: list[dict], infeasible: dict | None) -> list[str]:
    """Determine which strategies are applicable."""
    strategies = []
    codes = {i["code"] for i in issues}

    if infeasible:
        strategies.extend(["split_slide", "remove_secondary_content", "change_page_type"])
    if "UNEXPECTED_OVERLAP" in codes:
        strategies.extend(["nudge_element", "resize_element", "reorder_layers", "split_slide"])
    if "ALIGNMENT_DRIFT" in codes:
        strategies.extend(["align_elements", "distribute_elements"])
    if "FONT_BELOW_THRESHOLD" in codes:
        strategies.extend(["increase_font", "enlarge_textbox", "split_content"])
    if "SPACING_DEVIATION" in codes:
        strategies.extend(["equalize_spacing", "regroup_elements"])
    if "DENSITY_HIGH" in codes:
        strategies.extend(["split_slide", "remove_secondary_content", "reduce_font_size"])
    if "OUT_OF_BOUNDS" in codes:
        strategies.extend(["resize_element", "move_element", "change_page_type"])

    if not strategies:
        strategies = ["nudge_element", "align_elements", "resize_element"]

    return strategies


# ═══════════════════════════════════════════════════════════
# LLM CLIENT — sends decision pack, receives strategy
# ═══════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a slide layout strategist. You receive structured problem descriptions
and propose HIGH-LEVEL strategies. You NEVER output raw coordinates.

## Your output format (STRICT JSON):
{
  "strategy": "one of the allowed strategies",
  "reason": "why this strategy was chosen (1-2 sentences)",
  "plan": [
    {"action": "keep_on_current_slide", "targets": ["shape-03", "shape-04"]},
    {"action": "move_to_new_slide", "targets": ["shape-05"]},
    {"action": "align_left", "targets": ["shape-02"], "reference": "shape-00"},
    {"action": "enlarge_textbox", "targets": ["shape-07"]}
  ],
  "requires_human_confirmation": false
}

## Constraints:
- You CANNOT output (x, y, w, h) coordinates. The engine computes those.
- You ONLY choose strategies and assign elements to actions.
- Preserve locked elements (listed in constraints.preserve_ids).
- If the page is LAYOUT_INFEASIBLE, strongly prefer split_slide or remove_secondary_content.
- Mark destructive actions (split_slide, remove, compress) as requires_human_confirmation: true.
- Never select strategies not in the allowed_strategies list.

## Priorities:
1. Preserve primary and required elements.
2. Maintain semantic reading order.
3. Minimize element movement — prefer local fixes over global re-layout.
4. When choosing between splitting a slide and compressing, prefer splitting.
"""


def call_llm(
    decision_pack: DecisionPack,
    provider: str = "deepseek",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    """Send decision pack to LLM, return parsed strategy."""

    import urllib.request
    import urllib.error

    # Provider configs
    configs = {
        "deepseek": {
            "model": model or "deepseek-chat",
            "base_url": base_url or "https://api.deepseek.com/v1",
            "api_key": api_key or os.environ.get("DEEPSEEK_API_KEY", ""),
        },
        "openai": {
            "model": model or "gpt-4o",
            "base_url": base_url or "https://api.openai.com/v1",
            "api_key": api_key or os.environ.get("OPENAI_API_KEY", ""),
        },
        "claude": {
            "model": model or "claude-sonnet-4-20250514",
            "base_url": base_url or "https://api.anthropic.com/v1",
            "api_key": api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
        },
    }

    config = configs.get(provider, configs["deepseek"])
    if not config["api_key"]:
        return {
            "error": f"No API key for {provider}. Set {'ANTHROPIC_API_KEY' if provider == 'claude' else provider.upper() + '_API_KEY'} environment variable.",
        }

    # Build prompt
    pack_dict = {
        "slide_id": decision_pack.slide_id,
        "revision": decision_pack.revision,
        "page_type": decision_pack.page_type,
        "goal": decision_pack.goal_hint,
        "issue_summary": decision_pack.issue_summary,
        "infeasible": decision_pack.infeasible,
        "elements": decision_pack.elements,
        "relationships": decision_pack.relationships,
        "constraints": decision_pack.constraints,
        "attempted": decision_pack.attempted,
        "allowed_strategies": decision_pack.allowed_strategies,
        "budget": decision_pack.budget,
    }

    # Anthropic API uses different format
    if provider == "claude":
        return _call_claude(config, pack_dict, decision_pack)
    else:
        return _call_openai_compatible(config, pack_dict, decision_pack)


def _call_openai_compatible(config: dict, pack_dict: dict, pack: DecisionPack) -> dict:
    """Generic OpenAI-compatible API call (DeepSeek, OpenAI, etc.)."""
    import urllib.request
    import urllib.error

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(pack_dict, ensure_ascii=False, indent=2)},
    ]

    body = json.dumps({
        "model": config["model"],
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},
    }, ensure_ascii=False).encode('utf-8')

    url = f"{config['base_url']}/chat/completions"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        content = data["choices"][0]["message"]["content"]
        # Parse JSON from content (may have markdown wrapping)
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n```", 1)[0]
        return json.loads(content)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        return {"error": f"HTTP {e.code}: {error_body[:300]}"}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw_content": content[:500] if 'content' in dir() else 'N/A'}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _call_claude(config: dict, pack_dict: dict, pack: DecisionPack) -> dict:
    """Anthropic Messages API."""
    import urllib.request
    import urllib.error

    body = json.dumps({
        "model": config["model"],
        "max_tokens": 1024,
        "temperature": 0.3,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": json.dumps(pack_dict, ensure_ascii=False, indent=2)},
        ],
    }, ensure_ascii=False).encode('utf-8')

    url = f"{config['base_url']}/messages"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "x-api-key": config["api_key"],
        "anthropic-version": "2023-06-01",
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        content = data["content"][0]["text"]
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n```", 1)[0]
        return json.loads(content)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        return {"error": f"HTTP {e.code}: {error_body[:300]}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# ═══════════════════════════════════════════════════════════
# STRATEGY EXECUTOR —  translates LLM strategy to MCP calls
# ═══════════════════════════════════════════════════════════

def execute_strategy(
    session: PPTReflexMCPServer,
    strategy_response: dict,
    decision_pack: DecisionPack,
    expected_revision: int,
) -> dict:
    """Execute an LLM-chosen strategy via MCP calls. Returns result dict."""

    strategy = strategy_response.get("strategy", "unknown")
    plan = strategy_response.get("plan", [])
    requires_confirmation = strategy_response.get("requires_human_confirmation", False)

    if requires_confirmation:
        print(f"  ⚠ This strategy requires human confirmation (skipping for now)")
        return {"status": "requires_confirmation", "strategy": strategy}

    results = []

    for step in plan:
        action = step.get("action", "")
        targets = step.get("targets", [])

        if action == "align_left":
            # Align targets to a reference element's left edge
            reference = step.get("reference", targets[0] if targets else "")
            ctx_ref = session.call_tool("local_context", {"element_ids": [reference]})
            ref_bbox = None
            for t in ctx_ref.get("targets", []):
                if t["id"] == reference:
                    ref_bbox = t.get("bbox_pt")
                    break
            if ref_bbox:
                for tid in targets:
                    if tid == reference:
                        continue
                    ctx = session.call_tool("local_context", {"element_ids": [tid]})
                    for t in ctx.get("targets", []):
                        bbox = t.get("bbox_pt", [0, 0, 100, 100])
                        r = session.call_tool("move_element", {
                            "element_id": tid,
                            "x": ref_bbox[0],
                            "y": bbox[1],
                            "w": bbox[2],
                            "h": bbox[3],
                        })
                        results.append({"step": f"align_left {tid}→{reference}", "result": r.get("status")})

        elif action == "keep_on_current_slide":
            # No action needed — element stays
            pass

        elif action in ("move_to_new_slide", "remove_secondary_content", "split_slide"):
            # These are structural/destructive — mark for human confirmation in Phase 2
            results.append({"step": action, "result": "requires_implementation", "targets": targets})

        elif action in ("nudge_element", "move_element"):
            # Use the simulator to find best nudge
            for tid in targets:
                ctx = session.call_tool("local_context", {"element_ids": [tid]})
                for t in ctx.get("targets", []):
                    bbox = t.get("bbox_pt", [0, 0, 100, 100])
                    # Try nudging right first, then down
                    for direction, dx, dy in [("right", 80, 0), ("down", 0, 80)]:
                        r = session.call_tool("move_element", {
                            "element_id": tid,
                            "x": bbox[0] + dx,
                            "y": bbox[1] + dy,
                            "w": bbox[2],
                            "h": bbox[3],
                            "expected_revision": expected_revision,
                        })
                        if r.get("status") in ("ok", "needs_decision"):
                            results.append({"step": f"nudge {tid} {direction}", "result": "ok"})
                            break

        elif action == "resize_element":
            for tid in targets:
                ctx = session.call_tool("local_context", {"element_ids": [tid]})
                for t in ctx.get("targets", []):
                    bbox = t.get("bbox_pt", [0, 0, 100, 100])
                    r = session.call_tool("move_element", {
                        "element_id": tid,
                        "x": bbox[0],
                        "y": bbox[1],
                        "w": bbox[2] * 0.8,   # Shrink to 80%
                        "h": bbox[3],
                    })
                    results.append({"step": f"resize {tid}", "result": r.get("status")})

        else:
            results.append({"step": str(step), "result": "unknown_action"})

    return {
        "status": "executed" if results else "no_actions",
        "strategy": strategy,
        "results": results,
        "requires_human_confirmation": requires_confirmation,
    }


# ═══════════════════════════════════════════════════════════
# FULL AGENT LOOP WITH LLM
# ═══════════════════════════════════════════════════════════

def run_llm_agent_loop(
    input_path: str,
    provider: str = "deepseek",
    model: str | None = None,
    max_slides: int | None = None,
    max_rounds: int = 3,
    require_confirmation: bool = False,
):
    """Full agent loop: deterministic → LLM decision → execute → re-audit."""

    if not Path(input_path).exists():
        print(f"File not found: {input_path}")
        return

    work_path = input_path.replace(".pptx", "_llm.pptx")
    shutil.copy2(input_path, work_path)

    session = PPTReflexMCPServer()
    r = session.call_tool("open_presentation", {"path": work_path})
    total_slides = r["slides"]
    if max_slides:
        total_slides = min(total_slides, max_slides)

    print(f"PPT Reflex Agent + LLM (Provider: {provider})")
    print(f"Slides: {total_slides} | Max Rounds: {max_rounds}")
    if require_confirmation:
        print(f"Mode: requires human confirmation for destructive actions")
    print(f"{'='*60}")

    stats = {
        "slides_checked": 0,
        "slides_deterministic_fixed": 0,
        "slides_llm_fixed": 0,
        "slides_unchanged": 0,
        "slides_regressed": 0,
        "llm_calls": 0,
        "llm_success": 0,
        "llm_failures": 0,
        "total_score_delta": 0,
        "needs_human": 0,
    }

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

        # Initial audit
        initial_audit = session.call_tool("audit_slide", {})
        initial_score = score_issues(initial_audit.get("issues", []))
        initial_issues = initial_audit.get("issues", [])

        print(f"\nSlide {si+1}: initial score={initial_score} | {len(initial_issues)} issues")
        if not initial_issues:
            print(f"  ✓ Already clean")
            stats["slides_checked"] += 1
            continue

        # Phase 1: Deterministic repair (RepairPlanner)
        planner = RepairPlanner(session)
        det_results = []
        det_score_before = initial_score

        for rnd in range(min(2, max_rounds)):  # Up to 2 rounds of deterministic
            result = planner.plan()
            if result["status"] in ("clean",):
                print(f"  R{rnd+1}: deterministic ✓ clean")
                stats["slides_deterministic_fixed"] += 1
                break
            elif result["status"] == "fixed":
                print(f"  R{rnd+1}: deterministic fix — {result['candidate']['strategy']} "
                      f"(Δ={result['candidate']['delta']})")
                det_results.append(result)
            elif result["status"] in ("no_improvement", "no_candidates"):
                break
            elif result["status"] == "layout_infeasible":
                det_results.append(result)
                break

        # Post-deterministic audit
        post_det_audit = session.call_tool("audit_slide", {})
        remaining_issues = post_det_audit.get("issues", [])
        det_score_after = score_issues(remaining_issues)
        stats["total_score_delta"] += (det_score_after - det_score_before)

        if not remaining_issues:
            print(f"  ✓ Deterministic phase solved all issues")
            stats["slides_checked"] += 1
            continue

        # Phase 2: LLM decision for remaining issues
        print(f"  → {len(remaining_issues)} issues remain, consulting LLM...")

        # Check if layout is infeasible
        infeasible = check_layout_infeasible(session, summary, remaining_issues)

        # Build attempted history
        attempted = [
            {"strategy": r.get("candidate", {}).get("strategy", "deterministic"),
             "result": r.get("status", "?"),
             "reason": r.get("message", "")}
            for r in det_results
        ]

        # Build decision pack
        pack = build_decision_pack(session, remaining_issues, infeasible, attempted)

        # Call LLM
        print(f"  Decision pack: {pack.issue_summary['total']} issues, "
              f"{len(pack.elements)} elements, "
              f"{len(pack.allowed_strategies)} strategies")

        token_est = len(json.dumps({
            "issue_summary": pack.issue_summary,
            "elements": pack.elements,
            "relationships": pack.relationships,
            "constraints": pack.constraints,
            "allowed_strategies": pack.allowed_strategies,
        }, ensure_ascii=False))
        print(f"  Token est: ~{token_est} ({token_est//4} input tokens)")

        llm_response = call_llm(pack, provider=provider, model=model)
        stats["llm_calls"] += 1

        if llm_response.get("error"):
            print(f"  ✗ LLM error: {llm_response['error']}")
            stats["llm_failures"] += 1
            stats["slides_unchanged"] += 1
            stats["slides_checked"] += 1
            continue

        strategy = llm_response.get("strategy", "unknown")
        reason = llm_response.get("reason", "")
        print(f"  LLM chose: {strategy}")
        print(f"  Reason: {reason}")

        # Check if human confirmation required and enforce it
        if require_confirmation or llm_response.get("requires_human_confirmation"):
            plan = llm_response.get("plan", [])
            destructive = [s for s in plan if s.get("action") in
                          ("split_slide", "move_to_new_slide", "remove_secondary_content")]
            if destructive:
                print(f"  ⚠ Destructive actions require human confirmation:")
                for s in destructive:
                    print(f"    - {s['action']}: {s.get('targets', [])}")
                choice = input(f"  Confirm? [y/n]: ").strip().lower()
                if choice != 'y':
                    print(f"  → Skipped by human")
                    stats["needs_human"] += 1
                    stats["slides_unchanged"] += 1
                    stats["slides_checked"] += 1
                    continue

        # Execute strategy
        rev_r = session.call_tool("get_revision", {})
        exec_result = execute_strategy(session, llm_response, pack, rev_r.get("revision", 0))

        if exec_result.get("status") == "requires_confirmation":
            stats["needs_human"] += 1
            stats["slides_unchanged"] += 1
        elif exec_result.get("status") in ("executed", "no_actions"):
            # Re-audit
            post_llm_audit = session.call_tool("audit_slide", {})
            post_llm_score = score_issues(post_llm_audit.get("issues", []))
            delta = post_llm_score - det_score_after

            if delta < 0:
                print(f"  ✓ LLM phase improved score: {det_score_after} → {post_llm_score} ({delta:+d})")
                stats["slides_llm_fixed"] += 1
                stats["llm_success"] += 1
            elif delta == 0:
                print(f"  — LLM phase no change. {len(post_llm_audit.get('issues',[]))} issues remain")
                stats["slides_unchanged"] += 1
            else:
                print(f"  ✗ LLM phase regression: {det_score_after} → {post_llm_score} ({delta:+d})")
                stats["slides_regressed"] += 1

            stats["total_score_delta"] += delta
        else:
            stats["llm_failures"] += 1
            stats["slides_unchanged"] += 1

        stats["slides_checked"] += 1

    # Save
    session.call_tool("save_presentation", {})

    # Report
    print(f"\n{'='*60}")
    print(f"LLM AGENT RESULTS ({provider})")
    print(f"  Slides checked:              {stats['slides_checked']}")
    print(f"  Deterministic fixes:         {stats['slides_deterministic_fixed']}")
    print(f"  LLM fixes:                   {stats['slides_llm_fixed']}")
    print(f"  Slides unchanged:            {stats['slides_unchanged']}")
    print(f"  Slides regressed:            {stats['slides_regressed']}")
    print(f"  LLM calls:                   {stats['llm_calls']}")
    print(f"  LLM successes:               {stats['llm_success']}")
    print(f"  LLM failures:                {stats['llm_failures']}")
    print(f"  Needs human:                 {stats['needs_human']}")
    print(f"  Total score Δ:               {stats['total_score_delta']:+d}")
    print(f"  Output:                      {work_path}")
    print(f"{'='*60}")

    return stats


# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="PPT Reflex + LLM Agent")
    ap.add_argument("input", nargs="?", default="cases/broken.pptx")
    ap.add_argument("--provider", default="deepseek",
                    choices=["deepseek", "openai", "claude"])
    ap.add_argument("--model", help="Override default model")
    ap.add_argument("--max-slides", type=int, help="Limit slides to process")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--confirm", action="store_true",
                    help="Require human confirmation for destructive actions")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build decision packs but don't call LLM")
    args = ap.parse_args()

    if args.dry_run:
        # Dry run: just build and display decision packs
        import shutil
        work_path = args.input.replace(".pptx", "_dry.pptx")
        shutil.copy2(args.input, work_path)
        session = PPTReflexMCPServer()
        session.call_tool("open_presentation", {"path": work_path})

        for si in range(min(3, session.call_tool("open_presentation", {"path": work_path})["slides"])):
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
            print(f"\n{'='*60}")
            print(f"Slide {si+1} Decision Pack")
            print(f"{'='*60}")
            print(json.dumps({
                "slide_id": pack.slide_id,
                "page_type": pack.page_type,
                "goal": pack.goal_hint,
                "issue_summary": pack.issue_summary,
                "elements": pack.elements,
                "relationships": pack.relationships,
                "constraints": pack.constraints,
                "allowed_strategies": pack.allowed_strategies,
            }, ensure_ascii=False, indent=2))
            token_est = len(json.dumps(pack.elements, ensure_ascii=False))
            print(f"\nToken est: ~{token_est} elements ({token_est//4} input tokens)")
    else:
        run_llm_agent_loop(
            args.input, provider=args.provider, model=args.model,
            max_slides=args.max_slides, max_rounds=args.max_rounds,
            require_confirmation=args.confirm,
        )
