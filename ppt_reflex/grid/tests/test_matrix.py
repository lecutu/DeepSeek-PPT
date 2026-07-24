"""grid/tests/test_matrix.py — role-driven collision tests"""
import sys
sys.path.insert(0, "D:/文献搜索员/ppt_reflex")
from grid.types import ContentType, Verdict, Conflict, GridConfig, SemanticRole
from grid.matrix import InteractionMatrix
from grid.info_grid import InformationGrid
from grid.positioning import bbox_to_fine_cells


def test_entity_overlap_blocked():
    """Entity × Entity → BLOCK"""
    m = InteractionMatrix()
    cfg = GridConfig()
    grid = InformationGrid(cfg)
    # place entity A
    addrs = bbox_to_fine_cells(180, 180, 120, 120, cfg)
    grid.occupy(addrs, "A", ContentType.TEXTBOX, role=SemanticRole.ENTITY, source="agent")
    # query overlapping cells for new entity B
    covered = grid.cells_in_bbox(210, 210, 60, 60)
    conflicts = m.check_all(covered, ContentType.TEXTBOX, "B", new_role=SemanticRole.ENTITY)
    assert len(conflicts) > 0, "Entity×Entity should collide"
    assert conflicts[0].verdict == Verdict.BLOCK
    assert "ENTITY" in str(conflicts[0].detail).upper() or "Entity" in conflicts[0].detail
    print(f"  {conflicts[0].detail[:80]}...")
    print("[PASS] entity×entity → BLOCK")


def test_overlay_no_collision():
    """Overlay (CONNECTOR/ANNOTATION/EMPHASIS) → never collides"""
    m = InteractionMatrix()
    cfg = GridConfig()
    grid = InformationGrid(cfg)

    addrs = bbox_to_fine_cells(180, 180, 120, 120, cfg)
    grid.occupy(addrs, "A", ContentType.TEXTBOX, role=SemanticRole.ENTITY, source="agent")

    for role in [SemanticRole.CONNECTOR, SemanticRole.ANNOTATION,
                 SemanticRole.EMPHASIS, SemanticRole.BACKDROP]:
        covered = grid.cells_in_bbox(180, 180, 120, 120)
        conflicts = m.check_all(covered, ContentType.CONNECTOR, f"B_{role.value}",
                                new_role=role)
        assert len(conflicts) == 0, f"{role.value} should not collide with ENTITY"
    print("[PASS] overlay roles → no collision")


def test_same_rect_different_role():
    """Same bbox/ContentType, different role → different collision behavior"""
    m = InteractionMatrix()
    cfg = GridConfig()
    grid = InformationGrid(cfg)

    cell = ["C4"]  # col 2, row 3 → x=60pt, y=90pt
    grid.occupy(cell, "entity_A", ContentType.TEXTBOX,
                role=SemanticRole.ENTITY, source="agent")

    # Same cell, ENTITY → BLOCK
    covered = grid.cells_in_bbox(60, 90, 30, 30)  # x=60 (col 2), y=90 (row 3)
    c1 = m.check_all(covered, ContentType.TEXTBOX, "entity_B", new_role=SemanticRole.ENTITY)
    assert len(c1) > 0, "ENTITY on ENTITY should collide"

    # Same cell, ANNOTATION → 0 collision
    c2 = m.check_all(covered, ContentType.TEXTBOX, "annot_B",
                     new_role=SemanticRole.ANNOTATION)
    assert len(c2) == 0, "ANNOTATION on ENTITY should NOT collide"

    # Same cell, EMPHASIS → 0 collision
    c3 = m.check_all(covered, ContentType.TEXTBOX, "emph_B",
                     new_role=SemanticRole.EMPHASIS)
    assert len(c3) == 0, "EMPHASIS on ENTITY should NOT collide"

    print("[PASS] same rect, role differentiates")


def test_overlay_touches_overlay():
    """Two overlays share cells — still no collision"""
    m = InteractionMatrix()
    cfg = GridConfig()
    grid = InformationGrid(cfg)

    addrs = bbox_to_fine_cells(0, 0, 120, 120, cfg)
    grid.occupy(addrs, "entity_A", ContentType.TEXTBOX,
                role=SemanticRole.ENTITY, source="agent")

    # Place overlay
    grid.occupy(["D4", "D5"], "conn_A", ContentType.CONNECTOR,
                role=SemanticRole.CONNECTOR, source="agent")

    # New overlay overlapping existing overlay + entity → still no collision
    covered = grid.cells_in_bbox(90, 90, 60, 60)
    conflicts = m.check_all(covered, ContentType.ANNOTATION, "annot_B",
                            new_role=SemanticRole.ANNOTATION)
    assert len(conflicts) == 0, "Overlay on overlay+entity = no collision"
    print("[PASS] overlay×overlay → no collision")


def test_role_mislabel_hint_in_detail():
    """When ENTITY overlaps ENTITY, conflict.detail hints '改 role'"""
    m = InteractionMatrix()
    cfg = GridConfig()
    grid = InformationGrid(cfg)

    addrs = bbox_to_fine_cells(180, 180, 120, 120, cfg)
    grid.occupy(addrs, "S1_band", ContentType.TEXTBOX,
                role=SemanticRole.ENTITY, source="agent")

    covered = grid.cells_in_bbox(180, 180, 120, 120)
    conflicts = m.check_all(covered, ContentType.CONNECTOR, "vr_arrow",
                            new_role=SemanticRole.ENTITY)
    assert len(conflicts) > 0
    detail = conflicts[0].detail
    assert "role" in detail.lower(), f"Hint should mention role, got: {detail}"
    assert "coordinates" in detail.lower() or "move" in detail.lower(), \
        f"Hint should say 'do NOT move coordinates', got: {detail}"
    print(f"  Hint: {detail[:120]}")
    print("[PASS] mislabeled ENTITY conflict → '改 role 别改坐标' hint")


def test_legacy_judge_always_allow():
    """Legacy judge() is vestigial — always ALLOW (collision is role-driven)."""
    m = InteractionMatrix()
    assert m.judge(ContentType.TEXT, ContentType.TEXT) == Verdict.ALLOW
    assert m.judge(ContentType.TEXT, ContentType.IMAGE) == Verdict.ALLOW
    print("[PASS] legacy judge → always ALLOW")


if __name__ == "__main__":
    test_entity_overlap_blocked()
    test_overlay_no_collision()
    test_same_rect_different_role()
    test_overlay_touches_overlay()
    test_role_mislabel_hint_in_detail()
    test_legacy_judge_always_allow()
    print("\n✓ All role-matrix tests PASSED")
