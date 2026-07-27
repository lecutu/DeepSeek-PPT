"""
grid/canvas.py — Main controller: classify -> place two-stage + advisory + commit/rollback

Three-layer architecture:
  Geometric — coordinates / clamp / tangent tolerance (positioning + serializer._clamp_bbox)
  Semantic — SemanticRole / dual tables (AI's understanding, final authority)
  Commonsense — OverlapPolicy / Advisory (engine's domain priors, suggestions + validation baseline)
"""

from __future__ import annotations
from .types import (
    GridConfig, ContentType, Verdict, InfoCell,
    PlacementResult, Conflict, SemanticRole, ElementPayload,
    Family, Strength, OverlapPolicy, Advisory,
    ENTITY_ROLES, ROLE_Z_BASE, table_of, POLICIES, family_of,
)
from .info_grid import InformationGrid
from .matrix import InteractionMatrix
from .positioning import cells_to_bbox, is_cell_in_bounds, bbox_to_coarse_cells, bbox_to_fine_cells

_rects_overlap = lambda a, b: a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]
_cells_union = None  # Lazily imported from serializer


class GridCanvas:
    """PPT canvas. Three-layer architecture: geometric -> semantic -> commonsense."""

    def __init__(self, config: GridConfig | None = None):
        self.config = config or GridConfig()
        self.info_grid = InformationGrid(self.config)
        self.matrix = InteractionMatrix(self.config)
        self._decorations: dict[str, dict] = {}
        self._decoration_payloads: list[dict] = []  # Phase 2 -> serializer direct channel
        self._checkpoints: list = []

    def register_decoration(self, deco_id: str, kind: str, x1, y1, x2, y2, **kw):
        """Phase 2 decoration direct channel — pt-coordinate precise render, bypasses grid/cell system."""
        self._decoration_payloads.append(dict(
            type=kind, deco_id=deco_id, x1=x1, y1=y1, x2=x2, y2=y2, **kw,
        ))


    def entity_table(self) -> dict:
        """Return entity-level occupied cells. Callable for legacy test compat."""
        return self.info_grid.occupied_by_all()

    def overlay_table(self) -> dict:
        """Legacy: return overlay-level occupied cells for test compatibility."""
        out = {}
        for oid, cells in self.info_grid.occupied_by_all().items():
            for addr in cells[:1]:
                cell = self.info_grid._cells.get(addr)
                if cell and cell.role not in ENTITY_ROLES:
                    out[oid] = cells
                    break
        return out

    def checkpoint(self):
        from copy import deepcopy
        self._checkpoints.append(deepcopy(self.info_grid))

    def rollback(self):
        if self._checkpoints:
            self.info_grid = self._checkpoints.pop()
            return True
        return False

    # Commonsense layer interface
    def advise_default_role(self, content_type: ContentType) -> SemanticRole:
        """Handrail: when AI doesn't fill role, engine suggests default from family prior."""
        fam = family_of(content_type)
        pol = POLICIES[fam]
        return pol.default_role


    # CORE: try_place (three-layer integration)
    def try_place(self, element_id: str, content_type: ContentType,
                  target_cells: list[str], payload: ElementPayload | None = None) -> PlacementResult:
        """Place an element.

        Three-layer collaboration:
          Commonsense — Family -> OverlapPolicy (handrail + proactive advisory + validation baseline)
          Semantic    — payload.role (AI's understanding, can override commonsense)
          Geometric   — bbox / boundary / clamp
        """
        if not target_cells:
            return PlacementResult(
                verdict=Verdict.BLOCK,
                conflicts=[Conflict(cell_addr="", new_id=element_id,
                    existing_type=ContentType.UNKNOWN, new_type=content_type,
                    verdict=Verdict.BLOCK, detail="empty target region")],
            )

        fam = family_of(content_type)
        pol = POLICIES[fam]

        # ── Handrail: AI didn't fill role -> engine uses family prior default ──
        role = payload.role if payload else pol.default_role
        tbl = table_of(role)
        advisories: list[Advisory] = []

        # ── ① Geometric layer ──
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

        # ── ② Text overflow pre-check ──
        if payload and payload.text.strip() and content_type in (ContentType.TEXT, ContentType.TEXTBOX):
            from .text_metrics import estimate_text_size
            _, ov_y, rw, rh = estimate_text_size(
                payload.text, font_pt=payload.font_size,
                line_spacing=payload.line_spacing,
                box_width_pt=w, box_height_pt=h, word_wrap=True,
            )
            if ov_y > 2:
                advisories.append(Advisory(
                    kind="overflow_v",
                    detail=(f"text overflow: needs {rh:.0f}pt, box {h:.0f}pt, "
                            f"excess {ov_y:.0f}pt"),
                    options=[
                        f"shrink font to {payload.font_size * h / max(rh, 0.1):.0f}pt",
                        f"expand region vertically by {ov_y:.0f}pt",
                        "split text across slides",
                    ],
                ))

        # ── Semantic layer: collision check ──
        covered = self.info_grid.cells_in_bbox(x, y, w, h)
        conflicts = self.matrix.check_all(covered, content_type, element_id,
                                          new_role=role or SemanticRole.ENTITY)

        # ── ⑤ Commonsense proactive Advisory (even when no collision) ──
        # ⑤a. Family-level commonsense preventive reminders (overlay = non-entity families)
        if fam in (Family.CONNECTOR, Family.EMPHASIS, Family.BACKDROP):
            advisories.append(Advisory(
                kind="overlay_placement",
                detail="Placed as overlay — verify it lands on the element it decorates.",
            ))
        if content_type == ContentType.IMAGE:
            advisories.append(Advisory(
                kind="image_checks",
                detail="Image placed — verify aspect ratio + resolution + readability.",
            ))

        # ⑤b. AI's role deviates from family prior -> warn (suggestion, not verdict)
        if payload and payload.role and payload.role != pol.default_role:
            advisories.append(Advisory(
                kind="role_deviation",
                detail=f"AI assigned role={payload.role.value}, family prior suggests {pol.default_role.value}. "
                       f"Check whether {payload.role.value} semantics are intentional.",
            ))

        # ⑤c. Family.BAND entity mutual overlap -> prior forbid (WEAK level -> warn)
        if fam == Family.BAND:
            for addr, cell in covered:
                if cell.owner_id and cell.owner_id != element_id:
                    from .serializer import _cells_union
                    ocells = self.info_grid.occupied_by(cell.owner_id)
                    obbox = _cells_union(ocells, self.config)
                    if obbox and _rects_overlap((x, y, x + w, y + h),
                                                (obbox[0], obbox[1], obbox[0] + obbox[2], obbox[1] + obbox[3])):
                        advisories.append(Advisory(
                            kind="band_overlap",
                            detail=f"BAND '{element_id}' overlaps BAND '{cell.owner_id}'. "
                                   f"Consider spacing or semantic layering.",
                        ))
                        break

        # ── ⑥ Semantic layer collision ──
        if conflicts:
            free = self.info_grid._free_cells_suggestion(len(target_cells))
            return PlacementResult(verdict=Verdict.BLOCK, conflicts=conflicts,
                                   advisories=advisories,
                                   free_suggestion=[free] if free else [])

        # ── ⑦ Result ──
        self.info_grid.occupy_bbox(x, y, w, h, element_id, content_type,
                                   role=role or SemanticRole.ENTITY,
                                   source=payload.source if payload and hasattr(payload, 'source') else "agent")
        return PlacementResult(verdict=Verdict.ALLOW, advisories=advisories)

    def try_place_or_advisory(self, element_id: str, content_type: ContentType,
                               target_cells: list[str], payload=None) -> PlacementResult:
        """Placement attempt — if blocked, return advisory instead of silent failure."""
        result = self.try_place(element_id, content_type, target_cells, payload)
        if result.verdict != Verdict.BLOCK:
            return result
        # Even without collision, commonsense advisories are still there
        fam = family_of(content_type)
        pol = POLICIES[fam]
        return PlacementResult(
            verdict=Verdict.BLOCK,
            conflicts=result.conflicts,
            advisories=[
                Advisory(kind="blocked_with_advice", level="info",
                         detail=f"Blocked by {len(result.conflicts)} conflicts. "
                                f"Consider: role reassignment | coordinate shift | split to next slide.")
            ] + (result.advisories or []),
        )

    def commit(self):
        """Finalize all tentative placements."""
        pass

    def pre_commit_validation(self) -> dict:
        """Scan all elements, return validation report + advisory summary."""
        from .serializer import _cells_union, _clamp_bbox

        errors, warnings, advisories = [], [], []
        for eid, fine_cells in self.info_grid.occupied_by_all().items():
            bbox = _cells_union(fine_cells, self.config)
            if bbox is None:
                errors.append({"owner_id": eid, "detail": "cannot compute bbox from occupied cells"})
                continue
            x, y, w, h = bbox
            cx, cy, cw, ch = _clamp_bbox(x, y, w, h, self.config)

            if abs(cx - x) > 2 or abs(cy - y) > 2 or abs(cw - w) > 2 or abs(ch - h) > 2:
                warnings.append({
                    "owner_id": eid,
                    "kind": "bbox_clamped",
                    "detail": f"bbox ({w:.0f}x{h:.0f}pt) exceeds slide — clamped to ({cw:.0f}x{ch:.0f}pt)."
                })

            ct = self.info_grid.cell_type(eid)
            if ct in (ContentType.TEXTBOX, ContentType.SHAPE, ContentType.IMAGE):
                if cw < 24 or ch < 24:
                    warnings.append({
                        "owner_id": eid,
                        "kind": "too_small",
                        "detail": f"Element ({cw:.0f}x{ch:.0f}pt) below minimum visible size."
                    })

            payload = None
            if hasattr(self, '_phase1_payloads'):
                _, payload = self._phase1_payloads.get(eid, (None, None))
            if payload and payload.text.strip() and ct in (ContentType.TEXT, ContentType.TEXTBOX, ContentType.ANNOTATION):
                from .text_metrics import estimate_text_size
                _, ov_y, rw, rh = estimate_text_size(
                    payload.text, font_pt=payload.font_size,
                    line_spacing=payload.line_spacing,
                    box_width_pt=cw, box_height_pt=ch, word_wrap=True,
                )
                if ov_y > 2:
                    warnings.append({
                        "owner_id": eid,
                        "kind": "overflow_v",
                        "detail": f"text overflow: needs {rh:.0f}pt, box {ch:.0f}pt, excess {ov_y:.0f}pt"
                    })

            entry = self.info_grid._cells.get(list(fine_cells)[0]) if fine_cells else None
            if entry and entry.role:
                role = entry.role
                default = self.advise_default_role(ct)
                if role != default:
                    advisories.append({
                        "owner_id": eid,
                        "kind": "role_mismatch",
                        "detail": f"role={role.value}, family default={default.value}"
                    })

            for deco in self._decoration_payloads:
                if deco.get("type") == "arrow":
                    o_bbox = _cells_union(fine_cells, self.config)
                    if o_bbox and _rects_overlap(
                        (deco_bbox[0], deco_bbox[1], deco_bbox[0] + deco_bbox[2], deco_bbox[1] + deco_bbox[3]),
                        (o_bbox[0], o_bbox[1], o_bbox[0] + o_bbox[2], o_bbox[1] + o_bbox[3])
                    ):
                        warnings.append({
                            "owner_id": eid, "deco_id": deco_id,
                            "kind": "arrow_occlusion",
                            "detail": f"arrow '{deco_id}' may cross-element '{eid}' — check readability"
                        })

        return {"errors": errors, "warnings": warnings, "advisories": advisories}
