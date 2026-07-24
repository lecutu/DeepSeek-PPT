"""
grid/canvas.py — 主控制器：classify → place 两阶段 + advisory + commit/rollback

三层架构：
  几何层 — 坐标 / clamp / 相切容忍（positioning + serializer._clamp_bbox）
  语义层 — SemanticRole / 两张表（AI 的理解，最终决定权）
  常识层 — OverlapPolicy / Advisory（引擎的领域先验，建议+校验基线）
"""

from __future__ import annotations
from copy import deepcopy

from .types import (
    GridConfig, ContentType, Verdict, InfoCell,
    Conflict, PlacementResult, LayoutProfile,
    ElementPayload, SemanticRole, ENTITY_ROLES, OVERLAY_ROLES,
    ROLE_Z_BASE, table_of,
    Family, Strength, OverlapVerdict, OverlapPolicy,
    Advisory, POLICIES, family_of, _verdict_to_level,
)
from .positioning import cells_to_bbox, is_cell_in_bounds, bbox_to_coarse_cells, bbox_to_fine_cells
from .info_grid import InformationGrid
from .matrix import InteractionMatrix


class GridCanvas:
    """PPT 画布。三层架构：几何→语义→常识。"""

    def __init__(self, config: GridConfig | None = None):
        self.config = config or GridConfig()
        self.info_grid = InformationGrid(self.config)
        self.matrix = InteractionMatrix(self.config)
        self._profiles: dict[str, LayoutProfile] = {}
        self._entity_ids: set[str] = set()
        self._overlay_ids: set[str] = set()

    # ═══════════════════════════════════════════════════════════
    # 常识层接口
    # ═══════════════════════════════════════════════════════════

    def advise_default_role(self, ct: ContentType) -> SemanticRole:
        """扶手：AI 没填 role 时，引擎按族先验给默认建议。"""
        return POLICIES[family_of(ct)].default_role

    def family_of(self, ct: ContentType) -> Family:
        return family_of(ct)

    def policy(self, ct: ContentType) -> OverlapPolicy:
        return POLICIES[family_of(ct)]

    # ═══════════════════════════════════════════════════════════
    # CORE: try_place（三层整合）
    # ═══════════════════════════════════════════════════════════

    def try_place(self, element_id: str, content_type: ContentType,
                  target_cells: list[str], payload: ElementPayload | None = None) -> PlacementResult:
        """放置元素。

        三层协作：
          常识层 — Family → OverlapPolicy（扶手 + 主动 advisory + 校验基线）
          语义层 — payload.role（AI 的理解，可 override 常识）
          几何层 — bbox / boundary / clamp
        """
        if not target_cells:
            return PlacementResult(
                verdict=Verdict.BLOCK,
                conflicts=[Conflict(cell_addr="", new_id=element_id,
                    existing_type=ContentType.UNKNOWN, new_type=content_type,
                    verdict=Verdict.BLOCK, detail="空目标区域")],
            )

        fam = family_of(content_type)
        pol = POLICIES[fam]

        # ── 扶手：AI 没填 role → 引擎用族先验默认 ──
        role = payload.role if payload else pol.default_role
        tbl = table_of(role)
        advisories: list[Advisory] = []

        # ── ① 几何层 ──
        bbox = cells_to_bbox(target_cells, self.config)
        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]

        oob_cells = [c for c in target_cells if not is_cell_in_bounds(c, self.config)]
        if oob_cells:
            return PlacementResult(
                verdict=Verdict.BLOCK,
                conflicts=[Conflict(cell_addr=oob_cells[0], new_id=element_id,
                    existing_type=ContentType.UNKNOWN, new_type=content_type,
                    verdict=Verdict.BLOCK,
                    detail=f"out of bounds: {', '.join(oob_cells[:5])}")],
            )

        # ③ text overflow
        if payload is not None and payload.text.strip():
            from .text_metrics import estimate_text_size
            ov_x, ov_y, rw, rh = estimate_text_size(
                payload.text, font_pt=payload.font_size,
                line_spacing=payload.line_spacing,
                box_width_pt=w, box_height_pt=h, word_wrap=True,
            )
            if ov_y > 2:
                excess_lines = int(ov_y / (payload.font_size * payload.line_spacing)) + 1
                total_lines = payload.text.count("\n") + 1
                max_fit = max(1, total_lines - excess_lines)
                return PlacementResult(
                    verdict=Verdict.WARN,
                    warnings=[Conflict(cell_addr=target_cells[0], new_id=element_id,
                        existing_type=ContentType.UNKNOWN, new_type=content_type,
                        verdict=Verdict.WARN,
                        detail=(f"text overflow: needs {rh:.0f}pt, box {h:.0f}pt, "
                                f"excess {ov_y:.0f}pt. Reduce to {max_fit} lines."))],
                )

        # ④ image file check
        if payload is not None and payload.image_path and content_type == ContentType.IMAGE:
            import os
            if not os.path.isfile(payload.image_path):
                return PlacementResult(
                    verdict=Verdict.WARN,
                    warnings=[Conflict(cell_addr=target_cells[0], new_id=element_id,
                        existing_type=ContentType.UNKNOWN, new_type=content_type,
                        verdict=Verdict.WARN, detail=f"image file not found: {payload.image_path}")],
                )

        # ── ⑤ 常识层主动 Advisory（无碰撞也产出） ──

        # ⑤a. 族常识预防性提醒
        if fam == Family.TEXT and role == SemanticRole.ENTITY:
            advisories.append(Advisory(
                level="info", family=fam, element_id=element_id,
                message="Text entities must not overlap each other (readability = physical law).",
                suggest="Keep text blocks disjoint; if this text annotates a shape, set role=ANNOTATION.",
            ))

        # ⑤b. AI 的 role 偏离族先验 → warn（建议，非判决）
        if role == SemanticRole.ENTITY and fam in (Family.CONNECTOR, Family.EMPHASIS, Family.BACKDROP):
            advisories.append(Advisory(
                level="warn", family=fam, element_id=element_id,
                message=f"Family {fam.value} usually OVERLAYS (sits on top of content, not competing for space).",
                suggest=(f"You marked '{element_id}' as ENTITY. "
                         f"If it truly competes for space, fine; "
                         f"else set role={pol.default_role.value.upper()} "
                         f"to join the overlay table."),
            ))

        # ⑤c. Family.BAND 实体互叠 → 先验 forbid（WEAK 级→warn）
        if role == SemanticRole.ENTITY and fam in (Family.BAND, Family.TEXT):
            for oid, ocells in self.info_grid.all_occupied().items():
                if oid == element_id:
                    continue
                # Check overlap
                oc = next(iter(ocells))
                ocell = self.info_grid.get_cell(oc)
                if not ocell or ocell.role not in ENTITY_ROLES:
                    continue
                o_fam = family_of(ocell.content_type or ContentType.UNKNOWN)
                o_v = pol.self_overlap if o_fam == fam else pol.over_entity
                lvl = _verdict_to_level(o_v, pol.strength)
                # Check geometric intersection
                from .serializer import _cells_union
                obbox = _cells_union(ocells, self.config)
                if obbox and _rects_overlap((x, y, x + w, y + h),
                                            (obbox[0], obbox[1], obbox[0] + obbox[2], obbox[1] + obbox[3])):
                    adv = Advisory(
                        level=lvl, family=fam, element_id=element_id,
                        message=(f"Overlaps entity '{oid}' (family {o_fam.value}). "
                                 f"Policy: {o_v.value}/{pol.strength.value}."),
                        suggest=(f"'{fam.value}' self-overlap is {o_v.value} ({pol.strength.value}). "
                                 f"If '{element_id}' is truly an entity competing for space, "
                                 f"move it; if it annotates/connects '{oid}', "
                                 f"change its role to ANNOTATION/CONNECTOR.")
                    )
                    advisories.append(adv)
        # ── ⑥ 语义层碰撞 ──
        covered = self.info_grid.cells_in_bbox(x, y, w, h)
        conflicts = self.matrix.check_all(covered, content_type, element_id, new_role=role)

        # ── ⑦ 结果 ──
        if not conflicts:
            z = ROLE_Z_BASE.get(role, 100)
            self.info_grid.occupy(
                [addr for addr, _ in covered],
                element_id, content_type,
                z_order=z, source="agent",
                payload=payload, role=role,
            )
            if tbl == "entity":
                self._entity_ids.add(element_id)
            else:
                self._overlay_ids.add(element_id)

            # 即使无冲突，常识层的 advisory 仍在
            error_advs = [a for a in advisories if a.level == "error"]
            warn_advs = [a for a in advisories if a.level == "warn"]
            if error_advs:
                return PlacementResult(
                    verdict=Verdict.BLOCK, conflicts=conflicts,
                    advisories=advisories,
                )
            if warn_advs:
                return PlacementResult(
                    verdict=Verdict.WARN, conflicts=[],
                    warnings=[Conflict(verdict=Verdict.WARN,
                        detail=f"{len(warn_advs)} advisory(s) warn of policy deviation")],
                    advisories=advisories,
                )
            return PlacementResult(verdict=Verdict.ALLOW, advisories=advisories)

        blocks = [c for c in conflicts if c.verdict == Verdict.BLOCK]
        verdict = Verdict.BLOCK if blocks else Verdict.WARN

        n_cols = max(1, int(w / self.config.coarse_cell_pt))
        n_rows = max(1, int(h / self.config.coarse_cell_pt))
        free = self.info_grid.find_free(n_cols, n_rows)

        return PlacementResult(
            verdict=verdict, conflicts=blocks,
            warnings=[c for c in conflicts if c.verdict == Verdict.WARN],
            advisories=advisories,
            free_suggestion=free,
        )

    # ═══════════════════════════════════════════════════════════
    # COMMIT / ROLLBACK
    # ═══════════════════════════════════════════════════════════

    def checkpoint(self) -> None:
        self.info_grid.checkpoint()

    def commit(self, ppt_path: str) -> dict:
        import os
        from .serializer import grid_to_ppt
        tmp_path = ppt_path + ".tmp"
        try:
            grid_to_ppt(self.info_grid, self.config, tmp_path)
            os.replace(tmp_path, ppt_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return {"status": "error", "message": str(e)}
        self.info_grid.discard_checkpoint()
        return {"status": "ok", "path": ppt_path}

    def rollback(self) -> dict:
        self.info_grid.rollback()
        return {"status": "rolled_back"}

    def pre_commit_validation(self) -> dict:
        """扫描所有元素，返回校验报告 + advisory 汇总。"""
        from .positioning import parse_cell
        from .text_metrics import estimate_text_size
        from .serializer import _cells_union, _clamp_bbox

        report: dict = {"warnings": [], "errors": [], "advisories": [], "summary": ""}
        occ = self.info_grid.all_occupied()

        for owner_id, fine_cells in occ.items():
            bbox = _cells_union(fine_cells, self.config)
            if bbox is None:
                report["errors"].append({"owner_id": owner_id, "detail": "empty cell set"})
                continue
            x, y, w, h = bbox
            cx, cy, cw, ch = _clamp_bbox(x, y, w, h, self.config)
            cell_sample = self.info_grid.get_cell(next(iter(fine_cells)))
            if not cell_sample:
                continue
            payload = cell_sample.payload
            role = cell_sample.role
            ct = cell_sample.content_type or ContentType.UNKNOWN
            fam = family_of(ct)
            pol = POLICIES[fam]

            # 1: boundary
            if abs(cw - w) > 2 or abs(ch - h) > 2:
                report["warnings"].append({
                    "owner_id": owner_id,
                    "detail": f"bbox ({w:.0f}×{h:.0f}pt) exceeds slide — clamped to ({cw:.0f}×{ch:.0f}pt)."
                })

            # 2: minimum size
            if ct in (ContentType.TEXTBOX, ContentType.SHAPE, ContentType.IMAGE):
                if cw < 24 or ch < 12:
                    report["warnings"].append({
                        "owner_id": owner_id,
                        "detail": f"shape too small ({cw:.0f}×{ch:.0f}pt) — unit error? Min 24×12pt."
                    })

            # 3: text overflow
            if payload and payload.text.strip() and ct in (ContentType.TEXT, ContentType.TEXTBOX, ContentType.ANNOTATION):
                ov_x, ov_y, rw, rh = estimate_text_size(
                    payload.text, font_pt=payload.font_size,
                    line_spacing=payload.line_spacing,
                    box_width_pt=cw, box_height_pt=ch, word_wrap=True,
                )
                if ov_y > 2:
                    report["warnings"].append({
                        "owner_id": owner_id,
                        "detail": f"text overflow: needs {rh:.0f}pt, box {ch:.0f}pt, excess {ov_y:.0f}pt"
                    })

            # 4: role × family policy deviation
            if role == SemanticRole.ENTITY and fam in (Family.CONNECTOR, Family.EMPHASIS, Family.BACKDROP):
                report["advisories"].append({
                    "owner_id": owner_id, "level": "warn",
                    "detail": (
                        f"'{owner_id}' (family {fam.value}) has ENTITY role. "
                        f"Family {fam.value} normally overlays content. "
                        f"Default role is {pol.default_role.value.upper()}. "
                        f"If it truly competes for space keep ENTITY; "
                        f"else change role to join overlay table — do NOT move coordinates."
                    )
                })

            # 5: two TEXT entities overlapping
            if fam == Family.TEXT and role == SemanticRole.ENTITY:
                # Scan for other TEXT entities overlapping this one
                for oid, ocells in occ.items():
                    if oid == owner_id:
                        continue
                    oc = next(iter(ocells), None)
                    if not oc:
                        continue
                    o_cell = self.info_grid.get_cell(oc)
                    if not o_cell or o_cell.role not in ENTITY_ROLES:
                        continue
                    o_bbox = _cells_union(ocells, self.config)
                    if o_bbox and _rects_overlap(
                        (cx, cy, cx + cw, cy + ch),
                        (o_bbox[0], o_bbox[1], o_bbox[0] + o_bbox[2], o_bbox[1] + o_bbox[3])
                    ):
                        report["errors"].append({
                            "owner_id": owner_id,
                            "detail": (
                                f"TEXT entity '{owner_id}' overlaps TEXT entity '{oid}'. "
                                f"Text entities must not overlap (readability = physical law, STRONG). "
                                f"If one text block annotates the other, change its role to ANNOTATION."
                            )
                        })
                        break  # report once per element

        n_w, n_e, n_a = len(report["warnings"]), len(report["errors"]), len(report["advisories"])
        parts = []
        if n_e: parts.append(f"{n_e} error{'s' if n_e != 1 else ''}")
        if n_w: parts.append(f"{n_w} warning{'s' if n_w != 1 else ''}")
        if n_a: parts.append(f"{n_a} advisory{'s' if n_a != 1 else ''}")
        report["summary"] = ", ".join(parts) if parts else "clean"
        return report

    # ═══════════════════════════════════════════════════════════
    # QUERY
    # ═══════════════════════════════════════════════════════════

    def occupied_summary(self) -> dict:
        occ = self.info_grid.occupied_coarse()
        return {oid: list(cells) for oid, cells in occ.items()}

    def density(self) -> float:
        return self.info_grid.density()

    def entity_table(self) -> dict[str, list[str]]:
        occ = self.info_grid.all_occupied()
        return {oid: sorted(cells) for oid, cells in occ.items() if oid in self._entity_ids}

    def overlay_table(self) -> dict[str, list[str]]:
        occ = self.info_grid.all_occupied()
        return {oid: sorted(cells) for oid, cells in occ.items() if oid in self._overlay_ids}

    def load(self, ppt_path: str, slide_index: int = 0) -> dict:
        from .serializer import ppt_to_grid
        self.info_grid = ppt_to_grid(ppt_path, slide_index, self.config)
        slide_id = f"{ppt_path}:{slide_index}"
        self._profiles[slide_id] = self._infer_profile(slide_id)
        return {
            "status": "ok", "slide_index": slide_index,
            "elements": len(self.info_grid.all_occupied()),
            "density": round(self.info_grid.density() * 100, 1),
        }

    def unload(self, element_id: str) -> int:
        return self.info_grid.release(element_id)

    def profile(self, slide_id: str | None = None) -> LayoutProfile | None:
        if slide_id:
            return self._profiles.get(slide_id)
        for p in self._profiles.values():
            return p
        return None

    def _infer_profile(self, slide_id: str) -> LayoutProfile:
        profile = LayoutProfile(name="auto")
        occ = self.info_grid.occupied_coarse()
        for oid, coarse_cells in occ.items():
            rows = set()
            for c in coarse_cells:
                from .positioning import parse_cell
                try:
                    _, r = parse_cell(c)
                    rows.add(r)
                except ValueError:
                    continue
            if not rows:
                continue
            min_r, max_r = min(rows), max(rows)
            if min_r >= self.config.coarse_rows - 1:
                profile.locked_zones.update(coarse_cells)
                profile.decorative_elements.add(oid)
            elif max_r <= 1:
                profile.zones.setdefault("title", []).extend(
                    c for c in coarse_cells
                    if c not in profile.zones.get("title", [])
                )
        return profile


def _rects_overlap(a: tuple[float,float,float,float],
                   b: tuple[float,float,float,float],
                   tol: float = 5.0) -> bool:
    """True if rectangles have true area overlap (not just edge-touch)."""
    ox = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    oy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ox > tol and oy > tol
