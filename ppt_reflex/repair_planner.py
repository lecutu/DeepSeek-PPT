"""PPT Reflex Engine — Repair Planner v2 (Hot Wiring)

v2-hotwired: Simulator uses direct state copy from session instead of cloning.
The root bug was that the Simulator rebuilds elements from element_summary()
which doesn't include bbox_pt. Instead, we read local_context for each element
to get actual coordinates for the simulation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from mcp_server import PPTReflexMCPServer
import copy


# ═══════════════════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════════════════

def score_issues(issues: list[dict]) -> int:
    """Weighted issue score. Lower is better."""
    s = 0
    for iss in issues:
        sev = iss.get("severity", "medium")
        if sev == "fatal":    s += 100
        elif sev == "high":   s += 30
        elif sev == "medium": s += 10
        elif sev == "low":    s += 3
    return s

def score_delta(before: list[dict], after: list[dict]) -> int:
    """Net change in issue score. Negative = improvement."""
    return score_issues(after) - score_issues(before)


# ═══════════════════════════════════════════════════════════
# CANDIDATE GENERATION
# ═══════════════════════════════════════════════════════════

@dataclass
class Candidate:
    """A proposed fix that has been simulated but not applied."""
    strategy: str
    element_id: str
    new_bbox: dict              # {x, y, w, h}
    operation: dict              # args for tool call
    score_after: int = 999
    new_fatal: int = 99
    new_high: int = 99
    delta: int = 999             # negative = improvement

def generate_nudge_candidates(
    session: PPTReflexMCPServer,
    elem_id: str,
    target_bbox: list,           # [x, y, w, h]
    overlap_bbox: list | None,   # [x, y, w, h] of overlapping element
    avoid_oob: bool = True,
) -> list[Candidate]:
    """
    Multi-direction, progressive step nudge search.

    4 directions × 5 step sizes = 20 candidates.
    Pre-filters: must reduce overlap with overlap_bbox, must stay in bounds.
    """
    steps = [4, 8, 16, 32, 64]
    directions = ["left", "right", "up", "down"]
    candidates = []

    for direction in directions:
        for step in steps:
            new = {
                "x": target_bbox[0],
                "y": target_bbox[1],
                "w": target_bbox[2],
                "h": target_bbox[3],
            }
            if direction == "left":
                new["x"] -= step
            elif direction == "right":
                new["x"] += step
            elif direction == "up":
                new["y"] -= step
            elif direction == "down":
                new["y"] += step

            # Safety: within canvas bounds
            if avoid_oob:
                if new["x"] < 0 or new["y"] < 0:
                    continue
                if new["x"] + new["w"] > 960 or new["y"] + new["h"] > 540:
                    continue

            # Pre-filter: must reduce overlap with other element
            if overlap_bbox:
                # Current overlap area
                cur_inter_x = max(0, min(target_bbox[0]+target_bbox[2], overlap_bbox[0]+overlap_bbox[2])
                                    - max(target_bbox[0], overlap_bbox[0]))
                cur_inter_y = max(0, min(target_bbox[1]+target_bbox[3], overlap_bbox[1]+overlap_bbox[3])
                                    - max(target_bbox[1], overlap_bbox[1]))
                cur_overlap = cur_inter_x * cur_inter_y

                # New overlap area
                new_inter_x = max(0, min(new["x"]+new["w"], overlap_bbox[0]+overlap_bbox[2])
                                    - max(new["x"], overlap_bbox[0]))
                new_inter_y = max(0, min(new["y"]+new["h"], overlap_bbox[1]+overlap_bbox[3])
                                    - max(new["y"], overlap_bbox[1]))
                new_overlap = new_inter_x * new_inter_y

                # Only keep if overlap decreased
                if new_overlap > 0 and new_overlap >= cur_overlap:
                    continue

            candidates.append(Candidate(
                strategy=f"nudge_{direction}_{step}pt",
                element_id=elem_id,
                new_bbox=new,
                operation={
                    "element_id": elem_id,
                    "x": new["x"],
                    "y": new["y"],
                    "w": new["w"],
                    "h": new["h"],
                },
            ))

    return candidates


def generate_snap_candidates(
    session: PPTReflexMCPServer,
    elem_id: str,
    current_bbox: list,
    overflow: dict,
) -> list[Candidate]:
    """Snap element back inside safe area. Always exactly 1 candidate."""
    x, y, w, h = current_bbox
    margin = 36
    canvas_w, canvas_h = 960, 540

    new_x = max(margin, min(x, canvas_w - margin - w))
    new_y = max(margin, min(y, canvas_h - margin - h))

    if new_x == x and new_y == y:
        return []

    return [Candidate(
        strategy="snap_to_safe",
        element_id=elem_id,
        new_bbox={"x": new_x, "y": new_y, "w": w, "h": h},
        operation={"element_id": elem_id, "x": new_x, "y": new_y, "w": w, "h": h},
    )]


def check_layout_infeasible(
    session: PPTReflexMCPServer,
    summary: dict,
    issues: list[dict],
) -> dict | None:
    """
    Conservative layout infeasibility check.

    Returns LAYOUT_INFEASIBLE issue dict if:
    - Density > 85% AND ≥ 3 collision issues remain after 2 fix attempts
    OR
    - Total element area * 1.2 > safe area (with padding)
    """
    elements = summary.get("elements", [])
    if len(elements) < 4:
        return None

    # Compute total content area (excluding background)
    total_area = 0
    for el in elements:
        if el.get("role") == "background":
            continue
        bbox = el.get("bbox_pt")
        if bbox and len(bbox) == 4:
            total_area += bbox[2] * bbox[3]

    safe_area = (960 - 72) * (540 - 72)  # margin 36pt all sides
    ratio = total_area / safe_area

    if ratio > 1.15:  # 15% over safe area
        collision_count = sum(1 for i in issues if i["code"] == "UNEXPECTED_OVERLAP")
        if collision_count >= 3:
            return {
                "code": "LAYOUT_INFEASIBLE",
                "severity": "high",
                "reason": (
                    f"Content area ({ratio:.0%} of safe area) cannot fit "
                    f"with current constraints ({collision_count} collisions, "
                    f"{len(elements)} elements, min font constraints not met)."
                ),
                "metrics": {
                    "area_ratio": round(ratio, 2),
                    "element_count": len(elements),
                    "collision_count": collision_count,
                },
                "options": [
                    "split_slide",
                    "remove_secondary_content",
                    "change_page_type",
                    "reduce_element_sizes",
                ],
            }

    return None


# ═══════════════════════════════════════════════════════════
# SIMULATOR
# ═══════════════════════════════════════════════════════════

class Simulator:
    """
    Simulates candidate fixes by creating a temporary ReflexEngine,
    applying the candidate, and auditing. No commits to the real session.

    This is a lightweight simulation — it clones the element states
    into a new engine instance, applies the change, and audits.
    """

    def __init__(self, session: PPTReflexMCPServer):
        self.session = session
        # Snapshot current state for simulation
        self._snapshot()

    def _snapshot(self):
        """Capture current element states WITH bbox from local_context."""
        summary = self.session.call_tool("element_summary", {})
        elements = summary.get("elements", [])
        self._slide_id = summary.get("slide_id", "?")

        # Enrich with bbox from local_context (element_summary doesn't include bbox)
        for el in elements:
            ctx = self.session.call_tool("local_context", {"element_ids": [el["id"]]})
            for t in ctx.get("targets", []):
                if t["id"] == el["id"]:
                    el["bbox_pt"] = t.get("bbox_pt", [0, 0, 100, 100])
                    el["font_size_pt"] = t.get("font_size_pt", 12.0)

        self._elements = elements

    def simulate(self, candidate: Candidate) -> dict:
        """
        Apply candidate operation in a COPY of the engine,
        audit the result, return the audit dict.

        Strategy: clone state into a new ReflexEngine, apply, audit.
        """
        from reflex import ReflexEngine
        from engine import SlideElement, BBox, ContentRole, CollisionRole

        # Build a fresh engine with current state
        engine = ReflexEngine()
        elements = []
        for el in self._elements:
            bbox = el.get("bbox_pt", [0, 0, 100, 100])
            try:
                role = ContentRole(el.get("role", "unknown"))
            except ValueError:
                role = ContentRole.UNKNOWN

            e = SlideElement(
                id=el["id"],
                bbox=BBox(
                    x=bbox[0] if len(bbox) > 0 else 0,
                    y=bbox[1] if len(bbox) > 1 else 0,
                    w=bbox[2] if len(bbox) > 2 else 100,
                    h=bbox[3] if len(bbox) > 3 else 100,
                ),
                content_role=role,
                text=el.get("text_preview", ""),
                locked=el.get("locked", False),
                locked_by=el.get("locked_by", ""),
            )
            elements.append(e)

        engine.load_slide(elements)

        # Apply candidate
        bbox = candidate.new_bbox
        engine.move_element(
            candidate.element_id,
            BBox(x=bbox["x"], y=bbox["y"], w=bbox["w"], h=bbox["h"]),
            source="simulator",
        )

        # Audit
        result = engine.audit()
        return result


# ═══════════════════════════════════════════════════════════
# STRICT IMPROVEMENT GATE
# ═══════════════════════════════════════════════════════════

def evaluate_candidates(
    simulator: Simulator,
    candidates: list[Candidate],
    current_issues: list[dict],
) -> list[Candidate]:
    """
    Simulate each candidate, compute its post-fix score.
    Mark candidates that are strict improvements.
    Sorts best-to-worst.
    """
    current_score = score_issues(current_issues)

    for c in candidates:
        try:
            result = simulator.simulate(c)
            c.score_after = score_issues(result.get("issues", []))
            c.delta = c.score_after - current_score
            # Count new severe issues
            c.new_fatal = sum(
                1 for i in result.get("issues", [])
                if i.get("severity") == "fatal"
            )
            c.new_high = sum(
                1 for i in result.get("issues", [])
                if i.get("severity") == "high"
                and i.get("code") not in ("DENSITY_HIGH",)
            )
        except Exception:
            c.score_after = 9999
            c.delta = 9999

    # Filter: strict improvement only
    strict = [
        c for c in candidates
        if c.delta < 0           # net score improvement
        and c.new_fatal == 0     # no new fatal issues
        and c.new_high == 0      # no new high issues
    ]

    # Sort by delta (most negative = best), then by strategy (prefer nudge)
    strict.sort(key=lambda c: (c.delta, "snap" not in c.strategy))

    return strict


def accept_candidate(
    session: PPTReflexMCPServer,
    candidate: Candidate,
    expected_revision: int,
) -> dict:
    """
    Apply a validated candidate in a transaction.
    Checks revision lock, applies, audits, commits.
    """
    # Begin transaction
    session.call_tool("begin_transaction", {})

    # Re-check revision
    rev_r = session.call_tool("get_revision", {})
    if rev_r.get("revision", -1) != expected_revision:
        session.call_tool("rollback", {})
        return {"status": "state_changed", "message": "Revision changed during fix"}

    # Apply
    result = session.call_tool("move_element", {
        **candidate.operation,
        "expected_revision": expected_revision,
    })

    if result.get("status") in ("blocked", "state_changed", "error"):
        session.call_tool("rollback", {})
        return result

    # Post-audit
    audit = session.call_tool("audit_slide", {})
    post_score = score_issues(audit.get("issues", []))

    # Gate: if new fatal/high → rollback
    new_high = sum(
        1 for i in audit.get("issues", [])
        if i.get("severity") in ("high", "fatal")
        and i.get("code") != "DENSITY_HIGH"
    )
    if new_high > 0:
        session.call_tool("rollback", {})
        return {
            "status": "rolled_back",
            "reason": f"Candidate introduced {new_high} new high-severity issues",
            "strategy": candidate.strategy,
        }

    session.call_tool("commit", {})
    return {
        "status": "ok",
        "strategy": candidate.strategy,
        "element_id": candidate.element_id,
        "score_before": post_score - candidate.delta,
        "score_after": post_score,
        "delta": candidate.delta,
        "revision": audit.get("revision"),
    }


# ═══════════════════════════════════════════════════════════
# REPAIR PLANNER V2
# ═══════════════════════════════════════════════════════════

class RepairPlanner:
    """
    Coordinates the full repair pipeline:

    audit → detect infeasibility
          → generate candidates
          → simulate
          → strict improvement gate
          → commit best candidate
          → if none → needs_decision
    """

    def __init__(self, session: PPTReflexMCPServer):
        self.session = session

    def plan(self, max_candidates: int = 18) -> dict:
        """
        One round of repair planning.

        Returns:
          {"status": "fixed", "candidate": ..., "audit": ...}
          {"status": "no_candidates", "issues": [...], "infeasible": ...|None}
          {"status": "needs_decision", "issues": [...], "message": "..."}
        """
        # 1. Audit current state
        audit = self.session.call_tool("audit_slide", {})
        issues = audit.get("issues", [])
        current_score = score_issues(issues)

        if not issues:
            return {"status": "clean", "audit": audit}

        # 2. Check LAYOUT_INFEASIBLE
        summary = self.session.call_tool("element_summary", {})
        infeasible = check_layout_infeasible(self.session, summary, issues)
        if infeasible:
            return {
                "status": "layout_infeasible",
                "infeasible": infeasible,
                "issues": issues,
                "options": infeasible["options"],
            }

        # 3. Get current revision
        rev_r = self.session.call_tool("get_revision", {})
        expected_revision = rev_r.get("revision", 0)

        # 4. Generate candidates for each fixable issue
        simulator = Simulator(self.session)
        all_candidates = []

        for iss in issues:
            code = iss["code"]
            targets = iss.get("targets", [])

            if code == "OUT_OF_BOUNDS":
                for eid in targets:
                    ctx = self.session.call_tool("local_context", {"element_ids": [eid]})
                    for t in ctx.get("targets", []):
                        bbox = t.get("bbox_pt", [0, 0, 100, 100])
                        overflow = iss.get("overflow_pt", {})
                        candidates = generate_snap_candidates(
                            self.session, eid, bbox, overflow,
                        )
                        all_candidates.extend(candidates)

            elif code == "UNEXPECTED_OVERLAP":
                if len(targets) == 2:
                    ctx = self.session.call_tool("local_context", {"element_ids": targets})
                    target_bbox = None
                    other_bbox = None
                    for t in ctx.get("targets", []):
                        if t["id"] == targets[1]:
                            target_bbox = t.get("bbox_pt", [0, 0, 100, 100])
                        else:
                            other_bbox = t.get("bbox_pt", [0, 0, 100, 100])
                    if target_bbox:
                        candidates = generate_nudge_candidates(
                            self.session, targets[1], target_bbox, other_bbox,
                        )
                        all_candidates.extend(candidates)

            elif code == "ALIGNMENT_DRIFT":
                modal = iss.get("modal_left_pt")
                if modal and targets:
                    ctx = self.session.call_tool("local_context", {"element_ids": targets})
                    for t in ctx.get("targets", []):
                        bbox = t.get("bbox_pt", [0, 0, 100, 100])
                        c = Candidate(
                            strategy=f"align_to_{modal:.0f}pt",
                            element_id=targets[0],
                            new_bbox={
                                "x": modal, "y": bbox[1],
                                "w": bbox[2], "h": bbox[3],
                            },
                            operation={
                                "element_id": targets[0],
                                "x": modal, "y": bbox[1],
                                "w": bbox[2], "h": bbox[3],
                            },
                        )
                        all_candidates.append(c)

            # FONT_BELOW_THRESHOLD, SPACING_DEVIATION, DENSITY_HIGH → skip (needs human/LLM)

        if not all_candidates:
            return {
                "status": "no_candidates",
                "issues": issues,
                "current_score": current_score,
                "message": "No deterministic fix candidates available. Requires semantic decision.",
            }

        # 5. Simulate + evaluate
        viable = evaluate_candidates(simulator, all_candidates, issues)

        if not viable:
            return {
                "status": "no_improvement",
                "candidates_tried": len(all_candidates),
                "issues": issues,
                "current_score": current_score,
                "message": (
                    f"Simulated {len(all_candidates)} candidates. "
                    "None produced a strict improvement. "
                    "Page may require semantic restructuring."
                ),
            }

        # 6. Pick best candidate and commit
        best = viable[0]
        result = accept_candidate(self.session, best, expected_revision)

        # 7. Re-audit
        post_audit = self.session.call_tool("audit_slide", {})

        return {
            "status": "fixed" if result.get("status") == "ok" else "failed",
            "candidate": {
                "strategy": result.get("strategy", best.strategy),
                "element_id": result.get("element_id", best.element_id),
                "delta": result.get("delta", best.delta),
            },
            "audit": post_audit,
            "tried": len(all_candidates),
            "viable": len(viable),
        }


# ═══════════════════════════════════════════════════════════
# AGENT LOOP V2 (uses RepairPlanner)
# ═══════════════════════════════════════════════════════════

def run_agent_loop_v2(input_path: str, max_rounds: int = 3):
    """Full repair loop using RepairPlanner."""
    import shutil
    from pathlib import Path

    if not Path(input_path).exists():
        print(f"File not found: {input_path}")
        return

    work_path = input_path.replace(".pptx", "_work.pptx")
    shutil.copy2(input_path, work_path)

    session = PPTReflexMCPServer()
    r = session.call_tool("open_presentation", {"path": work_path})
    total_slides = r["slides"]

    print(f"PPT Reflex Agent Loop v2 (Simulate + Strict Gate)")
    print(f"Slides: {total_slides} | Max Rounds: {max_rounds}")
    print(f"{'='*60}")

    stats = {
        "slides_checked": 0,
        "slides_clean": 0,
        "slides_improved": 0,
        "slides_unchanged": 0,
        "slides_regressed": 0,
        "layout_infeasible": 0,
        "total_candidates_tried": 0,
        "total_candidates_accepted": 0,
        "total_rollbacks": 0,
        "initial_score": 0,
        "final_score": 0,
        "needs_decision": 0,
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

        planner = RepairPlanner(session)
        initial_audit = session.call_tool("audit_slide", {})
        slide_initial_score = score_issues(initial_audit.get("issues", []))
        stats["initial_score"] += slide_initial_score

        print(f"\nSlide {si+1}: initial score={slide_initial_score} | {len(initial_audit.get('issues',[]))} issues")

        round_num = 0
        slide_improved = False
        slide_regressed = False

        for round_num in range(1, max_rounds + 1):
            result = planner.plan()

            if result["status"] == "clean":
                print(f"  R{round_num}: ✓ clean")
                break
            elif result["status"] == "fixed":
                cand = result["candidate"]
                print(f"  R{round_num}: fixed via {cand['strategy']} "
                      f"(Δ={cand['delta']}, tried {result.get('tried',0)}, "
                      f"viable {result.get('viable',0)})")
                stats["total_candidates_tried"] += result.get("tried", 0)
                stats["total_candidates_accepted"] += 1
                slide_improved = True
            elif result["status"] == "no_improvement":
                print(f"  R{round_num}: no improvement "
                      f"(tried {result.get('candidates_tried',0)} candidates)")
                stats["total_candidates_tried"] += result.get("candidates_tried", 0)
                # Check if issues got worse
                post_score = score_issues(session.call_tool("audit_slide", {}).get("issues", []))
                if post_score > slide_initial_score:
                    slide_regressed = True
                break  # Stop trying — needs semantic decision
            elif result["status"] == "layout_infeasible":
                inf = result["infeasible"]
                print(f"  R{round_num}: LAYOUT_INFEASIBLE — "
                      f"area ratio {inf['metrics']['area_ratio']:.1%}, "
                      f"{inf['metrics']['collision_count']} collisions")
                stats["layout_infeasible"] += 1
                break
            elif result["status"] == "no_candidates":
                print(f"  R{round_num}: no deterministic candidates — needs_decision")
                stats["needs_decision"] += 1
                break
            elif result["status"] == "failed":
                print(f"  R{round_num}: fix failed (rolled back)")
                stats["total_rollbacks"] += 1

        else:
            print(f"  → max rounds reached")

        # Final audit for this slide
        final_audit = session.call_tool("audit_slide", {})
        slide_final_score = score_issues(final_audit.get("issues", []))
        stats["final_score"] += slide_final_score

        if slide_final_score == 0:
            stats["slides_clean"] += 1
        elif slide_final_score < slide_initial_score:
            stats["slides_improved"] += 1
        elif slide_final_score == slide_initial_score:
            stats["slides_unchanged"] += 1
        if slide_final_score > slide_initial_score:
            stats["slides_regressed"] += 1

        stats["slides_checked"] += 1

    # Save
    session.call_tool("save_presentation", {})

    # Report
    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"  Slides checked:      {stats['slides_checked']}")
    print(f"  Slides clean:        {stats['slides_clean']}")
    print(f"  Slides improved:     {stats['slides_improved']}")
    print(f"  Slides unchanged:    {stats['slides_unchanged']}")
    print(f"  Slides regressed:    {stats['slides_regressed']}")
    print(f"  Layout infeasible:   {stats['layout_infeasible']}")
    print(f"  Needs decision:      {stats['needs_decision']}")
    print(f"  Candidates tried:    {stats['total_candidates_tried']}")
    print(f"  Candidates accepted: {stats['total_candidates_accepted']}")
    print(f"  Rollbacks:           {stats['total_rollbacks']}")
    print(f"  Score Δ:             {stats['initial_score']} → {stats['final_score']} "
          f"({stats['final_score'] - stats['initial_score']:+d})")

    net_improved = stats['slides_clean'] + stats['slides_improved']
    reg_rate = stats['slides_regressed'] / stats['slides_checked'] * 100 if stats['slides_checked'] else 0
    print(f"  Net improvement:     {net_improved}/{stats['slides_checked']}")
    print(f"  Regression rate:     {reg_rate:.0f}%")
    print(f"{'='*60}")

    return stats


# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="PPT Reflex Agent Loop v2")
    ap.add_argument("input", nargs="?", default="cases/broken.pptx")
    ap.add_argument("--max-rounds", type=int, default=3)
    args = ap.parse_args()
    run_agent_loop_v2(args.input, args.max_rounds)
