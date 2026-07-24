"""
PPT Reflex Engine — 主协调器

整合 L1-L3 层：
  L1 几何引擎（双层网格 + 精确 bbox + 七类检测）
  L2 规则引擎（声明式碰撞/字体/边界规则）
  L3 布局引擎（8 种固定页面模板）

自动修复分流：
  auto_fix → 直接修（零 Token）
  agent_decision → 打包 issue 给 Agent
  human_confirmation → 标记pending
  fatal_error → 拒绝执行

每次操作前检查 revision 乐观锁。
"""

from __future__ import annotations
from engine import (
    GeometryEngine, SlideElement, BBox,
    ContentRole, CollisionRole, CollisionVerdict,
    Issue, IssueCode, Severity,
    COARSE_CELL_PT, DEFAULT_SLIDE_W, DEFAULT_SLIDE_H, SAFE_MARGIN_PT,
    _grid_range,
)
from rules import RulesEngine, CollisionVerdict as _CV
from layout import LayoutEngine, LayoutTemplate
from nudge import NudgeEngine, MAX_BOUNDARY_SNAP_PT, MAX_ALIGNMENT_SNAP_PT, MAX_NUDGE_ATTEMPTS
from journal import Journal, OpResult
from dataclasses import dataclass, field
from typing import Any, Optional
import copy


# ═══════════════════════════════════════════════════════════
# CORE ENGINE
# ═══════════════════════════════════════════════════════════
class ReflexEngine:
    """
    PPT Reflex Engine — deterministic spatial QA + limited auto-fix.

    Usage:
        r = ReflexEngine()
        r.load_slide(elements)          # register all elements
        result = r.audit()              # full QA pass
        result = r.apply_layout("text_left_figure_right", {"body": "s5", "figure": "s7"})
    """

    def __init__(self, rules_path: str | None = None,
                 canvas_w_pt: float = DEFAULT_SLIDE_W,
                 canvas_h_pt: float = DEFAULT_SLIDE_H):
        self.geo = GeometryEngine(canvas_w_pt, canvas_h_pt, SAFE_MARGIN_PT)
        self.rules = RulesEngine(rules_path)
        self.layout = LayoutEngine(canvas_w_pt, canvas_h_pt)
        self.nudge = NudgeEngine(self.geo)
        self.journal = Journal()

    # ── element registration ───────────────────────────────
    def load_slide(self, elements: list[SlideElement]):
        """Register all elements from a slide."""
        self.geo.elements.clear()
        self.geo.coarse_grid.clear()
        self.geo.fine_grid.clear()
        self.nudge.reset()
        for e in elements:
            self.geo.register(e)
        # Post-load: run background detection
        self._detect_backgrounds()

    def add_element(self, elem: SlideElement):
        self.geo.register(elem)
        self._detect_backgrounds()

    def get_element(self, elem_id: str) -> SlideElement | None:
        return self.geo.elements.get(elem_id)

    def _detect_backgrounds(self):
        """Post-load: auto-detect background elements.
        Any shape covering >85% of canvas area → BACKGROUND role.
        Also exempts from collision — overlaps with background are allowed."""
        canvas_area = self.geo.canvas_w * self.geo.canvas_h
        for elem in self.geo.elements.values():
            if elem.content_role in (ContentRole.BACKGROUND,):
                continue
            area = elem.bbox.area
            if area > 0.85 * canvas_area:
                # Override whatever heuristic assigned — full-bleed is background
                elem.content_role = ContentRole.BACKGROUND
                elem.collision_role = CollisionRole.BACKGROUND_FILL

    # ── full audit ─────────────────────────────────────────
    def audit(self, elem_ids: list[str] | None = None) -> dict:
        """
        Full QA pass. Returns structured result suitable for Agent consumption.
        Only returns issues that survived all filters.
        """
        if elem_ids is None:
            elem_ids = list(self.geo.elements.keys())
        all_issues: list[Issue] = []

        # L1a: bounds
        for eid in elem_ids:
            all_issues.extend(self.geo.check_bounds(eid))

        # L1b: collision (four-stage)
        candidates = self.geo.find_candidate_pairs()
        overlaps = self.geo.exact_overlap_check(candidates)
        for ov in overlaps:
            a = self.geo.elements[ov["a"]]
            b = self.geo.elements[ov["b"]]
            verdict = self.rules.judge_overlap(a, b, ov["overlap_pct"])

            if verdict == CollisionVerdict.ALLOW:
                continue  # Silent — no issue
            elif verdict == CollisionVerdict.WARN:
                all_issues.append(Issue(
                    code=IssueCode.UNEXPECTED_OVERLAP,
                    severity=Severity.LOW,
                    targets=[ov["a"], ov["b"]],
                    detail={**ov, "roles": [a.content_role.value, b.content_role.value]},
                ))
            else:  # BLOCK
                all_issues.append(Issue(
                    code=IssueCode.UNEXPECTED_OVERLAP,
                    severity=Severity.HIGH,
                    targets=[ov["a"], ov["b"]],
                    detail={**ov, "roles": [a.content_role.value, b.content_role.value]},
                    auto_fixable=True,
                    auto_fix_fn="nudge_collision",
                ))

        # L1c: alignment
        all_issues.extend(self.geo.check_alignment(elem_ids))

        # L1d: spacing
        all_issues.extend(self.geo.check_spacing(elem_ids))

        # L1e: font
        all_issues.extend(self.geo.check_font_all())

        # L1g: density
        all_issues.extend(self.geo.check_density())

        # ── classify & route ──
        return self._classify_and_route(all_issues)

    def _classify_and_route(self, issues: list[Issue]) -> dict:
        """Split issues into auto-fix / agent-needed / human-needed."""
        # Separate by type
        auto = [i for i in issues if i.auto_fixable]
        medium_plus = [i for i in issues if not i.auto_fixable
                       and i.severity.value >= Severity.MEDIUM.value]
        deferred = [i for i in issues if not i.auto_fixable
                    and i.severity.value < Severity.MEDIUM.value]

        # Include deferred LOW issues as well (for completeness of audit)
        agent = medium_plus + deferred

        # ── auto-fix pass ──
        auto_records = []
        for issue in auto:
            if issue.auto_fix_fn == "snap_to_safe_area":
                for target in issue.targets:
                    elem = self.geo.elements.get(target)
                    if elem:
                        rec = self.nudge.snap_to_safe_area(elem)
                        if rec:
                            auto_records.append(rec)
            elif issue.auto_fix_fn == "snap_alignment_left":
                if "modal_left_pt" in issue.detail:
                    for target in issue.targets:
                        elem = self.geo.elements.get(target)
                        if elem:
                            rec = self.nudge.snap_alignment(elem, issue.detail["modal_left_pt"])
                            if rec:
                                auto_records.append(rec)
            elif issue.auto_fix_fn == "nudge_collision":
                if len(issue.targets) == 2:
                    a = self.geo.elements.get(issue.targets[0])
                    b = self.geo.elements.get(issue.targets[1])
                    if a and b:
                        recs = self.nudge.nudge_to_resolve_collision(a, b, issue.detail.get("overlap_pct", 0))
                        auto_records.extend(recs)
            elif issue.auto_fix_fn == "bump_font_size":
                pass  # Day 1: font adjustments not applied automatically yet

        # Re-run collision check after auto-fix to see what remains
        remaining = []
        candidates = self.geo.find_candidate_pairs()
        overlaps = self.geo.exact_overlap_check(candidates)
        for ov in overlaps:
            a = self.geo.elements[ov["a"]]
            b = self.geo.elements[ov["b"]]
            verdict = self.rules.judge_overlap(a, b, ov["overlap_pct"])
            if verdict == CollisionVerdict.BLOCK:
                remaining.append({
                    "code": "UNEXPECTED_OVERLAP",
                    "severity": "high",
                    "targets": [ov["a"], ov["b"]],
                    "roles": [a.content_role.value, b.content_role.value],
                    "overlap_pct": ov["overlap_pct"],
                })

        # Merge remaining agent issues with post-fix collision results
        agent_issues = [self._issue_dict(i) for i in agent] + remaining

        # Deduplicate
        seen = set()
        deduped = []
        for iss in agent_issues:
            key = (iss.get("code"), tuple(sorted(iss.get("targets", []))))
            if key not in seen:
                seen.add(key)
                deduped.append(iss)

        # Build response
        if not deduped:
            return {
                "status": "ok",
                "revision": self.journal.last_revision(),
                "auto_adjusted": [
                    {"element_id": r.element_id, "reason": r.reason}
                    for r in auto_records
                ],
            }

        return {
            "status": "needs_decision",
            "revision": self.journal.last_revision(),
            "issues": deduped,  # Return all issues (not top 5) for validation
            "deferred": 0,
            "auto_adjusted": [
                {"element_id": r.element_id, "reason": r.reason}
                for r in auto_records
            ],
            "budget": {"max_operations": 4, "remaining_iterations": 2},
        }

    def _issue_dict(self, issue: Issue) -> dict:
        return {
            "code": issue.code.name,
            "severity": issue.severity.name.lower(),
            "targets": issue.targets,
            **issue.detail,
        }

    # ── local context ──────────────────────────────────────
    def local_context(self, elem_ids: list[str]) -> dict:
        """Return target elements + immediate neighbors for Agent decision-making."""
        targets = []
        neighbor_ids: set[str] = set()

        for eid in elem_ids:
            elem = self.geo.elements.get(eid)
            if not elem:
                continue
            targets.append(self._elem_dict(elem))
            # Find neighbors sharing coarse cells
            for cell in elem.coarse_cells:
                for n in self.geo.coarse_grid[cell]:
                    if n.id != eid:
                        neighbor_ids.add(n.id)

        neighbors = [self._elem_dict(self.geo.elements[nid])
                     for nid in neighbor_ids if nid in self.geo.elements]

        return {
            "status": "local_context",
            "targets": targets,
            "neighbors": neighbors,
            "canvas": {"width_pt": self.geo.canvas_w, "height_pt": self.geo.canvas_h,
                       "coarse_grid": f"{self.geo.coarse_max[0]}×{self.geo.coarse_max[1]}"},
        }

    def _elem_dict(self, elem: SlideElement) -> dict:
        return {
            "id": elem.id,
            "role": elem.content_role.value,
            "grid": _grid_range(elem.coarse_cells),
            "bbox_pt": [round(elem.bbox.x, 1), round(elem.bbox.y, 1),
                        round(elem.bbox.w, 1), round(elem.bbox.h, 1)],
            "font_size_pt": elem.font_size_pt,
            "locked": elem.locked,
            "locked_by": elem.locked_by,
        }

    # ── template layout application ────────────────────────
    def apply_layout(self, template_name: str, role_mapping: dict[str, str],
                     expected_revision: int | None = None) -> dict:
        """
        Move elements to positions defined by a template.
        role_mapping: {"body": "shape-05", "title": "shape-01", "figure": "shape-07", ...}
        """
        # Optimistic lock
        if expected_revision is not None:
            lock_check = self.journal.check_revision(expected_revision)
            if lock_check:
                return {"status": lock_check.status, "revision": lock_check.revision,
                        "message": lock_check.message}

        try:
            positions = self.layout.resolve_positions(template_name, role_mapping)
        except KeyError as e:
            return {"status": "blocked", "message": str(e)}

        self.journal.begin_transaction()
        ops = []
        for eid, new_bbox in positions.items():
            elem = self.geo.elements.get(eid)
            if not elem or elem.locked:
                continue
            original = {"x": round(elem.bbox.x, 1), "y": round(elem.bbox.y, 1),
                        "w": round(elem.bbox.w, 1), "h": round(elem.bbox.h, 1)}
            # Execute
            self.geo.remove(elem)
            elem.bbox = new_bbox
            self.geo.register(elem)
            after = {"x": round(elem.bbox.x, 1), "y": round(elem.bbox.y, 1),
                     "w": round(elem.bbox.w, 1), "h": round(elem.bbox.h, 1)}
            ops.append({"element_id": eid, "action": "move_to_template",
                        "before": original, "after": after,
                        "reason": f"applied template '{template_name}'"})

        rev, op_ids = self.journal.record_batch("agent", ops)
        self.journal.commit()

        # Post-layout audit
        audit_result = self.audit()
        audit_result["revision"] = rev
        audit_result["applied_template"] = template_name
        return audit_result

    # ── manual edit (human or agent) ───────────────────────
    def move_element(self, elem_id: str, new_bbox: BBox,
                     expected_revision: int | None = None,
                     source: str = "agent") -> dict:
        """Move/resize one element. Checks revision lock."""
        if expected_revision is not None:
            lock_check = self.journal.check_revision(expected_revision)
            if lock_check:
                return {"status": lock_check.status, "revision": lock_check.revision,
                        "message": lock_check.message}

        elem = self.geo.elements.get(elem_id)
        if not elem:
            return {"status": "blocked", "message": f"Element '{elem_id}' not found"}
        if elem.locked:
            return {"status": "blocked", "message": f"Element '{elem_id}' locked by {elem.locked_by}"}

        original = {"x": round(elem.bbox.x, 1), "y": round(elem.bbox.y, 1),
                    "w": round(elem.bbox.w, 1), "h": round(elem.bbox.h, 1)}

        # L1: physics check
        if new_bbox.w <= 0 or new_bbox.h <= 0:
            return {"status": "blocked", "message": "Invalid dimensions"}

        # Execute
        self.geo.remove(elem)
        elem.bbox = new_bbox
        self.geo.register(elem)

        after = {"x": round(elem.bbox.x, 1), "y": round(elem.bbox.y, 1),
                 "w": round(elem.bbox.w, 1), "h": round(elem.bbox.h, 1)}
        rev, op_id = self.journal.record(source, elem_id, "move", original, after)

        # Post-move audit
        audit_result = self.audit([elem_id])
        audit_result["revision"] = rev
        audit_result["operation_id"] = op_id
        return audit_result

    # ── human edit notification ────────────────────────────
    def notify_human_edit(self, elem_id: str, new_bbox: BBox):
        """Called when human manually edits in PowerPoint."""
        elem = self.geo.elements.get(elem_id)
        if elem:
            original = {"x": round(elem.bbox.x, 1), "y": round(elem.bbox.y, 1),
                        "w": round(elem.bbox.w, 1), "h": round(elem.bbox.h, 1)}
            self.geo.remove(elem)
            elem.bbox = new_bbox
            self.geo.register(elem)
            after = {"x": round(elem.bbox.x, 1), "y": round(elem.bbox.y, 1),
                     "w": round(elem.bbox.w, 1), "h": round(elem.bbox.h, 1)}
            self.journal.record("human", elem_id, "manual_edit", original, after)
        self.nudge.reset()

    # ── element locking ────────────────────────────────────
    def lock_element(self, elem_id: str, locked_by: str = "human"):
        elem = self.geo.elements.get(elem_id)
        if elem:
            elem.locked = True
            elem.locked_by = locked_by

    def unlock_element(self, elem_id: str):
        elem = self.geo.elements.get(elem_id)
        if elem:
            elem.locked = False
            elem.locked_by = ""

    # ── rollback ───────────────────────────────────────────
    def rollback(self) -> list[dict]:
        """Roll back last transaction — agent operations only.
        Human edits during the transaction are preserved.
        Engine state is reverted per-element: if a human edit overwrote
        the agent's position, the human edit stands."""
        reversed_ops = self.journal.rollback(source_filter="agent")
        # Collect human edits that happened during the rolled-back window:
        # those elements should NOT be reverted to agent's "before" state
        human_edited_elements: set[str] = set()
        for entry in self.journal.entries:
            if entry.source == "human":
                human_edited_elements.add(entry.element_id)

        for op in reversed_ops:
            elem = self.geo.elements.get(op["element_id"])
            if elem and not elem.locked:
                if op["element_id"] in human_edited_elements:
                    continue  # Human edit overrides — don't revert
                inv = op["before_inverse"]
                self.geo.remove(elem)
                elem.bbox = BBox(inv["x"], inv["y"], inv["w"], inv["h"])
                self.geo.register(elem)
        return reversed_ops
